"""Stage 04 significant financing component: gap test, rate, cash selling price and accretion.

ENGINE_SPEC S04-R-10 to S04-R-13 with S04-R-12a (rev 1.3); §4.4 S04-INV-04 (financed balance),
findings ``SFC_REVIEW_REQUIRED``, ``SFC_RATE_MISSING``, ``SFC_SCHEDULE_UNSETTLED``, trace nodes
``cash_selling_price:<ob>:-`` and ``financing_interest_cum:<contract>@<entity>:<period>`` (params
``suspended_until``); formulas ``sfc.gap_test.v1``, ``sfc.cash_selling_price.v1``,
``sfc.effective_interest.monthly.v1``, ``sfc.effective_interest.annual.v1``, ``sfc.accretion.v1``;
POLICIES POL-046, POL-047 notes, JET-11 (CHK-136, CHK-137, FASB Example 26); 05 §3.6.3 (EMOD-18);
ADJUDICATION.md B3-AK-01, R-SFC-04, R-SFC-05; S04-R-10a and the advance CSP over revenue shares
(D-87 L5-3-Q-8). Compounding uses integer powers of rational rates only (CV-31). Private to stage
04. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine import billing_identity, dates, progress
from erev_engine.bundle import JudgementInput, PeriodInput
from erev_engine.enums import RecognitionMethod, SatisfactionPattern
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.money import (
    cumulative_posted,
    format_exact,
    largest_remainder,
    round_half_up,
    to_fraction,
)
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    contract_subject_key,
    obligation_subject_key,
    payload_date,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.s03_pob_builder import PobDraft, PobState
from erev_engine.stages.s04_transaction_price import returns, specialist
from erev_engine.stages.state import (
    BILLING_MODE_ENGINE,
    BookContext,
    EventView,
    Finding,
    Quota1,
    Target,
    billing_mode_at,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ACCRETION_FORMULA",
    "ADVANCE",
    "ANNUAL",
    "ANNUAL_FORMULA",
    "BALANCE",
    "CSP_FORMULA",
    "DEFERRED",
    "GAP_FORMULA",
    "INTEREST",
    "MONTHLY",
    "MONTHLY_FORMULA",
    "Adjustment",
    "Assessment",
    "Month",
    "Payment",
    "Rate",
    "Schedule",
    "emit",
    "findings",
    "measure",
    "targets",
]

GAP_FORMULA: Final = "sfc.gap_test.v1"
CSP_FORMULA: Final = "sfc.cash_selling_price.v1"
MONTHLY_FORMULA: Final = "sfc.effective_interest.monthly.v1"
ANNUAL_FORMULA: Final = "sfc.effective_interest.annual.v1"
ACCRETION_FORMULA: Final = "sfc.accretion.v1"
BUILDUP_FORMULA: Final = "tp.buildup.v1"
EXPEDIENT: Final = "sfc.one_year_expedient"  # POL-046
RATE_POLICY: Final = "sfc.discount_rate_basis"  # POL-047
APPLY: Final = "APPLY"
MONTHLY: Final = "MONTHLY"
ANNUAL: Final = "ANNUAL"
DEFERRED: Final = "DEFERRED"
ADVANCE: Final = "ADVANCE"
TOPIC: Final = "SFC_ASSESSMENT"
MEMBER: Final = "payment_schedule"
INTEREST: Final = "financing_interest_cum"
BALANCE: Final = "financed_balance"
GAP: Final = "financing_gap_test"
CSP: Final = "cash_selling_price"
# S04-R-10 outcomes recorded as trace param ``reason`` of the gap-test node.
NO_PAYMENT_SCHEDULE: Final = "NO_PAYMENT_SCHEDULE"
WITHIN_ONE_YEAR: Final = "WITHIN_ONE_YEAR"
NOT_SIGNIFICANT: Final = "NOT_SIGNIFICANT"
EXCEPTION_32_17: Final = "EXCEPTION_32_17"
SIGNIFICANT_GAP: Final = "SIGNIFICANT_GAP"
EXPEDIENT_NOT_APPLIED: Final = "EXPEDIENT_NOT_APPLIED"
OPEN: Final = "OPEN"  # S04-R-12a: the revenue target is not yet positive at the horizon
JUDGEMENT_SIGNIFICANT: Final = "JUDGEMENT_SIGNIFICANT"  # S04-R-10a (D-87 L5-3-Q-8)
_RECEIPTS: Final = "PAYMENT_RECEIVED"  # S04-R-10a payment_source
_BILLING: Final = "BILLING_RECORDED"  # S04-R-10a payment_source
_CREDIT_MEMO: Final = "CREDIT_MEMO_RECORDED"
# D-97 (15): a credit memo against a still-memo-only ENGINE line fails closed (04 table 15.4-B).
_CREDIT_ON_MEMO_ONLY: Final = "CREDIT_MEMO_ON_MEMO_ONLY_LINE"
_DELIVERY: Final = "DELIVERY_RECORDED"
_TIME_POLICY: Final = "recognition.time_convention"  # POL-090 (S09-R-08)
_EXCEPTIONS: Final = frozenset({"A", "B", "C"})
_OVERRIDE_LEVELS: Final = frozenset({"C", "O"})
_TRANSFER_EVENTS: Final = frozenset({"DELIVERY_RECORDED", "RETURN_RECORDED"})
_STAGE: Final = 4


@dataclass(frozen=True, slots=True)
class Assessment:
    """S04-R-10 for one fixed-consideration obligation."""

    obligation: PobDraft
    transfer: Fraction  # T_p as an ordinal day number; an over-time midpoint may end in 1/2
    weighted: Fraction | None  # W as an ordinal day number; None without a payment schedule
    significant: bool  # W < ordinal(T_p − 12 months) or W > ordinal(T_p + 12 months)
    judgement: JudgementInput | None  # the governing reviewed SFC_ASSESSMENT record
    reason: str
    adjust: bool  # an adjustment applies
    review_required: bool  # SFC_REVIEW_REQUIRED
    payment_source: str | None = None  # S04-R-10a: PAYMENT_RECEIVED | BILLING_RECORDED
    transfer_open: bool = False  # S04-R-10a: a point-in-time transfer not yet reached
    # S04-R-10a (D-91 C606-05): the derived points and the status updates that added none.
    payment_points: tuple[tuple[date, Fraction], ...] = ()
    status_updates_ignored: tuple[str, ...] = ()
    # D-91 05g: ENGINE-mode cancellable lines with no S10-R-06 date at the position (no point).
    memo_only_lines: tuple[str, ...] = ()
    # D-97 (15): credit memos naming an invoice whose lines are still memo-only (fail closed).
    credit_memos_on_memo_only: tuple[MemoOnlyCredit, ...] = ()
    # D-97 (5) v2: the kept lines that entered a point before netting (boundary (iii)).
    eligible_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MemoOnlyCredit:
    """A ``CREDIT_MEMO_RECORDED`` against an invoice ANY of whose kept lines is still memo-only at
    the position, or dated before that invoice's earliest S10-R-06 date (D-97 (15) v3: a later
    status update alone is not sufficient remediation for a memo dated before it): it enters no
    point; ``findings`` raises ``CREDIT_MEMO_ON_MEMO_ONLY_LINE`` (``ERROR``, CV-15) until the
    memo-with-its-document netting is built."""

    event_key: str
    credit_memo_number: str
    credited_invoice_number: str
    memo_only_lines: tuple[str, ...]  # the memo-only kept lines of the credited invoice


@dataclass(frozen=True, slots=True)
class Rate:
    """The approved contract-level POL-047 override (S04-R-11)."""

    basis: str
    annual_rate: Fraction
    compounding: str  # MONTHLY | ANNUAL
    periodic: Fraction  # j = annual_rate ÷ 12 (MONTHLY) or i = annual_rate (ANNUAL)
    source_ref: str


@dataclass(frozen=True, slots=True)
class Payment:
    """One payment point on the S04-R-12 grid."""

    on: date
    amount: Fraction
    months: int  # m(T, date) for a deferred payment, m(date, T) for an advance
    count: int  # n_i: the months (MONTHLY) or ⌊months ÷ 12⌋ whole years (ANNUAL)
    step: int  # the grid month at whose end the payment enters the balance (0 = opening)
    # S04-R-10a (D-91): the event the point is derived from (the line, receipt or credit memo
    # first dated on it); None for a payment-schedule point, which cites the schedule's source.
    source_event_key: str | None = None


@dataclass(frozen=True, slots=True)
class Month:
    """One month end of the accretion schedule (S04-R-12)."""

    end: date  # e_m
    interest: Fraction  # w_m, exact
    balance: Fraction  # exact balance B_m after the payments of the step


@dataclass(frozen=True, slots=True)
class Schedule:
    """The effective-interest schedule of one contract (S04-R-12, S04-R-13)."""

    contract_key: str
    entity: str  # the contracting entity (JET-11 owner)
    subject_key: str  # <contract>@<entity> (CV-21)
    obligations: tuple[PobDraft, ...]  # the obligations S04-R-10 adjusts
    kind: str  # DEFERRED | ADVANCE
    transfer: date  # T
    start: date  # the grid origin: T (deferred) or the first payment date (advance)
    rate: Rate
    payments: tuple[Payment, ...]  # ascending date
    total: Fraction  # Σ payments
    csp: Fraction  # exact cash selling price (deferred) or accreted balance at T (advance)
    adjustment: int  # round(csp) − Σ payments, minor units
    opening: Fraction  # B_0
    months: tuple[Month, ...]
    source_event_key: str | None  # the booking or amendment carrying the payment schedule
    shares: tuple[tuple[int, Fraction], ...] = ()  # D-87 L5-3-Q-8: (grid step k, g_k) relieved
    transfer_open: bool = False  # S04-R-10a: accretion with no relief and no CSP


@dataclass(frozen=True, slots=True)
class Adjustment:
    """The financing member of a build-up at a position (S04-R-10 to S04-R-12)."""

    assessments: tuple[Assessment, ...]
    schedules: tuple[Schedule, ...]  # contract key
    missing_rate: tuple[tuple[str, tuple[PobDraft, ...]], ...]  # SFC_RATE_MISSING per contract
    exact: Fraction  # Σ adjustment, currency units


def measure(
    ctx: BookContext,
    st: PobState,
    at: date,
    before: EventView | None,
    lines: Sequence[PobDraft],
) -> Adjustment:
    """S04-R-10 to S04-R-12 for the fixed-consideration obligations ``lines`` at a position.

    Per member contract, the payment schedule in force (S01-R-20) gives W; each obligation is
    tested against its transfer date. The obligations that need an adjustment share the contract's
    schedule, discounted or accreted at the POL-047 rate; without a rate the contract is recorded
    for ``SFC_RATE_MISSING`` and contributes nothing. The member is Σ round(CSP) − Σ payments.
    """
    scale: int = 10 ** ctx.currencies[ctx.txn_currency].minor_unit
    assessments: list[Assessment] = []
    schedules: list[Schedule] = []
    missing: list[tuple[str, tuple[PobDraft, ...]]] = []
    for contract_key in st.identified.member_contract_keys:
        own = [ob for ob in lines if ob.contract_key == contract_key]
        if not own:
            continue
        points, source = _points(st, contract_key, at, before)
        weighted = _weighted(points)
        tested = [_assess(ctx, st, ob, weighted) for ob in own]
        point_sources: Mapping[date, str] = {}
        if not points:  # S04-R-10a (D-87 L5-3-Q-8)
            derived = _judged_points(ctx, st, contract_key, before)
            derived_weighted = _weighted(derived.points)
            judged = [
                _assess_judged(st, item, derived_weighted, derived, before) for item in tested
            ]
            if any(item.reason == JUDGEMENT_SIGNIFICANT for item in judged):
                points, weighted, tested = derived.points, derived_weighted, judged
                point_sources = derived.sources
        assessments.extend(tested)
        adjusted = tuple(item for item in tested if item.adjust)
        if not adjusted or weighted is None:
            continue
        rate = _rate(ctx, st, contract_key)
        if rate is None:
            missing.append((contract_key, tuple(item.obligation for item in adjusted)))
            continue
        schedules.append(
            _schedule(
                ctx, st, contract_key, adjusted, points, weighted, rate, source, point_sources
            )
        )
    exact = sum((Fraction(item.adjustment, scale) for item in schedules), Fraction(0))
    return Adjustment(tuple(assessments), tuple(schedules), tuple(missing), exact)


def findings(ctx: BookContext, st: PobState, adjustment: Adjustment) -> tuple[Finding, ...]:
    """``SFC_REVIEW_REQUIRED``, ``SFC_RATE_MISSING`` and ``SFC_SCHEDULE_UNSETTLED`` (``ERROR``)."""
    found: list[Finding] = []
    for item in adjustment.assessments:
        if not item.review_required:
            continue
        ob = item.obligation
        detail = {
            "obligation_key": ob.obligation_key,
            "reason": item.reason,
            "rule": "S04-R-10",
            "transfer_ordinal": format_exact(item.transfer),
        }
        if item.weighted is not None:
            detail["weighted_payment_ordinal"] = format_exact(item.weighted)
        if item.payment_source is not None:  # S04-R-10a, D-91 05g: no eligible payment point
            detail["payment_source"] = item.payment_source
            detail["memo_only_lines"] = "|".join(item.memo_only_lines)
        found.append(Finding("SFC_REVIEW_REQUIRED", "ERROR", ob.subject_key, detail, _STAGE, None))
    raised: set[str] = (
        set()
    )  # D-97 (15): one finding per credit memo, whatever the obligation count
    for item in adjustment.assessments:
        if item.payment_source is None:
            continue
        for credit in item.credit_memos_on_memo_only:
            if credit.event_key in raised:
                continue
            raised.add(credit.event_key)
            found.append(
                Finding(
                    _CREDIT_ON_MEMO_ONLY,
                    "ERROR",
                    item.obligation.subject_key,
                    {
                        "obligation_key": item.obligation.obligation_key,
                        "credit_memo_number": credit.credit_memo_number,
                        "credited_invoice_number": credit.credited_invoice_number,
                        "memo_only_lines": "|".join(credit.memo_only_lines),
                        "rule": "S04-R-10a",
                    },
                    _STAGE,
                    credit.event_key,
                )
            )
    for contract_key, obligations in adjustment.missing_rate:
        detail = {
            "obligation_keys": ",".join(ob.obligation_key for ob in obligations),
            "policy": RATE_POLICY,
            "rule": "S04-R-11",
        }
        found.append(Finding("SFC_RATE_MISSING", "ERROR", contract_key, detail, _STAGE, None))
    for schedule in adjustment.schedules:
        unsettled = _unsettled(ctx, st, schedule)
        if unsettled is not None:
            found.append(unsettled)
    return tuple(sorted(found, key=Finding.sort_key))


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    measure_name: str,
    subject_key: str,
    quota: Quota1,
    adjustment: Adjustment,
    suffix: str,
) -> str:
    """Gap-test nodes per obligation, ``cash_selling_price:<ob>:-`` per adjusted obligation and the
    ``financing_adjustment_amount`` node (§4.4); the id of the last."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    for item in adjustment.assessments:
        _emit_gap(tb, item, suffix)
    parts: list[tuple[str | SourceRef, str]] = []
    for schedule in adjustment.schedules:
        if schedule.transfer_open:  # S04-R-10a: no CSP is published while the transfer is open
            continue
        for node_id in _emit_csp(ctx, tb, schedule, suffix):
            parts.append((node_id, "+"))
        source = SourceRef(
            "contract_event",
            schedule.source_event_key or schedule.contract_key,
            {"value": format_exact(schedule.total)},
        )
        parts.append((source, "-"))
    return tb.node(
        measure=measure_name,
        subject_key=subject_key,
        period_key=None,
        value=quota.posted,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=BUILDUP_FORMULA,
        inputs=[item for item, _ in parts],
        params={"signs": ",".join(sign for _, sign in parts)},
        exact=quota.exact,
        narrative_key=BUILDUP_FORMULA.rsplit(".v", 1)[0],
    )


