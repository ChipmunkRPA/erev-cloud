"""Cloud Storage file store (05 CMP-05, CFG-05, CFG-07, OPR-09, OPR-13, PRV-06, PRV-07;
DG-KRN-FILE-05; hosted runtime contract §"GCS immutable file and wrapped-key contract").

Shared by every api and worker instance through the object API (never a mounted bucket). The
protocol derived from Cloud Storage's guarantees, which are per-object atomicity and strong
read-after-write consistency but no cross-object or cross-system transaction:

- ``put`` creates with ``if_generation_match=0``. A 412 means a live object already won; it is
  kept, verified to exist, and reported as the stored object. There is never an existence check
  followed by an unconditional upload, and never an overwrite.
- ``open`` reads the live object at the exact generation it was found at; ``read_generation``
  reads one named generation.
- ``replace`` is compare-and-swap on the live generation (``if_generation_match=g``) and never
  creates; ``delete_generation`` addresses one generation with the matching condition, so a retry
  never deletes a replacement; ``patch_metadata`` matches generation and metageneration together.
- ``versions`` enumerates live, noncurrent and soft-deleted generations with their hard-delete
  time, the residual retention PRV-07 makes irreversibility contingent on.
- Transient failures retry with the same preconditions and bounded backoff (``call_with_retry``).

Generation 0 is "no live object", not "never existed": the shred marker of
``erev_api.files.lifecycle`` is the durable state that stops a sidecar from being recreated.
Uploads spool to a temporary file first (TMPDIR, DG-RUN-30), so an interrupted client stream
never reaches the bucket. Logs carry bucket, key and generation only, never object bytes.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
import time
from collections.abc import Callable, Mapping
from typing import Any, BinaryIO, Final, cast

from erev_api.adapters import gcp
from erev_api.adapters.gcp import GcpError, Sleep, call_with_retry
from erev_api.files.store import (
    CHUNK_BYTES,
    GCS_BACKEND,
    SPOOL_MEMORY_BYTES,
    GenerationConflict,
    ObjectVersion,
    PutResult,
    StoredObjectListing,
    check_storage_key,
)
from erev_api.logging import get_logger, register_logger_fields

CONTENT_TYPE: Final = "application/octet-stream"
_LOGGER: Final = "erev_api.adapters.storage.gcs"

register_logger_fields(_LOGGER, ("bucket", "storage_key", "generation"))


def spool_stream(stream: BinaryIO, spool: BinaryIO) -> tuple[str, int]:
    """Copy ``stream`` into ``spool`` while hashing, then rewind; (sha256 hex, size)."""
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK_BYTES):
        digest.update(chunk)
        spool.write(chunk)
        size += len(chunk)
    spool.seek(0)
    return digest.hexdigest(), size


class GcsFileStore:
    """``VersionedFileStore`` over one bucket, with the process identity (ADC) unless a client is
    injected; tests inject an in-process fake and never reach a bucket (DG-KRN-FILE-05)."""

    backend: Final = GCS_BACKEND

    def __init__(
        self, bucket: str, *, client: Any | None = None, sleep: Sleep = time.sleep
    ) -> None:
        self._client = gcp.make_client("storage") if client is None else client
        self._bucket_name = bucket
        self._bucket = self._client.bucket(bucket)
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"GcsFileStore(bucket={self._bucket_name!r})"

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def _resource(self, key: str) -> str:
        return f"gs://{self._bucket_name}/{key}"

    def _call(self, operation: str, key: str, call: Callable[[], Any]) -> Any:
        return call_with_retry(operation, self._resource(key), call, sleep=self._sleep)

    def _live(self, key: str) -> Any | None:
        return self._call("get", key, lambda: self._bucket.get_blob(key))

    def _upload(self, key: str, spool: BinaryIO, size: int, *, if_generation_match: int) -> int:
        """Upload the spooled bytes under the given generation condition; the new generation."""
        blob = self._bucket.blob(key)

        def upload() -> None:
            spool.seek(0)
            blob.upload_from_file(
                spool,
                size=size,
                content_type=CONTENT_TYPE,
                if_generation_match=if_generation_match,
                retry=None,
            )

        self._call("upload", key, upload)
        generation = getattr(blob, "generation", None)
        if generation is None:
            live = self._live(key)
            if live is None:
                raise GcpError(
                    "other", "upload", self._resource(key), RuntimeError("no live object")
                )
            generation = live.generation
        return int(generation)

    # FileStore

    def put(self, storage_key: str, stream: BinaryIO) -> tuple[str, int]:
        result = self.put_object(storage_key, stream)
        return result.sha256, result.size

    def put_object(self, storage_key: str, stream: BinaryIO) -> PutResult:
        """Create-if-absent; the SHA-256 and size of the streamed bytes (SPEC-Q-158) and whether
        this call created the object.

        When a live object already exists (a concurrent writer, a planted object, or this
        process's own upload whose response was lost) it is kept, verified to exist and reported
        with ``created=False`` so the caller verifies its content before referencing it; the
        freshly uploaded object is verified durable at its generation (OPR-13).
        """
        check_storage_key(storage_key)
        log = get_logger(_LOGGER)
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES) as spooled:
            spool = cast(BinaryIO, spooled)
            sha256, size = spool_stream(stream, spool)
            try:
                generation = self._upload(storage_key, spool, size, if_generation_match=0)
            except GcpError as error:
                if error.kind != "precondition_failed":
                    raise
                winner = self._live(storage_key)
                if winner is None:
                    raise GcpError(
                        "precondition_failed",
                        "upload",
                        self._resource(storage_key),
                        RuntimeError("412 without a live object"),
                    ) from None
                log.info(
                    "files.gcs_kept_existing",
                    bucket=self._bucket_name,
                    storage_key=storage_key,
                    generation=int(winner.generation),
                )
                return PutResult(sha256, size, False, int(winner.generation))
            stored = self._call(
                "get",
                storage_key,
                lambda: self._bucket.get_blob(storage_key, generation=generation),
            )
            if stored is None or int(stored.size) != size:
                raise GcpError(
                    "other",
                    "verify",
                    self._resource(storage_key),
                    RuntimeError("uploaded object is not durable at its generation"),
                )
        return PutResult(sha256, size, True, generation)

    def open(self, storage_key: str) -> BinaryIO:
        live = self._live(storage_key)
        if live is None:
            raise FileNotFoundError(storage_key)
        return io.BytesIO(self.read_generation(storage_key, int(live.generation)))

    def exists(self, storage_key: str) -> bool:
        check_storage_key(storage_key)
        return self._live(storage_key) is not None

    # VersionedFileStore

    def live_generation(self, storage_key: str) -> int:
        check_storage_key(storage_key)
        live = self._live(storage_key)
        return 0 if live is None else int(live.generation)

    def read_generation(self, storage_key: str, generation: int) -> bytes:
        check_storage_key(storage_key)
        blob = self._bucket.blob(storage_key, generation=generation)
        try:
            data = self._call(
                "download",
                storage_key,
                lambda: blob.download_as_bytes(if_generation_match=generation, retry=None),
            )
        except GcpError as error:
            if error.kind in ("not_found", "precondition_failed"):
                raise FileNotFoundError(f"{storage_key}#{generation}") from None
            raise
        return bytes(data)

    def replace(self, storage_key: str, generation: int, stream: BinaryIO) -> int:
        check_storage_key(storage_key)
        if generation < 1:
            raise GenerationConflict(f"{storage_key} has no live generation to replace")
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES) as spooled:
            spool = cast(BinaryIO, spooled)
            _, size = spool_stream(stream, spool)
            try:
                return self._upload(storage_key, spool, size, if_generation_match=generation)
            except GcpError as error:
                if error.kind == "precondition_failed":
                    raise GenerationConflict(
                        f"{storage_key} is not live at generation {generation}"
                    ) from None
                raise

    def delete_generation(self, storage_key: str, generation: int) -> None:
        check_storage_key(storage_key)
        blob = self._bucket.blob(storage_key, generation=generation)
        try:
            self._call(
                "delete",
                storage_key,
                lambda: blob.delete(if_generation_match=generation, retry=None),
            )
        except GcpError as error:
            if error.kind == "not_found":
                return  # already gone; a retry never touches a replacement generation
            if error.kind == "precondition_failed":
                raise GenerationConflict(
                    f"{storage_key} generation {generation} is not the addressed generation"
                ) from None
            raise

    def list_objects(self) -> tuple[StoredObjectListing, ...]:
        """SCH-14: every live object of the bucket with the generation the listing saw and the
        object's own ``updated`` timestamp (no versions, no soft-deleted generations)."""
        blobs = self._call("list", "", lambda: list(self._bucket.list_blobs()))
        return tuple(
            StoredObjectListing(
                str(blob.name), int(blob.generation), getattr(blob, "updated", None)
            )
            for blob in blobs
        )

    def versions(self, storage_key: str) -> tuple[ObjectVersion, ...]:
        check_storage_key(storage_key)
        retained = self._call(
            "list",
            storage_key,
            lambda: list(self._bucket.list_blobs(prefix=storage_key, versions=True)),
        )
        soft_deleted = self._call(
            "list",
            storage_key,
            lambda: list(self._bucket.list_blobs(prefix=storage_key, soft_deleted=True)),
        )
        found = [
            ObjectVersion(
                int(blob.generation),
                live=getattr(blob, "time_deleted", None) is None,
                size=None if blob.size is None else int(blob.size),
                created_at=getattr(blob, "time_created", None),
            )
            for blob in retained
            if blob.name == storage_key
        ]
        found += [
            ObjectVersion(
                int(blob.generation),
                live=False,
                soft_deleted=True,
                hard_delete_at=getattr(blob, "hard_delete_time", None),
                size=None if blob.size is None else int(blob.size),
                created_at=getattr(blob, "time_created", None),
            )
            for blob in soft_deleted
            if blob.name == storage_key
        ]
        return tuple(sorted(found, key=lambda version: version.generation))

    # Metadata

    def metadata_generations(self, storage_key: str) -> tuple[int, int]:
        """(generation, metageneration) of the live object."""
        live = self._live(storage_key)
        if live is None:
            raise FileNotFoundError(storage_key)
        return int(live.generation), int(live.metageneration)

    def patch_metadata(
        self,
        storage_key: str,
        *,
        generation: int,
        metageneration: int,
        metadata: Mapping[str, str],
    ) -> int:
        """Set custom metadata on the live object only when both its generation and its
        metageneration still match; the new metageneration."""
        check_storage_key(storage_key)
        blob = self._bucket.blob(storage_key)
        blob.metadata = dict(metadata)
        try:
            self._call(
                "patch",
                storage_key,
                lambda: blob.patch(
                    if_generation_match=generation,
                    if_metageneration_match=metageneration,
                    retry=None,
                ),
            )
        except GcpError as error:
            if error.kind == "precondition_failed":
                raise GenerationConflict(
                    f"{storage_key} is not at generation {generation} and metageneration "
                    f"{metageneration}"
                ) from None
            raise
        return int(blob.metageneration)
