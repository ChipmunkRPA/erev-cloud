"""File store KRN-FILE (docs/dev-guide.md §5.13; 04 T-PLT-29; 05 PRV-06, SAR-07, UPL-11; BUILD_SPEC
BS1-D-03, BS1-D-21).

Stored objects are immutable and content addressed. ``put`` streams into ``<root>/.incoming/<uuid>``
while hashing and then links the finished file onto its key in one atomic step, so a key never
names a partial object and an existing object is never replaced (DG-KRN-FILE-01, DG-KRN-FILE-02).

``store_file`` spools the upload once, checks it against the purpose's policy, and returns the
existing row when ``(tenant_id, sha256, purpose)`` exists. The key is
``<tenant>/<purpose>/<sha256>`` of the plaintext. Files of the PRV-06 purposes are stored as
AES-256-GCM ciphertext under a per-file data key whose wrapped form is the sidecar ``<key>.dek``.
The sidecar is written first and read back, so concurrent uploads of identical content agree on one
key. Its associated data names the storage key where SAR-07 names a row id, because identical
content shares one object (SPEC-Q-158).

Write contract (Codex probe of c37b002, F01 to F04): ``put_object`` reports whether the call
created the object or met an existing live winner; ``put_file`` serialises every writer of a storage
key on the DB advisory lock ``lock_storage_key``, verifies a kept winner's plaintext digest and size
before the ``file_object`` row is inserted (a same-size wrong object at the key fails closed), and
refuses to recreate a sidecar once the shred marker exists, re-checking the marker after the sidecar
write and deleting the generation it created when a shred landed in between. ``open_file`` checks
the marker before any sidecar read, so a restored sidecar generation never makes a shredded payload
readable.

Backends: ``LocalFileStore`` over a directory (compose and the local environments) and
``erev_api.adapters.storage.gcs.GcsFileStore`` over a bucket (hosted, CMP-05, CFG-05), selected by
``build_file_store``. Both create objects only if absent, never replace them, and expose the
``VersionedFileStore`` primitives that ``erev_api.files.lifecycle`` builds KEY-04 rewrap and PRV-07
shred on. A shredded sidecar leaves a marker object ``<storage_key>.dek.shredded`` behind, so no
later upload, rewrap or retry can recreate a usable sidecar (hosted runtime contract).
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, BinaryIO, Final, Protocol, cast
from uuid import UUID

from sqlalchemy import Connection, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from erev_api.auth.keyring import KeyRing
from erev_api.config import Settings, SettingsError
from erev_api.db import new_id
from erev_api.db.tables import file_object, tenant
from erev_api.enums import FilePurpose
from erev_api.files import policy
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

CHUNK_BYTES: Final = 1024 * 1024
INCOMING_DIR: Final = ".incoming"
SIDECAR_SUFFIX: Final = ".dek"
# Uploads above this size spool to TMPDIR (.run/tmp under make, DG-RUN-30).
SPOOL_MEMORY_BYTES: Final = 1024 * 1024
LOCAL_BACKEND: Final = "local"
GCS_BACKEND: Final = "gcs"
# PRV-07: the marker object left where a shredded sidecar was, `<storage_key>.dek.shredded`.
SHRED_MARKER_SUFFIX: Final = ".shredded"
SHRED_MARKER_BYTES: Final = b"erev shred marker\n"
# The local backend has one generation while an object exists (no versioning on a directory).
LOCAL_GENERATION: Final = 1
# 04 §15.4 FILE_SHREDDED.
SHREDDED_MESSAGE: Final = "This file was shredded. Its contents are no longer available."
# A key segment starts with a letter or digit, so no key reaches `.incoming` or `..`.
_SEGMENT: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


_LOGGER: Final = "erev_api.files.store"
register_logger_fields(
    _LOGGER,
    ("storage_key", "generation", "expected_size", "stored_size", "file_id", "tenant_id"),
)


@dataclass(frozen=True, slots=True)
class PutResult:
    """What ``put_object`` did: the digest and size of the streamed bytes, whether this call created
    the object (``False`` when a live object already occupied the key and was kept) and the
    generation of the object now at the key (``LOCAL_GENERATION`` locally)."""

    sha256: str
    size: int
    created: bool
    generation: int


class FileStore(Protocol):
    def put(self, storage_key: str, stream: BinaryIO) -> tuple[str, int]: ...  # (sha256 hex, size)
    def put_object(self, storage_key: str, stream: BinaryIO) -> PutResult: ...
    def open(self, storage_key: str) -> BinaryIO: ...
    def exists(self, storage_key: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ObjectVersion:
    """One retained generation of an object (hosted runtime contract §"Shredding")."""

    generation: int
    live: bool
    soft_deleted: bool = False
    hard_delete_at: datetime | None = None  # when a soft-deleted generation becomes irrecoverable
    size: int | None = None
    # The store's own instant of the generation's creation (the file's mtime locally, GCS
    # ``time_created``): a shred marker is written once and never replaced, so its instant is when
    # the destruction of the key began (05 PRV-07 b rev 1.171).
    created_at: datetime | None = None


class GenerationConflict(RuntimeError):
    """A conditional write or delete met a different live generation (HTTP 412 hosted)."""


class FileShredded(RuntimeError):
    """The sidecar carries a shred marker or has no live generation; nothing recreates it."""


class ForeignStorageKey(RuntimeError):
    """A ``file_object`` row names the object of a workspace that is neither the row's own nor
    the workspace its sandbox was copied from (05 SBX-03 rev 1.196). An integrity fault of the
    stored data, never a question of permission: the row does not open."""


class StoredObjectMismatch(RuntimeError):
    """The live object at a storage key does not hold the content the key names (a planted or
    corrupted object); no ``file_object`` row may reference it (OPR-13 fail closed)."""

    def __init__(self, storage_key: str, detail: str) -> None:
        super().__init__(f"{storage_key}: {detail}")
        self.storage_key = storage_key


@dataclass(frozen=True, slots=True)
class StoredObjectListing:
    """One live object a store lists for SCH-14: its key, the generation the listing saw (the
    generation a later delete addresses) and the store's own timestamp of the object."""

    storage_key: str
    generation: int
    updated_at: datetime | None


