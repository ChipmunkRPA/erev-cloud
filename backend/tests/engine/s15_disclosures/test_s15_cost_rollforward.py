"""Stage 15 contract-cost rollforward (ENGINE_SPEC_B §15.2.6 S15-R-17; S15-INV-04; POLICIES
POL-196, JET-09 CHK-131, §5.3 CHK-112, §11.7 EX-11-A; BUILD_SPEC EDS-5; lane F-RPS + ENG-E1 prep).

The pure module is driven with stage 11 ``CostAssetSpec`` and ``CostAssetMeasures`` rows built
here from the CHK figures (never from engine output); its wiring into ``s15_disclosures.run`` waits
for ENG-C4's EDS-4 (the Stage 15 barrier). Amounts are USD minor units.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from erev_engine.stages.s11_costs_loss.capitalise import CostAssetSpec
from erev_engine.stages.s11_costs_loss.impair import CostAssetMeasures
from erev_engine.stages.s15_disclosures import cost_rollforward as module
from erev_engine.stages.s15_disclosures.cost_rollforward import (
    COST_KINDS,
    LINES,
    MOVEMENTS,
    cost_rollforward,
    rows_of,
)

US = "US01"
Y1, Y2 = "FY2026-P12", "FY2027-P12"


def _spec(asset_key: str, kind: str = "OBTAIN", entity: str = US) -> CostAssetSpec:
    return CostAssetSpec(
        asset_key=asset_key,
        contract_key="C-COST",
        entity=entity,
        cost_kind=kind,
        payee=None,
        plan_code=None,
        capitalization_date=date(2026, 1, 1),
        amount_capitalized=4_000_000,
        related_obligation_keys=("C-COST/L1",),
        amortization_pattern="STRAIGHT_LINE",
        amortization_start_date=date(2026, 1, 1),
        amortization_months=48,
        amortization_end_date=date(2029, 12, 31),
        term_months=48,
        period_option="CONTRACT_TERM",
        time_convention="MONTHLY",
        renewal_version_key=None,
        has_clawback=False,
    )


def _measures(
    asset_key: str,
    period_key: str,
    *,
    capitalized: int,
    amortized: int = 0,
    impaired: int = 0,
    reversed_: int = 0,
    clawback: int = 0,
    accelerated: int = 0,
) -> CostAssetMeasures:
    carrying = capitalized - amortized - impaired + reversed_ - clawback - accelerated
    return CostAssetMeasures(
        asset_key=asset_key,
        period_key=period_key,
        as_of=date(2026, 12, 31) if period_key == Y1 else date(2027, 12, 31),
        capitalized_cum=capitalized,
        amortized_cum=amortized,
        impaired_cum=impaired,
        impairment_reversed_cum=reversed_,
        clawback_cum=clawback,
        accelerated_cum=accelerated,
        carrying_amount=carrying,
        remaining_months=0,
        renewal_version_key=None,
        segments=(),
        trace_nodes={},
    )


def _lines(row: module.CostRollforwardRow) -> dict[str, int]:
    return {
        line: row.lines[line]
        for line in LINES
        if row.lines[line] != 0 or line in ("OPENING", "CLOSING")
    }


def test_chk_131_cost_rollforward() -> None:
    """CHK-131 per entity, book and kind OBTAIN. Year 1: opening 0.00, additions 40,000.00,
    amortisation (10,000.00), impairment (15,000.00), closing 15,000.00. Year 2 ASC606: amortisation
    (5,000.00), closing 10,000.00. Year 2 IFRS15: amortisation (5,000.00), reversal 10,000.00,
    closing 20,000.00 (POL-144 ``REQUIRED_CAPPED``)."""
    specs = [_spec("C-COST/COST/EV-000003")]
    asc606: Mapping[tuple[str, str], CostAssetMeasures] = {
        (specs[0].asset_key, Y1): _measures(
            specs[0].asset_key, Y1, capitalized=4_000_000, amortized=1_000_000, impaired=1_500_000
        ),
        (specs[0].asset_key, Y2): _measures(
            specs[0].asset_key, Y2, capitalized=4_000_000, amortized=1_500_000, impaired=1_500_000
        ),
    }
    result = cost_rollforward("ASC606", specs, asc606, (Y1, Y2))
    year_one = result.row(US, "OBTAIN", Y1)
    assert _lines(year_one) == {
        "OPENING": 0,
        "ADDITIONS": 4_000_000,
        "AMORTIZATION": -1_000_000,
        "IMPAIRMENT": -1_500_000,
        "CLOSING": 1_500_000,
    }
    assert year_one.ties and year_one.asset_keys == (specs[0].asset_key,)
    year_two = result.row(US, "OBTAIN", Y2)
    assert _lines(year_two) == {
        "OPENING": 1_500_000,
        "AMORTIZATION": -500_000,
        "CLOSING": 1_000_000,
    }
    ifrs15 = dict(asc606)
    ifrs15[(specs[0].asset_key, Y2)] = _measures(
        specs[0].asset_key,
        Y2,
        capitalized=4_000_000,
        amortized=1_500_000,
        impaired=1_500_000,
        reversed_=1_000_000,
    )
    reversed_row = cost_rollforward("IFRS15", specs, ifrs15, (Y1, Y2)).row(US, "OBTAIN", Y2)
    assert _lines(reversed_row) == {
        "OPENING": 1_500_000,
        "AMORTIZATION": -500_000,
        "IMPAIRMENT_REVERSAL": 1_000_000,
        "CLOSING": 2_000_000,
    }
    assert reversed_row.book_code == "IFRS15" and reversed_row.ties
    # The FULFILL rows of the same entity exist and are empty (no FULFILL asset).
    fulfill = result.row(US, "FULFILL", Y1)
    assert (fulfill.lines["OPENING"], fulfill.lines["CLOSING"], fulfill.asset_keys) == (0, 0, ())


def test_k02_september_2026() -> None:
    """EX-11-A: the K-02 commission asset gives opening 8,005.48, amortisation (493.15) and closing
    7,512.33 in September 2026 (the August closing opens September)."""
    august, september = "FY2026-P08", "FY2026-P09"
    spec = _spec("K-02/COST/EV-000002")
    measures = {
        (spec.asset_key, august): _measures(
            spec.asset_key, august, capitalized=864_000, amortized=63_452
        ),
        (spec.asset_key, september): _measures(
            spec.asset_key, september, capitalized=864_000, amortized=112_767
        ),
    }
    assert measures[(spec.asset_key, august)].carrying_amount == 800_548
    row = cost_rollforward("ASC606", [spec], measures, (august, september)).row(
        US, "OBTAIN", september
    )
    assert _lines(row) == {"OPENING": 800_548, "AMORTIZATION": -49_315, "CLOSING": 751_233}
    assert row.ties
    # The same September row from the August lock snapshot's asset rows (S15-R-17 "previous
    # snapshot"): September alone in scope, August measures as ``prior``.
    from_snapshot = cost_rollforward(
        "ASC606",
        [spec],
        {(spec.asset_key, september): measures[(spec.asset_key, september)]},
        (september,),
        prior={spec.asset_key: measures[(spec.asset_key, august)]},
    ).row(US, "OBTAIN", september)
    assert _lines(from_snapshot) == _lines(row)
    # Without the prior rows the whole cumulative history lands in September (opening 0).
    bare = cost_rollforward(
        "ASC606",
        [spec],
        {(spec.asset_key, september): measures[(spec.asset_key, september)]},
        (september,),
    ).row(US, "OBTAIN", september)
    assert _lines(bare) == {
        "OPENING": 0,
        "ADDITIONS": 864_000,
        "AMORTIZATION": -112_767,
        "CLOSING": 751_233,
    }


def test_chk_112_acceleration_line() -> None:
    """CHK-112: the terminated subscription's asset shows acceleration (18,000.00) and closing 0.00
    (JET-09e, S11-R-13); the acceleration is its own line, not amortisation."""
    spec = _spec("C-112/COST/EV-000004")
    measures = {
        (spec.asset_key, Y1): _measures(
            spec.asset_key, Y1, capitalized=2_400_000, amortized=600_000
        ),
        (spec.asset_key, Y2): _measures(
            spec.asset_key, Y2, capitalized=2_400_000, amortized=600_000, accelerated=1_800_000
        ),
    }
    row = cost_rollforward("ASC606", [spec], measures, (Y1, Y2)).row(US, "OBTAIN", Y2)
    assert _lines(row) == {"OPENING": 1_800_000, "ACCELERATION": -1_800_000, "CLOSING": 0}
    assert row.ties


def test_s15_inv_04_closing_equals_carrying() -> None:
    """S15-INV-04: the closing equals Σ ``carrying_amount`` of the cost-asset versions at the
    period end over every asset of the (entity, kind); a carrying amount the movements do not
    explain is ``OTHER``, shown and never absorbed."""
    obtain_a, obtain_b, fulfill = (
        _spec("A/COST/EV-1"),
        _spec("B/COST/EV-1"),
        _spec("F/COST/EV-1", kind="FULFILL"),
    )
    uk = _spec("UK/COST/EV-1", entity="UK01")
    measures = {
        (obtain_a.asset_key, Y1): _measures(
            obtain_a.asset_key, Y1, capitalized=100_000, amortized=25_000
        ),
        (obtain_b.asset_key, Y1): _measures(
            obtain_b.asset_key, Y1, capitalized=50_000, clawback=10_000
        ),
        (fulfill.asset_key, Y1): _measures(fulfill.asset_key, Y1, capitalized=30_000),
        (uk.asset_key, Y1): _measures(uk.asset_key, Y1, capitalized=70_000),
    }
    result = cost_rollforward("ASC606", [obtain_a, obtain_b, fulfill, uk], measures, (Y1,))
    obtain = result.row(US, "OBTAIN", Y1)
    assert (
        obtain.lines["CLOSING"]
        == 75_000 + 40_000
        == sum(measures[(key, Y1)].carrying_amount for key in obtain.asset_keys)
    )
    assert _lines(obtain) == {
        "OPENING": 0,
        "ADDITIONS": 150_000,
        "CLAWBACKS": -10_000,
        "AMORTIZATION": -25_000,
        "CLOSING": 115_000,
    }
    assert result.row(US, "FULFILL", Y1).lines["CLOSING"] == 30_000
    assert result.row("UK01", "OBTAIN", Y1).lines["CLOSING"] == 70_000
    assert [(row.entity, row.cost_kind) for row in rows_of(result, Y1)] == [
        (entity, kind) for entity in ("UK01", US) for kind in COST_KINDS
    ]
    # A carrying amount the cumulative movements do not explain surfaces as OTHER (S15-R-07 style).
    row = cost_rollforward(
        "ASC606", [fulfill], _with_carrying(measures, fulfill.asset_key, 29_000), (Y1,)
    ).row(US, "FULFILL", Y1)
    assert (row.lines["OTHER"], row.lines["CLOSING"], row.ties) == (-1_000, 29_000, False)
    assert set(MOVEMENTS) | {"OPENING", "OTHER", "CLOSING"} == set(LINES)


def _with_carrying(
    measures: Mapping[tuple[str, str], CostAssetMeasures], asset_key: str, carrying: int
) -> dict[tuple[str, str], CostAssetMeasures]:
    out = dict(measures)
    for (key, period), item in measures.items():
        if key == asset_key:
            out[(key, period)] = CostAssetMeasures(
                asset_key=item.asset_key,
                period_key=item.period_key,
                as_of=item.as_of,
                capitalized_cum=item.capitalized_cum,
                amortized_cum=item.amortized_cum,
                impaired_cum=item.impaired_cum,
                impairment_reversed_cum=item.impairment_reversed_cum,
                clawback_cum=item.clawback_cum,
                accelerated_cum=item.accelerated_cum,
                carrying_amount=carrying,
                remaining_months=item.remaining_months,
                renewal_version_key=item.renewal_version_key,
                segments=item.segments,
                trace_nodes=item.trace_nodes,
            )
    return out
