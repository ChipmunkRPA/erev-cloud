"""The plans of the audit log's reads as the application runs them — ``erev_app`` under the
tenant's row-level security — and the link table the read by contract goes through (04 T-PLT-48,
§16.14 "Audit events", rev 1.154; supervisor rulings R-108 and R-114; item AUD-API-GAPS-1).

Under a policy PostgreSQL turns a caller's condition into an index condition only when every
function in it is leakproof: ``uuid``, ``bigint``, ``text`` and ``timestamptz`` comparisons are,
the ``jsonb`` operators, array containment and enum equality are not. A read that looks indexed in
its SQL can therefore still read every row of the tenant, and only the plan shows it: the first
shape of revision 0101 — two expression indexes over ``audit_event.detail`` — built correctly and
was never entered by the contract. Each test writes a month of events through the audit writer,
analyses what it wrote and reads the plan of the statement the route runs.

A plan test here asks what an index CAN take, not what is cheapest for 1,500 rows: a table of one
page is read whole whatever its indexes. So the planner's alternatives are switched off for the
``EXPLAIN`` (``FORCED``) and the test reads the conditions: a condition the policy keeps out of
the index shows as ``Filter`` however the plan is forced — which is how the finding showed.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.audit import contract_key
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, audit_event_contract
from erev_api.domain.platform import audit_log
from erev_api.enums import TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import select, text
from support.db import TestDatabase
from support.factories import maya_principal
from support.http import HttpResponse, call
from support.plans import FORCED, nodes, plan, reads, sent
from support.principals import Actor, colleague, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

pytestmark = pytest.mark.pg

EVENTS = 1_500  # a month of one workspace, small enough to write in a test
AUDIT = "/api/v1/audit-events"
# The index of one partition that belongs to a partitioned index of the parent.
_CHILD = text(
    """
    SELECT child.relname
    FROM pg_class parent
    JOIN pg_namespace n ON n.oid = parent.relnamespace AND n.nspname = 'erev'
    JOIN pg_inherits i ON i.inhparent = parent.oid
    JOIN pg_class child ON child.oid = i.inhrelid
    JOIN pg_index x ON x.indexrelid = child.oid
    WHERE parent.relname = :parent AND x.indrelid = CAST(:partition AS regclass)
    """
)


def _write(
    tenant_id: UUID,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    events: list[tuple[Principal, dict[str, Any]]],
) -> None:
    """The events through the audit writer, each principal's in one unit of work."""
    for principal in {id(who): who for who, _ in events}.values():
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-audit-log-plans",
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=clock.now(),
            format_locale="en-US",
        )
        with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
            for who, keywords in events:
                if who is principal:
                    uow.audit(action="role.update", object_type="role", object_id=None, **keywords)
            uow.commit()


def _analysed(test_database: TestDatabase, clock: FrozenClock, *parents: str) -> dict[str, str]:
    """Analyse the month's partition and the link table; the name of the partition and of its
    index under each of the parent's partitioned indexes ``parents``."""
    month = f"audit_event_p{clock.now():%Y%m}"
    with test_database.owner_engine.begin() as connection:
        connection.exec_driver_sql(f"ANALYZE erev.{month}")
        connection.exec_driver_sql("ANALYZE erev.audit_event_contract")
        children = {
            parent: str(
                connection.execute(
                    _CHILD, {"parent": parent, "partition": f"erev.{month}"}
                ).scalar_one()
            )
            for parent in parents
        }
    return {"month": month, **children}


def _auditor(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    """A member who holds ``audit.read``, signed in to a workspace of their own."""
    someone = member(keyring, clock)
    context = DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code="auditor",
        )
    return workspace(app, someone, sign_in(app, someone.email))


