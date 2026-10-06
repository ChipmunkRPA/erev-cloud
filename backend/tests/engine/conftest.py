"""DG-TST-18: engine tests never request a database fixture (docs/dev-guide.md §9.3; D-78).

The check runs at collection, so a violating test fails the run before any fixture is set up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parent
DATABASE_FIXTURES = frozenset({"test_database", "db", "committed_db"})


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    errors = []
    for item in items:
        try:
            item.path.resolve().relative_to(ENGINE_ROOT)
        except ValueError:
            continue
        requested = sorted(DATABASE_FIXTURES.intersection(getattr(item, "fixturenames", ())))
        if requested:
            names = ", ".join(requested)
            errors.append(f"{item.nodeid}: engine tests may not request {names} (DG-TST-18)")
    if errors:
        raise pytest.UsageError("\n".join(errors))
