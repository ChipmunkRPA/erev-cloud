"""Demo seed scaffold (docs/02-PRD.md §2.1 WLD-R-01 to WLD-R-04, §2.3, §2.4; dev-guide DG-MK-seed,
DG-RUN-32, DG-PERF-06; 04 §14.3; BUILD_SPEC WEB-10, BS1-D-20; D-75 PRD Q1).

``seed_demo`` builds each requested demo tenant through the product's commands, executed as the
persona users (WLD-R-02):

1. ``tenant.provision`` as the CLI operator, with admin ``tomas@demo.erev`` (BS1-D-20);
2. each persona accepts its invitation through the accept-invitation command with
   ``EREV_DEMO_PASSWORD``, reading the token from the invitation email in the outbox (WLD-U-R4);
3. a persona who holds a ``requires_mfa`` permission, or whose journey signs off
   (``personas.SIGN_OFF_PERSONAS``), enrols TOTP with ``EREV_DEMO_TOTP_SECRET`` the first time; a
   persona enrolled by an earlier run verifies with it instead (WLD-U-R2). The verified session
   then opens each further workspace of the run and keeps its verification (SAR-09);
4. ``tomas`` invites the other personas with their PRD §2.3 roles for all entities before any of
   them accepts, and rule ``AUTO-BOOTSTRAP`` approves each assignment: setup is incomplete and
   nobody else can approve access yet (04 §14.3 item 3);
5. ``tomas`` creates each custom role a persona needs and ``grace`` approves its ``ROLE_CHANGE``,
   before the personas holding it are invited. ``grace`` is by then a second approver, so the
   bootstrap exception has ended and she approves those personas' assignments as well;
6. the SYSTEM principal records ``demo_seed.complete`` with the generator version and, for a
   tenant seeded with its close, what the close covers.

``with_close`` (``erev seed demo --with-close``; BUILD_SPEC CLO-22) adds the stage
``demo.close_history`` to the tenants that have one: the close of the demo world costs minutes, so
a seed runs it only when asked. The stage stands before the seeded open-period items, which hold
every lock made after them, so a tenant this version seeded without its close cannot receive it
afterwards: asked for it, the seed refuses by name.

Before any write the cast must be valid (emails in ``demo.erev``), and the tenant directory is read
once. A requested tenant whose ``is_demo`` is false, that an earlier run left unfinished, or that
another generator version built is refused; one this version built is skipped with
``seed.tenant_skipped``. Recovery codes issued in the run are merged into
``.run/demo-credentials.txt`` with mode 0600, and no password is written anywhere (DG-RUN-32).
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import select

from erev_api.approvals import engine as approvals
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import Clock
from erev_api.db.session import DbContext, platform_session, set_tenant_context, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    notification,
    tenant,
)
from erev_api.domain.demo import SeedRefused, builders, close_history
from erev_api.domain.demo import personas as demo_personas
from erev_api.domain.demo import sessions as sessions_support
from erev_api.domain.demo import tenants as demo_tenants
from erev_api.domain.demo.personas import CustomRole, Persona
from erev_api.domain.demo.tenants import DemoTenant
from erev_api.domain.platform import me_notifications, provisioning, roles, users
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    NotificationKind,
    TenantKind,
)
from erev_api.files.store import FileStore
from erev_api.logging import get_logger
from erev_api.uow import unit_of_work

GENERATOR_SEED: Final = 20260912  # WLD-R-01
# Raised whenever the seeded content changes (2: RFD-16; 3: CTR-20; 4: the role assignments of a
# persona holding a custom role are approved by the role approver, and the rule sets follow 04
# §16.10 rev 1.104; 5: the pricing basis of the series SSP entries (item DEMO-SSP-BASIS-1, which
# left the version at 4) and the preparer's factor of PRD WLD-U-R2 rev 1.153; 6: BUILD_SPEC CTR-6
# — a request of maya that holds a manual event waits as an event submission with its evidence
# document, and priya's approval appends it;
# 7: item EVT-EVIDENCE-1 — priya's approval of such a request also attaches the evidence document
# to every event it appends, T-PLT-30 subject ``contract_event`` (04 T-CON-24 rev 1.268);
# 8: item ACT-FLAGS-1 — every sample contract states ``acceptance_clause`` and ``side_letter``
# false, on its booking and on T-CON-01 (04 rev 1.287), and the request of each activation
# states the flags of its record and its amount as the item derives them;
# 9: item ENG-COST-READBACK-1 — a ledger line stores the subject of its entry (04
# T-SL-04 ``subject_key``) and the read-back answers it, so the seeded ledgers no longer
# hold the pairs a later computation posted again for a cost asset, a refund-liability
# component and a contract-level loss unit;
# 10: item PRODUCT-POLICY-VALUE-NOT-READ-1 — the draft template ``IND-D05-FRANCHISE-RIGHT`` of
# the consumer-brands workspace (WLD-T-05) states no POL-029 ``upfront_fee.recognition_period``:
# a product or a template states no value of it but the default (04 T-REF-23 rev 1.323), and
# the template held ``CONTRACT_TERM``, which no computation read).
# 11: computation also persists immutable FX layer movements (T-CON-18).
GENERATOR_VERSION: Final = 14
COMPLETE_ACTION: Final = "demo_seed.complete"
TENANT_OBJECT: Final = "tenant"
CREDENTIALS_FILE: Final = "demo-credentials.txt"  # DG-RUN-32, under the run directory
CREDENTIALS_MODE: Final = 0o600
RECOVERY_LINE: Final = "recovery-codes"
CREDENTIALS_HEADER: Final = (
    "# eRev Cloud demo credentials (DG-RUN-32; PRD WLD-U-R2), written by erev seed demo. "
    "Never commit or share this file.",
    f"# {RECOVERY_LINE} <persona email> <the ten single-use recovery codes of the newest batch>",
)
# DG-RUN-32 and DG-MK-seed copy.
PASSWORD_MISSING: Final = "EREV_DEMO_PASSWORD is not set. Copy it from .env.example."
# [J] L1-5-Q-4: the documents give no copy for an unusable TOTP seed.
TOTP_SECRET_INVALID: Final = (
    "EREV_DEMO_TOTP_SECRET must be a base32 secret of at least 80 bits. "
    "make setup adds one when the line is absent."
)
MIN_SECRET_BYTES: Final = 10  # 80 bits, the RFC 4226 minimum
# The route guards of the commands the personas run (04 §15.3 API-R-05, API-R-06).
USER_MANAGE: Final = "user.manage"
ROLE_MANAGE: Final = "role.manage"
_TOKEN_PREFIX: Final = provisioning.INVITATION_LINK.split("{token}", 1)[0]
_LOGGER: Final = "erev_api.domain.demo.seed"

# ``demo_seed.complete``: the member that names what the close stage closed (CLO-22).
CLOSE_MEMBER: Final = "closed"
# DG-MK-seed: the stage cannot be added to a seeded tenant — its open-period items hold every lock.
CLOSE_REFUSED: Final = (
    "Refusing to close {code}: it is seeded without its close, and its open items hold every "
    "lock; run make seed RESET=1 CLOSE=1"
)

Outcome = Literal["seeded", "skipped"]


@dataclass(frozen=True, slots=True, repr=False)
class DemoSecrets:
    password: str
    totp_secret: str

    def __repr__(self) -> str:
        return "DemoSecrets(password=***, totp_secret=***)"


@dataclass(frozen=True, slots=True)
class SeedResult:
    outcomes: tuple[tuple[str, Outcome], ...]  # (tenant code, outcome) in catalogue order
    credentials_path: Path | None  # the credentials file when this run issued recovery codes


@dataclass(frozen=True, slots=True)
class _DirectoryEntry:
    tenant_id: UUID
    is_demo: bool
    generator_version: int | None  # of the tenant's demo_seed.complete event; None without one
    with_close: bool = False  # the event names a close (``CLOSE_MEMBER``)


def checked_totp_secret(value: str) -> str:
    """The base32 seed without spaces or padding, upper-cased; ``SeedRefused`` when unusable."""
    compact = "".join(value.split()).upper().rstrip("=")
    try:
        raw = base64.b32decode(compact + "=" * (-len(compact) % 8))
    except (binascii.Error, ValueError):
        raise SeedRefused(TOTP_SECRET_INVALID) from None
    if len(raw) < MIN_SECRET_BYTES:
        raise SeedRefused(TOTP_SECRET_INVALID)
    return compact


def _directory(
    codes: Sequence[str], *, keyring: KeyRing, request_id: str
) -> dict[str, _DirectoryEntry]:
    """The requested tenants that exist, read in one ``tenant_directory`` transaction together with
    the generator version of each tenant's ``demo_seed.complete`` event. DG-KRN-DB-03 records the
    read as ``PLATFORM_SCOPE_USED``."""
    found: dict[str, _DirectoryEntry] = {}
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=request_id, keyring=keyring
    ) as db:
        rows = db.execute(
            select(tenant.c.id, tenant.c.code, tenant.c.is_demo).where(
                tenant.c.code.in_(sorted(codes))
            )
        ).all()
        for tenant_id, code, is_demo in rows:
            set_tenant_context(db, DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*"))
            after = db.execute(
                select(audit_event.c.after)
                .where(
                    audit_event.c.action == COMPLETE_ACTION, audit_event.c.object_id == tenant_id
                )
                .order_by(audit_event.c.chain_seq.desc())
                .limit(1)
            ).scalar_one_or_none()
            version = after.get("generator_version") if isinstance(after, Mapping) else None
            found[str(code)] = _DirectoryEntry(
                tenant_id=UUID(str(tenant_id)),
                is_demo=bool(is_demo),
                generator_version=version if isinstance(version, int) else None,
                with_close=isinstance(after, Mapping) and bool(after.get(CLOSE_MEMBER)),
            )
    return found


def has_close_stage(demo_tenant: DemoTenant) -> bool:
    """Whether the tenant's builders hold the close stage (WLD-T-01)."""
    return close_history.build in builders.builders_for(demo_tenant.wld_id)


