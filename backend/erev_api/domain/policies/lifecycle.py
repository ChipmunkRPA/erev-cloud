"""Configuration lifecycle of IM-P versions (04 §1.5 IM-P, E-12, §14.1 DB-03, DB-04, DB-10; PRD
SM-04, BR-PLT-04; dev-guide DG-SM-01 to DG-SM-03, DG-KRN-APR-01, DG-KRN-APR-02; REQ-POL-003;
BUILD_SPEC RFD-5).

``ConfigVersionKind`` describes one IM-P version table and its content. ``transition`` moves a
locked version along an E-12 pair, refuses any other pair in Python first (409
``invalid-transition``, rule DB-03) and audits ``<table>.<status lowercase>`` with the before and
after status (DG-SM-03); DB-04 enforces the same pairs in the database.

- ``mark_tested``: DRAFT → TESTED with the content hash the passing example cases ran against.
- ``submit``: TESTED → SUBMITTED once the evidence is current, then one approval request of the
  kind's E-08 subject type.
- ``approve`` (``SubjectSpec.on_approved``): SUBMITTED → APPROVED under the approved request, then
  ``publish`` in the same transaction (04 §16.5 publish note; SCREENS §11.0 Publication).
- ``publish``: APPROVED → PUBLISHED after the kind's publication checks. The PUBLISHED version of
  the same scope becomes SUPERSEDED first, with ``effective_to`` equal to the new version's
  ``effective_from`` (the publication instant when that is null); ranges are half-open
  ``[effective_from, effective_to)`` as in the DB-04 overlap check and D-80.
- ``close``: SUBMITTED → REJECTED or WITHDRAWN (``on_rejected``, ``on_voided``); ``reopen`` returns
  either to DRAFT for a new edit round (E-12).
- ``effective_errors`` (PRD ERR-75; 03 REQ-POL-007; 04 §16.5 "Effective date of a superseding
  version"; supervisor ruling R-113 (b)): a version that supersedes a PUBLISHED one never takes
  effect where a computation or an act has already chosen. ``ConfigVersionKind.chosen_by`` names
  how the versions of the kind are chosen. ``BY_DATE`` — the engine chooses by a contract date
  (obligation templates; the POB_ASSIGNMENT and SSP_ASSIGNMENT rule sets): the version needs an
  effective date, and the UTC date of ``effective_from`` is later than today's date in every active
  entity's time zone, so a contract dated up to today never meets it. ``BY_INSTANT`` — chosen at
  the instant of a computation or of an act (registry versions; the rule sets the platform reads):
  ``effective_from`` is null or not earlier than the instant of the check, so no past instant
  changes its answer. Checked by ``submit`` and again by ``publish``, the decision's transaction:
  a refusal there rolls the decision back and the request stays PENDING. The message is the
  problem's ``detail`` too (``invalid``), which is what the editors and the approval screen
  print. A first version of its scope keeps a free date, and a kind without ``chosen_by`` (a
  version named by id) is not checked. Before the workspace's first legal entity (PRD ERR-75 rev
  1.178; item PINP-PERIOD-VALUE-1, supervisor ruling of 2026-10-01) nothing has been computed, so
  a version whose readers all act on a legal entity's data (``ConfigVersionKind.entity_bound``: a
  registry version of an accounting category) may supersede with an effective date that has
  passed — a tenant that migrates dates its policies at the first day of its history. The
  condition is read by each check, the decision's included.

[J] E-12 and DB-04 have no TESTED → DRAFT pair, so an edit of a TESTED version keeps TESTED and
``submit`` refuses a version whose content differs from the hash its tests recorded (L1-4-Q-4).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import RowMapping, Table, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.clock import to_entity_date
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import approval_decision, legal_entity
from erev_api.enums import ApprovalDecisionKind, ApprovalSubjectType, ConfigStatus
from erev_api.problems import Problem, ProblemError
from erev_api.registry.platform import HUMAN_APPROVAL_REQUIRED

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

DRAFT: Final = ConfigStatus.DRAFT.value
TESTED: Final = ConfigStatus.TESTED.value
SUBMITTED: Final = ConfigStatus.SUBMITTED.value
APPROVED: Final = ConfigStatus.APPROVED.value
PUBLISHED: Final = ConfigStatus.PUBLISHED.value
# 04 E-12 configuration pairs; DB-04 installs the same list (`migration_ops.CONFIG_STATUS_PAIRS`).
STATUS_PAIRS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        (DRAFT, TESTED),
        (TESTED, SUBMITTED),
        (SUBMITTED, APPROVED),
        (SUBMITTED, ConfigStatus.REJECTED.value),
        (SUBMITTED, ConfigStatus.WITHDRAWN.value),
        (APPROVED, PUBLISHED),
        (PUBLISHED, ConfigStatus.SUPERSEDED.value),
        (ConfigStatus.REJECTED.value, DRAFT),
        (ConfigStatus.WITHDRAWN.value, DRAFT),
    }
)
EDITABLE: Final = frozenset({DRAFT, TESTED})
REOPENABLE: Final = frozenset({ConfigStatus.REJECTED.value, ConfigStatus.WITHDRAWN.value})
OPEN: Final = frozenset({DRAFT, TESTED, SUBMITTED, APPROVED})
RULE_TRANSITION: Final = "DB-03"
RULE_FROZEN: Final = "DB-04"
RULE_LIFECYCLE: Final = "REQ-POL-003"
RULE_OPEN_VERSION: Final = "SM-04"
RULE_PROSPECTIVE: Final = "REQ-POL-007"  # PRD ERR-75
BY_DATE: Final = "DATE"  # the engine chooses the version by a contract date
BY_INSTANT: Final = "INSTANT"  # chosen at the instant of a computation or of an act
# [J] Copy the documents leave open; the author notice is SCREENS §11.0.
TRANSITION_REFUSED: Final = "A {current} version cannot become {target}."
NOT_TESTED: Final = "Run the tests of this version before submitting it."
CONTENT_CHANGED: Final = "This version changed after its tests ran. Run the tests again."
NOT_SUBMITTED: Final = "Only a submitted version can be approved."
NOT_APPROVED: Final = "Only an approved version can be published."
FROZEN: Final = "This version is no longer a draft, so it cannot change."
VERSION_OPEN: Final = "Another version is open. Finish it or withdraw it first."
EFFECTIVE_ORDER: Final = "Choose an effective date after that of the published version."
# PRD §5.5 ERR-75, the date form and the instant form.
EFFECTIVE_DATE_PASSED: Final = (
    "This version replaces a published one. Choose an effective date later than today."
)
EFFECTIVE_INSTANT_PASSED: Final = (
    "This version replaces a published one. Choose an effective time that has not passed."
)
AUTHOR_DETAIL: Final = (
    "You authored this version. Another user with configuration approval must approve it."
)


def _named(_version: Mapping[str, Any]) -> str | None:
    """A version that is named by id wherever it is used: no effective-date rule."""
    return None


def _unbound(_version: Mapping[str, Any]) -> bool:
    """A version that an act may read before the workspace has a legal entity."""
    return False


@dataclass(frozen=True, slots=True)
class ConfigVersionKind:
    """One IM-P version table.

    ``scope_columns`` name the versions that supersede each other; ``content`` is the hashed content
    (SC-V ``content_sha256`` and the approval subject content); ``snapshot`` the field-level
    ``before`` and ``after`` of publication audits; ``submit_errors`` the missing test evidence;
    ``publish_errors`` the publication checks; ``summary`` names the version in its request;
    ``chosen_by`` answers ``BY_DATE``, ``BY_INSTANT`` or None for a version (``effective_errors``);
    ``entity_bound`` answers whether every reader that chooses the version acts on a legal
    entity's data, so that nothing can have chosen while the workspace has none.
    ``serialise`` takes the lock under which the kind's create decides that no other version of
    the scope is open (PRD SM-04), for ``reopen``: an advisory lock where the create takes one
    and reads the versions without locking them (registry versions per scope key, account mapping
    versions per tenant, import mapping profile versions per code). A kind whose create locks
    every version row of the scope — rule set and obligation template versions — sets none: the
    row lock of the version being reopened, which every caller of ``reopen`` holds, is one of the
    rows the create waits for, and taking the parent's row here would invert the create's order.
    ``restate`` answers the columns a kind rewrites when a version becomes a DRAFT again, for a
    kind whose submitted row is not what its draft holds: a registry version, whose submit
    replaces the author's statement by the whole value set (04 T-PLT-32).
    ``reopenable`` raises the kind's own refusal of a reopening, under the ``serialise`` lock: a
    registry version whose predecessor is no longer the PUBLISHED version of its key (PRD ERR-92).
    ``reopen`` asks it before the look for an open version and again after it.
    """

    table: Table
    subject_type: ApprovalSubjectType
    scope_columns: tuple[str, ...]
    content: Callable[[Session, UUID], Mapping[str, Any]]
    snapshot: Callable[[Session, UUID], Mapping[str, Any]]
    submit_errors: Callable[[Session, Mapping[str, Any]], list[ProblemError]]
    publish_errors: Callable[[Session, Mapping[str, Any]], list[ProblemError]]
    summary: Callable[[Session, Mapping[str, Any]], str]
    chosen_by: Callable[[Mapping[str, Any]], str | None] = _named
    entity_bound: Callable[[Mapping[str, Any]], bool] = _unbound
    serialise: Callable[[UnitOfWork, Mapping[str, Any]], None] | None = None
    restate: Callable[[UnitOfWork, Mapping[str, Any]], Mapping[str, Any]] | None = None
    reopenable: Callable[[UnitOfWork, Mapping[str, Any]], None] | None = None

    @property
    def object_type(self) -> str:
        return self.table.name


def refused(message: str, *, rule_id: str = RULE_TRANSITION) -> Problem:
    """409 ``invalid-transition`` on the version status (DG-SM-02)."""
    return Problem(
        "invalid-transition",
        errors=[ProblemError(field="status", rule_id=rule_id, message=message)],
    )


def invalid(errors: list[ProblemError]) -> Problem:
    """422 ``validation-failed`` with the findings. The refusal of PRD ERR-75 is the ``detail`` as
    well: the version editors and the approval screen print a problem's detail, and the approver
    has no effective-date field to read the message on."""
    detail = next((error.message for error in errors if error.rule_id == RULE_PROSPECTIVE), None)
    return Problem("validation-failed", detail, errors=errors)


def lock(session: Session, kind: ConfigVersionKind, version_id: UUID) -> Mapping[str, Any]:
    """The version row under ``FOR UPDATE``; 404 when it is not visible."""
    table = kind.table
    row = (
        session.execute(select(table).where(table.c.id == version_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def current_sha256(session: Session, kind: ConfigVersionKind, version_id: UUID) -> str:
    """The hash of the version's content now (04 §1.3 SC-V; DG-KRN-APR-01)."""
    return sha256_hex(kind.content(session, version_id))


