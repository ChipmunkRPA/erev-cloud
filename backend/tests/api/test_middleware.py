"""Request lifecycle middleware (05 §2.5 steps 1 to 3, SAR-20; 04 API-C-15, API-C-17; DG-LOG-04)."""

from __future__ import annotations

import io
import json
import uuid
from collections.abc import AsyncIterator

import pytest
from erev_api.config import Settings, SettingsError
from erev_api.main import create_app
from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
from support.http import call

LIMIT = 1_048_576
CHUNK = 65_536
SECURITY_HEADERS = {
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
    "Cross-Origin-Resource-Policy": "same-origin",  # 05 SAR-20 rev 1.53 (R-37 (a))
    "Cache-Control": "no-store",
}


def json_body(size: int) -> bytes:
    """A JSON object of exactly ``size`` bytes."""
    body = b'{"pad":"' + b"x" * (size - 10) + b'"}'
    assert len(body) == size
    return body


def probe_app(app_settings: Settings, invoked: list[int]) -> FastAPI:
    app = create_app(app_settings)

    @app.post("/api/v1/__probe__/echo")
    async def echo(request: Request) -> dict[str, int]:
        invoked.append(len(await request.body()))
        return {"size": invoked[-1]}

    @app.get("/api/v1/__probe__/boom")
    def boom() -> None:
        raise RuntimeError("probe failure")

    return app


def test_api_c_15_request_id_echo_or_generate(app_settings: Settings) -> None:
    app = create_app(app_settings)
    echoed = call(app, "GET", "/api/v1/healthz", headers={"X-Request-Id": "abcdefgh-123"})
    assert echoed.headers["X-Request-Id"] == "abcdefgh-123"

    replaced = call(app, "GET", "/api/v1/healthz", headers={"X-Request-Id": "bad id!"})
    generated = replaced.headers["X-Request-Id"]
    assert generated != "bad id!"
    assert uuid.UUID(generated).version == 7

    missing = call(app, "GET", "/api/v1/absent", headers={"X-Request-Id": "abcdefgh-456"})
    assert missing.json()["instance"] == "urn:erev:request:abcdefgh-456"


def test_sar_20_security_headers_on_every_response(app_settings: Settings) -> None:
    app = probe_app(app_settings, [])
    for path, status in (
        ("/api/v1/healthz", 200),
        ("/api/v1/absent", 404),
        ("/api/v1/__probe__/boom", 500),
    ):
        response = call(app, "GET", path)
        assert response.status_code == status
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value, (path, name)
        assert "X-Request-Id" in response.headers


def test_unhandled_error_is_about_blank_problem(app_settings: Settings) -> None:
    response = call(
        probe_app(app_settings, []),
        "GET",
        "/api/v1/__probe__/boom",
        headers={"X-Request-Id": "abcdefgh-789"},
    )
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert (body["type"], body["title"]) == ("about:blank", "Internal Server Error")
    assert body["instance"] == "urn:erev:request:abcdefgh-789"


def test_api_c_17_body_limit(app_settings: Settings) -> None:
    invoked: list[int] = []
    app = probe_app(app_settings, invoked)
    headers = {"content-type": "application/json"}

    refused = call(
        app, "POST", "/api/v1/__probe__/echo", content=json_body(LIMIT + 1), headers=headers
    )
    assert refused.status_code == 422
    body = refused.json()
    assert body["type"] == "https://erev.dev/problems/validation-failed"
    assert body["errors"][0]["rule_id"] == "API-C-17"
    assert invoked == []

    accepted = call(
        app, "POST", "/api/v1/__probe__/echo", content=json_body(LIMIT), headers=headers
    )
    assert accepted.status_code == 200
    assert invoked == [LIMIT]


