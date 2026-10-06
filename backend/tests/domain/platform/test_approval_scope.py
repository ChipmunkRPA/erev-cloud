"""Entity scope of approval requests in the engine and the queue (04 T-PLT-17 rev 1.104, T-PLT-18
``required_role_id``, §16.10 "Entity scope of a request"; dev-guide DG-KRN-APR-02, DG-KRN-APR-06,
DG-KRN-APR-07; 03 REQ-PLT-011, REQ-PLT-012, REQ-CLS-011; PRD BR-PLT-07; supervisor ruling R-25 on
the security review's findings SN-4, SC-5 and SC-N5, and R-41 on the lane's independent review).

Probe subjects bound to legal entities of one tenant exercise the rules every real subject gets
from the engine: a request freezes its entities; a decision needs ONE authority — the approver's
own grants or one delegation — that covers EVERY entity, and a delegation is taken only by an
approver who READS the subject in full in her own right (04 rev 1.319; until then: whose own
entity scope covered them too); a request is listed for a scope that covers at least one; a
step's role and the any-role quorum count a role only for the request's entities; a request
the caller cannot read answers 404 on every command, like an unknown id; and the entities are
read again at the decision. The people are real memberships with role assignments, and their
principals are built
from ``effective_grants`` as a request builds them, so the principal, a delegator's grants and the
notification recipients read the same rows. Each refusal stands beside the approver who
legitimately decides.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine
from erev_api.approvals.engine import (
    BulkApproveItem,
    ImpactPreview,
    bulk_approve,
    decide,
    submit,
    withdraw,
)
from erev_api.approvals.subjects import (
    ALL_ENTITIES,
    SubjectEntities,
    SubjectNotVisible,
    SubjectSpec,
    role_assignment_proposal,
)
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import effective_grants
from erev_api.auth.principal import Principal, RequestContext
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
    combination_group,
    fiscal_calendar,
    judgement_record,
    legal_entity,
    notification,
    role,
    role_assignment,
)
from erev_api.domain.platform import approval_queries
from erev_api.domain.policies import rule_sets
from erev_api.enums import (
    ApprovalSubjectType,
    AuditOutcome,
    PrincipalKind,
    RuleSetKind,
    TenantKind,
)
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork, unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import insert, select
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    approval_delegation_values,
    combination_group_values,
    fiscal_calendar_values,
    insert_active_membership,
    insert_app_user,
    insert_contract_rows,
    insert_role_assignment,
    judgement_record_values,
    legal_entity_values,
    publish_rule_set,
    revoke_role_assignments,
)
from support.subjects import ProbeSubjects, install

MFA_VERIFIED_AT = datetime(2026, 9, 12, 11, 58, tzinfo=UTC)
PERMISSION = "contract.approve"  # held by the Revenue Reviewer and the Controller role
READ = "contract.read"  # what reads the probe of several entities (``approvals.readers``)
ONE = ApprovalSubjectType.POLICY_OVERRIDE  # the probe of a subject bound to one entity
SEVERAL = ApprovalSubjectType.COMBINATION_GROUP  # the probe of a subject that names several
REOPEN = ApprovalSubjectType.PERIOD_REOPEN  # the subject whose step needs a Controller among two
REOPEN_PERMISSION = "period.reopen_approve"

Run = Callable[[Principal], AbstractContextManager[UnitOfWork]]
Grant = tuple[str, tuple[str, ...]]  # (role code, entity keys; () = all entities)


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    entities: Mapping[str, UUID]  # "A", "B", "C"
    people: Mapping[str, Principal]

    def scope(self, *keys: str) -> SubjectEntities:
        return SubjectEntities(frozenset(self.entities[key] for key in keys))


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


# Who holds what, for which entities. ``contract.approve`` comes with revenue_reviewer and
# controller; viewer and revenue_accountant carry no approval permission.
PEOPLE: Mapping[str, Sequence[Grant]] = {
    "preparer": (("revenue_accountant", ()),),
    "rev_a": (("revenue_reviewer", ("A",)),),
    "rev_b": (("revenue_reviewer", ("B",)),),
    "rev_c": (("revenue_reviewer", ("C",)),),
    "rev_ab": (("revenue_reviewer", ("A", "B")),),
    "rev_all": (("revenue_reviewer", ()),),
    # contract.approve for B only, and a read-only role on A: A is in the union entity scope (RLS
    # shows a request of A) although the approval permission does not cover it.
    "rev_b_viewer_a": (("revenue_reviewer", ("B",)), ("viewer", ("A",))),
    "viewer_a": (("viewer", ("A",)),),
    "delegate": (("viewer", ()),),  # holds no approval permission of its own
    "delegate_b": (("revenue_reviewer", ("B",)),),
    # A delegate who reads entity A only: a delegation conveys the permission, not the view.
    "delegate_a": (("viewer", ("A",)),),
    # Controllers: of A; of B only, while approving for A as a Revenue Reviewer (SC-N5).
    "ctl_a": (("controller", ("A",)),),
    "rev_a_ctl_b": (("revenue_reviewer", ("A",)), ("controller", ("B",))),
    "rev_a_too": (("revenue_reviewer", ("A",)),),
    # Access approvers (tenant_admin carries access.approve): for entity A only, and for all.
    "adm_a": (("tenant_admin", ("A",)),),
    "adm_all": (("tenant_admin", ()),),
}


@pytest.fixture
def world(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> World:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    with identity_session(request_id="tests-approval-scope-users") as session:
        users = {name: insert_app_user(session) for name in PEOPLE}
    people: dict[str, Principal] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        calendar = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        entities: dict[str, UUID] = {}
        for key in ("A", "B", "C"):
            row = legal_entity_values(tenant_id, calendar_id=calendar["id"], code=f"ENT-{key}")
            session.execute(insert(legal_entity).values(**row))
            entities[key] = UUID(str(row["id"]))
        memberships = {
            name: insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)
            for name, user_id in users.items()
        }
        for name, grants in PEOPLE.items():
            for role_code, keys in grants:
                insert_role_assignment(
                    session,
                    tenant_id=tenant_id,
                    membership_id=memberships[name],
                    role_code=role_code,
                    entity_ids=[entities[key] for key in keys],
                )
        for name, user_id in users.items():
            people[name] = _principal(session, tenant_id, user_id, memberships[name], clock.now())
    return World(tenant_id=tenant_id, entities=entities, people=people)


def _principal(
    session: Session, tenant_id: UUID, user_id: UUID, membership_id: UUID, at: datetime
) -> Principal:
    """The signed-in, MFA-verified person as ``auth.dependencies`` builds it from the grants."""
    grants = effective_grants(session, membership_id, at=at)
    return Principal(
        kind=PrincipalKind.USER,
        id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
        display_name="Probe person",
        roles=grants.roles,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope=grants.entity_scope,
        auth_method="password",
        mfa_verified_at=MFA_VERIFIED_AT,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
        role_scopes=grants.role_scopes,
    )


def _context(principal: Principal, clock: FrozenClock) -> RequestContext:
    return RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-approval-scope",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def run(clock: FrozenClock, keyring: KeyRing, files: LocalFileStore) -> Run:
    @contextmanager
    def open_uow(principal: Principal) -> Iterator[UnitOfWork]:
        with unit_of_work(
            _context(principal, clock), clock=clock, keyring=keyring, files=files
        ) as uow:
            yield uow

    return open_uow


@dataclass
class Probe:
    """Probe subjects whose entities a test states per subject id."""

    subjects: ProbeSubjects
    bound: dict[UUID, SubjectEntities]
    unreadable: set[UUID]
    hashed: list[UUID]  # one entry per content read: a refusal "before the hash" adds none

    def new(self, entities: SubjectEntities) -> UUID:
        subject_id = self.subjects.new_subject()
        self.bound[subject_id] = entities
        return subject_id


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> Probe:
    found = Probe(subjects=ProbeSubjects(), bound={}, unreadable=set(), hashed=[])

    def content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
        found.hashed.append(subject_id)
        if subject_id in found.unreadable:
            raise SubjectNotVisible(f"probe subject {subject_id} is not visible")
        return dict(found.subjects.contents[subject_id])

    def one_entity(_: Session, subject_id: UUID) -> UUID | None:
        (entity_id,) = found.bound[subject_id].ids
        return entity_id

    base = found.subjects.spec(ONE, required_permission=PERMISSION)
    install(monkeypatch, replace(base, content=content, entity_id=one_entity))
    install(
        monkeypatch,
        replace(
            base,
            subject_type=SEVERAL,
            content=content,
            entities=lambda _session, subject_id: found.bound[subject_id],
        ),
    )
    install(
        monkeypatch,
        replace(
            found.subjects.spec(REOPEN, required_permission=REOPEN_PERMISSION, min_approvers=2),
            content=content,
            entity_id=one_entity,
        ),
    )
    return found


def _submit(
    run: Run,
    world: World,
    probe: Probe,
    subject_type: ApprovalSubjectType,
    entities: SubjectEntities,
) -> Mapping[str, Any]:
    with run(world.people["preparer"]) as uow:
        request = submit(
            uow,
            subject_type=subject_type,
            subject_id=probe.new(entities),
            summary=f"Probe request of {subject_type.value}",
        )
        uow.commit()
    return request


def _args(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "approval_request_id": request["id"],
        "decision": "APPROVE",
        "subject_content_sha256": request["subject_content_sha256"],
        "impact_preview_sha256": request["impact_preview_sha256"],
        "comment": None,
        "reason_code": None,
    }


def _decide(run: Run, principal: Principal, request: Mapping[str, Any]) -> Mapping[str, Any]:
    with run(principal) as uow:
        row = decide(uow, **_args(request))
        uow.commit()
    return row


def _refused(run: Run, principal: Principal, request: Mapping[str, Any]) -> Problem:
    with run(principal) as uow, pytest.raises(Problem) as excinfo:
        decide(uow, **_args(request))
    return excinfo.value


def _status(world: World, request_id: UUID) -> tuple[str, int]:
    """The request's status and the number of its decisions, read as the system."""
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        status = session.execute(
            select(approval_request.c.status).where(approval_request.c.id == request_id)
        ).scalar_one()
        decisions = session.execute(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == request_id
            )
        ).all()
    return str(status), len(decisions)


def _stored_scope(world: World, request_id: UUID) -> tuple[UUID | None, list[UUID], bool]:
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        row = session.execute(
            select(
                approval_request.c.entity_id,
                approval_request.c.entity_ids,
                approval_request.c.is_all_entities,
            ).where(approval_request.c.id == request_id)
        ).one()
    return row.entity_id, list(row.entity_ids), bool(row.is_all_entities)


