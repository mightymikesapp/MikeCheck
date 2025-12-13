"""Jurisdiction and circuit analysis tools for legal research.

This module provides MCP tools for analyzing how different jurisdictions
treat cases, with specialized support for detecting federal circuit splits.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from app.analysis.circuit_analyzer import CircuitAnalyzer
from app.config import settings
from app.logging_config import tool_logging
from app.logging_utils import log_event, log_operation
from app.mcp_client import get_client
from app.mcp_types import ToolPayload
from app.tools.treatment import _classify_parallel, _coerce_cases

logger = logging.getLogger(__name__)

MAX_CITING_CASES_FOR_SPLIT_ANALYSIS = 200
DEFAULT_SPLIT_THRESHOLD = 0.6

jurisdiction_server: FastMCP[ToolPayload] = FastMCP(
    name="Jurisdiction Analysis Tools",
    instructions="Tools for analyzing how different jurisdictions and circuits treat cases",
)


async def find_circuit_splits_impl(
    citation: str,
    min_cases_per_circuit: int = 2,
    split_threshold: float = DEFAULT_SPLIT_THRESHOLD,
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Detect potential circuit splits for a given case.

    Args:
        citation: Citation to analyze (e.g., "410 U.S. 113")
        min_cases_per_circuit: Minimum citing cases needed per circuit (default: 2)
        split_threshold: Threshold for determining dominant treatment (default: 0.6)
        request_id: Optional request ID for logging
        job_id: Optional job ID for tracking

    Returns:
        Dictionary containing split detection results or error
    """
    client = get_client()

    with log_operation(
        logger,
        tool_name="find_circuit_splits",
        request_id=request_id,
        job_id=job_id,
        query_params={"citation": citation, "min_cases_per_circuit": min_cases_per_circuit},
        event="find_circuit_splits",
    ):
        # Step 1: Look up the target case
        target_case = await client.lookup_citation(citation, request_id=request_id)
        if "error" in target_case:
            return {
                "error": f"Could not find case: {target_case.get('error')}",
                "citation": citation,
                "job_id": job_id,
            }

        case_name = target_case.get("caseName", "Unknown")

        log_event(
            logger,
            "Target case located for circuit split analysis",
            tool_name="find_circuit_splits",
            request_id=request_id,
            job_id=job_id,
            query_params={"citation": citation},
            extra_context={"case_name": case_name},
            event="find_circuit_splits_case_located",
        )

        # Step 2: Get citing cases (use larger limit to get good circuit coverage)
        citing_limit = min(settings.max_citing_cases, MAX_CITING_CASES_FOR_SPLIT_ANALYSIS)
        citing_cases_result = await client.find_citing_cases(
            citation, limit=citing_limit, request_id=request_id
        )

        raw_results = citing_cases_result.get("results")
        if not isinstance(raw_results, list):
            return {
                "error": "Unexpected response format when fetching citing cases",
                "citation": citation,
                "job_id": job_id,
            }

        citing_cases = _coerce_cases(raw_results)

        if not citing_cases:
            return {
                "citation": citation,
                "case_name": case_name,
                "split_detected": False,
                "message": "No citing cases found",
                "job_id": job_id,
            }

        log_event(
            logger,
            "Citing cases fetched for circuit split analysis",
            tool_name="find_circuit_splits",
            request_id=request_id,
            job_id=job_id,
            query_params={"citation": citation},
            citation_count=len(citing_cases),
            event="find_circuit_splits_citing_cases_fetched",
        )

        # Step 3: Classify treatment for all citing cases
        analyses = await _classify_parallel(citing_cases, citation)

        # Filter out exceptions
        treatments = []
        valid_cases = []
        for case, analysis in zip(citing_cases, analyses):
            if not isinstance(analysis, BaseException):
                treatments.append(analysis)
                valid_cases.append(case)

        if not treatments:
            return {
                "citation": citation,
                "case_name": case_name,
                "split_detected": False,
                "message": "No valid treatment analyses available",
                "job_id": job_id,
            }

        log_event(
            logger,
            "Treatment classification complete for circuit split analysis",
            tool_name="find_circuit_splits",
            request_id=request_id,
            job_id=job_id,
            query_params={"citation": citation},
            extra_context={"valid_treatments": len(treatments)},
            event="find_circuit_splits_classification_complete",
        )

        # Step 4: Analyze for circuit splits
        analyzer = CircuitAnalyzer(
            min_cases_per_circuit=min_cases_per_circuit,
            split_threshold=split_threshold,
        )

        split, circuits_analyzed = analyzer.detect_circuit_split(
            citation, case_name, valid_cases, treatments
        )

        if not split:
            return {
                "citation": citation,
                "case_name": case_name,
                "split_detected": False,
                "message": f"No circuit split detected across {circuits_analyzed} circuit(s)",
                "total_citing_cases": len(citing_cases),
                "circuits_analyzed": circuits_analyzed,
                "job_id": job_id,
            }

        # Step 5: Format split results
        log_event(
            logger,
            f"Circuit split detected: {split.split_type}",
            tool_name="find_circuit_splits",
            request_id=request_id,
            job_id=job_id,
            query_params={"citation": citation},
            extra_context={
                "split_type": split.split_type,
                "circuits_involved": len(split.circuits_involved),
                "confidence": split.confidence,
            },
            event="find_circuit_splits_split_detected",
        )

        # Build circuit details
        circuit_details = []
        for circuit_id, treatment_data in split.conflicting_circuits.items():
            circuit_details.append(
                {
                    "circuit_id": circuit_id,
                    "circuit_name": treatment_data.circuit_name,
                    "total_cases": treatment_data.total_cases,
                    "positive_count": treatment_data.positive_count,
                    "negative_count": treatment_data.negative_count,
                    "neutral_count": treatment_data.neutral_count,
                    "dominant_treatment": treatment_data.dominant_treatment.value,
                    "average_confidence": round(treatment_data.average_confidence, 2),
                }
            )

        return {
            "citation": citation,
            "case_name": case_name,
            "split_detected": True,
            "split_type": split.split_type,
            "confidence": split.confidence,
            "summary": split.summary,
            "circuits_involved": split.circuits_involved,
            "circuit_details": circuit_details,
            "key_cases": split.key_cases,
            "supreme_court_likely": split.supreme_court_likely,
            "total_citing_cases": len(citing_cases),
            "job_id": job_id,
            "recommendation": (
                "STRONG SPLIT: Supreme Court review likely"
                if split.supreme_court_likely
                else (
                    "Emerging split: Monitor for development"
                    if split.split_type == "emerging_split"
                    else "Potential split: Requires further analysis"
                )
            ),
        }


