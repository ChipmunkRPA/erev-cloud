"""DB-19 ``tg_app_user__erasure_guard`` and the DB-13 grant it compensates (04 §14.1 / §14.2 rev
1.86, §15.2 rev 1.96; revision 0073; 05 PRV-07 a; 03 REQ-SEC-007; CTL-036).

``erev_app`` holds UPDATE on ``app_user.email`` and ``external_id`` only so that
``user.anonymise`` can rewrite them. The guard admits a change of either column only in the erased
form — ``email = 'erased+<user id>@invalid.erev'``, ``external_id`` NULL and ``status`` DISABLED
in the same UPDATE — and refuses every other change by name (``EREV-PRV-001`` → 403
``forbidden``), for every role, so a defect running as ``erev_app`` cannot repoint a login e-mail.
Each probe runs in a savepoint of an ``erev_app`` identity transaction that is rolled back.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.db import new_id
from erev_api.db.session import identity_session
from erev_api.db.tables import app_user
from erev_api.domain.platform.privacy import erased_display_name, erased_email
from erev_api.enums import UserStatus
from erev_api.problems import from_db_error
from sqlalchemy import Connection, exc, insert, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from support.db import TestDatabase

pytestmark = pytest.mark.pg

CODE = "EREV-PRV-001"
DISABLED = UserStatus.DISABLED.value
GUARDED = ("email", "external_id")
_TRIGGERS = text(
    "SELECT t.tgname, pg_get_triggerdef(t.oid), t.tgenabled FROM pg_trigger t "
    "WHERE t.tgrelid = CAST('erev.app_user' AS regclass) AND NOT t.tgisinternal ORDER BY t.tgname"
)
_FUNCTION = text(
    "SELECT p.prosecdef, coalesce(p.proconfig::text, '') FROM pg_proc p "
    "JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'erev' AND p.proname = 'tg_app_user__erasure_guard'"
)
_COLUMN_UPDATE = text(
    "SELECT has_column_privilege('erev_app', 'erev.app_user', CAST(:column AS text), 'UPDATE')"
)


def _insert_user(bind: Session | Connection, *, external_id: str | None = "scim-7421") -> UUID:
    """An ACTIVE ``app_user`` with a login e-mail and, unless None, an external id (an INSERT is
    not guarded: DB-19 is ``BEFORE UPDATE``)."""
    user_id = new_id()
    bind.execute(
        insert(app_user).values(
            id=user_id,
            email=f"lena-{secrets.token_hex(4)}@guard.test",
            display_name="Lena Fischer",
            external_id=external_id,
            created_by_kind="SYSTEM",
            updated_by_kind="SYSTEM",
        )
    )
    return user_id


def _row(bind: Session | Connection, user_id: UUID) -> Mapping[str, Any]:
    found = bind.execute(
        select(
            app_user.c.email, app_user.c.external_id, app_user.c.status, app_user.c.display_name
        ).where(app_user.c.id == user_id)
    )
    return dict(found.mappings().one())


def _erased(user_id: UUID) -> dict[str, Any]:
    """The values ``privacy.anonymise_user`` writes (05 PRV-07 a)."""
    return {
        "email": erased_email(user_id),
        "display_name": erased_display_name(user_id),
        "password_hash": None,
        "external_id": None,
        "status": DISABLED,
        "updated_by_kind": "SYSTEM",
    }


def _refused(bind: Session | Connection, user_id: UUID, values: Mapping[str, Any]) -> str:
    """The UPDATE is refused by DB-19: SQLSTATE P0001, the code leading the message, mapped to 403
    ``forbidden`` with the code and no detail (04 §15.2); returns the trigger's message."""
    savepoint = bind.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        bind.execute(update(app_user).where(app_user.c.id == user_id).values(**values))
    savepoint.rollback()
    origin = refused.value.orig
    message = str(getattr(getattr(origin, "diag", None), "message_primary", "") or "")
    assert getattr(origin, "sqlstate", None) == "P0001", (values, message)
    assert message.startswith(f"{CODE}: "), message
    problem = from_db_error(refused.value)
    assert problem is not None
    assert (problem.slug, problem.status, problem.code) == ("forbidden", 403, CODE)
    assert problem.detail is None and problem.errors == ()
    return message


