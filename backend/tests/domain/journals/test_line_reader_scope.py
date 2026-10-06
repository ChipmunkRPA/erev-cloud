"""Register index 182 (04 §16.7 rev 1.245; the supervisor's rulings of 2026-10-01 and 2026-10-02):
what ``GET /journal-runs/{id}/lines`` answers a reader whose entities do not hold the line's
contract or its counterparty, and what ``GET /journal-batches/{id}/download`` hands her.

World: PRD WLD-K-04 (``support.worlds.k04_saltmarsh``). ``SF-ORD-UK-2001`` is contracted by AVM-UK;
its O1 is performed by AVM-US, so the ledger of AVM-US holds lines of a contract of AVM-UK, one of
them on the intercompany account 1800 with AVM-UK as its counterparty. Maya reads every entity.
Ursa is a Revenue Accountant of AVM-US only: she reads the run of AVM-US and its lines, while the
contract's row (T-CON-01, RLS-TE by the contracting entity) and the row of AVM-UK (T-ORG-02,
RLS-TE) are outside her scope.

The defect (PRODUCT DEFECT of the blocker class, measured on 2 October 2026 on the head before the
item): the read answered Ursa 500. The row was built from two outer joins that find nothing for
her — the contract's external id and the counterparty's code and name — into members typed as
strings. Beside it, measured the same day: the batch she downloaded before its export was rendered
under her entity scope, so its lines' references lacked the contract's name, and the file and the
digest in its audit event differed from those of a reader of every entity.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from typing import Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, journal_batch
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.principals import colleague
from support.reference import approve, get, holding, post
from support.worlds import (
    AVM_UK,
    AVM_US,
    JOURNAL_RUNS,
    K04,
    RUN_ID_HEADER,
    k04_saltmarsh,
    run_now,
    verified,
)

APRIL: Final = "FY2026-P04"
GRAIN: Final = "CONTRACT_ACCOUNT_DIMENSIONS"
INTERCOMPANY: Final = "1800"
REVENUE: Final = "4010"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.mark.slow
def test_a_reader_of_one_entity_reads_the_lines_of_a_contract_of_another(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A reader of the run's entity alone reads every line of the run. The contract of a line is
    stated by its id, which is the line's own, and its external id is null where the contract is
    outside the reader's entity scope — as API-S-SubledgerLine answers ``contract_external_id``.
    The counterparty of an intercompany line is named — id, code and name — to every reader of
    the line. Nothing else of a line differs between the two readers."""
    k04 = k04_saltmarsh(app, keyring, clock, files)
    report = k04.report
    maya = report.maya
    ursa = holding(
        app,
        colleague(report.tenant_id, "ursa"),
        "revenue_accountant",
        entity_ids=[k04.us_entity_id],
    )
    started = post(
        app, JOURNAL_RUNS, maya, {"entity_code": AVM_US, "period_key": APRIL, "grain": GRAIN}
    )
    assert started.status_code == 202, started.text
    assert run_now(report, UUID(str(started.json()["id"])))["state"] == "SUCCEEDED"
    path = f"{JOURNAL_RUNS}/{started.headers[RUN_ID_HEADER]}/lines"

    whole = get(app, path, maya, {"limit": 200})
    assert whole.status_code == 200, whole.text
    named = {line["account"]["code"]: line for line in whole.json()["items"]}
    assert sorted(named) == [INTERCOMPANY, REVENUE]
    contract = {"id": str(k04.contract_id), "external_id": K04}
    assert [named[code]["contract"] for code in (INTERCOMPANY, REVENUE)] == [contract, contract]
    counterparty = named[INTERCOMPANY]["counterparty_entity"]
    assert (counterparty["id"], counterparty["code"]) == (str(k04.uk_entity_id), AVM_UK)
    assert counterparty["name"]
    assert named[INTERCOMPANY]["account_role"] == "INTERCOMPANY_DUE_FROM"
    assert named[REVENUE]["counterparty_entity"] is None

    # neither the contract nor the counterparty is a row Ursa reads
    assert get(app, f"/api/v1/contracts/{k04.contract_id}", ursa).status_code == 404
    assert get(app, f"/api/v1/entities/{k04.uk_entity_id}", ursa).status_code == 404

    scoped = get(app, path, ursa, {"limit": 200})
    assert scoped.status_code == 200, scoped.text  # 500 before the item
    own = {line["account"]["code"]: line for line in scoped.json()["items"]}
    assert sorted(own) == [INTERCOMPANY, REVENUE]
    unnamed = {"id": str(k04.contract_id), "external_id": None}
    assert [own[code]["contract"] for code in (INTERCOMPANY, REVENUE)] == [unnamed, unnamed]
    assert own[INTERCOMPANY]["counterparty_entity"] == counterparty
    assert own[REVENUE]["counterparty_entity"] is None
    for code in (INTERCOMPANY, REVENUE):
        assert {**own[code], "contract": None} == {**named[code], "contract": None}

    # the filter by the line's own contract id answers both readers the same lines
    for reader in (maya, ursa):
        filtered = get(app, path, reader, {"contract": str(k04.contract_id), "limit": 200})
        assert filtered.status_code == 200, filtered.text
        assert sorted(line["account"]["code"] for line in filtered.json()["items"]) == [
            INTERCOMPANY,
            REVENUE,
        ]


