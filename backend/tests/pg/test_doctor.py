"""``erev doctor --db test`` (03 REQ-CTL-005; dev-guide DG-MK-doctor; 05 RB-03; BUILD_SPEC PLF-30).

Each test starts from a freshly migrated ``erev_test``: the schema is reset and migrated as
``erev_owner`` as the session fixture does, and the pools are disposed, because recreated types get
new OIDs (``test_migrations.py``). One tenant is provisioned and its chain verified by the
``AUDIT_CHAIN_VERIFY`` job, played as the worker would (``test_audit_verification.py``).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from click.testing import Result
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import get_settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.domain.platform import audit_jobs  # noqa: F401  (registers AUDIT_CHAIN_VERIFY)
from erev_api.enums import JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from sqlalchemy import text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase, alembic_config, reset_schema
from support.factories import stamp_test_release, tenant_factory, tenant_id_of
from support.operators import invoke, operator_services
from support.rows import insert_engine_release, tamper_audit_event

pytestmark = pytest.mark.pg

CHECKS = (
    "row-level-security",
    "app-role",
    "immutability-triggers",
    "audit-chain",
    "ai",
    "setting-references",
)
# 05 REL-07 probe: a trigger function referencing a setting 04 does not list.
PROBE_FUNCTION = "tg_probe__data_fix"
_CREATE_PROBE = (
    f"CREATE FUNCTION erev.{PROBE_FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN IF coalesce(current_setting('app.data_fix_other', true), '') <> '' THEN RETURN NEW; "
    "END IF; RETURN NEW; END $$"
)
_DROP_PROBE = f"DROP FUNCTION IF EXISTS erev.{PROBE_FUNCTION}()"
TRIGGER = "tg_audit_event__immutable"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
_DISABLED_TRIGGERS = text(
    "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
    " JOIN pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'erev' AND NOT t.tgisinternal AND t.tgenabled = 'D'"
)


@dataclass(frozen=True, slots=True)
class Workspace:
    tenant_id: UUID
    code: str


def _verify(tenant_id: UUID, runtime: JobRuntime) -> None:
    """A SYSTEM SCHEDULED verification of the tenant, fetched and run as the worker would."""
    now = runtime.clock.now()
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        row = registry.insert_job(
            session,
            JobKind.AUDIT_CHAIN_VERIFY,
            {"trigger": "SCHEDULED"},
            tenant_id=tenant_id,
            now=now,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
        )
        procrastinate_job_id = registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=now
        )
        session.execute(_FETCHED, {"id": procrastinate_job_id})
    registry.run_job(UUID(str(row["id"])), tenant_id, attempt=1, runtime=runtime)


def _runtime(keyring: KeyRing, clock: FrozenClock, root: Path) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(root))


def _doctor(keyring: KeyRing, clock: FrozenClock, root: Path) -> Result:
    return invoke(operator_services(keyring, clock, root), ["doctor", "--db", "test"])


def _checks(result: Result, outcome: str) -> list[str]:
    return [
        line.split(":", 1)[0].removeprefix(f"{outcome} ")
        for line in result.stdout.splitlines()
        if line.startswith(f"{outcome} ")
    ]


@pytest.fixture
def workspace(test_database: TestDatabase, keyring: KeyRing, tmp_path: Path) -> Workspace:
    reset_schema(get_settings().owner_database_url())
    command.upgrade(alembic_config(), "head")
    test_database.app_engine.dispose()
    test_database.owner_engine.dispose()
    provisioned = tenant_factory(keyring=keyring)
    tenant_id = tenant_id_of(provisioned)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        insert_engine_release(session)  # SOP-1: the verification records CTL-039 evidence
    # 05 REL-03 (rev 1.15; D-98 60): the verification job runs in THIS process, and the CTL-039
    # evidence producer stamps the process release — a process that never stamped fails closed
    # (release-mismatch) whatever rows the table holds, so the job runtime stamps through the shared
    # pg support exactly as the world factories do (P5-DOCTOR-R1).
    stamp_test_release()
    _verify(tenant_id, _runtime(keyring, frozen_clock(), tmp_path / "files"))
    return Workspace(tenant_id=tenant_id, code=str(provisioned.tenant["code"]))


def test_req_ctl_005_doctor_passes_on_fresh_database(
    workspace: Workspace, keyring: KeyRing, tmp_path: Path, log_stream: io.StringIO
) -> None:
    result = _doctor(keyring, frozen_clock(), tmp_path / "files")

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert _checks(result, "OK") == list(CHECKS)
    assert len(lines) == len(CHECKS)
    assert lines[3] == "OK audit-chain: latest verification PASS for 1 of 1 tenants"
    assert lines[4] == "OK ai: ai.enabled defaults to false; AI enabled for 0 of 1 tenants"


def test_doctor_detects_disabled_trigger(
    workspace: Workspace,
    test_database: TestDatabase,
    keyring: KeyRing,
    tmp_path: Path,
    log_stream: io.StringIO,
) -> None:
    owner = test_database.owner_engine
    with owner.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE erev.audit_event DISABLE TRIGGER {TRIGGER}")
    try:
        result = _doctor(keyring, frozen_clock(), tmp_path / "files")
    finally:
        with owner.begin() as connection:
            connection.exec_driver_sql(f"ALTER TABLE erev.audit_event ENABLE TRIGGER {TRIGGER}")
    with owner.connect() as connection:
        assert connection.execute(_DISABLED_TRIGGERS).scalar_one() == 0

    assert result.exit_code == 1, result.output
    failures = [line for line in result.stdout.splitlines() if line.startswith("FAIL ")]
    assert set(_checks(result, "FAIL")) == {"immutability-triggers"}
    assert f"FAIL immutability-triggers: trigger {TRIGGER} on audit_event is disabled" in failures
    assert _checks(result, "OK") == [
        "row-level-security",
        "app-role",
        "audit-chain",
        "ai",
        "setting-references",
    ]


def test_doctor_detects_failed_verification(
    workspace: Workspace,
    test_database: TestDatabase,
    keyring: KeyRing,
    tmp_path: Path,
    log_stream: io.StringIO,
) -> None:
    tamper_audit_event(test_database.owner_engine, tenant_id=workspace.tenant_id, chain_seq=2)
    later = frozen_clock(FROZEN_AT + timedelta(hours=1))
    _verify(workspace.tenant_id, _runtime(keyring, later, tmp_path / "files"))

    result = _doctor(keyring, later, tmp_path / "files")

    assert result.exit_code == 1, result.output
    failures = [line for line in result.stdout.splitlines() if line.startswith("FAIL ")]
    assert failures == [
        f"FAIL audit-chain: tenant {workspace.code}: latest audit chain verification is FAIL"
        " from sequence 2"
    ]
    assert _checks(result, "OK") == [
        "row-level-security",
        "app-role",
        "immutability-triggers",
        "ai",
        "setting-references",
    ]


def test_rel_07_unknown_setting_reference(
    workspace: Workspace,
    test_database: TestDatabase,
    keyring: KeyRing,
    tmp_path: Path,
    log_stream: io.StringIO,
) -> None:
    """05 REL-07: a function referencing ``app.data_fix_other`` makes the command exit 1 naming the
    function and the setting; the other checks stay OK (BUILD_SPEC SOP-6)."""
    owner = test_database.owner_engine
    with owner.begin() as connection:
        connection.exec_driver_sql(_CREATE_PROBE)
    try:
        result = _doctor(keyring, frozen_clock(), tmp_path / "files")
    finally:
        with owner.begin() as connection:
            connection.exec_driver_sql(_DROP_PROBE)

    assert result.exit_code == 1, result.output
    failures = [line for line in result.stdout.splitlines() if line.startswith("FAIL ")]
    assert failures == [
        f"FAIL setting-references: function {PROBE_FUNCTION}() references setting "
        "app.data_fix_other, which 04 does not list (05 REL-07)"
    ]
    assert _checks(result, "OK") == list(CHECKS[:-1])
    clean = _doctor(keyring, frozen_clock(), tmp_path / "files")
    assert clean.exit_code == 0, clean.output
