"""DIN-3 dry-run diff (05 IPL-07; 04 §16.6 API-S-Import ``diff_summary``, API-S-ImportDiff, E-118;
PRD BR-DAT-05, WLD-X-23; 03 REQ-DAT-015; BUILD_SPEC DIN-3).

World: ``support.factories.j03_world`` (AVM-US and AVM-UK, customer C-12, AVM-PLAT-100 and
AVM-IMPL-PLUS in US-LIST 2026-H1). Maya uploads a CSV v2 ``contracts`` file booking
``SF-ORD-30001`` with the lines of PRD WLD-F-20; the validation and diff jobs run as the worker runs
them.
"""

from __future__ import annotations

import csv
import io
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    audit_event,
    contract,
    contract_event,
    import_row_lineage,
    job,
    obligation,
    source_record,
)
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    IMPORTS_PATH,
    ImportWorld,
    J03World,
    imported,
    j03_world,
    run_import_job,
)
from support.reference import get

CONTRACT_HEADERS = (
    "external_id",
    "customer_id",
    "contracting_entity_code",
    "transaction_currency",
    "inception_date",
    "document_ref",
    "lines.obligation_key",
    "lines.product_code",
    "lines.quantity",
    "lines.total_price.amount",
    "lines.total_price.currency",
    "lines.start_date",
    "lines.end_date",
    "lines.performing_entity_code",
)


def contracts_csv(
    customer: UUID, *, external_id: str = "SF-ORD-30001", implementation: str = "24000.00"
) -> bytes:
    """A CSV v2 ``contracts`` file: O1 AVM-PLAT-100 96,000.00 from 01 Sep 2026 to 31 Aug 2027 and
    O2 AVM-IMPL-PLUS performed by AVM-UK."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CONTRACT_HEADERS)
    header = [external_id, str(customer), "AVM-US", "USD", "2026-09-01", external_id]
    writer.writerow(
        [*header, "O1", "AVM-PLAT-100", "1", "96000.00", "USD", "2026-09-01", "2027-08-31", ""]
    )
    writer.writerow([*header, "O2", "AVM-IMPL-PLUS", "1", implementation, "USD", "", "", "AVM-UK"])
    return buffer.getvalue().encode("utf-8")


def job_of(world: ImportWorld, import_id: UUID, kind: str) -> UUID:
    rows = world.rows(
        select(job.c.id)
        .where(job.c.subject_id == import_id, job.c.kind == kind)
        .order_by(job.c.created_at)
    )
    assert rows, f"no {kind} job for {import_id}"
    return UUID(str(rows[-1]["id"]))


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> J03World:
    return j03_world(app, keyring, clock, files)


@pytest.fixture
def importer(
    world: J03World, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ImportWorld:
    return ImportWorld(
        app=world.app,
        actor=world.place.author,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )


def test_dry_run_diff_for_contract_rows(world: J03World, importer: ImportWorld) -> None:
    import_id, shown = imported(
        importer, "sf-ord-30001.csv", contracts_csv(world.customer_id), "contracts"
    )
    assert (shown["status"], shown["counts"]["rows"], shown["counts"]["errors"]) == (
        "VALIDATED",
        2,
        0,
    ), shown
    upload_id = UUID(import_id)
    early = get(world.app, f"{IMPORTS_PATH}/{import_id}/diff", importer.actor)
    assert early.status_code == 409, early.text
    assert early.json()["type"].endswith("invalid-transition")

    run_import_job(importer, job_of(importer, upload_id, "IMPORT_DIFF"))

    ready = get(world.app, f"{IMPORTS_PATH}/{import_id}", importer.actor).json()
    assert ready["status"] == "DIFF_READY", ready
    assert ready["diff_summary"] == {
        "contracts_affected": 1,
        "contracts_created": 1,
        "allocation_changes": [
            {"contract_external_id": "SF-ORD-30001", "before": None, "after": "97627.12"},
            {"contract_external_id": "SF-ORD-30001", "before": None, "after": "22372.88"},
        ],
        "revenue_by_period_delta": [],
        "journal_preview": [],
    }
    response = get(world.app, f"{IMPORTS_PATH}/{import_id}/diff", importer.actor)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary_counts"] == {
        "contracts_added": 1,
        "contracts_changed": 0,
        "obligations_added": 2,
        "obligations_changed": 0,
    }
    assert body["items"] == [
        {
            "change": "ADDED",
            "contract_external_id": "SF-ORD-30001",
            "obligation_key": None,
            "measure": "transaction_price",
            "before": None,
            "after": "120000.00",
        },
        {
            "change": "ADDED",
            "contract_external_id": "SF-ORD-30001",
            "obligation_key": "O1",
            "measure": "allocated_amount",
            "before": None,
            "after": "97627.12",
        },
        {
            "change": "ADDED",
            "contract_external_id": "SF-ORD-30001",
            "obligation_key": "O2",
            "measure": "allocated_amount",
            "before": None,
            "after": "22372.88",
        },
    ]
    assert body["next_cursor"] is None

    # Nothing is persisted before commit (BR-DAT-05): no contract, event, obligation, source record
    # or lineage row, and the diff audits only the upload.
    assert (
        importer.rows(select(contract.c.id).where(contract.c.external_id == "SF-ORD-30001")) == []
    )
    assert (
        importer.rows(
            select(contract_event.c.id).where(contract_event.c.import_upload_id == upload_id)
        )
        == []
    )
    assert importer.rows(select(obligation.c.id)) == []
    assert (
        importer.rows(
            select(source_record.c.id).where(source_record.c.import_upload_id == upload_id)
        )
        == []
    )
    assert (
        importer.rows(
            select(import_row_lineage.c.id).where(
                import_row_lineage.c.import_upload_id == upload_id
            )
        )
        == []
    )
    actions = [
        row["action"]
        for row in importer.rows(
            select(audit_event.c.action)
            .where(audit_event.c.request_id == f"job-{job_of(importer, upload_id, 'IMPORT_DIFF')}")
            .order_by(audit_event.c.chain_seq)
        )
    ]
    # The job's request id carries its own fact and, last, the registry's ``job.finish`` written
    # in the transaction that records the terminal state (04 T-PLT-27 rev 1.106; supervisor ruling
    # R-50 (a)); until that ruling the diff's fact was the only event of the request.
    assert actions == ["import_upload.diff", "job.finish"]
