"""Stage 03 POB builder: lines, templates, bundles, distinctness, series, scope and elections.

ENGINE_SPEC §3.2 and §3.3 (S03-R-01 to S03-R-18), §3.4 (S03-INV-01 to S03-INV-05, findings
``PRODUCT_UNMAPPED``, ``NEGATIVE_BOOKING_LINE``, ``NON_FINITE_AMOUNT``,
``PRINCIPAL_AGENT_NOT_ASSESSED``, formulas ``pob.*``, trace nodes ``stated_price:<ob>:-``,
``gross_amount_memo:<ob>:-``, ``option_ssp:<ob>:-`` and ``original_quantity:<ob>:-``); CV-27 time
triggers. ``run`` builds the obligations of every member's booking at the group inception (CV-10);
``build_lines`` builds the drafts of lines that a modification or an option exercise adds
(stage 06). Submodules are private (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.bundle import SspEntryInput, TimeTrigger
from erev_engine.errors import EngineError
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import booking_lines
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import (
    agent,
    bundles,
    distinct,
    elections,
    licences,
    measure,
    options,
    scope,
    templates,
    warranties,
)
from erev_engine.stages.s03_pob_builder.bundles import SspValues, ssp_values
from erev_engine.stages.s03_pob_builder.templates import (
    BundleSplit,
    MemberLine,
    PobDraft,
    RawLine,
)
from erev_engine.stages.s03_pob_builder.warranties import WarrantyAccrual
from erev_engine.stages.state import BookContext, Finding
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "POLICY_KEYS",
    "BundleSplit",
    "MemberLine",
    "PobDraft",
    "PobState",
    "RawLine",
    "SspValues",
    "WarrantyAccrual",
    "build_lines",
    "emit_original_quantity",
    "run",
    "ssp_values",
]

# ENGINE_SPEC Table 0.10-A row 03 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "bill_and_hold.custodial_pob",
    "franchisor.preopening_expedient",
    "licence.combined_pob_nature",
    "licence.nature_model",
    "licence.renewal_start",
    "material_right.ssp_method",
    "migration.legacy_vc_rows",
    "migration.material_right_convention",
    "migration.nondistinct_mapping",
    "pob.assurance_warranty_accrual",
    "pob.immaterial_promise_relief",
    "pob.principal_or_agent",
    "pob.shipping_as_fulfilment",
    "recognition.measure_of_progress",
    "recognition.time_convention",
    "scope.collaboration_808",
    "scope.lessor_combination_expedient",
    "scope.nonfinancial_asset_sale_610_20",
    "scope.repurchase_classification",
    "upfront_fee.recognition_period",
)
# POL-030 ("per assessment") and POL-091 ("per revenue policy template") have no framework
# default, so the orchestrator resolves them only where a level sets them (POLICIES §0.4).
OPTIONAL_POLICY_KEYS: Final = frozenset(
    {"pob.principal_or_agent", "recognition.measure_of_progress"}
)
# ENGINE_SPEC §3.4 formula ids, sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "pob.agent_net.v1",
    "pob.bundle_split.v1",
    "pob.merge.v1",
    "pob.option_ssp.v1",
    "pob.template_match.v1",
)


@dataclass(frozen=True, slots=True)
class PobState:
    """Stage 03 output for one book (ENGINE_SPEC §3.1), consumed by stage 04."""

    book_code: str
    group_key: str
    inception_date: date  # group inception, the pricing date of booking lines (S05-R-01)
    identified: IdentifiedState  # stage 02 state: canonical bundle, statuses, terms, deposits
    obligations: tuple[PobDraft, ...]  # subject key; LEASE_842 targets are routed_out (PT-09)
    routed_out: tuple[PobDraft, ...]  # S03-R-11 other flags, no obligation (S04-R-03); subject key
    # (line subject key, rule): no obligation (S03-R-07 option without incremental discount or
    # renewal alternative; S03-R-08 assurance-type warranty line; S03-R-16 custodial service)
    excluded: tuple[tuple[str, str], ...]
    immaterial_candidates: tuple[str, ...]  # S03-R-13 subject keys; stage 05 merges
    time_triggers: tuple[TimeTrigger, ...]  # CV-27: (date, kind, subject key)
    findings: tuple[Finding, ...]  # CV-43 order
    warranty_accruals: tuple[WarrantyAccrual, ...] = ()  # S03-R-08 definitions; subject key


def run(ctx: BookContext, st: IdentifiedState, tb: TraceBuilder) -> PobState:
    """The obligations of every member booking at the group inception (ENGINE_SPEC §3.2; CV-10).

    Every line is priced at the group inception and takes the template version effective at its
    contract's inception (S03-R-01, S03-R-02). Findings are returned in CV-43 order; ``compute``
    raises CV-15 for any ``ERROR``. A failed invariant raises
    ``EngineError("ENGINE_INVARIANT_VIOLATED")`` (CV-46).
    """
    ctx.policies.require(key for key in POLICY_KEYS if key not in OPTIONAL_POLICY_KEYS)
    findings: list[Finding] = []
    drafts: list[PobDraft] = []
    dropped: list[tuple[PobDraft, str]] = []
    merging: dict[str, bool] = {}
    for contract_key in st.member_contract_keys:
        view = st.canonical.contracts[contract_key]
        truncations = {
            key: (end, consideration)
            for key, end, consideration in st.terms[contract_key].truncated_lines
        }
        built, gone = _drafts(
            ctx,
            st,
            contract_key,
            booking_lines(view),
            pricing_date=st.inception_date,
            template_date=view.header.inception_date,
            truncations=truncations,
            findings=findings,
            agreement=None,
        )
        drafts.extend(built)
        dropped.extend(gone)
        mapping = ctx.policies.value("migration.nondistinct_mapping", contract=contract_key)
        merging[contract_key] = mapping != "SINGLE_POB"  # POL-211
    kept, routed = scope.split(drafts)  # S03-R-11
    merged = elections.franchisor_single(ctx, st, elections.shipping(ctx, st, kept))
    grouped = elections.immaterial(ctx, distinct.group(merged, merging))  # S03-R-05, S03-R-13
    obligations = tuple(sorted(grouped, key=lambda draft: draft.subject_key))
    ordered = tuple(sorted(findings, key=Finding.sort_key))
    _assert_invariants(kept, obligations, ordered)
    for obligation in obligations:
        _emit(ctx, st, tb, obligation, _booking_event_key(st, obligation.contract_key))
    for draft, rule in dropped:
        if rule == "S03-R-07" and options.not_material(st, draft):
            event_key = _booking_event_key(st, draft.contract_key)
            options.emit(ctx, st, tb, draft, event_key, reason=options.NOT_MATERIAL)
    assurance_lines = [draft for draft, rule in dropped if rule == "S03-R-08"]
    return PobState(
        book_code=ctx.book_code,
        group_key=st.group_code,
        inception_date=st.inception_date,
        identified=st,
        obligations=obligations,
        routed_out=tuple(sorted(routed, key=lambda draft: draft.subject_key)),
        excluded=tuple(sorted((draft.subject_key, rule) for draft, rule in dropped)),
        immaterial_candidates=tuple(
            ob.subject_key for ob in obligations if ob.immaterial_threshold_pct is not None
        ),
        time_triggers=options.triggers(st, obligations),
        findings=ordered,
        warranty_accruals=warranties.accruals(ctx, st, obligations, assurance_lines),
    )


def build_lines(
    ctx: BookContext,
    st: IdentifiedState,
    lines: Sequence[Mapping[str, object]],
    at: date,
    tb: TraceBuilder,
    *,
    contract_key: str | None = None,
    source_event_key: str | None = None,
    findings: list[Finding] | None = None,
    renewal: bool = False,
) -> tuple[PobDraft, ...]:
    """Drafts of lines added at pricing date ``at`` (Table 0.2-A; D-18; REQ-POB-004).

    One draft per line (per component for a bundle), in line order, with ``original_quantity`` and
    ``original_stated_price`` initialised and the template version effective at ``at``. Nothing is
    merged: stage 06 integrates the drafts. ``contract_key`` defaults to the only member.
    ``renewal`` marks lines booked by a renewal modification, whose licences take the POL-025 start
    guard with agreement date ``at`` (S03-R-10; S06-R-19). Findings are appended to ``findings``;
    without that list an ``ERROR`` finding raises ``EngineError`` with its code.
    """
    if contract_key is None:
        if len(st.member_contract_keys) != 1:
            raise ValueError("build_lines needs contract_key for a group with several members")
        contract_key = st.member_contract_keys[0]
    collected: list[Finding] = [] if findings is None else findings
    drafts, _ = _drafts(
        ctx,
        st,
        contract_key,
        lines,
        pricing_date=at,
        template_date=at,
        truncations={},
        findings=collected,
        agreement=at if renewal else None,
    )
    if findings is None:
        errors = sorted((f for f in collected if f.severity == "ERROR"), key=Finding.sort_key)
        if errors:
            first = errors[0]
            raise EngineError(
                first.code,
                "an added line is blocked by a stage 03 finding",
                subject_key=first.subject_key,
                detail=first.detail,
            )
    for draft in drafts:
        _emit(ctx, st, tb, draft, source_event_key)
    return tuple(drafts)


def _drafts(
    ctx: BookContext,
    st: IdentifiedState,
    contract_key: str,
    lines: Iterable[Mapping[str, object]],
    *,
    pricing_date: date,
    template_date: date,
    truncations: Mapping[str, tuple[date, Fraction | None]],
    findings: list[Finding],
    agreement: date | None,
) -> tuple[list[PobDraft], list[tuple[PobDraft, str]]]:
    """One draft per line and component, with the per-line rules applied, and the lines that
    create no obligation with their rule (S03-R-07, S03-R-08, S03-R-16).

    Order: S03-R-01 collection; S03-R-03 explosion; S03-R-02 and S03-R-18 templates; S03-R-04
    negative lines; S03-R-05 and S03-R-06 distinctness; S03-R-15 distinct services; S03-R-12 and
    S03-R-11 scope; S03-R-08 warranties; S03-R-07 options; S03-R-09 principal or agent; S03-R-10
    licences; S03-R-16 custodial service; S03-R-17 measure.
    """

    def entry_of(raw: RawLine) -> SspEntryInput | None:
        return bundles.ssp_entry(ctx, st, raw)

    raws = [
        templates.collect(
            st,
            contract_key,
            line,
            pricing_date=pricing_date,
            template_date=template_date,
            truncations=truncations,
        )
        for line in lines
    ]
    drafts: list[PobDraft] = []
    dropped: list[tuple[PobDraft, str]] = []
    for raw in bundles.explode(ctx, st, raws, findings):
        draft = templates.resolve(ctx, st, raw, findings, entry_of)
        if draft is None:
            continue
        if not draft.is_vc_line and (draft.quantity < 0 or draft.stated_price < 0):
            detail = {
                "obligation_key": draft.obligation_key,
                "quantity": format_exact(draft.quantity),
                "total_price": format_exact(draft.stated_price),
            }
            findings.append(
                Finding("NEGATIVE_BOOKING_LINE", "ERROR", draft.subject_key, detail, 3, None)
            )
            continue  # POL-078: a negative line is never an obligation
        draft = elections.franchisor_distinct(ctx, st, distinct.classify(ctx, st, draft))
        draft = scope.apply(ctx, st, draft)
        specialist, rule = _specialist(ctx, st, draft, findings, agreement)
        if specialist is None:
            dropped.append((draft, rule))
            continue
        held = elections.custodial(ctx, st, specialist)
        if held is None:
            dropped.append((specialist, "S03-R-16"))
            continue
        drafts.append(measure.apply(ctx, held))
    return drafts, dropped


def _specialist(
    ctx: BookContext,
    st: IdentifiedState,
    draft: PobDraft,
    findings: list[Finding],
    agreement: date | None,
) -> tuple[PobDraft | None, str]:
    """S03-R-08, S03-R-07, S03-R-09 and S03-R-10 for an allocation target (§3.2 order); ``None``
    with the rule when the line creates no obligation. Lines routed out of scope skip them."""
    if draft.scope_flag not in scope.ALLOCATION_TARGET_FLAGS:
        return draft, ""
    split = warranties.split(ctx, st, draft)
    if split is None:
        return None, "S03-R-08"
    option = options.build(ctx, st, split, findings)
    if option is None:
        return None, "S03-R-07"
    netted = agent.apply(ctx, st, option, findings)
    return licences.apply(ctx, st, netted, agreement=agreement), ""


def _booking_event_key(st: IdentifiedState, contract_key: str) -> str | None:
    return next(
        (
            event.event_key
            for event in st.canonical.events
            if event.contract_key == contract_key and event.event_type == "CONTRACT_BOOKED"
        ),
        None,
    )


def _invariant(invariant: str, message: str, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, detail={"invariant": invariant, **detail}
    )


def _assert_invariants(
    drafts: Sequence[PobDraft], obligations: Sequence[PobDraft], findings: Sequence[Finding]
) -> None:
    """S03-INV-01 to S03-INV-05 (CV-46); skipped once an ``ERROR`` finding blocks the stage."""
    if any(finding.severity == "ERROR" for finding in findings):
        return
    keys = [obligation.subject_key for obligation in obligations]
    if len(keys) != len(set(keys)):
        raise _invariant("S03-INV-02", "obligation subject keys repeat in the group")
    lines = sorted(draft.subject_key for draft in drafts)
    members = sorted(member.subject_key for ob in obligations for member in ob.members)
    if members != lines:
        raise _invariant("S03-INV-01", "a line belongs to no obligation or to several")
    for obligation in obligations:
        subject = obligation.subject_key
        if obligation.stated_price < 0 and not obligation.is_vc_line:
            raise _invariant("S03-INV-03", "a stated price is negative", subject_key=subject)
        option = obligation.option_ssp
        if obligation.material_right is not None and option is not None and option < 0:
            raise _invariant("S03-INV-04", "an option SSP is negative", subject_key=subject)
        gross = obligation.gross_amount_memo
        if gross is not None and len(obligation.members) == 1:
            if not 0 <= obligation.stated_price <= gross:
                raise _invariant(
                    "S03-INV-05",
                    "the retained consideration lies outside [0, P]",
                    subject_key=subject,
                )


def _emit(
    ctx: BookContext,
    st: IdentifiedState,
    tb: TraceBuilder,
    draft: PobDraft,
    event_key: str | None,
) -> None:
    """Version-state nodes ``original_quantity``, ``stated_price``, ``gross_amount_memo`` and
    ``option_ssp`` of one obligation (§3.4)."""
    template = _template_params(draft)
    if draft.option_ssp is not None:
        options.emit(ctx, st, tb, draft, event_key)
    emit_original_quantity(tb, draft, event_key)
    if len(draft.members) > 1:
        merged = {**template, "members": ",".join(m.obligation_key for m in draft.members)}
        prices = [(m.obligation_key, m.stated_price) for m in draft.members]
        _exact_node(
            tb,
            "stated_price",
            draft,
            draft.stated_price,
            ctx.txn_currency,
            "pob.merge.v1",
            prices,
            event_key,
            merged,
        )
        return
    key = draft.obligation_key
    if draft.gross_to_net is not None:
        agent.emit(ctx, tb, draft, event_key)
    elif draft.split is None:
        params = {**template, "price_basis": draft.price_basis}
        prices = [(key, draft.stated_price)]
        _exact_node(
            tb,
            "stated_price",
            draft,
            draft.stated_price,
            ctx.txn_currency,
            "pob.template_match.v1",
            prices,
            event_key,
            params,
        )
    else:
        _split_node(ctx, tb, draft, draft.split, event_key, template)


def _template_params(draft: PobDraft) -> dict[str, str]:
    return {
        "basis": draft.template_basis,
        "rule_key": draft.rule_key or "",
        "template_code": draft.template_code,
        "version_key": draft.template_version_key,
    }


def emit_original_quantity(tb: TraceBuilder, draft: PobDraft, event_key: str | None) -> None:
    """The version-state node ``original_quantity:<ob>:-`` of one draft (§3.4): ``pob.merge.v1``
    over the weighted members of a merged draft, else ``pob.template_match.v1`` over the line;
    with ``event_key`` the line's quantity is cited as a ``contract_event`` source (CV-53).

    Stage 03 emits it at inception through ``_emit``. Stage 06 emits it into the REAL trace for an
    obligation a boundary creates — native added goods, legacy retrospective additions and
    material-right continuation goods — whose stage 03 drafts are built in a scratch builder, so
    that the quantity node the original unit revenue rate cites exists with real provenance (the
    creating event's line; ENGINE_SPEC CV-47 (b), D-98 candidate 117 F1)."""
    template = _template_params(draft)
    if len(draft.members) > 1:
        merged = {**template, "members": ",".join(m.obligation_key for m in draft.members)}
        weighted = [(m.obligation_key, m.quantity) for m in draft.members if m.weighted]
        _exact_node(
            tb,
            "original_quantity",
            draft,
            draft.quantity,
            None,
            "pob.merge.v1",
            weighted,
            event_key,
            merged,
        )
        return
    _exact_node(
        tb,
        "original_quantity",
        draft,
        draft.quantity,
        None,
        "pob.template_match.v1",
        [(draft.obligation_key, draft.quantity)],
        event_key,
        template,
    )


def _exact_node(
    tb: TraceBuilder,
    measure: str,
    draft: PobDraft,
    value: Fraction,
    currency: str | None,
    formula_id: str,
    parts: Sequence[tuple[str, Fraction]],
    event_key: str | None,
    params: Mapping[str, str],
) -> None:
    inputs: list[str | SourceRef] = []
    if event_key is not None:
        inputs.extend(
            SourceRef("contract_event", event_key, {"line": line, "value": format_exact(part)})
            for line, part in parts
        )
    tb.node(
        measure=measure,
        subject_key=draft.subject_key,
        period_key=None,
        value=value,
        currency=currency,
        minor_unit=None,
        formula_id=formula_id,
        inputs=inputs,
        params={**params, "value": format_exact(value)},
        narrative_key=formula_id.rsplit(".v", 1)[0],
    )


def _split_node(
    ctx: BookContext,
    tb: TraceBuilder,
    draft: PobDraft,
    split: BundleSplit,
    event_key: str | None,
    template: Mapping[str, str],
) -> None:
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    posted = draft.stated_price * scale
    index = split.keys.index(draft.obligation_key)
    exact = split.bundle_price * split.weights[index] / sum(split.weights, Fraction(0))
    inputs: list[str | SourceRef] = []
    if event_key is not None:
        detail = {"line": split.bundle_key, "value": format_exact(split.bundle_price)}
        inputs.append(SourceRef("contract_event", event_key, detail))
    tb.node(
        measure="stated_price",
        subject_key=draft.subject_key,
        period_key=None,
        value=posted.numerator,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id="pob.bundle_split.v1",
        inputs=inputs,
        params={
            **template,
            "bundle_key": split.bundle_key,
            "index": str(index),
            "keys": ",".join(split.keys),
            "split_basis": split.split_basis,
            "value": format_exact(split.bundle_price),
            "weights": ",".join(format_exact(weight) for weight in split.weights),
        },
        exact=exact,
        narrative_key="pob.bundle_split",
    )
