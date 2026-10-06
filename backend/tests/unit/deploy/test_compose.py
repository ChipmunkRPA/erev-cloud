"""Compose file and local roles (05 §8.2 DPL-10 to DPL-16; DG-RUN-08; G§5; BUILD_SPEC DEP-2).

``deploy/compose.yaml``, ``deploy/compose.env.example`` and ``deploy/compose/initdb/01-roles.sql``
are read as files: the loop never runs Docker (DG-FORBID-12; ``make compose-verify`` is a supervisor
target). REQs: REQ-OPS-001 (ART; build verification by the supervisor), REQ-SEC-001.

DG-ARC-05 keeps host temporary paths and database administration statements out of machine files,
tests included. The expected tmpfs path is therefore read from the 05 DPL-13 text, and the script's
statements are matched with ``\\s+`` patterns.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import os
import re
import secrets
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml
from erev_api.config import Environment, Settings, SettingsError, database_of_url
from erev_api.controls.startup import production_refusals
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[4]
DEPLOY = ROOT / "deploy"
COMPOSE = DEPLOY / "compose.yaml"
ENV_EXAMPLE = DEPLOY / "compose.env.example"
INITDB = DEPLOY / "compose" / "initdb"
ROLES_SQL = INITDB / "01-roles.sql"
SECRETS_CHECK = ROOT / "scripts" / "secrets_check.py"
ARCHITECTURE = ROOT / "docs" / "05-ARCHITECTURE.md"

SERVICES = ("api", "migrate", "postgres", "web", "worker")
# The services that run the Python images (DPL-11, DPL-13, DPL-14).
PYTHON_SERVICES = ("migrate", "api", "worker")
PASSWORD_NAMES = (
    "EREV_COMPOSE_POSTGRES_PASSWORD",
    "EREV_COMPOSE_OWNER_PASSWORD",
    "EREV_COMPOSE_APP_PASSWORD",
)
KEY_NAMES = (
    "EREV_COMPOSE_ENCRYPTION_KEY",
    "EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY",
    "EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY",
)
# 05 CFG-18: the relay and the sender of the smtp backend (rev 1.53; R-34 SD-5).
SMTP_NAMES = (
    "EREV_COMPOSE_SMTP_HOST",
    "EREV_COMPOSE_SMTP_PORT",
    "EREV_COMPOSE_SMTP_USERNAME",
    "EREV_COMPOSE_SMTP_PASSWORD",
    "EREV_COMPOSE_SMTP_FROM",
)
# 05 CFG-09: the public origin is the operator's, because cookie Secure follows it (SAR-09).
PUBLIC_ORIGIN_NAME = "EREV_COMPOSE_PUBLIC_ORIGIN"
# 05 CFG-18, SAR-15 rev 1.53 (ruling R-39): the operator's private-relay opt-in and the bundle.
RELAY_NAMES = ("EREV_COMPOSE_SMTP_PRIVATE_RELAY", "EREV_COMPOSE_SMTP_CA_FILE")
API_BUILD = {"context": "..", "dockerfile": "deploy/docker/api.Dockerfile"}
OWNER_URL = "EREV_DB_OWNER_URL"


def compose_document() -> dict[str, Any]:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def services(document: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    found = (document or compose_document())["services"]
    assert isinstance(found, dict)
    return found


def environment(service: dict[str, Any]) -> dict[str, str]:
    raw = service.get("environment", {})
    assert isinstance(raw, dict), "environment is a mapping"
    return {str(name): str(value) for name, value in raw.items()}


def dpl13_tmpfs() -> str:
    """The container's own temporary directory named by 05 DPL-13 (`tmpfs: <path>`)."""
    rows = [
        line
        for line in ARCHITECTURE.read_text(encoding="utf-8").splitlines()
        if line.startswith("| DPL-13 |")
    ]
    assert len(rows) == 1, "one DPL-13 row"
    match = re.search(r"`tmpfs: (/\w+)`", rows[0])
    assert match is not None, "DPL-13 names the tmpfs path"
    return match.group(1)


