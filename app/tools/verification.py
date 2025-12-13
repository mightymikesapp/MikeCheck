"""Quote verification tools for legal research.

This module provides MCP tools for verifying quotes against their cited sources,
essential for maintaining academic integrity in legal scholarship.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, cast

from fastmcp import FastMCP

from app.analysis.quote_matcher import QuoteMatcher
from app.config import settings
from app.errors import job_too_large_error
from app.logging_config import tool_logging
from app.logging_utils import log_event, log_operation
from app.mcp_client import get_client
from app.mcp_types import ToolPayload
from app.types import QuoteGrounding, QuoteVerificationResult

logger = logging.getLogger(__name__)

# Initialize quote matcher
matcher = QuoteMatcher(
    exact_match_threshold=1.0,
    fuzzy_match_threshold=0.85,
    context_chars=200,
)


@dataclass
class PinpointSlice:
    text: str
    start_offset: int
    end_offset: int
    method: str
    target_value: int | None = None
    label: str | None = None
    error: str | None = None
    error_code: str | None = None


def _parse_pinpoint_number(pinpoint: str) -> int | None:
    """Extract a numeric pinpoint value if present."""

    matches = re.findall(r"\d+", pinpoint)
    if not matches:
        return None
    try:
        return int(matches[0])
    except ValueError:
        return None


def _extract_pinpoint_slice(full_text: str, pinpoint: str) -> PinpointSlice:
    """Try to isolate the portion of text most relevant to a pinpoint."""

    target_number = _parse_pinpoint_number(pinpoint)
    if target_number is None:
        return PinpointSlice(
            text=full_text,
            start_offset=0,
            end_offset=len(full_text),
            method="full_text",
            error="Could not parse numeric pinpoint value",
            error_code="PINPOINT_UNPARSABLE",
        )

    # Page/section markers heuristic
    patterns = [
        rf"Page\s+{target_number}\b",
        rf"Pg\.\s*{target_number}\b",
        rf"P\.\s*{target_number}\b",
        rf"\[{target_number}\]",
        rf"\({target_number}\)",
        rf"§\s*{target_number}\b",
        rf"¶\s*{target_number}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text, flags=re.IGNORECASE)
        if match:
            start = max(0, match.start() - 2000)
            end = min(len(full_text), match.end() + 2000)
            return PinpointSlice(
                text=full_text[start:end],
                start_offset=start,
                end_offset=end,
                method="page_marker",
                target_value=target_number,
                label=f"Around marker '{pattern}'",
            )

    # Paragraph index heuristic (1-indexed)
    paragraphs = re.split(r"\n\s*\n+", full_text)
    if 1 <= target_number <= len(paragraphs):
        start = 0
        for para in paragraphs[: target_number - 1]:
            start += len(para) + 2  # account for removed newlines
        para_text = paragraphs[target_number - 1]
        end = start + len(para_text)
        window_start = max(0, start - 500)
        window_end = min(len(full_text), end + 500)
        return PinpointSlice(
            text=full_text[window_start:window_end],
            start_offset=window_start,
            end_offset=window_end,
            method="paragraph_index",
            target_value=target_number,
            label=f"Paragraph {target_number}",
        )

    return PinpointSlice(
        text=full_text,
        start_offset=0,
        end_offset=len(full_text),
        method="full_text",
        target_value=target_number,
        error="Pinpoint marker not located in text",
        error_code="PINPOINT_NOT_FOUND",
    )


# Implementation functions
async def verify_quote_impl(
    quote: str,
    citation: str,
    pinpoint: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
) -> QuoteVerificationResult:
    """Verify a quote appears in the cited source.

    Args:
        quote: The quote to verify
        citation: The citation (e.g., "410 U.S. 113")
        pinpoint: Optional pinpoint citation (e.g., "at 153")

    Returns:
        Dictionary with verification results
    """
    client = get_client()

    with log_operation(
        logger,
        tool_name="verify_quote",
        request_id=request_id,
        job_id=job_id,
        query_params={"citation": citation, "pinpoint": pinpoint},
        event="verify_quote",
    ):
        # Step 1: Look up the case
        target_case = await client.lookup_citation(citation, request_id=request_id)

        if "error" in target_case:
            return {
                "error": f"Could not find case: {target_case.get('error')}",
                "error_code": "CASE_NOT_FOUND",
                "citation": citation,
                "quote": quote,
                "job_id": job_id,
            }

        case_name = target_case.get("caseName", "Unknown")
        log_event(
            logger,
            "Case located for quote verification",
            tool_name="verify_quote",
            request_id=request_id,
            job_id=job_id,
            query_params={"citation": citation, "pinpoint": pinpoint},
            event="verify_quote_case",
        )

        # Step 2: Get full text of the opinion
        # Extract opinion IDs
        opinion_ids = [op.get("id") for op in target_case.get("opinions", []) if op.get("id")]

        if not opinion_ids:
            return {
                "error": "No opinion text available for this case",
                "error_code": "NO_OPINION_TEXT",
                "citation": citation,
                "case_name": case_name,
                "quote": quote,
                "job_id": job_id,
            }

        opinion_id_raw = opinion_ids[0]
        if not isinstance(opinion_id_raw, int):
            return {
                "error": "Invalid opinion identifier",
                "error_code": "INVALID_OPINION_ID",
                "citation": citation,
                "case_name": case_name,
                "quote": quote,
                "job_id": job_id,
            }

        full_text = await client.get_opinion_full_text(
            opinion_id_raw, request_id=request_id
        )

        if not full_text:
            return {
                "error": "Could not retrieve opinion text",
                "error_code": "TEXT_RETRIEVAL_FAILED",
                "citation": citation,
                "case_name": case_name,
                "quote": quote,
                "job_id": job_id,
            }

        log_event(
            logger,
            "Opinion text retrieved for quote verification",
            tool_name="verify_quote",
            request_id=request_id,
            job_id=job_id,
            query_params={"citation": citation, "pinpoint": pinpoint},
            citation_count=len(full_text),
            event="verify_quote_text",
        )

        # Step 3: Narrow to pinpoint slice if provided
        pinpoint_slice: PinpointSlice | None = None
        if pinpoint:
            pinpoint_slice = _extract_pinpoint_slice(full_text, pinpoint)
            search_text = pinpoint_slice.text if pinpoint_slice else full_text
        else:
            search_text = full_text

        # Verify the quote within the targeted slice first
        result = matcher.verify_quote(quote, search_text, citation)
        match_offset = 0 if not pinpoint_slice else pinpoint_slice.start_offset

        # If slice search failed but pinpoint was provided, fall back to full text
        slice_miss = pinpoint and pinpoint_slice and not result.found
        if slice_miss:
            fallback_result = matcher.verify_quote(quote, full_text, citation)
            if fallback_result.found:
                result = fallback_result
                match_offset = 0

        # Step 4: Build response
        response: QuoteVerificationResult = {
            "citation": citation,
            "case_name": case_name,
            "quote": quote,
            "found": result.found,
            "exact_match": result.exact_match,
            "similarity": round(result.similarity, 3) if result.similarity else 0.0,
            "matches_found": len(result.matches),
            "warnings": result.warnings,
            "recommendation": result.recommendation,
        }

        mismatch_reasons: list[str] = []

        section_hint: dict[str, object] | None = None
        if pinpoint and pinpoint_slice:
            section_hint = {
                "pinpoint": pinpoint,
                "method": pinpoint_slice.method,
                "target_value": pinpoint_slice.target_value,
                "slice_span": {
                    "start": pinpoint_slice.start_offset,
                    "end": pinpoint_slice.end_offset,
                },
                "label": pinpoint_slice.label,
                "error": pinpoint_slice.error,
                "error_code": pinpoint_slice.error_code,
            }
            if slice_miss:
                mismatch_reasons.append(
                    "Quote not located in pinpoint slice; matched using full opinion text"
                )

        # Add match details
        if result.matches:
            best_match = result.matches[0]
            absolute_start = match_offset + best_match.position
            absolute_end = absolute_start + len(best_match.matched_text)
            response["best_match"] = {
                "position": absolute_start,
                "matched_text": best_match.matched_text[:200] + "..."
                if len(best_match.matched_text) > 200
                else best_match.matched_text,
                "context_before": best_match.context_before[-100:]
                if len(best_match.context_before) > 100
                else best_match.context_before,
                "context_after": best_match.context_after[:100]
                if len(best_match.context_after) > 100
                else best_match.context_after,
                "differences": best_match.differences if not best_match.exact_match else [],
            }

            # Include all match positions
            response["all_match_positions"] = [
                match_offset + match.position for match in result.matches
            ]

            grounding: QuoteGrounding = {
                "source_span": {"start": absolute_start, "end": absolute_end},
                "opinion_section_hint": section_hint,
                "alignment": {
                    "pinpoint_requested": bool(pinpoint),
                    "pinpoint_in_range": None,
                    "mismatch_reasons": mismatch_reasons,
                },
            }

            if pinpoint and section_hint:
                target_span = section_hint.get("slice_span")
                if (
                    isinstance(target_span, dict)
                    and isinstance(target_span.get("start"), int)
                    and isinstance(target_span.get("end"), int)
                ):
                    in_range = target_span["start"] <= absolute_start <= target_span["end"]
                    grounding["alignment"]["pinpoint_in_range"] = in_range
                    if not in_range:
                        mismatch_reasons.append(
                            "Best match falls outside pinpoint slice boundaries"
                        )

                error_hint = section_hint.get("error")
                if isinstance(error_hint, str):
                    mismatch_reasons.append(error_hint)

            grounding["alignment"]["mismatch_reasons"] = mismatch_reasons
            response["grounding"] = grounding
        elif section_hint:
            response["grounding"] = {
                "opinion_section_hint": section_hint,
                "alignment": {
                    "pinpoint_requested": bool(pinpoint),
                    "pinpoint_in_range": False,
                    "mismatch_reasons": mismatch_reasons
                    + ["Quote not found to anchor against pinpoint"],
                },
            }

        # Validate pinpoint if provided
        if pinpoint:
            response["pinpoint_provided"] = pinpoint
            response["pinpoint_note"] = (
                "Note: Pinpoint page validation not yet implemented - "
                "CourtListener does not provide page numbers in API responses"
            )

        return response


async def batch_verify_quotes_impl(
    quotes: list[dict[str, str]],
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Verify multiple quotes in batch.

    Args:
        quotes: List of dicts with keys: "quote", "citation", optional "pinpoint"

    Returns:
        Dictionary with batch verification results
    """
    import asyncio

    if len(quotes) > settings.max_quotes_per_batch:
        log_event(
            logger,
            "Quote verification batch exceeds configured limit",
            tool_name="batch_verify_quotes",
            request_id=request_id,
            query_params={"total_quotes": len(quotes)},
            extra_context={"max_allowed": settings.max_quotes_per_batch},
            event="job_too_large",
        )
        return job_too_large_error()

    with log_operation(
        logger,
        tool_name="batch_verify_quotes",
        request_id=request_id,
        job_id=job_id,
        query_params={"total_quotes": len(quotes)},
        event="batch_verify_quotes",
    ):
        # Helper to preserve index
        async def verify_with_index(index: int, q_data: dict[str, str]) -> tuple[int, dict[str, Any]]:
            quote = q_data.get("quote", "")
            citation = q_data.get("citation", "")
            pinpoint = q_data.get("pinpoint")

            if not quote or not citation:
                return index, {
                    "error": "Missing quote or citation",
                    "quote": quote,
                    "citation": citation,
                    "job_id": job_id,
                }

            try:
                result = cast(
                    dict[str, Any],
                    await verify_quote_impl(
                        quote,
                        citation,
                        pinpoint,
                        request_id=request_id,
                        job_id=job_id,
                    ),
                )
                return index, result
            except Exception as exc:  # noqa: BLE001
                return index, {
                    "error": f"Verification failed: {exc}",
                    "quote": quote,
                    "citation": citation,
                    "job_id": job_id,
                }

        # Build tasks for parallel execution
        tasks = []
        progress_interval = 10

        for i, quote_data in enumerate(quotes):
            log_event(
                logger,
                "Queuing quote for verification",
                tool_name="batch_verify_quotes",
                request_id=request_id,
                job_id=job_id,
                query_params={"index": i + 1, "citation": quote_data.get("citation")},
            )
            tasks.append(verify_with_index(i, quote_data))

        total_quotes = len(quotes)
        results_list: list[dict[str, Any] | None] = [None] * total_quotes

        for completed_index, future in enumerate(asyncio.as_completed(tasks), 1):
            index, result = await future
            results_list[index] = result

            if total_quotes >= progress_interval:
                if completed_index % progress_interval == 0 or completed_index == total_quotes:
                    log_event(
                        logger,
                        "Quote verification progress",
                        tool_name="batch_verify_quotes",
                        request_id=request_id,
                        job_id=job_id,
                        query_params={"completed": completed_index, "total": total_quotes},
                        event="batch_verify_quotes_progress",
                    )

        results = [result or {} for result in results_list]

        # Summary statistics
        total = len(results)
        verified = sum(1 for r in results if r.get("found"))
        exact = sum(1 for r in results if r.get("exact_match"))
        errors = sum(1 for r in results if "error" in r)

        log_event(
            logger,
            "Batch verification complete",
            tool_name="batch_verify_quotes",
            request_id=request_id,
            job_id=job_id,
            query_params={"total_quotes": len(quotes)},
            citation_count=verified,
            event="batch_verify_quotes_complete",
        )

        return {
            "job_id": job_id,
            "total_quotes": total,
            "verified": verified,
            "exact_matches": exact,
            "fuzzy_matches": verified - exact,
            "not_found": total - verified - errors,
            "errors": errors,
            "results": results,
        }


