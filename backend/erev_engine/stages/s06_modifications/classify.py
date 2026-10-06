"""Stage 06 proposal classification: the modification view, added lines and classes S, D and N.

ENGINE_SPEC §6.1, §6.2 S06-R-04 and S06-R-05; POLICIES ALG-04 §2.5.2; finding
``MOD_QTY_ON_SATISFIED_POB``; formula ``mod.classify.v1``. Private to stage 06. Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import ENGINE_VERSION, progress
from erev_engine.bundle import ModificationInput
from erev_engine.enums import Distinctness
from erev_engine.money import format_exact, to_fraction
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    encode_key,
    payload_bool,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, build_lines
from erev_engine.stages.s09_recognition import input_progress
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    Finding,
    LedgerPoint,
    ObligationState,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "ACTIONS",
    "FORMULA_ID",
    "AddedLine",
    "ModificationLine",
    "ModificationView",
    "ObligationClass",
    "added_lines",
    "classify",
    "contract_obligations",
    "progress_at",
]

FORMULA_ID: Final = "mod.classify.v1"
NARRATIVE_KEY: Final = "mod.classify"
ADD: Final = "ADD"
ACTIONS: Final = frozenset({"ADD", "CHANGE", "REMOVE"})
SATISFIED: Final = "S"
DISTINCT: Final = "D"
NONDISTINCT: Final = "N"
# Measures of progress "by units" (S06-R-05): distinct units transfer one by one.
_UNIT_MEASURES: Final = frozenset({"POINT_IN_TIME", "UNITS_DELIVERED"})
# API-S-ContractLine members copied from a T-CON-06 line for S03 ``build_lines``.
_LINE_MEMBERS: Final = (
    "start_date",
    "end_date",
    "stratification",
    "ssp_version_label",
    "memo_1",
    "memo_2",
    "memo_3",
    "scope_flag",
    "out_of_scope_amount",
    "bundle_parent_obligation_key",
)


def _frozen(value: object) -> object:
    """A read-only copy with every ``Decimal`` as ``Fraction`` (CV-30)."""
    if isinstance(value, Decimal):
        return to_fraction(value)
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _frozen(member) for key, member in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_frozen(member) for member in value)
    return value


@dataclass(frozen=True, slots=True)
class ModificationLine:
    """One T-CON-06 line: signed deltas and the remaining members, decimals as ``Fraction``."""

    obligation_key: str
    action: str  # ADD | REMOVE | CHANGE
    product_code: str | None
    quantity_delta: Fraction  # ΔQ_m
    consideration_delta: Fraction  # ΔC_m
    members: Mapping[str, object]

    def contract_line(self) -> Mapping[str, object]:
        """The API-S-ContractLine members of an added line for ``s03_pob_builder.build_lines``."""
        if self.product_code is None:
            raise ValueError(f"{self.obligation_key}: an added line needs product_code (T-CON-06)")
        line: dict[str, object] = {
            "obligation_key": self.obligation_key,
            "product_code": self.product_code,
            "quantity": self.quantity_delta,
            "total_price": self.consideration_delta,
        }
        for name in _LINE_MEMBERS:
            if self.members.get(name) is not None:
                line[name] = self.members[name]
        if self.members.get("selling_entity_code") is not None:
            line["performing_entity_code"] = self.members["selling_entity_code"]
        if self.members.get("account_codes") is not None:
            line["account_overrides"] = self.members["account_codes"]
        return MappingProxyType(line)


@dataclass(frozen=True, slots=True)
class ModificationView:
    """The ``ModificationView`` of Table 0.2-A: a T-CON-06 object of a member contract."""

    contract_key: str
    modification_key: str
    effective_date: date  # d
    kind: str  # E-25
    template_mode: str | None  # E-24
    questionnaire: Mapping[str, object]  # obligation key -> {question -> answer}; contract members
    lines: tuple[ModificationLine, ...]
    price_change_amount: Fraction | None
    event: EventView | None  # the CONTRACT_AMENDED being applied or previewed, if any

    @classmethod
    def of(
        cls,
        contract_key: str,
        modification: ModificationInput,
        *,
        event: EventView | None = None,
    ) -> ModificationView:
        """The view of a bundle ``ModificationInput``; a malformed line raises ``ValueError``."""
        lines = tuple(_line(member, index) for index, member in enumerate(modification.lines))
        price = modification.price_change_amount
        questionnaire = _frozen(modification.questionnaire)
        if not isinstance(questionnaire, Mapping):
            raise ValueError(f"{modification.modification_key}: questionnaire is not an object")
        return cls(
            contract_key=contract_key,
            modification_key=modification.modification_key,
            effective_date=modification.effective_date,
            kind=modification.kind,
            template_mode=modification.template_mode,
            questionnaire=questionnaire,
            lines=lines,
            price_change_amount=None if price is None else to_fraction(price),
            event=event,
        )

    @property
    def position(self) -> str:
        """The measure suffix of the proposal's trace nodes: the event key, else the modification
        key under the contract (CV-50; CV-21)."""
        if self.event is not None:
            return self.event.event_key
        return f"{contract_subject_key(self.contract_key)}/{encode_key(self.modification_key)}"

    def answer(self, obligation_key: str, question: str) -> bool | None:
        """A questionnaire answer for one obligation key, or ``None`` when unanswered."""
        section = self.questionnaire.get(obligation_key)
        if section is None:
            return None
        if not isinstance(section, Mapping):
            raise ValueError(f"questionnaire member {obligation_key} is not an object (T-CON-06)")
        return payload_bool(section, question)


def _line(member: Mapping[str, object], index: int) -> ModificationLine:
    key = payload_text(member, "obligation_key")
    action = payload_text(member, "action")
    if key is None or action not in ACTIONS:
        raise ValueError(
            f"modification line {index}: obligation_key and action ADD, REMOVE or CHANGE are "
            "required (T-CON-06)"
        )
    quantity = payload_fraction(member, "quantity_delta")
    consideration = payload_fraction(member, "consideration_delta")
    frozen = _frozen(member)
    if not isinstance(frozen, Mapping):
        raise ValueError(f"modification line {index} is not an object")
    return ModificationLine(
        obligation_key=key,
        action=action,
        product_code=payload_text(member, "product_code"),
        quantity_delta=Fraction(0) if quantity is None else quantity,
        consideration_delta=Fraction(0) if consideration is None else consideration,
        members=frozen,
    )


@dataclass(frozen=True, slots=True)
class AddedLine:
    """An ``ADD`` line with its stage 03 drafts at the modification date (D-18; S03 build_lines)."""

    line: ModificationLine
    drafts: tuple[PobDraft, ...]  # one per line or bundle component; empty when a finding blocks
    distinct: bool  # questionnaire added_goods_distinct, else no draft is nondistinct
    target: str | None  # integration target of a non-distinct line (S03-R-05)


@dataclass(frozen=True, slots=True)
class ObligationClass:
    """The S06-R-05 class of one obligation after the modification."""

    subject_key: str
    obligation_key: str
    label: str  # "S" | "D" | "N"
    progress: Fraction  # f_p(d)
    reason: str
    measure: str  # progress measure of the segment in force


def contract_obligations(st: AllocatedState, mod: ModificationView) -> tuple[ObligationState, ...]:
    """The obligations of the modified contract not terminated by d, in subject-key order."""
    return tuple(
        ob
        for ob in st.obligations
        if ob.contract_key == mod.contract_key
        and (ob.terminated_on is None or ob.terminated_on > mod.effective_date)
    )


def added_lines(
    ctx: BookContext,
    identified: IdentifiedState,
    mod: ModificationView,
    existing: Sequence[ObligationState],
    findings: list[Finding],
) -> tuple[AddedLine, ...]:
    """Drafts of every ``ADD`` line priced at d (S03-R-01; D-18); stage 03 findings are collected.

    The drafts are traced into a scratch builder: a proposal records no obligation state (CV-16).
    An ``ADD`` line naming an existing obligation, or a ``CHANGE`` or ``REMOVE`` line naming an
    unknown one, raises ``ValueError`` (CV-45; the import raises ``POB_NOT_FOUND``).
    """
    known = {ob.obligation_key for ob in existing}
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    collected: list[AddedLine] = []
    for line in mod.lines:
        if line.action != ADD:
            if line.obligation_key not in known:
                raise ValueError(
                    f"{mod.modification_key}: {line.obligation_key} is not an obligation"
                )
            continue
        if line.obligation_key in known:
            raise ValueError(f"{mod.modification_key}: ADD names obligation {line.obligation_key}")
        drafts = build_lines(
            ctx,
            identified,
            [line.contract_line()],
            mod.effective_date,
            scratch,
            contract_key=mod.contract_key,
            findings=findings,
        )
        answer = mod.answer(line.obligation_key, "added_goods_distinct")
        nondistinct = any(draft.distinctness == Distinctness.NONDISTINCT for draft in drafts)
        distinct = (not nondistinct) if answer is None else answer
        targets = {draft.integrates_into_obligation_key for draft in drafts} - {None}
        target = None if distinct or not targets else sorted(t for t in targets if t)[0]
        collected.append(AddedLine(line, tuple(drafts), bool(drafts) and distinct, target))
    return tuple(collected)


def classify(
    ctx: BookContext,
    st: AllocatedState,
    mod: ModificationView,
    existing: Sequence[ObligationState],
    added: Sequence[AddedLine],
    findings: list[Finding],
    tb: TraceBuilder,
) -> tuple[ObligationClass, ...]:
    """S06-R-05 classes of the existing obligations, with ``mod_class@<position>`` nodes.

    S: f_p(d) = 1; a quantity line on it yields ``MOD_QTY_ON_SATISFIED_POB`` (``ERROR``). D: the
    questionnaire answer ``remaining_goods_distinct_from_transferred``, else true for f_p(d) = 0,
    for series obligations and for distinct obligations measured by units. N otherwise.
    """
    changed = {
        line.obligation_key for line in mod.lines if line.action != ADD and line.quantity_delta
    }
    changed.update(item.target for item in added if item.target is not None)
    classes: list[ObligationClass] = []
    for ob in existing:
        f, measure = progress_at(ctx, st, ob, mod)
        answer = mod.answer(ob.obligation_key, "remaining_goods_distinct_from_transferred")
        if f == 1:
            label, reason = SATISFIED, "SATISFIED"
            if ob.obligation_key in changed:
                detail = {
                    "modification_key": mod.modification_key,
                    "obligation_key": ob.obligation_key,
                    "rule": "S06-R-05",
                }
                event_key = None if mod.event is None else mod.event.event_key
                findings.append(
                    Finding(
                        "MOD_QTY_ON_SATISFIED_POB", "ERROR", ob.subject_key, detail, 6, event_key
                    )
                )
        elif answer is not None:
            label, reason = (DISTINCT if answer else NONDISTINCT), "QUESTIONNAIRE"
        elif f == 0:
            label, reason = DISTINCT, "UNSTARTED"
        elif ob.distinctness == Distinctness.SERIES:
            label, reason = DISTINCT, "SERIES"
        elif ob.distinctness == Distinctness.DISTINCT and measure in _UNIT_MEASURES:
            label, reason = DISTINCT, "DISTINCT_UNITS"
        else:
            label, reason = NONDISTINCT, "PARTIALLY_SATISFIED"
        classes.append(
            ObligationClass(ob.subject_key, ob.obligation_key, label, f, reason, measure)
        )
    for item in added:
        if item.target is not None:
            continue
        for draft in item.drafts:
            reason = "NEW_DISTINCT" if item.distinct else "NEW_UNSTARTED"
            measure = draft.recognition_method.value
            classes.append(
                ObligationClass(
                    draft.subject_key, draft.obligation_key, DISTINCT, Fraction(0), reason, measure
                )
            )
    for found in classes:
        emit(tb, mod, found)
    return tuple(classes)


def emit(tb: TraceBuilder, mod: ModificationView, item: ObligationClass) -> None:
    tb.node(
        measure=f"mod_class@{mod.position}",
        subject_key=item.subject_key,
        period_key=None,
        value=item.progress,
        currency=None,
        minor_unit=None,
        formula_id=FORMULA_ID,
        inputs=(),
        params={
            "class": item.label,
            "progress_measure": item.measure,
            "reason": item.reason,
            "value": format_exact(item.progress),
        },
        narrative_key=NARRATIVE_KEY,
    )


def _segment_in_force(ob: ObligationState, at: date) -> AllocationSegment | None:
    found: AllocationSegment | None = None
    for segment in ob.segments:
        if segment.effective_date <= at:
            found = segment
    return found


def progress_at(
    ctx: BookContext, st: AllocatedState, ob: ObligationState, mod: ModificationView
) -> tuple[Fraction, str]:
    """f_p(d) on the inception basis over the totals in force (ENGINE_SPEC §6.1; CV-61).

    Units (``POINT_IN_TIME``, ``UNITS_DELIVERED`` and the parity measures) take net delivered units
    over Q; ``TIME_ELAPSED`` the ALG-11 fraction of the term; ``OUTPUT_PERCENT`` and ``MILESTONE``
    the ledger ratio and weight; ``COST_TO_COST`` and ``LABOUR_HOURS`` the ledger over the EAC pin
    in force (0 without a pin). The ledger position is before the modification event when the view
    carries one, else the end of d.
    """
    d = mod.effective_date
    segment = _segment_in_force(ob, d)
    measure = ob.recognition_method.value if segment is None else segment.progress_measure
    quantity = ob.quantity if segment is None else segment.totals.quantity
    start = (
        ob.start_date
        if segment is None or segment.totals.start_date is None
        else segment.totals.start_date
    )
    end = (
        ob.end_date
        if segment is None or segment.totals.end_date is None
        else segment.totals.end_date
    )
    point: LedgerPoint = (
        st.ledger.at(ob.subject_key, on=d)
        if mod.event is None
        else st.ledger.at(ob.subject_key, before=mod.event)
    )
    match measure:
        case "TIME_ELAPSED":
            if start is None or end is None:
                return Fraction(0), measure
            entity = ctx.entities.get(ob.performing_entity)
            calendar = None if entity is None else entity.periods
            convention = "DAILY" if ob.ratable_convention is None else ob.ratable_convention.value
            return progress.time_fraction(convention, start, end, d, calendar=calendar), measure
        case "OUTPUT_PERCENT":
            return progress.output_fraction(point.output_ratio), measure
        case "MILESTONE":
            return progress.milestone_fraction(point.milestone_weight_cum), measure
        case "COST_TO_COST" | "LABOUR_HOURS":
            # S09-R-14, S09-R-15 through stage 09 (ENC-5): 0 without a pin (S09-R-16).
            if segment is None:
                return Fraction(0), measure
            return input_progress(st, ob, segment, d, event=mod.event), measure
        case _:
            delivered = max(Fraction(0), point.delivered_cum - point.returned_cum)
            return progress.units_fraction(delivered, quantity), measure
