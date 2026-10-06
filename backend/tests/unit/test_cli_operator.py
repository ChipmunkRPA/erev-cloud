"""``erev operator create`` (04 T-PLT-02 ``is_operator``, T-PLT-06; BUILD_SPEC PLF-26, BS1-D-27)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from erev_api.auth import passwords
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import identity_session
from erev_api.db.tables import app_user, security_event
from sqlalchemy import select
from support.db import TestDatabase
from support.operators import invoke, operator_services
from support.principals import PASSWORD

PROBLEM_BASE = "https://erev.dev/problems/"
CREATE = ["operator", "create", "--email", "ops@erev.test", "--name", "Ops Tester"]


def test_operator_create_prompts_password(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    services = operator_services(keyring, clock, tmp_path)
    result = invoke(services, CREATE, input=f"{PASSWORD}\n{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    created = json.loads(result.stdout.splitlines()[-1])
    assert set(created) == {"id", "email", "display_name", "is_operator"}
    assert (created["email"], created["display_name"], created["is_operator"]) == (
        "ops@erev.test",
        "Ops Tester",
        True,
    )
    user_id = UUID(created["id"])
    with identity_session(request_id="tests-cli-operator") as db:
        user = db.execute(
            select(
                app_user.c.is_operator,
                app_user.c.password_hash,
                app_user.c.status,
                app_user.c.created_by_kind,
            ).where(app_user.c.id == user_id)
        ).one()
        events = db.execute(
            select(security_event.c.kind, security_event.c.detail).where(
                security_event.c.user_id == user_id
            )
        ).all()
    assert (user.is_operator, user.status, user.created_by_kind) == (True, "ACTIVE", "OPERATOR")
    assert user.password_hash.startswith("$argon2id$")
    assert passwords.verify_password(user.password_hash, PASSWORD)
    # Neither the password nor its hash is printed.
    assert PASSWORD not in result.output
    assert user.password_hash not in result.output
    assert [(event.kind, event.detail) for event in events] == [
        ("PLATFORM_SCOPE_USED", {"command": "operator.create"})
    ]

    duplicate = invoke(services, CREATE, input=f"{PASSWORD}\n{PASSWORD}\n")
    assert duplicate.exit_code == 1
    problem = json.loads(duplicate.stderr)
    assert problem["type"] == PROBLEM_BASE + "validation-failed"
    assert [(error["field"], error["rule_id"]) for error in problem["errors"]] == [
        ("email", "T-PLT-02")
    ]
    assert '"is_operator"' not in duplicate.stdout
