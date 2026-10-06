"""``erev tenant resend-invitation``: the operator issues the first Tenant Admin's invitation again
(04 §14.3 step 5 rev 1.114, T-PLT-07; PRD BR-PLT-01 rev 1.43; 03 REQ-PLT-038; dev-guide
DG-KRN-TEN-04 rev 1.97; supervisor ruling R-37 (d)).

Found in the deployment drills: until the provisioned Tenant Admin accepts, nobody in the tenant
can send the invitation again and an operator has no session there, so a lost or expired first
link left a workspace that nobody could enter. The command runs through its real entry point, the
CLI, against a workspace each test provisions for itself.
"""

from __future__ import annotations

import getpass
import io
import json
import re
import secrets
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from click.testing import Result
from erev_api import cli
from erev_api.auth.keyring import KeyRing
from erev_api.auth.sessions import sha256_hex
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    app_user,
    audit_event,
    outbox_message,
    security_event,
    tenant_membership,
)
from erev_api.domain.platform import provisioning
from erev_api.enums import MembershipStatus
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.links import emailed_token
from support.operators import invoke, operator_services
from support.principals import PASSWORD
from support.rows import RowContext, membership_row

LOOKUP = "/api/v1/session/invitations/lookup"
ACCEPT = "/api/v1/session/accept-invitation"
PROBLEM_BASE = "https://erev.dev/problems/"
INVITATION_LINK = "/accept-invitation#token="


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def services(keyring: KeyRing, clock: FrozenClock, tmp_path: Path) -> cli.CliServices:
    return operator_services(keyring, clock, tmp_path)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _provisioned(services: cli.CliServices) -> tuple[str, str, dict[str, Any]]:
    """A workspace of its own: the code, the admin's email and what ``tenant create`` printed."""
    code = f"reinvite-{secrets.token_hex(5)}"
    email = f"admin@{code}.test"
    created = invoke(
        services,
        [
            "tenant",
            "create",
            "--code",
            code,
            "--name",
            "Reinvite Test",
            "--reporting-currency",
            "USD",
        ]
        + ["--admin", email],
    )
    assert created.exit_code == 0, created.output
    return code, email, json.loads(created.stdout.splitlines()[-1])


def _resend(services: cli.CliServices, code: str, email: str) -> Result:
    return invoke(services, ["tenant", "resend-invitation", "--code", code, "--admin", email])


def _tokens(tenant_id: UUID, membership_id: UUID) -> list[str]:
    """The tokens of the invitation emails queued for the membership, oldest first — each as
    its email carries it: the stored message names its token and never holds it (04 T-INT-03
    ``payload`` rev 1.151; security review P3-17)."""
    with tenant_session(_context(tenant_id)) as db:
        payloads = db.scalars(
            select(outbox_message.c.payload)
            .where(outbox_message.c.aggregate_id == membership_id)
            .order_by(outbox_message.c.created_at, outbox_message.c.id)
        ).all()
    return [emailed_token(payload, prefix=INVITATION_LINK) for payload in payloads]


def _membership(tenant_id: UUID, membership_id: UUID) -> dict[str, Any]:
    with tenant_session(_context(tenant_id)) as db:
        row = db.execute(
            select(tenant_membership).where(tenant_membership.c.id == membership_id)
        ).mappings()
        return dict(row.one())


def _audit(tenant_id: UUID, action: str) -> Sequence[Any]:
    with tenant_session(_context(tenant_id)) as db:
        return db.execute(
            select(
                audit_event.c.actor_kind,
                audit_event.c.actor_id,
                audit_event.c.detail,
                audit_event.c.request_id,
            )
            .where(audit_event.c.action == action)
            .order_by(audit_event.c.chain_seq)
        ).all()


def _directory_reads(request_id: str) -> int:
    """The ``PLATFORM_SCOPE_USED`` events of the tenant directory scope under ``request_id``."""
    with identity_session(request_id="tests-reinvite") as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(security_event)
                .where(
                    security_event.c.kind == "PLATFORM_SCOPE_USED",
                    security_event.c.request_id == request_id,
                    security_event.c.detail["scope"].astext == "tenant_directory",
                )
            ).scalar_one()
        )


def _slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).rsplit("/", 1)[1]


def _problem(result: Result) -> tuple[str, list[tuple[str | None, str | None, str]]]:
    assert result.exit_code == 1 and result.stdout == "", result.output
    document = json.loads(result.stderr.splitlines()[-1])
    errors = [(e["field"], e["rule_id"], e["message"]) for e in document["errors"]]
    return str(document["type"]).removeprefix(PROBLEM_BASE), errors


