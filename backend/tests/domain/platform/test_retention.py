"""Retention sweep (04 T-PLT-08, T-PLT-16, T-PLT-28, T-PLT-42 IM-E; 05 SCH-07, SCH-08; dev-guide
DG-KRN-JOB-07; BUILD_SPEC PLF-22, PLF-25).

The global tables are shared by every test of the session, so the counts of the global deletes are
asserted as lower bounds; the rows each test inserts are asserted exactly.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    api_token,
    idempotency_record,
    job,
    password_reset_token,
    user_session,
)
from erev_api.domain.platform import retention
from erev_api.enums import IdentityProviderKind, JobKind, PrincipalKind, SessionEndReason
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_api_client, insert_app_user

_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring))


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _idempotency_record(tenant_id: UUID, *, created_at: datetime) -> str:
    key = f"retention-{secrets.token_hex(8)}"
    with tenant_session(_db(tenant_id)) as session:
        session.execute(
            insert(idempotency_record).values(
                tenant_id=tenant_id,
                principal_id=new_id(),
                idempotency_key=key,
                principal_kind=PrincipalKind.USER.value,
                method="POST",
                path="/api/v1/probes",
                request_sha256="0" * 64,
                created_at=created_at,
                expires_at=created_at + timedelta(days=7),
            )
        )
    return key


def _api_token(tenant_id: UUID, *, expires_at: datetime) -> UUID:
    token_id = new_id()
    with tenant_session(_db(tenant_id)) as session:
        client_id = insert_api_client(session, tenant_id=tenant_id)
        session.execute(
            insert(api_token).values(
                tenant_id=tenant_id,
                id=token_id,
                api_client_id=client_id,
                token_sha256=secrets.token_hex(32),
                scopes=["contract.read"],
                issued_at=expires_at - timedelta(minutes=60),
                expires_at=expires_at,
            )
        )
    return token_id


def _user_session(db: Session, user_id: UUID, *, ended_at: datetime | None) -> UUID:
    session_id = new_id()
    created_at = (ended_at or FROZEN_AT) - timedelta(hours=1)
    db.execute(
        insert(user_session).values(
            id=session_id,
            user_id=user_id,
            token_sha256=secrets.token_hex(32),
            csrf_token_sha256=secrets.token_hex(32),
            auth_method=IdentityProviderKind.PASSWORD.value,
            created_at=created_at,
            last_seen_at=created_at,
            idle_expires_at=created_at + timedelta(minutes=30),
            absolute_expires_at=created_at + timedelta(hours=12),
            ended_at=ended_at,
            end_reason=None if ended_at is None else SessionEndReason.LOGOUT.value,
            expires_at=None if ended_at is None else ended_at + timedelta(days=30),
        )
    )
    return session_id


def _reset_token(db: Session, user_id: UUID, *, expires_at: datetime) -> UUID:
    token_id = new_id()
    created_at = expires_at - timedelta(days=30, minutes=60)
    db.execute(
        insert(password_reset_token).values(
            id=token_id,
            user_id=user_id,
            token_sha256=secrets.token_hex(32),
            created_at=created_at,
            token_expires_at=created_at + timedelta(minutes=60),
            request_id="tests-retention",
            expires_at=expires_at,
        )
    )
    return token_id


def _job(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(select(job).where(job.c.id == job_id)).mappings().one()


def _sweep(tenant_id: UUID, runtime: JobRuntime) -> UUID:
    """A SYSTEM sweep of the tenant, fetched and run as the worker would."""
    now = runtime.clock.now()
    with tenant_session(_db(tenant_id)) as session:
        row = registry.insert_job(
            session,
            JobKind.RETENTION_SWEEP,
            {},
            tenant_id=tenant_id,
            now=now,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
        )
        procrastinate_job_id = registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=now
        )
        session.execute(_FETCHED, {"id": procrastinate_job_id})
    job_id = UUID(str(row["id"]))
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    return job_id


def test_retention_sweep_deletes_expired_rows(tenant_id: UUID, runtime: JobRuntime) -> None:
    now = runtime.clock.now()
    expired_key = _idempotency_record(tenant_id, created_at=now - timedelta(days=7, seconds=1))
    young_key = _idempotency_record(
        tenant_id, created_at=now - timedelta(days=7) + timedelta(seconds=1)
    )
    expired_token = _api_token(tenant_id, expires_at=now - timedelta(days=7, seconds=1))
    young_token = _api_token(tenant_id, expires_at=now - timedelta(days=7) + timedelta(seconds=1))
    with identity_session(request_id="tests-retention") as db:
        user_id = insert_app_user(db)
        _user_session(db, user_id, ended_at=now - timedelta(days=30, seconds=1))
        young_session = _user_session(
            db, user_id, ended_at=now - timedelta(days=30) + timedelta(seconds=1)
        )
        open_session = _user_session(db, user_id, ended_at=None)
        _reset_token(db, user_id, expires_at=now - timedelta(seconds=1))
        live_token = _reset_token(db, user_id, expires_at=now + timedelta(seconds=1))

    job_id = _sweep(tenant_id, runtime)

    swept = _job(tenant_id, job_id)
    assert (swept["state"], swept["result"]["href"]) == ("SUCCEEDED", f"/api/v1/jobs/{job_id}")
    counts = swept["result"]["counts"]
    assert set(counts) == {
        "idempotency_record",
        "api_token",
        "user_session",
        "password_reset_token",
    }
    assert (counts["idempotency_record"], counts["api_token"]) == (1, 1)
    assert counts["user_session"] >= 1 and counts["password_reset_token"] >= 1

    with tenant_session(_db(tenant_id)) as session:
        keys = session.scalars(select(idempotency_record.c.idempotency_key)).all()
        api_tokens = session.scalars(select(api_token.c.id)).all()
    assert expired_key not in keys and young_key in keys
    assert expired_token not in api_tokens and young_token in api_tokens
    with identity_session(request_id="tests-retention") as db:
        sessions = db.scalars(select(user_session.c.id).where(user_session.c.user_id == user_id))
        assert sorted(sessions) == sorted([young_session, open_session])
        tokens = db.scalars(
            select(password_reset_token.c.id).where(password_reset_token.c.user_id == user_id)
        )
        assert list(tokens) == [live_token]


def test_sch_07_idempotency_purge_defers_one_sweep_per_active_tenant(tenant_id: UUID) -> None:
    def sweeps() -> list[tuple[Any, ...]]:
        with tenant_session(_db(tenant_id)) as session:
            rows = session.execute(
                select(job.c.state, job.c.created_by_kind, job.c.procrastinate_job_id).where(
                    job.c.kind == JobKind.RETENTION_SWEEP.value
                )
            ).all()
        return [
            (row.state, row.created_by_kind, row.procrastinate_job_id is not None) for row in rows
        ]

    assert retention.defer_sweeps(frozen_clock()) >= 1
    assert sweeps() == [("QUEUED", "SYSTEM", True)]
    # A sweep still QUEUED is not deferred again.
    retention.defer_sweeps(frozen_clock())
    assert sweeps() == [("QUEUED", "SYSTEM", True)]


def test_sch_08_session_purge_deletes_global_rows(committed_db: TestDatabase) -> None:
    now = FROZEN_AT
    with identity_session(request_id="tests-retention") as db:
        user_id = insert_app_user(db)
        _user_session(db, user_id, ended_at=now - timedelta(days=31))
        _reset_token(db, user_id, expires_at=now - timedelta(days=1))

    counts = retention.purge_global(frozen_clock(now))

    assert set(counts) == {"user_session", "password_reset_token"}
    assert counts["user_session"] >= 1 and counts["password_reset_token"] >= 1
    with identity_session(request_id="tests-retention") as db:
        assert (
            db.scalars(select(user_session.c.id).where(user_session.c.user_id == user_id)).all()
            == []
        )
        assert (
            db.scalars(
                select(password_reset_token.c.id).where(password_reset_token.c.user_id == user_id)
            ).all()
            == []
        )
