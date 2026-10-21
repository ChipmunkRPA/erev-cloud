"""PDF outputs with the RV-07 stamp and a page footer (SCREENS_B RV-02, RV-07; 03 REQ-RPT-002;
BUILD_SPEC RPS-2).

A PDF 1.4 document written directly: A4 landscape pages, the standard Helvetica fonts with
WinAnsiEncoding, uncompressed content streams and no creation date. The first page opens with the
stamp lines (report name and version, run number, entity, book, as of, source, engine release, run
by, run time, rows, output SHA-256, every parameter, the control totals and tie-outs), then the grid
header and the rows; a page that continues the grid repeats its header. Every page footer reads
"Run <run no> · page <n> of <m>". Single-table reports use compact layout when content fits;
otherwise they use the chapter layout with wrapped text and horizontal column groups instead of
truncating cells.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from erev_api.domain.reports.outputs import (
    LayoutColumn,
    ReportData,
    RunStamp,
    display_text,
    display_timestamp,
    layout,
    parameter_text,
    rpo_exemptions,
    total_text,
)
from erev_api.domain.reports.outputs.xlsx import WorkbookChapter, validate_chapters

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
    rule: bool = False


def _fit(text: str, width: float) -> str:
    limit = max(int(width // CHARACTER_WIDTH), 1)
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + ELLIPSIS


def _stamp_lines(data: ReportData, stamp: RunStamp, *, wrapped: bool = False) -> list[_Line]:
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
            if key != "exemption_changes"
        ),
    ]
    if "exemption_changes" in data.control_totals:
        details = rpo_exemptions.records(data.control_totals["exemption_changes"])
        if details:
            texts.extend(((rpo_exemptions.TITLE, True), (rpo_exemptions.BASIS, False)))
        for detail in details:
            texts.append(
                (
                    f"{detail['contract']} / {detail['obligation']} / {detail['entity']}",
                    True,
                )
            )
            for endpoint in ("opening", "closing"):
                amount = total_text(
                    {
                        "amount": detail[f"{endpoint}_excluded"],
                        "currency": detail["currency"],
                    },
                    style,
                )
                rule = rpo_exemptions.cell(detail, f"{endpoint}_rule")
                texts.append(
                    (
                        f"{endpoint.title()} excluded RPO: {amount}; "
                        f"{detail[f'{endpoint}_date']}; {rule}",
                        False,
                    )
                )
            movement = total_text(
                {
                    "amount": detail["movement"],
                    "currency": detail["currency"],
                },
                style,
            )
            texts.append((f"Exemption movement: {movement}", False))
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
    for item in data.tie_out_results:
        for detail in item.get("details", ()):
            texts.append(("; ".join(f"{key}: {value}" for key, value in detail.items()), False))
    usable = PAGE_WIDTH - 2 * MARGIN
    return [
        _Line(((MARGIN, part),), bold=bold)
        for text, bold in texts
        for part in (_wrap_text(text, usable) if wrapped else [_fit(text, usable)])
    ]


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
        if line.rule:
            parts.append(
                f"0.65 G {MARGIN} {y + 4:.2f} m {PAGE_WIDTH - MARGIN} {y + 4:.2f} l S 0 G\n".encode(
                    "ascii"
                )
            )
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
    """Keep the compact grid only when every value and stamp fits without clipping."""
    header, body = _grid(data, stamp.negative_number_style)
    stamp_lines = _stamp_lines(data, stamp)
    columns = layout(data)
    original = [
        [item.header for item in columns],
        *[
            [
                display_text(
                    item.column, item.part, row.get(item.column.key), stamp.negative_number_style
                )
                for item in columns
            ]
            for row in data.rows
            if columns
        ],
    ]
    compact = [header, *body]
    fits = stamp_lines == _stamp_lines(data, stamp, wrapped=True) and all(
        [text for _, text in line.cells] == expected
        and all(
            x + _measure(text)
            <= (
                line.cells[index + 1][0] - COLUMN_GAP
                if index + 1 < len(line.cells)
                else PAGE_WIDTH - MARGIN
            )
            for index, (x, text) in enumerate(line.cells)
        )
        for line, expected in zip(compact, original, strict=True)
    )
    if not fits:
        return _document(_chapter_table_pages(data, stamp, stamp.report_name, ()), stamp)
    lines = [*stamp_lines, _Line(()), header, *body]
    return _document(_pages(lines, header), stamp)


def _measure(text: str) -> float:
    """Conservative Helvetica/Helvetica-Bold advances, including WinAnsi fallback glyphs.

    Letters/symbols reserve a full em; digits and ASCII punctuation reserve at least their
    maximum advance in either standard face. No external font/runtime dependency is needed.
    """
    return FONT_SIZE * sum(
        0.6 if ch.isascii() and ch.isdigit() else 0.4 if ch in " .,:;!|()[]-'" else 1.0
        for ch in text
    )


def _wrap_text(text: str, width: float) -> list[str]:
    remaining = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    result = []
    while remaining:
        length = 0
        advance = 0.0
        for ch in remaining:
            size = _measure(ch)
            if length and advance + size > width:
                break
            advance += size
            length += 1
        if length < len(remaining):
            space = remaining.rfind(" ", 0, length + 1)
            if space > 0:
                length = space
            else:
                boundary = max(remaining.rfind("-", 0, length), remaining.rfind("/", 0, length))
                if boundary > 0:
                    length = boundary + 1
        result.append(remaining[:length].rstrip())
        remaining = remaining[length:].lstrip()
    return result or [""]


def _table_bands(
    data: ReportData, style: str
) -> tuple[tuple[LayoutColumn, ...], list[list[str]], list[float], list[list[int]]]:
    columns = tuple(
        replace(item, header="Currency") if item.part == "currency" else item
        for item in layout(data)
    )
    texts = [
        [display_text(c.column, c.part, row.get(c.column.key), style) for c in columns]
        for row in data.rows
    ]
    widths = [
        (
            max(_measure("Currency"), *(_measure(row[i]) for row in texts))
            if c.part == "currency"
            else min(
                220.0,
                max(90.0, min(_measure(c.header), 150.0), *(_measure(row[i]) for row in texts)),
            )
        )
        + COLUMN_GAP
        for i, c in enumerate(columns)
    ]
    usable = PAGE_WIDTH - 2 * MARGIN - max(36.0, _measure(str(data.row_count)) + COLUMN_GAP)
    groups: list[list[int]] = []
    for i, column in enumerate(columns):
        # Keep mixed-currency value/code together, and adjacent period/QTD comparison pairs.
        key = column.column.key.removeprefix("period:").removeprefix("quarter:")
        previous = columns[groups[-1][0]].column.key if groups else ""
        previous = previous.removeprefix("period:").removeprefix("quarter:")
        if (
            groups
            and key == previous
            and sum(widths[j] for j in groups[-1]) + widths[i] <= usable - 226
        ):
            groups[-1].append(i)
        else:
            groups.append([i])
    if not groups:
        return columns, texts, widths, [[]]
    # Repeat the first logical field for context, plus the ordinal on every physical row.
    anchor = groups[0]
    anchor_width = sum(widths[i] for i in anchor)
    bands = [list(anchor)]
    used = anchor_width
    for group in groups[1:]:
        weight = sum(widths[i] for i in group)
        if used + weight > usable and len(bands[-1]) > len(anchor):
            bands.append(list(anchor))
            used = anchor_width
        if used + weight > usable:
            # An unusually large first field/mixed-currency pair must not squeeze out values.
            bands.append([])
            used = 0
        bands[-1].extend(group)
        used += weight
    return columns, texts, widths, bands


def _wrapped_grid_lines(
    values: Sequence[str], widths: Sequence[float], *, bold: bool = False
) -> list[_Line]:
    wrapped = [
        _wrap_text(value, width - COLUMN_GAP) for value, width in zip(values, widths, strict=True)
    ]
    positions = []
    x = float(MARGIN)
    for width in widths:
        positions.append(x)
        x += width
    return [
        _Line(
            tuple(
                (positions[i], parts[n] if n < len(parts) else "")
                for i, parts in enumerate(wrapped)
            ),
            bold=bold,
            grid=not bold,
        )
        for n in range(max((len(parts) for parts in wrapped), default=1))
    ]


def _chapter_table_pages(
    data: ReportData, stamp: RunStamp, title: str, notes: Sequence[str]
) -> list[list[_Line]]:
    usable = PAGE_WIDTH - 2 * MARGIN
    prefix = [_Line(((MARGIN, part),), bold=True) for part in _wrap_text(title, usable)]
    prefix.extend(_stamp_lines(data, stamp, wrapped=True))
    prefix.extend(_Line(((MARGIN, part),)) for note in notes for part in _wrap_text(note, usable))
    prefix.append(_Line(()))
    pages = _pages(prefix, _Line(()))
    columns, texts, widths, bands = _table_bands(data, stamp.negative_number_style)
    if not columns:
        return pages
    capacity = int((PAGE_HEIGHT - 2 * MARGIN) // LINE_HEIGHT)
    for band_no, band in enumerate(bands, 1):
        caption = _wrap_text(title, usable)
        if len(caption) > 2:
            caption = [f"Table from run {stamp.report_run_no}"]
        heading = [_Line(((MARGIN, part),), bold=True) for part in caption]
        heading.append(
            _Line(
                (
                    (
                        MARGIN,
                        f"Column group {band_no} of {len(bands)} - Row numbers match across groups",
                    ),
                )
            )
        )
        band_widths = [
            max(36.0, _measure(str(data.row_count)) + COLUMN_GAP),
            *(widths[i] for i in band),
        ]
        grid_header = _wrapped_grid_lines(
            ["Row", *(columns[i].header for i in band)], band_widths, bold=True
        )
        if len(grid_header) > capacity // 2:
            # Extremely long labels get a full-width legend, never an over-height page header.
            legend = [_Line(((MARGIN, f"Column group {band_no} definitions"),), bold=True)]
            for i in band:
                legend.extend(
                    _Line(((MARGIN, part),))
                    for part in _wrap_text(f"Column {i + 1}: {columns[i].header}", usable)
                )
            pages.extend(_pages(legend, _Line(())))
            grid_header = _wrapped_grid_lines(
                ["Row", *(f"Column {i + 1}" for i in band)], band_widths, bold=True
            )
        heading.extend(grid_header)
        heading.append(_Line((), rule=True))
        first_height = (
            max((len(_wrap_text(texts[0][i], widths[i] - COLUMN_GAP)) for i in band), default=1)
            if texts
            else 1
        )
        if (
            band_no > 1
            or len(pages[-1]) + len(heading) + min(first_height, capacity - len(heading)) > capacity
        ):
            pages.append([])
        pages[-1].extend(heading)
        if not texts:
            pages[-1].append(_Line(((MARGIN, "No rows"),)))
        for ordinal, values in enumerate(texts, 1):
            block = _wrapped_grid_lines([str(ordinal), *(values[i] for i in band)], band_widths)
            # Keep ordinary rows together. Oversize narrative rows continue under the same ordinal.
            if len(block) <= capacity - len(heading) and len(pages[-1]) + len(block) > capacity:
                pages.append(list(heading))
            for line_no, line in enumerate(block):
                continued = len(pages[-1]) >= capacity
                if continued:
                    pages.append(list(heading))
                label = str(ordinal) if line_no == 0 or continued else ""
                pages[-1].append(_Line(((float(MARGIN), label), *line.cells[1:]), grid=True))
        if len(pages[-1]) < capacity:
            pages[-1].append(_Line(()))
    return pages


def render_pdf_chapters(chapters: tuple[WorkbookChapter, ...], stamp: RunStamp) -> bytes:
    """Full-text chapter tables, horizontal bands and repeated context on continuation pages."""
    validate_chapters(chapters)
    table_pages: list[list[_Line]] = []
    entries: list[tuple[str, int]] = []
    for chapter in chapters:
        for table in chapter.tables:
            title = f"{chapter.key}. {chapter.title} / {table.title}"
            entries.append((title, len(table_pages)))
            table_pages.extend(
                _chapter_table_pages(
                    table.data,
                    table.stamp,
                    title,
                    ("Omitted" if table.omitted else "Included", *table.notes),
                )
            )
    index_header = _Line(((MARGIN, "Contents"),), bold=True)

    def index_lines(offset: int) -> list[_Line]:
        lines = [index_header, _Line(((MARGIN, f"Run {stamp.report_run_no}"),))]
        for title, page in entries:
            for n, part in enumerate(_wrap_text(title, PAGE_WIDTH - 2 * MARGIN - 60)):
                cells: tuple[tuple[float, str], ...] = ((float(MARGIN), part),)
                if n == 0:
                    cells += ((PAGE_WIDTH - MARGIN - 45.0, str(offset + page + 1)),)
                lines.append(_Line(cells))
        return lines

    index_count = len(_pages(index_lines(0), index_header))
    return _document([*_pages(index_lines(index_count), index_header), *table_pages], stamp)
