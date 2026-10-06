"""CLO-6 lock snapshots (BUILD_SPEC CLO-6 ``snapshots.py``; 03 REQ-CLS-010; 04 T-CLS-04
``snapshot_manifest_sha256``, T-CLS-05 ``lock_snapshot``, E-64; ENGINE_SPEC_B §15.2.7 S15-R-18 to
S15-R-20 through the EDS-6 engine module; supervisor ruling Q-10: ``report_run_id`` stays NULL).

``freeze_datasets`` iterates the engine's ``SNAPSHOT_KINDS``, calls F-RPS's registered builder for
each kind with a ``SnapshotScope``, stores the S15-R-18 CSV bytes as a ``SNAPSHOT_DATASET`` file
object and returns one ``DatasetFile`` per kind. The builders READ through a unit of work of the
tenant's SYSTEM principal (``freeze.system_unit``; supervisor ruling R-94 (a); S15-R-18c rev
1.88) — the frozen dataset of an entity, book and period is the same whoever decides — and the
caller's unit of work writes the files. A kind missing from the registry, or an absent
producer, refuses by name before any write: there is never a partial manifest (record §17). The
manifest is the engine's ``manifest_sha256`` over ``{kind: file_sha256}``; ``write_lock_snapshots``
inserts the T-CLS-05 rows. The engine, registry and reader parameters exist so the orchestration
is testable without a database; production callers leave them unset: the real producers are
resolved by name and read through the SYSTEM reader.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import insert

from erev_api.db import new_id
from erev_api.db.tables import lock_snapshot
from erev_api.domain.close import dependencies, freeze
from erev_api.enums import FilePurpose
from erev_api.files.store import store_file

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

# D-98 candidate 139 amendment 5 addendum (F-RPS §13.5): the frozen dataset is a MACHINE artefact —
# RAW identity cells inside, downloaded as exact bytes under ``file_sha256`` through the generic
# ``GET /files/{id}/content`` — so it is stored as octet-stream named ``<kind>.snapshot`` (UTF-8 CSV
# bytes inside, unchanged), never as a ``text/csv`` ``.csv`` a spreadsheet would open unguarded; the
# only spreadsheet deliveries are the report outputs.
MEDIA_TYPE: Final = "application/octet-stream"
FILE_SUFFIX: Final = ".snapshot"


def dataset_filename(kind: str) -> str:
    """The stored ``original_filename`` of one frozen dataset (``<kind>.snapshot``)."""
    return f"{kind}{FILE_SUFFIX}"


class MachineArtefactRefused(ValueError):
    """A retained SNAPSHOT_DATASET row came back from the store with spreadsheet metadata (D-98
    candidate 145 (A), CLO-SNAPSHOT-MEDIA-REUSE-1): ``store_file`` dedups on (tenant, sha256,
    purpose) and returns the existing row as stored, so a row from before the machine-artefact
    ruling keeps ``text/csv`` / ``<kind>.csv``; the freeze refuses by name rather than freezing it —
    nothing is deleted or rewritten (IM-A), deduplication and identities stand."""


def assert_machine_artefact(row: Mapping[str, Any], kind: str) -> None:
    """The returned (created or reused) row must be the machine artefact: ``MEDIA_TYPE`` and
    ``dataset_filename(kind)``; otherwise ``MachineArtefactRefused`` naming kind, file id, the
    stored media type / name and the expected pair (option (ii) of D-98 candidate 145 (A))."""
    expected = (MEDIA_TYPE, dataset_filename(kind))
    stored = (str(row.get("media_type")), str(row.get("original_filename")))
    if stored != expected:
        raise MachineArtefactRefused(
            f"SNAPSHOT_DATASET {kind} is retained as {stored[0]} / {stored[1]} by file "
            f"{row.get('id')}; the freeze stores machine artefacts only ({expected[0]}, "
            f"{expected[1]}) — D-98 candidate 145 (A): the retained row is reused by content, not "
            "rewritten; the lock refuses whole until that row leaves through the governed "
            "retention path"
        )


NO_PARTIAL_MANIFEST: Final = "a lock freezes every kind or none (no partial manifest)"


@dataclass(frozen=True, slots=True)
class DatasetFile:
    """One frozen dataset: the T-CLS-05 columns of its ``lock_snapshot`` row."""

    kind: str
    file_id: UUID
    file_sha256: str
    row_count: int
    control_totals: Mapping[str, Any]


def freeze_datasets(
    uow: UnitOfWork,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    known_at: datetime,
    *,
    frozen_at: datetime | None = None,
    registry: Mapping[str, Callable[..., Any]] | None = None,
    scope_type: Callable[..., Any] | None = None,
    engine: dependencies.SnapshotEngine | None = None,
    reader: Callable[[UnitOfWork], AbstractContextManager[UnitOfWork]] | None = None,
) -> tuple[DatasetFile, ...]:
    """Freeze the twelve E-64 datasets of the period as of ``known_at`` (S15-R-18); refuse by name
    when the engine, the registry or any kind's builder is absent. ``frozen_at`` is the freeze
    instant for the kinds that cut and reconstruct at the freeze rather than at ``known_at``
    (``JE_POPULATION`` — S15-R-18b Q5; D-98 candidate 139 amendment 3: ``SnapshotScope.frozen_at``,
    ``CUTOFF_OF[JE_POPULATION] = frozen_at or known_at``); it is handed to the scope type only when
    given, so an older or injected scope type stays valid. Every builder reads through
    ``reader(uow)`` — in production ``freeze.system_unit``: the tenant's SYSTEM scope, read-only
    (R-94 (a)) — and ``uow`` stores the files."""
    engine = engine or dependencies.snapshot_engine()
    if registry is None or scope_type is None:
        resolved = dependencies.snapshot_registry()
        registry = resolved.datasets if registry is None else registry
        scope_type = resolved.scope if scope_type is None else scope_type
    missing = tuple(kind for kind in engine.kinds if kind not in registry)
    if missing:
        raise dependencies.ProducerMissing(
            dependencies.SNAPSHOT_REGISTRY,
            missing,
            dependencies.OWNER_RPS,
            note=NO_PARTIAL_MANIFEST,
        )
    scope = scope_type(
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
        known_at=known_at,
        **({} if frozen_at is None else {"frozen_at": frozen_at}),
    )
    frozen: list[DatasetFile] = []
    # R-94 (a): what a dataset holds must not depend on the decider's row-level scope — the
    # builders read through the SYSTEM reader, the caller's unit of work stores the files.
    with (reader or freeze.system_unit)(uow) as source:
        if reader is None:
            # 05 TXN-03 rev 1.121 (supervisor ruling R-119 (d)): the reader this freeze opens is
            # idle while ``uow`` stores a file; the caller set the bound for its own transaction,
            # and a caller that hands its reader in set it for that one.
            freeze.allow_idle(source.session)
        for kind in engine.kinds:
            encoded = registry[kind](source, scope)
            if str(encoded.kind) != kind:
                raise ValueError(f"the {kind} builder returned a {encoded.kind} dataset")
            row = store_file(
                uow,
                purpose=FilePurpose.SNAPSHOT_DATASET,
                stream=BytesIO(bytes(encoded.content)),
                original_filename=dataset_filename(kind),
                media_type=MEDIA_TYPE,
            )
            if str(row["sha256"]) != str(encoded.file_sha256):
                raise ValueError(
                    f"the stored {kind} dataset hash differs from the encoder's (S15-INV-06)"
                )
            # D-98 candidate 145 (A): a reused retained row keeps its stored metadata — refuse by
            # name before any lock write when it is not the machine artefact (never delete or
            # rewrite).
            assert_machine_artefact(row, kind)
            frozen.append(
                DatasetFile(
                    kind=kind,
                    file_id=UUID(str(row["id"])),
                    file_sha256=str(encoded.file_sha256),
                    row_count=int(encoded.row_count),
                    control_totals=dict(encoded.control_totals),
                )
            )
    return tuple(frozen)


def manifest_of(
    datasets: Sequence[DatasetFile], *, engine: dependencies.SnapshotEngine | None = None
) -> str:
    """T-CLS-04 ``snapshot_manifest_sha256``: the engine's S15-R-19 manifest over every kind."""
    engine = engine or dependencies.snapshot_engine()
    kinds = {dataset.kind for dataset in datasets}
    if kinds != set(engine.kinds) or len(datasets) != len(engine.kinds):
        raise ValueError("a manifest covers each of the twelve snapshot kinds exactly once")
    return str(engine.manifest_sha256({dataset.kind: dataset.file_sha256 for dataset in datasets}))


def snapshot_rows(
    tenant_id: UUID,
    period_lock_id: UUID,
    datasets: Sequence[DatasetFile],
    *,
    stamp: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """T-CLS-05 rows, one per dataset, ``report_run_id`` NULL (ruling Q-10)."""
    return [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "period_lock_id": period_lock_id,
            "snapshot_kind": dataset.kind,
            "report_run_id": None,
            "file_id": dataset.file_id,
            "file_sha256": dataset.file_sha256,
            "row_count": dataset.row_count,
            "control_totals": dict(dataset.control_totals),
            **stamp,
        }
        for dataset in datasets
    ]


def write_lock_snapshots(
    uow: UnitOfWork, period_lock_id: UUID, datasets: Sequence[DatasetFile]
) -> None:
    """Insert the T-CLS-05 rows of a lock."""
    principal = uow.principal
    stamp = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    uow.session.execute(
        insert(lock_snapshot),
        snapshot_rows(principal.tenant_id, period_lock_id, datasets, stamp=stamp),
    )
