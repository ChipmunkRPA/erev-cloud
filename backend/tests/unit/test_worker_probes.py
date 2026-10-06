"""05 OPR-23 rev 1.28 worker probe listener (record §4.34): the two paths, HEAD, 404, status-only
bodies, no per-request logging, the configured-only opening and the CFG-32 aliases."""

from __future__ import annotations

import http.client
import json
import os

import pytest
from erev_api.config import Settings
from erev_api.jobs import probes
from pydantic import ValidationError
from support import log_guard


class Flags:
    ready = False
    live = False


def _request(port: int, method: str, path: str) -> tuple[int, bytes, dict[str, str]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read(), {k.lower(): v for k, v in response.getheaders()}
    finally:
        connection.close()


@pytest.fixture
def server() -> probes.ProbeServer:
    flags = Flags()
    started = probes.ProbeServer(
        host="127.0.0.1", port=0, ready=lambda: flags.ready, live=lambda: flags.live
    )
    started.flags = flags  # type: ignore[attr-defined]
    started.start()
    yield started
    started.stop()


def test_startupz_and_livez_follow_their_callables_and_carry_status_only(
    server: probes.ProbeServer,
) -> None:
    flags = server.flags  # type: ignore[attr-defined]
    status, body, headers = _request(server.port, "GET", "/startupz")
    assert (status, json.loads(body)) == (503, {"status": "starting"})
    assert headers["content-type"] == "application/json" and headers["cache-control"] == "no-store"
    flags.ready = True
    status, body, _ = _request(server.port, "GET", "/startupz")
    assert (status, json.loads(body)) == (200, {"status": "ok"})
    status, body, _ = _request(server.port, "GET", "/livez")
    assert (status, json.loads(body)) == (503, {"status": "stale"})
    flags.live = True
    status, body, _ = _request(server.port, "GET", "/livez")
    assert (status, json.loads(body)) == (200, {"status": "ok"})
    # Status only: no version, key id, tenant or environment detail (team-lead ruling).
    assert set(json.loads(body)) == {"status"}


def test_head_has_no_body_and_other_paths_are_404(server: probes.ProbeServer) -> None:
    status, body, headers = _request(server.port, "HEAD", "/livez")
    assert (status, body) == (503, b"") and int(headers["content-length"]) > 0
    status, body, _ = _request(server.port, "GET", "/api/v1/healthz")
    assert (status, json.loads(body)) == (404, {"status": "not_found"})
    assert "python" not in headers.get("server", "").lower()


def test_requests_are_not_logged_only_listening_and_stopped_are() -> None:
    with log_guard.capture() as events:
        started = probes.ProbeServer(
            host="127.0.0.1", port=0, ready=lambda: True, live=lambda: True
        )
        started.start()
        for _ in range(3):
            _request(started.port, "GET", "/startupz")
        started.stop()
    mine = [
        e["event"]
        for e in events
        if e.get("logger") == probes._LOGGER or str(e.get("event", "")).startswith("worker_probes.")
    ]
    assert mine == ["worker_probes.listening", "worker_probes.stopped"]


# Fixture placeholders, not credentials (the test_config / doctor-test pattern): Settings from the
# environment alone, the developer's .env ignored, so the CFG-32 aliases are read as deployed.
_MASTER_KEYS = {
    "EREV_ENCRYPTION_KEY": "0123456789abcdef" * 4,
    "EREV_AUDIT_HMAC_MASTER_KEY": "fedcba9876543210" * 4,
    "EREV_SECURITY_EVENT_HMAC_KEY": "13579bdf02468ace" * 4,
}
_DEV_ENVIRONMENT = {
    **_MASTER_KEYS,
    "EREV_ENV": "dev",
    "EREV_DB_OWNER_URL": "postgresql://erev_owner:fixture-placeholder@127.0.0.1:5432/erev",
    "EREV_DB_APP_URL": "postgresql://erev_app:fixture-placeholder@127.0.0.1:5432/erev",
    "EREV_TEST_DB_OWNER_URL": "postgresql://erev_owner:fixture-placeholder@127.0.0.1:5432/erev_test",
    "EREV_TEST_DB_APP_URL": "postgresql://erev_app:fixture-placeholder@127.0.0.1:5432/erev_test",
    "EREV_E2E_DB_OWNER_URL": "postgresql://erev_owner:fixture-placeholder@127.0.0.1:5432/erev_e2e",
    "EREV_E2E_DB_APP_URL": "postgresql://erev_app:fixture-placeholder@127.0.0.1:5432/erev_e2e",
}


def _settings_from_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for name in list(os.environ):
        if name.startswith("EREV_") or name in ("ANTHROPIC_API_KEY", "PORT"):
            monkeypatch.delenv(name)
    for name, value in {**_DEV_ENVIRONMENT, **overrides}.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_the_listener_opens_only_when_a_port_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    assert probes.probe_server_if_configured(None, ready=lambda: True, live=lambda: True) is None
    assert _settings_from_env(monkeypatch).worker_probe_port is None
    # PORT is the variable Cloud Run injects; EREV_WORKER_PROBE_PORT wins when both are set.
    assert _settings_from_env(monkeypatch, PORT="8080").worker_probe_port == 8080
    both = _settings_from_env(monkeypatch, PORT="8080", EREV_WORKER_PROBE_PORT="9090")
    assert both.worker_probe_port == 9090
    with pytest.raises(ValidationError):  # CFG-32 range (1, 65535)
        _settings_from_env(monkeypatch, EREV_WORKER_PROBE_PORT="70000")
