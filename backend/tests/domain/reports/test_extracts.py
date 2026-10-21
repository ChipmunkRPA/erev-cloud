"""Event BI extract through the real API and worker, including incremental and retained reads."""

import hashlib
import json
from datetime import timedelta
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_event, historical_source_commit
from erev_api.domain.reports.builders.extract_events import COLUMNS
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.redaction import CONTACT_FIELDS
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.reference import get, post
from support.worlds import (
    AVM_US,
    REPORT_RUNS,
    k01_pellworth,
    report_run,
    resigned,
    run_now,
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_event_extract_delivery_and_incremental(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    events = world.place.rows(select(contract_event).order_by(contract_event.c.recorded_at))
    cutoff = world.place.scalar(select(func.clock_timestamp()))
    clock.set(cutoff)
    world = resigned(world)
    params = {"entity_codes": [AVM_US], "known_at": cutoff.isoformat()}
    run, rows = report_run(world, "extract_events", params)
    assert {row["id"] for row in rows} == {str(row["id"]) for row in events}
    assert [col.key for col in COLUMNS] == [
        col.name for col in contract_event.c if col.name != "tenant_id"
    ]
    assert not CONTACT_FIELDS.intersection(col.key for col in COLUMNS)
    output = get(app, f"{REPORT_RUNS}/{run['id']}/output", world.maya).json()
    assert output["dataset"] == "extract_events"
    assert output["schema_version"] == 1
    assert output["mode"] == "FULL"
    assert output["row_count"] == len(events)
    commits = {
        row["source_id"]: row["committed_server_at"]
        for row in world.place.rows(
            select(historical_source_commit).where(
                historical_source_commit.c.source_kind == "contract_event"
            )
        )
    }
    since = min(commits[row["id"]] for row in events)
    _, incremental = report_run(
        world,
        "extract_events",
        {
            **params,
            "mode": "INCREMENTAL",
            "known_since": since.isoformat(),
        },
    )
    assert {row["id"] for row in incremental} == {
        str(row["id"]) for row in events if commits[row["id"]] > since
    }
    for known_since in (None, cutoff.isoformat()):
        invalid = post(
            app,
            REPORT_RUNS,
            world.maya,
            {
                "report_code": "extract_events",
                "output_format": "JSON",
                "parameters": {
                    **params,
                    "mode": "INCREMENTAL",
                    **({} if known_since is None else {"known_since": known_since}),
                },
            },
        )
        assert invalid.status_code == 422, invalid.text
    csv_run, _ = report_run(world, "extract_events", params, output_format="CSV")
    base = f"{REPORT_RUNS}/{csv_run['id']}/output"
    csv = get(app, base, world.maya)
    manifest = get(app, base, world.maya, {"part": "manifest"}).json()
    assert manifest["sha256"] == hashlib.sha256(csv.content).hexdigest()
    assert manifest["known_at"] == cutoff.isoformat().replace("+00:00", "Z")
    assert manifest["control_totals"] == {"row_count": len(events)}
    rerun = post(app, f"{REPORT_RUNS}/{run['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    repeated = get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya)
    assert repeated.json() == output


def test_contract_version_extract_delivery(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from erev_api.db.tables import contract, contract_computation, contract_version
    from erev_api.domain.reports.builders.extract_contract_versions import KEYS

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    versions = world.place.rows(
        select(contract_version).where(contract_version.c.book_code == "ASC606")
    )
    cutoff = world.place.scalar(select(func.clock_timestamp()))
    clock.set(cutoff)
    world = resigned(world)
    params = {"entity_codes": [AVM_US], "book": "ASC606", "known_at": cutoff.isoformat()}
    run, rows = report_run(world, "extract_contract_versions", params)
    assert {row["id"] for row in rows} == {str(row["id"]) for row in versions}
    assert list(KEYS) == [col.name for col in contract_version.c if col.name != "tenant_id"]
    by_id = {str(row["id"]): row for row in versions}
    for row in rows:
        source = by_id[row["id"]]
        assert row["transaction_price"] == str(source["transaction_price"])
        heads = world.place.scalar(
            select(contract_computation.c.stream_heads).where(
                contract_computation.c.id == source["contract_computation_id"],
            )
        )
        contracts = world.place.rows(select(contract.c.external_id).where(contract.c.id.in_(heads)))
        assert json.loads(row["contract_external_ids"]) == sorted(
            item["external_id"] for item in contracts
        )
    commits = {
        row["source_id"]: row["committed_server_at"]
        for row in world.place.rows(
            select(historical_source_commit).where(
                historical_source_commit.c.source_kind == "contract_version"
            )
        )
    }
    since = min(commits[row["id"]] for row in versions)
    if since == cutoff:
        since -= timedelta(microseconds=1)
    _, incremental = report_run(
        world,
        "extract_contract_versions",
        {
            **params,
            "mode": "INCREMENTAL",
            "known_since": since.isoformat(),
        },
    )
    assert {row["id"] for row in incremental} == {
        str(row["id"]) for row in versions if commits[row["id"]] > since
    }
    original = get(app, f"{REPORT_RUNS}/{run['id']}/output", world.maya).json()
    assert original["schema_version"] == 1
    assert original["dataset"] == "extract_contract_versions"
    rerun = post(app, f"{REPORT_RUNS}/{run['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == original
    )


@pytest.mark.parametrize(
    "code", ["extract_obligations", "extract_schedule_lines", "extract_balances"]
)
def test_latest_extracts_and_retained_sources(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing, code: str
) -> None:
    from datetime import date
    from decimal import Decimal

    from erev_api.db.tables import (
        contract,
        contract_version_balance,
        obligation_version,
        schedule_line,
    )
    from erev_api.domain.reports.builders import (
        extract_balances,
        extract_obligations,
        extract_schedule_lines,
    )
    from erev_api.enums import ContractEventType
    from erev_api.events.payloads import BillingRecordedV1
    from erev_api.events.stream import EventIn
    from erev_api.money import MoneyIn
    from sqlalchemy import func
    from support.factories import appended, computed
    from support.worlds import K01

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp)
    world = resigned(world)
    params = {"entity_codes": [AVM_US], "book": "ASC606", "known_at": clock.now().isoformat()}
    original, rows = report_run(world, code, params)
    assert rows
    table, columns, extra, totals = {
        "extract_obligations": (
            obligation_version,
            extract_obligations.COLUMNS,
            ["contract_external_id"],
            ("allocated_amount", "revenue_cum"),
        ),
        "extract_schedule_lines": (
            schedule_line,
            extract_schedule_lines.COLUMNS,
            ["contract_external_id", "period_key"],
            ("amount",),
        ),
        "extract_balances": (
            contract_version_balance,
            extract_balances.COLUMNS,
            ["contract_external_id", "entity_code"],
            (
                "contract_liability_functional",
                "contract_asset_functional",
                "unbilled_receivable_functional",
            ),
        ),
    }[code]
    expected_columns = [c.name for c in table.c if c.name not in {"tenant_id", "trace_nodes"}]
    assert [col.key for col in columns] == [*expected_columns, *extra]
    data = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    assert data["control_totals"]["by_currency"]["USD"] == {
        key: str(sum((Decimal(row[key]) for row in rows), Decimal(0))) for key in totals
    }
    booked = world.contracts[K01]
    cid = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    appended(
        world.place,
        cid,
        world.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == cid)),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 16),
                payload=BillingRecordedV1(
                    invoice_number="EXTRACT-NEW",
                    line_external_id="EXTRACT-NEW-1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="5000.00", currency="USD"),
                    issue_date=date(2026, 9, 16),
                ),
            ),
        ],
    )
    clock.advance(timedelta(seconds=2))
    clock.set(world.place.scalar(select(func.clock_timestamp())) + timedelta(seconds=1))
    computed(world.place, group_id)
    _, latest = report_run(world, code, {**params, "known_at": clock.now().isoformat()})
    assert {r["id"] for r in rows}.isdisjoint(r["id"] for r in latest)
    assert len(latest) == len(rows)
    if code == "extract_obligations":
        assert sum(Decimal(r["billed_cum"]) for r in latest) > sum(
            Decimal(r["billed_cum"]) for r in rows
        )
    _, incremental = report_run(
        world,
        code,
        {
            **params,
            "known_at": clock.now().isoformat(),
            "mode": "INCREMENTAL",
            "known_since": params["known_at"],
        },
    )
    assert incremental == latest
    rerun = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == data
    )


