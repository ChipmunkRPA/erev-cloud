"""Upload fixtures built in memory (BUILD_SPEC PLF-8; 05 UPL-02 to UPL-04).

OOXML workbooks and documents, a macro workbook, an OLE2 header, a plain archive, an entry at a
chosen compression ratio and a SQLite header. Nothing is read from disk, so the fixtures stay
deterministic and need no manifest.
"""

from __future__ import annotations

import codecs
import io
import random
import zipfile
from collections.abc import Mapping
from functools import cache
from typing import Final

XLSX_CONTENT_TYPES: Final = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Override PartName="/xl/workbook.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    b"</Types>"
)
XLSM_CONTENT_TYPES: Final = XLSX_CONTENT_TYPES.replace(
    b"spreadsheetml.sheet.main+xml", b"ms-excel.sheet.macroEnabled.main+xml"
)
DOCX_CONTENT_TYPES: Final = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Override PartName="/word/document.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.'
    b'wordprocessingml.document.main+xml"/>'
    b"</Types>"
)
WORKBOOK: Final = b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
OLE2: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
SQLITE: Final = b"SQLite format 3\x00" + b"\x10\x00\x01\x01" + b"\x00" * 80
PDF: Final = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
PNG: Final = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 17
CSV: Final = "customer,amount\nAvenmoor Ltd,1200.00\nZürich AG,300.00\n".encode()
EML: Final = b"From: maya@demo.erev\r\nSubject: Acceptance\r\n\r\nAccepted.\r\n"


def ooxml(entries: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def xlsx(extra: Mapping[str, bytes] | None = None) -> bytes:
    return ooxml(
        {"[Content_Types].xml": XLSX_CONTENT_TYPES, "xl/workbook.xml": WORKBOOK, **(extra or {})}
    )


# SAR-42 billion-laughs shape: a DTD with nested entities inside an OOXML part. Three levels keep
# the fixture small; it is never parsed, only refused at upload (UPL-05 companion in policy.py).
BILLION_LAUGHS_WORKBOOK: Final = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    b'<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    b'<!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">]>'
    b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    b'<sheets><sheet name="&lol2;" sheetId="1"/></sheets></workbook>'
)


def xlsx_billion_laughs() -> bytes:
    """An `.xlsx`-shaped workbook whose `xl/workbook.xml` carries an entity-expansion DTD."""
    return xlsx({"xl/workbook.xml": BILLION_LAUGHS_WORKBOOK})


def _utf16(xml: bytes, byteorder: str, *, bom: bool) -> bytes:
    """``xml`` re-encoded as UTF-16 little- or big-endian, with or without a byte-order mark."""
    body = xml.decode("utf-8").encode(f"utf-16-{byteorder}")
    mark = codecs.BOM_UTF16_LE if byteorder == "le" else codecs.BOM_UTF16_BE
    return (mark if bom else b"") + body


def xlsx_billion_laughs_utf16(byteorder: str = "le", *, bom: bool = True) -> bytes:
    """The billion-laughs workbook part written in UTF-16 (Codex P8-SOP8-DTD-1): the ASCII
    markers ``<!DOCTYPE`` / ``<!ENTITY`` are interleaved with NUL bytes and evade a bytes-only
    search."""
    return xlsx({"xl/workbook.xml": _utf16(BILLION_LAUGHS_WORKBOOK, byteorder, bom=bom)})


def xlsx_with_declared_encoding(name: str) -> bytes:
    """A workbook whose part declares ``encoding="<name>"`` and carries no DTD: the control for a
    text encoding, the attack for a registered non-text codec (Codex P8-SOP8-CODEC-1)."""
    part = f'<?xml version="1.0" encoding="{name}"?>'.encode("ascii") + WORKBOOK
    return xlsx({"xl/workbook.xml": part})


def xlsx_utf16(byteorder: str = "le", *, bom: bool = True) -> bytes:
    """A clean workbook whose part is written in UTF-16 (the control for the refusal above)."""
    return xlsx({"xl/workbook.xml": _utf16(WORKBOOK, byteorder, bom=bom)})


def xlsx_with_vba_project() -> bytes:
    """An `.xlsx`-shaped workbook carrying `xl/vbaProject.bin` (UPL-03)."""
    return xlsx({"xl/vbaProject.bin": b"\x00Attribute VB_Name"})


def xlsm() -> bytes:
    """A macro-enabled workbook: macroEnabled content type and a VBA project."""
    return ooxml(
        {
            "[Content_Types].xml": XLSM_CONTENT_TYPES,
            "xl/workbook.xml": WORKBOOK,
            "xl/vbaProject.bin": b"\x00Attribute VB_Name",
        }
    )


def docx() -> bytes:
    return ooxml({"[Content_Types].xml": DOCX_CONTENT_TYPES, "word/document.xml": b"<document/>"})


def zip_archive() -> bytes:
    """A plain archive without OOXML parts."""
    return ooxml({"report.csv": CSV})


@cache
def ooxml_with_ratio(ratio: int) -> bytes:
    """An `.xlsx` whose `xl/sharedStrings.xml` compresses at the first size reaching ``ratio``:1.

    Deterministic random bytes followed by zeros; the zero run grows until the declared
    uncompressed size is at least ``ratio`` times the compressed size.
    """
    noise = random.Random(20260912).randbytes(4096)
    zeros = 0
    while True:
        workbook = xlsx({"xl/sharedStrings.xml": noise + bytes(zeros)})
        with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
            entry = archive.getinfo("xl/sharedStrings.xml")
        if entry.file_size >= ratio * entry.compress_size:
            return workbook
        zeros += 1024
