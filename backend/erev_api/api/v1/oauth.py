"""API-R-02 OAuth token: the client-credentials grant.

04 §15.3 API-R-02, API-C-01, API-C-02, T-PLT-16; 05 SAR-28; RFC 6749 §2.3.1, §4.4; BUILD_SPEC
PLF-25. ``POST /oauth/token`` is an API-C-01 unauthenticated route: the client authenticates with
HTTP Basic, the form carries ``grant_type`` and an optional space-separated ``scope``, and like
sign-in it takes no ``Idempotency-Key`` (SPEC-Q-190). The response is never cached.
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Final
from urllib.parse import unquote_plus

from fastapi import APIRouter, Depends, Form, Request, Response

from erev_api.api.deps import API_PREFIX, GuardedRoute, problem_responses
from erev_api.auth import api_clients
from erev_api.auth.dependencies import admit_address, admit_request, request_facts
from erev_api.clock import Clock, get_clock
from erev_api.schemas.api_clients import TokenOut

TAG: Final = "API-R-02 OAuth token"
BASIC_SCHEME: Final = "basic"

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def basic_credentials(request: Request) -> tuple[str, str]:
    """The client id and secret of ``Authorization: Basic``, form-decoded (RFC 6749 §2.3.1); a
    missing or malformed header gives 401 ``unauthenticated``."""
    scheme, _, encoded = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == BASIC_SCHEME:
        try:
            decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            decoded = ""
        client_id, separator, client_secret = decoded.partition(":")
        if separator and client_id and client_secret:
            return unquote_plus(client_id), unquote_plus(client_secret)
    raise api_clients.client_refusal()


@router.post(
    "/oauth/token",
    operation_id="oauth_token",
    response_model=TokenOut,
    responses=problem_responses("validation-failed", "unauthenticated", "rate-limited"),
)
def oauth_token(
    request: Request,
    response: Response,
    clock: Annotated[Clock, Depends(get_clock)],
    grant_type: Annotated[str, Form()],
    scope: Annotated[str | None, Form()] = None,
) -> TokenOut:
    """A 60-minute access token of an API client; send it as ``Authorization: Bearer``."""
    # SAR-13: the address is counted before the credentials are read, whatever client id the
    # request names, so that one address cannot try client ids without limit.
    admit_address(request, request_facts(request, clock))
    client_id, client_secret = basic_credentials(request)
    admit_request(request, "TOKEN", now=clock.now(), client_id=client_id)
    issued = api_clients.issue_token(
        client_id=client_id,
        client_secret=client_secret,
        grant_type=grant_type,
        scope=scope,
        now=clock.now(),
    )
    response.headers["Cache-Control"] = "no-store"
    return TokenOut(
        access_token=issued.access_token,
        token_type=api_clients.TOKEN_TYPE,
        expires_in=issued.expires_in,
        scope=" ".join(issued.scopes),
    )
