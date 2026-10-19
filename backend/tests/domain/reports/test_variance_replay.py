"""Real engine event replay and fail-closed frozen endpoint reconciliation."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import cast

import pytest
from erev_api.domain.reports.variance_measures import MeasureKey
from erev_api.domain.reports.variance_projection import Projection
from erev_api.domain.reports.variance_replay import replay_events, replay_period_money
from erev_api.problems import Problem
from erev_engine import compute
from erev_engine.bundle import (
    InputBundle,
    IntentLine,
    OutputBundle,
    PostedAmountInput,
    PostingIntent,
)
from erev_engine.canonical import sha256_hex
from support import bundles, golden_streams

KEY = MeasureKey("Contract 2", "USD", "CONTRACT_LIABILITY")
RPO = MeasureKey("Contract 2", "USD", "RPO")


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


def _project(bundle: InputBundle, output: OutputBundle) -> dict[MeasureKey, Fraction]:
    book = next(book for book in output.books if book.book_code == "ASC606")
    row = next(
        row
        for row in book.balances
        if row.subject_key == "Contract 2@Mock Entity 2" and row.period_key == "FY2023-P04"
    )
    return {KEY: Fraction(cast(int, row.columns["contract_liability_txn"]), 100)}


def _active_pair() -> tuple[InputBundle, InputBundle]:
    before, _ = _pair()
    activated = bundles.event(
        "Contract 2",
        9,
        "CONTRACT_ACTIVATED",
        before.contracts[0].inception_date,
        {"checklist": {}},
    )
    activated = replace(activated, recorded_at=before.known_at)
    before = replace(
        before,
        known_at=datetime(2023, 6, 1, tzinfo=UTC),
        events=tuple(
            sorted(
                (*before.events, activated),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    delivered = bundles.event(
        "Contract 2",
        10,
        "DELIVERY_RECORDED",
        date(2023, 5, 31),
        {"obligation_key": "POB #1", "quantity": Decimal(1), "trigger": "CONTROL_TRANSFER"},
        obligation_keys=["POB #1"],
    )
    after = replace(
        before,
        known_at=datetime(2023, 6, 3, tzinfo=UTC),
        events=(*before.events, replace(delivered, recorded_at=datetime(2023, 6, 2, tzinfo=UTC))),
    )
    return before, after


def test_dated_rpo_and_revenue_changes_reconcile_through_real_replay() -> None:
    before, after = _active_pair()
    output = compute(after)
    assert Projection(after, "Mock Entity 2", "ASC606", "FY2023-P04")(output)[RPO] == 795
    assert Projection(after, "Mock Entity 2", "ASC606", "FY2023-P05")(output)[RPO] == Fraction(
        "736.16"
    )
    asset = MeasureKey("Contract 2", "USD", "CONTRACT_ASSET_AND_UNBILLED")
    revenue = MeasureKey("Contract 2", "USD", "REVENUE")
    result = replay_period_money(
        before,
        after,
        entity_code="Mock Entity 2",
        book_code="ASC606",
        period_key="FY2023-P05",
        earlier_metrics={asset: Fraction(85), RPO: Fraction(795)},
        later_metrics={
            asset: Fraction("143.84"),
            revenue: Fraction("58.84"),
            RPO: Fraction("736.16"),
        },
    )
    assert result.measures[RPO].total == -result.measures[revenue].total == Fraction("-58.84")
    assert result.measures[RPO].effects[-1].driver == "LATE_EVENT"


def test_dated_rpo_honors_duration_exemption_from_retained_policy() -> None:
    _, after = _active_pair()
    book = after.books[0]
    after = replace(
        after,
        books=(
            replace(
                book,
                policies=tuple(
                    replace(policy, value="APPLY")
                    if policy.code == "rpo.exemption_original_duration_one_year"
                    else policy
                    for policy in book.policies
                ),
            ),
        ),
    )
    values = Projection(after, "Mock Entity 2", "ASC606", "FY2023-P05")(compute(after))
    assert RPO not in values


def test_replay_rpo_uses_each_executed_bundles_entry_events() -> None:
    before, _ = _pair()
    activated = bundles.event(
        "Contract 2",
        9,
        "CONTRACT_ACTIVATED",
        before.contracts[0].inception_date,
        {"checklist": {}},
    )
    after = replace(
        before,
        known_at=before.known_at + timedelta(days=1),
        events=(
            *before.events,
            replace(activated, recorded_at=before.known_at + timedelta(hours=1)),
        ),
    )
    result = replay_period_money(
        before,
        after,
        entity_code="Mock Entity 2",
        book_code="ASC606",
        period_key="FY2023-P04",
        earlier_metrics={KEY: Fraction(20)},
        later_metrics={
            MeasureKey("Contract 2", "USD", "CONTRACT_ASSET_AND_UNBILLED"): Fraction(85),
            RPO: Fraction(795),
        },
    )
    assert result.measures[RPO].total == 795
    assert result.measures[RPO].effects[-1].event_keys == (activated.event_key,)


def test_dated_rpo_refuses_missing_measurement_trace() -> None:
    _, after = _active_pair()
    output = compute(after)
    book = output.books[0]
    output = replace(
        output,
        books=(
            replace(
                book,
                trace=replace(
                    book.trace,
                    nodes=tuple(node for node in book.trace.nodes if node.measure != "revenue_cum"),
                ),
            ),
        ),
    )
    with pytest.raises(Problem):
        Projection(after, "Mock Entity 2", "ASC606", "FY2023-P04")(output)


def test_real_engine_replays_one_maximal_run_and_retains_event_provenance() -> None:
    before, after = _pair()
    calls = []

    def engine(bundle: InputBundle) -> OutputBundle:
        calls.append(bundle)
        return compute(bundle)

    result = replay_period_money(
        before,
        after,
        entity_code="Mock Entity 2",
        book_code="ASC606",
        period_key="FY2023-P04",
        earlier_metrics={KEY: Fraction(20)},
        later_metrics={KEY: Fraction(170)},
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


def test_projection_uses_posting_period_and_signed_revenue_without_double_counting() -> None:
    basis, _ = _pair()
    output = compute(basis)
    book = output.books[0]
    subject = book.obligation_versions[0].subject_key
    posted = PostedAmountInput(
        book_code="ASC606",
        entity_code="Mock Entity 2",
        subject_key=subject,
        entry_kind="REVENUE",
        account_role="REVENUE",
        clearing_purpose=None,
        counterparty_entity_code=None,
        period_key="FY2023-P04",
        origin_period_key=None,
        posting_class="TIME",
        txn_currency="USD",
        functional_currency="USD",
        amount_txn=-10000,
        amount_functional=-10000,
    )
    basis = replace(basis, posted=(posted,))
    revenue_line = IntentLine(
        line_key="credit:revenue",
        side="C",
        account_role="REVENUE",
        clearing_purpose=None,
        counterparty_entity=None,
        account_code="4000",
        amount_txn=5000,
        amount_functional=5000,
        txn_currency="USD",
        functional_currency="USD",
        dimensions={},
        source_event_key=None,
        trace_node_id="projection-test:revenue",
    )
    credit = PostingIntent(
        entry_key="credit",
        book_code="ASC606",
        entity="Mock Entity 2",
        subject_key=subject,
        entry_kind="REVENUE",
        posting_class="TIME",
        reason_code=None,
        posting_period_key="FY2023-P04",
        origin_period_key=None,
        lines=(revenue_line,),
    )
    reversal = replace(
        credit,
        entry_key="reversal",
        origin_period_key="FY2023-P03",
        lines=(replace(credit.lines[0], side="D", amount_txn=2000, amount_functional=2000),),
    )
    later = replace(credit, entry_key="later", posting_period_key="FY2023-P05")
    output = replace(output, books=(replace(book, posting_intents=(credit, reversal, later)),))
    projection = Projection(basis, "Mock Entity 2", "ASC606", "FY2023-P04")
    revenue = MeasureKey("Contract 2", "USD", "REVENUE")
    assert projection(output)[revenue] == Fraction(130)  # 100 posted + 50 credit - 20 debit
    assert replace(projection, currency_view="functional")(output)[revenue] == Fraction(130)


@pytest.mark.parametrize("fault", ["duplicate", "missing_amount", "currency", "entity"])
def test_projection_refuses_inconsistent_balance_rows(fault: str) -> None:
    basis, _ = _pair()
    output = compute(basis)
    book = output.books[0]
    row = next(row for row in book.balances if row.period_key == "FY2023-P04")
    others = tuple(item for item in book.balances if item is not row)
    columns = dict(row.columns)
    if fault == "missing_amount":
        del columns["contract_liability_txn"]
    elif fault == "currency":
        columns["txn_currency"] = "EUR"
    elif fault == "entity":
        columns["entity"] = "ANOTHER"
    changed = replace(row, columns=columns)
    balances = (*others, changed, changed) if fault == "duplicate" else (*others, changed)
    output = replace(output, books=(replace(book, balances=balances),))
    with pytest.raises(Problem):
        Projection(basis, "Mock Entity 2", "ASC606", "FY2023-P04")(output)


def test_period_money_adapter_refuses_unknown_projection_measure() -> None:
    before, after = _pair()
    with pytest.raises(Problem, match="unsupported monetary measure"):
        replay_period_money(
            before,
            after,
            entity_code="Mock Entity 2",
            book_code="ASC606",
            period_key="FY2023-P04",
            earlier_metrics={},
            later_metrics={MeasureKey("Contract 2", "USD", "UNKNOWN"): Fraction(1)},
        )


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
