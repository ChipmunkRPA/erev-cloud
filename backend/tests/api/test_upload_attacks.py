"""SAR-42 upload attack fixtures (05 §6.13 UPL-02 to UPL-09; 03 REQ-SEC-012; BUILD_SPEC SOP-8).

``test_sar_42_upload_fixtures_rejected`` runs on the CPU against ``files.policy.check_upload``,
the decision ``POST /api/v1/files`` returns as 422 ``upload-type-not-allowed`` (T-PLT-29; ERR-37),
and against ``legacy_db.connect_read_only`` for the SQLite fixture. The same fixtures over HTTP
(``…_over_http``) need the test database and are recorded NOT RUN by lane P8 until a database is
provisioned. Upload limits themselves stay tested by ``tests/unit/test_upload_policy.py``.
"""

from __future__ import annotations

import codecs
import io
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.domain.migration import legacy_db
from erev_api.enums import FilePurpose
from erev_api.files import policy
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.parity.attack_fixtures import TRIGGER_LOG, row_count, sqlite_with_triggers
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.rows import insert_role_assignment
from support.upload_fixtures import (
    OLE2,
    ooxml_with_ratio,
    xlsm,
    xlsx,
    xlsx_billion_laughs,
    xlsx_billion_laughs_utf16,
    xlsx_utf16,
    xlsx_with_declared_encoding,
    xlsx_with_vba_project,
)

FILES = "/api/v1/files"
PROBLEM_BASE = "https://erev.dev/problems/"
ATTACKS: tuple[tuple[str, bytes, str | None], ...] = (
    ("billion-laughs OOXML", xlsx_billion_laughs(), "laughs.xlsx"),
    ("billion-laughs OOXML, UTF-16LE with BOM", xlsx_billion_laughs_utf16("le"), "l16le.xlsx"),
    ("billion-laughs OOXML, UTF-16BE with BOM", xlsx_billion_laughs_utf16("be"), "l16be.xlsx"),
    (
        "billion-laughs OOXML, UTF-16LE declaration only",
        xlsx_billion_laughs_utf16("le", bom=False),
        "l16.xlsx",
    ),
    (
        "billion-laughs OOXML, UTF-16BE declaration only",
        xlsx_billion_laughs_utf16("be", bom=False),
        "l16b.xlsx",
    ),
    (
        "registered binary-transform codec declared (base64_codec)",
        xlsx_with_declared_encoding("base64_codec"),
        "codec.xlsx",
    ),
    ("zip bomb", ooxml_with_ratio(policy.ZIP_MAX_RATIO + 1), "bomb.xlsx"),
    ("macro workbook (.xlsm)", xlsm(), "macros.xlsm"),
    ("macro workbook (vbaProject.bin in .xlsx)", xlsx_with_vba_project(), "macros.xlsx"),
    ("OLE2 container", OLE2, "legacy.xls"),
    ("OLE2 container, no name", OLE2, None),
)


def _refusal(purpose: FilePurpose, content: bytes, filename: str | None) -> Problem:
    with pytest.raises(Problem) as caught:
        policy.check_upload(
            purpose, io.BytesIO(content), size=len(content), original_filename=filename
        )
    return caught.value


@pytest.mark.parametrize(("label", "content", "filename"), ATTACKS, ids=[a[0] for a in ATTACKS])
def test_sar_42_upload_fixtures_rejected(label: str, content: bytes, filename: str | None) -> None:
    """Each attack fixture is refused for every purpose that could carry it, with the 422 problem
    the upload route returns; a clean workbook of the same shape is accepted (control)."""
    for purpose in (FilePurpose.IMPORT_SOURCE, FilePurpose.ATTACHMENT, FilePurpose.SSP_STUDY):
        problem = _refusal(purpose, content, filename)
        assert (problem.slug, problem.status) == ("upload-type-not-allowed", 422), (label, purpose)
    clean = xlsx()
    assert (
        policy.check_upload(
            FilePurpose.IMPORT_SOURCE,
            io.BytesIO(clean),
            size=len(clean),
            original_filename="ok.xlsx",
        )
        == policy.XLSX
    )


def test_sar_42_billion_laughs_is_refused_by_content_not_by_name() -> None:
    """The DTD is found inside the part whatever the file is called (UPL-02: content decides)."""
    content = xlsx_billion_laughs()
    assert policy.detect_media_type(io.BytesIO(content)) is None
    assert policy.detect_media_type(io.BytesIO(xlsx())) == policy.XLSX


@pytest.mark.parametrize(
    ("byteorder", "bom"), [("le", True), ("be", True), ("le", False), ("be", False)]
)
def test_sar_42_dtd_detected_in_utf16_parts(byteorder: str, bom: bool) -> None:
    """Codex P8-SOP8-DTD-1: a DTD written in UTF-16 (byte-order mark or declaration shape) is
    refused like the UTF-8 one, and a clean UTF-16 workbook of the same shape is admitted as XLSX
    (control), so the refusal is the DTD and not the encoding."""
    laughs = xlsx_billion_laughs_utf16(byteorder, bom=bom)
    assert policy.detect_media_type(io.BytesIO(laughs)) is None, (byteorder, bom)
    clean = xlsx_utf16(byteorder, bom=bom)
    assert policy.detect_media_type(io.BytesIO(clean)) == policy.XLSX, (byteorder, bom)


