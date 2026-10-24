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


def grouped_source(policy="FIFO", *, second_bill="6000.00", disabled=False, collision=False):
    value = source(policy)
    second = replace(value.contracts[0], external_id="MEMBER-B")
    booked, activated = value.events[:2]
    events = (
        *value.events,
        bundles.event(
            second.external_id,
            1,
            "CONTRACT_BOOKED",
            booked.effective_date,
            {**booked.payload, "external_id": second.external_id},
            record_seq=5,
        ),
        bundles.event(
            second.external_id,
            2,
            "CONTRACT_ACTIVATED",
            activated.effective_date,
            activated.payload,
            record_seq=6,
        ),
        bundles.event(
            second.external_id,
            3,
            "BILLING_RECORDED",
            value.events[-1].effective_date,
            {
                **value.events[-1].payload,
                "amount": Decimal(second_bill),
                "invoice_number": "SECOND",
                "line_external_id": "SECOND-1",
            },
            record_seq=7,
        ),
    )
    return replace(
        value,
        evidence_revision=54,
        contracts=(*value.contracts, second),
        group=replace(
            value.group,
            member_contract_keys=(value.contracts[0].external_id, second.external_id),
            group_key=value.contracts[0].external_id if collision else value.group.group_key,
            criterion="25_9_A",
        ),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        books=tuple(
            replace(
                b,
                policies=tuple(
                    replace(p, value="NONE")
                    if disabled and p.code == "balance.current_noncurrent"
                    else p
                    for p in b.policies
                ),
            )
            for b in value.books
        ),
    )


@pytest.mark.parametrize("policy", ["FIFO", "PRO_RATA"])
def test_combined_current_liability_allocates_by_original_member_carrying(policy):
    value = grouped_source(policy)
    output = compute(value).books[0]
    prior = compute(replace(value, evidence_revision=53)).books[0]
    assert output.posting_intents == prior.posting_intents
    assert output.schedules == prior.schedules
    assert reevaluate(output.trace) == {n.id: n.value for n in output.trace.nodes}
    rows = [r for r in output.balances if r.period_key == "FY2026-P03"]
    nodes = {n.id: n for n in output.trace.nodes}
    projected = []
    for row in rows:
        assert (
            0
            <= row.columns["contract_liability_current_txn"]
            <= row.columns["contract_liability_txn"]
        )
        stored = {k: Decimal(v) / 100 if isinstance(v, int) else v for k, v in row.columns.items()}
        member = next(
            c.external_id
            for c in value.contracts
            if row.subject_key.startswith(c.external_id + "@")
        )
        projected.append(
            project(
                output.trace,
                external_id=member,
                entity_code="US01",
                period_key=row.period_key,
                stored=stored,
                version_id=UUID(int=1),
                measures=("contract_liability", "contract_liability_current"),
            )
        )
        node = nodes[f"contract_liability_current_functional:{row.subject_key}:{row.period_key}"]
        assert node.params["basis"] == "MEMBER_LIABILITY_CARRYING"
    total = sum(p["contract_liability"] for p in projected)
    current = sum(p["contract_liability_current"] for p in projected)
    assert sum(r.columns["contract_liability_current_txn"] for r in rows) == 799635
    for p in projected:
        assert Decimal(0) <= p["contract_liability_current"] <= p["contract_liability"]
        assert abs(
            p["contract_liability_current"] - current * p["contract_liability"] / total
        ) < Decimal("0.01")
    assert (
        sum(p["contract_liability"] - p["contract_liability_current"] for p in projected)
        == total - current
    )
    group_node = next(
        n
        for n in output.trace.nodes
        if n.measure == "contract_liability_current_functional"
        and "current-liability" in n.id
        and n.id.endswith(":FY2026-P03")
    )
    assert current == Decimal(group_node.value)


@pytest.mark.parametrize("disabled,second_bill", [(True, "6000.00"), (False, "0.00")])
def test_combined_zero_current_and_zero_carrying_members(disabled, second_bill):
    output = compute(
        grouped_source(disabled=disabled, second_bill=second_bill, collision=True)
    ).books[0]
    assert reevaluate(output.trace) == {n.id: n.value for n in output.trace.nodes}
    for row in output.balances:
        if disabled or row.subject_key.startswith("MEMBER-B@"):
            assert row.columns["contract_liability_current_txn"] == 0
            node = next(
                n
                for n in output.trace.nodes
                if n.id
                == f"contract_liability_current_functional:{row.subject_key}:{row.period_key}"
            )
            assert Decimal(node.value) == 0


def test_combined_monetary_current_allocates_existing_closing_carrying():
    value = grouped_source()
    value = replace(
        value,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(p, value="DISABLED_REMEASURE_AS_MONETARY")
                    if p.code == "fx.cl_historical_layering"
                    else p
                    for p in book.policies
                ),
            )
            for book in value.books
        ),
        fx_rates=tuple(
            replace(r, rate=Decimal("1.20")) if r.rate_type == "closing" else r
            for r in value.fx_rates
        ),
    )
    output = compute(value).books[0]
    rows = [r for r in output.balances if r.period_key == "FY2026-P03"]
    ids = {f"contract_liability_current_functional:{r.subject_key}:{r.period_key}" for r in rows}
    assert sum(Decimal(n.value) for n in output.trace.nodes if n.id in ids) == Decimal("9595.62")
    assert reevaluate(output.trace) == {n.id: n.value for n in output.trace.nodes}
    assert (
        output.posting_intents
        == compute(replace(value, evidence_revision=53)).books[0].posting_intents
    )
