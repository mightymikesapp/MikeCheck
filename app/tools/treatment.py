"""Treatment analysis tools for legal research.

This module provides MCP tools for analyzing case treatment and validity,
serving as a free alternative to Shepard's Citations and KeyCite.
"""

import logging
from typing import Any, cast

from fastmcp import FastMCP

from app.analysis.treatment_classifier import TreatmentAnalysis, TreatmentClassifier
from app.config import settings
from app.logging_config import tool_logging
from app.logging_utils import log_event, log_operation
from app.mcp_client import get_client
from app.mcp_types import ToolPayload
from app.types import CourtListenerCase, TreatmentResult, TreatmentWarning

logger = logging.getLogger(__name__)

# Initialize classifier
classifier = TreatmentClassifier()


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


# Implementation functions (can be called directly or via MCP tools)
async def check_case_validity_impl(
    citation: str, request_id: str | None = None
) -> TreatmentResult:
    """Check if a case is still good law by analyzing citing cases.

    This provides a free alternative to Shepard's Citations and KeyCite by:
    1. Finding all cases that cite the target case
    2. Analyzing treatment signals (overruled, questioned, followed, etc.)
    3. Providing a confidence-scored validity assessment

    Args:
        citation: Legal citation to check (e.g., "410 U.S. 113" or "Roe v. Wade")

    Returns:
        Dictionary containing validity assessment and analysis
    """
    client = get_client()

    with log_operation(
        logger,
        tool_name="check_case_validity",
        request_id=request_id,
        query_params={"citation": citation},
        event="check_case_validity",
    ):
        # Step 1: Look up the target case
        target_case = await client.lookup_citation(citation, request_id=request_id)

        if "error" in target_case:
            return {
                "error": f"Could not find case: {target_case.get('error')}",
                "citation": citation,
            }

        # Step 2: Find citing cases
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
            }
        log_event(
            logger,
            "Citing cases located",
            tool_name="check_case_validity",
            request_id=request_id,
            query_params={"citation": citation},
            citation_count=len(citing_cases),
            extra_context={
                "incomplete_data": citing_cases_result.get("incomplete_data", False),
                "warnings": citing_cases_result.get("warnings", []),
            },
            event="citing_cases_fetched",
        )

        # Step 3: First pass - analyze all cases with snippets
        initial_treatments: list[tuple[CourtListenerCase, TreatmentAnalysis]] = []
        for citing_case in citing_cases:
            analysis = classifier.classify_treatment(citing_case, citation)
            initial_treatments.append((citing_case, analysis))

        # Step 4: Identify cases needing full text analysis
        strategy = settings.fetch_full_text_strategy
        cases_for_full_text = []

        for citing_case, initial_analysis in initial_treatments:
            if classifier.should_fetch_full_text(initial_analysis, strategy):
                cases_for_full_text.append((citing_case, initial_analysis))

        log_event(
            logger,
            "Full text selection complete",
            tool_name="check_case_validity",
            request_id=request_id,
            query_params={"citation": citation},
            extra_context={
                "strategy": strategy,
                "selected_for_full_text": len(cases_for_full_text),
            },
        )

        # Step 5: Fetch full text and re-analyze (limited by max_full_text_fetches)
        # PERFORMANCE: Parallelized full-text fetching to avoid N+1 query pattern
        import asyncio

        # Collect all opinion IDs that need fetching
        fetch_tasks: list[tuple[CourtListenerCase, TreatmentAnalysis, int]] = []
        for citing_case, initial_analysis in initial_treatments:
            needs_full_text = any(c is citing_case for c, _ in cases_for_full_text)
            if needs_full_text and len(fetch_tasks) < settings.max_full_text_fetches:
                # Extract opinion IDs from the case
                opinion_ids: list[int] = []
                for op in citing_case.get("opinions", []):
                    if not isinstance(op, dict):
                        continue
                    opinion_id = op.get("id")
                    if isinstance(opinion_id, int):
                        opinion_ids.append(opinion_id)

                if opinion_ids:
                    fetch_tasks.append((citing_case, initial_analysis, opinion_ids[0]))

        # Fetch all full texts in parallel with concurrency control
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

        async def fetch_with_limit(case: CourtListenerCase, analysis: TreatmentAnalysis, opinion_id: int):
            """Fetch full text with semaphore-controlled concurrency."""
            async with semaphore:
                try:
                    full_text = await client.get_opinion_full_text(opinion_id, request_id=request_id)
                    if full_text:
                        log_event(
                            logger,
                            "Enhanced analysis with full text",
                            tool_name="check_case_validity",
                            request_id=request_id,
                            query_params={"citation": citation},
                            event="full_text_analysis",
                        )
                        return (case, classifier.classify_treatment(case, citation, full_text=full_text), True)
                    else:
                        return (case, analysis, False)
                except Exception as e:
                    log_event(
                        logger,
                        f"Failed to fetch full text: {e}, using snippet analysis",
                        level=logging.WARNING,
                        tool_name="check_case_validity",
                        request_id=request_id,
                        query_params={"citation": citation},
                        event="full_text_error",
                    )
                    return (case, analysis, False)

        # Execute all fetches in parallel
        fetch_results = await asyncio.gather(
            *[fetch_with_limit(case, analysis, op_id) for case, analysis, op_id in fetch_tasks],
            return_exceptions=True
        )

        # Build treatments list, matching original order and handling results
        full_text_count = 0
        case_to_enhanced_analysis: dict[int, TreatmentAnalysis] = {}

        for result in fetch_results:
            if isinstance(result, Exception):
                continue
            case, enhanced_analysis, success = result
            if success:
                full_text_count += 1
                # Use case ID as key to map enhanced analysis back
                case_id = case.get("id") or id(case)
                case_to_enhanced_analysis[case_id] = enhanced_analysis

        # Build final treatments list in original order
        treatments: list[TreatmentAnalysis] = []
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
            query_params={"citation": citation},
            citation_count=len(treatments),
            extra_context={"full_text_count": full_text_count},
        )

        # Step 6: Aggregate treatments
        if treatments:
            aggregated = classifier.aggregate_treatments(treatments, citation)

            # Build warnings list
            warnings: list[TreatmentWarning] = []
            for neg_treatment in aggregated.negative_treatments:
                for signal in neg_treatment.signals_found[:2]:  # Top 2 signals
                    warnings.append(
                        {
                            "signal": signal.signal,
                            "case_name": neg_treatment.case_name,
                            "citation": neg_treatment.citation,
                            "date_filed": neg_treatment.date_filed,
                            "excerpt": signal.context,
                        }
                    )

            base_confidence = aggregated.confidence
            failed_requests = _coerce_failed_requests(
                citing_cases_result.get("failed_requests")
            )
            incomplete_data = _coerce_incomplete_flag(
                citing_cases_result.get("incomplete_data")
            ) or bool(failed_requests)
            result_warnings: list[str | TreatmentWarning] = [
                *warnings,
                *_coerce_warnings(citing_cases_result.get("warnings")),
            ]

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
                "warnings": result_warnings,
                "failed_requests": failed_requests,
                "incomplete_data": incomplete_data,
                "recommendation": (
                    "Manual review recommended"
                    if not aggregated.is_good_law or aggregated.negative_count > 0
                    else "Case appears reliable"
                ),
            }
        else:
            # No citing cases found
            return {
                "citation": citation,
                "case_name": target_case.get("caseName", "Unknown"),
                "is_good_law": True,
                "confidence": 0.5,
                "summary": "No citing cases found. Unable to determine treatment.",
                "total_citing_cases": 0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "unknown_count": 0,
                "warnings": _coerce_warnings(citing_cases_result.get("warnings")),
                "failed_requests": _coerce_failed_requests(
                    citing_cases_result.get("failed_requests")
                ),
                "incomplete_data": _coerce_incomplete_flag(
                    citing_cases_result.get("incomplete_data")
                ),
                "recommendation": "Case has not been cited. Validity uncertain.",
            }

    # log_operation will capture errors


