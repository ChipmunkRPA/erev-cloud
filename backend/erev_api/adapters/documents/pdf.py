"""Extract PDF page text for an authorized worker (AIA-13).

This parser is not an authorization boundary or a process resource sandbox. The
worker must impose its own memory/time limits before parsing untrusted documents.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, apply_configuration
from pypdf.errors import LimitReachedError, PyPdfError

from erev_api.domain.ai.document_preparation import MAX_PAGES, MAX_TEXT_BYTES
from erev_api.domain.ai.document_preparation import MAX_PDF_BYTES as MAX_PDF_BYTES

MAX_STREAM_BYTES = 8 * 1024 * 1024


class PDFExtractionRefused(ValueError):
    """Safe code without parser diagnostics, document content or a password."""


def extract_pdf_pages(data: bytes, *, send_contract_text: bool) -> tuple[str, ...]:
    """Return all page texts atomically; encrypted and image-only PDFs refuse.

    Empty pages inside a text-bearing document remain present. No OCR, actions,
    external links, attachments or JavaScript are executed by this adapter.
    """
    if not send_contract_text:
        raise PDFExtractionRefused("AI_TEXT_DISABLED")
    if len(data) > MAX_PDF_BYTES:
        raise PDFExtractionRefused("AI_DOCUMENT_FILE_LIMIT")
    if not data.startswith(b"%PDF-"):
        raise PDFExtractionRefused("AI_INVALID_PDF")
    pages: list[str] = []
    total = 0
    try:
        with apply_configuration(
            maximum_declared_stream_length=MAX_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_STREAM_BYTES,
            zlib_maximum_output_length=MAX_STREAM_BYTES,
            lzw_maximum_output_length=MAX_STREAM_BYTES,
            run_length_maximum_output_length=MAX_STREAM_BYTES,
            brotli_maximum_output_length=MAX_STREAM_BYTES,
            stream_decoding_work_maximum_length=4 * MAX_STREAM_BYTES,
            page_tree_maximum_entries=2 * MAX_PAGES + 1,
            jbig2dec_binary=None,
        ):
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise PDFExtractionRefused("AI_PDF_ENCRYPTED")
            if not 1 <= len(reader.pages) <= MAX_PAGES:
                raise PDFExtractionRefused("AI_DOCUMENT_PAGE_LIMIT")
            for page in reader.pages:
                text = page.extract_text()
                total += len(text.encode("utf-8"))
                if total > MAX_TEXT_BYTES:
                    raise PDFExtractionRefused("AI_DOCUMENT_TEXT_LIMIT")
                pages.append(text)
    except PDFExtractionRefused:
        raise
    except LimitReachedError:
        raise PDFExtractionRefused("AI_PDF_RESOURCE_LIMIT") from None
    except (PyPdfError, ValueError, TypeError, KeyError, IndexError, RecursionError):
        raise PDFExtractionRefused("AI_INVALID_PDF") from None
    if not any(text.strip() for text in pages):
        raise PDFExtractionRefused("AI_DOCUMENT_NO_TEXT")
    return tuple(pages)
