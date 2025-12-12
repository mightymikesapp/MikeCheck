"""Treatment analysis tools for legal research.

This module provides MCP tools for analyzing case treatment and validity,
serving as a free alternative to Shepard's Citations and KeyCite.
"""

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import Any, cast

from dateutil.relativedelta import relativedelta
from fastmcp import FastMCP

from app.analysis.treatment_classifier import TreatmentClassifier
from app.config import settings
from app.logging_config import tool_logging
from app.logging_utils import log_event, log_operation
from app.mcp_client import get_client
from app.mcp_types import ToolPayload
from app.types import CourtListenerCase, TreatmentResult, TreatmentWarning

logger = logging.getLogger(__name__)

# Initialize classifier
classifier = TreatmentClassifier()
_classification_executor: ProcessPoolExecutor | None = None


def _classifier_concurrency() -> int:
    """Return a safe concurrency limit for classification tasks."""
    return max(1, settings.treatment_classifier_workers)


def _get_classification_executor() -> ProcessPoolExecutor:
    """Return a lazily initialized process pool for classification."""
    global _classification_executor
    if _classification_executor is None:
        _classification_executor = ProcessPoolExecutor(
            max_workers=_classifier_concurrency()
        )
    return _classification_executor


async def start_classification_executor() -> None:
    """Initialize the classification executor during application startup."""
    _get_classification_executor()


async def shutdown_classification_executor() -> None:
    """Cleanly shut down the classification executor during application shutdown."""
    global _classification_executor
    if _classification_executor:
        _classification_executor.shutdown(wait=True)
        _classification_executor = None


def _coerce_failed_requests(raw_value: Any) -> list[dict[str, object]]:
    """Ensure failed request entries are dictionaries."""
    if not isinstance(raw_value, list):
        return []
    return [entry for entry in raw_value if isinstance(entry, dict)]


def _coerce_warnings(raw_value: Any) -> list[str | TreatmentWarning]:
    """Normalize warnings from API responses to supported values."""
    if not isinstance(raw_value, list):
        return []
    warnings: list[str | TreatmentWarning] = []
    for item in raw_value:
        if isinstance(item, str):
            warnings.append(item)
        elif isinstance(item, dict):
            warnings.append(cast(TreatmentWarning, item))
    return warnings


def _coerce_incomplete_flag(raw_value: Any) -> bool:
    """Return a boolean flag for incomplete data markers."""
    return raw_value is True


def _coerce_cases(raw_results: list[Any]) -> list[CourtListenerCase]:
    """Filter API results down to CourtListener case dictionaries."""
    cases: list[CourtListenerCase] = []
    for case in raw_results:
        if isinstance(case, dict):
            cases.append(cast(CourtListenerCase, case))
    return cases


async def _classify_case_in_executor(
    case: CourtListenerCase, citation: str, semaphore: asyncio.Semaphore
) -> Any:
    """Run treatment classification in the process pool with concurrency limits."""
    async with semaphore:
        loop = asyncio.get_running_loop()
        executor = _get_classification_executor()
        return await loop.run_in_executor(
            executor, classifier.classify_treatment, case, citation
        )


