"""SCH-14 ``file_orphan_sweep`` (05 §SCH row 973; OPR-13; record §4.22 (c); D-98 138).

Daily at 03:40 UTC the worker deletes file-store objects at least 24 hours old (inclusive:
age >= ``MAX_AGE`` by the store object's own timestamp; 05 SCH-14 rev 1.21, D-98 138-A2) that no
``file_object`` row references. OPR-13 orders the writes — the object (and its ``.dek`` sidecar)
first, the ``file_object`` row's transaction after — so a failed transaction leaves an orphan and a
committed row always has its bytes. The sweep therefore:

- lists the whole store through ``SweepableFileStore.list_objects`` (``LocalFileStore`` and
  ``GcsFileStore``); a store without the listing refuses by name (``SweepUnsupported``);
- measures the age from the STORE object's own timestamp (mtime; ``blob.updated``) against the
  worker clock — never from a database row — and takes only objects at least ``MAX_AGE`` old;
- treats keys by shape: ``<tenant_id>/<purpose>/<sha256>`` objects, their ``.dek`` sidecars
  (which follow their object; PRV-06), ``.dek.shredded`` markers (never deleted; PRV-07) and the
  local backend's ``.incoming/<uuid>`` partial spools (interrupted writes, swept apart);
- groups candidates by tenant prefix. RLS shows a session only its tenant's rows — "hidden rows are
  not evidence of absence" — so the reference re-check runs under the tenant scope derived from the
  key with the RLS the sweeper's SYSTEM-scoped tenant session has; a key whose tenant scope cannot
  be established (no three-segment shape, no UUID prefix, or a prefix that is not a tenant of the
  directory) is REPORTED, never deleted;
- re-checks each candidate under the existing storage-key boundary: ``reference_guard(tenant_id,
  key)`` holds ``files.store.lock_storage_key`` (the ``pg_advisory_xact_lock`` every writer path of
  a key takes) in the key's tenant session while the ``file_object`` row is re-read and, when
  absent, while the object and then its sidecar are deleted — so an upload of the same key cannot
  interleave; the delete is ``delete_generation`` addressed to the LISTED generation, so a newer
  generation written meanwhile is never touched (a generation conflict keeps the key and reports
  it); a ``.dek`` follows its object's verdict and is never independently an orphan — a sidecar
  whose object is absent is reported, not deleted;
- in ``dry_run`` reports every decision and deletes nothing.

Recording: an orphan has no ``file_object`` row, so no tenant audit event (subject-bound, IM-A)
can record its deletion and 04 names no ``file.*`` action for it. The record is the structured
log: ``file_orphan_sweep.deleted`` per deleted object, sidecar or partial, and one
``file_orphan_sweep.completed`` summary (listed / candidates / kept / deleted / reported / dry_run),
at WARNING when anything was deleted — the SCH-08 convention. A platform operations event for
these deletions is a named open item, not this task.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from erev_api.files.store import (
    INCOMING_DIR,
    SHRED_MARKER_SUFFIX,
    SIDECAR_SUFFIX,
    GenerationConflict,
    StoredObjectListing,
    SweepableFileStore,
)
from erev_api.jobs.context import JobRuntime
from erev_api.logging import get_logger, register_logger_fields

MAX_AGE: Final = timedelta(hours=24)  # 05 SCH-14 rev 1.21: at least 24 hours old (inclusive, >=)
REQUEST_ID: Final = "file-orphan-sweep"
MARKER_SUFFIX: Final = SIDECAR_SUFFIX + SHRED_MARKER_SUFFIX
_LOGGER: Final = "erev_api.files.sweep"

register_logger_fields(
    _LOGGER,
    (
        "backend",
        "storage_key",
        "generation",
        "updated_at",
        "tenant_id",
        "kind",
        "dry_run",
        "listed",
        "candidates",
        "deleted",
        "sidecars_deleted",
        "partials_deleted",
        "kept_referenced",
        "kept_young",
        "reported_unknown_tenant",
        "reported_conflicts",
        "reported_unaged",
        "reported_lonely_sidecars",
        "skipped_markers",
        "swept_at",
    ),
)

ReferenceGuard = Callable[[UUID, str], AbstractContextManager[bool]]
TenantKnown = Callable[[UUID], bool]


class SweepUnsupported(RuntimeError):
    """The store cannot list its objects, so nothing can be swept (refused by name)."""


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one sweep saw and did; every key is the storage key as listed."""

    backend: str
    swept_at: datetime
    dry_run: bool
    listed: int
    candidates: int
    deleted: tuple[str, ...] = ()
    sidecars_deleted: tuple[str, ...] = ()
    partials_deleted: tuple[str, ...] = ()
    kept_referenced: tuple[str, ...] = ()
    kept_young: tuple[str, ...] = ()
    reported_unknown_tenant: tuple[str, ...] = ()
    reported_conflicts: tuple[str, ...] = ()
    reported_unaged: tuple[str, ...] = ()  # the store gave no timestamp: never deleted
    reported_lonely_sidecars: tuple[str, ...] = ()  # a .dek without its object: never an orphan
    skipped_markers: tuple[str, ...] = ()


