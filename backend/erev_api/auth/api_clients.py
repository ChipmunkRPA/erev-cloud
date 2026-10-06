"""API clients and access tokens (04 T-PLT-15, T-PLT-16, API-R-02, API-R-08; 05 SAR-28, THR-04;
03 REQ-PLT-033; CTL-037; BUILD_SPEC PLF-25).

An API client is an OAuth2 client-credentials principal of one workspace. Its ``client_id`` embeds
the tenant (``erevc_<tenant hex>_<22 base64url characters>``). Its secret, 32 random bytes in
base64url, is returned once when it is issued; the row keeps the argon2id hash only. Scopes are
catalogue permission codes other than approval permissions: the command answers 422
``scope-not-allowed`` and trigger DB-12 refuses the row (CTL-037). Creating and rotating need a
step-up verification (PRD BR-PLT-06); revoking needs a reason of at least 10 characters (SCREENS_B
SB-R-05). Rotation and revocation revoke the client's open tokens. The three commands are AUD-CMD.

A client's scopes are an access grant (REQ-PLT-033 rev 1.83; 04 T-PLT-15 rev 1.168; supervisor
ruling R-38 (iii)): a Tenant Admin holds no finance permission by design, and a client with
``event.record`` or ``import.upload`` is that permission under another name. ``create_api_client``
therefore writes the row ``PENDING_APPROVAL`` and submits the grant for approval under the routing
of ``ROLE_ASSIGNMENT`` (``subjects.api_client_grant_proposal``): another person who holds
``access.approve`` for the client's entities decides it, and rule ``AUTO-BOOTSTRAP`` approves it at
once for the bootstrap Tenant Admin during setup. The approval makes the client ``ACTIVE``; a
rejection, withdrawal or void leaves it ``REJECTED``. The secret is issued after the approval, by
``rotate_secret`` to a holder of ``api_client.manage`` — the approver never sees one — and only a
request approved at once returns it from the creation. ``secret_rotated_at`` is the instant the
current secret was issued; while it is NULL nobody holds a secret that verifies, so the client
cannot authenticate whatever its status. No command changes the scopes of a client: another scope
set is another client and another request.

``issue_token`` serves ``POST /oauth/token``: HTTP Basic client authentication, then a 60-minute
access token ``erevt_<tenant hex>_<43 base64url characters>``, of which the ``api_token`` row keeps
the SHA-256 (AUD-OPS). ``token_principal`` resolves a bearer token: the tenant is parsed from the
token, the hash is looked up in that tenant, and the grants come from
``permissions.api_client_grants`` (DG-KRN-AUTH-01 step 1).
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, Uuid, and_, insert, literal, select, true, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope, mfa, passwords
from erev_api.auth.permissions import CATALOGUE, PermissionSpec, api_client_grants
from erev_api.auth.principal import Principal
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client, api_token, approval_request, tenant
from erev_api.enums import (
    ApiClientStatus,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    PrincipalKind,
    TenantKind,
    TenantStatus,
)
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "api_client"
CREATE_ACTION: Final = "api_client.create"
ROTATE_ACTION: Final = "api_client.rotate_secret"
REVOKE_ACTION: Final = "api_client.revoke"
RULE_CLIENT: Final = "T-PLT-15"
# 04 T-PLT-10 "Commands on what is granted": the rule the denial of a command on a grant, or of
# a request beyond its creator's access, is recorded under.
RULE_GRANT_SCOPE: Final = entity_scope.RULE_SHAPE
RULE_SCOPES: Final = "DB-12"
MANAGE_PERMISSION: Final = "api_client.manage"  # the permission that grants a client its scope
RULE_REASON: Final = "BR-PLT-08"
RULE_TOKEN: Final = "API-R-02"
CLIENT_LIFETIME: Final = timedelta(days=365)  # T-PLT-15 expires_at
TOKEN_LIFETIME: Final = timedelta(minutes=60)  # T-PLT-16; SAR-28
TOKEN_RETENTION: Final = timedelta(days=7)  # T-PLT-16 IM-E
DEFAULT_RATE_LIMIT: Final = 600  # T-PLT-15; REQ-PLT-037
LABEL_LENGTH: Final = range(1, 401)  # TY-07
MIN_REASON_LENGTH: Final = 10  # SCREENS_B SB-R-05
GRANT_TYPE: Final = "client_credentials"
TOKEN_TYPE: Final = "Bearer"
CLIENT_ID_PATTERN: Final = re.compile(r"erevc_([0-9a-f]{32})_[A-Za-z0-9_-]{22}")
TOKEN_PATTERN: Final = re.compile(r"erevt_([0-9a-f]{32})_[A-Za-z0-9_-]{43}")
BASIC_CHALLENGE: Final = 'Basic realm="erev"'
BEARER_CHALLENGE: Final = 'Bearer realm="erev", error="invalid_token"'

# PRD ERR-24.
SCOPE_NOT_ALLOWED: Final = "API clients cannot hold approval permissions."
# [J] SPEC-Q-190: copy the documents leave open; SB-R-05 gives the reason error.
NAME_LENGTH: Final = "Use 1 to 400 characters."
SCOPES_EMPTY: Final = "Choose at least one scope."
SCOPE_UNKNOWN: Final = "Choose permissions from the permission catalogue."
EXPIRY_PAST: Final = "Choose an expiry in the future."
RATE_LIMIT_INVALID: Final = "Enter a whole number of at least 1."
REASON_SHORT: Final = "Enter at least 10 characters."
NOT_ACTIVE: Final = "This API client is revoked."
WAITING_FOR_APPROVAL: Final = "This API client is waiting for approval."
REQUEST_REJECTED: Final = "The request for this API client was not approved."
GRANT_SUMMARY: Final = "Grant API client {name} its scopes for {scope}"
CLIENT_REFUSED: Final = "Authenticate with the client id and secret of an active API client."
TOKEN_REFUSED: Final = "The access token is invalid, expired or revoked. Request a new token."
GRANT_TYPE_INVALID: Final = "Use grant_type client_credentials."
SCOPE_NOT_HELD: Final = "Request only scopes that this API client holds."

_BY_CODE: Final[Mapping[str, PermissionSpec]] = MappingProxyType(
    {permission.code: permission for permission in CATALOGUE}
)
# The request that grants the client its scopes (ruling R-38 (iii)): the latest ``ROLE_ASSIGNMENT``
# request whose subject is the client, as far as the reader may read it (T-PLT-17 is RLS-TE).
GRANT_REQUEST_ID: Final = (
    select(approval_request.c.id)
    .where(
        approval_request.c.tenant_id == api_client.c.tenant_id,
        approval_request.c.subject_type == ApprovalSubjectType.ROLE_ASSIGNMENT.value,
        approval_request.c.subject_id == api_client.c.id,
    )
    .order_by(approval_request.c.submitted_at.desc(), approval_request.c.id.desc())
    .limit(1)
    .correlate(api_client)
    .scalar_subquery()
    .label("approval_request_id")
)
# Whether a secret of the client was ever issued (04 T-PLT-15 rev 1.168): the client was granted
# and ``secret_rotated_at`` is set. Without one the client cannot authenticate.
HAS_SECRET: Final = and_(
    api_client.c.status.in_([ApiClientStatus.ACTIVE.value, ApiClientStatus.REVOKED.value]),
    api_client.c.secret_rotated_at.is_not(None),
).label("has_secret")
_NOT_ACTIVE: Final[Mapping[str, str]] = MappingProxyType(
    {
        ApiClientStatus.PENDING_APPROVAL.value: WAITING_FOR_APPROVAL,
        ApiClientStatus.REJECTED.value: REQUEST_REJECTED,
        ApiClientStatus.REVOKED.value: NOT_ACTIVE,
    }
)
CLIENT_COLUMNS: Final = (
    api_client.c.id,
    api_client.c.name,
    api_client.c.client_id,
    api_client.c.secret_rotated_at,
    api_client.c.scopes,
    api_client.c.is_all_entities,
    api_client.c.entity_ids,
    api_client.c.status,
    api_client.c.expires_at,
    api_client.c.rate_limit_per_minute,
    api_client.c.last_used_at,
    api_client.c.created_at,
    api_client.c.updated_at,
    api_client.c.row_version,
    GRANT_REQUEST_ID,
    HAS_SECRET,
)


@dataclass(frozen=True, slots=True)
class IssuedSecret:
    client: Mapping[str, Any]
    client_secret: str | None  # shown once; None while the client's grant waits for a person


@dataclass(frozen=True, slots=True)
class IssuedToken:
    access_token: str
    expires_in: int  # seconds
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TokenPrincipal:
    principal: Principal
    tenant_kind: TenantKind
    default_locale: str
    rate_limit_per_minute: int | None = None  # api_client.rate_limit_per_minute (SAR-13; SOP-4)
    tenant_status: TenantStatus = TenantStatus.ACTIVE  # E-101 (05 SBX-07)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_client_id(tenant_id: UUID) -> str:
    return f"erevc_{tenant_id.hex}_{_b64url(secrets.token_bytes(16))}"


def new_client_secret() -> str:
    return _b64url(secrets.token_bytes(32))


def new_access_token(tenant_id: UUID) -> str:
    return f"erevt_{tenant_id.hex}_{_b64url(secrets.token_bytes(32))}"


def _tenant_of(value: str, pattern: re.Pattern[str]) -> UUID | None:
    match = pattern.fullmatch(value)
    return None if match is None else UUID(hex=match.group(1))


def client_refusal() -> Problem:
    """401 ``unauthenticated`` with the HTTP Basic challenge (RFC 6749 §5.2 ``invalid_client``)."""
    return Problem("unauthenticated", CLIENT_REFUSED, headers={"WWW-Authenticate": BASIC_CHALLENGE})


def bearer_refusal() -> Problem:
    """401 ``unauthenticated`` with the bearer challenge (RFC 6750 §3.1 ``invalid_token``)."""
    return Problem("unauthenticated", TOKEN_REFUSED, headers={"WWW-Authenticate": BEARER_CHALLENGE})


def _read(session: Session, api_client_id: UUID, *, lock: bool = False) -> Mapping[str, Any]:
    statement = select(*CLIENT_COLUMNS).where(api_client.c.id == api_client_id)
    if lock:
        statement = statement.with_for_update(of=api_client)
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def _audited(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "client_id": row["client_id"],
        "scopes": list(row["scopes"]),
        "is_all_entities": row["is_all_entities"],
        "entity_ids": [str(value) for value in row["entity_ids"]],
        "status": str(row["status"]),
        "expires_at": row["expires_at"].isoformat(),
        "rate_limit_per_minute": row["rate_limit_per_minute"],
    }


def _stamps(uow: UnitOfWork, *, created: bool) -> dict[str, Any]:
    principal = uow.principal
    values: dict[str, Any] = {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    if created:
        values |= {
            "created_at": uow.now,
            "created_by": principal.id,
            "created_by_kind": principal.kind.value,
        }
    return values


def _require_step_up(uow: UnitOfWork) -> None:
    """PRD BR-PLT-06: creating API clients needs a TOTP verification at most five minutes old."""
    if not mfa.step_up_fresh_at(uow.principal.mfa_verified_at, uow.now):
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)


def reaches(principal: Principal, row: Mapping[str, Any]) -> bool:
    """Whether ``principal`` reaches the client: its ``api_client.manage`` covers every entity
    the client names, and all entities when the client is for all (the kernel's
    ``entity_scope.covers``; 04 T-PLT-10 and T-PLT-15 rev 1.278; 03 REQ-PLT-012).
    ``api_client`` is RLS-T — no row policy knows a client's entities — so the reads and the
    commands here decide, as ``integrations.queries.reaches`` does for a connection."""
    held = entity_scope.held_scope(principal, MANAGE_PERMISSION)
    scope = (bool(row["is_all_entities"]), tuple(row["entity_ids"] or ()))
    return entity_scope.covers(held, [scope])


def in_reach(principal: Principal) -> ColumnElement[bool]:
    """``reaches`` in SQL, over ``api_client``."""
    held = entity_scope.held_scope(principal, MANAGE_PERMISSION)
    if held == "*":
        return true()
    return and_(
        api_client.c.is_all_entities.is_(False),
        api_client.c.entity_ids.contained_by(literal(sorted(held), ARRAY(Uuid()))),
    )


def _scope_denial(*, all_entities: bool) -> dict[str, str]:
    """The detail of the ``DENIED`` event of a scope denial (DG-KRN-AUTH-05): the rule and,
    where all entities were asked for or are covered, the scope. Like the answer it names no
    entity."""
    return {"rule_id": RULE_GRANT_SCOPE, **({"scope": "*"} if all_entities else {})}


def _require_reach(uow: UnitOfWork, row: Mapping[str, Any], *, action: str) -> None:
    """A command on a client the actor does not reach answers 404 ``not-found``, exactly as
    the read does and as an id that names no client (04 API-C-03; no command confirms an id
    the read denies) — after the ``DENIED`` event of the command is written under the client,
    in a transaction of its own (DG-KRN-AUTH-05). It is the one 404 that records (04 T-PLT-15
    rev 1.278): the client exists, and what was reached for is a credential for entities
    beyond the actor's own. The event is read by a holder of ``audit.read`` for all entities
    only, so it tells the caller nothing; it names no entity."""
    if reaches(uow.principal, row):
        return
    audit_writer.record_denied(
        uow.ctx,
        action=action,
        object_type=OBJECT_TYPE,
        object_id=UUID(str(row["id"])),
        permission=MANAGE_PERMISSION,
        detail=_scope_denial(all_entities=bool(row["is_all_entities"])),
        keyring=uow.keyring,
    )
    raise Problem("not-found")


def _require_active(row: Mapping[str, Any]) -> None:
    status = str(row["status"])
    if status != ApiClientStatus.ACTIVE.value:
        raise Problem("invalid-transition", _NOT_ACTIVE.get(status, NOT_ACTIVE))


def _revoke_tokens(session: Session, api_client_id: UUID, *, now: datetime) -> int:
    """Set ``revoked_at`` on every open token of the client; returns their number."""
    revoked = session.execute(
        update(api_token)
        .where(
            api_token.c.api_client_id == api_client_id,
            api_token.c.revoked_at.is_(None),
            api_token.c.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(api_token.c.id)
    )
    return len(revoked.all())


def _validated(
    uow: UnitOfWork,
    *,
    name: str,
    scopes: Sequence[str],
    is_all_entities: bool,
    entity_codes: Sequence[str],
    expires_at: datetime | None,
    rate_limit_per_minute: int | None,
) -> tuple[str, list[str], datetime, int, entity_scope.EntityScope]:
    """The trimmed name, sorted scopes, expiry, rate limit and entity scope, or the problem.

    An approval scope gives 422 ``scope-not-allowed`` before anything else (CTL-037); every other
    finding is collected into one 422 ``validation-failed``. The entity scope is resolved by
    ``auth.entity_scope.resolve`` (item API-CLIENT-ENTITY-SCOPE-1; supervisor ruling R-63 (e)):
    one shape, codes that name legal entities, and nothing beyond the creator's own scope for
    ``api_client.manage`` — an entity outside it answers as a code that does not exist.
    """
    approval = [
        index
        for index, code in enumerate(scopes)
        if code in _BY_CODE and _BY_CODE[code].is_approval
    ]
    if approval:
        raise Problem(
            "scope-not-allowed",
            SCOPE_NOT_ALLOWED,
            errors=[
                ProblemError(
                    field=f"scopes[{index}]", rule_id=RULE_SCOPES, message=SCOPE_NOT_ALLOWED
                )
                for index in approval
            ],
        )
    errors: list[ProblemError] = []
    text = name.strip()
    if len(text) not in LABEL_LENGTH:
        errors.append(ProblemError(field="name", rule_id=RULE_CLIENT, message=NAME_LENGTH))
    if not scopes:
        errors.append(ProblemError(field="scopes", rule_id=RULE_CLIENT, message=SCOPES_EMPTY))
    errors.extend(
        ProblemError(field=f"scopes[{index}]", rule_id=RULE_SCOPES, message=SCOPE_UNKNOWN)
        for index, code in enumerate(scopes)
        if code not in _BY_CODE
    )
    held = entity_scope.held_scope(uow.principal, MANAGE_PERMISSION)
    scope, findings = entity_scope.resolve(
        uow.session,
        held=held,
        is_all_entities=is_all_entities,
        entity_codes=entity_codes,
        field="entity_codes",
        shape_field="is_all_entities",
    )
    if entity_scope.reaches_beyond(
        held, is_all_entities=is_all_entities, entity_codes=entity_codes, scope=scope
    ):
        # The request asked for more than its creator's own access: recorded as a denial of the
        # creation, whatever else is wrong with it, as for an invitation and an assignment
        # (04 T-PLT-10 rev 1.187). The answer stays the 422.
        audit_writer.record_denied(
            uow.ctx,
            action=CREATE_ACTION,
            object_type=OBJECT_TYPE,
            object_id=None,
            permission=MANAGE_PERMISSION,
            detail=_scope_denial(all_entities=is_all_entities),
            keyring=uow.keyring,
        )
    # The shape and the creator's own scope are rules of this table (T-PLT-15), as they are rules
    # of T-PLT-10 for a role assignment; an unknown entity keeps DB-12's id.
    errors.extend(
        replace(finding, rule_id=RULE_CLIENT)
        if finding.rule_id == entity_scope.RULE_SHAPE
        else finding
        for finding in findings
    )
    expiry = uow.now + CLIENT_LIFETIME if expires_at is None else expires_at
    if expiry <= uow.now:
        errors.append(ProblemError(field="expires_at", rule_id=RULE_CLIENT, message=EXPIRY_PAST))
    limit = DEFAULT_RATE_LIMIT if rate_limit_per_minute is None else rate_limit_per_minute
    if limit < 1:
        errors.append(
            ProblemError(
                field="rate_limit_per_minute", rule_id=RULE_CLIENT, message=RATE_LIMIT_INVALID
            )
        )
    if errors or scope is None:
        raise Problem("validation-failed", errors=errors)
    return text, sorted(set(scopes)), expiry, limit, scope


def create_api_client(
    uow: UnitOfWork,
    *,
    name: str,
    scopes: Sequence[str],
    is_all_entities: bool = True,
    entity_codes: Sequence[str] = (),
    expires_at: datetime | None = None,
    rate_limit_per_minute: int | None = None,
    auto_approval: bool,
) -> IssuedSecret:
    """Request an API client: its scopes take effect only after approval (REQ-PLT-033 rev 1.83;
    supervisor ruling R-38 (iii)).

    ``auto_approval`` is the caller's reading of the setup state, taken before this request is
    routed (04 T-PLT-01 rev 1.224; ``domain.platform.setup.completion_due``): False keeps the
    grant from rule ``AUTO-BOOTSTRAP`` in a workspace whose setup is complete in all but the
    stamp. It has no default — every submitter of a ``ROLE_ASSIGNMENT`` states it
    (``tests/architecture/test_setup_rule_submitters.py``).

    Needs a fresh step-up (403 ``mfa-step-up-required``). ``expires_at`` defaults to 365 days and
    ``rate_limit_per_minute`` to 600. The entity scope is all entities or named entities within
    the creator's own (``_validated``), and the grant request is bound to it. The
    row is written ``PENDING_APPROVAL`` with the hash of a secret nobody is told, and the grant is
    submitted under the routing of ``ROLE_ASSIGNMENT``. When the request comes back approved —
    rule ``AUTO-BOOTSTRAP``, the bootstrap Tenant Admin during setup — the client is ``ACTIVE``
    and that secret is returned, once. Otherwise ``client_secret`` is None, the secret is dropped,
    and ``rotate_secret`` issues the first one after another person has approved.
    """
    _require_step_up(uow)
    text, clean_scopes, expiry, limit, scope = _validated(
        uow,
        name=name,
        scopes=scopes,
        is_all_entities=is_all_entities,
        entity_codes=entity_codes,
        expires_at=expires_at,
        rate_limit_per_minute=rate_limit_per_minute,
    )
    principal = uow.principal
    client_row_id = new_id()
    client_id = new_client_id(principal.tenant_id)
    client_secret = new_client_secret()
    uow.session.execute(
        insert(api_client).values(
            tenant_id=principal.tenant_id,
            id=client_row_id,
            name=text,
            client_id=client_id,
            secret_hash=passwords.hash_password(client_secret),
            scopes=clean_scopes,
            is_all_entities=scope.is_all_entities,
            entity_ids=list(scope.entity_ids),
            status=ApiClientStatus.PENDING_APPROVAL.value,
            expires_at=expiry,
            rate_limit_per_minute=limit,
            **_stamps(uow, created=True),
        )
    )
    row = _read(uow.session, client_row_id)
    uow.audit(
        action=CREATE_ACTION, object_type=OBJECT_TYPE, object_id=client_row_id, after=_audited(row)
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT,
        subject_id=client_row_id,
        summary=GRANT_SUMMARY.format(name=text, scope=scope.label),
        impact_preview=approvals.ImpactPreview(
            before={"api_client": None},
            after=subjects.api_client_grant_proposal(
                api_client_id=client_row_id,
                name=text,
                client_id=client_id,
                scopes=clean_scopes,
                is_all_entities=scope.is_all_entities,
                entity_ids=scope.entity_ids,
                entity_codes=scope.entity_codes,
                expires_at=expiry,
                rate_limit_per_minute=limit,
            ),
        ),
        auto_approval=auto_approval,
    )
    if str(request["status"]) != ApprovalRequestStatus.APPROVED.value:
        # A person decides: nobody is told the secret whose hash the row keeps.
        return IssuedSecret(client=_read(uow.session, client_row_id), client_secret=None)
    # Approved at submission (rule AUTO-BOOTSTRAP): the hook made the client ACTIVE, and the
    # secret hashed above is its first one.
    uow.session.execute(
        update(api_client)
        .where(api_client.c.id == client_row_id)
        .values(secret_rotated_at=uow.now, **_stamps(uow, created=False))
    )
    return IssuedSecret(client=_read(uow.session, client_row_id), client_secret=client_secret)


def rotate_secret(uow: UnitOfWork, api_client_id: UUID) -> IssuedSecret:
    """Replace the secret of an ACTIVE client, returned once, and revoke its open tokens.

    Needs a fresh step-up, and ``api_client.manage`` for every entity of the client — the
    secret is a credential for those entities; a client the actor does not reach answers 404
    (``_require_reach``). A client that is not ``ACTIVE`` gives 409 ``invalid-transition``.
    """
    _require_step_up(uow)
    current = _read(uow.session, api_client_id, lock=True)
    _require_reach(uow, current, action=ROTATE_ACTION)
    _require_active(current)
    client_secret = new_client_secret()
    uow.session.execute(
        update(api_client)
        .where(api_client.c.id == api_client_id)
        .values(
            secret_hash=passwords.hash_password(client_secret),
            secret_rotated_at=uow.now,
            **_stamps(uow, created=False),
        )
    )
    revoked = _revoke_tokens(uow.session, api_client_id, now=uow.now)
    row = _read(uow.session, api_client_id)
    previous = current["secret_rotated_at"]
    uow.audit(
        action=ROTATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=api_client_id,
        object_version=str(row["row_version"]),
        before={"secret_rotated_at": None if previous is None else previous.isoformat()},
        after={"secret_rotated_at": uow.now.isoformat()},
        detail={"tokens_revoked": revoked},
    )
    return IssuedSecret(client=row, client_secret=client_secret)


def revoke_api_client(
    uow: UnitOfWork, api_client_id: UUID, *, reason: str | None
) -> Mapping[str, Any]:
    """Revoke an ACTIVE client with a reason; every open token stops working at once. A client
    the actor does not reach answers 404 (``_require_reach``)."""
    current = _read(uow.session, api_client_id, lock=True)
    _require_reach(uow, current, action=REVOKE_ACTION)
    text = (reason or "").strip()
    if len(text) < MIN_REASON_LENGTH:
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="reason", rule_id=RULE_REASON, message=REASON_SHORT)],
        )
    _require_active(current)
    uow.session.execute(
        update(api_client)
        .where(api_client.c.id == api_client_id)
        .values(status=ApiClientStatus.REVOKED.value, **_stamps(uow, created=False))
    )
    revoked = _revoke_tokens(uow.session, api_client_id, now=uow.now)
    row = _read(uow.session, api_client_id)
    uow.audit(
        action=REVOKE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=api_client_id,
        object_version=str(row["row_version"]),
        before={"status": ApiClientStatus.ACTIVE.value},
        after={"status": ApiClientStatus.REVOKED.value},
        comment=text,
        detail={"tokens_revoked": revoked},
    )
    return row


def get_api_client(ctx: RequestContext, api_client_id: UUID) -> Mapping[str, Any]:
    """The client, for a reader who reaches it; 404 ``not-found`` for any other, as for an id
    that names no client (04 API-C-03; ``reaches``)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = _read(session, api_client_id)
    if not reaches(ctx.principal, row):
        raise Problem("not-found")
    return row


