"""RPT-41 ``migration_reconciliation`` report rendering, the pure part (SCREENS_B §5.6.7 RPT-41; 04
T-MIG-03; BUILD_SPEC LMG-3 ``test_report_run_migration_reconciliation`` control totals and row
key shape; PRD BR-MIG-02). ``report_data`` renders T-MIG-03 lines without a run, so no database.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.migration import legacy_db, reconciliation, repository
from erev_api.domain.migration.reconciliation import DeviationIndex
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import migration_reconciliation as report
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from sqlalchemy.dialects import postgresql
from support.architecture import ROOT

SOURCE = {
    ("Contract 1", None, "POB_COUNT"): Fraction(4),
    ("Contract 1", None, "TRANSACTION_PRICE"): Fraction(1300),
    ("Contract 1", None, "REVENUE_CUM"): Fraction("295.6888"),
    ("Contract 1", "POB #1", "ALLOCATION"): Fraction("322.1010901883"),
    ("Contract 1", "POB #1", "REVENUE_CUM"): Fraction("123.45"),
    ("Contract 3", "POB #5", "ALLOCATION"): Fraction(0),
}
EREV = {
    **SOURCE,
    ("Contract 1", "POB #1", "REVENUE_CUM"): Fraction("123.46"),  # unexplained 0.01
    ("Contract 3", "POB #5", "ALLOCATION"): Fraction("1268.1139"),  # DEV-052
}


def _index() -> DeviationIndex:
    # a documented applicable difference for the synthetic key: legacy 0 → corrected 1,268.1139
    return DeviationIndex(
        {
            ("Contract 3", "POB #5", "ALLOCATION"): reconciliation.Deviation(
                "DEV-052", Fraction(0), Fraction("1268.1139")
            )
        }
    )


def _lines() -> tuple[reconciliation.Line, ...]:
    return reconciliation.lines(SOURCE, EREV, _index())


def test_report_rows_columns_and_control_totals() -> None:
    lines = tuple(
        line if not line.needs_exception else replace(line, exception_ref="EXC-1")
        for line in _lines()
    )
    data = report.report_data(lines)
    assert [column.key for column in data.columns] == [
        "contract_external_id",
        "obligation_key",
        "measure",
        "source_value",
        "erev_value",
        "difference",
        "tolerance",
        "is_within_tolerance",
        "deviation_ref",
        "exception_item_id",
    ]
    assert [row["row_key"] for row in data.rows] == [
        "line:Contract 1::POB_COUNT",
        "line:Contract 1::TRANSACTION_PRICE",
        "line:Contract 1::REVENUE_CUM",
        "line:Contract 1:POB #1:ALLOCATION",
        "line:Contract 1:POB #1:REVENUE_CUM",
        "line:Contract 3:POB #5:ALLOCATION",
    ]
    contract_level = data.rows[1]
    assert contract_level["obligation_key"] == "Contract level"
    assert contract_level["measure"] == "Transaction price"
    assert contract_level["source_value"] == "1300" and contract_level["tolerance"] == "0.0001"
    assert contract_level["is_within_tolerance"] == "Yes"
    unexplained = data.rows[4]
    assert unexplained["difference"] == "0.01" and unexplained["is_within_tolerance"] == "No"
    assert unexplained["deviation_ref"] is None and unexplained["exception_item_id"] == "EXC-1"
    explained = data.rows[5]
    assert explained["deviation_ref"] == "DEV-052" and explained["exception_item_id"] is None
    assert explained["difference"] == "1268.1139" and explained["measure"] == "Allocation"
    assert data.control_totals == {
        "contracts": 0,  # the pure path without a T-MIG-01 profile (SCREENS_B rev 1.13 KPI totals)
        "legacy_obligation_rows": 0,
        "line_count": 6,
        "differences_above_tolerance": 2,
        "explained": 1,
        "unexplained": 1,
    }
    assert data.tie_out_results == (
        {"code": "TO_MIGRATION_UNEXPLAINED_ZERO", "result": "FAIL", "expected": 0, "actual": 1},
    )


def test_only_differences_keeps_the_totals() -> None:
    data = report.report_data(_lines(), only_differences=True)
    assert [row["row_key"] for row in data.rows] == [
        "line:Contract 1:POB #1:REVENUE_CUM",
        "line:Contract 3:POB #5:ALLOCATION",
    ]
    assert data.control_totals["line_count"] == 6


def test_pass_when_every_difference_is_explained() -> None:
    erev = {
        **EREV,
        ("Contract 1", "POB #1", "REVENUE_CUM"): SOURCE[("Contract 1", "POB #1", "REVENUE_CUM")],
    }
    data = report.report_data(reconciliation.lines(SOURCE, erev, _index()))
    assert data.control_totals["unexplained"] == 0
    assert data.tie_out_results[0]["result"] == "PASS"


def test_exact_text() -> None:
    # Codex R3 (PRODUCTION-F-LMG-SLICE1-INDEPENDENT-ed5173f, D-98 candidate 44), exact input: the
    # difference 0.00010000000004 is above tolerance ("Within tolerance" No) and must render as
    # itself, not quantised to "0.0001" (SCREENS_B §5.6.7: exact decimal text, trailing zeros
    # trimmed).
    diff = Fraction(Decimal("0.00010000000004"))
    assert report.exact_text(diff) == "0.00010000000004"
    assert report.exact_text(Fraction(12345, 100)) == "123.45"
    key = ("SYN-C1", "P1", "REVENUE_CUM")
    data = report.report_data(reconciliation.lines({key: Fraction(1)}, {key: Fraction(1) + diff}))
    (row,) = data.rows
    assert (row["source_value"], row["erev_value"], row["difference"], row["tolerance"]) == (
        "1",
        "1.00010000000004",
        "0.00010000000004",
        "0.0001",
    )
    assert row["is_within_tolerance"] == "No" and data.tie_out_results[0]["result"] == "FAIL"
    assert report.exact_text(Fraction(1300)) == "1300"
    assert report.exact_text(Fraction("295.6888")) == "295.6888"
    assert report.exact_text(Fraction(-1, 100)) == "-0.01"
    assert report.exact_text(Fraction(0)) == "0"
    assert report.exact_text(Fraction(1, 1024)) == "0.0009765625"
    assert report.exact_text(Fraction(-1, 20000)) == "-0.00005"
    with pytest.raises(ValueError):  # not a finite decimal; never rounded silently
        report.exact_text(Fraction(1, 3))
    assert report.MEASURE_LABELS["NET_POSITION"] == "Billed less recognized"
    assert report.CODE == "migration_reconciliation"


class _Result:
    def __init__(self, rows: tuple[Any, ...] = ()) -> None:
        self._rows = rows

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return len(self._rows)


class _Session:
    """Serves queued results in order; records the compiled statements (no database)."""

    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        self.calls.append(str(statement.compile(dialect=postgresql.dialect())))
        return self.results.pop(0) if self.results else _Result()


def _uow(*results: _Result) -> tuple[UnitOfWork, _Session]:
    session = _Session(*results)
    uow = SimpleNamespace(
        session=session,
        now=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        principal=SimpleNamespace(id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=UUID(int=1)),
    )
    return cast(UnitOfWork, uow), session


def _params(**values: Any) -> ReportParams:
    return ReportParams("migration_reconciliation", 1, values, (), known_at=cast(Any, None))


MIGRATION = UUID(int=21)
EXCEPTION = UUID(int=7)
FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"


def _stored_rows(uow: UnitOfWork) -> list[dict[str, Any]]:
    """T-MIG-03 rows of the WLD-X-27 world as the reconciliation stores them: the shipped legacy
    values reconciled against themselves, with one seeded unexplained difference (Contract 1
    POB #1 REVENUE_CUM +0.01) linked to an exception item."""
    source = reconciliation.legacy_values(legacy_db.latest_rows(legacy_db.rows(FIXTURE)))
    erev = dict(source)
    erev[("Contract 1", "POB #1", "REVENUE_CUM")] += Fraction(1, 100)
    lines = reconciliation.lines(source, erev)
    seeded = next(line for line in lines if line.needs_exception)
    return [repository.line_values(uow, MIGRATION, line, {seeded.key: EXCEPTION}) for line in lines]


def test_rpt41_is_registered_in_the_framework() -> None:
    # SCREENS_B RPT-41 "Reader and registration" (rev 1.13): registered under the report code, the
    # rows reader bound to the T-MIG-03 read, the pending reader retired.
    assert framework.BUILDERS[report.CODE] is report.build
    assert report.rows_reader is repository.reconciliation_rows
    assert not hasattr(report, "pending_rows_reader")


def test_build_reads_the_batch_then_the_lines_and_binds_the_kpis() -> None:
    # The run reads the T-MIG-01 row (profile → the two KPI totals), the T-MIG-03 rows (136 lines
    # of WLD-X-27) and the exception numbers of the linked items; exact values are rendered as
    # stored (D-98 89), the unexplained line carries its exception number.
    uow, _ = _uow()
    stored = _stored_rows(uow)
    batch = {
        "id": MIGRATION,
        "status": "RECONCILED",
        "profile": {"contracts": 4, "legacy_pob_rows": 16},
    }
    uow, session = _uow(
        _Result((batch,)),
        _Result(tuple(stored)),
        _Result(({"id": EXCEPTION, "exception_no": "EXC-000007"},)),
    )
    data = report.build(uow, _params(migration_id=str(MIGRATION)))
    assert data.control_totals == {
        "contracts": 4,
        "legacy_obligation_rows": 16,
        "line_count": 136,
        "differences_above_tolerance": 1,
        "explained": 0,
        "unexplained": 1,
    }
    assert data.tie_out_results[0]["result"] == "FAIL"
    (unexplained,) = [row for row in data.rows if row["is_within_tolerance"] == "No"]
    assert unexplained["row_key"] == "line:Contract 1:POB #1:REVENUE_CUM"
    assert unexplained["exception_item_id"] == "EXC-000007" and unexplained["difference"] == "0.01"
    assert [call[:6] for call in session.calls] == ["SELECT", "SELECT", "SELECT"]
    assert "erev.migration_batch" in session.calls[0]
    assert "erev.migration_reconciliation_line" in session.calls[1]
    assert "erev.exception_item" in session.calls[2]
    # only_differences keeps the totals and the one row
    uow, _ = _uow(
        _Result((batch,)),
        _Result(tuple(stored)),
        _Result(({"id": EXCEPTION, "exception_no": "EXC-000007"},)),
    )
    narrowed = report.build(uow, _params(migration_id=str(MIGRATION), only_differences=True))
    assert len(narrowed.rows) == 1 and narrowed.control_totals["line_count"] == 136


def test_build_refuses_an_absent_migration_before_reading_lines() -> None:
    # SCREENS_B RPT-41: an absent or invisible migration → 422 validation-failed on
    # parameters.migration_id with "Choose a migration."; no T-MIG-03 read follows.
    uow, session = _uow(_Result(()))
    with pytest.raises(Problem) as refused:
        report.build(uow, _params(migration_id=str(MIGRATION)))
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].field == "parameters.migration_id"
    assert refused.value.errors[0].message == "Choose a migration."
    assert len(session.calls) == 1 and "erev.migration_batch" in session.calls[0]
    uow, session = _uow()
    with pytest.raises(Problem) as missing:
        report.build(uow, _params())
    assert missing.value.errors[0].field == "parameters.migration_id" and session.calls == []


