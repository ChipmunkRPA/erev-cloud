#!/usr/bin/env bash
# make compose-verify (docs/dev-guide.md §4.5 DG-MK-compose-verify; §4.1 DG-MK-00g, DG-MK-00h; §10.3
# DG-FORBID-07, DG-FORBID-12; 00-GOAL G11; D-47; BUILD_SPEC DEP-5 compose-verify part; D-98 148 A2).
#   (1) if `docker info` fails, write {"result": "skipped-no-daemon"}, print
#       "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" and exit 0 (never a pass);
#   (2) fail if 127.0.0.1:8195 or 127.0.0.1:5436 is in use;
#   (2a) write the embedded release manifest of the executed source at the build root
#       (scripts/release_manifest.py --embedded: no image identities, DG-MK-release-manifest), keep its
#       copy next to the report and require it to name the build being verified: the api and worker
#       Dockerfiles copy release-manifest.json from the build context and a production process refuses
#       to start without it (05 REL-03), while the file is git-ignored, so an execution context never
#       holds one (the first run with a Docker daemon failed at that COPY). The generator reads gate
#       reports from the empty directory gate-reports/ under this report: the verification manifest
#       carries no gate evidence (every gate NOT_RUN) and the worktree's own release-manifest report is
#       never replaced. The build root is left as it stood (rev 1.150): before the step writes, the
#       script notes whether a regular file stood there and keeps its bytes next to the report
#       (release-manifest.root-before.json); when the script ends - verified, failed, kept up or
#       interrupted - it removes the manifest it wrote, or puts the earlier file back (restore_manifest).
#       A copy that a killed run left there goes back first, while the root still holds that run's
#       embedded manifest or nothing;
#   (2b) generate the run's three CFG-26 master keys (EREV_COMPOSE_ENCRYPTION_KEY,
#       EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY, EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY), each unless the
#       caller's environment already carries it: deploy/compose.env.example ships none, because a
#       production api or worker refuses to start on a placeholder or on two equal keys (05 CFG-26,
#       SAR-40 startup subset). They live in this process's environment, which docker compose
#       prefers to the env file, and in the containers; they are written to no file and no report.
#       The same step generates the run's three database passwords (EREV_COMPOSE_POSTGRES_PASSWORD,
#       EREV_COMPOSE_OWNER_PASSWORD, EREV_COMPOSE_APP_PASSWORD; secrets.token_urlsafe(24), URL-safe
#       because compose.yaml places two of them in the database URLs) under the same rules: the
#       role-init script refuses the example file's change-me placeholders (05 DPL-10 rev 1.53,
#       ruling R-53 (6));
#   (3) docker compose -f deploy/compose.yaml --env-file deploy/compose.env.example -p erev-verify build;
#   (4) up -d;
#   (5) wait up to 180 s for GET http://127.0.0.1:8195/api/v1/readyz = 200;
#   (6) smoke: GET / returns 200 with a Content-Security-Policy header; the worker container is
#       healthy through its heartbeat HEALTHCHECK (docker compose ps);
#   (7) docker compose -p erev-verify down -v (always, through the exit trap);
#   (8) write pass or fail to .run/reports/compose-verify/report.json (DG-MK-00g).
# Only project erev-verify is ever touched; no other `-p` appears in this script.
# Keep-up contract (D-98 148 A2 (2), the single source of the bring-up for scripts/zap_baseline.sh):
# EREV_COMPOSE_VERIFY_KEEP_UP=1 performs steps (2) to (6), skips (7), prints
# "compose-verify: project erev-verify left up for the caller (keep-up)" and records kept_up=true;
# the caller owns the `down -v`. EREV_COMPOSE_VERIFY_REPORT_DIR lets that caller keep this report
# inside its own report directory (under the GATE-BIND-1 wrapper only the caller's directory is copied back).
# GATE-BIND-1 (DG-MK-00i): `make compose-verify` runs this script through scripts/gate_context.sh; the
# report is written under <context>/.run/reports/compose-verify/ (EXEC_ROOT). Final line "OK compose-verify"
# or "FAIL compose-verify: <reason>" (DG-MK-00a). Diagnostics name stages, ports, URLs of the local
# loopback endpoints and file names only; compose output goes to log files next to the report.
# Test-only overrides (backend/tests/unit/deploy/test_supervisor_scripts.py): EREV_DOCKER_BIN names a
# stand-in docker; EREV_COMPOSE_VERIFY_ROOT a scratch root (honoured only under EREV_ENV=test without
# the wrapper; refused under the wrapper when it is not the context); EREV_COMPOSE_VERIFY_READYZ_URL and
# EREV_COMPOSE_VERIFY_ROOT_URL redirect the two HTTP probes to a scratch server; EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS
# shortens the 180 s wait; EREV_COMPOSE_VERIFY_PORTS (one or two ports 1024-65535, honoured only under EREV_ENV=test,
# refused elsewhere) redirects the port probe to the tests' ephemeral ports so concurrent CPU runs never contend for
# 8195 / 5436 (DEPLOY-PORT-FLAKE-1); EREV_RUN_DIR as in proc.sh; EREV_PY the interpreter used for the probes and the report.
set -uo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXEC_ROOT="${EREV_GATE_CONTEXT:-$PWD}"
TARGET="compose-verify"
PROJECT="erev-verify"
COMMAND="${EREV_COMPOSE_VERIFY_COMMAND:-make compose-verify}"
ROOT_OVERRIDE="${EREV_COMPOSE_VERIFY_ROOT:-}"
ROOT_REJECTED=""
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  CONTEXT_REAL="$(cd "$EREV_GATE_CONTEXT" 2>/dev/null && pwd -P)"
  if [[ -n "$ROOT_OVERRIDE" ]]; then
    OVERRIDE_REAL="$(cd "$ROOT_OVERRIDE" 2>/dev/null && pwd -P || true)"
    [[ -n "$OVERRIDE_REAL" && "$OVERRIDE_REAL" == "$CONTEXT_REAL" ]] || ROOT_REJECTED="$ROOT_OVERRIDE"
  fi
  ROOT="$CONTEXT_REAL"
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
if [[ -n "${EREV_COMPOSE_VERIFY_REPORT_DIR:-}" ]]; then
  REPORT_DIR="$EREV_COMPOSE_VERIFY_REPORT_DIR"
