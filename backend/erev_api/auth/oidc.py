"""OIDC sign-in (04 API-R-01 ``/session/oidc/*``, T-PLT-02, T-PLT-03, E-79 ``OIDC_LINKED``;
05 SAR-27, THR-05; 03 REQ-PLT-006; BUILD_SPEC PLF-27, BS1-D-25).

``begin`` starts the authorization code flow with PKCE S256, ``state`` and ``nonce``, and seals the
three values, bound to the provider, into a ten-minute flow cookie. ``complete`` checks the
returned ``state`` against the cookie, redeems the code with the verifier and validates the ID
token: an RS256 signature over the provider's JWKS, the issuer, the audience, the expiry and the
nonce. A provider signs in only a verified email of the domains the operator bound it to
(``email_domains``: at creation, changed afterwards by ``erev idp domains`` alone), and
``sessions.sign_in_external`` signs in only the existing ACTIVE identity
that was invited for the provider, under one provider subject — never an identity by its email
alone (REQ-PLT-006; ruling R-48 (d)); the IdP never creates a user or grants a role (THR-05).
Provider requests go through ``OidcHttp``, which an adapter implements (DG-ARC-12).
``create_provider`` backs ``erev idp create``, ``invite_identity`` ``erev idp invite``,
``change_domains`` ``erev idp domains``, ``set_enabled`` ``erev idp disable`` and ``erev idp
enable``, and ``end_sessions`` ``erev idp end-sessions``. A provider that is not enabled signs
nobody in: ``GET /session`` does not offer it, ``begin`` answers 404 as for an unknown code, and
``complete`` refuses with ``LOGIN_FAILED`` (reason ``provider_disabled``) before anything is sent
to the provider; a callback that was past that check when the operator disabled the provider is
refused by ``sessions.sign_in_external``, which reads the provider again in the transaction that
opens the session (05 SAR-27 rev 1.178).
"""

from __future__ import annotations

import base64
import hmac
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, NoReturn, Protocol, cast
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet, KeySetSerialization
from sqlalchemy import func, insert, select, update

from erev_api.auth import sessions
from erev_api.auth.keyring import KeyRing
from erev_api.auth.security_events import record_security_event
from erev_api.auth.sessions import AuthenticatedSession, RequestFacts
from erev_api.config import LOCAL_ENVIRONMENTS, Environment
from erev_api.db import new_id
from erev_api.db.session import identity_session, owner_engine
from erev_api.db.tables.platform import app_user, identity_provider
from erev_api.enums import (
    AuditOutcome,
    IdentityProviderKind,
    PrincipalKind,
    SecurityEventKind,
    UserStatus,
)
from erev_api.problems import Problem, ProblemError

FLOW_COOKIE: Final = "erev_oidc"
FLOW_COOKIE_PATH: Final = "/api/v1/session/oidc"
FLOW_LIFETIME: Final = timedelta(minutes=10)
FLOW_CONTEXT: Final = "oidc-flow"
FLOW_FIELDS: Final = frozenset({"state", "nonce", "verifier", "expires_at"})
CALLBACK_PATH: Final = "/api/v1/session/oidc/{provider}/callback"
# SCREENS_B §12.1: after sign-in SF-22 (RT-01 `/sign-in`) reads GET /me and chooses the landing.
SIGNED_IN_PATH: Final = "/sign-in"
DISCOVERY_PATH: Final = "/.well-known/openid-configuration"
DEFAULT_SCOPES: Final = "openid email profile"
ID_TOKEN_ALGORITHMS: Final = ("RS256",)
CLOCK_LEEWAY_SECONDS: Final = 60
# RFC 7636 §4.1: a verifier of 43 to 128 unreserved characters; state and nonce share the length.
TOKEN_LENGTH: Final = 64
CREATE_COMMAND: Final = "idp.create"
INVITE_COMMAND: Final = "idp.invite"
DOMAINS_COMMAND: Final = "idp.domains"
DISABLE_COMMAND: Final = "idp.disable"
ENABLE_COMMAND: Final = "idp.enable"
END_SESSIONS_COMMAND: Final = "idp.end-sessions"
# The reason of ``LOGIN_FAILED`` when a callback names a provider the operator disabled.
PROVIDER_DISABLED: Final = sessions.PROVIDER_DISABLED
RULE_PROVIDER: Final = "T-PLT-03"
# [J] SPEC-Q-192: the code appears in the callback path, so it uses a URL-safe subset of TY-06.
PROVIDER_CODE: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
LABEL_LENGTH: Final = range(1, 401)  # erev.label (TY-07)
REFERENCE_LENGTH: Final = range(1, 256)
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost"})
# REQ-PLT-006: the email domains a provider is authoritative for — host names in lower case.
EMAIL_DOMAIN: Final = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)
EMAIL_DOMAIN_COUNT: Final = range(1, 21)
# OpenID Connect Core §2: a subject is at most 255 ASCII characters.
SUBJECT_LENGTH: Final = range(1, 256)