def test_subledger_extract_seal_cutoff_and_controls(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from decimal import Decimal

    from erev_api.db.tables import subledger_line, subledger_posting_commit, subledger_posting_seal
    from erev_api.domain.reports.builders.extract_subledger_lines import COLUMNS
    from sqlalchemy import func

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    source = world.place.rows(select(subledger_line).where(subledger_line.c.book_code == "ASC606"))
    assert source
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp)
    world = resigned(world)
    params = {"entity_codes": [AVM_US], "book": "ASC606", "known_at": stamp.isoformat()}
    original, rows = report_run(world, "extract_subledger_lines", params)
    assert {r["id"] for r in rows} == {str(r["id"]) for r in source}
    assert [c.key for c in COLUMNS] == [
        *[c.name for c in subledger_line.c if c.name != "tenant_id"],
        "contract_external_id",
        "period_key",
        "origin_period_key",
        "gl_account_code",
    ]
    output = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    controls = output["control_totals"]
    assert all(
        Decimal(group["amount_functional"]) == 0
        for group in controls["by_entity_book_currency_period"]
    )
    assert controls["row_count"] == len(source)
    assert output["dataset"] == "extract_subledger_lines"
    first_seal = world.place.scalar(
        select(func.min(subledger_posting_seal.c.sealed_server_at)).where(
            subledger_posting_seal.c.book_code == "ASC606"
        )
    )
    _, before = report_run(
        world,
        "extract_subledger_lines",
        {**params, "known_at": (first_seal - timedelta(microseconds=1)).isoformat()},
    )
    assert before == []
    commits = {
        r["subledger_posting_id"]: r["committed_server_at"]
        for r in world.place.rows(select(subledger_posting_commit))
    }
    since = min(commits[r["subledger_posting_id"]] for r in source)
    _, incremental = report_run(
        world,
        "extract_subledger_lines",
        {
            **params,
            "mode": "INCREMENTAL",
            "known_since": since.isoformat(),
        },
    )
    assert {r["id"] for r in incremental} == {
        str(r["id"]) for r in source if commits[r["subledger_posting_id"]] > since
    }
    csv_run, _ = report_run(world, "extract_subledger_lines", params, output_format="CSV")
    base = f"{REPORT_RUNS}/{csv_run['id']}/output"
    content = get(app, base, world.maya).content
    manifest = get(app, base, world.maya, {"part": "manifest"}).json()
    assert manifest["sha256"] == hashlib.sha256(content).hexdigest()
    assert manifest["control_totals"] == controls
    rerun = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == output
    )


