"""Stage 10 share-based consideration payable and the composed JET-14 release (ENGINE_SPEC
S04-R-17 rev 1.6; ENGINE_SPEC_B §10.1 ``customer_consideration``, S10-R-26, §10.4, §10.5; POLICIES
PT-10, POL-246 (CHK-120); 04 T-CON-13 ``SHARE_BASED_CONSIDERATION``, table 15.4-C
``CPC_RELATED_SCOPE_INVALID``; D-91 C606-03).

Runs last in stage 10, after the concessions exist. For each contract with a stage 04 EMOD-22
series and each contracting period end t, per related obligation: the selected revenue node is
the posted stage 09 ``revenue_cum`` at the latest performing-entity period end c ≤ t (as stage 13
maps relief, S10-R-09); R(t) = Σ selected revenue − Σ posted portions of the JET-05c concessions
the selected node does not carry, a signed sum with no floor. The portions are the dated source
subledger ``AllocatedState.concession_history`` (one accepted addition per producing event and
receiving obligation, with the producer's exact share, its allocated posted cents and its
``revenue_basis``): an EMBEDDED portion (stage 06 S06-R-09 under CREDIT_OR_REFUND and stage 08
D-88 L7-5-Q-4 (iii) apply the negative share to the obligation's recognition segment) is
subtracted while its effective date lies after c and on or before t (the node cannot yet contain
it) and drops out once a later performing close embeds it (stage 09 excludes only boundaries after
the node's own cutoff; param ``concessions_embedded`` counts those left out); a SEPARATE portion
(none in 1.0-rc) is always subtracted. Each subtracted portion is cited through its own dated node
``concession_portion@<event>:<obligation>:<period>`` (``tp.cpc_release.v1`` over the producing
event's source; param ``aggregate_node`` names the unchanged ``concession_created_cum`` node),
never through the collapsed aggregate; the aggregate refund component, its node, JET-05c / JET-04b
netting and credit-memo consumption are untouched. The subledger is validated once per run by
``check_history`` over its FULL history against the final quota per obligation (Σ exact =
quota.x_exact, Σ posted = quota.a_posted; every portion dated by a producing event of the state
with a known producer; a quota without history, a history without a quota or a history exceeding
the quota is ``ENGINE_INVARIANT_VIOLATED``) and is never compared with the aggregate at an
intermediate t: the aggregate's date is its producer's (a settled modification is preferred over a
later TP_CHANGE), so the two populations carry unlike dates across mixed producers. Each
concession counts exactly once at every t (the supervisor's count-once cutoff ruling on
L9-ENG-B3-Q-1). Per element with the version
pinned at t, Red_e(t) = 0 while t < ``grant_date`` or vesting
is not probable, 0 when E ≤ 0 with R(t) = 0 (no division), ``NON_FINITE_AMOUNT`` when E ≤ 0 with
R(t) ≠ 0, else round_half_up(min(F, F × R(t) ÷ E)) once per element and period (CV-35). Nodes:
``share_based_reduction_element_cum:<contract>/<element>:<period>`` (``tp.cpc_share_based.v1``;
inputs the award ``estimate_version`` source then the selected revenue node ids and the not-yet-
embedded concession portion node ids; params ``revenue_cutoff`` = the selected node's cutoff and
``concessions_embedded`` = the count left out),
``share_based_reduction_cum`` and ``incentive_release_cum`` per ``<contract>@<entity>``
(``tp.cpc_release.v1`` signed sums of posted nodes, no further rounding). The related obligations
are the union of ``related_obligation_keys`` of the promises with ``share_based = true`` (empty =
every obligation); without a share-based promise the element's own keys, else every obligation;
element keys, when set, must equal the promise scope and every key must name an obligation
(``CPC_RELATED_SCOPE_INVALID``, ``ERROR``, reasons ``MISMATCH`` | ``UNKNOWN_OBLIGATION``). Private
to stage 10. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.bundle import EstimateVersionInput, PayableInput
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    contract_subject_key,
    member_in_force,
    payload_date,
    payload_fraction,
)
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances.refund_liability import CONCESSION, RefundComponent
from erev_engine.stages.state import (
    CONCESSION_SEPARATE,
    AllocatedState,
    BookContext,
    ConcessionAddition,
    ContractView,
    Finding,
    ObligationState,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ELEMENT",
    "check_history",
    "ORDINARY_RELEASE",
    "RELEASE",
    "RELEASE_FORMULA",
    "SHARE_BASED",
    "SHARE_BASED_FORMULA",
    "CustomerConsideration",
    "measure",
]

SHARE_BASED_FORMULA: Final = "tp.cpc_share_based.v1"
RELEASE_FORMULA: Final = "tp.cpc_release.v1"
KIND: Final = "SHARE_BASED_CONSIDERATION"
MEMBER: Final = "consideration_payable"  # 04 API-S-ConsiderationPayable (S04-R-14)
ORDINARY_RELEASE: Final = "incentive_release_ordinary_cum"  # stage 04 (S04-R-16)
ELEMENT: Final = "share_based_reduction_element_cum"
SHARE_BASED: Final = "share_based_reduction_cum"
RELEASE: Final = "incentive_release_cum"
REVENUE: Final = "revenue_cum"
SCOPE_INVALID: Final = "CPC_RELATED_SCOPE_INVALID"
# POL-246 LATER_OF_RELATED_REVENUE_AND_GRANT is FORCED; no window parameter in the rc (D-91 (2)).
TIMING: Final = "LATER_OF_RELATED_REVENUE_AND_GRANT"
STAGE: Final = 10
ZERO: Final = Fraction(0)


@dataclass(frozen=True, slots=True)
class CustomerConsideration:
    """The stage 10 EMOD-22 rows (S10-R-26) and the scope findings."""

    targets: tuple[Target, ...]  # element, aggregate and composed release per period
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class _Scope:
    """The related obligations of a contract's share-based awards (D-91 (3))."""

    promised: bool  # the contract has a share-based promise
    keys: frozenset[str]  # obligation keys; empty with ``promised`` = every obligation


