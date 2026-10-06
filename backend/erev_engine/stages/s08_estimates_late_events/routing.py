"""Stage 08 routing of a transaction price change (ENGINE_SPEC §8.3 S08-R-04, S08-R-05, S08-R-07).

``route`` returns Δ_p (minor units) and δ_p (currency units) per obligation, each with its
``tp_share@<event key>:<ob>:-`` node, and Σ Δ_p = ΔTP (S08-INV-02):

- An element with ``allocation_target = OBLIGATIONS`` routes only to its targets, by relative SSP
  within them (S08-R-04).
- VC promised before a 25-13(a) boundary of the contract routes under POL-106
  ``ASC_606_10_32_45`` (S08-R-05): Δ_pre over the obligations identified before the boundary
  (``lineage_pre_modification``) by inception SSP; the shares of obligations satisfied at the
  boundary (f = 1 there, measured by stage 09) stay with them, and the rest is apportioned over the
  obligations of the boundary by the weights recorded on their segments (``remaining_ssp``), then
  through each later 25-13(a) boundary in ENG-06 order. An element whose version 1 is in force at
  inception (S01-R-18 ``at_inception``) was promised before every boundary.
- When every obligation of the group is on an ``INCEPTION`` segment with no 25-13(a) boundary and
  the element is not targeted, the quotas in force are carried, ΔTP is spread by the inception
  weights and the posted allocations are one apportionment of the posted price over the exact
  quotas (S08-R-07 rev 1.6; D-91); a negative resulting exact quota selects incremental posted
  shares, and S08-R-06 decides in ``estimates.apply`` whether the change is refused.
- Otherwise ΔTP routes on the inception basis over the obligations of the element's contract.

Inception weights are ``ObligationState.inception_weight`` (S08-R-04): the selected SSP fixed by
stage 05, or the residual R of the residual candidate (D-91). ``check_version`` fails a version
closed whose target set or evidence state differs from the element's version 1 (S08-R-04). The
``tp_share`` nodes carry ``estimate.route.inception.v2``; v1 stays registered for stored traces.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine import money
from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.stages.s05_allocation import targeted
from erev_engine.stages.s09_recognition import target_at_position
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    ObligationState,
    SegmentCause,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "INCEPTION_FORMULA",
    "INCEPTION_FORMULA_V2",
    "ROUTE_32_45_FORMULA",
    "Share",
    "check_version",
    "element_obligations",
    "in_force",
    "minor_unit",
    "route",
    "weight",
]

INCEPTION_FORMULA: Final = "estimate.route.inception.v1"  # stored traces only (rev 1.6)
INCEPTION_FORMULA_V2: Final = "estimate.route.inception.v2"  # S08-R-07 (d); D-91
ROUTE_32_45_FORMULA: Final = "estimate.route.32_45.v1"
TARGETED: Final = "OBLIGATIONS"
ROUTING_32_45: Final = "ASC_606_10_32_45"
SEPARATOR: Final = "|"


@dataclass(frozen=True, slots=True)
class Share:
    """Δ_p and δ_p of one obligation with its ``tp_share`` node (S08-R-06)."""

    subject_key: str
    delta: int  # minor units
    exact: Fraction  # currency units
    node_id: str


def _invariant(message: str, subject_key: str, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def minor_unit(ctx: BookContext) -> int:
    """μ of the group's transaction currency (CV-33)."""
    spec = ctx.currencies.get(ctx.txn_currency)
    if spec is None:
        raise _invariant(
            "the transaction currency is absent from the currency table",
            ctx.txn_currency,
            rule="CV-30",
        )
    return spec.minor_unit


def in_force(st: AllocatedState, ob: ObligationState, ev: EventView) -> AllocationSegment | None:
    """The ``FIXED`` segment in force before ``ev`` in ENG-06 order (CV-60)."""
    order_keys = {item.event_key: item.order_key for item in st.events}
    found: AllocationSegment | None = None
    for seg in ob.segments:
        if seg.component != "FIXED" or seg.effective_date > ev.effective_date:
            continue
        if seg.event_key is not None:
            order_key = order_keys.get(seg.event_key)
            if order_key is None:
                raise _invariant(
                    "the boundary event of a segment is absent", ob.subject_key, rule="CV-60"
                )
            if order_key >= ev.order_key:
                continue
        found = seg
    return found