def _refusal(code: str, entry: _DirectoryEntry | None, *, close_asked: bool = False) -> str | None:
    """WLD-R-04 and DG-MK-seed: why an existing tenant may not be seeded, or None. ``close_asked``
    says that the seed was asked for the close and the tenant has that stage."""
    if entry is None:
        return None
    if not entry.is_demo:
        return f"Refusing to seed {code}: is_demo is false"
    # [J] L1-5-Q-3: DG-MK-seed covers only a tenant built by the same generator version.
    if entry.generator_version is None:
        return f"Refusing to seed {code}: an earlier run did not finish; run make seed RESET=1"
    if entry.generator_version != GENERATOR_VERSION:
        return (
            f"Refusing to seed {code}: generator version {entry.generator_version} built it; "
            "run make seed RESET=1"
        )
    if close_asked and not entry.with_close:
        return CLOSE_REFUSED.format(code=code)
    return None


# Lifted into ``demo.sessions`` (lane P7 slice 3b, code-only): the same objects under their
# old names.
_authorize = sessions_support.authorize
_read_only = sessions_support.read_only
_invitation_token = sessions_support.invitation_token
_role_ids = sessions_support.role_ids
_Run = sessions_support.PersonaRun


def _invite(
    run: _Run,
    admin: Persona,
    persona: Persona,
    tenant: DemoTenant,
    tenant_id: UUID,
) -> UUID:
    """``POST /users`` as the admin: the persona with its roles for all entities."""
    return sessions_support.invite(run, admin, persona, tenant.group, tenant_id)