def measure(
    ctx: BookContext,
    st: RecognitionState,
    components: Sequence[RefundComponent],
    concessions: Sequence[Target],
    listed: Sequence[Target],
    tb: TraceBuilder,
) -> CustomerConsideration:
    """S10-R-26 over the stage 04 EMOD-22 series ``listed`` (payable, ordinary release, asset);
    ``components`` are the stage 10 refund components (the CONCESSION ones name the aggregate
    quota), ``concessions`` the aggregate ``concession_created_cum`` targets (``cause`` = component
    key); the dated portions come from ``allocated.concession_history``."""
    allocated = st.allocated
    history: dict[str, list[ConcessionAddition]] = {}
    for addition in sorted(allocated.concession_history, key=lambda item: item.order_key):
        history.setdefault(addition.subject_key, []).append(addition)
    check_history(allocated, history)
    concession_keys = {component.key for component in components if component.kind == CONCESSION}
    aggregates: dict[tuple[str, str], Target] = {}
    for target in concessions:
        if target.cause in concession_keys:
            aggregates[(target.subject_key, target.period_key)] = target
    portion_nodes: dict[tuple[str, str, str], str] = {}
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    ends = {
        (code, period.period_key): period.end_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    revenue: dict[str, list[Target]] = {}
    for target in st.revenue_targets:
        if target.measure == REVENUE:
            revenue.setdefault(target.subject_key, []).append(target)
    for items in revenue.values():
        items.sort(key=lambda item: ends[(item.entity, item.period_key)])
    ordinary = {
        (target.subject_key, target.period_key): target
        for target in listed
        if target.measure == ORDINARY_RELEASE
    }
    found: list[Target] = []
    findings: list[Finding] = []
    for contract in sorted(allocated.contracts, key=lambda item: item.header.external_id):
        contract_key = contract.header.external_id
        entity = contract.header.contracting_entity_code
        subject = contract_entity_subject_key(contract_key, entity)
        series = sorted(
            (period_key for (key, period_key) in ordinary if key == subject),
            key=lambda period_key: ends[(entity, period_key)],
        )
        if not series:
            continue
        obligations = {
            ob.obligation_key: ob for ob in allocated.obligations if ob.contract_key == contract_key
        }
        elements = _element_keys(allocated, contract_key)
        scope = _promise_scope(allocated, contract, subject, obligations, findings)
        flagged: set[str] = set()
        for period_key in series:
            t = ends[(entity, period_key)]
            element_nodes: list[str] = []
            share_posted = 0
            for key in elements:
                if key in flagged or scope is None:
                    continue
                version = allocated.estimates.pin(key, t)
                if version is None:
                    continue
                related = _element_scope(key, version, scope, obligations, findings)
                if related is None:
                    flagged.add(key)
                    continue
                posted, node_id = _element(
                    ctx,
                    tb,
                    key,
                    version,
                    tuple(ob.subject_key for ob in related),
                    t,
                    period_key,
                    revenue,
                    aggregates,
                    history,
                    ends,
                    scale,
                    portion_nodes,
                )
                element_nodes.append(node_id)
                share_posted += posted
                found.append(
                    Target(
                        book_code=ctx.book_code,
                        entity=entity,
                        subject_key=key,
                        measure=ELEMENT,
                        period_key=period_key,
                        cause=None,
                        value=posted,
                        exact=None,
                        node_id=node_id,
                    )
                )
            release_inputs: list[str | SourceRef] = [ordinary[(subject, period_key)].node_id]
            signs = ["+"]
            if elements:
                share_node = _posted_sum(
                    ctx, tb, SHARE_BASED, subject, period_key, share_posted, element_nodes, scale
                )
                found.append(
                    _target(ctx, entity, subject, SHARE_BASED, period_key, share_posted, share_node)
                )
                release_inputs.append(share_node)
                signs.append("+")
            release_posted = ordinary[(subject, period_key)].value + share_posted
            release_node = _posted_sum(
                ctx, tb, RELEASE, subject, period_key, release_posted, release_inputs, scale, signs
            )
            found.append(
                _target(ctx, entity, subject, RELEASE, period_key, release_posted, release_node)
            )
    return CustomerConsideration(tuple(found), tuple(findings))


def _element(
    ctx: BookContext,
    tb: TraceBuilder,
    key: str,
    version: EstimateVersionInput,
    related: Sequence[str],
    t: date,
    period_key: str,
    revenue: Mapping[str, Sequence[Target]],
    aggregates: Mapping[tuple[str, str], Target],
    history: Mapping[str, Sequence[ConcessionAddition]],
    ends: Mapping[tuple[str, str], date],
    scale: int,
    portion_nodes: dict[tuple[str, str, str], str],
) -> tuple[int, str]:
    """One element's ``share_based_reduction_element_cum`` node at t over the related obligations'
    subject keys; (posted, node id). Per obligation the selected revenue node is the latest with
    period end c ≤ t. Of the dated concession portions created on or before t, an EMBEDDED portion
    dated after c is subtracted and cited (its ``concession_portion@<event>`` node, sign −), one
    dated on or before c is embedded and counted in ``concessions_embedded``; a SEPARATE portion is
    always subtracted and cited; without a revenue node every portion is subtracted. The portions
    are never compared with the aggregate ``concession_created_cum`` at t (``check_history``
    validates the subledger over its full history). ``portion_nodes`` shares emitted portion nodes
    across elements."""
    params = version.parameters
    fair = payload_fraction(params, "grant_date_fair_value")
    if fair is None or version.expected_total_amount is None:
        raise ValueError(f"{version.version_key}: grant_date_fair_value and expected total needed")
    expected = to_fraction(version.expected_total_amount)
    grant = payload_date(params, "grant_date") or version.effective_date
    probable = params.get("vesting_probable") in (True, "true")
    inputs: list[str | SourceRef] = [
        SourceRef("estimate_version", version.version_key, {"value": format_exact(fair)})
    ]
    signs: list[str] = []
    numerator = ZERO
    embedded = 0
    cutoffs: list[date] = []
    for subject_key in sorted(related):
        before = [
            item
            for item in revenue.get(subject_key, ())
            if ends[(item.entity, item.period_key)] <= t
        ]
        cutoff: date | None = None
        if before:
            last = before[-1]
            cutoff = ends[(last.entity, last.period_key)]
            cutoffs.append(cutoff)
            numerator += Fraction(last.value, scale)
            inputs.append(last.node_id)
            signs.append("+")
        # The dated portions are never compared with the aggregate concession_created_cum at t:
        # the aggregate's date is its producer's (refund_liability._concession_event prefers a
        # settled modification over a later TP_CHANGE), so the two populations carry unlike dates
        # across mixed stage 06 / stage 08 producers. The subledger is validated by check_history
        # over its full history against the final quota; the aggregate node is cited as lineage.
        portions = [item for item in history.get(subject_key, ()) if item.effective_date <= t]
        aggregate = aggregates.get((subject_key, period_key))
        for item in portions:
            if (
                item.revenue_basis != CONCESSION_SEPARATE
                and cutoff is not None
                and item.effective_date <= cutoff
            ):
                embedded += 1  # the selected node already carries it: counted once, not cited
                continue
            numerator -= Fraction(item.posted, scale)
            inputs.append(_portion_node(ctx, tb, item, period_key, aggregate, scale, portion_nodes))
            signs.append("-")
    if t < grant or not probable:
        exact = ZERO
    elif expected <= 0:
        if numerator != 0:
            raise EngineError(
                "NON_FINITE_AMOUNT",
                "the share-based reduction has no expected related revenue",
                subject_key=key,
                formula_id=SHARE_BASED_FORMULA,
                detail={
                    "formula_id": SHARE_BASED_FORMULA,
                    "subject_key": key,
                    "period_key": period_key,
                    "related_revenue": format_exact(numerator),
                },
            )
        exact = ZERO
    else:
        exact = min(fair, fair * numerator / expected)
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    posted = round_half_up(exact, minor_unit)
    node_id = tb.node(
        measure=ELEMENT,
        subject_key=key,
        period_key=period_key,
        value=posted,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=SHARE_BASED_FORMULA,
        inputs=inputs,
        params={
            "concessions_embedded": str(embedded),
            "expected": format_exact(expected),
            "grant_date": grant.isoformat(),
            "period_end": t.isoformat(),
            # The selected revenue nodes' own cutoffs (one per related obligation with a node).
            "revenue_cutoff": ",".join(c.isoformat() for c in cutoffs) or "-",
            "signs": ",".join(signs),
            "timing": TIMING,
            "vesting_probable": "true" if probable else "false",
        },
        exact=exact,
        narrative_key=SHARE_BASED_FORMULA.rsplit(".v", 1)[0],
    )
    return posted, node_id


PRODUCERS: Final = frozenset({"06", "08"})


def check_history(st: AllocatedState, history: Mapping[str, Sequence[ConcessionAddition]]) -> None:
    """Conservation of the dated concession subledger against the final quotas (S10-R-26): per
    obligation Σ portion.exact = quota.x_exact and Σ portion.posted = quota.a_posted (never
    re-rounded); every portion names a producing event of the state, is dated by it and names a
    known producer; a history without a quota, or a quota without history, fails closed. The check
    is independent of the temporal cutoff selection."""
    events = {event.event_key: event for event in st.events}
    quotas = {
        key: quota
        for key, quota in st.refund_components.items()
        if "#" not in key  # termination refunds are keyed <contract>#TERMINATION@<event>
    }
    for subject_key in sorted(set(history) | set(quotas)):
        portions = history.get(subject_key, ())
        quota = quotas.get(subject_key)
        detail = {"rule": "S10-R-26", "obligation": subject_key}
        for item in portions:
            event = events.get(item.event_key)
            if event is None or item.producer not in PRODUCERS:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a concession portion names no producing event or an unknown producer",
                    subject_key=subject_key,
                    detail={**detail, "event_key": item.event_key, "producer": item.producer},
                )
            if item.effective_date != event.effective_date:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a concession portion is not dated by its producing event",
                    subject_key=subject_key,
                    detail={
                        **detail,
                        "event_key": item.event_key,
                        "portion_date": item.effective_date.isoformat(),
                        "event_date": event.effective_date.isoformat(),
                    },
                )
        if quota is None:
            if portions:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "concession portions exist without a refund quota",
                    subject_key=subject_key,
                    detail={**detail, "portions": str(sum(item.posted for item in portions))},
                )
            continue
        if quota.x_exact == 0 and quota.a_posted == 0 and not portions:
            continue  # a genuinely empty quota with no history to reconcile
        exact = sum((item.exact for item in portions), ZERO)
        posted = sum(item.posted for item in portions)
        if exact != quota.x_exact or posted != quota.a_posted:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the dated concession portions do not conserve the refund quota",
                subject_key=subject_key,
                detail={
                    **detail,
                    "portions_exact": format_exact(exact),
                    "portions_posted": str(posted),
                    "quota_exact": format_exact(quota.x_exact),
                    "quota_posted": str(quota.a_posted),
                },
            )


