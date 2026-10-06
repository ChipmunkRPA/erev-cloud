"""Route helpers (docs/dev-guide.md §6.4 DG-API-05; §5.3 DG-KRN-AUTH-03; §5.7 KRN-IDEM; §6.1
DG-CMD-08, DG-CMD-12; 04 API-C-01, API-C-03, API-C-04, API-C-08).

``require``, ``require_authenticated``, ``require_operator`` and ``command`` join this module with
the authentication and idempotency kernels. ``command(permission, precondition=…)`` guards a tenant
command: the permission, the ``Idempotency-Key``, the ``If-Match`` precondition and the
``idempotency_record`` protocol. ``run_command`` runs the handler in a unit of work and stores the
first response. ``command()`` without a permission serves the session commands, which act before a
tenant is chosen and so validate the key only (SPEC-Q-122). ``GuardedRoute`` is the route class of
every resource router and of the application router: it records the permission of a ``require``
guard as ``openapi_extra["x-erev-permission"]``.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Any, Final, Literal, overload
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile

from erev_api.auth import sessions
from erev_api.auth.dependencies import (
    PERMISSION_EXTENSION,
    declared_permissions,
    refuse_operator_command,
    require,
    require_all_entities,
    require_authenticated,
    session_questions,
)
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.clock import Clock, get_clock
from erev_api.config import LOOPBACK_ORIGIN_HOSTS, Settings
from erev_api.db.session import tenant_session
from erev_api.enums import FilePurpose, TenantStatus
from erev_api.files.store import FileStore, store_file
from erev_api.idempotency import store
from erev_api.idempotency.store import Replay, Started
from erev_api.logging import get_logger
from erev_api.problems import (
    INSTANCE_BASE,
    MEDIA_TYPE,
    PROBLEMS,
    Problem,
    ProblemError,
    from_db_error,
)
from erev_api.schemas.common import ProblemOut
from erev_api.uow import UnitOfWork, unit_of_work

# Every resource router carries the full prefix, so a matched route's path is its template.
API_PREFIX: Final = "/api/v1"
# The API-C-01 unauthenticated routes built so far; DG-ARC-04 accepts exactly these unguarded.
PUBLIC_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/healthz",
        "/api/v1/readyz",
        "/api/v1/openapi.json",
        "/api/v1/session",
        "/api/v1/session/login",
        "/api/v1/session/accept-invitation",
        "/api/v1/session/invitations/lookup",
        "/api/v1/session/password-reset",
        "/api/v1/session/password-reset/confirm",
        "/api/v1/session/oidc/{provider}/start",
        "/api/v1/session/oidc/{provider}/callback",
        "/api/v1/oauth/token",
        # 05 ADP-01: the webhook receiver is signature-verified, not session-authenticated.
        "/api/v1/webhooks/{adapter}/{connection_id}",
        # API-R-53: guarded by the EREV_METRICS_TOKEN bearer inside the handler (SOP-4).
        "/metrics",
    }
)
IDEMPOTENCY_KEY_HEADER: Final = "Idempotency-Key"
IDEMPOTENCY_KEY_LENGTH: Final = range(8, 256)
# PRD ERR-05.
IDEMPOTENCY_KEY_DETAIL: Final = "1 field needs attention."
IDEMPOTENCY_KEY_MESSAGE: Final = "Send an Idempotency-Key header with every command."
REPLAY_HEADER: Final = "Idempotent-Replay"
MULTIPART_MEDIA_TYPE: Final = "multipart/form-data"
_HASH_CHUNK_BYTES: Final = 1024 * 1024
# PRD ERR-39 and ERR-07.
PRECONDITION_REQUIRED_DETAIL: Final = "Send If-Match with the record's ETag to change this record."
PRECONDITION_FAILED_DETAIL: Final = (
    "This record changed since you opened it. Reload to see the latest version, then try again."
)
# DG-KRN-IDEM-03: problem responses that are not kept, so a retry runs the command again. 5xx
# responses are never kept either.
UNSTORED_STATUSES: Final = frozenset({401, 403, 412, 428, 429})
# DG-KRN-IDEM-03 rev 1.127 (item IDEM-LOCK-CONFLICT-1; supervisor rulings R-97 (6) and R-112 (d);
# 04 DB-07 (2), (3)): two 409s are not kept either, by slug. Nothing was done and the rule for
# each is "submit it again" - a `lock-conflict` met a busy row, and the resubmission of a posting
# the period guard refused (`period-closed`, EREV-LED-003) is planned into the next open period.
# Kept, the same key and body would be answered the stored refusal for as long as the record lives
# and the command would never run. For the deterministic uses of `period-closed` the second run is
# refused again and writes nothing. Every other 409 stays kept.
UNSTORED_SLUGS: Final = frozenset({"lock-conflict", "period-closed"})

Precondition = Literal["none", "contract", "row"]
# DG-KRN-IDEM-05: contract ETags "s<head_stream_version>", row ETags "r<row_version>" (API-C-08).
_ETAG_VERSION: Final[Mapping[str, re.Pattern[str]]] = {
    "contract": re.compile(r'"s(0|[1-9][0-9]{0,9})"'),
    "row": re.compile(r'"r([1-9][0-9]{0,9})"'),
}


def cookie_secure(request: Request) -> bool:
    """05 SAR-09 / DG-KRN-AUTH-07: the session cookie is Secure unless ``EREV_PUBLIC_ORIGIN`` is
    an http origin on a loopback host.

    The attribute follows the configured origin, never the request: ``request.url`` is built from
    the ``Host`` header, which the client chooses, so reading it let a request with
    ``Host: 127.0.0.1`` obtain a cookie without Secure from an https deployment (R-34 SD-2). It
    fails closed (supervisor ruling R-53 (1)): only the local environments and the compose
    verification stack, whose configured origin is ``http://127.0.0.1``, set none — a browser
    would not return a Secure cookie to them. An http origin on any other host keeps Secure, so a
    misconfigured deployment holds no session rather than one in clear.
    """
    settings: Settings = request.app.state.settings
    origin = urlsplit(settings.public_origin)
    loopback = (origin.hostname or "").lower() in LOOPBACK_ORIGIN_HOSTS
    return not (origin.scheme == "http" and loopback)


@dataclass(frozen=True, slots=True)
class CommandContext:
    ctx: RequestContext
    started: Started
    expected_version: int | None  # parsed If-Match for precondition routes


@dataclass(frozen=True, slots=True)
class KernelDeps:
    settings: Settings
    clock: Clock
    keyring: KeyRing
    files: FileStore


def kernel_deps(request: Request, clock: Annotated[Clock, Depends(get_clock)]) -> KernelDeps:
    """The composition-root services a command handler's unit of work needs."""
    state = request.app.state
    return KernelDeps(
        settings=state.settings, clock=clock, keyring=state.keyring, files=state.file_store
    )


