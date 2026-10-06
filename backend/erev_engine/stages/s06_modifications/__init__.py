"""Stage 06 modifications: the modification proposal and the boundary handlers.

ENGINE_SPEC §6.1; §6.2 S06-R-01 to S06-R-05 (``propose``); §6.3 S06-R-06 to S06-R-18 and §6.4
S06-R-19 to S06-R-27 (``apply``); §6.6 S06-INV-01 to S06-INV-04, findings
``MOD_QTY_ON_SATISFIED_POB``, ``MOD_REMAINING_NEGATIVE``, ``MOD_UNIT_HISTORY_AMBIGUOUS`` (D-90b),
``MOD_PROGRESS_UNDEFINED`` and ``VC_ALLOCATION_NEGATIVE``; POLICIES ALG-04 §2.5.2 to §2.5.6,
ALG-05 §2.6.2 to §2.6.4, POL-028,
POL-080, POL-081, POL-100 to POL-106, POL-242 to POL-244.

``propose`` returns the engine's treatment per obligation (E-23) before approval. It never changes
accounting (CV-16) and reads no trigger, so ``DRY_RUN`` and ``COMMAND`` give the same proposal
(S06-R-02; ENG-12). ``apply`` folds one boundary event of Table 0.3-A: ``CONTRACT_AMENDED`` with
the approved treatments it carries (S06-R-01), ``CONTRACT_TERMINATED`` (S06-R-21),
``MATERIAL_RIGHT_EXERCISED`` (S06-R-23, S06-R-24), ``LINE_ATTRIBUTES_CHANGED`` (S06-R-26) and
``REGROUPED`` (S06-R-27). ``attributes_at`` gives the dated account overrides and performing entity
of an obligation. A ``CONTRACT_AMENDED`` whose treatments are a legacy template applies §6.5
(S06-R-28 to S06-R-32): ``LEGACY_PROSPECTIVE``, ``LEGACY_RETROSPECTIVE`` and ``LEGACY_POB_VC``.
``validate_modification`` is the integrity validator of B3-BS2-05. Submodules
are private (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.bundle import ModificationInput, ProposalOut
from erev_engine.enums import ModificationTreatment, RecognitionMethod
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up
from erev_engine.stages.s01_canonicalize import contract_subject_key, payload_date, payload_text
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, emit_original_quantity
from erev_engine.stages.s05_allocation import points, provenance
from erev_engine.stages.s06_modifications import (
    attributes,
    boundary_state,
    change_orders,
    classify,
    exercise,
    inception_basis,
    legacy_templates,
    lineage,
    pool,
    price_test,
    regroup,
    satisfied,
    segments,
    subscriptions,
    terminations,
    weights,
)
from erev_engine.stages.s06_modifications.attributes import LineAttributes
from erev_engine.stages.s06_modifications.classify import (
    ModificationLine,
    ModificationView,
    ObligationClass,
)
from erev_engine.stages.s06_modifications.integrity import refuse, validate_modification
from erev_engine.stages.s06_modifications.subscriptions import SubscriptionCommand
from erev_engine.stages.state import (
    CONCESSION_EMBEDDED,
    AllocatedState,
    AllocationSegment,
    BookContext,
    ConcessionAddition,
    ConcessionQuota,
    EventView,
    Finding,
    LedgerPoint,
    ObligationState,
    ProgressTotals,
    Quota,
    SegmentCause,
    TpBuildUp,
    disaggregation_tags,
)
from erev_engine.trace import ABSENT_NO_RESOLUTION, TraceBuilder

__all__ = [
    "APPLY_POLICY_KEYS",
    "FORMULA_IDS",
    "POLICY_KEYS",
    "TEMPLATE_POLICY_KEYS",
    "TEMPLATE_TREATMENTS",
    "LineAttributes",
    "ModificationLine",
    "ModificationView",
    "ObligationClass",
    "PriceAt",
    "Proposal",
    "SubscriptionCommand",
    "apply",
    "attributes_at",
    "propose",
    "subscription_lines",
    "validate_modification",
]

# The stage 04 price of the group at a date and ENG-06 position (ENGINE_SPEC §4.2; S04-R-01),
# bound by the orchestrator because ``AllocatedState`` carries no price function (as stage 08).
PriceAt = Callable[[BookContext, AllocatedState, date, EventView | None], TpBuildUp]

# ENGINE_SPEC Table 0.10-A row 06 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "concession.allocation_basis",
    "material_right.exercise",
    "mod.catch_up_progress_basis",
    "mod.catch_up_scope",
    "mod.mixed_allocation",
    "mod.post_modification_vc_routing",
    "mod.price_change_on_satisfied_performance",
    "mod.reduction_ssp",
    "mod.route_selection",
    "mod.separate_contract_price_test",
    "mod.ssp_basis",
    "mod.unpriced_change_orders",
    "returns.returned_units_scope",
    "termination.refund_settlement",
)
# ENGINE_SPEC §6.6 formula ids, sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "alloc.original_total.v1",
    "alloc.original_total_amount.v1",
    "alloc.original_weight.v1",
    "mod.allocation_adjustment.v1",
    "mod.catch_up.v1",
    "mod.classify.v1",
    "mod.exercise.continuation.v1",
    "mod.exercise.modification.v1",
    "mod.legacy.mod_ssp.v1",
    "mod.legacy.pob_vc.v1",
    "mod.legacy.prospective.v1",
    "mod.legacy.retrospective.v1",
    "mod.pool.by_line.v1",
    "mod.pool.remaining_tp.v1",
    "mod.pool.total_tp.v1",
    "mod.price_test.v1",
    "mod.satisfied_performance.v1",
    "mod.stated_price.v1",
    "mod.termination.v1",
    "mod.weights.d18.v1",
    "mod.weights.inception_all.v1",
)
# POL-100 USER_SELECTED_TEMPLATE: E-24 template mode -> E-23 treatment (ALG-04 §2.5.7).
TEMPLATE_TREATMENTS: Final[Mapping[str, ModificationTreatment]] = MappingProxyType(
    {
        "prospective": ModificationTreatment.LEGACY_PROSPECTIVE,
        "retrospective": ModificationTreatment.LEGACY_RETROSPECTIVE,
        "pob_price_change": ModificationTreatment.LEGACY_POB_VC,
    }
)
_USER_SELECTED_TEMPLATE: Final = "USER_SELECTED_TEMPLATE"
_BY_CLASS: Final = MappingProxyType(
    {
        classify.DISTINCT: ModificationTreatment.PROSPECTIVE,
        classify.NONDISTINCT: ModificationTreatment.CUMULATIVE_CATCH_UP,
    }
)
_STAGE: Final = 6
_AMENDED: Final = "CONTRACT_AMENDED"
_TERMINATED: Final = "CONTRACT_TERMINATED"
_EXERCISED: Final = "MATERIAL_RIGHT_EXERCISED"
_EXPIRED: Final = "MATERIAL_RIGHT_EXPIRED"
_ATTRIBUTES: Final = "LINE_ATTRIBUTES_CHANGED"
_REGROUPED: Final = "REGROUPED"
_D18_DEFAULT: Final = "D18_DEFAULT"
_INCEPTION_ALL: Final = "INCEPTION_ALL"
_BY_LINE: Final = "ATTRIBUTE_BY_LINE"
# The options of the row 06 keys ``apply`` reads that the native application builds.
_BUILT_OPTIONS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "concession.allocation_basis": frozenset(  # POL-243
            {"INCEPTION_BASIS", "TARGETED_WHEN_32_40_ATTESTED"}
        ),
        exercise.POLICY_CODE: frozenset({exercise.CONTINUATION, exercise.MODIFICATION}),  # POL-028
        "mod.catch_up_scope": frozenset({"PARTIALLY_SATISFIED_NONDISTINCT_ONLY"}),  # POL-102
        "mod.mixed_allocation": frozenset({"REMAINING_TP", _BY_LINE}),  # POL-103
        "mod.price_change_on_satisfied_performance": frozenset(  # POL-104
            {satisfied.RECOGNISE, satisfied.POOL_WITH_REMAINING}
        ),
        "mod.reduction_ssp": frozenset({"CARRIED_UNIT_SSP"}),  # POL-081
        "mod.ssp_basis": frozenset({_D18_DEFAULT, _INCEPTION_ALL}),  # POL-080
        change_orders.POLICY_CODE: frozenset(  # POL-105
            {change_orders.ESTIMATE_WITH_CONSTRAINT}
        ),
        terminations.POLICY_CODE: frozenset(  # POL-242
            {terminations.REFUND_LIABILITY_UNTIL_CREDIT_MEMO}
        ),
    }
)
# The row 06 keys ``apply`` reads for a native modification, sorted.
APPLY_POLICY_KEYS: Final = tuple(sorted(_BUILT_OPTIONS))
# The row 06 keys a legacy template reads (S06-R-30: POL-107 ``LEGACY_BY_TEMPLATE``).
TEMPLATE_POLICY_KEYS: Final = (legacy_templates.POLICY_CODE,)
# E-23 template treatment -> the formula of its allocated_exact@ and allocated_amount@ nodes (§6.6).
_TEMPLATE_FORMULAS: Final[Mapping[ModificationTreatment, str]] = MappingProxyType(
    {
        ModificationTreatment.LEGACY_PROSPECTIVE: legacy_templates.PROSPECTIVE_FORMULA,
        ModificationTreatment.LEGACY_RETROSPECTIVE: legacy_templates.RETROSPECTIVE_FORMULA,
        ModificationTreatment.LEGACY_POB_VC: legacy_templates.POB_VC_FORMULA,
    }
)
_LEGACY: Final = frozenset(_TEMPLATE_FORMULAS)


def subscription_lines(
    ob: ObligationState, command: SubscriptionCommand
) -> tuple[Mapping[str, object], ...]:
    """The T-CON-06 lines of one subscription command (S06-R-19; ``subscriptions.lines``)."""
    return subscriptions.lines(ob, command)


def attributes_at(st: AllocatedState, ob: ObligationState, at: date) -> LineAttributes:
    """The account overrides and performing entity of ``ob`` in force at ``at`` (S06-R-26).

    Stages that date targets read the attributes here: ``LINE_ATTRIBUTES_CHANGED`` applies to
    targets dated on or after its effective date and adds no segment.
    """
    return attributes.attributes_at(st, ob, at)


@dataclass(frozen=True, slots=True)
class Proposal:
    """The engine proposal of one modification (S06-R-01; CV-16)."""

    contract_key: str
    modification_key: str
    summary: ModificationTreatment | None  # None when every obligation is class S
    treatments: Mapping[str, ModificationTreatment]  # obligation key -> E-23 literal
    classification: Mapping[str, str]  # obligation key -> "S" | "D" | "N"
    findings: tuple[Finding, ...]  # CV-43 order
    # D-98 140 AMENDMENT 15 (CTR-17b): the SSP book version the price test resolved for each
    # distinct added line (S06-R-04; ``SspValues.version_key`` = ``<book>@v<n>``), so the platform's
    # classification default names the engine's selection, never a re-resolution outside the engine.
    ssp_versions: Mapping[str, str] = MappingProxyType({})  # obligation key -> version key

    def out(self) -> ProposalOut:
        """The ``OutputBundle`` proposal of kind ``MODIFICATION_TREATMENT`` (§0.5; CV-16): detail
        ``modification_key``, ``class[<key>]`` and ``ssp_version[<key>]`` (D-98 140-A15)."""
        detail = {"modification_key": self.modification_key}
        detail.update({f"class[{key}]": label for key, label in self.classification.items()})
        detail.update({f"ssp_version[{key}]": vk for key, vk in self.ssp_versions.items()})
        return ProposalOut(
            kind="MODIFICATION_TREATMENT",
            subject_key=contract_subject_key(self.contract_key),
            summary=None if self.summary is None else self.summary.value,
            treatments=MappingProxyType({key: t.value for key, t in self.treatments.items()}),
            detail=MappingProxyType(dict(sorted(detail.items()))),
        )


def propose(
    ctx: BookContext,
    st: AllocatedState,
    modification: ModificationView,
    tb: TraceBuilder,
    *,
    identified: IdentifiedState,
) -> Proposal:
    """The proposed treatment of every obligation of the modified contract (ENGINE_SPEC §6.2).

    (1) POL-100 ``USER_SELECTED_TEMPLATE`` with a template mode gives the parity treatment of the
    mode to every obligation of the contract and every added line. (2) Otherwise, when every line
    adds distinct goods, no existing obligation changes and every added line passes the POL-101
    price test, the proposal is ``SEPARATE_CONTRACT`` for the added lines (S06-R-04). (3) Otherwise
    class D obligations take ``PROSPECTIVE``, class N ``CUMULATIVE_CATCH_UP`` and class S nothing;
    the summary is the single treatment or ``MIXED`` (S06-R-05). A modification of an E-25
    subscription kind must have the S06-R-19 line shapes (``ValueError`` otherwise).

    ``identified`` is the stage 02 state of the book, which carries the canonical bundle: stage 03
    ``build_lines`` prices the added lines at d from it, because ``AllocatedState`` holds no SSP
    books or templates. The proposal emits ``mod_class@<position>`` and
    ``mod_price_test@<position>`` nodes, where the position is the event key when the view carries
    the event, else the modification key under the contract (CV-50).
    """
    ctx.policies.require(("mod.route_selection", price_test.POLICY_CODE))
    mod = modification
    header = next(
        (view.header for view in st.contracts if view.header.external_id == mod.contract_key), None
    )
    if header is None:
        raise ValueError(f"{mod.modification_key}: {mod.contract_key} is not a member (CV-10)")
    entity = header.contracting_entity_code
    period = dates.period_of(ctx.entities[entity], mod.effective_date).period_key
    route = ctx.policies.value("mod.route_selection", entity=entity, period=period)
    existing = classify.contract_obligations(st, mod)
    subscriptions.check(mod, existing)
    if route == _USER_SELECTED_TEMPLATE and mod.template_mode is not None:
        treatment = TEMPLATE_TREATMENTS.get(mod.template_mode)
        if treatment is None:
            raise ValueError(f"{mod.modification_key}: unknown template mode {mod.template_mode!r}")
        keys = {ob.obligation_key for ob in existing}
        keys.update(line.obligation_key for line in mod.lines if line.action == classify.ADD)
        return Proposal(
            contract_key=mod.contract_key,
            modification_key=mod.modification_key,
            summary=treatment,
            treatments=MappingProxyType({key: treatment for key in sorted(keys)}),
            classification=MappingProxyType({}),
            findings=(),
        )
    findings: list[Finding] = []
    added = classify.added_lines(ctx, identified, mod, existing, findings)
    classes = classify.classify(ctx, st, mod, existing, added, findings, tb)
    ratio = price_test.tolerance(ctx, mod.contract_key)
    tests = [
        price_test.run(ctx, identified, mod, draft, ratio, tb)
        for item in added
        if item.distinct and item.target is None
        for draft in item.drafts
    ]
    ordered = tuple(sorted(findings, key=Finding.sort_key))
    classification = MappingProxyType({item.obligation_key: item.label for item in classes})
    ssp_versions = MappingProxyType(
        {
            test.draft.line.obligation_key: test.values.version_key
            for test in tests
            if test.values is not None
        }
    )
    if _separate_contract(mod, added, tests):
        separate = ModificationTreatment.SEPARATE_CONTRACT
        return Proposal(
            contract_key=mod.contract_key,
            modification_key=mod.modification_key,
            summary=separate,
            treatments=MappingProxyType({line.obligation_key: separate for line in mod.lines}),
            classification=classification,
            findings=ordered,
            ssp_versions=ssp_versions,
        )
    treatments = {
        item.obligation_key: _BY_CLASS[item.label]
        for item in classes
        if item.label != classify.SATISFIED
    }
    kinds = set(treatments.values())
    summary = None if not kinds else kinds.pop() if len(kinds) == 1 else ModificationTreatment.MIXED
    return Proposal(
        contract_key=mod.contract_key,
        modification_key=mod.modification_key,
        summary=summary,
        treatments=MappingProxyType(dict(sorted(treatments.items()))),
        classification=classification,
        findings=ordered,
        ssp_versions=ssp_versions,
    )


def _separate_contract(
    mod: ModificationView,
    added: tuple[classify.AddedLine, ...],
    tests: list[price_test.PriceTest],
) -> bool:
    """S06-R-04: every line adds distinct goods, nothing existing changes, every price passes."""
    if not mod.lines or mod.price_change_amount is not None:
        return False
    if any(line.action != classify.ADD for line in mod.lines):
        return False
    if any(not item.drafts or not item.distinct or item.target is not None for item in added):
        return False
    return bool(tests) and all(test.passed for test in tests)


# --- Boundary handlers (ENGINE_SPEC §6.3, §6.4; ENB-2 to ENB-4) -----------------------------------


def _invariant(message: str, ev: EventView, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=ev.contract_key,
        detail={"event_key": ev.event_key, **detail},
    )


def _modification_input(st: AllocatedState, ev: EventView) -> ModificationInput:
    """The approved T-CON-06 object the event applies (``modification_id``; 04 §16.3)."""
    key = payload_text(ev.payload, "modification_id")
    if key is None:
        raise ValueError(f"{ev.event_key}: {ev.event_type} needs modification_id (04 §16.3)")
    header = next(
        (view.header for view in st.contracts if view.header.external_id == ev.contract_key), None
    )
    if header is None:
        raise ValueError(f"{ev.event_key}: {ev.contract_key} is not a member (CV-10)")
    found = next((item for item in header.modifications if item.modification_key == key), None)
    if found is None:
        raise ValueError(f"{ev.event_key}: modification {key} is absent from the bundle (CV-45)")
    return found


def _treatments(raw: object, ev: EventView) -> Mapping[str, ModificationTreatment]:
    """The approved treatment per obligation key (S06-R-01, S06-R-03)."""
    if not isinstance(raw, Mapping):
        raise ValueError(f"{ev.event_key}: {ev.event_type} needs treatments (04 §16.3)")
    found: dict[str, ModificationTreatment] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"{ev.event_key}: treatments map obligation keys to E-23 literals")
        treatment = ModificationTreatment(value)
        if treatment == ModificationTreatment.SEPARATE_CONTRACT:
            raise ValueError(
                f"{ev.event_key}: a separate contract is booked, not applied (S06-R-03)"
            )
        if treatment == ModificationTreatment.MIXED:
            raise ValueError(f"{ev.event_key}: MIXED is a summary, not a treatment of {key}")
        found[key] = treatment
    return MappingProxyType(dict(sorted(found.items())))


def _options(
    ctx: BookContext, st: AllocatedState, contract_key: str, ev: EventView
) -> Mapping[str, str]:
    """The resolved row 06 options ``apply`` reads; an option not built fails closed.

    Pin ``P`` values (for example POL-242) resolve for the contracting entity and the period of d.
    """
    header = next(
        (view.header for view in st.contracts if view.header.external_id == contract_key), None
    )
    if header is None:
        raise ValueError(f"{ev.event_key}: {contract_key} is not a member (CV-10)")
    entity = header.contracting_entity_code
    period = dates.period_of(ctx.entities[entity], ev.effective_date).period_key
    found: dict[str, str] = {}
    for code, built in _BUILT_OPTIONS.items():
        value = ctx.policies.value(code, contract=contract_key, entity=entity, period=period)
        if not isinstance(value, str) or value not in built:
            raise _invariant(
                "the policy option is not built",
                ev,
                rule="S06-R-06",
                policy=code,
                option=str(value),
            )
        found[code] = value
    return MappingProxyType(found)


def _ssp_basis(raw: object, ev: EventView) -> Mapping[str, Mapping[str, object]]:
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, Mapping):
        raise ValueError(f"{ev.event_key}: ssp_basis maps obligation keys to objects (D-18)")
    found: dict[str, Mapping[str, object]] = {}
    for key, member in raw.items():
        if not isinstance(member, Mapping):
            raise ValueError(f"{ev.event_key}: ssp_basis member {key} is not an object (D-18)")
        found[str(key)] = member
    return MappingProxyType(found)


def _next_event(st: AllocatedState, ev: EventView) -> EventView | None:
    return next((item for item in st.events if item.order_key > ev.order_key), None)


def _line_date(lines: Sequence[ModificationLine], name: str) -> date | None:
    found: date | None = None
    for line in lines:
        value = payload_date(line.members, name)
        if value is not None:
            found = value
    return found


def _blocking(findings: Sequence[Finding]) -> bool:
    return any(finding.severity == "ERROR" for finding in findings)


def _with_findings(st: AllocatedState, findings: Sequence[Finding]) -> AllocatedState:
    ordered = tuple(sorted((*st.findings, *findings), key=Finding.sort_key))
    return dataclasses.replace(st, findings=ordered)


def _finding(
    code: str,
    mod: ModificationView,
    subject_key: str,
    obligation_key: str,
    rule: str,
    **detail: str,
) -> Finding:
    members = {
        "modification_key": mod.modification_key,
        "obligation_key": obligation_key,
        "rule": rule,
        **detail,
    }
    event_key = None if mod.event is None else mod.event.event_key
    return Finding(code, "ERROR", subject_key, members, _STAGE, event_key)


def _check_remaining(
    mod: ModificationView,
    ob: ObligationState,
    before: segments.Measured,
    lines: Sequence[ModificationLine],
    findings: list[Finding],
) -> None:
    """S06-R-08: RQ_p = Q_p − q_p + ΔQ_p, and the units left after removals, must not be below 0."""
    change = sum((line.quantity_delta for line in lines), Fraction(0))
    lowest = min(
        before.remaining_quantity + change, before.remaining_quantity - weights.removed(lines)
    )
    if lowest < 0:
        findings.append(
            _finding(
                "MOD_REMAINING_NEGATIVE",
                mod,
                ob.subject_key,
                ob.obligation_key,
                "S06-R-08",
                remaining_quantity=format_exact(lowest),
            )
        )


_MIXED_SIGNS: Final = "MIXED_SIGNS"
_RE_TERMED_ADDED_UNITS: Final = "RE_TERMED_ADDED_UNITS"


def _check_unit_history(
    mod: ModificationView,
    ob: ObligationState,
    before: segments.Measured,
    lines: Sequence[ModificationLine],
    findings: list[Finding],
) -> None:
    """S06-R-08 unit history (D-90b; D-90c): ``MOD_UNIT_HISTORY_AMBIGUOUS`` for a started
    eligible obligation whose unit history the S06-R-11 net reconstruction cannot represent.

    Eligible: not a VC line, not ``series``, the ``FIXED`` segment in force measures
    ``TIME_ELAPSED`` with a cause other than ``TERMINATION`` (``segments.eligible``), whatever the
    class D or N treatment. Started: d after s_p, the start of the term in force. Refused: (a) the
    lines of this modification on the obligation carry both a negative and a positive
    ``quantity_delta``, where no order exists; (b) a line adding units carries a ``start_date``
    other than that of the term in force. Modifications effective on the same date are applied in
    event order and each is a boundary of its own (rev 1.5; D-90c): a removal then an addition
    keeps the remaining booked units at their start and adds a layer at d, an addition then a
    removal reduces every layer pro rata (``segments.unit_layers``). A mixed event before the
    service start reconstructs exactly and passes.
    """
    seg = before.segment
    if not lines or not segments.eligible(ob, seg):
        return
    term_start, _ = segments.term_in_force(ob, seg)
    d = mod.effective_date
    if d <= term_start:
        return
    added = sum((line.quantity_delta for line in lines if line.quantity_delta > 0), Fraction(0))
    gone = weights.removed(lines)
    detail = {
        "added": format_exact(added),
        "removed": format_exact(gone),
        "term_start": term_start.isoformat(),
    }
    reason: str | None = None
    if added > 0 and gone > 0:
        reason = _MIXED_SIGNS
    elif added > 0:
        booked_start = seg.totals.start_date or ob.start_date
        for line in lines:
            if line.quantity_delta <= 0:
                continue
            start = payload_date(line.members, "start_date")
            if start is not None and start not in (booked_start, term_start):
                reason = _RE_TERMED_ADDED_UNITS
                detail["start_date"] = start.isoformat()
                break
    if reason is None:
        return
    findings.append(
        _finding(
            "MOD_UNIT_HISTORY_AMBIGUOUS",
            mod,
            ob.subject_key,
            ob.obligation_key,
            "S06-R-08",
            reason=reason,
            **detail,
        )
    )


def _totals(
    ob: ObligationState,
    before: segments.Measured,
    lines: Sequence[ModificationLine],
    *,
    nondistinct: bool,
) -> ProgressTotals:
    """Totals after the boundary: RQ_p for class D (S06-R-14), Q_p + ΔQ_p for class N (S06-R-15)."""
    change = sum((line.quantity_delta for line in lines), Fraction(0))
    seg = before.segment
    quantity = ob.quantity + change if nondistinct else before.remaining_quantity + change
    return ProgressTotals(
        quantity,
        seg.totals.eac_element_code,
        _line_date(lines, "start_date") or seg.totals.start_date,
        _line_date(lines, "end_date") or seg.totals.end_date,
    )


def _consideration(ctx: BookContext, lines: Sequence[ModificationLine]) -> int:
    return sum(
        segments.to_minor(
            ctx, line.consideration_delta, f"{line.obligation_key} consideration_delta"
        )
        for line in lines
    )


_REVENUE_ROLE: Final = "REVENUE"


def _added_overrides(
    identified: IdentifiedState, draft: PobDraft, weight: weights.Weight
) -> Mapping[str, str]:
    """The line's account overrides and, below them, the revenue account of the SSP entry the
    added line resolved, as stage 05 merges it at inception (REQ-SSP-014; L3-2-Q-24)."""
    overrides = dict(draft.account_overrides)
    resolution = weight.resolution
    if resolution is not None:
        for version in identified.canonical.ssp_books.versions.get(resolution.book_code, ()):
            if version.version_key != resolution.version_key:
                continue
            for entry in version.entries:
                if entry.entry_key == resolution.entry_key and entry.revenue_account_code:
                    overrides.setdefault(_REVENUE_ROLE, entry.revenue_account_code)
    return MappingProxyType(dict(sorted(overrides.items())))


def _added_obligation(
    identified: IdentifiedState,
    draft: PobDraft,
    seg: AllocationSegment,
    weight: weights.Weight,
    pre: tuple[str, ...],
    modification_key: str | None,
    price_after: TpBuildUp,
    total_ssp: Fraction,
    allocation_nodes: tuple[str, ...],
    allocation_links: tuple[str, str],
    snapshot_links: Mapping[str, str],
) -> ObligationState:
    """An obligation a boundary adds, with its creation-time columns (S06-R-14; §0.11).

    ``allocation_nodes``: the trace node(s) that produced the quota installed as the original
    allocation — the creation producer the original unit revenue rate cites (CV-47 (b); D-98
    candidate 117 F1). The caller emits the obligation's ``original_quantity`` node into the trace
    (``emit_original_quantity``), the stage 03 drafts having been built in a scratch builder."""
    product = identified.canonical.group.products.get(draft.product_code)
    cost = None if product is None else product.assurance_cost_per_unit
    return ObligationState(
        subject_key=draft.subject_key,
        contract_key=draft.contract_key,
        obligation_key=draft.obligation_key,
        obligation_kind=draft.obligation_kind,
        distinctness=draft.distinctness,
        satisfaction_pattern=draft.satisfaction_pattern,
        recognition_method=draft.recognition_method,
        ratable_convention=draft.ratable_convention,
        principal_agent=draft.principal_agent,
        licence_nature=draft.licence_nature,
        scope_flag=draft.scope_flag,
        start_date=draft.start_date,
        end_date=draft.end_date,
        recognition_start_date=None,
        contracting_entity=draft.contracting_entity,
        performing_entity=draft.performing_entity,
        quantity=draft.quantity,
        resolved_ssp=weight.value,
        revenue_category=draft.revenue_category,
        dimensions=disaggregation_tags(
            identified.canonical,
            contract_key=draft.contract_key,
            template_version_key=draft.template_version_key,
            product_code=draft.product_code,
            performing_entity=draft.performing_entity,
            satisfaction_pattern=str(draft.satisfaction_pattern),
            revenue_category=draft.revenue_category,
        ),
        account_overrides=_added_overrides(identified, draft, weight),
        segments=(seg,),
        opening=None,
        terminated_on=None,
        template_version_key=draft.template_version_key,
        product_code=draft.product_code,
        sku_number=draft.sku_number,
        stratification=draft.stratification,
        series_increment_unit=draft.series_increment_unit,
        over_time_criterion=draft.over_time_criterion,
        warranty_type=draft.warranty_type,
        material_right=None,
        ssp=weight.resolution,
        original_quantity=draft.original_quantity,
        original_stated_price=draft.original_stated_price,
        stated_price=draft.stated_price,
        original_allocation=Quota(seg.x_exact, seg.a_posted),
        original_allocation_nodes=allocation_nodes,
        original_allocation_links=allocation_links,  # CV-50 (D-98 121): the creation pair
        snapshot_producer_links=MappingProxyType(dict(snapshot_links)),  # CV-50 rev 1.29 (124)
        original_total_contract_price=price_after.total.exact,
        original_total_contract_ssp=total_ssp,
        is_vc_line=draft.is_vc_line,
        gross_to_net=None,
        lineage_pre_modification=pre,
        assurance_cost_per_unit=None if cost is None else Fraction(cost),
        last_modification_key=modification_key,
        # S08-R-04: the selected SSP of the resolution, else the boundary weight (L1-3-Q-29).
        inception_weight=(
            weight.value if weight.resolution is None else weight.resolution.selected
        ),
    )


@dataclass(frozen=True, slots=True)
class _Boundary:
    """One obligation that takes a segment at the boundary, with what measures its catch-up.

    ``kind``: ``D`` class D or added (S06-INV-02), ``N`` class N (updated EAC), ``S`` receiver of
    satisfied performance, ``T`` ended by a termination, ``R`` rollover extension, ``X`` option
    closed by an exercise, ``A`` re-allocated by a corrected SSP version pin, ``L`` re-based by a
    legacy template (S06-R-29).
    """

    subject_key: str
    before: segments.Measured | None  # None for an added obligation
    kind: str
    share_node: str | None
    base: int  # the posted amount the share adds to
    cause: SegmentCause
    satisfied_residue: Fraction = Fraction(0)  # posted − exact ΔC_sat share in a D base (S06-R-09)


@dataclass(frozen=True, slots=True)
class _Route:
    """What the native application of §6.3 applies at one boundary event."""

    mod: ModificationView
    treatments: Mapping[str, ModificationTreatment]
    basis: Mapping[str, Mapping[str, object]]
    ended: frozenset[str] = frozenset()  # obligation keys ended by a termination (S06-R-21)
    refund: int = 0  # refund_amount in minor units (S06-R-21)
    cause: SegmentCause = SegmentCause.MODIFICATION


_Handler = Callable[
    [BookContext, AllocatedState, EventView, TraceBuilder, IdentifiedState, PriceAt | None],
    AllocatedState,
]


def apply(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    *,
    identified: IdentifiedState,
    price_at: PriceAt | None,
) -> AllocatedState:
    """The state after one stage 06 boundary event (ENGINE_SPEC §6.3, §6.4).

    ``CONTRACT_AMENDED`` applies its approved treatments. ``CONTRACT_TERMINATED`` applies its
    approved modification with the ended obligations pooled at weight 0, which take ``TERMINATION``
    segments, plus a ``TERMINATION`` refund component (S06-R-21). ``MATERIAL_RIGHT_EXERCISED``
    closes the option and allocates M + C_add to the optioned goods under POL-028
    ``CONTINUATION``, or applies the exercise as a modification under ``MODIFICATION`` (S06-R-23,
    S06-R-24). ``LINE_ATTRIBUTES_CHANGED`` adds no segment unless it corrects the SSP version pin,
    which re-allocates the group from inception (S06-R-26). ``REGROUPED`` is no boundary before
    posting, else the approved modification (S06-R-27). ``MATERIAL_RIGHT_EXPIRED`` is not a
    boundary and returns the state unchanged (S06-R-25).

    The native application weighs the obligations with treatment ``PROSPECTIVE`` (class D) or
    ``CUMULATIVE_CATCH_UP`` (class N), and the obligations the lines add, under POL-080 (S06-R-06,
    S06-R-11), and pools them under POL-103 ``REMAINING_TP`` or ``ATTRIBUTE_BY_LINE`` (S06-R-12,
    S06-R-13). Class D takes a ``PROSPECTIVE`` segment from R_p with no catch-up (S06-R-14;
    S06-INV-02); class N takes an ``INCEPTION`` segment over the updated totals with a catch-up
    (S06-R-15, S06-R-17). Satisfied performance goes to the satisfied and ended obligations
    (S06-R-09, S06-R-10), and every other class S obligation keeps X and A (S06-INV-03). A renewal
    carrying unconsumed credits extends the redemption obligation without a pool (S09-R-22). An
    unpriced change order enters through ΔVC with unpriced lines (S06-R-20).

    Every obligation of the contract records the modification, and each pooled segment lists the
    obligations identified before it (S06-R-16). A share that makes an allocation negative raises
    ``VC_ALLOCATION_NEGATIVE`` (S06-R-22). An ``ERROR`` finding returns the state with the finding
    and no segment (CV-15). The price after the event must equal Σ a_posted over the group
    (S06-R-18; S06-INV-01), and it is appended to ``tp_history``.

    ``identified`` carries the canonical bundle (SSP books, templates, products), which prices the
    lines at d; ``price_at`` is the stage 04 price function, bound by the orchestrator. Options not
    built (``TOTAL_TP``, ``ALL_POBS_FULL_REALLOCATION``, goods added to a class N obligation by
    integration target, the parity route of a material-right exercise) fail closed.

    Before the handler runs, ``integrity.refuse`` raises ``ENGINE_INVARIANT_VIOLATED`` (rule
    S06-R-07) for an unknown contract, a modification already applied, or a T-CON-06 object with
    a refused integrity code (ENB-13; CV-45).
    """
    if ev.event_type == _EXPIRED:
        return st  # S06-R-25: stage 09 recognises the option's remaining allocation (JET-08)
    handler = _HANDLERS.get(ev.event_type)
    if handler is None:
        raise _invariant(
            "stage 06 does not apply this event", ev, rule="S06-R-01", event_type=ev.event_type
        )
    refuse(ctx, st, ev)
    ctx.policies.require(APPLY_POLICY_KEYS)
    return handler(ctx, st, ev, tb, identified, price_at)


def _amended(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
) -> AllocatedState:
    """``CONTRACT_AMENDED``: the approved modification under the payload treatments (§6.3), or a
    legacy template when the treatments are one (§6.5)."""
    mod = ModificationView.of(ev.contract_key, _modification_input(st, ev), event=ev)
    subscriptions.check(mod, classify.contract_obligations(st, mod))
    treatments = _treatments(ev.payload.get("treatments"), ev)
    if any(treatment in _LEGACY for treatment in treatments.values()):
        return _template(ctx, st, ev, tb, identified, price_at, mod, treatments)
    route = _Route(mod, treatments, _ssp_basis(ev.payload.get("ssp_basis"), ev))
    return _native(ctx, st, ev, tb, identified, price_at, route)


def _template_basis(ctx: BookContext, st: AllocatedState, contract_key: str, ev: EventView) -> None:
    """POL-107 must be ``LEGACY_BY_TEMPLATE``: the templates fix their progress basis (S06-R-30)."""
    header = next(
        (view.header for view in st.contracts if view.header.external_id == contract_key), None
    )
    if header is None:
        raise ValueError(f"{ev.event_key}: {contract_key} is not a member (CV-10)")
    entity = header.contracting_entity_code
    period = dates.period_of(ctx.entities[entity], ev.effective_date).period_key
    code = legacy_templates.POLICY_CODE
    value = ctx.policies.value(code, contract=contract_key, entity=entity, period=period)
    if value != legacy_templates.BY_TEMPLATE:
        raise _invariant(
            "the policy option is not built", ev, rule="S06-R-30", policy=code, option=str(value)
        )


def _template(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
    mod: ModificationView,
    treatments: Mapping[str, ModificationTreatment],
) -> AllocatedState:
    """A legacy template at one ``CONTRACT_AMENDED`` (ENGINE_SPEC §6.5; ALG-04 §2.5.7).

    Every obligation of the contract carries the one template treatment (S06-R-28), and POL-107
    is ``LEGACY_BY_TEMPLATE`` (S06-R-30). The retrospective template may add obligations, which
    take their creation-time values (S06-R-31). Every obligation takes the S06-R-29 segment and a
    ``catch_up@`` node, CU = C_after(d) − C_before(d) (S06-R-30). TP_c must round to the
    allocation basis after the event, which Σ a_posted equals (S06-R-18; S06-INV-01), and Σ (x′ −
    x) = Σ ModBilling exactly (S06-INV-04). An ``ERROR`` finding returns the state with the
    finding and no segment (CV-15).
    """
    kinds = sorted({treatment.value for treatment in treatments.values()})
    existing = classify.contract_obligations(st, mod)
    if len(kinds) != 1 or any(ob.obligation_key not in treatments for ob in existing):
        raise ValueError(
            f"{mod.modification_key}: one legacy template applies to every obligation (S06-R-28)"
        )
    treatment = ModificationTreatment(kinds[0])
    pob_vc = treatment == ModificationTreatment.LEGACY_POB_VC
    ctx.policies.require(TEMPLATE_POLICY_KEYS)
    _template_basis(ctx, st, mod.contract_key, ev)
    by_key = {ob.obligation_key: ob for ob in existing}
    findings: list[Finding] = []
    added = classify.added_lines(ctx, identified, mod, existing, findings)
    if added and pob_vc:
        raise ValueError(
            f"{mod.modification_key}: a POB-specific price change names existing obligations"
        )
    drafts = [draft for item in added for draft in item.drafts]
    known = set(by_key) | {item.line.obligation_key for item in added}
    known.update(draft.obligation_key for draft in drafts)
    unknown = sorted(set(treatments) - known)
    if unknown:
        raise ValueError(f"{mod.modification_key}: treatments name unknown obligation {unknown[0]}")
    if _blocking(findings):
        return _with_findings(st, findings)
    lines_on: dict[str, list[ModificationLine]] = {}
    for line in mod.lines:
        if line.action != classify.ADD:
            lines_on.setdefault(line.obligation_key, []).append(line)
    positions = [
        legacy_templates.position(st, ob, _measure(ctx, st, ob, ev), ev) for ob in existing
    ]
    ssp: dict[str, legacy_templates.ModSsp] = {}
    for ob in existing:
        if not pob_vc and ob.obligation_key in lines_on:  # a price change adds no SSP
            found = legacy_templates.mod_ssp(
                ctx, identified, ob, lines_on[ob.obligation_key], ev, findings
            )
            if found is not None:
                ssp[ob.subject_key] = found
    template_lines: dict[str, Sequence[ModificationLine]] = dict(lines_on)
    for draft in drafts:
        found = legacy_templates.added_mod_ssp(ctx, identified, draft, ev, findings)
        if found is not None:
            ssp[draft.subject_key] = found
        positions.append(legacy_templates.added(draft))
        template_lines[draft.obligation_key] = (
            ModificationLine(
                draft.obligation_key,
                classify.ADD,
                draft.product_code,
                draft.quantity,
                draft.stated_price,
                MappingProxyType({}),
            ),
        )
    if _blocking(findings):
        return _with_findings(st, findings)
    if treatment == ModificationTreatment.LEGACY_PROSPECTIVE:
        outcomes = legacy_templates.prospective(mod, positions, template_lines, ssp, findings)
    elif pob_vc:
        outcomes = legacy_templates.pob_vc(mod, positions, lines_on, findings)
    else:
        outcomes = legacy_templates.retrospective(mod, positions, template_lines, ssp, findings)
    if outcomes is None:
        return _with_findings(st, findings)
    if price_at is None:
        raise _invariant("the transaction price function is not bound", ev, rule="S06-R-18")
    price_after = price_at(ctx, st, ev.effective_date, _next_event(st, ev))
    mu = segments.minor_unit(ctx)
    total = sum((item.x_exact for item in outcomes), Fraction(0))
    tp_minor = round_half_up(total, mu)
    if tp_minor != price_after.allocation_basis.posted:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the template price differs from the allocation basis after the event",
            subject_key=st.group_code,
            detail={
                "allocation_basis": str(price_after.allocation_basis.posted),
                "event_key": ev.event_key,
                "invariant": "S06-INV-01",
                "template_price": format_exact(total),
            },
        )
    posted = legacy_templates.amounts(outcomes, tp_minor)
    formula_id = _TEMPLATE_FORMULAS[treatment]
    ssp_nodes = {
        key: legacy_templates.emit_mod_ssp(tb, ev, item, ctx.txn_currency)
        for key, item in sorted(ssp.items())
    }
    exact_nodes = legacy_templates.emit_exact(
        tb, ev, formula_id, outcomes, ssp_nodes, ctx.txn_currency
    )
    amount_nodes = legacy_templates.emit_amounts(
        ctx, tb, ev, formula_id, outcomes, posted, tp_minor, exact_nodes
    )
    drafts_by_subject = {draft.subject_key: draft for draft in drafts}
    remaining_ssp = sum((item.remaining_ssp for item in outcomes), Fraction(0))
    changed: dict[str, ObligationState] = {}
    created: list[ObligationState] = []
    boundaries: list[_Boundary] = []
    cause = SegmentCause.MODIFICATION
    for item in outcomes:
        key, before = item.position.subject_key, item.position.before
        if before is None:
            draft = drafts_by_subject[key]
            totals = ProgressTotals(item.remaining_quantity, None, draft.start_date, draft.end_date)
            seg = legacy_templates.segment(
                ctx, ev, item, posted[key], point=LedgerPoint.zero(), source=None, totals=totals
            )
            found = ssp[key]
            resolution = (
                None
                if found.resolution is None
                else dataclasses.replace(found.resolution, selected=item.mod_ssp)
            )
            weight = weights.Weight(
                key,
                "D",
                item.mod_ssp,
                (item.mod_ssp,),
                found.sources,
                resolution,
                MappingProxyType({}),
            )
            emit_original_quantity(tb, draft, ev.event_key)  # CV-47 (b): real quantity provenance
            links = provenance.emit_original_allocation(  # CV-50 (D-98 121): the creation pair
                ctx,
                tb,
                ev.event_key,
                key,
                Quota(seg.x_exact, seg.a_posted),
                exact_inputs=[amount_nodes[key]],
                amount_inputs=[amount_nodes[key]],
                rule="S06-R-29",
            )
            # CV-50 rev 1.29: a LEGACY-VC line has no SSP resolution BY CONSTRUCTION
            # (``added_mod_ssp``'s VC branch returns the zero band without a lookup) — the named
            # absence, admitted from this constructor state only; a positive-Q non-VC line always
            # carries a resolution here (a failed lookup is refused upstream); nothing fabricated.
            selected: str | None = ABSENT_NO_RESOLUTION if draft.is_vc_line else None
            if weight.resolution is not None:  # the created line's SSP producer (CV-50 rev 1.29)
                selected = points.emit(
                    ctx,
                    tb,
                    key,
                    weight.resolution,
                    draft.stated_price,
                    found.sources,
                    event_key=ev.event_key,
                )
            total_node, weight_node = legacy_templates.emit_total_and_weight(
                tb, ev, formula_id, outcomes, ssp_nodes, ctx.txn_currency, key
            )
            snapshot = provenance.emit_snapshot_columns(  # CV-50 rev 1.29 (D-98 124)
                ctx,
                tb,
                ev.event_key,
                key,
                selected_node=selected,
                selected=None if weight.resolution is None else weight.value,  # clamped mod SSP
                quantity=draft.original_quantity,
                stated_price=draft.original_stated_price,  # echoed after boundary_state.emit
                price=price_after.total,
                rule="S06-R-29",
                total_node=total_node,
                allocation_weight_node=weight_node,
            )
            created.append(
                _added_obligation(
                    identified,
                    draft,
                    seg,
                    weight,
                    (),
                    mod.modification_key,
                    price_after,
                    remaining_ssp,
                    (amount_nodes[key],),  # the allocated_amount@<event> producer (S06-R-29)
                    links,
                    snapshot,
                )
            )
            boundaries.append(_Boundary(key, None, "L", amount_nodes[key], 0, cause))
            continue
        ob = by_key[item.position.obligation_key]
        lines = lines_on.get(ob.obligation_key, ())
        source = before.segment
        totals = ProgressTotals(
            item.remaining_quantity,
            source.totals.eac_element_code,
            _line_date(lines, "start_date") or source.totals.start_date,
            _line_date(lines, "end_date") or source.totals.end_date,
        )
        seg = legacy_templates.segment(
            ctx, ev, item, posted[key], point=before.point, source=source, totals=totals
        )
        changed[key] = dataclasses.replace(
            ob,
            quantity=ob.quantity + item.quantity_change,
            stated_price=ob.stated_price + item.consideration_change,
            end_date=_line_date(lines, "end_date") or ob.end_date,
            segments=(*ob.segments, seg),
            last_modification_key=mod.modification_key,
        )
        boundaries.append(_Boundary(key, before, "L", amount_nodes[key], 0, cause))
    obligations = lineage.record(st, mod.contract_key, mod.modification_key, changed, created)
    result = dataclasses.replace(
        _with_findings(st, findings),
        obligations=obligations,
        tp_history=(*st.tp_history, price_after),
    )
    _catch_ups(ctx, tb, result, ev, boundaries)
    boundary_state.emit(ctx, tb, st, result, ev)
    provenance.emit_stated_price_echoes(
        ctx, tb, ev, created
    )  # CV-50 rev 1.29 (D-98 124)  # D-97 (8) T1F-Q-3 (c)
    _assert_allocation_sum(result, ev, price_after)
    consideration = sum((line.consideration_delta for line in mod.lines), Fraction(0))
    legacy_templates.assert_moved(ev, outcomes, consideration)
    return result


def _terminated(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
) -> AllocatedState:
    """``CONTRACT_TERMINATED``: the approved scope reduction with the ended obligations (S06-R-21).

    The treatments of the remaining obligations are the payload ``treatments`` when present, else
    the modification's ``chosen_treatments``; an ended obligation takes no treatment.
    """
    found = _modification_input(st, ev)
    mod = ModificationView.of(ev.contract_key, found, event=ev)
    existing = classify.contract_obligations(st, mod)
    progress = {ob.obligation_key: _measure(ctx, st, ob, ev).progress for ob in existing}
    ended = terminations.ended(ev, existing, progress)
    # D-91 gaps (vi), route (b): while NOT_A_CONTRACT the deposit ledger refunds ``refund_amount``
    # out of the deposit liability (JET-01b refund, S02-R-07 (b)); that portion is settled and
    # creates no TERMINATION refund component, so the GL carries one refund, not two.
    refund = max(terminations.refund(ctx, ev) - _deposit_refund(ctx, identified, ev), 0)
    terminations.check_lines(ctx, mod, ended, refund)
    raw = ev.payload.get("treatments", found.chosen_treatments)
    chosen = _treatments(raw, ev)
    treatments = MappingProxyType({key: t for key, t in chosen.items() if key not in ended})
    basis = _ssp_basis(ev.payload.get("ssp_basis", found.ssp_basis), ev)
    route = _Route(mod, treatments, basis, ended=ended, refund=refund)
    return _native(ctx, st, ev, tb, identified, price_at, route)


def _deposit_refund(ctx: BookContext, identified: IdentifiedState, ev: EventView) -> int:
    """The deposit refunded by stage 02 at ``ev`` (S02-R-08 ``deposit_refunded_cum`` movement), in
    minor units; 0 when the contract kept no deposit ledger point at the event."""
    points = identified.deposits.get(ev.contract_key, ())
    at = next((point for point in points if point.order_key == ev.order_key), None)
    if at is None:
        return 0
    before = identified.deposit_at(ev.contract_key, before=ev)
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    return round_half_up(at.refunded_cum - before.refunded_cum, minor_unit)


def _event_finding(
    code: str, ev: EventView, subject_key: str, obligation_key: str, rule: str, **detail: str
) -> Finding:
    members = {"obligation_key": obligation_key, "rule": rule, **detail}
    return Finding(code, "ERROR", subject_key, members, _STAGE, ev.event_key)


def _exercise_policy(ctx: BookContext, st: AllocatedState, contract_key: str, ev: EventView) -> str:
    """POL-028, the option an exercise routes on; an option not built fails closed (S06-R-06).

    S06-R-23 reads no modification option, so a parity value such as POL-102
    ``ALL_POBS_FULL_REALLOCATION`` does not stop a continuation. The ``MODIFICATION`` route still
    resolves every option through ``_native`` (L5-3-Q-25).
    """
    header = next(
        (view.header for view in st.contracts if view.header.external_id == contract_key), None
    )
    if header is None:
        raise ValueError(f"{ev.event_key}: {contract_key} is not a member (CV-10)")
    entity = header.contracting_entity_code
    period = dates.period_of(ctx.entities[entity], ev.effective_date).period_key
    code = exercise.POLICY_CODE
    value = ctx.policies.value(code, contract=contract_key, entity=entity, period=period)
    if not isinstance(value, str) or value not in _BUILT_OPTIONS[code]:
        raise _invariant(
            "the policy option is not built", ev, rule="S06-R-06", policy=code, option=str(value)
        )
    return value


def _exercised(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
) -> AllocatedState:
    """``MATERIAL_RIGHT_EXERCISED`` under POL-028 (S06-R-23, S06-R-24).

    An option recognised by redemption pattern only records the redemption quantity, which the
    stage 01 ledger carries for stage 09. Under ``MODIFICATION`` the engine's classes are the
    treatments. The parity route selection (``USER_SELECTED_TEMPLATE``) is not built for the
    exercise event and fails closed: the parity import books the exercise as a ``CONTRACT_AMENDED``
    with ``LEGACY_PROSPECTIVE`` treatments (S01-R-09), which ``_template`` applies (L2-3-Q-45).
    """
    option = exercise.option(st, ev)
    if option.recognition_method == RecognitionMethod.REDEMPTION_PATTERN:
        return st
    rows = exercise.new_lines(st, ev)
    add = exercise.additional(ctx, ev)
    before = _measure(ctx, st, option, ev)
    if _exercise_policy(ctx, st, option.contract_key, ev) == exercise.CONTINUATION:
        return _continuation(ctx, st, ev, tb, identified, price_at, option, before, rows, add)
    entity = option.contracting_entity
    period = dates.period_of(ctx.entities[entity], ev.effective_date).period_key
    selection = ctx.policies.value(
        "mod.route_selection", contract=option.contract_key, entity=entity, period=period
    )
    if selection == _USER_SELECTED_TEMPLATE:
        raise _invariant(
            "the parity route of a material-right exercise is not built",
            ev,
            rule="S06-R-24",
            treatment=ModificationTreatment.LEGACY_PROSPECTIVE.value,
        )
    mod = exercise.modification(ctx, ev, option, before, rows, add)
    findings: list[Finding] = []
    treatments = exercise.treatments(ctx, st, mod, identified, findings)
    if _blocking(findings):
        return _with_findings(st, findings)
    route = _Route(
        mod, treatments, MappingProxyType({}), cause=SegmentCause.MATERIAL_RIGHT_EXERCISE
    )

    def record() -> object:
        return exercise.emit_modification(ctx, tb, ev, option, before, mod, add)

    return _native(ctx, st, ev, tb, identified, price_at, route, on_applied=record)


def _continuation(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
    option: ObligationState,
    before: segments.Measured,
    rows: Sequence[Mapping[str, object]],
    add: int,
) -> AllocatedState:
    """POL-028 ``CONTINUATION``: the option closes and M + C_add goes to the optioned goods.

    The option's segment gives f = 1 only for a units measure, so another measure fails closed.
    The price after the event adds C_add (S06-R-18; S06-INV-01), and Σ (x′ − x) = C_add exactly
    (S06-INV-04).
    """
    measure = before.segment.progress_measure
    if measure not in segments.UNIT_MEASURES:
        raise _invariant(
            "an option measured other than by units is not closed at exercise",
            ev,
            rule="S06-R-23",
            progress_measure=measure,
        )
    mu = segments.minor_unit(ctx)
    findings: list[Finding] = []
    drafts = exercise.goods(ctx, identified, ev, rows, findings)
    weighted: list[weights.Weight] = []
    for draft in drafts:
        found = weights.added(ctx, identified, draft, ev, None, findings, tb=tb)
        if found is not None:
            weighted.append(found)
    if _blocking(findings):
        return _with_findings(st, findings)
    if price_at is None:
        raise _invariant("the transaction price function is not bound", ev, rule="S06-R-18")
    quotas = exercise.quotas(before, add, [(item.subject_key, item.value) for item in weighted], mu)
    negatives = [
        _event_finding(
            "VC_ALLOCATION_NEGATIVE",
            ev,
            draft.subject_key,
            draft.obligation_key,
            "S06-R-22",
            allocation=format_exact(Fraction(quotas[draft.subject_key][0], 10**mu)),
        )
        for draft in drafts
        if quotas[draft.subject_key][0] < 0 or quotas[draft.subject_key][1] < 0
    ]
    if negatives:
        return _with_findings(st, [*findings, *negatives])
    price_after = price_at(ctx, st, ev.effective_date, _next_event(st, ev))
    weight_nodes = [
        (
            item.subject_key,
            weights.emit(tb, ev, item, basis=exercise.CONTINUATION, formula_id=weights.D18_FORMULA),
        )
        for item in weighted
    ]
    exercise.emit_option(ctx, tb, ev, option.subject_key, before)
    goods_nodes = exercise.emit_goods(ctx, tb, ev, before, add, weight_nodes, quotas)
    total_weight = sum((item.value for item in weighted), Fraction(0))
    cause = SegmentCause.MATERIAL_RIGHT_EXERCISE
    boundaries = [_Boundary(option.subject_key, before, "X", None, before.posted, cause)]
    created: list[ObligationState] = []
    for draft, weight in zip(drafts, weighted, strict=True):
        posted, exact = quotas[draft.subject_key]
        seg = segments.prospective(
            ctx,
            ev,
            before=None,
            x_exact=exact,
            a_posted=posted,
            totals=ProgressTotals(draft.quantity, None, draft.start_date, draft.end_date),
            progress_measure=draft.recognition_method.value,
            weight=weight.value,
            billing_plan=draft.stated_price,
            boundary_no=0,
            cause=cause,
        )
        emit_original_quantity(tb, draft, ev.event_key)  # CV-47 (b): real quantity provenance
        links = provenance.emit_original_allocation(  # CV-50 (D-98 121): the creation pair
            ctx,
            tb,
            ev.event_key,
            draft.subject_key,
            Quota(exact, posted),
            exact_inputs=[goods_nodes[draft.subject_key]],
            amount_inputs=[goods_nodes[draft.subject_key]],
            rule="S06-R-23",
        )
        snapshot = provenance.emit_snapshot_columns(  # CV-50 rev 1.29 (D-98 124)
            ctx,
            tb,
            ev.event_key,
            draft.subject_key,
            selected_node=f"original_ssp_selected@{ev.event_key}:{draft.subject_key}:-",
            selected=weight.value,  # the raw SSP of the optioned good at x
            quantity=draft.original_quantity,
            stated_price=draft.original_stated_price,  # echoed after boundary_state.emit
            price=price_after.total,
            rule="S06-R-23",
            total_inputs=[node for _, node in weight_nodes],
            total_value=total_weight,
            weight_input=dict(weight_nodes)[draft.subject_key],
            weight_value=weight.value,
        )
        created.append(
            _added_obligation(
                identified,
                draft,
                seg,
                weight,
                (),
                None,
                price_after,
                total_weight,
                (goods_nodes[draft.subject_key],),  # the allocated_amount@<event> producer
                links,
                snapshot,
            )
        )
        boundaries.append(
            _Boundary(draft.subject_key, None, "D", goods_nodes[draft.subject_key], 0, cause)
        )
    known = {ob.subject_key for ob in st.obligations}
    if any(ob.subject_key in known for ob in created):
        raise ValueError(f"{ev.event_key}: an optioned good names an existing obligation (CV-45)")
    closed = dataclasses.replace(option, segments=(*option.segments, exercise.closed(ev, before)))
    kept = (closed if ob.subject_key == option.subject_key else ob for ob in st.obligations)
    obligations = tuple(sorted((*kept, *created), key=lambda ob: ob.subject_key))
    result = dataclasses.replace(
        _with_findings(st, findings),
        obligations=obligations,
        tp_history=(*st.tp_history, price_after),
    )
    _catch_ups(ctx, tb, result, ev, boundaries)
    boundary_state.emit(ctx, tb, st, result, ev)
    provenance.emit_stated_price_echoes(
        ctx, tb, ev, created
    )  # CV-50 rev 1.29 (D-98 124)  # D-97 (8) T1F-Q-3 (c)
    _assert_allocation_sum(result, ev, price_after)
    moved = sum((ob.segments[-1].x_exact for ob in created), Fraction(0))
    moved += before.exact - before.segment.x_exact
    if moved != Fraction(add, 10**mu):
        raise _invariant(
            "the exact allocations moved by the exercise differ from its consideration",
            ev,
            invariant="S06-INV-04",
            moved=format_exact(moved),
            expected=format_exact(Fraction(add, 10**mu)),
        )
    return result


def _attributes_changed(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
) -> AllocatedState:
    """``LINE_ATTRIBUTES_CHANGED``: dated attributes, or a corrected SSP version pin (S06-R-26)."""
    found = attributes.change(ev)
    named = any(
        ob.contract_key == ev.contract_key and ob.obligation_key == found.obligation_key
        for ob in st.obligations
    )
    if not named:
        raise ValueError(f"{ev.event_key}: {found.obligation_key} is not an obligation (CV-45)")
    if found.performing_entity is not None and found.performing_entity not in ctx.entities:
        raise ValueError(
            f"{ev.event_key}: entity {found.performing_entity} has no calendar (CV-12)"
        )
    if not found.repins_ssp:
        return st
    findings: list[Finding] = []
    reallocation = attributes.reallocate(ctx, st, ev, tb, identified, found, findings)
    if reallocation is None:
        return _with_findings(st, findings)
    obligations = tuple(reallocation.obligations.get(ob.subject_key, ob) for ob in st.obligations)
    result = dataclasses.replace(_with_findings(st, findings), obligations=obligations)
    boundaries = [
        _Boundary(
            key,
            reallocation.befores[key],
            "A",
            reallocation.share_nodes[key],
            0,
            SegmentCause.MODIFICATION,
        )
        for key in sorted(reallocation.obligations)
    ]
    _catch_ups(ctx, tb, result, ev, boundaries)
    boundary_state.emit(ctx, tb, st, result, ev)  # D-97 (8) T1F-Q-3 (c)
    _assert_allocation_sum(result, ev, st.tp_history[-1])
    return result


def _regrouped(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
) -> AllocatedState:
    """``REGROUPED``: no boundary before posting, else the approved modification (S06-R-27)."""
    if regroup.before_posting(st, ev):
        return st
    found = _modification_input(st, ev)
    mod = ModificationView.of(ev.contract_key, found, event=ev)
    route = _Route(mod, _treatments(found.chosen_treatments, ev), _ssp_basis(found.ssp_basis, ev))
    return _native(ctx, st, ev, tb, identified, price_at, route)


def _native(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
    price_at: PriceAt | None,
    route: _Route,
    on_applied: Callable[[], object] | None = None,
) -> AllocatedState:
    """The native application of §6.3 at one boundary event.

    ``on_applied`` runs once no finding blocks, before the first node of the event is emitted.
    """
    mod, treatments, ended = route.mod, route.treatments, route.ended
    legacy = sorted(treatment.value for treatment in treatments.values() if treatment in _LEGACY)
    if legacy:
        raise _invariant(
            "the legacy templates are not built", ev, rule="S06-R-28", treatment=legacy[0]
        )
    options = _options(ctx, st, mod.contract_key, ev)
    mu = segments.minor_unit(ctx)
    existing = classify.contract_obligations(st, mod)
    by_key = {ob.obligation_key: ob for ob in existing}
    findings: list[Finding] = []
    added = classify.added_lines(ctx, identified, mod, existing, findings)
    drafts: list[PobDraft] = []
    for item in added:
        if item.target is not None:
            raise _invariant(
                "goods added to a class N obligation by integration target are not built",
                ev,
                rule="S06-R-05",
                obligation_key=item.line.obligation_key,
            )
        drafts.extend(item.drafts)
    known = set(by_key) | {draft.obligation_key for draft in drafts}
    known.update(item.line.obligation_key for item in added)
    unknown = sorted(set(treatments) - known)
    if unknown:
        raise ValueError(f"{mod.modification_key}: treatments name unknown obligation {unknown[0]}")
    orders = change_orders.elements(st, mod)
    change_orders.check(mod, orders)
    extensions = subscriptions.rollover_extensions(mod, existing)
    pooled = sorted(
        {*(key for key in treatments if key in by_key and key not in extensions), *ended}
    )
    nondistinct = {
        key
        for key in pooled
        if key not in ended and treatments.get(key) == ModificationTreatment.CUMULATIVE_CATCH_UP
    }
    lines_on: dict[str, list[ModificationLine]] = {}
    for line in mod.lines:
        if line.action != classify.ADD and line.obligation_key not in extensions:
            lines_on.setdefault(line.obligation_key, []).append(line)
    befores = {key: _measure(ctx, st, by_key[key], ev) for key in sorted({*pooled, *lines_on})}
    named_satisfied: list[str] = []
    for key in sorted(set(lines_on) - set(pooled)):
        if befores[key].progress != 1:
            raise ValueError(f"{mod.modification_key}: a line names {key} without a treatment")
        if any(line.quantity_delta != 0 for line in lines_on[key]):
            ob = by_key[key]
            findings.append(
                _finding(
                    "MOD_QTY_ON_SATISFIED_POB", mod, ob.subject_key, ob.obligation_key, "S06-R-05"
                )
            )
        else:
            named_satisfied.append(key)
    for key in pooled:
        _check_remaining(mod, by_key[key], befores[key], lines_on.get(key, ()), findings)
        _check_unit_history(mod, by_key[key], befores[key], lines_on.get(key, ()), findings)
    if _blocking(findings):
        return _with_findings(st, findings)

    basis = route.basis
    inception_all = options["mod.ssp_basis"] == _INCEPTION_ALL
    weighted: dict[str, weights.Weight] = {}
    for key in pooled:
        ob, before, lines = by_key[key], befores[key], lines_on.get(key, ())
        if key in ended:
            weighted[ob.subject_key] = terminations.weight(ob, inception_all=inception_all)
            continue
        weigh = (
            weights.nondistinct
            if key in nondistinct
            else inception_basis.existing
            if inception_all
            else weights.existing
        )
        found = weigh(ctx, identified, ob, before, lines, ev, basis.get(key), findings)
        if found is not None:
            weighted[ob.subject_key] = found
    for draft in drafts:
        found = weights.added(
            ctx, identified, draft, ev, basis.get(draft.obligation_key), findings, tb=tb
        )
        if found is not None:
            weighted[draft.subject_key] = inception_basis.added(found) if inception_all else found
    totals = {
        key: _totals(
            by_key[key], befores[key], lines_on.get(key, ()), nondistinct=key in nondistinct
        )
        for key in pooled
        if key not in ended
    }
    for key in sorted(nondistinct):
        probe = dataclasses.replace(befores[key].segment, basis="INCEPTION", totals=totals[key])
        if befores[key].exact != 0 and segments.progress_undefined(st, by_key[key], probe, ev):
            ob = by_key[key]
            findings.append(
                _finding(
                    "MOD_PROGRESS_UNDEFINED", mod, ob.subject_key, ob.obligation_key, "S06-R-17"
                )
            )
    if _blocking(findings):
        return _with_findings(st, findings)

    if price_at is None:
        raise _invariant("the transaction price function is not bound", ev, rule="S06-R-18")
    d = ev.effective_date
    price_before = price_at(ctx, st, d, ev)
    price_after = price_at(ctx, st, d, _next_event(st, ev))
    consideration = _consideration(ctx, mod.lines)
    vc_delta = (
        price_after.allocation_basis.posted - price_before.allocation_basis.posted - consideration
    )
    recognise = options[satisfied.POLICY_CODE] == satisfied.RECOGNISE
    satisfied_total = 0
    if recognise:
        if mod.price_change_amount is not None:
            satisfied_total = segments.to_minor(ctx, mod.price_change_amount, "price_change_amount")
        else:
            satisfied_total = sum(_consideration(ctx, lines_on[key]) for key in named_satisfied)
    by_line = options["mod.mixed_allocation"] == _BY_LINE
    order = sorted(weighted)
    total_weight = sum((weighted[key].value for key in order), Fraction(0))
    members = tuple(
        pool.Member(by_key[key].subject_key, befores[key].segment.a_posted, befores[key].posted)
        for key in pooled
    )
    the_pool = pool.Pool(mod.contract_key, members, consideration, satisfied_total, vc_delta)
    unabsorbed = the_pool.posted if by_line else 0
    line_members: list[pool.LineMember] = []
    if by_line:
        if vc_delta != 0:
            raise _invariant("includable VC over pools by line", ev, rule="S06-R-12")
        line_members = [
            pool.LineMember(
                by_key[key].subject_key,
                befores[key].segment.a_posted,
                befores[key].posted,
                _consideration(ctx, lines_on.get(key, ())),
            )
            for key in pooled
        ]
        line_members.extend(
            pool.LineMember(
                draft.subject_key, 0, 0, segments.to_minor(ctx, draft.stated_price, "ΔC")
            )
            for draft in drafts
        )
        unabsorbed -= sum(item.posted for item in line_members)
    elif total_weight == 0:
        unabsorbed = the_pool.posted
    if unabsorbed != 0:
        if not recognise:
            raise _invariant(
                "a pool without weights needs satisfied performance", ev, rule="S06-R-12"
            )
        satisfied_total += unabsorbed  # S06-R-12; DEV-054: no obligation absorbs the pool
        the_pool = dataclasses.replace(the_pool, satisfied=satisfied_total)
    receivers: list[ObligationState] = []
    targeted: str | None = None
    if satisfied_total != 0:
        for ob in existing:
            if ob.obligation_key in pooled:
                continue
            if ob.obligation_key not in befores:
                befores[ob.obligation_key] = _measure(ctx, st, ob, ev)
            if befores[ob.obligation_key].progress == 1:
                receivers.append(ob)
        receivers.extend(by_key[key] for key in sorted(ended))  # S06-R-21: nonrefundable remainder
        receivers.extend(
            _delivered_portions(mod, pooled, {*ended, *nondistinct}, lines_on, befores, by_key)
        )
        receivers.sort(key=lambda ob: ob.subject_key)
        targeted = satisfied.target(ctx, mod, named_satisfied)
        if not receivers:
            raise _invariant(
                "satisfied performance has no satisfied obligation to recognise it",
                ev,
                rule="S06-R-09",
            )

    previews = (
        {item.subject_key: (item.posted, Fraction(item.posted, 10**mu)) for item in line_members}
        if by_line
        else pool.preview(the_pool, [(key, weighted[key].value) for key in order], mu)
    )
    received = (
        satisfied.preview(satisfied_total, receivers, targeted, mu) if satisfied_total != 0 else {}
    )
    negatives = _negative_allocations(
        mod,
        mu,
        [by_key[key] for key in pooled],
        befores,
        ended,
        drafts,
        receivers,
        previews,
        received,
    )
    if negatives:
        return _with_findings(st, [*findings, *negatives])
    if on_applied is not None:
        on_applied()

    formula_id = inception_basis.INCEPTION_ALL_FORMULA if inception_all else weights.D18_FORMULA
    for key in order:
        weights.emit(tb, ev, weighted[key], basis=options["mod.ssp_basis"], formula_id=formula_id)
    if by_line:
        shares = pool.attribute(ctx, tb, ev, mod.contract_key, line_members, mu)
    else:
        extra = change_orders.params(orders)
        pool_node = pool.emit(ctx, tb, ev, the_pool, mu, extra)
        shares = pool.apportion(
            ctx, tb, ev, the_pool, pool_node, [(key, weighted[key].value) for key in order], mu
        )
    shared = (
        satisfied.apportion(ctx, tb, ev, mod, satisfied_total, receivers, targeted, mu)
        if satisfied_total != 0
        else {}
    )

    pre = lineage.pre_modification(existing)
    changed: dict[str, ObligationState] = {}
    boundaries: list[_Boundary] = []
    for key in pooled:
        ob, before, weight = by_key[key], befores[key], weighted[by_key[key].subject_key]
        share = shares[ob.subject_key]
        lines = lines_on.get(key, ())
        quantity_change = sum((line.quantity_delta for line in lines), Fraction(0))
        consideration_change = sum((line.consideration_delta for line in lines), Fraction(0))
        seg = before.segment
        if key in ended:
            receiver = shared.get(ob.subject_key)
            posted = before.posted + share.posted + (0 if receiver is None else receiver.posted)
            exact = before.exact + share.exact + (0 if receiver is None else receiver.exact)
            inputs = [share.node_id] + ([] if receiver is None else [receiver.node_id])
            terminations.emit_allocation(
                ctx, tb, ev, ob.subject_key, before, posted=posted, exact=exact, inputs=inputs
            )
            boundary = terminations.segment(
                ctx,
                ev,
                before,
                x_exact=exact,
                a_posted=posted,
                billing_plan=seg.remaining_billing_plan + consideration_change,
            )
            changed[ob.subject_key] = dataclasses.replace(
                ob,
                quantity=ob.quantity + quantity_change,
                stated_price=ob.stated_price + consideration_change,
                end_date=segments.boundary_as_of(ev),
                terminated_on=d,
                segments=(*ob.segments, boundary),
                last_modification_key=mod.modification_key,
            )
            boundaries.append(
                _Boundary(
                    ob.subject_key, before, "T", None, before.posted, SegmentCause.TERMINATION
                )
            )
            continue
        receiver = shared.get(ob.subject_key)  # the delivered portion's ΔC_sat share (S06-R-09)
        satisfied_posted = 0 if receiver is None else receiver.posted
        x_exact = Fraction(before.posted + satisfied_posted, 10**mu) + share.exact
        a_posted = before.posted + satisfied_posted + share.posted
        if key in nondistinct:
            boundary = segments.inception(
                ctx,
                ev,
                source=seg,
                x_exact=x_exact,
                a_posted=a_posted,
                totals=totals[key],
                remaining_ssp=weight.value,
                unit_ssp=None if totals[key].quantity == 0 else weight.value / totals[key].quantity,
                billing_plan=seg.remaining_billing_plan + consideration_change,
                cause=route.cause,
            )
        else:
            boundary = segments.prospective(
                ctx,
                ev,
                before=before,
                x_exact=x_exact,
                a_posted=a_posted,
                totals=totals[key],
                progress_measure=seg.progress_measure,
                weight=weight.value,
                billing_plan=seg.remaining_billing_plan + consideration_change,
                boundary_no=seg.modification_boundary_no + 1,
                cause=route.cause,
                satisfied=satisfied_posted,
            )
        changed[ob.subject_key] = dataclasses.replace(
            ob,
            quantity=ob.quantity + quantity_change,
            stated_price=ob.stated_price + consideration_change,
            end_date=_line_date(lines, "end_date") or ob.end_date,
            segments=(*ob.segments, boundary),
            lineage_pre_modification=pre,
            last_modification_key=mod.modification_key,
        )
        kind = "N" if key in nondistinct else "D"
        residue = (
            Fraction(0) if receiver is None else Fraction(receiver.posted, 10**mu) - receiver.exact
        )
        boundaries.append(
            _Boundary(
                ob.subject_key,
                before,
                kind,
                share.node_id,
                before.posted + satisfied_posted,
                route.cause,
                satisfied_residue=residue,
            )
        )
    for ob in receivers:
        if ob.subject_key not in shared or ob.obligation_key in ended:
            continue
        if (
            ob.obligation_key in pooled
        ):  # a delivered portion: its class D segment carries the share
            continue
        before, receiver = befores[ob.obligation_key], shared[ob.subject_key]
        seg = before.segment
        seg_totals = (
            seg.totals
            if seg.basis == "INCEPTION"
            else ProgressTotals(
                ob.quantity,
                seg.totals.eac_element_code,
                ob.start_date or seg.totals.start_date,
                ob.end_date or seg.totals.end_date,
            )
        )
        boundary = segments.inception(
            ctx,
            ev,
            source=seg,
            x_exact=seg.x_exact + receiver.exact,
            a_posted=seg.a_posted + receiver.posted,
            totals=seg_totals,
            remaining_ssp=seg.remaining_ssp,
            unit_ssp=seg.unit_ssp,
            billing_plan=seg.remaining_billing_plan,
            cause=route.cause,
        )
        changed[ob.subject_key] = dataclasses.replace(
            ob, segments=(*ob.segments, boundary), last_modification_key=mod.modification_key
        )
        boundaries.append(
            _Boundary(ob.subject_key, before, "S", receiver.node_id, seg.a_posted, route.cause)
        )
    for key in named_satisfied:
        ob = changed.get(by_key[key].subject_key, by_key[key])
        consideration_change = sum(
            (line.consideration_delta for line in lines_on[key]), Fraction(0)
        )
        changed[ob.subject_key] = dataclasses.replace(
            ob,
            stated_price=ob.stated_price + consideration_change,
            last_modification_key=mod.modification_key,
        )
    for key, end in extensions.items():
        ob = by_key[key]
        seg = _in_force(st, ob, ev)
        before = subscriptions.redemption_measure(ctx, st, ob, seg, ev)
        boundary = subscriptions.extension_segment(ev, seg, end, cause=route.cause)
        changed[ob.subject_key] = dataclasses.replace(
            ob,
            end_date=end,
            segments=(*ob.segments, boundary),
            last_modification_key=mod.modification_key,
        )
        boundaries.append(_Boundary(ob.subject_key, before, "R", None, seg.a_posted, route.cause))
    created: list[ObligationState] = []
    for draft in drafts:
        share, weight = shares[draft.subject_key], weighted[draft.subject_key]
        boundary = segments.prospective(
            ctx,
            ev,
            before=None,
            x_exact=share.exact,
            a_posted=share.posted,
            totals=ProgressTotals(draft.quantity, None, draft.start_date, draft.end_date),
            progress_measure=draft.recognition_method.value,
            weight=weight.value,
            billing_plan=draft.stated_price,
            boundary_no=1,
            cause=route.cause,
        )
        emit_original_quantity(tb, draft, ev.event_key)  # CV-47 (b): real quantity provenance
        links = provenance.emit_original_allocation(  # CV-50 (D-98 121): the creation pair
            ctx,
            tb,
            ev.event_key,
            draft.subject_key,
            Quota(share.exact, share.posted),
            exact_inputs=[share.node_id],
            amount_inputs=[share.node_id],
            rule="S06-R-14",
        )
        snapshot = provenance.emit_snapshot_columns(  # CV-50 rev 1.29 (D-98 124)
            ctx,
            tb,
            ev.event_key,
            draft.subject_key,
            selected_node=f"original_ssp_selected@{ev.event_key}:{draft.subject_key}:-",
            selected=weight.value,  # the raw selected SSP of the added line (S06-R-11)
            quantity=draft.original_quantity,
            stated_price=draft.original_stated_price,  # echoed after boundary_state.emit
            price=price_after.total,
            rule="S06-R-14",
            total_inputs=[f"mod_weight@{ev.event_key}:{key}:-" for key in order],
            total_value=total_weight,
            weight_input=f"mod_weight@{ev.event_key}:{draft.subject_key}:-",
            weight_value=weight.value,
        )
        created.append(
            _added_obligation(
                identified,
                draft,
                boundary,
                weight,
                pre,
                mod.modification_key,
                price_after,
                total_weight,
                (share.node_id,),  # the mod_share@<event> producer of the added quota
                links,
                snapshot,
            )
        )
        boundaries.append(_Boundary(draft.subject_key, None, "D", share.node_id, 0, route.cause))
    obligations = lineage.record(st, mod.contract_key, mod.modification_key, changed, created)
    components = st.refund_components
    history = st.concession_history
    if route.refund != 0:
        component = terminations.component_key(mod.contract_key, ev)
        terminations.emit_refund(ctx, tb, ev, mod.contract_key, route.refund)
        quota = Quota(Fraction(route.refund, 10**mu), route.refund)
        components = MappingProxyType(dict(sorted({**components, component: quota}.items())))
    if shared and satisfied.settlement(mod) == satisfied.CREDIT_OR_REFUND:
        # D-87 L6-5-Q-10: each receiving obligation's negative share adds a CONCESSION refund
        # quota, dated at d with event key CONTRACT_AMENDED (S06-R-09 apportionment, S06-R-10
        # targeting); stage 10 and JET-05c consume it as built.
        # The share was applied to the receiver's recognition segment above (x′ = X + share,
        # a′ = A + share), so the stage 09 revenue node already carries the concession: the quota
        # is EMBEDDED for the share-based numerator (S10-R-26; L9-ENG-B3-Q-1).
        concessions = dict(components)
        additions: list[ConcessionAddition] = []
        for subject_key, receiver in sorted(shared.items()):
            if receiver.exact >= 0:
                continue
            held = concessions.get(subject_key, Quota(Fraction(0), 0))
            concessions[subject_key] = ConcessionQuota(
                held.x_exact - receiver.exact,
                held.a_posted - receiver.posted,
                revenue_basis=CONCESSION_EMBEDDED,
            )
            # The dated source subledger entry (S10-R-26): the receiver's own signed exact share
            # and its separately allocated posted cents, at the amendment's ENG-06 position.
            additions.append(
                ConcessionAddition(
                    subject_key=subject_key,
                    event_key=ev.event_key,
                    effective_date=ev.effective_date,
                    order_key=ev.order_key,
                    exact=-receiver.exact,
                    posted=-receiver.posted,
                    producer="06",
                    revenue_basis=CONCESSION_EMBEDDED,
                )
            )
        components = MappingProxyType(dict(sorted(concessions.items())))
        history = (*st.concession_history, *additions)
    result = dataclasses.replace(
        _with_findings(st, findings),
        obligations=obligations,
        tp_history=(*st.tp_history, price_after),
        refund_components=components,
        concession_history=history,
    )
    _catch_ups(ctx, tb, result, ev, boundaries)
    boundary_state.emit(ctx, tb, st, result, ev)
    provenance.emit_stated_price_echoes(
        ctx, tb, ev, created
    )  # CV-50 rev 1.29 (D-98 124)  # D-97 (8) T1F-Q-3 (c)
    _assert_allocation_sum(result, ev, price_after)
    _assert_moved(ev, result, boundaries, consideration, vc_delta, mu)
    return result


def _delivered_portions(
    mod: ModificationView,
    pooled: Sequence[str],
    excluded: set[str],
    lines_on: Mapping[str, Sequence[ModificationLine]],
    befores: Mapping[str, segments.Measured],
    by_key: Mapping[str, ObligationState],
) -> list[ObligationState]:
    """S06-R-09: the class D obligations whose delivered portion receives ΔC_sat.

    Only a tagged ``price_change_amount`` names them, through the lines of the modification (ALG-04
    §2.5.3 "when the tag names them"). An obligation without revenue before the boundary has no
    delivered portion. ``excluded`` holds the ended and the class N obligations.
    """
    if mod.price_change_amount is None:
        return []
    return [
        by_key[key]
        for key in pooled
        if key not in excluded and key in lines_on and befores[key].posted != 0
    ]


def _negative_allocations(
    mod: ModificationView,
    mu: int,
    pooled: Sequence[ObligationState],
    befores: Mapping[str, segments.Measured],
    ended: frozenset[str],
    drafts: Sequence[PobDraft],
    receivers: Sequence[ObligationState],
    previews: Mapping[str, tuple[int, Fraction]],
    received: Mapping[str, tuple[int, Fraction]],
) -> list[Finding]:
    """S06-R-22: a pool share or price change that makes an allocation negative (``ERROR``)."""
    nothing = (0, Fraction(0))
    found: list[Finding] = []

    def check(subject_key: str, obligation_key: str, posted: int, exact: Fraction) -> None:
        if posted < 0 or exact < 0:
            found.append(
                _finding(
                    "VC_ALLOCATION_NEGATIVE",
                    mod,
                    subject_key,
                    obligation_key,
                    "S06-R-22",
                    allocation=format_exact(Fraction(posted, 10**mu)),
                )
            )

    for ob in pooled:
        before = befores[ob.obligation_key]
        share, extra = previews.get(ob.subject_key, nothing), received.get(ob.subject_key, nothing)
        base = before.exact if ob.obligation_key in ended else Fraction(before.posted, 10**mu)
        posted = before.posted + share[0] + extra[0]
        check(ob.subject_key, ob.obligation_key, posted, base + share[1] + extra[1])
    for draft in drafts:
        share = previews.get(draft.subject_key, nothing)
        check(draft.subject_key, draft.obligation_key, share[0], share[1])
    pooled_keys = {ob.subject_key for ob in pooled}  # delivered portions are checked above
    for ob in receivers:
        if ob.obligation_key in ended or ob.subject_key not in received:
            continue
        if ob.subject_key in pooled_keys:
            continue
        seg, extra = befores[ob.obligation_key].segment, received[ob.subject_key]
        check(ob.subject_key, ob.obligation_key, seg.a_posted + extra[0], seg.x_exact + extra[1])
    return found


def _in_force(st: AllocatedState, ob: ObligationState, ev: EventView) -> AllocationSegment:
    seg = segments.in_force(st, ob, ev)
    if seg is None:
        raise _invariant(
            "an obligation has no allocation before the boundary",
            ev,
            rule="CV-60",
            obligation_key=ob.obligation_key,
        )
    return seg


def _measure(
    ctx: BookContext, st: AllocatedState, ob: ObligationState, ev: EventView
) -> segments.Measured:
    return segments.measure(ctx, st, ob, _in_force(st, ob, ev), ev)


def _catch_ups(
    ctx: BookContext,
    tb: TraceBuilder,
    result: AllocatedState,
    ev: EventView,
    boundaries: Sequence[_Boundary],
) -> None:
    """``catch_up@<event key>:<ob>:-`` of every obligation with a boundary segment (S06-R-17)."""
    subjects = {ob.subject_key: ob for ob in result.obligations}
    for item in boundaries:
        ob = subjects[item.subject_key]
        seg = ob.segments[-1]
        if item.kind == "R":
            after = subscriptions.redemption_measure(ctx, result, ob, seg, ev)
        else:
            after = segments.measure(ctx, result, ob, seg, ev, eac_before=item.kind != "N")
        if item.kind == "D" and after.posted != item.base:
            raise _invariant(
                "a class D segment does not start at the revenue before the boundary",
                ev,
                invariant="S06-INV-02",
                obligation_key=ob.obligation_key,
            )
        if item.kind in ("S", "T", "X") and after.progress != 1:
            rules = {"S": "S06-R-09", "T": "S06-R-21", "X": "S06-R-23"}
            raise _invariant(
                "a satisfied, ended or exercised obligation is not complete after the boundary",
                ev,
                rule=rules[item.kind],
                obligation_key=ob.obligation_key,
            )
        segments.emit_catch_up(
            ctx,
            tb,
            ev,
            item.subject_key,
            before=item.before,
            after=after,
            share_node=item.share_node,
            base=item.base,
            extra={"cause": item.cause.value},
        )


def _assert_allocation_sum(result: AllocatedState, ev: EventView, price_after: TpBuildUp) -> None:
    """S06-INV-01: Σ a_posted over the group after the event = the allocation basis after it.

    The basis carries the S04-R-06 realised amounts (``TpBuildUp.realised``: right-to-invoice
    amounts, usage fees and royalties), which are allocated entirely to their obligation's
    ``PERIOD_VC`` or ``ROYALTY`` component (606-10-32-40; ENGINE_SPEC_B S09-R-01) and never to a
    ``FIXED`` segment, so the FIXED allocations sum to the basis less them (ENC-6).
    """
    total = 0
    for ob in result.obligations:
        seg = segments.in_force(result, ob, ev, inclusive=True)
        if seg is not None:
            total += seg.a_posted
    fixed_basis = price_after.allocation_basis.posted - price_after.realised.posted
    if total != fixed_basis:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the allocations after the boundary do not sum to the allocation basis",
            subject_key=result.group_code,
            detail={
                "allocated": str(total),
                "allocation_basis": str(price_after.allocation_basis.posted),
                "event_key": ev.event_key,
                "invariant": "S06-INV-01",
                "realised": str(price_after.realised.posted),
            },
        )


def _assert_moved(
    ev: EventView,
    result: AllocatedState,
    boundaries: Sequence[_Boundary],
    consideration: int,
    vc_delta: int,
    mu: int,
) -> None:
    """S06-INV-04: Σ (x′ − x) = Σ ΔC + ΔVC, plus the rounding residues of the pooled obligations.

    X′_p builds on the posted R_p and the posted pool (ALG-04 §2.5.5), so the residues A_p − X_p
    of the pooled allocations carry into Σ x′; they are 0 whenever every pooled X_p equals A_p. An
    ended obligation builds on the exact E_before(d_T), which adds E − C. The shares of satisfied
    performance (S06-R-09) leave the pool and reach the receivers, so they cancel in the sum; a
    rollover extension keeps X.
    """
    subjects = {ob.subject_key: ob for ob in result.obligations}
    scale = 10**mu
    moved = Fraction(0)
    residue = Fraction(0)
    for item in boundaries:
        after = subjects[item.subject_key].segments[-1].x_exact
        if item.before is None:
            moved += after
            continue
        moved += after - item.before.segment.x_exact
        if item.kind in ("D", "N", "T"):
            residue += Fraction(item.before.segment.a_posted, scale) - item.before.segment.x_exact
        if item.kind == "T":
            residue += item.before.exact - Fraction(item.before.posted, scale)
        residue += item.satisfied_residue  # a D base takes the posted share, receivers the exact
    expected = Fraction(consideration + vc_delta, scale) + residue
    if moved != expected:
        raise _invariant(
            "the exact allocations moved by the modification differ from its consideration",
            ev,
            invariant="S06-INV-04",
            moved=format_exact(moved),
            expected=format_exact(expected),
        )


_HANDLERS: Final[Mapping[str, _Handler]] = MappingProxyType(
    {
        _AMENDED: _amended,
        _ATTRIBUTES: _attributes_changed,
        _EXERCISED: _exercised,
        _REGROUPED: _regrouped,
        _TERMINATED: _terminated,
    }
)
