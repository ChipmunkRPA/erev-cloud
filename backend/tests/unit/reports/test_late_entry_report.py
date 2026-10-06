"""RPT-17 ``late_entry_report`` — CPU witnesses (BUILD_SPEC RPS-8; SCREENS_B §5.6.3 RPT-17 rev
1.25; 03 REQ-CLS-007). The specification grid is parsed from SCREENS_B, so a specification edit or
a builder column drift fails here; the two section rules, the row identity, the order and the
window are proven on pure inputs. The acceptance over a world built through the product's commands
is ``tests/domain/reports/test_registers_close.py::test_late_entry_window`` (database).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import late_entry_report as late
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.domain.reports.outputs import ReportData, RunStamp
from erev_api.domain.reports.outputs import csv as csv_output
from erev_api.domain.reports.outputs import manifest as manifest_output
from erev_api.domain.reports.outputs import pdf as pdf_output
from erev_api.domain.reports.outputs import xlsx as xlsx_output
from erev_api.problems import Problem
from support import report_specs

AUGUST = late.Scope(
    entity_code="AVM-DE",
    period_start=date(2026, 8, 1),
    period_end=date(2026, 8, 31),
    lock_recorded_at=datetime(2026, 9, 4, 9, 0, tzinfo=UTC),
)
MAYA = {"id": None, "kind": "USER", "display_name": "Maya Okafor"}


def event(day: date, *, version: int = 1, **changes: Any) -> late.Event:
    values: dict[str, Any] = {
        "entity_code": "AVM-DE",
        "contract_external_id": "NS-SO-DE-5003",
        "stream_version": version,
        "event_type": "BILLING_RECORDED",
        "effective_date": day,
        "recorded_at": datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        "origin": "IMPORT",
        "recorded_by": MAYA,
        "approval_request_no": "APR-000007",
    }
    return late.Event(**{**values, **changes})


def rows_of(
    events: list[late.Event], *, days: int = 5, scope: late.Scope = AUGUST
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return late.dataset_rows(events, {scope.entity_code: scope}, days=days)


# --- specification and registration ---------------------------------------------------------------


def test_columns_are_the_specification_grid() -> None:
    """SCREENS_B RPT-17 rev 1.25: the builder's columns are the grid's fields in its order, under
    the grid's headers ("(section 1)" names where the lock column is filled)."""
    keys = [column.key for column in late.COLUMNS]
    assert keys == report_specs.fields(17, late.CODE)
    assert len(set(keys)) == len(keys) and "row_key" not in keys
    headers = {column.key: column.header for column in late.COLUMNS}
    for header, names in report_specs.grid(17, late.CODE):
        assert len(names) == 1
        assert headers[names[0]] == header.replace(" (section 1)", ""), names


def test_registration_and_catalogue() -> None:
    assert framework.BUILDERS[late.CODE] is late.build
    contract = framework.SOURCE_CONTRACTS[late.CODE]
    assert contract.strategy == "open" and len(contract.open) == 1
    assert "RPT-17" in contract.open[0]
    definition = DEFINITIONS_BY_CODE[late.CODE]
    section = report_specs.section(17, late.CODE)
    assert f"| Kind, formats | `{definition.kind}`;" in section
    assert definition.tie_outs == ()  # "Tie-out: none"
    properties = definition.parameters_schema["properties"]
    assert set(properties) >= {"entity_codes", "book", "period_key", late.WINDOW_DAYS}
    low, high = late.WINDOW_RANGE
    assert properties[late.WINDOW_DAYS] == {"type": "integer", "minimum": low, "maximum": high}
    assert "period_lock_id" not in properties  # no E-64 lock dataset
    assert late.CODE not in framework.PARAMETER_DEFAULTS
    assert late.CODE not in framework.REQUIRED_PERMISSIONS  # contract.read data, entity-filtered


def test_the_window_default_is_the_registry_setting() -> None:
    """SCREENS_B RPT-17: default "registry ``close.late_entry_window_days`` (default 5)" — stored
    with the run (D-87 L6-3-Q-29) through ``SETTING_DEFAULTS``."""
    from erev_api.registry.platform import PLATFORM_PARAMETERS

    assert framework.SETTING_DEFAULTS[late.CODE] == {late.WINDOW_DAYS: late.WINDOW_SETTING}
    assert late.WINDOW_SETTING in PLATFORM_PARAMETERS
    section = report_specs.section(17, late.CODE)
    assert f"registry `{late.WINDOW_SETTING}` (default 5)" in section
    assert f'"{late.WINDOW_COPY}"' in section


