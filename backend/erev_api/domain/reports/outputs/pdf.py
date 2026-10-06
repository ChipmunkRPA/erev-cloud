"""PDF outputs with the RV-07 stamp and a page footer (SCREENS_B RV-02, RV-07; 03 REQ-RPT-002;
BUILD_SPEC RPS-2).

A PDF 1.4 document written directly: A4 landscape pages, the standard Helvetica fonts with
WinAnsiEncoding, uncompressed content streams and no creation date. The first page opens with the
stamp lines (report name and version, run number, entity, book, as of, source, engine release, run
by, run time, rows, output SHA-256, every parameter, the control totals and tie-outs), then the grid
header and the rows; a page that continues the grid repeats its header. Every page footer reads
"Run <run no> · page <n> of <m>". Cell text is truncated with an ellipsis to its column width.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from erev_api.domain.reports.outputs import (
    ReportData,
    RunStamp,
    display_text,
    display_timestamp,
    layout,
    parameter_text,
    total_text,
)

MEDIA_TYPE: Final = "application/pdf"
EXTENSION: Final = "pdf"
PAGE_WIDTH: Final = 842  # A4 landscape, points
PAGE_HEIGHT: Final = 595
MARGIN: Final = 36
FONT_SIZE: Final = 8
LINE_HEIGHT: Final = 11
FOOTER_Y: Final = 20
# Helvetica's average advance at 8 pt, used to fit cell text to a column.
CHARACTER_WIDTH: Final = 4.4
COLUMN_GAP: Final = 6
FOOTER: Final = "Run {run_no} · page {page} of {pages}"
ELLIPSIS: Final = "…"
ALL_ENTITIES: Final = "All entities"
REGULAR: Final = "F1"
BOLD: Final = "F2"


@dataclass(frozen=True, slots=True)
class _Line:
    cells: tuple[tuple[float, str], ...]  # (x, text)
    bold: bool = False
    grid: bool = False  # a row of the grid, which needs the grid header on a new page


def _fit(text: str, width: float) -> str:
    limit = max(int(width // CHARACTER_WIDTH), 1)
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + ELLIPSIS


def _stamp_lines(data: ReportData, stamp: RunStamp) -> list[_Line]:
    style = stamp.negative_number_style
    texts: list[tuple[str, bool]] = [
        (f"{stamp.report_name} v{stamp.report_version}", True),
        (f"Run {stamp.report_run_no}", False),
        (f"Entity: {', '.join(stamp.entity_codes) or ALL_ENTITIES}", False),
        (f"Book: {stamp.book or ''}", False),
        (f"As of: {stamp.as_of or ''}", False),
        (f"Source: {stamp.source}", False),
        (f"Engine: {stamp.engine_version} ({stamp.build_sha})", False),
        (f"Run by: {stamp.run_by}", False),
        (f"Run at: {display_timestamp(stamp.run_at)}", False),
        (f"Rows: {data.row_count:,}", False),
        (f"Output SHA-256: {stamp.output_sha256}", False),
        ("Parameters", True),
        *(
            (f"{key}: {parameter_text(value)}", False)
            for key, value in sorted(stamp.parameters.items())
        ),
        ("Control totals", True),
        *(
            (f"{key}: {total_text(value, style)}", False)
            for key, value in sorted(data.control_totals.items())
        ),
    ]
    if data.tie_out_results:
        texts.append(("Tie-outs", True))
        texts.extend(
            (
                f"{item['code']}: {item['result']} expected {parameter_text(item.get('expected'))}"
                f" actual {parameter_text(item.get('actual'))}",
                False,
            )
            for item in data.tie_out_results
        )
    usable = PAGE_WIDTH - 2 * MARGIN
    return [_Line(((MARGIN, _fit(text, usable)),), bold=bold) for text, bold in texts]


def _grid(data: ReportData, style: str) -> tuple[_Line, list[_Line]]:
    columns = layout(data)
    if not columns:
        return _Line(()), []
    texts = [
        [display_text(item.column, item.part, row.get(item.column.key), style) for item in columns]
        for row in data.rows
    ]
    weights = [
        min(max([len(item.header), *(len(line[index]) for line in texts)]), 40) + 2
        for index, item in enumerate(columns)
    ]
    usable = PAGE_WIDTH - 2 * MARGIN
    total = sum(weights)
    widths = [usable * weight / total for weight in weights]
    positions: list[float] = []
    x = float(MARGIN)
    for width in widths:
        positions.append(x)
        x += width
    fitted = [width - COLUMN_GAP for width in widths]
    header = _Line(
        tuple(
            (positions[index], _fit(item.header, fitted[index]))
            for index, item in enumerate(columns)
        ),
        bold=True,
    )
    body = [
        _Line(
            tuple((positions[index], _fit(text, fitted[index])) for index, text in enumerate(line)),
            grid=True,
        )
        for line in texts
    ]
    return header, body


def _pages(lines: Sequence[_Line], header: _Line) -> list[list[_Line]]:
    per_page = int((PAGE_HEIGHT - 2 * MARGIN) // LINE_HEIGHT)
    pages: list[list[_Line]] = [[]]
    for line in lines:
        if len(pages[-1]) >= per_page:
            pages.append([header] if line.grid else [])
        pages[-1].append(line)
    return pages


def _escape(text: str) -> bytes:
    flat = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    raw = flat.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _text(font: str, x: float, y: float, text: str) -> bytes:
    return (
        f"BT /{font} {FONT_SIZE} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm (".encode("ascii")
        + _escape(text)
        + b") Tj ET\n"
    )


def _content(lines: Sequence[_Line], footer: str) -> bytes:
    parts: list[bytes] = []
    y = PAGE_HEIGHT - MARGIN - FONT_SIZE
    for line in lines:
        font = BOLD if line.bold else REGULAR
        parts.extend(_text(font, x, y, text) for x, text in line.cells if text)
        y -= LINE_HEIGHT
    parts.append(_text(REGULAR, MARGIN, FOOTER_Y, footer))
    return b"".join(parts)


def _document(pages: Sequence[Sequence[_Line]], stamp: RunStamp) -> bytes:
    count = len(pages)
    first_page = 6
    kids = " ".join(f"{first_page + 2 * index} 0 R" for index in range(count))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Title ("
        + _escape(f"{stamp.report_name} v{stamp.report_version}")
        + b") /Subject ("
        + _escape(stamp.report_run_no)
        + b") /Producer (eRev Cloud) >>",
    ]
    for index, lines in enumerate(pages):
        content_ref = first_page + 2 * index + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /{REGULAR} 3 0 R /{BOLD} 4 0 R >> >> "
                f"/Contents {content_ref} 0 R >>"
            ).encode("ascii")
        )
        footer = FOOTER.format(run_no=stamp.report_run_no, page=index + 1, pages=count)
        stream = _content(lines, footer)
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        )
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    out += b"".join(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 5 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def render_pdf(data: ReportData, stamp: RunStamp) -> bytes:
    """The PDF bytes of ``data`` under ``stamp``."""
    header, body = _grid(data, stamp.negative_number_style)
    lines = [*_stamp_lines(data, stamp), _Line(()), header, *body]
    return _document(_pages(lines, header), stamp)
