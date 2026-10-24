"""Acquisition baselines enter POB eligibility after cutover, not as current billing."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support import onboarding_worlds as w

import erev_engine


@pytest.mark.parametrize("at", [date(2025, 12, 31), date(2026, 1, 31), date(2026, 2, 28)])
@pytest.mark.parametrize("pre_invoice", [False, True])
def test_acquired_pob_opening_preserves_baseline_and_journals(at, pre_invoice):
    extra = (
        []
        if at.year == 2025
        else [
            bundles.event(
                w.CONTRACT,
                5,
                "BILLING_RECORDED",
                at,
                {
                    "invoice_number": "POST-ACQ",
                    "line_external_id": "POST-ACQ-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("100.00"),
                    "issue_date": at,
                },
                obligation_keys=[w.OBLIGATION],
            )
        ]
    )
    if pre_invoice:
        extra.append(
            bundles.event(
                w.CONTRACT,
                4,
                "BILLING_RECORDED",
                date(2025, 6, 1),
                {
                    "invoice_number": "PRE-ACQ",
                    "line_external_id": "PRE-ACQ-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("240000.00"),
                    "issue_date": date(2025, 6, 1),
                },
                obligation_keys=[w.OBLIGATION],
            )
        )
    value = w.chk_121(
        as_of=at,
        extra=extra,
        states={"FY2025-P12": "open"},
        policies={
            "onboarding.method": "OPENING_BALANCES_AT_CUTOVER",
            "rollforward.opening_liability_consumption": "FIFO_WITHIN_POB",
        },
    )
    old = erev_engine.compute(replace(value, evidence_revision=13))
    new = erev_engine.compute(replace(value, evidence_revision=14))
    latest = erev_engine.compute(replace(value, evidence_revision=15))
    assert latest.books == new.books  # Existing targets retain priority over cutover fallback.
    for prior, book in zip(old.books, new.books, strict=True):
        assert book.posting_intents == prior.posting_intents
        assert prior.disclosure_rollforwards[0].obligation_closing == {
            "status": "UNAVAILABLE",
            "reason": "Original principal, same-entity sources are required.",
        }
        assert book.disclosure_rollforwards
        row = next(row for row in book.disclosure_rollforwards if row.view == "TRANSACTION")
        assert row.obligation_closing["status"] == "AVAILABLE"
        item = row.obligation_closing["obligations"][w.SUBJECT]
        original = 12000000 if book.book_code == "ASC606" else 9000000
        monthly = 1000000 if book.book_code == "ASC606" else 750000
        elapsed = 0 if at.year == 2025 else at.month
        assert item["liability"] == original - elapsed * monthly + (10000 if at.year == 2026 else 0)
        assert any(source.startswith("opening_revenue_cum@") for source in item["sources"])
        values = row.lines["CONTRACT_LIABILITY"]
        assert values["CLOSING"] == item["liability"]
        if elapsed:
            assert values["REVENUE_FROM_OPENING_BALANCE"] == -monthly
            assert values["REVENUE_FROM_OTHER_INCREASES"] == 0
        else:
            assert values["OPENING"] == 0
            assert values["BUSINESS_COMBINATIONS"] == original


def test_acquired_baseline_does_not_override_authenticated_frozen_opening():
    from types import SimpleNamespace as NS

    from erev_engine.errors import EngineError
    from erev_engine.stages.s15_disclosures.rollforward import _within_obligations

    records = NS(acquired_pob_opening=True, flows=())
    own = [NS(subject_key="C/P", opening=None)]
    lines = {
        "CONTRACT_LIABILITY": {
            "OPENING": 100,
            "REVENUE_FROM_OPENING_BALANCE": 0,
            "REVENUE_FROM_OTHER_INCREASES": 0,
        }
    }
    with pytest.raises(EngineError, match="complete original cutover baselines"):
        _within_obligations(
            records, own, "US", date(2026, 1, 1), date(2026, 1, 31), date(2025, 12, 31), lines
        )
    _within_obligations(
        records,
        own,
        "US",
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2025, 12, 31),
        lines,
        opening_obligations={"C/P": 100},
    )
    assert lines["CONTRACT_LIABILITY"]["REVENUE_FROM_OPENING_BALANCE"] == 0


@pytest.mark.parametrize("method", ["OPENING_BALANCES_AT_CUTOVER", "RECOMPUTE_FROM_INCEPTION"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_POB", "FIFO_WITHIN_CONTRACT"])
def test_closed_cutover_uses_original_baseline_without_posting(method, consumption):
    value = w.chk_121(
        as_of=date(2025, 12, 31),
        policies={
            "onboarding.method": method,
            "rollforward.opening_liability_consumption": consumption,
        },
    )
    prior = erev_engine.compute(replace(value, evidence_revision=14))
    current = erev_engine.compute(replace(value, evidence_revision=15))
    for old, book in zip(prior.books, current.books, strict=True):
        assert old.posting_intents == book.posting_intents == ()
        row = next(r for r in book.disclosure_rollforwards if r.view == "TRANSACTION")
        old_row = next(r for r in old.disclosure_rollforwards if r.view == "TRANSACTION")
        amount = 12000000 if book.book_code == "ASC606" else 9000000
        assert old_row.lines["CONTRACT_LIABILITY"]["CLOSING"] == 0
        assert old_row.lines["CONTRACT_LIABILITY"]["OTHER"] == -amount
        values = row.lines["CONTRACT_LIABILITY"]
        assert values["OPENING"] == 0
        assert values["BUSINESS_COMBINATIONS"] == values["CLOSING"] == amount
        assert values["OTHER"] == values["REVENUE_FROM_OPENING_BALANCE"] == 0
        for role, lines in row.lines.items():
            assert lines["CLOSING"] == sum(v for k, v in lines.items() if k != "CLOSING"), role


@pytest.mark.parametrize("cutover_open", [False, True])
def test_cutover_billing_evidence_serves_original_pob_reader_without_posting(
    monkeypatch, cutover_open
):
    from types import SimpleNamespace as NS
    from uuid import UUID

    from support import cpc_worlds as cpc

    from erev_api.domain.reports import opening_relief_pob as pob
    from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow

    value = w.chk_121(
        as_of=date(2025, 12, 31),
        states={"FY2025-P12": "open"} if cutover_open else None,
        policies={"onboarding.method": "OPENING_BALANCES_AT_CUTOVER"},
    )
    old = erev_engine.compute(replace(value, evidence_revision=16))
    new = erev_engine.compute(replace(value, evidence_revision=17))
    entity = UUID(int=1)
    session = NS(
        execute=lambda *a: NS(
            mappings=lambda: NS(
                all=lambda: [
                    dict(
                        obligation_key=w.OBLIGATION,
                        performing_entity_id=entity,
                        principal_agent="PRINCIPAL",
                    )
                ]
            )
        )
    )
    row = NS(
        version_id=UUID(int=2),
        contract_id=UUID(int=3),
        entity_id=entity,
        external_id=w.CONTRACT,
        currency="USD",
    )
    period = NS(key="FY2025-P12", end=date(2025, 12, 31))
    for prior, book in zip(old.books, new.books, strict=True):
        assert book.posting_intents == prior.posting_intents
        assert book.fx_layer_movements == prior.fx_layer_movements
        assert book.disclosure_rollforwards == prior.disclosure_rollforwards
        assert cpc.trace_mismatches(book.trace) == []
        if cutover_open:
            assert book.trace == prior.trace
        else:
            assert not any(
                n.id == f"billed_cum:{w.SUBJECT}:{period.key}" for n in prior.trace.nodes
            )
        monkeypatch.setattr(pob.store, "load_trace", lambda *a, trace=book.trace: trace)
        monthly = Decimal("10000" if book.book_code == "ASC606" else "7500")
        opening = monthly * 12
        relief, facts = pob.calculate(
            session,
            row,
            period,
            [
                Entry(
                    order=(1,), flow=Flow(monthly, True), subject_key=w.SUBJECT, line_id=UUID(int=4)
                )
            ],
            opening,
            monthly,
        )
        assert relief == monthly
        assert Decimal(facts["obligations"][w.SUBJECT]["opening_billing"]) == (
            Decimal("240000") if book.book_code == "ASC606" else Decimal("90000")
        )


@pytest.mark.parametrize(
    "cutover_open,missing_rates", [(False, False), (True, False), (False, True)]
)
def test_foreign_cutover_evidence_is_readable_without_financial_changes(
    monkeypatch, cutover_open, missing_rates
):
    from types import SimpleNamespace as NS
    from uuid import UUID

    from support import cpc_worlds as cpc

    from erev_api.domain.reports import opening_relief_pob as pob
    from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow
    from erev_engine.bundle import FxRateInput

    value = w.chk_121(
        as_of=w.CUTOVER,
        states={"FY2025-P12": "open"} if cutover_open else None,
        accounts=[("FX_GAIN_LOSS", None, "FX-GL")],
        policies={"onboarding.method": "OPENING_BALANCES_AT_CUTOVER"},
    )
    rates = tuple(
        FxRateInput(
            f"{kind}-{p.period_key}",
            "v1",
            kind,
            "USD",
            "EUR",
            p.end_date,
            None if kind == "spot" else p.period_key,
            Decimal("0.9"),
        )
        for p in value.entities[0].periods
        for kind in ("spot", "average", "closing")
    )
    value = replace(
        value,
        currencies=bundles.currencies("EUR", "USD"),
        entities=tuple(replace(e, functional_currency="EUR") for e in value.entities),
        fx_rates=tuple(
            sorted(
                rates,
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
    if missing_rates:
        value = replace(value, fx_rates=())
    old = erev_engine.compute(replace(value, evidence_revision=17))
    new = erev_engine.compute(replace(value, evidence_revision=18))
    current = erev_engine.compute(replace(value, evidence_revision=19))
    for prior, book in zip(new.books, current.books, strict=True):
        assert replace(book, disclosure_rollforwards=prior.disclosure_rollforwards) == prior
        if missing_rates:
            assert book == prior
            continue
        snapshot = next(r for r in book.disclosure_rollforwards if r.view == "FUNCTIONAL")
        expected = 10800000 if book.book_code == "ASC606" else 8100000
        values = snapshot.lines["CONTRACT_LIABILITY"]
        assert values["CLOSING"] == values["BUSINESS_COMBINATIONS"] == expected
        assert values["OPENING"] == values["OTHER"] == 0
        assert snapshot.obligation_closing["status"] == "AVAILABLE"
        assert snapshot.obligation_closing["obligations"][w.SUBJECT]["liability"] == expected
        for values in snapshot.lines.values():
            assert values["CLOSING"] == sum(v for k, v in values.items() if k != "CLOSING")

    entity = UUID(int=1)
    session = NS(
        execute=lambda *a: NS(
            mappings=lambda: NS(
                all=lambda: [
                    dict(
                        obligation_key=w.OBLIGATION,
                        performing_entity_id=entity,
                        principal_agent="PRINCIPAL",
                    )
                ]
            )
        )
    )
    row = NS(
        version_id=UUID(int=2),
        contract_id=UUID(int=3),
        entity_id=entity,
        external_id=w.CONTRACT,
        currency="USD",
    )
    period = NS(key="FY2025-P12", end=w.CUTOVER)
    for prior, book in zip(old.books, new.books, strict=True):
        assert book.posting_intents == prior.posting_intents
        assert book.fx_layer_movements == prior.fx_layer_movements
        assert book.disclosure_rollforwards == prior.disclosure_rollforwards
        assert replace(book, trace=prior.trace) == prior
        if missing_rates:
            assert book == prior
            assert not any(node.id.startswith("revenue_functional:") for node in book.trace.nodes)
            continue
        after = {node.id: node for node in book.trace.nodes}
        assert all(after[node.id] == node for node in prior.trace.nodes)
        assert cpc.trace_mismatches(book.trace) == []
        if cutover_open:
            assert book.trace == prior.trace
        monkeypatch.setattr(pob.store, "load_trace", lambda *a, trace=book.trace: trace)
        monthly = Decimal("9000" if book.book_code == "ASC606" else "6750")
        relief, facts = pob.calculate(
            session,
            row,
            period,
            [
                Entry(
                    order=(1,), flow=Flow(monthly, True), subject_key=w.SUBJECT, line_id=UUID(int=4)
                )
            ],
            monthly * 12,
            monthly,
            functional_currency="EUR",
        )
        assert relief == monthly
        expected = Decimal("216000" if book.book_code == "ASC606" else "81000")
        assert Decimal(facts["obligations"][w.SUBJECT]["opening_billing"]) == expected


def test_mixed_closing_keeps_ordinary_history_and_skips_only_acquired_pre_cutover():

    from types import SimpleNamespace as NS

    from support.fold import book_context, fold_book

    from erev_engine.stages.s12_fx_entities.layers import ControlFlow
    from erev_engine.stages.s15_disclosures.obligation_closing import capture
    from erev_engine.stages.s15_disclosures.rollforward import BalanceInputs

    value = w.chk_121(
        as_of=date(2026, 1, 31),
        states={"FY2025-P12": "open"},
        policies={"onboarding.method": "OPENING_BALANCES_AT_CUTOVER"},
    )
    state = fold_book(value, "ASC606")
    acquired = state.obligations[0]
    ordinary = replace(acquired, subject_key="ORDINARY/O1", contract_key="ORDINARY", opening=None)
    state = replace(state, obligations=(acquired, ordinary))
    ctx = book_context(value, "ASC606")
    entity = acquired.contracting_entity
    period = next(p for p in ctx.entities[entity].periods if p.end_date == date(2026, 1, 31))
    before, after = date(2025, 11, 30), date(2026, 1, 10)

    def flow(kind, key, subject, amount, day):
        return ControlFlow(kind, entity, subject, key, day, 1, amount, unconditional_date=day)

    records = BalanceInputs(
        flows=(
            flow("BILLING", "SHARED", "GROUP", 100000, before),
            flow("REVENUE", "ORD-REV", ordinary.subject_key, 10000, before),
            flow("REVENUE", "PRE-ACQ-REV", acquired.subject_key, 60000, before),
            flow("BILLING", "OPENING", "GROUP", 23940000, w.CUTOVER),
            flow("REVENUE", "OPENING-REV", acquired.subject_key, 11940000, w.CUTOVER),
            flow("BILLING", "ACQ-POST", "GROUP", 10000, after),
            flow("REVENUE", "ACQ-REV", acquired.subject_key, 2000, after),
            flow("CREDIT_MEMO", "ORD-CREDIT", "GROUP", 5000, after),
            flow("NEGATIVE_REVENUE", "ORD-RETURN", ordinary.subject_key, 3000, after),
        ),
        presented=(),
        right_classes=(),
        schedule_lines=(),
        attribution={
            "SHARED": {acquired.subject_key: 60000, ordinary.subject_key: 40000},
            "OPENING": {acquired.subject_key: 23940000},
            "ACQ-POST": {acquired.subject_key: 10000},
            "ORD-CREDIT": {ordinary.subject_key: -5000},
        },
        acquired_pob_opening=True,
        opening_billing_sources=True,
    )
    original = capture(ctx, state, records, entity, period, functional=False)
    assert original == {
        "status": "UNAVAILABLE",
        "reason": "Complete original acquisition baselines are required.",
    }
    updated = replace(records, mixed_acquisition_closing=True)
    result = capture(ctx, state, updated, entity, period, functional=False)
    assert result["status"] == "AVAILABLE"
    assert result["obligations"][ordinary.subject_key]["liability"] == 28000
    assert result["obligations"][acquired.subject_key]["liability"] == 12008000
    assert "SHARED" in result["obligations"][ordinary.subject_key]["sources"]
    assert "SHARED" not in result["obligations"][acquired.subject_key]["sources"]
    assert "PRE-ACQ-REV" not in result["obligations"][acquired.subject_key]["sources"]
    functional = capture(ctx, state, updated, entity, period, functional=True)
    assert functional["status"] == "UNAVAILABLE"
    # Functional capture consumes the exact original FX records, including the cutover
    # correction, and reconciles their transaction amounts before reporting any totals.
    ctx = replace(ctx, entities={entity: replace(ctx.entities[entity], functional_currency="EUR")})
    billings = tuple(
        NS(
            entity=entity,
            period_key=period.period_key,
            source_key=document,
            subject_key=subject,
            amount_txn=amount,
            amount_functional=amount * 9 // 10,
            node_id=f"original-fx:{document}:{subject}",
        )
        for document, shares in records.attribution.items()
        for subject, amount in shares.items()
    )
    targets = tuple(
        NS(
            entity=entity,
            subject_key=subject,
            measure="revenue_cum",
            period_key=period.period_key,
            amount_txn=amount,
            amount_functional=amount * 9 // 10,
            txn_currency="USD",
            functional_currency="EUR",
        )
        for subject, amount in ((acquired.subject_key, 12002000), (ordinary.subject_key, 7000))
    )
    fx = NS(billing_attribution_sources=billings, functional_targets=targets)
    functional = capture(ctx, state, replace(updated, fx=fx), entity, period, functional=True)
    assert functional["status"] == "AVAILABLE"
    assert functional["obligations"][acquired.subject_key]["liability"] == 10807200
    assert functional["obligations"][ordinary.subject_key]["liability"] == 25200
    incomplete = NS(billing_attribution_sources=billings[1:], functional_targets=targets)
    assert (
        capture(ctx, state, replace(updated, fx=incomplete), entity, period, functional=True)[
            "status"
        ]
        == "UNAVAILABLE"
    )


def test_revision_24_preserves_single_acquisition_outputs():
    value = w.chk_121(
        as_of=date(2026, 1, 31),
        states={"FY2025-P12": "open"},
        policies={"onboarding.method": "OPENING_BALANCES_AT_CUTOVER"},
    )
    old = erev_engine.compute(replace(value, evidence_revision=23))
    new = erev_engine.compute(replace(value, evidence_revision=24))
    assert new.books == old.books
