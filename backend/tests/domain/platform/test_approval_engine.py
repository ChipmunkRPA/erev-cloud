"""Approval engine (dev-guide §5.6 DG-KRN-APR-01 to DG-KRN-APR-05; 04 T-PLT-17, T-PLT-18,
T-PLT-20, T-PLT-21; PRD SM-01, BR-PLT-05, BR-PLT-07, ERR-02 to ERR-04; REQ-PLT-011, REQ-PLT-013 to
REQ-PLT-015, REQ-PLT-017; BUILD_SPEC PLF-10, PLF-11)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

import pytest
from erev_api.approvals.engine import (
    BulkApproveItem,
    ImpactPreview,
    bulk_approve,
    decide,
    submit,
    void_if_stale,
    withdraw,
)
from erev_api.auth import sod
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_delegation,
    approval_request,
    approval_step,
    audit_event,
    file_object,
    role,
    role_assignment,
    tenant,
    tenant_membership,
)
from erev_api.domain.platform import roles, users
from erev_api.enums import ApprovalSubjectType, PrincipalKind, RuleSetKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork, unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import exc, func, insert, select, text, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    approval_delegation_values,
    insert_active_membership,
    insert_app_user,
    insert_role_assignment,
    publish_rule_set,
)
from support.subjects import ProbeCallbackError, ProbeSubjects, install

MFA_VERIFIED_AT = datetime(2026, 9, 12, 11, 58, tzinfo=UTC)
PERMISSION = "access.approve"
SUBJECT = ApprovalSubjectType.ROLE_CHANGE
# PRD ERR-04 copy.
STALE_COPY = (
    "This item changed after submission, so the approval request was voided. "
    "Review the latest version."
)

Run = Callable[[Principal], AbstractContextManager[UnitOfWork]]


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    preparer: Principal
    approver_a: Principal
    approver_b: Principal


def _person(tenant_id: UUID, user_id: UUID, membership_id: UUID) -> Principal:
    """A signed-in, MFA-verified member holding ``access.approve`` for every entity."""
    scopes: dict[str, Any] = {PERMISSION: "*"}
    return Principal(
        kind=PrincipalKind.USER,
        id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
        display_name="Probe person",
        roles=("tenant_admin",),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=MFA_VERIFIED_AT,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def world(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> World:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    with identity_session(request_id="tests-approval-users") as session:
        users = [insert_app_user(session) for _ in range(3)]
    with tenant_session(_all_entities(tenant_id)) as session:
        people = [
            _person(
                tenant_id,
                user_id,
                insert_active_membership(session, tenant_id=tenant_id, user_id=user_id),
            )
            for user_id in users
        ]
    return World(
        tenant_id=tenant_id, preparer=people[0], approver_a=people[1], approver_b=people[2]
    )


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> ProbeSubjects:
    subjects = ProbeSubjects()
    install(monkeypatch, subjects.spec(SUBJECT))
    return subjects


def _context(principal: Principal, clock: FrozenClock) -> RequestContext:
    return RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-approvals",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


@pytest.fixture
def run(clock: FrozenClock, keyring: KeyRing, app_settings: Settings) -> Run:
    @contextmanager
    def open_uow(principal: Principal) -> Iterator[UnitOfWork]:
        files = LocalFileStore(app_settings.file_root)
        with unit_of_work(
            _context(principal, clock), clock=clock, keyring=keyring, files=files
        ) as uow:
            yield uow

    return open_uow


def _two_steps(world: World) -> None:
    """Publish an ``APPROVAL_ROUTING`` rule giving ``ROLE_CHANGE`` two ``access.approve`` steps."""
    steps = [
        {"name": "Access approval", "permission": PERMISSION, "min_approvers": 1},
        {"name": "Second access approval", "permission": PERMISSION, "min_approvers": 1},
    ]
    with tenant_session(_all_entities(world.tenant_id)) as session:
        publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            rules=[
                {
                    "rule_key": "ROLE-CHANGE-TWO-STEPS",
                    "conditions": [{"field": "subject.type", "op": "eq", "value": SUBJECT.value}],
                    "outputs": {"steps": steps},
                }
            ],
        )


def _submit(run: Run, world: World, probe: ProbeSubjects, **kwargs: Any) -> Mapping[str, Any]:
    subject_id = probe.new_subject(role="access_approver")
    with run(world.preparer) as uow:
        request = submit(
            uow,
            subject_type=SUBJECT,
            subject_id=subject_id,
            summary="Change the access approver role",
            **kwargs,
        )
        uow.commit()
    return request


def _decision_args(
    request: Mapping[str, Any], decision: Literal["APPROVE", "REJECT"], comment: str | None
) -> dict[str, Any]:
    return {
        "approval_request_id": request["id"],
        "decision": decision,
        "subject_content_sha256": request["subject_content_sha256"],
        "impact_preview_sha256": request["impact_preview_sha256"],
        "comment": comment,
        "reason_code": None,
    }


def _decide(
    run: Run,
    principal: Principal,
    request: Mapping[str, Any],
    decision: Literal["APPROVE", "REJECT"] = "APPROVE",
    comment: str | None = None,
) -> Mapping[str, Any]:
    with run(principal) as uow:
        row = decide(uow, **_decision_args(request, decision, comment))
        uow.commit()
    return row


def _refused(
    run: Run,
    principal: Principal,
    request: Mapping[str, Any],
    decision: Literal["APPROVE", "REJECT"] = "APPROVE",
) -> Problem:
    with run(principal) as uow, pytest.raises(Problem) as excinfo:
        decide(uow, **_decision_args(request, decision, None))
    return excinfo.value


def _state(tenant_id: UUID, request_id: UUID) -> tuple[str, list[tuple[int, str]], int]:
    """Request status, (step_no, status) of every step, and the number of decisions."""
    with tenant_session(_all_entities(tenant_id)) as session:
        status = session.execute(
            select(approval_request.c.status).where(approval_request.c.id == request_id)
        ).scalar_one()
        steps = session.execute(
            select(approval_step.c.step_no, approval_step.c.status)
            .where(approval_step.c.approval_request_id == request_id)
            .order_by(approval_step.c.step_no)
        ).all()
        decisions = session.execute(
            select(func.count()).where(approval_decision.c.approval_request_id == request_id)
        ).scalar_one()
    return str(status), [(int(no), str(step)) for no, step in steps], int(decisions)


def test_krn_apr_01_submit_stores_hash_and_one_step(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    request = _submit(run, world, probe)
    # Provisioning numbered the bootstrap admin grant APR-000001 (04 §14.3 item 2).
    assert request["request_no"] == "APR-000002"
    assert request["status"] == "PENDING"
    assert request["subject_content_sha256"] == sha256_hex(probe.contents[request["subject_id"]])
    assert (request["preparer_id"], request["preparer_kind"]) == (world.preparer.id, "USER")
    with tenant_session(_all_entities(world.tenant_id)) as session:
        steps = session.execute(
            select(
                approval_step.c.step_no,
                approval_step.c.status,
                approval_step.c.required_permission,
                approval_step.c.min_approvers,
            ).where(approval_step.c.approval_request_id == request["id"])
        ).all()
        actions = session.scalars(
            select(audit_event.c.action).where(audit_event.c.object_id == request["id"])
        ).all()
    assert [tuple(step) for step in steps] == [(1, "ACTIVE", PERMISSION, 1)]
    assert list(actions) == ["approval_request.submit"]


def test_req_plt_015_preview_required_for_revenue_affecting(
    world: World, probe: ProbeSubjects, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, probe.spec(SUBJECT, revenue_affecting=True))
    with run(world.preparer) as uow, pytest.raises(Problem) as excinfo:
        submit(uow, subject_type=SUBJECT, subject_id=probe.new_subject(), summary="No preview")
    assert (excinfo.value.slug, excinfo.value.status) == ("validation-failed", 422)
    assert [(error.field, error.rule_id) for error in excinfo.value.errors] == [
        ("impact_preview", "REQ-PLT-015")
    ]

    preview = ImpactPreview(
        before={"revenue_by_period": {"2026-09": "1200.00"}},
        after={"revenue_by_period": {"2026-09": "1500.00"}},
    )
    request = _submit(run, world, probe, impact_preview=preview)
    assert request["impact_preview_sha256"] == preview.sha256()
    with tenant_session(_all_entities(world.tenant_id)) as session:
        stored = session.execute(
            select(file_object.c.purpose, file_object.c.sha256, file_object.c.media_type).where(
                file_object.c.id == request["impact_preview_file_id"]
            )
        ).one()
    assert tuple(stored) == ("IMPACT_PREVIEW", preview.sha256(), "application/json")


@pytest.mark.control("CTL-014")
def test_ctl_014_preparer_cannot_approve(world: World, probe: ProbeSubjects, run: Run) -> None:
    request = _submit(run, world, probe)
    problem = _refused(run, world.preparer, request)
    assert (problem.slug, problem.status) == ("self-approval", 403)
    assert _state(world.tenant_id, request["id"]) == ("PENDING", [(1, "ACTIVE")], 0)


@pytest.mark.control("CTL-034")
def test_ctl_034_repeat_approver_blocked_on_later_step(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    _two_steps(world)
    request = _submit(run, world, probe)
    after_first = _decide(run, world.approver_a, request)
    assert (after_first["status"], after_first["current_step_no"]) == ("PENDING", 2)

    problem = _refused(run, world.approver_a, request)
    assert (problem.slug, problem.status) == ("approver-already-decided", 409)
    assert _state(world.tenant_id, request["id"]) == (
        "PENDING",
        [(1, "APPROVED"), (2, "ACTIVE")],
        1,
    )

    final = _decide(run, world.approver_b, request)
    assert final["status"] == "APPROVED"
    assert _state(world.tenant_id, request["id"]) == (
        "APPROVED",
        [(1, "APPROVED"), (2, "APPROVED")],
        2,
    )
    assert probe.calls == [("approved", request["subject_id"], request["id"])]


def test_krn_apr_02_on_approved_runs_in_transaction(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    request = _submit(run, world, probe)
    probe.fail_on_approved = True
    with run(world.approver_a) as uow, pytest.raises(ProbeCallbackError):
        decide(uow, **_decision_args(request, "APPROVE", None))
    assert _state(world.tenant_id, request["id"]) == ("PENDING", [(1, "ACTIVE")], 0)

    probe.fail_on_approved = False
    assert _decide(run, world.approver_a, request)["status"] == "APPROVED"


def test_krn_apr_04_non_human_principals_never_decide(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    request = _submit(run, world, probe)
    api_client = replace(
        world.approver_a,
        kind=PrincipalKind.API_CLIENT,
        id=new_id(),
        membership_id=None,
        auth_method="client_credentials",
    )
    for principal in (api_client, system_principal(world.tenant_id)):
        problem = _refused(run, principal, request)
        assert (problem.slug, problem.status) == ("forbidden", 403)
    assert _state(world.tenant_id, request["id"]) == ("PENDING", [(1, "ACTIVE")], 0)


def test_decide_requires_mfa_verified_session(world: World, probe: ProbeSubjects, run: Run) -> None:
    request = _submit(run, world, probe)
    problem = _refused(run, replace(world.approver_a, mfa_verified_at=None), request)
    assert (problem.slug, problem.status) == ("mfa-required", 403)
    assert _state(world.tenant_id, request["id"]) == ("PENDING", [(1, "ACTIVE")], 0)


def test_sm_01_rejection_needs_a_comment(world: World, probe: ProbeSubjects, run: Run) -> None:
    request = _submit(run, world, probe)
    problem = _refused(run, world.approver_a, request, decision="REJECT")
    assert (problem.slug, problem.status) == ("validation-failed", 422)
    assert [(error.field, error.rule_id) for error in problem.errors] == [("comment", "T-PLT-20")]

    rejected = _decide(
        run, world.approver_a, request, decision="REJECT", comment="Grants more than requested."
    )
    assert rejected["status"] == "REJECTED"
    assert _state(world.tenant_id, request["id"]) == ("REJECTED", [(1, "REJECTED")], 1)
    assert probe.calls == [("rejected", request["subject_id"], request["id"])]


def _request(tenant_id: UUID, request_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_all_entities(tenant_id)) as session:
        row = (
            session.execute(select(approval_request).where(approval_request.c.id == request_id))
            .mappings()
            .one()
        )
        return dict(row)


def _actions(tenant_id: UUID, request_id: UUID) -> list[str]:
    with tenant_session(_all_entities(tenant_id)) as session:
        actions = session.scalars(
            select(audit_event.c.action)
            .where(audit_event.c.object_id == request_id)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [str(action) for action in actions]


def _outcomes(tenant_id: UUID, request_id: UUID) -> list[tuple[str, str]]:
    """(action, outcome) of every audit event on the request, in chain order."""
    with tenant_session(_all_entities(tenant_id)) as session:
        rows = session.execute(
            select(audit_event.c.action, audit_event.c.outcome)
            .where(audit_event.c.object_id == request_id)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [(str(action), str(outcome)) for action, outcome in rows]


@pytest.mark.control("CTL-007")
def test_req_plt_014_changed_subject_voids_request(
    world: World, probe: ProbeSubjects, run: Run, clock: FrozenClock
) -> None:
    request = _submit(run, world, probe)
    probe.contents[request["subject_id"]]["role"] = "tenant_admin"
    problem = _refused(run, world.approver_a, request)
    assert (problem.slug, problem.status, problem.detail) == ("stale-approval", 409, STALE_COPY)
    # The void survives the refused decision.
    assert _state(world.tenant_id, request["id"]) == ("VOIDED", [(1, "VOIDED")], 0)
    row = _request(world.tenant_id, request["id"])
    assert (row["void_reason"], row["voided_at"], row["decided_at"]) == (
        "STALE_SUBJECT",
        clock.now(),
        None,
    )
    assert _actions(world.tenant_id, request["id"]) == [
        "approval_request.submit",
        "approval_request.void",
    ]
    assert probe.calls == [("voided", request["subject_id"], request["id"])]

    # A voided request takes no further decision.
    problem = _refused(run, world.approver_b, request)
    assert (problem.slug, problem.status) == ("invalid-transition", 409)


def test_krn_apr_02_client_hash_mismatch_voids(
    world: World, probe: ProbeSubjects, run: Run
) -> None:
    request = _submit(run, world, probe)
    reviewed = {**request, "subject_content_sha256": sha256_hex({"name": "An earlier version"})}
    problem = _refused(run, world.approver_a, reviewed)
    assert (problem.slug, problem.status) == ("stale-approval", 409)
    assert _state(world.tenant_id, request["id"]) == ("VOIDED", [(1, "VOIDED")], 0)
    assert _request(world.tenant_id, request["id"])["void_reason"] == "STALE_SUBJECT"
    assert _actions(world.tenant_id, request["id"]) == [
        "approval_request.submit",
        "approval_request.void",
    ]


def test_krn_apr_05_void_if_stale(world: World, probe: ProbeSubjects, run: Run) -> None:
    with run(world.preparer) as uow:
        assert void_if_stale(uow, subject_type=SUBJECT, subject_id=probe.new_subject()) is None
    request = _submit(run, world, probe)
    subject_id = request["subject_id"]
    with run(world.preparer) as uow:
        assert void_if_stale(uow, subject_type=SUBJECT, subject_id=subject_id) is None
    assert _state(world.tenant_id, request["id"]) == ("PENDING", [(1, "ACTIVE")], 0)

    probe.contents[subject_id]["role"] = "tenant_admin"
    with run(world.preparer) as uow:
        voided = void_if_stale(uow, subject_type=SUBJECT, subject_id=subject_id)
        uow.commit()
    assert voided is not None
    assert (voided["id"], voided["status"], voided["void_reason"]) == (
        request["id"],
        "VOIDED",
        "STALE_SUBJECT",
    )
    assert _state(world.tenant_id, request["id"]) == ("VOIDED", [(1, "VOIDED")], 0)
    assert probe.calls == [("voided", subject_id, request["id"])]


def test_withdraw_preparer_only(world: World, probe: ProbeSubjects, run: Run) -> None:
    _two_steps(world)
    request = _submit(run, world, probe)
    with run(world.approver_a) as uow, pytest.raises(Problem) as excinfo:
        withdraw(uow, approval_request_id=request["id"], comment=None)
    assert (excinfo.value.slug, excinfo.value.status) == ("forbidden", 403)
    assert _state(world.tenant_id, request["id"]) == ("PENDING", [(1, "ACTIVE"), (2, "WAITING")], 0)

    with run(world.preparer) as uow:
        row = withdraw(uow, approval_request_id=request["id"], comment="Submitted the wrong role.")
        uow.commit()
    assert (row["status"], row["void_reason"]) == ("WITHDRAWN", "WITHDRAWN_BY_PREPARER")
    assert _state(world.tenant_id, request["id"]) == (
        "WITHDRAWN",
        [(1, "VOIDED"), (2, "VOIDED")],
        0,
    )
    # Item APR-DENIED-AUDIT-1: the approver's refused withdrawal is on record as DENIED, before
    # the preparer's own.
    assert _outcomes(world.tenant_id, request["id"]) == [
        ("approval_request.submit", "SUCCESS"),
        ("approval_request.withdraw", "DENIED"),
        ("approval_request.withdraw", "SUCCESS"),
    ]
    assert probe.calls == [("voided", request["subject_id"], request["id"])]

    with run(world.preparer) as uow, pytest.raises(Problem) as again:
        withdraw(uow, approval_request_id=request["id"], comment=None)
    assert (again.value.slug, again.value.status) == ("invalid-transition", 409)


def test_krn_apr_03_bulk_approve_independent_items(
    world: World,
    probe: ProbeSubjects,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    app_settings: Settings,
) -> None:
    requests = [_submit(run, world, probe) for _ in range(3)]
    probe.contents[requests[1]["subject_id"]]["role"] = "tenant_admin"
    items = [
        BulkApproveItem(
            approval_request_id=request["id"],
            subject_content_sha256=request["subject_content_sha256"],
            impact_preview_sha256=request["impact_preview_sha256"],
        )
        for request in requests
    ]
    ctx = _context(world.approver_a, clock)
    files = LocalFileStore(app_settings.file_root)
    results = bulk_approve(
        ctx, items, comment="Reviewed together.", clock=clock, keyring=keyring, files=files
    )
    assert [(result.approval_request_id, result.status) for result in results] == [
        (requests[0]["id"], "APPROVED"),
        (requests[1]["id"], "VOIDED"),
        (requests[2]["id"], "APPROVED"),
    ]
    assert [
        None if result.problem is None else (result.problem.slug, result.problem.status)
        for result in results
    ] == [None, ("stale-approval", 409), None]
    assert [_state(world.tenant_id, request["id"]) for request in requests] == [
        ("APPROVED", [(1, "APPROVED")], 1),
        ("VOIDED", [(1, "VOIDED")], 0),
        ("APPROVED", [(1, "APPROVED")], 1),
    ]

    with pytest.raises(Problem) as excinfo:
        bulk_approve(ctx, [], comment=None, clock=clock, keyring=keyring, files=files)
    assert (excinfo.value.slug, excinfo.value.status) == ("validation-failed", 422)
    assert [(error.field, error.rule_id) for error in excinfo.value.errors] == [
        ("items", "REQ-PLT-017")
    ]


def _lock_not_available(excinfo: pytest.ExceptionInfo[exc.DBAPIError]) -> bool:
    return getattr(excinfo.value.orig, "sqlstate", None) == "55P03"


def _pending_request(run: Run, world: World, membership_id: UUID, code: str) -> Mapping[str, Any]:
    with run(world.preparer) as uow:
        found = uow.session.execute(select(role.c.id, role.c.name).where(role.c.code == code)).one()
        request = users.request_role_assignment(
            uow,
            membership_id=membership_id,
            role_id=UUID(str(found.id)),
            role_code=code,
            role_name=str(found.name),
        )
        uow.commit()
    assert request["status"] == "PENDING"
    return request


@pytest.mark.control("CTL-034")
def test_ctl_034_concurrent_conflicting_approvals_serialised(
    world: World, run: Run, clock: FrozenClock
) -> None:
    with identity_session(request_id="tests-approval-member-m") as session:
        user_id = insert_app_user(session)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.tenant_id)
            .values(setup_completed_at=clock.now())
        )
        member_m = insert_active_membership(session, tenant_id=world.tenant_id, user_id=user_id)
    first = _pending_request(run, world, member_m, "revenue_accountant")
    second = _pending_request(run, world, member_m, "revenue_reviewer")

    # A holds its transaction open after the grant; B waits for M's membership and gives up.
    with run(world.approver_a) as uow_a:
        assert decide(uow_a, **_decision_args(first, "APPROVE", None))["status"] == "APPROVED"
        with run(world.approver_b) as uow_b:
            uow_b.session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            with pytest.raises(exc.DBAPIError) as excinfo:
                decide(uow_b, **_decision_args(second, "APPROVE", None))
            assert _lock_not_available(excinfo), excinfo.value
        uow_a.commit()
    assert _state(world.tenant_id, second["id"]) == ("PENDING", [(1, "ACTIVE")], 0)

    problem = _refused(run, world.approver_b, second)
    assert (problem.slug, problem.status) == ("sod-conflict", 409)
    assert [error.rule_id for error in problem.errors] == ["SoD-3"]
    assert _state(world.tenant_id, second["id"]) == ("PENDING", [(1, "ACTIVE")], 0)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        held = session.execute(
            select(role_assignment.c.id).where(
                role_assignment.c.membership_id == member_m, role_assignment.c.revoked_at.is_(None)
            )
        ).all()
        report = sod.conflict_report(session, as_of=clock.now())
    assert len(held) == 1
    assert [conflict for membership_id, conflict in report if membership_id == member_m] == []

    # A role change locks the membership of every holder of the role. The role is created by an
    # administrator of all entities: ``POST /roles`` asks for ``role.manage``, and the definition
    # of a role for every entity (04 T-PLT-10) — the world's people hold ``access.approve`` alone.
    administrator = replace(
        world.preparer,
        permissions=world.preparer.permissions | {roles.GRANT_PERMISSION},
        permission_scopes=MappingProxyType(
            {**world.preparer.permission_scopes, roles.GRANT_PERMISSION: "*"}
        ),
    )
    with run(administrator) as uow:
        custom = roles.create_role(
            uow,
            code="deal_desk_analyst",
            name="Deal desk analyst",
            description=None,
            permissions=["scenario.use"],
        )
        uow.commit()
    with tenant_session(_all_entities(world.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=member_m,
            role_code="deal_desk_analyst",
        )
        change = dict(
            session.execute(select(approval_request).where(approval_request.c.subject_id == custom))
            .mappings()
            .one()
        )
    with tenant_session(_all_entities(world.tenant_id)) as locker:
        locker.execute(
            select(tenant_membership.c.id)
            .where(tenant_membership.c.id == member_m)
            .with_for_update()
        ).all()
        with run(world.approver_b) as uow_b:
            uow_b.session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            with pytest.raises(exc.DBAPIError) as excinfo:
                decide(uow_b, **_decision_args(change, "APPROVE", None))
            assert _lock_not_available(excinfo), excinfo.value
    assert _state(world.tenant_id, change["id"]) == ("PENDING", [(1, "ACTIVE")], 0)


def _membership(principal: Principal) -> UUID:
    assert principal.membership_id is not None
    return principal.membership_id


def _delegate(
    session: Session, *, delegator: Principal, delegate: Principal, valid_from: datetime
) -> UUID:
    """A 30-day T-PLT-21 delegation of ``access.approve``."""
    values = approval_delegation_values(
        delegator.tenant_id,
        delegator_membership_id=_membership(delegator),
        delegate_membership_id=_membership(delegate),
        valid_from=valid_from,
        valid_to=valid_from + timedelta(days=30),
    )
    session.execute(insert(approval_delegation).values(**values))
    return UUID(str(values["id"]))


def _without_permissions(principal: Principal) -> Principal:
    """The person as a member WITHOUT A ROLE is signed in: no permission, no role and no
    entity — what ``effective_grants`` answers for a membership without an assignment. Until 04
    rev 1.319 this helper kept the entity scope of the person it emptied, a principal no
    request builds: the kernel then asked a delegate's entity scope, and it now asks what she
    reads (``engine.own_scope_covers``; item READ-SCOPE-BY-PERMISSION-1). The subject of this
    module is tenant-level, which asks nothing of either."""
    return replace(
        principal,
        roles=(),
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope=(),
        role_scopes=MappingProxyType({}),
    )


def test_delegation_on_behalf_of(
    world: World, probe: ProbeSubjects, run: Run, clock: FrozenClock
) -> None:
    request = _submit(run, world, probe)
    delegator = world.approver_b
    delegate = _without_permissions(world.approver_a)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=_membership(delegator),
            role_code="tenant_admin",
        )
        # An expired delegation grants nothing.
        _delegate(
            session,
            delegator=delegator,
            delegate=delegate,
            valid_from=clock.now() - timedelta(days=31),
        )
    problem = _refused(run, delegate, request)
    # Supervisor ruling R-41 (8) (04 §16.10 rev 1.104): without a permission of its own and
    # without a delegation in force the delegate cannot read the request, so the command answers
    # 404 as ``GET /approvals/{id}`` does — it was 403 ``forbidden``, which confirmed the id.
    assert (problem.slug, problem.status) == ("not-found", 404)
    assert _state(world.tenant_id, request["id"]) == ("PENDING", [(1, "ACTIVE")], 0)

    with tenant_session(_all_entities(world.tenant_id)) as session:
        delegation_id = _delegate(
            session,
            delegator=delegator,
            delegate=delegate,
            valid_from=clock.now() - timedelta(days=1),
        )
        _delegate(
            session,
            delegator=delegator,
            delegate=world.preparer,
            valid_from=clock.now() - timedelta(days=1),
        )
    assert _decide(run, delegate, request)["status"] == "APPROVED"
    with tenant_session(_all_entities(world.tenant_id)) as session:
        decision = session.execute(
            select(
                approval_decision.c.approver_id,
                approval_decision.c.delegation_id,
                approval_decision.c.on_behalf_of_id,
            ).where(approval_decision.c.approval_request_id == request["id"])
        ).one()
    assert tuple(decision) == (world.approver_a.id, delegation_id, delegator.id)

    # A delegate who prepared the item still cannot approve it (BR-PLT-07).
    second = _submit(run, world, probe)
    problem = _refused(run, _without_permissions(world.preparer), second)
    assert (problem.slug, problem.status) == ("self-approval", 403)
    assert _state(world.tenant_id, second["id"]) == ("PENDING", [(1, "ACTIVE")], 0)
