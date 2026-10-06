#!/usr/bin/env python3
"""Environment checks for eRev Cloud (docs/dev-guide.md §2.4 and DG-MK-setup).

Modes, run in this order when combined:
  --tools        verify the toolchain (DG-ENV-01 to DG-ENV-05; report DG-ENV-06, DG-ENV-07)
  --ensure-keys  append missing master keys and the demo TOTP secret to .env (DG-ENV-16)
  --names        fail when a required variable name is absent
  --db           database allow-list, role guard and CREATE privilege (DG-ENV-12, 13, 15); the
                 recovery provider of D-95 (EREV_RECOVERY_PROVIDER, default from EREV_KEY_PROVIDER)
                 and the recovery URLs EREV_BACKUP_URL and EREV_RESTORE_ADMIN_URL (RB-04): NATIVE
                 requires both under EREV_ENV=production and reports an absent one elsewhere;
                 MANAGED refuses a set value

The script never prints a value read from .env or the environment. Output names variables,
databases and tool versions only (DG-FORBID-01).
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"

DB_URL_NAMES = (
    ("dev", "EREV_DB_OWNER_URL", "EREV_DB_APP_URL"),
    ("test", "EREV_TEST_DB_OWNER_URL", "EREV_TEST_DB_APP_URL"),
    ("e2e", "EREV_E2E_DB_OWNER_URL", "EREV_E2E_DB_APP_URL"),
)
KEY_NAMES = ("EREV_ENCRYPTION_KEY", "EREV_AUDIT_HMAC_MASTER_KEY", "EREV_SECURITY_EVENT_HMAC_KEY")
TOTP_SECRET_NAME = "EREV_DEMO_TOTP_SECRET"
REQUIRED_NAMES = (
    tuple(name for _, owner, app in DB_URL_NAMES for name in (owner, app))
    + KEY_NAMES
    + (TOTP_SECRET_NAME,)
)
# A copy of erev_api.config.ALLOWED_DATABASE and REDIRECTING_QUERY_PARAMETERS: --tools runs before
# the virtual environment exists, so the script cannot import them; a unit test compares them.
DATABASE_ALLOW_LIST = re.compile(r"^(erev|erev_test|erev_e2e|erev_rv_[a-z0-9_]+)$")
REDIRECTING_QUERY_PARAMETERS = ("dbname", "service", "servicefile")
APP_ROLE = "erev_app"
OWNER_ROLE = "erev_owner"
# Runbook RB-04, RB-11 (DG-MK-backup rev 1.3): the backup role dumps the dev/production database;
# the restore-target admin loads a clone in an isolated erev_rv_* database. Both are DBA-provisioned
# BYPASSRLS roles, never erev_owner or erev_app (FORCE ROW LEVEL SECURITY, 04 DB-14). --db reports
# their presence and checks their shape; it never connects with them and never prints them. Ruling
# D-95 selects the recovery provider: NATIVE (default with EREV_KEY_PROVIDER=local) requires both
# under EREV_ENV=production and notes an absent one elsewhere, because make backup and
# make restore-verify fail closed without it anyway; MANAGED (default with gcp: Cloud SQL automated
# backup and PITR, 05 OPR-08) refuses a set value, because no documented Cloud SQL customer path
# grants BYPASSRLS (specifying it needs a superuser or an actor already holding it;
# cloudsqlsuperuser carries CREATEROLE, CREATEDB and LOGIN only): the native path is unestablished
# there and the design does not depend on it.
PRODUCTION_ENV = "production"
RECOVERY_PROVIDER_NAME = "EREV_RECOVERY_PROVIDER"
_PROVIDER_BY_KEYS = {"local": "NATIVE", "gcp": "MANAGED"}
MANAGED_DRILL_NOTE = (
    "recovery provider MANAGED: the restore-test project and instance of the managed drill are "
    "unknown inputs (UI-P6-2); Cloud SQL automated backups and PITR are the backup (05 OPR-08)"
)
BACKUP_URL_NAME = "EREV_BACKUP_URL"
RESTORE_ADMIN_URL_NAME = "EREV_RESTORE_ADMIN_URL"
RECOVERY_URL_NAMES = (BACKUP_URL_NAME, RESTORE_ADMIN_URL_NAME)
RESTORE_TARGET_DATABASE = re.compile(r"^erev_rv_[a-z0-9_]+$")
_URL_SCHEMES = ("postgresql+psycopg://", "postgresql://", "postgres://")

_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def read_env_file(path: Path) -> dict[str, str]:
    """Parse NAME=value lines; comments and blank lines are ignored."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if match is None:
            continue
        raw = match.group(2).strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        values[match.group(1)] = raw
    return values


def merged_environment(env_file: Path) -> dict[str, str]:
    """Values from the env file, overridden by the process environment (pydantic-settings order)."""
    merged = read_env_file(env_file)
    merged.update({k: v for k, v in os.environ.items() if k.startswith(("EREV_", "ANTHROPIC_"))})
    return merged