class IdempotentReplay(Exception):
    """Raised by ``command`` for a repeat of a completed command; answered with the stored one."""

    def __init__(self, replay: Replay) -> None:
        super().__init__("idempotent replay")
        self.replay = replay


def validate_idempotency_key(request: Request) -> str:
    """8 to 255 printable ASCII characters, else 422 with ``rule_id`` API-C-04 (DG-KRN-IDEM-01)."""
    key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    if (
        key is None
        or len(key) not in IDEMPOTENCY_KEY_LENGTH
        or not (key.isascii() and key.isprintable())
    ):
        raise Problem(
            "validation-failed",
            IDEMPOTENCY_KEY_DETAIL,
            errors=[
                ProblemError(
                    field=IDEMPOTENCY_KEY_HEADER,
                    rule_id="API-C-04",
                    message=IDEMPOTENCY_KEY_MESSAGE,
                )
            ],
        )
    return key


def expected_version(if_match: str | None, precondition: Precondition) -> int | None:
    """The version of ``If-Match``: missing → 428, unparsable → 412 (DG-KRN-IDEM-05)."""
    if precondition == "none":
        return None
    if if_match is None or not if_match.strip():
        raise Problem("precondition-required", PRECONDITION_REQUIRED_DETAIL)
    match = _ETAG_VERSION[precondition].fullmatch(if_match.strip())
    if match is None:
        raise Problem("precondition-failed", PRECONDITION_FAILED_DETAIL)
    return int(match.group(1))


