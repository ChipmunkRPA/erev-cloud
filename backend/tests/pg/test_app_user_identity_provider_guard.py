"""DB-20 ``tg_app_user__identity_provider`` (04 §14.1 rev 1.189; revision 0103; 03 REQ-PLT-006;
independent review of the platform security merge, finding 9; supervisor ruling R-111 (7)).

An identity signs in through a provider only when it was invited for it
(``identity_provider_id``) and presents the subject its first sign-in recorded
(``identity_provider_subject``). ``erev_app`` holds UPDATE on both columns — the invitation and
the first sign-in write them — so nothing but the commands kept an identity from being moved to
another provider or its subject rebound. The guard admits a provider only where none was set and a
subject only where none was recorded; a subject is cleared only in the erased form of
``user.anonymise`` (DB-19). Every other change is refused by name (``EREV-IMM-001`` → 409
``immutable-record``), for every role. Each probe runs in a savepoint of one ``erev_owner``
transaction that is rolled back: only the owner writes ``identity_provider`` (04 §14.2).
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.db import new_id
from erev_api.db.tables import app_user, identity_provider
from erev_api.domain.platform.privacy import erased_display_name, erased_email
from erev_api.enums import UserStatus
from erev_api.problems import from_db_error
from sqlalchemy import Connection, exc, insert, select, text, update
from sqlalchemy.engine import CursorResult
from support.db import TestDatabase

pytestmark = pytest.mark.pg

CODE = "EREV-IMM-001"
DISABLED = UserStatus.DISABLED.value
SUBJECT = "248289761001"
_TRIGGER = text(
    "SELECT pg_get_triggerdef(t.oid), t.tgenabled FROM pg_trigger t "
    "WHERE t.tgrelid = CAST('erev.app_user' AS regclass) "
    "AND t.tgname = 'tg_app_user__identity_provider'"
)
_FUNCTION = text(
    "SELECT p.prosecdef, coalesce(p.proconfig::text, ''), "
    "has_function_privilege('erev_app', p.oid, 'EXECUTE') FROM pg_proc p "
    "JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'erev' AND p.proname = 'tg_app_user__identity_provider'"
)
_COLUMN_UPDATE = text(
    "SELECT has_column_privilege('erev_app', 'erev.app_user', CAST(:column AS text), 'UPDATE')"
)


def _provider(connection: Connection) -> UUID:
    provider_id = new_id()
    connection.execute(
        insert(identity_provider).values(
            id=provider_id,
            code=f"idp-{secrets.token_hex(4)}",
            kind="oidc",
            display_name="Guard test provider",
            issuer_url="https://idp.guard.test",
            client_id="erev",
            email_domains=["guard.test"],
            created_by_kind="SYSTEM",
            updated_by_kind="SYSTEM",
        )
    )
    return provider_id


def _user(connection: Connection) -> UUID:
    user_id = new_id()
    connection.execute(
        insert(app_user).values(
            id=user_id,
            email=f"lena-{secrets.token_hex(4)}@guard.test",
            display_name="Lena Fischer",
            created_by_kind="SYSTEM",
            updated_by_kind="SYSTEM",
        )
    )
    return user_id


def _identity(connection: Connection, user_id: UUID) -> tuple[Any, Any]:
    row = connection.execute(
        select(app_user.c.identity_provider_id, app_user.c.identity_provider_subject).where(
            app_user.c.id == user_id
        )
    ).one()
    return row.identity_provider_id, row.identity_provider_subject


def _admitted(connection: Connection, user_id: UUID, values: Mapping[str, Any]) -> None:
    changed = connection.execute(update(app_user).where(app_user.c.id == user_id).values(**values))
    assert cast(CursorResult[Any], changed).rowcount == 1, values


def _refused(connection: Connection, user_id: UUID, values: Mapping[str, Any]) -> str:
    """The UPDATE is refused by DB-20: SQLSTATE P0001 with the code leading the message, mapped
    to 409 ``immutable-record`` with the code and no detail; returns the trigger's message."""
    savepoint = connection.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        connection.execute(update(app_user).where(app_user.c.id == user_id).values(**values))
    savepoint.rollback()
    origin = refused.value.orig
    message = str(getattr(getattr(origin, "diag", None), "message_primary", "") or "")
    assert getattr(origin, "sqlstate", None) == "P0001", (values, message)
    assert message.startswith(f"{CODE}: "), message
    problem = from_db_error(refused.value)
    assert problem is not None
    assert (problem.slug, problem.status, problem.code) == ("immutable-record", 409, CODE)
    return message


def test_db_20_a_provider_is_set_once_and_a_subject_is_written_once(
    test_database: TestDatabase,
) -> None:
    with test_database.owner_engine.connect() as connection:
        outer = connection.begin()
        first, second = _provider(connection), _provider(connection)
        user_id = _user(connection)

        # The invitation: no provider yet, so one is set. From then on it does not move —
        # neither to another provider nor back to none.
        _admitted(connection, user_id, {"identity_provider_id": first})
        for value in (second, None):
            message = _refused(connection, user_id, {"identity_provider_id": value})
            assert "identity_provider_id" in message and str(user_id) in message
            assert str(second) not in message and str(first) not in message
        # The first sign-in: no subject yet, so one is recorded. It is not rebound, and it is
        # not cleared outside the erased form — not alone, not with the status alone.
        _admitted(connection, user_id, {"identity_provider_subject": SUBJECT})
        for values in (
            {"identity_provider_subject": "another-subject"},
            {"identity_provider_subject": None},
            {"identity_provider_subject": None, "status": DISABLED},
        ):
            message = _refused(connection, user_id, values)
            assert "identity_provider_subject" in message and str(user_id) in message
            assert SUBJECT not in message and "another-subject" not in message
        assert _identity(connection, user_id) == (first, SUBJECT)
        # A SET that leaves both columns at their stored values is not a change.
        _admitted(
            connection,
            user_id,
            {
                "identity_provider_id": first,
                "identity_provider_subject": SUBJECT,
                "display_name": "L. Fischer",
            },
        )

        # user.anonymise: the erased form clears the subject; the provider stays.
        _admitted(
            connection,
            user_id,
            {
                "email": erased_email(user_id),
                "display_name": erased_display_name(user_id),
                "password_hash": None,
                "external_id": None,
                "identity_provider_subject": None,
                "status": DISABLED,
            },
        )
        assert _identity(connection, user_id) == (first, None)
        outer.rollback()


def test_db_20_the_guard_fires_for_every_role_and_the_application_keeps_its_grant(
    test_database: TestDatabase,
) -> None:
    with test_database.owner_engine.connect() as connection:
        definition, enabled = connection.execute(_TRIGGER).one()
        definer, config, executable = connection.execute(_FUNCTION).one()
        granted = {
            column: bool(connection.execute(_COLUMN_UPDATE, {"column": column}).scalar_one())
            for column in ("identity_provider_id", "identity_provider_subject")
        }
    expected = "BEFORE UPDATE OF identity_provider_id, identity_provider_subject ON "
    assert expected in definition, definition
    assert "FOR EACH ROW EXECUTE FUNCTION " in definition, definition
    assert definition.endswith("tg_app_user__identity_provider()"), definition
    assert enabled == "O"  # fires in the origin (default) replication role: always, for sessions
    assert definer is False and executable is True
    assert "search_path=erev, pg_catalog" in config, config
    # The invitation and the first sign-in write the two columns as erev_app (04 §14.2): the
    # grant stays, and the guard is its compensating control.
    assert granted == {"identity_provider_id": True, "identity_provider_subject": True}
