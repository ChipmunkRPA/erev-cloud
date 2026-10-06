"""Stage 06 remaining service of an existing time-elapsed obligation (D-90b).

ENGINE_SPEC rev 1.5 S06-R-11 (ρ_p over the unit layers of a class D existing obligation measured by
time elapsed; ``mod.weights.d18.v1`` and ``mod.weights.inception_all.v1`` with additive params) and
S06-R-08 ``MOD_UNIT_HISTORY_AMBIGUOUS`` (same-date modifications accepted in event order,
D-90c); POLICIES ALG-04 §2.5.4; 04 §15.4 table 15.4-C. The worlds
follow the MOD-JS-06 design world (L1 40,000.00 over 1 Jul 2026 to 30 Jun 2036, weights 39,000.00 /
40,000.00, shares 53,810.13 / 55,189.87) and the layer-lineage review worlds W1 and W2. Template
``TPL-TE`` is distinct ``TIME_ELAPSED``; every world pins ``recognition.time_convention``, because
the resolved POL-090 value otherwise overrides the template convention (stage 03 ``measure``). The
inception state comes from the real stages 01 to 05, every ``CONTRACT_AMENDED`` is applied through
``s06_modifications.apply`` with the fake ``price_at`` of ``test_s06_prospective``, figures are
exact (``Fraction``) and every trace re-evaluates node for node (DG-ENG-04). No database
(DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, formulas, progress
from erev_engine.bundle import InputBundle, ModificationInput, TemplateInput
from erev_engine.enums import RatableConvention
from erev_engine.errors import EngineError
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
    s06_modifications,
)
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s06_modifications import segments
from erev_engine.stages.state import AllocatedState, BookContext, EventView, SegmentCause
from erev_engine.trace import TraceBuilder, TraceNode, reevaluate
from support import bundles
from test_s06_catch_up import apply as apply_folded
from test_s06_catch_up import chk_042
from test_s06_prospective import (
    CONTRACT,
    TEMPLATES,
    amended,
    booked,
    bundle,
    checked,
    chk_028,
    context,
    fold,
    mod_line,
    modification_input,
    obligation,
    point_entry,
    price_function,
    product,
    ssp_version,
    template,
)

S, E = date(2026, 7, 1), date(2036, 6, 30)  # L1: the MOD-JS-06 L1-STORE1 term
S2, E2 = date(2027, 7, 1), date(2037, 6, 30)  # L2: unstarted at the first boundary
S3, E3 = date(2028, 7, 1), date(2038, 6, 30)
D1 = date(2026, 10, 1)
D18, N = "PROSPECTIVE", "CUMULATIVE_CATCH_UP"
SKU = "SKU-TE"
SEATS = "SKU-SEAT"
CONVENTION = "recognition.time_convention"
D18_FORMULA = "mod.weights.d18.v1"
INCEPTION_ALL_FORMULA = "mod.weights.inception_all.v1"
SCALE_KEYS = frozenset(
    {
        "measure",
        "convention",
        "term_start",
        "term_end",
        "progress_as_of",
        "layer_quantities",
        "layer_starts",
        "layer_progress",
        "remaining_scale",
        "removed",
        "periods",
    }
)
Mod = tuple[ModificationInput, Mapping[str, str]]  # a modification and its approved treatments


# --- World ---------------------------------------------------------------------------------------


def te_template(convention: str, *, distinctness: str = "distinct") -> TemplateInput:
    return template(
        "TPL-TE",
        method="TIME_ELAPSED",
        pattern="OVER_TIME",
        convention=convention,
        distinctness=distinctness,
    )


def line(
    key: str, quantity: str, price: str, start: date, end: date, *, product_code: str = SKU
) -> Mapping[str, object]:
    return bundles.booking_line(
        key, product_code=product_code, quantity=quantity, total_price=price, start=start, end=end
    )


def mod(
    key: str, d: date, lines: Sequence[Mapping[str, object]], *, kind: str = "QUANTITY_CHANGE"
) -> ModificationInput:
    return modification_input(key, d, lines, kind=kind)


def all_d(*keys: str) -> dict[str, str]:
    return dict.fromkeys(keys, D18)


def world(
    lines: Sequence[Mapping[str, object]],
    mods: Sequence[Mod],
    *,
    convention: str = "MONTHLY_EVEN",
    pinned: bool = True,
    ssp: str = "40000.00",
    inception: date = date(2026, 1, 1),
    months: int = 156,
    overrides: Mapping[str, str] | None = None,
    distinctness: str = "distinct",
    product_code: str = SKU,
) -> InputBundle:
    """A one-contract world over ``TPL-TE`` with an SSP point of ``ssp`` per unit.

    ``pinned`` sets the book's ``recognition.time_convention`` to ``convention``; without the pin
    the resolved POL-090 value overrides the template convention.
    """
    policies = {CONVENTION: convention} if pinned else {}
    policies.update(overrides or {})
    events = [
        booked(inception, *lines),
        *(amended(3 + index, item, treatments) for index, (item, treatments) in enumerate(mods)),
    ]
    value = bundle(
        *events,
        products=[product(product_code, "TPL-TE")],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", product_code, ssp)], date(2020, 1, 1))],
        inception=inception,
        months=months,
        modifications=[item for item, _ in mods],
        overrides=policies or None,
    )
    templates = tuple(
        sorted(
            (*TEMPLATES, te_template(convention, distinctness=distinctness)),
            key=lambda t: t.template_code,
        )
    )
    return dataclasses.replace(value, pob_template_versions=templates)


@dataclasses.dataclass(frozen=True)
class Applied:
    """The inception fold and the states after each applied ``CONTRACT_AMENDED``."""

    ctx: BookContext
    identified: IdentifiedState
    events: tuple[EventView, ...]
    states: tuple[AllocatedState, ...]  # inception state first, then one per applied event
    tb: TraceBuilder
    blocked: tuple[EventView, AllocatedState] | None  # the refused event and the returned state

    @property
    def state(self) -> AllocatedState:
        return self.states[-1]


def run(value: InputBundle, booked_price: str) -> Applied:
    ctx = context(value)
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(value, scratch)
    identified = s02_contract_identification.run(ctx, cb, scratch)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, scratch), scratch)
    st = s05_allocation.run(ctx, priced, scratch)
    assert st.findings == ()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    price_at = price_function(booked_price)
    events = tuple(ev for ev in cb.boundary_events if ev.event_type == "CONTRACT_AMENDED")
    states = [st]
    blocked = None
    for ev in events:
        after = s06_modifications.apply(ctx, st, ev, tb, identified=identified, price_at=price_at)
        if any(finding.event_key == ev.event_key for finding in after.findings):
            blocked = (ev, after)
            break
        st = after
        states.append(after)
    return Applied(ctx, identified, events, tuple(states), tb, blocked)


def weight_node(nodes: Mapping[str, TraceNode], ev: EventView, key: str) -> TraceNode:
    return nodes[f"mod_weight@{ev.event_key}:{CONTRACT}/{key}:-"]


def share(nodes: Mapping[str, TraceNode], ev: EventView, key: str) -> str:
    return nodes[f"mod_share@{ev.event_key}:{CONTRACT}/{key}:-"].value


def exact(node: TraceNode) -> Fraction:
    """The exact weight the node's formula recomputes from its params (the value is a rendering)."""
    return formulas.FORMULAS[node.formula_id]([Fraction(0)] * len(node.inputs), node.params)