def row_etag(row_version: int) -> str:
    """API-C-08 ETag of an IM-M, IM-P or SC-M-carrying IM-S row."""
    return f'"r{row_version}"'


def contract_etag(head_stream_version: int) -> str:
    """API-C-08 ETag of a contract."""
    return f'"s{head_stream_version}"'


def assert_version(expected: int | None, actual: int) -> None:
    """412 ``precondition-failed`` unless the parsed ``If-Match`` equals the locked version."""
    if expected is None or expected != actual:
        raise Problem("precondition-failed", PRECONDITION_FAILED_DETAIL)


def _form_value(form: FormData) -> dict[str, list[Any]]:
    """The hashed value of a multipart body: field values and, per file, name, type and SHA-256."""
    value: dict[str, list[Any]] = {}
    for name, item in form.multi_items():
        entry: Any = item
        if isinstance(item, UploadFile):
            digest = hashlib.sha256()
            item.file.seek(0)
            while chunk := item.file.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
            item.file.seek(0)
            entry = {
                "filename": item.filename,
                "content_type": item.content_type,
                "sha256": digest.hexdigest(),
            }
        value.setdefault(name, []).append(entry)
    return value


def refuse_inactive_tenant(ctx: RequestContext) -> None:
    """05 SBX-07 rev 1.64: a tenant that is not ACTIVE — a sandbox archived by a reset or a failed
    load, or one whose load has not completed — takes no command; 409 ``invalid-transition``
    before the key is read, so nothing is stored for the attempt. Reads are not gated here."""
    if ctx.tenant_status is not TenantStatus.ACTIVE:
        raise Problem("invalid-transition", sessions.WORKSPACE_NOT_ACTIVE[ctx.tenant_status])


@overload
def command() -> Callable[..., str]: ...


@overload
def command(
    permission: str, *, precondition: Precondition = "none", all_entities: bool = False
) -> Callable[..., Awaitable[CommandContext]]: ...


@overload
def command(*, per_subject: Literal[True]) -> Callable[..., Awaitable[CommandContext]]: ...


def command(
    permission: str | None = None,
    *,
    precondition: Precondition = "none",
    per_subject: bool = False,
    all_entities: bool = False,
) -> Callable[..., Any]:
    """The dependency of every command route (DG-KRN-IDEM-01 to DG-KRN-IDEM-05).

    In order: the ``require(permission)`` guard; 403 for an operator, whose support access is
    read-only (REQ-PLT-036); 409 ``invalid-transition`` in a tenant that is not ACTIVE (05
    SBX-07); the key (422 API-C-04); the ``If-Match``
    precondition (428, 412); then ``idempotency.store.begin``, whose replay short-circuits the route
    with the stored response. Without a permission it validates the key only (SPEC-Q-122).
    ``per_subject=True`` guards with ``require_authenticated()`` and leaves authorisation to the
    handler, for routes whose permission depends on the request body (API-R-12; SPEC-Q-157).
    ``all_entities=True`` guards with ``require_all_entities(permission)``: a tenant-wide act,
    which a holder of named entities is refused (supervisor ruling R-28).
    """
    guard: Callable[..., RequestContext]
    if all_entities and (per_subject or permission is None):
        raise ValueError("a command for all entities names its permission")
    if per_subject:
        if permission is not None or precondition != "none":
            raise ValueError("a per-subject command names no permission and no precondition")
        guard = require_authenticated()
    elif permission is None:
        if precondition != "none":
            raise ValueError("a session command without a permission takes no precondition")

        def dependency(request: Request) -> str:
            return validate_idempotency_key(request)

        setattr(dependency, COMMAND_ATTRIBUTE, True)  # noqa: B010 - the route class reads it
        return dependency
    else:
        guard = require_all_entities(permission) if all_entities else require(permission)

    async def command_dependency(
        request: Request,
        ctx: RequestContext = Depends(guard),  # noqa: B008 - the guard is local to this factory
    ) -> CommandContext:
        await run_in_threadpool(refuse_operator_command, request, ctx)
        refuse_inactive_tenant(ctx)
        validate_idempotency_key(request)
        version = expected_version(ctx.if_match, precondition)
        query: dict[str, list[str]] = {}
        for name, value in request.query_params.multi_items():
            query.setdefault(name, []).append(value)
        route = request.scope.get("route")
        content_type = request.headers.get("content-type", "")
        form: dict[str, list[Any]] | None = None
        body = b""
        if content_type.split(";", 1)[0].strip().lower() == MULTIPART_MEDIA_TYPE:
            form = await run_in_threadpool(_form_value, await request.form())
        else:
            body = await request.body()
        outcome = await run_in_threadpool(
            store.begin,
            ctx,
            method=request.method,
            route_template=str(getattr(route, "path", request.url.path)),
            path_params={name: str(value) for name, value in request.path_params.items()},
            query=query,
            body=body,
            content_type=content_type,
            form=form,
            files=request.app.state.file_store,
        )
        if isinstance(outcome, Replay):
            raise IdempotentReplay(outcome)
        return CommandContext(ctx=ctx, started=outcome, expected_version=version)

    setattr(command_dependency, COMMAND_ATTRIBUTE, True)  # noqa: B010 - the route class reads it
    return command_dependency


