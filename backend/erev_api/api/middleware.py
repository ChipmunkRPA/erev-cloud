"""Request lifecycle middleware (05 §2.5 steps 1 to 3; 04 API-C-15, API-C-17; 05 SAR-20; DG-LOG-04).

One pure ASGI middleware runs the steps in the documented order around every response, problem
responses and unhandled errors included:

1. request id: keep an ``X-Request-Id`` matching ``^[A-Za-z0-9._-]{8,128}$`` or generate a UUIDv7,
   bind it to the log context, store it on the request state and echo it;
2. security headers on every response;
3. body limit: a declared ``Content-Length`` above the limit is refused with 422
   ``validation-failed`` before the route reads anything. ``POST /files`` allows the largest
   T-PLT-29 purpose limit plus multipart framing, refuses above it with 422
   ``upload-type-not-allowed`` and refuses a body without ``Content-Length`` with 422
   ``validation-failed``; the route applies the purpose's own limit (API-C-17; SPEC-Q-159) after
   it has authenticated the caller and bounded the body by what that caller may upload
   (``api.uploads``; ruling R-111 (8)). Every
   body is counted while the route reads it, one message at a time: once the count passes
   the limit the route receives ``http.disconnect``, its response is discarded and the refusal is
   sent instead (D-80, upload bodies).

A route may set its own ``Content-Security-Policy`` (downloads send ``sandbox``, 05 UPL-10); every
other security header is fixed.

It then logs one ``http.request`` line with the route template, never the raw path or query.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

import structlog
import uuid_utils
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from erev_api import clock
from erev_api.api import metrics as http_metrics
from erev_api.files import policy
from erev_api.logging import get_logger
from erev_api.problems import Problem, ProblemError, problem_response, unhandled_error_response

REQUEST_ID_HEADER: Final = "X-Request-Id"
TENANT_KIND_HEADER: Final = "X-Erev-Tenant-Kind"
CSP_HEADER: Final = "Content-Security-Policy"
BODY_LIMIT_BYTES: Final = 1024 * 1024
UPLOAD_PATHS: Final = frozenset({"/api/v1/files"})
MULTIPART_OVERHEAD_BYTES: Final = 64 * 1024
UPLOAD_LIMIT_BYTES: Final = max(policy.UPLOAD_LIMITS.values()) + MULTIPART_OVERHEAD_BYTES
SECURITY_HEADERS: Final[Mapping[str, str]] = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}
_REQUEST_ID: Final = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
_LOGGER: Final = "erev_api.http"


def accepted_request_id(value: str | None) -> str:
    """A well-formed client request id is kept; anything else is replaced by a new UUIDv7."""
    if value is not None and _REQUEST_ID.fullmatch(value):
        return value
    return str(uuid_utils.uuid7())


def body_too_large(limit_bytes: int) -> Problem:
    message = f"The request body is larger than the limit of {limit_bytes} bytes."
    return Problem(
        "validation-failed", message, errors=[ProblemError(rule_id="API-C-17", message=message)]
    )


def upload_too_large() -> Problem:
    """The purpose is not known before the body is read, so the largest limit is named."""
    return Problem("upload-type-not-allowed", policy.LEGACY_DATABASE_DETAIL)


def upload_length_required() -> Problem:
    """D-80 upload bodies rule 2: an upload declares its length before any byte is read."""
    message = "The upload must declare its length in the Content-Length header."
    return Problem(
        "validation-failed", message, errors=[ProblemError(rule_id="API-C-17", message=message)]
    )


class CountingReceive:
    """The ``receive`` a route reads from: it passes each message on as it arrives and answers
    ``http.disconnect`` once the body passes ``limit`` (D-80 upload bodies rule 1). The upload
    route counts a second time, to the bound of its caller (``api.uploads``)."""

    def __init__(self, receive: Receive, limit: int) -> None:
        self._receive = receive
        self._limit = limit
        self._size = 0
        self.exceeded = False

    async def __call__(self) -> Message:
        if self.exceeded:
            return {"type": "http.disconnect"}
        message = await self._receive()
        if message["type"] == "http.request":
            self._size += len(message.get("body", b""))
            if self._size > self._limit:
                self.exceeded = True
                return {"type": "http.disconnect"}
        return message


def route_template(scope: Scope) -> str | None:
    """The template of the route that served the request, or None when no route matched."""
    route = scope.get("route")
    if route is None:
        app = scope.get("app")
        for candidate in getattr(app, "routes", ()):
            if candidate.matches(scope)[0] is Match.FULL:
                route = candidate
                break
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else None


class RequestLifecycleMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        body_limit_bytes: int = BODY_LIMIT_BYTES,
        upload_limit_bytes: int = UPLOAD_LIMIT_BYTES,
    ) -> None:
        self.app = app
        self.body_limit_bytes = body_limit_bytes
        self.upload_limit_bytes = upload_limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        request_id = accepted_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started_at = clock.monotonic()
        status: int | None = None

        async def send_with_headers(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if name == CSP_HEADER and name in headers:
                        continue
                    headers[name] = value
                headers[REQUEST_ID_HEADER] = request_id
                # DG-API-06: authentication stores the active tenant's kind on the request state.
                tenant_kind = getattr(request.state, "tenant_kind", None)
                if isinstance(tenant_kind, str):
                    headers[TENANT_KIND_HEADER] = tenant_kind
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                upload = request.method == "POST" and request.url.path in UPLOAD_PATHS
                limit = self.upload_limit_bytes if upload else self.body_limit_bytes
                refusal = self._declared_refusal(request, upload, limit)
                if refusal is not None:
                    await problem_response(request, refusal)(scope, receive, send_with_headers)
                else:
                    await self._call_within_limit(
                        request, receive, send_with_headers, upload, limit
                    )
            except Exception as exc:
                if status is not None:
                    raise
                await unhandled_error_response(request, exc)(scope, receive, send_with_headers)
            finally:
                elapsed = clock.monotonic() - started_at
                route = route_template(scope)
                get_logger(_LOGGER).info(
                    "http.request",
                    method=request.method,
                    route=route,
                    status=status,
                    duration_ms=round(elapsed * 1000, 3),
                )
                # 05 MET-01, MET-02 (SOP-4): the route template, never the concrete path.
                http_metrics.observe_http(route, request.method, status, elapsed)

    @staticmethod
    def _declared_refusal(request: Request, upload: bool, limit: int) -> Problem | None:
        """The problem answered before any body byte is read, from the declared length."""
        declared = request.headers.get("content-length")
        if declared is None:
            return upload_length_required() if upload else None
        if declared.isdigit() and int(declared) > limit:
            return upload_too_large() if upload else body_too_large(limit)
        return None

    async def _call_within_limit(
        self, request: Request, receive: Receive, send: Send, upload: bool, limit: int
    ) -> None:
        """Run the route over a counting ``receive``; a body passing ``limit`` before the response
        starts discards the route's answer and sends the refusal."""
        body = CountingReceive(receive, limit)
        started = False

        async def route_send(message: Message) -> None:
            nonlocal started
            if body.exceeded and not started:
                return
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(request.scope, body, route_send)
        except Exception:
            if not body.exceeded or started:
                raise
        if body.exceeded and not started:
            problem = upload_too_large() if upload else body_too_large(limit)
            await problem_response(request, problem)(request.scope, receive, send)
