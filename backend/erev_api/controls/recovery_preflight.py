"""Recovery preflight KRN-RCV: the pure checks that ``scripts/backup.sh`` and
``scripts/restore_verify.sh`` run before they read, dump, drop, restore or extract anything (05
OPR-11, OPR-12, OPR-15, OPR-16; runbook RB-04, RB-06; independent review P6-R1 to R4, R7).

- Endpoint binding (R1): every role URL of one operation must reach the same server, port and
  database after libpq routing is accounted for; routing query parameters are refused, so the URL
  text is the whole route. ``server_identity`` is the SQL every connection then answers, so the
  scripts compare the servers they actually reached, not only the URLs they were given.
- Manifest completeness (R2): a manifest is bound to its backup id and covers exactly the four
  members the restore consumes, each with a lowercase SHA-256 and a positive size; the backup-time
  digests document is validated for schema and population and bound to the manifest.
- Backup ids and paths (R3): only ``erev-<yyyymmdd>T<hhmmss>Z`` is a backup id; restore roots and
  archive members are contained after canonicalisation; links are refused.
- Effective keys (R4): the master keys the verification used (environment first, then the copied
  ``.env``) must be the keys the ``.env`` copy carries, or the backup is not restorable.
- Measurements (R7): the restore point is the dump's snapshot start, never the manifest instant;
  recovered-evidence freshness excludes what the verifier itself appended; a drill's duration is
  not a cutover RTO.

No database and no file store is touched here; ``server_identity`` returns SQL text only.
"""

from __future__ import annotations

import json
import os
import re
import tarfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import UUID

from erev_api.config import ALLOWED_DATABASE

MANIFEST_SCHEMA: Final = "erev-backup-manifest/2"
DOCUMENT_SCHEMA: Final = "erev-recovery-verify/1"
BACKUP_ID: Final = re.compile(r"^erev-\d{8}T\d{6}Z$")
FILE_ROOT_NAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")
SECURITY_KEY_ID: Final = re.compile(r"^security-hmac:([1-9][0-9]*)$")
# RFC 3339 date-time only (calendar date, "T", seconds, optional fraction, "Z" or a numeric
# offset): week dates, ordinal dates, a space separator or missing seconds are refused even
# though Python's ISO 8601 parser would accept them (review ef8d8d3 residual 3).
RFC3339: Final = re.compile(
    r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T([01]\d|2[0-3]):[0-5]\d:([0-5]\d|60)"
    r"(\.\d{1,9})?(Z|[+-]([01]\d|2[0-3]):[0-5]\d)$"
)
IDENTITY_STUB_ENVIRONMENTS: Final = frozenset({"test", "dev"})
RESTORE_PIN_OVERRIDE_NAME: Final = "RESTORE_SECURITY_HMAC_VERSION"
CLONE_PIN_NAME: Final = "EREV_SECURITY_HMAC_SECRET_VERSION"
RESTORE_TARGET_DATABASE: Final = re.compile(r"^erev_rv_[a-z0-9_]+$")
DEFAULT_PORT: Final = 5432
URL_SCHEMES: Final = ("postgresql+psycopg://", "postgresql://", "postgres://")
# libpq keywords that would route a connection somewhere the URL's authority and path do not say.
ROUTING_QUERY_PARAMETERS: Final = ("host", "hostaddr", "port", "dbname", "service", "servicefile")
MASTER_KEY_NAMES: Final = (
    "EREV_ENCRYPTION_KEY",
    "EREV_AUDIT_HMAC_MASTER_KEY",
    "EREV_SECURITY_EVENT_HMAC_KEY",
)
# Ruling D-95 (hosted recovery provider). NATIVE: the read-only BYPASSRLS role dumps and the
# restore-target admin loads, where an authorised provisioner (a superuser, or an actor already
# holding BYPASSRLS) exists: self-hosted PostgreSQL and the compose stack. MANAGED: Cloud SQL
# automated backups and PITR (05 OPR-08, OPR-11, OPR-16) with the managed restore-test record
# (`recovery_managed`); Cloud SQL gives customers no superuser, cloudsqlsuperuser carries
# CREATEROLE, CREATEDB and LOGIN only and membership does not inherit attributes, so no documented
# customer path grants BYPASSRLS there: the native path is unestablished on Cloud SQL and the design
# does not depend on it. The default follows EREV_KEY_PROVIDER (local → NATIVE, gcp → MANAGED); an
# explicit value that contradicts the key provider is a configuration error.
RECOVERY_PROVIDER_NAME: Final = "EREV_RECOVERY_PROVIDER"
NATIVE: Final = "NATIVE"
MANAGED: Final = "MANAGED"
RECOVERY_PROVIDERS: Final = (NATIVE, MANAGED)
_PROVIDER_BY_KEYS: Final = {"local": NATIVE, "gcp": MANAGED}
MEMBER_KINDS: Final = ("dump", "files", "env", "digests")
# Every connection of one operation answers this; equal rows mean one server and one database.
SERVER_IDENTITY_SQL: Final = (
    "SELECT current_database(), (SELECT oid FROM pg_database WHERE datname = current_database()), "
    "pg_postmaster_start_time(), inet_server_addr()::text, inet_server_port()"
)


