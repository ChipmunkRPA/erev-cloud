"""Stage 06 material-right exercise, expiry, attribute changes and regrouping.

ENGINE_SPEC §6.4 S06-R-23 to S06-R-27, §6.7 EX-06-E; POLICIES ALG-05 §2.6.1 to §2.6.5 (CHK-050),
POL-028, POL-212; D-21, D-21a; legacy 03 §5.4, §7.3 TC-04; ENB-5. The inception state comes from
the real stages 01 to 05, and the tests bind a fake stage 04 price function (D-81). TC-04 needs
the state after golden step 12, the legacy retrospective template of ENB-6, so the test builds the
template segments of S06-R-29 from the golden ``contract_live.csv`` of step 12 (L2-3-Q-24). Every
stage 06 trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import csv
import dataclasses
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EventInput, InputBundle, MaterialRightInput
from erev_engine.canonical import sha256_hex
from erev_engine.money import largest_remainder, round_half_up
from erev_engine.stages import s06_modifications
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    ProgressBase,
    ProgressTotals,
    Quota1,
    SegmentCause,
    TpBuildUp,
)
from erev_engine.trace import TraceBuilder
from support import bundles, golden_streams
from test_s06_lifecycle import fold_at, inception
from test_s06_prospective import (
    CONTRACT,
    INCEPTION,
    TEMPLATES,
    booked,
    bundle,
    checked,
    delivered,
    obligation,
    point_entry,
    product,
    ssp_version,
    template,
    usd,
)

OPTION_DATE = date(2026, 6, 15)
OPTION_TEMPLATE = dataclasses.replace(
    template("TPL-MR", method="UNITS_DELIVERED", pattern="POINT_IN_TIME"),
    obligation_kind="MATERIAL_RIGHT",
)


def price_function(booked_price: str) -> s06_modifications.PriceAt:
    """A fake stage 04 ``price_at`` (ENGINE_SPEC §4.2; D-81), minor units: the booked price plus the
    consideration of every ``CONTRACT_AMENDED`` and the ``additional_consideration`` of every
    ``MATERIAL_RIGHT_EXERCISED`` before the position."""

    def price(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        total = usd(booked_price)
        for ev in st.events:
            if ev.effective_date > at or (before is not None and ev.order_key >= before.order_key):
                continue
            if ev.event_type == "MATERIAL_RIGHT_EXERCISED":
                amount = ev.payload["additional_consideration"]
                assert isinstance(amount, Fraction)
                total += int(amount * 100)
            elif ev.event_type == "CONTRACT_AMENDED":
                lines = ev.payload["lines"]
                assert isinstance(lines, tuple | list)
                for line in lines:
                    assert isinstance(line, Mapping)
                    delta = line["consideration_delta"]
                    assert isinstance(delta, Fraction)
                    total += int(delta * 100)
        quota = Quota1(Fraction(total, 100), total)
        zero = Quota1(Fraction(0), 0)
        key = None if before is None else before.event_key
        return TpBuildUp(at, key, quota, *(zero,) * 8, quota, quota, ())

    return price


# --- EX-06-E (CHK-050; ALG-05) -------------------------------------------------------------------


def ex_06_e(*, overrides: Mapping[str, str] | None = None, expired: bool = False) -> InputBundle:
    """TP 1,000.00: P1 (SSP 900, delivered), P2 (SSP 200, unstarted), option MR (SSP 100).

    The option is exercised on 15 Jun 2026 for P3 at 300.00 (SSP 400; P2's d SSP 200), or, with
    ``expired``, it expires on 31 Dec 2026.
    """
    lines = [
        bundles.booking_line("P1", product_code="SKU-P1", total_price="750.00"),
        bundles.booking_line("P2", product_code="SKU-P2", total_price="166.67"),
        bundles.booking_line("MR", product_code="SKU-MR", total_price="83.33"),
    ]
    if expired:
        payload: dict[str, object] = {"obligation_key": "MR"}
        option_event = bundles.event(
            CONTRACT,
            4,
            "MATERIAL_RIGHT_EXPIRED",
            date(2026, 12, 31),
            payload,
            obligation_keys=["MR"],
        )
    else:
        payload = {
            "obligation_key": "MR",
            "exercised_quantity": Decimal("1"),
            "additional_consideration": Decimal("300.00"),
            "new_lines": [
                bundles.booking_line(
                    "P3", product_code="SKU-P3", total_price="300.00", start=OPTION_DATE
                )
            ],
        }
        option_event = bundles.event(
            CONTRACT,
            4,
            "MATERIAL_RIGHT_EXERCISED",
            OPTION_DATE,
            payload,
            obligation_keys=["MR", "P3"],
        )
    value = bundle(
        booked(INCEPTION, *lines),
        delivered(3, "P1", "1", date(2026, 2, 28)),
        option_event,
        products=[
            product("SKU-MR", "TPL-MR"),
            product("SKU-P1", "TPL-UNITS"),
            product("SKU-P2", "TPL-UNITS"),
            product("SKU-P3", "TPL-UNITS"),
        ],
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "SKU-MR", "100.00"),
                    point_entry("SSP-US@v1", "SKU-P1", "900.00"),
                    point_entry("SSP-US@v1", "SKU-P2", "200.00"),
                ],
                date(2025, 1, 1),
                date(2026, 5, 31),
            ),
            ssp_version(
                2,
                [
                    point_entry("SSP-US@v2", "SKU-P2", "200.00"),
                    point_entry("SSP-US@v2", "SKU-P3", "400.00"),
                ],
                date(2026, 6, 1),
            ),
        ],
        inception=INCEPTION,
        months=24,
        modifications=[],
        overrides=overrides,
    )
    terms = MaterialRightInput(
        obligation_key="MR",
        option_type="VOUCHER",
        incremental_discount_ratio=None,
        is_discount_available_without_contract=False,
        expected_purchase_amount=None,
        currency="USD",
        ssp_method="ENTERED_AMOUNT",
        expiry_date=date(2026, 12, 31),
        likelihood_estimate_key=None,
        is_legacy_quantity_ssp_dollars=False,
    )
    header = dataclasses.replace(value.contracts[0], material_rights=(terms,))
    templates = sorted((*TEMPLATES, OPTION_TEMPLATE), key=lambda item: item.template_code)
    return dataclasses.replace(value, contracts=(header,), pob_template_versions=tuple(templates))


def test_ex_06_e_exercise_continuation() -> None:
    folded = fold_at(ex_06_e(), "MATERIAL_RIGHT_EXERCISED")
    ev = folded.amended
    allocations = {ob.obligation_key: ob.segments[0].a_posted for ob in folded.state.obligations}
    assert allocations == {"MR": usd("83.33"), "P1": usd("750.00"), "P2": usd("166.67")}
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx,
        folded.state,
        ev,
        tb,
        identified=folded.identified,
        price_at=price_function("1000.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    p3 = obligation(after, "P3")
    (segment,) = p3.segments
    assert (segment.cause, segment.basis, segment.a_posted, segment.x_exact) == (
        SegmentCause.MATERIAL_RIGHT_EXERCISE,
        "PROSPECTIVE",
        usd("383.33"),  # 83.33 + 300.00
        Fraction(250, 3) + 300,  # M_x + C_add
    )
    allocation = nodes[f"allocated_amount@{ev.event_key}:K-01/P3:-"]
    assert (allocation.formula_id, allocation.value) == ("mod.exercise.continuation.v1", "383.33")
    assert obligation(after, "P2").segments == obligation(folded.state, "P2").segments  # 166.67
    assert obligation(after, "P1").segments == obligation(folded.state, "P1").segments
    closing = obligation(after, "MR").segments[-1]
    assert (closing.cause, closing.basis, closing.x_exact, closing.a_posted) == (
        SegmentCause.MATERIAL_RIGHT_EXERCISE,
        "INCEPTION",
        0,  # E_o(x)
        0,  # C_o(x)
    )
    catch_ups = {key: nodes[f"catch_up@{ev.event_key}:K-01/{key}:-"].value for key in ("MR", "P3")}
    assert catch_ups == {"MR": "0.00", "P3": "0.00"}
    assert after.tp_history[-1].allocation_basis.posted == usd("1300.00")


def test_ex_06_e_exercise_modification() -> None:
    folded = fold_at(
        ex_06_e(overrides={"material_right.exercise": "MODIFICATION"}), "MATERIAL_RIGHT_EXERCISED"
    )
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx,
        folded.state,
        ev,
        tb,
        identified=folded.identified,
        price_at=price_function("1000.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    assert nodes[f"mod_pool@{ev.event_key}:K-01:-"].value == "550.00"  # 166.67 + 83.33 + 300.00
    weights = {
        key: nodes[f"mod_weight@{ev.event_key}:K-01/{key}:-"].value for key in ("MR", "P2", "P3")
    }
    assert weights == {"MR": "0", "P2": "200", "P3": "400"}
    shares = {key: nodes[f"mod_share@{ev.event_key}:K-01/{key}:-"].value for key in ("P2", "P3")}
    assert shares == {"P2": "183.33", "P3": "366.67"}
    p2 = obligation(after, "P2").segments[-1]
    assert (p2.cause, p2.basis, p2.a_posted) == (
        SegmentCause.MATERIAL_RIGHT_EXERCISE,
        "PROSPECTIVE",
        usd("183.33"),
    )
    assert obligation(after, "P3").segments[-1].a_posted == usd("366.67")
    assert obligation(after, "MR").segments[-1].a_posted == 0
    catch_ups = {key: nodes[f"catch_up@{ev.event_key}:K-01/{key}:-"].value for key in ("P2", "P3")}
    assert catch_ups == {"P2": "0.00", "P3": "0.00"}  # no catch-up
    assert obligation(after, "P1").segments == obligation(folded.state, "P1").segments
    lines = nodes[f"mod_exercise@{ev.event_key}:K-01/MR:-"]
    assert (lines.formula_id, lines.value, lines.params["removed_quantity"]) == (
        "mod.exercise.modification.v1",
        "300.00",
        "1",
    )


# --- TC-04 (legacy 03 §7.3; golden Contract 3 through step 13) -----------------------------------

STEP_12 = golden_streams.GOLDEN_ROOT / "12-retro-mod-2023-08-15-pob-reduction" / "contract_live.csv"


def exact(value: str) -> Fraction:
    return Fraction(Decimal(value))


def golden_step_12() -> dict[str, Mapping[str, str]]:
    """The Contract 3 rows that golden step 12 appended to ``contract_live`` (read-only)."""
    with STEP_12.open(encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["Contract Unique Name"] == "Contract 3"
            and row["Processing Time Log"] == "step-12"
        ]
    return {row["POB Unique ID"]: row for row in rows}


def contract_3_exercised() -> InputBundle:
    """Golden Contract 3 through step 13, with the 09.15 material right exercise as the event.

    Step 13 uploads POB #4 −1,000 units and POB #5 +5 units for 1,000.00 (legacy 03 §5.1). Under
    POL-028 ``CONTINUATION`` the platform appends ``MATERIAL_RIGHT_EXERCISED`` with those lines.
    The products the parity preset maps to its seeded templates take them as product defaults, as
    in ``test_tc_rm_15_zero_remaining_quantity``.
    """
    stream = golden_streams.stream("Contract 3", "13")
    base = stream.input_bundle(preset="DEFAULT")
    products = tuple(
        dataclasses.replace(
            item,
            default_template_code="LEGACY-DISTINCT"
            if item.distinctness_default == "distinct"
            else "LEGACY-NONDISTINCT",
        )
        if item.default_template_code is None
        else item
        for item in base.group.products
    )
    step_13 = next(event for event in base.events if event.modification_key == "MOD-13")
    lines = step_13.payload["lines"]
    assert isinstance(lines, list)
    option_line, added = lines
    payload: dict[str, object] = {
        "obligation_key": option_line["obligation_key"],
        "exercised_quantity": -option_line["quantity_delta"],
        "additional_consideration": added["consideration_delta"],
        "new_lines": [
            {
                "obligation_key": added["obligation_key"],
                "product_code": added["product_code"],
                "quantity": added["quantity_delta"],
                "total_price": added["consideration_delta"],
                "start_date": added["start_date"],
                "end_date": added["end_date"],
                "stratification": added["stratification"],
                "ssp_version_label": added["ssp_version_label"],
                "performing_entity_code": added["selling_entity_code"],
                "account_overrides": added["account_codes"],
            }
        ],
    }
    exercised: EventInput = dataclasses.replace(
        step_13,
        event_type="MATERIAL_RIGHT_EXERCISED",
        payload=payload,
        payload_sha256=sha256_hex(payload),
        modification_key=None,
    )
    header = base.contracts[0]
    kept = tuple(item for item in header.modifications if item.modification_key != "MOD-13")
    return dataclasses.replace(
        base,
        group=dataclasses.replace(base.group, products=products),
        contracts=(dataclasses.replace(header, modifications=kept),),
        events=tuple(exercised if event is step_13 else event for event in base.events),
    )


def after_step_12(st: AllocatedState) -> AllocatedState:
    """The state after golden step 12: the S06-R-29 template segment of every obligation, built
    from the step 12 ``contract_live`` rows (L2-3-Q-24)."""
    (step_12,) = [
        ev
        for ev in st.events
        if ev.event_type == "CONTRACT_AMENDED" and ev.payload["modification_id"] == "MOD-12"
    ]
    rows = golden_step_12()
    revenue = {key: exact(row["Current Rev Rec - Cumulative"]) for key, row in rows.items()}
    x_exact = {
        key: revenue[key] + exact(row["Current Remaining Allocation"]) for key, row in rows.items()
    }
    keys = [ob.subject_key for ob in st.obligations]
    posted = largest_remainder(
        usd("1600.00"), [x_exact[ob.obligation_key] for ob in st.obligations], keys
    )
    obligations = []
    for ob, a_posted in zip(st.obligations, posted, strict=True):
        row, key = rows[ob.obligation_key], ob.obligation_key
        quantity, remaining_ssp = (
            exact(row["Current Remaining Qty"]),
            exact(row["Current Remaining SSP"]),
        )
        end = date.fromisoformat(row["POB End Date"][:10])
        segment = AllocationSegment(
            component="FIXED",
            effective_date=step_12.effective_date,
            event_key=step_12.event_key,
            cause=SegmentCause.MODIFICATION,
            basis="PROSPECTIVE",
            x_exact=x_exact[key],
            a_posted=a_posted,
            base_revenue_posted=round_half_up(revenue[key], 2),
            base_revenue_exact=revenue[key],
            base_progress=ProgressBase(
                exact(row["Current Delivery - Cumulative"]),
                Fraction(0),
                Fraction(0),
                step_12.effective_date,
            ),
            totals=ProgressTotals(quantity, None, ob.start_date, end),
            progress_measure="UNITS_SINCE_BOUNDARY",
            unit_ssp=None if quantity == 0 else remaining_ssp / quantity,
            remaining_ssp=remaining_ssp,
            remaining_billing_plan=exact(row["Current Remaining Billing"]),
            estimate_pair=(None, None),
            modification_boundary_no=1,
        )
        obligations.append(dataclasses.replace(ob, end_date=end, segments=(*ob.segments, segment)))
    return dataclasses.replace(st, obligations=tuple(obligations))


def test_tc_prospective_04_continuation_values() -> None:
    folded = fold_at(contract_3_exercised(), "MATERIAL_RIGHT_EXERCISED")
    st, ev = after_step_12(folded.state), folded.amended
    assert sum(ob.segments[-1].a_posted for ob in st.obligations) == usd("1600.00")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx, st, ev, tb, identified=folded.identified, price_at=price_function("1300.00")
    )
    assert after.findings == ()
    nodes = checked(tb)
    # Remaining allocation: X − E at the exercise; nothing has transferred since step 12.
    remaining = {
        ob.obligation_key: ob.segments[-1].x_exact - ob.segments[-1].base_revenue_exact
        for ob in after.obligations
        if ob.obligation_key in ("POB #1", "POB #2", "POB #3")
    }
    remaining["POB #5"] = obligation(after, "POB #5").segments[-1].x_exact
    expected = {
        "POB #5": "1833.767587",
        "POB #1": "334.340803",
        "POB #2": "153.413236",
        "POB #3": "62.532569",
    }
    tolerance = Fraction(1, 10000)  # D-17
    assert all(abs(remaining[key] - exact(value)) <= tolerance for key, value in expected.items())
    for key in ("POB #1", "POB #2", "POB #3"):
        assert obligation(after, key).segments == obligation(st, key).segments  # other POBs kept
    catch_ups = [node.value for node_id, node in nodes.items() if node_id.startswith("catch_up@")]
    assert catch_ups == ["0.00", "0.00"]  # the option and POB #5: no catch-up
    assert after.tp_history[-1].allocation_basis.posted == usd("2600.00")


def test_l5_3_continuation_reads_only_the_exercise_policy() -> None:
    """MR-CHK-052-GT15-CONTINUATION runs the LEGACY_PARITY preset, so POL-102
    ``mod.catch_up_scope`` resolves to ``ALL_POBS_FULL_REALLOCATION``, which the native modification
    path does not build. S06-R-23 reads POL-028 only: the continuation exercise does not fail
    closed on the modification options and gives the TC-04 result (L5-3-Q-25)."""
    value = contract_3_exercised()
    (book,) = value.books
    policies = tuple(
        dataclasses.replace(
            item, value="ALL_POBS_FULL_REALLOCATION", level="T", source_ref="LEGACY_PARITY"
        )
        if item.code == "mod.catch_up_scope"
        else item
        for item in book.policies
    )
    assert any(item.code == "mod.catch_up_scope" for item in policies)
    value = dataclasses.replace(value, books=(dataclasses.replace(book, policies=policies),))
    folded = fold_at(value, "MATERIAL_RIGHT_EXERCISED")
    st, ev = after_step_12(folded.state), folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx, st, ev, tb, identified=folded.identified, price_at=price_function("1300.00")
    )
    assert after.findings == ()
    checked(tb)
    assert after.tp_history[-1].allocation_basis.posted == usd("2600.00")
    for key in ("POB #1", "POB #2", "POB #3"):
        assert obligation(after, key).segments == obligation(st, key).segments


# --- S06-R-25 expiry -----------------------------------------------------------------------------


def test_s06_r25_expiry_is_not_a_boundary() -> None:
    ctx, identified, st = inception(ex_06_e(expired=True))
    (expired,) = [ev for ev in st.events if ev.event_type == "MATERIAL_RIGHT_EXPIRED"]
    assert expired in st.measure_events  # stage 01 classifies it as a measure event (Table 0.3-A)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(ctx, st, expired, tb, identified=identified, price_at=None)
    assert after is st
    assert all(len(ob.segments) == 1 for ob in after.obligations)
    assert tb.build(root_measures={}).nodes == ()


# --- S06-R-26 LINE_ATTRIBUTES_CHANGED ------------------------------------------------------------

ATTRIBUTES_INCEPTION = date(2023, 1, 1)


def attribute_bundle() -> InputBundle:
    """A 600.00 (delivered in March) and B 400.00; an account override on 1 May 2023 and a
    corrected SSP version pin on 15 Jun 2023."""
    end = date(2023, 12, 31)
    lines = [
        bundles.booking_line(
            "A", product_code="SKU-A", total_price="600.00", start=ATTRIBUTES_INCEPTION, end=end
        ),
        bundles.booking_line(
            "B", product_code="SKU-B", total_price="400.00", start=ATTRIBUTES_INCEPTION, end=end
        ),
    ]
    override = {
        "obligation_key": "A",
        "changes": {"account_overrides": {"REVENUE": "4099"}},
        "diff": {"account_overrides.REVENUE": "4000 -> 4099"},
    }
    repin = {
        "obligation_key": "A",
        "changes": {"ssp_book_version_id": "SSP-US@v2", "justification": "Corrected SSP study"},
        "diff": {"ssp_book_version_id": "SSP-US@v1 -> SSP-US@v2"},
    }
    return bundle(
        booked(ATTRIBUTES_INCEPTION, *lines),
        delivered(3, "A", "1", date(2023, 3, 31)),
        bundles.event(
            CONTRACT,
            4,
            "LINE_ATTRIBUTES_CHANGED",
            date(2023, 5, 1),
            override,
            obligation_keys=["A"],
        ),
        bundles.event(
            CONTRACT, 5, "LINE_ATTRIBUTES_CHANGED", date(2023, 6, 15), repin, obligation_keys=["A"]
        ),
        products=[product("SKU-A", "TPL-UNITS"), product("SKU-B", "TPL-UNITS")],
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "SKU-A", "600.00"),
                    point_entry("SSP-US@v1", "SKU-B", "400.00"),
                ],
                date(2020, 1, 1),
            ),
            ssp_version(
                2,
                [
                    point_entry("SSP-US@v2", "SKU-A", "800.00"),
                    point_entry("SSP-US@v2", "SKU-B", "400.00"),
                ],
                date(2029, 1, 1),  # approved, named by the override, not effective at inception
            ),
        ],
        inception=ATTRIBUTES_INCEPTION,
        months=24,
        modifications=[],
    )


def test_s06_r26_line_attributes_changed() -> None:
    ctx, identified, st = inception(attribute_bundle())
    override, repin = [ev for ev in st.events if ev.event_type == "LINE_ATTRIBUTES_CHANGED"]
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(ctx, st, override, tb, identified=identified, price_at=None)
    assert after is st  # no segment
    assert tb.build(root_measures={}).nodes == ()
    a, b = obligation(after, "A"), obligation(after, "B")
    booked_attributes = s06_modifications.attributes_at(after, a, date(2023, 4, 30))
    changed = s06_modifications.attributes_at(after, a, date(2023, 5, 1))
    assert booked_attributes.account_overrides == a.account_overrides
    assert changed.account_overrides == {**a.account_overrides, "REVENUE": "4099"}
    assert changed.performing_entity == a.performing_entity
    assert s06_modifications.attributes_at(after, b, date(2023, 12, 31)).account_overrides == (
        b.account_overrides
    )

    # A corrected SSP version pin re-allocates the group from inception: A 800, B 400 over 1,000.00.
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    repinned = s06_modifications.apply(ctx, after, repin, tb, identified=identified, price_at=None)
    assert repinned.findings == ()
    nodes = checked(tb)
    assert nodes[f"mod_pool@{repin.event_key}:K-01:-"].value == "1000.00"
    weights = {key: nodes[f"mod_weight@{repin.event_key}:K-01/{key}:-"].value for key in "AB"}
    assert weights == {"A": "800", "B": "400"}
    shares = {key: nodes[f"mod_share@{repin.event_key}:K-01/{key}:-"].value for key in "AB"}
    assert shares == {"A": "666.67", "B": "333.33"}
    corrected = obligation(repinned, "A")
    segment = corrected.segments[-1]
    assert (segment.basis, segment.event_key, segment.a_posted) == (
        "INCEPTION",
        repin.event_key,
        usd("666.67"),
    )
    assert corrected.ssp is not None and corrected.ssp.version_key == "SSP-US@v2"
    assert corrected.resolved_ssp == 800
    # A is delivered: the difference posts as a catch-up at the event (RCP-06).
    catch_ups = {key: nodes[f"catch_up@{repin.event_key}:K-01/{key}:-"].value for key in "AB"}
    assert catch_ups == {"A": "66.67", "B": "0.00"}


# --- S06-R-27 REGROUPED --------------------------------------------------------------------------


def regroup_bundle() -> InputBundle:
    """K-01 books POB-A; bundle assembly has moved POB-B into K-02's booking beside POB-C."""
    moved_on = date(2026, 2, 1)
    first, second = bundles.contract("K-01"), bundles.contract("K-02")

    def events(contract: str, offset: int, lines: list[Mapping[str, object]]) -> list[EventInput]:
        keys = [str(line["obligation_key"]) for line in lines]
        payload = {
            "regroup_id": "RG-1",
            "direction": "OUT" if contract == "K-01" else "IN",
            "obligation_keys": ["POB-B"],
            "counterpart_contract_id": "K-02" if contract == "K-01" else "K-01",
            "modification_id": f"MOD-RG-{contract}",
        }
        return [
            bundles.event(
                contract,
                1,
                "CONTRACT_BOOKED",
                INCEPTION,
                {"lines": lines},
                record_seq=offset + 1,
                obligation_keys=keys,
            ),
            bundles.event(
                contract,
                2,
                "CONTRACT_ACTIVATED",
                INCEPTION,
                {"checklist": {}},
                record_seq=offset + 2,
            ),
            bundles.event(
                contract,
                3,
                "REGROUPED",
                moved_on,
                payload,
                record_seq=offset + 3,
                obligation_keys=["POB-B"],
            ),
        ]

    booked_first = [bundles.booking_line("POB-A", product_code="SKU-A", total_price="600.00")]
    booked_second = [
        bundles.booking_line("POB-B", product_code="SKU-B", total_price="400.00"),
        bundles.booking_line("POB-C", product_code="SKU-C", total_price="500.00"),
    ]
    stream = [*events("K-01", 0, booked_first), *events("K-02", 10, booked_second)]
    products = [
        product("SKU-A", "TPL-UNITS"),
        product("SKU-B", "TPL-UNITS"),
        product("SKU-C", "TPL-UNITS"),
    ]
    value = bundle(
        products=products,
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "SKU-A", "600.00"),
                    point_entry("SSP-US@v1", "SKU-B", "400.00"),
                    point_entry("SSP-US@v1", "SKU-C", "500.00"),
                ],
                date(2020, 1, 1),
            )
        ],
        inception=INCEPTION,
        months=24,
        modifications=[],
    )
    return dataclasses.replace(
        value,
        group=bundles.group((first, second), products=products),
        contracts=(first, second),
        events=tuple(sorted(stream, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
    )


def test_s06_r27_regrouped_before_posting() -> None:
    ctx, identified, st = inception(regroup_bundle())
    out_event, in_event = [ev for ev in st.events if ev.event_type == "REGROUPED"]
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(ctx, st, out_event, tb, identified=identified, price_at=None)
    after = s06_modifications.apply(ctx, after, in_event, tb, identified=identified, price_at=None)
    assert after is st  # no boundary: the obligation is booked in K-02 from its inception
    assert tb.build(root_measures={}).nodes == ()
    moved = obligation(after, "POB-B")
    (segment,) = moved.segments
    assert (moved.contract_key, segment.cause, segment.effective_date) == (
        "K-02",
        SegmentCause.INCEPTION,
        INCEPTION,
    )
    assert [ob.obligation_key for ob in after.obligations if ob.contract_key == "K-01"] == ["POB-A"]
    # An OUT event naming an obligation still booked in K-01 is after posting: a modification of
    # both contracts, applied by §6.3 from its approved modification.
    posted = dataclasses.replace(
        out_event, payload={**out_event.payload, "obligation_keys": ("POB-A",)}
    )
    with pytest.raises(ValueError, match="MOD-RG-K-01 is absent"):
        s06_modifications.apply(ctx, st, posted, tb, identified=identified, price_at=None)
