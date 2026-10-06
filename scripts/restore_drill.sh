#!/usr/bin/env bash
# make restore-drill (docs/dev-guide.md §4.5 DG-MK-restore-drill; §4.1 DG-MK-00a, DG-MK-00g, DG-MK-00i;
# §10.3 DG-FORBID-07, DG-FORBID-12; 05 §7.3 OPR-11, OPR-12; runbook RB-06; D-48a).
# The restore test as one command, on a throwaway PostgreSQL that is destroyed between the backup and
# the restore. Nothing of a deployment is read or written: the source is a demo seed.
#   (1) daemon: if `docker info` fails, write {"result": "skipped-no-daemon"}, print
#       "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" and exit 0 (never a pass);
#   (2) preflight: project erev-verify-drill must hold no container and no volume, and
#       127.0.0.1:<drill port> (5446; DRILL_PORT) must be free. What an interrupted drill left is
#       removed only when RESET=1 asks for it; without it the run fails and touches nothing, so a
#       drill that is running elsewhere on this daemon is never destroyed. One drill at a time per
#       daemon: a second one is refused while the first holds its server, which it does except for
#       the moment between its destroy and its fresh server;
#   (3) server: the `postgres` service of deploy/compose.yaml alone, under project erev-verify-drill,
#       with deploy/compose/drill/override.yaml on top: the drill's loopback port and, at the
#       container's first start, the recovery roles erev_backup and erev_restore_admin and the empty
#       restore target erev_rv_drill, as RB-11 provisions them (the init file beside the override;
#       nothing on the host creates a role or a database, DG-ENV-14). The three passwords of the
#       service and the two of the recovery roles are generated for the run and live in this
#       process's environment and in the container only;
#   (4) roles: as the container's superuser, confirm that the two recovery roles and the two
#       databases exist;
#   (5) source: `erev migrate`, then `erev seed demo` (EREV_ENV=dev; the master keys of .env; a file
#       root and a run directory of the drill's own; TENANTS narrows the seed);
#   (6) backup: scripts/backup.sh - the script of `make backup` - into the drill's own backup
#       directory, never .data/backups;
#   (7) the row count of every table of the source;
#   (8) destroy: `docker compose -p erev-verify-drill down -v`; the database volume is gone;
#   (9) a fresh server: (3) and (4) again;
#   (10) restore: scripts/restore_verify.sh - the script of `make restore-verify` - for the backup of
#        (6) into erev_rv_drill: restore, migrate, verify against the backup-time digests, doctor;
#   (11) the row counts of the clone against (7): no table missing and none with fewer rows (the
#        verification appends its own events, so a table may hold more);
#   (12) teardown, always, through the exit trap: down -v, and the drill's directory removed - it
#        holds the backup set, whose .env copy carries the master keys;
#   (13) .run/reports/restore-drill/report.json (DG-MK-00g), with the two scripts' reports beside it
#        as backup.report.json and restore-verify.report.json.
# Only project erev-verify-drill is ever touched; no other `-p` appears in this script. Final line
# "OK restore-drill" or "FAIL restore-drill: <reason>" (DG-MK-00a). Diagnostics name stages, the port
# and file names only; command output goes to log files next to the report, and no password, URL or
# key is printed or written.
# GATE-BIND-1 (DG-MK-00i): `make restore-drill` runs this script through scripts/gate_context.sh. The
# drill's directory is <run directory>/restore-drill; under the wrapper that is inside the execution
# context, which holds the code and a copy of .env and is removed when the run ends.
# Test-only overrides (backend/tests/unit/deploy/test_restore_drill.py): EREV_DOCKER_BIN names a
# stand-in docker; EREV_RESTORE_DRILL_ROOT a scratch root (honoured only under EREV_ENV=test without
# the wrapper); EREV_RESTORE_DRILL_EREV_BIN, EREV_RESTORE_DRILL_BACKUP_SCRIPT and
# EREV_RESTORE_DRILL_RESTORE_SCRIPT stand-ins for the three programs; EREV_RESTORE_DRILL_TIMEOUT_SECONDS
# shortens the 120 s wait for the server; EREV_PY the interpreter of the probes and the report.
set -uo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXEC_ROOT="${EREV_GATE_CONTEXT:-$PWD}"
TARGET="restore-drill"
PROJECT="erev-verify-drill"
RESTORE_DB="erev_rv_drill"
COMMAND="${EREV_RESTORE_DRILL_COMMAND:-make restore-drill}"
ROOT_OVERRIDE="${EREV_RESTORE_DRILL_ROOT:-}"
ROOT_REJECTED=""
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  ROOT="$(cd "$EREV_GATE_CONTEXT" 2>/dev/null && pwd -P)"
  [[ -z "$ROOT_OVERRIDE" ]] || ROOT_REJECTED="$ROOT_OVERRIDE"
