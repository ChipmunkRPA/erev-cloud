"""D-98 candidate 145 (A) CLO-SNAPSHOT-MEDIA-REUSE-1 (Codex production-20260921-1954 §1): a REAL
legacy-row reuse on a database. ``store_file`` dedups a SNAPSHOT_DATASET on (tenant, sha256,
purpose) and returns the retained row with its old metadata, so a row stored earlier as
``text/csv`` / ``<kind>.csv`` would be frozen under the machine-artefact ruling (139-A5 addendum)
with spreadsheet
metadata; the freeze now refuses it by name before any lock write — nothing deleted, nothing
rewritten, deduplication and ``ux_file_object__sha_purpose`` untouched. DB-bound (``CloseWorld``):
NOT RUN on the authoring worktree (databases not provisioned); measured by the integrated batch.
The registry, scope type and engine are injected test doubles (as in ``test_snapshots_freeze``);
the storage boundary under test is the real ``file_object`` table and file store."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import file_object
from erev_api.domain.close import dependencies, snapshots
from erev_api.enums import FilePurpose, SnapshotKind
from erev_api.files.store import LocalFileStore, store_file
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.close_world import BOOK, CloseWorld, close_world, system_session
from support.db import TestDatabase

KINDS: Final = tuple(kind.value for kind in SnapshotKind)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


@dataclass(frozen=True)
class _Encoded:
    kind: str
    content: bytes
    file_sha256: str
    row_count: int
    control_totals: dict[str, Any]


def _encoded(kind: str) -> _Encoded:
    content = f"row_key,amount\n{kind}-1,1.00\n".encode()
    return _Encoded(kind, content, hashlib.sha256(content).hexdigest(), 1, {"rows": 1})


def _registry() -> dict[str, Any]:
    return {kind: (lambda uow, scope, kind=kind: _encoded(kind)) for kind in KINDS}


def _engine() -> dependencies.SnapshotEngine:
    return dependencies.SnapshotEngine(
        kinds=KINDS,
        encoded=_Encoded,
        manifest_sha256=lambda hashes: "|".join(f"{k}:{v}" for k, v in sorted(hashes.items())),
    )


def _rows(world: CloseWorld) -> list[dict[str, Any]]:
    with system_session(world) as session:
        return [
            dict(row)
            for row in session.execute(
                select(file_object).where(
                    file_object.c.purpose == FilePurpose.SNAPSHOT_DATASET.value
                )
            ).mappings()
        ]


def test_legacy_csv_snapshot_row_refuses_the_freeze_by_name(world: CloseWorld) -> None:
    legacy = _encoded("WATERFALL")
    with world.place.uow() as uow:
        planted = store_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=BytesIO(legacy.content),
            original_filename="WATERFALL.csv",
            media_type="text/csv",
        )
        uow.commit()
    planted_id = UUID(str(planted["id"]))
    before = _rows(world)
    assert len(before) == 1 and before[0]["media_type"] == "text/csv"

    with pytest.raises(snapshots.MachineArtefactRefused) as caught, world.place.uow() as uow:
        snapshots.freeze_datasets(
            uow,
            world.entity_id,
            BOOK,
            world.period_id,
            world.place.clock.now(),
            registry=_registry(),
            scope_type=dict,
            engine=_engine(),
        )
    message = str(caught.value)
    assert "WATERFALL" in message and str(planted_id) in message and "text/csv" in message
    after = _rows(world)
    # The reused row is exactly the planted one, untouched; the refused unit of work wrote nothing.
    assert [(r["id"], r["media_type"], r["original_filename"]) for r in after] == [
        (planted_id, "text/csv", "WATERFALL.csv")
    ]


def test_fresh_rows_are_stored_as_machine_artefacts(world: CloseWorld) -> None:
    with world.place.uow() as uow:
        frozen = snapshots.freeze_datasets(
            uow,
            world.entity_id,
            BOOK,
            world.period_id,
            world.place.clock.now(),
            registry=_registry(),
            scope_type=dict,
            engine=_engine(),
        )
        uow.commit()
    assert [item.kind for item in frozen] == list(KINDS)
    rows = {UUID(str(r["id"])): r for r in _rows(world)}
    assert len(rows) == len(KINDS)
    for item in frozen:
        row = rows[item.file_id]
        assert (row["media_type"], row["original_filename"]) == (
            snapshots.MEDIA_TYPE,
            snapshots.dataset_filename(item.kind),
        )
        assert str(row["sha256"]) == item.file_sha256
    with system_session(world) as session:
        total = session.execute(select(func.count()).select_from(file_object)).scalar_one()
    assert total >= len(KINDS)
