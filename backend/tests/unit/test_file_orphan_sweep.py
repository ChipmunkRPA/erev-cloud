"""SCH-14 ``file_orphan_sweep`` (05 §SCH row 973; OPR-13): delete file-store objects older than
24 hours that no ``file_object`` row references. CPU only, over the two adapters the slice may
exercise — ``LocalFileStore`` on ``tmp_path`` and ``GcsFileStore`` over ``tests/support/fake_gcs``
(never a live cloud) — with the tenant's ``file_object`` reader and the tenant directory injected;
the database-bound readers are NOT RUN here (record §4.22 (e))."""

from __future__ import annotations

import errno
import io
import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.adapters.storage.gcs import GcsFileStore
from erev_api.files import sweep as sch14
from erev_api.files.store import (
    INCOMING_DIR,
    SHRED_MARKER_SUFFIX,
    LocalFileStore,
    sidecar_key,
)
from support.fake_gcs import FakeGcsBackend

NOW = datetime(2026, 9, 21, 3, 40, tzinfo=UTC)
TENANT = UUID("01a0c2a9-0036-72f3-b78c-ebef539cb392")
STRANGER = UUID("01a0c2a9-0036-72f3-b78c-000000000001")
BUCKET = "erev-files"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def _key(tenant: UUID, sha: str) -> str:
    return f"{tenant}/evidence/{sha}"


class Stores:
    """Both adapters behind one interface for the shared cases: ``put(key, data, age)`` stores an
    object whose store timestamp is ``age`` before NOW."""

    def __init__(self, kind: str, tmp_path: Path) -> None:
        self.kind = kind
        self.backend = FakeGcsBackend(now=NOW)
        if kind == "local":
            self.root = tmp_path / "files"
            self.store: sch14.SweepableFileStore = LocalFileStore(self.root)
        else:
            self.store = GcsFileStore(BUCKET, client=self.backend.client(), sleep=lambda _: None)

    def put(self, key: str, data: bytes, *, age: timedelta) -> int:
        if self.kind == "local":
            result = self.store.put_object(key, io.BytesIO(data))
            stamp = (NOW - age).timestamp()
            os.utime(self.root.joinpath(*key.split("/")), (stamp, stamp))
            return result.generation
        self.backend.now = NOW - age
        result = self.store.put_object(key, io.BytesIO(data))
        self.backend.now = NOW
        return result.generation

    def exists(self, key: str) -> bool:
        return self.store.exists(key)


@pytest.fixture(params=["local", "gcs"])
def stores(request: pytest.FixtureRequest, tmp_path: Path) -> Stores:
    return Stores(request.param, tmp_path)


def _guard(
    rows: dict[UUID, set[str]], events: list[str] | None = None
) -> Callable[[UUID, str], AbstractContextManager[bool]]:
    """A reference guard over an in-memory row set: enters the key's boundary (recorded when
    ``events`` is given), answers whether a row references the key, exits after the deletions."""

    @contextmanager
    def guard(tenant_id: UUID, key: str) -> Iterator[bool]:
        if events is not None:
            events.append(f"enter {key}")
        yield key in rows.get(tenant_id, set())
        if events is not None:
            events.append(f"exit {key}")

    return guard


def _known(*tenants: UUID) -> Callable[[UUID], bool]:
    return lambda tenant_id: tenant_id in tenants


def test_orphans_older_than_a_day_go_with_their_sidecar_and_references_stay(stores: Stores) -> None:
    old_orphan = _key(TENANT, SHA_A)
    referenced = _key(TENANT, SHA_B)
    young_orphan = _key(TENANT, SHA_C)
    stores.put(old_orphan, b"orphan", age=timedelta(hours=25))
    stores.put(sidecar_key(old_orphan), b"dek", age=timedelta(hours=25))
    stores.put(referenced, b"kept", age=timedelta(hours=48))
    stores.put(sidecar_key(referenced), b"dek", age=timedelta(hours=48))
    stores.put(young_orphan, b"fresh", age=timedelta(hours=23))
    report = sch14.sweep(
        stores.store,
        now=NOW,
        reference_guard=_guard({TENANT: {referenced}}),
        tenant_known=_known(TENANT),
    )
    assert report.deleted == (old_orphan,)
    assert report.sidecars_deleted == (sidecar_key(old_orphan),)
    assert report.kept_referenced == (referenced,) and report.kept_young == (young_orphan,)
    assert not stores.exists(old_orphan) and not stores.exists(sidecar_key(old_orphan))
    assert stores.exists(referenced) and stores.exists(sidecar_key(referenced))
    assert stores.exists(young_orphan)
    assert not report.dry_run and report.backend == stores.store.backend


