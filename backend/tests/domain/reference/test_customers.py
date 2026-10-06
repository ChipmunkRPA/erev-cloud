"""Customers and related-party groups (04 §15.3 API-R-22, §16.14, T-REF-18, T-REF-19, E-38; 03
REQ-REF-010, REQ-REF-011; PRD §2.7; SCREENS §9.4, §9.5, §9.8; BUILD_SPEC RFD-8).

Maya holds Revenue Accountant, which carries ``masterdata.maintain`` and ``contract.read``
(docs/02-PRD.md §5.6). The WLD-C customers of PRD §2.7 are created through ``POST /customers``.
The world does not assert customer codes (SCREENS §9.8), so the tests name them after their WLD ids.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, customer
from erev_api.domain.reference import customers
from erev_api.main import create_app
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from sqlalchemy import func, select
from support.db import TestDatabase
from support.http import call
from support.principals import Actor, cookie_headers, member
from support.reference import fields, get, holding, patch, post, slug

CUSTOMERS = "/api/v1/customers"
GROUPS = "/api/v1/related-party-groups"
KLINIKBEDARF = "Hollenbrand Klinikbedarf GmbH (Demo)"
MEDIZINTECHNIK = "Hollenbrand Medizintechnik GmbH (Demo)"
DROSSEL = "Drossel Fahrzeugtechnik GmbH (Demo)"
FENWRIGHT = "Fenwright Logistik AG (Demo)"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def tenant_context(actor: Actor) -> DbContext:
    return DbContext(tenant_id=actor.member.tenant_id, user_id=None, entity_scope="*")


def netsuite(external_id: str, **extra: Any) -> dict[str, Any]:
    """The NetSuite members of a German WLD customer (PRD §2.7)."""
    return {"country_code": "DE", "source_system": "NETSUITE", "external_id": external_id, **extra}


def new_customer(app: FastAPI, actor: Actor, code: str, name: str, **extra: Any) -> dict[str, Any]:
    created = post(app, CUSTOMERS, actor, {"code": code, "name": name, **extra})
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def new_group(
    app: FastAPI, actor: Actor, code: str = "HOLLENBRAND", name: str = "Hollenbrand (Demo)"
) -> dict[str, Any]:
    created = post(app, GROUPS, actor, {"code": code, "name": name})
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def listed(app: FastAPI, actor: Actor, path: str, **params: Any) -> list[dict[str, Any]]:
    response = get(app, path, actor, params)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def group_counts(app: FastAPI, actor: Actor) -> dict[str, int]:
    return {item["code"]: item["member_count"] for item in listed(app, actor, GROUPS)}


def audit_count(actor: Actor, action: str) -> int:
    with tenant_session(tenant_context(actor), read_only=True) as session:
        statement = (
            select(func.count()).select_from(audit_event).where(audit_event.c.action == action)
        )
        return int(session.execute(statement).scalar_one())


def test_external_id_unique_per_source_system(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    created = post(
        app, CUSTOMERS, maya, {"code": "C-05", "name": KLINIKBEDARF, **netsuite("C-DE-3001")}
    )
    assert created.status_code == 201, created.text
    klinik = created.json()
    assert created.headers["ETag"] == '"r1"'
    assert created.headers["Location"] == f"{CUSTOMERS}/{klinik['id']}"
    assert (
        klinik["name"],
        klinik["country_code"],
        klinik["source_system"],
        klinik["external_id"],
        klinik["is_active"],
    ) == (KLINIKBEDARF, "DE", "NETSUITE", "C-DE-3001", True)
    assert (klinik["related_party_group_id"], klinik["related_party_group"]) == (None, None)

    duplicate = post(
        app, CUSTOMERS, maya, {"code": "C-06", "name": DROSSEL, **netsuite("C-DE-3001")}
    )
    assert (duplicate.status_code, slug(duplicate)) == (422, "validation-failed"), duplicate.text
    assert fields(duplicate) == [("external_id", "T-REF-19")]
    assert duplicate.json()["errors"][0]["message"] == (
        "Another customer from NETSUITE already uses external id C-DE-3001."
    )

    salesforce = post(
        app,
        CUSTOMERS,
        maya,
        {"code": "C-06", "name": DROSSEL, **netsuite("C-DE-3001", source_system="SALESFORCE")},
    )
    assert salesforce.status_code == 201, salesforce.text
    assert (salesforce.json()["source_system"], salesforce.json()["external_id"]) == (
        "SALESFORCE",
        "C-DE-3001",
    )

    # Customers without an external id never collide; their channel is the principal's.
    for code in ("C-13", "C-14"):
        manual = new_customer(app, maya, code, f"Walk-in {code} (Demo)")
        assert (manual["source_system"], manual["external_id"]) == ("MANUAL_UI", None)

    both = listed(app, maya, CUSTOMERS, external_id="C-DE-3001", sort="code")
    assert [(item["code"], item["source_system"]) for item in both] == [
        ("C-05", "NETSUITE"),
        ("C-06", "SALESFORCE"),
    ]
    from_netsuite = listed(app, maya, CUSTOMERS, external_id="C-DE-3001", source_system="NETSUITE")
    assert [item["id"] for item in from_netsuite] == [klinik["id"]]
    unknown_source = get(app, CUSTOMERS, maya, {"source_system": "SAP"})
    assert (unknown_source.status_code, slug(unknown_source)) == (422, "validation-failed")
    assert audit_count(maya, "customer.create") == 4


def test_group_membership_and_count(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    created = post(
        app,
        GROUPS,
        maya,
        {"code": "HOLLENBRAND", "name": "Hollenbrand (Demo)", "description": "Common control."},
    )
    assert created.status_code == 201, created.text
    group = created.json()
    # API-R-22 has no GET /related-party-groups/{id}: the 201 carries an ETag but no Location.
    assert (created.headers["ETag"], "Location" in created.headers) == ('"r1"', False)
    assert (group["code"], group["description"], group["member_count"]) == (
        "HOLLENBRAND",
        "Common control.",
        0,
    )

    in_group = {"related_party_group_id": group["id"]}
    c05 = new_customer(app, maya, "C-05", KLINIKBEDARF, **netsuite("C-DE-3001", **in_group))
    c11 = new_customer(app, maya, "C-11", MEDIZINTECHNIK, **netsuite("C-DE-3004", **in_group))
    c06 = new_customer(app, maya, "C-06", DROSSEL, **netsuite("C-DE-3002"))
    assert c05["related_party_group"] == {
        "id": group["id"],
        "code": "HOLLENBRAND",
        "name": "Hollenbrand (Demo)",
    }
    assert c06["related_party_group"] is None
    assert [(item["code"], item["member_count"]) for item in listed(app, maya, GROUPS)] == [
        ("HOLLENBRAND", 2)
    ]

    # At most one group per customer: the member is a single id, and a list of groups is refused.
    assert isinstance(c11["related_party_group_id"], str)
    other = new_group(app, maya, code="KLINIK-NORD", name="Klinik Nord (Demo)")
    two = post(
        app,
        CUSTOMERS,
        maya,
        {
            "code": "C-15",
            "name": "Two groups (Demo)",
            "related_party_group_id": [group["id"], other["id"]],
        },
    )
    assert (two.status_code, slug(two)) == (422, "validation-failed"), two.text
    assert [field for field, _ in fields(two)] == ["related_party_group_id"]

    path = f"{CUSTOMERS}/{c11['id']}"
    moved = patch(app, path, maya, {"related_party_group_id": other["id"]}, if_match='"r1"')
    assert moved.status_code == 200, moved.text
    assert (moved.json()["related_party_group_id"], moved.headers["ETag"]) == (other["id"], '"r2"')
    assert group_counts(app, maya) == {"HOLLENBRAND": 1, "KLINIK-NORD": 1}
    unknown = patch(app, path, maya, {"related_party_group_id": str(uuid.uuid4())}, if_match='"r2"')
    assert fields(unknown) == [("related_party_group_id", "T-REF-19")]
    back = patch(app, path, maya, {"related_party_group_id": group["id"]}, if_match='"r2"')
    assert back.status_code == 200, back.text
    assert group_counts(app, maya) == {"HOLLENBRAND": 2, "KLINIK-NORD": 0}
    # A deactivated member still counts (L1-1-Q-39).
    deactivated = patch(
        app, f"{CUSTOMERS}/{c05['id']}", maya, {"is_active": False}, if_match='"r1"'
    )
    assert deactivated.status_code == 200, deactivated.text
    assert group_counts(app, maya)["HOLLENBRAND"] == 2

    with tenant_session(tenant_context(maya), read_only=True) as session:
        assert customers.related_customer_ids(session, uuid.UUID(c05["id"])) == [
            uuid.UUID(c11["id"])
        ]
        assert customers.related_customer_ids(session, uuid.UUID(c06["id"])) == []
        assert customers.related_customer_ids(session, uuid.uuid4()) == []


def test_filter_by_group_sorted_by_name(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    group = new_group(app, maya)
    in_group = {"related_party_group_id": group["id"]}
    # Created against name order, so the order comes from sort=name.
    new_customer(app, maya, "C-11", MEDIZINTECHNIK, **netsuite("C-DE-3004", **in_group))
    new_customer(app, maya, "C-07", FENWRIGHT, **netsuite("C-DE-3003"))
    new_customer(app, maya, "C-05", KLINIKBEDARF, **netsuite("C-DE-3001", **in_group))

    members = get(
        app,
        CUSTOMERS,
        maya,
        {"related_party_group_id": group["id"], "sort": "name", "count": "true"},
    )
    assert members.status_code == 200, members.text
    assert [item["name"] for item in members.json()["items"]] == [KLINIKBEDARF, MEDIZINTECHNIK]
    assert members.headers["X-Erev-Total-Count"] == "2"
    descending = listed(app, maya, CUSTOMERS, related_party_group_id=group["id"], sort="-name")
    assert [item["name"] for item in descending] == [MEDIZINTECHNIK, KLINIKBEDARF]
    assert [item["code"] for item in listed(app, maya, CUSTOMERS, sort="code")] == [
        "C-05",
        "C-07",
        "C-11",
    ]
    # The default order is by name; q searches code, name and external id.
    assert [item["code"] for item in listed(app, maya, CUSTOMERS)] == ["C-07", "C-05", "C-11"]
    assert [item["code"] for item in listed(app, maya, CUSTOMERS, q="hollenbrand")] == [
        "C-05",
        "C-11",
    ]
    assert [item["code"] for item in listed(app, maya, CUSTOMERS, q="DE-3003")] == ["C-07"]

    first = get(app, CUSTOMERS, maya, {"sort": "name", "limit": 2})
    assert [item["code"] for item in first.json()["items"]] == ["C-07", "C-05"]
    cursor = first.json()["next_cursor"]
    assert cursor is not None
    rest = listed(app, maya, CUSTOMERS, sort="name", limit=2, cursor=cursor)
    assert [item["code"] for item in rest] == ["C-11"]

    refused = get(app, CUSTOMERS, maya, {"sort": "country_code"})
    assert fields(refused) == [("sort", "API-C-09")]
    malformed = get(app, CUSTOMERS, maya, {"related_party_group_id": "HOLLENBRAND"})
    assert (malformed.status_code, slug(malformed)) == (422, "validation-failed")


def test_deactivate_instead_of_delete(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    salesforce = {"country_code": "US", "source_system": "SALESFORCE"}
    c01 = new_customer(
        app,
        maya,
        "C-01",
        "Pellworth Logistics Inc. (Demo)",
        external_id="001DEMO0001",
        **salesforce,
    )
    new_customer(
        app,
        maya,
        "C-02",
        "Marrowby Health Partners LLC (Demo)",
        external_id="001DEMO0002",
        **salesforce,
    )
    path = f"{CUSTOMERS}/{c01['id']}"

    # No DELETE route exists for customers or related-party groups (IM-M).
    methods = {
        method
        for route in iter_route_contexts(app.routes)
        if (route.path or "").startswith((CUSTOMERS, GROUPS))
        for method in route.methods or ()
    }
    assert methods == {"GET", "POST", "PATCH"}
    deleted = call(app, "DELETE", path, headers=cookie_headers(maya.token, maya.csrf_token))
    assert deleted.status_code == 405, deleted.text
    assert get(app, path, maya).status_code == 200

    deactivated = patch(app, path, maya, {"is_active": False}, if_match='"r1"')
    assert deactivated.status_code == 200, deactivated.text
    assert (deactivated.json()["is_active"], deactivated.headers["ETag"]) == (False, '"r2"')
    assert [item["code"] for item in listed(app, maya, CUSTOMERS, is_active="true")] == ["C-02"]
    assert [item["code"] for item in listed(app, maya, CUSTOMERS, is_active="false")] == ["C-01"]
    assert len(listed(app, maya, CUSTOMERS)) == 2

    # The customer is kept: it reads as inactive and can be reactivated.
    got = get(app, path, maya)
    assert (got.status_code, got.headers["ETag"], got.json()["is_active"]) == (200, '"r2"', False)
    with tenant_session(tenant_context(maya), read_only=True) as session:
        event = session.execute(
            select(audit_event.c.object_version, audit_event.c.before, audit_event.c.after).where(
                audit_event.c.action == "customer.update"
            )
        ).one()
        stored = session.execute(
            select(customer.c.is_active).where(customer.c.id == uuid.UUID(c01["id"]))
        ).scalar_one()
    assert tuple(event) == ("2", {"is_active": True}, {"is_active": False})
    assert stored is False
    reactivated = patch(app, path, maya, {"is_active": True}, if_match='"r2"')
    assert (reactivated.status_code, reactivated.headers["ETag"]) == (200, '"r3"')


def test_customer_findings(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    parent = new_customer(app, maya, "C-05", KLINIKBEDARF)

    # Every finding is listed, in field order.
    refused = post(
        app,
        CUSTOMERS,
        maya,
        {
            "code": "C-05",
            "name": " ",
            "related_party_group_id": str(uuid.uuid4()),
            "parent_customer_id": str(uuid.uuid4()),
            "country_code": "de",
            "source_system": "NETSUITE",
            "external_id": "  ",
        },
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [
        ("code", "T-REF-19"),
        ("name", "T-REF-19"),
        ("related_party_group_id", "T-REF-19"),
        ("parent_customer_id", "T-REF-19"),
        ("country_code", "T-REF-19"),
        ("external_id", "T-REF-19"),
    ]
    # SCREENS §9.5: "Customer code <code> is already used."
    assert refused.json()["errors"][0]["message"] == "Customer code C-05 is already used."
    malformed = post(app, CUSTOMERS, maya, {"code": "-C", "name": "Malformed (Demo)"})
    assert fields(malformed) == [("code", "T-REF-19")]
    contact = post(app, CUSTOMERS, maya, {"code": "C-99", "name": "X", "email": "a@b.test"})
    assert (contact.status_code, [field for field, _ in fields(contact)]) == (422, ["email"])

    # A parent and the optional members are stored; a blank segment is none.
    child = new_customer(
        app,
        maya,
        "C-05-NORD",
        "Hollenbrand Klinikbedarf Nord (Demo)",
        parent_customer_id=parent["id"],
        credit_grade=" A ",
        segment=" ",
        country_code="DE",
    )
    assert (
        child["parent_customer_id"],
        child["credit_grade"],
        child["segment"],
        child["country_code"],
    ) == (parent["id"], "A", None, "DE")
    assert audit_count(maya, "customer.create") == 2


def test_update_customer_requires_if_match(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    parent = new_customer(app, maya, "C-05", KLINIKBEDARF, **netsuite("C-DE-3001"))
    child = new_customer(app, maya, "C-11", MEDIZINTECHNIK, parent_customer_id=parent["id"])
    path = f"{CUSTOMERS}/{parent['id']}"
    change = {"code": "C-DE-05", "segment": "Healthcare", "credit_grade": "B+"}

    missing = patch(app, path, maya, change, if_match=None)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    stale = patch(app, path, maya, change, if_match='"r7"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    changed = patch(app, path, maya, change, if_match='"r1"')
    assert changed.status_code == 200, changed.text
    assert changed.headers["ETag"] == '"r2"'
    body = changed.json()
    assert (body["code"], body["segment"], body["credit_grade"], body["external_id"]) == (
        "C-DE-05",
        "Healthcare",
        "B+",
        "C-DE-3001",
    )

    # A loop of parents is refused, as is the customer as its own parent.
    loop = patch(app, path, maya, {"parent_customer_id": child["id"]}, if_match='"r2"')
    assert fields(loop) == [("parent_customer_id", "T-REF-19")]
    own = patch(app, path, maya, {"parent_customer_id": parent["id"]}, if_match='"r2"')
    assert fields(own) == [("parent_customer_id", "T-REF-19")]
    taken = patch(app, path, maya, {"code": "C-11"}, if_match='"r2"')
    assert fields(taken) == [("code", "T-REF-19")]
    blank = patch(app, path, maya, {"name": None, "is_active": None}, if_match='"r2"')
    assert fields(blank) == [("name", "T-REF-19"), ("is_active", "T-REF-19")]
    for member_name, value in (("source_system", "SALESFORCE"), ("external_id", "C-DE-9999")):
        frozen = patch(app, path, maya, {member_name: value}, if_match='"r2"')
        assert (frozen.status_code, [field for field, _ in fields(frozen)]) == (422, [member_name])
    unknown = patch(
        app, f"{CUSTOMERS}/{uuid.uuid4()}", maya, {"segment": "Retail"}, if_match='"r1"'
    )
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    assert get(app, f"{CUSTOMERS}/{uuid.uuid4()}", maya).status_code == 404

    # An unchanged request writes nothing; removing the parent works.
    unchanged = patch(app, path, maya, {"segment": "Healthcare"}, if_match='"r2"')
    assert (unchanged.status_code, unchanged.headers["ETag"]) == (200, '"r2"')
    orphan = patch(
        app, f"{CUSTOMERS}/{child['id']}", maya, {"parent_customer_id": None}, if_match='"r1"'
    )
    assert (orphan.status_code, orphan.json()["parent_customer_id"]) == (200, None)

    with tenant_session(tenant_context(maya), read_only=True) as session:
        events = session.execute(
            select(audit_event.c.object_version, audit_event.c.before, audit_event.c.after)
            .where(audit_event.c.action == "customer.update")
            .order_by(audit_event.c.occurred_at, audit_event.c.object_version)
        ).all()
    assert [tuple(event) for event in events] == [
        (
            "2",
            {"code": "C-05", "credit_grade": None, "segment": None},
            {"code": "C-DE-05", "credit_grade": "B+", "segment": "Healthcare"},
        ),
        ("2", {"parent_customer_id": parent["id"]}, {"parent_customer_id": None}),
    ]


def test_related_party_group_rules(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    group = new_group(app, maya)
    duplicate = post(app, GROUPS, maya, {"code": "HOLLENBRAND", "name": " "})
    assert (duplicate.status_code, slug(duplicate)) == (422, "validation-failed"), duplicate.text
    assert fields(duplicate) == [("code", "T-REF-18"), ("name", "T-REF-18")]

    path = f"{GROUPS}/{group['id']}"
    rename = {"name": "Hollenbrand Holding (Demo)", "description": "Common control."}
    missing = patch(app, path, maya, rename, if_match=None)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    stale = patch(app, path, maya, rename, if_match='"r9"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    renamed = patch(app, path, maya, rename, if_match='"r1"')
    assert renamed.status_code == 200, renamed.text
    assert renamed.headers["ETag"] == '"r2"'
    assert (
        renamed.json()["name"],
        renamed.json()["description"],
        renamed.json()["member_count"],
    ) == ("Hollenbrand Holding (Demo)", "Common control.", 0)
    cleared = patch(app, path, maya, {"description": None}, if_match='"r2"')
    assert (cleared.status_code, cleared.json()["description"]) == (200, None), cleared.text

    new_group(app, maya, code="KLINIK-NORD", name="Klinik Nord (Demo)")
    null_code = patch(app, path, maya, {"code": None}, if_match='"r3"')
    assert fields(null_code) == [("code", "T-REF-18")]
    taken = patch(app, path, maya, {"code": "KLINIK-NORD"}, if_match='"r3"')
    assert fields(taken) == [("code", "T-REF-18")]
    unknown = patch(app, f"{GROUPS}/{uuid.uuid4()}", maya, {"name": "Other"}, if_match='"r1"')
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    assert [item["code"] for item in listed(app, maya, GROUPS, q="nord")] == ["KLINIK-NORD"]
    assert [item["name"] for item in listed(app, maya, GROUPS, sort="name")] == [
        "Hollenbrand Holding (Demo)",
        "Klinik Nord (Demo)",
    ]
    assert audit_count(maya, "related_party_group.create") == 2
    assert audit_count(maya, "related_party_group.update") == 2
