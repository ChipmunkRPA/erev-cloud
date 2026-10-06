"""RPT-24 ``user_access_listing`` User access listing (SCREENS_B §5.6.5 RPT-24; 04 T-PLT-02,
T-PLT-04, T-PLT-07, T-PLT-09, T-PLT-10, T-PLT-14, SMAP-14; PRD J-01.3, J-17.6, BR-PLT-02; D-80; 03
REQ-PLT-008, REQ-PLT-012, REQ-RPT-022, REQ-CTL-006; research 07 AC-04, A-15; BUILD_SPEC RPS-10).

One row per membership and role assignment in force at ``as_of`` (default: the run's ``known_at``;
a later instant is refused): ``valid_from <= as_of``, not revoked by ``as_of`` and ``valid_to``
later — an assignment revoked afterwards still counts and shows its ``revoked_at`` (D-80 rule 2).
Every membership that existed at ``as_of`` is listed: a member without a role in force then has
one row without a role. A membership removed by ``as_of`` is left out unless ``include_removed``;
it then lists, per role, its latest assignment granted by ``as_of``. With entities in the run's
scope a role row is kept when its assignment covers all entities or one of them, and a member
whose roles all lie outside those entities is left out. Rows are ordered by email and role code;
``row_key`` ``access:<email>:<role code>``.

Removed at ``as_of`` (04 T-PLT-07 rev 1.307; item ACCESS-LISTING-SECOND-LIFE-1). The row says
it of a member who is removed now: ``REMOVED`` with ``removed_at`` by then. It keeps that one
removal only — a removed person is invited again on the same membership and ``removed_at`` goes
back to NULL (T-PLT-07 "Invited again") — so an earlier removal is read from the trail: the
``tenant_membership.invite`` event whose ``before`` states ``REMOVED`` carries the removal's
instant, and its own time ends the interval. A membership removed and invited again several
times has one such event each time. Read from the row alone, an ``as_of`` inside an ended
removal listed the person as a member without a role and counted the membership (measured:
``membership_count`` 7 to 8 and ``assignment_count`` 10 to 9 after a later invitation). The
trail states that interval and nothing else — the Membership cell stays the status at the run's
cutoff — and it is the one read here that the cutoff does not bound (``ended_removals``).

- ``entity_scope`` holds the entity codes of the assignment, empty for all entities ("All
  entities" in XLSX and PDF). ``granted_at`` is the assignment's ``valid_from``.
- ``granted_by`` names who approved the grant: the approver of the final approving decision of its
  ``ROLE_ASSIGNMENT`` request; "Setup grant (AUTO-BOOTSTRAP)" when rule ``AUTO-BOOTSTRAP``
  approved it while setup was incomplete (BR-PLT-02); another rule's key for any other
  auto-approval; empty for an assignment without an approving decision.
- ``as_of`` selects the role assignments. ``membership_status`` (E-78), ``mfa_enrolled`` (a
  confirmed factor that is not disabled) and ``last_login_at`` are the values recorded at the
  run's record cutoff. A membership that is INVITED or REMOVED shows no MFA state and no last
  sign-in of the person, as API-S-User shows none (D-80 rule 5 by the membership's status; 04
  T-PLT-02 rev 1.316): the two cells are ``NOT_SHOWN`` — null in the API and empty in CSV,
  "Not shown" in XLSX and PDF, where "Never" would be untrue. They go by the row's OWN
  ``membership_status``, so the dataset decides the printed cell and two runs with equal
  datasets print equal files (REQ-RPT-002). The name is the email unless this membership's
  invitation created the identity.

Control totals ``membership_count`` (memberships listed), ``assignment_count`` (role rows) and the
``as_of`` applied. T-PLT-07 and T-PLT-02 keep no history of the status, name or last sign-in, so an
explicit historical run whose cutoff precedes the last change of a membership in scope, or of its
person, is refused by name (REGISTER-CUTOFF-1); a live run never refuses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    app_user,
    audit_event,
    legal_entity,
    role,
    role_assignment,
    tenant_membership,
    user_mfa_factor,
)
from erev_api.domain.platform import approval_queries, provisioning, users
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import NOT_SHOWN, Column, ReportData, utc_text
from erev_api.enums import MembershipStatus
from erev_api.uow import UnitOfWork

CODE: Final = "user_access_listing"
ROW_KEY_PREFIX: Final = "access:"  # RPT-24: row_key `access:<email>:<role code>`
ALL_ENTITIES: Final = "All entities"
NEVER: Final = "Never"
SETUP_GRANT: Final = f"Setup grant ({provisioning.AUTO_BOOTSTRAP})"  # BR-PLT-02 "Setup grants"
REMOVED: Final = MembershipStatus.REMOVED.value
# The statuses in which the person is not a member now: the rule's own (``users.SIGN_IN_WITHHELD``).
NOT_A_MEMBER_NOW: Final = frozenset(users.WITHHELD_STATUSES)
HISTORY_UNAVAILABLE: Final = (
    "The user access listing cannot state the membership of {email} as of {cutoff}: the "
    "membership or its person last changed at {changed_at}, after the cutoff, and T-PLT-07 and "
    "T-PLT-02 keep no history of the status, name or last sign-in (not reconstructed). Run the "
    "listing at a later known_at or current; choose the instant of the role assignments with "
    "as_of."
)
COLUMNS: Final = (
    Column("display_name", "User", "text"),
    Column("email", "Email", "code"),
    Column("membership_status", "Membership", "code"),
    Column("role_name", "Role", "text"),
    Column("entity_scope", "Entity scope", "codes", empty_text=ALL_ENTITIES),
    Column("granted_at", "Granted", "timestamp"),
    Column("granted_by", "Granted by", "text"),
    Column("sod_exception_id", "SoD exception", "code"),
    Column("mfa_enrolled", "MFA enrolled", "boolean"),
    Column("last_login_at", "Last login", "timestamp", empty_text=NEVER),
    Column("revoked_at", "Revoked", "timestamp"),
)


@dataclass(frozen=True, slots=True)
class Grant:
    """One role assignment of a membership as the listing reads it."""

    role_code: str
    role_name: str
    is_all_entities: bool
    entity_codes: tuple[str, ...]
    granted_at: datetime
    granted_by: str | None
    sod_exception_id: UUID | None
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class Member:
    """One membership with its grants — the input of ``dataset_rows``."""

    email: str
    display_name: str
    status: str
    mfa_enrolled: bool | None
    last_login_at: datetime | None
    grants: tuple[Grant, ...]


def in_force(row: Mapping[str, Any], at: datetime) -> bool:
    """The assignment was in force at ``at`` (D-80 rule 2). Pure."""
    return bool(
        row["valid_from"] <= at
        and (row["revoked_at"] is None or row["revoked_at"] > at)
        and (row["valid_to"] is None or row["valid_to"] > at)
    )


def removed_by(
    row: Mapping[str, Any], at: datetime, ended: Sequence[tuple[datetime, datetime]] = ()
) -> bool:
    """The membership was removed at ``at``: REMOVED with ``removed_at`` by then, or ``at`` lies
    inside a removal that a later invitation ended — ``ended`` holds each as (removed, invited
    again), from the trail (``ended_removals``). Pure."""
    if any(removed <= at < invited_again for removed, invited_again in ended):
        return True
    return bool(
        support.text(row["status"]) == REMOVED
        and row["removed_at"] is not None
        and row["removed_at"] <= at
    )


def changed_at(row: Mapping[str, Any]) -> datetime:
    """The last change of a membership row or, unless its identity is withheld, of its person.
    Pure."""
    moments: list[datetime] = [row["updated_at"]]
    if not row["identity_withheld"]:
        moments.append(row["user_updated_at"])
    return max(moments)


def listed_assignments(
    rows: Sequence[Mapping[str, Any]], *, at: datetime, removed: bool
) -> list[Mapping[str, Any]]:
    """The assignments of one membership the listing shows, in role-code order: those in force at
    ``at``; for a membership removed by then, per role the latest one granted by ``at``. Pure."""
    if not removed:
        kept = [row for row in rows if in_force(row, at)]
    else:
        latest: dict[str, Mapping[str, Any]] = {}
        for row in sorted(rows, key=lambda item: (item["valid_from"], str(item["id"]))):
            if row["valid_from"] <= at:
                latest[str(row["role_code"])] = row
        kept = list(latest.values())
    return sorted(kept, key=lambda row: (str(row["role_code"]), row["valid_from"], str(row["id"])))


def covers(row: Mapping[str, Any], entity_ids: frozenset[UUID]) -> bool:
    """The assignment covers an entity of the run; every assignment without run entities. Pure."""
    if not entity_ids or row["is_all_entities"]:
        return True
    return bool(entity_ids & {UUID(str(value)) for value in row["entity_ids"] or ()})


def grantor(decision: Mapping[str, Any] | None, names: Mapping[UUID, str]) -> str | None:
    """``granted_by`` of an assignment from its request's final approving decision. Pure."""
    if decision is None:
        return None
    if users.is_setup_grant(decision):
        return SETUP_GRANT
    if decision["rule_key"] is not None:
        return str(decision["rule_key"])
    shown = approval_queries.actor(
        support.uuid_of(decision["approver_id"]),
        str(support.text(decision["approver_kind"])),
        names,
    )
    return str(shown["display_name"])


