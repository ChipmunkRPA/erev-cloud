"""The report adapter reads original closed-cutover amounts, never ERP guesses."""

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest
from support import bundles
from support import onboarding_worlds as w

from erev_api.domain.reports import acquisition_native, tie_outs
from erev_api.problems import Problem
from erev_engine import compute
from erev_engine.bundle import ResolvedPolicyInput
from erev_engine.canonical import canonical_bytes

PERIOD = tie_outs.PeriodRef(
    UUID(int=1),
    "FY2025-P12",
    "December",
    2025,
    12,
    4,
    w.CUTOVER.replace(day=1),
    w.CUTOVER,
)


def original(billed, unconditional=False):
    invoice = bundles.event(
        w.CONTRACT,
        4,
        "BILLING_RECORDED",
        w.CUTOVER.replace(month=6, day=1),
        {
            "invoice_number": "CUTOVER",
            "line_external_id": "CUTOVER-1",
            "obligation_key": w.OBLIGATION,
            "amount": Decimal(billed),
            "issue_date": w.CUTOVER.replace(month=6, day=1),
        },
        obligation_keys=[w.OBLIGATION],
    )
    value = replace(
        w.chk_121(
            as_of=w.CUTOVER,
            extra=[invoice],
            books=("ASC606",),
            policies={"onboarding.method": "RECOMPUTE_FROM_INCEPTION", "billing.posting": "ENGINE"},
        ),
        evidence_revision=41,
    )
    if unconditional:
        book = value.books[0]
        override = ResolvedPolicyInput(
            "balance.right_to_consideration",
            "CONTRACT",
            w.CONTRACT,
            "UNCONDITIONAL",
            "C",
            "approved-right-override",
            "K",
        )
        value = replace(
            value,
            books=(
                replace(
                    book,
                    policies=tuple(
                        sorted(
                            (*book.policies, override),
                            key=lambda p: (p.code, p.scope, p.subject_key),
                        )
                    ),
                ),
            ),
        )
    return value, json.loads(canonical_bytes(compute(value)))


def read(value, output, functional=False):
    return acquisition_native.single_member_cutover(
        value,
        output,
        member=w.CONTRACT,
        book="ASC606",
        entity=w.ENTITY,
        period=PERIOD,
        functional=functional,
    )


@pytest.mark.parametrize(
    "billed,unconditional,role,amount",
    [
        ("200000", False, "contract_liability", "80000"),
        ("100000", False, "contract_asset", "20000"),
        ("100000", True, "unbilled_receivable", "20000"),
    ],
)
def test_original_cutover_adapter_retains_source_and_actual_amount(
    billed, unconditional, role, amount
):
    value, output = original(billed, unconditional)
    nodes = output["books"][0]["trace"]["nodes"]
    assert not any(n["id"] == f"{role}:{w.CONTRACT}@{w.ENTITY}:{PERIOD.key}" for n in nodes)
    before = deepcopy(output)
    result = read(value, output)
    assert result is not None
    amounts, source = result
    assert amounts == {
        r: Decimal(amount) if r == role else Decimal(0) for r in tie_outs.ROLLFORWARD_BALANCES
    }
    assert source["members"] == [w.CONTRACT]
    assert source["nodes"]
    assert source["effective_date"] == w.CUTOVER.isoformat()
    assert read(value, output, functional=True) == result
    assert output == before
    # Neither old input revisions nor a group net amount may masquerade as a member balance.
    assert read(replace(value, evidence_revision=40), output) is None
    assert (
        read(
            replace(value, group=replace(value.group, member_contract_keys=(w.CONTRACT, "OTHER"))),
            output,
        )
        is None
    )


def test_cutover_adapter_rejects_inconsistent_native_sources():
    value, output = original("200000")
    row = output["books"][0]["disclosure_rollforwards"][0]
    row["lines"]["CONTRACT_LIABILITY"]["CLOSING"] += 1
    with pytest.raises(Problem) as refused:
        read(value, output)
    assert "sources do not reconcile" in refused.value.errors[0].message