def test_legacy_extract_71_columns_and_reproduction(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from erev_api.domain.reports import legacy_columns
    from sqlalchemy import func

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp)
    world = resigned(world)
    params = {"entity_codes": [AVM_US], "book": "ASC606", "known_at": stamp.isoformat()}
    original, rows = report_run(world, "extract_legacy_contract_live", params)
    assert rows
    assert len(legacy_columns.COLUMNS) == 71
    data = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    assert [col["key"] for col in data["columns"]] == [col.key for col in legacy_columns.COLUMNS]
    _, reference = report_run(
        world,
        "legacy_contract_history_export",
        {
            **params,
            "from_date": "1900-01-01",
            "to_date": "2100-12-31",
        },
    )
    assert rows == reference
    csv_run, _ = report_run(world, "extract_legacy_contract_live", params, output_format="CSV")
    base = f"{REPORT_RUNS}/{csv_run['id']}/output"
    content = get(app, base, world.maya).content
    manifest = get(app, base, world.maya, {"part": "manifest"}).json()
    assert manifest["sha256"] == hashlib.sha256(content).hexdigest()
    assert manifest["dataset"] == "extract_legacy_contract_live"
    assert manifest["row_count"] == len(rows)
    rerun = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == data
    )
    invalid = post(
        app,
        REPORT_RUNS,
        world.maya,
        {
            "report_code": "extract_legacy_contract_live",
            "output_format": "JSON",
            "parameters": {**params, "book": "IFRS15"},
        },
    )
    assert invalid.status_code == 422, invalid.text


def test_journal_extract_historical_cancellation(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from decimal import Decimal

    from erev_api.db.tables import journal_line
    from erev_api.domain.reports.builders.extract_journal_lines import COLUMNS
    from sqlalchemy import func
    from support.worlds import journal_run

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    world = resigned(world)
    journal = journal_run(world)
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp)
    params = {"entity_codes": [AVM_US], "book": "ASC606", "known_at": stamp.isoformat()}
    original, rows = report_run(world, "extract_journal_lines", params)
    assert rows
    assert [c.key for c in COLUMNS] == [
        *[c.name for c in journal_line.c if c.name != "tenant_id"],
        "je_no",
        "run_no",
        "batch_external_id",
        "period_key",
    ]
    data = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    totals = data["control_totals"]["by_currency"]["USD"]
    assert Decimal(totals["debit_functional"]) > 0
    assert Decimal(totals["debit_functional"]) == Decimal(totals["credit_functional"])
    csv_run, _ = report_run(world, "extract_journal_lines", params, output_format="CSV")
    base = f"{REPORT_RUNS}/{csv_run['id']}/output"
    content = get(app, base, world.maya).content
    manifest = get(app, base, world.maya, {"part": "manifest"}).json()
    assert manifest["sha256"] == hashlib.sha256(content).hexdigest()
    clock.advance(timedelta(seconds=2))
    path = f"/api/v1/journal-runs/{journal['id']}"
    shown = get(app, path, world.maya)
    cancelled = post(
        app,
        path + "/cancel",
        world.maya,
        {"reason": "Verify historical extract"},
        if_match=shown.headers["etag"],
    )
    assert cancelled.status_code == 200, cancelled.text
    _, current = report_run(
        world, "extract_journal_lines", {**params, "known_at": clock.now().isoformat()}
    )
    assert current == []
    _, historic = report_run(world, "extract_journal_lines", params)
    assert historic == rows
    rerun = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == data
    )