async def check_case_validity_impl(
    citation: str,
    request_id: str | None = None,
    job_id: str | None = None,
) -> TreatmentResult:
    """Check if a case is still good law by analyzing citing cases."""
    client = get_client()

    with log_operation(
        logger,
        tool_name="check_case_validity",
        request_id=request_id,
        job_id=job_id,
        query_params={"citation": citation},
        event="check_case_validity",
    ):
        target_case = await client.lookup_citation(citation, request_id=request_id)
        if "error" in target_case:
            return {
                "error": f"Could not find case: {target_case.get('error')}",
                "citation": citation,
                "job_id": job_id,
            }

        citing_cases_result = await client.find_citing_cases(
            citation,
            limit=settings.max_citing_cases,
            request_id=request_id,
        )
        raw_results = citing_cases_result.get("results")
        if not isinstance(raw_results, list):
            return {
                "error": "Unexpected response format when fetching citing cases.",
                "citation": citation,
                "failed_requests": _coerce_failed_requests(
                    citing_cases_result.get("failed_requests")
                ),
                "warnings": _coerce_warnings(citing_cases_result.get("warnings")),
                "incomplete_data": True,
                "job_id": job_id,
            }

        citing_cases = _coerce_cases(raw_results)
        if not citing_cases and raw_results:
            return {
                "error": "No usable citing cases returned from API response.",
                "citation": citation,
                "failed_requests": _coerce_failed_requests(
                    citing_cases_result.get("failed_requests")
                ),
                "warnings": _coerce_warnings(citing_cases_result.get("warnings")),
                "incomplete_data": True,
                "job_id": job_id,
            }

        log_event(
            logger,
            "Citing cases located",
            tool_name="check_case_validity",
            request_id=request_id,
            job_id=job_id,
            query_params={"citation": citation},
            citation_count=len(citing_cases),
            extra_context={
                "incomplete_data": citing_cases_result.get("incomplete_data", False),
                "warnings": citing_cases_result.get("warnings", []),
            },
            event="citing_cases_fetched",
        )

        # Parallelize initial analysis (MEDIUM Bottleneck #4 fix)
        semaphore = asyncio.Semaphore(_classifier_concurrency())

        analyses = await asyncio.gather(
            *[
                _classify_case_in_executor(case, citation, semaphore)
                for case in citing_cases
            ],
            return_exceptions=True,
        )

        initial_treatments = []
        cases_for_full_text = []
        strategy = settings.fetch_full_text_strategy

        for citing_case, analysis in zip(citing_cases, analyses):
            if isinstance(analysis, Exception):
                continue
            initial_treatments.append((citing_case, analysis))

            if classifier.should_fetch_full_text(analysis, strategy):
                cases_for_full_text.append((citing_case, analysis))

        # Parallel Fetching Logic
        fetch_tasks: list[tuple[CourtListenerCase, TreatmentAnalysis, int]] = []
        for citing_case, initial_analysis in cases_for_full_text:
            if len(fetch_tasks) >= settings.max_full_text_fetches:
                break

            opinion_ids = []
            for op in citing_case.get("opinions", []):
                if isinstance(op, dict) and isinstance(op.get("id"), int):
                    opinion_ids.append(op["id"])
            if opinion_ids:
                fetch_tasks.append((citing_case, initial_analysis, opinion_ids[0]))

        semaphore = asyncio.Semaphore(5)

        async def fetch_with_limit(case, analysis, opinion_id):
            async with semaphore:
                try:
                    full_text = await client.get_opinion_full_text(
                        opinion_id, request_id=request_id
                    )
                    if full_text:
                        return (
                            case,
                            classifier.classify_treatment(case, citation, full_text=full_text),
                            True,
                        )
                    return (case, analysis, False)
                except Exception:
                    return (case, analysis, False)

        fetch_results = await asyncio.gather(
            *[fetch_with_limit(case, analysis, op_id) for case, analysis, op_id in fetch_tasks],
            return_exceptions=True,
        )

        case_to_enhanced_analysis = {}
        full_text_count = 0
        for result in fetch_results:
            if isinstance(result, Exception):
                continue
            case, enhanced_analysis, success = result
            if success:
                full_text_count += 1
                case_id = case.get("id") or id(case)
                case_to_enhanced_analysis[case_id] = enhanced_analysis

        treatments = []
        for citing_case, initial_analysis in initial_treatments:
            case_id = citing_case.get("id") or id(citing_case)
            if case_id in case_to_enhanced_analysis:
                treatments.append(case_to_enhanced_analysis[case_id])
            else:
                treatments.append(initial_analysis)

        log_event(
            logger,
            "Completed analysis",
            tool_name="check_case_validity",
            request_id=request_id,
            job_id=job_id,
            extra_context={"full_text_count": full_text_count},
        )

        if treatments:
            aggregated = classifier.aggregate_treatments(treatments, citation)

            warnings = []
            for neg_treatment in aggregated.negative_treatments:
                for signal in neg_treatment.signals_found[:2]:
                    warnings.append(
                        {
                            "signal": signal.signal,
                            "case_name": neg_treatment.case_name,
                            "citation": neg_treatment.citation,
                            "date_filed": neg_treatment.date_filed,
                            "excerpt": signal.context,
                            "opinion_type": signal.opinion_type,
                        }
                    )

            base_confidence = aggregated.confidence
            failed_requests = _coerce_failed_requests(citing_cases_result.get("failed_requests"))
            incomplete_data = _coerce_incomplete_flag(
                citing_cases_result.get("incomplete_data")
            ) or bool(failed_requests)

            if incomplete_data:
                base_confidence = max(base_confidence * 0.8, 0.3)

            return {
                "citation": citation,
                "case_name": target_case.get("caseName", "Unknown"),
                "is_good_law": aggregated.is_good_law,
                "confidence": round(base_confidence, 2),
                "summary": aggregated.summary,
                "total_citing_cases": aggregated.total_citing_cases,
                "positive_count": aggregated.positive_count,
                "negative_count": aggregated.negative_count,
                "neutral_count": aggregated.neutral_count,
                "unknown_count": aggregated.unknown_count,
                "warnings": warnings + _coerce_warnings(citing_cases_result.get("warnings")),
                "failed_requests": failed_requests,
                "incomplete_data": incomplete_data,
                "job_id": job_id,
                "recommendation": (
                    "Manual review recommended"
                    if not aggregated.is_good_law or aggregated.negative_count > 0
                    else "Case appears reliable"
                ),
                "treatment_context": aggregated.treatment_context,
                "treatment_by_opinion_type": aggregated.treatment_by_opinion_type,
            }
        else:
            return {
                "citation": citation,
                "case_name": target_case.get("caseName", "Unknown"),
                "is_good_law": True,
                "confidence": 0.5,
                "summary": "No citing cases found.",
                "total_citing_cases": 0,
                "job_id": job_id,
                "treatment_context": "neutral",
            }