elif [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  REPORT_DIR="$EXEC_ROOT/.run/reports/$TARGET"
else
  REPORT_DIR="$RUN_DIR/reports/$TARGET"
fi
DOCKER="${EREV_DOCKER_BIN:-docker}"
if [[ -n "${EREV_PY:-}" ]]; then PY="$EREV_PY"
elif [[ -x "$SCRIPT_ROOT/backend/.venv/bin/python" ]]; then PY="$SCRIPT_ROOT/backend/.venv/bin/python"
else PY="python3"; fi
COMPOSE_FILE="deploy/compose.yaml"
ENV_FILE="deploy/compose.env.example"
export COMPOSE_PATH="$ROOT/$COMPOSE_FILE" ENV_PATH="$ROOT/$ENV_FILE"
MANIFEST="$ROOT/release-manifest.json"
MANIFEST_COPY="$REPORT_DIR/release-manifest.embedded.json"
MANIFEST_SHA256=""
# What stood at the build root before step (2a) wrote there, and what the script did about it when
# it ended: MANIFEST_STOOD is "absent" or "present" once the step has looked (empty before, and for
# a link or a directory, which the script leaves alone); MANIFEST_ROOT is "removed" or "restored".
MANIFEST_BEFORE="$REPORT_DIR/release-manifest.root-before.json"
MANIFEST_STOOD=""
MANIFEST_ROOT=""
MASTER_KEYS=""
MASTER_KEY_NAMES="EREV_COMPOSE_ENCRYPTION_KEY EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY"
DATABASE_PASSWORDS=""
DATABASE_PASSWORD_NAMES="EREV_COMPOSE_POSTGRES_PASSWORD EREV_COMPOSE_OWNER_PASSWORD EREV_COMPOSE_APP_PASSWORD"
READYZ_URL="${EREV_COMPOSE_VERIFY_READYZ_URL:-http://127.0.0.1:8195/api/v1/readyz}"
ROOT_URL="${EREV_COMPOSE_VERIFY_ROOT_URL:-http://127.0.0.1:8195/}"
TIMEOUT_SECONDS="${EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS:-180}"
KEEP_UP="${EREV_COMPOSE_VERIFY_KEEP_UP:-}"
PORTS_DEFAULT="8195 5436"
PORTS_OVERRIDE="${EREV_COMPOSE_VERIFY_PORTS:-}"
PORTS_REJECTED=""
if [[ -n "$PORTS_OVERRIDE" ]]; then
  if [[ "${EREV_ENV:-}" != "test" ]]; then
    PORTS_REJECTED="test-only override outside EREV_ENV=test"
  elif ! [[ "$PORTS_OVERRIDE" =~ ^[0-9]{1,5}( [0-9]{1,5})?$ ]]; then
    PORTS_REJECTED="not one or two ports"
  else
    for candidate in $PORTS_OVERRIDE; do
      (( candidate >= 1024 && candidate <= 65535 )) || PORTS_REJECTED="port $candidate outside 1024-65535"
    done
  fi
fi
if [[ -n "$PORTS_OVERRIDE" && -z "$PORTS_REJECTED" ]]; then PORTS="$PORTS_OVERRIDE"; PORTS_OVERRIDDEN="true"; else PORTS="$PORTS_DEFAULT"; PORTS_OVERRIDDEN="false"; fi
STAGES_PASSED=""
STAGES_SKIPPED=""
FAIL_STAGE=""
FAIL_EXIT=""
READY_SECONDS=""
CSP_PRESENT=""
WORKER_HEALTH=""
BROUGHT_UP=""
DOWN_DONE=""
DOWN_RC=""
DOWN_FAILED=""

utc_now() { "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'; }
build_sha() { git -C "$EXEC_ROOT" rev-parse HEAD 2>/dev/null || echo "nogit"; }
sample_dirty() { if [[ -n "$(git -C "$EXEC_ROOT" status --porcelain 2>/dev/null)" ]]; then echo "true"; else echo "false"; fi; }
compose() { "$DOCKER" compose -f "$ROOT/$COMPOSE_FILE" --env-file "$ROOT/$ENV_FILE" -p "$PROJECT" "$@"; }

write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_TARGET="$TARGET" REPORT_COMMAND="$COMMAND" REPORT_BUILD_SHA="$BUILD_SHA" REPORT_DIRTY="$DIRTY" \
    REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" REPORT_EXIT="$1" REPORT_RESULT="$2" \
    REPORT_STAGES="$STAGES_PASSED" REPORT_STAGES_SKIPPED="$STAGES_SKIPPED" REPORT_FAIL_STAGE="$FAIL_STAGE" \
    REPORT_FAIL_EXIT="$FAIL_EXIT" REPORT_PROJECT="$PROJECT" REPORT_PORTS="$PORTS" REPORT_READY_SECONDS="$READY_SECONDS" \
    REPORT_CSP="$CSP_PRESENT" REPORT_WORKER="$WORKER_HEALTH" REPORT_KEEP_UP="$KEEP_UP" REPORT_TIMEOUT="$TIMEOUT_SECONDS" \
    REPORT_EXEC_ROOT="$EXEC_ROOT" REPORT_ROOT="$ROOT" REPORT_ROOT_REJECTED="$ROOT_REJECTED" \
    REPORT_READYZ_URL="$READYZ_URL" REPORT_ROOT_URL="$ROOT_URL" REPORT_DOWN_RC="$DOWN_RC" REPORT_DOWN_FAILED="$DOWN_FAILED" \
    REPORT_PORTS_OVERRIDDEN="$PORTS_OVERRIDDEN" REPORT_MANIFEST_SHA256="$MANIFEST_SHA256" \
    REPORT_MANIFEST_COPY="$MANIFEST_COPY" REPORT_MASTER_KEYS="$MASTER_KEYS" \
    REPORT_DATABASE_PASSWORDS="$DATABASE_PASSWORDS" REPORT_MANIFEST_ROOT="$MANIFEST_ROOT" \
    "$PY" - "$REPORT_DIR/report.json" <<'PY'
import json
import os
import sys

env = os.environ
failures = []
if env["REPORT_FAIL_STAGE"]:
    failures.append({"stage": env["REPORT_FAIL_STAGE"], "exit_code": int(env["REPORT_FAIL_EXIT"] or 1)})
stages = {name: "pass" for name in env["REPORT_STAGES"].split()}
for name in env["REPORT_STAGES_SKIPPED"].split():
    stages.setdefault(name, "skipped")
if env["REPORT_FAIL_STAGE"]:
    stages[env["REPORT_FAIL_STAGE"]] = "fail"
# A failed required cleanup is a failure of the run with its own exit code, kept alongside the primary
# failure when there is one (Codex 0105 CLEANUP-1); the keep-up case is distinct (no down was owed).
if env["REPORT_DOWN_FAILED"]:
    stages["down"] = "fail"
    failures.append({"stage": "down", "exit_code": int(env["REPORT_DOWN_RC"] or 1)})
    cleanup = {"stage": "down", "result": "failed", "exit_code": int(env["REPORT_DOWN_RC"] or 1)}
elif env["REPORT_DOWN_RC"] == "0":
    cleanup = {"stage": "down", "result": "done", "exit_code": 0}
elif env["REPORT_KEEP_UP"] == "1" and "down" in env["REPORT_STAGES_SKIPPED"].split():
    cleanup = {"stage": "down", "result": "kept-up", "exit_code": None}
else:
    cleanup = None
for name in ("daemon", "ports", "manifest", "build", "up", "ready", "smoke", "worker", "down"):
    stages.setdefault(name, "not-run")
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
        "ports_checked": len(env["REPORT_PORTS"].split()),
        "ready_seconds": int(env["REPORT_READY_SECONDS"]) if env["REPORT_READY_SECONDS"] else None,
        "stages": stages,
    },
    "failures": failures,
    "cleanup": cleanup,
    "project": env["REPORT_PROJECT"],
    "ports": [f"127.0.0.1:{p}" for p in env["REPORT_PORTS"].split()],
    "ports_overridden": env["REPORT_PORTS_OVERRIDDEN"] == "true",
    "readyz_url": env["REPORT_READYZ_URL"],
    "root_url": env["REPORT_ROOT_URL"],
    "timeout_seconds": int(env["REPORT_TIMEOUT"]),
    "csp_present": None if env["REPORT_CSP"] == "" else env["REPORT_CSP"] == "true",
    "worker_health": env["REPORT_WORKER"] or None,
    "kept_up": env["REPORT_KEEP_UP"] == "1",
    # The embedded manifest the api and worker images of this run carry (step 2a): its SHA-256 and the
    # retained copy; null before that step.
    "manifest_sha256": env["REPORT_MANIFEST_SHA256"] or None,
    # How the run got its CFG-26 master keys: "generated", "inherited" (the caller's environment)
    # or "mixed"; never a value.
    "master_keys": env["REPORT_MASTER_KEYS"] or None,
    "database_passwords": env["REPORT_DATABASE_PASSWORDS"] or None,
    "manifest_copy": os.path.basename(env["REPORT_MANIFEST_COPY"]) if env["REPORT_MANIFEST_SHA256"] else None,
    # What became of the build root's release-manifest.json when the run ended (rev 1.150): "removed"
    # (none stood there before step 2a), "restored" (the file that stood there is back), or null
    # (the step did not run, or the path was a link or a directory).
    "manifest_root": env["REPORT_MANIFEST_ROOT"] or None,
    "execution_root": env["REPORT_EXEC_ROOT"],
    "root": env["REPORT_ROOT"],
    "root_override_rejected": bool(env["REPORT_ROOT_REJECTED"]),
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

restore_manifest() {
  # (2a, end) leave the build root as it stood before step (2a): the images are built by now, the
  # retained copy is the run's evidence, and a development process of this checkout must not meet
  # a verification run's embedded manifest. Called before every report and from the exit trap, so
  # it holds on every path; a second call does nothing.
  case "$MANIFEST_STOOD" in
    absent)
      rm -f "$MANIFEST" && MANIFEST_ROOT="removed" ;;
    present)
      cp "$MANIFEST_BEFORE" "$MANIFEST" && rm -f "$MANIFEST_BEFORE" && MANIFEST_ROOT="restored" \
        || echo "$TARGET: the release manifest that stood at the build root could not be put back; its copy is $(basename "$REPORT_DIR")/$(basename "$MANIFEST_BEFORE") and the next run restores it" ;;
  esac
  MANIFEST_STOOD=""
}

