"""Stage 06 cumulative catch-up, mixed modifications, satisfied performance, targeted concessions.

ENGINE_SPEC §6.3 S06-R-09, S06-R-10, S06-R-15; §6.6 S06-INV-03; §6.7 EX-06-A, EX-06-D; POLICIES
ALG-04 §2.5.3 to §2.5.8 (CHK-027, CHK-028, CHK-042), POL-102, POL-104, POL-243, §5.4 PT-04
(CHK-113); ENB-3. The inception state comes from the real stages 01 to 05, and the tests bind a fake
stage 04 price function (D-81), as in ``test_s06_prospective``. Stage 05 names no EAC element on a
segment (L1-2-Q-51), so the cost-to-cost tests set ``totals.eac_element_code`` on the inception
segment. Every stage 06 trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EstimateVersionInput, EventInput
from erev_engine.money import cumulative_posted
from erev_engine.stages import s06_modifications, s09_recognition
from erev_engine.stages.state import AllocatedState, ConcessionQuota, SegmentCause
from erev_engine.trace import TraceBuilder
from support import bundles
from support.recognition import estimate_version, period_amounts, targets_by_period
from test_s06_prospective import (
    CONTRACT,
    INCEPTION,
    Folded,
    amended,
    booked,
    bundle,
    checked,
    delivered,
    fold,
    mod_line,
    modification_input,
    obligation,
    point_entry,
    price_function,
    product,
    ssp_version,
    usd,
)


def eac(element: str, number: int, effective: date, total: str) -> EstimateVersionInput:
    """An approved ``EAC`` version of ``K-01/<element>`` (T-CON-13)."""
    base = estimate_version(f"{CONTRACT}/{element}", "EAC", number, effective)
    return dataclasses.replace(base, expected_total_amount=Decimal(total))


def estimate_event(stream: int, version: EstimateVersionInput) -> EventInput:
    payload = {"estimate_version_id": version.version_key}
    return bundles.event(CONTRACT, stream, "ESTIMATE_CHANGED", version.effective_date, payload)


def cost(stream: int, key: str, amount: str, on: date) -> EventInput:
    payload = {"obligation_key": key, "amount": Decimal(amount), "purpose": "PROGRESS_INPUT"}
    return bundles.event(CONTRACT, stream, "COST_INCURRED", on, payload, obligation_keys=[key])


def with_eac(folded: Folded, key: str, element: str) -> Folded:
    """Name the EAC element on the obligation's segments (stage 05 names none; L1-2-Q-51)."""
    obligations = tuple(
        dataclasses.replace(
            ob,
            segments=tuple(
                dataclasses.replace(
                    seg, totals=dataclasses.replace(seg.totals, eac_element_code=element)
                )
                for seg in ob.segments
            ),
        )
        if ob.obligation_key == key
        else ob
        for ob in folded.state.obligations
    )
    return dataclasses.replace(
        folded, state=dataclasses.replace(folded.state, obligations=obligations)
    )


def apply(folded: Folded, booked_price: str, tb: TraceBuilder, **price: str) -> AllocatedState:
    return s06_modifications.apply(
        folded.ctx,
        folded.state,
        folded.amended,
        tb,
        identified=folded.identified,
        price_at=price_function(booked_price, **price),
    )


# --- EX-06-D (CHK-027; FASB Example 8) ------------------------------------------------------------


