"""SOP-4 request limits as a pure policy (05 SAR-13; 04 API-C-16; REQ-PLT-037; lane P5
preparation slice): bucket selection, refusal without counting, ``Retry-After`` and the window
reset. The route wiring and the OpenAPI line are the integration slice; DB-free here."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from erev_api.auth.ratelimit import (
    API_CLIENT_DEFAULT_PER_MINUTE,
    BROWSER_PER_SESSION,
    OPENAPI_RATE_LIMIT_LINE,
    TOKEN_PER_CLIENT_ID,
    RequestRateLimiter,
    request_limits,
)

T0 = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)


def test_bucket_selection_per_route_class() -> None:
    assert request_limits("TOKEN", client_id="c1") == ((("token", "c1"), TOKEN_PER_CLIENT_ID),)
    assert request_limits("BROWSER_SESSION", session_id="s1") == (
        (("session", "s1"), BROWSER_PER_SESSION),
    )
    assert request_limits("API_CLIENT", api_client_id="a1") == (
        (("api-client", "a1"), API_CLIENT_DEFAULT_PER_MINUTE),
    )
    assert request_limits("API_CLIENT", api_client_id="a1", api_client_limit=5) == (
        (("api-client", "a1"), 5),
    )
    assert (TOKEN_PER_CLIENT_ID, BROWSER_PER_SESSION, API_CLIENT_DEFAULT_PER_MINUTE) == (
        30,
        1_200,
        600,
    )
    for kwargs in (
        {"route_class": "TOKEN"},
        {"route_class": "BROWSER_SESSION"},
        {"route_class": "API_CLIENT"},
    ):
        with pytest.raises(ValueError):
            request_limits(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        request_limits("API_CLIENT", api_client_id="a1", api_client_limit=0)


def test_api_client_limit_five_refuses_the_sixth_with_retry_after_and_resets_after_a_minute() -> (
    None
):
    limiter = RequestRateLimiter()
    for _ in range(5):
        assert limiter.admit("API_CLIENT", now=T0, api_client_id="a1", api_client_limit=5).allowed
    refused = limiter.admit("API_CLIENT", now=T0, api_client_id="a1", api_client_limit=5)
    assert not refused.allowed and refused.retry_after == 60
    assert refused.headers == {"Retry-After": "60"}
    # A refused request is not counted, so it does not extend the wait.
    again = limiter.admit(
        "API_CLIENT", now=T0 + timedelta(seconds=30), api_client_id="a1", api_client_limit=5
    )
    assert not again.allowed and again.retry_after == 30
    # Another client and another class are independent buckets.
    assert limiter.admit("API_CLIENT", now=T0, api_client_id="a2", api_client_limit=5).allowed
    assert limiter.admit("TOKEN", now=T0, client_id="a1").allowed
    # After the window the next request is admitted.
    assert limiter.admit(
        "API_CLIENT", now=T0 + timedelta(seconds=60), api_client_id="a1", api_client_limit=5
    ).allowed


def test_token_endpoint_thirty_one_per_minute_per_client_id() -> None:
    limiter = RequestRateLimiter()
    for index in range(30):
        assert limiter.admit("TOKEN", now=T0 + timedelta(seconds=index), client_id="cid").allowed
    thirty_first = limiter.admit("TOKEN", now=T0 + timedelta(seconds=30), client_id="cid")
    assert not thirty_first.allowed and thirty_first.retry_after == 30
    assert limiter.admit("TOKEN", now=T0 + timedelta(seconds=30), client_id="other").allowed


def test_browser_session_limit_and_openapi_line() -> None:
    limiter = RequestRateLimiter()
    for _ in range(BROWSER_PER_SESSION):
        assert limiter.admit("BROWSER_SESSION", now=T0, session_id="s").allowed
    assert not limiter.admit("BROWSER_SESSION", now=T0, session_id="s").allowed
    assert OPENAPI_RATE_LIMIT_LINE == (
        "Rate limit: 600 requests per minute per API client (default); enforced per api process."
    )
    assert "600 requests per minute per API client" in OPENAPI_RATE_LIMIT_LINE
