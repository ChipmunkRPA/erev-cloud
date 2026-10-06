"""Access review campaigns (04 T-PLT-40, T-PLT-41, E-107, E-108, §14.1 DB-10, §14.3 item 3, §15.3
API-R-51; SCREENS_B §9.13 SF-14:access-reviews and SF-14:access-review; PRD BR-PLT-02, J-22.11;
REQ-CTL-006; BUILD_SPEC PLF-28, BS1-D-28).

``create_campaign`` records a DRAFT campaign whose reviewers are ACTIVE members holding
``access.approve`` for all entities. ``start_campaign`` snapshots every membership that is not
REMOVED: the person's email and last sign-in and each role in force with its entity scope, grant
date and grantor (``AUTO-BOOTSTRAP`` for setup grants). It writes one PENDING item per membership
and the snapshot file of purpose ``REPORT_OUTPUT`` (BS1-D-28). A reviewer certifies another
member's item or requests its revocation with a comment; once the member's access is revoked,
``confirm_revocation`` records completion. ``complete_campaign`` needs every item decided.

A campaign is an act on the workspace: every route of it asks ``access.approve`` for all entities
(the guard of the routes; 04 API-C-03 rev 1.243). The snapshot is therefore taken by a principal
that reads every entity, and names each by its code: started under a narrower scope it stated
the entities outside it by id (``entity_scope.codes``) — measured before the guard, in the
stored item of a member of another entity.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import Select, and_, func, insert, or_, select
from sqlalchemy.orm import Session

from erev_api.auth import entity_scope
from erev_api.auth.principal import RequestContext
from erev_api.db import new_id, transitions
from erev_api.db.session import of_session_tenant, tenant_session
from erev_api.db.tables import (
    access_review_campaign,
    access_review_item,
    app_user,
    role,
    role_assignment,
    tenant_membership,
)
from erev_api.domain.platform import users
from erev_api.domain.platform.approval_queries import Page, actor, display_names
from erev_api.enums import (
    AccessReviewDecision,
    AccessReviewStatus,
    FilePurpose,
    MembershipStatus,
    PrincipalKind,
)
from erev_api.events import notifications
from erev_api.files.store import store_file
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

CAMPAIGN_OBJECT: Final = "access_review_campaign"
ITEM_OBJECT: Final = "access_review_item"
CREATE_ACTION: Final = "access_review_campaign.create"
START_ACTION: Final = "access_review_campaign.start"
COMPLETE_ACTION: Final = "access_review_campaign.complete"
CANCEL_ACTION: Final = "access_review_campaign.cancel"
ITEM_CREATE_ACTION: Final = "access_review_item.create"
DECIDE_ACTION: Final = "access_review_item.decide"
CONFIRM_ACTION: Final = "access_review_item.confirm_revocation"
RULE_CAMPAIGN: Final = "T-PLT-40"
RULE_ITEM: Final = "T-PLT-41"
REVIEW_PERMISSION: Final = "access.approve"
LABEL_LENGTH: Final = 400  # 04 TY-07 erev.label
SNAPSHOT_MEDIA_TYPE: Final = "application/json"
DECISIONS: Final = frozenset(
    {AccessReviewDecision.CERTIFIED.value, AccessReviewDecision.REVOKE_REQUESTED.value}
)
TRACKING: Final = frozenset(
    {AccessReviewStatus.IN_REVIEW.value, AccessReviewStatus.COMPLETED.value}
)
CANCELLABLE: Final = frozenset({AccessReviewStatus.DRAFT.value, AccessReviewStatus.IN_REVIEW.value})

# SCREENS_B §9.13.
OWN_ACCESS: Final = "You cannot review your own access."
PENDING_ITEMS: Final = "Decide {count} pending items before completing the campaign."
# [J] SPEC-Q-193: copy the documents leave open.
NAME_LENGTH: Final = "Use 1 to 400 characters."
AS_OF_FUTURE: Final = "Choose an as-of time that is not in the future."
REVIEWERS_EMPTY: Final = "Add at least one reviewer."
REVIEWER_UNKNOWN: Final = "Choose a member who holds access approval for all entities."
REVIEWER_TWICE: Final = "Add each reviewer once."
NOT_REVIEWER: Final = "Only a reviewer of this campaign can decide its items."
NOT_DRAFT: Final = "Only a draft campaign can be started."
NOT_IN_REVIEW: Final = "Only a campaign in review can change."
NOT_CANCELLABLE: Final = "Only a draft campaign or a campaign in review can be cancelled."
NOT_TRACKING: Final = "Revocations are confirmed only in a campaign in review or completed."
ALREADY_DECIDED: Final = "This item is already decided."
NOT_REQUESTED: Final = "Only a requested revocation can be confirmed."
ACCESS_NOT_REVOKED: Final = "Revoke the member's access before confirming the revocation."


def _refused(field: str, rule_id: str, message: str) -> Problem:
    return Problem(
        "invalid-transition", errors=[ProblemError(field=field, rule_id=rule_id, message=message)]
    )


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat()


def _touched(uow: UnitOfWork, row_version: int) -> dict[str, Any]:
    """SC-M of an IM-S row the command changes; IM-S tables carry no touch trigger."""
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
        "row_version": row_version + 1,
    }


def _lock_campaign(session: Session, campaign_id: UUID) -> Mapping[Any, Any]:
    found = (
        session.execute(
            select(access_review_campaign)
            .where(access_review_campaign.c.id == campaign_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    return found


def _lock_item(session: Session, campaign_id: UUID, item_id: UUID) -> Mapping[Any, Any]:
    found = (
        session.execute(
            select(access_review_item)
            .where(
                access_review_item.c.id == item_id,
                access_review_item.c.access_review_campaign_id == campaign_id,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    return found


def create_campaign(
    uow: UnitOfWork, *, name: str, as_of: datetime, reviewer_membership_ids: Sequence[UUID]
) -> UUID:
    """``POST /access-reviews``: a DRAFT campaign; returns its id.

    422 ``validation-failed`` collects the name (1 to 400 characters), an as-of time that is not
    in the future, and the reviewers: at least one, each once, each an ACTIVE member holding
    ``access.approve`` for all entities — the routes of a campaign refuse anyone else, so a
    reviewer of named entities could decide nothing. Audits ``access_review_campaign.create``.
    """
    session = uow.session
    principal = uow.principal
    errors: list[ProblemError] = []
    text = name.strip()
    if not 1 <= len(text) <= LABEL_LENGTH:
        errors.append(ProblemError(field="name", rule_id=RULE_CAMPAIGN, message=NAME_LENGTH))
    if as_of > uow.now:
        errors.append(ProblemError(field="as_of", rule_id=RULE_CAMPAIGN, message=AS_OF_FUTURE))
    if not reviewer_membership_ids:
        errors.append(
            ProblemError(
                field="reviewer_membership_ids", rule_id=RULE_CAMPAIGN, message=REVIEWERS_EMPTY
            )
        )
    # A campaign is the workspace's: its reviewers hold ``access.approve`` for all entities by a
    # grant of their own (ruling of 2026-10-01 on SCOPE-WORKSPACE-LISTS-1 (c3), answer Q3).
    holders = notifications.permission_holders_direct(
        session, permission=REVIEW_PERMISSION, entity_ids=(), all_entities=True, at=uow.now
    )
    seen: set[UUID] = set()
    for index, membership_id in enumerate(reviewer_membership_ids):
        field = f"reviewer_membership_ids[{index}]"
        if membership_id in seen:
            errors.append(ProblemError(field=field, rule_id=RULE_CAMPAIGN, message=REVIEWER_TWICE))
        elif membership_id not in holders:
            errors.append(
                ProblemError(field=field, rule_id=RULE_CAMPAIGN, message=REVIEWER_UNKNOWN)
            )
        seen.add(membership_id)
    if errors:
        raise Problem("validation-failed", errors=errors)

    campaign_id = new_id()
    values = {
        "name": text,
        "status": AccessReviewStatus.DRAFT.value,
        "as_of": as_of,
        "reviewer_membership_ids": list(reviewer_membership_ids),
    }
    session.execute(
        insert(access_review_campaign).values(
            tenant_id=principal.tenant_id,
            id=campaign_id,
            **values,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=CAMPAIGN_OBJECT,
        object_id=campaign_id,
        after={
            **values,
            "reviewer_membership_ids": [str(value) for value in reviewer_membership_ids],
        },
    )
    return campaign_id


def _grantor(decision: Mapping[str, Any] | None, names: Mapping[UUID, str]) -> str | None:
    """``granted_by``: the rule key of an auto-approval (``AUTO-BOOTSTRAP`` for setup grants), else
    the approver's name; None for an assignment without an approving decision (SPEC-Q-193)."""
    if decision is None:
        return None
    if decision["rule_key"] is not None:
        return str(decision["rule_key"])
    approver = decision["approver_id"]
    return None if approver is None else names.get(UUID(str(approver)))


