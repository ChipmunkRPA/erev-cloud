"""An API client's scopes are an access grant (supervisor ruling R-38 (iii); 03 REQ-PLT-033 rev
1.83; PRD §2.5 routing row of the access subjects, ACT-46 rev 1.97; 04 E-103, T-PLT-15 "Grant and
secret" and §16.10 rev 1.168; dev-guide DG-KRN-PERM-04 rev 1.151; control CTL-037).

A Tenant Admin holds no finance permission by design, and a client with ``import.upload`` or
``event.record`` is that permission under another name. So ``POST /api-clients`` writes the client
``PENDING_APPROVAL`` and submits its scopes for approval under the routing of ``ROLE_ASSIGNMENT``:
another holder of ``access.approve`` decides, the client cannot authenticate before, and its
secret is issued after the approval — by rotate-secret, to a holder of ``api_client.manage``; the
approver never sees one. Rule ``AUTO-BOOTSTRAP`` approves the request at once for the bootstrap
Tenant Admin during setup, as it does a role assignment, and only then does the creation return
the secret.

Tomas is the bootstrap Tenant Admin of a workspace in setup. Grace, a second Tenant Admin, ends
the bootstrap exception by existing (rulings R-66 (2), R-73).
"""

from __future__ import annotations

import base64
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals.engine import SELF_APPROVAL_DETAIL
from erev_api.auth import api_clients
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    approval_decision,
    approval_request,
    audit_event,
    fiscal_calendar,
    legal_entity,
    tenant,
)
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, colleague, enrolled, member, step_up
from support.reference import (
    APPROVALS,
    PERIODS,
    approve,
    assign,
    calendar,
    entity,
    get,
    periods,
    post,
    reject,
    slug,
)
from support.rows import fiscal_calendar_values, legal_entity_values

CLIENTS = "/api/v1/api-clients"
FILES = "/api/v1/files"
TOKEN_PATH = "/api/v1/oauth/token"
SCOPES = ["contract.create", "contract.read", "import.upload"]
REASON = "Integration retired in September"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def tomas(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    """The bootstrap Tenant Admin of a workspace in setup, enrolled (a fresh step-up)."""
    someone = member(keyring, clock, name="tomas")
    assign(someone, "tenant_admin")
    return enrolled(app, clock, someone)


def admin(app: FastAPI, clock: FrozenClock, tomas: Actor, name: str) -> Actor:
    """Another Tenant Admin of Tomas's workspace: a second access approver from now on."""
    someone = colleague(tomas.member.tenant_id, name)
    assign(someone, "tenant_admin")
    return enrolled(app, clock, someone)


def requested(app: FastAPI, actor: Actor, name: str = "svc-salesforce") -> dict[str, Any]:
    created = post(app, CLIENTS, actor, {"name": name, "scopes": SCOPES})
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def shown(app: FastAPI, actor: Actor, client_row_id: str) -> dict[str, Any]:
    found = get(app, f"{CLIENTS}/{client_row_id}", actor)
    assert found.status_code == 200, found.text
    body: dict[str, Any] = found.json()
    return body


def token_request(app: FastAPI, client_id: str, client_secret: str) -> HttpResponse:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("ascii")).decode("ascii")
    return call(
        app,
        "POST",
        TOKEN_PATH,
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {credentials}"},
    )


def refusal(response: HttpResponse) -> tuple[int, str, Any, str | None]:
    """What a refused token request tells its caller: status, slug, detail and the challenge."""
    return (
        response.status_code,
        slug(response),
        response.json()["detail"],
        response.headers.get("WWW-Authenticate"),
    )


