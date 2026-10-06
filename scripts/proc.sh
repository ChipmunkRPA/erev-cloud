#!/usr/bin/env bash
# Process control by PID file (docs/dev-guide.md §3.2, DG-RUN-10 to DG-RUN-12).
#   scripts/proc.sh start <name> <port or -> -- <command...>
#   scripts/proc.sh stop <name>
#   scripts/proc.sh status
# There is no other stop mechanism: no pkill, killall or pattern matching (DG-FORBID-02).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# EREV_RUN_DIR (.env.example; relative paths from the repository root) names the PID directory.
RUN_DIR="${EREV_RUN_DIR:-.run}"
[[ "$RUN_DIR" == /* ]] || RUN_DIR="$ROOT/$RUN_DIR"
PY="$ROOT/backend/.venv/bin/python"
WAIT="$ROOT/scripts/wait_for_http.py"

usage() {
  echo "usage: scripts/proc.sh start <name> <port|-> -- <command...> | stop <name> | status" >&2
  exit 2
}

valid_name() { [[ "$1" =~ ^[a-z0-9][a-z0-9-]*$ ]]; }

pid_alive() { [[ "$1" =~ ^[0-9]+$ ]] && kill -0 "$1" 2>/dev/null; }

# Readiness per docs/dev-guide.md §3.1 "Ready when": "http <url>", "heartbeat <file>" or "alive".
# readiness <name> [port]: the URL uses the port the process was started on; the EREV_*_PORT
# defaults apply only when the port is "-" (ruling D-78).
readiness() {
  local port="${2:--}"
  if [[ "$port" == "-" ]]; then port="$(port_of "$1")"; fi
  case "$1" in
    api | api-e2e | api-perf) echo "http http://127.0.0.1:$port/api/v1/readyz" ;;
    web | web-e2e) echo "http http://127.0.0.1:$port/" ;;
    worker | worker-e2e | perf-worker-*) echo "heartbeat $RUN_DIR/$1.heartbeat" ;;
    *) echo "alive -" ;;
  esac
}

# env_port <variable> <default>: the exported value, else the digits-only line of the .env file
# named by EREV_DOTENV (default .env; relative paths from the repository root), else the default
# (ruling D-80). Nothing else from the file is read or printed.
env_port() {
  local value="${!1:-}" file="${EREV_DOTENV:-.env}"
  [[ "$file" == /* ]] || file="$ROOT/$file"
  if [[ -z "$value" && -f "$file" ]]; then
    value="$(sed -n "s/^$1=\([0-9][0-9]*\)[[:space:]]*\$/\1/p" "$file" | tail -n 1)"
  fi
  echo "${value:-$2}"
}

port_of() {
  case "$1" in
    api) env_port EREV_API_PORT 8190 ;;
    api-e2e | api-perf) env_port EREV_E2E_API_PORT 8199 ;;
    web) env_port EREV_WEB_PORT 5270 ;;
    web-e2e) env_port EREV_E2E_WEB_PORT 5279 ;;
    *) echo "-" ;;
  esac
}

# check_ready <name> <pid> <timeout seconds> [port]
check_ready() {
  local kind target
  read -r kind target <<<"$(readiness "$1" "${4:--}")"
  case "$kind" in
    http) "$PY" "$WAIT" "$target" --timeout "$3" --pid "$2" ;;
    heartbeat) "$PY" "$WAIT" --heartbeat-file "$target" --max-age 60 --timeout "$3" --pid "$2" ;;
    *)
      if [[ "$3" != "0" ]]; then sleep 0.5; fi
      pid_alive "$2"
      ;;
  esac
}

recorded_pid() {
  local file
  for file in "$RUN_DIR"/*.pid; do
    [[ -f "$file" && "$(cat "$file")" == "$1" ]] && return 0
  done
  return 1
}

cmd_start() {
  [[ $# -ge 4 && "$3" == "--" ]] || usage
  local name="$1" port="$2"
  shift 3
  valid_name "$name" || usage
  local pidfile="$RUN_DIR/$name.pid" logfile="$RUN_DIR/$name.log" old holder pid
  mkdir -p "$RUN_DIR"
  if [[ -f "$pidfile" ]]; then
    old="$(cat "$pidfile")"
    if pid_alive "$old"; then
      echo "$name already running (pid $old)"
      exit 0
    fi
  fi
  if [[ "$port" != "-" ]]; then
    for holder in $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null); do
      if ! recorded_pid "$holder"; then
        echo "port $port in use by another process; not stopping it"
        exit 1
      fi
    done
  fi
  cd "$ROOT" || exit 1
  nohup "$@" >>"$logfile" 2>&1 </dev/null &
  pid=$!
  echo "$pid" >"$pidfile"
  if check_ready "$name" "$pid" 60 "$port"; then
    echo "$name started (pid $pid)"
    exit 0
  fi
  echo "$name not ready within 60 s; last 40 lines of .run/$name.log:"
  tail -n 40 "$logfile"
  exit 1
}

cmd_stop() {
  [[ $# -eq 1 ]] || usage
  valid_name "$1" || usage
  local name="$1" pidfile="$RUN_DIR/$1.pid" pid i
  if [[ ! -f "$pidfile" ]]; then
    echo "$name not running"
    exit 0
  fi
  pid="$(cat "$pidfile")"
  if pid_alive "$pid"; then
    kill -TERM "$pid" 2>/dev/null
    for ((i = 0; i < 30; i++)); do
      pid_alive "$pid" || break
      sleep 0.5
    done
    if pid_alive "$pid"; then
      kill -KILL "$pid" 2>/dev/null
    fi
    echo "$name stopped (pid $pid)"
  else
    echo "$name not running (stale pid file removed)"
  fi
  rm -f "$pidfile"
  exit 0
}

cmd_status() {
  local file name pid state ready found=0
  for file in "$RUN_DIR"/*.pid; do
    [[ -f "$file" ]] || continue
    found=1
    name="$(basename "$file" .pid)"
    pid="$(cat "$file")"
    if pid_alive "$pid"; then
      state="alive"
      if check_ready "$name" "$pid" 0; then ready="ready"; else ready="not-ready"; fi
    else
      state="stale"
      ready="-"
    fi
    echo "$name pid=$pid $state port=$(port_of "$name") ready=$ready"
  done
  if [[ "$found" == "0" ]]; then
    echo "no processes recorded in .run/"
  fi
  exit 0
}

# Dispatch only when executed; sourcing the script defines the functions and does nothing else.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  [[ $# -ge 1 ]] || usage
  command="$1"
  shift
  case "$command" in
    start) cmd_start "$@" ;;
    stop) cmd_stop "$@" ;;
    status) cmd_status "$@" ;;
    *) usage ;;
  esac
fi