def transition(
    uow: UnitOfWork,
    kind: ConfigVersionKind,
    version: Mapping[str, Any],
    to_status: ConfigStatus,
    *,
    values: Mapping[str, Any] | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    detail: Mapping[str, Any] | None = None,
    comment: str | None = None,
    approval_request_id: UUID | None = None,
) -> Mapping[str, Any]:
    """Move ``version`` to ``to_status`` along an E-12 pair and audit it (DG-SM-02, DG-SM-03)."""
    current = str(version["status"])
    if (current, to_status.value) not in STATUS_PAIRS:
        raise refused(TRANSITION_REFUSED.format(current=current, target=to_status.value))
    table = kind.table
    principal = uow.principal
    changes = dict(values or {})
    uow.session.execute(
        update(table)
        .where(table.c.id == version["id"], table.c.status == current)
        .values(
            status=to_status.value,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            **changes,
        )
    )
    uow.audit(
        action=f"{kind.object_type}.{to_status.value.lower()}",
        object_type=kind.object_type,
        object_id=version["id"],
        before={"status": current, **(before or {})},
        after={"status": to_status.value, **(after or {})},
        detail=detail,
        comment=comment,
        approval_request_id=approval_request_id,
    )
    return MappingProxyType({**version, **changes, "status": to_status.value})