def test_the_operator_issues_an_expired_first_invitation_again(
    app: FastAPI, services: cli.CliServices, clock: FrozenClock, log_stream: io.StringIO
) -> None:
    code, email, created = _provisioned(services)
    tenant_id, membership_id = UUID(created["tenant"]["id"]), UUID(created["admin_membership_id"])
    (first,) = _tokens(tenant_id, membership_id)
    assert _membership(tenant_id, membership_id)["invitation_token_sha256"] == sha256_hex(first)

    # Eight days later the link has expired and the workspace has no member who could resend it.
    clock.advance(timedelta(days=8))
    assert call(app, "POST", LOOKUP, json={"token": first}).status_code == 404

    result = _resend(services, code, email)
    assert result.exit_code == 0, result.output
    (line,) = result.stdout.splitlines()
    printed = json.loads(line)
    assert json.dumps(printed, sort_keys=True) == line, "keys sorted at every level"
    expires_at = clock.now() + provisioning.INVITATION_LIFETIME
    assert printed == {
        "admin_membership_id": str(membership_id),
        "invitation_expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tenant": {"code": code, "id": str(tenant_id)},
    }

    # A new token replaced the first; neither it nor its hash is printed.
    first_again, second = _tokens(tenant_id, membership_id)
    assert first_again == first and second != first
    membership = _membership(tenant_id, membership_id)
    assert membership["status"] == MembershipStatus.INVITED.value
    assert membership["invitation_token_sha256"] == sha256_hex(second)
    assert membership["invitation_expires_at"] == expires_at
    for secret in (first, second, sha256_hex(second)):
        assert secret not in result.output

    # Evidence: the membership command's audit event under the OPERATOR principal with the channel
    # and the OS user, as tenant.provision records them, and the security event of the directory
    # read that found the tenant, under the same request id.
    (event,) = _audit(tenant_id, "tenant_membership.resend_invitation")
    assert (event.actor_kind, event.actor_id) == ("OPERATOR", None)
    assert event.detail == {"channel": "CLI", "os_user": getpass.getuser()}
    assert re.fullmatch(r"cli-[0-9a-f]{16}", event.request_id)
    assert _directory_reads(event.request_id) == 1

    # The earlier link stays dead; the new one opens the invitation and is accepted.
    assert call(app, "POST", LOOKUP, json={"token": first}).status_code == 404
    lookup = call(app, "POST", LOOKUP, json={"token": second})
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["email"] == email
    assert datetime.fromisoformat(lookup.json()["expires_at"]) == expires_at
    accepted = call(app, "POST", ACCEPT, json={"token": second, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    assert _membership(tenant_id, membership_id)["status"] == MembershipStatus.ACTIVE.value

    # Once accepted there is nothing to issue again: refused, and nothing is written.
    slug, errors = _problem(_resend(services, code, email))
    assert (slug, errors) == (
        "invalid-transition",
        [("status", "SM-13", "Only an open invitation can be sent again.")],
    )
    assert len(_tokens(tenant_id, membership_id)) == 2
    assert len(_audit(tenant_id, "tenant_membership.resend_invitation")) == 1


def test_an_open_invitation_can_be_issued_again_before_it_expires(
    app: FastAPI, services: cli.CliServices, clock: FrozenClock, log_stream: io.StringIO
) -> None:
    """A lost email: the first link is still valid when the operator issues the invitation again,
    and it stops working at once."""
    code, email, created = _provisioned(services)
    tenant_id, membership_id = UUID(created["tenant"]["id"]), UUID(created["admin_membership_id"])
    (first,) = _tokens(tenant_id, membership_id)
    assert call(app, "POST", LOOKUP, json={"token": first}).status_code == 200
    clock.advance(timedelta(hours=1))
    assert _resend(services, code, email.upper()).exit_code == 0, "the address is matched as stored"
    _, second = _tokens(tenant_id, membership_id)
    assert call(app, "POST", LOOKUP, json={"token": first}).status_code == 404
    assert call(app, "POST", LOOKUP, json={"token": second}).status_code == 200


def test_refusals_write_nothing(
    services: cli.CliServices, clock: FrozenClock, log_stream: io.StringIO
) -> None:
    code, email, created = _provisioned(services)
    tenant_id, membership_id = UUID(created["tenant"]["id"]), UUID(created["admin_membership_id"])
    before = _membership(tenant_id, membership_id)

    # A code that names no workspace.
    slug, errors = _problem(_resend(services, f"{code}-absent", email))
    assert (slug, errors) == (
        "validation-failed",
        [("code", "BR-PLT-01", "Choose an existing production workspace.")],
    )
    # An email without a membership in the workspace.
    slug, errors = _problem(_resend(services, code, f"nobody@{code}.test"))
    assert (slug, errors) == (
        "validation-failed",
        [("admin", "T-PLT-07", "Enter the email address the invitation was sent to.")],
    )
    # An open invitation that the workspace itself sent (the row is not an operator's): the person
    # exists because another workspace was provisioned for them.
    _, other_email, _ = _provisioned(services)
    with identity_session(request_id="tests-reinvite") as db:
        other_user = db.execute(
            select(app_user.c.id).where(app_user.c.email == other_email)
        ).scalar_one()
    row = membership_row(RowContext(tenant_id, UUID(str(other_user))))
    assert row["created_by_kind"] != "OPERATOR" and row["status"] == "INVITED"
    with tenant_session(_context(tenant_id)) as db:
        db.execute(insert(tenant_membership).values(**row))
    slug, errors = _problem(_resend(services, code, other_email))
    assert (slug, errors) == (
        "invalid-transition",
        [
            (
                "status",
                "SM-13",
                "This invitation was sent from the workspace. A Tenant Admin sends it again.",
            )
        ],
    )
    assert (
        _membership(tenant_id, UUID(str(row["id"])))["invitation_token_sha256"]
        == (row["invitation_token_sha256"])
    )

    # Nothing moved: the first invitation, its one email and the audit trail are as they were.
    assert _membership(tenant_id, membership_id) == before
    assert len(_tokens(tenant_id, membership_id)) == 1
    assert _audit(tenant_id, "tenant_membership.resend_invitation") == []
