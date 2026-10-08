"""Files, attachments and upload safety (04 T-PLT-29, T-PLT-30, API-R-12, DB-11; 05 UPL-02 to
UPL-04, UPL-10, PRV-06; dev-guide DG-KRN-FILE-01 to DG-KRN-FILE-03, DG-KRN-IDEM-04; REQ-PLT-035,
REQ-SEC-012; BUILD_SPEC PLF-8, BS1-D-21, BS1-D-28)."""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

import pytest
from erev_api.api.deps import CommandContext, KernelDeps, command, kernel_deps, run_command
from erev_api.api.middleware import MULTIPART_OVERHEAD_BYTES
from erev_api.api.v1.files import content_disposition
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    evidence_pack,
    file_object,
    file_upload,
    idempotency_record,
    ssp_calculator_run,
)
from erev_api.domain.platform.attachments import ANY_UPLOAD_PERMISSION
from erev_api.domain.platform.file_access import ATTACHMENT_SUBJECTS, referencing_scopes
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    FilePurpose,
    PrincipalKind,
    TenantKind,
)
from erev_api.files import policy
from erev_api.files.store import store_file
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import Depends, FastAPI, Response
from sqlalchemy import insert, select, update
from support import upload_fixtures as fx
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    Member,
    Signed,
    colleague,
    cookie_headers,
    cookie_of,
    member,
    select_tenant,
    sign_in,
)
from support.principals import workspace as at_work
from support.rows import (
    ROW_BUILDERS,
    RowContext,
    evidence_pack_values,
    file_object_values,
    insert_approval_request,
    insert_approval_step,
    insert_contract_rows,
    insert_custom_role,
    insert_import_upload,
    insert_probe_row,
    insert_role_assignment,
    insert_sod_exception,
    revoke_role_assignments,
)

FILES = "/api/v1/files"
ATTACHMENTS = "/api/v1/attachments"
LARGE = "/api/v1/__tests__/large-response"
PROBLEM_BASE = "https://erev.dev/problems/"
# One byte above the 1 MiB DG-KRN-IDEM-04 limit once rendered as {"blob": "..."}.
LARGE_BLOB = "x" * 1_048_577


@dataclass(frozen=True, slots=True)
class Actor:
    member: Member
    token: str
    csrf_token: str


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    application = create_app(app_settings, clock=clock)

    @application.post(LARGE)
    def large_response(
        cmd: Annotated[CommandContext, Depends(command("report.run"))],
        deps: Annotated[KernelDeps, Depends(kernel_deps)],
    ) -> Response:
        return run_command(cmd, deps, lambda uow: {"blob": LARGE_BLOB})

    return application