# [J] SPEC-Q-192: copy the documents leave open.
UNAVAILABLE: Final = (
    "Sign-in through {name} is not available. Try again or sign in with your email and password."
)
CODE_INVALID: Final = "Use 1 to 63 lower-case letters, digits, hyphens or underscores."
CODE_TAKEN: Final = "An identity provider with this code already exists."
KIND_REFUSED: Final = "Only oidc identity providers can be created in this release."
NAME_LENGTH: Final = "Use 1 to 400 characters."
ISSUER_INVALID: Final = "Enter an https issuer URL without a query or fragment."
# D-80 [J] SPEC-Q-212: the refusal outside dev, test and e2e names the public-host requirement.
ISSUER_NOT_PUBLIC: Final = "Enter an https issuer URL on a public host without a query or fragment."
REFERENCE_INVALID: Final = "Use 1 to 255 characters."
DOMAINS_INVALID: Final = "Name 1 to 20 email domains in lower case, such as example.com, each once."
PROVIDER_UNKNOWN: Final = "No OIDC identity provider has this code."
DOMAIN_NOT_BOUND: Final = "The identity provider is not bound to the domain of this email address."
IDENTITY_UNKNOWN: Final = "No active identity has this email address."
OPERATOR_REFUSED: Final = "A platform operator signs in with a password and TOTP only."
LINKED_ELSEWHERE: Final = "This identity belongs to another identity provider."
DOMAINS_UNCHANGED: Final = "Name at least one email domain to add or to remove."
DOMAIN_INVALID: Final = "Name email domains in lower case, such as example.com, each once."
DOMAIN_BOTH: Final = "A domain cannot be added and removed by one command."
DOMAINS_COUNT: Final = "An identity provider keeps 1 to 20 email domains."
PROVIDER_ENABLED: Final = (
    "Disable the identity provider first. While it is enabled, a session that is ended is opened "
    "again at the next sign-in."
)


class OidcHttpError(Exception):
    """A provider request failed: transport error, non-2xx status or a body that is no object."""


class OidcHttp(Protocol):
    """Requests to an identity provider (implemented by ``adapters.idp.oidc_http``)."""

    def get_json(self, url: str) -> dict[str, Any]: ...

    def post_form(self, url: str, form: Mapping[str, str]) -> dict[str, Any]: ...


class SecretSource(Protocol):
    def secret(self, ref: str) -> str: ...


@dataclass(frozen=True, slots=True)
class Provider:
    id: UUID
    code: str
    display_name: str
    issuer_url: str
    client_id: str
    client_secret_ref: str | None
    scopes: str
    # The email domains the provider is authoritative for; it signs in no other (REQ-PLT-006).
    email_domains: tuple[str, ...] = ()
    # False once the operator took the provider out of sign-in (``erev idp disable``).
    is_enabled: bool = True


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


@dataclass(frozen=True, slots=True)
class OidcStart:
    location: str
    flow_token: str


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    code: str
    kind: str
    display_name: str
    issuer_url: str
    client_id: str
    client_secret_ref: str | None = None
    email_domains: tuple[str, ...] = ()


def email_domain(email: str) -> str:
    """The domain of an email address, lower case; empty without one."""
    return sessions.normalise_email(email).rpartition("@")[2]


def flow_cookie_header(token: str, *, secure: bool) -> str:
    """HttpOnly and SameSite=Lax, so the provider's top-level redirect back carries it."""
    max_age = int(FLOW_LIFETIME.total_seconds())
    header = (
        f"{FLOW_COOKIE}={token}; Path={FLOW_COOKIE_PATH}; Max-Age={max_age}; HttpOnly; SameSite=Lax"
    )
    return header + "; Secure" if secure else header


def cleared_flow_cookie_header(*, secure: bool) -> str:
    header = f"{FLOW_COOKIE}=; Path={FLOW_COOKIE_PATH}; Max-Age=0; HttpOnly; SameSite=Lax"
    return header + "; Secure" if secure else header


def redirect_uri(public_origin: str, provider_code: str) -> str:
    """The callback the browser reaches through the eRev origin."""
    return public_origin + CALLBACK_PATH.format(provider=provider_code)