async def get_citing_cases_impl(
    citation: str,
    treatment_filter: str | None = None,
    limit: int = 20,
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Get cases that cite a given citation."""
    client = get_client()
    with log_operation(
        logger,
        tool_name="get_citing_cases",
        request_id=request_id,
        job_id=job_id,
        query_params={"citation": citation},
    ):
        citing_cases_result = await client.find_citing_cases(
            citation, limit=limit, request_id=request_id
        )
        raw_results = citing_cases_result.get("results")
        if not isinstance(raw_results, list):
            return {"citation": citation, "total_found": 0, "citing_cases": []}

        citing_cases = _coerce_cases(raw_results)

        # Parallelize classification (HIGH Bottleneck #3 fix)
        semaphore = asyncio.Semaphore(_classifier_concurrency())

        analyses = await asyncio.gather(
            *[
                _classify_case_in_executor(case, citation, semaphore)
                for case in citing_cases
            ],
            return_exceptions=True,
        )

        treatments = []
        for analysis in analyses:
            if isinstance(analysis, Exception):
                continue
            if treatment_filter:
                if analysis.treatment_type.value != treatment_filter.lower():
                    continue
            treatments.append(
                {
                    "case_name": analysis.case_name,
                    "citation": analysis.citation,
                    "date_filed": analysis.date_filed,
                    "treatment": analysis.treatment_type.value,
                    "confidence": round(analysis.confidence, 2),
                    "signals": [s.signal for s in analysis.signals_found],
                    "excerpt": analysis.excerpt,
                    "treatment_context": analysis.treatment_context,
                    "opinion_breakdown": analysis.opinion_breakdown,
                }
            )

        return {
            "citation": citation,
            "total_found": len(citing_cases),
            "citing_cases": treatments,
            "filter_applied": treatment_filter,
            "incomplete_data": citing_cases_result.get("incomplete_data", False),
        }


async def treatment_timeline_impl(
    citation: str,
    buckets: str = "5y",
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Generate a timeline of treatment over time."""
    client = get_client()

    # 1. Look up target case
    target_case = await client.lookup_citation(citation, request_id=request_id)
    case_name = target_case.get("caseName", "Unknown")

    # 2. Get all citing cases (max limit to get good distribution)
    # Using a higher limit for timeline to be meaningful
    citing_cases_result = await client.find_citing_cases(citation, limit=300, request_id=request_id)
    raw_results = citing_cases_result.get("results")
    if not isinstance(raw_results, list):
        return {"error": "Failed to fetch citing cases"}

    citing_cases = _coerce_cases(raw_results)

    # 3. Analyze all cases in parallel (CRITICAL Bottleneck #2 fix)
    # Using Semaphore to limit concurrent analysis while respecting API rate limits
    semaphore = asyncio.Semaphore(_classifier_concurrency())

    analyses = await asyncio.gather(
        *[
            _classify_case_in_executor(case, citation, semaphore)
            for case in citing_cases
        ],
        return_exceptions=True,
    )

    treatments = []
    for analysis in analyses:
        if isinstance(analysis, Exception):
            continue
        if analysis.date_filed:
            treatments.append(analysis)

    if not treatments:
        return {
            "citation": citation,
            "case_name": case_name,
            "buckets": [],
            "metadata": {"total_citing_cases": 0},
        }

    # 4. Bucket Logic
    treatments.sort(key=lambda x: x.date_filed or "")

    # Parse start date
    try:
        start_date = datetime.strptime(treatments[0].date_filed, "%Y-%m-%d")
    except (ValueError, TypeError):
        start_date = datetime.now()  # Fallback

    # Determine bucket delta
    if buckets.endswith("y"):
        years = int(buckets[:-1])
        delta = relativedelta(years=years)
    else:
        # Default to 5y
        delta = relativedelta(years=5)

    bucket_bins = []
    current_start = start_date
    current_end = current_start + delta - relativedelta(days=1)

    # Group into buckets
    current_bucket = {
        "start_date": current_start.strftime("%Y-%m-%d"),
        "end_date": current_end.strftime("%Y-%m-%d"),
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "key_cases": [],
    }

    for t in treatments:
        try:
            t_date = datetime.strptime(t.date_filed, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        while t_date > current_end:
            # Close current bucket
            if (
                current_bucket["positive_count"]
                + current_bucket["negative_count"]
                + current_bucket["neutral_count"]
                > 0
            ):
                bucket_bins.append(current_bucket)

            # Start new bucket
            current_start = current_end + relativedelta(days=1)
            current_end = current_start + delta - relativedelta(days=1)
            current_bucket = {
                "start_date": current_start.strftime("%Y-%m-%d"),
                "end_date": current_end.strftime("%Y-%m-%d"),
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "key_cases": [],
            }

        # Add to current bucket
        if t.treatment_type.value == "positive":
            current_bucket["positive_count"] += 1
        elif t.treatment_type.value == "negative":
            current_bucket["negative_count"] += 1
        else:
            current_bucket["neutral_count"] += 1

        # Add key case (prioritize negative/positive)
        if len(current_bucket["key_cases"]) < 3:
            if t.treatment_type.value != "neutral" or len(current_bucket["key_cases"]) < 1:
                current_bucket["key_cases"].append(
                    {
                        "citation": t.citation,
                        "case_name": t.case_name,
                        "treatment": t.treatment_type.value,
                        "date_filed": t.date_filed,
                    }
                )

    # Append last bucket
    if (
        current_bucket["positive_count"]
        + current_bucket["negative_count"]
        + current_bucket["neutral_count"]
        > 0
    ):
        bucket_bins.append(current_bucket)

    # 5. Generate Mermaid Timeline
    mermaid_lines = ["timeline"]
    mermaid_lines.append(f"    title History of {case_name}")
    for bucket in bucket_bins:
        year_label = bucket["start_date"][:4]
        mermaid_lines.append(f"    {year_label}")
        for case in bucket["key_cases"]:
            label = f"{case['case_name']} ({case['treatment']})"
            mermaid_lines.append(f"      : {label}")

    return {
        "citation": citation,
        "case_name": case_name,
        "bucket_size": buckets,
        "buckets": bucket_bins,
        "metadata": {"total_citing_cases": len(treatments)},
        "mermaid_timeline": "\n".join(mermaid_lines),
    }


treatment_server: FastMCP[ToolPayload] = FastMCP(
    name="Treatment Analysis Tools",
    instructions="Tools for analyzing case treatment and validity (Shepardizing alternative)",
)


@treatment_server.tool()
@tool_logging("check_case_validity")
async def check_case_validity(
    citation: str, request_id: str | None = None, job_id: str | None = None
) -> TreatmentResult:
    """Check if a case is still good law by analyzing citing cases."""
    return await check_case_validity_impl(citation, request_id=request_id, job_id=job_id)


@treatment_server.tool()
@tool_logging("get_citing_cases")
async def get_citing_cases(
    citation: str,
    treatment_filter: str | None = None,
    limit: int = 20,
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Get cases that cite a given citation."""
    return await get_citing_cases_impl(
        citation, treatment_filter, limit, request_id=request_id, job_id=job_id
    )


@treatment_server.tool()
@tool_logging("treatment_timeline")
async def treatment_timeline(
    citation: str,
    buckets: str = "5y",
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Generate a timeline of treatment over time.

    Output a histogram of positive vs negative treatments over time.
    Useful for visualizing doctrinal drift.
    """
    return await treatment_timeline_impl(citation, buckets, request_id=request_id, job_id=job_id)
