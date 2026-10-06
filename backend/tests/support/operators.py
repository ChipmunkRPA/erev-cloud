"""Platform operators and support grants for api and domain tests (BUILD_SPEC PLF-26, BS1-D-27).

``invoke`` runs the ``erev`` application with the operator commands' services replaced by the
test's clock, key ring and file store. ``create_operator`` and ``request_grant`` drive ``erev
operator create`` and ``erev support-grant request``; ``operator_signed_in`` signs an operator in
and confirms TOTP enrolment, so the session is MFA-verified; ``approve`` decides an approval request
as a Tenant Admin.
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import structlog
from click.testing import Result
from erev_api import cli
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Environment
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import tenant
from erev_api.files.store import LocalFileStore
from fastapi import FastAPI
from sqlalchemy import select
from support.http import HttpResponse, call
from support.principals import (
    PASSWORD,
    Actor,
    Signed,
    cookie_headers,
    cookie_of,
    refreshed,
    sign_in,
)
from typer.testing import CliRunner

APPROVALS = "/api/v1/approvals"
OPERATOR_NAME = "Ops Tester"


def operator_services(
    keyring: KeyRing, clock: FrozenClock, root: Path, *, env: Environment = Environment.TEST
) -> cli.CliServices:
    return cli.CliServices(clock=clock, keyring=keyring, files=LocalFileStore(root), env=env)


@contextmanager
def logging_restored() -> Iterator[None]:
    """Put the process's logging pipeline back after a command that installed its own.

    ``cli._cli_settings`` (05 OPR-20 rev 1.53) binds the pipeline to the runner's stderr, which
    the runner closes when the command ends; left in place, every later log call of the test
    process would write to a closed stream.
    """
    saved = structlog.get_config()
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
        structlog.configure(
            processors=list(saved["processors"]),
            context_class=saved["context_class"],
            wrapper_class=saved["wrapper_class"],
            logger_factory=saved["logger_factory"],
            cache_logger_on_first_use=saved["cache_logger_on_first_use"],
        )


def invoke(services: cli.CliServices, args: Sequence[str], *, input: str | None = None) -> Result:
    def replaced(*, gated: bool = True) -> cli.CliServices:
        # The composition root's signature (05 SAR-40 rev 1.53: doctor and verify pass
        # ``gated=False``); the production gate itself is tested in unit/test_cli_logging.py.
        return services

    with pytest.MonkeyPatch.context() as patch, logging_restored():
        patch.setattr(cli, "cli_services", replaced)
        return CliRunner().invoke(cli.app, list(args), input=input)


def create_operator(services: cli.CliServices, *, email: str | None = None) -> dict[str, Any]:
    """``erev operator create`` with the shared test password on stdin."""
    address = email or f"ops-{secrets.token_hex(4)}@erev.test"
    result = invoke(
        services,
        ["operator", "create", "--email", address, "--name", OPERATOR_NAME],
        input=f"{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    created: dict[str, Any] = json.loads(result.stdout.splitlines()[-1])
    return created


def request_grant(
    services: cli.CliServices,
    *,
    tenant_code: str,
    operator_email: str,
    valid_from: str,
    valid_to: str,
) -> Result:
    """``erev support-grant request`` with the BUILD_SPEC PLF-26 reason and ticket."""
    return invoke(
        services,
        [
            "support-grant",
            "request",
            "--tenant",
            tenant_code,
            "--operator",
            operator_email,
            "--reason",
            "Investigate export failure",
            "--ticket",
            "SUP-2291",
            "--from",
            valid_from,
            "--to",
            valid_to,
        ],
    )


def tenant_code(tenant_id: UUID) -> str:
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
        return str(db.execute(select(tenant.c.code).where(tenant.c.id == tenant_id)).scalar_one())


def operator_signed_in(app: FastAPI, clock: FrozenClock, email: str) -> Signed:
    """Sign in and confirm TOTP enrolment; the rotated session is verified."""
    signed = sign_in(app, email)
    started = call(
        app,
        "POST",
        "/api/v1/me/mfa/enroll",
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    assert started.status_code == 200, started.text
    secret = str(started.json()["secret_base32"])
    confirmed = call(
        app,
        "POST",
        "/api/v1/me/mfa/confirm",
        json={"code": totp.code_at(secret, totp.time_step(clock.now()))},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    assert confirmed.status_code == 200, confirmed.text
    return refreshed(app, cookie_of(confirmed))


def approve(app: FastAPI, request_id: str, approver: Actor) -> HttpResponse:
    detail = call(
        app,
        "GET",
        f"{APPROVALS}/{request_id}",
        headers=cookie_headers(approver.token, key=False),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    return call(
        app,
        "POST",
        f"{APPROVALS}/{request_id}/approve",
        json={
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Ticket SUP-2291 checked",
        },
        headers=cookie_headers(approver.token, approver.csrf_token),
    )
