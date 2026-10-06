"""``TENANT_SNAPSHOT`` job handler (BUILD_SPEC SNP-1 slice I-2; 05 §10 SBX-02, SBX-03, SBX-06,
SBX-11; 05 §5.6 execution profile row; 04 T-PLT-34, §14.1 DB-03, DB-15; PRD ACT-50; lane record
§13.2).

The handler exports one tenant snapshot: it moves the T-PLT-34 row ``QUEUED → RUNNING``, reads
every copied dataset of the source as of an explicit ``known_at``, writes one JSONL file per
dataset and the manifest through a :class:`SnapshotWriter`, and ends ``RUNNING → SUCCEEDED`` with
the manifest digest and the row counts. Everything that decides is the pure :func:`export_snapshot`
over three protocols, so the unit tests drive it with fakes and the database adapters stay thin:

* :class:`SnapshotRepository` — the T-PLT-34 row (locked read, DB-03 transitions, audit events),
  the source tenant's kind and the 05 §5.6 copy lock ``tenant-copy:<source tenant>``, taken as a
  transaction advisory lock (supervisor ruling, record §13.1.1);
* :class:`SnapshotReader` — the rows of one dataset and the copied tables' row counts (SBX-11);
* :class:`SnapshotWriter` — one stored file per dataset and the manifest, each handed over as a
  stream (slice I-3: :class:`PutFileWriter` over ``files.store.put_file``, purpose
  ``SNAPSHOT_DATASET``, the stored bytes read back and compared; a dataset with no rows is not
  stored and its manifest entry carries the empty digest).

Refusals (each a :class:`Problem`): malformed params, a ``known_at`` later than now, a purpose
outside T-PLT-34 or a params / row mismatch → ``validation-failed``; no row → ``not-found``; a row
already ``SUCCEEDED`` → idempotent return; ``FAILED`` or ``RUNNING`` → ``invalid-transition``; a
sandbox source → ``sandbox-restricted`` (SBX-02: snapshots copy a production tenant); a source
whose row counts changed during the export, a process without a stamped release, a store whose
digest differs from what was hashed, or a failing write → ``precondition-failed`` (the write
failure names the datasets already stored; no manifest is written). The failure hook moves a
``QUEUED`` or ``RUNNING`` row to ``FAILED`` with the job's problem. Registration:
``jobs.registry.task`` on import; the worker's ``HANDLER_MODULES`` names this module (landed at
merge prep 2026-09-20, record §13.4.9), so ``TENANT_SNAPSHOT`` left ``PENDING_JOB_HANDLERS``; no
route imports this module.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, BinaryIO, Final, Protocol, cast
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from erev_api.controls.release import EngineRelease, current_release
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    metadata,
    registry_version,
    tenant,
    tenant_snapshot,
)
from erev_api.db.transitions import apply
from erev_api.domain.platform import sandboxes, snapshot_retention
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform.snapshot_export import select_export
from erev_api.enums import BookCode, FilePurpose, JobKind, RunStatus, TenantKind
from erev_api.files.store import open_file, put_file
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.problems import PROBLEMS, Problem, ProblemError
from erev_api.registry import resolve as registry_resolve
from erev_api.uow import UnitOfWork

__all__ = [
    "ACTION_CREATED",
    "ACTION_FAILED",
    "ACTION_STARTED",
    "COPY_LOCK",
    "DATASET_MEDIA_TYPE",
    "MANIFEST_MEDIA_TYPE",
    "MANIFEST_NAME",
    "SNAPSHOT_RETRY",
    "DbSnapshotReader",
    "DbSnapshotRepository",
    "ExportResult",
    "SnapshotParams",
    "SnapshotReader",
    "SnapshotRepository",
    "SnapshotWriter",
    "archive_failed_sandbox",
    "engine_release_of",
    "export_snapshot",
    "fail_snapshot",
    "parse_params",
    "retention_policy_for",
    "retention_unconfirmed",
    "snapshot_failed",
    "tenant_snapshot_export",
    "PutFileWriter",
    "RETENTION_UNCONFIRMED",
    "RETENTION_UNSET",
    "RetentionResolution",
    "STORAGE_FAILED",
    "STORED_MISMATCH",
    "writer_for",
]

TABLE: Final = "tenant_snapshot"
OBJECT_TYPE: Final = "tenant_snapshot"
ACTION_STARTED: Final = "tenant.snapshot_started"
ACTION_CREATED: Final = "tenant.snapshot_created"  # SBX-06
ACTION_FAILED: Final = "tenant.snapshot_failed"
# 05 §5.6: TENANT_SNAPSHOT retries none; the lock tenant-copy:<source tenant> is advisory (§13.1.1).
SNAPSHOT_RETRY: Final = RetryPolicy(max_attempts=1)
COPY_LOCK: Final = "tenant-copy:{tenant_id}"
DATASET_MEDIA_TYPE: Final = "application/x-ndjson"
MANIFEST_MEDIA_TYPE: Final = "application/json"
MANIFEST_NAME: Final = "manifest.json"
SNAPSHOTS_HREF: Final = "/api/v1/tenant/snapshots/{snapshot_id}"
KNOWN_AT_FUTURE: Final = "known_at must not be later than now."
NOT_PRODUCTION: Final = (
    "Snapshots copy a production tenant; a sandbox cannot be the source (SBX-02)."
)
ALREADY_RUNNING: Final = "This snapshot is already being exported."
ALREADY_FAILED: Final = "This snapshot failed; create a new one."
SOURCE_CHANGED: Final = "The source changed while the snapshot was read; the export was abandoned."
RELEASE_UNSTAMPED: Final = (
    "This process has no stamped engine release (05 REL-03); the snapshot cannot record the "
    "source's release and nothing was written."
)
RETENTION_UNSET: Final = (
    f"No confirmed snapshot retention policy: {sd.RETENTION_PARAMETER} is unset for this tenant "
    "(ruling Q-4 requires human confirmation before production use); nothing was read or written."
)
RETENTION_UNCONFIRMED: Final = (
    f"RETENTION_UNCONFIRMED: the in-force {sd.RETENTION_PARAMETER} version carries no named human "
    "approval (ruling D-98 candidate 86); nothing was counted, read or written."
)
SCOPE_UNREPRESENTABLE: Final = (
    f"{sd.SCOPE_UNREPRESENTABLE}: a scope array lost every target to the known_at cutoff; the copy "
    "never turns a restriction into all entities and never flips a paired flag (ruling D-98 "
    "candidate 106a); nothing was written."
)
BROKEN_REFERENCE: Final = (
    "A required reference names a row absent from the source; the export was abandoned "
    "(ruling D-98 62: never silently nulled)."
)
STORED_MISMATCH: Final = (
    "The stored bytes of {name} differ from what was hashed ({what}); the export was abandoned."
)
STORAGE_FAILED: Final = (
    "Storing a snapshot file failed; the export was abandoned before the manifest "
    "(the datasets already stored are named)."
)
_QUEUED: Final = RunStatus.QUEUED.value
_RUNNING: Final = RunStatus.RUNNING.value
_SUCCEEDED: Final = RunStatus.SUCCEEDED.value
_FAILED: Final = RunStatus.FAILED.value
_ADVISORY_LOCK: Final = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")


# --- params ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SnapshotParams:
    tenant_snapshot_id: UUID
    known_at: datetime  # explicit, timezone-aware (RFC 3339 in the job params)
    purpose: str


def _invalid(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed",
        message,
        errors=[ProblemError(field=field, rule_id="SNP-1", message=message)],
    )


def parse_params(params: Mapping[str, Any]) -> SnapshotParams:
    """The job params ``{tenant_snapshot_id, known_at, purpose}``; every field is required and
    ``known_at`` is an RFC 3339 instant with an offset (API-C-07) — nothing is defaulted here."""
    raw_id = params.get("tenant_snapshot_id")
    try:
        snapshot_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    except (TypeError, ValueError, AttributeError):
        raise _invalid("tenant_snapshot_id", "tenant_snapshot_id must be a UUID.") from None
    raw_at = params.get("known_at")
    if isinstance(raw_at, datetime):
        known_at = raw_at
    elif isinstance(raw_at, str):
        try:
            known_at = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
        except ValueError:
            raise _invalid("known_at", "known_at must be an RFC 3339 timestamp.") from None
    else:
        raise _invalid("known_at", "known_at is required (RFC 3339, UTC).")
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise _invalid("known_at", "known_at must carry a UTC offset.")
    purpose = params.get("purpose")
    if not isinstance(purpose, str) or purpose not in sd.PURPOSES:
        raise _invalid("purpose", f"purpose must be one of {', '.join(sorted(sd.PURPOSES))}.")
    return SnapshotParams(snapshot_id, known_at.astimezone(UTC), purpose)


# --- protocols ------------------------------------------------------------------------------------


class SnapshotRepository(Protocol):
    """The T-PLT-34 row and its tenant, as the export needs them."""

    @property
    def now(self) -> datetime: ...

    def load(self, snapshot_id: UUID) -> Mapping[str, Any]: ...  # locked; 404 not-found

    def source_kind(self, tenant_id: UUID) -> TenantKind: ...

    def take_copy_lock(self, tenant_id: UUID) -> None: ...  # 05 §5.6 tenant-copy:<tenant>

    def transition(
        self,
        snapshot_id: UUID,
        *,
        to_status: str,
        set_values: Mapping[str, Any],
        expected_status: str,
    ) -> Mapping[str, Any]: ...

    def audit(
        self,
        *,
        action: str,
        object_id: UUID,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        detail: Mapping[str, Any] | None,
    ) -> None: ...


class SnapshotReader(Protocol):
    """The source rows of one dataset (every row; ``cutoff`` applies ``known_at``) and the copied
    tables' row counts before and after the read (SBX-11)."""

    def rows(self, dataset: sd.Dataset) -> Sequence[Mapping[str, Any]]: ...

    def counts(self) -> Mapping[str, int]: ...

    def engine_release(self) -> str | None: ...

    def retention_policy(self) -> sd.RetentionPolicy | None: ...  # None = refusing default (I-5)


