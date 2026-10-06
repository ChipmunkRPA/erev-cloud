"""Sandbox reset by supersession (BUILD_SPEC SNP-3; 05 §10 SBX-07 rev 1.64; 04 API-R-04 and §16.14
rev 1.125; 03 REQ-PLT-024, REQ-PLT-025; PRD ACT-51, ERR-25, J-25.3, J-25-AC-1).

A reset deletes nothing: it creates a successor sandbox and archives the one it supersedes.

* :func:`request_reset` is ``POST /tenant/reset``. In a production tenant it answers 409
  ``production-reset-forbidden`` before anything else is asked of a caller who holds
  ``sandbox.reset``; in a sandbox it needs a fresh TOTP step-up, a user principal and a reason of
  at least ten characters. Mode ``SNAPSHOT`` goes back to the sandbox's SEED snapshot, the one its
  own ``tenant.snapshot_loaded`` names: the server resolves it, and a caller that names a snapshot
  must name that one. It defers ``SANDBOX_RESET`` in the sandbox, with the successor tenant
  pre-allocated, and refuses a second reset while one is queued or running.
* :func:`reset_sandbox` is the job. (a) The successor: mode ``SNAPSHOT`` is the SBX-04 load of the
  seed, driven through a job context of the SOURCE tenant as every load is; mode ``EMPTY`` is
  :func:`create_empty_sandbox`. (b) The old sandbox is set ``ARCHIVED`` in its own context, with
  ``tenant.sandbox_reset`` there and in the successor. (c) The requester's live sessions in the
  old sandbox move to the successor. Each step is its own transaction in one tenant context
  (TXN-08); the successor is complete before the old sandbox is archived.
* :func:`reset_failed` is the job's failure hook: a successor whose load failed is archived
  (05 SBX-04 rev 1.64); the old sandbox stays as it was.

Writes outside the two sandboxes are the source tenant's own provenance records of a sandbox
derived from it (05 SBX-02): what every load writes there (the snapshot row's
``target_tenant_id``, the completion event, the requester's notification) or, for an empty
successor, one ``tenant.sandbox_created`` event. ``scenario.scenario_tenant_id`` is repointed in
step (b) once T-FC-01 exists (FCS).

This module never imports a handler module: collecting the route registers no job kind
(DG-ARC-08). The handler is ``sandbox_reset_job``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import sqlalchemy as sa

from erev_api.db import new_id
from erev_api.domain.platform import jobs, sandboxes, snapshots
from erev_api.domain.platform.snapshot_dataset import EMPTY_SANDBOX_PURPOSE
from erev_api.enums import JobKind, JobState, PrincipalKind, TenantKind, TenantStatus
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "ACTION_CREATED",
    "ACTION_RESET",
    "ACTION_RESET_REQUESTED",
    "MODE_EMPTY",
    "MODE_SNAPSHOT",
    "PRODUCTION_RESET",
    "RESET_RUNNING",
    "ResetOutcome",
    "ResetParams",
    "create_empty_sandbox",
    "parse_reset",
    "request_reset",
    "reset_failed",
    "reset_params_of",
    "reset_sandbox",
    "successor_code",
]

MODE_SNAPSHOT: Final = "SNAPSHOT"
MODE_EMPTY: Final = EMPTY_SANDBOX_PURPOSE  # "EMPTY"
MODES: Final = (MODE_SNAPSHOT, MODE_EMPTY)
# 04 §16.14 rev 1.125.
ACTION_RESET_REQUESTED: Final = "tenant.sandbox_reset_requested"
ACTION_RESET: Final = "tenant.sandbox_reset"
ACTION_CREATED: Final = "tenant.sandbox_created"
OBJECT_TYPE: Final = "tenant"
# PRD ERR-25 (J-25-AC-1).
PRODUCTION_RESET: Final = (
    "Production workspaces cannot be reset or restored. Create a sandbox copy instead."
)
RESET_RUNNING: Final = "A reset of this sandbox is already queued or running."
NOT_ACTIVE: Final = "This sandbox is no longer active; it has been superseded or archived."
RULE_REASON: Final = "BR-PLT-08"
REASON_LENGTH: Final = range(10, 2001)
REASON_SHORT: Final = "Enter at least 10 characters."
REASON_LONG: Final = "Enter at most 2,000 characters."
SEED_REQUIRED: Final = (
    "A sandbox resets to its seed snapshot, the one it was copied from (REQ-PLT-025)."
)
NO_SEED: Final = (
    "This sandbox was created empty and has no seed snapshot; it can be reset to an empty "
    "workspace."
)
EMPTY_NAMES_NONE: Final = "A reset to an empty workspace names no snapshot."
_CODE_MAX: Final = 40  # provisioning.TENANT_CODE_LENGTH
_SUCCESSOR_SUFFIX: Final = re.compile(r"-r[0-9a-f]{6}$")


@dataclass(frozen=True, slots=True)
class ResetParams:
    """The ``SANDBOX_RESET`` job params (04 §16.14): the mode, the seed snapshot for mode
    ``SNAPSHOT``, the reason, and the successor as a load block — its pre-allocated tenant id,
    the display name and code it takes and the requesting user."""

    mode: str
    tenant_snapshot_id: UUID | None
    reason: str
    successor: sandboxes.LoadParams


@dataclass(frozen=True, slots=True)
class ResetOutcome:
    sandbox_tenant_id: UUID
    archived_tenant_id: UUID
    sessions_moved: int
    loaded: sandboxes.Loaded | None  # None for mode EMPTY


def successor_code(code: str, sandbox_tenant_id: UUID) -> str:
    """The code of a reset's successor: the superseded sandbox's code (without the suffix an
    earlier reset gave it) and ``-r`` plus the last six hex digits of the successor's id, cut to
    the T-PLT-01 code length. Derived, so no read of other tenants' codes is needed; a collision
    on ``ux_tenant__code`` is refused ``SANDBOX_NAME_TAKEN`` like any other."""
    suffix = f"-r{sandbox_tenant_id.hex[-6:]}"
    base = _SUCCESSOR_SUFFIX.sub("", code)[: _CODE_MAX - len(suffix)].rstrip("-")
    return base + suffix


def _invalid(field: str, rule_id: str, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def reset_params_of(
    *,
    mode: str,
    tenant_snapshot_id: UUID | None,
    reason: str,
    sandbox_tenant_id: UUID,
    name: str,
    code: str,
    requested_by: UUID,
) -> dict[str, Any]:
    """The params the request writes; the successor block is a load block under ``sandbox``."""
    return {
        "mode": mode,
        "tenant_snapshot_id": None if tenant_snapshot_id is None else str(tenant_snapshot_id),
        "reason": reason,
        **sandboxes.load_params_of(
            sandbox_tenant_id=sandbox_tenant_id,
            name=name,
            requested_by=requested_by,
            restore=False,
            code=code,
        ),
    }


def parse_reset(params: Mapping[str, Any]) -> ResetParams:
    """The job params, or 422 ``validation-failed`` by member."""
    mode = params.get("mode")
    errors: list[ProblemError] = []
    if mode not in MODES:
        errors.append(_invalid("mode", "PARAMS_INVALID", "SNAPSHOT or EMPTY."))
    raw = params.get("tenant_snapshot_id")
    snapshot_id: UUID | None = None
    if raw is not None:
        try:
            snapshot_id = raw if isinstance(raw, UUID) else UUID(str(raw))
        except (TypeError, ValueError):
            errors.append(_invalid("tenant_snapshot_id", "PARAMS_INVALID", "a uuid is required."))
    if mode == MODE_SNAPSHOT and raw is None:
        errors.append(_invalid("tenant_snapshot_id", sandboxes.RULE_SEED, SEED_REQUIRED))
    reason = params.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(_invalid("reason", RULE_REASON, REASON_SHORT))
    if errors:
        raise Problem("validation-failed", errors=errors)
    successor = sandboxes.parse_load(params)
    if successor is None or successor.requested_by is None or successor.code is None:
        raise Problem(
            "validation-failed",
            errors=[_invalid("sandbox", "PARAMS_INVALID", "the successor block is required.")],
        )
    return ResetParams(str(mode), snapshot_id, str(reason), successor)


def _sandbox_row(session: Session, tenant_id: UUID, *, lock: bool = False) -> Mapping[str, Any]:
    from erev_api.db.tables import tenant

    statement = sa.select(
        tenant.c.id,
        tenant.c.code,
        tenant.c.kind,
        tenant.c.status,
        tenant.c.display_name,
        tenant.c.reporting_currency,
        tenant.c.source_tenant_id,
        tenant.c.source_known_at,
        tenant.c.created_at,
    ).where(tenant.c.id == tenant_id)
    if lock:
        statement = statement.with_for_update()
    return dict(session.execute(statement).mappings().one())


def request_reset(
    uow: UnitOfWork, *, mode: str, tenant_snapshot_id: UUID | None, reason: str
) -> tuple[UUID, JobOut]:
    """``POST /tenant/reset`` (module docstring): the pre-allocated successor tenant id and the
    API-S-Job of the deferred ``SANDBOX_RESET`` job."""
    from erev_api.db.tables import job

    principal = uow.principal
    # the row lock serialises two requests for one sandbox: the second sees the first's job
    current = _sandbox_row(uow.session, principal.tenant_id, lock=True)
    if str(current["kind"]) != TenantKind.SANDBOX.value:
        raise Problem("production-reset-forbidden", PRODUCTION_RESET)
    snapshots.require_fresh_step_up(principal.mfa_verified_at, uow.now)
    if principal.kind is not PrincipalKind.USER or principal.id is None:
        raise sandboxes.actor_required()
    errors: list[ProblemError] = []
    text = reason.strip()
    if len(text) < REASON_LENGTH.start:
        errors.append(_invalid("reason", RULE_REASON, REASON_SHORT))
    elif len(text) >= REASON_LENGTH.stop:
        errors.append(_invalid("reason", RULE_REASON, REASON_LONG))
    seed_id = tenant_snapshot_id
    if mode == MODE_SNAPSHOT:
        # the seed is the sandbox's own fact: a caller may name it, and then it must be the seed
        seed = sandboxes.sandbox_load_of(uow.session, current)
        if seed is None:
            errors.append(_invalid("tenant_snapshot_id", sandboxes.RULE_SEED, NO_SEED))
        elif tenant_snapshot_id is not None and tenant_snapshot_id != seed["tenant_snapshot_id"]:
            errors.append(_invalid("tenant_snapshot_id", sandboxes.RULE_SEED, SEED_REQUIRED))
        else:
            seed_id = UUID(str(seed["tenant_snapshot_id"]))
    elif tenant_snapshot_id is not None:
        errors.append(_invalid("tenant_snapshot_id", sandboxes.RULE_SEED, EMPTY_NAMES_NONE))
    if errors:
        raise Problem("validation-failed", errors=errors)
    running = uow.session.execute(
        sa.select(job.c.id)
        .where(
            job.c.kind == JobKind.SANDBOX_RESET.value,
            job.c.state.in_([JobState.QUEUED.value, JobState.RUNNING.value]),
        )
        .limit(1)
    ).first()
    if running is not None:
        raise Problem("invalid-transition", RESET_RUNNING)
    successor_id = new_id()
    params = reset_params_of(
        mode=mode,
        tenant_snapshot_id=seed_id,
        reason=text,
        sandbox_tenant_id=successor_id,
        name=str(current["display_name"]),
        code=successor_code(str(current["code"]), successor_id),
        requested_by=principal.id,
    )
    deferred = uow.defer(
        JobKind.SANDBOX_RESET,
        params,
        subject_type=snapshots.JOB_SUBJECT_TYPE,
        subject_id=successor_id,
    )
    job_id = UUID(str(deferred["id"]))
    uow.audit(
        action=ACTION_RESET_REQUESTED,
        object_type=OBJECT_TYPE,
        object_id=principal.tenant_id,
        before=None,
        after=None,
        detail={
            "mode": mode,
            "tenant_snapshot_id": None if seed_id is None else str(seed_id),
            "sandbox_tenant_id": str(successor_id),
            "reason": text,
            "job_id": str(job_id),
        },
    )
    return successor_id, jobs.job_out_of(uow.session, job_id)


# --- the job --------------------------------------------------------------------------------------


def _system_actor(request_id: str, *, on_behalf_of: UUID | None) -> Any:
    from erev_api.audit.writer import AuditActor

    return AuditActor(
        kind=PrincipalKind.SYSTEM,
        id=None,
        roles=(),
        auth_method=None,
        mfa_verified=None,
        on_behalf_of_id=on_behalf_of,
        api_client_id=None,
        support_grant_id=None,
        source_ip=None,
        request_id=request_id,
    )


def create_empty_sandbox(
    runtime: Any,
    *,
    source_tenant_id: UUID,
    sandbox_tenant_id: UUID,
    name: str,
    code: str,
    reporting_currency: str,
    requested_by: UUID,
    request_id: str,
    now: datetime,
    enlist: Callable[[Session], None],
) -> UUID:
    """An EMPTY sandbox of ``source_tenant_id`` (05 SBX-02, SBX-07 rev 1.64; the step list of
    ``snapshot_dataset.empty_sandbox_plan``): in ONE provisioning-scope transaction the ``tenant``
    row (``kind = 'sandbox'``, no ``source_known_at``, ``ACTIVE`` — nothing is loaded, so nothing is
    half-done), its audit key, the 04 §14.3 seed exactly as ``tenant.provision`` writes it
    (``provisioning.seed_workspace``), the requester's membership ``ACTIVE`` at once with the
    ``tenant_admin`` grant rule ``AUTO-BOOTSTRAP`` approves — no invitation: the requester is a
    signed-in user — the chain head, and the audit events, ``tenant.sandbox_created`` first. The
    grant is the seed's own pair, stamped by this job's SYSTEM principal, so the requester is
    the sandbox's bootstrap Tenant Admin and can staff it (SBX-07 rev 1.181;
    ``routing.is_bootstrap_admin``). The membership's notification preferences follow in the
    sandbox's own context (§14.3 item 4). Returns the membership id. A code collision is
    ``SANDBOX_NAME_TAKEN``. ``enlist`` is the door of the reset's job (``JobContext.enlist``;
    05 JOB-06 rev 1.200): the provisioning transaction is one of that job's and passes it
    first."""
    from sqlalchemy.exc import IntegrityError

    from erev_api.audit.chain import append_events
    from erev_api.audit.writer import build_event
    from erev_api.auth.keyring import ProvisioningReadbackError
    from erev_api.auth.principal import system_principal
    from erev_api.db.session import (
        DbContext,
        name_platform_tenant,
        platform_session,
        set_tenant_context,
    )
    from erev_api.db.tables import audit_chain_head, tenant, tenant_membership
    from erev_api.domain.platform import memberships, provisioning
    from erev_api.enums import MembershipStatus
    from erev_api.jobs.context import system_unit_of_work

    keyring = runtime.keyring
    if keyring is None:
        raise RuntimeError("the job runtime has no key ring")
    membership_id = new_id()
    stamp = {
        "created_at": now,
        "created_by": None,
        "created_by_kind": PrincipalKind.SYSTEM.value,
        "updated_at": now,
        "updated_by": None,
        "updated_by_kind": PrincipalKind.SYSTEM.value,
    }
    actor = _system_actor(request_id, on_behalf_of=requested_by)
    try:
        with platform_session(
            "provisioning", actor_user_id=requested_by, request_id=request_id, keyring=keyring
        ) as session:
            enlist(session)
            audit_key_id = keyring.new_tenant_audit_key_id(sandbox_tenant_id)
            session.execute(
                sa.insert(tenant).values(
                    id=sandbox_tenant_id,
                    code=code,
                    kind=TenantKind.SANDBOX.value,
                    status=TenantStatus.ACTIVE.value,
                    display_name=name[:400],
                    reporting_currency=reporting_currency,
                    is_demo=False,
                    audit_hmac_key_id=audit_key_id,
                    source_tenant_id=source_tenant_id,
                    source_known_at=None,
                    setup_completed_at=None,
                    **stamp,
                )
            )
            provisioned = sandboxes.provision_audit_key(runtime, keyring, sandbox_tenant_id)
            if provisioned != audit_key_id:
                raise ProvisioningReadbackError(provisioned)
            name_platform_tenant(session, sandbox_tenant_id)
            set_tenant_context(
                session, DbContext(tenant_id=sandbox_tenant_id, user_id=None, entity_scope="*")
            )
            session.execute(
                sa.insert(tenant_membership).values(
                    tenant_id=sandbox_tenant_id,
                    id=membership_id,
                    user_id=requested_by,
                    status=MembershipStatus.ACTIVE.value,
                    invited_at=now,
                    activated_at=now,
                    **stamp,
                )
            )
            seeded = provisioning.seed_workspace(
                session,
                tenant_id=sandbox_tenant_id,
                reporting_currency=reporting_currency,
                stamp=stamp,
                published_by=None,
                now=now,
            )
            grant_events = provisioning.grant_bootstrap_admin(
                session,
                tenant_id=sandbox_tenant_id,
                membership_id=membership_id,
                role_id=seeded.admin_role_id,
                grantor=provisioning.SeedActor(
                    created_by=None,
                    created_by_kind=PrincipalKind.SYSTEM,
                    audit=actor,
                    source_channel=PrincipalKind.SYSTEM.value,
                ),
                now=now,
            )
            session.execute(
                sa.insert(audit_chain_head).values(
                    tenant_id=sandbox_tenant_id, last_chain_seq=0, updated_at=now
                )
            )
            created = build_event(
                tenant_id=sandbox_tenant_id,
                actor=actor,
                occurred_at=now,
                action=ACTION_CREATED,
                object_type=OBJECT_TYPE,
                object_id=sandbox_tenant_id,
                after={
                    "code": code,
                    "display_name": name[:400],
                    "kind": TenantKind.SANDBOX.value,
                    "reporting_currency": reporting_currency,
                    "status": TenantStatus.ACTIVE.value,
                },
                detail={
                    "source_tenant_id": str(source_tenant_id),
                    "requested_by": str(requested_by),
                    "purpose": MODE_EMPTY,
                },
            )
            append_events(
                session,
                tenant_id=sandbox_tenant_id,
                keyring=keyring,
                events=[
                    created,
                    *provisioning.registry_seed_events(
                        seeded.registry_defaults, request_id=request_id, now=now
                    ),
                    *grant_events,
                ],
            )
    except IntegrityError as error:
        if provisioning.TENANT_CODE_INDEX in str(error.orig):
            raise sandboxes.sandbox_name_taken(code) from None
        raise
    with system_unit_of_work(
        runtime, system_principal(sandbox_tenant_id), request_id=f"{request_id}-preferences"
    ) as uow:
        memberships.on_membership_activated(uow, membership_id)
        uow.commit()
    return membership_id


def _source_context(jc: JobContext, source_tenant_id: UUID) -> JobContext:
    """The job's context FOR THE SOURCE TENANT: the loader reads the snapshot and writes the
    source's provenance records as the source's SYSTEM principal, as in every load (05 SBX-04);
    the job row itself lives in the sandbox, so this context persists no progress."""
    from erev_api.auth.principal import system_principal
    from erev_api.jobs.context import JobContext as Context

    return Context(
        job_id=jc.job_id,
        tenant_id=source_tenant_id,
        kind=jc.kind,
        principal=system_principal(source_tenant_id),
        runtime=jc.runtime,
        clock=jc.clock,
        persisted=False,
    )


def reset_sandbox(
    jc: JobContext, params: ResetParams, *, heartbeat: Callable[[], None] | None = None
) -> ResetOutcome:
    """The ``SANDBOX_RESET`` job in the sandbox it supersedes (module docstring)."""
    from erev_api.auth import sessions
    from erev_api.auth.principal import system_principal
    from erev_api.db.tables import tenant
    from erev_api.jobs.context import system_unit_of_work

    beat = heartbeat or (lambda: None)
    runtime = jc.runtime
    keyring = runtime.keyring
    if keyring is None:
        raise RuntimeError("the job runtime has no key ring")
    old_id: UUID = jc.tenant_id
    successor = params.successor
    requester = successor.requested_by
    if requester is None or successor.code is None:
        raise sandboxes.actor_required()
    successor_id = successor.sandbox_tenant_id

    # authorise: the sandbox is still the one the request saw; 05 §5.6 lock of the source's copies
    with jc.unit_of_work() as uow:
        current = _sandbox_row(uow.session, old_id, lock=True)
        if str(current["kind"]) != TenantKind.SANDBOX.value:
            raise Problem("production-reset-forbidden", PRODUCTION_RESET)
        if str(current["status"]) != TenantStatus.ACTIVE.value:
            raise Problem("invalid-transition", NOT_ACTIVE)
        source_id = UUID(str(current["source_tenant_id"]))
        uow.session.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"tenant-copy:{source_id}"},
        )
        if params.mode == MODE_SNAPSHOT:
            seed = sandboxes.sandbox_load_of(uow.session, current)
            if seed is None or params.tenant_snapshot_id != seed["tenant_snapshot_id"]:
                raise Problem(
                    "validation-failed",
                    errors=[_invalid("tenant_snapshot_id", sandboxes.RULE_SEED, SEED_REQUIRED)],
                )
    beat()

    # (a) the successor
    loaded: sandboxes.Loaded | None = None
    if params.mode == MODE_SNAPSHOT:
        assert params.tenant_snapshot_id is not None
        loaded = sandboxes.load_sandbox(
            _source_context(jc, source_id),
            snapshot_id=params.tenant_snapshot_id,
            load=sandboxes.LoadParams(
                sandbox_tenant_id=successor_id,
                name=successor.name,
                requested_by=requester,
                restore=True,
                code=successor.code,
            ),
            heartbeat=beat,
        )
    else:
        create_empty_sandbox(
            runtime,
            source_tenant_id=source_id,
            sandbox_tenant_id=successor_id,
            name=successor.name,
            code=successor.code,
            reporting_currency=str(current["reporting_currency"]),
            requested_by=requester,
            request_id=f"job-{jc.job_id}-provision",
            now=jc.clock.now(),
            enlist=jc.enlist,
        )
        # the source's provenance record of a sandbox derived from it (05 SBX-02)
        with _source_context(jc, source_id).unit_of_work() as uow:
            uow.audit(
                action=ACTION_CREATED,
                object_type=OBJECT_TYPE,
                object_id=successor_id,
                before=None,
                after={"sandbox_tenant_id": str(successor_id)},
                detail={
                    "sandbox_tenant_id": str(successor_id),
                    "superseded_tenant_id": str(old_id),
                    "requested_by": str(requester),
                    "purpose": MODE_EMPTY,
                },
            )
            uow.commit()
    beat()

    snapshot_text = None if params.tenant_snapshot_id is None else str(params.tenant_snapshot_id)
    # (b) the old sandbox is archived in its own context ...
    with jc.unit_of_work() as uow:
        archived = uow.session.execute(
            sa.update(tenant)
            .where(tenant.c.id == old_id, tenant.c.status == TenantStatus.ACTIVE.value)
            .values(
                status=TenantStatus.ARCHIVED.value,
                updated_at=uow.now,
                updated_by=None,
                updated_by_kind=PrincipalKind.SYSTEM.value,
            )
            .returning(tenant.c.id)
        ).first()
        if archived is None:
            raise Problem("invalid-transition", NOT_ACTIVE)
        uow.audit(
            action=ACTION_RESET,
            object_type=OBJECT_TYPE,
            object_id=old_id,
            before={"status": TenantStatus.ACTIVE.value},
            after={"status": TenantStatus.ARCHIVED.value},
            detail={
                "mode": params.mode,
                "tenant_snapshot_id": snapshot_text,
                "successor_tenant_id": str(successor_id),
                "reason": params.reason,
            },
        )
        uow.commit()
    # ... and the successor records what it supersedes
    with system_unit_of_work(
        runtime, system_principal(successor_id), request_id=f"job-{jc.job_id}-reset"
    ) as uow:
        uow.audit(
            action=ACTION_RESET,
            object_type=OBJECT_TYPE,
            object_id=successor_id,
            before=None,
            after={"status": TenantStatus.ACTIVE.value},
            detail={
                "mode": params.mode,
                "tenant_snapshot_id": snapshot_text,
                "superseded_tenant_id": str(old_id),
                "reason": params.reason,
            },
        )
        uow.commit()
    beat()

    # (c) the requester's live sessions in the old sandbox continue in the successor
    moved = sessions.move_sessions(
        user_id=requester,
        from_tenant_id=old_id,
        to_tenant_id=successor_id,
        facts=sessions.RequestFacts(
            request_id=f"job-{jc.job_id}-sessions",
            source_ip=None,
            user_agent=None,
            now=jc.clock.now(),
        ),
        keyring=keyring,
    )
    return ResetOutcome(successor_id, old_id, moved, loaded)


def reset_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The ``SANDBOX_RESET`` failure hook: once the job's end is committed, a successor whose load
    left it ``SUSPENDED`` is archived (05 SBX-04 rev 1.64). The sandbox the reset was to supersede
    is untouched unless step (b) had already archived it — then the successor is complete and
    ``ACTIVE``, and nothing is undone."""
    from erev_api.jobs.context import JobRuntime

    try:
        load = sandboxes.parse_load(params)
    except Problem:
        return
    if load is None:
        return
    runtime = JobRuntime(clock=uow.clock, keyring=uow.keyring, files=uow.files)
    request_id = f"{uow.ctx.request_id}-load-failed"
    successor_id = load.sandbox_tenant_id
    failure = dict(problem)

    def archive() -> None:
        sandboxes.archive_failed_load(runtime, successor_id, failure, request_id=request_id)

    uow.after_commit(archive)