def targets(
    ctx: BookContext, st: PobState, adjustment: Adjustment, tb: TraceBuilder
) -> tuple[Target, ...]:
    """S04-R-13: ``financing_interest_cum`` and ``financed_balance`` per schedule and period end of
    the contracting entity, from the grid origin through the horizon (JET-11a deferred, JET-11b
    advance; cause ``DEFERRED`` or ``ADVANCE``). A deferred schedule follows S04-R-12a while
    expected returns exclude the whole consideration."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    found: list[Target] = []
    for schedule in adjustment.schedules:
        suspended, until = _suspension(ctx, st, schedule)
        x_int = Fraction(-schedule.adjustment, scale)
        remaining = sum(
            (m.interest for m in schedule.months if until is not None and m.end > until),
            Fraction(0),
        )
        formula = MONTHLY_FORMULA if schedule.rate.compounding == MONTHLY else ANNUAL_FORMULA
        rate_source = SourceRef(
            "policy_override",
            schedule.rate.source_ref,
            {"value": format_exact(schedule.rate.annual_rate)},
        )
        for period in specialist.periods(ctx, schedule.entity, schedule.start):
            t = period.end_date
            elapsed = [m for m in schedule.months if m.end <= t]
            params = {
                "annual_rate": format_exact(schedule.rate.annual_rate),
                "cash_selling_price": format_exact(schedule.csp),
                "compounding": schedule.rate.compounding,
                "kind": schedule.kind,
                "months": str(len(elapsed)),
                "opening": format_exact(schedule.opening),
                "payments": _payments_param(schedule),
            }
            params.update(_level_params(schedule))
            if not suspended:
                exact = sum((m.interest for m in elapsed), Fraction(0))
                posted = round_half_up(exact, minor_unit)
            else:
                params["suspended_until"] = OPEN if until is None else until.isoformat()
                params["suspended_interest"] = format_exact(x_int)
                if until is None or t <= until:
                    weight = Fraction(0)
                elif remaining == 0:
                    weight = Fraction(1)
                else:
                    later = sum((m.interest for m in elapsed if m.end > until), Fraction(0))
                    weight = later / remaining
                params["weight"] = format_exact(weight)
                exact = x_int * weight
                posted = cumulative_posted(x_int, -schedule.adjustment, weight, minor_unit)
            source = SourceRef(
                "contract_event",
                schedule.source_event_key or schedule.contract_key,
                {"value": format_exact(schedule.total)},
            )
            interest_id = tb.node(
                measure=INTEREST,
                subject_key=schedule.subject_key,
                period_key=period.period_key,
                value=posted,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=formula,
                inputs=[rate_source, source],
                params=params,
                exact=exact,
                narrative_key=formula.rsplit(".v", 1)[0],
            )
            balance, paid = _balance(schedule, t, exact if suspended else None)
            mode, step = _balance_mode(schedule, t, suspended)
            accretion = {
                "annual_rate": format_exact(schedule.rate.annual_rate),
                "cash_selling_price": format_exact(schedule.csp),
                "compounding": schedule.rate.compounding,
                "mode": mode,
                "months": str(step),
                "payments": _payments_param(schedule),
            }
            if mode == "suspended":
                accretion["recognised"] = format_exact(exact)
            accretion.update(_level_params(schedule))
            balance_id = tb.node(
                measure=BALANCE,
                subject_key=schedule.subject_key,
                period_key=period.period_key,
                value=round_half_up(balance, minor_unit),
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=ACCRETION_FORMULA,
                inputs=[
                    interest_id,
                    SourceRef(
                        "contract_event",
                        schedule.source_event_key or schedule.contract_key,
                        {"value": format_exact(paid)},
                    ),
                ],
                params={
                    **accretion,
                    "kind": schedule.kind,
                    "opening": format_exact(schedule.opening),
                    "signs": "+,-",
                },
                exact=balance,
                narrative_key=ACCRETION_FORMULA.rsplit(".v", 1)[0],
            )
            for measure_name, value, exact_value, node_id in (
                (INTEREST, posted, exact, interest_id),
                (BALANCE, round_half_up(balance, minor_unit), balance, balance_id),
            ):
                found.append(
                    Target(
                        book_code=ctx.book_code,
                        entity=schedule.entity,
                        subject_key=schedule.subject_key,
                        measure=measure_name,
                        period_key=period.period_key,
                        cause=schedule.kind,
                        value=value,
                        exact=exact_value,
                        node_id=node_id,
                    )
                )
    return tuple(found)


# --- S04-R-10 gap test ---------------------------------------------------------------------------


def _points(
    st: PobState, contract_key: str, at: date, before: EventView | None
) -> tuple[tuple[tuple[date, Fraction], ...], str | None]:
    """The payment schedule in force: the payload member, else the header projection."""
    value, source = specialist.in_force(st, contract_key, MEMBER, at, before)
    if value is None:
        header = st.identified.canonical.contracts[contract_key].header
        points = [(point.date, to_fraction(point.amount)) for point in header.payment_schedule]
        return tuple(sorted(points)), source
    if not isinstance(value, list | tuple):
        raise ValueError(f"{contract_key}: payment_schedule is not a list (CV-45)")
    found: list[tuple[date, Fraction]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{contract_key}: a payment point is not an object (CV-45)")
        on = payload_date(item, "date")
        amount = payload_fraction(item, "amount")
        if on is None or amount is None:
            raise ValueError(f"{contract_key}: a payment point needs date and amount (CV-45)")
        found.append((on, amount))
    return tuple(sorted(found)), source


def _weighted(points: Sequence[tuple[date, Fraction]]) -> Fraction | None:
    """W = Σ amount × ordinal(date) ÷ Σ amount; None for an empty or zero schedule."""
    total = sum((amount for _, amount in points), Fraction(0))
    if not points or total == 0:
        return None
    return sum((amount * on.toordinal() for on, amount in points), Fraction(0)) / total


def _assess(ctx: BookContext, st: PobState, ob: PobDraft, weighted: Fraction | None) -> Assessment:
    transfer = _transfer(st, ob)
    judgement = _judgement(ctx, st, ob)
    draft = specialist.latest_status(st, ob.contract_key) == "DRAFT"
    if weighted is None:
        review = _assessment_required(st, ob) and judgement is None and not draft
        return Assessment(ob, transfer, None, False, judgement, NO_PAYMENT_SCHEDULE, False, review)
    lower, upper = _bounds(transfer)
    significant = weighted < lower or weighted > upper
    expedient = ctx.policies.value(
        EXPEDIENT,
        contract=ob.contract_key,
        obligation=ob.subject_key,
        entity=ob.contracting_entity,
    )
    if expedient == APPLY and not significant:
        return Assessment(ob, transfer, weighted, False, judgement, WITHIN_ONE_YEAR, False, False)
    if judgement is not None and judgement.outcome.get("significant") == "false":
        return Assessment(
            ob, transfer, weighted, significant, judgement, NOT_SIGNIFICANT, False, False
        )
    if judgement is not None and judgement.outcome.get("exception_32_17") in _EXCEPTIONS:
        return Assessment(
            ob, transfer, weighted, significant, judgement, EXCEPTION_32_17, False, False
        )
    reason = SIGNIFICANT_GAP if significant else EXPEDIENT_NOT_APPLIED
    review = judgement is None and not draft
    return Assessment(ob, transfer, weighted, significant, judgement, reason, True, review)


def _transfer(st: PobState, ob: PobDraft) -> Fraction:
    """T_p: the exact midpoint of [start, end] (over time), else the line start date, else the
    booking date, as an ordinal day number."""
    start, end = ob.start_date, ob.end_date
    if ob.satisfaction_pattern == SatisfactionPattern.OVER_TIME and start and end:
        return Fraction(start.toordinal() + end.toordinal(), 2)
    if start is not None:
        return Fraction(start.toordinal())
    booked = next(
        (
            event.effective_date
            for event in st.identified.canonical.events
            if event.contract_key == ob.contract_key and event.event_type == "CONTRACT_BOOKED"
        ),
        st.identified.canonical.contracts[ob.contract_key].header.inception_date,
    )
    return Fraction(booked.toordinal())


def _bounds(transfer: Fraction) -> tuple[Fraction, Fraction]:
    """ordinal(T_p − 12 months) and ordinal(T_p + 12 months) with ``dates.add_months``."""
    whole = transfer.numerator // transfer.denominator
    part = transfer - whole
    day = date.fromordinal(whole)
    lower = Fraction(dates.add_months(day, -12).toordinal()) + part
    upper = Fraction(dates.add_months(day, 12).toordinal()) + part
    return lower, upper


def _judgement(ctx: BookContext, st: PobState, ob: PobDraft) -> JudgementInput | None:
    """The reviewed ``SFC_ASSESSMENT`` for the obligation, else the one with ``obligation_key``
    empty; of several, the greatest ``judgement_key`` (bundle order) governs."""
    header = st.identified.canonical.contracts[ob.contract_key].header
    contract = header.external_id
    subjects = {
        contract,
        contract_subject_key(contract),
        f"{contract}/{ob.obligation_key}",
        obligation_subject_key(contract, ob.obligation_key),
    }
    specific: JudgementInput | None = None
    general: JudgementInput | None = None
    for record in header.judgements:
        if record.topic != TOPIC or record.subject_key not in subjects:
            continue
        if record.book_code not in (None, ctx.book_code):
            continue
        named = record.outcome.get("obligation_key", "")
        if named == ob.obligation_key:
            specific = record
        elif named == "":
            general = record
    return specific if specific is not None else general


def _assessment_required(st: PobState, ob: PobDraft) -> bool:
    return any(
        version.version_key == ob.template_version_key and version.sfc_assessment_required
        for version in st.identified.canonical.templates.versions.get(ob.template_code, ())
    )


# --- S04-R-10a judged significant without a payment schedule (D-87 L5-3-Q-8) --------------------


@dataclass(frozen=True, slots=True)
class JudgedPoints:
    """The S04-R-10a payment points of one contract before a position (D-87 L5-3-Q-8; D-91)."""

    points: tuple[tuple[date, Fraction], ...]  # ascending date, net amounts, 0 dropped
    payment_source: str  # PAYMENT_RECEIVED | BILLING_RECORDED
    sources: Mapping[date, str]  # date -> the event key first dated on it (ENG-06 order)
    status_updates_ignored: tuple[str, ...]  # S10-R-07 status updates that added no point
    memo_only: tuple[str, ...] = ()  # D-91 05g: cancellable ENGINE lines with no S10-R-06 date
    credits_on_memo_only: tuple[MemoOnlyCredit, ...] = ()  # D-97 (15): fail closed, no point
    # D-97 (5) v2: the kept lines that entered a point, before netting (a netted-to-zero date is
    # dropped from ``points`` but its lines were eligible; boundary (iii)).
    eligible_lines: tuple[str, ...] = ()


def _judged_points(
    ctx: BookContext, st: PobState, contract_key: str, before: EventView | None
) -> JudgedPoints:
    """S04-R-10a payment points: (a) the contract's cash ``PAYMENT_RECEIVED`` receipts preceding
    ``before``, summed per the receipt event's effective date; else (b) its ``BILLING_RECORDED``
    lines recognised under S10-R-07 at contract scope (``billing_identity.iter_billing_lines``
    over ``CanonicalBundle.events``: the first-seen event of an identity is the line; a repeat
    whose ``is_cancellable`` is not true is a status update and adds no point; a repeat flagged
    cancellable is another line) less its ``CREDIT_MEMO_RECORDED`` amounts, netted per date (dates
    netting to 0 are dropped). A line enters at its S10-R-06 unconditional date under the billing
    mode of its own date (``billing_mode_at``): ``ERP``, and a noncancellable ``ENGINE`` line, at
    the line's effective date; a cancellable ``ENGINE`` line at the effective date of its first
    same-amount noncancellable status update (``billing_identity.first_updates`` /
    ``unconditional_date``; an applied receipt already governs under (a)); a cancellable ``ENGINE``
    line with no such date at the position is memo-only and contributes no point
    (``memo_only``; D-91 C606-05g, the ruled payment-timing proxy). A credit memo whose
    ``credited_invoice_number`` names an invoice ANY of whose kept lines is memo-only at the
    position, or that is dated before that invoice's earliest unconditional date (a later status
    update alone does not clear it), enters no point and is reported in ``credits_on_memo_only``
    (``CREDIT_MEMO_ON_MEMO_ONLY_LINE``, fail closed until the memo-with-its-document netting is
    built; D-97 (15) v3); every other memo nets at its own effective date. A different-amount
    update is stage 10's
    ``INVOICE_STATUS_UPDATE_MISMATCH``; this stage neither re-validates nor raises and keeps the
    first line's amount (D-91 C606-05)."""
    events = [
        event
        for event in st.identified.canonical.events
        if event.contract_key == contract_key
        and (before is None or event.order_key < before.order_key)
    ]
    classified = {
        item.event.event_key: item
        for item in billing_identity.iter_billing_lines(events, contract_key=contract_key)
    }
    ignored = tuple(item.event.event_key for item in classified.values() if item.is_status_update)
    updates = billing_identity.first_updates(events, contract_key=contract_key)
    entity_code = st.identified.canonical.contracts[contract_key].header.contracting_entity_code
    entity = ctx.entities.get(entity_code)
    if entity is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the contracting entity has no calendar",
            subject_key=contract_key,
            detail={"rule": "CV-12", "entity": entity_code},
        )
    receipts: list[tuple[date, Fraction]] = []
    receipt_sources: dict[date, str] = {}
    for event in events:
        if (
            event.event_type == _RECEIPTS
            and (payload_text(event.payload, "form") or "CASH") == "CASH"
        ):
            receipts.append(
                (event.effective_date, payload_fraction(event.payload, "amount") or Fraction(0))
            )
            receipt_sources.setdefault(event.effective_date, event.event_key)
    if receipts:
        return JudgedPoints(_by_date(receipts), _RECEIPTS, receipt_sources, ignored)
    billed: list[tuple[date, Fraction]] = []
    sources: dict[date, str] = {}
    memo_only: list[str] = []
    memo_only_invoices: dict[str, list[str]] = {}  # invoice number -> memo-only line keys
    dated_invoices: dict[str, date] = {}  # invoice number -> earliest S10-R-06 date of its lines
    eligible: list[str] = []  # D-97 (5) v2 boundary (iii): dated lines, netting aside
    credit_memos: list[EventView] = []
    for event in events:
        if event.event_type == _CREDIT_MEMO:
            credit_memos.append(event)  # netted after the lines are classified (D-97 (15))
            continue
        if event.event_type != _BILLING:
            continue
        item = classified[event.event_key]
        if item.is_status_update:
            continue  # S10-R-07: no billing, no payment point
        on = event.effective_date
        amount = payload_fraction(event.payload, "amount") or Fraction(0)
        mode = billing_mode_at(ctx.policies, entity, event.effective_date)
        if mode == BILLING_MODE_ENGINE and billing_identity.is_cancellable(event):
            # D-91 05g: the S10-R-06 date; receipts already govern under (a), so the only
            # source here is the identity's first same-amount noncancellable update.
            dated = billing_identity.unconditional_date(event, update=updates.get(event.event_key))
            if dated is None:
                memo_only.append(event.event_key)
                number = payload_text(event.payload, "invoice_number") or ""
                memo_only_invoices.setdefault(number, []).append(event.event_key)
                continue  # memo-only: no payment point at this position
            on = dated
        billed.append((on, amount))
        sources.setdefault(on, event.event_key)
        eligible.append(event.event_key)
        number = payload_text(event.payload, "invoice_number") or ""
        dated_invoices[number] = min(dated_invoices.get(number, on), on)
    credits: list[MemoOnlyCredit] = []
    for event in credit_memos:
        credited = payload_text(event.payload, "credited_invoice_number") or ""
        # D-97 (15): memo-only with its document; never a negative point at the memo's own date
        # while the line contributes nothing — the credited invoice has a memo-only kept line at
        # the position, or its lines become unconditional only after the memo's date (the memo
        # was recorded while the document was memo-only; the netting at the line's unconditional
        # date is the recorded follow-up).
        if credited in memo_only_invoices or (
            credited in dated_invoices and event.effective_date < dated_invoices[credited]
        ):
            credits.append(
                MemoOnlyCredit(
                    event.event_key,
                    payload_text(event.payload, "credit_memo_number") or "",
                    credited,
                    tuple(memo_only_invoices.get(credited, ())),
                )
            )
            continue
        on = event.effective_date
        billed.append((on, -(payload_fraction(event.payload, "amount") or Fraction(0))))
        sources.setdefault(on, event.event_key)
    return JudgedPoints(
        _by_date(billed),
        _BILLING,
        sources,
        ignored,
        tuple(memo_only),
        tuple(credits),
        tuple(eligible),
    )


