import logging
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.analysis.document_processing import extract_citations, extract_text_from_pdf


def _build_pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()

    page = writer.add_blank_page(width=200, height=200)

    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )

    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("utf-8"))
    page[NameObject("/Contents")] = writer._add_object(content)

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


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


def test_extract_text_from_pdf():
    pdf_bytes = _build_pdf_bytes("Hello World")

    extracted = extract_text_from_pdf(pdf_bytes)

    assert extracted.strip() == "Hello World"


def test_extract_text_from_pdf_invalid_bytes_logs_error(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.ERROR, logger="app.analysis.document_processing"):
        extracted = extract_text_from_pdf(b"%PDF-1.4 invalid content")

    assert extracted == ""
    assert any(
        record.levelname == "ERROR" and "PDF extraction failed" in record.message
        for record in caplog.records
    )