def test_the_age_comes_from_the_store_timestamp_at_exactly_twenty_four_hours(
    stores: Stores,
) -> None:
    at_boundary = _key(TENANT, SHA_A)
    just_under = _key(TENANT, SHA_B)
    stores.put(at_boundary, b"x", age=sch14.MAX_AGE)
    stores.put(just_under, b"y", age=sch14.MAX_AGE - timedelta(seconds=1))
    report = sch14.sweep(
        stores.store, now=NOW, reference_guard=_guard({}), tenant_known=_known(TENANT)
    )
    assert report.deleted == (at_boundary,) and report.kept_young == (just_under,)


def test_shred_markers_are_never_candidates(stores: Stores) -> None:
    shredded = _key(TENANT, SHA_A)
    marker = sidecar_key(shredded) + SHRED_MARKER_SUFFIX
    stores.put(marker, b"erev shred marker\n", age=timedelta(days=30))
    report = sch14.sweep(
        stores.store, now=NOW, reference_guard=_guard({}), tenant_known=_known(TENANT)
    )
    assert report.deleted == () and report.sidecars_deleted == ()
    assert stores.exists(marker)
    assert marker in report.skipped_markers


def test_a_sidecar_without_its_object_is_reported_never_deleted(stores: Stores) -> None:
    # A .dek follows its object's verdict and is never independently an orphan (D-98 138-A1):
    # without the object there is no verdict, so the sidecar is reported and kept.
    lonely = sidecar_key(_key(TENANT, SHA_D))
    stores.put(lonely, b"dek", age=timedelta(hours=30))
    report = sch14.sweep(
        stores.store, now=NOW, reference_guard=_guard({}), tenant_known=_known(TENANT)
    )
    assert report.reported_lonely_sidecars == (lonely,)
    assert report.sidecars_deleted == () and report.deleted == ()
    assert stores.exists(lonely)


def test_an_unknown_tenant_prefix_is_reported_never_deleted(stores: Stores) -> None:
    stranger = _key(STRANGER, SHA_A)
    stores.put(stranger, b"?", age=timedelta(days=3))
    report = sch14.sweep(
        stores.store, now=NOW, reference_guard=_guard({}), tenant_known=_known(TENANT)
    )
    assert report.deleted == () and report.reported_unknown_tenant == (stranger,)
    assert stores.exists(stranger)


def test_dry_run_reports_every_decision_and_deletes_nothing(stores: Stores) -> None:
    old_orphan = _key(TENANT, SHA_A)
    stores.put(old_orphan, b"orphan", age=timedelta(hours=25))
    stores.put(sidecar_key(old_orphan), b"dek", age=timedelta(hours=25))
    report = sch14.sweep(
        stores.store,
        now=NOW,
        reference_guard=_guard({}),
        tenant_known=_known(TENANT),
        dry_run=True,
    )
    assert report.dry_run and report.deleted == (old_orphan,)
    assert report.sidecars_deleted == (sidecar_key(old_orphan),)
    assert stores.exists(old_orphan) and stores.exists(sidecar_key(old_orphan))


def test_local_partial_spools_older_than_a_day_are_swept_and_reported_apart(tmp_path: Path) -> None:
    stores = Stores("local", tmp_path)
    stores.put(_key(TENANT, SHA_A), b"live", age=timedelta(hours=1))  # creates the root
    incoming = stores.root / INCOMING_DIR
    incoming.mkdir(exist_ok=True)
    stale = incoming / str(uuid4())
    fresh = incoming / str(uuid4())
    stale.write_bytes(b"partial")
    fresh.write_bytes(b"partial")
    old = (NOW - timedelta(hours=26)).timestamp()
    os.utime(stale, (old, old))
    recent = (NOW - timedelta(minutes=5)).timestamp()
    os.utime(fresh, (recent, recent))
    report = sch14.sweep(
        stores.store, now=NOW, reference_guard=_guard({}), tenant_known=_known(TENANT)
    )
    assert report.partials_deleted == (f"{INCOMING_DIR}/{stale.name}",)
    assert not stale.exists() and fresh.exists()
    assert report.deleted == ()


