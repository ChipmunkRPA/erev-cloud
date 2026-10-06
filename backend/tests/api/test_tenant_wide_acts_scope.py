"""The administration of the whole workspace under a role held for named entities (item
SCOPE-WORKSPACE-LISTS-1, part (c1); supervisor rulings R-28 and R-115 (c); 03 REQ-PLT-012,
REQ-PLT-036; 04 API-C-03, API-R-04, API-R-14, API-R-15, API-R-18, API-R-19, §16.10).

The tenant's settings and currencies, a close checklist template, a snapshot, a sandbox and its
reset, a webhook endpoint with the delivery log, and an operator's support grant belong to no
legal entity: each is an act on, or a list of, the whole workspace. Their permissions —
``settings.manage`` and ``support_grant.approve`` (Tenant Admin), ``tenant.snapshot`` and
``sandbox.reset`` (Controller), ``webhook.manage`` (Integration Admin) — are therefore asked for
ALL entities, and the request of an operator's grant spans every entity.

WLD-K-04 (``worlds.k04_saltmarsh``; AVM-UK and AVM-US). Every role here is granted through the
product — ``POST /role-assignments``, requested by Marcus and approved by Grace — for AVM-UK alone
or for all entities; a member holds one of the three roles, because the product refuses Tenant
Admin beside Controller on one person (SoD-1). Grace's own role is a row of the test world.

Measured before the item, with the same grants: the Tenant Admin of AVM-UK changed the tenant's
display name and currencies, created a close checklist template, requested a support grant and
approved another administrator's; the Controller of AVM-UK queued a snapshot of the workspace;
the Integration Admin of AVM-UK created a webhook endpoint and read the delivery log.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any, Final
from uuid import uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, role
from erev_api.enums import AuditOutcome
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.db import TestDatabase
from support.operators import create_operator, operator_services
from support.principals import Actor, colleague, enrolled
from support.reference import approve, get, patch, post, put
from support.worlds import AVM_UK
from tests.domain.reports.test_entity_scoped_runs_db import ASSIGNMENTS, scoped, second_admin

API: Final = "/api/v1"
TENANT: Final = f"{API}/tenant"
CURRENCIES: Final = f"{API}/tenant-currencies"
TEMPLATES: Final = f"{API}/close-checklist-templates"
TEMPLATE: Final = f"{API}/close-checklist-templates/{{template_id}}"
GRANTS: Final = f"{API}/support-grants"
REVOKE: Final = f"{API}/support-grants/{{support_grant_id}}/revoke"
SNAPSHOTS: Final = f"{API}/tenant/snapshots"
SNAPSHOT: Final = f"{API}/tenant/snapshots/{{tenant_snapshot_id}}"
MANIFEST: Final = f"{API}/tenant/snapshots/{{tenant_snapshot_id}}/manifest"
SANDBOXES: Final = f"{API}/tenant/sandboxes"
RESET: Final = f"{API}/tenant/reset"
ENDPOINTS: Final = f"{API}/webhook-endpoints"
ENDPOINT: Final = f"{API}/webhook-endpoints/{{endpoint_id}}"
DELIVERIES: Final = f"{API}/webhook-deliveries"
APPROVALS: Final = f"{API}/approvals"
# permission → the routes it guards for all entities: method, route template
TENANT_WIDE: Final[Mapping[str, Sequence[tuple[str, str]]]] = {
    "settings.manage": (
        ("GET", TENANT),
        ("PATCH", TENANT),
        ("PUT", CURRENCIES),
        ("POST", TEMPLATES),
        ("PATCH", TEMPLATE),
    ),
    "support_grant.approve": (("GET", GRANTS), ("POST", GRANTS), ("POST", REVOKE)),
    "tenant.snapshot": (
        ("GET", SNAPSHOTS),
        ("POST", SNAPSHOTS),
        ("GET", SNAPSHOT),
        ("GET", MANIFEST),
        ("POST", SANDBOXES),
    ),
    "sandbox.reset": (("POST", RESET),),
    "webhook.manage": (
        ("GET", ENDPOINTS),
        ("POST", ENDPOINTS),
        ("GET", ENDPOINT),
        ("PATCH", ENDPOINT),
        ("GET", DELIVERIES),
    ),
}
# the default role that holds each permission (04 T-PLT-11): one member per role
ROLE_OF: Final = {
    "settings.manage": "tenant_admin",
    "support_grant.approve": "tenant_admin",
    "tenant.snapshot": "controller",
    "sandbox.reset": "controller",
    "webhook.manage": "integration_admin",
}
REASON: Final = "Investigate the export failure of ticket SUP-2291"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def for_all_entities(
    world: worlds.ReportWorld, clock: FrozenClock, approver: Actor, name: str, role_code: str
) -> Actor:
    """A member holding ``role_code`` for all entities: Marcus requests, ``approver`` approves."""
    someone = colleague(world.tenant_id, name)
    role_id = world.place.scalar(select(role.c.id).where(role.c.code == role_code))
    granted = post(
        world.app,
        ASSIGNMENTS,
        world.marcus,
        {
            "membership_id": str(someone.membership_id),
            "role_id": str(role_id),
            "is_all_entities": True,
            "entity_codes": [],
        },
    )
    assert granted.status_code == 201, granted.text
    approved = approve(world.app, granted.json()["approval_request_id"], approver)
    assert approved.status_code == 200, approved.text
    return enrolled(world.app, clock, someone)


def slug(response: Any) -> str:
    """The problem slug of an answer; empty for an answer that is no problem."""
    body = response.json()
    return str(body.get("type", "")).rsplit("/", 1)[-1] if isinstance(body, dict) else ""


def asked(world: worlds.ReportWorld, actor: Actor, method: str, template: str) -> Any:
    """One request of a route by a caller its guard refuses: no body and no id is ever read."""
    path = template
    for name in ("template_id", "support_grant_id", "tenant_snapshot_id", "endpoint_id"):
        path = path.replace("{" + name + "}", str(uuid4()))
    if method == "GET":
        return get(world.app, path, actor)
    if method == "PUT":
        return put(world.app, path, actor, {})
    if method == "PATCH":
        return patch(world.app, path, actor, {}, if_match=None)
    return post(world.app, path, actor, {})


def denials(world: worlds.ReportWorld, permission: str) -> list[dict[str, Any]]:
    """The details of the DENIED events of ``permission``, oldest first."""
    rows = world.place.rows(
        select(audit_event.c.detail)
        .where(
            audit_event.c.action == permission,
            audit_event.c.outcome == AuditOutcome.DENIED.value,
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [dict(row["detail"]) for row in rows]


def grant_request(
    world: worlds.ReportWorld, keyring: KeyRing, clock: FrozenClock, settings: Settings
) -> dict[str, Any]:
    """The body of ``POST /support-grants`` for an operator created for it."""
    operator = create_operator(operator_services(keyring, clock, settings.file_root))
    now = clock.now()
    return {
        "operator_email": operator["email"],
        "reason": REASON,
        "ticket_ref": "SUP-2291",
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(days=1)).isoformat(),
    }


@pytest.mark.slow
def test_the_tenant_level_administration_is_for_holders_of_all_entities(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    app_settings: Settings,
) -> None:
    """Every route of the tenant's settings and currencies, the close checklist templates, the
    support grants, the snapshots, sandboxes and reset, and the webhooks answers the holder of
    its permission for AVM-UK alone 403 ``forbidden``, after one DENIED event that names the route
    and the scope it asks for; the holder for all entities is answered by the command itself.
    Before: every one of them answered the holder of one entity as it answers the other."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    grace = second_admin(world, clock)
    one_entity = {
        role_code: scoped(world, clock, grace, f"uk-{role_code[:4]}", (role_code, AVM_UK))
        for role_code in ("tenant_admin", "controller", "integration_admin")
    }

    for permission, routes in TENANT_WIDE.items():
        member = one_entity[ROLE_OF[permission]]
        for method, template in routes:
            refused = asked(world, member, method, template)
            assert (refused.status_code, slug(refused)) == (403, "forbidden"), (
                method,
                template,
                refused.text,
            )
        assert denials(world, permission) == [
            {"method": method, "path": template, "scope": "*", "permission": permission}
            for method, template in routes
        ]

    # The holders for all entities: each route answers with the command's own result.
    answered: dict[tuple[str, str], int] = {}
    # Tenant Admin (Grace): settings, currencies, templates, support grants
    shown = get(app, TENANT, grace)
    answered["GET", TENANT] = shown.status_code
    answered["PATCH", TENANT] = patch(
        app, TENANT, grace, {"display_name": "Saltmarsh Group"}, if_match=shown.headers["ETag"]
    ).status_code
    answered["PUT", CURRENCIES] = put(
        app, CURRENCIES, grace, {"currency_codes": ["GBP", "USD", "EUR"]}
    ).status_code
    template = post(
        app,
        TEMPLATES,
        grace,
        {"code": "RECON-BANK", "name": "Bank reconciliation signed", "gate_kind": "MANUAL"},
    )
    answered["POST", TEMPLATES] = template.status_code
    answered["PATCH", TEMPLATE] = patch(
        app,
        f"{TEMPLATES}/{template.json()['id']}",
        grace,
        {"description": "Signed by the Controller before the lock"},
        if_match=template.headers["ETag"],
    ).status_code
    answered["GET", GRANTS] = get(app, GRANTS, grace).status_code
    grant = post(app, GRANTS, grace, grant_request(world, keyring, clock, app_settings))
    answered["POST", GRANTS] = grant.status_code
    revoked = post(app, f"{GRANTS}/{grant.json()['id']}/revoke", grace, {"reason": REASON})
    answered["POST", REVOKE] = revoked.status_code
    # Controller: snapshots, sandboxes, reset
    cleo = for_all_entities(world, clock, grace, "cleo", "controller")
    answered["GET", SNAPSHOTS] = get(app, SNAPSHOTS, cleo).status_code
    snapshot = post(
        app, SNAPSHOTS, cleo, {"known_at": clock.now().isoformat(), "purpose": "STORED_BACKUP"}
    )
    answered["POST", SNAPSHOTS] = snapshot.status_code
    snapshot_id = snapshot.headers["X-Erev-Tenant-Snapshot-Id"]
    answered["GET", SNAPSHOT] = get(app, f"{SNAPSHOTS}/{snapshot_id}", cleo).status_code
    answered["GET", MANIFEST] = get(app, f"{SNAPSHOTS}/{snapshot_id}/manifest", cleo).status_code
    sandbox = post(app, SANDBOXES, cleo, {"tenant_snapshot_id": snapshot_id, "name": "Rehearsal"})
    answered["POST", SANDBOXES] = sandbox.status_code
    reset = post(app, RESET, cleo, {"mode": "EMPTY", "reason": "Rehearsal complete"})
    answered["POST", RESET] = reset.status_code
    # Integration Admin: webhooks
    ines = for_all_entities(world, clock, grace, "ines", "integration_admin")
    answered["GET", ENDPOINTS] = get(app, ENDPOINTS, ines).status_code
    endpoint = post(
        app,
        ENDPOINTS,
        ines,
        {"url": "https://hooks.example.test/erev", "event_kinds": ["period.locked"]},
    )
    answered["POST", ENDPOINTS] = endpoint.status_code
    endpoint_path = f"{ENDPOINTS}/{endpoint.json()['id']}"
    answered["GET", ENDPOINT] = get(app, endpoint_path, ines).status_code
    answered["PATCH", ENDPOINT] = patch(
        app,
        endpoint_path,
        ines,
        {"description": "Period locks to the consolidation tool"},
        if_match=endpoint.headers["ETag"],
    ).status_code
    answered["GET", DELIVERIES] = get(app, DELIVERIES, ines).status_code

    assert answered == {
        ("GET", TENANT): 200,
        ("PATCH", TENANT): 200,
        ("PUT", CURRENCIES): 200,
        ("POST", TEMPLATES): 201,
        ("PATCH", TEMPLATE): 200,
        ("GET", GRANTS): 200,
        ("POST", GRANTS): 201,
        # a grant still REQUESTED is not revoked: the command's own refusal, past the guard
        ("POST", REVOKE): 409,
        ("GET", SNAPSHOTS): 200,
        ("POST", SNAPSHOTS): 202,
        ("GET", SNAPSHOT): 200,
        # the snapshot's job has not run: no manifest yet, and nothing to load a sandbox from
        ("GET", MANIFEST): 404,
        ("POST", SANDBOXES): 412,
        # a production workspace is never reset: the command's refusal, past the guard
        ("POST", RESET): 409,
        ("GET", ENDPOINTS): 200,
        ("POST", ENDPOINTS): 201,
        ("GET", ENDPOINT): 200,
        ("PATCH", ENDPOINT): 200,
        ("GET", DELIVERIES): 200,
    }
    assert slug(revoked) == "invalid-transition" and slug(reset) == "production-reset-forbidden"
    # no denial but the one-entity members': one per route
    for permission, routes in TENANT_WIDE.items():
        assert len(denials(world, permission)) == len(routes), permission


