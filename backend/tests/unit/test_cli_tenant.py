"""``erev tenant create`` (dev-guide DG-KRN-TEN-04; 04 §14.3; PRD BR-PLT-01; BUILD_SPEC PLF-29)."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from uuid import UUID

from erev_api.api.v1.operator_tenants import OperatorTenantOut, OperatorTenantSummaryOut
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, outbox_message, tenant_membership
from sqlalchemy import select
from support.db import TestDatabase
from support.links import emailed_token
from support.operators import invoke, operator_services

PROBLEM_BASE = "https://erev.dev/problems/"
CREATE = [
    "tenant",
    "create",
    "--code",
    "corrie-test",
    "--name",
    "Corrie Test (Demo)",
    "--reporting-currency",
    "USD",
    "--demo",
    "--admin",
    "maya@demo.erev",
]


def test_krn_ten_04_json_line_and_exit_codes(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    log_stream: io.StringIO,
) -> None:
    # The replaced ``cli_services`` sends logs to stderr; here they go to the captured stream.
    services = operator_services(keyring, clock, tmp_path)
    result = invoke(services, CREATE)
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    created = json.loads(lines[0])
    # Keys sorted at every level: the line is its own canonical dump.
    assert json.dumps(created, sort_keys=True) == lines[0]
    assert set(created) == set(OperatorTenantOut.model_fields)
    assert set(created["tenant"]) == set(OperatorTenantSummaryOut.model_fields)
    assert (
        created["tenant"]["code"],
        created["tenant"]["display_name"],
        created["tenant"]["kind"],
        created["tenant"]["reporting_currency"],
        created["tenant"]["is_demo"],
    ) == ("corrie-test", "Corrie Test (Demo)", "production", "USD", True)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created["invitation_expires_at"])

    tenant_id = UUID(created["tenant"]["id"])
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
        membership = db.execute(select(tenant_membership)).mappings().one()
        payload = db.execute(select(outbox_message.c.payload)).scalar_one()
        detail = db.execute(
            select(audit_event.c.detail).where(audit_event.c.action == "tenant.provision")
        ).scalar_one()
    assert str(membership["id"]) == created["admin_membership_id"]
    # The message names the token; the link is composed as the email carries it (T-INT-03).
    token = emailed_token(payload, keyring, prefix="/accept-invitation#token=")
    assert len(token) == 43
    assert token not in result.output
    assert membership["invitation_token_sha256"] not in result.output
    assert set(detail) == {"channel", "os_user"}
    assert detail["channel"] == "CLI"

    duplicate = invoke(services, CREATE)
    assert duplicate.exit_code == 1
    assert duplicate.stdout == ""
    problem = json.loads(duplicate.stderr)
    assert problem["type"] == PROBLEM_BASE + "validation-failed"
    assert [(error["field"], error["rule_id"]) for error in problem["errors"]] == [
        ("code", "TENANT_CODE_EXISTS")
    ]