class SnapshotWriter(Protocol):
    """One stored file per dataset and the manifest, read from ``stream`` to its end; returns the
    ``file_object`` row (``id``, ``sha256`` of the stored bytes, ``size_bytes``)."""

    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ExportResult:
    snapshot_id: UUID
    status: str
    manifest_file_id: UUID | None
    manifest_sha256: str | None
    row_counts: Mapping[str, int]
    already_done: bool  # True when the row was SUCCEEDED before this run (idempotent return)


# --- the pure orchestration -----------------------------------------------------------------------


def _check_row(row: Mapping[str, Any], parsed: SnapshotParams, now: datetime) -> None:
    if parsed.known_at > now:
        raise _invalid("known_at", KNOWN_AT_FUTURE)
    row_known_at = row["known_at"]
    if not isinstance(row_known_at, datetime) or row_known_at.astimezone(UTC) != parsed.known_at:
        raise _invalid("known_at", "known_at differs from the snapshot row.")
    if str(row["purpose"]) != parsed.purpose:
        raise _invalid("purpose", "purpose differs from the snapshot row.")


def export_snapshot(
    repo: SnapshotRepository,
    reader: SnapshotReader,
    writer: SnapshotWriter,
    *,
    params: SnapshotParams,
    heartbeat: Callable[[], None] | None = None,
) -> ExportResult:
    """Export the snapshot named by ``params`` (see the module docstring for the refusals)."""
    row = repo.load(params.tenant_snapshot_id)
    snapshot_id = params.tenant_snapshot_id
    status = str(row["status"])
    if status == _SUCCEEDED:
        return ExportResult(
            snapshot_id,
            status,
            row.get("manifest_file_id"),
            row.get("manifest_sha256"),
            dict(row.get("row_counts") or {}),
            True,
        )
    if status == _FAILED:
        raise Problem("invalid-transition", ALREADY_FAILED)
    if status == _RUNNING:
        raise Problem("invalid-transition", ALREADY_RUNNING)
    _check_row(row, params, repo.now)
    tenant_id = row["tenant_id"]
    if repo.source_kind(tenant_id) is not TenantKind.PRODUCTION:
        raise Problem("sandbox-restricted", NOT_PRODUCTION)
    repo.take_copy_lock(tenant_id)
    repo.transition(
        snapshot_id,
        to_status=_RUNNING,
        set_values={"started_at": repo.now},
        expected_status=_QUEUED,
    )
    repo.audit(
        action=ACTION_STARTED,
        object_id=snapshot_id,
        before={"status": _QUEUED},
        after={"status": _RUNNING, "known_at": params.known_at, "purpose": params.purpose},
        detail=None,
    )
    # F-SNP-I2-R2: an unstamped process refuses before any dataset read or write (fail closed).
    release = reader.engine_release()
    if not release:
        raise Problem("precondition-failed", RELEASE_UNSTAMPED)
    # I-5: the Q-4 retention rules are tenant configuration with a refusing default.
    retention = reader.retention_policy()
    if retention is None:
        raise Problem("precondition-failed", RETENTION_UNSET)
    before = dict(reader.counts())
    inv = sd.inventory()
    source: dict[str, Sequence[Mapping[str, Any]]] = {}
    cut: dict[str, Sequence[Mapping[str, Any]]] = {}
    for dataset in inv.datasets:
        source[dataset.name] = reader.rows(dataset)
        cut[dataset.name] = sd.cutoff(dataset, source[dataset.name], params.known_at)
        if heartbeat is not None:
            heartbeat()
    # ruling D-98 62 (F-SNP-I2-R1): descendants of an excluded parent are excluded; a broken
    # required reference refuses before success
    parents = sd.apply_parent_cutoff(inv, source, cut)
    if parents.broken:
        raise Problem(
            "validation-failed",
            BROKEN_REFERENCE + " " + "; ".join(parents.broken),
            errors=[
                ProblemError(field=finding.split(":")[0], rule_id="SNP-1", message=finding)
                for finding in parents.broken
            ],
        )
    if parents.unrepresentable:  # D-98 candidate 106a: before selection, encoding and any write
        raise Problem(
            "validation-failed",
            SCOPE_UNREPRESENTABLE + " " + "; ".join(parents.unrepresentable),
            errors=[
                ProblemError(
                    field=finding.split(":", 1)[0],
                    rule_id=sd.SCOPE_UNREPRESENTABLE,
                    message=finding.split(": ", 1)[1],
                )
                for finding in parents.unrepresentable
            ],
        )
    # An open invitation is carried as one withdrawn before acceptance (05 SBX-03 rev 1.205):
    # the dataset's rule, applied to the kept rows before anything is selected or encoded.
    kept = sd.close_open_invitations(parents.kept, params.known_at)
    copied_ids = {
        name: [r["id"] for r in rows if "id" in r]
        for name, rows in kept.items()
        if inv.dataset(name).snapshot_class is sd.SnapshotClass.COPIED
    }
    selection = select_export(
        kept,
        kept.get("approval_request", ()),
        kept.get("approval_step", ()),
        kept.get("approval_decision", ()),
        kept.get("file_object", ()),
        copied_ids,
    )
    entries: list[sd.ManifestEntry] = []
    row_counts: dict[str, int] = {}
    written: list[str] = []
    for dataset in inv.datasets:
        rows = selection.rows.get(dataset.name, ())
        if not rows:  # T-PLT-29 stores at least one byte: a dataset with no rows has no file
            entries.append(sd.ManifestEntry(dataset.name, sd.EMPTY_SHA256, 0))
            row_counts[dataset.name] = 0
            if heartbeat is not None:
                heartbeat()
            continue
        stream = sd.encode_stream(dataset, rows)
        stored_row = _store(
            writer,
            name=f"{dataset.name}.jsonl",
            stream=cast(BinaryIO, stream),  # a RawIOBase; the same cast files.store makes
            media_type=DATASET_MEDIA_TYPE,
            written=written,
            dataset=dataset.name,
        )
        if not stream.exhausted or stored_row["sha256"] != stream.sha256:
            raise _write_failure(
                STORED_MISMATCH.format(
                    name=f"{dataset.name}.jsonl", what="the store's sha256 differs"
                ),
                written,
                dataset.name,
                "STORED_MISMATCH",
            )
        entries.append(sd.ManifestEntry(dataset.name, stream.sha256, stream.row_count))
        row_counts[dataset.name] = stream.row_count
        written.append(dataset.name)
        if heartbeat is not None:
            heartbeat()
    manifest = sd.Manifest(
        sd.Stamp(tenant_id, params.known_at, params.purpose),
        tuple(entries),
        inv.exclusions,
        sd.retention_of(selection.files, retention),
        sd.shared_dependencies(selection.rows, release),
        array_drops=parents.dropped_elements,
    )
    manifest_bytes = sd.manifest_bytes(manifest)
    digest = sd.manifest_sha256(manifest)
    stored = _store(
        writer,
        name=MANIFEST_NAME,
        stream=io.BytesIO(manifest_bytes),
        media_type=MANIFEST_MEDIA_TYPE,
        written=written,
        dataset="manifest",
    )
    if stored["sha256"] != digest:
        raise _write_failure(
            STORED_MISMATCH.format(name=MANIFEST_NAME, what="the store's sha256 differs"),
            written,
            "manifest",
            "STORED_MISMATCH",
        )
    after = dict(reader.counts())
    findings = sd.source_untouched(before, after)
    if findings:  # a post-write check: D-98 cand. 84 names the stored datasets, not a failed write
        raise _check_failure(SOURCE_CHANGED + " " + "; ".join(findings), written, "source_count")
    manifest_file_id = stored["id"]
    repo.transition(
        snapshot_id,
        to_status=_SUCCEEDED,
        set_values={
            "manifest_file_id": manifest_file_id,
            "manifest_sha256": digest,
            "row_counts": dict(row_counts),
            "finished_at": repo.now,
        },
        expected_status=_RUNNING,
    )
    repo.audit(
        action=ACTION_CREATED,
        object_id=snapshot_id,
        before={"status": _RUNNING},
        after={
            "status": _SUCCEEDED,
            "manifest_file_id": str(manifest_file_id),
            "manifest_sha256": digest,
        },
        detail={
            "known_at": params.known_at,
            "purpose": params.purpose,
            "datasets": len(entries),
            "rows": sum(row_counts.values()),
            "excluded_descendants": dict(parents.excluded_descendants),
            # I2-R3: identities are the primary-key text of each excluded row (row_identity)
            "excluded_descendant_ids": {
                table: list(ids) for table, ids in parents.excluded_ids.items()
            },
            "array_drops": dict(parents.dropped_elements),  # D-98 cand. 106
            "audit_history_carried": False,
        },
    )
    return ExportResult(snapshot_id, _SUCCEEDED, manifest_file_id, digest, row_counts, False)