def weight(ob: ObligationState) -> Fraction:
    """The S08-R-04 inception weight of the obligation, fixed by stage 05: its selected SSP, or the
    inception residual R of the residual candidate (D-91). Read on every routing path."""
    return ob.inception_weight


def _first_version(st: AllocatedState, version: EstimateVersionInput) -> EstimateVersionInput:
    """The element's pinned version 1: the lowest pinned version number (S01-R-18)."""
    pins = st.estimates.pins.get(version.estimate_key, ())
    return min(
        (pin.version for pin in pins),
        key=lambda item: (item.version_no, item.effective_date),
        default=version,
    )


def check_version(st: AllocatedState, ev: EventView, version: EstimateVersionInput) -> None:
    """S08-R-04 (rev 1.6; D-91): a reallocating version of a targeted element fails closed when its
    target set, or its S05-R-14 evidence state, differs from the element's version 1.

    Raises ``EngineError("ENGINE_INVARIANT_VIOLATED")`` with detail ``rule`` S08-R-04 and
    ``reason`` ``target_set_changed`` or ``evidence_changed`` (CV-45), before any routing, segment
    or quota-history mutation and whether or not the price changes (``estimates.apply`` calls it
    before its zero-delta return). The evidence predicate is stage 05 ``targeted.evidenced``, in
    either direction. An element targeted in neither version is not checked (post-rc: the F5
    ``WARNING`` for a targeted element without evidence).
    """
    first = _first_version(st, version)
    if first.version_key == version.version_key:
        return
    if first.allocation_target != TARGETED and version.allocation_target != TARGETED:
        return
    detail = {
        "estimate_key": version.estimate_key,
        "event_key": ev.event_key,
        "rule": "S08-R-04",
        "v_first": first.version_key,
        "v_new": version.version_key,
    }
    if first.allocation_target != version.allocation_target or set(
        first.target_obligation_keys
    ) != set(version.target_obligation_keys):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the target set of an estimate version differs from the element's version 1",
            subject_key=version.estimate_key,
            detail={**detail, "reason": "target_set_changed"},
        )
    if targeted.evidenced(first) != targeted.evidenced(version):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the 32-40 evidence state of an estimate version differs from the element's version 1",
            subject_key=version.estimate_key,
            detail={**detail, "reason": "evidence_changed"},
        )


def _element_contract(st: AllocatedState, ev: EventView, version: EstimateVersionInput) -> str:
    # "<contract external_id>/<element_code>", the head CV-21 encoded: the member whose encoded id
    # is the head (D-90d L9-RUN-Q-8), else the head itself; a portfolio element applies to the
    # event's contract.
    if version.estimate_key.startswith("PORTFOLIO:"):
        return ev.contract_key
    head = version.estimate_key.split("/", 1)[0]
    return next(
        (
            view.header.external_id
            for view in st.contracts
            if encode_key(view.header.external_id) == head
        ),
        head,
    )


def element_obligations(
    st: AllocatedState, ev: EventView, version: EstimateVersionInput
) -> tuple[ObligationState, ...]:
    """Obligations of the element's contract in force before ``ev``, its targets if targeted."""
    contract_key = _element_contract(st, ev, version)
    found = tuple(
        ob
        for ob in st.obligations
        if ob.contract_key == contract_key and in_force(st, ob, ev) is not None
    )
    if version.allocation_target == TARGETED:
        targets = set(version.target_obligation_keys)
        found = tuple(ob for ob in found if ob.obligation_key in targets)
    return found


