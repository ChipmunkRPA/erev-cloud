"""scripts/lane_isolation.py never echoes a DSN (common terms, 2026-09-19 amendment after two
credential exposures). Synthetic credential only; no database, no network."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
FAKE_DSN = "postgresql+psycopg://u:FAKE@127.0.0.1:1/x"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "lane_isolation", ROOT / "scripts" / "lane_isolation.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_redact_dsn_masks_credentials_and_bare_urls(script: ModuleType) -> None:
    masked = script.redact_dsn(f"cannot parse {FAKE_DSN} here; password=FAKE2 given")
    assert "FAKE" not in masked and "u:" not in masked
    assert (
        "127.0.0.1" not in masked or "[REDACTED]@" in masked
    )  # host may survive only behind the mask
    assert "password=[REDACTED]" in masked


def test_failure_is_reported_by_type_only(script: ModuleType) -> None:
    text = script.describe_failure(ValueError(f'missing "=" after "{FAKE_DSN}"'))
    assert text == "connection failed: ValueError"
    assert "FAKE" not in text


def test_run_with_failing_connector_never_echoes_the_dsn(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The regression for the 2026-09-19 exposure: a driver error whose message quotes the DSN."""
    monkeypatch.setenv("LANE_ISOLATION_TEST_DSN", FAKE_DSN)
    lines: list[str] = []

    def connect(dsn: str, **kwargs: object) -> object:
        raise RuntimeError(f'missing "=" after "{dsn}" in connection info string')

    rc = script.main(
        ["--worktree", str(tmp_path), "--dsn-env", "LANE_ISOLATION_TEST_DSN"],
        connect=connect,
        out=lines.append,
    )
    joined = "\n".join(lines)
    assert rc == 2
    assert joined == "connection failed: RuntimeError"
    assert "FAKE" not in joined and "postgresql" not in joined


def test_say_guards_every_line(script: ModuleType) -> None:
    lines: list[str] = []
    script.say(f"note {FAKE_DSN}", lines.append)
    assert lines == ["note postgresql+psycopg://[REDACTED]@127.0.0.1:1/x"]
