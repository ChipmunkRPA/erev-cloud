"""Contract operational exception counts and both sides of the list filter agree."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from erev_api.db.session import tenant_session
from erev_api.db.tables import exception_item, obligation
from sqlalchemy import insert, select, update
from support.factories import J03World, customer_id, sf_ord_20417_body
from support.reference import get, post
from support.rows import exception_item_values
from tests.domain.contracts.test_contract_reads import app as app  # noqa: F401
from tests.domain.contracts.test_contract_reads import world as world  # noqa: F401


def test_open_counts_follow_subjects_and_filters_before_paging(world: J03World) -> None:
    actor = world.place.author
    rows = []
    for suffix in ("A", "B", "C"):
        buyer = customer_id(
            world.app, actor, code=f"EXC-{suffix}", name=f"Exception probe {suffix}"
        )
        response = post(
            world.app,
            "/api/v1/contracts",
            actor,
            sf_ord_20417_body(buyer, external_id=f"EXC-{suffix}"),
        )
        assert response.status_code == 201, response.text
        assert response.json()["open_exception_count"] == 0
        rows.append(response.json())
    a, b, c = rows
    aid, bid, cid = (UUID(row["id"]) for row in rows)
    tenant = world.place.tenant_id
    with tenant_session(world.place.principal.db_context) as session:
        obligation_id = session.scalar(
            select(obligation.c.id).where(obligation.c.contract_id == aid)
        )
        assert obligation_id is not None

        def add(**values: Any) -> UUID:
            row = exception_item_values(tenant, **values)
            session.execute(insert(exception_item).values(**row))
            return UUID(str(row["id"]))

        direct = add(contract_id=aid, occurrence_count=7)
        add(contract_id=aid, status="IN_PROGRESS")
        add(combination_group_id=UUID(a["combination_group"]["id"]))
        add(obligation_id=obligation_id)
        add(
            code="COMBINATION_SUGGESTED",
            contract_id=cid,
            source_payload={"contract_ids": [str(aid), str(bid)]},
        )
        # An explicit contract takes precedence over a group reference.
        add(contract_id=bid, combination_group_id=UUID(a["combination_group"]["id"]))
        add(contract_id=aid, status="RESOLVED")
        add(contract_id=aid, status="DISMISSED")
        # Malformed/empty suggestion payloads fall back to their explicit contract.
        add(code="COMBINATION_SUGGESTED", contract_id=bid, source_payload={"contract_ids": "bad"})
        add()  # Unbound workspace finding: not a finding about every contract.
    expected = {str(aid): 5, str(bid): 3, str(cid): 0}
    for row in rows:
        response = get(world.app, f"/api/v1/contracts/{row['id']}", actor)
        assert response.status_code == 200, response.text
        assert response.json()["open_exception_count"] == expected[row["id"]]
    for flag, wanted in (("true", {str(aid), str(bid)}), ("false", {str(cid)})):
        response = get(
            world.app,
            "/api/v1/contracts",
            actor,
            {"has_exceptions": flag, "count": "true", "limit": "1", "q": "EXC-"},
        )
        assert response.status_code == 200, response.text
        assert response.headers["X-Erev-Total-Count"] == str(len(wanted))
        found = []
        while True:
            for item in response.json()["items"]:
                assert item["open_exception_count"] == expected[item["id"]]
                found.append(item["id"])
            cursor = response.json()["next_cursor"]
            if cursor is None:
                break
            response = get(
                world.app,
                "/api/v1/contracts",
                actor,
                {"has_exceptions": flag, "limit": "1", "q": "EXC-", "cursor": cursor},
            )
            assert response.status_code == 200, response.text
        assert set(found) == wanted and len(found) == len(wanted)
    with tenant_session(world.place.principal.db_context) as session:
        session.execute(
            update(exception_item).where(exception_item.c.id == direct).values(status="RESOLVED")
        )
    refreshed = get(world.app, f"/api/v1/contracts/{aid}", actor)
    assert refreshed.status_code == 200
    assert refreshed.json()["open_exception_count"] == 4


def test_counts_keep_tenant_and_entity_scope(committed_db: Any, keyring: Any) -> None:
    from erev_api.db.session import DbContext
    from erev_api.db.tables import contract
    from erev_api.domain.contracts import exception_counts
    from support.factories import tenant_factory, tenant_id_of
    from support.rows import insert_contract_rows

    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    foreign = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant, None, "*")) as session:
        own = insert_contract_rows(session, tenant)
        other = insert_contract_rows(session, tenant)
        for entity_id in (own.entity_id, other.entity_id):
            session.execute(
                insert(exception_item).values(
                    **exception_item_values(
                        tenant, contract_id=own.contract_id, entity_id=entity_id
                    )
                )
            )
    with tenant_session(DbContext(foreign, None, "*")) as session:
        session.execute(
            insert(exception_item).values(
                **exception_item_values(
                    foreign,
                    code="COMBINATION_SUGGESTED",
                    source_payload={"contract_ids": [str(own.contract_id)]},
                )
            )
        )
    for context, expected in (
        (DbContext(tenant, None, "*"), {own.contract_id: 2, other.contract_id: 0}),
        (DbContext(tenant, None, (own.entity_id,)), {own.contract_id: 1}),
    ):
        with tenant_session(context, read_only=True) as session:
            assert {
                row_id: total
                for row_id, total in session.execute(
                    select(contract.c.id, exception_counts.count())
                )
            } == expected