def snapshot_memberships(session: Session, *, at: datetime) -> list[dict[str, Any]]:
    """Every membership that is not REMOVED with its person and the roles in force at ``at``,
    ordered by email: the item values of ``start_campaign``.

    The person's name and last sign-in are what this workspace is shown of them at the start
    (``users.SHOWN_NAME``, ``users.SHOWN_LAST_LOGIN``; D-80 rule 5): the snapshot file, the items
    and their audit events store these values, and an invitation not accepted yet is a membership
    of the review."""
    members = session.execute(
        select(
            tenant_membership.c.id,
            app_user.c.email,
            users.SHOWN_DISPLAY_NAME,
            users.SHOWN_LAST_LOGIN.label("last_login_at"),
        )
        .select_from(tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id))
        .where(
            of_session_tenant(tenant_membership),
            tenant_membership.c.status != MembershipStatus.REMOVED.value,
        )
        .order_by(app_user.c.email, tenant_membership.c.id)
    ).all()
    assignments = (
        session.execute(
            select(
                role_assignment.c.membership_id,
                role_assignment.c.approval_request_id,
                role_assignment.c.is_all_entities,
                role_assignment.c.entity_ids,
                role_assignment.c.valid_from,
                role.c.code.label("role_code"),
            )
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
                role_assignment.c.membership_id.in_([row.id for row in members]),
                role_assignment.c.revoked_at.is_(None),
                role_assignment.c.valid_from <= at,
                or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > at),
            )
            .order_by(role.c.code, role_assignment.c.valid_from, role_assignment.c.id)
        )
        .mappings()
        .all()
    )
    granting = users.granting_decisions(
        session, [row["approval_request_id"] for row in assignments]
    )
    names = display_names(session, [decision["approver_id"] for decision in granting.values()])
    entities = entity_scope.names(
        session, [value for row in assignments for value in row["entity_ids"] or ()]
    )
    roles: dict[Any, list[dict[str, Any]]] = {}
    for assignment in assignments:
        roles.setdefault(assignment["membership_id"], []).append(
            {
                "role_code": str(assignment["role_code"]),
                "is_all_entities": bool(assignment["is_all_entities"]),
                "entity_codes": entity_scope.codes(entities, assignment["entity_ids"] or ()),
                "granted_at": _iso(assignment["valid_from"]),
                "granted_by": _grantor(granting.get(assignment["approval_request_id"]), names),
            }
        )
    return [
        {
            "membership_id": row.id,
            "user_email_snapshot": str(row.email),
            "display_name": str(row.display_name),
            "last_login_at": row.last_login_at,
            "roles_snapshot": roles.get(row.id, []),
        }
        for row in members
    ]