def test_build_with_is_the_supplied_row_seam() -> None:
    # The seam for tests: supplied rows, batch and exception numbers; an unprofiled batch gives
    # 0 / 0 KPI totals.
    row = {
        "contract_external_id": "Contract 1",
        "obligation_key": None,
        "measure": "TRANSACTION_PRICE",
        "source_value": Decimal("1300"),
        "erev_value": Decimal("1300.0005"),
        "difference": Decimal("0.0005"),
        "tolerance": Decimal("0.0001"),
        "is_within_tolerance": False,
        "deviation_ref": None,
        "exception_item_id": EXCEPTION,
    }
    (line,) = report.lines_from_rows([row])
    assert line.row_key == "line:Contract 1::TRANSACTION_PRICE" and line.needs_exception
    assert line.exception_ref == str(EXCEPTION)  # unresolved: the id itself
    (resolved,) = report.lines_from_rows([row], {EXCEPTION: "EXC-000001"})
    assert resolved.exception_ref == "EXC-000001"
    uow, session = _uow()
    data = report.build_with(
        lambda _uow, _id: [row],
        uow,
        _params(migration_id=str(MIGRATION)),
        batch_reader=lambda _uow, _id: {"id": MIGRATION, "profile": None},
        exception_reader=lambda _uow, ids: {EXCEPTION: "EXC-000001"},
    )
    assert data.rows[0]["exception_item_id"] == "EXC-000001"
    assert data.control_totals == {
        "contracts": 0,
        "legacy_obligation_rows": 0,
        "line_count": 1,
        "differences_above_tolerance": 1,
        "explained": 0,
        "unexplained": 1,
    }
    assert session.calls == []


