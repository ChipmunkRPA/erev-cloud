"""Contractor owes suppliers; the performer receives only the net commission."""

from dataclasses import replace
from decimal import Decimal

import pytest
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _Assembler

from erev_engine import compute
from erev_engine.bundle import FxRateInput, MappingRuleInput
from erev_engine.trace import reevaluate


def source(*, foreign=False):
    assembler = _Assembler(
        load(ANSWER_KEY_ROOT / "pob/POB-WM-05-HOTEL-MERCHANT-VERSUS-AGENCY.yaml")
    )
    value = next(
        b
        for b in assembler.checkpoints()[1].bundles
        if "WM-05-MERCHANT" in b.group.member_contract_keys
    )
    contractor = value.entities[0]
    performer = replace(contractor, code="PERFORMER")
    rates = []
    if foreign:
        contractor = replace(contractor, functional_currency="EUR")
        rates.append(
            FxRateInput(
                "advance",
                "1",
                "spot",
                "USD",
                "EUR",
                value.group.inception_date,
                None,
                Decimal(".9"),
            )
        )
        for p in contractor.periods:
            for kind in ("average", "closing"):
                rates.append(
                    FxRateInput(
                        f"{kind}-{p.period_key}",
                        "1",
                        kind,
                        "USD",
                        "EUR",
                        p.end_date,
                        p.period_key,
                        Decimal("1.2"),
                    )
                )
    books = []
    for book in value.books:
        policies = (
            *book.policies,
            *(
                replace(
                    p,
                    subject_key=p.subject_key.replace(
                        contractor.code + "@", performer.code + "@", 1
                    ),
                )
                for p in book.policies
                if p.scope == "PERIOD"
            ),
        )
        rules = (
            *book.account_mapping.rules,
            *(
                MappingRuleInput(role, None, None, None, None, None, role, {}, 0, 0)
                for role in ("INTERCOMPANY_DUE_TO", "INTERCOMPANY_DUE_FROM")
            ),
        )
        books.append(
            replace(
                book,
                entity_codes=tuple(sorted((contractor.code, performer.code))),
                policies=tuple(sorted(policies, key=lambda p: (p.code, p.scope, p.subject_key))),
                account_mapping=replace(
                    book.account_mapping,
                    rules=tuple(
                        sorted(
                            rules,
                            key=lambda r: (
                                r.account_role,
                                r.clearing_purpose or "",
                                r.account_code,
                            ),
                        )
                    ),
                ),
            )
        )
    return replace(
        value,
        evidence_revision=66,
        books=tuple(books),
        currencies=bundles.currencies("USD", "EUR"),
        entities=tuple(sorted((contractor, performer), key=lambda e: e.code)),
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
        events=tuple(
            replace(
                e,
                payload={
                    **e.payload,
                    "lines": [
                        {**line, "performing_entity_code": performer.code}
                        for line in e.payload["lines"]
                    ],
                },
            )
            if e.event_type == "CONTRACT_BOOKED"
            else e
            for e in value.events
        ),
    )


@pytest.mark.parametrize("foreign", [False, True])
def test_net_commission_and_supplier_payable_have_separate_owners(foreign):
    value = source(foreign=foreign)
    result = compute(value).books[0]
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    amounts = {}
    for entry in result.posting_intents:
        for line in entry.lines:
            key = (entry.entity, line.account_role, line.clearing_purpose)
            old = amounts.get(key, (0, 0))
            sign = 1 if line.side == "D" else -1
            amounts[key] = (old[0] + sign * line.amount_txn, old[1] + sign * line.amount_functional)
    contractor = next(e.code for e in value.entities if e.code != "PERFORMER")
    assert amounts[(contractor, "CONTRACT_LIABILITY", None)] == (
        12000000,
        10800000 if foreign else 12000000,
    )
    assert amounts[(contractor, "INTERCOMPANY_DUE_TO", None)] == (
        -1920000,
        -1728000 if foreign else -1920000,
    )
    assert amounts[(contractor, "BILLING_CLEARING", "AP_SUPPLIER")] == (
        -10080000,
        -9072000 if foreign else -10080000,
    )
    assert amounts[("PERFORMER", "INTERCOMPANY_DUE_FROM", None)] == (1920000, 1920000)
    assert amounts[("PERFORMER", "REVENUE", None)] == (-1920000, -1920000)
    assert all(key[0] == contractor for key in amounts if key[2] == "AP_SUPPLIER")
    row = next(r for r in result.balances if r.period_key == "FY2026-P03")
    assert row.columns["contract_liability_txn"] == 0
    assert compute(value) == compute(value)


def test_different_period_dates_cannot_shift_agent_income_to_a_later_period():
    from datetime import date

    from erev_engine.errors import EngineError

    value = source()
    value = replace(
        value,
        entities=tuple(
            replace(
                entity,
                periods=tuple(
                    replace(p, end_date=date(2026, 3, 30))
                    if p.period_key == "FY2026-P03"
                    else replace(p, start_date=date(2026, 3, 31))
                    if p.period_key == "FY2026-P04"
                    else p
                    for p in entity.periods
                ),
            )
            if entity.code == "PERFORMER"
            else entity
            for entity in value.entities
        ),
    )
    with pytest.raises(EngineError) as refused:
        compute(value)
    assert refused.value.detail["rule"] == "AGENT_IC_ALIGNED_CALENDARS"