def find_provider(code: str, *, request_id: str, enabled_only: bool = True) -> Provider:
    """The enabled ``oidc`` provider with ``code``; otherwise 404 ``not-found``. Without
    ``enabled_only`` a provider the operator disabled is returned as well, marked by
    ``is_enabled``: the callback refuses it by name instead of answering as for an unknown code."""
    with identity_session(request_id=request_id) as db:
        row = (
            db.execute(
                select(
                    identity_provider.c.id,
                    identity_provider.c.code,
                    identity_provider.c.display_name,
                    identity_provider.c.issuer_url,
                    identity_provider.c.client_id,
                    identity_provider.c.client_secret_ref,
                    identity_provider.c.config,
                    identity_provider.c.email_domains,
                    identity_provider.c.is_enabled,
                ).where(
                    identity_provider.c.code == code,
                    identity_provider.c.kind == IdentityProviderKind.OIDC.value,
                )
            )
            .mappings()
            .one_or_none()
        )
    if row is None or row["issuer_url"] is None or row["client_id"] is None:
        raise Problem("not-found")
    if enabled_only and not row["is_enabled"]:
        raise Problem("not-found")
    config = row["config"] if isinstance(row["config"], Mapping) else {}
    scopes = config.get("scopes")
    return Provider(
        id=row["id"],
        code=str(row["code"]),
        display_name=str(row["display_name"]),
        issuer_url=str(row["issuer_url"]),
        client_id=str(row["client_id"]),
        client_secret_ref=None
        if row["client_secret_ref"] is None
        else str(row["client_secret_ref"]),
        scopes=scopes if isinstance(scopes, str) and scopes else DEFAULT_SCOPES,
        email_domains=tuple(str(domain) for domain in row["email_domains"]),
        is_enabled=bool(row["is_enabled"]),
    )


def discover(http: OidcHttp, provider: Provider) -> ProviderMetadata:
    """The endpoints of the provider's discovery document; its issuer must equal ``issuer_url``."""
    document = http.get_json(provider.issuer_url.rstrip("/") + DISCOVERY_PATH)
    endpoints = [
        document.get(name) for name in ("authorization_endpoint", "token_endpoint", "jwks_uri")
    ]
    if document.get("issuer") != provider.issuer_url or not all(
        isinstance(value, str) and value for value in endpoints
    ):
        raise OidcHttpError("the discovery document does not describe this provider")
    authorization, token, jwks = (str(value) for value in endpoints)
    return ProviderMetadata(
        authorization_endpoint=authorization, token_endpoint=token, jwks_uri=jwks
    )


def _flow_context(provider_code: str) -> dict[str, str]:
    return {"purpose": FLOW_CONTEXT, "provider": provider_code}


def seal_flow(keyring: KeyRing, provider_code: str, flow: Mapping[str, str]) -> str:
    """The flow values encrypted under the provider's context, base64url without padding."""
    plaintext = json.dumps(dict(flow), sort_keys=True).encode("utf-8")
    blob = keyring.encrypt(plaintext, context=_flow_context(provider_code))
    return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


def open_flow(keyring: KeyRing, provider_code: str, token: str) -> dict[str, str] | None:
    """The values ``seal_flow`` sealed for this provider, or None for any other cookie."""
    try:
        blob = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        flow = json.loads(keyring.decrypt(blob, context=_flow_context(provider_code)))
    except Exception:  # a malformed, tampered or foreign cookie opens nothing
        return None
    if (
        not isinstance(flow, dict)
        or set(flow) != FLOW_FIELDS
        or not all(isinstance(value, str) for value in flow.values())
    ):
        return None
    return {str(name): str(value) for name, value in flow.items()}


def begin(
    provider_code: str,
    *,
    facts: RequestFacts,
    keyring: KeyRing,
    http: OidcHttp,
    public_origin: str,
) -> OidcStart:
    """The authorization request with PKCE S256, ``state`` and ``nonce``, and its flow cookie.

    404 ``not-found`` for an unknown, disabled or non-oidc provider; 401 ``unauthenticated`` when
    the provider's discovery document cannot be read or describes another issuer.
    """
    provider = find_provider(provider_code, request_id=facts.request_id)
    try:
        metadata = discover(http, provider)
    except OidcHttpError as error:
        raise Problem("unauthenticated", UNAVAILABLE.format(name=provider.display_name)) from error
    state, nonce, verifier = (str(generate_token(TOKEN_LENGTH)) for _ in range(3))
    flow = {
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "expires_at": (facts.now + FLOW_LIFETIME).isoformat(),
    }
    query = urlencode(
        {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": redirect_uri(public_origin, provider.code),
            "scope": provider.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": str(create_s256_code_challenge(verifier)),
            "code_challenge_method": "S256",
        }
    )
    endpoint = metadata.authorization_endpoint
    separator = "&" if "?" in endpoint else "?"
    return OidcStart(
        location=f"{endpoint}{separator}{query}",
        flow_token=seal_flow(keyring, provider.code, flow),
    )


