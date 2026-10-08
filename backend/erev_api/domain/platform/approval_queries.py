"""Approval request reads (04 §15.3 API-R-09, §16.10, T-PLT-17 to T-PLT-21; SCREENS §15.3,
§15.4; PRD BR-PLT-07; REQ-PLT-013, REQ-PLT-017, REQ-UX-013; BUILD_SPEC PLF-16).

A request is visible to its preparer, to everyone who decided it and to the holders of the
permission of any of its steps for AT LEAST ONE entity of the request — through their own grants,
or through a delegation in force when they read the subject in full in their OWN right
(``engine.decision_authorities``; supervisor ruling R-41 (1): a delegation conveys the permission,
not the view; 04 §16.10 rev 1.319 "Who reads a subject in full": ONE permission that reads the
subject, held for every entity of the request — until then the union of the entities of the
caller's roles) — always within the caller's entity scope: RLS hides a request of one entity
outside it (RLS-TE on ``entity_id``), and ``visible`` applies the same rule to a request of
several entities, whose row no policy hides (04 T-PLT-17 rev 1.104; REQ-PLT-012). A request that
spans every entity is listed only for a permission held for all entities. ``assigned_to_me=true``
keeps the pending requests whose active step permission ONE authority of the caller — its own
grants, or one delegation of a subject the caller reads in full — holds for every entity of the
request, and that the caller neither prepared nor decided (SCREENS §15.3 "Waiting for me";
dev-guide DG-KRN-APR-06). ``preparer`` is ``me`` or a membership id.
``entity`` takes entity codes or ids (API-C-11, repeatable): a request matches when it is a request
of one of the named entities (``gates.request_of_entity``), and an unknown code answers 422
``validation-failed`` with rule_id API-C-11 ([J] D-88 L7-2-Q-13). ``approval_outs`` builds
API-S-Approval, with ``can_decide`` from the approval engine, ``entity`` and ``entities`` as
API-S-Ref read from ``legal_entity`` (the entities of the reader's own scope; ``entity_count`` and
``all_entities`` state the rest) and the impact preview summary read from the stored
``IMPACT_PREVIEW`` file.

Listing a request is not reading what it puts in force (04 §16.10 rev 1.208; item
APR-CONTENT-SCOPE-1). Its CONTENT — the summary, the amount and the flags, the impact preview,
the attachments, what the deciders wrote — is answered only to a reader who covers EVERY entity
of the request (``content_visible``): with the permission of a step, or — its preparer, a decider
and a delegate — with a permission that reads the subject (rev 1.319). A reader who covers some
of them reads the header and ``content_withheld``, in which nothing of an entity outside its
scope is named. The file routes and the attachment routes ask the same rule
(``file_access.request_content_visible``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol
from uuid import UUID

from erev_engine.currencies import ISO_4217
from sqlalchemy import (
    ColumnElement,
    Select,
    Uuid,
    and_,
    case,
    exists,
    false,
    func,
    literal,
    null,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api.approvals import engine, readers
from erev_api.approvals.subjects import (
    SUBJECTS,
    SubjectEntities,
    covered_link,
    withheld_summary,
)
from erev_api.auth.principal import SYSTEM_DISPLAY_NAME
from erev_api.db.session import of_session_tenant, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    file_attachment,
    file_object,
    legal_entity,
    role,
    rule,
    tenant_membership,
)
from erev_api.domain.close import gates
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    ApprovalSubjectType,
    PrincipalKind,
)
from erev_api.files.store import open_file
from erev_api.money import money_out
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

type Scope = Literal["*"] | frozenset[UUID]

ASSIGNED_TO_ME: Final = "assigned_to_me"
ENTITY: Final = "entity"
PREPARER: Final = "preparer"
PREPARER_ME: Final = "me"
CUSTOM_FILTERS: Final = frozenset({ASSIGNED_TO_ME, ENTITY, PREPARER})
RULE_ID: Final = "API-C-09"
CONTEXT_RULE_ID: Final = "API-C-11"
UNKNOWN_ENTITY: Final = "Choose entities that exist in this workspace."
ATTACHMENT_SUBJECT: Final = "approval_request"
# The columns of T-PLT-17 that hold content (04 §16.10 rev 1.208): a list parameter reads one
# through ``shown`` only. The label of the reader's own ``amount`` sort key. ``reason_code`` since
# rev 1.252 (item APR-REQUEST-REASON-1): the code a void, a combination or a reopen was requested
# with says something of the subject, as a flag does.
CONTENT_COLUMNS: Final = frozenset(
    {
        "summary",
        "amount_functional",
        "amount_currency",
        "flags",
        "impact_preview_file_id",
        "impact_preview_sha256",
        "reason_code",
        "comment",
    }
)
AMOUNT_KEY: Final = "amount_shown"
# 04 §16.10 impact_preview.summary fields: (field, preview side, key of that side). Rev 1.126
# (supervisor ruling R-61 (f)): the catch-up total a preview states (a modification, an estimate
# version, a criteria-met activation) and the books a criteria-met activation moves.
SUMMARY_FIELDS: Final = (
    ("revenue_by_period_before", "before", "revenue_by_period"),
    ("revenue_by_period_after", "after", "revenue_by_period"),
    ("balances_before", "before", "balances"),
    ("balances_after", "after", "balances"),
    ("journal_lines", "after", "journal_lines"),
    ("catch_up_total", "after", "catch_up_total"),
    ("criteria_met", "after", "criteria_met"),
)


class Page(Protocol):
    """A list page: ``api.lists.ListResult`` (domain code does not import ``api``)."""

    @property
    def items(self) -> list[Mapping[str, Any]]: ...


def _invalid(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed", errors=[ProblemError(field=field, rule_id=RULE_ID, message=message)]
    )


# The authorities a principal decides with are the engine's (``engine.decision_authorities``); the
# queue filters with the same ones, so a request is "waiting for me" exactly when ``decide`` finds
# an authority for it.
decision_authorities = engine.decision_authorities
union_scopes = engine.union_scopes


def _entity_array(ids: Sequence[UUID]) -> ColumnElement[Any]:
    return literal(list(ids), ARRAY(Uuid()))


def _tenant_level() -> ColumnElement[bool]:
    """The request names no entity and does not span every entity: a tenant-level subject."""
    return and_(
        approval_request.c.entity_id.is_(None),
        func.cardinality(approval_request.c.entity_ids) == 0,
        approval_request.c.is_all_entities.is_(False),
    )


def _entities_covered(scope: Scope) -> ColumnElement[bool]:
    """EVERY entity of the request is in ``scope`` (``SubjectEntities.covered_by`` in SQL): the one
    entity of ``entity_id``, each of ``entity_ids``; a tenant-level request always; a request that
    spans every entity only for scope ``"*"``."""
    if not isinstance(scope, frozenset):
        return true()
    ids = sorted(scope)
    return and_(
        approval_request.c.is_all_entities.is_(False),
        or_(approval_request.c.entity_id.is_(None), approval_request.c.entity_id.in_(ids)),
        approval_request.c.entity_ids.contained_by(_entity_array(ids)),
    )


def _entities_touched(scope: Scope) -> ColumnElement[bool]:
    """AT LEAST ONE entity of the request is in ``scope`` (``SubjectEntities.touched_by`` in SQL);
    a tenant-level request always; a request that spans every entity only for scope ``"*"``."""
    if not isinstance(scope, frozenset):
        return true()
    ids = sorted(scope)
    return or_(
        _tenant_level(),
        approval_request.c.entity_id.in_(ids),
        approval_request.c.entity_ids.overlap(_entity_array(ids)),
    )


def _held(
    scopes: Mapping[str, Scope], entities: Callable[[Scope], ColumnElement[bool]]
) -> ColumnElement[bool]:
    """The step's permission is one of ``scopes`` and its scope satisfies ``entities``."""
    clauses = [
        and_(approval_step.c.required_permission == code, entities(scope))
        for code, scope in sorted(scopes.items())
    ]
    return or_(*clauses) if clauses else false()