def _apportion(total: int, weights: Sequence[Fraction], keys: Sequence[str]) -> list[int]:
    if total == 0 and sum(weights, Fraction(0)) == 0:
        return [0] * len(keys)
    return money.largest_remainder(total, list(weights), list(keys))


def _split(
    total: int, weights: Sequence[Fraction], keys: Sequence[str], mu: int
) -> dict[str, tuple[int, Fraction]]:
    # CV-34: posted shares of the posted total, exact shares (total ÷ 10^μ) × w ÷ Σw.
    posted = _apportion(total, weights, keys)
    weight_sum = sum(weights, Fraction(0))
    out: dict[str, tuple[int, Fraction]] = {}
    for key, value, share in zip(keys, weights, posted, strict=True):
        exact = Fraction(0) if weight_sum == 0 else Fraction(total, 10**mu) * value / weight_sum
        out[key] = (share, exact)
    return out


def _node(
    tb: TraceBuilder,
    ctx: BookContext,
    ev: EventView,
    subject_key: str,
    share: tuple[int, Fraction],
    formula_id: str,
    delta_node: str,
    params: dict[str, str],
) -> str:
    return tb.node(
        measure=f"tp_share@{ev.event_key}",
        subject_key=subject_key,
        period_key=None,
        value=share[0],
        currency=ctx.txn_currency,
        minor_unit=minor_unit(ctx),
        formula_id=formula_id,
        inputs=[delta_node],
        params=params,
        exact=share[1],
        narrative_key=formula_id.rsplit(".v", 1)[0],
    )


def route(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    version: EstimateVersionInput,
    delta: int,
    delta_node: str,
    tb: TraceBuilder,
) -> tuple[Share, ...]:
    """Δ_p and δ_p of a transaction price change ``delta`` (minor units), with trace nodes."""
    check_version(st, ev, version)
    members = element_obligations(st, ev, version)
    if not members:
        raise _invariant(
            "no obligation receives the transaction price change",
            ev.contract_key,
            rule="S08-R-04",
            event_key=ev.event_key,
        )
    if version.allocation_target != TARGETED:
        policy = ctx.policies.value(
            "mod.post_modification_vc_routing", contract=_element_contract(st, ev, version)
        )
        boundaries = _modification_boundaries(st, ev, version) if policy == ROUTING_32_45 else ()
        if boundaries:
            return _route_32_45(ctx, st, ev, delta, delta_node, tb, boundaries)
        if _pure_inception(st, ev, members):
            return _reapportion(ctx, st, ev, members, delta, delta_node, tb)
    return _incremental(ctx, ev, members, delta, delta_node, tb)


def _incremental(
    ctx: BookContext,
    ev: EventView,
    members: Sequence[ObligationState],
    delta: int,
    delta_node: str,
    tb: TraceBuilder,
) -> tuple[Share, ...]:
    keys = [ob.subject_key for ob in members]
    weights = [weight(ob) for ob in members]
    split = _split(delta, weights, keys, minor_unit(ctx))
    params = {
        "as_of": ev.effective_date.isoformat(),
        "keys": SEPARATOR.join(keys),
        "mode": "incremental",
        "ssp_weights": SEPARATOR.join(rational_param(value) for value in weights),
    }
    shares: list[Share] = []
    for key in keys:
        node_id = _node(
            tb, ctx, ev, key, split[key], INCEPTION_FORMULA_V2, delta_node, {**params, "key": key}
        )
        shares.append(Share(key, split[key][0], split[key][1], node_id))
    return tuple(shares)


def _pure_inception(st: AllocatedState, ev: EventView, members: Sequence[ObligationState]) -> bool:
    group: list[str] = []
    for ob in st.obligations:
        seg = in_force(st, ob, ev)
        if seg is None:
            continue
        if seg.basis != "INCEPTION" or seg.modification_boundary_no != 0:
            return False
        group.append(ob.subject_key)
    return sorted(group) == sorted(ob.subject_key for ob in members)