def token_form(
    provider: Provider, *, code: str, verifier: str, public_origin: str, secrets: SecretSource
) -> dict[str, str]:
    """The RFC 6749 §4.1.3 token request with the PKCE verifier; a confidential client adds the
    secret its reference names in the secret store (05 KEY-09, SAR-27)."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(public_origin, provider.code),
        "client_id": provider.client_id,
        "code_verifier": verifier,
    }
    if provider.client_secret_ref is not None:
        form["client_secret"] = secrets.secret(provider.client_secret_ref)
    return form


def validated_claims(
    id_token: object,
    *,
    provider: Provider,
    jwks: Mapping[str, Any],
    nonce: str,
    now: datetime,
) -> dict[str, Any] | None:
    """The claims of an RS256 ID token signed by a key of ``jwks``, issued by the provider to its
    client, unexpired and carrying ``nonce``; otherwise None."""
    if not isinstance(id_token, str):
        return None
    registry = jwt.JWTClaimsRegistry(
        now=int(now.timestamp()),
        leeway=CLOCK_LEEWAY_SECONDS,
        iss={"essential": True, "value": provider.issuer_url},
        aud={"essential": True, "value": provider.client_id},
        sub={"essential": True},
        exp={"essential": True},
        nonce={"essential": True, "value": nonce},
    )
    try:
        key_set = KeySet.import_key_set(cast(KeySetSerialization, dict(jwks)))
        token = jwt.decode(id_token, key_set, algorithms=list(ID_TOKEN_ALGORITHMS))
        registry.validate(token.claims)
    except (JoseError, ValueError, KeyError, TypeError):
        return None
    return dict(token.claims)


def _refuse(
    provider: Provider,
    facts: RequestFacts,
    keyring: KeyRing,
    *,
    reason: str,
    email: str | None = None,
) -> NoReturn:
    """Commit ``LOGIN_FAILED`` naming the provider and the reason — and, for a refused email, its
    SHA-256 — then 401 ``unauthenticated``."""
    with identity_session(request_id=facts.request_id) as db:
        record_security_event(
            db,
            keyring=keyring,
            kind=SecurityEventKind.LOGIN_FAILED,
            outcome=AuditOutcome.FAILED,
            request_id=facts.request_id,
            email_sha256=None
            if email is None
            else sessions.sha256_hex(sessions.normalise_email(email)),
            ip_address=facts.source_ip,
            user_agent=facts.user_agent,
            detail={
                "auth_method": IdentityProviderKind.OIDC.value,
                "provider": provider.code,
                "reason": reason,
            },
        )
    raise Problem("unauthenticated", sessions.OIDC_REFUSED)


def complete(
    provider_code: str,
    *,
    code: str | None,
    state: str | None,
    flow_token: str | None,
    facts: RequestFacts,
    keyring: KeyRing,
    http: OidcHttp,
    public_origin: str,
    previous_token: str | None,
) -> AuthenticatedSession:
    """The callback: a new session for the identity invited for the provider, or 401
    ``unauthenticated`` (THR-05). The provider vouches only for the email domains it was bound to
    (REQ-PLT-006): a verified email of another domain is refused before any identity is read.

    A provider the operator disabled (``erev idp disable``) is refused first, with
    ``LOGIN_FAILED`` and the reason ``provider_disabled``: a sign-in that was started before the
    provider was taken out ends here, and nothing is sent to the provider. An unknown code
    answers 404 ``not-found``."""
    provider = find_provider(provider_code, request_id=facts.request_id, enabled_only=False)
    if not provider.is_enabled:
        _refuse(provider, facts, keyring, reason=PROVIDER_DISABLED)
    flow = None if flow_token is None else open_flow(keyring, provider.code, flow_token)
    if (
        flow is None
        or code is None
        or state is None
        or not hmac.compare_digest(state.encode("utf-8"), flow["state"].encode("utf-8"))
        or datetime.fromisoformat(flow["expires_at"]) <= facts.now
    ):
        _refuse(provider, facts, keyring, reason="state_mismatch")
    try:
        metadata = discover(http, provider)
        tokens = http.post_form(
            metadata.token_endpoint,
            token_form(
                provider,
                code=code,
                verifier=flow["verifier"],
                public_origin=public_origin,
                secrets=keyring,
            ),
        )
        jwks = http.get_json(metadata.jwks_uri)
    except OidcHttpError:
        _refuse(provider, facts, keyring, reason="provider_request_failed")
    claims = validated_claims(
        tokens.get("id_token"), provider=provider, jwks=jwks, nonce=flow["nonce"], now=facts.now
    )
    if claims is None:
        _refuse(provider, facts, keyring, reason="id_token_invalid")
    email = claims.get("email")
    if not isinstance(email, str) or claims.get("email_verified") is not True:
        _refuse(provider, facts, keyring, reason="email_not_verified")
    subject = claims.get("sub")
    if not isinstance(subject, str) or len(subject) not in SUBJECT_LENGTH:
        _refuse(provider, facts, keyring, reason="id_token_invalid")
    if email_domain(email) not in provider.email_domains:
        _refuse(provider, facts, keyring, reason="email_domain_not_bound", email=email)
    return sessions.sign_in_external(
        email=email,
        subject=subject,
        provider_id=provider.id,
        provider_code=provider.code,
        facts=facts,
        keyring=keyring,
        previous_token=previous_token,
    )


def _is_loopback_host(host: str) -> bool:
    try:
        return host in LOOPBACK_HOSTS or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _issuer_valid(url: str, *, env: Environment) -> bool:
    """An issuer without a query, fragment or credentials. Under ``dev``, ``test`` and ``e2e`` it
    is https, or http on a loopback host for the mock IdP; elsewhere it is https on a host that is
    not loopback (05 SAR-15; D-80)."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.query or parts.fragment or not host or parts.username or parts.password:
        return False
    if env in LOCAL_ENVIRONMENTS:
        return parts.scheme == "https" or (parts.scheme == "http" and _is_loopback_host(host))
    return parts.scheme == "https" and not _is_loopback_host(host)


