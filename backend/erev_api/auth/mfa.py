"""Multi-factor authentication KRN-AUTH (04 T-PLT-04, T-PLT-05, T-PLT-08 ``mfa_verified_at``; 05
SAR-07, SAR-09, SAR-26, THR-03; 03 REQ-PLT-005; BUILD_SPEC BS1-D-19, BS1-D-30).

The identity repositories behind enrolment, the sign-in challenge and recovery codes
(DG-KRN-DB-02). A seed is stored as a KEY-04 envelope bound to its factor row; recovery codes are
argon2id hashes, ten per batch, and only the newest batch is valid. Confirming enrolment and
verifying a challenge rotate the session with ``mfa_verified_at`` set to the request time (SAR-09).
A wrong code commits ``MFA_CHALLENGE_FAILED`` before the 422 is raised.

``next_step`` states the second-factor step a session still owes. The rule is the user's, not the
route's (REQ-PLT-005; SAR-26): the sign-in answers and ``GET /session`` show it, and
``auth.dependencies`` refuses a session that owes a step on every route but the ones that settle
it (DG-KRN-AUTH-03).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import RowMapping, func, insert, select, update
from sqlalchemy.orm import Session

from erev_api.audit.chain import append_events
from erev_api.audit.writer import AuditActor, build_event
from erev_api.auth import passwords, sessions, totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import Grants, effective_grants, spec, standing_delegations
from erev_api.auth.security_events import record_security_event
from erev_api.auth.sessions import AuthenticatedSession, SessionRow
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    app_user,
    security_event,
    tenant_membership,
    user_mfa_factor,
    user_recovery_code,
)
from erev_api.db.transitions import apply
from erev_api.enums import (
    AuditOutcome,
    IdentityProviderKind,
    MembershipStatus,
    PrincipalKind,
    SecurityEventKind,
)
from erev_api.problems import Problem, ProblemError

TOTP_FACTOR: Final = "TOTP"
RECOVERY_CODE_COUNT: Final = 10  # REQ-PLT-005
# Lowercase letters and digits without 0, 1, i, l and o; codes read "4k7p-2m9x" (SCREENS_B §12.2).
RECOVERY_ALPHABET: Final = "23456789abcdefghjkmnpqrstuvwxyz"
RECOVERY_HALF: Final = 4
STEP_UP_WINDOW: Final = timedelta(minutes=5)  # BS1-D-19; PRD BR-PLT-06
MAX_CHALLENGE_FAILURES: Final = 5  # D-80, as REQ-PLT-004 for passwords
ENROL_ACTION: Final = "mfa_factor.enrol"
RESET_ACTION: Final = "user_mfa_factor.reset"
FACTOR_OBJECT: Final = "user_mfa_factor"

# PRD ERR-27, ERR-28 and SCREENS_B §12.1, §12.2 copy.
ENROLMENT_REQUIRED: Final = (
    "Set up multi-factor authentication to continue. "
    "Your roles include approval or administration permissions."
)
VERIFICATION_REQUIRED: Final = "Verify with your authenticator app to continue."
# 04 §15.2, API-C-03: what a session that owes a second-factor step is answered; the ERR-27 copy
# (``ENROLMENT_REQUIRED`` or ``VERIFICATION_REQUIRED``) says which step.
SECOND_FACTOR_SLUG: Final = "mfa-required"
STEP_UP_REQUIRED: Final = "Enter a code from your authenticator app to continue."
WRONG_CODE: Final = "That code did not match. Check your authenticator app and try again."
WRONG_ENROLMENT_CODE: Final = (
    "That code did not match. Check the time on your device and try again."
)
# [J] Copy of the 409 refusals, which the documents leave open (SPEC-Q-144).
ALREADY_ENROLLED: Final = "Multi-factor authentication is already set up."
NOT_ENROLLED: Final = "Set up multi-factor authentication first."
START_ENROLMENT: Final = "Start the multi-factor authentication setup first."


@dataclass(frozen=True, slots=True)
class Enrolment:
    otpauth_uri: str
    secret_base32: str


# The second-factor step a session owes (REQ-PLT-005): enrol a factor, or answer the challenge.
PendingStep = Literal["enrolment", "challenge"]
# (tenant id, membership id) → the membership's grants in force at the request time.
GrantsLoader = Callable[[UUID, UUID], Grants]


@dataclass(frozen=True, slots=True)
class NextStep:
    mfa_required: bool
    mfa_enrolment_required: bool

    @property
    def pending(self) -> PendingStep | None:
        """The step the session still owes; None for a session that owes none."""
        if self.mfa_enrolment_required:
            return "enrolment"
        return "challenge" if self.mfa_required else None


@dataclass(frozen=True, slots=True)
class Verified:
    auth: AuthenticatedSession
    recovery_codes_remaining: int | None


def _secret_context(factor_id: UUID) -> dict[str, str]:
    """SAR-07 associated data of a seed; T-PLT-04 is global, so no tenant id takes part."""
    return {"table": "user_mfa_factor", "column": "secret_ciphertext", "row_id": str(factor_id)}


def secret_context(factor_id: UUID) -> dict[str, str]:
    """The SAR-07 associated data of a factor's sealed seed, for the recovery verifier's envelope
    probe (``controls.recovery``; review P6-R5): the same context ``enroll`` sealed under."""
    return _secret_context(factor_id)


def _active_factor(db: Session, user_id: UUID, *, lock: bool = False) -> RowMapping | None:
    statement = select(
        user_mfa_factor.c.id,
        user_mfa_factor.c.secret_ciphertext,
        user_mfa_factor.c.confirmed_at,
        user_mfa_factor.c.last_used_step,
        user_mfa_factor.c.updated_at,
    ).where(user_mfa_factor.c.user_id == user_id, user_mfa_factor.c.disabled_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    return db.execute(statement).mappings().one_or_none()


def _secret(keyring: KeyRing, factor: RowMapping) -> str:
    blob = bytes(factor["secret_ciphertext"])
    return keyring.decrypt(blob, context=_secret_context(factor["id"])).decode("ascii")


def _event(
    db: Session,
    keyring: KeyRing,
    auth: AuthenticatedSession,
    kind: SecurityEventKind,
    outcome: AuditOutcome,
    *,
    session_id: UUID,
    detail: dict[str, Any],
) -> None:
    facts = auth.facts
    record_security_event(
        db,
        keyring=keyring,
        kind=kind,
        outcome=outcome,
        request_id=facts.request_id,
        user_id=auth.user.id,
        session_id=session_id,
        ip_address=facts.source_ip,
        user_agent=facts.user_agent,
        detail=detail,
    )


def _wrong_code(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed", message, errors=[ProblemError(field=field, message=message)]
    )


def _active_memberships(user_id: UUID, *, request_id: str) -> list[tuple[UUID, UUID]]:
    """(tenant id, membership id) of the user's ACTIVE memberships (RLS-TM self policy)."""
    with identity_session(request_id=request_id, user_id=user_id) as db:
        rows = db.execute(
            select(tenant_membership.c.tenant_id, tenant_membership.c.id)
            .where(
                tenant_membership.c.user_id == user_id,
                tenant_membership.c.status == MembershipStatus.ACTIVE.value,
            )
            .order_by(tenant_membership.c.tenant_id)
        ).all()
    return [(UUID(str(tenant_id)), UUID(str(membership_id))) for tenant_id, membership_id in rows]


