"""Issue discovery for legal citations.

This module provides heuristics to automatically label the legal issue
associated with a citation based on its context in the citing opinion.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Common section headers in legal opinions
SECTION_HEADER_PATTERNS = [
    # Roman Numerals: I. Standing, II. Analysis
    r"^[IVX]+\.\s+([A-Z][a-zA-Z0-9\s\-,]+)$",
    # Letters: A. Background, B. Merits
    r"^[A-Z]\.\s+([A-Z][a-zA-Z0-9\s\-,]+)$",
    # Standard words
    r"^(INTRODUCTION|BACKGROUND|DISCUSSION|ANALYSIS|CONCLUSION|ARGUMENT)$",
    # Numbered: 1. Jurisdiction
    r"^\d+\.\s+([A-Z][a-zA-Z0-9\s\-,]+)$",
]


class IssueDiscoverer:
    """Discoverer for legal issues in text."""

    def discover_issue(self, text: str, citation: str) -> dict[str, str]:
        """Discover the issue label for a citation based on context.

        Args:
            text: The text containing the citation (snippet or full text).
            citation: The citation string.

        Returns:
            Dictionary with 'label' and 'source'.
        """

        # 1. Try to find a section header preceding the citation
        header = self._find_nearest_header(text, citation)
        if header:
            return {"label": header, "source": "auto_discovered_header"}

        # 2. Try to find key phrase in the same sentence
        phrase = self._extract_key_phrase(text, citation)
        if phrase:
            return {"label": phrase, "source": "auto_discovered_keyword"}

        return {"label": "General Application", "source": "fallback"}

    def _find_nearest_header(self, text: str, citation: str) -> str | None:
        """Find the nearest section header appearing before the citation."""

        # Find citation position
        try:
            # Simple find, ignoring case variations for robustness
            idx = text.lower().find(citation.lower())
            if idx == -1:
                # Try normalized spacing
                cite_regex = re.escape(citation).replace(r"\ ", r"\s+")
                match = re.search(cite_regex, text, re.IGNORECASE)
                if match:
                    idx = match.start()
                else:
                    return None
        except Exception:
            return None

        # Look at text before citation
        preceding_text = text[:idx]
        lines = preceding_text.splitlines()

        # Traverse lines backwards
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            # Check against patterns
            for pattern in SECTION_HEADER_PATTERNS:
                match = re.match(pattern, line)
                if match:
                    # If pattern has groups, use the first group (the title)
                    # If no groups (like DISCUSSION), use the whole match
                    if match.groups():
                        return match.group(1).title()
                    return match.group(0).title()

            # Heuristic for implicit headers: Short, all caps or title case, distinct line
            if len(line) < 50 and (line.isupper() or line.istitle()) and not line.endswith("."):
                # Avoid common false positives
                if line.lower() not in ["it is so ordered", "affirmed", "reversed"]:
                    return line.title()

        return None

    def _extract_key_phrase(self, text: str, citation: str) -> str | None:
        """Extract a likely topic keyword from the context."""
        # This is harder. We look for "regarding X", "issue of X".

        # Find context around citation
        cite_regex = re.escape(citation).replace(r"\ ", r"\s+")
        match = re.search(cite_regex, text, re.IGNORECASE)
        if not match:
            return None

        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context = text[start:end]

        patterns = [
            r"issue\s+of\s+([a-zA-Z\s]+)",
            r"regarding\s+([a-zA-Z\s]+)",
            r"concerning\s+([a-zA-Z\s]+)",
            r"related\s+to\s+([a-zA-Z\s]+)",
        ]

        for pat in patterns:
            m = re.search(pat, context, re.IGNORECASE)
            if m:
                phrase = m.group(1).strip()
                # Limit length
                if len(phrase) < 40:
                    return phrase.title()

        return None