def scale_params(node: TraceNode) -> dict[str, str]:
    return {key: value for key, value in node.params.items() if key in SCALE_KEYS}


def accepted(applied: Applied) -> Mapping[str, TraceNode]:
    assert applied.blocked is None
    return checked(applied.tb)


# --- The MOD-JS-06 design world -------------------------------------------------------------------

JS06_LINES = (
    line("L1", "1", "40000.00", S, E),
    line("L2", "1", "40000.00", S2, E2),
    line("L3", "1", "40000.00", S3, E3),
)
JS06_KEYS = ("L1", "L2", "L3")


def js06_mod1(d: date = D1) -> Mod:
    """MOD-1: L3 removed for a 10,000.00 credit (the MOD-JS-06 schedule revision shape)."""
    return mod("MOD-1", d, [mod_line("L3", "REMOVE", SKU, "-1", "-10000.00")]), all_d(*JS06_KEYS)


def price_change(key: str, d: date, amount: str = "1000.00", *, name: str = "MOD-2") -> Mod:
    return (
        mod(name, d, [mod_line(key, "CHANGE", SKU, "0", amount)], kind="PRICE_CHANGE"),
        all_d(*JS06_KEYS),
    )


def test_s06_r11_time_elapsed_mod_js_06_world() -> None:
    applied = run(world(JS06_LINES, [js06_mod1()]), "120000.00")
    nodes = accepted(applied)
    (ev,) = applied.events
    l1 = weight_node(nodes, ev, "L1")
    assert (l1.formula_id, l1.value, exact(l1)) == (D18_FORMULA, "39000", Fraction(39000))
    assert l1.params["parts"] == "40000"  # the remaining unit's d SSP, unscaled in the parts
    assert scale_params(l1) == {
        "measure": "TIME_ELAPSED",
        "convention": "MONTHLY_EVEN",
        "term_start": "2026-07-01",
        "term_end": "2036-06-30",
        "progress_as_of": "2026-09-30",
        "layer_quantities": "1",
        "layer_starts": "2026-07-01",
        "layer_progress": "1/40",
        "remaining_scale": "39/40",
        "removed": "0",
    }
    l2 = weight_node(nodes, ev, "L2")  # unstarted: ρ = 1
    assert exact(l2) == 40000
    assert (l2.params["remaining_scale"], l2.params["layer_progress"], l2.params["term_start"]) == (
        "1",
        "0",
        "2027-07-01",
    )
    l3 = weight_node(nodes, ev, "L3")  # every unit removed: nothing to scale
    assert (exact(l3), l3.params["remaining_quantity"]) == (0, "0")
    assert "measure" not in l3.params
    assert nodes[f"mod_pool@{ev.event_key}:{CONTRACT}:-"].value == "109000.00"
    assert (share(nodes, ev, "L1"), share(nodes, ev, "L2"), share(nodes, ev, "L3")) == (
        "53810.13",
        "55189.87",
        "0.00",
    )
    # The segment after the boundary records the scaled weight (S08-R-05 reads it).
    assert obligation(applied.state, "L1").segments[-1].remaining_ssp == 39000


@pytest.mark.parametrize("d2", [date(2027, 4, 16), date(2027, 4, 1)])
def test_s06_r11_measured_on_the_term_in_force_at_every_boundary(d2: date) -> None:
    applied = run(world(JS06_LINES, [js06_mod1(), price_change("L2", d2)]), "120000.00")
    nodes = accepted(applied)
    _, ev2 = applied.events
    l1 = weight_node(nodes, ev2, "L1")
    assert exact(l1) == 37000
    assert (l1.params["remaining_scale"], l1.params["layer_progress"]) == ("37/40", "3/40")
    assert l1.params["progress_as_of"] == (d2 - timedelta(days=1)).isoformat()
    # ρ is never read from the progress g of the PROSPECTIVE segment since MOD-1 (6 of 117 months).
    before_state = applied.states[1]
    ob = obligation(before_state, "L1")
    measured = segments.measure(applied.ctx, before_state, ob, ob.segments[-1], ev2)
    assert (ob.segments[-1].basis, measured.progress) == ("PROSPECTIVE", Fraction(6, 117))
    assert 1 - measured.progress != Fraction(37, 40)
    assert (share(nodes, ev2, "L1"), share(nodes, ev2, "L2")) == ("51531.15", "55709.36")


@pytest.mark.parametrize(
    ("convention", "first", "first_shares", "second", "second_shares"),
    [
        (
            "MONTHLY_EVEN",
            Fraction(39000),
            ("53810.13", "55189.87"),
            Fraction(37000),
            ("51633.02", "55819.49"),
        ),
        (
            "MID_MONTH",
            Fraction(39000),
            ("53810.13", "55189.87"),
            Fraction(37000),
            ("51742.63", "55937.97"),
        ),
        (
            "DAILY",
            Fraction(141840000, 3653),
            ("53605.41", "55222.95"),
            Fraction(134560000, 3653),
            ("51333.50", "55743.54"),
        ),
    ],
)
def test_s06_r11_boundary_inside_a_period(
    convention: str,
    first: Fraction,
    first_shares: tuple[str, str],
    second: Fraction,
    second_shares: tuple[str, str],
) -> None:
    """[J] Inside a period under MONTHLY_EVEN or MID_MONTH the current period counts as
    remaining."""
    mods = [js06_mod1(date(2026, 10, 16)), price_change("L2", date(2027, 4, 16))]
    applied = run(world(JS06_LINES, mods, convention=convention), "120000.00")
    nodes = accepted(applied)
    ev1, ev2 = applied.events
    assert exact(weight_node(nodes, ev1, "L1")) == first
    assert weight_node(nodes, ev1, "L1").params["convention"] == convention
    assert (share(nodes, ev1, "L1"), share(nodes, ev1, "L2")) == first_shares
    assert exact(weight_node(nodes, ev2, "L1")) == second
    assert (share(nodes, ev2, "L1"), share(nodes, ev2, "L2")) == second_shares


@pytest.mark.parametrize(
    ("convention", "shares"),
    [
        ("MONTHLY_EVEN", ("39000.00", "40000.00", "40000.00")),
        ("MID_MONTH", ("39000.00", "40000.00", "40000.00")),
        ("DAILY", ("38828.36", "40000.00", "40000.00")),
    ],
)
def test_s06_r11_at_ssp_modification_moves_no_consideration(
    convention: str, shares: tuple[str, str, str]
) -> None:
    lines = (line("L1", "1", "40000.00", S, E), line("L2", "1", "40000.00", S2, E2))
    added = mod_line(
        "L3", "ADD", SKU, "1", "40000.00", start=date(2026, 10, 16), end=date(2036, 10, 15)
    )
    add = mod("MOD-1", date(2026, 10, 16), [added], kind="ADD_OBLIGATION"), all_d(*JS06_KEYS)
    applied = run(world(lines, [add], convention=convention), "80000.00")
    nodes = accepted(applied)
    (ev,) = applied.events
    assert tuple(share(nodes, ev, key) for key in JS06_KEYS) == shares
    l3 = weight_node(nodes, ev, "L3")  # an added obligation: its d SSP, no layers
    assert (exact(l3), "measure" in l3.params) == (40000, False)


