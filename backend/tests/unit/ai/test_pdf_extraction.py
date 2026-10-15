"""Real PDF limits and the documented WLD-F-29 fixture through fake extraction."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.adapters.ai.provider import FakeProvider
from erev_api.adapters.documents.pdf import PDFExtractionRefused, extract_pdf_pages
from erev_api.domain.ai.document_preparation import prepare_extraction
from pypdf import PdfWriter, get_configuration
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

FIXTURE = Path(__file__).parents[2] / "fixtures/ai/documents/Kinsley-Marrow-Order-Form-2026-10.pdf"


def pdf(texts: list[str], *, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream.flate_encode()
    if encrypted:
        writer.encrypt("test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_kinsley_marrow_fields_have_source_citations_and_expected_confidence() -> None:
    pages = extract_pdf_pages(FIXTURE.read_bytes(), send_contract_text=True)
    assert len(pages) == 4
    paths = frozenset(
        {
            "customer_name",
            "effective_date",
            "term_months",
            "payment_terms",
            "termination",
            "lines.0",
            "lines.1",
            "variable_consideration_terms",
            "material_right_indicator",
        }
    )
    prepared = prepare_extraction(
        document_id=UUID(int=41),
        pages=pages,
        allowed_paths=paths,
        model="fixture-model",
        max_tokens=16000,
        send_contract_text=True,
    )
    fields = prepared.validate(FakeProvider().complete(prepared.request))
    content = {item.path: item.as_content() for item in fields}
    assert content["customer_name"]["value"] == "Kinsley Marrow Foods Inc."
    assert content["effective_date"]["value"] == "2026-10-01"
    assert content["term_months"]["value"] == 12
    assert content["payment_terms"]["value"] == "Net 30"
    assert content["lines.0"]["value"] == {"product_code": "AVM-PLAT-100", "amount": "96000.00"}
    assert content["lines.1"]["value"] == {"product_code": "AVM-IMPL-PLUS", "amount": "24000.00"}
    assert [item.confidence for item in fields] == [
        Decimal(value)
        for value in ["0.97", "0.95", "0.93", "0.91", "0.72", "0.94", "0.88", "0.62", "0.58"]
    ]
    assert {item.path for item in fields if item.check} == {
        "termination",
        "variable_consideration_terms",
        "material_right_indicator",
    }
    for item in fields:
        citation = item.citation
        quote = pages[citation.page - 1][citation.char_start : citation.char_end]
        assert quote.strip()
        if item.path in {
            "customer_name",
            "payment_terms",
            "variable_consideration_terms",
            "material_right_indicator",
        }:
            assert quote == item.as_content()["value"]
    assert "purchasing@example.test" not in prepared.request.messages[0]["content"]


def test_disabled_before_pdf_parse() -> None:
    with pytest.raises(PDFExtractionRefused, match="AI_TEXT_DISABLED"):
        extract_pdf_pages(b"invalid", send_contract_text=False)


@pytest.mark.parametrize("data", [b"not a PDF", b"%PDF-1.7\nprivate broken content"])
def test_invalid_pdf_has_safe_failure(data: bytes) -> None:
    with pytest.raises(PDFExtractionRefused, match="^AI_INVALID_PDF$"):
        extract_pdf_pages(data, send_contract_text=True)


def test_encrypted_pdf_refused() -> None:
    with pytest.raises(PDFExtractionRefused, match="AI_PDF_ENCRYPTED"):
        extract_pdf_pages(pdf(["hello"], encrypted=True), send_contract_text=True)


def test_empty_pages_preserved_but_no_text_document_refused() -> None:
    assert extract_pdf_pages(pdf(["", "hello", ""]), send_contract_text=True) == ("", "hello", "")
    with pytest.raises(PDFExtractionRefused, match="AI_DOCUMENT_NO_TEXT"):
        extract_pdf_pages(pdf([""]), send_contract_text=True)


def test_page_cap_and_total_utf8_text_cap() -> None:
    with pytest.raises(PDFExtractionRefused, match="AI_DOCUMENT_PAGE_LIMIT"):
        extract_pdf_pages(pdf([""] * 601), send_contract_text=True)
    with pytest.raises(PDFExtractionRefused, match="AI_DOCUMENT_TEXT_LIMIT"):
        extract_pdf_pages(
            pdf(["a" * (1024 * 1024), "b" * (1024 * 1024 + 1)]), send_contract_text=True
        )


def test_stream_expansion_refused_and_configuration_restored() -> None:
    before = get_configuration()
    with pytest.raises(PDFExtractionRefused, match="AI_PDF_RESOURCE_LIMIT"):
        extract_pdf_pages(pdf(["a" * (9 * 1024 * 1024)]), send_contract_text=True)
    assert get_configuration() == before


def test_file_size_refused_before_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    from erev_api.adapters.documents import pdf as adapter

    monkeypatch.setattr(adapter, "MAX_PDF_BYTES", 5)
    with pytest.raises(PDFExtractionRefused, match="AI_DOCUMENT_FILE_LIMIT"):
        extract_pdf_pages(b"%PDF-1.7", send_contract_text=True)
