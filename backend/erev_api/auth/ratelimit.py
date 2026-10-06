"""Login, MFA and password reset rate limits (05 SAR-13; 03 REQ-SEC-004; PRD NFR-43; 04 T-PLT-42
rule 2; dev-guide DG-API-07; BS1-D-22).

An in-process sliding window with 1-second resolution: at most 10 attempts per minute per (client
address, normalised email) and 50 per minute per client address, and at most 20 password reset
requests per client address per rolling hour. A refused attempt is not counted, so it does not
extend the wait. Counters live per process, so a deployment with several api instances approximates
the limit per instance (DG-API-07; the runbook states this). SOP-4 adds the per-API-client and
per-session limits.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from collections.abc import Hashable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Literal

WINDOW_SECONDS: Final = 60
LOGIN_PER_ADDRESS_AND_EMAIL: Final = 10
LOGIN_PER_ADDRESS: Final = 50
RESET_WINDOW_SECONDS: Final = 3600
RESET_PER_ADDRESS: Final = 20
# Above this many keys, windows whose last hit is older than the window are dropped.
_SWEEP_ABOVE_KEYS: Final = 10_000


@dataclass(slots=True)
class _Window:
    # (epoch second, hits in that second), oldest first.
    seconds: deque[tuple[int, int]] = field(default_factory=deque)
    total: int = 0

    def expire(self, now_second: int, window: int) -> None:
        while self.seconds and self.seconds[0][0] <= now_second - window:
            _, hits = self.seconds.popleft()
            self.total -= hits

    def retry_after(self, now_second: int, window: int) -> int:
        """Seconds until the oldest counted second leaves the window, at least 1."""
        oldest = self.seconds[0][0] if self.seconds else now_second
        return max(1, oldest + window - now_second)

    def add(self, now_second: int) -> None:
        if self.seconds and self.seconds[-1][0] == now_second:
            second, hits = self.seconds[-1]
            self.seconds[-1] = (second, hits + 1)
        else:
            self.seconds.append((now_second, 1))
        self.total += 1


class SlidingWindowLimiter:
    """Counts hits per key over the last ``window_seconds``; thread-safe."""

    def __init__(self, window_seconds: int = WINDOW_SECONDS) -> None:
        self._window_seconds = window_seconds
        self._windows: dict[Hashable, _Window] = {}
        self._lock = threading.Lock()

    def admit(self, limits: tuple[tuple[Hashable, int], ...], now: datetime) -> int | None:
        """Count one hit on every key when all are below their limit and return None; otherwise
        count nothing and return the ``Retry-After`` seconds of the most constrained key."""
        now_second = math.floor(now.timestamp())
        window_seconds = self._window_seconds
        with self._lock:
            if len(self._windows) > _SWEEP_ABOVE_KEYS:
                self._sweep(now_second)
            windows = []
            refused: list[int] = []
            for key, limit in limits:
                window = self._windows.setdefault(key, _Window())
                window.expire(now_second, window_seconds)
                windows.append(window)
                if window.total >= limit:
                    refused.append(window.retry_after(now_second, window_seconds))
            if refused:
                return max(refused)
            for window in windows:
                window.add(now_second)
            return None

    def _sweep(self, now_second: int) -> None:
        for key in list(self._windows):
            window = self._windows[key]
            window.expire(now_second, self._window_seconds)
            if not window.seconds:
                del self._windows[key]


class LoginRateLimiter:
    """The SAR-13 login and MFA buckets over one sliding-window limiter."""

    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter()

    def admit(self, *, address: str, email: str | None, now: datetime) -> int | None:
        """None when the attempt may proceed; otherwise the ``Retry-After`` seconds."""
        limits: tuple[tuple[Hashable, int], ...] = ((("address", address), LOGIN_PER_ADDRESS),)
        if email is not None:
            limits = ((("address-email", address, email), LOGIN_PER_ADDRESS_AND_EMAIL), *limits)
        return self._limiter.admit(limits, now)


class PasswordResetRateLimiter:
    """The T-PLT-42 rule 2 bucket: 20 reset requests per client address per rolling hour."""

    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter(RESET_WINDOW_SECONDS)

    def admit(self, *, address: str, now: datetime) -> bool:
        """True when the request may proceed; a refused request is not counted."""
        return self._limiter.admit(((("address", address), RESET_PER_ADDRESS),), now) is None


# --- SOP-4 request limits (05 SAR-13; 04 API-C-16; REQ-PLT-037) — pure policy, lane P5 ---------
#
# The route middleware of the integration slice classifies each authenticated request, resolves the
# identifiers (client id, session id, api client id and its ``api_client.rate_limit_per_minute``)
# and calls ``RequestRateLimiter.admit``; a refusal is 429 ``rate-limited`` with ``Retry-After`` and
# is not stored as an idempotent response. The client address comes from
# ``erev_api.auth.dependencies.client_ip`` (X-Forwarded-For counted ``EREV_TRUSTED_PROXY_HOPS`` from
# the right); it is not re-implemented here.

RouteClass = Literal["TOKEN", "BROWSER_SESSION", "API_CLIENT"]
TOKEN_PER_CLIENT_ID: Final = 30  # POST /oauth/token, per client id
BROWSER_PER_SESSION: Final = 1_200  # authenticated browser traffic, per session
API_CLIENT_DEFAULT_PER_MINUTE: Final = 600  # api_client.rate_limit_per_minute default
# The sentence ``main.py`` publishes in the OpenAPI ``info.description`` (SOP-4 acceptance).
OPENAPI_RATE_LIMIT_LINE: Final = (
    "Rate limit: 600 requests per minute per API client (default); enforced per api process."
)


def request_limits(
    route_class: RouteClass,
    *,
    client_id: str | None = None,
    session_id: str | None = None,
    api_client_id: str | None = None,
    api_client_limit: int | None = None,
) -> tuple[tuple[Hashable, int], ...]:
    """The SAR-13 bucket (key, limit) of one request: the token endpoint counts per OAuth client
    id, browser traffic per session, API clients per api client at their configured limit
    (default 600). A missing identifier for the class is a programming error, never an open door."""
    if route_class == "TOKEN":
        if not client_id:
            raise ValueError("the token endpoint bucket needs the client id")
        return ((("token", client_id), TOKEN_PER_CLIENT_ID),)
    if route_class == "BROWSER_SESSION":
        if not session_id:
            raise ValueError("the browser bucket needs the session id")
        return ((("session", session_id), BROWSER_PER_SESSION),)
    if not api_client_id:
        raise ValueError("the API client bucket needs the api client id")
    limit = API_CLIENT_DEFAULT_PER_MINUTE if api_client_limit is None else api_client_limit
    if limit < 1:
        raise ValueError("api_client.rate_limit_per_minute is at least 1")
    return ((("api-client", api_client_id), limit),)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int | None  # seconds, set only when refused

    @property
    def headers(self) -> dict[str, str]:
        return {} if self.retry_after is None else {"Retry-After": str(self.retry_after)}


class RequestRateLimiter:
    """The SOP-4 buckets over one sliding-window limiter (one per api process, DG-API-07)."""

    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter()

    def admit(
        self,
        route_class: RouteClass,
        *,
        now: datetime,
        client_id: str | None = None,
        session_id: str | None = None,
        api_client_id: str | None = None,
        api_client_limit: int | None = None,
    ) -> RateLimitDecision:
        """Count the request when it is under its bucket's limit; otherwise count nothing and
        return the ``Retry-After`` seconds (a refused request never extends the wait)."""
        limits = request_limits(
            route_class,
            client_id=client_id,
            session_id=session_id,
            api_client_id=api_client_id,
            api_client_limit=api_client_limit,
        )
        retry_after = self._limiter.admit(limits, now)
        return RateLimitDecision(retry_after is None, retry_after)
