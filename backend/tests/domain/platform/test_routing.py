"""Approval routing and auto-approval (dev-guide §5.6 DG-KRN-APR-01; 04 T-REF-24 to T-REF-26,
T-PLT-01, §14.3; PRD §2.5, BR-PLT-02; REQ-PLT-013, REQ-PLT-016; BUILD_SPEC PLF-12)."""

from __future__ import annotations

import secrets
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import routing
from erev_api.approvals.engine import (
    decide,
    entity_columns,
    insert_request,
    record_auto_approval,
    submit,
)
from erev_api.approvals.subjects import ALL_ENTITIES
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    role,
    role_assignment,
    rule,
    rule_set,
    rule_set_version,
    tenant,
    tenant_membership,
)
from erev_api.domain.platform import provisioning, roles, users
from erev_api.domain.platform.setup import setup_completed
from erev_api.enums import (
    ApprovalSubjectType,
    MembershipStatus,
    PrincipalKind,
    RuleSetKind,
    TenantKind,
)
from erev_api.files.store import LocalFileStore
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import and_, insert, select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    ASSIGNED_FROM,
    PROBE_CONTENT_SHA256,
    RowContext,
    assignment_row,
    insert_active_membership,
    insert_app_user,
    insert_role_assignment,
    membership_row,
    publish_rule_set,
    revoke_role_assignments,
)
from support.subjects import ProbeSubjects, install