@jurisdiction_server.tool()
@tool_logging("find_circuit_splits")
async def find_circuit_splits(
    citation: str,
    min_cases_per_circuit: int = 2,
    split_threshold: float = DEFAULT_SPLIT_THRESHOLD,
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Detect if different federal circuits disagree on treatment of a case.

    This tool analyzes citing cases grouped by federal circuit court to identify
    "circuit splits" - situations where different circuits treat the same precedent
    in conflicting ways. Circuit splits are prime candidates for Supreme Court review.

    Args:
        citation: The citation to analyze (e.g., "410 U.S. 113" or "Roe v. Wade")
        min_cases_per_circuit: Minimum citing cases needed per circuit to consider it
            (default: 2). Lower values may detect more splits but with less confidence.
        split_threshold: Threshold for determining dominant treatment (default: 0.6)
        request_id: Optional request ID for logging
        job_id: Optional job ID for tracking

    Returns:
        Dictionary containing:
        - split_detected: Boolean indicating if a split was found
        - split_type: Type of split ("direct_conflict", "emerging_split", "potential_split")
        - confidence: Confidence score (0-1)
        - summary: Human-readable summary of the split
        - circuits_involved: List of circuit IDs involved in the split
        - circuit_details: Detailed breakdown of treatment by circuit
        - key_cases: Representative cases from each circuit
        - supreme_court_likely: Boolean indicating if Supreme Court review is likely
        - recommendation: Guidance on the significance of the split

    Example - Direct Conflict:
        >>> await find_circuit_splits("Miranda v. Arizona")
        {
            "split_detected": True,
            "split_type": "direct_conflict",
            "confidence": 0.85,
            "summary": "Direct Conflict: Ninth Circuit (5+ / 1-): positive; Fifth Circuit (1+ / 4-): negative",
            "circuits_involved": ["ca9", "ca5"],
            "supreme_court_likely": True,
            "recommendation": "STRONG SPLIT: Supreme Court review likely"
        }

    Example - No Split:
        >>> await find_circuit_splits("United States v. Jones")
        {
            "split_detected": False,
            "message": "No circuit split detected across 6 circuit(s)",
            "circuits_analyzed": 6
        }

    Use Cases:
        - Identify cases ripe for Supreme Court review
        - Assess predictability of case outcome across jurisdictions
        - Research forum shopping opportunities (where permissible)
        - Track evolution of legal doctrine across circuits
    """
    return await find_circuit_splits_impl(
        citation,
        min_cases_per_circuit,
        split_threshold=split_threshold,
        request_id=request_id,
        job_id=job_id,
    )
