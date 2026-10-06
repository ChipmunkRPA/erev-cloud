"""DG-API-11 ``erev_api.domain.platform.actors`` without a database (04 §16.0 API-S-Actor, rev
1.139): the Actor a row's id, stored kind and identity lookup give, and the shape of the lookup —
two scalar subqueries on primary keys inside the statement that reads the row."""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.db.tables import audit_event, period_lock
from erev_api.domain.platform import actors
from erev_api.enums import PrincipalKind
from erev_api.schemas.common import ActorOut
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

SOMEONE = UUID("0191e0a0-0000-7000-8000-0000000000a1")
MAYA = {"kind": "USER", "display_name": "Maya Chen"}
OPERATOR = {"kind": "OPERATOR", "display_name": "Dana Whitfield"}
CLIENT = {"kind": "API_CLIENT", "display_name": "svc-billing"}


@pytest.mark.parametrize(
    ("principal_id", "kind", "found", "expected"),
    [
        # the row stores the kind: it rules, and the lookup gives the name
        (SOMEONE, PrincipalKind.USER, MAYA, (SOMEONE, "USER", "Maya Chen")),
        (str(SOMEONE), "API_CLIENT", CLIENT, (SOMEONE, "API_CLIENT", "svc-billing")),
        (SOMEONE, "OPERATOR", OPERATOR, (SOMEONE, "OPERATOR", "Dana Whitfield")),
        # nobody: the system, whatever the lookup says
        (None, PrincipalKind.SYSTEM, None, (None, "SYSTEM", "System")),
        (None, None, None, (None, "SYSTEM", "System")),
        # the column stores no kind (SC-V `published_by`, T-PLT-19 `on_behalf_of_id`): the identity
        # table that answered gives it
        (SOMEONE, None, MAYA, (SOMEONE, "USER", "Maya Chen")),
        (SOMEONE, None, OPERATOR, (SOMEONE, "OPERATOR", "Dana Whitfield")),
        (SOMEONE, None, CLIENT, (SOMEONE, "API_CLIENT", "svc-billing")),
        # an id nobody answers keeps its stored kind and shows the system name; never an error
        (SOMEONE, "API_CLIENT", None, (SOMEONE, "API_CLIENT", "System")),
        (SOMEONE, None, None, (SOMEONE, "USER", "System")),
    ],
)
def test_actor_of_an_id_its_stored_kind_and_the_identity_lookup(
    principal_id: object,
    kind: object,
    found: dict[str, str] | None,
    expected: tuple[UUID | None, str, str],
) -> None:
    built = actors.actor(principal_id, kind, found)
    assert (built["id"], built["kind"], built["display_name"]) == expected
    shown = ActorOut.model_validate(built)  # API-S-Actor takes it as it is
    assert (shown.id, shown.kind.value, shown.display_name) == expected


def test_named_is_a_lookup_inside_the_statement_of_the_row() -> None:
    """One statement: the identity tables are read by primary key in scalar subqueries correlated
    to the row, ``app_user`` by ``id`` and ``api_client`` by ``(tenant_id, id)`` — no join that
    could multiply or drop rows, no second statement."""
    statement = select(
        period_lock.c.id,
        actors.named(period_lock.c.created_by, tenant_id=period_lock.c.tenant_id).label("who"),
    )
    sql = " ".join(str(statement.compile(dialect=postgresql.psycopg.dialect())).split())
    assert sql.count("FROM erev.period_lock") == 1  # the row's table is not read again
    assert "FROM erev.app_user WHERE erev.app_user.id = erev.period_lock.created_by)" in sql
    assert (
        "FROM erev.api_client WHERE erev.api_client.tenant_id = erev.period_lock.tenant_id "
        "AND erev.api_client.id = erev.period_lock.created_by)"
    ) in sql
    assert sql.startswith("SELECT erev.period_lock.id, coalesce((SELECT jsonb_build_object(")
    # a column without a stored kind takes it from the table that answers
    assert "CASE WHEN erev.app_user.is_operator THEN" in sql

    other = select(
        audit_event.c.id,
        actors.named(audit_event.c.on_behalf_of_id, tenant_id=audit_event.c.tenant_id),
    )
    text = " ".join(str(other.compile(dialect=postgresql.psycopg.dialect())).split())
    assert "erev.app_user.id = erev.audit_event.on_behalf_of_id" in text
    assert text.count("FROM erev.audit_event") == 1


def test_member_names_the_person_as_the_workspace_is_shown_them() -> None:
    """``member`` reads the person of a membership through the one rule of what the workspace is
    shown (dev-guide DG-KRN-DB-13; item IDENTITY-WITHHELD-BY-STATUS-1): the email for a
    membership that is INVITED or REMOVED and whose invitation did not create the identity, the
    name otherwise. The rule is the name's expression inside the lookup — the lookup keeps its
    one condition, the membership's key, so no owner drops out of the row that names them."""
    from erev_api.db.tables import exception_item

    statement = select(
        exception_item.c.id,
        actors.member(
            exception_item.c.owner_membership_id, tenant_id=exception_item.c.tenant_id
        ).label("owner"),
    )
    sql = " ".join(str(statement.compile(dialect=postgresql.dialect())).split())
    assert "CASE WHEN (erev.tenant_membership.status IN (" in sql
    assert "THEN erev.app_user.email ELSE erev.app_user.display_name END" in sql
    lookup = sql[sql.index("FROM erev.tenant_membership JOIN erev.app_user") :]
    assert lookup.count(" WHERE ") == 1
    assert (
        " WHERE erev.tenant_membership.tenant_id = erev.exception_item.tenant_id "
        "AND erev.tenant_membership.id = erev.exception_item.owner_membership_id"
    ) in lookup