def _write_failure(
    detail: str,
    written: Sequence[str],
    failed: str,
    kind: str,
    *,
    problem_slug: str | None = None,
) -> Problem:
    """Every refusal raised after the first dataset write began carries the datasets already
    stored (``SNP-1-WRITTEN``, write order) and the failed dataset (``SNP-1-WRITE``: the error's
    class name, or the refusal token ``STORED_MISMATCH`` where no exception exists — nothing else,
    DG-LOG-03; Codex I3-R1 / I3-R2). A wrapped catalogue ``Problem`` adds its slug in a separate
    entry ``problem_slug`` (``SNP-1-WRITE-SLUG``), validated against the catalogue (ruling D-98
    candidate 82): never free text, never the detail."""
    errors = [
        ProblemError(field="written", rule_id="SNP-1-WRITTEN", message=", ".join(written)),
        ProblemError(field=failed, rule_id="SNP-1-WRITE", message=kind),
    ]
    if problem_slug is not None:
        if problem_slug not in PROBLEMS:
            raise ValueError(f"{problem_slug!r} is not a catalogue slug (04 §15.2)")
        errors.append(
            ProblemError(field="problem_slug", rule_id="SNP-1-WRITE-SLUG", message=problem_slug)
        )
    return Problem("precondition-failed", detail, errors=errors)