def _open_assigned(run: _Run, persona: Persona, tenant_id: UUID, request_id: UUID) -> None:
    """``POST /me/notifications/{id}/read`` as ``persona`` for its unread ``APPROVAL_ASSIGNED``
    notification of the request: the approver opens the request from the bell before deciding, so
    the seed leaves no unread notification behind (D-84; WEB-17 ``sf-21``)."""
    ctx = run.context(persona, tenant_id)
    with tenant_session(_read_only(tenant_id), read_only=True) as db:
        unread = db.scalars(
            select(notification.c.id)
            .where(
                notification.c.recipient_membership_id == ctx.principal.membership_id,
                notification.c.kind == NotificationKind.APPROVAL_ASSIGNED.value,
                notification.c.subject_type == approvals.OBJECT_TYPE,
                notification.c.subject_id == request_id,
                notification.c.read_at.is_(None),
            )
            .order_by(notification.c.created_at, notification.c.id)
        ).all()
    for notification_id in unread:
        with unit_of_work(ctx, clock=run.clock, keyring=run.keyring, files=run.files) as uow:
            me_notifications.mark_read(uow, UUID(str(notification_id)))
            uow.commit()


def _add_custom_role(
    run: _Run, admin: Persona, approver: Persona, custom: CustomRole, tenant_id: UUID
) -> None:
    """``POST /roles`` as the admin, then the approver approves its ``ROLE_CHANGE`` (BS1-D-20)."""
    ctx = run.context(admin, tenant_id)
    _authorize(ctx, ROLE_MANAGE)
    with unit_of_work(ctx, clock=run.clock, keyring=run.keyring, files=run.files) as uow:
        role_id = roles.create_role(
            uow,
            code=custom.code,
            name=custom.name,
            description=custom.description,
            permissions=list(custom.permissions),
        )
        uow.commit()
    with tenant_session(_read_only(tenant_id), read_only=True) as db:
        request = db.execute(
            select(
                approval_request.c.id,
                approval_request.c.subject_content_sha256,
                approval_request.c.impact_preview_sha256,
            ).where(
                approval_request.c.subject_type == ApprovalSubjectType.ROLE_CHANGE.value,
                approval_request.c.subject_id == role_id,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
            )
        ).one()
    _approve(
        run,
        approver,
        tenant_id,
        UUID(str(request.id)),
        subject_content_sha256=str(request.subject_content_sha256),
        impact_preview_sha256=request.impact_preview_sha256,
    )


