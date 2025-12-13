"""Quote verification and matching for legal citations.

This module provides tools for verifying that quotes accurately appear in cited
cases, essential for maintaining academic integrity in legal scholarship.
"""

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class QuoteMatch:
    """A match found for a quote in source text."""

    found: bool
    exact_match: bool
    similarity: float  # 0-1 score
    position: int  # Character position in source
    matched_text: str  # What was actually found
    context_before: str  # Text before the quote
    context_after: str  # Text after the quote
    differences: list[str]  # List of differences if not exact


@dataclass
class QuoteVerificationResult:
    """Result of verifying a quote against a source."""

    quote: str
    citation: str
    found: bool
    exact_match: bool
    similarity: float
    matches: list[QuoteMatch]
    warnings: list[str]
    recommendation: str


class QuoteMatcher:
    """Matcher for verifying legal quotes against source text."""

    STOPWORDS = {
        "the", "of", "and", "a", "to", "in", "is", "you", "that", "it", "he", "was",
        "for", "on", "are", "as", "with", "his", "they", "i", "at", "be", "this",
        "have", "from", "or", "one", "had", "by", "word", "but", "not", "what",
        "all", "were", "we", "when", "your", "can", "said", "there", "use", "an",
        "each", "which", "she", "do", "how", "their", "if", "will", "up", "other",
        "about", "out", "many", "then", "them", "these", "so", "some", "her", "over",
        "would", "make", "like", "him", "into", "time", "has", "look", "two",
        "more", "write", "go", "see", "number", "no", "way", "could", "people",
        "my", "than", "first", "water", "been", "call", "who", "oil", "its", "now",
        "find", "long", "down", "day", "did", "get", "come", "made", "may", "part"
    }

    def __init__(
        self,
        exact_match_threshold: float = 1.0,
        fuzzy_match_threshold: float = 0.85,
        context_chars: int = 200,
    ) -> None:
        """Initialize the quote matcher.

        Args:
            exact_match_threshold: Similarity threshold for exact match (1.0)
            fuzzy_match_threshold: Minimum similarity for fuzzy match (0.85)
            context_chars: Characters of context to include before/after quote
        """
        self.exact_threshold = exact_match_threshold
        self.fuzzy_threshold = fuzzy_match_threshold
        self.context_chars = context_chars

    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison.

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        # Strip HTML tags if present
        text = re.sub(r"<[^>]+>", " ", text)
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove line breaks
        text = text.replace("\n", " ")
        # Remove smart quotes and replace with standard quotes
        text = text.replace(""", '"').replace(""", '"')
        text = text.replace("'", "'").replace("'", "'")
        # Strip leading/trailing whitespace
        text = text.strip()
        return text

    def normalize_for_fuzzy_match(self, text: str) -> str:
        """Normalize text for fuzzy matching (more aggressive).

        Args:
            text: Text to normalize

        Returns:
            Normalized text for fuzzy matching
        """
        text = self.normalize_text(text)
        # Case insensitive for fuzzy matching
        text = text.lower()
        # Remove punctuation variations
        text = re.sub(r'[""' "`]", '"', text)
        # Normalize ellipsis
        text = re.sub(r"\.{3,}|\.\s\.\s\.", "...", text)
        return text

    def _get_significant_words(self, text: str) -> list[str]:
        """Extract significant words (non-stopwords) from text.

        Args:
            text: Input text

        Returns:
            List of significant words
        """
        words = text.split()
        return [w for w in words if w not in self.STOPWORDS and len(w) > 2]

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score from 0 to 1
        """
        return SequenceMatcher(None, text1, text2).ratio()

    def find_quote_exact(self, quote: str, source: str) -> list[QuoteMatch]:
        """Find exact matches of quote in source text.

        Args:
            quote: Quote to search for
            source: Source text to search in

        Returns:
            List of exact matches found
        """
        matches = []

        # Normalize both texts but preserve source structure
        normalized_quote = self.normalize_text(quote)
        normalized_source = self.normalize_text(source)

        # Search for exact matches (case-sensitive)
        pattern = re.escape(normalized_quote)
        for match in re.finditer(pattern, normalized_source, re.IGNORECASE):
            position = match.start()

            # Extract context
            context_start = max(0, position - self.context_chars)
            context_end = min(len(normalized_source), match.end() + self.context_chars)

            context_before = normalized_source[context_start:position]
            context_after = normalized_source[match.end() : context_end]

            matches.append(
                QuoteMatch(
                    found=True,
                    exact_match=True,
                    similarity=1.0,
                    position=position,
                    matched_text=match.group(),
                    context_before=context_before,
                    context_after=context_after,
                    differences=[],
                )
            )

        return matches

    def find_quote_fuzzy(
        self,
        quote: str,
        source: str,
        max_matches: int = 5,
    ) -> list[QuoteMatch]:
        """Find fuzzy matches of quote in source text.

        Uses a two-phase "filter-then-verify" approach:
        1. Filter: Scan text using Jaccard index of significant words to find candidates.
        2. Verify: Apply detailed SequenceMatcher only to top candidates.

        Args:
            quote: Quote to search for
            source: Source text to search in
            max_matches: Maximum number of fuzzy matches to return

        Returns:
            List of fuzzy matches found, sorted by similarity
        """
        normalized_quote = self.normalize_for_fuzzy_match(quote)
        normalized_source = self.normalize_for_fuzzy_match(source)

        quote_len = len(normalized_quote)
        source_len = len(normalized_source)

        if quote_len > source_len:
            return []

        # Significant word analysis
        quote_words = self._get_significant_words(normalized_quote)
        if not quote_words:
            # Fallback to all words if no significant words found
            quote_words = normalized_quote.split()

        quote_word_set = set(quote_words)

        # Robust quick rejection: Check if significant words are present
        if len(quote_words) >= 3:
            # Check percentage of significant words present in source
            present_words = sum(1 for w in quote_word_set if w in normalized_source)
            coverage = present_words / len(quote_word_set)
            if coverage < 0.3: # At least 30% of unique significant words must be present
                 return []

        # --- Phase 1: Filter (Candidate Generation) ---
        candidates: list[tuple[float, int]] = [] # (score, position)

        # Use a sliding window roughly the size of the quote
        # Stride can be aggressive (half the quote length) since we just need to hit the region
        stride = max(1, quote_len // 2)
        window_size = quote_len

        # Tokenize source once for word-based filtering if needed,
        # but for simple Jaccard on the window text, we can just split the window string.
        # To make it faster, we'll scan character-based windows but process words inside.

        for start in range(0, source_len - window_size + 1, stride):
            end = start + window_size
            window_text = normalized_source[start:end]

            # Quick Jaccard Index estimate
            # Split is relatively cheap on small windows
            window_words = set(self._get_significant_words(window_text))

            if not window_words and not quote_word_set:
                continue

            intersection = len(quote_word_set.intersection(window_words))
            union = len(quote_word_set.union(window_words))

            jaccard_score = intersection / union if union > 0 else 0

            # Keep candidates with some overlap
            if jaccard_score > 0.1: # Low threshold to catch fuzzy matches
                candidates.append((jaccard_score, start))

        # Sort candidates by Jaccard score
        candidates.sort(reverse=True, key=lambda x: x[0])

        # Limit candidates to check fully
        top_candidates = candidates[:max(10, max_matches * 2)]

        # If no candidates found via Jaccard (e.g. very short quotes or no significant words),
        # we might need a fallback or just accept no match.
        # For very short quotes (no significant words), the logic above handles them via fallback to all words.

        # --- Phase 2: Verify (SequenceMatcher) ---
        matches: list[tuple[float, int, str]] = []  # (similarity, position, text)
        best_similarity_found = 0.0

        tolerance = int(quote_len * 0.2)  # Allow 20% size variation

        for _, start in top_candidates:
            # Optimization: Check exact window size first
            target_size = window_size
            end = start + target_size
            if end > source_len:
                end = source_len

            window = normalized_source[start:end]
            similarity = self.calculate_similarity(normalized_quote, window)

            best_local_match = (similarity, start, source[start:end])

            # Only expand/contract if promising
            if similarity > 0.5:
                # Try expanding/contracting
                # We search a range around the target size
                min_size = max(target_size - tolerance, 1)
                max_size = min(target_size + tolerance, source_len - start)

                # Check bounds to avoid redundant work if tolerance is small
                if min_size < target_size or max_size > target_size:
                    for size in range(min_size, max_size + 1):
                        if size == target_size:
                            continue

                        end = start + size
                        window = normalized_source[start:end]
                        sim = self.calculate_similarity(normalized_quote, window)

                        if sim > best_local_match[0]:
                            best_local_match = (sim, start, source[start:end])

            if best_local_match[0] >= self.fuzzy_threshold:
                matches.append(best_local_match)
                if best_local_match[0] > best_similarity_found:
                    best_similarity_found = best_local_match[0]

            # Early exit if perfect match
            if best_similarity_found >= 0.98:
                break

        # Sort by similarity (descending) and remove duplicates
        matches.sort(reverse=True, key=lambda x: x[0])
        unique_matches: list[QuoteMatch] = []
        seen_positions: set[int] = set()

        for similarity, position, matched_text in matches[:max_matches]:
            # Skip if too close to a previous match
            if any(abs(position - seen_pos) < quote_len // 2 for seen_pos in seen_positions):
                continue

            seen_positions.add(position)

            # Extract context
            context_start = max(0, position - self.context_chars)
            context_end = min(len(source), position + len(matched_text) + self.context_chars)

            context_before = source[context_start:position]
            context_after = source[position + len(matched_text) : context_end]

            # Find differences
            differences = self._find_differences(quote, matched_text)

            unique_matches.append(
                QuoteMatch(
                    found=True,
                    exact_match=False,
                    similarity=similarity,
                    position=position,
                    matched_text=matched_text,
                    context_before=context_before,
                    context_after=context_after,
                    differences=differences,
                )
            )

        return unique_matches

    def _find_differences(self, expected: str, actual: str) -> list[str]:
        """Find specific differences between expected and actual text.

        Args:
            expected: Expected text (quote)
            actual: Actual text found

        Returns:
            List of difference descriptions
        """
        differences = []

        # Normalize for comparison
        norm_expected = self.normalize_text(expected)
        norm_actual = self.normalize_text(actual)

        # Check length difference
        len_diff = abs(len(norm_expected) - len(norm_actual))
        if len_diff > 0:
            differences.append(f"Length differs by {len_diff} characters")

        # Check word count
        expected_words = norm_expected.split()
        actual_words = norm_actual.split()
        word_diff = abs(len(expected_words) - len(actual_words))
        if word_diff > 0:
            differences.append(f"Word count differs by {word_diff} words")

        # Find mismatched words
        matcher = SequenceMatcher(None, expected_words, actual_words)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                differences.append(
                    f"Words differ: '{' '.join(expected_words[i1:i2])}' vs '{' '.join(actual_words[j1:j2])}'"
                )
            elif tag == "delete":
                differences.append(f"Missing words: '{' '.join(expected_words[i1:i2])}'")
            elif tag == "insert":
                differences.append(f"Extra words: '{' '.join(actual_words[j1:j2])}'")

        return differences[:5]  # Limit to 5 most significant differences

    def verify_quote(
        self,
        quote: str,
        source: str,
        citation: str,
    ) -> QuoteVerificationResult:
        """Verify a quote against source text.

        Args:
            quote: The quote to verify
            source: The source text to check against
            citation: The citation being verified

        Returns:
            QuoteVerificationResult with detailed findings
        """
        logger.info(f"Verifying quote ({len(quote)} chars) against source ({len(source)} chars)")

        if not quote or not quote.strip():
            return QuoteVerificationResult(
                quote=quote,
                citation=citation,
                found=False,
                exact_match=False,
                similarity=0.0,
                matches=[],
                warnings=["Quote is empty"],
                recommendation="Please provide a valid quote to verify",
            )

        # First try exact match
        exact_matches = self.find_quote_exact(quote, source)

        if exact_matches:
            logger.info(f"Found {len(exact_matches)} exact match(es)")
            return QuoteVerificationResult(
                quote=quote,
                citation=citation,
                found=True,
                exact_match=True,
                similarity=1.0,
                matches=exact_matches,
                warnings=[],
                recommendation="Quote verified exactly in source",
            )

        # If no exact match, try fuzzy matching
        logger.info("No exact match, attempting fuzzy match...")
        fuzzy_matches = self.find_quote_fuzzy(quote, source)

        if fuzzy_matches:
            best_match = fuzzy_matches[0]
            logger.info(
                f"Found {len(fuzzy_matches)} fuzzy match(es), "
                f"best similarity: {best_match.similarity:.2%}"
            )

            warnings = []
            if best_match.similarity < 0.95:
                warnings.append("Quote differs from source text")
            if best_match.differences:
                warnings.append(f"Differences found: {len(best_match.differences)}")

            recommendation = (
                "Quote found with minor differences - review recommended"
                if best_match.similarity >= 0.95
                else "Quote significantly differs from source - verify carefully"
            )

            return QuoteVerificationResult(
                quote=quote,
                citation=citation,
                found=True,
                exact_match=False,
                similarity=best_match.similarity,
                matches=fuzzy_matches,
                warnings=warnings,
                recommendation=recommendation,
            )

        # No matches found
        logger.warning("No matches found for quote")
        return QuoteVerificationResult(
            quote=quote,
            citation=citation,
            found=False,
            exact_match=False,
            similarity=0.0,
            matches=[],
            warnings=["Quote not found in source text"],
            recommendation="Quote could not be verified - check citation and text",
        )
