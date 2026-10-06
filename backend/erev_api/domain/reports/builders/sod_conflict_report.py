"""RPT-25 ``sod_conflict_report`` SoD conflict report (SCREENS_B §5.6.5 RPT-25; 04 T-PLT-09,
T-PLT-10, T-PLT-12, T-PLT-13, T-PLT-14, T-PLT-21, E-96; PRD J-17.6, J-22.7, J-22.8, ERR-22; D-80;
dev-guide DG-KRN-PERM-02, DG-KRN-PERM-03; 03 REQ-PLT-010, REQ-RPT-022; research 07 AC-03, A-15;
CTL-034; BUILD_SPEC RPS-10).

One row per membership and SoD rule in conflict at ``as_of`` (default: the run's ``known_at``; a
later instant is refused). The conflicts are those of ``auth.sod.conflict_report``: the rule
versions in force at ``as_of`` (D-80 rule 1) against the permissions of the role assignments in
force then (D-80 rule 2: an assignment revoked afterwards still counts) and of the approval
delegations to the member that stood then (04 T-PLT-21; supervisor ruling R-111 (4): a permission
held through a delegation is held). With entities in the run's scope only the assignments covering
all entities or one of them count. A delegation counts for the permissions its delegator held at
``as_of`` through the assignments the run counts — the delegate decides with it only while the
delegator holds the permission (``approvals.engine.find_authority``) — so one whose delegator had
lost the permission, or holds it for other entities only, adds nothing. A conflict is listed when
what counts meets both functions. Rows are ordered by email and rule code; ``row_key``
``sod:<email>:<rule code>``.

- ``function_a_permissions`` and ``function_b_permissions`` are the permissions of each function
  the member holds; ``roles`` the names of the roles that grant them, joined with ", ".
- ``delegations`` names the delegations that give them (SCREENS_B rev 1.73): one entry per
  delegation, "<delegator> until <DD MMM YYYY>" — the UTC day of its ``valid_to`` — in the order
  of the delegator's name and the end, joined with ", "; empty when the conflict is held through
  roles alone.
- The exception columns describe the exception that covered the conflict at ``as_of``: approved by
  then, not revoked by then, with ``valid_from <= as_of < valid_to`` — the one ending last when
  several do. Its ``exception_status`` is the E-96 status at ``as_of``, ``APPROVED``, whatever
  happened to it afterwards; ``valid_from`` and ``valid_to`` are the UTC days of its validity
  instants. Without such an exception the five cells are empty ("None" for the id in XLSX and
  PDF) and the conflict counts as uncovered.

Control totals ``conflict_count``, ``uncovered_conflict_count`` and the ``as_of`` applied — the
instant the empty state names ("No member holds conflicting permissions at <as_of>."). A role's
permissions are the ones recorded at the run's record cutoff: T-PLT-12 keeps no history, so an
explicit historical run whose cutoff precedes the last change of a role held at ``as_of`` is
refused by name (REGISTER-CUTOFF-1); a live run never refuses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from erev_api.auth import sod as kernel
from erev_api.auth.permissions import standing_delegations
from erev_api.db.session import of_session_tenant
from erev_api.db.tables import (
    app_user,
    role,
    role_assignment,
    role_permission,
    sod_exception,
    sod_rule,
    tenant_membership,
)
from erev_api.domain.platform import users
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData, utc_text
from erev_api.enums import ConfigStatus, GrantStatus
from erev_api.uow import UnitOfWork

CODE: Final = "sod_conflict_report"
ROW_KEY_PREFIX: Final = "sod:"  # RPT-25: row_key `sod:<email>:<rule code>`
NONE: Final = "None"
COVERING: Final = GrantStatus.APPROVED.value
RULE_STATUSES: Final = (ConfigStatus.PUBLISHED.value, ConfigStatus.SUPERSEDED.value)
HISTORY_UNAVAILABLE: Final = (
    "The SoD conflict report cannot state the permissions of role {role} as of {cutoff}: the role "
    "last changed at {updated_at}, after the cutoff, and T-PLT-12 keeps no history (not "
    "reconstructed). Run the report at a later known_at or current; choose the instant of the "
    "role assignments with as_of."
)
COLUMNS: Final = (
    Column("display_name", "User", "text"),
    Column("rule_code", "Rule", "code"),
    Column("rule_name", "Rule name", "text"),
    Column("function_a_permissions", "Function A held", "codes"),
    Column("function_b_permissions", "Function B held", "codes"),
    Column("roles", "Through roles", "text"),
    Column("delegations", "Through delegations", "text"),
    Column("sod_exception_id", "Exception", "code", empty_text=NONE),
    Column("compensating_control", "Compensating control", "text"),
    Column("valid_from", "Valid from", "date"),
    Column("valid_to", "Valid to", "date"),
    Column("exception_status", "Status", "code"),
)


@dataclass(frozen=True, slots=True)
class Held:
    """One role a member holds at ``as_of`` with its permissions."""

    role_name: str
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class Delegated:
    """One delegation to a member that stood at ``as_of``: who gave it, when it ends and the
    permissions it counts for in this run."""

    delegator_name: str
    valid_to: datetime
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class Cover:
    """The exception covering a conflict at ``as_of``."""

    id: UUID
    compensating_control: str
    valid_from: datetime
    valid_to: datetime


@dataclass(frozen=True, slots=True)
class Conflict:
    """One conflict with its member, rule and cover resolved — the input of ``dataset_rows``."""

    email: str
    display_name: str
    rule_code: str
    rule_name: str
    function_a: frozenset[str]
    function_b: frozenset[str]
    held: tuple[Held, ...]
    cover: Cover | None
    delegated: tuple[Delegated, ...] = ()


def utc_day(moment: datetime) -> date:
    return moment.astimezone(UTC).date()


def held_permissions(held: Iterable[Held], delegated: Iterable[Delegated] = ()) -> frozenset[str]:
    found: set[str] = set()
    for item in held:
        found |= item.permissions
    for given in delegated:
        found |= given.permissions
    return frozenset(found)


def in_conflict(
    held: Iterable[Held],
    function_a: frozenset[str],
    function_b: frozenset[str],
    delegated: Iterable[Delegated] = (),
) -> bool:
    """The roles and the delegations together meet both functions (DG-KRN-PERM-02). Pure."""
    permissions = held_permissions(held, delegated)
    return bool(permissions & function_a and permissions & function_b)


def delegation_text(given: Delegated) -> str:
    """SCREENS_B RPT-25 "Through delegations": ``<delegator> until <DD MMM YYYY>`` — the UTC day
    of the delegation's end (DS-FMT-16). Pure."""
    return f"{given.delegator_name} until {utc_day(given.valid_to):%d %b %Y}"