def _in_entity_scope(principal: Principal) -> ColumnElement[bool]:
    """``engine.in_entity_scope`` in SQL for a request of several entities: one of them is in the
    principal's entity scope. A request of one entity is left to RLS-TE on ``entity_id``."""
    if principal.entity_scope == "*":
        return true()
    return or_(
        func.cardinality(approval_request.c.entity_ids) == 0,
        approval_request.c.entity_ids.overlap(_entity_array(sorted(principal.entity_scope))),
    )


def _step_exists(*conditions: ColumnElement[bool]) -> ColumnElement[bool]:
    return exists(
        select(approval_step.c.id).where(
            approval_step.c.tenant_id == approval_request.c.tenant_id,
            approval_step.c.approval_request_id == approval_request.c.id,
            *conditions,
        )
    )


def _decided_by(user_id: UUID) -> ColumnElement[bool]:
    return exists(
        select(approval_decision.c.id).where(
            approval_decision.c.tenant_id == approval_request.c.tenant_id,
            approval_decision.c.approval_request_id == approval_request.c.id,
            or_(
                approval_decision.c.approver_id == user_id,
                approval_decision.c.on_behalf_of_id == user_id,
            ),
        )
    )


def visible(
    principal: Principal, authorities: Sequence[Mapping[str, Scope]]
) -> ColumnElement[bool]:
    """The requests the principal lists and reads (04 §16.10 rev 1.104; ``engine.visible_to`` in
    SQL): within its entity scope, the ones it prepared or decided and the ones with a step whose
    permission it holds for at least one entity of the request — through its own grants
    (``authorities[0]``), or through a delegation when it reads the subject in full in its OWN
    right (``_own_scope_covers``; R-41 (1): a delegation is listed only where the delegate may
    read all of it)."""
    own, delegated = authorities[0], union_scopes(authorities[1:])
    clauses = [_step_exists(_held(own, _entities_touched))]
    if delegated:
        clauses.append(
            and_(_own_scope_covers(principal), _step_exists(_held(delegated, _entities_touched)))
        )
    if principal.id is not None:
        clauses += [approval_request.c.preparer_id == principal.id, _decided_by(principal.id)]
    return and_(_in_entity_scope(principal), or_(*clauses))