def user_memberships(user_id: UUID, *, request_id: str) -> list[tuple[UUID, UUID, str]]:
    """(tenant id, membership id, status) of every membership of the user, in tenant order
    (RLS-TM self policy). 05 PRV-07 a sets each of them ``REMOVED`` from the acting tenant's unit of
    work, so the erasure command needs the platform-wide view only this module may open
    (DG-KRN-DB-02)."""
    with identity_session(request_id=request_id, user_id=user_id) as db:
        rows = db.execute(
            select(
                tenant_membership.c.tenant_id, tenant_membership.c.id, tenant_membership.c.status
            )
            .where(tenant_membership.c.user_id == user_id)
            .order_by(tenant_membership.c.tenant_id)
        ).all()
    return [
        (UUID(str(tenant_id)), UUID(str(membership_id)), str(status))
        for tenant_id, membership_id, status in rows
    ]


def has_confirmed_factor(user_id: UUID, *, request_id: str) -> bool:
    with identity_session(request_id=request_id, user_id=user_id) as db:
        factor = _active_factor(db, user_id)
    return factor is not None and factor["confirmed_at"] is not None


def membership_grants(auth: AuthenticatedSession, tenant_id: UUID, membership_id: UUID) -> Grants:
    """The grants of one of the user's memberships in force at the request time."""
    context = DbContext(tenant_id=tenant_id, user_id=auth.user.id, entity_scope="*")
    with tenant_session(context, read_only=True) as db:
        return effective_grants(db, membership_id, at=auth.facts.now)


