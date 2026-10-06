"""The report specifications of SCREENS_B §5.6 as the builder tests read them (BUILD_SPEC RPS-9 to
RPS-12; the pattern of ``tests/unit/reports/test_rpt32_rpt36_spec_crosscheck.py``).

``section`` is the text of one ``##### RPT-NN `<code>` …`` specification; ``grid`` the rows of its
first "Header | Field" table as ``(header, fields)`` — a row may name several fields (``Region,
Channel, Segment``); text in parentheses after a field is commentary, not a field; ``fields`` the
field names in grid order. A later specification edit or a builder column drift then fails the test
that compares them.
"""

from __future__ import annotations

import re
from typing import Final

from support.architecture import read

SCREENS_B: Final = "docs/design/SCREENS_B.md"
_HEADING: Final = "##### RPT-{number} `{code}`"
_PARENTHESES: Final = re.compile(r"\([^()]*\)")
_FIELD: Final = re.compile(r"`([a-z_0-9.]+)`")


def section(number: int, code: str) -> str:
    """The specification of report ``RPT-<number>`` ``code`` (to the next heading)."""
    text = read(SCREENS_B)
    heading = _HEADING.format(number=f"{number:02d}", code=code)
    assert heading in text, heading
    return re.split(r"\n#{4,5} ", text.split(heading, 1)[1], maxsplit=1)[0]


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def grid(number: int, code: str) -> list[tuple[str, tuple[str, ...]]]:
    """(header, fields) of each row of the specification's first "Header | Field" table."""
    rows: list[tuple[str, tuple[str, ...]]] = []
    inside = False
    for line in section(number, code).splitlines():
        if not line.startswith("|"):
            if inside:
                break
            continue
        cells = _cells(line)
        if not inside:
            inside = cells[:2] == ["Header", "Field"]
            continue
        if set(cells[0]) <= {"-", ":"}:
            continue
        names = tuple(_FIELD.findall(_PARENTHESES.sub("", cells[1])))
        assert names, line
        rows.append((cells[0], names))
    assert rows, (number, code)
    return rows


def fields(number: int, code: str) -> list[str]:
    """The field names of the grid in specification order."""
    return [name for _, names in grid(number, code) for name in names]
