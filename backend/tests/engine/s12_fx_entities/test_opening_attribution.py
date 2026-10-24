"""Original acquisition billing corrections share the existing FX flow, not a new rate."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import erev_engine
import pytest
from erev_engine.bundle import FxRateInput
from support import bundles, cpc_worlds as cpc, onboarding_worlds as w


@pytest.mark.parametrize("prior_invoice", [False, True])
def test_acquisition_correction_retains_original_pob_fx_without_changing_postings(prior_invoice):
    extra = []
    if prior_invoice:
        extra.append(
            bundles.event(
                w.CONTRACT,
                4,
                "BILLING_RECORDED",
                date(2025, 6, 1),
                {
                    "invoice_number": "PRE",
                    "line_external_id": "PRE-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("100000"),
                    "issue_date": date(2025, 6, 1),
                },
                obligation_keys=[w.OBLIGATION],
            )
        )
    extra.append(
        bundles.event(
            w.CONTRACT,
            5,
            "BILLING_RECORDED",
            date(2026, 1, 31),
            {
                "invoice_number": "POST",
                "line_external_id": "POST-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("100"),
                "issue_date": date(2026, 1, 31),
            },
            obligation_keys=[w.OBLIGATION],
        )
    )
    value = w.chk_121(
        extra=extra,
        accounts=[("FX_GAIN_LOSS", None, "FX-GL")],
        policies={"onboarding.method": "OPENING_BALANCES_AT_CUTOVER"},
    )
    rates = [
        FxRateInput(
            "initial",
            "FX-PUBLISHED@v1",
            "spot",
            "USD",
            "EUR",
            date(2025, 1, 1),
            None,
            Decimal("0.8"),
        )
    ]
    rates.append(
        FxRateInput(
            "invoice",
            "FX-PUBLISHED@v1",
            "spot",
            "USD",
            "EUR",
            date(2025, 6, 1),
            None,
            Decimal("0.8"),
        )
    )
    for p in value.entities[0].periods:
        for kind in ("spot", "average", "closing"):
            rates.append(
                FxRateInput(
                    f"{kind}-{p.period_key}",
                    "FX-PUBLISHED@v1",
                    kind,
                    "USD",
                    "EUR",
                    p.end_date,
                    None if kind == "spot" else p.period_key,
                    Decimal("0.9" if p.end_date >= w.CUTOVER else "0.8"),
                )
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
    old = erev_engine.compute(replace(value, evidence_revision=15))
    new = erev_engine.compute(replace(value, evidence_revision=16))
    pob_value = replace(
        value,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(policy, value="FIFO_WITHIN_POB")
                    if policy.code == "rollforward.opening_liability_consumption"
                    else policy
                    for policy in book.policies
                ),
            )
            for book in value.books
        ),
    )
    pob = erev_engine.compute(replace(pob_value, evidence_revision=16))
    for before, after, classified in zip(old.books, new.books, pob.books, strict=True):
        assert classified.posting_intents == after.posting_intents
        functional = next(r for r in classified.disclosure_rollforwards if r.view == "FUNCTIONAL")
        assert functional.obligation_closing["status"] == "AVAILABLE"
        # ASC606 releases 10,000 at .9; IFRS releases 7,500 from the original
        # .8 prepaid layer when present, otherwise from the .9 cutover layer.
        relief = 900000 if after.book_code == "ASC606" else 600000 if prior_invoice else 675000
        assert functional.lines["CONTRACT_LIABILITY"]["REVENUE_FROM_OPENING_BALANCE"] == -relief
        assert cpc.trace_mismatches(classified.trace) == []
        assert before.posting_intents == after.posting_intents
        assert before.fx_layer_movements == after.fx_layer_movements
        assert cpc.trace_mismatches(after.trace) == []
        nodes = [n for n in after.trace.nodes if n.id.startswith("billing_opening_attributed@")]
        assert len(nodes) == 1
        expected = Decimal("240000" if after.book_code == "ASC606" else "90000")
        if prior_invoice:
            expected -= Decimal("100000")
        assert Decimal(nodes[0].value) == expected
        activity = [
            n
            for n in after.trace.nodes
            if n.id.startswith("billing_obligation_activity_functional:")
            and n.params["source_key"].endswith("/opening_billed_cum")
        ]
        assert len(activity) == 1
        assert Decimal(activity[0].value) * Decimal(
            activity[0].params["sign"]
        ) == expected * Decimal("0.9")
        assert not any(n.id.startswith("billing_opening_attributed@") for n in before.trace.nodes)

        from types import SimpleNamespace as NS
        from erev_api.domain.reports.opening_pob_functional_nodes import read

        billed, revenue, sources = read(
            {node.id: node for node in after.trace.nodes},
            subject=w.SUBJECT,
            period=NS(key="FY2025-P12", end=w.CUTOVER),
            txn_currency="USD",
            currency="EUR",
            billed=Decimal("240000" if after.book_code == "ASC606" else "90000"),
            revenue=Decimal("120000" if after.book_code == "ASC606" else "0"),
        )
        assert billed == expected * Decimal("0.9") + (Decimal("80000") if prior_invoice else 0)
        assert revenue >= 0
        assert nodes[0].id in sources


@pytest.mark.parametrize("issue", ["mixed", "missing", "raw_mismatch"])
def test_ambiguous_or_incomplete_cutover_does_not_emit_partial_attribution(monkeypatch, issue):
    from types import SimpleNamespace as NS
    from erev_engine.stages.s12_fx_entities import opening_attribution as opening
    from erev_engine.stages.s12_fx_entities.layers import ControlFlow
    from erev_engine.trace import TraceBuilder

    own = [
        NS(
            subject_key=f"C/{key}",
            contract_key="C",
            contracting_entity="US",
            obligation_key=key,
            opening={"event_key": "E", "billed_cum": Decimal("1")},
            baseline=NS(billed_cum=100, cutover_date=w.CUTOVER),
        )
        for key in ("A", "B")
    ]
    monkeypatch.setattr(opening, "baseline_of", lambda ob: ob.baseline)
    prior = ControlFlow("BILLING", "US", "C@US", "invoice", date(2025, 6, 1), None, 150)
    correction = ControlFlow(
        "BILLING", "US", "C@US", "C@US@2025-12-31/opening_billed_cum", w.CUTOVER, None, 50
    )
    shares = {"C/A": (150, "prior-A"), "C/B": (0, "prior-B")}
    if issue == "missing":
        shares = {}
    elif issue == "raw_mismatch":
        shares = {"C/A": (75, "prior-A"), "C/B": (75, "prior-B")}
        own[1].opening["billed_cum"] = Decimal("2")
    book = NS(
        entity="US",
        txn="USD",
        mu_txn=2,
        billing_attribution={"invoice": shares},
        tb=TraceBuilder(engine_version=erev_engine.ENGINE_VERSION),
    )
    opening.bind(book, NS(obligations=own), (prior, correction))
    assert correction.source_key not in book.billing_attribution
    assert book.tb.build(root_measures={}).nodes == ()