def _portion_node(
    ctx: BookContext,
    tb: TraceBuilder,
    item: ConcessionAddition,
    period_key: str,
    aggregate: Target | None,
    scale: int,
    portion_nodes: dict[tuple[str, str, str], str],
) -> str:
    """The dated event-level node of one concession portion at ``period_key``:
    ``concession_portion@<event key>:<obligation>:<period>`` (``tp.cpc_release.v1`` over the
    producing event's source valued at the portion's posted amount), emitted once and shared by
    every element that cites it; param ``aggregate_node`` names the unchanged aggregate
    ``concession_created_cum`` node (its id is never duplicated)."""
    cache_key = (item.event_key, item.subject_key, period_key)
    found = portion_nodes.get(cache_key)
    if found is not None:
        return found
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    value = Fraction(item.posted, scale)
    node_id = tb.node(
        measure=f"concession_portion@{item.event_key}",
        subject_key=item.subject_key,
        period_key=period_key,
        value=item.posted,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=RELEASE_FORMULA,
        inputs=[
            SourceRef(
                "contract_event",
                item.event_key,
                {"member": "refund_component", "value": format_exact(value)},
            )
        ],
        params={
            "aggregate_node": "-" if aggregate is None else aggregate.node_id,
            "effective_date": item.effective_date.isoformat(),
            "exact": format_exact(item.exact),
            "producer": item.producer,
            "revenue_basis": item.revenue_basis,
            "signs": "+",
        },
        exact=value,
        narrative_key=RELEASE_FORMULA.rsplit(".v", 1)[0],
    )
    portion_nodes[cache_key] = node_id
    return node_id


