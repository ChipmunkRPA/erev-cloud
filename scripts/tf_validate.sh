#!/usr/bin/env bash
# make tf-validate (docs/dev-guide.md §4.5 DG-MK-tf-validate; §4.1 DG-MK-00g, DG-MK-00h; §10.3
# DG-FORBID-07; 05 §8.3 DPL-42; 00-GOAL G11; BUILD_SPEC DEP-5 tf-validate part).
#   (1) if `terraform` is absent, write {"result": "skipped-not-installed"}, print
#       "SUPERVISOR VERIFICATION NEEDED: Terraform not installed" and exit 0 (never a pass);
#   (2) TF_PLUGIN_CACHE_DIR=<root>/.run/terraform-plugin-cache terraform -chdir=deploy/terraform/gcp
#       init -backend=false -input=false (the only network use: the provider download); on failure
#       exit 1 with "provider download failed; supervisor verification needed";
#   (3) terraform -chdir=deploy/terraform/gcp fmt -check -recursive;
#   (4) terraform -chdir=deploy/terraform/gcp validate;
#   (5) write .run/reports/tf-validate/report.json (DG-MK-00g) with the Terraform version and the
#       provider versions pinned by .terraform.lock.hcl, so the supervisor record names the exact
#       provider the configuration was validated against.
# Provenance (independent review of 3e50ac3, "static provenance limitation"): the Git identity
# (HEAD, dirty state) and the SHA-256 of the validated inputs (every *.tf, *.example and
# .terraform.lock.hcl under deploy/terraform/gcp) are sampled BEFORE init and AGAIN after validate;
# when either sample differs the run is reported as "source-changed" and exits 1. The report carries
# both samples (build_sha / build_sha_end, worktree_dirty / worktree_dirty_end, source_sha256_start /
# source_sha256_end, lock_sha256) and start_end_bound = true only when they agree. This is
# START/END-BOUND evidence, not proof of immutable execution: equal samples cannot exclude a change
# and revert between them (A -> B -> A). Immutable execution is pending GATE-BIND-1 (lane P1).
# No state is read or written, no cloud credential is used and no state-changing or credentialed
# Terraform subcommand is ever run (DG-FORBID-07; 00-GOAL §4). The final line is "OK tf-validate" or
# "FAIL tf-validate: <reason>" (DG-MK-00a).
# Gate evidence shape (DG-MK-00g; GATE-BIND-1 wrapper, P1 candidate 8 Q-13): the report always
# carries the nine keys target, command, build_sha, worktree_dirty, started_at, finished_at,
# exit_code, counts, failures with their types, target "tf-validate", build_sha = HEAD of the
# EXECUTION CONTEXT (EREV_GATE_CONTEXT under the wrapper, else the current directory), and a
# POPULATED counts on every path: counts.stages names init, fmt and validate as pass/fail/skipped
# (all "skipped" on the skipped-not-installed path) next to the tf_files and providers figures, so
# the release manifest can classify the run instead of reading an empty record as NOT_RUN. Under
# the wrapper the report is written to <context>/.run/reports/tf-validate/report.json, where the
# wrapper reads it, whatever EREV_RUN_DIR says.
# Module root (P3c-IF1): the tree validated is always the execution context's deploy/terraform/gcp.
# Under EREV_GATE_CONTEXT an EREV_TF_VALIDATE_ROOT that does not resolve to the context is rejected
# before any terraform call (FAIL, failures[] {stage: source}, result foreign-module-root), so a
# report bound to captured commit A can never describe module B. Without the wrapper the override is
# honoured only in isolated tests (EREV_ENV=test); anywhere else it is rejected the same way.
# Test-only overrides (backend/tests/unit/deploy/test_supervisor_scripts.py): EREV_TERRAFORM_BIN
# names the terraform binary, EREV_TF_VALIDATE_ROOT a scratch repository root, EREV_RUN_DIR as in
# proc.sh, EREV_PY the interpreter used to write the report.
set -uo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The execution context: the wrapper's immutable context when EREV_GATE_CONTEXT is set, else the
# current directory (make runs from the repository root). Identity (build_sha, worktree_dirty) is
# sampled here and, under the wrapper, the report is written here.
EXEC_ROOT="${EREV_GATE_CONTEXT:-$PWD}"
# Module root (P3c-IF1). ROOT is the tree whose deploy/terraform/gcp is validated and hashed. Under
# the wrapper it IS the context; an override that resolves elsewhere is recorded and rejected below,
# before any terraform call. Without the wrapper the override serves isolated tests only.
MODULE_ROOT_OVERRIDE="${EREV_TF_VALIDATE_ROOT:-}"
MODULE_ROOT_REJECTED=""
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  CONTEXT_REAL="$(cd "$EREV_GATE_CONTEXT" 2>/dev/null && pwd -P)"
  if [[ -n "$MODULE_ROOT_OVERRIDE" ]]; then
    OVERRIDE_REAL="$(cd "$MODULE_ROOT_OVERRIDE" 2>/dev/null && pwd -P || true)"
    if [[ -z "$OVERRIDE_REAL" || "$OVERRIDE_REAL" != "$CONTEXT_REAL" ]]; then
      MODULE_ROOT_REJECTED="$MODULE_ROOT_OVERRIDE"
    fi
  fi
  ROOT="$CONTEXT_REAL"