class PreflightError(ValueError):
    """A refusal; its message names variables, hosts, ports and databases, never credentials."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    host: str  # "" for a Unix socket
    port: int
    database: str

    def describe(self) -> str:
        where = "socket" if not self.host else f"{self.host}:{self.port}"
        return f"{where}/{self.database}"


def endpoint_of(url: str, *, variable: str) -> Endpoint:
    """The server, port and database ``url`` routes to; refuses routing query parameters and
    databases outside the DG-ENV-13 allow-list (R1)."""
    if not url.startswith(URL_SCHEMES):
        raise PreflightError(f"{variable} is not a postgresql:// URL")
    parts = urlsplit(url)
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        parameter = key.strip().lower()
        if parameter in ROUTING_QUERY_PARAMETERS:
            raise PreflightError(
                f"{variable} sets query parameter {parameter}, which could route the connection "
                "elsewhere (DG-ENV-13)"
            )
    database = unquote(parts.path.lstrip("/"))
    if not ALLOWED_DATABASE.fullmatch(database):
        raise PreflightError(
            f"{variable} names database {database or '(none)'}, which is outside the allow-list "
            "(DG-ENV-13)"
        )
    try:
        port = parts.port
    except ValueError as error:
        raise PreflightError(f"{variable} has an invalid port") from error
    host = (parts.hostname or "").lower()
    return Endpoint(host=host, port=DEFAULT_PORT if port is None else int(port), database=database)


def same_endpoint(urls: Mapping[str, str]) -> Endpoint:
    """The one endpoint every URL of ``urls`` (variable name → URL) reaches; refuses otherwise."""
    if not urls:
        raise PreflightError("no URLs to bind")
    names = list(urls)
    endpoints = {name: endpoint_of(urls[name], variable=name) for name in names}
    first = endpoints[names[0]]
    for name in names[1:]:
        if endpoints[name] != first:
            raise PreflightError(
                f"{name} reaches {endpoints[name].describe()}, not {first.describe()} "
                f"({names[0]}); every role URL of one operation must reach the same server, "
                "port and database"
            )
    return first


IDENTITY_STUB_NAME: Final = "EREV_RECOVERY_IDENTITY_STUB"


def identity_stub(environ: Mapping[str, str], *, env_name: str | None = None) -> str | None:
    """The test-only identity stub path, or None. Honoured under ``EREV_ENV`` ``test`` or ``dev``
    only (supervisor ruling of 2026-09-19): under any other environment a set value is a hard
    error naming the variable, raised before any connection, so a stub can never stand in for a
    server identity outside a test or development checkout. ``env_name`` is the caller's
    environment when the caller has already switched ``EREV_ENV`` (the scripts export ``dev``; the
    CLI switches for ``--db``); it defaults to ``EREV_ENV`` in ``environ`` (unset means ``dev``)."""
    stub = environ.get(IDENTITY_STUB_NAME) or None
    if stub is None:
        return None
    name = (env_name if env_name is not None else environ.get("EREV_ENV")) or "dev"
    if name.strip().lower() not in IDENTITY_STUB_ENVIRONMENTS:
        raise PreflightError(
            f"{IDENTITY_STUB_NAME} is set under EREV_ENV={name}: the identity stub is honoured "
            "under test or dev only"
        )
    return stub


def connected_identities(
    urls: Mapping[str, str],
    environ: Mapping[str, str] | None = None,
    *,
    env_name: str | None = None,
) -> dict[str, tuple[str, ...]]:
    """The SERVER_IDENTITY_SQL row of every URL (variable → row), connecting with psycopg; a
    connection failure is a PreflightError naming the variable and the error class only. Tests
    substitute the rows through ``EREV_RECOVERY_IDENTITY_STUB`` (a JSON object keyed by variable),
    the same stub the scripts honour, gated by ``identity_stub``."""
    stub = identity_stub(environ if environ is not None else os.environ, env_name=env_name)
    if stub:
        loaded = load_json_strict(Path(stub).read_text(encoding="utf-8"))
        missing = [name for name in urls if name not in loaded]
        if missing:
            raise PreflightError(f"identity stub has no row for {', '.join(missing)}")
        return {name: tuple(str(v) for v in loaded[name]) for name in urls}
    import psycopg

    rows: dict[str, tuple[str, ...]] = {}
    for name, url in urls.items():
        parts = urlsplit(url)
        sslmode = dict(parse_qsl(parts.query)).get("sslmode")
        try:
            with psycopg.connect(
                host=parts.hostname,
                port=parts.port or DEFAULT_PORT,
                user=unquote(parts.username or ""),
                password=unquote(parts.password or ""),
                dbname=unquote(parts.path.lstrip("/")),
                connect_timeout=10,
                sslmode=sslmode,
            ) as connection:
                row = connection.execute(SERVER_IDENTITY_SQL).fetchone()
        except psycopg.Error as error:
            raise PreflightError(
                f"cannot reach the server named by {name}: {type(error).__name__}"
            ) from error
        rows[name] = tuple(str(value) for value in (row or ()))
    return rows


def server_identity(rows: Mapping[str, tuple[Any, ...]]) -> list[str]:
    """Findings when the connections named by ``rows`` (variable → the SERVER_IDENTITY_SQL row)
    did not all reach the same server and database."""
    names = list(rows)
    if len(names) < 2:
        return []
    first = tuple(rows[names[0]])
    findings = []
    for name in names[1:]:
        if tuple(rows[name]) != first:
            findings.append(
                f"{name} reached another server or database than {names[0]} "
                f"(database {rows[name][0]} vs {first[0]})"
            )
    return findings


def security_key_version(key_id: Any) -> int:
    """The numbered version of a ``security-hmac:<n>`` key id (lane P2's id grammar); refuses
    anything else."""
    match = SECURITY_KEY_ID.fullmatch(str(key_id or ""))
    if match is None:
        raise PreflightError(f"{key_id!r} is not a security-hmac:<n> key id")
    return int(match.group(1))


def security_inventory_errors(security: Mapping[str, Any]) -> list[str]:
    """Why a document's ``security_chain`` does not carry the global key inventory of the P2/P6
    integration (`required_key_ids` = every key id the T-PLT-06 rows name plus the current pin;
    `current_key_id` = the pin; `head_key_id` = the key of the chain head row)."""
    errors: list[str] = []
    required = security.get("required_key_ids")
    if not isinstance(required, list) or not required:
        errors.append("expected document security_chain.required_key_ids is empty")
        required = []
    versions: list[int] = []
    for key_id in required:
        try:
            versions.append(security_key_version(key_id))
        except PreflightError:
            errors.append(
                "expected document security_chain.required_key_ids has an entry that is not a "
                "security-hmac:<n> key id"
            )
            break
    if len(set(versions)) != len(versions):
        errors.append("expected document security_chain.required_key_ids repeats a key id")
    for name in ("current_key_id", "head_key_id"):
        value = security.get(name)
        try:
            security_key_version(value)
        except PreflightError:
            errors.append(
                f"expected document security_chain.{name} is not a security-hmac:<n> key id"
            )
            continue
        if required and value not in required:
            errors.append(f"expected document security_chain.{name} is not in required_key_ids")
    return errors


def clone_security_pin(document: Mapping[str, Any], *, override: Any = None) -> dict[str, Any]:
    """P2/P6 integration control 3: the ``EREV_SECURITY_HMAC_SECRET_VERSION`` a native restore
    binds the clone to, decided from the backup evidence before any mutation and never inherited
    from the restore host. The backup's pin must not be behind its own chain head; an operator's
    ``RESTORE_SECURITY_HMAC_VERSION`` may only move forward (an explicit, recorded rotation): a pin
    behind the restored head would let the verifier's first platform event append a backwards
    key transition (KEY-03)."""
    security = document.get("security_chain") if isinstance(document, Mapping) else None
    if not isinstance(security, Mapping):
        raise PreflightError("expected document has no security_chain")
    errors = security_inventory_errors(security)
    if errors:
        raise PreflightError("; ".join(errors))
    head_version = security_key_version(security.get("head_key_id"))
    pin_version = security_key_version(security.get("current_key_id"))
    if pin_version < head_version:
        raise PreflightError(
            f"the backup's signing pin security-hmac:{pin_version} is behind its chain head "
            f"security-hmac:{head_version}; the backup evidence is inconsistent and the clone "
            "cannot be pinned from it"
        )
    version = pin_version
    if override is not None and str(override) != "":
        text = str(override).strip()
        if not text.isdigit() or int(text) < 1:
            raise PreflightError(
                f"{RESTORE_PIN_OVERRIDE_NAME} must be a positive integer version number"
            )
        version = int(text)
        if version < head_version:
            raise PreflightError(
                f"{RESTORE_PIN_OVERRIDE_NAME}={version} is behind the restored chain head "
                f"security-hmac:{head_version}; a stale pin may not append (KEY-03)"
            )
        if version < pin_version:
            # Review df43dd9 H1: forward-only is measured against the SOURCE pin as well as the
            # head; a move below the pin the backup was taken under is a rotation backwards.
            raise PreflightError(
                f"{RESTORE_PIN_OVERRIDE_NAME}={version} is below the backup's signing pin "
                f"security-hmac:{pin_version}; the override may only move forward"
            )
    return {
        "version": version,
        "key_id": f"security-hmac:{version}",
        "backup_pin": str(security["current_key_id"]),
        "head_key_id": str(security["head_key_id"]),
        "required_key_ids": list(security["required_key_ids"]),
        "forward_rotation": version > pin_version,
    }


DSN_CREDENTIALS: Final = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@'\"]*@")
# A secret assignment in diagnostic text: the name, `=` / `:` / `=>` with optional whitespace, and
# a value that is bare, single-quoted or double-quoted (the quotes are kept, the value is not).
KEY_VALUE_SECRET: Final = re.compile(
    r"((?:(?i:pgpassword|password|passwd)|EREV_[A-Z0-9_]*(?:KEY|URL|SECRET|PASSWORD))"
    r"\s*(?:=>|[=:])\s*)(['\"]?)([^\s'\"]+)(\2)?"
)


def redact_diagnostics(text: Any, *secrets: str | None) -> str:
    """Diagnostic text safe to print (common-terms amendment of 2026-09-19 after two credential
    exposures): credentials inside any DSN (``scheme://user:password@host`` → ``scheme://***@host``),
    ``PGPASSWORD`` / ``password`` / ``passwd`` / ``EREV_*_(URL|KEY|SECRET|PASSWORD)`` assignments
    (``=``, ``:`` or ``=>``; bare or quoted values, quotes kept), and every literal secret passed in
    are replaced by ``***``. Host, port, database name, PIDs, stages and counts
    stay; the scripts print nothing else about a connection."""
    out = str(text or "")
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    out = DSN_CREDENTIALS.sub(r"\1***@", out)
    return KEY_VALUE_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}***{m.group(2)}", out)


def validate_backup_id(value: str) -> str:
    if not BACKUP_ID.fullmatch(value or ""):
        raise PreflightError(
            "BACKUP must be a backup id of the form erev-<yyyymmdd>T<hhmmss>Z (or latest)"
        )
    return value


def expected_members(backup_id: str) -> dict[str, str]:
    """The four files a backup consists of and a restore consumes, by kind."""
    validate_backup_id(backup_id)
    return {
        "dump": f"{backup_id}.dump",
        "files": f"{backup_id}-files.tar.gz",
        "env": f"{backup_id}.env",
        "digests": f"{backup_id}.digests.json",
    }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_json_strict(text: str) -> Any:
    """``json.loads`` that refuses duplicate keys (a manifest with two entries of one name)."""
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def validate_manifest(manifest: Any, *, backup_id: str) -> list[str]:
    """Every reason a manifest is not a complete, bound inventory of ``backup_id`` (R2, R3)."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    if manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append(f"manifest schema is not {MANIFEST_SCHEMA}")
    if manifest.get("backup_id") != backup_id:
        errors.append(f"manifest backup_id is not {backup_id}")
    members = expected_members(backup_id)
    files = manifest.get("files")
    if not isinstance(files, dict):
        errors.append("manifest files is not an object")
        files = {}
    expected_names = set(members.values())
    present = set(files)
    for name in sorted(expected_names - present):
        errors.append(f"manifest omits {name}")
    for name in sorted(present - expected_names):
        errors.append(f"manifest lists an unexpected member {name!r}")
    for name in sorted(present & expected_names):
        entry = files[name]
        if not isinstance(entry, dict):
            errors.append(f"manifest entry {name} is not an object")
            continue
        sha256 = entry.get("sha256")
        size = entry.get("size_bytes")
        if not isinstance(sha256, str) or not SHA256_HEX.fullmatch(sha256):
            errors.append(f"manifest entry {name} has no lowercase 64-hex sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"manifest entry {name} has no positive size_bytes")
    digests = manifest.get("digests")
    if not isinstance(digests, dict):
        errors.append("manifest digests is not an object")
    else:
        if digests.get("file") != members["digests"]:
            errors.append(f"manifest digests.file is not {members['digests']}")
        if digests.get("result") not in ("PASS", "FAIL"):
            errors.append("manifest digests.result is not PASS or FAIL")
        if not _is_int(digests.get("tenants")) or int(digests["tenants"]) < 1:
            errors.append("manifest digests.tenants is not a positive count")
    file_root = manifest.get("file_root")
    if not isinstance(file_root, str) or not FILE_ROOT_NAME.fullmatch(file_root):
        errors.append("manifest file_root is not a plain directory name")
    # R7 residual: every required instant parses as RFC 3339 with an offset, and they are ordered
    # digests → snapshot start → snapshot end → manifest; a corrupt instant is refused, never
    # replaced by a later one.
    instants: dict[str, datetime] = {}
    for field in ("started_at", "snapshot_started_at", "snapshot_finished_at", "created_at"):
        parsed = _parse_instant(manifest.get(field))
        if parsed is None:
            errors.append(f"manifest {field} is missing or not an RFC 3339 instant with an offset")
        else:
            instants[field] = parsed
    if isinstance(digests, dict):
        generated = _parse_instant(digests.get("generated_at"))
        if generated is None:
            errors.append("manifest digests.generated_at is not an RFC 3339 instant with an offset")
        else:
            instants["digests.generated_at"] = generated
    if "security_hmac_pin" in manifest:
        try:
            security_key_version(manifest.get("security_hmac_pin"))
        except PreflightError:
            errors.append("manifest security_hmac_pin is not a security-hmac:<n> key id")
    order = (
        "started_at",
        "digests.generated_at",
        "snapshot_started_at",
        "snapshot_finished_at",
        "created_at",
    )
    known = [(name, instants[name]) for name in order if name in instants]
    for (earlier_name, earlier), (later_name, later) in zip(known, known[1:], strict=False):
        if earlier > later:
            errors.append(f"manifest {earlier_name} is later than {later_name}")
    database = manifest.get("database")
    if not isinstance(database, str) or not ALLOWED_DATABASE.fullmatch(database):
        errors.append("manifest database is not an allow-listed database name")
    return errors


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_uuid(value: Any) -> bool:
    try:
        UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


FILE_STATUSES: Final = frozenset(
    {
        "ok",
        "shredded",
        "missing_object",
        "missing_sidecar",
        "shredded_sidecar_present",
        "undecryptable",
        "foreign_storage_key",
        "sha256_mismatch",
        "size_mismatch",
    }
)


def _hex_or_none_for(seq: Any, value: Any) -> bool:
    """A chain head's hash: a 64-hex string when the head is past sequence 0, None when empty."""
    if not _is_int(seq) or int(seq) < 0:
        return False
    if int(seq) == 0:
        return value is None
    return isinstance(value, str) and SHA256_HEX.fullmatch(value) is not None


def _well_formed_head(head: Any) -> bool:
    if not isinstance(head, dict):
        return False
    return _hex_or_none_for(head.get("last_chain_seq"), head.get("last_hmac"))


def _typed_key(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("key_id"), str)
        and bool(entry.get("key_id"))
        and isinstance(entry.get("available"), bool)
    )


def validate_expected_document(document: Any) -> list[str]:
    """Every reason a backup-time verification document is not a usable baseline (R2 and its
    residual): schema, result, a populated tenant list whose count matches, and for every tenant
    an explicit head (an empty head is ``last_chain_seq 0`` with ``last_hmac null``; an omitted
    head is refused, because it would suppress the anchor comparison), nonzero heads with their
    hashes, typed ledger chains, typed file entries with coherent counts and typed key entries.
    A document that would raise or anchor nothing is refused before any mutation."""
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["expected document is not a JSON object"]
    if document.get("schema") != DOCUMENT_SCHEMA:
        errors.append(f"expected document schema is not {DOCUMENT_SCHEMA}")
    if document.get("result") not in ("PASS", "FAIL"):
        errors.append("expected document result is not PASS or FAIL")
    if _parse_instant(document.get("generated_at")) is None:
        errors.append("expected document generated_at is missing or not an RFC 3339 instant")
    security = document.get("security_chain")
    if not isinstance(security, dict) or not _is_int(security.get("last_chain_seq")):
        errors.append("expected document security_chain.last_chain_seq is missing")
    else:
        if not _hex_or_none_for(security.get("last_chain_seq"), security.get("last_hmac")):
            errors.append(
                "expected document security_chain.last_hmac is missing for a nonzero head"
            )
        # P2/P6 integration: the global security-key inventory travels with the evidence.
        errors.extend(security_inventory_errors(security))
    tenants = document.get("tenants")
    if not isinstance(tenants, list) or not tenants:
        errors.append("expected document records no tenants")
        tenants = []
    counts = document.get("counts")
    if not isinstance(counts, dict) or counts.get("tenants") != len(tenants):
        errors.append("expected document counts.tenants does not match its tenants")
    seen: set[str] = set()
    files_total = 0
    for index, workspace in enumerate(tenants):
        label = f"tenants[{index}]"
        if not isinstance(workspace, dict):
            errors.append(f"expected document {label} is not an object")
            continue
        tenant_id = workspace.get("tenant_id")
        if not _is_uuid(tenant_id):
            errors.append(f"expected document {label}.tenant_id is not a UUID")
        elif str(tenant_id) in seen:
            errors.append(f"expected document {label}.tenant_id repeats")
        else:
            seen.add(str(tenant_id))
        if not isinstance(workspace.get("code"), str) or not workspace.get("code"):
            errors.append(f"expected document {label}.code is missing")
        if "head" not in workspace or workspace.get("head") is None:
            errors.append(
                f"expected document {label}.head is omitted (an empty head is last_chain_seq 0 "
                "with last_hmac null)"
            )
        elif not _well_formed_head(workspace.get("head")):
            errors.append(f"expected document {label}.head is malformed")
        chains = workspace.get("ledger_chains")
        if not isinstance(chains, list):
            errors.append(f"expected document {label}.ledger_chains is not a list")
        else:
            for book in chains:
                if (
                    not isinstance(book, dict)
                    or not isinstance(book.get("book_code"), str)
                    or not _hex_or_none_for(
                        book.get("last_chain_seq"), book.get("last_seal_sha256")
                    )
                ):
                    errors.append(f"expected document {label}.ledger_chains has a malformed book")
                    break
        files = workspace.get("files")
        entries = files.get("entries") if isinstance(files, dict) else None
        if not isinstance(entries, list) or not isinstance(files, dict):
            errors.append(f"expected document {label}.files.entries is not a list")
        else:
            files_total += len(entries)
            for entry in entries:
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("storage_key"), str)
                    or entry.get("status") not in FILE_STATUSES
                    or not isinstance(entry.get("sha256"), str)
                    or not SHA256_HEX.fullmatch(str(entry.get("sha256")))
                ):
                    errors.append(f"expected document {label}.files.entries has a malformed entry")
                    break
            declared = files.get("checked")
            if declared is not None and declared != len(entries):
                errors.append(f"expected document {label}.files.checked does not match its entries")
            statuses = [files.get(name) for name in ("ok", "shredded", "failed")]
            if all(_is_int(v) for v in statuses) and _is_int(declared):
                if sum(int(str(v)) for v in statuses) != int(str(declared)):
                    errors.append(f"expected document {label}.files counts are incoherent")
        keys = workspace.get("audit_hmac_keys")
        if not isinstance(keys, list) or not keys:
            errors.append(f"expected document {label}.audit_hmac_keys is empty")
        elif not all(_typed_key(k) for k in keys):
            errors.append(f"expected document {label}.audit_hmac_keys has an untyped entry")
    versions = document.get("key_versions")
    if not isinstance(versions, dict):
        errors.append("expected document key_versions is missing")
    else:
        for name in ("security_hmac", "audit_hmac"):
            items = versions.get(name)
            if not isinstance(items, list) or not all(_typed_key(k) for k in items):
                errors.append(f"expected document key_versions.{name} has an untyped entry")
        served = versions.get("security_hmac")
        if (
            isinstance(security, dict)
            and isinstance(served, list)
            and all(_typed_key(k) for k in served)
        ):
            listed = {str(k["key_id"]) for k in served}
            required = security.get("required_key_ids")
            if isinstance(required, list) and not set(map(str, required)) <= listed:
                errors.append(
                    "expected document key_versions.security_hmac does not cover every "
                    "required security key id"
                )
        keks = versions.get("kek")
        if not isinstance(keks, list) or not all(
            (isinstance(k, str) and k) or _typed_key(k) for k in keks
        ):
            errors.append("expected document key_versions.kek has an untyped entry")
    files_counts = counts.get("files") if isinstance(counts, dict) else None
    if isinstance(files_counts, dict) and _is_int(files_counts.get("checked")):
        if int(files_counts["checked"]) != files_total:
            errors.append("expected document counts.files.checked does not match the tenants")
    return errors