bring_down() {
  # (7) always, unless the caller asked to keep the project up (keep-up contract). A failed down is
  #     recorded (DOWN_FAILED, DOWN_RC) and decides the verdict and the exit code (Codex 0105 CLEANUP-1).
  if [[ -n "$BROUGHT_UP" && -z "$DOWN_DONE" ]]; then
    DOWN_DONE="1"
    if [[ "$KEEP_UP" == "1" ]]; then
      STAGES_SKIPPED="$STAGES_SKIPPED down"
      echo "$TARGET: project $PROJECT left up for the caller (keep-up)"
    else
      compose down -v >"$REPORT_DIR/compose-down.log" 2>&1
      DOWN_RC=$?
      if [[ "$DOWN_RC" -eq 0 ]]; then
        STAGES_PASSED="$STAGES_PASSED down"
      else
        DOWN_FAILED="1"
        echo "$TARGET: compose down -v failed (exit $DOWN_RC; see $(basename "$REPORT_DIR")/compose-down.log); project $PROJECT may still be up"
      fi
    fi
  fi
}

fail() {
  # fail <stage> <exit code> <result> <reason>; a failed cleanup joins the verdict as <result>+cleanup-failed
  FAIL_STAGE="$1"; FAIL_EXIT="$2"
  local result="$3" reason="$4"
  restore_manifest
  bring_down
  if [[ -n "$DOWN_FAILED" ]]; then
    result="$result+cleanup-failed"
    reason="$reason; and compose down -v failed (exit $DOWN_RC)"
  fi
  write_report 1 "$result"
  echo "FAIL $TARGET: $reason"
  exit 1
}
trap 'restore_manifest; bring_down' EXIT

