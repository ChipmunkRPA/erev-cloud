"""Idempotency keys and optimistic concurrency (dev-guide §5.7 DG-KRN-IDEM-01 to DG-KRN-IDEM-05,
§6.1 DG-CMD-12; 04 T-PLT-28, API-C-04, API-C-08; 05 TXN-06; REQ-PLT-026, REQ-PLT-027; PLF-7).

The commands are test-only routes mounted on the test app. Each request acts as a signed-in member
who holds ``report.run`` through the ``viewer`` role.
"""

from __future__ import annotations

import io
import json
import uuid
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Annotated, Any

import pytest
from erev_api.api.deps import (
    CommandContext,
    KernelDeps,
    assert_version,
    command,
    kernel_deps,
    row_etag,
    run_command,
)
from erev_api.auth.dependencies import require
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, app_engine, tenant_session
from erev_api.db.tables import idempotency_record, tenant_membership
from erev_api.idempotency import store
from erev_api.main import create_app
from erev_api.problems import LOCK_CONFLICT_DETAIL, Problem
from erev_api.uow import UnitOfWork
from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Member, member, sign_in
from support.rows import insert_role_assignment

PERMISSION = "report.run"
BASE = "/api/v1/__tests__"
PROBES = f"{BASE}/probes"
FORBIDDEN = f"{BASE}/forbidden"
NOT_FOUND = f"{BASE}/not-found"
EXPLODE = f"{BASE}/explode"
BUSY = f"{BASE}/busy"
DEADLOCKED = f"{BASE}/deadlocked"
PERIOD_CLOSED = f"{BASE}/period-closed"
STALE = f"{BASE}/stale"
SLOW = f"{BASE}/slow"
SECOND_CONNECTION = f"{BASE}/second-connection"
CONTEXT = f"{BASE}/context"
MEMBERSHIPS = f"{BASE}/memberships"
CONTRACTS = f"{BASE}/contracts"
PROBLEM_BASE = "https://erev.dev/problems/"
# PRD ERR-05, ERR-06, ERR-07, ERR-39 and ERR-40.
KEY_MESSAGE = "Send an Idempotency-Key header with every command."
REUSED = "This Idempotency-Key was already used with a different request body."
CHANGED = (
    "This record changed since you opened it. Reload to see the latest version, then try again."
)
VERSION_REQUIRED = "Send If-Match with the record's ETag to change this record."
IN_PROGRESS = (
    "The first request with this Idempotency-Key is still being processed. "
    "Retry after it completes."
)


class ProbeIn(BaseModel):
    name: str