def _check_failure(detail: str, written: Sequence[str], check: str) -> Problem:
    """A refusal raised by a post-write validation step (ruling D-98 candidate 84; Codex I41-R1):
    the datasets stored so far (``SNP-1-WRITTEN``, write order) and the check that refused
    (``SNP-1-CHECK``: field = the check's fixed name, message = the class name only) — never an
    invented failed dataset or phase token, so no ``SNP-1-WRITE``."""
    return Problem(
        "precondition-failed",
        detail,
        errors=[
            ProblemError(field="written", rule_id="SNP-1-WRITTEN", message=", ".join(written)),
            ProblemError(field=check, rule_id="SNP-1-CHECK", message=Problem.__name__),
        ],
    )


def _store(
    writer: SnapshotWriter,
    *,
    name: str,
    stream: BinaryIO,
    media_type: str,
    written: Sequence[str],
    dataset: str,
) -> Mapping[str, Any]:
    """One write, or the refusal that names the datasets already stored (slice I-3): any error
    becomes ``precondition-failed`` through :func:`_write_failure` with the error's class only —
    a native ``Problem`` included (I3-R1) — before any manifest exists."""
    try:
        return writer.write(name=name, stream=stream, media_type=media_type)
    except Exception as error:
        raise _write_failure(
            STORAGE_FAILED,
            written,
            dataset,
            type(error).__name__,
            problem_slug=error.slug if isinstance(error, Problem) else None,
        ) from error


