"""scripts/check_env.py contract (docs/dev-guide.md DG-ENV-13, DG-ENV-16; BUILD_SPEC FND-1)."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check_env.py"
SECRET_NAMES = (
    "EREV_ENCRYPTION_KEY",
    "EREV_AUDIT_HMAC_MASTER_KEY",
    "EREV_SECURITY_EVENT_HMAC_KEY",
    "EREV_DEMO_TOTP_SECRET",
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_env", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EREV_", "ANTHROPIC_"))}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


@pytest.fixture
def scratch_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def test_dg_env_16_ensure_keys_appends_without_printing(scratch_dir: Path) -> None:
    env_file = scratch_dir / ".env"
    original = (
        b"EREV_ENV=dev\nEREV_DB_APP_URL=postgresql://erev_app:not-a-secret@127.0.0.1:5432/erev\n"
    )
    env_file.write_bytes(original)

    first = _run("--ensure-keys", "--env-file", str(env_file))
    assert first.returncode == 0, first.stdout + first.stderr
    content = env_file.read_bytes()
    assert content.startswith(original)
    appended = content[len(original) :].decode().splitlines()
    assert len(appended) == 4
    added = dict(line.split("=", 1) for line in appended)
    assert list(added) == list(SECRET_NAMES)
    for name in SECRET_NAMES[:3]:
        assert re.fullmatch(r"[0-9a-f]{64}", added[name])
    assert re.fullmatch(r"[A-Z2-7]{32}", added["EREV_DEMO_TOTP_SECRET"])
    for name in SECRET_NAMES:
        assert name in first.stdout
    for value in added.values():
        assert value not in first.stdout
        assert value not in first.stderr
    assert "EREV_DEMO_PASSWORD" not in content.decode()

    second = _run("--ensure-keys", "--env-file", str(env_file))
    assert second.returncode == 0
    assert env_file.read_bytes() == content


def test_dg_env_13_database_allow_list(scratch_dir: Path) -> None:
    module = _load_module()
    for database in ("erev", "erev_test", "erev_e2e", "erev_rv_a1"):
        url = f"postgresql://erev_app:pw-123456@127.0.0.1:5432/{database}"
        assert module.check_database_allowed(url) is None
    for database in ("postgres", "erev_other"):
        url = f"postgresql://erev_app:pw-123456@127.0.0.1:5432/{database}"
        error = module.check_database_allowed(url)
        assert error is not None
        assert database in error
        assert "erev_app" not in error
        assert "pw-123456" not in error

    env_file = scratch_dir / ".env"
    env_file.write_text(
        "EREV_DB_OWNER_URL=postgresql://erev_owner:pw-123456@127.0.0.1:5432/postgres\n"
        "EREV_DB_APP_URL=postgresql://erev_app:pw-123456@127.0.0.1:5432/postgres\n"
        "EREV_TEST_DB_OWNER_URL=postgresql://erev_owner:pw-123456@127.0.0.1:5432/erev_other\n"
        "EREV_TEST_DB_APP_URL=postgresql://erev_app:pw-123456@127.0.0.1:5432/erev_other\n"
        "EREV_E2E_DB_OWNER_URL=postgresql://erev_owner:pw-123456@127.0.0.1:5432/erev_e2e\n"
        "EREV_E2E_DB_APP_URL=postgresql://erev_app:pw-123456@127.0.0.1:5432/erev_e2e\n"
    )
    completed = _run("--db", "--env-file", str(env_file))
    output = completed.stdout + completed.stderr
    assert completed.returncode == 1
    assert "postgres" in output
    assert "erev_other" in output
    assert "erev_app" not in output
    assert "erev_owner" not in output
    assert "pw-123456" not in output


def test_names_prints_names_only(scratch_dir: Path) -> None:
    module = _load_module()
    env_file = scratch_dir / ".env"
    lines = [
        f"{name}=SENTINEL_VALUE_{index}"
        for index, name in enumerate(module.REQUIRED_NAMES)
        if name != "EREV_TEST_DB_APP_URL"
    ]
    env_file.write_text("\n".join(lines) + "\n")

    completed = _run("--names", "--env-file", str(env_file))
    assert completed.returncode == 1
    assert "EREV_TEST_DB_APP_URL" in completed.stdout
    assert "SENTINEL_VALUE" not in completed.stdout + completed.stderr


def test_rb_04_recovery_urls_presence_and_shape(scratch_dir: Path) -> None:
    # Runbook RB-04, RB-11 (DG-MK-backup rev 1.3): --db reports an absent EREV_BACKUP_URL or
    # EREV_RESTORE_ADMIN_URL by name and refuses a malformed one before any connection; values are
    # never printed and neither URL is ever connected to (a BYPASSRLS connection from the loop would
    # breach DG-FORBID-03).
    module = _load_module()
    base = {
        "EREV_DB_OWNER_URL": "postgresql://erev_owner:pw-123456@127.0.0.1:1/erev",
        "EREV_DB_APP_URL": "postgresql://erev_app:pw-123456@127.0.0.1:1/erev",
    }
    notes, errors = module.check_recovery_urls(base)
    assert notes == [
        "recovery URL absent: EREV_BACKUP_URL",
        "recovery URL absent: EREV_RESTORE_ADMIN_URL",
    ]
    assert errors == []

    good = {
        **base,
        "EREV_BACKUP_URL": "postgresql://erev_backup:pw-123456@127.0.0.1:1/erev",
        "EREV_RESTORE_ADMIN_URL": "postgresql+psycopg://postgres:pw-123456@127.0.0.1:1/erev_rv_x",
    }
    assert module.check_recovery_urls(good) == ([], [])

    wrong_database = {
        **good,
        "EREV_BACKUP_URL": "postgresql://erev_backup:pw@127.0.0.1:1/erev_test",
    }
    assert module.check_recovery_urls(wrong_database)[1] == [
        "EREV_BACKUP_URL must name the database of EREV_DB_OWNER_URL (erev), not erev_test"
    ]
    in_place_message = (
        "EREV_RESTORE_ADMIN_URL must name an isolated erev_rv_* restore target, not erev "
        "(05 OPR-11)"
    )
    in_place = {**good, "EREV_RESTORE_ADMIN_URL": "postgresql://postgres:pw@127.0.0.1:1/erev"}
    assert module.check_recovery_urls(in_place)[1] == [in_place_message]
    not_allowed = {
        **good,
        "EREV_RESTORE_ADMIN_URL": "postgresql://postgres:pw@127.0.0.1:1/postgres",
    }
    assert module.check_recovery_urls(not_allowed)[1] == [
        "database not allowed: postgres (EREV_RESTORE_ADMIN_URL)"
    ]
    redirecting = {**good, "EREV_BACKUP_URL": "postgresql://b:pw@127.0.0.1:1/erev?dbname=postgres"}
    assert module.check_recovery_urls(redirecting)[1] == [
        "database URL sets query parameter dbname (EREV_BACKUP_URL)"
    ]
    not_a_url = {**good, "EREV_BACKUP_URL": "mysql://b:pw@127.0.0.1:1/erev"}
    assert module.check_recovery_urls(not_a_url)[1] == ["not a postgresql:// URL (EREV_BACKUP_URL)"]

    # Through --db: shape errors stop the run before any connection is attempted.
    env_file = scratch_dir / ".env"
    urls = "\n".join(
        f"{name}=postgresql://{role}:pw-123456@127.0.0.1:1/{database}"
        for name, role, database in (
            ("EREV_DB_OWNER_URL", "erev_owner", "erev"),
            ("EREV_DB_APP_URL", "erev_app", "erev"),
            ("EREV_TEST_DB_OWNER_URL", "erev_owner", "erev_test"),
            ("EREV_TEST_DB_APP_URL", "erev_app", "erev_test"),
            ("EREV_E2E_DB_OWNER_URL", "erev_owner", "erev_e2e"),
            ("EREV_E2E_DB_APP_URL", "erev_app", "erev_e2e"),
        )
    )
    env_file.write_text(
        urls + "\nEREV_RESTORE_ADMIN_URL=postgresql://postgres:pw-123456@127.0.0.1:1/erev\n"
    )
    completed = _run("--db", "--env-file", str(env_file))
    output = completed.stdout + completed.stderr
    assert completed.returncode == 1
    assert in_place_message in output
    assert "cannot connect" not in output, "shape errors stop the run before any connection"
    assert "pw-123456" not in output and "postgres:" not in output

    # Absent recovery URLs are reported by name and never fail the run on their own: the run goes
    # on to the connection checks (which fail here on port 1, as intended for this scratch file).
    env_file.write_text(urls + "\n")
    completed = _run("--db", "--env-file", str(env_file))
    output = completed.stdout + completed.stderr
    assert "recovery URL absent: EREV_BACKUP_URL" in output
    assert "recovery URL absent: EREV_RESTORE_ADMIN_URL" in output
    assert "cannot connect to erev (EREV_DB_APP_URL)" in output
    assert "pw-123456" not in output


def test_rb_04_recovery_urls_required_in_production(scratch_dir: Path) -> None:
    # Supervisor ruling (lane P6): under EREV_ENV=production both recovery URLs are required and
    # their absence exits 1 with a named line; every other environment keeps "absent = note".
    module = _load_module()
    base = {
        "EREV_DB_OWNER_URL": "postgresql://erev_owner:pw-123456@127.0.0.1:1/erev",
        "EREV_DB_APP_URL": "postgresql://erev_app:pw-123456@127.0.0.1:1/erev",
    }
    notes, errors = module.check_recovery_urls({**base, "EREV_ENV": "production"})
    assert notes == []
    assert errors == [
        "recovery URL required: EREV_BACKUP_URL (EREV_ENV=production, recovery provider NATIVE; "
        "RB-04)",
        "recovery URL required: EREV_RESTORE_ADMIN_URL (EREV_ENV=production, recovery provider "
        "NATIVE; RB-04)",
    ]
    # D-95 MANAGED (default with EREV_KEY_PROVIDER=gcp): the native path is unestablished on Cloud
    # SQL, so a set URL is refused and the managed-drill inputs are noted as unknown.
    hosted = {**base, "EREV_ENV": "production", "EREV_KEY_PROVIDER": "gcp"}
    notes, errors = module.check_recovery_urls(hosted)
    assert errors == [] and notes == [module.MANAGED_DRILL_NOTE]
    notes, errors = module.check_recovery_urls(
        {**hosted, "EREV_BACKUP_URL": "postgresql://erev_backup:pw-123456@10.0.0.9:5432/erev"}
    )
    assert notes == [module.MANAGED_DRILL_NOTE] and len(errors) == 1
    assert errors[0].startswith(
        "recovery URL not applicable: EREV_BACKUP_URL is set under recovery provider MANAGED"
    )
    assert "pw-123456" not in errors[0]
    # An explicit provider that agrees passes; one that contradicts the key provider is an error.
    assert module.check_recovery_urls({**hosted, "EREV_RECOVERY_PROVIDER": "managed"}) == (
        [module.MANAGED_DRILL_NOTE],
        [],
    )
    assert module.check_recovery_urls({**hosted, "EREV_RECOVERY_PROVIDER": "NATIVE"})[1] == [
        "EREV_RECOVERY_PROVIDER=NATIVE contradicts EREV_KEY_PROVIDER=gcp (D-95: local → NATIVE, "
        "gcp → MANAGED)"
    ]
    assert module.check_recovery_urls({**base, "EREV_RECOVERY_PROVIDER": "MANAGED"})[1] == [
        "EREV_RECOVERY_PROVIDER=MANAGED contradicts EREV_KEY_PROVIDER=local (D-95: local → NATIVE, "
        "gcp → MANAGED)"
    ]
    assert module.check_recovery_urls({**base, "EREV_RECOVERY_PROVIDER": "cloud"})[1] == [
        "EREV_RECOVERY_PROVIDER must be NATIVE or MANAGED (D-95)"
    ]
    for environment in ("dev", "test", "e2e", ""):
        notes, errors = module.check_recovery_urls({**base, "EREV_ENV": environment})
        assert errors == [] and len(notes) == 2, environment
    complete = {
        **base,
        "EREV_ENV": "production",
        "EREV_BACKUP_URL": "postgresql://erev_backup:pw-123456@127.0.0.1:1/erev",
        "EREV_RESTORE_ADMIN_URL": "postgresql://postgres:pw-123456@127.0.0.1:1/erev_rv_clone",
    }
    assert module.check_recovery_urls(complete) == ([], [])

    urls = "\n".join(
        f"{name}=postgresql://{role}:pw-123456@127.0.0.1:1/{database}"
        for name, role, database in (
            ("EREV_DB_OWNER_URL", "erev_owner", "erev"),
            ("EREV_DB_APP_URL", "erev_app", "erev"),
            ("EREV_TEST_DB_OWNER_URL", "erev_owner", "erev_test"),
            ("EREV_TEST_DB_APP_URL", "erev_app", "erev_test"),
            ("EREV_E2E_DB_OWNER_URL", "erev_owner", "erev_e2e"),
            ("EREV_E2E_DB_APP_URL", "erev_app", "erev_e2e"),
        )
    )
    env_file = scratch_dir / ".env"
    env_file.write_text("EREV_ENV=production\n" + urls + "\n")
    completed = _run("--db", "--env-file", str(env_file))
    output = completed.stdout + completed.stderr
    assert completed.returncode == 1
    assert "recovery URL required: EREV_BACKUP_URL (EREV_ENV=production, recovery" in output
    assert "recovery URL required: EREV_RESTORE_ADMIN_URL (EREV_ENV=production, recovery" in output
    assert "cannot connect" not in output, "the missing URLs stop the run before any connection"
    assert "pw-123456" not in output

    # The same file under dev: two notes, then the connection checks run (and fail on port 1 here).
    env_file.write_text("EREV_ENV=dev\n" + urls + "\n")
    completed = _run("--db", "--env-file", str(env_file))
    output = completed.stdout + completed.stderr
    assert "recovery URL absent: EREV_BACKUP_URL" in output
    assert "recovery URL required" not in output
    assert "cannot connect to erev (EREV_DB_APP_URL)" in output
