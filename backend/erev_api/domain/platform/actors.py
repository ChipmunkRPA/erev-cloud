"""API-S-Actor of a response member that names a person (04 §16.0 API-S-Actor, rev 1.139;
dev-guide §6.4 DG-API-11).

A row names a principal by id: a user or an operator (``app_user.id``), an API client
(``api_client.id``) or nobody (NULL, the system). ``named`` is the SQL expression that reads who an
id column names inside the statement that reads the row — one scalar lookup on the primary key of
each identity table — so a page costs no statement per row and none per page, and a client never
resolves an id through another route. ``actor`` builds API-S-Actor from the id, the kind the row
stores (where it stores one) and that lookup. ``member`` and ``member_actor`` do the same for a row
that names a person by membership (``exception_item.owner_membership_id``).

The name is ``app_user.display_name`` as it stands when the row is read — for an anonymised person
the 05 PRV-07 (a) value ``Erased user <8 hex>``; a name is never taken from an event or audit
payload — or ``api_client.name``. ``app_user`` has no row-level security (RLS-NONE-U) and
``api_client`` is scoped by tenant alone (RLS-T), so a reader scoped to one legal entity resolves
every Actor of a row it may read. An id neither table answers shows the system name under the
stored kind, as ``approval_queries.actor`` does; nothing here raises.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.dialects.postgresql import JSONB

from erev_api.auth.principal import SYSTEM_DISPLAY_NAME
from erev_api.db.tables import api_client, app_user, tenant_membership
from erev_api.enums import PrincipalKind

__all__ = ["actor", "member", "member_actor", "named"]

KIND: Final = "kind"
DISPLAY_NAME: Final = "display_name"


# What ``app_user`` says a person is: an operator identity acts in a workspace only as OPERATOR
# (under a support grant), any other only as USER.
_USER_KIND: Final = case(
    (app_user.c.is_operator, PrincipalKind.OPERATOR.value), else_=PrincipalKind.USER.value
)


def named(principal_id: ColumnElement[Any], *, tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
    """``{kind, display_name}`` of the principal ``principal_id`` names, NULL for no id and for an
    id that is neither a user nor an API client of the row's tenant. ``kind`` is what the identity
    tables say: ``OPERATOR`` or ``USER`` for an ``app_user`` row, ``API_CLIENT`` for an
    ``api_client`` row. The lookup is correlated to whatever ``principal_id`` and ``tenant_id``
    are columns of — a table, or a derived table such as the actors of a range of the audit log:
    it is a column of a statement that selects from that."""
    user = (
        select(func.jsonb_build_object(KIND, _USER_KIND, DISPLAY_NAME, app_user.c.display_name))
        .where(app_user.c.id == principal_id)
        .correlate_except(app_user)
        .scalar_subquery()
    )
    client = (
        select(
            func.jsonb_build_object(
                KIND, PrincipalKind.API_CLIENT.value, DISPLAY_NAME, api_client.c.name
            )
        )
        .where(api_client.c.tenant_id == tenant_id, api_client.c.id == principal_id)
        .correlate_except(api_client)
        .scalar_subquery()
    )
    return func.coalesce(user, client, type_=JSONB)


def member(
    membership_id: ColumnElement[Any], *, tenant_id: ColumnElement[Any]
) -> ColumnElement[Any]:
    """``{id, kind, display_name}`` of the person behind the membership ``membership_id`` names —
    ``tenant_membership.user_id`` and the name this workspace is shown of that person
    (``users.SHOWN_NAME``: the email for a membership that is INVITED or REMOVED and whose
    invitation did not create the identity; dev-guide DG-KRN-DB-13) — NULL for no membership.
    Read like ``named``, in the statement that reads the row."""
    # Imported where it is used: the users module's imports reach this one.
    from erev_api.domain.platform import users  # noqa: PLC0415

    joined = tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
    return (
        select(
            func.jsonb_build_object(
                "id",
                app_user.c.id,
                KIND,
                _USER_KIND,
                DISPLAY_NAME,
                users.SHOWN_NAME,
                type_=JSONB,
            )
        )
        .select_from(joined)
        .where(tenant_membership.c.tenant_id == tenant_id, tenant_membership.c.id == membership_id)
        .correlate_except(tenant_membership, app_user)
        .scalar_subquery()
    )


def actor(principal_id: Any, kind: Any, found: Mapping[str, Any] | None) -> dict[str, Any]:
    """API-S-Actor of ``principal_id``. ``kind`` is the kind the row stores beside the id, or None
    for a column without one (SC-V ``published_by``, T-PLT-19 ``on_behalf_of_id``): the kind is then
    the one ``named`` found. ``found`` is the row's ``named`` value.

    No id is the system. An id nobody answers keeps its stored kind — ``USER`` without one, the only
    kind those columns are written with besides the ones the lookup finds — and shows the system
    name."""
    stored = None if kind is None else str(getattr(kind, "value", kind))
    if principal_id is None:
        return {
            "id": None,
            KIND: stored or PrincipalKind.SYSTEM.value,
            DISPLAY_NAME: SYSTEM_DISPLAY_NAME,
        }
    return {
        "id": principal_id if isinstance(principal_id, UUID) else UUID(str(principal_id)),
        KIND: stored or (PrincipalKind.USER.value if found is None else str(found[KIND])),
        DISPLAY_NAME: SYSTEM_DISPLAY_NAME if found is None else str(found[DISPLAY_NAME]),
    }


def member_actor(found: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """API-S-Actor of a row's ``member`` value; None where the row names no membership."""
    return None if found is None else actor(found["id"], found[KIND], found)
