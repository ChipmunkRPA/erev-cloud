"""``make restore-drill`` (dev-guide §4.5 DG-MK-restore-drill; §4.1 DG-MK-00a, DG-MK-00g; DG-ENV-14;
DG-FORBID-07, DG-FORBID-12; 05 OPR-12, DPL-10; runbook RB-06, RB-11).

The loop never runs a supervisor target. ``scripts/restore_drill.sh`` is exercised here against
stand-ins for docker, ``erev`` and the two recovery scripts in a scratch root: nothing is started,
seeded, dumped or restored, and the worktree's own reports are never touched. The init file and
the compose override the drill relies on are read as text.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml
from support.gate_evidence import REPORT_KEYS, has_population, usable_evidence

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "restore_drill.sh"
DRILL = ROOT / "deploy" / "compose" / "drill"
PROJECT = "erev-verify-drill"
BACKUP_ID = "erev-20260930T120000Z"
STAGES = (
    "daemon",
    "preflight",
    "server",
    "roles",
    "source",
    "backup",
    "counts",
    "destroy",
    "fresh-server",
    "restore",
    "compare",
    "teardown",
)

# docker stand-in: every call is recorded; `compose` calls also record the port and the five
# passwords they were handed (STUB_SECRETS, outside the scratch root). The containers and volumes
# of the project are two files under STUB_STATE: `up` creates them, `down` removes them.
DOCKER_STUB = """#!/usr/bin/env bash
echo "docker $*" >>"$STUB_CALLS"
state="${STUB_STATE:?}"
if [[ "$1" == "compose" ]]; then
  printf '%s|%s|%s|%s|%s|%s\\n' "${EREV_DRILL_PORT:-}" "${EREV_COMPOSE_POSTGRES_PASSWORD:-}" \\
    "${EREV_COMPOSE_OWNER_PASSWORD:-}" "${EREV_COMPOSE_APP_PASSWORD:-}" \\
    "${EREV_DRILL_BACKUP_PASSWORD:-}" "${EREV_DRILL_RESTORE_ADMIN_PASSWORD:-}" >>"$STUB_SECRETS"
fi
case "$1" in
  info) exit "${STUB_DOCKER_INFO_RC:-0}" ;;
  ps) [[ -f "$state/containers" ]] && cat "$state/containers"; exit 0 ;;
  volume) [[ -f "$state/volumes" ]] && cat "$state/volumes"; exit 0 ;;
  inspect) echo "${STUB_HEALTH:-healthy}"; exit 0 ;;
  compose)
    sub=""; database=""; prev=""
    for arg in "$@"; do
      if [[ -z "$sub" ]]; then case "$arg" in up|down|ps|exec) sub="$arg" ;; esac; fi
      [[ "$prev" == "-d" ]] && database="$arg"
      prev="$arg"
    done
    case "$sub" in
      up)
        n=$(( $(cat "$state/ups" 2>/dev/null || echo 0) + 1 )); echo "$n" >"$state/ups"
        [[ "${STUB_UP_FAIL_AT:-0}" == "$n" ]] && exit 1
        echo stubcontainer >"$state/containers"; echo stubvolume >"$state/volumes"; exit 0 ;;
      ps) echo stubcontainer; exit 0 ;;
      exec)
        sql="$(cat)"
        if [[ "$sql" == *pg_roles* ]]; then echo "${STUB_ROLES-2 2}"; exit 0; fi
        rows="$STUB_ROWS_CLONE"; [[ "$database" == "erev" ]] && rows="$STUB_ROWS_SOURCE"
        cat "$rows"
        exit 0 ;;
      down)
        n=$(( $(cat "$state/downs" 2>/dev/null || echo 0) + 1 )); echo "$n" >"$state/downs"
        [[ "${STUB_DOWN_FAIL_AT:-0}" == "$n" ]] && exit 1
        rm -f "$state/containers"
        [[ -n "${STUB_VOLUME_SURVIVES:-}" ]] || rm -f "$state/volumes"
        exit 0 ;;
    esac
    exit 0 ;;
  push|login) echo "forbidden: $1" >&2; exit 99 ;;
  *) exit 0 ;;
esac
"""
EREV_STUB = """#!/usr/bin/env bash
echo "erev $* | env=${EREV_ENV:-} files=${EREV_FILE_ROOT:-} run=${EREV_RUN_DIR:-}" >>"$STUB_CALLS"
printf 'owner %s\\napp %s\\n' "${EREV_DB_OWNER_URL:-}" "${EREV_DB_APP_URL:-}" >>"$STUB_URLS"
case "$1" in
  migrate) exit "${STUB_MIGRATE_RC:-0}" ;;
  seed) exit "${STUB_SEED_RC:-0}" ;;