def create_provider(
    spec: ProviderSpec, *, request_id: str, keyring: KeyRing, env: Environment
) -> dict[str, Any]:
    """``erev idp create`` (BS1-D-25): one ``identity_provider`` row written as ``erev_owner``,
    which alone may write the table (04 §14.2), and ``PLATFORM_SCOPE_USED`` with
    ``detail.command`` ``idp.create``.

    422 ``validation-failed`` with rule ``T-PLT-03`` for a malformed or used code, a kind other
    than ``oidc`` (``saml`` is rejected in 1.0), a display name outside 1 to 400 characters, an
    issuer that ``_issuer_valid`` refuses for ``env``, a client id or secret reference outside
    1 to 255 characters, and email domains that are not 1 to 20 distinct lower-case host names:
    a provider is bound at creation to the domains it is authoritative for (REQ-PLT-006).
    """
    name = spec.display_name.strip()
    domains = tuple(domain.strip().lower() for domain in spec.email_domains)
    checks = (
        ("code", PROVIDER_CODE.fullmatch(spec.code) is not None, CODE_INVALID),
        ("kind", spec.kind == IdentityProviderKind.OIDC.value, KIND_REFUSED),
        ("display_name", len(name) in LABEL_LENGTH, NAME_LENGTH),
        (
            "issuer_url",
            _issuer_valid(spec.issuer_url, env=env),
            ISSUER_INVALID if env in LOCAL_ENVIRONMENTS else ISSUER_NOT_PUBLIC,
        ),
        ("client_id", len(spec.client_id) in REFERENCE_LENGTH, REFERENCE_INVALID),
        (
            "client_secret_ref",
            spec.client_secret_ref is None or len(spec.client_secret_ref) in REFERENCE_LENGTH,
            REFERENCE_INVALID,
        ),
        (
            "email_domains",
            len(domains) in EMAIL_DOMAIN_COUNT
            and len(set(domains)) == len(domains)
            and all(EMAIL_DOMAIN.fullmatch(domain) for domain in domains),
            DOMAINS_INVALID,
        ),
    )
    errors = [
        ProblemError(field=field, rule_id=RULE_PROVIDER, message=message)
        for field, valid, message in checks
        if not valid
    ]
    if errors:
        raise Problem("validation-failed", errors=errors)
    provider_id = new_id()
    with owner_engine().begin() as connection:
        taken = connection.execute(
            select(identity_provider.c.id).where(identity_provider.c.code == spec.code)
        ).first()
        if taken is not None:
            raise Problem(
                "validation-failed",
                errors=[ProblemError(field="code", rule_id=RULE_PROVIDER, message=CODE_TAKEN)],
            )
        connection.execute(
            insert(identity_provider).values(
                id=provider_id,
                code=spec.code,
                kind=spec.kind,
                display_name=name,
                issuer_url=spec.issuer_url,
                client_id=spec.client_id,
                client_secret_ref=spec.client_secret_ref,
                email_domains=list(domains),
                created_by_kind=PrincipalKind.SYSTEM.value,
                updated_by_kind=PrincipalKind.SYSTEM.value,
            )
        )
        record_security_event(
            connection,
            keyring=keyring,
            kind=SecurityEventKind.PLATFORM_SCOPE_USED,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
            detail={"command": CREATE_COMMAND},
        )
    return {
        "id": provider_id,
        "code": spec.code,
        "kind": spec.kind,
        "display_name": name,
        "issuer_url": spec.issuer_url,
        "client_id": spec.client_id,
        "client_secret_ref": spec.client_secret_ref,
        "email_domains": list(domains),
        "is_enabled": True,
    }