def test_contract_source_revisions_are_atomic_and_source_owned(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from datetime import date
    from uuid import uuid4

    from erev_api.db.tables import contract, report_source_revision
    from erev_api.enums import ContractEventType
    from erev_api.events.payloads import BillingRecordedV1
    from erev_api.events.stream import EventIn, append_events
    from erev_api.money import MoneyIn
    from sqlalchemy import exc, func, insert, update
    from support.factories import appended
    from support.worlds import K01

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    cid = UUID(str(world.contracts[K01].contract["id"]))
    query = (
        select(report_source_revision)
        .where(
            report_source_revision.c.source_kind == "contract",
            report_source_revision.c.source_id == cid,
        )
        .order_by(report_source_revision.c.revision_no)
    )
    before = world.place.rows(query)
    assert len(before) > 1
    assert [r["revision_no"] for r in before] == list(range(1, len(before) + 1))
    assert not any(r["is_baseline"] for r in before)
    current = world.place.scalar(
        select(func.to_jsonb(contract.table_valued())).where(contract.c.id == cid)
    )
    current.pop("tenant_id")
    assert before[-1]["document"] == current
    from erev_api.domain.reports.builders.extract_contracts import COLUMNS as CONTRACT_COLUMNS

    cutoff = world.place.scalar(select(func.clock_timestamp()))
    clock.set(cutoff)
    world = resigned(world)
    params = {"entity_codes": [AVM_US], "known_at": cutoff.isoformat()}
    original, rows = report_run(world, "extract_contracts", params)
    assert rows and [col.key for col in CONTRACT_COLUMNS] == [
        col.name for col in contract.c if col.name != "tenant_id"
    ] + ["customer_code", "contracting_entity_code"]
    row = next(row for row in rows if row["id"] == str(cid))
    assert row["head_stream_version"] == current["head_stream_version"]
    assert row["customer_code"] and row["contracting_entity_code"] == AVM_US
    original_output = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    csv_run, _ = report_run(world, "extract_contracts", params, output_format="CSV")
    base = f"{REPORT_RUNS}/{csv_run['id']}/output"
    content = get(app, base, world.maya).content
    manifest = get(app, base, world.maya, {"part": "manifest"}).json()
    assert manifest["sha256"] == hashlib.sha256(content).hexdigest()
    assert manifest["dataset"] == "extract_contracts"
    _, incremental = report_run(
        world,
        "extract_contracts",
        {
            **params,
            "mode": "INCREMENTAL",
            "known_since": world.place.scalar(
                select(func.erev.source_commit_time("report_source_revision", before[-1]["id"]))
            ).isoformat(),
        },
    )
    assert incremental == []
    head = world.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == cid))
    event = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 9, 16),
        payload=BillingRecordedV1(
            invoice_number="REVISION-1",
            line_external_id="REVISION-1-1",
            obligation_key="O1",
            amount=MoneyIn(amount="5000.00", currency="USD"),
            issue_date=date(2026, 9, 16),
        ),
    )
    with world.place.uow() as uow:
        append_events(
            uow, contract_id=cid, expected_stream_version=head, events=[event], origin="UI"
        )
        assert len(uow.session.execute(query).mappings().all()) > len(before)
    assert world.place.rows(query) == before
    appended(world.place, cid, head, [event])
    after = world.place.rows(query)
    assert after[: len(before)] == before
    assert after[-1]["document"]["head_stream_version"] == head + 1
    _, historical = report_run(world, "extract_contracts", params)
    assert historical == rows
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    world = resigned(world)
    _, changed = report_run(
        world,
        "extract_contracts",
        {
            **params,
            "known_at": clock.now().isoformat(),
        },
    )
    assert next(r for r in changed if r["id"] == str(cid))["head_stream_version"] == head + 1
    rerun = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == original_output
    )
    with pytest.raises(exc.IntegrityError):
        with world.place.uow() as uow:
            uow.session.execute(
                insert(report_source_revision).values(**{**dict(after[-1]), "id": uuid4()})
            )
    with pytest.raises(exc.DBAPIError):
        with world.place.uow() as uow:
            uow.session.execute(
                update(report_source_revision)
                .where(report_source_revision.c.id == before[0]["id"])
                .values(document={})
            )