def start_campaign(uow: UnitOfWork, campaign_id: UUID) -> None:
    """``POST /access-reviews/{id}/start``: DRAFT → IN_REVIEW with the snapshot.

    404 ``not-found``; 409 ``invalid-transition`` unless DRAFT. Stores the snapshot file, writes
    one PENDING item per membership that is not REMOVED, and audits ``access_review_item.create``
    per item and ``access_review_campaign.start``.
    """
    session = uow.session
    principal = uow.principal
    campaign = _lock_campaign(session, campaign_id)
    if campaign["status"] != AccessReviewStatus.DRAFT.value:
        raise _refused("status", RULE_CAMPAIGN, NOT_DRAFT)
    snapshots = snapshot_memberships(session, at=uow.now)
    document = {
        "campaign": {
            "id": str(campaign_id),
            "name": campaign["name"],
            "as_of": _iso(campaign["as_of"]),
            "started_at": _iso(uow.now),
            "reviewer_membership_ids": [
                str(value) for value in campaign["reviewer_membership_ids"]
            ],
        },
        "items": [
            {
                "membership_id": str(snapshot["membership_id"]),
                "user_email_snapshot": snapshot["user_email_snapshot"],
                "display_name": snapshot["display_name"],
                "last_login_at": None
                if snapshot["last_login_at"] is None
                else _iso(snapshot["last_login_at"]),
                "roles_snapshot": snapshot["roles_snapshot"],
            }
            for snapshot in snapshots
        ],
    }
    stored = store_file(
        uow,
        purpose=FilePurpose.REPORT_OUTPUT,
        stream=io.BytesIO(canonical_bytes(document)),
        original_filename=f"access-review-{campaign_id}.json",
        media_type=SNAPSHOT_MEDIA_TYPE,
    )
    for snapshot in snapshots:
        item_id = new_id()
        values = {
            "access_review_campaign_id": campaign_id,
            "membership_id": snapshot["membership_id"],
            "user_email_snapshot": snapshot["user_email_snapshot"],
            "roles_snapshot": snapshot["roles_snapshot"],
            "last_login_at": snapshot["last_login_at"],
            "decision": AccessReviewDecision.PENDING.value,
        }
        session.execute(
            insert(access_review_item).values(
                tenant_id=principal.tenant_id,
                id=item_id,
                **values,
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
                updated_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
            )
        )
        uow.audit(
            action=ITEM_CREATE_ACTION,
            object_type=ITEM_OBJECT,
            object_id=item_id,
            after={
                "access_review_campaign_id": str(campaign_id),
                "membership_id": str(snapshot["membership_id"]),
                "roles_snapshot": snapshot["roles_snapshot"],
                "decision": AccessReviewDecision.PENDING.value,
            },
        )
    started = {"started_at": uow.now, "snapshot_file_id": stored["id"]}
    transitions.apply(
        session,
        CAMPAIGN_OBJECT,
        campaign_id,
        to_status=AccessReviewStatus.IN_REVIEW.value,
        expected_status=AccessReviewStatus.DRAFT.value,
        set_values={**started, **_touched(uow, campaign["row_version"])},
    )
    uow.audit(
        action=START_ACTION,
        object_type=CAMPAIGN_OBJECT,
        object_id=campaign_id,
        before={
            "status": AccessReviewStatus.DRAFT.value,
            "started_at": None,
            "snapshot_file_id": None,
        },
        after={"status": AccessReviewStatus.IN_REVIEW.value, **started},
    )