def _can_decide(
    world: World, clock: FrozenClock, principal: Principal, request_id: UUID
) -> bool | None:
    """``can_decide`` as the queue computes it; None when the principal's session cannot read the
    request row at all (row-level security)."""
    with tenant_session(principal.db_context, read_only=True) as session:
        row = (
            session.execute(select(approval_request).where(approval_request.c.id == request_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return engine.can_decide(session, principal, dict(row), at=clock.now())


def _listed(clock: FrozenClock, principal: Principal, *, assigned: bool = False) -> set[UUID]:
    """The ids ``GET /approvals`` selects for the principal: the queue's own clause in the
    principal's session. With ``assigned`` the "Waiting for me" set (``assigned_to_me=true``), which
    the inbox list, its total and the home count read (``approval_queries.decidable``; R-64 (4))
    — always a subset of what the principal lists."""
    with tenant_session(principal.db_context, read_only=True) as session:
        authorities = approval_queries.decision_authorities(session, principal, at=clock.now())
        visible = {
            UUID(str(value))
            for value in session.scalars(
                select(approval_request.c.id).where(
                    approval_queries.visible(principal, authorities)
                )
            )
        }
        if not assigned:
            return visible
        waiting = {
            UUID(str(row["id"]))
            for row in approval_queries.decidable(session, principal, authorities, at=clock.now())
        }
        assert waiting <= visible
        return waiting


def _read(
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    principal: Principal,
    request_id: UUID,
) -> dict[str, Any] | Problem:
    """``GET /approvals/{id}`` in the domain: API-S-Approval, or the problem it answers."""
    try:
        return approval_queries.get_approval(
            _context(principal, clock), request_id, files=files, keyring=keyring
        )
    except Problem as problem:
        return problem


def _delegate(world: World, clock: FrozenClock, delegator: str, delegate: str) -> UUID:
    """A delegation of ``contract.approve`` in force now (T-PLT-21)."""
    values = approval_delegation_values(
        world.tenant_id,
        delegator_membership_id=_membership(world.people[delegator]),
        delegate_membership_id=_membership(world.people[delegate]),
        valid_from=clock.now() - timedelta(days=1),
        valid_to=clock.now() + timedelta(days=29),
    )
    values["permissions"] = [PERMISSION]
    with tenant_session(_all_entities(world.tenant_id)) as session:
        session.execute(insert(approval_delegation).values(**values))
    return UUID(str(values["id"]))


def _membership(principal: Principal) -> UUID:
    assert principal.membership_id is not None
    return principal.membership_id


def _not_found(problem: Problem) -> bool:
    return (problem.slug, problem.status) == ("not-found", 404)


# --- one entity --------------------------------------------------------------------------------


def test_request_of_one_entity_needs_the_permission_for_that_entity(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """SN-4 / SC-5: a request of entity A is decided with ``contract.approve`` for A. The approver
    for B — without a role on A, or with a read-only role on A — neither reads, lists nor decides
    it: 404 like an unknown id, nothing written. The approver for A decides it."""
    people, a = world.people, world.entities["A"]
    request = _submit(run, world, probe, ONE, world.scope("A"))
    request_id = request["id"]
    assert _stored_scope(world, request_id) == (a, [], False)

    # No role on A: row-level security hides the row (RLS-TE on entity_id).
    assert _can_decide(world, clock, people["rev_b"], request_id) is None
    # A read-only role on A: the row is readable, the approval permission does not cover A.
    assert _can_decide(world, clock, people["rev_b_viewer_a"], request_id) is False
    for name in ("rev_b", "rev_b_viewer_a", "viewer_a"):
        shown = _read(clock, keyring, files, people[name], request_id)
        assert isinstance(shown, Problem) and _not_found(shown), (name, shown)
        assert request_id not in _listed(clock, people[name]), name
        assert request_id not in _listed(clock, people[name], assigned=True), name
    # None of them reads the request, so no command confirms its id either (R-41 (8)): 404 on
    # approve as on the read — for the reader of A without any approval permission too.
    for name in ("rev_b", "rev_b_viewer_a", "viewer_a"):
        assert _not_found(_refused(run, people[name], request)), name
        with run(people[name]) as uow, pytest.raises(Problem) as excinfo:
            withdraw(uow, approval_request_id=request_id, comment=None)
        assert _not_found(excinfo.value), name
    assert _status(world, request_id) == ("PENDING", 0)
    assert probe.subjects.calls == []

    # Positive control: the approver for A reads, lists and decides it.
    shown = _read(clock, keyring, files, people["rev_a"], request_id)
    assert isinstance(shown, dict) and shown["can_decide"] is True
    assert shown["entity"] is not None and shown["entity"]["id"] == a
    assert request_id in _listed(clock, people["rev_a"], assigned=True)
    assert _decide(run, people["rev_a"], request)["status"] == "APPROVED"
    assert probe.subjects.calls == [("approved", request["subject_id"], request_id)]


# --- several entities --------------------------------------------------------------------------


def test_request_of_several_entities_needs_one_authority_for_all_of_them(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """R-25: a request of entities A and B is listed for a scope that covers one of them and
    decided only by ONE authority that covers both; scopes are never added up."""
    people = world.people
    a, b = world.entities["A"], world.entities["B"]
    request = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    request_id = request["id"]
    assert _stored_scope(world, request_id) == (None, sorted([a, b]), False)
    # R-41 (8): the audit event of the submission states the entity set the request froze.
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        (submitted,) = session.execute(
            select(audit_event.c.after).where(
                audit_event.c.action == "approval_request.submit",
                audit_event.c.object_id == request_id,
            )
        ).all()
    assert submitted.after["entities"] == {
        "entity_ids": sorted([str(a), str(b)]),
        "all_entities": False,
    }

    # An approver for A alone reads and lists the request and cannot decide it: 403, because the
    # read answers it — with the entity of its own scope and the count of the ones it names.
    shown = _read(clock, keyring, files, people["rev_a"], request_id)
    assert isinstance(shown, dict) and shown["can_decide"] is False
    assert shown["entity"] is None  # no single entity to show
    assert [ref["id"] for ref in shown["entities"]] == [a]
    assert (shown["entity_count"], shown["all_entities"]) == (2, False)
    assert request_id in _listed(clock, people["rev_a"])
    assert request_id not in _listed(clock, people["rev_a"], assigned=True)
    partial = _refused(run, people["rev_a"], request)
    assert (partial.slug, partial.status) == ("forbidden", 403)
    assert partial.detail == engine.EVERY_ENTITY_DETAIL

    # An approver for C: none of the request's entities is in its entity scope.
    outside = _read(clock, keyring, files, people["rev_c"], request_id)
    assert isinstance(outside, Problem) and _not_found(outside)
    assert request_id not in _listed(clock, people["rev_c"])
    assert _not_found(_refused(run, people["rev_c"], request))

    # A delegation from the approver for A to a delegate who holds the permission for B: the two
    # scopes cover A and B together, no ONE authority does.
    _delegate(world, clock, "rev_a", "delegate_b")
    assert _can_decide(world, clock, people["delegate_b"], request_id) is False
    assert request_id in _listed(clock, people["delegate_b"])
    assert request_id not in _listed(clock, people["delegate_b"], assigned=True)
    summed = _refused(run, people["delegate_b"], request)
    assert (summed.slug, summed.detail) == ("forbidden", engine.EVERY_ENTITY_DETAIL)
    assert _status(world, request_id) == ("PENDING", 0)

    # Positive control: the approver for A and B decides it, and reads both entities.
    assert request_id in _listed(clock, people["rev_ab"], assigned=True)
    assert _can_decide(world, clock, people["rev_ab"], request_id) is True
    both = _read(clock, keyring, files, people["rev_ab"], request_id)
    assert isinstance(both, dict)
    assert sorted(ref["id"] for ref in both["entities"]) == sorted([a, b])
    assert [ref["code"] for ref in both["entities"]] == ["ENT-A", "ENT-B"]
    assert _decide(run, people["rev_ab"], request)["status"] == "APPROVED"

    # Positive control for a delegation: the delegator covers both entities, so the delegate
    # decides on the delegator's behalf.
    second = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    delegation_id = _delegate(world, clock, "rev_all", "delegate")
    assert second["id"] in _listed(clock, people["delegate"], assigned=True)
    assert _decide(run, people["delegate"], second)["status"] == "APPROVED"
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        decision = session.execute(
            select(
                approval_decision.c.approver_id,
                approval_decision.c.delegation_id,
                approval_decision.c.on_behalf_of_id,
            ).where(approval_decision.c.approval_request_id == second["id"])
        ).one()
    assert tuple(decision) == (people["delegate"].id, delegation_id, people["rev_all"].id)


def test_request_that_spans_every_entity_needs_the_permission_for_all_entities(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """R-25: a subject whose entities cannot be named (an import, a portfolio estimate) spans
    every entity. Only ``contract.approve`` for all entities lists and decides it — the approver for
    A and B does not, whatever entities exist."""
    people = world.people
    request = _submit(run, world, probe, SEVERAL, ALL_ENTITIES)
    request_id = request["id"]
    assert _stored_scope(world, request_id) == (None, [], True)
    for name in ("rev_a", "rev_ab"):
        shown = _read(clock, keyring, files, people[name], request_id)
        assert isinstance(shown, Problem) and _not_found(shown), name
        assert request_id not in _listed(clock, people[name]), name
        assert _not_found(_refused(run, people[name], request)), name
    assert _status(world, request_id) == ("PENDING", 0)
    # The preparer still reads the request it prepared.
    own = _read(clock, keyring, files, people["preparer"], request_id)
    assert isinstance(own, dict) and own["can_decide"] is False

    assert request_id in _listed(clock, people["rev_all"], assigned=True)
    assert _decide(run, people["rev_all"], request)["status"] == "APPROVED"


def test_tenant_level_request_is_decided_by_any_holder(
    world: World, probe: Probe, run: Run, clock: FrozenClock
) -> None:
    """A subject that belongs to no entity names none: every holder of the step permission lists
    and decides it, whatever its entity scope (04 §16.10 rev 1.104, last row)."""
    people = world.people
    request = _submit(run, world, probe, SEVERAL, SubjectEntities())
    assert _stored_scope(world, request["id"]) == (None, [], False)
    for name in ("rev_a", "rev_b", "rev_c", "rev_all"):
        assert request["id"] in _listed(clock, people[name], assigned=True), name
    assert request["id"] not in _listed(clock, people["viewer_a"])
    assert _decide(run, people["rev_c"], request)["status"] == "APPROVED"


def test_withdraw_and_bulk_approve_do_not_reveal_a_request_outside_the_scope(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """REQ-PLT-012: a request none of whose entities is in the caller's entity scope answers 404
    on withdraw and on bulk approval, where it also reports no status."""
    people = world.people
    request = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    with run(people["rev_c"]) as uow, pytest.raises(Problem) as excinfo:
        withdraw(uow, approval_request_id=request["id"], comment=None)
    assert _not_found(excinfo.value)
    item = BulkApproveItem(
        approval_request_id=request["id"],
        subject_content_sha256=request["subject_content_sha256"],
        impact_preview_sha256=request["impact_preview_sha256"],
    )
    (hidden,) = bulk_approve(
        _context(people["rev_c"], clock),
        [item],
        comment=None,
        clock=clock,
        keyring=keyring,
        files=files,
    )
    assert hidden.problem is not None and _not_found(hidden.problem)
    assert hidden.status is None
    assert _status(world, request["id"]) == ("PENDING", 0)

    # Within the scope the refusals keep their own answers: another member is not the preparer.
    with run(people["rev_ab"]) as uow, pytest.raises(Problem) as excinfo:
        withdraw(uow, approval_request_id=request["id"], comment=None)
    assert (excinfo.value.slug, excinfo.value.status) == ("forbidden", 403)
    # Positive controls: the covering approver's bulk item is decided; the preparer withdraws.
    (decided,) = bulk_approve(
        _context(people["rev_ab"], clock),
        [item],
        comment=None,
        clock=clock,
        keyring=keyring,
        files=files,
    )
    assert (decided.problem, decided.status) == (None, "APPROVED")
    second = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    with run(people["preparer"]) as uow:
        row = withdraw(uow, approval_request_id=second["id"], comment="Wrong contracts.")
        uow.commit()
    assert row["status"] == "WITHDRAWN"


def test_a_command_of_the_subject_tells_another_person_they_are_not_the_preparer(
    world: World, probe: Probe, run: Run
) -> None:
    """PRD SM-01; 04 §16.14 API-R-37 shapes: a withdraw route of a subject's own domain names the
    SUBJECT, has authorised its caller for it and found the pending request there, so anyone but
    the preparer is told exactly that — 403 — whether or not they could read the request
    (``engine.withdraw(through_subject=True)``). The approvals API names the REQUEST and keeps the
    404 of a request its caller cannot read (ruling R-41 (8)).

    Fail-first: at the merge of main 2cbd093d lane F-CLO-A's
    ``test_withdraw_returns_to_draft_and_discard_voids`` showed ``POST
    /manual-adjustments/{id}/withdraw`` answering 404 to a second preparer."""
    people = world.people
    request = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    # Outside the request's entities: unreadable by its id.
    with run(people["rev_c"]) as uow, pytest.raises(Problem) as excinfo:
        withdraw(uow, approval_request_id=request["id"], comment=None)
    assert _not_found(excinfo.value)
    # Through the subject's own command the same person is not the preparer, and is told so.
    with run(people["rev_c"]) as uow, pytest.raises(Problem) as excinfo:
        withdraw(uow, approval_request_id=request["id"], comment=None, through_subject=True)
    refusal = excinfo.value
    assert (refusal.slug, refusal.status, refusal.detail) == (
        "forbidden",
        403,
        engine.WITHDRAW_DETAIL,
    )
    assert _status(world, request["id"]) == ("PENDING", 0)
    # Positive control: the preparer withdraws through the subject's command.
    with run(people["preparer"]) as uow:
        row = withdraw(
            uow, approval_request_id=request["id"], comment="Wrong contracts.", through_subject=True
        )
        uow.commit()
    assert row["status"] == "WITHDRAWN"


def test_unreadable_subject_answers_not_found(world: World, probe: Probe, run: Run) -> None:
    """R-25: a content function that finds no subject row the approver may read answers 404, not an
    escaped error; nothing is decided or voided. The same request is decided once it is readable."""
    people = world.people
    request = _submit(run, world, probe, ONE, world.scope("A"))
    probe.unreadable.add(request["subject_id"])
    assert _not_found(_refused(run, people["rev_a"], request))
    assert _status(world, request["id"]) == ("PENDING", 0)
    probe.unreadable.clear()
    assert _decide(run, people["rev_a"], request)["status"] == "APPROVED"


def test_assigned_notification_goes_to_holders_who_cover_every_entity(
    world: World, probe: Probe, run: Run
) -> None:
    """NTF-01 (04 §16.10 rev 1.104): ``APPROVAL_ASSIGNED`` for a request of A and B reaches the
    holders of the step permission for both entities, not the holder for one of them."""
    people = world.people
    request = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        recipients = set(
            session.scalars(
                select(notification.c.recipient_membership_id).where(
                    notification.c.kind == "APPROVAL_ASSIGNED",
                    notification.c.subject_id == request["id"],
                )
            )
        )
    covering = {_membership(people[name]) for name in ("rev_ab", "rev_all")}
    partial = {_membership(people[name]) for name in ("rev_a", "rev_b", "rev_c", "rev_a_too")}
    assert covering <= recipients
    assert not recipients & partial


# --- roles on a step (SC-N5) -------------------------------------------------------------------


def _route(world: World, subject_type: ApprovalSubjectType, steps: list[dict[str, Any]]) -> None:
    with tenant_session(_all_entities(world.tenant_id)) as session:
        publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            rules=[
                {
                    "rule_key": f"PROBE-{subject_type.value}",
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": subject_type.value}
                    ],
                    "outputs": {"steps": steps},
                }
            ],
        )


@pytest.mark.control("CTL-005")
def test_step_role_is_met_only_by_an_assignment_for_the_requests_entity(
    world: World, probe: Probe, run: Run, clock: FrozenClock
) -> None:
    """SC-N5 (04 T-PLT-18 rev 1.104): a step that names the Controller role is decided by a
    Controller OF THE REQUEST'S ENTITY. A Revenue Reviewer for A who is a Controller for B holds
    the step permission for A and not the step's role: 403, nothing written."""
    people = world.people
    _route(
        world,
        ONE,
        [
            {
                "name": "Controller review",
                "permission": PERMISSION,
                "min_approvers": 1,
                "role": "controller",
            }
        ],
    )
    request = _submit(run, world, probe, ONE, world.scope("A"))
    assert _can_decide(world, clock, people["rev_a_ctl_b"], request["id"]) is False
    refused = _refused(run, people["rev_a_ctl_b"], request)
    assert (refused.slug, refused.status) == ("forbidden", 403)
    assert refused.detail == engine.ROLE_REQUIRED_DETAIL.format(role="Controller")
    # A Revenue Reviewer for A without the role at all is refused the same way.
    assert (_refused(run, people["rev_a"], request).slug) == "forbidden"
    assert _status(world, request["id"]) == ("PENDING", 0)
    # "Waiting for me" and NTF-01 follow ``can_decide`` (the second independent review): the step
    # waits for, and is announced to, the holders of its role for the entity — not to everyone
    # who holds its permission. Both still list the request they may read.
    notified = _notified(world, "APPROVAL_ASSIGNED", request["id"])
    for name in ("rev_a", "rev_a_ctl_b"):
        assert request["id"] in _listed(clock, people[name])
        assert request["id"] not in _listed(clock, people[name], assigned=True)
        assert _membership(people[name]) not in notified
    assert request["id"] in _listed(clock, people["ctl_a"], assigned=True)
    assert _membership(people["ctl_a"]) in notified

    assert _can_decide(world, clock, people["ctl_a"], request["id"]) is True
    assert _decide(run, people["ctl_a"], request)["status"] == "APPROVED"


@pytest.mark.control("CTL-018")
def test_any_role_quorum_counts_a_role_only_for_the_requests_entity(
    world: World, probe: Probe, run: Run
) -> None:
    """SC-N5 (REQ-CLS-011 rev 1.19): the two ``PERIOD_REOPEN`` approvers include a Controller of
    the period's entity. Two approvals for A, one of them by a Controller of B only, leave the
    request PENDING; a Controller of A completes it."""
    people = world.people
    request = _submit(run, world, probe, REOPEN, world.scope("A"))
    # Both hold period.reopen_approve for A through the Revenue Reviewer role.
    assert _decide(run, people["rev_a"], request)["status"] == "PENDING"
    assert _decide(run, people["rev_a_ctl_b"], request)["status"] == "PENDING"
    assert _status(world, request["id"]) == ("PENDING", 2)
    assert probe.subjects.calls == []

    assert _decide(run, people["ctl_a"], request)["status"] == "APPROVED"
    assert probe.subjects.calls == [("approved", request["subject_id"], request["id"])]


@pytest.mark.control("CTL-018")
def test_quorum_follows_the_subjects_own_step_behind_an_added_step(
    world: World, probe: Probe, run: Run
) -> None:
    """R-26 (c) (04 §16.10 rev 1.104): the ``PERIOD_REOPEN`` quorum belongs to the step that
    carries ``period.reopen_approve``, wherever a routing rule placed it. A rule that adds a
    judgement review BEFORE the reopen step does not move the Controller requirement onto that
    first step, and does not take it off the reopen step."""
    people = world.people
    _route(
        world,
        REOPEN,
        [
            {"name": "Judgement review", "permission": "judgement.review", "min_approvers": 1},
            {"name": "Reopen approval", "permission": REOPEN_PERMISSION, "min_approvers": 2},
        ],
    )
    request = _submit(run, world, probe, REOPEN, world.scope("A"))
    # Step 1 is the added step: one judgement reviewer of A completes it, no Controller asked.
    first = _decide(run, people["rev_a_too"], request)
    assert (first["status"], first["current_step_no"]) == ("PENDING", 2)
    # Step 2 is the subject's own: two approvers without a Controller of A leave it open.
    assert _decide(run, people["rev_a"], request)["status"] == "PENDING"
    assert _decide(run, people["rev_a_ctl_b"], request)["status"] == "PENDING"
    assert probe.subjects.calls == []
    assert _decide(run, people["ctl_a"], request)["status"] == "APPROVED"


@pytest.mark.control("CTL-018")
@pytest.mark.parametrize(
    "later_step",
    [
        {"name": "Judgement review", "permission": "judgement.review", "min_approvers": 1},
        {"name": "Second reopen approval", "permission": REOPEN_PERMISSION, "min_approvers": 1},
    ],
    ids=["a step after the own step", "the permission repeated on a later step"],
)
def test_quorum_stays_on_the_subjects_own_step_before_a_later_step(
    world: World, probe: Probe, run: Run, later_step: dict[str, Any]
) -> None:
    """R-26 (c) (04 §16.10 rev 1.104), the two placements the independent review named beside the
    step added before: the ``PERIOD_REOPEN`` quorum belongs to the FIRST step that carries
    ``period.reopen_approve``. A rule that adds a step after it — of another permission, or of the
    same permission again — neither moves the Controller requirement to that later step nor lets
    the own step complete without a Controller of the entity."""
    people = world.people
    _route(
        world,
        REOPEN,
        [
            {"name": "Reopen approval", "permission": REOPEN_PERMISSION, "min_approvers": 2},
            later_step,
        ],
    )
    request = _submit(run, world, probe, REOPEN, world.scope("A"))
    # Step 1 is the subject's own: two approvers without a Controller of A leave it open.
    first = _decide(run, people["rev_a"], request)
    second = _decide(run, people["rev_a_ctl_b"], request)
    assert [(row["status"], row["current_step_no"]) for row in (first, second)] == [
        ("PENDING", 1),
        ("PENDING", 1),
    ]
    completed = _decide(run, people["ctl_a"], request)
    assert (completed["status"], completed["current_step_no"]) == ("PENDING", 2)
    assert probe.subjects.calls == []
    # Step 2 is the added step: one holder of its permission for A completes it, no Controller.
    assert "controller" not in people["rev_a_too"].roles
    assert _decide(run, people["rev_a_too"], request)["status"] == "APPROVED"
    assert probe.subjects.calls == [("approved", request["subject_id"], request["id"])]


# --- excluded deciders through delegation ------------------------------------------------------


def test_excluded_decider_is_refused_through_a_delegate(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-PLT-011 "across ... delegation": a person the subject excludes — the runner of a journal
    run (BR-JE-01), the owner of a waived item — is refused when someone decides on their behalf,
    with the subject's own copy, exactly as in person."""
    people = world.people
    excluded = people["rev_all"]
    assert excluded.id is not None
    detail = "You calculated this probe, so another user must approve it."
    spec: SubjectSpec = engine.spec_for(ONE)
    install(
        monkeypatch,
        replace(
            spec,
            excluded_deciders=lambda _session, _subject_id: frozenset({excluded.id}),
            excluded_detail=detail,
        ),
    )
    _delegate(world, clock, "rev_all", "delegate")
    request = _submit(run, world, probe, ONE, world.scope("A"))
    in_person = _refused(run, excluded, request)
    assert (in_person.slug, in_person.status, in_person.detail) == ("self-approval", 403, detail)

    assert _can_decide(world, clock, people["delegate"], request["id"]) is False
    on_behalf = _refused(run, people["delegate"], request)
    assert (on_behalf.slug, on_behalf.status, on_behalf.detail) == ("self-approval", 403, detail)
    assert _status(world, request["id"]) == ("PENDING", 0)
    # "Waiting for me" is ``can_decide`` and the notifications follow it (R-64 (4), (5)): the
    # request is not waiting for the person its subject excludes, although that person holds the
    # step permission, nor for the delegate whose only delegator is that person — and neither is
    # told it was assigned. Both still list it; the approver who may decide finds it waiting.
    notified = _notified(world, "APPROVAL_ASSIGNED", request["id"])
    for someone in (excluded, people["delegate"]):
        assert request["id"] in _listed(clock, someone)
        assert request["id"] not in _listed(clock, someone, assigned=True)
        assert _membership(someone) not in notified
    assert request["id"] in _listed(clock, people["rev_a"], assigned=True)
    assert _membership(people["rev_a"]) in notified

    # Positive control: an approver for A who is not excluded and acts for nobody decides it.
    assert _decide(run, people["rev_a"], request)["status"] == "APPROVED"
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        assert engine.approvers_of(session, request["id"]) == frozenset({people["rev_a"].id})


# --- supervisor ruling R-41: the lane's independent review ---------------------------------------


def _notified(world: World, kind: str, subject_id: Any) -> set[UUID]:
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        return {
            UUID(str(value))
            for value in session.scalars(
                select(notification.c.recipient_membership_id).where(
                    notification.c.kind == kind, notification.c.subject_id == subject_id
                )
            )
        }


def test_delegate_decides_only_within_its_own_entity_scope(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """R-41 (1): a delegation conveys the permission, not the view. ``delegate_a`` reads entity A
    only and acts for ``rev_all``, who approves for every entity. A request of A and B is not
    listed for the delegate, not waiting for it and not notified to it; its Approve answers 404
    BEFORE the subject is hashed, so nothing is voided — the review's finding was a request voided
    STALE because the delegate's session could not see B's rows. A request of A alone is the
    delegate's to decide on the delegator's behalf.

    Since 04 rev 1.319 "its own entity scope" of this test's name is what the delegate READS —
    one permission that reads the subject, for every entity of it — where it was the union of
    the entities of its roles (item READ-SCOPE-BY-PERMISSION-1). For a Viewer of A the two are
    one, and every assertion stands; ``test_read_in_full.py`` holds the delegate whose roles
    name an entity she does not read."""
    people = world.people
    delegate = people["delegate_a"]
    delegation_id = _delegate(world, clock, "rev_all", "delegate_a")
    request = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    request_id = request["id"]
    assert _can_decide(world, clock, delegate, request_id) is False
    assert request_id not in _listed(clock, delegate)
    assert request_id not in _listed(clock, delegate, assigned=True)
    hidden = _read(clock, keyring, files, delegate, request_id)
    assert isinstance(hidden, Problem) and _not_found(hidden)
    hashed = list(probe.hashed)
    assert _not_found(_refused(run, delegate, request))
    assert probe.hashed == hashed  # refused before the content hash is recomputed
    assert _status(world, request_id) == ("PENDING", 0)
    assert _membership(delegate) not in _notified(world, "APPROVAL_ASSIGNED", request_id)
    # A request that spans every entity takes the delegate's own read for all entities too.
    everywhere = _submit(run, world, probe, SEVERAL, ALL_ENTITIES)
    assert everywhere["id"] not in _listed(clock, delegate)
    assert _not_found(_refused(run, delegate, everywhere))
    assert _status(world, everywhere["id"]) == ("PENDING", 0)
    # NTF-04: the void of the two-entity request is not told to the delegate either.
    with run(people["preparer"]) as uow:
        withdraw(uow, approval_request_id=request_id, comment="Wrong contracts.")
        uow.commit()
    voided = _notified(world, "APPROVAL_VOIDED", request["subject_id"])
    assert _membership(delegate) not in voided
    assert _membership(people["rev_all"]) in voided

    # Positive control: the request of A alone — listed, notified and decided on behalf.
    single = _submit(run, world, probe, ONE, world.scope("A"))
    assert single["id"] in _listed(clock, delegate, assigned=True)
    assert _can_decide(world, clock, delegate, single["id"]) is True
    assert _membership(delegate) in _notified(world, "APPROVAL_ASSIGNED", single["id"])
    assert _decide(run, delegate, single)["status"] == "APPROVED"
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        decision = session.execute(
            select(approval_decision.c.delegation_id, approval_decision.c.on_behalf_of_id).where(
                approval_decision.c.approval_request_id == single["id"]
            )
        ).one()
    assert tuple(decision) == (delegation_id, people["rev_all"].id)


def test_delegate_without_any_role_is_told_of_a_tenant_level_request(
    world: World, probe: Probe, run: Run, clock: FrozenClock
) -> None:
    """R-41 (1), the other direction (the second independent review): a tenant-level request names
    no entity, so every member's own scope covers it — a delegate without a single role
    assignment too. Such a delegate of an approver may decide it, finds it waiting and is told of
    it (NTF-01); a request of an entity it cannot read stays hidden from it."""
    nobody = _person(world, clock)
    assert nobody.entity_scope == () and not nobody.permissions
    values = approval_delegation_values(
        world.tenant_id,
        delegator_membership_id=_membership(world.people["rev_all"]),
        delegate_membership_id=_membership(nobody),
        valid_from=clock.now() - timedelta(days=1),
        valid_to=clock.now() + timedelta(days=29),
    )
    values["permissions"] = [PERMISSION]
    with tenant_session(_all_entities(world.tenant_id)) as session:
        session.execute(insert(approval_delegation).values(**values))

    tenant_level = _submit(run, world, probe, SEVERAL, SubjectEntities())
    assert _stored_scope(world, tenant_level["id"]) == (None, [], False)
    assert _can_decide(world, clock, nobody, tenant_level["id"]) is True
    assert tenant_level["id"] in _listed(clock, nobody, assigned=True)
    assert _membership(nobody) in _notified(world, "APPROVAL_ASSIGNED", tenant_level["id"])

    of_a = _submit(run, world, probe, ONE, world.scope("A"))
    assert of_a["id"] not in _listed(clock, nobody)
    assert _membership(nobody) not in _notified(world, "APPROVAL_ASSIGNED", of_a["id"])
    assert _not_found(_refused(run, nobody, of_a))

    decided = _decide(run, nobody, tenant_level)
    assert decided["status"] == "APPROVED"


def test_entities_are_read_again_at_the_decision(
    world: World, probe: Probe, run: Run, clock: FrozenClock
) -> None:
    """R-41 (2): the entities the request froze are compared with the entities the subject states
    at the decision; a difference voids the request as ``STALE_SUBJECT`` (REQ-PLT-014) although its
    content hash is unchanged — the re-scoped SSP book of the review. A request that spans every
    entity already takes the permission for all of them and is not voided when its subject can be
    named after all."""
    people = world.people
    a, b = world.entities["A"], world.entities["B"]
    moved = _submit(run, world, probe, ONE, world.scope("A"))
    probe.bound[moved["subject_id"]] = world.scope("B")  # re-scoped after submission
    stale = _refused(run, people["rev_all"], moved)
    assert (stale.slug, stale.status) == ("stale-approval", 409)
    assert _status(world, moved["id"]) == ("VOIDED", 0)
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        row = session.execute(
            select(approval_request.c.void_reason, approval_request.c.entity_id).where(
                approval_request.c.id == moved["id"]
            )
        ).one()
        (event,) = session.execute(
            select(audit_event.c.after).where(
                audit_event.c.action == "approval_request.void",
                audit_event.c.object_id == moved["id"],
            )
        ).all()
    assert (row.void_reason, row.entity_id) == ("STALE_SUBJECT", a)  # the frozen set stays
    assert event.after["entities"] == {"entity_ids": [str(b)], "all_entities": False}
    assert probe.subjects.calls == [("voided", moved["subject_id"], moved["id"])]

    # Grown: a subject of A that now also names B is stale for the approver of both.
    grown = _submit(run, world, probe, SEVERAL, world.scope("A"))
    probe.bound[grown["subject_id"]] = world.scope("A", "B")
    assert _refused(run, people["rev_ab"], grown).slug == "stale-approval"
    # Widened to the whole tenant: no entity named any more is a difference too.
    widened = _submit(run, world, probe, SEVERAL, world.scope("A"))
    probe.bound[widened["subject_id"]] = SubjectEntities()
    assert _refused(run, people["rev_all"], widened).slug == "stale-approval"

    # Positive controls: an unchanged subject is decided; a request of every entity stays
    # decidable when its entities can be named at the decision (nothing grew).
    same = _submit(run, world, probe, ONE, world.scope("A"))
    assert _decide(run, people["rev_a"], same)["status"] == "APPROVED"
    spanning = _submit(run, world, probe, SEVERAL, ALL_ENTITIES)
    probe.bound[spanning["subject_id"]] = world.scope("A", "B")
    assert _decide(run, people["rev_all"], spanning)["status"] == "APPROVED"
    del clock


def test_delegate_of_an_excluded_person_decides_for_another_delegator(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-41 (8): ``find_authority`` prefers an authority that is not barred. ``delegate`` acts for
    ``rev_all`` — whom the subject excludes — and for ``rev_a``. The older delegation (the excluded
    person's) no longer shadows the usable one: the delegate decides on ``rev_a``'s behalf. With
    the excluded person's delegation alone the refusal keeps its name."""
    people = world.people
    excluded = people["rev_all"]
    assert excluded.id is not None
    detail = "You calculated this probe, so another user must approve it."
    install(
        monkeypatch,
        replace(
            engine.spec_for(ONE),
            excluded_deciders=lambda _session, _subject_id: frozenset({excluded.id}),
            excluded_detail=detail,
        ),
    )
    _delegate(world, clock, "rev_all", "delegate")
    alone = _submit(run, world, probe, ONE, world.scope("A"))
    assert _can_decide(world, clock, people["delegate"], alone["id"]) is False
    barred = _refused(run, people["delegate"], alone)
    assert (barred.slug, barred.detail) == ("self-approval", detail)

    assert alone["id"] not in _listed(clock, people["delegate"], assigned=True)

    # A later delegation from an approver the subject does not exclude.
    clock.advance(timedelta(minutes=5))
    usable = _delegate(world, clock, "rev_a", "delegate")
    assert _can_decide(world, clock, people["delegate"], alone["id"]) is True
    # The waiting list and NTF-01 follow (R-64 (4), (5)): through the unbarred delegator the
    # request now waits for the delegate, and a request submitted from here on is announced to it.
    assert alone["id"] in _listed(clock, people["delegate"], assigned=True)
    assert _membership(people["delegate"]) not in _notified(world, "APPROVAL_ASSIGNED", alone["id"])
    announced = _submit(run, world, probe, ONE, world.scope("A"))
    assert _membership(people["delegate"]) in _notified(world, "APPROVAL_ASSIGNED", announced["id"])
    assert _decide(run, people["delegate"], alone)["status"] == "APPROVED"
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        decision = session.execute(
            select(approval_decision.c.delegation_id, approval_decision.c.on_behalf_of_id).where(
                approval_decision.c.approval_request_id == alone["id"]
            )
        ).one()
    assert tuple(decision) == (usable, people["rev_a"].id)


def test_commands_answer_not_found_exactly_where_the_read_does(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """R-41 (8); REQ-PLT-012: for every person and every shape of request, approve and withdraw
    answer 404 exactly when ``GET /approvals/{id}`` does — the engine's ``visible_to`` and the
    queue's ``visible`` are one rule — and a request listed as waiting is one ``can_decide``
    confirms."""
    people = world.people
    _delegate(world, clock, "rev_all", "delegate_a")
    _delegate(world, clock, "rev_a", "delegate_b")
    requests = [
        _submit(run, world, probe, ONE, world.scope("A")),
        _submit(run, world, probe, SEVERAL, world.scope("A", "B")),
        _submit(run, world, probe, SEVERAL, world.scope("B", "C")),
        _submit(run, world, probe, SEVERAL, ALL_ENTITIES),
        _submit(run, world, probe, SEVERAL, SubjectEntities()),
    ]
    seen = 0
    for name, person in people.items():
        listed = _listed(clock, person)
        waiting = _listed(clock, person, assigned=True)
        for request in requests:
            request_id = request["id"]
            readable = isinstance(_read(clock, keyring, files, person, request_id), dict)
            assert (request_id in listed) == readable, (name, request["summary"])
            seen += readable
            can_decide = _can_decide(world, clock, person, request_id)
            assert (request_id in waiting) == bool(can_decide), (name, request_id)
            if name == "preparer" or can_decide:
                continue  # their commands succeed: decided or withdrawn elsewhere
            refused = _refused(run, person, request)
            assert _not_found(refused) == (not readable), (name, refused.slug)
            with run(person) as uow, pytest.raises(Problem) as excinfo:
                withdraw(uow, approval_request_id=request_id, comment=None)
            assert _not_found(excinfo.value) == (not readable), (name, excinfo.value.slug)
            if readable:
                assert excinfo.value.slug == "forbidden" and refused.slug == "forbidden"
    assert seen > len(requests)  # the matrix holds readers and non-readers of every shape
    for request in requests:
        assert _status(world, request["id"]) == ("PENDING", 0)


# --- a real subject whose proposal names the entities ------------------------------------------


def _grant(run: Run, world: World, *, member: str, entities: tuple[str, ...]) -> Mapping[str, Any]:
    """A real ``ROLE_ASSIGNMENT`` request: the Viewer role for ``member`` on the entity keys (none:
    for all entities), prepared by the Revenue Accountant — the engine does not authorize the
    preparer, the subject command does."""
    membership_id = _membership(world.people[member])
    with run(world.people["preparer"]) as uow:
        role_id = UUID(
            str(uow.session.execute(select(role.c.id).where(role.c.code == "viewer")).scalar_one())
        )
        request = submit(
            uow,
            subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT,
            subject_id=new_id(),
            summary=f"Grant Viewer to {member}",
            impact_preview=engine.ImpactPreview(
                before={"membership_id": str(membership_id), "assignments": []},
                after=role_assignment_proposal(
                    membership_id=membership_id,
                    role_id=role_id,
                    role_code="viewer",
                    is_all_entities=not entities,
                    entity_ids=[world.entities[key] for key in entities],
                    sod_exception_id=None,
                ),
            ),
        )
        uow.commit()
    return request


def test_role_assignment_is_bound_to_the_entities_of_the_grant(
    world: World, run: Run, clock: FrozenClock
) -> None:
    """R-41 (4); 04 §16.10 rev 1.104 row ``ROLE_ASSIGNMENT``: a grant request is bound to the
    entities of the grant it proposes, read from its proposal — every entity for an all-entities
    grant. An access approver for entity A decides a grant for A. A grant for B is outside their
    scope, and so is an all-entities grant, which takes ``access.approve`` for every entity and is
    shown only to scope ``*``: both answer 404, like an unknown id, so an approver for one entity
    cannot hand out a role over another. The approver for all entities decides both. Before the
    ruling the request named no entity and the approver for A decided all three."""
    people = world.people
    a, b = world.entities["A"], world.entities["B"]
    adm_a, adm_all = people["adm_a"], people["adm_all"]
    for_a = _grant(run, world, member="rev_a", entities=("A",))
    for_b = _grant(run, world, member="rev_b", entities=("B",))
    for_all = _grant(run, world, member="rev_c", entities=())
    assert [request["status"] for request in (for_a, for_b, for_all)] == ["PENDING"] * 3
    assert _stored_scope(world, for_a["id"]) == (a, [], False)
    assert _stored_scope(world, for_b["id"]) == (b, [], False)
    assert _stored_scope(world, for_all["id"]) == (None, [], True)

    # The grant for B: row-level security hides the request from the approver for A.
    assert _can_decide(world, clock, adm_a, for_b["id"]) is None
    assert _not_found(_refused(run, adm_a, for_b))
    # The all-entities grant: no policy hides a row that names no single entity, and the engine
    # answers as for an unknown id — it is neither decidable nor listed for the approver of A.
    assert _can_decide(world, clock, adm_a, for_all["id"]) is False
    assert _not_found(_refused(run, adm_a, for_all))
    assert _listed(clock, adm_a) == {for_a["id"]}
    assert _listed(clock, adm_a, assigned=True) == {for_a["id"]}
    for request in (for_b, for_all):
        assert _status(world, request["id"]) == ("PENDING", 0)

    # The grant for A is theirs; the approver for every entity decides the other two.
    assert _can_decide(world, clock, adm_a, for_a["id"]) is True
    assert _decide(run, adm_a, for_a)["status"] == "APPROVED"
    assert _listed(clock, adm_all, assigned=True) == {for_b["id"], for_all["id"]}
    for request in (for_b, for_all):
        assert _can_decide(world, clock, adm_all, request["id"]) is True
        assert _decide(run, adm_all, request)["status"] == "APPROVED"
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        written = {
            UUID(str(row.id)): (bool(row.is_all_entities), [UUID(str(v)) for v in row.entity_ids])
            for row in session.execute(
                select(
                    role_assignment.c.id,
                    role_assignment.c.is_all_entities,
                    role_assignment.c.entity_ids,
                ).where(
                    role_assignment.c.id.in_(
                        [request["subject_id"] for request in (for_a, for_b, for_all)]
                    )
                )
            )
        }
    assert written == {
        for_a["subject_id"]: (False, [a]),
        for_b["subject_id"]: (False, [b]),
        for_all["subject_id"]: (True, []),
    }


def _person(world: World, clock: FrozenClock, *grants: tuple[str, Sequence[UUID]]) -> Principal:
    """A new member holding ``grants`` — (role code, entity ids; none: all entities)."""
    with identity_session(request_id="tests-approval-scope-person") as session:
        user_id = insert_app_user(session)
    with tenant_session(_all_entities(world.tenant_id)) as session:
        membership_id = insert_active_membership(
            session, tenant_id=world.tenant_id, user_id=user_id
        )
        for role_code, entity_ids in grants:
            insert_role_assignment(
                session,
                tenant_id=world.tenant_id,
                membership_id=membership_id,
                role_code=role_code,
                entity_ids=entity_ids,
            )
        return _principal(session, world.tenant_id, user_id, membership_id, clock.now())


def test_delegate_outside_an_entity_does_not_void_a_real_combination_request(
    world: World, run: Run, clock: FrozenClock
) -> None:
    """R-41 (1) on a REAL subject — the destructive case of the independent review, which the
    probe subjects cannot reach because their content ignores row-level security. A
    ``COMBINATION_GROUP`` over contracts of two entities hashes each member's state, read in the
    decider's session. ``outside`` reads the first entity only and is the delegate of ``holder``,
    who approves for every entity. Before the ruling the delegation made the request the
    delegate's to decide; its Approve recomputed the hash without the member it could not read,
    found it changed, and voided the request ``STALE_SUBJECT`` — the proposal was rejected by a
    person who could not see it. Now the delegate does not read the request at all: 404, nothing
    voided, the proposal still SUBMITTED. A delegate whose own scope covers both entities is
    shown the request and may decide it."""
    with tenant_session(_all_entities(world.tenant_id)) as session:
        first = insert_contract_rows(session, world.tenant_id, head_stream_version=1)
        second = insert_contract_rows(session, world.tenant_id, head_stream_version=1)
        # The rows as the combination commands leave them at the submission (04 T-CON-19 "The
        # `COMBINATION` topic", rev 1.283; item COMBINATION-PROPOSAL-RECORD-1): the group
        # SUBMITTED and naming its proposal, the SUBMITTED record of action JOIN. Before the
        # item: a PROPOSED group that named no record and a record of action "COMBINE".
        group = combination_group_values(
            world.tenant_id, is_singleton=False, status="SUBMITTED", criterion="25_9_A"
        )
        record = judgement_record_values(
            world.tenant_id,
            topic="COMBINATION",
            subject_type="combination_group",
            subject_id=group["id"],
            status="SUBMITTED",
            questionnaire={
                "action": "JOIN",
                "contract_ids": [str(first.contract_id), str(second.contract_id)],
            },
        )
        session.execute(insert(judgement_record).values(**record))
        session.execute(insert(combination_group).values(**group, judgement_record_id=record["id"]))
    assert first.entity_id != second.entity_id
    holder = _person(world, clock, ("revenue_reviewer", ()))
    outside = _person(world, clock, ("viewer", [first.entity_id]))
    inside = _person(world, clock, ("viewer", [first.entity_id, second.entity_id]))
    for delegate in (outside, inside):
        values = approval_delegation_values(
            world.tenant_id,
            delegator_membership_id=_membership(holder),
            delegate_membership_id=_membership(delegate),
            valid_from=clock.now() - timedelta(days=1),
            valid_to=clock.now() + timedelta(days=29),
        )
        values["permissions"] = [PERMISSION]
        with tenant_session(_all_entities(world.tenant_id)) as session:
            session.execute(insert(approval_delegation).values(**values))

    with run(world.people["preparer"]) as uow:
        request = submit(
            uow,
            subject_type=ApprovalSubjectType.COMBINATION_GROUP,
            subject_id=group["id"],
            summary="Combine two contracts of two entities",
        )
        uow.commit()
    request_id = request["id"]
    assert request["status"] == "PENDING"
    assert _stored_scope(world, request_id) == (
        None,
        sorted([first.entity_id, second.entity_id]),
        False,
    )

    assert _can_decide(world, clock, outside, request_id) is False
    assert request_id not in _listed(clock, outside)
    assert _not_found(_refused(run, outside, request))
    assert _status(world, request_id) == ("PENDING", 0)
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        states = session.execute(
            select(combination_group.c.status, judgement_record.c.status)
            .select_from(combination_group)
            .join(judgement_record, judgement_record.c.subject_id == combination_group.c.id)
            .where(combination_group.c.id == group["id"])
        ).one()
        voids = session.execute(
            select(audit_event.c.id).where(
                audit_event.c.action == "approval_request.void",
                audit_event.c.object_id == request_id,
            )
        ).all()
    # the group and its proposal are as the submission left them: a void would reject both
    assert (tuple(str(value) for value in states), voids) == (("SUBMITTED", "SUBMITTED"), [])

    # Positive control: the delegate who reads both entities is shown the request, and it waits
    # for that delegate and for the holder in person.
    assert _can_decide(world, clock, inside, request_id) is True
    assert request_id in _listed(clock, inside, assigned=True)
    assert _can_decide(world, clock, holder, request_id) is True


# --- content is reader-independent (R-64 (1), R-70 (b)) ----------------------------------------


def _entities_read(session: Session) -> int:
    """The legal entities the session reads: every one of the tenant under its SYSTEM scope,
    fewer under a member's entity scope (T-REF-01 is RLS-TE)."""
    return len(session.scalars(select(legal_entity.c.id)).all())


def test_content_is_read_under_the_tenants_system_scope(
    world: World, probe: Probe, run: Run, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor rulings R-64 (1) and R-70 (b): what a request hashes and what its hook reads
    never depend on the entity scope of whoever prepares or decides. The probe's content does
    what a real content function does — it reads rows that row-level security scopes by entity,
    here the legal entities themselves, of which the request is bound to A alone (as a contract's
    lines posted under a performing entity are not part of the bound set). A decider for A reads
    one entity in their own session and three are hashed; a preparer for A alone stores the same
    hash as one who reads everything; the hook sees the tenant's rows; and the caller's scope is
    given back afterwards. Before the ruling the hash was the reader's: the narrow decider
    recomputed another one and voided the request as stale, every time, and so did a wide decider
    of a narrow preparer's request. A real change still voids."""
    people = world.people
    seen: list[int] = []

    def content(session: Session, subject_id: UUID) -> Mapping[str, Any]:
        return {**probe.subjects.contents[subject_id], "entities_read": _entities_read(session)}

    def approved(uow: UnitOfWork, _subject_id: UUID, _request_id: UUID) -> None:
        seen.append(_entities_read(uow.session))

    install(monkeypatch, replace(engine.spec_for(ONE), content=content, on_approved=approved))
    everything = sha256_hex({"name": "Probe subject", "entities_read": 3})

    # A preparer who reads every entity, a decider who reads A alone.
    request = _submit(run, world, probe, ONE, world.scope("A"))
    assert request["subject_content_sha256"] == everything
    with run(people["rev_a"]) as uow:
        assert _entities_read(uow.session) == 1
        row = decide(uow, **_args(request))
        assert _entities_read(uow.session) == 1  # the decider's own scope again
        uow.commit()
    assert (row["status"], seen) == ("APPROVED", [3])

    # The mirror: a preparer who reads A alone, a decider who reads every entity.
    narrow = _person(world, clock, ("revenue_accountant", [world.entities["A"]]))
    with run(narrow) as uow:
        assert _entities_read(uow.session) == 1
        mirrored = submit(
            uow,
            subject_type=ONE,
            subject_id=probe.new(world.scope("A")),
            summary="Probe request of a preparer for entity A",
        )
        assert _entities_read(uow.session) == 1  # the preparer's own scope again
        uow.commit()
    assert mirrored["subject_content_sha256"] == everything
    assert _decide(run, people["rev_all"], mirrored)["status"] == "APPROVED"
    assert seen == [3, 3]
    for decided in (request, mirrored):
        assert _status(world, decided["id"]) == ("APPROVED", 1)

    # Positive control: content that did change voids the request, whoever decides.
    third = _submit(run, world, probe, ONE, world.scope("A"))
    with tenant_session(_all_entities(world.tenant_id)) as session:
        calendar = fiscal_calendar_values(world.tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        session.execute(
            insert(legal_entity).values(
                **legal_entity_values(world.tenant_id, calendar_id=calendar["id"], code="ENT-D")
            )
        )
    stale = _refused(run, people["rev_a"], third)
    assert (stale.slug, stale.status) == ("stale-approval", 409)
    assert _status(world, third["id"]) == ("VOIDED", 0)
    assert seen == [3, 3]


def test_excluded_deciders_are_read_under_the_tenants_system_scope(
    world: World, probe: Probe, run: Run, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-64 (1) for the deciders a subject excludes: who is excluded is a fact of the subject,
    never of the entity scope of whoever asks. The probe names its author only where the row
    that carries the author is readable — a row of entity B, while the request is bound to A.
    The author approves for A and cannot read B: before the ruling the exclusion read nothing in
    the author's own session and the author decided their own item; now the author is refused
    like any excluded decider, is not told the request waits, and a colleague decides."""
    people = world.people
    author = people["rev_a"]
    assert author.id is not None
    entity_b = world.entities["B"]

    def excluded(session: Session, _subject_id: UUID) -> frozenset[UUID]:
        readable = session.scalars(select(legal_entity.c.id).where(legal_entity.c.id == entity_b))
        return frozenset({author.id}) if readable.first() is not None else frozenset()

    install(monkeypatch, replace(engine.spec_for(ONE), excluded_deciders=excluded))
    request = _submit(run, world, probe, ONE, world.scope("A"))
    with tenant_session(author.db_context, read_only=True) as session:
        assert excluded(session, request["subject_id"]) == frozenset()  # the author's own view

    assert _can_decide(world, clock, author, request["id"]) is False
    assert request["id"] not in _listed(clock, author, assigned=True)
    assert _membership(author) not in _notified(world, "APPROVAL_ASSIGNED", request["id"])
    refused = _refused(run, author, request)
    assert (refused.slug, refused.status) == ("self-approval", 403)
    assert _status(world, request["id"]) == ("PENDING", 0)

    colleague = people["rev_a_too"]
    assert _can_decide(world, clock, colleague, request["id"]) is True
    assert _decide(run, colleague, request)["status"] == "APPROVED"


# --- submission (R-64 (6)) ---------------------------------------------------------------------


def test_preparer_outside_an_entity_of_the_subject_is_refused_at_submission(
    world: World, probe: Probe, run: Run, clock: FrozenClock
) -> None:
    """Supervisor ruling R-64 (6): a preparer whose own entity scope does not cover EVERY entity
    the subject names is refused at submission with one named 403 — for one entity and for
    several. Before the ruling a subject of one entity outside the scope failed the row-level
    security check of the insert (a bare 403), a subject that named an entity inside the scope
    beside one outside was submitted by a preparer who could not read all of what they asked
    others to approve, and only a subject wholly outside was refused by name. What the scope
    covers is submitted as before, a tenant-level subject too, and the preparer reads and
    withdraws their own request.

    Each refusal is on record (04 §16.10 rev 1.295; dev-guide DG-KRN-AUTH-05): one ``DENIED``
    audit event of the submission, which names the subject and no entity. Until that revision
    the refusal left no event."""
    a = world.entities["A"]
    scoped = _person(world, clock, ("revenue_accountant", [a]))
    outside = (
        (ONE, world.scope("B")),
        (SEVERAL, world.scope("A", "B")),
        (SEVERAL, world.scope("B", "C")),
        (SEVERAL, ALL_ENTITIES),
    )
    asked: list[tuple[ApprovalSubjectType, UUID]] = []
    for subject_type, entities in outside:
        asked.append((subject_type, probe.new(entities)))
        with run(scoped) as uow, pytest.raises(Problem) as excinfo:
            submit(
                uow,
                subject_type=subject_type,
                subject_id=asked[-1][1],
                summary="Probe request outside the preparer's scope",
            )
        refused = excinfo.value
        assert (refused.slug, refused.status) == ("forbidden", 403), entities
        assert refused.detail == engine.OUTSIDE_SCOPE_DETAIL, entities
    denied = (
        select(
            audit_event.c.action,
            audit_event.c.object_type,
            audit_event.c.object_id,
            audit_event.c.actor_id,
            audit_event.c.detail,
        )
        .where(audit_event.c.outcome == AuditOutcome.DENIED)
        .order_by(audit_event.c.chain_seq)
    )
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        probes = approval_request.c.subject_type.in_([ONE.value, SEVERAL.value])
        assert session.execute(select(approval_request.c.id).where(probes)).all() == []
        # one DENIED event per refused submission: the request that was not opened, the
        # subject, the closed reason — and no entity
        assert [tuple(row) for row in session.execute(denied)] == [
            (
                engine.SUBMIT_ACTION,
                engine.OBJECT_TYPE,
                None,
                scoped.id,
                {
                    "subject_type": subject_type.value,
                    "subject_id": str(subject_id),
                    "reason": engine.DENIED_PREPARER_SCOPE,
                    "permission": "",
                },
            )
            for subject_type, subject_id in asked
        ]

    # Positive controls.
    with run(scoped) as uow:
        own = submit(
            uow,
            subject_type=ONE,
            subject_id=probe.new(world.scope("A")),
            summary="Probe request of entity A",
        )
        tenant_level = submit(
            uow,
            subject_type=SEVERAL,
            subject_id=probe.new(SubjectEntities()),
            summary="Probe request of no entity",
        )
        uow.commit()
    assert (own["status"], tenant_level["status"]) == ("PENDING", "PENDING")
    assert _stored_scope(world, own["id"]) == (a, [], False)
    assert {own["id"], tenant_level["id"]} <= _listed(clock, scoped)
    with run(scoped) as uow:
        row = withdraw(uow, approval_request_id=own["id"], comment="Submitted too early.")
        uow.commit()
    assert row["status"] == "WITHDRAWN"
    # what the scope covers is refused nowhere: no further event
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        assert len(session.execute(denied).all()) == len(asked)


def test_a_preparer_is_held_to_the_entities_the_request_would_put_in_force(
    world: World, probe: Probe, run: Run, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-64 (6) where a subject states fewer entities for its preparer than its request names
    (``SubjectSpec.preparer_entities``; 04 §16.10 rev 1.104 part 9) — an import in quarantine
    mode, whose usable rows commit while its request names every entity any row names. A
    preparer who covers what the request would put in force submits a request bound to more:
    the request keeps every entity, so its decider needs them all, and the preparer reads and
    withdraws it. A preparer outside the entities it is held to is refused by name, and a subject
    that states none is held to the entities of its request as before.

    The statement fails closed (supervisor ruling R-106 (b)): only named entities — at least one,
    all among the request's — narrow the check. A statement that names an entity the request
    does not, every entity, or none beside a request that names entities, and any statement
    beside a request that spans every entity, hold the preparer to the request's entities and
    the stated ones together.

    Fail-first: without the seam the preparer of entity A is refused the request of A and B; a
    seam that took any statement as given would submit the five requests of the second block."""
    a, b = world.entities["A"], world.entities["B"]
    scoped = _person(world, clock, ("revenue_accountant", [a]))
    held: dict[UUID, SubjectEntities] = {}
    install(
        monkeypatch,
        replace(
            engine.spec_for(SEVERAL),
            preparer_entities=lambda _session, subject_id: held[subject_id],
        ),
    )

    both = world.scope("A", "B")
    closed = (
        (both, world.scope("B")),  # what it would put in force lies outside the preparer
        (both, world.scope("A", "C")),  # names an entity the request does not
        (both, SubjectEntities()),  # names none beside a request that names two
        (both, ALL_ENTITIES),  # unresolved
        (ALL_ENTITIES, world.scope("A")),  # a request that cannot name its entities
        (SubjectEntities(), world.scope("B")),  # a tenant-level request, a statement outside
    )
    for entities, stated in closed:
        refused_id = probe.new(entities)
        held[refused_id] = stated
        with run(scoped) as uow, pytest.raises(Problem) as excinfo:
            submit(uow, subject_type=SEVERAL, subject_id=refused_id, summary="Probe outside")
        refused = excinfo.value
        assert (refused.slug, refused.detail) == ("forbidden", engine.OUTSIDE_SCOPE_DETAIL), (
            entities,
            stated,
        )
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        probes = approval_request.c.subject_type == SEVERAL.value
        assert session.execute(select(approval_request.c.id).where(probes)).all() == []

    subject_id = probe.new(world.scope("A", "B"))
    held[subject_id] = world.scope("A")
    with run(scoped) as uow:
        request = submit(
            uow, subject_type=SEVERAL, subject_id=subject_id, summary="Probe A of A, B"
        )
        uow.commit()
    assert request["status"] == "PENDING"
    assert _stored_scope(world, request["id"]) == (None, sorted([a, b]), False)
    assert request["id"] in _listed(clock, scoped)
    # The request names both entities: an approver of A alone does not decide it.
    of_a = _person(world, clock, ("revenue_reviewer", [a]))
    of_both = _person(world, clock, ("revenue_reviewer", [a, b]))
    assert _can_decide(world, clock, of_a, request["id"]) is False
    assert _can_decide(world, clock, of_both, request["id"]) is True
    with run(scoped) as uow:
        row = withdraw(uow, approval_request_id=request["id"], comment="Submitted too early.")
        uow.commit()
    assert row["status"] == "WITHDRAWN"


# --- steps (R-66 (7)) --------------------------------------------------------------------------


def test_only_decider_of_a_later_step_is_kept_for_it(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """Supervisor ruling R-66 (7): a person who is the only eligible decider of a later step is
    refused an earlier step of the same request with a named 409. One decision per person per
    request — the only Controller of entity A, who also holds the first step's permission, would
    approve step 1 and leave step 2 without anyone to decide it; the request would stop there
    and only a withdrawal could end it. The Controller is refused in person, through a delegate
    who would decide on the Controller's behalf, on reject and in bulk; "Waiting for me" and
    ``can_decide`` say the same. A reviewer decides step 1 and the Controller step 2. With a
    second Controller nobody is kept back, and a later step that nobody at all can decide
    refuses nobody."""
    people = world.people
    controller = people["ctl_a"]
    _route(
        world,
        ONE,
        [
            {"name": "Review", "permission": PERMISSION, "min_approvers": 1},
            {
                "name": "Controller approval",
                "permission": PERMISSION,
                "min_approvers": 1,
                "role": "controller",
            },
        ],
    )
    request = _submit(run, world, probe, ONE, world.scope("A"))
    _delegate(world, clock, "ctl_a", "delegate_a")

    assert _can_decide(world, clock, controller, request["id"]) is False
    assert request["id"] in _listed(clock, controller)
    assert request["id"] not in _listed(clock, controller, assigned=True)
    for someone in (controller, people["delegate_a"]):
        refused = _refused(run, someone, request)
        assert (refused.slug, refused.status) == ("invalid-transition", 409)
        assert refused.detail == engine.SOLE_LATER_DECIDER_DETAIL
    with run(controller) as uow, pytest.raises(Problem) as excinfo:
        decide(uow, **{**_args(request), "decision": "REJECT", "comment": "Not like this."})
    assert excinfo.value.detail == engine.SOLE_LATER_DECIDER_DETAIL
    (item,) = bulk_approve(
        _context(controller, clock),
        [
            BulkApproveItem(
                approval_request_id=request["id"],
                subject_content_sha256=request["subject_content_sha256"],
                impact_preview_sha256=request["impact_preview_sha256"],
            )
        ],
        comment=None,
        clock=clock,
        keyring=keyring,
        files=files,
    )
    assert item.problem is not None and item.problem.slug == "invalid-transition"
    assert item.status == "PENDING"
    assert _status(world, request["id"]) == ("PENDING", 0)
    # NTF-01 follows: the first step is announced to the reviewers, not to the Controller nor to
    # the delegate who would decide on the Controller's behalf.
    reviewer = people["rev_a"]
    told = _notified(world, "APPROVAL_ASSIGNED", request["id"])
    assert _membership(reviewer) in told
    assert not told & {_membership(controller), _membership(people["delegate_a"])}

    # A reviewer decides the first step; the second is the Controller's, and is announced to them.
    assert _can_decide(world, clock, reviewer, request["id"]) is True
    assert request["id"] in _listed(clock, reviewer, assigned=True)
    assert _decide(run, reviewer, request)["status"] == "PENDING"
    assert _can_decide(world, clock, controller, request["id"]) is True
    assert request["id"] in _listed(clock, controller, assigned=True)
    assert _membership(controller) in _notified(world, "APPROVAL_ASSIGNED", request["id"])
    assert _decide(run, controller, request)["status"] == "APPROVED"

    # A later step nobody can decide is not the first decider's doing: entity C has no
    # Controller, so the reviewer of C decides step 1 and the request waits at step 2.
    stuck = _submit(run, world, probe, ONE, world.scope("C"))
    assert _can_decide(world, clock, people["rev_c"], stuck["id"]) is True
    assert _decide(run, people["rev_c"], stuck)["status"] == "PENDING"

    # Positive control: with a second Controller of the entity nobody is kept back.
    second = _person(world, clock, ("controller", [world.entities["A"]]))
    other = _submit(run, world, probe, ONE, world.scope("A"))
    assert _can_decide(world, clock, controller, other["id"]) is True
    assert other["id"] in _listed(clock, controller, assigned=True)
    assert _decide(run, controller, other)["status"] == "PENDING"
    assert _decide(run, second, other)["status"] == "APPROVED"


# --- evaluation equals submission (R-66 (8)) ---------------------------------------------------


def test_entity_code_condition_matches_at_submission_as_in_an_evaluation(
    world: World, probe: Probe, run: Run, clock: FrozenClock
) -> None:
    """Supervisor ruling R-66 (8): a submission states ``entity.code`` — the codes of the legal
    entities the request names — so a routing rule with an entity condition matches at
    submission exactly where it matches in the evaluation of a case. A rule that routes requests
    of ENT-B to two steps applies to a request of B, to one that names B among others and to one
    that spans every entity; not to a request of A alone, nor to a tenant-level one, which names
    no entity. Before the ruling a submission passed no entity: the rule matched every case of
    its rule set's tests and never a request."""
    two_steps = [
        {"name": "Review", "permission": PERMISSION, "min_approvers": 1},
        {"name": "Second review", "permission": PERMISSION, "min_approvers": 1},
    ]
    conditions = [
        {"field": "subject.type", "op": "in", "value": [ONE.value, SEVERAL.value]},
        {"field": "entity.code", "op": "eq", "value": "ENT-B"},
    ]
    rules = [{"rule_key": "ENTITY-B", "conditions": conditions, "outputs": {"steps": two_steps}}]
    with tenant_session(_all_entities(world.tenant_id)) as session:
        publish_rule_set(
            session, tenant_id=world.tenant_id, kind=RuleSetKind.APPROVAL_ROUTING, rules=rules
        )

    def steps(subject_type: ApprovalSubjectType, entities: SubjectEntities) -> int:
        request = _submit(run, world, probe, subject_type, entities)
        with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
            return len(
                session.scalars(
                    select(approval_step.c.id).where(
                        approval_step.c.approval_request_id == request["id"]
                    )
                ).all()
            )

    assert steps(ONE, world.scope("B")) == 2
    assert steps(SEVERAL, world.scope("A", "B")) == 2
    assert steps(SEVERAL, ALL_ENTITIES) == 2
    assert steps(ONE, world.scope("A")) == 1
    assert steps(SEVERAL, world.scope("A", "C")) == 1
    assert steps(SEVERAL, SubjectEntities()) == 1

    # The evaluation of the same cases: one function reads the rule on both paths.
    stored = [{"id": new_id(), "priority": 0, "specificity": 2, **rules[0]}]

    def evaluated(*codes: str) -> object:
        facts, errors = rule_sets.facts_of(
            RuleSetKind.APPROVAL_ROUTING,
            {"subject.type": ONE.value, "entity.code": list(codes)},
            where="input",
            rule_id="T-REF-27",
        )
        assert errors == []
        return rule_sets.evaluate(RuleSetKind.APPROVAL_ROUTING, stored, facts)["rule_key"]

    assert (evaluated("ENT-B"), evaluated("ENT-A", "ENT-B")) == ("ENTITY-B", "ENTITY-B")
    assert (evaluated("ENT-A"), evaluated()) == (None, None)


# --- content of a request (item APR-CONTENT-SCOPE-1; 04 §16.10 rev 1.208) ------------------------

AMOUNT = (Decimal("900.00"), "USD")
FLAG = "TP_CHANGE_GE_250K"
PREVIEW = ImpactPreview(
    before={"ssp_unit_rate": {"amount": "100.00", "currency": "USD"}},
    after={"ssp_unit_rate": {"amount": "1.00", "currency": "USD"}},
)
SEVERAL_LABEL = "Contract combination"  # SCREENS §15.3: the name of ``COMBINATION_GROUP``


def _with_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """The probe of several entities states an amount and a flag, as a real subject does."""
    install(
        monkeypatch,
        replace(
            engine.spec_for(SEVERAL),
            amount_functional=lambda _session, _subject_id: AMOUNT,
            flags=lambda _session, _subject_id: frozenset({FLAG}),
        ),
    )


def _content(shown: dict[str, Any] | Problem) -> dict[str, Any]:
    """The members of API-S-Approval that are content, as one reader is shown them."""
    assert isinstance(shown, dict), shown
    preview = shown["impact_preview"]
    amount = shown["amount"]
    return {
        "content_withheld": shown["content_withheld"],
        "summary": shown["summary"],
        "display": shown["subject"]["display"],
        "amount": None if amount is None else amount.model_dump(),
        "flags": shown["flags"],
        "preview": None if preview is None else preview["sha256"],
        "attachments": shown["attachments"],
        "comments": [
            decision["comment"] for step in shown["steps"] for decision in step["decisions"]
        ],
        # A decision's reason code is the decider's own text too (item
        # APR-DECISION-CODE-CONTENT-1): content, as its comment is.
        "codes": [
            decision["reason_code"] for step in shown["steps"] for decision in step["decisions"]
        ],
    }


def _whole(request: Mapping[str, Any], summary: str, *comments: str | None) -> dict[str, Any]:
    return {
        "content_withheld": False,
        "summary": summary,
        "display": summary,
        "amount": {"amount": "900.00", "currency": "USD"},
        "flags": [FLAG],
        "preview": request["impact_preview_sha256"],
        "attachments": [],
        "comments": list(comments),
        "codes": [None] * len(comments),
    }


def _header(request: Mapping[str, Any], decisions: int = 0) -> dict[str, Any]:
    withheld = f"{SEVERAL_LABEL} {request['request_no']}"
    return {
        "content_withheld": True,
        "summary": withheld,
        "display": withheld,
        "amount": None,
        "flags": [],
        "preview": None,
        "attachments": [],
        "comments": [None] * decisions,
        "codes": [None] * decisions,
    }


def _reads_content(clock: FrozenClock, principal: Principal) -> set[UUID]:
    """The ids whose content the principal reads: ``approval_queries.content_visible`` in the
    principal's session, as ``_listed`` reads ``visible``."""
    with tenant_session(principal.db_context, read_only=True) as session:
        authorities = approval_queries.decision_authorities(session, principal, at=clock.now())
        return {
            UUID(str(value))
            for value in session.scalars(
                select(approval_request.c.id).where(
                    approval_queries.content_visible(principal, authorities)
                )
            )
        }


def test_content_is_shown_to_who_covers_every_entity_and_to_nobody_else(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item APR-CONTENT-SCOPE-1 (release blocker; the supervisor's ruling of 2026-10-01 on the
    lane's finding that an approver for one entity of an import read the other entity's rows in
    its preview). A request is LISTED for a reader who covers one of its entities and its
    CONTENT is shown to a reader who covers every one: the summary, which names the record, the
    amount, the flags, the impact preview and what the deciders wrote.

    The rule is the listing rule with "every" for "at least one" — stricter than "listed, and
    the reader's own entity scope covers the request": ``rev_b_viewer_a`` reads both entities
    through a read-only role and approves for B alone, and a delegate who reads every entity
    acts for an approver of A alone; each is shown the header. The same delegate, once it also
    acts for an approver of A and B, is shown the content: ONE authority covers the request.
    A person who decided the request and no longer covers it is shown the header as anyone.

    Fail-first: with ``visible`` in place of ``content_visible`` every reader of the header
    blocks below reads the whole request."""
    people = world.people
    a, b = world.entities["A"], world.entities["B"]
    _with_content(monkeypatch)
    summary = "Combine 2 contracts in CG-000031"
    with run(people["preparer"]) as uow:
        request = submit(
            uow,
            subject_type=SEVERAL,
            subject_id=probe.new(world.scope("A", "B")),
            summary=summary,
            impact_preview=PREVIEW,
        )
        uow.commit()
    request_id = request["id"]

    def read(name: str) -> dict[str, Any]:
        shown = _read(clock, keyring, files, people[name], request_id)
        assert isinstance(shown, dict), name
        return shown

    # Positive controls: the preparer, who prepares for every entity, an approver for A and B,
    # an approver for all entities.
    for name in ("preparer", "rev_ab", "rev_all"):
        assert _content(read(name)) == _whole(request, summary), name

    # One entity of the two: the header, and in it nothing of the record.
    for name, codes in (
        ("rev_a", ["ENT-A"]),
        ("rev_b", ["ENT-B"]),
        ("rev_b_viewer_a", ["ENT-A", "ENT-B"]),
    ):
        shown = read(name)
        assert _content(shown) == _header(request), name
        assert (shown["id"], shown["request_no"], shown["status"], shown["can_decide"]) == (
            request_id,
            request["request_no"],
            "PENDING",
            False,
        ), name
        assert ([ref["code"] for ref in shown["entities"]], shown["entity_count"]) == (codes, 2)
        assert (shown["subject"]["type"], shown["subject"]["id"]) == (
            SEVERAL.value,
            request["subject_id"],
        )
        assert shown["subject"]["content_sha256"] == request["subject_content_sha256"]
        assert [
            (step["step_no"], step["required_permission"], step["status"])
            for step in shown["steps"]
        ] == [(1, PERMISSION, "ACTIVE")]
        assert shown["preparer"]["id"] == people["preparer"].id
        told = json.dumps(shown, default=str)
        for word in (summary, "CG-000031", "900.00", FLAG, str(request["impact_preview_sha256"])):
            assert word not in told, (name, word)
    # The approver for A alone is told nothing that names entity B.
    alone = json.dumps(read("rev_a"), default=str)
    assert "ENT-B" not in alone and str(b) not in alone
    assert str(a) in alone

    # A delegation conveys the permission, not the view (R-41 (1)) — and no more of the view
    # than the delegator has: the delegate of an approver for A is shown the header.
    _delegate(world, clock, "rev_a", "delegate")
    assert request_id in _listed(clock, people["delegate"])
    assert _content(read("delegate")) == _header(request)
    _delegate(world, clock, "rev_ab", "delegate")
    assert _content(read("delegate")) == _whole(request, summary)

    # What a decider wrote is content too.
    comment = "Both contracts are signed; ENT-B's is dated 2026-03-31."
    with run(people["rev_ab"]) as uow:
        decide(uow, **{**_args(request), "comment": comment})
        uow.commit()
    assert _content(read("rev_ab")) == _whole(request, summary, comment)
    assert _content(read("preparer")) == _whole(request, summary, comment)
    decided = read("rev_a")
    assert _content(decided) == _header(request, decisions=1)
    (step,) = decided["steps"]
    (decision,) = step["decisions"]
    assert (decided["status"], decision["decision"], decision["approver"]["id"]) == (
        "APPROVED",
        "APPROVE",
        people["rev_ab"].id,
    )

    # The scope in force at the read decides: a decider who loses entity B is shown the header.
    decider = _person(world, clock, ("revenue_reviewer", [a, b]))
    with run(people["preparer"]) as uow:
        second = submit(
            uow,
            subject_type=SEVERAL,
            subject_id=probe.new(world.scope("A", "B")),
            summary=summary,
            impact_preview=PREVIEW,
        )
        uow.commit()
    assert _decide(run, decider, second)["status"] == "APPROVED"
    assert _content(_read(clock, keyring, files, decider, second["id"])) == _whole(
        second, summary, None
    )
    with tenant_session(_all_entities(world.tenant_id)) as session:
        revoke_role_assignments(
            session,
            tenant_id=world.tenant_id,
            membership_id=_membership(decider),
            at=clock.now(),
        )
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=_membership(decider),
            role_code="revenue_reviewer",
            entity_ids=[a],
        )
        assert decider.id is not None
        narrowed = _principal(
            session, world.tenant_id, decider.id, _membership(decider), clock.now()
        )
    assert second["id"] in _listed(clock, narrowed)
    assert _content(_read(clock, keyring, files, narrowed, second["id"])) == _header(
        second, decisions=1
    )


def test_the_content_rule_is_the_listing_rule_but_for_a_request_of_several_entities(
    world: World, probe: Probe, run: Run, clock: FrozenClock
) -> None:
    """Item APR-CONTENT-SCOPE-1: ``content_visible`` over the four shapes of a request, for
    every person of the world. A tenant-level request and a request of one entity have no
    partial reader — whoever lists one is shown its content (row-level security hides a
    request of one entity from a reader outside it). A request that spans every entity is
    listed and shown only for a scope of all entities. A request of several entities is the
    one shape whose readers divide; the expected sets are computed from each person's grants,
    not from the statement under test."""
    people = world.people
    tenant_level = _submit(run, world, probe, SEVERAL, SubjectEntities())
    of_a = _submit(run, world, probe, ONE, world.scope("A"))
    of_b = _submit(run, world, probe, SEVERAL, world.scope("B"))
    everywhere = _submit(run, world, probe, SEVERAL, ALL_ENTITIES)
    both = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    undivided = {tenant_level["id"], of_a["id"], of_b["id"], everywhere["id"]}
    listed = {name: _listed(clock, principal) for name, principal in people.items()}
    content = {name: _reads_content(clock, principal) for name, principal in people.items()}
    for name in people:
        assert content[name] <= listed[name], name
        assert content[name] & undivided == listed[name] & undivided, name

    def names(found: Mapping[str, set[UUID]], request: Mapping[str, Any]) -> set[str]:
        return {name for name, ids in found.items() if request["id"] in ids}

    def covers(scope: Any, entities: SubjectEntities) -> bool:
        return scope is not None and entities.covered_by("*" if scope == "*" else frozenset(scope))

    def touches(scope: Any, entities: SubjectEntities) -> bool:
        return scope is not None and (scope == "*" or entities.touched_by(frozenset(scope)))

    a_and_b = world.scope("A", "B")
    expected_listed = {
        name
        for name, principal in people.items()
        if touches(principal.entity_scope, a_and_b)
        and (name == "preparer" or touches(principal.permission_scopes.get(PERMISSION), a_and_b))
    }
    # 04 §16.10 rev 1.319 (item READ-SCOPE-BY-PERMISSION-1): the content is for who holds the
    # step's permission for every entity in her own right — she is asked nothing further — and
    # for a preparer who READS the subject in full: one permission that reads it, for every
    # entity (``contract.read`` reads the probe of several). Until that revision the oracle
    # asked ``entity_scope``, the union of the entities of her roles, of both; every person of
    # this world holds a default role with the three reads, so the two were one set and the
    # oracle could not disagree with the old rule.
    expected_content = {
        name
        for name, principal in people.items()
        if covers(principal.permission_scopes.get(PERMISSION), a_and_b)
        or (name == "preparer" and covers(principal.permission_scopes.get(READ), a_and_b))
    }
    assert names(listed, both) == expected_listed
    assert names(content, both) == expected_content
    # The sets by name, so that the oracle above cannot agree with the statement by accident.
    assert {"preparer", "rev_ab", "rev_all", "rev_a_ctl_b"} <= expected_content
    assert expected_content.isdisjoint(
        {"rev_a", "rev_b", "rev_c", "rev_b_viewer_a", "viewer_a", "delegate", "delegate_b"}
    )
    assert {"rev_a", "rev_b", "rev_b_viewer_a", "delegate_b"} <= expected_listed - expected_content
    assert names(content, everywhere) == names(listed, everywhere)
    assert {"preparer", "rev_all"} <= names(content, everywhere)
    assert names(content, everywhere).isdisjoint({"rev_a", "rev_ab", "rev_b_viewer_a"})
    assert {"rev_a", "rev_b", "rev_c", "rev_all"} <= names(content, tenant_level)


def _told(world: World, kind: str, subject_id: Any) -> dict[UUID, tuple[str, str | None]]:
    """Recipient membership → (title, body) of the notifications of ``kind`` about a subject."""
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        return {
            UUID(str(row.recipient_membership_id)): (str(row.title), row.body)
            for row in session.execute(
                select(
                    notification.c.recipient_membership_id,
                    notification.c.title,
                    notification.c.body,
                ).where(notification.c.kind == kind, notification.c.subject_id == subject_id)
            )
        }


def test_a_preparer_is_shown_and_told_its_request_as_its_scope_reads_it(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item APR-CONTENT-SCOPE-1: no exception for the requester — the scope in force at the read
    decides, and a notification is a read of the summary composed for its recipient. A preparer
    of entity A whose request names A and B (an import in quarantine mode: held to the entities
    of the rows that commit, R-106 (b)) is shown the header of its own request, withdraws it,
    and is told its outcome without the summary. The approvers the request waits for cover both
    entities and are told the summary; a preparer who covers both is told the summary too.

    The comment of a rejection is written to the preparer (item APR-REJECTION-REASON-PREPARER-1;
    the supervisor's ruling of 2026-10-01; 04 §16.10 rev 1.240): she is told why, in the
    notification and on her read of the request — that decision's comment alone, in an answer
    that is still a header. Another reader of the header reads no comment, and the comment of
    an approval stays withheld from her.

    A decision's reason code goes with its comment (item APR-DECISION-CODE-CONTENT-1; the
    supervisor's ruling of 2026-10-01; 04 §16.10 rev 1.252): it is free text of the decider, so
    it is content — the preparer reads the code of the rejection with its comment, another
    reader of the header reads neither, and the code of an approval stays withheld from her.
    Until then every reader of the header read it.

    Fail-first: with the stored summary in the three notifications the preparer of A is told
    the name of the record, and with ``visible`` for the read it is shown the content."""
    people = world.people
    a, b = world.entities["A"], world.entities["B"]
    _with_content(monkeypatch)
    held: dict[UUID, SubjectEntities] = {}
    install(
        monkeypatch,
        replace(
            engine.spec_for(SEVERAL),
            preparer_entities=lambda _session, subject_id: held[subject_id],
        ),
    )
    scoped = _person(world, clock, ("revenue_accountant", [a]))
    of_both = _person(world, clock, ("revenue_reviewer", [a, b]))
    summary = "Combine 2 contracts in CG-000031"

    def submitted(preparer: Principal) -> Mapping[str, Any]:
        subject_id = probe.new(world.scope("A", "B"))
        held[subject_id] = world.scope("A")
        with run(preparer) as uow:
            request = submit(
                uow,
                subject_type=SEVERAL,
                subject_id=subject_id,
                summary=summary,
                impact_preview=PREVIEW,
            )
            uow.commit()
        return request

    # Shown: the header of its own request; the approver for both entities, the content.
    first = submitted(scoped)
    assert _content(_read(clock, keyring, files, scoped, first["id"])) == _header(first)
    assert _content(_read(clock, keyring, files, of_both, first["id"])) == _whole(first, summary)
    assigned = _told(world, "APPROVAL_ASSIGNED", first["id"])
    assert assigned[_membership(of_both)][0] == f"Approval needed: {summary}"
    assert _membership(scoped) not in assigned

    # Told the rejection without the summary — and why: the comment is written to her.
    comment = "ENT-B's contract is not signed."
    code = "ENT-B order 4471: no countersignature"
    with run(of_both) as uow:
        decide(
            uow,
            **{**_args(first), "decision": "REJECT", "comment": comment, "reason_code": code},
        )
        uow.commit()
    withheld = f"{SEVERAL_LABEL} {first['request_no']}"
    assert _told(world, "ITEM_REJECTED", first["subject_id"]) == {
        _membership(scoped): (
            f"Rejected: {withheld}",
            f"Probe person rejected {withheld}: {comment}",
        )
    }
    # She reads it on her own request too: that comment with its code, and nothing else of the
    # content. An approver for entity A reads the same header and is not the preparer: neither.
    assert _content(_read(clock, keyring, files, scoped, first["id"])) == {
        **_header(first),
        "comments": [comment],
        "codes": [code],
    }
    assert _content(_read(clock, keyring, files, of_both, first["id"])) == {
        **_whole(first, summary, comment),
        "codes": [code],
    }
    assert _content(_read(clock, keyring, files, people["rev_a"], first["id"])) == _header(
        first, decisions=1
    )

    # Told the approval, and the void of a request whose subject changed, in the same words.
    # The comment of an approval is content: it stays withheld from her.
    second = submitted(scoped)
    with run(of_both) as uow:
        approved = decide(
            uow,
            **{
                **_args(second),
                "comment": "The combination stands.",
                "reason_code": "ENT-B's order is one contract with ENT-A's",
            },
        )
        uow.commit()
    assert approved["status"] == "APPROVED"
    withheld = f"{SEVERAL_LABEL} {second['request_no']}"
    assert _told(world, "ITEM_APPROVED", second["subject_id"]) == {
        _membership(scoped): (f"Approved: {withheld}", f"Probe person approved {withheld}.")
    }
    assert _content(_read(clock, keyring, files, scoped, second["id"])) == _header(
        second, decisions=1
    )
    third = submitted(scoped)
    probe.subjects.contents[third["subject_id"]]["name"] = "Changed after submission"
    with run(scoped) as uow:
        voided = engine.void_if_stale(uow, subject_type=SEVERAL, subject_id=third["subject_id"])
        uow.commit()
    assert voided is not None and voided["status"] == "VOIDED"
    told = _told(world, "APPROVAL_VOIDED", third["subject_id"])
    withheld = f"{SEVERAL_LABEL} {third['request_no']}"
    assert told[_membership(scoped)][0] == f"Approval voided: {withheld}"
    assert told[_membership(of_both)][0] == f"Approval voided: {summary}"
    assert {title for title, _ in told.values()} == {
        f"Approval voided: {withheld}",
        f"Approval voided: {summary}",
    }

    # It withdraws its own request, and the answer of the command is the header too.
    fourth = submitted(scoped)
    with run(scoped) as uow:
        row = withdraw(uow, approval_request_id=fourth["id"], comment="Wrong file.")
        answer = approval_queries.request_out(uow, fourth["id"])
        uow.commit()
    assert row["status"] == "WITHDRAWN"
    assert (answer["status"], _content(answer)) == ("WITHDRAWN", _header(fourth))

    # Positive control: a preparer who covers both entities is told the summary and the comment.
    fifth = submitted(people["preparer"])
    with run(of_both) as uow:
        decide(uow, **{**_args(fifth), "decision": "REJECT", "comment": comment})
        uow.commit()
    assert _told(world, "ITEM_REJECTED", fifth["subject_id"]) == {
        _membership(people["preparer"]): (
            f"Rejected: {summary}",
            f"Probe person rejected {summary}: {comment}",
        )
    }


def test_a_request_answers_what_it_was_submitted_with_to_its_readers_and_its_preparer(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item APR-REQUEST-REASON-1 (supervisor rulings R-83 (d) and R-104 (a); the ruling of
    2026-10-01; 04 §16.10 rev 1.252): API-S-Approval answers the reason code and the comment a
    request was submitted with — the justification its approver decides on.

    Both are content. A reader who covers every entity of the request reads them; a reader of
    the header reads neither; and the preparer reads the two she wrote, in an answer that is
    still a header — her own words, and nothing else of the content with them. A decision's own
    comment stays where it is, under its step.

    Fail-first: the answer had neither member, so the approver read no justification and no
    reason."""
    people = world.people
    a, b = world.entities["A"], world.entities["B"]
    _with_content(monkeypatch)
    held: dict[UUID, SubjectEntities] = {}
    install(
        monkeypatch,
        replace(
            engine.spec_for(SEVERAL),
            preparer_entities=lambda _session, subject_id: held[subject_id],
        ),
    )
    scoped = _person(world, clock, ("revenue_accountant", [a]))
    of_both = _person(world, clock, ("revenue_reviewer", [a, b]))
    summary = "Combine 2 contracts in CG-000031"
    reason, comment = "DUPLICATE", "ENT-B booked this order a second time in March."

    def submitted(reason_code: str | None, said: str | None) -> Mapping[str, Any]:
        subject_id = probe.new(world.scope("A", "B"))
        held[subject_id] = world.scope("A")
        with run(scoped) as uow:
            request = submit(
                uow,
                subject_type=SEVERAL,
                subject_id=subject_id,
                summary=summary,
                impact_preview=PREVIEW,
                reason_code=reason_code,
                comment=said,
            )
            uow.commit()
        return request

    def submitted_with(
        principal: Principal, request: Mapping[str, Any]
    ) -> tuple[bool, str | None, str | None]:
        shown = _read(clock, keyring, files, principal, request["id"])
        assert isinstance(shown, dict), shown
        return shown["content_withheld"], shown["reason_code"], shown["comment"]

    first = submitted(reason, comment)
    # The approver of both entities reads the whole request, and what it was submitted with.
    assert submitted_with(of_both, first) == (False, reason, comment)
    # The preparer covers entity A: a header, and the two she wrote.
    assert submitted_with(scoped, first) == (True, reason, comment)
    assert _content(_read(clock, keyring, files, scoped, first["id"])) == _header(first)
    # An approver for entity A reads the same header and wrote nothing of it: neither.
    assert submitted_with(people["rev_a"], first) == (True, None, None)

    # The decision's comment is another member: the request's own two do not move with it.
    with run(of_both) as uow:
        decide(uow, **{**_args(first), "comment": "The combination stands."})
        uow.commit()
    assert submitted_with(of_both, first) == (False, reason, comment)
    assert submitted_with(scoped, first) == (True, reason, comment)
    assert submitted_with(people["rev_a"], first) == (True, None, None)
    assert _content(_read(clock, keyring, files, scoped, first["id"])) == _header(
        first, decisions=1
    )

    # Positive control: a request submitted with neither answers null to its whole reader too.
    second = submitted(None, None)
    assert submitted_with(of_both, second) == (False, None, None)
    assert submitted_with(scoped, second) == (True, None, None)


def _denied(world: World, request_id: Any) -> list[tuple[str, UUID | None, dict[str, Any]]]:
    """(action, actor, detail) of the ``DENIED`` audit events on a request, oldest first."""
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        rows = session.execute(
            select(audit_event.c.action, audit_event.c.actor_id, audit_event.c.detail)
            .where(audit_event.c.object_id == request_id, audit_event.c.outcome == "DENIED")
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [(str(action), actor_id, dict(detail)) for action, actor_id, detail in rows]


def test_a_decision_the_kernel_refuses_is_on_record_as_denied(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item APR-DENIED-AUDIT-1 (DG-KRN-AUTH-05; REQ-PLT-019): a decision that one of the kernel's
    own checks refuses writes its ``DENIED`` audit event, as the subject's own check does (R-98)
    — in a transaction of its own, so the attempt stays on record when the refusal rolls the
    command back. The event names the action that was tried, the person, the step's permission
    and number, the subject, and the reason:

    - the preparer of a request of A and B, who holds no approval permission: ``NO_AUTHORITY``;
    - an approver for A alone on that request, approving and rejecting:
      ``ENTITIES_NOT_COVERED``, once per action;
    - a Revenue Reviewer for A on a step that names the Controller role: ``STEP_ROLE`` with the
      role's code;
    - a person who prepared a request and holds the step's permission: ``SELF_APPROVAL``;
    - the delegate of a person the subject excludes: ``EXCLUDED_DECIDER`` with the delegator.

    A member who cannot read the request is answered 404 and nothing is recorded about it. The
    approver who may decide decides, and no ``DENIED`` event is written for her.

    Fail-first: the five refusals answered 403 and left no trace."""
    people = world.people
    approve, reject = "approval_request.approve", "approval_request.reject"

    def facts(request: Mapping[str, Any], subject_type: ApprovalSubjectType) -> dict[str, Any]:
        return {
            "permission": PERMISSION,
            "subject_type": subject_type.value,
            "subject_id": str(request["subject_id"]),
            "step_no": 1,
        }

    # No authority at all; the permission for one entity of two; and nobody outside the request.
    both = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    preparer = _refused(run, people["preparer"], both)
    assert (preparer.slug, preparer.status, preparer.detail) == ("forbidden", 403, None)
    partial = _refused(run, people["rev_a"], both)
    assert (partial.slug, partial.detail) == ("forbidden", engine.EVERY_ENTITY_DETAIL)
    with run(people["rev_a"]) as uow, pytest.raises(Problem) as refused:
        decide(uow, **{**_args(both), "decision": "REJECT", "comment": "Not this quarter."})
    assert (refused.value.slug, refused.value.status) == ("forbidden", 403)
    assert _not_found(_refused(run, people["rev_c"], both))
    assert _denied(world, both["id"]) == [
        (approve, people["preparer"].id, {**facts(both, SEVERAL), "reason": "NO_AUTHORITY"}),
        (approve, people["rev_a"].id, {**facts(both, SEVERAL), "reason": "ENTITIES_NOT_COVERED"}),
        (reject, people["rev_a"].id, {**facts(both, SEVERAL), "reason": "ENTITIES_NOT_COVERED"}),
    ]
    # Positive control: the approver for both entities decides, and nothing is denied her.
    assert _decide(run, people["rev_ab"], both)["status"] == "APPROVED"
    assert len(_denied(world, both["id"])) == 3

    # The step's role.
    _route(
        world,
        ONE,
        [
            {
                "name": "Controller review",
                "permission": PERMISSION,
                "min_approvers": 1,
                "role": "controller",
            }
        ],
    )
    one = _submit(run, world, probe, ONE, world.scope("A"))
    without_role = _refused(run, people["rev_a_ctl_b"], one)
    assert without_role.detail == engine.ROLE_REQUIRED_DETAIL.format(role="Controller")
    assert _denied(world, one["id"]) == [
        (
            approve,
            people["rev_a_ctl_b"].id,
            {**facts(one, ONE), "reason": "STEP_ROLE", "role": "controller"},
        )
    ]
    assert _decide(run, people["ctl_a"], one)["status"] == "APPROVED"
    assert len(_denied(world, one["id"])) == 1

    # Self-approval: she prepared the request and holds the step's permission for its entities.
    with run(people["rev_all"]) as uow:
        own = submit(
            uow,
            subject_type=SEVERAL,
            subject_id=probe.new(world.scope("A", "B")),
            summary="Probe request of its approver",
        )
        uow.commit()
    herself = _refused(run, people["rev_all"], own)
    assert (herself.slug, herself.detail) == ("self-approval", engine.SELF_APPROVAL_DETAIL)
    assert _denied(world, own["id"]) == [
        (approve, people["rev_all"].id, {**facts(own, SEVERAL), "reason": "SELF_APPROVAL"})
    ]
    assert _decide(run, people["rev_ab"], own)["status"] == "APPROVED"

    # A decider the subject excludes, through a delegate: the event names the delegator.
    excluded = people["rev_all"]
    install(
        monkeypatch,
        replace(
            engine.spec_for(SEVERAL),
            excluded_deciders=lambda _session, _subject_id: frozenset({excluded.id}),
        ),
    )
    _delegate(world, clock, "rev_all", "delegate")
    last = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    on_behalf = _refused(run, people["delegate"], last)
    assert (on_behalf.slug, on_behalf.detail) == ("self-approval", engine.EXCLUDED_DETAIL)
    assert _denied(world, last["id"]) == [
        (
            approve,
            people["delegate"].id,
            {
                **facts(last, SEVERAL),
                "reason": "EXCLUDED_DECIDER",
                "on_behalf_of_id": str(excluded.id),
            },
        )
    ]
    assert _decide(run, people["rev_ab"], last)["status"] == "APPROVED"
    assert len(_denied(world, last["id"])) == 1


def test_the_other_refusals_of_a_decision_and_of_a_withdrawal_are_on_record(
    world: World,
    probe: Probe,
    run: Run,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
) -> None:
    """Item APR-DENIED-AUDIT-1, as ruled on 2026-10-02 (DG-KRN-AUTH-05; REQ-PLT-019). Beside the
    five reasons of the kernel's own checks, on record too:

    - the second factor inside ``decide``: ``mfa-required``, as the guards of the other routes
      record theirs;
    - a caller that is no person, refused before the request is read: ``NOT_A_PERSON`` with the
      id as sent and nothing of a request — the same event for an id that exists and one that
      does not (ruling R-41 (8));
    - a withdrawal by someone who is not the preparer: ``approval_request.withdraw``,
      ``NOT_PREPARER``;
    - the bulk route: one event per item it refuses, none for an item it decides.

    A caller who cannot read the request is answered 404 and nothing is recorded. And an event
    states nothing of the request's content — no summary, no amount, and neither the comment nor
    the code of the decision that was tried: the audit trail is read by a holder of the audit
    permission for all entities, whatever a request withholds.

    Fail-first: none of these refusals left a trace."""
    people = world.people
    approve, reject = "approval_request.approve", "approval_request.reject"
    both = _submit(run, world, probe, SEVERAL, world.scope("A", "B"))
    one = _submit(run, world, probe, ONE, world.scope("A"))
    subject = {"subject_type": SEVERAL.value, "subject_id": str(both["subject_id"])}
    step = {**subject, "permission": PERMISSION, "step_no": 1}

    # The second factor: an approver for both entities whose session is not verified.
    unverified = replace(people["rev_ab"], mfa_verified_at=None)
    no_factor = _refused(run, unverified, both)
    assert (no_factor.slug, no_factor.status) == ("mfa-required", 403)
    # A rejection that is refused: neither its comment nor its code reaches the trail.
    tried = {"decision": "REJECT", "comment": "ENT-B is unsigned.", "reason_code": "ENT-B 4471"}
    with run(people["rev_a"]) as uow, pytest.raises(Problem) as refused:
        decide(uow, **{**_args(both), **tried})
    assert (refused.value.slug, refused.value.status) == ("forbidden", 403)
    # A withdrawal by a member who reads the request and did not prepare it. One who does not
    # read it is answered 404 and leaves no event — and 403 with its event where a command of
    # the subject's own domain found the request for them (``through_subject``).
    with run(people["rev_ab"]) as uow, pytest.raises(Problem) as refused:
        withdraw(uow, approval_request_id=both["id"], comment="Not mine to withdraw.")
    assert (refused.value.slug, refused.value.status) == ("forbidden", 403)
    with run(people["rev_c"]) as uow, pytest.raises(Problem) as refused:
        withdraw(uow, approval_request_id=both["id"], comment=None)
    assert _not_found(refused.value)
    assert len(_denied(world, both["id"])) == 3
    with run(people["rev_c"]) as uow, pytest.raises(Problem) as refused:
        withdraw(uow, approval_request_id=both["id"], comment=None, through_subject=True)
    assert (refused.value.slug, refused.value.status) == ("forbidden", 403)
    not_preparer = {**subject, "permission": "", "reason": "NOT_PREPARER"}
    assert _denied(world, both["id"]) == [
        (approve, people["rev_ab"].id, {**step, "reason": "mfa-required"}),
        (reject, people["rev_a"].id, {**step, "reason": "ENTITIES_NOT_COVERED"}),
        ("approval_request.withdraw", people["rev_ab"].id, not_preparer),
        ("approval_request.withdraw", people["rev_c"].id, not_preparer),
    ]
    # Nothing the request withholds is in an event, in whatever column.
    with tenant_session(_all_entities(world.tenant_id), read_only=True) as session:
        events = session.execute(
            select(audit_event).where(
                audit_event.c.object_id == both["id"], audit_event.c.outcome == "DENIED"
            )
        ).all()
    written = json.dumps([dict(event._mapping) for event in events], default=str)
    assert len(events) == 4
    for withheld in (both["summary"], "unsigned", "4471", "Not mine to withdraw"):
        assert withheld not in written

    # A caller that is no person: the same event for the request and for an id that names none.
    nobody = replace(people["rev_ab"], kind=PrincipalKind.SYSTEM, id=None)
    unknown = new_id()
    for request_id in (both["id"], unknown):
        with run(nobody) as uow, pytest.raises(Problem) as refused:
            decide(uow, **{**_args(both), "approval_request_id": request_id})
        assert (refused.value.slug, refused.value.detail) == ("forbidden", engine.NON_HUMAN_DETAIL)
    not_a_person = (approve, None, {"permission": "", "reason": "NOT_A_PERSON"})
    assert _denied(world, both["id"])[4:] == [not_a_person]
    assert _denied(world, unknown) == [not_a_person]

    # Bulk: the item it refuses is recorded, the item it decides is not.
    items = [
        BulkApproveItem(
            approval_request_id=request["id"],
            subject_content_sha256=request["subject_content_sha256"],
            impact_preview_sha256=request["impact_preview_sha256"],
        )
        for request in (both, one)
    ]
    refused_item, decided_item = bulk_approve(
        _context(people["rev_a"], clock),
        items,
        comment=None,
        clock=clock,
        keyring=keyring,
        files=files,
    )
    assert refused_item.problem is not None and refused_item.problem.slug == "forbidden"
    assert (decided_item.problem, decided_item.status) == (None, "APPROVED")
    assert _denied(world, both["id"])[5:] == [
        (approve, people["rev_a"].id, {**step, "reason": "ENTITIES_NOT_COVERED"})
    ]
    assert _denied(world, one["id"]) == []
