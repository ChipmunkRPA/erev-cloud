"""Functional impairment is independent of transaction impairment and reconciles to journals."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from erev_api.domain.reports.functional_balances import project
from erev_engine import compute
from erev_engine.bundle import FxRateInput
from erev_engine.trace import reevaluate
from tests.engine.s12_fx_entities.test_cost_asset_currency import source


def foreign_cost(path, impairment_date, *, rate=".8", recovery_date=None):
    value = source(path)
    extra = [
        FxRateInput(
            "independent-impairment",
            "1",
            "spot",
            "USD",
            "EUR",
            impairment_date,
            None,
            Decimal(rate),
        )
    ]
    if recovery_date:
        extra.append(
            FxRateInput(
                "independent-recovery",
                "1",
                "spot",
                "USD",
                "EUR",
                recovery_date,
                None,
                Decimal("1.1"),
            )
        )
    return replace(
        value,
        evidence_revision=67,
        fx_rates=tuple(
            sorted(
                (*value.fx_rates, *extra),
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.version_key,
                ),
            )
        ),
    )


def verify_carrying(value, result, period, expected):
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    from erev_api.explain.narratives import render

    nodes = {n.id: n for n in result.trace.nodes}
    assert all(render(n, nodes) for n in result.trace.nodes if n.formula_id.startswith("fx.cost_"))
    row = next(row for row in result.balances if row.period_key == period)
    projected = project(
        result.trace,
        external_id=value.contracts[0].external_id,
        entity_code=value.entities[0].code,
        period_key=period,
        version_id=UUID(int=1),
        stored={k: Decimal(v) / 100 if isinstance(v, int) else v for k, v in row.columns.items()},
        measures=("cost_asset_carrying",),
    )
    assert projected["cost_asset_carrying"] == Decimal(expected)
    amount = sum(
        (1 if line.side == "D" else -1) * line.amount_functional
        for entry in result.posting_intents
        if entry.posting_period_key <= period
        for line in entry.lines
        if line.account_role == "COST_TO_OBTAIN_ASSET"
    )
    assert Decimal(amount) / 100 == projected["cost_asset_carrying"]


@pytest.mark.parametrize("functional_only", [False, True])
def test_impairment_uses_remaining_functional_consideration_and_costs(functional_only):
    value = foreign_cost(
        "cost/COST-S8-CONTRACT-COSTS-IMPAIRMENT.yaml",
        date(2026, 12, 31),
        rate=".5" if functional_only else ".8",
    )
    if functional_only:
        value = replace(
            value,
            estimate_versions=tuple(
                replace(v, expected_total_amount=Decimal("360000"))
                if v.estimate_kind == "EAC" and v.effective_date == date(2026, 12, 31)
                else v
                for v in value.estimate_versions
            ),
        )
    result = compute(value).books[0]
    impairment = next(
        n
        for n in result.trace.nodes
        if n.measure == "cost_impaired_cum_functional" and n.id.endswith(":FY2026-P12")
    )
    transaction = next(
        n
        for n in result.trace.nodes
        if n.measure == "cost_impaired_cum" and n.id.endswith(":FY2026-P12")
    )
    assert Decimal(impairment.value) == Decimal("9500" if functional_only else "15000")
    assert Decimal(transaction.value) == Decimal("0" if functional_only else "15000")
    assert Decimal(impairment.value) != Decimal(transaction.value) * Decimal(
        ".5" if functional_only else ".8"
    )
    verify_carrying(value, result, "FY2026-P12", "17500" if functional_only else "12000")
    assert compute(value) == compute(value)


def test_ifrs_reversal_is_capped_by_independent_unimpaired_functional_carrying():
    value = foreign_cost(
        "je/JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL.yaml",
        date(2026, 1, 31),
        recovery_date=date(2026, 2, 1),
    )
    results = {result.book_code: result for result in compute(value).books}
    for code, result in results.items():
        reversal = next(
            n
            for n in result.trace.nodes
            if n.measure == "cost_impairment_reversed_cum_functional"
            and n.id.endswith(":FY2026-P02")
        )
        assert Decimal(reversal.value) == (Decimal("10000") if code == "IFRS15" else 0)
        verify_carrying(value, result, "FY2026-P01", "12000")
        verify_carrying(value, result, "FY2026-P02", "18000" if code == "IFRS15" else "8000")


def test_clawback_after_independent_impairment_keeps_original_capitalization_rate():
    value = foreign_cost("cost/COST-S8-CONTRACT-COSTS-IMPAIRMENT.yaml", date(2026, 12, 31))
    value = replace(
        value,
        events=tuple(
            replace(e, payload={**e.payload, "payee": "AGENT"})
            if e.payload.get("is_incremental")
            else e
            for e in value.events
        ),
    )
    original = next(e for e in value.events if e.payload.get("is_incremental") is True)
    key = f"{original.contract_key}/EV-999999"
    event = replace(
        original,
        event_key=key,
        stream_version=999999,
        record_seq=max(e.record_seq for e in value.events) + 1,
        effective_date=date(2027, 1, 1),
        payload={**original.payload, "cost_adjustment": "CLAWBACK", "amount": Decimal("1000")},
    )
    value = replace(
        value,
        events=tuple(
            sorted(
                (*value.events, event), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
            )
        ),
    )
    result = compute(value).books[0]
    clawback = next(
        n
        for n in result.trace.nodes
        if n.measure == "cost_clawback_cum_functional" and n.id.endswith(":FY2027-P01")
    )
    assert Decimal(clawback.value) == 900
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
