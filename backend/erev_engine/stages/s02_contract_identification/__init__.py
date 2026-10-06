"""Stage 02 contract identification: Step 1 gate, enforceable term and deposits.

ENGINE_SPEC §2.2 and §2.3 (S02-R-01 to S02-R-12), §2.5 (S02-INV-01 to S02-INV-04, finding
``INVOICE_ON_NOT_A_CONTRACT``, formulas ``step1.*``); §0.3 Table 0.3-A; POL-011 to POL-016, POL-128;
JET-01b (CHK-021). S02-R-13 and S02-R-14 are platform functions (CTR). ``run`` folds the group's
inception state per book; ``run_deposits`` folds the deposit ledger after stage 03, whose
classification the time-aware 25-7(a) test reads (S02-R-07 rev 1.6; D-91 gaps (ii), (iii)), and
the book loop replaces ``published["02"]`` with the refined state before stage 04; ``apply`` is the
boundary handler of ``COLLECTIBILITY_ASSESSED``, ``CONTRACT_CRITERIA_MET`` and
``SIGNIFICANT_CHANGE_FLAGGED``. Submodules are private (DG-ENG-07). Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

import bisect
import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erev_engine import billing_identity
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import (
    booking_lines,
    contract_subject_key,
    obligation_subject_key,
    payload_fraction,
)
from erev_engine.stages.s02_contract_identification import deposits, status, term
from erev_engine.stages.s02_contract_identification.deposits import (
    CriteriaMetTransition,
    DepositPoint,
    DepositRecognition,
)
from erev_engine.stages.s02_contract_identification.status import STATUS_ORDINAL, StatusSegment
from erev_engine.stages.s02_contract_identification.term import EnforceableTerm
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    CanonicalBundle,
    ContractView,
    EventView,
    Finding,
    LedgerPoint,
    QuantityLedger,
    Target,
)
from erev_engine.trace import TraceBuilder

if TYPE_CHECKING:
    from erev_engine.stages.s03_pob_builder import PobState

__all__ = [
    "FORMULA_IDS",
    "HANDLED_EVENT_TYPES",
    "POLICY_KEYS",
    "CriteriaMetTransition",
    "DepositPoint",
    "DepositRecognition",
    "EnforceableTerm",
    "IdentifiedState",
    "StatusSegment",
    "apply",
    "run",
    "run_deposits",
]

# Stage 03 classification of a booking line for the 25-7(a) time test: (start, end) of a resolved
# ``OVER_TIME`` ``TIME_ELAPSED`` term, None for an unresolved one; a line absent from the mapping
# keeps the ledger test (S02-R-07 rev 1.6; D-91 gaps (ii)).
TimeTerms = Mapping[str, tuple[date, date] | None]

# ENGINE_SPEC Table 0.10-A row 02 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "balance.deposit_liability",
    "step1.collectibility_threshold",
    "step1.criteria_met_transition",
    "step1.event_c_enabled",
    "step1.portfolio_approach",
    "step1.term_with_termination_rights",
)
# ENGINE_SPEC §2.5 formula ids, sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "step1.deposit.v1",
    "step1.enforceable_term.v1",
    "step1.event_25_7.v1",
    "step1.status.v1",
    "step1.transition_catch_up.v1",
)
# Table 0.3-A literals folded by ``apply``.
HANDLED_EVENT_TYPES: Final = frozenset(
    {"COLLECTIBILITY_ASSESSED", "CONTRACT_CRITERIA_MET", "SIGNIFICANT_CHANGE_FLAGGED"}
)


@dataclass(frozen=True, slots=True)
class IdentifiedState:
    """Stage 02 output for one book (ENGINE_SPEC §2.1), consumed by stage 03."""

    book_code: str
    canonical: CanonicalBundle
    group_code: str
    inception_date: date  # earliest member inception (T-CON-03)
    member_contract_keys: tuple[str, ...]  # the inception fold (CV-10; S02-R-09)
    contracts: tuple[ContractView, ...]  # external_id; status_in_book holds this book
    timelines: Mapping[str, tuple[StatusSegment, ...]]  # contract key -> ascending segments
    terms: Mapping[str, EnforceableTerm]  # contract key -> enforceable term (S02-R-06)
    deposits: Mapping[str, tuple[DepositPoint, ...]]  # contract key -> ascending deposit points
    transitions: tuple[CriteriaMetTransition, ...]  # (contract key, ENG-06 order)
    recognitions: tuple[DepositRecognition, ...]  # (contract key, date order)
    deposit_targets: tuple[Target, ...]  # SpecialistTargets.deposit (EMOD-12)
    # BILLING_RECORDED event key -> date the invoice enters billed_cum; None while not a contract
    deferred_invoices: Mapping[str, date | None]
    findings: tuple[Finding, ...]  # CV-43 order

    def status_at(self, contract_key: str, on: date) -> StatusSegment:
        """The segment in force at the end of ``on``."""
        segments = self.timelines[contract_key]
        count = bisect.bisect_right(segments, on, key=lambda segment: segment.from_date)
        return segments[max(count, 1) - 1]

    def deposit_at(
        self, contract_key: str, *, before: EventView | None = None, on: date | None = None
    ) -> DepositPoint:
        """Deposit values before an event or at the end of a date (S02-R-08)."""
        return deposits.point_at(self.deposits.get(contract_key, ()), before=before, on=on)

    def inception_basis(self, contract_key: str) -> tuple[str, date]:
        """The basis and start of the contract's first allocation segments (S02-R-04; CV-61).

        ``CATCH_UP_AT_TRANSITION`` and contracts that never met the criteria late keep the
        ``INCEPTION`` basis from inception; ``PROSPECTIVE_FROM_TRANSITION`` opens the first
        segments at the first ``CRITERIA_MET`` transition with basis ``PROSPECTIVE``.
        """
        inception = self.canonical.contracts[contract_key].header.inception_date
        for record in self.transitions:
            if record.contract_key == contract_key:
                if record.transition == "PROSPECTIVE_FROM_TRANSITION":
                    return "PROSPECTIVE", record.effective_date
                break
        return "INCEPTION", inception


def run(
    ctx: BookContext, cb: CanonicalBundle, tb: TraceBuilder, *, deposits: bool = True
) -> IdentifiedState:
    """The Step 1 gate, enforceable term and deposit accounting of every member (ENGINE_SPEC §2.2).

    Every member's booking enters the inception fold whatever its effective date (CV-10). A member
    in another currency raises ``EngineError("ENGINE_INVARIANT_VIOLATED")`` (S02-R-10, CV-45).
    With ``deposits`` false the deposit ledger is left to ``run_deposits``, which the book loop
    calls after stage 03 so that the 25-7(a) test reads the classification (D-91 gaps (iii)); the
    state then carries no deposit points, recognitions, transitions or targets. On its own,
    ``run`` folds the ledger with the ledger test only (no classification is in scope).
    """
    ctx.policies.require(POLICY_KEYS)
    group = cb.group.group
    _assert_single_currency(cb)
    findings: list[Finding] = []
    views: list[ContractView] = []
    timelines: dict[str, tuple[StatusSegment, ...]] = {}
    terms: dict[str, EnforceableTerm] = {}
    points: dict[str, tuple[DepositPoint, ...]] = {}
    transitions: list[CriteriaMetTransition] = []
    recognitions: list[DepositRecognition] = []
    targets: list[Target] = []
    deferred: dict[str, date | None] = {}
    for contract_key in group.member_contract_keys:
        view = cb.contracts[contract_key]
        lines = booking_lines(view)
        terms[contract_key] = term.enforceable(ctx, cb, contract_key, lines, tb)
        machine, ledger, first_not_a_contract = _fold_contract(
            ctx,
            cb,
            contract_key,
            lines,
            tb,
            findings,
            deferred,
            enforceable=terms[contract_key],
            fold_deposits=deposits,
            emit_status=True,
            time_terms=None,
        )
        timelines[contract_key] = tuple(machine.segments)
        if ledger is not None:
            points[contract_key] = tuple(ledger.points)
            transitions.extend(ledger.transitions)
            recognitions.extend(ledger.recognitions)
            targets.extend(ledger.period_targets(first_not_a_contract))
        else:
            points[contract_key] = ()
        segments = tuple((segment.from_date, segment.status) for segment in machine.segments)
        views.append(
            ContractView(
                header=view.header,
                booking=view.booking,
                status_in_book=MappingProxyType({ctx.book_code: segments}),
            )
        )
    return IdentifiedState(
        book_code=ctx.book_code,
        canonical=cb,
        group_code=group.group_key,
        inception_date=group.inception_date,
        member_contract_keys=group.member_contract_keys,
        contracts=tuple(views),
        timelines=MappingProxyType(timelines),
        terms=MappingProxyType(terms),
        deposits=MappingProxyType(points),
        transitions=tuple(transitions),
        recognitions=tuple(recognitions),
        deposit_targets=tuple(targets),
        deferred_invoices=MappingProxyType(dict(sorted(deferred.items()))),
        findings=tuple(sorted(findings, key=Finding.sort_key)),
    )


def run_deposits(
    ctx: BookContext, identified: IdentifiedState, pob: PobState, tb: TraceBuilder
) -> IdentifiedState:
    """The deposit fold after stage 03 (ENGINE_SPEC §2.3 S02-R-07, S02-R-08 rev 1.6; D-91 (iii)).

    Re-steps every member's status machine silently (the status nodes were emitted by ``run``) and
    folds its deposit ledger with the stage 03 classification in scope: an ``OVER_TIME``
    ``TIME_ELAPSED`` obligation with a resolved term is fully transferred from its term end
    inclusive, the receipt test reads the S02-R-06 enforceable consideration, every recognition
    is capped (gaps (vi)), and (a) is evaluated at T = max(term end) as a dated point ordered after
    every event of T (gaps (ii), (iii)). The refined state replaces ``published["02"]`` and
    ``PobState.identified`` in the book loop before stage 04. A state that already carries
    deposit points is refused: a second pass would duplicate the ledger nodes (CV-50).
    """
    if any(identified.deposits.get(key) for key in identified.member_contract_keys):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the deposit fold runs once, after stage 03 (D-91 gaps (iii))",
            subject_key=identified.group_code,
            detail={"rule": "S02-R-08", "stage": "02"},
        )
    cb = identified.canonical
    findings: list[Finding] = []
    deferred: dict[str, date | None] = {}
    points: dict[str, tuple[DepositPoint, ...]] = {}
    transitions: list[CriteriaMetTransition] = []
    recognitions: list[DepositRecognition] = []
    targets: list[Target] = []
    for contract_key in identified.member_contract_keys:
        view = cb.contracts[contract_key]
        lines = booking_lines(view)
        _machine, ledger, first_not_a_contract = _fold_contract(
            ctx,
            cb,
            contract_key,
            lines,
            tb,
            findings,
            deferred,
            enforceable=identified.terms[contract_key],
            fold_deposits=True,
            emit_status=False,
            time_terms=_time_terms(pob, contract_key),
        )
        if ledger is None:  # pragma: no cover - fold_deposits is True
            raise ValueError("run_deposits folds the deposit ledger")
        points[contract_key] = tuple(ledger.points)
        transitions.extend(ledger.transitions)
        recognitions.extend(ledger.recognitions)
        targets.extend(ledger.period_targets(first_not_a_contract))
    return dataclasses.replace(
        identified,
        deposits=MappingProxyType(points),
        transitions=tuple(transitions),
        recognitions=tuple(recognitions),
        deposit_targets=tuple(targets),
    )


def _time_terms(pob: PobState, contract_key: str) -> TimeTerms:
    """The stage 03 classification of the contract's lines for the 25-7(a) time test.

    A line that belongs to an ``OVER_TIME`` ``TIME_ELAPSED`` obligation (its own draft or the
    draft it merged into, S03-R-05) maps to that obligation's resolved term [start, end], with
    start = ``recognition_start_date`` else ``start_date`` (V5), or to None when the term is
    unresolved (a ``CONTROL_TRANSFER`` or ``FIRST_USAGE`` start not observed, no end date), which
    is never transferred by time. Lines of other obligations are absent and keep the ledger test.
    Routed-out drafts are not obligations (S03-R-11).
    """
    found: dict[str, tuple[date, date] | None] = {}
    for draft in pob.obligations:
        if draft.contract_key != contract_key or draft.routed_out:
            continue
        if (
            str(draft.satisfaction_pattern) != "OVER_TIME"
            or str(draft.recognition_method) != "TIME_ELAPSED"
        ):
            continue
        start = draft.recognition_start_date or draft.start_date
        end = draft.end_date
        span = (start, end) if start is not None and end is not None and start <= end else None
        keys = {draft.obligation_key, *(member.obligation_key for member in draft.members)}
        for key in keys:
            found[key] = span
    return MappingProxyType(found)


def apply(ctx: BookContext, st: AllocatedState, ev: EventView, tb: TraceBuilder) -> AllocatedState:
    """Boundary handler of the Step 1 events (Table 0.3-A; CV-11).

    ``run`` already folds every included event into the status timelines and deposit targets, and
    stage 05 opens the ``PROSPECTIVE`` segments of S02-R-04 from ``IdentifiedState``. A Step 1
    boundary therefore adds no allocation segment and returns the state unchanged.
    """
    if ev.event_type not in HANDLED_EVENT_TYPES:
        raise ValueError(f"{ev.event_key}: {ev.event_type} is not a stage 02 boundary")
    return st


def _assert_single_currency(cb: CanonicalBundle) -> None:
    currency = cb.group.group.transaction_currency
    for contract_key in cb.group.group.member_contract_keys:
        found = cb.contracts[contract_key].header.transaction_currency
        if found != currency:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a member contract departs from the group transaction currency",
                subject_key=contract_subject_key(contract_key),
                detail={"invariant": "S02-INV-04", "rule": "S02-R-10", "currency": found},
            )


def _point_through(ledger: QuantityLedger, subject_key: str, event: EventView) -> LedgerPoint:
    steps = ledger.steps.get(subject_key, ())
    count = bisect.bisect_right(steps, event.order_key, key=lambda step: step.order_key)
    return steps[count - 1].point if count else LedgerPoint.zero()


def _stated_consideration(
    lines: Sequence[Mapping[str, object]], enforceable: EnforceableTerm
) -> Fraction:
    """The stated consideration of the lines, the S02-R-06 enforceable consideration where a
    truncated line carries one (S02-R-07 rev 1.6; D-91 gaps (ii))."""
    truncated = {
        key: consideration
        for key, _end, consideration in enforceable.truncated_lines
        if consideration is not None
    }
    total = Fraction(0)
    for line in lines:
        key = line.get("obligation_key")
        price = payload_fraction(line, "total_price") or Fraction(0)
        if isinstance(key, str) and key in truncated:
            price = truncated[key]
        total += price
    return total


def _fully_performed(
    cb: CanonicalBundle,
    contract_key: str,
    lines: Sequence[Mapping[str, object]],
    *,
    event: EventView | None = None,
    on: date | None = None,
    time_terms: TimeTerms | None = None,
    stated: Fraction,
) -> bool:
    """S02-R-07(a) at an event, or at the end of a date without an event (rev 1.6; D-91 (ii)).

    Every obligation transferred: ledger totals at the booked quantities, output ratio 1 or
    milestone weight 1, or, for a line whose stage 03 classification is a resolved ``OVER_TIME``
    ``TIME_ELAPSED`` term, its term end reached (inclusive, whatever the ALG-11 convention, at the
    dated point ordered after every event of T, or at any later event; an event dated T itself,
    a completing receipt included, does not transfer it, D-94 (1), D1-R01); an unresolved term is
    never transferred by time. Receipts: cumulative receipts through the point at or above
    ``stated``, 100 percent with no tolerance.
    """
    if not lines:
        return False
    if (event is None) == (on is None):
        raise ValueError("pass event or on, not both")
    at = event.effective_date if event is not None else on
    assert at is not None

    def point(subject: str) -> LedgerPoint:
        if event is not None:
            return _point_through(cb.ledger, subject, event)
        return cb.ledger.at(subject, on=at)

    if point(contract_subject_key(contract_key)).paid_cum < stated:
        return False
    for line in lines:
        key = line.get("obligation_key")
        quantity = payload_fraction(line, "quantity")
        if not isinstance(key, str) or quantity is None:
            return False
        if time_terms is not None and key in time_terms:
            span = time_terms[key]
            if span is None or at < span[1] or (event is not None and at == span[1]):
                # Unresolved, or the term has not ended; an event dated T cannot transfer a term
                # ending T: T's dated point, ordered after every event of T, decides, and a
                # receipt dated T completes the receipts before that point (D-91 (iii); D-94 (1)).
                return False
            continue  # the term has ended: transferred by time (D-79, D-91)
        found = point(obligation_subject_key(contract_key, key))
        transferred = (
            found.delivered_cum - found.returned_cum >= quantity
            or found.output_ratio >= 1
            or found.milestone_weight_cum >= 1
        )
        if not transferred:
            return False
    return True


def _time_completion(
    lines: Sequence[Mapping[str, object]], time_terms: TimeTerms | None
) -> date | None:
    """T = max(term end) of the contract's time-elapsed lines; None without such a line or when
    any of them has an unresolved term (never transferred by time, so (a) cannot hold by time)."""
    if time_terms is None:
        return None
    ends: list[date] = []
    for line in lines:
        key = line.get("obligation_key")
        if isinstance(key, str) and key in time_terms:
            span = time_terms[key]
            if span is None:
                return None
            ends.append(span[1])
    return max(ends, default=None)


def _fold_contract(
    ctx: BookContext,
    cb: CanonicalBundle,
    contract_key: str,
    lines: Sequence[Mapping[str, object]],
    tb: TraceBuilder,
    findings: list[Finding],
    deferred: dict[str, date | None],
    *,
    enforceable: EnforceableTerm,
    fold_deposits: bool,
    emit_status: bool,
    time_terms: TimeTerms | None,
) -> tuple[status.StatusMachine, deposits.DepositLedger | None, date | None]:
    """The status timeline and, with ``fold_deposits``, the deposit ledger of one member.

    The 25-7 evaluation runs on every event while ``NOT_A_CONTRACT`` and at the dated points of
    S02-R-07 through the horizon: T = max(term end) of the time-elapsed lines for (a) and
    ``event_c_met_on`` for (c), each ordered after every event of its date and processed in date
    order (a later event flushes the earlier points; the stream end flushes those within the
    horizon). Every recognition is capped at the stated consideration less the revenue already
    recognised under the rule (gaps (vi)).
    """
    header = cb.contracts[contract_key].header
    events = tuple(event for event in cb.events if event.contract_key == contract_key)
    booked_on = next(
        (e.effective_date for e in events if e.event_type == "CONTRACT_BOOKED"),
        header.inception_date,
    )
    not_a_contract = term.judgement(header, "NOT_A_CONTRACT", ctx.book_code)
    nonrefundable = term.outcome_flag(not_a_contract, "consideration_nonrefundable") is True
    event_c_enabled = ctx.policies.value("step1.event_c_enabled", contract=contract_key)
    met_on = term.outcome_date(not_a_contract, "event_c_met_on")
    if not (nonrefundable and event_c_enabled == "ENABLED"):
        met_on = None
    transition = ctx.policies.value("step1.criteria_met_transition", contract=contract_key)
    if not isinstance(transition, str):
        raise ValueError("step1.criteria_met_transition holds one literal (POLICIES POL-013)")
    machine = status.StatusMachine(
        contract_key=contract_key,
        book_code=ctx.book_code,
        header=header,
        booked_on=booked_on,
        penalty_substantive=term.substantive_penalty(header, ctx.book_code),
        criteria_met_transition=transition,
        consideration_nonrefundable=nonrefundable,
    )
    ledger = (
        deposits.DepositLedger(ctx, contract_key, header.contracting_entity_code, tb)
        if fold_deposits
        else None
    )
    stated = _stated_consideration(lines, enforceable)
    first_not_a_contract: date | None = None
    pending_invoices: list[str] = []
    warned_identities: set[tuple[str, str, str]] = set()  # D-97 (29): one finding per identity
    # The dated points of S02-R-07, in date order: (date, route). (a) at T needs the nonrefundable
    # outcome like every route; (c) only under POL-012 ENABLED with met_on.
    dated: list[tuple[date, str]] = []
    if met_on is not None:
        dated.append((met_on, "C"))
    time_end = _time_completion(lines, time_terms) if nonrefundable else None
    if time_end is not None:
        dated.append((time_end, "A"))
    dated.sort()

    def limit() -> Fraction:
        assert ledger is not None
        return stated - ledger.recognised

    def evaluate_dated(on: date, route: str) -> None:
        if ledger is None or machine.current.status != "NOT_A_CONTRACT":
            return
        if route == "C":
            ledger.recognise("EVENT_25_7_C", event=None, on=on, limit=limit())
        elif _fully_performed(cb, contract_key, lines, on=on, time_terms=time_terms, stated=stated):
            ledger.recognise("EVENT_25_7_A", event=None, on=on, limit=limit())

    for event in events:
        while dated and dated[0][0] < event.effective_date:
            on, route = dated.pop(0)
            evaluate_dated(on, route)
        previous = machine.current
        segment = machine.step(event)
        current = machine.current
        if segment is not None:
            if emit_status:
                _status_node(tb, contract_key, event, segment)
            if segment.status == "NOT_A_CONTRACT" and first_not_a_contract is None:
                first_not_a_contract = segment.from_date
            if segment.reason == "CRITERIA_MET" and segment.transition is not None:
                if ledger is not None:
                    ledger.transfer(event, segment.transition)
                for invoice in pending_invoices:  # S02-R-11: billed_cum from the transition date
                    deferred[invoice] = event.effective_date
                pending_invoices.clear()
        not_a_contract_now = current.status == "NOT_A_CONTRACT"
        if event.event_type == "PAYMENT_RECEIVED" and not_a_contract_now:
            amount = payload_fraction(event.payload, "amount")
            if amount is None:
                raise ValueError(f"{event.event_key}: payload member amount is required (§16.3)")
            if ledger is not None:
                ledger.receive(event, amount)
        elif event.event_type == "BILLING_RECORDED" and not_a_contract_now:
            identity = billing_identity.line_identity(event)
            if identity not in warned_identities:  # S02-R-11: once per (contract, identity)
                warned_identities.add(identity)
                findings.append(
                    Finding(
                        "INVOICE_ON_NOT_A_CONTRACT",
                        "WARNING",
                        contract_subject_key(contract_key),
                        {"event_key": event.event_key},
                        2,
                        event.event_key,
                    )
                )
            deferred[event.event_key] = None
            pending_invoices.append(event.event_key)
        elif event.event_type == "CONTRACT_TERMINATED" and previous.status == "NOT_A_CONTRACT":
            if ledger is not None:
                ledger.refund(
                    event, payload_fraction(event.payload, "refund_amount") or Fraction(0)
                )
                if segment is not None and segment.reason == "EVENT_25_7_B":
                    ledger.recognise("EVENT_25_7_B", event=event, limit=limit())
        if ledger is not None and not_a_contract_now and nonrefundable:
            if _fully_performed(
                cb, contract_key, lines, event=event, time_terms=time_terms, stated=stated
            ):
                ledger.recognise("EVENT_25_7_A", event=event, limit=limit())
            elif met_on is not None and met_on <= event.effective_date:
                ledger.recognise("EVENT_25_7_C", event=event, limit=limit())
    horizon_end = _horizon_end(ctx, header.contracting_entity_code)
    for on, route in dated:  # the points after the stream, within the horizon (S02-R-07)
        if horizon_end is not None and on <= horizon_end:
            evaluate_dated(on, route)
    return machine, ledger, first_not_a_contract


def _horizon_end(ctx: BookContext, entity_code: str) -> date | None:
    entity = ctx.entities.get(entity_code)
    horizon_key = ctx.horizon.get(entity_code)
    if entity is None or horizon_key is None:
        return None
    horizon = next((p for p in entity.periods if p.period_key == horizon_key), None)
    return None if horizon is None else horizon.end_date


def _status_node(
    tb: TraceBuilder, contract_key: str, event: EventView, segment: StatusSegment
) -> None:
    ordinal = STATUS_ORDINAL[segment.status]
    params = {"reason": segment.reason, "status": segment.status, "value": str(ordinal)}
    if segment.transition is not None:
        params["transition"] = segment.transition
    tb.node(
        measure=f"status@{event.event_key}",
        subject_key=contract_subject_key(contract_key),
        period_key=None,
        value=ordinal,
        currency=None,
        minor_unit=None,
        formula_id="step1.status.v1",
        inputs=[event.source],
        params=params,
        narrative_key="step1.status",
    )
