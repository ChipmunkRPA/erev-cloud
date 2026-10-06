"""Stage 06 legacy retrospective template: legacy 04 TC-RM-01 to TC-RM-04 and TC-RM-11 (ENB-6).

ENGINE_SPEC §6.3 S06-R-07, §6.5 S06-R-28 to S06-R-32, §6.6; POLICIES ALG-04 §2.5.7, POL-102,
POL-107, §6.3; legacy 04 §7.3 (tolerance 1e-6; D-17); DEVIATIONS DEV-035, DEV-053, DEV-071. The
golden streams are folded by the real stages 01 to 05 under ``LEGACY_PARITY``. TC-RM-02 and
TC-RM-03 start after golden step 11, which the real legacy prospective template applies (ENB-8;
L2-3-Q-31 closed). Under ``DEFAULT`` the golden stream is folded as in TC-RM-15 (L2-3-Q-11).
The fake stage 04 price function follows ENGINE_SPEC §4.2 (D-81), and every stage 06 trace
re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import InputBundle, ModificationInput
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
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s06_modifications import ModificationView
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
)
from erev_engine.trace import TraceBuilder, TraceNode
from support import golden_streams
from test_s06_prospective import checked, context, obligation, price_function, usd

TOLERANCE = Fraction(1, 10**6)  # legacy 04 §7.3; D-17


def exact(value: str) -> Fraction:
    return Fraction(Decimal(value))


def near(value: Fraction | None, expected: str, tolerance: Fraction = TOLERANCE) -> bool:
    return value is not None and abs(value - exact(expected)) <= tolerance


@dataclasses.dataclass(frozen=True)
class Folded:
    """The inception fold of stages 01 to 05, with the booked allocation basis."""

    ctx: BookContext
    identified: IdentifiedState
    state: AllocatedState
    booked: str  # posted allocation basis at inception, for the fake price function


def fold(value: InputBundle) -> Folded:
    ctx = context(value)
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(value, scratch)
    identified = s02_contract_identification.run(ctx, cb, scratch)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, scratch), scratch)
    st = s05_allocation.run(ctx, priced, scratch)
    assert st.findings == ()
    return Folded(ctx, identified, st, format_money(priced.tp.allocation_basis.posted, 2))


def golden(contract: str, step: str) -> Folded:
    return fold(golden_streams.stream(contract, step).input_bundle(preset="LEGACY_PARITY"))


def amendments(st: AllocatedState) -> list[EventView]:
    return [ev for ev in st.events if ev.event_type == "CONTRACT_AMENDED"]


def apply(
    folded: Folded, st: AllocatedState, ev: EventView, tb: TraceBuilder | None = None
) -> AllocatedState:
    return s06_modifications.apply(
        folded.ctx,
        st,
        ev,
        TraceBuilder(engine_version=ENGINE_VERSION) if tb is None else tb,
        identified=folded.identified,
        price_at=price_function(folded.booked),
    )


def catch_up(nodes: Mapping[str, TraceNode], ev: EventView, subject_key: str) -> Fraction:
    """CU_exact of one obligation: E after − E before on its ``catch_up@`` node (S06-R-30)."""
    params = nodes[f"catch_up@{ev.event_key}:{subject_key}:-"].params
    return Fraction(params["exact_after"]) - Fraction(params["exact_before"])


def remaining(st: AllocatedState, key: str) -> Fraction:
    """Legacy ``Current Remaining Allocation``: X − E at the boundary of the last segment."""
    segment = obligation(st, key).segments[-1]
    return segment.x_exact - segment.base_revenue_exact


def booking_line(value: InputBundle, key: str) -> Mapping[str, object]:
    booked = next(event for event in value.events if event.event_type == "CONTRACT_BOOKED")
    lines = booked.payload["lines"]
    assert isinstance(lines, Sequence)
    return next(
        line for line in lines if isinstance(line, Mapping) and line["obligation_key"] == key
    )


def template_line(
    value: InputBundle, key: str, quantity: str, billing: str, **accounts: str
) -> dict[str, object]:
    """A modification row on an existing obligation that repeats its stored attributes, with the
    account roles in ``accounts`` replaced (LM-TPL-MOD-01 to 15)."""
    stored = booking_line(value, key)
    codes = stored["account_overrides"]
    assert isinstance(codes, Mapping)
    return {
        "obligation_key": key,
        "action": "CHANGE",
        "product_code": stored["product_code"],
        "quantity_delta": Decimal(quantity),
        "consideration_delta": Decimal(billing),
        "stratification": stored["stratification"],
        "selling_entity_code": stored["performing_entity_code"],
        "account_codes": {**codes, **accounts},
        "ssp_version_label": stored["ssp_version_label"],
    }


def amended(
    value: InputBundle,
    key: str,
    effective: date,
    mode: str,
    lines: Sequence[Mapping[str, object]],
    treatment: str,
) -> InputBundle:
    """``value`` with one more approved modification of its contract and the ``CONTRACT_AMENDED``
    that applies it, with ``treatment`` for every obligation (S01-R-09)."""
    header = value.contracts[0]
    booked = next(event for event in value.events if event.event_type == "CONTRACT_BOOKED")
    booked_lines = booked.payload["lines"]
    assert isinstance(booked_lines, Sequence)
    keys = {str(line["obligation_key"]) for line in booked_lines if isinstance(line, Mapping)}
    keys.update(str(line["obligation_key"]) for line in lines)
    treatments = {name: treatment for name in sorted(keys)}
    modification = ModificationInput(
        modification_key=key,
        effective_date=effective,
        kind="VC_CHANGE" if mode == "pob_price_change" else "QUANTITY_CHANGE",
        template_mode=mode,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=tuple(lines),
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments=treatments,
        treatment_summary=treatment,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )
    payload = {
        "modification_id": key,
        "treatments": treatments,
        "lines": list(lines),
        "ssp_basis": {},
    }
    head = max(event.stream_version for event in value.events) + 1
    event = dataclasses.replace(
        booked,
        event_key=f"{header.external_id}/EV-{head:06d}",
        stream_version=head,
        event_type="CONTRACT_AMENDED",
        effective_date=effective,
        recorded_at=max(event.recorded_at for event in value.events) + timedelta(seconds=1),
        record_seq=max(event.record_seq for event in value.events) + 1,
        obligation_keys=tuple(sorted({str(line["obligation_key"]) for line in lines})),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        idempotency_key=None,
        modification_key=key,
    )
    events = sorted(
        (*value.events, event), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
    )
    return dataclasses.replace(
        value,
        known_at=max(value.known_at, event.recorded_at),
        contracts=(
            dataclasses.replace(header, modifications=(*header.modifications, modification)),
        ),
        events=tuple(events),
    )


def option(folded: Folded, code: str, on: date) -> object:
    header = folded.state.contracts[0].header
    entity = header.contracting_entity_code
    period = dates.period_of(folded.ctx.entities[entity], on).period_key
    return folded.ctx.policies.value(
        code, contract=header.external_id, entity=entity, period=period
    )


def native(
    contract: str, treatments: Mapping[str, str]
) -> tuple[Folded, AllocatedState, EventView]:
    """Golden ``contract`` through step 12 under ``DEFAULT``: step 11 applied natively with
    ``PROSPECTIVE`` for every obligation other than a material right (as TC-RM-15), and step 12
    carrying the native ``treatments``."""
    base = golden_streams.stream(contract, "12").input_bundle(preset="DEFAULT")
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
    folded = fold(
        dataclasses.replace(base, group=dataclasses.replace(base.group, products=products))
    )
    step_11, step_12 = amendments(folded.state)
    prospective = {
        ob.obligation_key: "PROSPECTIVE"
        for ob in folded.state.obligations
        if ob.obligation_kind != ObligationKind.MATERIAL_RIGHT
    }
    st = apply(
        folded,
        folded.state,
        dataclasses.replace(step_11, payload={**step_11.payload, "treatments": prospective}),
    )
    assert st.findings == ()
    reduction = dataclasses.replace(
        step_12, payload={**step_12.payload, "treatments": dict(treatments)}
    )
    return folded, st, reduction


def test_tc_rm_01_retro_05_15() -> None:
    """Contract 2 POB #1 +2 / +400.00 at 2023-05-15 after 04.30 (golden step 08)."""
    folded = golden("Contract 2", "08")
    (step_08,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, step_08, tb)
    assert after.findings == ()
    nodes = checked(tb)
    pob1 = obligation(after, "POB #1")
    assert nodes[f"mod_ssp@{step_08.event_key}:{pob1.subject_key}:-"].value == "207"
    assert after.tp_history[-1].allocation_basis.posted == usd("1300.00")
    assert sum(ob.segments[-1].a_posted for ob in after.obligations) == usd("1300.00")
    catch_ups = {"POB #1": "13.376068", "POB #2": "0", "POB #3": "10.491034", "VC #1": "0"}
    for key, value in catch_ups.items():
        assert near(catch_up(nodes, step_08, obligation(after, key).subject_key), value), key
    allocations = {
        "POB #1": "700.980392",
        "POB #2": "385.185185",
        "POB #3": "84.967320",
        "VC #1": "0",
    }
    for key, value in allocations.items():
        assert near(remaining(after, key), value), key
    segment = pob1.segments[-1]
    assert (segment.basis, segment.progress_measure) == ("PROSPECTIVE", "UNITS_SINCE_BOUNDARY")
    assert (segment.totals.quantity, segment.remaining_ssp) == (9, Fraction(1485, 2))
    assert segment.unit_ssp == Fraction(165, 2)  # POB #1 unit SSP 82.5
    assert segment.remaining_billing_plan == 980
    assert (pob1.quantity, pob1.stated_price, pob1.last_modification_key) == (10, 1000, "MOD-08")