def test_specification_literals() -> None:
    section = report_specs.section(17, late.CODE)
    assert 'Section 1 "Entered after lock"' in section
    assert 'Section 2 "Near period end"' in section
    assert "`row_key` `event:<external id>:<stream version>`" in section
    assert "control totals `section_1_count`, `section_2_count`" in section
    assert (late.ENTERED_AFTER_LOCK, late.NEAR_PERIOD_END) == (1, 2)


# --- the window parameter -------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 5, 31])
def test_window_days_in_range(value: int) -> None:
    assert late.window_days(value) == value


@pytest.mark.parametrize("value", [-1, 32, True, "5", 5.0, None])
def test_window_days_out_of_range_is_refused_with_the_copy(value: object) -> None:
    with pytest.raises(Problem) as refused:
        late.window_days(value)
    (error,) = refused.value.errors
    assert (error.field, error.message) == ("parameters.window_days", late.WINDOW_COPY)


def test_the_api_answers_the_window_copy() -> None:
    """The closed schema refuses a value outside 0 to 31 at creation with the SCREENS_B copy, not
    the generic schema sentence; another integer parameter keeps the generic one."""
    schema = DEFINITIONS_BY_CODE[late.CODE].parameters_schema
    for value in (-1, 32, "5", True):
        (error,) = framework.parameter_errors(schema, {late.WINDOW_DAYS: value})
        assert (error.field, error.message) == ("parameters.window_days", late.WINDOW_COPY)
    assert framework.parameter_errors(schema, {late.WINDOW_DAYS: 0}) == []
    assert framework.parameter_errors(schema, {late.WINDOW_DAYS: 31}) == []
    limit = {"type": "integer", "minimum": 0, "maximum": 3}
    assert framework.schema_message("depth", limit, 4) == "depth must be at most 3."


# --- section 1: entered after lock ----------------------------------------------------------------


def test_section_1_lists_an_event_of_the_period_recorded_after_the_first_lock() -> None:
    locked = AUGUST.lock_recorded_at
    assert locked is not None
    after = locked + timedelta(days=1)
    rows, totals = rows_of(
        [
            event(date(2026, 8, 14), version=3),  # recorded before the lock
            event(date(2026, 8, 20), version=4, recorded_at=after),
            event(date(2026, 8, 1), version=5, recorded_at=after),  # the period's first day
            event(date(2026, 7, 31), version=6, recorded_at=after),  # the period before
            event(date(2026, 9, 1), version=7, recorded_at=after),  # the period after
            event(date(2026, 8, 19), version=8, recorded_at=locked),  # at the lock, not after
        ],
        days=0,
    )
    assert [(row["section"], row["row_key"]) for row in rows] == [
        (1, "event:NS-SO-DE-5003:5"),
        (1, "event:NS-SO-DE-5003:4"),
    ]
    first = rows[0]
    assert (first["effective_date"], first["recorded_at"]) == (date(2026, 8, 1), after)
    assert (first["days_from_period_end"], first["lock_recorded_at"]) == (-30, locked)
    assert totals == {"section_1_count": 2, "section_2_count": 0, "window_days": 0}


def test_a_period_without_a_lock_has_no_section_1_row() -> None:
    open_period = late.Scope("AVM-DE", date(2026, 9, 1), date(2026, 9, 30))
    rows, totals = rows_of(
        [event(date(2026, 9, 10), recorded_at=datetime(2026, 12, 1, tzinfo=UTC))],
        scope=open_period,
    )
    assert rows == [] and totals["section_1_count"] == 0


# --- section 2: near period end -------------------------------------------------------------------