def _approve(
    run: _Run,
    approver: Persona,
    tenant_id: UUID,
    request_id: UUID,
    *,
    subject_content_sha256: str,
    impact_preview_sha256: str | None,
) -> None:
    """``POST /approvals/{id}/approve`` as the approver, who opened the request from the bell."""
    _open_assigned(run, approver, tenant_id, request_id)
    approving = run.context(approver, tenant_id)
    with unit_of_work(approving, clock=run.clock, keyring=run.keyring, files=run.files) as uow:
        approvals.decide(
            uow,
            approval_request_id=request_id,
            decision="APPROVE",
            subject_content_sha256=subject_content_sha256,
            impact_preview_sha256=impact_preview_sha256,
            comment=None,
            reason_code=None,
        )
        uow.commit()


def _approve_grants(run: _Run, approver: Persona, tenant_id: UUID, membership_id: UUID) -> None:
    """The approver approves every pending ``ROLE_ASSIGNMENT`` request of the membership. Rule
    ``AUTO-BOOTSTRAP`` approves the admin's grants only while nobody else can approve access (04
    §14.3 item 3): a persona invited once the approver accepted waits for her."""
    with tenant_session(_read_only(tenant_id), read_only=True) as db:
        pending = users.pending_proposals(
            db, {str(membership_id)}, files=run.files, keyring=run.keyring
        )
    for request, _ in pending:
        _approve(
            run,
            approver,
            tenant_id,
            UUID(str(request["id"])),
            subject_content_sha256=str(request["subject_content_sha256"]),
            impact_preview_sha256=request["impact_preview_sha256"],
        )