def bind_expected_to_manifest(
    expected: Mapping[str, Any], manifest: Mapping[str, Any]
) -> list[str]:
    """Findings when the digests document is not the one the manifest describes."""
    raw_digests = manifest.get("digests")
    digests: dict[str, Any] = dict(raw_digests) if isinstance(raw_digests, dict) else {}
    raw_counts = expected.get("counts")
    counts: dict[str, Any] = dict(raw_counts) if isinstance(raw_counts, dict) else {}
    findings = []
    if expected.get("generated_at") != digests.get("generated_at"):
        findings.append("expected document generated_at differs from the manifest's digests")
    if expected.get("result") != digests.get("result"):
        findings.append("expected document result differs from the manifest's digests")
    if counts.get("tenants") != digests.get("tenants"):
        findings.append("expected document tenant count differs from the manifest's digests")
    pin = manifest.get("security_hmac_pin")
    security = expected.get("security_chain")
    current = security.get("current_key_id") if isinstance(security, Mapping) else None
    if pin is not None and pin != current:
        findings.append(
            "expected document security pin differs from the manifest's security_hmac_pin"
        )
    return findings


def real_directory(path: Path, *, label: str, allow_link: bool = False) -> Path:
    """``path`` as a trusted real directory, created when absent (R3 residual). The run directory
    itself may be a link to another disk (``allow_link=True``: its realpath is the anchor); a
    restore root or anything beneath it must be a plain directory, never a symbolic link."""
    if path.is_symlink() and not allow_link:
        raise PreflightError(f"{label} {path} is a symbolic link")
    if path.exists() and not path.is_dir():
        raise PreflightError(f"{label} {path} is not a directory")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def contained_path(root: Path, child: Path, *, label: str) -> Path:
    """``child`` as a real path inside the trusted real directory ``root`` (R3, and the review
    residual of 2026-09-19): ``root`` is realpath'd first and must be a directory; ``child`` is
    taken relative to ``root`` and every component below it must be a plain segment (no ``..``,
    no absolute path); every component that already exists is ``lstat``-checked and refused when
    it is a symbolic link, so a linked parent can never carry a descendant outside ``root``."""
    real_root = root.resolve()
    if not real_root.is_dir():
        raise PreflightError(f"{label}: root {root} is not a directory")
    if child.is_absolute():
        try:
            relative = child.relative_to(root)
        except ValueError:
            try:
                relative = child.relative_to(real_root)
            except ValueError as error:
                raise PreflightError(f"{label} escapes {root}") from error
    else:
        relative = child
    parts = relative.parts
    if not parts:
        raise PreflightError(f"{label} escapes {root}")
    if any(part in ("", ".", "..") or "/" in part or "\\" in part for part in parts):
        raise PreflightError(f"{label} has an unsafe path segment")
    current = real_root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise PreflightError(f"{label}: {current} is a symbolic link")
    resolved = current.resolve()
    if resolved == real_root or real_root not in resolved.parents:
        raise PreflightError(f"{label} escapes {root}")
    return resolved


