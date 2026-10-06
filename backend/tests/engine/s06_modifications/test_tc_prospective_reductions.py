"""Stage 06 price-only changes and reductions: legacy 03 TC-08, TC-09, legacy 04 TC-RM-15 (ENB-3).

ENGINE_SPEC §6.3 S06-R-08, S06-R-09, S06-R-11 to S06-R-14; legacy 03 §6.4 (D-06 P-05, D-07 P-11)
and §7.3; legacy 04 §7.3. The probe scripts of P-05 and P-11 live outside the repository (legacy 03
§7.3 scratch folder), so the tests rebuild the probe contracts from the TC figures. TC-RM-15 runs
over ``golden_streams.stream("Contract 3", "11")``. The fake stage 04 price function follows the
§4.2 contract (D-81). Every stage 06 trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal

from erev_engine import ENGINE_VERSION, guards
from erev_engine.canonical import sha256_hex
from erev_engine.enums import ObligationKind
from erev_engine.money import format_money
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
    s06_modifications,
)
from erev_engine.trace import TraceBuilder
from support import bundles, golden_streams
from test_s06_prospective import (
    INCEPTION,
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
    price_function,
    product,
    ssp_version,
    usd,
)


def test_tc_prospective_08_price_only_on_satisfied_pob() -> None:
    """P-05: a fully delivered contract; B +50.00 with quantity 0 (legacy dropped the pool)."""
    d = date(2026, 4, 15)
    modification = modification_input(
        "MOD-P05", d, [mod_line("B", "CHANGE", "SKU-B", "0", "50.00")], kind="VC_CHANGE"
    )
    value = bundle(
        booked(INCEPTION, bundles.booking_line("B", product_code="SKU-B", total_price="180.00")),
        delivered(3, "B", "1", date(2026, 3, 31)),
        amended(4, modification, {}),
        products=[product("SKU-B", "TPL-UNITS")],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", "SKU-B", "180.00")], date(2025, 1, 1))],
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
        price_at=price_function("180.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    assert nodes[f"satisfied_share@{ev.event_key}:K-01/B:-"].value == "50.00"
    assert nodes[f"catch_up@{ev.event_key}:K-01/B:-"].value == "50.00"  # recognised at d
    segment = obligation(after, "B").segments[-1]
    assert (segment.basis, segment.a_posted, segment.x_exact) == ("INCEPTION", usd("230.00"), 230)
    # TP 180.00 → 230.00 and every minor unit is allocated: no consideration is dropped.
    assert after.tp_history[-1].allocation_basis.posted == usd("230.00")
    assert nodes[f"mod_pool@{ev.event_key}:K-01:-"].value == "0.00"


def test_tc_prospective_09_remove_remaining_units() -> None:
    """P-11: hardware 3 at 360.00 (1 delivered), consulting 1 at 150.00 (0.4 delivered), TP 510."""
    d = date(2026, 4, 15)
    modification = modification_input(
        "MOD-P11",
        d,
        [mod_line("POB-HW", "REMOVE", "Hardware 1", "-2", "0.00")],
        kind="QUANTITY_CHANGE",
    )
    value = bundle(
        booked(
            INCEPTION,
            bundles.booking_line(
                "POB-HW", product_code="Hardware 1", quantity="3", total_price="360.00"
            ),
            bundles.booking_line("POB-CONS", product_code="Consulting 1", total_price="150.00"),
        ),
        delivered(3, "POB-HW", "1", date(2026, 2, 28)),
        delivered(4, "POB-CONS", "0.4", date(2026, 2, 28)),
        amended(5, modification, {"POB-HW": "PROSPECTIVE", "POB-CONS": "PROSPECTIVE"}),
        products=[product("Hardware 1", "TPL-UNITS"), product("Consulting 1", "TPL-UNITS")],
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "Hardware 1", "120.00"),
                    point_entry("SSP-US@v1", "Consulting 1", "150.00"),
                ],
                date(2025, 1, 1),
            )
        ],
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
        price_at=price_function("510.00"),
    )
    assert after.findings == ()
    nodes = checked(tb)
    hardware = obligation(after, "POB-HW").segments[-1]
    weight = nodes[f"mod_weight@{ev.event_key}:K-01/POB-HW:-"]
    assert (weight.value, weight.params["parts"], weight.params["remaining_quantity"]) == (
        "0",
        "",
        "0",
    )
    assert (hardware.remaining_ssp, hardware.totals.quantity, hardware.unit_ssp) == (0, 0, None)
    assert hardware.a_posted - hardware.base_revenue_posted == 0  # remaining allocation 0.00
    consulting = obligation(after, "POB-CONS").segments[-1]
    assert consulting.a_posted - consulting.base_revenue_posted == usd("330.00")
    assert nodes[f"mod_share@{ev.event_key}:K-01/POB-CONS:-"].value == "330.00"
    assert after.tp_history[-1].allocation_basis.posted == usd("510.00")


def _finite(value: object) -> bool:
    """No non-finite Decimal anywhere in a frozen state (Fractions are always finite)."""
    if isinstance(value, Decimal):
        return value.is_finite()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return all(_finite(getattr(value, item.name)) for item in dataclasses.fields(value))
    if isinstance(value, Mapping):
        return all(_finite(item) for item in value.values())
    if isinstance(value, tuple | list):
        return all(_finite(item) for item in value)
    return True


def test_tc_rm_15_zero_remaining_quantity() -> None:
    """Contract 3 POB #1 −7 / −100.00 after golden step 11 (07.15 prospective +2 / +500.00).

    The golden stream is folded under ``DEFAULT``: the products that the parity preset maps to its
    seeded templates (S03-R-18) take them as product defaults, and both amendments are applied by
    the native route with ``PROSPECTIVE`` chosen for every obligation other than the material right
    (L2-3-Q-11: the parity route of the preset is ENB-6 and ENB-7).
    """
    stream = golden_streams.stream("Contract 3", "11")
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
    header = base.contracts[0]
    step_11 = next(event for event in base.events if event.event_type == "CONTRACT_AMENDED")
    reduction = modification_input(
        "MOD-RM15",
        step_11.effective_date,
        [mod_line("POB #1", "CHANGE", "Hardware 1", "-7", "-100.00")],
        kind="QUANTITY_CHANGE",
    )
    payload = {
        "modification_id": reduction.modification_key,
        "treatments": {},
        "lines": list(reduction.lines),
        "ssp_basis": {},
    }
    head = max(event.stream_version for event in base.events) + 1
    rm_15_input = dataclasses.replace(
        step_11,
        event_key=f"{header.external_id}/EV-{head:06d}",
        stream_version=head,
        record_seq=max(event.record_seq for event in base.events) + 1,
        recorded_at=max(event.recorded_at for event in base.events) + timedelta(seconds=1),
        obligation_keys=("POB #1",),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        idempotency_key=None,
        modification_key=reduction.modification_key,
    )
    value = dataclasses.replace(
        base,
        known_at=max(base.known_at, rm_15_input.recorded_at),
        group=dataclasses.replace(base.group, products=products),
        contracts=(dataclasses.replace(header, modifications=(*header.modifications, reduction)),),
        events=(*base.events, rm_15_input),
    )
    ctx = context(value)
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(value, scratch)
    identified = s02_contract_identification.run(ctx, cb, scratch)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, scratch), scratch)
    st = s05_allocation.run(ctx, priced, scratch)
    assert st.findings == ()
    native = {
        ob.obligation_key: "PROSPECTIVE"
        for ob in st.obligations
        if ob.obligation_kind != ObligationKind.MATERIAL_RIGHT
    }
    step_11_ev, rm_15_ev = (
        dataclasses.replace(ev, payload={**ev.payload, "treatments": native})
        for ev in cb.boundary_events
        if ev.event_type == "CONTRACT_AMENDED"
    )
    price_at = price_function(format_money(priced.tp.allocation_basis.posted, 2))
    st = s06_modifications.apply(
        ctx, st, step_11_ev, scratch, identified=identified, price_at=price_at
    )
    assert st.findings == ()
    pob1 = obligation(st, "POB #1")
    assert pob1.quantity == 7 and pob1.segments[-1].totals.quantity == 7  # nothing delivered yet

    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(ctx, st, rm_15_ev, tb, identified=identified, price_at=price_at)
    assert after.findings == ()
    nodes = checked(tb)
    segment = obligation(after, "POB #1").segments[-1]
    assert (segment.totals.quantity, segment.remaining_ssp, segment.unit_ssp) == (0, 0, None)
    assert segment.a_posted - segment.base_revenue_posted == 0  # remaining allocation 0.00
    weight = nodes[f"mod_weight@{rm_15_ev.event_key}:Contract 3/POB %231:-"]
    assert (weight.value, weight.params["parts"]) == ("0", "")  # no unit SSP is computed
    pool = nodes[f"mod_pool@{rm_15_ev.event_key}:Contract 3:-"]
    index = pool.params["keys"].split("|").index("Contract 3/POB %231")
    allocation = int(pool.params["allocations"].split("|")[index])
    revenue = int(pool.params["revenue"].split("|")[index])
    # Its remaining allocation, nothing having transferred, joins the pool.
    assert (allocation, revenue) == (pob1.segments[-1].a_posted, 0)
    guards.no_floats(after)
    assert _finite(after)
