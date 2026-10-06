"""Who reads a subject in full, and whose the request's row is (04 §16.10 rev 1.319 "Who reads a
subject in full" and "The request's row is the kernel's"; dev-guide DG-KRN-APR-06 and -07, rev
1.295; 03 REQ-PLT-012 rev 1.146; item READ-SCOPE-BY-PERMISSION-1, register index 301; the
supervisor's rulings of 2026-10-03 on lane SECFIX-APR's reading; R-41 (1), R-64 (6)).

The kernel's side of the item, on the probes and the world of ``test_approval_scope``. The
routes' side is ``tests/api/test_read_scope_by_permission.py``.

Two facts meet here. A guarded command runs under the scope of its route's own permission
(``auth.dependencies.require``), and the kernel admits a preparer, and takes a delegation, by
another question — whether the person READS the subject, one permission for every entity of it.
So the question can answer yes where the route's permission does not hold the one entity a
request names. ``approval_request`` is under the entity policy on ``entity_id``. Measured before
the kernel's statements moved (2026-10-03): an import's submission by an SSP Analyst of one
entity who uploads for another answered 403 ``forbidden`` without a word — the policy's check
refused the insert. Now the question decides, not the route: once it has answered, the request
is looked for, inserted, read back, locked and closed under the tenant's scope.

A route is stood for by ``_on_route``: the principal of the context ``require(permission)``
hands on, with the scope of that permission for its transaction
(``test_the_route_of_this_module_is_the_guards`` holds the two equal). The grants of the people
are read from their role assignments, as a request reads them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine
from erev_api.approvals.engine import submit, withdraw
from erev_api.auth.principal import Principal
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import approval_delegation, approval_request, audit_event
from erev_api.enums import AuditOutcome
from erev_api.problems import Problem
from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session
from support.rows import approval_delegation_values, insert_custom_role
from tests.domain.platform.test_approval_scope import (  # noqa: F401 - fixtures
    ONE,
    PERMISSION,
    SEVERAL,
    Probe,
    Run,
    World,
    _all_entities,
    _can_decide,
    _context,
    _decide,
    _denied,
    _listed,
    _membership,
    _not_found,
    _notified,
    _person,
    _reads_content,
    _refused,
    _status,
    _stored_scope,
    _submit,
    files,
    probe,
    run,
    world,
)

# A command's permission that a Revenue Accountant holds: the route these tests stand on.
ROUTE = "contract.create"
UPLOADS_ONLY = "uploads_only"  # a role of the workspace's own: ``import.upload`` alone
# 04 §16.10 rev 1.319, spelled once: every other test compares with ``engine.EVERY_ENTITY_DETAIL``.
SENTENCE = (
    "Deciding this item takes the approval permission and the permission to read it, "
    "for every legal entity it names."
)


def _on_route(principal: Principal, permission: str = ROUTE) -> Principal:
    """``principal`` as a command guarded by ``permission`` holds it: the transaction's entity
    scope is the scope of that permission, and what she holds is unchanged."""
    held = principal.permission_scopes[permission]
    return dataclasses.replace(principal, entity_scope="*" if held == "*" else tuple(sorted(held)))


@dataclasses.dataclass(frozen=True)
class Stage:
    """The world of ``test_approval_scope`` with two preparers, each as her route holds her: Rae
    prepares for A and reads B; Una prepares for A and reads nothing of B."""

    place: World
    subjects: Probe
    unit: Run
    clock: FrozenClock
    rae: Principal
    una: Principal
    a: UUID
    b: UUID

    def person(self, *grants: tuple[str, list[UUID]]) -> Principal:
        return _person(self.place, self.clock, *grants)

    def pending_of_b(self) -> Mapping[str, Any]:
        """A request of entity B alone, submitted by Rae from a route that holds A alone."""
        with self.unit(self.rae) as uow:
            request = submit(
                uow,
                subject_type=ONE,
                subject_id=self.subjects.new(self.place.scope("B")),
                summary="Probe request of entity B",
            )
            uow.commit()
        return request

    def status(self, request_id: UUID) -> tuple[str, int]:
        return _status(self.place, request_id)

    def denied(self, actor: Principal) -> list[str]:
        """The actions of the ``DENIED`` events of ``actor``, in order."""
        with tenant_session(_all_entities(self.place.tenant_id), read_only=True) as session:
            return [
                str(action)
                for action in session.scalars(
                    select(audit_event.c.action)
                    .where(
                        audit_event.c.outcome == AuditOutcome.DENIED,
                        audit_event.c.actor_id == actor.id,
                    )
                    .order_by(audit_event.c.chain_seq)
                )
            ]


@pytest.fixture
def stage(world: World, probe: Probe, run: Run, clock: FrozenClock) -> Stage:  # noqa: F811
    a, b = world.entities["A"], world.entities["B"]
    rae = _person(world, clock, ("revenue_accountant", [a]), ("viewer", [b]))
    una = _person(world, clock, ("revenue_accountant", [a]))
    # the union of Rae's roles names both entities; the command's permission one
    assert set(rae.entity_scope) == {a, b} and rae.permission_scopes[ROUTE] == frozenset({a})
    assert rae.permission_scopes["config.read"] == frozenset({a, b})
    assert _on_route(rae).db_context.entity_scope == (a,)
    return Stage(
        place=world,
        subjects=probe,
        unit=run,
        clock=clock,
        rae=_on_route(rae),
        una=_on_route(una),
        a=a,
        b=b,
    )


def _scope_of(session: Session) -> str:
    return str(session.execute(text("SELECT current_setting('app.entity_scope', true)")).scalar())


def _reads(session: Session, request_id: UUID) -> bool:
    """Whether the session's own scope reads the request's row."""
    found = session.execute(
        select(approval_request.c.id).where(approval_request.c.id == request_id)
    ).first()
    return found is not None


def _problem(problem: Problem) -> tuple[str, int, str | None, list[tuple[str | None, str]]]:
    return (
        problem.slug,
        problem.status,
        problem.detail,
        [(error.rule_id, error.message) for error in problem.errors],
    )


def test_the_route_of_this_module_is_the_guards(stage: Stage) -> None:
    """``_on_route`` is what ``auth.dependencies.require`` hands on (``admitted_by``)."""
    from erev_api.auth.dependencies import admitted_by

    rae = stage.person(("revenue_accountant", [stage.a]), ("viewer", [stage.b]))
    for permission in (ROUTE, "contract.read", "config.read"):
        handed = admitted_by(_context(rae, stage.clock), permission).principal
        assert handed == _on_route(rae, permission), permission
    everywhere = stage.place.people["preparer"]
    assert admitted_by(_context(everywhere, stage.clock), ROUTE).principal == _on_route(everywhere)


def test_a_request_is_inserted_and_read_back_whatever_the_scope_of_the_route(stage: Stage) -> None:
    """Statement (a) of the ruling, and the read-back of (b). Rae's command runs under the
    scope of its permission — entity A — and her subject is of entity B, which she reads. The
    request is stored for B, PENDING, and returned to the command; the command's own scope does
    not read the row, before or after, and is the route's again when the kernel returns.

    As built before the statements moved: 403 ``forbidden`` without a detail, from the policy's
    check on the insert."""
    place = stage.place
    with stage.unit(stage.rae) as uow:
        before = _scope_of(uow.session)
        request = submit(
            uow,
            subject_type=ONE,
            subject_id=stage.subjects.new(place.scope("B")),
            summary="Probe request of entity B",
        )
        assert (request["status"], request["preparer_id"]) == ("PENDING", stage.rae.id)
        assert _scope_of(uow.session) == before == str(stage.a)
        assert _reads(uow.session, request["id"]) is False  # the route's scope: A alone
        uow.commit()
    assert _stored_scope(place, request["id"]) == (stage.b, [], False)
    assert stage.status(request["id"]) == ("PENDING", 0)
    assert stage.denied(stage.rae) == []
    # the control: a subject of the route's own entity, as before
    with stage.unit(stage.rae) as uow:
        own = submit(
            uow,
            subject_type=ONE,
            subject_id=stage.subjects.new(place.scope("A")),
            summary="Probe request of entity A",
        )
        assert _reads(uow.session, own["id"]) is True
        uow.commit()
    assert _stored_scope(place, own["id"]) == (stage.a, [], False)


def test_a_second_submission_is_told_of_the_pending_request_only_behind_the_question(
    stage: Stage,
) -> None:
    """Statement (b), lane SECFIX-APR's first condition. A pending request of entity B is hidden
    from a command whose route holds A alone, so the look for it that stands before the question
    finds nothing. Rae, whom the question admits, is told by name — 409 ``invalid-transition``,
    "This item already has a pending approval request." — by the second look, under the
    tenant's scope. Una, whom the question refuses, receives its 403 and nothing about the
    request: the same answer as for a subject of B that has none.

    As built before the second look: the insert met the database's one-pending-request index —
    an error of the database, not the named refusal."""
    request = stage.pending_of_b()
    subject_id = request["subject_id"]

    def again(principal: Principal, subject: UUID) -> Problem:
        with stage.unit(principal) as uow, pytest.raises(Problem) as excinfo:
            submit(uow, subject_type=ONE, subject_id=subject, summary="Probe request, again")
        return excinfo.value

    named = again(stage.rae, subject_id)
    assert _problem(named) == (
        "invalid-transition",
        409,
        None,
        [(engine.RULE_LIFECYCLE, engine.ALREADY_PENDING)],
    )
    refused = again(stage.una, subject_id)
    fresh = again(stage.una, stage.subjects.new(stage.place.scope("B")))
    by_name = ("forbidden", 403, engine.OUTSIDE_SCOPE_DETAIL, [])
    assert _problem(refused) == _problem(fresh) == by_name
    assert stage.denied(stage.una) == [engine.SUBMIT_ACTION] * 2
    assert stage.status(request["id"]) == ("PENDING", 0)
    # the control: a pending request the route's own scope reads is named by the first look
    own = stage.subjects.new(stage.place.scope("A"))
    with stage.unit(stage.rae) as uow:
        submit(uow, subject_type=ONE, subject_id=own, summary="Probe request of entity A")
        uow.commit()
    for principal in (stage.rae, stage.una):
        assert _problem(again(principal, own))[:2] == ("invalid-transition", 409)


def test_a_subjects_command_withdraws_its_request_whatever_the_scope_of_its_route(
    stage: Stage,
) -> None:
    """Statement (c), lane SECFIX-APR's second condition: the lock is taken under the tenant's
    scope only THROUGH A SUBJECT. Rae's own command — its route holds A — withdraws her request
    of B; the same call as a route of the approvals API makes it (it names the request, not the
    subject) answers 404 under that scope, as for an id that names nothing. Through the subject
    another preparer is told she is not the preparer, 403, as before — and her attempt is on
    record once, as on the approvals route (04 §16.10 rev 1.266, item APR-DENIED-AUDIT-1:
    ``approval_request.withdraw``, ``DENIED``, reason ``NOT_PREPARER``, the request and its
    subject, no permission), under whatever scope her route holds; the 404 leaves no event.

    The 404 is a statement of the kernel under a scope that does not read the row, not what a
    preparer meets on ``POST /approvals/{id}/withdraw``: an approvals route carries no
    permission guard and runs under the union of her roles, where she reads her own request."""
    request = stage.pending_of_b()
    request_id = request["id"]
    with stage.unit(stage.rae) as uow, pytest.raises(Problem) as hidden:
        withdraw(uow, approval_request_id=request_id, comment="By its id.")
    assert _not_found(hidden.value)
    assert _denied(stage.place, request_id) == []
    with stage.unit(stage.una) as uow, pytest.raises(Problem) as other:
        withdraw(uow, approval_request_id=request_id, comment="Not mine.", through_subject=True)
    assert _problem(other.value) == ("forbidden", 403, engine.WITHDRAW_DETAIL, [])
    assert _denied(stage.place, request_id) == [
        (
            "approval_request.withdraw",
            stage.una.id,
            {
                "subject_type": ONE.value,
                "subject_id": str(request["subject_id"]),
                "permission": "",
                "reason": "NOT_PREPARER",
            },
        )
    ]
    assert stage.status(request_id) == ("PENDING", 0)
    with stage.unit(stage.rae) as uow:
        row = withdraw(
            uow, approval_request_id=request_id, comment="Too early.", through_subject=True
        )
        assert _scope_of(uow.session) == str(stage.a)
        uow.commit()
    assert (row["status"], row["void_reason"]) == ("WITHDRAWN", engine.VOID_WITHDRAWN_BY_PREPARER)
    assert stage.status(request_id) == ("WITHDRAWN", 0)
    assert ("voided", request["subject_id"], request_id) in stage.subjects.subjects.calls


def test_a_changed_or_ended_subject_voids_its_request_whatever_the_scope_of_the_route(
    stage: Stage,
) -> None:
    """Statement (d) and ``void_subject``, lane SECFIX-APR's third condition: one scope for the
    whole void. A command that changes a subject, or ends it, closes the subject's pending
    request; under a route that holds A alone the request of B was not found, and a changed
    subject left its request standing until a decision hashed it again."""
    probes = stage.subjects
    stale = stage.pending_of_b()
    probes.subjects.contents[stale["subject_id"]]["name"] = "Probe subject, edited"
    with stage.unit(stage.una) as uow:
        voided = engine.void_if_stale(uow, subject_type=ONE, subject_id=stale["subject_id"])
        assert _scope_of(uow.session) == str(stage.a)
        uow.commit()
    assert voided is not None
    assert (voided["status"], voided["void_reason"]) == ("VOIDED", engine.VOID_STALE_SUBJECT)
    assert stage.status(stale["id"]) == ("VOIDED", 0)

    ended = stage.pending_of_b()
    with stage.unit(stage.una) as uow:
        closed = engine.void_subject(
            uow, subject_type=ONE, subject_id=ended["subject_id"], comment="The run was cancelled."
        )
        assert _scope_of(uow.session) == str(stage.a)
        uow.commit()
    assert closed is not None
    assert (closed["status"], closed["void_reason"]) == ("VOIDED", engine.VOID_SUBJECT_VOIDED)
    assert stage.status(ended["id"]) == ("VOIDED", 0)
    assert [call[0] for call in probes.subjects.calls] == ["voided", "voided"]
    # an unchanged subject keeps its request, and a subject without one answers nothing
    kept = stage.pending_of_b()
    with stage.unit(stage.una) as uow:
        assert engine.void_if_stale(uow, subject_type=ONE, subject_id=kept["subject_id"]) is None
        none_pending = probes.new(stage.place.scope("B"))
        assert (
            engine.void_subject(uow, subject_type=ONE, subject_id=none_pending, comment=None)
            is None
        )
    assert stage.status(kept["id"]) == ("PENDING", 0)


def _delegated(stage: Stage, delegate: Principal) -> None:
    """``rev_all``, who approves for every entity, delegates ``contract.approve``."""
    place = stage.place
    values = approval_delegation_values(
        place.tenant_id,
        delegator_membership_id=_membership(place.people["rev_all"]),
        delegate_membership_id=_membership(delegate),
        valid_from=stage.clock.now() - timedelta(days=1),
        valid_to=stage.clock.now() + timedelta(days=29),
    )
    values["permissions"] = [PERMISSION]
    with tenant_session(_all_entities(place.tenant_id)) as session:
        session.execute(insert(approval_delegation).values(**values))


def test_a_delegate_decides_what_she_reads_in_full(stage: Stage) -> None:
    """R-41 (1) as rev 1.319 asks it — a delegation conveys the permission, not the view — with
    the people the cast of ``test_approval_scope`` lacks: roles whose union names A and B, a
    read that names A alone. Dee is a Viewer of A and holds, for B, a role with
    ``import.upload`` alone; Rhea is a Revenue Reviewer of A with the same second role. Both
    act for ``rev_all``, who approves for every entity. A request of A and B, a subject that
    ``contract.read`` reads:

    - Dee does not decide it (404: it is no request of hers to read), does not find it listed or
      waiting, and is not told of it;
    - Rhea lists it in her own right — her permission names A — and does not find it waiting; her
      Approve answers 403 with the one sentence of both cases, which says what deciding takes:
      the approval permission AND the read, for every entity;
    - Vic, a Viewer of A and B with the same delegation, decides on the delegator's behalf.

    As built: Dee and Rhea decided — the union of their roles covered the request (the kernel
    asked ``entity_scope``)."""
    place, clock, a, b = stage.place, stage.clock, stage.a, stage.b
    with tenant_session(_all_entities(place.tenant_id)) as session:
        insert_custom_role(
            session, tenant_id=place.tenant_id, code=UPLOADS_ONLY, permissions=["import.upload"]
        )
    dee = stage.person(("viewer", [a]), (UPLOADS_ONLY, [b]))
    rhea = stage.person(("revenue_reviewer", [a]), (UPLOADS_ONLY, [b]))
    vic = stage.person(("viewer", [a, b]))
    for delegate in (dee, rhea):
        assert set(delegate.entity_scope) == {a, b}
        assert delegate.permission_scopes["contract.read"] == frozenset({a})
        _delegated(stage, delegate)
    _delegated(stage, vic)

    request = _submit(stage.unit, place, stage.subjects, SEVERAL, place.scope("A", "B"))
    request_id = request["id"]
    told = _notified(place, "APPROVAL_ASSIGNED", request_id)
    assert _membership(vic) in told and _membership(place.people["rev_all"]) in told
    assert not {_membership(dee), _membership(rhea)} & told

    assert _can_decide(place, clock, dee, request_id) is False
    assert request_id not in _listed(clock, dee)
    assert _not_found(_refused(stage.unit, dee, request))

    assert _can_decide(place, clock, rhea, request_id) is False
    assert request_id in _listed(clock, rhea)
    assert request_id not in _listed(clock, rhea, assigned=True)
    assert _problem(_refused(stage.unit, rhea, request)) == ("forbidden", 403, SENTENCE, [])
    assert stage.status(request_id) == ("PENDING", 0)

    assert request_id in _listed(clock, vic, assigned=True)
    assert _decide(stage.unit, vic, request)["status"] == "APPROVED"
    # what a delegate reads in full is hers to decide through the same delegation: a request of A
    single = _submit(stage.unit, place, stage.subjects, ONE, place.scope("A"))
    assert single["id"] in _listed(clock, dee, assigned=True)
    assert _decide(stage.unit, dee, single)["status"] == "APPROVED"


def test_an_approver_in_her_own_right_is_asked_nothing_further(stage: Stage) -> None:
    """The order of ``engine.find_authority`` (04 §16.10 rev 1.319 "Who is not asked"; lane
    SECFIX-APR's third reading): the principal's own grants first, the question only before a
    delegation is taken. Ava holds a role of the workspace's own with ``contract.approve``
    alone, for A and B — she approves and reads no contract. The request of A and B is put
    before her: she lists it, finds it waiting, is told of it, reads its content — what
    REQ-PLT-015 rests on for her is the request's content, answered by the step's permission —
    and decides it in her own right.

    With the question asked first, of everyone, she would be refused all of it: no permission
    of hers reads the subject. On the base she decided as well — the union of her role named
    both entities — so this test is a control there and a witness of the order here."""
    place, clock, a, b = stage.place, stage.clock, stage.a, stage.b
    with tenant_session(_all_entities(place.tenant_id)) as session:
        insert_custom_role(
            session, tenant_id=place.tenant_id, code="approves_only", permissions=[PERMISSION]
        )
    ava = stage.person(("approves_only", [a, b]))
    assert ava.permission_scopes == {PERMISSION: frozenset({a, b})}

    request = _submit(stage.unit, place, stage.subjects, SEVERAL, place.scope("A", "B"))
    request_id = request["id"]
    assert _membership(ava) in _notified(place, "APPROVAL_ASSIGNED", request_id)
    assert request_id in _listed(clock, ava)
    assert request_id in _listed(clock, ava, assigned=True)
    assert request_id in _reads_content(clock, ava)
    assert _can_decide(place, clock, ava, request_id) is True
    decided = _decide(stage.unit, ava, request)
    assert decided["status"] == "APPROVED"
    assert stage.status(request_id) == ("APPROVED", 1)