def validate_archive_members(members: Iterable[tuple[str, str]], *, file_root: str) -> list[str]:
    """Findings for archive members ``(name, kind)`` where kind is ``file``, ``dir`` or anything
    else (links, devices): every member lies under ``file_root/`` with plain segments (R3)."""
    if not FILE_ROOT_NAME.fullmatch(file_root or ""):
        return ["file_root is not a plain directory name"]
    findings: list[str] = []
    for name, kind in members:
        if kind not in ("file", "dir"):
            findings.append(f"archive member {name!r} is a {kind}, not a file or directory")
            continue
        if name.startswith("/") or name.startswith("\\"):
            findings.append(f"archive member {name!r} is absolute")
            continue
        segments = name.rstrip("/").split("/")
        if any(segment in ("", ".", "..") for segment in segments) or "\\" in name:
            findings.append(f"archive member {name!r} has an unsafe path segment")
            continue
        if segments[0] != file_root:
            findings.append(f"archive member {name!r} lies outside {file_root}/")
    return findings


def inspect_archive(path: Path, *, file_root: str) -> list[str]:
    """``validate_archive_members`` over a gzip tarball on disk, without extracting anything."""
    members: list[tuple[str, str]] = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if member.isfile():
                kind = "file"
            elif member.isdir():
                kind = "dir"
            elif member.issym():
                kind = "symlink"
            elif member.islnk():
                kind = "hardlink"
            else:
                kind = "special"
            members.append((member.name, kind))
    return validate_archive_members(members, file_root=file_root)


