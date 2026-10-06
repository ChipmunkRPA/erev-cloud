"""Gate marker placement (docs/dev-guide.md §9.2 DG-TST-07, DG-TST-09; ruling D-78).

``parity``, ``answer_key``, ``property``, ``pg`` and ``perf`` are applied through module-level
``pytestmark`` in their directories; a test carrying one of them lives nowhere else and carries no
``skip``, ``skipif`` or ``xfail``. The collection hook in ``backend/tests/conftest.py`` calls
:func:`check`, so a violation fails collection before ``-m`` deselection hides the test, and orders
items by :func:`collection_rank`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[1]
# Pure regressions fail before any database work (§9.1).
FIRST_AREAS = ("engine", "architecture")
# Marker → the directory under backend/tests that holds its modules (DG-TST-04, DG-TST-05).
HOMES: Mapping[str, str] = {
    "parity": "parity",
    "answer_key": "answer_keys",
    "property": "properties",
    "pg": "pg",
    "perf": "perf",
}
# DG-TST-02: the DG-ARC-07 and DG-ARC-09 parts of architecture/ may carry pg.
ALSO_ALLOWED: Mapping[str, frozenset[str]] = {"pg": frozenset({"architecture"})}
SKIP_MARKERS = frozenset({"skip", "skipif", "xfail"})


def area_of(path: Path, root: Path = TESTS_ROOT) -> str | None:
    """First directory under ``root`` that holds ``path``; None outside it or at its top level."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return None
    return parts[0] if len(parts) > 1 else None


def collection_rank(path: Path) -> int:
    area = area_of(path)
    return FIRST_AREAS.index(area) if area in FIRST_AREAS else len(FIRST_AREAS)


def _module_marker_names(item: pytest.Item) -> frozenset[str]:
    module = item.getparent(pytest.Module)
    marks = getattr(module.obj, "pytestmark", ()) if module is not None else ()
    if not isinstance(marks, list | tuple):
        marks = (marks,)
    return frozenset(str(getattr(mark, "name", "")) for mark in marks)


def errors(items: Iterable[pytest.Item], root: Path) -> list[str]:
    """Every DG-TST-07 and DG-TST-09 violation among ``items``, one line each."""
    found: list[str] = []
    for item in items:
        area = area_of(item.path, root)
        names = {mark.name for mark in item.iter_markers()}
        module_names = _module_marker_names(item)
        for marker, home in HOMES.items():
            if marker in names and area != home and area not in ALSO_ALLOWED.get(marker, ()):
                found.append(f"{item.nodeid}: {marker} tests live only under {home}/ (DG-TST-07)")
            if area == home and marker not in module_names:
                found.append(
                    f"{item.nodeid}: modules under {home}/ set pytestmark = pytest.mark.{marker}"
                    " (DG-TST-07)"
                )
            if marker in names and names & SKIP_MARKERS:
                found.append(
                    f"{item.nodeid}: {marker} tests may not carry skip, skipif or xfail (DG-TST-09)"
                )
    return found


def check(items: Iterable[pytest.Item], root: Path) -> None:
    """Collection hook body: raise ``pytest.UsageError`` listing every violation."""
    found = errors(items, root)
    if found:
        raise pytest.UsageError("\n".join(found))
