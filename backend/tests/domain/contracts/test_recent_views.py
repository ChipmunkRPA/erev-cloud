"""Recent contracts are private, bounded and reauthorized on every read."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import contract_recent_view
from erev_api.domain.contracts import recent_views
from sqlalchemy import func, select
from support.factories import J03World, maya_principal, sf_ord_20417_body
from support.reference import get, post
from tests.domain.contracts.test_contract_reads import app as app  # noqa: F401
from tests.domain.contracts.test_contract_reads import world as world  # noqa: F401


def test_successful_opens_are_private_ordered_and_paginated(world: J03World) -> None:
    actor = world.place.author
    ids = []
    for suffix in ("A", "B", "C"):
        response = post(
            world.app,
            "/api/v1/contracts",
            actor,
            sf_ord_20417_body(world.customer_id, external_id=f"RECENT-{suffix}"),
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    assert get(world.app, f"/api/v1/contracts/{ids[2]}", actor).status_code == 200
    params = {"quick_list": "RECENTLY_VIEWED", "count": "true", "limit": "1"}
    empty = get(world.app, "/api/v1/contracts", actor, params)
    assert empty.status_code == 200, empty.text
    assert empty.json()["items"] == []  # Neither creation nor lists record opens.
    for contract_id in (ids[0], ids[1], ids[0]):
        response = get(
            world.app, f"/api/v1/contracts/{contract_id}", actor, {"record_view": "true"}
        )
        assert response.status_code == 200, response.text
    first = get(world.app, "/api/v1/contracts", actor, params)
    assert first.status_code == 200, first.text
    assert first.headers["X-Erev-Total-Count"] == "2"
    assert first.json()["items"][0]["id"] == ids[0]
    second = get(
        world.app, "/api/v1/contracts", actor, {**params, "cursor": first.json()["next_cursor"]}
    )
    assert second.status_code == 200, second.text
    assert [row["id"] for row in second.json()["items"]] == [ids[1]]
    assert second.json()["next_cursor"] is None
    other = get(world.app, "/api/v1/contracts", world.priya, params)
    assert other.status_code == 200, other.text
    assert other.json()["items"] == []
    missing = get(world.app, f"/api/v1/contracts/{new_id()}", actor, {"record_view": "true"})
    assert missing.status_code == 404
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(contract_recent_view)) == 2
    with tenant_session(maya_principal(world.priya.member).db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(contract_recent_view)) == 0
    narrowed = replace(world.place.principal, entity_scope=(world.uk_entity_id,))
    with tenant_session(narrowed.db_context, read_only=True) as session:
        assert session.execute(recent_views.statement(narrowed)).all() == []


def test_history_retains_only_fifty_and_reopening_moves_to_front(world: J03World) -> None:
    from erev_api.db.tables import contract
    from sqlalchemy import insert
    from support.rows import contract_values, insert_contract_rows

    principal = world.place.principal
    with tenant_session(principal.db_context) as session:
        chain = insert_contract_rows(session, principal.tenant_id)
        ids = []
        for _ in range(52):
            row = contract_values(
                principal.tenant_id,
                customer_id=chain.customer_id,
                contracting_entity_id=chain.entity_id,
                combination_group_id=chain.group_id,
            )
            session.execute(insert(contract).values(**row))
            ids.append(UUID(str(row["id"])))
            recent_views.record(session, principal, ids[-1])
        found = [row.contract_id for row in session.execute(recent_views.statement(principal))]
        assert found == list(reversed(ids[2:]))
        recent_views.record(session, principal, ids[0])
        found = [row.contract_id for row in session.execute(recent_views.statement(principal))]
        assert found == [ids[0], *reversed(ids[3:])]
        assert session.scalar(select(func.count()).select_from(contract_recent_view)) == 50

    from concurrent.futures import ThreadPoolExecutor

    def open_again(contract_id: UUID) -> None:
        with tenant_session(principal.db_context) as session:
            recent_views.record(session, principal, contract_id)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(open_again, ids))
    with tenant_session(principal.db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(contract_recent_view)) == 50
        retained = [row.contract_id for row in session.execute(recent_views.statement(principal))]
        assert len(retained) == len(set(retained)) == 50


def test_recent_history_migration_roundtrip(committed_db: Any) -> None:
    from alembic import command
    from sqlalchemy import text
    from support.db import alembic_config

    command.downgrade(alembic_config(), "0158")
    with committed_db.owner_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('erev.contract_recent_view')")) is None
    command.upgrade(alembic_config(), "head")
    with committed_db.owner_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM erev.alembic_version")) == "0159"
        assert (
            connection.scalar(
                text(
                    "SELECT relforcerowsecurity FROM pg_class "
                    "WHERE oid = 'erev.contract_recent_view'::regclass"
                )
            )
            is True
        )
