"""Audit chain verification (04 T-PLT-23; 05 SCH-01, SCH-02, SAR-31; dev-guide DG-KRN-AUD-07,
DG-KRN-JOB-07; PRD NTF-09; 03 REQ-PLT-020, CTL-039; BUILD_SPEC PLF-23, BS1-D-13).

The tests play the worker as ``test_job_monitoring.py`` does: they start a SYSTEM verification job,
mark its Procrastinate task fetched and call ``run_job``.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from erev_api.audit.verify import record_tenant_verification
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    audit_chain_head,
    audit_chain_verification,
    audit_event,
    control_execution,
    file_object,
    job,
    notification,
    outbox_message,
    security_event,
)
from erev_api.domain.platform import audit_jobs
from erev_api.enums import ControlResult, JobKind, NotificationKind, PrincipalKind, TenantKind
from erev_api.events import notifications
from erev_api.files.store import LocalFileStore, open_file
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import Engine, func, select, text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import stamp_test_release, tenant_factory, tenant_id_of
from support.principals import colleague, member
from support.rows import insert_audited_tenant, insert_role_assignment, tamper_audit_event

_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
VERIFICATIONS_HREF = "/api/v1/audit-events/verifications"


@pytest.fixture
def runtime(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> JobRuntime:
    # 05 REL-03 (rev 1.15; D-98 60): the verification (AUDIT_CHAIN_VERIFY, SCH-02) runs in THIS
    # process and its CTL-039 evidence producer stamps the process release — a process that never
    # stamped fails closed (release-mismatch) whatever rows the table holds, so the job runtime
    # stamps through the shared support exactly as the world factories do (P5-DOCTOR-R1).
    stamp_test_release()
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _verify(tenant_id: UUID, runtime: JobRuntime, *, concurrency: int | None = None) -> UUID:
    """A SYSTEM SCHEDULED verification of the tenant, fetched and run as the worker would."""
    now = runtime.clock.now()
    with tenant_session(_db(tenant_id)) as session:
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
    job_id = UUID(str(row["id"]))
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime, concurrency=concurrency)
    return job_id


def _verifications(tenant_id: UUID) -> list[Mapping[str, Any]]:
    with tenant_session(_db(tenant_id)) as session:
        return list(session.execute(select(audit_chain_verification)).mappings())


def _job(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(select(job).where(job.c.id == job_id)).mappings().one()


def _last_event(tenant_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return (
            session.execute(select(audit_event).order_by(audit_event.c.chain_seq.desc()).limit(1))
            .mappings()
            .one()
        )


def _verification_fact(
    tenant_id: UUID, job_id: UUID, *, state: str = "SUCCEEDED"
) -> Mapping[str, Any]:
    """The AUD-FACT of the verification the job recorded, after checking what follows it: the
    chain's last event is the registry's ``job.finish`` of that job with its terminal ``state``,
    written as SYSTEM in the transaction that records it (04 T-PLT-27 rev 1.106; supervisor ruling
    R-50 (a)). Until that ruling the verification's fact was the last event of the chain."""
    with tenant_session(_db(tenant_id)) as session:
        finish, fact = (
            session.execute(select(audit_event).order_by(audit_event.c.chain_seq.desc()).limit(2))
            .mappings()
            .all()
        )
    assert (finish["action"], finish["object_type"], finish["object_id"]) == (
        "job.finish",
        "job",
        job_id,
    )
    assert (finish["actor_kind"], finish["request_id"]) == ("SYSTEM", f"job-{job_id}")
    assert finish["after"] == {"kind": "AUDIT_CHAIN_VERIFY", "state": state, "problem": None}
    assert finish["chain_seq"] == fact["chain_seq"] + 1
    return fact