def test_chk_027_pure_25_13_b() -> None:
    d = date(2026, 9, 10)
    modification = modification_input(
        "MOD-27", d, [mod_line("B", "CHANGE", "SKU-BUILD", "0", "150000.00")], kind="PRICE_CHANGE"
    )
    first, updated = eac("EAC-B", 1, INCEPTION, "700000.00"), eac("EAC-B", 2, d, "820000.00")
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "B",
                product_code="SKU-BUILD",
                total_price="1000000.00",
                end=date(2027, 12, 31),
            ),
        ),
        estimate_event(3, first),
        cost(4, "B", "420000.00", date(2026, 8, 31)),
        amended(5, modification, {"B": "CUMULATIVE_CATCH_UP"}),
        estimate_event(6, updated),  # the updated EAC is effective at d, recorded after the event
        products=[product("SKU-BUILD", "TPL-C2C")],
        ssp=[
            ssp_version(1, [point_entry("SSP-US@v1", "SKU-BUILD", "1000000.00")], date(2025, 1, 1))
        ],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
        estimate_versions=[first, updated],
    )
    folded = with_eac(fold(value), "B", "EAC-B")
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    # The bonus version now included by the modification: ΔVC 200,000.00.
    after = apply(folded, "1000000.00", tb, includable="200000.00")
    assert after.findings == ()
    nodes = checked(tb)
    pool = nodes[f"mod_pool@{ev.event_key}:K-01:-"]
    assert (pool.value, pool.params["revenue"], pool.params["vc_delta"]) == (
        "750000.00",
        str(usd("600000.00")),  # R = 1,000,000.00 × 420,000 ÷ 700,000
        str(usd("200000.00")),
    )
    weight = nodes[f"mod_weight@{ev.event_key}:K-01/B:-"]
    assert (weight.params["class"], weight.params["progress"], weight.value) == (
        "N",
        "3/5",
        "400000",
    )
    segment = obligation(after, "B").segments[-1]
    assert (segment.cause, segment.basis, segment.x_exact, segment.a_posted) == (
        SegmentCause.MODIFICATION,
        "INCEPTION",
        1350000,
        usd("1350000.00"),
    )
    assert segment.base_revenue_posted == 0
    posted = cumulative_posted(Fraction(1350000), usd("1350000.00"), Fraction(420, 820), 2)
    assert posted == usd("691463.41")  # C′
    catch_up = nodes[f"catch_up@{ev.event_key}:K-01/B:-"]
    assert (catch_up.formula_id, catch_up.value) == ("mod.catch_up.v1", "91463.41")


# --- EX-06-A (CHK-042; mixed 25-13(c)) -----------------------------------------------------------

MIXED_DATE = date(2026, 6, 15)


def chk_042(overrides: dict[str, str] | None = None) -> Folded:
    """A 40,000.00 satisfied; B cost to cost 50% complete (class N); C unstarted (class D)."""
    scope = mod_line("B", "CHANGE", "SKU-SCOPE", "1", "20000.00")
    modification = modification_input("MOD-42", MIXED_DATE, [scope], kind="QUANTITY_CHANGE")
    first, updated = (
        eac("EAC-B", 1, INCEPTION, "60000.00"),
        eac("EAC-B", 2, MIXED_DATE, "75000.00"),
    )
    lines = [
        bundles.booking_line("A", product_code="SKU-A", total_price="40000.00"),
        bundles.booking_line(
            "B", product_code="SKU-B", total_price="60000.00", end=date(2027, 6, 30)
        ),
        bundles.booking_line("C", product_code="SKU-C", total_price="20000.00"),
    ]
    value = bundle(
        booked(INCEPTION, *lines),
        estimate_event(3, first),
        delivered(4, "A", "1", date(2026, 3, 31)),
        cost(5, "B", "30000.00", date(2026, 5, 31)),
        amended(6, modification, {"B": "CUMULATIVE_CATCH_UP", "C": "PROSPECTIVE"}),
        estimate_event(7, updated),  # EAC +15,000.00 effective at d
        products=[
            product("SKU-A", "TPL-UNITS"),
            product("SKU-B", "TPL-C2C"),
            product("SKU-C", "TPL-UNITS"),
            product("SKU-SCOPE", "TPL-UNITS"),
        ],
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "SKU-A", "50000.00"),
                    point_entry("SSP-US@v1", "SKU-B", "75000.00"),
                    point_entry("SSP-US@v1", "SKU-C", "25000.00"),
                ],
                date(2025, 1, 1),
                date(2026, 5, 31),
            ),
            ssp_version(
                2,
                [
                    point_entry("SSP-US@v2", "SKU-C", "30000.00"),
                    point_entry("SSP-US@v2", "SKU-SCOPE", "25000.00"),
                ],
                date(2026, 6, 1),
            ),
        ],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
        overrides=overrides,
        estimate_versions=[first, updated],
    )
    folded = with_eac(fold(value), "B", "EAC-B")
    allocations = {ob.obligation_key: ob.segments[0].a_posted for ob in folded.state.obligations}
    assert allocations == {"A": usd("40000.00"), "B": usd("60000.00"), "C": usd("20000.00")}
    return folded


