"""Dimensions (04 §15.3 API-R-21, T-REF-13, T-REF-16, T-REF-17, DB-12, API-C-08; 03 REQ-REF-009;
SCREENS_B §9.5; BUILD_SPEC RFD-6).

Maya holds Revenue Accountant, which carries ``config.author`` and ``masterdata.maintain``; Omar
holds Viewer, which carries ``config.read`` only (docs/02-PRD.md §5.6).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, dimension_value
from erev_api.domain.reference import accounts
from erev_api.main import create_app
from erev_api.schemas.accounts import GlAccountOut
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

DIMENSIONS = "/api/v1/dimensions"
ACCOUNTS = "/api/v1/gl-accounts"
PROBLEM_BASE = "https://erev.dev/problems/"
BUILTIN = ("department", "class", "location", "product", "customer")


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


def revenue_account(code: str, **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "name": f"Revenue {code}",
        "account_type": "REVENUE",
        "normal_balance": "C",
        **extra,
    }


def test_sixth_custom_dimension_rejected(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    listed = get(app, DIMENSIONS, maya)
    assert listed.status_code == 200, listed.text
    assert [
        (item["code"], item["is_builtin"], item["position"]) for item in listed.json()["items"]
    ] == [(code, True, position) for position, code in enumerate(BUILTIN, start=1)]

    for number in range(1, 6):
        created = post(
            app, DIMENSIONS, maya, {"code": f"region_{number}", "name": f"Region {number}"}
        )
        assert created.status_code == 201, created.text
        assert created.headers["ETag"] == '"r1"'
        assert (created.json()["is_builtin"], created.json()["position"]) == (False, 5 + number)

    sixth = post(app, DIMENSIONS, maya, {"code": "region_6", "name": "Region 6"})
    assert (sixth.status_code, slug(sixth)) == (422, "validation-failed"), sixth.text
    assert sixth.json()["detail"] == "A workspace can define at most five custom dimensions."
    assert fields(sixth) == [(None, "DB-12")]
    assert len(get(app, DIMENSIONS, maya).json()["items"]) == 10


def test_custom_dimension_codes(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")

    taken = post(app, DIMENSIONS, maya, {"code": "department", "name": "Department"})
    assert fields(taken) == [("code", "T-REF-16")]
    malformed = post(app, DIMENSIONS, maya, {"code": "Region", "name": ""})
    assert fields(malformed) == [("code", "T-REF-16"), ("name", "T-REF-16")]
    denied = post(app, DIMENSIONS, omar, {"code": "region", "name": "Region"})
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    assert get(app, DIMENSIONS, omar).status_code == 200

    placed = post(app, DIMENSIONS, maya, {"code": "region", "name": "Region", "position": 3})
    assert placed.status_code == 201, placed.text
    assert placed.json()["position"] == 3
    inactive = get(app, f"{DIMENSIONS}?is_active=false", maya)
    assert inactive.json()["items"] == []


def test_required_dimensions_on_account(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    created = post(app, ACCOUNTS, maya, revenue_account("4010", required_dimensions=["department"]))
    assert created.status_code == 201, created.text

    got = get(app, f"{ACCOUNTS}/{created.json()['id']}", maya)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["required_dimensions"] == ["department"]
    assert accounts.missing_dimensions(body, {"department": None}) == ["department"]
    assert accounts.missing_dimensions(body, {"department": "SALES"}) == []
    assert accounts.missing_dimensions(GlAccountOut.model_validate(body), {}) == ["department"]

    unknown = post(app, ACCOUNTS, maya, revenue_account("4020", required_dimensions=["region"]))
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text
    assert fields(unknown) == [("required_dimensions", "T-REF-13")]
    repeated = post(
        app, ACCOUNTS, maya, revenue_account("4020", required_dimensions=["class", "class"])
    )
    assert fields(repeated) == [("required_dimensions", "T-REF-13")]

    # A custom dimension can be required once it exists.
    assert post(app, DIMENSIONS, maya, {"code": "region", "name": "Region"}).status_code == 201
    accepted = post(
        app, ACCOUNTS, maya, revenue_account("4020", required_dimensions=["department", "region"])
    )
    assert accepted.status_code == 201, accepted.text
    assert accounts.missing_dimensions(accepted.json(), {"department": "SALES"}) == ["region"]


def test_product_and_customer_values_not_stored(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    for code in ("product", "customer"):
        refused = post(
            app, f"{DIMENSIONS}/{code}/values", maya, {"code": "AVM-GW", "name": "Gateway"}
        )
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert fields(refused) == [(None, "T-REF-17")]
        listed = get(app, f"{DIMENSIONS}/{code}/values", maya)
        assert (listed.status_code, listed.json()["items"]) == (200, [])

    sales = post(app, f"{DIMENSIONS}/department/values", maya, {"code": "SALES", "name": "Sales"})
    assert sales.status_code == 201, sales.text
    assert sales.headers["ETag"] == '"r1"'
    values = get(app, f"{DIMENSIONS}/department/values", maya)
    assert [item["code"] for item in values.json()["items"]] == ["SALES"]

    unknown = post(app, f"{DIMENSIONS}/region/values", maya, {"code": "EU", "name": "Europe"})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    assert get(app, f"{DIMENSIONS}/region/values", maya).status_code == 404
    with tenant_session(tenant_context(maya), read_only=True) as session:
        assert session.execute(select(func.count()).select_from(dimension_value)).scalar_one() == 1


def test_dimension_value_hierarchy(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")
    values = f"{DIMENSIONS}/location/values"
    emea = post(app, values, maya, {"code": "EMEA", "name": "Europe, Middle East and Africa"})
    assert emea.status_code == 201, emea.text
    emea_id = emea.json()["id"]
    berlin = post(app, values, maya, {"code": "BER", "name": "Berlin", "parent_value_id": emea_id})
    assert berlin.status_code == 201, berlin.text
    assert berlin.json()["parent_value_id"] == emea_id
    berlin_id = berlin.json()["id"]

    # A parent is a value of the same dimension; a code is unique within its dimension.
    sales = post(app, f"{DIMENSIONS}/department/values", maya, {"code": "SALES", "name": "Sales"})
    foreign = post(
        app, values, maya, {"code": "PAR", "name": "Paris", "parent_value_id": sales.json()["id"]}
    )
    assert fields(foreign) == [("parent_value_id", "T-REF-17")]
    duplicate = post(app, values, maya, {"code": "EMEA", "name": "Again"})
    assert fields(duplicate) == [("code", "T-REF-17")]

    emea_path = f"{values}/{emea_id}"
    # EMEA cannot move below Berlin, its own child.
    cycle = patch(app, emea_path, maya, {"parent_value_id": berlin_id}, if_match='"r1"')
    assert fields(cycle) == [("parent_value_id", "T-REF-17")]
    missing = patch(app, emea_path, maya, {"name": "EMEA"}, if_match=None)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    denied = patch(app, emea_path, omar, {"name": "EMEA"}, if_match='"r1"')
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    elsewhere = patch(
        app, f"{DIMENSIONS}/department/values/{emea_id}", maya, {"name": "EMEA"}, if_match='"r1"'
    )
    assert (elsewhere.status_code, slug(elsewhere)) == (404, "not-found"), elsewhere.text

    renamed = patch(app, emea_path, maya, {"name": "EMEA", "is_active": False}, if_match='"r1"')
    assert renamed.status_code == 200, renamed.text
    assert renamed.headers["ETag"] == '"r2"'
    detached = patch(app, f"{values}/{berlin_id}", maya, {"parent_value_id": None}, if_match='"r1"')
    assert detached.status_code == 200, detached.text
    assert detached.json()["parent_value_id"] is None
    active = get(app, f"{values}?is_active=true", omar)
    assert [item["code"] for item in active.json()["items"]] == ["BER"]

    with tenant_session(tenant_context(maya), read_only=True) as session:
        event = session.execute(
            select(audit_event.c.before, audit_event.c.after).where(
                audit_event.c.action == "dimension_value.update",
                audit_event.c.object_id == uuid.UUID(emea_id),
            )
        ).one()
    assert tuple(event) == (
        {"name": "Europe, Middle East and Africa", "is_active": True},
        {"name": "EMEA", "is_active": False},
    )
