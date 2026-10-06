"""RPT-18 ``manual_adjustment_register`` producer — CPU witnesses (BUILD_SPEC RPS-8; ENGINE_SPEC_B
S15-R-20d rev 1.39; F-CLO record §25.3x). Pure row shaping, control totals, key columns and the
registration; no database (the RPS-8 acceptance over seeded rows is
``tests/domain/reports/test_registers_close.py`` — DB, NOT RUN in the lane)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.close import relock_diff
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import manual_adjustment_register as register
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.enums import SnapshotKind
from erev_api.problems import Problem

ADJ: UUID = UUID("00000000-0000-4000-8000-00000000ad01")
MAYA: UUID = UUID("00000000-0000-4000-8000-00000000000a")
PRIYA: UUID = UUID("00000000-0000-4000-8000-00000000000b")
AT: datetime = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _source(**over: object) -> register.Source:
    base = dict(
        adjustment_id=ADJ,
        adjustment_no="ADJ-000001",
        kind="SCHEDULE_OVERRIDE",
        status="REJECTED",
        contract_external_id="BG-AVM-0022",
        obligation_key="O1",
        entity_code="AVM-US",
        period_key="FY2026-P09",
        effective_date=date(2026, 9, 16),
        reason_code="DATA_CORRECTION",
        memo="Customer acceptance pending",
        currency="USD",
        amount_functional_abs=Decimal("2400.00"),
        preparer_id=MAYA,
        preparer_kind="USER",
        approvers=(),
        approved_at=None,
        decision_comment="Attach the customer acceptance before resubmitting.",
        attachment_count=0,
        is_deferred_past_lock=False,
    )
    base.update(over)
    return register.Source(**base)  # type: ignore[arg-type]


def test_registration_and_catalogue_row() -> None:
    """``framework.BUILDERS`` admits the code (19 → 20); the served view defaults to functional
    (RPT-18); the source contract is OPEN; the catalogue row admits the lock (CLO-8b)."""
    assert framework.BUILDERS[register.CODE] is register.build
    assert framework.PARAMETER_DEFAULTS[register.CODE] == {"currency_view": "functional"}
    assert framework.SOURCE_CONTRACTS[register.CODE].strategy == "open"
    definition = DEFINITIONS_BY_CODE[register.CODE]
    assert definition.kind == "REGISTER"
    assert {"from_period_key", "to_period_key", "status", "kind", "period_lock_id"} <= set(
        definition.parameters_schema["properties"]
    )
    assert [column.key for column in register.COLUMNS] == list(register.FIELDS)


def test_key_columns_match_the_relock_key_spec() -> None:
    """S15-R-20d: key (entity_code, adjustment_no); the one measure amount_functional_abs — the
    KeySpec ``close/relock_diff.py`` already pins for MANUAL_ADJUSTMENT_REGISTER."""
    kind = SnapshotKind.MANUAL_ADJUSTMENT_REGISTER.value
    assert relock_diff.key_columns_of(kind) == register.KEY_COLUMNS
    assert register.KEY_COLUMNS == ("entity_code", "adjustment_no")
    assert relock_diff.KEY_COLUMNS[kind].measures == register.MEASURES
    assert register.MEASURES == ("amount_functional_abs",)


def test_row_shape_rejected_schedule_override() -> None:
    """WLD-B-02 as a row: labels are attribute columns; the row key is RPT-18's; the rejected
    adjustment carries the REJECT comment, no approvers and preparer_differs False."""
    names = {MAYA: "Maya Chen", PRIYA: "Priya Natarajan"}
    (row,) = register.dataset_rows([_source()], names)
    assert row["row_key"] == "adjustment:ADJ-000001"
    assert (row["adjustment_no"], row["kind"], row["status"]) == (
        "ADJ-000001",
        "SCHEDULE_OVERRIDE",
        "REJECTED",
    )
    assert row["amount_functional_abs"] == {"amount": "2400.00", "currency": "USD"}
    assert row["preparer"] == "Maya Chen"
    assert row["approvers"] is None and row["approved_at"] is None
    assert row["preparer_differs"] is False and row["attachment_count"] == 0
    assert row["decision_comment"] == "Attach the customer acceptance before resubmitting."
    assert row["is_deferred_past_lock"] is False


def test_row_shape_posted_with_two_approvers() -> None:
    names = {MAYA: "Maya Chen", PRIYA: "Priya Natarajan"}
    source = _source(
        adjustment_no="ADJ-000002",
        status="POSTED",
        approvers=((PRIYA, "USER"), (None, "SYSTEM")),
        approved_at=AT,
        decision_comment=None,
        attachment_count=2,
    )
    (row,) = register.dataset_rows([source], names)
    assert row["approvers"] == "Priya Natarajan, System"
    assert row["approved_at"] == AT and row["preparer_differs"] is True
    assert row["attachment_count"] == 2


def test_control_totals_every_row_and_posted_footer() -> None:
    names: dict[UUID, str] = {}
    rows = register.dataset_rows(
        [
            _source(),
            _source(
                adjustment_no="ADJ-000002",
                status="POSTED",
                amount_functional_abs=Decimal("100.00"),
            ),
            _source(
                adjustment_no="ADJ-000003",
                status="POSTED",
                currency="EUR",
                entity_code="AVM-DE",
                amount_functional_abs=Decimal("50.00"),
            ),
        ],
        names,
    )
    totals = register.control_totals(rows)
    assert totals["row_count"] == 3
    assert totals["amount_functional_abs_total"] == {"EUR": "50.00", "USD": "2500.00"}
    assert totals["posted_total"] == {"EUR": "50.00", "USD": "100.00"}


def test_key_columns_refuse_a_repeat_and_a_missing_key() -> None:
    names: dict[UUID, str] = {}
    twice = register.dataset_rows([_source(), _source()], names)
    with pytest.raises(Problem):
        register.check_key_columns(twice)
    blank = register.dataset_rows([_source(adjustment_no="")], names)
    with pytest.raises(Problem):
        register.check_key_columns(blank)


def test_transaction_view_is_refused_by_name() -> None:
    params = ReportParams(
        report_code=register.CODE,
        report_version=1,
        parameters={"currency_view": "transaction"},
        entity_ids=(MAYA,),
        known_at=AT,
        historical=False,
    )
    with pytest.raises(Problem) as refused:
        register.check_view(params)
    (error,) = refused.value.errors
    assert error.field == "parameters.currency_view"


def test_historical_refusal_names_the_changed_row() -> None:
    later = AT.replace(hour=13)
    rows = [{"adjustment_no": "ADJ-000001", "updated_at": later}]
    message = register.historical_refusal(rows, cutoff=AT, historical=True)
    assert message is not None and "ADJ-000001" in message and AT.isoformat() in message
    assert register.historical_refusal(rows, cutoff=AT, historical=False) is None