BUILD_SHA="$(build_sha)"
DIRTY="$(sample_dirty)"
STARTED_AT="$(utc_now)"
mkdir -p "$REPORT_DIR"

if [[ -n "$ROOT_REJECTED" ]]; then
  STAGES_SKIPPED="daemon ports manifest build up ready smoke worker down"
  fail "source" 1 "foreign-root" "EREV_COMPOSE_VERIFY_ROOT does not resolve to the execution context (or is a test-only override outside EREV_ENV=test)"
fi
if [[ -n "$PORTS_REJECTED" ]]; then
  STAGES_SKIPPED="daemon ports manifest build up ready smoke worker down"
  fail "source" 1 "foreign-ports" "EREV_COMPOSE_VERIFY_PORTS refused: $PORTS_REJECTED (the probe keeps 127.0.0.1:${PORTS_DEFAULT// / and 127.0.0.1:})"
fi

# (1) daemon
if ! "$DOCKER" info >/dev/null 2>&1; then
  STAGES_SKIPPED="daemon ports manifest build up ready smoke worker down"
  write_report 0 "skipped-no-daemon"
  echo "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable"
  echo "OK $TARGET (skipped-no-daemon)"
  exit 0
fi
STAGES_PASSED="daemon"

# (2) the two published ports must be free.
BUSY="$("$PY" - $PORTS <<'PY'
import socket, sys
busy = []
for port in sys.argv[1:]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", int(port)))
        except OSError:
            busy.append(port)