def test_s06_r11_at_ssp_sequence_moves_no_consideration() -> None:
    lines = (line("L1", "1", "40000.00", S, E), line("L2", "1", "40000.00", S2, E2))
    added = mod_line("L3", "ADD", SKU, "1", "40000.00", start=D1, end=date(2036, 9, 30))
    add = mod("MOD-1", D1, [added], kind="ADD_OBLIGATION"), all_d(*JS06_KEYS)
    zero = price_change("L2", date(2027, 4, 1), "0.00")
    applied = run(world(lines, [add, zero]), "80000.00")
    nodes = accepted(applied)
    _, ev2 = applied.events
    assert [exact(weight_node(nodes, ev2, key)) for key in JS06_KEYS] == [37000, 40000, 38000]
    assert tuple(share(nodes, ev2, key) for key in JS06_KEYS) == (
        "37000.00",
        "40000.00",
        "38000.00",
    )
    l3 = weight_node(nodes, ev2, "L3")  # the added obligation is layered from its own start
    assert (l3.params["layer_starts"], l3.params["remaining_scale"]) == ("2026-10-01", "19/20")


def test_s06_r11_start_date_change_uses_the_term_in_force() -> None:
    lines = (line("L1", "1", "40000.00", S, E), line("L2", "1", "40000.00", S2, E2))
    defer = mod_line(
        "L2", "CHANGE", SKU, "0", "0.00", start=date(2028, 1, 1), end=date(2037, 6, 30)
    )
    later = l2_price(date(2027, 10, 1))
    applied = run(world(lines, [(mod("MOD-1", D1, [defer]), all_d("L1", "L2")), later]), "80000.00")
    nodes = accepted(applied)
    ev1, ev2 = applied.events
    assert (share(nodes, ev1, "L1"), share(nodes, ev1, "L2")) == ("39000.00", "40000.00")
    l1, l2 = weight_node(nodes, ev2, "L1"), weight_node(nodes, ev2, "L2")
    assert (exact(l1), l1.params["remaining_scale"]) == (35000, "7/8")
    assert (exact(l2), l2.params["remaining_scale"]) == (40000, "1")
    assert (l2.params["layer_starts"], l2.params["term_start"], l2.params["term_end"]) == (
        "2028-01-01",
        "2028-01-01",
        "2037-06-30",
    )
    assert (share(nodes, ev2, "L1"), share(nodes, ev2, "L2")) == ("35466.67", "40533.33")

    # MOD-1 also extends L1 to 30 Jun 2041 for 20,000.00: MOD-2 measures L1 on the extended term,
    # while MOD-1 itself weighed L1 on the term in force before it.
    extend = mod_line("L1", "CHANGE", SKU, "0", "20000.00", end=date(2041, 6, 30))
    both = mod("MOD-1", D1, [extend, defer]), all_d("L1", "L2")
    applied = run(world(lines, [both, later]), "80000.00")
    nodes = accepted(applied)
    ev1, ev2 = applied.events
    at_mod1 = weight_node(nodes, ev1, "L1")
    assert (exact(at_mod1), at_mod1.params["term_end"]) == (39000, "2036-06-30")
    at_mod2 = weight_node(nodes, ev2, "L1")
    assert (exact(at_mod2), at_mod2.params["remaining_scale"], at_mod2.params["term_end"]) == (
        Fraction(110000, 3),
        "11/12",
        "2041-06-30",
    )
    assert (share(nodes, ev2, "L1"), share(nodes, ev2, "L2")) == ("46241.39", "50445.16")


# --- Layered added units (seat-months) -----------------------------------------------------------

SEAT_START, SEAT_END = date(2026, 1, 1), date(2027, 12, 31)
SEAT_ADD_DATE = date(2026, 9, 16)


def seat_world(mods: Sequence[Mod], *, convention: str = "MONTHLY_EVEN") -> InputBundle:
    """POB-01: 2,400 seat-months at 100.00 over 2026 and 2027 (SSP 100.00 per seat-month)."""
    lines = (line("POB-01", "2400", "240000.00", SEAT_START, SEAT_END, product_code=SEATS),)
    return world(
        lines,
        mods,
        convention=convention,
        ssp="100.00",
        inception=SEAT_START,
        months=24,
        product_code=SEATS,
    )


def add_pob3(d: date, *keys: str) -> Mod:
    """MOD-2 adds POB-03 (1,200 seat-months for 100,000.00) beside the obligations ``keys``."""
    added = mod_line("POB-03", "ADD", SEATS, "1200", "100000.00", start=d, end=SEAT_END)
    return mod("MOD-2", d, [added], kind="ADD_OBLIGATION"), all_d(*keys, "POB-03")


ADDED_UNITS = (
    mod("MOD-1", SEAT_ADD_DATE, [mod_line("POB-01", "CHANGE", SEATS, "775", "60000.00")]),
    all_d("POB-01"),
)
NEW_OBLIGATION = (
    mod(
        "MOD-1",
        SEAT_ADD_DATE,
        [mod_line("POB-02", "ADD", SEATS, "775", "60000.00", start=SEAT_ADD_DATE, end=SEAT_END)],
        kind="ADD_OBLIGATION",
    ),
    all_d("POB-01", "POB-02"),
)


@pytest.mark.parametrize("d2", [date(2027, 1, 1), date(2027, 1, 16)])
def test_s06_r11_added_units_layered_symmetry(d2: date) -> None:
    # Added-units form: the 775 seat-months join POB-01 as a layer starting on 16 Sep 2026.
    applied = run(seat_world([ADDED_UNITS, add_pob3(d2, "POB-01")]), "240000.00")
    nodes = accepted(applied)
    ev1, ev2 = applied.events
    first = weight_node(nodes, ev1, "POB-01")
    assert (exact(first), first.params["parts"], first.params["remaining_scale"]) == (
        237500,
        "240000|77500",
        "2/3",
    )
    assert share(nodes, ev1, "POB-01") == "220000.00"
    second = weight_node(nodes, ev2, "POB-01")
    assert exact(second) == 180000
    assert scale_params(second) == {
        "measure": "TIME_ELAPSED",
        "convention": "MONTHLY_EVEN",
        "term_start": "2026-01-01",
        "term_end": "2027-12-31",
        "progress_as_of": (d2 - timedelta(days=1)).isoformat(),
        "layer_quantities": "2400|775",
        "layer_starts": "2026-01-01|2026-09-16",
        "layer_progress": "1/2|7/31",
        "remaining_scale": "72/127",
        "removed": "0",
    }
    assert (share(nodes, ev2, "POB-01"), share(nodes, ev2, "POB-03")) == ("162193.55", "108129.03")

    # New-obligation form: the same seat-months as POB-02 give the same remaining service.
    applied = run(seat_world([NEW_OBLIGATION, add_pob3(d2, "POB-01", "POB-02")]), "240000.00")
    nodes = accepted(applied)
    ev1, ev2 = applied.events
    assert [exact(weight_node(nodes, ev1, key)) for key in ("POB-01", "POB-02")] == [160000, 77500]
    assert (share(nodes, ev1, "POB-01"), share(nodes, ev1, "POB-02")) == ("148210.53", "71789.47")
    keys = ("POB-01", "POB-02", "POB-03")
    assert [exact(weight_node(nodes, ev2, key)) for key in keys] == [120000, 60000, 120000]
    pob2 = weight_node(nodes, ev2, "POB-02")
    assert (pob2.params["layer_starts"], pob2.params["remaining_scale"]) == ("2026-09-16", "24/31")
    assert tuple(share(nodes, ev2, key) for key in keys) == ("108129.03", "54064.52", "108129.03")