def _authorize_reviewer(
    uow: UnitOfWork, campaign: Mapping[str, Any], item: Mapping[str, Any]
) -> None:
    """403 ``forbidden`` for a principal who is not a reviewer of the campaign; 403
    ``self-approval`` for the reviewer's own membership (DB-10)."""
    membership_id = uow.principal.membership_id
    if membership_id is None or membership_id not in set(campaign["reviewer_membership_ids"]):
        raise Problem("forbidden", NOT_REVIEWER)
    if item["membership_id"] == membership_id:
        raise Problem("self-approval", OWN_ACCESS)


def decide_item(
    uow: UnitOfWork, campaign_id: UUID, item_id: UUID, *, decision: str, comment: str | None
) -> None:
    """``POST /access-reviews/{id}/items/{item_id}/decide``: CERTIFIED or REVOKE_REQUESTED.

    404 ``not-found``; 403 as ``_authorize_reviewer``; 422 for another decision or a revocation
    without a comment of at least 10 characters; 409 ``invalid-transition`` unless the campaign is
    IN_REVIEW and the item PENDING. Audits ``access_review_item.decide``.
    """
    session = uow.session
    campaign = _lock_campaign(session, campaign_id)
    item = _lock_item(session, campaign_id, item_id)
    _authorize_reviewer(uow, campaign, item)
    errors: list[ProblemError] = []
    if decision not in DECISIONS:
        errors.append(
            ProblemError(field="decision", rule_id=RULE_ITEM, message="Choose a decision.")
        )
    text = (comment or "").strip() or None
    if decision == AccessReviewDecision.REVOKE_REQUESTED.value and (
        text is None or len(text) < users.MIN_REASON_LENGTH
    ):
        errors.append(
            ProblemError(field="comment", rule_id=users.RULE_REASON, message=users.REASON_SHORT)
        )
    if errors:
        raise Problem("validation-failed", errors=errors)
    if campaign["status"] != AccessReviewStatus.IN_REVIEW.value:
        raise _refused("status", RULE_CAMPAIGN, NOT_IN_REVIEW)
    if item["decision"] != AccessReviewDecision.PENDING.value:
        raise _refused("decision", RULE_ITEM, ALREADY_DECIDED)
    decided = {"reviewer_id": uow.principal.id, "decided_at": uow.now, "comment": text}
    transitions.apply(
        session,
        ITEM_OBJECT,
        item_id,
        to_status=decision,
        expected_status=AccessReviewDecision.PENDING.value,
        set_values={**decided, **_touched(uow, item["row_version"])},
    )
    uow.audit(
        action=DECIDE_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        before={"decision": AccessReviewDecision.PENDING.value},
        after={"decision": decision, "reviewer_id": uow.principal.id, "decided_at": uow.now},
        comment=text,
    )