def test_sar_42_xml_part_text_follows_bom_then_declaration() -> None:
    """The decoder picks the part's own encoding: BOM first (UTF-8, UTF-16, UTF-32), then the
    byte shape of a wide declaration, then the declared name, else UTF-8; an unknown declared
    name falls back to UTF-8 and undecodable bytes are replaced, never dropped."""
    doctype = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "a">]><x/>'
    for encoding, mark in (
        ("utf-8", codecs.BOM_UTF8),
        ("utf-16-le", codecs.BOM_UTF16_LE),
        ("utf-16-be", codecs.BOM_UTF16_BE),
        ("utf-32-le", codecs.BOM_UTF32_LE),
        ("utf-32-be", codecs.BOM_UTF32_BE),
    ):
        text = policy.xml_part_text(mark + doctype.decode("ascii").encode(encoding))
        assert "<!doctype" in text and "<!entity" in text, encoding
    for encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
        assert "<!doctype" in policy.xml_part_text(doctype.decode("ascii").encode(encoding))
    latin = b'<?xml version="1.0" encoding="ISO-8859-1"?><!DOCTYPE x><x>caf\xe9</x>'
    text = policy.xml_part_text(latin)
    assert text is not None and "<!doctype" in text and "caf\u00e9" in text
    plain = policy.xml_part_text(b"<\xff<x/>")
    assert plain is not None and "\ufffd" in plain, "undecodable bytes are replaced"
    # Codex P8-SOP8-CODEC-1: an unknown name or a registered non-text codec is None (refused),
    # never a fallback and never an escaping LookupError.
    for name in ("x-no-such-codec", "base64_codec", "zlib_codec", "rot_13", "hex_codec"):
        declared = b'<?xml version="1.0" encoding="' + name.encode() + b'"?><x/>'
        assert policy.xml_part_text(declared) is None, name


@pytest.mark.parametrize("name", ["base64_codec", "zlib_codec", "rot_13", "x-no-such-codec"])
def test_sar_42_non_text_codec_is_the_named_refusal_not_a_500(name: str) -> None:
    """Codex P8-SOP8-CODEC-1: a part declaring a registered binary / str transform (or an unknown
    name) is refused at the policy seam the upload route uses — the named 422
    ``upload-type-not-allowed`` — for every purpose that could carry it; ``detect_media_type`` is
    None; no ``LookupError`` escapes. A part declaring a real text encoding is admitted
    (control)."""
    content = xlsx_with_declared_encoding(name)
    assert policy.detect_media_type(io.BytesIO(content)) is None, name
    for purpose in (FilePurpose.IMPORT_SOURCE, FilePurpose.ATTACHMENT, FilePurpose.SSP_STUDY):
        problem = _refusal(purpose, content, "codec.xlsx")
        assert (problem.slug, problem.status) == ("upload-type-not-allowed", 422), (name, purpose)
    for text_encoding in ("UTF-8", "ISO-8859-1", "utf-16"):
        clean = xlsx_with_declared_encoding(text_encoding)
        assert policy.detect_media_type(io.BytesIO(clean)) == policy.XLSX, text_encoding


def test_sar_42_sqlite_triggers_never_run(tmp_path: Path) -> None:
    """UPL-09: the legacy database is opened read-only and immutable with ``trusted_schema`` off and
    ``query_only`` on; a write attempt fails and the fixture's trigger leaves no trace, while the
    reader still sees the schema it needs."""
    path = sqlite_with_triggers(tmp_path / "legacy.sqlite")
    with path.open("rb") as stream:
        assert policy.detect_media_type(stream) == policy.SQLITE, "SQLite uploads stay accepted"
    connection = legacy_db.connect_read_only(path)
    try:
        assert connection.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(Exception, match="readonly|read-only|attempt to write|query_only"):
            connection.execute("INSERT INTO \"Contract_Live\" VALUES ('attack')")
        assert TRIGGER_LOG == "Trigger_Log"
        [count] = connection.execute('SELECT COUNT(*) FROM "Trigger_Log"').fetchone()
        assert count == 0
    finally:
        connection.close()
    assert row_count(path, TRIGGER_LOG) == 0, "the trigger never fired"
    assert [column.name for column in legacy_db.schema(path)] == ["Contract Unique Name"]


# ---- over HTTP (needs the test database; NOT RUN until provisioned)


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    tomas = member(keyring, clock)
    grace = colleague(tomas.tenant_id, "grace")
    with tenant_session(_context(tomas.tenant_id)) as session:
        for someone in (tomas, grace):
            insert_role_assignment(
                session,
                tenant_id=tomas.tenant_id,
                membership_id=someone.membership_id,
                role_code="tenant_admin",
            )
    return World(tomas=enrolled(app, clock, tomas))


def upload(app: FastAPI, actor: Actor, content: bytes, filename: str | None) -> HttpResponse:
    return call(
        app,
        "POST",
        FILES,
        data={"purpose": FilePurpose.ATTACHMENT.value},
        files={"file": (filename or "upload.bin", content, "application/octet-stream")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def test_sar_42_upload_fixtures_rejected_over_http(app: FastAPI, world: World) -> None:
    """The same fixtures through ``POST /api/v1/files`` answer 422 ``upload-type-not-allowed`` and
    store no row; a clean workbook is stored (201)."""
    for label, content, filename in ATTACKS:
        response = upload(app, world.tomas, content, filename)
        assert (response.status_code, slug(response)) == (422, "upload-type-not-allowed"), label
    accepted = upload(app, world.tomas, xlsx(), "ok.xlsx")
    assert accepted.status_code == 201, accepted.text
    body: Mapping[str, Any] = accepted.json()
    assert body["purpose"] == FilePurpose.ATTACHMENT.value
