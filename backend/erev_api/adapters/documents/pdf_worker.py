"""Private subprocess protocol. Apply resource limits before importing the parser."""

from __future__ import annotations

import json
import sys

MEMORY_BYTES = 512 * 1024 * 1024
CPU_SECONDS = 15


def _apply_limits() -> None:
    if sys.platform != "linux":
        raise RuntimeError("Unsupported resource isolation platform")
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))


def main() -> None:
    try:
        _apply_limits()
    except (OSError, ValueError, RuntimeError, ImportError):
        sys.stdout.write('{"code":"AI_PDF_ISOLATION_UNAVAILABLE"}')
        return
    try:
        from erev_api.adapters.documents.pdf import (
            MAX_PDF_BYTES,
            PDFExtractionRefused,
            extract_pdf_pages,
        )

        data = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
        try:
            pages = extract_pdf_pages(data, send_contract_text=True)
        except PDFExtractionRefused as error:
            sys.stdout.write(json.dumps({"code": str(error)}))
            return
        sys.stdout.write(json.dumps({"pages": pages}, ensure_ascii=True))
    except MemoryError:
        sys.stdout.write('{"code":"AI_PDF_RESOURCE_LIMIT"}')


if __name__ == "__main__":
    main()
