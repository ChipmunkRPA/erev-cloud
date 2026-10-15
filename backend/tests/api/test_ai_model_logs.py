"""AI call evidence is tenant-scoped and owner-filtered before pagination/counts."""

from datetime import timedelta

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_model_log, legal_entity
from fastapi import FastAPI
from sqlalchemy import insert
from support.http import call
from support.principals import colleague, cookie_headers, enrolled, member
from support.rows import (
    RowContext,
    ai_model_log_row,
    insert_custom_role,
    insert_role_assignment,
    legal_entity_row,
)
from tests.api.test_tenant_api import app as app  # noqa: F401

PATH = "/api/v1/ai/model-logs"


def test_call_log_visibility_counts_and_cursor(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = member(keyring, clock)
    peer = colleague(owner.tenant_id, "call_log_peer")
    admin = colleague(owner.tenant_id, "call_log_admin")
    outsider = member(keyring, clock)
    ids = []
    for person, permission in ((owner, "ai.use"), (peer, "ai.use"), (admin, "settings.manage")):
        with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
            code = "calls_" + str(person.user_id).replace("-", "")
            insert_custom_role(
                session, tenant_id=person.tenant_id, code=code, permissions=[permission]
            )
            insert_role_assignment(
                session,
                tenant_id=person.tenant_id,
                membership_id=person.membership_id,
                role_code=code,
            )
    for index, person in enumerate((owner, peer, owner, outsider)):
        with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
            row = ai_model_log_row(RowContext(person.tenant_id, person.user_id), session)
            row.update(
                created_by=person.user_id,
                created_by_kind="USER",
                created_at=clock.now() - timedelta(seconds=10 - index),
            )
            session.execute(insert(ai_model_log).values(**row))
            ids.append(str(row["id"]))
    owner_actor = enrolled(app, clock, owner)
    headers = cookie_headers(owner_actor.token, owner_actor.csrf_token)
    first = call(app, "GET", PATH, params={"count": "true", "limit": 1}, headers=headers)
    assert first.status_code == 200, first.text
    assert first.headers["X-Erev-Total-Count"] == "2"
    assert [row["id"] for row in first.json()["items"]] == [ids[2]]
    evidence = first.json()["items"][0]
    detail = call(app, "GET", PATH + "/" + ids[2], headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json() == evidence
    for hidden in (ids[1], ids[3]):
        assert call(app, "GET", PATH + "/" + hidden, headers=headers).status_code == 404

    assert evidence["created_by"]["id"] == str(owner.user_id)
    assert set(evidence) == {
        "id",
        "provider",
        "model_id",
        "prompt_template_id",
        "prompt_template_version",
        "parameters",
        "input_sha256",
        "response_sha256",
        "usage_known",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "outcome",
        "error_detail",
        "created_at",
        "created_by",
    }
    second = call(
        app,
        "GET",
        PATH,
        params={"limit": 1, "cursor": first.json()["next_cursor"]},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert [row["id"] for row in second.json()["items"]] == [ids[0]]
    assert second.json()["next_cursor"] is None
    peer_actor = enrolled(app, clock, peer)
    peer_rows = call(
        app,
        "GET",
        PATH,
        params={"count": "true"},
        headers=cookie_headers(peer_actor.token, peer_actor.csrf_token),
    )
    assert peer_rows.status_code == 200, peer_rows.text
    assert peer_rows.headers["X-Erev-Total-Count"] == "1"
    assert [row["id"] for row in peer_rows.json()["items"]] == [ids[1]]
    administrator = enrolled(app, clock, admin)
    all_rows = call(
        app,
        "GET",
        PATH,
        params={"count": "true"},
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert all_rows.status_code == 200, all_rows.text
    assert all_rows.headers["X-Erev-Total-Count"] == "3"
    assert [row["id"] for row in all_rows.json()["items"]] == [ids[2], ids[1], ids[0]]
    denied = enrolled(app, clock, outsider)
    assert (
        call(app, "GET", PATH, headers=cookie_headers(denied.token, denied.csrf_token)).status_code
        == 403
    )
    assert call(app, "GET", PATH).status_code == 401
    assert call(app, "GET", PATH, params={"outcome": "SUCCESS"}, headers=headers).status_code == 422


def test_scoped_administrator_cannot_read_workspace_calls(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    person = member(keyring, clock)
    with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
        entity = legal_entity_row(RowContext(person.tenant_id, person.user_id), session)
        session.execute(insert(legal_entity).values(**entity))
        insert_custom_role(
            session,
            tenant_id=person.tenant_id,
            code="scoped_calls",
            permissions=["settings.manage"],
        )
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=person.membership_id,
            role_code="scoped_calls",
            entity_ids=[entity["id"]],
        )
    actor = enrolled(app, clock, person)
    headers = cookie_headers(actor.token, actor.csrf_token)
    assert call(app, "GET", PATH, headers=headers).status_code == 403
    with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
        insert_custom_role(
            session, tenant_id=person.tenant_id, code="own_calls", permissions=["ai.use"]
        )
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=person.membership_id,
            role_code="own_calls",
            entity_ids=[entity["id"]],
        )
        for owner_id in (person.user_id, None):
            row = ai_model_log_row(RowContext(person.tenant_id, person.user_id), session)
            row.update(created_by=owner_id, created_by_kind="USER" if owner_id else "SYSTEM")
            session.execute(insert(ai_model_log).values(**row))
    own = call(app, "GET", PATH, params={"count": "true"}, headers=headers)
    assert own.status_code == 200, own.text
    assert own.headers["X-Erev-Total-Count"] == "1"
    assert own.json()["items"][0]["created_by"]["id"] == str(person.user_id)


def test_call_log_distinguishes_unknown_usage_from_confirmed_zero(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    person = member(keyring, clock)
    cases = [
        ("UNKNOWN", "ERROR", False, False),
        (None, "ERROR", False, False),
        ("invalid", "SUCCESS", True, False),
        ("NOT_SENT", "ERROR", False, False),
        ("REPORTED", "ERROR", False, True),
        ("REPORTED", "SUCCESS", True, True),
        ("NOT_SENT", "DISABLED", False, True),
        (None, "BUDGET_EXCEEDED", False, True),
        (None, "SUCCESS", True, True),
    ]
    expected = {}
    with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
        insert_custom_role(
            session, tenant_id=person.tenant_id, code="usage_reader", permissions=["ai.use"]
        )
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=person.membership_id,
            role_code="usage_reader",
        )
        for marker, outcome, response, known in cases:
            row = ai_model_log_row(RowContext(person.tenant_id, person.user_id), session)
            row.update(
                created_by=person.user_id,
                created_by_kind="USER",
                input_tokens=0,
                output_tokens=0,
                outcome=outcome,
                response_sha256="b" * 64 if response else None,
                parameters={} if marker is None else {"usage_evidence": marker},
            )
            session.execute(insert(ai_model_log).values(**row))
            expected[str(row["id"])] = known
    actor = enrolled(app, clock, person)
    headers = cookie_headers(actor.token, actor.csrf_token)
    result = call(app, "GET", PATH, headers=headers)
    assert result.status_code == 200, result.text
    assert {row["id"]: row["usage_known"] for row in result.json()["items"]} == expected
    for log_id, known in expected.items():
        detail = call(app, "GET", PATH + "/" + log_id, headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["usage_known"] is known
        assert detail.json()["input_tokens"] == detail.json()["output_tokens"] == 0