def test_journal_extract_uses_committed_lifecycle_cutoff(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from erev_api.db.tables import journal_run as runs
    from erev_api.domain.journals.commands import cancel_run
    from erev_api.domain.reports import tie_outs
    from erev_api.domain.reports.builders import ReportParams
    from erev_api.schemas.journals import JournalRunCancelIn
    from sqlalchemy import func
    from support.worlds import journal_run

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    world = resigned(world)
    before_creation = world.place.scalar(select(func.clock_timestamp()))
    journal = journal_run(world)
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp)
    params = {"entity_codes": [AVM_US], "book": "ASC606", "known_at": stamp.isoformat()}
    original, rows = report_run(world, "extract_journal_lines", params)
    assert rows
    _, incremental = report_run(
        world,
        "extract_journal_lines",
        {**params, "mode": "INCREMENTAL", "known_since": before_creation.isoformat()},
    )
    assert incremental == rows
    run = world.place.rows(select(runs).where(runs.c.id == UUID(journal["id"])))[0]

    def revenue(at):
        report_params = ReportParams(
            report_code="disaggregation",
            report_version=1,
            parameters={},
            entity_ids=(run["entity_id"],),
            book_code="ASC606",
            known_at=at,
            historical=True,
        )
        with world.place.uow() as reader:
            return tie_outs.journal_revenue(
                reader.session,
                entity_ids=report_params.entity_ids,
                book_code="ASC606",
                period_ids=[run["period_id"]],
                known_at=at,
                params=report_params,
            )

    expected_revenue = revenue(stamp)
    assert expected_revenue
    # The cancellation's business timestamp AND revision insert precede cutoff,
    # but its transaction becomes visible only afterward.
    with world.place.uow() as writer:
        cancel_run(writer, UUID(journal["id"]), JournalRunCancelIn(reason="Cutoff overlap"))
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    _, historical = report_run(
        world, "extract_journal_lines", {**params, "known_at": cutoff.isoformat()}
    )
    assert historical == rows
    assert revenue(cutoff) == expected_revenue
    _, latest = report_run(
        world, "extract_journal_lines", {**params, "known_at": clock.now().isoformat()}
    )
    assert latest == []
    assert revenue(clock.now()) == {}


def test_je_population_retains_inputs_and_committed_cancellation(
    app: FastAPI,
    app_settings: Settings,
    clock: FrozenClock,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from erev_api.db.tables import journal_run as runs
    from erev_api.db.tables import legal_entity, period
    from erev_api.domain.journals.commands import cancel_run
    from erev_api.schemas.journals import JournalRunCancelIn
    from sqlalchemy import update
    from support.worlds import journal_run

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    world = resigned(world)
    journal = journal_run(world)
    period_key = world.place.scalar(
        select(period.c.period_key)
        .join(runs, (runs.c.period_id == period.c.id) & (runs.c.tenant_id == period.c.tenant_id))
        .where(runs.c.id == UUID(journal["id"]))
    )
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp)
    params = {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "from_period_key": period_key,
        "to_period_key": period_key,
        "known_at": stamp.isoformat(),
        "known_at_basis": "historical",
    }
    original, rows = report_run(world, "je_population", params)
    assert rows
    assert {row["run_state"] for row in rows} == {"draft"}
    data = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    with world.place.uow() as writer:
        cancel_run(writer, UUID(journal["id"]), JournalRunCancelIn(reason="Retained population"))
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    _, historical = report_run(world, "je_population", {**params, "known_at": cutoff.isoformat()})
    assert historical == rows
    _, current = report_run(world, "je_population", {**params, "known_at": clock.now().isoformat()})
    assert current == []
    _, included = report_run(
        world,
        "je_population",
        {**params, "known_at": clock.now().isoformat(), "include_cancelled": True},
    )
    assert len(included) == len(rows)
    assert {row["run_state"] for row in included} == {"cancelled"}
    with world.place.uow() as writer:
        writer.session.execute(
            update(legal_entity)
            .where(legal_entity.c.code == AVM_US)
            .values(code="AVM-RENAMED", updated_at=clock.now())
        )
        writer.commit()
    rerun = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    assert (
        get(app, f"{REPORT_RUNS}/{rerun.headers['x-erev-report-run-id']}/output", world.maya).json()
        == data
    )

    # A pre-adapter OPEN record must still rerun as a new evaluation, not attempt
    # to rebuild from retained input records it never captured.
    from erev_api.domain.reports import framework

    original_reader = framework.run_row

    def legacy_reader(*args, **kwargs):
        row = dict(original_reader(*args, **kwargs))
        row["source_binding"] = {**row["source_binding"], "strategy": "open", "evidence": {}}
        return row

    with monkeypatch.context() as patch:
        patch.setattr(framework, "run_row", legacy_reader)
        legacy = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert legacy.status_code == 202, legacy.text
    assert run_now(world, UUID(legacy.json()["id"]))["state"] == "SUCCEEDED"
    legacy_data = get(
        app, f"{REPORT_RUNS}/{legacy.headers['x-erev-report-run-id']}/output", world.maya
    ).json()
    assert legacy_data != data
    assert {row["entity_code"] for row in legacy_data["rows"]} == {"AVM-RENAMED"}