def test_tc_rm_02_retro_08_15_contract3() -> None:
    """Contract 3 POB #1 −4 / −200.00 after golden step 11 (golden step 12, row 2)."""
    folded = golden("Contract 3", "12")
    step_11, step_12 = amendments(folded.state)
    st = apply(folded, folded.state, step_11)  # the real prospective template (ENB-8)
    assert st.findings == ()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, st, step_12, tb)
    assert after.findings == ()
    nodes = checked(tb)
    pob1 = obligation(after, "POB #1")
    assert nodes[f"mod_ssp@{step_12.event_key}:{pob1.subject_key}:-"].value == "-306"
    assert after.tp_history[-1].allocation_basis.posted == usd("1600.00")
    segment = pob1.segments[-1]
    assert (segment.totals.quantity, segment.remaining_ssp) == (3, 401)
    assert near(segment.unit_ssp, "133.666667")
    # Legacy parity (legacy 04 §5.3): every delivered obligation takes a catch-up (DEV-071).
    catch_ups = {"POB #1": "0", "POB #2": "34.880035", "POB #3": "7.223824", "POB #4": "0"}
    for key, value in catch_ups.items():
        assert near(catch_up(nodes, step_12, obligation(after, key).subject_key), value), key
    allocations = {
        "POB #1": "334.340803",
        "POB #2": "153.413236",
        "POB #3": "62.532569",
        "POB #4": "833.767587",
    }
    for key, value in allocations.items():
        assert near(remaining(after, key), value), key

    # DEFAULT, POL-102 PARTIALLY_SATISFIED_NONDISTINCT_ONLY (TC-RM-02 FIX-01).
    treatments = {"POB #1": "PROSPECTIVE", "POB #2": "PROSPECTIVE", "POB #3": "CUMULATIVE_CATCH_UP"}
    corrected, st, reduction = native("Contract 3", treatments)
    scope = option(corrected, "mod.catch_up_scope", reduction.effective_date)
    assert scope == "PARTIALLY_SATISFIED_NONDISTINCT_ONLY"
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    fixed = apply(corrected, st, reduction, tb)
    assert fixed.findings == ()
    nodes = checked(tb)
    for key in ("POB #1", "POB #2"):  # the delivered distinct software receives no catch-up
        subject = obligation(fixed, key).subject_key
        assert nodes[f"catch_up@{reduction.event_key}:{subject}:-"].value == "0.00", key
    assert fixed.tp_history[-1].allocation_basis.posted == usd("1600.00")


