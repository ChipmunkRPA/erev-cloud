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
