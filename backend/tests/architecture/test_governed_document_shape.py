"""DG-ARC-14: governed-document shape (dev-guide rev 1.45; GOV-MARK-1, lane F-ADM).

Two merge-time defects passed every gate and were caught only by inspection: a re-merge commit
that carried unresolved Git conflict hunks in ``docs/04-DATA_MODEL.md`` (845e5a67, corrected at
255fd514), and a landing that glued two header rows of the same document onto one line
(``… L-03. || Inputs | …``, 05c30117). Neither ``make lint``, typecheck nor the governed-document
tests read the shape of a Markdown table. This module does, read-only:

- (a) no tracked text file (``git ls-files``; binaries skipped) holds a conflict-marker line —
  ``<<<<<<< ``, a bare ``=======`` or ``>>>>>>> `` at the start of a line;
- (b) every governed document's header table has exactly one row per line: every row line starts
  and ends with ``|``, holds no ``||`` outside code spans (two rows glued onto one line), and has
  the header row's cell count — cells are split on ``|`` outside backtick code spans, an escaped
  ``\\|`` is text (the Markdown table syntax the documents admit);
- (c) the revision-log table of each governed document likewise.

The width rule is the declared DG-ARC-14 contract (Codex packet production-20260920-1711): the
historical ENGINE_SPEC_B row 1.23 at b179900b / c0de02a1 — five cells under the four-cell header,
its intro paragraph in the fifth — is bracketed, holds no ``||``, and is exactly the shape the
guard exists for. A row of the wrong width is a defect of the row's owner; this lane reports it
and repairs only its own rows.

Findings name the file and the line. The check may legitimately fail against a main whose defect a
later landing repairs; this lane never edits main's documents from a worktree.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from support.architecture import ROOT

# The governed documents whose header and revision-log tables carry the build contract.
GOVERNED_DOCUMENTS: Final[tuple[str, ...]] = (
    "docs/02-PRD.md",
    "docs/03-REQUIREMENTS.md",
    "docs/04-DATA_MODEL.md",
    "docs/05-ARCHITECTURE.md",
    "docs/dev-guide.md",
    "docs/accounting/ENGINE_SPEC.md",
    "docs/accounting/ENGINE_SPEC_B.md",
    "docs/design/SCREENS_B.md",
)
# Built by concatenation so that this module never holds a marker at the start of a line.
_OURS: Final = "<" * 7 + " "
_SEPARATOR: Final = "=" * 7
_THEIRS: Final = ">" * 7 + " "
_MARKER: Final = re.compile(
    "^(" + re.escape(_OURS) + "|" + re.escape(_SEPARATOR) + "$|" + re.escape(_THEIRS) + ")"
)
_REVISION_LOG: Final = re.compile(r"^(\*\*Revision log\*\*|#{2,3} Revision log)\s*$")
_CODE_SPAN: Final = re.compile(r"`[^`]*`")
_BINARY_SUFFIXES: Final = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".woff",
        ".woff2",
        ".ttf",
        ".zip",
        ".gz",
        ".pyc",
    }
)


def tracked_files() -> list[str]:
    """Repository-relative paths of every tracked file (``git ls-files``)."""
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    return sorted(name.decode("utf-8") for name in output.split(b"\0") if name)


def _is_text(path: Path) -> bool:
    if path.suffix.lower() in _BINARY_SUFFIXES or not path.is_file():
        return False
    with path.open("rb") as handle:
        return b"\0" not in handle.read(8192)


def conflict_marker_findings(name: str, text: str) -> list[str]:
    """``<file>:<line>: <marker>`` for every conflict-marker line of ``text``."""
    return [
        f"{name}:{number}: {line[:40]}"
        for number, line in enumerate(text.split("\n"), start=1)
        if _MARKER.match(line)
    ]


# --- table shape ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TableRow:
    number: int  # 1-based line number
    line: str

    def bracketed(self) -> bool:
        """A row line starts and ends with ``|``."""
        body = self.line.strip()
        return body.startswith("|") and body.endswith("|")

    def cells(self) -> list[str]:
        """The cells of the row: split on ``|`` outside backtick code spans; ``\\|`` is text."""
        body = self.line.strip()
        if body.startswith("|"):
            body = body[1:]
        if body.endswith("|") and not body.endswith("\\|"):
            body = body[:-1]
        cells: list[str] = []
        current: list[str] = []
        in_code = False
        index = 0
        while index < len(body):
            char = body[index]
            if char == "\\" and index + 1 < len(body) and body[index + 1] == "|":
                current.append("|")
                index += 2
                continue
            if char == "`":
                in_code = not in_code
            if char == "|" and not in_code:
                cells.append("".join(current))
                current = []
            else:
                current.append(char)
            index += 1
        cells.append("".join(current))
        return cells

    def glued(self) -> bool:
        """``||`` outside code spans: two rows glued onto one line."""
        return "||" in _CODE_SPAN.sub("`x`", self.line).replace("\\|", "")


def _table_at(lines: list[str], start: int) -> list[TableRow]:
    """The table rows from ``lines[start]`` (0-based) while lines keep starting with ``|``."""
    rows: list[TableRow] = []
    index = start
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        rows.append(TableRow(index + 1, lines[index]))
        index += 1
    return rows


def header_table(text: str) -> list[TableRow]:
    """The first table of the document (the header table)."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("|")), None)
    return [] if start is None else _table_at(lines, start)


