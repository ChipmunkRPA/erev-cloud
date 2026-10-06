#!/usr/bin/env bash
# make zap-baseline (docs/dev-guide.md §4.5 DG-MK-zap-baseline; §4.1 DG-MK-00g, DG-MK-00h; §10.3
# DG-FORBID-07, DG-FORBID-12; 05 SAR-43; BUILD_SPEC DEP-5 zap-baseline part; D-98 148 A2).
#   (1) if `docker info` fails, write {"result": "skipped-no-daemon"}, print
#       "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" and exit 0 (never a pass);
#   (2) bring up compose project erev-verify through steps 2 to 5 of DG-MK-compose-verify — by calling
#       scripts/compose_verify.sh under its keep-up contract (EREV_COMPOSE_VERIFY_KEEP_UP=1), the single
#       source of the bring-up; this script never runs `compose build` or `up` itself (D-98 148 A2 (2));
#   (3) docker run --rm -v "<report dir>:/zap/wrk" ghcr.io/zaproxy/zaproxy:stable zap-baseline.py
#       -t http://host.docker.internal:8195/ -J zap.json -r zap.html (the image pull is the network use);
#   (4) docker compose -p erev-verify down -v, through the exit trap: this script owns the down of the
#       project its own bring-up left up, and of no other (ZAP-DOWN-OWNERSHIP-1, DG-MK-zap-baseline
#       rev 1.235). compose_verify.sh prints that it left the project up for the caller when it ends
#       after its `up` stage was begun - verified, failed or ended by a signal - and never before; the
#       down runs only when the bring-up of THIS run printed it. A bring-up that stopped at the port
#       check found another checkout's project on the ports; taking that down would remove it with
#       its volumes. A signal ends the run through the same trap, once the command in the foreground
#       has ended;
#   (5) record the image digest and the alert counts by risk in .run/reports/zap-baseline/report.json
#       (DG-MK-00g). Exit 1 on any FAIL alert (zap-baseline.py exit 1); WARN-only alerts pass with counts.
# Only project erev-verify is ever touched. GATE-BIND-1 (DG-MK-00i): `make zap-baseline` runs this
# script through scripts/gate_context.sh; the report, zap.json, zap.html and the compose sub-report
# (compose-verify/) are written under <context>/.run/reports/zap-baseline/, which the wrapper copies back.
# Final line "OK zap-baseline" or "FAIL zap-baseline: <reason>" (DG-MK-00a). Diagnostics name stages,
# counts and file names only.
# Test-only overrides (backend/tests/unit/deploy/test_supervisor_scripts.py): EREV_DOCKER_BIN names a
# stand-in docker; EREV_ZAP_BASELINE_ROOT a scratch root (honoured only under EREV_ENV=test without the
# wrapper; refused under the wrapper when it is not the context); EREV_COMPOSE_VERIFY_BIN names the
# compose_verify.sh to call (default: the sibling script); the compose_verify overrides pass through;
# EREV_RUN_DIR as in proc.sh; EREV_PY the interpreter used for the report.
set -uo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXEC_ROOT="${EREV_GATE_CONTEXT:-$PWD}"
TARGET="zap-baseline"
PROJECT="erev-verify"
COMMAND="${EREV_ZAP_BASELINE_COMMAND:-make zap-baseline}"
ROOT_OVERRIDE="${EREV_ZAP_BASELINE_ROOT:-}"
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
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  REPORT_DIR="$EXEC_ROOT/.run/reports/$TARGET"
else
  REPORT_DIR="$RUN_DIR/reports/$TARGET"
fi
DOCKER="${EREV_DOCKER_BIN:-docker}"
COMPOSE_VERIFY="${EREV_COMPOSE_VERIFY_BIN:-$SCRIPT_ROOT/scripts/compose_verify.sh}"
if [[ -n "${EREV_PY:-}" ]]; then PY="$EREV_PY"
elif [[ -x "$SCRIPT_ROOT/backend/.venv/bin/python" ]]; then PY="$SCRIPT_ROOT/backend/.venv/bin/python"
else PY="python3"; fi
COMPOSE_FILE="deploy/compose.yaml"
ENV_FILE="deploy/compose.env.example"
ZAP_IMAGE="ghcr.io/zaproxy/zaproxy:stable"
ZAP_TARGET_URL="http://host.docker.internal:8195/"
STAGES_PASSED=""
STAGES_SKIPPED=""
FAIL_STAGE=""
FAIL_EXIT=""
IMAGE_DIGEST=""
ALERT_COUNTS=""
ZAP_RC=""
KEPT_UP_LINE="left up for the caller (keep-up)"
BRING_UP_CALLED=""
DOWN_DONE=""
DOWN_RC=""
DOWN_FAILED=""

