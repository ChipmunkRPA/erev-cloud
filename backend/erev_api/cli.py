"""The ``erev`` command-line application (docs/dev-guide.md §1.1; DG-LAY-10)."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, NoReturn

import typer
from sqlalchemy import text

from erev_api import __version__

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing, TenantKeyProvisioner
    from erev_api.clock import Clock
    from erev_api.config import Environment, Settings
    from erev_api.files.store import FileStore
    from erev_api.problems import Problem

app = typer.Typer(
    name="erev",
    help="eRev Cloud command-line interface.",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(
    help="Schema revisions, the catalogue lint and the dev database reset.",
    no_args_is_help=True,
)
app.add_typer(db_app, name="db")
operator_app = typer.Typer(help="Platform operators (BS1-D-27).", no_args_is_help=True)
app.add_typer(operator_app, name="operator")
support_grant_app = typer.Typer(
    help="Operator support access to a workspace (REQ-PLT-036).", no_args_is_help=True
)
app.add_typer(support_grant_app, name="support-grant")
idp_app = typer.Typer(help="Identity providers for sign-in (BS1-D-25).", no_args_is_help=True)
app.add_typer(idp_app, name="idp")
tenant_app = typer.Typer(
    help="Workspaces created by an operator (REQ-PLT-038).", no_args_is_help=True
)
app.add_typer(tenant_app, name="tenant")
seed_app = typer.Typer(help="Demo data for local environments (DG-MK-seed).", no_args_is_help=True)
app.add_typer(seed_app, name="seed")
perf_app = typer.Typer(
    help="The performance dataset for make perf (DG-MK-perf-seed, DG-PERF-01).",
    no_args_is_help=True,
)
app.add_typer(perf_app, name="perf")

# DG-MK-doctor: the environments `erev doctor --db` and `erev verify --db` may select. A
# DG-ENV-13 review database (`erev_rv_*`, a restore drill's clone, RB-04) is selected by name: it
# must be the database that EREV_DB_OWNER_URL and EREV_DB_APP_URL already point at.
DOCTOR_DATABASES = ("dev", "test", "e2e")
REVIEW_DATABASE = re.compile(r"^erev_rv_[a-z0-9_]+$")
DB_HELP = (
    "Database to check: dev, test, e2e, or an erev_rv_* database named by EREV_DB_OWNER_URL and "
    "EREV_DB_APP_URL (default: EREV_ENV)."
)
DB_USAGE = "--db must be dev, test, e2e or an erev_rv_* database (DG-ENV-13)"
# [J] SPEC-Q-191: an instant flag that does not parse as RFC 3339 with an offset.
INSTANT_INVALID = "Enter an RFC 3339 instant with a UTC offset, for example 2026-09-13T09:00:00Z."
# [J] L1-5-Q-5: demo personas and tenants only where the in-process mocks run (WLD-R-05).
SEED_ENVIRONMENT = "erev seed demo runs only with EREV_ENV dev, test or e2e"
PERF_SEED_ENVIRONMENT = "erev perf seed runs only with EREV_ENV dev, test or e2e"
PERF_SEED_PASSWORD = "EREV_DEMO_PASSWORD is not set. Copy it from .env.example."
# 05 SAR-40 rev 1.53 (ruling R-53 (6)): the closing line of an operator command's refusal, after
# the FAIL lines of the startup subset; the exit code is the one a refused api start ends with.
STARTUP_REFUSED = (
    "production refuses to run this command with this configuration (05 SAR-40 startup subset); "
    "erev doctor lists every finding"
)
STARTUP_REFUSED_EXIT = 3


@dataclass(frozen=True, slots=True)
class CliServices:
    clock: Clock
    keyring: KeyRing
    files: FileStore
    env: Environment  # EREV_ENV, for the rules that depend on the environment (05 SAR-15)
    run_dir: Path | None = None  # EREV_RUN_DIR for generated files; None reads the settings
    # KEY-05 provisioning authority of `erev tenant create`; None derives the key locally.
    key_provisioner: TenantKeyProvisioner | None = None


def _cli_settings() -> Settings:
    """The process settings, with the CFG-22 logging pipeline installed on stderr (05 OPR-20
    rev 1.53, ruling R-37 (c); DG-LOG-01).

    A command's log lines - the domain's, SQLAlchemy's, Alembic's - are rendered and scrubbed as the
    api's and the worker's are (OPR-21), and stdout carries only the command's own output
    (DG-KRN-TEN-04). Every command that opens a database connection or calls domain code calls this
    before its first log line, directly or through ``cli_services``; ``erev migrate`` and the ``db``
    commands installed no pipeline before, so a production migrate job printed structlog's default
    console lines on stdout and dropped Alembic's.
    """
    import sys

    from erev_api.config import get_settings
    from erev_api.logging import configure_logging

    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format, stream=sys.stderr)
    return settings


def _refuse_unsafe_production(settings: Settings) -> None:
    """05 SAR-40 rev 1.53 (ruling R-53 (6)): an operator command refuses under ``production`` when
    the startup subset fails, as the api and the worker refuse to start - one ``FAIL`` line per
    finding and a closing line on stderr, exit 3, before the key ring and any connection."""
    from erev_api.controls.startup import StartupRefused, refuse_unsafe_production

    try:
        refuse_unsafe_production(settings)
    except StartupRefused as refused:
        for line in refused.findings:
            typer.echo(line, err=True)
        typer.echo(STARTUP_REFUSED, err=True)
        raise typer.Exit(STARTUP_REFUSED_EXIT) from None


def cli_services(*, gated: bool = True) -> CliServices:
    """The clock, key ring, file store and environment of the operator commands; tests replace it
    (DG-TST-14).

    Logs go to stderr, so stdout carries only the command's JSON line (DG-KRN-TEN-04). Under
    ``production`` the startup subset is evaluated first and a failing one ends the command
    (``_refuse_unsafe_production``); only ``erev doctor`` and ``erev verify``, which are how an
    operator finds the fault, pass ``gated=False``.
    """
    from erev_api.auth.keyring import build_keyring, build_tenant_key_provisioner
    from erev_api.clock import SystemClock
    from erev_api.files.store import build_file_store

    settings = _cli_settings()
    # 05 REL-03 rev 1.15 (D-98 60): the trusted entrypoint boundary records the environment before
    # any domain call; an inline command that never stamps still fails closed outside dev / test.
    from erev_api.controls.release import remember_environment

    remember_environment(settings.env)
    if gated:
        _refuse_unsafe_production(settings)
    keyring = build_keyring(settings)
    return CliServices(
        clock=SystemClock(),
        keyring=keyring,
        files=build_file_store(settings),
        env=settings.env,
        run_dir=settings.run_dir,
        key_provisioner=build_tenant_key_provisioner(settings, keyring),
    )


def _request_id() -> str:
    return f"cli-{secrets.token_hex(8)}"


def _json_line(value: Any) -> str:
    """One JSON line with keys sorted at every level (DG-KRN-TEN-04)."""
    return json.dumps(value, sort_keys=True, default=str)


def _fail(problem: Problem, request_id: str) -> NoReturn:
    """The problem JSON on stderr and exit 1 (DG-KRN-TEN-04)."""
    from erev_api.problems import INSTANCE_BASE

    typer.echo(_json_line(problem.to_json(instance=INSTANCE_BASE + request_id)), err=True)
    raise typer.Exit(1)


def _instant(value: str, field: str) -> datetime:
    """An RFC 3339 instant with an offset, else 422 ``validation-failed`` on ``field``."""
    from erev_api.problems import Problem, ProblemError

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field=field, rule_id="BS1-D-27", message=INSTANT_INVALID)],
        )
    return parsed


@app.callback()
def main() -> None:
    """eRev Cloud command-line interface."""


def _select_database(db: str | None) -> None:
    """Point the process at the database ``--db`` names before any engine exists (DG-ENV-10).

    ``dev``, ``test`` and ``e2e`` switch ``EREV_ENV``. An ``erev_rv_*`` name selects the dev pair
    and requires both dev URLs to name that database, so a drill can never verify the wrong
    clone by accident (DG-ENV-13; RB-04, RB-06). Exit 2 otherwise.
    """
    import os

    from erev_api.config import get_settings
    from erev_api.controls import recovery_preflight as preflight
    from erev_api.db.session import dispose_engines

    if db is None:
        return
    caller_env = os.environ.get("EREV_ENV") or "dev"
    try:
        # The test-only identity stub is a hard error outside test/dev, decided before the
        # settings are read and before any connection (supervisor ruling of 2026-09-19).
        preflight.identity_stub(os.environ, env_name=caller_env)
    except preflight.PreflightError as error:
        typer.echo(f"--db {db}: {error}")
        raise typer.Exit(2) from error
    if db in DOCTOR_DATABASES:
        env = db
    elif REVIEW_DATABASE.fullmatch(db):
        env = "dev"
    else:
        typer.echo(DB_USAGE)
        raise typer.Exit(2)
    if get_settings().env.value != env:
        # DG-ENV-10: EREV_ENV selects the database URLs, so the process switches before any
        # engine exists.
        os.environ["EREV_ENV"] = env
        get_settings.cache_clear()
        dispose_engines()
    if db not in DOCTOR_DATABASES:
        # R1 residual: the direct entry points bind like the scripts. The owner and app URLs must
        # route to one host, port and database (a shared database name is not enough, and routing
        # query parameters are refused), and the servers they reach must answer one identity that
        # serves the selected clone.
        settings = get_settings()
        urls = {
            "EREV_DB_OWNER_URL": settings.owner_database_url(),
            "EREV_DB_APP_URL": settings.app_database_url(),
        }
        try:
            endpoint = preflight.same_endpoint(urls)
            if endpoint.database != db:
                raise preflight.PreflightError(
                    "EREV_DB_OWNER_URL and EREV_DB_APP_URL must name that database, not "
                    f"{endpoint.database} (DG-ENV-13)"
                )
            rows = preflight.connected_identities(urls, env_name=caller_env)
            findings = preflight.server_identity(rows)
            reached = next(iter(rows.values()))[0]
            if reached != db:
                findings.append(f"the server reached serves {reached}, not {db}")
            if findings:
                raise preflight.PreflightError("; ".join(findings))
        except preflight.PreflightError as error:
            typer.echo(f"--db {db}: {error}")
            raise typer.Exit(2) from error


@app.command()
def version() -> None:
    """Print the eRev Cloud backend version."""
    typer.echo(__version__)


@app.command("registry-seed")
def registry_seed(
    check: bool = typer.Option(False, "--check", help="Exit 1 when policies.py would change."),
    policies: Annotated[Path | None, typer.Option(help="POLICIES.md to parse.")] = None,
    out: Annotated[Path | None, typer.Option(help="Module path to write or check.")] = None,
) -> None:
    """Generate erev_api/registry/policies.py from POLICIES.md §1 (DG-MK-registry-seed)."""
    from erev_api.registry.seed import MODULE_PATH, POLICIES_PATH, is_current, write_module

    source = policies or POLICIES_PATH
    target = out or MODULE_PATH
    if check:
        if not is_current(source, target):
            typer.echo(f"{target} is stale; run make registry-seed")
            raise typer.Exit(1)
        typer.echo(f"{target} is current")
        return
    typer.echo(str(write_module(source, target)))


@app.command("openapi")
def openapi(
    out: Annotated[Path, typer.Option("--out", help="Where to write the OpenAPI document.")],
) -> None:
    """Write the OpenAPI 3.1 document with sorted keys and 2-space indent (DG-MK-openapi)."""
    from erev_api.main import create_app, openapi_document

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(openapi_document(create_app()), encoding="utf-8")
    typer.echo(str(out))


@app.command("controls-report")
def controls_report(
    tags_only: bool = typer.Option(False, "--tags-only", help="Validate control markers only."),
    tests: Annotated[Path | None, typer.Option(help="Test directory to collect.")] = None,
    out: Annotated[
        Path | None, typer.Option(help="Directory for report.json and report.md.")
    ] = None,
    command: Annotated[
        str, typer.Option(help="Invocation recorded in report.json.")
    ] = "erev controls-report",
) -> None:
    """Run the control-tagged tests and write the G7 report (DG-MK-controls-report)."""
    from erev_api.clock import SystemClock
    from erev_api.controls.registry import (
        REPORT_TARGET,
        REPOSITORY_ROOT,
        load_controls,
        run_tagged_tests,
        write_report,
    )

    specs = load_controls()
    clock = SystemClock()
    started_at = clock.now()
    run = run_tagged_tests(
        tests or REPOSITORY_ROOT / "backend" / "tests",
        collect_only=tags_only,
        base_temp=REPOSITORY_ROOT / ".run" / "pytest-controls",
    )
    if tags_only:
        if not run.collection_ok:
            typer.echo(f"control marker validation failed (pytest exit {run.exit_code})")
            raise typer.Exit(1)
        typer.echo(f"control markers valid: {run.tagged_test_count} tagged tests")
        return
    exit_code, summary = write_report(
        out or REPOSITORY_ROOT / ".run" / "reports" / REPORT_TARGET,
        specs=specs,
        run=run,
        command=command,
        started_at=started_at,
        finished_at=clock.now(),
    )
    typer.echo(summary)
    if exit_code:
        raise typer.Exit(exit_code)


# 05 DPL-01: the api image's health check waits at most this long for an answer.
HEALTHCHECK_TIMEOUT_SECONDS = 5.0


@app.command("api")
def api(
    host: Annotated[str, typer.Option("--host", help="Address to bind.")] = "127.0.0.1",
    port: Annotated[
        int, typer.Option("--port", min=1, max=65535, help="Port to listen on.")
    ] = 8190,
) -> None:
    """Serve the API through the application factory (05 CMP-08, DPL-01; DG-RUN-01).

    The api image runs ``erev api --host 0.0.0.0 --port 8080``. Access logs stay off (DG-RUN-01).
    """
    import uvicorn

    uvicorn.run("erev_api.main:create_app", factory=True, host=host, port=port, access_log=False)


@app.command("healthcheck")
def healthcheck(
    url: Annotated[
        str,
        typer.Option("--url", help="URL to GET, for example http://127.0.0.1:8080/api/v1/healthz."),
    ],
) -> None:
    """Exit 0 when a GET of ``url`` answers 2xx within 5 seconds, else 1 (05 DPL-01 HEALTHCHECK).

    A URL that is not http or https exits 2. Proxy variables are ignored: the check targets the
    container itself.
    """
    from erev_api.adapters.http.health import HealthProbeFailed, is_http_url, probe_status

    if not is_http_url(url):
        typer.echo("--url must be an http or https URL")
        raise typer.Exit(2)
    try:
        status = probe_status(url, timeout_seconds=HEALTHCHECK_TIMEOUT_SECONDS)
    except HealthProbeFailed as error:
        typer.echo(f"healthcheck {url} failed: {error}")
        raise typer.Exit(1) from error
    typer.echo(f"healthcheck {url} answered {status}")
    if not 200 <= status < 300:
        raise typer.Exit(1)


# 05 CMP-09: the migrate job's Alembic configuration, backend/alembic.ini next to the package.
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@app.command("migrate")
def migrate() -> None:
    """Upgrade the database to head as erev_owner, then run the DB-14 lint as erev_app.

    The compose ``migrate`` job runs ``erev migrate`` once before the api and worker start
    (05 CMP-08, CMP-09, DPL-11; DG-MK-migrate steps 2 and 3). ``EREV_ENV`` selects the database
    pair (DG-ENV-10). It never downgrades, and exits 1 on any lint finding.
    """
    from alembic import command
    from alembic.config import Config

    from erev_api.db.lint import lint_as_app

    _cli_settings()
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    findings = lint_as_app(request_id="migrate")
    for finding in findings:
        typer.echo(str(finding))
    typer.echo(f"DB-14 lint: {len(findings)} findings")
    if findings:
        raise typer.Exit(1)


@app.command("worker")
def worker(
    queues: Annotated[
        str | None,
        typer.Option("--queues", help="Comma-separated queues; overrides EREV_WORKER_QUEUES."),
    ] = None,
    heartbeat_file: Annotated[
        Path | None,
        typer.Option("--heartbeat-file", help="Heartbeat file (default .run/worker.heartbeat)."),
    ] = None,
    check: bool = typer.Option(
        False, "--check", help="Exit 0 when the heartbeat file is younger than 60 seconds."
    ),
) -> None:
    """Run the job worker on all eight queues unless a subset is named (DG-KRN-JOB-11)."""
    from erev_api import worker as worker_module
    from erev_api.config import get_settings
    from erev_api.jobs.registry import QUEUES

    settings = get_settings()
    path = heartbeat_file or settings.run_dir / "worker.heartbeat"
    if check:
        if not worker_module.heartbeat_is_fresh(path, worker_module.process_clock()):
            typer.echo(f"worker heartbeat {path} is missing or older than 60 seconds")
            raise typer.Exit(1)
        typer.echo("worker heartbeat is fresh")
        return
    if queues is None:
        names = list(settings.worker_queues)
    else:
        names = [name.strip() for name in queues.split(",") if name.strip()]
    for name in names:
        if name not in QUEUES:
            typer.echo(f"unknown queue {name}")
            raise typer.Exit(2)
    selected = tuple(queue for queue in QUEUES if queue in names)
    worker_module.main(queues=selected or QUEUES, heartbeat_file=path)


@app.command("doctor")
def doctor(
    db: Annotated[str | None, typer.Option("--db", help=DB_HELP)] = None,
    analyze: Annotated[
        str | None,
        typer.Option(
            "--analyze",
            help="Comma-separated schema-erev tables to ANALYZE as erev_owner; runs no check "
            "(05 PERF-27; DG-MK-perf-seed step 4).",
        ),
    ] = None,
) -> None:
    """Check the control-critical configuration; exit 1 on any failure (REQ-CTL-005).

    Prints one ``OK <check>: <summary>`` line per passing check, one ``FAIL <check>: <finding>``
    line per finding and one ``WARN <check>: <finding>`` line per warning (DG-MK-doctor;
    runbook "erev doctor"). Under ``EREV_ENV=production`` the 05 SAR-40 production checks follow,
    over observations collected once through ``production_collector`` (RB-03).
    ``--db erev_rv_<name>`` checks a restore drill's clone (RB-06); the environment switch and
    the engine disposal happen in ``_select_database`` (DG-ENV-10).
    """
    import os

    from erev_api.config import Environment, get_settings
    from erev_api.controls.doctor import (
        AnalyzeFailed,
        UnknownTable,
        analyze_tables,
        production_collector,
        run_doctor,
    )
    from erev_api.db.session import OWNER_ROLE, build_engine

    # DG-ENV-10 / DG-ENV-13: the environment switch, the engine disposal and the erev_rv_*
    # binding of a restore drill's clone live in _select_database (lane P6).
    _select_database(db)
    settings = get_settings()
    if analyze is not None:
        # 05 PERF-27: planner statistics need the table owner; the checks do not run in this mode.
        # No operator services are built here, so the pipeline is installed directly (OPR-20).
        _cli_settings()
        names = [name.strip() for name in analyze.split(",") if name.strip()]
        engine = build_engine(settings.owner_database_url(), role=OWNER_ROLE, component="cli")
        try:
            count = analyze_tables(engine, names)
        except UnknownTable as exc:  # validated before any SQL; the name is the caller's argument
            typer.echo(f"unknown table {exc.table}")
            raise typer.Exit(2) from None
        except AnalyzeFailed as exc:  # exception type and table position only (Codex P4C-S6-R2)
            typer.echo(str(exc))
            raise typer.Exit(1) from None
        finally:
            engine.dispose()
        typer.echo(f"OK analyze: {count} tables analyzed as {OWNER_ROLE}")
        return
    services = cli_services(gated=False)
    request_id = _request_id()
    production = None
    if settings.env is Environment.PRODUCTION:
        # 05 SAR-40: the real collectors, composed here (the composition root) and run once
        # inside run_doctor with the tenant directory it reads for audit-chain.
        production = production_collector(
            settings,
            keyring=services.keyring,
            environ=os.environ,
            request_id=request_id,
            now=services.clock.now(),
        )
    results = run_doctor(
        clock=services.clock,
        keyring=services.keyring,
        request_id=request_id,
        ai_kill_switch=settings.ai_kill_switch,
        production=production,
    )
    for result in results:
        for line in result.lines():
            typer.echo(line)
    if not all(result.ok for result in results):
        raise typer.Exit(1)


@app.command("verify")
def verify_command(
    all_tenants: bool = typer.Option(
        False, "--all-tenants", help="Verify every workspace (05 OPR-11 step (3))."
    ),
    tenant_code: Annotated[
        list[str] | None, typer.Option("--tenant", help="A workspace code; repeatable.")
    ] = None,
    db: Annotated[str | None, typer.Option("--db", help=DB_HELP)] = None,
    output: Annotated[
        Path | None, typer.Option("--output", help="Write the verification document here.")
    ] = None,
    json_output: bool = typer.Option(False, "--json", help="Print the document to stdout."),
    expect: Annotated[
        Path | None,
        typer.Option(
            "--expect",
            help="A backup-time document whose chain heads, files and keys must still hold.",
        ),
    ] = None,
    check_files: bool = typer.Option(
        True, "--files/--no-files", help="Verify the file store against file_object (default on)."
    ),
) -> None:
    """Verify chains, digests, files and key versions; exit 1 on any finding (05 OPR-11 (3)).

    One line per check (``OK`` or ``FAIL``), then ``OK verify`` or ``FAIL verify: <n> findings``.
    ``make backup`` stores the document next to the dump; ``make restore-verify`` passes it back
    through ``--expect`` so the restored chains must still carry every recorded head (RB-04, RB-06).
    """
    from erev_engine import ENGINE_VERSION

    from erev_api.config import get_settings
    from erev_api.controls import recovery
    from erev_api.domain.journals import (
        subledger,  # noqa: F401  (registers the ledger-chain verifier, DG-ARC-01)
    )

    if not all_tenants and not tenant_code:
        typer.echo("erev verify needs --all-tenants or at least one --tenant")
        raise typer.Exit(2)
    _select_database(db)
    services = cli_services(gated=False)
    request_id = _request_id()
    try:
        document = recovery.verify_all_tenants(
            keyring=services.keyring,
            files=services.files,
            clock=services.clock,
            request_id=request_id,
            database=get_settings().database_name(),
            engine_version=ENGINE_VERSION,
            tenant_codes=None if all_tenants else tenant_code,
            check_files=check_files,
        )
    except ValueError as error:
        typer.echo(str(error))
        raise typer.Exit(2) from error
    findings = list(document["failures"])
    if expect is not None:
        from erev_api.controls import recovery_preflight as preflight

        # P6-R2: an expected document is a baseline only when it is populated and well formed.
        try:
            expected = preflight.load_json_strict(expect.read_text(encoding="utf-8"))
        except ValueError as error:
            typer.echo(f"--expect {expect.name}: {error}")
            raise typer.Exit(2) from error
        invalid = preflight.validate_expected_document(expected)
        if invalid:
            for line in invalid:
                typer.echo(f"--expect {expect.name}: {line}")
            raise typer.Exit(2)
        anchors = recovery.resolve_anchors(
            recovery.anchor_requests(expected), request_id=request_id
        )
        compared = recovery.compare_expected(expected, document, anchors)
        document["expected"] = {
            "source": expect.name,
            "generated_at": expected.get("generated_at"),
            "result_at_backup": expected.get("result"),
            "tenants": len(expected.get("tenants") or []),
            "anchors": len(anchors),
            "findings": compared,
            "result": "FAIL" if compared else "PASS",
        }
        findings.extend(compared)
        if expected.get("result") != "PASS":
            findings.append(
                f"the backup-time verification {expect.name} had result "
                f"{expected.get('result')}: the clone reproduces failed evidence, not a clean "
                "baseline (RB-08)"
            )
    document["result"] = "FAIL" if findings else "PASS"
    document["failures"] = findings
    document["counts"]["failures"] = len(findings)
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    if json_output:
        typer.echo(rendered, nl=False)
    else:
        for line in _verify_lines(document):
            typer.echo(line)
    if output is not None:
        typer.echo(f"verify: document {output}")
    if findings:
        typer.echo(f"FAIL verify: {len(findings)} findings")
        raise typer.Exit(1)
    typer.echo("OK verify")


def _verify_lines(document: dict[str, Any]) -> list[str]:
    """The human summary of a verification document, one ``OK`` or ``FAIL`` line per check."""

    def line(ok: bool, check: str, summary: str) -> str:
        return f"{'OK' if ok else 'FAIL'} {check}: {summary}"

    security = document["security_chain"]
    lines = [
        line(
            security["result"] == "PASS",
            "security-chain",
            f"{security['events_checked']} events checked; head {security['last_chain_seq']}",
        )
    ]
    for workspace in document["tenants"]:
        code = workspace["code"]
        chain = workspace["audit_chain"]
        head = workspace["head"] or {}
        digest = workspace["digest"]
        summary = f"{chain['events_checked']} events checked; head {head.get('last_chain_seq')}"
        if digest is None:
            summary += "; no digest yet"
        else:
            summary += f"; digest at {digest['last_chain_seq']} (gap {workspace['gap_events']})"
        lines.append(
            line(
                chain["result"] == "PASS" and (digest is None or digest["event_matches"]),
                f"{code} audit-chain",
                summary,
            )
        )
        for book in workspace["ledger_chains"]:
            lines.append(
                line(
                    book["result"] == "PASS",
                    f"{code} ledger {book['book_code']}",
                    f"{book['seals_checked']} seals checked",
                )
            )
        files = workspace["files"]
        lines.append(
            line(
                files["failed"] == 0,
                f"{code} files",
                f"{files['checked']} checked, {files['ok']} ok, {files['shredded']} shredded, "
                f"{files['failed']} failed",
            )
        )
        keys = workspace["audit_hmac_keys"]
        lines.append(
            line(
                all(k["available"] for k in keys),
                f"{code} audit-keys",
                f"{len(keys)} key ids, {sum(1 for k in keys if k['available'])} served",
            )
        )
    versions = document["key_versions"]
    keks = versions["kek"]
    opened = sum(int(k["opened"]) for k in keks)
    references = sum(int(k["references"]) for k in keks)
    lines.append(
        line(
            all(k["available"] for k in versions["security_hmac"])
            and all(k["available"] for k in versions["audit_hmac"])
            and all(k["available"] for k in keks),
            "key-versions",
            f"{len(versions['security_hmac'])} security, {len(versions['audit_hmac'])} audit, "
            f"{len(keks)} kek ids; {opened} of {references} envelopes opened",
        )
    )
    expected = document.get("expected")
    if expected is not None:
        lines.append(
            line(
                expected["result"] == "PASS" and expected.get("result_at_backup") == "PASS",
                "expected",
                f"{expected['anchors']} backup-time anchors from {expected['source']} "
                f"({expected['tenants']} tenants, result {expected.get('result_at_backup')}); "
                f"{len(expected['findings'])} findings",
            )
        )
    return lines


@app.command("restore-applied")
def restore_applied_command(
    instant: str = typer.Option(..., "--instant", help="The restore point, RFC 3339 with offset."),
    backup: str = typer.Option(..., "--backup", help="The backup or clone identifier restored."),
    digests: Annotated[
        Path | None,
        typer.Option("--digests", help="The backup-time document holding the previous heads."),
    ] = None,
    db: Annotated[str | None, typer.Option("--db", help=DB_HELP)] = None,
) -> None:
    """Append ``platform.restore_applied`` to every ACTIVE workspace's audit log (05 OPR-11 (6)).

    Run once after a cutover, against the database now serving production, never against the
    source that was replaced. Prints one JSON line per workspace with the previous and new chain
    heads, then ``OK restore-applied``. Tenant Admins are then notified by the operator (RB-04).
    """
    from erev_api.controls import recovery

    restore_instant = _instant(instant, "instant")
    _select_database(db)
    previous = None
    if digests is not None:
        previous = recovery.previous_heads_of(json.loads(digests.read_text(encoding="utf-8")))
    services = cli_services()
    applied = recovery.record_restore_applied(
        keyring=services.keyring,
        files=services.files,
        clock=services.clock,
        request_id=_request_id(),
        restore_instant=restore_instant,
        backup_id=backup,
        previous_heads=previous,
    )
    for row in applied:
        typer.echo(_json_line(row))
    typer.echo(f"OK restore-applied: {len(applied)} workspaces")


@operator_app.command("create")
def operator_create(
    email: str = typer.Option(..., "--email", help="The operator's email address."),
    name: str = typer.Option(..., "--name", help="The operator's display name."),
) -> None:
    """Create a platform operator; the password is read from a hidden prompt (BS1-D-27).

    Prints one JSON line ``{display_name, email, id, is_operator}``; a problem goes to stderr as
    JSON with exit 1. Neither the password nor its hash is printed.
    """
    from erev_api.auth import operators
    from erev_api.problems import Problem

    services = cli_services()  # first: a refused command asks for no password
    password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    request_id = _request_id()
    try:
        created = operators.create_operator(
            email=email,
            display_name=name,
            password=password,
            request_id=request_id,
            keyring=services.keyring,
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(created))


@support_grant_app.command("request")
def support_grant_request(
    tenant: str = typer.Option(..., "--tenant", help="The workspace code."),
    operator: str = typer.Option(..., "--operator", help="The operator's email address."),
    reason: str = typer.Option(..., "--reason", help="Why access is needed (10+ characters)."),
    ticket: str | None = typer.Option(None, "--ticket", help="The support ticket reference."),
    valid_from: str = typer.Option(..., "--from", help="Start, RFC 3339 with an offset."),
    valid_to: str = typer.Option(..., "--to", help="End, RFC 3339; at most 72 hours later."),
) -> None:
    """Request read-only support access to a workspace for a Tenant Admin to approve (BS1-D-27).

    Prints API-S-SupportGrant as one JSON line; a problem goes to stderr as JSON with exit 1.
    """
    from erev_api.domain.platform import support_grants
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        out = support_grants.request_as_operator(
            support_grants.OperatorRequest(
                tenant_code=tenant,
                operator_email=operator,
                reason=reason,
                ticket_ref=ticket,
                valid_from=_instant(valid_from, "valid_from"),
                valid_to=_instant(valid_to, "valid_to"),
            ),
            request_id=request_id,
            clock=services.clock,
            keyring=services.keyring,
            files=services.files,
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(out))


@tenant_app.command("create")
def tenant_create(
    code: str = typer.Option(..., "--code", help="URL-safe workspace code."),
    name: str = typer.Option(..., "--name", help="The workspace's display name."),
    reporting_currency: str = typer.Option(
        ..., "--reporting-currency", help="ISO 4217 reporting currency."
    ),
    demo: bool = typer.Option(False, "--demo", help="Mark the workspace as a demo workspace."),
    admin: str = typer.Option(..., "--admin", help="Email address of the Tenant Admin to invite."),
    industry_cluster: str | None = typer.Option(
        None,
        "--industry-cluster",
        help="T-PLT-01 cluster code; perf:<16 hex> names a generator manifest (05 PERF-11).",
    ),
) -> None:
    """Provision a production workspace and invite its Tenant Admin (DG-KRN-TEN-04).

    Prints the API-R-54 201 body as one JSON line with sorted keys; a problem goes to stderr as JSON
    with exit 1. The invitation token travels only in the invitation email and is never printed.
    """
    import getpass

    from erev_api.api.v1.operator_tenants import OperatorTenantOut
    from erev_api.domain.platform.provisioning import (
        OperatorActor,
        TenantProvisionRequest,
        provision_tenant,
    )
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        result = provision_tenant(
            TenantProvisionRequest(
                code=code,
                display_name=name,
                reporting_currency=reporting_currency,
                is_demo=demo,
                admin_email=admin,
                industry_cluster=industry_cluster,
            ),
            actor=OperatorActor(
                channel="CLI",
                operator_user_id=None,
                os_user=getpass.getuser(),
                request_id=request_id,
            ),
            clock=services.clock,
            keyring=services.keyring,
            key_provisioner=services.key_provisioner,
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(OperatorTenantOut.of(result).model_dump(mode="json")))


@tenant_app.command("resend-invitation")
def tenant_resend_invitation(
    code: str = typer.Option(..., "--code", help="The workspace code."),
    admin: str = typer.Option(..., "--admin", help="Email address of the invited Tenant Admin."),
) -> None:
    """Issue the first Tenant Admin's invitation again while it is open (04 §14.3 step 5).

    For a link that was lost or has expired before the admin accepted. Prints
    ``{admin_membership_id, invitation_expires_at, tenant: {code, id}}`` as one JSON line with
    sorted keys; a problem goes to stderr as JSON with exit 1. The new link travels only in the
    email, the earlier one stops working, and nothing but an open invitation that an operator
    issued can be sent again this way (PRD BR-PLT-01).
    """
    import getpass

    from erev_api.api.v1.operator_tenants import OperatorInvitationOut
    from erev_api.domain.platform.provisioning import OperatorActor, reissue_admin_invitation
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        done = reissue_admin_invitation(
            code=code,
            admin_email=admin,
            actor=OperatorActor(
                channel="CLI",
                operator_user_id=None,
                os_user=getpass.getuser(),
                request_id=request_id,
            ),
            clock=services.clock,
            keyring=services.keyring,
            files=services.files,
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(OperatorInvitationOut.of(done).model_dump(mode="json")))


@seed_app.command("demo")
def seed_demo_command(
    tenants: str = typer.Option(
        "all", "--tenants", help="all, or comma-separated codes of WLD-T-00 to WLD-T-07."
    ),
    with_close: bool = typer.Option(
        False,
        "--with-close",
        help="Also close the months the demo world shows as closed (minutes; BUILD_SPEC CLO-22).",
    ),
) -> None:
    """Build the demo tenants through commands run as the persona users (DG-MK-seed; WLD-R-02).

    Prints ``seeded <code>`` or ``skipped <code>`` per tenant, then the credentials file when
    recovery codes were issued (DG-RUN-32). A refusal goes to stderr with exit 1; no password or
    recovery code is printed. ``--with-close`` adds the close stage (``demo.close_history``): its
    jobs run in this process, which therefore registers the CSV general-ledger adapter as the
    worker does (DG-LAY-03).
    """
    import getpass

    from erev_api.config import LOCAL_ENVIRONMENTS, get_settings
    from erev_api.domain.demo import SeedRefused, seed
    from erev_api.domain.demo import tenants as demo_tenants
    from erev_api.problems import Problem

    services = cli_services()
    if services.env not in LOCAL_ENVIRONMENTS:
        typer.echo(SEED_ENVIRONMENT, err=True)
        raise typer.Exit(1)
    settings = get_settings()
    password = "" if settings.demo_password is None else settings.demo_password.get_secret_value()
    totp_secret = (
        "" if settings.demo_totp_secret is None else settings.demo_totp_secret.get_secret_value()
    )
    request_id = _request_id()
    run_dir = services.run_dir or settings.run_dir
    # 05 REL-03: the Avenmoor contract builders compute (CTR-20), so the seed stamps the engine
    # release row as the api and the worker do when they start.
    from erev_api.controls.release import stamp_release

    stamp_release(services.env, request_id=request_id)
    if with_close:
        # DG-LAY-03: the close stage exports its journals through the adapter a composition root
        # registered for the batch; a seed has no connection, so the batches are CSV batches.
        from erev_api.adapters.gl.csv import CsvGl
        from erev_api.domain.journals import ports as gl_ports
        from erev_api.enums import GlAdapter

        gl_ports.register_gl_adapter(GlAdapter.CSV, CsvGl)
    try:
        result = seed.seed_demo(
            demo_tenants.select_codes(tenants),
            services.clock,
            keyring=services.keyring,
            files=services.files,
            secrets=seed.DemoSecrets(password=password, totp_secret=totp_secret),
            credentials_path=run_dir / seed.CREDENTIALS_FILE,
            request_id=request_id,
            os_user=getpass.getuser(),
            with_close=with_close,
        )
    except SeedRefused as refused:
        typer.echo(str(refused), err=True)
        raise typer.Exit(1) from None
    except Problem as problem:
        _fail(problem, request_id)
    for code, outcome in result.outcomes:
        typer.echo(f"{outcome} {code}")
    if result.credentials_path is not None:
        typer.echo(f"recovery codes written to {result.credentials_path}")


@perf_app.command("seed")
def perf_seed_command(
    scale: str = typer.Option(
        "1", "--scale", help="Fraction of the full dataset, e.g. 1 or 1/1000 (tests only)."
    ),
    through_month: int = typer.Option(
        23, "--through-month", min=1, max=24, help="Last month to append and lock (default 23)."
    ),
    snapshot_only: bool = typer.Option(
        False,
        "--snapshot-only",
        help="Step 5 only: the stored snapshot after make perf-seed's ANALYZE (step 4).",
    ),
) -> None:
    """Build or resume the ``perf-volume`` tenant for ``make perf`` (DG-MK-perf-seed steps 1-3),
    or with ``--snapshot-only`` take its stored snapshot — a ``STORED_BACKUP``, which loads no
    sandbox — (step 5, after the step-4 ANALYZE).

    Idempotent: an up-to-date tenant prints "perf-volume up to date" and exits 0; a tenant built
    from another generator version exits 2 with "perf tenant built from another generator
    version; run make db-reset"; the same version but incomplete resumes at the first unfinished
    step; ``--snapshot-only`` before the month-23 lock is refused by name with exit 1. Prints one
    JSON line (the report document) then the message; writes
    ``<run dir>/reports/perf-seed/report.json`` (step 6; the snapshot phase merges into the seed
    phase's document). No password or TOTP secret is printed.

    The months are closed as a person closes them (``demo.closing``; 05 PERF-15), and the jobs of
    a close run in this process, which therefore registers the CSV general-ledger adapter as the
    worker does (DG-LAY-03). An open exception item that holds a lock and is not a late event of
    the generator stops the seed: it is named on stderr with exit 1. So does a snapshot whose
    job does not succeed, with the job's own sentence.
    """
    import getpass
    from fractions import Fraction

    from erev_api.config import LOCAL_ENVIRONMENTS, get_settings
    from erev_api.controls.release import stamp_release
    from erev_api.domain.demo import perf_seed
    from erev_api.domain.demo.sessions import SeedSecrets
    from erev_api.problems import Problem
    from erev_api.worker import build_runtime

    services = cli_services()
    if services.env not in LOCAL_ENVIRONMENTS:
        typer.echo(PERF_SEED_ENVIRONMENT, err=True)
        raise typer.Exit(1)
    settings = get_settings()
    password = "" if settings.demo_password is None else settings.demo_password.get_secret_value()
    totp_secret = (
        "" if settings.demo_totp_secret is None else settings.demo_totp_secret.get_secret_value()
    )
    if not password:
        typer.echo(PERF_SEED_PASSWORD, err=True)
        raise typer.Exit(1)
    try:
        fraction = Fraction(scale)
    except (ValueError, ZeroDivisionError):
        typer.echo("--scale must be a fraction such as 1 or 1/1000", err=True)
        raise typer.Exit(2) from None
    if not 0 < fraction <= 1:
        typer.echo("--scale must be above 0 and at most 1", err=True)
        raise typer.Exit(2)
    request_id = _request_id()
    run_dir = services.run_dir or settings.run_dir
    # 05 REL-03: the seed computes (CTR-20), so it stamps the engine release row as the api and
    # the worker do when they start.
    stamp_release(services.env, request_id=request_id)
    if not snapshot_only:
        # DG-LAY-03: a month's journal run is exported through the adapter a composition root
        # registered for the batch; the volume tenant has no connection, so its batches are CSV.
        from erev_api.adapters.gl.csv import CsvGl
        from erev_api.domain.journals import ports as gl_ports
        from erev_api.enums import GlAdapter

        gl_ports.register_gl_adapter(GlAdapter.CSV, CsvGl)
    try:
        result = perf_seed.run(
            perf_seed.Services(
                clock=services.clock,
                keyring=services.keyring,
                files=services.files,
                runtime=build_runtime(settings, services.clock),
                secrets=SeedSecrets(password=password, totp_secret=totp_secret),
                request_id=request_id,
                os_user=getpass.getuser(),
                key_provisioner=services.key_provisioner,
            ),
            reports_dir=run_dir / "reports",
            scale=fraction,
            through_month=through_month,
            snapshot_only=snapshot_only,
        )
    except perf_seed.SeedStopped as stopped:
        typer.echo(str(stopped), err=True)
        raise typer.Exit(1) from None
    except Problem as problem:
        _fail(problem, request_id)
    perf_seed.write_report(result, run_dir / "reports")
    typer.echo(_json_line(result.document()))
    typer.echo(result.message)
    if result.exit_code:
        raise typer.Exit(result.exit_code)


@idp_app.command("list")
def idp_list() -> None:
    """List the identity providers as erev_app (05 SAR-27; 04 T-PLT-03).

    Each provider with the code the other ``erev idp`` commands take, its kind, name, issuer,
    email domains and whether it is enabled, ordered by code. Reads only: it needs no owner URL
    and leaves no event. Prints one JSON line; a problem goes to stderr as JSON with exit 1.
    """
    from erev_api.auth import oidc
    from erev_api.problems import Problem

    cli_services()
    request_id = _request_id()
    try:
        listed = oidc.list_providers(request_id=request_id)
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(listed))


@idp_app.command("create")
def idp_create(
    email_domain: Annotated[
        list[str],
        typer.Option(
            "--email-domain",
            help="An email domain the provider is authoritative for; repeat for each (1 to 20).",
        ),
    ],
    code: str = typer.Option(..., "--code", help="URL-safe provider code."),
    kind: str = typer.Option(..., "--kind", help="Provider kind; only oidc in 1.0."),
    name: str = typer.Option(..., "--name", help="Name on the sign-in page."),
    issuer_url: str = typer.Option(..., "--issuer-url", help="The OIDC issuer URL."),
    client_id: str = typer.Option(..., "--client-id", help="The client id at the provider."),
    client_secret_ref: str | None = typer.Option(
        None, "--client-secret-ref", help="Secret store reference of a confidential client."
    ),
) -> None:
    """Add an identity provider as erev_owner (BS1-D-25), bound to its email domains.

    The provider signs in only verified emails of the domains named here (REQ-PLT-006). Prints
    the provider as one JSON line; a problem goes to stderr as JSON with exit 1.
    """
    from erev_api.auth import oidc
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        created = oidc.create_provider(
            oidc.ProviderSpec(
                code=code,
                kind=kind,
                display_name=name,
                issuer_url=issuer_url,
                client_id=client_id,
                client_secret_ref=client_secret_ref,
                email_domains=tuple(email_domain),
            ),
            request_id=request_id,
            keyring=services.keyring,
            env=services.env,
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(created))


@idp_app.command("invite")
def idp_invite(
    code: str = typer.Option(..., "--code", help="The provider's code."),
    email: str = typer.Option(..., "--email", help="The email address of an existing identity."),
) -> None:
    """Invite an existing identity for an identity provider as erev_owner (REQ-PLT-006).

    Only an invited identity signs in through a provider: its first sign-in links it to the
    provider's subject. Prints the result as one JSON line; a problem goes to stderr as JSON
    with exit 1.
    """
    from erev_api.auth import oidc
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        invited = oidc.invite_identity(
            code=code, email=email, request_id=request_id, keyring=services.keyring
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(invited))


@idp_app.command("domains")
def idp_domains(
    code: str = typer.Option(..., "--code", help="The provider's code."),
    add: Annotated[
        list[str] | None,
        typer.Option("--add", help="An email domain to bind the provider to; repeat for each."),
    ] = None,
    remove: Annotated[
        list[str] | None,
        typer.Option("--remove", help="An email domain to take from the provider; repeat."),
    ] = None,
) -> None:
    """Change the email domains of an identity provider as erev_owner (REQ-PLT-006).

    The provider signs in only verified emails of its domains, from the next sign-in on; it keeps
    1 to 20. Prints the provider's domains after the change, what was added and removed, and the
    number of identities invited for the provider whose email is now outside its domains, as one
    JSON line; a problem goes to stderr as JSON with exit 1.
    """
    from erev_api.auth import oidc
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        changed = oidc.change_domains(
            code=code,
            add=tuple(add or ()),
            remove=tuple(remove or ()),
            request_id=request_id,
            keyring=services.keyring,
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(changed))


@idp_app.command("disable")
def idp_disable(
    code: str = typer.Option(..., "--code", help="The provider's code."),
) -> None:
    """Take an identity provider out of sign-in as erev_owner (05 SAR-27; 04 T-PLT-03).

    From the next request on the sign-in page does not offer the provider and nobody signs in
    through it; its identities keep their passwords, and sessions that are open stay open until
    they end or expire - ``erev idp end-sessions`` ends them. Prints the provider, its state and
    whether it changed as one JSON line; a problem goes to stderr as JSON with exit 1.
    """
    from erev_api.auth import oidc
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        result = oidc.set_enabled(
            code=code, enabled=False, request_id=request_id, keyring=services.keyring
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(result))


@idp_app.command("enable")
def idp_enable(
    code: str = typer.Option(..., "--code", help="The provider's code."),
) -> None:
    """Put an identity provider back into sign-in as erev_owner (05 SAR-27; 04 T-PLT-03).

    Prints the provider, its state and whether it changed as one JSON line; a problem goes to
    stderr as JSON with exit 1.
    """
    from erev_api.auth import oidc
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        result = oidc.set_enabled(
            code=code, enabled=True, request_id=request_id, keyring=services.keyring
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(result))


@idp_app.command("end-sessions")
def idp_end_sessions(
    code: str = typer.Option(..., "--code", help="The provider's code."),
) -> None:
    """End the sessions opened through a disabled identity provider, as erev_app (05 SAR-27).

    For a provider that can no longer be trusted: disable it, then end its sessions. Every open
    session that one of the provider's identities opened through it ends at once; a session
    opened with a password stays. Refused while the provider is enabled. Prints the provider,
    the identities that had such a session and the sessions ended as one JSON line; a problem
    goes to stderr as JSON with exit 1.
    """
    from erev_api.auth import oidc
    from erev_api.problems import Problem

    services = cli_services()
    request_id = _request_id()
    try:
        result = oidc.end_sessions(
            code=code,
            request_id=request_id,
            keyring=services.keyring,
            now=services.clock.now(),
        )
    except Problem as problem:
        _fail(problem, request_id)
    typer.echo(_json_line(result))


@db_app.command("lint")
def db_lint() -> None:
    """Run the DB-14 catalogue lint as erev_app; exit 1 on any finding (DG-MK-migrate)."""
    from erev_api.db.lint import lint_as_app

    _cli_settings()
    findings = lint_as_app()
    for finding in findings:
        typer.echo(str(finding))
    typer.echo(f"DB-14 lint: {len(findings)} findings")
    if findings:
        raise typer.Exit(1)


def _reset_unless(refusal: str | None) -> None:
    """End ``erev db reset`` with the refusal, when there is one."""
    if refusal is not None:
        typer.echo(refusal)
        raise typer.Exit(1)


@db_app.command("reset")
def db_reset() -> None:
    """Drop schema erev in the development database the environment names, as erev_owner
    (DG-MK-db-reset; DG-ENV-13 rev 1.200).

    A development database: ``EREV_ENV=dev``, a database named ``erev`` or ``erev_rv_*`` that the
    server answers by that name, and no tenant without the demo marker (``controls/reset.py``).
    The command names the one that does not hold and drops nothing.
    """
    from erev_api.auth.keyring import build_keyring
    from erev_api.controls import reset
    from erev_api.db import migration_ops
    from erev_api.db.session import OWNER_ROLE, build_engine

    settings = _cli_settings()
    database = settings.database_name()
    _reset_unless(reset.refused_before_connecting(settings.env, database))
    engine = build_engine(settings.owner_database_url(), role=OWNER_ROLE, component="cli")
    try:
        with engine.connect() as connection:
            answered = str(connection.execute(text("SELECT current_database()")).scalar_one())
            holds_tenants = reset.tenant_table_exists(connection)
        _reset_unless(reset.refused_by_server(database, answered))
        if holds_tenants:
            try:
                unmarked = reset.unmarked_tenants(keyring=build_keyring(settings))
            except Exception as error:  # what could not be judged is not reset
                typer.echo(
                    f"refusing to reset {database}: its tenants could not be counted "
                    f"({type(error).__name__})"
                )
                raise typer.Exit(1) from error
            _reset_unless(reset.refused_for_tenants(database, unmarked))
        # One partitioned table per transaction first, within the shared lock table (CTR-2).
        migration_ops.drop_partitioned_tables(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS erev CASCADE")
            # DG-MK-db-reset: the Procrastinate objects in public go too (DG-MIG-09).
            with migration_ops.bound_to(connection):
                migration_ops.drop_procrastinate_schema()
    finally:
        engine.dispose()
    typer.echo(f"schema erev and the Procrastinate objects dropped in {database}")


@db_app.command("revision")
def db_revision(
    msg: str = typer.Option(..., "--msg", help="Summary; becomes the file slug."),
    item: str = typer.Option(..., "--item", help="BUILD_SPEC item id named in the docstring."),
) -> None:
    """Render the next handwritten revision after the current head (DG-MK-revision)."""
    from erev_api.db.migration_ops import write_revision

    _cli_settings()
    typer.echo(str(write_revision(msg, item)))