def _json_body(result: BaseModel | Mapping[str, Any]) -> Any:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    return jsonable_encoder(dict(result))


def _settle_failed_command(cmd: CommandContext, exc: BaseException) -> None:
    """Keep a problem response as the first response, or abandon the attempt (DG-KRN-IDEM-03).

    The command transaction has rolled back, so a kept problem is stored in a transaction of its
    own. When settling fails, the record stays ``IN_PROGRESS`` until TXN-06 takes it over.
    """
    problem: Problem | None = None
    if isinstance(exc, Problem):
        problem = exc
    elif isinstance(exc, DBAPIError):
        problem = from_db_error(exc)
    try:
        if (
            problem is None
            or problem.status >= 500
            or problem.status in UNSTORED_STATUSES
            or problem.slug in UNSTORED_SLUGS
        ):
            store.abandon(cmd.ctx, cmd.started)
            return
        with tenant_session(cmd.ctx.principal.db_context) as session:
            store.complete(
                session,
                cmd.started,
                status=problem.status,
                headers={"Content-Type": MEDIA_TYPE},
                body=problem.to_json(instance=INSTANCE_BASE + cmd.ctx.request_id),
            )
    except Exception:
        get_logger(__name__).exception("idempotency.settle_failed")


def _store_response_body(uow: UnitOfWork, data: bytes) -> UUID:
    """DG-KRN-IDEM-04: a large first response becomes a ``REPORT_OUTPUT`` file (BS1-D-28)."""
    row = store_file(
        uow,
        purpose=FilePurpose.REPORT_OUTPUT,
        stream=io.BytesIO(data),
        original_filename=None,
        media_type=store.JSON_MEDIA_TYPE,
    )
    return UUID(str(row["id"]))


def run_command(
    cmd: CommandContext,
    deps: KernelDeps,
    fn: Callable[[UnitOfWork], BaseModel | Mapping[str, Any] | None],
    *,
    status_code: int = 200,
    location: Callable[[Any], str] | None = None,
    etag: Callable[[Any], str] | None = None,
    stored_body: Callable[[Any], Any] | None = None,
    extra_headers: Callable[[Any], Mapping[str, str]] | None = None,
    status_of: Callable[[Any], int] | None = None,
) -> Response:
    """Run ``fn`` in a unit of work, store the response, then commit (DG-CMD-08; DG-KRN-IDEM-03).

    ``location`` and ``etag`` build the ``Location`` (201, DG-CMD-12) and ``ETag`` (API-C-08)
    headers from the handler's result. A handler returning None answers without a body (204).
    ``stored_body`` maps the returned body to the body kept for replay, when the two differ
    (``withheld``; D-80). ``extra_headers`` adds resource headers such as the id of the resource a
    202 job creates (04 §16.14 ``X-Erev-Evidence-Pack-Id`` precedent). ``status_of`` picks the
    status from the result, for a command that answers 201 or a 202 job (API-R-30; CTR-5).
    """
    try:
        with unit_of_work(cmd.ctx, clock=deps.clock, keyring=deps.keyring, files=deps.files) as uow:
            result = fn(uow)
            if status_of is not None:
                status_code = status_of(result)
            body = None if result is None else _json_body(result)
            headers: dict[str, str] = {}
            if location is not None:
                headers["Location"] = location(result)
            if etag is not None:
                headers["ETag"] = etag(result)
            if extra_headers is not None:
                headers.update(extra_headers(result))
            store.complete(
                uow.session,
                cmd.started,
                status=status_code,
                headers=headers,
                body=body if stored_body is None or body is None else stored_body(body),
                store_body=lambda data: _store_response_body(uow, data),
            )
            uow.commit()
    except BaseException as exc:
        _settle_failed_command(cmd, exc)
        raise
    if body is None:
        return Response(status_code=status_code, headers=headers)
    return JSONResponse(body, status_code=status_code, headers=headers)


