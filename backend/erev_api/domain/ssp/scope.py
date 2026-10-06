"""The reach of an SSP book (04 T-REF-28 and API-R-26 rev 1.277; supervisor ruling R-28, row N-29
of the ruled repairs; item SSP-ENTITY-SCOPE-1; 03 REQ-PLT-012).

T-REF-28 to T-REF-31 are RLS-T: no row policy knows the entity a book is for. A book of an entity
(``ssp_book.entity_id``) is listed, read and commanded only by a member whose permission covers
that entity — ``ssp.read`` for a read, ``ssp.create`` for a command: the route's own permission,
asked FOR THAT ENTITY (ruling R-28: not the permission for another entity and some role on this
one). For anyone else the book is absent: the list leaves it out, and every read and command that
names it, one of its versions or one of their entries answers 404 ``not-found``, as for an id that
names none (API-C-03). A book of all entities (``entity_id`` NULL) is the workspace's
configuration and stays reached under the permission held for any entity, as before.

Measured before (lane F-RPS-REG's row 5 and this lane's probe of 2026-10-02): an SSP Analyst of
one entity listed the book of another with ``entity_code`` null — the join to an entity her
session does not read hid the scope, so the book read as one of all entities — renamed it, created
a DRAFT version on it and read its approved prices.

The principal's scope is the kernel's (``auth.entity_scope.held_scope``): SYSTEM, which holds no
permission and acts for the tenant — the commit of an import, a seed — reaches every book.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, or_, select, true

from erev_api.auth import entity_scope
from erev_api.db.tables import ssp_book, ssp_book_version
from erev_api.problems import Problem

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.orm import Session

    from erev_api.auth.principal import Principal

READ: Final = "ssp.read"
CREATE: Final = "ssp.create"


def in_reach(principal: Principal, permission: str) -> ColumnElement[bool]:
    """``reaches`` in SQL, over ``ssp_book``: the books of all entities, and the books of the
    entities ``permission`` is held for."""
    held = entity_scope.held_scope(principal, permission)
    if held == "*":
        return true()
    return or_(ssp_book.c.entity_id.is_(None), ssp_book.c.entity_id.in_(sorted(held)))


def reaches(principal: Principal, permission: str, entity_id: Any) -> bool:
    """Whether ``principal`` reaches a book of ``entity_id`` under ``permission``. A book of all
    entities (None) is reached by every caller the route's guard admitted."""
    if entity_id is None:
        return True
    return entity_scope.holds_for(principal, (permission,), UUID(str(entity_id)))


def require_book(
    session: Session, principal: Principal, permission: str, book_id: UUID, *, lock: bool = False
) -> Mapping[str, Any]:
    """The book's row — locked ``FOR UPDATE`` when asked — or 404 ``not-found``: for an id that
    names no book, and for a book out of the principal's reach."""
    statement = select(ssp_book).where(ssp_book.c.id == book_id)
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None or not reaches(principal, permission, row["entity_id"]):
        raise Problem("not-found")
    return dict(row)


def require_version_book(
    session: Session, principal: Principal, permission: str, version_id: UUID
) -> UUID:
    """The id of the book of version ``version_id``, or 404 ``not-found``: for an id that names
    no version, and for a version of a book out of the principal's reach."""
    row = session.execute(
        select(ssp_book.c.id, ssp_book.c.entity_id)
        .select_from(
            ssp_book_version.join(
                ssp_book,
                and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
        )
        .where(ssp_book_version.c.id == version_id)
    ).one_or_none()
    if row is None or not reaches(principal, permission, row.entity_id):
        raise Problem("not-found")
    return UUID(str(row.id))