@dataclass(frozen=True, slots=True)
class Actor:
    member: Member
    token: str
    csrf_token: str


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    application = create_app(app_settings, clock=clock)
    runs: list[str] = []
    contexts: list[RequestContext] = []
    application.state.runs = runs
    application.state.contexts = contexts

    @application.post(PROBES, status_code=201)
    def create_probe(
        body: ProbeIn,
        cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
        deps: Annotated[KernelDeps, Depends(kernel_deps)],
    ) -> Response:
        def handler(uow: UnitOfWork) -> dict[str, Any]:
            runs.append(body.name)
            return {"name": body.name, "run": len(runs)}

        return run_command(
            cmd, deps, handler, status_code=201, location=lambda result: f"{PROBES}/{result['run']}"
        )

    def failing_route(path: str, error: Exception) -> None:
        @application.post(path)
        def failing(
            cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
            deps: Annotated[KernelDeps, Depends(kernel_deps)],
        ) -> Response:
            def handler(uow: UnitOfWork) -> dict[str, Any]:
                runs.append(path.rsplit("/", 1)[1])
                raise error

            return run_command(cmd, deps, handler)

    failing_route(FORBIDDEN, Problem("forbidden"))
    failing_route(NOT_FOUND, Problem("not-found"))
    failing_route(EXPLODE, RuntimeError("probe failure"))
    # The refusal a deadlock is mapped to (the commit's mapper raises it as a Problem), and a 409 of
    # another slug.
    failing_route(DEADLOCKED, Problem("lock-conflict", LOCK_CONFLICT_DETAIL))
    # The period guard's refusal as the client sees it (04 DB-07 (2); §14.1 EREV-LED-003).
    failing_route(PERIOD_CLOSED, Problem("period-closed", code="EREV-LED-003"))
    failing_route(STALE, Problem("invalid-transition"))

    @application.post(BUSY + "/{membership_id}")
    def busy(
        membership_id: uuid.UUID,
        cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
        deps: Annotated[KernelDeps, Depends(kernel_deps)],
    ) -> Response:
        def handler(uow: UnitOfWork) -> dict[str, Any]:
            runs.append("busy")
            # The row lock of a decision that does not wait: SQLSTATE 55P03 while another holds it.
            uow.session.execute(
                select(tenant_membership.c.id)
                .where(tenant_membership.c.id == membership_id)
                .with_for_update(nowait=True)
            ).scalar_one()
            return {"taken": True}

        return run_command(cmd, deps, handler)

    @application.post(SLOW + "/{membership_id}")
    def slow(
        membership_id: uuid.UUID,
        cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
        deps: Annotated[KernelDeps, Depends(kernel_deps)],
    ) -> Response:
        def handler(uow: UnitOfWork) -> dict[str, Any]:
            runs.append("slow")
            # A statement that outlives the unit of work's statement timeout - shortened for this
            # one statement from 60 seconds to 200 ms, below the lock timeout: while another
            # transaction holds the row, PostgreSQL cancels the wait with SQLSTATE 57014.
            uow.session.execute(text("SET LOCAL statement_timeout = 200"))
            uow.session.execute(
                select(tenant_membership.c.id)
                .where(tenant_membership.c.id == membership_id)
                .with_for_update()
            ).scalar_one()
            uow.session.execute(text("SET LOCAL statement_timeout = 60000"))
            return {"taken": True}

        return run_command(cmd, deps, handler)

    @application.post(SECOND_CONNECTION)
    def second_connection(
        cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
        deps: Annotated[KernelDeps, Depends(kernel_deps)],
    ) -> Response:
        def handler(uow: UnitOfWork) -> dict[str, Any]:
            runs.append("second-connection")
            # The shape of the lock decision's readers (domain/close/freeze.py `system_reads`,
            # `system_unit`): a second pooled connection while the command holds its own.
            with tenant_session(uow.principal.db_context, read_only=True) as reader:
                reader.execute(select(tenant_membership.c.id).limit(1)).all()
            return {"read": True}

        return run_command(cmd, deps, handler)

    @application.get(CONTEXT)
    def context_probe(
        ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
    ) -> dict[str, str]:
        contexts.append(ctx)
        return {}

    @application.patch(MEMBERSHIPS + "/{membership_id}")
    def touch_membership(
        membership_id: uuid.UUID,
        cmd: Annotated[CommandContext, Depends(command(PERMISSION, precondition="row"))],
        deps: Annotated[KernelDeps, Depends(kernel_deps)],
    ) -> Response:
        def handler(uow: UnitOfWork) -> dict[str, Any]:
            current = uow.session.execute(
                select(tenant_membership.c.row_version)
                .where(tenant_membership.c.id == membership_id)
                .with_for_update()
            ).scalar_one()
            assert_version(cmd.expected_version, int(current))
            version = uow.session.execute(
                update(tenant_membership)
                .where(tenant_membership.c.id == membership_id)
                .values(
                    last_opened_at=uow.now,
                    updated_by=uow.principal.id,
                    updated_by_kind=uow.principal.kind.value,
                )
                .returning(tenant_membership.c.row_version)
            ).scalar_one()
            return {"row_version": int(version)}

        return run_command(cmd, deps, handler, etag=lambda result: row_etag(result["row_version"]))

    @application.post(CONTRACTS + "/{contract_id}/probe")
    def contract_probe(
        contract_id: uuid.UUID,
        cmd: Annotated[CommandContext, Depends(command(PERMISSION, precondition="contract"))],
        deps: Annotated[KernelDeps, Depends(kernel_deps)],
    ) -> Response:
        return run_command(
            cmd,
            deps,
            lambda uow: {"contract_id": str(contract_id), "expected_version": cmd.expected_version},
        )

    return application


