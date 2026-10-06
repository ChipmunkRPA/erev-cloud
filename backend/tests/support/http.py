"""HTTP calls over ASGI for api tests (docs/dev-guide.md §9.1; no network, DG-TST-15)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

# The response type for api test helpers, which may not import httpx themselves (DG-ARC-12).
type HttpResponse = httpx.Response
# The request an outbound adapter sends through ``mock_transport``.
type HttpRequest = httpx.Request
# The client ``asgi_client`` returns.
type HttpClient = httpx.Client


def mock_transport(respond: Callable[[httpx.Request], int]) -> httpx.MockTransport:
    """An in-process transport answering each request with the status ``respond`` returns and an
    empty body; outbound adapters use it instead of the network (DG-TST-15)."""
    return httpx.MockTransport(lambda request: httpx.Response(respond(request)))


def json_transport(respond: Callable[[httpx.Request], Any]) -> httpx.MockTransport:
    """An in-process transport answering each request with 200 and the JSON value ``respond``
    returns."""
    return httpx.MockTransport(lambda request: httpx.Response(200, json=respond(request)))


def asgi_sync_transport(app: Any) -> httpx.MockTransport:
    """A synchronous transport answering through ``app`` over ASGI, so an outbound adapter called
    inside a synchronous route reaches the in-process mocks (DG-API-09) without a port. Each request
    runs on a fresh event loop in the route's worker thread, which has no running loop."""

    def handle(request: httpx.Request) -> httpx.Response:
        async def run() -> httpx.Response:
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            response = await transport.handle_async_request(request)
            content = await response.aread()
            return httpx.Response(response.status_code, headers=response.headers, content=content)

        return asyncio.run(run())

    return httpx.MockTransport(handle)


def asgi_client(app: Any) -> httpx.Client:
    """A synchronous client over ``asgi_sync_transport``: adapter unit tests call an outbound
    adapter against the in-process mocks through it and import no network library (DG-ARC-12)."""
    return httpx.Client(transport=asgi_sync_transport(app), base_url="http://127.0.0.1")


def recording_transport(inner: httpx.MockTransport, requested: list[str]) -> httpx.MockTransport:
    """``inner`` with each request's URL appended to ``requested`` before it is answered."""

    def handle(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return inner.handle_request(request)

    return httpx.MockTransport(handle)


def recording_asgi_client(app: Any, requested: list[str]) -> httpx.Client:
    """``asgi_client`` that appends each request's URL to ``requested`` before it is answered."""
    return httpx.Client(
        transport=recording_transport(asgi_sync_transport(app), requested),
        base_url="http://127.0.0.1",
    )


def call(app: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    """One request through ``httpx.ASGITransport``; unhandled errors become 500 responses."""

    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())