def audited(tenant_id: UUID, client_row_id: str) -> list[tuple[str, Any, Any]]:
    """(action, after.status, approval_request_id) of the client's audit events, in order."""
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(
            select(audit_event.c.action, audit_event.c.after, audit_event.c.approval_request_id)
            .where(
                audit_event.c.object_type == "api_client",
                audit_event.c.object_id == UUID(client_row_id),
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (str(action), (after or {}).get("status"), None if request is None else str(request))
        for action, after, request in rows
    ]


@pytest.mark.control("CTL-037")
def test_r38_a_client_takes_effect_only_after_another_person_approves(
    app: FastAPI, clock: FrozenClock, tomas: Actor
) -> None:
    """Grace exists, so nothing is approved by rule any more. Tomas requests ``svc-salesforce``:
    201 with the client ``PENDING_APPROVAL``, no secret, and the request another access approver
    decides. The request is a ``ROLE_ASSIGNMENT`` over every entity whose preview shows the
    scopes. Until Grace approves, no secret can be issued and the client cannot authenticate;
    after, it is ``ACTIVE`` without a secret — still unable to authenticate — until Tomas issues
    the first one under step-up, which then obtains a token. The approver saw no secret.

    Fail-first: before the ruling the creation answered an ``ACTIVE`` client with its secret, on
    the requester's authority alone."""
    tenant_id = tomas.member.tenant_id
    grace = admin(app, clock, tomas, "grace")
    client = requested(app, tomas)
    assert (client["status"], client["client_secret"]) == ("PENDING_APPROVAL", None)
    assert client["has_secret"] is False
    assert client["secret_rotated_at"] is None
    request_id = client["approval_request_id"]
    assert request_id is not None

    request = get(app, f"{APPROVALS}/{request_id}", grace)
    assert request.status_code == 200, request.text
    seen = request.json()
    assert (seen["subject"]["type"], seen["status"], seen["all_entities"], seen["can_decide"]) == (
        "ROLE_ASSIGNMENT",
        "PENDING",
        True,
        True,
    )
    assert seen["summary"] == "Grant API client svc-salesforce its scopes for all entities"
    assert seen["preparer"]["id"] == str(tomas.member.user_id)
    # The approver reads the proposal where a request shows what it puts in force: its stored
    # preview (API-S-Approval names the file; the document is the file's content).
    document = get(app, f"{FILES}/{seen['impact_preview']['file_id']}/content", grace)
    assert document.status_code == 200, document.text
    proposal = document.json()["after"]
    assert (proposal["object_type"], proposal["api_client_id"], proposal["scopes"]) == (
        "api_client",
        client["id"],
        SCOPES,
    )
    assert "client_secret" not in proposal and "secret_hash" not in proposal

    # Pending: no secret is issued, the client is not revoked — the request is withdrawn instead.
    early = post(app, f"{CLIENTS}/{client['id']}/rotate-secret", tomas, {})
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    assert early.json()["detail"] == api_clients.WAITING_FOR_APPROVAL
    revoked = post(app, f"{CLIENTS}/{client['id']}/revoke", tomas, {"reason": REASON})
    assert (revoked.status_code, slug(revoked)) == (409, "invalid-transition"), revoked.text

    decided = approve(app, request_id, grace)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    assert "client_secret" not in decided.text
    active = shown(app, tomas, client["id"])
    assert (active["status"], active["has_secret"], active["secret_rotated_at"]) == (
        "ACTIVE",
        False,
        None,
    )
    assert active["approval_request_id"] == request_id

    # Tomas issues the first secret, under step-up; it is shown once and authenticates.
    clock.advance(timedelta(minutes=6))
    stale = post(app, f"{CLIENTS}/{client['id']}/rotate-secret", tomas, {})
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text
    fresh = step_up(app, clock, tomas)
    issued = post(app, f"{CLIENTS}/{client['id']}/rotate-secret", fresh, {})
    assert issued.status_code == 200, issued.text
    first = issued.json()
    assert (first["status"], first["has_secret"]) == ("ACTIVE", True)
    assert first["secret_rotated_at"] is not None and first["client_secret"]
    granted = token_request(app, client["client_id"], first["client_secret"])
    assert granted.status_code == 200, granted.text
    assert granted.json()["scope"].split() == SCOPES

    assert audited(tenant_id, client["id"]) == [
        ("api_client.create", "PENDING_APPROVAL", None),
        ("api_client.activate", "ACTIVE", request_id),
        ("api_client.rotate_secret", None, None),
    ]


@pytest.mark.control("CTL-037")
def test_r38_the_requester_cannot_approve_their_own_client(
    app: FastAPI, clock: FrozenClock, tomas: Actor
) -> None:
    """The witness that matters most (the supervisor's answer (f)): Tomas holds ``access.approve``
    himself, and his own approval of the client he requested is refused — 403 ``self-approval`` —
    with nothing decided and the client still pending. Grace, who holds the same role, approves
    it; and what Grace requests, Tomas approves."""
    grace = admin(app, clock, tomas, "grace")
    client = requested(app, tomas)
    assert (client["status"], client["client_secret"]) == ("PENDING_APPROVAL", None)
    request_id = client["approval_request_id"]
    waiting = get(app, f"{APPROVALS}/{request_id}", tomas)
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["can_decide"] is False

    own = approve(app, request_id, tomas)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    assert own.json()["detail"] == SELF_APPROVAL_DETAIL
    ctx = DbContext(tenant_id=tomas.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        decisions = session.execute(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == UUID(request_id)
            )
        ).all()
        status = session.execute(
            select(api_client.c.status).where(api_client.c.id == UUID(client["id"]))
        ).scalar_one()
    assert (decisions, str(status)) == ([], "PENDING_APPROVAL")

    # Positive controls: the other approver decides, both ways round.
    assert approve(app, request_id, grace).status_code == 200
    assert shown(app, tomas, client["id"])["status"] == "ACTIVE"
    hers = requested(app, grace, "svc-netsuite")
    assert hers["status"] == "PENDING_APPROVAL"
    assert approve(app, hers["approval_request_id"], tomas).status_code == 200
    assert shown(app, grace, hers["id"])["status"] == "ACTIVE"


@pytest.mark.control("CTL-037")
def test_r38_a_pending_client_answers_the_token_endpoint_as_an_unknown_client(
    app: FastAPI, clock: FrozenClock, tomas: Actor
) -> None:
    """A pending client's token request tells its caller exactly what an unknown client's does —
    the same status, slug, detail and challenge — whatever secret is sent; so does an approved
    client before its first secret is issued, and a rejected one."""
    grace = admin(app, clock, tomas, "grace")
    client = requested(app, tomas)
    assert (client["status"], client["client_secret"]) == ("PENDING_APPROVAL", None)
    tenant_hex = tomas.member.tenant_id.hex
    unknown = refusal(token_request(app, f"erevc_{tenant_hex}_{'A' * 22}", "guess"))
    assert unknown[:2] == (401, "unauthenticated") and unknown[3] is not None

    assert refusal(token_request(app, client["client_id"], "guess")) == unknown
    assert approve(app, client["approval_request_id"], grace).status_code == 200
    assert refusal(token_request(app, client["client_id"], "guess")) == unknown  # no secret yet

    other = requested(app, tomas, "svc-metering")
    refused = reject(app, other["approval_request_id"], grace, "Not needed this quarter.")
    assert refused.status_code == 200, refused.text
    assert refusal(token_request(app, other["client_id"], "guess")) == unknown


def test_r38_a_rejected_or_withdrawn_request_leaves_the_client_rejected(
    app: FastAPI, clock: FrozenClock, tomas: Actor
) -> None:
    """A rejection by the approver and a withdrawal by the requester both leave the client
    ``REJECTED``: the grant never took effect, no secret can be issued for it, and the audit trail
    names the request that closed it."""
    tenant_id = tomas.member.tenant_id
    grace = admin(app, clock, tomas, "grace")
    first = requested(app, tomas)
    assert (first["status"], first["client_secret"]) == ("PENDING_APPROVAL", None)
    refused = reject(app, first["approval_request_id"], grace, "Scopes too wide.")
    assert refused.status_code == 200, refused.text
    rejected = shown(app, tomas, first["id"])
    assert (rejected["status"], rejected["has_secret"]) == ("REJECTED", False)
    late = post(app, f"{CLIENTS}/{first['id']}/rotate-secret", tomas, {})
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text
    assert late.json()["detail"] == api_clients.REQUEST_REJECTED
    assert audited(tenant_id, first["id"]) == [
        ("api_client.create", "PENDING_APPROVAL", None),
        ("api_client.reject", "REJECTED", first["approval_request_id"]),
    ]

    second = requested(app, tomas, "svc-netsuite")
    withdrawn = post(
        app,
        f"{APPROVALS}/{second['approval_request_id']}/withdraw",
        tomas,
        {"comment": "Wrong scopes."},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert shown(app, tomas, second["id"])["status"] == "REJECTED"
    listed = get(app, CLIENTS, tomas, {"status": "REJECTED"})
    assert listed.status_code == 200, listed.text
    assert sorted(item["name"] for item in listed.json()["items"]) == [
        "svc-netsuite",
        "svc-salesforce",
    ]


def test_r38_the_bootstrap_admin_in_setup_gets_the_client_and_its_secret_at_once(
    app: FastAPI, tomas: Actor
) -> None:
    """PRD BR-PLT-02: a new workspace has no second approver. While Tomas is alone, rule
    ``AUTO-BOOTSTRAP`` approves the grant as it approves his role assignments: the creation
    answers ``ACTIVE`` with the secret, which authenticates at once, and the request shows the
    rule, not a person."""
    client = requested(app, tomas)
    assert (client["status"], client["has_secret"]) == ("ACTIVE", True)
    assert client["client_secret"] and client["secret_rotated_at"] == client["created_at"]
    assert token_request(app, client["client_id"], client["client_secret"]).status_code == 200
    ctx = DbContext(tenant_id=tomas.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        request = (
            session.execute(
                select(approval_request.c.status, approval_request.c.subject_type).where(
                    approval_request.c.id == UUID(client["approval_request_id"])
                )
            )
            .mappings()
            .one()
        )
        decisions = session.execute(
            select(approval_decision.c.decision, approval_decision.c.approver_id).where(
                approval_decision.c.approval_request_id == UUID(client["approval_request_id"])
            )
        ).all()
    assert (str(request["status"]), str(request["subject_type"])) == ("APPROVED", "ROLE_ASSIGNMENT")
    assert [(str(decision), approver) for decision, approver in decisions] == [
        ("AUTO_APPROVE", None)
    ]
    assert [action for action, _, _ in audited(tomas.member.tenant_id, client["id"])] == [
        "api_client.create",
        "api_client.activate",
    ]


def test_apr_setup_rule_2_a_client_requested_when_setup_completion_is_due_waits_for_a_person(
    app: FastAPI, tomas: Actor, clock: FrozenClock
) -> None:
    """Item APR-SETUP-RULE-2 for the second submitter of the subject (04 T-PLT-01 rev 1.224;
    dev-guide DG-KRN-APR-08): rule ``AUTO-BOOTSTRAP`` ends when the conditions of PRD BR-PLT-02
    hold, for the scopes of an API client as for a role. A period is open, and the preparing and
    the approving permission are held by two people whose roles are written as a seed would write
    them: no command has evaluated setup since, so the stamp is not set. Tomas's client waits for
    a person — ``PENDING_APPROVAL``, no secret — and his command sets the stamp.

    Positive control: ``test_r38_the_bootstrap_admin_in_setup_gets_the_client_and_its_secret_at_
    once``, the same request while the conditions do not hold.

    Fail-first: the grant was routed on the stamp alone, and the rule approved it."""
    tenant_id = tomas.member.tenant_id
    entity(app, tomas, code="AVM-US", calendar_id=calendar(app, tomas))
    first = periods(app, tomas, entity="AVM-US")[0]
    opened = post(app, f"{PERIODS}/{first['id']}/open", tomas, {}, if_match='"r1"')
    assert opened.status_code == 200, opened.text
    assign(colleague(tenant_id, "maya"), "revenue_accountant")
    assign(colleague(tenant_id, "priya"), "revenue_reviewer")

    def completed_at() -> Any:
        ctx = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(ctx, read_only=True) as session:
            return session.execute(
                select(tenant.c.setup_completed_at).where(tenant.c.id == tenant_id)
            ).scalar_one()

    assert completed_at() is None, "no command has evaluated setup since the roles were written"
    clock.advance(timedelta(seconds=60))
    client = requested(app, tomas)
    assert (client["status"], client["client_secret"]) == ("PENDING_APPROVAL", None)
    assert client["has_secret"] is False
    assert completed_at() == clock.now()
    assert [action for action, _, _ in audited(tenant_id, client["id"])] == ["api_client.create"]


# --- the entities of a client (item API-CLIENT-ENTITY-SCOPE-1) -----------------------------------


@pytest.fixture
def entities(tomas: Actor) -> dict[str, UUID]:
    """Two legal entities of Tomas's workspace, ENT-A and ENT-B."""
    tenant_id = tomas.member.tenant_id
    found: dict[str, UUID] = {}
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        calendar = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        for key in "AB":
            row = legal_entity_values(tenant_id, calendar_id=calendar["id"], code=f"ENT-{key}")
            session.execute(insert(legal_entity).values(**row))
            found[key] = UUID(str(row["id"]))
    return found


def named(app: FastAPI, actor: Actor, name: str, *codes: str) -> HttpResponse:
    """``POST /api-clients`` for the named entities."""
    return post(
        app,
        CLIENTS,
        actor,
        {"name": name, "scopes": SCOPES, "is_all_entities": False, "entity_codes": list(codes)},
    )


def findings(response: HttpResponse) -> list[tuple[str, str, str]]:
    return [
        (error["field"], error["rule_id"], error["message"]) for error in response.json()["errors"]
    ]


def stored_clients(tenant_id: UUID) -> dict[str, tuple[bool, list[str], str]]:
    """name → (is_all_entities, entity ids, status) of every client row of the workspace."""
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(
            select(
                api_client.c.name,
                api_client.c.is_all_entities,
                api_client.c.entity_ids,
                api_client.c.status,
            )
        ).all()
    return {
        str(name): (bool(everywhere), [str(value) for value in ids], str(status))
        for name, everywhere, ids, status in rows
    }


def test_api_client_entity_scope_1_a_client_is_granted_for_entities_its_creator_covers(
    app: FastAPI, clock: FrozenClock, tomas: Actor, entities: dict[str, UUID]
) -> None:
    """Item API-CLIENT-ENTITY-SCOPE-1 (04 T-PLT-10 "Entity scope of a grant" and T-PLT-15 rev
    1.168). ``POST /api-clients`` refused every entity code, so a client covered all entities or
    did not exist. It takes them through the one resolver a role grant uses, with the creator's
    own ``api_client.manage`` scope:

    - a client for ENT-A holds that entity's id, and its request is bound to ENT-A, names it in
      its summary, and is decided by an approver of access for ENT-A;
    - the setup rule ends per request (reading B): Dana has approved access for ENT-A, so Tomas's
      client for ENT-A waits for her, while his client for ENT-B — which nobody else covers — is
      approved by the rule and returns its secret;
    - Dana administers ENT-A only: her client for ENT-A is requested and Tomas decides it; a
      client for ENT-B answers her exactly as one for an entity that does not exist, a client
      for all entities is refused by name, and none of the three is stored."""
    tenant_id = tomas.member.tenant_id
    a, b = entities["A"], entities["B"]
    someone = colleague(tenant_id, "dana")
    assign(someone, "tenant_admin", entity_ids=[a])
    dana = enrolled(app, clock, someone)

    # Tomas, for ENT-A: waits for Dana, who approves access for ENT-A.
    for_a = named(app, tomas, "svc-a", "ENT-A")
    assert for_a.status_code == 201, for_a.text
    client = for_a.json()
    assert (
        client["status"],
        client["is_all_entities"],
        client["entity_ids"],
        client["client_secret"],
    ) == ("PENDING_APPROVAL", False, [str(a)], None)
    request_id = str(client["approval_request_id"])
    request = get(app, f"{APPROVALS}/{request_id}", dana)
    assert request.status_code == 200, request.text
    assert (
        [ref["code"] for ref in request.json()["entities"]],
        request.json()["entity_count"],
        request.json()["summary"],
        request.json()["can_decide"],
    ) == (["ENT-A"], 1, "Grant API client svc-a its scopes for ENT-A", True)
    approved = approve(app, request_id, dana)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    assert shown(app, tomas, client["id"])["status"] == "ACTIVE"

    # Tomas, for ENT-B: nobody else has approved access for ENT-B, so the setup rule decides.
    for_b = named(app, tomas, "svc-b", "ENT-B")
    assert for_b.status_code == 201, for_b.text
    assert (
        for_b.json()["status"],
        for_b.json()["entity_ids"],
        isinstance(for_b.json()["client_secret"], str),
    ) == ("ACTIVE", [str(b)], True)
    # ... and for both entities: no ONE other person covers the two.
    for_both = named(app, tomas, "svc-ab", "ENT-B", "ENT-A")
    assert for_both.status_code == 201, for_both.text
    assert (for_both.json()["status"], for_both.json()["entity_ids"]) == (
        "ACTIVE",
        [str(a), str(b)],
    )

    # Dana, for her own entity: requested, and decided by another approver of access for it.
    own = named(app, dana, "svc-dana", "ENT-A")
    assert own.status_code == 201, own.text
    assert (own.json()["status"], own.json()["entity_ids"]) == ("PENDING_APPROVAL", [str(a)])
    hers = str(own.json()["approval_request_id"])
    refused = approve(app, hers, dana)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    decided = approve(app, hers, tomas)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text

    # Dana, beyond her own scope: as an entity that does not exist; all entities by name.
    outside = named(app, dana, "svc-outside", "ENT-B")
    unknown = named(app, dana, "svc-unknown", "ENT-Z")
    for answer in (outside, unknown):
        assert (answer.status_code, slug(answer)) == (422, "validation-failed"), answer.text
        assert findings(answer) == [
            ("entity_codes", "EREV-REF-002", "Choose entities that exist in this workspace.")
        ]
    assert {**outside.json(), "instance": None} == {**unknown.json(), "instance": None}
    everywhere = post(app, CLIENTS, dana, {"name": "svc-everywhere", "scopes": SCOPES})
    assert (everywhere.status_code, slug(everywhere)) == (422, "validation-failed")
    assert findings(everywhere) == [
        (
            "is_all_entities",
            "T-PLT-15",
            "Your own access covers named entities only. Choose from those entities, not all "
            "entities.",
        )
    ]
    neither = post(
        app, CLIENTS, dana, {"name": "svc-none", "scopes": SCOPES, "is_all_entities": False}
    )
    assert findings(neither) == [
        ("entity_codes", "T-PLT-15", "Choose at least one entity, or all entities.")
    ]
    assert stored_clients(tenant_id) == {
        "svc-a": (False, [str(a)], "ACTIVE"),
        "svc-b": (False, [str(b)], "ACTIVE"),
        "svc-ab": (False, [str(a), str(b)], "ACTIVE"),
        "svc-dana": (False, [str(a)], "ACTIVE"),
    }


# --- reads and commands within the actor's entities (item API-CLIENT-COMMANDS-SCOPE-1) ----------


def denials(tenant_id: UUID) -> list[tuple[str, str | None, UUID | None, dict[str, Any]]]:
    """(action, client row id, actor, detail) of the ``DENIED`` audit events of API clients."""
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.object_id,
                audit_event.c.actor_id,
                audit_event.c.detail,
            )
            .where(audit_event.c.object_type == "api_client", audit_event.c.outcome == "DENIED")
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (str(action), None if object_id is None else str(object_id), actor_id, dict(detail))
        for action, object_id, actor_id, detail in rows
    ]


def secret_issued_at(tenant_id: UUID, client_row_id: str) -> Any:
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        return session.execute(
            select(api_client.c.secret_rotated_at).where(api_client.c.id == UUID(client_row_id))
        ).scalar_one()


def listed(app: FastAPI, actor: Actor) -> list[str]:
    """The names of the clients ``GET /api-clients`` answers the actor, in name order."""
    found = get(app, CLIENTS, actor, {"sort": "name"})
    assert found.status_code == 200, found.text
    return [str(item["name"]) for item in found.json()["items"]]


def told(response: HttpResponse) -> tuple[int, dict[str, Any]]:
    """What an answer tells its caller: the status and the body without the request's own id."""
    return response.status_code, {**response.json(), "instance": None}


def test_api_client_commands_scope_1_a_client_is_read_and_commanded_within_its_entities(
    app: FastAPI, clock: FrozenClock, tomas: Actor, entities: dict[str, UUID]
) -> None:
    """Item API-CLIENT-COMMANDS-SCOPE-1 (04 T-PLT-10 and T-PLT-15 rev 1.278; 03 REQ-PLT-012;
    the supervisor's rulings of 2026-10-02). The secret of a client is a credential for the
    client's entities, so a client is listed, read, given a secret and revoked only by a holder
    of ``api_client.manage`` for every entity it names — for all entities when it covers all.

    Dana administers ENT-A alone. Tomas's client for every entity and his client for ENT-B are
    ``ACTIVE`` with a secret:

    - she is listed neither, and ``GET /api-clients/{id}`` answers her 404 for each;
    - her rotate-secret and her revoke of each answer 404 as well — to her exactly what the
      same command answers for an id that names no client;
    - the secret Tomas was told still authenticates, the instant it was issued has not moved,
      and the client stays ``ACTIVE``;
    - each of the four attempts is one ``DENIED`` event of the command under the client — the
      one 404 that records, because a member reached for a credential beyond her scope: the
      rule and, for the client of every entity, the scope, and no entity; the same commands on
      an id that names no client write nothing;
    - a request of hers beyond her own access (ENT-B; all entities) is recorded as a denial of
      the creation, as an invitation's and an assignment's are (rev 1.187), and still answers
      its 422; an entity nobody knows is recorded the same way, so the trail tells no more than
      the answer.

    Positive controls: Dana lists and reads her own approved client for ENT-A, issues its first
    secret and revokes it; Tomas, who covers every entity, lists and reads all three and rotates
    and revokes the two that are hidden from her.

    Fail-first: Dana was listed every client and answered the new secret of the client for
    every entity."""
    tenant_id = tomas.member.tenant_id
    a = entities["A"]
    # Tomas is alone, so rule AUTO-BOOTSTRAP approves both and each answers its secret.
    everywhere = requested(app, tomas, "svc-all")
    for_b_created = named(app, tomas, "svc-b", "ENT-B")
    assert for_b_created.status_code == 201, for_b_created.text
    for_b = for_b_created.json()
    for client in (everywhere, for_b):
        assert (client["status"], isinstance(client["client_secret"], str)) == ("ACTIVE", True)
    issued = {
        client["id"]: secret_issued_at(tenant_id, client["id"]) for client in (everywhere, for_b)
    }

    someone = colleague(tenant_id, "dana")
    assign(someone, "tenant_admin", entity_ids=[a])
    dana = enrolled(app, clock, someone)
    nobody = str(UUID(int=0))
    commands: tuple[tuple[str, dict[str, Any]], ...] = (
        ("rotate-secret", {}),
        ("revoke", {"reason": REASON}),
    )

    # The reads: neither client is hers to act on, so neither is listed or read.
    assert listed(app, dana) == []
    no_client = get(app, f"{CLIENTS}/{nobody}", dana)
    assert (no_client.status_code, slug(no_client)) == (404, "not-found"), no_client.text
    for client in (everywhere, for_b):
        assert told(get(app, f"{CLIENTS}/{client['id']}", dana)) == told(no_client)

    # The commands: what an id that names no client is answered, and nothing recorded for it.
    unknown = {
        command: post(app, f"{CLIENTS}/{nobody}/{command}", dana, body)
        for command, body in commands
    }
    for answer in unknown.values():
        assert (answer.status_code, slug(answer)) == (404, "not-found"), answer.text
    assert denials(tenant_id) == []
    # ... and the two clients she does not reach: the same answer, and the attempt on record.
    for client in (everywhere, for_b):
        for command, body in commands:
            hidden = post(app, f"{CLIENTS}/{client['id']}/{command}", dana, body)
            assert told(hidden) == told(unknown[command]), hidden.text
        assert shown(app, tomas, client["id"])["status"] == "ACTIVE"
        assert secret_issued_at(tenant_id, client["id"]) == issued[client["id"]]
        still = token_request(app, client["client_id"], client["client_secret"])
        assert still.status_code == 200, still.text

    # Beyond her own access at the creation: the 422 it answered before, and now its trace.
    outside = named(app, dana, "svc-outside", "ENT-B")
    unknown_entity = named(app, dana, "svc-unknown", "ENT-Z")
    all_of_them = post(app, CLIENTS, dana, {"name": "svc-everywhere", "scopes": SCOPES})
    for answer in (outside, unknown_entity, all_of_them):
        assert (answer.status_code, slug(answer)) == (422, "validation-failed"), answer.text

    rule, scope = {"permission": "api_client.manage", "rule_id": "T-PLT-10"}, {"scope": "*"}
    her = dana.member.user_id
    assert denials(tenant_id) == [
        ("api_client.rotate_secret", everywhere["id"], her, {**rule, **scope}),
        ("api_client.revoke", everywhere["id"], her, {**rule, **scope}),
        ("api_client.rotate_secret", for_b["id"], her, rule),
        ("api_client.revoke", for_b["id"], her, rule),
        ("api_client.create", None, her, rule),
        ("api_client.create", None, her, rule),
        ("api_client.create", None, her, {**rule, **scope}),
    ]

    # Positive controls. Her own client for ENT-A, approved by Tomas: she lists and reads it,
    # issues its first secret and revokes it, and nothing is denied her.
    own = named(app, dana, "svc-dana", "ENT-A")
    assert own.status_code == 201, own.text
    approved = approve(app, str(own.json()["approval_request_id"]), tomas)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    assert listed(app, dana) == ["svc-dana"]
    hers = shown(app, dana, own.json()["id"])
    assert (hers["status"], hers["entity_ids"], hers["has_secret"]) == ("ACTIVE", [str(a)], False)
    first = post(app, f"{CLIENTS}/{own.json()['id']}/rotate-secret", dana, {})
    assert first.status_code == 200, first.text
    token = token_request(app, own.json()["client_id"], first.json()["client_secret"])
    assert token.status_code == 200, token.text
    gone = post(app, f"{CLIENTS}/{own.json()['id']}/revoke", dana, {"reason": REASON})
    assert (gone.status_code, gone.json()["status"]) == (200, "REVOKED"), gone.text
    # Tomas covers every entity: he lists and reads all three, and rotates and revokes the two
    # that are hidden from her.
    assert listed(app, tomas) == ["svc-all", "svc-b", "svc-dana"]
    for client in (everywhere, for_b):
        assert shown(app, tomas, client["id"])["name"] == client["name"]
        rotated = post(app, f"{CLIENTS}/{client['id']}/rotate-secret", tomas, {})
        assert rotated.status_code == 200, rotated.text
        ended = post(app, f"{CLIENTS}/{client['id']}/revoke", tomas, {"reason": REASON})
        assert (ended.status_code, ended.json()["status"]) == (200, "REVOKED"), ended.text
    assert len(denials(tenant_id)) == 7
