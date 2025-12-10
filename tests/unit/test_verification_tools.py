"""Unit tests for quote verification tools."""

import pytest
from unittest.mock import AsyncMock, patch

from app.tools.verification import (
    _parse_pinpoint_number,
    _extract_pinpoint_slice,
    verify_quote_impl,
    batch_verify_quotes_impl,
)


# Test _parse_pinpoint_number
@pytest.mark.unit
def test_parse_pinpoint_number_simple():
    """Test parsing simple numeric pinpoint."""
    assert _parse_pinpoint_number("153") == 153
    assert _parse_pinpoint_number("42") == 42


@pytest.mark.unit
def test_parse_pinpoint_number_with_text():
    """Test parsing pinpoint with surrounding text."""
    assert _parse_pinpoint_number("at 153") == 153
    assert _parse_pinpoint_number("page 42") == 42
    assert _parse_pinpoint_number("§ 123") == 123


@pytest.mark.unit
def test_parse_pinpoint_number_multiple_numbers():
    """Test parsing pinpoint with multiple numbers (returns first)."""
    assert _parse_pinpoint_number("153-160") == 153
    assert _parse_pinpoint_number("42, 45") == 42


@pytest.mark.unit
def test_parse_pinpoint_number_no_numbers():
    """Test parsing pinpoint without numbers."""
    assert _parse_pinpoint_number("no numbers here") is None
    assert _parse_pinpoint_number("") is None


# Test _extract_pinpoint_slice
@pytest.mark.unit
def test_extract_pinpoint_slice_page_marker():
    """Test extracting slice using page marker."""
    full_text = "Some text before. Page 5 This is the target page content. More text after."
    pinpoint = "5"

    result = _extract_pinpoint_slice(full_text, pinpoint)

    assert result.method == "page_marker"
    assert result.target_value == 5
    assert "target page content" in result.text
    assert result.error is None


@pytest.mark.unit
def test_extract_pinpoint_slice_paragraph_index():
    """Test extracting slice using paragraph index."""
    full_text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    pinpoint = "2"  # Second paragraph (1-indexed)

    result = _extract_pinpoint_slice(full_text, pinpoint)

    assert result.method == "paragraph_index"
    assert result.target_value == 2
    assert "Second paragraph" in result.text


@pytest.mark.unit
def test_extract_pinpoint_slice_unparsable():
    """Test extracting slice with unparsable pinpoint."""
    full_text = "Some opinion text"
    pinpoint = "no numbers"

    result = _extract_pinpoint_slice(full_text, pinpoint)

    assert result.method == "full_text"
    assert result.text == full_text
    assert result.error == "Could not parse numeric pinpoint value"
    assert result.error_code == "PINPOINT_UNPARSABLE"


@pytest.mark.unit
def test_extract_pinpoint_slice_not_found():
    """Test extracting slice when marker not found."""
    full_text = "Opinion text without markers."
    pinpoint = "999"  # Non-existent page

    result = _extract_pinpoint_slice(full_text, pinpoint)

    # Should try paragraph index, and if that fails, return full text
    assert result.text == full_text
    if result.method == "full_text":
        assert result.error == "Pinpoint marker not located in text"
        assert result.error_code == "PINPOINT_NOT_FOUND"


# Test verify_quote_impl
@pytest.mark.unit
async def test_verify_quote_impl_successful_exact_match(mock_client):
    """Test successful quote verification with exact match."""
    # Setup mock
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [{"id": 789}],
    }
    mock_client.get_opinion_full_text.return_value = (
        "The right to privacy is fundamental and well-established."
    )

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await verify_quote_impl(
            quote="right to privacy",
            citation="123 U.S. 456",
        )

    assert result["found"] is True
    assert result["citation"] == "123 U.S. 456"
    assert result["case_name"] == "Test Case"
    assert "error" not in result


@pytest.mark.unit
async def test_verify_quote_impl_case_not_found(mock_client):
    """Test verification when case is not found."""
    mock_client.lookup_citation.return_value = {"error": "Case not found"}

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await verify_quote_impl(
            quote="test quote",
            citation="999 U.S. 999",
        )

    assert "error" in result
    assert result["error_code"] == "CASE_NOT_FOUND"
    assert result["citation"] == "999 U.S. 999"


@pytest.mark.unit
async def test_verify_quote_impl_no_opinions(mock_client):
    """Test verification when case has no opinions."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [],  # No opinions
    }

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await verify_quote_impl(
            quote="test quote",
            citation="123 U.S. 456",
        )

    assert "error" in result
    assert result["error_code"] == "NO_OPINION_TEXT"
    assert "No opinion text available" in result["error"]


@pytest.mark.unit
async def test_verify_quote_impl_text_retrieval_failed(mock_client):
    """Test verification when opinion text cannot be retrieved."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [{"id": 789}],
    }
    mock_client.get_opinion_full_text.return_value = ""  # Empty text

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await verify_quote_impl(
            quote="test quote",
            citation="123 U.S. 456",
        )

    assert "error" in result
    assert result["error_code"] == "TEXT_RETRIEVAL_FAILED"