esac
exit 0
"""
BACKUP_STUB = """#!/usr/bin/env bash
echo "backup | env=${EREV_ENV:-} dir=${EREV_BACKUP_DIR:-} run=${EREV_RUN_DIR:-}" \\
  "command=${EREV_BACKUP_COMMAND:-}" >>"$STUB_CALLS"
printf 'backup %s\\n' "${EREV_BACKUP_URL:-}" >>"$STUB_URLS"
if [[ "${STUB_BACKUP_RC:-0}" != "0" ]]; then
  echo "FAIL backup: stub"; exit "$STUB_BACKUP_RC"
fi
reports="${EREV_GATE_CONTEXT:+$EREV_GATE_CONTEXT/.run}"
reports="${reports:-$EREV_RUN_DIR}/reports/backup"
mkdir -p "$EREV_BACKUP_DIR" "$reports"
id="${STUB_BACKUP_ID-erev-20260930T120000Z}"
: >"$EREV_BACKUP_DIR/$id.dump"
[[ -n "${STUB_NO_MANIFEST:-}" ]] || echo "{}" >"$EREV_BACKUP_DIR/$id.manifest.json"
echo "EREV_ENCRYPTION_KEY=the-master-keys-travel-with-the-backup" >"$EREV_BACKUP_DIR/$id.env"
printf '{"target": "backup", "backup_id": "%s", "exit_code": 0}\\n' "$id" \\
  >"$reports/report.json"
echo "OK backup"
"""
RESTORE_STUB = """#!/usr/bin/env bash
echo "restore-verify | BACKUP=${BACKUP:-} RESET=${RESET-unset} dir=${EREV_BACKUP_DIR:-}" \\
  "run=${EREV_RUN_DIR:-} command=${EREV_RESTORE_COMMAND:-}" >>"$STUB_CALLS"
printf 'restore-owner %s\\nrestore-app %s\\nrestore-admin %s\\n' "${EREV_RESTORE_OWNER_URL:-}" \\
  "${EREV_RESTORE_APP_URL:-}" "${EREV_RESTORE_ADMIN_URL:-}" >>"$STUB_URLS"
if [[ "${STUB_RESTORE_RC:-0}" != "0" ]]; then
  echo "FAIL restore-verify: stub"; exit "$STUB_RESTORE_RC"
fi
reports="${EREV_GATE_CONTEXT:+$EREV_GATE_CONTEXT/.run}"
reports="${reports:-$EREV_RUN_DIR}/reports/restore-verify"
mkdir -p "$reports"
cat >"$reports/report.json" <<'JSON'
{"target": "restore-verify", "exit_code": 0,
 "counts": {"failures": 0, "files_checked": 310, "tenants": 8},
 "restore": {"restore_point": "2026-09-30T12:00:00Z", "evidence_lag_seconds": 3},
 "restore_test_record": {"verification_result": "PASS"}}
JSON
echo "OK restore-verify"
"""
SOURCE_ROWS = (
    "erev.audit_event|40\nerev.security_event|300\nerev.tenant|8\npublic.procrastinate_jobs|12\n"
)
# The verification appends its own security events to the clone; nothing else differs.
CLONE_ROWS = (
    "erev.audit_event|40\nerev.security_event|302\nerev.tenant|8\npublic.procrastinate_jobs|12\n"
)


@pytest.fixture
def scratch() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _stub(scratch: Path, name: str, text: str) -> str:
    binary = scratch / "bin" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(text, "utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return str(binary)


def _free_port() -> int:
    """A free loopback port (bind at 0, read, close; no ``socket`` import: DG-ARC-12)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        return int(server.server_address[1])
    finally:
        server.server_close()


@contextmanager
def _held_port() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        yield int(server.server_address[1])
    finally:
        server.server_close()


def _root(scratch: Path) -> Path:
    root = scratch / "drill-root"
    (root / "deploy" / "compose" / "drill").mkdir(parents=True)
    (root / "deploy" / "compose.yaml").write_text("services: {}\n", "utf-8")
    (root / "deploy" / "compose.env.example").write_text(
        "EREV_COMPOSE_POSTGRES_PASSWORD=\n", "utf-8"
    )
    (root / "deploy" / "compose" / "drill" / "override.yaml").write_text("services: {}\n", "utf-8")
    return root


