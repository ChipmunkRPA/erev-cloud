"""The ``erev`` commands' logging pipeline and their production gate (05 OPR-20, SAR-40 rev 1.53;
DG-LOG-01, DG-KRN-CFG-02, DG-KRN-TEN-04; rulings R-37 (c) and R-53 (6)).

Two findings of the first deployment drills. ``erev migrate`` and the ``db`` commands installed no
logging pipeline, so a production migrate job printed structlog's default console lines on stdout,
outside the hygiene processor, and dropped Alembic's own lines. And an operator command could
provision a workspace under placeholder master keys before the first start: only the api and the
worker evaluated the startup subset.
"""

from __future__ import annotations

import ast
import inspect
import io
import json
import logging
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import typer
from alembic import command as alembic_command
from click.testing import Result
from erev_api import cli
from erev_api import config as config_module
from erev_api.auth import keyring as keyring_module
from erev_api.config import MASTER_KEY_FIELDS, Environment, Settings
from erev_api.controls import doctor as doctor_module
from erev_api.controls import release
from erev_api.db import lint as lint_module
from erev_api.domain.platform import provisioning
from erev_api.files import store as store_module
from erev_api.logging import get_logger
from pydantic import SecretStr
from support.production import production_settings
from typer.testing import CliRunner

# Commands that may install no pipeline: they open no database and emit no log line, or (api,
# worker) their own composition root installs it on stdout. A new command is classified here or
# calls ``_cli_settings()`` / ``cli_services()``.
QUIET = {
    "version",
    "healthcheck",
    "registry-seed",
    "openapi",
    "controls-report",
    "api",
    "worker",
}
# The commands that call ``_cli_settings()`` themselves, and the first work each does after it.
DIRECT = {
    "migrate": "command.upgrade(",
    "db lint": "lint_as_app(",
    "db reset": "build_engine(",
    "db revision": "write_revision(",
}
SERVICES = {
    "doctor",
    "verify",
    "restore-applied",
    "operator create",
    "support-grant request",
    "tenant create",
    "tenant resend-invitation",
    "idp list",
    "idp create",
    "idp invite",
    "idp domains",
    "idp disable",
    "idp enable",
    "idp end-sessions",
    "seed demo",
    "perf seed",
}
FAKE = (
    "FAIL email-backend: EREV_EMAIL_BACKEND is fake; production requires smtp (05 CFG-17, SAR-40)"
)
PLACEHOLDERS = tuple("0" * 63 + digit for digit in "123")
TENANT_CREATE = [
    "tenant",
    "create",
    "--code",
    "gate-probe",
    "--name",
    "Gate Probe",
    "--reporting-currency",
    "USD",
    "--admin",
    "admin@erev.test",
]


@pytest.fixture(autouse=True)
def _environment_remembered_before() -> Iterator[None]:
    """``cli_services`` records the environment of the settings it read (05 REL-03); a test that
    runs it under production settings puts the process's own back."""
    before = release.current_environment()
    yield
    release.remember_environment(before)


def _commands(app: typer.Typer, prefix: str = "") -> Iterator[tuple[str, Callable[..., object]]]:
    for info in app.registered_commands:
        assert info.callback is not None
        yield prefix + (info.name or info.callback.__name__.replace("_", "-")), info.callback
    for group in app.registered_groups:
        assert group.typer_instance is not None and group.name
        yield from _commands(group.typer_instance, f"{prefix}{group.name} ")


def test_every_command_installs_the_pipeline_or_is_on_the_list() -> None:
    sources = {name: inspect.getsource(callback) for name, callback in _commands(cli.app)}
    installs = {
        name
        for name, source in sources.items()
        if re.search(r"\b(?:cli_services|_cli_settings)\(", source)
    }
    assert set(sources) - installs == QUIET
    assert installs >= set(DIRECT) | SERVICES
    for name, first_work in DIRECT.items():
        source = sources[name]
        assert source.count("_cli_settings()") == 1, name
        assert source.index("_cli_settings()") < source.index(first_work), name
    # The one installer: the CFG-22 level and format, on stderr.
    installer = inspect.getsource(cli._cli_settings)
    assert (
        "configure_logging(level=settings.log_level, fmt=settings.log_format, stream=sys.stderr)"
        in installer
    )
    assert "_cli_settings()" in inspect.getsource(cli.cli_services)
    assert "configure_logging" not in inspect.getsource(cli.cli_services)


def test_only_doctor_and_verify_build_ungated_services() -> None:
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    gated: set[str] = set()
    ungated: set[str] = set()
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            if not (isinstance(call.func, ast.Name) and call.func.id == "cli_services"):
                continue
            assert not call.args, function.name
            if call.keywords:
                (keyword,) = call.keywords
                assert (keyword.arg, ast.literal_eval(keyword.value)) == ("gated", False)
                ungated.add(function.name)
            else:
                gated.add(function.name)
    assert ungated == {"doctor", "verify_command"}
    assert gated == {
        "restore_applied_command",
        "operator_create",
        "support_grant_request",
        "tenant_create",
        "tenant_resend_invitation",
        "idp_list",
        "idp_create",
        "idp_invite",
        "idp_domains",
        "idp_disable",
        "idp_enable",
        "idp_end_sessions",
        "seed_demo_command",
        "perf_seed_command",
    }
    assert inspect.signature(cli.cli_services).parameters["gated"].default is True