utc_now() { "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'; }
build_sha() { git -C "$EXEC_ROOT" rev-parse HEAD 2>/dev/null || echo "nogit"; }
sample_dirty() { if [[ -n "$(git -C "$EXEC_ROOT" status --porcelain 2>/dev/null)" ]]; then echo "true"; else echo "false"; fi; }

write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_TARGET="$TARGET" REPORT_COMMAND="$COMMAND" REPORT_BUILD_SHA="$BUILD_SHA" REPORT_DIRTY="$DIRTY" \
    REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" REPORT_EXIT="$1" REPORT_RESULT="$2" \
    REPORT_STAGES="$STAGES_PASSED" REPORT_STAGES_SKIPPED="$STAGES_SKIPPED" REPORT_FAIL_STAGE="$FAIL_STAGE" \
    REPORT_FAIL_EXIT="$FAIL_EXIT" REPORT_PROJECT="$PROJECT" REPORT_IMAGE="$ZAP_IMAGE" REPORT_IMAGE_DIGEST="$IMAGE_DIGEST" \
    REPORT_ALERTS="$ALERT_COUNTS" REPORT_ZAP_RC="$ZAP_RC" REPORT_TARGET_URL="$ZAP_TARGET_URL" \
    REPORT_EXEC_ROOT="$EXEC_ROOT" REPORT_ROOT="$ROOT" REPORT_ROOT_REJECTED="$ROOT_REJECTED" \
    REPORT_DOWN_RC="$DOWN_RC" REPORT_DOWN_FAILED="$DOWN_FAILED" \
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
# The down this script owns: a failure is a failure of the run with its own exit code, alongside the
# primary failure when there is one (Codex 0105 CLEANUP-1).
if env["REPORT_DOWN_FAILED"]:
    stages["down"] = "fail"
    failures.append({"stage": "down", "exit_code": int(env["REPORT_DOWN_RC"] or 1)})
    cleanup = {"stage": "down", "result": "failed", "exit_code": int(env["REPORT_DOWN_RC"] or 1)}
elif env["REPORT_DOWN_RC"] == "0":
    cleanup = {"stage": "down", "result": "done", "exit_code": 0}
else:
    cleanup = None
for name in ("daemon", "bring-up", "zap", "down", "counts"):
    stages.setdefault(name, "not-run")
alerts = {}
for token in env["REPORT_ALERTS"].split():
    name, _, value = token.partition("=")
    alerts[name] = int(value or 0)
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
        "alerts_by_risk": alerts,
        "alerts_total": sum(alerts.values()),
        "fail_alerts": alerts.get("fail", 0),
        "stages": stages,
    },
    "failures": failures,
    "cleanup": cleanup,
    "project": env["REPORT_PROJECT"],
    "image": env["REPORT_IMAGE"],
    "image_digest": env["REPORT_IMAGE_DIGEST"] or None,
    "target_url": env["REPORT_TARGET_URL"],
    "zap_exit_code": int(env["REPORT_ZAP_RC"]) if env["REPORT_ZAP_RC"] else None,
    "compose_verify_report": "compose-verify/report.json",
    "execution_root": env["REPORT_EXEC_ROOT"],
    "root": env["REPORT_ROOT"],
    "root_override_rejected": bool(env["REPORT_ROOT_REJECTED"]),
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

owns_project() {
  # ZAP-DOWN-OWNERSHIP-1 (DG-MK-zap-baseline rev 1.235): whether the bring-up of THIS run left a
  # project up for this script. compose_verify.sh prints the keep-up line when it ends after its
  # `up` stage was begun - verified, failed, or ended by a signal (its exit trap; it writes no report
  # then) - and never before: a held port or a failed build started nothing. The log is this run's
  # own: what an earlier run left is removed before the bring-up is called.
  [[ -n "$BRING_UP_CALLED" ]] && grep -q "$KEPT_UP_LINE" "$REPORT_DIR/compose-verify.log" 2>/dev/null
}

bring_down() {
  # (4) this script owns the down of the project compose_verify.sh left up under the keep-up contract -
  #     and of no other (owns_project). A bring-up that stopped before its `up` stage started nothing,
  #     and a project of this name on the daemon is then another checkout's, which a `down -v` would
  #     remove with its volumes. A failed down is recorded (DOWN_FAILED, DOWN_RC) and decides the
  #     verdict and the exit code (Codex 0105 CLEANUP-1).
  if [[ -z "$DOWN_DONE" ]] && owns_project; then
    DOWN_DONE="1"
    "$DOCKER" compose -f "$ROOT/$COMPOSE_FILE" --env-file "$ROOT/$ENV_FILE" -p "$PROJECT" down -v >"$REPORT_DIR/compose-down.log" 2>&1
    DOWN_RC=$?
    if [[ "$DOWN_RC" -eq 0 ]]; then
      STAGES_PASSED="$STAGES_PASSED down"
    else
      DOWN_FAILED="1"
      echo "$TARGET: compose down -v failed (exit $DOWN_RC; see $(basename "$REPORT_DIR")/compose-down.log); project $PROJECT may still be up"
    fi
  fi
}