def _by_date(points: Iterable[tuple[date, Fraction]]) -> tuple[tuple[date, Fraction], ...]:
    summed: dict[date, Fraction] = {}
    for on, amount in points:
        summed[on] = summed.get(on, Fraction(0)) + amount
    return tuple((on, amount) for on, amount in sorted(summed.items()) if amount != 0)


def _assess_judged(
    st: PobState,
    item: Assessment,
    weighted: Fraction | None,
    derived: JudgedPoints,
    before: EventView | None,
) -> Assessment:
    """S04-R-10a for an obligation tested without a payment schedule: a reviewed ``SFC_ASSESSMENT``
    with ``significant = true`` and ``exception_32_17 = NONE`` makes an adjustment apply on the
    derived payment points with no gap test (``reason = JUDGEMENT_SIGNIFICANT``). Any other outcome
    keeps the S04-R-10 assessment."""
    judgement = item.judgement
    if (
        item.reason != NO_PAYMENT_SCHEDULE
        or judgement is None
        or judgement.outcome.get("significant") != "true"
        or judgement.outcome.get("exception_32_17") != "NONE"
    ):
        return item
    transfer, transfer_open = _judged_transfer(st, item.obligation, before)
    # D-91 05g as bounded by D-97 (5) v2, four boundaries: (i) no billing line at the position ->
    # the S04-R-10 no-schedule outcome, no finding (nothing is known about payment timing before
    # the first document); (ii) lines exist and EVERY kept line is memo-only -> SFC_REVIEW_REQUIRED
    # (ERROR), nothing accretes; (iii) unconditional lines netting to zero beside memo-only lines
    # -> eligible lines exist, so NOT the finding (``points`` is empty only because ``_by_date``
    # dropped the netted date); (iv) receipts-first (branch (a)) never raises it (``memo_only`` is
    # empty there). The predicate reads the lines, not the netted points.
    no_eligible_point = bool(derived.memo_only) and not derived.eligible_lines
    return Assessment(
        item.obligation,
        transfer,
        weighted,
        True,
        judgement,
        JUDGEMENT_SIGNIFICANT,
        not no_eligible_point,
        no_eligible_point,
        derived.payment_source,
        transfer_open,
        derived.points,
        derived.status_updates_ignored,
        derived.memo_only,
        derived.credits_on_memo_only,
        derived.eligible_lines,
    )


