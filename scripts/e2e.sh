#!/usr/bin/env bash
# make e2e (docs/dev-guide.md §4.4 DG-MK-e2e; §9.8 DG-E2E-01 to DG-E2E-04, DG-E2E-11; DG-MK-00e,
# DG-MK-00g; PHASES BS-D-20; BUILD_SPEC WEB-11).
#   (1) fail when EREV_DEMO_PASSWORD is absent from the environment and the .env file, before any port;
#   (2) take the e2e-ports lock; (3) reset schema erev in the e2e database and migrate; (4) seed the demo
#   world; (5) build the frontend with the design gallery; (6) start api-e2e, worker-e2e and web-e2e by
#   PID file; (7) run the Playwright projects in DG-E2E-02 order, each as its own invocation, skipping a
#   project that holds no test yet; (8) on exit stop the three processes, write
#   .run/reports/e2e/report.json and release the lock. The exit code is the first non-zero Playwright
#   exit code, else 0.
#   SPEC     a journey id (J-05), a comma-separated list, or a spec path (DG-E2E-04)
#   PROJECT  a project name or a comma-separated list restricting the DG-E2E-02 projects
#   CLOSE    1 = the run on the closed world (DG-MK-e2e rev 1.277): the seed with --with-close and
#            the one project `closed`; without it that project is neither listed nor run.
#            PROJECT=qa-rc, alone or after closed, also runs the release candidate's multi-role
#            browser QA there (DG-E2E-14 rev 1.280): a pass no run takes unless it is named
# Sourcing the script defines the functions and runs nothing (backend/tests/unit/test_e2e_script.py).
set -uo pipefail

# shellcheck source=scripts/proc.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/proc.sh"

EREV="$ROOT/backend/.venv/bin/erev"
PLAYWRIGHT="$ROOT/frontend/node_modules/.bin/playwright"
PLAYWRIGHT_CONFIG="frontend/e2e/playwright.config.ts"
VITE="frontend/node_modules/vite/bin/vite.js"
LOCK_DIR="$RUN_DIR/locks/e2e-ports"
# GATE-BIND-1 (DG-MK-00i): under scripts/gate_context.sh the report is written in the execution
# context (EREV_REPORTS_DIR) while PID files, logs and the ports lock stay in EREV_RUN_DIR.
REPORT_DIR="${EREV_REPORTS_DIR:-$RUN_DIR/reports}/e2e"
# DG-E2E-02: projects in execution order.
PROJECTS="avenmoor-serial fresh-tenant industry screens design crawl"
# DG-E2E-02 rev 1.277: the project of a CLOSE=1 run. It reads the months the seed closes when
# asked (BUILD_SPEC CLO-22); the projects above need every period of 2026 open, as the seed
# leaves them otherwise, so the two worlds share no run.
CLOSED_PROJECTS="closed"
# DG-E2E-02 rev 1.280, DG-E2E-14: a project of the closed world that runs only when PROJECT names
# it, after the list above. The release candidate's multi-role browser QA writes a record, invites
# a member and locks a month: the world it leaves is not the seeded one, so no run takes it unasked.
CLOSED_BY_NAME="qa-rc"
# docs/02-PRD.md E2E-04: the serial journeys in order.
SERIAL_JOURNEYS="J-02 J-03 J-04 J-05 J-06 J-07 J-08 J-09 J-10 J-11 J-12 J-16 J-19 J-26 J-13 J-14 J-15 J-17 J-18 J-25 J-22"
PASSWORD_MESSAGE="EREV_DEMO_PASSWORD is not set. Copy it from .env.example."

LOCK_TAKEN=0
FINISHED=0
E2E_EXIT=0
RUN_INDEX=0
STARTED_AT=""
E2E_API_PORT=""
E2E_WEB_PORT=""

workers_of() {
  case "$1" in
    avenmoor-serial | design | qa-rc) echo 1 ;;
    fresh-tenant) echo 4 ;;
    *) echo 2 ;;
  esac
}

