"""Original acquired control balances remain with the contracting entity across cutover."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles, cpc_worlds
from support import onboarding_worlds as w

import erev_engine
from erev_engine.bundle import FxRateInput
from erev_engine.errors import EngineError


@pytest.mark.parametrize("at", [w.CUTOVER, date(2026, 1, 31)])
@pytest.mark.parametrize("foreign", [False, True])
def test_acquired_cross_entity_control_sources(at, foreign):
    value = w.chk_121(
        as_of=at,
        policies={
            "onboarding.method": "OPENING_BALANCES_AT_CUTOVER",
            "rollforward.opening_liability_consumption": "FIFO_WITHIN_POB",
        },
        accounts=[
            ("INTERCOMPANY_DUE_FROM", None, "IC-FROM"),
            ("INTERCOMPANY_DUE_TO", None, "IC-TO"),
            ("FX_GAIN_LOSS", None, "FX"),
        ],
    )
    original = value.entities[0]
    performer = replace(original, code="PERFORMER")
    rates = tuple(
        FxRateInput(
            f"{kind}-{p.period_key}",
            "v1",
            kind,
            "USD",
            "EUR",
            p.end_date,
            None if kind == "spot" else p.period_key,
            Decimal("0.9" if p.end_date.year == 2025 else "0.8"),
        )
        for p in original.periods
        for kind in ("spot", "average", "closing")
    )
    value = replace(
        value,
        evidence_revision=20,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    sorted(
                        [
                            *book.policies,
                            *(
                                replace(
                                    p,
                                    subject_key=p.subject_key.replace(
                                        original.code + "@", performer.code + "@", 1
                                    ),
                                )
                                for p in book.policies
                                if p.scope == "PERIOD"
                            ),
                        ],
                        key=lambda p: (p.code, p.scope, p.subject_key),
                    )
                ),
            )
            for book in value.books
        ),
        entities=tuple(
            sorted(
                [
                    replace(original, functional_currency="EUR" if foreign else "USD"),
                    performer,
                ],
                key=lambda e: e.code,
            )
        ),
        currencies=bundles.currencies("EUR", "USD"),
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
        )
        if foreign
        else (),
        events=tuple(
            replace(
                event,
                payload={
                    **event.payload,
                    "lines": [
                        {**line, "performing_entity_code": performer.code}
                        for line in event.payload["lines"]
                    ],
                },
            )
            if event.event_type == "CONTRACT_BOOKED"
            else event
            for event in value.events
        ),
    )
    # The pre-source revision can still calculate the financial output using contract FIFO.
    # POL-126 changes only the disclosure classification, not recognition or posting.
    prior = erev_engine.compute(
        replace(
            value,
            evidence_revision=13,
            books=tuple(
                replace(
                    book,
                    policies=tuple(
                        replace(p, value="FIFO_WITHIN_CONTRACT")
                        if p.code == "rollforward.opening_liability_consumption"
                        else p
                        for p in book.policies
                    ),
                )
                for book in value.books
            ),
        )
    )
    if at == w.CUTOVER:
        with pytest.raises(
            EngineError, match="Acquisition closing requires complete original baselines"
        ):
            erev_engine.compute(replace(value, evidence_revision=19))
    output = erev_engine.compute(value)
    for old, book in zip(prior.books, output.books, strict=True):
        assert book.posting_intents == old.posting_intents
        assert book.fx_layer_movements == old.fx_layer_movements
        assert book.balances == old.balances
        assert book.schedules == old.schedules
        assert cpc_worlds.trace_mismatches(book.trace) == []
        assert book.disclosure_rollforwards
        for row in book.disclosure_rollforwards:
            assert row.entity == original.code
            source = row.obligation_closing
            assert source["status"] == "AVAILABLE", source
            item = source["obligations"][w.SUBJECT]
            assert item["relief_basis"] == "CONTRACTING_ENTITY_CONTROL"
            assert item["performing_entity"] == performer.code
            amount = 12000000 if book.book_code == "ASC606" else 9000000
            monthly = amount // 12
            factor = Decimal("0.9") if row.view == "FUNCTIONAL" and foreign else Decimal(1)
            remaining = amount - (monthly if row.closing_date.year == 2026 else 0)
            assert item["liability"] == int(remaining * factor), (
                row.period_key,
                row.view,
                row.lines,
                item,
            )
            lines = row.lines["CONTRACT_LIABILITY"]
            assert lines["CLOSING"] == item["liability"]
            assert lines["OTHER"] == 0
            if row.closing_date.year == 2026:
                assert lines["REVENUE_FROM_OPENING_BALANCE"] == -int(monthly * factor)
            else:
                assert lines["BUSINESS_COMBINATIONS"] == int(amount * factor)
        if at == w.CUTOVER:
            assert book.posting_intents == ()
