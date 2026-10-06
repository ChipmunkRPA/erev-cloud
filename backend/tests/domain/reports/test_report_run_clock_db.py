"""F-RPS-CUTOFF-R1 — the registered path's validation clock at the REAL ``create_run`` boundary
(Codex 1845 / 1952 item 4), end to end through ``POST /report-runs``. DB-bound: written for the
lane's ``erev_rv_l17_test`` and recorded **not run — databases not provisioned**; it runs in an
admitted database stage (the integrated batch's ``ci`` stage collects this directory).

Shape of POS-CHK-117's March checkpoint: the application ``FrozenClock`` sits at an item's business
time while the checkpoint's ``known_at`` is the server stamp (``SELECT clock_timestamp()``) taken
after the last commit. ``framework._resolve`` refuses a ``known_at`` later than ``uow.now``
(``KNOWN_AT_FUTURE``): on the business clock the stamp is refused by name; on the record-time clock
(the clock the runner's ``WorkspaceJobs.report_run`` fixes at one server read) the same request
is accepted and stored ``historical`` with the stamp unchanged — nothing substituted, advanced or
bypassed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.domain.reports import framework
from erev_api.domain.reports.catalogue import HISTORICAL_BASIS, KNOWN_AT_BASIS_KEY
from erev_api.domain.reports.outputs import utc_text
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.reference import get, post
from support.worlds import (
    AVM_US,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    ReportWorld,
    k01_pellworth,
    resigned,
)

CODE: Final = "contract_balances"
BALANCES: Final = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": "FY2026-P09"}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    return k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))


def test_the_server_stamp_is_refused_on_the_business_clock_and_accepted_on_record_time(
    world: ReportWorld, clock: FrozenClock
) -> None:
    business_at = clock.now()
    stamp = world.place.scalar(select(func.clock_timestamp()))  # the checkpoint's known_at
    assert isinstance(stamp, datetime) and stamp > business_at
    body = {
        "report_code": CODE,
        "parameters": {**BALANCES, "known_at": utc_text(stamp)},
        "output_format": "JSON",
    }
    # On the business clock the record-time stamp is "later than now": refused by name.
    refused = post(world.app, REPORT_RUNS, world.maya, body)
    assert refused.status_code == 422, refused.text
    problem = refused.json()
    assert [(e["field"], e["message"]) for e in problem["errors"]] == [
        (f"parameters.{framework.KNOWN_AT}", framework.KNOWN_AT_FUTURE)
    ]
    # On the record-time clock (one server read, as WorkspaceJobs.report_run fixes it) the same
    # request is accepted; the stamp is stored unchanged with the historical basis.
    clock.set(stamp + timedelta(seconds=1))
    world = resigned(world)  # the jump (+ days) would end every session at the 12-hour limit
    started = post(world.app, REPORT_RUNS, world.maya, body)
    assert started.status_code == 202, started.text
    shown = get(world.app, f"{REPORT_RUNS}/{started.headers[REPORT_RUN_ID_HEADER]}", world.maya)
    assert shown.status_code == 200, shown.text
    run = shown.json()
    assert run["parameters"]["known_at"] == utc_text(stamp)
    assert run["parameters"][KNOWN_AT_BASIS_KEY] == HISTORICAL_BASIS