def test_s06_r11_added_units_layered_symmetry_daily() -> None:
    applied = run(
        seat_world([ADDED_UNITS, add_pob3(date(2027, 1, 1), "POB-01")], convention="DAILY"),
        "240000.00",
    )
    nodes = accepted(applied)
    _, ev2 = applied.events
    pob1 = weight_node(nodes, ev2, "POB-01")
    assert (exact(pob1), pob1.params["remaining_scale"]) == (Fraction(21231875, 118), "33971/59944")
    assert (share(nodes, ev2, "POB-01"), share(nodes, ev2, "POB-03")) == ("159814.52", "106583.78")

    applied = run(
        seat_world(
            [NEW_OBLIGATION, add_pob3(date(2027, 1, 1), "POB-01", "POB-02")], convention="DAILY"
        ),
        "240000.00",
    )
    nodes = accepted(applied)
    _, ev2 = applied.events
    pob2 = weight_node(nodes, ev2, "POB-02")
    assert (exact(pob2), pob2.params["remaining_scale"]) == (Fraction(7071875, 118), "365/472")
    keys = ("POB-01", "POB-02", "POB-03")
    assert tuple(share(nodes, ev2, key) for key in keys) == ("106583.78", "53230.74", "106583.78")


def test_s06_r11_removal_reduces_the_carried_units_before_scaling() -> None:
    lines = (line("L1", "3", "120000.00", S, E), line("L2", "1", "40000.00", S2, E2))
    remove = mod("MOD-1", D1, [mod_line("L1", "CHANGE", SKU, "-1", "-10000.00")]), all_d("L1", "L2")
    applied = run(world(lines, [remove]), "160000.00")
    nodes = accepted(applied)
    (ev,) = applied.events
    l1 = weight_node(nodes, ev, "L1")
    assert (exact(l1), l1.params["parts"]) == (78000, "80000")  # RQ⁰ = 2 at the carried 40,000
    assert (
        l1.params["remaining_quantity"],
        l1.params["removed"],
        l1.params["layer_quantities"],
    ) == (
        "2",
        "1",
        "3",
    )
    assert l1.params["remaining_scale"] == "39/40"
    assert exact(weight_node(nodes, ev, "L2")) == 40000
    assert (share(nodes, ev, "L1"), share(nodes, ev, "L2")) == ("97169.49", "49830.51")

    # Layered: MOD-2 removes 300 seat-months from POB-01 while adding POB-03; ρ is unchanged.
    removal = mod_line("POB-01", "CHANGE", SEATS, "-300", "-20000.00")
    added = mod_line(
        "POB-03", "ADD", SEATS, "1200", "100000.00", start=date(2027, 1, 1), end=SEAT_END
    )
    mod2 = mod("MOD-2", date(2027, 1, 1), [removal, added]), all_d("POB-01", "POB-03")
    applied = run(seat_world([ADDED_UNITS, mod2]), "240000.00")
    nodes = accepted(applied)
    _, ev2 = applied.events
    pob1 = weight_node(nodes, ev2, "POB-01")
    assert exact(pob1) == Fraction(20700000, 127)
    assert (
        pob1.params["remaining_quantity"],
        pob1.params["removed"],
        pob1.params["remaining_scale"],
    ) == (
        "2875",
        "300",
        "72/127",
    )
    assert pob1.params["layer_quantities"] == "2400|775"  # the layers before the event
    assert (share(nodes, ev2, "POB-01"), share(nodes, ev2, "POB-03")) == ("144175.78", "106146.80")


def test_s06_r11_series_units_and_class_n_unchanged() -> None:
    # A series takes the d SSP of its remaining increments: ρ = 1 and no layer params.
    applied = run(world(JS06_LINES, [js06_mod1()], distinctness="series"), "120000.00")
    nodes = accepted(applied)
    (ev,) = applied.events
    l1 = weight_node(nodes, ev, "L1")
    assert (exact(l1), "measure" in l1.params) == (40000, False)
    assert (share(nodes, ev, "L1"), share(nodes, ev, "L2")) == ("54500.00", "54500.00")
    # Units (CHK-028) and class N (CHK-042) weigh as before, without layer params.
    folded = fold(chk_028(mod_line("POB-01", "CHANGE", "SKU-P", "30", "2400.00"), after_units=True))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply_folded(folded, "12000.00", tb)
    assert after.findings == ()
    units = weight_node(checked(tb), folded.amended, "POB-01")
    assert (units.formula_id, "measure" in units.params, exact(units)) == (D18_FORMULA, False, 8550)
    folded = chk_042()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply_folded(folded, "120000.00", tb)
    assert after.findings == ()
    nodes = checked(tb)
    nondistinct = weight_node(nodes, folded.amended, "B")
    assert (nondistinct.params["class"], "measure" in nondistinct.params, exact(nondistinct)) == (
        "N",
        False,
        62500,
    )
    assert exact(weight_node(nodes, folded.amended, "C")) == 30000


@pytest.mark.parametrize(
    ("convention", "term", "price", "d", "rho", "weight"),
    [
        (
            "DAILY",
            (date(2027, 7, 1), date(2028, 6, 30)),
            "36600.00",
            date(2028, 3, 1),
            "1/3",
            Fraction(12200),
        ),
        (
            "MONTHLY_EVEN",
            (date(2028, 2, 10), date(2029, 2, 9)),
            "12000.00",
            date(2028, 2, 29),
            "9221/9753",
            Fraction(36884000, 3251),
        ),
        (
            "MONTHLY_EVEN",
            (date(2028, 2, 10), date(2029, 2, 9)),
            "12000.00",
            date(2028, 3, 1),
            "9193/9753",
            Fraction(36772000, 3251),
        ),
        (
            "MID_MONTH",
            (date(2028, 2, 10), date(2029, 2, 9)),
            "12000.00",
            date(2028, 2, 29),
            "1",
            Fraction(12000),
        ),
        (
            "MID_MONTH",
            (date(2028, 2, 10), date(2029, 2, 9)),
            "12000.00",
            date(2028, 3, 1),
            "11/12",
            Fraction(11000),
        ),
    ],
)
def test_s06_r11_leap_year(
    convention: str, term: tuple[date, date], price: str, d: date, rho: str, weight: Fraction
) -> None:
    start, end = term
    lines = (line("L1", "1", price, start, end),)
    change = mod("MOD-1", d, [mod_line("L1", "CHANGE", SKU, "0", "1000.00")], kind="PRICE_CHANGE")
    value = world(
        lines,
        [(change, all_d("L1"))],
        convention=convention,
        ssp=price,
        inception=date(2027, 7, 1),
        months=24,
    )
    applied = run(value, price)
    nodes = accepted(applied)
    (ev,) = applied.events
    l1 = weight_node(nodes, ev, "L1")
    assert (l1.params["remaining_scale"], exact(l1)) == (rho, weight)