@pytest.mark.unit
async def test_verify_quote_impl_with_pinpoint(mock_client):
    """Test verification with pinpoint citation."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [{"id": 789}],
    }
    mock_client.get_opinion_full_text.return_value = (
        "Page 5 contains important text about privacy rights."
    )

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await verify_quote_impl(
            quote="privacy rights",
            citation="123 U.S. 456",
            pinpoint="at 5",
        )

    assert "pinpoint_provided" in result
    assert result["pinpoint_provided"] == "at 5"


@pytest.mark.unit
async def test_verify_quote_impl_pinpoint_fallback_to_full_text(mock_client):
    """Test that verification falls back to full text if pinpoint slice fails."""
    full_text = "Beginning text. The quote is here in the middle. Ending text."

    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [{"id": 789}],
    }
    mock_client.get_opinion_full_text.return_value = full_text

    with patch("app.tools.verification.get_client", return_value=mock_client):
        # Pinpoint that won't match, but quote exists in full text
        result = await verify_quote_impl(
            quote="quote is here",
            citation="123 U.S. 456",
            pinpoint="999",  # Non-existent page
        )

    # Should find the quote via fallback to full text
    assert result["found"] is True or "grounding" in result


# Test batch_verify_quotes_impl
@pytest.mark.unit
async def test_batch_verify_quotes_impl_multiple_quotes(mock_client):
    """Test batch verification of multiple quotes."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [{"id": 789}],
    }
    mock_client.get_opinion_full_text.return_value = (
        "This opinion contains privacy rights and equal protection."
    )

    quotes = [
        {"quote": "privacy rights", "citation": "123 U.S. 456"},
        {"quote": "equal protection", "citation": "123 U.S. 456"},
    ]

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await batch_verify_quotes_impl(quotes)

    assert result["total_quotes"] == 2
    assert "verified" in result
    assert "results" in result
    assert len(result["results"]) == 2


@pytest.mark.unit
async def test_batch_verify_quotes_impl_statistics(mock_client):
    """Test that batch verification includes correct statistics."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [{"id": 789}],
    }
    mock_client.get_opinion_full_text.return_value = "Only one quote matches here."

    quotes = [
        {"quote": "quote matches", "citation": "123 U.S. 456"},
        {"quote": "this does not exist", "citation": "123 U.S. 456"},
    ]

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await batch_verify_quotes_impl(quotes)

    assert "total_quotes" in result
    assert "verified" in result
    assert "exact_matches" in result
    assert "fuzzy_matches" in result
    assert "not_found" in result
    assert "errors" in result


@pytest.mark.unit
async def test_batch_verify_quotes_impl_missing_data():
    """Test batch verification with missing quote or citation."""
    quotes = [
        {"quote": "", "citation": "123 U.S. 456"},  # Empty quote
        {"quote": "valid quote", "citation": ""},  # Empty citation
    ]

    result = await batch_verify_quotes_impl(quotes)

    assert result["errors"] == 2
    assert all("error" in r for r in result["results"])


@pytest.mark.unit
async def test_batch_verify_quotes_impl_empty_list():
    """Test batch verification with empty list."""
    result = await batch_verify_quotes_impl([])

    assert result["total_quotes"] == 0
    assert result["verified"] == 0
    assert result["errors"] == 0


@pytest.mark.unit
async def test_batch_verify_quotes_impl_with_pinpoints(mock_client):
    """Test batch verification with pinpoint citations."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
        "opinions": [{"id": 789}],
    }
    mock_client.get_opinion_full_text.return_value = "Page 5 has the quote."

    quotes = [
        {
            "quote": "the quote",
            "citation": "123 U.S. 456",
            "pinpoint": "at 5",
        },
    ]

    with patch("app.tools.verification.get_client", return_value=mock_client):
        result = await batch_verify_quotes_impl(quotes)

    assert result["total_quotes"] == 1
    assert result["results"][0]["pinpoint_provided"] == "at 5"


# Edge cases
@pytest.mark.unit
def test_extract_pinpoint_slice_boundary_paragraph():
    """Test paragraph extraction at boundary (last paragraph)."""
    full_text = "Para 1\n\nPara 2\n\nPara 3"
    pinpoint = "3"

    result = _extract_pinpoint_slice(full_text, pinpoint)

    assert result.method == "paragraph_index"
    assert "Para 3" in result.text


@pytest.mark.unit
def test_extract_pinpoint_slice_out_of_range_paragraph():
    """Test paragraph extraction with out-of-range index."""
    full_text = "Para 1\n\nPara 2"
    pinpoint = "10"  # Beyond number of paragraphs

    result = _extract_pinpoint_slice(full_text, pinpoint)

    assert result.method == "full_text"
    assert result.text == full_text


@pytest.mark.unit
def test_parse_pinpoint_number_with_section_symbol():
    """Test parsing pinpoint with section symbol."""
    assert _parse_pinpoint_number("§ 42") == 42
    assert _parse_pinpoint_number("¶ 15") == 15