def database_name(url: str) -> str:
    return unquote(urlsplit(url).path.lstrip("/"))


def check_database_allowed(url: str) -> str | None:
    """Return an error naming only the database or a query parameter, or None (DG-ENV-13)."""
    for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        parameter = key.strip().lower()
        if parameter in REDIRECTING_QUERY_PARAMETERS:
            return f"database URL sets query parameter {parameter}"
    name = database_name(url)
    if DATABASE_ALLOW_LIST.fullmatch(name):
        return None
    return f"database not allowed: {name or '(none)'}"


def check_recovery_urls(env: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """(notes, errors) for the two recovery URLs (RB-04): an absent variable is a note, or an error
    when ``EREV_ENV=production``; a malformed one is an error. Nothing but variable and database
    names is ever returned."""
    notes: list[str] = []
    errors: list[str] = []
    production = env.get("EREV_ENV", "").strip() == PRODUCTION_ENV
    key_provider = (env.get("EREV_KEY_PROVIDER") or "local").strip()
    implied = _PROVIDER_BY_KEYS.get(key_provider)
    explicit = (env.get(RECOVERY_PROVIDER_NAME) or "").strip().upper()
    if implied is None:
        return notes, [f"EREV_KEY_PROVIDER is {key_provider}, which names no recovery provider"]
    if explicit and explicit not in _PROVIDER_BY_KEYS.values():
        return notes, [f"{RECOVERY_PROVIDER_NAME} must be NATIVE or MANAGED (D-95)"]
    if explicit and explicit != implied:
        return notes, [
            f"{RECOVERY_PROVIDER_NAME}={explicit} contradicts EREV_KEY_PROVIDER={key_provider} "
            "(D-95: local → NATIVE, gcp → MANAGED)"
        ]
    provider = explicit or implied
    if provider == "MANAGED":
        notes.append(MANAGED_DRILL_NOTE)
    dev_database = database_name(env["EREV_DB_OWNER_URL"]) if "EREV_DB_OWNER_URL" in env else None
    for name in RECOVERY_URL_NAMES:
        url = env.get(name, "")
        if provider == "MANAGED":
            if url:
                errors.append(
                    f"recovery URL not applicable: {name} is set under recovery provider MANAGED, "
                    "which has no native pg_dump path (D-95; 05 OPR-08, OPR-15)"
                )
            continue
        if not url:
            if production:
                errors.append(
                    f"recovery URL required: {name} (EREV_ENV=production, recovery provider "
                    "NATIVE; RB-04)"
                )
            else:
                notes.append(f"recovery URL absent: {name}")
            continue
        if not url.startswith(_URL_SCHEMES):
            errors.append(f"not a postgresql:// URL ({name})")
            continue
        allowed = check_database_allowed(url)
        if allowed is not None:
            errors.append(f"{allowed} ({name})")
            continue
        database = database_name(url)
        if name == BACKUP_URL_NAME and dev_database is not None and database != dev_database:
            errors.append(
                f"{name} must name the database of EREV_DB_OWNER_URL ({dev_database}), "
                f"not {database}"
            )
        if name == RESTORE_ADMIN_URL_NAME and not RESTORE_TARGET_DATABASE.fullmatch(database):
            errors.append(
                f"{name} must name an isolated erev_rv_* restore target, not {database} (05 OPR-11)"
            )
    return notes, errors


def _run_version(command: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else None


def _parse_version(text: str | None) -> tuple[int, int, int] | None:
    if text is None:
        return None
    match = _VERSION.search(text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def check_tools() -> int:
    failures = 0

    def report(tool: str, found: str | None, ok: bool, requirement: str) -> None:
        nonlocal failures
        status = "OK" if ok else f"FAIL (requires {requirement})"
        print(f"tool {tool}: {found or 'not found'} {status}")
        if not ok:
            failures += 1

    uv = _run_version(["uv", "--version"])
    uv_version = _parse_version(uv)
    report("uv", uv, uv_version is not None and uv_version[:2] >= (0, 11), ">= 0.11")

    python_path = _run_version(["uv", "python", "find", "3.12"])
    python = _run_version([python_path, "--version"]) if python_path else None
    python_version = _parse_version(python)
    report("python", python, python_version is not None and python_version[:2] == (3, 12), "3.12")

    node = _run_version(["node", "--version"])
    node_version = _parse_version(node)
    report("node", node, node_version is not None and node_version[0] >= 22, ">= 22")

    npm = _run_version(["npm", "--version"])
    report("npm", npm, npm is not None, "npm")

    psql = _run_version(["psql", "--version"])
    psql_version = _parse_version(psql)
    report("psql", psql, psql_version is not None and psql_version[0] == 17, "17")

    make = _run_version(["make", "--version"])
    make_version = _parse_version(make)
    report("make", make, make_version is not None and make_version[:2] >= (3, 81), ">= 3.81")

    for optional in ("docker", "terraform"):
        state = "available" if shutil.which(optional) else "not installed"
        print(f"tool {optional} (optional): {state}")
    return 1 if failures else 0


def ensure_keys(env_file: Path) -> int:
    """Append missing key lines with fresh random values; never change or print an existing line."""
    present = read_env_file(env_file)
    additions: list[tuple[str, str]] = [
        (name, secrets.token_hex(32)) for name in KEY_NAMES if name not in present
    ]
    if TOTP_SECRET_NAME not in present:
        additions.append((TOTP_SECRET_NAME, base64.b32encode(secrets.token_bytes(20)).decode()))
    if not additions:
        print("keys present")
        return 0
    created = not env_file.exists()
    existing = b"" if created else env_file.read_bytes()
    separator = b"\n" if existing and not existing.endswith(b"\n") else b""
    block = "".join(f"{name}={value}\n" for name, value in additions).encode()
    with env_file.open("ab") as handle:
        handle.write(separator + block)
    if created:
        os.chmod(env_file, 0o600)
    for name, _ in additions:
        print(f"added {name}")
    return 0


def check_names(env: Mapping[str, str]) -> int:
    missing = [name for name in REQUIRED_NAMES if name not in env]
    for name in missing:
        print(f"missing variable: {name}")
    if missing:
        return 1
    print(f"variables present: {len(REQUIRED_NAMES)} required names")
    return 0


def _connect_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def check_databases(env: Mapping[str, str]) -> int:
    missing = [name for _, owner, app in DB_URL_NAMES for name in (owner, app) if name not in env]
    for name in missing:
        print(f"missing variable: {name}")
    if missing:
        return 1

    errors = []
    for _, owner_name, app_name in DB_URL_NAMES:
        for name in (owner_name, app_name):
            error = check_database_allowed(env[name])
            if error is not None:
                errors.append(f"{error} ({name})")
    notes, recovery_errors = check_recovery_urls(env)
    errors.extend(recovery_errors)
    for error in errors:
        print(error)
    if errors:
        return 1
    for note in notes:
        print(note)
    present = [name for name in RECOVERY_URL_NAMES if env.get(name)]
    if present:
        print(f"recovery URLs OK: {', '.join(present)}")

    import psycopg  # the project environment provides psycopg; --tools runs without it

    failures = 0
    checked = []
    for _, owner_name, app_name in DB_URL_NAMES:
        database = database_name(env[app_name])
        try:
            with psycopg.connect(_connect_url(env[app_name]), connect_timeout=5) as conn:
                row = conn.execute(
                    "SELECT current_user, r.rolsuper, r.rolbypassrls "
                    "FROM pg_roles r WHERE r.rolname = current_user"
                ).fetchone()
        except psycopg.Error as exc:
            print(f"cannot connect to {database} ({app_name}): {type(exc).__name__}")
            failures += 1
            continue
        if row is None or tuple(row) != (APP_ROLE, False, False):
            found = row[0] if row else "unknown"
            print(
                f"role guard: expected {APP_ROLE} without SUPERUSER or BYPASSRLS on {database}, "
                f"found {found}"
            )
            failures += 1

        owner_database = database_name(env[owner_name])
        try:
            with psycopg.connect(_connect_url(env[owner_name]), connect_timeout=5) as conn:
                owner_row = conn.execute(
                    "SELECT current_user, r.rolsuper, "
                    "has_database_privilege(current_user, current_database(), 'CREATE') "
                    "FROM pg_roles r WHERE r.rolname = current_user"
                ).fetchone()
        except psycopg.Error as exc:
            print(f"cannot connect to {owner_database} ({owner_name}): {type(exc).__name__}")
            failures += 1
            continue
        if owner_row is None or tuple(owner_row[:2]) != (OWNER_ROLE, False):
            found = owner_row[0] if owner_row else "unknown"
            print(
                f"role guard: expected {OWNER_ROLE} without SUPERUSER on {owner_database}, "
                f"found {found}"
            )
            failures += 1
        elif owner_row[2] is not True:
            print(f"BLOCKED: {OWNER_ROLE} lacks CREATE on {owner_database}")
            failures += 1
        checked.append(database)
    if failures:
        return 1
    print(f"databases OK: {', '.join(checked)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--tools", action="store_true")
    parser.add_argument("--ensure-keys", action="store_true")
    parser.add_argument("--names", action="store_true")
    parser.add_argument("--db", action="store_true")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = parser.parse_args(argv)
    if not (args.tools or args.ensure_keys or args.names or args.db):
        parser.error("choose at least one of --tools, --ensure-keys, --names, --db")

    if args.tools and check_tools() != 0:
        return 1
    if args.ensure_keys and ensure_keys(args.env_file) != 0:
        return 1
    env = merged_environment(args.env_file)
    if args.names and check_names(env) != 0:
        return 1
    if args.db and check_databases(env) != 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
