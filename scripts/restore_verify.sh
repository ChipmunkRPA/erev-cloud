#!/usr/bin/env bash
# make restore-verify (docs/dev-guide.md §4.5 DG-MK-restore-verify; §4.1 DG-MK-00a, DG-MK-00g,
# DG-MK-00h; §2.4 DG-ENV-13; 05 §7.3 OPR-11 steps (3) and (4), OPR-12, OPR-16; runbook RB-04, RB-06;
# BUILD_SPEC DEP-6; production readiness audit DEP-F; independent review P6-R1 to R4, R7).
#   BACKUP names the backup id (erev-<yyyymmdd>T<hhmmss>Z, the only grammar accepted, R3) or
#   "latest". EREV_RESTORE_OWNER_URL and EREV_RESTORE_APP_URL name the ISOLATED target as erev_owner
#   and erev_app: an erev_rv_* database (DG-ENV-13). EREV_RESTORE_ADMIN_URL names the same database
#   as the restore-target admin (a BYPASSRLS non-superuser member of erev_owner, RB-11): pg_restore
#   loads rows into tables under FORCE ROW LEVEL SECURITY, which the application roles cannot (04
#   DB-14), and ownership comes back as dumped. Production data is never restored in place (05
#   OPR-11; REQ-PLT-024). RESET=1 first drops schema erev and the Procrastinate objects of a target
#   used before, as erev_owner; nothing else is ever dropped.
#   Ruling D-95: this is the NATIVE recovery drill (self-hosted, where a provisioner holds BYPASSRLS
#   or is a superuser); under recovery provider MANAGED (Cloud SQL, default with
#   EREV_KEY_PROVIDER=gcp) it refuses: the managed drill is a Cloud SQL clone into the restore-test
#   instance verified by `erev verify --all-tenants` and recorded through recovery_managed.
#   PREFLIGHT then MUTATION (review residual of 2026-09-19): every check below, (1) to (2b), must
#   succeed before the first side effect; the RESET drop, pg_restore, the removal and the
#   extraction happen only in the mutation phase, and the restore directory is anchored to the
#   real run directory with every component lstat-checked (no symbolic link anywhere in it).
#   (1) the manifest (erev-backup-manifest/2) must be a complete inventory bound to BACKUP: exactly
#       the four members dump, files tarball, .env copy and digests, each present with its recorded
#       SHA-256 and size (R2); the archive's members must all lie under the manifest's file_root
#       with plain segments and no links (R3); the digests document must be a populated,
#       well-formed verification document bound to the manifest (R2); a backup whose verification
#       had FAILed is restored and verified, and the run then fails naming that failed evidence;
#   (2) the three target URLs must route to one server, port and erev_rv_* database, and the three
#       connections actually made (owner, app, admin) must answer the same server identity (R1);
#       the target must be empty unless RESET=1;
#   (3) pg_restore --exit-on-error --single-transaction as the admin role (PG* variables built
#       inside Python; never printed);
#   (4) the tarball is extracted with Python's data filter under .run/restore/<backup id>/, a path
#       proven to lie inside .run/restore/ and not to be a link before it is removed and reused;
#   (5) under the master keys read from the backup's .env copy (never printed): `erev migrate` on
#       the clone (forward-fix under the release being validated, OPR-16), then
#       `erev verify --all-tenants --db <target> --expect <id>.digests.json --files` BEFORE
#       `erev doctor --db` (the doctor's own directory read appends a security event, which must not
#       count as recovered evidence, R7), then the doctor;
#   (6) the measurements of erev_api.controls.recovery_preflight.restore_measurements: restore point
#       = the dump's snapshot start, recovery age from it, recovered-evidence lag (the verifier's own
#       events excluded), drill duration and phase seconds, and no cutover RTO (a drill performs
#       none) (R7); .run/reports/restore-verify/report.json (DG-MK-00g) with the OPR-12 record.
# The final line is "OK restore-verify" or "FAIL restore-verify: <reason>" (DG-MK-00a).
# GATE-BIND-1 (DG-MK-00i; rev 1.81, the first run on a clean tree): `make restore-verify` runs this
# script in an execution context that is removed when the run ends. The recipe therefore exports
# the worktree's run directory as EREV_RUN_DIR, so the restore directory .run/restore/<backup id>/
# (the extracted file store a cutover points EREV_FILE_ROOT at, and the migrate, verify, doctor and
# pg_restore logs) outlives the run; the report and verify.json alone are written in the context,
# where the wrapper reads them and copies them back to .run/reports/restore-verify/.
# Test-only overrides (backend/tests/unit/deploy/test_backup_restore_scripts.py): EREV_RESTORE_ROOT,
# EREV_PG_RESTORE_BIN, EREV_RESTORE_EREV_BIN, EREV_RECOVERY_IDENTITY_STUB.
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${EREV_RESTORE_ROOT:-$SCRIPT_ROOT}"
PY="$SCRIPT_ROOT/backend/.venv/bin/python"
EREV="${EREV_RESTORE_EREV_BIN:-$SCRIPT_ROOT/backend/.venv/bin/erev}"
PG_RESTORE="${EREV_PG_RESTORE_BIN:-pg_restore}"
TARGET="restore-verify"
COMMAND="${EREV_RESTORE_COMMAND:-make restore-verify}"
RUN_DIR="${EREV_RUN_DIR:-.run}"
[[ "$RUN_DIR" == /* ]] || RUN_DIR="$ROOT/$RUN_DIR"
# Under the wrapper the report is written in the execution context (the wrapper reads it there and
# copies it back); the run directory itself is the worktree's, exported by the recipe.
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  REPORT_DIR="$EREV_GATE_CONTEXT/.run/reports/$TARGET"
else
  REPORT_DIR="$RUN_DIR/reports/$TARGET"
fi
# Where the report is found after the run, named relative to the worktree (DG-MK-00g).
REPORT_NAME="$(basename "$RUN_DIR")/reports/$TARGET/report.json"
BACKUP_DIR="${EREV_BACKUP_DIR:-.data/backups}"
[[ "$BACKUP_DIR" == /* ]] || BACKUP_DIR="$ROOT/$BACKUP_DIR"
BACKUP="${BACKUP:-latest}"
RESET="${RESET:-}"

export PYTHONPATH="$SCRIPT_ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
STARTED_AT=""
T0=""
BACKUP_ID=""
TARGET_DB=""
FAIL_STAGE=""
BASELINE_RESULT=""
CLONE_SECURITY_VERSION=""
BACKUP_SECURITY_PIN=""
BACKUP_HEAD_KEY=""
PIN_FORWARD_ROTATION=""
RESTORED_REVISION=""
MIGRATED_REVISION=""
RESTORE_SECONDS=""
MIGRATE_SECONDS=""
DOCTOR_SECONDS=""
DOCTOR_EXIT=""
VERIFY_SECONDS=""
VERIFY_EXIT=""
VERIFY_DOC=""
RESTORE_DIR=""

utc_now() {
  "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'
}

epoch() { date +%s; }

# mark <phase:step>: the call sequence, appended to EREV_RECOVERY_CALLS_LOG when set (tests assert
# that every preflight step precedes the first mutation; DG-FORBID-04: the file is the caller's).
mark() { [[ -z "${EREV_RECOVERY_CALLS_LOG:-}" ]] || echo "$1" >>"$EREV_RECOVERY_CALLS_LOG"; }

# file_value <file> <name>: the named line of an env file, without quotes; never printed.
file_value() {
  local value
  [[ -f "$1" ]] || return 0
  value="$(sed -n "s/^$2=//p" "$1" | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

# write_report <exit code> [failure stage]: .run/reports/restore-verify/report.json (DG-MK-00g).
write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_EXIT="$1" REPORT_STAGE="${2:-}" REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" \
    REPORT_COMMAND="$COMMAND" REPORT_ROOT="$ROOT" REPORT_BACKUP_ID="$BACKUP_ID" \
    REPORT_BACKUP_DIR="$BACKUP_DIR" REPORT_TARGET_DB="$TARGET_DB" REPORT_T0="${T0:-0}" \
    REPORT_BASELINE="$BASELINE_RESULT" \
    REPORT_RESTORED_REVISION="$RESTORED_REVISION" REPORT_MIGRATED_REVISION="$MIGRATED_REVISION" \
    REPORT_RESTORE_SECONDS="$RESTORE_SECONDS" REPORT_MIGRATE_SECONDS="$MIGRATE_SECONDS" \
    REPORT_DOCTOR_SECONDS="$DOCTOR_SECONDS" REPORT_DOCTOR_EXIT="$DOCTOR_EXIT" \
    REPORT_VERIFY_SECONDS="$VERIFY_SECONDS" REPORT_VERIFY_EXIT="$VERIFY_EXIT" \
    REPORT_VERIFY_DOC="$VERIFY_DOC" REPORT_CLONE_PIN="$CLONE_SECURITY_VERSION" \
    REPORT_BACKUP_PIN="$BACKUP_SECURITY_PIN" REPORT_HEAD_KEY="$BACKUP_HEAD_KEY" \
    REPORT_PIN_ROTATION="$PIN_FORWARD_ROTATION" \
    "$PY" - "$REPORT_DIR/report.json" <<'PY'
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from erev_api.controls import recovery_preflight as pf

env = os.environ
root = env["REPORT_ROOT"]


def git(*args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def seconds(name: str) -> int | None:
    value = env.get(name) or ""
    return int(value) if value.isdigit() else None


build_sha = git("rev-parse", "HEAD") or "nogit"
porcelain = git("status", "--porcelain")
backup_id = env["REPORT_BACKUP_ID"]
manifest_path = Path(env["REPORT_BACKUP_DIR"]) / f"{backup_id}.manifest.json" if backup_id else None
manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path and manifest_path.is_file() else {}
verify_path = Path(env["REPORT_VERIFY_DOC"]) if env["REPORT_VERIFY_DOC"] else None
verify = json.loads(verify_path.read_text("utf-8")) if verify_path and verify_path.is_file() else {}
exit_code = int(env["REPORT_EXIT"])
t0 = int(env["REPORT_T0"] or 0)
phases = {
    "restore": seconds("REPORT_RESTORE_SECONDS"),
    "migrate": seconds("REPORT_MIGRATE_SECONDS"),
    "doctor": seconds("REPORT_DOCTOR_SECONDS"),
    "verify": seconds("REPORT_VERIFY_SECONDS"),
}
try:
    measurements = pf.restore_measurements(
        manifest=manifest,
        verify_document=verify,
        now=dt.datetime.now(dt.UTC),
        drill_seconds=(int(time.time()) - t0) if t0 else None,
        phase_seconds=phases,
    )
except pf.PreflightError as error:
    # R7 residual: a manifest with missing or corrupt instants yields no measurements (the drill
    # already failed on it); nothing is substituted.
    measurements = {"error": str(error), "restore_point": None, "restore_point_basis": None}
failures = [] if exit_code == 0 else [{"stage": env["REPORT_STAGE"] or "unknown", "exit_code": exit_code}]
failures += [{"stage": "verify", "finding": f} for f in verify.get("failures", [])]
report = {
    "target": "restore-verify",
    "command": env["REPORT_COMMAND"],
    "build_sha": build_sha,
    "worktree_dirty": bool(porcelain) if porcelain is not None else False,
    "started_at": env["REPORT_STARTED"],
    "finished_at": env["REPORT_FINISHED"],
    "exit_code": exit_code,
    "counts": {
        "tenants": verify.get("counts", {}).get("tenants"),
        "files_checked": verify.get("counts", {}).get("files", {}).get("checked"),
        "failures": len(failures),
    },
    "failures": failures,
    "restore_test_record": {
        "backup_id": backup_id or None,
        "restore_duration_seconds": phases["restore"],
        "verification_result": verify.get("result"),
        "baseline_result_at_backup": env["REPORT_BASELINE"] or manifest.get("digests", {}).get("result"),
    },
    "restore": {
        "target_database": env["REPORT_TARGET_DB"] or None,
        "source_database": manifest.get("database"),
        "backup_build_sha": manifest.get("build_sha"),
        "backup_quiesced": manifest.get("quiesced"),
        "restored_schema_revision": env["REPORT_RESTORED_REVISION"] or None,
        "schema_revision_after_migrate": env["REPORT_MIGRATED_REVISION"] or None,
        "doctor_exit": seconds("REPORT_DOCTOR_EXIT"),
        "verify_exit": seconds("REPORT_VERIFY_EXIT"),
        # The verifier's document sits next to this report (its name, not a path: under the
        # wrapper both are copied out of an execution context that is then removed).
        "verify_document": verify_path.name if verify_path else None,
        "expected_anchors": verify.get("expected", {}).get("anchors"),
        "expected_result": verify.get("expected", {}).get("result"),
        "security_hmac": {
            "clone_pin": f"security-hmac:{env['REPORT_CLONE_PIN']}" if env["REPORT_CLONE_PIN"] else None,
            "backup_pin": env["REPORT_BACKUP_PIN"] or None,
            "backup_head_key_id": env["REPORT_HEAD_KEY"] or None,
            "forward_rotation": env["REPORT_PIN_ROTATION"] == "true",
            # The set the backup evidence requires (manifest, bound to the digests document) and
            # what the verifier served on the clone (None when the verifier did not run).
            "required_key_ids": (verify.get("security_chain") or {}).get("required_key_ids")
            or manifest.get("security_required_key_ids"),
            "served": None
            if not verify
            else [
                k.get("key_id")
                for k in (verify.get("key_versions") or {}).get("security_hmac") or []
                if k.get("available") is True
            ],
        },
        "per_tenant_digest_gap_events": {
            t.get("code"): t.get("gap_events") for t in verify.get("tenants", [])
        },
        **measurements,
    },
}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

fail() {
  echo "FAIL $TARGET: $1"
  write_report 1 "${FAIL_STAGE:-$1}" || true
  exit 1
}

STARTED_AT="$(utc_now)"
T0="$(epoch)"

# (1) the backup id, its manifest, the four members, the archive and the digests document.
FAIL_STAGE="manifest"
[[ -d "$BACKUP_DIR" ]] || fail "no backups directory $(basename "$BACKUP_DIR")"
if [[ "$BACKUP" == "latest" ]]; then
  BACKUP_ID="$(ls -1 "$BACKUP_DIR" | sed -n 's/^\(erev-[0-9]\{8\}T[0-9]\{6\}Z\)\.manifest\.json$/\1/p' | sort | tail -n 1)"
  [[ -n "$BACKUP_ID" ]] || fail "no backup manifest found; run make backup first"
else
  BACKUP_ID="$("$PY" -c 'import sys; from erev_api.controls.recovery_preflight import validate_backup_id, PreflightError
try:
    print(validate_backup_id(sys.argv[1]))
except PreflightError as e:
    print(f"restore-verify: {e}", file=sys.stderr); sys.exit(1)' "$BACKUP")" || fail "BACKUP is not a backup id (erev-<yyyymmdd>T<hhmmss>Z or latest)"
fi
MANIFEST="$BACKUP_DIR/$BACKUP_ID.manifest.json"
[[ -f "$MANIFEST" ]] || fail "$(basename "$MANIFEST") not found"
echo "$TARGET: backup $BACKUP_ID"
BASELINE_RESULT="$(MANIFEST_PATH="$MANIFEST" MANIFEST_BACKUP_ID="$BACKUP_ID" "$PY" - <<'PY'
import hashlib
import sys
from pathlib import Path
import os

from erev_api.controls import recovery_preflight as pf

manifest_path = Path(os.environ["MANIFEST_PATH"])
backup_id = os.environ["MANIFEST_BACKUP_ID"]


def refuse(lines: list[str]) -> None:
    for line in lines:
        print(f"restore-verify: {line}", file=sys.stderr)
    sys.exit(1)


try:
    manifest = pf.load_json_strict(manifest_path.read_text("utf-8"))
except ValueError as error:
    refuse([f"manifest is not valid JSON: {error}"])
errors = pf.validate_manifest(manifest, backup_id=backup_id)
if errors:
    refuse(errors)
members = pf.expected_members(backup_id)
bad = []
for kind, name in members.items():
    path = manifest_path.parent / name
    expected = manifest["files"][name]
    if not path.is_file() or path.is_symlink():
        bad.append(f"{name}: missing")
        continue
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected["sha256"] or path.stat().st_size != expected["size_bytes"]:
        bad.append(f"{name}: hash or size differs from the manifest")
if bad:
    refuse(bad)
archive_findings = pf.inspect_archive(manifest_path.parent / members["files"], file_root=manifest["file_root"])
if archive_findings:
    refuse(archive_findings)
try:
    expected_document = pf.load_json_strict((manifest_path.parent / members["digests"]).read_text("utf-8"))
except ValueError as error:
    refuse([f"digests document is not valid JSON: {error}"])
document_errors = pf.validate_expected_document(expected_document)
if document_errors:
    refuse(document_errors)
binding = pf.bind_expected_to_manifest(expected_document, manifest)
if binding:
    refuse(binding)
print(manifest["digests"]["result"])
PY
)" || fail "the backup is incomplete, altered or unbound (see the restore-verify: lines above)"
mark "preflight:manifest"
echo "$TARGET: manifest, four members, archive and digests verified (baseline result at backup: $BASELINE_RESULT)"

# (1b) P2/P6 integration control 3: the clone's signing pin (EREV_SECURITY_HMAC_SECRET_VERSION) is
#      decided here, from the backup's own evidence, before any mutation. It is never inherited
#      from this host's environment or .env: a pin behind the restored chain head would let the
#      verifier's first platform event append a backwards key transition (KEY-03). An operator may
#      move it FORWARD only, explicitly (RESTORE_SECURITY_HMAC_VERSION), and the record says so.
FAIL_STAGE="pin"
PIN_JSON="$(PIN_DIGESTS="$BACKUP_DIR/$BACKUP_ID.digests.json" PIN_OVERRIDE="${RESTORE_SECURITY_HMAC_VERSION:-}" "$PY" - <<'PY'
import json
import os
import sys
from pathlib import Path

from erev_api.controls import recovery_preflight as pf

document = pf.load_json_strict(Path(os.environ["PIN_DIGESTS"]).read_text("utf-8"))
try:
    decision = pf.clone_security_pin(document, override=os.environ.get("PIN_OVERRIDE") or None)
except pf.PreflightError as error:
    print(f"restore-verify: {error}", file=sys.stderr)
    sys.exit(1)
print(json.dumps(decision))
PY
)" || fail "the clone's security-key pin cannot be bound from the backup (see the restore-verify: line above)"
CLONE_SECURITY_VERSION="$("$PY" -c 'import json, sys; print(json.loads(sys.argv[1])["version"])' "$PIN_JSON")"
BACKUP_SECURITY_PIN="$("$PY" -c 'import json, sys; print(json.loads(sys.argv[1])["backup_pin"])' "$PIN_JSON")"
BACKUP_HEAD_KEY="$("$PY" -c 'import json, sys; print(json.loads(sys.argv[1])["head_key_id"])' "$PIN_JSON")"
PIN_FORWARD_ROTATION="$("$PY" -c 'import json, sys; print(str(json.loads(sys.argv[1])["forward_rotation"]).lower())' "$PIN_JSON")"
mark "preflight:pin"
echo "$TARGET: clone security pin security-hmac:$CLONE_SECURITY_VERSION (backup pin $BACKUP_SECURITY_PIN, chain head under $BACKUP_HEAD_KEY, forward rotation $PIN_FORWARD_ROTATION)"
DUMP="$BACKUP_DIR/$BACKUP_ID.dump"
FILES_TAR="$BACKUP_DIR/$BACKUP_ID-files.tar.gz"
ENV_COPY="$BACKUP_DIR/$BACKUP_ID.env"
DIGESTS="$BACKUP_DIR/$BACKUP_ID.digests.json"
FILE_ROOT_NAME="$(MANIFEST_PATH="$MANIFEST" "$PY" -c 'import json, os; print(json.load(open(os.environ["MANIFEST_PATH"]))["file_root"])')"

# (1a) D-95: this is the NATIVE drill; under recovery provider MANAGED the drill is a Cloud SQL
#      clone verified by erev verify, never pg_restore.
FAIL_STAGE="provider"
PROVIDER_DOTENV="$ROOT/.env" "$PY" - <<'PY' || fail "recovery provider refused (see the restore-verify: line above)"
import os
import sys
from pathlib import Path

from check_env import read_env_file
from erev_api.controls import recovery_preflight as pf

try:
    provider = pf.resolve_recovery_provider(os.environ, read_env_file(Path(os.environ["PROVIDER_DOTENV"])))
except pf.PreflightError as error:
    print(f"restore-verify: {error}", file=sys.stderr)
    sys.exit(1)
if provider != pf.NATIVE:
    print(f"restore-verify: {pf.MANAGED_NATIVE_REFUSAL}", file=sys.stderr)
    sys.exit(1)
PY
mark "preflight:provider"

# (2) the isolated target: one endpoint on the URLs, one server identity on the connections.
FAIL_STAGE="target"
[[ -n "${EREV_RESTORE_OWNER_URL:-}" && -n "${EREV_RESTORE_APP_URL:-}" ]] \
  || fail "EREV_RESTORE_OWNER_URL and EREV_RESTORE_APP_URL must name the isolated erev_rv_* target"
[[ -n "${EREV_RESTORE_ADMIN_URL:-}" ]] \
  || fail "EREV_RESTORE_ADMIN_URL must name the target as the restore-target admin (BYPASSRLS; RB-11)"
command -v "$PG_RESTORE" >/dev/null 2>&1 || fail "pg_restore not found (DG-ENV-04)"
TARGET_DB="$("$PY" - <<'PY'
import json
import os
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

from erev_api.controls import recovery_preflight as pf


def refuse(message: str) -> None:
    print(f"restore-verify: {message}", file=sys.stderr)
    sys.exit(1)


urls = {
    name: os.environ[name]
    for name in ("EREV_RESTORE_OWNER_URL", "EREV_RESTORE_APP_URL", "EREV_RESTORE_ADMIN_URL")
}
try:
    endpoint = pf.same_endpoint(urls)
except pf.PreflightError as error:
    refuse(str(error))
if not pf.RESTORE_TARGET_DATABASE.fullmatch(endpoint.database):
    refuse(
        f"restore target must be an erev_rv_* database, not {endpoint.database}; production is "
        "never restored in place (05 OPR-11)"
    )
# The test-only identity stub is honoured under EREV_ENV test or dev only (hard error otherwise).
try:
    stub = pf.identity_stub(os.environ)
except pf.PreflightError as error:
    refuse(str(error))
if stub:
    loaded = json.load(open(stub))
    rows = {name: tuple(loaded[name]) for name in urls}
else:
    import psycopg

    rows = {}
    for name, url in urls.items():
        parts = urlsplit(url)
        try:
            with psycopg.connect(
                host=parts.hostname,
                port=parts.port or 5432,
                user=unquote(parts.username or ""),
                password=unquote(parts.password or ""),
                dbname=unquote(parts.path.lstrip("/")),
                connect_timeout=10,
                **{k: v for k, v in parse_qsl(parts.query) if k == "sslmode"},
            ) as conn:
                rows[name] = tuple(str(v) for v in conn.execute(pf.SERVER_IDENTITY_SQL).fetchone())
        except psycopg.Error as exc:
            refuse(f"cannot reach the target named by {name}: {type(exc).__name__}")
findings = pf.server_identity(rows)
if findings:
    refuse("; ".join(findings))
reached = rows[next(iter(rows))][0] if rows else endpoint.database
if reached != endpoint.database or not pf.RESTORE_TARGET_DATABASE.fullmatch(reached):
    refuse(f"the connections reached database {reached}, not the erev_rv_* target {endpoint.database}")
print(endpoint.database)
PY
)" || fail "target refused (see the restore-verify: line above)"
mark "preflight:identity"
echo "$TARGET: target endpoint $TARGET_DB bound (one server identity on owner, app and admin)"

# (2b) the restore directory: anchored to the real run directory, created here, no symbolic link
#      anywhere in its path (R3 residual). Still preflight: nothing has been changed yet.
FAIL_STAGE="paths"
RESTORE_DIR="$(RESTORE_RUN_DIR="$RUN_DIR" RESTORE_ID="$BACKUP_ID" "$PY" - <<'PY'
import os
import sys
from pathlib import Path

from erev_api.controls.recovery_preflight import PreflightError, contained_path, real_directory

try:
    run_dir = real_directory(Path(os.environ["RESTORE_RUN_DIR"]), label="run directory", allow_link=True)
    root = real_directory(run_dir / "restore", label="restore root")
    print(contained_path(root, root / os.environ["RESTORE_ID"], label="restore directory"))
except PreflightError as error:
    print(f"restore-verify: {error}", file=sys.stderr)
    sys.exit(1)
PY
)" || fail "restore directory refused (see the restore-verify: line above)"
mark "preflight:containment"
mark "preflight:complete"
echo "$TARGET: preflight complete; no side effect so far"

# ---- mutation phase: only now may the target be reset, restored into, or the restore directory
#      removed and written ----------------------------------------------------------------------
FAIL_STAGE="target"
mark "mutate:reset"
RESTORE_RESET="$RESET" "$PY" - <<'PY' || fail "target $TARGET_DB is not empty (set RESET=1 to drop schema erev there) or not reachable as erev_owner"
import os
import re
import sys

from sqlalchemy import text

from erev_api.db import migration_ops
from erev_api.db.session import OWNER_ROLE, build_engine

pattern = re.compile(r"^erev_rv_[a-z0-9_]+$")
url = os.environ["EREV_RESTORE_OWNER_URL"]
for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
    if url.startswith(prefix):
        url = "postgresql+psycopg://" + url[len(prefix) :]
        break
from urllib.parse import unquote, urlsplit

from erev_api.controls.recovery_preflight import redact_diagnostics

parts = urlsplit(url)
secret = unquote(parts.password or "")
engine = build_engine(url, role=OWNER_ROLE, component="restore")
try:
    with engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        if not pattern.fullmatch(str(database)):
            print(f"restore-verify: refusing {database}: not an erev_rv_* database (DG-ENV-13)")
            sys.exit(1)
        used = connection.execute(
            text("SELECT count(*) FROM pg_namespace WHERE nspname = 'erev'")
        ).scalar_one()
    if used and os.environ.get("RESTORE_RESET") != "1":
        print(f"restore-verify: {database} already holds schema erev")
        sys.exit(1)
    if used:
        # As `erev db reset` does for the dev database (DG-MK-db-reset), here on an erev_rv_* only.
        migration_ops.drop_partitioned_tables(engine)
        with engine.begin() as connection:
            again = connection.execute(text("SELECT current_database()")).scalar_one()
            if not pattern.fullmatch(str(again)):
                sys.exit(1)
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS erev CASCADE")
            with migration_ops.bound_to(connection):
                migration_ops.drop_procrastinate_schema()
        print(f"restore-verify: schema erev and the Procrastinate objects dropped in {database} (RESET=1)")
except SystemExit:
    raise
except Exception as error:  # noqa: BLE001 - diagnostic-output rule: class and redacted message only
    print(
        f"restore-verify: target step failed with {type(error).__name__}: "
        + redact_diagnostics(str(error).splitlines()[0] if str(error) else "", secret),
        file=sys.stderr,
    )
    sys.exit(1)
finally:
    engine.dispose()
PY
echo "$TARGET: target database $TARGET_DB is ready"

# (3) pg_restore into the clone as the restore-target admin; objects come back owned by erev_owner.
FAIL_STAGE="pg_restore"
mark "mutate:pg_restore"
T_RESTORE="$(epoch)"
DUMP_PATH="$DUMP" PG_RESTORE_BIN="$PG_RESTORE" RESTORE_LOG="$RUN_DIR/restore-pg_restore.log" "$PY" - <<'PY' || fail "pg_restore failed; see $(basename "$RUN_DIR")/restore-pg_restore.log"
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

parts = urlsplit(os.environ["EREV_RESTORE_ADMIN_URL"])
env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
env["PGDATABASE"] = unquote(parts.path.lstrip("/"))
if parts.hostname:
    env["PGHOST"] = parts.hostname
if parts.port:
    env["PGPORT"] = str(parts.port)
if parts.username:
    env["PGUSER"] = unquote(parts.username)
if parts.password:
    env["PGPASSWORD"] = unquote(parts.password)
for key, value in parse_qsl(parts.query):
    if key == "sslmode":
        env["PGSSLMODE"] = value
done = subprocess.run(
    [
        os.environ["PG_RESTORE_BIN"],
        "--no-password",
        "--exit-on-error",
        "--single-transaction",
        "--dbname",
        env["PGDATABASE"],
        os.environ["DUMP_PATH"],
    ],
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    text=True,
    check=False,
)
Path(os.environ["RESTORE_LOG"]).parent.mkdir(parents=True, exist_ok=True)
from erev_api.controls.recovery_preflight import redact_diagnostics

Path(os.environ["RESTORE_LOG"]).write_text(
    redact_diagnostics(done.stderr, env.get("PGPASSWORD")), encoding="utf-8"
)
sys.exit(done.returncode)
PY
RESTORE_SECONDS=$(( $(epoch) - T_RESTORE ))
echo "$TARGET: pg_restore into $TARGET_DB done in ${RESTORE_SECONDS}s"

# (4) the file store of the clone, extracted with the data filter into the contained directory.
FAIL_STAGE="files"
mark "mutate:extract"
rm -rf "$RESTORE_DIR"
mkdir -p "$RESTORE_DIR"
TAR_PATH="$FILES_TAR" TAR_DEST="$RESTORE_DIR" TAR_ROOT="$FILE_ROOT_NAME" "$PY" - <<'PY' || fail "extracting the files tarball failed"
import os
import sys
import tarfile

from erev_api.controls import recovery_preflight as pf

findings = pf.inspect_archive(os.environ["TAR_PATH"], file_root=os.environ["TAR_ROOT"])
if findings:
    for line in findings:
        print(f"restore-verify: {line}", file=sys.stderr)
    sys.exit(1)
with tarfile.open(os.environ["TAR_PATH"], "r:gz") as archive:
    archive.extractall(os.environ["TAR_DEST"], filter="data")
PY
FILE_ROOT="$RESTORE_DIR/$FILE_ROOT_NAME"
[[ -d "$FILE_ROOT" ]] || fail "the files tarball holds no $FILE_ROOT_NAME directory"
echo "$TARGET: files extracted under $(basename "$RESTORE_DIR")/$FILE_ROOT_NAME"

# (5) the application against the clone, under the backup's master keys (never printed).
FAIL_STAGE="keys"
ENCRYPTION_KEY="$(file_value "$ENV_COPY" EREV_ENCRYPTION_KEY)"
AUDIT_KEY="$(file_value "$ENV_COPY" EREV_AUDIT_HMAC_MASTER_KEY)"
SECURITY_KEY="$(file_value "$ENV_COPY" EREV_SECURITY_EVENT_HMAC_KEY)"
[[ -n "$ENCRYPTION_KEY" && -n "$AUDIT_KEY" && -n "$SECURITY_KEY" ]] \
  || fail "the backup's .env copy lacks a master key (EREV_ENCRYPTION_KEY, EREV_AUDIT_HMAC_MASTER_KEY, EREV_SECURITY_EVENT_HMAC_KEY)"
CLONE_ENV=(
  "EREV_ENV=dev"
  "EREV_DB_OWNER_URL=$EREV_RESTORE_OWNER_URL"
  "EREV_DB_APP_URL=$EREV_RESTORE_APP_URL"
  "EREV_FILE_ROOT=$FILE_ROOT"
  "EREV_RUN_DIR=$RESTORE_DIR/run"
  "EREV_KEY_PROVIDER=local"
  "EREV_EMAIL_BACKEND=fake"
  "EREV_AI_PROVIDER=fake"
  "EREV_ENCRYPTION_KEY=$ENCRYPTION_KEY"
  "EREV_AUDIT_HMAC_MASTER_KEY=$AUDIT_KEY"
  "EREV_SECURITY_EVENT_HMAC_KEY=$SECURITY_KEY"
  "EREV_SECURITY_HMAC_SECRET_VERSION=$CLONE_SECURITY_VERSION"
)
mkdir -p "$RESTORE_DIR/run"

FAIL_STAGE="migrate"
RESTORED_REVISION="$(env "${CLONE_ENV[@]}" "$PY" -c 'from sqlalchemy import text; from erev_api.db.session import OWNER_ROLE, build_engine; from erev_api.config import get_settings
e = build_engine(get_settings().owner_database_url(), role=OWNER_ROLE, component="restore")
with e.connect() as c: print(c.execute(text("SELECT version_num FROM erev.alembic_version")).scalar_one())
e.dispose()' 2>/dev/null | tail -n 1 || echo "")"
echo "$TARGET: restored schema revision ${RESTORED_REVISION:-unknown}"
T_MIGRATE="$(epoch)"
env "${CLONE_ENV[@]}" "$EREV" migrate >"$RESTORE_DIR/run/migrate.log" 2>&1 || fail "erev migrate failed on the clone; see $(basename "$RESTORE_DIR")/run/migrate.log"
MIGRATE_SECONDS=$(( $(epoch) - T_MIGRATE ))
MIGRATED_REVISION="$(env "${CLONE_ENV[@]}" "$PY" -c 'from erev_api.db.migration_ops import code_head; print(code_head())' 2>/dev/null || echo "")"
echo "$TARGET: erev migrate on the clone done in ${MIGRATE_SECONDS}s (head ${MIGRATED_REVISION:-unknown})"

FAIL_STAGE="verify"
mkdir -p "$REPORT_DIR"
VERIFY_DOC="$REPORT_DIR/verify.json"
T_VERIFY="$(epoch)"
VERIFY_EXIT=0
env "${CLONE_ENV[@]}" "$EREV" verify --all-tenants --db "$TARGET_DB" --expect "$DIGESTS" --output "$VERIFY_DOC" \
  >"$RESTORE_DIR/run/verify.log" 2>&1 || VERIFY_EXIT=$?
VERIFY_SECONDS=$(( $(epoch) - T_VERIFY ))
grep -E '^(OK|FAIL) ' "$RESTORE_DIR/run/verify.log" || true
[[ "$VERIFY_EXIT" == "0" ]] || fail "erev verify found problems on the clone (exit $VERIFY_EXIT); see $(basename "$REPORT_DIR")/verify.json"

FAIL_STAGE="doctor"
T_DOCTOR="$(epoch)"
DOCTOR_EXIT=0
env "${CLONE_ENV[@]}" "$EREV" doctor --db "$TARGET_DB" >"$RESTORE_DIR/run/doctor.log" 2>&1 || DOCTOR_EXIT=$?
DOCTOR_SECONDS=$(( $(epoch) - T_DOCTOR ))
grep -E '^(OK|FAIL) ' "$RESTORE_DIR/run/doctor.log" || true
[[ "$DOCTOR_EXIT" == "0" ]] || fail "erev doctor failed on the clone (exit $DOCTOR_EXIT); see $(basename "$RESTORE_DIR")/run/doctor.log"
if [[ "$BASELINE_RESULT" != "PASS" ]]; then
  FAIL_STAGE="baseline"
  fail "the backup-time verification of $BACKUP_ID had result $BASELINE_RESULT; the clone reproduces failed evidence, not a clean baseline (RB-08)"
fi

# (6) the record.
FAIL_STAGE=""
write_report 0
echo "$TARGET: drill duration $(( $(epoch) - T0 ))s (restore ${RESTORE_SECONDS}s, migrate ${MIGRATE_SECONDS}s, verify ${VERIFY_SECONDS}s, doctor ${DOCTOR_SECONDS}s); no cutover RTO in a drill; record $REPORT_NAME"
echo "OK $TARGET"
