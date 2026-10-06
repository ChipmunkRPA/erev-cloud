#!/usr/bin/env bash
# make audit-deps (docs/dev-guide.md §4.5 DG-MK-audit-deps; §4.1 DG-MK-00g, DG-MK-00h; §10.3
# DG-FORBID-07, DG-FORBID-12; 05 SAR-17, THR-24; BUILD_SPEC DEP-5 audit-deps part; D-98 148 A2).
#   (1) uv export --project backend --no-dev --frozen --no-emit-project --all-extras
#       --output-file .run/tmp/audit-requirements.txt (the runtime Python set the images install,
#       `uv sync --no-dev --extra gcp`, pinned with hashes; the project itself is not a published
#       distribution and is not emitted; never under the system temp dir, DG-FORBID-04);
#   (1a) every requirement of that file must be `name==version` with hashes (an editable, path, URL
#       or unpinned line is `export-invalid`); the environment markers are removed into
#       .run/reports/audit-deps/audited-requirements.txt, so the audited set is every distribution
#       the lock pins for the runtime set on any platform, never the subset the auditing host would
#       install (on macOS arm64 pip-audit drops `greenlet`, which the Linux images carry);
#   (2) uv tool run pip-audit --strict --require-hashes --disable-pip -r <the audited file>
#       --format json (pip-audit's mode for a fully pinned, hashed file: no virtual environment and
#       no resolution, so nothing depends on the host interpreter; the only network use besides npm
#       is the advisory database); the result must name exactly the pinned set (a requirement that
#       pip-audit did not audit is an incomplete result, `pip-audit-invalid`);
#   (3) npm --prefix frontend audit --omit=dev --json;
#   (4) counts by severity and output_sha256 = SHA-256 of the two captured outputs concatenated in
#       that order, in .run/reports/audit-deps/report.json (DG-MK-00g). Exit 1 when pip-audit reports
#       any vulnerability or npm reports a high or critical advisory; the captured JSON stays next to
#       the report (pip-audit.json, npm-audit.json) for the supervisor's verification.
#   Without uv or npm every stage is recorded as skipped ("skipped-not-installed", populated
#   counts), the SUPERVISOR VERIFICATION NEEDED line is printed and the exit is 0 (never a pass).
# GATE-BIND-1 (DG-MK-00i): `make audit-deps` runs this script through scripts/gate_context.sh; the
# report is written to <context>/.run/reports/audit-deps/report.json (EXEC_ROOT), where the wrapper
# reads it and stamps source_binding. The final line is "OK audit-deps" or "FAIL audit-deps: <reason>"
# (DG-MK-00a). Diagnostics name stages, counts and file names only (common-terms redaction rule).
# Test-only overrides (backend/tests/unit/deploy/test_supervisor_scripts.py): EREV_UV_BIN and
# EREV_NPM_BIN name stand-in binaries, EREV_AUDIT_DEPS_ROOT a scratch root (honoured only under
# EREV_ENV=test without the wrapper; refused under the wrapper when it is not the context), EREV_RUN_DIR
# as in proc.sh, EREV_PY the interpreter used to write the report.
set -uo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXEC_ROOT="${EREV_GATE_CONTEXT:-$PWD}"
TARGET="audit-deps"
COMMAND="${EREV_AUDIT_DEPS_COMMAND:-make audit-deps}"
ROOT_OVERRIDE="${EREV_AUDIT_DEPS_ROOT:-}"
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
UV="${EREV_UV_BIN:-uv}"
NPM="${EREV_NPM_BIN:-npm}"
if [[ -n "${EREV_PY:-}" ]]; then PY="$EREV_PY"
elif [[ -x "$SCRIPT_ROOT/backend/.venv/bin/python" ]]; then PY="$SCRIPT_ROOT/backend/.venv/bin/python"
else PY="python3"; fi
REQUIREMENTS="$RUN_DIR/tmp/audit-requirements.txt"
AUDITED="$REPORT_DIR/audited-requirements.txt"
PIP_AUDIT_OUT="$REPORT_DIR/pip-audit.json"
NPM_AUDIT_OUT="$REPORT_DIR/npm-audit.json"
STAGES_PASSED=""
STAGES_SKIPPED=""
FAIL_STAGE=""
FAIL_EXIT=""
PYTHON_VULNS=""
PYTHON_DEPS=""
PINNED=""
MARKERS_REMOVED=""
PIP_EXIT=""
NPM_COUNTS=""
NPM_TOTAL=""
NPM_EXIT=""
OUTPUT_SHA256=""