def dataset_rows(found: Iterable[Member]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in email and role-code order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    memberships = 0
    assignments = 0
    for member in sorted(found, key=lambda item: item.email):
        memberships += 1
        # By the row's own status, the one it prints: never by what the member carries.
        hidden = member.status in NOT_A_MEMBER_NOW
        shared = {
            "display_name": member.display_name,
            "email": member.email,
            "membership_status": member.status,
            "mfa_enrolled": NOT_SHOWN if hidden else member.mfa_enrolled,
            "last_login_at": NOT_SHOWN if hidden else member.last_login_at,
        }
        if not member.grants:
            rows.append({"row_key": f"{ROW_KEY_PREFIX}{member.email}:", **shared})
            continue
        for grant in member.grants:
            assignments += 1
            rows.append(
                {
                    "row_key": f"{ROW_KEY_PREFIX}{member.email}:{grant.role_code}",
                    **shared,
                    "role_name": grant.role_name,
                    "entity_scope": () if grant.is_all_entities else grant.entity_codes,
                    "granted_at": grant.granted_at,
                    "granted_by": grant.granted_by,
                    "sod_exception_id": (
                        None if grant.sod_exception_id is None else str(grant.sod_exception_id)
                    ),
                    "revoked_at": grant.revoked_at,
                }
            )
    return rows, {"membership_count": memberships, "assignment_count": assignments}


def _assignments(
    session: Session, membership_ids: Sequence[UUID], *, cutoff: datetime
) -> dict[UUID, list[dict[str, Any]]]:
    if not membership_ids:
        return {}
    statement = (
        select(role_assignment, role.c.code.label("role_code"), role.c.name.label("role_name"))
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            )
        )
        .where(
            role_assignment.c.membership_id.in_(list(membership_ids)),
            role_assignment.c.created_at <= cutoff,
        )
        .order_by(role.c.code, role_assignment.c.valid_from, role_assignment.c.id)
    )
    found: dict[UUID, list[dict[str, Any]]] = {}
    for row in session.execute(statement).mappings():
        item = dict(row)
        if item["revoked_at"] is not None and item["revoked_at"] > cutoff:
            item["revoked_at"] = None  # revoked after the record cutoff
        found.setdefault(UUID(str(row["membership_id"])), []).append(item)
    return found