async def get_citing_cases_impl(
    citation: str,
    treatment_filter: str | None = None,
    limit: int = 20,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Get cases that cite a given citation, optionally filtered by treatment type.

    Args:
        citation: The citation to find citing cases for
        treatment_filter: Optional filter: "positive", "negative", or "neutral"
        limit: Maximum number of results to return (default 20)

    Returns:
        Dictionary containing citing cases with treatment analysis
    """
    client = get_client()

    with log_operation(
        logger,
        tool_name="get_citing_cases",
        request_id=request_id,
        query_params={"citation": citation, "treatment_filter": treatment_filter, "limit": limit},
        event="get_citing_cases",
    ):
        # Find citing cases
        citing_cases_result = await client.find_citing_cases(
            citation, limit=limit, request_id=request_id
        )
        raw_results = citing_cases_result.get("results")
        if not isinstance(raw_results, list):
            return {
                "citation": citation,
                "total_found": 0,
                "citing_cases": [],
                "filter_applied": treatment_filter,
                "incomplete_data": True,
                "warnings": _coerce_warnings(citing_cases_result.get("warnings")),
                "failed_requests": _coerce_failed_requests(
                    citing_cases_result.get("failed_requests")
                ),
            }

        citing_cases = _coerce_cases(raw_results)
        failed_requests = _coerce_failed_requests(
            citing_cases_result.get("failed_requests")
        )
        incomplete_data = _coerce_incomplete_flag(
            citing_cases_result.get("incomplete_data")
        ) or bool(failed_requests)

        # Analyze treatment
        treatments = []
        for citing_case in citing_cases:
            analysis = classifier.classify_treatment(citing_case, citation)

            # Apply filter if specified
            if treatment_filter:
                filter_lower = treatment_filter.lower()
                if filter_lower == "positive" and analysis.treatment_type.value != "positive":
                    continue
                elif filter_lower == "negative" and analysis.treatment_type.value != "negative":
                    continue
                elif filter_lower == "neutral" and analysis.treatment_type.value != "neutral":
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
                }
            )

        log_event(
            logger,
            "Citing cases analyzed",
            tool_name="get_citing_cases",
            request_id=request_id,
            query_params={"citation": citation, "treatment_filter": treatment_filter},
            citation_count=len(treatments),
        )

        return {
            "citation": citation,
            "total_found": len(citing_cases),
            "citing_cases": treatments,
            "filter_applied": treatment_filter,
            "incomplete_data": incomplete_data,
            "warnings": _coerce_warnings(citing_cases_result.get("warnings")),
            "failed_requests": failed_requests,
        }


# Create treatment tools server
treatment_server: FastMCP[ToolPayload] = FastMCP(
    name="Treatment Analysis Tools",
    instructions="Tools for analyzing case treatment and validity (Shepardizing alternative)",
)


@treatment_server.tool()
@tool_logging("check_case_validity")
async def check_case_validity(
    citation: str, request_id: str | None = None
) -> TreatmentResult:
    """Check if a case is still good law by analyzing citing cases.

    This tool provides a free alternative to Shepard's Citations and KeyCite by:
    1. Finding all cases that cite the target case
    2. Analyzing treatment signals (overruled, questioned, followed, etc.)
    3. Providing a confidence-scored validity assessment

    Args:
        citation: Legal citation to check (e.g., "410 U.S. 113" or "Roe v. Wade")

    Returns:
        Dictionary containing:
        - is_good_law: Boolean indicating if case appears to be good law
        - confidence: Float 0-1 confidence score
        - summary: Human-readable summary
        - total_citing_cases: Number of citing cases analyzed
        - positive_count: Number of positive treatments
        - negative_count: Number of negative treatments
        - neutral_count: Number of neutral citations
        - negative_treatments: List of cases with negative treatment
        - warnings: List of specific warnings if validity is questionable

    Example:
        >>> await check_case_validity("410 U.S. 113")
        {
            "is_good_law": False,
            "confidence": 0.95,
            "summary": "Case overruled by Dobbs v. Jackson...",
            "negative_count": 1,
            ...
        }
    """
    return await check_case_validity_impl(citation, request_id=request_id)


@treatment_server.tool()
@tool_logging("get_citing_cases")
async def get_citing_cases(
    citation: str,
    treatment_filter: str | None = None,
    limit: int = 20,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Get cases that cite a given citation, optionally filtered by treatment type.

    Args:
        citation: The citation to find citing cases for
        treatment_filter: Optional filter: "positive", "negative", or "neutral"
        limit: Maximum number of results to return (default 20)

    Returns:
        Dictionary containing:
        - citation: The target citation
        - total_found: Total number of citing cases
        - citing_cases: List of citing cases with treatment analysis
        - filter_applied: The filter that was applied, if any

    Example:
        >>> await get_citing_cases("410 U.S. 113", treatment_filter="negative")
        {
            "citation": "410 U.S. 113",
            "total_found": 50,
            "citing_cases": [...],
            "filter_applied": "negative"
        }
    """
    return await get_citing_cases_impl(
        citation, treatment_filter, limit, request_id=request_id
    )
