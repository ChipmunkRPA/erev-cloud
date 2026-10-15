"""Real child processes exercise transport, fail-closed platform and timeout cleanup."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from erev_api.adapters.documents import isolated_pdf
from erev_api.adapters.documents.pdf import PDFExtractionRefused


def command(monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    monkeypatch.setattr(
        isolated_pdf, "_worker_command", lambda: [sys.executable, "-I", "-c", script]
    )


def test_production_command_is_isolated_interpreter() -> None:
    assert isolated_pdf._worker_command() == [
        sys.executable,
        "-I",
        "-m",
        "erev_api.adapters.documents.pdf_worker",
    ]


def test_real_child_does_not_inherit_secrets_and_receives_exact_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-test-value")
    monkeypatch.setenv("DATABASE_URL", "secret-test-database")
    command(
        monkeypatch,
        'import json,os,sys; data=sys.stdin.buffer.read(); assert data==b"input"; '
        'assert "ANTHROPIC_API_KEY" not in os.environ; '
        'assert "DATABASE_URL" not in os.environ; '
        'print(json.dumps({"pages":["", "Café", ""]}))',
    )
    assert isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=True) == (
        "",
        "Café",
        "",
    )


def test_disabled_does_not_launch_child(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> list[str]:
        pytest.fail("must not launch a child")

    monkeypatch.setattr(isolated_pdf, "_worker_command", forbidden)
    with pytest.raises(PDFExtractionRefused, match="AI_TEXT_DISABLED"):
        isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=False)


def test_timeout_kills_and_reaps_real_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "child.pid"
    command(
        monkeypatch,
        "import os,pathlib,time; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)",
    )
    monkeypatch.setattr(isolated_pdf, "WALL_TIMEOUT_SECONDS", 1)
    with pytest.raises(PDFExtractionRefused, match="AI_PDF_TIMEOUT"):
        isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=True)
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize(
    "response",
    [
        {"code": "private details"},
        {"pages": []},
        {"pages": [1]},
        {"pages": [""]},
        {"unexpected": "secret"},
    ],
)
def test_invalid_child_protocol_has_safe_failure(
    monkeypatch: pytest.MonkeyPatch, response: object
) -> None:
    command(
        monkeypatch,
        "import sys; sys.stderr.write('sensitive parser diagnostics'); "
        f"sys.stdout.write({json.dumps(response)!r})",
    )
    with pytest.raises(PDFExtractionRefused, match="^AI_PDF_PROCESS_FAILED$"):
        isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=True)


def test_known_error_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    command(monkeypatch, 'print(\'{"code":"AI_PDF_ENCRYPTED"}\')')
    with pytest.raises(PDFExtractionRefused, match="AI_PDF_ENCRYPTED"):
        isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=True)


def test_actual_worker_refuses_unsupported_host_or_parses_on_linux() -> None:
    fixture = (
        Path(__file__).parents[2] / "fixtures/ai/documents/Kinsley-Marrow-Order-Form-2026-10.pdf"
    )
    if sys.platform != "linux":
        with pytest.raises(PDFExtractionRefused, match="AI_PDF_ISOLATION_UNAVAILABLE"):
            isolated_pdf.extract_pdf_pages_isolated(fixture.read_bytes(), send_contract_text=True)
    else:
        pages = isolated_pdf.extract_pdf_pages_isolated(
            fixture.read_bytes(), send_contract_text=True
        )
        assert len(pages) == 4
        assert "Kinsley Marrow Foods Inc." in pages[0]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux RLIMIT_AS enforcement requires Linux")
def test_linux_address_space_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    command(
        monkeypatch,
        "from erev_api.adapters.documents.pdf_worker import _apply_limits; "
        "_apply_limits(); import sys;\ntry: bytearray(1024*1024*1024)\n"
        'except MemoryError: sys.stdout.write(\'{"code":"AI_PDF_RESOURCE_LIMIT"}\')',
    )
    with pytest.raises(PDFExtractionRefused, match="AI_PDF_RESOURCE_LIMIT"):
        isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=True)


@pytest.mark.parametrize(
    "script,code",
    [
        ("import sys; sys.exit(2)", "AI_PDF_PROCESS_FAILED"),
        ("import os,signal; os.kill(os.getpid(), signal.SIGKILL)", "AI_PDF_RESOURCE_LIMIT"),
    ],
)
def test_child_failure_is_classified(
    monkeypatch: pytest.MonkeyPatch, script: str, code: str
) -> None:
    command(monkeypatch, script)
    with pytest.raises(PDFExtractionRefused, match=code):
        isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=True)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux CPU enforcement requires Linux")
def test_linux_cpu_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    command(
        monkeypatch,
        "from erev_api.adapters.documents import pdf_worker; "
        "pdf_worker.CPU_SECONDS=1; pdf_worker._apply_limits();\nwhile True: pass",
    )
    with pytest.raises(PDFExtractionRefused, match="AI_PDF_RESOURCE_LIMIT"):
        isolated_pdf.extract_pdf_pages_isolated(b"input", send_contract_text=True)
