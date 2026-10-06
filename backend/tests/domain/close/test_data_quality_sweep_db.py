"""SCH-10 ``data_quality_monitors`` database witnesses (record §4.30). NOT RUN on the lane
(database-bound; the integrated batch measures). Every run is scoped to the world's tenant
through ``only_tenants``."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import exception_item, notification
from erev_api.domain.close import data_quality_sweep, monitor_rules, monitors
from erev_api.enums import ExceptionSeverity, ExceptionSource, NotificationKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.close_world import CloseWorld, close_world, identity_duplicates, system_session
from support.db import TestDatabase


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _items(world: CloseWorld, code: str) -> list[dict[str, Any]]:
    with system_session(world) as session:
        rows = (
            session.execute(
                select(exception_item)
                .where(exception_item.c.code == code)
                .order_by(exception_item.c.created_at, exception_item.c.id)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def test_the_sweep_evaluates_every_open_period_and_raises_the_september_duplicate(
    world: CloseWorld,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AVM-US has FY2026 P01 to P09 open and P10 onwards future: nine periods are evaluated in
    start-date order (P01 first). The fixture is a RULE 2 duplicate (two external ids sharing one
    identity tuple, one date — ``identity_duplicates``); it does not distinguish Rule 1's earliest
    from latest anchor (Codex 0530; Rule 1 is witnessed at the pure-rule level). The September
    duplicate is ONE BLOCKING item scoped to P09 — P01–P08 get no item for September's data
    (SCH10-PERIOD-SCOPE-1) — with the NTF-11 notification to the Revenue Accountant; a second sweep
    sees that one item again exactly once (an authored assertion of this line: the P09 evaluation
    alone) and creates nothing. ``evaluated`` counts completed ``run_monitors`` calls, including a
    no-op after a period-state race; only a ``Problem`` inside ``run_monitors`` is caught. A sweep
    whose monitors no longer find the duplicate settles its item — RESOLVED by the SYSTEM — and
    counts it (05 SCH-10 rev 1.124; 04 T-IMP-05 "A monitor finding that is gone"; the facts are
    withheld for that sweep, a source invoice being append-only)."""
    with system_session(world) as session:
        identity_duplicates(session, world, issue_date=date(2026, 9, 3))
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)

    report = data_quality_sweep.run(runtime, only_tenants=[world.tenant_id])

    assert (report.tenants, report.periods, report.evaluated, report.failed) == (1, 9, 9, 0)
    assert report.created == 1
    (item,) = _items(world, "DQ_DUPLICATE_INVOICE")
    assert (item["severity"], item["source"], item["status"], item["period_id"]) == (
        ExceptionSeverity.BLOCKING.value,
        ExceptionSource.DATA_QUALITY.value,
        "OPEN",
        world.period_id,
    )
    with system_session(world) as session:
        kinds = session.scalars(
            select(notification.c.kind).where(
                notification.c.recipient_membership_id == world.maya.member.membership_id,
                notification.c.subject_id == item["id"],
            )
        ).all()
    assert [str(kind) for kind in kinds] == [NotificationKind.EXCEPTION_ASSIGNED.value]

    # The earlier-period negative: no DQ item of the entity is scoped to P01–P08.
    earlier = [
        row for row in _items(world, "DQ_DUPLICATE_INVOICE") if row["period_id"] != world.period_id
    ]
    assert earlier == []

    again = data_quality_sweep.run(runtime, only_tenants=[world.tenant_id])
    assert (again.evaluated, again.created, again.failed) == (9, 0, 0)
    assert again.seen_again == 1  # the P09 evaluation alone sees the item again
    (same,) = _items(world, "DQ_DUPLICATE_INVOICE")
    assert (same["id"], same["period_id"], same["occurrence_count"]) == (
        item["id"],
        world.period_id,
        2,
    )
    assert (report.settled, again.settled) == (0, 0)  # the finding stood in both sweeps

    with monkeypatch.context() as withheld:
        withheld.setattr(monitors, "collect_inputs", lambda *_: monitor_rules.MonitorInputs())
        swept = data_quality_sweep.run(runtime, only_tenants=[world.tenant_id])
    assert (swept.evaluated, swept.created, swept.seen_again, swept.settled) == (9, 0, 0, 1)
    (done,) = _items(world, "DQ_DUPLICATE_INVOICE")
    assert (done["id"], done["status"], done["resolved_by"], str(done["resolved_by_kind"])) == (
        item["id"],
        "RESOLVED",
        None,
        "SYSTEM",
    )
