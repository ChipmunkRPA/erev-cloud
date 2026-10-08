"""Sandbox load and determinism verification (BUILD_SPEC SNP-2; 05 §10 SBX-02 to SBX-06, SBX-11;
04 rev 1.67 API-R-04 / T-PLT-34 / §15.4-B / §16.14; D-98 candidate 137 with amendments 1 and 2).

Two entry points share one loader: ``POST /tenant/snapshots`` with purpose ``SANDBOX_COPY`` or
``SANDBOX_SEED`` (its ``TENANT_SNAPSHOT`` job exports, then loads — ``params.sandbox``) and
``POST /tenant/sandboxes`` (a stored ``SUCCEEDED`` snapshot restored into a NEW sandbox by a
``TENANT_SNAPSHOT`` job in load-only mode — ``params.load``; API-S-Job ``mode = "restore"``).

The pure part (planning, refusals, typed decoding, the load report, the copy phase's guards) is
tested on CPU; the database driver :func:`load_sandbox` by the DB witnesses of
``tests/domain/platform/test_sandbox_load.py`` and ``test_sandbox_replay.py``.

Sequence (04 T-PLT-34 rev 1.67; 05 SBX-04):

1. **authorise** — the snapshot row is ``SUCCEEDED`` with a manifest (``SNAPSHOT_NOT_LOADABLE``);
   the request carried a user principal (``SANDBOX_ACTOR_REQUIRED`` — only an ACTIVE membership of
   the sandbox makes the target visible to DB-15 under RLS-TN, 04 rev 1.56; provisioning scope
   reveals nothing); the manifest's stamp, format and dataset list equal the running registry
   (``SNAPSHOT_REGISTRY_MISMATCH``); each file's SHA-256 and row count equal the manifest
   (``SNAPSHOT_DIGEST_MISMATCH``).
2. **provision** — the sandbox ``tenant`` row in provisioning scope (the id pre-allocated by the
   request; ``kind = 'sandbox'``, ``source_tenant_id``, ``source_known_at``; ``SANDBOX_NAME_TAKEN``
   on a code collision), its audit key, its ``audit_chain_head`` and one ``ledger_chain_head`` per
   book (04 §14.3: the sandbox's own chains start empty; no copied dataset brings them). The row
   is inserted ``SUSPENDED`` (05 SBX-04 rev 1.64): it becomes ``ACTIVE`` in step 6 with its
   summary event, and a failed load's sandbox is set ``ARCHIVED`` by the job's failure hook
   (:func:`archive_failed_load`) — until then it cannot be opened and takes no command.
3. **load** — COPIED datasets streamed in ``LOAD_ORDER`` under the sandbox context, ``tenant_id``
   re-stamped, identities preserved, deferred references inserted NULL and restored by the fixup
   step, a self-reference inserted with its row (the dataset's rows referenced-first),
   ``contract_event`` in source ``record_seq`` order (DB-08 re-stamps). The tables of a
   component (``snapshot_dataset.COMPONENTS`` — the stream with its obligations, estimates,
   estimate versions and manual adjustments, whose frozen references form a cycle no table order
   breaks) load as ONE unit at the component's first table: their rows in one order in which
   every row follows the rows it names, in one transaction (05 SBX-04 rev 1.50). This is the COPY
   PHASE (05 SBX-04 rev 1.30; 04 §14.3 rev 1.85): every transaction that inserts a copied dataset,
   restores an approval graph, finalizes held statuses or fixes up deferred references is one
   :func:`copy_transaction` — the provisioning platform scope with the sandbox tenant context set
   inside, the shape step 2 uses — because the DB-04 insert guard admits a copied configuration
   version in its exported PUBLISHED / TESTED / APPROVED status only there. Its four compensating
   controls live in that one function; no later step carries the scope.
4. **target** — ``tenant_snapshot.target_tenant_id`` set under the requesting user's context.
5. **periods / recompute / replay** — every period of the source's ``period_state`` dataset opens
   (``future`` then ``open`` with their transitions), every ``combination_group`` is recomputed with
   trigger ``MIGRATION`` in its own transaction (the load FAILS by name when the budget is exceeded,
   listing the groups not recomputed — never a partial success), then the source's transitions and
   locks are replayed through the DB-03 transition kernel; a refused step is the WARNING
   ``SANDBOX_REPLAY_BLOCKED`` and the period stays at its last reachable state.
6. **verify / report / audit** — ``derived_mismatches`` per (group, book) against the source's
   latest version as of ``known_at`` (05 SBX-05 rev 1.50): the MONETARY STATE of the two versions
   — stored version, balances, obligation versions and schedule lines without the per-version
   activity columns — and, where the source version is its group's first computation, the
   sandbox's recomputed output hashed with the source computation's ``input_sha256`` in place of
   its own against the source version's stored ``output_sha256`` (the raw hashes can never be
   equal: the load re-stamps what the input hash covers; and a later source version is one step
   of an incremental history that a single recompute does not retrace); each mismatch names the
   first differing member; ONE load report (file purpose ``AUDIT_DIGEST``) referenced by the
   load's single summary event in the sandbox, ``tenant.snapshot_loaded`` — written after the
   verification, so every earlier event of the sandbox's chain is this load's own period replay
   or recompute (05 SBX-06 rev 1.34); ``tenant.sandbox_restored`` in the source; a non-zero count
   raises ``SANDBOX_DETERMINISM_MISMATCH`` and notifies the requester.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import sqlalchemy as sa

from erev_api.db import errors as db_errors
from erev_api.db.tables import metadata
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform.snapshot_replay import BlockedPeriod
from erev_api.enums import JobKind
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JOB_MODE_EXPORT, JOB_MODE_RESTORE
from erev_api.schemas.common import job_mode as common_job_mode

if TYPE_CHECKING:
    from erev_engine.bundle import InputBundle, OutputBundle
    from sqlalchemy.orm import ORMExecuteState, Session

    from erev_api.auth.keyring import KeyRing
    from erev_api.domain.contracts.computation import Engine

__all__ = [
    "ACTION_LOADED",
    "ACTION_LOAD_FAILED",
    "ACTION_REQUESTED",
    "ACTION_RESTORED",
    "BUDGET_SECONDS",
    "COPY_PHASE_SCOPE",
    "COPY_PHASE_TABLES",
    "EXCEPTION_DETERMINISM",
    "EXCEPTION_REPLAY_BLOCKED",
    "LOAD_REPORT_FORMAT_VERSION",
    "LOAD_REPORT_PURPOSE",
    "MODE_EXPORT",
    "MODE_RESTORE",
    "RULE_ACTOR",
    "RULE_BUDGET",
    "RULE_DIGEST",
    "RULE_KEY_DENIED",
    "RULE_NAME_TAKEN",
    "RULE_NOT_LOADABLE",
    "RULE_PERIODS_BLOCKED",
    "RULE_REGISTRY",
    "RULE_SEED",
    "SANDBOX_ID_HEADER",
    "BlockedPeriod",
    "LoadParams",
    "LoadPlan",
    "LoadReport",
    "PlannedDataset",
    "check_copy_statement",
    "coerce_row",
    "copy_refused",
    "copy_transaction",
    "guard_refusal",
    "job_mode",
    "key_provisioning_denied",
    "load_params_of",
    "parse_load",
    "plan_load",
    "provision_audit_key",
    "report_bytes",
    "archive_failed_load",
    "require_point_in_time",
    "sandbox_code",
    "sandbox_load_of",
    "sandbox_name_taken",
    "verify_entry",
    "verify_manifest",
]

# 04 §16.14 (rev 1.67; rev 1.95): the request event in the source, the load's single summary event
# in the sandbox, the completion event in the source.
ACTION_REQUESTED: Final = "tenant.sandbox_requested"
ACTION_LOADED: Final = "tenant.snapshot_loaded"
ACTION_RESTORED: Final = "tenant.sandbox_restored"
# 04 §16.14 rev 1.125: written in the sandbox a failed load leaves ARCHIVED (05 SBX-04).
ACTION_LOAD_FAILED: Final = "tenant.sandbox_load_failed"
SANDBOX_ID_HEADER: Final = "X-Erev-Sandbox-Tenant-Id"  # API-R-04 rev 1.67
# 04 §15.4-B; the E-68 purpose widened in rev 1.67 to job-written verification artefacts.
EXCEPTION_DETERMINISM: Final = "SANDBOX_DETERMINISM_MISMATCH"
EXCEPTION_REPLAY_BLOCKED: Final = "SANDBOX_REPLAY_BLOCKED"
LOAD_REPORT_PURPOSE: Final = "AUDIT_DIGEST"
LOAD_REPORT_FORMAT_VERSION: Final = 1
# Load refusals ride existing slugs as rule_ids (04 rev 1.67; D-98 candidate 137 amendment 1).
RULE_NOT_LOADABLE: Final = "SNAPSHOT_NOT_LOADABLE"  # 412 precondition-failed
RULE_REGISTRY: Final = "SNAPSHOT_REGISTRY_MISMATCH"  # 412 precondition-failed
RULE_DIGEST: Final = "SNAPSHOT_DIGEST_MISMATCH"  # 412 precondition-failed
RULE_BUDGET: Final = "SANDBOX_RECOMPUTE_BUDGET"  # 412 precondition-failed (D-98 137 (2))
RULE_ACTOR: Final = "SANDBOX_ACTOR_REQUIRED"  # 403 forbidden
RULE_NAME_TAKEN: Final = "SANDBOX_NAME_TAKEN"  # 422 validation-failed on `name`
# 05 SBX-04 rev 1.64: the refusal of a consumer that needs point-in-time equivalence.
RULE_PERIODS_BLOCKED: Final = "SANDBOX_PERIODS_BLOCKED"  # 412 precondition-failed
# 05 SBX-07 rev 1.64: a reset goes back to the sandbox's SEED snapshot, or to empty.
RULE_SEED: Final = "SANDBOX_SEED_REQUIRED"  # 422 validation-failed on `tenant_snapshot_id`
# 05 SBX-02 rev 1.64 (ruling R-60 (d)): the provider denies the worker the key of a new tenant.
RULE_KEY_DENIED: Final = "SANDBOX_KEY_PROVISIONING_DENIED"  # 412 precondition-failed
KEY_DENIED: Final = (
    "A new sandbox workspace needs its own audit key, and this deployment's worker is not "
    "allowed to create one. No workspace was created; an operator has to enable sandbox copies "
    "for this deployment."
)
# The load's summary event is written within the job's 1,800 s timeout of the tenant row
# (05 §5.6); the window bounds the partitions of `audit_event` the lookup reads.
LOAD_EVENT_WINDOW: Final = timedelta(days=2)
# API-S-Job `mode` (rev 1.67), derived from the job params — never a stored column.
MODE_EXPORT: Final = JOB_MODE_EXPORT
MODE_RESTORE: Final = JOB_MODE_RESTORE
# D-98 candidate 137 (2): the in-job sequential recompute budget; exceeding it fails the load by
# name (RULE_BUDGET) listing the groups not recomputed.
BUDGET_SECONDS: Final = 1800.0
_CODE_PREFIX: Final = "sbx-"
_CODE_MAX: Final = 40  # provisioning.TENANT_CODE_LENGTH = range(3, 41)
_NOT_CODE: Final = re.compile(r"[^a-z0-9]+")
_CODE: Final = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # provisioning.TENANT_CODE
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_UUID_LIKE: Final = re.compile(r"^[0-9a-fA-F-]{36}$")


# --- refusals ----------------------------------------------------------------------------------


def _precondition(rule_id: str, message: str, field_name: str = "tenant_snapshot_id") -> Problem:
    return Problem(
        "precondition-failed",
        errors=[ProblemError(field=field_name, rule_id=rule_id, message=message)],
    )


def not_loadable(message: str) -> Problem:
    return _precondition(RULE_NOT_LOADABLE, message)


def registry_mismatch(message: str) -> Problem:
    return _precondition(RULE_REGISTRY, message)


def digest_mismatch(message: str) -> Problem:
    return _precondition(RULE_DIGEST, message)


def budget_exceeded(pending: Sequence[UUID]) -> Problem:
    listed = ", ".join(str(group_id) for group_id in pending)
    return _precondition(
        RULE_BUDGET,
        f"The sandbox recompute exceeded its budget of {BUDGET_SECONDS:.0f} s; groups not "
        f"recomputed: {listed}. The load failed; nothing partial is reported as success.",
    )


def key_provisioning_denied() -> Problem:
    """05 SBX-02 rev 1.64 (KEY-05; supervisor ruling R-60 (d), item OPS-SBX-KEY-1): hosted, the
    worker's identity reads keys and does not hold the provisioning role, so until the deployment
    gives a job that creates a tenant an authority that may, a sandbox copy fails closed — by
    this name, with no tenant row committed, and not as an unexpected error."""
    return Problem(
        "precondition-failed",
        errors=[ProblemError(field=None, rule_id=RULE_KEY_DENIED, message=KEY_DENIED)],
    )


def actor_required() -> Problem:
    return Problem(
        "forbidden",
        errors=[
            ProblemError(
                field="requested_by",
                rule_id=RULE_ACTOR,
                message=(
                    "A sandbox is created for a signed-in user: the user's membership of the "
                    "sandbox is what makes the target visible (04 rev 1.56)."
                ),
            )
        ],
    )


def sandbox_name_taken(code: str) -> Problem:
    return Problem(
        "validation-failed",
        errors=[
            ProblemError(
                field="name",
                rule_id=RULE_NAME_TAKEN,
                message=f"A workspace with code {code!r} already exists; choose another name.",
            )
        ],
    )


# --- params and mode ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoadParams:
    """``params.load`` (restore) or ``params.sandbox`` (export then load) of a TENANT_SNAPSHOT job:
    the sandbox tenant id pre-allocated by the request, the requested name and the requesting user
    (``None`` for a SYSTEM request — refused by ``SANDBOX_ACTOR_REQUIRED`` before any write)."""

    sandbox_tenant_id: UUID
    name: str
    requested_by: UUID | None
    restore: bool  # True for `params.load` (load-only), False for `params.sandbox`
    # The successor of a reset takes the old sandbox's name and a code of its own (05 SBX-07);
    # None derives the code from the name (`sandbox_code`).
    code: str | None = None

    def as_params(self) -> dict[str, Any]:
        params = {
            "sandbox_tenant_id": str(self.sandbox_tenant_id),
            "name": self.name,
            "requested_by": None if self.requested_by is None else str(self.requested_by),
        }
        if self.code is not None:
            params["code"] = self.code
        return params


def _uuid_field(value: Any, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and _UUID_LIKE.fullmatch(value):
        try:
            return UUID(value)
        except ValueError:
            pass
    raise Problem(
        "validation-failed",
        errors=[
            ProblemError(field=field_name, rule_id="PARAMS_INVALID", message="a uuid is required.")
        ],
    )


def parse_load(params: Mapping[str, Any]) -> LoadParams | None:
    """The load part of TENANT_SNAPSHOT params: ``load`` (restore) or ``sandbox`` (copy); ``None``
    when the job only exports. Malformed shapes are refused by name (422 ``validation-failed``)."""
    restore = "load" in params
    block = params.get("load") if restore else params.get("sandbox")
    if block is None:
        return None
    if not isinstance(block, Mapping):
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="load", rule_id="PARAMS_INVALID", message="an object.")],
        )
    name = block.get("name")
    if not isinstance(name, str) or not name.strip():
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="load.name", rule_id="PARAMS_INVALID", message="a name.")],
        )
    requested_by = block.get("requested_by")
    code = block.get("code")
    if code is not None and not (
        isinstance(code, str) and _CODE.fullmatch(code) and 3 <= len(code) <= _CODE_MAX
    ):
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="load.code", rule_id="PARAMS_INVALID", message="a code.")],
        )
    return LoadParams(
        sandbox_tenant_id=_uuid_field(block.get("sandbox_tenant_id"), "load.sandbox_tenant_id"),
        name=name.strip(),
        requested_by=None
        if requested_by is None
        else _uuid_field(requested_by, "load.requested_by"),
        restore=restore,
        code=code,
    )


def load_params_of(
    *,
    sandbox_tenant_id: UUID,
    name: str,
    requested_by: UUID | None,
    restore: bool,
    code: str | None = None,
) -> dict[str, Any]:
    """The params entry the request writes: ``{"load": {...}}`` or ``{"sandbox": {...}}``."""
    load = LoadParams(sandbox_tenant_id, name, requested_by, restore, code)
    return {("load" if restore else "sandbox"): load.as_params()}


def job_mode(kind: str | JobKind, params: Mapping[str, Any] | None) -> str | None:
    """API-S-Job ``mode`` (04 rev 1.67; D-98 137 (1)) — the kernel derivation of
    ``schemas.common.job_mode``: ``restore`` when a TENANT_SNAPSHOT job carries ``params.load``,
    ``export`` for every other TENANT_SNAPSHOT job, ``None`` otherwise."""
    return common_job_mode(kind, params)


def sandbox_code(name: str) -> str:
    """The sandbox tenant ``code`` from the requested name: ``sbx-`` + the lowercase slug, cut to
    the T-PLT-01 code length; a collision on ``ux_tenant__code`` is ``SANDBOX_NAME_TAKEN``."""
    slug = _NOT_CODE.sub("-", name.strip().lower()).strip("-")
    if not slug:
        slug = "sandbox"
    code = (_CODE_PREFIX + slug)[:_CODE_MAX].rstrip("-")
    return code if len(code) >= 3 else _CODE_PREFIX + "sandbox"


# --- manifest verification and the load plan ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannedDataset:
    """One manifest entry bound to its registry dataset: loaded as rows (COPIED) or read for the
    replay plan (REPLAY_REFERENCE); ``row_count == 0`` datasets have no stored file."""

    name: str
    sha256: str
    row_count: int
    load_rows: bool  # COPIED: insert; REPLAY_REFERENCE: read for the period replay only
    load_position: int


@dataclass(frozen=True, slots=True)
class LoadPlan:
    source_tenant_id: UUID
    known_at: datetime
    purpose: str
    datasets: tuple[PlannedDataset, ...]  # LOAD_ORDER


def verify_manifest(document: Mapping[str, Any], inventory: Any) -> LoadPlan:
    """The manifest document against the RUNNING registry (``snapshot_dataset.inventory()``): the
    same ``format_version``, the same dataset names in the same ``LOAD_ORDER``, hex digests and
    integer counts — anything else is ``SNAPSHOT_REGISTRY_MISMATCH`` (the registry is versioned by
    the release stamp, not guessed)."""
    from erev_api.domain.platform import snapshot_dataset as sd

    if document.get("format_version") != sd.MANIFEST_FORMAT_VERSION:
        raise registry_mismatch(
            f"manifest format_version {document.get('format_version')!r} differs from the running "
            f"registry's {sd.MANIFEST_FORMAT_VERSION}."
        )
    entries = document.get("datasets")
    if not isinstance(entries, list):
        raise registry_mismatch("the manifest carries no dataset list.")
    expected = [dataset.name for dataset in inventory.datasets]
    names = [entry.get("name") for entry in entries if isinstance(entry, Mapping)]
    if names != expected:
        present = {str(n) for n in names if n is not None}
        missing = sorted(set(expected) - present)
        extra = sorted(present - set(expected))
        raise registry_mismatch(
            "the manifest's datasets differ from the running registry"
            + (f"; missing {missing}" if missing else "")
            + (f"; unknown {extra}" if extra else "")
            + ("; order differs" if not missing and not extra else "")
            + "."
        )
    planned: list[PlannedDataset] = []
    for entry, dataset in zip(entries, inventory.datasets, strict=True):
        sha = entry.get("sha256")
        count = entry.get("row_count")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise registry_mismatch(f"{dataset.name}: the manifest digest is not a SHA-256.")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise registry_mismatch(f"{dataset.name}: the manifest row_count is not a count.")
        planned.append(
            PlannedDataset(
                dataset.name,
                sha,
                count,
                dataset.snapshot_class is sd.SnapshotClass.COPIED,
                dataset.load_position,
            )
        )
    try:
        source_tenant_id = UUID(str(document["source_tenant_id"]))
        known_at = datetime.fromisoformat(str(document["known_at"]))
        purpose = str(document["purpose"])
    except (KeyError, ValueError, TypeError) as error:
        raise registry_mismatch(f"the manifest stamp is unreadable: {error}.") from None
    if known_at.tzinfo is None:
        known_at = known_at.replace(tzinfo=UTC)
    if purpose not in sd.PURPOSES:
        raise registry_mismatch(f"the manifest purpose {purpose!r} is not a T-PLT-34 purpose.")
    return LoadPlan(source_tenant_id, known_at.astimezone(UTC), purpose, tuple(planned))


def verify_entry(planned: PlannedDataset, *, stored_sha256: str, decoded_rows: int) -> None:
    """A dataset file against its manifest entry: the stored row's SHA-256 (the store hashed and
    read the plaintext back at export) and the number of decoded rows
    (``SNAPSHOT_DIGEST_MISMATCH``)."""
    if stored_sha256 != planned.sha256:
        raise digest_mismatch(
            f"{planned.name}: the stored file's SHA-256 differs from the manifest entry."
        )
    if decoded_rows != planned.row_count:
        raise digest_mismatch(
            f"{planned.name}: {decoded_rows} rows decoded, the manifest counts {planned.row_count}."
        )


def plan_load(plan: LoadPlan) -> tuple[PlannedDataset, ...]:
    """The datasets to insert, in ``LOAD_ORDER`` (COPIED with rows); REPLAY_REFERENCE and empty
    datasets are left out."""
    return tuple(
        sorted(
            (d for d in plan.datasets if d.load_rows and d.row_count > 0),
            key=lambda d: d.load_position,
        )
    )


# --- typed decoding of a JSONL row --------------------------------------------------------------


def _impl(column_type: Any) -> Any:
    return getattr(column_type, "impl", column_type)


def _coerce_scalar(column_type: Any, value: Any) -> Any:
    if value is None:
        return None
    base = _impl(column_type)
    if isinstance(base, sa.Uuid):
        return UUID(str(value))
    if isinstance(base, sa.DateTime):
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    if isinstance(base, sa.Date):
        return date.fromisoformat(str(value))
    if isinstance(base, sa.Numeric) and not isinstance(base, sa.Float):
        return Decimal(str(value))
    return value


def coerce_row(
    table: sa.Table,
    row: Mapping[str, Any],
    *,
    tenant_id: UUID,
    deferred: Sequence[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The insertable values of one decoded JSONL row: JSON strings back to the column types
    (uuid, timestamptz, date, numeric — including the money / exact decorators — and arrays of
    them), ``tenant_id`` re-stamped to the sandbox, and the ``deferred`` reference columns held
    back as NULL; returns ``(values, held)`` where ``held`` is what the fixup step restores. A
    GENERATED column (``account_mapping_rule.specificity``) is never inserted: the database
    derives it from the row and refuses any supplied value."""
    values: dict[str, Any] = {}
    held: dict[str, Any] = {}
    for column in table.columns:
        name = column.name
        if name == "tenant_id":
            values[name] = tenant_id
            continue
        if column.computed is not None:
            continue  # GENERATED ALWAYS: derived by the database from the inserted row
        if name not in row:
            continue  # server default (e.g. record_seq, recorded_at under DB-08)
        raw = row[name]
        base = _impl(column.type)
        if isinstance(base, sa.ARRAY):
            coerced = None if raw is None else [_coerce_scalar(base.item_type, v) for v in raw]
        else:
            coerced = _coerce_scalar(column.type, raw)
        if name in deferred and coerced is not None:
            held[name] = coerced
            values[name] = None
        else:
            values[name] = coerced
    return values, held


