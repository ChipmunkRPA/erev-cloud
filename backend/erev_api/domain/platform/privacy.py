"""Personal data erasure commands (05 §6.17 PRV-07; 04 §15.3 API-R-05, API-R-12, T-PLT-02, T-PLT-29;
03 REQ-SEC-007; runbook RB-14; BUILD_SPEC SOP-5).

``anonymise_user`` (PRV-07 a) rewrites the global identity behind a membership and removes the
person from every workspace; the immutable stores keep their pseudonymous ``actor_id`` references
(PRV-03), and the audit diff carries the old e-mail only in the PRV-04 HMAC form the writer applies
at append. ``shred_file`` (PRV-07 b) decides the shred of a file — it marks the immutable row and
writes the event of the decision — and the file's wrapped data key is destroyed after that
commit, through ``erev_api.files.lifecycle.shred_sidecar``, by ``complete_shred`` (see "Decide,
then destroy" below); it is coded to D-98
candidate 145 AMENDMENT 2 (FILES-SHRED-1, lane P1, not yet on main): a shredded row is refused by
name (``FILE_SHREDDED``) everywhere, and its two database witnesses are NOT RUN until that chain
lands. Blocked, not guessed: shredding a purpose outside ``policy.ENCRYPTED_PURPOSES`` (a plaintext
object would survive the marker; D-98 145 addendum (2)) is refused with rule ``PRV-06`` until the
privacy owner rules on plaintext erasure, and re-admission of shredded bytes stays P1's open
question.

Cross-tenant work (Codex P8-PRV07-COMPLETE-1 and its residual): ``tenant_membership`` is RLS-T,
so the acting tenant's unit of work can only remove the person's membership in its own
workspace. The other memberships are enumerated through ``erev_api.auth.mfa.user_memberships``
(the platform-wide identity view only ``auth`` may open, DG-KRN-DB-02) and removed BEFORE the
identity changes, one workspace transaction each, and each of those transactions records only
what it completed: its ``tenant_membership.remove`` marked ``erasure``. A failure raises while
nothing of the acting tenant has changed (the response is the problem, never a stored success)
and a repeated command resumes the removals still owed (rows already ``REMOVED`` are locked,
skipped and not audited again). The ``app_user.anonymise`` event each of those workspaces is
owed (04 T-PLT-02: AUD-CMD changes of ``app_user`` are written to each tenant in which the user
is ACTIVE) can be truthfully written only after the global identity change is durable, so it is
delivered by the resume run of the same command from durable markers (the erasure-marked removal
in the tenant's chain, and the absence of the event), never from memory; the acting tenant's event
lists the workspaces still owed it. No cross-tenant transaction, no new table or job kind.

What this module does not decide (05 PRV-07, D-97 §C proposals pending the privacy owner): whether
MFA factors and recovery codes are deleted with the identity (D-97 (39) proposes yes; not done
here), the handling of ``access_review_item.user_email_snapshot`` and ``file_object.
original_filename``, and legal-hold precedence. Those stay recorded in the lane record.

Decide, then destroy (05 PRV-07 b rev 1.171; 04 T-PLT-29 rev 1.237; item
FILE-SHRED-DURABLE-ORDER-1, the supervisor's ruling on finding B4 of the review of the
``EVIDENCE_SHRED`` merge). A destruction is irreversible, so the record of it is made durable
first. (1) The command's transaction — ``file.shred``, or the hook of an approved
``EVIDENCE_SHRED`` request — sets the row's four shred columns and writes ``file_object.shred``:
who, when, why, the approval and the holds it lifted. Nothing of the store is touched before
that commit, so a command that fails saved nothing and destroyed nothing. (2) The key is
destroyed afterwards by ``complete_shred``, in a transaction of its own: the row's lock, the
key's advisory lock, ``shred_sidecar``, ``shred_completed_at`` and ``file_object.shred_complete``
with the store's report. (3) Three roads run that one function: the continuation of the unit of
work that committed the decision (``continuation``), ``file.shred`` sent again for a row decided
and not completed (it finishes the shred in its own transaction and answers the row), and the
sweep SCH-16 (``domain.platform.shred_completion``). Until the completion the marked row is the
durable intent: every reader of the workspace refuses by it, and the verifier names
``shredded_sidecar_present``. Measured before this order (the marker and the delete came first,
in the command's transaction): a commit that lost its wait for the audit chain head answered
409 "nothing was saved" with the key destroyed, the row unmarked and no event.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import delegations
from erev_api.audit import writer as audit_writer
from erev_api.audit.chain import append_events
from erev_api.audit.writer import AuditActor, actor_of, build_event
from erev_api.auth import entity_scope, mfa
from erev_api.auth.sessions import end_user_sessions
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    app_user,
    audit_event,
    file_object,
    role_assignment,
    tenant_membership,
    user_session,
)
from erev_api.domain.platform import file_access, file_evidence, guards, users
from erev_api.enums import FilePurpose, MembershipStatus, SessionEndReason, UserStatus
from erev_api.files import lifecycle, policy
from erev_api.files.store import (
    SHREDDED_MESSAGE,
    FileStore,
    GenerationConflict,
    VersionedFileStore,
    owns_key,
)
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import LOCK_CONFLICT_DETAIL, Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import RequestContext
    from erev_api.clock import Clock
    from erev_api.uow import UnitOfWork

_LOGGER: Final = "erev_api.domain.platform.privacy"
register_logger_fields(_LOGGER, ("file_id", "road", "error_type"))

USER_OBJECT: Final = "app_user"
ANONYMISE_ACTION: Final = "app_user.anonymise"
ERASED_DOMAIN: Final = "invalid.erev"
RULE_ERASURE: Final = "PRV-07"
ALREADY_ERASED: Final = "This person's personal data is already erased."
FILE_OBJECT: Final = "file_object"
SHRED_ACTION: Final = "file_object.shred"
# 04 T-PLT-29 rev 1.237: the event of the store's part of a shred, written by whatever
# finishes it, with the road it came by.
COMPLETE_ACTION: Final = "file_object.shred_complete"
ROAD_COMMAND: Final = "command"  # the continuation of the unit of work that decided
ROAD_RETRY: Final = "retry"  # ``file.shred`` sent again for a row decided and not completed
ROAD_SWEEP: Final = "sweep"  # SCH-16
SHRED_PERMISSION: Final = "settings.manage"  # 04 API-R-12 ``file.shred``
# 05 SBX-08 rev 1.164 (item FILE-SHRED-SCOPE-1): the line of 403 ``sandbox-restricted`` for the
# three commands that destroy a stored file, for a file the sandbox shares. A copy's
# ``file_object`` rows carry the storage keys of their source (SBX-03), so a shred of such a
# file issued in a sandbox would destroy the production file.
SANDBOX_SHRED: Final = (
    "This file belongs to the workspace this sandbox was copied from and cannot be shredded here."
)
# 04 T-PLT-29 "Shred scope" rev 1.225 (item FILE-SHRED-SCOPE-1, B3): the line of 403
# ``forbidden`` for an administrator whose ``settings.manage`` does not cover every entity of the
# records that reference the file. It names no record and no entity.
SHRED_BEYOND_SCOPE: Final = (
    "This file belongs to records of legal entities outside your roles, so you cannot shred it."
)
# 04 table 15.4-B rule ids and the PRV-06 block for plaintext purposes.
RULE_RETENTION_ACTIVE: Final = "FILE_RETENTION_ACTIVE"
RULE_SHREDDED: Final = "FILE_SHREDDED"
RULE_PLAINTEXT_PURPOSE: Final = "PRV-06"
RETENTION_ACTIVE_MESSAGE: Final = (
    "This file is under legal hold or within its retention period and cannot be shredded."
)
PLAINTEXT_PURPOSE_MESSAGE: Final = (
    "Only files stored under a per-file data key can be shredded in 1.0; erasure of a plaintext "
    "purpose awaits the privacy owner's ruling."
)


def erased_display_name(user_id: UUID) -> str:
    """05 PRV-07 a: ``Erased user <first 8 hex of SHA-256(user id)>``."""
    return f"Erased user {hashlib.sha256(str(user_id).encode('utf-8')).hexdigest()[:8]}"


def erased_email(user_id: UUID) -> str:
    """05 PRV-07 a: ``erased+<user id>@invalid.erev``; unique per user, undeliverable by design."""
    return f"erased+{user_id}@{ERASED_DOMAIN}"


@dataclass(frozen=True, slots=True)
class AnonymiseResult:
    """What one request changed. Every count is of THIS request, measured after the work; the
    history of earlier attempts is in the tenants' audit chains, never summed here."""

    user_id: UUID
    membership_id: UUID
    sessions_ended: int
    membership_removed: bool  # False when the acting tenant's membership was already REMOVED
    other_memberships_removed: tuple[tuple[UUID, UUID], ...]  # (tenant, membership) removed now
    # Secondary rows the helper found already REMOVED or missing after enumeration (this request).
    other_memberships_already_removed: int
    # Secondary rows enumerated REMOVED before the work: an earlier attempt's completed part.
    other_memberships_skipped_removed: int
    # Other tenants still owed their app_user.anonymise completion event once this commit lands.
    completion_pending: tuple[UUID, ...]
    # Other tenants that received their completion event in this request (the resume path).
    completion_events_delivered: tuple[UUID, ...]


