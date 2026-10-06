"""In-process Cloud Storage fake honouring generations, metagenerations, request preconditions,
object versioning and soft delete, with per-client IAM permission sets (DG-KRN-FILE-05: tests
never reach a real bucket).

Semantics follow Cloud Storage's documented behaviour as the hosted runtime contract summarises
it: ``if_generation_match=0`` succeeds only without a live object (noncurrent and soft-deleted
generations do not block it); replacing a live object makes the old generation noncurrent;
deleting a generation makes it soft-deleted until its hard-delete time; a generation mismatch is
a 412; permission is checked before any precondition, so a creator-only client can meet a 412 it
cannot read past. Faults can be injected per operation, including the ambiguous success where the
operation is applied and the response is lost.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO, Final

from support.fake_gcp import FaultInjector, Forbidden, NotFound, PreconditionFailed

OBJECT_ADMIN: Final = frozenset({"create", "get", "list", "delete", "update"})
OBJECT_CREATOR: Final = frozenset({"create"})
OBJECT_VIEWER: Final = frozenset({"get", "list"})
DEFAULT_NOW: Final = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class Version:
    generation: int
    data: bytes
    content_type: str | None
    metadata: dict[str, str] = field(default_factory=dict)
    metageneration: int = 1
    noncurrent_since: datetime | None = None
    soft_deleted_at: datetime | None = None
    hard_delete_at: datetime | None = None
    updated: datetime | None = (
        None  # the object's own timestamp (``blob.updated``); SCH-14 ages by it
    )
    # when the generation was created (``blob.time_created``); a metadata patch moves
    # ``updated`` and never this
    created: datetime | None = None

    @property
    def live(self) -> bool:
        return self.noncurrent_since is None and self.soft_deleted_at is None

    @property
    def soft_deleted(self) -> bool:
        return self.soft_deleted_at is not None


class FakeGcsBackend:
    """Bucket state shared by every client built from it; one lock serialises operations."""

    def __init__(
        self,
        *,
        now: datetime = DEFAULT_NOW,
        soft_delete_retention: timedelta = timedelta(days=7),
    ) -> None:
        self._objects: dict[str, dict[str, list[Version]]] = {}
        self._generation = 1000
        self.lock = threading.RLock()
        self.now = now
        self.soft_delete_retention = soft_delete_retention
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.faults = FaultInjector()

    def client(self, permissions: frozenset[str] = OBJECT_ADMIN) -> FakeGcsClient:
        return FakeGcsClient(self, permissions)

    # Inspection helpers for assertions

    def versions_of(self, bucket: str, name: str) -> list[Version]:
        return list(self._objects.get(bucket, {}).get(name, []))

    def live(self, bucket: str, name: str) -> Version | None:
        for version in self.versions_of(bucket, name):
            if version.live:
                return version
        return None

    def object_names(self, bucket: str) -> list[str]:
        return sorted(
            name
            for name, versions in self._objects.get(bucket, {}).items()
            if any(version.live for version in versions)
        )

    # Operations (called by the client objects)

    def _record(self, operation: str, name: str, **kwargs: Any) -> None:
        self.calls.append((operation, name, kwargs))

    def _versions(self, bucket: str, name: str) -> list[Version]:
        return self._objects.setdefault(bucket, {}).setdefault(name, [])

    def upload(
        self,
        bucket: str,
        name: str,
        data: bytes,
        *,
        content_type: str | None,
        if_generation_match: int | None,
    ) -> Version:
        self._record("upload", name, if_generation_match=if_generation_match, size=len(data))

        def do() -> Version:
            with self.lock:
                versions = self._versions(bucket, name)
                live = self.live(bucket, name)
                if if_generation_match is not None:
                    current = 0 if live is None else live.generation
                    if current != if_generation_match:
                        raise PreconditionFailed(f"{name}: generation {current}")
                if live is not None:
                    live.noncurrent_since = self.now
                self._generation += 1
                version = Version(
                    self._generation,
                    bytes(data),
                    content_type,
                    updated=self.now,
                    created=self.now,
                )
                versions.append(version)
                return version

        return self.faults.run("upload", do)

    def get(
        self, bucket: str, name: str, *, generation: int | None, soft_deleted: bool
    ) -> Version | None:
        self._record("get", name, generation=generation, soft_deleted=soft_deleted)

        def do() -> Version | None:
            with self.lock:
                for version in self.versions_of(bucket, name):
                    if generation is None:
                        if version.live:
                            return version
                    elif version.generation == generation and version.soft_deleted == soft_deleted:
                        return version
                return None

        return self.faults.run("get", do)

    def download(
        self, bucket: str, name: str, *, generation: int | None, if_generation_match: int | None
    ) -> bytes:
        self._record(
            "download", name, generation=generation, if_generation_match=if_generation_match
        )

        def do() -> bytes:
            with self.lock:
                version = self.get(bucket, name, generation=generation, soft_deleted=False)
                self.calls.pop()  # the nested get is not a client call
                if version is None or version.soft_deleted:
                    raise NotFound(name)
                if if_generation_match is not None and version.generation != if_generation_match:
                    raise PreconditionFailed(f"{name}: generation {version.generation}")
                return version.data

        return self.faults.run("download", do)

    def delete(
        self, bucket: str, name: str, *, generation: int | None, if_generation_match: int | None
    ) -> None:
        self._record("delete", name, generation=generation, if_generation_match=if_generation_match)

        def do() -> None:
            with self.lock:
                target: Version | None = None
                for version in self.versions_of(bucket, name):
                    if version.soft_deleted:
                        continue
                    if (generation is None and version.live) or version.generation == generation:
                        target = version
                        break
                if target is None:
                    raise NotFound(name)
                if if_generation_match is not None and target.generation != if_generation_match:
                    raise PreconditionFailed(f"{name}: generation {target.generation}")
                if generation is None:
                    target.noncurrent_since = (
                        self.now
                    )  # versioning: the live object goes noncurrent
                    return
                target.noncurrent_since = target.noncurrent_since or self.now
                target.soft_deleted_at = self.now
                target.hard_delete_at = self.now + self.soft_delete_retention

        self.faults.run("delete", do)

    def list(
        self, bucket: str, *, prefix: str | None, versions: bool, soft_deleted: bool
    ) -> list[tuple[str, Version]]:
        self._record("list", prefix or "", versions=versions, soft_deleted=soft_deleted)

        def do() -> list[tuple[str, Version]]:
            with self.lock:
                found: list[tuple[str, Version]] = []
                for name, stored in sorted(self._objects.get(bucket, {}).items()):
                    if prefix is not None and not name.startswith(prefix):
                        continue
                    for version in stored:
                        if soft_deleted:
                            keep = version.soft_deleted
                        elif versions:
                            keep = not version.soft_deleted
                        else:
                            keep = version.live
                        if keep:
                            found.append((name, version))
                return found

        return self.faults.run("list", do)

    def patch(
        self,
        bucket: str,
        name: str,
        metadata: dict[str, str],
        *,
        if_generation_match: int | None,
        if_metageneration_match: int | None,
    ) -> Version:
        self._record(
            "patch",
            name,
            if_generation_match=if_generation_match,
            if_metageneration_match=if_metageneration_match,
        )

        def do() -> Version:
            with self.lock:
                live = self.live(bucket, name)
                if live is None:
                    raise NotFound(name)
                if if_generation_match is not None and live.generation != if_generation_match:
                    raise PreconditionFailed(f"{name}: generation {live.generation}")
                if (
                    if_metageneration_match is not None
                    and live.metageneration != if_metageneration_match
                ):
                    raise PreconditionFailed(f"{name}: metageneration {live.metageneration}")
                live.metadata = dict(metadata)
                live.metageneration += 1
                return live

        return self.faults.run("patch", do)

    def restore(self, bucket: str, name: str, *, generation: int) -> Version:
        """Restore a soft-deleted generation as a new live generation (operator action)."""
        self._record("restore", name, generation=generation)
        with self.lock:
            source = self.get(bucket, name, generation=generation, soft_deleted=True)
            self.calls.pop()
            if source is None:
                raise NotFound(f"{name}#{generation}")
            return self.upload(
                bucket,
                name,
                source.data,
                content_type=source.content_type,
                if_generation_match=None,
            )


class FakeGcsClient:
    def __init__(self, backend: FakeGcsBackend, permissions: frozenset[str]) -> None:
        self.backend = backend
        self.permissions = permissions

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise Forbidden(f"storage.objects.{permission} denied")

    def bucket(self, name: str) -> FakeBucket:
        return FakeBucket(self, name)


class FakeBucket:
    def __init__(self, client: FakeGcsClient, name: str) -> None:
        self.client = client
        self.name = name

    def blob(self, name: str, generation: int | None = None, **_: Any) -> FakeBlob:
        return FakeBlob(self, name, generation=generation)

    def get_blob(
        self, name: str, generation: int | None = None, soft_deleted: bool = False, **_: Any
    ) -> FakeBlob | None:
        self.client.require("get")
        version = self.client.backend.get(
            self.name, name, generation=generation, soft_deleted=soft_deleted
        )
        if version is None:
            return None
        blob = FakeBlob(self, name, generation=version.generation)
        blob._set(version)
        return blob

    def list_blobs(
        self,
        prefix: str | None = None,
        versions: bool = False,
        soft_deleted: bool = False,
        **_: Any,
    ) -> Iterator[FakeBlob]:
        self.client.require("list")
        for name, version in self.client.backend.list(
            self.name, prefix=prefix, versions=versions, soft_deleted=soft_deleted
        ):
            blob = FakeBlob(self, name, generation=version.generation)
            blob._set(version)
            yield blob

    def restore_blob(self, name: str, generation: int, **_: Any) -> FakeBlob:
        self.client.require("create")
        self.client.require("get")
        version = self.client.backend.restore(self.name, name, generation=generation)
        blob = FakeBlob(self, name, generation=version.generation)
        blob._set(version)
        return blob


class FakeBlob:
    def __init__(self, bucket: FakeBucket, name: str, *, generation: int | None = None) -> None:
        self.bucket = bucket
        self.name = name
        self.generation = generation
        self.metageneration: int | None = None
        self.size: int | None = None
        self.content_type: str | None = None
        self.metadata: dict[str, str] | None = None
        self.time_deleted: datetime | None = None
        self.soft_delete_time: datetime | None = None
        self.hard_delete_time: datetime | None = None
        self.updated: datetime | None = None
        self.time_created: datetime | None = None

    def _set(self, version: Version) -> None:
        self.generation = version.generation
        self.metageneration = version.metageneration
        self.size = len(version.data)
        self.content_type = version.content_type
        self.metadata = dict(version.metadata)
        self.time_deleted = version.noncurrent_since
        self.soft_delete_time = version.soft_deleted_at
        self.hard_delete_time = version.hard_delete_at
        self.updated = version.updated
        self.time_created = version.created

    @property
    def _backend(self) -> FakeGcsBackend:
        return self.bucket.client.backend

    def upload_from_file(
        self,
        file_obj: BinaryIO,
        size: int | None = None,
        content_type: str | None = None,
        if_generation_match: int | None = None,
        **_: Any,
    ) -> None:
        self.bucket.client.require("create")
        chunks: list[bytes] = []
        while chunk := file_obj.read(64 * 1024):  # a failing stream raises here, before any write
            chunks.append(chunk)
        data = b"".join(chunks)
        if size is not None and size != len(data):
            raise ValueError("size does not match the stream")
        version = self._backend.upload(
            self.bucket.name,
            self.name,
            data,
            content_type=content_type,
            if_generation_match=if_generation_match,
        )
        self._set(version)

    def download_as_bytes(self, if_generation_match: int | None = None, **_: Any) -> bytes:
        self.bucket.client.require("get")
        return self._backend.download(
            self.bucket.name,
            self.name,
            generation=self.generation,
            if_generation_match=if_generation_match,
        )

    def delete(self, if_generation_match: int | None = None, **_: Any) -> None:
        self.bucket.client.require("delete")
        self._backend.delete(
            self.bucket.name,
            self.name,
            generation=self.generation,
            if_generation_match=if_generation_match,
        )

    def patch(
        self,
        if_generation_match: int | None = None,
        if_metageneration_match: int | None = None,
        **_: Any,
    ) -> None:
        self.bucket.client.require("update")
        version = self._backend.patch(
            self.bucket.name,
            self.name,
            dict(self.metadata or {}),
            if_generation_match=if_generation_match,
            if_metageneration_match=if_metageneration_match,
        )
        self._set(version)

    def reload(self, **_: Any) -> None:
        self.bucket.client.require("get")
        version = self._backend.get(
            self.bucket.name, self.name, generation=self.generation, soft_deleted=False
        )
        if version is None:
            raise NotFound(self.name)
        self._set(version)

    def exists(self, **_: Any) -> bool:
        self.bucket.client.require("get")
        return (
            self._backend.get(
                self.bucket.name, self.name, generation=self.generation, soft_deleted=False
            )
            is not None
        )
