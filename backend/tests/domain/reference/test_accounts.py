"""Chart of accounts (04 §15.3 API-R-20, T-REF-13, E-38, E-52, API-C-08, §17 LM-CL-11; 03
REQ-REF-007; PRD §2.6; BUILD_SPEC RFD-6).

Maya holds Revenue Accountant, which carries ``config.author``; Omar holds Viewer, which carries
``config.read`` only (docs/02-PRD.md §5.6). ``legal_entity`` arrives with RFD-2, so AVM-DE and
AVM-US are fixed ids here; since 04 rev 1.319 an account names entities that exist, and the test
of applicability writes the two rows first.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, fiscal_calendar, gl_account, legal_entity
from erev_api.domain.reference import accounts
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, member, sign_in, workspace
from support.rows import fiscal_calendar_values, insert_role_assignment, legal_entity_values

ACCOUNTS = "/api/v1/gl-accounts"
PROBLEM_BASE = "https://erev.dev/problems/"
AVM_DE = uuid.UUID("0191e0a0-0000-7000-8000-0000000000de")
AVM_US = uuid.UUID("0191e0a0-0000-7000-8000-0000000000a5")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def post(app: FastAPI, path: str, actor: Actor, json: dict[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def patch(
    app: FastAPI, path: str, actor: Actor, json: dict[str, Any], *, if_match: str | None
) -> HttpResponse:
    headers = cookie_headers(actor.token, actor.csrf_token)
    if if_match is not None:
        headers["If-Match"] = if_match
    return call(app, "PATCH", path, json=json, headers=headers)


def get(app: FastAPI, path: str, actor: Actor) -> HttpResponse:
    return call(app, "GET", path, headers=cookie_headers(actor.token, key=False))


def holding(app: FastAPI, someone: Member, role_code: str) -> Actor:
    """Assign the tenant's role ``role_code``, then sign in to the workspace."""
    ctx = DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code=role_code,
        )
    return workspace(app, someone, sign_in(app, someone.email))


def tenant_context(actor: Actor) -> DbContext:
    return DbContext(tenant_id=actor.member.tenant_id, user_id=None, entity_scope="*")


def account(
    code: str,
    name: str,
    account_type: str = "ASSET",
    normal_balance: str = "D",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "account_type": account_type,
        "normal_balance": normal_balance,
        **extra,
    }