def test_api_c_17_body_limit_without_declared_length(app_settings: Settings) -> None:
    invoked: list[int] = []
    app = probe_app(app_settings, invoked)
    yielded: list[int] = []

    async def chunks(total: int) -> AsyncIterator[bytes]:
        stream = io.BytesIO(json_body(total))
        while chunk := stream.read(CHUNK):
            yielded.append(len(chunk))
            yield chunk

    # A chunked 4 MiB body to a 1 MiB route is refused once the count passes the limit.
    refused = call(app, "POST", "/api/v1/__probe__/echo", content=chunks(4 * LIMIT))
    assert refused.status_code == 422
    body = refused.json()
    assert body["type"] == "https://erev.dev/problems/validation-failed"
    assert body["errors"][0]["rule_id"] == "API-C-17"
    assert invoked == []
    assert sum(yielded) <= LIMIT + CHUNK

    yielded.clear()
    accepted = call(app, "POST", "/api/v1/__probe__/echo", content=chunks(4_096))
    assert accepted.status_code == 200
    assert invoked == [4_096]

    # No pre-buffering: the route holds its first chunk while the rest of the body is unsent.
    first_chunk_after: list[int] = []

    @app.post("/api/v1/__probe__/stream")
    async def stream(request: Request) -> dict[str, int]:
        async for chunk in request.stream():
            if chunk and not first_chunk_after:
                first_chunk_after.append(len(yielded))
        return {"chunks": len(yielded)}

    yielded.clear()
    streamed = call(app, "POST", "/api/v1/__probe__/stream", content=chunks(8 * CHUNK))
    assert streamed.status_code == 200
    assert streamed.json() == {"chunks": 8}
    assert first_chunk_after == [1]


def test_api_c_17_chunked_upload_needs_declared_length(app_settings: Settings) -> None:
    app = create_app(app_settings)
    yielded: list[int] = []

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(256 * 16):  # 256 MiB in 64 KiB chunks
            yielded.append(CHUNK)
            yield bytes(CHUNK)

    # Without a session, the api used to consume the whole body before answering 401.
    response = call(
        app,
        "POST",
        "/api/v1/files",
        content=chunks(),
        headers={"content-type": "multipart/form-data; boundary=probe"},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["type"] == "https://erev.dev/problems/validation-failed"
    assert body["errors"][0]["rule_id"] == "API-C-17"
    assert len(yielded) <= 1


def test_sar_12_cors_allow_list_and_wildcard_refusal(
    app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = "http://127.0.0.1:5270"
    app = create_app(app_settings.model_copy(update={"cors_origins": (allowed,)}))
    preflight = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Idempotency-Key",
    }
    response = call(app, "OPTIONS", "/api/v1/healthz", headers={"Origin": allowed, **preflight})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == allowed
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    # The lifecycle middleware wraps the CORS middleware (SAR-20 headers on preflights too).
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    refused = call(
        app, "OPTIONS", "/api/v1/healthz", headers={"Origin": "http://127.0.0.1:9999", **preflight}
    )
    assert "Access-Control-Allow-Origin" not in refused.headers
    assert CORSMiddleware in [middleware.cls for middleware in app.user_middleware]

    plain = create_app(app_settings.model_copy(update={"cors_origins": ()}))
    assert CORSMiddleware not in [middleware.cls for middleware in plain.user_middleware]

    monkeypatch.setenv("EREV_CORS_ORIGINS", "*")
    wildcard = Settings()
    assert wildcard.cors_origins == ("*",)
    with pytest.raises(SettingsError, match="EREV_CORS_ORIGINS"):
        create_app(wildcard)
    for malformed in ("http://127.0.0.1:5270/", "127.0.0.1:5270", "https://*.example.com"):
        with pytest.raises(SettingsError, match="EREV_CORS_ORIGINS"):
            create_app(app_settings.model_copy(update={"cors_origins": (malformed,)}))


def test_dg_log_04_one_request_line(app_settings: Settings, log_stream: io.StringIO) -> None:
    response = call(
        create_app(app_settings),
        "GET",
        "/api/v1/healthz?probe=query-marker",
        headers={"X-Request-Id": "abcdefgh-123"},
    )
    assert response.status_code == 200

    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    (line,) = [line for line in lines if line["event"] == "http.request"]
    assert line["method"] == "GET"
    assert line["route"] == "/api/v1/healthz"
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], float | int)
    assert line["request_id"] == "abcdefgh-123"
    assert {"tenant_id", "principal_kind"} <= set(line)
    assert "query-marker" not in log_stream.getvalue()
