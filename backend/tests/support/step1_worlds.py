"""Worlds for the 606-10-25-7 deposit release, the STEP1_MET netting and the RPO exclusion
(ENGINE_SPEC S02-R-04, S02-R-07, S02-R-08 rev 1.6; ENGINE_SPEC_B S14-R-25, S15-R-08 to S15-R-12
rev 1.7; D-91 "Contract and obligation gaps" (ii) to (vii); BUILD_SPEC ENA-2b, END-4b).

One ASC606 book, one entity ``US01`` with monthly periods from January 2026, one contract booked
while collectibility is not probable (``NOT_A_CONTRACT``) with a reviewed ``NOT_A_CONTRACT``
judgement (``consideration_nonrefundable`` and, optionally, ``event_c_met_on``). The D-91 worlds:
T1 the completed time service (1,200.00, 1 January to 31 December 2026, 1,200.00 received on 15
February), T4 receipts completing after the term end, T5 goods plus a service, T8 a term ending
mid-month, T9 criteria met after a release, X4 an overpayment, FX2 the EUR deposit released while a
USD entity holds it (the FX-CHK-084-B rates). Every figure asserted against these worlds was derived
with Fraction arithmetic in ``.run/l9/d91-gaps-d1/derive.py`` before the tests were written.
Bundles come from ``support.bundles`` and ``support.cpc_worlds`` (DG-ENG-11); no database
(DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookOutput,
    ContractInput,
    EventInput,
    FxRateInput,
    InputBundle,
    JudgementInput,
    MappingRuleInput,
    ModificationInput,
    OutputBundle,
    ProductInput,
    SspVersionInput,
    TemplateInput,
)
from support import bundles, intent_totals
from support import cpc_worlds as cpc
from support.cpc_worlds import PIT, ZERO_SHA, line, product, ssp_book, template

__all__ = [
    "CONTRACT",
    "END",
    "ENTITY",
    "GOODS",
    "JAN",
    "PIT",
    "SERVICE",
    "SUBJECT",
    "TIME",
    "criteria_met",
    "delivered",
    "eur_deposit",
    "eur_mixed_rates",
    "fx_pass",
    "header",
    "invoiced",
    "journal",
    "mixed_world",
    "not_a_contract",
    "not_probable",
    "payment",
    "pit_world",
    "release_pass",
    "significant_change",
    "step1_events",
    "terminated",
    "termination",
    "time_template",
    "time_world",
    "world",
]

CONTRACT = "C-STEP1"
ENTITY = bundles.ENTITY_CODE
SUBJECT = f"{CONTRACT}@{ENTITY}"
JAN = date(2026, 1, 1)
END = date(2026, 12, 31)
FEB_15 = date(2026, 2, 15)
SERVICE = "L1-SVC"
GOODS = "L1-GOODS"
RATE_SET = "RATES@v1"
# The FX roles a foreign-currency deposit posts (JET-10d) beside the kernel and JET-14 accounts.
EXTRA_ACCOUNTS = (("FX_GAIN_LOSS", None, "7200"), ("ROUNDING", None, "7900"))


def time_template(code: str = "TPL-TIME", convention: str = "MONTHLY_EVEN") -> TemplateInput:
    """An ``OVER_TIME`` ``TIME_ELAPSED`` template with the ALG-11 convention pinned."""
    return template(
        code,
        "TIME_ELAPSED",
        satisfaction_pattern="OVER_TIME",
        over_time_criterion="OT_A",
        ratable_convention=convention,
    )


TIME = time_template()


def not_a_contract(
    *, nonrefundable: bool = True, met_on: date | None = None, book_code: str | None = None
) -> JudgementInput:
    """The reviewed ``NOT_A_CONTRACT`` record (Table 0.4-A; S02-R-07)."""
    outcome = {"consideration_nonrefundable": "true" if nonrefundable else "false"}
    if met_on is not None:
        outcome["event_c_met_on"] = met_on.isoformat()
    return JudgementInput("J-NAC", "NOT_A_CONTRACT", CONTRACT, book_code, outcome)


def header(
    *,
    nonrefundable: bool = True,
    met_on: date | None = None,
    judgements: Sequence[JudgementInput] = (),
    modifications: Sequence[ModificationInput] = (),
    currency: str = "USD",
    inception: date = JAN,
    termination_party: str | None = None,
) -> ContractInput:
    return dataclasses.replace(
        bundles.contract(CONTRACT, inception=inception, currency=currency),
        judgements=(not_a_contract(nonrefundable=nonrefundable, met_on=met_on), *judgements),
        modifications=tuple(modifications),
        termination_party=termination_party,
    )


def step1_events(
    lines: Sequence[Mapping[str, object]],
    *,
    paid: str | None = "1200.00",
    paid_on: date = FEB_15,
    inception: date = JAN,
) -> list[EventInput]:
    """Booking, the failed collectibility assessment, the activation and the first receipt."""
    keys = [str(item["obligation_key"]) for item in lines]
    events = [
        bundles.event(
            CONTRACT, 1, "CONTRACT_BOOKED", inception, {"lines": list(lines)}, obligation_keys=keys
        ),
        bundles.event(
            CONTRACT,
            2,
            "COLLECTIBILITY_ASSESSED",
            inception,
            {"book": "ASC606", "is_probable": False, "judgement_record_id": "J-2"},
        ),
        bundles.event(CONTRACT, 3, "CONTRACT_ACTIVATED", inception, {"checklist": {}}),
    ]
    if paid is not None:
        events = payment(events, paid_on, paid)
    return events


def payment(events: list[EventInput], on: date, amount: str) -> list[EventInput]:
    reference = f"R-{len(events) + 1}"
    payload = {"receipt_reference": reference, "amount": Decimal(amount), "receipt_date": on}
    return cpc.then(events, "PAYMENT_RECEIVED", on, payload)


def delivered(
    events: list[EventInput], on: date, key: str = GOODS, quantity: str = "1"
) -> list[EventInput]:
    return cpc.delivered(events, key, on, quantity)


def criteria_met(events: list[EventInput], on: date) -> list[EventInput]:
    payload = {"book": "ASC606", "judgement_record_id": f"J-{len(events) + 1}"}
    return cpc.then(events, "CONTRACT_CRITERIA_MET", on, payload)


def invoiced(
    events: list[EventInput], on: date, amount: str, key: str = SERVICE
) -> list[EventInput]:
    """A ``BILLING_RECORDED`` of ``amount`` on ``key`` (a warning while ``NOT_A_CONTRACT``)."""
    return cpc.invoiced(events, key, on, amount)


def significant_change(events: list[EventInput], on: date, description: str) -> list[EventInput]:
    """``SIGNIFICANT_CHANGE_FLAGGED`` (606-10-25-5): the next collectibility reassessment acts."""
    return cpc.then(events, "SIGNIFICANT_CHANGE_FLAGGED", on, {"description": description})


def not_probable(events: list[EventInput], on: date) -> list[EventInput]:
    """``COLLECTIBILITY_ASSESSED`` not probable in the ASC606 book (a Step 1 failure after a
    significant change, 606-10-25-5 and 25-6)."""
    payload = {
        "book": "ASC606",
        "is_probable": False,
        "judgement_record_id": f"J-{len(events) + 1}",
    }
    return cpc.then(events, "COLLECTIBILITY_ASSESSED", on, payload)


def termination(
    on: date, lines: Sequence[Mapping[str, object]], reference: str = "MOD-TERM"
) -> ModificationInput:
    """A FULL termination removing every line (S06-R-21 ``REMOVE`` lines with negative deltas)."""
    removed = tuple(
        {
            "obligation_key": item["obligation_key"],
            "action": "REMOVE",
            "product_code": item["product_code"],
            "quantity_delta": -Decimal(str(item["quantity"])),
            "consideration_delta": -Decimal(str(item["total_price"])),
        }
        for item in lines
    )
    return ModificationInput(
        modification_key=reference,
        effective_date=on,
        kind="TERMINATION",
        template_mode=None,
        status="APPROVED",
        reference=reference,
        questionnaire={},
        lines=removed,
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=ZERO_SHA,
    )


def terminated(
    events: list[EventInput], modification: ModificationInput, refund: str
) -> list[EventInput]:
    payload = {
        "modification_id": modification.modification_key,
        "termination_kind": "FULL",
        "refund_amount": Decimal(refund),
    }
    return cpc.then(
        events,
        "CONTRACT_TERMINATED",
        modification.effective_date,
        payload,
        modification_key=modification.modification_key,
    )


def _rates(currency: str, functional: str) -> tuple[FxRateInput, ...]:
    """The FX-CHK-084-B rates: spot 1.1000 on 10 January and 1.1300 on 15 February 2026; January
    closing 1.1200, February closing 1.1300; averages 1.1100 and 1.1250."""
    if currency == functional:
        return ()

    def rate(kind: str, on: date, period: str | None, value: str) -> FxRateInput:
        key = f"{currency}{functional}-{kind.upper()}-{period or on.isoformat()}"
        return FxRateInput(key, RATE_SET, kind, currency, functional, on, period, Decimal(value))

    rates = (
        rate("spot", date(2026, 1, 10), None, "1.1000"),
        rate("spot", date(2026, 2, 15), None, "1.1300"),
        rate("closing", date(2026, 1, 31), "FY2026-P01", "1.1200"),
        rate("closing", date(2026, 2, 28), "FY2026-P02", "1.1300"),
        rate("average", date(2026, 1, 31), "FY2026-P01", "1.1100"),
        rate("average", date(2026, 2, 28), "FY2026-P02", "1.1250"),
    )
    return tuple(sorted(rates, key=lambda item: item.rate_key))


def world(
    contract: ContractInput,
    events: Sequence[EventInput],
    *,
    products: Sequence[ProductInput],
    templates: Sequence[TemplateInput],
    ssp: Sequence[SspVersionInput],
    months: int = 12,
    states: Mapping[str, str] | None = None,
    policies: Mapping[str, str] | None = None,
    functional_currency: str = "USD",
    known_at: datetime | None = None,
    books: Sequence[str] = ("ASC606",),
    rates: Sequence[FxRateInput] | None = None,
) -> InputBundle:
    """One entity with monthly periods from January 2026 (``states`` names the E-04 state of a
    period, default open), the books named, the deposit accounts mapped, GROUP-scope ``policies``
    replaced per book, and the FX-CHK-084-B rates (or ``rates``) when the contract's currency is
    foreign."""
    currency = contract.transaction_currency
    calendar = bundles.entity(
        start=JAN,
        months=months,
        functional_currency=functional_currency,
        books=books,
        states=states,
    )
    book_inputs = []
    for code in books:
        base = bundles.book(code, entity=calendar)
        rows = tuple(
            dataclasses.replace(policy, value=(policies or {})[policy.code])
            if policy.code in (policies or {}) and policy.scope == "GROUP"
            else policy
            for policy in base.policies
        )
        mapping = base.account_mapping
        rules = tuple(
            sorted(
                (
                    *mapping.rules,
                    *(
                        MappingRuleInput(role, purpose, None, None, None, None, code, {}, 0, 0)
                        for role, purpose, code in (*cpc.CPC_ACCOUNTS, *EXTRA_ACCOUNTS)
                    ),
                ),
                key=lambda rule: (
                    rule.account_role,
                    rule.clearing_purpose or "",
                    rule.account_code,
                ),
            )
        )
        book_inputs.append(
            dataclasses.replace(
                base, policies=rows, account_mapping=dataclasses.replace(mapping, rules=rules)
            )
        )
    last = max(event.effective_date for event in events)
    codes = sorted({currency, functional_currency})
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=known_at or datetime(last.year, last.month, last.day, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies(*codes),
        books=tuple(book_inputs),
        entities=(calendar,),
        group=bundles.group((contract,), products=tuple(products)),
        contracts=(contract,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=tuple(ssp),
        pob_template_versions=tuple(sorted(templates, key=lambda t: t.template_code)),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(
            _rates(currency, functional_currency)
            if rates is None
            else tuple(sorted(rates, key=lambda item: item.rate_key))
        ),
        posted=(),
    )


def time_world(
    *,
    end: date = END,
    paid: str | None = "1200.00",
    price: str = "1200.00",
    extra: Sequence[EventInput] | None = None,
    steps: Sequence[tuple[str, date, str]] = (),
    nonrefundable: bool = True,
    met_on: date | None = None,
    convention: str = "MONTHLY_EVEN",
    months: int = 12,
    states: Mapping[str, str] | None = None,
    known_at: datetime | None = None,
    judgements: Sequence[JudgementInput] = (),
    policies: Mapping[str, str] | None = None,
    template_changes: Mapping[str, object] | None = None,
    termination_party: str | None = None,
    books: Sequence[str] = ("ASC606",),
    inception: date = JAN,
    paid_on: date = FEB_15,
) -> InputBundle:
    """T1: a 1,200.00 ``TIME_ELAPSED`` service from ``inception`` (1 January) to ``end``, received
    in full on ``paid_on`` (15 February) while ``NOT_A_CONTRACT``. ``steps``: ``("P", date,
    amount)`` a receipt, ``("C", date, "")`` the criteria met, ``("T", date, refund)`` a FULL
    termination, ``("I", date, amount)`` an invoice, ``("S", date, description)`` a significant
    change flagged, ``("N", date, "")`` collectibility reassessed not probable. Same-day steps
    keep their listed order."""
    lines = [line(SERVICE, "SERVICE", "1", price, start=inception, end=end)]
    events = step1_events(lines, paid=paid, paid_on=paid_on, inception=inception)
    modifications: list[ModificationInput] = []
    for kind, on, amount in steps:
        if kind == "P":
            events = payment(events, on, amount)
        elif kind == "C":
            events = criteria_met(events, on)
        elif kind == "T":
            modification = termination(on, lines)
            modifications.append(modification)
            events = terminated(events, modification, amount)
        elif kind == "I":
            events = invoiced(events, on, amount)
        elif kind == "S":
            events = significant_change(events, on, amount)
        elif kind == "N":
            events = not_probable(events, on)
        else:
            raise ValueError(kind)
    events = [*events, *(extra or ())]
    changes = dict(template_changes or {})
    tpl = (
        time_template(convention=convention)
        if not changes
        else dataclasses.replace(time_template(convention=convention), **changes)  # type: ignore[arg-type]
    )
    return world(
        header(
            nonrefundable=nonrefundable,
            met_on=met_on,
            judgements=judgements,
            modifications=modifications,
            termination_party=termination_party,
            inception=inception,
        ),
        events,
        products=[product("SERVICE", "TPL-TIME")],
        templates=[tpl],
        ssp=[ssp_book({"SERVICE": price.split(".")[0]})],
        months=months,
        states=states,
        # POL-090: the resolved convention governs a TIME_ELAPSED obligation (S03-R-17).
        policies={"recognition.time_convention": convention, **(policies or {})},
        known_at=known_at,
        books=books,
    )


def pit_world(
    *,
    paid: str | None = "1200.00",
    price: str = "1200.00",
    delivery: date | None = END,
    steps: Sequence[tuple[str, date, str]] = (),
    nonrefundable: bool = True,
    met_on: date | None = None,
    months: int = 12,
    states: Mapping[str, str] | None = None,
    known_at: datetime | None = None,
    quantity: str = "1",
) -> InputBundle:
    """T6b / T9: point-in-time goods of 1,200.00 (``quantity`` units) booked while
    ``NOT_A_CONTRACT``, received on 15 February and delivered in full on ``delivery``; ``steps`` as
    ``time_world`` plus ``("D", date, quantity)`` a partial delivery."""
    lines = [line(GOODS, "GOODS", quantity, price)]
    events = step1_events(lines, paid=paid)
    modifications: list[ModificationInput] = []
    if delivery is not None:
        events = delivered(events, delivery, quantity=quantity)
    for kind, on, amount in steps:
        if kind == "P":
            events = payment(events, on, amount)
        elif kind == "C":
            events = criteria_met(events, on)
        elif kind == "T":
            modification = termination(on, lines)
            modifications.append(modification)
            events = terminated(events, modification, amount)
        elif kind == "D":
            events = delivered(events, on, quantity=amount)
        elif kind == "I":
            events = invoiced(events, on, amount, GOODS)
        elif kind == "S":
            events = significant_change(events, on, amount)
        elif kind == "N":
            events = not_probable(events, on)
        else:
            raise ValueError(kind)
    return world(
        header(nonrefundable=nonrefundable, met_on=met_on, modifications=modifications),
        events,
        products=[product("GOODS", "TPL-PIT")],
        templates=[PIT],
        ssp=[ssp_book({"GOODS": price.split(".")[0]})],
        months=months,
        states=states,
        known_at=known_at,
    )


def mixed_world(
    *,
    delivery: date | None = date(2026, 12, 15),
    months: int = 12,
    steps: Sequence[tuple[str, date, str]] = (),
    service_end: date = END,
    met_on: date | None = None,
) -> InputBundle:
    """T5: goods 800.00 (SSP 800) delivered on ``delivery`` and a service 400.00 (SSP 400) from
    1 January to ``service_end``; 1,200.00 received on 15 February while ``NOT_A_CONTRACT``;
    ``steps`` as ``time_world`` (receipts and the criteria met); ``met_on`` the 25-7(c) point."""
    lines = [
        line(GOODS, "GOODS", "1", "800.00"),
        line(SERVICE, "SERVICE", "1", "400.00", start=JAN, end=service_end),
    ]
    events = step1_events(lines)
    if delivery is not None:
        events = delivered(events, delivery)
    for kind, on, amount in steps:
        if kind == "P":
            events = payment(events, on, amount)
        elif kind == "C":
            events = criteria_met(events, on)
        else:
            raise ValueError(kind)
    return world(
        header(met_on=met_on),
        events,
        products=[product("GOODS", "TPL-PIT"), product("SERVICE", "TPL-TIME")],
        templates=[PIT, TIME],
        ssp=[ssp_book({"GOODS": "800", "SERVICE": "400"})],
        months=months,
        policies={"recognition.time_convention": "MONTHLY_EVEN"},
    )


def eur_deposit(
    *, met_on: date | None = date(2026, 2, 15), delivery: date | None = None
) -> InputBundle:
    """FX2: a EUR contract of a USD entity (FX-CHK-084-B rates): two goods L1 2,000.00 (SSP 2,000)
    and L2 1,000.00 (SSP 1,000), EUR 1,000.00 received on 10 January while ``NOT_A_CONTRACT``, and
    the 25-7(c) point ``event_c_met_on`` 15 February (or a delivery of both goods on that date)."""
    lines = [line("L1", "G1", "1", "2000.00"), line("L2", "G2", "1", "1000.00")]
    events = step1_events(
        lines, paid="1000.00", paid_on=date(2026, 1, 10), inception=date(2026, 1, 5)
    )
    if delivery is not None:
        events = delivered(events, delivery, "L1")
        events = delivered(events, delivery, "L2")
    return world(
        header(met_on=met_on, currency="EUR", inception=date(2026, 1, 5)),
        events,
        products=[product("G1", "TPL-PIT"), product("G2", "TPL-PIT")],
        templates=[PIT],
        ssp=[ssp_book({"G1": "2000", "G2": "1000"}, "EUR")],
        months=2,
        functional_currency="USD",
    )


def eur_mixed_rates(
    *,
    two_obligations: bool = False,
    second_on: date = date(2026, 1, 20),
    states: Mapping[str, str] | None = None,
) -> InputBundle:
    """D1-R04: a EUR good of 1,200.00 (SSP 1,200) of a USD entity, booked 5 January while
    ``NOT_A_CONTRACT``; EUR 600.00 received 10 January at spot 1.1000, the 25-7(c) point
    ``event_c_met_on`` 12 January (a dated TIME release at spot 1.1000), EUR 600.00 received on
    ``second_on`` (20 January) at spot 1.2000 (an EVENT release at 1.2000); January closing
    1.1200. ``two_obligations``: goods L1 800.00 (SSP 800) and L2 400.00 (SSP 400) instead, the
    posted inception weights 2 : 1 (the secondary review's multi-period control)."""
    if two_obligations:
        lines = [line("L1", "G1", "1", "800.00"), line("L2", "G2", "1", "400.00")]
        products = [product("G1", "TPL-PIT"), product("G2", "TPL-PIT")]
        ssp = ssp_book({"G1": "800", "G2": "400"}, "EUR")
    else:
        lines = [line("L1", "G1", "1", "1200.00")]
        products = [product("G1", "TPL-PIT")]
        ssp = ssp_book({"G1": "1200"}, "EUR")
    events = step1_events(
        lines, paid="600.00", paid_on=date(2026, 1, 10), inception=date(2026, 1, 5)
    )
    events = payment(events, second_on, "600.00")

    def rate(kind: str, on: date, period: str | None, value: str) -> FxRateInput:
        key = f"EURUSD-{kind.upper()}-{period or on.isoformat()}"
        return FxRateInput(key, RATE_SET, kind, "EUR", "USD", on, period, Decimal(value))

    return world(
        header(met_on=date(2026, 1, 12), currency="EUR", inception=date(2026, 1, 5)),
        events,
        products=products,
        templates=[PIT],
        ssp=[ssp],
        months=2,
        states=states,
        functional_currency="USD",
        rates=(
            rate("spot", date(2026, 1, 10), None, "1.1000"),
            rate("spot", second_on, None, "1.2000"),
            rate("closing", date(2026, 1, 31), "FY2026-P01", "1.1200"),
            rate("closing", date(2026, 2, 28), "FY2026-P02", "1.1300"),
            rate("average", date(2026, 1, 31), "FY2026-P01", "1.1100"),
            rate("average", date(2026, 2, 28), "FY2026-P02", "1.1250"),
        ),
    )


# --- observation ----------------------------------------------------------------------------------


def release_pass(bundle: InputBundle, *prior: OutputBundle) -> BookOutput:
    """The ``CLOSE_RELEASE`` pass over ``bundle`` with ``prior`` posted (RCP-08(b)); one book."""
    output = intent_totals.close_pass(bundle, list(prior), "CLOSE_RELEASE")
    (book,) = output.books
    return book


def fx_pass(bundle: InputBundle, *prior: OutputBundle) -> BookOutput:
    output = intent_totals.close_pass(bundle, list(prior), "FX_REMEASUREMENT")
    (book,) = output.books
    return book


def journal(
    book: BookOutput, *roles: str
) -> list[tuple[str, str, str, str, str, int, int, str | None]]:
    """(posting period, entry kind, class, role, side, txn, functional, origin) of the lines of
    ``roles`` (every role when none is named), sorted."""
    return sorted(
        (
            intent.posting_period_key,
            intent.entry_kind,
            intent.posting_class,
            item.account_role,
            item.side,
            item.amount_txn,
            item.amount_functional,
            intent.origin_period_key,
        )
        for intent in book.posting_intents
        for item in intent.lines
        if not roles or item.account_role in roles
    )
