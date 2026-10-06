"""Stage 10 refund liabilities and return assets (ENGINE_SPEC_B §10.2.4, §10.2.5; ENC-12).

Refund liabilities are measured per component and never netted into the position except through
the control-role flows JET-04b creates (S10-R-13; POL-127; D-15). ``RETURN`` is round(p_ref × E_b)
per returnable obligation from the stage 09 ``ReturnState`` (POLICIES ALG-06 step 3).
``VARIABLE_CONSIDERATION`` is the ``refund_liability_target`` of the latest APPROVED version of a
refund-settled VC element (04 T-CON-13 rev 1.2); without a target, a REBATE, PRICE_PROTECTION,
REFUND or VOLUME_TIER version outside the LEGACY book takes
max(0, min(K_t, B_t − R_t − O_t)) over its target obligations, earlier elements by key first
(D-87 L5-3-Q-7 = L6-5-Q-11). Supervisor model-scope ruling of 2026-09-19 (ENC-VC-direction; the
32-10 basis is the supervisor's reading: a refund liability measures consideration the entity does
not expect to be entitled to, not a direction relative to another price component): (1) an
explicit ``refund_liability_target`` on one of the five refund-settled types drives the component
for either T-CON-12 ``direction``, a non-negative target including an explicit zero; (2) an
element without a target and ``direction`` ``INCREASE`` (a positive tiered overage, a bonus)
derives nothing and never reaches this producer — the derived form measures a reduction (K_t, D-87)
and applies to a ``DECREASE`` element only; (3) an explicit target on a type outside the five
(``VOLUME_TIER``, ``BONUS``, …), including an explicit zero, fails closed naming the supported
modelling route and is never silently discarded; (4) an explicit ``null`` target is the T-CON-13
"absent = 0" case (current behaviour, not an approved extension). ``TERMINATION`` is the
``refund_amount`` of
``CONTRACT_TERMINATED`` while the contract is not ``NOT_A_CONTRACT`` (POL-242; S02-R-08 routes the
others to the deposit), and ``CONCESSION`` is the stage 06 refund quota of a price concession
settled by credit memo or refund (S06-R-09; JET-05c; L2-4-Q-14). Both are consumed by credit memos
in ENG-06 order, termination refunds first, then concessions, oldest first (S10-R-14).
``UNCLAIMED_PROPERTY`` is the unclaimed-property amount A − C_total stage 09 publishes at the
expiry of a redemption-pattern obligation (``escheat_components``, S09-R-28; ENC-8), created on the
expiry date and consumed by the remittance credit memo (L2-4-Q-16). A termination refund, a
contract-level subject, is attributed to obligations by posted allocation at its creation date
(S10-R-15). Return assets are round(max(0, k − c_rec) ×
E), and the JET-07d derecognition is Σ round(max(0, k − c_rec) × min(units returned, E before the
return)) over the return events; neither enters the position (S10-R-16, S10-R-17). Every value
comes from a registered formula (DG-KRN-EXP-04). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.bundle import DECREASE, EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    encode_key,
    group_entity_subject_key,
)
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances import billing, classification
from erev_engine.stages.s10_billing_balances.billing import Billed, BillingDocumentOut
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ConcessionQuota,
    ContractView,
    EventView,
    ObligationState,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "CONCESSION",
    "CONSUMPTION_FORMULA",
    "DERIVED_TYPES",
    "FORMULA_OF_KIND",
    "KIND_ORDER",
    "RETURN",
    "RETURN_ASSET_FORMULA",
    "TERMINATION",
    "UNCLAIMED_PROPERTY",
    "VARIABLE_CONSIDERATION",
    "Consumption",
    "RefundComponent",
    "Refunds",
    "REFUND_SETTLED_TYPES",
    "TARGET_MEMBER",
    "TARGET_ROUTE",
    "derives",
    "excess_share",
    "explicit_target",
    "measure",
    "refund_candidate",
    "refuse_unsupported_target",
]

RETURN: Final = "RETURN"
VARIABLE_CONSIDERATION: Final = "VARIABLE_CONSIDERATION"
TERMINATION: Final = "TERMINATION"
CONCESSION: Final = "CONCESSION"
UNCLAIMED_PROPERTY: Final = "UNCLAIMED_PROPERTY"
# S10-R-14: consumed kinds in consumption order; RETURN and VARIABLE_CONSIDERATION are remeasured.
KIND_ORDER: Final[Mapping[str, int]] = MappingProxyType(
    {TERMINATION: 0, CONCESSION: 1, UNCLAIMED_PROPERTY: 2}
)
FORMULA_OF_KIND: Final[Mapping[str, str]] = MappingProxyType(
    {
        RETURN: "rl.return.v2",  # D-91: input 0 the stage 09 return_refundable_units node
        VARIABLE_CONSIDERATION: "rl.vc_target.v1",
        TERMINATION: "rl.termination.v1",
        CONCESSION: "rl.concession.v1",
        UNCLAIMED_PROPERTY: "rl.unclaimed_property.v1",
    }
)
CONSUMPTION_FORMULA: Final = "rl.consumption.v1"
RETURN_FORMULA_V1: Final = "rl.return.v1"  # stored traces; states without an E_b node (D-91)
_CONCESSION_CREATED: Final = "concession_created_cum"  # the JET-05c target (Table 14-A)
RETURN_ASSET_FORMULA: Final = "returns.return_asset.v1"
# ALG-10 §2.11.1 values of vc_element_type settled by refund or credit (§10.2.4; OQ-B-07): the five
# types on which T-CON-13 defines an explicit ``refund_liability_target`` (04 §16.14 rev 1.2).
REFUND_SETTLED_TYPES: Final = frozenset(
    {"REBATE", "PRICE_PROTECTION", "REFUND", "SLA_CREDIT", "DISCOUNT"}
)
TARGET_MEMBER: Final = "refund_liability_target"
# The supported modelling route a fail-closed unsupported target names (ENC-VC-direction).
TARGET_ROUTE: Final = (
    "model the refund as a separate VARIABLE_CONSIDERATION element of type "
    + "|".join(sorted(REFUND_SETTLED_TYPES))
    + " carrying the refund_liability_target (04 T-CON-13; ENGINE_SPEC_B §10.2.4), "
    "or omit the target and let a DECREASE REBATE, PRICE_PROTECTION, REFUND or VOLUME_TIER "
    "element derive the billed excess (D-87 L5-3-Q-7)"
)
# D-87 L5-3-Q-7 = L6-5-Q-11: types whose version without a target takes the billed excess.
DERIVED_TYPES: Final = frozenset({"REBATE", "PRICE_PROTECTION", "REFUND", "VOLUME_TIER"})
_LEGACY: Final = "LEGACY"  # keeps "0 without it"
CREDIT_OR_REFUND: Final = "CREDIT_OR_REFUND"  # T-CON-06 price_change_settlement (S06-R-07)
_MEASURE: Final = "refund_liability"
# S06-R-21: stage 06 keys a termination refund '<contract subject>#TERMINATION@<event key>'
# (D-88 L7-5-Q-2 (i)); the key form is matched here, not imported (DG-ENG-07).
_TERMINATION_MARK: Final = f"#{TERMINATION}@"


@dataclass(frozen=True, slots=True)
class Consumption:
    """The part of one credit memo that consumed a component (S10-R-14)."""

    document_key: str
    effective_date: date
    amount: int  # minor units
    node_id: str  # refund_liability_consumed@<memo key>:<component key>:-


@dataclass(frozen=True, slots=True)
class RefundComponent:
    """One refund-liability component of a (group, contracting entity) (§10.1)."""

    kind: str  # RETURN | VARIABLE_CONSIDERATION | TERMINATION | CONCESSION | UNCLAIMED_PROPERTY
    key: str  # "<group>@<entity>/<kind>/<source key>" (L2-4-Q-15)
    entity: str  # the contracting entity
    contract_key: str
    subject_key: str  # obligation subject key, or "<contract>@<entity>" (S10-R-15)
    source_key: str  # the creating event key, the estimate key or the obligation subject key
    created_on: date | None  # None for a remeasured component
    created_amount: int  # minor units; 0 for a remeasured component
    created_ref: SourceRef | None
    consumptions: tuple[Consumption, ...] = ()
    attribution: Mapping[str, int] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )  # obligation subject key -> share of the created amount (S10-R-15)
    # CONCESSION only: the producer's revenue basis (EMBEDDED | SEPARATE) the share-based numerator
    # reads (S10-R-26; D-91 L9-ENG-B3-Q-1); None for a quota built without the marker.
    revenue_basis: str | None = None
    # UNCLAIMED_PROPERTY only: the stage 09 ``unclaimed_property_cum`` node the component was
    # created from, cited as input 0 in place of a source reference (S09-R-28; ENC-8).
    created_node: str | None = None

    @property
    def created_input(self) -> str | SourceRef | None:
        """The creating reference the open-balance node cites first: a source or a node."""
        return self.created_ref if self.created_ref is not None else self.created_node

    def consumed_by(self, t: date) -> tuple[Consumption, ...]:
        """The consumptions by credit memos effective on or before ``t``."""
        return tuple(item for item in self.consumptions if item.effective_date <= t)


@dataclass(frozen=True, slots=True)
class Refunds:
    """Refund-liability components and return assets of one book (§10.2.4, §10.2.5)."""

    components: tuple[RefundComponent, ...]  # sorted by key
    refund_liabilities: tuple[Target, ...]  # per component and period; cause = the kind
    balances: Mapping[tuple[str, str], Target]  # (component key, period key) -> balance target
    return_assets: tuple[Target, ...]  # return_asset, return_asset_derecognised_cum per obligation
    concessions: tuple[Target, ...] = ()  # concession_created_cum (JET-05c)

    def concession_total(self, subject_key: str, t: date) -> int:
        """Σ ``CONCESSION`` amounts created on obligation ``subject_key`` by ``t`` (S10-R-09)."""
        return sum(
            component.created_amount
            for component in self.components
            if component.kind == CONCESSION
            and component.subject_key == subject_key
            and component.created_on is not None
            and component.created_on <= t
        )


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def _key(st: AllocatedState, entity: str, kind: str, source_key: str) -> str:
    """The component key ``<group>@<entity>/<kind>/<source key>`` (L2-4-Q-15); the group code and
    the entity are CV-21 encoded as stages 05 and 07 encode them (D-90d L9-RUN-Q-3)."""
    return f"{group_entity_subject_key(st.group_code, entity)}/{kind}/{source_key}"


def _period_ends(ctx: BookContext) -> dict[tuple[str, str], date]:
    return {
        (code, period.period_key): period.end_date
        for code, calendar in sorted(ctx.entities.items())
        for period in calendar.periods
    }


def _terminations(
    ctx: BookContext, st: AllocatedState, contracts: Mapping[str, ContractView], mu: int
) -> list[RefundComponent]:
    """``TERMINATION`` components from ``CONTRACT_TERMINATED.refund_amount`` (S06-R-21; POL-242)."""
    out: list[RefundComponent] = []
    for ev in st.events:  # ENG-06 order
        if ev.event_type != "CONTRACT_TERMINATED" or ev.payload.get("refund_amount") is None:
            continue
        contract = contracts.get(ev.contract_key)
        if contract is None:
            raise _invariant(
                "a termination names a contract absent from the state",
                ev.contract_key,
                rule="CV-45",
                event_key=ev.event_key,
            )
        amount = classification.amount_of(ev, "refund_amount", mu)
        if amount < 0:
            raise _invariant("a termination refund is negative", ev.contract_key, rule="S10-INV-02")
        if amount == 0 or _status_before(ctx, contract, ev) == "NOT_A_CONTRACT":
            # S02-R-07 (b), S02-R-08: a refund while NOT_A_CONTRACT settles the deposit liability
            # (JET-01b refund), also when the termination itself turns the status TERMINATED under
            # the nonrefundable outcome (EVENT_25_7_B; D-91 gaps (vi)).
            continue
        entity = contract.header.contracting_entity_code
        detail = {"member": "refund_amount", "value": money.format_money(amount, mu)}
        out.append(
            RefundComponent(
                kind=TERMINATION,
                key=_key(st, entity, TERMINATION, ev.event_key),
                entity=entity,
                contract_key=ev.contract_key,
                subject_key=contract_entity_subject_key(ev.contract_key, entity),
                source_key=ev.event_key,
                created_on=ev.effective_date,
                created_amount=amount,
                created_ref=SourceRef("contract_event", ev.event_key, detail),
            )
        )
    return out


def _status_before(ctx: BookContext, contract: ContractView, ev: EventView) -> str | None:
    """The book status in force before ``ev``: the status at its date unless a segment starts on
    that date, in which case the segment before it (the status the event replaced)."""
    history = contract.status_in_book.get(str(ctx.book_code), ())
    previous: str | None = None
    for when, status in history:
        if when > ev.effective_date:
            break
        if when == ev.effective_date and status != "NOT_A_CONTRACT":
            return previous
        previous = status
    return previous


def _concession_event(st: AllocatedState, ob: ObligationState) -> EventView:
    """The boundary that created the concession quota of ``ob`` (L2-4-Q-14).

    The latest ``CONTRACT_AMENDED`` among the obligation's ``MODIFICATION`` segments whose payload
    carries ``price_change_settlement = CREDIT_OR_REFUND``, else the latest ``MODIFICATION``
    boundary, else the latest ``TP_CHANGE`` boundary: the stage 08 ESTIMATE_CHANGED producer of a
    DISCOUNT or SLA_CREDIT share on a satisfied obligation (D-88 L7-5-Q-4 (iii)).
    """
    by_key = {ev.event_key: ev for ev in st.events}
    settled: EventView | None = None
    latest: EventView | None = None
    changed: EventView | None = None
    for seg in ob.segments:
        ev = None if seg.event_key is None else by_key.get(seg.event_key)
        if ev is None:
            continue
        if seg.cause == SegmentCause.TP_CHANGE:
            changed = ev
            continue
        if seg.cause != SegmentCause.MODIFICATION:
            continue
        latest = ev
        if ev.payload.get("price_change_settlement") == CREDIT_OR_REFUND:
            settled = ev
    found = settled or latest or changed
    if found is None:
        raise _invariant(
            "a concession refund quota has no modification or transaction-price boundary",
            ob.subject_key,
            rule="S10-R-13",
        )
    return found


def _is_termination_key(st: AllocatedState, key: str) -> bool:
    """D-88 L7-5-Q-2 (i): ``key`` has the S06-R-21 form '<contract subject>#TERMINATION@<event
    key>' naming a ``CONTRACT_TERMINATED`` event of the state, whose component ``_terminations``
    already creates from the event."""
    prefix, mark, event_key = key.partition(_TERMINATION_MARK)
    return bool(prefix and mark) and any(
        ev.event_type == "CONTRACT_TERMINATED" and ev.event_key == event_key for ev in st.events
    )


def _unclaimed_property(recognition: RecognitionState, mu: int) -> list[RefundComponent]:
    """``UNCLAIMED_PROPERTY`` components from the stage 09 escheat components (S09-R-28; JET-04b).

    One component per expired redemption obligation, created on its expiry date for the amount
    A − C_total stage 09 published at the first period end at or after the expiry; its creating
    reference is the ``unclaimed_property_cum`` node, so ``rl.unclaimed_property.v1`` (mode
    ``open``) reads the created amount from the cited node (ENC-8).
    """
    st = recognition.allocated
    obligations = {ob.subject_key: ob for ob in st.obligations}
    first: dict[str, tuple[str, int, date, str]] = {}
    for item in recognition.escheat_components:
        found = first.get(item.subject_key)
        if found is None or item.period_key < found[0]:
            first[item.subject_key] = (item.period_key, item.amount, item.expired_on, item.node_id)
    out: list[RefundComponent] = []
    for subject_key, (_, amount, expired_on, node_id) in sorted(first.items()):
        if amount == 0:
            continue
        ob = obligations.get(subject_key)
        if ob is None:
            raise _invariant(
                "an escheat component names an obligation absent from the state",
                subject_key,
                rule="S09-R-28",
            )
        if amount < 0:
            raise _invariant(
                "an unclaimed-property amount is negative", subject_key, rule="S10-INV-02"
            )
        out.append(
            RefundComponent(
                kind=UNCLAIMED_PROPERTY,
                key=_key(st, ob.contracting_entity, UNCLAIMED_PROPERTY, subject_key),
                entity=ob.contracting_entity,
                contract_key=ob.contract_key,
                subject_key=subject_key,
                source_key=subject_key,
                created_on=expired_on,
                created_amount=amount,
                created_ref=None,
                created_node=node_id,
            )
        )
    return out


def _concessions(st: AllocatedState, mu: int) -> list[RefundComponent]:
    """``CONCESSION`` components from ``AllocatedState.refund_components`` (S06-R-09; JET-05c).

    A termination refund key (S06-R-21) is skipped: ``_terminations`` creates that component."""
    obligations = {ob.subject_key: ob for ob in st.obligations}
    out: list[RefundComponent] = []
    for subject_key, quota in sorted(st.refund_components.items()):
        if quota.a_posted == 0 or _is_termination_key(st, subject_key):
            continue
        ob = obligations.get(subject_key)
        if ob is None:
            raise _invariant(
                "a refund quota names an obligation absent from the state",
                subject_key,
                rule="S06-R-09",
            )
        if quota.a_posted < 0:
            raise _invariant(
                "a concession refund quota is negative", subject_key, rule="S10-INV-02"
            )
        ev = _concession_event(st, ob)
        detail = {"member": "refund_component", "value": money.format_money(quota.a_posted, mu)}
        source_key = f"{ev.event_key}/{subject_key}"
        out.append(
            RefundComponent(
                kind=CONCESSION,
                key=_key(st, ob.contracting_entity, CONCESSION, source_key),
                entity=ob.contracting_entity,
                contract_key=ob.contract_key,
                subject_key=subject_key,
                source_key=source_key,
                created_on=ev.effective_date,
                created_amount=quota.a_posted,
                created_ref=SourceRef("contract_event", ev.event_key, detail),
                revenue_basis=(quota.revenue_basis if isinstance(quota, ConcessionQuota) else None),
            )
        )
    return out


def _consume(
    ctx: BookContext,
    tb: TraceBuilder,
    components: Sequence[RefundComponent],
    memos: Sequence[BillingDocumentOut],
    mu: int,
) -> list[RefundComponent]:
    """``consume_credit_memos`` of §10.2.4 (S10-R-14; S10-INV-07)."""
    order = sorted(
        (component for component in components if component.kind in KIND_ORDER),
        key=lambda component: (
            KIND_ORDER[component.kind],
            component.created_on,
            component.source_key,
        ),
    )
    open_amounts = {component.key: component.created_amount for component in order}
    taken_by: dict[str, list[Consumption]] = {component.key: [] for component in order}
    for memo in memos:  # ENG-06 order
        amount = sum(line.amount for line in memo.lines if line.in_position)
        if amount <= 0:
            continue
        detail = {"member": "amount", "value": money.format_money(amount, mu)}
        taken = 0
        for component in order:
            if taken == amount:
                break
            if component.contract_key != memo.contract_key or open_amounts[component.key] == 0:
                continue
            if component.created_on is None or component.created_on > memo.effective_date:
                continue
            take = min(open_amounts[component.key], amount - taken)
            node_id = tb.node(
                measure=f"refund_liability_consumed@{memo.document_key}",
                subject_key=component.key,
                period_key=None,
                value=take,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=CONSUMPTION_FORMULA,
                inputs=[SourceRef("contract_event", memo.document_key, detail)],
                params={
                    "as_of": memo.effective_date.isoformat(),
                    "open_before": str(open_amounts[component.key]),
                    "taken_before": str(taken),
                },
                narrative_key=_narrative(CONSUMPTION_FORMULA),
            )
            open_amounts[component.key] -= take
            taken += take
            taken_by[component.key].append(
                Consumption(memo.document_key, memo.effective_date, take, node_id)
            )
        if taken > amount or any(value < 0 for value in open_amounts.values()):
            raise _invariant(
                "a credit memo consumed more than its amount or a component went below 0",
                memo.contract_key,
                rule="S10-INV-07",
                event_key=memo.document_key,
            )
    return [
        dataclasses.replace(component, consumptions=tuple(taken_by.get(component.key, ())))
        for component in components
    ]


def _attribute(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder, component: RefundComponent, mu: int
) -> RefundComponent:
    """S10-R-15: a contract-level component by posted allocation at its creation date."""
    if component.kind != TERMINATION or component.created_on is None:
        return component
    created_on = component.created_on
    candidates = sorted(
        (
            ob
            for ob in st.obligations
            if ob.contract_key == component.contract_key
            and ob.contracting_entity == component.entity
            and not billing.is_vc_line(ob)
        ),
        key=lambda ob: ob.subject_key,
    )
    keys = [ob.subject_key for ob in candidates]
    weights = [Fraction(billing.posted_allocation(ob, created_on)) for ob in candidates]
    if sum(weights, Fraction(0)) == 0:
        weights = [ob.resolved_ssp for ob in candidates]
    if not keys or sum(weights, Fraction(0)) <= 0:
        raise _invariant(
            "a contract-level refund component has no obligation to attribute to",
            component.subject_key,
            rule="S10-R-15",
        )
    shares = money.largest_remainder(component.created_amount, weights, keys)
    formula_id = FORMULA_OF_KIND[component.kind]
    params = {
        "as_of": created_on.isoformat(),
        "keys": "|".join(keys),
        "mode": "apportion",
        "weights": "|".join(rational_param(weight) for weight in weights),
    }
    inputs: list[str | SourceRef] = [] if component.created_ref is None else [component.created_ref]
    for subject_key, share in zip(keys, shares, strict=True):
        tb.node(
            measure=f"refund_liability_attributed@{component.source_key}",
            subject_key=subject_key,
            period_key=None,
            value=share,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=formula_id,
            inputs=inputs,
            params={**params, "key": subject_key},
            narrative_key=_narrative(formula_id),
        )
    return dataclasses.replace(
        component, attribution=MappingProxyType(dict(zip(keys, shares, strict=True)))
    )


def _vc_amount(raw: object, subject_key: str) -> Fraction:
    if isinstance(raw, bool) or not isinstance(raw, str | int | Decimal | Fraction):
        raise _invariant("a refund_liability_target is malformed", subject_key, rule="CV-45")
    return money.to_fraction(raw)


def derives(book_code: str, element_type: str | None) -> bool:
    """D-87 L5-3-Q-7: a version without ``refund_liability_target`` takes the billed excess when
    its type is REBATE, PRICE_PROTECTION, REFUND or VOLUME_TIER and the book is not LEGACY. The
    caller has established the element reduces the price (``refund_candidate``)."""
    return str(book_code) != _LEGACY and element_type in DERIVED_TYPES


def explicit_target(version: EstimateVersionInput) -> object | None:
    """The version's explicit ``refund_liability_target`` (T-CON-13), ``None`` when absent or
    explicitly ``null`` (both "absent = 0"). An explicit ``"0.00"`` is a target."""
    return version.parameters.get(TARGET_MEMBER)


def refund_candidate(version: EstimateVersionInput) -> bool:
    """Whether a ``VARIABLE_CONSIDERATION`` version can produce a refund-liability component
    (§10.2.4; D-87 L5-3-Q-7; ENC-VC-direction ruling): an explicit target on one of the five
    refund-settled types, for either direction; or, without a target, a ``DECREASE`` element of a
    refund-settled or derived type (the derived form measures a reduction). An ``INCREASE``
    element without a target is never a candidate. An explicit target on any other type is
    refused by ``refuse_unsupported_target`` before this test is consulted."""
    if version.estimate_kind != VARIABLE_CONSIDERATION:
        return False
    if explicit_target(version) is not None:
        return version.vc_element_type in REFUND_SETTLED_TYPES
    return version.resolved_direction() == DECREASE and (
        version.vc_element_type in REFUND_SETTLED_TYPES or version.vc_element_type in DERIVED_TYPES
    )


def refuse_unsupported_target(version: EstimateVersionInput, estimate_key: str) -> None:
    """Ruling (3): an explicit ``refund_liability_target`` (including ``"0.00"``) on a type outside
    the five refund-settled types of T-CON-13 is outside the model; fail closed naming the type,
    the version and the supported route (``ENGINE_INVARIANT_VIOLATED``, CV-45). Never skipped,
    converted or partially computed (ENC-VC-direction)."""
    if (
        version.estimate_kind == VARIABLE_CONSIDERATION
        and explicit_target(version) is not None
        and version.vc_element_type not in REFUND_SETTLED_TYPES
    ):
        raise _invariant(
            f"{TARGET_MEMBER} is not supported on vc_element_type "
            f"{version.vc_element_type!r} (T-CON-13 defines it for "
            f"{'|'.join(sorted(REFUND_SETTLED_TYPES))}); {TARGET_ROUTE}",
            estimate_key,
            rule="CV-45",
            reason="REFUND_TARGET_TYPE_UNSUPPORTED",
            vc_element_type=str(version.vc_element_type),
            direction=version.resolved_direction(),
            estimate_version_key=version.version_key,
            supported_types="|".join(sorted(REFUND_SETTLED_TYPES)),
            route=TARGET_ROUTE,
        )


def _constrained_reduction(
    st: AllocatedState, version: EstimateVersionInput, t: date, mu: int
) -> int:
    """K_t of D-88 L7-6-Q-5: |posted amount| of the ``VcElementView`` naming the pinned version in
    the latest ``tp_history`` build-up with ``at`` ≤ t (S04-R-07's K, read from published state);
    when no build-up names that version, |``constrained_amount``|, else 0."""
    build = None
    for item in st.tp_history:
        if item.at <= t and (build is None or item.at >= build.at):
            build = item
    if build is not None:
        for element in build.elements:
            if (element.estimate_key, element.version_key) == (
                version.estimate_key,
                version.version_key,
            ):
                return abs(element.amount.posted)
    constrained = version.constrained_amount
    if constrained is None:
        return 0
    return money.round_half_up(abs(money.to_fraction(constrained)), mu)


def excess_share(k: int, billed: int, revenue: int, other: int, taken: int) -> int:
    """max(0, min(K_t, B_t − R_t − O_t − taken)) in minor units, where ``taken`` is the refund
    liability that earlier elements on the same obligations published (D-87 L5-3-Q-7)."""
    return max(0, min(k, billed - revenue - other - taken))


def _element_obligations(
    st: AllocatedState, target_keys: Sequence[str], obligation_key: str | None, contract_key: str
) -> frozenset[str]:
    """Subject keys of an element's target obligations: ``target_obligation_keys``, else
    ``obligation_key``, else every obligation of the contract (allocation target ``CONTRACT``)."""
    keys = tuple(target_keys) or (() if obligation_key is None else (obligation_key,))
    return frozenset(
        ob.subject_key
        for ob in st.obligations
        if ob.contract_key == contract_key
        and not billing.is_vc_line(ob)
        and (not keys or ob.obligation_key in keys)
    )


def _other_components(
    recognition: RecognitionState,
    components: Sequence[RefundComponent],
    balances: Mapping[tuple[str, str], Target],
    mu: int,
) -> dict[tuple[str, str], int]:
    """O_t per (obligation subject key, period key): the open RETURN, TERMINATION and CONCESSION
    components of the obligation (D-87 L5-3-Q-7). A termination refund takes its S10-R-15 shares
    of the open balance by largest remainder."""
    out: dict[tuple[str, str], int] = {}
    for (subject_key, period_key), state in recognition.return_states.items():
        value = money.round_half_up(state.p_ref * state.E_b, mu)
        out[(subject_key, period_key)] = out.get((subject_key, period_key), 0) + value
    by_key = {component.key: component for component in components}
    for (component_key, period_key), target in sorted(balances.items()):
        component = by_key.get(component_key)
        if component is None or component.kind not in (TERMINATION, CONCESSION):
            continue
        if component.kind == CONCESSION:
            shares = {component.subject_key: target.value}
        else:
            keys = sorted(component.attribution)
            weights = [Fraction(component.attribution[key]) for key in keys]
            if not keys or sum(weights, Fraction(0)) <= 0:
                continue
            shares = dict(
                zip(keys, money.largest_remainder(target.value, weights, keys), strict=True)
            )
        for subject_key, value in shares.items():
            out[(subject_key, period_key)] = out.get((subject_key, period_key), 0) + value
    return out


def measure(
    ctx: BookContext, recognition: RecognitionState, billed: Billed, tb: TraceBuilder
) -> Refunds:
    """Refund-liability components, their balances per period end and return assets (§10.2.4)."""
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    contracts = {view.header.external_id: view for view in st.contracts}
    by_encoded_id = {encode_key(view.header.external_id): view for view in st.contracts}
    obligations = {ob.subject_key: ob for ob in st.obligations}
    memos = [document for document in billed.documents if document.kind == "CREDIT_MEMO"]
    created = [
        *_terminations(ctx, st, contracts, mu),
        *_concessions(st, mu),
        *_unclaimed_property(recognition, mu),
    ]
    components = [
        _attribute(ctx, st, tb, item, mu) for item in _consume(ctx, tb, created, memos, mu)
    ]
    targets: list[Target] = []
    balances: dict[tuple[str, str], Target] = {}

    def publish(component: RefundComponent, period_key: str, value: int, node_id: str) -> None:
        if value < 0:
            raise _invariant(
                "a refund-liability component is negative", component.key, rule="S10-INV-02"
            )
        target = Target(
            book_code=ctx.book_code,
            entity=component.entity,
            subject_key=component.key,
            measure=_MEASURE,
            period_key=period_key,
            cause=component.kind,
            value=value,
            exact=None,
            node_id=node_id,
        )
        targets.append(target)
        balances[(component.key, period_key)] = target

    for component in sorted(components, key=lambda item: item.key):
        formula_id = FORMULA_OF_KIND[component.kind]
        created_on = component.created_on
        created_input = component.created_input
        if created_on is None or created_input is None:
            raise _invariant(
                "an event-created component has no creating event", component.key, rule="S10-R-14"
            )
        for period in billing.periods(ctx, st, component.entity):
            if created_on > period.end_date:
                continue
            consumed = component.consumed_by(period.end_date)
            value = component.created_amount - sum(item.amount for item in consumed)
            node_id = tb.node(
                measure=_MEASURE,
                subject_key=component.key,
                period_key=period.period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=formula_id,
                inputs=[created_input, *(item.node_id for item in consumed)],
                params={"as_of": period.end_date.isoformat(), "mode": "open"},
                narrative_key=_narrative(formula_id),
            )
            publish(component, period.period_key, value, node_id)

    # JET-05c creates each CONCESSION component: its created amount per obligation and period end
    # from creation on, unchanged by consumption, which JET-04b carries (Table 14-A; L4-3-Q-42).
    concessions: list[Target] = []
    for component in sorted(components, key=lambda item: item.key):
        if component.kind != CONCESSION or component.created_on is None:
            continue
        if component.created_ref is None:
            raise _invariant("a concession has no creating event", component.key, rule="S10-R-14")
        formula_id = FORMULA_OF_KIND[CONCESSION]
        for period in billing.periods(ctx, st, component.entity):
            if component.created_on > period.end_date:
                continue
            node_id = tb.node(
                measure=_CONCESSION_CREATED,
                subject_key=component.subject_key,
                period_key=period.period_key,
                value=component.created_amount,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=formula_id,
                inputs=[component.created_ref],
                params={"as_of": period.end_date.isoformat(), "mode": "open"},
                narrative_key=_narrative(formula_id),
            )
            concessions.append(
                Target(
                    ctx.book_code,
                    component.entity,
                    component.subject_key,
                    _CONCESSION_CREATED,
                    period.period_key,
                    component.key,  # stage 14 nets JET-04b by component (D-88 L7-5-Q-4 (2))
                    component.created_amount,
                    None,
                    node_id,
                )
            )

    remeasured: dict[str, RefundComponent] = {}
    # D-87 L5-3-Q-7 = L6-5-Q-11: B_t, R_t and O_t per (obligation, period) for the derived form,
    # and the refund liability earlier elements published per period (target set, value).
    billed_at = {
        (item.subject_key, item.period_key): item.value
        for item in billed.targets
        if item.measure == "billed_cum"
    }
    revenue_at = {
        (item.subject_key, item.period_key): item.value
        for item in recognition.revenue_targets
        if item.measure == "revenue_cum"
    }
    other_at = _other_components(recognition, components, balances, mu)
    taken_at: dict[str, list[tuple[frozenset[str], int]]] = {}
    for estimate_key, pins in sorted(st.estimates.pins.items()):
        versions = [pin.version for pin in pins]
        # ENC-VC-direction ruling: an unsupported explicit target fails closed before any
        # component; an INCREASE element without a target never reaches this producer.
        for item in versions:
            refuse_unsupported_target(item, estimate_key)
        if not any(refund_candidate(item) for item in versions):
            continue
        # The estimate key head is the CV-21 encoded contract id (D-90d L9-RUN-Q-8); a
        # ``PORTFOLIO:<code>`` head never equals an encoded id.
        contract = by_encoded_id.get(estimate_key.split("/", 1)[0])
        if contract is None:
            continue  # a portfolio-scoped element applies through member versions (L2-4-Q-16)
        entity = contract.header.contracting_entity_code
        component = RefundComponent(
            kind=VARIABLE_CONSIDERATION,
            key=_key(st, entity, VARIABLE_CONSIDERATION, estimate_key),
            entity=entity,
            contract_key=contract.header.external_id,
            subject_key=contract_entity_subject_key(contract.header.external_id, entity),
            source_key=estimate_key,
            created_on=None,
            created_amount=0,
            created_ref=None,
        )
        remeasured[component.key] = component
        first = min(version.effective_date for version in versions)
        for period in billing.periods(ctx, st, entity):
            if period.end_date < first:
                continue
            version = st.estimates.pin(estimate_key, period.end_date)
            inputs: list[str | SourceRef] = []
            raw = None if version is None else explicit_target(version)
            value = 0
            params = {"as_of": period.end_date.isoformat()}
            subjects: frozenset[str] = frozenset()
            if version is not None:
                subjects = _element_obligations(
                    st,
                    version.target_obligation_keys,
                    version.obligation_key,
                    contract.header.external_id,
                )
            if version is not None and raw is not None:
                exact = _vc_amount(raw, component.key)
                value = money.round_half_up(exact, mu)
                detail = {"member": "refund_liability_target", "value": money.format_exact(exact)}
                inputs.append(SourceRef("estimate_version", version.version_key, detail))
            elif (
                version is not None
                and version.resolved_direction() == DECREASE
                and derives(ctx.book_code, version.vc_element_type)
            ):
                k = _constrained_reduction(st, version, period.end_date, mu)
                key_of = [(subject, period.period_key) for subject in sorted(subjects)]
                figures = {
                    "billed": sum(billed_at.get(item, 0) for item in key_of),
                    "revenue": sum(revenue_at.get(item, 0) for item in key_of),
                    "other": sum(other_at.get(item, 0) for item in key_of),
                    "taken": sum(
                        taken
                        for keys, taken in taken_at.get(period.period_key, ())
                        if keys & subjects
                    ),
                }
                value = excess_share(k, *figures.values())
                detail = {"member": "vc_constrained", "value": money.format_money(k, mu)}
                inputs.append(SourceRef("estimate_version", version.version_key, detail))
                params.update({name: str(amount) for name, amount in figures.items()})
                params.update({"keys": "|".join(sorted(subjects)), "mode": "excess"})
            formula_id = FORMULA_OF_KIND[VARIABLE_CONSIDERATION]
            node_id = tb.node(
                measure=_MEASURE,
                subject_key=component.key,
                period_key=period.period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=formula_id,
                inputs=inputs,
                params=params,
                narrative_key=_narrative(formula_id),
            )
            publish(component, period.period_key, value, node_id)
            if value:
                taken_at.setdefault(period.period_key, []).append((subjects, value))

    ends = _period_ends(ctx)
    assets: list[Target] = []
    for (subject_key, period_key), state in sorted(recognition.return_states.items()):
        ob = obligations[subject_key]
        as_of = ends[(ob.performing_entity, period_key)].isoformat()
        component = remeasured.setdefault(
            _key(st, ob.contracting_entity, RETURN, subject_key),
            RefundComponent(
                kind=RETURN,
                key=_key(st, ob.contracting_entity, RETURN, subject_key),
                entity=ob.contracting_entity,
                contract_key=ob.contract_key,
                subject_key=subject_key,
                source_key=subject_key,
                created_on=None,
                created_amount=0,
                created_ref=None,
            ),
        )
        value = money.round_half_up(state.p_ref * state.E_b, mu)
        # D-91 C606-01 (7): the component cites stage 09's E_b node (rl.return.v2). A state whose
        # returns target traced no expected-units node (no E_b node) keeps the stored-trace v1 form.
        formula_id = FORMULA_OF_KIND[RETURN] if state.e_b_node_id is not None else RETURN_FORMULA_V1
        params = {"as_of": as_of, "p_ref": rational_param(state.p_ref)}
        if state.e_b_node_id is None:
            params["e_b"] = rational_param(state.E_b)
        node_id = tb.node(
            measure=_MEASURE,
            subject_key=component.key,
            period_key=period_key,
            value=value,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=formula_id,
            inputs=[] if state.e_b_node_id is None else [state.e_b_node_id],
            params=params,
            narrative_key=_narrative(formula_id),
        )
        publish(component, period_key, value, node_id)
        unit = max(Fraction(0), state.k - state.c_rec)
        quantities = [quantity for _, quantity in state.returns_before_E]
        balance = money.round_half_up(unit * state.E, mu)
        derecognised = sum(money.round_half_up(unit * quantity, mu) for quantity in quantities)
        for measure_name, value, params in (
            ("return_asset", balance, {"expected": rational_param(state.E), "mode": "balance"}),
            (
                "return_asset_derecognised_cum",
                derecognised,
                {
                    "mode": "derecognised",
                    "quantities": "|".join(rational_param(quantity) for quantity in quantities),
                },
            ),
        ):
            if value < 0:
                raise _invariant("a return asset is negative", subject_key, rule="S10-INV-02")
            node_id = tb.node(
                measure=measure_name,
                subject_key=subject_key,
                period_key=period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=RETURN_ASSET_FORMULA,
                inputs=[],
                params={**params, "as_of": as_of, "unit": rational_param(unit)},
                narrative_key=_narrative(RETURN_ASSET_FORMULA),
            )
            assets.append(
                Target(
                    ctx.book_code,
                    ob.contracting_entity,
                    subject_key,
                    measure_name,
                    period_key,
                    None,
                    value,
                    None,
                    node_id,
                )
            )
    every = sorted([*components, *remeasured.values()], key=lambda item: item.key)
    return Refunds(
        components=tuple(every),
        refund_liabilities=tuple(sorted(targets, key=lambda t: (t.subject_key, t.period_key))),
        balances=MappingProxyType(balances),
        return_assets=tuple(assets),
        concessions=tuple(concessions),
    )