utc_now() { "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'; }
build_sha() { git -C "$EXEC_ROOT" rev-parse HEAD 2>/dev/null || echo "nogit"; }
sample_dirty() { if [[ -n "$(git -C "$EXEC_ROOT" status --porcelain 2>/dev/null)" ]]; then echo "true"; else echo "false"; fi; }

# write_report <exit code> <result>: the DG-MK-00g report; every value passes through the environment.
write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_TARGET="$TARGET" REPORT_COMMAND="$COMMAND" REPORT_BUILD_SHA="$BUILD_SHA" REPORT_DIRTY="$DIRTY" \
    REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" REPORT_EXIT="$1" REPORT_RESULT="$2" \
    REPORT_STAGES="$STAGES_PASSED" REPORT_STAGES_SKIPPED="$STAGES_SKIPPED" REPORT_FAIL_STAGE="$FAIL_STAGE" \
    REPORT_FAIL_EXIT="$FAIL_EXIT" REPORT_PYTHON_VULNS="$PYTHON_VULNS" REPORT_NPM_COUNTS="$NPM_COUNTS" \
    REPORT_OUTPUT_SHA256="$OUTPUT_SHA256" REPORT_EXEC_ROOT="$EXEC_ROOT" REPORT_ROOT="$ROOT" \
    REPORT_ROOT_REJECTED="$ROOT_REJECTED" REPORT_PIP_AUDIT_OUT="$PIP_AUDIT_OUT" REPORT_NPM_AUDIT_OUT="$NPM_AUDIT_OUT" \
    REPORT_PIP_EXIT="$PIP_EXIT" REPORT_PYTHON_DEPS="$PYTHON_DEPS" REPORT_NPM_EXIT="$NPM_EXIT" REPORT_NPM_TOTAL="$NPM_TOTAL" \
    REPORT_PINNED="$PINNED" REPORT_MARKERS_REMOVED="$MARKERS_REMOVED" REPORT_AUDITED="$AUDITED" \
    "$PY" - "$REPORT_DIR/report.json" <<'PY'
import hashlib
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
for name in ("export", "pip-audit", "npm-audit", "digest"):
    stages.setdefault(name, "not-run")
# The audited set (step 1a): how many requirements the export pins, how many carried an environment
# marker, and the identity of the marker-free file pip-audit read (kept next to this report).
requirements = None
if env["REPORT_PINNED"] != "" and os.path.isfile(env["REPORT_AUDITED"]):
    with open(env["REPORT_AUDITED"], "rb") as handle:
        audited_sha256 = hashlib.sha256(handle.read()).hexdigest()
    requirements = {
        "file": os.path.basename(env["REPORT_AUDITED"]),
        "pinned": int(env["REPORT_PINNED"]),
        "markers_removed": int(env["REPORT_MARKERS_REMOVED"] or 0),
        "sha256": audited_sha256,
    }
npm = {}
for token in env["REPORT_NPM_COUNTS"].split():
    name, _, value = token.partition("=")
    npm[name] = int(value or 0)
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
        "python_vulnerabilities": int(env["REPORT_PYTHON_VULNS"] or 0),
        "npm_advisories": npm,
        "npm_high_or_critical": npm.get("high", 0) + npm.get("critical", 0),
        "stages": stages,
    },
    "failures": failures,
    "scanners": {
        "pip_audit": {
            "exit_code": int(env["REPORT_PIP_EXIT"]) if env["REPORT_PIP_EXIT"] != "" else None,
            "dependencies_audited": int(env["REPORT_PYTHON_DEPS"]) if env["REPORT_PYTHON_DEPS"] != "" else None,
            "accepted": env["REPORT_PYTHON_VULNS"] != "",
        },
        "npm_audit": {
            "exit_code": int(env["REPORT_NPM_EXIT"]) if env["REPORT_NPM_EXIT"] != "" else None,
            "total": int(env["REPORT_NPM_TOTAL"]) if env["REPORT_NPM_TOTAL"] != "" else None,
            "accepted": env["REPORT_NPM_COUNTS"] != "",
        },
    },
    "output_sha256": env["REPORT_OUTPUT_SHA256"] or None,
    "requirements": requirements,
    "captured": {
        "pip_audit": env["REPORT_PIP_AUDIT_OUT"] if env["REPORT_PYTHON_VULNS"] != "" else None,
        "npm_audit": env["REPORT_NPM_AUDIT_OUT"] if env["REPORT_NPM_COUNTS"] != "" else None,
    },
    "execution_root": env["REPORT_EXEC_ROOT"],
    "root": env["REPORT_ROOT"],
    "root_override_rejected": bool(env["REPORT_ROOT_REJECTED"]),
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