def engine_release_of(release: EngineRelease | None) -> str | None:
    """The manifest's ``shared.engine_release``: ``<engine_version>+<build_sha>`` of the stamped
    T-PLT-38 release; None when no release is stamped — ``export_snapshot`` then refuses
    (``RELEASE_UNSTAMPED``) before any read or write."""
    return None if release is None else f"{release.engine_version}+{release.build_sha}"


def fail_snapshot(
    repo: SnapshotRepository, snapshot_id: UUID, problem: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    """The pure part of the failure hook: a ``QUEUED`` or ``RUNNING`` row ends ``FAILED`` with the
    job's problem recorded in the audit event; any other status is left alone."""
    row = repo.load(snapshot_id)
    status = str(row["status"])
    if status not in (_QUEUED, _RUNNING):
        return None
    updated = repo.transition(
        snapshot_id,
        to_status=_FAILED,
        set_values={"finished_at": repo.now},
        expected_status=status,
    )
    detail: dict[str, Any] = {
        "problem_type": str(problem.get("type")),
        "status": problem.get("status"),
    }
    errors = [dict(error) for error in problem.get("errors") or ()]
    by_rule = {str(e.get("rule_id")): e for e in errors if e.get("rule_id")}
    if "SNP-1-WRITTEN" in by_rule:
        # After the first dataset write began every refusal names the datasets stored so far
        # (D-98 cand. 84); a failed write adds the failed dataset (I-3), a post-write check the
        # check's name, a wrapped catalogue Problem its slug (D-98 cand. 82).
        written = str(by_rule["SNP-1-WRITTEN"].get("message") or "")
        detail["errors"] = errors
        detail["written"] = written.split(", ") if written else []
        if "SNP-1-WRITE" in by_rule:
            detail["failed"] = by_rule["SNP-1-WRITE"].get("field")
        if "SNP-1-CHECK" in by_rule:
            detail["check"] = by_rule["SNP-1-CHECK"].get("field")
        if "SNP-1-WRITE-SLUG" in by_rule:
            detail["problem_slug"] = by_rule["SNP-1-WRITE-SLUG"].get("message")
    repo.audit(
        action=ACTION_FAILED,
        object_id=snapshot_id,
        before={"status": status},
        after={"status": _FAILED},
        detail=detail,
    )
    return updated


# --- database adapters (thin; exercised by the written DB tests, not by the unit tests) -----------


class DbSnapshotRepository:
    """:class:`SnapshotRepository` over a unit of work."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    @property
    def now(self) -> datetime:
        return self._uow.now

    def load(self, snapshot_id: UUID) -> Mapping[str, Any]:
        row = (
            self._uow.session.execute(
                select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem("not-found")
        return dict(row)

    def source_kind(self, tenant_id: UUID) -> TenantKind:
        kind = self._uow.session.execute(
            select(tenant.c.kind).where(tenant.c.id == tenant_id)
        ).scalar_one()
        return TenantKind(str(kind))

    def take_copy_lock(self, tenant_id: UUID) -> None:
        self._uow.session.execute(_ADVISORY_LOCK, {"key": COPY_LOCK.format(tenant_id=tenant_id)})

    def transition(
        self,
        snapshot_id: UUID,
        *,
        to_status: str,
        set_values: Mapping[str, Any],
        expected_status: str,
    ) -> Mapping[str, Any]:
        return apply(
            self._uow.session,
            TABLE,
            snapshot_id,
            to_status=to_status,
            set_values=set_values,
            expected_status=expected_status,
        )

    def audit(
        self,
        *,
        action: str,
        object_id: UUID,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        detail: Mapping[str, Any] | None,
    ) -> None:
        self._uow.audit(
            action=action,
            object_type=OBJECT_TYPE,
            object_id=object_id,
            before=before,
            after=after,
            detail=detail,
        )


class DbSnapshotReader:
    """:class:`SnapshotReader` reading each dataset in its own read-only REPEATABLE READ tenant
    transaction (SBX-04: repeatable-read batches per table, established explicitly as the
    transaction's first statement); the counts bracket the read (SBX-11).

    Each read names the tenant. A dataset's table is taken from the model by name, and
    ``tenant_membership`` is one of them: its user policy shows a person their memberships of
    every tenant in any transaction that carries that person (dev-guide DG-KRN-DB-12). The worker
    reads as SYSTEM, but the handler also runs inline under a person's principal (the perf
    seed), and a copy holds the rows of its source and of no other workspace."""

    ISOLATION_LEVEL: Final = "REPEATABLE READ"

    def __init__(
        self,
        ctx: DbContext,
        *,
        engine_release: str | None = None,
        retention: sd.RetentionPolicy | None = None,
        retention_refusal: str | None = None,
        retention_unset: Problem | None = None,
    ) -> None:
        self._ctx = ctx
        self._engine_release = engine_release
        self._retention = retention
        self._retention_refusal = retention_refusal
        self._retention_unset = retention_unset

    def rows(self, dataset: sd.Dataset) -> Sequence[Mapping[str, Any]]:
        table = metadata.tables[f"erev.{dataset.name}"]
        with tenant_session(
            self._ctx, read_only=True, isolation_level=self.ISOLATION_LEVEL
        ) as session:
            statement = select(table).where(table.c.tenant_id == self._ctx.tenant_id)
            return [dict(row) for row in session.execute(statement).mappings()]

    def counts(self) -> Mapping[str, int]:
        with tenant_session(
            self._ctx, read_only=True, isolation_level=self.ISOLATION_LEVEL
        ) as session:
            return {name: _count(session, name, self._ctx.tenant_id) for name in sd.LOAD_ORDER}

    def engine_release(self) -> str | None:
        return self._engine_release

    def retention_policy(self) -> sd.RetentionPolicy | None:
        if self._retention_refusal is not None:
            raise retention_unconfirmed(self._retention_refusal)
        if self._retention is None and self._retention_unset is not None:
            # The refusing default in the words of PRD ERR-77 (``snapshot_retention``): from
            # when copies are possible. The exporter's own sentence is for a reader that knows
            # no more.
            raise self._retention_unset
        return self._retention


def retention_unconfirmed(reason: str) -> Problem:
    """The D-98 candidate 86 refusal, raised at the exporter's retention step."""
    return Problem("precondition-failed", f"{RETENTION_UNCONFIRMED} {reason}")


@dataclass(frozen=True, slots=True)
class RetentionResolution:
    """What the registry says about the tenant's retention families: a confirmed policy, the
    refusing default (both None) or an in-force version without a human approval (refusal)."""

    policy: sd.RetentionPolicy | None
    refusal: str | None = None
    # the refusing default as a person reads it (PRD ERR-77): from when copies are possible
    unset: Problem | None = None


def retention_policy_for(session: Session, known_at: datetime) -> RetentionResolution:
    """The tenant's ``platform.snapshot_retention_families`` in force at ``known_at`` (T-PLT-32
    resolution, TENANT level): the framework default ``{}`` is the refusing default
    (``RETENTION_UNSET``); a value outside the parameter's shape refuses ``validation-failed``;
    a confirming version without a named human approval is a ``RETENTION_UNCONFIRMED`` refusal
    (ruling D-98 candidate 86) — the confirming decision names the approver and the instant.
    The confirming version is the one that last changed or first stated the families
    (``snapshot_retention.confirming_version``); the policy's source names it and, when another
    version is in force, that version beside it. The refusing default carries its copy
    (``unset``, PRD ERR-77): from when copies are possible, read from the same version."""
    resolved = registry_resolve.resolve(
        session, sd.RETENTION_PARAMETER, book_code=BookCode.ASC606, known_at=known_at
    )
    if resolved.source_id is None:
        found = snapshot_retention.ahead(session, known_at)
        return RetentionResolution(None, unset=snapshot_retention.refusal(found))
    in_force: dict[str, Any] = dict(
        session.execute(select(registry_version).where(registry_version.c.id == resolved.source_id))
        .mappings()
        .one()
    )
    version = snapshot_retention.confirming_version(session, in_force)
    decisions: list[dict[str, Any]] = (
        [
            dict(row)
            for row in session.execute(
                select(approval_decision).where(
                    approval_decision.c.approval_request_id == version["approval_request_id"]
                )
            ).mappings()
        ]
        if version["approval_request_id"] is not None
        else []
    )
    try:
        confirmed = sd.retention_confirmation(version, decisions)
    except sd.UnconfirmedRetention as error:
        return RetentionResolution(None, str(error))
    try:
        policy = sd.retention_policy_of(
            resolved.value, sd.confirmation_source(version, confirmed, in_force=in_force)
        )
    except ValueError as error:
        raise Problem("validation-failed", str(error)) from error
    return RetentionResolution(policy)


def _count(session: Session, name: str, tenant_id: UUID) -> int:
    table = metadata.tables[f"erev.{name}"]
    statement = select(func.count()).select_from(table).where(table.c.tenant_id == tenant_id)
    return int(session.execute(statement).scalar_one())


class PutFileWriter:
    """:class:`SnapshotWriter` over ``files.store.put_file`` (slice I-3): each stream is spooled
    and hashed by the store under purpose ``SNAPSHOT_DATASET`` (E-68; encrypted at rest, PRV-06;
    content-addressed per tenant, sha256 and purpose), then read back through ``open_file`` and
    hashed again — the row is returned only when the read-back digest equals the row's."""

    PURPOSE: Final = FilePurpose.SNAPSHOT_DATASET
    CHUNK: Final = 1024 * 1024

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def write(self, *, name: str, stream: BinaryIO, media_type: str) -> Mapping[str, Any]:
        stored = put_file(
            self._uow,
            purpose=self.PURPOSE,
            stream=stream,
            original_filename=name,
            media_type=media_type,
        )
        row = stored.row
        _, plaintext = open_file(
            self._uow.session, row["id"], files=self._uow.files, keyring=self._uow.keyring
        )
        digest = hashlib.sha256()
        with plaintext:
            for chunk in iter(lambda: plaintext.read(self.CHUNK), b""):
                digest.update(chunk)
        if digest.hexdigest() != row["sha256"]:
            raise Problem(
                "precondition-failed",
                STORED_MISMATCH.format(name=name, what="read back through open_file"),
            )
        return row


def writer_for(uow: UnitOfWork) -> SnapshotWriter:
    """The handler's writer: :class:`PutFileWriter` over the unit of work's file store."""
    return PutFileWriter(uow)


# --- the job --------------------------------------------------------------------------------------


def snapshot_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The ``TENANT_SNAPSHOT`` failure hook (jobs.registry ``on_failure``): the row ends FAILED,
    and the sandbox of a load that failed is archived once the job's end is committed (05 SBX-04
    rev 1.64)."""
    archive_failed_sandbox(uow, params, problem)
    raw = params.get("tenant_snapshot_id")
    if raw is None:
        return
    try:
        snapshot_id = raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError):
        return
    fail_snapshot(DbSnapshotRepository(uow), snapshot_id, problem)


def archive_failed_sandbox(
    uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]
) -> None:
    """After the failing job's transaction commits, set the sandbox its params pre-allocated
    ``ARCHIVED`` if the load left it ``SUSPENDED`` (``sandboxes.archive_failed_load``; its own
    transaction in the sandbox's context, TXN-08). Params without a load name no sandbox."""
    try:
        load = sandboxes.parse_load(params)
    except Problem:
        return
    if load is None:
        return
    runtime = JobRuntime(clock=uow.clock, keyring=uow.keyring, files=uow.files)
    request_id = f"{uow.ctx.request_id}-load-failed"
    sandbox_tenant_id = load.sandbox_tenant_id
    failure = dict(problem)

    def archive() -> None:
        sandboxes.archive_failed_load(runtime, sandbox_tenant_id, failure, request_id=request_id)

    uow.after_commit(archive)


@task(JobKind.TENANT_SNAPSHOT, retry=SNAPSHOT_RETRY, on_failure=snapshot_failed)
def tenant_snapshot_export(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``TENANT_SNAPSHOT``: export the snapshot of ``params`` as of its explicit ``known_at``; with
    ``params.sandbox`` (a SANDBOX_COPY / SANDBOX_SEED) the same job then loads the sandbox, and
    with ``params.load`` (``POST /tenant/sandboxes``, mode ``restore``) it only loads — a
    ``SUCCEEDED`` row is never re-exported (SNP-2; 04 rev 1.67; D-98 candidate 137 (1))."""
    parsed = parse_params(params)
    load = sandboxes.parse_load(params)
    with jc.unit_of_work() as uow:
        resolution = retention_policy_for(uow.session, parsed.known_at)
        reader = DbSnapshotReader(
            uow.principal.db_context,
            engine_release=engine_release_of(current_release()),
            retention=resolution.policy,
            retention_refusal=resolution.refusal,
            retention_unset=resolution.unset,
        )
        result = export_snapshot(
            DbSnapshotRepository(uow),
            reader,
            writer_for(uow),
            params=parsed,
            heartbeat=jc.heartbeat,
        )
        uow.commit()
    counts: dict[str, Any] = {
        "datasets": len(result.row_counts),
        "rows": sum(result.row_counts.values()),
        "already_done": 1 if result.already_done else 0,
    }
    if load is not None:
        loaded = sandboxes.load_sandbox(
            jc, snapshot_id=parsed.tenant_snapshot_id, load=load, heartbeat=jc.heartbeat
        )
        counts.update(
            {
                "loaded_rows": loaded.rows,
                "groups_recomputed": loaded.groups_recomputed,
                "groups_not_recomputed": loaded.groups_not_recomputed,
                "derived_mismatches": loaded.derived_mismatches,
                "blocked_periods": loaded.blocked_periods,
            }
        )
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": SNAPSHOTS_HREF.format(snapshot_id=result.snapshot_id),
            "counts": counts,
            **({"sandbox_tenant_id": str(load.sandbox_tenant_id)} if load is not None else {}),
        },
    )