def _judged_transfer(st: PobState, ob: PobDraft, before: EventView | None) -> tuple[Fraction, bool]:
    """T of S04-R-10a: over time as S04-R-10; point in time the line start date, else the date of
    the delivery at which net delivered (deliveries less returns preceding ``before``) reaches the
    line quantity, else open (the S04-R-10 ordinal is kept for the trace, flagged open)."""
    if ob.satisfaction_pattern == SatisfactionPattern.OVER_TIME or ob.start_date is not None:
        return _transfer(st, ob), False
    net = Fraction(0)
    for event in st.identified.canonical.events:
        if event.event_type not in _TRANSFER_EVENTS or event.contract_key != ob.contract_key:
            continue
        if before is not None and event.order_key >= before.order_key:
            continue
        named = payload_text(event.payload, "obligation_key")
        if ob.subject_key not in event.obligation_subject_keys and named != ob.obligation_key:
            continue
        quantity = payload_fraction(event.payload, "quantity") or Fraction(0)
        net += quantity if event.event_type == _DELIVERY else -quantity
        if event.event_type == _DELIVERY and net >= ob.quantity:
            return Fraction(event.effective_date.toordinal()), False
    return _transfer(st, ob), True


# --- S04-R-11 rate and S04-R-12 schedule ---------------------------------------------------------


