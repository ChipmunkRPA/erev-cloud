"""Reading the operational guides in tests (PHASES BS-D-13; BUILD_SPEC FND-18, DEP-6, DEP-7).

Shared by ``tests/unit/test_guides.py`` (the FND-18 and FR-M guide contracts, at the path those
items name) and ``tests/unit/docs/test_guides.py`` (the DEP-6, DEP-7, DMO-11 and PRF-6 tests, at the
path BS4-D-17 and those items name): headings outside fenced code, and the text of one section.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUIDES = ROOT / "docs" / "guides"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def headings(text: str) -> list[tuple[int, str]]:
    """``(level, title)`` of every Markdown heading of ``text`` outside fenced code blocks."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and (match := HEADING.match(line)):
            found.append((len(match.group(1)), match.group(2)))
    return found


def section(name: str, title: str) -> str:
    """The text under heading ``title`` of guide ``name``, up to the next heading of its level or
    higher, with whitespace collapsed."""
    lines = (GUIDES / name).read_text(encoding="utf-8").splitlines()
    collected: list[str] = []
    level = 0
    for line in lines:
        match = HEADING.match(line)
        if level and match and len(match.group(1)) <= level:
            break
        if level:
            collected.append(line)
        elif match and match.group(2) == title:
            level = len(match.group(1))
    assert level, f"{name}: {title}"
    return " ".join(" ".join(collected).split())


def titles(name: str) -> set[str]:
    """The titles of the level-2 and deeper headings of guide ``name``."""
    text = (GUIDES / name).read_text(encoding="utf-8")
    return {title for level, title in headings(text) if level >= 2}