class SweepableFileStore(Protocol):
    """What ``erev_api.files.sweep`` (SCH-14) needs from a backend: the whole-store listing of
    live objects with their own timestamps, and the generation-addressed delete of
    ``VersionedFileStore``. A store without ``list_objects`` makes the sweep refuse by name."""

    backend: str

    def list_objects(self) -> tuple[StoredObjectListing, ...]: ...
    def delete_generation(self, storage_key: str, generation: int) -> None: ...
    def exists(self, storage_key: str) -> bool: ...


class VersionedFileStore(FileStore, Protocol):
    """The generation primitives ``erev_api.files.lifecycle`` needs from a backend.

    Generation 0 means no live object. ``replace`` is compare-and-swap on the live generation and
    never creates; ``delete_generation`` addresses one generation and is idempotent; ``versions``
    lists every retained generation, live, noncurrent and soft-deleted.
    """

    def live_generation(self, storage_key: str) -> int: ...
    def read_generation(self, storage_key: str, generation: int) -> bytes: ...
    def replace(self, storage_key: str, generation: int, stream: BinaryIO) -> int: ...
    def delete_generation(self, storage_key: str, generation: int) -> None: ...
    def versions(self, storage_key: str) -> tuple[ObjectVersion, ...]: ...


def check_storage_key(storage_key: str) -> list[str]:
    """The ``/``-separated segments of a valid key; ``ValueError`` for any other string."""
    segments = storage_key.split("/")
    if not all(_SEGMENT.fullmatch(segment) for segment in segments):
        raise ValueError(
            "a storage key is '/'-separated segments of letters, digits, '.', '_' and '-'"
        )
    return segments