def _rate(ctx: BookContext, st: PobState, contract_key: str) -> Rate | None:
    """The approved contract-level override with ``annual_rate`` (level C or O), else None."""
    entity = st.identified.canonical.contracts[contract_key].header.contracting_entity_code
    try:
        resolved = ctx.policies.resolved(RATE_POLICY, contract=contract_key, entity=entity)
    except ValueError:  # the code is not declared in the bundle (CV-17)
        return None
    value = resolved.value
    if resolved.level not in _OVERRIDE_LEVELS or not isinstance(value, Mapping):
        return None
    raw = value.get("annual_rate")
    if raw is None:
        return None
    annual = to_fraction(raw)
    compounding = value.get("compounding") or MONTHLY
    if compounding not in (MONTHLY, ANNUAL):
        raise ValueError(f"{RATE_POLICY}: unknown compounding {compounding!r} (CV-45)")
    periodic = annual / 12 if compounding == MONTHLY else annual
    if periodic <= -1:
        raise EngineError(
            "NON_FINITE_AMOUNT",
            "the periodic financing rate does not exceed −1",
            subject_key=contract_key,
            detail={"formula_id": CSP_FORMULA, "subject_key": contract_key},
        )
    return Rate(value.get("basis", ""), annual, compounding, periodic, resolved.source_ref)