print(" ".join(busy))
PY
)"
[[ -z "$BUSY" ]] || fail "ports" 1 "port-in-use" "127.0.0.1 port(s) in use: $BUSY; stop what listens there (never the dev stack's own ports) and rerun"
STAGES_PASSED="$STAGES_PASSED ports"

# (2a) the embedded release manifest of the executed source, written where the build context is
#      read (05 REL-03; DG-MK-release-manifest EMBEDDED=1). The retained copy is what the report
#      identifies; a manifest that names another build, or carries image identities, is refused.
# A run that was killed between this step and its end left the checkout's own manifest next to its
# report and its embedded manifest at the build root. The checkout's file goes back first - unless
# the root holds something else by now (the checkout wrote a new manifest since), which stands.
if [[ -f "$MANIFEST_BEFORE" ]]; then
  if [[ ! -e "$MANIFEST" && ! -L "$MANIFEST" ]] \
    || { [[ -f "$MANIFEST" && ! -L "$MANIFEST" && -f "$MANIFEST_COPY" ]] && cmp -s "$MANIFEST" "$MANIFEST_COPY"; }; then
    cp "$MANIFEST_BEFORE" "$MANIFEST" \
      || fail "manifest" 1 "manifest-failed" "the release manifest an interrupted run set aside could not be put back at the build root"
  fi
  rm -f "$MANIFEST_BEFORE"
fi
rm -f "$MANIFEST_COPY"
mkdir -p "$REPORT_DIR/gate-reports"
if [[ -L "$MANIFEST" || ( -e "$MANIFEST" && ! -f "$MANIFEST" ) ]]; then
  MANIFEST_STOOD=""  # a link or a directory is not this script's to set aside; the generator decides