def _own_scope_covers(principal: Principal) -> ColumnElement[bool]:
    """``engine.own_scope_covers`` in SQL: the principal reads the subject of the request in full
    in its OWN right — ONE permission that reads a subject of the request's type is held for
    every entity of the request (04 §16.10 rev 1.319 "Who reads a subject in full";
    ``approvals.readers``; R-41 (1): a delegation conveys the permission, not the view). Until
    that revision: the principal's entity scope, the union of the entities of every role. A
    request that names no entity asks nothing; a SYSTEM principal covers what its entity scope
    covers, and so does the provider's operator at the command line (rev 1.321: the kernel's one
    predicate, ``engine.asked_by_entity_scope``, names the principals for both forms)."""
    if engine.asked_by_entity_scope(principal):
        if principal.entity_scope == "*":
            return true()
        return _entities_covered(frozenset(principal.entity_scope))
    held = principal.permission_scopes
    clauses = [_tenant_level()]
    for code, scope in sorted(held.items()):
        subject_types = readers.read_with(code)
        if subject_types:
            clauses.append(
                and_(approval_request.c.subject_type.in_(subject_types), _entities_covered(scope))
            )
    if held:
        clauses.append(
            and_(
                approval_request.c.subject_type.in_(readers.read_with_any()),
                _entities_covered(readers.any_scope(held)),
            )
        )
    return or_(*clauses)


def content_visible(
    principal: Principal, authorities: Sequence[Mapping[str, Scope]]
) -> ColumnElement[bool]:
    """The requests whose CONTENT the principal reads (04 §16.10 rev 1.208; item
    APR-CONTENT-SCOPE-1) — ``visible`` with "every entity" for "at least one". Its own grants
    hold the permission of a step for every entity of the request (REQ-PLT-015: the approver
    sees what they approve); or it reads the subject in full in its OWN right
    (``_own_scope_covers``; rev 1.319) and it prepared the request, decided it, or ONE
    delegation holds the permission of a step for every entity of the request. The content is
    what the request puts in force: the summary, which names the record, the amount and the
    flags, the impact preview and its file, the attachments and what the deciders wrote. A
    reader ``visible`` lists and this rule does not is shown the header of the request
    (``approval_outs``: ``content_withheld``) — also its preparer: what she reads at the read
    decides, as for every other read, so a preparer whose read permission no longer covers every
    entity of her request is answered its header. The rule is stricter than "listed, and reads
    the subject": a member who reads the request's entities through another role reads no more
    of the request than its step permission covers unless she prepared or decided it, and a
    delegate no more than its delegator. Whoever can decide the request reads its content
    (``engine.can_decide`` asks more). Until rev 1.319 the second half asked the principal's
    entity scope — the union of every role's entities — where it now asks the read."""
    own = authorities[0] if authorities else {}
    clauses = [_step_exists(_held(authority, _entities_covered)) for authority in authorities[1:]]
    if principal.id is not None:
        clauses += [approval_request.c.preparer_id == principal.id, _decided_by(principal.id)]
    through_own_grants = _step_exists(_held(own, _entities_covered))
    if not clauses:
        return through_own_grants
    return or_(through_own_grants, and_(_own_scope_covers(principal), or_(*clauses)))


def shown(
    principal: Principal,
    authorities: Sequence[Mapping[str, Scope]],
    column: ColumnElement[Any],
) -> ColumnElement[Any]:
    """``column`` for the requests whose content the principal reads and NULL for the others:
    what a filter, a search or a sort key of the list reads in place of a content column
    (``CONTENT_COLUMNS``), so that the list cannot be made to tell a member the row withholds —
    a row found by a search on its summary, bracketed by a range on its amount, or ordered by
    it (04 §16.10 rev 1.208; item APR-CONTENT-SCOPE-1)."""
    return case((content_visible(principal, authorities), column), else_=null())


def amount_key(
    principal: Principal, authorities: Sequence[Mapping[str, Scope]]
) -> ColumnElement[Any]:
    """The sort key ``amount`` of ``GET /approvals`` for this reader: the stored functional
    amount where it is answered and NULL where it is withheld, so a withheld row is ordered as
    a request without an amount. ``list_approvals`` selects it; the list kernel orders by it
    and reads the page's last value from it."""
    return shown(principal, authorities, approval_request.c.amount_functional).label(AMOUNT_KEY)


def rejection_reason_shown(principal: Principal, row: Mapping[str, Any]) -> bool:
    """Whether ``principal`` is answered the comment of a REJECTION of the request ``row`` also
    where its content is withheld: it prepared the request (04 §16.10 rev 1.240; item
    APR-REJECTION-REASON-PREPARER-1, the supervisor's ruling of 2026-10-01). A decision's comment
    is content, and a preparer who does not cover every entity of her request reads its header —
    but the comment of a rejection is written to her: the decider covers every entity and
    answers for what it says, and she cannot correct what she is not told. That decision's
    comment alone: no summary beyond the label, no amount, no preview, no attachment, and no
    comment of an approving step. ``engine`` tells her the same in the notification. The
    decision's reason code goes with its comment on her read (rev 1.252; item
    APR-DECISION-CODE-CONTENT-1): the reason of a rejection is the two."""
    return _prepared_by(principal, row)


