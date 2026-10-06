"""Upload policy (04 T-PLT-29 upload limits; 05 UPL-01 to UPL-04; REQ-SEC-012; PRD ERR-37, NFR-50).

``check_upload`` accepts a file of one of the four uploadable purposes or raises 422
``upload-type-not-allowed`` whose detail names the purpose's limit. The type is decided by content,
never by the declared ``Content-Type`` (UPL-02): PDF, PNG, JPEG and SQLite by magic bytes; OOXML by
its ZIP entries after the UPL-04 bomb limits; CSV and EML as strict UTF-8 text. A file name, when
present, must carry an extension of the same type, so `.xlsm`, `.xlsb`, `.xls` and archives are
refused whatever their content (UPL-03).
"""

from __future__ import annotations

import codecs
import copy
import re
import struct
import zipfile
import zlib
from collections.abc import Mapping
from types import MappingProxyType
from typing import BinaryIO, Final

from erev_api.enums import FilePurpose
from erev_api.problems import Problem

MIB: Final = 1024 * 1024
CHUNK_BYTES: Final = MIB
UPLOAD_LIMITS: Final[Mapping[FilePurpose, int]] = MappingProxyType(
    {
        FilePurpose.ATTACHMENT: 25 * MIB,
        FilePurpose.SSP_STUDY: 25 * MIB,
        FilePurpose.IMPORT_SOURCE: 50 * MIB,
        FilePurpose.LEGACY_DATABASE: 500 * MIB,
    }
)
UPLOADABLE_PURPOSES: Final = frozenset(UPLOAD_LIMITS)
# 05 PRV-06: purposes stored under a per-file data key with a `.dek` sidecar (BS1-D-21).
ENCRYPTED_PURPOSES: Final = frozenset(
    {
        FilePurpose.IMPORT_SOURCE,
        FilePurpose.ATTACHMENT,
        FilePurpose.SSP_STUDY,
        FilePurpose.LEGACY_DATABASE,
        FilePurpose.SNAPSHOT_DATASET,
    }
)
# PRD ERR-37.
IMPORT_DETAIL: Final = (
    "Import files must be .xlsx or .csv and at most 50 MiB. "
    "Macro-enabled workbooks and archives are not accepted."
)
ATTACHMENT_DETAIL: Final = (
    "Attachments and SSP studies must be pdf, docx, xlsx, csv, png, jpg or eml files "
    "of at most 25 MiB."
)
LEGACY_DATABASE_DETAIL: Final = "Legacy databases must be SQLite files of at most 500 MiB."
LIMIT_DETAILS: Final[Mapping[FilePurpose, str]] = MappingProxyType(
    {
        FilePurpose.ATTACHMENT: ATTACHMENT_DETAIL,
        FilePurpose.SSP_STUDY: ATTACHMENT_DETAIL,
        FilePurpose.IMPORT_SOURCE: IMPORT_DETAIL,
        FilePurpose.LEGACY_DATABASE: LEGACY_DATABASE_DETAIL,
    }
)

PDF: Final = "application/pdf"
DOCX: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV: Final = "text/csv"
PNG: Final = "image/png"
JPEG: Final = "image/jpeg"
EML: Final = "message/rfc822"
SQLITE: Final = "application/vnd.sqlite3"
_DOCUMENTS: Final = frozenset({PDF, DOCX, XLSX, CSV, PNG, JPEG, EML})
ALLOWED_MEDIA_TYPES: Final[Mapping[FilePurpose, frozenset[str]]] = MappingProxyType(
    {
        FilePurpose.ATTACHMENT: _DOCUMENTS,
        FilePurpose.SSP_STUDY: _DOCUMENTS,
        FilePurpose.IMPORT_SOURCE: frozenset({XLSX, CSV}),
        FilePurpose.LEGACY_DATABASE: frozenset({SQLITE}),
    }
)
EXTENSION_MEDIA_TYPES: Final[Mapping[str, str]] = MappingProxyType(
    {
        ".pdf": PDF,
        ".docx": DOCX,
        ".xlsx": XLSX,
        ".csv": CSV,
        ".png": PNG,
        ".jpg": JPEG,
        ".jpeg": JPEG,
        ".eml": EML,
        ".db": SQLITE,
        ".sqlite": SQLITE,
        ".sqlite3": SQLITE,
    }
)

