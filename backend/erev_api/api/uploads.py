"""Upload routes: a multipart body is admitted before it is read (04 API-C-17 rev 1.189; 05
UPL-01 and §2.5 step 3; dev-guide DG-API-12; supervisor ruling R-111 (8)).

FastAPI parses a route's form before it solves the route's dependencies, so a plain route
receives and spools a multipart body — up to the middleware's route limit — before its guard has
looked at the session. ``UploadRoute`` puts the questions that need no body in front of the parse
(``admit_upload``):

1. the route's session guard, ``get_request_context``: the session or token, the synchronizer
   token, the request rate and the second factor (DG-KRN-AUTH-01 to -03);
2. ``refuse_operator_command`` and ``refuse_inactive_tenant``, as every command does;
3. the ``Idempotency-Key`` header (API-C-04);
4. what the caller could store: ``attachments.upload_ceiling``, the largest T-PLT-29 limit among
   the purposes the caller may upload. A body declared above it plus the multipart envelope is
   refused unread — 403 with its ``DENIED`` event for a caller who may upload for no purpose, 422
   ``upload-type-not-allowed`` naming that largest limit otherwise — and the body is then read
   through a ``receive`` that counts to the same bound, whatever length was declared.

FastAPI's handler then runs unchanged: it parses the form and solves the dependencies, the
command dependency with its guard among them. For a form that arrived within
``auth.dependencies.KEPT_FOR`` that guard is answered from what the identity store answered to
``admit_upload`` (DG-KRN-AUTH-09); for one that took longer the session is checked again when
the command starts, so a session ended during the upload stores nothing. The limit of the
purpose the form names is applied where the purpose is known.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from erev_api.api.deps import GuardedRoute, refuse_inactive_tenant, validate_idempotency_key
from erev_api.api.middleware import MULTIPART_OVERHEAD_BYTES, CountingReceive
from erev_api.auth.dependencies import get_request_context, refuse_operator_command
from erev_api.auth.principal import RequestContext
from erev_api.clock import get_clock
from erev_api.domain.platform import attachments
from erev_api.files import policy
from erev_api.problems import Problem


@dataclass(frozen=True, slots=True)
class Admission:
    """What an admitted upload may send: ``limit`` body bytes, and the refusal of a body that
    passes them (it may write an audit event: call it in a worker thread)."""

    limit: int
    refusal: Callable[[], Problem]


def _admission(request: Request, ctx: RequestContext) -> Admission:
    """The bound of the caller's upload, or the refusal of a body declared above it."""
    keyring = request.app.state.keyring
    ceiling = attachments.upload_ceiling(ctx)
    if ceiling is None:
        admission = Admission(
            limit=MULTIPART_OVERHEAD_BYTES,
            refusal=lambda: attachments.refuse_upload(ctx, keyring=keyring),
        )
    else:
        detail = policy.LIMIT_DETAILS[ceiling.purpose]
        admission = Admission(
            limit=ceiling.limit + MULTIPART_OVERHEAD_BYTES,
            refusal=lambda: Problem("upload-type-not-allowed", detail),
        )
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > admission.limit:
        raise admission.refusal()
    return admission


def admit_upload(request: Request) -> Admission:
    """Everything ``POST /files`` asks before a byte of the body is read; the problem of the
    first question that fails (module docstring). Blocking: run it in a worker thread."""
    ctx = get_request_context(request, get_clock(request))
    refuse_operator_command(request, ctx)
    refuse_inactive_tenant(ctx)
    validate_idempotency_key(request)
    return _admission(request, ctx)


class UploadRoute(GuardedRoute):
    """A ``GuardedRoute`` whose body is a multipart upload: ``admit_upload`` answers before the
    form is parsed, and the form is read through a ``receive`` bounded by the admission."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def upload_handler(request: Request) -> Response:
            admission = await run_in_threadpool(admit_upload, request)
            body = CountingReceive(request.receive, admission.limit)
            try:
                response = await handler(Request(request.scope, body))
            except Exception:
                if not body.exceeded:
                    raise
                # The parser met the bound as a disconnect; the answer is the refusal.
                raise await run_in_threadpool(admission.refusal) from None
            if body.exceeded:
                raise await run_in_threadpool(admission.refusal)
            return response

        return upload_handler