def _posted_sum(
    ctx: BookContext,
    tb: TraceBuilder,
    measure_name: str,
    subject: str,
    period_key: str,
    value: int,
    inputs: Sequence[str | SourceRef],
    scale: int,
    signs: Sequence[str] | None = None,
) -> str:
    """A ``tp.cpc_release.v1`` node: the signed sum of posted nodes, no further rounding."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    return tb.node(
        measure=measure_name,
        subject_key=subject,
        period_key=period_key,
        value=value,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=RELEASE_FORMULA,
        inputs=list(inputs),
        params={"signs": ",".join(signs if signs is not None else ("+" for _ in inputs))},
        exact=Fraction(value, scale),
        narrative_key=RELEASE_FORMULA.rsplit(".v", 1)[0],
    )


def _target(
    ctx: BookContext,
    entity: str,
    subject: str,
    measure_name: str,
    period_key: str,
    value: int,
    node_id: str,
) -> Target:
    return Target(
        book_code=ctx.book_code,
        entity=entity,
        subject_key=subject,
        measure=measure_name,
        period_key=period_key,
        cause=None,
        value=value,
        exact=None,
        node_id=node_id,
    )


def _element_keys(st: AllocatedState, contract_key: str) -> tuple[str, ...]:
    """The contract's ``SHARE_BASED_CONSIDERATION`` element keys, sorted (as stage 04 reads
    them)."""
    pins = st.estimates.pins
    head = contract_subject_key(contract_key)
    return tuple(
        key
        for key in sorted(pins)
        if pins[key]
        and pins[key][-1].version.estimate_kind == KIND
        and key.split("/", 1)[0] == head
    )


def _share_based_promises(
    st: AllocatedState, contract: ContractView
) -> list[tuple[str, ...] | None]:
    """The related keys of each share-based promise of the list in force (S01-R-20); ``None`` for
    a malformed item (stage 04 raises CV-45 first)."""
    contract_key = contract.header.external_id
    value = member_in_force(st.events, contract_key, MEMBER, date.max)
    items: Sequence[object]
    if value is None:
        items = contract.header.consideration_payable
    elif isinstance(value, list | tuple):
        items = value
    else:
        return []
    found: list[tuple[str, ...] | None] = []
    for item in items:
        if isinstance(item, PayableInput):
            if item.share_based:
                found.append(tuple(item.related_obligation_keys))
        elif isinstance(item, Mapping):
            if item.get("share_based") in (True, "true"):
                raw = item.get("related_obligation_keys") or ()
                if isinstance(raw, list | tuple) and all(isinstance(k, str) for k in raw):
                    found.append(tuple(str(k) for k in raw))
                else:
                    found.append(None)
    return found


def _promise_scope(
    st: AllocatedState,
    contract: ContractView,
    subject: str,
    obligations: Mapping[str, ObligationState],
    findings: list[Finding],
) -> _Scope | None:
    """The union of the share-based promises' related keys (empty = every obligation); ``None``
    after an ``UNKNOWN_OBLIGATION`` finding on the promise scope."""
    promises = _share_based_promises(st, contract)
    if not promises:
        return _Scope(False, frozenset())
    keys: set[str] = set()
    every = False
    for related in promises:
        if not related:
            every = True
            continue
        keys.update(related)
    unknown = sorted(key for key in keys if key not in obligations)
    if unknown:
        findings.append(
            Finding(
                SCOPE_INVALID,
                "ERROR",
                subject,
                {
                    "reason": "UNKNOWN_OBLIGATION",
                    "rule": "S10-R-26",
                    "source": "promise",
                    "unknown_keys": ",".join(unknown),
                },
                STAGE,
                None,
            )
        )
        return None
    return _Scope(True, frozenset() if every else frozenset(keys))


def _element_scope(
    key: str,
    version: EstimateVersionInput,
    scope: _Scope,
    obligations: Mapping[str, ObligationState],
    findings: list[Finding],
) -> tuple[ObligationState, ...] | None:
    """The related obligations of one element under the version pinned at t, or ``None`` with a
    ``CPC_RELATED_SCOPE_INVALID`` finding (D-91 (3); 04 table 15.4-C)."""
    own = tuple(version.target_obligation_keys) or (
        () if version.obligation_key is None else (version.obligation_key,)
    )
    unknown = sorted(item for item in own if item not in obligations)
    if unknown:
        findings.append(
            Finding(
                SCOPE_INVALID,
                "ERROR",
                key,
                {
                    "reason": "UNKNOWN_OBLIGATION",
                    "rule": "S10-R-26",
                    "source": "element",
                    "unknown_keys": ",".join(unknown),
                    "version_key": version.version_key,
                },
                STAGE,
                None,
            )
        )
        return None
    if scope.promised:
        promised = scope.keys or frozenset(obligations)
        if own and frozenset(own) != promised:
            findings.append(
                Finding(
                    SCOPE_INVALID,
                    "ERROR",
                    key,
                    {
                        "reason": "MISMATCH",
                        "rule": "S10-R-26",
                        "element_keys": ",".join(sorted(own)),
                        "promise_keys": ",".join(sorted(promised)),
                        "version_key": version.version_key,
                    },
                    STAGE,
                    None,
                )
            )
            return None
        related = promised
    else:
        related = frozenset(own) if own else frozenset(obligations)
    return tuple(obligations[item] for item in sorted(related))
