"""``GcsFileStore`` over the in-process Cloud Storage fake (05 CMP-05, CFG-05, OPR-13, PRV-06;
DG-KRN-FILE-05; hosted runtime contract §"GCS immutable file and wrapped-key contract"; deployment
audit DEP-C; lane P2). No test constructs a Google client or reaches a bucket."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import threading
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.gcp import GcpError
from erev_api.adapters.keys.provider import GcpKeyProvider
from erev_api.adapters.storage.gcs import GcsFileStore
from erev_api.auth.keyring import KeyRing
from erev_api.enums import FilePurpose
from erev_api.files.store import (
    GenerationConflict,
    _file_key,
    encryption_context,
    sidecar_key,
    storage_key,
)
from pydantic import SecretStr
from support import log_guard
from support.fake_gcp import FakeKms, ServiceUnavailable
from support.fake_gcs import (
    DEFAULT_NOW,
    OBJECT_ADMIN,
    OBJECT_CREATOR,
    OBJECT_VIEWER,
    FakeGcsBackend,
)

BUCKET = "erev-files-test"
TENANT = UUID("0191e0a0-0000-7000-8000-000000000001")
KMS_KEY = "projects/p/locations/l/keyRings/erev/cryptoKeys/erev-app-kek"
KEY = "t1/ATTACHMENT/0000000000000000000000000000000000000000000000000000000000000001"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FailingStream(io.RawIOBase):
    """Yields ``chunks`` then raises, like a client connection reset mid-upload."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def read(self, size: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        raise OSError("connection reset while uploading")


class NoSecrets:
    def get(self, name: str) -> SecretStr:
        raise KeyError(name)

    def get_version(self, name: str, version: int) -> SecretStr:
        raise KeyError(name)


def store(
    backend: FakeGcsBackend,
    permissions: frozenset[str] = OBJECT_ADMIN,
    *,
    sleeps: list[float] | None = None,
) -> GcsFileStore:
    sleep = sleeps.append if sleeps is not None else (lambda _: None)
    return GcsFileStore(BUCKET, client=backend.client(permissions), sleep=sleep)


def hosted_keyring(kms: FakeKms | None = None) -> KeyRing:
    provider = GcpKeyProvider(NoSecrets(), kms_key=KMS_KEY, kms_client=kms or FakeKms())  # type: ignore[arg-type]
    return KeyRing(provider)


@pytest.fixture
def backend() -> FakeGcsBackend:
    return FakeGcsBackend()


def test_put_creates_if_absent_and_keeps_the_winner(backend: FakeGcsBackend) -> None:
    files = store(backend)
    assert files.backend == "gcs"
    assert files.put(KEY, io.BytesIO(b"first")) == (_sha(b"first"), 5)
    generation = files.live_generation(KEY)
    assert generation > 0
    # A second writer reports the bytes it streamed (SPEC-Q-158) and the stored object is kept.
    assert files.put(KEY, io.BytesIO(b"second bytes")) == (_sha(b"second bytes"), 12)
    assert files.live_generation(KEY) == generation
    with files.open(KEY) as stored:
        assert stored.read() == b"first"
    assert files.exists(KEY)
    uploads = [kwargs for operation, _, kwargs in backend.calls if operation == "upload"]
    assert [upload["if_generation_match"] for upload in uploads] == [0, 0]
    assert len(backend.versions_of(BUCKET, KEY)) == 1


def test_partial_upload_leaves_no_object(backend: FakeGcsBackend) -> None:
    files = store(backend)
    with pytest.raises(OSError):
        files.put(KEY, FailingStream([b"partial"]))  # type: ignore[arg-type]
    assert not files.exists(KEY)
    assert backend.versions_of(BUCKET, KEY) == []
    assert [operation for operation, _, _ in backend.calls if operation == "upload"] == []


def test_transient_failure_retries_with_the_same_precondition(backend: FakeGcsBackend) -> None:
    sleeps: list[float] = []
    files = store(backend, sleeps=sleeps)
    backend.faults.fail_next("upload", ServiceUnavailable())
    assert files.put(KEY, io.BytesIO(b"bytes")) == (_sha(b"bytes"), 5)
    uploads = [kwargs for operation, _, kwargs in backend.calls if operation == "upload"]
    assert [upload["if_generation_match"] for upload in uploads] == [0, 0]
    assert sleeps == [0.2]
    live = backend.live(BUCKET, KEY)
    assert live is not None and live.data == b"bytes"


def test_lost_response_then_412_verifies_the_winner(backend: FakeGcsBackend) -> None:
    files = store(backend)
    backend.faults.fail_next("upload", ServiceUnavailable(), ambiguous=True)
    assert files.put(KEY, io.BytesIO(b"bytes")) == (_sha(b"bytes"), 5)
    operations = [operation for operation, _, _ in backend.calls]
    assert operations.count("upload") == 2  # applied but lost, then 412 on the retry
    assert operations[-1] == "get"  # the winner is verified to exist
    assert len(backend.versions_of(BUCKET, KEY)) == 1
    with files.open(KEY) as stored:
        assert stored.read() == b"bytes"