fail() {
  # fail <stage> <exit code> <result> <reason>
  FAIL_STAGE="$1"; FAIL_EXIT="$2"
  write_report 1 "$3"
  echo "FAIL $TARGET: $4"
  exit 1
}

BUILD_SHA="$(build_sha)"
DIRTY="$(sample_dirty)"
STARTED_AT="$(utc_now)"

# (0) a root outside the execution context is refused before any tool call (P3c-IF1 pattern).
if [[ -n "$ROOT_REJECTED" ]]; then
  STAGES_SKIPPED="export pip-audit npm-audit digest"
  fail "source" 1 "foreign-root" "EREV_AUDIT_DEPS_ROOT does not resolve to the execution context (or is a test-only override outside EREV_ENV=test)"
fi

# (1) tools present? Without uv or npm every stage is skipped (populated counts), never a pass.
if ! command -v "$UV" >/dev/null 2>&1 || ! command -v "$NPM" >/dev/null 2>&1; then
  STAGES_SKIPPED="export pip-audit npm-audit digest"
  write_report 0 "skipped-not-installed"
  echo "SUPERVISOR VERIFICATION NEEDED: uv or npm not installed"
  echo "OK $TARGET (skipped-not-installed)"
  exit 0
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR/tmp"

# (2) the runtime Python set the images install, pinned with hashes: the project's dependencies and
#     every extra (the Dockerfiles sync `--extra gcp`), without the dev group and without the project
#     itself, which is no published distribution and carries no hash.
rm -f "$AUDITED"
"$UV" export --project "$ROOT/backend" --no-dev --frozen --no-emit-project --all-extras --output-file "$REQUIREMENTS" >"$REPORT_DIR/uv-export.log" 2>&1
rc=$?
[[ $rc -eq 0 && -s "$REQUIREMENTS" ]] || fail "export" "$rc" "export-failed" "uv export failed (see $(basename "$REPORT_DIR")/uv-export.log)"

# (2a) the audited file: every requirement must be `name==version` (its hashes follow on continuation
#      lines, which pip-audit --require-hashes checks); environment markers are removed, because
#      pip-audit evaluates them on the auditing host and silently drops what that host would not
#      install. The audited set is therefore the lock's whole runtime set, on every host.
PINNED_VERDICT="$("$PY" - "$REQUIREMENTS" "$AUDITED" <<'PY'
"""uv export (requirements.txt): comment lines, option lines (`--index-url …`), and requirements
`name==version[ ; marker]` continued by a trailing backslash onto indented `--hash=sha256:…` lines.
Anything else at the start of a logical line (`-e .`, a path, a URL, an unpinned name) cannot be
audited by name and version and is refused by its line number, never skipped."""
import re
import sys