def covering(rows: Iterable[Mapping[str, Any]], at: datetime) -> Mapping[str, Any] | None:
    """The exception of one membership and rule that covered at ``at``: approved by then, not
    revoked by then and valid then — the one ending last, then the lowest id (the kernel's
    order). Pure."""
    candidates = [
        row
        for row in rows
        if row["approved_at"] is not None
        and row["approved_at"] <= at
        and (row["revoked_at"] is None or row["revoked_at"] > at)
        and row["valid_from"] <= at < row["valid_to"]
    ]
    if not candidates:
        return None
    latest = max(row["valid_to"] for row in candidates)
    return min((row for row in candidates if row["valid_to"] == latest), key=lambda r: str(r["id"]))


def dataset_rows(found: Iterable[Conflict]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in email and rule-code order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    uncovered = 0
    for item in sorted(found, key=lambda conflict: (conflict.email, conflict.rule_code)):
        permissions = held_permissions(item.held, item.delegated)
        both = item.function_a | item.function_b
        row: dict[str, Any] = {
            "row_key": f"{ROW_KEY_PREFIX}{item.email}:{item.rule_code}",
            "display_name": item.display_name,
            "rule_code": item.rule_code,
            "rule_name": item.rule_name,
            "function_a_permissions": tuple(sorted(permissions & item.function_a)),
            "function_b_permissions": tuple(sorted(permissions & item.function_b)),
            "roles": support.joined(
                sorted({held.role_name for held in item.held if held.permissions & both})
            ),
            "delegations": support.joined(
                [
                    delegation_text(given)
                    for given in sorted(
                        item.delegated, key=lambda one: (one.delegator_name, one.valid_to)
                    )
                    if given.permissions & both
                ]
            ),
        }
        if item.cover is None:
            uncovered += 1
        else:
            row |= {
                "sod_exception_id": str(item.cover.id),
                "compensating_control": item.cover.compensating_control,
                "valid_from": utc_day(item.cover.valid_from),
                "valid_to": utc_day(item.cover.valid_to),
                "exception_status": COVERING,
            }
        rows.append(row)
    return rows, {"conflict_count": len(rows), "uncovered_conflict_count": uncovered}


def _held(
    session: Session, params: ReportParams, *, at: datetime, cutoff: datetime
) -> dict[UUID, list[Held]]:
    """Per membership, the active roles of its assignments in force at ``at`` that cover an entity
    of the run, each with its permissions."""
    statement = (
        select(
            role_assignment.c.membership_id,
            role_assignment.c.is_all_entities,
            role_assignment.c.entity_ids,
            role.c.id.label("role_id"),
            role.c.code.label("role_code"),
            role.c.name.label("role_name"),
            role.c.updated_at.label("role_updated_at"),
            role_permission.c.permission_code,
        )
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            ).join(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role.c.tenant_id,
                    role_permission.c.role_id == role.c.id,
                ),
            )
        )
        .where(
            role_assignment.c.valid_from <= at,
            or_(role_assignment.c.revoked_at.is_(None), role_assignment.c.revoked_at > at),
            or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > at),
            role.c.is_active.is_(True),
        )
        .order_by(role.c.code, role_permission.c.permission_code)
    )
    run_entities = frozenset(params.entity_ids)
    roles: dict[tuple[UUID, UUID], tuple[str, set[str]]] = {}
    for row in session.execute(statement).mappings():
        if params.historical and row["role_updated_at"] > cutoff:  # REGISTER-CUTOFF-1
            raise tie_outs.invalid(
                "known_at",
                HISTORY_UNAVAILABLE.format(
                    role=row["role_code"],
                    cutoff=cutoff.isoformat(),
                    updated_at=row["role_updated_at"].isoformat(),
                ),
            )
        covered = (
            not run_entities
            or row["is_all_entities"]
            or run_entities & {UUID(str(value)) for value in row["entity_ids"] or ()}
        )
        if not covered:
            continue
        key = (UUID(str(row["membership_id"])), UUID(str(row["role_id"])))
        roles.setdefault(key, (str(row["role_name"]), set()))[1].add(str(row["permission_code"]))
    found: dict[UUID, list[Held]] = {}
    for (membership_id, _), (name, permissions) in roles.items():
        found.setdefault(membership_id, []).append(Held(name, frozenset(permissions)))
    return found