def resolve_recovery_provider(*sources: Mapping[str, str]) -> str:
    """``NATIVE`` or ``MANAGED`` (D-95) from the first source that sets the variable, defaulting
    from ``EREV_KEY_PROVIDER`` (``local`` → NATIVE, ``gcp`` → MANAGED); an explicit value that
    contradicts the key provider, or an unknown value, is a configuration error."""

    def lookup(name: str) -> str:
        for source in sources:
            value = source.get(name)
            if value:
                return value.strip()
        return ""

    key_provider = lookup("EREV_KEY_PROVIDER") or "local"
    implied = _PROVIDER_BY_KEYS.get(key_provider)
    if implied is None:
        raise PreflightError(
            f"EREV_KEY_PROVIDER is {key_provider}, which names no recovery provider"
        )
    explicit = lookup(RECOVERY_PROVIDER_NAME).upper()
    if not explicit:
        return implied
    if explicit not in RECOVERY_PROVIDERS:
        raise PreflightError(f"{RECOVERY_PROVIDER_NAME} must be NATIVE or MANAGED (D-95)")
    if explicit != implied:
        raise PreflightError(
            f"{RECOVERY_PROVIDER_NAME}={explicit} contradicts EREV_KEY_PROVIDER={key_provider} "
            f"(D-95: local → NATIVE, gcp → MANAGED)"
        )
    return explicit