def _references(content: bytes, external_id: str) -> list[str]:
    """The ``source_references`` column of the CSV in a downloaded batch, in line order."""
    archive = zipfile.ZipFile(io.BytesIO(content))
    name = external_id.replace(":", "_")
    [header, *rows] = list(csv.reader(io.StringIO(archive.read(f"{name}.csv").decode("utf-8"))))
    column = header.index("source_references")
    return [row[column] for row in rows]


@pytest.mark.slow
def test_a_batch_is_downloaded_as_it_leaves_whoever_downloads_it(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 §16.7 ``GET /journal-batches/{id}/download`` (rev 1.245; the supervisor's ruling of
    2026-10-02 on the lane's point three): one artifact, one digest. A batch without a stored
    file — approved and not yet exported — is rendered from its lines, and a line's reference is
    part of the entry: the external id of its contract, then the journal line's identity. Maya
    and Ursa, who is not told the contract's name on the screen, download one batch: equal bytes,
    the contract named in every reference, and one digest in the two ``journal_batch.download``
    events. Before the item the rendering ran under the caller's entity scope: Ursa's file lacked
    the name and her event recorded another digest for the same batch."""
    k04 = k04_saltmarsh(app, keyring, clock, files)
    report = k04.report
    maya = report.maya
    ursa = holding(
        app,
        colleague(report.tenant_id, "ursa"),
        "revenue_accountant",
        entity_ids=[k04.us_entity_id],
    )
    started = post(
        app, JOURNAL_RUNS, maya, {"entity_code": AVM_US, "period_key": APRIL, "grain": GRAIN}
    )
    assert started.status_code == 202, started.text
    assert run_now(report, UUID(str(started.json()["id"])))["state"] == "SUCCEEDED"
    run = f"{JOURNAL_RUNS}/{started.headers[RUN_ID_HEADER]}"
    submitted = post(app, f"{run}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    report = verified(report, clock, "priya")
    decided = approve(app, str(submitted.json()["approval_request_id"]), report.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    listed = get(app, f"{run}/batches", maya)
    assert listed.status_code == 200, listed.text
    (batch,) = listed.json()["items"]
    assert batch["state"] == "approved"
    batch_id = UUID(str(batch["id"]))
    # nothing is stored yet: the download renders the batch's lines
    stored = report.place.rows(
        select(journal_batch.c.export_file_id).where(journal_batch.c.id == batch_id)
    )
    assert [row["export_file_id"] for row in stored] == [None]

    path = f"/api/v1/journal-batches/{batch_id}/download"
    whole = get(app, path, maya)
    assert whole.status_code == 200, whole.text
    references = _references(whole.content, str(batch["external_id"]))
    assert len(references) == 2
    assert all(reference.startswith(f"{K04}; journal_line=") for reference in references)

    scoped = get(app, path, ursa)
    assert scoped.status_code == 200, scoped.text
    assert _references(scoped.content, str(batch["external_id"])) == references
    assert scoped.content == whole.content
    digest = hashlib.sha256(whole.content).hexdigest()
    events = report.place.rows(
        select(audit_event.c.actor_id, audit_event.c.detail)
        .where(
            audit_event.c.action == "journal_batch.download", audit_event.c.object_id == batch_id
        )
        .order_by(audit_event.c.chain_seq)
    )
    assert [(row["actor_id"], row["detail"]["sha256"]) for row in events] == [
        (maya.member.user_id, digest),
        (ursa.member.user_id, digest),
    ]