class LocalFileStore:
    """``FileStore`` over a local directory (``settings.file_root``)."""

    backend: Final = LOCAL_BACKEND

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, storage_key: str) -> Path:
        return self._root.joinpath(*check_storage_key(storage_key))

    def _spool(self, stream: BinaryIO) -> tuple[Path, str, int]:
        """Stream into ``.incoming/<uuid>`` while hashing; the caller links or moves the file."""
        incoming = self._root / INCOMING_DIR
        incoming.mkdir(parents=True, exist_ok=True)
        partial = incoming / str(uuid.uuid4())
        digest = hashlib.sha256()
        size = 0
        with partial.open("xb") as out:
            while chunk := stream.read(CHUNK_BYTES):
                digest.update(chunk)
                out.write(chunk)
                size += len(chunk)
            out.flush()
            os.fsync(out.fileno())
        return partial, digest.hexdigest(), size

    def put(self, storage_key: str, stream: BinaryIO) -> tuple[str, int]:
        """Store ``stream`` at ``storage_key``; returns the SHA-256 and size of the bytes written.

        An interrupted write leaves its partial file under ``.incoming/`` and nothing at the key.
        When the key already holds an object, that object is kept. The key names the plaintext
        hash of an encrypted file, so the stored bytes need not hash to the key (SPEC-Q-158).
        """
        result = self.put_object(storage_key, stream)
        return result.sha256, result.size

    def put_object(self, storage_key: str, stream: BinaryIO) -> PutResult:
        """``put`` that also reports whether this call created the object (``os.link`` fails with
        ``FileExistsError`` when another writer's object is already at the key)."""
        target = self._path(storage_key)
        partial, sha256, size = self._spool(stream)
        created = True
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(partial, target)
            except FileExistsError:
                created = False
        finally:
            partial.unlink()
        return PutResult(sha256, size, created, LOCAL_GENERATION)

    def open(self, storage_key: str) -> BinaryIO:
        return self._path(storage_key).open("rb")

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).is_file()

    # VersionedFileStore: one generation while the file exists. The compose shape runs one node,
    # and the shred command serialises writers per storage key (lifecycle.lock_storage_key).

    def live_generation(self, storage_key: str) -> int:
        return LOCAL_GENERATION if self._path(storage_key).is_file() else 0

    def read_generation(self, storage_key: str, generation: int) -> bytes:
        if generation != LOCAL_GENERATION:
            raise FileNotFoundError(f"{storage_key}#{generation}")
        return self._path(storage_key).read_bytes()

    def replace(self, storage_key: str, generation: int, stream: BinaryIO) -> int:
        target = self._path(storage_key)
        if generation != LOCAL_GENERATION or not target.is_file():
            raise GenerationConflict(f"{storage_key} is not live at generation {generation}")
        partial, _, _ = self._spool(stream)
        os.replace(partial, target)
        return LOCAL_GENERATION

    def delete_generation(self, storage_key: str, generation: int) -> None:
        if generation != LOCAL_GENERATION:
            return
        try:
            self._path(storage_key).unlink()
        except FileNotFoundError:
            pass

    def versions(self, storage_key: str) -> tuple[ObjectVersion, ...]:
        target = self._path(storage_key)
        try:
            found = target.stat()
        except FileNotFoundError:
            return ()
        if not target.is_file():
            return ()
        return (
            ObjectVersion(
                LOCAL_GENERATION,
                live=True,
                size=found.st_size,
                created_at=datetime.fromtimestamp(found.st_mtime, UTC),
            ),
        )

    def remove_partial(self, listed_key: str) -> None:
        """SCH-14: unlink one partial spool the listing named as ``.incoming/<uuid>`` — the only
        path that reaches ``.incoming/`` (storage keys never do); anything else is refused."""
        prefix = f"{INCOMING_DIR}/"
        name = listed_key.removeprefix(prefix)
        if not listed_key.startswith(prefix) or "/" in name or not name:
            raise ValueError(f"{listed_key!r} is not a partial spool under {INCOMING_DIR}/")
        try:
            (self._root / INCOMING_DIR / name).unlink()
        except FileNotFoundError:
            pass

    def list_objects(self) -> tuple[StoredObjectListing, ...]:
        """SCH-14: every file under the root — a partial spool appears as ``.incoming/<uuid>`` —
        keyed by its ``/``-joined relative path, stamped with the file's own mtime (UTC)."""
        if not self._root.is_dir():
            return ()
        listings: list[StoredObjectListing] = []
        for path in sorted(item for item in self._root.rglob("*") if item.is_file()):
            try:
                stamp = path.stat().st_mtime
            except FileNotFoundError:
                # SCH14-R1 (D-98 138-A2): an entry that vanished between the inventory and its
                # stat — a `put_object` linking its `.incoming` spool away — is not an object now;
                # other permission / I/O errors still propagate.
                continue
            listings.append(
                StoredObjectListing(
                    path.relative_to(self._root).as_posix(),
                    LOCAL_GENERATION,
                    datetime.fromtimestamp(stamp, UTC),
                )
            )
        return tuple(listings)


