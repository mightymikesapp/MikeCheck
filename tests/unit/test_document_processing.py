from app.analysis import document_processing
from app.analysis.document_processing import extract_citations, extract_text_from_pdf


def test_extract_citations_simple():
    text = "See 410 U.S. 113 for details."
    citations = extract_citations(text)
    assert "410 U.S. 113" in citations

def test_extract_citations_with_excluded_terms():
    text = "The January 2020 report." # Should not match "January 2020" even if it looks like vol/rep/page
    citations = extract_citations(text)
    assert not citations

def test_extract_citations_multiple():
    text = "Cases 123 F.2d 456 and 789 U.S. 101."
    citations = extract_citations(text)
    assert "123 F.2d 456" in citations
    assert "789 U.S. 101" in citations

def test_extract_citations_duplicates():
    text = "410 U.S. 113. Also 410 U.S. 113."
    citations = extract_citations(text)
    assert len(citations) == 1
    assert citations[0] == "410 U.S. 113"


def test_extract_text_from_pdf_with_none_page(monkeypatch):
    class FakePage:
        def __init__(self, text: str | None):
            self._text = text

        def extract_text(self) -> str | None:
            return self._text

    class FakeReader:
        def __init__(self, *_: object, **__: object) -> None:
            self.pages = [FakePage(None)]

    monkeypatch.setattr(document_processing, "PdfReader", FakeReader)

    result = extract_text_from_pdf(b"irrelevant")

    assert result == ""
