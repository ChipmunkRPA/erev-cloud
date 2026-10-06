"""Separation of duties (dev-guide §5.4 ``sod.py``, DG-KRN-PERM-02, DG-KRN-PERM-03; 04 T-PLT-13,
T-PLT-14; BUILD_SPEC BS1-D-26, PLF-6; PRD §5.6 "Checks", J-22.6, J-22.9, ERR-22; CTL-034)."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.approvals.preview import preview_sha256, store_preview
from erev_api.approvals.subjects import SUBJECTS
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.auth.sod import (
    SodConflict,
    assert_assignment_allowed,
    assert_delegation_allowed,
    assert_role_change_allowed,
    conflict_report,
    conflicts_for,
)
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import audit_event, role, role_assignment, sod_exception, sod_rule
from erev_api.domain.platform.provisioning import TenantProvisionResult
from erev_api.enums import ApprovalSubjectType, ConfigStatus, GrantStatus, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    assignment_row,
    insert_active_membership,
    insert_app_user,
    insert_approval_delegation,
    insert_custom_role,
    insert_role_assignment,
    insert_sod_exception,
    insert_sod_rule,
    publish_sod_rule_version,
    revoke_role_assignments,
    submit_sod_rule_version,
)

SOD_3_A = frozenset(
    {
        "contract.create",
        "modification.create",
        "event.record",
        "estimate.create",
        "judgement.create",
        "adjustment.create",
        "import.upload",
    }
)
SOD_3_B = frozenset(
    {
        "contract.approve",
        "modification.approve",
        "event.approve",
        "estimate.approve",
        "judgement.review",
        "adjustment.approve",
        "import.approve",
    }
)


@pytest.fixture
def tenant(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> TenantProvisionResult:
    """A tenant whose admin membership holds no role: the bootstrap grant is revoked."""
    result = tenant_factory(keyring=keyring, clock=clock)
    with tenant_session(_ctx(result)) as session:
        revoke_role_assignments(
            session,
            tenant_id=tenant_id_of(result),
            membership_id=result.admin_membership_id,
            at=clock.now(),
        )
    return result


def _ctx(result: TenantProvisionResult) -> DbContext:
    return DbContext(tenant_id=tenant_id_of(result), user_id=None, entity_scope="*")


def _role_id(session: Session, code: str) -> UUID:
    return UUID(str(session.execute(select(role.c.id).where(role.c.code == code)).scalar_one()))


def _assign(result: TenantProvisionResult, *codes: str) -> None:
    with tenant_session(_ctx(result)) as session:
        for code in codes:
            insert_role_assignment(
                session,
                tenant_id=tenant_id_of(result),
                membership_id=result.admin_membership_id,
                role_code=code,
            )


@contextmanager
def _uow(
    result: TenantProvisionResult, *, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=system_principal(tenant_id_of(result), on_behalf_of_id=None),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-sod-as-of",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(app_settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        yield uow


def _walk(session: Session, version_id: UUID, *statuses: ConfigStatus) -> None:
    """Move a DRAFT version along E-12 to each status in turn (DB-04)."""
    for status in statuses:
        values: dict[str, str] = {"status": status.value}
        if status is ConfigStatus.TESTED:
            values["content_sha256"] = "d" * 64
        session.execute(update(sod_rule).where(sod_rule.c.id == version_id).values(**values))


def _counts(session: Session) -> tuple[int, ...]:
    return tuple(
        int(session.execute(select(func.count()).select_from(table)).scalar_one())
        for table in (role_assignment, sod_exception, audit_event)
    )


def _blocked(result: TenantProvisionResult, adding: str, at: datetime) -> Problem:
    with tenant_session(_ctx(result)) as session:
        before = _counts(session)
        with pytest.raises(Problem) as excinfo:
            assert_assignment_allowed(
                session, result.admin_membership_id, _role_id(session, adding), at=at
            )
        assert _counts(session) == before
    return excinfo.value


@pytest.mark.control("CTL-034")
def test_ctl_034_conflicting_assignment_blocked(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    _assign(tenant, "revenue_accountant")
    problem = _blocked(tenant, "revenue_reviewer", clock.now())
    assert (problem.slug, problem.status) == ("sod-conflict", 409)
    assert [(error.rule_id, error.message) for error in problem.errors] == [
        (
            "SoD-3",
            "Separation of duties conflict SoD-3: Revenue Accountant with Revenue Reviewer lets "
            "one person create and approve the same contract or modification.",
        )
    ]


def test_sod_1_tenant_admin_with_controller(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    _assign(tenant, "tenant_admin")
    problem = _blocked(tenant, "controller", clock.now())
    assert [(error.rule_id, error.message) for error in problem.errors] == [
        (
            "SoD-1",
            "Separation of duties conflict SoD-1: user administration with transaction or "
            "approval permissions.",
        )
    ]


def test_default_roles_and_personas_have_no_conflict(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    personas = (
        ("revenue_accountant", "ssp_analyst"),
        ("revenue_reviewer", "ssp_approver"),
        ("controller", "ssp_approver"),
    )
    membership_id, at = tenant.admin_membership_id, clock.now()
    with tenant_session(_ctx(tenant), read_only=True) as session:
        for code in DEFAULT_ROLES:
            adding = [_role_id(session, code)]
            assert conflicts_for(session, membership_id, adding_role_ids=adding, at=at) == [], code
        for pair in personas:
            adding = [_role_id(session, code) for code in pair]
            assert conflicts_for(session, membership_id, adding_role_ids=adding, at=at) == [], pair
        # The combination of J-22.6 does conflict, so the check above can fail.
        adding = [_role_id(session, code) for code in ("revenue_accountant", "revenue_reviewer")]
        assert [
            conflict.rule_code
            for conflict in conflicts_for(session, membership_id, adding_role_ids=adding, at=at)
        ] == ["SoD-3"]


def test_approved_exception_covers_conflict(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    tenant_id, membership_id, at = tenant_id_of(tenant), tenant.admin_membership_id, clock.now()
    _assign(tenant, "revenue_accountant")
    with tenant_session(_ctx(tenant)) as session:
        insert_sod_exception(
            session,
            tenant_id=tenant_id,
            membership_id=membership_id,
            status=GrantStatus.APPROVED,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_to=datetime(2026, 6, 30, tzinfo=UTC),
        )
    # With valid_to in the past the conflict is uncovered.
    assert [error.rule_id for error in _blocked(tenant, "revenue_reviewer", at).errors] == ["SoD-3"]

    with tenant_session(_ctx(tenant)) as session:
        covering = insert_sod_exception(
            session,
            tenant_id=tenant_id,
            membership_id=membership_id,
            status=GrantStatus.APPROVED,
            valid_from=datetime(2026, 9, 1, tzinfo=UTC),
            valid_to=datetime(2026, 11, 30, tzinfo=UTC),
        )
        # A REQUESTED exception covers nothing.
        insert_sod_exception(session, tenant_id=tenant_id, membership_id=membership_id)
    with tenant_session(_ctx(tenant), read_only=True) as session:
        reviewer = _role_id(session, "revenue_reviewer")
        assert assert_assignment_allowed(session, membership_id, reviewer, at=at) == covering
        assert conflicts_for(session, membership_id, adding_role_ids=[reviewer], at=at) == [
            SodConflict(
                rule_code="SoD-3",
                function_a_permissions=SOD_3_A,
                function_b_permissions=SOD_3_B,
                sod_exception_id=covering,
            )
        ]
        # After the exception lapses the conflict is uncovered again.
        with pytest.raises(Problem):
            assert_assignment_allowed(
                session, membership_id, reviewer, at=datetime(2026, 12, 1, tzinfo=UTC)
            )


def test_krn_perm_03_rules_from_published_rows_only(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    # Provisioning published SoD-3 v1 at t0; v2 (ssp.create × ssp.approve) supersedes it at t1.
    tenant_id, membership_id, t0 = tenant_id_of(tenant), tenant.admin_membership_id, clock.now()
    t1 = t0 + timedelta(days=10)
    _assign(tenant, "revenue_accountant")
    with tenant_session(_ctx(tenant)) as session:
        publish_sod_rule_version(
            session,
            tenant_id=tenant_id,
            code="SoD-3",
            function_a=["ssp.create"],
            function_b=["ssp.approve"],
            at=t1,
        )
        # DRAFT, TESTED and SUBMITTED rules over the same combination are never in force.
        for code, statuses in (
            ("draft-probe", ()),
            ("tested-probe", (ConfigStatus.TESTED,)),
            ("submitted-probe", (ConfigStatus.TESTED, ConfigStatus.SUBMITTED)),
        ):
            probe = insert_sod_rule(
                session,
                tenant_id=tenant_id,
                code=code,
                function_a=sorted(SOD_3_A),
                function_b=sorted(SOD_3_B),
            )
            _walk(session, probe, *statuses)
    with tenant_session(_ctx(tenant), read_only=True) as session:
        reviewer = _role_id(session, "revenue_reviewer")

        def codes(at: datetime) -> list[str]:
            return [
                conflict.rule_code
                for conflict in conflicts_for(
                    session, membership_id, adding_role_ids=[reviewer], at=at
                )
            ]

        # The SUPERSEDED v1 counts for instants in [published_at, effective_to) (D-80).
        assert codes(t0 - timedelta(seconds=1)) == []
        assert codes(t0) == ["SoD-3"]
        assert codes(t1 - timedelta(seconds=1)) == ["SoD-3"]
        # From t1 the PUBLISHED v2 applies, which the combination does not meet.
        assert codes(t1) == []
        assert codes(t1 + timedelta(days=365)) == []
        assert assert_assignment_allowed(session, membership_id, reviewer, at=t1) is None
        with pytest.raises(Problem):
            assert_assignment_allowed(session, membership_id, reviewer, at=t0)


def _member(tenant: TenantProvisionResult, *codes: str) -> UUID:
    """Another ACTIVE membership of the tenant, holding the roles ``codes``."""
    tenant_id = tenant_id_of(tenant)
    with identity_session(request_id="tests-sod-member") as session:
        user_id = insert_app_user(session, email=f"sod-{secrets.token_hex(4)}@members.test")
    with tenant_session(_ctx(tenant)) as session:
        membership_id = insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)
        for code in codes:
            insert_role_assignment(
                session, tenant_id=tenant_id, membership_id=membership_id, role_code=code
            )
    return membership_id


def _sod_3(*delegation_ids: UUID, covered_by: UUID | None = None) -> SodConflict:
    return SodConflict(
        rule_code="SoD-3",
        function_a_permissions=SOD_3_A,
        function_b_permissions=SOD_3_B,
        sod_exception_id=covered_by,
        delegation_ids=tuple(sorted(delegation_ids)),
    )


@pytest.mark.control("CTL-034")
def test_r_111_4_a_permission_held_through_a_delegation_is_held(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 6 (supervisor ruling R-111
    (4)); 04 T-PLT-21 rev 1.189. The engine read role grants only, so a duty held through an
    approval delegation was invisible to it: SoD-3 was assembled by delegating the approval
    first and granting the preparing role second, a change of a role the delegate held was
    checked without it, and the conflict report did not list the member. A permission of a
    delegation that stands is held, and the conflict names the delegation."""
    # The rules count from the tenant's creation (D-80 rule 1): the instants read below lie
    # after it.
    clock.advance(timedelta(days=40))
    tenant_id, delegate, at = tenant_id_of(tenant), tenant.admin_membership_id, clock.now()
    reviewer = _member(tenant, "revenue_reviewer")  # holds contract.approve: the delegator
    with tenant_session(_ctx(tenant)) as session:
        standing = insert_approval_delegation(
            session,
            tenant_id=tenant_id,
            delegator_membership_id=reviewer,
            delegate_membership_id=delegate,
            valid_from=at - timedelta(days=1),
            valid_to=at + timedelta(days=30),
        )

    # The delegation alone meets one function: nothing conflicts yet.
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflicts_for(session, delegate, at=at) == []
        assert conflict_report(session, as_of=at) == []
        accountant = _role_id(session, "revenue_accountant")
        # The preparing role on top of it does.
        assert conflicts_for(session, delegate, adding_role_ids=[accountant], at=at) == [
            _sod_3(standing)
        ]
    problem = _blocked(tenant, "revenue_accountant", at)
    assert (problem.slug, problem.status) == ("sod-conflict", 409)
    assert [(error.field, error.rule_id) for error in problem.errors] == [("role_id", "SoD-3")]

    # The role held already (a legacy row): the report lists the member and names the
    # delegation; as of an instant before the delegation started nothing conflicted (D-80) —
    # the role was held and SoD-3 in force then, the delegation was not standing.
    _assign(tenant, "revenue_accountant")
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflict_report(session, as_of=at) == [(delegate, _sod_3(standing))]
        assert conflict_report(session, as_of=at - timedelta(days=2)) == []
        reviewer_role = _role_id(session, "revenue_reviewer")
        assert [
            conflict.rule_code
            for conflict in conflicts_for(
                session, delegate, adding_role_ids=[reviewer_role], at=at - timedelta(days=2)
            )
        ] == ["SoD-3"]

    # An approved exception covers a conflict held through a delegation as it covers one held
    # through roles.
    with tenant_session(_ctx(tenant)) as session:
        covering = insert_sod_exception(
            session,
            tenant_id=tenant_id,
            membership_id=delegate,
            status=GrantStatus.APPROVED,
            valid_from=at - timedelta(days=1),
            valid_to=at + timedelta(days=60),
        )
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflict_report(session, as_of=at) == [
            (delegate, _sod_3(standing, covered_by=covering))
        ]


