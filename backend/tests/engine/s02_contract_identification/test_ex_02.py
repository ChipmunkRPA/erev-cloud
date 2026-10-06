"""EX-02-A and EX-02-B (ENGINE_SPEC §2.6; CHK-021; S02-R-04, S02-R-08, S02-R-09; ENA-2)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION, dates, money, progress
from erev_engine.bundle import BookInput, ContractInput, EventInput, InputBundle
from erev_engine.enums import BookCode
from erev_engine.stages import s01_canonicalize, s02_contract_identification
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.state import BookContext, PolicyResolver
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles

INCEPTION = date(2026, 1, 1)
CASE_C = "S1-CASE-C"
MONTH_ENDS = [dates.month_end(date(2026, month, 1)) for month in range(1, 7)]


def _event(
    contract: str, stream: int, kind: str, on: date, payload: Mapping[str, object]
) -> EventInput:
    return bundles.event(contract, stream, kind, on, payload)


def _booking(contract: str, on: date, product: str, price: str, end: date) -> EventInput:
    line = bundles.booking_line(
        "POB-01", product_code=product, quantity="1", total_price=price, start=on, end=end
    )
    return bundles.event(
        contract, 1, "CONTRACT_BOOKED", on, {"lines": [line]}, obligation_keys=["POB-01"]
    )


def _with_policies(book: BookInput, overrides: Mapping[str, str]) -> BookInput:
    policies = tuple(
        dataclasses.replace(policy, value=overrides[policy.code])
        if policy.code in overrides and policy.scope == "GROUP"
        else policy
        for policy in book.policies
    )
    return dataclasses.replace(book, policies=policies)


def _bundle(
    events: Iterable[EventInput],
    contracts: Iterable[ContractInput],
    products: Iterable[str],
    *,
    known_at: datetime,
    policies: Mapping[str, str] | None = None,
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    headers = tuple(contracts)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=known_at,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(_with_policies(bundles.book(entity=calendar), policies or {}),),
        entities=(calendar,),
        group=bundles.group(headers, products=[bundles.product(code) for code in products]),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def _fold(value: InputBundle) -> tuple[IdentifiedState, dict[str, TraceNode]]:
    book = value.books[0]
    ctx = BookContext(
        book_code=BookCode.ASC606,
        framework=BookCode.ASC606,
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon={value.entities[0].code: value.entities[0].periods[-1].period_key},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    st = s02_contract_identification.run(ctx, cb, tb)
    return st, {node.id: node for node in tb.build(root_measures={}).nodes}


def _case_c(policies: Mapping[str, str] | None = None) -> InputBundle:
    term_end = date(2028, 12, 31)
    events = [
        _booking(CASE_C, INCEPTION, "SVC", "720.00", term_end),
        _event(
            CASE_C,
            2,
            "COLLECTIBILITY_ASSESSED",
            INCEPTION,
            {"book": "ASC606", "is_probable": False, "judgement_record_id": "J-1"},
        ),
        _event(CASE_C, 3, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        *(
            _event(
                CASE_C,
                4 + index,
                "PAYMENT_RECEIVED",
                on,
                {
                    "receipt_reference": f"R-{index + 1}",
                    "amount": Decimal("20.00"),
                    "receipt_date": on,
                },
            )
            for index, on in enumerate(MONTH_ENDS)
        ),
        _event(
            CASE_C,
            10,
            "CONTRACT_CRITERIA_MET",
            MONTH_ENDS[-1],
            {"book": "ASC606", "judgement_record_id": "J-2"},
        ),
    ]
    contract = bundles.contract(CASE_C, inception=INCEPTION)
    return _bundle(
        events, [contract], ["SVC"], known_at=datetime(2026, 7, 1, tzinfo=UTC), policies=policies
    )


def test_ex_02_a_deposit_targets() -> None:
    st, nodes = _fold(_case_c())
    assert [(s.status, s.reason, s.transition) for s in st.timelines[CASE_C]] == [
        ("DRAFT", "BOOKED", None),
        ("NOT_A_CONTRACT", "NOT_PROBABLE", None),
        ("ACTIVE", "CRITERIA_MET", "CATCH_UP_AT_TRANSITION"),
    ]
    targets = {(t.measure, t.period_key): t for t in st.deposit_targets}
    month_5 = targets[("deposit_liability", "FY2026-P05")]
    assert (month_5.value, month_5.exact, month_5.subject_key) == (10000, 100, "S1-CASE-C@US01")
    assert nodes[month_5.node_id].value == "100.00"
    criteria = next(v for v in st.canonical.events if v.event_type == "CONTRACT_CRITERIA_MET")
    assert st.deposit_at(CASE_C, before=criteria).liability == 120  # after the month-6 receipt

    assert targets[("deposit_liability", "FY2026-P06")].value == 0
    assert targets[("deposit_received_cum", "FY2026-P06")].value == 12000
    assert targets[("deposit_to_contract_liability_cum", "FY2026-P06")].value == 12000
    [transition] = st.transitions
    assert (transition.transition, transition.deposit_transferred) == (
        "CATCH_UP_AT_TRANSITION",
        Fraction(120),
    )
    assert (
        transition.node_id == "deposit_to_contract_liability@S1-CASE-C/EV-000010:S1-CASE-C@US01:-"
    )
    assert nodes[transition.node_id].value == "120.00"
    assert nodes[transition.node_id].formula_id == "step1.transition_catch_up.v1"
    assert all(point.liability >= 0 for point in st.deposits[CASE_C])  # S02-INV-02
    assert st.deposit_at(CASE_C).liability == 0  # S02-INV-03
    assert st.inception_basis(CASE_C) == ("INCEPTION", INCEPTION)  # INCEPTION segments kept
    assert st.findings == ()
    # CHK-021 inputs: on the inception basis the transition-period revenue is 120.00.
    f = progress.time_fraction("MONTHLY_EVEN", INCEPTION, date(2028, 12, 31), MONTH_ENDS[-1])
    assert f == Fraction(6, 36)
    assert money.cumulative_posted(Fraction(720), 72000, f, 2) == 12000

    prospective, _ = _fold(
        _case_c({"step1.criteria_met_transition": "PROSPECTIVE_FROM_TRANSITION"})
    )
    assert prospective.inception_basis(CASE_C) == ("PROSPECTIVE", MONTH_ENDS[-1])
    assert prospective.deposit_at(CASE_C).to_contract_liability_cum == 120


def test_ex_02_b_combined_inception_fold() -> None:
    licence_on, services_on = date(2026, 1, 10), date(2026, 1, 20)
    contracts = [
        bundles.contract("C-1", inception=licence_on),
        bundles.contract("C-2", inception=services_on),
    ]
    events = [
        _booking("C-1", licence_on, "LICENCE", "90000.00", date(2026, 12, 31)),
        _booking("C-2", services_on, "SERVICES", "60000.00", date(2026, 3, 31)),
        _event("C-1", 2, "CONTRACT_ACTIVATED", services_on, {"checklist": {}}),
        _event("C-2", 2, "CONTRACT_ACTIVATED", services_on, {"checklist": {}}),
    ]
    value = _bundle(
        events, contracts, ["LICENCE", "SERVICES"], known_at=datetime(2026, 2, 1, tzinfo=UTC)
    )
    combined = dataclasses.replace(
        value, group=dataclasses.replace(value.group, criterion="25_9_A")
    )
    st, _ = _fold(combined)
    assert st.member_contract_keys == ("C-1", "C-2")
    assert (st.group_code, st.inception_date) == ("CG-1", licence_on)
    assert [view.header.external_id for view in st.contracts] == ["C-1", "C-2"]
    assert all(s01_canonicalize.booking_lines(view) for view in st.contracts)
    assert [st.timelines[c][-1].status for c in ("C-1", "C-2")] == ["ACTIVE", "ACTIVE"]
    assert set(st.terms) == {"C-1", "C-2"}
