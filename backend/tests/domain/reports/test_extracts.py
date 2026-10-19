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


def test_obligation_extract_latest_and_retained_sources(
    app: FastAPI, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    from datetime import date
    from decimal import Decimal

    from erev_api.db.tables import contract, obligation_version
    from erev_api.domain.reports.builders.extract_obligations import COLUMNS
    from erev_api.enums import ContractEventType
    from erev_api.events.payloads import BillingRecordedV1
    from erev_api.events.stream import EventIn
    from erev_api.money import MoneyIn
    from sqlalchemy import func
    from support.factories import appended, computed
    from support.worlds import K01

    world = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp + timedelta(seconds=1))
    world = resigned(world)
    params = {"entity_codes": [AVM_US], "book": "ASC606", "known_at": clock.now().isoformat()}
    original, rows = report_run(world, "extract_obligations", params)
    assert rows
    expected_columns = [
        c.name for c in obligation_version.c if c.name not in {"tenant_id", "trace_nodes"}
    ]
    assert [col.key for col in COLUMNS] == [*expected_columns, "contract_external_id"]
    data = get(app, f"{REPORT_RUNS}/{original['id']}/output", world.maya).json()
    assert data["control_totals"]["by_currency"]["USD"] == {
        key: str(sum((Decimal(row[key]) for row in rows), Decimal(0)))
        for key in ("allocated_amount", "revenue_cum")
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
    computed(world.place, group_id)
    _, latest = report_run(
        world, "extract_obligations", {**params, "known_at": clock.now().isoformat()}
    )
    assert {r["id"] for r in rows}.isdisjoint(r["id"] for r in latest)
    assert len(latest) == len(rows)
    assert sum(Decimal(r["billed_cum"]) for r in latest) > sum(
        Decimal(r["billed_cum"]) for r in rows
    )
    _, incremental = report_run(
        world,
        "extract_obligations",
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
