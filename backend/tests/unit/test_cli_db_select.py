"""``erev --db erev_rv_*`` binding (DG-ENV-13; RB-06; independent review P6-R1 residual of
2026-09-19): the direct ``verify``/``doctor`` entry points bind the owner and app URLs to one host,
port and database and check the server identity they reach, exactly as the drill scripts do. A
shared database name alone never selects a clone.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from erev_api import cli
from erev_api.config import SettingsError, get_settings
from erev_api.controls import recovery_preflight as pf

SYNTHETIC = "SYNTHETIC_ONLY"
CLONE = "erev_rv_unit"
IDENTITY = [CLONE, "16401", "2026-09-19 10:00:00+00", "127.0.0.1", "1"]


def _url(role: str, host: str = "127.0.0.1", port: int = 1, database: str = CLONE) -> str:
    return f"postgresql://{role}:{SYNTHETIC}@{host}:{port}/{database}"


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    monkeypatch.setenv("EREV_ENV", "dev")
    get_settings.cache_clear()
    try:
        yield monkeypatch
    finally:
        get_settings.cache_clear()


def _stub(tmp_path: Path, rows: dict[str, list[str]]) -> str:
    path = tmp_path / "identity.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return str(path)


def _select(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    try:
        cli._select_database(CLONE)
    except typer.Exit as exit_:
        return exit_.exit_code, capsys.readouterr().out
    return 0, capsys.readouterr().out


def test_db_select_binds_host_port_database_and_identity(
    fresh_settings: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fresh_settings.setenv("EREV_DB_OWNER_URL", _url("erev_owner"))
    fresh_settings.setenv("EREV_DB_APP_URL", _url("erev_app"))
    both = {"EREV_DB_OWNER_URL": IDENTITY, "EREV_DB_APP_URL": IDENTITY}
    fresh_settings.setenv(pf.IDENTITY_STUB_NAME, _stub(tmp_path, both))
    assert _select(capsys) == (0, "")

    # The same database name on another host or port is not the same database.
    for variable, url in (
        ("EREV_DB_APP_URL", _url("erev_app", host="127.0.0.2")),
        ("EREV_DB_APP_URL", _url("erev_app", port=2)),
    ):
        fresh_settings.setenv(variable, url)
        get_settings.cache_clear()
        code, out = _select(capsys)
        assert code == 2 and "must reach the same server" in out and SYNTHETIC not in out, out
    fresh_settings.setenv("EREV_DB_APP_URL", _url("erev_app"))
    get_settings.cache_clear()

    # A routing query parameter is refused by the settings themselves (DG-ENV-13), before the
    # binding runs.
    fresh_settings.setenv("EREV_DB_APP_URL", _url("erev_app") + "?dbname=erev")
    get_settings.cache_clear()
    with pytest.raises(SettingsError, match="query parameter dbname"):
        cli._select_database(CLONE)
    fresh_settings.setenv("EREV_DB_APP_URL", _url("erev_app"))
    get_settings.cache_clear()

    # Both URLs name the clone but the servers reached differ, or serve another database.
    other = [CLONE, "16402", "2026-09-19 10:00:01+00", "127.0.0.1", "1"]
    fresh_settings.setenv(
        pf.IDENTITY_STUB_NAME,
        _stub(tmp_path, {"EREV_DB_OWNER_URL": IDENTITY, "EREV_DB_APP_URL": other}),
    )
    code, out = _select(capsys)
    assert code == 2 and "reached another server or database than" in out, out
    elsewhere = ["erev", "16400", "2026-09-19 10:00:00+00", "127.0.0.1", "1"]
    fresh_settings.setenv(
        pf.IDENTITY_STUB_NAME,
        _stub(tmp_path, {"EREV_DB_OWNER_URL": elsewhere, "EREV_DB_APP_URL": elsewhere}),
    )
    code, out = _select(capsys)
    assert code == 2 and f"serves erev, not {CLONE}" in out, out


def test_db_select_requires_both_urls_to_name_the_clone(
    fresh_settings: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fresh_settings.setenv("EREV_DB_OWNER_URL", _url("erev_owner", database="erev"))
    fresh_settings.setenv("EREV_DB_APP_URL", _url("erev_app", database="erev"))
    fresh_settings.setenv(pf.IDENTITY_STUB_NAME, _stub(tmp_path, {}))
    code, out = _select(capsys)
    assert code == 2 and "must name that database, not erev (DG-ENV-13)" in out
    # Only one of the two names the clone: refused as two endpoints, before any connection.
    fresh_settings.setenv("EREV_DB_OWNER_URL", _url("erev_owner"))
    get_settings.cache_clear()
    code, out = _select(capsys)
    assert code == 2 and "must reach the same server" in out


def test_db_select_refuses_the_identity_stub_outside_test_and_dev(
    fresh_settings: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fresh_settings.setenv("EREV_DB_OWNER_URL", _url("erev_owner"))
    fresh_settings.setenv("EREV_DB_APP_URL", _url("erev_app"))
    both = {"EREV_DB_OWNER_URL": IDENTITY, "EREV_DB_APP_URL": IDENTITY}
    fresh_settings.setenv(pf.IDENTITY_STUB_NAME, _stub(tmp_path, both))
    # The caller's EREV_ENV is production: the stub is a hard error before any connection, even
    # though --db erev_rv_* switches the process to dev.
    fresh_settings.setenv("EREV_ENV", "production")
    get_settings.cache_clear()
    code, out = _select(capsys)
    assert code == 2 and "EREV_RECOVERY_IDENTITY_STUB is set under EREV_ENV=production" in out
