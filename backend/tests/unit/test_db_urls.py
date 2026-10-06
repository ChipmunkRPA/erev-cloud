"""Database URLs: engine creation logs host, port and database, never credentials (DG-ENV-11;
BUILD_SPEC FND-5); one allow-list refuses redirecting query parameters (DG-ENV-13; EKC-7b)."""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest
import structlog
from erev_api import config
from erev_api.config import Settings, SettingsError
from erev_api.db import session
from erev_api.db.session import APP_ROLE, OWNER_ROLE, build_engine
from erev_api.logging import configure_logging

CHECK_ENV = Path(__file__).resolve().parents[3] / "scripts" / "check_env.py"
PLAIN_URL = "postgresql://u:p@127.0.0.1:5432/erev_test"

APP_USER = "erev_app"
OWNER_USER = "erev_owner"
APP_CREDENTIAL = "unit-app-credential"
OWNER_CREDENTIAL = "unit-owner-credential"
ENVIRONMENT = {
    "EREV_ENV": "test",
    "EREV_TEST_DB_OWNER_URL": f"postgresql://{OWNER_USER}:{OWNER_CREDENTIAL}@127.0.0.1:5432/erev_test",
    "EREV_TEST_DB_APP_URL": f"postgresql://{APP_USER}:{APP_CREDENTIAL}@127.0.0.1:5432/erev_test",
    "EREV_ENCRYPTION_KEY": "0123456789abcdef" * 4,
    "EREV_AUDIT_HMAC_MASTER_KEY": "fedcba9876543210" * 4,
    "EREV_SECURITY_EVENT_HMAC_KEY": "13579bdf02468ace" * 4,
}


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    """A fresh JSON pipeline writing to a buffer; the previous pipeline is restored afterwards."""
    saved = structlog.get_config()
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    stream = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=stream)
    try:
        yield stream
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        structlog.configure(
            processors=list(saved["processors"]),
            context_class=saved["context_class"],
            wrapper_class=saved["wrapper_class"],
            logger_factory=saved["logger_factory"],
            cache_logger_on_first_use=saved["cache_logger_on_first_use"],
        )


def _check_env() -> ModuleType:
    # scripts/check_env.py is loaded by path: it must stay importable without the venv (setup.sh).
    spec = importlib.util.spec_from_file_location("check_env_urls", CHECK_ENV)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS: tuple[Callable[[str], str], ...] = (config.database_of_url, session.database_of)


def test_dg_env_13_query_parameters_cannot_redirect_database() -> None:
    check_env = _check_env()
    for parameter in ("dbname", "service", "servicefile"):
        url = f"{PLAIN_URL}?{parameter}={'postgres' if parameter == 'dbname' else 'x'}"
        for helper in HELPERS:
            with pytest.raises(SettingsError) as excinfo:
                helper(url)
            assert f"query parameter {parameter}," in str(excinfo.value)
            assert "p@" not in str(excinfo.value)
        error = check_env.check_database_allowed(url)
        assert error is not None and error.endswith(f"query parameter {parameter}")
        assert "p@" not in error

    accepted = f"{PLAIN_URL}?sslmode=disable"
    assert [helper(accepted) for helper in HELPERS] == ["erev_test", "erev_test"]
    assert check_env.check_database_allowed(accepted) is None


def test_dg_env_13_allow_list_helpers_agree() -> None:
    check_env = _check_env()
    expected = {
        "erev": "erev",
        "erev_test": "erev_test",
        "erev_e2e": "erev_e2e",
        "erev_rv_x%5Fy": "erev_rv_x_y",
        "postgres": None,
        "erev_test?dbname=postgres": None,
    }
    for path, database in expected.items():
        url = f"postgresql://u:p@127.0.0.1:5432/{path}"
        outcomes: list[str | None] = []
        for helper in HELPERS:
            try:
                outcomes.append(helper(url))
            except SettingsError:
                outcomes.append(None)
        allowed = check_env.check_database_allowed(url) is None
        outcomes.append(check_env.database_name(url) if allowed else None)
        assert outcomes == [database] * 3, (path, outcomes)
    assert check_env.DATABASE_ALLOW_LIST.pattern == config.ALLOWED_DATABASE.pattern
    assert check_env.REDIRECTING_QUERY_PARAMETERS == config.REDIRECTING_QUERY_PARAMETERS


def test_dg_env_11_logged_url_has_no_credentials(
    settings: Settings, log_stream: io.StringIO
) -> None:
    engines = [
        build_engine(settings.app_database_url(), role=APP_ROLE, component="tests"),
        build_engine(settings.owner_database_url(), role=OWNER_ROLE, component="tests"),
    ]
    for engine in engines:
        engine.dispose()

    lines = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    created = [line for line in lines if line["event"] == "db.engine_created"]
    assert [line["engine"] for line in created] == ["app", "owner"]
    for line in created:
        assert (line["host"], line["port"], line["database"]) == ("127.0.0.1", 5432, "erev_test")
    text = log_stream.getvalue()
    leaked = [
        word for word in (APP_USER, OWNER_USER, APP_CREDENTIAL, OWNER_CREDENTIAL) if word in text
    ]
    assert leaked == []
