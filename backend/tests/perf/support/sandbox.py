"""The perf sandbox (dev-guide DG-PERF-02; 05 SBX-02 to SBX-07): the stored snapshot of
``perf-volume`` restored into a new ``perf-run-*`` tenant through ``run_inline`` — never
``perf-volume`` itself — with ``derived_mismatches = 0`` required of a load that recomputed
every contract group, in a sandbox that holds the source's contract events as of the cutoff."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from perf.support.rules import (
    EVENTS_COPIED_NOTE,
    EVENTS_NOT_COPIED_MESSAGE,
    NON_DETERMINISTIC_MESSAGE,
    NOT_RECOMPUTED_MESSAGE,
    PRIOR_ACTIVE_RESET_ABSENT_MESSAGE,
    PRIOR_ACTIVE_RESET_UNBOUND_MESSAGE,
    REQUESTER_MISSING_MESSAGE,
)
from perf.support.tenant import SnapshotFacts

SANDBOX_PREFIX: Final = "perf-run-"
# ``sandboxes.sandbox_code("perf-run-…")``: "sbx-" + the slug — the tenant codes of earlier runs.
SANDBOX_CODE_PREFIX: Final = "sbx-perf-run-"


class SandboxNotDeterministic(RuntimeError):
    """Raised with ``NON_DETERMINISTIC_MESSAGE`` when the load report counts mismatches."""


class SandboxNotVerified(RuntimeError):
    """Raised by name, with the counts, when a load proves nothing about the copy: a contract
    group it did not recompute, or a sandbox that does not hold the contract events of
    ``perf-volume`` as of the snapshot's cutoff (DG-PERF-02 (1), rev 1.243)."""


class RequesterMissing(RuntimeError):
    """Raised with ``REQUESTER_MISSING_MESSAGE``: the restore names no real requesting user."""


class PriorActiveSandbox(RuntimeError):
    """Raised by name BEFORE the restore when an earlier ``perf-run-*`` sandbox is still ACTIVE
    (05 SBX-07; D-98 148 AMENDMENT 4)."""


def require_requester(user_id: UUID | None) -> UUID:
    """The requesting user of the restore (``load.requested_by``): the perf-controller's
    ``app_user.id`` holding an ACTIVE membership of ``perf-volume``. The loader refuses ``None``
    with 403 ``SANDBOX_ACTOR_REQUIRED`` (``sandboxes.load_sandbox``); the harness refuses it
    earlier, by name, and never invents an actor (Codex 2353 PRF3-RESTORE-ACTOR-1)."""
    if user_id is None:
        raise RequesterMissing(REQUESTER_MISSING_MESSAGE)
    return user_id


def prior_active_refusal(active_codes: Sequence[str], *, reset_available: bool) -> str | None:
    """The governed A4 condition, checked BEFORE the restore and before any process starts: an
    EXISTING ACTIVE ``perf-run-*`` sandbox requires ``SANDBOX_RESET`` first. ``None`` when no
    such sandbox exists (a first run restores without it); otherwise the refusal message — the
    handler is absent on main, or present but not yet called by the harness (the PRF-4
    follow-up binds the call to the landed handler's params rather than guessing them)."""
    if not any(code.startswith(SANDBOX_CODE_PREFIX) for code in active_codes):
        return None
    return (
        PRIOR_ACTIVE_RESET_UNBOUND_MESSAGE if reset_available else PRIOR_ACTIVE_RESET_ABSENT_MESSAGE
    )


@dataclass(frozen=True, slots=True)
class RestoredSandbox:
    sandbox_tenant_id: UUID
    snapshot_id: UUID
    derived_mismatches: int
    groups_recomputed: int
    notes: tuple[str, ...] = ()


def with_note(restored: RestoredSandbox, note: str) -> RestoredSandbox:
    return RestoredSandbox(
        restored.sandbox_tenant_id,
        restored.snapshot_id,
        restored.derived_mismatches,
        restored.groups_recomputed,
        (*restored.notes, note),
    )