# Create verification tools server
verification_server: FastMCP[ToolPayload] = FastMCP(
    name="Quote Verification Tools",
    instructions="Tools for verifying legal quotes against their cited sources",
)


@verification_server.tool()
@tool_logging("verify_quote")
async def verify_quote(
    quote: str,
    citation: str,
    pinpoint: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
) -> QuoteVerificationResult:
    """Verify that a quote accurately appears in the cited case.

    This tool fetches the full text of a cited case and verifies that a quote
    appears exactly (or approximately) as stated. Essential for maintaining
    academic integrity in legal scholarship.

    Args:
        quote: The quote to verify (e.g., "Congress shall make no law...")
        citation: The citation (e.g., "410 U.S. 113" or "Roe v. Wade")
        pinpoint: Optional pinpoint citation (e.g., "at 153")

    Returns:
        Dictionary containing:
        - found: Boolean indicating if quote was found
        - exact_match: Boolean indicating if quote matched exactly
        - similarity: Float 0-1 similarity score (1.0 = exact)
        - matches_found: Number of matches found
        - best_match: Details of the best match including context
        - warnings: List of any issues found
        - recommendation: Guidance on quote validity

    Example:
        >>> await verify_quote(
        ...     "The right of privacy is fundamental",
        ...     "410 U.S. 113"
        ... )
        {
            "found": True,
            "exact_match": True,
            "similarity": 1.0,
            "best_match": {
                "context_before": "...Court has held that...",
                "matched_text": "The right of privacy is fundamental",
                "context_after": "...and applies to..."
            }
        }
    """
    return await verify_quote_impl(quote, citation, pinpoint, request_id=request_id, job_id=job_id)


@verification_server.tool()
@tool_logging("batch_verify_quotes")
async def batch_verify_quotes(
    quotes: list[dict[str, str]],
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Verify multiple quotes in a single batch operation.

    Useful for validating all citations in a law review article or brief.

    Args:
        quotes: List of quote dictionaries, each containing:
            - quote: The quote text
            - citation: The citation
            - pinpoint: Optional pinpoint (e.g., "at 153")

    Returns:
        Dictionary containing:
        - total_quotes: Total number of quotes processed
        - verified: Number of quotes found
        - exact_matches: Number of exact matches
        - fuzzy_matches: Number of approximate matches
        - not_found: Number of quotes not found
        - errors: Number of errors encountered
        - results: List of individual verification results

    Example:
        >>> await batch_verify_quotes([
        ...     {"quote": "Equal protection...", "citation": "347 U.S. 483"},
        ...     {"quote": "Congress shall...", "citation": "410 U.S. 113"}
        ... ])
        {
            "total_quotes": 2,
            "verified": 2,
            "exact_matches": 2,
            "results": [...]
        }
    """
    return await batch_verify_quotes_impl(quotes, request_id=request_id, job_id=job_id)