fail() {
  # fail <stage> <exit code> <result> <reason>; a failed cleanup joins the verdict as <result>+cleanup-failed
  FAIL_STAGE="$1"; FAIL_EXIT="$2"
  local result="$3" reason="$4"
  bring_down
  if [[ -n "$DOWN_FAILED" ]]; then
    result="$result+cleanup-failed"
    reason="$reason; and compose down -v failed (exit $DOWN_RC)"
  fi
  write_report 1 "$result"
  echo "FAIL $TARGET: $reason"
  exit 1
}
trap bring_down EXIT
# A signal ends the run through the exit trap as well - and only once the command in the foreground
# has ended, which is when bash runs a trap that is set for a signal. A bring-up that the same signal
# ended has by then printed whether it left a project up; one that the signal did not reach runs to
# its end first.
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

BUILD_SHA="$(build_sha)"
DIRTY="$(sample_dirty)"
STARTED_AT="$(utc_now)"
mkdir -p "$REPORT_DIR"

if [[ -n "$ROOT_REJECTED" ]]; then
  STAGES_SKIPPED="daemon bring-up zap down counts"
  fail "source" 1 "foreign-root" "EREV_ZAP_BASELINE_ROOT does not resolve to the execution context (or is a test-only override outside EREV_ENV=test)"
fi

# (1) daemon
if ! "$DOCKER" info >/dev/null 2>&1; then
  STAGES_SKIPPED="daemon bring-up zap down counts"
  write_report 0 "skipped-no-daemon"
  echo "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable"
  echo "OK $TARGET (skipped-no-daemon)"
  exit 0
fi
STAGES_PASSED="daemon"

# (2) bring-up through compose_verify.sh's keep-up contract (steps 2 to 6 of DG-MK-compose-verify).
[[ -x "$COMPOSE_VERIFY" ]] || fail "bring-up" 1 "compose-verify-missing" "scripts/compose_verify.sh is not in this tree (DEP-5)"
# The run's CFG-26 master keys are generated here, before the bring-up, unless the caller's
# environment carries them: compose_verify.sh inherits them (its step 2b) and this script's own
# `down` then interpolates the same values as the bring-up did. deploy/compose.env.example ships
# none (05 CFG-26; SAR-40 startup subset). They are written to no file and no report.
for KEY_NAME in EREV_COMPOSE_ENCRYPTION_KEY EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY; do
  if [[ -z "${!KEY_NAME:-}" ]]; then
    KEY_VALUE="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')" \
      || fail "bring-up" 1 "keys-failed" "a master key for the run could not be generated"
    printf -v "$KEY_NAME" '%s' "$KEY_VALUE"
  fi
  export "${KEY_NAME?}"
done
unset KEY_VALUE KEY_NAME
# The run's three database passwords, generated here for the same reason (05 DPL-10 rev 1.53: the
# role-init script refuses the example file's placeholders; DG-MK-compose-verify step 2b).
for PASSWORD_NAME in EREV_COMPOSE_POSTGRES_PASSWORD EREV_COMPOSE_OWNER_PASSWORD EREV_COMPOSE_APP_PASSWORD; do
  if [[ -z "${!PASSWORD_NAME:-}" ]]; then
    PASSWORD_VALUE="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')" \
      || fail "bring-up" 1 "keys-failed" "a database password for the run could not be generated"
    printf -v "$PASSWORD_NAME" '%s' "$PASSWORD_VALUE"
  fi
  export "${PASSWORD_NAME?}"
done
unset PASSWORD_VALUE PASSWORD_NAME
# What the bring-up of an earlier run said - its log and its report - is not this run's.
rm -f "$REPORT_DIR/compose-verify.log" "$REPORT_DIR/compose-verify/report.json" \
  || fail "bring-up" 1 "stale-bring-up" "the log and the report an earlier bring-up left in $(basename "$REPORT_DIR") could not be removed"
# ZAP-DOWN-OWNERSHIP-1: from here on the exit trap takes the project down - if this bring-up says
# that it left one up (owns_project).
BRING_UP_CALLED="1"
EREV_COMPOSE_VERIFY_KEEP_UP=1 EREV_COMPOSE_VERIFY_REPORT_DIR="$REPORT_DIR/compose-verify" \
  EREV_COMPOSE_VERIFY_ROOT="${EREV_ZAP_BASELINE_ROOT:-}" EREV_COMPOSE_VERIFY_COMMAND="$COMMAND (bring-up)" \
  "$COMPOSE_VERIFY" >"$REPORT_DIR/compose-verify.log" 2>&1