def withheld(member: str) -> Callable[[Any], Any]:
    """The ``stored_body`` of a response that shows a one-time secret: the stored and replayed body
    carries ``member`` as null, so the value appears only in the first response (D-80; SAR-18)."""
    return lambda body: {**body, member: None}


def replay_response(replay: Replay) -> Response:
    """The stored status, headers and body plus ``Idempotent-Replay: true`` (DG-KRN-IDEM-04)."""
    headers = dict(replay.headers)
    media_type = headers.pop("Content-Type", "application/json")
    headers[REPLAY_HEADER] = "true"
    if replay.body is None:
        return Response(status_code=replay.status, headers=headers)
    if isinstance(replay.body, bytes):  # a body stored as a file (DG-KRN-IDEM-04)
        return Response(
            replay.body, status_code=replay.status, headers=headers, media_type=media_type
        )
    return JSONResponse(
        replay.body, status_code=replay.status, headers=headers, media_type=media_type
    )


async def _handle_replay(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, IdempotentReplay)
    return replay_response(exc.replay)


def install_command_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IdempotentReplay, _handle_replay)


# --- shared OpenAPI header components (Codex I4 follow-up 1; lane record §13.2.16) ----------------
# One definition each; routes reference them by $ref and GuardedRoute adds the Idempotency-Key
# parameter to every command operation, so the generated client types carry the headers.
COMMAND_ATTRIBUTE: Final = "erev_command"  # set on the dependencies command(...) returns
IDEMPOTENCY_KEY_COMPONENT: Final = "IdempotencyKey"
IDEMPOTENCY_KEY_REF: Final[Mapping[str, str]] = MappingProxyType(
    {"$ref": f"#/components/parameters/{IDEMPOTENCY_KEY_COMPONENT}"}
)
# Codex F-SNP-I51-DOC1: the operator route (DG-KRN-TEN-05) validates the same header directly and
# keeps no tenant idempotency record, so its declaration promises no stored-response replay.
IDEMPOTENCY_KEY_OPERATOR_COMPONENT: Final = "IdempotencyKeyOperator"
IDEMPOTENCY_KEY_OPERATOR_REF: Final[Mapping[str, str]] = MappingProxyType(
    {"$ref": f"#/components/parameters/{IDEMPOTENCY_KEY_OPERATOR_COMPONENT}"}
)
PARAMETER_COMPONENTS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        IDEMPOTENCY_KEY_COMPONENT: {
            "name": "Idempotency-Key",
            "in": "header",
            "required": True,
            "description": (
                "API-C-04: one key per user intent (8-255 characters); a repeat with the same key "
                "and body replays the stored response, another body is 422 idempotency-key-reused."
            ),
            "schema": {"type": "string", "minLength": 8, "maxLength": 255},
        },
        IDEMPOTENCY_KEY_OPERATOR_COMPONENT: {
            "name": "Idempotency-Key",
            "in": "header",
            "required": True,
            "description": (
                "DG-KRN-TEN-05: required, 8-255 printable ASCII characters, validated by the "
                "operator route itself. The operator route keeps no tenant idempotency record and "
                "sends no stored response on a repeat: a repeated key is not a replay."
            ),
            "schema": {"type": "string", "minLength": 8, "maxLength": 255},
        },
    }
)
HEADER_COMPONENTS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        "Location": {
            "description": "The created resource, or the job a 202 accepted (API-C-12).",
            "schema": {"type": "string"},
        },
        "ETag": {
            "description": (
                "API-C-08: the row version or representation hash; sent back as If-Match on the "
                "next command."
            ),
            "schema": {"type": "string"},
        },
        "X-Erev-Tenant-Snapshot-Id": {
            "description": (
                "The T-PLT-34 row the accepted TENANT_SNAPSHOT job fills (the 04 §16.14 "
                "X-Erev-Evidence-Pack-Id precedent)."
            ),
            "schema": {"type": "string", "format": "uuid"},
        },
        "X-Erev-Sandbox-Tenant-Id": {
            "description": (
                "The sandbox tenant the accepted load-only TENANT_SNAPSHOT job creates "
                "(API-R-04 rev 1.67; the id is pre-allocated by the request)."
            ),
            "schema": {"type": "string", "format": "uuid"},
        },
    }
)


