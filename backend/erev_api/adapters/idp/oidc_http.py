"""HTTP client of the OIDC relying party (05 SAR-15, SAR-27; D-80; BUILD_SPEC PLF-27, WEB-3b).

``HttpxOidcHttp`` implements ``erev_api.auth.oidc.OidcHttp``: discovery, JWKS and token requests
with a 10-second timeout, no redirects and no proxies from the environment. Every URL passes the
SAR-15 guard first, and the request goes to the checked address with the ``Host`` header and SNI
set to the URL host, as the webhook client does. A refused URL raises ``OidcDestinationRefused``,
which is both a ``DestinationRefused`` and an ``OidcHttpError``, so the sign-in refuses it as a
failed provider request. Tests hand it a transport over the in-process mock IdP and a resolver, so
no request leaves the process (DG-API-09, DG-TST-15).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

import httpx

from erev_api.adapters.http.guard import (
    DestinationRefused,
    Resolver,
    check_destination,
    system_resolver,
)
from erev_api.auth.oidc import OidcHttpError
from erev_api.config import Environment

REQUEST_TIMEOUT_SECONDS: Final = 10.0
ACCEPT_JSON: Final = {"Accept": "application/json"}


class OidcDestinationRefused(DestinationRefused, OidcHttpError):
    """A provider URL breaks SAR-15; nothing was sent."""


class HttpxOidcHttp:
    """The ``OidcHttp`` of the api process."""

    def __init__(
        self,
        *,
        env: Environment,
        transport: httpx.BaseTransport | None = None,
        resolve: Resolver = system_resolver,
    ) -> None:
        self._env = env
        self._transport = transport
        self._resolve = resolve

    def _json(
        self, url: str, send: Callable[[httpx.Client, httpx.URL, dict[str, Any]], httpx.Response]
    ) -> dict[str, Any]:
        try:
            destination = check_destination(url, env=self._env, resolve=self._resolve)
        except DestinationRefused as refused:
            raise OidcDestinationRefused(str(refused)) from refused
        target = httpx.URL(url).copy_with(host=destination.address)
        options: dict[str, Any] = {
            "headers": {**ACCEPT_JSON, "Host": destination.netloc},
            "extensions": {"sni_hostname": destination.host}
            if destination.scheme == "https"
            else {},
        }
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = send(client, target, options)
                body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OidcHttpError(type(error).__name__) from error
        if not response.is_success or not isinstance(body, dict):
            raise OidcHttpError(f"HTTP {response.status_code}")
        return body

    def get_json(self, url: str) -> dict[str, Any]:
        return self._json(url, lambda client, target, options: client.get(target, **options))

    def post_form(self, url: str, form: Mapping[str, str]) -> dict[str, Any]:
        return self._json(
            url, lambda client, target, options: client.post(target, data=dict(form), **options)
        )