MANAGED_NATIVE_REFUSAL: Final = (
    "recovery provider MANAGED (D-95): the backup is Cloud SQL's automated backup and PITR and the "
    "drill is a clone into the restore-test instance verified by erev verify; make backup and "
    "make restore-verify are the NATIVE path (self-hosted, where a provisioner can grant BYPASSRLS)"
)


def effective_key_mismatches(
    environ: Mapping[str, str], file_values: Mapping[str, str]
) -> list[str]:
    """Why the ``.env`` copy would not carry the keys the verification used (R4): a master key
    set in the environment that differs from the file, a key the file lacks or that is not 64
    hex characters, or a recovery provider other than NATIVE (D-95). Names only, never values."""
    findings: list[str] = []
    try:
        provider = resolve_recovery_provider(environ, file_values)
    except PreflightError as error:
        return [str(error)]
    if provider != NATIVE:
        findings.append(MANAGED_NATIVE_REFUSAL)
    for name in MASTER_KEY_NAMES:
        in_file = file_values.get(name, "")
        if not SHA256_HEX.fullmatch(in_file.lower()) or len(in_file) != 64:
            findings.append(f"{name} in the .env copy is missing or not 64 hex characters")
            continue
        override = environ.get(name)
        if override is not None and override != in_file:
            findings.append(
                f"effective {name} (environment) differs from the .env copy that would be restored"
            )
    return findings


