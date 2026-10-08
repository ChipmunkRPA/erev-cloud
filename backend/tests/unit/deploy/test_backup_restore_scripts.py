"""Supervisor target scripts: the DEP-5 ``backup`` part and the DEP-6 ``restore-verify`` drill
(dev-guide §4.5 DG-MK-backup, DG-MK-restore-verify; §4.1 DG-MK-00a, DG-MK-00g, DG-MK-00h; §10.3
DG-FORBID-12; 05 OPR-11, OPR-15, OPR-17; RB-04 to RB-06; independent review P6-R1 to R4, R7 of
2026-09-19). Lane P3's ``test_supervisor_scripts.py`` holds the ``tf-validate`` part and P1's
``test_docker_build.py`` the ``docker-build`` part; the banner rule below applies to every
DEP-5/DEP-6 target present, so the modules coexist.

Static rules, ``bash -n``, and runs of both scripts against stand-in ``pg_dump``/``pg_restore``
and ``erev`` binaries in a scratch repository root: no database, no worktree ``.env`` and no real
backup directory is touched; the scratch ``.env`` holds a sentinel password that must never be
printed, and the server-identity rows the scripts would fetch come from a stub file
(``EREV_RECOVERY_IDENTITY_STUB``), so the same-identity comparison is exercised without a server.
``scripts/restore_verify.sh`` is driven up to its refusals, all of which happen before any
connection, reset, restore, extraction or removal. The Makefile recipes are covered by
``test_makefile_targets``.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from erev_api.controls import recovery_preflight as pf

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"
MAKEFILE = ROOT / "Makefile"
BACKUP = SCRIPTS / "backup.sh"
RESTORE = SCRIPTS / "restore_verify.sh"
# The six DEP-5 targets plus the DEP-6 drill; the rules below apply to every one present.
SUPERVISOR_TARGETS = {
    "audit-deps": "scripts/audit_deps.sh",
    "zap-baseline": "scripts/zap_baseline.sh",
    "docker-build": "scripts/docker_build.sh",
    "compose-verify": "scripts/compose_verify.sh",
    "tf-validate": "scripts/tf_validate.sh",
    "backup": "scripts/backup.sh",
    "restore-verify": "scripts/restore_verify.sh",
}
SENTINEL = "never-print-this-sentinel"
# Password-like values the scratch .env carries only to prove they are never printed.
SCRATCH_OWNER_URL = f"postgresql://erev_owner:{SENTINEL}@127.0.0.1:1/erev"
SCRATCH_APP_URL = f"postgresql://erev_app:{SENTINEL}@127.0.0.1:1/erev"
SCRATCH_BACKUP_URL = f"postgresql://erev_backup:{SENTINEL}@127.0.0.1:1/erev"
KEYS = {
    "EREV_ENCRYPTION_KEY": "1" * 64,
    "EREV_AUDIT_HMAC_MASTER_KEY": "2" * 64,
    "EREV_SECURITY_EVENT_HMAC_KEY": "3" * 64,
}
IDENTITY = ["erev", "16400", "2026-09-19 10:00:00+00", "127.0.0.1", "1"]
TENANT_ID = "11111111-1111-4111-8111-111111111111"

PG_DUMP_STUB = """#!/usr/bin/env bash
# pg_dump / pg_restore stand-in: records its arguments and environment names, writes a fake dump.
if [[ "${1:-}" == "--version" ]]; then echo "pg_dump (PostgreSQL) 17.0 (stub)"; exit 0; fi
echo "$*" >>"$STUB_CALLS"
env | sed -n 's/^\\(PG[A-Z]*\\)=.*/\\1/p' | sort | tr '\\n' ' ' >>"$STUB_CALLS"
echo >>"$STUB_CALLS"
[[ -n "${PGPASSWORD:-}" ]] || { echo "no PGPASSWORD" >&2; exit 3; }
for arg in "$@"; do out="$arg"; done
if [[ "${STUB_PG_DUMP_RC:-0}" != "0" ]]; then
  # A tool that echoes its connection string on failure: the scripts must redact it.
  echo "pg_dump: error: stub failure" >&2
  dsn="postgresql://erev_backup:${PGPASSWORD}@127.0.0.1:1/erev"
  echo "pg_dump: error: connection to $dsn failed: PGPASSWORD=${PGPASSWORD}" >&2
  exit "$STUB_PG_DUMP_RC"
fi
if [[ -n "${STUB_MUTATE_DOTENV:-}" ]]; then
  # A concurrent edit of .env during the dump (the capture-protocol race the residual names).
  echo "# edited during the backup" >>"$STUB_MUTATE_DOTENV"