def test_account_types_and_normal_balance(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    chart = (
        ("1100", "Accounts receivable", "ASSET", "D"),
        ("2100", "Contract liability", "LIABILITY", "C"),
        ("4010", "Revenue - services and subscriptions", "REVENUE", "C"),
    )
    for code, name, account_type, normal_balance in chart:
        created = post(app, ACCOUNTS, maya, account(code, name, account_type, normal_balance))
        assert created.status_code == 201, created.text
        body = created.json()
        assert created.headers["ETag"] == '"r1"'
        assert created.headers["Location"] == f"{ACCOUNTS}/{body['id']}"
        assert (body["code"], body["name"], body["account_type"], body["normal_balance"]) == (
            code,
            name,
            account_type,
            normal_balance,
        )
        assert (body["entity_ids"], body["required_dimensions"]) == ([], [])
        assert (body["source_system"], body["is_active"]) == ("MANUAL_UI", True)

    refused = post(app, ACCOUNTS, maya, account("1300", "Other receivable", normal_balance="X"))
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert [field for field, _ in fields(refused)] == ["normal_balance"]

    listed = get(app, ACCOUNTS, maya)
    assert listed.status_code == 200, listed.text
    assert [
        (item["code"], item["account_type"], item["normal_balance"])
        for item in listed.json()["items"]
    ] == [(code, account_type, normal) for code, _, account_type, normal in chart]
    liabilities = get(app, f"{ACCOUNTS}?account_type=LIABILITY", maya)
    assert [item["code"] for item in liabilities.json()["items"]] == ["2100"]
    searched = get(app, f"{ACCOUNTS}?q=revenue", maya)
    assert [item["code"] for item in searched.json()["items"]] == ["4010"]
    with tenant_session(tenant_context(maya), read_only=True) as session:
        created_events = select(audit_event.c.object_id).where(
            audit_event.c.action == "gl_account.create"
        )
        assert len(session.execute(created_events).scalars().all()) == 3


def test_account_code_unique(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    first = post(app, ACCOUNTS, maya, account("2100", "Contract liability", "LIABILITY", "C"))
    assert first.status_code == 201, first.text

    second = post(app, ACCOUNTS, maya, account("2100", "Deferred revenue", "LIABILITY", "C"))
    assert (second.status_code, slug(second)) == (422, "validation-failed"), second.text
    assert second.json()["errors"][0]["field"] == "code"
    assert fields(second) == [("code", "T-REF-13")]

    # Every finding is listed: a malformed code and a blank name.
    malformed = post(app, ACCOUNTS, maya, account("-2100", " ", "LIABILITY", "C"))
    assert fields(malformed) == [("code", "T-REF-13"), ("name", "T-REF-13")]


def _entities(actor: Actor, *entity_ids: uuid.UUID) -> None:
    """The legal entities ``entity_ids`` of the actor's workspace, on one calendar, as rows."""
    tenant_id = actor.member.tenant_id
    everything = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(everything) as session:
        calendar = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        for number, entity_id in enumerate(entity_ids, start=1):
            row = legal_entity_values(tenant_id, calendar_id=calendar["id"], code=f"AVM-{number}")
            session.execute(insert(legal_entity).values(**{**row, "id": entity_id}))


def test_entity_applicability(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    # 04 T-REF-13 rev 1.319 (item READ-SCOPE-BY-PERMISSION-1, register index 301): an id of
    # ``entity_ids`` names a legal entity of the workspace. Until that revision the list was
    # checked for repetition alone, and this test stored the ids of entities that did not exist
    # — a STALE TEST WORLD by the supervisor's ruling of 2026-10-03. The two entities exist now;
    # an id that names none is refused on the member.
    unknown = post(app, ACCOUNTS, maya, account("1200", "Contract asset", entity_ids=[str(AVM_DE)]))
    assert unknown.status_code == 422, unknown.text
    assert fields(unknown) == [("entity_ids", "T-REF-13")]
    _entities(maya, AVM_DE, AVM_US)
    german = post(app, ACCOUNTS, maya, account("1200", "Contract asset", entity_ids=[str(AVM_DE)]))
    assert german.status_code == 201, german.text
    assert german.json()["entity_ids"] == [str(AVM_DE)]
    everywhere = post(app, ACCOUNTS, maya, account("1100", "Accounts receivable"))
    assert everywhere.status_code == 201, everywhere.text
    repeated = post(
        app,
        ACCOUNTS,
        maya,
        account("1105", "Unbilled receivable", entity_ids=[str(AVM_DE), str(AVM_DE)]),
    )
    assert fields(repeated) == [("entity_ids", "T-REF-13")]

    with tenant_session(tenant_context(maya), read_only=True) as session:
        assert accounts.applicable(session, code="1200", entity_id=AVM_DE) is True
        assert accounts.applicable(session, code="1200", entity_id=AVM_US) is False
        # Empty entity_ids: applicable to all entities.
        assert accounts.applicable(session, code="1100", entity_id=AVM_US) is True
        assert accounts.applicable(session, code="1999", entity_id=AVM_DE) is False


def test_legacy_account_numbers_are_text(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    for code in ("21001", "15002", "5001"):
        created = post(app, ACCOUNTS, maya, account(code, f"Legacy {code}", "LIABILITY", "C"))
        assert created.status_code == 201, created.text
        assert created.json()["code"] == code

    items = get(app, ACCOUNTS, maya).json()["items"]
    # Text order, not numeric order.
    assert [item["code"] for item in items] == ["15002", "21001", "5001"]
    assert all(isinstance(item["code"], str) for item in items)
    with tenant_session(tenant_context(maya), read_only=True) as session:
        stored = session.execute(select(gl_account.c.code).order_by(gl_account.c.code)).scalars()
        assert list(stored) == ["15002", "21001", "5001"]


def test_update_account_requires_if_match(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")
    created = post(app, ACCOUNTS, maya, account("4010", "Revenue - services", "REVENUE", "C"))
    assert created.status_code == 201, created.text
    path = f"{ACCOUNTS}/{created.json()['id']}"

    # config.read reads an account; config.author creates and changes one.
    got = get(app, path, omar)
    assert (got.status_code, got.headers["ETag"]) == (200, '"r1"'), got.text
    denied = post(app, ACCOUNTS, omar, account("4020", "Licences", "REVENUE", "C"))
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    refused = patch(app, path, omar, {"name": "Services"}, if_match='"r1"')
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text

    rename = {"name": "Revenue - services and subscriptions", "is_active": False}
    missing = patch(app, path, maya, rename, if_match=None)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    stale = patch(app, path, maya, rename, if_match='"r7"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    renamed = patch(app, path, maya, rename, if_match='"r1"')
    assert renamed.status_code == 200, renamed.text
    assert renamed.headers["ETag"] == '"r2"'
    assert (renamed.json()["name"], renamed.json()["is_active"]) == (
        "Revenue - services and subscriptions",
        False,
    )

    code_change = patch(app, path, maya, {"code": "4011"}, if_match='"r2"')
    assert (code_change.status_code, slug(code_change)) == (422, "validation-failed")
    blank = patch(app, path, maya, {"name": None}, if_match='"r2"')
    assert fields(blank) == [("name", "T-REF-13")]
    unknown = get(app, f"{ACCOUNTS}/{uuid.uuid4()}", maya)
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    with tenant_session(tenant_context(maya), read_only=True) as session:
        event = session.execute(
            select(audit_event.c.object_version, audit_event.c.before, audit_event.c.after).where(
                audit_event.c.action == "gl_account.update"
            )
        ).one()
        # An inactive account applies to no entity.
        assert accounts.applicable(session, code="4010", entity_id=AVM_US) is False
    assert tuple(event) == (
        "2",
        {"name": "Revenue - services", "is_active": True},
        {"name": "Revenue - services and subscriptions", "is_active": False},
    )