def _parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    if RFC3339.fullmatch(value) is None:
        # R7 residuals: an instant without an offset is ambiguous and therefore corrupt (never read
        # as UTC); a week date, ordinal date or other ISO 8601 form outside RFC 3339 is refused.
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _seconds(later: datetime | None, earlier: datetime | None) -> int | None:
    if later is None or earlier is None:
        return None
    return int((later - earlier).total_seconds())


def restore_measurements(
    *,
    manifest: Mapping[str, Any],
    verify_document: Mapping[str, Any],
    now: datetime,
    drill_seconds: int | None,
    phase_seconds: Mapping[str, int | None],
) -> dict[str, Any]:
    """The RPO/RTO record of a restore drill (R7; OPR-12).

    The restore point is the dump's ``snapshot_started_at`` (pg_dump's snapshot is taken at start;
    the manifest instant is written after archiving and is never the restore point). Recovered
    evidence freshness comes from the restored data only (``verify_document.latest_evidence_at``
    excludes the verifier's own events); a negative lag is reported as such, never clamped. The
    drill's wall time is the sum of its phases; a cutover RTO is not measured by a drill.
    """
    restore_point = _parse_instant(manifest.get("snapshot_started_at"))
    snapshot_finished = _parse_instant(manifest.get("snapshot_finished_at"))
    manifest_at = _parse_instant(manifest.get("created_at"))
    if restore_point is None or snapshot_finished is None or manifest_at is None:
        # R7 residual: a later manifest instant is never a conservative replacement for a missing
        # or corrupt snapshot instant; the record cannot be computed.
        raise PreflightError(
            "manifest snapshot_started_at, snapshot_finished_at and created_at must all be RFC "
            "3339 instants with an offset; the restore point cannot be substituted"
        )
    if not restore_point <= snapshot_finished <= manifest_at:
        raise PreflightError(
            "manifest instants are out of order (snapshot_started_at <= snapshot_finished_at <= "
            "created_at)"
        )
    basis = "snapshot_started_at"
    latest_evidence = _parse_instant(verify_document.get("latest_evidence_at"))
    lag = _seconds(restore_point, latest_evidence)
    components = [phase_seconds.get(k) for k in ("restore", "migrate", "doctor", "verify")]
    known = [c for c in components if c is not None]
    return {
        "restore_point": _rfc3339(restore_point),
        "restore_point_basis": basis,
        "snapshot_started_at": manifest.get("snapshot_started_at"),
        "snapshot_finished_at": manifest.get("snapshot_finished_at"),
        "snapshot_duration_seconds": _seconds(snapshot_finished, restore_point),
        "manifest_created_at": manifest.get("created_at"),
        "archive_after_snapshot_seconds": _seconds(manifest_at, snapshot_finished),
        "measured_at": _rfc3339(now),
        "recovery_age_seconds": _seconds(now, restore_point),
        "latest_recovered_evidence_at": verify_document.get("latest_evidence_at"),
        "evidence_lag_seconds": lag,
        "evidence_after_restore_point": None if lag is None else lag < 0,
        "verifier_events_excluded": verify_document.get("verifier_events_appended"),
        "drill_duration_seconds": drill_seconds,
        "restore_component_seconds": sum(known) if known else None,
        "phase_seconds": dict(phase_seconds),
        "cutover_rto_seconds": None,
        "cutover_rto_note": (
            "a drill restores into an isolated clone and performs no cutover; the hosted RTO of "
            "OPR-08 is measured in the annual DR exercise (RB-06)"
        ),
    }


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
