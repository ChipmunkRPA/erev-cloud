"""Stage 06 native prospective modification (ENGINE_SPEC §6.3 S06-R-06 to S06-R-18; ENB-2).

The inception state comes from the real stages 01 to 05 over bundles built with
``support.bundles``. Stage 04 ``price_at`` takes a ``PobState`` and reads no modification lines, and
the orchestrator binds the price function in ENB-13, so the tests bind a fake that follows the
§4.2 contract (D-81 integration after merge). Every stage 06 trace re-evaluates node for node
(DG-ENG-04). No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    ModificationInput,
    ProductInput,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.money import decimal_to_minor, largest_remainder
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
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    ObligationState,
    PolicyResolver,
    Quota1,
    SegmentCause,
    TpBuildUp,
)
from erev_engine.trace import TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.recognition import period_amounts, targets_by_period

CONTRACT = "K-01"
ZERO_SHA = "0" * 64
KNOWN_AT = datetime(2029, 12, 31, 23, tzinfo=UTC)


def usd(amount: str) -> int:
    """USD minor units of a plain decimal string."""
    return decimal_to_minor(Decimal(amount), 2)


def template(
    code: str,
    *,
    method: str,
    pattern: str,
    convention: str | None = None,
    distinctness: str = "distinct",
    series_increment_unit: str = "month",
) -> TemplateInput:
    """A template version; ``series_increment_unit`` applies to ``series`` templates only."""
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        obligation_kind="STANDARD",
        distinctness=distinctness,
        series_increment_unit=series_increment_unit if distinctness == "series" else None,
        satisfaction_pattern=pattern,
        over_time_criterion="OT_A" if pattern == "OVER_TIME" else "NOT_APPLICABLE",
        recognition_method=method,
        ratable_convention=convention,
        start_date_rule="LINE_START",
        end_date_rule="LINE_END",
        term_months=None,
        principal_agent="PRINCIPAL",
        warranty_type="NONE",
        licence_nature="NOT_APPLICABLE",
        sfc_assessment_required=False,
        revenue_category=None,
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )


TEMPLATES = (  # template code order (§0.4)
    template("TPL-C2C", method="COST_TO_COST", pattern="OVER_TIME"),
    # PRD K-02 O1 is a series with increment day (TPL-SUB-DAILY); its mod-date SSP prices the
    # remaining increments, so S06-R-11 does not scale it (D-90b).
    template(
        "TPL-SAAS",
        method="TIME_ELAPSED",
        pattern="OVER_TIME",
        convention="DAILY",
        distinctness="series",
        series_increment_unit="day",
    ),
    template("TPL-SER", method="UNITS_DELIVERED", pattern="OVER_TIME", distinctness="series"),
    template("TPL-UNITS", method="UNITS_DELIVERED", pattern="POINT_IN_TIME"),
)


def product(code: str, template_code: str) -> ProductInput:
    return bundles.product(code, template_code=template_code, family=None)


def point_entry(version_key: str, product_code: str, point: str) -> SspEntryInput:
    """An observable point per unit in USD (T-REF-31)."""
    return SspEntryInput(
        entry_key=f"{version_key}/{product_code}//-/USD",
        product_code=product_code,
        stratification="",
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="USD",
        method="observable",
        value_basis="AMOUNT",
        unit_list_price=None,
        midpoint_discount_ratio=None,
        range_ratio=None,
        cost_basis=None,
        margin_ratio=None,
        distinctness="distinct",
        revenue_account_code=None,
        observable_point=None,
        ranges=(SspRangeInput("NONE", None, None, Decimal(point), None, None, None),),
    )


def ssp_version(
    number: int,
    entries: Iterable[SspEntryInput],
    effective_from: date,
    effective_to: date | None = None,
) -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key=f"SSP-US@v{number}",
        version_no=number,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=effective_from,
        effective_to_date=effective_to,
        status="APPROVED",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        content_sha256=ZERO_SHA,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda entry: entry.product_code)),
    )


def bundle(
    *events: EventInput,
    products: Sequence[ProductInput],
    ssp: Sequence[SspVersionInput],
    inception: date,
    months: int,
    modifications: Sequence[ModificationInput],
    overrides: Mapping[str, str] | None = None,
    estimate_versions: Sequence[EstimateVersionInput] = (),
) -> InputBundle:
    calendar = bundles.entity(start=inception, months=months)
    header = dataclasses.replace(
        bundles.contract(CONTRACT, inception=inception), modifications=tuple(modifications)
    )
    book: BookInput = bundles.book("ASC606", preset="DEFAULT", entity=calendar)
    if overrides:
        policies = tuple(
            dataclasses.replace(policy, value=overrides[policy.code])
            if policy.code in overrides and policy.scope == "GROUP"
            else policy
            for policy in book.policies
        )
        book = dataclasses.replace(book, policies=policies)
    activated = bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", inception, {"checklist": {}})
    events = (*events, activated)  # stream version 2: ACTIVE from inception (S02-R-01)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=tuple(ssp),
        pob_template_versions=TEMPLATES,
        rule_set_versions=(),
        estimate_versions=tuple(
            sorted(estimate_versions, key=lambda v: (v.estimate_key, v.version_no))
        ),
        fx_rates=(),
        posted=(),
    )


def context(value: InputBundle) -> BookContext:
    book = value.books[0]
    return BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in value.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


@dataclasses.dataclass(frozen=True)
class Folded:
    """The inception fold of stages 01 to 05 and the amendment to apply."""

    ctx: BookContext
    identified: IdentifiedState
    state: AllocatedState
    amended: EventView


def fold(value: InputBundle) -> Folded:
    ctx = context(value)
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(value, scratch)
    identified = s02_contract_identification.run(ctx, cb, scratch)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, scratch), scratch)
    st = s05_allocation.run(ctx, priced, scratch)
    assert st.findings == ()
    (amended,) = [ev for ev in cb.boundary_events if ev.event_type == "CONTRACT_AMENDED"]
    return Folded(ctx, identified, st, amended)


def booked(on: date, *lines: Mapping[str, object]) -> EventInput:
    keys = [str(line["obligation_key"]) for line in lines]
    payload = {"lines": list(lines)}
    return bundles.event(CONTRACT, 1, "CONTRACT_BOOKED", on, payload, obligation_keys=keys)


def delivered(stream: int, key: str, quantity: str, on: date) -> EventInput:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return bundles.event(CONTRACT, stream, "DELIVERY_RECORDED", on, payload, obligation_keys=[key])


def mod_line(
    key: str,
    action: str,
    product_code: str,
    quantity: str,
    consideration: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, object]:
    members: dict[str, object] = {
        "obligation_key": key,
        "action": action,
        "product_code": product_code,
        "quantity_delta": Decimal(quantity),
        "consideration_delta": Decimal(consideration),
    }
    if start is not None:
        members["start_date"] = start
    if end is not None:
        members["end_date"] = end
    return members


def modification_input(
    key: str,
    effective: date,
    lines: Sequence[Mapping[str, object]],
    *,
    kind: str,
    questionnaire: Mapping[str, object] | None = None,
    price_change_amount: str | None = None,
) -> ModificationInput:
    return ModificationInput(
        modification_key=key,
        effective_date=effective,
        kind=kind,
        template_mode=None,
        status="APPLIED",
        reference=None,
        questionnaire=dict(questionnaire or {}),
        lines=tuple(lines),
        price_change_amount=None if price_change_amount is None else Decimal(price_change_amount),
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )


def amended(
    stream: int, modification: ModificationInput, treatments: Mapping[str, str]
) -> EventInput:
    payload = {
        "modification_id": modification.modification_key,
        "treatments": dict(treatments),
        "lines": list(modification.lines),
        "ssp_basis": {},
    }
    keys = sorted({str(line["obligation_key"]) for line in modification.lines})
    return bundles.event(
        CONTRACT,
        stream,
        "CONTRACT_AMENDED",
        modification.effective_date,
        payload,
        obligation_keys=keys,
    )


def price_function(
    booked_price: str, *, includable: str = "0.00", drift: int = 0
) -> s06_modifications.PriceAt:
    """A fake stage 04 ``price_at`` (ENGINE_SPEC §4.2; D-81), minor units.

    The allocation basis is the booked price plus the consideration of every ``CONTRACT_AMENDED``
    before the position, plus ``includable`` VC that each such modification makes includable
    (S06-R-12 ΔVC), plus ``drift`` at every position.
    """

    def price(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        total = usd(booked_price) + drift
        for ev in st.events:
            if ev.event_type != "CONTRACT_AMENDED" or ev.effective_date > at:
                continue
            if before is not None and ev.order_key >= before.order_key:
                continue
            lines = ev.payload["lines"]
            assert isinstance(lines, Sequence)
            for line in lines:
                assert isinstance(line, Mapping)
                amount = line["consideration_delta"]
                assert isinstance(amount, Fraction)
                total += int(amount * 100)
            total += usd(includable)
        quota = Quota1(Fraction(total, 100), total)
        zero = Quota1(Fraction(0), 0)
        key = None if before is None else before.event_key
        return TpBuildUp(at, key, quota, *(zero,) * 8, quota, quota, ())

    return price


def checked(tb: TraceBuilder) -> dict[str, TraceNode]:
    """The trace nodes by id, after checking that re-evaluation reproduces every node."""
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return {node.id: node for node in trace.nodes}


def obligation(st: AllocatedState, key: str) -> ObligationState:
    return next(ob for ob in st.obligations if ob.obligation_key == key)


# --- EX-09-A (ENGINE_SPEC_B §9.7; K-02) ---------------------------------------------------------

INCEPTION = date(2026, 1, 1)
END = date(2027, 12, 31)
MOD_DATE = date(2026, 9, 16)


def ex_09_a(*, satisfied: bool = False) -> InputBundle:
    """O1 240,000.00 DAILY over 2026 and 2027; O2 added on 16 Sep 2026 for 60,000.00.

    O1 and O2 are series with increment day (PRD K-02 O1, TPL-SUB-DAILY), so the mod-date SSPs
    155,000 and 77,500 (SSP-US v2) price the remaining increments and S06-R-11 weighs them
    unscaled (D-90b). With ``satisfied`` a hardware obligation of 10,000.00 delivered in January is
    booked as well, and takes no treatment (class S).
    """
    lines = [
        bundles.booking_line(
            "POB-01", product_code="SKU-SAAS", quantity="1", total_price="240000.00", end=END
        )
    ]
    events: list[EventInput] = []
    products = [product("SKU-SAAS", "TPL-SAAS"), product("SKU-SEATS", "TPL-SAAS")]
    inception_entries = [point_entry("SSP-US@v1", "SKU-SAAS", "240000.00")]
    if satisfied:
        lines.append(
            bundles.booking_line(
                "POB-HW",
                product_code="SKU-HW",
                quantity="1",
                total_price="10000.00",
                end=date(2026, 1, 31),
            )
        )
        events.append(delivered(3, "POB-HW", "1", date(2026, 1, 31)))
        products.append(product("SKU-HW", "TPL-UNITS"))
        inception_entries.append(point_entry("SSP-US@v1", "SKU-HW", "10000.00"))
    addon = mod_line("POB-02", "ADD", "SKU-SEATS", "1", "60000.00", start=MOD_DATE, end=END)
    modification = modification_input("MOD-1", MOD_DATE, [addon], kind="ADD_OBLIGATION")
    treatments = {"POB-01": "PROSPECTIVE", "POB-02": "PROSPECTIVE"}
    mod_entries = [
        point_entry("SSP-US@v2", "SKU-SAAS", "155000.00"),
        point_entry("SSP-US@v2", "SKU-SEATS", "77500.00"),
    ]
    return bundle(
        booked(INCEPTION, *lines),
        *events,
        amended(4, modification, treatments),
        products=products,
        ssp=[
            ssp_version(1, inception_entries, date(2025, 1, 1), date(2026, 8, 31)),
            ssp_version(2, mod_entries, date(2026, 9, 1)),
        ],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
    )


def test_ex_09_a_pool_and_shares() -> None:
    folded = fold(ex_09_a())
    ctx, st, ev = folded.ctx, folded.state, folded.amended
    (o1_before,) = st.obligations
    assert (o1_before.segments[0].x_exact, o1_before.segments[0].a_posted) == (
        240000,
        usd("240000.00"),
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        ctx, st, ev, tb, identified=folded.identified, price_at=price_function("240000.00")
    )
    assert after.findings == ()
    nodes = checked(tb)
    pool = nodes[f"mod_pool@{ev.event_key}:K-01:-"]
    assert (pool.formula_id, pool.value) == ("mod.pool.remaining_tp.v1", "215178.08")
    # R_k = C(15 Sep 2026) = round(240,000 × 258 ÷ 730): the remaining term starts on 16 Sep.
    assert (pool.params["allocations"], pool.params["revenue"]) == (
        str(usd("240000.00")),
        str(usd("84821.92")),
    )
    weight = {key: nodes[f"mod_weight@{ev.event_key}:K-01/{key}:-"] for key in ("POB-01", "POB-02")}
    assert {key: node.value for key, node in weight.items()} == {
        "POB-01": "155000",
        "POB-02": "77500",
    }
    assert weight["POB-01"].formula_id == "mod.weights.d18.v1"
    assert weight["POB-01"].params["class"] == "D"
    share = {key: nodes[f"mod_share@{ev.event_key}:K-01/{key}:-"] for key in ("POB-01", "POB-02")}
    assert (share["POB-01"].value, share["POB-02"].value) == ("143452.05", "71726.03")
    exact_o1 = Fraction(usd("215178.08"), 100) * 155000 / 232500  # 143,452.0533…
    exact_o2 = Fraction(usd("215178.08"), 100) * 77500 / 232500  # 71,726.0266…
    # The remaining minor unit goes to O2, whose fractional remainder is the larger.
    floors = [int(exact_o1 * 100), int(exact_o2 * 100)]
    assert floors == [usd("143452.05"), usd("71726.02")]
    assert largest_remainder(
        usd("215178.08"), [Fraction(155000), Fraction(77500)], ["K-01/POB-01", "K-01/POB-02"]
    ) == [usd("143452.05"), usd("71726.03")]

    o1 = obligation(after, "POB-01")
    boundary = o1.segments[-1]
    assert len(o1.segments) == 2
    assert (boundary.cause, boundary.basis, boundary.effective_date, boundary.event_key) == (
        SegmentCause.MODIFICATION,
        "PROSPECTIVE",
        MOD_DATE,
        ev.event_key,
    )
    assert (boundary.base_revenue_posted, boundary.base_revenue_exact) == (
        usd("84821.92"),
        Fraction(usd("84821.92"), 100),
    )
    assert (boundary.x_exact, boundary.a_posted) == (
        Fraction(usd("84821.92"), 100) + exact_o1,
        usd("228273.97"),
    )
    assert (boundary.remaining_ssp, boundary.totals.end_date) == (155000, END)
    (o2_segment,) = obligation(after, "POB-02").segments
    assert (o2_segment.basis, o2_segment.x_exact, o2_segment.a_posted) == (
        "PROSPECTIVE",
        exact_o2,
        usd("71726.03"),
    )
    assert o2_segment.base_revenue_posted == 0
    for key in ("POB-01", "POB-02"):
        catch_up = nodes[f"catch_up@{ev.event_key}:K-01/{key}:-"]
        assert (catch_up.formula_id, catch_up.value, catch_up.params["cause"]) == (
            "mod.catch_up.v1",
            "0.00",
            "MODIFICATION",
        )  # S06-INV-02: no catch-up at the boundary
    assert nodes[f"catch_up@{ev.event_key}:K-01/POB-01:-"].params["measured_on"] == "2026-09-15"

    # Stage 09 over the state after the boundary gives the EX-09-A period amounts.
    state = s09_recognition.run(ctx, after, TraceBuilder(engine_version=ENGINE_VERSION))
    o1_amounts = period_amounts(targets_by_period(state, "K-01/POB-01"))
    o2_amounts = period_amounts(targets_by_period(state, "K-01/POB-02"))
    assert (o1_amounts["FY2026-P09"], o2_amounts["FY2026-P09"]) == (usd("9490.37"), usd("2279.43"))
    assert o1_amounts["FY2026-P10"] + o2_amounts["FY2026-P10"] == usd("14132.46")


def recorded(
    value: InputBundle,
    own: Mapping[str, str],
    weights: Mapping[tuple[str, str], str] | None = None,
) -> InputBundle:
    """``value`` with the orchestrator's read-back rows (S05-R-03): per obligation key the key of
    the version recorded for its own pricing (``own``), and per (obligation key, event key) the
    version recorded for its weight in that modification event (``weights``)."""
    book = value.books[0]
    members: dict[str, dict[str, str]] = {
        key: {"recorded": version} for key, version in own.items()
    }
    for (key, event_key), version in (weights or {}).items():
        members.setdefault(key, {})[f"recorded@{event_key}"] = version
    rows = tuple(
        ResolvedPolicyInput(
            "ssp.version_basis",
            "OBLIGATION",
            f"{CONTRACT}/{key}",
            dict(sorted(member.items())),
            "O",
            member.get("recorded", ""),
            "K",
        )
        for key, member in members.items()
    )
    policies = tuple(
        sorted((*book.policies, *rows), key=lambda p: (p.code, p.scope, p.subject_key))
    )
    return dataclasses.replace(value, books=(dataclasses.replace(book, policies=policies),))


def test_s06_r11_recorded_versions_and_the_weights_of_a_modification() -> None:
    """S05-R-03 and S06-R-11 (01-DECISIONS D-18): a recorded version prices what it was recorded
    for and nothing else. EX-09-A with a third version in force from 1 September: by date it
    prices both weights of the modification of 16 September, 160,000 and 90,000.

    With the records of the obligations' OWN pricings — POB-01 from version 1 at its booking,
    POB-02 from version 2 in the event that added it — and none for the event, as at the event's
    first computation, POB-01's remaining increments are weighed at the modification date from
    the version in force then (160,000), and POB-02, priced for itself, keeps the version it was
    added under (77,500).

    With the record of the event as well — POB-01's weight was priced from version 2 when the
    modification was computed — the weight is priced from version 2 again (155,000): a version
    approved later does not weigh an applied modification a second time."""
    third = ssp_version(
        3,
        [
            point_entry("SSP-US@v3", "SKU-SAAS", "160000.00"),
            point_entry("SSP-US@v3", "SKU-SEATS", "90000.00"),
        ],
        date(2026, 9, 1),
    )
    base = ex_09_a()
    by_date = dataclasses.replace(base, ssp_versions=(*base.ssp_versions, third))

    def weights(value: InputBundle) -> dict[str, tuple[str, str]]:
        folded = fold(value)
        (booked_first,) = folded.state.obligations
        assert booked_first.ssp is not None and booked_first.ssp.version_key == "SSP-US@v1"
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        after = s06_modifications.apply(
            folded.ctx,
            folded.state,
            folded.amended,
            tb,
            identified=folded.identified,
            price_at=price_function("240000.00"),
        )
        assert after.findings == ()
        nodes = checked(tb)
        found = {}
        for key in ("POB-01", "POB-02"):
            node = nodes[f"mod_weight@{folded.amended.event_key}:K-01/{key}:-"]
            (source,) = [item for item in node.inputs if not isinstance(item, str)]
            found[key] = (node.value, source.ref_id.split("/")[0])
        return found

    assert weights(by_date) == {
        "POB-01": ("160000", "SSP-US@v3"),
        "POB-02": ("90000", "SSP-US@v3"),
    }
    own = {"POB-01": "SSP-US@v1", "POB-02": "SSP-US@v2"}
    assert weights(recorded(by_date, own)) == {
        "POB-01": ("160000", "SSP-US@v3"),
        "POB-02": ("77500", "SSP-US@v2"),
    }
    event_key = fold(by_date).amended.event_key
    assert weights(recorded(by_date, own, {("POB-01", event_key): "SSP-US@v2"})) == {
        "POB-01": ("155000", "SSP-US@v2"),
        "POB-02": ("77500", "SSP-US@v2"),
    }
    # The record of the event alone: the booking pricing has none and selects by date.
    assert weights(recorded(by_date, {}, {("POB-01", event_key): "SSP-US@v2"})) == {
        "POB-01": ("155000", "SSP-US@v2"),
        "POB-02": ("90000", "SSP-US@v3"),
    }


def test_chk_043_series_prospective() -> None:
    """FASB Example 7: Year 3 remaining at 100,000.00; the fee drops 20,000.00; 3 years added."""
    inception, d, end = date(2024, 1, 1), date(2026, 1, 1), date(2026, 12, 31)
    service = bundles.booking_line(
        "SVC",
        product_code="SKU-YEAR",
        quantity="3",
        total_price="300000.00",
        start=inception,
        end=end,
    )
    reduction = mod_line("SVC", "CHANGE", "SKU-YEAR", "0", "-20000.00")
    years = [
        mod_line(
            f"YEAR-{number}",
            "ADD",
            "SKU-YEAR",
            "1",
            price,
            start=date(2023 + number, 1, 1),
            end=date(2023 + number, 12, 31),
        )
        for number, price in ((4, "66667.00"), (5, "66667.00"), (6, "66666.00"))
    ]
    modification = modification_input("MOD-43", d, [reduction, *years], kind="ADD_OBLIGATION")
    treatments = {key: "PROSPECTIVE" for key in ("SVC", "YEAR-4", "YEAR-5", "YEAR-6")}
    value = bundle(
        booked(inception, service),
        delivered(3, "SVC", "1", date(2024, 12, 31)),
        delivered(4, "SVC", "1", date(2025, 12, 31)),
        amended(5, modification, treatments),
        products=[product("SKU-YEAR", "TPL-SER")],
        ssp=[
            ssp_version(
                1,
                [point_entry("SSP-US@v1", "SKU-YEAR", "100000.00")],
                date(2023, 1, 1),
                date(2025, 12, 31),
            ),
            ssp_version(2, [point_entry("SSP-US@v2", "SKU-YEAR", "80000.00")], d),
        ],
        inception=inception,
        months=72,
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
        price_at=price_function("300000.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    assert nodes[f"mod_pool@{ev.event_key}:K-01:-"].value == "280000.00"
    keys = ("SVC", "YEAR-4", "YEAR-5", "YEAR-6")
    weights = {key: nodes[f"mod_weight@{ev.event_key}:K-01/{key}:-"].value for key in keys}
    assert weights == dict.fromkeys(keys, "80000")  # four equal weights
    shares = {key: nodes[f"mod_share@{ev.event_key}:K-01/{key}:-"].value for key in keys}
    assert shares == dict.fromkeys(keys, "70000.00")  # 70,000.00 a year
    service_after = obligation(after, "SVC").segments[-1]
    assert (service_after.base_revenue_posted, service_after.a_posted) == (
        usd("200000.00"),
        usd("270000.00"),
    )
    assert service_after.totals.quantity == 1  # RQ = 3 − 2 + 0
    for key in keys[1:]:
        (segment,) = obligation(after, key).segments
        assert (segment.basis, segment.a_posted, segment.x_exact) == (
            "PROSPECTIVE",
            usd("70000.00"),
            70000,
        )


def chk_028(*lines: Mapping[str, object], after_units: bool = False) -> InputBundle:
    """120 products at 100.00, 60 transferred by 31 May 2026; mod-date SSP point 95.00."""
    d = date(2026, 6, 15)
    modification = modification_input("MOD-28", d, lines, kind="QUANTITY_CHANGE")
    later = (
        [
            delivered(5, "POB-01", "1", date(2026, 6, 20)),
            delivered(6, "POB-01", "1", date(2026, 7, 20)),
            delivered(7, "POB-01", "1", date(2026, 8, 20)),
        ]
        if after_units
        else []
    )
    return bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "POB-01", product_code="SKU-P", quantity="120", total_price="12000.00"
            ),
        ),
        delivered(3, "POB-01", "60", date(2026, 5, 31)),
        amended(4, modification, {"POB-01": "PROSPECTIVE"}),
        *later,
        products=[product("SKU-P", "TPL-UNITS")],
        ssp=[
            ssp_version(
                1,
                [point_entry("SSP-US@v1", "SKU-P", "100.00")],
                date(2025, 1, 1),
                date(2026, 5, 31),
            ),
            ssp_version(2, [point_entry("SSP-US@v2", "SKU-P", "95.00")], date(2026, 6, 1)),
        ],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
    )


def test_chk_028_pool_over_remaining_and_added_units() -> None:
    folded = fold(chk_028(mod_line("POB-01", "CHANGE", "SKU-P", "30", "2400.00"), after_units=True))
    ctx, ev = folded.ctx, folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        ctx, folded.state, ev, tb, identified=folded.identified, price_at=price_function("12000.00")
    )
    assert after.findings == ()
    (ob,) = after.obligations
    segment = ob.segments[-1]
    assert (segment.basis, segment.totals.quantity, segment.base_progress.delivered_cum) == (
        "PROSPECTIVE",
        90,
        60,
    )
    assert (segment.base_revenue_posted, segment.a_posted, segment.x_exact) == (
        usd("6000.00"),
        usd("14400.00"),
        14400,
    )
    assert (ob.quantity, ob.stated_price) == (150, 14400)
    # Stage 09 in the same trace: units 93.33 / 93.34 / 93.33 over the 90 remaining units, and
    # the whole trace, stage 06 and stage 09 nodes together, re-evaluates node for node.
    state = s09_recognition.run(ctx, after, tb)
    nodes = checked(tb)
    assert nodes[f"mod_pool@{ev.event_key}:K-01:-"].value == "8400.00"
    weight = nodes[f"mod_weight@{ev.event_key}:K-01/POB-01:-"]
    assert (weight.value, weight.params["parts"], weight.params["remaining_quantity"]) == (
        "8550",
        "5700|2850",
        "60",
    )
    assert nodes[f"catch_up@{ev.event_key}:K-01/POB-01:-"].value == "0.00"
    amounts = period_amounts(targets_by_period(state, "K-01/POB-01"))
    assert (amounts["FY2026-P06"], amounts["FY2026-P07"], amounts["FY2026-P08"]) == (
        usd("93.33"),
        usd("93.34"),
        usd("93.33"),
    )


def test_s06_r08_remaining_negative() -> None:
    folded = fold(chk_028(mod_line("POB-01", "REMOVE", "SKU-P", "-70", "-7000.00")))
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
    assert [(f.code, f.severity, f.subject_key, f.stage, f.event_key) for f in after.findings] == [
        ("MOD_REMAINING_NEGATIVE", "ERROR", "K-01/POB-01", 6, ev.event_key)
    ]
    assert after.findings[0].detail["remaining_quantity"] == "-10"
    assert after.obligations == folded.state.obligations  # no segment is added (CV-15)
    assert tb.build(root_measures={}).nodes == ()


def test_s06_r16_every_obligation_versioned_with_lineage() -> None:
    folded = fold(ex_09_a(satisfied=True))
    st, ev = folded.state, folded.amended
    after = s06_modifications.apply(
        folded.ctx,
        st,
        ev,
        TraceBuilder(engine_version=ENGINE_VERSION),
        identified=folded.identified,
        price_at=price_function("250000.00"),
    )
    assert after.findings == ()
    assert [ob.obligation_key for ob in after.obligations] == ["POB-01", "POB-02", "POB-HW"]
    assert all(ob.last_modification_key == "MOD-1" for ob in after.obligations)
    o1, o2, hardware = after.obligations
    assert [seg.event_key for seg in o1.segments] == [None, ev.event_key]
    assert [seg.event_key for seg in o2.segments] == [ev.event_key]
    assert "K-01/POB-01" in o2.lineage_pre_modification
    assert o2.lineage_pre_modification == ("K-01/POB-01", "K-01/POB-HW")
    assert (o1.segments[-1].modification_boundary_no, o2.segments[0].modification_boundary_no) == (
        1,
        1,
    )
    # The satisfied hardware keeps X and A (S06-INV-03) and records the modification.
    assert hardware.segments == obligation(st, "POB-HW").segments
    assert o1.segments[-1].a_posted == usd("228273.97")


def test_s06_inv_01_and_inv_04() -> None:
    folded = fold(ex_09_a())
    ctx, st, ev = folded.ctx, folded.state, folded.amended
    x_before = st.obligations[0].segments[0].x_exact

    after = s06_modifications.apply(
        ctx,
        st,
        ev,
        TraceBuilder(engine_version=ENGINE_VERSION),
        identified=folded.identified,
        price_at=price_function("240000.00"),
    )
    basis = after.tp_history[-1].allocation_basis.posted
    assert basis == usd("300000.00")
    assert sum(ob.segments[-1].a_posted for ob in after.obligations) == basis  # S06-INV-01
    o1, o2 = after.obligations
    moved = (o1.segments[-1].x_exact - x_before) + o2.segments[0].x_exact
    assert moved == 60000  # S06-INV-04: Σ (x′ − x) = Σ ΔC + ΔVC with ΔVC 0

    # VC made includable by the modification (ΔVC 5,000.00) joins the pool.
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    with_vc = s06_modifications.apply(
        ctx,
        st,
        ev,
        tb,
        identified=folded.identified,
        price_at=price_function("240000.00", includable="5000.00"),
    )
    pool = checked(tb)[f"mod_pool@{ev.event_key}:K-01:-"]
    assert (pool.value, pool.params["vc_delta"], pool.params["consideration"]) == (
        "220178.08",
        str(usd("5000.00")),
        str(usd("60000.00")),
    )
    o1, o2 = with_vc.obligations
    assert (o1.segments[-1].x_exact - x_before) + o2.segments[0].x_exact == 65000
    assert sum(ob.segments[-1].a_posted for ob in with_vc.obligations) == usd("305000.00")

    # A price function one minor unit away from the allocations fails closed.
    with pytest.raises(EngineError) as raised:
        s06_modifications.apply(
            ctx,
            st,
            ev,
            TraceBuilder(engine_version=ENGINE_VERSION),
            identified=folded.identified,
            price_at=price_function("240000.00", drift=1),
        )
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["invariant"] == "S06-INV-01"