def storage_key_lock_id(storage_key: str) -> int:
    """A stable signed 63-bit advisory lock id for a storage key."""
    digest = hashlib.sha256(storage_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


def lock_storage_key(session: Session | Connection, storage_key: str) -> None:
    """Serialise upload, rewrap and shred of one storage key for the rest of the transaction
    (``pg_advisory_xact_lock``): every writer path of a key takes this lock before it touches the
    key's objects, so a shred cannot interleave with an upload or a rewrap of the same key."""
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": storage_key_lock_id(storage_key)},
    )


def build_file_store(settings: Settings, *, client: Any | None = None) -> FileStore:
    """Composition roots only (DG-KRN-CFG-01): the backend follows ``EREV_FILE_BACKEND`` (CFG-05).

    ``Settings`` already refuses ``gcs`` without its buckets or outside production; the check here
    keeps the factory fail-closed on its own. ``client`` exists for tests, which never construct a
    real Google client (DG-KRN-FILE-05).
    """
    if settings.file_backend == LOCAL_BACKEND:
        return LocalFileStore(settings.file_root)
    if settings.gcs_files_bucket is None:
        raise SettingsError("EREV_FILE_BACKEND=gcs requires EREV_GCS_FILES_BUCKET")
    from erev_api.adapters.storage.gcs import GcsFileStore

    return GcsFileStore(settings.gcs_files_bucket, client=client)


@dataclass(frozen=True, slots=True)
class StoredFile:
    row: Mapping[str, Any]
    created: bool  # False when an existing row of the same content and purpose was returned


def storage_key(tenant_id: UUID, purpose: FilePurpose, sha256: str) -> str:
    """T-PLT-29 ``storage_key``: ``<tenant_id>/<purpose>/<sha256>`` (UPL-11)."""
    return f"{tenant_id}/{purpose.value}/{sha256}"


def owns_key(tenant_id: UUID, key: str) -> bool:
    """Whether the object at ``key`` is the tenant's own: the key has the form ``storage_key``
    writes and its first segment is the tenant's id. The rows of a sandbox copy carry the keys of
    their source (05 SBX-03), and this is how a sandbox tells what it stored itself from what it
    shares (SBX-08: it destroys nothing it shares). A key of any other form — no separator, an
    empty first segment, another case — is nobody's own: the answer is False, never an error.
    ``tests/unit/test_sandbox_guard.py`` pins this against ``storage_key`` itself, so that a
    change of the key's form closes the door and does not open it."""
    segments = key.split("/")
    return len(segments) == 3 and segments[0] == str(tenant_id)


def key_tenant(key: str) -> UUID | None:
    """The workspace that stored the object at ``key``: the first segment of a key of the form
    ``storage_key`` writes, read as ``owns_key`` reads it (three segments, the first a workspace
    id as ``str(UUID)`` spells it). None for a key of any other form.
    ``tests/unit/test_sandbox_guard.py`` pins it against ``storage_key`` itself."""
    segments = key.split("/")
    if len(segments) != 3:
        return None
    try:
        stored_by = UUID(segments[0])
    except ValueError:
        return None
    return stored_by if str(stored_by) == segments[0] else None


def content_tenant(tenant_id: UUID, key: str, *, source_tenant_id: UUID | None) -> UUID | None:
    """The workspace the associated data of the content at ``key`` names, for a row of
    ``tenant_id`` (05 SAR-07, SBX-03 rev 1.196; item SBX-FILE-READ-1): the workspace that STORED
    the object. That is the row's own workspace — also for a key of another form, as before —
    or, for a row of a sandbox copy, the workspace the sandbox was copied from: a copy carries
    its source's rows with their keys and shares the objects and their wrapped keys, which were
    sealed under the source's id. Any other workspace is no one the row may open: None.

    Until this rule the row's own workspace was named always, so a copy could open no copied
    file stored under a data key (measured: the download 500 without a ``file.download`` event,
    the verifier ``undecryptable``). The rule opens no door: what stopped a row from opening
    another workspace's object was the mismatch of the two ids, and it still does for every
    workspace but the one source."""
    stored_by = key_tenant(key)
    if stored_by is None or stored_by == tenant_id:
        return tenant_id
    if source_tenant_id is not None and stored_by == source_tenant_id:
        return stored_by
    return None


