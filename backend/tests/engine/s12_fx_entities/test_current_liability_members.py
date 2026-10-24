"""Ordinary dated current liabilities keep historical layer carrying and posted revenue."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

import pytest
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

from erev_api.domain.reports.functional_balances import project
from erev_engine import compute
from erev_engine.trace import reevaluate


def source(policy="FIFO"):
    key = "FX-POL-161-FIFO-TWO-LAYERS-IN-ONE-PERIOD"
    (value,) = _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / "fx" / f"{key}.yaml"))[-1].bundles
    original = value.entities[0]
    periods = tuple(
        p
        if p.period_key <= original.periods[-1].period_key
        else replace(p, states=(("ASC606", "future"),))
        for p in bundles.entity(months=36).periods
    )
    events = tuple(
        replace(
            e,
            payload={
                **e.payload,
                "lines": [{**line, "end_date": "2028-12-31"} for line in e.payload["lines"]],
            },
        )
        if e.event_type == "CONTRACT_BOOKED"
        else e
        for e in value.events
    )
    book = value.books[0]
    return replace(
        value,
        evidence_revision=50,
        entities=(replace(original, periods=periods),),
        events=events,
        books=(
            replace(
                book,
                policies=tuple(
                    replace(p, value=policy) if p.code == "fx.cl_layer_consumption" else p
                    for p in book.policies
                ),
            ),
        ),
    )


@pytest.mark.parametrize("policy", ["FIFO", "PRO_RATA"])
def test_current_liability_uses_original_layers_and_projects_into_reporting(policy):
    value = source(policy)
    result = compute(value).books[0]
    old = compute(replace(value, evidence_revision=49)).books[0]
    assert result.posting_intents == old.posting_intents
    assert result.schedules == old.schedules
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    rows = [r for r in result.balances if r.period_key == "FY2026-P03"]
    assert len(rows) == 1
    row = rows[0]
    name = f"contract_liability_current_functional:{row.subject_key}:{row.period_key}"
    node = next(n for n in result.trace.nodes if n.id == name)
    assert row.columns["contract_liability_current_txn"] == 400_000
    assert Decimal(node.value) > 0
    assert Decimal(node.value) < Decimal(row.columns["contract_liability_functional"]) / 100
    if policy == "FIFO":
        assert Decimal(node.value) == Decimal("4350.00")
    stored = {k: Decimal(v) / 100 if isinstance(v, int) else v for k, v in row.columns.items()}
    projected = project(
        result.trace,
        external_id=value.contracts[0].external_id,
        entity_code="US01",
        period_key=row.period_key,
        stored=stored,
        version_id=UUID(int=1),
        measures=("contract_liability", "contract_liability_current"),
    )
    assert projected["contract_liability_current"] == Decimal(node.value)
    assert (
        projected["contract_liability"]
        == Decimal(row.columns["contract_liability_functional"]) / 100
    )
    dependencies = {n.id: n for n in result.trace.nodes}
    assert any("layer" in key for key in node.inputs if isinstance(key, str))
    for key in node.inputs:
        if isinstance(key, str):
            assert key in dependencies
    assert not any(n.measure == "contract_liability_current_functional" for n in old.trace.nodes)
    assert (
        Fraction(row.columns["contract_liability_current_txn"])
        <= row.columns["contract_liability_txn"]
    )


def test_monetary_current_liability_uses_existing_remeasured_carrying():
    value = source()
    book = value.books[0]
    value = replace(
        value,
        books=(
            replace(
                book,
                policies=tuple(
                    replace(p, value="DISABLED_REMEASURE_AS_MONETARY")
                    if p.code == "fx.cl_historical_layering"
                    else p
                    for p in book.policies
                ),
            ),
        ),
        fx_rates=tuple(
            replace(r, rate=Decimal("1.20")) if r.rate_type == "closing" else r
            for r in value.fx_rates
        ),
    )
    output = compute(value).books[0]
    current = next(
        n
        for n in output.trace.nodes
        if n.measure == "contract_liability_current_functional" and n.id.endswith(":FY2026-P03")
    )
    assert Decimal(current.value) == Decimal("4800.00")
    assert current.params["monetary"] == "true"
    assert reevaluate(output.trace) == {n.id: n.value for n in output.trace.nodes}
    prior = compute(replace(value, evidence_revision=49)).books[0]
    assert output.posting_intents == prior.posting_intents
