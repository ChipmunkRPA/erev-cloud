"""Separation of duties KRN-PERM (dev-guide §5.4 ``sod.py``; DG-KRN-PERM-02, DG-KRN-PERM-03; 04
T-PLT-13, T-PLT-14; REQ-PLT-010; CTL-034).

Rule content comes only from published ``sod_rule`` versions (DG-KRN-PERM-03). For an instant
``at``, a code's rule is its PUBLISHED version published at or before ``at``, or its SUPERSEDED
version with ``published_at <= at < effective_to``; a version without ``published_at`` counts from
the tenant's ``created_at`` (D-80, SoD rules as of a date). A membership conflicts with a rule when
its permissions meet both function A and function B. Its permissions are those of the role
assignments in force at ``at``, those of the approval delegations to it
(``permissions.standing_delegations``; 04 T-PLT-21) and what a command is adding — roles, or the
permissions of a delegation (supervisor ruling R-111 (4)): a delegate decides with the delegated
permission, so a duty held through a delegation is held. An APPROVED, unrevoked ``sod_exception``
of that membership and rule whose validity holds ``at`` covers the conflict, however it is held.

Which delegations count depends on who asks. A command (``conflicts_for`` and the three
``assert_*`` functions; ``at = now``) counts every delegation to the member that has not ended,
started or not: one given for a later start comes into force without a further command, so a
command that waited for the start would grant the other side of a rule in between. The report
(``conflict_report``) answers for an instant: it counts the delegations that stood then and had
been given by then, so a ``valid_from`` earlier than the command that created the delegation
changes no report of an earlier instant.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from erev_api.auth.permissions import (
    StandingDelegation,
    effective_grants,
    standing_delegations,
)
from erev_api.db.tables import (
    role,
    role_assignment,
    role_permission,
    sod_exception,
    sod_rule,
    tenant,
)
from erev_api.enums import ConfigStatus, GrantStatus
from erev_api.problems import Problem, ProblemError


@dataclass(frozen=True, slots=True)
class SodConflict:
    rule_code: str
    function_a_permissions: frozenset[str]
    function_b_permissions: frozenset[str]
    sod_exception_id: UUID | None  # APPROVED, unexpired exception covering it
    # The standing delegations to the member that name a permission of either function: the
    # conflict is held through them, wholly or beside a role. Empty when no delegation takes part.
    delegation_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class _Rule:
    code: str
    name: str
    function_a: frozenset[str]
    function_b: frozenset[str]


def conflict_message(rule_code: str, name: str) -> str:
    """PRD ERR-22: ``Separation of duties conflict <code>: <name>.``"""
    return f"Separation of duties conflict {rule_code}: {name}."


def _published_rules(session: Session, at: datetime) -> list[_Rule]:
    """The rule versions in force at ``at``, by code (D-80 rule 1)."""
    published_from = func.coalesce(
        sod_rule.c.published_at,
        select(tenant.c.created_at).where(tenant.c.id == sod_rule.c.tenant_id).scalar_subquery(),
    )
    statement = (
        select(
            sod_rule.c.code,
            sod_rule.c.name,
            sod_rule.c.function_a_permissions,
            sod_rule.c.function_b_permissions,
        )
        .where(
            or_(
                sod_rule.c.status == ConfigStatus.PUBLISHED.value,
                and_(
                    sod_rule.c.status == ConfigStatus.SUPERSEDED.value,
                    sod_rule.c.effective_to.is_not(None),
                ),
            ),
            published_from <= at,
            or_(sod_rule.c.effective_from.is_(None), sod_rule.c.effective_from <= at),
            or_(sod_rule.c.effective_to.is_(None), sod_rule.c.effective_to > at),
        )
        .order_by(sod_rule.c.code)
    )
    return [
        _Rule(
            code=str(code),
            name=str(name),
            function_a=frozenset(str(value) for value in function_a),
            function_b=frozenset(str(value) for value in function_b),
        )
        for code, name, function_a, function_b in session.execute(statement)
    ]


def _role_permissions(session: Session, role_ids: Sequence[UUID]) -> frozenset[str]:
    if not role_ids:
        return frozenset()
    statement = select(role_permission.c.permission_code).where(
        role_permission.c.role_id.in_(role_ids)
    )
    return frozenset(str(code) for code in session.scalars(statement))


def _covering_exception(
    session: Session, membership_id: UUID, rule_code: str, at: datetime
) -> UUID | None:
    statement = (
        select(sod_exception.c.id)
        .where(
            sod_exception.c.membership_id == membership_id,
            sod_exception.c.sod_rule_code == rule_code,
            sod_exception.c.status == GrantStatus.APPROVED.value,
            sod_exception.c.revoked_at.is_(None),
            sod_exception.c.valid_from <= at,
            sod_exception.c.valid_to > at,
        )
        .order_by(sod_exception.c.valid_to.desc(), sod_exception.c.id)
        .limit(1)
    )
    value = session.execute(statement).scalar_one_or_none()
    return None if value is None else UUID(str(value))


def _delegated(delegations: Iterable[StandingDelegation]) -> dict[str, tuple[UUID, ...]]:
    """Permission code → the ids of the delegations that name it, in the order given. Pure."""
    found: dict[str, list[UUID]] = {}
    for delegation in delegations:
        for code in sorted(delegation.permissions):
            found.setdefault(code, []).append(delegation.id)
    return {code: tuple(ids) for code, ids in found.items()}


def _through(delegated: Mapping[str, tuple[UUID, ...]], rule: _Rule) -> tuple[UUID, ...]:
    """The delegations a conflict with ``rule`` is held through: those that name a permission
    of either function, by id. Pure."""
    return tuple(
        sorted(
            {
                delegation_id
                for code in rule.function_a | rule.function_b
                for delegation_id in delegated.get(code, ())
            }
        )
    )


def _conflicts(
    session: Session,
    membership_id: UUID,
    adding_role_ids: Sequence[UUID],
    at: datetime,
    *,
    adding_permissions: Iterable[str] = (),
) -> list[tuple[_Rule, SodConflict]]:
    delegated = _delegated(
        standing_delegations(session, at=at, delegate_membership_id=membership_id, scheduled=True)
    )
    held = effective_grants(session, membership_id, at=at).permissions
    held |= _role_permissions(session, adding_role_ids)
    held |= frozenset(delegated) | frozenset(adding_permissions)
    found: list[tuple[_Rule, SodConflict]] = []
    for rule in _published_rules(session, at):
        if not (held & rule.function_a and held & rule.function_b):
            continue
        conflict = SodConflict(
            rule_code=rule.code,
            function_a_permissions=rule.function_a,
            function_b_permissions=rule.function_b,
            sod_exception_id=_covering_exception(session, membership_id, rule.code, at),
            delegation_ids=_through(delegated, rule),
        )
        found.append((rule, conflict))
    return found


def conflicts_for(
    session: Session,
    membership_id: UUID,
    *,
    adding_role_ids: Sequence[UUID] = (),
    adding_permissions: Iterable[str] = (),
    at: datetime,
) -> list[SodConflict]:
    """The rules the membership meets at ``at`` once ``adding_role_ids`` and
    ``adding_permissions`` — the permissions of a delegation to it — are added, by rule code. A
    command's reading: a delegation given to the membership and not ended counts, started or
    not."""
    return [
        conflict
        for _, conflict in _conflicts(
            session, membership_id, adding_role_ids, at, adding_permissions=adding_permissions
        )
    ]


def assert_assignment_allowed(
    session: Session, membership_id: UUID, role_id: UUID, *, at: datetime
) -> UUID | None:
    """The exception covering the combination, None without conflict; else 409 ``sod-conflict``
    with one error per uncovered rule (DG-KRN-PERM-02). Reads only; writes no row."""
    return assert_assignments_allowed(session, membership_id, (role_id,), at=at)


def assert_assignments_allowed(
    session: Session,
    membership_id: UUID,
    role_ids: Sequence[UUID],
    *,
    at: datetime,
    field: str = "role_id",
) -> UUID | None:
    """``assert_assignment_allowed`` for several roles added together, such as the roles of an
    invitation; the errors name ``field``."""
    found = _conflicts(session, membership_id, role_ids, at)
    uncovered = [rule for rule, conflict in found if conflict.sod_exception_id is None]
    if uncovered:
        raise Problem(
            "sod-conflict",
            errors=[
                ProblemError(
                    field=field,
                    rule_id=rule.code,
                    message=conflict_message(rule.code, rule.name),
                )
                for rule in uncovered
            ],
        )
    return next((conflict.sod_exception_id for _, conflict in found), None)


def assert_delegation_allowed(
    session: Session,
    membership_id: UUID,
    permissions: Sequence[str],
    *,
    at: datetime,
    field: str = "permissions",
) -> UUID | None:
    """``assert_assignments_allowed`` for a delegation to ``membership_id``: the delegate's grants
    and the delegations to them that have not ended, with ``permissions`` added (PRD BR-PLT-07;
    ruling R-111 (4)). The exception covering the combination, None without conflict; else 409
    ``sod-conflict`` with one error per uncovered rule, each naming ``<field>[i]`` — the first
    permission of the request the rule counts — or ``field`` when the conflict stands without
    them. Reads only."""
    found = _conflicts(session, membership_id, (), at, adding_permissions=permissions)
    uncovered = [rule for rule, conflict in found if conflict.sod_exception_id is None]
    if uncovered:

        def named(rule: _Rule) -> str:
            counted = rule.function_a | rule.function_b
            for index, code in enumerate(permissions):
                if code in counted:
                    return f"{field}[{index}]"
            return field

        raise Problem(
            "sod-conflict",
            errors=[
                ProblemError(
                    field=named(rule),
                    rule_id=rule.code,
                    message=conflict_message(rule.code, rule.name),
                )
                for rule in uncovered
            ],
        )
    return next((conflict.sod_exception_id for _, conflict in found), None)


def _in_force(at: datetime) -> ColumnElement[bool]:
    return and_(
        role_assignment.c.revoked_at.is_(None),
        role_assignment.c.valid_from <= at,
        or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > at),
    )


def assert_role_change_allowed(
    session: Session,
    role_id: UUID,
    permissions: Iterable[str],
    *,
    at: datetime,
    field: str = "permissions",
) -> None:
    """409 ``sod-conflict`` when giving the role ``permissions`` would let a member who holds it
    meet a rule that no exception covers, with one error per rule (REQ-PLT-009, REQ-PLT-010).

    Each holder's permissions are those of their other active roles in force at ``at``, those of
    the delegations to them that have not ended at ``at``, started or not, plus ``permissions``.
    Reads only; writes no row.
    """
    proposed = frozenset(permissions)
    holders = session.scalars(
        select(role_assignment.c.membership_id)
        .where(role_assignment.c.role_id == role_id, _in_force(at))
        .distinct()
        .order_by(role_assignment.c.membership_id)
    ).all()
    if not holders:
        return
    rules = _published_rules(session, at)
    uncovered: dict[str, _Rule] = {}
    for value in holders:
        membership_id = UUID(str(value))
        held = proposed | frozenset(
            str(code)
            for code in session.scalars(
                select(role_permission.c.permission_code)
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
                    role_assignment.c.membership_id == membership_id,
                    role_assignment.c.role_id != role_id,
                    role.c.is_active.is_(True),
                    _in_force(at),
                )
            )
        )
        held |= frozenset(
            _delegated(
                standing_delegations(
                    session, at=at, delegate_membership_id=membership_id, scheduled=True
                )
            )
        )
        for rule in rules:
            if rule.code in uncovered or not (held & rule.function_a and held & rule.function_b):
                continue
            if _covering_exception(session, membership_id, rule.code, at) is None:
                uncovered[rule.code] = rule
    if uncovered:
        raise Problem(
            "sod-conflict",
            errors=[
                ProblemError(
                    field=field, rule_id=rule.code, message=conflict_message(rule.code, rule.name)
                )
                for _, rule in sorted(uncovered.items())
            ],
        )


def conflict_report(session: Session, *, as_of: datetime) -> list[tuple[UUID, SodConflict]]:
    """Every membership with role assignments in force or delegations standing at ``as_of`` and
    its conflicts under the rules in force then, ordered by membership id, then rule code
    (REQ-PLT-010).

    An assignment counts when ``valid_from <= as_of``, it was not revoked by ``as_of`` and its
    ``valid_to`` is later (D-80 rule 2), so an assignment revoked afterwards still counts; a
    delegation by the same rule (``permissions.standing_delegations``), and only once it had been
    given (``created_at <= as_of``): a ``valid_from`` earlier than the command that created it
    adds nothing to an earlier instant. A conflict names the delegations it is held through
    (``SodConflict.delegation_ids``)."""
    statement = (
        select(role_assignment.c.membership_id, role_permission.c.permission_code)
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
            role_assignment.c.valid_from <= as_of,
            or_(role_assignment.c.revoked_at.is_(None), role_assignment.c.revoked_at > as_of),
            or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > as_of),
            role.c.is_active.is_(True),
        )
    )
    held: dict[UUID, set[str]] = {}
    for membership, permission_code in session.execute(statement):
        held.setdefault(UUID(str(membership)), set()).add(str(permission_code))
    given: dict[UUID, list[StandingDelegation]] = {}
    for delegation in standing_delegations(session, at=as_of):
        if delegation.created_at > as_of:
            continue
        given.setdefault(delegation.delegate_membership_id, []).append(delegation)
        held.setdefault(delegation.delegate_membership_id, set()).update(delegation.permissions)
    rules = _published_rules(session, as_of)
    report: list[tuple[UUID, SodConflict]] = []
    for membership_id in sorted(held):
        permissions = held[membership_id]
        delegated = _delegated(given.get(membership_id, ()))
        report += [
            (
                membership_id,
                SodConflict(
                    rule_code=rule.code,
                    function_a_permissions=rule.function_a,
                    function_b_permissions=rule.function_b,
                    sod_exception_id=_covering_exception(session, membership_id, rule.code, as_of),
                    delegation_ids=_through(delegated, rule),
                ),
            )
            for rule in rules
            if permissions & rule.function_a and permissions & rule.function_b
        ]
    return report