def _delegated(
    session: Session, *, at: datetime, held: Mapping[UUID, Sequence[Held]]
) -> dict[UUID, list[Delegated]]:
    """Per delegate, the delegations that stood at ``at`` and had been given by then — the ones
    the kernel's report counts (``auth.sod.conflict_report``) — each with its delegator's name
    and the permissions it counts for: those of its permissions that its delegator held at
    ``at`` through the assignments the run counts (``held``). A delegation whose delegator had
    lost the permission, or holds it for other entities than the run's, counts for nothing and
    is left out. A delegation is revoked at an instant and never edited (IM-S), so the record
    cutoff of a historical run asks nothing more of it."""
    standing = [
        delegation
        for delegation in standing_delegations(session, at=at)
        if delegation.created_at <= at
    ]
    if not standing:
        return {}
    delegators = sorted({delegation.delegator_membership_id for delegation in standing}, key=str)
    # The delegator is named as the person who GAVE the delegation — the record of a delegation
    # given while the workspace read that name — and not as the workspace is shown a membership
    # now: a delegator removed since would read as an address in a register already reviewed
    # (the supervisor's ruling of 2026-10-02 on item IDENTITY-WITHHELD-BY-STATUS-1;
    # listed in ``tests/architecture/test_shown_identity.py``).
    names = {
        UUID(str(membership_id)): str(name)
        for membership_id, name in session.execute(
            select(tenant_membership.c.id, app_user.c.display_name)
            .select_from(
                tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
            )
            .where(of_session_tenant(tenant_membership), tenant_membership.c.id.in_(delegators))
        )
    }
    found: dict[UUID, list[Delegated]] = {}
    for delegation in standing:
        permissions = delegation.permissions & held_permissions(
            held.get(delegation.delegator_membership_id, ())
        )
        if not permissions:
            continue
        found.setdefault(delegation.delegate_membership_id, []).append(
            Delegated(
                delegator_name=names[delegation.delegator_membership_id],
                valid_to=delegation.valid_to,
                permissions=permissions,
            )
        )
    return found