def require_deterministic(counts: Mapping[str, Any]) -> int:
    """The ``derived_mismatches`` count of a load outcome; > 0 fails (SBX-05; DG-PERF-02).

    A load that compared nothing proves nothing, so every contract group must have been
    recomputed as well: ``groups_not_recomputed`` above 0 — a recompute that ended FAILED or
    QUARANTINED, or was deferred — fails by name with the two counts (rev 1.243). Measured
    2026-10-02 in the story of the perf seed: a copy cut before every event ended SUCCEEDED
    with 0 mismatches, 0 groups recomputed and 10 not recomputed — the source had no version
    as of that cutoff either, so nothing differed."""
    mismatches = int(counts.get("derived_mismatches", 0))
    if mismatches > 0:
        raise SandboxNotDeterministic(NON_DETERMINISTIC_MESSAGE)
    left = int(counts.get("groups_not_recomputed", 0))
    if left > 0:
        raise SandboxNotVerified(
            NOT_RECOMPUTED_MESSAGE.format(
                recomputed=int(counts.get("groups_recomputed", 0)), not_recomputed=left
            )
        )
    return mismatches


def require_events_copied(*, source: int, sandbox: int, known_at: datetime) -> int:
    """The sandbox holds the contract events ``perf-volume`` recorded at or before the
    snapshot's ``known_at`` — the two counts are equal and not zero — or the run refuses by
    name, stating both and the cutoff: a snapshot cut before its events is a copy of nothing
    (rev 1.243). Returns the count."""
    if source != sandbox or sandbox == 0:
        raise SandboxNotVerified(
            EVENTS_NOT_COPIED_MESSAGE.format(
                sandbox=sandbox, source=source, known_at=known_at.isoformat()
            )
        )
    return sandbox


def verify_copy(
    restored: RestoredSandbox,
    *,
    source_tenant_id: UUID,
    known_at: datetime,
    events: Callable[[UUID, datetime | None], int],
) -> RestoredSandbox:
    """After the restore and before anything is appended to the sandbox: ``events`` counts the
    contract events of a tenant, up to a record time when one is given — those of
    ``perf-volume`` as of the snapshot's ``known_at`` and those the sandbox holds
    (``require_events_copied``). The count reaches the report as a note."""
    copied = require_events_copied(
        source=events(source_tenant_id, known_at),
        sandbox=events(restored.sandbox_tenant_id, None),
        known_at=known_at,
    )
    return with_note(restored, EVENTS_COPIED_NOTE.format(count=copied))


def restore_params(snapshot: SnapshotFacts, load_params: Mapping[str, Any]) -> dict[str, Any]:
    """The TENANT_SNAPSHOT job params: the snapshot's own ``tenant_snapshot_id``, ``known_at`` (RFC
    3339 with offset) and ``purpose`` — every member ``snapshot_job.parse_params`` requires (Codex
    2316 R2 (b)) — plus the ``load`` entry of ``sandboxes.load_params_of(restore=True)``."""
    known_at = snapshot.known_at
    if known_at.tzinfo is None:
        raise ValueError("the snapshot's known_at must carry a UTC offset")
    return {
        "tenant_snapshot_id": str(snapshot.snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": snapshot.purpose,
        **load_params,
    }


def restore_seed(
    run: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    *,
    snapshot: SnapshotFacts,
    sandbox_tenant_id: UUID,
    load_params: Mapping[str, Any],
) -> RestoredSandbox:
    """Run the restore (``run`` wraps ``run_inline(JobKind.TENANT_SNAPSHOT, params, …)`` and
    returns the outcome's ``result``) and require a deterministic copy in which every contract
    group was recomputed (``require_deterministic``)."""
    result = run(restore_params(snapshot, load_params))
    counts = result.get("counts", {})
    mismatches = require_deterministic(counts)
    return RestoredSandbox(
        sandbox_tenant_id=UUID(str(result.get("sandbox_tenant_id", sandbox_tenant_id))),
        snapshot_id=snapshot.snapshot_id,
        derived_mismatches=mismatches,
        groups_recomputed=int(counts.get("groups_recomputed", 0)),
    )
