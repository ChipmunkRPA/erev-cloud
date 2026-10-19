"""Real engine event replay and fail-closed frozen endpoint reconciliation."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import cast

import pytest
from erev_api.domain.reports.variance_measures import MeasureKey
from erev_api.domain.reports.variance_replay import replay_events
from erev_api.problems import Problem
from erev_engine import compute
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from support import golden_streams

KEY = MeasureKey("Contract 2", "USD", "CONTRACT_LIABILITY")


def _pair() -> tuple[InputBundle, InputBundle]:
    before = golden_streams.stream("Contract 2", "07").input_bundle()
    template = next(event for event in before.events if event.event_type == "BILLING_RECORDED")
    additions = []
    for sequence, amount in ((9, "100"), (10, "50")):
        identity = f"variance-invoice-{sequence}"
        payload = {
            **template.payload,
            "invoice_number": identity,
            "line_external_id": identity,
            "source_invoice_id": identity,
            "amount": Decimal(amount),
        }
        additions.append(
            replace(
                template,
                event_key=f"Contract 2/EV-{sequence:06}",
                record_seq=sequence,
                stream_version=sequence,
                recorded_at=before.known_at + timedelta(hours=1),
                payload=payload,
                payload_sha256=sha256_hex(payload),
            )
        )
    return before, replace(
        before,
        known_at=before.known_at + timedelta(days=1),
        # The service must establish ENG-06 order itself.
        events=(*before.events, *reversed(additions)),
    )


def _project(output: OutputBundle) -> dict[MeasureKey, Fraction]:
    book = next(book for book in output.books if book.book_code == "ASC606")
    row = next(
        row
        for row in book.balances
        if row.subject_key == "Contract 2@Mock Entity 2" and row.period_key == "FY2023-P04"
    )
    return {KEY: Fraction(cast(int, row.columns["contract_liability_txn"]), 100)}


def test_real_engine_replays_one_maximal_run_and_retains_event_provenance() -> None:
    before, after = _pair()
    calls = []

    def engine(bundle: InputBundle) -> OutputBundle:
        calls.append(bundle)
        return compute(bundle)

    result = replay_events(
        before,
        after,
        earlier_period_end=date(2023, 4, 30),
        earlier_metrics={KEY: Fraction(20)},
        later_metrics={KEY: Fraction(170)},
        project=_project,
        engine=engine,
    )
    assert len(calls) == 3  # baseline, time, one run of two late billing events
    assert all(bundle.trigger == "DRY_RUN" for bundle in calls)
    assert before.trigger == after.trigger == "COMMAND"
    decomposition = result.measures[KEY]
    assert [(effect.driver, effect.amount) for effect in decomposition.effects] == [
        ("PROGRESS", Fraction(0)),
        ("LATE_EVENT", Fraction(150)),
    ]
    assert decomposition.effects[1].event_keys == ("Contract 2/EV-000009", "Contract 2/EV-000010")
    assert decomposition.sums_exactly
    assert result.executions[-1].input_sha256 == calls[-1].sha256()
    assert len(result.executions[-1].output_sha256) == 64


@pytest.mark.parametrize("endpoint", ["earlier", "later"])
def test_endpoint_mismatch_is_not_an_other_residual(endpoint: str) -> None:
    before, after = _pair()
    with pytest.raises(Problem, match=f"{'earlier' if endpoint == 'earlier' else 'final'} replay"):
        replay_events(
            before,
            after,
            earlier_period_end=date(2023, 4, 30),
            earlier_metrics={KEY: Fraction(21 if endpoint == "earlier" else 20)},
            later_metrics={KEY: Fraction(171 if endpoint == "later" else 170)},
            project=_project,
        )


@pytest.mark.parametrize(
    "fault", ["runtime", "reference", "mutated", "duplicate", "cutoff", "classification"]
)
def test_bad_plan_refuses_before_engine_execution(fault: str) -> None:
    before, after = _pair()
    if fault == "runtime":
        after = replace(after, engine_version="unavailable-runtime")
    elif fault == "reference":
        after = replace(after, tenant_preset="DEFAULT")
    elif fault == "mutated":
        after = replace(after, events=after.events[1:])
    elif fault == "duplicate":
        after = replace(after, events=(*after.events, after.events[0]))
    elif fault == "cutoff":
        after = replace(after, known_at=before.known_at)
    else:
        after = replace(
            after, events=(*after.events[:-1], replace(after.events[-1], event_type="EVENT_VOIDED"))
        )

    def forbidden(bundle: InputBundle) -> OutputBundle:
        pytest.fail("invalid replay inputs must be rejected before compute")

    with pytest.raises(Problem):
        replay_events(
            before,
            after,
            earlier_period_end=date(2023, 4, 30),
            earlier_metrics={KEY: Fraction(20)},
            later_metrics={KEY: Fraction(170)},
            project=_project,
            engine=forbidden,
        )
