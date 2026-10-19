"""Independent retained legacy history reproduces the archived monthly journal outputs."""

import calendar
import csv
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from erev_api.domain.migration import legacy_db, parallel_legacy
from erev_api.domain.reports.parallel_comparison import Period
from erev_api.problems import Problem
from support.architecture import ROOT

GOLDEN = ROOT / "docs/legacy/golden"


def history() -> tuple[legacy_db.LegacyRow, ...]:
    with (GOLDEN / "14-full-delivery-2023-10-31/contract_live.csv").open() as source:
        return tuple(
            legacy_db.LegacyRow(index, dict(row))
            for index, row in enumerate(csv.DictReader(source), 1)
        )


def periods(month: int) -> tuple[Period, ...]:
    return tuple(
        Period(
            entity,
            "ASC606",
            "USD",
            f"FY2023-P{month:02d}",
            date(2023, month, 1),
            date(2023, month, calendar.monthrange(2023, month)[1]),
        )
        for entity in ("Mock Entity 1", "Mock Entity 2")
    )


MAPPING = {entity: entity for entity in ("Mock Entity 1", "Mock Entity 2")}


@pytest.mark.parametrize("month", range(1, 11))
def test_monthly_journals_match_independent_legacy_exports(month: int) -> None:
    result = parallel_legacy.snapshot(
        history(), source_id="retained-history", periods=periods(month), entity_mapping=MAPPING
    )
    actual: dict[str, tuple[Decimal, Decimal]] = {}
    for row in result.journals:
        debit, credit = actual.get(row.account, (Decimal(0), Decimal(0)))
        actual[row.account] = (debit + row.debit, credit + row.credit)
        assert row.source_rows and all("legacy-row:" in ref for ref in row.source_rows)
    expected: dict[str, tuple[Decimal, Decimal]] = {}
    with (GOLDEN / f"monthly/2023-{month:02d}/je_gross.csv").open() as source:
        for exported in csv.DictReader(source):
            account = str(int(Decimal(exported["Account"])))
            value = Decimal(exported["Amount"])
            debit, credit = expected.get(account, (Decimal(0), Decimal(0)))
            expected[account] = debit + max(value, Decimal(0)), credit - min(value, Decimal(0))
    assert actual == expected
    if month == 10:
        assert sum(row[0] for row in actual.values()) == Decimal("5043.84")
        assert sum(row[1] for row in actual.values()) == Decimal("5043.85")


def test_sqlite_history_balance_and_complete_period_coverage() -> None:
    rows = legacy_db.rows(ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db")
    result = parallel_legacy.snapshot(
        rows, source_id="file:step04", periods=(*periods(1), *periods(2)), entity_mapping=MAPPING
    )
    assert result.periods == frozenset(periods(1))
    contract = next(row for row in result.balances if row.contract == "Contract 2")
    assert contract.net_position == Decimal("-58.85")
    assert len(contract.source_rows) > 1  # Sum POB positions, not repeated contract totals.
    same = parallel_legacy.snapshot(
        reversed(rows),
        source_id="file:step04",
        periods=(*periods(1), *periods(2)),
        entity_mapping=MAPPING,
    )
    assert result == same
    changed = list(rows)
    changed[0] = replace(changed[0], values={**changed[0].values, "Memo 1": "Changed evidence"})
    assert (
        parallel_legacy.snapshot(
            changed,
            source_id="file:step04",
            periods=(*periods(1), *periods(2)),
            entity_mapping=MAPPING,
        ).sha256
        != result.sha256
    )


@pytest.mark.parametrize("fault", ["mapping", "duplicate", "currency", "book", "entity", "amount"])
def test_incomplete_or_unsupported_source_refuses(fault: str) -> None:
    rows = list(history())
    selected = periods(1)
    mapping = dict(MAPPING)
    if fault == "mapping":
        mapping.pop("Mock Entity 2")
    elif fault == "duplicate":
        rows.append(rows[0])
    elif fault == "currency":
        selected = tuple(replace(p, currency="JPY") for p in selected)
    elif fault == "book":
        selected = tuple(replace(p, book_code="IFRS15") for p in selected)
    elif fault == "entity":
        selected = tuple(replace(p, entity_code="UNMAPPED") for p in selected)
    else:
        rows[0] = replace(rows[0], values={**rows[0].values, "Current Rev Rec": "NaN"})
    with pytest.raises(Problem):
        parallel_legacy.snapshot(
            rows, source_id="retained-history", periods=selected, entity_mapping=mapping
        )