def _admitted(bind: Session | Connection, user_id: UUID, values: Mapping[str, Any]) -> None:
    changed = bind.execute(update(app_user).where(app_user.c.id == user_id).values(**values))
    assert cast(CursorResult[Any], changed).rowcount == 1, values


def test_db_19_the_erased_form_is_admitted_as_erev_app(test_database: TestDatabase) -> None:
    """The UPDATE ``user.anonymise`` issues — the three conditions together — passes the guard and
    the DB-13 column grant as ``erev_app``; ``erased_email`` (Python ``str(UUID)``) is the form the
    trigger builds from ``NEW.id::text``."""
    with identity_session(request_id="tests-db-19-erased") as session:
        user_id = _insert_user(session)
        _admitted(session, user_id, _erased(user_id))
        assert _row(session, user_id) == {
            "email": f"erased+{user_id}@invalid.erev",
            "external_id": None,
            "status": DISABLED,
            "display_name": erased_display_name(user_id),
        }
        session.rollback()


REPOINTED = "repointed@attacker.test"
# What each refused UPDATE sets, given the row's id and another user's id.
REFUSED: dict[str, Callable[[UUID, UUID], dict[str, Any]]] = {
    # an ordinary e-mail change
    "email-changed": lambda own, other: {"email": REPOINTED},
    # external_id cleared and DISABLED in the same UPDATE, but not the erased address
    "email-changed-with-the-other-two-conditions": lambda own, other: {
        "email": REPOINTED,
        "external_id": None,
        "status": DISABLED,
    },
    # the erased address and the cleared external id while status stays ACTIVE
    "erased-email-not-disabled": lambda own, other: {
        "email": erased_email(own),
        "external_id": None,
    },
    # the erased address and DISABLED while the external id stays
    "erased-email-external-id-kept": lambda own, other: {
        "email": erased_email(own),
        "status": DISABLED,
    },
    "external-id-changed-alone": lambda own, other: {"external_id": "scim-0001"},
    "external-id-cleared-alone": lambda own, other: {"external_id": None},
    # cleared and DISABLED while the login e-mail stays
    "external-id-cleared-disabled-email-kept": lambda own, other: {
        "external_id": None,
        "status": DISABLED,
    },
    # the erased form of ANOTHER user's id
    "erased-form-of-another-user": lambda own, other: {
        "email": erased_email(other),
        "external_id": None,
        "status": DISABLED,
    },
    # an erased-looking address that is not the form (the id without hyphens)
    "erased-looking-address": lambda own, other: {
        "email": f"erased+{own.hex}@invalid.erev",
        "external_id": None,
        "status": DISABLED,
    },
}


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_db_19_any_other_change_is_refused_by_name_as_erev_app(
    case: str, test_database: TestDatabase
) -> None:
    """Every change of ``email`` or ``external_id`` outside the erased form is refused with
    ``EREV-PRV-001`` although ``erev_app`` holds the column grant; nothing of the row changes and
    the message names the row, never a value of either column."""
    with identity_session(request_id="tests-db-19-refused") as session:
        user_id, other_id = _insert_user(session), _insert_user(session, external_id=None)
        before = _row(session, user_id)
        values = REFUSED[case](user_id, other_id)
        message = _refused(session, user_id, values)
        assert str(user_id) in message, message
        for value in (before["email"], before["external_id"], values.get("email")):
            assert value is None or str(value) not in message, message
        assert _row(session, user_id) == before
        session.rollback()


