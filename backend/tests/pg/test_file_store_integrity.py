"""Native ``put_file`` / ``open_file`` over the Cloud Storage fake against the review database:
the Codex storage probe of c37b002 (F01 to F04) and the controls that must keep passing (lane P2;
05 OPR-13, PRV-06, PRV-07; DG-KRN-FILE-01, DG-KRN-FILE-02; hosted runtime contract)."""

from __future__ import annotations

import hashlib
import io
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.storage.gcs import GcsFileStore
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.db.session import identity_session
from erev_api.db.tables.platform import file_object
from erev_api.enums import FilePurpose, TenantKind
from erev_api.files import store as store_module
from erev_api.files.lifecycle import shred_sidecar
from erev_api.files.store import (
    StoredObjectMismatch,
    _file_key,
    encryption_context,
    open_file,
    put_file,
    shred_marker_key,
    sidecar_key,
    storage_key,
    storage_key_lock_id,
)
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import select, text, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.fake_gcs import FakeGcsBackend

pytestmark = pytest.mark.pg
BUCKET = "erev-files-integrity"
CORRECT = b"snapshot rows of the real tenant\n" * 4
WRONG = b"planted rows of another payload!\n" * 4  # same size, different content
assert len(CORRECT) == len(WRONG)
TRY_LOCK = text("SELECT pg_try_advisory_xact_lock(:lock_id)")


def _context(tenant_id: UUID, clock: FrozenClock, request_id: str) -> RequestContext:
    return RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id=request_id,
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring))


@pytest.fixture
def backend() -> FakeGcsBackend:
    return FakeGcsBackend()


def gcs(backend: FakeGcsBackend) -> GcsFileStore:
    return GcsFileStore(BUCKET, client=backend.client(), sleep=lambda _: None)


@contextmanager
def uow_over(
    files: Any, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock, request_id: str
) -> Iterator[UnitOfWork]:
    with unit_of_work(
        _context(tenant_id, clock, request_id), clock=clock, keyring=keyring, files=files
    ) as uow:
        yield uow


def _rows(uow: UnitOfWork, sha256: str) -> list[Any]:
    return list(
        uow.session.execute(select(file_object).where(file_object.c.sha256 == sha256)).mappings()
    )