fi
printf 'PGDMP-stub' >"$out"
"""

# The erev stand-in writes a populated verification document (P6-R2 refuses an empty one).
EREV_STUB = """#!/usr/bin/env bash
echo "$*" >>"$STUB_CALLS"
# The clone's signing pin is a non-secret key version; the drill must bind it explicitly.
echo "SECURITY_PIN=${EREV_SECURITY_HMAC_SECRET_VERSION:-unset}" >>"$STUB_CALLS"
# The file store the verifier is told to read (the wrapper's shape hands it an absolute path).
echo "FILE_ROOT=${EREV_FILE_ROOT:-unset}" >>"$STUB_CALLS"
out=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
cp "$STUB_DIGESTS" "$out"
stamp='import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'
now="$("$STUB_PY" -c "$stamp")"
sed -i.bak "s/STUB_RESULT/${STUB_VERIFY_RESULT:-PASS}/" "$out" && rm -f "$out.bak"
sed -i.bak "s/STUB_GENERATED_AT/$now/" "$out" && rm -f "$out.bak"
exit "${STUB_VERIFY_RC:-0}"
"""


def _digests_document() -> dict[str, object]:
    return {
        "schema": pf.DOCUMENT_SCHEMA,
        "result": "STUB_RESULT",
        "engine_version": "0.2.0",
        "schema_revision": "0001_stub",
        "generated_at": "STUB_GENERATED_AT",  # the stub stamps the run instant (chronology)
        "latest_evidence_at": "2026-09-19T11:59:00.000000Z",
        "verifier_events_appended": 1,
        "security_chain": {
            "last_chain_seq": 3,
            "last_hmac": "a" * 64,
            "head_key_id": "security-hmac:1",
            "current_key_id": "security-hmac:1",
            "required_key_ids": ["security-hmac:1"],
        },
        "tenants": [
            {
                "tenant_id": TENANT_ID,
                "code": "acme",
                "head": {"last_chain_seq": 12, "last_hmac": "b" * 64},
                "ledger_chains": [],
                "files": {"entries": [{"storage_key": "k", "sha256": "c" * 64, "status": "ok"}]},
                "audit_hmac_keys": [{"key_id": f"audit-hmac:{TENANT_ID}:1", "available": True}],
            }
        ],
        "counts": {"tenants": 1, "failures": 0, "files": {"checked": 1}},
        "key_versions": {
            "kek": [],
            "security_hmac": [{"key_id": "security-hmac:1", "available": True}],
            "audit_hmac": [],
        },
    }


@pytest.fixture
def scratch() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _write_executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _env_text(**overrides: str | None) -> str:
    values: dict[str, str | None] = {
        "EREV_ENV": "dev",
        "EREV_DB_OWNER_URL": SCRATCH_OWNER_URL,
        "EREV_DB_APP_URL": SCRATCH_APP_URL,
        "EREV_BACKUP_URL": SCRATCH_BACKUP_URL,
        **KEYS,
    }
    values.update(overrides)
    return "".join(f"{k}={v}\n" for k, v in values.items() if v is not None)


def _scratch_repo(scratch: Path, name: str = "repo") -> Path:
    repo = scratch / name
    (repo / ".data" / "files" / "t" / "ATTACHMENT").mkdir(parents=True)
    (repo / ".data" / "files" / ".incoming").mkdir()
    (repo / ".data" / "files" / "t" / "ATTACHMENT" / "obj").write_bytes(b"ciphertext")
    (repo / ".data" / "files" / ".incoming" / "partial").write_bytes(b"partial")
    (repo / ".env").write_text(_env_text(), encoding="utf-8")
    return repo


RESTORE_IDENTITY = ["erev_rv_clone", "16401", "2026-09-19 10:00:00+00", "127.0.0.1", "1"]


def _identity_stub(scratch: Path, rows: dict[str, list[str]] | None = None) -> Path:
    """The server-identity rows the scripts would fetch: the source names answer the source
    database, the restore names the clone; custom rows go to their own file."""
    default = {
        name: IDENTITY for name in ("EREV_BACKUP_URL", "EREV_DB_OWNER_URL", "EREV_DB_APP_URL")
    }
    default.update(
        {
            name: RESTORE_IDENTITY
            for name in ("EREV_RESTORE_OWNER_URL", "EREV_RESTORE_APP_URL", "EREV_RESTORE_ADMIN_URL")
        }
    )
    path = scratch / ("identity-custom.json" if rows is not None else "identity.json")
    path.write_text(json.dumps(rows if rows is not None else default), encoding="utf-8")
    return path


def _run(script: Path, repo: Path, scratch: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    calls = scratch / "calls.log"
    calls.touch()
    digests = scratch / "digests.json"
    digests.write_text(json.dumps(_digests_document()), encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("EREV_", "PG", "STUB_", "MAKE", "BACKUP", "RESET", "ALLOW_LIVE"))
    }
    env.update(
        {
            "EREV_BACKUP_ROOT": str(repo),
            "EREV_RESTORE_ROOT": str(repo),
            "EREV_RUN_DIR": str(repo / ".run"),
            "EREV_PG_DUMP_BIN": str(_write_executable(scratch / "bin" / "pg_dump", PG_DUMP_STUB)),
            "EREV_PG_RESTORE_BIN": str(
                _write_executable(scratch / "bin" / "pg_restore", PG_DUMP_STUB)
            ),
            "EREV_BACKUP_EREV_BIN": str(_write_executable(scratch / "bin" / "erev", EREV_STUB)),
            "EREV_RESTORE_EREV_BIN": str(scratch / "bin" / "erev"),
            "EREV_RECOVERY_IDENTITY_STUB": str(_identity_stub(scratch)),
            "STUB_CALLS": str(calls),
            "STUB_DIGESTS": str(digests),
            "STUB_PY": sys.executable,
            "TMPDIR": str(scratch),
        }
    )
    env.update(extra)
    return subprocess.run(
        ["bash", str(script)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _backed_up(scratch: Path, repo: Path, **extra: str) -> str:
    done = _run(BACKUP, repo, scratch, **extra)
    assert done.returncode == 0, done.stdout + done.stderr
    (manifest,) = (repo / ".data" / "backups").glob("*.manifest.json")
    return manifest.name.removesuffix(".manifest.json")


def _restore_urls(database: str = "erev_rv_clone", **overrides: str) -> dict[str, str]:
    urls = {
        "EREV_RESTORE_OWNER_URL": f"postgresql://erev_owner:{SENTINEL}@127.0.0.1:1/{database}",
        "EREV_RESTORE_APP_URL": f"postgresql://erev_app:{SENTINEL}@127.0.0.1:1/{database}",
        "EREV_RESTORE_ADMIN_URL": f"postgresql://erev_restore_admin:{SENTINEL}@127.0.0.1:1/{database}",
    }
    urls.update(overrides)
    return urls


def _last(done: subprocess.CompletedProcess[str]) -> str:
    return done.stdout.splitlines()[-1]


def _phony() -> set[str]:
    targets: set[str] = set()
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(".PHONY:"):
            targets.update(line.removeprefix(".PHONY:").split())
    return targets


def _recipe(target: str) -> str | None:
    text = MAKEFILE.read_text(encoding="utf-8")
    marker = f"\n{target}:\n"
    if marker not in text:
        return None
    return text.split(marker, 1)[1].split("\n\n", 1)[0]


def test_makefile_supervisor_targets() -> None:
    # DG-MK-00h: every supervisor target present is .PHONY, prints its banner first and calls its
    # script; the DEP-5 targets other lanes own are listed so the rule applies the day they land.
    present = {t: s for t, s in SUPERVISOR_TARGETS.items() if _recipe(t) is not None}
    assert {"backup", "restore-verify"} <= set(present)
    for target, script in present.items():
        recipe = _recipe(target)
        assert recipe is not None
        first = next(line for line in recipe.splitlines() if line.strip())
        assert first.strip() == f'@echo "SUPERVISOR TARGET {target} (D-48a)"', target
        assert target in _phony(), target
        # GATE-BIND-1 (DG-MK-00i): a wrapped supervisor target calls its script from <target>-gate.
        inner = _recipe(f"{target}-gate") or ""
        assert script in recipe or script in inner, target
        assert (ROOT / script).is_file(), script


def test_scripts_parse() -> None:
    # bash -n: syntax only, nothing executes (DG-FORBID-12).
    for script in sorted(SCRIPTS.glob("*.sh")):
        done = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert done.returncode == 0, (script.name, done.stderr)
        assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n"), script.name


def test_backup_and_restore_rules() -> None:
    # DG-MK-backup: the URL travels through the environment (PG* variables built inside Python),
    # never as a pg_dump argument or an echo; the .env copy gets mode 0600; only file names are
    # printed. DG-MK-restore-verify: pg_restore into an allow-listed erev_rv_* target only, never a
    # database drop, master keys from the backup's .env copy, extraction through the data filter.
    backup = BACKUP.read_text(encoding="utf-8")
    restore = RESTORE.read_text(encoding="utf-8")
    for text in (backup, restore):
        assert "set -euo pipefail" in text
        assert "/" + "tmp" not in text.replace("$TMPDIR", "")  # DG-FORBID-04 (literal split)
        assert not re.search(r"echo\s+\"?\$\{?EREV_(DB|RESTORE|BACKUP)_[A-Z_]*URL", text)
        assert not re.search(r"echo\s+\"?\$\{?(ENCRYPTION_KEY|AUDIT_KEY|SECURITY_KEY)", text)
        assert "set -x" not in text
        assert "recovery_preflight" in text  # the pure checks come from one module
    assert 'env["PGPASSWORD"]' in backup and 'env["PGPASSWORD"]' in restore
    assert re.search(r"--dbname\W", backup) is None  # the URL is never an argument
    assert "chmod 600" in backup
    assert "pg_dump" in backup and "--format=custom" in backup
    assert '"$EREV" verify --all-tenants --json' in backup
    assert (
        "same_endpoint" in backup
        and "server_identity" in backup
        and "SERVER_IDENTITY_SQL" in backup
    )
    assert "effective_key_mismatches" in backup and "validate_manifest" in backup
    assert "SNAPSHOT_STARTED_AT" in backup and "snapshot_started_at" in backup
    assert "ALLOW_LIVE" in backup and "api.pid" not in backup.replace('"$RUN_DIR/$name.pid"', "")

    assert "pg_restore" in restore and "--exit-on-error" in restore and "--no-owner" not in restore
    assert "DROP " + "DATABASE" not in restore  # literal split so DG-ARC-05 does not flag the test
    assert "validate_backup_id" in restore and "validate_manifest" in restore
    assert "inspect_archive" in restore and 'filter="data"' in restore and "tar -xzf" not in restore
    assert "validate_expected_document" in restore and "bind_expected_to_manifest" in restore
    assert (
        "same_endpoint" in restore and "server_identity" in restore and "contained_path" in restore
    )
    assert "restore_measurements" in restore
    assert "--expect" in restore and "doctor --db" in restore and '"$EREV" migrate' in restore
    assert "EREV_AUDIT_HMAC_MASTER_KEY" in restore and "EREV_ENCRYPTION_KEY" in restore
    # The reset happens only after the identity check and the containment check are in the text.
    assert restore.index("server_identity") < restore.index("DROP SCHEMA IF EXISTS erev CASCADE")
    assert restore.index("contained_path") < restore.index('rm -rf "$RESTORE_DIR"')


def test_backup_script_writes_dump_files_env_digests_and_manifest(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    if sys.platform == "darwin":
        # BSD tar otherwise synthesizes AppleDouble entries (including outside files/).
        # These host attributes are not application file content and must not be archived.
        for path in (repo / ".data/files", repo / ".data/files/t/ATTACHMENT/obj"):
            subprocess.run(
                ["xattr", "-w", "com.erev.backup-test", "host-metadata", str(path)], check=True
            )
    done = _run(BACKUP, repo, scratch)
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert lines[-1] == "OK backup"
    assert SENTINEL not in done.stdout + done.stderr
    for value in KEYS.values():
        assert value not in done.stdout + done.stderr

    backups = sorted((repo / ".data" / "backups").iterdir())
    names = [path.name for path in backups]
    (backup_id,) = {
        re.sub(r"(-files\.tar\.gz|\.dump|\.env|\.digests\.json|\.manifest\.json)$", "", n)
        for n in names
    }
    assert re.fullmatch(r"erev-\d{8}T\d{6}Z", backup_id)
    members = pf.expected_members(backup_id)
    assert names == sorted([*members.values(), f"{backup_id}.manifest.json"])
    # Only file names are printed, each exactly once, in the order they are written.
    printed = [line for line in lines if line.startswith("erev-")]
    assert printed == [
        members["digests"],
        members["dump"],
        members["files"],
        members["env"],
        f"{backup_id}.manifest.json",
    ]
    assert f"backup: database erev -> {backup_id} (quiesced=true)" in lines
    env_copy = repo / ".data" / "backups" / members["env"]
    assert stat.S_IMODE(env_copy.stat().st_mode) == 0o600
    assert env_copy.read_text(encoding="utf-8") == (repo / ".env").read_text(encoding="utf-8")
    # The capture protocol: the .env was hashed at preflight and its copy carries the same bytes.
    manifest_text = (repo / ".data" / "backups" / f"{backup_id}.manifest.json").read_text("utf-8")
    assert (
        json.loads(manifest_text)["env_copy_sha256"]
        == hashlib.sha256(env_copy.read_bytes()).hexdigest()
        == hashlib.sha256((repo / ".env").read_bytes()).hexdigest()
    )

    manifest = pf.load_json_strict(
        (repo / ".data" / "backups" / f"{backup_id}.manifest.json").read_text("utf-8")
    )
    assert pf.validate_manifest(manifest, backup_id=backup_id) == []
    assert manifest["schema"] == pf.MANIFEST_SCHEMA and manifest["quiesced"] is True
    assert manifest["database"] == "erev" and manifest["schema_revision"] == "0001_stub"
    assert (
        manifest["snapshot_started_at"]
        <= manifest["snapshot_finished_at"]
        <= manifest["created_at"]
    )
    assert manifest["digests"]["result"] == "PASS" and manifest["digests"]["tenants"] == 1
    assert set(manifest["files"]) == set(members.values())
    for name, entry in manifest["files"].items():
        path = repo / ".data" / "backups" / name
        assert entry["size_bytes"] == path.stat().st_size
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest["tool_versions"]["pg_dump"].startswith("pg_dump (PostgreSQL)")
    assert SENTINEL not in json.dumps(manifest)

    listed = subprocess.run(
        ["tar", "-tzf", str(repo / ".data" / "backups" / members["files"])],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "files/t/ATTACHMENT/obj" in listed and ".incoming" not in listed
    archive = repo / ".data" / "backups" / members["files"]
    assert pf.inspect_archive(archive, file_root="files") == []
    with tarfile.open(archive, "r:gz") as captured:
        assert {member.name.rstrip("/") for member in captured.getmembers()} == {
            "files",
            "files/t",
            "files/t/ATTACHMENT",
            "files/t/ATTACHMENT/obj",
        }
        stored = captured.extractfile("files/t/ATTACHMENT/obj")
        assert stored is not None and stored.read() == b"ciphertext"

    calls = (scratch / "calls.log").read_text(encoding="utf-8")
    dump_call = next(line for line in calls.splitlines() if "--format=custom" in line)
    assert "postgresql://" not in dump_call and SENTINEL not in calls
    assert "PGDATABASE PGHOST PGPASSWORD PGPORT PGUSER" in calls
    assert (
        f"verify --all-tenants --json --output {repo}/.data/backups/{members['digests']}" in calls
    )

    report = json.loads((repo / ".run" / "reports" / "backup" / "report.json").read_text("utf-8"))
    assert (
        report["target"] == "backup"
        and report["exit_code"] == 0
        and report["command"] == "make backup"
    )
    assert report["counts"]["files"] == 4 and report["counts"]["digests_result"] == "PASS"
    assert report["failures"] == [] and report["backup_id"] == backup_id


def test_backup_script_keeps_the_backup_when_verification_fails(scratch: Path) -> None:
    # Evidence first: a FAIL from erev verify still dumps, tars and copies .env, then fails the
    # target and records the failed result in the manifest (RB-04, RB-08; P6-R2).
    repo = _scratch_repo(scratch)
    done = _run(BACKUP, repo, scratch, STUB_VERIFY_RC="1", STUB_VERIFY_RESULT="FAIL")
    assert done.returncode == 1, done.stdout + done.stderr
    assert _last(done).startswith("FAIL backup: chain, file or key verification found problems")
    names = sorted(path.name for path in (repo / ".data" / "backups").iterdir())
    assert len(names) == 5 and any(name.endswith(".dump") for name in names)
    (manifest,) = (repo / ".data" / "backups").glob("*.manifest.json")
    assert json.loads(manifest.read_text("utf-8"))["digests"]["result"] == "FAIL"
    report = json.loads((repo / ".run" / "reports" / "backup" / "report.json").read_text("utf-8"))
    assert report["exit_code"] == 1 and report["failures"] == [{"stage": "digests", "exit_code": 1}]
    assert SENTINEL not in done.stdout + done.stderr

    # A restore of that backup runs, then fails naming the failed baseline (never a clean pass).
    # The stub restore path is cut at the target checks here, so the failed baseline is visible
    # on the manifest line already.
    restore = _run(RESTORE, repo, scratch, BACKUP="latest", **_restore_urls())
    assert "baseline result at backup: FAIL" in restore.stdout


def test_backup_script_fails_closed(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    (repo / ".env").unlink()
    done = _run(BACKUP, repo, scratch)
    assert done.returncode == 1
    assert (
        _last(done)
        == "FAIL backup: .env not found; nothing to back up the master keys from (RB-05)"
    )
    assert not (repo / ".data" / "backups").exists()

    repo = _scratch_repo(scratch, "no-backup-role")
    (repo / ".env").write_text(_env_text(EREV_BACKUP_URL=None), encoding="utf-8")
    done = _run(BACKUP, repo, scratch)
    assert done.returncode == 1 and _last(done).startswith(
        "FAIL backup: EREV_BACKUP_URL is not set"
    )

    repo = _scratch_repo(scratch, "pg-dump-fails")
    done = _run(BACKUP, repo, scratch, STUB_PG_DUMP_RC="2")
    assert done.returncode == 1 and _last(done) == "FAIL backup: pg_dump failed"
    report = json.loads((repo / ".run" / "reports" / "backup" / "report.json").read_text("utf-8"))
    assert report["failures"] == [{"stage": "pg_dump", "exit_code": 1}]

    # The .env copied for restore must be the .env the application reads.
    repo = _scratch_repo(scratch, "other-dotenv")
    (repo / "review.env").write_text(_env_text(), encoding="utf-8")
    done = _run(BACKUP, repo, scratch, EREV_DOTENV="review.env")
    assert done.returncode == 1 and "EREV_DOTENV pointing elsewhere is not supported" in _last(done)
    assert SENTINEL not in done.stdout + done.stderr


def test_failed_backup_leaves_no_partial_set_and_the_same_second_retries(scratch: Path) -> None:
    # Lane P5's finding (2026-09-22): the id is second-resolution and a run that failed after its
    # digests left them behind, so a retry in the same second was refused as "already exists".
    # Deterministic same-second witness through the test-only clock pin: (a) the first backup fails
    # at pg_dump and removes the partial set it wrote; (b) the second, same second, succeeds; (c) a
    # third, same second, is the genuinely pre-existing id and is refused with nothing removed.
    repo = _scratch_repo(scratch, "same-second")
    backups = repo / ".data" / "backups"
    second = "20260922T001107Z"
    done = _run(BACKUP, repo, scratch, STUB_PG_DUMP_RC="3", EREV_BACKUP_TIMESTAMP=second)
    assert done.returncode == 1 and _last(done) == "FAIL backup: pg_dump failed"
    assert f"backup: removed the partial backup set: erev-{second}.digests.json" in done.stdout
    assert sorted(p.name for p in backups.iterdir()) == [], list(backups.iterdir())
    report = json.loads((repo / ".run" / "reports" / "backup" / "report.json").read_text("utf-8"))
    assert report["failures"] == [{"stage": "pg_dump", "exit_code": 1}]
    assert (
        report["cleaned"] == [f"erev-{second}.digests.json"]
        and report["backup_id"] == f"erev-{second}"
    )
    # (b) same second, clean run
    done = _run(BACKUP, repo, scratch, EREV_BACKUP_TIMESTAMP=second)
    assert done.returncode == 0, done.stdout + done.stderr
    names = sorted(p.name for p in backups.iterdir())
    assert names == sorted(
        f"erev-{second}{suffix}"
        for suffix in (".dump", "-files.tar.gz", ".env", ".digests.json", ".manifest.json")
    )
    report = json.loads((repo / ".run" / "reports" / "backup" / "report.json").read_text("utf-8"))
    assert report["cleaned"] == [] and report["backup_id"] == f"erev-{second}"
    # (c) same second again: the pre-existing set is refused before anything is written or removed
    done = _run(BACKUP, repo, scratch, EREV_BACKUP_TIMESTAMP=second)
    assert done.returncode == 1 and _last(done) == f"FAIL backup: erev-{second}.dump already exists"
    assert sorted(p.name for p in backups.iterdir()) == names
    report = json.loads((repo / ".run" / "reports" / "backup" / "report.json").read_text("utf-8"))
    assert report["cleaned"] == [] and "removed the partial backup set" not in done.stdout
    # a malformed pin is refused before the id is derived
    done = _run(BACKUP, repo, scratch, EREV_BACKUP_TIMESTAMP="2026-09-22")
    assert (
        done.returncode == 1
        and _last(done) == "FAIL backup: EREV_BACKUP_TIMESTAMP is not yyyymmddThhmmssZ"
    )
    assert sorted(p.name for p in backups.iterdir()) == names
    # the pin is a test-only override: the script gates it on the caller's EREV_ENV (test or dev)
    backup = BACKUP.read_text(encoding="utf-8")
    gate = (
        '[[ "$CALLER_EREV_ENV" == "test" || "$CALLER_EREV_ENV" == "dev" ]] \\\n'
        '    || fail "EREV_BACKUP_TIMESTAMP is a test-only override'
    )
    assert gate in backup
    assert 'ARTIFACTS_OWNED="1"' in backup and "cleanup_partial" in backup.split("fail() {", 1)[1]


def test_r1_backup_binds_dump_owner_and_app_to_one_server(scratch: Path) -> None:
    # Same database name on another port, or a server that answers another identity, is refused
    # before erev verify or pg_dump run.
    repo = _scratch_repo(scratch, "other-port")
    (repo / ".env").write_text(
        _env_text(EREV_BACKUP_URL=f"postgresql://erev_backup:{SENTINEL}@127.0.0.1:2/erev"),
        encoding="utf-8",
    )
    done = _run(BACKUP, repo, scratch)
    assert done.returncode == 1, done.stdout + done.stderr
    assert _last(done) == "FAIL backup: preflight refused (see the backup: line above)"
    assert (
        "EREV_DB_OWNER_URL reaches 127.0.0.1:1/erev, not 127.0.0.1:2/erev (EREV_BACKUP_URL)"
        in done.stderr
    )
    assert not (scratch / "calls.log").read_text(encoding="utf-8")  # neither stub was called
    assert SENTINEL not in done.stdout + done.stderr

    repo = _scratch_repo(scratch, "other-identity")
    rows = {name: IDENTITY for name in ("EREV_BACKUP_URL", "EREV_DB_OWNER_URL")}
    rows["EREV_DB_APP_URL"] = ["erev", "16400", "2026-09-19 09:00:00+00", "127.0.0.1", "1"]
    done = _run(
        BACKUP, repo, scratch, EREV_RECOVERY_IDENTITY_STUB=str(_identity_stub(scratch, rows))
    )
    assert done.returncode == 1
    assert "EREV_DB_APP_URL reached another server or database than EREV_BACKUP_URL" in done.stderr
    assert not (scratch / "calls.log").read_text(encoding="utf-8")

    repo = _scratch_repo(scratch, "other-database")
    (repo / ".env").write_text(
        _env_text(EREV_BACKUP_URL=f"postgresql://postgres:{SENTINEL}@127.0.0.1:1/erev_test"),
        encoding="utf-8",
    )
    done = _run(BACKUP, repo, scratch)
    assert (
        done.returncode == 1
        and "reaches 127.0.0.1:1/erev, not 127.0.0.1:1/erev_test" in done.stderr
    )


def test_r4_backup_refuses_effective_keys_the_env_copy_would_not_carry(scratch: Path) -> None:
    for name in KEYS:
        repo = _scratch_repo(scratch, f"override-{name.lower()}")
        done = _run(BACKUP, repo, scratch, **{name: "f" * 64})
        assert done.returncode == 1, (name, done.stdout + done.stderr)
        assert f"effective {name} (environment) differs from the .env copy" in done.stderr
        assert not (repo / ".data" / "backups").exists()
        assert (
            "f" * 64 not in done.stdout + done.stderr
            and KEYS[name] not in done.stdout + done.stderr
        )
    repo = _scratch_repo(scratch, "same-override")
    done = _run(BACKUP, repo, scratch, EREV_ENCRYPTION_KEY=KEYS["EREV_ENCRYPTION_KEY"])
    assert done.returncode == 0, done.stdout + done.stderr
    repo = _scratch_repo(scratch, "missing-key")
    (repo / ".env").write_text(_env_text(EREV_SECURITY_EVENT_HMAC_KEY=None), encoding="utf-8")
    done = _run(BACKUP, repo, scratch)
    assert (
        done.returncode == 1
        and "EREV_SECURITY_EVENT_HMAC_KEY in the .env copy is missing" in done.stderr
    )
    # D-95: under the MANAGED recovery provider (default with gcp) there is no native backup.
    repo = _scratch_repo(scratch, "hosted")
    done = _run(BACKUP, repo, scratch, EREV_KEY_PROVIDER="gcp")
    assert done.returncode == 1 and "recovery provider MANAGED (D-95)" in done.stderr
    assert not (repo / ".data" / "backups").exists()
    repo = _scratch_repo(scratch, "contradiction")
    done = _run(BACKUP, repo, scratch, EREV_RECOVERY_PROVIDER="MANAGED")
    assert done.returncode == 1
    assert "EREV_RECOVERY_PROVIDER=MANAGED contradicts EREV_KEY_PROVIDER=local" in done.stderr
    repo = _scratch_repo(scratch, "explicit-native")
    done = _run(BACKUP, repo, scratch, EREV_RECOVERY_PROVIDER="native")
    assert done.returncode == 0, done.stdout + done.stderr


def test_quiesce_refuses_a_running_stack_unless_allowed(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    (repo / ".run").mkdir()
    (repo / ".run" / "worker.pid").write_text(str(os.getpid()), encoding="utf-8")  # alive: us
    done = _run(BACKUP, repo, scratch)
    assert done.returncode == 1
    assert _last(done).startswith("FAIL backup: worker is running (PID file .run/worker.pid)")
    assert not (repo / ".data" / "backups").exists()
    done = _run(BACKUP, repo, scratch, ALLOW_LIVE="1")
    assert done.returncode == 0, done.stdout + done.stderr
    (manifest,) = (repo / ".data" / "backups").glob("*.manifest.json")
    assert json.loads(manifest.read_text("utf-8"))["quiesced"] is False
    assert "(quiesced=false)" in done.stdout
    (repo / ".run" / "worker.pid").write_text("999999999", encoding="utf-8")  # dead PID: fine
    repo2 = _scratch_repo(scratch, "dead-pid")
    (repo2 / ".run").mkdir()
    (repo2 / ".run" / "api.pid").write_text("999999999", encoding="utf-8")
    assert _run(BACKUP, repo2, scratch).returncode == 0


def _wrapper_shape(scratch: Path, name: str = "wrapped") -> tuple[Path, Path, dict[str, str]]:
    """``(deployment, context, environment)`` in the shape `make backup` and `make restore-verify`
    give the scripts on a clean tree (GATE-BIND-1): the execution context holds the code and a
    copy of ``.env`` and nothing else; the deployment (the worktree) holds the file store, the run
    directory and the backups, and the recipe exports where they are."""
    deployment = _scratch_repo(scratch, f"{name}-deployment")
    context = scratch / f"{name}-context"
    context.mkdir()
    (context / ".env").write_bytes((deployment / ".env").read_bytes())
    environment = {
        "EREV_BACKUP_ROOT": str(context),
        "EREV_RESTORE_ROOT": str(context),
        "EREV_GATE_CONTEXT": str(context),
        "EREV_BACKUP_DATA_ROOT": str(deployment),
        "EREV_RUN_DIR": str(deployment / ".run"),
        "EREV_BACKUP_DIR": str(deployment / ".data" / "backups"),
    }
    return deployment, context, environment


def test_wrapped_backup_reads_the_deployment_not_the_execution_context(scratch: Path) -> None:
    # Rev 1.81 (lane OPS; the first `make backup` on a clean tree, 2026-09-29): in the execution
    # context a relative file root resolved against the clone (`FAIL backup: file root files does
    # not exist` with the default .data/files) and the PID files of step (0) were read from the
    # clone's empty run directory, so a live worker in the worktree's .run/worker.pid was recorded
    # as quiesced=true. The recipe now exports the worktree and its run directory.
    deployment, context, wrapped = _wrapper_shape(scratch)
    done = _run(BACKUP, context, scratch, **wrapped)
    assert done.returncode == 0, done.stdout + done.stderr
    assert _last(done) == "OK backup"
    (manifest,) = (deployment / ".data" / "backups").glob("*.manifest.json")
    backup_id = manifest.name.removesuffix(".manifest.json")
    listed = subprocess.run(
        ["tar", "-tzf", str(deployment / ".data" / "backups" / f"{backup_id}-files.tar.gz")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "files/t/ATTACHMENT/obj" in listed  # the deployment's store, not an empty context
    calls = (scratch / "calls.log").read_text(encoding="utf-8")
    assert f"FILE_ROOT={deployment}/.data/files" in calls  # the verifier reads the same store
    # the report is written where the wrapper reads it; the verifier's log stays in the worktree
    report = json.loads(
        (context / ".run" / "reports" / "backup" / "report.json").read_text("utf-8")
    )
    assert report["exit_code"] == 0 and report["backup_id"] == backup_id
    assert not (deployment / ".run" / "reports").exists()
    assert (deployment / ".run" / "backup-verify.log").is_file()
    assert not (context / ".data").exists()  # nothing of the backup is written into the context

    # a relative EREV_FILE_ROOT of the operator's resolves against the deployment the same way
    deployment2, context2, wrapped2 = _wrapper_shape(scratch, "custom")
    (deployment2 / ".data" / "files").rename(deployment2 / "store")
    done = _run(BACKUP, context2, scratch, EREV_FILE_ROOT="store", **wrapped2)
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"FILE_ROOT={deployment2}/store" in (scratch / "calls.log").read_text("utf-8")

    # step (0): a live process in the deployment's PID file refuses the backup
    deployment3, context3, wrapped3 = _wrapper_shape(scratch, "live")
    (deployment3 / ".run").mkdir()
    (deployment3 / ".run" / "worker.pid").write_text(str(os.getpid()), encoding="utf-8")
    done = _run(BACKUP, context3, scratch, **wrapped3)
    assert done.returncode == 1
    assert _last(done).startswith("FAIL backup: worker is running (PID file .run/worker.pid)")
    assert not (deployment3 / ".data" / "backups").exists()
    failed = json.loads(
        (context3 / ".run" / "reports" / "backup" / "report.json").read_text("utf-8")
    )
    assert failed["exit_code"] == 1 and failed["failures"] == [{"stage": "quiesce", "exit_code": 1}]

    # negative control, the shape before rev 1.81: without the two exports the context has no file
    # store to archive and no PID file to read (the same live worker goes unseen)
    deployment4, context4, wrapped4 = _wrapper_shape(scratch, "before")
    (deployment4 / ".run").mkdir()
    (deployment4 / ".run" / "worker.pid").write_text(str(os.getpid()), encoding="utf-8")
    old_shape = {
        k: v for k, v in wrapped4.items() if k not in ("EREV_BACKUP_DATA_ROOT", "EREV_RUN_DIR")
    }
    done = _run(BACKUP, context4, scratch, **old_shape, EREV_RUN_DIR=str(context4 / ".run"))
    assert done.returncode == 1
    assert _last(done) == "FAIL backup: file root files does not exist"

    # the data root must be an existing directory named by its absolute path
    for bad in ("relative/root", str(scratch / "absent")):
        deployment5, context5, wrapped5 = _wrapper_shape(scratch, f"bad-{len(bad)}")
        done = _run(BACKUP, context5, scratch, **{**wrapped5, "EREV_BACKUP_DATA_ROOT": bad})
        assert done.returncode == 1
        assert _last(done).startswith("FAIL backup: EREV_BACKUP_DATA_ROOT must name an existing")
        assert not (deployment5 / ".data" / "backups").exists()


def test_wrapped_restore_keeps_the_restore_directory_in_the_deployment(scratch: Path) -> None:
    # Rev 1.81 (lane OPS; the first `make restore-verify` on a clean tree): the restore directory
    # .run/restore/<backup id>/ — the extracted file store a cutover points EREV_FILE_ROOT at, and
    # the run's logs — was created inside the execution context and removed with it, and the
    # report named paths of the removed context. The recipe now exports the worktree's run
    # directory; the report alone is written in the context.
    deployment, context, wrapped = _wrapper_shape(scratch)
    assert _run(BACKUP, context, scratch, **wrapped).returncode == 0
    done = _run(RESTORE, context, scratch, BACKUP="latest", RESET="1", **wrapped, **_restore_urls())
    # the stand-in target is unreachable (port 1): the run stops at the first mutation, after the
    # restore root was anchored — in the deployment's run directory
    assert done.returncode == 1
    assert _last(done).startswith("FAIL restore-verify: target erev_rv_clone is not empty")
    assert (deployment / ".run" / "restore").is_dir()
    assert not (context / ".run" / "restore").exists()
    report = json.loads(
        (context / ".run" / "reports" / "restore-verify" / "report.json").read_text("utf-8")
    )
    assert report["target"] == "restore-verify" and report["exit_code"] == 1
    assert not (deployment / ".run" / "reports").exists()
    restore = RESTORE.read_text(encoding="utf-8")
    # the record line and the report name their files relative to the worktree, never by a path
    # inside a context that is removed when the run ends
    assert 'REPORT_NAME="$(basename "$RUN_DIR")/reports/$TARGET/report.json"' in restore
    assert "no cutover RTO in a drill; record $REPORT_NAME" in restore
    assert "record $REPORT_DIR" not in restore
    assert '"verify_document": verify_path.name if verify_path else None' in restore
    for script in (BACKUP.read_text(encoding="utf-8"), restore):
        assert 'REPORT_DIR="$EREV_GATE_CONTEXT/.run/reports/$TARGET"' in script


def test_residual_backup_refuses_external_writers_unless_allowed(scratch: Path) -> None:
    # Two local PID files do not prove no external writers: the preflight counts erev_app and
    # erev_owner sessions on the database (pg_stat_activity; the stub reports them) and refuses
    # unless ALLOW_LIVE=1, which the manifest then records as quiesced=false.
    repo = _scratch_repo(scratch)
    rows = json.loads(_identity_stub(scratch).read_text("utf-8"))
    busy = _identity_stub(scratch, {**rows, "writers": 2})
    done = _run(BACKUP, repo, scratch, EREV_RECOVERY_IDENTITY_STUB=str(busy))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "backup: 2 application session(s) (erev_app or erev_owner) are connected to erev" in (
        done.stderr
    )
    assert _last(done) == "FAIL backup: preflight refused (see the backup: line above)"
    assert not (repo / ".data" / "backups").exists()
    assert "--format=custom" not in (scratch / "calls.log").read_text("utf-8")
    done = _run(BACKUP, repo, scratch, EREV_RECOVERY_IDENTITY_STUB=str(busy), ALLOW_LIVE="1")
    assert done.returncode == 0, done.stdout + done.stderr
    (manifest,) = (repo / ".data" / "backups").glob("*.manifest.json")
    assert json.loads(manifest.read_text("utf-8"))["quiesced"] is False
    assert "(quiesced=false)" in done.stdout
    # The live source connects for the count: the script text queries pg_stat_activity by role.
    backup = BACKUP.read_text(encoding="utf-8")
    assert "pg_stat_activity" in backup and "'erev_app', 'erev_owner'" in backup
    assert "pg_backend_pid()" in backup


def test_residual_backup_refuses_an_env_edited_during_the_run(scratch: Path) -> None:
    # The .env is hashed before anything is written and its copy is hashed after: an edit
    # between the two (the stub pg_dump performs it) fails the backup instead of shipping a copy
    # that differs from the file the digests were computed under.
    repo = _scratch_repo(scratch)
    done = _run(BACKUP, repo, scratch, STUB_MUTATE_DOTENV=str(repo / ".env"))
    assert done.returncode == 1, done.stdout + done.stderr
    assert _last(done).startswith("FAIL backup: .env changed during the backup")
    assert SENTINEL not in done.stdout + done.stderr
    names = sorted(p.name for p in (repo / ".data" / "backups").iterdir())
    assert not any(name.endswith(".manifest.json") for name in names)  # no manifest: not a set
    report = json.loads((repo / ".run" / "reports" / "backup" / "report.json").read_text("utf-8"))
    assert report["exit_code"] == 1 and report["failures"][0]["stage"] == "env"
    # The keys the copy would restore are verified on the copy itself (capture, then check).
    backup = BACKUP.read_text(encoding="utf-8")
    assert backup.index('DOTENV_SHA256="$(') < backup.index('"$EREV" verify --all-tenants')
    assert backup.index('cp "$DOTENV" "$ENV_COPY"') < backup.index("PREFLIGHT_ENV_COPY")


def test_residual_restore_refuses_an_incoherent_baseline_before_any_connection(
    scratch: Path,
) -> None:
    # R2 residual: the backup-time document is typed and complete before the drill touches the
    # target; an omitted head, an untyped key entry and incoherent counts are each refused.
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    backups = repo / ".data" / "backups"
    members = pf.expected_members(backup_id)
    digests_path = backups / members["digests"]
    manifest_path = backups / f"{backup_id}.manifest.json"
    original = pf.load_json_strict(digests_path.read_text("utf-8"))

    def attempt(document: dict[str, object]) -> subprocess.CompletedProcess[str]:
        text = json.dumps(document)
        digests_path.write_text(text, encoding="utf-8")
        manifest = pf.load_json_strict(manifest_path.read_text("utf-8"))
        manifest["files"][members["digests"]] = {
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "size_bytes": len(text.encode()),
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        calls = scratch / "calls.log"
        calls.write_text("", encoding="utf-8")
        done = _run(RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **_restore_urls())
        assert done.returncode == 1, done.stdout + done.stderr
        assert _last(done) == (
            "FAIL restore-verify: the backup is incomplete, altered or unbound (see the "
            "restore-verify: lines above)"
        )
        assert "target database" not in done.stdout
        assert calls.read_text("utf-8") == ""  # no pg_restore, no erev: nothing was connected
        return done

    tenant = dict(original["tenants"][0])  # type: ignore[index]
    headless = {**original, "tenants": [{k: v for k, v in tenant.items() if k != "head"}]}
    done = attempt(headless)
    assert "restore-verify: expected document tenants[0].head is omitted" in done.stderr
    hollow_head = {**original, "tenants": [{**tenant, "head": {"last_chain_seq": 12}}]}
    done = attempt(hollow_head)
    assert "restore-verify: expected document tenants[0].head is malformed" in done.stderr
    untyped = {**original, "key_versions": {**original["key_versions"], "kek": [{}]}}  # type: ignore[dict-item]
    done = attempt(untyped)
    assert "restore-verify: expected document key_versions.kek has an untyped entry" in done.stderr
    miscounted = {**original, "counts": {**original["counts"], "files": {"checked": 2}}}  # type: ignore[dict-item]
    done = attempt(miscounted)
    assert (
        "restore-verify: expected document counts.files.checked does not match the tenants"
        in done.stderr
    )
    # An explicit empty head is a complete baseline (it anchors nothing, and says so).
    empty_head = {
        **original,
        "tenants": [{**tenant, "head": {"last_chain_seq": 0, "last_hmac": None}}],
    }
    text = json.dumps(empty_head)
    digests_path.write_text(text, encoding="utf-8")
    manifest = pf.load_json_strict(manifest_path.read_text("utf-8"))
    manifest["files"][members["digests"]] = {
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "size_bytes": len(text.encode()),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **_restore_urls())
    assert "the backup is incomplete" not in done.stdout


def _rewrite_digests(repo: Path, backup_id: str, document: dict[str, object]) -> None:
    """Replace a backup's digests document and rebind the manifest (hash, size, pin) to it, as a
    backup taken under that evidence would have."""
    backups = repo / ".data" / "backups"
    members = pf.expected_members(backup_id)
    manifest_path = backups / f"{backup_id}.manifest.json"
    manifest = pf.load_json_strict(manifest_path.read_text("utf-8"))
    if document.get("generated_at") in (None, "STUB_GENERATED_AT"):
        document["generated_at"] = manifest["digests"]["generated_at"]  # keep the binding
    text = json.dumps(document)
    (backups / members["digests"]).write_text(text, encoding="utf-8")
    manifest["files"][members["digests"]] = {
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "size_bytes": len(text.encode()),
    }
    security = document.get("security_chain") or {}
    manifest.pop("security_hmac_pin", None)
    manifest.pop("security_required_key_ids", None)
    if security.get("current_key_id") is not None:  # type: ignore[union-attr]
        manifest["security_hmac_pin"] = security.get("current_key_id")  # type: ignore[union-attr]
        manifest["security_required_key_ids"] = security.get("required_key_ids")  # type: ignore[union-attr]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _security_document(head: int, pin: int, *versions: int) -> dict[str, object]:
    document = _digests_document()
    document["result"] = "PASS"
    document["security_chain"] = {
        "last_chain_seq": 3,
        "last_hmac": "a" * 64,
        "head_key_id": f"security-hmac:{head}",
        "current_key_id": f"security-hmac:{pin}",
        "required_key_ids": [f"security-hmac:{v}" for v in versions],
    }
    document["key_versions"] = {
        "kek": [],
        "security_hmac": [{"key_id": f"security-hmac:{v}", "available": True} for v in versions],
        "audit_hmac": [],
    }
    return document


def _clone_binds_pin() -> bool:
    """The clone environment array of the script carries the decided pin explicitly (the erev
    calls on the clone run after the reset, which these DB-less tests never reach; the live drill
    on the throwaway container exercises the binding itself)."""
    text = RESTORE.read_text(encoding="utf-8")
    start = text.index("CLONE_ENV=(")
    clone_env = text[start : text.index("\n)", start)]
    return '"EREV_SECURITY_HMAC_SECRET_VERSION=$CLONE_SECURITY_VERSION"' in clone_env


def test_p2_p6_backup_records_the_pin_and_required_security_keys(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    manifest = pf.load_json_strict(
        (repo / ".data" / "backups" / f"{backup_id}.manifest.json").read_text("utf-8")
    )
    # Key ids only (never material), bound to the digests document.
    assert manifest["security_hmac_pin"] == "security-hmac:1"
    assert manifest["security_required_key_ids"] == ["security-hmac:1"]
    assert manifest["key_versions"]["security_hmac"] == [
        {"key_id": "security-hmac:1", "available": True}
    ]
    assert KEYS["EREV_SECURITY_EVENT_HMAC_KEY"] not in json.dumps(manifest)


def test_p2_p6_restore_binds_the_clone_pin_from_the_backup_never_the_host(scratch: Path) -> None:
    # Integration control 3. The backed-up chain ends under security-hmac:3 and the backup's pin
    # is 3: the clone is bound to 3 explicitly (same-pin positive control), whatever the restore
    # host's own EREV_SECURITY_HMAC_SECRET_VERSION says.
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    _rewrite_digests(repo, backup_id, _security_document(3, 3, 1, 3))
    (scratch / "calls.log").write_text("", encoding="utf-8")
    done = _run(
        RESTORE,
        repo,
        scratch,
        BACKUP=backup_id,
        RESET="1",
        EREV_SECURITY_HMAC_SECRET_VERSION="9",  # the host's pin: never inherited
        **_restore_urls(),
    )
    assert (
        "restore-verify: clone security pin security-hmac:3 (backup pin security-hmac:3, chain "
        "head under security-hmac:3, forward rotation false)"
    ) in done.stdout
    assert done.stdout.index("clone security pin") < done.stdout.index("preflight complete")
    assert _clone_binds_pin()
    report = json.loads(
        (repo / ".run" / "reports" / "restore-verify" / "report.json").read_text("utf-8")
    )
    assert report["restore"]["security_hmac"] == {
        "clone_pin": "security-hmac:3",
        "backup_pin": "security-hmac:3",
        "backup_head_key_id": "security-hmac:3",
        "forward_rotation": False,
        "required_key_ids": ["security-hmac:1", "security-hmac:3"],
        "served": None,  # the verifier never ran: these DB-less drills stop at the reset
    }
    # The backup's own pin ahead of its head (rotation before the backup): the clone gets 5.
    _rewrite_digests(repo, backup_id, _security_document(3, 5, 1, 3, 5))
    (scratch / "calls.log").write_text("", encoding="utf-8")
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **_restore_urls())
    assert "clone security pin security-hmac:5 (backup pin security-hmac:5" in done.stdout
    report = json.loads(
        (repo / ".run" / "reports" / "restore-verify" / "report.json").read_text("utf-8")
    )
    assert report["restore"]["security_hmac"]["clone_pin"] == "security-hmac:5"
    assert report["restore"]["security_hmac"]["forward_rotation"] is False


def test_p2_p6_restore_refuses_a_backwards_pin_before_any_mutation(scratch: Path) -> None:
    # A backup whose pin (1) is behind its chain head (3) is inconsistent evidence; a restore under
    # it would append a forbidden 3→1 transition, so nothing is connected, reset or restored.
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    _rewrite_digests(repo, backup_id, _security_document(3, 1, 1, 3))
    calls = scratch / "calls.log"
    calls.write_text("", encoding="utf-8")
    sequence = scratch / "sequence.log"
    sequence.write_text("", encoding="utf-8")
    done = _run(
        RESTORE,
        repo,
        scratch,
        BACKUP=backup_id,
        RESET="1",
        EREV_RECOVERY_CALLS_LOG=str(sequence),
        **_restore_urls(),
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert (
        "restore-verify: the backup's signing pin security-hmac:1 is behind its chain head "
        "security-hmac:3"
    ) in done.stderr
    assert _last(done) == (
        "FAIL restore-verify: the clone's security-key pin cannot be bound from the backup (see "
        "the restore-verify: line above)"
    )
    assert calls.read_text("utf-8") == ""  # no pg_restore, no erev
    marks = sequence.read_text("utf-8").split()
    assert marks == ["preflight:manifest"]  # refused before the pin mark, long before mutate:*
    assert "target database" not in done.stdout


def test_p2_p6_operator_pin_override_moves_forward_only(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    _rewrite_digests(repo, backup_id, _security_document(3, 3, 1, 3))
    # Forward: explicit, recorded as a rotation, and the clone runs under it.
    (scratch / "calls.log").write_text("", encoding="utf-8")
    done = _run(
        RESTORE,
        repo,
        scratch,
        BACKUP=backup_id,
        RESET="1",
        RESTORE_SECURITY_HMAC_VERSION="5",
        **_restore_urls(),
    )
    assert (
        "clone security pin security-hmac:5 (backup pin security-hmac:3, chain head under "
        "security-hmac:3, forward rotation true)"
    ) in done.stdout
    report = json.loads(
        (repo / ".run" / "reports" / "restore-verify" / "report.json").read_text("utf-8")
    )
    assert report["restore"]["security_hmac"]["forward_rotation"] is True
    assert report["restore"]["security_hmac"]["clone_pin"] == "security-hmac:5"
    # Backwards or garbage: refused before any connection.
    for override, fragment in (
        ("2", "RESTORE_SECURITY_HMAC_VERSION=2 is behind the restored chain head security-hmac:3"),
        ("0", "RESTORE_SECURITY_HMAC_VERSION must be a positive integer"),
        ("latest", "RESTORE_SECURITY_HMAC_VERSION must be a positive integer"),
    ):
        (scratch / "calls.log").write_text("", encoding="utf-8")
        done = _run(
            RESTORE,
            repo,
            scratch,
            BACKUP=backup_id,
            RESET="1",
            RESTORE_SECURITY_HMAC_VERSION=override,
            **_restore_urls(),
        )
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"restore-verify: {fragment}" in done.stderr, (override, done.stderr)
        assert (scratch / "calls.log").read_text("utf-8") == ""


def test_p2_p6_restore_refuses_a_manifest_pin_that_differs_from_the_evidence(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    manifest_path = repo / ".data" / "backups" / f"{backup_id}.manifest.json"
    manifest = pf.load_json_strict(manifest_path.read_text("utf-8"))
    manifest["security_hmac_pin"] = "security-hmac:2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (scratch / "calls.log").write_text("", encoding="utf-8")
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **_restore_urls())
    assert done.returncode == 1
    assert (
        "restore-verify: expected document security pin differs from the manifest's "
        "security_hmac_pin"
    ) in done.stderr
    assert (scratch / "calls.log").read_text("utf-8") == ""
    # And a digests document without the inventory is not a usable baseline.
    hollow = _digests_document()
    hollow["result"] = "PASS"
    hollow["security_chain"] = {"last_chain_seq": 3, "last_hmac": "a" * 64}
    _rewrite_digests(repo, backup_id, hollow)
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **_restore_urls())
    assert done.returncode == 1
    assert (
        "restore-verify: expected document security_chain.required_key_ids is empty" in done.stderr
    )


def test_identity_stub_is_refused_outside_test_and_dev(scratch: Path) -> None:
    # Supervisor ruling: the stub is a test hook; under any other EREV_ENV a set value is a hard
    # error naming the variable, before any connection, for both scripts.
    repo = _scratch_repo(scratch)
    done = _run(BACKUP, repo, scratch, EREV_ENV="production")
    assert done.returncode == 1, done.stdout + done.stderr
    assert (
        "backup: EREV_RECOVERY_IDENTITY_STUB is set under EREV_ENV=production: the identity stub "
        "is honoured under test or dev only"
    ) in done.stderr
    assert not (repo / ".data" / "backups").exists()
    assert "--format=custom" not in (scratch / "calls.log").read_text("utf-8")
    # dev (the default) and test honour it; the backup then proceeds.
    backup_id = _backed_up(scratch, repo)
    for env_name in ("staging", "production", "PRODUCTION"):
        (scratch / "calls.log").write_text("", encoding="utf-8")
        done = _run(
            RESTORE,
            repo,
            scratch,
            BACKUP=backup_id,
            RESET="1",
            EREV_ENV=env_name,
            **_restore_urls(),
        )
        assert done.returncode == 1, done.stdout + done.stderr
        assert (
            f"restore-verify: EREV_RECOVERY_IDENTITY_STUB is set under EREV_ENV={env_name}: the "
            "identity stub is honoured under test or dev only"
        ) in done.stderr
        assert "target database" not in done.stdout
        assert (scratch / "calls.log").read_text("utf-8") == ""
    done = _run(
        RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", EREV_ENV="test", **_restore_urls()
    )
    assert "identity stub is honoured" not in done.stderr


# A DSN still carrying credentials (the redacted form `scheme://***@host` does not match).
CREDENTIAL_DSN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@'\"*]*@")


def _assert_no_credentials(done: subprocess.CompletedProcess[str]) -> None:
    combined = done.stdout + done.stderr
    assert SENTINEL not in combined, combined
    assert CREDENTIAL_DSN.search(combined) is None, combined
    for value in KEYS.values():
        assert value not in combined


def _diagnostics_sequence(scratch: Path, **pin: str) -> tuple[Path, str]:
    """The sequence of ``test_diagnostics_never_echo_a_dsn_or_secret``; ``pin`` (an
    ``EREV_BACKUP_TIMESTAMP``) reaches every backup.sh invocation.

    backup.sh runs three times against ONE repository (one ``.data/backups``): (a) fails at
    ``pg_dump`` (stub exit 3) after its digests were written; (b) ``_backed_up`` succeeds, the only
    successful backup of the sequence; (c) fails at preflight (``EREV_BACKUP_URL`` on another server
    than the owner and app URLs) before an id is derived. No two invocations can succeed into the
    same directory, so the sequence does not depend on the clock once (a) removes its partial set
    (lane P5's finding, 2026-09-22): under one pinned second (a) and (b) share the id and (b) still
    succeeds.
    """
    repo = _scratch_repo(scratch)
    # (a) pg_dump fails and echoes its connection string: the script redacts it.
    done = _run(BACKUP, repo, scratch, STUB_PG_DUMP_RC="3", **pin)
    assert done.returncode == 1, done.stdout + done.stderr  # FAIL backup: pg_dump failed
    assert "connection to postgresql://***@127.0.0.1:1/erev failed: PGPASSWORD=***" in done.stderr
    _assert_no_credentials(done)
    # (b) a completed backup, then a restore whose reset step cannot reach the target (port 1):
    #     the failure names the error class and a redacted first line, never a traceback or DSN.
    backup_id = _backed_up(scratch, repo, **pin)
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **_restore_urls())
    assert done.returncode == 1, done.stdout + done.stderr
    assert "restore-verify: target step failed with " in done.stderr
    assert "Traceback" not in done.stderr
    _assert_no_credentials(done)
    # (c) refusals that name variables: binding, identity, stub gate.
    for extra in (
        {
            "EREV_RESTORE_ADMIN_URL": f"postgresql://erev_restore_admin:{SENTINEL}@127.0.0.1:2/erev_rv_clone"
        },
        {"EREV_ENV": "production"},
        {"EREV_RECOVERY_IDENTITY_STUB": str(_identity_stub(scratch, {}))},
    ):
        done = _run(
            RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **{**_restore_urls(), **extra}
        )
        assert done.returncode == 1
        _assert_no_credentials(done)
    done = _run(
        BACKUP,
        repo,
        scratch,
        EREV_BACKUP_URL=f"postgresql://erev_backup:{SENTINEL}@127.0.0.2:1/erev",
        **pin,
    )
    assert done.returncode == 1
    _assert_no_credentials(done)
    # (d) the redaction helper is what both scripts use for tool output.
    for script in (BACKUP, RESTORE):
        assert "redact_diagnostics" in script.read_text(encoding="utf-8"), script.name
    return repo, backup_id


def test_diagnostics_never_echo_a_dsn_or_secret(scratch: Path) -> None:
    # Synthetic-credential regression (common-terms amendment): every URL carries the sentinel
    # password; across the failure paths below no DSN with credentials, no sentinel and no master
    # key reaches stdout or stderr.
    _diagnostics_sequence(scratch)


def test_diagnostics_sequence_under_one_pinned_second(scratch: Path) -> None:
    # Lane P5's finding (2026-09-22), the forced same-second worst case: the whole sequence above
    # runs under one pinned EREV_BACKUP_TIMESTAMP, so (a), (b) and (c) all derive the same id. (b)
    # succeeds because (a) removed its partial set; (c) never reaches the id; the directory ends
    # with exactly the five artifacts of the one successful backup.
    second = "20260922T001107Z"
    repo, backup_id = _diagnostics_sequence(scratch, EREV_BACKUP_TIMESTAMP=second)
    assert backup_id == f"erev-{second}"
    names = sorted(p.name for p in (repo / ".data" / "backups").iterdir())
    assert names == sorted(
        f"erev-{second}{suffix}"
        for suffix in (".dump", "-files.tar.gz", ".env", ".digests.json", ".manifest.json")
    )


def test_residual_restore_refuses_corrupt_manifest_instants(scratch: Path) -> None:
    # R7 residual: a manifest whose snapshot instant is corrupt is refused before any mutation;
    # the report carries no substituted restore point.
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    manifest_path = repo / ".data" / "backups" / f"{backup_id}.manifest.json"
    original = pf.load_json_strict(manifest_path.read_text("utf-8"))
    for field, value in (
        ("snapshot_started_at", "2026-09-19T12:00:00"),
        ("snapshot_finished_at", None),
        ("created_at", "garbage"),
        ("snapshot_started_at", original["created_at"]),  # after snapshot_finished_at
    ):
        manifest_path.write_text(json.dumps({**original, field: value}), encoding="utf-8")
        calls = scratch / "calls.log"
        calls.write_text("", encoding="utf-8")
        done = _run(RESTORE, repo, scratch, BACKUP=backup_id, RESET="1", **_restore_urls())
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"restore-verify: manifest {field}" in done.stderr, (field, value, done.stderr)
        assert _last(done) == (
            "FAIL restore-verify: the backup is incomplete, altered or unbound (see the "
            "restore-verify: lines above)"
        )
        assert calls.read_text("utf-8") == ""
        report = json.loads(
            (repo / ".run" / "reports" / "restore-verify" / "report.json").read_text("utf-8")
        )
        assert report["restore"]["restore_point"] is None and "error" in report["restore"]


def test_r2_restore_refuses_incomplete_or_unbound_manifests(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    backups = repo / ".data" / "backups"
    manifest_path = backups / f"{backup_id}.manifest.json"
    original = pf.load_json_strict(manifest_path.read_text("utf-8"))
    members = pf.expected_members(backup_id)

    def attempt(manifest: dict[str, object]) -> subprocess.CompletedProcess[str]:
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        done = _run(RESTORE, repo, scratch, BACKUP=backup_id, **_restore_urls())
        assert done.returncode == 1, done.stdout + done.stderr
        assert _last(done) == (
            "FAIL restore-verify: the backup is incomplete, altered or unbound (see the "
            "restore-verify: lines above)"
        )
        assert "target database" not in done.stdout  # nothing was connected to or reset
        return done

    # The reviewer's three accepted manifests: empty inventory, no dump, no digests.
    done = attempt({**original, "files": {}})
    for name in members.values():
        assert f"restore-verify: manifest omits {name}" in done.stderr
    files = dict(original["files"])  # type: ignore[arg-type]
    done = attempt({**original, "files": {k: v for k, v in files.items() if k != members["dump"]}})
    assert f"restore-verify: manifest omits {members['dump']}" in done.stderr
    done = attempt(
        {**original, "files": {k: v for k, v in files.items() if k != members["digests"]}}
    )
    assert f"restore-verify: manifest omits {members['digests']}" in done.stderr
    # Extra, traversing, other id, other schema, malformed entry, duplicate key.
    done = attempt({**original, "files": {**files, "../x": {"sha256": "0" * 64, "size_bytes": 1}}})
    assert "manifest lists an unexpected member '../x'" in done.stderr
    done = attempt({**original, "backup_id": "erev-20000101T000000Z"})
    assert f"manifest backup_id is not {backup_id}" in done.stderr
    done = attempt({**original, "schema": "erev-backup-manifest/1"})
    assert f"manifest schema is not {pf.MANIFEST_SCHEMA}" in done.stderr
    bad_entry = {**files, members["env"]: {"sha256": "zz", "size_bytes": 1}}
    done = attempt({**original, "files": bad_entry})
    assert f"manifest entry {members['env']} has no lowercase 64-hex sha256" in done.stderr
    manifest_path.write_text(
        json.dumps(original).replace('"files": {', '"files": {"dup": 1, "dup": 2, ', 1),
        encoding="utf-8",
    )
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, **_restore_urls())
    assert done.returncode == 1 and "duplicate JSON key" in done.stderr

    # A listed member tampered, then a digests document emptied out.
    manifest_path.write_text(json.dumps(original), encoding="utf-8")
    dump = backups / members["dump"]
    dump.write_bytes(b"PGDMP-tampered")
    done = attempt(original)
    assert (
        f"restore-verify: {members['dump']}: hash or size differs from the manifest" in done.stderr
    )
    done = _run(BACKUP, _scratch_repo(scratch, "fresh"), scratch)
    assert done.returncode == 0
    repo2 = scratch / "fresh"
    (manifest2,) = (repo2 / ".data" / "backups").glob("*.manifest.json")
    id2 = manifest2.name.removesuffix(".manifest.json")
    digests2 = repo2 / ".data" / "backups" / f"{id2}.digests.json"
    hollow = {**_digests_document(), "result": "PASS", "tenants": [], "counts": {"tenants": 0}}
    digests2.write_text(json.dumps(hollow), encoding="utf-8")
    m2 = pf.load_json_strict(manifest2.read_text("utf-8"))
    m2["files"][f"{id2}.digests.json"] = {
        "sha256": hashlib.sha256(digests2.read_bytes()).hexdigest(),
        "size_bytes": digests2.stat().st_size,
    }
    manifest2.write_text(json.dumps(m2), encoding="utf-8")
    done = _run(RESTORE, repo2, scratch, BACKUP=id2, **_restore_urls())
    assert done.returncode == 1 and "expected document records no tenants" in done.stderr


def test_r3_restore_refuses_bad_ids_and_unsafe_archives(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    for bad in ("../..", "/etc", "erev-20260919T120000Z/../x", "x; rm -rf /"):
        done = _run(RESTORE, repo, scratch, BACKUP=bad, **_restore_urls())
        assert done.returncode == 1, bad
        assert _last(done) == (
            "FAIL restore-verify: BACKUP is not a backup id (erev-<yyyymmdd>T<hhmmss>Z or latest)"
        )
        assert "backup ../.." not in done.stdout
    assert not (repo / ".run" / "restore").exists()

    # An archive member escaping the file root, or a link, is refused before any connection.
    members = pf.expected_members(backup_id)
    archive = repo / ".data" / "backups" / members["files"]
    manifest_path = repo / ".data" / "backups" / f"{backup_id}.manifest.json"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("files/t/obj")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
        link = tarfile.TarInfo("files/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    manifest = pf.load_json_strict(manifest_path.read_text("utf-8"))
    manifest["files"][members["files"]] = {
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "size_bytes": archive.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, **_restore_urls())
    assert done.returncode == 1
    assert "archive member 'files/escape' is a symlink, not a file or directory" in done.stderr
    assert "target database" not in done.stdout


def test_r1_restore_binds_owner_app_and_admin_to_one_target(scratch: Path) -> None:
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    calls = scratch / "calls.log"

    def refused(fragment: str, **overrides: str) -> None:
        calls.write_text("", encoding="utf-8")
        done = _run(RESTORE, repo, scratch, BACKUP=backup_id, **_restore_urls(**overrides))
        assert done.returncode == 1, done.stdout + done.stderr
        assert (
            _last(done)
            == "FAIL restore-verify: target refused (see the restore-verify: line above)"
        )
        assert fragment in done.stderr, done.stderr
        assert "pg_restore" not in calls.read_text(
            encoding="utf-8"
        ).lower() or "--dbname" not in calls.read_text(encoding="utf-8")
        assert SENTINEL not in done.stdout + done.stderr
        assert not (repo / ".run" / "restore").exists()

    # The reviewer's three accepted targets: admin on another host, app on another host, admin on
    # another port, each with the same database name.
    refused(
        "EREV_RESTORE_ADMIN_URL reaches 127.0.0.2:1/erev_rv_clone, not 127.0.0.1:1/erev_rv_clone",
        EREV_RESTORE_ADMIN_URL=f"postgresql://erev_restore_admin:{SENTINEL}@127.0.0.2:1/erev_rv_clone",
    )
    refused(
        "EREV_RESTORE_APP_URL reaches 127.0.0.2:1/erev_rv_clone, not 127.0.0.1:1/erev_rv_clone",
        EREV_RESTORE_APP_URL=f"postgresql://erev_app:{SENTINEL}@127.0.0.2:1/erev_rv_clone",
    )
    refused(
        "EREV_RESTORE_ADMIN_URL reaches 127.0.0.1:2/erev_rv_clone, not 127.0.0.1:1/erev_rv_clone",
        EREV_RESTORE_ADMIN_URL=f"postgresql://erev_restore_admin:{SENTINEL}@127.0.0.1:2/erev_rv_clone",
    )
    # The controls the reviewer saw refused stay refused, now on the endpoint.
    refused(
        "EREV_RESTORE_ADMIN_URL reaches 127.0.0.1:1/erev_rv_other",
        EREV_RESTORE_ADMIN_URL=f"postgresql://x:{SENTINEL}@127.0.0.1:1/erev_rv_other",
    )
    refused(
        "query parameter dbname",
        EREV_RESTORE_ADMIN_URL=f"postgresql://x:{SENTINEL}@127.0.0.1:1/erev_rv_clone?dbname=erev",
    )
    calls.write_text("", encoding="utf-8")
    done = _run(RESTORE, repo, scratch, BACKUP=backup_id, **_restore_urls(database="erev"))
    assert done.returncode == 1
    assert (
        "restore target must be an erev_rv_* database, not erev; production is never restored "
        "in place (05 OPR-11)"
    ) in done.stderr

    # Same URLs, but the servers reached answer different identities.
    rows = {n: RESTORE_IDENTITY for n in ("EREV_RESTORE_OWNER_URL", "EREV_RESTORE_APP_URL")}
    rows["EREV_RESTORE_ADMIN_URL"] = [
        "erev_rv_clone",
        "16401",
        "2026-09-19 08:00:00+00",
        "10.0.0.9",
        "5432",
    ]
    done = _run(
        RESTORE,
        repo,
        scratch,
        BACKUP=backup_id,
        EREV_RECOVERY_IDENTITY_STUB=str(_identity_stub(scratch, rows)),
        **_restore_urls(),
    )
    assert done.returncode == 1
    assert (
        "EREV_RESTORE_ADMIN_URL reached another server or database than EREV_RESTORE_OWNER_URL"
        in done.stderr
    )

    # Missing URLs are named before anything else.
    done = _run(RESTORE, repo, scratch, BACKUP="latest")
    assert _last(done) == (
        "FAIL restore-verify: EREV_RESTORE_OWNER_URL and EREV_RESTORE_APP_URL must name the "
        "isolated erev_rv_* target"
    )
    partial = {k: v for k, v in _restore_urls().items() if k != "EREV_RESTORE_ADMIN_URL"}
    done = _run(RESTORE, repo, scratch, BACKUP="latest", **partial)
    assert _last(done) == (
        "FAIL restore-verify: EREV_RESTORE_ADMIN_URL must name the target as the restore-target "
        "admin (BYPASSRLS; RB-11)"
    )
    empty = _scratch_repo(scratch, "empty")
    done = _run(RESTORE, empty, scratch, **_restore_urls())
    assert _last(done) == "FAIL restore-verify: no backups directory backups"
    # D-95: the NATIVE drill refuses under the MANAGED provider, after the manifest step and
    # before any target connection.
    done = _run(
        RESTORE, repo, scratch, BACKUP=backup_id, EREV_KEY_PROVIDER="gcp", **_restore_urls()
    )
    assert done.returncode == 1
    assert _last(done) == (
        "FAIL restore-verify: recovery provider refused (see the restore-verify: line above)"
    )
    assert "recovery provider MANAGED (D-95)" in done.stderr
    assert "target database" not in done.stdout


def test_residual_preflight_precedes_every_mutation(scratch: Path) -> None:
    # Review residual (2026-09-19): the RESET drop ran before the containment check on d96c728.
    # The call sequence proves the order now: every preflight step, then "preflight:complete",
    # then the first mutation ("mutate:reset"), which here fails to connect (port 1) and stops
    # the run before pg_restore or any extraction.
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    calls = scratch / "sequence.log"
    calls.write_text("", encoding="utf-8")
    done = _run(
        RESTORE,
        repo,
        scratch,
        BACKUP=backup_id,
        RESET="1",
        EREV_RECOVERY_CALLS_LOG=str(calls),
        **_restore_urls(),
    )
    sequence = calls.read_text(encoding="utf-8").split()
    assert sequence == [
        "preflight:manifest",
        "preflight:pin",
        "preflight:provider",
        "preflight:identity",
        "preflight:containment",
        "preflight:complete",
        "mutate:reset",
    ]
    assert done.returncode == 1
    assert _last(done).startswith("FAIL restore-verify: target erev_rv_clone is not empty")
    assert "--dbname" not in (scratch / "calls.log").read_text(encoding="utf-8")  # no pg_restore
    assert (repo / ".run" / "restore").is_dir()  # created by the script, as a real directory
    assert not (repo / ".run" / "restore" / backup_id).exists()  # never written before the restore

    # The backup script: preflight complete before the digests and the dump are written.
    calls.write_text("", encoding="utf-8")
    repo2 = _scratch_repo(scratch, "order")
    assert _run(BACKUP, repo2, scratch, EREV_RECOVERY_CALLS_LOG=str(calls)).returncode == 0
    assert calls.read_text(encoding="utf-8").split() == [
        "preflight:complete",
        "write:digests",
        "write:pg_dump",
    ]


def test_residual_symlinked_restore_parent_is_refused_before_any_mutation(scratch: Path) -> None:
    # Review residual (2026-09-19): .run/restore is a link to a directory elsewhere; on d96c728
    # the descendant resolved "inside" the resolved link target and the reset had already run.
    repo = _scratch_repo(scratch)
    backup_id = _backed_up(scratch, repo)
    elsewhere = scratch / "elsewhere"
    elsewhere.mkdir()
    (repo / ".run").mkdir(exist_ok=True)
    (repo / ".run" / "restore").symlink_to(elsewhere)
    calls = scratch / "sequence.log"
    calls.write_text("", encoding="utf-8")
    done = _run(
        RESTORE,
        repo,
        scratch,
        BACKUP=backup_id,
        RESET="1",
        EREV_RECOVERY_CALLS_LOG=str(calls),
        **_restore_urls(),
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert _last(done) == (
        "FAIL restore-verify: restore directory refused (see the restore-verify: line above)"
    )
    assert "restore root" in done.stderr and "is a symbolic link" in done.stderr
    sequence = calls.read_text(encoding="utf-8").split()
    assert "mutate:reset" not in sequence and "preflight:complete" not in sequence
    assert sequence[-1] == "preflight:identity"
    assert not any(elsewhere.iterdir())  # nothing was written through the link
    assert (repo / ".run" / "restore").is_symlink()  # and the link itself was left alone
