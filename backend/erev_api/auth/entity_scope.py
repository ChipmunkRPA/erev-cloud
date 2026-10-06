"""The entity scope of a grant: all entities, or a named subset (04 T-PLT-10, T-PLT-15, DB-12; 03
REQ-PLT-012; PRD J-22.1; supervisor ruling R-63 (e)).

A role assignment and an API client cover every legal entity of the workspace or the entities the
grant names. The names arrive as entity codes; ``resolve`` is the one place a command turns them
into the ids the row stores, so every path that creates a grant applies the same three rules:

- the request states one of the two shapes — all entities and no code, or not all entities and at
  least one code (T-PLT-10 ``ck_role_assignment__entity_ids``);
- every code names a legal entity of the workspace (DB-12, ``EREV-REF-002``);
- nobody grants beyond their own access: a grantor who holds the granting permission for named
  entities only grants those entities and never all entities (REQ-PLT-012). An entity outside the
  grantor's own scope is refused exactly as a code that does not exist.

``resolve`` collects findings (DG-CMD-03) and writes nothing. ``refs`` gives the API-S-Ref members
a read shows for a stored scope.

The same rule guards what is already granted (supervisor ruling R-63 (e) as refined by R-115 (c)):
a command on a role assignment needs the actor's permission for every entity the assignment
names, and a command on a membership for every entity any of the member's assignments names — an
all-entities scope needs the permission for all entities. ``covers`` is that test and ``assigned``
reads a member's scopes; the commands refuse by name (403, rule ``T-PLT-10``). A tenant-wide act
on access — the definition of a role — needs the permission for all entities (``holds_all``), and
a command on an entity's row its permission for that entity (``holds_for``; ruling R-28).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.auth.principal import Principal
from erev_api.db.tables import legal_entity, role_assignment
from erev_api.enums import PrincipalKind
from erev_api.problems import ProblemError

RULE_ENTITY: Final = "EREV-REF-002"  # 04 DB-12: the ids of a scope are legal entities
RULE_SHAPE: Final = "T-PLT-10"  # all entities, or at least one named entity
# Nobody grants beyond their own access (03 REQ-PLT-012): stated under the table's rule id — a
# requirement id is a rule id only where a PRD §5.5 row names it (04 §15.4).
RULE_OWN_SCOPE: Final = RULE_SHAPE
# [J] SPEC-Q-182: copy the documents leave open.
ENTITY_UNKNOWN: Final = "Choose entities that exist in this workspace."
ENTITIES_EMPTY: Final = "Choose at least one entity, or all entities."
ALL_AND_NAMED: Final = "Choose all entities or named entities, not both."
BEYOND_OWN_SCOPE: Final = (
    "Your own access covers named entities only. Choose from those entities, not all entities."
)
type HeldScope = Literal["*"] | frozenset[UUID]


@dataclass(frozen=True, slots=True)
class EntityScope:
    """The scope a grant stores: ``entity_ids`` is empty exactly when ``is_all_entities``; ids and
    codes are in code order."""

    is_all_entities: bool
    entity_ids: tuple[UUID, ...] = ()
    entity_codes: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """The scope in a sentence: "all entities" or the codes, for an approval summary."""
        return "all entities" if self.is_all_entities else ", ".join(self.entity_codes)


ALL_ENTITIES: Final = EntityScope(is_all_entities=True)


def held_scope(principal: Principal, permission: str) -> HeldScope:
    """The entities ``principal`` holds ``permission`` for. The SYSTEM principal — provisioning or
    a job, which holds no permission and acts for the tenant — covers every entity; a principal
    without the permission covers none."""
    if principal.kind is PrincipalKind.SYSTEM:
        return "*"
    return principal.permission_scopes.get(permission, frozenset())


def holds_all(principal: Principal, permission: str) -> bool:
    """Whether ``principal`` holds ``permission`` for all entities: what a tenant-wide act needs —
    the definition of a role, a tenant-wide list (supervisor rulings R-28 and R-115 (c))."""
    return held_scope(principal, permission) == "*"


def holds_for(principal: Principal, permissions: Iterable[str], entity_id: UUID) -> bool:
    """Whether ``principal`` holds one of ``permissions`` for ``entity_id``: a command on a row of
    an entity needs its permission FOR that entity, not the permission for another entity and
    some role on this one (supervisor ruling R-28; security finding S18)."""
    for permission in permissions:
        scope = held_scope(principal, permission)
        if scope == "*" or entity_id in scope:
            return True
    return False


def decided(
    *,
    held: HeldScope,
    is_all_entities: bool,
    entity_codes: Sequence[str],
    known: Mapping[str, UUID],
    field: str,
    shape_field: str | None = None,
) -> tuple[EntityScope | None, list[ProblemError]]:
    """The three rules of the module docstring over ``known``, the legal entities of the workspace
    by code: the scope a request names, or the findings that refuse it. Pure."""
    codes = sorted({str(code) for code in entity_codes})
    if is_all_entities:
        if codes:
            return None, [ProblemError(field=field, rule_id=RULE_SHAPE, message=ALL_AND_NAMED)]
        if held != "*":
            return None, [
                ProblemError(
                    field=shape_field or field, rule_id=RULE_OWN_SCOPE, message=BEYOND_OWN_SCOPE
                )
            ]
        return ALL_ENTITIES, []
    if not codes:
        return None, [ProblemError(field=field, rule_id=RULE_SHAPE, message=ENTITIES_EMPTY)]
    grantable = {
        code: known[code]
        for code in codes
        if code in known and (held == "*" or known[code] in held)
    }
    if len(grantable) != len(codes):
        # an entity outside the grantor's own scope answers as one that does not exist
        return None, [ProblemError(field=field, rule_id=RULE_ENTITY, message=ENTITY_UNKNOWN)]
    return (
        EntityScope(
            is_all_entities=False,
            entity_ids=tuple(grantable[code] for code in codes),
            entity_codes=tuple(codes),
        ),
        [],
    )


def reaches_beyond(
    held: HeldScope,
    *,
    is_all_entities: bool,
    entity_codes: Sequence[str],
    scope: EntityScope | None,
) -> bool:
    """Whether a refused grant request reached beyond the grantor's own scope: a grantor of named
    entities asked for all entities, or named a code it does not cover. The command records such
    a request as a denial (DG-KRN-AUTH-05) and answers the 422 it answers anyway.

    A code the grantor does not cover counts whether or not it names an entity: the grantor may
    read the audit log, so an event written only for a code that exists would tell what the
    answer withholds. A grantor of all entities reaches beyond nothing — its unknown code is a
    mistake — and a request that states both shapes or neither is malformed, not a reach. Pure."""
    if held == "*" or scope is not None:
        return False
    return is_all_entities != bool(entity_codes)


def resolve(
    session: Session,
    *,
    held: HeldScope,
    is_all_entities: bool,
    entity_codes: Sequence[str],
    field: str,
    shape_field: str | None = None,
) -> tuple[EntityScope | None, list[ProblemError]]:
    """``decided`` over the legal entities the request's codes name. ``held`` is the grantor's own
    scope for the granting permission (``held_scope``); ``field`` is the request member of the
    codes and ``shape_field`` the member of the all-entities flag (default ``field``)."""
    codes = sorted({str(code) for code in entity_codes})
    known: dict[str, UUID] = {}
    if codes and not is_all_entities:
        known = {
            str(code): UUID(str(entity_id))
            for entity_id, code in session.execute(
                select(legal_entity.c.id, legal_entity.c.code).where(legal_entity.c.code.in_(codes))
            )
        }
    return decided(
        held=held,
        is_all_entities=is_all_entities,
        entity_codes=codes,
        known=known,
        field=field,
        shape_field=shape_field,
    )


def names(session: Session, entity_ids: Iterable[Any]) -> dict[UUID, Mapping[str, Any]]:
    """API-S-Ref (``id``, ``code``, ``name``) of each legal entity of ``entity_ids`` the session
    reads, by id: one read for a page of grants."""
    ids = sorted({UUID(str(value)) for value in entity_ids}, key=str)
    if not ids:
        return {}
    return {
        UUID(str(row["id"])): dict(row)
        for row in session.execute(
            select(legal_entity.c.id, legal_entity.c.code, legal_entity.c.name).where(
                legal_entity.c.id.in_(ids)
            )
        ).mappings()
    }


def refs(
    found: Mapping[UUID, Mapping[str, Any]], entity_ids: Iterable[Any]
) -> list[dict[str, Any]]:
    """The API-S-Ref list of one stored scope from ``names``, in code order. An id ``found`` does
    not hold is an entity the reader's session does not cover: it is left out."""
    shown = [found[key] for value in entity_ids if (key := UUID(str(value))) in found]
    return [dict(item) for item in sorted(shown, key=lambda item: str(item["code"]))]


