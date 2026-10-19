"""Event BI extract through the real API and worker, including incremental and retained reads."""

import hashlib
import json
from datetime import timedelta
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_event
from erev_api.domain.reports.builders.extract_events import COLUMNS
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.redaction import CONTACT_FIELDS
from fastapi import FastAPI
from sqlalchemy import select
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
    cutoff = max(row["recorded_at"] for row in events)
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
    since = events[0]["recorded_at"]
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
        str(row["id"]) for row in events if row["recorded_at"] > since
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
    cutoff = max(max(row["created_at"], row["known_at"]) for row in versions)
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
    since = min(row["created_at"] for row in versions)
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
        str(row["id"]) for row in versions if row["created_at"] > since
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

    from erev_api.db.tables import subledger_line, subledger_posting_seal
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
    since = min(r["recorded_at"] for r in source)
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
        str(r["id"]) for r in source if r["recorded_at"] > since
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
            "known_since": max(r["recorded_at"] for r in before).isoformat(),
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
