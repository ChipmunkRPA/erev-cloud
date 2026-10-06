"""Stage 06 line attribute changes (ENGINE_SPEC §6.4 S06-R-26; REQ-MOD-021).

``LINE_ATTRIBUTES_CHANGED`` names one obligation and its ``changes``: ``account_overrides``,
``performing_entity_code``, ``ssp_version_label``, or ``ssp_book_version_id`` with
``justification``.

Account overrides and the performing entity apply to targets dated on or after the effective date,
and create no segment. ``attributes_at`` folds the changes effective on or before a date over the
booked attributes of the obligation.

A change of the SSP version pin corrects the inception SSP. The group is re-allocated from
inception with the corrected resolution: the inception price is apportioned again over the
inception SSPs, the corrected one included. Every obligation takes an ``INCEPTION`` segment at the
event, so the differences post as catch-ups (RCP-06). The re-allocation traces through the §6.6
nodes ``mod_weight`` (the SSPs), ``mod_pool`` (the group's posted allocations, revenue 0) and
``mod_share`` (the corrected quotas). It is built for a group whose obligations still hold only
their inception segment and whose price history is the inception price; any earlier boundary fails
closed. Private to stage 06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import payload_text
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s05_allocation import provenance
from erev_engine.stages.s06_modifications import pool, segments, weights
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    Finding,
    ObligationState,
    Quota,
    SegmentCause,
    SspResolution,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "AttributeChange",
    "LineAttributes",
    "Reallocation",
    "attributes_at",
    "change",
    "reallocate",
]

EVENT_TYPE: Final = "LINE_ATTRIBUTES_CHANGED"
MEMBERS: Final = frozenset(
    {
        "account_overrides",
        "justification",
        "performing_entity_code",
        "ssp_book_version_id",
        "ssp_version_label",
    }
)
BASIS: Final = "CORRECTED_INCEPTION"


@dataclass(frozen=True, slots=True)
class LineAttributes:
    """The account overrides and performing entity of an obligation in force at a date."""

    account_overrides: Mapping[str, str]
    performing_entity: str


@dataclass(frozen=True, slots=True)
class AttributeChange:
    """The ``changes`` of one ``LINE_ATTRIBUTES_CHANGED`` event (04 §16.3)."""

    obligation_key: str
    account_overrides: Mapping[str, str] | None
    performing_entity: str | None
    ssp_version_key: str | None  # ssp_book_version_id of an approved SSP_OVERRIDE
    ssp_version_label: str | None

    @property
    def repins_ssp(self) -> bool:
        return self.ssp_version_key is not None or self.ssp_version_label is not None


def change(ev: EventView) -> AttributeChange:
    """The validated changes of the event; a malformed payload raises ``ValueError`` (CV-45)."""
    key = payload_text(ev.payload, "obligation_key")
    raw = ev.payload.get("changes")
    if key is None or not isinstance(raw, Mapping) or not raw:
        raise ValueError(f"{ev.event_key}: {EVENT_TYPE} needs obligation_key and changes (§16.3)")
    if ev.payload.get("diff") is None:
        raise ValueError(f"{ev.event_key}: {EVENT_TYPE} needs diff (REQ-MOD-021)")
    unknown = sorted(str(name) for name in raw if name not in MEMBERS)
    if unknown:
        raise ValueError(f"{ev.event_key}: changes member {unknown[0]} is unknown (§16.3)")
    overrides: Mapping[str, str] | None = None
    members = raw.get("account_overrides")
    if members is not None:
        if not isinstance(members, Mapping) or not all(
            isinstance(role, str) and isinstance(account, str) for role, account in members.items()
        ):
            raise ValueError(f"{ev.event_key}: account_overrides maps roles to accounts")
        overrides = MappingProxyType(dict(sorted(members.items())))
    entity = payload_text(raw, "performing_entity_code")
    version_key = payload_text(raw, "ssp_book_version_id")
    label = payload_text(raw, "ssp_version_label")
    if version_key is not None and not payload_text(raw, "justification"):
        raise ValueError(f"{ev.event_key}: ssp_book_version_id comes with a justification (R-26)")
    if overrides is None and entity is None and version_key is None and label is None:
        raise ValueError(f"{ev.event_key}: {EVENT_TYPE} changes nothing (§16.3)")
    return AttributeChange(key, overrides, entity, version_key, label)


def attributes_at(st: AllocatedState, ob: ObligationState, at: date) -> LineAttributes:
    """The attributes of ``ob`` in force at ``at``: the booked account overrides and performing
    entity with every change effective on or before ``at`` applied in ENG-06 order (S06-R-26)."""
    overrides = dict(ob.account_overrides)
    entity = ob.performing_entity
    for ev in st.events:
        if ev.event_type != EVENT_TYPE or ev.contract_key != ob.contract_key:
            continue
        if ev.effective_date > at:
            continue
        found = change(ev)
        if found.obligation_key != ob.obligation_key:
            continue
        if found.account_overrides is not None:
            overrides.update(found.account_overrides)
        if found.performing_entity is not None:
            entity = found.performing_entity
    return LineAttributes(MappingProxyType(dict(sorted(overrides.items()))), entity)


@dataclass(frozen=True, slots=True)
class Reallocation:
    """The obligations re-allocated from inception by a corrected SSP version pin (S06-R-26)."""

    obligations: Mapping[str, ObligationState]  # subject key -> obligation after the event
    befores: Mapping[str, segments.Measured]  # subject key -> measured before the event
    share_nodes: Mapping[str, str]  # subject key -> mod_share node


def _invariant(message: str, ev: EventView, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=ev.contract_key,
        detail={"event_key": ev.event_key, "rule": "S06-R-26", **detail},
    )


def reallocate(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    found: AttributeChange,
    findings: list[Finding],
) -> Reallocation | None:
    """The group re-allocated from inception with the corrected SSP of the named obligation.

    ``None`` when a finding blocks the corrected resolution; nothing is emitted before it resolves.
    """
    target = next(
        (
            ob
            for ob in st.obligations
            if ob.contract_key == ev.contract_key and ob.obligation_key == found.obligation_key
        ),
        None,
    )
    if target is None:
        raise ValueError(f"{ev.event_key}: {found.obligation_key} is not an obligation (CV-45)")
    if len(st.tp_history) != 1:
        raise _invariant("a group with an earlier boundary is not re-allocated from inception", ev)
    in_force = {}
    for ob in st.obligations:
        seg = segments.in_force(st, ob, ev)
        if (
            seg is None
            or len(ob.segments) != 1
            or seg.cause != SegmentCause.INCEPTION
            or seg.basis != segments.INCEPTION
        ):
            raise _invariant(
                "an obligation of the group holds more than its inception segment",
                ev,
                obligation_key=ob.obligation_key,
            )
        in_force[ob.subject_key] = seg
    price = st.tp_history[-1]
    if sum(seg.a_posted for seg in in_force.values()) != price.allocation_basis.posted:
        raise _invariant("the inception allocations differ from the allocation basis", ev)
    corrected = weights.corrected(
        ctx,
        identified,
        target,
        st.inception_date,
        version_key=found.ssp_version_key,
        version_label=found.ssp_version_label,
        findings=findings,
        tb=tb,  # CV-50 rev 1.29 (D-98 123): the corrected original_ssp_selected@<event> node
        event_key=ev.event_key,
    )
    if corrected is None:
        return None
    mu = segments.minor_unit(ctx)
    weighted: list[weights.Weight] = []
    for ob in st.obligations:
        resolution: SspResolution | None
        if ob.subject_key == target.subject_key:
            value, member, entry, resolution = (
                corrected.selected,
                "corrected",
                corrected.entry_key,
                corrected,
            )
        else:
            value, member = weights.inception_ssp(ob)[0], "inception"
            entry, resolution = ("-" if ob.ssp is None else ob.ssp.entry_key), ob.ssp
        source = SourceRef(
            "ssp_entry", entry or "-", {"member": member, "value": format_exact(value)}
        )
        params = MappingProxyType({"member": member})
        weighted.append(
            weights.Weight(ob.subject_key, "D", value, (value,), (source,), resolution, params)
        )
    for weight in weighted:
        weights.emit(tb, ev, weight, basis=BASIS, formula_id=weights.D18_FORMULA)
    members = tuple(
        pool.Member(ob.subject_key, in_force[ob.subject_key].a_posted, 0) for ob in st.obligations
    )
    the_pool = pool.Pool(ev.contract_key, members, 0, 0, 0)
    pool_node = pool.emit(ctx, tb, ev, the_pool, mu, {"rule": "S06-R-26"})
    order = [(weight.subject_key, weight.value) for weight in weighted]
    shares = pool.apportion(ctx, tb, ev, the_pool, pool_node, order, mu)
    total_ssp = sum((weight.value for weight in weighted), Fraction(0))
    obligations: dict[str, ObligationState] = {}
    befores: dict[str, segments.Measured] = {}
    nodes: dict[str, str] = {}
    for ob in st.obligations:
        seg, share = in_force[ob.subject_key], shares[ob.subject_key]
        is_target = ob.subject_key == target.subject_key
        remaining = corrected.selected if is_target else seg.remaining_ssp
        unit = (
            seg.unit_ssp
            if not is_target
            else None
            if seg.totals.quantity == 0
            else remaining / seg.totals.quantity
        )
        boundary = segments.inception(
            ctx,
            ev,
            source=seg,
            x_exact=share.exact,
            a_posted=share.posted,
            totals=seg.totals,
            remaining_ssp=remaining,
            unit_ssp=unit,
            billing_plan=seg.remaining_billing_plan,
        )
        # CV-50 (D-98 candidate 121): the repin re-measures the two allocation columns — their
        # ``<column>@<event>`` pair over the repin's share, stamped on the state as the columns'
        # producer identity, which the assembler links.
        links = provenance.emit_original_allocation(
            ctx,
            tb,
            ev.event_key,
            ob.subject_key,
            Quota(share.exact, share.posted),
            exact_inputs=[share.node_id],
            amount_inputs=[share.node_id],
            rule="S06-R-26",
        )
        # CV-50 rev 1.29 (D-98 123): the target's corrected selected SSP and unit SSP, and every
        # reallocated obligation's total SSP, get their ``<column>@<event>`` producers.
        snapshot = provenance.emit_snapshot_columns(
            ctx,
            tb,
            ev.event_key,
            ob.subject_key,
            selected_node=(
                f"original_ssp_selected@{ev.event_key}:{ob.subject_key}:-" if is_target else None
            ),
            selected=corrected.selected if is_target else None,
            quantity=ob.original_quantity,
            stated_price=None,
            price=None,
            rule="S06-R-26",
            total_inputs=[
                f"mod_weight@{ev.event_key}:{item.subject_key}:-" for item in st.obligations
            ],
            total_value=total_ssp,
        )
        changed = dataclasses.replace(
            ob,
            segments=(*ob.segments, boundary),
            original_allocation=Quota(share.exact, share.posted),
            # CV-47 (b): the repin's share is the sole producer of the current original allocation
            original_allocation_nodes=(share.node_id,),
            original_allocation_links=links,
            # merged: a created-then-repinned obligation keeps its creation stamps (Codex 0944)
            snapshot_producer_links=MappingProxyType({**ob.snapshot_producer_links, **snapshot}),
            original_total_contract_ssp=total_ssp,
        )
        if is_target:
            changed = dataclasses.replace(changed, resolved_ssp=corrected.selected, ssp=corrected)
        obligations[ob.subject_key] = changed
        befores[ob.subject_key] = segments.measure(ctx, st, ob, seg, ev)
        nodes[ob.subject_key] = share.node_id
    return Reallocation(
        MappingProxyType(obligations), MappingProxyType(befores), MappingProxyType(nodes)
    )