@dataclass(slots=True)
class _Tally:
    deleted: list[str] = field(default_factory=list)
    sidecars_deleted: list[str] = field(default_factory=list)
    partials_deleted: list[str] = field(default_factory=list)
    kept_referenced: list[str] = field(default_factory=list)
    kept_young: list[str] = field(default_factory=list)
    reported_unknown_tenant: list[str] = field(default_factory=list)
    reported_conflicts: list[str] = field(default_factory=list)
    reported_unaged: list[str] = field(default_factory=list)
    reported_lonely_sidecars: list[str] = field(default_factory=list)
    skipped_markers: list[str] = field(default_factory=list)


def _tenant_of(object_key: str) -> UUID | None:
    """The tenant of a ``<tenant_id>/<purpose>/<sha256>`` key; None for any other shape."""
    segments = object_key.split("/")
    if len(segments) != 3:
        return None
    try:
        return UUID(segments[0])
    except ValueError:
        return None


def sweep(
    store: SweepableFileStore,
    *,
    now: datetime,
    reference_guard: ReferenceGuard,
    tenant_known: TenantKnown,
    dry_run: bool = False,
    max_age: timedelta = MAX_AGE,
) -> SweepReport:
    """One sweep of ``store`` at ``now`` (the worker clock). ``reference_guard(tenant_id, key)``
    enters the key's boundary — the tenant session holding ``lock_storage_key`` — and yields
    whether a ``file_object`` row references the key; the deletions of that key happen inside the
    boundary. ``tenant_known`` answers whether a prefix is a tenant of the directory."""
    lister = getattr(store, "list_objects", None)
    if not callable(lister):
        raise SweepUnsupported(
            f"{type(store).__name__} has no list_objects; SCH-14 sweeps only a store that lists "
            "its objects (LocalFileStore, GcsFileStore)"
        )
    listings: tuple[StoredObjectListing, ...] = tuple(lister())
    logger = get_logger(_LOGGER)
    tally = _Tally()
    objects: dict[str, StoredObjectListing] = {}
    sidecars: dict[str, StoredObjectListing] = {}
    partials: list[StoredObjectListing] = []
    for listing in listings:
        key = listing.storage_key
        if key.startswith(f"{INCOMING_DIR}/"):
            partials.append(listing)
        elif key.endswith(MARKER_SUFFIX):
            tally.skipped_markers.append(key)  # PRV-07: the durable shred marker stays
        elif key.endswith(SIDECAR_SUFFIX):
            sidecars[key[: -len(SIDECAR_SUFFIX)]] = listing
        else:
            objects[key] = listing

    def age_reference(object_key: str) -> datetime | None:
        listing = objects.get(object_key) or sidecars.get(object_key)
        return listing.updated_at if listing is not None else None

    def delete(listing: StoredObjectListing, kind: str, tenant_id: UUID | None) -> bool:
        if not dry_run:
            try:
                store.delete_generation(listing.storage_key, listing.generation)
            except GenerationConflict:
                tally.reported_conflicts.append(listing.storage_key)
                return False
        logger.info(
            "file_orphan_sweep.deleted",
            backend=store.backend,
            storage_key=listing.storage_key,
            generation=listing.generation,
            updated_at=listing.updated_at.isoformat() if listing.updated_at else None,
            tenant_id=str(tenant_id) if tenant_id else None,
            kind=kind,
            dry_run=dry_run,
        )
        return True

    by_tenant: dict[UUID, list[str]] = {}
    for object_key in sorted(set(objects) | set(sidecars)):
        tenant_id = _tenant_of(object_key)
        if tenant_id is None:
            tally.reported_unknown_tenant.append(object_key)
            continue
        by_tenant.setdefault(tenant_id, []).append(object_key)
    candidates = 0
    for tenant_id, keys in sorted(by_tenant.items()):
        if not tenant_known(tenant_id):
            tally.reported_unknown_tenant.extend(keys)
            continue
        old: list[str] = []
        for object_key in keys:
            stamped = age_reference(object_key)
            if stamped is None:
                tally.reported_unaged.append(object_key)
            elif now - stamped >= max_age:
                old.append(object_key)
            else:
                tally.kept_young.append(object_key)
        if not old:
            continue
        for object_key in old:
            if object_key not in objects:
                # A .dek without its object follows the object's verdict — and there is none.
                tally.reported_lonely_sidecars.append(sidecars[object_key].storage_key)
                continue
            candidates += 1
            with reference_guard(tenant_id, object_key) as has_row:
                if has_row:
                    tally.kept_referenced.append(object_key)
                    continue
                if delete(objects[object_key], "object", tenant_id):
                    tally.deleted.append(object_key)
                    sidecar = sidecars.get(object_key)
                    if sidecar is not None and delete(sidecar, "sidecar", tenant_id):
                        tally.sidecars_deleted.append(sidecar.storage_key)
    remove_partial = getattr(store, "remove_partial", None)  # the local backend's spools only
    for listing in partials:
        if listing.updated_at is None:
            tally.reported_unaged.append(listing.storage_key)
        elif now - listing.updated_at >= max_age:
            candidates += 1
            if callable(remove_partial):
                if not dry_run:
                    remove_partial(listing.storage_key)
                logger.info(
                    "file_orphan_sweep.deleted",
                    backend=store.backend,
                    storage_key=listing.storage_key,
                    generation=listing.generation,
                    updated_at=listing.updated_at.isoformat(),
                    tenant_id=None,
                    kind="partial",
                    dry_run=dry_run,
                )
                tally.partials_deleted.append(listing.storage_key)
            else:
                tally.reported_conflicts.append(listing.storage_key)  # no way to remove it here
        else:
            tally.kept_young.append(listing.storage_key)
    report = SweepReport(
        backend=store.backend,
        swept_at=now,
        dry_run=dry_run,
        listed=len(listings),
        candidates=candidates,
        deleted=tuple(tally.deleted),
        sidecars_deleted=tuple(tally.sidecars_deleted),
        partials_deleted=tuple(tally.partials_deleted),
        kept_referenced=tuple(tally.kept_referenced),
        kept_young=tuple(tally.kept_young),
        reported_unknown_tenant=tuple(tally.reported_unknown_tenant),
        reported_conflicts=tuple(tally.reported_conflicts),
        reported_unaged=tuple(tally.reported_unaged),
        reported_lonely_sidecars=tuple(tally.reported_lonely_sidecars),
        skipped_markers=tuple(tally.skipped_markers),
    )
    summary = {
        "backend": report.backend,
        "dry_run": dry_run,
        "listed": report.listed,
        "candidates": report.candidates,
        "deleted": len(report.deleted),
        "sidecars_deleted": len(report.sidecars_deleted),
        "partials_deleted": len(report.partials_deleted),
        "kept_referenced": len(report.kept_referenced),
        "kept_young": len(report.kept_young),
        "reported_unknown_tenant": len(report.reported_unknown_tenant),
        "reported_conflicts": len(report.reported_conflicts),
        "reported_unaged": len(report.reported_unaged),
        "reported_lonely_sidecars": len(report.reported_lonely_sidecars),
        "skipped_markers": len(report.skipped_markers),
        "swept_at": now.isoformat(),
    }
    removed = report.deleted or report.sidecars_deleted or report.partials_deleted
    if removed and not dry_run:
        logger.warning("file_orphan_sweep.completed", **summary)
    else:
        logger.info("file_orphan_sweep.completed", **summary)
    return report