def delegated_permissions(
    auth: AuthenticatedSession, tenant_id: UUID, membership_id: UUID
) -> frozenset[str]:
    """The permissions one of the user's memberships holds through the approval delegations
    that stand at the request time (04 T-PLT-21; ``permissions.standing_delegations``)."""
    context = DbContext(tenant_id=tenant_id, user_id=auth.user.id, entity_scope="*")
    with tenant_session(context, read_only=True) as db:
        found = standing_delegations(db, at=auth.facts.now, delegate_membership_id=membership_id)
    return frozenset(code for delegation in found for code in delegation.permissions)


def _requires_mfa(code: str) -> bool:
    """``spec(code).requires_mfa``; a code the catalogue no longer holds counts as requiring it
    (a delegation row keeps the codes it was given)."""
    try:
        return spec(code).requires_mfa
    except KeyError:
        return True


def holds_mfa_permission(auth: AuthenticatedSession, *, grants: GrantsLoader | None = None) -> bool:
    """Whether any ACTIVE membership holds a ``requires_mfa`` permission now (REQ-PLT-005):
    through its own grants, or through an approval delegation that stands — a delegate decides
    with the delegated permission, and reads what its holder reads to decide, so the second
    factor is owed like the holder's (03 REQ-PLT-005 rev 1.104; ruling R-111 (2)).

    ``grants`` reads a membership's grants; a request passes its own reader so the active
    membership is read once (``auth.dependencies``)."""
    facts = auth.facts
    for tenant_id, membership_id in _active_memberships(auth.user.id, request_id=facts.request_id):
        held = (
            membership_grants(auth, tenant_id, membership_id)
            if grants is None
            else grants(tenant_id, membership_id)
        )
        if any(spec(code).requires_mfa for code in held.permissions):
            return True
        if any(
            _requires_mfa(code) for code in delegated_permissions(auth, tenant_id, membership_id)
        ):
            return True
    return False


def mfa_mandatory(auth: AuthenticatedSession, *, grants: GrantsLoader | None = None) -> bool:
    """REQ-PLT-005: MFA is mandatory for a user who holds a ``requires_mfa`` permission in any
    ACTIVE membership — by grant or by a delegation that stands — and for a platform operator
    (DG-KRN-TEN-05)."""
    return auth.user.is_operator or holds_mfa_permission(auth, grants=grants)


def next_step(auth: AuthenticatedSession, *, grants: GrantsLoader | None = None) -> NextStep:
    """The second-factor step a session still owes (REQ-PLT-005; BS1-D-30; SCREENS_B §12.1).

    A verified session owes none. A user with a confirmed factor owes the challenge, whatever the
    user's permissions; without one, a user for whom MFA is mandatory owes enrolment (SPEC-Q-144).
    A verified session always has a confirmed factor behind it: only a confirmation or a challenge
    sets ``mfa_verified_at``, and an MFA reset ends every session of the user (SAR-10).
    """
    if auth.session.mfa_verified_at is not None:
        return NextStep(mfa_required=False, mfa_enrolment_required=False)
    if has_confirmed_factor(auth.user.id, request_id=auth.facts.request_id):
        return NextStep(mfa_required=True, mfa_enrolment_required=False)
    return NextStep(mfa_required=False, mfa_enrolment_required=mfa_mandatory(auth, grants=grants))