elif [[ -f "$MANIFEST" ]]; then
  cp "$MANIFEST" "$MANIFEST_BEFORE" \
    || fail "manifest" 1 "manifest-failed" "the release manifest at the build root could not be set aside"
  MANIFEST_STOOD="present"
else
  MANIFEST_STOOD="absent"
fi
"$PY" "$SCRIPT_ROOT/scripts/release_manifest.py" --root "$ROOT" --reports-dir "$REPORT_DIR/gate-reports" \
  --embedded --command "$COMMAND (embedded manifest)" >"$REPORT_DIR/release-manifest.log" 2>&1 \
  || fail "manifest" $? "manifest-failed" "the embedded release manifest could not be written (see $(basename "$REPORT_DIR")/release-manifest.log)"
cp "$MANIFEST" "$MANIFEST_COPY" 2>/dev/null \
  || fail "manifest" 1 "manifest-failed" "release-manifest.json is missing at the build root after the manifest step"
MANIFEST_VERDICT="$("$PY" - "$MANIFEST_COPY" "$BUILD_SHA" <<'PY'
import hashlib, json, sys
path, build = sys.argv[1], sys.argv[2]
try:
    raw = open(path, "rb").read()
    document = json.loads(raw)
except Exception:
    print("INVALID release-manifest.json is not valid JSON")
    sys.exit(0)
if not isinstance(document, dict) or document.get("build_sha") != build:
    named = str(document.get("build_sha"))[:12] if isinstance(document, dict) else "nothing"
    print(f"INVALID release-manifest.json names build {named}, not the build being verified ({build[:12]})")
    sys.exit(0)
images = document.get("images")
if isinstance(images, dict) and any(
    isinstance(image, dict) and (image.get("tag") is not None or image.get("digest") is not None)
    for image in images.values()
):
    print("INVALID release-manifest.json carries image identities (not the embedded manifest)")
    sys.exit(0)
print("OK " + hashlib.sha256(raw).hexdigest())
PY
)"
case "$MANIFEST_VERDICT" in
  OK*) MANIFEST_SHA256="${MANIFEST_VERDICT#OK }" ;;
  INVALID*) fail "manifest" 1 "manifest-invalid" "${MANIFEST_VERDICT#INVALID }" ;;
  *) fail "manifest" 1 "manifest-failed" "the embedded release manifest could not be read" ;;
esac
STAGES_PASSED="$STAGES_PASSED manifest"

# (2b) the run's CFG-26 master keys (05 CFG-26; SAR-40 startup subset): generated unless the
#      caller's environment carries them, exported for every compose call of this process.
KEYS_GENERATED=0
KEYS_INHERITED=0
for KEY_NAME in $MASTER_KEY_NAMES; do
  if [[ -n "${!KEY_NAME:-}" ]]; then
    KEYS_INHERITED=$((KEYS_INHERITED + 1))
  else
    KEY_VALUE="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')" \
      || fail "manifest" 1 "keys-failed" "a master key for the run could not be generated"
    printf -v "$KEY_NAME" '%s' "$KEY_VALUE"
    KEYS_GENERATED=$((KEYS_GENERATED + 1))
  fi
  export "${KEY_NAME?}"
done
unset KEY_VALUE KEY_NAME
if [[ "$KEYS_INHERITED" -eq 0 ]]; then MASTER_KEYS="generated"; elif [[ "$KEYS_GENERATED" -eq 0 ]]; then MASTER_KEYS="inherited"; else MASTER_KEYS="mixed"; fi
# The run's three database passwords, by the same rules (05 DPL-10, DPL-16 rev 1.53): the role-init
# script refuses the example file's placeholders, and nothing of them reaches a file or the report.
PASSWORDS_GENERATED=0
PASSWORDS_INHERITED=0
for PASSWORD_NAME in $DATABASE_PASSWORD_NAMES; do
  if [[ -n "${!PASSWORD_NAME:-}" ]]; then
    PASSWORDS_INHERITED=$((PASSWORDS_INHERITED + 1))
  else
    PASSWORD_VALUE="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')" \
      || fail "manifest" 1 "keys-failed" "a database password for the run could not be generated"
    printf -v "$PASSWORD_NAME" '%s' "$PASSWORD_VALUE"
    PASSWORDS_GENERATED=$((PASSWORDS_GENERATED + 1))
  fi
  export "${PASSWORD_NAME?}"
