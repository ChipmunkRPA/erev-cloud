"""Outbound HTTP client of the inbound adapters (05 ADP-14, ADP-20, SAR-15, TB-5; dev-guide
DG-ARC-12, DG-LAY-03; BUILD_SPEC DIN-12).

``client_factory(env)`` builds the ``HttpClientFactory`` a composition root registers with
``domain.integrations.sync.register_http_client_factory``: given ``integration_connection.base_url``
it checks the destination through the SAR-15 guard when the client is built and again per request
in ``GuardedTransport``, and connects to the address it checked with the ``Host`` header and SNI
carrying the name (the ``WebhookClient`` pattern), with a 10 s timeout, no redirects and no proxy
environment. In dev / test / e2e the guard admits loopback and plain http, so a worker reaches the
api process's in-process mock routers over ``base_url`` (ADP-20); a refused destination is
``ports.Permanent`` (ADP-12: never retried). Network imports live here and nowhere in the domain
(DG-ARC-12).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

import httpx

from erev_api.adapters.http.guard import (
    DestinationRefused,
    Resolver,
    check_destination,
    system_resolver,
)
from erev_api.config import Environment
from erev_api.domain.integrations import ports

__all__ = ["REQUEST_TIMEOUT_SECONDS", "GuardedTransport", "client_factory"]

REQUEST_TIMEOUT_SECONDS: Final = 10.0


class GuardedTransport(httpx.BaseTransport):
    """Checks every request's destination (SAR-15) and pins the connection to the checked address;
    the name travels in ``Host`` and, under https, as the SNI host name."""

    def __init__(
        self, inner: httpx.BaseTransport, *, env: Environment, resolve: Resolver = system_resolver
    ) -> None:
        self._inner = inner
        self._env = env
        self._resolve = resolve

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            destination = check_destination(str(request.url), env=self._env, resolve=self._resolve)
        except DestinationRefused as refused:
            raise ports.Permanent(str(refused)) from refused
        request.url = request.url.copy_with(host=destination.address)
        request.headers["Host"] = destination.netloc
        if destination.scheme == "https":
            request.extensions["sni_hostname"] = destination.host
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def client_factory(
    env: Environment,
    *,
    transport: httpx.BaseTransport | None = None,
    resolve: Resolver = system_resolver,
) -> Callable[[str], httpx.Client]:
    """The factory of guarded clients for ``env``; ``transport`` replaces the network transport in
    tests (an ``httpx.MockTransport``)."""

    def build(base_url: str) -> httpx.Client:
        try:
            check_destination(base_url, env=env, resolve=resolve)
        except DestinationRefused as refused:
            raise ports.Permanent(f"base_url refused: {refused}") from refused
        inner = transport if transport is not None else httpx.HTTPTransport()
        return httpx.Client(
            transport=GuardedTransport(inner, env=env, resolve=resolve),
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        )

    return build
