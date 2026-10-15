"""Run untrusted PDF parsing outside the worker process, with no inherited secrets."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys

from erev_api.adapters.documents.pdf import MAX_PDF_BYTES, PDFExtractionRefused
from erev_api.domain.ai.document_preparation import MAX_PAGES, MAX_TEXT_BYTES

WALL_TIMEOUT_SECONDS = 30
SAFE_CODES = frozenset(
    {
        "AI_PDF_ISOLATION_UNAVAILABLE",
        "AI_PDF_RESOURCE_LIMIT",
        "AI_INVALID_PDF",
        "AI_DOCUMENT_FILE_LIMIT",
        "AI_PDF_ENCRYPTED",
        "AI_DOCUMENT_PAGE_LIMIT",
        "AI_DOCUMENT_TEXT_LIMIT",
        "AI_DOCUMENT_NO_TEXT",
    }
)


def _worker_command() -> list[str]:
    return [sys.executable, "-I", "-m", "erev_api.adapters.documents.pdf_worker"]


def extract_pdf_pages_isolated(data: bytes, *, send_contract_text: bool) -> tuple[str, ...]:
    """Only this entry point should parse uploads in an operational worker.

    The child establishes Linux CPU/address-space limits before importing pypdf.
    Other hosts fail closed. The parent bounds wall time, kills and reaps a timed
    out child, discards stderr, and validates the bounded child's response.
    """
    if not send_contract_text:
        raise PDFExtractionRefused("AI_TEXT_DISABLED")
    if len(data) > MAX_PDF_BYTES:
        raise PDFExtractionRefused("AI_DOCUMENT_FILE_LIMIT")
    try:
        result = subprocess.run(
            _worker_command(),
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=WALL_TIMEOUT_SECONDS,
            check=False,
            close_fds=True,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        )
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for the child before propagating timeout.
        raise PDFExtractionRefused("AI_PDF_TIMEOUT") from None
    except OSError:
        raise PDFExtractionRefused("AI_PDF_ISOLATION_UNAVAILABLE") from None
    if result.returncode in (-signal.SIGKILL, -signal.SIGXCPU):
        raise PDFExtractionRefused("AI_PDF_RESOURCE_LIMIT")
    if result.returncode != 0:
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED")
    # ASCII JSON may escape each text character as six bytes.
    if len(result.stdout) > 6 * MAX_TEXT_BYTES + 64 * MAX_PAGES:
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED")
    try:
        response = json.loads(result.stdout)
    except (ValueError, RecursionError):
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED") from None
    if isinstance(response, dict) and set(response) == {"code"}:
        code = response["code"]
        if isinstance(code, str) and code in SAFE_CODES:
            raise PDFExtractionRefused(code)
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED")
    if not isinstance(response, dict) or set(response) != {"pages"}:
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED")
    pages = response["pages"]
    if (
        not isinstance(pages, list)
        or not 1 <= len(pages) <= MAX_PAGES
        or any(not isinstance(page, str) for page in pages)
    ):
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED")
    try:
        text_size = sum(len(page.encode("utf-8")) for page in pages)
    except UnicodeEncodeError:
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED") from None
    if text_size > MAX_TEXT_BYTES or not any(page.strip() for page in pages):
        raise PDFExtractionRefused("AI_PDF_PROCESS_FAILED")
    return tuple(pages)