def test_s06_r11_inception_all_scales_the_carried_units() -> None:
    mods = [js06_mod1(), price_change("L2", date(2027, 4, 16))]
    applied = run(
        world(JS06_LINES, mods, overrides={"mod.ssp_basis": "INCEPTION_ALL"}), "120000.00"
    )
    nodes = accepted(applied)
    ev1, ev2 = applied.events
    l1 = weight_node(nodes, ev1, "L1")
    assert (l1.formula_id, exact(l1)) == (INCEPTION_ALL_FORMULA, 39000)
    assert (l1.params["remaining_quantity"], l1.params["u0"], l1.params["remaining_scale"]) == (
        "1",
        "40000",
        "39/40",
    )
    assert l1.params["parts"] == ""  # no added units; the carried units live in the params
    assert (share(nodes, ev1, "L1"), share(nodes, ev1, "L2")) == ("53810.13", "55189.87")
    assert exact(weight_node(nodes, ev2, "L1")) == 37000
    assert (share(nodes, ev2, "L1"), share(nodes, ev2, "L2")) == ("51531.15", "55709.36")


def test_s06_r11_fixtures_pin_the_time_convention() -> None:
    pinned = run(world(JS06_LINES, [js06_mod1()], convention="MONTHLY_EVEN"), "120000.00")
    assert obligation(pinned.states[0], "L1").ratable_convention == RatableConvention.MONTHLY_EVEN
    node = weight_node(accepted(pinned), pinned.events[0], "L1")
    assert (node.params["convention"], exact(node)) == ("MONTHLY_EVEN", 39000)
    # Without the pin the resolved POL-090 value overrides the template's MONTHLY_EVEN.
    unpinned = run(
        world(JS06_LINES, [js06_mod1()], convention="MONTHLY_EVEN", pinned=False), "120000.00"
    )
    assert obligation(unpinned.states[0], "L1").ratable_convention == RatableConvention.DAILY
    node = weight_node(accepted(unpinned), unpinned.events[0], "L1")
    assert (node.params["convention"], exact(node)) == ("DAILY", Fraction(142440000, 3653))


# --- Fail closed ----------------------------------------------------------------------------------


def test_s06_r11_fails_closed() -> None:
    applied = run(world(JS06_LINES, [js06_mod1()]), "120000.00")
    (ev,) = applied.events
    ctx, st = applied.ctx, applied.states[0]
    ob = obligation(st, "L1")
    (seg,) = ob.segments
    before = segments.measure(ctx, st, ob, seg, ev)
    rho, params = segments.remaining_scale(ctx, ob, before, ev, removed=Fraction(0))
    assert (rho, params["remaining_scale"], params["removed"]) == (Fraction(39, 40), "39/40", "0")

    def invariant(call: object) -> EngineError:
        with pytest.raises(EngineError) as caught:
            call()  # type: ignore[operator]
        assert (caught.value.code, caught.value.detail["rule"]) == (
            "ENGINE_INVARIANT_VIOLATED",
            "S06-R-11",
        )
        return caught.value

    # (a) the layers do not reconcile with the remaining quantity before the event
    forged = dataclasses.replace(before, remaining_quantity=Fraction(2))
    error = invariant(lambda: segments.remaining_scale(ctx, ob, forged, ev, removed=Fraction(0)))
    assert "do not sum to the remaining quantity" in error.message
    # a segment in force absent from the FIXED history
    stray = dataclasses.replace(seg)
    invariant(lambda: segments.unit_layers(ob, stray, S))
    # a boundary other than a modification or a material-right exercise changes the quantity
    two = dataclasses.replace(seg.totals, quantity=Fraction(2))
    changed = dataclasses.replace(
        seg,
        cause=SegmentCause.TP_CHANGE,
        effective_date=date(2026, 9, 1),
        event_key="EV-FORGED",
        totals=two,
    )
    error = invariant(
        lambda: segments.unit_layers(dataclasses.replace(ob, segments=(seg, changed)), changed, S)
    )
    assert error.detail["cause"] == "TP_CHANGE"
    # the OPENING_BALANCE carve-out: a layer reset at the opening start
    opening = dataclasses.replace(
        changed,
        cause=SegmentCause.OPENING_BALANCE,
        totals=dataclasses.replace(two, start_date=date(2026, 9, 1)),
    )
    layers = segments.unit_layers(dataclasses.replace(ob, segments=(seg, opening)), opening, S)
    assert layers == ((Fraction(2), date(2026, 9, 1)),)
    # (b) ρ = 0: the term in force ended before the boundary
    ended = dataclasses.replace(
        seg, totals=dataclasses.replace(seg.totals, end_date=date(2026, 8, 31))
    )
    error = invariant(
        lambda: segments.remaining_scale(
            ctx,
            dataclasses.replace(ob, segments=(ended,)),
            dataclasses.replace(before, segment=ended),
            ev,
            removed=Fraction(0),
        )
    )
    assert "no remaining service" in error.message


# --- Formula re-evaluation (CV-52; DG-ENG-04) -----------------------------------------------------

JS06_PARAMS: Mapping[str, str] = {
    "as_of": "2026-10-01",
    "basis": "D18_DEFAULT",
    "class": "D",
    "parts": "40000",
    "remaining_quantity": "1",
    "unit_price": "40000",
    "measure": "TIME_ELAPSED",
    "convention": "MONTHLY_EVEN",
    "term_start": "2026-07-01",
    "term_end": "2036-06-30",
    "progress_as_of": "2026-09-30",
    "layer_quantities": "1",
    "layer_starts": "2026-07-01",
    "layer_progress": "1/40",
    "remaining_scale": "39/40",
    "removed": "0",
}


def evaluate(formula_id: str, params: Mapping[str, str]) -> Fraction:
    parts = [part for part in params["parts"].split("|") if part]
    return formulas.FORMULAS[formula_id]([Fraction(0)] * len(parts), params)


def test_mod_weights_formulas_recompute_the_remaining_scale_exactly() -> None:
    assert evaluate(D18_FORMULA, JS06_PARAMS) == 39000
    daily = {
        **JS06_PARAMS,
        "as_of": "2026-10-16",
        "progress_as_of": "2026-10-15",
        "convention": "DAILY",
        "layer_progress": "107/3653",
        "remaining_scale": "3546/3653",
    }
    assert evaluate(D18_FORMULA, daily) == Fraction(141840000, 3653)
    layered = {
        **JS06_PARAMS,
        "parts": "80000|40000",
        "remaining_quantity": "2",
        "layer_quantities": "1|1",
        "layer_starts": "2026-07-01|2026-10-01",
        "layer_progress": "1/40|0",
        "remaining_scale": "79/80",
    }
    assert evaluate(D18_FORMULA, layered) == 80000 * Fraction(79, 80) + 40000  # added part unscaled
    # A node without measure evaluates as before: Σ parts.
    plain = {key: value for key, value in JS06_PARAMS.items() if key not in SCALE_KEYS}
    assert evaluate(D18_FORMULA, plain) == 40000
    # INCEPTION_ALL: ρ × remaining_quantity × u0 + Σ parts.
    inception_all = {**JS06_PARAMS, "basis": "INCEPTION_ALL", "parts": "", "u0": "40000"}
    assert evaluate(INCEPTION_ALL_FORMULA, inception_all) == 39000
    assert evaluate(INCEPTION_ALL_FORMULA, {**inception_all, "parts": "5000"}) == 44000
    plain_all = {key: value for key, value in inception_all.items() if key not in SCALE_KEYS}
    assert evaluate(INCEPTION_ALL_FORMULA, plain_all) == 40000


