"""Sidecar lifecycle: KEY-04 rewrap and PRV-07 shred over both backends (05 SAR-07, PRV-06,
PRV-07, OPR-10; hosted runtime contract §"GCS immutable file and wrapped-key contract" and
§"Shredding and retained digests"; deployment audit DEP-C; lane P2)."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

import pytest
from erev_api.adapters.keys.provider import LocalKeyProvider
from erev_api.adapters.storage.gcs import GcsFileStore
from erev_api.auth.keyring import KeyRing
from erev_api.enums import FilePurpose
from erev_api.files import lifecycle
from erev_api.files.lifecycle import rewrap_sidecar, shred_sidecar, storage_key_lock_id
from erev_api.files.store import (
    SHRED_MARKER_BYTES,
    FileShredded,
    GenerationConflict,
    LocalFileStore,
    VersionedFileStore,
    _admit,
    _file_key,
    encryption_context,
    shred_marker_key,
    sidecar_key,
    storage_key,
)
from erev_api.problems import Problem
from pydantic import SecretStr
from support.fake_gcs import DEFAULT_NOW, FakeGcsBackend

BUCKET = "erev-files-test"
TENANT = UUID("0191e0a0-0000-7000-8000-000000000001")
MASTER = "5a5a5a5a5a5a5a5a" * 4
PLAINTEXT = b"contract attachment with personal data\n" * 100


class MasterKeys:
    def get(self, name: str) -> SecretStr:
        return SecretStr(MASTER)


def local_keyring() -> KeyRing:
    return KeyRing(LocalKeyProvider(MasterKeys()))


def gcs_pair() -> tuple[FakeGcsBackend, GcsFileStore]:
    backend = FakeGcsBackend()
    return backend, GcsFileStore(BUCKET, client=backend.client(), sleep=lambda _: None)


@pytest.fixture(params=["local", "gcs"])
def files(request: pytest.FixtureRequest, tmp_path: Path) -> VersionedFileStore:
    if request.param == "local":
        return LocalFileStore(tmp_path)
    return gcs_pair()[1]


def encrypted_file(
    files: VersionedFileStore, keyring: KeyRing, plaintext: bytes = PLAINTEXT
) -> str:
    """The upload sequence of ``put_file`` for one encrypted purpose; the storage key."""
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, hashlib.sha256(plaintext).hexdigest())
    context = encryption_context(TENANT, key)
    dek = _file_key(files, keyring, key, context)
    files.put(key, io.BytesIO(keyring.seal_file(dek, plaintext, context=context)))
    return key


def decrypt(files: VersionedFileStore, keyring: KeyRing, key: str) -> bytes:
    context = encryption_context(TENANT, key)
    with files.open(sidecar_key(key)) as stored_key:
        dek = keyring.file_key(stored_key.read(), context=context)
    with files.open(key) as stored:
        return keyring.open_file(dek, stored.read(), context=context)


class Interposed:
    """A store whose ``replace`` (or marker ``exists``) runs a hook first, to interleave a
    concurrent shred at the exact point the contract worries about."""

    def __init__(self, inner: VersionedFileStore, *, before_replace: Callable[[], None]) -> None:
        self._inner = inner
        self._before_replace = before_replace

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def replace(self, storage_key: str, generation: int, stream: BinaryIO) -> int:
        self._before_replace()
        return self._inner.replace(storage_key, generation, stream)


class MarkerAppearsAfterCheck:
    """The marker check passes once, then a shred lands right after the CAS replace."""

    def __init__(self, inner: VersionedFileStore, storage_key: str) -> None:
        self._inner = inner
        self._marker = shred_marker_key(storage_key)
        self._storage_key = storage_key
        self._checks = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def exists(self, key: str) -> bool:
        if key == self._marker:
            self._checks += 1
            if self._checks == 1:
                return False
        return self._inner.exists(key)

    def replace(self, storage_key: str, generation: int, stream: BinaryIO) -> int:
        new_generation = self._inner.replace(storage_key, generation, stream)
        shred_sidecar(self._inner, self._storage_key)
        return new_generation


def test_rewrap_keeps_the_data_key_and_leaves_the_payload(files: VersionedFileStore) -> None:
    keyring = local_keyring()
    key = encrypted_file(files, keyring)
    sidecar = sidecar_key(key)
    context = encryption_context(TENANT, key)
    generation = files.live_generation(sidecar)
    before = files.read_generation(sidecar, generation)
    with files.open(key) as payload:
        payload_before = payload.read()

    result = rewrap_sidecar(files, keyring, key)

    assert result.changed and result.previous_generation == generation
    assert files.live_generation(sidecar) == result.generation
    after = files.read_generation(sidecar, result.generation)
    assert after != before, "a fresh wrap"
    assert keyring.file_key(after, context=context) == keyring.file_key(before, context=context)
    with files.open(key) as payload:
        assert payload.read() == payload_before, "the immutable payload is never re-encrypted"
    assert decrypt(files, keyring, key) == PLAINTEXT
    if files.backend == "gcs":
        assert result.generation > generation
        assert files.read_generation(sidecar, generation) == before, "noncurrent, still retained"


def test_shred_marks_first_then_deletes_every_generation(files: VersionedFileStore) -> None:
    keyring = local_keyring()
    key = encrypted_file(files, keyring)
    sidecar = sidecar_key(key)
    rewrap_sidecar(files, keyring, key)
    rewrap_sidecar(files, keyring, key)
    retained_before = len(files.versions(sidecar))

    report = shred_sidecar(files, key)

    assert report.marker_created and report.live_generation == 0
    assert files.exists(shred_marker_key(key))
    with files.open(shred_marker_key(key)) as marker:
        assert marker.read() == SHRED_MARKER_BYTES
    assert files.live_generation(sidecar) == 0 and not files.exists(sidecar)
    assert files.exists(key), "the ciphertext stays as evidence (D-43); it is unreadable"
    if files.backend == "gcs":
        assert retained_before == 3 and len(report.deleted_generations) == 3
        assert all(v.soft_deleted for v in report.retained) and len(report.retained) == 3
        assert report.irreversible_after == DEFAULT_NOW + timedelta(days=7)
    else:
        assert report.deleted_generations == (1,) and report.retained == ()
        assert report.irreversible_after is None
    # Idempotent: a repeated shred deletes nothing new and reports the same residual retention.
    again = shred_sidecar(files, key)
    assert not again.marker_created and again.deleted_generations == ()
    assert again.retained == report.retained and again.live_generation == 0
    # Nothing recreates a usable sidecar: not an upload retry, not a rewrap.
    context = encryption_context(TENANT, key)
    with pytest.raises(Problem) as excinfo:
        _file_key(files, keyring, key, context)
    assert excinfo.value.slug == "invalid-transition"
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]
    assert files.live_generation(sidecar) == 0
    with pytest.raises(FileShredded):
        rewrap_sidecar(files, keyring, key)
    with pytest.raises(FileNotFoundError):
        decrypt(files, keyring, key)


def test_rewrap_conflict_reevaluates_and_never_creates() -> None:
    backend, files = gcs_pair()
    other = GcsFileStore(BUCKET, client=backend.client(), sleep=lambda _: None)
    keyring = local_keyring()
    key = encrypted_file(files, keyring)
    sidecar = sidecar_key(key)

    # A concurrent rewrap of the same data key wins between our read and our CAS write.
    racing = Interposed(files, before_replace=lambda: rewrap_sidecar(other, keyring, key))
    result = rewrap_sidecar(racing, keyring, key)  # type: ignore[arg-type]
    assert not result.changed and result.generation == files.live_generation(sidecar)
    assert decrypt(files, keyring, key) == PLAINTEXT

    # A winner carrying a different data key is an inconsistency, never silently accepted.
    def corrupt() -> None:
        generation = other.live_generation(sidecar)
        _, blob = keyring.new_file_key(context=encryption_context(TENANT, key))
        other.replace(sidecar, generation, io.BytesIO(blob))

    with pytest.raises(GenerationConflict):
        rewrap_sidecar(Interposed(files, before_replace=corrupt), keyring, key)  # type: ignore[arg-type]


def test_rewrap_racing_shred_cannot_restore_access(files: VersionedFileStore) -> None:
    keyring = local_keyring()
    key = encrypted_file(files, keyring)
    sidecar = sidecar_key(key)

    # Order A: the shred completes between the rewrap's read and its CAS write.
    racing = Interposed(files, before_replace=lambda: shred_sidecar(files, key))
    with pytest.raises(FileShredded):
        rewrap_sidecar(racing, keyring, key)  # type: ignore[arg-type]
    assert files.live_generation(sidecar) == 0 and files.exists(shred_marker_key(key))
    assert all(v.soft_deleted or not v.live for v in files.versions(sidecar)), (
        "no generation is live after the race"
    )


def test_rewrap_then_shred_lands_before_the_marker_recheck(files: VersionedFileStore) -> None:
    keyring = local_keyring()
    key = encrypted_file(files, keyring)
    sidecar = sidecar_key(key)

    # Order B: the marker check passed, the CAS replace succeeded, then a shred ran; the rewrap
    # must not leave its fresh generation live.
    racing = MarkerAppearsAfterCheck(files, key)
    with pytest.raises(FileShredded):
        rewrap_sidecar(racing, keyring, key)  # type: ignore[arg-type]
    assert files.live_generation(sidecar) == 0
    assert files.exists(shred_marker_key(key))


def test_upload_racing_shred_fails_closed(files: VersionedFileStore) -> None:
    keyring = local_keyring()
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, hashlib.sha256(PLAINTEXT).hexdigest())
    context = encryption_context(TENANT, key)
    dek = _file_key(files, keyring, key, context)  # the sidecar exists; the writer holds the key
    shred_sidecar(files, key)
    # The writer's payload write succeeds (immutable ciphertext, now unreadable) but the retry
    # path that would need a sidecar refuses, and no reader can recover the key.
    files.put(key, io.BytesIO(keyring.seal_file(dek, PLAINTEXT, context=context)))
    with pytest.raises(Problem) as excinfo:
        _file_key(files, keyring, key, context)
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]
    assert files.live_generation(sidecar_key(key)) == 0
    with pytest.raises(FileNotFoundError):
        decrypt(files, keyring, key)


def test_restore_of_a_soft_deleted_sidecar_reproduces_the_plaintext() -> None:
    backend, files = gcs_pair()
    keyring = local_keyring()
    key = encrypted_file(files, keyring)
    sidecar = sidecar_key(key)
    expected = hashlib.sha256(PLAINTEXT).hexdigest()
    generation = files.live_generation(sidecar)

    files.delete_generation(sidecar, generation)  # an accidental deletion, no marker
    with pytest.raises(FileNotFoundError):
        decrypt(files, keyring, key)
    (retained,) = files.versions(sidecar)
    assert retained.soft_deleted and retained.hard_delete_at == DEFAULT_NOW + timedelta(days=7)

    restored = backend.client().bucket(BUCKET).restore_blob(sidecar, generation=generation)
    assert restored.generation is not None and restored.generation > generation
    assert hashlib.sha256(decrypt(files, keyring, key)).hexdigest() == expected

    # After a shred, the same platform-level restore cannot give the application access back:
    # the marker refuses uploads and rewraps, and the row's shredded_at refuses reads.
    report = shred_sidecar(files, key)
    assert report.retained and report.irreversible_after is not None
    backend.client().bucket(BUCKET).restore_blob(sidecar, generation=report.deleted_generations[-1])
    with pytest.raises(FileShredded):
        rewrap_sidecar(files, keyring, key)
    with pytest.raises(Problem):
        _file_key(files, keyring, key, encryption_context(TENANT, key))


def test_storage_key_lock_id_is_stable_and_positive() -> None:
    first = storage_key_lock_id("t1/ATTACHMENT/abc")
    assert first == storage_key_lock_id("t1/ATTACHMENT/abc")
    assert 0 < first < 2**63
    assert first != storage_key_lock_id("t1/ATTACHMENT/abd")
    assert lifecycle.MAX_SHRED_PASSES >= 2


class ShredAfterNegativeMarkerCheck:
    """Codex probe F04 at the store level: the marker check passes, a shred completes, then the
    upload writes its sidecar."""

    def __init__(self, inner: VersionedFileStore, storage_key: str) -> None:
        self._inner = inner
        self._marker = shred_marker_key(storage_key)
        self._storage_key = storage_key
        self._checks = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def exists(self, key: str) -> bool:
        if key == self._marker:
            self._checks += 1
            if self._checks == 1:
                shred_sidecar(self._inner, self._storage_key)
                return False
        return self._inner.exists(key)


def test_file_key_never_leaves_a_live_sidecar_after_a_shred(files: VersionedFileStore) -> None:
    keyring = local_keyring()
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, hashlib.sha256(PLAINTEXT).hexdigest())
    racing = ShredAfterNegativeMarkerCheck(files, key)
    with pytest.raises(Problem) as excinfo:
        _file_key(racing, keyring, key, encryption_context(TENANT, key))  # type: ignore[arg-type]
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]
    assert files.live_generation(sidecar_key(key)) == 0, "the recreated sidecar was deleted"
    assert files.exists(shred_marker_key(key))
    assert all(not version.live for version in files.versions(sidecar_key(key)))


def test_a_shredded_row_never_satisfies_dedup_a_live_row_is_returned_unchanged() -> None:
    """FILES-SHRED-1 (D-98 145 Amendment 2): the dedup admission is pure — a retained row with
    ``shredded_at`` set is refused by name before any lock, sidecar or object write; a live row and
    an absent row pass through unchanged."""
    live = {"id": "live", "shredded_at": None}
    assert _admit(live) is live
    assert _admit(None) is None
    with pytest.raises(Problem) as excinfo:
        _admit({"id": "gone", "shredded_at": DEFAULT_NOW})
    assert excinfo.value.slug == "invalid-transition"
    assert [error.rule_id for error in excinfo.value.errors] == ["FILE_SHREDDED"]


def test_prv_07_a_shred_reports_the_markers_own_instant() -> None:
    """05 PRV-07 b rev 1.171 (item FILE-SHRED-DURABLE-ORDER-1): the report carries the instant the
    store gives the marker. The marker is written once, by the first shred of the key, and never
    replaced — so a run that finds the key already destroyed, hours later, still says when the
    destruction began, and so does the run that deletes a generation which came back."""
    backend, files = gcs_pair()
    keyring = local_keyring()
    key = encrypted_file(files, keyring)
    sidecar = sidecar_key(key)

    first = shred_sidecar(files, key)
    assert (first.marker_created, first.marker_at) == (True, DEFAULT_NOW)

    backend.now = DEFAULT_NOW + timedelta(hours=3)
    again = shred_sidecar(files, key)
    assert (again.marker_created, again.deleted_generations, again.marker_at) == (
        False,
        (),
        DEFAULT_NOW,
    )

    backend.client().bucket(BUCKET).restore_blob(sidecar, generation=first.deleted_generations[-1])
    restored = files.live_generation(sidecar)
    assert restored != 0
    cleared = shred_sidecar(files, key)
    assert (cleared.marker_created, cleared.deleted_generations, cleared.marker_at) == (
        False,
        (restored,),
        DEFAULT_NOW,
    )


def test_prv_07_the_local_store_gives_the_marker_files_own_time(tmp_path: Path) -> None:
    """The same member on the local store: the marker file's modification time, which no later
    shred changes (``put`` keeps an object that is already at the key)."""
    files = LocalFileStore(tmp_path)
    key = encrypted_file(files, local_keyring())
    report = shred_sidecar(files, key)
    marker = tmp_path.joinpath(*shred_marker_key(key).split("/"))
    written = datetime.fromtimestamp(marker.stat().st_mtime, UTC)
    assert report.marker_at == written
    (version,) = files.versions(shred_marker_key(key))
    assert (version.live, version.created_at) == (True, written)
    assert shred_sidecar(files, key).marker_at == written
    assert files.versions(sidecar_key(key)) == ()


def test_key_04_a_rewrap_reads_its_context_from_the_key(files: VersionedFileStore) -> None:
    """05 SBX-03 rev 1.196 (item SBX-FILE-READ-1): the associated data of a stored file names
    the workspace of its STORAGE KEY, and a sandbox copy's row carries its source's key. The
    rewrap takes that workspace from the key itself — it has no parameter for it — so a caller
    that holds a copied row cannot name the row's workspace by mistake (measured before: the
    rewrap of a copied file with the sandbox's id failed ``InvalidTag``). The sidecar is
    rewrapped under the key's workspace and the payload still opens; a key that names no
    workspace is refused."""
    keyring = local_keyring()
    key = encrypted_file(files, keyring)  # stored by TENANT: for a copy's row, its source
    before = files.live_generation(sidecar_key(key))
    result = rewrap_sidecar(files, keyring, key)
    assert result.changed and result.previous_generation == before
    assert decrypt(files, keyring, key) == PLAINTEXT
    for other in ("no-separator", f"{str(TENANT).upper()}/ATTACHMENT/{'ab' * 32}"):
        with pytest.raises(ValueError, match="names no workspace"):
            rewrap_sidecar(files, keyring, other)