def _open_elsewhere(session: Session, kind: ConfigVersionKind, version: Mapping[str, Any]) -> bool:
    table = kind.table
    found = session.execute(
        select(table.c.id).where(
            table.c.id != version["id"],
            table.c.status.in_(sorted(OPEN)),
            *(table.c[column] == version[column] for column in kind.scope_columns),
        )
    ).first()
    return found is not None


def reopen(
    uow: UnitOfWork, kind: ConfigVersionKind, version: Mapping[str, Any]
) -> Mapping[str, Any]:
    """REJECTED or WITHDRAWN → DRAFT for a new edit round (E-12); 409 ``invalid-transition`` while
    another version of the scope is open. The kind's ``serialise`` lock is taken first: a create
    of the same scope that has not committed is waited for, never missed (supervisor ruling of
    2026-10-01 on the pre-build line of item REG-VERSION-WHOLE-SET-1, point E). Under it the
    kind's ``reopenable`` raises its own refusal, twice. Before the look for an open version: a
    version that can never be reopened is not told to wait for another one. And after it, which
    is the answer that stands: a publication takes no such lock and may commit between the first
    read and the look, but with the lock held and no version of the scope open, none can be
    published before this transaction ends. The kind's ``restate`` columns are written with the
    draft's: the row is a draft's again."""
    if kind.serialise is not None:
        kind.serialise(uow, version)
    if kind.reopenable is not None:
        kind.reopenable(uow, version)
    if _open_elsewhere(uow.session, kind, version):
        raise refused(VERSION_OPEN, rule_id=RULE_OPEN_VERSION)
    if kind.reopenable is not None:
        kind.reopenable(uow, version)
    reopened = transition(uow, kind, version, ConfigStatus.DRAFT)
    table = kind.table
    # A DRAFT version carries no content hash and no request; DB-04 lets every column change now.
    columns: dict[str, Any] = {"content_sha256": None, "approval_request_id": None}
    if kind.restate is not None:
        columns.update(kind.restate(uow, reopened))
    uow.session.execute(update(table).where(table.c.id == version["id"]).values(**columns))
    return MappingProxyType({**reopened, **columns})