@pytest.mark.control("CTL-039")
def test_ctl_039_failure_notifies_and_records(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    lena = member(keyring, clock)
    tenant_id = lena.tenant_id
    carla = colleague(tenant_id, "carla")
    victor = colleague(tenant_id, "victor")
    with tenant_session(_db(tenant_id)) as session:
        for someone, role_code in (
            (lena, "tenant_admin"),
            (carla, "controller"),
            (victor, "viewer"),
        ):
            insert_role_assignment(
                session,
                tenant_id=tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
            )
    tamper_audit_event(committed_db.owner_engine, tenant_id=tenant_id, chain_seq=2)

    job_id = _verify(tenant_id, runtime)

    (row,) = _verifications(tenant_id)
    assert (row["result"], row["first_failure_seq"], row["trigger"], row["job_id"]) == (
        "FAIL",
        2,
        "SCHEDULED",
        job_id,
    )
    assert (row["from_chain_seq"], row["to_chain_seq"], row["events_checked"]) == (1, 2, 2)
    assert row["failure_detail"] == {"reason": "hmac does not match the event content"}
    assert (row["digest_file_id"], row["created_by_kind"]) == (None, "SYSTEM")
    # BS1-D-13: the exception item fails closed, so the job reports the failure as an exception.
    stored = _job(tenant_id, job_id)
    assert (stored["state"], stored["result"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        {
            "href": VERIFICATIONS_HREF,
            "verification_id": str(row["id"]),
            "counts": {"events_checked": 2, "failures": 1},
        },
    )

    with tenant_session(_db(tenant_id)) as session:
        received = session.execute(
            select(
                notification.c.recipient_membership_id,
                notification.c.title,
                notification.c.body,
                notification.c.link_path,
                notification.c.subject_type,
                notification.c.subject_id,
            ).where(notification.c.kind == "CHAIN_VERIFICATION_FAILED")
        ).all()
        emails = session.scalars(
            select(outbox_message.c.payload).where(
                outbox_message.c.aggregate_type == "notification"
            )
        ).all()
    # Tenant Admins and Controllers, never the viewer (NTF-09).
    assert sorted(item.recipient_membership_id for item in received) == sorted(
        [lena.membership_id, carla.membership_id]
    )
    assert {tuple(item)[1:] for item in received} == {
        (
            "Audit chain verification failed",
            "Verification stopped at event 2. "
            "Open the verification details and follow the runbook.",
            f"/reports/audit-log/verifications/{row['id']}",
            "audit_chain_verification",
            row["id"],
        )
    }
    # NTF-R2: the notification is always emailed too.
    assert sorted(payload["to"] for payload in emails) == sorted([lena.email, carla.email])
    assert {payload["subject"] for payload in emails} == {"Audit chain verification failed"}

    # A verification that records FAIL ends its job SUCCEEDED_WITH_EXCEPTIONS.
    audited = _verification_fact(tenant_id, job_id, state="SUCCEEDED_WITH_EXCEPTIONS")
    assert (audited["action"], audited["object_type"], audited["detail"]) == (
        "audit_chain_verification.create",
        "audit_chain_verification",
        {
            "ids": [str(row["id"])],
            "trigger": "SCHEDULED",
            "result": "FAIL",
            "first_failure_seq": 2,
            "digest_file_id": None,
        },
    )


def _record(
    tenant_id: UUID, clock: FrozenClock, keyring: KeyRing, settings: Settings
) -> Mapping[str, Any]:
    """An ON_DEMAND verification recorded by the system principal and committed."""
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id=f"tests-ctl-039-{secrets.token_hex(4)}",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        row = record_tenant_verification(uow, trigger="ON_DEMAND", job_id=None)
        uow.commit()
    return row


def _data_fix(
    owner: Engine, tenant_id: UUID, *, delete: Sequence[int], head_seq: int | None
) -> None:
    """As erev_owner with a data-fix ticket: delete audit events and, when ``head_seq`` is given,
    move the head to that event with the guard disabled (runbook "Audit log and hash chain")."""
    of_tenant = {"tenant_id": tenant_id}
    with owner.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE erev.audit_event NO FORCE ROW LEVEL SECURITY")
        connection.execute(text("SELECT set_config('app.data_fix_ticket', 'DF-WEB-3A', true)"))
        deleted = connection.execute(
            text(
                "DELETE FROM erev.audit_event "
                "WHERE tenant_id = :tenant_id AND chain_seq = ANY(:seqs)"
            ),
            {**of_tenant, "seqs": list(delete)},
        ).rowcount
        assert deleted == len(delete)
        if head_seq is not None:
            head = "erev.audit_chain_head"
            connection.exec_driver_sql(f"ALTER TABLE {head} NO FORCE ROW LEVEL SECURITY")
            connection.exec_driver_sql(
                f"ALTER TABLE {head} DISABLE TRIGGER tg_audit_chain_head__guard"
            )
            moved = connection.execute(
                text(
                    "UPDATE erev.audit_chain_head h "
                    "SET last_chain_seq = e.chain_seq, last_hmac = e.hmac "
                    "FROM erev.audit_event e "
                    "WHERE h.tenant_id = :tenant_id AND e.tenant_id = h.tenant_id "
                    "AND e.chain_seq = :seq"
                ),
                {**of_tenant, "seq": head_seq},
            ).rowcount
            assert moved == 1
            connection.exec_driver_sql(
                f"ALTER TABLE {head} ENABLE TRIGGER tg_audit_chain_head__guard"
            )
            connection.exec_driver_sql(f"ALTER TABLE {head} FORCE ROW LEVEL SECURITY")
        connection.exec_driver_sql("ALTER TABLE erev.audit_event FORCE ROW LEVEL SECURITY")


@pytest.mark.control("CTL-039")
def test_ctl_039_truncated_chain_fails(
    committed_db: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notified: list[NotificationKind] = []
    original = notifications.notify

    def recording(uow: UnitOfWork, **kwargs: Any) -> Any:
        notified.append(kwargs["kind"])
        return original(uow, **kwargs)

    monkeypatch.setattr(notifications, "notify", recording)

    # (a) Tail truncation: the head still names event 5.
    truncated = insert_audited_tenant(keyring, events=5, at=FROZEN_AT)
    _data_fix(committed_db.owner_engine, truncated, delete=[4, 5], head_seq=None)
    with tenant_session(_db(truncated)) as session:
        assert session.execute(select(audit_chain_head.c.last_chain_seq)).scalar_one() == 5
    row = _record(truncated, clock, keyring, app_settings)
    assert (row["result"], row["to_chain_seq"], row["first_failure_seq"]) == ("FAIL", 3, 4)
    assert row["failure_detail"] == {"reason": "the chain ends before the head"}
    assert row["digest_file_id"] is None
    assert notified == [NotificationKind.CHAIN_VERIFICATION_FAILED]

    # (b) Truncation with a rewound head: only the earlier PASS digest reveals it.
    rewound = insert_audited_tenant(keyring, events=5, at=FROZEN_AT)
    first = _record(rewound, clock, keyring, app_settings)
    assert (first["result"], first["to_chain_seq"]) == ("PASS", 5)
    assert _last_event(rewound)["chain_seq"] == 6
    _data_fix(committed_db.owner_engine, rewound, delete=[5, 6], head_seq=4)
    with tenant_session(_db(rewound)) as session:
        assert session.execute(select(audit_chain_head.c.last_chain_seq)).scalar_one() == 4
    second = _record(rewound, clock, keyring, app_settings)
    assert (second["result"], second["first_failure_seq"]) == ("FAIL", 5)
    assert second["failure_detail"] == {"reason": "a verified event is missing or changed"}
    assert second["digest_file_id"] is None
    assert notified == [NotificationKind.CHAIN_VERIFICATION_FAILED] * 2


def test_req_plt_020_pass_writes_digest(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, runtime: JobRuntime
) -> None:
    tenant_id = insert_audited_tenant(keyring, events=5, at=FROZEN_AT)
    head_hmac = _last_event(tenant_id)["hmac"]

    # The bare tenant publishes no registry values, so the worker is given its slot count.
    job_id = _verify(tenant_id, runtime, concurrency=1)

    (row,) = _verifications(tenant_id)
    assert (
        row["result"],
        row["trigger"],
        row["from_chain_seq"],
        row["to_chain_seq"],
        row["events_checked"],
        row["first_failure_seq"],
        row["failure_detail"],
    ) == ("PASS", "SCHEDULED", 1, 5, 5, None, None)
    assert row["digest_last_hmac"] == head_hmac
    assert (row["job_id"], row["started_at"], row["finished_at"]) == (job_id, FROZEN_AT, FROZEN_AT)

    with tenant_session(_db(tenant_id)) as session:
        stored_file, stream = open_file(
            session,
            row["digest_file_id"],
            files=LocalFileStore(app_settings.file_root),
            keyring=keyring,
        )
        with stream:
            document = json.loads(stream.read())
    assert (
        stored_file["purpose"],
        stored_file["media_type"],
        stored_file["original_filename"],
    ) == ("AUDIT_DIGEST", "application/json", "chain_digest.json")
    assert document == {
        "tenant_id": str(tenant_id),
        "last_chain_seq": 5,
        "last_hmac": head_hmac,
        "hmac_key_id": f"audit-hmac:{tenant_id}:1",
        "events_checked": 5,
        "verified_at": "2026-09-12T12:00:00Z",
    }

    stored = _job(tenant_id, job_id)
    assert (stored["state"], stored["result"]) == (
        "SUCCEEDED",
        {
            "href": VERIFICATIONS_HREF,
            "verification_id": str(row["id"]),
            "counts": {"events_checked": 5, "failures": 0},
        },
    )
    audited = _verification_fact(tenant_id, job_id)
    assert (audited["chain_seq"], audited["action"], audited["detail"]["ids"]) == (
        6,
        "audit_chain_verification.create",
        [str(row["id"])],
    )
    assert audited["detail"]["digest_file_id"] == str(row["digest_file_id"])
    with tenant_session(_db(tenant_id)) as session:
        assert session.execute(select(notification.c.id)).all() == []


def test_sch_01_fan_out_per_tenant(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    request_id = f"tests-sch-01-{secrets.token_hex(4)}"

    def verifications() -> list[tuple[Any, ...]]:
        with tenant_session(_db(tenant_id)) as session:
            rows = session.execute(
                select(
                    job.c.state, job.c.created_by_kind, job.c.params, job.c.procrastinate_job_id
                ).where(job.c.kind == JobKind.AUDIT_CHAIN_VERIFY.value)
            ).all()
        return [
            (item.state, item.created_by_kind, item.params, item.procrastinate_job_id is not None)
            for item in rows
        ]

    assert audit_jobs.defer_verifications(frozen_clock(), request_id=request_id) >= 1
    assert verifications() == [("QUEUED", "SYSTEM", {"trigger": "SCHEDULED"}, True)]
    # A verification still QUEUED is not deferred again.
    audit_jobs.defer_verifications(frozen_clock(), request_id=request_id)
    assert verifications() == [("QUEUED", "SYSTEM", {"trigger": "SCHEDULED"}, True)]

    with identity_session(request_id="tests-sch-01") as session:
        events = session.execute(
            select(
                security_event.c.kind, security_event.c.tenant_id, security_event.c.detail
            ).where(security_event.c.request_id == request_id)
        ).all()
    assert [tuple(event) for event in events] == [
        ("PLATFORM_SCOPE_USED", None, {"scope": "tenant_directory"})
    ] * 2


def test_sch_02_security_chain_verification(
    committed_db: TestDatabase, runtime: JobRuntime
) -> None:
    # A tenant directory read records one security event, so the chain is not empty.
    with platform_session("tenant_directory", actor_user_id=None, request_id="tests-sch-02"):
        pass

    result = audit_jobs.security_chain_verify(runtime)

    with identity_session(request_id="tests-sch-02") as session:
        last = session.execute(
            select(security_event.c.chain_seq, security_event.c.hmac)
            .order_by(security_event.c.chain_seq.desc())
            .limit(1)
        ).one()
    assert (
        result.scope,
        result.result,
        result.first_failure_seq,
        result.to_chain_seq,
        result.digest_last_hmac,
    ) == ("security_event", ControlResult.PASS, None, last.chain_seq, last.hmac)
    assert result.events_checked >= 1


@pytest.mark.parametrize("conflict", [None, "duplicate", "trigger"])
@pytest.mark.parametrize("damage_chain", [False, True])
def test_verification_retry_reuses_committed_result(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
    damage_chain: bool,
    conflict: str | None,
) -> None:
    """Crash after verification commit; reuse one result, refuse ambiguous or mismatched rows."""
    lena = member(keyring, clock)
    tenant_id = lena.tenant_id
    with tenant_session(_db(tenant_id)) as session:
        insert_role_assignment(
            session, tenant_id=tenant_id, membership_id=lena.membership_id, role_code="tenant_admin"
        )
    if damage_chain:
        tamper_audit_event(committed_db.owner_engine, tenant_id=tenant_id, chain_seq=2)
    calls = 0

    def interrupted(jc: JobContext, params: Mapping[str, Any]) -> registry.JobOutcome:
        nonlocal calls
        first_params = {"trigger": "ON_DEMAND"} if calls == 0 and conflict == "trigger" else params
        outcome = audit_jobs.audit_chain_verify(jc, first_params)
        calls += 1
        if calls == 1:
            if conflict == "duplicate":
                with jc.unit_of_work() as uow:
                    record_tenant_verification(uow, trigger="SCHEDULED", job_id=jc.job_id)
                    uow.commit()
            raise RuntimeError("lost audit completion acknowledgement")
        return outcome

    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.AUDIT_CHAIN_VERIFY,
        replace(registry.HANDLERS[JobKind.AUDIT_CHAIN_VERIFY], handler=interrupted),
    )
    job_id = _verify(tenant_id, runtime)
    assert _job(tenant_id, job_id)["state"] == "QUEUED"
    originals = _verifications(tenant_id)
    assert len(originals) == (2 if conflict == "duplicate" else 1)
    original = originals[0]

    def effects() -> tuple[int | None, ...]:
        with tenant_session(_db(tenant_id)) as session:
            return tuple(
                session.scalar(select(func.count()).select_from(table))
                for table in (
                    audit_chain_verification,
                    file_object,
                    control_execution,
                    notification,
                    outbox_message,
                )
            )

    before = effects()

    # No digest exporter, verifier, or alert sender may run on the retry.
    def unexpected(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a committed verification must not be repeated")

    monkeypatch.setattr(audit_jobs.verify, "record_tenant_verification", unexpected)
    with tenant_session(_db(tenant_id)) as session:
        task_id = session.scalar(select(job.c.procrastinate_job_id).where(job.c.id == job_id))
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, tenant_id, attempt=2, runtime=runtime)
    if conflict:
        assert _job(tenant_id, job_id)["state"] == "QUEUED"
        assert effects() == before
        with tenant_session(_db(tenant_id)) as session:
            task_id = session.scalar(select(job.c.procrastinate_job_id).where(job.c.id == job_id))
            session.execute(_FETCHED, {"id": task_id})
        registry.run_job(job_id, tenant_id, attempt=3, runtime=runtime)
    finished = _job(tenant_id, job_id)
    if conflict:
        assert finished["state"] == "FAILED", finished
        assert "inconsistent retained results" in finished["problem"]["detail"]
        assert calls == 1
    else:
        assert finished["state"] == ("SUCCEEDED_WITH_EXCEPTIONS" if damage_chain else "SUCCEEDED")
        assert finished["result"]["verification_id"] == str(original["id"])
        assert finished["result"]["counts"]["failures"] == int(damage_chain)
        assert calls == 2
    assert effects() == before
    assert _verifications(tenant_id) == originals
