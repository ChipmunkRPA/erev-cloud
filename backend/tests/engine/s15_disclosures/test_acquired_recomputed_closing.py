"""Recomputed acquisition eligibility reads original cumulative targets, not ERP imports."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support import onboarding_worlds as w

import erev_engine


@pytest.mark.parametrize("engine_invoice", [False, True])
@pytest.mark.parametrize("imported", ["100000", "120000", "140000"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_POB", "FIFO_WITHIN_CONTRACT"])
def test_recomputed_acquisition_uses_native_revenue_and_preserves_journals(
    imported, consumption, engine_invoice
):
    value = w.chk_121(
        as_of=date(2026, 1, 31),
        states={"FY2025-P12": "open"},
        payload=w.opening_payload(
            revenue_cum=imported,
            remaining_allocation=str(Decimal("240000") - Decimal(imported)),
        ),
        extra=[
            bundles.event(
                w.CONTRACT,
                5,
                "BILLING_RECORDED",
                date(2026, 1, 31),
                {
                    "invoice_number": "POST-ACQ",
                    "line_external_id": "POST-ACQ-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("100"),
                    "issue_date": date(2026, 1, 31),
                },
                obligation_keys=[w.OBLIGATION],
            ),
        ],
        policies={
            "onboarding.method": "RECOMPUTE_FROM_INCEPTION",
            "billing.posting": "ENGINE" if engine_invoice else "ERP",
            "rollforward.opening_liability_consumption": consumption,
        },
    )
    if engine_invoice:
        invoice = bundles.event(
            w.CONTRACT,
            4,
            "BILLING_RECORDED",
            date(2025, 6, 1),
            {
                "invoice_number": "ORIGINAL",
                "line_external_id": "ORIGINAL-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("200000"),
                "issue_date": date(2025, 6, 1),
            },
            obligation_keys=[w.OBLIGATION],
        )
        value = replace(
            value,
            events=tuple(
                sorted(
                    (*value.events, invoice),
                    key=lambda e: (e.effective_date, e.record_seq, e.event_key),
                )
            ),
        )
    previous = erev_engine.compute(replace(value, evidence_revision=13))
    current = erev_engine.compute(replace(value, evidence_revision=38))
    for old, book in zip(previous.books, current.books, strict=True):
        assert book.posting_intents == old.posting_intents
        for row in book.disclosure_rollforwards:
            assert row.obligation_closing["status"] == "AVAILABLE"
            item = row.obligation_closing["obligations"][w.SUBJECT]
            expected = (
                (20010000 if engine_invoice else 24010000, 13000000)
                if book.book_code == "ASC606"
                else (9010000, 750000)
            )
            assert (item["billed"], item["revenue"]) == expected
            assert item["liability"] == expected[0] - expected[1]
            assert row.lines["CONTRACT_LIABILITY"]["CLOSING"] == item["liability"]
            assert row.lines["CONTRACT_LIABILITY"]["REVENUE_FROM_OTHER_INCREASES"] == 0
            assert row.lines["CONTRACT_LIABILITY"]["OTHER"] == 0
            if book.book_code == "ASC606":
                nodes = {n.id for n in book.trace.nodes}
                assert set(item["sources"]) <= nodes
                assert any(s.startswith("billed_cum:") for s in item["sources"])
                assert any(s.startswith("revenue_cum:") for s in item["sources"])


def test_closed_recomputed_cutover_does_not_substitute_imported_balances():
    value = w.chk_121(
        as_of=date(2025, 12, 31),
        policies={"onboarding.method": "RECOMPUTE_FROM_INCEPTION"},
    )
    output = erev_engine.compute(replace(value, evidence_revision=38))
    asc = next(b for b in output.books if b.book_code == "ASC606")
    assert all(r.obligation_closing["status"] == "UNAVAILABLE" for r in asc.disclosure_rollforwards)


@pytest.mark.parametrize("imported", ["100000", "140000"])
def test_recomputed_cutover_caption_uses_actual_target_without_unexplained_other(imported):
    value = w.chk_121(
        as_of=date(2025, 12, 31),
        states={"FY2025-P12": "open"},
        payload=w.opening_payload(
            revenue_cum=imported,
            remaining_allocation=str(Decimal("240000") - Decimal(imported)),
        ),
        policies={"onboarding.method": "RECOMPUTE_FROM_INCEPTION"},
    )
    before = erev_engine.compute(replace(value, evidence_revision=38))
    after = erev_engine.compute(replace(value, evidence_revision=39))
    for old, book in zip(before.books, after.books, strict=True):
        assert old.posting_intents == book.posting_intents
        for row in book.disclosure_rollforwards:
            lines = row.lines["CONTRACT_LIABILITY"]
            assert lines["BUSINESS_COMBINATIONS"] == lines["CLOSING"]
            assert lines["OTHER"] == 0
            assert lines["BUSINESS_COMBINATIONS"] == (
                12000000 if book.book_code == "ASC606" else 9000000
            )


@pytest.mark.parametrize("units", [False, True])
@pytest.mark.parametrize("engine_invoice", [False, True])
def test_closed_cutover_retains_original_calculation_without_new_posting_targets(
    units, engine_invoice
):
    from support.cpc_worlds import template

    events = []
    if units:
        events.append(
            bundles.event(
                w.CONTRACT,
                4,
                "DELIVERY_RECORDED",
                date(2025, 12, 15),
                {"obligation_key": w.OBLIGATION, "quantity": Decimal("0.5"), "trigger": "DELIVERY"},
                obligation_keys=[w.OBLIGATION],
            )
        )
    if engine_invoice:
        events.append(
            bundles.event(
                w.CONTRACT,
                5,
                "BILLING_RECORDED",
                date(2025, 6, 1),
                {
                    "invoice_number": "ORIGINAL",
                    "line_external_id": "ORIGINAL-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("200000"),
                    "issue_date": date(2025, 6, 1),
                },
                obligation_keys=[w.OBLIGATION],
            )
        )
    value = w.chk_121(
        as_of=w.CUTOVER,
        extra=events,
        payload=w.opening_payload(revenue_cum="100000", remaining_allocation="140000"),
        policies={
            "onboarding.method": "RECOMPUTE_FROM_INCEPTION",
            "billing.posting": "ENGINE" if engine_invoice else "ERP",
        },
    )
    if units:
        value = replace(value, pob_template_versions=(template("TPL-RATABLE", "UNITS_DELIVERED"),))
    before = erev_engine.compute(replace(value, evidence_revision=39))
    after = erev_engine.compute(replace(value, evidence_revision=40))
    for old, book in zip(before.books, after.books, strict=True):
        assert book.posting_intents == old.posting_intents == ()
        assert book.schedules == old.schedules
        assert book.balances == old.balances
        assert book.obligation_versions == old.obligation_versions
        for row in book.disclosure_rollforwards:
            assert row.obligation_closing["status"] == "AVAILABLE"
            item = row.obligation_closing["obligations"][w.SUBJECT]
            billed = (
                (20000000 if engine_invoice else 24000000)
                if book.book_code == "ASC606"
                else 9000000
            )
            revenue = 12000000 if book.book_code == "ASC606" else 0
            assert (item["billed"], item["revenue"]) == (billed, revenue)
            assert item["liability"] == billed - revenue
            assert set(item["sources"]) <= {n.id for n in book.trace.nodes}
            lines = row.lines["CONTRACT_LIABILITY"]
            assert lines["BUSINESS_COMBINATIONS"] == lines["CLOSING"] == item["liability"]
            assert lines["OTHER"] == 0


def test_closed_recomputed_asset_requires_original_right_class():
    from erev_engine.errors import EngineError

    invoice = bundles.event(
        w.CONTRACT,
        4,
        "BILLING_RECORDED",
        date(2025, 6, 1),
        {
            "invoice_number": "LOW-BILL",
            "line_external_id": "LOW-BILL-1",
            "obligation_key": w.OBLIGATION,
            "amount": Decimal("100000"),
            "issue_date": date(2025, 6, 1),
        },
        obligation_keys=[w.OBLIGATION],
    )
    value = w.chk_121(
        as_of=w.CUTOVER,
        extra=[invoice],
        policies={"onboarding.method": "RECOMPUTE_FROM_INCEPTION", "billing.posting": "ENGINE"},
    )
    # Imported balances show a liability; actual recomputed billing yields an asset.
    # Missing original classification cannot silently label it a contract asset.
    with pytest.raises(EngineError, match="asset classification"):
        erev_engine.compute(replace(value, evidence_revision=40))


@pytest.mark.parametrize("right", ["CONDITIONAL", "UNCONDITIONAL"])
def test_closed_recomputed_asset_keeps_original_class_without_posting(right):
    from erev_engine.bundle import ResolvedPolicyInput

    invoice = bundles.event(
        w.CONTRACT,
        4,
        "BILLING_RECORDED",
        date(2025, 6, 1),
        {
            "invoice_number": "LOW-BILL",
            "line_external_id": "LOW-BILL-1",
            "obligation_key": w.OBLIGATION,
            "amount": Decimal("100000"),
            "issue_date": date(2025, 6, 1),
        },
        obligation_keys=[w.OBLIGATION],
    )
    value = w.chk_121(
        as_of=w.CUTOVER,
        extra=[invoice],
        books=("ASC606",),
        policies={"onboarding.method": "RECOMPUTE_FROM_INCEPTION", "billing.posting": "ENGINE"},
    )
    if right == "UNCONDITIONAL":
        book = value.books[0]
        override = ResolvedPolicyInput(
            "balance.right_to_consideration",
            "CONTRACT",
            w.CONTRACT,
            right,
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
    old = erev_engine.compute(replace(value, evidence_revision=39)).books[0]
    current = erev_engine.compute(replace(value, evidence_revision=41)).books[0]
    assert current.posting_intents == old.posting_intents == ()
    assert current.balances == old.balances
    assert current.schedules == old.schedules
    assert current.obligation_versions == old.obligation_versions
    role = "CONTRACT_ASSET" if right == "CONDITIONAL" else "UNBILLED_RECEIVABLE"
    other = "UNBILLED_RECEIVABLE" if right == "CONDITIONAL" else "CONTRACT_ASSET"
    for row in current.disclosure_rollforwards:
        item = row.obligation_closing["obligations"][w.SUBJECT]
        assert item["right_class"] == right
        assert item["right_class_rule"] == "S10-R-21"
        assert (item["billed"], item["revenue"], item["liability"]) == (10000000, 12000000, 0)
        assert row.lines[role]["BUSINESS_COMBINATIONS"] == row.lines[role]["CLOSING"] == 2000000
        assert row.lines[other]["CLOSING"] == row.lines["CONTRACT_LIABILITY"]["CLOSING"] == 0
        assert all(lines["OTHER"] == 0 for lines in row.lines.values())
