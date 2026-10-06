"""API-R-53 health routes (05 OPR-23; dev-guide DG-API-08; BUILD_SPEC FND-10, BS1-D-10)."""

from __future__ import annotations

from typing import NoReturn

import pytest
from erev_api.api.v1 import health
from erev_api.auth import security_events
from erev_api.config import Settings
from erev_api.db import session as db_session
from erev_api.main import create_app
from support.db import TestDatabase
from support.http import call


def test_dg_api_08_healthz_without_database(
    app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> NoReturn:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db_session, "app_engine", unavailable)
    response = call(create_app(app_settings), "GET", "/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_opr_23_readyz_all_checks_pass(committed_db: TestDatabase, app_settings: Settings) -> None:
    response = call(create_app(app_settings), "GET", "/api/v1/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "migrations": "ok", "files": "ok", "keys": "ok"},
    }
    assert (app_settings.file_root / health.PROBE_KEY).read_bytes() == health.PROBE_BYTES


def test_readyz_not_ready_when_head_differs(
    committed_db: TestDatabase, app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "code_head", lambda: "9999")
    response = call(create_app(app_settings), "GET", "/api/v1/readyz")
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "not_ready", "failed": ["migrations"]}


def test_readyz_keys_refuses_a_stale_pin(
    committed_db: TestDatabase, app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 KEY-03 rev 1.17, DG-KRN-AUD-08: `keys` covers the admission too — a chain head signed
    under a newer pin fails it although the provider serves the pinned version."""
    ahead = security_events.ChainHead(hmac="ab" * 32, key_id="security-hmac:2", canonical_version=2)
    monkeypatch.setattr(security_events, "chain_head", lambda bind: ahead)
    response = call(create_app(app_settings), "GET", "/api/v1/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "failed": ["keys"]}


def test_readyz_reports_every_failed_check(
    app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every failed check is named. `keys` is among them (05 OPR-23 provisional row; Codex
    terminal review of 4cba4f0a): the check reads the chain head for the DG-KRN-AUD-08 admission,
    which the unavailable database prevents, and it is never skipped or narrowed."""

    def unavailable() -> NoReturn:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db_session, "app_engine", unavailable)
    blocked = app_settings.model_copy(update={"file_root": app_settings.file_root / "absent"})
    blocked.file_root.parent.mkdir(parents=True)
    blocked.file_root.write_bytes(b"a file where the store root should be")
    response = call(create_app(blocked), "GET", "/api/v1/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "failed": ["database", "migrations", "files", "keys"],
    }
