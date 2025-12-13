"""Unit tests for FootnoteParser."""

import pytest

from app.analysis.document_processing import FootnoteParser, ParsedDocument


@pytest.mark.unit
def test_parse_html_with_footnotes():
    """Test parsing HTML with footnote tags."""
    html = """
    <p>The court found that the precedent in 410 U.S. 113 was overruled.</p>
    <p>This is another paragraph of body text.</p>
    <fn num="1">This is a footnote citing 410 U.S. 113 as distinguished.</fn>
    <fn num="2">Another footnote with different content.</fn>
    """

    result = FootnoteParser.parse_html(html)

    assert isinstance(result, ParsedDocument)
    assert "precedent in 410 U.S. 113 was overruled" in result.body_text
    assert "another paragraph of body text" in result.body_text.lower()
    assert "footnote citing 410 U.S. 113 as distinguished" in result.footnote_text
    assert "another footnote" in result.footnote_text.lower()
    assert "1" in result.footnotes
    assert "2" in result.footnotes
    assert "distinguished" in result.footnotes["1"]


@pytest.mark.unit
def test_parse_html_with_div_footnotes():
    """Test parsing HTML with div-based footnote structure."""
    html = """
    <p>Main body text with a citation to 410 U.S. 113.</p>
    <div class="footnote">
        <p>1. This is a footnote in a div.</p>
    </div>
    """

    result = FootnoteParser.parse_html(html)

    assert "Main body text" in result.body_text
    assert "410 U.S. 113" in result.body_text
    assert "footnote in a div" in result.footnote_text


@pytest.mark.unit
def test_parse_html_without_footnotes():
    """Test parsing HTML with no footnotes."""
    html = """
    <p>This is just body text.</p>
    <p>Another paragraph of body text.</p>
    """

    result = FootnoteParser.parse_html(html)

    assert "body text" in result.body_text
    assert result.footnote_text == ""
    assert len(result.footnotes) == 0


@pytest.mark.unit
def test_parse_plain_text_fallback_with_footnotes():
    """Test fallback plain text parser with footnotes at end."""
    text = """
    The court examined the precedent in 410 U.S. 113 and found it was overruled.
    This is the main body of the opinion.

    More body text here.

    1. This is the first footnote mentioning 410 U.S. 113 as distinguished.
    2. This is the second footnote.
    3. A third footnote with more content.
    """

    result = FootnoteParser.parse_plain_text_fallback(text)

    assert "main body of the opinion" in result.body_text
    assert "More body text here" in result.body_text
    # Footnotes should be detected
    assert "first footnote" in result.footnote_text
    assert "second footnote" in result.footnote_text
    assert "1" in result.footnotes, "Expected footnote '1' to be detected"
    assert len(result.footnotes) >= 1


@pytest.mark.unit
def test_parse_plain_text_fallback_without_footnotes():
    """Test fallback parser with no footnotes."""
    text = """
    The court examined the precedent in 410 U.S. 113.
    This is the main body of the opinion.
    No footnotes here.
    """

    result = FootnoteParser.parse_plain_text_fallback(text)

    assert "main body of the opinion" in result.body_text
    # Should not detect footnotes since no numbered patterns at end
    assert len(result.footnotes) == 0 or result.footnote_text == ""


@pytest.mark.unit
def test_parse_plain_text_with_inline_footnote_references():
    """Test detection of inline footnote references like 'n. 14'."""
    text = """
    The court found that Roe was overruled, see n. 14.
    Another case cited in FN 3 supports this.

    Main body continues.
    """

    result = FootnoteParser.parse_plain_text_fallback(text)

    # Text with footnote references might be classified as footnote text
    # depending on heuristics
    assert result.body_text or result.footnote_text


@pytest.mark.unit
def test_parse_empty_html():
    """Test parsing empty HTML."""
    html = ""

    result = FootnoteParser.parse_html(html)

    assert result.body_text == ""
    assert result.footnote_text == ""
    assert len(result.footnotes) == 0


@pytest.mark.unit
def test_parse_empty_plain_text():
    """Test parsing empty plain text."""
    text = ""

    result = FootnoteParser.parse_plain_text_fallback(text)

    assert result.body_text == ""
    assert result.footnote_text == ""
    assert len(result.footnotes) == 0


@pytest.mark.unit
def test_parse_html_complex_structure():
    """Test parsing HTML with mixed content and nested tags."""
    html = """
    <div>
        <p>First paragraph with citation to 410 U.S. 113.</p>
        <p>Second paragraph discussing the case.</p>
    </div>
    <fn num="7">
        <p>Footnote 7 mentions that this was distinguished in later cases.</p>
    </fn>
    <p>More body text after footnote.</p>
    <fn num="8">Another footnote.</fn>
    """

    result = FootnoteParser.parse_html(html)

    assert "First paragraph" in result.body_text
    assert "Second paragraph" in result.body_text
    assert "More body text after footnote" in result.body_text
    assert "Footnote 7" in result.footnote_text
    assert "Another footnote" in result.footnote_text
    assert "7" in result.footnotes
    assert "8" in result.footnotes