def _env(scratch: Path, root: Path, **extra: str) -> dict[str, str]:
    state = scratch / "state"
    state.mkdir(exist_ok=True)
    for name in ("calls.log", "secrets.log", "urls.log"):
        (scratch / name).touch()
    (scratch / "rows-source.txt").write_text(SOURCE_ROWS, "utf-8")
    (scratch / "rows-clone.txt").write_text(CLONE_ROWS, "utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EREV_", "STUB_", "MAKE"))}
    for name in ("RESET", "TENANTS", "DRILL_PORT", "BACKUP"):
        env.pop(name, None)
    env.update(
        {
            "EREV_ENV": "test",
            "EREV_RUN_DIR": str(root / ".run"),
            "EREV_RESTORE_DRILL_ROOT": str(root),
            "EREV_DOCKER_BIN": _stub(scratch, "docker", DOCKER_STUB),
            "EREV_RESTORE_DRILL_EREV_BIN": _stub(scratch, "erev", EREV_STUB),
            "EREV_RESTORE_DRILL_BACKUP_SCRIPT": _stub(scratch, "backup.sh", BACKUP_STUB),
            "EREV_RESTORE_DRILL_RESTORE_SCRIPT": _stub(scratch, "restore_verify.sh", RESTORE_STUB),
            "EREV_RESTORE_DRILL_TIMEOUT_SECONDS": "120",
            # Never the published 5446: a real drill on this machine may hold it.
            "DRILL_PORT": str(_free_port()),
            "STUB_CALLS": str(scratch / "calls.log"),
            "STUB_SECRETS": str(scratch / "secrets.log"),
            "STUB_URLS": str(scratch / "urls.log"),
            "STUB_STATE": str(state),
            "STUB_ROWS_SOURCE": str(scratch / "rows-source.txt"),
            "STUB_ROWS_CLONE": str(scratch / "rows-clone.txt"),
            "TMPDIR": str(ROOT / ".run" / "tmp"),
            "GIT_CEILING_DIRECTORIES": str(root.parent),
        }
    )
    env.update(extra)
    return env


def _run(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,  # a slow-but-correct run under load is never killed by the harness
    )


def _report(root: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (root / ".run" / "reports" / "restore-drill" / "report.json").read_text("utf-8")
    )
    assert all(key in document for key in REPORT_KEYS)
    assert usable_evidence(document, "restore-drill", str(document["build_sha"])) is None
    return document


def _calls(scratch: Path) -> list[str]:
    return (scratch / "calls.log").read_text("utf-8").splitlines()


def _compose(calls: list[str], sub: str) -> list[str]:
    return [call for call in calls if call.startswith("docker compose ") and f" {sub}" in call]


def _passwords(scratch: Path) -> list[tuple[str, ...]]:
    return [
        tuple(line.split("|")) for line in (scratch / "secrets.log").read_text("utf-8").splitlines()
    ]