def sidecar_key(key: str) -> str:
    """05 PRV-06: the wrapped data key of a file lives at ``<storage_key>.dek``."""
    return key + SIDECAR_SUFFIX


def shred_marker_key(key: str) -> str:
    """PRV-07: the durable marker a shred leaves at ``<storage_key>.dek.shredded``."""
    return sidecar_key(key) + SHRED_MARKER_SUFFIX


def _shredded_problem(slug: str) -> Problem:
    return Problem(slug, errors=[ProblemError(rule_id="FILE_SHREDDED", message=SHREDDED_MESSAGE)])


def encryption_context(tenant_id: UUID, key: str) -> dict[str, str]:
    """SAR-07 associated data of a stored file (SPEC-Q-158)."""
    return {"tenant_id": str(tenant_id), "table": "file_object", "column": "content", "row_id": key}


def _spool(stream: BinaryIO, spool: BinaryIO, limit: int | None) -> tuple[str, int]:
    """Copy ``stream`` into ``spool`` while hashing; stops once the size exceeds ``limit``."""
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK_BYTES):
        size += len(chunk)
        if limit is not None and size > limit:
            break
        digest.update(chunk)
        spool.write(chunk)
    spool.seek(0)
    return digest.hexdigest(), size


def _file_key(files: FileStore, keyring: KeyRing, key: str, context: Mapping[str, str]) -> bytes:
    """The data key every writer of ``key`` agrees on: create the sidecar if absent, then read the
    winning sidecar back and unwrap it (authenticated by the KEK and the context), so no writer
    ever encrypts under a losing candidate key. A shred marker refuses the whole upload with 409
    ``FILE_SHREDDED``: a shredded object is never given a fresh usable sidecar (PRV-07)."""
    marker = shred_marker_key(key)
    if files.exists(marker):
        raise _shredded_problem("invalid-transition")
    sidecar = sidecar_key(key)
    if not files.exists(sidecar):
        _, blob = keyring.new_file_key(context=context)
        written = files.put_object(sidecar, io.BytesIO(blob))  # a concurrent sidecar is kept
        if files.exists(marker):
            # A shred completed between the marker check and the write: the generation this call
            # created must not survive it (the shred's passes delete it too; belt and braces).
            if written.created:
                delete = getattr(files, "delete_generation", None)
                if callable(delete):
                    delete(sidecar, written.generation)
            raise _shredded_problem("invalid-transition")
    with files.open(sidecar) as stored:
        return keyring.file_key(stored.read(), context=context)


def _verify_kept_object(
    files: FileStore,
    key: str,
    *,
    expected_sha256: str,
    expected_size: int,
    plaintext_of: Callable[[bytes], bytes],
) -> None:
    """A live object already occupied ``key`` when this upload arrived: it is the winner only if
    it holds this content (identical plaintext; ciphertexts differ by nonce). Anything else is a
    planted or corrupted object and the reference is never written (Codex probe F01/F02)."""
    with files.open(key) as stored:
        stored_bytes = stored.read()
    try:
        plaintext = plaintext_of(stored_bytes)
    except Exception as error:  # InvalidTag under a different key or content
        get_logger(_LOGGER).warning(
            "files.stored_object_mismatch", storage_key=key, error_code=type(error).__name__
        )
        raise StoredObjectMismatch(key, "the stored object does not open under this key") from None
    if len(plaintext) != expected_size or hashlib.sha256(plaintext).hexdigest() != expected_sha256:
        get_logger(_LOGGER).warning(
            "files.stored_object_mismatch",
            storage_key=key,
            expected_size=expected_size,
            stored_size=len(plaintext),
        )
        raise StoredObjectMismatch(key, "the stored object holds different content")


def _existing(session: Session, tenant_id: UUID, sha256: str, purpose: FilePurpose) -> Any:
    return (
        session.execute(
            select(file_object).where(
                file_object.c.tenant_id == tenant_id,
                file_object.c.sha256 == sha256,
                file_object.c.purpose == purpose.value,
            )
        )
        .mappings()
        .one_or_none()
    )