def record_pending_denied(
    auth: AuthenticatedSession, *, keyring: KeyRing, method: str, path: str, step: PendingStep
) -> None:
    """Write ``MFA_PENDING_DENIED``: a request refused because its session still owes ``step``,
    made with no workspace membership open — a user of several workspaces before one is chosen,
    an operator — so that no tenant audit log can hold the ``DENIED`` event such a refusal
    writes inside a workspace (05 SAR-26 rev 1.128; 04 E-79; ruling R-111 (6)). In a transaction
    of its own, committed before the caller raises the 403; ``path`` is the route's template."""
    facts = auth.facts
    active = auth.active_tenant
    with identity_session(request_id=facts.request_id, user_id=auth.user.id) as db:
        record_security_event(
            db,
            keyring=keyring,
            kind=SecurityEventKind.MFA_PENDING_DENIED,
            outcome=AuditOutcome.DENIED,
            request_id=facts.request_id,
            user_id=auth.user.id,
            session_id=auth.session.id,
            tenant_id=None if active is None else active.id,
            ip_address=facts.source_ip,
            user_agent=facts.user_agent,
            detail={"method": method, "path": path, "step": step},
        )


def step_up_fresh(auth: AuthenticatedSession) -> bool:
    """BS1-D-19: the session's MFA verification is at most five minutes old."""
    return step_up_fresh_at(auth.session.mfa_verified_at, auth.facts.now)


def step_up_fresh_at(verified_at: datetime | None, now: datetime) -> bool:
    """BS1-D-19 for a principal: an MFA verification at most five minutes before ``now``."""
    return verified_at is not None and now - verified_at <= STEP_UP_WINDOW


def enroll(
    auth: AuthenticatedSession, *, keyring: KeyRing, secret_base32: str | None = None
) -> Enrolment:
    """A new TOTP seed on the user's pending factor, created when absent (SAR-26).

    A confirmed factor gives 409 ``invalid-transition``; its seed is never shown again. Only the
    demo seed names the seed, from ``EREV_DEMO_TOTP_SECRET`` (PRD WLD-U-R2; BUILD_SPEC WEB-10);
    every other caller gets a random one. Issuing a seed is a security-relevant write:
    ``MFA_ENROLMENT_STARTED`` is written with the factor row (04 E-79, T-PLT-04; ruling R-50 (b)),
    ``detail.reseeded`` true when a pending factor got a new seed — never the seed itself.
    """
    facts = auth.facts
    secret = totp.new_secret() if secret_base32 is None else secret_base32
    with identity_session(request_id=facts.request_id, user_id=auth.user.id) as db:
        factor = _active_factor(db, auth.user.id, lock=True)
        if factor is not None and factor["confirmed_at"] is not None:
            raise Problem("invalid-transition", ALREADY_ENROLLED)
        factor_id = new_id() if factor is None else factor["id"]
        ciphertext = keyring.encrypt(secret.encode("ascii"), context=_secret_context(factor_id))
        values: dict[str, Any] = {
            "secret_ciphertext": ciphertext,
            "secret_key_id": keyring.envelope_key_id(ciphertext),
            "updated_by": auth.user.id,
            "updated_by_kind": PrincipalKind.USER.value,
        }
        if factor is None:
            db.execute(
                insert(user_mfa_factor).values(
                    id=factor_id,
                    user_id=auth.user.id,
                    factor_kind=TOTP_FACTOR,
                    created_by=auth.user.id,
                    created_by_kind=PrincipalKind.USER.value,
                    **values,
                )
            )
        else:
            db.execute(
                update(user_mfa_factor).where(user_mfa_factor.c.id == factor_id).values(**values)
            )
        _event(
            db,
            keyring,
            auth,
            SecurityEventKind.MFA_ENROLMENT_STARTED,
            AuditOutcome.SUCCESS,
            session_id=auth.session.id,
            detail={"factor_kind": TOTP_FACTOR, "reseeded": factor is not None},
        )
    return Enrolment(
        otpauth_uri=totp.provisioning_uri(secret, account=auth.user.email), secret_base32=secret
    )


