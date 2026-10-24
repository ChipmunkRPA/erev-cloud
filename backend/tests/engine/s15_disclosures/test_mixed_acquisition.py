"""Ordinary activity must not become a residual at another member's acquisition date."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support import onboarding_worlds as w

from erev_engine import compute


def mixed_value(invoice_day, billed, consumption):
    value = w.two_contracts(as_of=date(2026, 1, 31))
    ordinary = w.COLLIDING[0]
    events = [
        replace(e, payload=w.opening_payload(billed_cum=billed))
        if e.event_type == "OPENING_BALANCE_ESTABLISHED"
        else e
        for e in value.events
        if not (e.contract_key == ordinary and e.event_type == "OPENING_BALANCE_ESTABLISHED")
    ]
    events.append(
        bundles.event(
            ordinary,
            4,
            "BILLING_RECORDED",
            invoice_day,
            {
                "invoice_number": "ORDINARY",
                "line_external_id": "ORDINARY-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("240000"),
                "issue_date": invoice_day,
            },
            obligation_keys=[w.OBLIGATION],
        )
    )
    value = replace(
        value,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(p, value=consumption)
                    if p.code == "rollforward.opening_liability_consumption"
                    else p
                    for p in book.policies
                ),
            )
            for book in value.books
        ),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
    )
    return value


@pytest.mark.parametrize("invoice_day", [date(2025, 12, 30), w.CUTOVER])
@pytest.mark.parametrize("billed", ["240000", "0"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_CONTRACT", "FIFO_WITHIN_POB"])
def test_mixed_acquisition_keeps_activity_and_dates_netting(invoice_day, billed, consumption):
    value = mixed_value(invoice_day, billed, consumption)
    ordinary = w.COLLIDING[0]
    prior = compute(replace(value, evidence_revision=24)).books[0]
    current = compute(replace(value, evidence_revision=25)).books[0]
    assert current.posting_intents == prior.posting_intents
    assert current.fx_layer_movements == prior.fx_layer_movements
    row = next(r for r in current.disclosure_rollforwards if r.view == "TRANSACTION")
    assert row.lines["CONTRACT_LIABILITY"]["CLOSING"] == (24000000 if billed == "240000" else 0)
    for role, amounts in row.lines.items():
        assert amounts["OTHER"] == 0, (role, dict(amounts))
        assert amounts["CLOSING"] == sum(v for k, v in amounts.items() if k != "CLOSING")
    if invoice_day < w.CUTOVER:
        assert row.lines["CONTRACT_LIABILITY"]["INCREASES_BILLING"] == 24000000
        assert row.lines["CONTRACT_LIABILITY"]["BUSINESS_COMBINATIONS"] == (
            12000000 if billed == "240000" else -12000000
        )
    elif billed == "240000":
        # Ordinary revenue comes first; acquisition settles its asset before billing.
        assert row.lines["CONTRACT_ASSET"]["BUSINESS_COMBINATIONS"] == -12000000
        assert row.lines["CONTRACT_LIABILITY"]["BUSINESS_COMBINATIONS"] == 0
    if consumption == "FIFO_WITHIN_POB" and invoice_day < w.CUTOVER and billed == "240000":
        later = bundles.event(
            ordinary,
            5,
            "BILLING_RECORDED",
            date(2026, 1, 1),
            {
                "invoice_number": "LATER",
                "line_external_id": "LATER-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("100"),
                "issue_date": date(2026, 1, 1),
            },
            obligation_keys=[w.OBLIGATION],
        )
        subsequent = compute(replace(value, evidence_revision=25, events=(*value.events, later)))
        period = next(
            r
            for r in subsequent.books[0].disclosure_rollforwards
            if r.period_key == "FY2026-P01" and r.view == "TRANSACTION"
        )
        liability = period.lines["CONTRACT_LIABILITY"]
        assert liability["OPENING"] == 24000000
        assert liability["CLOSING"] == 22010000
        assert liability["REVENUE_FROM_OPENING_BALANCE"] == -2000000
        assert liability["OTHER"] == 0


@pytest.mark.parametrize("invoice_day", [date(2025, 12, 30), w.CUTOVER])
@pytest.mark.parametrize("billed", ["240000", "0"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_CONTRACT", "FIFO_WITHIN_POB"])
def test_mixed_functional_uses_original_fx_movements(invoice_day, billed, consumption):
    from erev_engine.bundle import FxRateInput, MappingRuleInput

    value = mixed_value(invoice_day, billed, consumption)
    rates = tuple(
        FxRateInput(
            f"{kind}-{p.period_key}",
            "v1",
            kind,
            "USD",
            "EUR",
            p.end_date,
            None if kind == "spot" else p.period_key,
            Decimal("0.88" if kind == "average" else "0.9"),
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
                    r.period_key or "",
                    r.version_key,
                ),
            )
        ),
        books=tuple(
            replace(
                b,
                account_mapping=replace(
                    b.account_mapping,
                    rules=tuple(
                        sorted(
                            (
                                *b.account_mapping.rules,
                                MappingRuleInput(
                                    "FX_GAIN_LOSS", None, None, None, None, None, "FX-GL", {}, 0, 0
                                ),
                            ),
                            key=lambda r: (
                                r.account_role,
                                r.clearing_purpose or "",
                                r.account_code,
                            ),
                        )
                    ),
                ),
            )
            for b in value.books
        ),
    )
    prior = compute(replace(value, evidence_revision=25)).books[0]
    current = compute(replace(value, evidence_revision=26)).books[0]
    retained = compute(replace(value, evidence_revision=27)).books[0]
    assert (
        replace(
            retained,
            disclosure_rollforwards=tuple(
                replace(r, acquisition_sources=None) for r in retained.disclosure_rollforwards
            ),
        )
        == current
    )
    nodes = {node.id for node in retained.trace.nodes}
    for evidence_row in retained.disclosure_rollforwards:
        sources = evidence_row.acquisition_sources
        assert sources is not None
        for role, amounts in evidence_row.lines.items():
            assert (
                sum(source["amounts"][role] for source in sources)
                == amounts["BUSINESS_COMBINATIONS"]
            )
        for source in sources:
            assert source["effective_date"] == w.CUTOVER.isoformat()
            if evidence_row.view == "FUNCTIONAL":
                assert source["kind"] == "ORIGINAL_FX_MOVEMENT"
                assert source["trace_node_id"] in nodes
                assert any(
                    move.columns["layer_key"] == source["layer_key"]
                    and move.columns["source_key"] == source["source_key"]
                    and move.columns["movement_kind"] == source["movement_kind"]
                    and move.trace_nodes["amount_functional"] == source["trace_node_id"]
                    for move in retained.fx_layer_movements
                )
            else:
                assert source["kind"] == "ORIGINAL_CUTOVER_EVENT"
                event = next(e for e in value.events if e.event_key == source["event_key"])
                assert event.event_type == "OPENING_BALANCE_ESTABLISHED"
                assert source["subjects"]
    assert current.posting_intents == prior.posting_intents
    assert current.fx_layer_movements == prior.fx_layer_movements
    row = next(r for r in current.disclosure_rollforwards if r.view == "FUNCTIONAL")
    for role, amounts in row.lines.items():
        assert amounts["OTHER"] == 0, (role, dict(amounts))
        assert amounts["CLOSING"] == sum(v for k, v in amounts.items() if k != "CLOSING")
    assert row.lines["CONTRACT_LIABILITY"]["CLOSING"] == (21600000 if billed == "240000" else 0)
    if invoice_day == w.CUTOVER:
        assets = row.lines["CONTRACT_ASSET"]
        assert assets["REVENUE_IN_EXCESS_OF_BILLING"] == 10560000
        assert assets["FX"] == 480000
        assert assets["BUSINESS_COMBINATIONS"] == (-11040000 if billed == "240000" else 10560000)
    if consumption == "FIFO_WITHIN_POB" and invoice_day < w.CUTOVER and billed == "240000":
        later = bundles.event(
            w.COLLIDING[0],
            5,
            "BILLING_RECORDED",
            date(2026, 1, 1),
            {
                "invoice_number": "NEXT",
                "line_external_id": "NEXT-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("100"),
                "issue_date": date(2026, 1, 1),
            },
            obligation_keys=[w.OBLIGATION],
        )
        following = compute(replace(value, evidence_revision=26, events=(*value.events, later)))
        next_row = next(
            r
            for r in following.books[0].disclosure_rollforwards
            if r.view == "FUNCTIONAL" and r.period_key == "FY2026-P01"
        )
        liability = next_row.lines["CONTRACT_LIABILITY"]
        assert liability["OPENING"] == 21600000
        assert liability["REVENUE_FROM_OPENING_BALANCE"] == -1800000
        assert liability["CLOSING"] == 19809000
        assert liability["OTHER"] == 0