# -- the database-bound readers the worker composes (NOT RUN on the lane; record §4.22 (e)) --------


@contextmanager
def reference_guard(tenant_id: UUID, storage_key: str) -> Iterator[bool]:
    """The key's boundary in production: ONE read-only tenant session under the key's tenant scope
    (the RLS the SYSTEM-scoped session has), holding ``lock_storage_key`` for the transaction while
    the ``file_object`` row is re-read and — inside the ``with`` — while the caller deletes."""
    from sqlalchemy import select

    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import file_object
    from erev_api.files.store import lock_storage_key

    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        lock_storage_key(session, storage_key)
        row = session.scalar(
            select(file_object.c.id).where(file_object.c.storage_key == storage_key)
        )
        yield row is not None


def tenant_directory(*, request_id: str = REQUEST_ID) -> frozenset[UUID]:
    """Every tenant of the directory, whatever its status: a prefix outside it is never deleted."""
    from sqlalchemy import select

    from erev_api.db.session import platform_session
    from erev_api.db.tables import tenant

    with platform_session("tenant_directory", actor_user_id=None, request_id=request_id) as session:
        return frozenset(UUID(str(value)) for value in session.scalars(select(tenant.c.id)))


def run(runtime: JobRuntime, *, dry_run: bool = False) -> SweepReport:
    """The worker task body: the runtime's file store at the runtime clock, the tenant directory
    and the per-key reference guard under the storage-key lock."""
    if runtime.files is None:
        raise RuntimeError("this job runtime has no file store")
    known = tenant_directory()
    return sweep(
        runtime.files,  # type: ignore[arg-type]  # LocalFileStore / GcsFileStore list objects
        now=runtime.clock.now(),
        reference_guard=reference_guard,
        tenant_known=known.__contains__,
        dry_run=dry_run,
    )