def test_tc_rm_03_retro_08_15_contract4() -> None:
    """Contract 4 POB #3 −0.5 / −50.00 after golden step 11 (golden step 12, row 3)."""
    folded = golden("Contract 4", "12")
    step_11, step_12 = amendments(folded.state)
    st = apply(folded, folded.state, step_11)  # the real prospective template (ENB-8)
    assert st.findings == ()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, st, step_12, tb)
    assert after.findings == ()
    nodes = checked(tb)
    pob3 = obligation(after, "POB #3")
    assert nodes[f"mod_ssp@{step_12.event_key}:{pob3.subject_key}:-"].value == "-75"
    assert after.tp_history[-1].allocation_basis.posted == usd("1200.00")
    catch_ups = {"POB #1": "8.627592", "POB #2": "7.668971", "POB #3": "0", "VC #1": "0"}
    for key, value in catch_ups.items():
        assert near(catch_up(nodes, step_12, obligation(after, key).subject_key), value), key
    allocations = {
        "POB #1": "359.764860",
        "POB #2": "319.790986",
        "POB #3": "293.925539",
        "VC #1": "0",
    }
    for key, value in allocations.items():
        assert near(remaining(after, key), value), key
    segment = pob3.segments[-1]
    assert (segment.totals.quantity, segment.remaining_ssp, segment.remaining_billing_plan) == (
        Fraction(5, 2),
        375,
        400,
    )

    # DEFAULT (TC-RM-03 FIX-01): the catch-up is confined to POB #3, which has 0 delivered. The VC
    # row is a VC element there, not an obligation (S01-R-06).
    treatments = {"POB #1": "PROSPECTIVE", "POB #2": "PROSPECTIVE", "POB #3": "CUMULATIVE_CATCH_UP"}
    corrected, st, reduction = native("Contract 4", treatments)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    fixed = apply(corrected, st, reduction, tb)
    assert fixed.findings == ()
    nodes = checked(tb)
    values = {
        node_id: node.value for node_id, node in nodes.items() if node_id.startswith("catch_up@")
    }
    assert f"catch_up@{reduction.event_key}:{obligation(fixed, 'POB #3').subject_key}:-" in values
    assert set(values.values()) == {"0.00"}
    assert fixed.tp_history[-1].allocation_basis.posted == usd("1200.00")