def test_chk_042_mixed_d18_default() -> None:
    folded = chk_042()
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "120000.00", tb)
    assert after.findings == ()
    nodes = checked(tb)
    assert nodes[f"mod_pool@{ev.event_key}:K-01:-"].value == "70000.00"
    weights = {key: nodes[f"mod_weight@{ev.event_key}:K-01/{key}:-"] for key in ("B", "C")}
    assert (weights["B"].value, weights["C"].value) == ("62500", "30000")
    assert weights["B"].formula_id == "mod.weights.d18.v1"
    shares = {key: nodes[f"mod_share@{ev.event_key}:K-01/{key}:-"].value for key in ("B", "C")}
    assert shares == {"B": "47297.30", "C": "22702.70"}
    b = obligation(after, "B").segments[-1]
    assert (b.basis, b.a_posted, b.totals.quantity) == ("INCEPTION", usd("77297.30"), 2)
    assert b.x_exact == 30000 + Fraction(70000 * 62500, 92500)
    revenue = cumulative_posted(b.x_exact, b.a_posted, Fraction(30000, 75000), 2)
    assert revenue == usd("30918.92")  # C′_B
    assert nodes[f"catch_up@{ev.event_key}:K-01/B:-"].value == "918.92"
    assert b.a_posted - revenue == usd("46378.38")  # B remaining
    c = obligation(after, "C").segments[-1]
    assert (c.basis, c.a_posted, c.base_revenue_posted) == ("PROSPECTIVE", usd("22702.70"), 0)
    assert nodes[f"catch_up@{ev.event_key}:K-01/C:-"].value == "0.00"


def test_chk_042_mixed_inception_all() -> None:
    folded = chk_042({"mod.ssp_basis": "INCEPTION_ALL"})
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "120000.00", tb)
    nodes = checked(tb)
    weights = {key: nodes[f"mod_weight@{ev.event_key}:K-01/{key}:-"] for key in ("B", "C")}
    assert (weights["B"].value, weights["C"].value) == ("62500", "25000")
    assert weights["C"].formula_id == "mod.weights.inception_all.v1"
    shares = {key: nodes[f"mod_share@{ev.event_key}:K-01/{key}:-"].value for key in ("B", "C")}
    assert shares == {"B": "50000.00", "C": "20000.00"}
    b = obligation(after, "B").segments[-1]
    assert b.a_posted == usd("80000.00")
    revenue = cumulative_posted(b.x_exact, b.a_posted, Fraction(2, 5), 2)
    assert revenue == usd("32000.00")
    assert nodes[f"catch_up@{ev.event_key}:K-01/B:-"].value == "2000.00"
    assert b.a_posted - revenue == usd("48000.00")


def test_s06_inv_03_class_s_unchanged() -> None:
    folded = chk_042()
    after = apply(folded, "120000.00", TraceBuilder(engine_version=ENGINE_VERSION))
    before_a, after_a = obligation(folded.state, "A"), obligation(after, "A")
    assert after_a.segments == before_a.segments  # X and A kept: no satisfied performance
    assert after_a.last_modification_key == "MOD-42"
    assert (len(obligation(after, "B").segments), len(obligation(after, "C").segments)) == (2, 2)


# --- CHK-028 (FASB Example 5 Case B), satisfied performance ---------------------------------------


def test_chk_028_satisfied_performance_credit() -> None:
    d = date(2026, 6, 15)
    lines = [
        mod_line("POB-DEL", "CHANGE", "SKU-P", "0", "-900.00"),
        mod_line("POB-REM", "CHANGE", "SKU-P", "30", "2400.00"),
    ]
    modification = modification_input(
        "MOD-28B",
        d,
        lines,
        kind="QUANTITY_CHANGE",
        questionnaire={"price_change_settlement": "FUTURE_PRICING"},
        price_change_amount="-900.00",
    )
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "POB-DEL", product_code="SKU-P", quantity="60", total_price="6000.00"
            ),
            bundles.booking_line(
                "POB-REM", product_code="SKU-P", quantity="60", total_price="6000.00"
            ),
        ),
        delivered(3, "POB-DEL", "60", date(2026, 5, 31)),
        amended(4, modification, {"POB-REM": "PROSPECTIVE"}),
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
    folded = fold(value)
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "12000.00", tb)
    assert after.findings == ()
    nodes = checked(tb)
    share = nodes[f"satisfied_share@{ev.event_key}:K-01/POB-DEL:-"]
    assert (share.formula_id, share.value, share.params["mode"], share.params["settlement"]) == (
        "mod.satisfied_performance.v1",
        "-900.00",  # ΔC_sat over the class S obligations (JET-05b in END)
        "INCEPTION_BASIS",
        "FUTURE_PRICING",
    )
    delivered_after = obligation(after, "POB-DEL").segments[-1]
    assert (delivered_after.basis, delivered_after.x_exact, delivered_after.a_posted) == (
        "INCEPTION",
        5100,
        usd("5100.00"),
    )
    assert nodes[f"catch_up@{ev.event_key}:K-01/POB-DEL:-"].value == "-900.00"
    pool = nodes[f"mod_pool@{ev.event_key}:K-01:-"]
    assert (pool.value, pool.params["satisfied"]) == ("8400.00", str(usd("-900.00")))
    remaining = obligation(after, "POB-REM").segments[-1]
    assert (remaining.basis, remaining.totals.quantity, remaining.a_posted) == (
        "PROSPECTIVE",
        90,
        usd("8400.00"),
    )