source, target = sys.argv[1], sys.argv[2]
pinned = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)\s*(;[^\\]*)?(\\)?\s*$")
refused_options = ("-e", "--editable", "-r", "--requirement", "-c", "--constraint")
out, count, markers, continued = [], 0, 0, False
with open(source, encoding="utf-8") as handle:
    for number, raw in enumerate(handle, start=1):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if continued or not stripped or stripped.startswith("#"):
            out.append(line)
            continued = continued and stripped.endswith("\\")
            continue
        match = pinned.match(line)
        if match is None:
            if stripped.startswith("-") and stripped.split()[0].split("=")[0] not in refused_options:
                out.append(line)  # an index or format option of the export
                continue
            print(f"INVALID line {number} is not a pinned requirement (name==version)")
            sys.exit(0)
        count += 1
        if match.group(3):
            markers += 1
        out.append(f"{match.group(1)}=={match.group(2)}" + (" \\" if match.group(4) else ""))
        continued = bool(match.group(4))
if count == 0:
    print("INVALID no pinned requirement in the export")
    sys.exit(0)
with open(target, "w", encoding="utf-8") as handle:
    handle.write("\n".join(out) + "\n")
print(f"OK {count} {markers}")
PY
)"
case "$PINNED_VERDICT" in
  OK*) ;;
  INVALID*) fail "export" 1 "export-invalid" "the exported requirements cannot be audited: ${PINNED_VERDICT#INVALID } (see $(basename "$REQUIREMENTS") under the run directory's tmp)" ;;
  *) fail "export" 1 "export-invalid" "the exported requirements could not be read" ;;
esac
read -r _ PINNED MARKERS_REMOVED <<<"$PINNED_VERDICT"
STAGES_PASSED="export"

# (3) pip-audit over the audited file, without pip (no virtual environment and no resolution: the file
#     is fully pinned and hashed); the JSON is captured whatever the exit code, then judged: only a
#     result in the expected shape, naming exactly the pinned set, whose exit code agrees with it is a
#     verdict (Codex 0105 AUDIT-1).
"$UV" tool run pip-audit --strict --require-hashes --disable-pip -r "$AUDITED" --format json >"$PIP_AUDIT_OUT" 2>"$REPORT_DIR/pip-audit.log"
pip_rc=$?
PIP_EXIT="$pip_rc"
PIP_VERDICT="$("$PY" - "$PIP_AUDIT_OUT" "$pip_rc" "$AUDITED" <<'PY'
"""pip-audit --format json: {"dependencies": [{"name", "version", "vulns": [{"id", ...}]}, ...], "fixes": [...]}.
Exit semantics: 0 = every dependency audited, no vulnerability; 1 = vulnerabilities found (under --strict
also a dependency that could not be audited, which appears with "skip_reason" and is incomplete here).
Anything else (no JSON, an error object, a missing field, a skipped dependency, a pinned requirement
the result does not name or a dependency the requirements do not pin, another exit code, or a
disagreement between the exit code and the result) is a tool failure, never a verdict."""
import json
import re
import sys

path, rc, requirements = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    document = json.load(open(path, encoding="utf-8"))
except Exception:
    print("NOJSON")
    sys.exit(0)


def invalid(reason):
    print(f"INVALID {reason}")
    sys.exit(0)


if not isinstance(document, dict):
    invalid("top-level is not an object")
if "error" in document:
    invalid("error object")
dependencies = document.get("dependencies")
if not isinstance(dependencies, list) or not dependencies:
    invalid("dependencies missing or empty")
if not isinstance(document.get("fixes"), list):
    invalid("fixes missing")
vulns = 0
for dependency in dependencies:
    if not isinstance(dependency, dict) or not isinstance(dependency.get("name"), str) or not dependency["name"]:
        invalid("dependency without a name")
    name = dependency["name"]
    if "skip_reason" in dependency:
        invalid(f"dependency {name} skipped (incomplete audit)")
    if not isinstance(dependency.get("version"), str) or not isinstance(dependency.get("vulns"), list):
        invalid(f"dependency {name} without version or vulns")
    for vulnerability in dependency["vulns"]:
        if not isinstance(vulnerability, dict) or not vulnerability.get("id"):
            invalid(f"vulnerability without an id on {name}")
    vulns += len(dependency["vulns"])


