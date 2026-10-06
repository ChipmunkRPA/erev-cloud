"""Sidecar lifecycle over a ``VersionedFileStore``: KEY-04 rewrap and PRV-07 shred (05 SAR-07,
PRV-06, PRV-07, OPR-10; hosted runtime contract §"GCS immutable file and wrapped-key contract"
and §"Shredding and retained digests").

Rewrap keeps the data key and replaces only the live sidecar generation by compare-and-swap; on a
conflict it re-reads and re-evaluates, and it never creates a sidecar, so a rewrap racing a shred
cannot restore access. Shred writes the durable marker ``<storage_key>.dek.shredded`` first, then
deletes every retained generation of the sidecar by generation until none is live, and reports the
soft-deleted generations that stay recoverable until their hard-delete time: erasure is complete
only once backup and soft-delete retention lapse (PRV-07, OPR-10). The immutable payload and the
``file_object`` row are never touched (D-43).

Concurrency contract (Codex probe F04): every writer of a storage key takes the transaction-scoped
PostgreSQL advisory lock ``lock_storage_key`` before touching the key's objects. ``put_file`` takes
it inside its unit of work; ``rewrap_sidecar`` and ``shred_sidecar`` take it when the caller passes
its ``session`` — for a shred the transaction that completes it, after the decision's own has
committed (``domain.platform.privacy.complete_shred``; 05 PRV-07 b rev 1.171: nothing here runs
before the shred is durably decided). Generation-conditioned writes and the marker re-check
after a sidecar write are the second line of defence for a writer that bypasses the lock.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import Connection
from sqlalchemy.orm import Session

from erev_api.auth.keyring import KeyRing
from erev_api.files.store import (
    SHRED_MARKER_BYTES,
    FileShredded,
    GenerationConflict,
    ObjectVersion,
    VersionedFileStore,
    encryption_context,
    key_tenant,
    lock_storage_key,
    shred_marker_key,
    sidecar_key,
    storage_key_lock_id,
)
from erev_api.logging import get_logger, register_logger_fields

# Deleting generations can race a concurrent rewrap that lands between two passes.
MAX_SHRED_PASSES: Final = 5
_LOGGER: Final = "erev_api.files.lifecycle"

register_logger_fields(_LOGGER, ("storage_key", "generation", "generations", "retained"))


@dataclass(frozen=True, slots=True)
class RewrapResult:
    storage_key: str
    previous_generation: int
    generation: int
    changed: bool  # False when a concurrent rewrap of the same data key already won


@dataclass(frozen=True, slots=True)
class ShredReport:
    storage_key: str
    marker_created: bool  # False when an earlier shred had already left the marker
    deleted_generations: tuple[int, ...]
    retained: tuple[ObjectVersion, ...]  # soft-deleted generations still recoverable
    irreversible_after: datetime | None  # the latest hard-delete time, None without retention
    live_generation: int  # always 0 on return
    # The marker's own instant in the store: written once, by the first shred of the key, so
    # it says when the destruction began also to a run that finds the key already destroyed
    # (05 PRV-07 b rev 1.171). None for a store that keeps no instant of its objects.
    marker_at: datetime | None = None


def rewrap_sidecar(
    files: VersionedFileStore,
    keyring: KeyRing,
    storage_key: str,
    *,
    session: Session | Connection | None = None,
) -> RewrapResult:
    """Re-wrap the file's data key under the current KEK, replacing only the live sidecar
    generation the key was read from (compare-and-swap). ``session`` takes the per-key advisory
    lock first (the command's transaction), which every writer of the key honours.

    The associated data names the workspace of the STORAGE KEY (05 SAR-07, SBX-03 rev 1.196;
    item SBX-FILE-READ-1) and is read from the key, not handed in: a sandbox copy's row carries
    its source's key, and a caller that passed the row's workspace would fail on every copied
    file (measured: ``InvalidTag`` with the sandbox's id, a rewrap with production's). A key of
    another form names no workspace and is refused."""
    stored_by = key_tenant(storage_key)
    if stored_by is None:
        raise ValueError("a storage key of another form names no workspace to rewrap under")
    if session is not None:
        lock_storage_key(session, storage_key)
    key = sidecar_key(storage_key)
    context = encryption_context(stored_by, storage_key)
    if files.exists(shred_marker_key(storage_key)):
        raise FileShredded(storage_key)
    generation = files.live_generation(key)
    if generation == 0:
        raise FileNotFoundError(key)
    dek = keyring.file_key(files.read_generation(key, generation), context=context)
    fresh = keyring.wrap_file_key(dek, context=context)
    try:
        new_generation = files.replace(key, generation, io.BytesIO(fresh))
    except GenerationConflict:
        winner = files.live_generation(key)
        if winner == 0:
            raise FileShredded(storage_key) from None
        # Another rewrap won; it must carry the same data key, or the store is inconsistent.
        if keyring.file_key(files.read_generation(key, winner), context=context) != dek:
            raise GenerationConflict(f"{key} was replaced with a different data key") from None
        return RewrapResult(storage_key, generation, winner, changed=False)
    if files.exists(shred_marker_key(storage_key)):
        # A shred began after the marker check above; the generation this rewrap created must not
        # outlive it. The marker is durable, so the shred's own passes delete it too.
        files.delete_generation(key, new_generation)
        raise FileShredded(storage_key)
    get_logger(_LOGGER).info(
        "files.sidecar_rewrapped", storage_key=storage_key, generation=new_generation
    )
    return RewrapResult(storage_key, generation, new_generation, changed=True)


def shred_sidecar(
    files: VersionedFileStore, storage_key: str, *, session: Session | Connection | None = None
) -> ShredReport:
    """PRV-07 (b): destroy every retained generation of the sidecar and leave the marker.

    Idempotent: a repeated shred finds the marker, deletes nothing and reports the same residual
    retention and the marker's own instant. Raises ``GenerationConflict`` when a generation is
    still live after the passes — the marker stands then, and the next shred of the key deletes
    what is left.
    ``session`` takes the per-key advisory lock first (the transaction that completes a decided
    shred), so an upload or rewrap of the same key waits until the completion has committed.
    """
    if session is not None:
        lock_storage_key(session, storage_key)
    key = sidecar_key(storage_key)
    marker = shred_marker_key(storage_key)
    marker_created = not files.exists(marker)
    files.put(marker, io.BytesIO(SHRED_MARKER_BYTES))  # create-if-absent; an existing marker stays
    deleted: list[int] = []
    for _ in range(MAX_SHRED_PASSES):
        present = [version for version in files.versions(key) if not version.soft_deleted]
        if not present:
            break
        for version in present:
            files.delete_generation(key, version.generation)
            deleted.append(version.generation)
    live = files.live_generation(key)
    if live != 0:
        raise GenerationConflict(f"{key} is still live at generation {live} after shredding")
    retained = tuple(version for version in files.versions(key) if version.soft_deleted)
    marker_at = next(
        (version.created_at for version in files.versions(marker) if version.live), None
    )
    irreversible_after = max(
        (version.hard_delete_at for version in retained if version.hard_delete_at is not None),
        default=None,
    )
    get_logger(_LOGGER).info(
        "files.sidecar_shredded",
        storage_key=storage_key,
        generations=len(deleted),
        retained=len(retained),
    )
    return ShredReport(
        storage_key=storage_key,
        marker_created=marker_created,
        deleted_generations=tuple(deleted),
        retained=retained,
        irreversible_after=irreversible_after,
        live_generation=live,
        marker_at=marker_at,
    )


__all__ = [
    "MAX_SHRED_PASSES",
    "RewrapResult",
    "ShredReport",
    "lock_storage_key",
    "rewrap_sidecar",
    "shred_sidecar",
    "storage_key_lock_id",
]
