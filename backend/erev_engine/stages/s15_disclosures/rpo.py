"""Stage 15 remaining performance obligations, exemptions, time bands and the RPO rollforward
(ENGINE_SPEC_B §15.2.3; S15-R-08 to S15-R-12; S15-INV-02; POLICIES POL-197 to POL-201; EDS-1,
EDS-2).

Private to stage 15 (DG-ENG-07). At the version date d_v (04 T-CON-11 ``effective_date``):

- S15-R-08: an obligation is included when stage 09 publishes E-22 ``UNSATISFIED`` or
  ``PARTIALLY_SATISFIED``. Its RPO before exemptions is ``scheduled_amount`` +
  ``awaiting_trigger_amount``, which equals ``allocated_amount`` − ``revenue_cum`` (S09-INV-03).
  The group's ``rpo_amount`` (T-CON-08) sums the included obligations before the S15-R-09
  exemptions — the gross contractual remaining amount (rev 1.26; D-98 candidates 91 / 91a) —
  and ``Rpo.after_exemptions`` names the net (gross = net + exempt).
- S15-R-09, read at the contracting entity's period of d_v (pin ``P``):
  - POL-197 omits every obligation of a contract whose original expected duration, from inception
    to the latest end date of its inception segments, is 12 months or less (L3-2-Q-27);
  - POL-198 omits ``RIGHT_TO_INVOICE`` obligations;
  - POL-199 omits the ``ROYALTY`` component, whose amounts stage 09 realises as reported
    (S09-R-02), so the omitted amount is 0 (L3-2-Q-28);
  - POL-200 omits the targeted VC quota in force at the measured date for a wholly unsatisfied
    obligation, read from ``targeted_vc_quota_history`` (stage 05 at inception, stage 08 after
    each reallocating version; S05-R-14, S08-R-07; D-91): d_v for the RPO row, each end of the
    rollforward; a negative quota exempts nothing; ``rpo_excluded`` records ``quota_as_of`` and
    ``quota_nodes``.
  The registry forces POL-199 and POL-200 to ``DO_NOT_APPLY`` for IFRS15, so no framework literal
  is compared (S13-R-06). Each exemption lists its nature, remaining duration and a description of
  the excluded consideration (50-15).
- S15-R-10: band k covers (d_v + b_(k−1) months, d_v + b_k months] with b_0 = 0, and the last band
  is open-ended (POL-201). Scheduled amounts are placed by period end from the movement of the stage
  09 targets after d_v. What the horizon does not schedule is placed by the obligation's end date
  (L3-2-Q-27). Awaiting-trigger amounts are placed by the end date, else in band 0. A partial
  exemption apportions the non-exempt total with ``largest_remainder`` (``formulas.rpo_bands``).

S15-R-12 (``rollforward``; REQ-RPT-010; V9) gives, per contracting entity and period, the lines of
``ROLLFORWARD_LINES`` per obligation and in total, after exemptions (D-91, which withdraws the
lane simplification L3-2-Q-32):

- the RPO of an obligation at a date d is A(d) − R(d) while it is included (S15-R-08). A(d) is
  ``a_posted`` of the ``FIXED`` segment in force at d plus realized PERIOD_VC/ROYALTY
  allocation at the revenue cut, less the S09-R-23 reduction
  ρ(d) = round(r × (Y + E)) of a returnable obligation under POL-053 ``REDUCE_CONTRACT_QUANTITY``
  (``returns.reduction``; the segments keep the gross allocation, S04-R-08b); R(d) is the stage 09
  ``revenue_cum`` target. ρ(d) and R(d) are read from the states stage 09 publishes at the last
  performing-entity period end on or before d (``return_states``, ``revenue_targets``; C-04), and a
  segment boundary inside the period is measured on its date (D-91). The obligation is included
  while a segment is in force and it is not cancelled (``terminated_on`` on or before d, or a
  ``TERMINATION`` segment in force; S09-R-46); after its cancellation boundary it contributes
  nothing to any line, while its history, the termination period's opening and pre-boundary
  movements and the ``CANCELLATIONS`` removal are retained. The exempt amount at d follows
  S15-R-09, read at the period of d with the targeted quota in force at d;
- ``OPENING`` is the previous lock snapshot when the caller passes one (``opening``), else the RPO
  restated from the version on the day before the period starts. ``LATE_EVENTS`` is the restated
  opening less the snapshot, so 0 without a snapshot;
- ``NEW_CONTRACTS``, ``MODIFICATIONS``, ``VC_ESTIMATE_CHANGES`` and ``CANCELLATIONS`` take the
  movement of the returns-adjusted allocation of the segments effective in the period by cause
  (``CAUSE_LINES``); ``VC_ESTIMATE_CHANGES`` also takes realized-allocation movements and −Δρ
  between boundaries (estimate revisions,
  returns beyond E, window expiry; 606-10-55-25, 32-14, 32-42 to 32-44). ``CANCELLATIONS`` also
  takes what remains when an obligation stops being included;
- ``REVENUE`` is −(R(end) − R(start − 1 day)), ``EXEMPTIONS`` the exempt amount at the opening less
  that at the closing, and ``FX`` 0, because the engine reports the transaction currency (the
  reporting views belong to the platform);
- ``CLOSING`` is the RPO after exemptions at the period end, measured on its own, and equals the
  stage 09 dated measure of the obligation (S15-INV-08); ``UNEXPLAINED`` = closing − (opening +
  movements), shown and never absorbed (V9), and is not by itself evidence of the closing.

Nodes (§15.5): ``rpo_amount:<obligation>:-`` and ``rpo_amount:<group>:-`` (``disc.rpo.v1``; the
group node sums the obligation nodes and, when an expedient applies, carries the additive
params ``excluded`` and ``exempt_nodes``),
``rpo_band:<obligation>/<k>:-`` (``disc.rpo_band.v1``) and ``rpo_excluded:<obligation>/<POL id>:-``
(``disc.rpo_exemption.v1``). §15.5 names no rollforward node, so the rollforward emits none.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.errors import EngineError
from erev_engine.formulas import rpo_bands
from erev_engine.money import format_money
from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.stages.s09_recognition import (
    DepositAttribution,
    ObligationMeasures,
    RecognitionState,
    deposit_attributions,
    deposit_share,
    deposit_share_node_id,
    returns,
    schedule,
)
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    ObligationState,
    Quota,
    SegmentCause,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "CAUSE_LINES",
    "EXEMPTIONS",
    "INCLUDED",
    "MOVEMENTS",
    "ROLLFORWARD_LINES",
    "Exemption",
    "RollforwardRow",
    "STATUS_25_5",
    "Rpo",
    "RpoRollforward",
    "RpoRow",
    "band_index",
    "build",
    "period_of",
    "rollforward",
]

APPLY: Final = "APPLY"
BANDS_CODE: Final = "rpo.time_bands"  # POL-201
ONE_YEAR_MONTHS: Final = 12  # POL-197
INCLUDED: Final = frozenset({"UNSATISFIED", "PARTIALLY_SATISFIED"})  # E-22 (S15-R-08)
UNSATISFIED: Final = "UNSATISFIED"
NOT_A_CONTRACT: Final = "NOT_A_CONTRACT"  # E-17; excluded from RPO (D-91 gaps (vii))
# The rollforward reason of a CANCELLATIONS movement caused by a Step 1 reassessment (D-94 (4)).
STATUS_25_5: Final = "STATUS_25_5"
RIGHT_TO_INVOICE: Final = "RIGHT_TO_INVOICE"
ROYALTY: Final = "ROYALTY"
FIXED: Final = "FIXED"
ALL: Final = "ALL"
AMOUNT: Final = "AMOUNT"
_RPO: Final = "disc.rpo.v1"
_BAND: Final = "disc.rpo_band.v1"
_EXEMPTION: Final = "disc.rpo_exemption.v1"
# (POL id, registry code, basis, description of the excluded consideration), in application order.
EXEMPTIONS: Final = (
    (
        "POL-197",
        "rpo.exemption_original_duration_one_year",
        ALL,
        "consideration of a contract with an original expected duration of one year or less "
        "(606-10-50-14(a))",
    ),
    (
        "POL-198",
        "rpo.exemption_right_to_invoice",
        ALL,
        "consideration the entity has a right to invoice for performance completed to date "
        "(606-10-50-14(b))",
    ),
    (
        "POL-199",
        "rpo.exemption_royalty_vc",
        AMOUNT,
        "sales- or usage-based royalty consideration of a licence (606-10-50-14A(a))",
    ),
    (
        "POL-200",
        "rpo.exemption_vc_wholly_unsatisfied",
        AMOUNT,
        "variable consideration allocated entirely to a wholly unsatisfied performance obligation "
        "(606-10-50-14A(b))",
    ),
)
# S15-R-12 lines in report order: the SCREENS_B RPT-07 rows with the ENGINE_SPEC_B lines for late
# events and exemption movements (L3-2-Q-33).
ROLLFORWARD_LINES: Final = (
    "OPENING",
    "NEW_CONTRACTS",
    "MODIFICATIONS",
    "VC_ESTIMATE_CHANGES",
    "LATE_EVENTS",
    "REVENUE",
    "CANCELLATIONS",
    "EXEMPTIONS",
    "FX",
    "UNEXPLAINED",
    "CLOSING",
)
MOVEMENTS: Final = (  # the lines between opening and closing
    "NEW_CONTRACTS",
    "MODIFICATIONS",
    "VC_ESTIMATE_CHANGES",
    "LATE_EVENTS",
    "REVENUE",
    "CANCELLATIONS",
    "EXEMPTIONS",
    "FX",
)
# The line of a segment's allocation change, by segment cause (S15-R-12; L3-2-Q-33).
CAUSE_LINES: Final[Mapping[str, str]] = MappingProxyType(
    {
        SegmentCause.INCEPTION.value: "NEW_CONTRACTS",
        SegmentCause.OPENING_BALANCE.value: "NEW_CONTRACTS",
        SegmentCause.MODIFICATION.value: "MODIFICATIONS",
        SegmentCause.MATERIAL_RIGHT_EXERCISE.value: "MODIFICATIONS",
        SegmentCause.TP_CHANGE.value: "VC_ESTIMATE_CHANGES",
        SegmentCause.ESTIMATE_CHANGE.value: "VC_ESTIMATE_CHANGES",
        SegmentCause.TERMINATION.value: "CANCELLATIONS",
    }
)


@dataclass(frozen=True, slots=True)
class Exemption:
    """One practical expedient applied to one obligation (S15-R-09; 606-10-50-15)."""

    policy: str  # POL id
    code: str  # registry code
    subject_key: str  # obligation subject key
    amount: int  # omitted from RPO, minor units
    nature: str  # "<E-11 recognition method> <E-12 obligation kind>"
    product_code: str | None
    end_date: date | None
    remaining_months: int  # month ends after d_v through the end date; 0 without an end date
    description: str  # of the excluded consideration
    node_id: str  # rpo_excluded node


@dataclass(frozen=True, slots=True)
class RpoRow:
    """The RPO of one obligation at d_v (S15-R-08 to S15-R-10)."""

    subject_key: str
    contract_key: str
    as_of: date
    included: bool  # UNSATISFIED or PARTIALLY_SATISFIED
    scheduled: int  # stage 09 scheduled_amount of an included obligation, minor units
    awaiting: int  # stage 09 awaiting_trigger_amount of an included obligation
    total: int  # before exemptions: scheduled + awaiting (S15-INV-02)
    excluded: int  # Σ exempt amounts
    bounds: tuple[date, ...]  # POL-201 band upper bounds; the last band is open-ended
    placed: tuple[int, ...]  # per band before exemptions
    bands: tuple[int, ...]  # per band after exemptions; Σ = total − excluded
    exemptions: tuple[Exemption, ...]
    trace_nodes: Mapping[str, str]  # "rpo_amount" and "rpo_band/<k>" -> node id

    @property
    def after_exemptions(self) -> int:
        return self.total - self.excluded


@dataclass(frozen=True, slots=True)
class Rpo:
    """Every obligation's row and the T-CON-08 ``rpo_amount`` node of the group.

    ``total`` is gross of the S15-R-09 exemptions: the contractual remaining amount of the included
    obligations (S15-R-08 rev 1.26; D-98 candidates 91 / 91a). ``excluded`` is Σ exempt amounts and
    ``after_exemptions`` the net the time bands and the rollforward closing carry (S15-INV-08).
    """

    as_of: date
    rows: tuple[RpoRow, ...]
    total: int  # Σ row.total: gross, before exemptions (T-CON-08 rpo_amount)
    excluded: int  # Σ row.excluded
    node_id: str

    @property
    def after_exemptions(self) -> int:
        return self.total - self.excluded


@dataclass(frozen=True, slots=True)
class RollforwardRow:
    """The S15-R-12 lines of one obligation: signed minor units, ``ROLLFORWARD_LINES`` order.

    ``reasons`` names, per line, a distinguishing reason where the line's cause is not its default:
    ``CANCELLATIONS`` carries ``STATUS_25_5`` when the obligation left RPO through a Step 1
    reassessment (the contract's book status turned ``NOT_A_CONTRACT``, 606-10-25-5) rather than a
    termination, so the preparer can reclassify (D-94 (4), Q-10; a presentation question flagged
    for G12).
    """

    subject_key: str
    contract_key: str
    lines: Mapping[str, int]
    reasons: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class RpoRollforward:
    """The RPO rollforward of one contracting entity's period (S15-R-12; REQ-RPT-010; V9)."""

    entity: str
    period_key: str
    opening_date: date  # the day before the period starts
    closing_date: date  # the period end
    rows: tuple[RollforwardRow, ...]  # subject key order
    lines: Mapping[str, int]  # Σ rows per line, ROLLFORWARD_LINES order

    @property
    def unexplained(self) -> int:
        """Closing − (opening + movements); non-zero fails the tie-out (V9)."""
        return self.lines["UNEXPLAINED"]


def build(
    ctx: BookContext, st: AllocatedState, recognition: RecognitionState, tb: TraceBuilder
) -> Rpo:
    """The RPO rows of every obligation stage 09 measured, and the group total (§15.2.3)."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    points = _revenue_points(ctx, recognition)
    short = _short_contracts(st)
    attributed = deposit_attributions(st)  # S14-R-25 (D-91)
    rows: list[RpoRow] = []
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        measures = recognition.obligation_measures.get(ob.subject_key)
        if measures is None:
            continue
        dated = points.get(ob.subject_key, ())
        rows.append(
            _row(
                ctx,
                st,
                ob,
                measures,
                dated,
                short,
                tb,
                minor_unit,
                attribution=attributed.get(ob.contract_key),
            )
        )
    # S15-R-08 (rev 1.26; D-98 candidates 91 / 91a): the group node sums the obligation nodes, so
    # T-CON-08 ``rpo_amount`` is gross of the exemptions; the exempt amount rides along as the
    # additive params ``excluded`` and ``exempt_nodes`` (gross = net + exempt), never as a netting
    # input. The time bands and the rollforward stay net through the rows.
    inputs: list[str | SourceRef] = [row.trace_nodes["rpo_amount"] for row in rows]
    total = sum(row.total for row in rows)
    excluded = sum(row.excluded for row in rows)
    params = {"kind": "group", "minor_unit": str(minor_unit), "signs": "|".join("+" * len(rows))}
    exempt_nodes = [item.node_id for row in rows for item in row.exemptions]
    if exempt_nodes:
        params["excluded"] = str(excluded)
        params["exempt_nodes"] = "|".join(exempt_nodes)
    node_id = tb.node(
        measure="rpo_amount",
        subject_key=st.group_code,
        period_key=None,
        value=total,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=_RPO,
        inputs=inputs,
        params=params,
        narrative_key="disc.rpo",
    )
    return Rpo(
        as_of=_version_date(st), rows=tuple(rows), total=total, excluded=excluded, node_id=node_id
    )


def rollforward(
    ctx: BookContext,
    st: AllocatedState,
    recognition: RecognitionState,
    entity: str,
    period_key: str,
    *,
    opening: Mapping[str, int] | None = None,
) -> RpoRollforward:
    """S15-R-12 lines of the obligations ``entity`` contracts over ``period_key`` of its calendar.

    ``opening`` holds the previous lock snapshot's RPO after exemptions per obligation subject key,
    0 for a key it does not hold; without it the opening is restated from the version.
    """
    calendar = ctx.entities.get(entity)
    period = None
    if calendar is not None:
        period = next((item for item in calendar.periods if item.period_key == period_key), None)
    if period is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the contracting entity keeps no such period",
            detail={"entity": entity, "period_key": period_key, "rule": "CV-12", "stage": "15"},
        )
    before, end = period.start_date - timedelta(days=1), period.end_date
    previous_key = period_of(ctx, entity, before)
    points = _revenue_points(ctx, recognition)
    reductions = _reduction_points(ctx, st, recognition)
    short = _short_contracts(st)
    attributed = deposit_attributions(st)  # S14-R-25 (D-91)
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    rows: list[RollforwardRow] = []
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        if ob.contracting_entity != entity or ob.subject_key not in recognition.obligation_measures:
            continue
        revenue = points.get(ob.subject_key, ())
        reduced = reductions.get(ob.subject_key, ())
        fixed = tuple(seg for seg in ob.segments if seg.component == FIXED)
        # Match the performing-entity period cuts used by recognized revenue. Recognition
        # owns the realization rules (including unrecognized royalties awaiting satisfaction).
        realised = (
            tuple((on, schedule.realised_at(ctx, st, ob, on)) for on, _ in revenue)
            if any(seg.component in ("PERIOD_VC", ROYALTY) for seg in ob.segments)
            else ()
        )
        contract = _contract_of(st, ob)
        basis = _Basis(ctx, contract, attributed.get(ob.contract_key), minor_unit)
        open_in, open_rpo = _rpo_at(ob, fixed, revenue, realised, reduced, before, basis)
        close_in, close_rpo = _rpo_at(ob, fixed, revenue, realised, reduced, end, basis)
        wholly_open = open_in and _revenue_at(revenue, before) == 0
        wholly_close = close_in and _revenue_at(revenue, end) == 0
        restated = open_rpo - _excluded(
            ctx, st, ob, open_rpo, wholly_open, short, previous_key, before
        )
        closing = close_rpo - _excluded(
            ctx, st, ob, close_rpo, wholly_close, short, period_key, end
        )
        lines = dict.fromkeys(ROLLFORWARD_LINES, 0)
        lines["OPENING"] = restated if opening is None else opening.get(ob.subject_key, 0)
        lines["LATE_EVENTS"] = restated - lines["OPENING"]
        cancelled_on = _cancelled_on(ob, fixed)
        if cancelled_on is None or cancelled_on > before:
            # S15-R-12 (D-91): strictly after its cancellation boundary an obligation contributes
            # nothing; its history and the termination period's lines are retained.
            entered = None if open_in else basis.entered(before, end)
            _movements(
                ctx,
                st,
                ob,
                fixed,
                revenue,
                realised,
                reduced,
                before,
                end,
                open_in,
                close_in,
                lines,
                basis,
                entered,
            )
            if entered is not None:
                # D-91 gaps (vii): the obligations of a NOT_A_CONTRACT contract are outside RPO;
                # a contract whose book status turns recognising inside the period enters on the
                # NEW_CONTRACTS line at its allocation net of the 25-7 revenue attributed (the
                # "groups activated in the period" of S15-R-12), so the period ties (V9); one that
                # leaves again before the period end exits through `_movements` (secondary
                # review item 1).
                _, entry = _rpo_at(
                    ob, fixed, revenue, realised, reduced, entered, basis, status=False
                )
                lines["NEW_CONTRACTS"] += entry + _revenue_at(revenue, entered)
        lines["EXEMPTIONS"] = (open_rpo - restated) - (close_rpo - closing)
        lines["CLOSING"] = closing
        lines["UNEXPLAINED"] = closing - lines["OPENING"] - sum(lines[code] for code in MOVEMENTS)
        reasons: dict[str, str] = {}
        if (
            lines["CANCELLATIONS"] != 0
            and not close_in
            and cancelled_on is None
            and basis.excluded(end)
        ):
            reasons["CANCELLATIONS"] = STATUS_25_5  # D-94 (4), Q-10: a status-driven removal
        rows.append(
            RollforwardRow(
                ob.subject_key, ob.contract_key, MappingProxyType(lines), MappingProxyType(reasons)
            )
        )
    totals = {code: sum(row.lines[code] for row in rows) for code in ROLLFORWARD_LINES}
    return RpoRollforward(
        entity=entity,
        period_key=period_key,
        opening_date=before,
        closing_date=end,
        rows=tuple(rows),
        lines=MappingProxyType(totals),
    )


def band_index(end: date, bounds: Sequence[date]) -> int:
    """The band whose (previous bound, bound] holds ``end``; past the last bound, the open band."""
    for index, bound in enumerate(bounds):
        if end <= bound:
            return index
    return len(bounds)


def period_of(ctx: BookContext, entity: str, at: date) -> str:
    """The period of ``entity`` holding ``at``; else the last before it, else the first."""
    calendar = ctx.entities.get(entity)
    if calendar is None or not calendar.periods:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the contracting entity keeps no calendar",
            detail={"entity": entity, "rule": "CV-12", "stage": "15"},
        )
    ordered = sorted(calendar.periods, key=lambda period: period.start_date)
    for period in ordered:
        if period.start_date <= at <= period.end_date:
            return period.period_key
    earlier = [period for period in ordered if period.end_date < at]
    return (earlier[-1] if earlier else ordered[0]).period_key


def _version_date(st: AllocatedState) -> date:
    latest = max((event.effective_date for event in st.events), default=st.inception_date)
    return max(latest, st.inception_date)


def _revenue_points(
    ctx: BookContext, recognition: RecognitionState
) -> dict[str, tuple[tuple[date, int], ...]]:
    """Stage 09 ``revenue_cum`` targets per obligation as ascending (period end, value)."""
    ends = {
        (code, period.period_key): period.end_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    found: dict[str, list[tuple[date, int]]] = {}
    for target in recognition.revenue_targets:
        if target.measure == "revenue_cum":
            end = ends[(target.entity, target.period_key)]
            found.setdefault(target.subject_key, []).append((end, target.value))
    return {subject: tuple(sorted(items)) for subject, items in sorted(found.items())}


def _revenue_at(points: Sequence[tuple[date, int]], at: date) -> int:
    """R(at): the target at the last period end on or before ``at``, else 0."""
    value = 0
    for end, amount in points:
        if end > at:
            break
        value = amount
    return value


def _reduction_points(
    ctx: BookContext, st: AllocatedState, recognition: RecognitionState
) -> dict[str, tuple[tuple[date, int], ...]]:
    """ρ(d) = round(r × (Y + E)) per REDUCE returnable obligation as ascending (performing-entity
    period end, value), from the return states stage 09 publishes (S15-R-12 basis; D-91)."""
    ends = {
        (code, period.period_key): period.end_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    by_key = {ob.subject_key: ob for ob in st.obligations}
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    found: dict[str, list[tuple[date, int]]] = {}
    for (subject_key, period_key), state in recognition.return_states.items():
        ob = by_key.get(subject_key)
        path = st.return_paths.get(subject_key)
        if ob is None or path is None:
            continue
        if returns.policy(ctx, st, ob, returns.SCOPE_POLICY) != returns.REDUCE:
            continue
        end = ends[(ob.performing_entity, period_key)]
        value = returns.reduction_from_state(path, ob, state, end, minor_unit)
        found.setdefault(subject_key, []).append((end, value))
    return {subject: tuple(sorted(items)) for subject, items in sorted(found.items())}


def _in_force(fixed: Sequence[AllocationSegment], at: date) -> AllocationSegment | None:
    """The last ``FIXED`` segment in fold order effective on or before ``at``."""
    found = None
    for seg in fixed:
        if seg.effective_date <= at:
            found = seg
    return found


def _contract_of(st: AllocatedState, ob: ObligationState) -> ContractView:
    return next(view for view in st.contracts if view.header.external_id == ob.contract_key)


def _cancelled_on(ob: ObligationState, fixed: Sequence[AllocationSegment]) -> date | None:
    """The cancellation boundary of ``ob``: ``terminated_on`` or its first ``TERMINATION`` segment
    (S09-R-46), whichever is earlier; None while it is never cancelled."""
    dates_found = [seg.effective_date for seg in fixed if seg.cause == SegmentCause.TERMINATION]
    if ob.terminated_on is not None:
        dates_found.append(ob.terminated_on)
    return min(dates_found, default=None)


@dataclass(frozen=True, slots=True)
class _Basis:
    """The status and 25-7 attribution of one contract for the dated RPO measurements (D-91)."""

    ctx: BookContext
    contract: ContractView
    attribution: DepositAttribution | None
    minor_unit: int

    def status_at(self, at: date) -> str | None:
        history = self.contract.status_in_book.get(str(self.ctx.book_code), ())
        found: str | None = None
        for when, status in history:
            if when > at:
                break
            found = status
        return found

    def excluded(self, at: date) -> bool:
        """D-91 gaps (vii): a Step 1 failure has no remaining performance obligations."""
        return self.status_at(at) == NOT_A_CONTRACT

    def entered(self, before: date, end: date) -> date | None:
        """The first date in (``before``, ``end``] at which the status stops being
        ``NOT_A_CONTRACT`` after being so at ``before`` or earlier inside the period (a contract
        booked NOT_A_CONTRACT inside the period whose criteria are met later in it enters once,
        at that date; secondary review item 4); None otherwise."""
        was_excluded = self.excluded(before)
        history = self.contract.status_in_book.get(str(self.ctx.book_code), ())
        for when, status in history:
            if not before < when <= end:
                continue
            if status == NOT_A_CONTRACT:
                was_excluded = True
            elif was_excluded:
                return when
        return None

    def outside(self, on: date) -> bool:
        """Whether a segment boundary on ``on`` falls while the contract is outside RPO: excluded
        on the boundary date or the day before, or entered the book as ``NOT_A_CONTRACT`` on that
        date (the segment then replaces a state that was never in RPO, or leaves RPO with it; the
        entry of the period is ``entered``)."""
        if self.excluded(on) or self.excluded(on - timedelta(days=1)):
            return True
        history = self.contract.status_in_book.get(str(self.ctx.book_code), ())
        return any(when == on and status == NOT_A_CONTRACT for when, status in history)

    def r25(self, subject_key: str, at: date) -> int:
        """The 606-10-25-7 revenue attributed to the obligation through ``at`` (S14-R-25)."""
        if self.attribution is None or subject_key not in self.attribution.keys:
            return 0
        value, _ = deposit_share(self.attribution, subject_key, at, self.minor_unit)
        return value


def _rpo_at(
    ob: ObligationState,
    fixed: Sequence[AllocationSegment],
    revenue: Sequence[tuple[date, int]],
    realised: Sequence[tuple[date, int]],
    reductions: Sequence[tuple[date, int]],
    at: date,
    basis: _Basis,
    *,
    status: bool = True,
) -> tuple[bool, int]:
    """(included, RPO before exemptions) of ``ob`` at ``at``: the S15-R-08 measurement A(at) −
    ρ(at) − R(at) − R25(at) on the published performing-entity period-end states (S15-R-12 basis;
    D-91), 0 and excluded while the contract is ``NOT_A_CONTRACT`` in the book (gaps (vii)) unless
    ``status`` is false, and floored at 0 where the 25-7 revenue attributed exceeds the remainder.
    """
    in_force = _in_force(fixed, at)
    if in_force is None or in_force.cause == SegmentCause.TERMINATION:
        return False, 0
    if ob.terminated_on is not None and ob.terminated_on <= at:
        return False, 0
    if status and basis.excluded(at):
        return False, 0
    remaining = (
        in_force.a_posted
        + _revenue_at(realised, at)
        - _revenue_at(reductions, at)
        - _revenue_at(revenue, at)
    )
    return True, max(remaining - basis.r25(ob.subject_key, at), 0)


def _movements(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    fixed: Sequence[AllocationSegment],
    revenue: Sequence[tuple[date, int]],
    realised: Sequence[tuple[date, int]],
    reduced: Sequence[tuple[date, int]],
    before: date,
    end: date,
    open_in: bool,
    close_in: bool,
    lines: dict[str, int],
    basis: _Basis,
    entered: date | None = None,
) -> None:
    """The movement lines of one obligation over (``before``, ``end``] (S15-R-12; D-91).

    A segment's cause line takes the movement of the returns-adjusted allocation at its boundary,
    ρ measured on the boundary date (and the day before for the segment it replaces); the movement
    of ρ between boundaries goes to ``VC_ESTIMATE_CHANGES`` with sign −Δρ; ``REVENUE`` is the
    movement of the stage 09 targets; ``CANCELLATIONS`` takes the returns-adjusted remainder, net
    of the 25-7 revenue attributed (D-91 (v); D1-R03), when the obligation stops being included.

    A boundary while the contract is ``NOT_A_CONTRACT`` in the book, on the boundary date or the
    day before, is outside RPO and emits nothing (D-91 (vii); D1-R02): a contract that enters
    inside the period is the caller's ``NEW_CONTRACTS`` entry (``entered``), and one that never
    enters reports no activity. An obligation that entered inside the period and is excluded
    again at its end exits through ``CANCELLATIONS`` like one included at the opening (secondary
    review item 1), so the period reconciles.
    """
    rho_before = 0 if _in_force(fixed, before) is None else _revenue_at(reduced, before)
    rho_end = 0 if _in_force(fixed, end) is None else _revenue_at(reduced, end)
    boundary_rho = 0
    moved = False
    previous: AllocationSegment | None = None
    contract: ContractView | None = None
    for seg in fixed:
        if before < seg.effective_date <= end and not basis.outside(seg.effective_date):
            if contract is None:
                contract = _contract_of(st, ob)
            rho_after = returns.reduction(ctx, st, contract, ob, seg, seg.effective_date)
            rho_prior = 0
            if previous is not None:
                day_before = seg.effective_date - timedelta(days=1)
                rho_prior = returns.reduction(ctx, st, contract, ob, previous, day_before)
            prior = 0 if previous is None else previous.a_posted - rho_prior
            lines[CAUSE_LINES[str(seg.cause)]] += (seg.a_posted - rho_after) - prior
            boundary_rho += rho_after - rho_prior
            moved = True
        previous = seg
    lines["VC_ESTIMATE_CHANGES"] -= (rho_end - rho_before) - boundary_rho
    realised_end = _revenue_at(realised, end)
    if open_in or close_in or moved or entered is not None:
        # Entry already includes the allocation realized through its own cut. Only later
        # realizations are additions; an entirely excluded contract has no RPO activity.
        realised_start = _revenue_at(realised, before if entered is None else entered)
        lines["VC_ESTIMATE_CHANGES"] += realised_end - realised_start
    lines["REVENUE"] = -(_revenue_at(revenue, end) - _revenue_at(revenue, before))
    if not close_in and (open_in or moved or entered is not None):
        in_force = _in_force(fixed, end)
        left = (
            (0 if in_force is None else in_force.a_posted - rho_end)
            + realised_end
            - _revenue_at(revenue, end)
        )
        r25 = basis.r25(ob.subject_key, end)
        # The remainder nets the 25-7 revenue attributed, floored as the dated measurements are
        # (`_rpo_at`); without a 25-7 recognition the expression is the S15-R-12 one unchanged.
        lines["CANCELLATIONS"] -= left if r25 == 0 else max(left - r25, 0)


def _row(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    m: ObligationMeasures,
    targets: Sequence[tuple[date, int]],
    short: frozenset[str],
    tb: TraceBuilder,
    minor_unit: int,
    attribution: DepositAttribution | None = None,
) -> RpoRow:
    status = str(m.satisfaction_status)
    contract_basis = _Basis(ctx, _contract_of(st, ob), attribution, minor_unit)
    # D-91 gaps (vii): the obligations of a contract that is NOT_A_CONTRACT in the book at d_v
    # contribute nothing (606-10-50-13); the row records the exclusion.
    not_a_contract = contract_basis.excluded(m.as_of)
    included = status in INCLUDED and not not_a_contract
    scheduled = m.scheduled_amount if included else 0
    awaiting = m.awaiting_trigger_amount if included else 0
    inputs: list[str | SourceRef] = [
        _measure_input(m, "scheduled_amount", m.scheduled_amount, minor_unit),
        _measure_input(m, "awaiting_trigger_amount", m.awaiting_trigger_amount, minor_unit),
    ]
    params = {
        "included": "true" if included else "false",
        "kind": "obligation",
        "minor_unit": str(minor_unit),
        "satisfaction_status": status,
    }
    if not_a_contract:
        params["excluded"] = NOT_A_CONTRACT
    r25 = 0
    if included and attribution is not None and ob.subject_key in attribution.keys:
        # S14-R-25 (D-91 gaps (v)): the 25-7 revenue attributed to the obligation is recognised
        # revenue, so the remainder nets it (floored at 0); the share node at d_v is the input.
        r25 = contract_basis.r25(ob.subject_key, m.as_of)
        inputs.append(deposit_share_node_id(ob.subject_key, None))
        params["r25"] = str(r25)
    total = max(scheduled + awaiting - r25, 0) if included else 0
    if included and r25 > 0:
        # Keep S15-INV-02 (Σ bands = total): scale the placed amounts below through ``placed``.
        deducted = scheduled + awaiting - total
        if deducted >= awaiting:
            deducted -= awaiting
            awaiting = 0
            scheduled -= deducted
        else:
            awaiting -= deducted
    rpo_node = tb.node(
        measure="rpo_amount",
        subject_key=ob.subject_key,
        period_key=None,
        value=total,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=_RPO,
        inputs=inputs,
        params=params,
        narrative_key="disc.rpo",
    )
    entity = ob.contracting_entity
    period = period_of(ctx, entity, m.as_of)
    bounds = tuple(
        dates.add_months(m.as_of, months) for months in _band_months(ctx, entity, period)
    )
    placed = [0] * (len(bounds) + 1)
    if included:
        running = m.revenue_cum
        for end, value in targets:
            if end <= m.as_of:
                continue
            placed[band_index(end, bounds)] += value - running
            running = value
        unscheduled = scheduled - sum(placed)
        if unscheduled:
            placed[band_index(ob.end_date or m.as_of, bounds)] += unscheduled
        placed[band_index(ob.end_date or m.as_of, bounds)] += awaiting
    exemptions: list[Exemption] = []
    excluded_nodes: list[str | SourceRef] = []
    excluded = 0
    wholly_unsatisfied = status == UNSATISFIED and m.revenue_cum == 0
    for policy, code, basis, description, cap, omitted in _omissions(
        ctx, st, ob, total, wholly_unsatisfied, short, period, m.as_of
    ):
        params = {"basis": basis, "minor_unit": str(minor_unit), "policy": policy}
        if basis == AMOUNT:
            params["amount"] = str(cap)
        if policy == "POL-200":  # S15-R-09 (rev 1.7; D-91): the quota in force at d_v
            params["quota_as_of"] = m.as_of.isoformat()
            params["quota_nodes"] = "|".join(_quota_nodes(st, ob, m.as_of))
        node_id = tb.node(
            measure="rpo_excluded",
            subject_key=f"{ob.subject_key}/{policy}",
            period_key=None,
            value=omitted,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=_EXEMPTION,
            inputs=[rpo_node, *excluded_nodes],
            params=params,
            narrative_key="disc.rpo_exemption",
        )
        excluded += omitted
        excluded_nodes.append(node_id)
        exemptions.append(
            Exemption(
                policy=policy,
                code=code,
                subject_key=ob.subject_key,
                amount=omitted,
                nature=f"{ob.recognition_method} {ob.obligation_kind}",
                product_code=ob.product_code,
                end_date=ob.end_date,
                remaining_months=0
                if ob.end_date is None
                else dates.month_ends_between(m.as_of, ob.end_date),
                description=description,
                node_id=node_id,
            )
        )
    bands = tuple(rpo_bands(total - excluded, placed)) if included else tuple(placed)
    nodes = {"rpo_amount": rpo_node}
    if included:
        for index, amount in enumerate(bands):
            nodes[f"rpo_band/{index}"] = tb.node(
                measure="rpo_band",
                subject_key=f"{ob.subject_key}/{index}",
                period_key=None,
                value=amount,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=_BAND,
                inputs=[rpo_node, *excluded_nodes],
                params={
                    "bounds": "|".join(bound.isoformat() for bound in bounds),
                    "index": str(index),
                    "minor_unit": str(minor_unit),
                    "placed": "|".join(str(amount) for amount in placed),
                },
                narrative_key="disc.rpo_band",
            )
    return RpoRow(
        subject_key=ob.subject_key,
        contract_key=ob.contract_key,
        as_of=m.as_of,
        included=included,
        scheduled=scheduled,
        awaiting=awaiting,
        total=total,
        excluded=excluded,
        bounds=bounds,
        placed=tuple(placed),
        bands=bands,
        exemptions=tuple(exemptions),
        trace_nodes=MappingProxyType(dict(sorted(nodes.items()))),
    )


def _measure_input(
    m: ObligationMeasures, name: str, amount: int, minor_unit: int
) -> str | SourceRef:
    """The stage 09 version-date node of ``name``, else a source reference with its value."""
    found = m.trace_nodes.get(name)
    if found is not None:
        return found
    ref_id = f"{m.subject_key}#{name}"
    return SourceRef("source_record", ref_id, {"value": format_money(amount, minor_unit)})


def _omissions(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    total: int,
    wholly_unsatisfied: bool,
    short: frozenset[str],
    period: str,
    at: date,
) -> tuple[tuple[str, str, str, str, int, int], ...]:
    """(POL id, code, basis, description, cap, omitted) of every expedient that reaches ``ob``,
    read at ``period`` of its contracting entity with the targeted quota in force at ``at``, in
    application order (S15-R-09)."""
    found: list[tuple[str, str, str, str, int, int]] = []
    excluded = 0
    for policy, code, basis, description in EXEMPTIONS:
        if ctx.policies.value(code, entity=ob.contracting_entity, period=period) != APPLY:
            continue
        cap = _exemption_cap(policy, st, ob, wholly_unsatisfied, short, at)
        if cap is None:
            continue
        remaining = total - excluded
        if basis == ALL:
            omitted = remaining
        else:
            omitted = min(remaining, cap) if remaining > 0 else 0
        excluded += omitted
        found.append((policy, code, basis, description, cap, omitted))
    return tuple(found)


def _excluded(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    total: int,
    wholly_unsatisfied: bool,
    short: frozenset[str],
    period: str,
    at: date,
) -> int:
    """Σ amounts the expedients omit from an RPO of ``total`` at ``at`` (S15-R-09)."""
    found = _omissions(ctx, st, ob, total, wholly_unsatisfied, short, period, at)
    return sum(item[5] for item in found)


def _quota_in_force(history: Sequence[tuple[date, Quota]], at: date) -> Quota | None:
    """The last dated quota effective on or before ``at`` (ENG-06 order), else None."""
    found: Quota | None = None
    for effective, quota in history:
        if effective <= at:
            found = quota
    return found


def _exemption_cap(
    policy: str,
    st: AllocatedState,
    ob: ObligationState,
    wholly_unsatisfied: bool,
    short: frozenset[str],
    at: date,
) -> int | None:
    """None when the expedient does not reach the obligation; else the most it may omit.

    POL-200 (S15-R-09 rev 1.7; D-91): max(0, Σ a_posted of the targeted quotas in force at ``at``)
    from ``targeted_vc_quota_history``; a negative quota exempts nothing (50-14A(b)); None when no
    quota reaches the obligation by ``at``.
    """
    if policy == "POL-197":
        return 0 if ob.contract_key in short else None
    if policy == "POL-198":
        return 0 if str(ob.recognition_method) == RIGHT_TO_INVOICE else None
    if policy == "POL-199":
        return 0 if any(seg.component == ROYALTY for seg in ob.segments) else None
    if not wholly_unsatisfied:
        return None
    quotas = [
        quota
        for _, members in sorted(st.targeted_vc_quota_history.items())
        if (quota := _quota_in_force(members.get(ob.subject_key, ()), at)) is not None
    ]
    if not quotas:
        return None
    return max(0, sum(quota.a_posted for quota in quotas))


def _quota_nodes(st: AllocatedState, ob: ObligationState, at: date) -> list[str]:
    """The nodes composing the targeted quotas of ``ob`` in force at ``at`` (§15.5 ``quota_nodes``):
    the stage 05 ``targeted_vc_allocated`` node of each element seeded at inception and the stage
    08 ``tp_share`` node of each of its reallocating versions effective on or before ``at``."""
    events = {item.order_key: item for item in st.events}
    found: list[str] = []
    for estimate_key, members in sorted(st.targeted_vc_quota_history.items()):
        history = members.get(ob.subject_key, ())
        if not history or history[0][0] > at:
            continue
        if history[0][0] == st.inception_date:
            found.append(f"targeted_vc_allocated@{encode_key(estimate_key)}:{ob.subject_key}:-")
        for pin in st.estimates.pins.get(estimate_key, ()):
            ev = events.get(pin.event_order_key)
            if ev is None or ev.effective_date > at or ev.effective_date <= st.inception_date:
                continue
            if any(seg.event_key == ev.event_key for seg in ob.segments):
                found.append(f"tp_share@{ev.event_key}:{ob.subject_key}:-")
    return found


def _short_contracts(st: AllocatedState) -> frozenset[str]:
    """POL-197: contracts whose inception segments end within 12 months of inception."""
    found: set[str] = set()
    for view in st.contracts:
        header = view.header
        ends = [
            ob.segments[0].totals.end_date
            for ob in st.obligations
            if ob.contract_key == header.external_id
            and ob.segments
            and ob.segments[0].cause == SegmentCause.INCEPTION
            and ob.segments[0].totals.end_date is not None
        ]
        latest = max((end for end in ends if end is not None), default=header.inception_date)
        if latest < dates.add_months(header.inception_date, ONE_YEAR_MONTHS):
            found.add(header.external_id)
    return frozenset(found)


def _band_months(ctx: BookContext, entity: str, period: str) -> tuple[int, ...]:
    """POL-201 month boundaries: positive integers in ascending order."""
    value = ctx.policies.value(BANDS_CODE, entity=entity, period=period)
    items: Sequence[str]
    if isinstance(value, str):
        items = [item.strip() for item in value.strip("[]").split(",") if item.strip()]
    elif isinstance(value, tuple):
        items = value
    else:
        raise ValueError(f"{BANDS_CODE} holds a list of month boundaries (POL-201)")
    months: list[int] = []
    for item in items:
        if not item.isdigit() or int(item) < 1:
            raise ValueError(f"{BANDS_CODE} boundaries are positive integers (POL-201)")
        months.append(int(item))
    if months != sorted(set(months)):
        raise ValueError(f"{BANDS_CODE} boundaries ascend without repeats (POL-201)")
    return tuple(months)
