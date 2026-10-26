"""Native foreign return assets and loss provisions retain their monetary source basis."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from support import intent_totals

from erev_api.domain.reports.builders.loss_provision_register import project_functional
from erev_api.domain.reports.functional_balances import project
from erev_api.explain.narratives import render
from erev_api.problems import Problem
from erev_engine import compute
from erev_engine.bundle import FxRateInput
from erev_engine.errors import EngineError
from erev_engine.trace import reevaluate
from tests.engine.s12_fx_entities.test_cost_asset_currency import source


def rates(value, *extra):
    return replace(
        value,
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


def spot(key, when, rate):
    return FxRateInput(key, "1", "spot", "USD", "EUR", when, None, Decimal(rate))


def verify(value, result, measure, period, expected, role):
    nodes = {n.id: n for n in result.trace.nodes}
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    assert all(
        render(n, nodes)
        for n in result.trace.nodes
        if n.formula_id in {"fx.return_asset.v1", "fx.loss_forecast.v1"}
    )
    row = next(r for r in result.balances if r.period_key == period)
    projected = project(
        result.trace,
        external_id=value.contracts[0].external_id,
        entity_code=value.entities[0].code,
        period_key=period,
        version_id=UUID(int=1),
        stored={k: Decimal(v) / 100 if isinstance(v, int) else v for k, v in row.columns.items()},
        measures=(measure,),
    )
    assert projected[measure] == Decimal(expected)
    first = compute(value)
    released = intent_totals.close_pass(value, [first], "CLOSE_RELEASE")
    signed = sum(
        (1 if line.side == "D" else -1) * line.amount_functional
        for book in (first.books[0], released.books[0])
        for entry in book.posting_intents
        if entry.posting_period_key <= period
        for line in entry.lines
        if line.account_role == role
    )
    assert Decimal(signed) / 100 == (
        Decimal(expected) if role == "RETURN_ASSET" else -Decimal(expected)
    )


@pytest.mark.parametrize(
    "policy,first,second,released", [("FIFO", "162", "54", "108"), ("PRO_RATA", "180", "60", "120")]
)
def test_original_delivery_cost_layers_release_by_existing_policy(policy, first, second, released):
    value = replace(source("ret/RET-CHK-029-S3-EX22.yaml"), evidence_revision=69)
    original = next(e for e in value.events if e.event_type == "DELIVERY_RECORDED")
    key = f"{original.contract_key}/EV-999999"
    later = replace(
        original,
        event_key=key,
        stream_version=999999,
        record_seq=max(e.record_seq for e in value.events) + 1,
        effective_date=date(2026, 1, 20),
        payload={**original.payload, "quantity": Decimal(50)},
    )
    value = replace(
        value,
        events=tuple(
            sorted(
                (
                    *(
                        replace(e, payload={**e.payload, "quantity": Decimal(50)})
                        if e == original
                        else e
                        for e in value.events
                    ),
                    later,
                ),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
        books=tuple(
            replace(
                b,
                policies=tuple(
                    replace(p, value=policy) if p.code == "fx.cl_layer_consumption" else p
                    for p in b.policies
                ),
            )
            for b in value.books
        ),
    )
    value = rates(value, spot("later-delivery", date(2026, 1, 20), "1.1"))
    result = compute(value).books[0]
    verify(value, result, "return_asset", "FY2026-P01", first, "RETURN_ASSET")
    verify(value, result, "return_asset", "FY2026-P02", second, "RETURN_ASSET")
    node = next(
        n
        for n in result.trace.nodes
        if n.measure == "return_asset_derecognised_cum_functional" and n.id.endswith(":FY2026-P02")
    )
    assert Decimal(node.value) == Decimal(released)
    verify(value, result, "return_asset", "FY2026-P03", "0", "RETURN_ASSET")
    assert compute(value) == compute(value)


def test_recovery_reassessment_does_not_replace_existing_delivery_cost_or_rate():
    value = replace(source("ret/RET-CHK-029-S3-EX22.yaml"), evidence_revision=69)
    initial = next(v for v in value.estimate_versions if v.estimate_kind == "RETURN_RATE")
    revised = replace(
        initial,
        version_key=initial.estimate_key + "@v2",
        version_no=2,
        effective_date=date(2026, 2, 1),
        parameters={
            **initial.parameters,
            "carrying_cost_per_unit": "90.00",
            "recovery_cost_per_unit": "10.00",
        },
        supersedes_version_key=initial.version_key,
    )
    event = next(e for e in value.events if e.event_type == "ESTIMATE_CHANGED")
    changed = replace(
        event,
        event_key=f"{event.contract_key}/EV-999999",
        stream_version=999999,
        record_seq=max(e.record_seq for e in value.events) + 1,
        effective_date=date(2026, 2, 1),
        payload={"estimate_version_id": revised.version_key},
        estimate_version_key=revised.version_key,
    )
    value = replace(
        value,
        estimate_versions=(*value.estimate_versions, revised),
        events=tuple(
            sorted(
                (*value.events, changed),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    value = rates(value, spot("recovery-assessment", date(2026, 2, 1), "1.2"))
    result = compute(value).books[0]
    verify(value, result, "return_asset", "FY2026-P02", "42", "RETURN_ASSET")
    node = next(
        n
        for n in result.trace.nodes
        if n.measure == "return_asset_derecognised_cum_functional" and n.id.endswith(":FY2026-P02")
    )
    assert Decimal(node.value) == 84


@pytest.mark.parametrize(
    "average,assessment,expected", [("1.2", ".9", "0"), (".9", "1.3", "39000")]
)
def test_loss_tests_use_historical_actuals_and_dated_remaining_forecasts(
    average, assessment, expected
):
    value = replace(source("loss/LOSS-S7-LOSS-OWN.yaml"), evidence_revision=69)
    value = replace(
        value,
        fx_rates=tuple(
            replace(r, rate=Decimal(average)) if r.rate_type == "average" else r
            for r in value.fx_rates
        ),
    )
    value = rates(value, spot("loss-assessment", date(2027, 12, 31), assessment))
    result = compute(value).books[0]
    verify(value, result, "loss_provision", "FY2027-P12", expected, "LOSS_PROVISION")
    held = next(
        r for r in result.loss_provision_versions if r.columns["period_key"] == "FY2027-P12"
    )
    from erev_api.domain.reports.builders.loss_provision_register import MONEY

    row = {
        **held.columns,
        **{key: Decimal(held.columns[key]) / 100 for key in MONEY},
        "trace_nodes": held.trace_nodes,
    }
    projected = project_functional(row, result.trace, "EUR")
    assert projected["provision_balance"] == Decimal(expected)
    assert Decimal(row["provision_balance"]) == 30000
    if expected == "0":
        assert projected["provision_balance"] != Decimal(row["provision_balance"]) * Decimal(
            assessment
        )
    else:
        assert projected["costs_to_date"] == 821000
        assert projected["revenue_to_date"] == 630000
        assert projected["expected_total_costs"] == 1250000
        assert projected["expected_consideration"] == 1020000
    with pytest.raises(Problem):
        project_functional({**row, "provision_balance": Decimal(1)}, result.trace, "EUR")
    with pytest.raises(Problem):
        project_functional(row, result.trace, "GBP")
    assert compute(value) == compute(value)


def test_same_currency_and_legacy_return_evidence_keep_existing_behavior():
    value = source("ret/RET-CHK-029-S3-EX22.yaml")
    with pytest.raises(EngineError, match="no functional amount"):
        compute(replace(value, evidence_revision=68))
    value = replace(
        value, entities=tuple(replace(e, functional_currency="USD") for e in value.entities)
    )
    assert (
        compute(replace(value, evidence_revision=69)).books
        == compute(replace(value, evidence_revision=68)).books
    )