def ended_removals(session: Session) -> dict[UUID, list[tuple[datetime, datetime]]]:
    """Per membership, the removals a later invitation ended, each as (removed, invited again)
    in the order they happened (module docstring). One command writes the event,
    ``users.invite_user``: its ``before`` holds the status it found and the ``removed_at`` it
    cleared, and the event's own time is the invitation's. The same action is also a first
    invitation and the DENIED event of a refused one; neither has a ``before``, so the status it
    states selects the event. An event without the removal's instant states no interval.

    NOT bounded by the run's record cutoff, unlike every other read of this builder (04 T-PLT-07
    rev 1.307; the supervisor's ruling of 2026-10-02 on the lane's finding). The event is read
    to recover a state the row has overwritten, not to learn a later one: an interval holds
    ``as_of`` only if its removal is at or before it, and ``as_of`` is at or before the cutoff,
    so an event recorded after the cutoff tells the run nothing but a removal that was on
    record at it. Bounded by the event's time, the read would drop exactly the invitation that
    ended a removal standing at the cutoff — and the membership would read as never removed."""
    statement = (
        select(audit_event.c.object_id, audit_event.c.before, audit_event.c.occurred_at)
        .where(
            audit_event.c.action == users.INVITE_ACTION,
            audit_event.c.before["status"].astext == REMOVED,
        )
        .order_by(audit_event.c.occurred_at, audit_event.c.chain_seq)
    )
    found: dict[UUID, list[tuple[datetime, datetime]]] = {}
    for membership_id, before, invited_again in session.execute(statement):
        removed = before.get("removed_at")
        if not isinstance(removed, str):
            continue
        found.setdefault(UUID(str(membership_id)), []).append(
            (datetime.fromisoformat(removed), invited_again)
        )
    return found


