"""Evidence ZIP construction and verification (REQ-RPT-014; T-RPT-04; RPS-16).

Every payload file is hashed in manifest.json. The manifest's own bytes are bound by
T-RPT-04.manifest_sha256, supplied separately to verification: a file cannot contain
its own SHA-256. No files are extracted to the filesystem. This module does not select
accounting evidence, authorize access or establish that a close pack is complete.
Callers supply export-sanitized bytes; this boundary never rewrites a payload.
"""

from __future__ import annotations

import hashlib
import io
import json
import stat
import unicodedata
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes

MANIFEST: Final = "manifest.json"
MAX_FILES: Final = 10_000
MAX_PATH_BYTES: Final = 1_024
MAX_MANIFEST_BYTES: Final = 16 * 1024 * 1024
MAX_PAYLOAD_BYTES: Final = 256 * 1024 * 1024
RESERVED_NAMES: Final = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)


class InvalidArchive(ValueError):
    """An unsafe, incomplete, oversized or altered evidence archive."""


@dataclass(frozen=True, slots=True)
class PackFile:
    path: str
    content: bytes
    report_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Archive:
    content: bytes
    manifest_bytes: bytes
    manifest_sha256: str

    def manifest_document(self) -> dict[str, Any]:
        """An independent JSON document for the evidence_pack row; callers cannot change bytes."""
        value: dict[str, Any] = json.loads(self.manifest_bytes)
        return value


def _path_key(path: str) -> str:
    try:
        encoded = path.encode("utf-8")
    except UnicodeError as error:
        raise InvalidArchive("Evidence path is not valid UTF-8.") from error
    if (
        not path
        or len(encoded) > MAX_PATH_BYTES
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or "\\" in path
        or any(character in path for character in '<>:"|?*')
        or any(part.split(".", 1)[0].casefold() in RESERVED_NAMES for part in path.split("/"))
        or path.startswith("/")
        or any(part in ("", ".", "..") or part.endswith((".", " ")) for part in path.split("/"))
        or str(PurePosixPath(path)) != path
        or unicodedata.normalize("NFC", path) != path
    ):
        raise InvalidArchive("Evidence file path is not a canonical relative path.")
    return path.casefold()


def _add_path(path: str, files: set[str], directories: set[str]) -> None:
    key = _path_key(path)
    parents = [key.rsplit("/", index)[0] for index in range(1, key.count("/") + 1)]
    if key in files or key in directories or any(parent in files for parent in parents):
        raise InvalidArchive("Duplicate or conflicting evidence file path.")
    files.add(key)
    directories.update(parents)


def _limits(files: int, size: int, maximum: int) -> None:
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
        raise ValueError("max_payload_bytes must be a non-negative integer")
    if files > MAX_FILES or size > maximum:
        raise InvalidArchive("Evidence archive exceeds its file or payload size limit.")


def _entry(path: str) -> zipfile.ZipInfo:
    entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = (stat.S_IFREG | 0o600) << 16
    entry.compress_type = zipfile.ZIP_STORED
    return entry


