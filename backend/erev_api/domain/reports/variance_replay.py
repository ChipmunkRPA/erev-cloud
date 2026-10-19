"""S15-R-21/23 event-only DRY_RUN execution for close variance.

This is the worker-side calculation, not a registered report/job. A caller must
load and authorize retained bundles and supply a metric projection for the fixed
period. Both projected endpoints must agree exactly with the frozen figures.
Reference, rate, membership and posting-basis changes need separate replay phases
and are refused here; they must never be mislabeled as event effects or residuals.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from datetime import date
from fractions import Fraction
from itertools import groupby
from typing import Final

from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import EventInput, InputBundle, OutputBundle
from erev_engine.stages.s15_disclosures.variance import Decomposition, Evaluation, decompose

from erev_api.problems import Problem

from .variance_measures import MeasureKey

type Metrics = Mapping[MeasureKey, Fraction]
type Project = Callable[[OutputBundle], Metrics]
type Engine = Callable[[InputBundle], OutputBundle]

_DRIVERS: Final = {
    "DELIVERY_RECORDED": "PROGRESS",
    "PROGRESS_RECORDED": "PROGRESS",
    "MILESTONE_ACHIEVED": "PROGRESS",
    "USAGE_REPORTED": "PROGRESS",
    "COST_INCURRED": "PROGRESS",
    "RETURN_RECORDED": "PROGRESS",
    "BILLING_RECORDED": "BILLING",
    "CREDIT_MEMO_RECORDED": "BILLING",
    "PAYMENT_RECEIVED": "BILLING",
    "CONTRACT_ACTIVATED": "NEW_CONTRACT",
    "CONTRACT_CRITERIA_MET": "NEW_CONTRACT",
    "OPENING_BALANCE_ESTABLISHED": "NEW_CONTRACT",
    "CONTRACT_AMENDED": "MODIFICATION",
    "ESTIMATE_CHANGED": "ESTIMATE_CHANGE",
    "MEMO_UPDATED": "OTHER",
}


@dataclass(frozen=True)
class Execution:
    driver: str
    event_keys: tuple[str, ...]
    input_sha256: str
    output_sha256: str


@dataclass(frozen=True)
class Replay:
    engine_version: str
    executions: tuple[Execution, ...]
    measures: Mapping[MeasureKey, Decomposition]


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close variance replay: {detail}")


def _order(event: EventInput) -> tuple[date, int, str]:
    return event.effective_date, event.record_seq, event.event_key


def driver(event: EventInput, earlier_period_end: date) -> str:
    """Late-event precedence applies before the ordinary event-type driver."""
    ordinary = _DRIVERS.get(event.event_type)
    if ordinary is None:
        raise _refuse(f"{event.event_type} needs an explicit replay classification.")
    return "LATE_EVENT" if event.effective_date <= earlier_period_end else ordinary


def _validate(before: InputBundle, after: InputBundle) -> tuple[EventInput, ...]:
    if before.engine_version != ENGINE_VERSION or after.engine_version != ENGINE_VERSION:
        raise _refuse("the retained engine runtime is unavailable.")
    if before.known_at >= after.known_at:
        raise _refuse("the later cutoff must follow the earlier cutoff.")
    # Compare all fields, including future bundle additions, rather than accidentally
    # permitting a new kind of reference change through a fixed allowlist.
    changed = [
        field.name
        for field in fields(before)
        if field.name not in {"events", "known_at", "trigger"}
        and getattr(before, field.name) != getattr(after, field.name)
    ]
    if changed:
        raise _refuse(f"separate reference replay is required for {', '.join(changed)}.")
    for bundle in (before, after):
        if len({event.event_key for event in bundle.events}) != len(bundle.events):
            raise _refuse("event identities are duplicated.")
        if any(event.recorded_at > bundle.known_at for event in bundle.events):
            raise _refuse("an event is recorded after its source cutoff.")
    earlier = {event.event_key: event for event in before.events}
    later = {event.event_key: event for event in after.events}
    if any(later.get(key) != event for key, event in earlier.items()):
        raise _refuse("the later bundle removes or changes an earlier immutable event.")
    added = tuple(sorted((e for e in after.events if e.event_key not in earlier), key=_order))
    if any(event.recorded_at <= before.known_at for event in added):
        raise _refuse("an added event was already known at the earlier cutoff.")
    return added


def _metric_values(values: Metrics) -> dict[MeasureKey, Fraction]:
    result = dict(values)
    if any(not isinstance(key, MeasureKey) for key in result) or any(
        not isinstance(value, Fraction) for value in result.values()
    ):
        raise _refuse("metric projections must use exact, contract/currency-qualified values.")
    return result


def _equal(actual: Metrics, expected: Metrics) -> bool:
    return all(
        actual.get(key, Fraction(0)) == expected.get(key, Fraction(0))
        for key in actual.keys() | expected.keys()
    )


def replay_events(
    before: InputBundle,
    after: InputBundle,
    *,
    earlier_period_end: date,
    earlier_metrics: Metrics,
    later_metrics: Metrics,
    project: Project,
    engine: Engine = compute,
) -> Replay:
    """Execute one compute per maximal same-driver run, then bind every effect.

    The projection must read the same period/measure definitions on every output;
    it is server-owned, never supplied by report request JSON. No database or posting
    writer is called. Any endpoint mismatch aborts the entire decomposition.
    """
    added = _validate(before, after)
    # Validate every classification before executing any potentially expensive work.
    runs = [
        (name, tuple(events))
        for name, events in groupby(added, key=lambda event: driver(event, earlier_period_end))
    ]
    expected_before = _metric_values(earlier_metrics)
    expected_after = _metric_values(later_metrics)
    executions: list[Execution] = []

    def evaluate(
        bundle: InputBundle, name: str, keys: tuple[str, ...]
    ) -> dict[MeasureKey, Fraction]:
        dry = replace(bundle, trigger="DRY_RUN", events=tuple(sorted(bundle.events, key=_order)))
        output = engine(dry)
        if output.engine_version != ENGINE_VERSION or output.input_sha256 != dry.sha256():
            raise _refuse("the engine output does not identify the executed input/runtime.")
        values = _metric_values(project(output))
        executions.append(Execution(name, keys, dry.sha256(), output.sha256()))
        return values

    values = evaluate(before, "BASELINE", ())
    if not _equal(values, expected_before):
        raise _refuse("the earlier replay does not reproduce its frozen monetary endpoint.")
    values = evaluate(replace(before, known_at=after.known_at), "PROGRESS", ())
    states: list[tuple[str, tuple[str, ...], Metrics]] = [("PROGRESS", (), values)]
    accumulated = list(before.events)
    for name, events in runs:
        accumulated.extend(events)
        keys = tuple(event.event_key for event in events)
        values = evaluate(replace(after, events=tuple(accumulated)), name, keys)
        states.append((name, keys, values))
    if not _equal(values, expected_after):
        raise _refuse("the final replay does not reproduce its frozen monetary endpoint.")
    metric_keys = set(expected_before) | set(expected_after)
    for _, _, state in states:
        metric_keys.update(state)
    measures: dict[MeasureKey, Decomposition] = {}
    for key in sorted(metric_keys):
        evaluations: list[Evaluation] = []
        for name, event_keys, state in states:
            # decompose accepts one event key per evaluation. Repeating the final
            # run value preserves all event identities without extra engine calls.
            evaluations.extend(
                Evaluation(name, state.get(key, Fraction(0)), event_key)
                for event_key in (event_keys or (None,))
            )
        result = decompose(expected_before.get(key, Fraction(0)), evaluations)
        if not result.sums_exactly or result.metric_after != expected_after.get(key, Fraction(0)):
            raise _refuse("driver effects do not reconcile to the frozen change.")
        measures[key] = result
    return Replay(ENGINE_VERSION, tuple(executions), measures)
