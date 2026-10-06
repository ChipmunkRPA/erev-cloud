"""CLO-8 ``POST /journal-runs`` and the run summary (04 §15.3 API-R-38, §16.7
API-S-JournalRunCreate, API-S-JournalRunSummary, API-C-04; T-SL-06; BUILD_SPEC CLO-8).

World: ``support.worlds.journal_world`` with the CHK-022 intents posted (L6-3-Q-1).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.factories import run_import_job
from support.http import call
from support.principals import cookie_headers
from support.reference import fields, get, post, slug
from support.worlds import (
    ENTITY_1,
    JANUARY,
    JOURNAL_RUNS,
    RUN_ID_HEADER,
    journal_world,
    post_chk_022,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def test_create_run_contract(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    maya = world.legacy.maya
    body = {"entity_code": ENTITY_1, "period_key": JANUARY}

    unkeyed = call(
        app,
        "POST",
        JOURNAL_RUNS,
        json=body,
        headers=cookie_headers(maya.token, maya.csrf_token, key=False),
    )
    assert (unkeyed.status_code, slug(unkeyed)) == (422, "validation-failed"), unkeyed.text
    assert fields(unkeyed)[0][1] == "API-C-04"

    legacy = post(app, JOURNAL_RUNS, maya, {**body, "book": "LEGACY"})
    assert (legacy.status_code, slug(legacy)) == (422, "validation-failed"), legacy.text
    assert fields(legacy) == [("book", "T-SL-06")]

    created = post(app, JOURNAL_RUNS, maya, body)
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]
    assert created.headers["Location"] == f"/api/v1/jobs/{job_id}"
    assert created.json()["kind"] == "JOURNAL_RUN_CALCULATE"
    run_id = created.headers[RUN_ID_HEADER]
    run_import_job(world.legacy.imports, UUID(job_id))
    job = get(app, f"/api/v1/jobs/{job_id}", maya)
    assert job.status_code == 200, job.text
    assert (job.json()["state"], job.json()["result"]["href"]) == (
        "SUCCEEDED",
        f"/api/v1/journal-runs/{run_id}",
    )
    # POL-005 and POL-006 under LEGACY_PARITY: GROSS at the LEGACY_CONTRACT_POB grain.
    shown = get(app, f"{JOURNAL_RUNS}/{run_id}", maya)
    assert shown.status_code == 200, shown.text
    assert (shown.json()["mode"], shown.json()["grain"]) == ("GROSS", "LEGACY_CONTRACT_POB")

    summary = get(app, f"{JOURNAL_RUNS}/{run_id}/summary", maya)
    assert summary.status_code == 200, summary.text
    checks = summary.json()["balance_checks"]
    assert [(item["basis"], item["currency"], item["difference"]["amount"]) for item in checks] == [
        ("TRANSACTION", "USD", "0.00"),
        ("FUNCTIONAL", "USD", "0.00"),
    ]
    assert [(item["debit"]["amount"], item["credit"]["amount"]) for item in checks] == [
        ("295.69", "295.69"),
        ("295.69", "295.69"),
    ]
    assert [item["account_code"] for item in summary.json()["lines"]] == [
        "21001",
        "5001",
        "5002",
        "5003",
    ]

    # SCREENS_B §3.1: SF-06 lists runs with sort=-period&count=true (API-R-38).
    listed = get(
        app, f"{JOURNAL_RUNS}?entity={ENTITY_1}&period={JANUARY}&sort=-period&count=true", maya
    )
    assert listed.status_code == 200, listed.text
    assert run_id in [item["id"] for item in listed.json()["items"]]