def test_persistent_outage_fails_closed(backend: FakeGcsBackend) -> None:
    files = store(backend, sleeps=[])
    for _ in range(4):
        backend.faults.fail_next("upload", ServiceUnavailable())
    with pytest.raises(GcpError) as excinfo:
        files.put(KEY, io.BytesIO(b"bytes"))
    assert excinfo.value.kind == "transient"
    assert "bytes" not in str(excinfo.value)
    assert not files.exists(KEY)


def test_racing_identical_encrypted_uploads_share_one_data_key(backend: FakeGcsBackend) -> None:
    keyring = hosted_keyring()
    plaintext = b"customer contract, personal data inside\n" * 200
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, _sha(plaintext))
    context = encryption_context(TENANT, key)
    barrier = threading.Barrier(2)
    results: list[tuple[bytes, tuple[str, int]]] = []
    errors: list[BaseException] = []

    def upload() -> None:
        files = store(backend)  # one client per process
        try:
            barrier.wait(timeout=5)
            dek = _file_key(files, keyring, key, context)
            sealed = keyring.seal_file(dek, plaintext, context=context)
            results.append((dek, files.put(key, io.BytesIO(sealed))))
        except BaseException as error:  # noqa: BLE001 - collected for the assertion below
            errors.append(error)

    threads = [threading.Thread(target=upload, name=f"uploader-{n}") for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert len(results) == 2
    assert results[0][0] == results[1][0], "both writers used the winning sidecar's data key"
    sidecar_versions = backend.versions_of(BUCKET, sidecar_key(key))
    assert len(sidecar_versions) == 1 and sidecar_versions[0].live
    assert len(backend.versions_of(BUCKET, key)) == 1
    reader = store(backend)
    with reader.open(sidecar_key(key)) as stored_key:
        dek = keyring.file_key(stored_key.read(), context=context)
    with reader.open(key) as stored:
        assert keyring.open_file(dek, stored.read(), context=context) == plaintext
    assert not any(name.startswith("google.cloud") for name in sys.modules)


def test_exact_generation_reads_replace_and_deletes(backend: FakeGcsBackend) -> None:
    files = store(backend)
    files.put(KEY, io.BytesIO(b"one"))
    g1 = files.live_generation(KEY)
    g2 = files.replace(KEY, g1, io.BytesIO(b"two"))
    assert g2 > g1
    assert files.read_generation(KEY, g1) == b"one"  # noncurrent, still addressable by generation
    assert files.read_generation(KEY, g2) == b"two"
    with files.open(KEY) as live:
        assert live.read() == b"two"
    with pytest.raises(GenerationConflict):
        files.replace(KEY, g1, io.BytesIO(b"three"))  # stale generation
    assert [(v.generation, v.live, v.soft_deleted) for v in files.versions(KEY)] == [
        (g1, False, False),
        (g2, True, False),
    ]
    files.delete_generation(KEY, g1)
    files.delete_generation(KEY, g1)  # idempotent: a retry never touches another generation
    (old, live) = files.versions(KEY)
    assert old.soft_deleted and old.hard_delete_at == DEFAULT_NOW + timedelta(days=7)
    assert live.generation == g2 and live.live
    with pytest.raises(FileNotFoundError):
        files.read_generation(KEY, g1)
    files.delete_generation(KEY, g2)
    assert files.live_generation(KEY) == 0 and not files.exists(KEY)
    with pytest.raises(FileNotFoundError):
        files.open(KEY)
    with pytest.raises(GenerationConflict):
        files.replace(KEY, g2, io.BytesIO(b"resurrected"))  # replace never creates
    with pytest.raises(GenerationConflict):
        files.replace(KEY, 0, io.BytesIO(b"resurrected"))
    assert backend.live(BUCKET, KEY) is None
    deletes = [kwargs for operation, _, kwargs in backend.calls if operation == "delete"]
    assert all(kwargs["generation"] == kwargs["if_generation_match"] for kwargs in deletes)


def test_metadata_patch_matches_generation_and_metageneration(backend: FakeGcsBackend) -> None:
    files = store(backend)
    files.put(KEY, io.BytesIO(b"x"))
    generation, metageneration = files.metadata_generations(KEY)
    assert metageneration == 1
    assert (
        files.patch_metadata(
            KEY, generation=generation, metageneration=1, metadata={"erev": "probe"}
        )
        == 2
    )
    with pytest.raises(GenerationConflict):
        files.patch_metadata(KEY, generation=generation, metageneration=1, metadata={"erev": "x"})
    with pytest.raises(GenerationConflict):
        files.patch_metadata(KEY, generation=generation + 1, metageneration=2, metadata={})
    live = backend.live(BUCKET, KEY)
    assert live is not None and live.metadata == {"erev": "probe"} and live.metageneration == 2


def test_identities_are_checked_before_preconditions(backend: FakeGcsBackend) -> None:
    store(backend).put(KEY, io.BytesIO(b"first"))
    creator = store(backend, OBJECT_CREATOR)
    with pytest.raises(GcpError) as excinfo:
        creator.put(KEY, io.BytesIO(b"second"))  # meets the 412 but cannot read the winner
    assert excinfo.value.kind == "denied"
    live = backend.live(BUCKET, KEY)
    assert live is not None and live.data == b"first"
    with pytest.raises(GcpError) as denied:
        creator.open(KEY)
    assert denied.value.kind == "denied"
    viewer = store(backend, OBJECT_VIEWER)
    with viewer.open(KEY) as stored:
        assert stored.read() == b"first"
    with pytest.raises(GcpError) as refused:
        viewer.put("t1/ATTACHMENT/new", io.BytesIO(b"x"))
    assert refused.value.kind == "denied"


def test_key_provider_outage_never_publishes_a_payload(backend: FakeGcsBackend) -> None:
    kms = FakeKms()
    keyring = hosted_keyring(kms)
    files = store(backend)
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, _sha(b"doc"))
    context = encryption_context(TENANT, key)
    kms.faults.fail_next("encrypt", ServiceUnavailable())
    with pytest.raises(ServiceUnavailable):
        _file_key(files, keyring, key, context)
    assert backend.object_names(BUCKET) == []
    kms.faults.fail_next("decrypt", ServiceUnavailable())
    with pytest.raises(ServiceUnavailable):
        _file_key(files, keyring, key, context)
    # The sidecar exists as a recoverable orphan (SCH-14); no payload and no reference.
    assert backend.object_names(BUCKET) == [sidecar_key(key)]
    assert not files.exists(key)


