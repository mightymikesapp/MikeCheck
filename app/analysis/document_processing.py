"""Document processing and citation extraction tools."""

import io
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from pypdf import PdfReader

logger = logging.getLogger(__name__)


@dataclass
class ParsedDocument:
    """Represents a parsed legal document with body and footnotes separated."""

    body_text: str
    footnote_text: str
    footnotes: dict[str, str]  # footnote number -> footnote content


class FootnoteParser(HTMLParser):
    """Parse HTML legal opinions to separate body text from footnotes.

    CourtListener's html_lawbox format preserves structural distinction between
    main body text (in <p> tags) and footnotes (in <fn> or <div> tags with
    specific classes). This parser extracts both separately for more accurate
    treatment analysis.
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        super().__init__()
        self.body_parts: list[str] = []
        self.footnote_parts: list[str] = []
        self.footnotes: dict[str, str] = {}
        self.current_tag: str | None = None
        self.current_footnote_num: str | None = None
        self.in_footnote = False
        self.in_body = False
        self.footnote_div_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening HTML tags."""
        self.current_tag = tag

        # Check for footnote tags
        if tag == "fn":
            self.in_footnote = True
            # Try to extract footnote number from attributes
            for attr_name, attr_value in attrs:
                if attr_name == "num" and attr_value:
                    self.current_footnote_num = attr_value
        elif tag == "div":
            # Check for footnote-related classes
            starts_footnote_div = False
            for attr_name, attr_value in attrs:
                if attr_name == "class" and attr_value:
                    if "footnote" in attr_value.lower() or "fn" in attr_value.lower():
                        starts_footnote_div = True
            if starts_footnote_div:
                self.in_footnote = True
                self.footnote_div_depth = 1
            elif self.in_footnote and self.footnote_div_depth > 0:
            is_footnote_div = False
            for attr_name, attr_value in attrs:
                if attr_name == "class" and attr_value:
                    if "footnote" in attr_value.lower() or "fn" in attr_value.lower():
                        self.in_footnote = True
                        self.footnote_div_depth = 1
                        is_footnote_div = True
            if self.in_footnote and self.footnote_div_depth > 0 and not is_footnote_div:
                self.footnote_div_depth += 1
        elif tag == "p":
            if not self.in_footnote:
                self.in_body = True

    def handle_endtag(self, tag: str) -> None:
        """Handle closing HTML tags."""
        if tag == "fn":
            self.in_footnote = False
            self.current_footnote_num = None
            self.footnote_div_depth = 0
        elif tag == "div" and self.footnote_div_depth > 0:
            self.footnote_div_depth -= 1
            if self.footnote_div_depth == 0:
                self.in_footnote = False
                self.current_footnote_num = None
        elif tag == "p" and self.in_body:
            self.in_body = False
        self.current_tag = None

    def handle_data(self, data: str) -> None:
        """Handle text data within tags."""
        data = data.strip()
        if not data:
            return

        if self.in_footnote:
            self.footnote_parts.append(data)
            if self.current_footnote_num:
                if self.current_footnote_num in self.footnotes:
                    self.footnotes[self.current_footnote_num] += " " + data
                else:
                    self.footnotes[self.current_footnote_num] = data
        elif self.in_body or self.current_tag == "p":
            self.body_parts.append(data)

    def get_parsed_document(self) -> ParsedDocument:
        """Get the parsed document with separated body and footnotes."""
        return ParsedDocument(
            body_text=" ".join(self.body_parts),
            footnote_text=" ".join(self.footnote_parts),
            footnotes=self.footnotes,
        )

    @staticmethod
    def parse_html(html: str) -> ParsedDocument:
        """Parse HTML and return separated body and footnote text.

        Args:
            html: HTML content from html_lawbox field

        Returns:
            ParsedDocument with separated body and footnote text
        """
        parser = FootnoteParser()
        parser.feed(html)
        return parser.get_parsed_document()

    @staticmethod
    def parse_plain_text_fallback(text: str) -> ParsedDocument:
        """Fallback parser for plain text using regex heuristics.

        This is used when html_lawbox is not available. It looks for common
        footnote patterns:
        - Lines starting with digits followed by a period (e.g., "1. ", "2. ")
        - Patterns like "n. 14" or "FN 3"

        Args:
            text: Plain text content

        Returns:
            ParsedDocument with heuristically separated body and footnotes
        """
        lines = text.split("\n")
        body_lines: list[str] = []
        footnote_lines: list[str] = []
        footnotes: dict[str, str] = {}

        # Track if we've entered a footnote section (typically at end of document)
        in_footnote_section = False
        current_footnote_num: str | None = None

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Check if this line starts a footnote
            # Pattern 1: Line starts with digit(s) followed by period and space
            footnote_start = re.match(r"^(\d+)\.\s+(.+)$", line_stripped)
            if footnote_start and i >= len(lines) * 0.6:  # Likely in footnote section
            if footnote_start and (in_footnote_section or i > len(lines) * 0.5):
                in_footnote_section = True
                current_footnote_num = footnote_start.group(1)
                footnote_content = footnote_start.group(2)
                footnotes[current_footnote_num] = footnote_content
                footnote_lines.append(line_stripped)
                continue

            # Pattern 2: Check for inline footnote references like "n. 14" or "FN3"
            has_footnote_ref = bool(
                re.search(r"\b(?:n\.|fn|note)\s*\d+\b", line_stripped, re.IGNORECASE)
            )

            if has_footnote_ref and not footnote_start:
                current_footnote_num = None

            if in_footnote_section or has_footnote_ref:
                footnote_lines.append(line_stripped)
                if current_footnote_num and in_footnote_section and not has_footnote_ref:
                    # Continue adding to current footnote
                    footnotes[current_footnote_num] += " " + line_stripped
            else:
                body_lines.append(line_stripped)

        return ParsedDocument(
            body_text=" ".join(body_lines),
            footnote_text=" ".join(footnote_lines),
            footnotes=footnotes,
        )


EXCLUDED_TERMS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "section",
    "sec",
    "id",
    "at",
    "and",
    "or",
    "the",
    "see",
    "cf",
}


def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF content.

    Args:
        content: Raw bytes of the PDF file.

    Returns:
        Extracted text as a string.
    """
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
    """Extract legal citations from text using regex.

    Args:
        text: Input text to scan.

    Returns:
        List of unique extracted citations (normalized).
    """
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
