"""Upload policy by content (05 UPL-02 to UPL-04; 04 T-PLT-29; REQ-SEC-012; PLF-8)."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from collections.abc import Sequence
from typing import Any

import pytest
from erev_api.enums import FilePurpose
from erev_api.files import policy
from erev_api.problems import Problem
from support import upload_fixtures as fx

MIB = 1024 * 1024
# zipfile.structFileHeader, structCentralDir and structEndArchive.
LOCAL_HEADER = struct.Struct("<4s2B4HL2L2H")
CENTRAL_HEADER = struct.Struct("<4s4B4HL2L5H2L")
END_RECORD = struct.Struct("<4s4H2LH")
DOS_DATE = 33  # 1980-01-01


def raw_zip(entries: Sequence[tuple[str, bytes, int, int, int]]) -> bytes:
    """A ZIP of deflated entries ``(name, raw deflate stream, CRC, local header uncompressed size,
    central directory uncompressed size)``, so a test can declare sizes the stream does not hold."""
    body, central = bytearray(), bytearray()
    for name, stream, crc, local_size, central_size in entries:
        encoded = name.encode("ascii")
        offset = len(body)
        method = zipfile.ZIP_DEFLATED
        body += LOCAL_HEADER.pack(
            b"PK\x03\x04", 20, 0, 0, method, 0, DOS_DATE, crc, len(stream), local_size,
            len(encoded), 0,
        )  # fmt: skip
        body += encoded + stream
        central += CENTRAL_HEADER.pack(
            b"PK\x01\x02", 20, 0, 20, 0, 0, method, 0, DOS_DATE, crc, len(stream), central_size,
            len(encoded), 0, 0, 0, 0, 0, offset,
        )  # fmt: skip
        central += encoded
    end = END_RECORD.pack(
        b"PK\x05\x06", 0, 0, len(entries), len(entries), len(central), len(body), 0
    )
    return bytes(body + central + end)


def deflated(content: bytes) -> bytes:
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    return compressor.compress(content) + compressor.flush()


def workbook_entry() -> tuple[str, bytes, int, int, int]:
    size = len(fx.WORKBOOK)
    return ("xl/workbook.xml", deflated(fx.WORKBOOK), zlib.crc32(fx.WORKBOOK), size, size)


def declared_size_bomb(inflated: int, declared: int) -> bytes:
    """An xlsx whose `[Content_Types].xml` inflates to ``inflated`` bytes while both headers declare
    ``declared`` bytes with the CRC of the first ``declared`` bytes (review probe
    `zip_declared_size_bomb.py`)."""
    head = fx.XLSX_CONTENT_TYPES
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    parts = [compressor.compress(head)]
    remaining = inflated - len(head)
    while remaining > 0:
        parts.append(compressor.compress(bytes(min(MIB, remaining))))
        remaining -= MIB
    parts.append(compressor.flush())
    crc = zlib.crc32((head + bytes(declared))[:declared])
    types = (policy.CONTENT_TYPES_ENTRY, b"".join(parts), crc, declared, declared)
    return raw_zip([types, workbook_entry()])


class CountingDecompressor:
    """``zlib.decompressobj`` that records the bytes each instance produces."""

    def __init__(self, inflated: list[int], *args: Any) -> None:
        self._inner = REAL_DECOMPRESSOBJ(*args)
        self._index = len(inflated)
        self._inflated = inflated
        inflated.append(0)

    def decompress(self, data: bytes, max_length: int = 0) -> bytes:
        output = self._inner.decompress(data, max_length)
        self._inflated[self._index] += len(output)
        return output

    def flush(self, *args: Any) -> bytes:
        output = self._inner.flush(*args)
        self._inflated[self._index] += len(output)
        return output

    @property
    def eof(self) -> bool:
        return self._inner.eof

    @property
    def unconsumed_tail(self) -> bytes:
        return self._inner.unconsumed_tail


REAL_DECOMPRESSOBJ = zlib.decompressobj


def media_type(purpose: FilePurpose, name: str | None, content: bytes) -> str:
    return policy.check_upload(
        purpose, io.BytesIO(content), size=len(content), original_filename=name
    )


def refusal(purpose: FilePurpose, name: str | None, content: bytes) -> str | None:
    with pytest.raises(Problem) as excinfo:
        media_type(purpose, name, content)
    assert excinfo.value.slug == "upload-type-not-allowed"
    return excinfo.value.detail


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("acceptance.pdf", fx.PDF, policy.PDF),
        ("contract.docx", fx.docx(), policy.DOCX),
        ("revenue.xlsx", fx.xlsx(), policy.XLSX),
        ("revenue.csv", fx.CSV, policy.CSV),
        ("signature.png", fx.PNG, policy.PNG),
        ("scan.JPG", b"\xff\xd8\xff\xe0" + b"\x00" * 32, policy.JPEG),
        ("acceptance.eml", fx.EML, policy.EML),
        (None, fx.CSV, policy.CSV),
    ],
)
def test_upl_02_attachment_types_by_content(
    name: str | None, content: bytes, expected: str
) -> None:
    assert media_type(FilePurpose.ATTACHMENT, name, content) == expected


def test_upl_02_extension_must_match_content() -> None:
    # A PDF named .csv, text named .xlsx, and a CSV without an email header named .eml.
    for name, content in (("renamed.csv", fx.PDF), ("text.xlsx", fx.CSV), ("note.eml", fx.CSV)):
        assert refusal(FilePurpose.ATTACHMENT, name, content) == policy.ATTACHMENT_DETAIL
    # SVG and HTML are not on any list (UPL-10).
    assert refusal(FilePurpose.ATTACHMENT, "logo.svg", b"<svg/>") == policy.ATTACHMENT_DETAIL


def test_upl_02_text_must_be_utf8_without_nul() -> None:
    assert refusal(FilePurpose.IMPORT_SOURCE, "latin.csv", "Zürich".encode("latin-1")) == (
        policy.IMPORT_DETAIL
    )
    assert refusal(FilePurpose.IMPORT_SOURCE, "nul.csv", b"a,b\x00\n") == policy.IMPORT_DETAIL


def test_import_sources_accept_only_xlsx_and_csv() -> None:
    assert media_type(FilePurpose.IMPORT_SOURCE, "orders.xlsx", fx.xlsx()) == policy.XLSX
    assert refusal(FilePurpose.IMPORT_SOURCE, "acceptance.pdf", fx.PDF) == policy.IMPORT_DETAIL
    assert refusal(FilePurpose.IMPORT_SOURCE, "contract.docx", fx.docx()) == policy.IMPORT_DETAIL


def test_upl_03_macro_binary_and_archives_refused() -> None:
    for name, content in (
        ("revenue.xlsx", fx.xlsx_with_vba_project()),
        ("revenue.xlsm", fx.xlsm()),
        (None, fx.xlsm()),
        ("revenue.xlsb", fx.xlsx()),
        ("protected.xlsx", fx.OLE2),
        ("bundle.zip", fx.zip_archive()),
        (None, fx.zip_archive()),
        ("bundle.gz", b"\x1f\x8b\x08\x00" + b"\x00" * 16),
    ):
        assert refusal(FilePurpose.IMPORT_SOURCE, name, content) == policy.IMPORT_DETAIL


def test_upl_04_zip_limits() -> None:
    at_ratio = fx.ooxml_with_ratio(101)
    with zipfile.ZipFile(io.BytesIO(at_ratio)) as archive:
        entry = archive.getinfo("xl/sharedStrings.xml")
    assert 101 * entry.compress_size <= entry.file_size < 102 * entry.compress_size
    assert refusal(FilePurpose.IMPORT_SOURCE, "ratio.xlsx", at_ratio) == policy.IMPORT_DETAIL
    for extra in ({"xl/../escape.xml": b"x"}, {"/absolute.xml": b"x"}, {"xl/nested.zip": b"x"}):
        content = fx.xlsx(extra)
        assert refusal(FilePurpose.IMPORT_SOURCE, "nested.xlsx", content) == policy.IMPORT_DETAIL


def test_upl_04_declared_sizes_not_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    bomb = declared_size_bomb(inflated=100 * MIB, declared=1_500)
    assert len(bomb) < 250 * 1024
    with zipfile.ZipFile(io.BytesIO(bomb)) as archive:
        entry = archive.getinfo(policy.CONTENT_TYPES_ENTRY)
    assert (entry.file_size, entry.file_size * policy.ZIP_MAX_RATIO > entry.compress_size) == (
        1_500,
        True,
    )
    inflated: list[int] = []
    monkeypatch.setattr(
        zipfile.zlib, "decompressobj", lambda *args: CountingDecompressor(inflated, *args)
    )
    assert refusal(FilePurpose.IMPORT_SOURCE, "bomb.xlsx", bomb) == policy.IMPORT_DETAIL
    assert inflated
    assert max(inflated) <= 1_500 + policy.ZIP_READ_BYTES

    # The local header and the central directory disagree about the uncompressed size.
    types = fx.XLSX_CONTENT_TYPES
    size = len(types)
    mismatched = raw_zip(
        [
            (policy.CONTENT_TYPES_ENTRY, deflated(types), zlib.crc32(types), size + 1, size),
            workbook_entry(),
        ]
    )
    assert refusal(FilePurpose.IMPORT_SOURCE, "mismatch.xlsx", mismatched) == policy.IMPORT_DETAIL
    # The same archive with agreeing headers is a workbook.
    agreeing = raw_zip(
        [
            (policy.CONTENT_TYPES_ENTRY, deflated(types), zlib.crc32(types), size, size),
            workbook_entry(),
        ]
    )
    assert media_type(FilePurpose.IMPORT_SOURCE, "agreeing.xlsx", agreeing) == policy.XLSX


def test_size_limits_per_purpose() -> None:
    limit = policy.UPLOAD_LIMITS[FilePurpose.ATTACHMENT]
    assert limit == 26_214_400
    with pytest.raises(Problem) as oversized:
        policy.check_upload(
            FilePurpose.ATTACHMENT, io.BytesIO(fx.PDF), size=limit + 1, original_filename="a.pdf"
        )
    assert oversized.value.detail == policy.ATTACHMENT_DETAIL
    assert refusal(FilePurpose.ATTACHMENT, "empty.csv", b"") == policy.ATTACHMENT_DETAIL
    assert media_type(FilePurpose.LEGACY_DATABASE, "ASC606.db", fx.SQLITE) == policy.SQLITE
    assert refusal(FilePurpose.LEGACY_DATABASE, "ASC606.db", fx.CSV) == (
        policy.LEGACY_DATABASE_DETAIL
    )
    with pytest.raises(ValueError):
        media_type(FilePurpose.REPORT_OUTPUT, None, fx.CSV)