def key(name, version):
    return re.sub(r"[-_.]+", "-", name).lower(), version


# Completeness: the result names exactly the pinned set of the audited file (PEP 503 names).
expected = set()
with open(requirements, encoding="utf-8") as handle:
    for line in handle:
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", line)
        if match:
            expected.add(key(match.group(1), match.group(2)))
audited = {key(dependency["name"], dependency["version"]) for dependency in dependencies}
missing = sorted(f"{name}=={version}" for name, version in expected - audited)
if missing:
    invalid(f"{len(missing)} pinned requirement(s) not audited: {', '.join(missing[:5])}")
extra = sorted(f"{name}=={version}" for name, version in audited - expected)
if extra:
    invalid(f"{len(extra)} audited dependency(ies) not pinned by the requirements: {', '.join(extra[:5])}")
if rc not in (0, 1):
    invalid(f"exit {rc} is not a pip-audit verdict")
if (rc == 0) != (vulns == 0):
    print(f"INCONSISTENT exit {rc} with {vulns} vulnerabilities")
    sys.exit(0)
print(f"OK {vulns} {len(dependencies)}")
PY
)"
case "$PIP_VERDICT" in
  NOJSON) fail "pip-audit" "$pip_rc" "pip-audit-failed" "pip-audit produced no JSON (exit $pip_rc; see $(basename "$REPORT_DIR")/pip-audit.log)" ;;
  INVALID*) fail "pip-audit" "$pip_rc" "pip-audit-invalid" "pip-audit result rejected: ${PIP_VERDICT#INVALID } (exit $pip_rc; see $(basename "$REPORT_DIR")/pip-audit.json)" ;;
  INCONSISTENT*) fail "pip-audit" "$pip_rc" "pip-audit-inconsistent" "pip-audit ${PIP_VERDICT#INCONSISTENT }: exit code and result disagree (see $(basename "$REPORT_DIR")/pip-audit.json)" ;;
  OK*) ;;
  *) fail "pip-audit" "$pip_rc" "pip-audit-failed" "pip-audit result could not be judged" ;;
esac
read -r _ PYTHON_VULNS PYTHON_DEPS <<<"$PIP_VERDICT"
STAGES_PASSED="$STAGES_PASSED pip-audit"

# (4) npm audit of the production dependencies; the JSON is captured whatever the exit code, then judged
#     the same way: expected shape, no error object, exit code agreeing with the total. npm exits 1 on any
#     advisory, so a nonzero exit with low or moderate advisories only is a valid result; the low/moderate
#     policy below is this script's, applied after the result is accepted (Codex 0105 AUDIT-1).
"$NPM" --prefix "$ROOT/frontend" audit --omit=dev --json >"$NPM_AUDIT_OUT" 2>"$REPORT_DIR/npm-audit.log"
npm_rc=$?
NPM_EXIT="$npm_rc"
NPM_VERDICT="$("$PY" - "$NPM_AUDIT_OUT" "$npm_rc" <<'PY'
"""npm audit --json (auditReportVersion 2): {"auditReportVersion": 2, "vulnerabilities": {<package>: ...},
"metadata": {"vulnerabilities": {"info", "low", "moderate", "high", "critical", "total"}, ...}}.
Exit semantics: 0 = no advisory; 1 = advisories at any severity. An {"error": ...} object (ENOLOCK,
registry or network failures), a missing or non-integer count, a total that is not the sum of the
severities or disagrees with the vulnerabilities map, another exit code, or a disagreement between the
exit code and the total is a tool failure, never a verdict."""
import json
import sys

path, rc = sys.argv[1], int(sys.argv[2])
try:
    document = json.load(open(path, encoding="utf-8"))