def _reapportion(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    members: Sequence[ObligationState],
    delta: int,
    delta_node: str,
    tb: TraceBuilder,
) -> tuple[Share, ...]:
    # S08-R-07 (rev 1.6; D-91): (a) δ_p = (ΔTP ÷ 10^μ) × w_p ÷ Σw and x′_p = x_p + δ_p, so every
    # pool of the quota in force is carried; (b) when every x′_p ≥ 0 the posted allocations are one
    # apportionment of the posted price over the exact quotas, a′ = largest_remainder(basis after,
    # [x′_p], keys), Δ_p = a′_p − a_p (PROP:P1, P2); a basis of 0 posts 0; (c) when any x′_p < 0
    # the posted shares are incremental, Δ = largest_remainder(ΔTP, w, keys), and the S08-R-06
    # transition predicate in ``estimates.apply`` decides whether the change is refused.
    mu = minor_unit(ctx)
    keys = [ob.subject_key for ob in members]
    weights = [weight(ob) for ob in members]
    before: dict[str, AllocationSegment] = {}
    for ob in members:
        seg = in_force(st, ob, ev)
        if seg is None:
            raise _invariant("an obligation has no allocation", ob.subject_key, rule="CV-60")
        before[ob.subject_key] = seg
    weight_sum = sum(weights, Fraction(0))
    if weight_sum == 0:
        raise EngineError(
            "TOTAL_WEIGHT_ZERO",
            "the inception weights of the element's obligations sum to 0",
            subject_key=ev.contract_key,
            detail={"event_key": ev.event_key, "rule": "S08-R-07"},
        )
    basis_after = sum(seg.a_posted for seg in before.values()) + delta
    exact = {
        key: Fraction(delta, 10**mu) * value / weight_sum
        for key, value in zip(keys, weights, strict=True)
    }
    quotas_after = [before[key].x_exact + exact[key] for key in keys]
    if sum(quotas_after, Fraction(0)) * 10**mu != basis_after:
        raise _invariant(
            "the exact quotas after the change do not sum to the posted allocation basis",
            ev.contract_key,
            rule="S08-INV-01",
            event_key=ev.event_key,
        )
    if any(value < 0 for value in quotas_after):
        mode = "incremental"
        posted = _apportion(delta, weights, keys)
        after = {key: before[key].a_posted + share for key, share in zip(keys, posted, strict=True)}
    elif basis_after == 0:
        mode = "reapportion"
        after = dict.fromkeys(keys, 0)
    else:
        mode = "reapportion"
        posted = money.largest_remainder(basis_after, quotas_after, keys)
        after = dict(zip(keys, posted, strict=True))
    params = {
        "as_of": ev.effective_date.isoformat(),
        "basis_after": str(basis_after),
        "keys": SEPARATOR.join(keys),
        "mode": mode,
        "quotas_after": SEPARATOR.join(rational_param(value) for value in quotas_after),
        "ssp_weights": SEPARATOR.join(rational_param(value) for value in weights),
    }
    shares: list[Share] = []
    for key in keys:
        seg = before[key]
        change = (after[key] - seg.a_posted, exact[key])
        node_params = {**params, "a_before": str(seg.a_posted), "key": key}
        node_id = _node(tb, ctx, ev, key, change, INCEPTION_FORMULA_V2, delta_node, node_params)
        shares.append(Share(key, change[0], change[1], node_id))
    return tuple(shares)