def submission_shown(principal: Principal, row: Mapping[str, Any]) -> bool:
    """Whether ``principal`` is answered the reason code and the comment the request ``row`` was
    submitted with also where its content is withheld: it prepared the request (04 §16.10 rev
    1.252; item APR-REQUEST-REASON-1, supervisor rulings R-83 (d) and R-104 (a) and the ruling of
    2026-10-01). The two members are content — another reader of the header reads neither — but
    they are the preparer's own words, and she reads what she wrote. Nothing else of the content
    comes with them."""
    return _prepared_by(principal, row)


def _prepared_by(principal: Principal, row: Mapping[str, Any]) -> bool:
    """The principal is the person or the client that prepared the request ``row``. A request
    the SYSTEM principal prepared names no preparer and is nobody's own."""
    return principal.id is not None and row["preparer_id"] == principal.id


def content_readable(
    session: Session,
    principal: Principal,
    authorities: Sequence[Mapping[str, Scope]],
    request_ids: Sequence[UUID],
) -> set[UUID]:
    """The requests of ``request_ids`` whose content the principal reads (``content_visible``),
    in one statement for a page of them."""
    if not request_ids:
        return set()
    return {
        UUID(str(value))
        for value in session.scalars(
            select(approval_request.c.id).where(
                approval_request.c.id.in_(list(request_ids)),
                content_visible(principal, authorities),
            )
        )
    }


def _step_role_held(principal: Principal) -> ColumnElement[bool]:
    """``engine._holds_step_role`` in SQL: the step names no role, or a role the principal holds
    through assignments that cover every entity of the request (04 T-PLT-18 ``required_role_id``).
    A delegation conveys a permission, never a role."""
    held = [
        and_(
            approval_step.c.required_role_id.in_(
                select(role.c.id).where(
                    role.c.tenant_id == approval_step.c.tenant_id, role.c.code == code
                )
            ),
            _entities_covered(scope),
        )
        for code, scope in sorted(principal.role_scopes.items())
    ]
    return or_(approval_step.c.required_role_id.is_(None), *held)


def _assigned(
    principal: Principal, authorities: Sequence[Mapping[str, Scope]]
) -> ColumnElement[bool]:
    if principal.kind is not PrincipalKind.USER or principal.id is None:
        return false()

    def active_step(decidable: ColumnElement[bool]) -> ColumnElement[bool]:
        return _step_exists(
            approval_step.c.step_no == approval_request.c.current_step_no,
            approval_step.c.status == ApprovalStepStatus.ACTIVE.value,
            decidable,
            _step_role_held(principal),
        )

    # ``engine.find_authority``: the principal's own grants ask nothing further; a delegation is
    # taken only by a principal who reads the subject in full in its own right.
    own = authorities[0] if authorities else {}
    decidable = active_step(_held(own, _entities_covered))
    delegated = [_held(authority, _entities_covered) for authority in authorities[1:]]
    if delegated:
        decidable = or_(decidable, and_(_own_scope_covers(principal), active_step(or_(*delegated))))
    return and_(
        approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        decidable,
        or_(
            approval_request.c.preparer_id.is_(None),
            approval_request.c.preparer_id != principal.id,
        ),
        ~_decided_by(principal.id),
    )


def assigned_clause(
    principal: Principal, authorities: Sequence[Mapping[str, Scope]]
) -> ColumnElement[bool]:
    """The SQL part of ``assigned_to_me=true`` as a clause on ``approval_request``: pending
    requests whose active step permission ONE of the principal's ``decision_authorities`` holds
    for every entity of the request — a delegation only where the principal reads the subject in
    full in its own right (``_own_scope_covers``) — whose step role the principal holds, and
    that the principal neither prepared nor decided. ``decidable`` completes it to
    ``can_decide`` (the inbox and the home ``pending_approvals``; BUILD_SPEC RPS-17)."""
    return _assigned(principal, authorities)