except Exception:
    print("NOJSON")
    sys.exit(0)


def invalid(reason):
    print(f"INVALID {reason}")
    sys.exit(0)


def count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


if not isinstance(document, dict):
    invalid("top-level is not an object")
if "error" in document:
    invalid("error object")
if document.get("auditReportVersion") != 2:
    invalid("auditReportVersion is not 2")
entries = document.get("vulnerabilities")
if not isinstance(entries, dict):
    invalid("vulnerabilities missing")
counts = (document.get("metadata") or {}).get("vulnerabilities") if isinstance(document.get("metadata"), dict) else None
if not isinstance(counts, dict):
    invalid("metadata.vulnerabilities missing")
names = ("info", "low", "moderate", "high", "critical")
for name in (*names, "total"):
    if not count(counts.get(name)):
        invalid(f"metadata.vulnerabilities.{name} missing or not a count")
total = counts["total"]
if total != sum(counts[name] for name in names):
    invalid("total is not the sum of the severities")
if (total == 0) != (len(entries) == 0):
    invalid("vulnerabilities map and total disagree")
if rc not in (0, 1):
    invalid(f"exit {rc} is not an npm audit verdict")
if (rc == 0) != (total == 0):
    print(f"INCONSISTENT exit {rc} with total {total}")
    sys.exit(0)
print("OK " + " ".join(f"{name}={counts[name]}" for name in names) + f" total={total}")
PY
)"
case "$NPM_VERDICT" in
  NOJSON) fail "npm-audit" "$npm_rc" "npm-audit-failed" "npm audit produced no JSON (exit $npm_rc; see $(basename "$REPORT_DIR")/npm-audit.log)" ;;
  INVALID*) fail "npm-audit" "$npm_rc" "npm-audit-invalid" "npm audit result rejected: ${NPM_VERDICT#INVALID } (exit $npm_rc; see $(basename "$REPORT_DIR")/npm-audit.json)" ;;
  INCONSISTENT*) fail "npm-audit" "$npm_rc" "npm-audit-inconsistent" "npm audit ${NPM_VERDICT#INCONSISTENT }: exit code and result disagree (see $(basename "$REPORT_DIR")/npm-audit.json)" ;;
  OK*) ;;
  *) fail "npm-audit" "$npm_rc" "npm-audit-failed" "npm audit result could not be judged" ;;
esac
NPM_COUNTS="${NPM_VERDICT#OK }"
NPM_TOTAL="${NPM_COUNTS##* total=}"
NPM_COUNTS="${NPM_COUNTS% total=*}"
STAGES_PASSED="$STAGES_PASSED npm-audit"

# (5) the digest of the two captured outputs, in that order.
OUTPUT_SHA256="$("$PY" -c 'import hashlib, sys; h = hashlib.sha256(); [h.update(open(p, "rb").read()) for p in sys.argv[1:]]; print(h.hexdigest())' "$PIP_AUDIT_OUT" "$NPM_AUDIT_OUT")"
STAGES_PASSED="$STAGES_PASSED digest"
NPM_HIGH="$("$PY" -c 'import sys; c = dict(t.split("=") for t in sys.argv[1].split()); print(int(c.get("high", 0)) + int(c.get("critical", 0)))' "$NPM_COUNTS")"
if [[ "$PYTHON_VULNS" != "0" || "$NPM_HIGH" != "0" ]]; then
  FAIL_STAGE=""
  write_report 1 "vulnerabilities-found"
  echo "FAIL $TARGET: $PYTHON_VULNS python vulnerabilities, $NPM_HIGH npm high or critical advisories (npm: $NPM_COUNTS); see $(basename "$REPORT_DIR")/pip-audit.json and npm-audit.json"
  exit 1
fi
write_report 0 "clean"
echo "$TARGET: python vulnerabilities 0 in $PYTHON_DEPS audited of $PINNED pinned ($MARKERS_REMOVED environment markers removed); npm $NPM_COUNTS; output sha256 $OUTPUT_SHA256"
echo "OK $TARGET"
