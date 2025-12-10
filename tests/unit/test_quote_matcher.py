"""Unit tests for QuoteMatcher class."""

import pytest

from app.analysis.quote_matcher import QuoteMatcher, QuoteMatch, QuoteVerificationResult


@pytest.fixture
def matcher():
    """Create a QuoteMatcher instance with default settings."""
    return QuoteMatcher(
        exact_match_threshold=1.0,
        fuzzy_match_threshold=0.85,
        context_chars=200,
    )


@pytest.fixture
def sample_source_text():
    """Sample legal text for testing."""
    return """
    The Supreme Court has long recognized that the Constitution protects
    the right to privacy. In Griswold v. Connecticut, we held that this
    right extends to marital relations. The right to privacy is broad enough
    to encompass a woman's decision whether or not to terminate her pregnancy.
    This is a fundamental right protected by the Due Process Clause.
    """


# Test initialization
@pytest.mark.unit
def test_quote_matcher_initialization():
    """Test QuoteMatcher initializes with correct thresholds."""
    matcher = QuoteMatcher(
        exact_match_threshold=1.0,
        fuzzy_match_threshold=0.90,
        context_chars=150,
    )

    assert matcher.exact_threshold == 1.0
    assert matcher.fuzzy_threshold == 0.90
    assert matcher.context_chars == 150


# Test normalize_text
@pytest.mark.unit
def test_normalize_text_removes_html(matcher):
    """Test that HTML tags are removed during normalization."""
    text = "<p>This is <strong>important</strong> text</p>"
    result = matcher.normalize_text(text)

    assert "<p>" not in result
    assert "<strong>" not in result
    assert "This is" in result
    assert "important" in result


@pytest.mark.unit
def test_normalize_text_removes_excess_whitespace(matcher):
    """Test that excessive whitespace is collapsed."""
    text = "This   has    too     many      spaces"
    result = matcher.normalize_text(text)

    assert result == "This has too many spaces"


@pytest.mark.unit
def test_normalize_text_removes_line_breaks(matcher):
    """Test that line breaks are replaced with spaces."""
    text = "Line one\nLine two\nLine three"
    result = matcher.normalize_text(text)

    assert "\n" not in result
    assert "Line one Line two Line three" == result


@pytest.mark.unit
def test_normalize_text_preserves_content(matcher):
    """Test that normalization preserves text content."""
    text = "This is a quote with content"
    result = matcher.normalize_text(text)

    # Core content should be preserved
    assert "This is a quote with content" == result


# Test normalize_for_fuzzy_match
@pytest.mark.unit
def test_normalize_for_fuzzy_match_lowercase(matcher):
    """Test that fuzzy normalization converts to lowercase."""
    text = "This Is MiXeD CaSe"
    result = matcher.normalize_for_fuzzy_match(text)

    assert result == "this is mixed case"


@pytest.mark.unit
def test_normalize_for_fuzzy_match_preserves_content_lowercase(matcher):
    """Test that fuzzy normalization converts to lowercase and preserves content."""
    text = "Left AND Right AND Backtick"
    result = matcher.normalize_for_fuzzy_match(text)

    # Verify result is lowercase (fuzzy match normalizes to lowercase)
    assert result == "left and right and backtick"
    assert result.islower()


@pytest.mark.unit
def test_normalize_for_fuzzy_match_ellipsis(matcher):
    """Test that ellipsis variations are normalized."""
    text1 = "This... is ellipsis"
    text2 = "This . . . is ellipsis"

    result1 = matcher.normalize_for_fuzzy_match(text1)
    result2 = matcher.normalize_for_fuzzy_match(text2)

    assert "..." in result1
    assert "..." in result2


# Test calculate_similarity
@pytest.mark.unit
def test_calculate_similarity_identical_strings(matcher):
    """Test similarity of identical strings is 1.0."""
    text = "The quick brown fox"
    similarity = matcher.calculate_similarity(text, text)

    assert similarity == 1.0


@pytest.mark.unit
def test_calculate_similarity_completely_different(matcher):
    """Test similarity of completely different strings is low."""
    text1 = "The quick brown fox"
    text2 = "Zebra jumping over clouds"
    similarity = matcher.calculate_similarity(text1, text2)

    assert similarity < 0.3