def revision_log_table(text: str) -> list[TableRow]:
    """The table that follows the ``Revision log`` heading (bold or ``##``/``###``)."""
    lines = text.split("\n")
    heading = next((i for i, line in enumerate(lines) if _REVISION_LOG.match(line)), None)
    if heading is None:
        return []
    start = next(
        (i for i in range(heading + 1, len(lines)) if lines[i].startswith("|")),
        None,
    )
    return [] if start is None else _table_at(lines, start)


def table_shape_findings(name: str, label: str, rows: list[TableRow]) -> list[str]:
    """Rows of ``rows`` that are not one row per line — glued by ``||``, not bracketed by ``|``, or
    of a cell count unlike the header row's (the first row)."""
    if not rows:
        return [f"{name}: no {label} table"]
    width = len(rows[0].cells())
    findings: list[str] = []
    for row in rows:
        if row.glued():
            findings.append(f"{name}:{row.number}: {label} row glued with '||': {row.line[:80]}")
        elif not row.bracketed():
            findings.append(
                f"{name}:{row.number}: {label} row not bracketed by '|': {row.line[:80]}"
            )
        elif (count := len(row.cells())) != width:
            findings.append(
                f"{name}:{row.number}: {label} row has {count} cells, header has {width}: "
                f"{row.line[:80]}"
            )
    return findings


def governed_shape_findings(name: str, text: str) -> list[str]:
    return table_shape_findings(name, "header", header_table(text)) + table_shape_findings(
        name, "revision-log", revision_log_table(text)
    )


# --- the guard -----------------------------------------------------------------------------------


def _governed_texts() -> Iterator[tuple[str, str]]:
    for name in GOVERNED_DOCUMENTS:
        path = ROOT / name
        assert path.is_file(), f"governed document missing: {name}"
        yield name, path.read_text(encoding="utf-8")


def test_dg_arc_14_no_conflict_markers_in_tracked_text_files() -> None:
    """(a) No tracked text file holds a Git conflict-marker line."""
    findings: list[str] = []
    for name in tracked_files():
        path = ROOT / name
        if not _is_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings += conflict_marker_findings(name, text)
    assert findings == [], "\n".join(findings)


def test_dg_arc_14_governed_tables_one_row_per_line() -> None:
    """(b) header tables and (c) revision-log tables of the governed documents: one row per line."""
    findings: list[str] = []
    for name, text in _governed_texts():
        findings += governed_shape_findings(name, text)
    assert findings == [], "\n".join(findings)


# --- the guard catches the two historical shapes (synthetic, so the test never depends on git
# history) ----------------------------------------------------------------------------------------


