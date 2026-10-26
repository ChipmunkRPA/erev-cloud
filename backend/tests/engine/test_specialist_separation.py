"""Separation retains native accounting state, sources and independent balances."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from erev_engine import compute
from erev_engine.combination_split_balances import calculate, preview_input
from erev_engine.trace import reevaluate
from support import bundles, intent_totals
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles
from tests.engine.s06_modifications.test_s06_prospective import point_entry


def combined(path, day):
    v = _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / path))[-1].bundles[0]
    first = v.contracts[0]
    second = replace(
        first,
        external_id="SEP-B",
        modifications=(),
        judgements=tuple(
            replace(
                j,
                judgement_key="SEP-B/" + j.judgement_key,
                subject_key=j.subject_key.replace(first.external_id, "SEP-B", 1),
            )
            for j in first.judgements
        ),
    )
    booking = next(
        e
        for e in v.events
        if e.contract_key == first.external_id and e.event_type == "CONTRACT_BOOKED"
    )
    extras = [
        bundles.event(
            "SEP-B",
            1,
            "CONTRACT_BOOKED",
            booking.effective_date,
            booking.payload,
            obligation_keys=booking.obligation_keys,
        ),
        bundles.event("SEP-B", 2, "CONTRACT_ACTIVATED", booking.effective_date, {}),
    ]
    estimates = list(v.estimate_versions)
    for version in v.estimate_versions:
        if version.effective_date > day:
            continue
        original = version.estimate_key.split("/", 1)[0]
        new = replace(
            version,
            estimate_key=version.estimate_key.replace(original, "SEP-B", 1),
            version_key="SEP-B/" + version.version_key,
        )
        estimates.append(new)
        extras.append(
            bundles.event(
                "SEP-B",
                len(extras) + 1,
                "ESTIMATE_CHANGED",
                new.effective_date,
                {"estimate_version_id": new.version_key},
            )
        )
    v = replace(
        v,
        books=tuple(
            replace(
                b,
                policies=tuple(
                    sorted(
                        (
                            *(
                                replace(p, value="ENGINE") if p.code == "billing.posting" else p
                                for p in b.policies
                            ),
                            *(
                                replace(
                                    p,
                                    subject_key=p.subject_key.replace(
                                        first.external_id, "SEP-B", 1
                                    ),
                                )
                                for p in b.policies
                                if p.scope in {"CONTRACT", "OBLIGATION"}
                                and p.subject_key.startswith(first.external_id)
                            ),
                        ),
                        key=lambda p: (p.code, p.scope, p.subject_key),
                    )
                ),
            )
            for b in v.books
        ),
        evidence_revision=71,
        group=replace(
            v.group,
            member_contract_keys=tuple(sorted((first.external_id, "SEP-B"))),
            criterion="25_9_A",
        ),
        contracts=tuple(sorted((first, second), key=lambda c: c.external_id)),
        events=tuple(
            sorted(
                (*v.events, *extras), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
            )
        ),
        estimate_versions=tuple(sorted(estimates, key=lambda x: (x.estimate_key, x.version_no))),
    )
    return preview_input(
        v, effective_date=day, destinations={first.external_id: "LEFT", "SEP-B": "RIGHT"}
    )


def partial(policy="FIFO"):
    day = date(2026, 1, 16)
    v = combined("ret/RET-CHK-029-S3-EX22.yaml", day)
    a = v.contracts[0].external_id
    booking = next(e for e in v.events if e.contract_key == a and e.event_type == "CONTRACT_BOOKED")
    product = booking.payload["lines"][0]["product_code"]
    bprod = "SEP-PRODUCT"
    prod = next(p for p in v.group.products if p.code == product)
    original = v.ssp_versions[0]
    base = replace(
        original,
        entries=tuple(
            sorted(
                (*original.entries, point_entry(original.version_key, bprod, "100")),
                key=lambda e: e.entry_key,
            )
        ),
    )
    later = replace(
        base,
        version_key=base.version_key + "-SEP",
        version_no=base.version_no + 1,
        effective_from_date=day,
        entries=tuple(
            sorted(
                (
                    replace(e, ranges=point_entry(base.version_key + "-SEP", bprod, "200").ranges)
                    if e.product_code == bprod
                    else e
                    for e in base.entries
                ),
                key=lambda e: e.entry_key,
            )
        ),
    )
    events = []
    for e in v.events:
        if e.event_type == "DELIVERY_RECORDED" and e.contract_key == a:
            e = replace(e, payload={**e.payload, "quantity": Decimal(50)})
        if e.event_type == "CONTRACT_BOOKED" and e.contract_key == "SEP-B":
            e = replace(
                e,
                payload={
                    **e.payload,
                    "lines": [{**line, "product_code": bprod} for line in e.payload["lines"]],
                },
            )
        events.append(e)
    events.append(
        bundles.event(
            a,
            99999,
            "DELIVERY_RECORDED",
            date(2026, 2, 5),
            {
                "obligation_key": booking.payload["lines"][0]["obligation_key"],
                "quantity": "50",
                "trigger": "DELIVERY",
            },
            obligation_keys=booking.obligation_keys,
            record_seq=99999,
        )
    )
    return replace(
        v,
        group=replace(
            v.group,
            products=tuple(
                sorted((*v.group.products, replace(prod, code=bprod)), key=lambda p: p.code)
            ),
        ),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(base, later),
        books=tuple(
            replace(
                b,
                policies=tuple(
                    replace(p, value=policy)
                    if p.code == "fx.cl_layer_consumption"
                    else replace(p, value="ENGINE")
                    if p.code == "billing.posting"
                    else p
                    for p in b.policies
                ),
            )
            for b in v.books
        ),
    )


@pytest.mark.parametrize(
    "path, day",
    [
        ("ret/RET-CHK-029-S3-EX22.yaml", date(2026, 1, 16)),
        ("vc/VC-CHK-100-S3-EX21-EXTENDED.yaml", date(2027, 1, 16)),
        ("rec/REC-S5-EX19.yaml", date(2026, 12, 16)),
        ("rec/REC-S5-PROGRESS-VARIANTS-COSTRECOVERY.yaml", date(2026, 7, 1)),
        ("brk/BRK-S5-BREAKAGE-OWN.yaml", date(2026, 2, 1)),
        ("sfc/SFC-S3-EX26.yaml", date(2026, 6, 16)),
        ("ncc/NCC-CHK-135-S3-EX31.yaml", date(2026, 6, 16)),
    ],
)
def test_specialist_state_continues_and_reports_reconcile(path, day):
    value = combined(path, day)
    result = compute(value)
    book = result.books[0]
    assert reevaluate(book.trace) == {n.id: n.value for n in book.trace.nodes}
    baseline = compute(
        replace(
            value,
            events=tuple(
                e for e in value.events if "prospective_split_destinations" not in e.payload
            ),
        )
    ).books[0]
    for row in book.balances:
        end = next(p.end_date for p in value.entities[0].periods if p.period_key == row.period_key)
        if end < day:
            assert row == next(
                r
                for r in baseline.balances
                if (r.subject_key, r.period_key) == (row.subject_key, row.period_key)
            )
    for row in book.disclosure_rollforwards:
        assert all(v["OTHER"] == 0 for v in row.lines.values())
    outputs = [result]
    for phase in ("CLOSE_RELEASE", "FX_REMEASUREMENT", "NETTING_RECLASS"):
        outputs.append(intent_totals.close_pass(value, outputs, phase))
    for period in sorted({r.period_key for r in book.balances}):
        for role in ("CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE"):
            ledger = sum(
                line.amount_txn
                * (1 if line.side == ("C" if role == "CONTRACT_LIABILITY" else "D") else -1)
                for o in outputs
                for b in o.books
                for i in b.posting_intents
                if i.posting_period_key <= period
                for line in i.lines
                if line.account_role == role
            )
            assert ledger == sum(
                r.columns[role.lower() + "_txn"] for r in book.balances if r.period_key == period
            )


@pytest.mark.parametrize("policy,expected", [("FIFO", 770000), ("PRO_RATA", 776000)])
def test_partial_return_separation_preserves_old_rates_and_future_allocation(policy, expected):
    value = partial(policy)
    digest = value.sha256()
    result = compute(value).books[0]
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    nodes = {n.id: n for n in result.trace.nodes}
    from erev_api.explain.narratives import render

    assert all(
        render(n, nodes) for n in result.trace.nodes if n.formula_id.startswith("rec.separation.")
    )
    subject = value.contracts[0].external_id + "/L1-PROD"
    assert Decimal(nodes[f"revenue_cum:{subject}:FY2026-P01"].value) * 100 == 470000
    assert Decimal(nodes[f"revenue_cum:{subject}:FY2026-P02"].value) * 100 == expected
    row = next(r for r in result.obligation_versions if r.subject_key == subject)
    assert (
        row.columns["allocated_amount"]
        == row.columns["revenue_cum"] + row.columns["remaining_allocation"]
    )
    assert value.sha256() == digest
    assert compute(value).books[0] == result


@pytest.mark.parametrize("policy", ["FIFO", "PRO_RATA"])
def test_foreign_partial_returns_retain_sources_and_destination_balances(policy):
    from tests.engine.s15_disclosures.test_mixed_acquisition import foreign_value

    value = foreign_value(partial(policy))
    # Original invoices and credit memos are posted by the ERP in this foreign return case.
    value = replace(
        value,
        books=tuple(
            replace(
                b,
                policies=tuple(
                    replace(p, value="ERP") if p.code == "billing.posting" else p
                    for p in b.policies
                ),
            )
            for b in value.books
        ),
    )
    rate = next(r for r in value.fx_rates if r.rate_type == "spot")
    rates = (
        *value.fx_rates,
        replace(rate, rate_key="ORIGINAL-SPOT", effective_date=date(2026, 1, 1)),
        replace(
            rate, rate_key="SEPARATION-SPOT", effective_date=date(2026, 1, 16), rate=Decimal("1.15")
        ),
    )
    value = replace(
        value,
        fx_rates=tuple(
            sorted(
                rates,
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.period_key or "",
                    r.version_key,
                ),
            )
        ),
    )
    output = compute(value)
    book = output.books[0]
    assert reevaluate(book.trace) == {n.id: n.value for n in book.trace.nodes}
    assert {r.view for r in book.disclosure_rollforwards} == {"TRANSACTION", "FUNCTIONAL"}
    for row in book.disclosure_rollforwards:
        assert all(v["OTHER"] == 0 for v in row.lines.values())
        for lines in row.lines.values():
            assert lines["CLOSING"] == sum(v for k, v in lines.items() if k != "CLOSING")
    destinations = calculate(value, book_code="ASC606", as_of=date(2026, 2, 28))
    for role in ("contract_liability", "contract_asset", "unbilled_receivable"):
        assert sum(
            t.value for d in destinations for t in d.presentation if t.measure == role
        ) == sum(r.columns[role + "_txn"] for r in book.balances if r.period_key == "FY2026-P02")
    outputs = [output]
    for phase in ("CLOSE_RELEASE", "FX_REMEASUREMENT", "NETTING_RECLASS"):
        outputs.append(intent_totals.close_pass(value, outputs, phase))
    for output in outputs:
        for b in output.books:
            for intent in b.posting_intents:
                for suffix in ("txn", "functional"):
                    assert (
                        sum(
                            getattr(line, "amount_" + suffix) * (1 if line.side == "D" else -1)
                            for line in intent.lines
                        )
                        == 0
                    )


def test_breakage_separation_prices_only_unperformed_entitlement():
    from erev_engine.combination_split import prepare

    value = combined("brk/BRK-S5-BREAKAGE-OWN.yaml", date(2026, 2, 1))
    event = next(e for e in value.events if "prospective_split_destinations" in e.payload)
    plan = prepare(
        value,
        book_code="ASC606",
        event_key=event.event_key,
        destinations=event.payload["prospective_split_destinations"],
    )
    original, untouched = plan.members
    # Half of the original gift-card entitlement has been performed; the second
    # member has no redemptions. Only the remaining 50,000:100,000 SSP is pooled.
    assert original.remaining_ssp == 50000
    assert untouched.remaining_ssp == 100000
    assert original.remaining_after_minor == 5000000
    assert untouched.remaining_after_minor == 10000000


def test_successive_separations_keep_historical_return_entitlements():
    value = partial()
    third = replace(
        next(c for c in value.contracts if c.external_id == "SEP-B"), external_id="SEP-C"
    )
    events = [e for e in value.events if "prospective_split_destinations" not in e.payload]
    for e in value.events:
        if e.contract_key == "SEP-B":
            events.append(
                replace(e, event_key=e.event_key.replace("SEP-B", "SEP-C", 1), contract_key="SEP-C")
            )
    value = replace(
        value,
        contracts=tuple(sorted((*value.contracts, third), key=lambda c: c.external_id)),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        group=replace(
            value.group,
            member_contract_keys=tuple(sorted((*value.group.member_contract_keys, "SEP-C"))),
        ),
    )
    a = value.contracts[0].external_id
    first = preview_input(
        value,
        effective_date=date(2026, 1, 16),
        destinations={a: "LEFT", "SEP-B": "LEFT", "SEP-C": "RIGHT"},
    )
    second = preview_input(
        first, effective_date=date(2026, 1, 20), destinations={a: "FINAL", "SEP-B": "LEFT"}
    )
    before, after = compute(first).books[0], compute(second).books[0]
    assert reevaluate(after.trace) == {n.id: n.value for n in after.trace.nodes}
    for period in ("FY2026-P01", "FY2026-P02"):
        for member in value.group.member_contract_keys:
            subject = member + "/L1-PROD"
            node = f"revenue_cum:{subject}:{period}"
            assert next(n.value for n in before.trace.nodes if n.id == node) == next(
                n.value for n in after.trace.nodes if n.id == node
            )


def test_later_member_vc_reassessment_does_not_change_separated_member():
    value = combined("vc/VC-CHK-100-S3-EX21-EXTENDED.yaml", date(2027, 1, 16))
    future = {
        v.version_key for v in value.estimate_versions if v.effective_date > date(2027, 1, 16)
    }
    assert future
    prior = replace(
        value,
        estimate_versions=tuple(v for v in value.estimate_versions if v.version_key not in future),
        events=tuple(e for e in value.events if e.payload.get("estimate_version_id") not in future),
    )
    before, after = compute(prior).books[0], compute(value).books[0]
    assert [r for r in before.obligation_versions if r.subject_key.startswith("SEP-B/")] == [
        r for r in after.obligation_versions if r.subject_key.startswith("SEP-B/")
    ]