def pending_secondary_memberships(
    memberships: Iterable[tuple[UUID, UUID, str]], acting_tenant_id: UUID
) -> tuple[tuple[UUID, UUID], ...]:
    """The person's memberships outside the acting tenant that are not yet ``REMOVED``, in the
    enumeration's (tenant id) order: the removals 05 PRV-07 a still owes. Already removed rows are
    the completed part of an earlier attempt and are never touched again (no duplicate audit)."""
    return tuple(
        (tenant_id, membership_id)
        for tenant_id, membership_id, status in memberships
        if tenant_id != acting_tenant_id and status != MembershipStatus.REMOVED.value
    )


def _lock_membership(uow: UnitOfWork, membership_id: UUID) -> Mapping[str, Any]:
    row = (
        uow.session.execute(
            select(tenant_membership)
            .where(tenant_membership.c.id == membership_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _lock_user(uow: UnitOfWork, user_id: UUID) -> Mapping[str, Any]:
    row = (
        uow.session.execute(
            select(app_user).where(app_user.c.id == user_id).with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _updated(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


@dataclass(frozen=True, slots=True)
class _Erasure:
    """The facts every per-tenant step shares."""

    user_id: UUID
    acting_tenant_id: UUID
    actor: AuditActor
    now: datetime
    principal_id: UUID | None  # SYSTEM principals carry none; the columns are nullable
    principal_kind: str
    comment: str
    keyring: KeyRing


def _other_context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _remove_membership_in_tenant(erasure: _Erasure, tenant_id: UUID, membership_id: UUID) -> bool:
    """Remove one membership of the person in another workspace, in that workspace's own
    transaction, and record ONLY what that transaction completed: the row is locked; a row already
    ``REMOVED`` or missing (an earlier attempt completed it) is left alone and nothing is audited;
    otherwise the membership becomes ``REMOVED``, its role assignments are revoked and the tenant's
    chain gets one ``tenant_membership.remove`` event marked ``erasure`` (the durable marker that
    this workspace took part). The global identity is not yet changed here, so no ``app_user``
    after-state is written (Codex P8-PRV07-COMPLETE-1 residual); that event follows in
    :func:`_deliver_completion` once the identity change is durable. Returns whether this call
    removed the membership."""
    with tenant_session(_other_context(tenant_id)) as db:
        status = db.execute(
            select(tenant_membership.c.status)
            .where(tenant_membership.c.id == membership_id)
            .with_for_update()
        ).scalar_one_or_none()
        if status is None or status == MembershipStatus.REMOVED.value:
            return False
        db.execute(
            update(tenant_membership)
            .where(tenant_membership.c.id == membership_id)
            .values(
                status=MembershipStatus.REMOVED.value,
                removed_at=erasure.now,
                invitation_token_sha256=None,
                invitation_expires_at=None,
                updated_at=erasure.now,
                updated_by=erasure.principal_id,
                updated_by_kind=erasure.principal_kind,
            )
        )
        db.execute(
            update(role_assignment)
            .where(
                role_assignment.c.membership_id == membership_id,
                role_assignment.c.revoked_at.is_(None),
            )
            .values(
                revoked_at=erasure.now,
                revoked_by=erasure.principal_id,
                revoked_by_kind=erasure.principal_kind,
            )
        )
        # PRD BR-PLT-07: what the person had delegated in this workspace ends with the
        # membership, in the same transaction, each end on this workspace's chain.
        ended = delegations.end_unsupported_rows(
            db,
            now=erasure.now,
            revoked_by=erasure.principal_id,
            revoked_by_kind=erasure.principal_kind,
        )
        append_events(
            db,
            tenant_id=tenant_id,
            keyring=erasure.keyring,
            events=[
                build_event(
                    tenant_id=tenant_id,
                    actor=erasure.actor,
                    occurred_at=erasure.now,
                    action=users.REMOVE_ACTION,
                    object_type=users.OBJECT_TYPE,
                    object_id=membership_id,
                    before={"status": status},
                    after={"status": MembershipStatus.REMOVED.value, "removed_at": erasure.now},
                    comment=erasure.comment,
                    detail={
                        "acting_tenant_id": str(erasure.acting_tenant_id),
                        "erasure": True,
                        "user_id": str(erasure.user_id),
                    },
                ),
                *(
                    build_event(
                        tenant_id=tenant_id,
                        actor=erasure.actor,
                        occurred_at=erasure.now,
                        action=delegations.END_ACTION,
                        object_type=delegations.OBJECT_TYPE,
                        object_id=item.id,
                        before={"revoked_at": None},
                        after={"revoked_at": erasure.now},
                        detail=item.detail(delegations.IDENTITY_ERASED),
                    )
                    for item in ended
                ),
            ],
        )
    return True


def _erasure_removal_recorded(db: Session, membership_id: UUID) -> bool:
    """Whether this tenant's chain holds the erasure-marked removal of ``membership_id``."""
    return (
        db.execute(
            select(audit_event.c.id).where(
                audit_event.c.action == users.REMOVE_ACTION,
                audit_event.c.object_id == membership_id,
                audit_event.c.detail.op("->>")("erasure") == "true",
            )
        ).first()
        is not None
    )


def _completion_recorded(db: Session, user_id: UUID) -> bool:
    return (
        db.execute(
            select(audit_event.c.id).where(
                audit_event.c.action == ANONYMISE_ACTION, audit_event.c.object_id == user_id
            )
        ).first()
        is not None
    )


def erasure_tenants(
    user_id: UUID, *, exclude_tenant_id: UUID | None, request_id: str
) -> tuple[tuple[UUID, UUID, bool], ...]:
    """(tenant id, membership id, completion recorded) of every workspace whose own chain holds the
    erasure-marked removal of the person's membership: the durable, state-derived set of workspaces
    owed an ``app_user.anonymise`` completion event (04 T-PLT-02: AUD-CMD changes of ``app_user``
    are written to each tenant in which the user is ACTIVE), and whether each already has it. The
    set is derived from the tenants' chains alone, INDEPENDENTLY of the workspace that runs the
    request (Codex P8-PRV07-COMPLETE-1, production-20260921-2359): the erasing workspace is never
    owed because its own ``app_user.anonymise`` event — the original global-change audit — counts
    as recorded, and a workspace that retries through the person's removed membership there is
    included like any other. ``exclude_tenant_id`` names the workspace completing in the caller's
    open transaction (the first run's acting tenant), whose chain cannot be read consistently yet.
    Nothing here lives in memory between requests."""
    found: list[tuple[UUID, UUID, bool]] = []
    for tenant_id, membership_id, _status in mfa.user_memberships(user_id, request_id=request_id):
        if exclude_tenant_id is not None and tenant_id == exclude_tenant_id:
            continue
        with tenant_session(_other_context(tenant_id), read_only=True) as db:
            if _erasure_removal_recorded(db, membership_id):
                found.append((tenant_id, membership_id, _completion_recorded(db, user_id)))
    return tuple(found)


def completion_next_step(pending: Sequence[UUID]) -> str | None:
    """The administrator's next step when other workspaces are still owed their completion event,
    stated in the 200 response so completion never depends on someone remembering (RB-14 step 2);
    ``None`` when nothing is owed. eRev delivers nothing in the background."""
    if not pending:
        return None
    ids = ", ".join(str(tenant_id) for tenant_id in pending)
    return (
        f"Run this command again with a new Idempotency-Key to write the app_user.anonymise "
        f"completion event in {len(pending)} other workspace(s) ({ids}); an administrator of an "
        "owed workspace may run it there through the person's removed membership. Nothing "
        "completes in the background."
    )


def _deliver_completion(
    erasure: _Erasure, tenant_id: UUID, membership_id: UUID, *, completed_at: datetime
) -> bool:
    """Write the ``app_user.anonymise`` completion event in one other workspace, after the global
    identity change is durable: the tenant's chain is checked under the transaction and an event
    already present is never written twice. The after-state is the erased identity as it now is;
    the before-state (old e-mail in the PRV-04 HMAC form) lives in the acting tenant's event, since
    the old values are gone by the time this event can truthfully be written."""
    with tenant_session(_other_context(tenant_id)) as db:
        if _completion_recorded(db, erasure.user_id):
            return False
        append_events(
            db,
            tenant_id=tenant_id,
            keyring=erasure.keyring,
            events=[
                build_event(
                    tenant_id=tenant_id,
                    actor=erasure.actor,
                    occurred_at=erasure.now,
                    action=ANONYMISE_ACTION,
                    object_type=USER_OBJECT,
                    object_id=erasure.user_id,
                    after={
                        "email": erased_email(erasure.user_id),
                        "display_name": erased_display_name(erasure.user_id),
                        "status": UserStatus.DISABLED.value,
                    },
                    comment=erasure.comment,
                    detail={
                        "acting_tenant_id": str(erasure.acting_tenant_id),
                        "membership_id": str(membership_id),
                        "identity_erased_at": completed_at.isoformat(),
                        "delivery": "completion after the global commit",
                    },
                )
            ],
        )
    return True


def _erasure_of(uow: UnitOfWork, user_id: UUID, comment: str) -> _Erasure:
    principal = uow.principal
    return _Erasure(
        user_id=user_id,
        acting_tenant_id=principal.tenant_id,
        actor=replace(actor_of(uow.ctx), roles=(), support_grant_id=None),
        now=uow.now,
        principal_id=principal.id,
        principal_kind=principal.kind.value,
        comment=comment,
        keyring=uow.keyring,
    )


def anonymise_user(uow: UnitOfWork, membership_id: UUID, *, reason: str | None) -> AnonymiseResult:
    """``POST /users/{membership_id}/anonymise`` (05 PRV-07 a).

    Checks, in order: 403 ``mfa-step-up-required`` without a verification at most five minutes old;
    404 for an unknown membership or a platform operator's identity (D-80); 403 ``forbidden`` for
    the caller's own membership; 422 without a reason of at least 10 characters (SB-R-05, as every
    membership command).

    First run (identity not yet erased). 1. The person's memberships in OTHER workspaces are
    removed first, one workspace transaction each — durable as each commits, already removed rows
    skipped without re-audit — and each of those workspaces records ONLY its membership removal
    (``tenant_membership.remove``, marked ``erasure``). A failure there raises while nothing of
    the acting tenant has changed: the response is the problem, never a stored success, and a
    repeated command resumes the removals still owed. 2. In the caller's transaction:
    ``app_user`` becomes ``Erased user <8 hex>`` / ``erased+<id>@invalid.erev`` with
    ``password_hash``, ``external_id`` and ``identity_provider_subject`` null and status
    ``DISABLED``; every open session of the
    person ends ``REVOKED``; the acting tenant's membership is removed through
    ``users.remove_membership`` unless already ``REMOVED``; one ``app_user.anonymise`` event
    records the change with the old e-mail in the PRV-04 HMAC form, never the old display name in
    clear, and the counts of THIS request measured after the work, plus the list of other
    workspaces still owed their completion event.

    Resume run (identity already erased). The other workspaces whose chains hold the
    erasure-marked removal and no ``app_user.anonymise`` event yet receive it now, one workspace
    transaction each (04 T-PLT-02: AUD-CMD changes of ``app_user`` are written to each tenant in
    which the user is ACTIVE; the event can be truthfully written only after the global change is
    durable, and no in-memory hook is used, so the delivery is this second, idempotent run). With
    nothing owed the command answers 409 ``invalid-transition`` / ``PRV-07``.
    """
    principal = uow.principal
    if not mfa.step_up_fresh_at(principal.mfa_verified_at, uow.now):
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)
    membership = _lock_membership(uow, membership_id)
    user_id = UUID(str(membership["user_id"]))
    user = _lock_user(uow, user_id)
    if user["is_operator"]:
        raise Problem("not-found")
    if membership["id"] == principal.membership_id:
        raise Problem("forbidden", users.SELF_DETAIL)
    # REQ-PLT-012: the erasure removes the member here, so it needs the same scope as a removal
    users.require_member_scope(uow, membership_id, action=ANONYMISE_ACTION)
    comment = users.require_reason(reason)
    erasure = _erasure_of(uow, user_id, comment)
    request_id = uow.ctx.request_id
    new_email = erased_email(user_id)
    if str(user["email"]) == new_email:
        # Resume path: deliver the completion events still owed; nothing else remains. Any workspace
        # of the person may run it — the erasing one or an owed one through the removed membership
        # (the caller's own `user.manage`, step-up and RLS-visible membership are the authorization;
        # nothing is widened) — because the owed set comes from the tenants' chains, not from who
        # is asking (Codex production-20260921-2359).
        completed_at: datetime = user["updated_at"]
        delivered = tuple(
            tenant_id
            for tenant_id, other_id, recorded in erasure_tenants(
                user_id, exclude_tenant_id=None, request_id=request_id
            )
            if not recorded
            and _deliver_completion(erasure, tenant_id, other_id, completed_at=completed_at)
        )
        if not delivered:
            raise Problem(
                "invalid-transition",
                errors=[ProblemError(field="status", rule_id=RULE_ERASURE, message=ALREADY_ERASED)],
            )
        return AnonymiseResult(
            user_id=user_id,
            membership_id=membership_id,
            sessions_ended=0,
            membership_removed=False,
            other_memberships_removed=(),
            other_memberships_already_removed=0,
            other_memberships_skipped_removed=0,
            completion_pending=(),
            completion_events_delivered=delivered,
        )
    # 1. The other workspaces first, each durable in its own transaction, removals only.
    memberships = mfa.user_memberships(user_id, request_id=request_id)
    pending = pending_secondary_memberships(memberships, principal.tenant_id)
    skipped_removed = sum(
        1
        for tenant_id, _other_id, status in memberships
        if tenant_id != principal.tenant_id and status == MembershipStatus.REMOVED.value
    )
    removed_elsewhere: list[tuple[UUID, UUID]] = []
    already_removed = 0
    for tenant_id, other_id in pending:
        if _remove_membership_in_tenant(erasure, tenant_id, other_id):
            removed_elsewhere.append((tenant_id, other_id))
        else:
            already_removed += 1
    completion_pending = tuple(
        tenant_id
        for tenant_id, _other_id, recorded in erasure_tenants(
            user_id, exclude_tenant_id=principal.tenant_id, request_id=request_id
        )
        if not recorded
    )
    # 2. The acting tenant, in the caller's transaction.
    session = uow.session
    open_sessions = session.execute(
        select(func.count())
        .select_from(user_session)
        .where(user_session.c.user_id == user_id, user_session.c.ended_at.is_(None))
    ).scalar_one()
    session.execute(
        update(app_user)
        .where(app_user.c.id == user_id)
        .values(
            email=new_email,
            display_name=erased_display_name(user_id),
            password_hash=None,
            external_id=None,
            identity_provider_subject=None,
            status=UserStatus.DISABLED.value,
            **_updated(uow),
        )
    )
    end_user_sessions(session, user_id, reason=SessionEndReason.REVOKED, now=uow.now)
    membership_removed = membership["status"] != MembershipStatus.REMOVED.value
    if membership_removed:
        users.remove_membership(uow, membership_id, reason=comment)
    uow.audit(
        action=ANONYMISE_ACTION,
        object_type=USER_OBJECT,
        object_id=user_id,
        before={
            "email": user["email"],
            "status": user["status"],
            "password_set": user["password_hash"] is not None,
            "external_id_set": user["external_id"] is not None,
        },
        after={
            "email": new_email,
            "display_name": erased_display_name(user_id),
            "status": UserStatus.DISABLED.value,
            "password_set": False,
            "external_id_set": False,
        },
        comment=comment,
        detail={
            "membership_id": str(membership_id),
            "sessions_ended": int(open_sessions),
            "count_scope": "this request only; skipped_removed = rows enumerated REMOVED "
            "before the work (an earlier attempt's completed part, never re-audited); "
            "already_removed = rows the helper found REMOVED or missing after enumeration",
            "other_memberships_removed": len(removed_elsewhere),
            "other_memberships_already_removed": already_removed,
            "other_memberships_skipped_removed": skipped_removed,
            "other_tenants_removed_now": [str(tenant_id) for tenant_id, _ in removed_elsewhere],
            "other_tenants_completion_pending": [
                str(tenant_id) for tenant_id in completion_pending
            ],
        },
    )
    return AnonymiseResult(
        user_id=user_id,
        membership_id=membership_id,
        sessions_ended=int(open_sessions),
        membership_removed=membership_removed,
        other_memberships_removed=tuple(removed_elsewhere),
        other_memberships_already_removed=already_removed,
        other_memberships_skipped_removed=skipped_removed,
        completion_pending=completion_pending,
        completion_events_delivered=(),
    )


# ---- PRV-07 b: file.shred


def retention_active(row: Mapping[str, Any], today: date) -> bool:
    """04 table 15.4-B ``FILE_RETENTION_ACTIVE``: ``legal_hold``, or ``retention_until`` after
    ``today`` (the UTC date of the command's clock; a retention ending today is not active)."""
    until = row.get("retention_until")
    return bool(row.get("legal_hold")) or (until is not None and until > today)


def shred_supported(purpose: FilePurpose) -> bool:
    """A purpose stored under a per-file data key (05 PRV-06; ``policy.ENCRYPTED_PURPOSES``): the
    only kind whose bytes a sidecar shred makes unreadable. Plaintext purposes are refused until the
    privacy owner rules on their erasure (D-98 145 addendum (2))."""
    return purpose in policy.ENCRYPTED_PURPOSES


def shred_refusal(
    row: Mapping[str, Any], today: date, *, held: file_evidence.Hold | None = None
) -> Problem | None:
    """The refusal ``file.shred`` returns for ``row`` before any write, in order: already shredded
    (409 ``invalid-transition`` / ``FILE_SHREDDED``, refused by name as FILES-SHRED-1 rules), legal
    hold or future retention (``FILE_RETENTION_ACTIVE``), the evidence of a standing record
    (``held`` is the record ``file_evidence.first_refusing`` names — rulings R-30, R-49 and R-86:
    refused by reference, whatever the retention columns say; ``FILE_EVIDENCE_HELD``, or
    ``FILE_SHRED_APPROVAL_REQUIRED`` for a hold that an approved ``EVIDENCE_SHRED`` request
    lifts), plaintext purpose (``PRV-06``)."""
    if row.get("shredded_at") is not None:
        return Problem(
            "invalid-transition",
            errors=[ProblemError(field="status", rule_id=RULE_SHREDDED, message=SHREDDED_MESSAGE)],
        )
    if retention_active(row, today):
        return Problem(
            "invalid-transition",
            errors=[
                ProblemError(
                    field="status", rule_id=RULE_RETENTION_ACTIVE, message=RETENTION_ACTIVE_MESSAGE
                )
            ],
        )
    if held is not None:
        return Problem(
            "invalid-transition",
            errors=[
                ProblemError(
                    field="status",
                    rule_id=file_evidence.held_rule(held),
                    message=file_evidence.held_message(held),
                )
            ],
        )
    if not shred_supported(FilePurpose(str(row["purpose"]))):
        return Problem(
            "invalid-transition",
            errors=[
                ProblemError(
                    field="purpose",
                    rule_id=RULE_PLAINTEXT_PURPOSE,
                    message=PLAINTEXT_PURPOSE_MESSAGE,
                )
            ],
        )
    return None


def refuse_shared_in_sandbox(
    uow: UnitOfWork, row: Mapping[str, Any], *, action: str, detail: Mapping[str, Any]
) -> None:
    """05 SBX-08: a sandbox destroys nothing it shares with the workspace it was copied from, and
    what it stored itself is its own. Pass for a file whose storage key is the workspace's own
    (``files.store.owns_key``: the key's first segment is the workspace's id) — a sandbox's own
    upload has no other erasure path, a reset deleting nothing. For any other key the production
    guard decides: a production workspace passes, and a sandbox records the attempt ``DENIED``
    under ``action`` and answers 403 ``sandbox-restricted``. The three commands that destroy a
    stored file call this once they hold the file's row and before anything else of the file is
    looked at (``tests/architecture/test_ensure_production.py``)."""
    if owns_key(uow.principal.tenant_id, str(row["storage_key"])):
        return
    guards.ensure_production(
        uow,
        action=action,
        object_type=FILE_OBJECT,
        object_id=UUID(str(row["id"])),
        detail=detail,
        message=SANDBOX_SHRED,
    )


def refuse_beyond_scope(
    uow: UnitOfWork, row: Mapping[str, Any], *, action: str, reason: str, refusal: Problem
) -> None:
    """Pass when the caller's ``settings.manage`` covers every entity of the records that
    reference the file (``file_access.referencing_scopes``: every entity for a record that names
    none, and for a file no record references); otherwise record the attempt as a ``DENIED``
    event of ``action`` and raise ``refusal`` (04 T-PLT-29 "Shred scope"; item
    FILE-SHRED-SCOPE-1, B3). It stands before every refusal that names a record, so that a
    refusal by reference is read only by a caller whose scope covers the record (B5): the event
    names the file, the rule and the reason given — never a record or an entity."""
    held = entity_scope.held_scope(uow.principal, SHRED_PERMISSION)
    bound = file_access.referencing_scopes(uow.principal.tenant_id, UUID(str(row["id"])))
    if entity_scope.covers(held, bound):
        return
    audit_writer.record_denied(
        uow.ctx,
        action=action,
        object_type=FILE_OBJECT,
        object_id=UUID(str(row["id"])),
        permission=SHRED_PERMISSION,
        detail={
            **users.scope_denial(),
            "sha256": str(row["sha256"]),
            "purpose": str(row["purpose"]),
            "reason": reason.strip(),
        },
        keyring=uow.keyring,
    )
    raise refusal


def _versioned(files: FileStore) -> VersionedFileStore:
    """The store's generation primitives; a backend without them is a deployment defect, never a
    silent no-op shred."""
    for name in ("versions", "delete_generation", "live_generation"):
        if not callable(getattr(files, name, None)):
            raise RuntimeError(f"file store {type(files).__name__} has no {name}(); cannot shred")
    return cast(VersionedFileStore, files)


def shred_file(
    uow: UnitOfWork, file_id: UUID, *, reason: str, files: FileStore
) -> Mapping[str, Any]:
    """``POST /files/{id}/shred`` (05 PRV-07 b; runbook RB-14).

    404 for an unknown file. In a sandbox a file it shares with the workspace it was copied from
    is refused next, 403 ``sandbox-restricted`` with its ``DENIED`` event
    (:func:`refuse_shared_in_sandbox`; 05 SBX-08 rev 1.164) — a sandbox destroys nothing it
    shares; a file it stored itself is its own and goes on as in production.

    403 ``forbidden`` for a caller whose ``settings.manage`` does not
    cover every entity of the records that reference the file (:func:`refuse_beyond_scope`, asked
    before any refusal that names a record); then :func:`shred_refusal` — a file that a standing
    record references as its evidence (``file_evidence.holds``, read over every entity of the
    tenant) is refused by reference. Every refusal is written as a ``DENIED`` audit event that
    names its rule, and for an evidence file the record (DG-KRN-AUTH-05; rulings R-30, R-49 and
    R-86 (f): one rule for every refusal of a destructive command). Then the DECISION of the
    shred (:func:`_decide`): the row is marked and the event written, and the store is not
    touched; the key is destroyed after this unit of work commits (:func:`continuation`).

    Sent again for a row that is decided and whose completion is not recorded, the command
    finishes the shred in its own transaction and answers the row (05 PRV-07 b rev 1.171, road
    two) — after the sandbox question, the scope and the reason, and without asking a hold
    again: the decision is durable, and its holds were lifted or absent when it was taken. A
    store that still holds a live sidecar after the passes (``GenerationConflict``: something
    restored it beside the shred) answers 409 ``lock-conflict``; nothing was saved, the marker
    stands and the next attempt deletes what is left. A row whose completion is recorded is
    refused as before, ``FILE_SHREDDED``. Returns the updated row."""
    session = uow.session
    locked = (
        session.execute(select(file_object).where(file_object.c.id == file_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if locked is None:
        raise Problem("not-found")
    row: Mapping[str, Any] = dict(locked)
    refuse_shared_in_sandbox(uow, row, action=SHRED_ACTION, detail={"reason": reason.strip()})
    refuse_beyond_scope(
        uow, row, action=SHRED_ACTION, reason=reason, refusal=users.beyond_scope(SHRED_BEYOND_SCOPE)
    )
    comment = reason.strip()
    if not comment:
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="reason", rule_id=RULE_ERASURE, message="Enter a reason.")],
        )
    if row["shredded_at"] is not None and row["shred_completed_at"] is None:
        try:
            finished = _complete(uow, row, road=ROAD_RETRY, files=files, comment=comment)
        except GenerationConflict as conflict:
            raise Problem("lock-conflict", LOCK_CONFLICT_DETAIL) from conflict
        if finished is not None:
            return finished
    today = uow.now.date()
    held = (
        None
        if row["shredded_at"] is not None or retention_active(row, today)
        else file_evidence.holding(uow.principal.tenant_id, file_id)
    )
    refusal = shred_refusal(row, today, held=held)
    if refusal is not None:
        # The refusal is the recorded outcome of the request (R-49 (b); runbook RB-14).
        detail: dict[str, Any] = {
            "rule_id": refusal.errors[0].rule_id,
            "sha256": str(row["sha256"]),
            "purpose": str(row["purpose"]),
            "reason": comment,
        }
        if held is not None and refusal.errors[0].rule_id == file_evidence.held_rule(held):
            detail["held_by"] = held.held_by
            detail["record"] = held.record
        audit_writer.record_denied(
            uow.ctx,
            action=SHRED_ACTION,
            object_type=FILE_OBJECT,
            object_id=file_id,
            permission=SHRED_PERMISSION,
            detail=detail,
            keyring=uow.keyring,
        )
        raise refusal
    decided = _decide(uow, row, comment=comment)
    uow.after_commit(
        continuation(uow.ctx, file_id, clock=uow.clock, keyring=uow.keyring, files=files)
    )
    return decided


def shred_approved(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    *,
    reason: str,
    approval_request_id: UUID,
    lifted: Sequence[file_evidence.Hold],
) -> Mapping[str, Any]:
    """The shred an approved ``EVIDENCE_SHRED`` request decides (rulings R-49 (a), R-86):
    ``uow`` is the SYSTEM principal on behalf of the requester, ``row`` the ``file_object`` row
    the caller holds locked, ``lifted`` the holds the approval lifts — the caller has established
    that they are exactly the records that hold the file now, each one liftable by an approval
    (``evidence_shred``). The file's own refusals stand: already shredded, legal hold or
    retention, a plaintext purpose. The audit event names the approval and the records.

    This is the decision alone (:func:`_decide`): it takes no file store, and nothing of the
    store is touched in the decision's transaction. The caller registers :func:`continuation`
    on the unit of work that commits the decision — ``uow`` here shares that transaction and is
    never committed itself — with ``uow.ctx``, so that the completion's event carries the same
    principal."""
    refusal = shred_refusal(row, uow.now.date())
    if refusal is not None:
        raise refusal
    return _decide(
        uow,
        row,
        comment=reason.strip(),
        approval_request_id=approval_request_id,
        lifted=[hold.record for hold in lifted],
    )


def _decide(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    *,
    comment: str,
    approval_request_id: UUID | None = None,
    lifted: Sequence[str] = (),
) -> Mapping[str, Any]:
    """The decision of a shred no refusal stands against, in the command's transaction: the row's
    ``shredded_at`` / ``shredded_by`` / ``shredded_by_kind`` / ``shred_reason`` are set once
    (IM-A, DB-03) and one ``file_object.shred`` audit event names the file id, its SHA-256 and
    storage key — and, for an approved shred, the approval request and the records whose hold it
    lifted. The store is not touched: until this transaction commits nothing is destroyed, and
    from then on the marked row is the durable intent that :func:`complete_shred` carries out
    (05 PRV-07 b rev 1.171). The store's report is on the completion's event."""
    session = uow.session
    file_id = UUID(str(row["id"]))
    now: datetime = uow.now
    principal = uow.principal
    session.execute(
        update(file_object)
        .where(file_object.c.id == file_id, file_object.c.shredded_at.is_(None))
        .values(
            shredded_at=now,
            shredded_by=principal.id,
            shredded_by_kind=principal.kind.value,
            shred_reason=comment,
        )
    )
    detail: dict[str, Any] = {
        "file_id": str(file_id),
        "sha256": str(row["sha256"]),
        "purpose": str(row["purpose"]),
        "storage_key": str(row["storage_key"]),
    }
    if lifted:
        detail["lifted_holds"] = list(lifted)
    uow.audit(
        action=SHRED_ACTION,
        object_type=FILE_OBJECT,
        object_id=file_id,
        before={"shredded_at": None},
        after={
            "shredded_at": now,
            "shredded_by": None if principal.id is None else str(principal.id),
            "shredded_by_kind": principal.kind.value,
            "shred_reason": comment,
        },
        comment=comment,
        detail=detail,
        approval_request_id=approval_request_id,
    )
    updated = (
        session.execute(select(file_object).where(file_object.c.id == file_id)).mappings().one()
    )
    return dict(updated)


def complete_shred(
    uow: UnitOfWork, file_id: UUID, *, road: str, files: FileStore
) -> Mapping[str, Any] | None:
    """Carry out a decided shred in ``uow``'s transaction (05 PRV-07 b rev 1.171): the one
    function behind the three roads. The file's row is locked first, so two roads that meet wait
    for each other and the second finds the completion recorded. Returns the updated row, or
    None when there was nothing to finish — no such file, a file not decided, a completion
    already recorded, or a key that is not this workspace's own (:func:`_complete`). The caller
    commits; a failure leaves the row decided and not completed, for the next road."""
    locked = (
        uow.session.execute(
            select(file_object).where(file_object.c.id == file_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if locked is None:
        return None
    return _complete(uow, dict(locked), road=road, files=files)


def _complete(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    *,
    road: str,
    files: FileStore,
    comment: str | None = None,
) -> Mapping[str, Any] | None:
    """The store's part of a decided shred, for ``row`` held locked: under the key's advisory
    lock ``lifecycle.shred_sidecar`` writes the durable marker and deletes every retained sidecar
    generation (the payload and ``sha256`` stay as evidence, D-43); ``shred_completed_at`` is set
    once (IM-A, DB-03) and one ``file_object.shred_complete`` audit event carries the store's
    report — the generations deleted, the residual soft-deleted generations with their
    hard-delete horizon (OPR-10) and the marker's own instant — the road, and the instant of the
    decision. It is written by whoever finishes: the principal of the decision on the command's
    continuation, the administrator who sent ``file.shred`` again, SYSTEM for the sweep.

    Idempotent on a key already destroyed: after a crash between the store's delete and this
    event the next road finds the marker, deletes nothing (``marker_created`` false, an empty
    list) and records the completion with the marker's instant, which says when the destruction
    began. ``GenerationConflict`` — a generation live again after the passes — propagates: the
    transaction rolls back, the row stays decided, the marker stands, and the next road deletes
    what is left.

    Only a key the workspace owns is destroyed (05 SBX-08): a sandbox's copy of a row that was
    decided in its source carries the mark and the source's key, and is finished there."""
    if row["shredded_at"] is None or row["shred_completed_at"] is not None:
        return None
    storage_key = str(row["storage_key"])
    if not owns_key(uow.principal.tenant_id, storage_key):
        return None
    session = uow.session
    file_id = UUID(str(row["id"]))
    report = lifecycle.shred_sidecar(_versioned(files), storage_key, session=session)
    now: datetime = uow.now
    session.execute(
        update(file_object)
        .where(file_object.c.id == file_id, file_object.c.shred_completed_at.is_(None))
        .values(shred_completed_at=now)
    )
    decided_at: datetime = row["shredded_at"]
    uow.audit(
        action=COMPLETE_ACTION,
        object_type=FILE_OBJECT,
        object_id=file_id,
        before={"shred_completed_at": None},
        after={"shred_completed_at": now},
        comment=comment,
        detail={
            "file_id": str(file_id),
            "sha256": str(row["sha256"]),
            "purpose": str(row["purpose"]),
            "storage_key": storage_key,
            "road": road,
            "decided_at": decided_at.isoformat(),
            "marker_created": report.marker_created,
            "marker_at": None if report.marker_at is None else report.marker_at.isoformat(),
            "deleted_generations": list(report.deleted_generations),
            "retained_generations": len(report.retained),
            "irreversible_after": (
                None if report.irreversible_after is None else report.irreversible_after.isoformat()
            ),
        },
    )
    updated = (
        session.execute(select(file_object).where(file_object.c.id == file_id)).mappings().one()
    )
    return dict(updated)


def continuation(
    ctx: RequestContext, file_id: UUID, *, clock: Clock, keyring: KeyRing, files: FileStore
) -> Callable[[], None]:
    """Road one (05 PRV-07 b rev 1.171): what the unit of work that commits a decision runs after
    its commit (``UnitOfWork.after_commit``) — the completion in a unit of work of its own, for
    the same principal, before the request is answered. A failure is logged by name, values-free,
    and raised to the unit of work, which logs it and lets the command's answer stand: the
    decision is committed, the row says that the completion is owed, and ``file.shred`` sent
    again or the sweep finishes it."""
    from erev_api.uow import unit_of_work

    def finish_shred() -> None:
        try:
            with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as own:
                complete_shred(own, file_id, road=ROAD_COMMAND, files=files)
                own.commit()
        except Exception as error:
            get_logger(_LOGGER).warning(
                "file_shred.completion_failed",
                file_id=str(file_id),
                road=ROAD_COMMAND,
                error_type=type(error).__name__,
            )
            raise

    return finish_shred