@dataclass(frozen=True, slots=True)
class HeldFinalization:
    """A copied row inserted in its initial status; its exported status and set-once finalization
    columns are applied through the DB-03 kernel after the guarded dependants loaded."""

    table: str
    row_id: UUID
    final_status: str
    set_values: Mapping[str, Any]


def hold_finalization(
    name: str, values: Mapping[str, Any]
) -> tuple[dict[str, Any], HeldFinalization | None]:
    """The insertable values of a copied row under ``snapshot_dataset.FINALIZATIONS``: a finalized
    row goes in as its initial status with the held set-once columns NULL, and what was held is
    returned for the kernel to apply once the guarded dependants loaded (R3); every other row is
    unchanged."""
    rule = sd.FINALIZATIONS.get(name)
    inserted = dict(values)
    if rule is None:
        return inserted, None
    status = inserted.get(rule.status_column)
    status_text = None if status is None else str(getattr(status, "value", status))
    if status_text not in rule.final:
        return inserted, None
    if rule.when is not None and inserted.get(rule.when) is None:
        return inserted, None
    inserted[rule.status_column] = rule.initial
    set_values: dict[str, Any] = {}
    for column in rule.held:
        if inserted.get(column) is not None:
            set_values[column] = inserted[column]
            inserted[column] = None
    assert status_text is not None
    return inserted, HeldFinalization(name, UUID(str(inserted["id"])), status_text, set_values)