def _all_entities(tenant_id: uuid.UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def actor(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    lena = member(keyring, clock)
    with tenant_session(_all_entities(lena.tenant_id)) as db:
        insert_role_assignment(
            db, tenant_id=lena.tenant_id, membership_id=lena.membership_id, role_code="viewer"
        )
    # D-83: sign-in opens her only ACTIVE membership, so the membership row version stays at 3.
    signed = sign_in(app, lena.email)
    assert signed.body["active_tenant"]["id"] == str(lena.tenant_id), signed.body
    return Actor(member=lena, token=signed.token, csrf_token=signed.csrf_token)


def send(
    app: FastAPI,
    method: str,
    path: str,
    actor: Actor,
    *,
    key: str | None,
    json: Any = None,
    if_match: str | None = None,
) -> HttpResponse:
    headers = {"Cookie": f"erev_session={actor.token}", "X-CSRF-Token": actor.csrf_token}
    if key is not None:
        headers["Idempotency-Key"] = key
    if if_match is not None:
        headers["If-Match"] = if_match
    return call(app, method, path, json=json, headers=headers)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def records(actor: Actor, key: str) -> list[dict[str, Any]]:
    with tenant_session(_all_entities(actor.member.tenant_id), read_only=True) as db:
        rows = db.execute(
            select(idempotency_record).where(idempotency_record.c.idempotency_key == key)
        ).mappings()
        return [dict(row) for row in rows]


def begin_probe(app: FastAPI, actor: Actor, key: str) -> store.Started | store.Replay:
    """Start an attempt of ``POST PROBES {"name": "alpha"}`` outside HTTP, as the actor."""
    assert send(app, "GET", CONTEXT, actor, key=None).status_code == 200
    ctx = replace(app.state.contexts[-1], idempotency_key=key)
    return store.begin(
        ctx,
        method="POST",
        route_template=PROBES,
        path_params={},
        query={},
        body=b'{"name": "alpha"}',
        content_type="application/json",
    )


def membership_version(actor: Actor) -> int:
    with tenant_session(_all_entities(actor.member.tenant_id), read_only=True) as db:
        version = db.execute(
            select(tenant_membership.c.row_version).where(
                tenant_membership.c.id == actor.member.membership_id
            )
        ).scalar_one()
    return int(version)


@pytest.mark.control("CTL-001")
def test_krn_idem_01_missing_or_malformed_key(app: FastAPI, actor: Actor) -> None:
    """CTL-001, its second clause ("command retries are safe"; 03 REQ-PLT-026): a
    command without an ``Idempotency-Key``, or with a malformed one, is refused 422
    ``validation-failed`` under rule API-C-04 and runs nothing. Not witnessed here:
    the repeat itself (``test_krn_idem_02_replay_same_body``).
    """
    for key in (None, "k-12345"):
        response = send(app, "POST", PROBES, actor, key=key, json={"name": "alpha"})
        assert response.status_code == 422, response.text
        assert slug(response) == "validation-failed"
        error = response.json()["errors"][0]
        assert (error["field"], error["rule_id"], error["message"]) == (
            "Idempotency-Key",
            "API-C-04",
            KEY_MESSAGE,
        )
    assert app.state.runs == []


@pytest.mark.control("CTL-001")
def test_krn_idem_02_replay_same_body(app: FastAPI, actor: Actor) -> None:
    """CTL-001, its second clause ("command retries are safe"; 03 REQ-PLT-026): a
    repeat with the same key and payload returns the stored first response — status,
    body and ``Location`` — marked as a replay, and the command ran once. Not
    witnessed here: the first clause, duplicates rejected before commit (the three
    tests tagged for it in imports and integrations).
    """
    key = "replay-key-0001"
    first = send(app, "POST", PROBES, actor, key=key, json={"name": "alpha"})
    assert first.status_code == 201, first.text
    assert "idempotent-replay" not in first.headers
    second = send(app, "POST", PROBES, actor, key=key, json={"name": "alpha"})
    assert second.status_code == 201, second.text
    assert second.json() == first.json() == {"name": "alpha", "run": 1}
    assert second.headers["location"] == first.headers["location"] == f"{PROBES}/1"
    assert second.headers["idempotent-replay"] == "true"
    assert app.state.runs == ["alpha"]
    (record,) = records(actor, key)
    assert (record["state"], record["response_status"], record["method"], record["path"]) == (
        "COMPLETED",
        201,
        "POST",
        PROBES,
    )
    assert record["principal_id"] == actor.member.user_id
    assert record["completed_at"] is not None


@pytest.mark.control("CTL-001")
def test_krn_idem_02_reused_key_different_body(app: FastAPI, actor: Actor) -> None:
    """CTL-001, its second clause (03 REQ-PLT-026): the same key with a different
    payload is refused 422 ``idempotency-key-reused`` and runs nothing more.
    """
    key = "reused-key-0001"
    assert send(app, "POST", PROBES, actor, key=key, json={"name": "alpha"}).status_code == 201
    reused = send(app, "POST", PROBES, actor, key=key, json={"name": "beta"})
    assert reused.status_code == 422, reused.text
    assert slug(reused) == "idempotency-key-reused"
    assert reused.json()["detail"] == REUSED
    assert app.state.runs == ["alpha"]


@pytest.mark.control("CTL-001")
def test_krn_idem_02_in_progress(app: FastAPI, actor: Actor) -> None:
    """CTL-001, its second clause: a request whose key is held by an attempt still in
    progress is refused 409 ``idempotency-in-progress`` and does not run the
    command.
    """
    key = "in-progress-0001"
    assert isinstance(begin_probe(app, actor, key), store.Started)
    response = send(app, "POST", PROBES, actor, key=key, json={"name": "alpha"})
    assert response.status_code == 409, response.text
    assert slug(response) == "idempotency-in-progress"
    assert response.json()["detail"] == IN_PROGRESS
    assert app.state.runs == []
    (record,) = records(actor, key)
    assert record["state"] == "IN_PROGRESS"


def test_txn_06_stale_in_progress_is_a_new_attempt(
    app: FastAPI, actor: Actor, clock: FrozenClock
) -> None:
    key = "stale-attempt-0001"
    assert isinstance(begin_probe(app, actor, key), store.Started)
    clock.advance(timedelta(minutes=10))
    response = send(app, "POST", PROBES, actor, key=key, json={"name": "alpha"})
    assert response.status_code == 201, response.text
    assert app.state.runs == ["alpha"]
    (record,) = records(actor, key)
    assert (record["state"], record["created_at"]) == ("COMPLETED", clock.now())


def test_krn_idem_03_errors_not_stored(app: FastAPI, actor: Actor) -> None:
    key = "forbidden-0001"
    for _ in range(2):
        response = send(app, "POST", FORBIDDEN, actor, key=key)
        assert response.status_code == 403, response.text
        assert slug(response) == "forbidden"
    assert app.state.runs == ["forbidden", "forbidden"]
    assert records(actor, key) == []
    explode_key = "explode-0001"
    assert send(app, "POST", EXPLODE, actor, key=explode_key).status_code == 500
    assert app.state.runs[-1] == "explode"
    assert records(actor, explode_key) == []


def test_krn_idem_03_kept_problem_is_replayed(app: FastAPI, actor: Actor) -> None:
    key = "not-found-0001"
    first = send(app, "POST", NOT_FOUND, actor, key=key)
    assert first.status_code == 404, first.text
    second = send(app, "POST", NOT_FOUND, actor, key=key)
    assert second.status_code == 404
    assert second.json() == first.json()
    assert second.headers["content-type"] == "application/problem+json"
    assert second.headers["idempotent-replay"] == "true"
    assert app.state.runs == ["not-found"]


def test_idem_lock_conflict_1_the_same_key_runs_the_command_after_a_lock_conflict(
    app: FastAPI, actor: Actor
) -> None:
    """IDEM-LOCK-CONFLICT-1 (DG-KRN-IDEM-03 rev 1.127; 04 DB-07 (3); supervisor ruling R-97 (6)):
    the rule for a command that met a busy row is "send it again" - and the same key and body
    then run the command. Fail-first: the 409 was stored as the key's first response and replayed
    with ``Idempotent-Replay: true``; the command never ran a second time."""
    key = "busy-0001"
    path = f"{BUSY}/{actor.member.membership_id}"
    with tenant_session(_all_entities(actor.member.tenant_id)) as holder:
        holder.execute(
            select(tenant_membership.c.id)
            .where(tenant_membership.c.id == actor.member.membership_id)
            .with_for_update()
        ).scalar_one()
        refused = send(app, "POST", path, actor, key=key)
        assert refused.status_code == 409, refused.text
        assert slug(refused) == "lock-conflict"
        assert "idempotent-replay" not in refused.headers
        assert records(actor, key) == []  # nothing is kept for the key
        holder.rollback()
    again = send(app, "POST", path, actor, key=key)
    assert again.status_code == 200, again.text
    assert again.json() == {"taken": True}
    assert "idempotent-replay" not in again.headers
    assert app.state.runs == ["busy", "busy"]  # the command ran both times
    (record,) = records(actor, key)
    assert (record["state"], record["response_status"]) == ("COMPLETED", 200)
    # From here on the key behaves as any other: the success is what a third request is answered.
    replayed = send(app, "POST", path, actor, key=key)
    assert (replayed.status_code, replayed.headers["idempotent-replay"]) == (200, "true")
    assert app.state.runs == ["busy", "busy"]


@pytest.mark.parametrize(
    ("path", "refusal"),
    [(DEADLOCKED, "lock-conflict"), (PERIOD_CLOSED, "period-closed")],
)
def test_idem_lock_conflict_1_the_two_resubmittable_409s_are_not_kept(
    path: str, refusal: str, app: FastAPI, actor: Actor
) -> None:
    """DG-KRN-IDEM-03 rev 1.127, a list by slug (supervisor rulings R-97 (6) and, for the period
    guard, R-112 (d); 04 DB-07 (2)): ``lock-conflict`` raised as a ``Problem``
    (the commit's mapper, a decision's own NOWAIT refusal) and ``period-closed`` - whose
    resubmission is planned into the next open period - are not kept, so the same key runs the
    command again; a 409 of any other slug stays the first response of its key."""
    key = f"{refusal}-0001"
    name = path.rsplit("/", 1)[1]
    for _ in range(2):
        response = send(app, "POST", path, actor, key=key)
        assert (response.status_code, slug(response)) == (409, refusal), response.text
        assert "idempotent-replay" not in response.headers
    assert app.state.runs == [name, name]
    assert records(actor, key) == []
    stale_key = "stale-0001"
    first = send(app, "POST", STALE, actor, key=stale_key)
    assert (first.status_code, slug(first)) == (409, "invalid-transition"), first.text
    second = send(app, "POST", STALE, actor, key=stale_key)
    assert second.json() == first.json()
    assert second.headers["idempotent-replay"] == "true"
    assert app.state.runs.count("stale") == 1


def test_a_cancelled_statement_answers_503_statement_timeout_and_keeps_nothing(
    app: FastAPI, actor: Actor, log_stream: io.StringIO
) -> None:
    """Supervisor ruling R-97 (6) (04 §15.2 rev 1.144; DG-KRN-ERR-02 rev 1.127; PRD ERR-66): a
    command whose statement PostgreSQL cancels at the statement timeout answers the named 503
    ``statement-timeout`` with ``Retry-After: 30`` - the server's state, no fault of the request -
    logs one WARNING without a stack trace, and keeps nothing for its key, so the same key runs
    the command when it is sent again. The error is the server's own (a row lock that waits
    behind another transaction under a statement timeout shortened to 200 ms). Fail-first: 500
    ``about:blank``, logged ``http.unhandled_error`` with a stack trace."""
    key = "slow-0001"
    path = f"{SLOW}/{actor.member.membership_id}"
    with tenant_session(_all_entities(actor.member.tenant_id)) as holder:
        holder.execute(
            select(tenant_membership.c.id)
            .where(tenant_membership.c.id == actor.member.membership_id)
            .with_for_update()
        ).scalar_one()
        log_stream.seek(0)
        log_stream.truncate()
        refused = send(app, "POST", path, actor, key=key)
        holder.rollback()
    assert refused.status_code == 503, refused.text
    assert slug(refused) == "statement-timeout"
    assert refused.headers["retry-after"] == "30"
    assert refused.json()["title"] == "The request took too long"
    assert "idempotent-replay" not in refused.headers
    assert records(actor, key) == []  # nothing is kept for the key
    events = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    named = [event for event in events if event["event"] == "http.statement_timeout"]
    assert [(event["level"], event["sqlstate"]) for event in named] == [("warning", "57014")]
    assert named[0]["driver_error_class"] == "psycopg.errors.QueryCanceled"
    assert "exception" not in named[0]
    assert [event for event in events if event["event"] == "http.unhandled_error"] == []
    again = send(app, "POST", path, actor, key=key)
    assert again.status_code == 200, again.text
    assert again.json() == {"taken": True}
    assert "idempotent-replay" not in again.headers
    assert app.state.runs == ["slow", "slow"]  # the command ran both times


def test_a_pool_that_gives_no_connection_answers_503_and_keeps_nothing(
    app: FastAPI, actor: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor ruling R-103 (c) (04 API-C-05 rev 1.144; DG-KRN-ERR-03 rev 1.127): a command
    that needs a second pooled connection while the pool has none answers 503 with
    ``Retry-After`` - the server's state, never a 409 - and nothing is kept for its key, so the
    same key runs the command once the pool has a connection again. The pool is the
    application's own, exhausted for real; only its wait is shortened from 30 seconds.
    Fail-first: 500 ``about:blank`` without ``Retry-After``."""
    engine = app_engine()
    monkeypatch.setattr(engine.pool, "_timeout", 0.2)
    key = "pool-0001"
    held = []
    try:
        with pytest.raises(PoolTimeoutError):
            while True:
                held.append(engine.connect())
        held.pop().close()  # exactly one connection is left: the command's own
        refused = send(app, "POST", SECOND_CONNECTION, actor, key=key)
    finally:
        for connection in held:
            connection.close()
    assert refused.status_code == 503, refused.text
    assert refused.headers["retry-after"] == "5"
    assert refused.json()["type"] == "about:blank"
    assert "idempotent-replay" not in refused.headers
    assert app.state.runs == ["second-connection"]
    assert records(actor, key) == []
    again = send(app, "POST", SECOND_CONNECTION, actor, key=key)
    assert again.status_code == 200, again.text
    assert again.json() == {"read": True}
    assert "idempotent-replay" not in again.headers
    assert app.state.runs == ["second-connection", "second-connection"]


@pytest.mark.control("CTL-001")
def test_krn_idem_02_expiry_seven_days(app: FastAPI, actor: Actor, clock: FrozenClock) -> None:
    """CTL-001, its second clause (03 REQ-PLT-026 "kept at least 7 days"): the record
    of a command's first response expires seven days after it was created.
    """
    key = "expiry-0001"
    assert send(app, "POST", PROBES, actor, key=key, json={"name": "alpha"}).status_code == 201
    (record,) = records(actor, key)
    assert record["created_at"] == clock.now()
    assert record["expires_at"] == record["created_at"] + timedelta(days=7)


def test_krn_idem_05_if_match(app: FastAPI, actor: Actor) -> None:
    path = f"{MEMBERSHIPS}/{actor.member.membership_id}"
    missing = send(app, "PATCH", path, actor, key="if-match-0001")
    assert missing.status_code == 428, missing.text
    assert slug(missing) == "precondition-required"
    assert missing.json()["detail"] == VERSION_REQUIRED
    assert records(actor, "if-match-0001") == []
    version = membership_version(actor)
    assert version <= 3
    for step in range(version, 3):
        touched = send(
            app, "PATCH", path, actor, key=f"if-match-touch-{step}", if_match=row_etag(step)
        )
        assert touched.status_code == 200, touched.text
    assert membership_version(actor) == 3
    stale = send(app, "PATCH", path, actor, key="if-match-0002", if_match='"r2"')
    assert stale.status_code == 412, stale.text
    assert slug(stale) == "precondition-failed"
    assert stale.json()["detail"] == CHANGED
    assert membership_version(actor) == 3
    assert records(actor, "if-match-0002") == []
    contract_id = uuid.uuid4()
    probe = send(
        app, "POST", f"{CONTRACTS}/{contract_id}/probe", actor, key="contract-0001", if_match='"s3"'
    )
    assert probe.status_code == 200, probe.text
    assert probe.json() == {"contract_id": str(contract_id), "expected_version": 3}


def test_dg_cmd_12_etag_on_single_resource(app: FastAPI, actor: Actor) -> None:
    path = f"{MEMBERSHIPS}/{actor.member.membership_id}"
    version = membership_version(actor)
    response = send(app, "PATCH", path, actor, key="etag-0001", if_match=row_etag(version))
    assert response.status_code == 200, response.text
    assert response.headers["etag"] == f'"r{version + 1}"'
    assert response.json() == {"row_version": version + 1}
    assert membership_version(actor) == version + 1


def test_krn_idem_02_request_hash() -> None:
    def digest(body: bytes, content_type: str) -> str:
        return store.request_sha256(
            method="post",
            route_template=PROBES,
            path_params={},
            query={"b": ["2"], "a": ["1"]},
            body=body,
            content_type=content_type,
        )

    # JSON bodies hash by content, with numbers as Decimal (canonical hashing rejects floats).
    compact = digest(b'{"amount":12.30,"name":"a"}', "application/json; charset=utf-8")
    assert compact == digest(b'{ "name": "a", "amount": 12.30 }', "application/json")
    assert compact != digest(b'{"amount":12.31,"name":"a"}', "application/json")
    # Other media types hash the raw bytes.
    assert digest(b"a,b\n", "text/csv") != digest(b"a, b\n", "text/csv")