def decidable(
    session: Session,
    principal: Principal,
    authorities: Sequence[Mapping[str, Scope]],
    *,
    at: datetime,
    extra: Sequence[ColumnElement[bool]] = (),
) -> list[dict[str, Any]]:
    """The pending requests the principal can decide NOW, oldest first — "Waiting for me" is
    ``can_decide`` (04 §16.10 rev 1.104; supervisor ruling R-64 (4)). ``assigned_clause`` states
    in SQL what the stored columns hold: the step permission through one authority, the step's
    role, the principal's own read of the subject, not the preparer and not an earlier decider. What
    only the subject knows — the deciders it excludes, and its own check of who may give the next
    approval (``SubjectSpec.deciders``; R-92) — what a delegation adds — a delegator who is
    barred while another is not — and what a later step needs — its only decider is kept for it
    (R-66 (7)) — is settled by ``engine.can_decide``, asked for exactly those rows. The inbox
    list, its total and the home count read the same set."""
    rows = [
        dict(row)
        for row in session.execute(
            select(approval_request)
            .where(assigned_clause(principal, authorities), *extra)
            .order_by(approval_request.c.submitted_at, approval_request.c.id)
        ).mappings()
    ]
    delegated = len(authorities) > 1
    stepped = _with_later_steps(session, [row["id"] for row in rows])
    found: list[dict[str, Any]] = []
    for row in rows:
        spec = SUBJECTS.get(ApprovalSubjectType(row["subject_type"]))
        # A subject type without a specification (``subjects.PENDING_SUBJECTS``; no command
        # submits one) is waiting for nobody, as ``engine.can_decide`` answers for it (R-64 (7)
        # (c); item APR-WAITING-SPECLESS-1, supervisor ruling R-87 (3)).
        if spec is None:
            continue
        if (
            delegated
            or spec.excluded_deciders is not None
            or spec.deciders is not None
            or row["id"] in stepped
        ) and not engine.can_decide(session, principal, row, at=at):
            continue
        found.append(row)
    return found


def _with_later_steps(session: Session, request_ids: Sequence[UUID]) -> set[UUID]:
    """The requests of ``request_ids`` that have a step after the active one: the only decider of
    a later step does not decide an earlier one (``engine.can_decide``; R-66 (7))."""
    if not request_ids:
        return set()
    return {
        UUID(str(value))
        for value in session.scalars(
            select(approval_step.c.approval_request_id)
            .select_from(
                approval_step.join(
                    approval_request,
                    and_(
                        approval_request.c.tenant_id == approval_step.c.tenant_id,
                        approval_request.c.id == approval_step.c.approval_request_id,
                    ),
                )
            )
            .where(
                approval_step.c.approval_request_id.in_(list(request_ids)),
                approval_step.c.step_no > approval_request.c.current_step_no,
            )
            .distinct()
        )
    }


def _single(filters: Mapping[str, tuple[str, ...]], name: str) -> str | None:
    values = filters.get(name)
    if values is None:
        return None
    if len(values) != 1:
        raise _invalid(name, f"Send {name} once.")
    return values[0]


def _entity_clause(session: Session, values: Sequence[str]) -> ColumnElement[bool]:
    """``entity`` (API-C-11): each value is an entity id or code; a request of any named entity
    matches, and an unknown code answers 422 ``validation-failed`` ([J] D-88 L7-2-Q-13). Only an
    entity the reader may read filters: an id outside the reader's scope matches nothing, so the
    filter cannot be used to test which other entities a listed request names (REQ-PLT-012)."""
    ids: list[UUID] = []
    codes: list[str] = []
    for value in values:
        try:
            ids.append(UUID(value))
        except ValueError:
            codes.append(value)
    if codes:
        found = {
            str(code): UUID(str(entity_id))
            for code, entity_id in session.execute(
                select(legal_entity.c.code, legal_entity.c.id).where(
                    legal_entity.c.code.in_(sorted(set(codes)))
                )
            ).tuples()
        }
        if any(code not in found for code in codes):
            raise Problem(
                "validation-failed",
                errors=[
                    ProblemError(field=ENTITY, rule_id=CONTEXT_RULE_ID, message=UNKNOWN_ENTITY)
                ],
            )
        ids.extend(found[code] for code in codes)
    wanted = list(dict.fromkeys(ids))
    readable = {
        UUID(str(value))
        for value in session.scalars(select(legal_entity.c.id).where(legal_entity.c.id.in_(wanted)))
    }
    clauses = [gates.request_of_entity(entity_id) for entity_id in wanted if entity_id in readable]
    return or_(*clauses) if clauses else false()