def test_section_2_window_is_inclusive_on_both_sides_of_the_period_end() -> None:
    """REQ-CLS-007 "within ±N days of period end": 3 days before is listed under the 5-day window,
    6 days before is not; the boundary days are in."""
    days = {
        1: date(2026, 8, 25),  # −6
        2: date(2026, 8, 26),  # −5
        3: date(2026, 8, 28),  # −3
        4: date(2026, 8, 31),  # 0
        5: date(2026, 9, 5),  # +5
        6: date(2026, 9, 6),  # +6
    }
    rows, totals = rows_of([event(day, version=version) for version, day in days.items()])
    assert [(row["row_key"], row["days_from_period_end"]) for row in rows] == [
        ("event:NS-SO-DE-5003:2", -5),
        ("event:NS-SO-DE-5003:3", -3),
        ("event:NS-SO-DE-5003:4", 0),
        ("event:NS-SO-DE-5003:5", 5),
    ]
    assert {row["section"] for row in rows} == {2}
    assert all(row["lock_recorded_at"] is None for row in rows)  # filled in section 1 only
    assert totals == {"section_1_count": 0, "section_2_count": 4, "window_days": 5}
    wider, _ = rows_of([event(days[1], version=1), event(days[6], version=6)], days=6)
    assert [row["days_from_period_end"] for row in wider] == [-6, 6]
    end_only, _ = rows_of([event(day, version=version) for version, day in days.items()], days=0)
    assert [row["row_key"] for row in end_only] == ["event:NS-SO-DE-5003:4"]


# --- both sections --------------------------------------------------------------------------------


def test_an_event_in_both_sections_keeps_its_key_and_section_identifies_the_row() -> None:
    locked = AUGUST.lock_recorded_at
    assert locked is not None
    late_invoice = event(date(2026, 8, 31), version=4, recorded_at=locked + timedelta(hours=2))
    rows, totals = rows_of([late_invoice])
    assert [(row["section"], row["row_key"], row["event_key"]) for row in rows] == [
        (1, "event:NS-SO-DE-5003:4", "event:NS-SO-DE-5003:4"),
        (2, "event:NS-SO-DE-5003:4", "event:NS-SO-DE-5003:4"),
    ]
    assert len({(row["section"], row["row_key"]) for row in rows}) == len(rows)
    entered, near = rows
    assert entered["lock_recorded_at"] == locked and near["lock_recorded_at"] is None
    for row in rows:
        assert (row["event_type"], row["event_type_label"]) == (
            "BILLING_RECORDED",
            "Billing recorded",
        )
        assert (row["origin"], row["recorded_by"], row["approval_request_no"]) == (
            "IMPORT",
            MAYA,
            "APR-000007",
        )
        assert set(row) == {"row_key", *(column.key for column in late.COLUMNS)}
    assert (totals["section_1_count"], totals["section_2_count"]) == (1, 1)


def test_rows_are_ordered_by_section_entity_date_record_time_contract_and_version() -> None:
    other = late.Scope(
        entity_code="AVM-UK",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )
    earlier = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)  # before the others' 20 Aug
    events = [
        event(date(2026, 8, 30), version=9),
        event(date(2026, 8, 30), version=2, contract_external_id="NS-SO-DE-5004"),
        event(date(2026, 8, 30), version=7, recorded_at=earlier),
        event(date(2026, 8, 29), version=8),
        event(date(2026, 8, 31), version=1, entity_code="AVM-UK", contract_external_id="UK-1"),
        event(date(2026, 8, 30), version=1),
    ]
    scopes = {AUGUST.entity_code: AUGUST, other.entity_code: other}
    forward, _ = late.dataset_rows(events, scopes, days=5)
    backward, _ = late.dataset_rows(list(reversed(events)), scopes, days=5)
    assert forward == backward  # the input order never shows
    assert [(row["entity_code"], row["row_key"]) for row in forward] == [
        ("AVM-DE", "event:NS-SO-DE-5003:8"),
        ("AVM-DE", "event:NS-SO-DE-5003:7"),
        ("AVM-DE", "event:NS-SO-DE-5003:1"),
        ("AVM-DE", "event:NS-SO-DE-5003:9"),
        ("AVM-DE", "event:NS-SO-DE-5004:2"),
        ("AVM-UK", "event:UK-1:1"),
    ]