def _rule_names(
    session: Session, conflicts: Sequence[tuple[UUID, kernel.SodConflict]]
) -> dict[tuple[str, frozenset[str], frozenset[str]], str]:
    """The name of each rule version in conflict, found by its code and functions; the latest
    version when several carry the same functions."""
    codes = sorted({conflict.rule_code for _, conflict in conflicts})
    if not codes:
        return {}
    statement = (
        select(
            sod_rule.c.code,
            sod_rule.c.name,
            sod_rule.c.function_a_permissions,
            sod_rule.c.function_b_permissions,
        )
        .where(sod_rule.c.code.in_(codes), sod_rule.c.status.in_(RULE_STATUSES))
        .order_by(sod_rule.c.code, sod_rule.c.version_no)
    )
    names: dict[tuple[str, frozenset[str], frozenset[str]], str] = {}
    for code, name, function_a, function_b in session.execute(statement):
        key = (
            str(code),
            frozenset(str(value) for value in function_a),
            frozenset(str(value) for value in function_b),
        )
        names[key] = str(name)
    return names


def _exceptions(
    session: Session, membership_ids: Sequence[UUID], *, cutoff: datetime
) -> dict[tuple[UUID, str], list[Mapping[str, Any]]]:
    if not membership_ids:
        return {}
    statement = select(sod_exception).where(
        sod_exception.c.membership_id.in_(list(membership_ids)),
        sod_exception.c.created_at <= cutoff,
    )
    found: dict[tuple[UUID, str], list[Mapping[str, Any]]] = {}
    for row in session.execute(statement).mappings():
        key = (UUID(str(row["membership_id"])), str(row["sod_rule_code"]))
        found.setdefault(key, []).append(dict(row))
    return found


def conflicts(uow: UnitOfWork, params: ReportParams, *, at: datetime) -> list[Conflict]:
    """The conflicts at ``at`` with member, rule name, held roles, delegations and cover (module
    docstring)."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    held = _held(session, params, at=at, cutoff=cutoff)
    delegated = _delegated(session, at=at, held=held)
    reported = [
        (membership_id, conflict)
        for membership_id, conflict in kernel.conflict_report(session, as_of=at)
        if in_conflict(
            held.get(membership_id, ()),
            conflict.function_a_permissions,
            conflict.function_b_permissions,
            delegated.get(membership_id, ()),
        )
    ]
    membership_ids = sorted({membership_id for membership_id, _ in reported}, key=str)
    members: dict[UUID, Mapping[str, Any]] = {}
    if membership_ids:
        members = {
            UUID(str(row["id"])): dict(row)
            for row in session.execute(
                users.member_select().where(tenant_membership.c.id.in_(membership_ids))
            ).mappings()
        }
    names = _rule_names(session, reported)
    exceptions = _exceptions(session, membership_ids, cutoff=cutoff)
    found: list[Conflict] = []
    for membership_id, conflict in reported:
        member = members[membership_id]
        cover = covering(exceptions.get((membership_id, conflict.rule_code), ()), at)
        found.append(
            Conflict(
                email=str(member["email"]),
                display_name=str(member["display_name"]),
                rule_code=conflict.rule_code,
                rule_name=names[
                    (
                        conflict.rule_code,
                        conflict.function_a_permissions,
                        conflict.function_b_permissions,
                    )
                ],
                function_a=conflict.function_a_permissions,
                function_b=conflict.function_b_permissions,
                held=tuple(held.get(membership_id, ())),
                cover=None
                if cover is None
                else Cover(
                    id=UUID(str(cover["id"])),
                    compensating_control=str(cover["compensating_control"]),
                    valid_from=cover["valid_from"],
                    valid_to=cover["valid_to"],
                ),
                delegated=tuple(delegated.get(membership_id, ())),
            )
        )
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    at = support.as_of_instant(params)
    rows, totals = dataset_rows(conflicts(uow, params, at=at))
    totals["as_of"] = utc_text(at)
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "Conflict",
    "Cover",
    "Delegated",
    "Held",
    "build",
    "conflicts",
    "covering",
    "dataset_rows",
    "delegation_text",
    "in_conflict",
]
