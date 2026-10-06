"""Tenant snapshot requests and reads (API-R-04 ``POST`` / ``GET /tenant/snapshots``; 04 T-PLT-34;
05 §10 SBX-02, SBX-06; PRD ACT-50; BUILD_SPEC SNP-1 slice I-4; lane record §13.2.10).

The command side generates the T-PLT-34 id, defers the ``TENANT_SNAPSHOT`` job with the handler's
params, inserts the row ``QUEUED`` with its ``job_id`` (not an updatable column under DB-03, so it
is set at insert) and writes the AUD-CMD event ``tenant.snapshot_requested``. Refusals by name:
``mfa-step-up-required`` (BR-PLT-06: a TOTP verification older than the window),
``validation-failed`` (a ``known_at`` later than now, a purpose outside the T-PLT-34 check, a
sandbox name longer than a label), ``sandbox-restricted`` (SBX-02: only a production tenant is a
snapshot source). The read side serves the row, the list statement and the stored manifest bytes.
This module never imports the handler module: collecting the route registers no job kind
(DG-ARC-08; record §13.1.1).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Select, insert, select
from sqlalchemy.orm import Session

from erev_api.auth import mfa
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import tenant, tenant_snapshot
from erev_api.domain.platform import actors, jobs, sandboxes
from erev_api.domain.platform.snapshot_dataset import PURPOSES
from erev_api.enums import JobKind, PrincipalKind, RunStatus, TenantKind
from erev_api.files.store import FileStore, open_file
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut
from erev_api.schemas.users import LABEL_LENGTH
from erev_api.uow import UnitOfWork

__all__ = [
    "ACTION_REQUESTED",
    "KNOWN_AT_FUTURE",
    "NOT_PRODUCTION",
    "NO_MANIFEST",
    "JOB_SUBJECT_TYPE",
    "OBJECT_TYPE",
    "SANDBOX_PURPOSES",
    "SNAPSHOT_ID_HEADER",
    "request_sandbox",
    "SnapshotRequest",
    "check_request",
    "get_snapshot",
    "job_params",
    "list_snapshots",
    "manifest_content",
    "request_snapshot",
    "require_fresh_step_up",
]

OBJECT_TYPE: Final = "tenant_snapshot"  # audit object type (AUD-CMD); not a T-PLT-13 job subject
# T-PLT-13 `ck_job__subject_type` admits a fixed list; the snapshot job works on the source tenant
# (04 T-PLT-34 job_id, rev 1.56). The row names the job; the job's params name the row.
JOB_SUBJECT_TYPE: Final = "tenant"
ACTION_REQUESTED: Final = "tenant.snapshot_requested"  # AUD-CMD; SBX-06 names the job's events
SNAPSHOT_ID_HEADER: Final = "X-Erev-Tenant-Snapshot-Id"  # 04 §16.14 precedent for a 202 job
# Purposes whose job exports AND then loads a sandbox in the same job (SNP-2; 04 rev 1.67).
SANDBOX_PURPOSES: Final = frozenset({"SANDBOX_COPY", "SANDBOX_SEED"})
RULE_ID: Final = "SNP-1"
KNOWN_AT_FUTURE: Final = (
    "known_at is later than now; a snapshot is taken as of a present or past instant."
)
NOT_PRODUCTION: Final = (
    "Snapshots copy a production tenant; a sandbox is not a snapshot source (05 SBX-02)."
)
NO_MANIFEST: Final = "The snapshot has no manifest yet."
# The ``actors.named`` value a row is read with, for ``snapshot_out`` alone (dev-guide DG-API-11).
_CREATED_BY_NAMED: Final = "created_by__named"
_LIST_COLUMNS: Final = (
    *tenant_snapshot.c,
    actors.named(tenant_snapshot.c.created_by, tenant_id=tenant_snapshot.c.tenant_id).label(
        _CREATED_BY_NAMED
    ),
)
_READ_ONLY: Final = frozenset({"created_by_kind", _CREATED_BY_NAMED})


@dataclass(frozen=True, slots=True)
class SnapshotRequest:
    """A request that passed every pure check; ``known_at`` is UTC."""

    known_at: datetime
    purpose: str
    sandbox_name: str | None  # SNP-2 reads it for SANDBOX_COPY; T-PLT-34 stores no name


def _invalid(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed", errors=[ProblemError(field=field, rule_id=RULE_ID, message=message)]
    )


def check_request(
    *,
    kind: TenantKind,
    known_at: datetime,
    purpose: str,
    now: datetime,
    sandbox_name: str | None = None,
) -> SnapshotRequest:
    """The pure refusals of ``POST /tenant/snapshots``, each by name."""
    if kind is not TenantKind.PRODUCTION:
        raise Problem("sandbox-restricted", NOT_PRODUCTION)
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise _invalid("known_at", "known_at must carry a UTC offset (API-C-07).")
    if known_at > now:
        raise _invalid("known_at", KNOWN_AT_FUTURE)
    if purpose not in PURPOSES:
        raise _invalid("purpose", f"purpose must be one of {', '.join(sorted(PURPOSES))}.")
    if sandbox_name is not None and len(sandbox_name) > LABEL_LENGTH:
        raise _invalid("name", f"name is at most {LABEL_LENGTH} characters.")
    if purpose in SANDBOX_PURPOSES and (sandbox_name is None or not sandbox_name.strip()):
        raise _invalid("name", "a sandbox copy or seed names the sandbox it creates (SNP-2).")
    return SnapshotRequest(known_at.astimezone(UTC), purpose, sandbox_name)


def require_fresh_step_up(verified_at: datetime | None, now: datetime) -> None:
    """PRD ACT-50 / BR-PLT-06: requesting a snapshot needs a TOTP verification inside the step-up
    window; an older or absent one gives 403 ``mfa-step-up-required`` (the approvals precedent)."""
    if not mfa.step_up_fresh_at(verified_at, now):
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)


def job_params(
    snapshot_id: UUID, known_at: datetime, purpose: str, sandbox_name: str | None
) -> dict[str, Any]:
    """The ``TENANT_SNAPSHOT`` params the handler parses (``tenant_snapshot_id``, RFC 3339
    ``known_at`` with offset, ``purpose``); ``sandbox_name`` travels only when given."""
    params: dict[str, Any] = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.astimezone(UTC).isoformat(),
        "purpose": purpose,
    }
    if sandbox_name is not None:
        params["sandbox_name"] = sandbox_name
    return params


def _source_kind(session: Session, tenant_id: UUID) -> TenantKind:
    kind = session.execute(select(tenant.c.kind).where(tenant.c.id == tenant_id)).scalar_one()
    return TenantKind(str(kind))


def request_snapshot(
    uow: UnitOfWork, *, known_at: datetime, purpose: str, sandbox_name: str | None = None
) -> tuple[Mapping[str, Any], JobOut]:
    """``POST /tenant/snapshots``: the QUEUED T-PLT-34 row and the API-S-Job of its deferred
    ``TENANT_SNAPSHOT`` job (dispatched after commit, DG-KRN-JOB-02)."""
    principal = uow.principal
    require_fresh_step_up(principal.mfa_verified_at, uow.now)
    request = check_request(
        kind=_source_kind(uow.session, principal.tenant_id),
        known_at=known_at,
        purpose=purpose,
        now=uow.now,
        sandbox_name=sandbox_name,
    )
    snapshot_id = new_id()
    params = job_params(snapshot_id, request.known_at, request.purpose, request.sandbox_name)
    sandbox_tenant_id: UUID | None = None
    if request.purpose in SANDBOX_PURPOSES:
        # SNP-2 (04 rev 1.67): the job exports and then loads a sandbox whose tenant id is
        # pre-allocated here; only a user principal can hold the membership that makes the target
        # visible (rev 1.56) — SYSTEM / operator requests are refused before any write.
        if principal.kind is not PrincipalKind.USER or principal.id is None:
            raise sandboxes.actor_required()
        sandbox_tenant_id = new_id()
        params.update(
            sandboxes.load_params_of(
                sandbox_tenant_id=sandbox_tenant_id,
                name=request.sandbox_name or "",
                requested_by=principal.id,
                restore=False,
            )
        )
    job = uow.defer(
        JobKind.TENANT_SNAPSHOT,
        params,
        subject_type=JOB_SUBJECT_TYPE,
        subject_id=sandbox_tenant_id if sandbox_tenant_id is not None else principal.tenant_id,
    )
    job_id = UUID(str(job["id"]))
    row = (
        uow.session.execute(
            insert(tenant_snapshot)
            .values(
                tenant_id=principal.tenant_id,
                id=snapshot_id,
                known_at=request.known_at,
                purpose=request.purpose,
                status=RunStatus.QUEUED.value,
                job_id=job_id,
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
            )
            .returning(*tenant_snapshot.c)
        )
        .mappings()
        .one()
    )
    uow.audit(
        action=ACTION_REQUESTED,
        object_type=OBJECT_TYPE,
        object_id=snapshot_id,
        before=None,
        after={"status": RunStatus.QUEUED.value},
        detail={
            "known_at": request.known_at.isoformat(),
            "purpose": request.purpose,
            "job_id": str(job_id),
            **(
                {"sandbox_tenant_id": str(sandbox_tenant_id)}
                if sandbox_tenant_id is not None
                else {}
            ),
        },
    )
    return dict(row), jobs.job_out_of(uow.session, job_id)


def request_sandbox(uow: UnitOfWork, *, tenant_snapshot_id: UUID, name: str) -> tuple[UUID, JobOut]:
    """``POST /tenant/sandboxes`` (API-R-04 rev 1.67; SNP-2; D-98 candidate 137): restore a stored
    ``SUCCEEDED`` snapshot of this workspace into a NEW sandbox — a ``TENANT_SNAPSHOT`` job in
    load-only mode (``params.load``; it never re-exports); the sandbox tenant id is pre-allocated
    here and is the job's T-PLT-13 subject. Refusals by name: 403 ``forbidden``
    ``SANDBOX_ACTOR_REQUIRED`` (no user principal), 412 ``precondition-failed``
    ``SNAPSHOT_NOT_LOADABLE`` (the row is not ``SUCCEEDED`` or has no manifest), 422
    ``validation-failed`` on ``name`` (``SANDBOX_NAME_TAKEN`` when its code exists).
    ``sandbox-restricted`` when this workspace is itself a sandbox."""
    principal = uow.principal
    require_fresh_step_up(principal.mfa_verified_at, uow.now)
    if _source_kind(uow.session, principal.tenant_id) is not TenantKind.PRODUCTION:
        raise Problem("sandbox-restricted", NOT_PRODUCTION)
    if principal.kind is not PrincipalKind.USER or principal.id is None:
        raise sandboxes.actor_required()
    cleaned = name.strip()
    if not cleaned or len(cleaned) > LABEL_LENGTH:
        raise _invalid("name", f"name is 1 to {LABEL_LENGTH} characters.")
    row = _row(uow.session, tenant_snapshot_id)
    if row is None:
        raise Problem("not-found")
    if str(row["status"]) != RunStatus.SUCCEEDED.value or row["manifest_file_id"] is None:
        raise sandboxes.not_loadable(
            f"the snapshot is {row['status']}; only a SUCCEEDED snapshot with a manifest loads."
        )
    code = sandboxes.sandbox_code(cleaned)
    taken = uow.session.execute(select(tenant.c.id).where(tenant.c.code == code)).first()
    if taken is not None:
        raise sandboxes.sandbox_name_taken(code)
    sandbox_tenant_id = new_id()
    params: dict[str, Any] = {
        "tenant_snapshot_id": str(tenant_snapshot_id),
        "known_at": row["known_at"].isoformat(),
        "purpose": str(row["purpose"]),
        **sandboxes.load_params_of(
            sandbox_tenant_id=sandbox_tenant_id,
            name=cleaned,
            requested_by=principal.id,
            restore=True,
        ),
    }
    job = uow.defer(
        JobKind.TENANT_SNAPSHOT,
        params,
        subject_type=JOB_SUBJECT_TYPE,
        subject_id=sandbox_tenant_id,
    )
    job_id = UUID(str(job["id"]))
    uow.audit(
        action=sandboxes.ACTION_REQUESTED,
        object_type=OBJECT_TYPE,
        object_id=tenant_snapshot_id,
        before=None,
        after={"sandbox_tenant_id": str(sandbox_tenant_id)},
        detail={
            "tenant_snapshot_id": str(tenant_snapshot_id),
            "sandbox_tenant_id": str(sandbox_tenant_id),
            "name": cleaned,
            "job_id": str(job_id),
        },
    )
    return sandbox_tenant_id, jobs.job_out_of(uow.session, job_id)


def snapshot_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """The API members of a T-PLT-34 row read with ``_LIST_COLUMNS``: ``created_by`` is
    API-S-Actor — who asked for the snapshot (04 §16.14 API-S-TenantSnapshot)."""
    return {
        **{name: value for name, value in row.items() if name not in _READ_ONLY},
        "created_by": actors.actor(
            row["created_by"], row["created_by_kind"], row[_CREATED_BY_NAMED]
        ),
    }


def _row(session: Session, snapshot_id: UUID) -> Mapping[str, Any]:
    row = (
        session.execute(select(*_LIST_COLUMNS).where(tenant_snapshot.c.id == snapshot_id))
        .mappings()
        .one_or_none()
    )
    if row is None:  # unknown, or another tenant's row hidden by RLS
        raise Problem("not-found")
    return dict(row)


def get_snapshot(ctx: RequestContext, snapshot_id: UUID) -> Mapping[str, Any]:
    """``GET /tenant/snapshots/{id}``: the row's API members, 404 ``not-found`` otherwise."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return snapshot_out(_row(session, snapshot_id))


def list_snapshots[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """``GET /tenant/snapshots``: ``page`` applies the list parameters (DG-LST-01 to -07)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*_LIST_COLUMNS))


def manifest_content(
    ctx: RequestContext, snapshot_id: UUID, *, files: FileStore, keyring: KeyRing
) -> tuple[Mapping[str, Any], bytes]:
    """``GET /tenant/snapshots/{id}/manifest``: the stored manifest bytes verbatim, so their SHA-256
    is the row's ``manifest_sha256``; 404 ``not-found`` while the snapshot has no manifest."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = _row(session, snapshot_id)
        if row["manifest_file_id"] is None:
            raise Problem("not-found", NO_MANIFEST)
        _, stream = open_file(
            session, UUID(str(row["manifest_file_id"])), files=files, keyring=keyring
        )
    with stream:
        return row, stream.read()