def header_responses(status: int, *names: str, description: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` entry declaring the shared response headers ``names`` on ``status``;
    merged by FastAPI with the response the route model generates."""
    unknown = sorted(set(names) - set(HEADER_COMPONENTS))
    if unknown:
        raise ValueError(f"no shared header component for {unknown}")
    return {
        status: {
            "description": description,
            "headers": {name: {"$ref": f"#/components/headers/{name}"} for name in names},
        }
    }


def install_openapi_components(app: FastAPI) -> None:
    """Add the shared parameter and header components to the generated document, once."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = original()
            components = schema.setdefault("components", {})
            components.setdefault("parameters", {}).update(
                {name: dict(value) for name, value in PARAMETER_COMPONENTS.items()}
            )
            components.setdefault("headers", {}).update(
                {name: dict(value) for name, value in HEADER_COMPONENTS.items()}
            )
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def _depends_on_command(dependant: Any) -> bool:
    pending = list(getattr(dependant, "dependencies", ()))
    while pending:
        current = pending.pop()
        if getattr(current.call, COMMAND_ATTRIBUTE, False):
            return True
        pending.extend(current.dependencies)
    return False


def problem_responses(*slugs: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` for the problems a route can return, one per status (DG-API-05)."""
    by_status: dict[int, list[str]] = {}
    for slug in slugs:
        by_status.setdefault(PROBLEMS[slug].status, []).append(slug)
    return {
        status: {
            "model": ProblemOut,
            "description": "Problem: " + ", ".join(names),
            "content": {MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/ProblemOut"}}},
        }
        for status, names in sorted(by_status.items())
    }


class GuardedRoute(APIRoute):
    """An ``APIRoute`` that records its ``require`` permission in ``openapi_extra`` (API-C-03)
    and asks its route's session question before the request body is read (05 §2.5; 04
    API-C-17; DG-API-12, DG-KRN-AUTH-09; item AUTH-BEFORE-BODY-1).

    FastAPI reads and decodes a route's body before it solves the route's dependencies, the
    guard among them, so a plain route answered a caller without a session for its body — 422
    for one that does not decode — before it had looked at the session. ``get_route_handler``
    puts the route's own session question (``auth.dependencies.session_questions``: the
    session or token, the synchronizer token, the request rate and the second factor) in front
    of that handler. What the identity store answered is kept for the request, so FastAPI's
    later call of the same guard asks the store nothing — unless the body took longer than
    ``auth.dependencies.KEPT_FOR``, when it asks again as it did before the rule. The
    permission, the operator's and the tenant-status refusals and the key stay after the body.
    A route without a guard is not wrapped."""

    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(path, endpoint, **kwargs)
        codes = declared_permissions(self.dependant)
        if len(codes) > 1:
            raise ValueError(f"route {path} declares several permissions: {sorted(codes)}")
        if codes:
            (code,) = codes
            self.openapi_extra = {**(self.openapi_extra or {}), PERMISSION_EXTENSION: code}
        if _depends_on_command(self.dependant):
            # API-C-04: every command operation documents the Idempotency-Key header once.
            extra = dict(self.openapi_extra or {})
            extra["parameters"] = [*extra.get("parameters", []), dict(IDEMPOTENCY_KEY_REF)]
            self.openapi_extra = extra

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        questions = session_questions(self.dependant)
        if not questions:
            return handler

        async def guarded_handler(request: Request) -> Response:
            clock = get_clock(request)
            for question in questions:
                # Blocking (the identity store): a worker thread, as FastAPI runs the guard.
                await run_in_threadpool(question, request, clock)
            return await handler(request)

        return guarded_handler