elif [[ -n "$ROOT_OVERRIDE" && "${EREV_ENV:-}" == "test" ]]; then
  ROOT="$ROOT_OVERRIDE"
elif [[ -n "$ROOT_OVERRIDE" ]]; then
  ROOT_REJECTED="$ROOT_OVERRIDE"
  ROOT="$SCRIPT_ROOT"
else
  ROOT="$SCRIPT_ROOT"
fi
RUN_DIR="${EREV_RUN_DIR:-.run}"
[[ "$RUN_DIR" == /* ]] || RUN_DIR="$ROOT/$RUN_DIR"
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  REPORT_DIR="$EXEC_ROOT/.run/reports/$TARGET"
else
  REPORT_DIR="$RUN_DIR/reports/$TARGET"
fi
WORK="$RUN_DIR/$TARGET"
DOCKER="${EREV_DOCKER_BIN:-docker}"
if [[ -n "${EREV_PY:-}" ]]; then PY="$EREV_PY"
elif [[ -x "$SCRIPT_ROOT/backend/.venv/bin/python" ]]; then PY="$SCRIPT_ROOT/backend/.venv/bin/python"
else PY="python3"; fi
EREV="${EREV_RESTORE_DRILL_EREV_BIN:-$SCRIPT_ROOT/backend/.venv/bin/erev}"
BACKUP_SCRIPT="${EREV_RESTORE_DRILL_BACKUP_SCRIPT:-$SCRIPT_ROOT/scripts/backup.sh}"
RESTORE_SCRIPT="${EREV_RESTORE_DRILL_RESTORE_SCRIPT:-$SCRIPT_ROOT/scripts/restore_verify.sh}"
COMPOSE_FILE="deploy/compose.yaml"
ENV_FILE="deploy/compose.env.example"
OVERRIDE_FILE="deploy/compose/drill/override.yaml"
PORT="${DRILL_PORT:-5446}"
RESET="${RESET:-}"
TENANTS="${TENANTS:-}"
TIMEOUT_SECONDS="${EREV_RESTORE_DRILL_TIMEOUT_SECONDS:-120}"
STAGES="daemon preflight server roles source backup counts destroy fresh-server restore compare teardown"
STAGES_PASSED=""
STAGES_SKIPPED=""
FAIL_STAGE=""
FAIL_EXIT=""
BROUGHT_UP=""
DOWN_RC=""
DOWN_FAILED=""
TORN_DOWN=""
WORK_CREATED=""
BACKUP_ID=""
T_START="$(date +%s)"
T_SERVER=""; T_SOURCE=""; T_BACKUP_0=""; T_BACKUP_1=""; T_DESTROY=""; T_FRESH=""; T_RESTORE_0=""; T_VERIFIED=""

utc_now() { "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'; }
build_sha() { git -C "$EXEC_ROOT" rev-parse HEAD 2>/dev/null || echo "nogit"; }
sample_dirty() { if [[ -n "$(git -C "$EXEC_ROOT" status --porcelain 2>/dev/null)" ]]; then echo "true"; else echo "false"; fi; }
compose() { "$DOCKER" compose -f "$ROOT/$COMPOSE_FILE" -f "$ROOT/$OVERRIDE_FILE" --env-file "$ROOT/$ENV_FILE" -p "$PROJECT" "$@"; }
log_name() { echo "$(basename "$REPORT_DIR")/$1"; }
token() { "$PY" -c 'import secrets; print(secrets.token_urlsafe(24))'; }

write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_TARGET="$TARGET" REPORT_COMMAND="$COMMAND" REPORT_BUILD_SHA="$BUILD_SHA" REPORT_DIRTY="$DIRTY" \
    REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" REPORT_EXIT="$1" REPORT_RESULT="$2" \
    REPORT_STAGE_NAMES="$STAGES" REPORT_STAGES="$STAGES_PASSED" REPORT_STAGES_SKIPPED="$STAGES_SKIPPED" \
    REPORT_FAIL_STAGE="$FAIL_STAGE" REPORT_FAIL_EXIT="$FAIL_EXIT" REPORT_PROJECT="$PROJECT" REPORT_PORT="$PORT" \
    REPORT_RESTORE_DB="$RESTORE_DB" REPORT_BACKUP_ID="$BACKUP_ID" REPORT_TENANTS="$TENANTS" REPORT_RESET="$RESET" \
    REPORT_DOWN_RC="$DOWN_RC" REPORT_DOWN_FAILED="$DOWN_FAILED" REPORT_EXEC_ROOT="$EXEC_ROOT" REPORT_ROOT="$ROOT" \
    REPORT_T="$T_START ${T_SERVER:-0} ${T_SOURCE:-0} ${T_BACKUP_0:-0} ${T_BACKUP_1:-0} ${T_DESTROY:-0} ${T_FRESH:-0} ${T_RESTORE_0:-0} ${T_VERIFIED:-0} $(date +%s)" \
    "$PY" - "$REPORT_DIR" <<'PY'
import json
import os
import sys
from pathlib import Path

env = os.environ
directory = Path(sys.argv[1])


def load(name: str):
    try:
        return json.loads((directory / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


failures = []
if env["REPORT_FAIL_STAGE"]:
    failures.append({"stage": env["REPORT_FAIL_STAGE"], "exit_code": int(env["REPORT_FAIL_EXIT"] or 1)})
stages = {name: "pass" for name in env["REPORT_STAGES"].split()}
for name in env["REPORT_STAGES_SKIPPED"].split():
    stages.setdefault(name, "skipped")
if env["REPORT_FAIL_STAGE"]:
    stages[env["REPORT_FAIL_STAGE"]] = "fail"
if env["REPORT_DOWN_FAILED"]:
    stages["teardown"] = "fail"
    failures.append({"stage": "teardown", "exit_code": int(env["REPORT_DOWN_RC"] or 1)})
    cleanup = {"stage": "teardown", "result": "failed", "exit_code": int(env["REPORT_DOWN_RC"] or 1)}
elif env["REPORT_DOWN_RC"] == "0":
    cleanup = {"stage": "teardown", "result": "done", "exit_code": 0}
else:
    cleanup = None
for name in env["REPORT_STAGE_NAMES"].split():
    stages.setdefault(name, "not-run")
start, server, source, backup_0, backup_1, destroy, fresh, restore_0, verified, now = (
    int(value) for value in env["REPORT_T"].split()
)


def span(later: int, earlier: int):
    return later - earlier if later and earlier else None


counts = load("row-counts.json") or {}
backup = load("backup.report.json") or {}
restore = load("restore-verify.report.json") or {}
report = {
    "target": env["REPORT_TARGET"],
    "command": env["REPORT_COMMAND"],
    "build_sha": env["REPORT_BUILD_SHA"],
    "worktree_dirty": env["REPORT_DIRTY"] == "true",
    "started_at": env["REPORT_STARTED"],
    "finished_at": env["REPORT_FINISHED"],
    "exit_code": int(env["REPORT_EXIT"]),
    "result": env["REPORT_RESULT"],
    "counts": {
        "stages": stages,
        "stages_passed": sum(1 for state in stages.values() if state == "pass"),
        "tables": counts.get("tables"),
        "rows_source": counts.get("rows_source"),
        "rows_clone": counts.get("rows_clone"),
        "tables_missing_in_clone": len(counts["missing_in_clone"]) if counts else None,
        "tables_with_fewer_rows": len(counts["fewer_in_clone"]) if counts else None,
        "tables_with_more_rows": len(counts["more_in_clone"]) if counts else None,
        "restore_verify": restore.get("counts"),
    },
    "failures": failures,
    "cleanup": cleanup,
    "project": env["REPORT_PROJECT"],
    "port": f"127.0.0.1:{env['REPORT_PORT']}",
    "restore_database": env["REPORT_RESTORE_DB"],
    "tenants": env["REPORT_TENANTS"] or None,
    "reset": env["REPORT_RESET"] == "1",
    "backup_id": env["REPORT_BACKUP_ID"] or None,
    # Seconds, measured by this script: the server of step (3) with its roles; migrate and seed; the
    # backup script; from the start of the destroy to the fresh server with its roles; the restore
    # script; from the start of the destroy to the verified clone; the whole drill.
    "seconds": {
        "server": span(server, start),
        "source": span(source, server),
        "backup": span(backup_1, backup_0),
        "destroy_to_fresh_server": span(fresh, destroy),
        "restore_verify": span(verified, restore_0),
        "destroy_to_verified_clone": span(verified, destroy),
        "total": now - start,
    },
    "row_counts": counts or None,
    # What the restore script measured (05 OPR-12), copied from its report.
    "restore": restore.get("restore"),
    "restore_test_record": restore.get("restore_test_record"),
    "backup_report": "backup.report.json" if backup else None,
    "restore_report": "restore-verify.report.json" if restore else None,
    "execution_root": env["REPORT_EXEC_ROOT"],
    "root": env["REPORT_ROOT"],
}
with open(directory / "report.json", "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

tear_down() {
  # (12) always. A failed down is recorded and decides the verdict and the exit code.
  [[ -z "$TORN_DOWN" ]] || return 0
  TORN_DOWN="1"
  if [[ -n "$BROUGHT_UP" ]]; then
    compose down -v >"$REPORT_DIR/compose-down.log" 2>&1
    DOWN_RC=$?
    if [[ "$DOWN_RC" -eq 0 ]]; then
      STAGES_PASSED="$STAGES_PASSED teardown"
    else
      DOWN_FAILED="1"
      echo "$TARGET: compose down -v failed (exit $DOWN_RC; see $(log_name compose-down.log)); project $PROJECT may still be up"
    fi
  fi
  # The backup set (its .env copy carries the master keys), the seeded files and the restore
  # directory. Only the run that created the directory removes it: a run refused by the preflight
  # leaves it alone.
  if [[ -n "$WORK_CREATED" ]]; then rm -rf "${WORK:?}"; fi
}

fail() {
  # fail <stage> <exit code> <result> <reason>
  FAIL_STAGE="$1"; FAIL_EXIT="$2"
  local result="$3" reason="$4"
  tear_down
  if [[ -n "$DOWN_FAILED" ]]; then
    result="$result+cleanup-failed"
    reason="$reason; and compose down -v failed (exit $DOWN_RC)"
  fi
  write_report 1 "$result"
  echo "FAIL $TARGET: $reason"
  exit 1
}
trap tear_down EXIT

BUILD_SHA="$(build_sha)"
DIRTY="$(sample_dirty)"
STARTED_AT="$(utc_now)"
mkdir -p "$REPORT_DIR"
# The report directory holds only what this run writes.
rm -f "${REPORT_DIR:?}"/*.log "${REPORT_DIR:?}"/*.json "${REPORT_DIR:?}"/*.txt

if [[ -n "$ROOT_REJECTED" ]]; then
  STAGES_SKIPPED="$STAGES"
  fail "source" 1 "foreign-root" "EREV_RESTORE_DRILL_ROOT is a test-only override (EREV_ENV=test, outside the wrapper)"
fi
if ! [[ "$PORT" =~ ^[0-9]{4,5}$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  STAGES_SKIPPED="$STAGES"
  fail "preflight" 1 "port-invalid" "DRILL_PORT must be a port between 1024 and 65535"
fi
if [[ -n "$TENANTS" ]] && ! [[ "$TENANTS" =~ ^[a-z0-9,-]+$ ]]; then
  STAGES_SKIPPED="$STAGES"
  fail "preflight" 1 "tenants-invalid" "TENANTS must be a comma-separated list of demo workspace codes"
fi

# (1) daemon
if ! "$DOCKER" info >/dev/null 2>&1; then
  STAGES_SKIPPED="$STAGES"
  write_report 0 "skipped-no-daemon"
  echo "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable"
  echo "OK $TARGET (skipped-no-daemon)"
  exit 0
fi
STAGES_PASSED="daemon"

# (2) preflight. Nothing of the project is touched unless RESET=1 asks for it: containers or volumes
#     of the project belong to a drill that is running (here or from another checkout on this
#     daemon) or to one that was interrupted, and only the operator knows which.
leftovers() {
  LEFT_CONTAINERS="$("$DOCKER" ps -a -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null | wc -l | tr -d ' ')"
  LEFT_VOLUMES="$("$DOCKER" volume ls -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$LEFT_CONTAINERS" != "0" || "$LEFT_VOLUMES" != "0" ]]
}
if leftovers; then
  if [[ "$RESET" == "1" ]]; then
    "$DOCKER" compose -f "$ROOT/$COMPOSE_FILE" --env-file "$ROOT/$ENV_FILE" -p "$PROJECT" down -v >"$REPORT_DIR/compose-reset.log" 2>&1 \
      || fail "preflight" $? "reset-failed" "RESET=1 could not remove what project $PROJECT held (see $(log_name compose-reset.log))"
    echo "$TARGET: project $PROJECT held $LEFT_CONTAINERS container(s) and $LEFT_VOLUMES volume(s); removed (RESET=1)"
  else
    fail "preflight" 1 "project-exists" "project $PROJECT holds $LEFT_CONTAINERS container(s) and $LEFT_VOLUMES volume(s) of another drill: if it is running, wait for it; if it was interrupted, rerun with RESET=1 to remove what it left"
  fi
fi
BUSY="$("$PY" - "$PORT" <<'PROBE'
import socket, sys
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", int(sys.argv[1])))
    except OSError:
        print(sys.argv[1])
PROBE
)"
[[ -z "$BUSY" ]] || fail "preflight" 1 "port-in-use" "127.0.0.1:$PORT is in use; choose another port with DRILL_PORT=<port>"
# The drill's directory, from here on this run's own: no drill is running, so what is there is stale.
rm -rf "${WORK:?}"
{ mkdir -p "$WORK" && chmod 700 "$WORK"; } || fail "preflight" 1 "workdir-failed" "the drill directory could not be created"
WORK_CREATED="1"
STAGES_PASSED="$STAGES_PASSED preflight"

# The run's passwords: URL-safe, generated here, exported for compose (which prefers the process
# environment to the env file and hands them to the container) and used in the URLs below;
# written to no file and no report. EREV_DRILL_PORT is the override's port.
{ EREV_COMPOSE_POSTGRES_PASSWORD="$(token)" && EREV_COMPOSE_OWNER_PASSWORD="$(token)" \
  && EREV_COMPOSE_APP_PASSWORD="$(token)" && EREV_DRILL_BACKUP_PASSWORD="$(token)" \
  && EREV_DRILL_RESTORE_ADMIN_PASSWORD="$(token)"; } \
  || fail "server" 1 "passwords-failed" "the run's passwords could not be generated"
EREV_DRILL_PORT="$PORT"
export EREV_COMPOSE_POSTGRES_PASSWORD EREV_COMPOSE_OWNER_PASSWORD EREV_COMPOSE_APP_PASSWORD
export EREV_DRILL_BACKUP_PASSWORD EREV_DRILL_RESTORE_ADMIN_PASSWORD EREV_DRILL_PORT
HOSTPORT="127.0.0.1:$PORT"

start_server() {
  # start_server <log suffix>: up, wait until healthy, then confirm the roles and the databases.
  local suffix="$1" health="" waited=0 container="" found=""
  BROUGHT_UP="1"
  compose up -d postgres >"$REPORT_DIR/compose-up-$suffix.log" 2>&1 || return 10
  while (( waited < TIMEOUT_SECONDS )); do
    container="$(compose ps -q postgres 2>/dev/null | head -n 1)"
    [[ -z "$container" ]] || health="$("$DOCKER" inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || true)"
    [[ "$health" == "healthy" ]] && break
    sleep 2; waited=$((waited + 2))
  done
  [[ "$health" == "healthy" ]] || return 11
  # The container's first start ran the init files the override mounts: the compose roles and
  # database, then the recovery roles and the restore target of RB-11. Confirm what the drill
  # needs: two BYPASSRLS roles that are no superusers, and the two databases.
  found="$(compose exec -T postgres psql -v ON_ERROR_STOP=1 -X -q -A -t -U postgres -d postgres 2>"$REPORT_DIR/roles-$suffix.log" <<SQL
select (select count(*) from pg_roles where rolname in ('erev_backup', 'erev_restore_admin') and rolbypassrls and not rolsuper)
       || ' ' || (select count(*) from pg_database where datname in ('erev', '$RESTORE_DB'));
SQL
)" || return 12
  [[ "$found" == "2 2" ]] || { echo "recovery roles and databases found: ${found:-none} (expected 2 2)" >>"$REPORT_DIR/roles-$suffix.log"; return 12; }
  return 0
}

server_failure() {
  # server_failure <stage> <return code of start_server> <log suffix>
  case "$2" in
    10) fail "$1" 1 "up-failed" "docker compose up postgres failed (see $(log_name "compose-up-$3.log"))" ;;
    11) fail "$1" 1 "not-healthy" "the postgres container was not healthy within ${TIMEOUT_SECONDS}s (see $(log_name "compose-up-$3.log"))" ;;
    *) fail "roles" 1 "roles-failed" "the container did not come up with the recovery roles and the restore target (see $(log_name "roles-$3.log"))" ;;
  esac
}

drill_env() {
  # The environment of the application programs: the drill's server, files and run directory.
  # The master keys come from .env, as they do for the deployment the two scripts are written for.
  env EREV_ENV=dev \
    EREV_DB_OWNER_URL="postgresql://erev_owner:${EREV_COMPOSE_OWNER_PASSWORD}@${HOSTPORT}/erev" \
    EREV_DB_APP_URL="postgresql://erev_app:${EREV_COMPOSE_APP_PASSWORD}@${HOSTPORT}/erev" \
    EREV_BACKUP_URL="postgresql://erev_backup:${EREV_DRILL_BACKUP_PASSWORD}@${HOSTPORT}/erev" \
    EREV_RESTORE_OWNER_URL="postgresql://erev_owner:${EREV_COMPOSE_OWNER_PASSWORD}@${HOSTPORT}/${RESTORE_DB}" \
    EREV_RESTORE_APP_URL="postgresql://erev_app:${EREV_COMPOSE_APP_PASSWORD}@${HOSTPORT}/${RESTORE_DB}" \
    EREV_RESTORE_ADMIN_URL="postgresql://erev_restore_admin:${EREV_DRILL_RESTORE_ADMIN_PASSWORD}@${HOSTPORT}/${RESTORE_DB}" \
    EREV_FILE_ROOT="$WORK/files" EREV_RUN_DIR="$WORK/run" EREV_BACKUP_DIR="$WORK/backups" \
    "$@"
}

row_counts() {
  # row_counts <database> <file>: "schema.table|rows" for schema erev and the Procrastinate tables,
  # as the container's superuser (row-level security does not apply to it).
  compose exec -T postgres psql -v ON_ERROR_STOP=1 -X -q -A -t -U postgres -d "$1" >"$2" 2>>"$REPORT_DIR/row-counts.log" <<'SQL'
select format('%I.%I', n.nspname, c.relname) || '|' ||
       (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname), false, true, '')))[1]::text
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind in ('r', 'p') and (n.nspname = 'erev' or (n.nspname = 'public' and c.relname like 'procrastinate%'))
order by 1;
SQL
}

inner_report() {
  # inner_report <script target>: where backup.sh and restore_verify.sh write their report - under
  # the execution context when there is one, else under their run directory, which is the drill's.
  # Never the worktree's own .run/reports/<target>/: that holds the deployment's last backup or
  # restore, and the drill must neither read nor replace it.
  if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then echo "$EREV_GATE_CONTEXT/.run/reports/$1/report.json"
  else echo "$WORK/run/reports/$1/report.json"; fi
}

# (3), (4) the server and its roles
start_server source || server_failure "server" $? source
T_SERVER="$(date +%s)"
STAGES_PASSED="$STAGES_PASSED server roles"

# (5) the source: migrate, then the demo seed
mkdir -p "$WORK/files" "$WORK/run" "$WORK/backups"
drill_env "$EREV" migrate >"$REPORT_DIR/migrate.log" 2>&1 \
  || fail "source" $? "migrate-failed" "erev migrate failed on the drill's server (see $(log_name migrate.log))"
if [[ -n "$TENANTS" ]]; then
  drill_env "$EREV" seed demo --tenants "$TENANTS" >"$REPORT_DIR/seed.log" 2>&1
else
  drill_env "$EREV" seed demo >"$REPORT_DIR/seed.log" 2>&1
fi || fail "source" $? "seed-failed" "erev seed demo failed (see $(log_name seed.log))"
T_SOURCE="$(date +%s)"
STAGES_PASSED="$STAGES_PASSED source"

# (6) the backup
T_BACKUP_0="$(date +%s)"
rm -f "$(inner_report backup)"
drill_env env EREV_BACKUP_COMMAND="$COMMAND (backup)" "$BACKUP_SCRIPT" >"$REPORT_DIR/backup.log" 2>&1
BACKUP_RC=$?
T_BACKUP_1="$(date +%s)"
cp "$(inner_report backup)" "$REPORT_DIR/backup.report.json" 2>/dev/null || true
[[ "$BACKUP_RC" -eq 0 ]] || fail "backup" "$BACKUP_RC" "backup-failed" "the backup failed (see $(log_name backup.log))"
BACKUP_ID="$("$PY" - "$REPORT_DIR/backup.report.json" <<'PY'
import json, re, sys
try:
    value = str(json.load(open(sys.argv[1], encoding="utf-8")).get("backup_id") or "")
except (OSError, ValueError):
    value = ""
print(value if re.fullmatch(r"erev-\d{8}T\d{6}Z", value) else "")
PY
)"
[[ -n "$BACKUP_ID" ]] || fail "backup" 1 "backup-unnamed" "the backup report names no backup id"
[[ -f "$WORK/backups/$BACKUP_ID.manifest.json" ]] \
  || fail "backup" 1 "backup-missing" "the backup set $BACKUP_ID is not in the drill's backup directory"
STAGES_PASSED="$STAGES_PASSED backup"

# (7) what the source holds
row_counts erev "$REPORT_DIR/row-counts-source.txt" \
  || fail "counts" $? "counts-failed" "the source's row counts could not be read (see $(log_name row-counts.log))"
STAGES_PASSED="$STAGES_PASSED counts"

# (8) destroy the server and its volume
T_DESTROY="$(date +%s)"
compose down -v >"$REPORT_DIR/compose-destroy.log" 2>&1 \
  || fail "destroy" $? "destroy-failed" "docker compose down -v failed (see $(log_name compose-destroy.log))"
LEFT_VOLUMES="$("$DOCKER" volume ls -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null | wc -l | tr -d ' ')"
[[ "$LEFT_VOLUMES" == "0" ]] || fail "destroy" 1 "destroy-failed" "a volume of project $PROJECT outlived the destroy"
STAGES_PASSED="$STAGES_PASSED destroy"

# (9) a fresh server
start_server fresh || server_failure "fresh-server" $? fresh
T_FRESH="$(date +%s)"
STAGES_PASSED="$STAGES_PASSED fresh-server"

# (10) restore and verify
T_RESTORE_0="$(date +%s)"
rm -f "$(inner_report restore-verify)"
drill_env env BACKUP="$BACKUP_ID" RESET="" EREV_RESTORE_COMMAND="$COMMAND (restore-verify)" "$RESTORE_SCRIPT" >"$REPORT_DIR/restore-verify.log" 2>&1
RESTORE_RC=$?
T_VERIFIED="$(date +%s)"
cp "$(inner_report restore-verify)" "$REPORT_DIR/restore-verify.report.json" 2>/dev/null || true
[[ "$RESTORE_RC" -eq 0 ]] || fail "restore" "$RESTORE_RC" "restore-failed" "the restore or its verification failed (see $(log_name restore-verify.log))"
STAGES_PASSED="$STAGES_PASSED restore"

# (11) the clone against the source
row_counts "$RESTORE_DB" "$REPORT_DIR/row-counts-clone.txt" \
  || fail "compare" $? "counts-failed" "the clone's row counts could not be read (see $(log_name row-counts.log))"
VERDICT="$("$PY" - "$REPORT_DIR" <<'PY'
import json, sys
from pathlib import Path

directory = Path(sys.argv[1])


def load(name: str) -> dict[str, int]:
    rows = {}
    for line in (directory / name).read_text(encoding="utf-8").splitlines():
        if line.strip():
            table, count = line.strip().rsplit("|", 1)
            rows[table] = int(count)
    return rows


source, clone = load("row-counts-source.txt"), load("row-counts-clone.txt")
differing = [
    {"table": table, "source": source[table], "clone": clone[table]}
    for table in sorted(source)
    if table in clone and clone[table] != source[table]
]
result = {
    "tables": len(source),
    "rows_source": sum(source.values()),
    "rows_clone": sum(clone.values()),
    "missing_in_clone": sorted(set(source) - set(clone)),
    "extra_in_clone": sorted(set(clone) - set(source)),
    "fewer_in_clone": [row for row in differing if row["clone"] < row["source"]],
    "more_in_clone": [row for row in differing if row["clone"] > row["source"]],
}
(directory / "row-counts.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not source:
    print("EMPTY the source holds no table")
elif result["missing_in_clone"] or result["fewer_in_clone"]:
    print(f"LOSS {len(result['missing_in_clone'])} table(s) missing and {len(result['fewer_in_clone'])} with fewer rows")
else:
    print(f"OK {result['tables']} tables; {result['rows_source']} rows in the source, {result['rows_clone']} in the clone; {len(result['more_in_clone'])} table(s) hold more")
PY
)"
case "$VERDICT" in
  OK*) ;;
  EMPTY*|LOSS*) fail "compare" 1 "rows-lost" "the clone does not hold what the source held: ${VERDICT#* } (see $(log_name row-counts.json))" ;;
  *) fail "compare" 1 "counts-failed" "the row counts could not be compared" ;;
esac
STAGES_PASSED="$STAGES_PASSED compare"

# (12) teardown, (13) report
tear_down
if [[ -n "$DOWN_FAILED" ]]; then
  write_report 1 "cleanup-failed"
  echo "FAIL $TARGET: the drill passed but compose down -v failed (exit $DOWN_RC); project $PROJECT may still be up (see $(log_name compose-down.log))"
  exit 1
fi
write_report 0 "verified"
echo "$TARGET: backup $BACKUP_ID restored into a fresh server; ${VERDICT#OK }; backup $((T_BACKUP_1 - T_BACKUP_0))s, destroy to verified clone $((T_VERIFIED - T_DESTROY))s, drill $(( $(date +%s) - T_START ))s"
echo "OK $TARGET"