# dotenv_value <name>: the named line of the .env file named by EREV_DOTENV (ruling D-80), without
# surrounding quotes. The value is never printed.
dotenv_value() {
  local file="${EREV_DOTENV:-.env}" value
  [[ "$file" == /* ]] || file="$ROOT/$file"
  [[ -f "$file" ]] || return 0
  value="$(sed -n "s/^$1=//p" "$file" | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

# (1) WLD-U-R1, DG-RUN-32: the demo password, and the TOTP seed when present, reach Playwright.
require_password() {
  if [[ -z "${EREV_DEMO_PASSWORD:-}" ]]; then
    EREV_DEMO_PASSWORD="$(dotenv_value EREV_DEMO_PASSWORD)"
  fi
  if [[ -z "${EREV_DEMO_PASSWORD:-}" ]]; then
    echo "$PASSWORD_MESSAGE"
    return 1
  fi
  export EREV_DEMO_PASSWORD
  if [[ -z "${EREV_DEMO_TOTP_SECRET:-}" ]]; then
    EREV_DEMO_TOTP_SECRET="$(dotenv_value EREV_DEMO_TOTP_SECRET)"
  fi
  if [[ -n "${EREV_DEMO_TOTP_SECRET:-}" ]]; then
    export EREV_DEMO_TOTP_SECRET
  fi
  return 0
}

# with_close: CLOSE=1 asks for the run on the closed world.
with_close() {
  [[ "${CLOSE:-}" == "1" ]]
}

# The projects of this run, in execution order.
run_kind_projects() {
  if with_close; then
    echo "$CLOSED_PROJECTS"
  else
    echo "$PROJECTS"
  fi
}

# The projects PROJECT may name in this run: its list and, on the closed world, those run by name.
nameable_projects() {
  if with_close; then
    echo "$CLOSED_PROJECTS $CLOSED_BY_NAME"
  else
    echo "$PROJECTS"
  fi
}

validate_projects() {
  local name projects nameable
  [[ -n "${PROJECT:-}" ]] || return 0
  projects="$(run_kind_projects)"
  nameable="$(nameable_projects)"
  for name in $(printf '%s' "$PROJECT" | tr ',' ' '); do
    if [[ " $nameable " != *" $name "* ]]; then
      if [[ " $CLOSED_PROJECTS $CLOSED_BY_NAME " == *" $name "* ]]; then
        echo "project $name runs on the closed world only: make e2e CLOSE=1 PROJECT=$name"
      elif [[ " $PROJECTS " == *" $name "* ]]; then
        echo "project $name does not run on the closed world (CLOSE=1); projects: $projects"
      else
        echo "unknown project $name; projects: $projects"
      fi
      return 1
    fi
  done
  return 0
}

selected_projects() {
  local project
  for project in $(run_kind_projects); do
    if [[ -z "${PROJECT:-}" || ",$PROJECT," == *",$project,"* ]]; then
      echo "$project"
    fi
  done
  # DG-E2E-14: a project run by name only comes after the run's list, and never without its name.
  if with_close && [[ -n "${PROJECT:-}" ]]; then
    for project in $CLOSED_BY_NAME; do
      if [[ ",$PROJECT," == *",$project,"* ]]; then
        echo "$project"
      fi
    done
  fi
}

# (2) DG-MK-00e: a directory lock holding the owner's PID; a lock whose PID is dead is taken over.
take_lock() {
  local holder
  mkdir -p "$RUN_DIR/locks" || return 1
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    holder="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    if pid_alive "$holder"; then
      echo "e2e ports busy (pid $holder)"
      return 1
    fi
    rm -rf "$LOCK_DIR"
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
      echo "e2e ports lock $LOCK_DIR could not be taken"
      return 1
    fi
  fi
  echo "$$" >"$LOCK_DIR/pid"
  LOCK_TAKEN=1
  return 0
}

release_lock() {
  if [[ "$LOCK_TAKEN" == "1" ]]; then
    rm -rf "$LOCK_DIR"
    LOCK_TAKEN=0
  fi
}

# DG-E2E-01: the e2e ports, from the environment or the .env file, else 8199 and 5279.
e2e_ports() {
  E2E_API_PORT="$(env_port EREV_E2E_API_PORT 8199)"
  E2E_WEB_PORT="$(env_port EREV_E2E_WEB_PORT 5279)"
  export EREV_E2E_API_PORT="$E2E_API_PORT" EREV_E2E_WEB_PORT="$E2E_WEB_PORT"
}

# (3) DG-ENV-13: drop schema erev and the Procrastinate objects of the e2e database as erev_owner, then
# migrate. Only erev_e2e, or the erev_rv_*_e2e database of a review worktree (D-81), is reset.
reset_database() {
  EREV_ENV=e2e "$PY" - <<'PY' || return 1
import re
import sys

from erev_api.config import Environment, get_settings
from erev_api.db import migration_ops
from erev_api.db.session import OWNER_ROLE, build_engine
from sqlalchemy import text

ALLOWED = re.compile(r"^(erev_e2e|erev_rv_[a-z0-9_]+_e2e)$")
settings = get_settings()
database = settings.database_name()
if settings.env is not Environment.E2E or not ALLOWED.fullmatch(database):
    print(f"refusing to reset database {database}: EREV_ENV=e2e on erev_e2e or erev_rv_*_e2e only")
    sys.exit(1)
engine = build_engine(settings.owner_database_url(), role=OWNER_ROLE, component="e2e")
try:
    with engine.connect() as connection:
        current = connection.execute(text("SELECT current_database()")).scalar_one()
    if not ALLOWED.fullmatch(current):
        print(f"refusing to reset database {current}")
        sys.exit(1)
    # D-85 (L3-1-Q-24): the partitioned tables go first, one per transaction, so that the schema
    # drop stays within the shared lock table (max_locks_per_transaction).
    migration_ops.drop_partitioned_tables(engine)
    with engine.begin() as connection:
        current = connection.execute(text("SELECT current_database()")).scalar_one()
        if not ALLOWED.fullmatch(current):
            print(f"refusing to reset database {current}")
            sys.exit(1)
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS erev CASCADE")
        with migration_ops.bound_to(connection):
            migration_ops.drop_procrastinate_schema()
finally:
    engine.dispose()
print(f"schema erev and the Procrastinate objects dropped in {database}")
PY
  make --no-print-directory -C "$ROOT" migrate DB=e2e
}

# (4) E2E-03: the deterministic demo world of WLD-T-00 to WLD-T-07. Under CLOSE=1 with the close
# stage (DG-MK-seed rev 1.221), which a tenant takes at its seed or not at all.
seed_world() {
  if with_close; then
    (cd "$ROOT" && EREV_ENV=e2e "$EREV" seed demo --tenants all --with-close)
  else
    (cd "$ROOT" && EREV_ENV=e2e "$EREV" seed demo --tenants all)
  fi
}

# (5) DG-RUN-06: a production build with the design gallery.
build_web() {
  (cd "$ROOT" && VITE_EREV_DESIGN_GALLERY=1 EREV_API_PROXY_TARGET="http://127.0.0.1:$E2E_API_PORT" \
    EREV_VITE_MODE=e2e node "$VITE" build --config frontend/vite.config.ts)
}

# (6) DG-RUN-04 to DG-RUN-06, by PID file (DG-RUN-10).
start_stack() {
  local origin="http://127.0.0.1:$E2E_WEB_PORT"
  EREV_ENV=e2e EREV_PUBLIC_ORIGIN="$origin" "$ROOT/scripts/proc.sh" start api-e2e "$E2E_API_PORT" -- \
    backend/.venv/bin/uvicorn erev_api.main:create_app --factory --host 127.0.0.1 \
    --port "$E2E_API_PORT" --no-access-log || return 1
  EREV_ENV=e2e EREV_PUBLIC_ORIGIN="$origin" "$ROOT/scripts/proc.sh" start worker-e2e - -- \
    backend/.venv/bin/erev worker --heartbeat-file "$RUN_DIR/worker-e2e.heartbeat" || return 1
  EREV_API_PROXY_TARGET="http://127.0.0.1:$E2E_API_PORT" EREV_E2E_WEB_PORT="$E2E_WEB_PORT" \
    EREV_VITE_MODE=e2e VITE_EREV_DESIGN_GALLERY=1 "$ROOT/scripts/proc.sh" start web-e2e "$E2E_WEB_PORT" -- \
    node "$VITE" preview --config frontend/vite.config.ts || return 1
}

# (8) DG-RUN-11: stop by PID file only; a missing PID file is not an error.
stack_down() {
  "$ROOT/scripts/proc.sh" stop web-e2e
  "$ROOT/scripts/proc.sh" stop worker-e2e
  "$ROOT/scripts/proc.sh" stop api-e2e
}

stack_up() {
  # Processes left by an interrupted run belong to this lock holder's worktree.
  stack_down >/dev/null
  rm -rf "$ROOT/frontend/e2e/.results/network"
  reset_database || { echo "e2e database reset or migration failed"; return 1; }
  seed_world || { echo "erev seed demo failed"; return 1; }
  build_web || { echo "frontend build failed"; return 1; }
  start_stack || { echo "e2e stack did not start; see the api-e2e, worker-e2e and web-e2e logs in $RUN_DIR"; return 1; }
}

# record <key> <value> ...: one JSON line of the run record.
record() {
  mkdir -p "$REPORT_DIR"
  "$PY" -c 'import json, sys; a = sys.argv[1:]; print(json.dumps(dict(zip(a[0::2], a[1::2]))))' "$@" \
    >>"$REPORT_DIR/projects.jsonl"
}

# pw <project> <SPEC item or ""> <arguments...>: Playwright for one project with the DG-E2E-04 filter.
pw() {
  local project="$1" item="$2" until=""
  shift 2
  if [[ "$item" =~ ^J-[0-9][0-9]$ ]]; then
    if [[ "$project" == "avenmoor-serial" && " $SERIAL_JOURNEYS " == *" $item "* ]]; then
      until="$item"
    else
      set -- "$@" --grep "^$item "
    fi
  elif [[ -n "$item" ]]; then
    set -- "$@" "$item"
  fi
  (
    cd "$ROOT" || exit 1
    if [[ -n "$until" ]]; then
      export EREV_E2E_UNTIL="$until"
    else
      unset EREV_E2E_UNTIL
    fi
    # The Playwright configuration lists the project `closed` in a CLOSE=1 run and in no other,
    # whatever the caller's environment holds.
    if with_close; then
      export EREV_E2E_CLOSE=1
    else
      unset EREV_E2E_CLOSE
    fi
    exec "$PLAYWRIGHT" test -c "$PLAYWRIGHT_CONFIG" --project "$project" "$@"
  )
}

# count_tests <project> <SPEC item or "">: the "Total: N tests" figure of `playwright test --list`.
count_tests() {
  local output total
  output="$(PLAYWRIGHT_JSON_OUTPUT_FILE="$REPORT_DIR/list.json" pw "$1" "$2" --list --pass-with-no-tests 2>&1)"
  total="$(printf '%s\n' "$output" | sed -n 's/^Total: \([0-9][0-9]*\) tests\{0,1\} in .*$/\1/p' | tail -n 1)"
  if [[ -z "$total" ]]; then
    printf '%s\n' "$output" >&2
    return 1
  fi
  printf '%s\n' "$total"
}

note_exit() {
  if [[ "$1" != "0" && "$E2E_EXIT" == "0" ]]; then
    E2E_EXIT="$1"
  fi
}

run_project() {
  local project="$1" item="$2" total workers report rc
  if [[ -n "$item" ]]; then
    if ! total="$(count_tests "$project" "$item")"; then
      echo "$project: listing tests for SPEC $item failed"
      record stage "$project" spec "$item" exit_code 1
      note_exit 1
      return 0
    fi
    if [[ "$total" == "0" ]]; then
      echo "$project: skipped, SPEC $item selects no test"
      record project "$project" skipped "not selected by SPEC" spec "$item"
      return 0
    fi
  fi
  RUN_INDEX=$((RUN_INDEX + 1))
  workers="$(workers_of "$project")"
  report="playwright-$RUN_INDEX-$project.json"
  echo "== e2e: project $project --workers=$workers${item:+ SPEC $item} =="
  PLAYWRIGHT_JSON_OUTPUT_FILE="$REPORT_DIR/$report" pw "$project" "$item" --workers="$workers"
  rc=$?
  record project "$project" spec "$item" workers "$workers" exit_code "$rc" report "$report"
  note_exit "$rc"
}

# (7) DG-E2E-02 order; BS-D-20: a project without tests is skipped and recorded.
run_projects() {
  local project item total
  for project in $(selected_projects); do
    if ! total="$(count_tests "$project" "")"; then
      echo "$project: listing tests failed"
      record stage "$project" exit_code 1
      note_exit 1
      continue
    fi
    if [[ "$total" == "0" ]]; then
      echo "$project: skipped, no tests yet"
      record project "$project" skipped "no tests yet"
      continue
    fi
    if [[ -z "${SPEC:-}" ]]; then
      run_project "$project" ""
      continue
    fi
    for item in $(printf '%s' "$SPEC" | tr ',' ' '); do
      run_project "$project" "$item"
    done
  done
}

# DG-MK-00g: the gate report, on success and on failure, with Playwright's per-project statistics.
write_report() {
  mkdir -p "$REPORT_DIR"
  "$PY" - "$ROOT" "$REPORT_DIR" "$E2E_EXIT" "$STARTED_AT" "${EREV_E2E_COMMAND:-scripts/e2e.sh}" <<'PY'
import json
import sys
from pathlib import Path

root, report_dir, exit_code, started_at, command = sys.argv[1:6]
sys.path.insert(0, str(Path(root) / "scripts"))
import gate_report  # noqa: E402

directory = Path(report_dir)
entries = []
lines = directory / "projects.jsonl"
if lines.is_file():
    entries = [json.loads(line) for line in lines.read_text(encoding="utf-8").splitlines() if line]
projects, failures = [], []
counts = {"passed": 0, "failed": 0, "flaky": 0, "skipped": 0, "projects": {}}
for entry in entries:
    for key in ("exit_code", "workers"):
        if key in entry:
            entry[key] = int(entry[key])
    if entry.get("spec") == "":
        del entry["spec"]
    if "stage" in entry:
        failures.append(entry)
        continue
    projects.append(entry)
    if "skipped" in entry:
        continue
    source = directory / entry["report"]
    stats = json.loads(source.read_text(encoding="utf-8")).get("stats", {}) if source.is_file() else {}
    summary = {
        "passed": int(stats.get("expected", 0)),
        "failed": int(stats.get("unexpected", 0)),
        "flaky": int(stats.get("flaky", 0)),
        "skipped": int(stats.get("skipped", 0)),
    }
    project = counts["projects"].setdefault(entry["project"], dict.fromkeys(summary, 0))
    for key, value in summary.items():
        counts[key] += value
        project[key] += value
    if entry["exit_code"] != 0:
        failures.append({"stage": entry["project"], "exit_code": entry["exit_code"]})
report = {
    "target": "e2e",
    "command": command,
    "build_sha": gate_report.build_sha(),
    "worktree_dirty": gate_report.worktree_dirty(),
    "started_at": started_at,
    "finished_at": gate_report.utc_now(),
    "exit_code": int(exit_code),
    "counts": counts,
    "failures": failures,
    "projects": projects,
}
(directory / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
skipped = [entry["project"] for entry in projects if entry.get("skipped") == "no tests yet"]
print(
    f"e2e counts: {counts['passed']} passed, {counts['failed']} failed, {counts['flaky']} flaky, "
    f"{counts['skipped']} skipped; projects without tests: {', '.join(skipped) or 'none'}"
)
PY
}

finish() {
  if [[ "$FINISHED" == "1" ]]; then
    return 0
  fi
  FINISHED=1
  if [[ "$LOCK_TAKEN" == "1" ]]; then
    stack_down
    write_report
  fi
  release_lock
}

main() {
  STARTED_AT="$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import gate_report; print(gate_report.utc_now())' "$ROOT/scripts")"
  require_password || return 1
  validate_projects || return 1
  e2e_ports
  take_lock || return 1
  rm -f "$REPORT_DIR/projects.jsonl" "$REPORT_DIR/list.json" "$REPORT_DIR"/playwright-*.json
  if stack_up; then
    run_projects
  else
    record stage stack exit_code 1
    note_exit 1
  fi
  finish
  return "$E2E_EXIT"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  trap finish EXIT
  trap 'E2E_EXIT=130; exit 130' INT
  trap 'E2E_EXIT=143; exit 143' TERM
  main
  exit $?
fi