def _access_revoked(session: Session, membership_id: UUID, *, since: datetime) -> bool:
    """Whether the membership was removed, or lost a role at or after ``since``."""
    status = session.scalar(
        select(tenant_membership.c.status).where(
            of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id
        )
    )
    if status == MembershipStatus.REMOVED.value:
        return True
    revoked = session.scalar(
        select(func.count())
        .select_from(role_assignment)
        .where(
            role_assignment.c.membership_id == membership_id,
            role_assignment.c.revoked_at.is_not(None),
            role_assignment.c.revoked_at >= since,
        )
    )
    return bool(revoked)


def confirm_revocation(uow: UnitOfWork, campaign_id: UUID, item_id: UUID) -> None:
    """``POST /access-reviews/{id}/items/{item_id}/confirm-revocation``: REVOKE_REQUESTED → REVOKED.

    404 ``not-found``; 403 as ``_authorize_reviewer``; 409 ``invalid-transition`` unless the
    campaign is IN_REVIEW or COMPLETED, the item REVOKE_REQUESTED, and the member removed or a role
    of the member revoked since the campaign started. Audits
    ``access_review_item.confirm_revocation``.
    """
    session = uow.session
    campaign = _lock_campaign(session, campaign_id)
    item = _lock_item(session, campaign_id, item_id)
    _authorize_reviewer(uow, campaign, item)
    if campaign["status"] not in TRACKING:
        raise _refused("status", RULE_CAMPAIGN, NOT_TRACKING)
    if item["decision"] != AccessReviewDecision.REVOKE_REQUESTED.value:
        raise _refused("decision", RULE_ITEM, NOT_REQUESTED)
    if not _access_revoked(session, item["membership_id"], since=campaign["started_at"]):
        raise _refused("decision", RULE_ITEM, ACCESS_NOT_REVOKED)
    transitions.apply(
        session,
        ITEM_OBJECT,
        item_id,
        to_status=AccessReviewDecision.REVOKED.value,
        expected_status=AccessReviewDecision.REVOKE_REQUESTED.value,
        set_values={"revocation_completed_at": uow.now, **_touched(uow, item["row_version"])},
    )
    uow.audit(
        action=CONFIRM_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        before={
            "decision": AccessReviewDecision.REVOKE_REQUESTED.value,
            "revocation_completed_at": None,
        },
        after={
            "decision": AccessReviewDecision.REVOKED.value,
            "revocation_completed_at": uow.now,
        },
    )


