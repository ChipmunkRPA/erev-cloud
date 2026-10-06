"""A report states an obligation's remainder through the reader, never from the stored columns
(dev-guide DG-CMD-13 rev 1.162; ENGINE_SPEC_B S15-R-01 and S15-R-08 rev 1.127; item
RPT-ASOF-FIGURES-1; supervisor ruling R-116 (c)).

``obligation_version.scheduled_amount`` and ``awaiting_trigger_amount`` are the amounts at the
version's effective date. A computation recognises revenue past that date, so a builder that adds
either column to posted revenue, or to the schedule lines after a date, states an amount twice:
the waterfall did, and the remaining performance obligation a lock froze read 79,780.82 for a
remainder of 20,164.38. The reports read an obligation at their date through
``erev_api.domain.reports.cuts``, the reader of the contract reads.

So no module of ``erev_api/domain/reports`` names either column of ``obligation_version`` or of
``contract_version`` in a statement. A builder that prints a version's own row at its effective
date selects the row whole (``contract_history.population``) and says which date it prints.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

REPORTS: Final = Path(__file__).resolve().parents[2] / "erev_api" / "domain" / "reports"
TABLES: Final = frozenset({"obligation_version", "contract_version"})
STORED: Final = frozenset({"scheduled_amount", "awaiting_trigger_amount"})


def findings(source: str, name: str) -> list[str]:
    """``<table>.c.<column>`` for a stored remainder column, by line."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in STORED
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "c"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id in TABLES
        ):
            found.append(f"{name}:{node.lineno}: {node.value.value.id}.c.{node.attr}")
    return found


def test_no_report_builder_selects_a_stored_remainder_column() -> None:
    modules = sorted(REPORTS.rglob("*.py"))
    assert len(modules) > 40, "the reports package was not found"
    found = [
        line
        for module in modules
        for line in findings(module.read_text(), str(module.relative_to(REPORTS)))
    ]
    assert found == [], "\n".join(found)


def test_the_check_sees_a_stored_column_and_leaves_a_whole_row_alone() -> None:
    select_one = (
        "rows = select(obligation_version.c.id, obligation_version.c.awaiting_trigger_amount)\n"
    )
    assert findings(select_one, "x.py") == ["x.py:1: obligation_version.c.awaiting_trigger_amount"]
    of_version = "total = select(func.sum(contract_version.c.scheduled_amount))\n"
    assert findings(of_version, "x.py") == ["x.py:1: contract_version.c.scheduled_amount"]
    whole_row = "rows = select(obligation_version, contract.c.external_id)\n"
    at_the_cut = "amount = at.awaiting + found.scheduled\n"
    assert findings(whole_row + at_the_cut, "x.py") == []
