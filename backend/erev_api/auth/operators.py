"""Platform operators (04 T-PLT-02 ``is_operator``, T-PLT-08 ``operator_support_grant_id``,
T-PLT-33; 05 SAR-29, TB-7, THR-20; 03 REQ-PLT-036; BUILD_SPEC PLF-26, BS1-D-27).

``create_operator`` adds the ``app_user`` of ``erev operator create``. An operator never acts in a
tenant through a membership: ``select_support_tenant`` opens a workspace only under an APPROVED
support grant in force, after an MFA verification, in a new session that carries
``operator_support_grant_id``. ``operator_context`` gives such a session the read-only grants of
``READ_ONLY_PERMISSIONS`` and the grant id that every audit event of the request carries, and
``record_access`` writes one audit event per tenant request (SAR-29).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import insert, select

from erev_api.audit.writer import record_now
from erev_api.auth import mfa, passwords, sessions
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext
from erev_api.auth.security_events import record_security_event
from erev_api.auth.sessions import AuthenticatedSession
from erev_api.db import new_id
from erev_api.db.session import identity_session
from erev_api.db.tables import app_user
from erev_api.enums import (
    AuditOutcome,
    IdentityProviderKind,
    PrincipalKind,
    SecurityEventKind,
)
from erev_api.problems import Problem, ProblemError

# [J] SPEC-Q-191: T-PLT-33 scope READ_ONLY holds the catalogue's view permissions only.
READ_ONLY_PERMISSIONS: Final = frozenset({"audit.read", "config.read", "contract.read", "ssp.read"})
OBJECT_TYPE: Final = "support_grant"
SESSION_OPEN_ACTION: Final = "support_grant.open_session"
ACCESS_ACTION: Final = "support_grant.access"
COMMAND_DENIED_ACTION: Final = "support_grant.command"
CREATE_COMMAND: Final = "operator.create"
RULE_USER: Final = "T-PLT-02"
EMAIL: Final = re.compile(r"^[^@\s]+@[^@\s]+$")  # TY-09 after lower-casing
EMAIL_LENGTH: Final = 320
LABEL_LENGTH: Final = range(1, 401)  # erev.label (TY-07)

# [J] SPEC-Q-191: copy the documents leave open.
READ_ONLY_DETAIL: Final = "Support access is read-only."
EMAIL_INVALID: Final = "Enter an email address."
EMAIL_TAKEN: Final = "An account with this email address already exists."
NAME_LENGTH: Final = "Use 1 to 400 characters."
_OPERATOR_PERMISSION_SCOPES: Final[Mapping[str, Literal["*"] | frozenset[UUID]]] = MappingProxyType(
    dict.fromkeys(sorted(READ_ONLY_PERMISSIONS), "*")
)


def create_operator(
    *, email: str, display_name: str, password: str, request_id: str, keyring: KeyRing
) -> dict[str, Any]:
    """A new ACTIVE ``app_user`` with ``is_operator`` and an argon2id password hash (BS1-D-27).

    422 ``validation-failed`` for a malformed email, a display name outside 1 to 400 characters or
    an email already in use; 422 ``password-policy`` for a weak password. The command writes
    ``security_event`` ``PLATFORM_SCOPE_USED`` with ``detail.command`` ``operator.create``, because
    an operator has no tenant log to hold the event.
    """
    normalised = sessions.normalise_email(email)
    name = display_name.strip()
    errors: list[ProblemError] = []
    if len(normalised) > EMAIL_LENGTH or not EMAIL.fullmatch(normalised):
        errors.append(ProblemError(field="email", rule_id=RULE_USER, message=EMAIL_INVALID))
    if len(name) not in LABEL_LENGTH:
        errors.append(ProblemError(field="display_name", rule_id=RULE_USER, message=NAME_LENGTH))
    if errors:
        raise Problem("validation-failed", errors=errors)
    passwords.check_policy(password, email=normalised)
    user_id = new_id()
    with identity_session(request_id=request_id) as db:
        taken = db.execute(select(app_user.c.id).where(app_user.c.email == normalised)).first()
        if taken is not None:
            raise Problem(
                "validation-failed",
                errors=[ProblemError(field="email", rule_id=RULE_USER, message=EMAIL_TAKEN)],
            )
        db.execute(
            insert(app_user).values(
                id=user_id,
                email=normalised,
                display_name=name,
                password_hash=passwords.hash_password(password),
                is_operator=True,
                created_by_kind=PrincipalKind.OPERATOR.value,
                updated_by_kind=PrincipalKind.OPERATOR.value,
            )
        )
        record_security_event(
            db,
            keyring=keyring,
            kind=SecurityEventKind.PLATFORM_SCOPE_USED,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
            user_id=user_id,
            detail={"command": CREATE_COMMAND},
        )
    return {"id": user_id, "email": normalised, "display_name": name, "is_operator": True}


def _operator_principal(auth: AuthenticatedSession) -> Principal:
    active = auth.active_tenant
    grant_id = auth.session.operator_support_grant_id
    if active is None or grant_id is None or not auth.user.is_operator:
        raise Problem("unauthenticated", sessions.SIGN_IN_REQUIRED)
    return Principal(
        kind=PrincipalKind.OPERATOR,
        id=auth.user.id,
        tenant_id=active.id,
        membership_id=None,
        display_name=auth.user.display_name,
        roles=(),
        permissions=READ_ONLY_PERMISSIONS,
        permission_scopes=_OPERATOR_PERMISSION_SCOPES,
        entity_scope="*",
        auth_method="oidc" if auth.session.auth_method is IdentityProviderKind.OIDC else "password",
        mfa_verified_at=auth.session.mfa_verified_at,
        session_id=auth.session.id,
        support_grant_id=grant_id,
        on_behalf_of_id=None,
    )


def operator_context(
    auth: AuthenticatedSession, *, idempotency_key: str | None, if_match: str | None
) -> RequestContext:
    """The request context of an operator session in the workspace of its support grant."""
    principal = _operator_principal(auth)
    active = auth.active_tenant
    assert active is not None
    locale = auth.user.preferences.get("format_locale")
    return RequestContext(
        principal=principal,
        tenant_kind=active.kind,
        request_id=auth.facts.request_id,
        source_ip=auth.facts.source_ip,
        user_agent=auth.facts.user_agent,
        idempotency_key=idempotency_key,
        if_match=if_match,
        now=auth.facts.now,
        format_locale=locale if isinstance(locale, str) else active.default_locale,
        tenant_status=active.status,
    )


def record_access(ctx: RequestContext, *, method: str, path: str, keyring: KeyRing) -> None:
    """One ``support_grant.access`` event in the tenant log per operator request (SAR-29)."""
    record_now(
        ctx,
        action=ACCESS_ACTION,
        object_type=OBJECT_TYPE,
        object_id=ctx.principal.support_grant_id,
        detail={"method": method, "path": path},
        keyring=keyring,
    )


def select_support_tenant(
    auth: AuthenticatedSession, tenant_id: UUID, *, keyring: KeyRing
) -> AuthenticatedSession:
    """``POST /session/tenant`` for an operator (CTL-035; TB-7).

    Without an APPROVED grant in force for the operator and tenant the tenant is 404
    ``not-found``; an operator session without MFA verification gets 403 ``mfa-required``. The new
    session carries the grant id and keeps the MFA verification and absolute expiry. It writes
    ``TENANT_SELECTED`` naming the grant and ``support_grant.open_session`` in the tenant log.
    """
    facts = auth.facts
    grant_id = sessions.support_grant_in_force(facts, user_id=auth.user.id, tenant_id=tenant_id)
    if grant_id is None:
        raise Problem("not-found")
    if auth.session.mfa_verified_at is None:
        enrolled = mfa.has_confirmed_factor(auth.user.id, request_id=facts.request_id)
        raise Problem(
            "mfa-required", mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED
        )
    active = sessions.support_tenant(
        facts, user_id=auth.user.id, tenant_id=tenant_id, grant_id=grant_id
    )
    if active is None:
        raise Problem("not-found")
    with identity_session(request_id=facts.request_id, user_id=auth.user.id) as db:
        row, token = sessions.reissue(
            db,
            auth,
            active_tenant_id=tenant_id,
            mfa_verified_at=auth.session.mfa_verified_at,
            operator_support_grant_id=grant_id,
        )
        record_security_event(
            db,
            keyring=keyring,
            kind=SecurityEventKind.TENANT_SELECTED,
            outcome=AuditOutcome.SUCCESS,
            request_id=facts.request_id,
            user_id=auth.user.id,
            session_id=row.id,
            tenant_id=tenant_id,
            ip_address=facts.source_ip,
            user_agent=facts.user_agent,
            detail={"support_grant_id": str(grant_id)},
        )
    selected = AuthenticatedSession(
        session=row, token=token, user=auth.user, active_tenant=active, facts=facts
    )
    ctx = operator_context(selected, idempotency_key=None, if_match=None)
    record_now(
        ctx,
        action=SESSION_OPEN_ACTION,
        object_type=OBJECT_TYPE,
        object_id=grant_id,
        detail={"session_id": str(row.id)},
        keyring=keyring,
    )
    return selected