def _invite_refused(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed",
        errors=[ProblemError(field=field, rule_id=RULE_PROVIDER, message=message)],
    )


def invite_identity(*, code: str, email: str, request_id: str, keyring: KeyRing) -> dict[str, Any]:
    """``erev idp invite`` (REQ-PLT-006; ruling R-48 (d)): the existing identity with ``email`` is
    invited for the provider ``code`` — ``app_user.identity_provider_id`` names it — so that its
    first sign-in through the provider links it. Written as ``erev_owner`` with
    ``PLATFORM_SCOPE_USED`` (``detail.command`` ``idp.invite``) on the identity.

    422 ``validation-failed`` with rule ``T-PLT-03``: an unknown provider code; an email outside
    the provider's domains; no identity, or a disabled one, with that email; a platform operator
    (an operator never signs in through a provider); an identity that belongs to another
    provider. Inviting an identity twice changes nothing and is answered as the first time.
    """
    normalised = sessions.normalise_email(email)
    with owner_engine().begin() as connection:
        provider = (
            connection.execute(
                select(identity_provider.c.id, identity_provider.c.email_domains).where(
                    identity_provider.c.code == code,
                    identity_provider.c.kind == IdentityProviderKind.OIDC.value,
                )
            )
            .mappings()
            .one_or_none()
        )
        if provider is None:
            raise _invite_refused("code", PROVIDER_UNKNOWN)
        if email_domain(normalised) not in provider["email_domains"]:
            raise _invite_refused("email", DOMAIN_NOT_BOUND)
        user = (
            connection.execute(
                select(
                    app_user.c.id,
                    app_user.c.status,
                    app_user.c.is_operator,
                    app_user.c.identity_provider_id,
                    app_user.c.identity_provider_subject,
                )
                .where(app_user.c.email == normalised)
                .with_for_update(key_share=True)
            )
            .mappings()
            .one_or_none()
        )
        if user is None or user["status"] == UserStatus.DISABLED:
            raise _invite_refused("email", IDENTITY_UNKNOWN)
        if user["is_operator"]:
            raise _invite_refused("email", OPERATOR_REFUSED)
        if user["identity_provider_id"] not in (None, provider["id"]):
            raise _invite_refused("email", LINKED_ELSEWHERE)
        invited = user["identity_provider_id"] is None
        if invited:
            connection.execute(
                update(app_user)
                .where(app_user.c.id == user["id"])
                .values(
                    identity_provider_id=provider["id"],
                    updated_by=None,
                    updated_by_kind=PrincipalKind.SYSTEM.value,
                )
            )
        record_security_event(
            connection,
            keyring=keyring,
            kind=SecurityEventKind.PLATFORM_SCOPE_USED,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
            user_id=user["id"],
            detail={"command": INVITE_COMMAND, "provider": code, "invited": invited},
        )
    return {
        "provider": code,
        "email": normalised,
        "user_id": user["id"],
        "invited": invited,
        "linked": user["identity_provider_subject"] is not None,
    }


def _domains(named: Sequence[str]) -> tuple[tuple[str, ...], bool]:
    """The domains an option names, trimmed and in lower case, and whether each is a host name
    named once."""
    domains = tuple(domain.strip().lower() for domain in named)
    valid = len(set(domains)) == len(domains) and all(
        EMAIL_DOMAIN.fullmatch(domain) for domain in domains
    )
    return domains, valid