# UPL-04 limits for OOXML before parsing.
ZIP_MAX_ENTRIES: Final = 10_000
ZIP_MAX_TOTAL_BYTES: Final = 250 * MIB
ZIP_MAX_ENTRY_BYTES: Final = 150 * MIB
ZIP_MAX_RATIO: Final = 100
CONTENT_TYPES_ENTRY: Final = "[Content_Types].xml"
# Entries are inflated through reads of at most this many bytes (PR-R-05).
ZIP_READ_BYTES: Final = 64 * 1024
_CONTENT_TYPES_MAX_BYTES: Final = MIB
_NESTED_ARCHIVE_SUFFIXES: Final = (".zip", ".7z", ".rar", ".gz", ".tar", ".tgz")
_ZIP_METHODS: Final = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
# zipfile.structFileHeader: signature, versions, flags, method, time, date, CRC, sizes, name and
# extra lengths.
_LOCAL_HEADER: Final = struct.Struct("<4s2B4HL2L2H")
_DATA_DESCRIPTOR_FLAG: Final = 0x08
_DATA_DESCRIPTOR_MAGIC: Final = b"PK\x07\x08"
_ZIP64_MARKER: Final = 0xFFFFFFFF
_ZIP64_EXTRA_ID: Final = 0x0001

_ZIP_MAGIC: Final = b"PK\x03\x04"
_OLE2_MAGIC: Final = b"\xd0\xcf\x11\xe0"
_PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC: Final = b"\xff\xd8\xff"
_SQLITE_MAGIC: Final = b"SQLite format 3\x00"
_ARCHIVE_MAGICS: Final = (b"\x1f\x8b", b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07", b"PK\x05\x06")
# RFC 5322 §2.2: a header field name is printable ASCII other than ":" followed by ":".
_EML_HEADER: Final = re.compile(r"^[!-9;-~]+:[ \t]")
_EML_HEAD_CHARACTERS: Final = 998


def refused(purpose: FilePurpose) -> Problem:
    """422 ``upload-type-not-allowed`` naming the limit of ``purpose`` (T-PLT-29; ERR-37)."""
    return Problem("upload-type-not-allowed", LIMIT_DETAILS[purpose])


def extension_of(original_filename: str | None) -> str | None:
    """The lower-cased extension of the name's last path segment, or None without one."""
    if original_filename is None:
        return None
    name = re.split(r"[\\/]", original_filename)[-1]
    stem, dot, suffix = name.rpartition(".")
    return "." + suffix.lower() if dot and stem else None


def check_upload(
    purpose: FilePurpose, stream: BinaryIO, *, size: int, original_filename: str | None
) -> str:
    """The media type of an accepted upload; ``stream`` is seekable and returned at offset 0."""
    if purpose not in UPLOAD_LIMITS:
        raise ValueError(f"purpose {purpose} has no upload route (T-PLT-29)")
    if size <= 0 or size > UPLOAD_LIMITS[purpose]:
        raise refused(purpose)
    extension = extension_of(original_filename)
    declared = None if extension is None else EXTENSION_MEDIA_TYPES.get(extension)
    if extension is not None and declared is None:
        raise refused(purpose)
    detected = detect_media_type(stream, declared=declared)
    if detected is None or detected not in ALLOWED_MEDIA_TYPES[purpose]:
        raise refused(purpose)
    if declared is not None and declared != detected:
        raise refused(purpose)
    return detected


def detect_media_type(stream: BinaryIO, *, declared: str | None = None) -> str | None:
    """The UPL-02 media type of the content, or None for refused or unrecognised content."""
    stream.seek(0)
    head = stream.read(16)
    stream.seek(0)
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(_PNG_MAGIC):
        return PNG
    if head.startswith(_JPEG_MAGIC):
        return JPEG
    if head.startswith(_SQLITE_MAGIC):
        return SQLITE
    if head.startswith(_OLE2_MAGIC) or head.startswith(_ARCHIVE_MAGICS):
        return None
    if head.startswith(_ZIP_MAGIC):
        return _ooxml_media_type(stream)
    return _text_media_type(stream, declared=declared)


def zip_within_limits(archive: zipfile.ZipFile) -> bool:
    """UPL-04: entry count, sizes, per-entry ratio, nested archives and entry paths.

    Declared sizes are not trusted (PR-R-05). The declared sizes pass the limits first; then each
    local header must declare the central directory's sizes, and each entry is inflated through
    bounded reads that stop one byte past its declared size, so an entry producing more or less
    than it declares is refused and the limits hold for the output actually produced. A stream
    whose CRC differs raises ``zipfile.BadZipFile``.
    """
    entries = archive.infolist()
    if len(entries) > ZIP_MAX_ENTRIES:
        return False
    total = 0
    for entry in entries:
        name = entry.filename
        segments = name.split("/")
        if (
            name.startswith("/")
            or "\\" in name
            or ".." in segments
            or re.match(r"^[A-Za-z]:", name)
        ):
            return False
        if name.lower().endswith(_NESTED_ARCHIVE_SUFFIXES):
            return False
        if entry.compress_type not in _ZIP_METHODS:
            return False
        if entry.file_size > ZIP_MAX_ENTRY_BYTES:
            return False
        if entry.file_size > ZIP_MAX_RATIO * entry.compress_size:
            return False
        total += entry.file_size
        if total > ZIP_MAX_TOTAL_BYTES:
            return False
    return all(
        _local_sizes_match(archive, entry) and _inflated_size(archive, entry) == entry.file_size
        for entry in entries
    )


def _local_sizes_match(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> bool:
    """The local file header, or the data descriptor it announces, declares the central
    directory's compressed and uncompressed sizes."""
    source = archive.fp
    if source is None:
        return False
    source.seek(entry.header_offset)
    header = source.read(_LOCAL_HEADER.size)
    if len(header) != _LOCAL_HEADER.size:
        return False
    fields = _LOCAL_HEADER.unpack(header)
    magic, flags = fields[0], fields[3]
    compressed, uncompressed, name_length, extra_length = fields[8:12]
    if magic != _ZIP_MAGIC:
        return False
    if flags & _DATA_DESCRIPTOR_FLAG:
        source.seek(
            entry.header_offset
            + _LOCAL_HEADER.size
            + name_length
            + extra_length
            + entry.compress_size
        )
        descriptor = source.read(16)
        if descriptor.startswith(_DATA_DESCRIPTOR_MAGIC):
            descriptor = descriptor[4:]
        if len(descriptor) < 12:
            return False
        _, compressed, uncompressed = struct.unpack("<3L", descriptor[:12])
    elif _ZIP64_MARKER in (compressed, uncompressed):
        source.seek(entry.header_offset + _LOCAL_HEADER.size + name_length)
        compressed, uncompressed = _zip64_sizes(source.read(extra_length), compressed, uncompressed)
    return (compressed, uncompressed) == (entry.compress_size, entry.file_size)


def _zip64_sizes(extra: bytes, compressed: int, uncompressed: int) -> tuple[int, int]:
    """The sizes a local header's ZIP64 extra field holds for the members marked 0xFFFFFFFF."""
    offset = 0
    while offset + 4 <= len(extra):
        kind, length = struct.unpack_from("<2H", extra, offset)
        body = extra[offset + 4 : offset + 4 + length]
        if kind == _ZIP64_EXTRA_ID:
            values = iter(struct.unpack(f"<{len(body) // 8}Q", body[: len(body) // 8 * 8]))
            if uncompressed == _ZIP64_MARKER:
                uncompressed = next(values, -1)
            if compressed == _ZIP64_MARKER:
                compressed = next(values, -1)
            break
        offset += 4 + length
    return compressed, uncompressed


def _inflated_size(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> int:
    """The bytes the entry produces, counted to at most one byte past its declared size."""
    bounded = copy.copy(entry)
    bounded.file_size = entry.file_size + 1
    size = 0
    with archive.open(bounded) as stream:
        while chunk := stream.read(ZIP_READ_BYTES):
            size += len(chunk)
            if size > entry.file_size:
                break
    return size


def _read_entry(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> bytes:
    """An entry whose size ``zip_within_limits`` verified, read in bounded reads."""
    parts: list[bytes] = []
    with archive.open(entry) as stream:
        while chunk := stream.read(ZIP_READ_BYTES):
            parts.append(chunk)
    return b"".join(parts)


# UPL-05 companion (SAR-42 billion-laughs fixture): the OOXML schema forbids document type
# declarations, so an XML part that declares one is refused before any parser sees it.
_DTD_MARKERS: Final = ("<!doctype", "<!entity")
_XML_PART_SUFFIXES: Final = (".xml", ".rels")
# The encodings an XML part may announce, in the order they are recognised: a byte-order mark
# (UTF-32 before UTF-16, whose LE mark is a prefix of the UTF-32 LE mark), else the byte shape of a
# ``<?xml`` declaration written in a wide encoding, else the ``encoding`` the declaration names.
_BOM_ENCODINGS: Final = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
_WIDE_DECLARATIONS: Final = (
    (b"<\x00\x00\x00?\x00\x00\x00", "utf-32-le"),
    (b"\x00\x00\x00<\x00\x00\x00?", "utf-32-be"),
    (b"<\x00?\x00", "utf-16-le"),
    (b"\x00<\x00?", "utf-16-be"),
)
_DECLARED_ENCODING: Final = re.compile(
    rb"^\s*<\?xml[^>]*?encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']"
)


def _text_encoding(declared: bytes) -> str | None:
    """The canonical name of a TEXT encoding, or ``None`` for an unknown name and for a registered
    codec that is not a text encoding — the binary and str transforms of the Python codecs
    registry (``base64_codec``, ``zlib_codec``, ``rot_13``, …), which ``bytes.decode`` refuses with
    ``LookupError`` (Codex P8-SOP8-CODEC-1). The probe decodes ONE byte with replacement inside the
    guard — an empty ``decode`` short-circuits before the text-encoding check and proves nothing —
    so the refusal stays named instead of letting the error escape as a 500."""
    try:
        name = codecs.lookup(declared.decode("ascii")).name
        b"<".decode(name, errors="replace")
    except (LookupError, UnicodeDecodeError, ValueError):
        return None
    return name


def xml_part_text(content: bytes) -> str | None:
    """The lowercase text of an XML part decoded under the encoding the part itself announces (its
    BOM, else the byte shape of a UTF-16 / UTF-32 declaration, else the declared ``encoding``, else
    UTF-8), so a document type declaration written in a wide encoding cannot hide from the marker
    search (Codex P8-SOP8-DTD-1); ``None`` when the declared encoding is unknown or not a text
    encoding, which the caller treats as a refusal of the part (Codex P8-SOP8-CODEC-1). Undecodable
    bytes become U+FFFD and are never dropped; the input is already bounded by
    ``zip_within_limits``."""
    encoding = "utf-8"
    for bom, name in _BOM_ENCODINGS:
        if content.startswith(bom):
            encoding, content = name, content[len(bom) :]
            break
    else:
        for prefix, name in _WIDE_DECLARATIONS:
            if content.startswith(prefix):
                encoding = name
                break
        else:
            declared = _DECLARED_ENCODING.match(content)
            if declared is not None:
                found = _text_encoding(declared.group(1))
                if found is None:
                    return None
                encoding = found
    return content.decode(encoding, errors="replace").lower()


def _refuses_xml_parts(archive: zipfile.ZipFile, entries: Mapping[str, zipfile.ZipInfo]) -> bool:
    """Whether any XML part of the archive is refused: it declares a DTD or an entity (entity-
    expansion shape) in whatever encoding it announces, or it announces an encoding that is not a
    text encoding. Entry sizes were verified by ``zip_within_limits``, so the bounded reads stay
    within UPL-04."""
    for name, entry in entries.items():
        if entry.is_dir() or not name.lower().endswith(_XML_PART_SUFFIXES):
            continue
        content = _read_entry(archive, entry)
        text = xml_part_text(content)
        if text is None:
            return True
        raw = content.lower()
        if any(marker in text or marker.encode("ascii") in raw for marker in _DTD_MARKERS):
            return True
    return False


def _ooxml_media_type(stream: BinaryIO) -> str | None:
    try:
        with zipfile.ZipFile(stream) as archive:
            if not zip_within_limits(archive):
                return None
            entries = {entry.filename: entry for entry in archive.infolist()}
            content_types = entries.get(CONTENT_TYPES_ENTRY)
            if content_types is None or content_types.file_size > _CONTENT_TYPES_MAX_BYTES:
                return None
            if any(name.lower().endswith("vbaproject.bin") for name in entries):
                return None
            if b"macroenabled" in _read_entry(archive, content_types).lower():
                return None
            if _refuses_xml_parts(archive, entries):
                return None
            if "xl/workbook.xml" in entries:
                return XLSX
            if "word/document.xml" in entries:
                return DOCX
            return None
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        NotImplementedError,
        OSError,
        ValueError,
        EOFError,
        zlib.error,
        struct.error,
    ):
        return None
    finally:
        stream.seek(0)


def _text_media_type(stream: BinaryIO, *, declared: str | None) -> str | None:
    """Strict UTF-8 without NUL bytes: EML when declared and headed by a header field, else CSV."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    head = ""
    try:
        while chunk := stream.read(CHUNK_BYTES):
            if b"\x00" in chunk:
                return None
            text = decoder.decode(chunk)
            if len(head) < _EML_HEAD_CHARACTERS:
                head += text[: _EML_HEAD_CHARACTERS - len(head)]
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return None
    finally:
        stream.seek(0)
    if declared == EML:
        return EML if _EML_HEADER.match(head.removeprefix("﻿")) else None
    return CSV