@pytest.mark.unit
def test_calculate_similarity_minor_difference(matcher):
    """Test similarity with minor differences."""
    text1 = "The quick brown fox jumps"
    text2 = "The quick brown fox leaps"
    similarity = matcher.calculate_similarity(text1, text2)

    # Should be high but not perfect
    assert 0.8 < similarity < 1.0


# Test find_quote_exact
@pytest.mark.unit
def test_find_quote_exact_perfect_match(matcher, sample_source_text):
    """Test finding an exact quote match."""
    quote = "the right to privacy"
    matches = matcher.find_quote_exact(quote, sample_source_text)

    assert len(matches) > 0
    assert matches[0].exact_match is True
    assert matches[0].similarity == 1.0
    assert matches[0].found is True


@pytest.mark.unit
def test_find_quote_exact_case_insensitive(matcher, sample_source_text):
    """Test that exact matching is case-insensitive."""
    quote = "THE RIGHT TO PRIVACY"
    matches = matcher.find_quote_exact(quote, sample_source_text)

    assert len(matches) > 0
    assert matches[0].exact_match is True


@pytest.mark.unit
def test_find_quote_exact_no_match(matcher, sample_source_text):
    """Test when quote is not found."""
    quote = "this text does not appear in the source"
    matches = matcher.find_quote_exact(quote, sample_source_text)

    assert len(matches) == 0


@pytest.mark.unit
def test_find_quote_exact_multiple_matches(matcher):
    """Test finding multiple occurrences of the same quote."""
    source = "Privacy is important. Privacy protects us. Privacy matters."
    quote = "Privacy"
    matches = matcher.find_quote_exact(quote, source)

    assert len(matches) >= 3


@pytest.mark.unit
def test_find_quote_exact_includes_context(matcher, sample_source_text):
    """Test that matches include context before and after."""
    quote = "right to privacy"
    matches = matcher.find_quote_exact(quote, sample_source_text)

    assert len(matches) > 0
    match = matches[0]
    assert len(match.context_before) > 0
    assert len(match.context_after) > 0


# Test find_quote_fuzzy
@pytest.mark.unit
def test_find_quote_fuzzy_near_threshold(matcher):
    """Test fuzzy matching at the 0.85 threshold boundary."""
    # Create quote and source with ~85% similarity
    quote = "The quick brown fox jumps over the lazy dog today"
    source = "The quick brown fox leaps over the lazy dog yesterday"

    matches = matcher.find_quote_fuzzy(quote, source)

    # Should find a match since similarity is around threshold
    assert len(matches) > 0
    assert matches[0].exact_match is False
    assert matches[0].similarity >= 0.85


@pytest.mark.unit
def test_find_quote_fuzzy_below_threshold(matcher):
    """Test fuzzy matching below threshold doesn't match."""
    quote = "The Supreme Court decided this case unanimously"
    source = "Congress passed legislation on budget matters recently"

    matches = matcher.find_quote_fuzzy(quote, source)

    # Should not find matches (too different)
    assert len(matches) == 0


@pytest.mark.unit
def test_find_quote_fuzzy_finds_differences(matcher):
    """Test that fuzzy matches include difference descriptions."""
    quote = "the right to privacy"
    source = "the right to private life"  # Similar but different

    matches = matcher.find_quote_fuzzy(quote, source)

    if len(matches) > 0:
        match = matches[0]
        assert len(match.differences) > 0
        assert match.exact_match is False


@pytest.mark.unit
def test_find_quote_fuzzy_sorts_by_similarity(matcher):
    """Test that fuzzy matches are sorted by similarity (descending)."""
    quote = "court decided"
    source = """
    The court decided quickly. The court decided carefully.
    The supreme court decided unanimously.
    """

    matches = matcher.find_quote_fuzzy(quote, source, max_matches=3)

    if len(matches) > 1:
        # Verify sorted in descending order
        for i in range(len(matches) - 1):
            assert matches[i].similarity >= matches[i + 1].similarity


# Test _find_differences
@pytest.mark.unit
def test_find_differences_identical_text(matcher):
    """Test that identical text has no differences."""
    text = "The right to privacy is fundamental"
    differences = matcher._find_differences(text, text)

    assert len(differences) == 0


@pytest.mark.unit
def test_find_differences_length_difference(matcher):
    """Test detection of length differences."""
    text1 = "short"
    text2 = "much longer text"
    differences = matcher._find_differences(text1, text2)

    assert any("Length differs" in d for d in differences)


