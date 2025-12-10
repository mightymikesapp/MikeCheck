"""Document processing and citation extraction tools."""

import io
import logging
import re

from pypdf import PdfReader

logger = logging.getLogger(__name__)

EXCLUDED_TERMS = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "section", "sec", "id", "at", "and", "or", "the", "see", "cf"
}

def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF content."""
    try:
        reader = PdfReader(io.BytesIO(content))
        text_parts: list[str] = []
        for page in reader.pages:
            text_parts.append((page.extract_text() or ""))
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return ""

def extract_citations(text: str) -> list[str]:
    """Extract legal citations from text using regex."""
    pattern = r"(\d+)\s+([A-Za-z\d\.\s]+?)\s+(\d+)"

    matches = re.finditer(pattern, text)
    citations = []

    for match in matches:
        volume = match.group(1)
        reporter = match.group(2).strip()
        page = match.group(3)

        if len(reporter) < 2:
            continue
        if reporter.lower() in EXCLUDED_TERMS:
            continue
        if reporter.isdigit():
            continue
        if len(reporter) == 4 and reporter.isdigit():
            continue

        citation = f"{volume} {reporter} {page}"
        citations.append(citation)

    return list(set(citations))
