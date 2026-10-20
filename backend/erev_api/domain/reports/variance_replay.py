"""S15-R-21/23 phased DRY_RUN execution for close variance.

This is the worker-side calculation, not a registered report/job. A caller must
load and authorize retained bundles and supply a metric projection for the fixed
period. Both projected endpoints must agree exactly with the frozen figures.
Reference changes run before events, and FX changes run afterward. Membership and
posting-basis changes still require explicit normalization by the caller.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import date
from fractions import Fraction
from itertools import groupby
from typing import Final, Literal

from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import ContractInput, EventInput, InputBundle, OutputBundle
from erev_engine.stages.s15_disclosures.variance import Decomposition, Evaluation, decompose

from erev_api.problems import Problem

from .variance_measures import MeasureKey
from .variance_projection import MEASURES, Projection
from .variance_reporting import Basis

type Metrics = Mapping[MeasureKey, Fraction]
type Project = Callable[[InputBundle, OutputBundle], Metrics]
type Engine = Callable[[InputBundle], OutputBundle]

REFERENCE_FIELDS: Final = (
    "contracts",
    "books",
    "ssp_versions",
    "pob_template_versions",
    "rule_set_versions",
    "estimate_versions",
)

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
    changed_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class Replay:
    engine_version: str
    executions: tuple[Execution, ...]
    measures: Mapping[MeasureKey, Decomposition]
    reporting_basis_sha256: tuple[str, str] | None = None


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


def validate_contract_basis(
    before: Sequence[ContractInput], after: Sequence[ContractInput]
) -> None:
    """Permit retained record updates without changing the accounting population/basis."""
    old = {contract.external_id: contract for contract in before}
    new = {contract.external_id: contract for contract in after}
    if len(old) != len(before) or len(new) != len(after) or old.keys() != new.keys():
        raise _refuse("contract records require the same unique retained members.")
    for name, previous in old.items():
        current = new[name]
        if any(
            getattr(previous, field) != getattr(current, field)
            for field in (
                "transaction_currency",
                "contracting_entity_code",
                "inception_date",
            )
        ):
            raise _refuse(
                "contract currency, entity or inception changes require a basis migration."
            )


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
        if field.name not in {"events", "known_at", "trigger", "fx_rates", *REFERENCE_FIELDS}
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
    final_project: Project | None = None,
) -> Replay:
    """Execute one compute per maximal same-driver run, then bind every effect.

    The projection must read the same period/measure definitions on every output;
    it is server-owned, never supplied by report request JSON. No database or posting
    writer is called. Any endpoint mismatch aborts the entire decomposition.
    """
    validate_contract_basis(before.contracts, after.contracts)
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
        bundle: InputBundle,
        name: str,
        keys: tuple[str, ...],
        changed: tuple[str, ...] = (),
        projector: Project | None = None,
    ) -> dict[MeasureKey, Fraction]:
        dry = replace(bundle, trigger="DRY_RUN", events=tuple(sorted(bundle.events, key=_order)))
        output = engine(dry)
        if output.engine_version != ENGINE_VERSION or output.input_sha256 != dry.sha256():
            raise _refuse("the engine output does not identify the executed input/runtime.")
        values = _metric_values((projector or project)(dry, output))
        executions.append(Execution(name, keys, dry.sha256(), output.sha256(), changed))
        return values

    values = evaluate(before, "BASELINE", ())
    if not _equal(values, expected_before):
        raise _refuse("the earlier replay does not reproduce its frozen monetary endpoint.")
    values = evaluate(replace(before, known_at=after.known_at), "PROGRESS", ())
    states: list[tuple[str, tuple[str, ...], Metrics]] = [("PROGRESS", (), values)]
    # Apply references together: policies can point at SSP/template/estimate versions
    # introduced in the same source. Splitting these dependencies creates invalid inputs.
    current = replace(before, known_at=after.known_at)
    changed = tuple(
        name for name in REFERENCE_FIELDS if getattr(before, name) != getattr(after, name)
    )
    if changed:
        current = replace(current, **{name: getattr(after, name) for name in changed})
        values = evaluate(current, "OTHER", (), changed)
        states.append(("OTHER", (), values))
    accumulated = list(before.events)
    for name, events in runs:
        accumulated.extend(events)
        keys = tuple(event.event_key for event in events)
        current = replace(current, events=tuple(accumulated))
        values = evaluate(current, name, keys)
        states.append((name, keys, values))
    if before.fx_rates != after.fx_rates:
        current = replace(current, fx_rates=after.fx_rates)
        values = evaluate(current, "FX", (), ("fx_rates",))
        states.append(("FX", (), values))
    if final_project is not None:
        values = evaluate(current, "FX", (), ("reporting_rates",), projector=final_project)
        states.append(("FX", (), values))
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


def replay_period_money(
    before: InputBundle,
    after: InputBundle,
    *,
    entity_code: str,
    book_code: str,
    period_key: str,
    earlier_metrics: Metrics,
    later_metrics: Metrics,
    currency_view: Literal["transaction", "functional", "reporting"] = "transaction",
    earlier_reporting_basis: Basis | None = None,
    later_reporting_basis: Basis | None = None,
    engine: Engine = compute,
) -> Replay:
    """Fixed-period revenue, balance and dated RPO replay over retained inputs."""
    if any(key.measure not in MEASURES for key in earlier_metrics.keys() | later_metrics.keys()):
        raise _refuse("an unsupported monetary measure was requested.")
    validate_reporting_pair(currency_view, earlier_reporting_basis, later_reporting_basis)
    projection = Projection(
        before, entity_code, book_code, period_key, currency_view, earlier_reporting_basis
    )
    entity = next(item for item in before.entities if item.code == entity_code)
    period_end = next(item.end_date for item in entity.periods if item.period_key == period_key)
    result = replay_events(
        before,
        after,
        earlier_period_end=period_end,
        earlier_metrics=earlier_metrics,
        later_metrics=later_metrics,
        project=lambda bundle, output: replace(projection, basis=bundle)(output),
        final_project=(
            lambda bundle, output: replace(
                projection, basis=bundle, reporting_basis=later_reporting_basis
            )(output)
        )
        if currency_view == "reporting"
        else None,
        engine=engine,
    )

    return (
        replace(
            result,
            reporting_basis_sha256=(
                earlier_reporting_basis.evidence_sha256,
                later_reporting_basis.evidence_sha256,
            ),
        )
        if earlier_reporting_basis is not None and later_reporting_basis is not None
        else result
    )


def validate_reporting_pair(view: str, earlier: Basis | None, later: Basis | None) -> None:
    if view != "reporting":
        if earlier is not None or later is not None:
            raise _refuse("reporting rates require reporting currency selection.")
        return
    if earlier is None or later is None:
        raise _refuse("reporting replay requires both retained rate bases.")
    if (earlier.functional_currency, earlier.currency, earlier.period_key, earlier.period_end) != (
        later.functional_currency,
        later.currency,
        later.period_key,
        later.period_end,
    ):
        raise _refuse("reporting currency or period changes require a basis migration.")
