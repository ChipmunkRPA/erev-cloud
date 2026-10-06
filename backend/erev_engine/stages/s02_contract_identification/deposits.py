"""Stage 02 deposit accounting while a contract fails Step 1 (ENGINE_SPEC §2.3 S02-R-07, S02-R-08).

EMOD-12 cumulative targets for the JET-01b lines (POL-012, POL-013, POL-128), in transaction
currency. Money cumulative values are rounded by CV-35 (``money.round_half_up`` of the exact
cumulative value). Every deposit node records, in ``params["signs"]``, the sign with which each
input enters its value, so the formula is the signed sum of its inputs; a 25-7 recognition also
records the D-91 cap (``params["limit"]``: the stated consideration less the revenue already
recognised under S02-R-07), and its value is the lesser of the balance and that cap (D-91 gaps
(vi)). A recognition at a dated point without an event ((a) at the term end, (c) at
``event_c_met_on``) feeds the sixth EMOD-12 measure ``deposit_to_revenue_time_cum``, the
``CLOSE_RELEASE`` share stage 14 posts as a ``TIME`` amount (S02-R-08 rev 1.6; D-91 gaps (iii)).
Private to stage 02. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine import dates, money
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import BookContext, EventView, Target
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "END_OF_DAY",
    "MEASURES",
    "CriteriaMetTransition",
    "DepositLedger",
    "DepositPoint",
    "DepositRecognition",
]

DEPOSIT_FORMULA: Final = "step1.deposit.v1"
TRANSITION_FORMULA: Final = "step1.transition_catch_up.v1"
EVENT_25_7_FORMULA: Final = "step1.event_25_7.v1"
RECEIVED, REFUNDED, TO_REVENUE, TO_CONTRACT_LIABILITY, TO_REVENUE_TIME, LIABILITY = (
    "deposit_received_cum",
    "deposit_refunded_cum",
    "deposit_to_revenue_cum",
    "deposit_to_contract_liability_cum",
    "deposit_to_revenue_time_cum",
    "deposit_liability",
)
# The four movement sums, then the dated share of the recognitions and the derived liability.
_SUMMED: Final = (RECEIVED, REFUNDED, TO_REVENUE, TO_CONTRACT_LIABILITY)
MEASURES: Final = (*_SUMMED, TO_REVENUE_TIME, LIABILITY)
# Orders a dated evaluation without an event (25-7(a) at the term end, 25-7(c) at
# ``event_c_met_on``) after every event of its date (L1-2-Q-7).
END_OF_DAY: Final = 2**63 - 1

OrderKey = tuple[date, int, str]


@dataclass(frozen=True, slots=True)
class DepositPoint:
    """Cumulative deposit values after a movement (S02-R-08)."""

    order_key: OrderKey
    received_cum: Fraction
    refunded_cum: Fraction
    to_revenue_cum: Fraction
    to_contract_liability_cum: Fraction
    # The portion of ``to_revenue_cum`` recognised at dated points without an event (S02-R-08).
    to_revenue_time_cum: Fraction = Fraction(0)

    @property
    def effective_date(self) -> date:
        return self.order_key[0]

    @property
    def liability(self) -> Fraction:
        """``deposit_liability``: received − refunded − to revenue − to contract liability."""
        return (
            self.received_cum
            - self.refunded_cum
            - self.to_revenue_cum
            - self.to_contract_liability_cum
        )

    @classmethod
    def zero(cls, order_key: OrderKey = (date.min, 0, "")) -> DepositPoint:
        nothing = Fraction(0)
        return cls(order_key, nothing, nothing, nothing, nothing)


@dataclass(frozen=True, slots=True)
class DepositRecognition:
    """A 606-10-25-7 recognition of the deposit balance (S02-R-07; JET-01b)."""

    contract_key: str
    reason: str  # EVENT_25_7_A | EVENT_25_7_B | EVENT_25_7_C
    effective_date: date
    event_key: str | None  # None for a dated point without an event ((a) at T, (c) at met_on)
    amount: Fraction
    node_id: str

    @property
    def timed(self) -> bool:
        """A recognition at a dated point: the ``CLOSE_RELEASE`` ``TIME`` share (D-91 (iii))."""
        return self.event_key is None


@dataclass(frozen=True, slots=True)
class CriteriaMetTransition:
    """A ``CRITERIA_MET`` transition and the deposit balance it transfers (S02-R-04, S02-R-08)."""

    contract_key: str
    event_key: str
    effective_date: date
    transition: str  # POL-013 literal
    deposit_transferred: Fraction
    node_id: str


@dataclass(frozen=True, slots=True)
class _Movement:
    order_key: OrderKey
    measure: str  # the cumulative measure it feeds
    input: str | SourceRef  # valued source, or the node of a recognition or transfer
    amount: Fraction
    reason: str | None
    timed: bool = False  # a recognition at a dated point without an event


class DepositLedger:
    """Deposit accounting of one contract in one book (EMOD-12); an instance lives for one call."""

    def __init__(
        self, ctx: BookContext, contract_key: str, entity_code: str, tb: TraceBuilder
    ) -> None:
        self._ctx = ctx
        self._tb = tb
        self.contract_key = contract_key
        self.entity_code = entity_code
        self.subject_key = contract_entity_subject_key(contract_key, entity_code)
        self._currency = ctx.txn_currency
        self._minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
        self._movements: list[_Movement] = []
        self.points: list[DepositPoint] = []
        self.recognitions: list[DepositRecognition] = []
        self.transitions: list[CriteriaMetTransition] = []

    @property
    def balance(self) -> Fraction:
        return self.points[-1].liability if self.points else Fraction(0)

    @property
    def recognised(self) -> Fraction:
        """Revenue recognised under S02-R-07 so far (the cap's deduction, D-91 gaps (vi))."""
        return self.points[-1].to_revenue_cum if self.points else Fraction(0)

    def _sum(self, measure: str, *, timed: bool | None = None) -> Fraction:
        return sum(
            (
                m.amount
                for m in self._movements
                if m.measure == measure and (timed is None or m.timed == timed)
            ),
            Fraction(0),
        )

    def _record(self, movement: _Movement) -> None:
        if self.points and movement.order_key < self.points[-1].order_key:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a deposit movement is recorded out of ENG-06 order",
                subject_key=self.subject_key,
                detail={"rule": "S02-R-08", "order_key": movement.order_key[2]},
            )
        self._movements.append(movement)
        point = DepositPoint(
            movement.order_key,
            self._sum(RECEIVED),
            self._sum(REFUNDED),
            self._sum(TO_REVENUE),
            self._sum(TO_CONTRACT_LIABILITY),
            self._sum(TO_REVENUE, timed=True),
        )
        if point.liability < 0:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the deposit liability is negative",
                subject_key=self.subject_key,
                detail={"invariant": "S02-INV-02", "order_key": movement.order_key[2]},
            )
        self.points.append(point)

    def _node(
        self,
        measure: str,
        period_key: str | None,
        amount: Fraction,
        formula_id: str,
        inputs: Sequence[tuple[str | SourceRef, str]],
        **params: str,
    ) -> str:
        return self._tb.node(
            measure=measure,
            subject_key=self.subject_key,
            period_key=period_key,
            value=money.round_half_up(amount, self._minor_unit),
            currency=self._currency,
            minor_unit=self._minor_unit,
            formula_id=formula_id,
            inputs=[item for item, _ in inputs],
            params={"signs": "".join(sign for _, sign in inputs), **params},
            exact=amount,
            narrative_key=formula_id.rsplit(".v", 1)[0],
        )

    def _balance_inputs(self, trigger: SourceRef | None) -> list[tuple[str | SourceRef, str]]:
        inputs: list[tuple[str | SourceRef, str]] = []
        if trigger is not None:
            inputs.append((SourceRef(trigger.ref_type, trigger.ref_id, {"value": "0"}), "+"))
        for movement in self._movements:
            inputs.append((movement.input, "+" if movement.measure == RECEIVED else "-"))
        return inputs

    def receive(self, event: EventView, amount: Fraction) -> None:
        """A receipt while ``NOT_A_CONTRACT``: Dr BILLING_CLEARING / Cr DEPOSIT_LIABILITY."""
        source = SourceRef("contract_event", event.event_key, {"value": money.format_exact(amount)})
        self._record(_Movement(event.order_key, RECEIVED, source, amount, None))

    def refund(self, event: EventView, requested: Fraction) -> Fraction:
        """``CONTRACT_TERMINATED.refund_amount`` limited to the deposit balance (JET-01b)."""
        amount = min(requested, self.balance)
        if amount > 0:
            value = money.format_exact(amount)
            source = SourceRef("contract_event", event.event_key, {"value": value})
            self._record(_Movement(event.order_key, REFUNDED, source, amount, None))
        return amount

    def recognise(
        self,
        reason: str,
        *,
        event: EventView | None,
        on: date | None = None,
        limit: Fraction | None = None,
    ) -> DepositRecognition | None:
        """Recognise the deposit balance as revenue (S02-R-07); ``None`` when nothing is due.

        ``limit`` is the D-91 gaps (vi) cap: the stated (enforceable) consideration less the
        revenue already recognised under S02-R-07, applied to every route ((a), (b) and (c)); the
        excess stays in the deposit liability as a customer credit (606-10-32-1). A recognition
        without an event is a dated point ordered after every event of its date and counts toward
        ``deposit_to_revenue_time_cum`` (the ``CLOSE_RELEASE`` share; D-91 gaps (iii)).
        """
        amount = self.balance
        if limit is not None:
            amount = min(amount, limit)
        if amount <= 0:
            return None
        if event is None:
            if on is None:
                raise ValueError("a recognition without an event needs its date")
            order_key: OrderKey = (on, END_OF_DAY, "")
            measure, trigger, effective = f"deposit_to_revenue@{on.isoformat()}", None, on
        else:
            order_key, trigger, effective = event.order_key, event.source, event.effective_date
            measure = f"deposit_to_revenue@{event.event_key}"
        params = {"reason": reason}
        if limit is not None:
            params["limit"] = money.format_exact(limit)
        node_id = self._node(
            measure, None, amount, EVENT_25_7_FORMULA, self._balance_inputs(trigger), **params
        )
        self._record(_Movement(order_key, TO_REVENUE, node_id, amount, reason, event is None))
        recognition = DepositRecognition(
            self.contract_key,
            reason,
            effective,
            None if event is None else event.event_key,
            amount,
            node_id,
        )
        self.recognitions.append(recognition)
        return recognition

    def transfer(self, event: EventView, transition: str) -> CriteriaMetTransition:
        """``CRITERIA_MET``: the deposit balance moves to the contract liability (S02-R-04)."""
        amount = self.balance
        node_id = self._node(
            f"deposit_to_contract_liability@{event.event_key}",
            None,
            amount,
            TRANSITION_FORMULA,
            self._balance_inputs(event.source),
            transition=transition,
        )
        self._record(_Movement(event.order_key, TO_CONTRACT_LIABILITY, node_id, amount, None))
        if self.balance != 0:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a deposit balance remains after the criteria-met transition",
                subject_key=self.subject_key,
                detail={"invariant": "S02-INV-03", "event_key": event.event_key},
            )
        record = CriteriaMetTransition(
            self.contract_key, event.event_key, event.effective_date, transition, amount, node_id
        )
        self.transitions.append(record)
        return record

    def period_targets(self, start: date | None) -> tuple[Target, ...]:
        """Period-end targets of the five deposit measures from the period containing ``start``
        (the first ``NOT_A_CONTRACT`` date) through the horizon (CV-13; S02-R-08)."""
        entity = self._ctx.entities.get(self.entity_code)
        if entity is None:
            raise ValueError(f"entity {self.entity_code} is absent from the bundle (CV-12)")
        horizon_key = self._ctx.horizon.get(self.entity_code)
        if start is None or horizon_key is None:
            return ()
        horizon = next((p for p in entity.periods if p.period_key == horizon_key), None)
        if horizon is None:
            raise ValueError(f"horizon period {horizon_key} is absent from the calendar (CV-13)")
        if start > horizon.end_date:
            return ()
        targets: list[Target] = []
        for period in dates.covering_periods(entity.periods, start, horizon.end_date):
            moves = [m for m in self._movements if m.order_key[0] <= period.end_date]
            nodes: dict[str, str] = {}
            totals: dict[str, Fraction] = {}
            for measure in _SUMMED:
                selected = [m for m in moves if m.measure == measure]
                totals[measure] = sum((m.amount for m in selected), Fraction(0))
                nodes[measure] = self._node(
                    measure,
                    period.period_key,
                    totals[measure],
                    DEPOSIT_FORMULA,
                    [(m.input, "+") for m in selected],
                )
            # S02-R-08 rev 1.6: the recognitions at dated points, the CLOSE_RELEASE share (D-91).
            timed = [m for m in moves if m.measure == TO_REVENUE and m.timed]
            totals[TO_REVENUE_TIME] = sum((m.amount for m in timed), Fraction(0))
            nodes[TO_REVENUE_TIME] = self._node(
                TO_REVENUE_TIME,
                period.period_key,
                totals[TO_REVENUE_TIME],
                DEPOSIT_FORMULA,
                [(m.input, "+") for m in timed],
            )
            totals[LIABILITY] = (
                totals[RECEIVED]
                - totals[REFUNDED]
                - totals[TO_REVENUE]
                - totals[TO_CONTRACT_LIABILITY]
            )
            nodes[LIABILITY] = self._node(
                LIABILITY,
                period.period_key,
                totals[LIABILITY],
                DEPOSIT_FORMULA,
                [(nodes[measure], sign) for measure, sign in zip(_SUMMED, "+---", strict=True)],
            )
            reasons = [m.reason for m in moves if m.measure == TO_REVENUE]
            timed_reasons = [m.reason for m in timed]
            for measure in MEASURES:
                cause = None
                if measure == TO_REVENUE and reasons:
                    cause = reasons[-1]
                elif measure == TO_REVENUE_TIME and timed_reasons:
                    cause = timed_reasons[-1]
                targets.append(
                    Target(
                        book_code=self._ctx.book_code,
                        entity=self.entity_code,
                        subject_key=self.subject_key,
                        measure=measure,
                        period_key=period.period_key,
                        cause=cause,
                        value=money.round_half_up(totals[measure], self._minor_unit),
                        exact=totals[measure],
                        node_id=nodes[measure],
                    )
                )
        return tuple(targets)


def point_at(
    points: Sequence[DepositPoint], *, before: EventView | None = None, on: date | None = None
) -> DepositPoint:
    """The deposit values after every movement preceding ``before`` in ENG-06 order, or effective
    on or before ``on``; the latest values when neither is given."""
    if before is not None and on is not None:
        raise ValueError("pass before or on, not both")
    if before is not None:
        count = bisect.bisect_left(points, before.order_key, key=lambda point: point.order_key)
    elif on is not None:
        count = bisect.bisect_right(points, on, key=lambda point: point.order_key[0])
    else:
        count = len(points)
    return points[count - 1] if count else DepositPoint.zero()