@pytest.mark.parametrize(
    "mutation",
    [
        {"remaining_scale": "1"},
        {"layer_progress": "1/41"},
        {"progress_as_of": "2026-10-01"},
        {"measure": "UNITS_DELIVERED"},
        {"parts": ""},
        {"layer_starts": "2026-08-01"},
        {"layer_starts": "2026-06-01"},  # before the term in force
        {"convention": "DAILY"},
        {"term_end": "2036-06-29"},
        {
            "layer_quantities": "1|1",
            "layer_starts": "2026-07-01|2026-10-01",
            "layer_progress": "1/40|0",
            "remaining_scale": "79/80",
        },
        {"removed": "1"},
        {"layer_quantities": "1|1"},
    ],
    ids=str,
)
def test_mod_weights_formulas_fail_on_mutated_params(mutation: Mapping[str, str]) -> None:
    """The layers, their progress, ρ and Σ q_L = remaining_quantity + removed are all re-derived."""
    with pytest.raises(ValueError):
        evaluate(D18_FORMULA, {**JS06_PARAMS, **mutation})
    if mutation == {"parts": ""}:
        return  # INCEPTION_ALL carries the remaining units in its params, not in a part
    with pytest.raises(ValueError):
        evaluate(INCEPTION_ALL_FORMULA, {**JS06_PARAMS, "parts": "", "u0": "40000", **mutation})


def test_s06_r11_trace_ties_the_layers_to_the_remaining_quantity_plus_removed_units() -> None:
    lines = (line("L1", "3", "120000.00", S, E), line("L2", "1", "40000.00", S2, E2))
    remove = mod("MOD-1", D1, [mod_line("L1", "CHANGE", SKU, "-1", "-10000.00")]), all_d("L1", "L2")
    applied = run(world(lines, [remove]), "160000.00")
    trace = applied.tb.build(root_measures={})
    (ev,) = applied.events
    node_id = f"mod_weight@{ev.event_key}:{CONTRACT}/L1:-"
    node = next(item for item in trace.nodes if item.id == node_id)
    assert (
        node.params["layer_quantities"],
        node.params["remaining_quantity"],
        node.params["removed"],
    ) == (
        "3",
        "2",
        "1",
    )
    assert reevaluate(trace)[node_id] == node.value

    def mutated(**params: str) -> None:
        nodes = tuple(
            dataclasses.replace(item, params={**item.params, **params})
            if item.id == node_id
            else item
            for item in trace.nodes
        )
        with pytest.raises(ValueError):
            reevaluate(dataclasses.replace(trace, nodes=nodes))

    mutated(removed="0")  # Σ layers 3 ≠ remaining 2 + removed 0
    mutated(layer_quantities="2")  # Σ layers 2 ≠ 2 + 1
    mutated(
        layer_quantities="2|1", layer_starts="2026-07-01|2026-08-01", layer_progress="1/40|1/119"
    )
    mutated(layer_starts="2026-08-01")


@pytest.mark.parametrize("convention", ["DAILY", "MONTHLY_EVEN", "MID_MONTH"])
def test_s06_r11_single_layer_equals_one_minus_inception_progress_at_every_date(
    convention: str,
) -> None:
    applied = run(world(JS06_LINES, [js06_mod1()], convention=convention), "120000.00")
    (ev,) = applied.events
    ctx, st = applied.ctx, applied.states[0]
    ob = obligation(st, "L1")
    (seg,) = ob.segments
    for offset in range((E - S).days + 1):
        d = S + timedelta(days=offset)
        probe = dataclasses.replace(ev, effective_date=d)
        before = segments.measure(ctx, st, ob, seg, probe)
        rho, params = segments.remaining_scale(ctx, ob, before, probe, removed=Fraction(0))
        expected = 1 - progress.time_fraction(convention, S, E, d - timedelta(days=1))
        assert rho == expected == 1 - before.progress, d
        assert params["progress_as_of"] == (d - timedelta(days=1)).isoformat()


# --- MOD_UNIT_HISTORY_AMBIGUOUS (S06-R-08; layer-lineage review worlds W1 and W2) -----------------

W1_LINES = (line("L1", "2", "80000.00", S, E), line("L2", "1", "40000.00", S2, E2))
REMOVE_ONE = mod_line("L1", "REMOVE", SKU, "-1", "-10000.00")
LESS_ONE = mod_line("L1", "CHANGE", SKU, "-1", "-10000.00")
ADD_ONE = mod_line("L1", "CHANGE", SKU, "1", "40000.00")
EXPLICIT_W1 = Fraction(
    2923000, 39
)  # 80,000 × (111/120 + 111/117) ÷ 2: old units from s, new unit from d1


def w1(mods: Sequence[Mod], *, convention: str = "MONTHLY_EVEN") -> InputBundle:
    return world(W1_LINES, mods, convention=convention)


def l2_price(d: date, *, name: str = "MOD-2") -> Mod:
    return (
        mod(name, d, [mod_line("L2", "CHANGE", SKU, "0", "1000.00")], kind="PRICE_CHANGE"),
        all_d("L1", "L2"),
    )


def assert_refused(applied: Applied, name: str, key: str, reason: str, **detail: str) -> EventView:
    """The event ``name`` is blocked by one ``MOD_UNIT_HISTORY_AMBIGUOUS`` finding on ``key``."""
    assert applied.blocked is not None
    ev, after = applied.blocked
    assert ev.payload["modification_id"] == name
    found = [finding for finding in after.findings if finding.event_key == ev.event_key]
    assert [(f.code, f.severity, f.subject_key, f.stage) for f in found] == [
        ("MOD_UNIT_HISTORY_AMBIGUOUS", "ERROR", f"{CONTRACT}/{key}", 6)
    ]
    expected = {
        "modification_key": name,
        "obligation_key": key,
        "rule": "S06-R-08",
        "reason": reason,
        **detail,
    }
    assert {name: found[0].detail[name] for name in expected} == expected
    assert after.obligations == applied.state.obligations  # blocked: nothing appended (CV-15)
    nodes = applied.tb.build(root_measures={}).nodes
    assert not any(node.id.startswith(f"mod_weight@{ev.event_key}:") for node in nodes)
    return ev


@pytest.mark.parametrize(
    ("lines", "convention", "d1"),
    [
        ((REMOVE_ONE, ADD_ONE), "MONTHLY_EVEN", D1),
        ((LESS_ONE, ADD_ONE), "MONTHLY_EVEN", D1),
        ((ADD_ONE, REMOVE_ONE), "DAILY", date(2026, 10, 16)),
    ],
)
def test_s06_r08_w1_mixed_event_refused(
    lines: Sequence[Mapping[str, object]], convention: str, d1: date
) -> None:
    mods = [(mod("MOD-1", d1, lines), all_d("L1", "L2")), l2_price(date(2027, 4, 1))]
    applied = run(w1(mods, convention=convention), "120000.00")
    assert_refused(
        applied, "MOD-1", "L1", "MIXED_SIGNS", added="1", removed="1", term_start="2026-07-01"
    )
    assert len(applied.states) == 1  # the first event is refused: no node at all
    assert applied.tb.build(root_measures={}).nodes == ()