def test_sample_journals_use_committed_lines_and_lifecycle(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from dataclasses import replace
    from datetime import date
    from decimal import Decimal

    from erev_api.domain.journals.commands import cancel_run
    from erev_api.domain.reports import evidence_sample_journals
    from erev_api.domain.reports.evidence_commands import PERMISSIONS
    from erev_api.domain.reports.evidence_selection import SourceSelection
    from erev_api.schemas.journals import JournalRunCancelIn
    from support.worlds import K01, journal_run

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    world = resigned(world)
    before = world.place.scalar(select(func.clock_timestamp()))
    journal = journal_run(world)
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp)
    permissions = world.place.principal.permissions | PERMISSIONS | {"journal.run"}
    principal = replace(
        world.place.principal,
        permissions=permissions,
        permission_scopes={
            **world.place.principal.permission_scopes,
            **{p: "*" for p in permissions},
        },
    )
    selection = SourceSelection(
        tenant_id=principal.tenant_id,
        known_at=stamp,
        entity_ids=(),
        contract_ids=(UUID(str(world.contracts[K01].contract["id"])),),
    )

    def collect(at):
        with world.place.uow(principal) as reader:
            result = evidence_sample_journals.collect(
                reader, replace(selection, known_at=at), as_of=date(2026, 9, 30)
            )
        return json.loads(result.files[0].content)

    assert collect(before)["lines"] == []
    original = collect(stamp)
    assert original["schema_version"] == 2
    assert original["lines"]
    for row in original["lines"]:
        assert row["run_state_as_of"] == "draft"
        assert row["commit_evidence"]["run_revision_id"]
        assert row["commit_evidence"]["batch_revision_id"]
        assert row["commit_evidence"]["line_committed_at"]
        assert all(source["committed_server_at"] for source in row["sources"])
        assert Decimal(row["sample_contribution"]["net_functional"]) == (
            Decimal(row["line"]["debit_functional"]) - Decimal(row["line"]["credit_functional"])
        )
    with world.place.uow(principal) as writer:
        cancel_run(writer, UUID(journal["id"]), JournalRunCancelIn(reason="Sample cutoff"))
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    assert collect(cutoff)["lines"] == original["lines"]
    latest = collect(clock.now())
    assert len(latest["lines"]) == len(original["lines"])
    assert all(row["cancelled_as_of"] for row in latest["lines"])
    assert all(row["run_state_as_of"] == "cancelled" for row in latest["lines"])


