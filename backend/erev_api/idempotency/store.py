"""Idempotency store KRN-IDEM (docs/dev-guide.md §5.7; 04 T-PLT-28, API-C-04; 05 TXN-06;
REQ-PLT-026).

``begin`` records a command's ``Idempotency-Key`` as ``IN_PROGRESS`` in a committed transaction of
its own, before the command transaction starts (TXN-06). A repeat of a completed command with the
same request returns the stored response, a different request 422 ``idempotency-key-reused``, and a
repeat while the first attempt runs 409 ``idempotency-in-progress`` (DG-KRN-IDEM-02). ``complete``
stores the first response inside the command transaction; ``abandon`` deletes the ``IN_PROGRESS``
record in its own transaction when the response is not kept (DG-KRN-IDEM-03).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Final, cast
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import ColumnElement, CursorResult, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import file_object, idempotency_record
from erev_api.files.store import FileStore
from erev_api.problems import Problem

# T-PLT-28: expires_at = created_at + 7 days.
RETENTION: Final = timedelta(days=7)
# 05 TXN-06: an attempt still IN_PROGRESS after this long is treated as a new attempt.
STALE_AFTER: Final = timedelta(minutes=10)
IN_PROGRESS: Final = "IN_PROGRESS"
COMPLETED: Final = "COMPLETED"
JSON_MEDIA_TYPE: Final = "application/json"
# DG-KRN-IDEM-04: larger response bodies are stored as files of purpose REPORT_OUTPUT (BS1-D-28).
RESPONSE_BODY_LIMIT_BYTES: Final = 1024 * 1024
# PRD ERR-06 and ERR-40.
KEY_REUSED_DETAIL: Final = "This Idempotency-Key was already used with a different request body."
IN_PROGRESS_DETAIL: Final = (
    "The first request with this Idempotency-Key is still being processed. "
    "Retry after it completes."
)
_PATH_PARAMETER: Final = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::[A-Za-z_]+)?\}")


@dataclass(frozen=True, slots=True)
class Started:
    record_key: tuple[UUID, UUID, str]  # (tenant_id, principal_id, idempotency_key)
    request_sha256: str


@dataclass(frozen=True, slots=True)
class Replay:
    status: int
    headers: Mapping[str, str]
    body: Any


def _reject_constant(name: str) -> Any:
    raise ValueError(f"JSON constant {name} is not a number")


def _body_value(body: bytes, content_type: str) -> Any:
    """The parsed JSON of an ``application/json`` body, else the SHA-256 of the raw bytes.

    Numbers parse as ``Decimal``, because canonical hashing rejects floats (DG-KRN-CAN-03).
    """
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type == JSON_MEDIA_TYPE and body:
        try:
            return json.loads(body, parse_float=Decimal, parse_constant=_reject_constant)
        except ValueError:
            pass
    return hashlib.sha256(body).hexdigest()


def request_sha256(
    *,
    method: str,
    route_template: str,
    path_params: Mapping[str, str],
    query: Mapping[str, Sequence[str]],
    body: bytes,
    content_type: str,
    form: Mapping[str, Sequence[Any]] | None = None,
) -> str:
    """``sha256_hex({method, route, path_params, query, body})`` of DG-KRN-IDEM-02; the canonical
    encoding sorts the query parameter names.

    A multipart body hashes as ``{"form": form}``: its field values and, per file, the name, type
    and SHA-256, so a retry with another multipart boundary is the same request (SPEC-Q-159).
    """
    return sha256_hex(
        {
            "method": method.upper(),
            "route": route_template,
            "path_params": dict(path_params),
            "query": {name: list(values) for name, values in query.items()},
            "body": {"form": dict(form)} if form is not None else _body_value(body, content_type),
        }
    )


def response_bytes(body: Any) -> bytes:
    """The body as ``JSONResponse`` renders it; its length decides DG-KRN-IDEM-04 file storage."""
    return json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _render_path(route_template: str, path_params: Mapping[str, str]) -> str:
    """T-PLT-28 ``path``: the route template with its path parameters filled in."""
    return _PATH_PARAMETER.sub(
        lambda match: path_params.get(match.group(1), match.group(0)), route_template
    )


def _key_clause(record_key: tuple[UUID, UUID, str]) -> tuple[ColumnElement[bool], ...]:
    tenant_id, principal_id, key = record_key
    return (
        idempotency_record.c.tenant_id == tenant_id,
        idempotency_record.c.principal_id == principal_id,
        idempotency_record.c.idempotency_key == key,
    )


def _attempt_clause(started: Started) -> tuple[ColumnElement[bool], ...]:
    return (
        *_key_clause(started.record_key),
        idempotency_record.c.state == IN_PROGRESS,
        idempotency_record.c.request_sha256 == started.request_sha256,
    )


def begin(
    ctx: RequestContext,
    *,
    method: str,
    route_template: str,
    path_params: Mapping[str, str],
    query: Mapping[str, Sequence[str]],
    body: bytes,
    content_type: str,
    form: Mapping[str, Sequence[Any]] | None = None,
    files: FileStore | None = None,
) -> Started | Replay:
    """Start an attempt, or answer a repeat (DG-KRN-IDEM-02; TXN-06).

    An expired record not yet removed by retention, and an ``IN_PROGRESS`` record at least
    ``STALE_AFTER`` old with the same request, are taken over as a new attempt. A stored body kept
    as a file replays its bytes, read through ``files`` (DG-KRN-IDEM-04).
    """
    principal = ctx.principal
    key = ctx.idempotency_key
    if principal.id is None or key is None:
        raise ValueError(
            "an idempotent command needs an acting principal id and an Idempotency-Key"
        )
    started = Started(
        record_key=(principal.tenant_id, principal.id, key),
        request_sha256=request_sha256(
            method=method,
            route_template=route_template,
            path_params=path_params,
            query=query,
            body=body,
            content_type=content_type,
            form=form,
        ),
    )
    attempt: dict[str, Any] = {
        "principal_kind": principal.kind.value,
        "method": method.upper(),
        "path": _render_path(route_template, path_params),
        "request_sha256": started.request_sha256,
        "state": IN_PROGRESS,
        "created_at": ctx.now,
        "expires_at": ctx.now + RETENTION,
    }
    with tenant_session(principal.db_context) as session:
        inserted = session.execute(
            insert(idempotency_record)
            .values(
                tenant_id=principal.tenant_id,
                principal_id=principal.id,
                idempotency_key=key,
                **attempt,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "principal_id", "idempotency_key"])
            .returning(idempotency_record.c.state)
        ).first()
        if inserted is not None:
            return started
        record = (
            session.execute(
                select(
                    idempotency_record.c.state,
                    idempotency_record.c.request_sha256,
                    idempotency_record.c.created_at,
                    idempotency_record.c.expires_at,
                    idempotency_record.c.response_status,
                    idempotency_record.c.response_headers,
                    idempotency_record.c.response_body,
                    idempotency_record.c.response_file_id,
                )
                .where(*_key_clause(started.record_key))
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if record["expires_at"] > ctx.now:
            if record["request_sha256"] != started.request_sha256:
                raise Problem("idempotency-key-reused", KEY_REUSED_DETAIL)
            if record["state"] == COMPLETED:
                headers = record["response_headers"] or {}
                file_id = record["response_file_id"]
                return Replay(
                    status=int(record["response_status"]),
                    headers={str(name): str(value) for name, value in headers.items()},
                    body=record["response_body"]
                    if file_id is None
                    else _file_body(session, file_id, files),
                )
            if record["created_at"] > ctx.now - STALE_AFTER:
                raise Problem("idempotency-in-progress", IN_PROGRESS_DETAIL)
        session.execute(
            update(idempotency_record)
            .where(*_key_clause(started.record_key))
            .values(
                **attempt,
                response_status=None,
                response_headers=None,
                response_body=None,
                response_file_id=None,
                completed_at=None,
            )
        )
    return started


def _file_body(session: Session, file_id: UUID, files: FileStore | None) -> bytes:
    if files is None:
        raise RuntimeError("replaying a response stored as a file needs the file store")
    key = session.execute(
        select(file_object.c.storage_key).where(file_object.c.id == file_id)
    ).scalar_one()
    with files.open(str(key)) as stored:
        return stored.read()


def complete(
    session: Session,
    started: Started,
    *,
    status: int,
    headers: Mapping[str, str],
    body: Any,
    store_body: Callable[[bytes], UUID] | None = None,
) -> None:
    """Store the first response in the caller's transaction (DG-KRN-IDEM-03; TXN-06).

    ``body`` is the body a replay returns. It may differ from the body the first response carried:
    a one-time secret is stored as null (D-80). A body above ``RESPONSE_BODY_LIMIT_BYTES`` is
    written through ``store_body``, which returns the file id kept as ``response_file_id``
    (DG-KRN-IDEM-04). Raises ``RuntimeError`` when the attempt no longer holds the record, so the
    command rolls back.
    """
    stored: dict[str, Any] = {"response_body": body, "response_file_id": None}
    if body is not None:
        encoded = response_bytes(body)
        if len(encoded) > RESPONSE_BODY_LIMIT_BYTES:
            if store_body is None:
                raise RuntimeError("a response body above 1 MiB needs store_body")
            stored = {"response_body": None, "response_file_id": store_body(encoded)}
    result = session.execute(
        update(idempotency_record)
        .where(*_attempt_clause(started))
        .values(
            state=COMPLETED,
            response_status=status,
            response_headers=dict(headers),
            completed_at=func.now(),
            **stored,
        )
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        raise RuntimeError("the idempotency record is no longer held by this attempt")


def abandon(ctx: RequestContext, started: Started) -> None:
    """Delete the attempt's ``IN_PROGRESS`` record in a transaction of its own (DG-KRN-IDEM-03)."""
    with tenant_session(ctx.principal.db_context) as session:
        session.execute(delete(idempotency_record).where(*_attempt_clause(started)))
