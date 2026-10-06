"""Governed-document revision tables are consistent with their headers (docs lane rule
REVISION-ROW-RULE-for-P1, 2026-09-20; P1 follow-up after the duplicate rows of 2026-09-19 — 05 1.6
and dev-guide 1.9, numbered onto existing revisions with another date — were repaired at COMMIT 19).

Parsing follows the docs lane's generator: table cells are split on unescaped pipes; the header
entries are the second cell of the first table row whose first cell is exactly ``Revision`` (a
semicolon-separated list of ``X.Y (date, description)`` entries; the number before each opening
parenthesis is taken); a log row is any table row whose first cell is ``x.y`` and whose second cell
is an ISO date, whatever its column count. Revision numbers compare by integer components
(1.9 < 1.10 < 1.21), never as floats. Assertions: (a) header numbers unique and strictly
descending; (b) every log row whose number is at least the oldest header entry has a header entry
— the headers end with "see the Revision log" and omit the earliest revisions (1.0 to 1.2 or 1.3),
so the rule is bounded below by the oldest header entry; (c) rows sharing a number share a date
(the one-revision-many-rows convention of 2026-09-12 passes; COMMIT 20 annotates it and renumbers
nothing); (d) the first header number equals the maximum log-row number. No allow-list and no
tolerated gap: the 04-DATA_MODEL 1.9 header entry (D-90b) that was missing on main 7b4ba7f is a
defect the docs lane repairs at COMMIT 20, which precedes this test's merge (supervisor ruling
2026-09-20). SCREENS / SCREENS_B carry a log but no ``Revision`` header cell and are out of scope.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOVERNED_DOCUMENTS = (
    "docs/02-PRD.md",
    "docs/03-REQUIREMENTS.md",
    "docs/04-DATA_MODEL.md",
    "docs/05-ARCHITECTURE.md",
    "docs/dev-guide.md",
    "docs/accounting/ENGINE_SPEC.md",
    "docs/accounting/ENGINE_SPEC_B.md",
    "docs/build-spec/00-header.md",
)
NUMBER = re.compile(r"^\d+\.\d+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEADER_ENTRY = re.compile(r"(\d+\.\d+) \(")


def revision_key(number: str) -> tuple[int, ...]:
    return tuple(int(part) for part in number.split("."))


def table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped)[1:-1]]


def header_revisions(text: str) -> list[str]:
    """Revision numbers of the first ``| Revision | … |`` table row, in listing order."""
    for line in text.splitlines():
        cells = table_cells(line)
        if len(cells) > 1 and cells[0] == "Revision":
            return HEADER_ENTRY.findall(cells[1])
    return []


def log_rows(text: str) -> list[tuple[str, str, int]]:
    """``(number, date, line)`` for every revision-log row, whatever its column count."""
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        cells = table_cells(line)
        if len(cells) > 1 and NUMBER.match(cells[0]) and DATE.match(cells[1]):
            rows.append((cells[0], cells[1], number))
    return rows


def revision_problems(relative: str, text: str) -> list[str]:
    """The (a) to (d) findings for one document; empty when it is consistent."""
    header, rows = header_revisions(text), log_rows(text)
    problems: list[str] = []
    if not header:
        return [f"{relative}: no `| Revision |` header row"]
    if not rows:
        return [f"{relative}: no revision-log rows"]
    if len(set(header)) != len(header):
        problems.append(f"{relative}: header revision numbers repeat: {header}")
    keys = [revision_key(number) for number in header]
    if any(earlier <= later for earlier, later in zip(keys, keys[1:], strict=False)):
        problems.append(
            f"{relative}: header revision numbers are not strictly descending: {header}"
        )
    oldest = min(keys)
    for number in sorted({n for n, _, _ in rows}, key=revision_key):
        if revision_key(number) >= oldest and number not in header:
            problems.append(f"{relative}: log row {number} has no header entry")
    dates: dict[str, set[str]] = defaultdict(set)
    for number, date, _ in rows:
        dates[number].add(date)
    for number, seen in sorted(dates.items(), key=lambda item: revision_key(item[0])):
        if len(seen) > 1:
            problems.append(
                f"{relative}: rows numbered {number} carry several dates {sorted(seen)}"
            )
    newest = max((n for n, _, _ in rows), key=revision_key)
    if revision_key(header[0]) != revision_key(newest):
        problems.append(f"{relative}: header leads with {header[0]} but the log reaches {newest}")
    return problems


def test_governed_documents_are_revision_consistent() -> None:
    findings = []
    for relative in GOVERNED_DOCUMENTS:
        findings += revision_problems(relative, (ROOT / relative).read_text(encoding="utf-8"))
    assert findings == []


def test_revision_numbers_compare_by_integer_components() -> None:
    assert revision_key("1.9") < revision_key("1.10") < revision_key("1.21")
    assert sorted(["1.10", "1.9", "1.21"], key=revision_key) == ["1.9", "1.10", "1.21"]


def test_the_convention_groups_pass_and_each_defect_shape_fails() -> None:
    # The one-revision-many-rows convention (05 and dev-guide 1.1 / 1.2 of 2026-09-12, several rows
    # each) passes as it stands; the fail-first shapes are scratch copies of dev-guide.md.
    text = (ROOT / "docs/dev-guide.md").read_text(encoding="utf-8")
    assert revision_problems("docs/dev-guide.md", text) == []
    groups = defaultdict(int)
    for number, _, _ in log_rows(text):
        groups[number] += 1
    assert groups["1.1"] > 1 and groups["1.2"] > 1
    header = header_revisions(text)
    newest = header[0]
    # COMMIT 19 reverted: the newest header entry removed while its log row stays → (b) and (d).
    reverted = text.replace(f"| Revision | {newest} (", "| Revision | (", 1)
    reverted = re.sub(r"\| Revision \| \([^;]*; ", "| Revision | ", reverted, count=1)
    assert newest not in header_revisions(reverted)
    problems = revision_problems("docs/dev-guide.md", reverted)
    assert any(f"log row {newest} has no header entry" in p for p in problems), problems
    assert any("header leads with" in p for p in problems), problems
    # A row numbered onto an existing revision with another date (tonight's P1 defect) → (c).
    existing = header[1]
    duplicated = (
        text + f"\n| {existing} | 2099-01-01 | numbered onto an existing revision | x | y |\n"
    )
    problems = revision_problems("docs/dev-guide.md", duplicated)
    assert problems == [
        f"docs/dev-guide.md: rows numbered {existing} carry several dates "
        f"{sorted({'2099-01-01'} | {d for n, d, _ in log_rows(text) if n == existing})}"
    ], problems
    # A header that repeats or does not descend → (a).
    swapped = text.replace(f"| Revision | {newest} (", f"| Revision | {existing} (", 1)
    swapped = swapped.replace(f"; {existing} (", f"; {newest} (", 1)
    problems = revision_problems("docs/dev-guide.md", swapped)
    assert any("not strictly descending" in p for p in problems), problems