@pytest.mark.control("CTL-034")
def test_r_111_4_a_delegation_is_checked_as_a_role_assignment_is(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    """Ruling R-111 (4); PRD BR-PLT-07. ``assert_delegation_allowed`` runs the check of a role
    assignment on the delegate's grants and standing delegations with the delegated permissions:
    one error per uncovered rule, on the first permission of the request the rule counts; an
    approved exception covers it; a permission no rule sets against what the delegate holds
    passes (positive control)."""
    tenant_id, at = tenant_id_of(tenant), clock.now()
    preparer = _member(tenant, "revenue_accountant")
    with tenant_session(_ctx(tenant), read_only=True) as session:
        with pytest.raises(Problem) as refused:
            assert_delegation_allowed(
                session, preparer, ["period.reopen_approve", "contract.approve"], at=at
            )
        assert (
            assert_delegation_allowed(session, preparer, ["period.reopen_approve"], at=at) is None
        )
        assert conflicts_for(session, preparer, adding_permissions=["contract.approve"], at=at) == [
            _sod_3()
        ]
    assert (refused.value.slug, refused.value.status) == ("sod-conflict", 409)
    assert [(error.field, error.rule_id, error.message) for error in refused.value.errors] == [
        (
            "permissions[1]",
            "SoD-3",
            "Separation of duties conflict SoD-3: Revenue Accountant with Revenue Reviewer lets "
            "one person create and approve the same contract or modification.",
        )
    ]
    with tenant_session(_ctx(tenant)) as session:
        covering = insert_sod_exception(
            session,
            tenant_id=tenant_id,
            membership_id=preparer,
            status=GrantStatus.APPROVED,
            valid_from=at - timedelta(days=1),
            valid_to=at + timedelta(days=60),
        )
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert assert_delegation_allowed(session, preparer, ["contract.approve"], at=at) == covering


def test_r_111_4_only_a_delegation_that_stands_counts(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    """04 T-PLT-21 rev 1.189: a delegation stands when ``valid_from <= at < valid_to`` and it
    was not revoked by ``at``. One that ended and one that was revoked hold nothing now; the
    revoked one still counts as of an instant before its revocation (D-80 rule 2). A member
    without any role meets SoD-1 through two delegations alone, and a change of a role counts
    what its holder was delegated. (One that has not started: the next test.)"""
    # The rules count from the tenant's creation (D-80 rule 1): every instant read below lies
    # after it.
    clock.advance(timedelta(days=40))
    tenant_id, at = tenant_id_of(tenant), clock.now()
    reviewer = _member(tenant, "revenue_reviewer")
    day = timedelta(days=1)

    def delegated(
        delegate: UUID,
        start: datetime,
        end: datetime,
        *,
        permissions: tuple[str, ...] = ("contract.approve",),
        revoked_at: datetime | None = None,
    ) -> UUID:
        with tenant_session(_ctx(tenant)) as session:
            return insert_approval_delegation(
                session,
                tenant_id=tenant_id,
                delegator_membership_id=reviewer,
                delegate_membership_id=delegate,
                valid_from=start,
                valid_to=end,
                permissions=permissions,
                revoked_at=revoked_at,
            )

    preparer = _member(tenant, "revenue_accountant")
    ended = delegated(preparer, at - 20 * day, at - day)
    revoked = delegated(preparer, at - 5 * day, at + 20 * day, revoked_at=at - timedelta(hours=1))
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflicts_for(session, preparer, at=at) == []
        assert conflict_report(session, as_of=at) == []
        assert conflict_report(session, as_of=at - timedelta(hours=2)) == [
            (preparer, _sod_3(revoked))
        ]
        # The end is exclusive and the start inclusive, as for a role assignment.
        assert conflict_report(session, as_of=at - day) == [(preparer, _sod_3(revoked))]
        assert conflict_report(session, as_of=at - 20 * day) == [(preparer, _sod_3(ended))]

    # No role at all: access administration (SoD-1 function A) and a transaction approval
    # (function B), each through a delegation.
    bare = _member(tenant)
    first = delegated(bare, at - day, at + day, permissions=("access.approve",))
    second = delegated(bare, at - day, at + day)
    with tenant_session(_ctx(tenant), read_only=True) as session:
        [(membership_id, conflict)] = conflict_report(session, as_of=at)
        assert (membership_id, conflict.rule_code) == (bare, "SoD-1")
        assert conflict.delegation_ids == tuple(sorted((first, second)))

    # A change of a role: its holder was delegated contract.approve, and the role is to gain a
    # preparing permission.
    holder = _member(tenant)
    held = delegated(holder, at - day, at + day)
    with tenant_session(_ctx(tenant)) as session:
        desk = insert_custom_role(
            session, tenant_id=tenant_id, code="deal_desk", permissions=["contract.read"]
        )
        session.execute(
            role_assignment.insert().values(
                **assignment_row(tenant_id, membership_id=holder, role_id=desk)
            )
        )
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert_role_change_allowed(session, desk, ["contract.read", "config.read"], at=at)
        with pytest.raises(Problem) as refused:
            assert_role_change_allowed(session, desk, ["contract.read", "contract.create"], at=at)
        assert [error.rule_id for error in refused.value.errors] == ["SoD-3"]
        assert conflicts_for(session, holder, at=at) == []
        assert held  # the delegation stands: it is what the refusal counted


@pytest.mark.control("CTL-034")
def test_r_111_4_a_command_counts_a_delegation_from_the_moment_it_is_given(
    tenant: TenantProvisionResult, clock: FrozenClock
) -> None:
    """04 T-PLT-21 rev 1.189, the lane's own finding in its SoD part. A delegation given for a
    later start comes into force without a further command. Counted only once it had started, it
    let a command grant the other side of a rule in between, and the member held both from its
    first day. A command counts it from the moment it is given — ``conflicts_for``, a role
    assignment, a further delegation, a change of a role — while the report as of an instant
    lists what stood then: from its start, and never before it was given, whatever its
    ``valid_from`` says."""
    # The rules count from the tenant's creation (D-80 rule 1): every instant read below lies
    # after it.
    clock.advance(timedelta(days=40))
    tenant_id, at = tenant_id_of(tenant), clock.now()
    reviewer = _member(tenant, "revenue_reviewer")
    day = timedelta(days=1)

    def delegated(
        delegate: UUID,
        start: datetime,
        end: datetime,
        *,
        given: datetime,
        permissions: tuple[str, ...] = ("contract.approve",),
    ) -> UUID:
        with tenant_session(_ctx(tenant)) as session:
            return insert_approval_delegation(
                session,
                tenant_id=tenant_id,
                delegator_membership_id=reviewer,
                delegate_membership_id=delegate,
                valid_from=start,
                valid_to=end,
                permissions=permissions,
                created_at=given,
            )

    # Given yesterday for a start in five days, to a member who prepares (a legacy row: the
    # command refuses it). A command reads the conflict today; the report from the first day.
    preparer = _member(tenant, "revenue_accountant")
    scheduled = delegated(preparer, at + 5 * day, at + 20 * day, given=at - day)
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflicts_for(session, preparer, at=at) == [_sod_3(scheduled)]
        assert conflict_report(session, as_of=at) == []
        assert conflict_report(session, as_of=at + 5 * day - timedelta(seconds=1)) == []
        assert conflict_report(session, as_of=at + 5 * day) == [(preparer, _sod_3(scheduled))]

    # The order the product admits: a member who holds nothing is given the approval for next
    # week, and the other side is asked for before it starts — by a role, by a further
    # delegation, by a change of a role the member holds.
    bare = _member(tenant)
    coming = delegated(bare, at + 5 * day, at + 20 * day, given=at - day)
    with tenant_session(_ctx(tenant)) as session:
        desk = insert_custom_role(
            session, tenant_id=tenant_id, code="order_desk", permissions=["contract.read"]
        )
        session.execute(
            role_assignment.insert().values(
                **assignment_row(tenant_id, membership_id=bare, role_id=desk)
            )
        )
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflicts_for(session, bare, at=at) == []  # one side alone
        accountant = _role_id(session, "revenue_accountant")
        with pytest.raises(Problem) as by_role:
            assert_assignment_allowed(session, bare, accountant, at=at)
        with pytest.raises(Problem) as by_delegation:
            assert_delegation_allowed(session, bare, ["access.approve"], at=at)
        with pytest.raises(Problem) as by_change:
            assert_role_change_allowed(session, desk, ["contract.read", "contract.create"], at=at)
        # Positive controls: what no rule sets against the approval passes each of the three.
        viewer = _role_id(session, "viewer")
        assert assert_assignment_allowed(session, bare, viewer, at=at) is None
        assert assert_delegation_allowed(session, bare, ["event.approve"], at=at) is None
        assert_role_change_allowed(session, desk, ["contract.read", "config.read"], at=at)
    assert [(error.field, error.rule_id) for error in by_role.value.errors] == [
        ("role_id", "SoD-3")
    ]
    assert [(error.field, error.rule_id) for error in by_delegation.value.errors] == [
        ("permissions[0]", "SoD-1")
    ]
    assert [error.rule_id for error in by_change.value.errors] == ["SoD-3"]
    assert coming

    # A start dated back: given now for ten days ago. It stands now, and it adds nothing to an
    # instant before it was given — the report of that instant reads as it did then.
    late = _member(tenant, "revenue_accountant")
    backdated = delegated(late, at - 10 * day, at + 20 * day, given=at)
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflict_report(session, as_of=at) == [(late, _sod_3(backdated))]
        assert conflict_report(session, as_of=at - timedelta(seconds=1)) == []
        assert conflict_report(session, as_of=at - 5 * day) == []


def test_conflict_report_as_of(tenant: TenantProvisionResult, clock: FrozenClock) -> None:
    tenant_id, membership_id, at = tenant_id_of(tenant), tenant.admin_membership_id, clock.now()
    with tenant_session(_ctx(tenant)) as session:
        exception_id = insert_sod_exception(
            session,
            tenant_id=tenant_id,
            membership_id=membership_id,
            status=GrantStatus.APPROVED,
            valid_from=datetime(2026, 9, 1, tzinfo=UTC),
            valid_to=datetime(2026, 11, 30, tzinfo=UTC),
        )
    _assign(tenant, "revenue_accountant", "revenue_reviewer")
    with tenant_session(_ctx(tenant), read_only=True) as session:
        report = conflict_report(session, as_of=at)
        before_assignments = conflict_report(session, as_of=datetime(2025, 12, 31, tzinfo=UTC))
    assert report == [
        (
            membership_id,
            SodConflict(
                rule_code="SoD-3",
                function_a_permissions=SOD_3_A,
                function_b_permissions=SOD_3_B,
                sod_exception_id=exception_id,
            ),
        )
    ]
    assert before_assignments == []


def test_conflict_report_as_of_uses_rule_in_force_then(
    tenant: TenantProvisionResult, clock: FrozenClock, app_settings: Settings, keyring: KeyRing
) -> None:
    tenant_id, membership_id, t0 = tenant_id_of(tenant), tenant.admin_membership_id, clock.now()
    t1, t2 = t0 + timedelta(days=10), t0 + timedelta(days=5)
    # A legacy conflict: both roles written directly, in force before provisioning published v1.
    _assign(tenant, "revenue_accountant", "revenue_reviewer")
    v1_conflict = (
        membership_id,
        SodConflict(
            rule_code="SoD-3",
            function_a_permissions=SOD_3_A,
            function_b_permissions=SOD_3_B,
            sod_exception_id=None,
        ),
    )
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflict_report(session, as_of=t0 + timedelta(days=1)) == [v1_conflict]

    # At t1 a ROLE_CHANGE approval publishes v2 (ssp.create × ssp.approve) and supersedes v1.
    clock.set(t1)
    proposal = {
        "object_type": "sod_rule",
        "code": "SoD-3",
        "function_a_permissions": ["ssp.create"],
        "function_b_permissions": ["ssp.approve"],
    }
    with _uow(tenant, app_settings=app_settings, keyring=keyring, clock=clock) as uow:
        stored = store_preview(uow, before={}, after=proposal)
        version_id, request_id = submit_sod_rule_version(
            uow.session,
            tenant_id=tenant_id,
            code="SoD-3",
            function_a=["ssp.create"],
            function_b=["ssp.approve"],
            request={
                "impact_preview_file_id": stored["id"],
                "impact_preview_sha256": preview_sha256({}, proposal),
            },
        )
        SUBJECTS[ApprovalSubjectType.ROLE_CHANGE].on_approved(uow, version_id, request_id)
        uow.commit()
    with tenant_session(_ctx(tenant), read_only=True) as session:
        versions = session.execute(
            select(
                sod_rule.c.version_no,
                sod_rule.c.status,
                sod_rule.c.published_at,
                sod_rule.c.effective_to,
            )
            .where(sod_rule.c.code == "SoD-3")
            .order_by(sod_rule.c.version_no)
        ).all()
        earlier = conflict_report(session, as_of=t0 + timedelta(days=1))
        later = conflict_report(session, as_of=t1 + timedelta(seconds=1))
    assert [tuple(row) for row in versions] == [
        (1, "SUPERSEDED", t0, t1),
        (2, "PUBLISHED", t1, None),
    ]
    assert earlier == [v1_conflict]
    assert later == []

    # An assignment revoked at t2 counts for as_of before t2 and not from t2.
    with tenant_session(_ctx(tenant)) as session:
        session.execute(
            update(role_assignment)
            .where(
                role_assignment.c.membership_id == membership_id,
                role_assignment.c.role_id == _role_id(session, "revenue_reviewer"),
            )
            .values(revoked_at=t2, revoked_by_kind="SYSTEM")
        )
    with tenant_session(_ctx(tenant), read_only=True) as session:
        assert conflict_report(session, as_of=t0 + timedelta(days=1)) == [v1_conflict]
        assert conflict_report(session, as_of=t2 - timedelta(seconds=1)) == [v1_conflict]
        assert conflict_report(session, as_of=t2) == []