def _schedule(
    ctx: BookContext,
    st: PobState,
    contract_key: str,
    adjusted: Sequence[Assessment],
    points: Sequence[tuple[date, Fraction]],
    weighted: Fraction,
    rate: Rate,
    source: str | None,
    point_sources: Mapping[date, str] | None = None,
) -> Schedule:
    """S04-R-12: counts, cash selling price, adjustment and the month grid of the contract.

    A payment enters the balance at the grid step equal to its count, so discounting and accretion
    use the same grid and the schedule settles exactly (R-SFC-04). ``MONTHLY`` interest is
    B_(m−1) × j; ``ANNUAL`` interest of contract year y is the opening balance of the year × i,
    spread as interest_y ÷ 12 over its months.
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    header = st.identified.canonical.contracts[contract_key].header
    entity = header.contracting_entity_code
    transfer = _schedule_transfer(adjusted)
    growth = 1 + rate.periodic
    monthly = rate.compounding == MONTHLY
    total = sum((amount for _, amount in points), Fraction(0))
    transfer_open = any(item.transfer_open for item in adjusted)
    keyed = {} if point_sources is None else point_sources
    if transfer_open or (weighted < transfer.toordinal() and _level_form(adjusted, monthly)):
        return _advance_schedule(
            ctx, st, contract_key, adjusted, points, rate, source, transfer, keyed
        )
    payments: list[Payment] = []
    if weighted < transfer.toordinal():
        kind, start = ADVANCE, min(on for on, _ in points)
        span = dates.month_ends_between(start, transfer)
        grid = span if monthly else 12 * (span // 12)
        for on, amount in points:
            months = dates.month_ends_between(on, transfer)
            count = months if monthly else months // 12
            payments.append(
                Payment(
                    on,
                    amount,
                    months,
                    count,
                    grid - (count if monthly else 12 * count),
                    keyed.get(on),
                )
            )
        csp = sum((p.amount * growth**p.count for p in payments), Fraction(0))
        opening = sum((p.amount for p in payments if p.step == 0), Fraction(0))
    else:
        kind, start = DEFERRED, transfer
        for on, amount in points:
            months = dates.month_ends_between(transfer, on)
            count = months if monthly else months // 12
            payments.append(
                Payment(on, amount, months, count, count if monthly else 12 * count, keyed.get(on))
            )
        grid = max(p.step for p in payments)
        csp = sum((p.amount / growth**p.count for p in payments), Fraction(0))
        opening = csp - sum((p.amount for p in payments if p.step == 0), Fraction(0))
    balance = opening
    year_opening = opening
    grid_months: list[Month] = []
    for step in range(1, grid + 1):
        if monthly:
            interest = balance * rate.periodic
        else:
            if (step - 1) % 12 == 0:
                year_opening = balance
            interest = year_opening * rate.periodic / 12
        paid = sum((p.amount for p in payments if p.step == step), Fraction(0))
        balance = balance + interest + (paid if kind == ADVANCE else -paid)
        grid_months.append(Month(_month_end_after(start, step), interest, balance))
    settled = (balance - csp) if kind == ADVANCE else balance
    if abs(settled) > Fraction(1, 10**minor_unit):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the financed balance does not settle within one minor unit",
            subject_key=contract_key,
            detail={"invariant": "S04-INV-04", "residual": format_exact(settled)},
        )
    return Schedule(
        contract_key=contract_key,
        entity=entity,
        subject_key=contract_entity_subject_key(contract_key, entity),
        obligations=tuple(item.obligation for item in adjusted),
        kind=kind,
        transfer=transfer,
        start=start,
        rate=rate,
        payments=tuple(payments),
        total=total,
        csp=csp,
        adjustment=round_half_up(csp, minor_unit) - round_half_up(total, minor_unit),
        opening=opening,
        months=tuple(grid_months),
        source_event_key=source,
    )


def _schedule_transfer(adjusted: Sequence[Assessment]) -> date:
    """T of the contract schedule: the adjusted obligations' transfer date, or the stated-price
    weighted mean of their ordinals when they differ (the earliest when every price is 0)."""
    ordinals = [item.transfer for item in adjusted]
    if len(set(ordinals)) == 1:
        mean = ordinals[0]
    else:
        weights = [item.obligation.stated_price for item in adjusted]
        total = sum(weights, Fraction(0))
        if total == 0:
            mean = min(ordinals)
        else:
            mean = sum((w * o for w, o in zip(weights, ordinals, strict=True)), Fraction(0)) / total
    return date.fromordinal(mean.numerator // mean.denominator)


def _level_form(adjusted: Sequence[Assessment], monthly: bool) -> bool:
    """D-87 L5-3-Q-8: an advance schedule is relieved by revenue shares when it compounds monthly,
    an adjusted obligation is over time, and every adjusted obligation is time elapsed with a term
    or point in time. Point-in-time schedules keep S04-R-12 (the same X with g = 1 at T)."""
    obligations = [item.obligation for item in adjusted]
    if not monthly or all(
        ob.satisfaction_pattern != SatisfactionPattern.OVER_TIME for ob in obligations
    ):
        return False
    return all(
        ob.satisfaction_pattern != SatisfactionPattern.OVER_TIME
        or (
            ob.recognition_method == RecognitionMethod.TIME_ELAPSED
            and ob.start_date is not None
            and ob.end_date is not None
        )
        for ob in obligations
    )


def _advance_schedule(
    ctx: BookContext,
    st: PobState,
    contract_key: str,
    adjusted: Sequence[Assessment],
    points: Sequence[tuple[date, Fraction]],
    rate: Rate,
    source: str | None,
    transfer: date,
    point_sources: Mapping[date, str] | None = None,
) -> Schedule:
    """The ``ADVANCE`` schedule of D-87 L5-3-Q-8 on the month grid from the first payment.

    Open transfer (S04-R-10a): B_k = B_(k−1)(1 + j) + pay_k through the horizon (``ANNUAL``: the
    year-opening interest of S04-R-12), with no relief and no CSP. Otherwise
    X = Σ pay_i·v^(n_i) ÷ Σ_k g_k·v^k with v = 1 ÷ (1 + j), n_i = m(start, date_i) and g_k the
    revenue share at the k-th month end (``_shares``); B_k = B_(k−1)(1 + j) + pay_k − X·g_k settles
    to 0 at the last revenue month (no zeroing at the midpoint).
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    entity = st.identified.canonical.contracts[contract_key].header.contracting_entity_code
    transfer_open = any(item.transfer_open for item in adjusted)
    growth = 1 + rate.periodic
    total = sum((amount for _, amount in points), Fraction(0))
    start = min(on for on, _ in points)
    keyed = {} if point_sources is None else point_sources
    payments = tuple(
        Payment(on, amount, step, step, step, keyed.get(on))
        for on, amount in points
        for step in (dates.month_ends_between(start, on),)
    )
    last_payment = max(p.step for p in payments)
    shares: tuple[tuple[int, Fraction], ...] = ()
    csp = Fraction(0)
    if transfer_open:
        grid = max(dates.month_ends_between(start, specialist.stream_end(ctx, st)), last_payment)
    else:
        shares = _shares(ctx, adjusted, start)
        grid = max(max(k for k, _ in shares), last_payment)
        v = 1 / growth
        csp = sum((p.amount * v**p.step for p in payments), Fraction(0)) / sum(
            (g * v**k for k, g in shares), Fraction(0)
        )
    relief = dict(shares)
    opening = sum((p.amount for p in payments if p.step == 0), Fraction(0)) - csp * relief.get(
        0, Fraction(0)
    )
    balance = opening
    year_opening = opening
    grid_months: list[Month] = []
    for step in range(1, grid + 1):
        if rate.compounding == MONTHLY:
            interest = balance * rate.periodic
        else:
            if (step - 1) % 12 == 0:
                year_opening = balance
            interest = year_opening * rate.periodic / 12
        paid = sum((p.amount for p in payments if p.step == step), Fraction(0))
        balance = balance + interest + paid - csp * relief.get(step, Fraction(0))
        grid_months.append(Month(_month_end_after(start, step), interest, balance))
    if not transfer_open and abs(balance) > Fraction(1, 10**minor_unit):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the financed balance does not settle within one minor unit",
            subject_key=contract_key,
            detail={"invariant": "S04-INV-04", "residual": format_exact(balance)},
        )
    return Schedule(
        contract_key=contract_key,
        entity=entity,
        subject_key=contract_entity_subject_key(contract_key, entity),
        obligations=tuple(item.obligation for item in adjusted),
        kind=ADVANCE,
        transfer=transfer,
        start=start,
        rate=rate,
        payments=payments,
        total=total,
        csp=csp,
        adjustment=0
        if transfer_open
        else round_half_up(csp, minor_unit) - round_half_up(total, minor_unit),
        opening=opening,
        months=tuple(grid_months),
        source_event_key=source,
        shares=shares,
        transfer_open=transfer_open,
    )