@dataclass(frozen=True, slots=True)
class GraphBatch:
    """One root row with its dependants' rows, in the registry's order (typed values)."""

    root: Mapping[str, Any]
    dependants: Mapping[str, tuple[Mapping[str, Any], ...]]


def _order_key(row: Mapping[str, Any], columns: Sequence[str]) -> tuple[Any, ...]:
    key: list[Any] = []
    for column in columns:
        value = row.get(column)
        if value is None:
            key.append((1, ""))
        elif isinstance(value, datetime):
            key.append((0, value.timestamp()))
        elif isinstance(value, int):
            key.append((0, value))
        else:
            key.append((0, str(value)))
    return tuple(key)


def graph_batches(
    graph: sd.Graph,
    roots: Sequence[Mapping[str, Any]],
    dependants: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[GraphBatch, ...]:
    """The graphs of ``graph.root``: every FINALIZED root in the registry's chronological order
    (``order``: ``submitted_at``, then id for equal timestamps), then the legitimately CURRENT root
    (``graph.current``) last — the explicit partition of Codex 1757 §2 — each root with its
    dependants' rows in their order (APPROVAL-UNIQUE-1); a dependant row naming no root is an
    inconsistent export (``ValueError``)."""
    by_id = {UUID(str(row["id"])): row for row in roots}
    grouped: dict[UUID, dict[str, list[Mapping[str, Any]]]] = {
        root_id: {name: [] for name, _ in graph.dependants} for root_id in by_id
    }
    for name, column in graph.dependants:
        for row in dependants.get(name, ()):
            root_id = UUID(str(row[column]))
            if root_id not in grouped:
                raise ValueError(f"{name} row {row.get('id')} names no {graph.root} {root_id}")
            grouped[root_id][name].append(row)

    def partition(row: Mapping[str, Any]) -> int:
        if graph.current is None:
            return 0
        column, value = graph.current
        return 1 if str(getattr(row.get(column), "value", row.get(column))) == value else 0

    ordered = sorted(
        by_id.values(), key=lambda row: (partition(row), *_order_key(row, graph.order))
    )
    batches: list[GraphBatch] = []
    for root in ordered:
        root_id = UUID(str(root["id"]))
        batches.append(
            GraphBatch(
                root,
                {
                    name: tuple(
                        sorted(rows, key=lambda r: _order_key(r, graph.dependant_order[name]))
                    )
                    for name, rows in grouped[root_id].items()
                },
            )
        )
    return tuple(batches)


def typed_references(
    references: Mapping[str, Sequence[Mapping[str, Any]]], *, tenant_id: UUID
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    """REPLAY-2 (Codex 1623 §1): the three REPLAY_REFERENCE populations decoded BY THEIR TABLE
    SCHEMA — uuid, timestamptz, date and the enums as text — and re-stamped to the sandbox, so the
    planner receives the typed objects it validates; the validation itself stays with
    ``snapshot_replay``."""
    from erev_api.domain.platform.sandbox_periods import REFERENCE_DATASETS

    typed: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for name in REFERENCE_DATASETS:
        table = metadata.tables[f"erev.{name}"]
        typed[name] = tuple(
            coerce_row(table, row, tenant_id=tenant_id)[0] for row in references.get(name, ())
        )
    return typed


def sandbox_actor(sandbox_tenant_id: UUID, user_id: UUID, *, at: datetime) -> Any:
    """The requesting user as a principal OF THE SANDBOX: their copied ACTIVE membership and the
    grants its copied assignments confer at ``at`` (the ``_session_context`` shape of the auth
    kernel). The period replay runs its normal commands as this principal, so their permissions
    are the guards' facts; a requester without a copied membership is refused by name."""
    from erev_api.auth.permissions import effective_grants
    from erev_api.auth.principal import Principal
    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import app_user, tenant_membership
    from erev_api.enums import PrincipalKind

    lookup = DbContext(tenant_id=sandbox_tenant_id, user_id=user_id, entity_scope="*")
    with tenant_session(lookup, read_only=True) as db:
        membership_id = db.execute(
            sa.select(tenant_membership.c.id).where(
                tenant_membership.c.tenant_id == sandbox_tenant_id,
                tenant_membership.c.user_id == user_id,
                tenant_membership.c.status == "ACTIVE",
            )
        ).scalar_one_or_none()
        if membership_id is None:
            raise actor_required()
        grants = effective_grants(db, UUID(str(membership_id)), at=at)
        display_name = db.execute(
            sa.select(app_user.c.display_name).where(app_user.c.id == user_id)
        ).scalar_one_or_none()
    return Principal(
        kind=PrincipalKind.USER,
        id=user_id,
        tenant_id=sandbox_tenant_id,
        membership_id=UUID(str(membership_id)),
        display_name=str(display_name) if display_name else "Requester",
        roles=grants.roles,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope=grants.entity_scope,
        auth_method="system",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
        role_scopes=grants.role_scopes,
    )


# --- the load report (ONE place for derived_mismatches; D-98 137 (4)) ---------------------------


@dataclass(frozen=True, slots=True)
class LoadReport:
    sandbox_tenant_id: UUID
    source_tenant_id: UUID
    tenant_snapshot_id: UUID
    known_at: datetime
    loaded_at: datetime
    row_counts: Mapping[str, int]
    groups_recomputed: int
    compared: int
    mismatches: tuple[Mapping[str, Any], ...]
    blocked_periods: tuple[BlockedPeriod, ...] = field(default_factory=tuple)
    format_version: int = LOAD_REPORT_FORMAT_VERSION
    # of the pairs present on both sides, those whose source version is a first computation and
    # were therefore compared by output hash as well as by monetary state (05 SBX-05 rev 1.50)
    first_computations: int = 0

    @property
    def derived_mismatches(self) -> int:
        return len(self.mismatches)


def _json_default(value: Any) -> Any:
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"not JSON-serialisable: {type(value).__name__}")


def report_document(report: LoadReport) -> dict[str, Any]:
    return {
        "format_version": report.format_version,
        "sandbox_tenant_id": str(report.sandbox_tenant_id),
        "source_tenant_id": str(report.source_tenant_id),
        "tenant_snapshot_id": str(report.tenant_snapshot_id),
        "known_at": report.known_at.astimezone(UTC).isoformat(),
        "loaded_at": report.loaded_at.astimezone(UTC).isoformat(),
        "row_counts": dict(sorted(report.row_counts.items())),
        "groups_recomputed": report.groups_recomputed,
        "compared": report.compared,
        "first_computations": report.first_computations,
        "derived_mismatches": report.derived_mismatches,
        "mismatches": [dict(m) for m in report.mismatches],
        "blocked_periods": [
            {
                "period_state_id": str(b.period_state_id),
                "entity_id": str(b.entity_id),
                "book_code": b.book_code,
                "period_id": str(b.period_id),
                "attempted": b.attempted,
                "reached": b.reached,
                "reason": b.reason,
            }
            for b in report.blocked_periods
        ],
    }


def report_bytes(report: LoadReport) -> bytes:
    """Canonical JSON (sorted keys, LF-terminated) — the ``AUDIT_DIGEST`` file the sandbox's
    ``tenant.snapshot_loaded`` event references by id and SHA-256."""
    return (
        json.dumps(report_document(report), sort_keys=True, default=_json_default, indent=None)
        + "\n"
    ).encode("utf-8")


def provision_audit_key(runtime: Any, keyring: KeyRing, tenant_id: UUID) -> str:
    """The audit HMAC key of a tenant a job creates (05 KEY-05; DG-KRN-KEY-06): through the
    runtime's provisioning authority — hosted, the tenant secret is created and its first version
    read back through the key ring — or derived locally when the runtime names none. Returns the
    key id the ``tenant`` row must carry.

    An authority the provider denies (hosted: a worker identity without the provisioning role)
    is the named refusal :func:`key_provisioning_denied`; the caller asks inside the transaction
    that inserts the tenant row, so nothing of the tenant is committed. An outage, a malformed
    secret and every other failure propagate as they are and the job's retry policy applies."""
    from erev_api.auth.keyring import DerivedTenantKeyProvisioner, provisioning_denied

    provisioner = getattr(runtime, "key_provisioner", None) or DerivedTenantKeyProvisioner(keyring)
    try:
        return str(provisioner.provision_audit_key(tenant_id))
    except Exception as error:
        if provisioning_denied(error):
            raise key_provisioning_denied() from error
        raise


# --- a loaded sandbox's facts (05 SBX-04 rev 1.64; 04 §16.14 rev 1.125) ---------------------------


def sandbox_load_of(session: Session, tenant_row: Mapping[str, Any]) -> dict[str, Any] | None:
    """API-S-Tenant ``sandbox_load``: what the sandbox's own ``tenant.snapshot_loaded`` event says
    about its load — the SEED snapshot (the event's object), when it was loaded, the mismatch
    count, the blocked period states and the load report. None for a production tenant, a sandbox
    created empty (no ``source_known_at``) and a sandbox whose load has not written the event.

    The lookup is bounded to :data:`LOAD_EVENT_WINDOW` after the tenant row's ``created_at``: the
    event is written within the job's timeout of it, and an unbounded read of the partitioned
    ``audit_event`` would touch every partition."""
    from erev_api.db.tables import audit_event
    from erev_api.enums import TenantKind

    if str(tenant_row["kind"]) != TenantKind.SANDBOX.value or tenant_row["source_known_at"] is None:
        return None
    created_at: datetime = tenant_row["created_at"]
    event = (
        session.execute(
            sa.select(audit_event.c.object_id, audit_event.c.occurred_at, audit_event.c.detail)
            .where(
                audit_event.c.tenant_id == tenant_row["id"],
                audit_event.c.action == ACTION_LOADED,
                audit_event.c.occurred_at >= created_at,
                audit_event.c.occurred_at < created_at + LOAD_EVENT_WINDOW,
            )
            .order_by(audit_event.c.chain_seq)
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if event is None:
        return None
    detail = dict(event["detail"] or {})
    return {
        "tenant_snapshot_id": event["object_id"],
        "loaded_at": event["occurred_at"],
        "derived_mismatches": int(detail.get("derived_mismatches", 0)),
        "blocked_periods": [UUID(str(value)) for value in detail.get("blocked_periods", ())],
        "load_report_file_id": UUID(str(detail["load_report_file_id"])),
        "load_report_sha256": str(detail["load_report_sha256"]),
    }


def _tenant_facts(session: Session, tenant_id: UUID) -> Mapping[str, Any]:
    from erev_api.db.tables import tenant

    return dict(
        session.execute(
            sa.select(
                tenant.c.id,
                tenant.c.kind,
                tenant.c.status,
                tenant.c.source_tenant_id,
                tenant.c.source_known_at,
                tenant.c.created_at,
            ).where(tenant.c.id == tenant_id)
        )
        .mappings()
        .one()
    )


def require_point_in_time(session: Session, tenant_id: UUID) -> None:
    """05 SBX-04 (rev 1.20; rev 1.64): a consumer that requires point-in-time equivalence with
    the source — a replay, a scenario refresh, a forecast run — calls this before it reads a
    derived figure of the sandbox ``tenant_id`` (the session's tenant) and is refused by name
    while ``blocked_periods`` is non-empty: those periods stopped short of their source state, so
    postings the source holds in a closed period sit elsewhere here. 412 ``precondition-failed``,
    rule id ``SANDBOX_PERIODS_BLOCKED``, naming the period states. A production tenant, a sandbox
    created empty and a sandbox with no blocked period pass."""
    loaded = sandbox_load_of(session, _tenant_facts(session, tenant_id))
    if loaded is None or not loaded["blocked_periods"]:
        return
    blocked = ", ".join(str(state_id) for state_id in loaded["blocked_periods"])
    raise _precondition(
        RULE_PERIODS_BLOCKED,
        f"This sandbox could not replay {len(loaded['blocked_periods'])} period state(s) to the "
        f"source's state ({blocked}); figures that depend on the period a posting falls in are "
        "not equal to the source's as of the copy.",
        field_name="blocked_periods",
    )


def archive_failed_load(
    runtime: Any, sandbox_tenant_id: UUID, problem: Mapping[str, Any], *, request_id: str
) -> bool:
    """05 SBX-04 rev 1.64: the sandbox of a load that failed is set ARCHIVED — it was never
    ACTIVE, so it was never a workspace — with ``tenant.sandbox_load_failed`` in its own chain.
    A tenant that does not exist (the load failed before provisioning it) or is not SUSPENDED
    (the load completed; a later step failed) is left alone. Its own transaction, in the
    sandbox's context, as its SYSTEM principal; returns whether it archived."""
    from erev_api.auth.principal import system_principal
    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import tenant
    from erev_api.enums import PrincipalKind, TenantStatus
    from erev_api.jobs.context import system_unit_of_work

    principal = system_principal(sandbox_tenant_id)
    lookup = DbContext(tenant_id=sandbox_tenant_id, user_id=None, entity_scope="*")
    with tenant_session(lookup, read_only=True) as session:
        status = session.execute(
            sa.select(tenant.c.status).where(tenant.c.id == sandbox_tenant_id)
        ).scalar_one_or_none()
    if status != TenantStatus.SUSPENDED.value:
        return False
    with system_unit_of_work(runtime, principal, request_id=request_id) as uow:
        archived = uow.session.execute(
            sa.update(tenant)
            .where(
                tenant.c.id == sandbox_tenant_id,
                tenant.c.status == TenantStatus.SUSPENDED.value,
            )
            .values(
                status=TenantStatus.ARCHIVED.value,
                updated_at=uow.now,
                updated_by=None,
                updated_by_kind=PrincipalKind.SYSTEM.value,
            )
            .returning(tenant.c.id)
        ).first()
        if archived is None:
            return False
        uow.audit(
            action=ACTION_LOAD_FAILED,
            object_type="tenant",
            object_id=sandbox_tenant_id,
            before={"status": TenantStatus.SUSPENDED.value},
            after={"status": TenantStatus.ARCHIVED.value},
            detail={
                "problem_type": str(problem.get("type")),
                "status": problem.get("status"),
            },
        )
        uow.commit()
    return True


# --- the copy phase (05 SBX-04 rev 1.30; 04 §14.3 rev 1.85) -------------------------------------

# The platform scope of the copy phase: the scope ``tenant.provision`` runs under, in its second
# sanctioned use. Only there does the DB-04 insert guard admit a copied configuration version in
# its exported PUBLISHED / TESTED / APPROVED status, and the DB-04 child guard its children.
COPY_PHASE_SCOPE: Final = "provisioning"
# Compensating control 1: the only tables a copy-phase transaction writes. The scope also lifts
# the ``tenant`` INSERT policy (RLS-TN); ``LOAD_ORDER`` carries no ``tenant`` table and the phase
# writes the COPIED datasets of ``LOAD_ORDER`` only (the three REPLAY_REFERENCE datasets belong to
# the period replay, which does not carry the scope), so that capability is unused by construction.
COPY_PHASE_TABLES: Final = frozenset(
    name for name in sd.LOAD_ORDER if sd.RULES[name].snapshot_class is sd.SnapshotClass.COPIED
)


def check_copy_statement(statement: Any) -> None:
    """Compensating control 1 at the session boundary: a copy-phase transaction reads, and inserts
    or updates rows of ``COPY_PHASE_TABLES``. Anything else — a write to another table (``tenant``
    above all), a DELETE, a textual or DDL statement — is a defect of the loader and is refused
    here, before it reaches the database (``RuntimeError``: never a business refusal)."""
    if getattr(statement, "is_select", False):
        return
    if getattr(statement, "is_insert", False) or getattr(statement, "is_update", False):
        table = getattr(statement, "table", None)
        name = getattr(table, "name", None)
        if name in COPY_PHASE_TABLES and table is metadata.tables.get(f"erev.{name}"):
            return
        raise RuntimeError(
            f"the sandbox copy phase writes the copied LOAD_ORDER tables only, not {name!r} "
            "(05 SBX-04)"
        )
    raise RuntimeError(
        "the sandbox copy phase runs SELECT, INSERT and UPDATE statements only (05 SBX-04)"
    )


def guard_refusal(error: BaseException) -> str | None:
    """The first line of a database guard's own refusal — SQLSTATE P0001 with an ``EREV-…``
    message (04 §14.1) — else None: every other error is a defect and is never named."""
    if not isinstance(error, sa.exc.DBAPIError):
        return None
    if db_errors.sqlstate(error) != db_errors.RAISE_EXCEPTION:
        return None
    lines = db_errors.message_primary(error).strip().splitlines()
    line = lines[0].strip() if lines else ""
    return line if line.startswith("EREV-") else None


def copy_refused(step: str, guard_line: str) -> Problem:
    """Compensating control 4: a database guard's refusal raised in the copy phase, by name —
    ``SNAPSHOT_NOT_LOADABLE`` (412 ``precondition-failed``) with the guard's first line as the
    detail; ``step`` names the copy-phase transaction that was refused."""
    return Problem(
        "precondition-failed",
        guard_line,
        errors=[
            ProblemError(
                field="tenant_snapshot_id",
                rule_id=RULE_NOT_LOADABLE,
                message=f"{step} was refused by a database guard: {guard_line}",
            )
        ],
    )


@contextmanager
def copy_transaction(
    *,
    sandbox_tenant_id: UUID,
    requested_by: UUID,
    request_id: str,
    keyring: KeyRing,
    step: str,
) -> Iterator[Session]:
    """ONE transaction of the COPY PHASE of a sandbox load (05 SBX-04 rev 1.30; 04 §14.3 rev 1.85),
    committed on a clean exit and rolled back on any error: ``erev_app`` under
    ``app.platform_scope = 'provisioning'`` with the sandbox tenant context set inside — the shape
    ``tenant.provision`` and the loader's own provision step use. Exactly five guards yield to
    that scope (the ``tenant`` INSERT policy, the DB-04 version and child guards, the two SSP
    bodies), so the copied configuration versions and their children go in with their exported
    status; DB-01 / 02 / 03 / 07 / 08 / 10 / 12 / 15 and every RLS-T / TE / TM policy stay live.

    The ruling's compensating controls, all in this one function:

    1. the transaction writes rows of ``COPY_PHASE_TABLES`` only (``check_copy_statement`` sees
       every statement of the session), so the tenant-creation capability the scope retains is
       unused by construction;
    2. the tenant context is the sandbox's and no other is ever set (TXN-08), so row-level
       security refuses a row of any other tenant (the DB witness in
       ``tests/pg/test_sandbox_isolation.py``);
    3. ``platform_session`` records ONE ``PLATFORM_SCOPE_USED`` security event in this
       transaction, naming the sandbox tenant and ``requested_by`` (DG-KRN-DB-03); a rolled-back
       transaction leaves none, as it leaves nothing else;
    4. a database guard's own refusal — SQLSTATE P0001 with an ``EREV-…`` message, from a statement
       or from a deferred constraint at the commit — is re-raised as the named
       ``SNAPSHOT_NOT_LOADABLE`` with the guard's first line as the detail (``copy_refused``); a
       ``Problem`` raised inside passes unchanged and every other error propagates as the defect
       it is.
    """
    from sqlalchemy import event

    from erev_api.db.session import (
        DbContext,
        name_platform_tenant,
        platform_session,
        set_tenant_context,
    )

    def guard(state: ORMExecuteState) -> None:
        check_copy_statement(state.statement)

    try:
        with platform_session(
            COPY_PHASE_SCOPE, actor_user_id=requested_by, request_id=request_id, keyring=keyring
        ) as session:
            name_platform_tenant(session, sandbox_tenant_id)
            set_tenant_context(
                session, DbContext(tenant_id=sandbox_tenant_id, user_id=None, entity_scope="*")
            )
            event.listen(session, "do_orm_execute", guard)
            try:
                yield session
            finally:
                # The scope's own PLATFORM_SCOPE_USED insert follows this block (control 3).
                event.remove(session, "do_orm_execute", guard)
    except sa.exc.DBAPIError as error:
        line = guard_refusal(error)
        if line is None:
            raise
        raise copy_refused(step, line) from error


# --- database driver -----------------------------------------------------------------------------


def _kept(run: Engine) -> tuple[Engine, list[OutputBundle]]:
    """``run`` and the outputs it returns, in call order. 05 SBX-05 compares the sandbox's
    recomputed OUTPUT, and only the recompute holds it — the stored rows keep its hash."""
    outputs: list[OutputBundle] = []

    def engine(bundle: InputBundle) -> OutputBundle:
        output = run(bundle)
        outputs.append(output)
        return output

    return engine, outputs


def _source_of(expected: Mapping[tuple[UUID, str], Any], finding: Any, member: str) -> str | None:
    """``member`` (``output_sha256`` or ``input_sha256``) of the source version behind a
    finding; None without a source version as of ``known_at``."""
    source = expected.get((finding.combination_group_id, finding.book_code))
    return None if source is None else str(getattr(source, member))


def _stored_of(stored: Mapping[tuple[UUID, str], tuple[Any, ...]], finding: Any) -> str | None:
    """The sandbox version's own stored ``output_sha256``; None when nothing was recomputed."""
    found = stored.get((finding.combination_group_id, finding.book_code))
    return None if found is None else str(found[1])


def _comparable_of(hashes: Mapping[tuple[UUID, str], Any], finding: Any) -> str | None:
    """The sandbox's comparable hash where the hash comparison found the pair unequal; None
    where the hashes were equal or the pair is one-sided."""
    found = hashes.get((finding.combination_group_id, finding.book_code))
    return None if found is None else found.sandbox_sha256


def _named(finding: Any) -> str:
    """One finding as the warning names it: the pair, the comparison and the member."""
    pair = f"group {finding.combination_group_id} in {finding.book_code}"
    if finding.member is None:
        side = "the source" if finding.sandbox is None else "the sandbox"
        return f"{pair} has a version in {side} only"
    return f"{pair}, {finding.member} ({finding.comparison})"


def _monetary_rows(
    session: Session, tenant_id: UUID, version_id: UUID
) -> dict[str, list[Mapping[str, Any]]]:
    """The stored rows of one contract version that make its monetary state
    (``snapshot_export.MONETARY_TABLES``), each schedule line with its header's
    ``schedule_kind``; read under the session's own tenant context.

    ``schedule_line`` is partitioned and keyed for reads by contract
    (``ix_schedule_line__contract``), so the version's lines are asked for through the contracts
    its balances and obligation versions name; the headers' ``line_count`` says whether that
    found every line, and when it did not the lines are read by the version alone."""
    from erev_api.domain.platform import snapshot_export as sx

    tables = {name: metadata.tables[f"erev.{name}"] for name in sx.MONETARY_TABLES}
    version, lines = tables["contract_version"], tables["schedule_line"]
    rows: dict[str, list[Mapping[str, Any]]] = {
        "contract_version": [
            dict(row)
            for row in session.execute(
                sa.select(version).where(
                    version.c.tenant_id == tenant_id, version.c.id == version_id
                )
            ).mappings()
        ]
    }
    for name in sx.MONETARY_TABLES:
        if name in {"contract_version", "schedule_line"}:
            continue  # the version itself and the line/header join have specialized reads
        table = tables[name]
        rows[name] = [
            dict(row)
            for row in session.execute(
                sa.select(table).where(
                    table.c.tenant_id == tenant_id, table.c.contract_version_id == version_id
                )
            ).mappings()
        ]
    kinds = {row["id"]: row["schedule_kind"] for row in rows["schedule"]}
    expected = sum(int(row["line_count"]) for row in rows["schedule"])
    contracts = sorted(
        {
            row["contract_id"]
            for name in ("contract_version_balance", "obligation_version")
            for row in rows[name]
        },
        key=str,
    )

    def read(*narrowed: Any) -> list[Mapping[str, Any]]:
        found = session.execute(
            sa.select(lines).where(
                lines.c.tenant_id == tenant_id, lines.c.contract_version_id == version_id, *narrowed
            )
        ).mappings()
        return [{**line, "schedule_kind": kinds[line["schedule_id"]]} for line in found]

    found = read(lines.c.contract_id.in_(contracts)) if contracts else []
    rows["schedule_line"] = found if len(found) == expected else read()
    return rows


@dataclass(frozen=True, slots=True)
class Loaded:
    """What :func:`load_sandbox` reports back to the job outcome."""

    sandbox_tenant_id: UUID
    report_file_id: UUID
    report_sha256: str
    derived_mismatches: int
    blocked_periods: int
    groups_recomputed: int
    rows: int
    groups_not_recomputed: int = 0  # QUARANTINED / FAILED / deferred (R1: not a recompute)


def load_sandbox(  # noqa: PLR0912, PLR0915 — the SBX-04 sequence, one step after another
    jc: Any,
    *,
    snapshot_id: UUID,
    load: LoadParams,
    heartbeat: Callable[[], None] | None = None,
    budget_seconds: float = BUDGET_SECONDS,
) -> Loaded:
    """The SBX-04 load of snapshot ``snapshot_id`` into the pre-allocated sandbox, driven by the
    ``TENANT_SNAPSHOT`` job context ``jc`` (its principal is the SOURCE tenant's SYSTEM principal;
    every phase is its own transaction — TXN-08)."""
    from erev_api.auth.keyring import ProvisioningReadbackError
    from erev_api.auth.principal import system_principal
    from erev_api.db import transitions as tx
    from erev_api.db.session import (
        DbContext,
        name_platform_tenant,
        platform_session,
        set_tenant_context,
        tenant_session,
    )
    from erev_api.db.tables import (
        audit_chain_head,
        combination_group,
        contract_computation,
        contract_version,
        ledger_chain_head,
        metadata,
        tenant,
        tenant_membership,
        tenant_snapshot,
    )
    from erev_api.domain.contracts import computation, compute_job
    from erev_api.domain.imports.exceptions import raise_exception_item
    from erev_api.domain.journals.subledger import ledger_chain_head_rows
    from erev_api.domain.platform import sandbox_periods
    from erev_api.domain.platform import snapshot_export as sx
    from erev_api.enums import (
        ComputationStatus,
        ComputationTrigger,
        ExceptionSeverity,
        ExceptionSource,
        FilePurpose,
        NotificationKind,
        PrincipalKind,
        TenantKind,
        TenantStatus,
    )
    from erev_api.events.notifications import notify
    from erev_api.files.store import open_file, put_file
    from erev_api.jobs.context import system_unit_of_work

    beat = heartbeat or (lambda: None)
    runtime = jc.runtime
    keyring, files = runtime.keyring, runtime.files
    if keyring is None or files is None:
        raise RuntimeError("the job runtime has no key ring or file store")
    source_id: UUID = jc.tenant_id
    now: datetime = jc.clock.now()
    if load.requested_by is None:
        raise actor_required()
    requester: UUID = load.requested_by

    # 1. authorise: the snapshot row, the manifest, the registry.
    with jc.unit_of_work() as uow:
        session = uow.session
        row = (
            session.execute(select_snapshot(tenant_snapshot, snapshot_id)).mappings().one_or_none()
        )
        if row is None:
            raise not_loadable("the snapshot does not exist in this workspace.")
        if str(row["status"]) != "SUCCEEDED" or row["manifest_file_id"] is None:
            raise not_loadable(
                f"the snapshot is {row['status']} and cannot be loaded; only a SUCCEEDED "
                "snapshot with a manifest loads."
            )
        manifest_row, manifest_stream = open_file(
            session, UUID(str(row["manifest_file_id"])), files=files, keyring=keyring
        )
        manifest_bytes = manifest_stream.read()
        if str(manifest_row["sha256"]) != str(row["manifest_sha256"]):
            raise digest_mismatch("the stored manifest's SHA-256 differs from the snapshot row.")
        document = json.loads(manifest_bytes.decode("utf-8"))
        inventory = sd.inventory()
        plan = verify_manifest(document, inventory)
        if plan.source_tenant_id != source_id:
            raise registry_mismatch("the manifest names another source tenant.")
        reporting_currency = session.execute(
            sa.select(tenant.c.reporting_currency).where(tenant.c.id == source_id)
        ).scalar_one()
        requester_membership = session.execute(
            sa.select(tenant_membership.c.id).where(
                tenant_membership.c.tenant_id == source_id,
                tenant_membership.c.user_id == load.requested_by,
                tenant_membership.c.status == "ACTIVE",
            )
        ).scalar_one_or_none()
    beat()

    # 2. provision the sandbox tenant (provisioning scope), its key and its chain heads.
    code = load.code or sandbox_code(load.name)
    stamp = {
        "created_at": now,
        "created_by": None,
        "created_by_kind": PrincipalKind.SYSTEM.value,
        "updated_at": now,
        "updated_by": None,
        "updated_by_kind": PrincipalKind.SYSTEM.value,
    }
    try:
        with platform_session(
            "provisioning",
            actor_user_id=load.requested_by,
            request_id=f"job-{jc.job_id}-provision",
            keyring=keyring,
        ) as session:
            jc.enlist(session)  # 05 JOB-06 rev 1.200: a transaction of the load's job
            audit_key_id = keyring.new_tenant_audit_key_id(load.sandbox_tenant_id)
            session.execute(
                sa.insert(tenant).values(
                    id=load.sandbox_tenant_id,
                    code=code,
                    kind=TenantKind.SANDBOX.value,
                    # 05 SBX-04 rev 1.64: not a workspace until the load's last transaction
                    status=TenantStatus.SUSPENDED.value,
                    display_name=load.name[:400],
                    reporting_currency=reporting_currency,
                    is_demo=False,
                    audit_hmac_key_id=audit_key_id,
                    source_tenant_id=source_id,
                    source_known_at=plan.known_at,
                    setup_completed_at=now,
                    **stamp,
                )
            )
            # DG-KRN-KEY-06, as `tenant.provision`: the row first under its deterministic key
            # id, then the key through the runtime's provisioning authority (hosted: the
            # tenant secret is created and read back), so a sandbox commits only with a key
            # that can be read; a failure rolls the row back.
            provisioned = provision_audit_key(runtime, keyring, load.sandbox_tenant_id)
            if provisioned != audit_key_id:
                raise ProvisioningReadbackError(provisioned)
            name_platform_tenant(session, load.sandbox_tenant_id)
            set_tenant_context(
                session,
                DbContext(tenant_id=load.sandbox_tenant_id, user_id=None, entity_scope="*"),
            )
            session.execute(
                sa.insert(audit_chain_head).values(
                    tenant_id=load.sandbox_tenant_id, last_chain_seq=0, updated_at=now
                )
            )
            # 04 §14.3: a ledger chain head per book, as `tenant.provision` seeds it. T-SL-03 is
            # REGENERATED — the sandbox's own ledger chain starts empty — and the recompute's
            # postings need the head (no copied dataset brings it).
            session.execute(
                sa.insert(ledger_chain_head),
                ledger_chain_head_rows(load.sandbox_tenant_id, now=now),
            )
    except sa.exc.IntegrityError as error:
        if "ux_tenant__code" in str(error.orig):
            raise sandbox_name_taken(code) from None
        raise
    beat()

    # 3. load the COPIED datasets in LOAD_ORDER; hold deferred references for the fixup step.
    # This is the COPY PHASE (05 SBX-04 rev 1.30; 04 §14.3 rev 1.85): each of its transactions is
    # one `copy_step` — and nothing after the fixup step carries the platform scope.
    sandbox_principal = system_principal(load.sandbox_tenant_id)
    held_rows: list[tuple[str, tuple[str, ...], dict[str, Any], dict[str, Any]]] = []
    held_finalizations: list[HeldFinalization] = []
    row_counts: dict[str, int] = {}
    replay_source: dict[str, tuple[Mapping[str, Any], ...]] = {}

    @contextmanager
    def copy_step(name: str, what: str) -> Iterator[Session]:
        """One copy-phase transaction of this load: the provisioning platform scope with the
        sandbox tenant context, for the requester, under the request id ``job-<job>-<name>``;
        ``what`` names the transaction in a guard's refusal (``copy_transaction``). It is a
        transaction of the load's job and passes its door first (05 JOB-06 rev 1.200): the
        job's lock, which the statement guard admits as the read it is, and a heartbeat in
        the job's workspace - a step of a load whose job was stopped writes nothing."""
        with copy_transaction(
            sandbox_tenant_id=load.sandbox_tenant_id,
            requested_by=requester,
            request_id=f"job-{jc.job_id}-{name}",
            keyring=keyring,
            step=what,
        ) as session:
            jc.enlist(session)
            yield session

    def apply_finalization(session: Session, held_row: HeldFinalization) -> None:
        """The exported status and the held columns of one row: through the DB-03 kernel for a
        governed table, or — for ``tenant_membership``, an SC-M status the kernel does not govern
        — the platform domain's plain status UPDATE (``users._set_status`` shape); the row is IM-M,
        so DB-02 ``tg_touch`` stamps the sandbox's own ``updated_at`` and ``row_version`` (source
        + 1) — stated in 05 SBX-04, never bypassed (MEMBERSHIP-1, MEMBERSHIP-STAMPS-1)."""
        rule = sd.FINALIZATIONS[held_row.table]
        if rule.kernel:
            tx.apply(
                session,
                held_row.table,
                held_row.row_id,
                to_status=held_row.final_status,
                set_values=held_row.set_values,
                expected_status=rule.initial,
            )
            return
        table = metadata.tables[f"erev.{held_row.table}"]
        session.execute(
            sa.update(table)
            .where(
                table.c.tenant_id == load.sandbox_tenant_id,
                table.c.id == held_row.row_id,
                table.c[rule.status_column] == rule.initial,
            )
            .values(**{rule.status_column: held_row.final_status}, **dict(held_row.set_values))
        )

    def finalize_after(name: str) -> None:
        """R3 / MEMBERSHIP-1: once the dataset the guard protects has loaded, apply the exported
        statuses of the held rows — steps before their request, memberships last — in one
        copy-phase transaction."""
        due = [h for h in held_finalizations if sd.FINALIZATIONS[h.table].after == name]
        if not due:
            return
        with copy_step(
            f"finalize-{name}", f"the finalization of the rows held for {name}"
        ) as session:
            for table_name in sd.FINALIZATION_ORDER:
                for held_row in due:
                    if held_row.table == table_name:
                        apply_finalization(session, held_row)
        for held_row in due:
            held_finalizations.remove(held_row)

    def read_rows(planned: PlannedDataset) -> tuple[Mapping[str, Any], ...]:
        """The dataset's rows from its stored file (opened in the SOURCE context), verified."""
        if planned.row_count == 0:
            row_counts[planned.name] = 0
            return ()
        with jc.unit_of_work() as uow:  # the files belong to the SOURCE tenant
            stored = (
                uow.session.execute(
                    select_file_by_digest(planned.sha256, FilePurpose.SNAPSHOT_DATASET.value)
                )
                .mappings()
                .one_or_none()
            )
            if stored is None:
                raise digest_mismatch(f"{planned.name}: no stored dataset file has the digest.")
            _, stream = open_file(
                uow.session, UUID(str(stored["id"])), files=files, keyring=keyring
            )
            content = stream.read()
        rows = sd.decode_rows(content)
        verify_entry(planned, stored_sha256=str(stored["sha256"]), decoded_rows=len(rows))
        row_counts[planned.name] = len(rows)
        return rows

    def insertion_order(
        name: str, rows: Sequence[Mapping[str, Any]]
    ) -> tuple[Mapping[str, Any], ...]:
        """The dataset's rows referenced-first over its self-references, so each of those
        references is inserted with its row and never waits for an UPDATE the table's
        immutability class refuses; an inconsistent dataset is refused by name."""
        try:
            return sd.referenced_first(name, rows, inventory.dataset(name).self_references)
        except ValueError as error:
            raise not_loadable(f"the {name} dataset is inconsistent: {error}") from None

    def insert_row(
        session: Session, name: str, decoded: Mapping[str, Any]
    ) -> tuple[dict[str, Any], HeldFinalization | None]:
        """One copied row: typed, re-stamped, its deferred references held for the fixup step,
        a finalized row inserted in its initial status (R3)."""
        table = metadata.tables[f"erev.{name}"]
        dataset = inventory.dataset(name)
        values, held = coerce_row(
            table, decoded, tenant_id=load.sandbox_tenant_id, deferred=dataset.deferred
        )
        values, finalization = hold_finalization(name, values)
        session.execute(sa.insert(table).values(**values))
        if held:
            identity = {column: values[column] for column in sd.identity_columns(name)}
            held_rows.append((name, dataset.deferred, identity, held))
        return values, finalization

    def load_graphs(graph: sd.Graph, roots: Sequence[Mapping[str, Any]]) -> None:
        """APPROVAL-UNIQUE-1 (Codex 1739 §1; D-98 137 amendment 5): the root's dependants are read
        now and every graph — root, its steps, its decisions — loads root by root in the
        registry's chronological order, finalized (R3) before the next root inserts, so two
        completed requests of one subject are never PENDING together
        (``ux_approval_request__pending_subject``)."""
        dependant_rows = {
            name: read_rows(plan_by_name[name]) if name in plan_by_name else ()
            for name, _ in graph.dependants
        }
        graph_loaded.update(name for name, _ in graph.dependants)
        typed_roots = [
            coerce_row(
                metadata.tables[f"erev.{graph.root}"], row, tenant_id=load.sandbox_tenant_id
            )[0]
            for row in roots
        ]
        typed_dependants = {
            name: [
                coerce_row(metadata.tables[f"erev.{name}"], row, tenant_id=load.sandbox_tenant_id)[
                    0
                ]
                for row in rows
            ]
            for name, rows in dependant_rows.items()
        }
        try:
            batches = graph_batches(graph, typed_roots, typed_dependants)
        except ValueError as error:
            raise not_loadable(f"the {graph.root} graphs are inconsistent: {error}") from None
        decoded_roots = {UUID(str(row["id"])): row for row in roots}
        decoded_dependants = {
            name: {UUID(str(row["id"])): row for row in rows}
            for name, rows in dependant_rows.items()
        }
        for batch in batches:
            root_id = UUID(str(batch.root["id"]))
            with copy_step(f"graph-{root_id}", f"the {graph.root} graph {root_id}") as session:
                held: list[HeldFinalization] = []
                _, finalization = insert_row(session, graph.root, decoded_roots[root_id])
                if finalization is not None:
                    held.append(finalization)
                for name, _ in graph.dependants:
                    for typed in batch.dependants[name]:
                        _, finalization = insert_row(
                            session, name, decoded_dependants[name][UUID(str(typed["id"]))]
                        )
                        if finalization is not None:
                            held.append(finalization)
                for table_name in sd.FINALIZATION_ORDER:
                    for held_row in held:
                        if held_row.table == table_name:
                            apply_finalization(session, held_row)
            beat()
        # the held rows of OTHER tables waiting for this graph's datasets (MEMBERSHIP-1)
        finalize_after(graph.root)
        for name, _ in graph.dependants:
            finalize_after(name)

    def load_component(component: sd.Component) -> None:
        """05 SBX-04 rev 1.50 (supervisor ruling R-43 (b)): the tables of a component load
        together, here, at the position of its first table — every row AFTER the rows it names
        (``sd.component_order``), the stream in its source ``record_seq`` order, in ONE copy-phase
        transaction. An event therefore arrives with the estimate version or the manual
        adjustment it names: ``contract_event`` is IM-A, so no fixup UPDATE could restore the
        reference. An inconsistent component is refused by name."""
        member_rows = {
            name: read_rows(plan_by_name[name]) for name in component.tables if name in plan_by_name
        }
        component_loaded.update(component.tables)
        try:
            ordered = sd.component_order(
                component, member_rows, sd.component_references(inventory, component)
            )
        except ValueError as error:
            raise not_loadable(f"the {component.name} component is inconsistent: {error}") from None
        if ordered:
            with copy_step(
                f"load-{component.name}", f"the copy of the {component.name} component"
            ) as session:
                for name, decoded in ordered:
                    _, finalization = insert_row(session, name, decoded)
                    if finalization is not None:
                        held_finalizations.append(finalization)
        for name in component.tables:
            finalize_after(name)
        beat()

    def settle_memberships() -> None:
        """MEMBERSHIP-REFUSAL-1 (Codex 1824 §1): a supported refusal after the membership load
        applies the held final statuses of the non-kernel rows (the suspended / removed members
        inserted ACTIVE for their historical decisions) before the refusal returns, so no copied
        member is left ACTIVE behind a refused load; a held row whose insert never committed is
        matched by nothing (``WHERE status = initial``) and is simply dropped."""
        due = [h for h in held_finalizations if not sd.FINALIZATIONS[h.table].kernel]
        if not due:
            return
        with copy_step(
            "settle-memberships", "the settlement of the held membership statuses"
        ) as session:
            for held_row in due:
                apply_finalization(session, held_row)
        for held_row in due:
            held_finalizations.remove(held_row)

    plan_by_name = {planned.name: planned for planned in plan.datasets}
    graph_loaded: set[str] = set()
    component_loaded: set[str] = set()
    try:
        for planned in plan.datasets:
            if planned.name in graph_loaded:
                continue  # loaded with its root's graphs
            if planned.name in component_loaded:
                continue  # loaded with its component, at the component's first table
            component = sd.COMPONENTS.get(planned.name)
            if component is not None:
                load_component(component)
                continue
            rows = read_rows(planned)
            if planned.row_count == 0:
                graph = sd.GRAPHS.get(planned.name)
                if graph is not None:
                    load_graphs(graph, ())  # dependants of a root without rows: none allowed
                finalize_after(planned.name)
                continue
            if not planned.load_rows:
                replay_source[planned.name] = rows  # REPLAY_REFERENCE: the period replay's source
                continue
            graph = sd.GRAPHS.get(planned.name)
            if graph is not None:
                load_graphs(graph, rows)
                continue
            ordered = insertion_order(planned.name, rows)
            with copy_step(f"load-{planned.name}", f"the copy of {planned.name}") as session:
                for decoded in ordered:
                    _, finalization = insert_row(session, planned.name, decoded)
                    if finalization is not None:
                        held_finalizations.append(finalization)
            finalize_after(planned.name)
            beat()
    except Problem:
        settle_memberships()  # the original refusal is preserved and re-raised
        raise
    if held_finalizations:  # a FINALIZATIONS rule whose `after` dataset the manifest never names
        settle_memberships()
        raise RuntimeError(
            "finalizations never applied: "
            + ", ".join(sorted({h.table for h in held_finalizations}))
        )
    # fixup-deferred-references: the last transaction of the copy phase
    if held_rows:
        with copy_step("fixup", "the fixup of the deferred references") as session:
            for name, _deferred, identity, held in held_rows:
                table = metadata.tables[f"erev.{name}"]
                statement = sa.update(table).values(**held)
                for key, value in identity.items():
                    statement = statement.where(table.c[key] == value)
                session.execute(statement.where(table.c.tenant_id == load.sandbox_tenant_id))
    beat()

    # 4. the target: under the requesting user's SOURCE context (04 rev 1.56).
    with tenant_session(
        DbContext(tenant_id=source_id, user_id=load.requested_by, entity_scope="*")
    ) as session:
        jc.enlist(session)  # 05 JOB-06 rev 1.200: a transaction of the load's job
        tx.apply(
            session,
            "tenant_snapshot",
            snapshot_id,
            to_status=None,
            set_values={"target_tenant_id": load.sandbox_tenant_id},
        )
    beat()

    # 5a. the period replay plan over the TYPED reference rows (REPLAY-2), validated and checked
    # against the exported end state BEFORE the recompute and before any period write; an
    # inconsistent export is refused by name.
    references = typed_references(replay_source, tenant_id=load.sandbox_tenant_id)
    try:
        prepared = sandbox_periods.prepare(references)
    except ValueError as error:
        raise not_loadable(f"the replay reference datasets are inconsistent: {error}") from None
    beat()
    # 5a'. the period-ready precondition of the recompute (05 SBX-04: open periods → recompute →
    # close replay; Codex 1713 §3 R1): every source period state is created `future` and every
    # `future → open` of the plan replays NOW, through the governed DB-07 path as the requesting
    # user's copied membership — the closing / lock steps wait until the groups are recomputed.
    actor = sandbox_actor(load.sandbox_tenant_id, load.requested_by, at=now)
    period_replay = sandbox_periods.Replay(
        prepared, runtime=runtime, actor=actor, request_prefix=f"job-{jc.job_id}", beat=beat
    )
    period_replay.open_periods()

    # 5b. recompute every group (MIGRATION trigger), one transaction each, within the budget —
    # keeping, per (group, book) the recompute writes a version for, the hash SBX-05 compares
    # for a first computation: the sandbox's OUTPUT under the source computation's input hash.
    # Only the recompute holds the output (the stored rows keep its hash), so the source's
    # versions are read first.
    with jc.unit_of_work() as uow:
        # per group, its FIRST succeeded computation: the one whose bundle had no previous stream
        # heads and nothing posted (`bundles._previous_heads` orders the same way)
        first_computation: dict[UUID, UUID] = {}
        for group, computation_id in uow.session.execute(
            sa.select(contract_computation.c.combination_group_id, contract_computation.c.id)
            .where(
                contract_computation.c.tenant_id == source_id,
                contract_computation.c.status == ComputationStatus.SUCCEEDED.value,
            )
            .order_by(contract_computation.c.created_at, contract_computation.c.id)
        ):
            first_computation.setdefault(UUID(str(group)), UUID(str(computation_id)))
        source_versions = [
            sx.SourceVersion(
                combination_group_id=UUID(str(r["combination_group_id"])),
                book_code=str(r["book_code"]),
                version_no=int(r["version_no"]),
                known_at=r["known_at"],
                output_sha256=str(r["output_sha256"]),
                input_sha256=str(r["input_sha256"]),
                version_id=UUID(str(r["id"])),
                first_computation=(
                    first_computation.get(UUID(str(r["combination_group_id"])))
                    == UUID(str(r["contract_computation_id"]))
                ),
            )
            for r in uow.session.execute(
                sa.select(
                    contract_version.c.id,
                    contract_version.c.contract_computation_id,
                    contract_version.c.combination_group_id,
                    contract_version.c.book_code,
                    contract_version.c.version_no,
                    contract_version.c.known_at,
                    contract_version.c.output_sha256,
                    contract_computation.c.input_sha256,
                )
                .join(
                    contract_computation,
                    sa.and_(
                        contract_computation.c.tenant_id == contract_version.c.tenant_id,
                        contract_computation.c.id == contract_version.c.contract_computation_id,
                    ),
                )
                .where(contract_version.c.tenant_id == source_id)
            ).mappings()
        ]
    expected = sx.latest_as_of(source_versions, plan.known_at)
    comparable: dict[tuple[UUID, str], str] = {}
    run = computation.default_engine()
    started = jc.clock.now()  # the injected clock (DG-ARC-05), never the wall or monotonic clock
    with system_unit_of_work(
        runtime, sandbox_principal, request_id=f"job-{jc.job_id}-groups"
    ) as uow:
        group_ids = [
            UUID(str(g))
            for g in uow.session.execute(
                sa.select(combination_group.c.id)
                .where(combination_group.c.tenant_id == load.sandbox_tenant_id)
                .order_by(combination_group.c.id)
            ).scalars()
        ]
    recomputed = 0
    outcomes: dict[UUID, str | None] = {}  # per group: the computation status the engine stored
    for index, group_id in enumerate(group_ids):
        if (jc.clock.now() - started).total_seconds() > budget_seconds:
            raise budget_exceeded(group_ids[index:])
        with system_unit_of_work(
            runtime, sandbox_principal, request_id=f"job-{jc.job_id}-recompute-{group_id}"
        ) as uow:
            # No `job_id`: the load job is a row of the SOURCE tenant, and a sandbox row cannot
            # name it (04 NC-06 — `fk_contract_computation__job` is `(tenant_id, job_id)`); the
            # MIGRATION trigger and the request id `job-<load job>-recompute-<group>` of the
            # computation's audit event mark it as this load's recompute.
            engine, outputs = _kept(run)
            outcome = compute_job.compute_group(
                uow, group_id, trigger=ComputationTrigger.MIGRATION, engine=engine
            )
            uow.commit()
        outcomes[group_id] = None if outcome.status is None else outcome.status.value
        if outcome.status is ComputationStatus.SUCCEEDED:
            recomputed += 1  # a QUARANTINED, FAILED or deferred group is NOT a recompute (R1)
            comparable.update(sx.comparable_hashes(group_id, outputs[-1], expected))
        beat()
    not_recomputed = sorted(
        (g for g, status in outcomes.items() if status != ComputationStatus.SUCCEEDED.value),
        key=str,
    )

    # 5c. replay the source's period states and locks through the close domain's governed
    # commands as the requesting user's copied membership (PERIOD-1, LOCK-3; D-98 137 (3)).
    period_replay.close_periods()
    replayed = period_replay.result()
    blocked: list[BlockedPeriod] = list(replayed.blocked)

    # 6. verify (05 SBX-05 rev 1.50): per (group, book), the source's latest version as of
    # known_at against the sandbox's. The hash comparison pairs the two sides and finds the
    # one-sided pairs; the MONETARY STATE of every pair present on both sides is read from the
    # stored rows of the two versions, pair by pair, and `sx.judge` puts the two together. The
    # source is read in its own context, the sandbox in its own.
    with (
        jc.unit_of_work() as source_uow,
        system_unit_of_work(
            runtime, sandbox_principal, request_id=f"job-{jc.job_id}-verify"
        ) as sandbox_uow,
    ):
        sandbox_versions: dict[tuple[UUID, str], tuple[int, str, UUID]] = {}
        for r in sandbox_uow.session.execute(
            sa.select(
                contract_version.c.id,
                contract_version.c.combination_group_id,
                contract_version.c.book_code,
                contract_version.c.version_no,
                contract_version.c.output_sha256,
            ).where(contract_version.c.tenant_id == load.sandbox_tenant_id)
        ).mappings():
            pair = (UUID(str(r["combination_group_id"])), str(r["book_code"]))
            current = sandbox_versions.get(pair)
            if current is None or int(r["version_no"]) > current[0]:
                sandbox_versions[pair] = (
                    int(r["version_no"]),
                    str(r["output_sha256"]),
                    UUID(str(r["id"])),
                )
        facts: dict[tuple[UUID, str], sx.PairFacts] = {}
        for pair in sorted(set(expected) & set(sandbox_versions), key=lambda k: (str(k[0]), k[1])):
            source_version = expected[pair]
            if source_version.version_id is None:
                continue  # cannot be read: the hash comparison alone speaks for the pair
            facts[pair] = sx.PairFacts(
                first_computation=source_version.first_computation,
                difference=sx.first_difference(
                    sx.monetary_state(
                        _monetary_rows(source_uow.session, source_id, source_version.version_id)
                    ),
                    sx.monetary_state(
                        _monetary_rows(
                            sandbox_uow.session, load.sandbox_tenant_id, sandbox_versions[pair][2]
                        )
                    ),
                ),
            )
            beat()
    report_of = sx.compare_determinism(
        source_versions,
        # a stored version the recompute kept no output for cannot be compared by hash: its raw
        # hash never equals the source's, so a first computation is reported rather than passed
        {k: comparable.get(k, v[1]) for k, v in sandbox_versions.items()},
        plan.known_at,
    )
    findings = sx.judge(report_of, facts)
    hashes = {(m.combination_group_id, m.book_code): m for m in report_of.mismatches}
    report = LoadReport(
        sandbox_tenant_id=load.sandbox_tenant_id,
        source_tenant_id=source_id,
        tenant_snapshot_id=snapshot_id,
        known_at=plan.known_at,
        loaded_at=jc.clock.now(),
        row_counts=row_counts,
        groups_recomputed=recomputed,
        compared=report_of.compared,
        mismatches=tuple(
            {
                "combination_group_id": str(f.combination_group_id),
                "book_code": f.book_code,
                # which comparison found it, the first differing member and its two values
                "comparison": f.comparison,
                "member": f.member,
                "source": None if f.source is None else str(f.source),
                "sandbox": None if f.sandbox is None else str(f.sandbox),
                # the source version's stored hash and the input hash of its computation
                "source_sha256": _source_of(expected, f, "output_sha256"),
                "source_input_sha256": _source_of(expected, f, "input_sha256"),
                # the sandbox version's own stored hash, and — where the hashes were unequal —
                # the hash compared with `source_sha256`: the same output under
                # `source_input_sha256`
                "sandbox_sha256": _stored_of(sandbox_versions, f),
                "comparable_sha256": _comparable_of(hashes, f),
                "sandbox_computation": outcomes.get(f.combination_group_id),
            }
            for f in findings
        ),
        blocked_periods=tuple(blocked),
        first_computations=sum(1 for known in facts.values() if known.first_computation),
    )
    content = report_bytes(report)

    # 6b. the load report (AUDIT_DIGEST), the load's summary event in the sandbox (05 SBX-06 rev
    # 1.34: written after the verification, the last audit event of the load there but for the
    # warning items raised beside it in this transaction), the exception items.
    with jc.unit_of_work() as uow:
        source_head = uow.session.execute(
            sa.select(audit_chain_head.c.last_chain_seq).where(
                audit_chain_head.c.tenant_id == source_id
            )
        ).scalar_one_or_none()
    with system_unit_of_work(
        runtime, sandbox_principal, request_id=f"job-{jc.job_id}-report"
    ) as uow:
        stored_report = put_file(
            uow,
            purpose=FilePurpose(LOAD_REPORT_PURPOSE),
            stream=io.BytesIO(content),
            original_filename=f"sandbox-load-{snapshot_id}.json",
            media_type="application/json",
        )
        report_file_id = UUID(str(stored_report.row["id"]))
        report_sha256 = str(stored_report.row["sha256"])
        # 05 SBX-04 rev 1.64: the sandbox becomes a workspace here, with its summary event —
        # until this transaction commits it is SUSPENDED: not selectable and closed to commands.
        uow.session.execute(
            sa.update(tenant)
            .where(
                tenant.c.id == load.sandbox_tenant_id,
                tenant.c.status == TenantStatus.SUSPENDED.value,
            )
            .values(
                status=TenantStatus.ACTIVE.value,
                updated_at=uow.now,
                updated_by=None,
                updated_by_kind=PrincipalKind.SYSTEM.value,
            )
        )
        uow.audit(
            action=ACTION_LOADED,
            object_type="tenant_snapshot",
            object_id=snapshot_id,
            before=None,
            after={
                "sandbox_tenant_id": str(load.sandbox_tenant_id),
                "status": TenantStatus.ACTIVE.value,
            },
            detail={
                "source_tenant_id": str(source_id),
                "known_at": plan.known_at.isoformat(),
                "manifest_sha256": str(row["manifest_sha256"]),
                "row_counts": dict(sorted(row_counts.items())),
                "source_audit_chain_head": source_head,
                "load_report_file_id": str(report_file_id),
                "load_report_sha256": report_sha256,
                "derived_mismatches": report.derived_mismatches,
                "blocked_periods": [str(b.period_state_id) for b in blocked],
                "audit_history_carried": False,
            },
        )
        if report.derived_mismatches:
            raise_exception_item(
                uow,
                source=ExceptionSource.ENGINE,
                code=EXCEPTION_DETERMINISM,
                severity=ExceptionSeverity.WARNING,
                message=(
                    f"{report.derived_mismatches} of {report.compared} (group, book) pairs "
                    "recomputed to a result that differs from the source version's; the first: "
                    f"{_named(findings[0])}"
                    + (
                        f"; {len(not_recomputed)} group(s) did not recompute "
                        "(QUARANTINED, FAILED or deferred)."
                        if not_recomputed
                        else "."
                    )
                ),
                dedupe=f"snapshot:{snapshot_id}:determinism",
            )
        for b in blocked:
            raise_exception_item(
                uow,
                source=ExceptionSource.ENGINE,
                code=EXCEPTION_REPLAY_BLOCKED,
                severity=ExceptionSeverity.WARNING,
                message=(
                    f"period {b.period_id} ({b.book_code}) could not replay {b.attempted}: "
                    f"{b.reason}; it stays {b.reached}."
                ),
                dedupe=f"snapshot:{snapshot_id}:replay:{b.period_state_id}",
                entity_id=b.entity_id,
                period_id=b.period_id,
            )
        uow.commit()
    # 6c. the source: completion event and the requester's notification.
    with jc.unit_of_work() as uow:
        uow.audit(
            action=ACTION_RESTORED if load.restore else ACTION_LOADED,
            object_type="tenant_snapshot",
            object_id=snapshot_id,
            before=None,
            after={"target_tenant_id": str(load.sandbox_tenant_id)},
            detail={
                "tenant_snapshot_id": str(snapshot_id),
                "sandbox_tenant_id": str(load.sandbox_tenant_id),
                "derived_mismatches": report.derived_mismatches,
                "blocked_periods": [str(b.period_state_id) for b in blocked],
                "load_report_sha256": report_sha256,
            },
        )
        if (report.derived_mismatches or blocked) and requester_membership is not None:
            notify(
                uow,
                recipient_membership_ids=[UUID(str(requester_membership))],
                kind=NotificationKind.EXCEPTION_ASSIGNED,
                title="Sandbox load finished with findings",
                body=(
                    f"{report.derived_mismatches} determinism mismatch(es), "
                    f"{len(blocked)} blocked period replay(s); see the load report."
                ),
                subject_type="tenant_snapshot",
                subject_id=snapshot_id,
            )
        uow.commit()
    return Loaded(
        load.sandbox_tenant_id,
        report_file_id,
        report_sha256,
        report.derived_mismatches,
        len(blocked),
        recomputed,
        sum(row_counts.values()),
        groups_not_recomputed=len(not_recomputed),
    )


def select_snapshot(table: sa.Table, snapshot_id: UUID) -> sa.Select[Any]:
    return sa.select(table).where(table.c.id == snapshot_id)


def select_file_by_digest(sha256: str, purpose: str) -> sa.Select[Any]:
    from erev_api.db.tables import file_object

    return sa.select(file_object).where(
        file_object.c.sha256 == sha256, file_object.c.purpose == purpose
    )


def rows_of(rows: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(rows)