def test_db_19_a_set_that_changes_neither_column_is_not_a_change(
    test_database: TestDatabase,
) -> None:
    """The trigger fires when the SET list names a guarded column, but a SET that leaves both at
    their stored values is not a change; an UPDATE of other columns never meets the guard."""
    with identity_session(request_id="tests-db-19-unchanged") as session:
        user_id = _insert_user(session)
        before = _row(session, user_id)
        _admitted(
            session,
            user_id,
            {
                "email": before["email"],
                "external_id": before["external_id"],
                "display_name": "Lena F.",
                "updated_by_kind": "SYSTEM",
            },
        )
        _admitted(session, user_id, {"status": DISABLED, "updated_by_kind": "SYSTEM"})
        assert _row(session, user_id) == {**before, "display_name": "Lena F.", "status": DISABLED}
        session.rollback()


def test_db_19_an_erased_identity_cannot_be_repointed(test_database: TestDatabase) -> None:
    """After the erasure the same UPDATE again is not a change (the resume run of the command never
    issues it, but it would not be refused); restoring a login e-mail or an external id is."""
    with identity_session(request_id="tests-db-19-after") as session:
        user_id = _insert_user(session)
        _admitted(session, user_id, _erased(user_id))
        erased = _row(session, user_id)
        _admitted(session, user_id, _erased(user_id))
        _refused(session, user_id, {"email": "lena@guard.test"})
        _refused(session, user_id, {"email": "lena@guard.test", "status": UserStatus.ACTIVE.value})
        _refused(session, user_id, {"external_id": "scim-7421"})
        assert _row(session, user_id) == erased
        session.rollback()


def test_db_19_fires_for_erev_owner_too(test_database: TestDatabase) -> None:
    """04 DB-19: "the trigger fires for every role" — the owner's UPDATE is judged by the same
    predicate (no ``current_user`` exemption, unlike DB-01's data-fix ticket)."""
    with test_database.owner_engine.connect() as connection:
        connection.begin()
        try:
            user_id = _insert_user(connection)
            before = _row(connection, user_id)
            message = _refused(connection, user_id, {"email": REPOINTED})
            assert str(user_id) in message
            _refused(connection, user_id, {"external_id": None})
            assert _row(connection, user_id) == before
            _admitted(connection, user_id, _erased(user_id))
            assert _row(connection, user_id)["email"] == erased_email(user_id)
        finally:
            connection.rollback()


def test_db_19_installed_trigger_function_and_grant(test_database: TestDatabase) -> None:
    """The catalogue as revision 0073 leaves it: the guard is a ``BEFORE UPDATE OF email,
    external_id`` row trigger beside the DB-02 touch trigger, its function is SECURITY INVOKER
    with the search path pinned (NC-18; DB-14 (h)), and ``erev_app`` holds UPDATE on the two
    guarded columns while the identity columns stay withheld (DB-13)."""
    with test_database.owner_engine.connect() as connection:
        triggers = {
            str(name): (str(definition), str(enabled))
            for name, definition, enabled in connection.execute(_TRIGGERS)
        }
        definer, config = connection.execute(_FUNCTION).one()
        granted = {
            column: bool(connection.execute(_COLUMN_UPDATE, {"column": column}).scalar_one())
            for column in (*GUARDED, "id", "is_operator", "created_at")
        }
    # DB-20 tg_app_user__identity_provider joins the table in revision 0103 (04 rev 1.189):
    # its own witnesses are tests/pg/test_app_user_identity_provider_guard.py.
    assert sorted(triggers) == [
        "tg_app_user__erasure_guard",
        "tg_app_user__identity_provider",
        "tg_app_user__touch",
    ]
    definition, enabled = triggers["tg_app_user__erasure_guard"]
    assert "BEFORE UPDATE OF email, external_id ON " in definition, definition
    assert "FOR EACH ROW EXECUTE FUNCTION " in definition, definition
    assert definition.endswith("tg_app_user__erasure_guard()"), definition
    assert enabled == "O"  # fires in the origin (default) replication role: always, for sessions
    assert definer is False
    assert "search_path=erev, pg_catalog" in config, config
    assert granted == {
        "email": True,
        "external_id": True,
        "id": False,
        "is_operator": False,
        "created_at": False,
    }