def require_editable(
    uow: UnitOfWork, kind: ConfigVersionKind, version: Mapping[str, Any]
) -> Mapping[str, Any]:
    """The version ready to change: DRAFT and TESTED as they are, REJECTED and WITHDRAWN reopened;
    otherwise 409 ``configuration-frozen`` (DB-04; PRD ERR-09)."""
    status = version["status"]
    if status in EDITABLE:
        return version
    if status in REOPENABLE:
        return reopen(uow, kind, version)
    raise Problem(
        "configuration-frozen",
        errors=[ProblemError(field="status", rule_id=RULE_FROZEN, message=FROZEN)],
    )


def mark_tested(
    uow: UnitOfWork,
    kind: ConfigVersionKind,
    version: Mapping[str, Any],
    *,
    content_sha256: str,
    detail: Mapping[str, Any],
) -> Mapping[str, Any]:
    """DRAFT → TESTED with the content hash the passing cases ran against. A TESTED version, which
    has no way back to DRAFT, records the hash of its new run instead."""
    if version["status"] == DRAFT:
        return transition(
            uow,
            kind,
            version,
            ConfigStatus.TESTED,
            values={"content_sha256": content_sha256},
            after={"content_sha256": content_sha256},
            detail=detail,
        )
    if version["status"] != TESTED:
        raise refused(TRANSITION_REFUSED.format(current=version["status"], target=TESTED))
    table = kind.table
    principal = uow.principal
    uow.session.execute(
        update(table)
        .where(table.c.id == version["id"])
        .values(
            content_sha256=content_sha256,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=f"{kind.object_type}.test",
        object_type=kind.object_type,
        object_id=version["id"],
        before={"content_sha256": version["content_sha256"]},
        after={"content_sha256": content_sha256},
        detail=detail,
    )
    return MappingProxyType({**version, "content_sha256": content_sha256})


def published_of_scope(
    session: Session, kind: ConfigVersionKind, version: Mapping[str, Any], *, for_update: bool
) -> RowMapping | None:
    """The PUBLISHED version of the scope of ``version``, other than itself."""
    table = kind.table
    statement = select(table).where(
        table.c.id != version["id"],
        table.c.status == PUBLISHED,
        *(table.c[column] == version[column] for column in kind.scope_columns),
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).mappings().one_or_none()


def latest_entity_date(session: Session, now: datetime) -> date:
    """Today's date in the active entity whose day is furthest ahead; the UTC date without one."""
    zones = session.execute(
        select(legal_entity.c.time_zone).where(legal_entity.c.is_active.is_(True))
    ).scalars()
    return max(
        (to_entity_date(now, str(zone)) for zone in zones), default=now.astimezone(UTC).date()
    )


def has_legal_entity(session: Session) -> bool:
    """Whether the workspace has a legal entity, active or not. Before the first one no contract,
    period state, journal or report exists, so no computation and no act on an entity's data
    can have chosen a version (PRD ERR-75 rev 1.178). ``legal_entity`` is RLS-TE: the fact is the
    tenant's, whoever submits or decides, so it is read under the tenant's scope (DG-KRN-DB-05).
    The read answers a truth value and shows the caller no row."""
    with system_entity_scope(session):
        return session.execute(select(legal_entity.c.id).limit(1)).first() is not None


def effective_errors(
    session: Session,
    kind: ConfigVersionKind,
    version: Mapping[str, Any],
    *,
    supersedes: bool,
    now: datetime,
) -> list[ProblemError]:
    """PRD ERR-75 for a version that supersedes a PUBLISHED one (module docstring)."""
    form = kind.chosen_by(version)
    if form is None or not supersedes:
        return []
    effective_from: datetime | None = version["effective_from"]
    if form == BY_DATE:
        today = latest_entity_date(session, now)
        late_enough = effective_from is not None and effective_from.astimezone(UTC).date() > today
        message = EFFECTIVE_DATE_PASSED
    else:
        late_enough = effective_from is None or effective_from >= now
        message = EFFECTIVE_INSTANT_PASSED
    if late_enough:
        return []
    if kind.entity_bound(version) and not has_legal_entity(session):
        return []  # before the first legal entity nothing can have chosen (rev 1.178)
    return [ProblemError(field="effective_from", rule_id=RULE_PROSPECTIVE, message=message)]


def human_approval_required(changes: Mapping[str, Any] | None) -> bool:
    """Ruling D-98 candidate 86 under the whole value set (04 T-PLT-32; the supervisor's ruling of
    2026-10-01 on the independent review of item REG-VERSION-WHOLE-SET-1): a version that CHANGES a
    parameter of ``registry.platform.HUMAN_APPROVAL_REQUIRED`` — states it for the first time,
    changes it or returns it to the default — is never auto-approved: ``submit`` withholds the
    ``AUTO_APPROVAL`` rules so its CFG approval waits for a named human approver. ``changes`` is
    the difference a version's submit records (``added``, ``changed``, ``returned_to_default``, by
    code); a kind that records none changes no such parameter. A version that only carries the
    parameter forward changes nothing of it: the keys of its set do not decide."""
    if not isinstance(changes, Mapping):
        return False
    touched = {str(code) for codes in changes.values() for code in codes}
    return bool(touched & HUMAN_APPROVAL_REQUIRED)


def submit(
    uow: UnitOfWork,
    kind: ConfigVersionKind,
    version: Mapping[str, Any],
    *,
    comment: str | None,
    attach: Callable[[Mapping[str, Any]], tuple[Mapping[str, Any], Mapping[str, Any]]]
    | None = None,
) -> Mapping[str, Any]:
    """TESTED → SUBMITTED and one approval request; returns the request (DG-KRN-APR-01).

    409 ``invalid-transition`` with rule DB-03 unless the version is TESTED, and with rule
    REQ-POL-003 when its content changed after the tests ran or its evidence is incomplete; 422
    ``validation-failed`` for the effective date of a superseding version (PRD ERR-75).
    ``attach`` runs after these checks and returns the column values and audit detail it adds.
    A matching ``AUTO_APPROVAL`` rule approves and publishes the version before this returns.
    """
    if version["status"] != TESTED:
        raise refused(NOT_TESTED)
    session = uow.session
    if version["content_sha256"] != current_sha256(session, kind, version["id"]):
        raise refused(CONTENT_CHANGED, rule_id=RULE_LIFECYCLE)
    errors = kind.submit_errors(session, version)
    if errors:
        raise Problem("invalid-transition", errors=errors)
    if kind.chosen_by(version) is not None:
        # Only a kind the effective-date rule applies to is asked for the version it supersedes: a
        # scope of a kind without the rule may hold several PUBLISHED versions side by side — an
        # account mapping's effective-dated versions — and has no single "published of scope".
        prior = published_of_scope(session, kind, version, for_update=False)
        errors = effective_errors(session, kind, version, supersedes=prior is not None, now=uow.now)
        if errors:
            raise invalid(errors)
    values, detail = attach(version) if attach is not None else ({}, {})
    transition(
        uow,
        kind,
        version,
        ConfigStatus.SUBMITTED,
        values=values,
        after=values,
        detail=detail,
        comment=comment,
    )
    request = approvals.submit(
        uow,
        subject_type=kind.subject_type,
        subject_id=version["id"],
        summary=kind.summary(session, version),
        comment=comment,
        auto_approval=not human_approval_required(detail.get("changes")),
    )
    table = kind.table
    status = session.execute(select(table.c.status).where(table.c.id == version["id"])).scalar_one()
    if status == SUBMITTED:
        session.execute(
            update(table)
            .where(table.c.id == version["id"])
            .values(approval_request_id=request["id"])
        )
    return request


def _approvers(session: Session, approval_request_id: UUID) -> set[UUID]:
    """The people whose APPROVE decisions the request holds, delegators included."""
    rows = session.execute(
        select(approval_decision.c.approver_id, approval_decision.c.on_behalf_of_id).where(
            approval_decision.c.approval_request_id == approval_request_id,
            approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
        )
    ).all()
    return {UUID(str(value)) for row in rows for value in row if value is not None}


def approve(
    uow: UnitOfWork, kind: ConfigVersionKind, version_id: UUID, approval_request_id: UUID
) -> None:
    """``SubjectSpec.on_approved``: SUBMITTED → APPROVED under the approved request, then
    publication in the same transaction.

    The version's author never approves it (REQ-POL-003; SoD-5): an approval by the author, who
    need not be the preparer, raises 403 ``self-approval`` and rolls the decision back. Without a
    human approval (``AUTO_APPROVE``) the version is published without ``published_by``.
    """
    session = uow.session
    version = lock(session, kind, version_id)
    if version["status"] != SUBMITTED:
        raise refused(NOT_SUBMITTED)
    approvers = _approvers(session, approval_request_id)
    if version["created_by"] is not None and UUID(str(version["created_by"])) in approvers:
        raise Problem("self-approval", AUTHOR_DETAIL)
    approved = transition(
        uow,
        kind,
        version,
        ConfigStatus.APPROVED,
        values={"approval_request_id": approval_request_id},
        after={"approval_request_id": approval_request_id},
        approval_request_id=approval_request_id,
    )
    principal_id = uow.principal.id
    publish(
        uow,
        kind,
        approved,
        approval_request_id=approval_request_id,
        published_by=principal_id if principal_id in approvers else None,
    )


def publish(
    uow: UnitOfWork,
    kind: ConfigVersionKind,
    version: Mapping[str, Any],
    *,
    approval_request_id: UUID | None,
    published_by: UUID | None,
) -> Mapping[str, Any]:
    """APPROVED → PUBLISHED; a PUBLISHED version is returned as it is (04 §16.5 publish note).

    422 ``validation-failed`` collects the kind's publication findings (REQ-POL-002), the
    effective date of a superseding version as it stands at this instant (PRD ERR-75) and an
    effective date not after that of the scope's PUBLISHED version. That version becomes SUPERSEDED
    first, because DB-04 refuses overlapping PUBLISHED ranges.
    """
    if version["status"] == PUBLISHED:
        return version
    if version["status"] != APPROVED:
        raise refused(NOT_APPROVED)
    session = uow.session
    errors = kind.publish_errors(session, version)
    prior = published_of_scope(session, kind, version, for_update=True)
    errors += effective_errors(session, kind, version, supersedes=prior is not None, now=uow.now)
    effective_from: datetime | None = version["effective_from"]
    boundary = uow.now if effective_from is None else effective_from
    if prior is not None and prior["effective_from"] is not None:
        if boundary <= prior["effective_from"]:
            errors.append(
                ProblemError(field="effective_from", rule_id=RULE_FROZEN, message=EFFECTIVE_ORDER)
            )
    if errors:
        raise invalid(errors)
    snapshot = dict(kind.snapshot(session, version["id"]))
    if prior is None:
        prior_snapshot: dict[str, Any] = {name: None for name in snapshot}
    else:
        prior_snapshot = dict(kind.snapshot(session, prior["id"]))
        transition(
            uow,
            kind,
            dict(prior),
            ConfigStatus.SUPERSEDED,
            values={"effective_to": boundary},
            before={"effective_to": None, **prior_snapshot},
            after={"effective_to": boundary, **snapshot},
            detail={"superseded_by_version_id": version["id"]},
            approval_request_id=approval_request_id,
        )
    published = {"published_at": uow.now, "published_by": published_by}
    return transition(
        uow,
        kind,
        version,
        ConfigStatus.PUBLISHED,
        values=published,
        before={"published_at": None, "published_by": None, **prior_snapshot},
        after={**published, **snapshot},
        detail={
            "supersedes_version_id": None if prior is None else prior["id"],
            "effective_from": effective_from,
        },
        approval_request_id=approval_request_id,
    )


def close(
    uow: UnitOfWork,
    kind: ConfigVersionKind,
    version_id: UUID,
    approval_request_id: UUID,
    *,
    to_status: ConfigStatus,
) -> None:
    """``on_rejected`` (REJECTED) or ``on_voided`` (WITHDRAWN) of a SUBMITTED version; any other
    status stays as it is."""
    version = lock(uow.session, kind, version_id)
    if version["status"] != SUBMITTED:
        return
    transition(uow, kind, version, to_status, approval_request_id=approval_request_id)
