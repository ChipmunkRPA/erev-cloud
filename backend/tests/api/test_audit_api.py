"""API-R-10 audit (04 §15.3 API-R-10, §16.14 "Audit events" rev 1.154, API-C-12, T-PLT-19,
T-PLT-23; SCREENS_B §6.3, §6.4; BUILD_SPEC PLF-23; item AUD-API-GAPS-1).

Maya reads the audit log as an auditor holding ``audit.read``; Victor is a viewer without it. The
events come from units of work at chosen instants, and the verification job runs as the worker
would: the test marks its Procrastinate task fetched and calls ``run_job``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.api.lists import TOTAL_COUNT_HEADER
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls import release
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import api_client, app_user, audit_event, job, role, tenant_membership
from erev_api.domain.platform import audit_jobs, audit_log
from erev_api.enums import AuditOutcome, JobKind, PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text, update
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import maya_principal, stamp_test_release
from support.http import HttpResponse, call
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import Actor, Member, colleague, cookie_headers, member, sign_in, workspace
from support.rows import api_client_values, insert_role_assignment

AUDIT = "/api/v1/audit-events"
VERIFICATIONS = f"{AUDIT}/verifications"
VERIFY = f"{AUDIT}/verify"
PROBLEM_BASE = "https://erev.dev/problems/"
REQUEST_ID = "X-Request-Id"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
EVENT_KEYS = {
    "id",
    "chain_seq",
    "occurred_at",
    "actor",
    "actor_membership_id",
    "actor_roles",
    "auth_method",
    "mfa_verified",
    "on_behalf_of",
    "api_client_id",
    "support_grant_id",
    "source_ip",
    "request_id",
    "action",
    "object_type",
    "object_id",
    "object_label",
    "object_version",
    "before",
    "after",
    "diff",
    "reason_code",
    "comment",
    "approval_request_id",
    "outcome",
    "detail",
    "prev_hmac",
    "hmac",
    "hmac_key_id",
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def runtime(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> JobRuntime:
    # 05 REL-03 (rev 1.15; D-98 60): the on-demand verification (AUDIT_CHAIN_VERIFY) runs in THIS
    # process and its CTL-039 evidence producer stamps the process release — a process that never
    # stamped fails closed (release-mismatch) whatever rows the table holds, so the job runtime
    # stamps through the shared support exactly as the world factories do (P5-DOCTOR-R1).
    stamp_test_release()
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _people(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> tuple[Member, Actor, Actor]:
    """Maya as an auditor and Victor as a viewer, both signed in to Maya's workspace."""
    maya_member = member(keyring, clock)
    victor_member = colleague(maya_member.tenant_id, "victor")
    with tenant_session(_db(maya_member.tenant_id)) as session:
        for someone, role_code in ((maya_member, "auditor"), (victor_member, "viewer")):
            insert_role_assignment(
                session,
                tenant_id=someone.tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
            )
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    victor = workspace(app, victor_member, sign_in(app, victor_member.email))
    return maya_member, maya, victor


def _record(
    tenant_id: UUID,
    keyring: KeyRing,
    files: LocalFileStore,
    *,
    at: datetime,
    action: str,
    principal: Principal | None = None,
    object_id: UUID | None = None,
    **event: Any,
) -> None:
    """One audit event at ``at`` through the audit writer: of the system unless ``principal`` acts,
    about the tenant's id unless ``object_id`` names a row; ``event`` are further keywords of
    ``uow.audit`` (``outcome``, ``contract_id``)."""
    ctx = RequestContext(
        principal=system_principal(tenant_id) if principal is None else principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-audit-api",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=at,
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=frozen_clock(at), keyring=keyring, files=files) as uow:
        uow.audit(
            action=action,
            object_type=action.split(".")[0],
            object_id=tenant_id if object_id is None else object_id,
            **event,
        )
        uow.commit()


def _stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def verify(app: FastAPI, actor: Actor) -> HttpResponse:
    return call(app, "POST", VERIFY, headers=cookie_headers(actor.token, actor.csrf_token))


