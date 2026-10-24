"""Real engine event replay and fail-closed frozen endpoint reconciliation."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import cast

import pytest
from support import bundles, golden_streams

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


@pytest.mark.parametrize("event_details", [False, True])
def test_real_engine_replay_supports_driver_and_event_detail(event_details: bool) -> None:
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
        event_details=event_details,
    )
    assert len(calls) == (4 if event_details else 3)
    assert all(bundle.trigger == "DRY_RUN" for bundle in calls)
    assert before.trigger == after.trigger == "COMMAND"
    decomposition = result.measures[KEY]
    assert [(effect.driver, effect.amount) for effect in decomposition.effects] == (
        [("PROGRESS", Fraction(0)), ("LATE_EVENT", Fraction(100)), ("LATE_EVENT", Fraction(50))]
        if event_details
        else [("PROGRESS", Fraction(0)), ("LATE_EVENT", Fraction(150))]
    )
    assert tuple(key for effect in decomposition.effects for key in effect.event_keys) == (
        "Contract 2/EV-000009",
        "Contract 2/EV-000010",
    )
    if event_details:
        assert all(len(effect.event_keys) == 1 for effect in decomposition.effects[1:])
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


def test_retained_execution_checks_originals_and_preserves_event_effects() -> None:
    from uuid import uuid4

    from erev_api.domain.reports.computation_sources import VerifiedComputation
    from erev_api.domain.reports.variance_execution import RetainedReplay, execute
    from erev_engine import upgrade

    before, after = _active_pair()
    group_id, release_id = uuid4(), uuid4()

    def source(bundle: InputBundle) -> VerifiedComputation:
        output = compute(bundle)
        return VerifiedComputation(
            uuid4(),
            group_id,
            release_id,
            bundle,
            upgrade.output_mapping(output),
            output.sha256(),
            {"ASC606": 0},
            None,
        )

    # Simulate persistence of the earlier output before the later computation.
    carried = tuple(
        PostedAmountInput(
            book_code=intent.book_code,
            entity_code=intent.entity,
            subject_key=intent.subject_key,
            entry_kind=intent.entry_kind,
            account_role=line.account_role,
            clearing_purpose=line.clearing_purpose,
            counterparty_entity_code=line.counterparty_entity,
            period_key=intent.posting_period_key,
            origin_period_key=intent.origin_period_key,
            posting_class=intent.posting_class,
            txn_currency=line.txn_currency,
            functional_currency=line.functional_currency,
            amount_txn=line.amount_txn * (1 if line.side == "D" else -1),
            amount_functional=line.amount_functional * (1 if line.side == "D" else -1),
            reason_code=intent.reason_code,
            rate_refs=(),
        )
        for book in compute(before).books
        for intent in book.posting_intents
        for line in intent.lines
    )
    after = replace(
        after,
        posted=(*before.posted, *carried),
        group=replace(after.group, previous_stream_heads=(("Contract 2", 9),)),
    )
    earlier, later = source(before), source(after)
    first = Projection(before, "Mock Entity 2", "ASC606", "FY2023-P05")(compute(before))
    last = Projection(after, "Mock Entity 2", "ASC606", "FY2023-P05")(compute(after))

    def run(
        left: VerifiedComputation, right: VerifiedComputation, end: dict[MeasureKey, Fraction]
    ) -> RetainedReplay:
        return execute(
            left,
            right,
            entity_code="Mock Entity 2",
            book_code="ASC606",
            period_key="FY2023-P05",
            earlier_metrics=first,
            later_metrics=end,
        )

    result = run(earlier, later, last)
    assert result.replay.measures[RPO].total == Fraction("-58.84")
    assert result.normalized_fields == ("posted", "group.previous_stream_heads")
    assert result.earlier.output_sha256 == earlier.output_sha256
    unchanged = run(earlier, earlier, first)
    assert unchanged.replay.executions == ()
    assert all(item.total == 0 for item in unchanged.replay.measures.values())
    with pytest.raises(Problem, match="retained output"):
        run(earlier, replace(later, output_sha256="0" * 64), last)
    with pytest.raises(Problem, match="frozen endpoint"):
        run(earlier, later, {**last, RPO: last[RPO] + 1})


def test_group_replay_reconciles_two_contracts_to_frozen_datasets() -> None:
    """Real engine execution; authored frozen CSVs, not a full lock workflow."""
    import csv
    import hashlib
    from io import StringIO
    from uuid import UUID, uuid4

    from erev_api.domain.reports import locked, variance_groups
    from erev_api.domain.reports.computation_sources import VerifiedComputation
    from erev_api.domain.reports.evidence_close import FrozenClose, FrozenReport
    from erev_api.domain.reports.variance_sources import Pair, Side
    from erev_engine import upgrade

    before, after = _active_pair()
    entity_id, period_id = uuid4(), uuid4()
    group_ids = [uuid4(), uuid4()]
    release_id = uuid4()

    def side(
        bundle: InputBundle,
        day: int,
        keep: tuple[int, ...] = (0, 1),
        prepared: tuple[tuple[UUID, InputBundle], ...] | None = None,
    ) -> Side:
        scope = locked.LockScope(
            uuid4(), entity_id, "Mock Entity 2", "ASC606", period_id, "FY2023-P05"
        )
        sources: dict[UUID, VerifiedComputation] = {}
        contracts = {}
        amounts = {}
        inputs = (
            prepared
            if prepared is not None
            else tuple(
                (
                    group_id,
                    upgrade.decode_input(
                        upgrade.encode_input(bundle).replace(
                            b"Contract 2", f"Contract {number}".encode()
                        )
                    ),
                )
                for number, group_id in enumerate(group_ids, start=2)
                if number - 2 in keep
            )
        )
        for group_id, named in inputs:
            output = compute(named)
            identity = uuid4()
            sources[identity] = VerifiedComputation(
                identity,
                group_id,
                release_id,
                named,
                upgrade.output_mapping(output),
                output.sha256(),
                {"ASC606": 0},
                None,
            )
            contracts.update({name: identity for name in named.group.member_contract_keys})
            amounts.update(
                Projection(named, scope.entity_code, scope.book_code, scope.period_key)(output)
            )
        common = ["row_key", "entity_code", "contract_external_id", "currency"]
        reports = []
        for kind, extra in (
            ("WATERFALL", ["obligation_key", "period_key", "recognised"]),
            ("CONTRACT_BALANCES", ["contract_liability", "contract_asset", "unbilled_receivable"]),
            ("RPO", ["obligation_key", "section", "total"]),
        ):
            stream = StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(common + extra)
            for name in contracts:

                def amount(measure: str, contract_name: str = name) -> str:
                    value = amounts.get(MeasureKey(contract_name, "USD", measure), Fraction(0))
                    return str(Decimal(value.numerator) / Decimal(value.denominator))

                values = (
                    ["O1", scope.period_key, amount("REVENUE")]
                    if kind == "WATERFALL"
                    else [amount("CONTRACT_LIABILITY"), amount("CONTRACT_ASSET_AND_UNBILLED"), "0"]
                    if kind == "CONTRACT_BALANCES"
                    else ["O1", "1", amount("RPO")]
                )
                writer.writerow([f"{kind}:{name}", scope.entity_code, name, "USD", *values])
            content = stream.getvalue().encode()
            dataset = locked.LockedDataset(
                scope.lock_id,
                kind,
                uuid4(),
                hashlib.sha256(content).hexdigest(),
                len(contracts),
                {},
                content,
            )
            from erev_api.domain.reports import snapshot_views
            from erev_engine.stages.s15_disclosures import snapshots as snapshot_engine

            fact = {
                "base_currency": "USD",
                "quote_currency": "USD",
                "period_key": scope.period_key,
                "period_end": "2023-05-31",
                "rate": "1",
                "rate_id": None,
                "version_id": None,
                "rate_cutoff": "2023-06-01T00:00:00+00:00",
            }
            controls = {
                "reporting_currency": "USD",
                "translation_rates": [
                    {**fact, "rate_type": "closing"},
                    *([{**fact, "rate_type": "average"}] if kind == "WATERFALL" else []),
                ],
            }
            variant = snapshot_engine.Encoded(
                kind, content, dataset.file_sha256, len(contracts), controls
            )
            packed = snapshot_views.pack({view: variant for view in snapshot_views.VIEWS})
            dataset = replace(
                dataset,
                content=packed.content,
                file_sha256=packed.file_sha256,
                row_count=packed.row_count,
                control_totals=packed.control_totals,
            )
            reports.append(FrozenReport(kind, uuid4(), None, dataset))
        frozen = FrozenClose(
            scope,
            {
                "created_at": datetime(2023, 6, day, tzinfo=UTC),
                "snapshot_manifest_sha256": "a" * 64,
            },
            tuple(reports),
        )
        return Side(frozen, sources, contracts)

    pair = Pair(side(before, 1), side(after, 3), (entity_id,))
    result = variance_groups.execute(pair)
    assert len(result.groups) == 2
    assert result.required_entity_ids == (entity_id,)
    assert result.driver_totals[("USD", "RPO", "LATE_EVENT")] == Fraction("-117.68")
    assert result.driver_totals[("USD", "REVENUE", "LATE_EVENT")] == Fraction("117.68")
    assert all(item.sums_exactly for item in result.measures.values())
    from erev_api.domain.reports import variance_presentation
    from erev_api.domain.reports.outputs import RunStamp
    from erev_api.domain.reports.outputs.csv import render_csv
    from erev_api.domain.reports.outputs.pdf import render_pdf
    from erev_api.domain.reports.outputs.xlsx import render_xlsx
    from erev_engine.canonical import canonical_bytes

    functional = variance_groups.execute(pair, currency_view="functional")
    assert functional.measures == result.measures
    projected = variance_presentation.dataset(pair, functional)
    assert projected.data.control_totals["currency_view"] == "functional"
    assert projected.evidence["currency_view"] == "functional"
    reporting = variance_groups.execute(pair, currency_view="reporting")
    reported = variance_presentation.dataset(pair, reporting)
    assert reported.data.control_totals["USD:REVENUE"] == "117.68"
    assert all(run.replay.reporting_basis_sha256 for run in reporting.groups.values())
    presentation = variance_presentation.dataset(pair, result)
    data = presentation.data
    contract_rows = [
        row for row in data.rows if row["section"] == 2 and not row["row_key"].startswith("TOTAL:")
    ]
    assert len(contract_rows) == 6
    totals = [row for row in data.rows if row["row_key"].startswith("TOTAL:")]
    assert len(totals) == 6
    assert {row["change"]["amount"] for row in totals if row["measure"] == "REVENUE"} == {"117.68"}
    assert {row["change"]["amount"] for row in totals if row["measure"] == "RPO"} == {"-117.68"}
    assert data.control_totals["USD:REVENUE"] == "117.68"
    assert data.control_totals["USD:RPO"] == "-117.68"
    assert len(presentation.evidence["groups"]) == 2
    for row in contract_rows:
        assert row["driver_label"] == "Late events"
        evidence = presentation.evidence["contributors"][row["row_key"]]
        assert evidence["earlier_source_rows"]
        assert evidence["later_source_rows"]
        assert evidence["effects"][-1]["event_keys"]
    summary_rows = [
        row for row in data.rows if row["section"] == 1 and not row["row_key"].startswith("TOTAL:")
    ]
    for row in summary_rows:
        assert len(presentation.evidence["contributors"][row["row_key"]]["contracts"]) == 2
    csv_output = render_csv(data)
    assert b"Late events" in csv_output
    assert b"Change by driver" in csv_output
    assert b"-117.68" in csv_output
    stamp = RunStamp(
        "variance_between_closes",
        "Variance between closes",
        1,
        "RPT-TEST",
        {
            "from_period_lock_id": str(pair.earlier.frozen.scope.lock_id),
            "to_period_lock_id": str(pair.later.frozen.scope.lock_id),
        },
        ("Mock Entity 2",),
        "ASC606",
        "FY2023-P05",
        "Frozen close comparison",
        before.engine_version,
        "test",
        "Accountant",
        before.known_at,
        "0" * 64,
    )
    assert render_xlsx(data, stamp).startswith(b"PK")
    pdf = render_pdf(data, stamp)
    assert pdf.startswith(b"%PDF")
    assert str(pair.earlier.frozen.scope.lock_id).encode() in pdf
    assert str(pair.later.frozen.scope.lock_id).encode() in pdf
    assert canonical_bytes(presentation.evidence)
    from types import SimpleNamespace
    from typing import Any

    from sqlalchemy.orm import Session

    from erev_api.domain.reports import variance_cells
    from erev_api.domain.reports.builders import ADAPTER, ReportParams, SourceBinding

    def identities(value: Pair) -> list[dict[str, Any]]:
        sides: list[dict[str, Any]] = []
        for source_side in (value.earlier, value.later):
            sides.append(
                {
                    "lock_id": str(source_side.frozen.scope.lock_id),
                    "contracts": {
                        name: str(identity)
                        for name, identity in source_side.contract_computations.items()
                    },
                    "computations": {
                        str(identity): {
                            "group_id": str(source.group_id),
                            "input_sha256": source.bundle.sha256(),
                            "output_sha256": source.output_sha256,
                        }
                        for identity, source in source_side.computations.items()
                    },
                }
            )
        return sides

    sides = identities(pair)
    binding = SourceBinding(
        cutoff=after.known_at,
        versions={},
        labels={},
        row_keys=frozenset(row["row_key"] for row in data.rows),
        strategy=ADAPTER,
        report_version=1,
        evidence={
            "close_variance_sources": {
                "version": 1,
                "sides": sides,
                "required_entity_ids": [str(entity_id)],
            },
            "close_variance_contributors": presentation.evidence,
            "close_variance_evidence_sha256": sha256_hex(presentation.evidence),
        },
    )
    params = ReportParams(
        "variance_between_closes",
        1,
        {"from_period_lock_id": sides[0]["lock_id"], "to_period_lock_id": sides[1]["lock_id"]},
        (entity_id,),
        after.known_at,
        book_code="ASC606",
        binding=binding,
    )
    contract_ids = {name: uuid4() for name in pair.later.contract_computations}

    class Lookup:
        def execute(self, statement: Any) -> Any:
            filters = statement.compile().params
            name = filters["external_id_1"]
            assert str(filters["contract_computation_id_1"]) == sides[1]["contracts"][name]
            assert filters["book_code_1"] == "ASC606"
            return SimpleNamespace(scalar_one_or_none=lambda: contract_ids[name])

    for row in (*contract_rows, *summary_rows):
        value, items = variance_cells.cell(
            cast(Session, Lookup()), params, row["row_key"], "change"
        )
        assert value == row["change"]
        assert sum((Fraction(item["value"]["amount"]) for item in items), Fraction(0)) == Fraction(
            value["amount"]
        )
        assert all(item["object_type"] == "contract" for item in items)
        assert all(any(detail.startswith("Event:") for detail in item["details"]) for item in items)
    with pytest.raises(Problem):
        variance_cells.cell(
            cast(Session, Lookup()),
            replace(params, parameters={**params.parameters, "currency_view": "functional"}),
            contract_rows[0]["row_key"],
            "change",
        )
    invalid = replace(
        binding, evidence={**binding.evidence, "close_variance_evidence_sha256": "0" * 64}
    )
    with pytest.raises(Problem, match="contributors are unavailable"):
        variance_cells.cell(
            cast(Session, Lookup()),
            replace(params, binding=invalid),
            contract_rows[0]["row_key"],
            "change",
        )
    with pytest.raises(Problem, match="below the currency"):
        variance_presentation._money(Fraction(1, 1000), "USD")
    with pytest.raises(Problem, match="access scope"):
        variance_presentation.dataset(pair, replace(result, required_entity_ids=()))
    with pytest.raises(Problem, match="driver totals differ"):
        variance_presentation.dataset(pair, replace(result, driver_totals={}))
    with pytest.raises(Problem, match="no retained source"):
        variance_groups.execute(replace(pair, later=replace(pair.later, contract_computations={})))

    # Presentation witnesses: unchanged endpoints can still have opposing
    # intermediate effects. Do not make those facts disappear from the drill path.
    from erev_engine.stages.s15_disclosures.variance import (
        Decomposition,
        DriverEffect,
        totals_by_driver,
    )

    zero_pair = Pair(
        side(before, 1), side(replace(before, known_at=after.known_at), 3), (entity_id,)
    )
    unchanged = variance_groups.execute(zero_pair)
    assert not variance_presentation.dataset(zero_pair, unchanged).data.rows
    for same_driver in (False, True):
        changed_measures = dict(unchanged.measures)
        changed_groups = dict(unchanged.groups)
        driver_totals = dict(unchanged.driver_totals)
        for index, key in enumerate(sorted(k for k in changed_measures if k.measure == "REVENUE")):
            was = changed_measures[key].metric_before
            amount = Fraction(25 if index == 0 else -25)
            effects = (
                DriverEffect("MODIFICATION", amount, (f"change-{index}-1",), was + amount),
                DriverEffect(
                    "PROGRESS",
                    Fraction(0) if same_driver else -amount,
                    (),
                    was + amount if same_driver else was,
                ),
                *(
                    (DriverEffect("MODIFICATION", -amount, (f"change-{index}-2",), was),)
                    if same_driver
                    else ()
                ),
            )
            measured = Decomposition(was, was, effects)
            changed_measures[key] = measured
            source_id = zero_pair.later.contract_computations[key.contract_external_id]
            group_id = zero_pair.later.computations[source_id].group_id
            original = changed_groups[group_id]
            changed_groups[group_id] = replace(
                original,
                replay=replace(
                    original.replay, measures={**original.replay.measures, key: measured}
                ),
            )
            for driver, amount in totals_by_driver(effects).items():
                identity = (key.currency, key.measure, driver)
                driver_totals[identity] = driver_totals.get(identity, Fraction(0)) + amount
        offset = replace(
            unchanged, measures=changed_measures, groups=changed_groups, driver_totals=driver_totals
        )
        assert not variance_presentation.dataset(zero_pair, offset, retain_offsets=False).data.rows
        shown = variance_presentation.dataset(zero_pair, offset)
        detail_rows = [
            row
            for row in shown.data.rows
            if row["section"] == 2 and not row["row_key"].startswith("TOTAL:")
        ]
        driver_rows = [
            row
            for row in shown.data.rows
            if row["section"] == 1 and not row["row_key"].startswith("TOTAL:")
        ]
        assert len(detail_rows) == 2
        assert len(driver_rows) == (1 if same_driver else 2)
        assert all(row["change"]["amount"] == "0.00" for row in shown.data.rows)
        assert all("Modifications" in row["driver_label"] for row in detail_rows)
        for row in driver_rows:
            held = shown.evidence["contributors"][row["row_key"]]["contracts"]
            assert len(held) == 2
            assert any(
                Fraction(effect["change"]["amount"]) for item in held for effect in item["effects"]
            )
        # Use the original source-scope checks on the newly retained zero rows.
        zero_sides = identities(zero_pair)
        zero_binding = replace(
            binding,
            row_keys=frozenset(row["row_key"] for row in shown.data.rows),
            evidence={
                "close_variance_sources": {
                    "version": 1,
                    "sides": zero_sides,
                    "required_entity_ids": [str(entity_id)],
                },
                "close_variance_contributors": shown.evidence,
                "close_variance_evidence_sha256": sha256_hex(shown.evidence),
            },
        )
        zero_params = replace(
            params,
            binding=zero_binding,
            parameters={
                "from_period_lock_id": zero_sides[0]["lock_id"],
                "to_period_lock_id": zero_sides[1]["lock_id"],
            },
        )

        class ZeroLookup:
            def execute(self, statement):
                name = statement.compile().params["external_id_1"]
                return SimpleNamespace(scalar_one_or_none=lambda: contract_ids[name])

        for row in (*detail_rows, *driver_rows):
            value, items = variance_cells.cell(
                cast(Session, ZeroLookup()), zero_params, row["row_key"], "change"
            )
            assert value["amount"] == "0.00"
            assert any("25.00 USD" in detail for item in items for detail in item["details"])

        # A retained driver's internal effects must reconcile, even when its
        # overall amount is zero and the outer evidence hash is self-consistent.
        import copy

        broken = copy.deepcopy(shown.evidence)
        chosen = driver_rows[0]["row_key"]
        broken["contributors"][chosen]["contracts"][0]["effects"][0]["change"]["amount"] = "99.00"
        broken_binding = replace(
            zero_binding,
            evidence={
                **zero_binding.evidence,
                "close_variance_contributors": broken,
                "close_variance_evidence_sha256": sha256_hex(broken),
            },
        )
        with pytest.raises(Problem, match="contributors are unavailable"):
            variance_cells.cell(
                cast(Session, ZeroLookup()),
                replace(zero_params, binding=broken_binding),
                chosen,
                "change",
            )

    for entering in (True, False):
        population_pair = Pair(
            side(before, 1, (0,) if entering else (0, 1)),
            side(after, 3, (0, 1) if entering else (0,)),
            (entity_id,),
        )
        population = variance_groups.execute(population_pair)
        rendered = variance_presentation.dataset(population_pair, population)
        evidence = rendered.evidence["groups"][str(group_ids[1])]
        absent = "earlier" if entering else "later"
        assert evidence[absent] is None
        assert evidence["executions"][0]["changed_fields"] == (
            "population.entered" if entering else "population.left",
        )
        pop_sides = identities(population_pair)
        pop_binding = replace(
            binding,
            evidence={
                "close_variance_sources": {
                    "version": 1,
                    "sides": pop_sides,
                    "required_entity_ids": [str(entity_id)],
                },
                "close_variance_contributors": rendered.evidence,
                "close_variance_evidence_sha256": sha256_hex(rendered.evidence),
            },
        )
        pop_params = replace(
            params,
            binding=pop_binding,
            parameters={
                "from_period_lock_id": pop_sides[0]["lock_id"],
                "to_period_lock_id": pop_sides[1]["lock_id"],
            },
        )

        class PopulationLookup:
            def __init__(self, records: list[dict[str, Any]]) -> None:
                self.records = records

            def execute(self, statement: Any) -> Any:
                filters = statement.compile().params
                name = filters["external_id_1"]
                expected = (
                    self.records[1]["contracts"].get(name) or self.records[0]["contracts"][name]
                )
                assert str(filters["contract_computation_id_1"]) == expected
                return SimpleNamespace(scalar_one_or_none=lambda: contract_ids[name])

        rows = [
            row for row in rendered.data.rows if row.get("contract_external_id") == "Contract 3"
        ]
        assert rows
        for row in rows:
            value, contributors = variance_cells.cell(
                cast(Session, PopulationLookup(pop_sides)), pop_params, row["row_key"], "change"
            )
            assert value == row["change"]
            assert any(
                "population." in detail for item in contributors for detail in item["details"]
            )
        assert all(item.sums_exactly for item in population.measures.values())

    # Existing contracts are merged without any business/reference change.
    # Different booking prices make the shared allocation redistribute real money.
    second = upgrade.decode_input(
        upgrade.encode_input(before).replace(b"Contract 2", b"Contract 3")
    )
    booking = next(event for event in second.events if event.event_type == "CONTRACT_BOOKED")
    lines = [dict(line) for line in booking.payload["lines"]]
    lines[0]["total_price"] = Decimal("1200")
    second = replace(
        second,
        events=tuple(
            replace(event, payload={**event.payload, "lines": lines}) if event is booking else event
            for event in second.events
        ),
    )
    joined_books = tuple(
        replace(
            book,
            policies=tuple(
                {
                    canonical_bytes(policy): policy
                    for source in (before, second)
                    for held in source.books
                    if held.book_code == book.book_code
                    for policy in held.policies
                }.values()
            ),
        )
        for book in before.books
    )
    joined = replace(
        before,
        known_at=before.known_at + timedelta(days=1),
        books=joined_books,
        contracts=(*before.contracts, *second.contracts),
        estimate_versions=(*before.estimate_versions, *second.estimate_versions),
        events=tuple(
            sorted(
                (*before.events, *second.events),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
        group=replace(
            before.group,
            group_key="MERGED",
            member_contract_keys=("Contract 2", "Contract 3"),
            criterion="25_9_A",
        ),
    )
    merged_id = uuid4()
    membership_pair = Pair(
        side(before, 1, prepared=((group_ids[0], before), (group_ids[1], second))),
        side(joined, 2, prepared=((merged_id, joined),)),
        (entity_id,),
    )
    membership = variance_groups.execute(membership_pair)
    reporting_membership = variance_groups.execute(membership_pair, currency_view="reporting")
    functional_membership = variance_groups.execute(membership_pair, currency_view="functional")
    detailed_membership = variance_groups.execute(
        membership_pair, currency_view="functional", event_details=True
    )
    assert detailed_membership.driver_totals == functional_membership.driver_totals
    assert {
        key: (value.metric_before, value.metric_after)
        for key, value in detailed_membership.measures.items()
    } == {
        key: (value.metric_before, value.metric_after)
        for key, value in functional_membership.measures.items()
    }
    assert all(change.sums_exactly for change in reporting_membership.measures.values())
    assert all(
        run.replay.executions[-1].changed_fields == ("reporting_rates",)
        for run in reporting_membership.groups.values()
    )

    assert all(change.sums_exactly for change in membership.measures.values())
    assert any(change.total for change in membership.measures.values())
    assert all(
        effect.driver == "MODIFICATION"
        for change in membership.measures.values()
        for effect in change.effects
    )
    shown = variance_presentation.dataset(membership_pair, membership)
    assert canonical_bytes(shown.evidence)
    split = Pair(
        side(joined, 2, prepared=((merged_id, joined),)),
        side(
            before,
            3,
            prepared=(
                (group_ids[0], replace(before, known_at=joined.known_at + timedelta(days=1))),
                (group_ids[1], replace(second, known_at=joined.known_at + timedelta(days=1))),
            ),
        ),
        (entity_id,),
    )
    split_result = variance_groups.execute(split)
    assert {key: change.total for key, change in split_result.measures.items()} == {
        key: -change.total for key, change in membership.measures.items()
    }
    assert variance_presentation.dataset(split, split_result).data.rows
    delivery = next(
        event
        for event in after.events
        if event.event_key not in {e.event_key for e in before.events}
    )
    mixed = replace(
        joined,
        events=tuple(
            sorted(
                (*joined.events, delivery),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    mixed_pair = replace(membership_pair, later=side(mixed, 2, prepared=((merged_id, mixed),)))
    mixed_result = variance_groups.execute(mixed_pair)
    joined_metrics = Projection(joined, "Mock Entity 2", "ASC606", "FY2023-P05")(compute(joined))
    mixed_metrics = Projection(mixed, "Mock Entity 2", "ASC606", "FY2023-P05")(compute(mixed))
    for key, change in mixed_result.measures.items():
        assert change.sums_exactly
        assert (
            sum(effect.amount for effect in change.effects if effect.driver == "MODIFICATION")
            == membership.measures[key].total
        )
        assert sum(
            effect.amount for effect in change.effects if effect.driver == "LATE_EVENT"
        ) == mixed_metrics.get(key, Fraction(0)) - joined_metrics.get(key, Fraction(0))
    assert any(
        effect.amount
        for change in mixed_result.measures.values()
        for effect in change.effects
        if effect.driver == "LATE_EVENT"
    )
    # An approved VC version is introduced with its application event after merging.
    previous_estimate = next(
        v for v in joined.estimate_versions if v.estimate_key.startswith("Contract 2/")
    )
    revised_estimate = replace(
        previous_estimate,
        version_no=2,
        version_key=previous_estimate.estimate_key + "@v2",
        effective_date=date(2023, 5, 31),
        constrained_amount=Decimal("-150"),
        supersedes_version_key=previous_estimate.version_key,
        content_sha256=sha256_hex({"version": 2, "amount": "-150"}),
    )
    estimate_event = replace(
        bundles.event(
            "Contract 2",
            11,
            "ESTIMATE_CHANGED",
            date(2023, 5, 31),
            {"estimate_version_id": revised_estimate.version_key},
        ),
        recorded_at=joined.known_at,
        estimate_version_key=revised_estimate.version_key,
    )
    with_version = replace(
        mixed,
        estimate_versions=tuple(
            sorted(
                (*mixed.estimate_versions, revised_estimate),
                key=lambda v: (v.estimate_key, v.version_no),
            )
        ),
    )
    estimated = replace(
        with_version,
        events=tuple(
            sorted(
                (*with_version.events, estimate_event),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    estimate_pair = replace(
        membership_pair, later=side(estimated, 2, prepared=((merged_id, estimated),))
    )
    estimate_result = variance_groups.execute(estimate_pair)
    estimate_metrics = Projection(estimated, "Mock Entity 2", "ASC606", "FY2023-P05")(
        compute(estimated)
    )
    assert any(
        estimate_metrics.get(k, Fraction(0)) != mixed_metrics.get(k, Fraction(0))
        for k in estimate_metrics.keys() | mixed_metrics.keys()
    )
    for key, change in estimate_result.measures.items():
        assert change.sums_exactly
        assert (
            sum(e.amount for e in change.effects if e.driver == "MODIFICATION")
            == membership.measures[key].total
        )
        assert sum(e.amount for e in change.effects if e.driver == "OTHER") == 0
        assert sum(
            e.amount for e in change.effects if e.driver == "LATE_EVENT"
        ) == estimate_metrics.get(key, Fraction(0)) - joined_metrics.get(key, Fraction(0))
    assert all(
        any(estimate_event.event_key in step.event_keys for step in run.replay.executions)
        for run in estimate_result.groups.values()
    )
    # A newly approved contract modification is replayed separately from its application.
    from support import cpc_worlds

    booking_line = next(e for e in before.events if e.event_type == "CONTRACT_BOOKED").payload[
        "lines"
    ][0]
    concession = cpc_worlds.concession(
        "-100", date(2023, 5, 31), key=booking_line["obligation_key"]
    )
    concession = replace(
        concession,
        lines=tuple(
            {**line, "product_code": booking_line["product_code"]} for line in concession.lines
        ),
    )
    treatments = {
        line["obligation_key"]: "LEGACY_PROSPECTIVE"
        for line in next(e for e in before.events if e.event_type == "CONTRACT_BOOKED").payload[
            "lines"
        ]
    }
    concession = replace(
        concession,
        template_mode="prospective",
        status="APPLIED",
        price_change_amount=None,
        questionnaire={},
        chosen_treatments=treatments,
        treatment_summary="LEGACY_PROSPECTIVE",
    )
    amendment = cpc_worlds.amended(list(after.events), concession, treatments)[-1]
    amendment = replace(
        amendment,
        event_key="Contract 2/EV-000011",
        record_seq=11,
        stream_version=11,
        recorded_at=mixed.known_at,
    )
    modified = replace(
        mixed,
        contracts=tuple(
            replace(c, modifications=(*c.modifications, concession))
            if c.external_id == "Contract 2"
            else c
            for c in mixed.contracts
        ),
        events=tuple(
            sorted(
                (*mixed.events, amendment),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    modification_pair = replace(
        membership_pair, later=side(modified, 2, prepared=((merged_id, modified),))
    )
    modification_result = variance_groups.execute(modification_pair)
    modification_metrics = Projection(modified, "Mock Entity 2", "ASC606", "FY2023-P05")(
        compute(modified)
    )
    assert any(
        modification_metrics.get(k, Fraction(0)) != mixed_metrics.get(k, Fraction(0))
        for k in modification_metrics.keys() | mixed_metrics.keys()
    )
    # Other-member allocations/revenue/RPO stay fixed. Contract-asset attribution
    # can change because the balance reader apportions the combined group's position.
    for key in modification_metrics.keys() | mixed_metrics.keys():
        if key.contract_external_id == "Contract 3" and key.measure in {"REVENUE", "RPO"}:
            assert modification_metrics.get(key, Fraction(0)) == mixed_metrics.get(key, Fraction(0))

    def other_allocations(bundle: InputBundle) -> dict[str, object]:
        return {
            row.subject_key: row.columns["allocated_amount"]
            for book in compute(bundle).books
            for row in book.obligation_versions
            if row.subject_key.startswith("Contract 3/")
        }

    assert other_allocations(mixed)
    assert other_allocations(modified) == other_allocations(mixed)
    for key, change in modification_result.measures.items():
        assert change.sums_exactly
        assert (
            sum(e.amount for e in change.effects if e.driver == "MODIFICATION")
            == membership.measures[key].total
        )
        assert sum(e.amount for e in change.effects if e.driver == "OTHER") == 0
        assert sum(
            e.amount for e in change.effects if e.driver == "LATE_EVENT"
        ) == modification_metrics.get(key, Fraction(0)) - joined_metrics.get(key, Fraction(0))
    standalone = replace(
        after,
        contracts=tuple(c for c in modified.contracts if c.external_id == "Contract 2"),
        events=tuple(e for e in modified.events if e.contract_key == "Contract 2"),
    )
    standalone_metrics = Projection(standalone, "Mock Entity 2", "ASC606", "FY2023-P05")(
        compute(standalone)
    )
    single = replay_period_money(
        before,
        standalone,
        entity_code="Mock Entity 2",
        book_code="ASC606",
        period_key="FY2023-P05",
        earlier_metrics=Projection(before, "Mock Entity 2", "ASC606", "FY2023-P05")(
            compute(before)
        ),
        later_metrics=standalone_metrics,
    )
    assert any(step.changed_fields == ("contracts",) for step in single.executions)
    assert all(change.sums_exactly for change in single.measures.values())
    # The exemption election changes in the same close as merge and delivery.
    elected = replace(
        joined,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(policy, value="APPLY")
                    if policy.code == "rpo.exemption_original_duration_one_year"
                    else policy
                    for policy in book.policies
                ),
            )
            for book in joined.books
        ),
    )
    elected_delivery = replace(mixed, books=elected.books)
    elected_pair = replace(
        membership_pair, later=side(elected_delivery, 2, prepared=((merged_id, elected_delivery),))
    )
    elected_result = variance_groups.execute(elected_pair)
    reference_metrics = Projection(elected, "Mock Entity 2", "ASC606", "FY2023-P05")(
        compute(elected)
    )
    final_metrics = Projection(elected_delivery, "Mock Entity 2", "ASC606", "FY2023-P05")(
        compute(elected_delivery)
    )
    for key, change in elected_result.measures.items():
        assert change.sums_exactly
        assert (
            sum(e.amount for e in change.effects if e.driver == "MODIFICATION")
            == membership.measures[key].total
        )
        assert sum(
            e.amount for e in change.effects if e.driver == "OTHER"
        ) == reference_metrics.get(key, Fraction(0)) - joined_metrics.get(key, Fraction(0))
        assert sum(
            e.amount for e in change.effects if e.driver == "LATE_EVENT"
        ) == final_metrics.get(key, Fraction(0)) - reference_metrics.get(key, Fraction(0))
    assert any(
        e.amount
        for change in elected_result.measures.values()
        for e in change.effects
        if e.driver == "OTHER"
    )
    conflicting_second = replace(
        second,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(policy, value="APPLY")
                    if policy.code == "rpo.exemption_original_duration_one_year"
                    else policy
                    for policy in book.policies
                ),
            )
            for book in second.books
        ),
    )
    with pytest.raises(Problem, match="(conflicting|inconsistent).*policy bases"):
        variance_groups.execute(
            replace(
                membership_pair,
                earlier=side(
                    before, 1, prepared=((group_ids[0], before), (group_ids[1], conflicting_second))
                ),
            )
        )
    shown = variance_presentation.dataset(elected_pair, elected_result)
    sides = identities(elected_pair)
    rebound = replace(
        binding,
        row_keys=frozenset(row["row_key"] for row in shown.data.rows),
        evidence={
            "close_variance_sources": {
                "version": 1,
                "sides": sides,
                "required_entity_ids": [str(entity_id)],
            },
            "close_variance_contributors": shown.evidence,
            "close_variance_evidence_sha256": sha256_hex(shown.evidence),
        },
    )
    for row in shown.data.rows:
        if row["row_key"].startswith("TOTAL:"):
            continue
        value, contributors = variance_cells.cell(
            cast(Session, Lookup()),
            replace(
                params,
                binding=rebound,
                parameters={
                    "from_period_lock_id": sides[0]["lock_id"],
                    "to_period_lock_id": sides[1]["lock_id"],
                },
            ),
            row["row_key"],
            "change",
        )
        assert value == row["change"]
        assert sum(Fraction(item["value"]["amount"]) for item in contributors) == Fraction(
            value["amount"]
        )
        assert any(
            "group.membership" in detail or delivery.event_key in detail or "books" in detail
            for item in contributors
            for detail in item["details"]
        )


@pytest.mark.parametrize("fault", ["version", "source", "weight", "existing"])
def test_ssp_readback_normalization_preserves_actual_reference_changes(fault: str) -> None:
    from erev_api.domain.reports.variance_execution import _readback_books
    from erev_engine.bundle import ResolvedPolicyInput

    before, after = _active_pair()
    output = compute(before)
    book = before.books[0]
    row = output.books[0].obligation_versions[0]
    version = row.columns["ssp_book_version_key"]
    assert isinstance(version, str)
    policy = ResolvedPolicyInput(
        "ssp.version_basis",
        "OBLIGATION",
        row.subject_key,
        {"recorded": version},
        "O",
        "RECORDED",
        "K",
    )
    if fault == "version":
        policy = replace(policy, value={"recorded": "unrelated@v1"})
    elif fault == "source":
        policy = replace(policy, source_ref="OVERRIDE")
    elif fault == "weight":
        policy = replace(policy, value={"recorded": version, "recorded@event": version})
    else:
        before = replace(before, books=(replace(book, policies=(*book.policies, policy)),))
        policy = replace(policy, value={"recorded": "different@v2"})
    after = replace(after, books=(replace(book, policies=(*book.policies, policy)),))
    books, normalized = _readback_books(before, after, output)
    assert books == after.books
    assert normalized == ()


def test_reference_election_change_is_replayed_separately_from_delivery() -> None:
    before, after = _active_pair()
    after = replace(
        after,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(policy, value="APPLY")
                    if policy.code == "rpo.exemption_original_duration_one_year"
                    else policy
                    for policy in book.policies
                ),
            )
            for book in after.books
        ),
    )

    def project(bundle: InputBundle, output: OutputBundle) -> dict[MeasureKey, Fraction]:
        return Projection(bundle, "Mock Entity 2", "ASC606", "FY2023-P05")(output)

    result = replay_events(
        before,
        after,
        earlier_period_end=date(2023, 5, 31),
        earlier_metrics=project(before, compute(before)),
        later_metrics=project(after, compute(after)),
        project=project,
    )
    effects = result.measures[RPO].effects
    assert [(effect.driver, effect.amount) for effect in effects] == [
        ("PROGRESS", Fraction(0)),
        ("OTHER", Fraction(-795)),
        ("LATE_EVENT", Fraction(0)),
    ]
    assert result.executions[2].changed_fields == ("books",)
    assert result.executions[-1].event_keys


def test_fx_change_replays_real_engine_functional_revenue() -> None:
    from support import step1_worlds

    before = step1_worlds.eur_mixed_rates()
    after = replace(
        before,
        known_at=before.known_at + timedelta(days=1),
        fx_rates=tuple(
            replace(rate, rate=rate.rate + Decimal("0.10"), version_key="CORRECTED")
            for rate in before.fx_rates
        ),
    )
    key = MeasureKey(before.contracts[0].external_id, "USD", "REVENUE")

    def project(bundle: InputBundle, output: OutputBundle) -> dict[MeasureKey, Fraction]:
        revenue = sum(
            (
                line.amount_functional * (1 if line.side == "C" else -1)
                for book in output.books
                for intent in book.posting_intents
                for line in intent.lines
                if line.account_role == "REVENUE"
            ),
            0,
        )
        return {key: Fraction(revenue, 100)}

    result = replay_events(
        before,
        after,
        earlier_period_end=date(2026, 2, 28),
        earlier_metrics=project(before, compute(before)),
        later_metrics=project(after, compute(after)),
        project=project,
    )
    # The ordinary compute releases the second EUR 600 payment; the first
    # payment is released by the distinct CLOSE_RELEASE pass. 600 * 0.10 = 60.
    assert result.measures[key].metric_before == 720
    assert result.measures[key].metric_after == 780
    assert result.measures[key].total == 60
    assert result.measures[key].effects[-1].driver == "FX"
    assert result.measures[key].effects[-1].amount == 60
    assert result.executions[-1].changed_fields == ("fx_rates",)


def test_membership_replay_separates_real_functional_fx() -> None:
    from uuid import uuid4

    from support import step1_worlds

    from erev_api.domain.reports import variance_membership
    from erev_api.domain.reports.computation_sources import VerifiedComputation
    from erev_engine import upgrade
    from erev_engine.canonical import canonical_bytes

    first = step1_worlds.eur_mixed_rates()
    second = upgrade.decode_input(upgrade.encode_input(first).replace(b"C-STEP1", b"C-SECOND"))
    merged = replace(
        first,
        known_at=first.known_at + timedelta(days=1),
        contracts=tuple(sorted((*first.contracts, *second.contracts), key=lambda c: c.external_id)),
        books=tuple(
            replace(
                book,
                policies=tuple(
                    {
                        canonical_bytes(policy): policy
                        for source in (first, second)
                        for held in source.books
                        if held.book_code == book.book_code
                        for policy in held.policies
                    }.values()
                ),
            )
            for book in first.books
        ),
        group=replace(
            first.group,
            group_key="MERGED",
            member_contract_keys=("C-SECOND", "C-STEP1"),
            criterion="25_9_A",
        ),
        events=tuple(
            sorted(
                (*first.events, *second.events),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    changed = replace(
        merged,
        fx_rates=tuple(
            replace(rate, rate=rate.rate + Decimal("0.10"), version_key="CORRECTED")
            for rate in merged.fx_rates
        ),
    )
    entity = first.entities[0].code

    def project(bundle: InputBundle) -> dict[MeasureKey, Fraction]:
        return Projection(bundle, entity, "ASC606", "FY2026-P01", "functional")(compute(bundle))

    def source(bundle: InputBundle) -> VerifiedComputation:
        output = compute(bundle)
        return VerifiedComputation(
            uuid4(),
            uuid4(),
            uuid4(),
            bundle,
            upgrade.output_mapping(output),
            output.sha256(),
            {"ASC606": 0},
            None,
        )

    originals = [source(first), source(second)]
    final = source(changed)
    earlier = {**project(first), **project(second)}
    intermediate, later = project(merged), project(changed)
    results, aliases = variance_membership.execute(
        {item.group_id: item for item in originals},
        {final.group_id: final},
        earlier,
        later,
        entity_code=entity,
        book_code="ASC606",
        period_key="FY2026-P01",
        currency_view="functional",
        engine=compute,
    )
    for contract in ("C-STEP1", "C-SECOND"):
        result = results[aliases[contract]]
        revenue = result.replay.measures[MeasureKey(contract, "USD", "REVENUE")]
        assert revenue.effects[-1].driver == "FX"
        assert revenue.effects[-1].amount == 60
        assert result.replay.executions[-1].changed_fields == ("fx_rates",)
        for key, change in result.replay.measures.items():
            assert change.sums_exactly
            assert change.metric_after == later.get(key, Fraction(0))
            assert sum(
                e.amount for e in change.effects if e.driver == "MODIFICATION"
            ) == intermediate.get(key, Fraction(0)) - earlier.get(key, Fraction(0))
            assert sum(e.amount for e in change.effects if e.driver == "FX") == later.get(
                key, Fraction(0)
            ) - intermediate.get(key, Fraction(0))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transaction_currency", "EUR"),
        ("contracting_entity_code", "OTHER"),
        ("inception_date", date(2023, 2, 1)),
    ],
)
def test_contract_reference_replay_preserves_accounting_basis(field: str, value: object) -> None:
    from erev_api.domain.reports.variance_replay import validate_contract_basis

    before, _ = _active_pair()
    with pytest.raises(Problem, match="basis migration"):
        validate_contract_basis(before.contracts, (replace(before.contracts[0], **{field: value}),))


def test_foreign_rpo_projection_uses_retained_closing_rate_and_attributes_fx() -> None:
    from erev_engine import upgrade
    from erev_engine.bundle import FxRateInput

    source, _ = _active_pair()
    source = replace(
        source,
        books=tuple(
            replace(
                book,
                account_mapping=bundles.account_mapping(extra=(("FX_GAIN_LOSS", None, "7999"),)),
            )
            for book in source.books
        ),
    )
    before = upgrade.decode_input(upgrade.encode_input(source).replace(b"USD", b"EUR"))
    rates = [
        FxRateInput(
            kind + p.period_key, "FX", kind, "EUR", "USD", p.end_date, p.period_key, Decimal("1.2")
        )
        for p in source.entities[0].periods
        for kind in ("closing", "average")
    ]
    rates.extend(
        FxRateInput("spot" + str(day), "FX", "spot", "EUR", "USD", day, None, Decimal("1.2"))
        for day in {event.effective_date for event in source.events}
    )
    before = replace(
        before,
        entities=source.entities,
        currencies={**source.currencies, **before.currencies},
        fx_rates=tuple(
            sorted(
                rates,
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.version_key,
                ),
            )
        ),
    )
    after = replace(
        before,
        known_at=before.known_at + timedelta(days=1),
        fx_rates=tuple(
            replace(rate, rate=Decimal("1.3"), version_key="NEW")
            if rate.rate_type == "closing"
            else rate
            for rate in before.fx_rates
        ),
    )

    def amounts(bundle: InputBundle) -> dict[MeasureKey, Fraction]:
        return Projection(bundle, "Mock Entity 2", "ASC606", "FY2023-P05", "functional")(
            compute(bundle)
        )

    assert amounts(before)[RPO] == Fraction("954")
    assert amounts(after)[RPO] == Fraction("1033.51")  # sum of individually rounded obligations
    result = replay_period_money(
        before,
        after,
        entity_code="Mock Entity 2",
        book_code="ASC606",
        period_key="FY2023-P05",
        earlier_metrics=amounts(before),
        later_metrics=amounts(after),
        currency_view="functional",
    )
    assert result.measures[RPO].effects[-1].driver == "FX"
    assert result.measures[RPO].effects[-1].amount == Fraction("79.51")
    output = compute(before)
    missing = replace(
        before, fx_rates=tuple(rate for rate in before.fx_rates if rate.rate_type != "closing")
    )
    with pytest.raises(Problem, match="retained closing rate"):
        Projection(missing, "Mock Entity 2", "ASC606", "FY2023-P05", "functional")(output)


def test_reporting_projection_rounds_each_contribution_and_obligation() -> None:
    from erev_api.domain.reports.variance_reporting import Basis

    _, bundle = _active_pair()
    output = compute(bundle)
    basis = Basis(
        "USD", "EUR", "FY2023-P05", date(2023, 5, 31), Fraction("0.9"), Fraction("0.8"), "a" * 64
    )
    projected = Projection(bundle, "Mock Entity 2", "ASC606", "FY2023-P05", "reporting", basis)(
        output
    )
    assert projected[MeasureKey("Contract 2", "EUR", "REVENUE")] == Fraction("47.07")
    assert projected[MeasureKey("Contract 2", "EUR", "RPO")] == Fraction("662.55")
    assert all(key.currency == "EUR" for key in projected)
    from uuid import uuid4

    from erev_api.domain.reports.computation_sources import VerifiedComputation
    from erev_api.domain.reports.variance_execution import verify_source
    from erev_engine import upgrade

    retained = VerifiedComputation(
        uuid4(),
        uuid4(),
        uuid4(),
        bundle,
        upgrade.output_mapping(output),
        output.sha256(),
        {"ASC606": 0},
        None,
    )
    verified, _ = verify_source(
        retained,
        projected,
        entity_code="Mock Entity 2",
        book_code="ASC606",
        period_key="FY2023-P05",
        currency_view="reporting",
        reporting_basis=basis,
    )
    assert verified.output_sha256 == output.sha256()
    with pytest.raises(Problem, match="retained average rate"):
        Projection(
            bundle,
            "Mock Entity 2",
            "ASC606",
            "FY2023-P05",
            "reporting",
            replace(basis, average=None),
        )(output)
    with pytest.raises(Problem, match="selected entity/period"):
        Projection(
            bundle,
            "Mock Entity 2",
            "ASC606",
            "FY2023-P05",
            "reporting",
            replace(basis, period_key="OTHER"),
        )


def test_reporting_replay_separates_business_and_reporting_fx_including_same_computation() -> None:
    from uuid import uuid4

    from erev_api.domain.reports import variance_execution, variance_population
    from erev_api.domain.reports.computation_sources import VerifiedComputation
    from erev_api.domain.reports.variance_reporting import Basis
    from erev_engine import upgrade

    before, after = _active_pair()
    old = Basis(
        "USD", "EUR", "FY2023-P05", date(2023, 5, 31), Fraction("0.9"), Fraction("0.8"), "a" * 64
    )
    new = replace(old, closing=Fraction("0.85"), average=Fraction("0.7"), evidence_sha256="b" * 64)

    def values(bundle: InputBundle, rates: Basis) -> dict[MeasureKey, Fraction]:
        return Projection(bundle, "Mock Entity 2", "ASC606", "FY2023-P05", "reporting", rates)(
            compute(bundle)
        )

    earlier, later = values(before, old), values(after, new)
    common = dict(
        entity_code="Mock Entity 2",
        book_code="ASC606",
        period_key="FY2023-P05",
        currency_view="reporting",
        earlier_reporting_basis=old,
        later_reporting_basis=new,
    )
    result = replay_period_money(
        before, after, earlier_metrics=earlier, later_metrics=later, **common
    )
    unchanged_rates = values(after, old)
    for key, change in result.measures.items():
        assert change.sums_exactly
        assert change.effects[-1].driver == "FX"
        assert change.effects[-1].amount == later.get(key, Fraction(0)) - unchanged_rates.get(
            key, Fraction(0)
        )
    assert result.executions[-1].changed_fields == ("reporting_rates",)
    output = compute(after)
    source = VerifiedComputation(
        uuid4(),
        uuid4(),
        uuid4(),
        after,
        upgrade.output_mapping(output),
        output.sha256(),
        {"ASC606": 0},
        None,
    )
    same = variance_execution.execute(
        source, source, earlier_metrics=unchanged_rates, later_metrics=later, **common
    )
    assert all(change.effects[0].driver == "FX" for change in same.replay.measures.values())
    assert same.replay.reporting_basis_sha256 == ("a" * 64, "b" * 64)
    entering = variance_population.execute(source, later, entering=True, **common)
    for key, change in entering.replay.measures.items():
        assert change.effects[0].amount == unchanged_rates.get(key, Fraction(0))
        assert change.effects[-1].amount == later[key] - unchanged_rates.get(key, Fraction(0))


def test_reopen_normalization_retains_calendar_and_entity_basis() -> None:
    from erev_api.domain.reports.variance_execution import _calendar_states

    before, _ = _active_pair()
    entity = before.entities[0]
    period = entity.periods[0]
    reopened = replace(period, states=tuple((book, "reopened") for book, _ in period.states))
    after = replace(
        before,
        entities=(replace(entity, periods=(reopened, *entity.periods[1:])), *before.entities[1:]),
    )
    normalized, fields = _calendar_states(before, after)
    assert normalized == before.entities
    assert fields == ("entities.periods.states",)
    assert after.entities[0].periods[0] == reopened  # original evidence stays intact
    for changed in (
        replace(after.entities[0], functional_currency="JPY"),
        replace(
            after.entities[0],
            periods=(
                replace(reopened, end_date=period.end_date + timedelta(days=1)),
                *entity.periods[1:],
            ),
        ),
        replace(after.entities[0], periods=(replace(reopened, states=()), *entity.periods[1:])),
    ):
        with pytest.raises(Problem, match="basis migration"):
            _calendar_states(before, replace(after, entities=(changed, *before.entities[1:])))


@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize("net_zero", [False, True])
def test_same_period_modifications_have_signed_per_event_functional_replay(foreign, net_zero):
    from erev_engine.stages.s15_disclosures.variance import Decomposition, totals_by_driver
    from tests.unit.reports.test_modification_event_amounts import _trace

    after, keys = _trace(
        foreign=foreign,
        same_period=True,
        return_input=True,
        second_delta="-20000.00" if net_zero else "-10000.00",
    )
    cutoff = after.known_at - timedelta(days=1)
    after = replace(
        after,
        events=tuple(
            replace(event, recorded_at=cutoff + timedelta(hours=1))
            if event.event_key in keys
            else event
            for event in after.events
        ),
    )
    before = replace(
        after, known_at=cutoff, events=tuple(e for e in after.events if e.event_key not in keys)
    )
    old_projection = Projection(before, "US01", "ASC606", "FY2026-P04", "functional")
    new_projection = replace(old_projection, basis=after)
    earlier, later = old_projection(compute(before)), new_projection(compute(after))
    args = dict(
        entity_code="US01",
        book_code="ASC606",
        period_key="FY2026-P04",
        currency_view="functional",
        earlier_metrics=earlier,
        later_metrics=later,
    )
    grouped = replay_period_money(before, after, **args)
    detailed = replay_period_money(before, after, **args, event_details=True)
    for key, result in detailed.measures.items():
        assert result.sums_exactly
        grouped_result = grouped.measures.get(key, Decomposition(Fraction(0), Fraction(0), ()))
        assert (result.metric_before, result.metric_after) == (
            grouped_result.metric_before,
            grouped_result.metric_after,
        )
        assert totals_by_driver(result.effects) == totals_by_driver(grouped_result.effects)
    revenue = detailed.measures[MeasureKey("K-01", "GBP" if foreign else "USD", "REVENUE")]
    changes = [effect for effect in revenue.effects if effect.event_keys]
    assert [effect.event_keys for effect in changes] == [(keys[0],), (keys[1],)]
    assert [effect.amount for effect in changes] == (
        [Fraction(8000), Fraction(-8000 if net_zero else -4000)]
        if foreign
        else [Fraction(10000), Fraction(-10000 if net_zero else -5000)]
    )


@pytest.mark.parametrize("kind", ["FULL", "PARTIAL"])
@pytest.mark.parametrize("view", ["transaction", "functional", "reporting"])
def test_termination_between_close_cutoffs_reconciles_revenue_and_rpo(kind, view):
    from erev_api.domain.reports.variance_replay import driver
    from erev_api.domain.reports.variance_reporting import Basis
    from tests.engine.s03_pob_builder.test_lessor_termination import termination

    source = termination(kind)
    cutoff = datetime(2026, 1, 31, 23, tzinfo=UTC)
    terminal = replace(source.events[-1], recorded_at=cutoff + timedelta(hours=1))
    before = replace(source, known_at=cutoff, events=source.events[:-1])
    after = replace(source, known_at=cutoff + timedelta(days=1), events=(*before.events, terminal))
    assert driver(terminal, date(2026, 1, 31)) == "LATE_EVENT"
    assert driver(terminal, date(2026, 1, 1)) == "MODIFICATION"
    reporting = (
        Basis(
            "USD",
            "GBP",
            "FY2026-P01",
            date(2026, 1, 31),
            Fraction("0.8"),
            Fraction("0.8"),
            "a" * 64,
        )
        if view == "reporting"
        else None
    )
    old_projection = Projection(before, "US01", "ASC606", "FY2026-P01", view, reporting)
    new_projection = replace(old_projection, basis=after)
    earlier, later = old_projection(compute(before)), new_projection(compute(after))
    for detailed in (False, True):
        result = replay_period_money(
            before,
            after,
            entity_code="US01",
            book_code="ASC606",
            period_key="FY2026-P01",
            currency_view=view,
            earlier_metrics=earlier,
            later_metrics=later,
            earlier_reporting_basis=reporting,
            later_reporting_basis=reporting,
            event_details=detailed,
        )
        currency = "GBP" if view == "reporting" else "USD"
        assert result.measures[MeasureKey("K-01", currency, "RPO")].metric_after == 0
        changed = []
        for key, measured in result.measures.items():
            assert measured.sums_exactly
            assert measured.metric_before == earlier.get(key, Fraction(0))
            assert measured.metric_after == later.get(key, Fraction(0))
            effects = [
                effect for effect in measured.effects if terminal.event_key in effect.event_keys
            ]
            assert len(effects) == 1
            assert effects[0].driver == "LATE_EVENT"
            changed.append(effects[0].amount)
        assert any(changed)