def test_l5_3_chk_028_satisfied_performance_on_the_delivered_portion() -> None:
    """MOD-CHK-028-S6-EX5-CASEB with one obligation: 120 products at 100.00, 60 delivered; a
    CHANGE line adds 30 for 1,500.00 and ``price_change_amount`` -900.00 credits the 60 defective
    products already transferred. No class S obligation exists. S06-R-09 apportions ΔC_sat over
    the delivered portion of the class D obligation the line names (ALG-04 §2.5.3: added to A_p
    and R_p), so the PROSPECTIVE segment starts at R_p + share = 5,100.00, the catch-up is the
    share, and the pool of 8,400.00 covers the 90 remaining units (CHK-028)."""
    d = date(2026, 6, 15)
    modification = modification_input(
        "MOD-28C",
        d,
        [mod_line("POB-01", "CHANGE", "SKU-P", "30", "1500.00")],
        kind="QUANTITY_CHANGE",
        questionnaire={"price_change_settlement": "FUTURE_PRICING"},
        price_change_amount="-900.00",
    )
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "POB-01", product_code="SKU-P", quantity="120", total_price="12000.00"
            ),
        ),
        delivered(3, "POB-01", "60", date(2026, 5, 31)),
        amended(4, modification, {"POB-01": "PROSPECTIVE"}),
        delivered(5, "POB-01", "1", date(2026, 6, 20)),
        delivered(6, "POB-01", "1", date(2026, 7, 20)),
        delivered(7, "POB-01", "1", date(2026, 8, 20)),
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
    folded = fold(value)
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "12000.00", tb)
    assert after.findings == ()
    (ob,) = after.obligations
    segment = ob.segments[-1]
    assert (segment.basis, segment.totals.quantity, segment.base_revenue_posted) == (
        "PROSPECTIVE",
        90,
        usd("5100.00"),
    )
    assert (segment.a_posted, segment.x_exact) == (usd("13500.00"), 13500)
    state = s09_recognition.run(folded.ctx, after, tb)
    nodes = checked(tb)
    share = nodes[f"satisfied_share@{ev.event_key}:K-01/POB-01:-"]
    assert (share.value, share.params["keys"]) == ("-900.00", "K-01/POB-01")
    assert nodes[f"mod_pool@{ev.event_key}:K-01:-"].value == "8400.00"
    assert nodes[f"catch_up@{ev.event_key}:K-01/POB-01:-"].value == "-900.00"
    amounts = period_amounts(targets_by_period(state, "K-01/POB-01"))
    assert (amounts["FY2026-P06"], amounts["FY2026-P07"], amounts["FY2026-P08"]) == (
        usd("-806.67"),  # the -900.00 catch-up at d, then unit 1 at 93.33
        usd("93.34"),
        usd("93.33"),
    )


# --- CHK-113 (PT-04; legacy 05 TC-pob-vc-16 corrected value) --------------------------------------


