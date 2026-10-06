"""RPT-41 report run over stored T-MIG rows (BUILD_SPEC LMG-3
``test_report_run_migration_reconciliation`` — named there under
tests/domain/migration/test_reconciliation.py; it lives here because pg tests live only under
tests/pg/, DG-TST-07; SCREENS_B §5.6.7 RPT-41 rev 1.13; BS-D-06). WRITTEN, NOT RUN on the lane (the
databases ``erev_rv_l24_*`` are Ray-side) — lane record docs/reviews/loop/prod/F-LMG.md §20.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import file_object, job, migration_batch, migration_reconciliation_line
from erev_api.domain.migration import legacy_db, reconciliation, repository
from erev_api.enums import FilePurpose, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.uow import UnitOfWork
from sqlalchemy import insert, select, text
from support.architecture import ROOT
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.principals import member
from support.reference import get, holding, post
from support.rows import file_object_values, migration_batch_values

pytestmark = pytest.mark.pg

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
RUNS = "/api/v1/report-runs"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def _run(context: DbContext, job_id: UUID, runtime: JobRuntime, *, attempt: int = 1) -> None:
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, context.tenant_id, attempt=attempt, runtime=runtime)


def _start(app: Any, actor: Any, migration_id: UUID) -> tuple[UUID, UUID]:
    started = post(
        app,
        RUNS,
        actor,
        {
            "report_code": "migration_reconciliation",
            "parameters": {"migration_id": str(migration_id)},
            "output_format": "JSON",
        },
    )
    assert started.status_code == 202, started.text
    return UUID(started.headers["x-erev-report-run-id"]), UUID(started.json()["id"])


def test_report_run_migration_reconciliation(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    # A stored WLD-X-27 batch (profile 4 contracts / 16 legacy POB rows; 136 T-MIG-03 lines with
    # no difference): the run gives control totals contracts 4, legacy_obligation_rows 16,
    # line_count 136, differences / explained / unexplained 0, tie-out PASS and the row
    # line:Contract 1::TRANSACTION_PRICE; an unknown migration_id fails the run with the
    # RPT-41 refusal "Choose a migration.".
    app = create_app(app_settings, clock=clock)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))
    stamp_test_release()
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    tenant_id = maya_member.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    source = reconciliation.legacy_values(legacy_db.latest_rows(legacy_db.rows(FIXTURE)))
    lines = reconciliation.lines(source, source)
    stamp = cast(
        UnitOfWork,
        SimpleNamespace(
            now=clock.now(),
            principal=SimpleNamespace(id=None, kind=PrincipalKind.SYSTEM, tenant_id=tenant_id),
        ),
    )
    with tenant_session(context) as session:
        file_row = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
        session.execute(insert(file_object).values(**file_row))
        batch = migration_batch_values(
            tenant_id,
            source_file_id=file_row["id"],
            status="RECONCILED",
            profile={"contracts": 4, "legacy_pob_rows": 16, "contract_live_rows": 24},
        )
        session.execute(insert(migration_batch).values(**batch))
        session.execute(
            insert(migration_reconciliation_line),
            [repository.line_values(stamp, batch["id"], line, {}) for line in lines],
        )
    run_id, job_id = _start(app, maya, UUID(str(batch["id"])))
    _run(context, job_id, runtime)
    record: dict[str, Any] = get(app, f"{RUNS}/{run_id}", maya).json()
    assert record["status"] == "SUCCEEDED", record
    assert record["control_totals"] == {
        "contracts": 4,
        "legacy_obligation_rows": 16,
        "line_count": 136,
        "differences_above_tolerance": 0,
        "explained": 0,
        "unexplained": 0,
    }
    assert record["tie_out_results"][0]["result"] == "PASS"
    rows = get(app, f"{RUNS}/{run_id}/data", maya, {"limit": "200"}).json()["items"]
    assert "line:Contract 1::TRANSACTION_PRICE" in {row["row_key"] for row in rows}
    # an unknown migration: both attempts fail with the RPT-41 refusal (RV-14 record kept)
    failed_run, failed_job = _start(app, maya, UUID(int=99))
    for attempt in (1, 2):
        _run(context, failed_job, runtime, attempt=attempt)
    failed: dict[str, Any] = get(app, f"{RUNS}/{failed_run}", maya).json()
    assert failed["status"] == "FAILED"
    assert failed["problem"]["errors"][0]["message"] == "Choose a migration."