def change_domains(
    *, code: str, add: Sequence[str], remove: Sequence[str], request_id: str, keyring: KeyRing
) -> dict[str, Any]:
    """``erev idp domains`` (OPS-IDP-DOMAINS-1; 04 T-PLT-03 rev 1.217; REQ-PLT-006): the email
    domains of the provider ``code`` gain ``add`` and lose ``remove``. Written as ``erev_owner``
    in one transaction that holds the provider's row, with ``PLATFORM_SCOPE_USED``
    (``detail.command`` ``idp.domains``, the provider, the domains added and removed, and the
    number of identities left outside).

    The change takes effect at the next sign-in: the callback reads the provider's row every
    time. An identity that was invited for the provider and whose email is outside the resulting
    domains is no longer signed in through it and keeps every other way in; the command counts
    such identities (``identities_outside``) and does not refuse for them - taking a domain from
    a provider is how its authority over that domain ends.

    422 ``validation-failed`` with rule ``T-PLT-03``: no domain named; a domain that is not a
    host name, or one named twice in an option; a domain named to be added and removed; an
    unknown provider code; a result outside 1 to 20 domains - a provider keeps at least one, as
    at its creation. Adding a domain that is bound, or removing one that is not, changes nothing
    and is answered as done.
    """
    adding, add_valid = _domains(add)
    removing, remove_valid = _domains(remove)
    checks = (
        ("email_domains", bool(adding or removing), DOMAINS_UNCHANGED),
        ("add", add_valid, DOMAIN_INVALID),
        ("remove", remove_valid, DOMAIN_INVALID),
        ("email_domains", not set(adding) & set(removing), DOMAIN_BOTH),
    )
    errors = [
        ProblemError(field=field, rule_id=RULE_PROVIDER, message=message)
        for field, valid, message in checks
        if not valid
    ]
    if errors:
        raise Problem("validation-failed", errors=errors)
    with owner_engine().begin() as connection:
        provider = (
            connection.execute(
                select(identity_provider.c.id, identity_provider.c.email_domains)
                .where(
                    identity_provider.c.code == code,
                    identity_provider.c.kind == IdentityProviderKind.OIDC.value,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if provider is None:
            raise _invite_refused("code", PROVIDER_UNKNOWN)
        before = [str(domain) for domain in provider["email_domains"]]
        added = [domain for domain in adding if domain not in before]
        removed = [domain for domain in removing if domain in before]
        after = [domain for domain in before if domain not in removed] + added
        if len(after) not in EMAIL_DOMAIN_COUNT:
            raise _invite_refused("email_domains", DOMAINS_COUNT)
        if added or removed:
            connection.execute(
                update(identity_provider)
                .where(identity_provider.c.id == provider["id"])
                .values(
                    email_domains=after,
                    updated_by=None,
                    updated_by_kind=PrincipalKind.SYSTEM.value,
                )
            )
        outside = connection.execute(
            select(func.count())
            .select_from(app_user)
            .where(
                app_user.c.identity_provider_id == provider["id"],
                app_user.c.status != UserStatus.DISABLED.value,
                func.split_part(app_user.c.email, "@", 2).not_in(after),
            )
        ).scalar_one()
        record_security_event(
            connection,
            keyring=keyring,
            kind=SecurityEventKind.PLATFORM_SCOPE_USED,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
            detail={
                "command": DOMAINS_COMMAND,
                "provider": code,
                "added": added,
                "removed": removed,
                "identities_outside": int(outside),
            },
        )
    return {
        "provider": code,
        "email_domains": after,
        "added": added,
        "removed": removed,
        "identities_outside": int(outside),
    }


def set_enabled(*, code: str, enabled: bool, request_id: str, keyring: KeyRing) -> dict[str, Any]:
    """``erev idp disable`` and ``erev idp enable`` (OPS-IDP-DOMAINS-1 with the supervisor's
    ruling of 2026-10-01; 04 T-PLT-03 rev 1.217; 05 SAR-27 rev 1.156): the provider ``code``
    is taken out of sign-in, or put back. Written as ``erev_owner`` in one transaction that holds
    the provider's row, with ``PLATFORM_SCOPE_USED`` (``detail.command`` ``idp.disable`` or
    ``idp.enable``, the provider, and whether the row changed).

    While a provider is not enabled ``GET /session`` does not offer it, its start route answers
    404 and its callback refuses with ``LOGIN_FAILED`` (``provider_disabled``) - from the next
    request on, because each reads the provider's row - and a callback that was past its first
    read is refused by the second, in ``sessions.sign_in_external`` (rev 1.178). Nothing else
    changes: its identities stay invited and linked and keep every other way in, and a session
    that was opened through the provider stays open until it ends or expires, or until the
    operator ends it (``end_sessions``).

    422 ``validation-failed`` with rule ``T-PLT-03``: an unknown provider code. Disabling a
    provider that is disabled, or enabling one that is enabled, does not write the row and is
    answered as done, with its event.
    """
    with owner_engine().begin() as connection:
        provider = (
            connection.execute(
                select(identity_provider.c.id, identity_provider.c.is_enabled)
                .where(
                    identity_provider.c.code == code,
                    identity_provider.c.kind == IdentityProviderKind.OIDC.value,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if provider is None:
            raise _invite_refused("code", PROVIDER_UNKNOWN)
        changed = bool(provider["is_enabled"]) is not enabled
        if changed:
            connection.execute(
                update(identity_provider)
                .where(identity_provider.c.id == provider["id"])
                .values(
                    is_enabled=enabled,
                    updated_by=None,
                    updated_by_kind=PrincipalKind.SYSTEM.value,
                )
            )
        record_security_event(
            connection,
            keyring=keyring,
            kind=SecurityEventKind.PLATFORM_SCOPE_USED,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
            detail={
                "command": ENABLE_COMMAND if enabled else DISABLE_COMMAND,
                "provider": code,
                "changed": changed,
            },
        )
    return {"provider": code, "is_enabled": enabled, "changed": changed}


def end_sessions(*, code: str, request_id: str, keyring: KeyRing, now: datetime) -> dict[str, Any]:
    """``erev idp end-sessions`` (item OPS-IDP-SESSIONS-1; 05 SAR-27 rev 1.178; 04 T-PLT-08 rev
    1.249): the sessions that are open and were opened through the provider ``code`` end with
    ``REVOKED`` - what an operator does after disabling a provider that can no longer be trusted
    (``sessions.end_provider_sessions`` says which rows, and why the command is exact against a
    sign-in under way). One transaction as ``erev_app``, which may write sessions and security
    events and read the provider's row (04 section 14.2): the command needs no owner URL. It
    writes ``PLATFORM_SCOPE_USED`` (``detail.command`` ``idp.end-sessions``, the provider, the
    identities that had such a session and the sessions ended). A second run ends nothing and is
    answered as done, with its event.

    422 ``validation-failed`` with rule ``T-PLT-03``: an unknown provider code, and a provider
    that is enabled - its sessions would be opened again by the next sign-in, so the command
    would only look as if it had worked. Nothing is written for a refusal."""
    with identity_session(request_id=request_id) as db:
        provider = (
            db.execute(
                select(identity_provider.c.id, identity_provider.c.is_enabled).where(
                    identity_provider.c.code == code,
                    identity_provider.c.kind == IdentityProviderKind.OIDC.value,
                )
            )
            .mappings()
            .one_or_none()
        )
        if provider is None:
            raise _invite_refused("code", PROVIDER_UNKNOWN)
        if provider["is_enabled"]:
            raise _invite_refused("code", PROVIDER_ENABLED)
        identities, ended = sessions.end_provider_sessions(db, provider["id"], now=now)
        record_security_event(
            db,
            keyring=keyring,
            kind=SecurityEventKind.PLATFORM_SCOPE_USED,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
            detail={
                "command": END_SESSIONS_COMMAND,
                "provider": code,
                "identities": identities,
                "sessions_ended": ended,
            },
        )
    return {"provider": code, "identities": identities, "sessions_ended": ended}


def list_providers(*, request_id: str) -> dict[str, Any]:
    """``erev idp list`` (05 SAR-27 rev 1.201; 04 T-PLT-03; a rider of item
    INVITE-ACCEPT-SESSION-1): every identity provider with its code, kind, name, issuer, email
    domains and whether it is enabled, ordered by code. The other ``erev idp`` commands take the
    code of an ``oidc`` provider and name none when they refuse an unknown one; until this
    command an operator had a code only from the line ``erev idp create`` printed.

    One transaction as ``erev_app``, which reads the provider's row (04 section 14.2): the
    command needs no owner URL, writes nothing and leaves no event - the sign-in page reads the
    enabled providers of the same table for anybody."""
    with identity_session(request_id=request_id) as db:
        rows = (
            db.execute(
                select(
                    identity_provider.c.code,
                    identity_provider.c.kind,
                    identity_provider.c.display_name,
                    identity_provider.c.issuer_url,
                    identity_provider.c.email_domains,
                    identity_provider.c.is_enabled,
                ).order_by(identity_provider.c.code)
            )
            .mappings()
            .all()
        )
    return {
        "providers": [
            {
                "code": str(row["code"]),
                "kind": str(getattr(row["kind"], "value", row["kind"])),
                "display_name": str(row["display_name"]),
                "issuer_url": row["issuer_url"],
                "email_domains": sorted(row["email_domains"] or ()),
                "is_enabled": bool(row["is_enabled"]),
            }
            for row in rows
        ]
    }