def _get(app: FastAPI, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", AUDIT, params=params, headers=cookie_headers(actor.token, key=False))


def _full_sorts(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The nodes that sort their whole input; an incremental sort over a presorted key is none."""
    return [node for node in found if node["Node Type"] == "Sort"]


def _driven_by_the_link(node: dict[str, Any]) -> bool:
    """A nested loop whose outer side is the scan of ``audit_event_contract``."""
    if node["Node Type"] != "Nested Loop":
        return False
    outer = node["Plans"][0]
    return outer["Parent Relationship"] == "Outer" and (
        outer.get("Relation Name") == "audit_event_contract"
    )


def _trail_events(
    system: Principal, contract: UUID, sibling: UUID
) -> list[tuple[Principal, dict[str, Any]]]:
    """A month of events: six of the contract alone, four of the contract and a sibling, fifty of
    fifty other contracts, and the rest of none."""
    events: list[tuple[Principal, dict[str, Any]]] = []
    for number in range(EVENTS):
        if number % 250 == 0:
            events.append((system, {"contract_id": contract}))
        elif number % 375 == 1:
            events.append((system, {"contract_ids": [sibling, contract]}))
        elif number % 30 == 2:
            events.append((system, {"contract_id": uuid4()}))
        else:
            events.append((system, {}))
    return events


def test_t_plt_48_the_link_rows_are_the_keys_of_the_events(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """04 T-PLT-48: the chain append writes one row for ``detail.contract_id``, one for each member
    of ``detail.contract_ids`` and none for an event without the key — nothing else, each with the
    event's own sequence, instant and id."""
    tenant_id = member(keyring, clock).tenant_id
    contract, sibling = uuid4(), uuid4()
    events = _trail_events(system_principal(tenant_id), contract, sibling)
    _write(tenant_id, keyring, clock, LocalFileStore(app_settings.file_root), events)

    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(
                audit_event.c.chain_seq,
                audit_event.c.occurred_at,
                audit_event.c.id,
                audit_event.c.detail,
            )
        ).all()
        links = session.execute(
            select(
                audit_event_contract.c.contract_id,
                audit_event_contract.c.chain_seq,
                audit_event_contract.c.occurred_at,
                audit_event_contract.c.audit_event_id,
            )
        ).all()
    keys = [
        (named, event.chain_seq, event.occurred_at, event.id)
        for event in stored
        for named in contract_key.named(event.detail)
    ]
    assert sorted(tuple(link) for link in links) == sorted(keys)
    # ... over events of one contract, of several and of none (provisioning wrote some of none).
    of_one = [event for event in stored if "contract_id" in event.detail]
    of_several = [event for event in stored if "contract_ids" in event.detail]
    assert (len(of_one), len(of_several)) == (56, 4) and len(stored) > EVENTS
    assert len(links) == 56 + 2 * 4
    assert sum(1 for link in links if link.contract_id == contract) == 10
    assert sum(1 for link in links if link.contract_id == sibling) == 4


def test_the_trail_of_a_contract_is_read_through_the_link(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """``GET /audit-events?contract_id=``: for ``erev_app`` the contract is an INDEX CONDITION of
    the link's primary key, each event is looked up by its own key in its own month, the link
    drives the read — and the statement carries no range of ``occurred_at``. The page comes
    newest first from the link's key read backwards: the list kernel orders a key that is never
    NULL without ``NULLS LAST`` (DG-LST-08), so nothing sorts the trail before the limit."""
    app = create_app(app_settings, clock=clock)
    maya = _auditor(app, keyring, clock)
    tenant_id = maya.member.tenant_id
    contract = uuid4()
    events = _trail_events(system_principal(tenant_id), contract, uuid4())
    _write(tenant_id, keyring, clock, LocalFileStore(app_settings.file_root), events)
    names = _analysed(test_database, clock)
    # The statement of the route as the engine got it: the read by contract with the list
    # kernel's order and page size (default sort -chain_seq; 50 and one more).
    with sent() as seen:
        answered = _get(app, maya, contract_id=str(contract))
    assert answered.status_code == 200, answered.text
    (page,) = [read for read in reads(seen, "audit_event_contract") if " LIMIT " in read[0]]
    sql = page[0]
    assert "occurred_at >=" not in sql and "occurred_at <" not in sql  # no range is sent
    assert "detail ->" not in sql and "@>" not in sql  # and no operator the policy keeps out
    assert "NULLS LAST" not in sql.rsplit("ORDER BY", 1)[1], sql[-200:]

    found = list(nodes(plan(tenant_id, page)))
    (link,) = [node for node in found if node.get("Relation Name") == "audit_event_contract"]
    assert link["Node Type"] in ("Index Scan", "Index Only Scan"), link
    assert link["Index Name"] == "audit_event_contract_pkey", link
    assert f"contract_id = '{contract}'::uuid" in link["Index Cond"], link
    assert "tenant_id =" in link["Index Cond"], link
    assert "contract_id" not in link.get("Filter", ""), link
    assert link["Scan Direction"] == "Backward", link  # the newest sequence first, from the key
    assert _full_sorts(found) == [], _full_sorts(found)
    # The event's month is reached by the event's own key, never read row by row ...
    (month,) = [node for node in found if node.get("Relation Name") == names["month"]]
    assert month["Node Type"] == "Index Scan", month
    assert month["Index Name"] == f"{names['month']}_pkey", month
    for column in ("tenant_id", "occurred_at", "id"):
        assert f"({column} = " in month["Index Cond"], month
    assert "audit_event_contract.occurred_at" in month["Index Cond"], month
    # ... and the link drives: it is the outer side of the join that looks the events up — also
    # in the plan the planner prices freely, where the lateral lookup leaves it no other order.
    (join,) = [node for node in found if _driven_by_the_link(node)]
    assert any(node is month for node in nodes(join["Plans"][1]))
    unforced = list(nodes(plan(tenant_id, page, off=())))
    (natural,) = [node for node in unforced if _driven_by_the_link(node)]
    assert names["month"] in {node.get("Relation Name") for node in nodes(natural["Plans"][1])}

    items = answered.json()["items"]
    assert len(items) == 10
    assert all(contract in contract_key.named(item["detail"]) for item in items)
    sequences = [item["chain_seq"] for item in items]
    assert sequences == sorted(sequences, reverse=True)


def test_dg_lst_08_a_page_of_the_log_is_read_newest_first_from_the_chain_index(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """``GET /audit-events`` in its default order, ``-chain_seq``: the sequence is never NULL, so
    the list kernel orders it without ``NULLS LAST`` and the chain index of the month, read
    backwards, supplies the page. No node sorts the events of the range; the tie-breaker ``id``
    is ordered within one sequence only. With the clause no index order applied — a b-tree read
    backwards yields ``DESC NULLS FIRST`` — and every event of the range was sorted for a page of
    fifty."""
    app = create_app(app_settings, clock=clock)
    maya = _auditor(app, keyring, clock)
    tenant_id = maya.member.tenant_id
    system = system_principal(tenant_id)
    _write(
        tenant_id,
        keyring,
        clock,
        LocalFileStore(app_settings.file_root),
        [(system, {}) for _ in range(EVENTS)],
    )
    names = _analysed(test_database, clock, "ix_audit_event__chain")
    with sent() as seen:
        answered = _get(app, maya)
    assert answered.status_code == 200, answered.text
    (page,) = [read for read in reads(seen, "audit_event") if " LIMIT " in read[0]]
    assert "NULLS LAST" not in page[0].rsplit("ORDER BY", 1)[1], page[0][-200:]

    found = list(nodes(plan(tenant_id, page, off=(*FORCED, "enable_sort"))))
    assert _full_sorts(found) == [], _full_sorts(found)
    (month,) = [node for node in found if node.get("Relation Name") == names["month"]]
    assert month["Node Type"] == "Index Scan", month
    assert month["Index Name"] == names["ix_audit_event__chain"], month
    assert month["Scan Direction"] == "Backward", month
    for node in found:
        if node["Node Type"] == "Incremental Sort":
            assert node["Presorted Key"] == ["audit_event.chain_seq"], node

    items = answered.json()["items"]
    sequences = [item["chain_seq"] for item in items]
    assert len(items) == 50 and sequences == sorted(sequences, reverse=True)


def test_the_actors_of_a_range_are_read_one_index_probe_an_actor(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """``GET /audit-events/actors``: the statement walks ``ix_audit_event__actor`` from one actor
    to the next — each step an index condition ``actor_id > <the previous one>`` under the tenant —
    and never reads the month row by row, whatever the number of events."""
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    people = [maya_principal(colleague(tenant_id, name)) for name in ("ada", "ben", "cyd")]
    system = system_principal(tenant_id)
    events: list[tuple[Principal, dict[str, Any]]] = [
        (people[number % 3] if number % 5 == 0 else system, {}) for number in range(EVENTS)
    ]
    _write(tenant_id, keyring, clock, LocalFileStore(app_settings.file_root), events)
    names = _analysed(test_database, clock, "ix_audit_event__actor")
    statement = audit_log.actors_statement(
        clock.now() - timedelta(days=30), until=None, q=None, limit=101
    )

    scans = [
        node
        for node in nodes(plan(tenant_id, statement, off=()))
        if node.get("Relation Name") == names["month"]
    ]
    assert len(scans) == 2, scans  # the first actor, and the step to the next
    for node in scans:
        assert node["Node Type"] in ("Index Only Scan", "Index Scan"), node
        assert node["Index Name"] == names["ix_audit_event__actor"], node
        assert "tenant_id =" in node["Index Cond"], node
    first, following = sorted(scans, key=lambda node: "actor_id >" in node["Index Cond"])
    assert "actor_id IS NOT NULL" in first["Index Cond"], first
    assert "actor_id > previous.actor_id" in following["Index Cond"], following

    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        found = session.execute(statement).all()
    acted = {str(who.id) for who in people}
    assert acted <= {str(row.id) for row in found}  # and whoever set the workspace up
    assert len(found) <= len(acted) + 1


def _months(found: dict[str, Any]) -> list[str]:
    """The partitions of ``audit_event`` a plan reads, in order."""
    return sorted(
        {
            str(node["Relation Name"])
            for node in nodes(found)
            if str(node.get("Relation Name", "")).startswith("audit_event_p")
        }
    )


def test_audit_list_plan_1_a_read_plans_the_months_of_its_range(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """04 §16.14 rev 1.280 (item AUDIT-LIST-PLAN-1): a read of the log has an end as it has a
    start — ``to``, else one day after the request — so PostgreSQL plans the months of the
    range. Without the end a read of the last thirty days planned every monthly partition from
    its start to the last one created and the default: 77 of the table's 181 on 2026-10-02,
    where it reads two. The same for ``from`` without ``to`` and for the actors of the range.
    The clock stands on 12 September 2026: thirty days back is 13 August."""
    app = create_app(app_settings, clock=clock)
    maya = _auditor(app, keyring, clock)
    tenant_id = maya.member.tenant_id
    august, september = "audit_event_p202608", "audit_event_p202609"
    assert f"{clock.now():%Y%m}" == "202609"

    with sent() as seen:
        answered = _get(app, maya, limit="10")
    assert answered.status_code == 200, answered.text
    (page,) = [read for read in reads(seen, "audit_event") if " LIMIT " in read[0]]
    assert _months(plan(tenant_id, page, off=())) == [august, september]

    # `from` without `to`: from the month of `from` to the month of the request, no further.
    since = (clock.now() - timedelta(days=80)).isoformat()
    with sent() as seen:
        answered = _get(app, maya, limit="10", **{"from": since})
    assert answered.status_code == 200, answered.text
    (page,) = [read for read in reads(seen, "audit_event") if " LIMIT " in read[0]]
    assert _months(plan(tenant_id, page, off=())) == [
        "audit_event_p202606",
        "audit_event_p202607",
        august,
        september,
    ]

    # Who acted in the range: the same two months.
    with sent() as seen:
        answered = call(
            app, "GET", f"{AUDIT}/actors", headers=cookie_headers(maya.token, key=False)
        )
    assert answered.status_code == 200, answered.text
    (actors,) = [read for read in reads(seen, "audit_event") if "actor_id" in read[0]]
    assert _months(plan(tenant_id, actors, off=())) == [august, september]

    # A read by its sequence is one event of any age and takes no end: every month is planned.
    with sent() as seen:
        answered = _get(app, maya, chain_seq="1")
    assert answered.status_code == 200, answered.text
    (page,) = [read for read in reads(seen, "audit_event") if " LIMIT " in read[0]]
    assert len(_months(plan(tenant_id, page, off=()))) == 181
