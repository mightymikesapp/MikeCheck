"""Standardized error payload helpers."""

from collections.abc import Sequence

JOB_TOO_LARGE_SUGGESTIONS: Sequence[str] = (
    "Split the request by chapter or section to keep batches manageable.",
    "Reduce the citation network depth or node limit to keep the job within limits.",
)


def job_too_large_error() -> dict[str, object]:
    """Create a standardized payload for oversized requests."""

    return {"error": "JOB_TOO_LARGE", "suggestions": list(JOB_TOO_LARGE_SUGGESTIONS)}