def test_journal_ancillary_sources_exclude_late_commits(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from erev_api.db import new_id, transitions
    from erev_api.db.tables import (
        approval_decision,
        approval_request,
        approval_step,
        audit_event,
        journal_batch,
        posting_ack,
    )
    from erev_api.domain.journals import commit_evidence
    from erev_api.domain.reports.builders import je_population
    from sqlalchemy import insert
    from support.rows import (
        approval_decision_values,
        approval_request_values,
        approval_step_values,
        posting_ack_values,
    )
    from support.worlds import K01, journal_run

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    world = resigned(world)
    journal = journal_run(world)
    batch_id = world.place.scalar(
        select(journal_batch.c.id).where(journal_batch.c.journal_run_id == UUID(journal["id"]))
    )
    cid = UUID(str(world.contracts[K01].contract["id"]))
    request = approval_request_values(world.place.tenant_id)
    request_id = request["id"]
    step = approval_step_values(
        world.place.tenant_id, approval_request_id=request_id, min_approvers=2
    )
    original = approval_decision_values(
        world.place.tenant_id,
        approval_request_id=request_id,
        approval_step_id=step["id"],
        approver_id=world.priya.member.user_id,
    )
    with world.place.uow() as setup:
        setup.session.execute(insert(approval_request).values(**request))
        setup.session.execute(insert(approval_step).values(**step))
        setup.session.execute(insert(approval_decision).values(**original))
        before_request_commit = world.place.scalar(select(func.clock_timestamp()))
        setup.commit()
    changed_actor = world.maya.member.user_id
    stamp = world.place.scalar(select(func.clock_timestamp()))
    decision = {
        **original,
        "id": new_id(),
        "approver_id": changed_actor,
        "decided_at": stamp,
        "mfa_verified_at": stamp,
    }
    with world.place.uow() as writer:
        writer.session.execute(insert(approval_decision).values(**decision))
        ack = posting_ack_values(
            world.place.tenant_id,
            batch_id=batch_id,
            received_at=stamp,
            gl_document_id="GL-LATE-COMMIT",
        )
        writer.session.execute(insert(posting_ack).values(**ack))
        transitions.apply(
            writer.session,
            "approval_step",
            step["id"],
            to_status="APPROVED",
            set_values={"completed_at": stamp},
            expected_status="ACTIVE",
        )
        transitions.apply(
            writer.session,
            "approval_request",
            request_id,
            to_status="APPROVED",
            set_values={"decided_at": stamp},
            expected_status="PENDING",
        )
        writer.audit(
            action="approval.approve",
            object_type="approval_request",
            object_id=request_id,
            approval_request_id=request_id,
            contract_id=cid,
        )
        from erev_api.audit.chain import flush

        flush(writer)
        audit_id = writer.session.scalar(
            select(audit_event.c.id).where(audit_event.c.approval_request_id == request_id)
        )
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    now = world.place.scalar(select(func.clock_timestamp()))
    with world.place.uow() as reader:
        assert (
            je_population._gl_documents(reader.session, [batch_id], cutoff, historical=True) == {}
        )
        assert je_population._gl_documents(reader.session, [batch_id], now, historical=True) == {
            batch_id: "GL-LATE-COMMIT"
        }
        assert je_population._approvals(reader.session, [request_id], cutoff, historical=True) == {
            request_id: (original["approver_id"], "USER")
        }
        assert je_population._approvals(reader.session, [request_id], now, historical=True) == {
            request_id: (changed_actor, "USER")
        }
        assert je_population._gl_documents(reader.session, [batch_id], cutoff) == {
            batch_id: "GL-LATE-COMMIT"
        }
    from erev_api.domain.reports.builders import register_support

    with world.place.uow() as reader:
        old = register_support.requests(
            reader.session,
            cutoff=cutoff,
            where=[approval_request.c.id == request_id],
            committed=True,
        )
        latest = register_support.requests(
            reader.session, cutoff=now, where=[approval_request.c.id == request_id], committed=True
        )
        assert old[0].status == "PENDING" and old[0].comment is None
        assert len(old[0].decisions) == 1
        assert latest[0].status == "APPROVED" and latest[0].decided_at == stamp
        assert len(latest[0].decisions) == 2
        assert (
            register_support.requests(
                reader.session,
                cutoff=before_request_commit,
                where=[approval_request.c.id == request_id],
                committed=True,
            )
            == []
        )
        from dataclasses import replace

        from erev_api.domain.reports.builders import ReportParams, approvals_register

        entity_id = reader.session.scalar(
            select(journal_batch.c.entity_id).where(journal_batch.c.id == batch_id)
        )
        params = ReportParams(
            report_code="approvals_register",
            report_version=1,
            parameters={"status": ["PENDING"]},
            entity_ids=(entity_id,),
            known_at=cutoff,
            historical=True,
        )
        bounds = (cutoff - timedelta(days=365), now + timedelta(days=1))
        assert request_id in {
            r.id for r in approvals_register.sources(reader, params, bounds=bounds)
        }
        assert request_id not in {
            r.id
            for r in approvals_register.sources(
                reader, replace(params, parameters={"status": ["APPROVED"]}), bounds=bounds
            )
        }
        assert request_id in {
            r.id
            for r in approvals_register.sources(
                reader,
                replace(params, known_at=now, parameters={"status": ["APPROVED"]}),
                bounds=bounds,
            )
        }
    from erev_api.domain.reports import evidence_sample_decisions
    from erev_api.domain.reports.evidence_commands import PERMISSIONS
    from erev_api.domain.reports.evidence_selection import SourceSelection

    clock.set(now)
    principal = replace(
        world.place.principal,
        permissions=world.place.principal.permissions | PERMISSIONS,
        permission_scopes={
            **world.place.principal.permission_scopes,
            **{permission: "*" for permission in PERMISSIONS},
        },
    )
    selection = SourceSelection(
        tenant_id=principal.tenant_id, known_at=cutoff, entity_ids=(), contract_ids=(cid,)
    )
    with world.place.uow(principal) as reader:
        old_sample = evidence_sample_decisions.collect(
            reader, selection, approval_request_ids=(request_id,)
        )
        new_sample = evidence_sample_decisions.collect(
            reader, replace(selection, known_at=now), approval_request_ids=(request_id,)
        )
        old_files = {f.path: json.loads(f.content) for f in old_sample.files}
        new_files = {f.path: json.loads(f.content) for f in new_sample.files}
        old_approval = old_files["sample/approvals.json"]
        new_approval = new_files["sample/approvals.json"]
        assert old_approval["schema_version"] == new_approval["schema_version"] == 2
        old_request = next(r for r in old_approval["requests"] if r["id"] == str(request_id))
        new_request = next(r for r in new_approval["requests"] if r["id"] == str(request_id))
        assert old_request["status"] == "PENDING"
        assert new_request["status"] == "APPROVED"
        assert str(decision["id"]) not in {d["id"] for d in old_approval["decisions"]}
        assert str(decision["id"]) in {d["id"] for d in new_approval["decisions"]}
        assert all(d["committed_server_at"] for d in new_approval["decisions"])
        old_audit, new_audit = old_files["sample/audit.json"], new_files["sample/audit.json"]
        assert str(audit_id) not in old_audit["commit_evidence"]
        assert str(audit_id) in new_audit["commit_evidence"]
        assert str(audit_id) not in old_audit["contracts"][str(cid)]
        assert str(audit_id) in new_audit["contracts"][str(cid)]
        assert new_audit["control_totals"]["row_count"] == len(new_audit["events"])
        from erev_api.problems import Problem

        with pytest.raises(Problem, match="unavailable at its source cutoff"):
            evidence_sample_decisions.collect(
                reader,
                replace(selection, known_at=before_request_commit),
                approval_request_ids=(request_id,),
            )
    from types import SimpleNamespace

    from erev_api.domain.reports.builders import RETAINED, SourceCollector, audit_log_export

    for parameters in ({"contract_id": str(cid)}, {}):
        params = ReportParams(
            report_code="audit_log_export",
            report_version=1,
            parameters=parameters,
            entity_ids=(),
            known_at=cutoff,
            historical=True,
            sources=SourceCollector(),
        )
        with world.place.uow(principal) as reader:
            old_export = audit_log_export.build(reader, params)
            new_export = audit_log_export.build(reader, replace(params, known_at=now, sources=None))
        assert str(audit_id) not in {row["id"] for row in old_export.rows}
        assert str(audit_id) in {row["id"] for row in new_export.rows}
        bound = params.sources.binding(
            row_keys=[row["row_key"] for row in old_export.rows],
            strategy=RETAINED,
        )
        # No database is provided: rebuild must derive rows/controls solely from input evidence.
        rebuilt = audit_log_export.build(
            SimpleNamespace(principal=principal),
            replace(params, known_at=now, sources=None, binding=bound),
        )
        assert rebuilt.rows == old_export.rows
        assert rebuilt.control_totals == old_export.control_totals
    commit_evidence.recover_pending_sources(world.place.tenant_id)
    for kind, identity in (
        ("approval_decision", decision["id"]),
        ("posting_ack", ack["id"]),
        ("audit_event", audit_id),
    ):
        commit = world.place.scalar(
            select(historical_source_commit.c.committed_server_at).where(
                historical_source_commit.c.source_kind == kind,
                historical_source_commit.c.source_id == identity,
            )
        )
        assert cutoff < commit <= now


def test_sample_documents_use_committed_attachment_lifecycle(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    import io
    from dataclasses import replace
    from datetime import date

    from erev_api.domain.platform.attachments import attach_evidence, void_attachment
    from erev_api.domain.reports import evidence_sample_documents
    from erev_api.domain.reports.evidence_commands import PERMISSIONS
    from erev_api.domain.reports.evidence_selection import SourceSelection
    from erev_api.enums import FilePurpose
    from erev_api.files.store import store_file
    from support.worlds import K01

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    permissions = world.place.principal.permissions | PERMISSIONS
    principal = replace(
        world.place.principal,
        permissions=permissions,
        permission_scopes={
            **world.place.principal.permission_scopes,
            **{p: "*" for p in permissions},
        },
    )
    cid = UUID(str(world.contracts[K01].contract["id"]))
    selection = SourceSelection(principal.tenant_id, clock.now(), (), (cid,))
    content = b"contract,evidence\nK01,committed cutoff\n"
    with world.place.uow(principal) as writer:
        stored = store_file(
            writer,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(content),
            original_filename="contract.csv",
            media_type="text/csv",
        )
        attachments = attach_evidence(
            writer, file_object_id=stored["id"], subject_type="contract", subject_ids=[cid]
        )
        before_commit = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    clock.set(world.place.scalar(select(func.clock_timestamp())))

    def collect(at):
        with world.place.uow(principal) as reader:
            result = evidence_sample_documents.collect(
                reader,
                replace(selection, known_at=at),
                as_of=date(2026, 9, 30),
                event_ids=(),
                approval_request_ids=(),
            )
        return result, json.loads(result.files[0].content)

    assert collect(before_commit)[1]["attachments"] == []
    result, original = collect(clock.now())
    assert result.file_ids == (stored["id"],)
    assert result.files[1].content == content
    assert original["schema_version"] == 2
    assert original["attachments"][0]["source_revision_id"]
    assert original["attachments"][0]["committed_at"]
    with world.place.uow(principal) as writer:
        void_attachment(writer, attachments[0], reason="Historical sample test")
        before_void_commit = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    assert collect(before_void_commit)[1]["attachments"] == original["attachments"]
    assert collect(clock.now())[1]["attachments"] == []