@pytest.mark.parametrize("key", ["../escape", "/absolute", "t1//x", "t1/.incoming/x", "t1/a b"])
def test_invalid_storage_keys_raise(backend: FakeGcsBackend, key: str) -> None:
    with pytest.raises(ValueError):
        store(backend).exists(key)
    assert backend.calls == []


def test_open_missing_raises_file_not_found(backend: FakeGcsBackend) -> None:
    with pytest.raises(FileNotFoundError):
        store(backend).open(KEY)
    assert store(backend).versions(KEY) == ()


def test_logs_carry_names_and_generations_only(backend: FakeGcsBackend) -> None:
    keyring = hosted_keyring()
    plaintext = b"personal data of a customer\n" * 50
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, _sha(plaintext))
    context = encryption_context(TENANT, key)
    files = store(backend, sleeps=[])
    backend.faults.fail_next("upload", ServiceUnavailable())
    with log_guard.capture() as events:
        dek = _file_key(files, keyring, key, context)
        sealed = keyring.seal_file(dek, plaintext, context=context)
        files.put(key, io.BytesIO(sealed))
        files.put(key, io.BytesIO(sealed))  # kept
        with files.open(key) as stored:
            assert keyring.open_file(dek, stored.read(), context=context) == plaintext
    log_guard.check(events)
    dump = json.dumps(events, default=str)
    assert "gcp.retry" in dump and "files.gcs_kept_existing" in dump
    for secret in (dek.hex(), sealed.hex(), plaintext.decode(), str(plaintext)):
        assert secret not in dump
    assert all(isinstance(event.get("generation", 0), int) for event in events), (
        "generations are logged as numbers"
    )


def test_versions_lists_every_retained_generation(backend: FakeGcsBackend) -> None:
    files = store(backend)
    files.put(KEY, io.BytesIO(b"a"))
    g1 = files.live_generation(KEY)
    g2 = files.replace(KEY, g1, io.BytesIO(b"bb"))
    g3 = files.replace(KEY, g2, io.BytesIO(b"ccc"))
    files.delete_generation(KEY, g1)
    versions: tuple[Any, ...] = files.versions(KEY)
    assert [(v.generation, v.live, v.soft_deleted, v.size) for v in versions] == [
        (g1, False, True, 1),
        (g2, False, False, 2),
        (g3, True, False, 3),
    ]


def test_put_object_reports_whether_this_call_created_the_object(backend: FakeGcsBackend) -> None:
    """Codex probe F01/F02: a kept winner must be reported so the caller verifies its content."""
    files = store(backend)
    first = files.put_object(KEY, io.BytesIO(b"first"))
    assert (first.created, first.sha256, first.size) == (True, _sha(b"first"), 5)
    assert first.generation == files.live_generation(KEY)
    kept = files.put_object(KEY, io.BytesIO(b"planted same size"))
    assert (kept.created, kept.generation) == (False, first.generation)
    assert kept.sha256 == _sha(b"planted same size")
    # A lost response followed by a 412 on retry is this call's own object, reported conservatively
    # as kept, so the caller's verification still runs.
    other = FakeGcsBackend()
    other.faults.fail_next("upload", ServiceUnavailable(), ambiguous=True)
    lost = store(other, sleeps=[]).put_object(KEY, io.BytesIO(b"bytes"))
    assert not lost.created and lost.generation == other.versions_of(BUCKET, KEY)[0].generation