def new_recovery_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(2 * RECOVERY_HALF))
    return f"{raw[:RECOVERY_HALF]}-{raw[RECOVERY_HALF:]}"


def normalise_recovery_code(code: str) -> str | None:
    """The canonical ``xxxx-xxxx`` form, ignoring case, spaces and hyphens; None when malformed."""
    raw = "".join(character for character in code.lower() if character not in " -")
    if len(raw) != 2 * RECOVERY_HALF or any(ch not in RECOVERY_ALPHABET for ch in raw):
        return None
    return f"{raw[:RECOVERY_HALF]}-{raw[RECOVERY_HALF:]}"


def _new_batch(db: Session, user_id: UUID, *, batch_id: UUID | None = None) -> list[str]:
    """Ten codes in a new batch; ``created_at`` is the transaction time, so the batch is newest."""
    batch_id = batch_id or new_id()
    codes = [new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    db.execute(
        insert(user_recovery_code),
        [
            {
                "id": new_id(),
                "user_id": user_id,
                "batch_id": batch_id,
                "code_hash": passwords.hash_password(code),
            }
            for code in codes
        ],
    )
    return codes


def _audit_enrolment(auth: AuthenticatedSession, factor_id: UUID, *, keyring: KeyRing) -> None:
    """T-PLT-04 AUD-OPS: one ``mfa_factor.enrol`` event in each ACTIVE membership's tenant."""
    facts = auth.facts
    auth_method = "oidc" if auth.session.auth_method is IdentityProviderKind.OIDC else "password"
    for tenant_id, membership_id in _active_memberships(auth.user.id, request_id=facts.request_id):
        context = DbContext(tenant_id=tenant_id, user_id=auth.user.id, entity_scope="*")
        with tenant_session(context) as db:
            grants = effective_grants(db, membership_id, at=facts.now)
            actor = AuditActor(
                kind=PrincipalKind.USER,
                id=auth.user.id,
                roles=grants.roles,
                auth_method=auth_method,
                mfa_verified=True,
                on_behalf_of_id=None,
                api_client_id=None,
                support_grant_id=None,
                source_ip=facts.source_ip,
                request_id=facts.request_id,
            )
            event = build_event(
                tenant_id=tenant_id,
                actor=actor,
                occurred_at=facts.now,
                action=ENROL_ACTION,
                object_type="user_mfa_factor",
                object_id=factor_id,
                after={"factor_kind": TOTP_FACTOR},
            )
            append_events(db, tenant_id=tenant_id, keyring=keyring, events=[event])


def audit_reset(
    *,
    user_id: UUID,
    factor_id: UUID,
    actor: AuditActor,
    occurred_at: datetime,
    comment: str | None,
    acting_tenant_id: UUID,
    keyring: KeyRing,
    request_id: str,
) -> None:
    """T-PLT-04 (D-80): one ``user_mfa_factor.reset`` event in the tenant of each ACTIVE membership
    of the user other than the acting tenant, whose unit of work audits the command itself. The
    actor holds no roles in those tenants, so ``actor_roles`` is empty there."""
    other_actor = replace(actor, roles=(), support_grant_id=None)
    for tenant_id, membership_id in _active_memberships(user_id, request_id=request_id):
        if tenant_id == acting_tenant_id:
            continue
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as db:
            event = build_event(
                tenant_id=tenant_id,
                actor=other_actor,
                occurred_at=occurred_at,
                action=RESET_ACTION,
                object_type=FACTOR_OBJECT,
                object_id=factor_id,
                before={"disabled_at": None},
                after={"disabled_at": occurred_at},
                comment=comment,
                detail={
                    "membership_id": str(membership_id),
                    "acting_tenant_id": str(acting_tenant_id),
                },
            )
            append_events(db, tenant_id=tenant_id, keyring=keyring, events=[event])


def _rotated(auth: AuthenticatedSession, row: SessionRow, token: str) -> AuthenticatedSession:
    return AuthenticatedSession(
        session=row, token=token, user=auth.user, active_tenant=auth.active_tenant, facts=auth.facts
    )


def confirm(
    auth: AuthenticatedSession, code: str, *, keyring: KeyRing
) -> tuple[AuthenticatedSession, list[str]]:
    """Confirm the pending factor with a first valid code (SAR-26).

    The factor is confirmed, ten recovery codes are issued, the session rotates as verified and
    ``MFA_ENROLLED`` is written; the tenant audit events follow in their own transactions. Without a
    pending factor, or with a confirmed one, 409 ``invalid-transition``.
    """
    facts = auth.facts
    refusal: Problem | None = None
    issued: tuple[UUID, SessionRow, str, list[str]] | None = None
    with identity_session(request_id=facts.request_id, user_id=auth.user.id) as db:
        factor = _active_factor(db, auth.user.id, lock=True)
        if factor is None:
            refusal = Problem("invalid-transition", START_ENROLMENT)
        elif factor["confirmed_at"] is not None:
            refusal = Problem("invalid-transition", ALREADY_ENROLLED)
        elif (
            step := totp.matching_step(
                _secret(keyring, factor),
                code,
                at=facts.now,
                last_used_step=factor["last_used_step"],
            )
        ) is None:
            _event(
                db,
                keyring,
                auth,
                SecurityEventKind.MFA_CHALLENGE_FAILED,
                AuditOutcome.FAILED,
                session_id=auth.session.id,
                detail={"method": "code", "purpose": "enrolment"},
            )
            refusal = _wrong_code("code", WRONG_ENROLMENT_CODE)
        else:
            db.execute(
                update(user_mfa_factor)
                .where(user_mfa_factor.c.id == factor["id"])
                .values(
                    confirmed_at=facts.now,
                    last_used_step=step,
                    updated_by=auth.user.id,
                    updated_by_kind=PrincipalKind.USER.value,
                )
            )
            codes = _new_batch(db, auth.user.id)
            row, token = sessions.reissue(
                db, auth, active_tenant_id=auth.session.active_tenant_id, mfa_verified_at=facts.now
            )
            _event(
                db,
                keyring,
                auth,
                SecurityEventKind.MFA_ENROLLED,
                AuditOutcome.SUCCESS,
                session_id=row.id,
                detail={"factor_kind": TOTP_FACTOR},
            )
            issued = (factor["id"], row, token, codes)
    if refusal is not None:
        raise refusal
    assert issued is not None
    factor_id, row, token, codes = issued
    _audit_enrolment(auth, factor_id, keyring=keyring)
    return _rotated(auth, row, token), codes


def _consume_recovery_code(db: Session, auth: AuthenticatedSession, code: str) -> int | None:
    """Mark a matching unused code of the newest batch used; the count left, or None."""
    normalised = normalise_recovery_code(code)
    if normalised is None:
        return None
    batch_id = db.execute(
        select(user_recovery_code.c.batch_id)
        .where(user_recovery_code.c.user_id == auth.user.id)
        .order_by(user_recovery_code.c.created_at.desc(), user_recovery_code.c.batch_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if batch_id is None:
        return None
    unused = db.execute(
        select(user_recovery_code.c.id, user_recovery_code.c.code_hash)
        .where(
            user_recovery_code.c.user_id == auth.user.id,
            user_recovery_code.c.batch_id == batch_id,
            user_recovery_code.c.used_at.is_(None),
        )
        .order_by(user_recovery_code.c.id)
    ).all()
    for code_id, code_hash in unused:
        if passwords.verify_password(str(code_hash), normalised):
            apply(
                db,
                "user_recovery_code",
                UUID(str(code_id)),
                to_status=None,
                set_values={"used_at": auth.facts.now},
            )
            return len(unused) - 1
    return None


def _challenge_failures(db: Session, user_id: UUID, verified_at: datetime) -> int:
    """``MFA_CHALLENGE_FAILED`` events of the user since the factor's last successful verification
    and since the user's latest ``ACCOUNT_LOCKED`` (D-80).

    Security events take ``occurred_at`` from the database clock, as the factor's ``updated_at``
    does, so the two compare in one time base. The lock is anchored by its event's chain position
    rather than by ``app_user.locked_until``, which holds the request clock and which a later
    password sign-in clears (SPEC-Q-206).
    """
    locked_seq = db.execute(
        select(func.max(security_event.c.chain_seq)).where(
            security_event.c.user_id == user_id,
            security_event.c.kind == SecurityEventKind.ACCOUNT_LOCKED.value,
        )
    ).scalar_one()
    statement = select(func.count()).where(
        security_event.c.user_id == user_id,
        security_event.c.kind == SecurityEventKind.MFA_CHALLENGE_FAILED.value,
        security_event.c.occurred_at > verified_at,
    )
    if locked_seq is not None:
        statement = statement.where(security_event.c.chain_seq > locked_seq)
    return int(db.execute(statement).scalar_one())


def _lock_account(
    db: Session, keyring: KeyRing, auth: AuthenticatedSession, *, method: str
) -> Problem:
    """Lock the account for 15 minutes after the fifth wrong code and write ``ACCOUNT_LOCKED``."""
    facts = auth.facts
    db.execute(
        update(app_user)
        .where(app_user.c.id == auth.user.id)
        .values(
            locked_until=facts.now + sessions.LOCKOUT,
            updated_by=auth.user.id,
            updated_by_kind=PrincipalKind.USER.value,
        )
    )
    _event(
        db,
        keyring,
        auth,
        SecurityEventKind.ACCOUNT_LOCKED,
        AuditOutcome.SUCCESS,
        session_id=auth.session.id,
        detail={
            "lockout_minutes": int(sessions.LOCKOUT.total_seconds()) // 60,
            "method": method,
        },
    )
    return Problem("account-locked", sessions.ACCOUNT_LOCKED)


def verify(
    auth: AuthenticatedSession,
    *,
    code: str | None,
    recovery_code: str | None,
    keyring: KeyRing,
) -> Verified:
    """The sign-in challenge and step-up (BS1-D-19, BS1-D-30): exactly one of ``code`` and
    ``recovery_code``.

    A valid code rotates the session with ``mfa_verified_at`` = now and writes
    ``MFA_CHALLENGE_PASSED`` (``detail.method``; ``detail.step_up`` for a session that was
    verified already); a recovery code is spent and writes ``RECOVERY_CODE_USED`` as well. A
    wrong, replayed or spent code writes ``MFA_CHALLENGE_FAILED``
    and gives 422 ``validation-failed`` on the field sent; the fifth such failure since the factor's
    last successful verification and the latest lock sets ``locked_until`` 15 minutes ahead, writes
    ``ACCOUNT_LOCKED`` and gives 423 ``account-locked``. While the account is locked, 423 without
    verifying (D-80). Without a confirmed factor, 409.
    """
    facts = auth.facts
    field = "code" if code is not None else "recovery_code"
    refusal: Problem | None = None
    issued: tuple[SessionRow, str, int | None] | None = None
    with identity_session(request_id=facts.request_id, user_id=auth.user.id) as db:
        factor = _active_factor(db, auth.user.id, lock=True)
        # The identity's row, before an event is written (dev-guide DG-KRN-AUTH-08): the
        # factor, then the identity, then the security chain - a password step takes the
        # identity before the chain as well, so the two steps of one member never wait in
        # a ring.
        locked_until = db.execute(
            select(app_user.c.locked_until)
            .where(app_user.c.id == auth.user.id)
            .with_for_update(key_share=True)
        ).scalar_one()
        remaining: int | None = None
        if locked_until is not None and locked_until > facts.now:
            refusal = Problem("account-locked", sessions.ACCOUNT_LOCKED)
        elif factor is None or factor["confirmed_at"] is None:
            refusal = Problem("invalid-transition", NOT_ENROLLED)
        elif code is not None:
            step = totp.matching_step(
                _secret(keyring, factor),
                code,
                at=facts.now,
                last_used_step=factor["last_used_step"],
            )
            if step is not None:
                db.execute(
                    update(user_mfa_factor)
                    .where(user_mfa_factor.c.id == factor["id"])
                    .values(
                        last_used_step=step,
                        updated_by=auth.user.id,
                        updated_by_kind=PrincipalKind.USER.value,
                    )
                )
            else:
                refusal = _wrong_code(field, WRONG_CODE)
        else:
            remaining = _consume_recovery_code(db, auth, recovery_code or "")
            if remaining is None:
                refusal = _wrong_code(field, WRONG_CODE)
        if refusal is not None and refusal.slug == "validation-failed":
            assert factor is not None
            _event(
                db,
                keyring,
                auth,
                SecurityEventKind.MFA_CHALLENGE_FAILED,
                AuditOutcome.FAILED,
                session_id=auth.session.id,
                detail={"method": field},
            )
            if (
                _challenge_failures(db, auth.user.id, factor["updated_at"])
                >= MAX_CHALLENGE_FAILURES
            ):
                refusal = _lock_account(db, keyring, auth, method=field)
        elif refusal is None:
            assert factor is not None
            if remaining is not None:
                # A spent recovery code is a successful verification too: the factor's updated_at
                # restarts the failure count (D-80).
                db.execute(
                    update(user_mfa_factor)
                    .where(user_mfa_factor.c.id == factor["id"])
                    .values(updated_by=auth.user.id, updated_by_kind=PrincipalKind.USER.value)
                )
            row, token = sessions.reissue(
                db, auth, active_tenant_id=auth.session.active_tenant_id, mfa_verified_at=facts.now
            )
            # 05 SAR-26 rev 1.128 (ruling R-111 (6)): LOGIN_SUCCEEDED stands at the password
            # step; this is the event that says the second step was passed, at sign-in or as a
            # step-up of a session that was verified already.
            _event(
                db,
                keyring,
                auth,
                SecurityEventKind.MFA_CHALLENGE_PASSED,
                AuditOutcome.SUCCESS,
                session_id=row.id,
                detail={"method": field, "step_up": auth.session.mfa_verified_at is not None},
            )
            if remaining is not None:
                _event(
                    db,
                    keyring,
                    auth,
                    SecurityEventKind.RECOVERY_CODE_USED,
                    AuditOutcome.SUCCESS,
                    session_id=row.id,
                    detail={"remaining": remaining},
                )
            issued = (row, token, remaining)
    if refusal is not None:
        raise refusal
    assert issued is not None
    row, token, remaining = issued
    return Verified(auth=_rotated(auth, row, token), recovery_codes_remaining=remaining)


def regenerate_recovery_codes(auth: AuthenticatedSession, *, keyring: KeyRing) -> list[str]:
    """A new batch of ten codes, which invalidates every earlier batch (T-PLT-05). Replacing the
    batch is a security-relevant write: ``RECOVERY_CODES_REGENERATED`` names the batch and the
    number of codes issued, never a code (04 E-79; ruling R-50 (b))."""
    with identity_session(request_id=auth.facts.request_id, user_id=auth.user.id) as db:
        factor = _active_factor(db, auth.user.id, lock=True)
        if factor is None or factor["confirmed_at"] is None:
            raise Problem("invalid-transition", NOT_ENROLLED)
        batch_id = new_id()
        codes = _new_batch(db, auth.user.id, batch_id=batch_id)
        _event(
            db,
            keyring,
            auth,
            SecurityEventKind.RECOVERY_CODES_REGENERATED,
            AuditOutcome.SUCCESS,
            session_id=auth.session.id,
            detail={"batch_id": str(batch_id), "codes": len(codes)},
        )
        return codes