def test_each_entity_is_measured_against_its_own_period_and_an_unknown_entity_is_left_out() -> None:
    """Entities on different calendars name different days by one period key; an event of an
    entity outside the run (no scope) is never listed."""
    april_year = late.Scope("AVM-JP", date(2026, 11, 1), date(2026, 11, 30))
    events = [
        event(date(2026, 8, 30), version=1),
        event(date(2026, 11, 28), version=1, entity_code="AVM-JP", contract_external_id="JP-1"),
        event(date(2026, 8, 30), version=1, entity_code="AVM-US", contract_external_id="US-1"),
    ]
    rows, totals = late.dataset_rows(
        events, {AUGUST.entity_code: AUGUST, april_year.entity_code: april_year}, days=5
    )
    assert [(row["entity_code"], row["days_from_period_end"]) for row in rows] == [
        ("AVM-DE", -1),
        ("AVM-JP", -2),
    ]
    assert totals["section_2_count"] == 2


def test_an_external_id_with_a_delimiter_keeps_a_distinct_key() -> None:
    """The key is RPT-16's ``event_key``: the external id CV-21 percent-encoded, so ``A:1`` at
    version 2 and ``A`` at a version spelt ``1:2`` cannot collide."""
    rows, _ = rows_of(
        [
            event(date(2026, 8, 31), version=2, contract_external_id="A:1"),
            event(date(2026, 8, 31), version=12, contract_external_id="A"),
        ]
    )
    assert [row["row_key"] for row in rows] == ["event:A:12", "event:A%3A1:2"]
    assert [row["contract_external_id"] for row in rows] == ["A", "A:1"]


# --- outputs --------------------------------------------------------------------------------------


def _data(events: list[late.Event]) -> ReportData:
    rows, totals = rows_of(events)
    return ReportData(columns=late.COLUMNS, rows=tuple(rows), control_totals=totals)


def _stamp() -> RunStamp:
    return RunStamp(
        report_code=late.CODE,
        report_name="Late-entry report",
        report_version=1,
        report_run_no="RPT-000017",
        parameters={"period_key": "FY2026-P08", "window_days": 5},
        entity_codes=("AVM-DE",),
        book="ASC606",
        as_of=None,
        source="Live",
        engine_version="test",
        build_sha="0" * 40,
        run_by="Maya",
        run_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
        output_sha256="0" * 64,
    )


def test_both_sections_render_in_every_output_format() -> None:
    """The dataset passes the four serializers natively: the empty lock cell of section 2, the
    signed integer, the instants and the actor; an empty run renders its header alone."""
    locked = AUGUST.lock_recorded_at
    assert locked is not None
    recorded = locked + timedelta(hours=2)
    populated = _data(
        [
            event(date(2026, 8, 31), version=4, recorded_at=recorded),
            event(date(2026, 9, 3), version=5, event_type="MEMO_UPDATED", origin="UI"),
        ]
    )
    report = {"code": late.CODE, "version": 1, "name": "Late-entry report"}
    stored = json.loads(manifest_output.dataset_bytes(report, {}, populated).decode("utf-8"))
    assert [(row["section"], row["row_key"]) for row in stored["rows"]] == [
        (1, "event:NS-SO-DE-5003:4"),
        (2, "event:NS-SO-DE-5003:4"),
        (2, "event:NS-SO-DE-5003:5"),
    ]
    entered, same, after = stored["rows"]
    assert (entered["effective_date"], entered["days_from_period_end"]) == ("2026-08-31", 0)
    assert entered["recorded_at"] == "2026-09-04T11:00:00Z"
    assert (entered["lock_recorded_at"], same["lock_recorded_at"]) == ("2026-09-04T09:00:00Z", None)
    assert (after["days_from_period_end"], after["event_type_label"]) == (3, "Memo updated")
    assert entered["recorded_by"] == MAYA

    table = list(
        csv.reader(io.StringIO(csv_output.render_csv(populated).decode("utf-8"), newline=""))
    )
    assert table[0] == [column.header for column in late.COLUMNS]
    assert [line[0] for line in table[1:]] == ["1", "2", "2"]
    lock_at = [column.key for column in late.COLUMNS].index("lock_recorded_at")
    assert [line[lock_at] for line in table[1:]] == ["2026-09-04T09:00:00Z", "", ""]
    assert csv_output.render_csv(_data([])).decode("utf-8").splitlines() == [
        ",".join(column.header for column in late.COLUMNS)
    ]

    for data in (populated, _data([])):
        assert xlsx_output.render_xlsx(data, _stamp()).startswith(b"PK")
        assert pdf_output.render_pdf(data, _stamp()).startswith(b"%PDF")
