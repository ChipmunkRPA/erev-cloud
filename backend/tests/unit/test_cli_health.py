"""Container entrypoints of ``erev`` (05 CMP-08, CMP-09, DPL-01, DPL-02, DPL-11; DG-KRN-JOB-08;
BUILD_SPEC DEP-1, DEP-2).

``erev worker --check`` reads the heartbeat file; ``erev healthcheck --url`` answers the api image's
health check against a loopback server (DG-TST-15 allows loopback sockets); ``erev api`` serves the
application factory through uvicorn; ``erev migrate`` upgrades to head and then lints, here with
both steps replaced by fakes.
"""

from __future__ import annotations

import io
import os
import threading
from collections.abc import Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from alembic import command as alembic_command
from alembic.config import Config
from erev_api import cli
from erev_api import worker as worker_module
from erev_api.clock import FrozenClock
from erev_api.db import lint as lint_module
from typer.testing import CliRunner


def _check(heartbeat: Path) -> int:
    result = CliRunner().invoke(cli.app, ["worker", "--check", "--heartbeat-file", str(heartbeat)])
    return result.exit_code


def test_worker_check_heartbeat(
    clock: FrozenClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_module, "process_clock", lambda: clock)
    heartbeat = tmp_path / "worker.heartbeat"
    assert _check(heartbeat) == 1, "no heartbeat file yet"

    worker_module.HeartbeatWriter(heartbeat, clock).tick()
    assert _check(heartbeat) == 0, "the worker's own heartbeat is fresh"

    for age_seconds, exit_code in ((0, 0), (15, 0), (59, 0), (60, 1), (61, 1), (3_600, 1)):
        stamp = (clock.now() - timedelta(seconds=age_seconds)).timestamp()
        os.utime(heartbeat, (stamp, stamp))
        assert _check(heartbeat) == exit_code, f"heartbeat {age_seconds} s old"


class _HealthHandler(BaseHTTPRequestHandler):
    """``/api/v1/healthz`` answers 200; any other path answers 503."""

    def do_GET(self) -> None:
        status = 200 if self.path == "/api/v1/healthz" else 503
        body = b'{"status": "ok"}' if status == 200 else b'{"status": "not_ready"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def health_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _closed_loopback_port() -> int:
    """A loopback port whose server was started and closed, so nothing listens on it.

    ``http.server`` binds the port, so the test imports no network module (DG-ARC-12).
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    port = int(server.server_address[1])
    server.server_close()
    return port


def test_healthcheck_url(health_server: str) -> None:
    runner = CliRunner()
    healthy = runner.invoke(cli.app, ["healthcheck", "--url", f"{health_server}/api/v1/healthz"])
    assert healthy.exit_code == 0, healthy.output
    assert "answered 200" in healthy.output

    unhealthy = runner.invoke(cli.app, ["healthcheck", "--url", f"{health_server}/api/v1/readyz"])
    assert unhealthy.exit_code == 1
    assert "answered 503" in unhealthy.output

    port = _closed_loopback_port()
    refused = runner.invoke(
        cli.app, ["healthcheck", "--url", f"http://127.0.0.1:{port}/api/v1/healthz"]
    )
    assert refused.exit_code == 1
    assert "failed" in refused.output

    not_http = runner.invoke(cli.app, ["healthcheck", "--url", "file:///etc/hostname"])
    assert not_http.exit_code == 2


def test_api_serves_the_application_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def run(*args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(uvicorn, "run", run)
    all_interfaces = ".".join(["0"] * 4)
    result = CliRunner().invoke(cli.app, ["api", "--host", all_interfaces, "--port", "8080"])
    assert result.exit_code == 0, result.output
    assert calls == [
        (
            ("erev_api.main:create_app",),
            {"factory": True, "host": all_interfaces, "port": 8080, "access_log": False},
        )
    ]


def test_migrate_upgrades_to_head_then_lints(
    monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    # ``log_stream``: the command installs the logging pipeline on the runner's stderr (05 OPR-20
    # rev 1.53); the fixture puts the process's own back (test_cli_logging covers the lines).
    calls: list[tuple[str, Any]] = []
    findings: list[str] = []

    def upgrade(config: Config, revision: str) -> None:
        calls.append(("upgrade", (Path(str(config.config_file_name)), revision)))

    def lint_as_app(**kwargs: Any) -> list[str]:
        calls.append(("lint", kwargs))
        return list(findings)

    monkeypatch.setattr(alembic_command, "upgrade", upgrade)
    monkeypatch.setattr(lint_module, "lint_as_app", lint_as_app)
    backend = Path(cli.__file__).resolve().parents[1]
    runner = CliRunner()

    result = runner.invoke(cli.app, ["migrate"])
    assert result.exit_code == 0, result.output
    assert calls == [
        ("upgrade", (backend / "alembic.ini", "head")),
        ("lint", {"request_id": "migrate"}),
    ]
    assert "DB-14 lint: 0 findings" in result.output
    # The image keeps alembic.ini beside erev_api, so %(here)s reaches the revisions (DPL-01).
    script_location = Config(str(cli.ALEMBIC_INI)).get_main_option("script_location")
    assert script_location is not None
    assert Path(script_location) == backend / "erev_api" / "db" / "migrations"

    calls.clear()
    findings.append("DB-14 (a) probe finding")
    result = runner.invoke(cli.app, ["migrate"])
    assert result.exit_code == 1
    assert [name for name, _ in calls] == ["upgrade", "lint"]
    assert "DB-14 (a) probe finding" in result.output
    assert "DB-14 lint: 1 findings" in result.output