def _shares(
    ctx: BookContext, adjusted: Sequence[Assessment], start: date
) -> tuple[tuple[int, Fraction], ...]:
    """(k, g_k): the exact revenue share of the adjusted obligations recognised by the k-th month
    end after ``start``, weighted by stated price (equal weights when every price is 0). A
    time-elapsed obligation follows its ALG-11 convention over [start, end] on the performing
    entity's calendar (S09-R-08, V5); a point-in-time obligation gives its share at m(start, T)."""
    weights = [item.obligation.stated_price for item in adjusted]
    if sum(weights, Fraction(0)) == 0:
        weights = [Fraction(1) for _ in adjusted]
    total = sum(weights, Fraction(0))
    found: dict[int, Fraction] = {}
    for item, weight in zip(adjusted, weights, strict=True):
        ob = item.obligation
        share = weight / total
        if ob.satisfaction_pattern != SatisfactionPattern.OVER_TIME:
            on = date.fromordinal(item.transfer.numerator // item.transfer.denominator)
            step = dates.month_ends_between(start, on) if on > start else 0
            found[step] = found.get(step, Fraction(0)) + share
            continue
        if ob.start_date is None or ob.end_date is None:
            raise ValueError(f"{ob.subject_key}: a time-elapsed share needs a term (CV-45)")
        term_start = max(ob.start_date, ob.recognition_start_date or ob.start_date)
        convention, calendar = _time_convention(ctx, ob)
        cut_off = dates.add_months(ob.end_date, 2)  # MID_MONTH may complete after the end (D-79)
        previous, step = Fraction(0), 0
        while previous < 1:
            step += 1
            end_k = _month_end_after(start, step)
            current = (
                Fraction(1)
                if end_k > cut_off
                else progress.time_fraction(
                    convention, term_start, ob.end_date, end_k, calendar=calendar
                )
            )
            if current != previous:
                found[step] = found.get(step, Fraction(0)) + share * (current - previous)
            previous = current
    return tuple(sorted((k, g) for k, g in found.items() if g != 0))


def _time_convention(ctx: BookContext, ob: PobDraft) -> tuple[str, tuple[PeriodInput, ...] | None]:
    """The E-21 convention pinned on the obligation, else POL-090, and the performing entity's
    periods (None for a ``MONTHLY`` calendar), as stage 09 reads them (S09-R-08; ALG-11 rule 3)."""
    convention: object = ob.ratable_convention
    if convention is None:
        convention = ctx.policies.value(
            _TIME_POLICY,
            contract=ob.contract_key,
            obligation=ob.subject_key,
            entity=ob.performing_entity,
        )
    if not isinstance(convention, str) or str(convention) not in progress.TIME_CONVENTIONS:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a time-elapsed obligation carries no ratable convention",
            subject_key=ob.subject_key,
            detail={"rule": "S09-R-08"},
        )
    calendar = ctx.entities.get(ob.performing_entity)
    if calendar is None or calendar.calendar_pattern == "MONTHLY":
        return str(convention), None
    return str(convention), tuple(
        sorted(calendar.periods, key=lambda period: (period.start_date, period.end_date))
    )


def _level_params(schedule: Schedule) -> dict[str, str]:
    """Trace params of a D-87 L5-3-Q-8 schedule: ``shares`` (``<k>:<g_k>`` separated by ``,``) and
    ``transfer_open``."""
    found: dict[str, str] = {}
    if schedule.shares:
        found["shares"] = ",".join(f"{k}:{rational_param(g)}" for k, g in schedule.shares)
    if schedule.transfer_open:
        found["transfer_open"] = "true"
    return found


def _zero_balance(schedule: Schedule, t: date) -> bool:
    """The financed balance is 0 before the grid origin and, for a point-in-time advance, from the
    transfer (S04-R-13). A revenue-share schedule settles on its grid, and an open transfer is never
    relieved (D-87 L5-3-Q-8)."""
    if t < schedule.start:
        return True
    return (
        schedule.kind == ADVANCE
        and not schedule.shares
        and not schedule.transfer_open
        and t >= schedule.transfer
    )


def _month_end_after(start: date, step: int) -> date:
    """e_k: the k-th calendar month end after ``start`` (m(start, e_k) = k)."""
    first = dates.month_end(start)
    if first == start:
        first = dates.month_end(dates.add_months(dates.month_start(start), 1))
    return dates.month_end(dates.add_months(dates.month_start(first), step - 1))


def _balance(schedule: Schedule, t: date, recognised: Fraction | None) -> tuple[Fraction, Fraction]:
    """(financed balance at the end of ``t``, scheduled payments through it) (S04-R-13).

    Before the grid origin the balance is 0; an advance balance is relieved by revenue at T. While
    S04-R-12a applies, the balance is CSP + the interest recognised − the payments.
    """
    if _zero_balance(schedule, t):
        return Fraction(0), Fraction(0)
    step = sum(1 for m in schedule.months if m.end <= t)
    paid = sum((p.amount for p in schedule.payments if p.step <= step), Fraction(0))
    if recognised is not None:
        return schedule.csp + recognised - paid, paid
    return (schedule.opening if step == 0 else schedule.months[step - 1].balance), paid


def _balance_mode(schedule: Schedule, t: date, suspended: bool) -> tuple[str, int]:
    """The ``sfc.accretion.v1`` mode of the balance at ``t`` and its grid step (S04-R-13)."""
    if _zero_balance(schedule, t):
        return "zero", 0
    step = sum(1 for m in schedule.months if m.end <= t)
    return ("suspended" if suspended else "grid"), step


def _payments_param(schedule: Schedule) -> str:
    """The grid steps and amounts of the payments, ``<step>:<amount>`` separated by ``,``."""
    return ",".join(f"{p.step}:{format_exact(p.amount)}" for p in schedule.payments)


def _unsettled(ctx: BookContext, st: PobState, schedule: Schedule) -> Finding | None:
    """``SFC_SCHEDULE_UNSETTLED`` for the first cash ``PAYMENT_RECEIVED`` of the contract that takes
    the cumulative receipts beyond the amount that settles the schedule at its date by more than
    one minor unit (05 §3.6.3): the scheduled payments through the grid step of the month end on or
    after the receipt plus the balance after that step (deferred), or Σ scheduled payments
    (advance)."""
    minor = Fraction(1, 10 ** ctx.currencies[ctx.txn_currency].minor_unit)
    received = Fraction(0)
    for event in st.identified.canonical.events:
        if event.event_type != "PAYMENT_RECEIVED" or event.contract_key != schedule.contract_key:
            continue
        if (payload_text(event.payload, "form") or "CASH") != "CASH":
            continue
        received += payload_fraction(event.payload, "amount") or Fraction(0)
        available = _available(schedule, event.effective_date)
        if received - available > minor:
            detail = {
                "available": format_exact(available),
                "received": format_exact(received),
                "rule": "S04-R-12",
            }
            return Finding(
                "SFC_SCHEDULE_UNSETTLED",
                "ERROR",
                schedule.subject_key,
                detail,
                _STAGE,
                event.event_key,
            )
    return None