def _all_entities(tenant_id: uuid.UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def assign(someone: Member, *role_codes: str) -> None:
    with tenant_session(_all_entities(someone.tenant_id)) as session:
        for role_code in role_codes:
            insert_role_assignment(
                session,
                tenant_id=someone.tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
            )


def workspace(app: FastAPI, someone: Member, signed: Signed) -> Actor:
    selected = select_tenant(app, signed, someone.tenant_id)
    assert selected.status_code == 200, selected.text
    return Actor(
        member=someone, token=cookie_of(selected), csrf_token=selected.json()["csrf_token"]
    )


@pytest.fixture
def accountant(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    """A Revenue Accountant: import.upload, migration.run, subject writes and report.run."""
    someone = member(keyring, clock)
    assign(someone, "revenue_accountant")
    return workspace(app, someone, sign_in(app, someone.email))


def enrolled(app: FastAPI, clock: FrozenClock, signed: Signed) -> Signed:
    """Confirm TOTP enrolment; the rotated session is verified (SPEC-Q-145)."""
    headers = cookie_headers(signed.token, signed.csrf_token)
    started = call(app, "POST", "/api/v1/me/mfa/enroll", headers=headers)
    assert started.status_code == 200, started.text
    code = totp.code_at(started.json()["secret_base32"], totp.time_step(clock.now()))
    confirmed = call(
        app,
        "POST",
        "/api/v1/me/mfa/confirm",
        json={"code": code},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    assert confirmed.status_code == 200, confirmed.text
    token = cookie_of(confirmed)
    body = call(app, "GET", "/api/v1/session", headers={"Cookie": f"erev_session={token}"}).json()
    return Signed(token=token, csrf_token=body["csrf_token"], body=body)


def upload(
    app: FastAPI,
    actor: Actor,
    purpose: str,
    name: str,
    content: bytes,
    *,
    key: str | None = None,
) -> HttpResponse:
    headers = cookie_headers(actor.token, actor.csrf_token)
    if key is not None:
        headers["Idempotency-Key"] = key
    return call(
        app,
        "POST",
        FILES,
        data={"purpose": purpose},
        files={"file": (name, content, "application/octet-stream")},
        headers=headers,
    )


def send(app: FastAPI, method: str, path: str, actor: Actor, **kwargs: Any) -> HttpResponse:
    return call(app, method, path, headers=cookie_headers(actor.token, actor.csrf_token), **kwargs)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def file_rows(actor: Actor) -> list[dict[str, Any]]:
    with tenant_session(_all_entities(actor.member.tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(select(file_object)).mappings()]


def test_req_sec_012_rejects_macro_and_archives(app: FastAPI, accountant: Actor) -> None:
    for name, content in (
        ("revenue.xlsx", fx.xlsx_with_vba_project()),
        ("revenue.xlsm", fx.xlsm()),
        ("protected.xlsx", fx.OLE2),
        ("bundle.zip", fx.zip_archive()),
    ):
        response = upload(app, accountant, "IMPORT_SOURCE", name, content)
        assert response.status_code == 422, (name, response.text)
        assert slug(response) == "upload-type-not-allowed"
        assert response.json()["detail"] == (
            "Import files must be .xlsx or .csv and at most 50 MiB. "
            "Macro-enabled workbooks and archives are not accepted."
        )
    assert file_rows(accountant) == []
    accepted = upload(app, accountant, "IMPORT_SOURCE", "orders.xlsx", fx.xlsx())
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["media_type"] == policy.XLSX


def test_upload_limits_per_purpose(app: FastAPI, accountant: Actor) -> None:
    oversized = fx.PDF + b"\x00" * (26_214_401 - len(fx.PDF))
    response = upload(app, accountant, "ATTACHMENT", "acceptance.pdf", oversized)
    assert response.status_code == 422, response.text
    assert slug(response) == "upload-type-not-allowed"
    assert response.json()["detail"] == (
        "Attachments and SSP studies must be pdf, docx, xlsx, csv, png, jpg or eml files "
        "of at most 25 MiB."
    )
    legacy = upload(app, accountant, "LEGACY_DATABASE", "ASC606.db", b"PRAGMA user_version;\n")
    assert legacy.status_code == 422, legacy.text
    assert legacy.json()["detail"] == "Legacy databases must be SQLite files of at most 500 MiB."
    report = upload(app, accountant, "REPORT_OUTPUT", "report.csv", fx.CSV)
    assert report.status_code == 422, report.text
    assert slug(report) == "validation-failed"
    assert [error["field"] for error in report.json()["errors"]] == ["purpose"]
    assert file_rows(accountant) == []
    database = upload(app, accountant, "LEGACY_DATABASE", "ASC606.db", fx.SQLITE)
    assert database.status_code == 201, database.text
    assert (database.json()["purpose"], database.json()["media_type"]) == (
        "LEGACY_DATABASE",
        "application/vnd.sqlite3",
    )


def test_upl_04_zip_limits(app: FastAPI, accountant: Actor) -> None:
    response = upload(app, accountant, "IMPORT_SOURCE", "ratio.xlsx", fx.ooxml_with_ratio(101))
    assert response.status_code == 422, response.text
    assert slug(response) == "upload-type-not-allowed"
    assert file_rows(accountant) == []


def test_krn_file_01_content_addressed_deduplication(app: FastAPI, accountant: Actor) -> None:
    first = upload(app, accountant, "ATTACHMENT", "acceptance.pdf", fx.PDF)
    assert first.status_code == 201, first.text
    assert first.headers["location"] == f"{FILES}/{first.json()['id']}"
    second = upload(app, accountant, "ATTACHMENT", "acceptance-copy.pdf", fx.PDF)
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    # A retry of the first request with another multipart boundary replays it (SPEC-Q-159).
    key = "upload-retry-0001"
    original = upload(app, accountant, "ATTACHMENT", "study.csv", fx.CSV, key=key)
    retried = upload(app, accountant, "ATTACHMENT", "study.csv", fx.CSV, key=key)
    assert retried.status_code == 201, retried.text
    assert retried.headers["idempotent-replay"] == "true"
    assert retried.json() == original.json()
    (row,) = [row for row in file_rows(accountant) if row["id"] == uuid.UUID(first.json()["id"])]
    sha256 = hashlib.sha256(fx.PDF).hexdigest()
    assert row["sha256"] == sha256
    assert row["storage_key"] == f"{accountant.member.tenant_id}/ATTACHMENT/{sha256}"
    assert (row["size_bytes"], row["media_type"], row["original_filename"]) == (
        len(fx.PDF),
        "application/pdf",
        "acceptance.pdf",
    )
    with tenant_session(_all_entities(accountant.member.tenant_id), read_only=True) as session:
        uploads = session.execute(
            select(audit_event.c.detail).where(audit_event.c.action == "file.upload")
        ).scalars()
        assert sorted(detail["ids"][0] for detail in uploads) == sorted(
            {first.json()["id"], original.json()["id"]}
        )


def test_r_111_5_an_uploader_of_the_same_bytes_is_shown_their_own_upload(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 5 (ruling R-111 (5), item
    FILE-DEDUPE-READER-1); 04 T-PLT-29 "Uploads of the same bytes" and T-PLT-49, rev 1.189.
    Identical content of one purpose is one stored row, and ``POST /files`` answered that row to
    whoever uploaded the same bytes again: the first uploader's file name, time and identity —
    so a member who uploaded a known document learned who had stored it first, when and under
    what name. Each uploader has a row of their own (T-PLT-49) and is shown their own facts; a
    caller who reads the file through a record that owns it sees the stored row."""
    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id)
    lena = joined(app, tenant_id, "lena", "revenue_accountant")
    pete = joined(app, tenant_id, "pete", "revenue_accountant")
    auditor = joined(app, tenant_id, "ava", "auditor")  # reads contracts and their attachments
    content = fx.PDF + b"% board pack\n"

    first = upload(app, lena, "ATTACHMENT", "board-pack-DRAFT-lena.pdf", content)
    assert first.status_code == 201, first.text
    file_id = first.json()["id"]
    stored_at = first.json()["created_at"]
    clock.advance(timedelta(minutes=10))  # within the sessions' idle time
    second = upload(app, pete, "ATTACHMENT", "copy.pdf", content)
    assert second.status_code == 201, second.text
    answered = second.json()
    # The stored id and the content facts, with Pete's own name, time and identity.
    assert (answered["id"], answered["sha256"], answered["size_bytes"]) == (
        file_id,
        first.json()["sha256"],
        len(content),
    )
    assert answered["original_filename"] == "copy.pdf", answered
    assert answered["created_by"] == str(pete.member.user_id)
    assert answered["created_at"] != stored_at
    assert answered["created_at"] == clock.now().isoformat().replace("+00:00", "Z")
    assert "board-pack-DRAFT-lena.pdf" not in second.text
    assert str(lena.member.user_id) not in second.text

    # GET /files/{id} and the download answer each uploader with their own upload.
    for actor, name, uploader in (
        (pete, "copy.pdf", pete.member.user_id),
        (lena, "board-pack-DRAFT-lena.pdf", lena.member.user_id),
    ):
        shown = read(app, f"{FILES}/{file_id}", actor)
        assert shown.status_code == 200, shown.text
        assert (shown.json()["original_filename"], shown.json()["created_by"]) == (
            name,
            str(uploader),
        )
        downloaded = read(app, f"{FILES}/{file_id}/content", actor)
        assert downloaded.content == content
        assert name in downloaded.headers["content-disposition"]
    assert "board-pack-DRAFT-lena.pdf" not in read(app, f"{FILES}/{file_id}", pete).text
    # A third member, who uploaded nothing, reads nothing: the id alone opens no file.
    assert_hidden(app, file_id, auditor)

    # One row per file and uploader, each with its uploader's own name; one audit fact each.
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        uploads = session.execute(
            select(file_upload.c.uploaded_by, file_upload.c.original_filename).where(
                file_upload.c.file_object_id == uuid.UUID(file_id)
            )
        ).all()
        facts = session.execute(
            select(audit_event.c.actor_id, audit_event.c.detail)
            .where(audit_event.c.action == "file.upload")
            .order_by(audit_event.c.chain_seq)
        ).all()
    assert sorted(uploads, key=lambda row: str(row[1])) == [
        (lena.member.user_id, "board-pack-DRAFT-lena.pdf"),
        (pete.member.user_id, "copy.pdf"),
    ]
    assert [(actor_id, detail.get("deduplicated")) for actor_id, detail in facts] == [
        (lena.member.user_id, None),
        (pete.member.user_id, True),
    ]
    # The same uploader again under another name (04 T-PLT-49 Keys; ruling R-119 (f)): no second
    # row and no second audit fact, and the name and time of their first upload stay — for the
    # second uploader and for the first.
    clock.advance(timedelta(minutes=5))
    # Each call goes out under a NEW idempotency key and answers the stored file's id — to the
    # second uploader and to the first: content identity is what a command sequence that sends
    # an upload again relies on (API-R-12; the supervisor's message of 2026-10-01, W-23).
    for actor, renamed, name, at in (
        (pete, "copy-renamed.pdf", "copy.pdf", answered["created_at"]),
        (lena, "board-pack-FINAL.pdf", "board-pack-DRAFT-lena.pdf", stored_at),
    ):
        again = upload(app, actor, "ATTACHMENT", renamed, content)
        assert again.status_code == 201, again.text
        assert "idempotent-replay" not in again.headers  # a new execution, not a replay
        assert (again.json()["id"], again.json()["original_filename"]) == (file_id, name)
        assert again.json()["created_at"] == at
        assert renamed not in read(app, f"{FILES}/{file_id}", actor).text
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        kept = session.execute(
            select(file_upload.c.original_filename, file_upload.c.uploaded_at).where(
                file_upload.c.file_object_id == uuid.UUID(file_id)
            )
        ).all()
        recorded = session.execute(
            select(audit_event.c.actor_id).where(audit_event.c.action == "file.upload")
        ).all()
    assert sorted(name for name, _ in kept) == ["board-pack-DRAFT-lena.pdf", "copy.pdf"]
    assert all(at < clock.now() for _, at in kept), kept
    assert len(recorded) == 2, recorded

    # The second uploader uses the upload as the first does. Once a record owns the file, a
    # caller who reads it through that record sees the stored row, as before.
    assert attach_to(app, pete, file_id, "contract", north.contract_id).status_code == 201
    through_the_contract = read(app, f"{FILES}/{file_id}", auditor)
    assert through_the_contract.status_code == 200, through_the_contract.text
    assert through_the_contract.json()["original_filename"] == "board-pack-DRAFT-lena.pdf"


def downloads(tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    """The workspace's ``file.download`` audit events, in chain order."""
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(
                audit_event.c.outcome,
                audit_event.c.actor_id,
                audit_event.c.object_type,
                audit_event.c.object_id,
                audit_event.c.request_id,
                audit_event.c.detail,
            )
            .where(audit_event.c.action == "file.download")
            .order_by(audit_event.c.chain_seq)
        ).mappings()
        return [dict(row) for row in rows]


def test_r_111_6_a_content_read_is_audited_served_or_refused(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 8 (ruling R-111 (6)); 04
    T-PLT-29 "Content reads are audited", rev 1.189. A read through ``GET /files/{id}/content``
    left no trace, served or refused, where the report and journal downloads audit each export.
    It writes one ``file.download`` event under the request's id: ``SUCCESS`` when the bytes are
    served, ``DENIED`` when the id names a file of the workspace the caller may not read — and
    the answer stays the 404 of an unknown id. An unknown id and the metadata read write none."""
    tenant_id = member(keyring, clock).tenant_id
    lena = joined(app, tenant_id, "lena", "revenue_accountant")
    pete = joined(app, tenant_id, "pete", "revenue_accountant")  # uploaded nothing
    content = fx.PDF + b"% audited read\n"
    created = upload(app, lena, "ATTACHMENT", "acceptance.pdf", content)
    assert created.status_code == 201, created.text
    file_id = created.json()["id"]
    assert downloads(tenant_id) == []

    # The metadata read is not a content read.
    assert read(app, f"{FILES}/{file_id}", lena).status_code == 200
    assert downloads(tenant_id) == []

    served = read(app, f"{FILES}/{file_id}/content", lena)
    assert (served.status_code, served.content) == (200, content), served.text
    refused = read(app, f"{FILES}/{file_id}/content", pete)
    unknown = read(app, f"{FILES}/{uuid.uuid4()}/content", pete)
    for answer in (refused, unknown):
        assert (answer.status_code, slug(answer)) == (404, "not-found"), answer.text
    assert {**refused.json(), "instance": None} == {**unknown.json(), "instance": None}
    # Neither metadata read of a hidden or unknown file is on record either.
    assert read(app, f"{FILES}/{file_id}", pete).status_code == 404

    sha256 = hashlib.sha256(content).hexdigest()
    assert downloads(tenant_id) == [
        {
            "outcome": "SUCCESS",
            "actor_id": lena.member.user_id,
            "object_type": "file_object",
            "object_id": uuid.UUID(file_id),
            "request_id": served.headers["X-Request-Id"],
            "detail": {"purpose": "ATTACHMENT", "sha256": sha256},
        },
        {
            "outcome": "DENIED",
            "actor_id": pete.member.user_id,
            "object_type": "file_object",
            "object_id": uuid.UUID(file_id),
            "request_id": refused.headers["X-Request-Id"],
            "detail": {"reason": "not-readable", "purpose": "ATTACHMENT", "permission": ""},
        },
    ]


BOUNDARY = "erev-upload-guard"
STREAM_CHUNK = 64 * 1024


def streamed(
    app: FastAPI,
    headers: Mapping[str, str],
    *,
    payload: int,
    declared: int | None = None,
    purpose: str = "ATTACHMENT",
) -> tuple[HttpResponse, int]:
    """``POST /files`` with a multipart body whose file part holds ``payload`` zero bytes, sent
    in 64 KiB chunks: the response, and the number of body bytes the application asked the
    client for. ``declared`` replaces the true ``Content-Length``."""
    head = (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\n{purpose}\r\n'
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="doc.pdf"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    tail = f"\r\n--{BOUNDARY}--\r\n".encode()
    pulled: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        pulled.append(len(head))
        yield head
        remaining = payload
        while remaining:
            size = min(STREAM_CHUNK, remaining)
            remaining -= size
            pulled.append(size)
            yield bytes(size)
        pulled.append(len(tail))
        yield tail

    total = len(head) + payload + len(tail)
    response = call(
        app,
        "POST",
        FILES,
        content=body(),
        headers={
            **headers,
            "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
            "Content-Length": str(total if declared is None else declared),
        },
    )
    return response, sum(pulled)


def test_r_111_8_an_upload_is_authenticated_before_its_body_is_read(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 10 (ruling R-111 (8)); 04
    API-C-17 rev 1.189. FastAPI parses a multipart form before it solves a route's guard, so
    ``POST /files`` received and spooled a body — up to the 500 MiB route limit — from a client
    without a session before it answered 401. The route asks everything that needs no body
    first, and then reads no more than its caller could store. "Pulled" is the number of body
    bytes the application asked the client for."""
    tenant_id = member(keyring, clock).tenant_id
    megabyte = 1024 * 1024
    limit = policy.UPLOAD_LIMITS[FilePurpose.ATTACHMENT]

    # No session; a session that owes its second factor; no synchronizer token; no key.
    nobody, pulled = streamed(app, {"Idempotency-Key": "upload-guard-0001"}, payload=2 * megabyte)
    assert (nobody.status_code, slug(nobody), pulled) == (401, "unauthenticated", 0)
    rhea = colleague(tenant_id, "rhea")
    assign(rhea, "controller")  # MFA is mandatory, and she has not enrolled
    pending = sign_in(app, rhea.email)
    assert pending.body["mfa_enrolment_required"] is True
    owed, pulled = streamed(
        app, cookie_headers(pending.token, pending.csrf_token), payload=2 * megabyte
    )
    assert (owed.status_code, slug(owed), pulled) == (403, "mfa-required", 0)
    sana = joined(app, tenant_id, "sana", "ssp_analyst")  # SSP studies and attachments: 25 MiB
    forged, pulled = streamed(app, cookie_headers(sana.token), payload=2 * megabyte)
    assert (forged.status_code, slug(forged), pulled) == (403, "forbidden", 0)
    assert forged.json()["errors"][0]["rule_id"] == "API-C-02"
    keyless, pulled = streamed(
        app, cookie_headers(sana.token, sana.csrf_token, key=False), payload=2 * megabyte
    )
    assert (keyless.status_code, slug(keyless), pulled) == (422, "validation-failed", 0)
    assert keyless.json()["errors"][0]["rule_id"] == "API-C-04"

    # A caller who may upload for no purpose is refused a body above the envelope, unread; the
    # attempt is on record, naming every upload permission — no purpose was read.
    vera = joined(app, tenant_id, "vera", "viewer")
    refused, pulled = streamed(
        app, cookie_headers(vera.token, vera.csrf_token), payload=2 * megabyte
    )
    assert (refused.status_code, slug(refused), pulled) == (403, "forbidden", 0)
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        denied = session.execute(
            select(audit_event.c.actor_id, audit_event.c.request_id, audit_event.c.detail).where(
                audit_event.c.outcome == "DENIED", audit_event.c.action == "file.upload"
            )
        ).all()
    codes = sorted(ANY_UPLOAD_PERMISSION)
    assert [
        (actor_id, request_id, detail["permission"], detail["permissions"])
        for actor_id, request_id, detail in denied
    ] == [(vera.member.user_id, refused.headers["X-Request-Id"], "|".join(codes), codes)]

    # A caller who may upload sends no more than its largest purpose allows: refused on the
    # declared length, unread ...
    oversized, pulled = streamed(
        app, cookie_headers(sana.token, sana.csrf_token), payload=limit + 2 * megabyte
    )
    assert (oversized.status_code, slug(oversized), pulled) == (422, "upload-type-not-allowed", 0)
    assert oversized.json()["detail"] == policy.ATTACHMENT_DETAIL
    # ... and counted while the body is read, whatever length was declared.
    lied, pulled = streamed(
        app,
        cookie_headers(sana.token, sana.csrf_token),
        payload=limit + 2 * megabyte,
        declared=4096,
    )
    assert (lied.status_code, slug(lied)) == (422, "upload-type-not-allowed"), lied.text
    assert lied.json()["detail"] == policy.ATTACHMENT_DETAIL
    assert limit < pulled <= limit + MULTIPART_OVERHEAD_BYTES + 2 * STREAM_CHUNK
    assert file_rows(sana) == []

    # Positive controls: within its bound each caller is answered as before — a body below the
    # caller's largest purpose is read and stored, and a caller without the permission of the
    # purpose the form names gets the command's own refusal, which names that permission.
    read_in_full, pulled = streamed(
        app, cookie_headers(sana.token, sana.csrf_token), payload=megabyte, purpose="SSP_STUDY"
    )
    # Zero bytes are no document: the type refuses, after the whole body was read.
    assert (read_in_full.status_code, slug(read_in_full)) == (422, "upload-type-not-allowed")
    assert pulled > megabyte
    accepted = upload(app, sana, "SSP_STUDY", "study.pdf", fx.PDF)
    assert accepted.status_code == 201, accepted.text
    small = upload(app, vera, "IMPORT_SOURCE", "orders.csv", fx.CSV)
    assert (small.status_code, slug(small)) == (403, "forbidden"), small.text
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        named = session.execute(
            select(audit_event.c.detail).where(
                audit_event.c.outcome == "DENIED",
                audit_event.c.action == "file.upload",
                audit_event.c.request_id == small.headers["X-Request-Id"],
            )
        ).scalar_one()
    assert named["permission"] == "import.upload"


def test_r_111_8_the_requester_of_a_pending_request_uploads_its_evidence(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Ruling R-111 (8) beside R-100 (b): the bound of an upload is what its caller may store,
    and the requester of a pending approval request stores an attachment whatever they hold. A
    Revenue Reviewer without a request is refused a body above the envelope, unread; with a
    pending request of their own the same body is read, and one above 25 MiB is not."""
    tenant_id = member(keyring, clock).tenant_id
    rhea = joined(app, tenant_id, "rhea", "revenue_reviewer")  # no upload permission
    megabyte = 1024 * 1024
    headers = cookie_headers(rhea.token, rhea.csrf_token)

    before, pulled = streamed(app, headers, payload=megabyte)
    assert (before.status_code, slug(before), pulled) == (403, "forbidden", 0)
    with tenant_session(_all_entities(tenant_id)) as session:
        request_id = insert_approval_request(
            session,
            tenant_id=tenant_id,
            preparer_id=rhea.member.user_id,
            subject_type=ApprovalSubjectType.PERIOD_REOPEN.value,
        )
        insert_approval_step(
            session,
            tenant_id=tenant_id,
            approval_request_id=request_id,
            required_permission="period.reopen_approve",
        )
    document = fx.PDF + b"%" + b" job cost report" * 12_000 + b"\n"  # above the envelope
    assert len(document) > MULTIPART_OVERHEAD_BYTES
    evidence = upload(app, rhea, "ATTACHMENT", "job-cost.pdf", document)
    assert evidence.status_code == 201, evidence.text
    too_large, pulled = streamed(
        app,
        cookie_headers(rhea.token, rhea.csrf_token),
        payload=policy.UPLOAD_LIMITS[FilePurpose.ATTACHMENT] + megabyte,
    )
    assert (too_large.status_code, slug(too_large), pulled) == (
        422,
        "upload-type-not-allowed",
        0,
    )


def test_bs1_d_21_encrypted_storage_with_sidecar(
    app: FastAPI, accountant: Actor, app_settings: Settings
) -> None:
    created = upload(app, accountant, "ATTACHMENT", "acceptance final.pdf", fx.PDF)
    assert created.status_code == 201, created.text
    file_id = created.json()["id"]
    (row,) = file_rows(accountant)
    stored = Path(app_settings.file_root) / row["storage_key"]
    assert stored.is_file()
    ciphertext = stored.read_bytes()
    assert ciphertext != fx.PDF
    assert b"%PDF-" not in ciphertext
    assert (stored.parent / f"{stored.name}.dek").is_file()

    content = send(app, "GET", f"{FILES}/{file_id}/content", accountant)
    assert content.status_code == 200, content.text
    assert content.content == fx.PDF
    assert content.headers["content-type"] == "application/pdf"
    assert content.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''acceptance%20final.pdf"
    )
    # Names are metadata only: control characters, quotes and path separators never reach the
    # header (UPL-10, UPL-11).
    assert content_disposition({"original_filename": 'x"y/z\n.pdf', "sha256": "ab"}) == (
        "attachment; filename*=UTF-8''x_y_z_.pdf"
    )
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.headers["content-security-policy"] == "sandbox"
    metadata = send(app, "GET", f"{FILES}/{file_id}", accountant)
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["sha256"] == hashlib.sha256(fx.PDF).hexdigest()
    assert send(app, "GET", f"{FILES}/{uuid.uuid4()}/content", accountant).status_code == 404


def test_upload_needs_a_purpose_permission(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    someone = member(keyring, clock)
    assign(someone, "viewer")
    viewer = workspace(app, someone, sign_in(app, someone.email))
    response = upload(app, viewer, "IMPORT_SOURCE", "orders.csv", fx.CSV)
    assert response.status_code == 403, response.text
    assert slug(response) == "forbidden"
    assert file_rows(viewer) == []
    with tenant_session(_all_entities(someone.tenant_id), read_only=True) as session:
        denied = session.execute(
            select(audit_event.c.action, audit_event.c.outcome, audit_event.c.detail).where(
                audit_event.c.outcome == "DENIED"
            )
        ).all()
    assert [(action, outcome) for action, outcome, _ in denied] == [("file.upload", "DENIED")]
    assert denied[0].detail["permission"] == "import.upload"


def test_req_plt_035_attach_and_void(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    someone = member(keyring, clock)
    assign(someone, "revenue_accountant", "tenant_admin")
    admin = workspace(app, someone, enrolled(app, clock, sign_in(app, someone.email)))
    with tenant_session(_all_entities(someone.tenant_id)) as session:
        exception_id = insert_sod_exception(
            session, tenant_id=someone.tenant_id, membership_id=someone.membership_id
        )
    created = upload(app, admin, "ATTACHMENT", "compensating-control.pdf", fx.PDF)
    assert created.status_code == 201, created.text
    file_id = created.json()["id"]

    attach = {
        "file_object_id": file_id,
        "subject_type": "sod_exception",
        "subject_id": str(exception_id),
    }
    attached = send(app, "POST", ATTACHMENTS, admin, json={**attach, "description": "Control memo"})
    assert attached.status_code == 201, attached.text
    attachment = attached.json()
    assert (
        attachment["subject_type"],
        attachment["original_filename"],
        attachment["voided_at"],
    ) == (
        "sod_exception",
        "compensating-control.pdf",
        None,
    )
    # An id that names no record of the subject type is not found (REQ-PLT-012).
    missing = send(app, "POST", ATTACHMENTS, admin, json={**attach, "subject_type": "contract"})
    assert missing.status_code == 404, missing.text

    listed = send(
        app,
        "GET",
        ATTACHMENTS,
        admin,
        params={"subject_type": "sod_exception", "subject_id": str(exception_id), "count": "true"},
    )
    assert listed.status_code == 200, listed.text
    assert listed.headers["x-erev-total-count"] == "1"
    assert [item["id"] for item in listed.json()["items"]] == [attachment["id"]]
    assert listed.json()["next_cursor"] is None

    voided = send(
        app, "POST", f"{ATTACHMENTS}/{attachment['id']}/void", admin, json={"reason": "Wrong memo"}
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["voided_at"] == clock.now().isoformat().replace("+00:00", "Z")
    assert (voided.json()["void_reason"], voided.json()["voided_by"]) == (
        "Wrong memo",
        str(someone.user_id),
    )
    again = send(
        app, "POST", f"{ATTACHMENTS}/{attachment['id']}/void", admin, json={"reason": "Again"}
    )
    assert again.status_code == 409, again.text
    assert slug(again) == "invalid-transition"
    with tenant_session(_all_entities(someone.tenant_id), read_only=True) as session:
        actions = session.execute(
            select(audit_event.c.action, audit_event.c.object_id).where(
                audit_event.c.action.in_(["file_attachment.create", "file_attachment.void"])
            )
        ).all()
    assert sorted(actions) == sorted(
        [
            ("file_attachment.create", uuid.UUID(attachment["id"])),
            ("file_attachment.void", uuid.UUID(attachment["id"])),
        ]
    )


def joined(
    app: FastAPI,
    tenant_id: uuid.UUID,
    name: str,
    *role_codes: str,
    entity_ids: tuple[uuid.UUID, ...] = (),
) -> Actor:
    """A colleague holding ``role_codes`` — for ``entity_ids`` only, when given — at work in the
    tenant, the second factor passed where a role makes it mandatory."""
    someone = colleague(tenant_id, name)
    with tenant_session(_all_entities(tenant_id)) as session:
        for role_code in role_codes:
            insert_role_assignment(
                session,
                tenant_id=tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
                entity_ids=entity_ids,
            )
    signed = at_work(app, someone, sign_in(app, someone.email))
    return Actor(member=someone, token=signed.token, csrf_token=signed.csrf_token)


def read(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def assert_hidden(app: FastAPI, file_id: str, *actors: Actor) -> None:
    """Metadata and content answer 404 ``not-found``, word for word as for an unknown id."""
    for actor in actors:
        unknown = read(app, f"{FILES}/{uuid.uuid4()}/content", actor)
        for path in (f"{FILES}/{file_id}", f"{FILES}/{file_id}/content"):
            hidden = read(app, path, actor)
            assert hidden.status_code == 404, (path, actor.member.email, hidden.text[:200])
            assert slug(hidden) == "not-found", hidden.text
            assert {**hidden.json(), "instance": None} == {**unknown.json(), "instance": None}


def attached(app: FastAPI, actor: Actor, subject_type: str, subject_id: uuid.UUID) -> list[str]:
    """The file ids of the attachments the actor lists on the subject."""
    listed = read(app, ATTACHMENTS, actor, subject_type=subject_type, subject_id=str(subject_id))
    assert listed.status_code == 200, listed.text
    return [item["file_object_id"] for item in listed.json()["items"]]


def attach_to(
    app: FastAPI, actor: Actor, file_id: str, subject_type: str, subject_id: uuid.UUID
) -> HttpResponse:
    return send(
        app,
        "POST",
        ATTACHMENTS,
        actor,
        json={
            "file_object_id": file_id,
            "subject_type": subject_type,
            "subject_id": str(subject_id),
        },
    )


def void(app: FastAPI, actor: Actor, attachment_id: str) -> HttpResponse:
    path = f"{ATTACHMENTS}/{attachment_id}/void"
    return send(app, "POST", path, actor, json={"reason": "Wrong document"})


def test_req_plt_035_a_file_is_read_through_the_record_that_owns_it(
    app: FastAPI, accountant: Actor
) -> None:
    """Security review S2 (ruling R-48 (c)). ``audit.read`` opened every file of the workspace:
    an Auditor downloaded an import source nothing tied it to. A file is read by its uploader and
    through a record that owns it, by the people who read that record — for an import, which
    does not name its entities yet, with the permission for all entities (R-28)."""
    tenant_id = accountant.member.tenant_id
    source = b"secret_customer,secret_amount\nAcme Corp,9999999.00\n"
    uploaded = upload(app, accountant, "IMPORT_SOURCE", "q3-orders.csv", source)
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id)
    auditor = joined(app, tenant_id, "ava", "auditor")  # audit.read, contract.read
    admin = joined(app, tenant_id, "tomas", "tenant_admin")  # audit.read, contract.read
    reviewer = joined(app, tenant_id, "rhea", "revenue_reviewer")  # import.approve
    # The same grants as the uploader's, audit.read among them, for one entity only.
    narrow = joined(app, tenant_id, "nils", "revenue_accountant", entity_ids=(north.entity_id,))
    outsider = joined(app, tenant_id, "otto")  # a member without a role

    # The uploader reads the upload back. Nothing owns it yet, so nobody else reads it —
    # whatever they hold, ``audit.read`` included.
    assert read(app, f"{FILES}/{file_id}/content", accountant).content == source
    assert_hidden(app, file_id, auditor, admin, reviewer, narrow, outsider)

    # An import of the file owns it: the people who read contracts and approve imports read it
    # (R-98) — with their permission for all entities, because this import's entities are not
    # resolved. Nils holds them for one entity.
    with tenant_session(_all_entities(tenant_id)) as session:
        insert_import_upload(session, tenant_id=tenant_id, file_object_id=uuid.UUID(file_id))
    for reader in (auditor, admin, reviewer):
        shown = read(app, f"{FILES}/{file_id}/content", reader)
        assert shown.status_code == 200, shown.text
        assert shown.content == source
        assert read(app, f"{FILES}/{file_id}", reader).json()["purpose"] == "IMPORT_SOURCE"
    assert_hidden(app, file_id, narrow, outsider)


REPOSITORY = Path(__file__).resolve().parents[3]
READ_ACCESS_HEADING = "**Read access (authoritative"
READ_ACCESS_HEADER = "| Purpose | Owner | Read by | Entity |"
WITHOUT_ONE = "; all entities without one"
# The entity of an owner whose row does not carry it: the column that names the row that does.
PARENT_OF = {"lock_snapshot": ("period_lock", "period_lock_id")}
SWEEP_UPLOADS = {
    FilePurpose.IMPORT_SOURCE: ("source.csv", "text/csv"),
    FilePurpose.LEGACY_DATABASE: ("legacy.db", "application/octet-stream"),
}


@dataclass(frozen=True, slots=True)
class DocumentedOwner:
    """One row of 04 T-PLT-29 "Read access" that names permissions."""

    purpose: FilePurpose
    table: str
    column: str
    permissions: tuple[str, ...]
    entity: str  # the Entity cell

    @property
    def ref(self) -> str:
        return f"{self.table}.{self.column}"


def documented_owners() -> list[DocumentedOwner]:
    """The owners 04 T-PLT-29 "Read access" lets be read with a permission, as the document
    states them: the contract the file routes are held to (the registry in code is held to the
    same table by ``tests/architecture/test_file_access.py``)."""
    lines = (REPOSITORY / "docs" / "04-DATA_MODEL.md").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(READ_ACCESS_HEADING))
    top = next(i for i in range(start, start + 6) if lines[i].strip() == READ_ACCESS_HEADER)
    found: list[DocumentedOwner] = []
    for line in lines[top + 2 :]:
        if not line.startswith("|"):
            break
        purpose, owner, read_by, entity = (
            cell.strip() for cell in line.strip().strip("|").split("|")
        )
        permissions = tuple(re.findall(r"`([a-z_]+\.[a-z_]+)`", read_by.split(";")[0]))
        if not owner.startswith("`") or not permissions:
            continue  # an uploader row, a rule of the owner's own, or a route
        table, _, column = owner.strip("`").partition(".")
        found.append(
            DocumentedOwner(FilePurpose(purpose.strip("`")), table, column, permissions, entity)
        )
    return found


STORED_PREVIEW_RULE = " for every entity the "


def documented_preview_owners() -> list[DocumentedOwner]:
    """The owners 04 T-PLT-29 "Read access" states by the rule of a stored preview (rev 1.300;
    §16.10 "Who reads a stored preview"): the permissions are the words of the rule — one of
    them, for every entity the subject is bound to."""
    lines = (REPOSITORY / "docs" / "04-DATA_MODEL.md").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(READ_ACCESS_HEADING))
    top = next(i for i in range(start, start + 6) if lines[i].strip() == READ_ACCESS_HEADER)
    found: list[DocumentedOwner] = []
    for line in lines[top + 2 :]:
        if not line.startswith("|"):
            break
        purpose, owner, read_by, entity = (
            cell.strip() for cell in line.strip().strip("|").split("|")
        )
        if not read_by.startswith("rule: ") or STORED_PREVIEW_RULE not in read_by:
            continue
        words = read_by.removeprefix("rule: ").split(STORED_PREVIEW_RULE)[0]
        table, _, column = owner.strip("`").partition(".")
        found.append(
            DocumentedOwner(
                FilePurpose(purpose.strip("`")),
                table,
                column,
                tuple(re.findall(r"[a-z_]+\.[a-z_]+", words)),
                entity,
            )
        )
    return found


def documented_need(cell: str, value: Any) -> str | tuple[uuid.UUID, ...]:
    """Whom the Entity cell lets read a row whose entity column holds ``value``: ``"tenant"`` —
    a holder of the permission at any scope; ``"all"`` — only a holder for all entities; or the
    entities the permission is needed for."""
    plain = cell.removesuffix(WITHOUT_ONE)
    if plain == "tenant":
        return "tenant"
    if plain == "all entities":
        return "all"
    if value is None:
        return "all" if cell.endswith(WITHOUT_ONE) else "tenant"
    ids = tuple(uuid.UUID(str(item)) for item in (value if isinstance(value, list) else [value]))
    return ids or "tenant"  # a list that names no entity concerns none


def test_r_111_9_every_owner_of_the_registry_is_read_through_the_file_routes(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The review's untested branches of rule 3 (ruling R-111 (9)): through ``/files`` six
    owners were exercised; the reconciliation source, the re-lock diff, the evidence pack, the
    impact simulations, the calculator result, the legacy database, the control exception list,
    the modification and adjustment previews and the import diff never were, so a wrong
    permission or entity column on one of those rows would have gone unseen. Every row of 04
    T-PLT-29 "Read access" that names permissions is read here through both file routes: by a
    holder of each permission for all entities, by a holder for the row's own entity, by no
    holder for another entity unless the row is tenant-level, and by nobody without the
    permission. The files are written as SYSTEM, as a job writes them: nobody uploaded them.

    Since 04 rev 1.300 (item MOD-PREVIEW-READ-SCOPE-1) the previews a modification and a manual
    adjustment retain are stated by a rule — the same permissions, for every entity the
    subject is bound to — and are no rows that name permissions. Thirteen permission rows
    remain; evidence packs require their audited download route. The two previews are read
    in a block of their own below, as this sweep read them."""
    admin = member(keyring, clock)
    tenant_id = admin.tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        named = insert_contract_rows(session, tenant_id).entity_id
        other = insert_contract_rows(session, tenant_id).entity_id
    variants: dict[str, list[dict[str, Any]]] = {
        "registry_version.impact_simulation_file_id": [{}, {"scope": "ENTITY", "entity_id": named}],
        "control_execution.exceptions_file_id": [{}, {"entity_id": named}],
        "import_upload.file_object_id": [
            {},
            {"named_entity_ids": [named]},
            {"named_entity_ids": []},
        ],
        "import_upload.diff_file_id": [{}, {"named_entity_ids": [named]}],
    }
    system = RequestContext(
        principal=system_principal(tenant_id, on_behalf_of_id=None),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-file-owners",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    roles: dict[str, str] = {}
    members = 0

    def holder(permission: str, entity_ids: tuple[uuid.UUID, ...] = ()) -> Actor:
        """A new member whose one role holds ``permission`` alone, for ``entity_ids`` or all."""
        nonlocal members
        if permission not in roles:
            roles[permission] = f"own_{len(roles)}"
            with tenant_session(_all_entities(tenant_id)) as session:
                insert_custom_role(
                    session, tenant_id=tenant_id, code=roles[permission], permissions=[permission]
                )
        members += 1
        return joined(app, tenant_id, f"holder{members}", roles[permission], entity_ids=entity_ids)

    def stored(owner: DocumentedOwner, marker: str) -> tuple[uuid.UUID, bytes]:
        name, media_type = SWEEP_UPLOADS.get(
            owner.purpose, ("file.bin", "application/octet-stream")
        )
        content = f"owner sweep, {marker}\n".encode()
        if owner.purpose is FilePurpose.IMPORT_SOURCE:
            content = fx.CSV + content
        elif owner.purpose is FilePurpose.LEGACY_DATABASE:
            content = fx.SQLITE + content
        with unit_of_work(system, clock=clock, keyring=keyring, files=app.state.file_store) as uow:
            row = store_file(
                uow,
                purpose=owner.purpose,
                stream=io.BytesIO(content),
                original_filename=name,
                media_type=media_type,
            )
            uow.commit()
        return uuid.UUID(str(row["id"])), content

    def owned(owner: DocumentedOwner, file_id: uuid.UUID, extra: Mapping[str, Any]) -> Any:
        """Insert a row of the owner's table that holds the file; the entity value it stores."""
        table = file_object.metadata.tables[f"erev.{owner.table}"]
        entity_table, _, entity_column = (
            owner.entity.removesuffix(WITHOUT_ONE).strip("`").partition(".")
        )
        with tenant_session(_all_entities(tenant_id)) as session:
            row = ROW_BUILDERS[owner.table](RowContext(tenant_id, admin.user_id), session)
            row = {**row, **extra, owner.column: file_id}
            session.execute(insert(table).values(**row))
            if not entity_column:
                return None
            if entity_table == owner.table:
                return session.execute(
                    select(table.c[entity_column]).where(table.c.id == row["id"])
                ).scalar_one()
            parent_name, link = PARENT_OF[owner.table]
            assert parent_name == entity_table, owner.ref
            parent = file_object.metadata.tables[f"erev.{parent_name}"]
            return session.execute(
                select(parent.c[entity_column]).where(parent.c.id == row[link])
            ).scalar_one()

    def readable(actor: Actor, file_id: uuid.UUID, content: bytes) -> bool:
        shown = read(app, f"{FILES}/{file_id}", actor)
        body = read(app, f"{FILES}/{file_id}/content", actor)
        return (shown.status_code, body.status_code, body.content) == (200, 200, content)

    def hidden(actor: Actor, file_id: uuid.UUID) -> bool:
        return all(
            (answer.status_code, slug(answer)) == (404, "not-found")
            for answer in (
                read(app, f"{FILES}/{file_id}", actor),
                read(app, f"{FILES}/{file_id}/content", actor),
            )
        )

    owners = documented_owners()
    assert len(owners) >= 13, [owner.ref for owner in owners]
    outsider = joined(app, tenant_id, "outsider")
    problems: list[str] = []
    for owner in owners:
        for number, extra in enumerate(variants.get(owner.ref, [{}])):
            clock.advance(timedelta(seconds=61))  # each owner's sign-ins in a window of their own
            case = f"{owner.ref}#{number}"
            file_id, content = stored(owner, case)
            try:
                value = owned(owner, file_id, extra)
            except Exception as error:  # noqa: BLE001 - every owner is reported, not the first
                problems.append(f"{case}: no owning row could be written: {error!r}"[:400])
                continue
            need = documented_need(owner.entity, value)
            for permission in owner.permissions:
                if not readable(holder(permission), file_id, content):
                    problems.append(f"{case}: {permission} for all entities does not read")
            first = owner.permissions[0]
            elsewhere = holder(first, (other,))
            if need == "tenant":
                if not readable(elsewhere, file_id, content):
                    problems.append(
                        f"{case}: tenant-level, yet {first} for one entity does not read"
                    )
            elif not hidden(elsewhere, file_id):
                problems.append(f"{case}: {first} for ANOTHER entity reads (need {need})")
            if isinstance(need, tuple) and not readable(holder(first, need), file_id, content):
                problems.append(f"{case}: {first} for the row's own entity does not read")
            if not hidden(outsider, file_id):
                problems.append(f"{case}: a member without a role reads")

    # The one owner with a rule of its own that no test reached: the pool a calculator run
    # names (04: "ssp.read for all entities, for the pool a run names in
    # parameters.pool_file_id").
    clock.advance(timedelta(seconds=61))
    pool = DocumentedOwner(FilePurpose.IMPORT_SOURCE, "ssp_calculator_run", "parameters", (), "-")
    pool_id, pool_content = stored(pool, "the pool of a calculator run")
    with tenant_session(_all_entities(tenant_id)) as session:
        run = ROW_BUILDERS["ssp_calculator_run"](RowContext(tenant_id, admin.user_id), session)
        run["parameters"] = {
            **run["parameters"],
            "source": "source_order_lines",
            "pool_file_id": str(pool_id),
        }
        session.execute(insert(ssp_calculator_run).values(**run))
    if not readable(holder("ssp.read"), pool_id, pool_content):
        problems.append("the pool: ssp.read for all entities does not read")
    for actor, who in (
        (holder("ssp.read", (other,)), "ssp.read for one entity"),
        (holder("contract.read"), "contract.read for all entities"),
        (outsider, "a member without a role"),
    ):
        if not hidden(actor, pool_id):
            problems.append(f"the pool: {who} reads")

    # The two owners 04 states by the rule of a stored preview (rev 1.300; §16.10 "Who reads a
    # stored preview"): the subject's read permission for EVERY entity the subject is bound to.
    # The row written here is of a contract alone in its group, so that is the row's own
    # entity — what the loop above held for both rows while they named permissions. A group
    # of two contracting entities is witnessed through the product's commands in
    # tests/domain/contracts/test_reader_independence.py.
    previews = documented_preview_owners()
    assert {(owner.ref, owner.permissions) for owner in previews} == {
        ("modification.impact_preview_file_id", ("contract.read",)),
        (
            "manual_adjustment.impact_preview_file_id",
            ("adjustment.approve", "adjustment.create", "contract.read", "report.run"),
        ),
    }
    own_entity = {"modification": "contracting_entity_id", "manual_adjustment": "entity_id"}
    for preview in previews:
        clock.advance(timedelta(seconds=61))
        case = f"{preview.ref} (the rule of a stored preview)"
        file_id, content = stored(preview, case)
        table = file_object.metadata.tables[f"erev.{preview.table}"]
        with tenant_session(_all_entities(tenant_id)) as session:
            row = ROW_BUILDERS[preview.table](RowContext(tenant_id, admin.user_id), session)
            session.execute(insert(table).values(**{**row, preview.column: file_id}))
        own = uuid.UUID(str(row[own_entity[preview.table]]))
        for permission in preview.permissions:
            if not readable(holder(permission), file_id, content):
                problems.append(f"{case}: {permission} for all entities does not read")
        first = preview.permissions[0]
        if not hidden(holder(first, (other,)), file_id):
            problems.append(f"{case}: {first} for ANOTHER entity reads")
        if not readable(holder(first, (own,)), file_id, content):
            problems.append(f"{case}: {first} for the row's own entity does not read")
        if not hidden(outsider, file_id):
            problems.append(f"{case}: a member without a role reads")
    assert not problems, "\n".join(problems)


def test_r_98_the_files_of_an_import_are_read_by_its_uploader_and_for_the_entities_it_names(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Supervisor rulings R-86 (f) and R-98; 04 T-PLT-29 Read access, rev 1.151. An upload states
    the entities its rows name since revision 0087 (``named_entity_ids``), and the import is
    read within them. Its source and its diff were read with the permission for ALL entities
    whatever the upload named, and then by every holder of ``import.upload`` for the named
    entities — a permission to bring data in, which reads nothing another member brought. They
    are read by the upload's own uploader and by a holder of ``contract.read`` or of
    ``import.approve`` for every entity of the list: any scope for a tenant-level upload, all
    entities while the list is not set. One witness per reader, each holding ONE permission."""
    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id).entity_id
        south = insert_contract_rows(session, tenant_id).entity_id
        for code, permission in (
            ("only_upload", "import.upload"),
            ("only_read", "contract.read"),
            ("only_approve", "import.approve"),
        ):
            insert_custom_role(session, tenant_id=tenant_id, code=code, permissions=[permission])
    uploader = joined(app, tenant_id, "uma", "only_upload", entity_ids=(north,))
    plain = joined(app, tenant_id, "pia", "only_upload")  # import.upload, for every entity
    reader = joined(app, tenant_id, "cora", "only_read", entity_ids=(north,))
    approver = joined(app, tenant_id, "ira", "only_approve", entity_ids=(north,))
    wide_reader = joined(app, tenant_id, "cleo", "only_read")
    wide_approver = joined(app, tenant_id, "ines", "only_approve")

    def imported(label: str, named: list[uuid.UUID] | None) -> tuple[str, str]:
        """An import Uma makes of a source she uploads, naming ``named``; (source, diff) ids.
        The diff is the validation job's file: nobody uploaded it."""
        content = f"customer,amount\n{label},1.00\n".encode()
        uploaded = upload(app, uploader, "IMPORT_SOURCE", f"{label}.csv", content)
        assert uploaded.status_code == 201, uploaded.text
        source_id = uploaded.json()["id"]
        diff = file_object_values(tenant_id, purpose=FilePurpose.IMPACT_PREVIEW)
        with tenant_session(_all_entities(tenant_id)) as session:
            session.execute(insert(file_object).values(**diff))
            insert_import_upload(
                session,
                tenant_id=tenant_id,
                file_object_id=uuid.UUID(source_id),
                diff_file_id=diff["id"],
                named_entity_ids=named,
                created_by=uploader.member.user_id,
                created_by_kind=PrincipalKind.USER.value,
            )
        return source_id, str(diff["id"])

    def shown(file_id: str, *readers: Actor) -> None:
        for reader in readers:
            metadata = read(app, f"{FILES}/{file_id}", reader)
            assert metadata.status_code == 200, (reader.member.email, metadata.text)
            assert metadata.json()["id"] == file_id

    # 1. An import of North: its readers are the reader of North's contracts and the approver of
    # North's imports. Pia holds import.upload for every entity and did not make this upload:
    # she reads neither file.
    source, diff = imported("north-only", [north])
    for file_id in (source, diff):
        assert_hidden(app, file_id, plain)
        shown(file_id, uploader, reader, approver, wide_reader, wide_approver)
    assert read(app, f"{FILES}/{source}/content", reader).status_code == 200
    # 2. An import of North and South: not the holders for North alone. Uma's own grant is for
    # North too — she reads the upload because it is hers.
    source, diff = imported("north-and-south", [north, south])
    for file_id in (source, diff):
        shown(file_id, uploader, wide_reader, wide_approver)
        assert_hidden(app, file_id, reader, approver, plain)
    # 3. A tenant-level upload (it names no entity): every reader and approver, at any scope.
    source, diff = imported("tenant-level", [])
    for file_id in (source, diff):
        shown(file_id, uploader, reader, approver, wide_reader, wide_approver)
        assert_hidden(app, file_id, plain)
    # 4. An upload whose entities are not resolved: the all-entities holders only (R-28; R-98
    # (2)), and its uploader.
    source, diff = imported("unresolved", None)
    for file_id in (source, diff):
        shown(file_id, uploader, wide_reader, wide_approver)
        assert_hidden(app, file_id, reader, approver, plain)


def test_att_requester_1_the_requester_attaches_to_their_own_pending_request(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item ATT-REQUESTER-1 (supervisor ruling R-100 (b)); 04 T-PLT-30 Subjects, rev 1.151. The
    requester of a period reopen — a Revenue Reviewer or a Controller — holds none of the eleven
    permissions an attachment to an approval request needs, so the evidence PRD J-14.1 has them
    attach could be neither uploaded nor attached. Whoever submitted a request attaches to it
    while it is ``PENDING``, whatever they hold; nobody else gains anything, and a request that
    is decided gives its requester nothing."""
    tenant_id = member(keyring, clock).tenant_id
    requester = joined(app, tenant_id, "rhea", "revenue_reviewer")  # period.reopen_request
    peer = joined(app, tenant_id, "ravi", "revenue_reviewer")  # the same role, not the requester

    def reopen_request(preparer: Actor, **values: Any) -> uuid.UUID:
        """A PERIOD_REOPEN request ``preparer`` submitted, read by the holders of
        ``period.reopen_approve`` (both of them) through its step."""
        with tenant_session(_all_entities(tenant_id)) as session:
            request_id = insert_approval_request(
                session,
                tenant_id=tenant_id,
                preparer_id=preparer.member.user_id,
                subject_type=ApprovalSubjectType.PERIOD_REOPEN.value,
                **values,
            )
            insert_approval_step(
                session,
                tenant_id=tenant_id,
                approval_request_id=request_id,
                required_permission="period.reopen_approve",
            )
        return request_id

    def refused(response: HttpResponse) -> None:
        assert response.status_code == 403, response.text
        assert slug(response) == "forbidden", response.text

    hers = reopen_request(requester)
    evidence = fx.PDF + b"% job cost report\n"
    # Ravi has no request of his own: he uploads no attachment.
    refused(upload(app, peer, "ATTACHMENT", "job-cost.pdf", fx.PDF + b"% ravi\n"))
    # Rhea uploads the evidence, attaches it to her request and reads it back.
    uploaded = upload(app, requester, "ATTACHMENT", "job-cost.pdf", evidence)
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    linked = attach_to(app, requester, file_id, "approval_request", hers)
    assert linked.status_code == 201, linked.text
    assert attached(app, requester, "approval_request", hers) == [file_id]
    assert read(app, f"{FILES}/{file_id}/content", requester).content == evidence

    # What she attached she takes back while the request is pending (R-100 (b)): a second
    # file, attached by mistake and voided.
    draft = upload(app, requester, "ATTACHMENT", "draft.pdf", fx.PDF + b"% draft\n")
    mistaken = attach_to(app, requester, draft.json()["id"], "approval_request", hers)
    assert mistaken.status_code == 201, mistaken.text
    taken_back = void(app, requester, mistaken.json()["id"])
    assert taken_back.status_code == 200, taken_back.text
    assert taken_back.json()["voided_at"] is not None
    # A voided attachment stays listed, with its void: the request shows both files from here.
    both = sorted([file_id, draft.json()["id"]])

    # Ravi reads the request and its evidence — he may decide it — and attaches nothing to it:
    # the file is one he reads, the request is one he sees, the permission is what he lacks.
    # Her evidence is not his to void either: to him that attachment is not there.
    assert sorted(attached(app, peer, "approval_request", hers)) == both
    assert read(app, f"{FILES}/{file_id}/content", peer).content == evidence
    refused(attach_to(app, peer, file_id, "approval_request", hers))
    assert void(app, peer, linked.json()["id"]).status_code == 404

    # The rule is the request's own: with a pending request of his own Ravi uploads and attaches
    # to HIS request, still not to hers, and Rhea not to his.
    his = reopen_request(peer)
    own_file = upload(app, peer, "ATTACHMENT", "ravi-memo.pdf", fx.PDF + b"% ravi\n")
    assert own_file.status_code == 201, own_file.text
    assert attach_to(app, peer, own_file.json()["id"], "approval_request", his).status_code == 201
    refused(attach_to(app, peer, file_id, "approval_request", hers))
    refused(attach_to(app, requester, file_id, "approval_request", his))
    assert sorted(attached(app, requester, "approval_request", hers)) == both

    # A request that is no longer pending gives its requester nothing: decided here, and the
    # same for one that was rejected or withdrawn. What she attached stays with the request.
    with tenant_session(_all_entities(tenant_id)) as session:
        session.execute(
            update(approval_request)
            .where(approval_request.c.id == hers)
            .values(status=ApprovalRequestStatus.APPROVED.value, decided_at=clock.now())
        )
    refused(attach_to(app, requester, file_id, "approval_request", hers))
    for status in (ApprovalRequestStatus.REJECTED, ApprovalRequestStatus.WITHDRAWN):
        refused(
            attach_to(
                app,
                requester,
                file_id,
                "approval_request",
                reopen_request(requester, status=status),
            )
        )
    refused(upload(app, requester, "ATTACHMENT", "late.pdf", fx.PDF + b"% late\n"))
    # Nor does she take her evidence back once the request is decided: the rule was the
    # pending request's, and she holds no permission of the cell.
    refused(void(app, requester, linked.json()["id"]))
    assert sorted(attached(app, requester, "approval_request", hers)) == both


def test_att_multi_entity_1_attaching_to_a_request_of_several_entities_needs_all_of_them(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item ATT-MULTI-ENTITY-1 (from lane SECFIX-APR's report; the supervisor's message of
    2026-10-01); 04 T-PLT-30 Subjects, rev 1.189. An approval request is bound to the legal
    entities of its subject: one (``entity_id``), several (``entity_ids``) or every one
    (``is_all_entities``; T-PLT-17 rev 1.104). The attach rule read ``entity_id`` alone, so a
    request of several entities — which names none in that column — asked the "Attach with"
    permission at tenant level: a holder of it for ONE entity, who sees the request through a
    step permission for that entity, attached to a request of two. The permission is needed for
    every entity the request names, as a decision is. The requester still attaches whatever they
    hold (ATT-REQUESTER-1), and what is attached is read by the readers of the request's content
    — who covers every entity it names (item APR-CONTENT-SCOPE-1; supervisor ruling R-121 (c); 04
    §16.10 rev 1.208)."""
    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id).entity_id
        south = insert_contract_rows(session, tenant_id).entity_id
        # Sees a request through contract.approve, attaches with exception.resolve.
        insert_custom_role(
            session,
            tenant_id=tenant_id,
            code="deal_desk",
            permissions=["contract.approve", "exception.resolve"],
        )
    nils = joined(app, tenant_id, "nils", "deal_desk", entity_ids=(north,))
    bea = joined(app, tenant_id, "bea", "deal_desk", entity_ids=(north, south))
    rhea = joined(app, tenant_id, "rhea", "viewer")  # the requester: holds no attach permission

    def request(**entities: Any) -> uuid.UUID:
        with tenant_session(_all_entities(tenant_id)) as session:
            request_id = insert_approval_request(
                session,
                tenant_id=tenant_id,
                preparer_id=rhea.member.user_id,
                subject_type=ApprovalSubjectType.COMBINATION_GROUP.value,
                **entities,
            )
            insert_approval_step(
                session,
                tenant_id=tenant_id,
                approval_request_id=request_id,
                required_permission="contract.approve",
            )
        return request_id

    def uploaded(actor: Actor, name: str) -> str:
        created = upload(app, actor, "ATTACHMENT", name, fx.PDF + f"% {name}\n".encode())
        assert created.status_code == 201, created.text
        return str(created.json()["id"])

    several = request(entity_ids=[north, south])
    single = request(entity_id=north)
    side_letter = uploaded(nils, "side-letter.pdf")

    # Nils sees both requests, and attaches to the one of his entity (positive control) ...
    assert attached(app, nils, "approval_request", several) == []
    assert attach_to(app, nils, side_letter, "approval_request", single).status_code == 201
    # ... and not to the request of two entities: his permission covers one of them.
    refused = attach_to(app, nils, side_letter, "approval_request", several)
    assert refused.status_code == 404, refused.text
    assert slug(refused) == "not-found"
    assert attached(app, bea, "approval_request", several) == []

    # Bea holds the permission for both; the requester attaches whatever she holds.
    memo = uploaded(bea, "memo.pdf")
    assert attach_to(app, bea, memo, "approval_request", several).status_code == 201
    evidence = uploaded(rhea, "evidence.pdf")
    assert attach_to(app, rhea, evidence, "approval_request", several).status_code == 201
    # Reading is for the readers of the request's content (APR-CONTENT-SCOPE-1): Bea, who covers
    # both entities and holds the step's permission for both, reads what the request of two
    # carries; Nils, who covers one of them, is shown none of it.
    assert sorted(attached(app, bea, "approval_request", several)) == sorted([memo, evidence])
    assert attached(app, nils, "approval_request", several) == []


def test_req_plt_012_attachments_follow_the_entity_of_their_subject(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """R-48 (c) with R-28: a file attached to a record is read, and a record attached to, with
    the record's permission for the record's legal entity. The check was the subject TYPE alone,
    so a member restricted to one entity read and attached across entities, and any file id could
    be attached to a record of one's own and read through it."""
    owner = member(keyring, clock)
    tenant_id = owner.tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id)
        south = insert_contract_rows(session, tenant_id)
    wide = joined(app, tenant_id, "lena", "revenue_accountant")
    narrow = joined(app, tenant_id, "nils", "revenue_accountant", entity_ids=(north.entity_id,))
    auditor = joined(app, tenant_id, "ava", "auditor")  # contract.read and audit.read, everywhere

    south_file = upload(app, wide, "ATTACHMENT", "south-msa.pdf", fx.PDF + b"% south\n")
    assert south_file.status_code == 201, south_file.text
    south_id = south_file.json()["id"]
    assert_hidden(app, south_id, auditor)  # unattached: only its uploader reads it
    assert attach_to(app, wide, south_id, "contract", south.contract_id).status_code == 201
    assert read(app, f"{FILES}/{south_id}/content", auditor).status_code == 200

    # The south contract is outside Nils's entity scope: its attachments and their files are not
    # there for him, and he attaches nothing to it — answered as for a contract that is not.
    assert attached(app, narrow, "contract", south.contract_id) == []
    assert_hidden(app, south_id, narrow)
    mine = upload(app, narrow, "ATTACHMENT", "north-order.pdf", fx.PDF + b"% north\n")
    north_id = mine.json()["id"]
    outside = attach_to(app, narrow, north_id, "contract", south.contract_id)
    unknown = attach_to(app, narrow, north_id, "contract", uuid.uuid4())
    assert (outside.status_code, slug(outside)) == (404, "not-found"), outside.text
    assert {**outside.json(), "instance": None} == {**unknown.json(), "instance": None}
    # A file he may not read does not become readable by attaching it to a record of his own:
    # its id is answered like one that names no file.
    smuggled = attach_to(app, narrow, south_id, "contract", north.contract_id)
    nameless = attach_to(app, narrow, str(uuid.uuid4()), "contract", north.contract_id)
    assert (smuggled.status_code, slug(smuggled)) == (422, "validation-failed"), smuggled.text
    assert smuggled.json()["errors"] == nameless.json()["errors"]
    assert attached(app, wide, "contract", north.contract_id) == []
    assert_hidden(app, south_id, narrow)

    # Positive controls: inside his entity he attaches and reads, and so do the contract's other
    # readers — through the contract, not as uploaders.
    assert attach_to(app, narrow, north_id, "contract", north.contract_id).status_code == 201
    for reader in (narrow, wide, auditor):
        assert attached(app, reader, "contract", north.contract_id) == [north_id]
        shown = read(app, f"{FILES}/{north_id}/content", reader)
        assert shown.status_code == 200, shown.text
        assert shown.content == fx.PDF + b"% north\n"

    # Uploading the same bytes makes him an uploader of the stored row (content identity): what
    # he holds himself he may attach to his own record.
    again = upload(app, narrow, "ATTACHMENT", "msa-copy.pdf", fx.PDF + b"% south\n")
    assert (again.status_code, again.json()["id"]) == (201, south_id)
    assert read(app, f"{FILES}/{south_id}/content", narrow).content == fx.PDF + b"% south\n"
    assert attach_to(app, narrow, south_id, "contract", north.contract_id).status_code == 201
    assert attached(app, narrow, "contract", south.contract_id) == []  # the scope stands


def test_r_111_5_an_attachment_is_voided_by_the_person_who_attached_it(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 5 (ruling R-111 (5)); 04
    T-PLT-30 Subjects, rev 1.189. ``POST /attachments/{id}/void`` answered 404 for an id that
    names nothing and 403 for an attachment the caller could not void — because they lacked the
    subject's write permission, or held it and had not attached the file — so the answer told an
    attachment from none. An attachment the caller did not attach answers 404, word for word as
    an unknown id; the entity rule of attaching holds for the void of every subject type, as it
    did for a manual adjustment only (BUILD_SPEC CLO-12)."""
    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id)
        south = insert_contract_rows(session, tenant_id)
    lena = joined(app, tenant_id, "lena", "revenue_accountant")
    peer = joined(app, tenant_id, "pete", "revenue_accountant")  # may attach; did not attach this
    auditor = joined(app, tenant_id, "ava", "auditor")  # reads the contract, attaches nothing
    narrow = joined(app, tenant_id, "nils", "revenue_accountant", entity_ids=(north.entity_id,))

    def attachment_of(actor: Actor, name: str) -> str:
        uploaded = upload(app, actor, "ATTACHMENT", name, fx.PDF + name.encode())
        assert uploaded.status_code == 201, uploaded.text
        linked = attach_to(app, actor, uploaded.json()["id"], "contract", north.contract_id)
        assert linked.status_code == 201, linked.text
        return str(linked.json()["id"])

    def voided_at(attachment_id: str) -> Any:
        listed = read(
            app, ATTACHMENTS, lena, subject_type="contract", subject_id=str(north.contract_id)
        )
        (item,) = [item for item in listed.json()["items"] if item["id"] == attachment_id]
        return item["voided_at"]

    hers = attachment_of(lena, "msa.pdf")
    unknown = void(app, peer, str(uuid.uuid4()))
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    for other in (peer, auditor):
        refused = void(app, other, hers)
        assert refused.status_code == 404, (other.member.email, refused.text)
        assert {**refused.json(), "instance": None} == {**unknown.json(), "instance": None}
    assert voided_at(hers) is None
    # The refused attempts are on record, each as a DENIED event of the void.
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        denied = session.execute(
            select(audit_event.c.actor_id, audit_event.c.detail)
            .where(
                audit_event.c.action == "file_attachment.void",
                audit_event.c.outcome == "DENIED",
                audit_event.c.object_id == uuid.UUID(hers),
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    assert [(actor_id, detail["reason"]) for actor_id, detail in denied] == [
        (peer.member.user_id, "not-uploader"),
        (auditor.member.user_id, "not-uploader"),
    ]

    # Her own attachment, once its subject is outside the entity scope of her permission, is
    # answered as attaching to that subject is: 404. Without any permission of the cell: 403.
    his = attachment_of(narrow, "north-order.pdf")
    with tenant_session(_all_entities(tenant_id)) as session:
        revoke_role_assignments(
            session,
            tenant_id=tenant_id,
            membership_id=narrow.member.membership_id,
            at=clock.now(),
        )
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=narrow.member.membership_id,
            role_code="revenue_accountant",
            entity_ids=(south.entity_id,),
        )
    outside = void(app, narrow, his)
    assert outside.status_code == 404, outside.text
    assert {**outside.json(), "instance": None} == {**unknown.json(), "instance": None}
    with tenant_session(_all_entities(tenant_id)) as session:
        revoke_role_assignments(
            session,
            tenant_id=tenant_id,
            membership_id=narrow.member.membership_id,
            at=clock.now(),
        )
    without = void(app, narrow, his)
    assert (without.status_code, slug(without)) == (403, "forbidden"), without.text
    assert voided_at(his) is None

    # Positive control: the person who attached the file voids it.
    done = void(app, lena, hers)
    assert done.status_code == 200, done.text
    assert voided_at(hers) is not None


# The subject types whose attachments the Viewer (contract.read, ssp.read, config.read,
# report.run) does not read: an SoD exception is read with access administration permissions, an
# approval request by its readers.
VIEWER_BLIND: frozenset[str] = frozenset({"sod_exception", "approval_request"})


def test_att_subjects_1_every_documented_subject_type_holds_attachments(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item ATT-SUBJECTS-1 (rulings R-47 (e), R-48 (c)): 04 T-PLT-30 names twelve subject types
    and the code admitted two, so an estimate version or a judgement record could not carry its
    evidence (PRD J-07.2; REQ-POL-008). Every type attaches, and its attachments are read with
    the type's read permission (04 T-PLT-30 "Subjects")."""
    owner = member(keyring, clock)
    tenant_id = owner.tenant_id
    # The three roles that together hold a write permission of every subject type.
    writer = joined(app, tenant_id, "wren", "revenue_accountant", "ssp_analyst", "tenant_admin")
    viewer = joined(app, tenant_id, "vera", "viewer")
    subjects: dict[str, uuid.UUID] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        ctx = RowContext(tenant_id, owner.user_id)
        for subject_type in ATTACHMENT_SUBJECTS:
            row = insert_probe_row(session, subject_type, ctx)
            subjects[subject_type] = uuid.UUID(str(row["id"]))
        # A request is read by the holders of its step's permission (``access.approve``: Wren).
        insert_approval_step(
            session, tenant_id=tenant_id, approval_request_id=subjects["approval_request"]
        )
    assert len(subjects) == 12

    for subject_type, subject_id in subjects.items():
        content = fx.CSV + f"{subject_type},1.00\n".encode()
        uploaded = upload(app, writer, "ATTACHMENT", f"{subject_type}.csv", content)
        assert uploaded.status_code == 201, (subject_type, uploaded.text)
        file_id = uploaded.json()["id"]
        linked = attach_to(app, writer, file_id, subject_type, subject_id)
        assert linked.status_code == 201, (subject_type, linked.text)
        assert attached(app, writer, subject_type, subject_id) == [file_id], subject_type

        listed = read(
            app, ATTACHMENTS, viewer, subject_type=subject_type, subject_id=str(subject_id)
        )
        if subject_type not in VIEWER_BLIND:
            assert [item["file_object_id"] for item in listed.json()["items"]] == [file_id]
            shown = read(app, f"{FILES}/{file_id}/content", viewer)
            assert (shown.status_code, shown.content) == (200, content), subject_type
            continue
        if subject_type == "approval_request":
            # No permission names its readers: a request she does not see lists nothing.
            assert (listed.status_code, listed.json()["items"]) == (200, []), listed.text
        else:
            assert (listed.status_code, slug(listed)) == (403, "forbidden"), subject_type
        assert_hidden(app, file_id, viewer)


def test_krn_idem_04_large_response_stored_as_file(app: FastAPI, accountant: Actor) -> None:
    key = "large-response-0001"
    headers = {**cookie_headers(accountant.token, accountant.csrf_token), "Idempotency-Key": key}
    first = call(app, "POST", LARGE, headers=headers)
    assert first.status_code == 200, first.text
    replayed = call(app, "POST", LARGE, headers=headers)
    assert replayed.status_code == 200, replayed.text
    assert replayed.headers["idempotent-replay"] == "true"
    assert replayed.content == first.content
    assert replayed.json() == {"blob": LARGE_BLOB}
    with tenant_session(_all_entities(accountant.member.tenant_id), read_only=True) as session:
        record = (
            session.execute(
                select(idempotency_record).where(idempotency_record.c.idempotency_key == key)
            )
            .mappings()
            .one()
        )
        stored = (
            session.execute(
                select(file_object).where(file_object.c.id == record["response_file_id"])
            )
            .mappings()
            .one()
        )
    assert record["response_body"] is None
    assert (stored["purpose"], stored["media_type"], stored["size_bytes"]) == (
        "REPORT_OUTPUT",
        "application/json",
        len(first.content),
    )


@pytest.mark.parametrize("entity_bound", [False, True])
def test_evidence_pack_files_require_the_audited_pack_download_route(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, entity_bound: bool
) -> None:
    """Even an all-entity Auditor cannot bypass pack source checks/audit via /files."""
    admin = member(keyring, clock)
    tenant_id = admin.tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        entity_id = insert_contract_rows(session, tenant_id).entity_id
    auditor = joined(app, tenant_id, "pack-auditor", "auditor")
    scoped = joined(app, tenant_id, "pack-scoped", "auditor", entity_ids=(entity_id,))
    system = RequestContext(
        principal=system_principal(tenant_id, on_behalf_of_id=None),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-pack-file-route",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(system, clock=clock, keyring=keyring, files=app.state.file_store) as uow:
        stored = store_file(
            uow,
            purpose=FilePurpose.EVIDENCE_PACK,
            stream=io.BytesIO(b"private retained pack fixture"),
            original_filename="evidence.zip",
            media_type="application/zip",
        )
        file_id = stored["id"]
        uow.session.execute(
            insert(evidence_pack).values(
                **evidence_pack_values(
                    tenant_id, entity_id=entity_id if entity_bound else None, file_id=file_id
                )
            )
        )
        uow.commit()
    assert_hidden(app, str(file_id), auditor, scoped)
    # Reserving the read route must preserve the entity binding used by shred protection.
    assert referencing_scopes(tenant_id, file_id) == [
        (False, (entity_id,)) if entity_bound else (True, ())
    ]