def test_s06_r08_net_and_same_sign_histories_accepted() -> None:
    # A net price-only change keeps one layer.
    net = mod("MOD-1", D1, [mod_line("L1", "CHANGE", SKU, "0", "30000.00")]), all_d("L1", "L2")
    applied = run(w1([net, l2_price(date(2027, 4, 1))]), "120000.00")
    nodes = accepted(applied)
    l1 = weight_node(nodes, applied.events[1], "L1")
    assert (exact(l1), l1.params["layer_quantities"], l1.params["remaining_scale"]) == (
        74000,
        "2",
        "37/40",
    )
    # Two lines of the same sign on one obligation are one layer of their sum.
    twice = mod("MOD-1", D1, [ADD_ONE, ADD_ONE]), all_d("L1", "L2")
    applied = run(w1([twice, l2_price(date(2027, 4, 1))]), "120000.00")
    nodes = accepted(applied)
    l1 = weight_node(nodes, applied.events[1], "L1")
    assert (l1.params["layer_quantities"], l1.params["layer_starts"]) == (
        "2|2",
        "2026-07-01|2026-10-01",
    )
    assert exact(l1) == 160000 * Fraction(2923, 3120)


@pytest.mark.parametrize(
    ("convention", "removal", "addition", "d2", "rho", "weight"),
    [
        ("MONTHLY_EVEN", date(2026, 9, 30), D1, date(2027, 4, 1), "2923/3120", EXPLICIT_W1),
        (
            "DAILY",
            date(2026, 10, 15),
            date(2026, 10, 16),
            date(2027, 4, 16),
            "6054359/6476769",
            Fraction(484348720000, 6476769),
        ),
    ],
)
def test_s06_r08_split_removal_first_equals_the_explicit_representation(
    convention: str, removal: date, addition: date, d2: date, rho: str, weight: Fraction
) -> None:
    """The removal recorded the day before the addition reconstructs the old-unit/new-unit
    layers."""
    mods = [
        (mod("MOD-1a", removal, [LESS_ONE]), all_d("L1", "L2")),
        (mod("MOD-1b", addition, [ADD_ONE]), all_d("L1", "L2")),
        l2_price(d2),
    ]
    applied = run(w1(mods, convention=convention), "120000.00")
    nodes = accepted(applied)
    l1 = weight_node(nodes, applied.events[2], "L1")
    assert (exact(l1), l1.params["parts"], l1.params["remaining_scale"]) == (weight, "80000", rho)
    assert (l1.params["layer_quantities"], l1.params["layer_starts"]) == (
        "1|1",
        f"2026-07-01|{addition.isoformat()}",
    )


def same_date_fixed_segments(
    applied: Applied, key: str, d: date
) -> list[tuple[str | None, Fraction]]:
    """(event key, quantity) of the ``FIXED`` ``MODIFICATION`` segments of ``key`` effective on
    ``d``: one per same-date boundary (D-90c)."""
    ob = obligation(applied.state, key)
    return [
        (seg.event_key, seg.totals.quantity)
        for seg in ob.segments
        if seg.component == segments.FIXED
        and seg.effective_date == d
        and seg.cause == SegmentCause.MODIFICATION
    ]


def test_s06_r08_same_date_removal_first_equals_the_explicit_representation() -> None:
    """D-90c: two modifications effective on one date are applied in event order, each a boundary
    of its own. Removal first keeps the remaining booked unit at s_p and adds the new unit at d:
    the explicit old-unit/new-unit representation of the W1 review world (2,923,000/39)."""
    mods = [
        (mod("MOD-1a", D1, [LESS_ONE]), all_d("L1", "L2")),
        (mod("MOD-1b", D1, [ADD_ONE]), all_d("L1", "L2")),
        l2_price(date(2027, 4, 1)),
    ]
    applied = run(w1(mods), "120000.00")
    nodes = accepted(applied)
    ev1, ev2, ev3 = applied.events
    assert same_date_fixed_segments(applied, "L1", D1) == [
        (ev1.event_key, Fraction(1)),
        (ev2.event_key, Fraction(2)),
    ]
    l1 = weight_node(nodes, ev3, "L1")
    assert (exact(l1), l1.params["parts"], l1.params["remaining_scale"]) == (
        EXPLICIT_W1,
        "80000",
        "2923/3120",
    )
    assert (l1.params["layer_quantities"], l1.params["layer_starts"]) == (
        "1|1",
        "2026-07-01|2026-10-01",
    )
    # MOD-1b itself weighs L1 on the layers MOD-1a left: one remaining unit at s_p.
    at_addition = weight_node(nodes, ev2, "L1")
    assert (at_addition.params["layer_quantities"], at_addition.params["layer_starts"]) == (
        "1",
        "2026-07-01",
    )


def test_s06_r08_same_date_addition_first_accepted_pro_rata() -> None:
    """D-90c: addition then removal on one date reduces every layer pro rata (the D-90b decrease
    rule): the 2 booked units at s_p and the unit added at d become 4/3 and 2/3. The order is the
    preparer's representation of which units were removed, so the weight differs from the
    removal-first history."""
    mods = [
        (mod("MOD-1a", D1, [ADD_ONE]), all_d("L1", "L2")),
        (mod("MOD-1b", D1, [LESS_ONE]), all_d("L1", "L2")),
        l2_price(date(2027, 4, 1)),
    ]
    applied = run(w1(mods), "120000.00")
    nodes = accepted(applied)
    ev1, ev2, ev3 = applied.events
    assert same_date_fixed_segments(applied, "L1", D1) == [
        (ev1.event_key, Fraction(3)),
        (ev2.event_key, Fraction(2)),
    ]
    l1 = weight_node(nodes, ev3, "L1")
    # 80,000 × (4/3 × 111/120 + 2/3 × 111/117) ÷ 2 = 8,732,000/117 (74,632.48).
    assert exact(l1) == Fraction(8732000, 117)
    assert exact(l1) != EXPLICIT_W1
    assert (
        l1.params["layer_quantities"],
        l1.params["layer_starts"],
        l1.params["layer_progress"],
    ) == ("4/3|2/3", "2026-07-01|2026-10-01", "3/40|2/39")
    assert (l1.params["remaining_quantity"], l1.params["remaining_scale"]) == ("2", "2183/2340")


REVIEW_LINES = (
    line("L1", "10", "10000.00", date(2026, 1, 1), date(2026, 12, 31)),
    line("L2", "1", "1000.00", date(2027, 1, 1), date(2027, 12, 31)),
)
REVIEW_D = date(2026, 3, 1)
LESS_FIVE = mod_line("L1", "REMOVE", SKU, "-5", "-5000.00")
ADD_FIVE = mod_line("L1", "CHANGE", SKU, "5", "5000.00")


