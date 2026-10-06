"""Persona sessions for seeds that act through the product's commands (PRD WLD-R-02; DG-MK-seed;
BUILD_SPEC PRF-2): accept an invitation with ``EREV_DEMO_PASSWORD``, enrol or verify TOTP from
``EREV_DEMO_TOTP_SECRET`` where the caller says the persona needs a factor (PRD WLD-U-R2:
``personas.needs_mfa``), and build the persona's
``RequestContext`` as a signed-in request would. Lifted from ``demo.seed`` (code-only refactor, lane
P7 slice 3b) so that ``erev perf seed`` reuses the same machinery; the MFA step-up is never
bypassed.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import select

from erev_api.auth import mfa, sessions, totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import effective_grants, spec
from erev_api.auth.principal import Principal, RequestContext
from erev_api.auth.sessions import AuthenticatedSession, RequestFacts
from erev_api.clock import Clock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import outbox_message, role
from erev_api.domain.demo.personas import Persona, TenantGroup
from erev_api.domain.platform import memberships, provisioning, users
from erev_api.enums import OutboxTopic, PrincipalKind
from erev_api.events import outbox
from erev_api.files.store import FileStore
from erev_api.problems import Problem
from erev_api.uow import unit_of_work

USER_MANAGE: Final = "user.manage"
_TOKEN_PREFIX: Final = provisioning.INVITATION_LINK.split("{token}", 1)[0]


@dataclass(frozen=True, slots=True)
class SeedSecrets:
    """The shared password and TOTP seed of the personas (``EREV_DEMO_PASSWORD``,
    ``EREV_DEMO_TOTP_SECRET``); never logged."""

    password: str
    totp_secret: str


def authorize(ctx: RequestContext, permission: str) -> None:
    """The route guard of a command a persona runs: the permission, and an MFA-verified session for
    a ``requires_mfa`` permission (04 API-C-03)."""
    principal = ctx.principal
    if permission not in principal.permissions:
        raise Problem("forbidden")
    if spec(permission).requires_mfa and principal.mfa_verified_at is None:
        raise Problem("mfa-required", mfa.VERIFICATION_REQUIRED)


def read_only(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def invitation_token(tenant_id: UUID, membership_id: UUID, keyring: KeyRing) -> str:
    """The token of the membership's newest invitation email, taken from its link as the persona
    would follow it (the outbox is the local mail channel, WLD-U-R4). The message names the token
    by reference; the link is composed as the dispatcher composes it
    (``outbox.email_link_path``)."""
    with tenant_session(read_only(tenant_id), read_only=True) as db:
        payload = db.execute(
            select(outbox_message.c.payload)
            .where(
                outbox_message.c.topic == OutboxTopic.EMAIL.value,
                outbox_message.c.aggregate_type == users.OBJECT_TYPE,
                outbox_message.c.aggregate_id == membership_id,
            )
            .order_by(outbox_message.c.created_at.desc(), outbox_message.c.id.desc())
            .limit(1)
        ).scalar_one()
    link = str(outbox.email_link_path(payload, keyring))
    if not link.startswith(_TOKEN_PREFIX):
        raise LookupError(f"the invitation email of membership {membership_id} has no token link")
    return link.removeprefix(_TOKEN_PREFIX)


def role_ids(tenant_id: UUID) -> dict[str, UUID]:
    with tenant_session(read_only(tenant_id), read_only=True) as db:
        return {
            str(code): UUID(str(role_id))
            for code, role_id in db.execute(select(role.c.code, role.c.id)).tuples()
        }


class PersonaRun:
    """The personas' sessions during one run: each persona's latest session, and whether that
    session is MFA-verified, so a verified persona is verified once per run."""

    def __init__(
        self,
        *,
        clock: Clock,
        keyring: KeyRing,
        files: FileStore,
        secrets: SeedSecrets,
        request_id: str,
    ) -> None:
        self.clock = clock
        self.keyring = keyring
        self.files = files
        self.secrets = secrets
        self.request_id = request_id
        self.sessions: dict[str, AuthenticatedSession] = {}
        self.verified: set[str] = set()
        self.recovery_codes: dict[str, list[str]] = {}

    def facts(self) -> RequestFacts:
        return RequestFacts(
            request_id=self.request_id, source_ip=None, user_agent=None, now=self.clock.now()
        )

    def _refreshed(self, auth: AuthenticatedSession) -> AuthenticatedSession:
        return dataclasses.replace(auth, facts=self.facts())

    def join(self, persona: Persona, tenant_id: UUID, membership_id: UUID, *, mfa: bool) -> None:
        """Accept the persona's invitation with the shared password; with ``mfa`` the persona's
        session in the workspace is then MFA-verified."""
        accepted = memberships.accept_invitation(
            token=invitation_token(tenant_id, membership_id, self.keyring),
            password=self.secrets.password,
            facts=self.facts(),
            keyring=self.keyring,
            clock=self.clock,
            files=self.files,
            previous_token=None,
        )
        current = self.sessions.get(persona.key)
        if current is not None and persona.key in self.verified:
            sessions.sign_out(self._refreshed(accepted), keyring=self.keyring)
            self.sessions[persona.key] = sessions.select_tenant(
                self._refreshed(current), tenant_id, keyring=self.keyring
            )
            return
        latest = accepted
        if mfa:
            latest = self._verified(persona, accepted)
            self.verified.add(persona.key)
        if current is not None:
            sessions.sign_out(self._refreshed(current), keyring=self.keyring)
        self.sessions[persona.key] = latest

    def _verified(self, persona: Persona, auth: AuthenticatedSession) -> AuthenticatedSession:
        """Enrol the TOTP seed and confirm it, keeping the ten recovery codes; a persona enrolled by
        an earlier run verifies instead."""
        secret = self.secrets.totp_secret
        step = totp.time_step(auth.facts.now)
        if mfa.has_confirmed_factor(auth.user.id, request_id=self.request_id):
            # [J] The earlier run confirmed with the code of its own step; the next step is still
            # inside the window when this run starts within the same 30 seconds (totp.WINDOW).
            code = totp.code_at(secret, step + totp.WINDOW)
            return mfa.verify(auth, code=code, recovery_code=None, keyring=self.keyring).auth
        mfa.enroll(auth, keyring=self.keyring, secret_base32=secret)
        confirmed, codes = mfa.confirm(auth, totp.code_at(secret, step), keyring=self.keyring)
        self.recovery_codes[persona.email] = codes
        return confirmed

    def step_up(self, persona: Persona) -> None:
        """BR-PLT-06 for a persona who decides late in a run (PRD WLD-R-02): a reconciliation's
        review and a lock decision ask for a verification at most ``mfa.STEP_UP_WINDOW`` old. When
        the persona's is older she verifies again by the command of the screen's step-up dialog
        (``mfa.verify``) with the code of the current TOTP step, and the reissued session replaces
        hers; a verification inside the window is left as it is, so under a clock that stands
        still no second code is asked for (and none of that instant would be unused)."""
        auth = self._refreshed(self.sessions[persona.key])
        if mfa.step_up_fresh_at(auth.session.mfa_verified_at, auth.facts.now):
            return
        code = totp.code_at(self.secrets.totp_secret, totp.time_step(auth.facts.now))
        self.sessions[persona.key] = mfa.verify(
            auth, code=code, recovery_code=None, keyring=self.keyring
        ).auth

    def context(self, persona: Persona, tenant_id: UUID) -> RequestContext:
        """The persona's request context in the workspace of its session, with the grants in force
        now (as ``get_request_context`` builds it for a signed-in request)."""
        auth = self.sessions[persona.key]
        active = auth.active_tenant
        if active is None or active.id != tenant_id or active.membership_id is None:
            raise LookupError(f"persona {persona.wld_id} has no session in tenant {tenant_id}")
        now = self.clock.now()
        lookup = DbContext(tenant_id=tenant_id, user_id=auth.user.id, entity_scope="*")
        with tenant_session(lookup, read_only=True) as db:
            grants = effective_grants(db, active.membership_id, at=now)
        principal = Principal(
            kind=PrincipalKind.USER,
            id=auth.user.id,
            tenant_id=tenant_id,
            membership_id=active.membership_id,
            display_name=auth.user.display_name,
            roles=grants.roles,
            permissions=grants.permissions,
            permission_scopes=grants.permission_scopes,
            entity_scope=grants.entity_scope,
            auth_method="password",
            mfa_verified_at=auth.session.mfa_verified_at,
            session_id=auth.session.id,
            support_grant_id=None,
            on_behalf_of_id=None,
            role_scopes=grants.role_scopes,
        )
        return RequestContext(
            principal=principal,
            tenant_kind=active.kind,
            request_id=self.request_id,
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=now,
            format_locale=active.default_locale,
            tenant_status=active.status,
        )

    def sign_out_all(self) -> None:
        for key in sorted(self.sessions):
            sessions.sign_out(self._refreshed(self.sessions[key]), keyring=self.keyring)
        self.sessions.clear()
        self.verified.clear()


def invite(
    run: PersonaRun, admin: Persona, persona: Persona, group: TenantGroup, tenant_id: UUID
) -> UUID:
    """``POST /users`` as the admin: the persona with its roles of ``group`` for all entities."""
    ctx = run.context(admin, tenant_id)
    authorize(ctx, USER_MANAGE)
    ids = role_ids(tenant_id)
    grants = [
        users.RoleGrant(role_id=ids[code], is_all_entities=True, entity_codes=())
        for code in persona.roles_in(group)
    ]
    with unit_of_work(ctx, clock=run.clock, keyring=run.keyring, files=run.files) as uow:
        membership_id = users.invite_user(
            uow, email=persona.email, display_name=persona.display_name, roles=grants
        )
        uow.commit()
    return membership_id
