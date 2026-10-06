"""Local file store KRN-FILE (dev-guide §5.13 DG-KRN-FILE-01, DG-KRN-FILE-02; BS1-D-03)."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from erev_api.files.store import LocalFileStore


class ProbeStream(io.RawIOBase):
    """Yields ``chunks`` one per read, calling ``on_read`` first; raises after them when told."""

    def __init__(self, chunks: list[bytes], *, fail: bool = False, on_read=None) -> None:  # type: ignore[no-untyped-def]
        self._chunks = list(chunks)
        self._fail = fail
        self._on_read = on_read

    def read(self, size: int = -1) -> bytes:
        if self._on_read is not None:
            self._on_read()
        if self._chunks:
            return self._chunks.pop(0)
        if self._fail:
            raise OSError("connection reset while uploading")
        return b""


def test_put_is_content_addressed_and_atomic(tmp_path: Path) -> None:
    store = LocalFileStore(tmp_path)
    data = b"eRev attachment line\n" * 5000
    sha = hashlib.sha256(data).hexdigest()
    key = f"t1/ATTACHMENT/{sha}"
    seen_before_completion: list[bool] = []

    stream = ProbeStream(
        [data[:40_000], data[40_000:]],
        on_read=lambda: seen_before_completion.append(store.exists(key)),
    )
    assert store.put(key, stream) == (sha, len(data))  # type: ignore[arg-type]
    assert seen_before_completion == [False, False, False]
    assert store.exists(key)
    with store.open(key) as stored:
        assert stored.read() == data
    assert list((tmp_path / ".incoming").iterdir()) == []

    partial = b"partial upload"
    partial_key = f"t1/ATTACHMENT/{hashlib.sha256(partial + b'rest').hexdigest()}"
    with pytest.raises(OSError):
        store.put(partial_key, ProbeStream([partial], fail=True))  # type: ignore[arg-type]
    (incoming,) = list((tmp_path / ".incoming").iterdir())
    assert incoming.read_bytes() == partial
    assert not store.exists(partial_key)
    assert not (tmp_path / partial_key).exists()


def test_put_stores_ciphertext_under_the_plaintext_key(tmp_path: Path) -> None:
    # PRV-06: the key names the plaintext SHA-256 while the object holds ciphertext (SPEC-Q-158);
    # put reports the hash of the bytes it wrote and never replaces them.
    store = LocalFileStore(tmp_path)
    key = "t1/ATTACHMENT/" + hashlib.sha256(b"plaintext").hexdigest()
    assert store.put(key, io.BytesIO(b"ciphertext")) == (
        hashlib.sha256(b"ciphertext").hexdigest(),
        10,
    )
    store.put(key, io.BytesIO(b"other ciphertext"))
    with store.open(key) as stored:
        assert stored.read() == b"ciphertext"
    assert list((tmp_path / ".incoming").iterdir()) == []


def test_existing_objects_are_never_replaced(tmp_path: Path) -> None:
    store = LocalFileStore(tmp_path)
    assert store.put("health/probe", io.BytesIO(b"first")) == (
        hashlib.sha256(b"first").hexdigest(),
        5,
    )
    store.put("health/probe", io.BytesIO(b"second"))
    with store.open("health/probe") as stored:
        assert stored.read() == b"first"


@pytest.mark.parametrize("key", ["../escape", "/absolute", "t1//x", "t1/.incoming/x", "t1/a b"])
def test_invalid_storage_keys_raise(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        LocalFileStore(tmp_path).exists(key)


def test_put_object_reports_a_kept_winner(tmp_path: Path) -> None:
    """Lane P2 (Codex probe F01): the local store reports whether this call created the object."""
    store = LocalFileStore(tmp_path)
    first = store.put_object("t1/ATTACHMENT/k", io.BytesIO(b"first"))
    assert (first.created, first.generation, first.size) == (True, 1, 5)
    kept = store.put_object("t1/ATTACHMENT/k", io.BytesIO(b"other"))
    assert (kept.created, kept.generation) == (False, 1)
    assert kept.sha256 == hashlib.sha256(b"other").hexdigest()
    with store.open("t1/ATTACHMENT/k") as stored:
        assert stored.read() == b"first"
    assert store.put("t1/ATTACHMENT/k", io.BytesIO(b"third")) == (
        hashlib.sha256(b"third").hexdigest(),
        5,
    )