def test_f01_planted_same_size_object_never_gets_a_reference(
    backend: FakeGcsBackend, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    files = gcs(backend)
    sha = hashlib.sha256(CORRECT).hexdigest()
    key = storage_key(tenant_id, FilePurpose.AUDIT_DIGEST, sha)
    files.put(key, io.BytesIO(WRONG))  # an unencrypted purpose: the key names the plaintext hash
    with uow_over(files, tenant_id, keyring, clock, "f01") as uow:
        with pytest.raises(StoredObjectMismatch):
            put_file(
                uow,
                purpose=FilePurpose.AUDIT_DIGEST,
                stream=io.BytesIO(CORRECT),
                original_filename="digest.json",
                media_type="application/json",
            )
    with uow_over(files, tenant_id, keyring, clock, "f01-check") as uow:
        assert _rows(uow, sha) == []
    live = backend.live(BUCKET, key)
    assert live is not None and live.data == WRONG, "the planted object is not overwritten either"


def test_f02_planted_encrypted_wrong_plaintext_never_gets_a_reference(
    backend: FakeGcsBackend, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    files = gcs(backend)
    sha = hashlib.sha256(CORRECT).hexdigest()
    key = storage_key(tenant_id, FilePurpose.SNAPSHOT_DATASET, sha)
    context = encryption_context(tenant_id, key)
    # An attacker with KEK access plants a valid-AAD ciphertext of the wrong plaintext.
    dek = _file_key(files, keyring, key, context)
    files.put(key, io.BytesIO(keyring.seal_file(dek, WRONG, context=context)))
    with uow_over(files, tenant_id, keyring, clock, "f02") as uow:
        with pytest.raises(StoredObjectMismatch):
            put_file(
                uow,
                purpose=FilePurpose.SNAPSHOT_DATASET,
                stream=io.BytesIO(CORRECT),
                original_filename=None,
                media_type="application/x-ndjson",
            )
    with uow_over(files, tenant_id, keyring, clock, "f02-check") as uow:
        assert _rows(uow, sha) == []


def test_legitimate_encrypted_dedup_across_processes_still_works(
    backend: FakeGcsBackend, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Another process stored the same plaintext (different nonce) but has not committed its row:
    the kept winner verifies and the reference is written."""
    other = gcs(backend)
    sha = hashlib.sha256(CORRECT).hexdigest()
    key = storage_key(tenant_id, FilePurpose.SNAPSHOT_DATASET, sha)
    context = encryption_context(tenant_id, key)
    dek = _file_key(other, keyring, key, context)
    other.put(key, io.BytesIO(keyring.seal_file(dek, CORRECT, context=context)))
    files = gcs(backend)
    with uow_over(files, tenant_id, keyring, clock, "dedup") as uow:
        stored = put_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=io.BytesIO(CORRECT),
            original_filename=None,
            media_type="application/x-ndjson",
        )
        assert stored.created and stored.row["sha256"] == sha
        # The upload holds the per-key advisory lock for the rest of its transaction (F04); the
        # contender is a second session with a context (DG-KRN-DB-04).
        with identity_session(request_id="dedup-contender") as contender:
            held = contender.execute(TRY_LOCK, {"lock_id": storage_key_lock_id(key)})
            assert held.scalar_one() is False
        uow.commit()
    assert len(backend.versions_of(BUCKET, key)) == 1, "the winner was kept, nothing rewritten"
    with uow_over(files, tenant_id, keyring, clock, "dedup-read") as uow:
        row, stream = open_file(
            uow.session, UUID(str(stored.row["id"])), files=files, keyring=keyring
        )
        assert stream.read() == CORRECT and row["storage_backend"] == "gcs"


def test_f03_restored_sidecar_generation_stays_unreadable_after_a_shred(
    backend: FakeGcsBackend, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    files = gcs(backend)
    with uow_over(files, tenant_id, keyring, clock, "f03-store") as uow:
        stored = put_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=io.BytesIO(CORRECT),
            original_filename=None,
            media_type="application/x-ndjson",
        )
        uow.commit()
    key = str(stored.row["storage_key"])
    report = shred_sidecar(files, key)  # the row keeps shredded_at = NULL (a restored database)
    assert report.deleted_generations
    backend.client().bucket(BUCKET).restore_blob(
        sidecar_key(key), generation=report.deleted_generations[0]
    )
    assert files.live_generation(sidecar_key(key)) > 0, "the platform restored the sidecar"
    with uow_over(files, tenant_id, keyring, clock, "f03-read") as uow:
        with pytest.raises(Problem) as excinfo:
            open_file(uow.session, UUID(str(stored.row["id"])), files=files, keyring=keyring)
    assert excinfo.value.slug == "not-found"
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]
    assert files.exists(shred_marker_key(key))


class ShredAfterNegativeMarkerCheck:
    """F04: the marker check passes, a shred completes, then the upload writes its sidecar."""

    def __init__(self, inner: GcsFileStore, storage_key: str) -> None:
        self._inner = inner
        self._marker = shred_marker_key(storage_key)
        self._storage_key = storage_key
        self.checks = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def exists(self, key: str) -> bool:
        if key == self._marker:
            self.checks += 1
            if self.checks == 1:
                shred_sidecar(self._inner, self._storage_key)
                return False
        return self._inner.exists(key)


def test_f04_upload_interleaved_with_a_shred_never_publishes_a_readable_file(
    backend: FakeGcsBackend, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    files = gcs(backend)
    sha = hashlib.sha256(CORRECT).hexdigest()
    key = storage_key(tenant_id, FilePurpose.SNAPSHOT_DATASET, sha)
    racing = ShredAfterNegativeMarkerCheck(files, key)
    with uow_over(racing, tenant_id, keyring, clock, "f04") as uow:
        with pytest.raises(Problem) as excinfo:
            put_file(
                uow,
                purpose=FilePurpose.SNAPSHOT_DATASET,
                stream=io.BytesIO(CORRECT),
                original_filename=None,
                media_type="application/x-ndjson",
            )
    assert excinfo.value.slug == "invalid-transition"
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]
    assert racing.checks >= 2, "the marker is re-checked after the sidecar write"
    assert files.live_generation(sidecar_key(key)) == 0
    assert files.exists(shred_marker_key(key))
    assert not files.exists(key), "no payload was written"
    with uow_over(files, tenant_id, keyring, clock, "f04-check") as uow:
        assert _rows(uow, sha) == []
    # And a later, honest upload of the same content is refused as long as the marker stands.
    with uow_over(files, tenant_id, keyring, clock, "f04-retry") as uow:
        with pytest.raises(Problem) as retry:
            put_file(
                uow,
                purpose=FilePurpose.SNAPSHOT_DATASET,
                stream=io.BytesIO(CORRECT),
                original_filename=None,
                media_type="application/x-ndjson",
            )
    assert [error.rule_id for error in retry.value.errors] == ["FILE_SHREDDED"]


def test_unrelated_keys_are_not_serialised_behind_each_other(
    backend: FakeGcsBackend, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    files = gcs(backend)
    with uow_over(files, tenant_id, keyring, clock, "lock-scope") as uow:
        put_file(
            uow,
            purpose=FilePurpose.AUDIT_DIGEST,
            stream=io.BytesIO(CORRECT),
            original_filename="a.json",
            media_type="application/json",
        )
        other_key = storage_key(
            tenant_id, FilePurpose.AUDIT_DIGEST, hashlib.sha256(WRONG).hexdigest()
        )
        with identity_session(request_id="lock-scope-contender") as contender:
            free = contender.execute(TRY_LOCK, {"lock_id": storage_key_lock_id(other_key)})
            assert free.scalar_one() is True
        uow.commit()
    assert uuid.UUID(str(tenant_id))  # the tenant row exists (factory), nothing else to assert


def _mark_shredded(uow: UnitOfWork, file_id: Any, clock: FrozenClock, reason: str) -> None:
    """PRV-07 (b) row state through the permitted IM-A update (the set-once quartet; the
    ``POST /files/{id}/shred`` command route belongs to SOP-5 and is not in source)."""
    uow.session.execute(
        update(file_object)
        .where(file_object.c.id == file_id)
        .values(
            shredded_at=clock.now(),
            shredded_by=uow.principal.id,
            shredded_by_kind=uow.principal.kind.value,
            shred_reason=reason,
        )
    )


def test_identical_bytes_after_a_shred_are_refused_by_name(
    backend: FakeGcsBackend, tenant_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    """FILES-SHRED-1 (D-98 145 Amendment 2): a shredded row never satisfies dedup. The lifecycle
    shred (marker first, every sidecar generation gone) and the row's shredded_* quartet, then the
    same bytes again: 409 ``invalid-transition`` / ``FILE_SHREDDED`` before any write; one row,
    still shredded; no ``created=False`` return."""
    files = gcs(backend)
    sha = hashlib.sha256(CORRECT).hexdigest()
    with uow_over(files, tenant_id, keyring, clock, "shred-reuse-store") as uow:
        stored = put_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=io.BytesIO(CORRECT),
            original_filename=None,
            media_type="application/x-ndjson",
        )
        uow.commit()
    key = str(stored.row["storage_key"])
    assert shred_sidecar(files, key).deleted_generations
    with uow_over(files, tenant_id, keyring, clock, "shred-reuse-mark") as uow:
        _mark_shredded(uow, stored.row["id"], clock, "FILES-SHRED-1 witness")
        uow.commit()
    versions_before = len(backend.versions_of(BUCKET, key))
    with uow_over(files, tenant_id, keyring, clock, "shred-reuse-again") as uow:
        with pytest.raises(Problem) as excinfo:
            put_file(
                uow,
                purpose=FilePurpose.SNAPSHOT_DATASET,
                stream=io.BytesIO(CORRECT),
                original_filename=None,
                media_type="application/x-ndjson",
            )
    assert excinfo.value.slug == "invalid-transition"
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]
    with uow_over(files, tenant_id, keyring, clock, "shred-reuse-rows") as uow:
        rows = _rows(uow, sha)
    assert [row["id"] for row in rows] == [stored.row["id"]], "the shredded row stays the sole row"
    assert rows[0]["shredded_at"] is not None
    assert len(backend.versions_of(BUCKET, key)) == versions_before, "nothing written"
    assert files.exists(shred_marker_key(key)) and files.live_generation(sidecar_key(key)) == 0


def test_a_shredded_winner_of_the_insert_race_is_refused_not_returned(
    backend: FakeGcsBackend,
    tenant_id: UUID,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FILES-SHRED-1, post-conflict site: the pre-check sees no row (another session's shredded
    row commits in between), the insert loses on ``ux_file_object__sha_purpose`` and the winner is
    shredded — refused by name, not returned as ``created=False``. A plaintext purpose is used so
    only the row state (no marker, no sidecar) can refuse."""
    files = gcs(backend)
    payload = b"report,cells\nA,1\n"
    sha = hashlib.sha256(payload).hexdigest()
    with uow_over(files, tenant_id, keyring, clock, "race-store") as uow:
        stored = put_file(
            uow,
            purpose=FilePurpose.REPORT_OUTPUT,
            stream=io.BytesIO(payload),
            original_filename=None,
            media_type="text/csv",
        )
        _mark_shredded(uow, stored.row["id"], clock, "FILES-SHRED-1 race witness")
        uow.commit()
    real_existing = store_module._existing
    calls: list[int] = []

    def late_visibility(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return None if len(calls) == 1 else real_existing(*args, **kwargs)

    monkeypatch.setattr(store_module, "_existing", late_visibility)
    with uow_over(files, tenant_id, keyring, clock, "race-again") as uow:
        with pytest.raises(Problem) as excinfo:
            put_file(
                uow,
                purpose=FilePurpose.REPORT_OUTPUT,
                stream=io.BytesIO(payload),
                original_filename=None,
                media_type="text/csv",
            )
    assert excinfo.value.slug == "invalid-transition"
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]
    assert len(calls) == 2, "pre-check (unseen) then the post-conflict re-read"
    with uow_over(files, tenant_id, keyring, clock, "race-rows") as uow:
        rows = _rows(uow, sha)
    assert [row["id"] for row in rows] == [stored.row["id"]] and rows[0]["shredded_at"] is not None