@pytest.mark.slow
def test_an_operators_grant_is_decided_by_an_administrator_of_all_entities(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    app_settings: Settings,
) -> None:
    """04 §16.10: the request of a support grant spans every entity. Grace asks for an operator's
    access; Tia, Tenant Admin of AVM-UK alone, is neither listed the request nor answered it —
    404, as for a request outside her scope — and Marcus, Tenant Admin of all entities, approves
    it. Before: the request named no entity, any holder of ``support_grant.approve`` decided it,
    and Tia approved an operator's access to the whole workspace."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    grace = second_admin(world, clock)
    tia = scoped(world, clock, grace, "tia", ("tenant_admin", AVM_UK))

    requested = post(app, GRANTS, grace, grant_request(world, keyring, clock, app_settings))
    assert requested.status_code == 201, requested.text
    request_id = str(requested.json()["approval_request_id"])

    listed = get(app, APPROVALS, tia, {"limit": "200"})
    assert listed.status_code == 200, listed.text
    assert request_id not in {str(item["id"]) for item in listed.json()["items"]}
    hidden = get(app, f"{APPROVALS}/{request_id}", tia)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found")
    decided = post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        tia,
        {"subject_content_sha256": "0" * 64, "comment": "OK"},
    )
    assert (decided.status_code, slug(decided)) == (404, "not-found")

    shown = get(app, f"{APPROVALS}/{request_id}", world.marcus)
    assert shown.status_code == 200, shown.text
    assert shown.json()["can_decide"] is True
    approved = approve(app, request_id, world.marcus)
    assert approved.status_code == 200, approved.text
    grants = get(app, GRANTS, grace)
    assert [item["status"] for item in grants.json()["items"]] == ["APPROVED"]
