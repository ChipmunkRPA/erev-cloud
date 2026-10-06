"""``MIGRATION_RECONCILE`` over a database (BUILD_SPEC LMG-3; PRD SM-12). WRITTEN, NOT RUN on the
lane (the databases ``erev_rv_l24_*`` are Ray-side) — lane record docs/reviews/loop/prod/F-LMG.md
§23. Measured here: an IMPORTED batch whose comparison population is not captured (the current
state for both modes — the import / replay slices supply it) fails the job, after its attempts,
with the refusal that names the missing source of its mode; nothing moves, no line is written, and
the latest live computation is not read in its place (Codex F1 on a2aad104). The REPLAY case
creates the sandbox tenant its batch references (Codex R1 on d093acee). The reconciling path over
a captured population follows those slices.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    file_object,
    job,
    migrated_legacy_row,
    migration_batch,
    migration_reconciliation_line,
)
from erev_api.domain.migration import (
    jobs,  # noqa: F401  (registers MIGRATION_RECONCILE — the module must run alone too)
    legacy_db,
    population,
    repository,
)
from erev_api.enums import FilePurpose, JobKind, MigrationMode, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from sqlalchemy import func, insert, select, text
from support.architecture import ROOT
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.principals import member
from support.rows import file_object_values, insert_sandbox_tenant, migration_batch_values

pytestmark = pytest.mark.pg

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.mark.parametrize("mode", [MigrationMode.OPENING_BALANCES, MigrationMode.REPLAY])
def test_reconcile_job_refuses_by_name_an_uncaptured_population(
    committed_db: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    mode: MigrationMode,
) -> None:
    runtime = JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))
    stamp_test_release()
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    over: dict[str, Any] = {}
    if mode is MigrationMode.REPLAY:
        # the T-MIG-01 sandbox_tenant_id → tenant foreign key (0056): the referenced sandbox tenant
        # of kind SANDBOX exists before the batch names it (Codex R1 on d093acee; the established
        # seam insert_sandbox_tenant, as tests/pg/test_db_invariants.py uses it)
        over = {"cutover_date": None, "sandbox_tenant_id": insert_sandbox_tenant(keyring)}
    with tenant_session(context) as session:
        file_row = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
        session.execute(insert(file_object).values(**file_row))
        batch = migration_batch_values(
            tenant_id, source_file_id=file_row["id"], status="IMPORTED", mode=mode.value, **over
        )
        session.execute(insert(migration_batch).values(**batch))
        stamp = type("Uow", (), {})()
        stamp.principal = type(
            "P", (), {"id": None, "kind": PrincipalKind.SYSTEM, "tenant_id": tenant_id}
        )()
        stamp.now = clock.now()
        session.execute(
            insert(migrated_legacy_row),
            [
                repository.legacy_row_values(stamp, batch["id"], row)  # type: ignore[arg-type]
                for row in legacy_db.rows(FIXTURE)
            ],
        )
        row = registry.insert_job(
            session,
            JobKind.MIGRATION_RECONCILE,
            {"migration_id": str(batch["id"])},
            tenant_id=tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=clock.now()
        )
    job_id = UUID(str(row["id"]))
    for attempt in (1, 2):
        with tenant_session(context) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(_FETCHED, {"id": task_id})
        registry.run_job(job_id, tenant_id, attempt=attempt, runtime=runtime)
    with tenant_session(context) as session:
        state: Any = session.execute(
            select(job.c.state, job.c.problem).where(job.c.id == job_id)
        ).one()
        status = session.execute(
            select(migration_batch.c.status).where(migration_batch.c.id == batch["id"])
        ).scalar_one()
        lines = session.execute(
            select(func.count())
            .select_from(migration_reconciliation_line)
            .where(migration_reconciliation_line.c.migration_batch_id == batch["id"])
        ).scalar_one()
    assert state[0] == "FAILED"
    assert state[1]["detail"] == population.not_captured_copy(mode)
    assert status == "IMPORTED"  # nothing moved
    assert lines == 0  # no line written