MFA_VERIFIED_AT = datetime(2026, 9, 12, 11, 58, tzinfo=UTC)
ROLE_CHANGE = ApprovalSubjectType.ROLE_CHANGE
ROLE_ASSIGNMENT = ApprovalSubjectType.ROLE_ASSIGNMENT
TWO_STEPS = {
    "steps": [
        {"name": "Access approval", "permission": "access.approve", "min_approvers": 1},
        {"name": "Second access approval", "permission": "access.approve", "min_approvers": 1},
    ]
}


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    # THE bootstrap Tenant Admin: the member of the tenant_admin assignment the seed of the
    # workspace wrote — here ``tenant.provision`` — known by that grant's own request (04 §14.3
    # item 2 rev 1.254; supervisor ruling R-38 (iv)).
    admin: Principal
    accountant: Principal  # holds revenue_accountant
    # Another person who holds tenant_admin, as a session would state it. No assignment row
    # exists for this member until a test writes one, so it is no second approver by itself.
    other_admin: Principal


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _person(tenant_id: UUID, user_id: UUID, membership_id: UUID, role_code: str) -> Principal:
    # As a session states it: the permissions of the role, each for all entities. The membership
    # commands ask for their own permission over the entities of what they change (supervisor
    # ruling R-115 (c)), so a Tenant Admin's principal carries ``user.manage`` and ``role.manage``.
    scopes: dict[str, Any] = {**dict.fromkeys(sorted(DEFAULT_ROLES[role_code]), "*")}
    scopes["access.approve"] = "*"
    return Principal(
        kind=PrincipalKind.USER,
        id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
        display_name="Routing probe person",
        roles=(role_code,),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=MFA_VERIFIED_AT,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


@pytest.fixture
def world(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> World:
    provisioned = tenant_factory(keyring=keyring, clock=clock)
    tenant_id = tenant_id_of(provisioned)
    with identity_session(request_id="tests-routing-users") as session:
        users = [insert_app_user(session) for _ in range(2)]
    with tenant_session(_all_entities(tenant_id)) as session:
        memberships = [
            insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)
            for user_id in users
        ]
        bootstrap_user = session.execute(
            select(tenant_membership.c.user_id).where(
                tenant_membership.c.id == provisioned.admin_membership_id
            )
        ).scalar_one()
    return World(
        tenant_id=tenant_id,
        admin=_person(
            tenant_id, UUID(str(bootstrap_user)), provisioned.admin_membership_id, "tenant_admin"
        ),
        accountant=_person(tenant_id, users[1], memberships[1], "revenue_accountant"),
        other_admin=_person(tenant_id, users[0], memberships[0], "tenant_admin"),
    )


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> ProbeSubjects:
    subjects = ProbeSubjects()
    for subject_type in (ROLE_CHANGE, ROLE_ASSIGNMENT, ApprovalSubjectType.SOD_EXCEPTION):
        install(monkeypatch, subjects.spec(subject_type))
    return subjects


Run = Any


@pytest.fixture
def run(clock: FrozenClock, keyring: KeyRing, app_settings: Settings) -> Run:
    @contextmanager
    def open_uow(principal: Principal) -> Iterator[UnitOfWork]:
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-routing",
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

    open_uow_typed: Any = open_uow
    return open_uow_typed


def _submit(
    run: Any, principal: Principal, probe: ProbeSubjects, subject_type: ApprovalSubjectType
) -> Mapping[str, Any]:
    opener: AbstractContextManager[UnitOfWork] = run(principal)
    with opener as uow:
        request = submit(
            uow,
            subject_type=subject_type,
            subject_id=probe.new_subject(role="access_approver"),
            summary="Routing probe",
        )
        uow.commit()
    return request


def _steps(tenant_id: UUID, request_id: UUID) -> list[tuple[Any, ...]]:
    with tenant_session(_all_entities(tenant_id)) as session:
        rows = session.execute(
            select(
                approval_step.c.step_no,
                approval_step.c.name,
                approval_step.c.required_permission,
                approval_step.c.min_approvers,
                approval_step.c.status,
            )
            .where(approval_step.c.approval_request_id == request_id)
            .order_by(approval_step.c.step_no)
        ).all()
    return [tuple(row) for row in rows]


def _decisions(tenant_id: UUID, request_id: UUID) -> list[tuple[Any, ...]]:
    with tenant_session(_all_entities(tenant_id)) as session:
        rows = session.execute(
            select(
                approval_decision.c.decision,
                approval_decision.c.approver_kind,
                approval_decision.c.approver_id,
                approval_decision.c.auto_rule_set_version_id,
                approval_decision.c.auto_rule_id,
            ).where(approval_decision.c.approval_request_id == request_id)
        ).all()
    return [tuple(row) for row in rows]


def _bootstrap_rule(tenant_id: UUID) -> tuple[UUID, UUID]:
    """Version 1 of rule set ``AUTO-BOOTSTRAP`` and its rule ``AUTO-BOOTSTRAP``."""
    with tenant_session(_all_entities(tenant_id)) as session:
        version_id, rule_id = session.execute(
            select(rule_set_version.c.id, rule.c.id)
            .select_from(
                rule_set_version.join(
                    rule_set,
                    and_(
                        rule_set.c.tenant_id == rule_set_version.c.tenant_id,
                        rule_set.c.id == rule_set_version.c.rule_set_id,
                    ),
                ).join(
                    rule,
                    and_(
                        rule.c.tenant_id == rule_set_version.c.tenant_id,
                        rule.c.rule_set_version_id == rule_set_version.c.id,
                    ),
                )
            )
            .where(
                rule_set.c.code == "AUTO-BOOTSTRAP",
                rule_set_version.c.version_no == 1,
                rule.c.rule_key == "AUTO-BOOTSTRAP",
            )
        ).one()
    return UUID(str(version_id)), UUID(str(rule_id))


def _actions(tenant_id: UUID, request_id: UUID) -> list[str]:
    with tenant_session(_all_entities(tenant_id)) as session:
        actions = session.scalars(
            select(audit_event.c.action)
            .where(audit_event.c.object_id == request_id)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [str(action) for action in actions]


def _complete_setup(tenant_id: UUID, at: datetime) -> None:
    with tenant_session(_all_entities(tenant_id)) as session:
        session.execute(
            update(tenant).where(tenant.c.id == tenant_id).values(setup_completed_at=at)
        )


def test_krn_apr_01_published_routing_steps(world: World, probe: ProbeSubjects, run: Run) -> None:
    with tenant_session(_all_entities(world.tenant_id)) as session:
        version_id, rule_ids = publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            code="ACCESS-ROUTING",
            rules=[
                {
                    "rule_key": "ROLE-CHANGE",
                    "conditions": [{"field": "subject.type", "op": "eq", "value": "ROLE_CHANGE"}],
                    "outputs": TWO_STEPS,
                }
            ],
        )
    routed = _submit(run, world.accountant, probe, ROLE_CHANGE)
    assert (routed["routing_rule_set_version_id"], routed["routing_rule_id"]) == (
        version_id,
        rule_ids["ROLE-CHANGE"],
    )
    assert _steps(world.tenant_id, routed["id"]) == [
        (1, "Access approval", "access.approve", 1, "ACTIVE"),
        (2, "Second access approval", "access.approve", 1, "WAITING"),
    ]

    # Without a matching rule the subject's default step applies.
    fallback = _submit(run, world.accountant, probe, ApprovalSubjectType.SOD_EXCEPTION)
    assert (fallback["routing_rule_set_version_id"], fallback["routing_rule_id"]) == (None, None)
    assert _steps(world.tenant_id, fallback["id"]) == [
        (1, "Approval", "access.approve", 1, "ACTIVE")
    ]


def test_malformed_routing_outputs_refuse_submission(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    with tenant_session(_all_entities(world.tenant_id)) as session:
        publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            rules=[
                {
                    "rule_key": "NO-STEPS",
                    "conditions": [{"field": "subject.type", "op": "eq", "value": "ROLE_CHANGE"}],
                    "outputs": {"steps": []},
                }
            ],
        )
    with pytest.raises(ValueError, match="names no steps"):
        _submit(run, world.accountant, probe, ROLE_CHANGE)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        subjects = session.scalars(
            select(approval_request.c.subject_type).where(
                approval_request.c.subject_type == ROLE_CHANGE.value
            )
        ).all()
    assert list(subjects) == []


def test_req_plt_016_auto_approval_names_rule(
    world: World, probe: ProbeSubjects, run: Run, clock: FrozenClock
) -> None:
    request = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    assert (request["status"], request["decided_at"]) == ("APPROVED", clock.now())
    version_id, rule_id = _bootstrap_rule(world.tenant_id)
    assert _decisions(world.tenant_id, request["id"]) == [
        ("AUTO_APPROVE", "SYSTEM", None, version_id, rule_id)
    ]
    assert _steps(world.tenant_id, request["id"]) == [
        (1, "Approval", "access.approve", 1, "APPROVED")
    ]
    assert probe.calls == [("approved", request["subject_id"], request["id"])]
    assert _actions(world.tenant_id, request["id"]) == [
        "approval_request.submit",
        "approval_request.auto_approve",
    ]

    # A preparer without tenant_admin waits for a person.
    pending = _submit(run, world.accountant, probe, ROLE_ASSIGNMENT)
    assert pending["status"] == "PENDING"
    assert _decisions(world.tenant_id, pending["id"]) == []


def test_r38_bootstrap_exception_is_the_bootstrap_admins_alone(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    """Supervisor ruling R-38 (iv); PRD BR-PLT-02 "the bootstrap Tenant Admin": the exception is
    the bootstrap Tenant Admin's — the user of the assignment the seed of the workspace wrote,
    here ``tenant.provision`` — not every holder of ``tenant_admin``. Another Tenant Admin's
    grant waits for a person while setup is incomplete; the bootstrap admin's is approved by the
    seeded rule."""
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        assert routing.setup_completed(session, world.tenant_id) is False
        assert world.admin.membership_id is not None
        assert world.other_admin.membership_id is not None
        assert routing.is_bootstrap_admin(session, world.admin.membership_id) is True
        assert routing.is_bootstrap_admin(session, world.other_admin.membership_id) is False
    pending = _submit(run, world.other_admin, probe, ROLE_ASSIGNMENT)
    assert pending["status"] == "PENDING"
    assert _decisions(world.tenant_id, pending["id"]) == []
    assert probe.calls == []

    approved = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    assert approved["status"] == "APPROVED"
    assert probe.calls == [("approved", approved["subject_id"], approved["id"])]


def _is_bootstrap_admin(
    tenant_id: UUID, membership_id: UUID | None, ctx: DbContext | None = None
) -> bool:
    """``routing.is_bootstrap_admin`` in a session of ``ctx`` (every entity without one)."""
    assert membership_id is not None
    with tenant_session(ctx or _all_entities(tenant_id), read_only=True) as session:
        return routing.is_bootstrap_admin(session, membership_id)


def _seeded_rule(session: Any, code: str) -> routing.RuleRef:
    """Version 1 of a rule set provisioning seeds and its one rule, as a decision names them."""
    version_id, rule_id, rule_key = session.execute(
        select(rule_set_version.c.id, rule.c.id, rule.c.rule_key)
        .select_from(
            rule_set_version.join(
                rule_set,
                and_(
                    rule_set.c.tenant_id == rule_set_version.c.tenant_id,
                    rule_set.c.id == rule_set_version.c.rule_set_id,
                ),
            ).join(
                rule,
                and_(
                    rule.c.tenant_id == rule_set_version.c.tenant_id,
                    rule.c.rule_set_version_id == rule_set_version.c.id,
                ),
            )
        )
        .where(rule_set.c.code == code, rule_set_version.c.version_no == 1)
    ).one()
    return routing.RuleRef(
        rule_set_version_id=UUID(str(version_id)),
        rule_id=UUID(str(rule_id)),
        rule_set_code=code,
        rule_key=str(rule_key),
    )


def _new_member(tenant_id: UUID) -> UUID:
    """Another ACTIVE member of the workspace, without a role; the membership."""
    with identity_session(request_id="tests-routing-mark") as session:
        user_id = insert_app_user(session)
    with tenant_session(_all_entities(tenant_id)) as session:
        return insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)


def _granted_by_rows(
    world: World,
    clock: FrozenClock,
    *,
    role_code: str = "tenant_admin",
    subject_type: ApprovalSubjectType = ROLE_ASSIGNMENT,
    subject_is_the_assignment: bool = True,
    preparer: tuple[PrincipalKind, UUID | None] = (PrincipalKind.SYSTEM, None),
    approved_by: str | None = routing.AUTO_BOOTSTRAP,
    decided_by: UUID | None = None,
) -> UUID:
    """A new member whose assignment of ``role_code`` names a request written as the seed of a
    workspace writes its own (``provisioning.grant_bootstrap_admin``: ``insert_request``, then
    ``record_auto_approval``) — but for the one part a case changes. With ``decided_by`` the
    request is left PENDING and holds a row no code writes and every check admits: that
    person's APPROVE, naming the rule. The membership."""
    now = clock.now()
    membership_id = _new_member(world.tenant_id)
    assignment_id, request_id = new_id(), new_id()
    with tenant_session(_all_entities(world.tenant_id)) as session:
        role_id = session.execute(select(role.c.id).where(role.c.code == role_code)).scalar_one()
        insert_request(
            session,
            values={
                "tenant_id": world.tenant_id,
                "id": request_id,
                "request_no": f"APR-T{secrets.token_hex(5)}",
                "subject_type": subject_type.value,
                "subject_id": assignment_id if subject_is_the_assignment else new_id(),
                "subject_content_sha256": PROBE_CONTENT_SHA256,
                "summary": "A grant written by rows",
                **entity_columns(ALL_ENTITIES),
                "amount_functional": None,
                "amount_currency": None,
                "flags": [],
                "preparer_id": preparer[1],
                "preparer_kind": preparer[0].value,
                "impact_preview_file_id": None,
                "impact_preview_sha256": None,
                "reason_code": None,
                "comment": None,
                "created_by": None,
                "created_by_kind": PrincipalKind.SYSTEM.value,
            },
            routed=routing.Routing(steps=(provisioning.BOOTSTRAP_STEP,), rule=None),
            now=now,
        )
        if approved_by is not None and decided_by is None:
            record_auto_approval(
                session,
                tenant_id=world.tenant_id,
                approval_request_id=request_id,
                subject_content_sha256=PROBE_CONTENT_SHA256,
                rule=_seeded_rule(session, approved_by),
                now=now,
            )
        elif approved_by is not None:
            named = _seeded_rule(session, approved_by)
            session.execute(
                insert(approval_decision).values(
                    tenant_id=world.tenant_id,
                    id=new_id(),
                    approval_request_id=request_id,
                    approval_step_id=session.execute(
                        select(approval_step.c.id).where(
                            approval_step.c.approval_request_id == request_id
                        )
                    ).scalar_one(),
                    decision="APPROVE",
                    approver_id=decided_by,
                    approver_kind=PrincipalKind.USER.value,
                    auto_rule_set_version_id=named.rule_set_version_id,
                    auto_rule_id=named.rule_id,
                    subject_content_sha256=PROBE_CONTENT_SHA256,
                    mfa_verified_at=now,
                    decided_at=now,
                )
            )
        row = assignment_row(
            world.tenant_id, membership_id=membership_id, role_id=UUID(str(role_id))
        )
        session.execute(
            insert(role_assignment).values(
                **row | {"id": assignment_id, "approval_request_id": request_id}
            )
        )
    return membership_id


def _admin_by_rows(world: World, **columns: Any) -> UUID:
    """A new member with a ``tenant_admin`` assignment written by rows, as
    ``support.rows.assignment_row`` builds it but for ``columns``. The membership."""
    membership_id = _new_member(world.tenant_id)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        role_id = session.execute(
            select(role.c.id).where(role.c.code == "tenant_admin")
        ).scalar_one()
        row = assignment_row(
            world.tenant_id, membership_id=membership_id, role_id=UUID(str(role_id))
        )
        session.execute(insert(role_assignment).values(**row | columns))
    return membership_id


def test_the_bootstrap_admin_is_known_by_every_part_of_the_seed_grant(
    world: World, clock: FrozenClock
) -> None:
    """04 §14.3 item 2 rev 1.254 (item SBX-EMPTY-BOOTSTRAP-1; the supervisor's ruling of
    2026-10-01): the bootstrap Tenant Admin is the user of the ``tenant_admin`` assignment whose
    ``approval_request_id`` names its own ``ROLE_ASSIGNMENT`` request — the request's subject
    is that assignment — prepared by SYSTEM with no preparer and approved by rule
    ``AUTO-BOOTSTRAP``: the pair the seed of a workspace writes. Each member here holds a pair
    written with the kernel's own two functions, as the seed writes its own. The first holds
    the whole of it; every other lacks one part — the role, the subject type, the request
    being the assignment's own, the absent preparer, the approval, its being the rule's own
    decision, the rule — and is not the bootstrap admin.

    Two more members hold no pair of their own. One holds a ``tenant_admin`` assignment that
    names the provisioned admin's request: a request has one subject, so a second assignment
    does not share the seed's. The other holds what the mark was before this revision — a
    ``tenant_admin`` assignment stamped ``OPERATOR`` that names no request, which is what an
    operator's recovery grant writes (item APR-RECOVERY-1): a recovery grant is not the
    workspace's seed.

    Fail-first (the stamp as the mark): the first member was not the bootstrap admin, the last
    one was."""
    assert world.admin.id is not None and world.accountant.id is not None
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        seed_request = session.execute(
            select(role_assignment.c.approval_request_id).where(
                role_assignment.c.membership_id == world.admin.membership_id
            )
        ).scalar_one()
    members = {
        "the pair of the seed": _granted_by_rows(world, clock),
        "another role": _granted_by_rows(world, clock, role_code="viewer"),
        "another subject type": _granted_by_rows(world, clock, subject_type=ROLE_CHANGE),
        "the request of another assignment": _granted_by_rows(
            world, clock, subject_is_the_assignment=False
        ),
        "a member prepared it": _granted_by_rows(
            world, clock, preparer=(PrincipalKind.USER, world.admin.id)
        ),
        "SYSTEM, for a preparer": _granted_by_rows(
            world, clock, preparer=(PrincipalKind.SYSTEM, world.admin.id)
        ),
        "nothing approved it": _granted_by_rows(world, clock, approved_by=None),
        "a person approved it, naming the rule": _granted_by_rows(
            world, clock, decided_by=world.accountant.id
        ),
        "another seeded rule approved it": _granted_by_rows(
            world, clock, approved_by=routing.AUTO_MIGRATION
        ),
        "an assignment that names the seed's request": _admin_by_rows(
            world, approval_request_id=seed_request
        ),
        "an operator's grant without a request": _admin_by_rows(
            world, created_by_kind=PrincipalKind.OPERATOR.value
        ),
    }
    answered = {
        name: _is_bootstrap_admin(world.tenant_id, membership_id)
        for name, membership_id in members.items()
    }
    assert answered == {name: name == "the pair of the seed" for name in members}


def test_the_bootstrap_admin_is_read_from_the_seed_grant_once_it_is_revoked(
    world: World, clock: FrozenClock
) -> None:
    """04 §14.3 item 2 rev 1.254: the assignment the seed wrote counts whether or not it is still
    in force — that the preparer still holds the role is the engine's second fact, read from the
    preparer's role codes, not from this row. Every world built on
    ``support.principals.member`` stands on it: that helper revokes the provisioned grant and
    the world then writes its own assignments, which name no request."""
    admin = world.admin.membership_id
    assert admin is not None
    with tenant_session(_all_entities(world.tenant_id)) as session:
        revoke_role_assignments(
            session, tenant_id=world.tenant_id, membership_id=admin, at=clock.now()
        )
        revoked = session.scalars(
            select(role_assignment.c.revoked_at).where(role_assignment.c.membership_id == admin)
        ).all()
    assert len(revoked) == 1 and revoked[0] is not None  # the one row: the provisioned grant
    assert _is_bootstrap_admin(world.tenant_id, admin) is True


def test_the_bootstrap_admin_is_read_whatever_the_callers_entity_scope(world: World) -> None:
    """04 §14.3 item 2 rev 1.254: the engine asks in the preparer's own session, whose entity
    scope is the union of the preparer's grants — one entity for an admin who holds the role for
    one entity, none for a member without a grant. The seed's request is for all entities, so
    its ``entity_id`` is null and the policy of T-PLT-17 shows it to every scope; the other rows
    of the mark are the tenant's (RLS-T). A scope that hid one of them would end the exception
    for an admin of named entities and for nobody else. Another Tenant Admin, whose assignment
    names no request, is none in any scope."""
    assert world.admin.id is not None
    another = _admin_by_rows(world)
    for scope in ((new_id(),), ()):
        ctx = DbContext(tenant_id=world.tenant_id, user_id=world.admin.id, entity_scope=scope)
        assert _is_bootstrap_admin(world.tenant_id, world.admin.membership_id, ctx) is True
        assert _is_bootstrap_admin(world.tenant_id, another, ctx) is False


def test_r38_bootstrap_exception_ends_with_a_second_approver(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    """Addendum to R-38 (iv); BR-PLT-02's reason "a new tenant has no second approver": as soon as
    another ACTIVE member holds ``access.approve`` the bootstrap admin's grants route to that
    person, whatever the setup state. No second approver — auto-approved; a second approver,
    setup still incomplete — PENDING, and that person approves it."""
    first = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    assert first["status"] == "APPROVED"  # no second approver yet

    assert world.other_admin.membership_id is not None
    with tenant_session(_all_entities(world.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=world.other_admin.membership_id,
            role_code="tenant_admin",
        )
        assert routing.setup_completed(session, world.tenant_id) is False
    routed = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    assert routed["status"] == "PENDING"
    assert _steps(world.tenant_id, routed["id"]) == [(1, "Approval", "access.approve", 1, "ACTIVE")]
    assert _decisions(world.tenant_id, routed["id"]) == []

    opener: AbstractContextManager[UnitOfWork] = run(world.other_admin)
    with opener as uow:
        decided = decide(
            uow,
            approval_request_id=routed["id"],
            decision="APPROVE",
            subject_content_sha256=routed["subject_content_sha256"],
            impact_preview_sha256=routed["impact_preview_sha256"],
            comment=None,
            reason_code=None,
        )
        uow.commit()
    assert decided["status"] == "APPROVED"
    assert [row[:3] for row in _decisions(world.tenant_id, routed["id"])] == [
        ("APPROVE", "USER", world.other_admin.id)
    ]


GONE: str = "The second approver leaves the workspace"


@pytest.mark.parametrize("fate", ["suspended", "removed", "revoked", "expired"])
def test_r66_bootstrap_exception_does_not_return_when_the_second_approver_goes(
    world: World, probe: ProbeSubjects, run: Run, clock: FrozenClock, fate: str
) -> None:
    """Supervisor rulings R-66 (2) and R-73: the bootstrap exception ends one way. Once a person
    other than the bootstrap Tenant Admin has been ACTIVE in the workspace while holding
    ``access.approve``, ``AUTO-BOOTSTRAP`` never matches again, whatever that person's later
    status, revocation or expiry. The bootstrap admin suspends or removes the second approver,
    or revokes the grant, or the grant runs out: none of it is refused (R-73: taking access away
    never waits for a second approver) and the next grant still waits for a person. Under the
    earlier reading — no other member holds the permission NOW — each of the four brought the
    exception back: suspend the approver, grant, reactivate."""
    other = world.other_admin
    assert other.membership_id is not None and world.admin.membership_id is not None
    assert _submit(run, world.admin, probe, ROLE_ASSIGNMENT)["status"] == "APPROVED"  # alone
    with tenant_session(_all_entities(world.tenant_id)) as session:
        assignment_id = insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=other.membership_id,
            role_code="tenant_admin",
            valid_to=clock.now() + timedelta(minutes=1) if fate == "expired" else None,
        )
    assert _submit(run, world.admin, probe, ROLE_ASSIGNMENT)["status"] == "PENDING"

    # The second approver goes — by a command of the bootstrap admin that is not refused, or by
    # the passing of time — after having been an active access approver for a while (a grant
    # that ended the instant its holder was activated was never held).
    if fate == "expired":
        clock.advance(timedelta(minutes=5))
    else:
        clock.advance(timedelta(seconds=30))
        opener: AbstractContextManager[UnitOfWork] = run(world.admin)
        with opener as uow:
            if fate == "suspended":
                users.suspend_membership(uow, other.membership_id, reason=GONE)
            elif fate == "removed":
                users.remove_membership(uow, other.membership_id, reason=GONE)
            else:
                roles.revoke_role_assignment(uow, assignment_id, reason=GONE)
            uow.commit()
        clock.advance(timedelta(minutes=5))
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        # Nobody else can approve access now: the state the exception was made for.
        status = session.execute(
            select(tenant_membership.c.status).where(tenant_membership.c.id == other.membership_id)
        ).scalar_one()
        assert (str(status) == MembershipStatus.ACTIVE.value) == (fate in ("revoked", "expired"))
        assert routing.second_approver_has_existed(
            session,
            bootstrap_membership_id=world.admin.membership_id,
            permission="access.approve",
            at=clock.now(),
        )

    again = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    assert again["status"] == "PENDING"
    assert _decisions(world.tenant_id, again["id"]) == []
    assert _steps(world.tenant_id, again["id"]) == [(1, "Approval", "access.approve", 1, "ACTIVE")]


def test_r66_only_an_approver_who_was_active_ends_the_bootstrap_exception(
    world: World, probe: ProbeSubjects, run: Run, clock: FrozenClock
) -> None:
    """The other side of R-66 (2): the exception ends when another person HAS BEEN ACTIVE WHILE
    HOLDING the permission — not before. A Tenant Admin who was invited and never accepted, a
    grant revoked before its holder accepted the invitation, and an active member whose role
    carries no ``access.approve`` end nothing: the workspace still has no second approver and
    the bootstrap admin's grants are still setup grants."""
    assert world.admin.membership_id is not None and world.accountant.membership_id is not None
    with identity_session(request_id="tests-routing-invited") as session:
        invited_user, late_user = insert_app_user(session), insert_app_user(session)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        invited = membership_row(RowContext(world.tenant_id, invited_user))  # INVITED
        session.execute(tenant_membership.insert().values(**invited))
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=UUID(str(invited["id"])),
            role_code="tenant_admin",
        )
        # Granted in January and revoked in June; the member accepted in September.
        late = insert_active_membership(session, tenant_id=world.tenant_id, user_id=late_user)
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=late,
            role_code="tenant_admin",
            revoked_at=ASSIGNED_FROM + timedelta(days=150),
        )
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=world.accountant.membership_id,
            role_code="revenue_reviewer",
        )
        assert not routing.second_approver_has_existed(
            session,
            bootstrap_membership_id=world.admin.membership_id,
            permission="access.approve",
            at=clock.now(),
        )
    request = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    assert request["status"] == "APPROVED"
    version_id, rule_id = _bootstrap_rule(world.tenant_id)
    assert _decisions(world.tenant_id, request["id"]) == [
        ("AUTO_APPROVE", "SYSTEM", None, version_id, rule_id)
    ]