@pytest.mark.parametrize("unconditional", [False, True])
def test_original_current_parts_use_retained_maturity(unconditional):
    value, _ = original("100000", unconditional)
    value = replace(value, evidence_revision=42)
    output = json.loads(canonical_bytes(compute(value)))
    result = acquisition_native.single_member_cutover(
        value,
        output,
        member=w.CONTRACT,
        book="ASC606",
        entity=w.ENTITY,
        period=PERIOD,
        functional=False,
        include_current=True,
    )
    assert result is not None
    amounts, snapshot = result
    assert amounts["contract_liability_current"] == 0
    assert amounts["contract_asset_current"] == (0 if unconditional else Decimal("20000"))
    assert snapshot["maturity"]["obligations"][w.SUBJECT]["expected_relief"] == 12000000
    old = replace(value, evidence_revision=41)
    with pytest.raises(Problem):
        acquisition_native.single_member_cutover(
            old,
            json.loads(canonical_bytes(compute(old))),
            member=w.CONTRACT,
            book="ASC606",
            entity=w.ENTITY,
            period=PERIOD,
            functional=False,
            include_current=True,
        )


@pytest.mark.parametrize(
    "policy,current",
    [
        ("POB_DEBIT_POSITIONS", "20000"),
        ("CUMULATIVE_SSP_DELIVERED", "60000"),
    ],
)
def test_mixed_maturity_reads_original_asset_attribution(policy, current):
    from datetime import date

    from support.cpc_worlds import line

    value, _ = original("100000")
    events = []
    for event in value.events:
        payload = dict(event.payload)
        if event.event_type == "CONTRACT_BOOKED":
            payload["lines"] = [
                *payload["lines"],
                line(
                    "L2-LONG",
                    "SUB-24M",
                    "1",
                    "240000.00",
                    start=w.INCEPTION,
                    end=date(2027, 12, 31),
                ),
            ]
            event = replace(event, obligation_keys=(w.OBLIGATION, "L2-LONG"))
        elif event.event_type == "OPENING_BALANCE_ESTABLISHED":
            second = {**payload["obligations"][0], "obligation_key": "L2-LONG"}
            payload["obligations"] = [*payload["obligations"], second]
            event = replace(event, obligation_keys=(w.OBLIGATION, "L2-LONG"))
        events.append(replace(event, payload=payload))
    book = value.books[0]
    extended = bundles.entity(start=w.INCEPTION, months=36, books=("ASC606",))
    entity = replace(
        value.entities[0],
        periods=(
            *value.entities[0].periods,
            *(
                replace(p, states=(("ASC606", "future"),))
                for p in extended.periods
                if p.fiscal_year == 2027
            ),
        ),
    )
    value = replace(
        value,
        entities=(entity,),
        evidence_revision=43,
        events=tuple(events),
        books=(
            replace(
                book,
                policies=tuple(
                    replace(item, value=policy)
                    if item.code == "position.reclass_attribution_key"
                    else item
                    for item in book.policies
                ),
            ),
        ),
    )
    output = json.loads(canonical_bytes(compute(value)))
    result = acquisition_native.single_member_cutover(
        value,
        output,
        member=w.CONTRACT,
        book="ASC606",
        entity=w.ENTITY,
        period=PERIOD,
        functional=False,
        include_current=True,
    )
    assert result is not None
    amounts, snapshot = result
    assert amounts["contract_asset"] == Decimal("100000")
    assert amounts["contract_asset_current"] == Decimal(current)
    attribution = snapshot["maturity"]["asset_attribution"]
    assert attribution["policy"] == policy
    assert sum(item["contract_asset"] for item in attribution["parts"].values()) == 10000000
    previous = replace(value, evidence_revision=42)
    prior_output = json.loads(canonical_bytes(compute(previous)))
    # Disclosure evidence does not change posting, scheduling or ordinary balances.
    for field in ("posting_intents", "schedules", "balances"):
        assert output["books"][0][field] == prior_output["books"][0][field]
    with pytest.raises(Problem):
        acquisition_native.single_member_cutover(
            previous,
            prior_output,
            member=w.CONTRACT,
            book="ASC606",
            entity=w.ENTITY,
            period=PERIOD,
            functional=False,
            include_current=True,
        )
    row = output["books"][0]["disclosure_rollforwards"][0]
    row["obligation_closing"]["asset_attribution"]["parts"][w.SUBJECT]["contract_asset"] += 1
    with pytest.raises(Problem) as refused:
        acquisition_native.single_member_cutover(
            value,
            output,
            member=w.CONTRACT,
            book="ASC606",
            entity=w.ENTITY,
            period=PERIOD,
            functional=False,
            include_current=True,
        )
    assert "does not reconcile" in refused.value.errors[0].message