def test_a_newer_generation_under_the_same_key_is_never_touched(tmp_path: Path) -> None:
    stores = Stores("gcs", tmp_path)
    key = _key(TENANT, SHA_A)
    first = stores.put(key, b"one", age=timedelta(hours=25))
    seen: list[int] = []

    @contextmanager
    def guard(tenant_id: UUID, key_: str) -> Iterator[bool]:
        # Between the listing and the decision another writer replaces the live object: a fresh
        # generation under the same key (a second put would keep the existing object).
        seen.append(stores.store.replace(key_, first, io.BytesIO(b"two")))  # type: ignore[attr-defined]
        yield False

    report = sch14.sweep(stores.store, now=NOW, reference_guard=guard, tenant_known=_known(TENANT))
    (second,) = seen
    assert first != second
    assert report.deleted == (key,)  # the listed (old) generation
    live = stores.store.live_generation(key)
    assert live == second and stores.store.read_generation(key, second) == b"two"


def test_a_store_without_listing_refuses_by_name() -> None:
    class Plain:
        backend = "plain"

    with pytest.raises(sch14.SweepUnsupported, match="list_objects"):
        sch14.sweep(Plain(), now=NOW, reference_guard=_guard({}), tenant_known=_known(TENANT))  # type: ignore[arg-type]


def test_the_report_names_no_tenant_audit_event() -> None:
    """An orphan has no ``file_object`` row, so no tenant audit event can record its deletion and
    04 names no ``file.*`` action for it: the structured log lines are the record — a named open
    item (a platform operations event) in §4.22."""
    assert "open item" in (sch14.__doc__ or "") and "file_orphan_sweep.completed" in (
        sch14.__doc__ or ""
    )


def test_deletions_happen_inside_the_reference_boundary(stores: Stores) -> None:
    """The object and its sidecar are deleted while the key's guard is held — the storage-key
    lock boundary every writer path takes (D-98 138-A1) — never after it exits."""
    orphan = _key(TENANT, SHA_A)
    stores.put(orphan, b"orphan", age=timedelta(hours=25))
    stores.put(sidecar_key(orphan), b"dek", age=timedelta(hours=25))
    events: list[str] = []
    real_delete = stores.store.delete_generation

    def recording_delete(key: str, generation: int) -> None:
        events.append(f"delete {key}")
        real_delete(key, generation)

    stores.store.delete_generation = recording_delete  # type: ignore[method-assign]
    sch14.sweep(
        stores.store, now=NOW, reference_guard=_guard({}, events), tenant_known=_known(TENANT)
    )
    assert events == [
        f"enter {orphan}",
        f"delete {orphan}",
        f"delete {sidecar_key(orphan)}",
        f"exit {orphan}",
    ]


def test_a_listing_entry_that_vanishes_before_its_stat_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SCH14-R1 (D-98 138-A2): `put_object` links its `.incoming` spool away between the inventory
    and the stat of a listing; the vanished entry is skipped and the other objects are still
    listed and swept. Injected interleaving (the second stat of one path raises), not native
    concurrency evidence; a permission error still propagates."""
    stores = Stores("local", tmp_path)
    vanishing = _key(TENANT, SHA_A)
    surviving = _key(TENANT, SHA_B)
    stores.put(vanishing, b"spool", age=timedelta(hours=25))
    stores.put(surviving, b"orphan", age=timedelta(hours=25))
    target = stores.root.joinpath(*vanishing.split("/"))
    real_stat = Path.stat
    calls: dict[Path, int] = {}

    def racing_stat(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == target:
            calls[self] = calls.get(self, 0) + 1
            if calls[self] >= 2:  # is_file() saw it once; every later stat finds it gone
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(self))
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", racing_stat)
    listed = {item.storage_key for item in stores.store.list_objects()}
    assert surviving in listed and vanishing not in listed
    report = sch14.sweep(
        stores.store, now=NOW, reference_guard=_guard({}), tenant_known=_known(TENANT)
    )
    assert report.deleted == (surviving,)
    monkeypatch.undo()

    def forbidden_stat(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == stores.root.joinpath(*surviving.split("/")):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(self))
        return real_stat(self, *args, **kwargs)

    stores.put(surviving, b"again", age=timedelta(hours=25))
    monkeypatch.setattr(Path, "stat", forbidden_stat)
    with pytest.raises(PermissionError):
        stores.store.list_objects()
