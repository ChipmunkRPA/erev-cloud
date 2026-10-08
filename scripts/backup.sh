#!/usr/bin/env bash
# make backup (docs/dev-guide.md §4.5 DG-MK-backup; §4.1 DG-MK-00a, DG-MK-00g, DG-MK-00h; §10.3
# DG-FORBID-12; 05 §7.2 OPR-15, §7.3 OPR-17, §6.5 SAR-23, §6.16 SAR-31; runbook RB-04, RB-05;
# BUILD_SPEC DEP-5; production readiness audit DEP-F; independent review P6-R1, R4, R7).
#   (0) Quiesce and capture protocol (RB-04 "Consistency"; review residual): the dev stack's api
#       and worker (PID files under EREV_RUN_DIR) must be stopped AND no other session of erev_app
#       or erev_owner may be connected to the database (pg_stat_activity, checked with the backup
#       role), so no file, key or shred changes between the digests, the dump and the archive;
#       ALLOW_LIVE=1 overrides both and the manifest records quiesced=false. The .env is hashed at
#       preflight and its copy is hashed again after it is written: a change during the backup
#       fails the run (the keys the copy would restore are verified on the copy itself).
#   (1) EREV_ENV=dev. Ruling D-95: this is the NATIVE recovery provider (default with
#       EREV_KEY_PROVIDER=local; refused under MANAGED, whose backup is Cloud SQL's). The dump
#       identity is EREV_BACKUP_URL (environment, else .env): the DBA-provisioned read-only
#       BYPASSRLS role erev_backup (RB-11), provisionable where a superuser or an actor already
#       holding BYPASSRLS exists; pg_dump as erev_owner is refused by FORCE ROW LEVEL SECURITY (04
#       DB-14). EREV_BACKUP_URL, EREV_DB_OWNER_URL and
#       EREV_DB_APP_URL must route to one server, port and database (R1), and the servers actually
#       reached must answer the same identity, so the digests (as erev_app) and the dump (as
#       erev_backup) describe one database. The .env copied for restore must be the .env the
#       application reads (no EREV_DOTENV elsewhere) and must hold the effective master keys: an
#       environment override that differs from the file fails the backup (R4). Nothing prints a
#       URL or a key; the URL reaches pg_dump only as PG* connection variables.
#   (2) `erev verify --all-tenants --json` writes the backup-time digests
#       .data/backups/erev-<UTC yyyymmddThhmmssZ>.digests.json (chain heads per tenant and book,
#       the security chain head, the file inventory with plaintext hashes, the key versions in use
#       with their envelope probes). A FAIL still backs up (evidence first) and fails the target
#       at the end; the manifest records the failed result and restore-verify treats it as failed
#       evidence, never as a clean baseline (R2).
#   (3) `pg_dump --format=custom` into erev-<timestamp>.dump; snapshot_started_at and
#       snapshot_finished_at are recorded around it, and the restore point is the start (R7).
#   (4) `tar -czf erev-<timestamp>-files.tar.gz` of EREV_FILE_ROOT (default .data/files), without
#       the .incoming partials; the file root's name must be a plain directory name (R3).
#   (5) a copy of .env as erev-<timestamp>.env with mode 0600 (the master keys travel with the
#       data, D-75 Q8; OPR-17; RB-05).
#   (6) erev-<timestamp>.manifest.json (schema erev-backup-manifest/2): SHA-256 and size of
#       exactly the four members, the database name, schema revision, build sha, the snapshot and
#       archive instants, quiesced, the digests result; validated by
#       erev_api.controls.recovery_preflight.validate_manifest before it is written; then
#       .run/reports/backup/report.json (DG-MK-00g).
# Prints only file names. The final line is "OK backup" or "FAIL backup: <reason>" (DG-MK-00a).
# GATE-BIND-1 (DG-MK-00i; rev 1.81, the first run on a clean tree): `make backup` runs this script
# in an execution context, a clone that holds the code and a copy of .env but none of the
# deployment's live data. The recipe therefore exports the worktree as EREV_BACKUP_DATA_ROOT (a
# relative EREV_FILE_ROOT, the default .data/files included, resolves against it, exactly as the
# application resolves it against its own checkout, and is handed to `erev verify` as an absolute
# path) and the worktree's run directory as EREV_RUN_DIR (the PID files of step 0 and the
# backup-verify.log); the report alone is written in the context, where the wrapper reads it.
# Test-only overrides (backend/tests/unit/deploy/test_backup_restore_scripts.py): EREV_BACKUP_ROOT
# (a scratch repository root), EREV_PG_DUMP_BIN, EREV_BACKUP_EREV_BIN, EREV_RECOVERY_IDENTITY_STUB
# (a JSON file of server-identity rows per variable, instead of connecting).
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${EREV_BACKUP_ROOT:-$SCRIPT_ROOT}"
PY="$SCRIPT_ROOT/backend/.venv/bin/python"
EREV="${EREV_BACKUP_EREV_BIN:-$SCRIPT_ROOT/backend/.venv/bin/erev}"
PG_DUMP="${EREV_PG_DUMP_BIN:-pg_dump}"
TARGET="backup"
COMMAND="${EREV_BACKUP_COMMAND:-make backup}"
RUN_DIR="${EREV_RUN_DIR:-.run}"
[[ "$RUN_DIR" == /* ]] || RUN_DIR="$ROOT/$RUN_DIR"
# Under the wrapper the report is written in the execution context (the wrapper reads it there and
# copies it back); the run directory itself is the worktree's, exported by the recipe.
if [[ -n "${EREV_GATE_CONTEXT:-}" ]]; then
  REPORT_DIR="$EREV_GATE_CONTEXT/.run/reports/$TARGET"
else
  REPORT_DIR="$RUN_DIR/reports/$TARGET"
fi
# The directory a relative file root resolves against: the deployment (the worktree), not the code.
DATA_ROOT="${EREV_BACKUP_DATA_ROOT:-$ROOT}"
DOTENV="${EREV_DOTENV:-.env}"
[[ "$DOTENV" == /* ]] || DOTENV="$ROOT/$DOTENV"
BACKUP_DIR="${EREV_BACKUP_DIR:-.data/backups}"
[[ "$BACKUP_DIR" == /* ]] || BACKUP_DIR="$ROOT/$BACKUP_DIR"
ALLOW_LIVE="${ALLOW_LIVE:-}"

# The caller's environment gates the test-only identity stub (honoured under test or dev only).
CALLER_EREV_ENV="${EREV_ENV:-dev}"
export EREV_ENV=dev
export PREFLIGHT_CALLER_ENV="$CALLER_EREV_ENV"
export PYTHONPATH="$SCRIPT_ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
STARTED_AT=""
DOTENV_SHA256=""
BACKUP_ID=""
DIGESTS_RC=""
FAIL_STAGE=""
DUMP=""
FILES_TAR=""
ENV_COPY=""
DIGESTS=""
MANIFEST=""
ARTIFACTS_OWNED=""
CLEANED=""
# Test-only clock pin for the same-second witness (honoured under EREV_ENV test or dev only).
BACKUP_TIMESTAMP_OVERRIDE="${EREV_BACKUP_TIMESTAMP:-}"
QUIESCED="true"
SNAPSHOT_STARTED_AT=""
SNAPSHOT_FINISHED_AT=""

utc_now() {
  "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'
}

# dotenv_value <name>: the named line of the .env file, without surrounding quotes; never printed.
dotenv_value() {
  local value
  [[ -f "$DOTENV" ]] || return 0
  value="$(sed -n "s/^$1=//p" "$DOTENV" | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

pid_alive() { [[ "$1" =~ ^[0-9]+$ ]] && kill -0 "$1" 2>/dev/null; }

# mark <phase:step>: the call sequence, appended to EREV_RECOVERY_CALLS_LOG when set (tests).
mark() { [[ -z "${EREV_RECOVERY_CALLS_LOG:-}" ]] || echo "$1" >>"$EREV_RECOVERY_CALLS_LOG"; }

# write_report <exit code> [failure stage]: .run/reports/backup/report.json (DG-MK-00g).
write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_EXIT="$1" REPORT_STAGE="${2:-}" REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" \
    REPORT_COMMAND="$COMMAND" REPORT_ROOT="$ROOT" REPORT_BACKUP_ID="$BACKUP_ID" \
    REPORT_BACKUP_DIR="$BACKUP_DIR" REPORT_DIGESTS_RC="$DIGESTS_RC" REPORT_CLEANED="$CLEANED" \
    "$PY" - "$REPORT_DIR/report.json" <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

env = os.environ
root = env["REPORT_ROOT"]


def git(*args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


build_sha = git("rev-parse", "HEAD") or "nogit"
porcelain = git("status", "--porcelain")
manifest_path = Path(env["REPORT_BACKUP_DIR"]) / f"{env['REPORT_BACKUP_ID']}.manifest.json"
manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.is_file() else None
exit_code = int(env["REPORT_EXIT"])
failures = [] if exit_code == 0 else [{"stage": env["REPORT_STAGE"] or "unknown", "exit_code": exit_code}]
report = {
    "target": "backup",
    "command": env["REPORT_COMMAND"],
    "build_sha": build_sha,
    "worktree_dirty": bool(porcelain) if porcelain is not None else False,
    "started_at": env["REPORT_STARTED"],
    "finished_at": env["REPORT_FINISHED"],
    "exit_code": exit_code,
    "counts": {
        "files": 0 if manifest is None else len(manifest["files"]),
        "bytes": 0 if manifest is None else sum(f["size_bytes"] for f in manifest["files"].values()),
        "digests_result": None if manifest is None else manifest["digests"]["result"],
    },
    "failures": failures,
    "backup_id": env["REPORT_BACKUP_ID"] or None,
    "manifest": str(manifest_path) if manifest is not None else None,
    "cleaned": env["REPORT_CLEANED"].split(),
}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

# cleanup_partial: a failed run leaves no partial backup set behind. The five artifact paths were
# proven absent at preflight (ARTIFACTS_OWNED is set right after that check), so whatever exists at
# failure was written by this run; a pre-existing id, refused before that point, is never touched.
# Without this a backup that failed after its digests blocked the next backup in the same second
# (second-resolution id; lane P5's finding of 2026-09-22).
cleanup_partial() {
  [[ -n "$ARTIFACTS_OWNED" ]] || return 0
  local path
  for path in "$DUMP" "$FILES_TAR" "$ENV_COPY" "$DIGESTS" "$MANIFEST"; do
    if [[ -n "$path" && -e "$path" ]]; then
      rm -f -- "$path" && CLEANED="$CLEANED $(basename "$path")"
    fi
  done
  CLEANED="${CLEANED# }"
  [[ -z "$CLEANED" ]] || echo "$TARGET: removed the partial backup set: $CLEANED"
}

fail() {
  cleanup_partial
  echo "FAIL $TARGET: $1"
  write_report 1 "${FAIL_STAGE:-$1}" || true
  exit 1
}

STARTED_AT="$(utc_now)"

# (0) quiesce: nothing may change files, keys or shred state between the digests and the archive.
FAIL_STAGE="quiesce"
for name in api worker; do
  pid="$(cat "$RUN_DIR/$name.pid" 2>/dev/null || true)"
  if pid_alive "$pid"; then
    if [[ "$ALLOW_LIVE" == "1" ]]; then
      QUIESCED="false"
    else
      fail "$name is running (PID file $(basename "$RUN_DIR")/$name.pid); stop the stack first (make dev-down) or set ALLOW_LIVE=1 to record a non-quiesced backup (RB-04)"
    fi
  fi
done

# (1) identities, routing and keys; nothing printed but variable names, hosts, ports and databases.
FAIL_STAGE="preconditions"
[[ -f "$DOTENV" ]] || fail ".env not found; nothing to back up the master keys from (RB-05)"
if [[ "$(cd "$(dirname "$DOTENV")" && pwd)/$(basename "$DOTENV")" != "$ROOT/.env" ]]; then
  fail "the backup copies the .env the application reads ($ROOT/.env); EREV_DOTENV pointing elsewhere is not supported (RB-05)"
fi
if [[ -z "${EREV_BACKUP_URL:-}" ]]; then
  EREV_BACKUP_URL="$(dotenv_value EREV_BACKUP_URL)"
fi
[[ -n "${EREV_BACKUP_URL:-}" ]] \
  || fail "EREV_BACKUP_URL is not set: name the erev_backup role on the database (pg_dump as erev_owner is refused by FORCE ROW LEVEL SECURITY, RB-04, RB-11)"
export EREV_BACKUP_URL
for name in EREV_DB_OWNER_URL EREV_DB_APP_URL EREV_FILE_ROOT; do
  if [[ -z "${!name:-}" ]]; then
    value="$(dotenv_value "$name")"
    [[ -z "$value" ]] || export "$name=$value"
  fi
done
[[ -n "${EREV_DB_OWNER_URL:-}" && -n "${EREV_DB_APP_URL:-}" ]] || fail "EREV_DB_OWNER_URL and EREV_DB_APP_URL are not set"
[[ "$DATA_ROOT" == /* && -d "$DATA_ROOT" ]] || fail "EREV_BACKUP_DATA_ROOT must name an existing directory by its absolute path"
FILE_ROOT="${EREV_FILE_ROOT:-.data/files}"
[[ "$FILE_ROOT" == /* ]] || FILE_ROOT="$DATA_ROOT/$FILE_ROOT"
[[ -d "$FILE_ROOT" ]] || fail "file root $(basename "$FILE_ROOT") does not exist"
# `erev verify` resolves a relative EREV_FILE_ROOT against its own checkout (the execution context
# under the wrapper): it is given the store this script archives, by its absolute path.
export EREV_FILE_ROOT="$FILE_ROOT"
command -v "$PG_DUMP" >/dev/null 2>&1 || fail "pg_dump not found (DG-ENV-04)"
DOTENV_SHA256="$("$PY" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$DOTENV")"
# R1: one endpoint for the dump, the migrations and the digests, checked on the URLs and then on
# the servers reached; R4: the keys the digests will use are the keys the .env copy carries;
# quiesce: no application session may be connected (ALLOW_LIVE=1 records quiesced=false).
DATABASE="$(PREFLIGHT_DOTENV="$DOTENV" PREFLIGHT_FILE_ROOT="$FILE_ROOT" PREFLIGHT_ALLOW_LIVE="$ALLOW_LIVE" "$PY" - <<'PY'
import json
import os
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

from check_env import read_env_file
from erev_api.controls import recovery_preflight as pf


def refuse(message: str) -> None:
    print(f"backup: {message}", file=sys.stderr)
    sys.exit(1)


urls = {name: os.environ[name] for name in ("EREV_BACKUP_URL", "EREV_DB_OWNER_URL", "EREV_DB_APP_URL")}
try:
    endpoint = pf.same_endpoint(urls)
except pf.PreflightError as error:
    refuse(str(error))
if not pf.FILE_ROOT_NAME.fullmatch(os.path.basename(os.environ["PREFLIGHT_FILE_ROOT"])):
    refuse("EREV_FILE_ROOT must end in a plain directory name")
file_values = read_env_file(__import__("pathlib").Path(os.environ["PREFLIGHT_DOTENV"]))
mismatches = pf.effective_key_mismatches(os.environ, file_values)
if mismatches:
    refuse("; ".join(mismatches))

try:
    stub = pf.identity_stub(os.environ, env_name=os.environ.get("PREFLIGHT_CALLER_ENV"))
except pf.PreflightError as error:
    refuse(str(error))
writers = 0
if stub:
    loaded = json.load(open(stub))
    rows = {name: tuple(loaded[name]) for name in urls}
    writers = int(loaded.get("writers", 0))
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
                if name == "EREV_BACKUP_URL":
                    # Quiesce: other application sessions on this database are writers we cannot
                    # see stop; the backup role reads pg_stat_activity like any role.
                    writers = int(
                        conn.execute(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                            "AND usename IN ('erev_app', 'erev_owner') AND pid <> pg_backend_pid()"
                        ).fetchone()[0]
                    )
        except psycopg.Error as exc:
            refuse(f"cannot reach the server named by {name}: {type(exc).__name__}")
findings = pf.server_identity(rows)
if findings:
    refuse("; ".join(findings))
if rows and rows[next(iter(rows))][0] != endpoint.database:
    refuse(f"the server reached by EREV_BACKUP_URL serves {rows[next(iter(rows))][0]}, not {endpoint.database}")
if writers and os.environ.get("PREFLIGHT_ALLOW_LIVE") != "1":
    refuse(
        f"{writers} application session(s) (erev_app or erev_owner) are connected to "
        f"{endpoint.database}; stop them or set ALLOW_LIVE=1 to record a non-quiesced backup (RB-04)"
    )
print(endpoint.database + (" live" if writers else ""))
PY
)" || fail "preflight refused (see the backup: line above)"
if [[ "$DATABASE" == *" live" ]]; then
  DATABASE="${DATABASE% live}"
  QUIESCED="false"
fi

if [[ -n "$BACKUP_TIMESTAMP_OVERRIDE" ]]; then
  [[ "$CALLER_EREV_ENV" == "test" || "$CALLER_EREV_ENV" == "dev" ]] \
    || fail "EREV_BACKUP_TIMESTAMP is a test-only override (EREV_ENV=$CALLER_EREV_ENV)"
  [[ "$BACKUP_TIMESTAMP_OVERRIDE" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || fail "EREV_BACKUP_TIMESTAMP is not yyyymmddThhmmssZ"
  TIMESTAMP="$BACKUP_TIMESTAMP_OVERRIDE"
else
  TIMESTAMP="$("$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y%m%dT%H%M%SZ"))')"
fi
BACKUP_ID="erev-$TIMESTAMP"
mkdir -p "$BACKUP_DIR"
DUMP="$BACKUP_DIR/$BACKUP_ID.dump"
FILES_TAR="$BACKUP_DIR/$BACKUP_ID-files.tar.gz"
ENV_COPY="$BACKUP_DIR/$BACKUP_ID.env"
DIGESTS="$BACKUP_DIR/$BACKUP_ID.digests.json"
MANIFEST="$BACKUP_DIR/$BACKUP_ID.manifest.json"
for existing in "$DUMP" "$FILES_TAR" "$ENV_COPY" "$DIGESTS" "$MANIFEST"; do
  [[ ! -e "$existing" ]] || fail "$(basename "$existing") already exists"
done
ARTIFACTS_OWNED="1"
mark "preflight:complete"
echo "$TARGET: database $DATABASE -> $BACKUP_ID (quiesced=$QUIESCED)"

# (2) backup-time digests: chain heads, file inventory, key versions with envelope probes.
FAIL_STAGE="digests"
mkdir -p "$RUN_DIR"
DIGESTS_RC=0
mark "write:digests"
"$EREV" verify --all-tenants --json --output "$DIGESTS" >"$RUN_DIR/backup-verify.log" 2>&1 || DIGESTS_RC=$?
[[ "$DIGESTS_RC" == "0" || "$DIGESTS_RC" == "1" ]] || fail "erev verify exited $DIGESTS_RC; see $(basename "$RUN_DIR")/backup-verify.log"
[[ -f "$DIGESTS" ]] || fail "erev verify wrote no digests document"
echo "$(basename "$DIGESTS")"

# (3) pg_dump -Fc as the backup role; the snapshot instants bracket it (the restore point is the
#     start). The URL is split into PG* variables inside Python; nothing printed.
FAIL_STAGE="pg_dump"
mark "write:pg_dump"
SNAPSHOT_STARTED_AT="$(utc_now)"
DUMP_PATH="$DUMP" PG_DUMP_BIN="$PG_DUMP" "$PY" - <<'PY' || fail "pg_dump failed"
import os
import subprocess
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

parts = urlsplit(os.environ["EREV_BACKUP_URL"])
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
    [os.environ["PG_DUMP_BIN"], "--format=custom", "--no-password", "--file", os.environ["DUMP_PATH"]],
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    text=True,
    check=False,
)
if done.returncode != 0:
    # Diagnostic-output rule: whatever pg_dump says is passed through the redaction helper (DSN
    # credentials, PGPASSWORD and the literal password never reach the terminal).
    from erev_api.controls.recovery_preflight import redact_diagnostics

    sys.stderr.write(redact_diagnostics(done.stderr, env.get("PGPASSWORD")))
    sys.exit(done.returncode)
PY
SNAPSHOT_FINISHED_AT="$(utc_now)"
echo "$(basename "$DUMP")"

# (4) the file store, without partial uploads or host-specific AppleDouble metadata.
# macOS BSD tar otherwise adds ._files outside the declared archive root. The restore
# validator must keep rejecting such paths; only application bytes belong in this archive.
FAIL_STAGE="files"
COPYFILE_DISABLE=1 tar -czf "$FILES_TAR" -C "$(dirname "$FILE_ROOT")" --exclude "$(basename "$FILE_ROOT")/.incoming" "$(basename "$FILE_ROOT")" \
  || fail "tar of the file root failed"
echo "$(basename "$FILES_TAR")"

# (5) the master keys travel with the data: a 0600 copy of .env (OPR-17, RB-05). The copy must be
#     byte-identical to the .env hashed at preflight (a change during the backup is refused), and
#     the keys the copy would restore are verified on the copy itself (capture, then check).
FAIL_STAGE="env"
cp "$DOTENV" "$ENV_COPY" && chmod 600 "$ENV_COPY" || fail "copy of .env failed"
COPY_SHA256="$("$PY" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ENV_COPY")"
[[ "$COPY_SHA256" == "$DOTENV_SHA256" ]] || fail ".env changed during the backup (its copy differs from the file hashed at preflight); the backup set is not consistent"
PREFLIGHT_ENV_COPY="$ENV_COPY" "$PY" - <<'PY' || fail "the .env copy does not carry the effective master keys (see the backup: line above)"
import os
import sys
from pathlib import Path

from check_env import read_env_file
from erev_api.controls import recovery_preflight as pf

mismatches = pf.effective_key_mismatches(os.environ, read_env_file(Path(os.environ["PREFLIGHT_ENV_COPY"])))
if mismatches:
    print("backup: " + "; ".join(mismatches), file=sys.stderr)
    sys.exit(1)
PY
echo "$(basename "$ENV_COPY")"

# (6) the manifest: exactly the four members with SHA-256 and size, the instants, the digests
#     result; validated before it is written.
FAIL_STAGE="manifest"
MANIFEST_PATH="$MANIFEST" MANIFEST_BACKUP_ID="$BACKUP_ID" MANIFEST_DATABASE="$DATABASE" \
  MANIFEST_STARTED="$STARTED_AT" MANIFEST_DIGESTS_RC="$DIGESTS_RC" MANIFEST_ROOT="$ROOT" \
  MANIFEST_PG_DUMP="$PG_DUMP" MANIFEST_FILE_ROOT="$FILE_ROOT" MANIFEST_QUIESCED="$QUIESCED" \
  MANIFEST_SNAPSHOT_STARTED="$SNAPSHOT_STARTED_AT" MANIFEST_SNAPSHOT_FINISHED="$SNAPSHOT_FINISHED_AT" \
  "$PY" - "$DUMP" "$FILES_TAR" "$ENV_COPY" "$DIGESTS" <<'PY' || fail "manifest failed"
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from erev_api.controls import recovery_preflight as pf

env = os.environ


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=env["MANIFEST_ROOT"], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def tool_version(binary: str) -> str | None:
    try:
        done = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout.strip() or None


files = {}
for name in sys.argv[1:]:
    path = Path(name)
    files[path.name] = {"sha256": sha256_of(path), "size_bytes": path.stat().st_size}
digests = pf.load_json_strict(Path(sys.argv[4]).read_text("utf-8"))
porcelain = git("status", "--porcelain")
manifest = {
    "schema": pf.MANIFEST_SCHEMA,
    "backup_id": env["MANIFEST_BACKUP_ID"],
    "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    "started_at": env["MANIFEST_STARTED"],
    "snapshot_started_at": env["MANIFEST_SNAPSHOT_STARTED"],
    "snapshot_finished_at": env["MANIFEST_SNAPSHOT_FINISHED"],
    "quiesced": env["MANIFEST_QUIESCED"] == "true",
    "env_copy_sha256": files[Path(sys.argv[3]).name]["sha256"],
    "database": env["MANIFEST_DATABASE"],
    "file_root": Path(env["MANIFEST_FILE_ROOT"]).name,
    "build_sha": git("rev-parse", "HEAD") or "nogit",
    "worktree_dirty": bool(porcelain) if porcelain is not None else False,
    "engine_version": digests.get("engine_version"),
    "schema_revision": digests.get("schema_revision"),
    "files": files,
    "digests": {
        "file": Path(sys.argv[4]).name,
        "result": digests.get("result"),
        "exit_code": int(env["MANIFEST_DIGESTS_RC"]),
        "generated_at": digests.get("generated_at"),
        "latest_evidence_at": digests.get("latest_evidence_at"),
        "tenants": digests.get("counts", {}).get("tenants"),
        "files_checked": digests.get("counts", {}).get("files", {}).get("checked"),
        "failures": digests.get("counts", {}).get("failures"),
    },
    "key_versions": digests.get("key_versions"),
    # P2/P6 integration: the deployment's signing pin (a key id, never material) and every
    # security key id the backed-up global chain names travel with the evidence.
    "security_hmac_pin": (digests.get("security_chain") or {}).get("current_key_id"),
    "security_required_key_ids": (digests.get("security_chain") or {}).get("required_key_ids"),
    "tool_versions": {"pg_dump": tool_version(env["MANIFEST_PG_DUMP"])},
}
errors = pf.validate_manifest(manifest, backup_id=env["MANIFEST_BACKUP_ID"])
if errors:
    for line in errors:
        print(f"backup: {line}", file=sys.stderr)
    sys.exit(1)
Path(env["MANIFEST_PATH"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
echo "$(basename "$MANIFEST")"
# The set is complete from here: it is kept even when the evidence failed (the FAIL below is the
# verdict on the digests, not a partial run), so cleanup_partial no longer owns it.
ARTIFACTS_OWNED=""

if [[ "$DIGESTS_RC" != "0" ]]; then
  FAIL_STAGE="digests"
  fail "chain, file or key verification found problems (see $(basename "$DIGESTS")); the backup was still written as failed evidence"
fi
write_report 0
echo "OK $TARGET"