@pytest.mark.unit
def test_find_differences_word_count(matcher):
    """Test detection of word count differences."""
    text1 = "one two three"
    text2 = "one two three four five"
    differences = matcher._find_differences(text1, text2)

    assert any("Word count differs" in d for d in differences)


@pytest.mark.unit
def test_find_differences_word_replacement(matcher):
    """Test detection of word replacements."""
    text1 = "the quick brown fox"
    text2 = "the slow brown fox"
    differences = matcher._find_differences(text1, text2)

    assert any("Words differ" in d or "replace" in d.lower() for d in differences)


# Test verify_quote
@pytest.mark.unit
def test_verify_quote_exact_match(matcher, sample_source_text):
    """Test verification with exact match."""
    quote = "right to privacy"
    result = matcher.verify_quote(quote, sample_source_text, "410 U.S. 113")

    assert result.found is True
    assert result.exact_match is True
    assert result.similarity == 1.0
    assert len(result.matches) > 0
    assert len(result.warnings) == 0
    assert "verified exactly" in result.recommendation.lower()


@pytest.mark.unit
def test_verify_quote_fuzzy_match_high_similarity(matcher):
    """Test verification with high-similarity fuzzy match."""
    quote = "The Supreme Court has long recognized"
    source = "The Supreme Court has long recognized this principle"

    result = matcher.verify_quote(quote, source, "Test")

    assert result.found is True
    assert result.exact_match is True or result.similarity >= 0.95


@pytest.mark.unit
def test_verify_quote_fuzzy_match_low_similarity(matcher):
    """Test verification with low-similarity fuzzy match."""
    quote = "the right to privacy is fundamental"
    source = "the right to personal freedom is essential"

    result = matcher.verify_quote(quote, source, "Test")

    # Might find fuzzy match or not find at all
    if result.found:
        assert result.exact_match is False
        assert len(result.warnings) > 0
        assert "differs" in result.recommendation.lower()


@pytest.mark.unit
def test_verify_quote_not_found(matcher, sample_source_text):
    """Test verification when quote is not found."""
    quote = "this quote does not exist anywhere in the source at all"
    result = matcher.verify_quote(quote, sample_source_text, "Test")

    assert result.found is False
    assert result.exact_match is False
    assert result.similarity == 0.0
    assert len(result.matches) == 0
    assert len(result.warnings) > 0
    assert "not found" in result.warnings[0].lower()


@pytest.mark.unit
def test_verify_quote_empty_quote(matcher, sample_source_text):
    """Test verification with empty quote."""
    quote = ""
    result = matcher.verify_quote(quote, sample_source_text, "Test")

    assert result.found is False
    assert result.exact_match is False
    assert "empty" in result.warnings[0].lower()


@pytest.mark.unit
def test_verify_quote_whitespace_only(matcher, sample_source_text):
    """Test verification with whitespace-only quote."""
    quote = "   \n\t  "
    result = matcher.verify_quote(quote, sample_source_text, "Test")

    assert result.found is False
    assert len(result.warnings) > 0


# Test context extraction edge cases
@pytest.mark.unit
def test_context_extraction_at_start_of_text(matcher):
    """Test context extraction when match is at the start."""
    source = "Privacy is important and fundamental."
    quote = "Privacy"
    matches = matcher.find_quote_exact(quote, source)

    assert len(matches) > 0
    match = matches[0]
    # Context before should be empty or very short
    assert len(match.context_before) < 10
    assert len(match.context_after) > 0


@pytest.mark.unit
def test_context_extraction_at_end_of_text(matcher):
    """Test context extraction when match is at the end."""
    source = "This is important for privacy"
    quote = "privacy"
    matches = matcher.find_quote_exact(quote, source)

    assert len(matches) > 0
    match = matches[0]
    assert len(match.context_before) > 0
    # Context after should be empty or very short
    assert len(match.context_after) < 10


@pytest.mark.unit
def test_verify_quote_very_long_quote(matcher):
    """Test verification with a very long quote."""
    quote = " ".join(["word"] * 100)  # 100-word quote
    source = "Some text " + quote + " more text"

    result = matcher.verify_quote(quote, source, "Test")

    assert result.found is True


@pytest.mark.unit
def test_verify_quote_with_special_characters(matcher):
    """Test verification with special characters in quote."""
    quote = "privacy? Yes! It's important."
    source = "We asked: privacy? Yes! It's important. Very important."

    result = matcher.verify_quote(quote, source, "Test")

    assert result.found is True
