"""The perf harness's httpx session against ``api-perf`` (dev-guide DG-PERF-03): password
sign-in, the TOTP step, the CSRF header on every command, tenant selection, polling. Lives in
the shared test support package because DG-ARC-12 allows ``httpx`` only in adapters and test
support; ``perf.support.client`` re-exports it. Authored for ``make perf``; NOT RUN in the lane.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final, NamedTuple

import httpx

API_PREFIX: Final = "/api/v1"
CSRF_HEADER: Final = "X-CSRF-Token"
DEFAULT_TIMEOUT: Final = 30.0


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, response: httpx.Response) -> None:
        super().__init__(f"{method} {path} → {response.status_code}: {response.text[:400]}")
        self.status_code = response.status_code
        self.body = response.text


class PerfClient:
    """One signed-in persona. ``base_url`` is ``http://127.0.0.1:8199``."""

    def __init__(self, base_url: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.csrf_token: str | None = None

    def close(self) -> None:
        self.http.close()

    # -- session ------------------------------------------------------------------------------

    def sign_in(
        self, email: str, password: str, totp_code: Callable[[], str] | None
    ) -> Mapping[str, Any]:
        """``POST /session/login`` then, when the session asks for it, ``POST /session/mfa`` with a
        current TOTP code (the perf personas hold MFA-requiring permissions)."""
        body = self.post("/session/login", {"email": email, "password": password})
        self.csrf_token = str(body["csrf_token"])
        if body.get("mfa_required") or body.get("mfa_enrolment_required"):
            if totp_code is None:
                raise RuntimeError(f"{email}: MFA required but no TOTP secret was given")
            body = self.post("/session/mfa", {"code": totp_code()})
            self.csrf_token = str(body.get("csrf_token", self.csrf_token))
        return body

    def select_tenant(self, tenant_id: str) -> Mapping[str, Any]:
        """``POST /session/tenant`` — the perf sandbox, never ``perf-volume`` (DG-PERF-06)."""
        body = self.post("/session/tenant", {"tenant_id": tenant_id})
        self.csrf_token = str(body.get("csrf_token", self.csrf_token))
        return body

    # -- requests -----------------------------------------------------------------------------

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.csrf_token:
            headers[CSRF_HEADER] = self.csrf_token
        if extra:
            headers.update(extra)
        return headers

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        response = self.http.get(API_PREFIX + path, params=params, headers=self._headers())
        if response.status_code >= 400:
            raise ApiError("GET", path, response)
        return response.json()

    def get_response(self, path: str, params: Mapping[str, Any] | None = None) -> httpx.Response:
        return self.http.get(API_PREFIX + path, params=params, headers=self._headers())

    def post(
        self,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        extra: dict[str, str] = {}
        if if_match is not None:
            extra["If-Match"] = if_match
        if idempotency_key is not None:
            extra["Idempotency-Key"] = idempotency_key
        response = self.http.post(API_PREFIX + path, json=body or {}, headers=self._headers(extra))
        if response.status_code >= 400:
            raise ApiError("POST", path, response)
        return response.json() if response.content else {}

    def upload(
        self,
        path: str,
        *,
        fields: Mapping[str, str],
        filename: str,
        content: bytes,
        media_type: str,
    ) -> Any:
        """``POST path`` as multipart form data: the form ``fields`` and the part ``file`` (04
        API-R ``POST /files``; the evidence document of a manual event, BUILD_SPEC CTR-6)."""
        response = self.http.post(
            API_PREFIX + path,
            data=dict(fields),
            files={"file": (filename, content, media_type)},
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise ApiError("POST", path, response)
        return response.json()

    def poll(
        self,
        path: str,
        done: Callable[[Mapping[str, Any]], bool],
        *,
        every: float = 2.0,
        timeout: float = 3600.0,
    ) -> Mapping[str, Any]:
        """``GET path`` every ``every`` seconds until ``done`` (DG-PERF-02: every 2 seconds)."""
        deadline = time.monotonic() + timeout
        while True:
            body = self.get(path)
            if done(body):
                return body
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{path} did not finish within {timeout:.0f} s")
            time.sleep(every)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class PerfClients(NamedTuple):
    """The signed-in harness personas (Codex 0105 PERSONA-1 split): the accountant prepares
    (appends, policy authoring, journal submits), the controller runs closes and exports, the
    reviewer approves. Reads may use any of them."""

    accountant: PerfClient
    controller: PerfClient
    reviewer: PerfClient
