#!/usr/bin/env bash
# make perf (docs/dev-guide.md §4.4 DG-MK-perf; §9.9 DG-PERF-01 to DG-PERF-08; DG-MK-00e, DG-MK-00g;
# BUILD_SPEC PRF-3 to PRF-6; G9).
#   (1) take the e2e-ports lock (api-perf binds 8199, DG-RUN-09); (2) run the perf harness:
#       EREV_ENV=dev EREV_PERF_RUN=1 pytest backend/tests/perf -m perf --basetemp=$RUN_DIR/pytest-perf
#       (the harness verifies perf-volume, restores its stored snapshot into a perf-run-* sandbox,
#       starts and stops api-perf and perf-worker-1..4 by PID file, measures and reports); (3) leave
#       .run/reports/perf/report.json — the harness writes it; when it wrote none this script records
#       the exit code and command so a report always exists. The exit code is pytest's.
#   Every perf run targets the dev database `erev` (05 PERF-11): Ray-side (DG-MK-perf), never a lane.
# Sourcing the script defines the functions and runs nothing (backend/tests/unit/perf/test_harness_rules.py).
set -uo pipefail

# shellcheck source=scripts/proc.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/proc.sh"

PY="$ROOT/backend/.venv/bin/python"
LOCK_DIR="$RUN_DIR/locks/e2e-ports"
REPORT_DIR="${EREV_REPORTS_DIR:-$RUN_DIR/reports}/perf"
REPORT="$REPORT_DIR/report.json"
PERF_COMMAND="${EREV_PERF_COMMAND:-make perf}"
LOCK_TAKEN=0
PERF_EXIT=0
STARTED_AT=""

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# (1) DG-MK-00e: a directory lock holding the owner's PID; a lock whose PID is dead is taken over.
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

# (2) DG-MK-perf step 2; DG-PERF-06: EREV_PERF_RUN=1 makes backend/tests/conftest.py set EREV_ENV=dev.
run_harness() {
  mkdir -p "$REPORT_DIR"
  (
    cd "$ROOT" && EREV_ENV=dev EREV_PERF_RUN=1 EREV_RUN_DIR="$RUN_DIR" EREV_REPORTS_DIR="${EREV_REPORTS_DIR:-$RUN_DIR/reports}" \
      "$PY" -m pytest backend/tests/perf -m perf --basetemp="$RUN_DIR/pytest-perf" -p no:cacheprovider
  )
}

# (3) DG-MK-00g: a report always exists; the harness's own report is left untouched.
ensure_report() {
  mkdir -p "$REPORT_DIR"
  if [[ ! -f "$REPORT" ]]; then
    printf '{"command": "%s", "started_at": "%s", "finished_at": "%s", "exit_code": %s, "result": "no harness report"}\n' \
      "$PERF_COMMAND" "$STARTED_AT" "$(now_utc)" "$PERF_EXIT" >"$REPORT"
  fi
}

finish() {
  ensure_report
  release_lock
}

main() {
  STARTED_AT="$(now_utc)"
  take_lock || {
    PERF_EXIT=1
    return 1
  }
  run_harness
  PERF_EXIT=$?
  return "$PERF_EXIT"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  trap finish EXIT
  trap 'PERF_EXIT=130; exit 130' INT
  trap 'PERF_EXIT=143; exit 143' TERM
  main
  exit $?
fi
