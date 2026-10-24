"""Fixed-basis sequential modification analysis, never a posting allocation.

The caller authorizes the complete retained computation before invoking this pure worker
calculation. The same known-at, references, posted history and FX basis apply to every
counterfactual. An event prefix is an analytical scenario, not an earlier historical snapshot.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction
from typing import Literal

from erev_api.problems import Problem
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import EventInput, InputBundle, OutputBundle

from .variance_measures import MeasureKey
from .variance_projection import Projection
from .variance_replay import Engine, Execution, Metrics, Replay, decompose_steps, driver
from .variance_reporting import Basis


@dataclass(frozen=True)
class Analysis:
    source_input_sha256: str
    source_output_sha256: str
    selected_event_keys: tuple[str, ...]
    entity_code: str
    book_code: str
    period_key: str
    currency_view: str
    replay: Replay


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Modification causal analysis: {detail}")


def calculate(
    source: InputBundle,
    *,
    source_output_sha256: str,
    selected_event_keys: Sequence[str],
    entity_code: str,
    book_code: str,
    period_key: str,
    currency_view: Literal["transaction", "functional", "reporting"] = "functional",
    reporting_basis: Basis | None = None,
    engine: Engine = compute,
) -> Analysis:
    """Reconcile baseline + every event effect to the reproduced period revenue.

    The baseline is the prefix immediately before the earliest selected amendment. All
    subsequent events, including unselected amendments and non-modification events, remain
    separate reconciliation contributors. Offsetting changes are never netted away.
    """
    selected = set(selected_event_keys)
    events = tuple(
        sorted(source.events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))
    )
    indexed = {event.event_key: index for index, event in enumerate(events)}
    if (
        not selected
        or len(selected) != len(selected_event_keys)
        or len(indexed) != len(events)
        or not selected <= indexed.keys()
        or any(
            events[indexed[key]].event_type
            not in {"CONTRACT_AMENDED", "CONTRACT_BOOKED", "REGROUPED", "CONTRACT_TERMINATED"}
            for key in selected
        )
    ):
        raise _refuse("select unique applied modification events from the retained computation.")
    if source.engine_version != ENGINE_VERSION:
        raise _refuse("the retained engine runtime is unavailable.")
    if any(event.recorded_at > source.known_at for event in events):
        raise _refuse("a retained event is later than the source cutoff.")
    first = min(indexed[key] for key in selected)
    additions = events[first:]
    # Validate classifications before expensive execution. No cutoff is fabricated to
    # satisfy the historical-close replay API: this is one fixed-basis causal scenario.
    modifications = {
        item.modification_key: item
        for contract in source.contracts
        for item in contract.modifications
    }

    def causal_driver(event: EventInput) -> str:
        if event.event_type == "CONTRACT_TERMINATED":
            return "MODIFICATION"
        if event.event_type == "REGROUPED":
            retained = modifications.get(
                event.modification_key or str(event.payload.get("modification_id"))
            )
            if (
                (source.evidence_revision or 0) < 37
                or retained is None
                or not (
                    retained.questionnaire.get("regroup_book_lines")
                    and retained.questionnaire.get("regroup_source_basis")
                )
            ):
                raise _refuse("regroup analysis requires retained after-posting transfer evidence.")
            return "MODIFICATION"
        return "NEW_CONTRACT" if event.event_type == "CONTRACT_BOOKED" else driver(event, date.min)

    drivers = tuple(causal_driver(event) for event in additions)
    projection = Projection(
        source,
        entity_code,
        book_code,
        period_key,
        currency_view,
        reporting_basis,
        revenue_only=True,
    )

    def project(bundle: InputBundle, output: OutputBundle) -> dict[MeasureKey, Fraction]:
        values = {
            key: amount
            for key, amount in replace(projection, basis=bundle)(output).items()
            if key.measure == "REVENUE"
        }
        entity = next(e for e in bundle.entities if e.code == entity_code)
        for contract in bundle.contracts:
            if contract.contracting_entity_code != entity_code:
                continue
            currency = (
                contract.transaction_currency
                if currency_view == "transaction"
                else reporting_basis.currency
                if reporting_basis is not None
                else entity.functional_currency
            )
            # A complete reproduced book with no revenue is an explicit zero, including
            # a separate-contract booking that has not yet been activated.
            values.setdefault(MeasureKey(contract.external_id, currency, "REVENUE"), Fraction(0))
        return values

    def execute(bundle: InputBundle) -> OutputBundle:
        output = engine(bundle)
        if output.engine_version != ENGINE_VERSION or output.input_sha256 != bundle.sha256():
            raise _refuse("engine output does not identify its executed input/runtime.")
        return output

    original = execute(source)
    if original.sha256() != source_output_sha256:
        raise _refuse("the original computation does not reproduce its retained output.")
    expected = project(source, original)
    projection = replace(
        projection,
        retained_revenue_subjects=frozenset(
            row.subject_key
            for book in original.books
            if book.book_code == book_code
            for row in book.obligation_versions
        ),
    )
    executions = []

    def evaluate(prefix: int, name: str, keys: tuple[str, ...]) -> Metrics:
        bundle = replace(source, trigger="DRY_RUN", events=events[:prefix])
        output = execute(bundle)
        executions.append(Execution(name, keys, bundle.sha256(), output.sha256()))
        return project(bundle, output)

    baseline = evaluate(first, "BASELINE", ())
    steps = []
    for index, (event, name) in enumerate(zip(additions, drivers, strict=True), start=first):
        keys = (event.event_key,)
        steps.append((name, keys, evaluate(index + 1, name, keys)))
    final = steps[-1][2]
    if any(
        final.get(key, Fraction(0)) != expected.get(key, Fraction(0))
        for key in final.keys() | expected.keys()
    ):
        raise _refuse("the final replay differs from the original period revenue.")
    metric_keys = set(baseline) | set(expected)
    for _, _, state in steps:
        metric_keys.update(state)
    measures = {
        key: decompose_steps(
            baseline.get(key, Fraction(0)),
            [(name, keys, state.get(key, Fraction(0))) for name, keys, state in steps],
            event_details=True,
        )
        for key in sorted(metric_keys)
    }
    if any(
        not value.sums_exactly or value.metric_after != expected.get(key, Fraction(0))
        for key, value in measures.items()
    ):
        raise _refuse("event effects do not reconcile to the original period revenue.")
    return Analysis(
        source.sha256(),
        source_output_sha256,
        tuple(event.event_key for event in events if event.event_key in selected),
        entity_code,
        book_code,
        period_key,
        currency_view,
        Replay(
            ENGINE_VERSION,
            tuple(executions),
            measures,
            (reporting_basis.evidence_sha256, reporting_basis.evidence_sha256)
            if reporting_basis is not None
            else None,
        ),
    )