def complete_campaign(uow: UnitOfWork, campaign_id: UUID) -> None:
    """``POST /access-reviews/{id}/complete``: IN_REVIEW → COMPLETED once every item is decided.

    404 ``not-found``; 409 ``invalid-transition`` unless IN_REVIEW, and with detail "Decide <n>
    pending items before completing the campaign." while items are PENDING. Audits
    ``access_review_campaign.complete``.
    """
    session = uow.session
    campaign = _lock_campaign(session, campaign_id)
    if campaign["status"] != AccessReviewStatus.IN_REVIEW.value:
        raise _refused("status", RULE_CAMPAIGN, NOT_IN_REVIEW)
    pending = session.scalar(
        select(func.count())
        .select_from(access_review_item)
        .where(
            access_review_item.c.access_review_campaign_id == campaign_id,
            access_review_item.c.decision == AccessReviewDecision.PENDING.value,
        )
    )
    if pending:
        raise Problem("invalid-transition", PENDING_ITEMS.format(count=pending))
    transitions.apply(
        session,
        CAMPAIGN_OBJECT,
        campaign_id,
        to_status=AccessReviewStatus.COMPLETED.value,
        expected_status=AccessReviewStatus.IN_REVIEW.value,
        set_values={"completed_at": uow.now, **_touched(uow, campaign["row_version"])},
    )
    uow.audit(
        action=COMPLETE_ACTION,
        object_type=CAMPAIGN_OBJECT,
        object_id=campaign_id,
        before={"status": AccessReviewStatus.IN_REVIEW.value, "completed_at": None},
        after={"status": AccessReviewStatus.COMPLETED.value, "completed_at": uow.now},
    )


def cancel_campaign(uow: UnitOfWork, campaign_id: UUID) -> None:
    """``POST /access-reviews/{id}/cancel``: DRAFT or IN_REVIEW → CANCELLED; decided items stay.

    404 ``not-found``; 409 ``invalid-transition`` otherwise. Audits
    ``access_review_campaign.cancel``.
    """
    session = uow.session
    campaign = _lock_campaign(session, campaign_id)
    current = str(campaign["status"])
    if current not in CANCELLABLE:
        raise _refused("status", RULE_CAMPAIGN, NOT_CANCELLABLE)
    transitions.apply(
        session,
        CAMPAIGN_OBJECT,
        campaign_id,
        to_status=AccessReviewStatus.CANCELLED.value,
        expected_status=current,
        set_values=_touched(uow, campaign["row_version"]),
    )
    uow.audit(
        action=CANCEL_ACTION,
        object_type=CAMPAIGN_OBJECT,
        object_id=campaign_id,
        before={"status": current},
        after={"status": AccessReviewStatus.CANCELLED.value},
    )


