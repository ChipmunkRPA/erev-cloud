"""Scenario catalogue authorization, filtering and tenant isolation."""

from uuid import uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import (
    DbContext,
    name_platform_tenant,
    platform_session,
    set_tenant_context,
    tenant_session,
)
from erev_api.db.tables import audit_event, scenario, tenant, tenant_snapshot
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert
from support.db import TestDatabase
from support.http import call
from support.principals import cookie_headers, enrolled, member, sign_in, workspace
from support.rows import insert_active_membership, insert_role_assignment, tenant_snapshot_values


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_scenario_catalogue(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    source = member(keyring, clock)
    denied = enrolled(app, clock, source)
    response = call(
        app, "GET", "/api/v1/scenarios", headers=cookie_headers(denied.token, key=False)
    )
    assert response.status_code == 403, response.text
    with tenant_session(
        DbContext(tenant_id=source.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        insert_role_assignment(
            session,
            tenant_id=source.tenant_id,
            membership_id=source.membership_id,
            role_code="controller",
        )
    allowed = workspace(app, source, sign_in(app, source.email), denied.secret)
    other = member(keyring, clock)
    for owner, name, status in (
        (source, "Base", "ACTIVE"),
        (source, "Old", "ARCHIVED"),
        (other, "Private", "ACTIVE"),
    ):
        target = uuid4()
        with platform_session(
            "provisioning", actor_user_id=None, request_id="scenario-list-fixture", keyring=keyring
        ) as session:
            session.execute(
                insert(tenant).values(
                    id=target,
                    code=f"fc-{target.hex[:12]}",
                    kind="sandbox",
                    status="ACTIVE",
                    display_name=name,
                    reporting_currency="USD",
                    source_tenant_id=owner.tenant_id,
                    audit_hmac_key_id=keyring.new_tenant_audit_key_id(target),
                    created_by_kind="SYSTEM",
                    updated_by_kind="SYSTEM",
                )
            )
            name_platform_tenant(session, target)
            set_tenant_context(
                session, DbContext(tenant_id=target, user_id=owner.user_id, entity_scope="*")
            )
            insert_active_membership(session, tenant_id=target, user_id=owner.user_id)
            set_tenant_context(
                session,
                DbContext(tenant_id=owner.tenant_id, user_id=owner.user_id, entity_scope="*"),
            )
            snapshot = tenant_snapshot_values(owner.tenant_id)
            session.execute(insert(tenant_snapshot).values(**snapshot))
            session.execute(
                insert(scenario).values(
                    tenant_id=owner.tenant_id,
                    id=uuid4(),
                    name=name,
                    status=status,
                    scenario_tenant_id=target,
                    tenant_snapshot_id=snapshot["id"],
                    base_known_at=clock.now(),
                    created_by=owner.user_id,
                    created_by_kind="USER",
                    updated_by_kind="SYSTEM",
                )
            )
    headers = cookie_headers(allowed.token, key=False)
    listed = call(app, "GET", "/api/v1/scenarios", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["name"] for row in listed.json()["items"]] == ["Base", "Old"]
    assert "tenant_id" not in listed.json()["items"][0]
    filtered = call(app, "GET", "/api/v1/scenarios", params={"status": "ARCHIVED"}, headers=headers)
    assert filtered.status_code == 200, filtered.text
    assert [row["name"] for row in filtered.json()["items"]] == ["Old"]


@pytest.mark.parametrize("late_creator", [False, True])
def test_create_scenario_runs_snapshot_job(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    late_creator: bool,
) -> None:
    from datetime import timedelta
    from uuid import UUID

    from erev_api.auth.permissions import effective_grants
    from erev_api.db.tables import job, role, role_assignment, tenant_membership
    from erev_api.domain.platform import snapshot_job
    from erev_api.enums import JobKind, MembershipStatus
    from erev_api.files.store import LocalFileStore
    from erev_api.jobs import registry
    from erev_api.jobs.context import JobRuntime
    from sqlalchemy import select, text
    from support.factories import stamp_test_release
    from support.principals import Member
    from support.rows import RowContext, assignment_row, membership_row
    from support.snapshots import confirm_retention

    source = member(keyring, clock)
    known_at = clock.now()
    if late_creator:
        newcomer = member(keyring, clock, name="late_creator")
        membership_values = membership_row(
            RowContext(source.tenant_id, newcomer.user_id), status=MembershipStatus.ACTIVE
        )
        membership_values["created_at"] = known_at + timedelta(minutes=1)
        with tenant_session(
            DbContext(tenant_id=source.tenant_id, user_id=None, entity_scope="*")
        ) as session:
            session.execute(insert(tenant_membership).values(**membership_values))
        source = Member(
            user_id=newcomer.user_id,
            email=newcomer.email,
            tenant_id=source.tenant_id,
            membership_id=membership_values["id"],
        )
    ctx = DbContext(tenant_id=source.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        confirm_retention(session, source.tenant_id, at=clock.now() - timedelta(days=1))
        role_id = session.execute(
            select(role.c.id).where(role.c.code == "revenue_accountant")
        ).scalar_one()
        assignment = assignment_row(
            source.tenant_id, membership_id=source.membership_id, role_id=role_id
        )
        if late_creator:
            assignment["created_at"] = known_at + timedelta(minutes=1)
        session.execute(insert(role_assignment).values(**assignment))
    actor = enrolled(app, clock, source)
    # scenario.use has no tenant.snapshot/fresh-step-up requirement.
    clock.advance(timedelta(minutes=6))
    headers = cookie_headers(actor.token, actor.csrf_token)
    body = {
        "name": "Forecast outlook",
        "purpose": "Quarter planning",
        "known_at": known_at.isoformat(),
    }
    created = call(app, "POST", "/api/v1/scenarios", json=body, headers=headers)
    assert created.status_code == 202, created.text
    repeated = call(app, "POST", "/api/v1/scenarios", json=body, headers=headers)
    assert repeated.status_code == 202 and repeated.json() == created.json(), repeated.text
    assert (
        call(
            app, "GET", "/api/v1/scenarios", headers=cookie_headers(actor.token, key=False)
        ).json()["items"]
        == []
    )
    job_id = UUID(created.json()["id"])
    stamp_test_release()
    with tenant_session(ctx) as session:
        row = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
        session.execute(
            text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
            {"id": row["procrastinate_job_id"]},
        )
    old = registry.HANDLERS.get(JobKind.TENANT_SNAPSHOT)
    registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = registry.HandlerSpec(
        handler=snapshot_job.tenant_snapshot_export,
        retry=snapshot_job.SNAPSHOT_RETRY,
        on_failure=snapshot_job.snapshot_failed,
    )
    try:
        registry.run_job(
            job_id,
            source.tenant_id,
            attempt=1,
            runtime=JobRuntime(
                clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root)
            ),
        )
    finally:
        if old is None:
            registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)
        else:
            registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = old
    with tenant_session(ctx) as session:
        finished = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
        assert finished["state"] == "SUCCEEDED", str(finished["problem"])
        assert finished["result"]["href"] == "/api/v1/scenarios"
        assert (
            session.execute(
                select(audit_event.c.id).where(
                    audit_event.c.object_id == UUID(created.json()["scenario_id"]),
                    audit_event.c.action == "scenario.create",
                )
            ).scalar_one()
            is not None
        )
    listed = call(app, "GET", "/api/v1/scenarios", headers=cookie_headers(actor.token, key=False))
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 1
    registered = listed.json()["items"][0]
    assert registered["id"] == created.json()["scenario_id"]
    assert registered["tenant_snapshot_id"] == created.json()["tenant_snapshot_id"]
    assert registered["purpose"] == "Quarter planning"
    target_id = UUID(registered["scenario_tenant_id"])
    with tenant_session(DbContext(tenant_id=target_id, user_id=None, entity_scope="*")) as session:
        assert (
            session.execute(
                select(audit_event.c.id).where(
                    audit_event.c.object_id == UUID(created.json()["scenario_id"]),
                    audit_event.c.action == "scenario.create",
                )
            ).scalar_one()
            is not None
        )
    if late_creator:
        target_id = UUID(registered["scenario_tenant_id"])
        with tenant_session(
            DbContext(tenant_id=target_id, user_id=None, entity_scope="*")
        ) as session:
            membership_id = session.execute(
                select(tenant_membership.c.id).where(tenant_membership.c.user_id == source.user_id)
            ).scalar_one()
            grants = effective_grants(session, membership_id, at=clock.now())
            assert "scenario.use" in grants.permissions
            assert "contract.create" not in grants.permissions
            assert "viewer" in grants.roles

    # The archived sandbox remains readable, including for an already signed-in session.
    with tenant_session(DbContext(tenant_id=target_id, user_id=None, entity_scope="*")) as session:
        membership_id = session.execute(
            select(tenant_membership.c.id).where(tenant_membership.c.user_id == source.user_id)
        ).scalar_one()
    target_member = Member(
        user_id=source.user_id, email=source.email, tenant_id=target_id, membership_id=membership_id
    )
    sandbox_actor = workspace(app, target_member, sign_in(app, source.email), actor.secret)
    from support.forecast_inputs import exercise_input_sets

    exercise_input_sets(app, actor, sandbox_actor, target_id)
    write_headers = cookie_headers(sandbox_actor.token, sandbox_actor.csrf_token)
    view_body = {"screen_code": "SF-02", "name": "Before archive", "config": {}}
    wrote = call(app, "POST", "/api/v1/saved-views", json=view_body, headers=write_headers)
    assert wrote.status_code == 201, wrote.text
    from erev_api.db import transitions
    from support.principals import colleague
    from support.rows import job_row

    archive_actor = actor
    if not late_creator:
        colleague_member = colleague(source.tenant_id, "other_planner")
        with tenant_session(ctx) as session:
            insert_role_assignment(
                session,
                tenant_id=source.tenant_id,
                membership_id=colleague_member.membership_id,
                role_code="revenue_accountant",
            )
        other_actor = enrolled(app, clock, colleague_member)
        denied_headers = cookie_headers(other_actor.token, other_actor.csrf_token)
        denied_headers["If-Match"] = f'"r{registered["row_version"]}"'
        denied = call(
            app, "POST", f"/api/v1/scenarios/{registered['id']}/archive", headers=denied_headers
        )
        assert denied.status_code == 403, denied.text
        with tenant_session(ctx) as session:
            insert_role_assignment(
                session,
                tenant_id=source.tenant_id,
                membership_id=colleague_member.membership_id,
                role_code="controller",
            )
        archive_actor = workspace(
            app, colleague_member, sign_in(app, colleague_member.email), other_actor.secret
        )
    target_context = DbContext(tenant_id=target_id, user_id=None, entity_scope="*")
    with tenant_session(target_context) as session:
        pending = job_row(RowContext(target_id, source.user_id), session)
        session.execute(insert(job).values(**pending))
    busy_headers = cookie_headers(archive_actor.token, archive_actor.csrf_token)
    busy_headers["If-Match"] = f'"r{registered["row_version"]}"'
    busy = call(app, "POST", f"/api/v1/scenarios/{registered['id']}/archive", headers=busy_headers)
    assert busy.status_code == 409, busy.text
    with tenant_session(target_context) as session:
        transitions.apply(
            session,
            "job",
            pending["id"],
            to_status="CANCELLED",
            expected_status="QUEUED",
            set_values={"finished_at": clock.now()},
        )
    archive_headers = cookie_headers(archive_actor.token, archive_actor.csrf_token)
    archive_headers["If-Match"] = f'"r{registered["row_version"]}"'
    archived = call(
        app, "POST", f"/api/v1/scenarios/{registered['id']}/archive", headers=archive_headers
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "ARCHIVED"
    replay = call(
        app, "POST", f"/api/v1/scenarios/{registered['id']}/archive", headers=archive_headers
    )
    assert replay.status_code == 200 and replay.json() == archived.json(), replay.text
    refused = call(app, "POST", "/api/v1/saved-views", json=view_body, headers=write_headers)
    assert refused.status_code == 409, refused.text
    assert refused.json()["errors"][0]["rule_id"] == "SCENARIO_ARCHIVED"
    readable = call(
        app, "GET", "/api/v1/saved-views", headers=cookie_headers(sandbox_actor.token, key=False)
    )
    assert readable.status_code == 200, readable.text
    assert readable.json()["items"][0]["name"] == "Before archive"
    # A delayed business worker is refused, but job failure settlement can still commit.
    from collections.abc import Mapping
    from typing import Any

    from erev_api.auth.principal import system_principal
    from erev_api.jobs.context import JobContext, system_unit_of_work

    runtime = JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))
    with system_unit_of_work(
        runtime, system_principal(target_id), request_id="test-late-job"
    ) as uow:
        delayed = uow.defer(JobKind.AUDIT_CHAIN_VERIFY, {})
        delayed_id = UUID(str(delayed["id"]))
        uow.commit()
    with tenant_session(target_context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == delayed_id)
        ).scalar_one()
        session.execute(
            text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"), {"id": task_id}
        )

    def attempted_write(jc: JobContext, params: Mapping[str, Any]) -> registry.JobOutcome:
        with jc.unit_of_work() as uow:
            uow.audit(
                action="test.archived_write",
                object_type="scenario",
                object_id=UUID(registered["id"]),
            )
            uow.commit()
        return registry.JobOutcome(state="SUCCEEDED", result={})

    prior = registry.HANDLERS.get(JobKind.AUDIT_CHAIN_VERIFY)
    registry.HANDLERS[JobKind.AUDIT_CHAIN_VERIFY] = registry.HandlerSpec(
        handler=attempted_write, retry=registry.RetryPolicy(max_attempts=1)
    )
    try:
        registry.run_job(delayed_id, target_id, attempt=1, runtime=runtime)
    finally:
        if prior is None:
            registry.HANDLERS.pop(JobKind.AUDIT_CHAIN_VERIFY, None)
        else:
            registry.HANDLERS[JobKind.AUDIT_CHAIN_VERIFY] = prior
    with tenant_session(target_context) as session:
        settled = session.execute(select(job).where(job.c.id == delayed_id)).mappings().one()
        assert settled["state"] == "FAILED", str(settled["problem"])
        assert settled["problem"]["errors"][0]["rule_id"] == "SCENARIO_ARCHIVED"
        assert (
            session.execute(
                select(audit_event.c.id).where(audit_event.c.action == "test.archived_write")
            ).first()
            is None
        )
        assert (
            session.execute(
                select(audit_event.c.id).where(
                    audit_event.c.action == "scenario.archive",
                    audit_event.c.object_id == UUID(registered["id"]),
                )
            ).scalar_one()
            is not None
        )