def _admit(row: Any) -> Any:
    """The retained row for a content identity, or ``None`` — never a SHREDDED row. Identical
    bytes uploaded after ``file.shred`` are refused by name, 409 ``invalid-transition`` /
    ``FILE_SHREDDED``, before any lock, sidecar or object write, so an upload never binds to a row
    whose content ``open_file`` refuses; the shredded row stays the sole row for that content
    identity (PRV-07; 04 T-PLT-29 rev 1.73; D-98 145 Amendment 2, FILES-SHRED-1). A fresh row for
    re-uploaded bytes is not taken for 1.0."""
    if row is not None and row["shredded_at"] is not None:
        raise _shredded_problem("invalid-transition")
    return row


def _retained(session: Session, tenant_id: UUID, sha256: str, purpose: FilePurpose) -> Any:
    return _admit(_existing(session, tenant_id, sha256, purpose))


def put_file(
    uow: UnitOfWork,
    *,
    purpose: FilePurpose,
    stream: BinaryIO,
    original_filename: str | None,
    media_type: str,
) -> StoredFile:
    """``store_file`` that also reports whether the row was created."""
    purpose = FilePurpose(purpose)
    tenant_id = uow.principal.tenant_id
    with tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES) as spooled:
        spool = cast(BinaryIO, spooled)
        sha256, size = _spool(stream, spool, policy.UPLOAD_LIMITS.get(purpose))
        if purpose in policy.UPLOADABLE_PURPOSES:
            media_type = policy.check_upload(
                purpose, spool, size=size, original_filename=original_filename
            )
        elif size == 0:
            raise ValueError("a stored file holds at least one byte (T-PLT-29)")
        existing = _retained(uow.session, tenant_id, sha256, purpose)
        if existing is not None:
            return StoredFile(row=MappingProxyType(dict(existing)), created=False)
        key = storage_key(tenant_id, purpose, sha256)
        # Every writer of a key serialises here for the rest of the transaction, so a shred or a
        # rewrap of the same key cannot interleave with this upload (Codex probe F04).
        lock_storage_key(uow.session, key)
        if purpose in policy.ENCRYPTED_PURPOSES:
            context = encryption_context(tenant_id, key)
            dek = _file_key(uow.files, uow.keyring, key, context)
            sealed = uow.keyring.seal_file(dek, spool.read(), context=context)
            stored = uow.files.put_object(key, io.BytesIO(sealed))
            if not stored.created:
                _verify_kept_object(
                    uow.files,
                    key,
                    expected_sha256=sha256,
                    expected_size=size,
                    plaintext_of=lambda data: uow.keyring.open_file(dek, data, context=context),
                )
        else:
            stored = uow.files.put_object(key, spool)
            if not stored.created:
                _verify_kept_object(
                    uow.files,
                    key,
                    expected_sha256=sha256,
                    expected_size=size,
                    plaintext_of=lambda data: data,
                )
    principal = uow.principal
    inserted = (
        uow.session.execute(
            insert(file_object)
            .values(
                tenant_id=tenant_id,
                id=new_id(),
                sha256=sha256,
                size_bytes=size,
                media_type=media_type,
                original_filename=original_filename,
                purpose=purpose.value,
                storage_backend=str(getattr(uow.files, "backend", LOCAL_BACKEND)),
                storage_key=key,
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "sha256", "purpose"])
            .returning(*file_object.c)
        )
        .mappings()
        .one_or_none()
    )
    if inserted is None:  # a concurrent upload of the same content committed first
        row = _retained(uow.session, tenant_id, sha256, purpose)  # a shredded winner is refused
        return StoredFile(row=MappingProxyType(dict(row)), created=False)
    return StoredFile(row=MappingProxyType(dict(inserted)), created=True)


def store_file(
    uow: UnitOfWork,
    *,
    purpose: FilePurpose,
    stream: BinaryIO,
    original_filename: str | None,
    media_type: str,
) -> Mapping[str, Any]:
    """Validate and store a file, returning its ``file_object`` row (DG-KRN-FILE-01).

    Uploadable purposes pass ``policy.check_upload``, whose detected type replaces ``media_type``
    (UPL-02); system purposes keep the given type. No audit event is written here: the command
    that stores the file audits it (T-PLT-29 AUD-FACT).
    """
    return put_file(
        uow,
        purpose=purpose,
        stream=stream,
        original_filename=original_filename,
        media_type=media_type,
    ).row