def chk_113(overrides: dict[str, str] | None = None, *, settlement: str | None = None) -> Folded:
    """Contract 2 figures: POB #2 fully delivered at 385.19; POB #1 delivered at 914.81."""
    d = date(2026, 5, 31)
    questionnaire: dict[str, object] = {"POB #2": {"pol_243_attested": True}}
    if settlement is not None:
        questionnaire["price_change_settlement"] = settlement
    modification = modification_input(
        "MOD-113",
        d,
        [mod_line("POB #2", "CHANGE", "Software 1", "0", "-60.00")],
        kind="VC_CHANGE",
        questionnaire=questionnaire,
        price_change_amount="-60.00",
    )
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line("POB #1", product_code="Hardware 1", total_price="914.81"),
            bundles.booking_line("POB #2", product_code="Software 1", total_price="385.19"),
        ),
        delivered(3, "POB #1", "1", date(2026, 3, 31)),
        delivered(4, "POB #2", "1", date(2026, 3, 31)),
        amended(5, modification, {}),
        products=[product("Hardware 1", "TPL-UNITS"), product("Software 1", "TPL-UNITS")],
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "Hardware 1", "914.81"),
                    point_entry("SSP-US@v1", "Software 1", "385.19"),
                ],
                date(2025, 1, 1),
            )
        ],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
        overrides=overrides,
    )
    return fold(value)


def test_chk_113_targeted_concession() -> None:
    folded = chk_113({"concession.allocation_basis": "TARGETED_WHEN_32_40_ATTESTED"})
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "1300.00", tb)
    assert after.findings == ()
    nodes = checked(tb)
    share = nodes[f"satisfied_share@{ev.event_key}:K-01/POB %232:-"]
    assert (share.value, share.params["mode"]) == ("-60.00", "TARGETED_WHEN_32_40_ATTESTED")
    catch_up = nodes[f"catch_up@{ev.event_key}:K-01/POB %232:-"]
    assert (catch_up.value, catch_up.params["a_before"]) == ("-60.00", str(usd("385.19")))
    pob2 = obligation(after, "POB #2").segments[-1]
    assert (pob2.a_posted, pob2.x_exact) == (usd("325.19"), Fraction(32519, 100))  # C = A′ at f = 1
    assert obligation(after, "POB #1").segments == obligation(folded.state, "POB #1").segments
    assert f"satisfied_share@{ev.event_key}:K-01/POB %231:-" not in nodes

    # POL-243 INCEPTION_BASIS: S06-R-09 apportionment over both satisfied obligations.
    folded = chk_113()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    apply(folded, "1300.00", tb)
    nodes = checked(tb)
    shares = {
        key: nodes[f"satisfied_share@{ev.event_key}:K-01/POB %23{key}:-"].value for key in "12"
    }
    assert shares == {"1": "-42.22", "2": "-17.78"}


def test_l7_5_credit_or_refund_concession_creates_refund_quotas() -> None:
    """D-87 L6-5-Q-10: under ``price_change_settlement = CREDIT_OR_REFUND`` each receiving
    obligation's negative share adds ``refund_components[subject] += ConcessionQuota(−exact,
    −posted, EMBEDDED)``
    (S06-R-09 apportionment, S06-R-10 targeting). Before the fix stage 06 recorded termination
    quotas only, so ``RND-CHK-003C`` posted no JET-05c ``REFUND_LIABILITY`` credit."""
    targeted = {"concession.allocation_basis": "TARGETED_WHEN_32_40_ATTESTED"}
    folded = chk_113(targeted, settlement="CREDIT_OR_REFUND")
    after = apply(folded, "1300.00", TraceBuilder(engine_version=ENGINE_VERSION))
    assert after.findings == ()
    # D-91 L9-ENG-B3-Q-1: the producer marks the quota EMBEDDED (the share was applied to the
    # receiver's segment, so the stage 09 revenue node already carries the concession).
    assert dict(after.refund_components) == {
        "K-01/POB %232": ConcessionQuota(Fraction(60), usd("60.00"), revenue_basis="EMBEDDED")
    }

    # INCEPTION_BASIS: each satisfied obligation receives the quota of its own share, exact
    # 60 × original posted allocation ÷ 1,300.00 (914.81 and 385.19), posted 42.22 and 17.78.
    folded = chk_113(settlement="CREDIT_OR_REFUND")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "1300.00", tb)
    checked(tb)
    assert dict(after.refund_components) == {
        "K-01/POB %231": ConcessionQuota(
            Fraction(60 * 91481, 130000), usd("42.22"), revenue_basis="EMBEDDED"
        ),
        "K-01/POB %232": ConcessionQuota(
            Fraction(60 * 38519, 130000), usd("17.78"), revenue_basis="EMBEDDED"
        ),
    }

    # FUTURE_PRICING (the default) creates no quota.
    after = apply(chk_113(targeted), "1300.00", TraceBuilder(engine_version=ENGINE_VERSION))
    assert dict(after.refund_components) == {}
