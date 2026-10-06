"""DG-API-09 / D-72 (BUILD_SPEC DIN-12 ``test_mock_routes_absent_in_production``; F-DIN ruling (d)):
the mock adapter servers ship inside the one backend package but a production-profile app mounts no
``/api/v1/__mocks__`` route and its OpenAPI document never lists one; a test-profile app mounts
them all. ``adapters.mocks.mounted_mock_routes`` is the predicate (reusable by the P4 doctor). The
production settings here are synthetic values that are never connected to."""

from __future__ import annotations

import os

import pytest
from erev_api.adapters import mocks
from erev_api.config import Environment, Settings
from erev_api.main import create_app

SYNTHETIC_KEY = "0" * 64
SYNTHETIC_DB = "postgresql://erev_none:none@127.0.0.1:1/erev_arch_test_none"


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: str, env: str) -> Settings:
    for name in list(os.environ):
        if name.startswith("EREV_"):
            monkeypatch.delenv(name)
    values = {
        "EREV_ENV": env,
        "EREV_DB_OWNER_URL": SYNTHETIC_DB,
        "EREV_DB_APP_URL": SYNTHETIC_DB,
        "EREV_TEST_DB_OWNER_URL": SYNTHETIC_DB,
        "EREV_TEST_DB_APP_URL": SYNTHETIC_DB,
        "EREV_ENCRYPTION_KEY": SYNTHETIC_KEY,
        "EREV_AUDIT_HMAC_MASTER_KEY": SYNTHETIC_KEY,
        "EREV_SECURITY_EVENT_HMAC_KEY": SYNTHETIC_KEY,
        # 05 KEY-03 (rev 1.17, lane P2): production pins the platform security key version.
        "EREV_SECURITY_HMAC_SECRET_VERSION": "1",
        "EREV_FILE_ROOT": tmp_path,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_dg_api_09_production_app_mounts_no_mock_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    settings = _settings(monkeypatch, str(tmp_path), "production")
    assert settings.env is Environment.PRODUCTION
    app = create_app(settings)
    assert mocks.mounted_mock_routes(app) == []
    assert not any(path.startswith(mocks.MOCKS_PREFIX) for path in app.openapi()["paths"])


def test_dg_api_09_test_app_mounts_every_mock_out_of_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    settings = _settings(monkeypatch, str(tmp_path), "test")
    app = create_app(settings)
    mounted = mocks.mounted_mock_routes(app)
    for adapter in ("oidc", "salesforce", "stripe", "netsuite", "qbo"):  # qbo: CLO-15
        assert any(path.startswith(f"{mocks.MOCKS_PREFIX}/{adapter}/") for path in mounted), adapter
    assert f"{mocks.MOCKS_PREFIX}/__admin/reset" in mounted
    assert not any(path.startswith(mocks.MOCKS_PREFIX) for path in app.openapi()["paths"])
