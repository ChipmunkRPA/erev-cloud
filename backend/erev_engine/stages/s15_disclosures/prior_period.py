"""Stage 15 revenue from obligations satisfied in prior periods (ENGINE_SPEC_B §15.2.4 S15-R-13,
S15-R-14; §15.5; POLICIES POL-204, ALG-10 §2.11.3; 606-10-50-12A; IFRS 15.116(c); EDS-4).

``build(ctx, allocated, recognition, posted, tb)`` is the consumer ENGINE_SPEC_B §0.4 names for
the stage 08 producer: for every performing entity of the obligations stage 09 measured
(``recognition.obligation_measures``; an obligation stage 09 produces no targets for — a
``LEASE_842`` scope routed out under S09-R-13 — has no revenue to decompose) and every period of
that entity's calendar from the group's inception period through the entity's horizon (CV-13; the
period set stages 09 and 10 measure), it calls ``decompose_prior_period(ctx, view, period_key,
tb, posted=posted)`` with the allocated state viewed through those obligations, so each
obligation is decomposed on its own calendar (S08-R-14 to S08-R-16 emit one
``revenue_prior_period:<ob>:<period>`` node per obligation, zero when nothing in the period changed
the revenue of performance before its start). Per (contract, contracting entity) and period it then
emits ``revenue_prior_period_sum:<contract>@<entity>:<period>`` (``disc.prior_period_sum.v1``,
inputs the obligation nodes), the aggregate S15-R-14's report row sums. Journal lines are not
split (ALG-10 §2.11.3). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Final

from erev_engine import dates
from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s08_estimates_late_events import decompose_prior_period
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.state import AllocatedState, BookContext, PostedIndex, Target
from erev_engine.trace import TraceBuilder

__all__ = ["MEASURE", "SUM_FORMULA", "SUM_MEASURE", "PriorPeriod", "build", "periods"]

MEASURE: Final = "revenue_prior_period"  # the stage 08 node (S08-R-16)
SUM_MEASURE: Final = "revenue_prior_period_sum"
SUM_FORMULA: Final = "disc.prior_period_sum.v1"


@dataclass(frozen=True, slots=True)
class PriorPeriod:
    """S15-R-13 targets of one book: per obligation and period, and their contract-entity sums."""

    targets: tuple[Target, ...]  # measure ``revenue_prior_period``; (subject key, period) order
    sums: tuple[Target, ...]  # measure ``revenue_prior_period_sum``; (subject key, period) order


def _invariant(message: str, subject_key: str, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=subject_key,
        detail={**detail, "stage": "15"},
    )


def periods(ctx: BookContext, st: AllocatedState, entity_code: str) -> tuple[PeriodInput, ...]:
    """Periods of ``entity_code`` from the group's inception period through its horizon (CV-13),
    the set stages 09 and 10 evaluate (S15-R-13 "every period through the horizon")."""
    entity = ctx.entities.get(entity_code)
    horizon_key = ctx.horizon.get(entity_code)
    if entity is None or horizon_key is None:
        raise _invariant(
            "the performing entity has no calendar or horizon", entity_code, rule="CV-13"
        )
    ordered = tuple(sorted(entity.periods, key=lambda period: (period.start_date, period.end_date)))
    horizon = next((period for period in ordered if period.period_key == horizon_key), None)
    if horizon is None:
        raise _invariant(
            "the horizon period is absent from the calendar", entity_code, rule="CV-13"
        )
    first = dates.period_of(entity, st.inception_date)
    return tuple(
        period
        for period in ordered
        if period.start_date >= first.start_date and period.end_date <= horizon.end_date
    )


def build(
    ctx: BookContext,
    st: AllocatedState,
    recognition: RecognitionState,
    posted: PostedIndex | None,
    tb: TraceBuilder,
) -> PriorPeriod:
    """The prior-period revenue targets of one book (§15.2.4) for the obligations stage 09
    measured."""
    by_entity: dict[str, list[str]] = {}
    for ob in st.obligations:
        if ob.subject_key in recognition.obligation_measures:
            by_entity.setdefault(ob.performing_entity, []).append(ob.subject_key)
    targets: list[Target] = []
    for entity_code in sorted(by_entity):
        members = frozenset(by_entity[entity_code])
        view = replace(
            st, obligations=tuple(ob for ob in st.obligations if ob.subject_key in members)
        )
        for period in periods(ctx, st, entity_code):
            targets.extend(decompose_prior_period(ctx, view, period.period_key, tb, posted=posted))
    ordered = tuple(sorted(targets, key=lambda item: (item.subject_key, item.period_key)))
    return PriorPeriod(targets=ordered, sums=_sums(ctx, st, ordered, tb))


def _sums(
    ctx: BookContext, st: AllocatedState, targets: Sequence[Target], tb: TraceBuilder
) -> tuple[Target, ...]:
    """``revenue_prior_period_sum`` per (contract, contracting entity, period): Σ the obligation
    nodes of the contract's obligations for that period (S15-R-14 grain, ENGINE_SPEC_B §15.3)."""
    obligations = {ob.subject_key: ob for ob in st.obligations}
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    groups: dict[tuple[str, str, str], list[Target]] = {}
    for target in targets:
        ob = obligations[target.subject_key]
        subject = contract_entity_subject_key(ob.contract_key, ob.contracting_entity)
        groups.setdefault((subject, ob.contracting_entity, target.period_key), []).append(target)
    out: list[Target] = []
    for (subject, entity, period_key), members in sorted(groups.items()):
        value = sum(item.value for item in members)
        exact = sum(
            (
                item.exact if item.exact is not None else Fraction(item.value, 10**minor_unit)
                for item in members
            ),
            Fraction(0),
        )
        node_id = tb.node(
            measure=SUM_MEASURE,
            subject_key=subject,
            period_key=period_key,
            value=value,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=SUM_FORMULA,
            inputs=[item.node_id for item in members],
            params={"count": str(len(members)), "period": period_key},
            exact=exact,
            narrative_key=SUM_FORMULA.rsplit(".v", 1)[0],
        )
        out.append(
            Target(
                book_code=ctx.book_code,
                entity=entity,
                subject_key=subject,
                measure=SUM_MEASURE,
                period_key=period_key,
                cause=None,
                value=value,
                exact=exact,
                node_id=node_id,
            )
        )
    return tuple(out)


def by_period(targets: Sequence[Target]) -> Mapping[tuple[str, str], int]:
    """(subject key, period key) -> posted minor units, for readers of the state."""
    return {(item.subject_key, item.period_key): item.value for item in targets}