def _record_complete(
    run: _Run, tenant: DemoTenant, tenant_id: UUID, cast: Sequence[str], *, closed: bool
) -> None:
    """``demo_seed.complete`` by the SYSTEM principal: the generator seed and version, the WLD
    ids of the tenant and its personas and, when the close stage ran, what it closed."""
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id=run.request_id,
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=run.clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=run.clock, keyring=run.keyring, files=run.files) as uow:
        uow.audit(
            action=COMPLETE_ACTION,
            object_type=TENANT_OBJECT,
            object_id=tenant_id,
            after={
                "generator_seed": GENERATOR_SEED,
                "generator_version": GENERATOR_VERSION,
                "wld_id": tenant.wld_id,
                "persona_wld_ids": list(cast),
                **({CLOSE_MEMBER: close_history.closed_scopes()} if closed else {}),
            },
        )
        uow.commit()


def _persona(cast: Sequence[Persona], key: str) -> Persona:
    for persona in cast:
        if persona.key == key:
            return persona
    raise LookupError(f"the tenant's cast has no persona {key}")


def _seed_tenant(
    run: _Run,
    tenant: DemoTenant,
    cast: Sequence[Persona],
    *,
    os_user: str | None,
    with_close: bool = False,
) -> int:
    """Build one tenant through the persona commands; returns its membership count."""
    group = tenant.group
    members = [persona for persona in cast if persona.roles_in(group)]
    admin = _persona(members, demo_personas.ADMIN)
    approver = _persona(members, demo_personas.ROLE_APPROVER)
    provisioned = provisioning.provision_tenant(
        provisioning.TenantProvisionRequest(
            code=tenant.code,
            display_name=tenant.display_name,
            reporting_currency=demo_tenants.REPORTING_CURRENCY,
            is_demo=True,
            admin_email=admin.email,
        ),
        actor=provisioning.OperatorActor(
            channel="CLI", operator_user_id=None, os_user=os_user, request_id=run.request_id
        ),
        clock=run.clock,
        keyring=run.keyring,
    )
    tenant_id = UUID(str(provisioned.tenant["id"]))
    run.join(
        admin,
        tenant_id,
        provisioned.admin_membership_id,
        mfa=demo_personas.needs_mfa(admin, group),
    )
    custom = sorted(
        {code for persona in members for code in persona.roles_in(group)}
        & set(demo_personas.CUSTOM_ROLES)
    )
    invited = [persona for persona in members if persona.key != admin.key]
    first = [persona for persona in invited if not set(persona.roles_in(group)) & set(custom)]
    later = [persona for persona in invited if persona not in first]
    # Every persona without a custom role is invited before any of them accepts — the role
    # approver among them — so the admin is still the only member who can approve access and rule
    # AUTO-BOOTSTRAP approves each grant (04 §14.3 item 3; BS1-D-20).
    memberships = [(persona, _invite(run, admin, persona, tenant, tenant_id)) for persona in first]
    for persona, membership_id in memberships:
        run.join(persona, tenant_id, membership_id, mfa=demo_personas.needs_mfa(persona, group))
    for code in custom:
        _add_custom_role(run, admin, approver, demo_personas.CUSTOM_ROLES[code], tenant_id)
    # A custom role exists once the approver approved it; from then on she approves the admin's
    # grants too, so the personas holding one are no setup grants.
    for persona in later:
        membership_id = _invite(run, admin, persona, tenant, tenant_id)
        _approve_grants(run, approver, tenant_id, membership_id)
        run.join(persona, tenant_id, membership_id, mfa=demo_personas.needs_mfa(persona, group))
    # RFD-16 (XR-09): the content builders registered for the tenant's WLD id; CLO-22: the close
    # stage among them runs for a seed that was asked for it.
    closing = with_close and has_close_stage(tenant)
    builders.run(
        builders.BuildContext(
            tenant_id=tenant_id,
            tenant_code=tenant.code,
            wld_id=tenant.wld_id,
            cast={persona.key: persona for persona in members},
            clock=run.clock,
            keyring=run.keyring,
            files=run.files,
            request_id=run.request_id,
            principal_context=run.context,
            guard=_authorize,
            with_close=closing,
            verify_again=run.step_up,
        )
    )
    _record_complete(
        run, tenant, tenant_id, [persona.wld_id for persona in members], closed=closing
    )
    return len(members)