@pytest.fixture
def settings_of(
    monkeypatch: pytest.MonkeyPatch, app_settings: Settings
) -> Callable[[Settings], Settings]:
    """Make a command read the given settings, with the production log format and level."""

    def install(settings: Settings) -> Settings:
        chosen = settings.model_copy(update={"log_format": "json", "log_level": "INFO"})
        monkeypatch.setattr(config_module, "get_settings", lambda: chosen)
        return chosen

    return install


def test_migrate_logs_through_the_pipeline_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    app_settings: Settings,
    settings_of: Callable[[Settings], Settings],
    log_stream: io.StringIO,
) -> None:
    """Alembic's record and a domain event leave ``erev migrate`` as scrubbed JSON lines on stderr;
    stdout carries the command's one line. ``log_stream`` holds the pipeline that was installed
    before the command ran (nothing may reach it) and restores the process's own afterwards."""
    settings_of(app_settings)

    def upgrade(config: object, revision: str) -> None:
        logging.getLogger("alembic.runtime.migration").info(
            "Running upgrade 0072 -> 0073, probe revision"
        )
        get_logger("erev_api.db.session").info(
            "db.engine_created",
            component="cli",
            api_key_id="k-123456",
            contact="someone@erev.example",
        )

    monkeypatch.setattr(alembic_command, "upgrade", upgrade)
    monkeypatch.setattr(lint_module, "lint_as_app", lambda **_: [])
    result = CliRunner().invoke(cli.app, ["migrate"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "DB-14 lint: 0 findings\n"
    lines = [json.loads(line) for line in result.stderr.splitlines()]
    assert [(line["logger"], line["level"], line["event"]) for line in lines] == [
        ("alembic.runtime.migration", "info", "Running upgrade 0072 -> 0073, probe revision"),
        ("erev_api.db.session", "info", "db.engine_created"),
    ]
    assert all({"ts", "request_id", "tenant_id"} <= line.keys() for line in lines)
    assert lines[1]["component"] == "cli"
    assert "api_key_id" not in lines[1] and "contact" not in lines[1]
    assert "k-123456" not in result.output and "someone@erev.example" not in result.output
    assert log_stream.getvalue() == ""


def test_db_lint_logs_on_stderr_and_prints_its_line_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
    app_settings: Settings,
    settings_of: Callable[[Settings], Settings],
    log_stream: io.StringIO,
) -> None:
    settings_of(app_settings)

    def lint_as_app(**_: object) -> list[str]:
        get_logger("erev_api.db.lint").warning("db.lint_probe", status="checked")
        return ["DB-14 (a) probe finding"]

    monkeypatch.setattr(lint_module, "lint_as_app", lint_as_app)
    result = CliRunner().invoke(cli.app, ["db", "lint"])
    assert result.exit_code == 1
    assert result.stdout == "DB-14 (a) probe finding\nDB-14 lint: 1 findings\n"
    (line,) = [json.loads(line) for line in result.stderr.splitlines()]
    assert (line["event"], line["level"], line["status"]) == ("db.lint_probe", "warning", "checked")


def _never(name: str) -> Callable[..., object]:
    def called(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"{name} was reached by a refused command")

    return called


@pytest.fixture
def no_composition(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused command builds no key ring and no file store, and provisions nothing."""
    monkeypatch.setattr(keyring_module, "build_keyring", _never("build_keyring"))
    monkeypatch.setattr(store_module, "build_file_store", _never("build_file_store"))
    monkeypatch.setattr(provisioning, "provision_tenant", _never("provision_tenant"))


def _refused(result: Result, *findings: str) -> None:
    assert result.exit_code == cli.STARTUP_REFUSED_EXIT == 3, result.output
    assert result.stdout == ""
    plain = [line for line in result.stderr.splitlines() if not line.startswith("{")]
    assert plain == [*findings, cli.STARTUP_REFUSED]
    logged = [json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")]
    assert [(line["event"], line["level"], line["findings"]) for line in logged] == [
        ("startup.refused", "error", list(findings))
    ]


def test_an_operator_command_refuses_under_production_when_the_subset_fails(
    app_settings: Settings,
    settings_of: Callable[[Settings], Settings],
    no_composition: None,
    log_stream: io.StringIO,
) -> None:
    """``erev tenant create`` with the fake email backend, then with the placeholder master keys
    the example file once shipped: FAIL lines and the closing line on stderr, exit 3, nothing on
    stdout, no key ring, no provisioning."""
    settings_of(production_settings(app_settings, email_backend="fake"))
    _refused(CliRunner().invoke(cli.app, TENANT_CREATE), FAKE)

    keys = {
        field: SecretStr(value)
        for field, value in zip(MASTER_KEY_FIELDS, PLACEHOLDERS, strict=True)
    }
    settings_of(production_settings(app_settings, **keys))
    result = CliRunner().invoke(cli.app, TENANT_CREATE)
    _refused(
        result,
        *(
            f"FAIL master-keys: {name} is a placeholder, not a generated key: fewer than 16 "
            "distinct byte values (05 CFG-26)"
            for name in (
                "EREV_ENCRYPTION_KEY",
                "EREV_AUDIT_HMAC_MASTER_KEY",
                "EREV_SECURITY_EVENT_HMAC_KEY",
            )
        ),
    )
    assert all(value not in result.output for value in PLACEHOLDERS), "a finding names no value"


@pytest.mark.parametrize(
    "arguments",
    [
        ["operator", "create", "--email", "ops@erev.test", "--name", "Ops"],
        [
            "support-grant",
            "request",
            "--tenant",
            "gate-probe",
            "--operator",
            "ops@erev.test",
            "--reason",
            "gate probe reason",
            "--from",
            "2026-09-30T00:00:00Z",
            "--to",
            "2026-09-30T01:00:00Z",
        ],
        [
            "idp",
            "create",
            "--code",
            "probe",
            "--kind",
            "oidc",
            "--name",
            "Probe",
            "--issuer-url",
            "https://idp.erev.example",
            "--client-id",
            "client",
            "--email-domain",
            "erev.example",
        ],
        ["idp", "list"],
        ["idp", "invite", "--code", "probe", "--email", "admin@erev.test"],
        ["idp", "domains", "--code", "probe", "--add", "erev.example"],
        ["idp", "disable", "--code", "probe"],
        ["idp", "enable", "--code", "probe"],
        ["idp", "end-sessions", "--code", "probe"],
        ["restore-applied", "--instant", "2026-09-30T00:00:00Z", "--backup", "b-1"],
        ["tenant", "resend-invitation", "--code", "gate-probe", "--admin", "admin@erev.test"],
        ["seed", "demo"],
        ["perf", "seed"],
    ],
    ids=lambda arguments: " ".join(arguments[:2]),
)
def test_every_gated_command_refuses_before_it_asks_or_connects(
    arguments: list[str],
    app_settings: Settings,
    settings_of: Callable[[Settings], Settings],
    no_composition: None,
    log_stream: io.StringIO,
) -> None:
    settings_of(production_settings(app_settings, email_backend="fake"))
    # No input is offered: `operator create` would fail on its password prompt (exit 1, "Aborted")
    # if it asked before the gate.
    result = CliRunner().invoke(cli.app, arguments)
    _refused(result, FAKE)
    assert "Password" not in result.output


def test_the_gate_applies_to_production_only_and_not_to_a_sound_configuration(
    monkeypatch: pytest.MonkeyPatch,
    app_settings: Settings,
    settings_of: Callable[[Settings], Settings],
    log_stream: io.StringIO,
) -> None:
    built: list[Environment] = []

    def build_keyring(settings: Settings) -> object:
        built.append(settings.env)
        return object()

    monkeypatch.setattr(keyring_module, "build_keyring", build_keyring)
    monkeypatch.setattr(keyring_module, "build_tenant_key_provisioner", lambda *_: None)
    monkeypatch.setattr(store_module, "build_file_store", lambda _: object())
    # The local environments require the fake backend and are never refused.
    assert app_settings.env is Environment.TEST and app_settings.email_backend == "fake"
    settings_of(app_settings)
    assert cli.cli_services().env is Environment.TEST
    # A sound production configuration passes the gate.
    settings_of(production_settings(app_settings))
    assert cli.cli_services().env is Environment.PRODUCTION
    # A failing one is refused, unless the caller is doctor or verify.
    settings_of(production_settings(app_settings, email_backend="fake"))
    with pytest.raises(typer.Exit) as refused:
        cli.cli_services()
    assert refused.value.exit_code == 3
    assert cli.cli_services(gated=False).env is Environment.PRODUCTION
    assert built == [Environment.TEST, Environment.PRODUCTION, Environment.PRODUCTION]


def test_doctor_still_runs_and_reports_under_a_failing_subset(
    monkeypatch: pytest.MonkeyPatch,
    app_settings: Settings,
    settings_of: Callable[[Settings], Settings],
    log_stream: io.StringIO,
) -> None:
    """``erev doctor`` is how the operator finds the fault: the gate does not apply, the checks
    run, and the command ends with the doctor's own exit code."""
    settings_of(production_settings(app_settings, email_backend="fake"))
    monkeypatch.setattr(keyring_module, "build_keyring", lambda _: object())
    monkeypatch.setattr(keyring_module, "build_tenant_key_provisioner", lambda *_: None)
    monkeypatch.setattr(store_module, "build_file_store", lambda _: object())
    monkeypatch.setattr(doctor_module, "production_collector", lambda *_, **__: object())
    failing = doctor_module.CheckResult(
        doctor_module.EMAIL_BACKEND, "", failures=(FAKE.split(": ", 1)[1],)
    )
    monkeypatch.setattr(doctor_module, "run_doctor", lambda **_: [failing])
    result = CliRunner().invoke(cli.app, ["doctor"])
    assert result.exit_code == 1, result.output
    assert result.stdout == FAKE + "\n"
    assert cli.STARTUP_REFUSED not in result.output
