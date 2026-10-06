"""RPT-36 ``balance_aging`` pure core (SCREENS_B §5.6.1 RPT-36; POLICIES §5.7 CHK-117; 03
REQ-BIL-013; BUILD_SPEC RPS-12 prep, lane F-RPS + ENG-E1).

No database: layers are built here from the CHK-010 / CHK-117 figures; ``build`` (the subledger
reader) is exercised by the RPS-12 database test once the lane is admitted to a DB slot.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5

from erev_api.domain.reports.builders import balance_aging as aging
from erev_api.domain.reports.builders.balance_aging import (
    BUCKET_FIELDS,
    TO_AGING_EQ_BALANCES,
    Layer,
    aged_rows,
    aging_tie,
    bucket_of,
    open_layers,
    total_rows,
)
from erev_api.domain.reports.tie_outs import BalanceRow

NS = UUID("00000000-0000-0000-0000-000000000117")
CONTRACT, ENTITY, VERSION = uuid5(NS, "contract"), uuid5(NS, "entity"), uuid5(NS, "version")
MARCH_END = date(2026, 3, 31)
D = Decimal


def _layer(role: str, amount: str, day: date, currency: str = "USD") -> Layer:
    return Layer(
        contract_id=CONTRACT,
        external_id="C-POS-117",
        customer_name="Pellworth Logistics Inc. (Demo)",
        entity_id=ENTITY,
        entity_code="US01",
        balance_role=role,
        currency=currency,
        amount=D(amount),
        effective_date=day,
    )


def _balance(**values: str) -> BalanceRow:
    return BalanceRow(
        contract_id=CONTRACT,
        external_id="C-POS-117",
        customer_name="Pellworth Logistics Inc. (Demo)",
        entity_id=ENTITY,
        entity_code="US01",
        currency="USD",
        version_id=VERSION,
        values={key: D(value) for key, value in values.items()},
    )


def test_bucket_boundaries() -> None:
    """0 to 30, 31 to 90, 91 to 180, 181 to 365, over 365 days; a negative age is 0 to 30."""
    assert [bucket_of(age) for age in (-1, 0, 30)] == ["bucket_0_30"] * 3
    assert [bucket_of(age) for age in (31, 90)] == ["bucket_31_90"] * 2
    assert [bucket_of(age) for age in (91, 180)] == ["bucket_91_180"] * 2
    assert [bucket_of(age) for age in (181, 365)] == ["bucket_181_365"] * 2
    assert [bucket_of(age) for age in (366, 4000)] == ["bucket_over_365"] * 2
    assert BUCKET_FIELDS == (
        "bucket_0_30",
        "bucket_31_90",
        "bucket_91_180",
        "bucket_181_365",
        "bucket_over_365",
    )


def test_open_layers_consume_first_in_first_out() -> None:
    """POL-126: a 10,000.00 billing on 1 Jan and 2,000.00 on 1 Feb; revenue of 4,000.00 on 31 Jan
    consumes the January layer first; 9,000.00 more consumes the rest of January and 1,000.00 of
    February; a further 5,000.00 leaves a negative layer dated by that debit, so Σ still equals the
    flows."""
    flows = [
        (date(2026, 1, 1), D("10000.00")),
        (date(2026, 1, 31), D("-4000.00")),
        (date(2026, 2, 1), D("2000.00")),
    ]
    assert open_layers(flows) == [
        (date(2026, 1, 1), D("6000.00")),
        (date(2026, 2, 1), D("2000.00")),
    ]
    flows.append((date(2026, 2, 28), D("-7000.00")))
    assert open_layers(flows) == [(date(2026, 2, 1), D("1000.00"))]
    flows.append((date(2026, 3, 31), D("-6000.00")))
    assert open_layers(flows) == [(date(2026, 3, 31), D("-5000.00"))]
    assert sum((amount for _, amount in open_layers(flows)), D(0)) == sum(
        (amount for _, amount in flows), D(0)
    )
    assert open_layers([]) == []


def test_chk_117_unbilled_and_contract_asset_in_bucket_0_30() -> None:
    """CHK-117 over CHK-010 at 31 Mar 2026: unbilled receivable 3,000.00 (P1 revenue of 10 Mar) and
    contract asset 2,000.00 (P2 revenue of 20 Mar) both age under 31 days; row keys
    ``contract:<external id>:<role>``; totals per role; ``TO_AGING_EQ_BALANCES`` passes against the
    presented balances and fails when they differ."""
    layers = [
        _layer("UNBILLED_RECEIVABLE", "3000.00", date(2026, 3, 10)),
        _layer("CONTRACT_ASSET", "2000.00", date(2026, 3, 20)),
    ]
    rows = aged_rows(layers, {ENTITY: MARCH_END})
    assert [row.row_key for row in rows] == [
        "contract:C-POS-117:CONTRACT_ASSET",
        "contract:C-POS-117:UNBILLED_RECEIVABLE",
    ]
    asset, unbilled = rows
    assert (asset.buckets["bucket_0_30"], asset.buckets["bucket_31_90"], asset.total) == (
        D("2000.00"),
        D(0),
        D("2000.00"),
    )
    assert (unbilled.buckets["bucket_0_30"], unbilled.total) == (D("3000.00"), D("3000.00"))
    totals = total_rows(rows)
    assert [row["row_key"] for row in totals] == [
        "TOTAL:CONTRACT_ASSET:USD",
        "TOTAL:UNBILLED_RECEIVABLE:USD",
    ]
    assert totals[1]["bucket_0_30"] == {"amount": "3000.00", "currency": "USD"}
    balances = [_balance(contract_asset="2000.00", unbilled_receivable="3000.00")]
    tie = aging_tie(rows, balances)
    assert (tie["code"], tie["result"]) == (TO_AGING_EQ_BALANCES, "PASS")
    assert tie["expected"] == tie["actual"] == [{"amount": "5000.00", "currency": "USD"}]
    broken = aging_tie(rows, [_balance(contract_asset="2000.00", unbilled_receivable="2999.99")])
    assert broken["result"] == "FAIL" and broken["expected"] == [
        {"amount": "4999.99", "currency": "USD"}
    ]


def test_aged_rows_split_buckets_and_drop_zero_totals() -> None:
    """A liability with layers of 5, 60, 120, 200 and 400 days fills one bucket each; a role whose
    layers net to zero gives no row; rows sort by external id, entity, then asset, unbilled,
    liability."""
    as_of = date(2026, 12, 31)
    layers = [
        _layer("CONTRACT_LIABILITY", "100.00", date(2026, 12, 26)),
        _layer("CONTRACT_LIABILITY", "200.00", date(2026, 11, 1)),
        _layer("CONTRACT_LIABILITY", "300.00", date(2026, 9, 2)),
        _layer("CONTRACT_LIABILITY", "400.00", date(2026, 6, 14)),
        _layer("CONTRACT_LIABILITY", "500.00", date(2025, 11, 26)),
        _layer("CONTRACT_ASSET", "50.00", date(2026, 12, 1)),
        _layer("CONTRACT_ASSET", "-50.00", date(2026, 12, 31)),
    ]
    (row,) = aged_rows(layers, {ENTITY: as_of})
    assert row.balance_role == "CONTRACT_LIABILITY"
    assert [row.buckets[field] for field in BUCKET_FIELDS] == [
        D("100.00"),
        D("200.00"),
        D("300.00"),
        D("400.00"),
        D("500.00"),
    ]
    assert row.total == D("1500.00")
    assert aging.ROLES == ("CONTRACT_ASSET", "UNBILLED_RECEIVABLE", "CONTRACT_LIABILITY")
    assert aging.CODE == "balance_aging" and aging.COLUMNS[-1].key == "total"


# --- Codex review F-RPS-E1-R2 (PRODUCTION-F-RPS-E1-INDEPENDENT-642363e.md) ---


def test_r2_cross_bucket_zero_total_row_is_omitted() -> None:
    """SCREENS_B RPT-36: one row per contract and role with a NON-ZERO balance. A role whose layers
    net to zero across buckets (−50.00 dated 1 Nov in 31 to 90, +50.00 dated 31 Dec in 0 to 30)
    gives no row, as the same-bucket case already does."""
    as_of = date(2026, 12, 31)
    layers = [
        _layer("CONTRACT_ASSET", "-50.00", date(2026, 11, 1)),
        _layer("CONTRACT_ASSET", "50.00", date(2026, 12, 31)),
        _layer("UNBILLED_RECEIVABLE", "10.00", date(2026, 12, 1)),
    ]
    rows = aged_rows(layers, {ENTITY: as_of})
    assert [(row.balance_role, row.total) for row in rows] == [("UNBILLED_RECEIVABLE", D("10.00"))]


def test_r2_fifo_consumption_reaches_the_oldest_positive_layer_past_a_negative_carry() -> None:
    """Flows 1 Nov −50, 15 Dec +100, 31 Dec −50: the last debit consumes the 15 Dec layer to
    +50.00 while the earlier excess debit of −50.00 stays (the documented negative-excess
    convention); a leading negative layer never blocks consumption."""
    flows = [
        (date(2026, 11, 1), D("-50.00")),
        (date(2026, 12, 15), D("100.00")),
        (date(2026, 12, 31), D("-50.00")),
    ]
    assert open_layers(flows) == [
        (date(2026, 11, 1), D("-50.00")),
        (date(2026, 12, 15), D("50.00")),
    ]
    # A debit larger than every positive layer consumes them all and leaves its own excess.
    flows.append((date(2027, 1, 31), D("-80.00")))
    assert open_layers(flows) == [
        (date(2026, 11, 1), D("-50.00")),
        (date(2027, 1, 31), D("-30.00")),
    ]