rc=$?
if [[ $rc -ne 0 ]]; then
  # The sub-run's verdict travels in this FAIL line so a failure is attributable from the line alone
  # (DEPLOY-PORT-FLAKE-1: the CPU tests' scratch roots are removed after each test).
  SUB_RESULT="$("$PY" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("result") or "")' "$REPORT_DIR/compose-verify/report.json" 2>/dev/null || true)"
  if owns_project; then OWNED="it left the project up, and this run takes it down"
  else OWNED="it started nothing, so nothing is taken down: a project $PROJECT on the daemon is not this run's"; fi
  fail "bring-up" "$rc" "bring-up-failed" "compose_verify.sh failed to bring project $PROJECT up (compose-verify result: ${SUB_RESULT:-unknown}; $OWNED; see $(basename "$REPORT_DIR")/compose-verify.log and compose-verify/report.json)"
fi
grep -q "$KEPT_UP_LINE" "$REPORT_DIR/compose-verify.log" \
  || fail "bring-up" 1 "bring-up-not-kept-up" "compose_verify.sh did not honour the keep-up contract"
STAGES_PASSED="$STAGES_PASSED bring-up"

# (3) the baseline scan against the loopback web port through the container's host alias.
"$DOCKER" run --rm -v "$REPORT_DIR:/zap/wrk" "$ZAP_IMAGE" zap-baseline.py -t "$ZAP_TARGET_URL" -J zap.json -r zap.html >"$REPORT_DIR/zap.log" 2>&1
ZAP_RC=$?
case "$ZAP_RC" in
  0|1|2) STAGES_PASSED="$STAGES_PASSED zap" ;;
  *) fail "zap" "$ZAP_RC" "zap-error" "zap-baseline.py exited $ZAP_RC (see $(basename "$REPORT_DIR")/zap.log)" ;;
esac

# (4) down
bring_down

# (5) the image digest and the alert counts by risk (zap.json: site[].alerts[].riskcode).
IMAGE_DIGEST="$("$DOCKER" image inspect --format '{{index .RepoDigests 0}}' "$ZAP_IMAGE" 2>/dev/null | head -n 1 || true)"
ALERT_COUNTS="$("$PY" - "$REPORT_DIR/zap.json" "$ZAP_RC" <<'PY'
import json, sys
names = {"0": "informational", "1": "low", "2": "medium", "3": "high"}
counts = {name: 0 for name in names.values()}
try:
    document = json.load(open(sys.argv[1], encoding="utf-8"))
    for site in document.get("site") or []:
        for alert in site.get("alerts") or []:
            counts[names.get(str(alert.get("riskcode")), "informational")] += 1
except Exception:
    print("")
    sys.exit(0)
counts["fail"] = 1 if sys.argv[2] == "1" else 0
print(" ".join(f"{k}={v}" for k, v in counts.items()))
PY
)"
[[ -n "$ALERT_COUNTS" ]] || fail "counts" 1 "no-zap-json" "zap.json is missing or unreadable (see $(basename "$REPORT_DIR")/zap.log)"
STAGES_PASSED="$STAGES_PASSED counts"
if [[ "$ZAP_RC" == "1" ]]; then
  FAIL_STAGE=""
  if [[ -n "$DOWN_FAILED" ]]; then
    write_report 1 "fail-alerts+cleanup-failed"
    echo "FAIL $TARGET: zap-baseline.py reported FAIL alerts ($ALERT_COUNTS); and compose down -v failed (exit $DOWN_RC); see $(basename "$REPORT_DIR")/zap.html"
    exit 1
  fi
  write_report 1 "fail-alerts"
  echo "FAIL $TARGET: zap-baseline.py reported FAIL alerts ($ALERT_COUNTS); see $(basename "$REPORT_DIR")/zap.html"
  exit 1
fi
if [[ -n "$DOWN_FAILED" ]]; then
  write_report 1 "cleanup-failed"
  echo "FAIL $TARGET: scan clean but compose down -v failed (exit $DOWN_RC); project $PROJECT may still be up (see $(basename "$REPORT_DIR")/compose-down.log)"
  exit 1
fi
write_report 0 "clean"
echo "$TARGET: $ZAP_IMAGE ${IMAGE_DIGEST:-(digest unavailable)}; alerts $ALERT_COUNTS; zap exit $ZAP_RC"
echo "OK $TARGET"