def test_colliding_rows_keep_their_own_exception_numbers() -> None:
    # Codex RPT41-ID-1: two distinct T-MIG-03 rows whose old display keys collided each render
    # their own exception number; the association is by row identity, never by the key string.
    def row(contract: str, obligation: str | None, item: UUID) -> dict[str, Any]:
        return {
            "contract_external_id": contract,
            "obligation_key": obligation,
            "measure": "REVENUE_CUM",
            "source_value": Decimal("1"),
            "erev_value": Decimal("2"),
            "difference": Decimal("1"),
            "tolerance": Decimal("0.0001"),
            "is_within_tolerance": False,
            "deviation_ref": None,
            "exception_item_id": item,
        }

    pairs = [
        (row("C1", None, UUID(int=1)), row("C1", "contract", UUID(int=2))),
        (row("C:A", "P1", UUID(int=3)), row("C", "A:P1", UUID(int=4))),
    ]
    numbers = {UUID(int=n): f"EXC-00000{n}" for n in (1, 2, 3, 4)}
    for first, second in pairs:
        uow, _ = _uow()
        looked_up: list[UUID] = []

        def exception_reader(_uow: Any, ids: Any, log: list[UUID] = looked_up) -> dict[UUID, str]:
            log.extend(ids)
            return numbers

        data = report.build_with(
            lambda _uow, _id, rows=(first, second): list(rows),
            uow,
            _params(migration_id=str(MIGRATION)),
            batch_reader=lambda _uow, _id: {"id": MIGRATION, "profile": None},
            exception_reader=exception_reader,
        )
        # packet 1006 symptom "only the second UUID reaches the lookup": both ids are looked up
        assert sorted(looked_up) == sorted(
            [first["exception_item_id"], second["exception_item_id"]]
        )
        assert len(data.rows) == 2
        assert len({r["row_key"] for r in data.rows}) == 2
        shown = {r["row_key"]: r["exception_item_id"] for r in data.rows}
        expected = {
            report.lines_from_rows([first])[0].row_key: numbers[first["exception_item_id"]],
            report.lines_from_rows([second])[0].row_key: numbers[second["exception_item_id"]],
        }
        assert shown == expected
        assert data.control_totals["unexplained"] == 2


def test_report_data_exception_items_are_keyed_structurally() -> None:
    # The pure path accepts exception numbers keyed by Line.key (contract, obligation, measure) —
    # never by the display string; a display-string key would be ignored.
    key = ("C1", None, "REVENUE_CUM")
    (line,) = reconciliation.lines({key: Fraction(1)}, {key: Fraction(2)})
    data = report.report_data([line], exception_items={key: "EXC-000009"})
    assert data.rows[0]["exception_item_id"] == "EXC-000009"
    by_string = report.report_data([line], exception_items=cast(Any, {line.row_key: "EXC-000009"}))
    assert by_string.rows[0]["exception_item_id"] is None
