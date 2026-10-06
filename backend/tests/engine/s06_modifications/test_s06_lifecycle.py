"""Stage 06 subscription changes, terminations, unpriced change orders, credit rollover, negatives.

ENGINE_SPEC §6.4 S06-R-19 to S06-R-22, §6.7 EX-06-I, EX-06-J; ENGINE_SPEC_B §9.2.6 S09-R-22;
POLICIES §5.2 PT-02, §5.3 PT-03 (CHK-112), §5.5 PT-05 (CHK-115), POL-105, POL-241, POL-242,
POL-244; ENB-4. The inception state comes from the real stages 01 to 05. The tests bind a fake
stage 04 price function (D-81), which prices the modifications applied by ``CONTRACT_AMENDED`` and
``CONTRACT_TERMINATED`` and the ``UNPRICED_CHANGE_ORDER`` versions. Every stage 06 trace
re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EstimateVersionInput, EventInput, InputBundle
from erev_engine.enums import ModificationTreatment
from erev_engine.money import cumulative_posted
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
    s06_modifications,
    s09_recognition,
)
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s06_modifications import ModificationView, SubscriptionCommand
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    Quota,
    Quota1,
    SegmentCause,
    TpBuildUp,
)
from erev_engine.trace import TraceBuilder
from support import bundles
from support.recognition import estimate_version, period_amounts, targets_by_period
from test_s06_catch_up import cost, eac, estimate_event, with_eac
from test_s06_prospective import (
    CONTRACT,
    INCEPTION,
    KNOWN_AT,
    TEMPLATES,
    Folded,
    amended,
    booked,
    bundle,
    checked,
    context,
    delivered,
    fold,
    mod_line,
    modification_input,
    obligation,
    point_entry,
    product,
    ssp_version,
    template,
    usd,
)

EXTRA_TEMPLATES = (
    template("TPL-CREDITS", method="REDEMPTION_PATTERN", pattern="POINT_IN_TIME"),
    template("TPL-SUB", method="TIME_ELAPSED", pattern="OVER_TIME", convention="MONTHLY_EVEN"),
)


def with_templates(value: InputBundle) -> InputBundle:
    """The bundle with the subscription and prepaid-credit templates of this module."""
    found = sorted((*TEMPLATES, *EXTRA_TEMPLATES), key=lambda item: item.template_code)
    return dataclasses.replace(value, pob_template_versions=tuple(found))


def inception(value: InputBundle) -> tuple[BookContext, IdentifiedState, AllocatedState]:
    ctx = context(value)
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(value, scratch)
    identified = s02_contract_identification.run(ctx, cb, scratch)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, scratch), scratch)
    st = s05_allocation.run(ctx, priced, scratch)
    assert st.findings == ()
    return ctx, identified, st


def fold_at(value: InputBundle, event_type: str) -> Folded:
    """The inception fold and the one boundary event of ``event_type`` to apply."""
    ctx, identified, st = inception(value)
    (boundary,) = [ev for ev in st.events if ev.event_type == event_type]
    return Folded(ctx, identified, st, boundary)


def price_function(booked_price: str) -> s06_modifications.PriceAt:
    """A fake stage 04 ``price_at`` (ENGINE_SPEC §4.2; D-81), minor units.

    The allocation basis is the booked price, plus the consideration of every modification that a
    ``CONTRACT_AMENDED`` or ``CONTRACT_TERMINATED`` applied before the position, plus the
    constrained amount of each ``UNPRICED_CHANGE_ORDER`` element. That amount comes from the
    version applied by an event before the position, else from the version effective on the date
    of a modification that precedes the position: the modification makes it includable (S06-R-12
    ΔVC).
    """

    def price(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        total = usd(booked_price)
        header = st.contracts[0].header
        modifications = {item.modification_key: item for item in header.modifications}
        modified_on: set[date] = set()
        for ev in st.events:
            if ev.event_type not in ("CONTRACT_AMENDED", "CONTRACT_TERMINATED"):
                continue
            if ev.effective_date > at or (before is not None and ev.order_key >= before.order_key):
                continue
            found = modifications[str(ev.payload["modification_id"])]
            total += sum(usd(str(line["consideration_delta"])) for line in found.lines)
            modified_on.add(ev.effective_date)
        for key in sorted(st.estimates.pins):
            version = st.estimates.pin(key, at, before)
            if version is None:
                included = [
                    pin.version
                    for pin in st.estimates.pins[key]
                    if pin.version.effective_date in modified_on
                ]
                version = min(included, key=lambda item: item.version_no, default=None)
            if version is None or version.vc_element_type != "UNPRICED_CHANGE_ORDER":
                continue
            total += usd(str(version.constrained_amount))
        quota = Quota1(Fraction(total, 100), total)
        zero = Quota1(Fraction(0), 0)
        key = None if before is None else before.event_key
        return TpBuildUp(at, key, quota, *(zero,) * 8, quota, quota, ())

    return price


def billing(stream: int, key: str, amount: str, on: date) -> EventInput:
    payload = {
        "invoice_number": f"INV-{stream}",
        "line_external_id": f"INV-{stream}/1",
        "obligation_key": key,
        "amount": Decimal(amount),
        "issue_date": on,
    }
    return bundles.event(CONTRACT, stream, "BILLING_RECORDED", on, payload, obligation_keys=[key])


# --- EX-06-J (CHK-112; PT-03): termination with refund -------------------------------------------

TERMINATION_DATE = date(2027, 7, 1)  # month 19: the refund covers months 19 to 24


def chk_112(refund: str) -> Folded:
    """A 24-month subscription for 240,000.00, billed 120,000.00 a year in advance."""
    subscription = bundles.booking_line(
        "SUB", product_code="SKU-SUB", total_price="240000.00", end=date(2027, 12, 31)
    )
    removal = mod_line("SUB", "REMOVE", "SKU-SUB", "0", f"-{refund}")
    modification = modification_input("MOD-T", TERMINATION_DATE, [removal], kind="TERMINATION")
    payload = {
        "modification_id": "MOD-T",
        "termination_kind": "FULL",
        "refund_amount": Decimal(refund),
    }
    terminated = bundles.event(
        CONTRACT, 5, "CONTRACT_TERMINATED", TERMINATION_DATE, payload, obligation_keys=["SUB"]
    )
    value = bundle(
        booked(INCEPTION, subscription),
        billing(3, "SUB", "120000.00", INCEPTION),
        billing(4, "SUB", "120000.00", date(2027, 1, 1)),
        terminated,
        products=[product("SKU-SUB", "TPL-SUB")],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", "SKU-SUB", "240000.00")], date(2025, 1, 1))],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
        # POL-090 applies over the template convention (S03-R-17): 18 whole months at d_T − 1.
        overrides={"recognition.time_convention": "MONTHLY_EVEN"},
    )
    return fold_at(with_templates(value), "CONTRACT_TERMINATED")


def test_chk_112_termination_with_refund() -> None:
    folded = chk_112("60000.00")
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx,
        folded.state,
        ev,
        tb,
        identified=folded.identified,
        price_at=price_function("240000.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    pool = nodes[f"mod_pool@{ev.event_key}:K-01:-"]
    assert (pool.value, pool.params["revenue"], pool.params["consideration"]) == (
        "0.00",  # Pool = 60,000.00 − 60,000.00
        str(usd("180000.00")),
        str(usd("-60000.00")),  # the REMOVE line
    )
    subscription = obligation(after, "SUB")
    segment = subscription.segments[-1]
    assert (segment.cause, segment.basis, segment.x_exact, segment.a_posted) == (
        SegmentCause.TERMINATION,
        "INCEPTION",
        180000,
        usd("180000.00"),
    )
    assert (subscription.terminated_on, subscription.end_date) == (
        TERMINATION_DATE,
        date(2027, 6, 30),
    )
    allocation = nodes[f"allocated_amount@{ev.event_key}:K-01/SUB:-"]
    assert (allocation.formula_id, allocation.value) == ("mod.termination.v1", "180000.00")
    assert nodes[f"catch_up@{ev.event_key}:K-01/SUB:-"].value == "0.00"
    component = f"K-01#TERMINATION@{ev.event_key}"
    assert after.refund_components == {component: Quota(Fraction(60000), usd("60000.00"))}
    refund = nodes[f"refund_component@{ev.event_key}:K-01:-"]
    assert (refund.formula_id, refund.value, refund.params["component"]) == (
        "mod.termination.v1",
        "60000.00",
        "TERMINATION",
    )
    assert after.tp_history[-1].allocation_basis.posted == usd("180000.00")
    # A FULL termination sets TERMINATED in every book (Table 2.2-A, stage 02 status machine).
    assert after.contracts[0].status_in_book["ASC606"][-1] == (TERMINATION_DATE, "TERMINATED")
    # Stage 09 over the state: revenue 180,000.00 through June 2027 and no revenue after it.
    state = s09_recognition.run(folded.ctx, after, TraceBuilder(engine_version=ENGINE_VERSION))
    cumulative = targets_by_period(state, "K-01/SUB")
    assert (cumulative["FY2027-P06"], cumulative["FY2027-P12"]) == (
        usd("180000.00"),
        usd("180000.00"),
    )
    amounts = period_amounts(cumulative)
    assert all(amounts[key] == 0 for key in amounts if key > "FY2027-P06")

    # A smaller refund leaves nonrefundable consideration in the pool with no remaining
    # obligation: satisfied performance the ended obligation recognises (S06-R-09, S06-R-21).
    folded = chk_112("40000.00")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx,
        folded.state,
        folded.amended,
        tb,
        identified=folded.identified,
        price_at=price_function("240000.00"),
    )
    nodes = checked(tb)
    assert nodes[f"satisfied_share@{ev.event_key}:K-01/SUB:-"].value == "20000.00"
    segment = obligation(after, "SUB").segments[-1]
    assert (segment.x_exact, segment.a_posted) == (200000, usd("200000.00"))
    assert nodes[f"catch_up@{ev.event_key}:K-01/SUB:-"].value == "20000.00"
    assert after.refund_components == {component: Quota(Fraction(40000), usd("40000.00"))}


# --- EX-06-I (CHK-115; PT-05): unpriced change order ---------------------------------------------

CHANGE_DATE = date(2026, 7, 1)
AGREED_DATE = date(2026, 11, 1)


def unpriced(number: int, effective: date, likely: str, constrained: str) -> EstimateVersionInput:
    """An ``UNPRICED_CHANGE_ORDER`` version of ``K-01/UCO-1`` (T-CON-13; POL-105)."""
    base = estimate_version(f"{CONTRACT}/UCO-1", "VARIABLE_CONSIDERATION", number, effective)
    return dataclasses.replace(
        base,
        vc_element_type="UNPRICED_CHANGE_ORDER",
        allocation_target="CONTRACT",
        unconstrained_amount=Decimal(likely),
        constrained_amount=Decimal(constrained),
    )


def test_chk_115_unpriced_change_order() -> None:
    change = modification_input(
        "MOD-115", CHANGE_DATE, [mod_line("B", "CHANGE", "SKU-BUILD", "0", "0.00")], kind="OTHER"
    )
    first, updated = (
        eac("EAC-B", 1, INCEPTION, "800000.00"),
        eac("EAC-B", 2, CHANGE_DATE, "900000.00"),
    )
    estimated, agreed = (
        unpriced(1, CHANGE_DATE, "120000.00", "90000.00"),
        unpriced(2, AGREED_DATE, "110000.00", "110000.00"),
    )
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "B", product_code="SKU-BUILD", total_price="1000000.00", end=date(2027, 12, 31)
            ),
        ),
        estimate_event(3, first),
        cost(4, "B", "400000.00", date(2026, 6, 30)),
        amended(5, change, {"B": "CUMULATIVE_CATCH_UP"}),
        estimate_event(6, estimated),  # the unpriced change order, effective at d
        estimate_event(7, updated),  # the approved scope adds 100,000.00 of costs
        cost(8, "B", "200000.00", date(2026, 10, 31)),
        estimate_event(9, agreed),  # the price is agreed at 110,000.00
        products=[product("SKU-BUILD", "TPL-C2C")],
        ssp=[
            ssp_version(1, [point_entry("SSP-US@v1", "SKU-BUILD", "1000000.00")], date(2025, 1, 1))
        ],
        inception=INCEPTION,
        months=24,
        modifications=[change],
        estimate_versions=[first, updated, estimated, agreed],
    )
    folded = with_eac(fold(value), "B", "EAC-B")
    ev = folded.amended
    price = price_function("1000000.00")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx, folded.state, ev, tb, identified=folded.identified, price_at=price
    )
    assert after.findings == ()
    nodes = checked(tb)
    pool = nodes[f"mod_pool@{ev.event_key}:K-01:-"]
    assert (pool.value, pool.params["vc_delta"], pool.params["unpriced_change_orders"]) == (
        "590000.00",  # (1,000,000.00 − 500,000.00) + ΔVC 90,000.00
        str(usd("90000.00")),
        "K-01/UCO-1@v1",
    )
    segment = obligation(after, "B").segments[-1]
    assert (segment.basis, segment.x_exact, segment.a_posted) == (
        "INCEPTION",
        1090000,
        usd("1090000.00"),  # A′
    )
    revenue = cumulative_posted(segment.x_exact, segment.a_posted, Fraction(400000, 900000), 2)
    assert revenue == usd("484444.44")  # C′ with f′ = 400,000 ÷ 900,000
    assert nodes[f"catch_up@{ev.event_key}:K-01/B:-"].value == "-15555.56"

    # Pricing the change is an estimate change (stage 08, ALG-10): the price moves 1,090,000.00 →
    # 1,110,000.00 when costs are 600,000.00, and the single obligation takes the whole change.
    settled = next(
        item
        for item in after.events
        if item.event_type == "ESTIMATE_CHANGED"
        and item.payload["estimate_version_id"] == agreed.version_key
    )
    before_price = price(folded.ctx, after, AGREED_DATE, settled).allocation_basis.posted
    after_price = price(folded.ctx, after, AGREED_DATE, None).allocation_basis.posted
    assert (before_price, after_price) == (usd("1090000.00"), usd("1110000.00"))
    progress = Fraction(600000, 900000)
    before = cumulative_posted(segment.x_exact, segment.a_posted, progress, 2)
    settled_x = segment.x_exact + Fraction(after_price - before_price, 100)
    settled_a = segment.a_posted + after_price - before_price
    agreed_revenue = cumulative_posted(settled_x, settled_a, progress, 2)
    assert (before, agreed_revenue, agreed_revenue - before) == (
        usd("726666.67"),
        usd("740000.00"),
        usd("13333.33"),
    )

    # A priced line beside an unpriced change order is refused (S06-R-20).
    priced = dataclasses.replace(
        change, lines=(mod_line("B", "CHANGE", "SKU-BUILD", "0", "10.00"),)
    )
    header = dataclasses.replace(folded.state.contracts[0].header, modifications=(priced,))
    refused = dataclasses.replace(
        folded.state,
        contracts=(dataclasses.replace(folded.state.contracts[0], header=header),),
    )
    with pytest.raises(ValueError, match="S06-R-20"):
        s06_modifications.apply(
            folded.ctx,
            refused,
            ev,
            TraceBuilder(engine_version=ENGINE_VERSION),
            identified=folded.identified,
            price_at=price,
        )


# --- S06-R-19 subscription commands --------------------------------------------------------------

SUBSCRIPTION_END = date(2026, 12, 31)


def subscription() -> tuple[BookContext, IdentifiedState, AllocatedState]:
    """10 seats for 12,000.00 over 2026; SSP point 1,200.00 a seat."""
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "SUB", product_code="SKU-SUB", quantity="10", total_price="12000.00"
            ),
        ),
        products=[product("SKU-SUB", "TPL-SUB")],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", "SKU-SUB", "1200.00")], date(2025, 1, 1))],
        inception=INCEPTION,
        months=36,
        modifications=[],
    )
    return inception(with_templates(value))


def line(
    key: str, action: str, quantity: str, consideration: str, start: date, end: date
) -> Mapping[str, object]:
    return {
        "action": action,
        "consideration_delta": Decimal(consideration),
        "end_date": end,
        "obligation_key": key,
        "product_code": "SKU-SUB",
        "quantity_delta": Decimal(quantity),
        "start_date": start,
    }


def view(key: str, d: date, kind: str, *lines: Mapping[str, object]) -> ModificationView:
    return ModificationView.of(CONTRACT, modification_input(key, d, lines, kind=kind))


def test_s06_r19_subscription_commands() -> None:
    ctx, identified, st = subscription()
    ob = obligation(st, "SUB")
    d, early = date(2026, 7, 1), date(2026, 10, 1)
    renewal_end = date(2027, 12, 31)
    shapes = {
        "UPGRADE": SubscriptionCommand("UPGRADE", d, Decimal("5"), Decimal("3000.00")),
        "DOWNGRADE": SubscriptionCommand("DOWNGRADE", d, Decimal("-2"), Decimal("-1200.00")),
        "CO_TERM": SubscriptionCommand(
            "CO_TERM", d, Decimal("3"), Decimal("900.00"), added_obligation_key="SUB-CT"
        ),
        "RENEWAL": SubscriptionCommand(
            "RENEWAL",
            d,
            Decimal("10"),
            Decimal("12000.00"),
            added_obligation_key="SUB-2027",
            renewal_end_date=renewal_end,
        ),
        "EARLY_RENEWAL": SubscriptionCommand(
            "EARLY_RENEWAL",
            early,
            Decimal("10"),
            Decimal("12000.00"),
            added_obligation_key="SUB-2027",
            renewal_end_date=renewal_end,
            current_term_consideration_delta=Decimal("-500.00"),
        ),
    }
    built = {kind: s06_modifications.subscription_lines(ob, cmd) for kind, cmd in shapes.items()}
    renewal = line("SUB-2027", "ADD", "10", "12000.00", date(2027, 1, 1), renewal_end)
    assert built == {
        "UPGRADE": (line("SUB", "CHANGE", "5", "3000.00", d, SUBSCRIPTION_END),),
        "DOWNGRADE": (line("SUB", "CHANGE", "-2", "-1200.00", d, SUBSCRIPTION_END),),
        "CO_TERM": (line("SUB-CT", "ADD", "3", "900.00", d, SUBSCRIPTION_END),),
        "RENEWAL": (renewal,),
        "EARLY_RENEWAL": (
            renewal,
            line("SUB", "CHANGE", "0", "-500.00", early, SUBSCRIPTION_END),
        ),
    }
    with pytest.raises(ValueError, match="S06-R-19"):
        s06_modifications.subscription_lines(
            ob, SubscriptionCommand("UPGRADE", d, Decimal("-1"), Decimal("0.00"))
        )
    with pytest.raises(ValueError, match="S06-R-19"):
        s06_modifications.subscription_lines(
            ob, SubscriptionCommand("RENEWAL", d, Decimal("10"), added_obligation_key="SUB-2027")
        )

    # Each shape is proposed through §6.2; a renewal priced at its d SSP is a separate contract.
    proposals = {
        kind: s06_modifications.propose(
            ctx,
            st,
            view(f"MOD-{kind}", early if kind == "EARLY_RENEWAL" else d, kind, *lines),
            TraceBuilder(engine_version=ENGINE_VERSION),
            identified=identified,
        )
        for kind, lines in built.items()
    }
    assert proposals["RENEWAL"].summary == ModificationTreatment.SEPARATE_CONTRACT
    assert proposals["RENEWAL"].treatments == {"SUB-2027": ModificationTreatment.SEPARATE_CONTRACT}
    # The early renewal changes the current term's price, so it is not a separate contract.
    assert proposals["EARLY_RENEWAL"].summary != ModificationTreatment.SEPARATE_CONTRACT
    # A co-term line that does not end on the original end date is out of shape.
    wrong = line("SUB-CT", "ADD", "3", "900.00", d, date(2026, 11, 30))
    with pytest.raises(ValueError, match="CO_TERM shape"):
        s06_modifications.propose(
            ctx,
            st,
            view("MOD-CT", d, "CO_TERM", wrong),
            TraceBuilder(engine_version=ENGINE_VERSION),
            identified=identified,
        )


# --- S09-R-22 (PT-02; REQ-MOD-017): renewal carrying unconsumed credits --------------------------

RENEWAL_DATE = date(2026, 12, 15)


def test_s09_r22_renewal_carries_unconsumed_credits() -> None:
    credits = bundles.booking_line(
        "CRED", product_code="SKU-CREDIT", quantity="100000", total_price="100000.00"
    )
    extension = mod_line("CRED", "CHANGE", "SKU-CREDIT", "0", "0.00", end=date(2027, 12, 31))
    renewal = modification_input("MOD-R", RENEWAL_DATE, [extension], kind="RENEWAL")
    value = bundle(
        booked(INCEPTION, credits),
        delivered(3, "CRED", "70000", date(2026, 11, 30)),  # 70,000 credits redeemed
        amended(4, renewal, {"CRED": "PROSPECTIVE"}),
        products=[product("SKU-CREDIT", "TPL-CREDITS")],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", "SKU-CREDIT", "1.00")], date(2025, 1, 1))],
        inception=INCEPTION,
        months=24,
        modifications=[renewal],
    )
    folded = fold(with_templates(value))
    ev = folded.amended
    inception_segment = obligation(folded.state, "CRED").segments[0]
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx,
        folded.state,
        ev,
        tb,
        identified=folded.identified,
        price_at=price_function("100000.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    credit = obligation(after, "CRED")
    segment = credit.segments[-1]
    assert (segment.basis, segment.x_exact, segment.a_posted) == (
        "PROSPECTIVE",
        inception_segment.x_exact,  # the same exact allocation
        inception_segment.a_posted,
    )
    assert (segment.totals.end_date, credit.end_date, credit.last_modification_key) == (
        date(2027, 12, 31),
        date(2027, 12, 31),
        "MOD-R",
    )
    catch_up = nodes[f"catch_up@{ev.event_key}:K-01/CRED:-"]
    assert (catch_up.value, catch_up.params["exact_before"]) == ("0.00", "70000")
    assert f"mod_share@{ev.event_key}:K-01/CRED:-" not in nodes  # no pool share

    # The renewal's own consideration is booked as its own contract with lineage to the source.
    header = dataclasses.replace(
        bundles.contract("K-02", inception=date(2027, 1, 1)), renewal_of_contract_key=CONTRACT
    )
    renewal_line = bundles.booking_line(
        "CRED-2027",
        product_code="SKU-CREDIT",
        quantity="20000",
        total_price="20000.00",
        start=date(2027, 1, 1),
        end=date(2027, 12, 31),
    )
    events = (
        bundles.event("K-02", 1, "CONTRACT_BOOKED", date(2027, 1, 1), {"lines": [renewal_line]}),
        bundles.event("K-02", 2, "CONTRACT_ACTIVATED", date(2027, 1, 1), {"checklist": {}}),
    )
    calendar = bundles.entity(start=date(2027, 1, 1), months=12)
    booked_renewal = dataclasses.replace(
        with_templates(value),
        known_at=KNOWN_AT,
        books=(bundles.book("ASC606", preset="DEFAULT", entity=calendar),),
        entities=(calendar,),
        group=bundles.group(
            (header,), group_key="CG-2", products=[product("SKU-CREDIT", "TPL-CREDITS")]
        ),
        contracts=(header,),
        events=events,
        estimate_versions=(),
    )
    _, _, renewed = inception(booked_renewal)
    assert renewed.contracts[0].header.renewal_of_contract_key == CONTRACT
    assert obligation(renewed, "CRED-2027").segments[0].a_posted == usd("20000.00")


# --- S06-R-22 negative allocation ----------------------------------------------------------------


def test_s06_r22_negative_allocation() -> None:
    reduction = mod_line("POB-01", "CHANGE", "SKU-P", "0", "-12500.00")
    modification = modification_input("MOD-22", date(2026, 6, 15), [reduction], kind="PRICE_CHANGE")
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "POB-01", product_code="SKU-P", quantity="120", total_price="12000.00"
            ),
        ),
        amended(3, modification, {"POB-01": "PROSPECTIVE"}),
        products=[product("SKU-P", "TPL-UNITS")],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", "SKU-P", "100.00")], date(2025, 1, 1))],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
    )
    folded = fold(value)
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx,
        folded.state,
        ev,
        tb,
        identified=folded.identified,
        price_at=price_function("12000.00"),
    )
    # Pool = 12,000.00 − 12,500.00: the obligation's total allocation would be −500.00.
    assert [(f.code, f.severity, f.subject_key, f.stage, f.event_key) for f in after.findings] == [
        ("VC_ALLOCATION_NEGATIVE", "ERROR", "K-01/POB-01", 6, ev.event_key)
    ]
    assert after.findings[0].detail["allocation"] == "-500"
    assert after.obligations == folded.state.obligations  # no segment is added (CV-15)
    assert tb.build(root_measures={}).nodes == ()