@pytest.mark.parametrize(
    ("first", "second", "quantities", "layers", "rho", "weight"),
    [
        (LESS_FIVE, ADD_FIVE, ("5", "10"), "5|5", "11/40", Fraction(2750)),
        (ADD_FIVE, LESS_FIVE, ("15", "10"), "20/3|10/3", "4/15", Fraction(8000, 3)),
    ],
    ids=["removal-first", "addition-first"],
)
def test_s06_r08_d90c_review_world_same_date_orders(
    first: Mapping[str, object],
    second: Mapping[str, object],
    quantities: tuple[str, str],
    layers: str,
    rho: str,
    weight: Fraction,
) -> None:
    """The D-90c figures: a one-year MONTHLY_EVEN service from 1 January, ten booked units,
    changes on 1 March, measured on 1 October at a 1,000 full-term unit SSP. Remove five then add
    five: layers 5 at 1 January and 5 at 1 March, ρ = 11/40, weight 2,750. Add five then remove
    five: 20/3 and 10/3, ρ = 4/15, weight 8,000/3 (2,666.67 before rounding)."""
    mods = [
        (mod("MOD-1a", REVIEW_D, [first]), all_d("L1", "L2")),
        (mod("MOD-1b", REVIEW_D, [second]), all_d("L1", "L2")),
        (
            mod(
                "MOD-2",
                date(2026, 10, 1),
                [mod_line("L2", "CHANGE", SKU, "0", "100.00")],
                kind="PRICE_CHANGE",
            ),
            all_d("L1", "L2"),
        ),
    ]
    applied = run(world(REVIEW_LINES, mods, ssp="1000.00"), "11000.00")
    nodes = accepted(applied)
    _, _, ev3 = applied.events
    assert [q for _, q in same_date_fixed_segments(applied, "L1", REVIEW_D)] == [
        Fraction(q) for q in quantities
    ]
    l1 = weight_node(nodes, ev3, "L1")
    assert (exact(l1), l1.params["parts"], l1.params["remaining_scale"]) == (weight, "10000", rho)
    assert (
        l1.params["layer_quantities"],
        l1.params["layer_starts"],
        l1.params["layer_progress"],
    ) == (layers, "2026-01-01|2026-03-01", "3/4|7/10")
    assert l1.params["remaining_quantity"] == "10"
    assert exact(weight_node(nodes, ev3, "L2")) == 1000  # unstarted on 1 October: ρ = 1


def test_s06_r08_class_n_mixed_history_refused_before_a_class_d_event() -> None:
    treatments = {"L1": N, "L2": D18}
    mixed = mod("MOD-1", D1, [REMOVE_ONE, ADD_ONE]), treatments
    applied = run(w1([mixed, l2_price(date(2027, 4, 1))]), "120000.00")
    assert_refused(applied, "MOD-1", "L1", "MIXED_SIGNS", added="1", removed="1")
    # The class N split on adjacent dates carries the explicit layers into the later class D event.
    mods = [
        (mod("MOD-1a", date(2026, 9, 30), [LESS_ONE]), treatments),
        (mod("MOD-1b", D1, [ADD_ONE]), treatments),
        l2_price(date(2027, 4, 1)),
    ]
    applied = run(w1(mods), "120000.00")
    nodes = accepted(applied)
    ev1, ev2, ev3 = applied.events
    assert weight_node(nodes, ev2, "L1").params["class"] == "N"
    assert obligation(applied.states[2], "L1").segments[-1].basis == "INCEPTION"
    l1 = weight_node(nodes, ev3, "L1")
    assert (l1.params["class"], exact(l1), l1.params["layer_quantities"]) == (
        "D",
        EXPLICIT_W1,
        "1|1",
    )


def test_s06_r08_pre_start_mixed_event_accepted() -> None:
    before_start = [
        mod_line("L2", "REMOVE", SKU, "-1", "-5000.00"),
        mod_line("L2", "CHANGE", SKU, "1", "40000.00"),
    ]
    mods = [
        (mod("MOD-1", D1, before_start), all_d("L1", "L2")),
        (
            mod(
                "MOD-2",
                date(2027, 10, 1),
                [mod_line("L1", "CHANGE", SKU, "0", "1000.00")],
                kind="PRICE_CHANGE",
            ),
            all_d("L1", "L2"),
        ),
    ]
    applied = run(w1(mods), "120000.00")
    nodes = accepted(applied)  # L2 has not started on 1 Oct 2026: max(d, s_p) = s_p for every unit
    _, ev2 = applied.events
    l2 = weight_node(nodes, ev2, "L2")
    assert (exact(l2), l2.params["layer_quantities"], l2.params["layer_starts"]) == (
        39000,
        "1",
        "2027-07-01",
    )
    assert l2.params["remaining_scale"] == "39/40"
    l1 = weight_node(nodes, ev2, "L1")
    assert (exact(l1), l1.params["remaining_scale"]) == (70000, "7/8")


def test_s06_r08_re_terming_added_unit_line_refused() -> None:
    re_termed = mod_line("L1", "CHANGE", SKU, "1", "40000.00", start=D1)
    applied = run(
        w1([(mod("MOD-1", D1, [re_termed]), all_d("L1", "L2")), l2_price(date(2027, 4, 1))]),
        "120000.00",
    )
    assert_refused(
        applied,
        "MOD-1",
        "L1",
        "RE_TERMED_ADDED_UNITS",
        added="1",
        removed="0",
        start_date="2026-10-01",
    )
    # The start of the term in force is not a re-terming.
    kept = mod_line("L1", "CHANGE", SKU, "1", "40000.00", start=S)
    applied = run(
        w1([(mod("MOD-1", D1, [kept]), all_d("L1", "L2")), l2_price(date(2027, 4, 1))]), "120000.00"
    )
    nodes = accepted(applied)
    l1 = weight_node(nodes, applied.events[1], "L1")
    assert (l1.params["layer_quantities"], l1.params["layer_starts"]) == (
        "2|1",
        "2026-07-01|2026-10-01",
    )
    # A mixed and re-termed event reports the mixed signs.
    applied = run(w1([(mod("MOD-1", D1, [REMOVE_ONE, re_termed]), all_d("L1", "L2"))]), "120000.00")
    assert_refused(applied, "MOD-1", "L1", "MIXED_SIGNS")
    # An unstarted obligation may be re-termed by an added-unit line (d ≤ s_p).
    unstarted = mod_line(
        "L2", "CHANGE", SKU, "1", "40000.00", start=date(2027, 10, 1), end=date(2037, 9, 30)
    )
    applied = run(w1([(mod("MOD-1", D1, [unstarted]), all_d("L1", "L2"))]), "120000.00")
    nodes = accepted(applied)
    assert exact(weight_node(nodes, applied.events[0], "L2")) == 80000


def test_s06_r08_w2_pro_rata_sequential_attribution() -> None:
    """An earlier decrease reduces every layer pro rata (documented decrease rule)."""
    mods = [
        (mod("MOD-0", D1, [ADD_ONE]), all_d("L1", "L2")),
        (mod("MOD-1a", date(2026, 12, 31), [LESS_ONE]), all_d("L1", "L2")),
        (mod("MOD-1b", date(2027, 1, 1), [ADD_ONE]), all_d("L1", "L2")),
        l2_price(date(2027, 4, 1)),
    ]
    applied = run(w1(mods), "120000.00")
    nodes = accepted(applied)
    l1 = weight_node(nodes, applied.events[3], "L1")
    assert exact(l1) == Fraction(252488000, 2223)
    assert (
        l1.params["layer_quantities"],
        l1.params["layer_starts"],
        l1.params["layer_progress"],
    ) == (
        "4/3|2/3|1",
        "2026-07-01|2026-10-01|2027-01-01",
        "3/40|2/39|1/38",
    )
    assert (l1.params["remaining_quantity"], l1.params["remaining_scale"]) == ("3", "31561/33345")
    # The same swap as one mixed event on 1 Jan 2027 is refused.
    mixed = [
        (mod("MOD-0", D1, [ADD_ONE]), all_d("L1", "L2")),
        (mod("MOD-1", date(2027, 1, 1), [REMOVE_ONE, ADD_ONE]), all_d("L1", "L2")),
        l2_price(date(2027, 4, 1)),
    ]
    applied = run(w1(mixed), "120000.00")
    assert_refused(applied, "MOD-1", "L1", "MIXED_SIGNS")
    assert len(applied.states) == 2