def _enrolled(session: Session, user_ids: Sequence[UUID], *, cutoff: datetime) -> set[UUID]:
    if not user_ids:
        return set()
    statement = select(user_mfa_factor.c.user_id).where(
        user_mfa_factor.c.user_id.in_(list(user_ids)),
        user_mfa_factor.c.confirmed_at.is_not(None),
        user_mfa_factor.c.confirmed_at <= cutoff,
        or_(user_mfa_factor.c.disabled_at.is_(None), user_mfa_factor.c.disabled_at > cutoff),
    )
    return {UUID(str(value)) for value in session.scalars(statement)}


def _entity_codes(session: Session, rows: Iterable[Mapping[str, Any]]) -> dict[UUID, str]:
    ids = sorted({UUID(str(value)) for row in rows for value in row["entity_ids"] or ()}, key=str)
    if not ids:
        return {}
    statement = select(legal_entity.c.id, legal_entity.c.code).where(legal_entity.c.id.in_(ids))
    return {UUID(str(entity_id)): str(code) for entity_id, code in session.execute(statement)}


def members(uow: UnitOfWork, params: ReportParams, *, at: datetime) -> list[Member]:
    """Every membership in scope with the grants the listing shows (module docstring)."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    include_removed = bool(params.parameters.get("include_removed", False))
    people = [
        dict(row)
        for row in session.execute(
            users.member_select()
            .add_columns(app_user.c.updated_at.label("user_updated_at"))
            .where(tenant_membership.c.created_at <= cutoff, tenant_membership.c.invited_at <= at)
            .order_by(tenant_membership.c.id)
        ).mappings()
    ]
    if params.historical:
        for row in people:  # REGISTER-CUTOFF-1: inspected before any filter
            if changed_at(row) > cutoff:
                raise tie_outs.invalid(
                    "known_at",
                    HISTORY_UNAVAILABLE.format(
                        email=row["email"],
                        cutoff=cutoff.isoformat(),
                        changed_at=changed_at(row).isoformat(),
                    ),
                )
    assignments = _assignments(session, [UUID(str(row["id"])) for row in people], cutoff=cutoff)
    ended = ended_removals(session)
    run_entities = frozenset(params.entity_ids)
    shown: dict[UUID, list[Mapping[str, Any]]] = {}
    for row in people:
        membership_id = UUID(str(row["id"]))
        removed = removed_by(row, at, ended.get(membership_id, ()))
        if removed and not include_removed:
            continue
        kept = listed_assignments(assignments.get(membership_id, []), at=at, removed=removed)
        scoped = [item for item in kept if covers(item, run_entities)]
        if kept and not scoped:
            continue  # every role of the member lies outside the run's entities
        shown[membership_id] = scoped
    every = [item for kept in shown.values() for item in kept]
    granting = users.granting_decisions(session, [item["approval_request_id"] for item in every])
    names = approval_queries.display_names(
        session, [support.uuid_of(decision["approver_id"]) for decision in granting.values()]
    )
    codes = _entity_codes(session, every)
    listed = [row for row in people if UUID(str(row["id"])) in shown]
    enrolled = _enrolled(session, [UUID(str(row["user_id"])) for row in listed], cutoff=cutoff)
    found: list[Member] = []
    for row in listed:
        grants = tuple(
            Grant(
                role_code=str(item["role_code"]),
                role_name=str(item["role_name"]),
                is_all_entities=bool(item["is_all_entities"]),
                entity_codes=tuple(
                    sorted(
                        codes.get(UUID(str(value)), str(value))
                        for value in item["entity_ids"] or ()
                    )
                ),
                granted_at=item["valid_from"],
                granted_by=grantor(granting.get(item["approval_request_id"]), names),
                sod_exception_id=support.uuid_of(item["sod_exception_id"]),
                revoked_at=item["revoked_at"],
            )
            for item in shown[UUID(str(row["id"]))]
        )
        found.append(
            Member(
                email=str(row["email"]),
                display_name=str(row["display_name"]),
                status=str(support.text(row["status"])),
                # Whether the row shows it is decided where the row is written (``dataset_rows``).
                mfa_enrolled=UUID(str(row["user_id"])) in enrolled,
                last_login_at=row["last_login_at"],
                grants=grants,
            )
        )
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    at = support.as_of_instant(params)
    rows, totals = dataset_rows(members(uow, params, at=at))
    totals["as_of"] = utc_text(at)
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "SETUP_GRANT",
    "Grant",
    "Member",
    "build",
    "changed_at",
    "covers",
    "dataset_rows",
    "ended_removals",
    "grantor",
    "in_force",
    "listed_assignments",
    "members",
    "removed_by",
]