elif [[ -n "$MODULE_ROOT_OVERRIDE" && "${EREV_ENV:-}" == "test" ]]; then
  ROOT="$MODULE_ROOT_OVERRIDE"
elif [[ -n "$MODULE_ROOT_OVERRIDE" ]]; then
  MODULE_ROOT_REJECTED="$MODULE_ROOT_OVERRIDE"
  ROOT="$SCRIPT_ROOT"
else
  ROOT="$SCRIPT_ROOT"
fi
RUN_DIR="${EREV_RUN_DIR:-.run}"
[[ "$RUN_DIR" == /* ]] || RUN_DIR="$ROOT/$RUN_DIR"
TERRAFORM="${EREV_TERRAFORM_BIN:-terraform}"
COMMAND="${EREV_TF_VALIDATE_COMMAND:-make tf-validate}"
TARGET="tf-validate"
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  REPORT_DIR="$EXEC_ROOT/.run/reports/$TARGET"
else
  REPORT_DIR="$RUN_DIR/reports/$TARGET"
fi
TF_DIR="deploy/terraform/gcp"
LOCK_FILE="$ROOT/$TF_DIR/.terraform.lock.hcl"
export TF_PLUGIN_CACHE_DIR="${TF_PLUGIN_CACHE_DIR:-$RUN_DIR/terraform-plugin-cache}"
export TF_IN_AUTOMATION=1
export TF_INPUT=0

if [[ -n "${EREV_PY:-}" ]]; then
  PY="$EREV_PY"
elif [[ -x "$SCRIPT_ROOT/backend/.venv/bin/python" ]]; then
  PY="$SCRIPT_ROOT/backend/.venv/bin/python"
else
  PY="python3"
fi

TERRAFORM_VERSION=""
FAIL_STAGE=""
FAIL_EXIT=""
STAGES_PASSED=""
STAGES_SKIPPED=""
BUILD_SHA_START=""
DIRTY_START=""
SOURCE_SHA_START=""
LOCK_SHA_START=""
BUILD_SHA_END=""
DIRTY_END=""
SOURCE_SHA_END=""
LOCK_SHA_END=""

utc_now() {
  "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'
}

build_sha() {
  git -C "$EXEC_ROOT" rev-parse HEAD 2>/dev/null || echo "nogit"
}

sample_dirty() {
  if [[ -n "$(git -C "$EXEC_ROOT" status --porcelain 2>/dev/null)" ]]; then echo "true"; else echo "false"; fi
}

tf_file_count() {
  find "$ROOT/$TF_DIR" -name '*.tf' -not -path '*/.terraform/*' 2>/dev/null | wc -l | tr -d ' '
}

# Content hash of the validated inputs: sorted relative paths and bytes of every *.tf, *.example and
# the lock file under the module directory (never the .terraform provider cache).
source_sha256() {
  "$PY" - "$ROOT/$TF_DIR" <<'PYSRC'
import hashlib
import os
import sys

root = sys.argv[1]
digest = hashlib.sha256()
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = sorted(name for name in dirnames if name != ".terraform")
    for name in sorted(filenames):
        if not (name.endswith(".tf") or name.endswith(".example") or name == ".terraform.lock.hcl"):
            continue
        path = os.path.join(dirpath, name)
        digest.update(os.path.relpath(path, root).encode() + b"\0")
        with open(path, "rb") as handle:
            digest.update(hashlib.sha256(handle.read()).digest() + b"\0")
print(digest.hexdigest())
PYSRC
}

lock_sha256() {
  if [[ -f "$LOCK_FILE" ]]; then
    "$PY" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$LOCK_FILE"
  else
    echo ""
  fi
}

sample_start() {
  BUILD_SHA_START="$(build_sha)"
  DIRTY_START="$(sample_dirty)"
  SOURCE_SHA_START="$(source_sha256)"
  LOCK_SHA_START="$(lock_sha256)"
}

sample_end() {
  BUILD_SHA_END="$(build_sha)"
  DIRTY_END="$(sample_dirty)"
  SOURCE_SHA_END="$(source_sha256)"
  LOCK_SHA_END="$(lock_sha256)"
}

# write_report <exit code> <result>: the DG-MK-00g report. Every value passes through the
# environment; the lock file is parsed by the interpreter, never by string interpolation.
write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_TARGET="$TARGET" REPORT_COMMAND="$COMMAND" REPORT_BUILD_SHA="$BUILD_SHA_START" \
    REPORT_DIRTY="$DIRTY_START" REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" \
    REPORT_EXIT="$1" REPORT_RESULT="$2" REPORT_TF_VERSION="$TERRAFORM_VERSION" \
    REPORT_LOCK_FILE="$LOCK_FILE" REPORT_TF_FILES="$(tf_file_count)" REPORT_TF_DIR="$TF_DIR" \
    REPORT_PLUGIN_CACHE="$TF_PLUGIN_CACHE_DIR" REPORT_STAGES="$STAGES_PASSED" \
    REPORT_STAGES_SKIPPED="$STAGES_SKIPPED" REPORT_EXEC_ROOT="$EXEC_ROOT" REPORT_MODULE_ROOT="$ROOT" \
    REPORT_MODULE_ROOT_OVERRIDE="$MODULE_ROOT_OVERRIDE" REPORT_MODULE_ROOT_REJECTED="$MODULE_ROOT_REJECTED" \
    REPORT_FAIL_STAGE="$FAIL_STAGE" REPORT_FAIL_EXIT="$FAIL_EXIT" \
    REPORT_BUILD_SHA_END="$BUILD_SHA_END" REPORT_DIRTY_END="$DIRTY_END" \
    REPORT_SOURCE_SHA_START="$SOURCE_SHA_START" REPORT_SOURCE_SHA_END="$SOURCE_SHA_END" \
    REPORT_LOCK_SHA_START="$LOCK_SHA_START" REPORT_LOCK_SHA_END="$LOCK_SHA_END" \
    "$PY" - "$REPORT_DIR/report.json" <<'PY'
import json
import os
import re
import sys

env = os.environ

providers = {}
lock = env["REPORT_LOCK_FILE"]
if os.path.isfile(lock):
    text = open(lock, encoding="utf-8").read()
    for name, body in re.findall(r'provider "([^"]+)" \{(.*?)\n\}', text, flags=re.S):
        version = re.search(r'version\s*=\s*"([^"]+)"', body)
        constraints = re.search(r'constraints\s*=\s*"([^"]+)"', body)
        providers[name] = {
            "version": version.group(1) if version else None,
            "constraints": constraints.group(1) if constraints else None,
        }

failures = []
if env["REPORT_FAIL_STAGE"]:
    failures.append({"stage": env["REPORT_FAIL_STAGE"], "exit_code": int(env["REPORT_FAIL_EXIT"] or 1)})

stages = {name: "pass" for name in env["REPORT_STAGES"].split()}
for name in env["REPORT_STAGES_SKIPPED"].split():
    stages.setdefault(name, "skipped")
if env["REPORT_FAIL_STAGE"]:
    stages[env["REPORT_FAIL_STAGE"]] = "fail"
# Every DG-MK-tf-validate stage is named on every path: a stage after a failure is "not-run".
for name in ("init", "fmt", "validate"):
    stages.setdefault(name, "not-run")

def optional(value):
    return value or None


def optional_bool(value):
    return None if value == "" else value == "true"


end_sha = optional(env["REPORT_BUILD_SHA_END"])
start_end_bound = (
    end_sha is not None
    and end_sha == env["REPORT_BUILD_SHA"]
    and env["REPORT_DIRTY_END"] == env["REPORT_DIRTY"]
    and env["REPORT_SOURCE_SHA_END"] == env["REPORT_SOURCE_SHA_START"]
    and env["REPORT_LOCK_SHA_END"] == env["REPORT_LOCK_SHA_START"]
)

report = {
    "target": env["REPORT_TARGET"],
    "command": env["REPORT_COMMAND"],
    "build_sha": env["REPORT_BUILD_SHA"],
    "worktree_dirty": env["REPORT_DIRTY"] == "true",
    # Provenance: identity and input hashes sampled before init and after validate.
    "build_sha_end": end_sha,
    "worktree_dirty_end": optional_bool(env["REPORT_DIRTY_END"]),
    "source_sha256_start": optional(env["REPORT_SOURCE_SHA_START"]),
    "source_sha256_end": optional(env["REPORT_SOURCE_SHA_END"]),
    "lock_sha256": optional(env["REPORT_LOCK_SHA_END"] or env["REPORT_LOCK_SHA_START"]),
    # Start/end-bound only (A -> B -> A between samples is not excluded); immutable execution is
    # pending GATE-BIND-1 (lane P1).
    "start_end_bound": start_end_bound,
    "started_at": env["REPORT_STARTED"],
    "finished_at": env["REPORT_FINISHED"],
    "exit_code": int(env["REPORT_EXIT"]),
    "result": env["REPORT_RESULT"],
    "counts": {
        "tf_files": int(env["REPORT_TF_FILES"] or 0),
        "providers": len(providers),
        "stages": stages,
    },
    "failures": failures,
    "terraform_version": env["REPORT_TF_VERSION"] or None,
    "providers": providers,
    "directory": env["REPORT_TF_DIR"],
    "plugin_cache_dir": env["REPORT_PLUGIN_CACHE"],
    # Where the run executed (identity root) and which module tree it validated. Under the wrapper
    # module_root is the context; a rejected foreign override is named, never validated (P3c-IF1).
    "execution_root": env["REPORT_EXEC_ROOT"],
    "module_root": env["REPORT_MODULE_ROOT"],
    "module_root_override": env["REPORT_MODULE_ROOT_OVERRIDE"] or None,
    "module_root_rejected": bool(env["REPORT_MODULE_ROOT_REJECTED"]),
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

fail() {
  # fail <stage> <exit code> <result> <reason>
  FAIL_STAGE="$1"
  FAIL_EXIT="$2"
  sample_end
  write_report 1 "$3"
  echo "FAIL $TARGET: $4"
  exit 1
}

STARTED_AT="$(utc_now)"
sample_start

# (0) P3c-IF1: a module root outside the execution context is refused before any terraform call,
# so the report (bound to the context) never describes a foreign module.
if [[ -n "$MODULE_ROOT_REJECTED" ]]; then
  STAGES_SKIPPED="init fmt validate"
  if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
    fail "source" 1 "foreign-module-root" "EREV_TF_VALIDATE_ROOT=$MODULE_ROOT_REJECTED does not resolve to the execution context $EXEC_ROOT; the module validated must be the captured context's $TF_DIR"
  else
    fail "source" 1 "foreign-module-root" "EREV_TF_VALIDATE_ROOT=$MODULE_ROOT_REJECTED is a test-only override (EREV_ENV=test); it is refused in any other execution"
  fi
fi

# (1) Terraform present? Without it every stage is recorded as skipped (populated counts), never
# as an empty record.
if ! command -v "$TERRAFORM" >/dev/null 2>&1; then
  STAGES_SKIPPED="init fmt validate"
  sample_end
  write_report 0 "skipped-not-installed"
  echo "SUPERVISOR VERIFICATION NEEDED: Terraform not installed"
  echo "OK $TARGET (skipped-not-installed)"
  exit 0
fi

if [[ ! -d "$ROOT/$TF_DIR" ]]; then
  fail "layout" 1 "missing-directory" "$TF_DIR does not exist"
fi

TERRAFORM_VERSION="$("$TERRAFORM" version -json 2>/dev/null | "$PY" -c 'import json, sys
try:
    print(json.load(sys.stdin).get("terraform_version", ""))
except Exception:
    print("")' 2>/dev/null || true)"
if [[ -z "$TERRAFORM_VERSION" ]]; then
  TERRAFORM_VERSION="$("$TERRAFORM" version 2>/dev/null | head -n 1 | sed -n 's/^Terraform v\{0,1\}\([0-9][0-9.]*\).*/\1/p')"
fi

mkdir -p "$TF_PLUGIN_CACHE_DIR"

# (2) provider download and module initialisation without any backend or state.
"$TERRAFORM" -chdir="$ROOT/$TF_DIR" init -backend=false -input=false -no-color
rc=$?
if [[ $rc -ne 0 ]]; then
  fail "init" "$rc" "provider-download-failed" "provider download failed; supervisor verification needed"
fi
STAGES_PASSED="init"

# (3) formatting.
"$TERRAFORM" -chdir="$ROOT/$TF_DIR" fmt -check -recursive -no-color
rc=$?
if [[ $rc -ne 0 ]]; then
  fail "fmt" "$rc" "fmt-failed" "terraform fmt -check found unformatted files; run terraform fmt -recursive in $TF_DIR"
fi
STAGES_PASSED="$STAGES_PASSED fmt"

# (4) schema validation against the locked provider.
"$TERRAFORM" -chdir="$ROOT/$TF_DIR" validate -no-color
rc=$?
if [[ $rc -ne 0 ]]; then
  fail "validate" "$rc" "validate-failed" "terraform validate failed; see the lines above"
fi
STAGES_PASSED="$STAGES_PASSED validate"

# (5) provenance: the inputs and the Git identity must be what they were before init.
sample_end
if [[ "$BUILD_SHA_END" != "$BUILD_SHA_START" || "$DIRTY_END" != "$DIRTY_START" \
      || "$SOURCE_SHA_END" != "$SOURCE_SHA_START" || "$LOCK_SHA_END" != "$LOCK_SHA_START" ]]; then
  FAIL_STAGE="provenance"
  FAIL_EXIT=1
  write_report 1 "source-changed"
  echo "FAIL $TARGET: source changed during validation (HEAD, worktree state, module files or lock file differ between start and end); rerun on a quiet tree"
  exit 1
fi

write_report 0 "validated"
echo "terraform ${TERRAFORM_VERSION:-unknown}; providers pinned by $TF_DIR/.terraform.lock.hcl; inputs sha256 $SOURCE_SHA_END"
echo "OK $TARGET"