def codes(found: Mapping[UUID, Mapping[str, Any]], entity_ids: Iterable[Any]) -> list[str]:
    """The entity codes of one stored scope from ``names``, sorted — for evidence that states a
    scope in full (an access review's snapshot): an entity the reader's session does not cover is
    stated by its id, as RPT-24 states it, never dropped."""
    return sorted(
        str(found[key]["code"]) if (key := UUID(str(value))) in found else str(key)
        for value in entity_ids
    )


def covers(held: HeldScope, scopes: Iterable[tuple[bool, Iterable[Any]]]) -> bool:
    """Whether ``held`` covers every scope of ``scopes`` — pairs of ``is_all_entities`` and entity
    ids: all entities cover everything; named entities cover a scope that names none but them and
    never an all-entities scope. No scope at all is covered by anyone. Pure."""
    if held == "*":
        return True
    for is_all_entities, entity_ids in scopes:
        if is_all_entities or any(UUID(str(value)) not in held for value in entity_ids):
            return False
    return True


def assigned(session: Session, membership_id: UUID) -> list[tuple[bool, tuple[UUID, ...]]]:
    """The scopes of a member's role assignments that are not revoked (T-PLT-10)."""
    return [
        (bool(is_all_entities), tuple(UUID(str(value)) for value in entity_ids or ()))
        for is_all_entities, entity_ids in session.execute(
            select(role_assignment.c.is_all_entities, role_assignment.c.entity_ids).where(
                role_assignment.c.membership_id == membership_id,
                role_assignment.c.revoked_at.is_(None),
            )
        )
    ]