def list_api_clients[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the API clients the reader reaches (``in_reach``: a list holds what its
    reader may act on — every client for a holder of ``api_client.manage`` for all entities);
    ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*CLIENT_COLUMNS).where(in_reach(ctx.principal)))


def issue_token(
    *, client_id: str, client_secret: str, grant_type: str, scope: str | None, now: datetime
) -> IssuedToken:
    """The client-credentials grant (RFC 6749 §4.4; SAR-28).

    The client authenticates first: an unknown client id still runs one argon2 verification, and a
    wrong secret, a revoked client or an expired client gives 401 ``unauthenticated``. Then
    ``grant_type`` must be ``client_credentials`` and the space-separated ``scope``, when sent,
    must name scopes the client holds (422 ``validation-failed``); without it the token carries
    every scope of the client. The token row is written and ``last_used_at`` set in one
    transaction.
    """
    tenant_id = _tenant_of(client_id, CLIENT_ID_PATTERN)
    if tenant_id is None:
        passwords.verify_dummy(client_secret)
        raise client_refusal()
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        client = (
            session.execute(
                select(
                    api_client.c.id,
                    api_client.c.secret_hash,
                    api_client.c.scopes,
                    api_client.c.status,
                    api_client.c.expires_at,
                )
                .where(api_client.c.client_id == client_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if client is None:
            passwords.verify_dummy(client_secret)
            raise client_refusal()
        verified = passwords.verify_password(str(client["secret_hash"]), client_secret)
        if not verified or client["status"] != ApiClientStatus.ACTIVE.value:
            raise client_refusal()
        if client["expires_at"] <= now:
            raise client_refusal()
        if grant_type != GRANT_TYPE:
            raise Problem(
                "validation-failed",
                errors=[
                    ProblemError(field="grant_type", rule_id=RULE_TOKEN, message=GRANT_TYPE_INVALID)
                ],
            )
        held = {str(code) for code in client["scopes"]}
        requested = set(scope.split()) if scope is not None and scope.strip() else held
        if not requested <= held:
            raise Problem(
                "validation-failed",
                errors=[ProblemError(field="scope", rule_id=RULE_TOKEN, message=SCOPE_NOT_HELD)],
            )
        granted = tuple(
            sorted(
                code for code in requested if code in _BY_CODE and not _BY_CODE[code].is_approval
            )
        )
        access_token = new_access_token(tenant_id)
        session.execute(
            insert(api_token).values(
                tenant_id=tenant_id,
                id=new_id(),
                api_client_id=client["id"],
                token_sha256=token_sha256(access_token),
                scopes=list(granted),
                issued_at=now,
                expires_at=now + TOKEN_LIFETIME,
            )
        )
        session.execute(
            update(api_client)
            .where(api_client.c.id == client["id"])
            .values(
                last_used_at=now,
                updated_at=now,
                updated_by=client["id"],
                updated_by_kind=PrincipalKind.API_CLIENT.value,
            )
        )
    return IssuedToken(
        access_token=access_token,
        expires_in=int(TOKEN_LIFETIME.total_seconds()),
        scopes=granted,
    )


def token_principal(token: str, *, now: datetime) -> TokenPrincipal:
    """The API client principal of a bearer token (DG-KRN-AUTH-01 step 1).

    A malformed, unknown, expired or revoked token, or a token of a revoked or expired client,
    gives 401 ``unauthenticated`` with the bearer challenge.
    """
    tenant_id = _tenant_of(token, TOKEN_PATTERN)
    if tenant_id is None:
        raise bearer_refusal()
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        found = (
            session.execute(
                select(
                    api_token.c.scopes,
                    api_client.c.id,
                    api_client.c.name,
                    api_client.c.rate_limit_per_minute,
                    tenant.c.kind,
                    tenant.c.status.label("tenant_status"),
                )
                .select_from(
                    api_token.join(
                        api_client,
                        and_(
                            api_client.c.tenant_id == api_token.c.tenant_id,
                            api_client.c.id == api_token.c.api_client_id,
                        ),
                    ).join(tenant, tenant.c.id == api_token.c.tenant_id)
                )
                .where(
                    api_token.c.token_sha256 == token_sha256(token),
                    api_token.c.revoked_at.is_(None),
                    api_token.c.expires_at > now,
                    api_client.c.status == ApiClientStatus.ACTIVE.value,
                    api_client.c.expires_at > now,
                )
            )
            .mappings()
            .one_or_none()
        )
        if found is None:
            raise bearer_refusal()
        locale = session.execute(
            select(tenant.c.default_locale).where(tenant.c.id == tenant_id)
        ).scalar_one()
        grants = api_client_grants(
            session, found["id"], token_scopes=[str(code) for code in found["scopes"]], at=now
        )
    principal = Principal(
        kind=PrincipalKind.API_CLIENT,
        id=found["id"],
        tenant_id=tenant_id,
        membership_id=None,
        display_name=str(found["name"]),
        roles=grants.roles,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope=grants.entity_scope,
        auth_method="client_credentials",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    limit = found["rate_limit_per_minute"]
    return TokenPrincipal(
        principal=principal,
        tenant_kind=TenantKind(found["kind"]),
        default_locale=str(locale),
        rate_limit_per_minute=None if limit is None else int(limit),
        tenant_status=TenantStatus(found["tenant_status"]),
    )