def open_file(
    session: Session, file_object_id: UUID, *, files: FileStore, keyring: KeyRing
) -> tuple[Mapping[str, Any], BinaryIO]:
    """The visible row and a plaintext stream; 404 ``not-found``, with ``FILE_SHREDDED`` when the
    sidecar was destroyed (T-PLT-29). ``files`` and ``keyring`` extend the binding signature,
    because decryption needs both (SPEC-Q-158)."""
    row = (
        session.execute(select(file_object).where(file_object.c.id == file_object_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    if row["shredded_at"] is not None:
        raise Problem(
            "not-found", errors=[ProblemError(rule_id="FILE_SHREDDED", message=SHREDDED_MESSAGE)]
        )
    key = str(row["storage_key"])
    stored_by = _content_workspace(session, row)
    if FilePurpose(row["purpose"]) not in policy.ENCRYPTED_PURPOSES:
        return MappingProxyType(dict(row)), files.open(key)
    context = encryption_context(stored_by, key)
    # The shred marker is the durable erasure state (PRV-07, OPR-11): a database restored to before
    # the shred, or a sidecar generation restored from soft delete, never makes the payload
    # readable (Codex probe F03).
    if files.exists(shred_marker_key(key)):
        raise _shredded_problem("not-found")
    with files.open(sidecar_key(key)) as stored_key:
        dek = keyring.file_key(stored_key.read(), context=context)
    with files.open(key) as stored:
        plaintext = keyring.open_file(dek, stored.read(), context=context)
    return MappingProxyType(dict(row)), io.BytesIO(plaintext)


def _content_workspace(session: Session, row: Mapping[Any, Any]) -> UUID:
    """``content_tenant`` for a row read in ``session``. The row's own ``tenant`` row is read
    only when the key names another workspace — a copied row — and tells whether that workspace
    is the source of this sandbox (the session's context admits its own tenant row, RLS-TN). A
    key of any other workspace is logged by name and refused as ``ForeignStorageKey``: the
    caller answers 500, as an integrity fault is answered, and writes nothing."""
    tenant_id = UUID(str(row["tenant_id"]))
    key = str(row["storage_key"])
    stored_by = key_tenant(key)
    if stored_by is None or stored_by == tenant_id:
        return tenant_id
    source = session.execute(
        select(tenant.c.source_tenant_id).where(tenant.c.id == tenant_id)
    ).scalar_one_or_none()
    found = content_tenant(
        tenant_id, key, source_tenant_id=None if source is None else UUID(str(source))
    )
    if found is None:
        get_logger(_LOGGER).error(
            "files.foreign_storage_key",
            file_id=str(row["id"]),
            tenant_id=str(tenant_id),
            storage_key=key,
        )
        raise ForeignStorageKey(f"file {row['id']} names the object of another workspace")
    return found


def lock_readable(session: Session, file_ids: Iterable[Any]) -> frozenset[UUID]:
    """Lock the ``file_object`` rows of ``file_ids`` FOR SHARE, in id order, to the end of the
    caller's transaction, and answer those whose content can still be read — not shredded (04
    T-PLT-29 "A document a rule asks for", rev 1.216; rulings R-119 (g), R-120 (g)).

    A command that counts a stored file as the document a rule asks for — or that makes a record
    hold it — reads the file here. ``file.shred`` takes the same row FOR UPDATE before it reads
    the records that hold the file, so the later of the two sees what the earlier committed: a
    shred that waited finds the record and is refused by reference; a command that waited finds
    the file shredded. Reading ``shredded_at`` without the lock leaves a window in which neither
    sees the other. A share lock lets two such commands count one file at the same time."""
    ids = sorted({UUID(str(value)) for value in file_ids})
    if not ids:
        return frozenset()
    rows = session.execute(
        select(file_object.c.id, file_object.c.shredded_at)
        .where(file_object.c.id.in_(ids))
        .order_by(file_object.c.id)
        .with_for_update(read=True)
    )
    return frozenset(UUID(str(row.id)) for row in rows if row.shredded_at is None)