def test_r41_foreign_rule_neither_approves_nor_outranks_the_seeded_one(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    """R-26 (b) / R-41 (7), the AUTO-BOOTSTRAP pin isolated (the review's gap): a published rule
    of ANOTHER rule set names ``ROLE_ASSIGNMENT`` for Tenant Admins with a higher priority and
    more conditions than the seeded rule. It approves nobody — another Tenant Admin's grant stays
    PENDING — and it does not outrank the seeded rule: the bootstrap admin's grant is approved by
    ``AUTO-BOOTSTRAP``, which the decision names."""
    with tenant_session(_all_entities(world.tenant_id)) as session:
        foreign_version, foreign_rules = publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            code="SEC-AUTO-ROLE",
            rules=[
                {
                    "rule_key": "ANY-ADMIN",
                    "priority": 100,
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": "ROLE_ASSIGNMENT"},
                        {"field": "preparer.role_codes", "op": "in", "value": ["tenant_admin"]},
                        {"field": "source.channel", "op": "eq", "value": "USER"},
                        {"field": "tenant.setup_completed", "op": "eq", "value": False},
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
        )
    pending = _submit(run, world.other_admin, probe, ROLE_ASSIGNMENT)
    assert pending["status"] == "PENDING"
    assert _decisions(world.tenant_id, pending["id"]) == []

    approved = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    version_id, rule_id = _bootstrap_rule(world.tenant_id)
    assert _decisions(world.tenant_id, approved["id"]) == [
        ("AUTO_APPROVE", "SYSTEM", None, version_id, rule_id)
    ]
    assert (version_id, rule_id) != (foreign_version, foreign_rules["ANY-ADMIN"])


def test_auto_bootstrap_stops_after_setup_completion(
    world: World, probe: ProbeSubjects, run: Run, clock: FrozenClock
) -> None:
    _complete_setup(world.tenant_id, clock.now())
    request = _submit(run, world.admin, probe, ROLE_ASSIGNMENT)
    assert request["status"] == "PENDING"
    assert _steps(world.tenant_id, request["id"]) == [
        (1, "Approval", "access.approve", 1, "ACTIVE")
    ]
    assert _decisions(world.tenant_id, request["id"]) == []
    assert probe.calls == []


def test_br_plt_02_setup_completed(world: World, clock: FrozenClock) -> None:
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        assert setup_completed(session, world.tenant_id) is False
    _complete_setup(world.tenant_id, clock.now())
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        assert setup_completed(session, world.tenant_id) is True


def _step_roles(tenant_id: UUID, request_id: UUID) -> list[UUID | None]:
    with tenant_session(_all_entities(tenant_id)) as session:
        rows = session.execute(
            select(approval_step.c.required_role_id)
            .where(approval_step.c.approval_request_id == request_id)
            .order_by(approval_step.c.step_no)
        ).all()
    return [row[0] for row in rows]


def test_d98_93_published_step_role_parses_into_required_role_id(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    """04 T-REF-26 ``role`` (D-98 93): a published step naming an active role code routes with that
    role as T-PLT-18 ``required_role_id``; a step without one stays open to every holder of the
    permission (a step name is never an enforced role)."""
    with tenant_session(_all_entities(world.tenant_id)) as session:
        controller = session.execute(
            select(role.c.id).where(role.c.code == "controller")
        ).scalar_one()
        _, rule_ids = publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            code="ACCESS-ROUTING-ROLE",
            rules=[
                {
                    "rule_key": "ROLE-CHANGE-CTRL",
                    "conditions": [{"field": "subject.type", "op": "eq", "value": "ROLE_CHANGE"}],
                    "outputs": {
                        "steps": [
                            {
                                "name": "Access approval",
                                "permission": "access.approve",
                                "min_approvers": 1,
                            },
                            {
                                "name": "Controller approval",
                                "permission": "access.approve",
                                "min_approvers": 1,
                                "role": "controller",
                            },
                        ]
                    },
                }
            ],
        )
    routed = _submit(run, world.accountant, probe, ROLE_CHANGE)
    assert routed["routing_rule_id"] == rule_ids["ROLE-CHANGE-CTRL"]
    assert _steps(world.tenant_id, routed["id"]) == [
        (1, "Access approval", "access.approve", 1, "ACTIVE"),
        (2, "Controller approval", "access.approve", 1, "WAITING"),
    ]
    assert _step_roles(world.tenant_id, UUID(str(routed["id"]))) == [None, controller]


def test_d98_93_unknown_step_role_refuses_submission(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    """A published step naming an unknown or inactive role code refuses the submission (fail
    closed) instead of routing without the restriction the rule states."""
    with tenant_session(_all_entities(world.tenant_id)) as session:
        publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            rules=[
                {
                    "rule_key": "ROLE-CHANGE-GHOST",
                    "conditions": [{"field": "subject.type", "op": "eq", "value": "ROLE_CHANGE"}],
                    "outputs": {
                        "steps": [
                            {
                                "name": "Ghost approval",
                                "permission": "access.approve",
                                "min_approvers": 1,
                                "role": "chief_wizard",
                            }
                        ]
                    },
                }
            ],
        )
    with pytest.raises(ValueError, match="names no active role"):
        _submit(run, world.accountant, probe, ROLE_CHANGE)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        subjects = session.scalars(
            select(approval_request.c.subject_type).where(
                approval_request.c.subject_type == ROLE_CHANGE.value
            )
        ).all()
    assert list(subjects) == []