def test_tc_rm_04_account_member_conflict() -> None:
    """Contract 4 VC #1 billing −50.00, quantity 0, after 04.30 (legacy 04 §7.3 TC-RM-04)."""
    value = golden_streams.stream("Contract 4", "07").input_bundle(preset="LEGACY_PARITY")
    d = date(2023, 5, 15)
    conflicting = template_line(value, "VC #1", "0", "-50", CONTRACT_LIABILITY="29999")
    folded = fold(
        amended(value, "MOD-RM04", d, "retrospective", [conflicting], "LEGACY_RETROSPECTIVE")
    )
    (ev,) = amendments(folded.state)
    header = folded.state.contracts[0].header
    view = ModificationView.of("Contract 4", header.modifications[-1], event=ev)
    (finding,) = s06_modifications.validate_modification(folded.ctx, folded.state, view)
    assert (finding.code, finding.severity, finding.stage) == ("MOD_ATTRIBUTE_CONFLICT", "ERROR", 6)
    assert finding.detail["members"] == "account_codes.CONTRACT_LIABILITY"
    assert finding.subject_key == obligation(folded.state, "VC #1").subject_key
    assert obligation(folded.state, "VC #1").account_overrides["CONTRACT_LIABILITY"] == "21002"

    # The same line with the stored account 21002.
    stored = template_line(value, "VC #1", "0", "-50")
    folded = fold(amended(value, "MOD-RM04", d, "retrospective", [stored], "LEGACY_RETROSPECTIVE"))
    (ev,) = amendments(folded.state)
    header = folded.state.contracts[0].header
    view = ModificationView.of("Contract 4", header.modifications[-1], event=ev)
    assert s06_modifications.validate_modification(folded.ctx, folded.state, view) == ()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, ev, tb)
    assert after.findings == ()
    nodes = checked(tb)
    assert after.tp_history[-1].allocation_basis.posted == usd("900.00")
    catch_ups = {"POB #1": "-5.857580", "POB #2": "-5.206738", "POB #3": "0", "VC #1": "0"}
    for key, expected in catch_ups.items():
        assert near(catch_up(nodes, ev, obligation(after, key).subject_key), expected), key
    vc = obligation(after, "VC #1")
    assert vc.account_overrides["CONTRACT_LIABILITY"] == "21002"
    assert vc.segments[-1].remaining_billing_plan == -150  # legacy VC CRB −150


def test_tc_rm_11_new_pob_joins_the_pool() -> None:
    """DEV-053 corrected: Contract 2 POB #4 Software 1 +1 / +170.00 after 04.30. Every obligation
    of the contract is in scope, and the added obligation takes its S06-R-31 creation values."""
    value = golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    software = template_line(value, "POB #2", "1", "170")
    add = {
        **software,
        "obligation_key": "POB #4",
        "action": "ADD",
        "start_date": date(2023, 1, 1),
        "end_date": date(2023, 12, 31),
    }
    folded = fold(
        amended(
            value, "MOD-RM11", date(2023, 5, 15), "retrospective", [add], "LEGACY_RETROSPECTIVE"
        )
    )
    (ev,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, ev, tb)
    assert after.findings == ()
    nodes = checked(tb)
    assert after.tp_history[-1].allocation_basis.posted == usd("1070.00")
    for key, expected in {"POB #1": "2.239667", "POB #3": "1.756602"}.items():
        assert near(catch_up(nodes, ev, obligation(after, key).subject_key), expected), key
    added = obligation(after, "POB #4")
    assert near(added.segments[-1].x_exact, "135.746269")
    assert (added.original_stated_price, added.original_quantity) == (170, 1)
    assert added.ssp is not None
    assert (added.ssp.low, added.ssp.high, added.ssp.selected) == (136, 184, 170)
    assert added.original_total_contract_price == 1070
    assert added.original_total_contract_ssp == Fraction(2407, 2)  # Σ remaining SSP 1,203.5
    assert added.original_allocation.x_exact == added.segments[-1].x_exact
    assert added.last_modification_key == "MOD-RM11"
