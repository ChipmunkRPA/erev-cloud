"""RPT-32 ``contract_cost_rollforward`` pure core — the governed ``COST_ROLLFORWARD`` dataset
(SCREENS_B §5.6.1 RPT-32 rev 1.14; ENGINE_SPEC_B §15.2.6 S15-R-17, §15.2.7 S15-R-20a / S15-R-20b;
04 T-CLS-05; supervisor rulings D-98 85 / 97; PRD WLD-X-08, WLD-X-20; BUILD_SPEC RPS-12).

No database: the movements are the JET-09 subledger lines of K-02 and K-09 written here from the
PRD figures (the figures of the interim wide builder of lane F-RPS + ENG-E1 are kept); ``build``
(the subledger reader) is exercised by the RPS-12 database test once a DB slot is admitted.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid5

import pytest
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import contract_cost_rollforward as costs
from erev_api.domain.reports.builders.contract_cost_rollforward import (
    COLUMNS,
    KEY_COLUMNS,
    LINE_CODES,
    MOVEMENT_LINES,
    TO_COST_ROLLFORWARD_BALANCES,
    CostMovement,
    CostRollforwardRefusal,
    check_key_columns,
    classify,
    control_totals,
    cost_tie,
    dataset_rows,
    rollforward,
)
from erev_api.domain.reports.tie_outs import BalanceRow

NS = UUID("00000000-0000-0000-0000-000000000032")
ENTITY = uuid5(NS, "AVM-US")
D = Decimal
OBTAIN, FULFIL = "COST_TO_OBTAIN_ASSET", "COST_TO_FULFILL_ASSET"
CAPITALIZATION, AMORTIZATION, IMPAIRMENT = (
    "CONTRACT_COST_CAPITALIZATION",
    "CONTRACT_COST_AMORTIZATION",
    "CONTRACT_COST_IMPAIRMENT",
)
HEADER = (
    "entity_code",
    "cost_kind",
    "line_code",
    "category_label",
    "line_label",
    "currency",
    "amount",
)


def _movement(
    external_id: str,
    role: str,
    kind: str,
    dr_cr: str,
    amount: str,
    *,
    in_range: bool,
    reason: str | None = None,
    currency: str = "USD",
    entity: str = "AVM-US",
) -> CostMovement:
    cost_kind, line_code, signed = classify(role, kind, dr_cr, reason, _minor(amount))
    return CostMovement(
        entity_code=entity,
        cost_kind=cost_kind,
        line_code=line_code,
        amount_minor=signed,
        currency=currency,
        in_range=in_range,
        contract_external_id=external_id,
    )


def _minor(amount: str) -> int:
    return int(D(amount).scaleb(2))


def _balance(external_id: str, carrying: str, *, currency: str = "USD") -> BalanceRow:
    return BalanceRow(
        contract_id=uuid5(NS, external_id),
        external_id=external_id,
        customer_name=None,
        entity_id=ENTITY,
        entity_code="AVM-US",
        currency=currency,
        version_id=uuid5(NS, f"{external_id}/v"),
        values={"cost_asset_carrying": D(carrying)},
    )


def _amount(row: dict[str, object]) -> str:
    cell = row["amount"]
    assert isinstance(cell, dict) and set(cell) == {"amount", "currency"}  # typed Money cell
    return str(cell["amount"])


def test_line_codes_and_header_are_the_governed_key() -> None:
    """S15-R-17 order, eight codes; the dataset header carries the KeySpec key columns
    (``cost_kind``, ``line_code``) as codes, the labels as attributes, one money field."""
    assert LINE_CODES == (
        "OPENING",
        "ADDITIONS",
        "CLAWBACKS",
        "AMORTIZATION",
        "ACCELERATION",
        "IMPAIRMENT",
        "IMPAIRMENT_REVERSAL",
        "CLOSING",
    )
    assert MOVEMENT_LINES == LINE_CODES[1:-1]
    assert KEY_COLUMNS == ("cost_kind", "line_code")
    keys = [column.key for column in COLUMNS if column.key != "section"]
    assert tuple(keys) == HEADER
    kinds = {column.key: column.kind for column in COLUMNS}
    assert kinds["cost_kind"] == kinds["line_code"] == kinds["entity_code"] == "code"
    assert kinds["amount"] == "money" and kinds["category_label"] == kinds["line_label"] == "text"
    assert costs.LINE_LABELS["ACCELERATION"] == "Acceleration on termination"


def test_classify_jet_09_lines_by_kind_side_and_reason() -> None:
    """S15-R-17 with D-98 19: a CAPITALIZATION debit is ADDITIONS, a credit or reason CLAWBACK is
    CLAWBACKS; an AMORTIZATION credit is AMORTIZATION, or ACCELERATION under
    TERMINATION_ACCELERATION; an IMPAIRMENT credit is IMPAIRMENT and a debit its reversal; the
    fulfilment role maps to FULFILL; another role refuses by name."""
    assert classify(OBTAIN, CAPITALIZATION, "D", None, 1200000) == ("OBTAIN", "ADDITIONS", 1200000)
    assert classify(OBTAIN, CAPITALIZATION, "C", None, 50000) == ("OBTAIN", "CLAWBACKS", -50000)
    assert classify(OBTAIN, CAPITALIZATION, "C", "CLAWBACK", 50000) == (
        "OBTAIN",
        "CLAWBACKS",
        -50000,
    )
    assert classify(OBTAIN, CAPITALIZATION, "D", "LATE_EVENT", 100) == ("OBTAIN", "ADDITIONS", 100)
    assert classify(OBTAIN, AMORTIZATION, "C", None, 49315) == ("OBTAIN", "AMORTIZATION", -49315)
    assert classify(OBTAIN, AMORTIZATION, "C", "TERMINATION_ACCELERATION", 1800000) == (
        "OBTAIN",
        "ACCELERATION",
        -1800000,
    )
    assert classify(OBTAIN, AMORTIZATION, "D", "VOID", 100) == ("OBTAIN", "AMORTIZATION", 100)
    assert classify(OBTAIN, IMPAIRMENT, "C", None, 1500000) == ("OBTAIN", "IMPAIRMENT", -1500000)
    assert classify(FULFIL, IMPAIRMENT, "D", None, 1000000) == (
        "FULFILL",
        "IMPAIRMENT_REVERSAL",
        1000000,
    )
    with pytest.raises(CostRollforwardRefusal) as refused:
        classify("CONTRACT_ASSET", CAPITALIZATION, "D", None, 1)
    assert refused.value.column == "cost_kind" and "CONTRACT_ASSET" in str(refused.value)
    with pytest.raises(CostRollforwardRefusal) as unclassified:
        classify(OBTAIN, "BILLING", "D", None, 1)
    assert unclassified.value.column == "line_code" and "BILLING" in str(unclassified.value)


def test_cost_rollforward_k09_k02_september_2026() -> None:
    """September 2026 (RPS-12 figures): K-02 ``COM-2026-0002`` 12,000.00 capitalised 1 Jan with
    3,994.52 amortised through August opens at 8,005.48, amortises 493.15 and closes at 7,512.33
    (WLD-X-08); K-09 adds 6,480.00 and amortises 177.37 to 6,302.63 (WLD-X-20). One row per
    (cost_kind, line_code): OBTAIN OPENING 8,005.48, ADDITIONS 6,480.00, AMORTIZATION (670.52),
    CLOSING 13,814.96, the other lines 0.00; no FULFILL rows (no asset in scope); control totals
    opening / closing; ``TO_COST_ROLLFORWARD_BALANCES`` passes against Σ ``cost_asset_carrying``
    13,814.96 and fails when a balance is missing."""
    movements = [
        _movement("SF-ORD-10002", OBTAIN, CAPITALIZATION, "D", "12000.00", in_range=False),
        _movement("SF-ORD-10002", OBTAIN, AMORTIZATION, "C", "3994.52", in_range=False),
        _movement("SF-ORD-10002", OBTAIN, AMORTIZATION, "C", "493.15", in_range=True),
        _movement("SF-ORD-10417", OBTAIN, CAPITALIZATION, "D", "6480.00", in_range=True),
        _movement("SF-ORD-10417", OBTAIN, AMORTIZATION, "C", "177.37", in_range=True),
    ]
    lines, currencies = rollforward(movements)
    assert list(lines) == [("AVM-US", "OBTAIN")] and currencies == {"AVM-US": "USD"}
    obtain = lines[("AVM-US", "OBTAIN")]
    assert {code: value for code, value in obtain.items() if value} == {
        "OPENING": 800548,
        "ADDITIONS": 648000,
        "AMORTIZATION": -67052,
        "CLOSING": 1381496,
    }
    rows = dataset_rows(lines, currencies)
    assert [row["row_key"] for row in rows] == [f"OBTAIN:{code}" for code in LINE_CODES]
    assert [tuple(row[key] for key in KEY_COLUMNS) for row in rows] == [
        ("OBTAIN", code) for code in LINE_CODES
    ]
    assert {row["section"] for row in rows} == {1}
    assert all(row["entity_code"] == "AVM-US" and row["currency"] == "USD" for row in rows)
    assert rows[0]["category_label"] == "Costs to obtain a contract"
    assert rows[0]["line_label"] == "Opening carrying amount"
    assert [_amount(row) for row in rows] == [
        "8005.48",
        "6480.00",
        "0.00",
        "-670.52",
        "0.00",
        "0.00",
        "0.00",
        "13814.96",
    ]
    check_key_columns(rows)
    assert control_totals(lines, currencies) == {
        "opening": {"USD": "8005.48"},
        "closing": {"USD": "13814.96"},
    }
    tie = cost_tie(
        lines,
        currencies,
        [_balance("SF-ORD-10002", "7512.33"), _balance("SF-ORD-10417", "6302.63")],
    )
    assert (tie["code"], tie["result"]) == (TO_COST_ROLLFORWARD_BALANCES, "PASS")
    assert tie["expected"] == tie["actual"] == [{"amount": "13814.96", "currency": "USD"}]
    broken = cost_tie(lines, currencies, [_balance("SF-ORD-10002", "7512.33")])
    assert broken["result"] == "FAIL"


def test_acceleration_and_clawback_are_their_own_lines() -> None:
    """MOD-CHK-112 June 2027 shape: the month's amortisation 1,000.00 and the acceleration
    18,000.00 (reason TERMINATION_ACCELERATION) are two lines; a clawback 2,000.00 by reason
    CLAWBACK is a third; OPENING + Σ movements = CLOSING = 0.00 for a fully amortised asset."""
    movements = [
        _movement("C-TERM", OBTAIN, CAPITALIZATION, "D", "36000.00", in_range=False),
        _movement("C-TERM", OBTAIN, AMORTIZATION, "C", "15000.00", in_range=False),
        _movement("C-TERM", OBTAIN, AMORTIZATION, "C", "1000.00", in_range=True),
        _movement(
            "C-TERM",
            OBTAIN,
            AMORTIZATION,
            "C",
            "18000.00",
            in_range=True,
            reason="TERMINATION_ACCELERATION",
        ),
        _movement(
            "C-TERM", OBTAIN, CAPITALIZATION, "C", "2000.00", in_range=True, reason="CLAWBACK"
        ),
    ]
    lines, currencies = rollforward(movements)
    obtain = lines[("AVM-US", "OBTAIN")]
    assert (
        obtain["OPENING"],
        obtain["AMORTIZATION"],
        obtain["ACCELERATION"],
        obtain["CLAWBACKS"],
    ) == (
        2100000,
        -100000,
        -1800000,
        -200000,
    )
    assert obtain["CLOSING"] == 0
    assert obtain["OPENING"] + sum(obtain[code] for code in MOVEMENT_LINES) == obtain["CLOSING"]
    rows = dataset_rows(lines, currencies)
    by_line = {row["line_code"]: _amount(row) for row in rows}
    assert (by_line["ACCELERATION"], by_line["AMORTIZATION"], by_line["CLAWBACKS"]) == (
        "-18000.00",
        "-1000.00",
        "-2000.00",
    )
    assert by_line["CLOSING"] == "0.00"  # a typed zero, never "-0.00"


def test_ifrs15_reversal_second_kind_and_two_entities() -> None:
    """CHK-131 year 2 under IFRS15: opening 15,000.00, amortisation (5,000.00), reversal 10,000.00,
    closing 20,000.00. A FULFILL asset adds its own eight rows after the OBTAIN rows; a second
    entity prefixes the row keys with its code and keeps its own currency."""
    movements = [
        _movement("C-COST", OBTAIN, CAPITALIZATION, "D", "40000.00", in_range=False),
        _movement("C-COST", OBTAIN, AMORTIZATION, "C", "10000.00", in_range=False),
        _movement("C-COST", OBTAIN, IMPAIRMENT, "C", "15000.00", in_range=False),
        _movement("C-COST", OBTAIN, AMORTIZATION, "C", "5000.00", in_range=True),
        _movement("C-COST", OBTAIN, IMPAIRMENT, "D", "10000.00", in_range=True),
        _movement("C-FUL", FULFIL, CAPITALIZATION, "D", "300.00", in_range=True),
        _movement(
            "C-GBP",
            OBTAIN,
            CAPITALIZATION,
            "D",
            "300.00",
            in_range=True,
            currency="GBP",
            entity="AVM-UK",
        ),
    ]
    lines, currencies = rollforward(movements)
    obtain = lines[("AVM-US", "OBTAIN")]
    assert (
        obtain["OPENING"],
        obtain["AMORTIZATION"],
        obtain["IMPAIRMENT_REVERSAL"],
        obtain["CLOSING"],
    ) == (
        1500000,
        -500000,
        1000000,
        2000000,
    )
    assert currencies == {"AVM-UK": "GBP", "AVM-US": "USD"}
    rows = dataset_rows(lines, currencies)
    assert [row["row_key"] for row in rows][:2] == [
        "AVM-UK:OBTAIN:OPENING",
        "AVM-UK:OBTAIN:ADDITIONS",
    ]
    assert [row["row_key"] for row in rows][8:10] == [
        "AVM-US:OBTAIN:OPENING",
        "AVM-US:OBTAIN:ADDITIONS",
    ]
    assert [row["row_key"] for row in rows][16:18] == [
        "AVM-US:FULFILL:OPENING",
        "AVM-US:FULFILL:ADDITIONS",
    ]
    assert len(rows) == 24
    uk = next(row for row in rows if row["row_key"] == "AVM-UK:OBTAIN:CLOSING")
    assert uk["amount"] == {"amount": "300.00", "currency": "GBP"}
    check_key_columns(rows)
    assert control_totals(lines, currencies) == {
        "opening": {"GBP": "0.00", "USD": "15000.00"},
        "closing": {"GBP": "300.00", "USD": "20300.00"},
    }


def test_refusals_by_name() -> None:
    """A second currency inside one (entity, cost kind) cannot be one row per key and refuses by
    name; a row set lacking a key column or repeating a key refuses by name (S15-R-20a / 20b)."""
    with pytest.raises(CostRollforwardRefusal) as mixed:
        rollforward(
            [
                _movement("A", OBTAIN, CAPITALIZATION, "D", "1.00", in_range=True),
                _movement("B", OBTAIN, CAPITALIZATION, "D", "1.00", in_range=True, currency="EUR"),
            ]
        )
    assert mixed.value.column == "currency" and "AVM-US" in str(mixed.value)
    lines, currencies = rollforward(
        [_movement("A", OBTAIN, CAPITALIZATION, "D", "1.00", in_range=True)]
    )
    rows = dataset_rows(lines, currencies)
    with pytest.raises(CostRollforwardRefusal) as duplicate:
        check_key_columns([*rows, dict(rows[0])])
    assert duplicate.value.column == "line_code" and "OBTAIN" in str(duplicate.value)
    with pytest.raises(CostRollforwardRefusal) as missing:
        check_key_columns([{**rows[0], "line_code": ""}])
    assert missing.value.column == "line_code"


def test_registered_with_its_non_false_default() -> None:
    """RPS-12 registration (supervisor dispatch, D-98 85): the builder is in ``BUILDERS`` and its
    ``currency_view`` default ``functional`` is named in ``PARAMETER_DEFAULTS`` (D-87 L6-3-Q-29)."""
    assert framework.BUILDERS[costs.CODE] is costs.build
    assert framework.PARAMETER_DEFAULTS[costs.CODE] == {"currency_view": "functional"}
    assert costs.CODE == "contract_cost_rollforward"