def _available(schedule: Schedule, on: date) -> Fraction:
    if schedule.kind == ADVANCE:
        return schedule.total
    if on <= schedule.start:
        step = 0
    else:
        ends = dates.month_ends_between(schedule.start, on)
        step = min(ends + (0 if on == dates.month_end(on) else 1), len(schedule.months))
    balance = schedule.opening if step == 0 else schedule.months[step - 1].balance
    paid = sum((p.amount for p in schedule.payments if p.step <= step), Fraction(0))
    return paid + balance


# --- S04-R-12a suspension ------------------------------------------------------------------------


def _suspension(ctx: BookContext, st: PobState, schedule: Schedule) -> tuple[bool, date | None]:
    """(suspended, L) of a deferred schedule (S04-R-12a).

    L is the first date on or after T on which N − Y − E > 0 for an obligation that carries the
    adjustment. Only returnable obligations can have a target held at 0 by expected returns, so a
    schedule with a non-returnable carrying obligation is never suspended. The candidates are T,
    the transfer and return dates, the pin dates and each ``window_end_date`` (E = 0 from the
    window end; D-87 L6-5-Q-25). The
    schedule is suspended when its first month end falls on or before L, or when no candidate
    gives a positive target (L open).
    """
    if schedule.kind != DEFERRED or not schedule.months:
        return False, None
    returnable = {item.obligation.subject_key: item for item in returns.returnable(ctx, st)}
    carrying = [returnable.get(ob.subject_key) for ob in schedule.obligations]
    items = [item for item in carrying if item is not None]
    if len(items) != len(carrying):
        return False, None
    cb = st.identified.canonical
    candidates = {schedule.transfer}
    for event in cb.events:
        if event.contract_key == schedule.contract_key and event.event_type in _TRANSFER_EVENTS:
            candidates.add(max(event.effective_date, schedule.transfer))
    for item in items:
        for key in item.estimate_keys:
            for applied in cb.estimates.pins.get(key, ()):
                version = applied.version
                candidates.add(max(version.effective_date, schedule.transfer))
                window = payload_date(version.parameters, "window_end_date")
                if window is not None:
                    candidates.add(max(window, schedule.transfer))
    for day in sorted(candidates):
        if any(_positive(ctx, st, item, day) for item in items):
            return schedule.months[0].end <= day, day
    return True, None


def _positive(ctx: BookContext, st: PobState, item: returns.Returnable, day: date) -> bool:
    ob = item.obligation
    (measured,) = returns.measure(ctx, st, (item,), day, None, {ob.subject_key: Fraction(1)})
    delivered = st.identified.canonical.ledger.at(ob.subject_key, on=day).delivered_cum
    return delivered - measured.returned - measured.expected > 0


# --- Trace ---------------------------------------------------------------------------------------


def _emit_gap(tb: TraceBuilder, item: Assessment, suffix: str) -> str:
    """Node ``financing_gap_test:<ob>:-`` (``sfc.gap_test.v1``): W − ordinal(T_p) in days."""
    ob = item.obligation
    params = {
        "adjust": "true" if item.adjust else "false",
        "reason": item.reason,
        "significant": "true" if item.significant else "false",
        "transfer_ordinal": format_exact(item.transfer),
    }
    if item.weighted is not None:
        params["weighted_payment_ordinal"] = format_exact(item.weighted)
    if item.judgement is not None:
        params["judgement_key"] = item.judgement.judgement_key
    if item.payment_source is not None:  # S04-R-10a (D-87 L5-3-Q-8; D-91 C606-05)
        params["payment_source"] = item.payment_source
        params["payment_points"] = "|".join(
            f"{on.isoformat()}:{format_exact(amount)}" for on, amount in item.payment_points
        )
        params["status_updates_ignored"] = str(len(item.status_updates_ignored))
        if item.status_updates_ignored:
            params["status_updates_ignored_keys"] = "|".join(item.status_updates_ignored)
        params["memo_only_lines"] = str(len(item.memo_only_lines))  # D-91 05g
        if item.memo_only_lines:
            params["memo_only_line_keys"] = "|".join(item.memo_only_lines)
        if item.credit_memos_on_memo_only:  # D-97 (15)
            params["credit_memos_on_memo_only"] = "|".join(
                credit.event_key for credit in item.credit_memos_on_memo_only
            )
        params["eligible_lines"] = str(len(item.eligible_lines))  # D-97 (5) v2 boundary (iii)
    if item.transfer_open:
        params["transfer_open"] = "true"
    gap = Fraction(0) if item.weighted is None else item.weighted - item.transfer
    return tb.node(
        measure=f"{GAP}{suffix}",
        subject_key=ob.subject_key,
        period_key=None,
        value=gap,
        currency=None,
        minor_unit=None,
        formula_id=GAP_FORMULA,
        inputs=[],
        params=params,
        narrative_key=GAP_FORMULA.rsplit(".v", 1)[0],
    )


def _emit_csp(ctx: BookContext, tb: TraceBuilder, schedule: Schedule, suffix: str) -> list[str]:
    """``cash_selling_price:<ob>:-`` per adjusted obligation: round(CSP) apportioned by stated price
    with ``largest_remainder`` (CV-36), the exact share in the residue."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    obligations = schedule.obligations
    weights = [ob.stated_price for ob in obligations]
    if sum(weights, Fraction(0)) == 0:
        weights = [Fraction(1) for _ in obligations]
    keys = [ob.subject_key for ob in obligations]
    posted = largest_remainder(round_half_up(schedule.csp, minor_unit), weights, keys)
    total_weight = sum(weights, Fraction(0))
    params = {
        "annual_rate": format_exact(schedule.rate.annual_rate),
        "basis": schedule.rate.basis,
        "compounding": schedule.rate.compounding,
        "counts": ",".join(str(p.count) for p in schedule.payments),
        "kind": schedule.kind,
        "months": ",".join(str(p.months) for p in schedule.payments),
        "transfer_date": schedule.transfer.isoformat(),
    }
    params.update(_level_params(schedule))  # D-87 L5-3-Q-8: counts are grid steps with shares
    params["keys"] = "|".join(keys)
    params["weights"] = ",".join(format_exact(weight) for weight in weights)
    ids: list[str] = []
    for index, (ob, weight, value) in enumerate(zip(obligations, weights, posted, strict=True)):
        inputs: list[str | SourceRef] = [
            SourceRef(
                "policy_override",
                schedule.rate.source_ref,
                {"value": format_exact(schedule.rate.annual_rate)},
            ),
            *(
                SourceRef(
                    "contract_event",
                    p.source_event_key or schedule.source_event_key or schedule.contract_key,
                    {"date": p.on.isoformat(), "value": format_exact(p.amount)},
                )
                for p in schedule.payments
            ),
        ]
        ids.append(
            tb.node(
                measure=f"{CSP}{suffix}",
                subject_key=ob.subject_key,
                period_key=None,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=CSP_FORMULA,
                inputs=inputs,
                params={
                    **params,
                    "index": str(index),
                    "share": format_exact(weight / total_weight),
                },
                exact=schedule.csp * weight / total_weight,
                narrative_key=CSP_FORMULA.rsplit(".v", 1)[0],
            )
        )
    return ids
