"""Current asset classification follows original obligation maturity and FX attribution."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

from erev_api.domain.reports.functional_balances import project
from erev_engine import compute
from erev_engine.trace import reevaluate


def source(*, grouped=False, collision=False, disabled=False):
    key = "FX-CHK-081-CONTRACT-ASSET-REMEASURED-TO-CLOSING-RATE"
    (value,) = _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / "fx" / f"{key}.yaml"))[1].bundles
    booked = value.events[0]
    line = {**booked.payload["lines"][0], "total_price": Decimal("6000")}
    long = {**line, "obligation_key": "LONG", "end_date": date(2028, 12, 31)}
    if grouped:
        second = replace(value.contracts[0], external_id="MEMBER-B")
        contracts = (*value.contracts, second)
        events = (
            replace(booked, payload={**booked.payload, "lines": [line]}),
            value.events[1],
            bundles.event(
                second.external_id,
                1,
                "CONTRACT_BOOKED",
                booked.effective_date,
                {**booked.payload, "external_id": second.external_id, "lines": [long]},
                obligation_keys=["LONG"],
                record_seq=3,
            ),
            bundles.event(
                second.external_id,
                2,
                "CONTRACT_ACTIVATED",
                booked.effective_date,
                value.events[1].payload,
                record_seq=4,
            ),
        )
    else:
        contracts = value.contracts
        events = (
            replace(
                booked,
                obligation_keys=(line["obligation_key"], "LONG"),
                payload={**booked.payload, "lines": [line, long]},
            ),
            value.events[1],
        )
    original = value.entities[0]
    periods = (
        *original.periods,
        *(
            replace(p, states=(("ASC606", "future"),))
            for p in bundles.entity(months=36).periods
            if p.period_key > original.periods[-1].period_key
        ),
    )
    book = value.books[0]
    return replace(
        value,
        evidence_revision=51,
        contracts=contracts,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        group=replace(
            value.group,
            group_key=value.contracts[0].external_id if collision else value.group.group_key,
            member_contract_keys=tuple(c.external_id for c in contracts),
            criterion="25_9_A" if grouped else None,
        ),
        entities=(replace(original, periods=periods),),
        books=(
            replace(
                book,
                policies=tuple(
                    replace(p, value="NONE")
                    if disabled and p.code == "balance.current_noncurrent"
                    else p
                    for p in book.policies
                ),
            ),
        ),
    )


@pytest.mark.parametrize("grouped,collision", [(False, False), (True, False), (True, True)])
def test_member_asset_maturity_uses_original_functional_reclass(grouped, collision):
    value = source(grouped=grouped, collision=collision)
    output = compute(value).books[0]
    previous = compute(replace(value, evidence_revision=50)).books[0]
    assert output.posting_intents == previous.posting_intents
    assert output.schedules == previous.schedules
    assert reevaluate(output.trace) == {n.id: n.value for n in output.trace.nodes}
    for period, total, current in [
        ("FY2026-P01", Decimal("750.08"), Decimal("560.00")),
        ("FY2026-P02", Decimal("1508.21"), Decimal("1140.00")),
    ]:
        rows = [r for r in output.balances if r.period_key == period]
        amounts = []
        for row in rows:
            stored = {
                k: Decimal(v) / 100 if isinstance(v, int) else v for k, v in row.columns.items()
            }
            key = next(
                c.external_id
                for c in value.contracts
                if row.subject_key.startswith(c.external_id + "@")
            )
            projected = project(
                output.trace,
                external_id=key,
                entity_code="US01",
                period_key=period,
                stored=stored,
                version_id=UUID(int=1),
                measures=("contract_asset", "contract_asset_current", "unbilled_receivable"),
            )
            amounts.append(projected)
            assert Decimal(0) <= projected["contract_asset_current"] <= projected["contract_asset"]
            if key == "MEMBER-B":
                assert projected["contract_asset_current"] == 0
        assert sum(a["contract_asset"] for a in amounts) == total
        assert sum(a["contract_asset_current"] for a in amounts) == current
        assert sum(a["unbilled_receivable"] for a in amounts) == 0


def test_disabled_asset_classification_publishes_dated_zero():
    output = compute(source(grouped=True, disabled=True)).books[0]
    nodes = [n for n in output.trace.nodes if n.measure == "contract_asset_current_functional"]
    assert nodes and all(Decimal(n.value) == 0 for n in nodes)
    assert all(r.columns["contract_asset_current_txn"] == 0 for r in output.balances)


def test_unconditional_member_receivable_remains_separate_from_current_assets():
    from erev_engine.bundle import ResolvedPolicyInput

    value = source(grouped=True)
    book = value.books[0]
    overrides = tuple(
        ResolvedPolicyInput(
            "balance.right_to_consideration",
            "CONTRACT",
            c.external_id,
            "UNCONDITIONAL",
            "C",
            f"right-{c.external_id}",
            "K",
        )
        for c in value.contracts
    )
    value = replace(
        value,
        books=(
            replace(
                book,
                policies=tuple(
                    sorted(
                        (*book.policies, *overrides), key=lambda p: (p.code, p.scope, p.subject_key)
                    )
                ),
            ),
        ),
    )
    result = compute(value).books[0]
    rows = [r for r in result.balances if r.period_key == "FY2026-P02"]
    # The original short obligation's reviewed O-level conditional right takes
    # precedence; the new long member has the explicit C-level unconditional right.
    assert sum(r.columns["unbilled_receivable_functional"] for r in rows) == 36821
    assert sum(r.columns["contract_asset_current_txn"] for r in rows) == 100000
    current = [
        n
        for n in result.trace.nodes
        if n.measure == "contract_asset_current_functional" and n.id.endswith(":FY2026-P02")
    ]
    assert sum(Decimal(n.value) for n in current) == Decimal("1140.00")
    assert (
        next(r for r in rows if r.subject_key.startswith("MEMBER-B@")).columns[
            "contract_asset_current_txn"
        ]
        == 0
    )
    assert (
        result.posting_intents
        == compute(replace(value, evidence_revision=50)).books[0].posting_intents
    )