def build(files: Sequence[PackFile], *, max_payload_bytes: int = MAX_PAYLOAD_BYTES) -> Archive:
    """Build reproducible bytes without timestamps, compression versions or host permissions."""
    _limits(len(files), sum(len(file.content) for file in files), max_payload_bytes)
    seen = {MANIFEST.casefold()}
    directories: set[str] = set()
    rows = []
    ordered = sorted(files, key=lambda file: file.path)
    for file in ordered:
        _add_path(file.path, seen, directories)
        rows.append(
            {
                "path": file.path,
                "sha256": hashlib.sha256(file.content).hexdigest(),
                "bytes": len(file.content),
                "report_run_id": None if file.report_run_id is None else str(file.report_run_id),
            }
        )
    manifest = canonical_bytes({"files": rows})
    if len(manifest) > MAX_MANIFEST_BYTES:
        raise InvalidArchive("Evidence manifest exceeds its size limit.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for file in ordered:
            archive.writestr(_entry(file.path), file.content)
        archive.writestr(_entry(MANIFEST), manifest)
    return Archive(output.getvalue(), manifest, hashlib.sha256(manifest).hexdigest())


def verify(
    content: bytes,
    *,
    expected_manifest_sha256: str,
    max_payload_bytes: int = MAX_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Verify against the trusted stored manifest hash, not a hash from the ZIP itself.

    Require one canonical manifest, exactly its listed files, safe unique regular-file
    paths, and matching actual byte counts and SHA-256 values. Bound decompression before
    reading members, including a separately bounded manifest.
    """
    _limits(0, 0, max_payload_bytes)
    # Bound container overhead too, before ZipFile allocates its member index.
    overhead = (MAX_FILES + 1) * (2 * MAX_PATH_BYTES + 256)
    if len(content) > max_payload_bytes + MAX_MANIFEST_BYTES + overhead:
        raise InvalidArchive("Evidence ZIP exceeds its size limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            _limits(len(entries) - 1, 0, max_payload_bytes)
            names: set[str] = set()
            directories: set[str] = set()
            actual: dict[str, bytes] = {}
            size = 0
            for entry in entries:
                _add_path(entry.filename, names, directories)
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if entry.is_dir() or mode not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                    raise InvalidArchive("Evidence ZIP members must be unencrypted regular files.")
                limit = (
                    MAX_MANIFEST_BYTES if entry.filename == MANIFEST else max_payload_bytes - size
                )
                if entry.file_size > limit:
                    raise InvalidArchive("Evidence ZIP member exceeds its size limit.")
                with archive.open(entry) as source:
                    data = source.read(limit + 1)
                if len(data) != entry.file_size or len(data) > limit:
                    raise InvalidArchive("Evidence ZIP member has an invalid byte count.")
                actual[entry.filename] = data
                if entry.filename != MANIFEST:
                    size += len(data)
            manifest = actual.pop(MANIFEST, None)
            if manifest is None or hashlib.sha256(manifest).hexdigest() != expected_manifest_sha256:
                raise InvalidArchive(
                    "Evidence manifest is missing or its stored hash does not match."
                )
            document = json.loads(manifest)
            if (
                not isinstance(document, dict)
                or set(document) != {"files"}
                or not isinstance(document["files"], list)
                or canonical_bytes(document) != manifest
            ):
                raise InvalidArchive("Evidence manifest is not a canonical files document.")
            listed: set[str] = set()
            for row in document["files"]:
                if not isinstance(row, dict) or set(row) != {
                    "path",
                    "sha256",
                    "bytes",
                    "report_run_id",
                }:
                    raise InvalidArchive("Evidence manifest file metadata is invalid.")
                path = row["path"]
                if not isinstance(path, str):
                    raise InvalidArchive("Evidence manifest path must be text.")
                key = _path_key(path)
                if key in listed or key == MANIFEST.casefold():
                    raise InvalidArchive("Duplicate or self-referencing manifest entry.")
                listed.add(key)
                if row["report_run_id"] is not None:
                    if (
                        not isinstance(row["report_run_id"], str)
                        or str(UUID(row["report_run_id"])) != row["report_run_id"]
                    ):
                        raise InvalidArchive("Evidence report run id is not canonical.")
                payload = actual.pop(path, None)
                if (
                    payload is None
                    or type(row["bytes"]) is not int
                    or row["bytes"] != len(payload)
                    or row["sha256"] != hashlib.sha256(payload).hexdigest()
                ):
                    raise InvalidArchive(
                        "Evidence payload is missing or its count/hash does not match."
                    )
            if actual:
                raise InvalidArchive("Evidence ZIP contains files absent from its manifest.")
            return document
    except InvalidArchive:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        OSError,
        RuntimeError,
        zipfile.BadZipFile,
        zlib.error,
        NotImplementedError,
    ) as error:
        raise InvalidArchive("Evidence ZIP or manifest cannot be read.") from error