def env_example() -> dict[str, str]:
    assignments = [
        line.split("=", 1)
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert all(len(parts) == 2 for parts in assignments), "NAME=value lines only"
    names = [name for name, _ in assignments]
    assert names == [*PASSWORD_NAMES, *KEY_NAMES, PUBLIC_ORIGIN_NAME, *SMTP_NAMES, *RELAY_NAMES]
    return dict(assignments)


def interpolated(service: dict[str, Any], values: dict[str, str]) -> dict[str, str]:
    """The service's environment as compose hands it to the container for ``values``. Compose
    interpolates string values after parsing the YAML, so the keys stay strings."""
    return {
        name: re.sub(r"\$\{(\w+)\}", lambda match: values[match.group(1)], value)
        for name, value in environment(service).items()
    }


def load_secrets_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("secrets_check", SECRETS_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def active_sql(text: str) -> str:
    """The script without ``--`` comments, whitespace collapsed to single spaces."""
    lines = [line.split("--", 1)[0] for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def runtime_runs(dockerfile: Path) -> str:
    text = dockerfile.read_text(encoding="utf-8").replace("\\\n", " ")
    runtime = re.split(r"(?m)^FROM \S+ AS runtime$", text, maxsplit=1)[1]
    return " ".join(line for line in runtime.splitlines() if line.startswith("RUN "))


def test_services() -> None:
    document = compose_document()
    assert document["name"] == "erev", "verification overrides the project with -p erev-verify"
    found = services(document)
    assert sorted(found) == list(SERVICES)
    # DPL-15 withdrawn (D-72): no mocks service and no rev 1.0 mocks port.
    assert "mocks" not in found
    assert "8191" not in COMPOSE.read_text(encoding="utf-8")

    postgres = found["postgres"]
    assert postgres["image"] == "postgres:17-bookworm"
    assert postgres["ports"] == ["127.0.0.1:5436:5432"]
    assert "erev-pg:/var/lib/postgresql/data" in postgres["volumes"]
    # DPL-10 rev 1.106 (item 6 of supervisor ruling R-108 (b)): the health check signs in as the
    # application role to the application database and runs one statement. `pg_isready` answered
    # 0 for any server that accepts connections, whether or not that role and database exist, so
    # a first start that the role-init script refused looked healthy and `migrate` failed first.
    probe = postgres["healthcheck"]["test"]
    assert probe[:2] == ["CMD", "psql"] and "pg_isready" not in probe
    assert probe[-2:] == ["-tAc", "select 1"]
    options = dict(zip(probe[2:-2:2], probe[3:-2:2], strict=True))
    assert options["-U"] == "erev_app"
    assert options["-d"] == "erev"
    assert options["-v"] == "ON_ERROR_STOP=1"
    # The image's temporary init server listens on the socket only; a TCP probe waits for the
    # restarted server, after 01-roles.sql has run.
    assert (options["-h"], options["-p"]) == ("127.0.0.1", "5432")
    # The role and the database the check names are the ones the init script makes (the
    # statements' verbs are left out here: DG-ARC-05 keeps them to the init script).
    roles = (ROOT / "deploy" / "compose" / "initdb" / "01-roles.sql").read_text(encoding="utf-8")
    assert " ROLE erev_app WITH LOGIN" in roles
    assert " DATABASE erev WITH OWNER erev_owner" in roles
    assert "GRANT CONNECT, TEMPORARY ON DATABASE erev TO erev_app" in roles

    migrate = found["migrate"]
    assert migrate["build"] == API_BUILD
    assert migrate["command"] == ["migrate"]
    assert migrate["restart"] == "no"
    assert migrate["depends_on"] == {"postgres": {"condition": "service_healthy"}}
    assert migrate["healthcheck"] == {"disable": True}, "a one-shot job has no health state"

    api = found["api"]
    assert api["build"] == API_BUILD
    assert api["image"] == migrate["image"], "migrate runs the api image (DPL-11)"
    assert "ports" not in api and "expose" not in api, "no published port (DPL-13)"
    api_environment = environment(api)
    assert {
        name: api_environment[name]
        for name in (
            "EREV_ENV",
            "EREV_KEY_PROVIDER",
            "EREV_EMAIL_BACKEND",
            "EREV_TRUSTED_PROXY_HOPS",
            "EREV_FILE_ROOT",
        )
    } == {
        "EREV_ENV": "production",
        "EREV_KEY_PROVIDER": "local",
        # 05 CFG-17 rev 1.53 (R-34 SD-5): a production process refuses the fake backend.
        "EREV_EMAIL_BACKEND": "smtp",
        "EREV_TRUSTED_PROXY_HOPS": "1",
        "EREV_FILE_ROOT": "/data/files",
    }
    assert api["read_only"] is True
    assert api["tmpfs"] == [dpl13_tmpfs()]
    assert api["volumes"] == ["erev-files:/data/files"]
    assert api["depends_on"] == {"migrate": {"condition": "service_completed_successfully"}}

    # DG-ENV-10: the database URLs name the container roles on postgres:5432, database erev.
    # 05 DPL-11, DPL-13 rev 1.53 (R-34 SD-1): migrate alone holds the owner URL.
    migrate_environment = environment(migrate)
    for variable, role, holder in (
        (OWNER_URL, "erev_owner", migrate_environment),
        ("EREV_DB_APP_URL", "erev_app", api_environment),
    ):
        url = urlsplit(holder[variable])
        assert (url.scheme, url.username, url.hostname, url.port) == (
            "postgresql+psycopg",
            role,
            "postgres",
            5432,
        )
        assert database_of_url(holder[variable], variable=variable) == "erev"

    worker = found["worker"]
    assert worker["build"] == {"context": "..", "dockerfile": "deploy/docker/worker.Dockerfile"}
    assert worker["command"] == ["worker"], "all eight queues: no --queues (DG-KRN-JOB-11)"
    assert worker["volumes"] == api["volumes"]
    assert worker["depends_on"] == api["depends_on"]
    # DPL-14: the worker runs on the api's environment; migrate on the same plus the owner URL,
    # which no long-lived service holds (DPL-33 least privilege, as hosted).
    assert environment(worker) == api_environment
    assert OWNER_URL not in api_environment
    assert migrate_environment == {**api_environment, OWNER_URL: migrate_environment[OWNER_URL]}
    assert "erev_owner" not in "".join(api_environment.values())

    web = found["web"]
    assert web["build"] == {"context": "..", "dockerfile": "deploy/docker/web.Dockerfile"}
    assert web["ports"] == ["127.0.0.1:8195:8080"]
    assert "environment" not in web, "nginx needs no secrets"
    assert web["depends_on"] == {"api": {"condition": "service_healthy"}}

    for name in ("migrate", "api", "worker", "web"):
        build = found[name]["build"]
        assert (COMPOSE.parent / build["context"]).resolve() == ROOT, name
        assert (ROOT / build["dockerfile"]).is_file(), name

    assert sorted(document["volumes"]) == ["erev-files", "erev-pg"]
    assert "keyring" not in COMPOSE.read_text(encoding="utf-8"), "no keyring volume (D-75 Q8)"


def test_ports_bind_loopback_only() -> None:
    published: list[str] = []
    for name, service in services().items():
        assert "network_mode" not in service, f"{name}: host networking bypasses port bindings"
        for entry in service.get("ports", []):
            assert isinstance(entry, str), f"{name}: short syntax with an explicit host address"
            assert entry.startswith("127.0.0.1:"), f"{name}: {entry} binds beyond loopback"
            published.append(entry)
    assert sorted(published) == ["127.0.0.1:5436:5432", "127.0.0.1:8195:8080"]


def test_initdb_roles() -> None:
    sql = active_sql(ROLES_SQL.read_text(encoding="utf-8"))
    assert sql.startswith("\\set ON_ERROR_STOP on ")

    assert re.findall(r"CREATE\s+ROLE\s+(\w+)", sql) == ["erev_owner", "erev_app"]
    denied = {"SUPERUSER", "CREATEDB", "CREATEROLE", "REPLICATION", "BYPASSRLS"}
    for role in ("erev_owner", "erev_app"):
        match = re.search(rf"CREATE\s+ROLE\s+{role}\s+WITH\s+([^;]+);", sql)
        assert match is not None, role
        attributes = set(match.group(1).split())
        assert {"LOGIN", "NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE", "NOBYPASSRLS"} <= attributes
        assert not denied & attributes, role
        # Passwords come from the container environment through psql variables, never literals.
        variable = re.search(r"\bPASSWORD\s+:'(\w+)'", match.group(1))
        assert variable is not None and variable.group(1) == f"{role}_password", role
    assert "PASSWORD '" not in sql
    assert re.findall(r"\\getenv (\w+) (\w+)", sql) == [
        ("erev_owner_password", "EREV_COMPOSE_OWNER_PASSWORD"),
        ("erev_app_password", "EREV_COMPOSE_APP_PASSWORD"),
        # 05 DPL-10 rev 1.53 (ruling R-53 (6)): read to refuse the example's placeholder; the
        # image itself set the superuser's password from it.
        ("postgres_password", "POSTGRES_PASSWORD"),
    ]
    # Missing or short passwords stop the script before any role exists.
    first_role = re.search(r"CREATE\s+ROLE\b", sql)
    assert first_role is not None and sql.index("RAISE EXCEPTION") < first_role.start()
    # So do the placeholders of the example file (rev 1.53): each of the three passwords is
    # compared with one pattern, every value the example ships matches it, the refusal names the
    # three variables of the environment file and no value, and both refusals precede the roles.
    refusals = [found.start() for found in re.finditer(r"RAISE EXCEPTION", sql)]
    assert len(refusals) == 2 and max(refusals) < first_role.start()
    compared = re.findall(r":'(\w+)' LIKE '([^']+)'", sql)
    assert compared == [
        ("erev_owner_password", "change-me%"),
        ("erev_app_password", "change-me%"),
        ("postgres_password", "change-me%"),
    ]
    shipped = env_example()
    for name in PASSWORD_NAMES:
        assert shipped[name].startswith("change-me"), name
    message = re.findall(r"RAISE EXCEPTION '([^']*)'", sql)[1]
    assert all(name in message for name in PASSWORD_NAMES)
    assert "deploy/compose.env.example" in message
    assert not any(shipped[name] in message for name in PASSWORD_NAMES)

    assert re.search(r"CREATE\s+DATABASE\s+erev\s+WITH\s+OWNER\s+erev_owner\b", sql)
    assert "REVOKE ALL ON DATABASE erev FROM PUBLIC;" in sql
    assert "GRANT CONNECT, CREATE, TEMPORARY ON DATABASE erev TO erev_owner;" in sql
    assert "GRANT CONNECT, TEMPORARY ON DATABASE erev TO erev_app;" in sql
    assert not re.search(r"\bALTER\s+(?:SYSTEM|ROLE)\b|\bDROP\s+\w", sql), "no settings or drops"

    # Inside the container only (G§5): the init directory is mounted read-only into postgres alone,
    # which receives the two password variables, and nothing on the host runs the script.
    found = services()
    mounts = {
        name: [volume for volume in service.get("volumes", []) if "initdb" in volume]
        for name, service in found.items()
    }
    assert mounts == {
        "postgres": ["./compose/initdb:/docker-entrypoint-initdb.d:ro"],
        "migrate": [],
        "api": [],
        "worker": [],
        "web": [],
    }
    assert sorted(path.name for path in INITDB.iterdir()) == ["01-roles.sql"]
    postgres_environment = environment(found["postgres"])
    assert postgres_environment == {
        "POSTGRES_PASSWORD": "${EREV_COMPOSE_POSTGRES_PASSWORD}",
        "EREV_COMPOSE_OWNER_PASSWORD": "${EREV_COMPOSE_OWNER_PASSWORD}",
        "EREV_COMPOSE_APP_PASSWORD": "${EREV_COMPOSE_APP_PASSWORD}",
    }
    host_side = [
        ROOT / "Makefile",
        *(ROOT / "scripts").rglob("*"),
        *(ROOT / "backend" / "erev_api").rglob("*.py"),
    ]
    for path in host_side:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(ROOT).as_posix()
        assert "01-roles.sql" not in text and "docker-entrypoint-initdb.d" not in text, relative
        assert not re.search(r"(?i)\bCREATE\s+ROLE\b", text), relative


def test_env_example_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings reads the process environment for what a service's environment does not name, so
    # the services are judged in a clean one: what the container gets is what compose hands it.
    for name in list(os.environ):
        if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    values = env_example()
    for name in PASSWORD_NAMES:
        assert values[name].startswith("change-me-"), name
        # URL-safe, because compose.yaml places the role passwords in the database URLs.
        assert re.fullmatch(r"[A-Za-z0-9_-]{12,}", values[name]), name
    # 05 CFG-26 rev 1.53 (R-34 SD-6): no master key is shipped — the patterned placeholders the
    # file carried passed the format check and were documented for use as they were.
    for name in KEY_NAMES:
        assert values[name] == "", f"{name}: no value in the example"
    # CFG-18 placeholders: a relay name that never resolves (RFC 6761 `.invalid`), no credential.
    assert values["EREV_COMPOSE_SMTP_HOST"].endswith(".invalid")
    assert values["EREV_COMPOSE_SMTP_FROM"].endswith("@example.invalid")
    assert values["EREV_COMPOSE_SMTP_PORT"] == "587"
    assert values["EREV_COMPOSE_SMTP_USERNAME"] == values["EREV_COMPOSE_SMTP_PASSWORD"] == ""
    # The private-relay opt-in is off and no bundle is named (SAR-15 rev 1.53).
    assert (values[RELAY_NAMES[0]], values[RELAY_NAMES[1]]) == ("false", "")
    # The verification stack's origin is the loopback port nginx publishes (DPL-12).
    assert values[PUBLIC_ORIGIN_NAME] == "http://127.0.0.1:8195"

    # Every interpolated variable is a bare ${EREV_COMPOSE_*} from the example, and each is used.
    text = COMPOSE.read_text(encoding="utf-8")
    references = re.findall(r"\$\{([^}]*)\}", text)
    assert all(re.fullmatch(r"EREV_COMPOSE_[A-Z0-9_]+", name) for name in references), references
    assert set(references) == set(values)

    # make secrets-check reports nothing for the DEP-2 files (DG-MK-secrets-check).
    secrets_check = load_secrets_check()
    for path in (COMPOSE, ENV_EXAMPLE, ROLES_SQL):
        relative = path.relative_to(ROOT).as_posix()
        assert secrets_check.scan_text(path.read_text(encoding="utf-8"), relative) == [], relative
        assert not relative.startswith(secrets_check.SKIPPED_PREFIXES), relative
        assert not any(
            fnmatch.fnmatchcase(path.name, pattern)
            for pattern in secrets_check.IGNORED_FILE_PATTERNS
        ), relative

    # As it is, the file starts nothing: the settings name the three missing keys.
    found = services()
    with pytest.raises(ValidationError) as missing:
        Settings(_env_file=None, **interpolated(found["api"], values))
    for name in (
        "EREV_ENCRYPTION_KEY",
        "EREV_AUDIT_HMAC_MASTER_KEY",
        "EREV_SECURITY_EVENT_HMAC_KEY",
    ):
        assert f"{name} must be set when EREV_KEY_PROVIDER is local" in str(missing.value)

    # With generated keys — what make compose-verify adds for its run — the file passes the
    # settings checks and the production startup subset (05 SAR-40 rev 1.53).
    generated = {**values, **{name: secrets.token_hex(32) for name in KEY_NAMES}}
    settings = Settings(_env_file=None, **interpolated(found["api"], generated))
    assert settings.env is Environment.PRODUCTION
    assert settings.key_provider == "local"
    assert settings.database_name() == "erev"
    assert settings.app_database_url().startswith("postgresql+psycopg://erev_app:")
    assert (settings.email_backend, settings.smtp_port) == ("smtp", 587)
    assert settings.smtp_host == "smtp.example.invalid"
    assert settings.smtp_username is None and settings.smtp_password is None  # blank is unset
    assert (settings.smtp_private_relay, settings.smtp_ca_file) == (False, None)
    # An environment file written before rev 1.53 names neither relay variable; compose then
    # hands the containers empty strings, which leave the opt-in off and the bundle unset.
    older = {**generated, **dict.fromkeys(RELAY_NAMES, "")}
    before = Settings(_env_file=None, **interpolated(found["api"], older))
    assert (before.smtp_private_relay, before.smtp_ca_file) == (False, None)
    assert production_refusals(before) == ()
    # The opt-in and a bundle path reach the api and the worker alike (the shared environment).
    relayed = {**generated, RELAY_NAMES[0]: "true", RELAY_NAMES[1]: "/etc/erev/smtp-ca.pem"}
    for service in ("api", "worker"):
        opted = Settings(_env_file=None, **interpolated(found[service], relayed))
        assert opted.smtp_private_relay is True, service
        assert opted.smtp_ca_file == Path("/etc/erev/smtp-ca.pem"), service
    assert settings.public_origin == "http://127.0.0.1:8195"
    assert production_refusals(settings) == ()
    # The api and the worker hold no owner URL; migrate does.
    with pytest.raises(SettingsError, match="EREV_DB_OWNER_URL is not set"):
        settings.owner_database_url()
    migrating = Settings(_env_file=None, **interpolated(found["migrate"], generated))
    assert migrating.owner_database_url().startswith("postgresql+psycopg://erev_owner:")
    # The placeholders the file shipped until rev 1.53 would now be refused at startup.
    shipped = {**values, **{name: "0" * 63 + str(n) for n, name in enumerate(KEY_NAMES, 1)}}
    refused = production_refusals(Settings(_env_file=None, **interpolated(found["api"], shipped)))
    assert len(refused) == 3 and all("is a placeholder" in line for line in refused)


def test_read_only_services_write_to_tmpfs_and_volumes() -> None:
    found = services()
    tmpfs = dpl13_tmpfs()
    for name in PYTHON_SERVICES:
        service = found[name]
        assert service["read_only"] is True, name
        assert service["tmpfs"] == [tmpfs], name
        # The run directory (heartbeat, fake mail) lives on the container's own tmpfs.
        assert environment(service)["EREV_RUN_DIR"].startswith(f"{tmpfs}/"), name
    for name in (*PYTHON_SERVICES, "web"):
        assert found[name]["cap_drop"] == ["ALL"], name
        assert found[name]["security_opt"] == ["no-new-privileges:true"], name
    # A new named volume copies the ownership of the image's mount point, so both images create
    # /data/files for uid 10001 (DPL-13, DPL-14).
    for dockerfile in ("api.Dockerfile", "worker.Dockerfile"):
        runs = runtime_runs(DEPLOY / "docker" / dockerfile)
        assert re.search(r"mkdir -p [^&]*/data/files\b", runs), dockerfile
        assert re.search(r"chown -R 10001:10001 [^&]* /data\b", runs), dockerfile