def _custom_clauses(
    session: Session,
    principal: Principal,
    authorities: Sequence[Mapping[str, Scope]],
    filters: Mapping[str, tuple[str, ...]],
    *,
    at: datetime,
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    entities = filters.get(ENTITY)
    if entities:
        clauses.append(_entity_clause(session, entities))
    assigned = _single(filters, ASSIGNED_TO_ME)
    if assigned is not None:
        if assigned not in {"true", "false"}:
            raise _invalid(ASSIGNED_TO_ME, "assigned_to_me must be true or false.")
        if assigned == "true":
            ids = [row["id"] for row in decidable(session, principal, authorities, at=at)]
            clauses.append(approval_request.c.id.in_(ids) if ids else false())
    preparer = _single(filters, PREPARER)
    if preparer is not None:
        user_id: Any = principal.id
        if preparer != PREPARER_ME:
            try:
                membership_id = UUID(preparer)
            except ValueError:
                raise _invalid(PREPARER, "preparer must be me or a membership id.") from None
            user_id = session.execute(
                select(tenant_membership.c.user_id).where(
                    of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id
                )
            ).scalar_one_or_none()
        clauses.append(false() if user_id is None else approval_request.c.preparer_id == user_id)
    return clauses


def list_approvals[P: Page](
    ctx: RequestContext,
    *,
    filters: Mapping[str, tuple[str, ...]],
    page: Callable[[Session, Select[Any], ColumnElement[Any]], P],
    files: FileStore,
    keyring: KeyRing,
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the visible requests; ``page`` applies the list parameters (DG-LST) and is
    handed the reader's own ``amount`` sort key (``amount_key``), which the statement selects."""
    principal = ctx.principal
    with tenant_session(principal.db_context, read_only=True) as session:
        authorities = decision_authorities(session, principal, at=ctx.now)
        amount = amount_key(principal, authorities)
        statement = select(approval_request, amount).where(
            visible(principal, authorities),
            *_custom_clauses(session, principal, authorities, filters, at=ctx.now),
        )
        result = page(session, statement, amount)
        items = approval_outs(
            session,
            principal,
            result.items,
            at=ctx.now,
            files=files,
            keyring=keyring,
            authorities=authorities,
        )
        return result, items


def get_approval(
    ctx: RequestContext, approval_request_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    """API-S-Approval of a visible request; 404 ``not-found`` otherwise."""
    principal = ctx.principal
    with tenant_session(principal.db_context, read_only=True) as session:
        authorities = decision_authorities(session, principal, at=ctx.now)
        row = (
            session.execute(
                select(approval_request).where(
                    approval_request.c.id == approval_request_id, visible(principal, authorities)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem("not-found")
        return approval_outs(
            session,
            principal,
            [dict(row)],
            at=ctx.now,
            files=files,
            keyring=keyring,
            authorities=authorities,
        )[0]


def request_out(uow: UnitOfWork, approval_request_id: UUID) -> dict[str, Any]:
    """API-S-Approval of a request the command just decided, in the command's transaction."""
    row = (
        uow.session.execute(
            select(approval_request).where(approval_request.c.id == approval_request_id)
        )
        .mappings()
        .one()
    )
    return approval_outs(
        uow.session, uow.principal, [dict(row)], at=uow.now, files=uow.files, keyring=uow.keyring
    )[0]


def request_row(uow: UnitOfWork, approval_request_id: UUID) -> Mapping[str, Any]:
    """The request row a decision acts on; 404 ``not-found`` when it is not visible."""
    row = (
        uow.session.execute(
            select(approval_request).where(approval_request.c.id == approval_request_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def display_names(session: Session, user_ids: Iterable[UUID | None]) -> dict[UUID, str]:
    ids = sorted({user_id for user_id in user_ids if user_id is not None})
    if not ids:
        return {}
    return {
        UUID(str(user_id)): str(name)
        for user_id, name in session.execute(
            select(app_user.c.id, app_user.c.display_name).where(app_user.c.id.in_(ids))
        ).tuples()
    }


def actor(user_id: UUID | None, kind: str, names: Mapping[UUID, str]) -> dict[str, Any]:
    """API-S-Actor; SYSTEM and unknown principals show the system name."""
    display = SYSTEM_DISPLAY_NAME if user_id is None else names.get(user_id, SYSTEM_DISPLAY_NAME)
    return {"id": user_id, "kind": kind, "display_name": display}


def _entity_refs(session: Session, rows: Sequence[Mapping[str, Any]]) -> dict[UUID, dict[str, Any]]:
    """API-S-Ref {id, code, name} of each entity the rows name — alone (``entity_id``) or among
    several (``entity_ids``) — read from ``legal_entity``, whose RLS-TE shows the reader the
    entities of its own scope only."""
    ids = sorted({entity_id for row in rows for entity_id in engine.request_entities(row).ids})
    if not ids:
        return {}
    return {
        UUID(str(entity_id)): {"id": entity_id, "code": code, "name": name}
        for entity_id, code, name in session.execute(
            select(legal_entity.c.id, legal_entity.c.code, legal_entity.c.name).where(
                legal_entity.c.id.in_(ids)
            )
        ).tuples()
    }


def _entity_ref(
    refs: Mapping[UUID, dict[str, Any]], entity_id: UUID | None
) -> dict[str, Any] | None:
    """API-S-Approval ``entity``: the request's entity as API-S-Ref, or None when the request names
    no entity ([J] D-88 L7-2-Q-13)."""
    if entity_id is None:
        return None
    return refs.get(UUID(str(entity_id)))


def _entity_list(
    refs: Mapping[UUID, dict[str, Any]], entities: SubjectEntities
) -> list[dict[str, Any]]:
    """API-S-Approval ``entities`` (rev 1.104; R-41 (8)): the entities the request names that the
    reader may read, by code. ``entity_count`` states how many it names in all."""
    found = [refs[entity_id] for entity_id in entities.ids if entity_id in refs]
    return sorted(found, key=lambda ref: (str(ref["code"]), str(ref["id"])))


def _subject_href(session: Session, row: Mapping[str, Any]) -> str | None:
    """API-S-Approval ``subject.href``: the covered table's link when a covered table holds the
    subject ([J] D-88 L7-2-Q-7), else the spec's route, else None."""
    covered = covered_link(session, row["subject_type"], row["subject_id"])
    if covered is not None:
        return covered
    spec = SUBJECTS.get(ApprovalSubjectType(row["subject_type"]))
    if spec is None or spec.link_path is None:
        return None
    return spec.link_path(row["subject_id"])


def _impact_preview(
    session: Session, row: Mapping[str, Any], *, files: FileStore, keyring: KeyRing
) -> dict[str, Any] | None:
    file_id = row["impact_preview_file_id"]
    if file_id is None:
        return None
    _, stream = open_file(session, file_id, files=files, keyring=keyring)
    with stream:
        document = json.loads(stream.read(), parse_float=Decimal)
    summary = {name: (document.get(side) or {}).get(key) for name, side, key in SUMMARY_FIELDS}
    return {"file_id": file_id, "sha256": row["impact_preview_sha256"], "summary": summary}


def _decision_out(
    decision: Mapping[str, Any], names: Mapping[UUID, str], *, written: bool
) -> dict[str, Any]:
    """One decision of API-S-Approval. Who gave it, on whose behalf, when, which it is and the
    key of the rule behind an automatic one are of the header. ``comment`` and ``reason_code``
    are the decider's own words — the code is free text of up to 100 characters, bound to no
    code table — so both are content, answered only where ``written`` says so (04 §16.10 rev
    1.252; item APR-DECISION-CODE-CONTENT-1, the supervisor's ruling of 2026-10-01: until then
    the code was answered to every reader of the header, a second channel beside the comment)."""
    return {
        "id": decision["id"],
        "decision": decision["decision"],
        "approver": actor(decision["approver_id"], str(decision["approver_kind"]), names),
        "on_behalf_of": None
        if decision["on_behalf_of_id"] is None
        else actor(decision["on_behalf_of_id"], PrincipalKind.USER.value, names),
        "decided_at": decision["decided_at"],
        "comment": decision["comment"] if written else None,
        "reason_code": decision["reason_code"] if written else None,
        "auto_rule_key": decision["auto_rule_key"],
    }


def _reopen_evidence(session: Session, visible_requests: set[UUID]) -> dict[UUID, dict[str, Any]]:
    """The submitted citation, never the period's possibly newer pending request's evidence."""
    if not visible_requests:
        return {}
    found = {}
    for row in session.execute(
        select(audit_event.c.approval_request_id, audit_event.c.after).where(
            audit_event.c.approval_request_id.in_(visible_requests),
            audit_event.c.action == "period.request_reopen",
        )
    ):
        basis = (row.after or {}).get("judgement")
        if basis is not None:
            found[row.approval_request_id] = basis
    names = display_names(session, [UUID(basis["reviewer_id"]) for basis in found.values()])
    return {
        request_id: {
            "id": basis["id"],
            "judgement_no": basis["content"]["judgement_no"],
            "contract_id": basis["content"]["contract_id"],
            "conclusion": basis["content"]["conclusion"],
            "rationale": basis["content"]["rationale"],
            "reviewer": actor(UUID(basis["reviewer_id"]), "USER", names),
            "reviewed_at": basis["reviewed_at"],
        }
        for request_id, basis in found.items()
    }


def approval_outs(
    session: Session,
    principal: Principal,
    rows: Sequence[Mapping[str, Any]],
    *,
    at: datetime,
    files: FileStore,
    keyring: KeyRing,
    authorities: Sequence[Mapping[str, Scope]] | None = None,
) -> list[dict[str, Any]]:
    """API-S-Approval of each request row, loading steps, decisions, names and attachments once.

    A request whose content the principal does not read (``content_visible``) answers its
    header and ``content_withheld`` (04 §16.10 rev 1.208; item APR-CONTENT-SCOPE-1): the summary
    and ``subject.display`` read the subject type's name and the request's number
    (``withheld_summary``), ``amount`` and ``impact_preview`` are null, ``flags`` and
    ``attachments`` are empty and no decision carries its comment or its reason code
    (``_decision_out``). Its preview file is not opened and its attachments are not read. One
    comment is answered all the same (rev 1.240; item APR-REJECTION-REASON-PREPARER-1): the
    comment of a REJECTION, with its reason code, to the preparer of the request — it is
    written to her, and she cannot correct what she is not told. The answer stays a header,
    with ``content_withheld`` true.

    ``reason_code`` and ``comment`` are what the request was submitted with (T-PLT-17; rev 1.252,
    item APR-REQUEST-REASON-1). Both are content, so a withheld answer carries null for them —
    except to the preparer, who reads the two she wrote (``submission_shown``).

    ``authorities`` are the principal's ``decision_authorities`` when the caller has read them
    already."""
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    if authorities is None:
        authorities = decision_authorities(session, principal, at=at)
    whole = content_readable(session, principal, authorities, ids)
    steps: dict[UUID, list[Mapping[str, Any]]] = {}
    for step in session.execute(
        select(approval_step)
        .where(approval_step.c.approval_request_id.in_(ids))
        .order_by(approval_step.c.approval_request_id, approval_step.c.step_no)
    ).mappings():
        steps.setdefault(step["approval_request_id"], []).append(dict(step))
    decisions: dict[UUID, list[Mapping[str, Any]]] = {}
    for decision in session.execute(
        select(approval_decision, rule.c.rule_key.label("auto_rule_key"))
        .select_from(
            approval_decision.outerjoin(
                rule,
                and_(
                    rule.c.tenant_id == approval_decision.c.tenant_id,
                    rule.c.id == approval_decision.c.auto_rule_id,
                ),
            )
        )
        .where(approval_decision.c.approval_request_id.in_(ids))
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    ).mappings():
        decisions.setdefault(decision["approval_step_id"], []).append(dict(decision))
    routing_ids = sorted({row["routing_rule_id"] for row in rows if row["routing_rule_id"]})
    rule_keys: dict[Any, str] = (
        {
            rule_id: str(key)
            for rule_id, key in session.execute(
                select(rule.c.id, rule.c.rule_key).where(rule.c.id.in_(routing_ids))
            ).tuples()
        }
        if routing_ids
        else {}
    )
    names = display_names(
        session,
        [row["preparer_id"] for row in rows]
        + [
            user
            for items in decisions.values()
            for item in items
            for user in (item["approver_id"], item["on_behalf_of_id"])
        ],
    )
    attachments: dict[UUID, list[dict[str, Any]]] = {}
    for item in session.execute(
        select(
            file_attachment.c.subject_id,
            file_attachment.c.file_object_id,
            file_object.c.original_filename,
        )
        .select_from(
            file_attachment.join(
                file_object,
                and_(
                    file_object.c.tenant_id == file_attachment.c.tenant_id,
                    file_object.c.id == file_attachment.c.file_object_id,
                ),
            )
        )
        .where(
            file_attachment.c.subject_type == ATTACHMENT_SUBJECT,
            file_attachment.c.subject_id.in_(sorted(whole)),
            file_attachment.c.voided_at.is_(None),
        )
        .order_by(file_attachment.c.created_at, file_attachment.c.id)
    ):
        attachments.setdefault(item.subject_id, []).append(
            {"file_id": item.file_object_id, "original_filename": item.original_filename}
        )
    entities = _entity_refs(session, rows)
    reopen_evidence = _reopen_evidence(
        session,
        {
            UUID(str(row["id"]))
            for row in rows
            if row["id"] in whole and row["subject_type"] == ApprovalSubjectType.PERIOD_REOPEN.value
        },
    )
    outs: list[dict[str, Any]] = []
    for row in rows:
        answered = row["id"] in whole
        told_why = rejection_reason_shown(principal, row)
        submitted = answered or submission_shown(principal, row)
        amount = row["amount_functional"] if answered else None
        summary = (
            row["summary"] if answered else withheld_summary(row["subject_type"], row["request_no"])
        )
        outs.append(
            {
                "id": row["id"],
                "request_no": row["request_no"],
                "subject": {
                    "type": row["subject_type"],
                    "id": row["subject_id"],
                    "display": summary,
                    "href": _subject_href(session, row),
                    "content_sha256": row["subject_content_sha256"],
                    "row_version": row["subject_row_version"],
                },
                "summary": summary,
                "reopen_judgement": reopen_evidence.get(row["id"]) if answered else None,
                "status": row["status"],
                "entity": _entity_ref(entities, row["entity_id"]),
                "entities": _entity_list(entities, engine.request_entities(row)),
                "entity_count": len(engine.request_entities(row).ids),
                "all_entities": bool(row["is_all_entities"]),
                "amount": None
                if amount is None
                else money_out(Decimal(amount), str(row["amount_currency"]), ISO_4217),
                "flags": list(row["flags"]) if answered else [],
                "routing": {
                    "rule_set_version_id": row["routing_rule_set_version_id"],
                    "rule_key": rule_keys.get(row["routing_rule_id"]),
                },
                "preparer": actor(row["preparer_id"], str(row["preparer_kind"]), names),
                "submitted_at": row["submitted_at"],
                "reason_code": row["reason_code"] if submitted else None,
                "comment": row["comment"] if submitted else None,
                "decided_at": row["decided_at"],
                "voided_at": row["voided_at"],
                "void_reason": row["void_reason"],
                "current_step_no": row["current_step_no"],
                "steps": [
                    {
                        "step_no": step["step_no"],
                        "name": step["name"],
                        "required_permission": step["required_permission"],
                        "min_approvers": step["min_approvers"],
                        "status": step["status"],
                        "decisions": [
                            _decision_out(
                                decision,
                                names,
                                written=answered
                                or (
                                    told_why
                                    and decision["decision"] == ApprovalDecisionKind.REJECT.value
                                ),
                            )
                            for decision in decisions.get(step["id"], [])
                        ],
                    }
                    for step in steps.get(row["id"], [])
                ],
                "impact_preview": _impact_preview(session, row, files=files, keyring=keyring)
                if answered
                else None,
                "attachments": attachments.get(row["id"], []),
                "can_decide": engine.can_decide(session, principal, row, at=at),
                "content_withheld": not answered,
            }
        )
    return outs