def read_recovery_codes(path: Path) -> dict[str, list[str]]:
    """The recovery-code lines of an existing credentials file, by persona email."""
    if not path.is_file():
        return {}
    found: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == RECOVERY_LINE:
            found[parts[1]] = parts[2:]
    return found


def write_credentials(
    path: Path, issued: Mapping[str, Sequence[str]], cast: Sequence[Persona]
) -> Path:
    """Merge the recovery codes issued in this run into the credentials file (DG-RUN-32).

    Codes of personas not enrolled in this run are kept, so a partial run never drops earlier codes.
    The file is written beside the target with mode 0600 and then moved over it.
    """
    codes = {
        **read_recovery_codes(path),
        **{email: list(values) for email, values in issued.items()},
    }
    order = {persona.email: index for index, persona in enumerate(cast)}
    emails = sorted(codes, key=lambda email: (order.get(email, len(order)), email))
    lines = [*CREDENTIALS_HEADER, *(f"{RECOVERY_LINE} {e} {' '.join(codes[e])}" for e in emails)]
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.partial")
    descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, CREDENTIALS_MODE)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), CREDENTIALS_MODE)
            handle.write("\n".join(lines) + "\n")
        os.replace(staged, path)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return path


def seed_demo(
    tenant_codes: Sequence[str],
    clock: Clock,
    *,
    keyring: KeyRing,
    files: FileStore,
    secrets: DemoSecrets,
    credentials_path: Path,
    request_id: str,
    os_user: str | None = None,
    personas: Sequence[Persona] | None = None,
    with_close: bool = False,
) -> SeedResult:
    """Seed the demo tenants of ``tenant_codes`` in catalogue order (DG-MK-seed); with
    ``with_close`` the tenants that have the close stage are seeded with it (CLO-22).

    ``SeedRefused`` before any write for an invalid cast, a missing password, an unusable TOTP seed,
    an unknown code, or an existing tenant that may not be seeded — among them one seeded without
    its close that is now asked for it. A ``Problem`` from a command propagates.
    """
    cast = tuple(demo_personas.PERSONAS if personas is None else personas)
    demo_personas.validate_personas(cast)
    if not secrets.password:
        raise SeedRefused(PASSWORD_MISSING)
    checked = DemoSecrets(
        password=secrets.password, totp_secret=checked_totp_secret(secrets.totp_secret)
    )
    selected = demo_tenants.by_codes(tenant_codes)
    directory = _directory(
        [tenant.code for tenant in selected], keyring=keyring, request_id=request_id
    )
    for demo_tenant in selected:
        refusal = _refusal(
            demo_tenant.code,
            directory.get(demo_tenant.code),
            close_asked=with_close and has_close_stage(demo_tenant),
        )
        if refusal is not None:
            raise SeedRefused(refusal)
    logger = get_logger(_LOGGER)
    run = _Run(
        clock=clock,
        keyring=keyring,
        files=files,
        secrets=sessions_support.SeedSecrets(
            password=checked.password, totp_secret=checked.totp_secret
        ),
        request_id=request_id,
    )
    outcomes: list[tuple[str, Outcome]] = []
    written: Path | None = None
    try:
        for demo_tenant in selected:
            if demo_tenant.code in directory:
                logger.info("seed.tenant_skipped", tenant_code=demo_tenant.code)
                outcomes.append((demo_tenant.code, "skipped"))
                continue
            count = _seed_tenant(run, demo_tenant, cast, os_user=os_user, with_close=with_close)
            logger.info("seed.tenant_seeded", tenant_code=demo_tenant.code, membership_count=count)
            outcomes.append((demo_tenant.code, "seeded"))
    finally:
        # Issued codes are committed, so they reach the file even when a later step fails.
        if run.recovery_codes:
            written = write_credentials(credentials_path, run.recovery_codes, cast)
        run.sign_out_all()
    return SeedResult(outcomes=tuple(outcomes), credentials_path=written)