def test_restore_drill_runs_the_whole_procedure_and_tears_down(scratch: Path) -> None:
    root = _root(scratch)
    env = _env(scratch, root, TENANTS="avenmoor,bracken")
    port = env["DRILL_PORT"]
    # The deployment's own last backup and restore reports lie where the drill runs. The first
    # real run read the backup id from that file and asked the restore for a backup it had never
    # made; the drill reads the two scripts' reports where those scripts write them.
    theirs = {}
    for target, document in (
        ("backup", {"target": "backup", "backup_id": "erev-20250101T000000Z", "exit_code": 0}),
        ("restore-verify", {"target": "restore-verify", "counts": {"failures": 9}}),
    ):
        path = root / ".run" / "reports" / target / "report.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(document), "utf-8")
        theirs[path] = path.read_text("utf-8")
    done = _run(root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    for path, before in theirs.items():
        assert path.read_text("utf-8") == before, "the deployment's report is untouched"
    lines = done.stdout.splitlines()
    assert lines[-1] == "OK restore-drill"
    assert lines[-2].startswith(
        f"restore-drill: backup {BACKUP_ID} restored into a fresh server; 4 tables; 360 rows in "
        "the source, 362 in the clone; 1 table(s) hold more; backup "
    )

    # The order of the procedure: server, roles, migrate, seed, backup, counts, destroy, a fresh
    # server with its roles, restore, counts, teardown.
    calls = _calls(scratch)
    compose = (
        f"docker compose -f {root}/deploy/compose.yaml -f {root}/deploy/compose/drill/override.yaml"
    )
    compose += f" --env-file {root}/deploy/compose.env.example -p {PROJECT} "
    work = f"{root}/.run/restore-drill"
    roles = compose + "exec -T postgres psql -v ON_ERROR_STOP=1 -X -q -A -t -U postgres -d postgres"
    counts = compose + "exec -T postgres psql -v ON_ERROR_STOP=1 -X -q -A -t -U postgres -d "
    app = f" | env=dev files={work}/files run={work}/run"
    script = f"env=dev dir={work}/backups run={work}/run command=make restore-drill"
    steps = [call for call in calls if " ps -q postgres" not in call and " inspect " not in call]
    assert steps == [
        "docker info",
        f"docker ps -a -q --filter label=com.docker.compose.project={PROJECT}",
        f"docker volume ls -q --filter label=com.docker.compose.project={PROJECT}",
        compose + "up -d postgres",
        roles,
        "erev migrate" + app,
        "erev seed demo --tenants avenmoor,bracken" + app,
        f"backup | {script} (backup)",
        counts + "erev",
        compose + "down -v",
        f"docker volume ls -q --filter label=com.docker.compose.project={PROJECT}",
        compose + "up -d postgres",
        roles,
        f"restore-verify | BACKUP={BACKUP_ID} RESET= dir={work}/backups run={work}/run "
        "command=make restore-drill (restore-verify)",
        counts + "erev_rv_drill",
        compose + "down -v",
    ]
    # Only the drill's project, and nothing is pushed, pulled or logged in.
    assert {m for call in calls for m in re.findall(r" -p (\S+)", call)} == {PROJECT}
    assert not any(re.match(r"docker (push|pull|login|rm|rmi|system|image)\b", c) for c in calls)

    report = _report(root)
    assert (report["result"], report["exit_code"], report["failures"]) == ("verified", 0, [])
    assert report["counts"]["stages"] == dict.fromkeys(STAGES, "pass")
    assert has_population(report["counts"])
    assert {
        key: report["counts"][key]
        for key in (
            "stages_passed",
            "tables",
            "rows_source",
            "rows_clone",
            "tables_missing_in_clone",
            "tables_with_fewer_rows",
            "tables_with_more_rows",
        )
    } == {
        "stages_passed": 12,
        "tables": 4,
        "rows_source": 360,
        "rows_clone": 362,
        "tables_missing_in_clone": 0,
        "tables_with_fewer_rows": 0,
        "tables_with_more_rows": 1,
    }
    assert report["counts"]["restore_verify"] == {"failures": 0, "files_checked": 310, "tenants": 8}
    assert report["row_counts"]["more_in_clone"] == [
        {"table": "erev.security_event", "source": 300, "clone": 302}
    ]
    assert report["cleanup"] == {"stage": "teardown", "result": "done", "exit_code": 0}
    assert (report["project"], report["port"]) == (PROJECT, f"127.0.0.1:{port}")
    assert (report["restore_database"], report["backup_id"]) == ("erev_rv_drill", BACKUP_ID)
    assert (report["tenants"], report["reset"]) == ("avenmoor,bracken", False)
    assert report["command"] == "make restore-drill"
    assert report["restore"] == {"restore_point": "2026-09-30T12:00:00Z", "evidence_lag_seconds": 3}
    assert report["restore_test_record"] == {"verification_result": "PASS"}
    assert set(report["seconds"]) == {
        "server",
        "source",
        "backup",
        "destroy_to_fresh_server",
        "restore_verify",
        "destroy_to_verified_clone",
        "total",
    }
    assert all(isinstance(value, int) and value >= 0 for value in report["seconds"].values())
    reports = root / ".run" / "reports" / "restore-drill"
    kept = {path.name for path in reports.iterdir()}
    assert {
        "report.json",
        "backup.report.json",
        "restore-verify.report.json",
        "row-counts.json",
        "row-counts-source.txt",
        "row-counts-clone.txt",
        "migrate.log",
        "seed.log",
        "backup.log",
        "restore-verify.log",
        "compose-up-source.log",
        "compose-up-fresh.log",
        "compose-destroy.log",
        "compose-down.log",
    } <= kept
    # The drill's directory — the backup set with its copy of the master keys — is gone.
    assert not (root / ".run" / "restore-drill").exists()

    # The passwords: five per run, generated, distinct, the same for both servers, handed to the
    # programs in their URLs — and written nowhere under the root nor printed.
    seen = _passwords(scratch)
    assert {row[0] for row in seen} == {port}
    (passwords,) = {row[1:] for row in seen}
    assert len(set(passwords)) == 5
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{32}", password) for password in passwords)
    _postgres, owner, app_password, backup, admin = passwords
    urls = (scratch / "urls.log").read_text("utf-8").splitlines()
    at = f"@127.0.0.1:{port}/"
    assert set(urls) == {
        f"owner postgresql://erev_owner:{owner}{at}erev",
        f"app postgresql://erev_app:{app_password}{at}erev",
        f"backup postgresql://erev_backup:{backup}{at}erev",
        f"restore-owner postgresql://erev_owner:{owner}{at}erev_rv_drill",
        f"restore-app postgresql://erev_app:{app_password}{at}erev_rv_drill",
        f"restore-admin postgresql://erev_restore_admin:{admin}{at}erev_rv_drill",
    }
    written = [done.stdout, done.stderr, "\n".join(calls)]
    written += [
        path.read_text("utf-8", errors="replace") for path in root.rglob("*") if path.is_file()
    ]
    for password in passwords:
        assert not any(password in text for text in written)
    assert not any("the-master-keys-travel-with-the-backup" in text for text in written)


def test_restore_drill_under_the_gate_wrapper_reads_the_context(scratch: Path) -> None:
    """GATE-BIND-1: under ``scripts/gate_context.sh`` the script runs in the execution context.
    Its report, the two scripts' reports and its directory lie there, and a scratch-root override
    is refused."""
    root = _root(scratch)
    env = _env(scratch, root, EREV_GATE_CONTEXT=str(root))
    refused = _run(root, env)
    assert refused.returncode == 1
    assert "FAIL restore-drill: EREV_RESTORE_DRILL_ROOT is a test-only override" in refused.stdout
    assert _calls(scratch) == []

    del env["EREV_RESTORE_DRILL_ROOT"], env["EREV_RUN_DIR"]
    done = _run(root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    report = _report(root)
    assert (report["result"], report["backup_id"]) == ("verified", BACKUP_ID)
    assert report["counts"]["restore_verify"] == {"failures": 0, "files_checked": 310, "tenants": 8}
    assert report["execution_root"] == str(root)
    # The two scripts wrote under the context, as they do under the wrapper; the drill's directory
    # was the context's and is gone.
    assert (root / ".run" / "reports" / "backup" / "report.json").is_file()
    assert (root / ".run" / "reports" / "restore-verify" / "report.json").is_file()
    assert not (root / ".run" / "restore-drill").exists()


def test_restore_drill_skips_without_a_daemon(scratch: Path) -> None:
    root = _root(scratch)
    done = _run(root, _env(scratch, root, STUB_DOCKER_INFO_RC="1"))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" in done.stdout
    assert done.stdout.splitlines()[-1] == "OK restore-drill (skipped-no-daemon)"
    report = _report(root)
    assert report["result"] == "skipped-no-daemon"
    assert set(report["counts"]["stages"].values()) == {"skipped"}
    assert report["counts"]["stages_passed"] == 0 and has_population(report["counts"])
    assert _calls(scratch) == ["docker info"]


def test_restore_drill_never_touches_another_drill_without_reset(scratch: Path) -> None:
    """A container or a volume of the project belongs to a drill that is running or was
    interrupted. Without RESET=1 the run fails and touches nothing; with it, what is left is
    removed first and the drill runs."""
    root = _root(scratch)
    env = _env(scratch, root)
    state = Path(env["STUB_STATE"])
    (state / "containers").write_text("othercontainer\n", "utf-8")
    (state / "volumes").write_text("othervolume\n", "utf-8")
    # The other drill's directory, were it running in place in this checkout.
    marker = root / ".run" / "restore-drill" / "backups" / "theirs.dump"
    marker.parent.mkdir(parents=True)
    marker.write_text("their backup\n", "utf-8")

    done = _run(root, env)
    assert done.returncode == 1
    assert done.stdout.splitlines()[-1] == (
        f"FAIL restore-drill: project {PROJECT} holds 1 container(s) and 1 volume(s) of another "
        "drill: if it is running, wait for it; if it was interrupted, rerun with RESET=1 to remove "
        "what it left"
    )
    report = _report(root)
    assert report["result"] == "project-exists"
    assert report["counts"]["stages"]["preflight"] == "fail"
    assert report["counts"]["stages"]["server"] == "not-run" and report["cleanup"] is None
    assert _calls(scratch) == [
        "docker info",
        f"docker ps -a -q --filter label=com.docker.compose.project={PROJECT}",
        f"docker volume ls -q --filter label=com.docker.compose.project={PROJECT}",
    ]
    assert marker.read_text("utf-8") == "their backup\n", "the other drill's directory is untouched"

    (scratch / "calls.log").write_text("", "utf-8")
    done = _run(root, {**env, "RESET": "1"})
    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        f"restore-drill: project {PROJECT} held 1 container(s) and 1 volume(s); removed (RESET=1)"
        in done.stdout
    )
    calls = _calls(scratch)
    # The removal names the project and the compose file only, before anything else of compose.
    assert _compose(calls, "")[0] == (
        f"docker compose -f {root}/deploy/compose.yaml --env-file "
        f"{root}/deploy/compose.env.example -p {PROJECT} down -v"
    )
    report = _report(root)
    assert (report["result"], report["reset"]) == ("verified", True)
    assert report["command"] == "make restore-drill"
    assert not marker.exists(), "a stale directory is cleared once no drill holds the project"


def test_restore_drill_refuses_a_busy_port_and_bad_variables(scratch: Path) -> None:
    root = _root(scratch)
    with _held_port() as port:
        done = _run(root, _env(scratch, root, DRILL_PORT=str(port)))
    assert done.returncode == 1
    assert done.stdout.splitlines()[-1] == (
        f"FAIL restore-drill: 127.0.0.1:{port} is in use; choose another port with "
        "DRILL_PORT=<port>"
    )
    report = _report(root)
    assert report["result"] == "port-in-use" and report["port"] == f"127.0.0.1:{port}"
    assert not _compose(_calls(scratch), ""), "no compose call before the port is free"

    for extra, result, reason in (
        ({"DRILL_PORT": "80"}, "port-invalid", "DRILL_PORT must be a port between 1024 and 65535"),
        ({"DRILL_PORT": "5446;id"}, "port-invalid", "DRILL_PORT must be a port between"),
        ({"TENANTS": "avenmoor; rm"}, "tenants-invalid", "TENANTS must be a comma-separated list"),
    ):
        (scratch / "calls.log").write_text("", "utf-8")
        done = _run(root, _env(scratch, root, **extra))
        assert done.returncode == 1 and f"FAIL restore-drill: {reason}" in done.stdout, extra
        assert _report(root)["result"] == result
        assert _calls(scratch) == [], "refused before any docker call"

    # The scratch root is a test-only override: refused outside EREV_ENV=test.
    (scratch / "calls.log").write_text("", "utf-8")
    done = _run(root, _env(scratch, root, EREV_ENV="dev"))
    assert done.returncode == 1
    assert "FAIL restore-drill: EREV_RESTORE_DRILL_ROOT is a test-only override" in done.stdout
    assert _calls(scratch) == []


@pytest.mark.parametrize(
    ("extra", "stage", "result", "log", "downs"),
    [
        ({"STUB_UP_FAIL_AT": "1"}, "server", "up-failed", "compose-up-source.log", 1),
        (
            {"STUB_HEALTH": "starting", "EREV_RESTORE_DRILL_TIMEOUT_SECONDS": "2"},
            "server",
            "not-healthy",
            "compose-up-source.log",
            1,
        ),
        ({"STUB_ROLES": "1 2"}, "roles", "roles-failed", "roles-source.log", 1),
        ({"STUB_MIGRATE_RC": "1"}, "source", "migrate-failed", "migrate.log", 1),
        ({"STUB_SEED_RC": "1"}, "source", "seed-failed", "seed.log", 1),
        ({"STUB_BACKUP_RC": "1"}, "backup", "backup-failed", "backup.log", 1),
        ({"STUB_BACKUP_ID": "latest"}, "backup", "backup-unnamed", None, 1),
        ({"STUB_NO_MANIFEST": "1"}, "backup", "backup-missing", None, 1),
        ({"STUB_VOLUME_SURVIVES": "1"}, "destroy", "destroy-failed", None, 2),
        ({"STUB_UP_FAIL_AT": "2"}, "fresh-server", "up-failed", "compose-up-fresh.log", 2),
        ({"STUB_RESTORE_RC": "1"}, "restore", "restore-failed", "restore-verify.log", 2),
    ],
)
def test_restore_drill_names_the_failed_stage_and_always_tears_down(
    extra: dict[str, str],
    stage: str,
    result: str,
    log: str | None,
    downs: int,
    scratch: Path,
) -> None:
    root = _root(scratch)
    done = _run(root, _env(scratch, root, **extra))
    assert done.returncode == 1, done.stdout + done.stderr
    final = done.stdout.splitlines()[-1]
    assert final.startswith("FAIL restore-drill: ")
    if log is not None:
        assert f"(see restore-drill/{log})" in final
        assert (root / ".run" / "reports" / "restore-drill" / log).is_file()
    report = _report(root)
    assert report["result"] == result and report["exit_code"] == 1
    assert report["failures"] == [{"stage": stage, "exit_code": 1}]
    assert report["counts"]["stages"][stage] == "fail"
    later = STAGES[STAGES.index(stage) + 1 : -1]
    assert all(report["counts"]["stages"][name] == "not-run" for name in later), later
    # The server is destroyed and the drill's directory removed on every path after the bring-up.
    assert len(_compose(_calls(scratch), "down -v")) == downs
    assert report["cleanup"] == {"stage": "teardown", "result": "done", "exit_code": 0}
    assert report["counts"]["stages"]["teardown"] == "pass"
    assert not (root / ".run" / "restore-drill").exists()


def test_restore_drill_fails_when_the_clone_lost_rows_or_a_table(scratch: Path) -> None:
    root = _root(scratch)
    for clone, reason, missing, fewer in (
        (
            "erev.audit_event|39\nerev.security_event|302\nerev.tenant|8\npublic.procrastinate_jobs|12\n",
            "0 table(s) missing and 1 with fewer rows",
            [],
            [{"table": "erev.audit_event", "source": 40, "clone": 39}],
        ),
        (
            "erev.audit_event|40\nerev.security_event|302\npublic.procrastinate_jobs|12\n",
            "1 table(s) missing and 0 with fewer rows",
            ["erev.tenant"],
            [],
        ),
    ):
        env = _env(scratch, root)
        Path(env["STUB_ROWS_CLONE"]).write_text(clone, "utf-8")
        done = _run(root, env)
        assert done.returncode == 1
        assert done.stdout.splitlines()[-1] == (
            "FAIL restore-drill: the clone does not hold what the source held: "
            f"{reason} (see restore-drill/row-counts.json)"
        )
        report = _report(root)
        assert report["result"] == "rows-lost" and report["counts"]["stages"]["compare"] == "fail"
        assert report["row_counts"]["missing_in_clone"] == missing
        assert report["row_counts"]["fewer_in_clone"] == fewer
        assert report["counts"]["stages"]["restore"] == "pass"
        assert report["cleanup"] == {"stage": "teardown", "result": "done", "exit_code": 0}

    # A source without tables is no drill at all.
    env = _env(scratch, root)
    Path(env["STUB_ROWS_SOURCE"]).write_text("", "utf-8")
    done = _run(root, env)
    assert done.returncode == 1 and "the source holds no table" in done.stdout.splitlines()[-1]


def test_restore_drill_cleanup_failure_decides_the_verdict(scratch: Path) -> None:
    root = _root(scratch)
    # The second down is the teardown of a drill that passed.
    done = _run(root, _env(scratch, root, STUB_DOWN_FAIL_AT="2"))
    assert done.returncode == 1
    assert done.stdout.splitlines()[-1].startswith(
        "FAIL restore-drill: the drill passed but compose down -v failed (exit 1); project "
        f"{PROJECT} may still be up"
    )
    report = _report(root)
    assert report["result"] == "cleanup-failed" and report["exit_code"] == 1
    assert report["failures"] == [{"stage": "teardown", "exit_code": 1}]
    assert report["cleanup"] == {"stage": "teardown", "result": "failed", "exit_code": 1}
    assert report["counts"]["stages"]["compare"] == "pass"
    assert report["counts"]["stages"]["teardown"] == "fail"
    # The backup set with its copy of the master keys is removed even then.
    assert not (root / ".run" / "restore-drill").exists()

    # After a failed stage the failed teardown joins the verdict.
    (scratch / "calls.log").write_text("", "utf-8")
    state = scratch / "state"
    for name in ("ups", "downs", "containers", "volumes"):
        (state / name).unlink(missing_ok=True)
    done = _run(root, _env(scratch, root, STUB_RESTORE_RC="1", STUB_DOWN_FAIL_AT="2"))
    assert done.returncode == 1
    assert done.stdout.splitlines()[-1].endswith("; and compose down -v failed (exit 1)")
    report = _report(root)
    assert report["result"] == "restore-failed+cleanup-failed"
    assert report["failures"] == [
        {"stage": "restore", "exit_code": 1},
        {"stage": "teardown", "exit_code": 1},
    ]


def test_the_recovery_roles_are_created_by_the_container_as_rb_11_writes_them() -> None:
    """DG-ENV-14: no script creates a role or a database. The drill's container creates the
    recovery roles and the restore target at its first start, from an init file the drill's
    override mounts beside the compose init file; the statements are the runbook's RB-11 block."""
    sql_text = (DRILL / "02-recovery-roles.sql").read_text(encoding="utf-8")
    active = "\n".join(line.split("--", 1)[0] for line in sql_text.splitlines())
    statements = [
        " ".join(s.split()) for s in re.findall(r"(?m)^((?:CREATE|GRANT|REVOKE)\b[^;]*);", active)
    ]
    runbook = (ROOT / "docs" / "guides" / "runbook.md").read_text(encoding="utf-8")
    block = (
        runbook.split("Self-hosted provisioning", 1)[1].split("```sql\n", 1)[1].split("```", 1)[0]
    )
    expected = [
        " ".join(line.split())
        .replace("'<…>'", ":'PASSWORD'")
        .replace("erev_rv_<name>", "erev_rv_drill")
        .rstrip(";")
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    assert len(expected) == 10
    assert [re.sub(r":'erev_\w+_password'", ":'PASSWORD'", s) for s in statements] == expected
    assert "PASSWORD '" not in active, "passwords are psql variables, never literals"
    assert re.findall(r"\\getenv (\w+) (\w+)", active) == [
        ("erev_backup_password", "EREV_DRILL_BACKUP_PASSWORD"),
        ("erev_restore_admin_password", "EREV_DRILL_RESTORE_ADMIN_PASSWORD"),
    ]
    # Missing or short passwords stop the file before any role exists.
    first_role = re.search(r"CREATE\s+ROLE\b", active)
    assert first_role is not None and active.index("RAISE EXCEPTION") < first_role.start()
    assert not re.search(
        r"\bALTER\s+(?:SYSTEM|ROLE)\b|\bDROP\s+\w|\bSUPERUSER\b(?<!NOSUPERUSER)", active
    )

    override = yaml.safe_load(
        (DRILL / "override.yaml").read_text(encoding="utf-8").replace("!override", "")
    )
    assert list(override["services"]) == ["postgres"]
    postgres = override["services"]["postgres"]
    assert postgres["ports"] == ["127.0.0.1:${EREV_DRILL_PORT}:5432"]
    assert postgres["environment"] == {
        "EREV_DRILL_BACKUP_PASSWORD": "${EREV_DRILL_BACKUP_PASSWORD}",
        "EREV_DRILL_RESTORE_ADMIN_PASSWORD": "${EREV_DRILL_RESTORE_ADMIN_PASSWORD}",
    }
    assert postgres["volumes"] == [
        "erev-pg:/var/lib/postgresql/data",
        "./compose/initdb/01-roles.sql:/docker-entrypoint-initdb.d/01-roles.sql:ro",
        "./compose/drill/02-recovery-roles.sql:/docker-entrypoint-initdb.d/02-recovery-roles.sql:ro",
    ]
    raw = (DRILL / "override.yaml").read_text(encoding="utf-8")
    assert raw.count("!override") == 2, "the drill's port and mounts replace the stack's"
    # The compose stack itself never mounts the drill's file.
    compose = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    assert "drill" not in compose and "erev_backup" not in compose
    assert sorted(path.name for path in DRILL.iterdir()) == [
        "02-recovery-roles.sql",
        "override.yaml",
    ]


def test_the_script_touches_one_project_and_administers_nothing() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    active = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert re.findall(r'(?m)^PROJECT="([^"]+)"', active) == [PROJECT]
    projects = re.findall(r"compose\b[^\n]*? -p (\S+)", active)
    assert len(projects) == 2 and set(projects) == {'"$PROJECT"'}, "the wrapper and the reset"
    # DG-ENV-14 and the compose init rule: the script names no init file and creates nothing.
    for forbidden in ("docker-entrypoint-initdb.d", "01-roles.sql", "02-recovery-roles.sql"):
        assert forbidden not in text, forbidden
    assert not re.search(r"(?i)\b(?:CREATE|ALTER|DROP)\s+(?:ROLE|DATABASE|USER|EXTENSION)\b", text)
    for forbidden in ("docker push", "docker login", "docker pull", "prune", '.data/backups"'):
        assert forbidden not in active, forbidden
    # Both removals are guarded against an empty variable.
    assert [target.rstrip(";") for target in re.findall(r"rm -rf (\S+)", active)] == [
        '"${WORK:?}"',
        '"${WORK:?}"',
    ]
    assert stat.S_IMODE(SCRIPT.stat().st_mode) & stat.S_IXUSR