def _modification_boundaries(
    st: AllocatedState, ev: EventView, version: EstimateVersionInput
) -> tuple[EventView, ...]:
    """25-13(a) boundaries of the contract after the element's version 1 and before ``ev``. A
    version 1 in force at inception (S01-R-18 ``at_inception``) was promised before every boundary:
    the inception price holds it wherever its event stands among the events of that date."""
    contract_key = _element_contract(st, ev, version)
    pins = st.estimates.pins.get(version.estimate_key, ())
    first = min(pins, key=lambda pin: (pin.version.version_no, pin.event_order_key), default=None)
    promised = (version.effective_date, ev.order_key)
    at_inception = False
    if first is not None:
        promised = (first.version.effective_date, first.event_order_key)
        at_inception = first.at_inception
    events = {item.event_key: item for item in st.events}
    found: dict[str, EventView] = {}
    for ob in st.obligations:
        if ob.contract_key != contract_key:
            continue
        for seg in ob.segments:
            if (
                seg.cause != SegmentCause.MODIFICATION
                or seg.basis != "PROSPECTIVE"
                or seg.event_key is None
            ):
                continue
            boundary = events.get(seg.event_key)
            if boundary is None:
                raise _invariant(
                    "the boundary event of a segment is absent", ob.subject_key, rule="CV-60"
                )
            promised_before = (
                at_inception
                or promised[0] < boundary.effective_date
                or (promised[0] == boundary.effective_date and promised[1] < boundary.order_key)
            )
            if promised_before and boundary.order_key < ev.order_key:
                found[boundary.event_key] = boundary
    return tuple(sorted(found.values(), key=lambda item: item.order_key))


def _boundary_segments(
    st: AllocatedState, boundary: EventView
) -> tuple[tuple[ObligationState, AllocationSegment], ...]:
    found: list[tuple[ObligationState, AllocationSegment]] = []
    for ob in st.obligations:
        for seg in ob.segments:
            if seg.component == "FIXED" and seg.event_key == boundary.event_key:
                found.append((ob, seg))
                break
    return tuple(found)


def _route_32_45(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    delta: int,
    delta_node: str,
    tb: TraceBuilder,
    boundaries: Sequence[EventView],
) -> tuple[Share, ...]:
    mu = minor_unit(ctx)
    by_key = {ob.subject_key: ob for ob in st.obligations}
    first = _boundary_segments(st, boundaries[0])
    pre_keys = sorted({key for ob, _ in first for key in ob.lineage_pre_modification})
    if not pre_keys or any(key not in by_key for key in pre_keys):
        raise _invariant(
            "the obligations identified before the modification are unknown",
            ev.contract_key,
            rule="S06-R-16",
            event_key=boundaries[0].event_key,
        )
    pre_weights = [weight(by_key[key]) for key in pre_keys]
    current = _split(delta, pre_weights, pre_keys, mu)
    kept: dict[str, tuple[int, Fraction]] = {}
    params = {
        "as_of": ev.effective_date.isoformat(),
        "pre_keys": SEPARATOR.join(pre_keys),
        "pre_weights": SEPARATOR.join(rational_param(value) for value in pre_weights),
        "steps": str(len(boundaries)),
    }
    for step, boundary in enumerate(boundaries, start=1):
        satisfied = sorted(
            key
            for key in current
            if key in by_key
            and target_at_position(
                ctx, st, by_key[key], boundary.effective_date, event=boundary, inclusive=False
            ).complete
        )
        pool = 0
        for key, (share, exact) in current.items():
            if key in satisfied:
                held = kept.get(key, (0, Fraction(0)))
                kept[key] = (held[0] + share, held[1] + exact)
            else:
                pool += share
        post = _boundary_segments(st, boundary)
        post_keys = [ob.subject_key for ob, _ in post]
        post_weights = [seg.remaining_ssp for _, seg in post]
        current = _split(pool, post_weights, post_keys, mu)
        params[f"satisfied_{step}"] = SEPARATOR.join(satisfied)
        params[f"post_keys_{step}"] = SEPARATOR.join(post_keys)
        params[f"post_weights_{step}"] = SEPARATOR.join(
            rational_param(value) for value in post_weights
        )
    final = dict(kept)
    for key, (share, exact) in current.items():
        held = final.get(key, (0, Fraction(0)))
        final[key] = (held[0] + share, held[1] + exact)
    shares: list[Share] = []
    for key in sorted(final):
        node_params = {**params, "key": key}
        node_id = _node(tb, ctx, ev, key, final[key], ROUTE_32_45_FORMULA, delta_node, node_params)
        shares.append(Share(key, final[key][0], final[key][1], node_id))
    return tuple(shares)