done
unset PASSWORD_VALUE PASSWORD_NAME
if [[ "$PASSWORDS_INHERITED" -eq 0 ]]; then DATABASE_PASSWORDS="generated"; elif [[ "$PASSWORDS_GENERATED" -eq 0 ]]; then DATABASE_PASSWORDS="inherited"; else DATABASE_PASSWORDS="mixed"; fi

# (3) build, (4) up
compose build >"$REPORT_DIR/compose-build.log" 2>&1 || fail "build" $? "build-failed" "docker compose build failed (see $(basename "$REPORT_DIR")/compose-build.log)"
STAGES_PASSED="$STAGES_PASSED build"
BROUGHT_UP="1"
compose up -d >"$REPORT_DIR/compose-up.log" 2>&1 || fail "up" $? "up-failed" "docker compose up failed (see $(basename "$REPORT_DIR")/compose-up.log)"
STAGES_PASSED="$STAGES_PASSED up"

# (5) readiness within the timeout.
READY_SECONDS="$("$PY" - "$READYZ_URL" "$TIMEOUT_SECONDS" <<'PY'
import sys, time, urllib.request, urllib.error
url, timeout = sys.argv[1], int(sys.argv[2])
start = time.monotonic()
while True:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status == 200:
                print(int(time.monotonic() - start)); sys.exit(0)
    except (urllib.error.URLError, OSError, ValueError):
        pass
    if time.monotonic() - start >= timeout:
        print(""); sys.exit(0)
    time.sleep(2)
PY
)"
[[ -n "$READY_SECONDS" ]] || fail "ready" 1 "not-ready" "GET $READYZ_URL did not answer 200 within ${TIMEOUT_SECONDS}s"
STAGES_PASSED="$STAGES_PASSED ready"

# (6) smoke: the SPA root with its CSP header, then the worker's health.
CSP_PRESENT="$("$PY" - "$ROOT_URL" <<'PY'
import sys, urllib.request, urllib.error
try:
    with urllib.request.urlopen(sys.argv[1], timeout=10) as response:
        print("true" if response.status == 200 and response.headers.get("Content-Security-Policy") else "false")
except Exception:
    print("false")
PY
)"
[[ "$CSP_PRESENT" == "true" ]] || fail "smoke" 1 "smoke-failed" "GET $ROOT_URL is not 200 with a Content-Security-Policy header"
STAGES_PASSED="$STAGES_PASSED smoke"
WORKER_HEALTH="$(WORKER_TIMEOUT="$TIMEOUT_SECONDS" "$PY" - <<'PY'
import json, os, subprocess, sys, time
timeout = int(os.environ["WORKER_TIMEOUT"])
docker = os.environ["EREV_DOCKER_BIN"] if os.environ.get("EREV_DOCKER_BIN") else "docker"
start = time.monotonic()
health = "unknown"
while True:
    done = subprocess.run(
        [docker, "compose", "-f", os.environ["COMPOSE_PATH"], "--env-file", os.environ["ENV_PATH"], "-p", "erev-verify", "ps", "--format", "json"],
        capture_output=True, text=True, check=False,
    )
    rows = []
    for line in done.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        rows.extend(parsed if isinstance(parsed, list) else [parsed])
    for row in rows:
        if row.get("Service") == "worker":
            health = str(row.get("Health") or row.get("State") or "unknown").lower()
    if health == "healthy" or time.monotonic() - start >= timeout:
        break
    time.sleep(2)
print(health)
PY
)"
[[ "$WORKER_HEALTH" == "healthy" ]] || fail "worker" 1 "worker-unhealthy" "the worker container is $WORKER_HEALTH, not healthy (heartbeat HEALTHCHECK)"
STAGES_PASSED="$STAGES_PASSED worker"

# (7) down (unless keep-up), (8) report: a failed down after a verified project is cleanup-failed, exit 1.
restore_manifest
bring_down
if [[ -n "$DOWN_FAILED" ]]; then
  write_report 1 "cleanup-failed"
  echo "FAIL $TARGET: project $PROJECT verified but compose down -v failed (exit $DOWN_RC); the project may still be up (see $(basename "$REPORT_DIR")/compose-down.log)"
  exit 1
fi
write_report 0 "verified"
echo "$TARGET: project $PROJECT built and up; readyz in ${READY_SECONDS}s; CSP present; worker healthy; embedded manifest sha256 ${MANIFEST_SHA256:0:12}"
echo "OK $TARGET"