def list_campaigns[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of campaigns in every status."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(access_review_campaign))
        return result, campaign_outs(session, result.items)


def get_campaign(ctx: RequestContext, campaign_id: UUID) -> dict[str, Any]:
    """API-S-AccessReview of one campaign; 404 ``not-found`` otherwise."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return _one_campaign(session, campaign_id)


def campaign_out(uow: UnitOfWork, campaign_id: UUID) -> dict[str, Any]:
    """API-S-AccessReview of a campaign the command just changed, in its transaction."""
    return _one_campaign(uow.session, campaign_id)


def _one_campaign(session: Session, campaign_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(
            select(access_review_campaign).where(access_review_campaign.c.id == campaign_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return campaign_outs(session, [dict(row)])[0]


def campaign_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-AccessReview of each ``access_review_campaign`` row: the T-PLT-40 columns, the
    reviewers with their names and the item counts by decision."""
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    counts: dict[Any, dict[str, int]] = {}
    for campaign_id, decision, count in session.execute(
        select(
            access_review_item.c.access_review_campaign_id,
            access_review_item.c.decision,
            func.count(),
        )
        .where(access_review_item.c.access_review_campaign_id.in_(ids))
        .group_by(access_review_item.c.access_review_campaign_id, access_review_item.c.decision)
    ):
        counts.setdefault(campaign_id, {})[str(decision)] = int(count)
    reviewer_ids = sorted({value for row in rows for value in row["reviewer_membership_ids"]})
    reviewers = {
        row.id: row
        for row in session.execute(
            select(tenant_membership.c.id, tenant_membership.c.user_id, users.SHOWN_DISPLAY_NAME)
            .select_from(
                tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
            )
            .where(of_session_tenant(tenant_membership), tenant_membership.c.id.in_(reviewer_ids))
        )
    }
    names = display_names(session, [row["created_by"] for row in rows])
    outs: list[dict[str, Any]] = []
    for row in rows:
        by_decision = counts.get(row["id"], {})
        outs.append(
            {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "as_of": row["as_of"],
                "reviewers": [
                    {
                        "membership_id": value,
                        "user_id": reviewers[value].user_id,
                        "display_name": reviewers[value].display_name,
                    }
                    for value in row["reviewer_membership_ids"]
                    if value in reviewers
                ],
                "counts": {
                    "members": sum(by_decision.values()),
                    "pending": by_decision.get(AccessReviewDecision.PENDING.value, 0),
                    "certified": by_decision.get(AccessReviewDecision.CERTIFIED.value, 0),
                    "revoke_requested": by_decision.get(
                        AccessReviewDecision.REVOKE_REQUESTED.value, 0
                    ),
                    "revoked": by_decision.get(AccessReviewDecision.REVOKED.value, 0),
                },
                "snapshot_file_id": row["snapshot_file_id"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "created_at": row["created_at"],
                "created_by": actor(row["created_by"], str(row["created_by_kind"]), names),
                "updated_at": row["updated_at"],
                "row_version": row["row_version"],
            }
        )
    return outs


def list_items[P: Page](
    ctx: RequestContext, campaign_id: UUID, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the campaign's items; 404 ``not-found`` for an unknown campaign."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        exists = session.scalar(
            select(access_review_campaign.c.id).where(access_review_campaign.c.id == campaign_id)
        )
        if exists is None:
            raise Problem("not-found")
        result = page(
            session,
            select(access_review_item).where(
                access_review_item.c.access_review_campaign_id == campaign_id
            ),
        )
        return result, item_outs(session, result.items)


def item_out(uow: UnitOfWork, item_id: UUID) -> dict[str, Any]:
    """API-S-AccessReviewItem of an item the command just changed, in its transaction."""
    row = (
        uow.session.execute(select(access_review_item).where(access_review_item.c.id == item_id))
        .mappings()
        .one()
    )
    return item_outs(uow.session, [dict(row)])[0]


def item_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-AccessReviewItem of each ``access_review_item`` row: the T-PLT-41 columns with the
    member's name as this workspace is shown it now (``users.SHOWN_NAME``; D-80 rule 5) and the
    reviewer as API-S-Actor."""
    if not rows:
        return []
    members = {
        row.id: str(row.display_name)
        for row in session.execute(
            select(tenant_membership.c.id, users.SHOWN_DISPLAY_NAME)
            .select_from(
                tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
            )
            .where(
                of_session_tenant(tenant_membership),
                tenant_membership.c.id.in_([row["membership_id"] for row in rows]),
            )
        )
    }
    names = display_names(session, [row["reviewer_id"] for row in rows])
    return [
        {
            "id": row["id"],
            "access_review_campaign_id": row["access_review_campaign_id"],
            "membership_id": row["membership_id"],
            "user_email_snapshot": row["user_email_snapshot"],
            "display_name": members.get(row["membership_id"], row["user_email_snapshot"]),
            "roles_snapshot": row["roles_snapshot"],
            "last_login_at": row["last_login_at"],
            "decision": row["decision"],
            "reviewer": None
            if row["reviewer_id"] is None
            else actor(row["reviewer_id"], PrincipalKind.USER.value, names),
            "decided_at": row["decided_at"],
            "comment": row["comment"],
            "revocation_completed_at": row["revocation_completed_at"],
            "row_version": row["row_version"],
        }
        for row in rows
    ]
