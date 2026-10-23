"""Public portfolio membership commands retain history and require current parent ETags."""

from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.http import call
from support.principals import colleague, cookie_headers, member
from support.reference import entity, get, holding, post

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, contract, legal_entity
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_portfolio_membership_workflow(
    app: FastAPI, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    world = worlds.k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    maya = world.maya
    viewer = holding(app, colleague(maya.member.tenant_id, "portfolio-viewer"), "viewer")
    foreign = holding(app, member(keyring, clock), "revenue_accountant")
    identity = {"code": "SIMILAR-RETURNS", "name": "Similar return profiles"}
    assert post(app, "/api/v1/portfolios", viewer, identity).status_code == 403
    created = post(app, "/api/v1/portfolios", maya, identity)
    assert created.status_code == 201, created.text
    path = created.headers["location"]
    tag = created.headers["etag"]
    assert get(app, path, foreign).status_code == 404
    listed = get(app, "/api/v1/portfolios", viewer, {"count": "true"})
    assert listed.status_code == 200, listed.text
    assert listed.headers["X-Erev-Total-Count"] == "1"
    assert [row["code"] for row in listed.json()["items"]] == [identity["code"]]
    contract_id = str(world.contracts[worlds.K01].contract["id"])
    before_computation = world.place.scalar(
        select(contract.c.latest_computation_id).where(contract.c.id == UUID(contract_id))
    )
    other_entity = entity(
        app,
        world.marcus,
        code="PORTFOLIO-OTHER",
        calendar_id=str(world.place.scalar(select(legal_entity.c.calendar_id).limit(1))),
    )
    hidden = holding(
        app,
        colleague(maya.member.tenant_id, "portfolio-hidden"),
        "revenue_accountant",
        entity_ids=[UUID(other_entity["id"])],
    )
    payload = {"contract_id": contract_id, "rationale": "Same return terms and customer profile."}
    assert post(app, path + "/members", maya, payload).status_code == 428
    assert post(app, path + "/members", viewer, payload, if_match=tag).status_code == 403
    joined = post(app, path + "/members", maya, payload, if_match=tag)
    assert joined.status_code == 201, joined.text
    assert joined.headers["etag"] != tag
    assert post(app, path + "/members", maya, payload, if_match=tag).status_code == 412
    tag = joined.headers["etag"]
    assert get(app, path + "/members", hidden, {"count": "true"}).json()["items"] == []
    assert (
        get(app, path + "/members", hidden, {"count": "true"}).headers["X-Erev-Total-Count"] == "0"
    )
    assert post(app, path + "/members", hidden, payload, if_match=tag).status_code == 404
    assert (
        post(
            app,
            path + f"/members/{contract_id}/remove",
            hidden,
            {"rationale": "Hidden"},
            if_match=tag,
        ).status_code
        == 404
    )
    assert post(app, path + "/members", maya, payload, if_match=tag).status_code == 409
    members = get(app, path + "/members", viewer)
    assert members.status_code == 200, members.text
    assert [row["contract_id"] for row in members.json()["items"]] == [contract_id]
    clock.advance(timedelta(seconds=1))
    ended = post(
        app,
        path + f"/members/{contract_id}/remove",
        maya,
        {"rationale": "Customer terms changed."},
        if_match=tag,
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["valid_to_known_at"] is not None
    assert get(app, path + "/members", viewer).json()["items"] == []
    history = get(app, path + "/members", viewer, {"include_history": "true"})
    assert history.status_code == 200, history.text
    assert len(history.json()["items"]) == 1
    clock.advance(timedelta(seconds=1))
    rejoined = post(app, path + "/members", maya, payload, if_match=ended.headers["etag"])
    assert rejoined.status_code == 201, rejoined.text
    assert rejoined.json()["id"] != joined.json()["id"]
    assert (
        len(get(app, path + "/members", viewer, {"include_history": "true"}).json()["items"]) == 2
    )
    assert (
        world.place.scalar(
            select(func.count())
            .select_from(audit_event)
            .where(audit_event.c.action.in_(["portfolio.member_join", "portfolio.member_leave"]))
        )
        == 3
    )
    assert (
        world.place.scalar(
            select(contract.c.latest_computation_id).where(
                contract.c.id == world.contracts[worlds.K01].contract["id"]
            )
        )
        == before_computation
    )

    headers = cookie_headers(maya.token, maya.csrf_token, key=True)
    headers["If-Match"] = rejoined.headers["etag"]
    updated = call(
        app, "PUT", path, json={**identity, "name": "Updated population"}, headers=headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Updated population"
    headers = cookie_headers(maya.token, maya.csrf_token, key=True)
    headers["If-Match"] = rejoined.headers["etag"]
    assert call(app, "PUT", path, json=identity, headers=headers).status_code == 412
