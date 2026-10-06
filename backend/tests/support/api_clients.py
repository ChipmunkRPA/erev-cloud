"""An API client through the product, as a workspace makes one since its scopes are an access grant
(supervisor ruling R-38 (iii); 03 REQ-PLT-033; 04 T-PLT-15 "Grant and secret").

A test whose subject is what a client DOES or how it is LISTED — an integration's events, a
token's refusals, a report over clients — needs a client whose grant is in force. In a workspace
past its bootstrap that takes two people: the request (``POST /api-clients``), another access
approver's approval, and — for a client that authenticates — the first secret, issued to the
requester (``rotate-secret``). ``granted_client`` and ``issued_client`` take these steps through
the routes; where rule ``AUTO-BOOTSTRAP`` approves the request at once — the bootstrap Tenant
Admin during setup — the creation's own answer is the client, with its secret.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from erev_api.clock import FrozenClock
from fastapi import FastAPI
from support.principals import Actor, Member, colleague, enrolled
from support.reference import approve, assign, post

API_CLIENTS = "/api/v1/api-clients"


def access_approver(app: FastAPI, clock: FrozenClock, admin: Member, name: str) -> Actor:
    """A colleague of ``admin`` who holds ``tenant_admin`` for all entities, at work with the
    second factor passed: another access approver of the workspace from now on."""
    someone = colleague(admin.tenant_id, name)
    assign(someone, "tenant_admin")
    return enrolled(app, clock, someone)


def granted_client(
    app: FastAPI,
    requester: Actor,
    body: Mapping[str, Any],
    *,
    approver: Actor | None = None,
) -> dict[str, Any]:
    """The creation's API-S-ApiClient of a client whose grant is in force (``ACTIVE``).

    ``requester`` requests the client. When the request waits for a person, ``approver`` — a
    holder of ``access.approve`` for the client's entities who is not the requester — approves
    it; no secret is issued then (``issued_client`` does that). Without ``approver`` the request
    must have been approved at its submission (rule ``AUTO-BOOTSTRAP``)."""
    created = post(app, API_CLIENTS, requester, dict(body))
    assert created.status_code == 201, created.text
    client: dict[str, Any] = created.json()
    if client["status"] == "ACTIVE":
        return client
    assert client["status"] == "PENDING_APPROVAL", client
    assert approver is not None, "the client waits for an approver and the test names none"
    decided = approve(app, str(client["approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED", decided.text
    return client


def issued_client(
    app: FastAPI,
    requester: Actor,
    body: Mapping[str, Any],
    *,
    approver: Actor | None = None,
) -> dict[str, Any]:
    """API-S-ApiClient of a client that authenticates, with its ``client_secret``.

    ``granted_client``, and where the grant waited for a person ``requester`` then issues the
    first secret: the step-up that admitted the request admits the secret, at the same
    instant."""
    client = granted_client(app, requester, body, approver=approver)
    if client["client_secret"]:
        return client
    issued = post(app, f"{API_CLIENTS}/{client['id']}/rotate-secret", requester, {})
    assert issued.status_code == 200, issued.text
    first: dict[str, Any] = issued.json()
    assert first["status"] == "ACTIVE" and first["client_secret"], first
    return first
