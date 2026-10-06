"""Stage 02 contract identification rules (ENGINE_SPEC §2.2, §2.3, §2.5; BUILD_SPEC ENA-2).

Bundles come from ``support.bundles`` (DG-ENG-11); no database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import BookInput, ContractInput, EventInput, InputBundle, JudgementInput
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages import s01_canonicalize, s02_contract_identification
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.state import BookContext, PolicyResolver
from erev_engine.trace import SourceRef, TraceBuilder, TraceNode
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
LINE_END = date(2026, 12, 31)
SUBJECT = "K-01@US01"


def booking(
    contract: str = CONTRACT, *, price: str = "1200.00", end: date = LINE_END
) -> EventInput:
    line = bundles.booking_line("POB-01", quantity="1", total_price=price, start=INCEPTION, end=end)
    return bundles.event(
        contract, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["POB-01"]
    )


def event(
    stream: int,
    event_type: str,
    on: date,
    payload: Mapping[str, object],
    *,
    contract: str = CONTRACT,
) -> EventInput:
    obligation = payload.get("obligation_key")
    keys = [obligation] if isinstance(obligation, str) else []
    return bundles.event(contract, stream, event_type, on, payload, obligation_keys=keys)


def collectibility(stream: int, on: date, *, probable: bool, book: str = "ASC606") -> EventInput:
    payload = {"book": book, "is_probable": probable, "judgement_record_id": f"J-{stream}"}
    return event(stream, "COLLECTIBILITY_ASSESSED", on, payload)


def activated(stream: int, on: date = INCEPTION, *, contract: str = CONTRACT) -> EventInput:
    return event(stream, "CONTRACT_ACTIVATED", on, {"checklist": {}}, contract=contract)


def payment(stream: int, on: date, amount: str) -> EventInput:
    payload = {"receipt_reference": f"R-{stream}", "amount": Decimal(amount), "receipt_date": on}
    return event(stream, "PAYMENT_RECEIVED", on, payload)


def criteria_met(stream: int, on: date, *, book: str = "ASC606") -> EventInput:
    payload = {"book": book, "judgement_record_id": f"J-{stream}"}
    return event(stream, "CONTRACT_CRITERIA_MET", on, payload)


def judgement(topic: str, outcome: Mapping[str, str], *, key: str = "J-01") -> JudgementInput:
    return JudgementInput(key, topic, CONTRACT, None, outcome)


def header(**changes: object) -> ContractInput:
    return dataclasses.replace(bundles.contract(CONTRACT, inception=INCEPTION), **changes)


def with_policies(book: BookInput, overrides: Mapping[str, str]) -> BookInput:
    policies = tuple(
        dataclasses.replace(policy, value=overrides[policy.code])
        if policy.code in overrides and policy.scope == "GROUP"
        else policy
        for policy in book.policies
    )
    return dataclasses.replace(book, policies=policies)


def bundle(
    *events: EventInput,
    contracts: Iterable[ContractInput] | None = None,
    books: tuple[str, ...] = ("ASC606",),
    preset: str = "DEFAULT",
    policies: Mapping[str, str] | None = None,
    known_at: datetime = datetime(2026, 12, 31, 23, tzinfo=UTC),
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24, books=books)
    headers = tuple(contracts or (header(),))
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=known_at,
        tenant_preset=preset,
        currencies=bundles.currencies("USD"),
        books=tuple(
            with_policies(bundles.book(code, preset=preset, entity=calendar), policies or {})
            for code in books
        ),
        entities=(calendar,),
        group=bundles.group(headers, products=(bundles.product(),)),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def context(value: InputBundle, book_code: str = "ASC606") -> BookContext:
    book = next(b for b in value.books if b.book_code == book_code)
    horizon = {}
    for entity in value.entities:
        postable = [
            p for p in entity.periods if dates.period_state(p, book_code) in dates.POSTABLE_STATES
        ]
        if postable:
            horizon[entity.code] = postable[-1].period_key
    return BookContext(
        book_code=BookCode(book_code),
        framework=BookCode(book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon=horizon,
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def fold(
    value: InputBundle, book_code: str = "ASC606"
) -> tuple[IdentifiedState, dict[str, TraceNode]]:
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    st = s02_contract_identification.run(context(value, book_code), cb, tb)
    return st, {node.id: node for node in tb.build(root_measures={}).nodes}


def statuses(st: IdentifiedState, contract: str = CONTRACT) -> list[tuple[str, str, str | None]]:
    return [(s.status, s.reason, s.transition) for s in st.timelines[contract]]


def test_s02_r01_gate_per_book() -> None:
    books = ("ASC606", "IFRS15")
    value = bundle(
        booking(),
        collectibility(2, INCEPTION, probable=False, book="IFRS15"),
        activated(3),
        books=books,
    )
    asc, _ = fold(value, "ASC606")
    ifrs, _ = fold(value, "IFRS15")
    assert statuses(asc)[-1] == ("ACTIVE", "ACTIVATED", None)
    assert statuses(ifrs)[-1] == ("NOT_A_CONTRACT", "NOT_PROBABLE", None)
    assert ifrs.contracts[0].status_in_book == {
        "IFRS15": ((INCEPTION, "DRAFT"), (INCEPTION, "NOT_A_CONTRACT"))
    }
    with pytest.raises(ValueError, match="book is required"):
        fold(
            bundle(
                booking(), event(2, "COLLECTIBILITY_ASSESSED", INCEPTION, {"is_probable": False})
            )
        )


def test_s02_r02_draft_status_recorded() -> None:
    value = bundle(booking(), books=("ASC606", "IFRS15"))
    for book_code in ("ASC606", "IFRS15"):
        st, nodes = fold(value, book_code)
        assert statuses(st) == [("DRAFT", "BOOKED", None)]
        assert st.contracts[0].status_in_book == {book_code: ((INCEPTION, "DRAFT"),)}
        assert st.status_at(CONTRACT, date(2026, 6, 30)).status == "DRAFT"
        assert not any(node_id.startswith("status@") for node_id in nodes)


def test_s02_r06_enforceable_term() -> None:
    outcome = {
        "enforceable_end_date": "2026-01-31",
        "termination_penalty_substantive": "false",
        "enforceable_consideration[POB-01]": "100.00",
    }
    terminable = header(
        termination_party="CUSTOMER",
        termination_has_penalty=False,
        termination_notice_days=30,
        judgements=(judgement("CONTRACT_TERM", outcome),),
    )
    st, nodes = fold(bundle(booking(), contracts=[terminable]))
    node = nodes["enforceable_end_date:K-01:-"]
    assert (node.params["basis"], node.params["date"]) == ("JUDGEMENT", "2026-01-31")
    assert node.value == str(date(2026, 1, 31).toordinal())
    assert node.formula_id == "step1.enforceable_term.v1"
    assert st.terms[CONTRACT].truncated_lines == (("POB-01", date(2026, 1, 31), Fraction(100)),)

    pending = dataclasses.replace(terminable, judgements=())
    st, nodes = fold(bundle(booking(), contracts=[pending]))
    assert (st.terms[CONTRACT].basis, st.terms[CONTRACT].end_date) == (
        "STATED_TERM_PENDING_JUDGEMENT",
        LINE_END,
    )
    assert st.terms[CONTRACT].truncated_lines == ()
    substantive = dataclasses.replace(
        terminable,
        judgements=(judgement("CONTRACT_TERM", {"termination_penalty_substantive": "true"}),),
    )
    for contract, preset in ((substantive, "DEFAULT"), (terminable, "LEGACY_PARITY")):
        st, nodes = fold(bundle(booking(), contracts=[contract], preset=preset))
        assert nodes["enforceable_end_date:K-01:-"].params["basis"] == "STATED_TERM"
        assert st.terms[CONTRACT].end_date == LINE_END
    entity_only = dataclasses.replace(terminable, termination_party="ENTITY")
    st, _ = fold(bundle(booking(), contracts=[entity_only]))
    assert st.terms[CONTRACT].basis == "STATED_TERM"


def test_s02_r07_event_25_7() -> None:
    nonrefundable = header(
        judgements=(judgement("NOT_A_CONTRACT", {"consideration_nonrefundable": "true"}),)
    )
    events = (
        booking(),
        collectibility(2, INCEPTION, probable=False),
        activated(3),
        payment(4, date(2026, 2, 15), "1200.00"),
        event(
            5,
            "DELIVERY_RECORDED",
            date(2026, 3, 1),
            {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "DELIVERY"},
        ),
    )
    st, nodes = fold(bundle(*events, contracts=[nonrefundable]))
    assert [(r.reason, r.effective_date, r.event_key, r.amount) for r in st.recognitions] == [
        ("EVENT_25_7_A", date(2026, 3, 1), "K-01/EV-000005", Fraction(1200))
    ]
    recognition = st.recognitions[0]
    assert recognition.node_id == "deposit_to_revenue@K-01/EV-000005:K-01@US01:-"
    node = nodes[recognition.node_id]
    assert (node.value, node.formula_id, node.params["reason"]) == (
        "1200.00",
        "step1.event_25_7.v1",
        "EVENT_25_7_A",
    )
    assert statuses(st)[-1] == ("NOT_A_CONTRACT", "NOT_PROBABLE", None)
    assert st.deposit_at(CONTRACT).liability == 0
    targets = {(t.measure, t.period_key): t for t in st.deposit_targets}
    assert targets[("deposit_liability", "FY2026-P02")].value == 120000
    revenue = targets[("deposit_to_revenue_cum", "FY2026-P03")]
    assert (revenue.value, revenue.cause) == (120000, "EVENT_25_7_A")
    assert targets[("deposit_liability", "FY2026-P03")].value == 0

    refundable, _ = fold(bundle(*events))
    assert refundable.recognitions == ()
    assert refundable.deposit_at(CONTRACT).liability == 1200


def test_s02_r07_events_b_and_c() -> None:
    nonrefundable = judgement("NOT_A_CONTRACT", {"consideration_nonrefundable": "true"})
    terminated = event(
        5,
        "CONTRACT_TERMINATED",
        date(2026, 4, 1),
        {
            "modification_id": "MOD-1",
            "termination_kind": "FULL",
            "refund_amount": Decimal("200.00"),
        },
    )
    base = (booking(), collectibility(2, INCEPTION, probable=False), activated(3))
    st, _ = fold(
        bundle(
            *base,
            payment(4, date(2026, 2, 15), "1200.00"),
            terminated,
            contracts=[header(judgements=(nonrefundable,))],
        )
    )
    assert statuses(st)[-1] == ("TERMINATED", "EVENT_25_7_B", None)
    assert [(r.reason, r.amount) for r in st.recognitions] == [("EVENT_25_7_B", Fraction(1000))]
    final = st.deposit_at(CONTRACT)
    assert (final.refunded_cum, final.to_revenue_cum, final.liability) == (200, 1000, 0)

    met_on = judgement(
        "NOT_A_CONTRACT", {"consideration_nonrefundable": "true", "event_c_met_on": "2026-03-31"}
    )
    events_c = (
        *base,
        # Assessed for IFRS15 before the activation too (record_seq 2).
        dataclasses.replace(
            collectibility(4, INCEPTION, probable=False, book="IFRS15"), record_seq=2
        ),
        payment(5, date(2026, 2, 15), "500.00"),
        payment(6, date(2026, 4, 15), "300.00"),
    )
    value = bundle(*events_c, contracts=[header(judgements=(met_on,))], books=("ASC606", "IFRS15"))
    st, nodes = fold(value, "ASC606")
    assert [(r.reason, r.effective_date, r.event_key, r.amount) for r in st.recognitions] == [
        ("EVENT_25_7_C", date(2026, 3, 31), None, Fraction(500)),
        ("EVENT_25_7_C", date(2026, 4, 15), "K-01/EV-000006", Fraction(300)),
    ]
    assert nodes["deposit_to_revenue@2026-03-31:K-01@US01:-"].value == "500.00"
    assert st.deposit_at(CONTRACT, on=date(2026, 3, 30)).liability == 500
    ifrs, _ = fold(value, "IFRS15")  # POL-012 DISABLED in the IFRS15 book (IFRS 15.15)
    assert ifrs.recognitions == () and ifrs.deposit_at(CONTRACT).liability == 800


def test_s02_r10_single_currency() -> None:
    euro = header(transaction_currency="EUR")
    value = bundle(booking(), contracts=[euro])
    usd = dataclasses.replace(
        value, group=dataclasses.replace(value.group, transaction_currency="USD")
    )
    with pytest.raises(EngineError) as raised:
        fold(usd)
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["invariant"] == "S02-INV-04"


def test_s02_r11_invoice_on_not_a_contract() -> None:
    billing = event(
        4,
        "BILLING_RECORDED",
        date(2026, 2, 1),
        {
            "invoice_number": "INV-1",
            "line_external_id": "1",
            "amount": Decimal("100.00"),
            "issue_date": date(2026, 2, 1),
        },
    )
    base = (booking(), collectibility(2, INCEPTION, probable=False), activated(3), billing)
    st, _ = fold(bundle(*base))
    assert [(f.code, f.severity, f.subject_key, f.event_key, f.stage) for f in st.findings] == [
        ("INVOICE_ON_NOT_A_CONTRACT", "WARNING", CONTRACT, "K-01/EV-000004", 2)
    ]
    assert st.deferred_invoices == {"K-01/EV-000004": None}
    met, _ = fold(bundle(*base, criteria_met(5, date(2026, 3, 1))))
    assert met.deferred_invoices == {"K-01/EV-000004": date(2026, 3, 1)}
    active, _ = fold(bundle(booking(), activated(2), dataclasses.replace(billing, record_seq=3)))
    assert active.findings == () and active.deferred_invoices == {}


def test_s02_activation_reasons() -> None:
    no_substance = header(has_commercial_substance=False)
    st, _ = fold(bundle(booking(), activated(2), contracts=[no_substance]))
    assert statuses(st)[-1] == ("NOT_A_CONTRACT", "NO_COMMERCIAL_SUBSTANCE", None)

    mutual = header(
        termination_party="BOTH", termination_has_penalty=False, termination_notice_days=0
    )
    delivery = event(
        3,
        "DELIVERY_RECORDED",
        date(2026, 2, 1),
        {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "DELIVERY"},
    )
    st, _ = fold(bundle(booking(), activated(2), delivery, contracts=[mutual]))
    assert statuses(st) == [
        ("DRAFT", "BOOKED", None),
        ("NOT_A_CONTRACT", "MUTUAL_TERMINATION_UNPERFORMED", None),
        ("ACTIVE", "CRITERIA_MET", "CATCH_UP_AT_TRANSITION"),
    ]
    performed_first = (booking(), payment(2, INCEPTION, "10.00"), activated(3))
    st, _ = fold(bundle(*performed_first, contracts=[mutual]))
    assert statuses(st)[-1] == ("ACTIVE", "ACTIVATED", None)

    voided = event(
        3, "CONTRACT_VOIDED", date(2026, 2, 1), {"reason_code": "DUPLICATE", "comment": "x"}
    )
    st, _ = fold(bundle(booking(), activated(2), voided))
    assert statuses(st)[-1] == ("VOIDED", "VOIDED", None)
    assert st.terms[CONTRACT].end_date is None


def test_s02_r05_prospective_failure() -> None:
    events = (
        booking(),
        activated(2),
        collectibility(3, date(2026, 2, 1), probable=False),
        event(4, "SIGNIFICANT_CHANGE_FLAGGED", date(2026, 3, 1), {"description": "credit event"}),
        collectibility(5, date(2026, 3, 2), probable=False),
        payment(6, date(2026, 4, 1), "50.00"),
    )
    st, _ = fold(bundle(*events[:3]))
    assert statuses(st)[-1] == ("ACTIVE", "ACTIVATED", None)  # 25-5: no significant change
    st, _ = fold(bundle(*events))
    assert statuses(st)[-1] == ("NOT_A_CONTRACT", "NOT_PROBABLE", None)
    assert st.status_at(CONTRACT, date(2026, 3, 1)).status == "ACTIVE"
    assert st.deposit_at(CONTRACT).received_cum == 50
    first = {t.period_key for t in st.deposit_targets}
    assert "FY2026-P02" not in first and "FY2026-P03" in first


def test_s02_status_trace_nodes() -> None:
    _, nodes = fold(bundle(booking(), activated(2)))
    node = nodes["status@K-01/EV-000002:K-01:-"]
    assert node.value == "4" and node.formula_id == "step1.status.v1"
    assert node.params == {"reason": "ACTIVATED", "status": "ACTIVE", "value": "4"}
    assert node.inputs == (SourceRef("contract_event", "K-01/EV-000002"),)


def test_s02_apply_boundary_handler() -> None:
    value = bundle(booking(), collectibility(2, INCEPTION, probable=True), activated(3))
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    state = object()
    for view in cb.boundary_events:
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        assert s02_contract_identification.apply(context(value), state, view, tb) is state  # type: ignore[arg-type]
    activation = next(v for v in cb.events if v.event_type == "CONTRACT_ACTIVATED")
    with pytest.raises(ValueError, match="not a stage 02 boundary"):
        s02_contract_identification.apply(context(value), state, activation, tb)  # type: ignore[arg-type]
    assert s02_contract_identification.POLICY_KEYS == tuple(
        sorted(s02_contract_identification.POLICY_KEYS)
    )


def test_d97_29_invoice_on_not_a_contract_once_per_identity() -> None:
    """D-97 (29), S02-R-11 rev 1.12: the warning is raised once per (contract, S10-R-07 identity).
    A status update of INV-1 (same identity, ``is_cancellable`` false) while ``NOT_A_CONTRACT``
    adds no second finding; a second identity INV-2 does. Every such event is still deferred to
    the transition date. Before D-97 (29) each event raised its own finding."""
    payload = {
        "invoice_number": "INV-1",
        "line_external_id": "1",
        "amount": Decimal("100.00"),
        "issue_date": date(2026, 2, 1),
        "is_cancellable": True,
    }
    first = event(4, "BILLING_RECORDED", date(2026, 2, 1), payload)
    update = event(5, "BILLING_RECORDED", date(2026, 2, 10), {**payload, "is_cancellable": False})
    other = event(6, "BILLING_RECORDED", date(2026, 2, 12), {**payload, "invoice_number": "INV-2"})
    base = (
        booking(),
        collectibility(2, INCEPTION, probable=False),
        activated(3),
        first,
        update,
        other,
    )
    st, _ = fold(bundle(*base))
    assert [(f.code, f.event_key) for f in st.findings] == [
        ("INVOICE_ON_NOT_A_CONTRACT", "K-01/EV-000004"),
        ("INVOICE_ON_NOT_A_CONTRACT", "K-01/EV-000006"),
    ]
    assert st.deferred_invoices == {
        "K-01/EV-000004": None,
        "K-01/EV-000005": None,
        "K-01/EV-000006": None,
    }
    met, _ = fold(bundle(*base, criteria_met(7, date(2026, 3, 1))))
    assert set(met.deferred_invoices.values()) == {date(2026, 3, 1)}


# --- S02-R-07 rev 1.6: the time-aware 25-7(a) test, dated points and the cap (D-91 gaps; ENA-2b) --
#
# The worlds come from ``support.step1_worlds`` and run through the book loop, where the deposit
# fold reads the stage 03 classification (``run_deposits`` after stage 03; D-91 gaps (iii)). The
# figures were derived with Fraction arithmetic in ``.run/l9/d91-gaps-d1/derive.py``.

from erev_engine.stages import s03_pob_builder  # noqa: E402
from support import step1_worlds as w  # noqa: E402

EARLIEST_TERMINATION = "TO_EARLIEST_TERMINATION_WITHOUT_SUBSTANTIVE_PENALTY"
END_OF_DAY = 2**63 - 1  # deposits.END_OF_DAY: a dated point after every event of its date


def run_deposits(ctx: BookContext, identified: IdentifiedState, pob: object, tb: TraceBuilder):  # type: ignore[no-untyped-def]
    """The ENA-2b entry point, resolved at call time so the earlier cases still collect on a
    revision without it (the fail-first evidence names each case's own failure)."""
    return s02_contract_identification.run_deposits(ctx, identified, pob, tb)  # type: ignore[arg-type]


def refined(
    value: InputBundle, book_code: str = "ASC606"
) -> tuple[IdentifiedState, dict[str, TraceNode]]:
    """Stage 02 without its ledger, stage 03, then the deposit fold (the book loop's order)."""
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    ctx = context(value, book_code)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    identified = s02_contract_identification.run(ctx, cb, tb, deposits=False)
    assert identified.deposits[w.CONTRACT] == () and identified.deposit_targets == ()
    pob = s03_pob_builder.run(ctx, identified, tb)
    state = run_deposits(ctx, identified, pob, tb)
    return state, {node.id: node for node in tb.build(root_measures={}).nodes}


def recognitions(st: IdentifiedState) -> list[tuple[str, date, str | None, Fraction]]:
    return [(r.reason, r.effective_date, r.event_key, r.amount) for r in st.recognitions]


def target(st: IdentifiedState, measure: str, period: str) -> int:
    return next(
        t.value for t in st.deposit_targets if (t.measure, t.period_key) == (measure, period)
    )


def test_s02_r07_a_time_elapsed_service_releases_at_its_term_end() -> None:
    """T1 (D-91 gaps (ii), (iii)): a completed, fully paid, nonrefundable TIME_ELAPSED service of
    1,200.00 recognises its deposit at the term end 2026-12-31 as a dated point ordered after the
    events of that date (node ``deposit_to_revenue@2026-12-31``), so the FY2026-P12 liability is 0
    and the CLOSE_RELEASE share ``deposit_to_revenue_time_cum`` is 1,200.00."""
    st, nodes = refined(w.time_world())
    assert recognitions(st) == [("EVENT_25_7_A", date(2026, 12, 31), None, Fraction(1200))]
    (recognition,) = st.recognitions
    assert (
        recognition.timed and recognition.node_id == f"deposit_to_revenue@2026-12-31:{w.SUBJECT}:-"
    )
    node = nodes[recognition.node_id]
    assert (node.value, node.formula_id, node.params["reason"], node.params["limit"]) == (
        "1200.00",
        "step1.event_25_7.v1",
        "EVENT_25_7_A",
        "1200",
    )
    assert st.deposits[w.CONTRACT][-1].order_key == (date(2026, 12, 31), END_OF_DAY, "")
    assert target(st, "deposit_liability", "FY2026-P11") == 120000
    assert target(st, "deposit_liability", "FY2026-P12") == 0
    assert target(st, "deposit_to_revenue_cum", "FY2026-P12") == 120000
    assert target(st, "deposit_to_revenue_time_cum", "FY2026-P12") == 120000
    assert target(st, "deposit_to_revenue_time_cum", "FY2026-P11") == 0
    assert statuses(st, w.CONTRACT)[-1] == ("NOT_A_CONTRACT", "NOT_PROBABLE", None)  # (a) keeps it
    # T2: at the November horizon nothing is due; T3: a refundable deposit stays a liability.
    early, _ = refined(w.time_world(months=11))
    assert early.recognitions == () and target(early, "deposit_liability", "FY2026-P11") == 120000
    refundable, _ = refined(w.time_world(nonrefundable=False))
    assert refundable.recognitions == ()
    assert target(refundable, "deposit_liability", "FY2026-P12") == 120000


@pytest.mark.parametrize("convention", ["MONTHLY_EVEN", "DAILY", "MID_MONTH"])
def test_s02_r07_a_term_end_mid_month_whatever_the_convention(convention: str) -> None:
    """T8 and its DAILY twin (D-91 gaps (ii)): a term ending 2026-11-15 is transferred on
    2026-11-15 in FY2026-P11, not on the ALG-11 f = 1 date (MID_MONTH reaches f = 1 only on
    2026-11-30, D-79); E10: MID_MONTH with a term ending 2026-11-10 reaches f = 1 on 2026-10-31,
    yet the transfer waits for the term end (FY2026-P11)."""
    st, _ = refined(w.time_world(end=date(2026, 11, 15), convention=convention))
    assert recognitions(st) == [("EVENT_25_7_A", date(2026, 11, 15), None, Fraction(1200))]
    assert target(st, "deposit_liability", "FY2026-P10") == 120000
    assert target(st, "deposit_liability", "FY2026-P11") == 0
    assert target(st, "deposit_to_revenue_time_cum", "FY2026-P11") == 120000
    early, _ = refined(w.time_world(end=date(2026, 11, 10), convention=convention))
    assert recognitions(early) == [("EVENT_25_7_A", date(2026, 11, 10), None, Fraction(1200))]
    assert target(early, "deposit_liability", "FY2026-P10") == 120000


def test_s02_r07_a_receipts_completing_after_the_term_end() -> None:
    """T4 (D-91 gaps (iii)): 1,100.00 received by the term end and 100.00 on 2027-01-15: nothing at
    T (receipts short), the recognition is dated the completing receipt (an EVENT); T4b: receipts
    of 1,100.00 alone recognise nothing through January 2027.

    E6 (a completing receipt dated T itself) records the two readings of the texts, ruled by D-94
    (1): reading A, S02-R-07 "the recognition is dated the first date the conditions hold: T when
    receipts are complete, else the completing receipt's event" read as EVENT at the receipt on T
    (the test's expectation on aa7c3a7); reading B, D-91 (iii) "Stage 02 evaluates (a) at T =
    max(term end) as a dated point ordered after every event of T" and the same S02-R-07 sentence
    read as: a receipt dated T completes the receipts AT the dated point, so the recognition is at T
    as a TIME amount of the CLOSE_RELEASE pass; the completing-receipt branch is for a receipt after
    T (T4). D-94 (1) rules reading B; the total is 1,200.00 under both, only the class and the pass
    differ. This edited expectation is the ruling, not independent proof of the reading."""
    st, _ = refined(
        w.time_world(paid="1100.00", steps=[("P", date(2027, 1, 15), "100.00")], months=13)
    )
    assert recognitions(st) == [
        ("EVENT_25_7_A", date(2027, 1, 15), f"{w.CONTRACT}/EV-000005", Fraction(1200))
    ]
    assert not st.recognitions[0].timed
    assert target(st, "deposit_liability", "FY2026-P12") == 110000
    assert target(st, "deposit_liability", "FY2027-P01") == 0
    assert (
        target(st, "deposit_to_revenue_time_cum", "FY2027-P01") == 0
    )  # an EVENT, not a dated point
    short, _ = refined(w.time_world(paid="1100.00", months=13))
    assert short.recognitions == () and target(short, "deposit_liability", "FY2027-P01") == 110000
    # E6 (D-94 (1), reading B): the completing receipt dated T completes the receipts before the
    # dated point, which is ordered after every event of T; the recognition is the dated point.
    on_end, _ = refined(w.time_world(paid="1100.00", steps=[("P", date(2026, 12, 31), "100.00")]))
    assert recognitions(on_end) == [("EVENT_25_7_A", date(2026, 12, 31), None, Fraction(1200))]
    assert on_end.recognitions[0].timed
    assert target(on_end, "deposit_to_revenue_time_cum", "FY2026-P12") == 120000


def test_s02_r07_a_mixed_contract_and_unresolved_term() -> None:
    """T5 (D-91 gaps (ii)): goods delivered 2026-12-15 and a service ending 2026-12-31 release at
    max(delivery, service end) = 2026-12-31; T5b: undelivered goods release nothing although the
    term elapsed; E9: a TIME_ELAPSED term whose CONTROL_TRANSFER start is not observed is never
    transferred by time."""
    st, _ = refined(w.mixed_world())
    assert recognitions(st) == [("EVENT_25_7_A", date(2026, 12, 31), None, Fraction(1200))]
    undelivered, _ = refined(w.mixed_world(delivery=None))
    assert undelivered.recognitions == ()
    assert target(undelivered, "deposit_liability", "FY2026-P12") == 120000
    unresolved, _ = refined(w.time_world(template_changes={"start_date_rule": "CONTROL_TRANSFER"}))
    assert unresolved.recognitions == ()
    assert target(unresolved, "deposit_liability", "FY2026-P12") == 120000


def test_s02_r07_cap_on_every_route() -> None:
    """X4 (D-91 gaps (vi)): receipts of 1,300.00 on a 1,200.00 contract recognise 120,000 minor and
    leave 10,000 minor in DEPOSIT_LIABILITY under (a) delivery, (b) termination and (c) the dated
    ``event_c_met_on`` point alike; a receipt after the release stays in the liability (E7)."""
    delivery, nodes = refined(w.pit_world(paid="1300.00"))
    assert recognitions(delivery) == [
        ("EVENT_25_7_A", date(2026, 12, 31), f"{w.CONTRACT}/EV-000005", Fraction(1200))
    ]
    assert target(delivery, "deposit_liability", "FY2026-P12") == 10000
    assert nodes[delivery.recognitions[0].node_id].params["limit"] == "1200"
    terminated, _ = refined(
        w.pit_world(paid="1300.00", delivery=None, steps=[("T", date(2026, 4, 1), "0.00")])
    )
    assert recognitions(terminated) == [
        ("EVENT_25_7_B", date(2026, 4, 1), f"{w.CONTRACT}/EV-000005", Fraction(1200))
    ]
    assert target(terminated, "deposit_liability", "FY2026-P04") == 10000
    assert statuses(terminated, w.CONTRACT)[-1] == ("TERMINATED", "EVENT_25_7_B", None)
    met, _ = refined(
        w.time_world(
            paid="1200.00", met_on=date(2026, 3, 31), steps=[("P", date(2026, 4, 15), "100.00")]
        )
    )
    assert recognitions(met) == [("EVENT_25_7_C", date(2026, 3, 31), None, Fraction(1200))]
    assert target(met, "deposit_liability", "FY2026-P04") == 10000  # the later receipt is capped
    after, _ = refined(w.time_world(steps=[("P", date(2027, 1, 15), "100.00")], months=13))
    assert recognitions(after) == [("EVENT_25_7_A", date(2026, 12, 31), None, Fraction(1200))]
    assert target(after, "deposit_liability", "FY2027-P01") == 10000


def test_s02_r07_b_refund_then_release() -> None:
    """(b): a FULL termination on 2026-04-01 with a 200.00 refund recognises the 1,000.00 balance
    (node params ``limit``); the refund and the release are two movements of one event."""
    st, nodes = refined(w.pit_world(delivery=None, steps=[("T", date(2026, 4, 1), "200.00")]))
    assert recognitions(st) == [
        ("EVENT_25_7_B", date(2026, 4, 1), f"{w.CONTRACT}/EV-000005", Fraction(1000))
    ]
    final = st.deposit_at(w.CONTRACT)
    assert (final.refunded_cum, final.to_revenue_cum, final.liability) == (200, 1000, 0)
    assert target(st, "deposit_refunded_cum", "FY2026-P04") == 20000
    assert nodes[st.recognitions[0].node_id].params["limit"] == "1200"


def test_s02_r07_c_dated_point_then_receipts() -> None:
    """(c) at ``event_c_met_on`` 2026-03-31 is a dated point (the CLOSE_RELEASE share), a later
    receipt is recognised at its event; the two points of one contract stay in ENG-06 order."""
    st, nodes = refined(
        w.time_world(
            paid="500.00", met_on=date(2026, 3, 31), steps=[("P", date(2026, 4, 15), "300.00")]
        )
    )
    assert recognitions(st) == [
        ("EVENT_25_7_C", date(2026, 3, 31), None, Fraction(500)),
        ("EVENT_25_7_C", date(2026, 4, 15), f"{w.CONTRACT}/EV-000005", Fraction(300)),
    ]
    assert target(st, "deposit_to_revenue_time_cum", "FY2026-P04") == 50000
    assert target(st, "deposit_to_revenue_cum", "FY2026-P04") == 80000
    keys = [point.order_key for point in st.deposits[w.CONTRACT]]
    assert keys == sorted(keys)
    assert nodes[f"deposit_to_revenue_time_cum:{w.SUBJECT}:FY2026-P04"].value == "500.00"


def test_s02_r07_a_receipt_test_reads_the_enforceable_consideration() -> None:
    """S02-R-06 truncation (D-91 gaps (ii)): the customer may terminate without a substantive
    penalty and the reviewed CONTRACT_TERM ends the term on 2026-06-30 with an enforceable
    consideration of 600.00; receipts of 600.00 complete the test and the release of 600.00 is
    dated the truncated end."""
    term = JudgementInput(
        "J-TERM",
        "CONTRACT_TERM",
        w.CONTRACT,
        None,
        {
            "enforceable_end_date": "2026-06-30",
            "termination_penalty_substantive": "false",
            f"enforceable_consideration[{w.SERVICE}]": "600.00",
        },
    )
    value = w.time_world(
        paid="600.00",
        judgements=[term],
        termination_party="CUSTOMER",
        policies={"step1.term_with_termination_rights": EARLIEST_TERMINATION},
    )
    st, _ = refined(value)
    assert st.terms[w.CONTRACT].basis == "JUDGEMENT"
    assert recognitions(st) == [("EVENT_25_7_A", date(2026, 6, 30), None, Fraction(600))]
    assert target(st, "deposit_liability", "FY2026-P06") == 0


def test_s02_run_deposits_refuses_a_second_pass() -> None:
    """A state whose ledger already folded (``run`` on its own) is not folded again (CV-50)."""
    value = w.time_world()
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    ctx = context(value)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    identified = s02_contract_identification.run(ctx, cb, tb)  # the ledger test only
    assert identified.recognitions == () and identified.deposits[w.CONTRACT] != ()
    pob = s03_pob_builder.run(ctx, identified, tb)
    with pytest.raises(EngineError) as raised:
        run_deposits(ctx, identified, pob, tb)
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"


def test_s02_r07_a_term_end_event_does_not_pre_empt_the_dated_point() -> None:
    """D1-R01 (D-91 gaps (iii)): T's 25-7(a) evaluation is ordered after every event of T, so an
    event dated T cannot transfer a time term ending T. Receipts 1,200.00, a billing dated T and a
    FULL termination dated T with a 200.00 refund: the refund is 200.00 and route (b) recognises
    1,000.00 at the termination (deposit 0); the sibling with CONTRACT_CRITERIA_MET dated T
    recognises nothing under 25-7 and transfers the 1,200.00 (S02-R-08). Figures: derive.py R01."""
    st, _ = refined(w.time_world(steps=[("I", w.END, "1200.00"), ("T", w.END, "200.00")]))
    assert recognitions(st) == [("EVENT_25_7_B", w.END, f"{w.CONTRACT}/EV-000006", Fraction(1000))]
    assert target(st, "deposit_refunded_cum", "FY2026-P12") == 20000
    assert target(st, "deposit_to_revenue_cum", "FY2026-P12") == 100000
    assert target(st, "deposit_to_revenue_time_cum", "FY2026-P12") == 0
    assert target(st, "deposit_liability", "FY2026-P12") == 0
    met, _ = refined(w.time_world(steps=[("I", w.END, "1200.00"), ("C", w.END, "")]))
    assert met.recognitions == ()
    assert statuses(met, w.CONTRACT)[-1][:2] == ("ACTIVE", "CRITERIA_MET")
    assert target(met, "deposit_to_contract_liability_cum", "FY2026-P12") == 120000
    assert target(met, "deposit_to_revenue_cum", "FY2026-P12") == 0
    assert target(met, "deposit_liability", "FY2026-P12") == 0


def test_s02_r07_a_qualifying_events_keep_their_timing() -> None:
    """Secondary review item 2 (D-94 (1) conditions): the same-date rule defers only a time term
    ending on the event's date; an event after T or without a time term keeps its EVENT timing.
    (a) service 1 Jan–30 Jun, receipts 1,199.99 through T and 0.01 on 1 Jul: nothing at T, EVENT
    1,200.00 on 1 Jul, time share 0; (b) goods fully paid and delivered 30 Jun: EVENT at the
    delivery; (c) service ended 29 Jun and goods delivered 30 Jun: nothing at T = 29 Jun, EVENT at
    the delivery. Figures: derive.py ITEM2a-c."""
    a, _ = refined(
        w.time_world(end=date(2026, 6, 30), paid="1199.99", steps=[("P", date(2026, 7, 1), "0.01")])
    )
    assert recognitions(a) == [
        ("EVENT_25_7_A", date(2026, 7, 1), f"{w.CONTRACT}/EV-000005", Fraction(1200))
    ]
    assert target(a, "deposit_liability", "FY2026-P06") == 119999
    assert target(a, "deposit_liability", "FY2026-P07") == 0
    assert target(a, "deposit_to_revenue_time_cum", "FY2026-P07") == 0
    b, _ = refined(w.pit_world(delivery=date(2026, 6, 30)))
    assert recognitions(b) == [
        ("EVENT_25_7_A", date(2026, 6, 30), f"{w.CONTRACT}/EV-000005", Fraction(1200))
    ]
    assert target(b, "deposit_to_revenue_time_cum", "FY2026-P06") == 0
    c, _ = refined(w.mixed_world(delivery=date(2026, 6, 30), service_end=date(2026, 6, 29)))
    assert recognitions(c) == [
        ("EVENT_25_7_A", date(2026, 6, 30), f"{w.CONTRACT}/EV-000005", Fraction(1200))
    ]
    assert target(c, "deposit_to_revenue_time_cum", "FY2026-P06") == 0