def test_dg_arc_14_detects_conflict_markers() -> None:
    text = "\n".join(
        [
            "| Field | Value |",
            "|---|---|",
            _OURS + "HEAD",
            "| Revision | 1.38 (ours) |",
            _SEPARATOR,
            "| Revision | 1.43 (theirs) |",
            _THEIRS + "main",
        ]
    )
    assert conflict_marker_findings("docs/x.md", text) == [
        "docs/x.md:3: " + _OURS + "HEAD",
        "docs/x.md:5: " + _SEPARATOR,
        "docs/x.md:7: " + _THEIRS + "main",
    ]
    assert conflict_marker_findings("docs/x.md", "a\n=== not a marker ===\nb") == []


def test_dg_arc_14_detects_glued_rows() -> None:
    glued = "\n".join(
        [
            "# Title",
            "",
            "| Field | Value |",
            "|---|---|",
            "| Owner | someone |",
            "| Closes | C-04 (see §19). || Inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` |",
            "",
            "**Revision log**",
            "",
            "| Rev | Date | Change | Sections |",
            "|---|---|---|---|",
            "| 1.0 | 2026-09-12 | Initial | all |",
            "| 1.1 | 2026-09-13 | A cell with `a || b` code is fine | §1 |",
            "| 1.2 | 2026-09-14 | Two rows | §2 || 1.3 | 2026-09-15 | glued together | §3 |",
        ]
    )
    rows = glued.split("\n")
    assert governed_shape_findings("docs/x.md", glued) == [
        f"docs/x.md:6: header row glued with '||': {rows[5][:80]}",
        f"docs/x.md:14: revision-log row glued with '||': {rows[13][:80]}",
    ]
    clean = "\n".join(
        [
            "| Field | Value |",
            "|---|---|",
            "| Owner | a \\| b |",
            "",
            "## Revision log",
            "",
            "| Rev | Date | Change |",
            "|---|---|---|",
            "| 1.0 | 2026-09-12 | `x | y` inside code |",
        ]
    )
    assert governed_shape_findings("docs/y.md", clean) == []


def test_dg_arc_14_detects_the_fifth_cell_prose_row() -> None:
    """ABRIDGED fixture of the b179900b / c0de02a1 ENGINE_SPEC_B row 1.23 (line 43 at b179900b):
    five cells under the four-cell revision-log header, the intro paragraph in the fifth —
    bracketed, no ``||``, wrong width. The Change cell is shortened; the full original row is
    retained verbatim in the lane record ``docs/reviews/loop/prod/F-ADM.md`` (GOV-MARK-1 width
    correction) and in ``.run/f-adm-b/fail-first-govmark-width-b179900b.log``."""
    header = ["**Revision log**", "", "| Rev | Date | Author | Change |", "|---|---|---|---|"]
    fifth_cell = (
        "| 1.23 | 2026-09-20 | lane F-CLO (CLO-7c; supervisor ruling D-98 85) | "
        "**Applied (no figure "
        "change).** §15.2.7 gains S15-R-20a: the frozen dataset carries its row key "
        "(`line_code`) | "
        "This document specifies the engine's second half. |"
    )
    text = "\n".join(["| Field | Value |", "|---|---|", "| Owner | x |", "", *header, fifth_cell])
    assert governed_shape_findings("docs/e.md", text) == [
        f"docs/e.md:9: revision-log row has 5 cells, header has 4: {fifth_cell[:80]}"
    ]
    four_cells = (
        "| 1.23 | 2026-09-20 | lane F-CLO (CLO-7c; supervisor ruling D-98 85) | "
        "**Applied (no figure "
        "change).** §15.2.7 gains S15-R-20a: the frozen dataset carries its row key "
        "(`line_code`). "
        "This document specifies the engine's second half. |"
    )
    text = "\n".join(["| Field | Value |", "|---|---|", "| Owner | x |", "", *header, four_cells])
    assert governed_shape_findings("docs/e.md", text) == []


def test_dg_arc_14_cell_count_respects_code_spans_and_escaped_pipes() -> None:
    row = TableRow(1, "| 1.0 | 2026-09-12 | a cell with `x | y` and an escaped a \\| b pipe | §1 |")
    assert row.cells() == [
        " 1.0 ",
        " 2026-09-12 ",
        " a cell with `x | y` and an escaped a | b pipe ",
        " §1 ",
    ]
    assert TableRow(2, "| a | b || c |").cells() == [" a ", " b ", "", " c "]