def _actions(response: HttpResponse) -> list[str]:
    assert response.status_code == 200, response.text
    return [str(item["action"]) for item in response.json()["items"]]


def test_outcome_filter_is_exact_and_repeatable(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """04 §16.14 rev 1.154 (a): ``outcome`` is one of E-81, and sent several times it answers the
    events of any of them."""
    maya_member, maya, _victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    files = LocalFileStore(app_settings.file_root)
    t0 = FROZEN_AT - timedelta(hours=2)
    for seconds, action, outcome in (
        (0, "role.create", AuditOutcome.SUCCESS),
        (60, "role.update", AuditOutcome.DENIED),
        (120, "role.archive", AuditOutcome.FAILED),
        (180, "role.delete", AuditOutcome.DENIED),
    ):
        at = t0 + timedelta(seconds=seconds)
        _record(tenant_id, keyring, files, at=at, action=action, outcome=outcome)
    window = [("object_type", "role"), ("from", _stamp(t0)), ("to", _stamp(FROZEN_AT))]

    def listed(*outcomes: str) -> HttpResponse:
        params = [*window, *(("outcome", outcome) for outcome in outcomes)]
        return call(app, "GET", AUDIT, params=params, headers=cookie_headers(maya.token, key=False))

    assert _actions(listed()) == ["role.delete", "role.archive", "role.update", "role.create"]
    assert _actions(listed("DENIED")) == ["role.delete", "role.update"]
    assert _actions(listed("FAILED")) == ["role.archive"]
    assert _actions(listed("DENIED", "FAILED")) == ["role.delete", "role.archive", "role.update"]
    assert {item["outcome"] for item in listed("SUCCESS").json()["items"]} == {"SUCCESS"}
    unknown = listed("REFUSED")
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text


def test_a_read_without_a_range_starts_thirty_days_back(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """04 §16.14 rev 1.154: a read always has a start — ``from`` when sent, else thirty days before
    ``to``, else thirty days before the request — except a read by chain sequence or by contract,
    which an index answers in every month; ``from`` and ``to`` narrow those too when sent."""
    maya_member, maya, _victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    files = LocalFileStore(app_settings.file_root)
    now = clock.now()
    contract = uuid4()  # the filter reads the key; it does not ask what the id names
    for age, action in (
        (timedelta(days=75), "role.create"),
        (timedelta(days=40), "role.update"),
        (timedelta(days=30), "role.archive"),  # exactly the start: `from` is inclusive
        (timedelta(days=29), "role.restore"),
        (timedelta(hours=1), "role.delete"),
    ):
        _record(tenant_id, keyring, files, at=now - age, action=action, contract_id=contract)
    role_events = {"object_type": "role"}

    recent = get(app, AUDIT, maya, **role_events)
    assert _actions(recent) == ["role.delete", "role.restore", "role.archive"]
    # `to` without `from`: the thirty days before `to`.
    before = get(app, AUDIT, maya, to=_stamp(now - timedelta(days=35)), **role_events)
    assert _actions(before) == ["role.update"]
    # `from` is honoured however far back it reaches.
    since = get(app, AUDIT, maya, **{"from": _stamp(now - timedelta(days=80))}, **role_events)
    assert _actions(since) == [
        "role.delete",
        "role.restore",
        "role.archive",
        "role.update",
        "role.create",
    ]
    counted = get(app, AUDIT, maya, count="true", **role_events)
    assert counted.headers[TOTAL_COUNT_HEADER] == "3"

    # An event is addressed by its chain sequence, at any age.
    oldest = since.json()["items"][-1]
    by_sequence = get(app, AUDIT, maya, chain_seq=str(oldest["chain_seq"]))
    assert [item["id"] for item in by_sequence.json()["items"]] == [oldest["id"]]
    assert _actions(get(app, AUDIT, maya, chain_seq="999999999")) == []
    for malformed in ("0", "-3", "first"):
        refused = get(app, AUDIT, maya, chain_seq=malformed)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    # ... and never by its id (no index leads with it): `id` is not a filter of the resource.
    by_id = get(app, AUDIT, maya, id=oldest["id"])
    assert (by_id.status_code, slug(by_id)) == (422, "validation-failed"), by_id.text
    assert by_id.json()["errors"][0]["field"] == "id"

    # The trail of a contract is read whole ...
    trail = get(app, AUDIT, maya, contract_id=str(contract))
    assert _actions(trail) == _actions(since)
    assert _actions(get(app, AUDIT, maya, contract_id=str(uuid4()))) == []
    # ... and a range narrows it when the caller sends one.
    narrowed = get(
        app,
        AUDIT,
        maya,
        contract_id=str(contract),
        **{"from": _stamp(now - timedelta(days=45)), "to": _stamp(now - timedelta(days=29))},
    )
    assert _actions(narrowed) == ["role.archive", "role.update"]
    not_an_id = get(app, AUDIT, maya, contract_id="SF-ORD-10002")
    assert (not_an_id.status_code, slug(not_an_id)) == (422, "validation-failed"), not_an_id.text
    # A cursor continues the read it came from: the contract is part of what it is bound to.
    first_page = get(app, AUDIT, maya, contract_id=str(contract), limit="2")
    cursor = first_page.json()["next_cursor"]
    rest = get(app, AUDIT, maya, contract_id=str(contract), limit="2", cursor=cursor)
    assert _actions(first_page) + _actions(rest) == _actions(since)[:4]
    foreign = get(app, AUDIT, maya, contract_id=str(uuid4()), limit="2", cursor=cursor)
    assert (foreign.status_code, slug(foreign)) == (422, "validation-failed"), foreign.text


def test_an_event_is_read_with_its_object_label_and_its_actors_membership(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """04 §16.14 rev 1.154 (d) and (e): ``object_label`` is the business identifier of the object
    — null for a type without one, for no object id and for an id no row has — and
    ``actor_membership_id`` is the membership of the person who acted, null for the system, for an
    API client and for a member who has been removed. Both are read in the event's own statement."""
    maya_member, maya, _victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    files = LocalFileStore(app_settings.file_root)
    oscar_member = colleague(tenant_id, "oscar")
    with tenant_session(_db(tenant_id)) as session:
        auditor = session.execute(select(role.c.id).where(role.c.code == "auditor")).scalar_one()
    acting = maya_principal(oscar_member)
    t0 = FROZEN_AT - timedelta(hours=2)
    written: list[tuple[str, UUID | None, Principal | None]] = [
        ("role.update", UUID(str(auditor)), acting),  # a row with a code, by a person
        ("tenant_membership.suspend", oscar_member.membership_id, None),  # a member, by the system
        ("app_user.update", oscar_member.user_id, None),
        ("role.archive", uuid4(), None),  # an id no role has
        ("route.refuse", None, None),  # a type without a label
    ]
    for offset, (action, object_id, principal) in enumerate(written):
        _record(
            tenant_id,
            keyring,
            files,
            at=t0 + timedelta(seconds=offset),
            action=action,
            object_id=object_id,
            principal=principal,
        )
    window = {"from": _stamp(t0), "to": _stamp(t0 + timedelta(minutes=5)), "sort": "chain_seq"}

    listed = get(app, AUDIT, maya, **window)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [(item["action"], item["object_label"]) for item in items] == [
        ("role.update", "auditor"),
        ("tenant_membership.suspend", "Oscar"),
        ("app_user.update", "Oscar"),
        ("role.archive", None),
        ("route.refuse", None),
    ]
    by_oscar, by_system = items[0], items[1]
    assert by_oscar["actor"] == {
        "id": str(oscar_member.user_id),
        "kind": "USER",
        "display_name": "Oscar",
    }
    assert by_oscar["actor_membership_id"] == str(oscar_member.membership_id)
    assert (by_system["actor"]["kind"], by_system["actor_membership_id"]) == ("SYSTEM", None)

    # A member who has been removed has no user screen to open: the id is not answered.
    with tenant_session(_db(tenant_id)) as session:
        session.execute(
            update(tenant_membership)
            .where(tenant_membership.c.id == oscar_member.membership_id)
            .values(status="REMOVED", removed_at=clock.now())
        )
    removed = get(app, AUDIT, maya, **window).json()["items"][0]
    assert removed["actor"]["display_name"] == "Oscar"  # the Actor still names the person
    assert removed["actor_membership_id"] is None


def test_actors_of_a_range_are_the_options_of_the_actor_filter(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 §16.14 rev 1.154 (f): ``GET /audit-events/actors`` answers who acted in a range — never
    the workspace's user list — to a holder of ``audit.read``, who does not hold ``user.manage``
    (API-R-05)."""
    maya_member, maya, victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    files = LocalFileStore(app_settings.file_root)
    # Three names whose order no collation disputes: Billing sync, Lena, Oscar.
    with identity_session(request_id="tests-audit-actors") as identity:
        identity.execute(
            update(app_user)
            .where(app_user.c.id == maya_member.user_id)
            .values(display_name="Lena", updated_by_kind="SYSTEM")
        )
    oscar_member = colleague(tenant_id, "oscar")
    idle_member = colleague(tenant_id, "idle")  # a member who does nothing
    client_id = uuid4()
    with tenant_session(_db(tenant_id)) as session:
        session.execute(
            insert(api_client).values(
                **api_client_values(tenant_id=tenant_id, id=client_id, name="Billing sync")
            )
        )
    client = Principal(
        kind=PrincipalKind.API_CLIENT,
        id=client_id,
        tenant_id=tenant_id,
        membership_id=None,
        display_name="Billing sync",
        roles=(),
        permissions=frozenset(),
        permission_scopes={},
        entity_scope="*",
        auth_method="client_credentials",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    now = clock.now()
    for age, principal in (
        (timedelta(days=40), maya_principal(oscar_member)),  # before the default range
        (timedelta(days=3), client),
        (timedelta(days=2), maya_principal(maya_member)),
        (timedelta(days=1), maya_principal(maya_member)),  # a second event of the same person
        (timedelta(hours=1), None),  # the system: no id, so no option
    ):
        _record(tenant_id, keyring, files, at=now - age, action="role.update", principal=principal)

    def actors(**params: str) -> HttpResponse:
        return get(app, f"{AUDIT}/actors", maya, **params)

    recent = actors()
    assert recent.status_code == 200, recent.text
    lena = {"id": str(maya_member.user_id), "kind": "USER", "display_name": "Lena"}
    sync = {"id": str(client_id), "kind": "API_CLIENT", "display_name": "Billing sync"}
    oscar = {"id": str(oscar_member.user_id), "kind": "USER", "display_name": "Oscar"}
    # By name; one entry a person; the idle member, Victor and the system are not answered.
    assert recent.json() == {"items": [sync, lena], "is_truncated": False}
    assert str(idle_member.user_id) not in recent.text
    everyone = actors(**{"from": _stamp(now - timedelta(days=60))})
    assert everyone.json() == {"items": [sync, lena, oscar], "is_truncated": False}
    assert actors(to=_stamp(now - timedelta(days=35))).json()["items"] == [oscar]
    # Each option filters the log.
    for option in everyone.json()["items"]:
        found = get(
            app, AUDIT, maya, actor_id=option["id"], **{"from": _stamp(now - timedelta(days=60))}
        )
        assert {item["actor"]["id"] for item in found.json()["items"]} == {option["id"]}
    # `q` is part of the name, any case; LIKE wildcards are plain characters.
    assert actors(q="SYNC").json()["items"] == [sync]
    assert actors(q="%").json()["items"] == []
    # Bounded: the first of the range by name, and the answer says that there are more.
    monkeypatch.setattr(audit_log, "ACTOR_LIMIT", 1)
    assert actors().json() == {"items": [sync], "is_truncated": True}
    refused = get(app, f"{AUDIT}/actors", victor)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text


def test_list_filters(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    maya_member, maya, victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    files = LocalFileStore(app_settings.file_root)
    t0, t1 = FROZEN_AT - timedelta(hours=2), FROZEN_AT - timedelta(hours=1)
    for seconds, action in (
        (-60, "role.create"),
        (0, "role.create"),
        (60, "role.update"),
        (120, "tenant.update"),
        (180, "role.create"),
        (3600, "role.create"),
    ):
        _record(tenant_id, keyring, files, at=t0 + timedelta(seconds=seconds), action=action)
    window = {"from": _stamp(t0), "to": _stamp(t1)}

    listed = get(app, AUDIT, maya, object_type="role", action="role.create", **window)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    # Newest first; `from` is inclusive and `to` exclusive.
    assert [(item["action"], datetime.fromisoformat(item["occurred_at"])) for item in items] == [
        ("role.create", t0 + timedelta(seconds=180)),
        ("role.create", t0),
    ]
    newest, oldest = items
    assert set(newest) == EVENT_KEYS
    assert newest["chain_seq"] == oldest["chain_seq"] + 3
    assert (newest["object_type"], newest["object_id"], newest["outcome"]) == (
        "role",
        str(tenant_id),
        "SUCCESS",
    )
    assert (newest["actor"]["kind"], newest["actor"]["id"]) == ("SYSTEM", None)
    assert newest["prev_hmac"] and newest["hmac"]

    counted = get(app, AUDIT, maya, object_type="role", count="true", **window)
    assert counted.status_code == 200, counted.text
    assert counted.headers[TOTAL_COUNT_HEADER] == "3"

    malformed = get(app, AUDIT, maya, **{"from": "yesterday"})
    assert (malformed.status_code, slug(malformed)) == (422, "validation-failed"), malformed.text
    refused = get(app, AUDIT, victor, object_type="role")
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text


def test_verify_on_demand_without_a_stamped_release_fails_closed(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P5-DOCTOR-R1b, the cause certified (Codex; D-98 candidate 101c (e)): a JobRuntime in a
    process that never stamped — no remembered release, no remembered environment — runs the
    on-demand verification into the CTL-039 producer's fail-closed refusal (05 REL-03; D-98 60):
    every attempt of VERIFY_RETRY fails with ``release-mismatch`` and the job ends FAILED with that
    problem (503) in ``job.problem``; no T-PLT-23 row is written. DB-bound, NOT RUN on l12."""
    monkeypatch.setattr(release, "_current_release", None)
    monkeypatch.setattr(release, "_current_env", None)
    unstamped = JobRuntime(
        clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root)
    )
    maya_member, maya, _ = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    requested = verify(app, maya)
    assert requested.status_code == 202, requested.text
    job_id = UUID(requested.json()["id"])
    for attempt in range(1, audit_jobs.VERIFY_RETRY.max_attempts + 1):
        with tenant_session(_db(tenant_id)) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(_FETCHED, {"id": task_id})
        run_job(job_id, tenant_id, attempt=attempt, runtime=unstamped)
    with tenant_session(_db(tenant_id)) as session:
        failed = (
            session.execute(select(job.c.state, job.c.problem).where(job.c.id == job_id))
            .mappings()
            .one()
        )
    assert failed["state"] == "FAILED", failed
    assert (failed["problem"]["type"], failed["problem"]["status"]) == (
        "https://erev.dev/problems/release-mismatch",
        503,
    )
    listed = get(app, VERIFICATIONS, maya)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []


def test_verify_on_demand_returns_job(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    maya_member, maya, victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id

    requested = verify(app, maya)
    assert requested.status_code == 202, requested.text
    body = requested.json()
    assert (body["kind"], body["state"], body["created_by"]["id"]) == (
        "AUDIT_CHAIN_VERIFY",
        "QUEUED",
        str(maya_member.user_id),
    )
    job_id = UUID(body["id"])
    assert requested.headers["location"] == f"/api/v1/jobs/{job_id}"

    with tenant_session(_db(tenant_id)) as session:
        procrastinate_job_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": procrastinate_job_id})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)

    listed = get(app, VERIFICATIONS, maya)
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    assert (item["trigger"], item["result"], item["job_id"], item["first_failure_seq"]) == (
        "ON_DEMAND",
        "PASS",
        str(job_id),
        None,
    )
    assert set(item) == {
        "id",
        "trigger",
        "from_chain_seq",
        "to_chain_seq",
        "events_checked",
        "result",
        "first_failure_seq",
        "failure_detail",
        "digest_last_hmac",
        "digest_file_id",
        "job_id",
        "started_at",
        "finished_at",
    }
    assert item["events_checked"] == item["to_chain_seq"] >= 12
    assert get(app, VERIFICATIONS, maya, result="FAIL").json()["items"] == []
    # 04 §16.14 rev 1.154 (g): one verification by its id, to a holder of audit.read.
    shown = get(app, f"{VERIFICATIONS}/{item['id']}", maya)
    assert shown.status_code == 200, shown.text
    assert shown.json() == item
    missing = get(app, f"{VERIFICATIONS}/{job_id}", maya)  # an id of another table
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text
    malformed = get(app, f"{VERIFICATIONS}/latest", maya)
    assert (malformed.status_code, slug(malformed)) == (422, "validation-failed"), malformed.text

    finished = get(app, f"/api/v1/jobs/{job_id}", maya).json()
    assert (finished["state"], finished["result"]["href"]) == ("SUCCEEDED", VERIFICATIONS)
    # Holders of audit.read download the digest (SF-09:verification).
    digest = get(app, f"/api/v1/files/{item['digest_file_id']}/content", maya)
    assert digest.status_code == 200, digest.text
    assert json.loads(digest.content)["last_chain_seq"] == item["to_chain_seq"]
    # ... and nobody else does: the digest is an audit artefact (04 T-PLT-29 Read access).
    unseen = get(app, f"/api/v1/files/{item['digest_file_id']}/content", victor)
    assert (unseen.status_code, slug(unseen)) == (404, "not-found"), unseen.text

    refused = verify(app, victor)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    hidden = get(app, VERIFICATIONS, victor)
    assert (hidden.status_code, slug(hidden)) == (403, "forbidden"), hidden.text
    unseen_one = get(app, f"{VERIFICATIONS}/{item['id']}", victor)
    assert (unseen_one.status_code, slug(unseen_one)) == (403, "forbidden"), unseen_one.text


def _verify_jobs(tenant_id: UUID) -> list[tuple[UUID, str]]:
    """(id, state) of the tenant's AUDIT_CHAIN_VERIFY jobs, oldest first."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(job.c.id, job.c.state)
            .where(job.c.kind == "AUDIT_CHAIN_VERIFY")
            .order_by(job.c.created_at, job.c.id)
        ).all()
    return [(UUID(str(found)), str(state)) for found, state in rows]


def _job_audit(tenant_id: UUID) -> list[tuple[str, str, UUID | None, str, UUID]]:
    """``(action, actor kind, actor id, request id, job id)`` of the tenant's job audit events, in
    chain order (04 T-PLT-27 rev 1.106)."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.actor_kind,
                audit_event.c.actor_id,
                audit_event.c.request_id,
                audit_event.c.object_id,
            )
            .where(audit_event.c.object_type == "job")
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (str(action), str(kind), actor, str(request), UUID(str(found)))
        for action, kind, actor, request, found in rows
    ]


def test_sc_8_verify_on_demand_defers_one_job_at_a_time(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Security finding SC-8 (supervisor ruling R-32; dev-guide DG-KRN-AUD-07 rev 1.89). Every
    ``POST /audit-events/verify`` (``audit.read``, no MFA) deferred one more full-chain job: three
    requests, three QUEUED jobs. The command now defers unless a verification is pending, and
    answers 202 with the pending job otherwise — whoever asks, whether the job is still waiting
    to be dispatched, has a task, or is being run. Positive control: once that job has finished,
    the next request defers a new one. Supervisor ruling R-50 (a) (04 T-PLT-27 rev 1.106): each
    deferral writes ``job.start`` as its caller under the response's request id, a request answered
    with the pending job writes nothing, and the run writes ``job.finish``."""
    maya_member, maya, _victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    oscar_member = colleague(tenant_id, "oscar")
    with tenant_session(_db(tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=oscar_member.membership_id,
            role_code="auditor",
        )
    oscar = workspace(app, oscar_member, sign_in(app, oscar_member.email))

    first = verify(app, maya)
    assert first.status_code == 202, first.text
    job_id = UUID(first.json()["id"])
    assert _verify_jobs(tenant_id) == [(job_id, "QUEUED")]

    # The same auditor and another one ask again: the pending job answers, none is deferred.
    for actor in (maya, oscar, maya):
        again = verify(app, actor)
        assert again.status_code == 202, again.text
        assert (again.json()["id"], again.json()["kind"]) == (str(job_id), "AUDIT_CHAIN_VERIFY")
        assert again.json()["created_by"]["id"] == str(maya_member.user_id)
        assert again.headers["location"] == f"/api/v1/jobs/{job_id}"
    assert _verify_jobs(tenant_id) == [(job_id, "QUEUED")]

    # A worker has fetched the task (``doing``): still pending.
    with tenant_session(_db(tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    fetched = verify(app, oscar)
    assert (fetched.status_code, fetched.json()["id"]) == (202, str(job_id)), fetched.text
    assert _verify_jobs(tenant_id) == [(job_id, "QUEUED")]

    # Positive control: the verification runs to its end; the next request defers a new job.
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    assert _verify_jobs(tenant_id) == [(job_id, "SUCCEEDED")]
    later = verify(app, oscar)
    assert later.status_code == 202, later.text
    second_id = UUID(later.json()["id"])
    assert second_id != job_id
    assert later.json()["created_by"]["id"] == str(oscar_member.user_id)
    assert _verify_jobs(tenant_id) == [(job_id, "SUCCEEDED"), (second_id, "QUEUED")]
    listed = get(app, VERIFICATIONS, maya)
    assert listed.status_code == 200, listed.text
    assert [item["job_id"] for item in listed.json()["items"]] == [str(job_id)]
    # R-50 (a): two deferrals, two job.start events; the five requests answered with the pending
    # job left none.
    assert _job_audit(tenant_id) == [
        ("job.start", "USER", maya_member.user_id, first.headers[REQUEST_ID], job_id),
        ("job.finish", "SYSTEM", None, f"job-{job_id}", job_id),
        ("job.start", "USER", oscar_member.user_id, later.headers[REQUEST_ID], second_id),
    ]


def test_sc_8_concurrent_on_demand_verifications_defer_one_job(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The pending check and the insert of ``registry.defer_single`` are one critical section
    (dev-guide DG-KRN-AUD-07): a request that arrives while another transaction holds the advisory
    lock of the tenant and kind is observed WAITING for it, and once that transaction has deferred
    its verification and committed, the request answers with that job — two callers, one job."""
    maya_member, maya, _victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    key = f"erev.job.single:{tenant_id}:{JobKind.AUDIT_CHAIN_VERIFY.value}"
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = verify(app, maya)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    request = threading.Thread(target=run, name="verify-on-demand")
    started = False
    try:
        with observing_checkouts() as backends:
            with tenant_session(_db(tenant_id)) as holder:
                holder_pid = backend_pid(holder)
                holder.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
                request.start()
                started = True
                blocked_pid, blocked_in = await_lock_wait(
                    holder,
                    holder_pid=holder_pid,
                    backends=backends,
                    timeout=20.0,
                    expect="pg_advisory_xact_lock",
                )
                assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
                # The holder defers the verification the request is about to ask for.
                row = registry.insert_job(
                    holder,
                    JobKind.AUDIT_CHAIN_VERIFY,
                    {"trigger": "SCHEDULED"},
                    tenant_id=tenant_id,
                    now=clock.now(),
                    created_by=None,
                    created_by_kind=PrincipalKind.SYSTEM,
                )
                registry.dispatch(
                    holder,
                    job_id=row["id"],
                    tenant_id=tenant_id,
                    queue=str(row["queue"]),
                    now=clock.now(),
                )
    finally:
        if started:
            request.join(timeout=30)
    assert "error" not in outcome, outcome
    response = outcome["result"]
    assert response.status_code == 202, response.text
    assert response.json()["id"] == str(row["id"])
    assert _verify_jobs(tenant_id) == [(UUID(str(row["id"])), "QUEUED")]
