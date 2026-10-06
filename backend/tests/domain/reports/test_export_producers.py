"""D-98 candidate 85 — canonical export producers ``je_population`` (RPT-15) and
``out_of_period_register`` (RPT-16): the pure row cores and the framework registration
(ENGINE_SPEC_B §15.2.7, S15-R-18a; SCREENS_B §5.6.3; F-CLO's relock_diff KeySpec names).

CPU only: no database. The DB-bound ``build`` paths run under the report worker tests and are not
exercised here. Fail-first on the committed tree: the builder modules do not exist and ``BUILDERS``
lacks both codes.

ENG-C6-RPT-2 (D-98 candidates 95, 96; Codex C6-RPT-R1 to R4 on 343e0392): the populated and empty
datasets pass through the native JSON and CSV serializers with typed Money cells (R1); stored
dimension mappings keep their members (R2); a cumulative multi-event delta is attributed once to
its event set and the effects are conserved, an unattributable line is refused by name (R3;
S15-R-18b); journal state is reconstructed as of the cutoff and a lock source is refused by name
(R4). Fail-first on the docs head 374a38e0: money cells are Decimals (TypeError in the
serializers), members collapse, ``events`` records and ``state_as_of`` do not exist.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams, je_population, out_of_period_register
from erev_api.domain.reports.outputs import ReportData
from erev_api.domain.reports.outputs import csv as csv_output
from erev_api.domain.reports.outputs import manifest as manifest_output
from erev_api.problems import Problem

# F-CLO's KeySpec header names (relock_diff.KEY_COLUMNS on sprint/l18; D-98 85).
JE_KEY: Final = ("entity_code", "book", "je_no", "line_no")
OOP_KEY: Final = ("origin_period_key", "posting_period_key", "event_key")
D = Decimal
T0 = datetime(2026, 2, 3, 9, 0, tzinfo=UTC)
ACTOR = {"id": None, "kind": "SYSTEM", "display_name": "System"}


def test_builders_are_registered() -> None:
    assert framework.BUILDERS["je_population"] is je_population.build
    assert framework.BUILDERS["out_of_period_register"] is out_of_period_register.build


def test_column_shapes_lead_with_the_key_code_columns_and_end_with_labels() -> None:
    """S15-R-18a: key code columns first (F-CLO's KeySpec names), measures in the middle, display
    attributes last; no column is named ``row_key``."""
    je_keys = [column.key for column in je_population.COLUMNS]
    assert tuple(je_keys[:4]) == JE_KEY == je_population.KEY_COLUMNS
    assert je_keys[-3:] == ["description", "created_by", "approved_by"]
    assert {c.kind for c in je_population.COLUMNS if c.key.startswith(("debit", "credit"))} == {
        "money"
    }
    oop_keys = [column.key for column in out_of_period_register.COLUMNS]
    assert tuple(oop_keys[:3]) == OOP_KEY == out_of_period_register.KEY_COLUMNS
    assert oop_keys[3] == "attribution_kind"  # D-98 102 Q1: EVENT_SET | TRIGGER, after the key
    assert oop_keys[4] == "lineage_scope"  # D-98 102b: SUBJECT | GROUP, null on a trigger row
    assert oop_keys[-2:] == ["event_type_label", "recorded_by"]
    assert "row_key" not in je_keys and "row_key" not in oop_keys
    assert len(set(je_keys)) == len(je_keys) and len(set(oop_keys)) == len(oop_keys)


def _je_record(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "entity_code": "US01",
        "book": "ASC606",
        "je_no": "JE-2026-02-0001",
        "line_no": 1,
        "period_key": "FY2026-P02",
        "je_type": "AUTOMATED",
        "account_code": "2100",
        "account_role": "CONTRACT_LIABILITY",
        "dimensions": ("dept:FIN", "cc:100"),
        "txn_currency": "USD",
        "debit_txn": D("1200.00"),
        "credit_txn": D("0.00"),
        "functional_currency": "USD",
        "debit_functional": D("1200.00"),
        "credit_functional": D("0.00"),
        "contract_external_id": "K-01",
        "obligation_key": "POB-01",
        "origin_period_key": None,
        "is_post_close": False,
        "run_no": "JR-000007",
        "run_state": "ACKNOWLEDGED",
        "batch_external_id": "B-7-1",
        "gl_document_id": "GL-9001",
        "source_line_count": 3,
        "created_at": T0,
        "approved_at": T0,
        "acknowledged_at": T0,
        "description": "Revenue recognition February",
        "created_by": ACTOR,
        "approved_by": ACTOR,
    }
    base.update(changes)
    return base


def test_je_population_rows_keys_order_and_control_totals() -> None:
    """Rows keyed ``line:<je no>:<line no>``, ordered entity / period / je_no / line_no, every
    column present; control totals count rows and distinct entries and sum debits and credits per
    currency in both currencies; a MANUAL entry sets ``is_manual``."""
    records = [
        _je_record(
            je_no="JE-2026-02-0002",
            line_no=1,
            je_type="MANUAL",
            account_code="4000",
            account_role="REVENUE",
            debit_txn=D("0.00"),
            credit_txn=D("50.00"),
            debit_functional=D("0.00"),
            credit_functional=D("50.00"),
        ),
        _je_record(
            line_no=2,
            account_code="4000",
            account_role="REVENUE",
            debit_txn=D("0.00"),
            credit_txn=D("1200.00"),
            debit_functional=D("0.00"),
            credit_functional=D("1200.00"),
        ),
        _je_record(),
        _je_record(
            entity_code="UK01",
            je_no="JE-2026-02-0009",
            line_no=1,
            txn_currency="GBP",
            debit_txn=D("80.00"),
            functional_currency="GBP",
            debit_functional=D("80.00"),
            period_key="FY2026-P01",
        ),
    ]
    rows = je_population.rows_from(records)
    assert [row["row_key"] for row in rows] == [  # entity code order puts UK01 before US01
        "line:JE-2026-02-0009:1",
        "line:JE-2026-02-0001:1",
        "line:JE-2026-02-0001:2",
        "line:JE-2026-02-0002:1",
    ]
    keys = {column.key for column in je_population.COLUMNS}
    assert all(keys <= set(row) for row in rows)
    assert [row["is_manual"] for row in rows] == [False, False, False, True]
    assert rows[1]["dimensions"] == ("cc:100", "dept:FIN")
    totals = je_population.control_totals(rows)
    assert totals["row_count"] == 4 and totals["entry_count"] == 3
    assert totals["debit_txn_total"] == {"GBP": "80.00", "USD": "1200.00"}
    assert totals["credit_txn_total"] == {"GBP": "0.00", "USD": "1250.00"}
    assert totals["debit_functional_total"] == {"GBP": "80.00", "USD": "1200.00"}
    assert totals["credit_functional_total"] == {"GBP": "0.00", "USD": "1250.00"}
    data = ReportData(columns=je_population.COLUMNS, rows=rows, control_totals=totals)
    assert data.row_count == 4


def test_je_population_tie_out_compares_functional_debits_with_the_runs() -> None:
    rows = je_population.rows_from(
        [
            _je_record(),
            _je_record(
                line_no=2,
                debit_txn=D("0.00"),
                credit_txn=D("1200.00"),
                debit_functional=D("0.00"),
                credit_functional=D("1200.00"),
            ),
        ]
    )
    passing = je_population.tie_out(rows, {"USD": D("1200.00")})
    assert (passing["code"], passing["result"]) == ("TO_JE_POPULATION_EQ_RUNS", "PASS")
    failing = je_population.tie_out(rows, {"USD": D("1300.00")})
    assert failing["result"] == "FAIL"


def _line(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "origin_period_key": "FY2026-P01",
        "posting_period_key": "FY2026-P02",
        "contract_external_id": "K-01",
        "stream_version": 4,
        "event_type": "BILLING_RECORDED",
        "effective_date": date(2026, 1, 20),
        "recorded_at": T0,
        "origin": "API",
        "created_by": None,
        "reason_code": "LATE_EVENT",
        "account_role": "REVENUE",
        "txn_currency": "USD",
        "amount_txn": D("-300.00"),  # a revenue credit (signed, debit positive)
        "approval_request_no": "AR-000012",
        "recorded_by": ACTOR,
    }
    base.update(changes)
    return base


def test_out_of_period_register_keeps_distinct_events_with_the_same_fields_apart() -> None:
    """Two events of one contract, type and effective date (stream versions 4 and 5) are two rows
    keyed by their own ``event_key``; a proxy tuple would have collapsed them. Effects sum per
    event: the revenue credit shows positive, the contract-liability debit in parentheses."""
    lines = [
        _line(),
        _line(account_role="CONTRACT_LIABILITY", amount_txn=D("300.00")),
        _line(stream_version=5, amount_txn=D("-125.00")),
        _line(stream_version=5, account_role="CONTRACT_LIABILITY", amount_txn=D("125.00")),
        _line(
            stream_version=5,
            account_role="ACCOUNTS_RECEIVABLE",
            amount_txn=D("0.00"),
            reason_code="LATE_EVENT",
        ),
    ]
    rows = out_of_period_register.rows_from(lines)
    assert [row["event_key"] for row in rows] == ["event:K-01:4:SUBJECT", "event:K-01:5:SUBJECT"]
    # S15-R-18a rev 1.110: the row key is the whole key — origin period, posting period, event key
    assert [row["row_key"] for row in rows] == [
        "FY2026-P01:FY2026-P02:event:K-01:4:SUBJECT",
        "FY2026-P01:FY2026-P02:event:K-01:5:SUBJECT",
    ]
    assert all(row["contract_external_id"] == "K-01" for row in rows)
    assert all(row["event_type"] == "BILLING_RECORDED" for row in rows)
    assert all(row["effective_date"] == date(2026, 1, 20) for row in rows)
    assert [row["revenue_effect"] for row in rows] == [_usd("300.00"), _usd("125.00")]
    assert [row["balance_effect"] for row in rows] == [_usd("-300.00"), _usd("-125.00")]
    assert rows[0]["event_type_label"] == "Billing recorded"
    assert rows[0]["reason_code"] == "LATE_EVENT"
    keys = {column.key for column in out_of_period_register.COLUMNS}
    assert all(keys <= set(row) for row in rows)
    totals = out_of_period_register.control_totals(rows, line_count=len(lines))
    assert totals == {
        "row_count": 2,
        "line_count": 5,  # S15-R-18a rev 1.25: the aggregated lines (conservation evidence)
        "revenue_effect_total": {"USD": "425.00"},
        "balance_effect_total": {"USD": "-425.00"},
    }
    ReportData(columns=out_of_period_register.COLUMNS, rows=rows, control_totals=totals)


def test_out_of_period_register_orders_by_the_key_and_joins_reason_codes() -> None:
    lines = [
        _line(origin_period_key="FY2026-P02", posting_period_key="FY2026-P03", stream_version=9),
        _line(contract_external_id="A-99", stream_version=1, reason_code="VOID"),
        _line(
            contract_external_id="A-99",
            stream_version=1,
            account_role="CONTRACT_LIABILITY",
            amount_txn=D("300.00"),
            reason_code="LATE_EVENT",
        ),
    ]
    rows = out_of_period_register.rows_from(lines)
    assert [row["row_key"] for row in rows] == [
        "FY2026-P01:FY2026-P02:event:A-99:1:SUBJECT",
        "FY2026-P02:FY2026-P03:event:K-01:9:SUBJECT",
    ]
    assert rows[0]["reason_code"] == "LATE_EVENT|VOID"
    assert out_of_period_register.event_key("K-01", 4) == "event:K-01:4"


# --- ENG-C6-RPT-2 ---------------------------------------------------------------------------------


def _usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _report(code: str) -> dict[str, Any]:
    return {"code": code, "version": 1, "name": code}


def _json(data: ReportData, code: str) -> dict[str, Any]:
    return json.loads(manifest_output.dataset_bytes(_report(code), {}, data).decode("utf-8"))


def _csv(data: ReportData) -> list[list[str]]:
    import csv
    import io

    return list(csv.reader(io.StringIO(csv_output.render_csv(data).decode("utf-8"), newline="")))


def _je_data(records: list[dict[str, object]]) -> ReportData:
    rows = je_population.rows_from(records)
    return ReportData(
        columns=je_population.COLUMNS,
        rows=rows,
        control_totals=je_population.control_totals(rows),
        tie_out_results=(je_population.tie_out(rows, {}),),
    )


def _oop_data(lines: list[dict[str, object]]) -> ReportData:
    found = out_of_period_register.aggregate(lines)
    return ReportData(
        columns=out_of_period_register.COLUMNS,
        rows=found.rows,
        control_totals=out_of_period_register.control_totals(
            found.rows, line_count=found.line_count
        ),
    )


def test_r1_je_population_money_cells_serialize_natively_populated_and_empty() -> None:
    """C6-RPT-R1: the four money columns are typed Money — transaction amounts in the line's
    transaction currency, functional amounts in its functional currency, at the currency's minor
    unit — so the native JSON and CSV serializers accept a populated dataset; an empty dataset
    serializes to a header-only CSV and an empty JSON row list. Values are preserved."""
    records = [
        _je_record(),
        _je_record(
            entity_code="UK01",
            je_no="JE-2026-02-0009",
            txn_currency="GBP",
            debit_txn=D("80.50"),
            functional_currency="USD",
            debit_functional=D("101.43"),
        ),
    ]
    data = _je_data(records)
    (uk, us) = data.rows
    assert uk["debit_txn"] == {"amount": "80.50", "currency": "GBP"}
    assert uk["debit_functional"] == {"amount": "101.43", "currency": "USD"}
    assert uk["credit_txn"] == {"amount": "0.00", "currency": "GBP"}
    assert us["debit_txn"] == _usd("1200.00") and us["credit_functional"] == _usd("0.00")
    document = _json(data, "je_population")
    assert [row["debit_txn"] for row in document["rows"]] == [
        {"amount": "80.50", "currency": "GBP"},
        {"amount": "1200.00", "currency": "USD"},
    ]
    assert document["row_count"] == 2
    assert document["control_totals"]["debit_txn_total"] == {"GBP": "80.50", "USD": "1200.00"}
    assert document["control_totals"]["debit_functional_total"] == {"USD": "1301.43"}
    table = _csv(data)
    header = table[0]
    assert "Debit (txn)" in header and "Debit (txn) currency" in header  # mixed currencies
    assert "Debit (functional) (USD)" in header  # one functional currency
    assert table[1][header.index("Debit (txn)")] == "80.50"
    assert table[1][header.index("Debit (txn) currency")] == "GBP"
    assert table[2][header.index("Debit (txn)")] == "1200.00"
    empty = _je_data([])
    assert _json(empty, "je_population")["rows"] == []
    assert len(_csv(empty)) == 1  # header only


def test_r1_out_of_period_register_money_cells_serialize_natively_populated_and_empty() -> None:
    lines = [
        _line(),
        _line(account_role="CONTRACT_LIABILITY", amount_txn=D("300.00")),
        _line(stream_version=5, txn_currency="EUR", amount_txn=D("-99.99")),
    ]
    data = _oop_data(lines)
    assert [row["revenue_effect"] for row in data.rows] == [
        _usd("300.00"),
        {"amount": "99.99", "currency": "EUR"},
    ]
    assert data.rows[0]["balance_effect"] == _usd("-300.00")
    document = _json(data, "out_of_period_register")
    assert document["rows"][1]["revenue_effect"] == {"amount": "99.99", "currency": "EUR"}
    assert document["control_totals"] == {
        "row_count": 2,
        "line_count": 3,
        "revenue_effect_total": {"EUR": "99.99", "USD": "300.00"},
        "balance_effect_total": {"EUR": "0.00", "USD": "-300.00"},
    }
    table = _csv(data)
    header = table[0]
    assert "Revenue effect" in header and "Revenue effect currency" in header
    assert table[1][header.index("Revenue effect")] == "300.00"
    assert table[2][header.index("Revenue effect currency")] == "EUR"
    empty = _oop_data([])
    assert _json(empty, "out_of_period_register")["rows"] == []
    assert len(_csv(empty)) == 1
    assert empty.control_totals["row_count"] == 0 and empty.control_totals["line_count"] == 0


def test_r2_je_population_dimensions_keep_their_members() -> None:
    """C6-RPT-R2: the stored ``journal_line.dimensions`` mapping renders as stable
    ``<dimension>:<member>`` pairs in dimension order; two lines with the same dimensions and
    different members stay distinct; an empty mapping is an empty list. The historical
    pre-rendered tuple fixture keeps its result."""
    rows = je_population.rows_from(
        [
            _je_record(line_no=1, dimensions={"dept": "FIN", "cc": "100"}),
            _je_record(line_no=2, dimensions={"dept": "OPS", "cc": "200"}),
            _je_record(line_no=3, dimensions={}),
            _je_record(line_no=4, dimensions=("dept:FIN", "cc:100")),
            _je_record(line_no=5, dimensions=None),
        ]
    )
    assert [row["dimensions"] for row in rows] == [
        ("cc:100", "dept:FIN"),
        ("cc:200", "dept:OPS"),
        (),
        ("cc:100", "dept:FIN"),
        (),
    ]
    document = _json(_je_data([_je_record(dimensions={"dept": "FIN", "cc": "100"})]), "x")
    assert document["rows"][0]["dimensions"] == ["cc:100", "dept:FIN"]


def _event(stream_version: int, **changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "contract_external_id": "K-01",
        "stream_version": stream_version,
        "event_type": "BILLING_RECORDED",
        "effective_date": date(2026, 1, 20),
        "recorded_at": T0 + timedelta(hours=stream_version),
        "origin": "API",
        "approval_request_no": f"AR-0000{stream_version}",
        "recorded_by": ACTOR,
    }
    base.update(changes)
    return base


def _cumulative(**changes: object) -> dict[str, object]:
    """A cumulative engine line (S14-R-13a): no single event, an ordered event set."""
    base: dict[str, object] = {
        "line_id": UUID("00000000-0000-0000-0000-00000000a001"),
        "origin_period_key": "FY2026-P01",
        "posting_period_key": "FY2026-P02",
        "contract_external_id": "K-01",
        "reason_code": "LATE_EVENT",
        "account_role": "REVENUE",
        "txn_currency": "USD",
        "amount_txn": D("-425.00"),
        "events": (
            _event(4),
            _event(5, event_type="CONTRACT_MODIFIED", approval_request_no="AR-00007"),
        ),
    }
    base.update(changes)
    return base


def test_r3_multi_event_delta_is_attributed_once_and_the_effects_are_conserved() -> None:
    """S15-R-18b: a cumulative delta of two first-included events is one row keyed by the joined
    event keys in set order; its amount is attributed once (never per member, never to the latest
    member alone); per currency the row effects equal the credit-positive sums of the input lines
    (conservation); ``line_count`` counts the lines. A single-event line of the same contract in
    the same periods stays its own row; the same set with a second origin is a second row."""
    lines = [
        _cumulative(),
        _cumulative(
            line_id=UUID("00000000-0000-0000-0000-00000000a002"),
            account_role="CONTRACT_LIABILITY",
            amount_txn=D("425.00"),
        ),
        _cumulative(
            line_id=UUID("00000000-0000-0000-0000-00000000a003"),
            origin_period_key="FY2025-P12",
            amount_txn=D("-10.00"),
            reason_code="VOID",
        ),
        _line(stream_version=4, amount_txn=D("-300.00")),  # single-event line, event 4
    ]
    found = out_of_period_register.aggregate(lines)
    rows = found.rows
    assert found.line_count == 4
    assert [(row["origin_period_key"], row["event_key"]) for row in rows] == [
        ("FY2025-P12", "event:K-01:4|event:K-01:5:SUBJECT"),
        ("FY2026-P01", "event:K-01:4:SUBJECT"),
        ("FY2026-P01", "event:K-01:4|event:K-01:5:SUBJECT"),
    ]
    multi = rows[2]
    # the same set with a second origin is a second row, and a second row key (RPT-OOP-ROWKEY-1)
    assert rows[0]["row_key"] == "FY2025-P12:FY2026-P02:event:K-01:4|event:K-01:5:SUBJECT"
    assert multi["row_key"] == "FY2026-P01:FY2026-P02:event:K-01:4|event:K-01:5:SUBJECT"
    assert len({row["row_key"] for row in rows}) == len(rows)
    assert multi["revenue_effect"] == _usd("425.00")  # once, not 850.00
    assert multi["balance_effect"] == _usd("-425.00")
    assert multi["event_type"] == "BILLING_RECORDED|CONTRACT_MODIFIED"
    assert multi["event_type_label"] == "Billing recorded | Contract modified"
    assert multi["approval_request_no"] == "AR-00004|AR-00007"
    assert multi["effective_date"] == date(2026, 1, 20)  # every member agrees
    assert multi["recorded_at"] == T0 + timedelta(hours=5)  # the latest member
    assert multi["recorded_by"] == ACTOR
    assert rows[0]["reason_code"] == "VOID" and rows[0]["revenue_effect"] == _usd("10.00")
    assert rows[1]["revenue_effect"] == _usd("300.00")
    # conservation: Σ row effects == Σ credit-positive line amounts on the revenue / position roles
    expected_revenue = -sum(
        D(str(line["amount_txn"]))
        for line in lines
        if line["account_role"] in out_of_period_register.REVENUE_ROLES
    )
    expected_balance = -sum(
        D(str(line["amount_txn"]))
        for line in lines
        if line["account_role"] in out_of_period_register.POSITION_ROLES
    )
    totals = out_of_period_register.control_totals(rows, line_count=found.line_count)
    assert totals["revenue_effect_total"] == {"USD": str(expected_revenue)} == {"USD": "735.00"}
    assert totals["balance_effect_total"] == {"USD": str(expected_balance)} == {"USD": "-425.00"}
    assert totals["line_count"] == 4 and totals["row_count"] == 3


def test_r3_members_that_disagree_leave_the_date_and_actor_null_never_a_proxy() -> None:
    other = {"id": None, "kind": "USER", "display_name": "Pat"}
    lines = [
        _cumulative(
            events=(
                _event(4),
                _event(5, effective_date=date(2026, 1, 25), recorded_by=other, origin="UI"),
            )
        )
    ]
    (row,) = out_of_period_register.aggregate(lines).rows
    assert row["effective_date"] is None and row["recorded_by"] is None
    assert row["origin"] == "API|UI"
    assert row["recorded_at"] == T0 + timedelta(hours=5)


def test_r3_an_unattributable_line_is_refused_by_name_never_dropped() -> None:
    """S15-R-18b: a selected out-of-period line with neither ``contract_event_id`` nor T-SL-12
    rows refuses the run with ``OUT_OF_PERIOD_ATTRIBUTION_MISSING``, one error per line naming the
    line, its periods, reason and contract; attributable lines in the same population do not
    rescue it."""
    orphan = _cumulative(
        line_id=UUID("00000000-0000-0000-0000-00000000b001"), events=(), reason_code="LATE_EVENT"
    )
    with pytest.raises(Problem) as raised:
        out_of_period_register.aggregate([_line(), orphan])
    problem = raised.value
    assert problem.slug == "validation-failed"
    (error,) = problem.errors
    assert error.rule_id == out_of_period_register.ATTRIBUTION_MISSING
    assert error.rule_id == "OUT_OF_PERIOD_ATTRIBUTION_MISSING"
    assert "00000000-0000-0000-0000-00000000b001" in error.message
    assert "FY2026-P01" in error.message and "FY2026-P02" in error.message
    assert "LATE_EVENT" in error.message and "K-01" in error.message
    with pytest.raises(Problem):
        out_of_period_register.rows_from([orphan])


def _run_record(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "run_state": "acknowledged",
        "run_updated_at": T0 + timedelta(days=9),
        "run_approved_at": T0 + timedelta(days=1),
        "run_exported_at": T0 + timedelta(days=2),
        "run_acknowledged_at": T0 + timedelta(days=3),
        "run_cancelled_at": None,
        "batch_acknowledged_at": T0 + timedelta(days=3),
    }
    base.update(changes)
    return base


def test_r4_journal_state_is_reconstructed_as_of_the_cutoff() -> None:
    """REQ-PLT-030 / S15-R-18b: a run mutated after the cutoff reports the state its timestamps
    establish — a later approval, export, acknowledgement or cancellation never appears; a run
    whose last mutation is at or before the cutoff reports its stored state (``failed`` has no
    timestamp of its own)."""
    record = _run_record()
    before_approval = je_population.state_as_of(record, T0 + timedelta(hours=1))
    assert (before_approval.run_state, before_approval.approved_at) == ("draft", None)
    assert before_approval.acknowledged_at is None and before_approval.cancelled is False
    after_approval = je_population.state_as_of(record, T0 + timedelta(days=1, hours=1))
    assert (after_approval.run_state, after_approval.approved_at) == (
        "approved",
        T0 + timedelta(days=1),
    )
    exported = je_population.state_as_of(record, T0 + timedelta(days=2, hours=1))
    assert exported.run_state == "exported" and exported.acknowledged_at is None
    acknowledged = je_population.state_as_of(record, T0 + timedelta(days=3, hours=1))
    assert acknowledged.run_state == "acknowledged"
    assert acknowledged.acknowledged_at == T0 + timedelta(days=3)
    cancelled_later = _run_record(run_state="cancelled", run_cancelled_at=T0 + timedelta(days=8))
    as_of_day_4 = je_population.state_as_of(cancelled_later, T0 + timedelta(days=4))
    assert as_of_day_4.cancelled is False and as_of_day_4.run_state == "acknowledged"
    as_of_day_10 = je_population.state_as_of(cancelled_later, T0 + timedelta(days=10))
    assert as_of_day_10.cancelled is True and as_of_day_10.run_state == "cancelled"
    failed = _run_record(
        run_state="failed",
        run_no="JR-000042",
        run_updated_at=T0 + timedelta(days=4),
        run_acknowledged_at=None,
        batch_acknowledged_at=None,
    )
    history = (  # the SOP-7 transition history the reader returns (occurrence, after.state)
        je_population.Transition(T0 + timedelta(days=1), 1, "approved"),
        je_population.Transition(T0 + timedelta(days=2, hours=2), 2, "failed"),
    )
    settled = je_population.state_as_of(failed, T0 + timedelta(days=5), history)
    assert settled.run_state == "failed"  # last mutation at or before the cutoff: stored state
    audited = je_population.state_as_of(failed, T0 + timedelta(days=3), history)
    assert audited.run_state == "failed"  # D-98 102 Q3: the audit event dates the transition
    pending = je_population.state_as_of(failed, T0 + timedelta(days=2, hours=1), history)
    assert pending.run_state == "exported"  # the failure is after the cutoff
    unknown = _run_record(
        run_state="failed",
        run_no="JR-000043",
        run_updated_at=T0 + timedelta(days=4),
        run_acknowledged_at=None,
        batch_acknowledged_at=None,
    )
    with pytest.raises(Problem) as raised:
        je_population.state_as_of(unknown, T0 + timedelta(days=3), ())  # no audit event at all
    (error,) = raised.value.errors
    assert error.rule_id == je_population.STATE_UNKNOWN_AS_OF == "JOURNAL_RUN_STATE_UNKNOWN_AS_OF"
    assert "JR-000043" in error.message


def test_r4_a_lock_source_is_refused_by_name_until_the_snapshot_branch_lands() -> None:
    params = ReportParams(
        report_code="je_population",
        report_version=1,
        parameters={},
        entity_ids=(),
        known_at=T0,
        period_lock_id=UUID("00000000-0000-0000-0000-0000000000c1"),
    )
    for module in (je_population, out_of_period_register):
        with pytest.raises(Problem) as raised:
            module.refuse_locked_source(params)
        (error,) = raised.value.errors
        assert error.field == "parameters.period_lock_id"
        assert "S15-R-19" in error.message
    current = ReportParams(
        report_code="je_population", report_version=1, parameters={}, entity_ids=(), known_at=T0
    )
    je_population.refuse_locked_source(current)  # no lock: nothing to refuse


def _trigger_line(**changes: object) -> dict[str, object]:
    """A late line of a trigger-only recomputation (D-98 102 Q1): no event set, a computation."""
    base: dict[str, object] = {
        "line_id": UUID("00000000-0000-0000-0000-00000000c001"),
        "origin_period_key": "FY2026-P01",
        "posting_period_key": "FY2026-P02",
        "contract_external_id": "K-01",
        "reason_code": "LATE_EVENT",
        "account_role": "REVENUE",
        "txn_currency": "USD",
        "amount_txn": D("-40.00"),
        "events": (),
        "trigger": "POLICY_RERUN",
        "computation_id": UUID("00000000-0000-0000-0000-0000000000f1"),
        "computation_created_at": T0 + timedelta(days=2),
        "computation_recorded_by": ACTOR,
        # D-98 102a: the persisted proof — none of the computation's cause events belongs to the
        # line's subject (contract); read from contract_version.cause_event_ids by ``build``.
        "cause_event_count": 0,
    }
    base.update(changes)
    return base


def test_q1_trigger_only_delta_is_attributed_to_its_computation_trigger() -> None:
    """D-98 102 Q1: a late delta of a computation with no first-included event of its subject is a
    TRIGGER row keyed ``trigger:<E-87 code>:<computation id>`` — never a refusal, never a proxy
    event; an event-set row of the same periods stays its own row; the effects are conserved
    across both kinds."""
    lines = [
        _trigger_line(),
        _trigger_line(
            line_id=UUID("00000000-0000-0000-0000-00000000c002"),
            account_role="CONTRACT_LIABILITY",
            amount_txn=D("40.00"),
        ),
        _line(),  # event 4, revenue credit 300.00
    ]
    found = out_of_period_register.aggregate(lines)
    assert found.line_count == 3
    (event_row, trigger_row) = found.rows
    assert event_row["attribution_kind"] == "EVENT_SET"
    assert event_row["event_key"] == "event:K-01:4:SUBJECT"
    assert trigger_row["attribution_kind"] == "TRIGGER"
    assert trigger_row["event_key"] == "trigger:POLICY_RERUN:00000000-0000-0000-0000-0000000000f1"
    assert trigger_row["row_key"] == "FY2026-P01:FY2026-P02:" + trigger_row["event_key"]
    assert trigger_row["contract_external_id"] == "K-01"
    assert trigger_row["event_type"] is None and trigger_row["effective_date"] is None
    assert trigger_row["event_type_label"] == "Policy rerun"
    assert trigger_row["recorded_at"] == T0 + timedelta(days=2)
    assert trigger_row["recorded_by"] == ACTOR
    assert trigger_row["origin"] is None and trigger_row["approval_request_no"] is None
    assert trigger_row["revenue_effect"] == _usd("40.00")
    assert trigger_row["balance_effect"] == _usd("-40.00")
    totals = out_of_period_register.control_totals(found.rows, line_count=found.line_count)
    assert totals["revenue_effect_total"] == {"USD": "340.00"}  # 300.00 + 40.00, both kinds
    assert totals["balance_effect_total"] == {"USD": "-40.00"}
    document = _json(
        ReportData(columns=out_of_period_register.COLUMNS, rows=found.rows, control_totals=totals),
        "out_of_period_register",
    )
    assert [row["attribution_kind"] for row in document["rows"]] == ["EVENT_SET", "TRIGGER"]
    # neither an event set nor a computation: still the named refusal
    with pytest.raises(Problem) as raised:
        out_of_period_register.aggregate([_trigger_line(trigger=None, computation_id=None)])
    assert raised.value.errors[0].rule_id == "OUT_OF_PERIOD_ATTRIBUTION_MISSING"


def test_r5_joined_event_keys_are_injective_codex_witness() -> None:
    """D-98 candidate 104 (Codex C6-RPT-R5): a singleton contract whose external id is
    ``K:1|event:K`` at stream version 2 and the two-event set of contract ``K`` at versions 1 and
    2 must not share a key. Components are CV-21 percent-encoded before joining (``%`` first, then
    ``:`` and ``|``), so the two sets stay two rows with their own metadata and distinct keys;
    conservation is unchanged. Fail-first on 976cd8d2: both produced ``event:K:1|event:K:2`` and
    merged into one row."""
    witness = _line(
        contract_external_id="K:1|event:K",
        stream_version=2,
        event_type="BILLING_RECORDED",
        amount_txn=D("-10.00"),
    )
    pair = _cumulative(
        line_id=UUID("00000000-0000-0000-0000-00000000d001"),
        amount_txn=D("-20.00"),
        events=(
            _event(1, contract_external_id="K", event_type="CONTRACT_BOOKED"),
            _event(2, contract_external_id="K", event_type="BILLING_RECORDED"),
        ),
    )
    found = out_of_period_register.aggregate([witness, pair])
    assert found.line_count == 2
    keys = [row["event_key"] for row in found.rows]
    assert len(keys) == 2 and len(set(keys)) == 2, keys
    assert "event:K%3A1%7Cevent%3AK:2:SUBJECT" in keys
    assert "event:K:1|event:K:2:SUBJECT" in keys
    by_key = {row["event_key"]: row for row in found.rows}
    single = by_key["event:K%3A1%7Cevent%3AK:2:SUBJECT"]
    assert single["contract_external_id"] == "K:1|event:K"  # attributes stay raw
    assert single["event_type"] == "BILLING_RECORDED"
    assert single["revenue_effect"] == _usd("10.00")
    pair_row = by_key["event:K:1|event:K:2:SUBJECT"]
    assert pair_row["contract_external_id"] == "K"
    assert pair_row["event_type"] == "CONTRACT_BOOKED|BILLING_RECORDED"
    assert pair_row["revenue_effect"] == _usd("20.00")
    totals = out_of_period_register.control_totals(found.rows, line_count=found.line_count)
    assert totals["revenue_effect_total"] == {"USD": "30.00"}  # conservation unchanged
    # the encoding: percent first, then the component and set delimiters; plain ids unchanged
    assert out_of_period_register.event_key("K-01", 4) == "event:K-01:4"
    assert out_of_period_register.event_key("A%B:C|D", 7) == "event:A%25B%3AC%7CD:7"


def test_r3_trigger_rows_require_persisted_subject_proof_d98_102a() -> None:
    """D-98 candidate 102a (Codex packet 1130): an empty T-SL-12 set is a TRIGGER row only on
    persisted, subject-specific proof — the computation's stored lineage for the line's subject
    is empty AND its trigger is non-event. A NULL-event cumulative line persisted before T-SL-12
    and linked to an event-driven computation (COMMAND) refuses; so does an empty set whose
    subject had first-included events (the line lost its lineage), or whose proof the reader
    could not establish. A genuine trigger-only computation attributes."""
    historical = _trigger_line(trigger="COMMAND", cause_event_count=0)
    with pytest.raises(Problem) as raised:
        out_of_period_register.aggregate([historical])
    assert raised.value.errors[0].rule_id == "OUT_OF_PERIOD_ATTRIBUTION_MISSING"
    lost_lineage = _trigger_line(trigger="POLICY_RERUN", cause_event_count=2)
    with pytest.raises(Problem):
        out_of_period_register.aggregate([lost_lineage])
    unproven = _trigger_line(trigger="POLICY_RERUN", cause_event_count=None)
    with pytest.raises(Problem):
        out_of_period_register.aggregate([unproven])
    for trigger in ("POLICY_RERUN", "RESTATE"):
        (row,) = out_of_period_register.aggregate(
            [_trigger_line(trigger=trigger, cause_event_count=0)]
        ).rows
        assert row["attribution_kind"] == "TRIGGER" and row["event_key"].startswith("trigger:")
    # S15-R-18b rev 1.166 (item FX-REPUBLISH-DIRTY-1; the supervisor's ruling of 2026-10-02): a
    # republished rate moves the functional amount alone. FX_REPUBLISH attributes a line whose
    # transaction amount is nil, and a line that moves a transaction amount under that trigger
    # is refused with its proof in hand — it was not made by the republication.
    (row,) = out_of_period_register.aggregate(
        [_trigger_line(trigger="FX_REPUBLISH", cause_event_count=0, amount_txn=D("0.00"))]
    ).rows
    assert row["attribution_kind"] == "TRIGGER"
    assert row["event_key"] == "trigger:FX_REPUBLISH:00000000-0000-0000-0000-0000000000f1"
    assert row["event_type_label"] == "Fx republish"
    with pytest.raises(Problem) as moved:
        out_of_period_register.aggregate(
            [_trigger_line(trigger="FX_REPUBLISH", cause_event_count=0)]
        )
    assert moved.value.errors[0].rule_id == "OUT_OF_PERIOD_ATTRIBUTION_MISSING"
    for trigger in ("COMMAND", "REPLAY_VERIFY", "UPGRADE_VALIDATE", "CLOSE_RELEASE", "MIGRATION"):
        with pytest.raises(Problem):
            out_of_period_register.aggregate([_trigger_line(trigger=trigger, cause_event_count=0)])


def test_r4_state_from_the_full_transition_history_across_retry_cycles() -> None:
    """D-98 candidate 102a (Codex packet 1130), through the composed path ``build`` uses
    (``state_as_of`` over the reader's transition history, not a single failure time): the state
    as of the cutoff is the latest transition at or before it across every cycle. (a) Approval day
    1, failure day 3, successful re-export day 3 + 6 h, current state exported, cutoff day 3 + 1 h
    → failed, not approved. (b) Repeated failures — failed day 3, re-exported day 4, failed day 5 —
    give the eligible one at each cutoff. (c) A history with no failure and a stored later export
    leaves the stored timestamps in charge."""
    retried = _run_record(
        run_state="exported",
        run_no="JR-000050",
        run_approved_at=T0 + timedelta(days=1),
        run_exported_at=T0 + timedelta(days=3, hours=6),  # the retry overwrote the export time
        run_acknowledged_at=None,
        run_cancelled_at=None,
        batch_acknowledged_at=None,
        run_updated_at=T0 + timedelta(days=3, hours=6),
    )
    history = (
        je_population.Transition(T0 + timedelta(days=1), 1, "approved"),
        je_population.Transition(T0 + timedelta(days=3), 2, "failed"),
        je_population.Transition(T0 + timedelta(days=3, hours=6), 3, "exported"),
    )
    at = T0 + timedelta(days=3, hours=1)
    assert je_population.state_as_of(retried, at, history).run_state == "failed"
    assert je_population.state_as_of(retried, T0 + timedelta(days=2), history).run_state == (
        "approved"
    )
    assert je_population.state_as_of(retried, T0 + timedelta(days=4), history).run_state == (
        "exported"
    )
    repeated = _run_record(
        run_state="failed",
        run_no="JR-000051",
        run_approved_at=T0 + timedelta(days=1),
        run_exported_at=T0 + timedelta(days=4),
        run_acknowledged_at=None,
        run_cancelled_at=None,
        batch_acknowledged_at=None,
        run_updated_at=T0 + timedelta(days=5),
    )
    cycles = (
        je_population.Transition(T0 + timedelta(days=1), 1, "approved"),
        je_population.Transition(T0 + timedelta(days=3), 2, "failed"),
        je_population.Transition(T0 + timedelta(days=4), 3, "exported"),
        je_population.Transition(T0 + timedelta(days=5), 4, "failed"),
    )
    assert je_population.state_as_of(
        repeated, T0 + timedelta(days=3, hours=1), cycles
    ).run_state == (
        "failed"  # the eligible failure is day 3, not the later day 5 one
    )
    assert je_population.state_as_of(
        repeated, T0 + timedelta(days=4, hours=1), cycles
    ).run_state == ("exported")
    assert je_population.state_as_of(
        repeated, T0 + timedelta(days=5, hours=1), cycles
    ).run_state == ("failed")
    no_failure = _run_record(run_updated_at=T0 + timedelta(days=9))
    assert je_population.state_as_of(no_failure, T0 + timedelta(days=2, hours=1), ()).run_state == (
        "exported"
    )


def test_r3_member_b_event_moves_member_a_group_lineage_d98_102b() -> None:
    """D-98 candidate 102b (Q-C6-RPT-6): in a combination group a COMMAND computation whose only
    first-included event belongs to member B moves member A's allocation. A's late line carries
    the GROUP's set (B's event) as ``lineage_scope`` GROUP — an EVENT_SET row, not a refusal;
    the R5 key is B's encoded event key. A line whose set holds its own subject's event is
    SUBJECT; a trigger row has no scope; the pre-T-SL-12 refusal (empty set, event-driven trigger,
    stored lineage present) is unchanged."""
    group_line = _cumulative(
        line_id=UUID("00000000-0000-0000-0000-00000000e001"),
        contract_external_id="A",
        subject_contract_external_id="A",  # dimensions.contract_key of a single-member subject
        amount_txn=D("-15.00"),
        events=(_event(3, contract_external_id="B", event_type="CONTRACT_MODIFIED"),),
        trigger="COMMAND",
        computation_id=UUID("00000000-0000-0000-0000-0000000000f2"),
        cause_event_count=1,
    )
    own_line = _cumulative(
        line_id=UUID("00000000-0000-0000-0000-00000000e002"),
        contract_external_id="A",
        subject_contract_external_id="A",
        amount_txn=D("-5.00"),
        events=(_event(4, contract_external_id="A"),),
    )
    found = out_of_period_register.aggregate([group_line, own_line, _trigger_line()])
    by_key = {row["event_key"]: row for row in found.rows}
    group_row = by_key["event:B:3:GROUP"]
    assert group_row["attribution_kind"] == "EVENT_SET"
    assert group_row["lineage_scope"] == "GROUP"
    assert group_row["contract_external_id"] == "B"  # the members' contract, raw
    assert group_row["revenue_effect"] == _usd("15.00")
    assert by_key["event:A:4:SUBJECT"]["lineage_scope"] == "SUBJECT"
    (trigger_row,) = [row for row in found.rows if row["attribution_kind"] == "TRIGGER"]
    assert trigger_row["lineage_scope"] is None
    totals = out_of_period_register.control_totals(found.rows, line_count=found.line_count)
    assert totals["revenue_effect_total"] == {"USD": "60.00"}  # 15 + 5 + 40, conserved
    # a multi-member subject (no dimensions.contract_key) is always SUBJECT
    multi = _cumulative(
        line_id=UUID("00000000-0000-0000-0000-00000000e003"),
        contract_external_id="A",
        events=(_event(3, contract_external_id="B", event_type="CONTRACT_MODIFIED"),),
    )
    (row,) = out_of_period_register.aggregate([multi]).rows
    assert row["lineage_scope"] == "SUBJECT"
    # unchanged: a NULL-event cumulative line of an event-driven computation refuses
    with pytest.raises(Problem):
        out_of_period_register.aggregate([_trigger_line(trigger="COMMAND", cause_event_count=1)])
    # the historical single-event fixture is SUBJECT
    (single,) = out_of_period_register.aggregate([_line()]).rows
    assert single["lineage_scope"] == "SUBJECT"


def test_r4_equal_time_transitions_resolve_by_the_audit_chain_not_the_spelling() -> None:
    """D-98 candidate 102c (Codex packet 1210, RPT4-H1): a declared failure and the retry's export
    at the same instant T (both audited; the export has the higher chain_seq), acknowledged at T2;
    with T ≤ K < T2 the state is exported — the chain's durable sequence breaks the tie, never the
    spelling ("failed" > "exported"). The reversed history order gives the same answer; the later
    acknowledgement never leaks before T2; the stored-only tie (no audit) falls to the later E-34
    stage (documented fallback)."""
    T = T0 + timedelta(days=3)
    T2 = T0 + timedelta(days=4)
    run = _run_record(
        run_state="acknowledged",
        run_no="JR-000060",
        run_approved_at=T0 + timedelta(days=1),
        run_exported_at=T,
        run_acknowledged_at=T2,
        run_cancelled_at=None,
        batch_acknowledged_at=T2,
        run_updated_at=T2,
    )
    history = (
        je_population.Transition(T0 + timedelta(days=1), 10, "approved"),
        je_population.Transition(T, 11, "failed"),
        je_population.Transition(T, 12, "exported"),  # the retry, same instant, later in the chain
        je_population.Transition(T2, 13, "acknowledged"),
    )
    at_k = T + timedelta(minutes=30)
    assert je_population.state_as_of(run, at_k, history).run_state == "exported"
    assert je_population.state_as_of(run, at_k, tuple(reversed(history))).run_state == "exported"
    assert (
        je_population.state_as_of(run, T2 - timedelta(seconds=1), history).acknowledged_at is None
    )
    assert je_population.state_as_of(run, T2, history).run_state == "acknowledged"
    # the failure alone at T (no audited retry at T): failed until the stored later export at T + 6
    # h
    only_failure = (
        je_population.Transition(T0 + timedelta(days=1), 10, "approved"),
        je_population.Transition(T, 11, "failed"),
    )
    retried_later = _run_record(
        run_state="exported",
        run_no="JR-000061",
        run_exported_at=T + timedelta(hours=6),
        run_acknowledged_at=None,
        batch_acknowledged_at=None,
        run_updated_at=T + timedelta(hours=6),
    )
    assert je_population.state_as_of(retried_later, at_k, only_failure).run_state == "failed"
    assert je_population.state_as_of(
        retried_later, T + timedelta(hours=7), only_failure
    ).run_state == ("exported")
    # stored-only tie (nothing audited at that instant): the later E-34 stage, explicitly, not the
    # spelling
    stored_tie = _run_record(
        run_state="acknowledged",
        run_no="JR-000062",
        run_exported_at=T,
        run_acknowledged_at=T,
        batch_acknowledged_at=T,
        run_updated_at=T2,
    )
    assert je_population.state_as_of(stored_tie, at_k, ()).run_state == "acknowledged"


def test_r5_scope_is_part_of_the_row_identity_both_orders_identical() -> None:
    """D-98 candidate 102c (Codex packet 1210, RPT5 mixed scope): B's own late line (subject B, its
    event B:3 → SUBJECT) and A's late line carrying the group's set {B:3} (→ GROUP), same periods:
    two rows with distinct public keys ``event:B:3:SUBJECT`` and ``event:B:3:GROUP``, never one row
    labelled by whichever line came first; both input orders give byte-identical JSON; line count
    and monetary conservation hold across the split."""
    b_own = _cumulative(
        line_id=UUID("00000000-0000-0000-0000-00000000f001"),
        contract_external_id="B",
        subject_contract_external_id="B",
        amount_txn=D("-25.00"),
        events=(_event(3, contract_external_id="B", event_type="CONTRACT_MODIFIED"),),
    )
    a_group = _cumulative(
        line_id=UUID("00000000-0000-0000-0000-00000000f002"),
        contract_external_id="A",
        subject_contract_external_id="A",
        amount_txn=D("-15.00"),
        events=(_event(3, contract_external_id="B", event_type="CONTRACT_MODIFIED"),),
    )
    forward = out_of_period_register.aggregate([b_own, a_group])
    backward = out_of_period_register.aggregate([a_group, b_own])
    assert forward.line_count == backward.line_count == 2
    assert [row["row_key"] for row in forward.rows] == [
        "FY2026-P01:FY2026-P02:event:B:3:GROUP",
        "FY2026-P01:FY2026-P02:event:B:3:SUBJECT",
    ]
    by_key = {row["event_key"]: row for row in forward.rows}
    assert by_key["event:B:3:SUBJECT"]["lineage_scope"] == "SUBJECT"
    assert by_key["event:B:3:SUBJECT"]["revenue_effect"] == _usd("25.00")
    assert by_key["event:B:3:GROUP"]["lineage_scope"] == "GROUP"
    assert by_key["event:B:3:GROUP"]["revenue_effect"] == _usd("15.00")
    totals = out_of_period_register.control_totals(forward.rows, line_count=forward.line_count)
    assert totals["revenue_effect_total"] == {"USD": "40.00"} and totals["row_count"] == 2
    f_json = manifest_output.dataset_bytes(
        _report("out_of_period_register"),
        {},
        ReportData(
            columns=out_of_period_register.COLUMNS, rows=forward.rows, control_totals=totals
        ),
    )
    b_json = manifest_output.dataset_bytes(
        _report("out_of_period_register"),
        {},
        ReportData(
            columns=out_of_period_register.COLUMNS,
            rows=backward.rows,
            control_totals=out_of_period_register.control_totals(
                backward.rows, line_count=backward.line_count
            ),
        ),
    )
    assert f_json == b_json  # byte-identical regardless of input order
    assert csv_output.render_csv(
        ReportData(columns=out_of_period_register.COLUMNS, rows=forward.rows, control_totals=totals)
    ) == csv_output.render_csv(
        ReportData(
            columns=out_of_period_register.COLUMNS, rows=backward.rows, control_totals=totals
        )
    )
    # a trigger row's identity has no scope component
    (trigger_row,) = out_of_period_register.aggregate([_trigger_line()]).rows
    assert trigger_row["row_key"] == (
        "FY2026-P01:FY2026-P02:trigger:POLICY_RERUN:00000000-0000-0000-0000-0000000000f1"
    )


# --- RPT-OOP-ROWKEY-1 (supervisor ruling R-112 (j); ENGINE_SPEC_B S15-R-18a rev 1.110) ------------


def test_one_event_set_over_several_origin_periods_is_one_row_key_per_origin() -> None:
    """A contract booked after seven of its periods were closed posts each closed month into the
    first open period with its own origin: one event set, seven rows — and seven row keys, each
    the row's whole key (origin period, posting period, event key). Fail-first: every row carried
    the event key ``event:LATE-ARRIVAL-01:1|event:LATE-ARRIVAL-01:2:SUBJECT`` as its ``row_key``,
    so the rows formed no dataset (S15-R-18) and the lock of the posting period was refused."""
    months = [f"FY2026-P{number:02d}" for number in range(1, 8)]
    booked = (
        _event(1, contract_external_id="LATE-ARRIVAL-01", event_type="CONTRACT_BOOKED"),
        _event(2, contract_external_id="LATE-ARRIVAL-01", event_type="CONTRACT_ACTIVATED"),
    )
    lines = [
        _cumulative(
            line_id=UUID(int=0xD000 + index * 2 + side),
            origin_period_key=origin,
            posting_period_key="FY2026-P08",
            contract_external_id="LATE-ARRIVAL-01",
            account_role=role,
            amount_txn=amount,
            events=booked,
        )
        for index, origin in enumerate(months)
        for side, (role, amount) in enumerate(
            (("REVENUE", D("-100.00")), ("CONTRACT_LIABILITY", D("100.00")))
        )
    ]
    found = out_of_period_register.aggregate(lines)
    event_key = "event:LATE-ARRIVAL-01:1|event:LATE-ARRIVAL-01:2:SUBJECT"
    assert [row["event_key"] for row in found.rows] == [event_key] * 7
    assert [row["row_key"] for row in found.rows] == [
        f"{origin}:FY2026-P08:{event_key}" for origin in months
    ]
    assert [row["origin_period_key"] for row in found.rows] == months
    # the rows are a dataset: the S15-R-18 row key is unique, and so is the S15-R-20 key tuple
    assert len({row["row_key"] for row in found.rows}) == len(found.rows) == 7
    assert len({tuple(row[column] for column in OOP_KEY) for row in found.rows}) == 7
    totals = out_of_period_register.control_totals(found.rows, line_count=found.line_count)
    assert (totals["row_count"], totals["line_count"]) == (7, 14)
    assert totals["revenue_effect_total"] == {"USD": "700.00"}


def test_the_row_key_is_injective_over_its_three_components() -> None:
    """The period keys are CV-21-encoded as every other component, so a ``:`` inside a period key
    cannot move the boundary between the periods and the event key; the event key is the
    attribution's own single-string form, unchanged in the ``event_key`` column."""
    key = out_of_period_register.row_key
    assert key("FY2026-P01", "FY2026-P08", "event:K-01:4:SUBJECT") == (
        "FY2026-P01:FY2026-P08:event:K-01:4:SUBJECT"
    )
    assert key("A:B", "C", "event:K:1:SUBJECT") != key("A", "B:C", "event:K:1:SUBJECT")
    assert key("A:B", "C", "event:K:1:SUBJECT") == "A%3AB:C:event:K:1:SUBJECT"
    assert key("P1", "P2", "trigger:RESTATE:c0ffee") == "P1:P2:trigger:RESTATE:c0ffee"
