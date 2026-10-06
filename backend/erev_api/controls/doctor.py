"""Deployment self-check ``erev doctor`` (03 REQ-CTL-005; dev-guide DG-MK-doctor; 05 RB-03;
BUILD_SPEC PLF-30).

Six checks, each printed as one line ``OK <check>: <summary>``, or as one
``FAIL <check>: <finding>`` line per finding:

- ``row-level-security``: every tenant table has forced row level security and a policy
  (04 DB-14 (a) and (c));
- ``app-role``: ``erev_app`` has neither SUPERUSER nor BYPASSRLS (DB-14 (d));
- ``immutability-triggers``: every trigger in schema erev is enabled, and every IM-A table and its
  partitions carry their DB-01 triggers (DB-14 (g));
- ``audit-chain``: the latest ``audit_chain_verification`` of every tenant is ``PASS``;
- ``ai``: AI is off unless ``ai.enabled`` resolves true (D-46);
- ``setting-references``: no schema ``erev`` function references a ``current_setting`` name
  outside the 04 list (05 REL-07). ``erev doctor --analyze <tables>`` runs ``ANALYZE`` on
  schema-``erev`` tables as ``erev_owner`` instead of the checks (05 PERF-27; ``analyze_tables``).

The catalogue checks run as ``erev_app`` through an identity session; the tenant checks read the
tenant directory and then one read-only tenant session per tenant.

Under ``EREV_ENV=production`` the 05 SAR-40 production checks follow (BUILD_SPEC SOP-6): pure
predicates over ``ProductionObservations`` collected once by ``collect_production_observations``
through injected collectors, applied by ``production_checks`` and appended by ``run_doctor`` when
observations are passed. Each prints ``OK``, ``FAIL`` per finding, or ``WARN`` per warning
(exit 0). Their names and rules are the runbook RB-03 "Production checks" table.
"""

from __future__ import annotations

import calendar
import dataclasses
import importlib
import importlib.util
import ipaddress
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import Connection, Engine, select, text

from erev_api.config import LOOPBACK_ORIGIN_HOSTS, Environment, Settings
from erev_api.controls.release import MANIFEST_PATH, git_build_sha, release_facts
from erev_api.db import index_conditions as db_index_conditions
from erev_api.db import tables as db_tables
from erev_api.db.lint import GLOBAL_TABLES, catalogue_connection, run_lint
from erev_api.db.migration_ops import PARTITION_COLUMNS, SCHEMA, qualified
from erev_api.db.session import APP_ROLE, DbContext, platform_session, tenant_session
from erev_api.db.tables import audit_chain_verification, tenant
from erev_api.db.tables.platform import registry_parameter
from erev_api.enums import ControlResult, TenantStatus
from erev_api.registry.resolve import setting

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.clock import Clock

ROW_LEVEL_SECURITY: Final = "row-level-security"
APP_ROLE_CHECK: Final = "app-role"
IMMUTABILITY_TRIGGERS: Final = "immutability-triggers"
AUDIT_CHAIN: Final = "audit-chain"
AI: Final = "ai"
SETTING_REFERENCES: Final = "setting-references"
CHECK_NAMES: Final = (
    ROW_LEVEL_SECURITY,
    APP_ROLE_CHECK,
    IMMUTABILITY_TRIGGERS,
    AUDIT_CHAIN,
    AI,
    SETTING_REFERENCES,
)
# 04 §14 names these session settings (DB-14 helpers, RLS policies, DB-15, the REL-07 data-fix
# ticket); 05 REL-07: no function may reference another.
DOCUMENTED_SETTINGS: Final = frozenset(
    {
        "app.tenant_id",
        "app.user_id",
        "app.entity_scope",
        "app.platform_scope",
        "app.data_fix_ticket",
    }
)
AI_ENABLED: Final = "ai.enabled"
# [J] SPEC-Q-195: the daily verification runs at 02:00 UTC with up to 3 attempts (runbook "Chain
# verification"), so an ACTIVE tenant younger than one cycle plus two hours may have none yet.
FIRST_VERIFICATION_GRACE: Final = timedelta(hours=26)

_TENANT_TABLES = text(
    """
    SELECT count(*)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'erev' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
      AND EXISTS (SELECT 1 FROM pg_attribute a
                  WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped)
      AND c.relname <> ALL(:global_tables)
    """
)
# pg_trigger.tgenabled: O fires in origin and local sessions, A always, R only in replica sessions,
# D never.
_TRIGGERS = text(
    """
    SELECT t.tgname, c.relname, c.relispartition, t.tgenabled
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'erev' AND NOT t.tgisinternal
    ORDER BY t.tgname, c.relname
    """
)
_NOT_FIRING: Final = {"D": "is disabled", "R": "fires only in replica sessions"}


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One check: ``OK`` with its summary, ``FAIL`` per finding, or ``WARN`` per warning (a
    warning keeps ``ok`` true; 05 SAR-40 exit 0)."""

    check: str
    summary: str
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures

    def lines(self) -> list[str]:
        if self.failures:
            return [f"FAIL {self.check}: {failure}" for failure in self.failures]
        if self.warnings:
            return [f"WARN {self.check}: {warning}" for warning in self.warnings]
        return [f"OK {self.check}: {self.summary}"]


@dataclass(frozen=True, slots=True)
class _Tenant:
    id: UUID
    code: str
    status: str
    created_at: datetime
    ai_disabled_at: datetime | None


def _lint_failures(connection: Connection, checks: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        f"{finding.object_name}: {finding.message}"
        for finding in run_lint(connection, checks=checks)
    )


def row_level_security(connection: Connection) -> CheckResult:
    count = connection.execute(
        _TENANT_TABLES, {"global_tables": sorted(GLOBAL_TABLES)}
    ).scalar_one()
    return CheckResult(
        ROW_LEVEL_SECURITY,
        f"{count} tenant tables have forced row level security and a policy",
        _lint_failures(connection, ("a", "c")),
    )


def app_role(connection: Connection) -> CheckResult:
    return CheckResult(
        APP_ROLE_CHECK,
        f"{APP_ROLE} has neither SUPERUSER nor BYPASSRLS",
        _lint_failures(connection, ("d",)),
    )


def immutability_triggers(connection: Connection) -> CheckResult:
    failures: list[str] = []
    partitions: dict[tuple[str, str], int] = {}
    enabled = 0
    for name, table, is_partition, state in connection.execute(_TRIGGERS):
        problem = _NOT_FIRING.get(str(state))
        if problem is None:
            enabled += 1
        elif is_partition:
            partitions[(name, problem)] = partitions.get((name, problem), 0) + 1
        else:
            failures.append(f"trigger {name} on {table} {problem}")
    failures += [
        f"trigger {name} {problem} on {count} partitions"
        for (name, problem), count in sorted(partitions.items())
    ]
    failures += _lint_failures(connection, ("g",))
    return CheckResult(
        IMMUTABILITY_TRIGGERS,
        f"{enabled} triggers enabled; every IM-A table carries its DB-01 triggers",
        tuple(failures),
    )


def _tenants(*, keyring: KeyRing, request_id: str) -> list[_Tenant]:
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=request_id, keyring=keyring
    ) as session:
        rows = session.execute(
            select(
                tenant.c.id,
                tenant.c.code,
                tenant.c.status,
                tenant.c.created_at,
                tenant.c.ai_disabled_at,
            ).order_by(tenant.c.code)
        ).all()
    return [_Tenant(*row) for row in rows]


def _latest_verification(connection: Connection) -> Any:
    return connection.execute(
        select(audit_chain_verification.c.result, audit_chain_verification.c.first_failure_seq)
        .order_by(
            audit_chain_verification.c.finished_at.desc(),
            audit_chain_verification.c.to_chain_seq.desc(),
        )
        .limit(1)
    ).one_or_none()


def audit_chain(tenants: Sequence[_Tenant], *, now: datetime) -> CheckResult:
    failures: list[str] = []
    passed = awaiting = 0
    for workspace in tenants:
        ctx = DbContext(tenant_id=workspace.id, user_id=None, entity_scope="*")
        with tenant_session(ctx, read_only=True) as session:
            latest = _latest_verification(session.connection())
        if latest is None:
            overdue = now - workspace.created_at > FIRST_VERIFICATION_GRACE
            if workspace.status == TenantStatus.ACTIVE.value and overdue:
                failures.append(f"tenant {workspace.code} has no audit chain verification")
            else:
                awaiting += 1
        elif latest.result == ControlResult.PASS.value:
            passed += 1
        else:
            first = (
                ""
                if latest.first_failure_seq is None
                else f" from sequence {latest.first_failure_seq}"
            )
            failures.append(
                f"tenant {workspace.code}: latest audit chain verification is "
                f"{latest.result}{first}"
            )
    summary = f"latest verification PASS for {passed} of {len(tenants)} tenants"
    if awaiting:
        summary += f"; {awaiting} awaiting their first verification"
    return CheckResult(AUDIT_CHAIN, summary, tuple(failures))


def ai(
    connection: Connection, tenants: Sequence[_Tenant], *, now: datetime, kill_switch: bool
) -> CheckResult:
    failures: list[str] = []
    defaults = connection.execute(
        select(registry_parameter.c.default_asc606, registry_parameter.c.default_ifrs15).where(
            registry_parameter.c.code == AI_ENABLED
        )
    ).one_or_none()
    if defaults is None:
        failures.append(f"registry parameter {AI_ENABLED} is missing")
    elif defaults.default_asc606 is not False or defaults.default_ifrs15 not in (None, False):
        failures.append(f"registry parameter {AI_ENABLED} does not default to false")
    enabled = 0
    for workspace in tenants:
        ctx = DbContext(tenant_id=workspace.id, user_id=None, entity_scope="*")
        with tenant_session(ctx, read_only=True) as session:
            value = setting(session, AI_ENABLED, known_at=now)
        if not isinstance(value, bool):
            failures.append(f"tenant {workspace.code}: {AI_ENABLED} does not resolve to a boolean")
        elif value and workspace.ai_disabled_at is None and not kill_switch:
            enabled += 1
    summary = f"{AI_ENABLED} defaults to false; AI enabled for {enabled} of {len(tenants)} tenants"
    if kill_switch:
        summary += "; EREV_AI_KILL_SWITCH is on"
    return CheckResult(AI, summary, tuple(failures))


# ---- 05 REL-07: setting references of the schema-erev functions ---------------------------------

_FUNCTION_SOURCES = text(
    """
    SELECT format('%I(%s)', p.proname, pg_get_function_identity_arguments(p.oid)), p.prosrc
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'erev'
    ORDER BY 1
    """
)
_SETTING_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
UNPARSABLE_SETTING: Final = "<unparsable>"
UNRESOLVED_SETTING: Final = "<unresolved>"
# Codex P4C-S6-R1: references are found on the SQL token stream, not by substring. The lexer knows
# PostgreSQL comments (-- and nested /* */), '…' strings with doubled quotes, E'…' strings with
# backslash escapes, $tag$…$tag$ strings, "quoted identifiers" (case kept) and bare identifiers
# (case folded); a call's first argument is taken by argument boundary.
_BARE_IDENTIFIER: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_DOLLAR_TAG: Final = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
_OPENERS: Final = frozenset("([")
_CLOSERS: Final = frozenset(")]")


@dataclass(frozen=True, slots=True)
class FunctionSettingReferences:
    """One schema-``erev`` function and the ``current_setting`` names its source references."""

    function: str
    settings: tuple[str, ...]


def _sql_tokens(source: str) -> list[tuple[str, str]]:
    """``(kind, text)`` tokens of a function source: ``string`` (literal content), ``ident``
    (quoted identifiers exact, bare identifiers lower-cased) and ``punct`` (one character);
    whitespace and comments are dropped."""
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
        elif source.startswith("--", i):
            end = source.find("\n", i)
            i = n if end < 0 else end + 1
        elif source.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if source.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif source.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
        elif ch == "'" or (ch in "eE" and source.startswith("'", i + 1)):
            escapes = ch != "'"
            i += 2 if escapes else 1
            parts: list[str] = []
            while i < n:
                c = source[i]
                if escapes and c == "\\" and i + 1 < n:
                    decoded, i = _e_escape(source, i + 1)
                    parts.append(decoded)
                elif c == "'":
                    if source.startswith("'", i + 1):
                        parts.append("'")
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    parts.append(c)
                    i += 1
            tokens.append(("string", "".join(parts)))
        elif ch == "$" and (tag := _DOLLAR_TAG.match(source, i)) is not None:
            end = source.find(tag.group(0), tag.end())
            tokens.append(("string", source[tag.end() : n if end < 0 else end]))
            i = n if end < 0 else end + len(tag.group(0))
        elif ch == '"':
            i += 1
            parts = []
            while i < n:
                c = source[i]
                if c == '"':
                    if source.startswith('"', i + 1):
                        parts.append('"')
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    parts.append(c)
                    i += 1
            tokens.append(("ident", "".join(parts)))
        elif (word := _BARE_IDENTIFIER.match(source, i)) is not None:
            tokens.append(("ident", word.group(0).lower()))
            i = word.end()
        else:
            tokens.append(("punct", ch))
            i += 1
    return tokens


_E_SIMPLE: Final[Mapping[str, str]] = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
_E_NUMERIC: Final[Mapping[str, tuple[int, int]]] = {"x": (2, 16), "u": (4, 16), "U": (8, 16)}


def _e_escape(source: str, i: int) -> tuple[str, int]:
    """Decode the E'…' escape starting at ``source[i]`` (the character after the backslash) per the
    PostgreSQL lexer: ``\\n``-style, ``\\xhh``, ``\\ooo``, ``\\uxxxx``, ``\\Uxxxxxxxx``; a malformed
    escape keeps its character. Returns the decoded text and the index after the escape."""
    char = source[i]
    if char in _E_SIMPLE:
        return _E_SIMPLE[char], i + 1
    if char in "01234567":
        digits = 1
        while digits < 3 and i + digits < len(source) and source[i + digits] in "01234567":
            digits += 1
        return chr(int(source[i : i + digits], 8)), i + digits
    if char in _E_NUMERIC:
        width, base = _E_NUMERIC[char]
        digits = 0
        while (
            digits < width
            and i + 1 + digits < len(source)
            and source[i + 1 + digits] in ("0123456789abcdefABCDEF")
        ):
            digits += 1
        if digits:
            try:
                return chr(int(source[i + 1 : i + 1 + digits], base)), i + 1 + digits
            except ValueError:
                return char, i + 1
        return char, i + 1
    return char, i + 1


def referenced_settings(source: str) -> tuple[str, ...]:
    """The distinct settings a function source passes to ``current_setting``, sorted, from the SQL
    token stream (Codex P4C-S6-R1). A call whose first argument is one string literal yields the
    literal: the name when identifier-shaped, else ``<unparsable>`` (never echoed, Codex P4B-R1).
    A call whose first argument is anything else — an expression, a variable, a nested call,
    nothing — yields ``<unresolved>``: it can never establish "only documented settings". Text in
    comments and inside strings is not a reference; a differently spelled quoted identifier is
    another function."""
    tokens = _sql_tokens(source)
    names: set[str] = set()
    i = 0
    while i < len(tokens):
        kind, text_ = tokens[i]
        if (
            kind == "ident"
            and text_ == "current_setting"
            and tokens[i + 1 : i + 2] == [("punct", "(")]
        ):
            depth, j = 0, i + 2
            argument: list[tuple[str, str]] = []
            while j < len(tokens):
                token_kind, token_text = tokens[j]
                if token_kind == "punct" and token_text in _OPENERS:
                    depth += 1
                elif token_kind == "punct" and token_text in _CLOSERS:
                    if depth == 0:
                        break
                    depth -= 1
                elif token_kind == "punct" and token_text == "," and depth == 0:
                    break
                argument.append(tokens[j])
                j += 1
            if len(argument) == 1 and argument[0][0] == "string":
                literal = argument[0][1]
                names.add(literal if _SETTING_NAME.fullmatch(literal) else UNPARSABLE_SETTING)
            else:
                names.add(UNRESOLVED_SETTING)
            i = j
        i += 1
    return tuple(sorted(names))


def observe_setting_references(connection: Connection) -> tuple[FunctionSettingReferences, ...]:
    """Every function of schema ``erev`` with its referenced settings, from ``pg_proc``."""
    return tuple(
        FunctionSettingReferences(str(name), referenced_settings(str(source or "")))
        for name, source in connection.execute(_FUNCTION_SOURCES)
    )


def setting_references(functions: Sequence[FunctionSettingReferences]) -> CheckResult:
    """05 REL-07: a function referencing a setting 04 does not list fails, naming both."""
    failures: list[str] = []
    for function in functions:
        for name in function.settings:
            if name == UNPARSABLE_SETTING:
                failures.append(
                    f"function {function.function} references a setting whose name is not "
                    "identifier-shaped (05 REL-07)"
                )
            elif name == UNRESOLVED_SETTING:
                failures.append(
                    f"function {function.function} passes current_setting an argument that is "
                    "not a single string literal (05 REL-07)"
                )
            elif name not in DOCUMENTED_SETTINGS:
                failures.append(
                    f"function {function.function} references setting {name}, which 04 does not "
                    "list (05 REL-07)"
                )
    return CheckResult(
        SETTING_REFERENCES,
        f"{len(functions)} functions reference only the documented app.* settings",
        tuple(failures),
    )


class UnknownTable(ValueError):
    """A name outside the schema-``erev`` allow-list. Safe to print: ``table`` is the caller's
    argument compared against the metadata, never text from an exception."""

    def __init__(self, table: str) -> None:
        super().__init__(f"unknown table {table}")
        self.table = table


class AnalyzeFailed(RuntimeError):
    """``ANALYZE`` stopped: the exception TYPE and the table position (1-based; 0 before the first
    statement), never the driver's message (Codex P4C-S6-R2; P4B-R1 rule)."""

    def __init__(self, *, index: int, count: int, exception_type: str) -> None:
        super().__init__(f"ANALYZE failed at table {index} of {count}: {exception_type}")
        self.index = index
        self.count = count
        self.exception_type = exception_type


def analyze_tables(engine: Engine, tables: Sequence[str]) -> int:
    """``ANALYZE`` the named schema-``erev`` tables through ``engine`` (``erev_owner``; 05 PERF-27,
    DG-MK-perf-seed step 4). Every name is validated against the metadata allow-list before the
    first statement (``UnknownTable``); an execution failure is ``AnalyzeFailed`` with type and
    position only. Returns the count."""
    known = {name.removeprefix(f"{SCHEMA}.") for name in db_tables.metadata.tables}
    for table in tables:
        if table not in known:
            raise UnknownTable(table)
    statements = [f"ANALYZE {qualified(table)}" for table in tables]
    position = 0
    try:
        with engine.begin() as connection:
            for statement in statements:
                position += 1
                connection.exec_driver_sql(statement)
    except Exception as exc:  # the driver's message is untrusted: type and position only
        raise AnalyzeFailed(
            index=position, count=len(tables), exception_type=type(exc).__name__
        ) from None
    return len(tables)


def run_doctor(
    *,
    clock: Clock,
    keyring: KeyRing,
    request_id: str,
    ai_kill_switch: bool,
    production: ProductionObservations | ProductionCollector | None = None,
) -> list[CheckResult]:
    """The six checks in ``CHECK_NAMES`` order, then the SAR-40 production checks when
    ``production`` is passed and ``EREV_ENV`` is ``production``: either ready observations or
    a ``ProductionCollector`` that receives the tenant directory read for ``audit-chain``, so
    one run records one ``PLATFORM_SCOPE_USED`` event (RB-03)."""
    now = clock.now()
    with catalogue_connection(request_id=request_id) as connection:
        results = [
            row_level_security(connection),
            app_role(connection),
            immutability_triggers(connection),
        ]
    tenants = _tenants(keyring=keyring, request_id=request_id)
    results.append(audit_chain(tenants, now=now))
    with catalogue_connection(request_id=request_id) as connection:
        results.append(ai(connection, tenants, now=now, kill_switch=ai_kill_switch))
        results.append(setting_references(observe_setting_references(connection)))
    if production is not None:
        observations = (
            production if isinstance(production, ProductionObservations) else production(tenants)
        )
        results += production_checks(observations, now=now)
    return results


# ---- 05 SAR-40 production checks (BUILD_SPEC SOP-6; runbook RB-03 "Production checks") --------
#
# Pure predicates over observations collected once per run. ``production_checks`` applies them only
# under ``EREV_ENV=production``; an observation the build cannot collect (``None``) fails its check
# closed, and a documented setting the build does not define yet prints WARN naming the pending
# lane. The database collectors (active connections, partition windows), the key-provider probe and
# the command wiring are later SOP-6 phases (docs/reviews/loop/prod/P4-doctor.md).

EMAIL_BACKEND: Final = "email-backend"
INTEGRATION_URLS: Final = "integration-urls"
CORS_ORIGINS: Final = "cors-origins"
SESSION_COOKIE: Final = "session-cookie"
DEFUSEDXML: Final = "defusedxml"
PARTITION_WINDOW: Final = "partition-window"
RELEASE_STAMP: Final = "release-stamp"
KEY_PROVIDER: Final = "key-provider"
KEY_VERSION_PIN: Final = "key-version-pin"
RECOVERY_PROVIDER: Final = "recovery-provider"
ANTHROPIC_KEY: Final = "anthropic-key"
OPERATOR_ALERTS: Final = "operator-alerts"  # 05 OPR-24, CFG-31, SAR-40 rev 1.27
LOCK_BUDGET: Final = "lock-budget"  # 05 §2.7, SAR-40 rev 1.53
MASTER_KEYS: Final = "master-keys"  # 05 CFG-26, SAR-40 rev 1.53
INDEX_CONDITIONS: Final = "index-conditions"  # 05 §2.7, SAR-40 rev 1.156; 04 NC-20
PRODUCTION_CHECK_NAMES: Final = (
    EMAIL_BACKEND,
    INTEGRATION_URLS,
    CORS_ORIGINS,
    SESSION_COOKIE,
    DEFUSEDXML,
    PARTITION_WINDOW,
    RELEASE_STAMP,
    KEY_PROVIDER,
    KEY_VERSION_PIN,
    RECOVERY_PROVIDER,
    ANTHROPIC_KEY,
    OPERATOR_ALERTS,
    LOCK_BUDGET,
    MASTER_KEYS,
    INDEX_CONDITIONS,
)
# 05 SAR-40 rev 1.53 (R-34 SD-5, SD-6): the checks a production api or worker also evaluates on its
# own settings when it starts, and refuses to start on (``controls.startup``). Configuration only:
# a check over tenant data never decides whether a process starts.
STARTUP_CHECK_NAMES: Final = (EMAIL_BACKEND, MASTER_KEYS)
# 05 SAR-40 rev 1.53 (ruling R-39): what `email-backend` prints as WARN while the operator's
# opt-in for a relay on a private-use or loopback address is on (SAR-15, CFG-18).
PRIVATE_RELAY_NOTICE: Final = (
    "EREV_SMTP_PRIVATE_RELAY is on: the SMTP relay may be on a private or loopback address "
    "(05 SAR-15, CFG-18)"
)
# Documented names a build may not define yet: 05 KEY-03 (lane P2) and CFG-30 (lane P6).
SECURITY_HMAC_SECRET_VERSION_NAME: Final = "EREV_SECURITY_HMAC_SECRET_VERSION"
RECOVERY_PROVIDER_NAME: Final = "EREV_RECOVERY_PROVIDER"
BACKUP_URL_NAME: Final = "EREV_BACKUP_URL"
RESTORE_ADMIN_URL_NAME: Final = "EREV_RESTORE_ADMIN_URL"
PENDING_LANES: Final[Mapping[str, str]] = {
    SECURITY_HMAC_SECRET_VERSION_NAME: "P2",
    RECOVERY_PROVIDER_NAME: "P6",
}
# (Settings field, documented variable) pairs ``snapshot_settings`` reads by value or as set/unset.
_DOCUMENTED_FIELDS: Final = (
    ("security_hmac_secret_version", SECURITY_HMAC_SECRET_VERSION_NAME),
    ("recovery_provider", RECOVERY_PROVIDER_NAME),
)
# A build also defines a documented variable when the owning lane's module exists: lane P6 resolves
# CFG-30 in ``controls/recovery_preflight.py`` from the environment, not through ``Settings``.
_DEFINING_MODULES: Final[Mapping[str, str]] = {
    RECOVERY_PROVIDER_NAME: "erev_api.controls.recovery_preflight",
}
_RECOVERY_URL_FIELDS: Final = (
    ("backup_url", BACKUP_URL_NAME),
    ("restore_admin_url", RESTORE_ADMIN_URL_NAME),
)
NATIVE: Final = "NATIVE"
MANAGED: Final = "MANAGED"
RECOVERY_PROVIDERS: Final = (NATIVE, MANAGED)
# 05 CFG-30 (D-95): the recovery provider defaults from the key provider.
RECOVERY_PROVIDER_OF_KEY_PROVIDER: Final[Mapping[str, str]] = {"local": NATIVE, "gcp": MANAGED}
PARTITION_HORIZON_MONTHS: Final = 12
# 05 §2.7: the connection rule keeps the sessions of a deployment under 80% of max_connections, and
# the lock rule lets every one of them hold the whole partition lock footprint at once.
LOCK_SESSION_SHARE: Final = (4, 5)
# An origin on one of these hosts is this machine's own: no user's browser reaches it.
LOOPBACK_HOSTS: Final = LOOPBACK_ORIGIN_HOSTS
LOCAL_NAME_SUFFIXES: Final = (".localhost", ".local", ".internal")
SECURITY_HMAC_PURPOSE: Final = "security-hmac"
NOT_COLLECTED: Final = "was not collected; the SOP-6 collector is pending"
# 05 KEY-03: the pin and the provider's current key id carry ASCII-digit versions (Codex P4-R4:
# ``str.isdigit`` accepts "²", which ``int`` refuses); 7 digits bound the P2 range of 1..1,000,000.
_PIN_TEXT: Final = re.compile(r"[0-9]{1,7}")
_SECURITY_HMAC_KEY_ID: Final = re.compile(rf"{SECURITY_HMAC_PURPOSE}:([0-9]{{1,7}})")
INVALID_PIN: Final = (
    f"{SECURITY_HMAC_SECRET_VERSION_NAME} must be a positive integer version number of at most 7 "
    "ASCII digits"
)


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    """The non-secret settings the production checks read (05 CFG-01, -09, -10, -11, -13, -17,
    -30; KEY-03, KEY-10). Recovery URLs appear as set or unset only, never by value."""

    env: Environment
    email_backend: str
    cors_origins: tuple[str, ...]
    public_origin: str
    ai_provider: str
    anthropic_api_key_set: bool
    key_provider: str
    gcp_project_set: bool
    gcp_kms_kek_set: bool
    security_hmac_secret_version: str | None = None
    recovery_provider: str | None = None
    backup_url_set: bool = False
    restore_admin_url_set: bool = False
    operator_alert_email_set: bool = False  # CFG-31, as set or unset only
    operator_alert_delivery: str | None = None  # CFG-31 `log-only` acknowledgement
    smtp_host_set: bool = False  # CFG-18, as set or unset only
    smtp_from_set: bool = False
    smtp_private_relay: bool = False  # CFG-18 rev 1.53: the operator's private-relay opt-in
    # CFG-18: why EREV_SMTP_CA_FILE is unfit (the variable name only, never the path).
    smtp_ca_findings: tuple[str, ...] = ()
    # CFG-26: why the master keys are unfit for production (variable names only, never a value).
    master_key_findings: tuple[str, ...] = ()
    # Documented variables this build's ``Settings`` does not define (pending lane merges).
    undefined: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class IntegrationConnectionObservation:
    """One T-INT-01 row as the check reads it; ``base_url`` is non-secret (04 T-INT-01)."""

    tenant_code: str
    code: str
    status: str
    base_url: str | None


@dataclass(frozen=True, slots=True)
class PartitionWindowObservation:
    """``ends_on`` is the exclusive upper bound of the last bounded partition of ``table``
    (04 §1.6); None when the table has no bounded partition."""

    table: str
    ends_on: date | None


@dataclass(frozen=True, slots=True)
class LockBudgetObservation:
    """What the 05 §2.7 lock rule reads: the server's three lock-table settings and two catalogue
    counts. ``partition_lock_footprint`` is the number of relations one statement locks when it
    reads every partitioned table of schema erev without a value for the partition column: per
    table 1 + the parent's indexes + partitions × (1 + indexes per partition). ``relations`` is
    every relation of the database outside the system schemas (one DDL, dump or restore
    transaction may hold each once)."""

    max_locks_per_transaction: int
    max_connections: int
    max_prepared_transactions: int
    partition_lock_footprint: int
    relations: int


@dataclass(frozen=True, slots=True)
class IndexConditionsObservation:
    """What the catalogue check of ``db.index_conditions`` answers on this schema (05 §2.7; 04
    NC-20 and §1.4): ``findings`` in the module's own words — an index of a table with a policy
    whose key the policy cannot use and that the list does not name, or an entry of the list
    whose index has no finding — and ``listed``, the length of that list."""

    findings: tuple[str, ...]
    listed: int


@dataclass(frozen=True, slots=True)
class ReleaseObservation:
    """The REL-03 release facts; ``error`` carries the manifest problem, if any."""

    manifest_present: bool
    build_sha: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    """Key provider identity and probe result (05 CFG-11, CFG-13); ``security_hmac_key_id`` is
    the provider's current KEY-03 key id, when it reports one."""

    kind: str
    identity: str
    healthy: bool
    security_hmac_key_id: str | None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where and when one ``ProductionObservations`` member was collected; ``error`` says why
    it is None (a collector failure, or a collector this build cannot compose)."""

    member: str
    source: str
    collected_at: datetime
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ProductionObservations:
    """Everything the production checks read, collected once; None means not collected."""

    settings: SettingsSnapshot
    defusedxml: bool | None = None
    anthropic_key_resolves: bool | None = None
    integration_connections: tuple[IntegrationConnectionObservation, ...] | None = None
    partition_windows: tuple[PartitionWindowObservation, ...] | None = None
    release: ReleaseObservation | None = None
    provider: ProviderObservation | None = None
    lock_budget: LockBudgetObservation | None = None
    index_conditions: IndexConditionsObservation | None = None
    provenance: tuple[Provenance, ...] = ()


# Code-owned reasons a collector cannot run on this build: the only free-form text a FAIL line ever
# carries verbatim (Codex P4B-R1 ruling: everything else renders as exception type plus attempt).
PENDING_KEY_ID_ACCESSOR: Final = (
    "KeyRing.current_security_key_id() is not on this build (lane P2 pending); the current "
    "security-hmac key id cannot be collected"
)
PENDING_INTEGRATION_TABLE: Final = (
    "T-INT-01 integration_connection is not on this build (INT lane pending)"
)
PENDING_REASONS: Final = frozenset({PENDING_KEY_ID_ACCESSOR, PENDING_INTEGRATION_TABLE})


class CollectorPending(RuntimeError):
    """This build lacks what the collector needs (a table, module or accessor of a pending
    lane); the observation is not collected and its check fails closed. ``reason`` must be one of
    ``PENDING_REASONS``, so nothing external can ride the verbatim path."""

    def __init__(self, reason: str) -> None:
        if reason not in PENDING_REASONS:
            raise ValueError("CollectorPending takes a code-owned reason from PENDING_REASONS")
        super().__init__(reason)
        self.reason = reason


def snapshot_settings(
    settings: Settings, environ: Mapping[str, str] | None = None
) -> SettingsSnapshot:
    """The non-secret observation of ``settings`` the production checks read.

    A documented variable is read from the ``Settings`` field when the build defines one, else
    from ``environ`` when the owning lane's module defines it outside ``Settings``
    (``_DEFINING_MODULES``). A variable this build defines neither way (lane P2's KEY-03 pin,
    lane P6's CFG-30 provider before their merges) is listed in ``undefined`` and its value is
    never read, so a supplied environment value cannot hide the pending status (Codex P4-R2). The
    recovery URLs are observed as set or unset only.
    """
    fields = Settings.model_fields
    values = dict(environ or {})
    undefined: set[str] = set()

    def documented(field: str, name: str) -> str | None:
        if field in fields:
            value = getattr(settings, field)
            return None if value is None else str(value)
        module = _DEFINING_MODULES.get(name)
        if module is None or importlib.util.find_spec(module) is None:
            undefined.add(name)
            return None
        raw = values.get(name, "").strip()
        return raw or None

    def url_set(field: str, name: str) -> bool:
        if field in fields:
            return getattr(settings, field) is not None
        return bool(values.get(name, "").strip())

    return SettingsSnapshot(
        env=settings.env,
        email_backend=settings.email_backend,
        cors_origins=tuple(settings.cors_origins),
        public_origin=settings.public_origin,
        ai_provider=settings.ai_provider,
        anthropic_api_key_set=settings.anthropic_api_key is not None,
        key_provider=settings.key_provider,
        gcp_project_set=settings.gcp_project is not None,
        gcp_kms_kek_set=settings.gcp_kms_kek is not None,
        security_hmac_secret_version=documented(*_DOCUMENTED_FIELDS[0]),
        recovery_provider=documented(*_DOCUMENTED_FIELDS[1]),
        backup_url_set=url_set(*_RECOVERY_URL_FIELDS[0]),
        restore_admin_url_set=url_set(*_RECOVERY_URL_FIELDS[1]),
        operator_alert_email_set=settings.operator_alert_email is not None,
        operator_alert_delivery=settings.operator_alert_delivery,
        smtp_host_set=settings.smtp_host is not None,
        smtp_from_set=settings.smtp_from is not None,
        smtp_private_relay=settings.smtp_private_relay,
        smtp_ca_findings=settings.smtp_ca_findings(),
        master_key_findings=settings.master_key_findings(),
        undefined=frozenset(undefined),
    )


def _host_of(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def private_url_reason(url: str) -> str | None:
    """Why ``url`` is a loopback or private base URL (05 SAR-40), or None when it is public."""
    host = _host_of(url)
    if not host:
        return "has no host"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        name = host.lower().rstrip(".")
        if name == "localhost" or name.endswith(LOCAL_NAME_SUFFIXES):
            return "is a local name"
        return "is a single-label host name" if "." not in name else None
    if address.is_loopback:
        return "is a loopback address"
    if address.is_link_local:
        return "is a link-local address"
    if address.is_unspecified:
        return "is an unspecified address"
    return "is a private address" if address.is_private else None


def _uncollected(check: str, observation: str) -> CheckResult:
    return CheckResult(check, "", (f"{observation} {NOT_COLLECTED}",))


def _undefined_warning(check: str, name: str) -> CheckResult:
    """RB-03: a setting this build does not define prints WARN naming the pending lane instead of
    a result; nothing supplied for it is read (Codex P4-R2)."""
    lane = PENDING_LANES[name]
    return CheckResult(
        check,
        "",
        warnings=(f"{name} is not defined by this build (pending lane {lane} merge); not checked",),
    )


def email_backend(snapshot: SettingsSnapshot) -> CheckResult:
    """05 CFG-17, CFG-18: production sends its mail. ``fake`` writes files nobody reads, and
    ``smtp`` without a host or a sender address, or with a certificate bundle that cannot be
    read, fails every send. The operator's private-relay opt-in is a warning: the check stays
    ok and the line says that the opt-in is on (SAR-15 rev 1.53; ruling R-39)."""
    if snapshot.email_backend == "fake":
        return CheckResult(
            EMAIL_BACKEND,
            "",
            ("EREV_EMAIL_BACKEND is fake; production requires smtp (05 CFG-17, SAR-40)",),
        )
    missing = [
        name
        for name, is_set in (
            ("EREV_SMTP_HOST", snapshot.smtp_host_set),
            ("EREV_SMTP_FROM", snapshot.smtp_from_set),
        )
        if not is_set
    ]
    if missing:
        return CheckResult(
            EMAIL_BACKEND,
            "",
            (
                f"EREV_EMAIL_BACKEND is {snapshot.email_backend} and {' and '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} not set (05 CFG-18, SAR-40)",
            ),
        )
    if snapshot.smtp_ca_findings:
        return CheckResult(EMAIL_BACKEND, "", snapshot.smtp_ca_findings)
    summary = f"EREV_EMAIL_BACKEND is {snapshot.email_backend}"
    if snapshot.smtp_private_relay:
        return CheckResult(EMAIL_BACKEND, summary, warnings=(PRIVATE_RELAY_NOTICE,))
    return CheckResult(EMAIL_BACKEND, summary)


def master_keys(snapshot: SettingsSnapshot) -> CheckResult:
    """05 CFG-26 (rev 1.53): under the local key provider the three master keys differ and none
    is a placeholder. The findings come from ``Settings.master_key_findings``."""
    if snapshot.key_provider != "local":
        return CheckResult(
            MASTER_KEYS,
            f"EREV_KEY_PROVIDER is {snapshot.key_provider}; the CFG-26 master keys are not used",
        )
    return CheckResult(
        MASTER_KEYS,
        "the three CFG-26 master keys differ and none is a placeholder",
        snapshot.master_key_findings,
    )


def integration_urls(
    connections: Sequence[IntegrationConnectionObservation] | None,
) -> CheckResult:
    if connections is None:
        return _uncollected(INTEGRATION_URLS, "the active integration connections")
    failures: list[str] = []
    active = 0
    for connection in connections:
        if connection.status != "ACTIVE":
            continue
        active += 1
        if connection.base_url is None:
            continue
        reason = private_url_reason(connection.base_url)
        if reason is None:
            continue
        host = _host_of(connection.base_url)
        what = "base URL has no host" if host is None else f"base URL host {host} {reason}"
        failures.append(
            f"connection {connection.code} of tenant {connection.tenant_code}: {what} (05 SAR-40)"
        )
    return CheckResult(
        INTEGRATION_URLS,
        f"{active} active integration connections have public or no base URLs",
        tuple(failures),
    )


def cors_origins(snapshot: SettingsSnapshot) -> CheckResult:
    if any("*" in origin for origin in snapshot.cors_origins):
        return CheckResult(
            CORS_ORIGINS, "", ("EREV_CORS_ORIGINS contains a wildcard origin (05 SAR-12)",)
        )
    if not snapshot.cors_origins:
        return CheckResult(CORS_ORIGINS, "CORS is disabled (EREV_CORS_ORIGINS is empty)")
    count = len(snapshot.cors_origins)
    return CheckResult(CORS_ORIGINS, f"EREV_CORS_ORIGINS lists {count} origins without a wildcard")


def session_cookie(snapshot: SettingsSnapshot) -> CheckResult:
    """Observed through EREV_PUBLIC_ORIGIN, which alone decides the cookie's Secure attribute
    (05 SAR-09 rev 1.53; DG-KRN-AUTH-07): an origin that is not https cannot carry a deployment's
    session cookie — it is Secure and a browser does not return it over http, or, on a loopback
    host, it goes without Secure. A loopback origin is reported as well: only this machine
    reaches it."""
    parts = urlsplit(snapshot.public_origin)
    host = (parts.hostname or "").lower()
    failures: list[str] = []
    if host in LOOPBACK_HOSTS:
        failures.append(
            f"EREV_PUBLIC_ORIGIN names {host}, a loopback host that only this machine reaches "
            "(05 CFG-09)"
        )
    if parts.scheme != "https":
        failures.append(
            f"EREV_PUBLIC_ORIGIN scheme is {parts.scheme or 'missing'}, not https; a session "
            "cookie needs an https origin (05 SAR-09)"
        )
    return CheckResult(
        SESSION_COOKIE, f"the session cookie is Secure on {parts.scheme}://{host}", tuple(failures)
    )


def defusedxml(active: bool | None) -> CheckResult:
    if active is None:
        return _uncollected(DEFUSEDXML, "openpyxl.DEFUSEDXML")
    if not active:
        return CheckResult(
            DEFUSEDXML,
            "",
            ("openpyxl.DEFUSEDXML is false; defusedxml is not installed (05 UPL-05)",),
        )
    return CheckResult(DEFUSEDXML, "openpyxl.DEFUSEDXML is true (05 UPL-05)")


def _months_ahead(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def partition_window(
    windows: Sequence[PartitionWindowObservation] | None,
    *,
    now: datetime,
    horizon_months: int = PARTITION_HORIZON_MONTHS,
) -> CheckResult:
    """Every PT-MPE and PT-MOC table (``PARTITION_COLUMNS``) keeps a bounded window ending more
    than ``horizon_months`` after the check — the doctor's startup horizon of 12 months by default;
    SCH-13 passes 04 §1.6 rule 2's 24 (``controls.partition_window``)."""
    if windows is None:
        return _uncollected(PARTITION_WINDOW, "the partition windows")
    today = now.date()
    horizon = _months_ahead(today, horizon_months)
    observed = {window.table: window for window in windows}
    failures: list[str] = []
    ends: list[date] = []
    for table in sorted(set(PARTITION_COLUMNS) | set(observed)):
        window = observed.get(table)
        if window is None:
            failures.append(f"table {table} has no partition window observation")
        elif window.ends_on is None:
            failures.append(f"table {table} has no bounded partition (04 §1.6 rule 1)")
        elif window.ends_on <= horizon:
            failures.append(
                f"partition window of {table} ends {window.ends_on.isoformat()}, within "
                f"{horizon_months} months of {today.isoformat()} (04 §1.6 rule 2)"
            )
        else:
            ends.append(window.ends_on)
    earliest = f" (earliest {min(ends).isoformat()})" if ends else ""
    return CheckResult(
        PARTITION_WINDOW,
        f"every partition window ends after {horizon.isoformat()}{earliest}",
        tuple(failures),
    )


def release_stamp(release: ReleaseObservation | None) -> CheckResult:
    """05 REL-03: the manifest is present and describes the running release. An observation that
    reports absence fails even without a collector error (Codex P4-R3)."""
    if release is None:
        return _uncollected(RELEASE_STAMP, "the release manifest")
    if release.error is not None:
        return CheckResult(RELEASE_STAMP, "", (release.error,))
    if not release.manifest_present:
        return CheckResult(
            RELEASE_STAMP,
            "",
            (
                "release-manifest.json is absent; production requires the release manifest "
                "(05 REL-03)",
            ),
        )
    sha = (release.build_sha or "unknown")[:12]
    return CheckResult(RELEASE_STAMP, f"release-manifest.json describes build {sha}")


def key_provider(snapshot: SettingsSnapshot, provider: ProviderObservation | None) -> CheckResult:
    failures: list[str] = []
    if snapshot.key_provider == "local":
        summary = "EREV_KEY_PROVIDER is local (compose shape, 05 CFG-11)"
    else:
        if not snapshot.gcp_project_set:
            failures.append("EREV_KEY_PROVIDER=gcp requires EREV_GCP_PROJECT (05 CFG-13)")
        if not snapshot.gcp_kms_kek_set:
            failures.append("EREV_KEY_PROVIDER=gcp requires EREV_GCP_KMS_KEK (05 CFG-13)")
        if provider is None:
            failures.append(f"the key provider probe {NOT_COLLECTED}")
            summary = ""
        else:
            summary = f"key provider {provider.identity} is healthy"
    if provider is not None and not provider.healthy:
        detail = provider.detail or "no detail"
        failures.append(f"key provider {provider.identity} probe failed: {detail}")
    return CheckResult(KEY_PROVIDER, summary, tuple(failures))


def key_version_pin(
    snapshot: SettingsSnapshot, provider: ProviderObservation | None
) -> CheckResult:
    """05 KEY-03: the pinned ``security-hmac`` version equals the version of the provider's
    collected current key id. A configured pin is never a verified match without that identity
    (Codex P4-R1); the pin text is parsed as ASCII digits only (P4-R4)."""
    name = SECURITY_HMAC_SECRET_VERSION_NAME
    if name in snapshot.undefined:  # Codex P4-R2: before any value is read
        return _undefined_warning(KEY_VERSION_PIN, name)
    text = snapshot.security_hmac_secret_version
    if text is None:
        return CheckResult(
            KEY_VERSION_PIN, "", (f"{name} must be set under production (05 KEY-03)",)
        )
    if _PIN_TEXT.fullmatch(text) is None or int(text) < 1:
        return CheckResult(KEY_VERSION_PIN, "", (INVALID_PIN,))
    version = int(text)
    current = provider.security_hmac_key_id if provider is not None else None
    if current is None:
        return CheckResult(
            KEY_VERSION_PIN,
            "",
            (
                f"the provider's current {SECURITY_HMAC_PURPOSE} key id was not collected; "
                f"{name}={version} is not verified (05 KEY-03, SAR-40)",
            ),
        )
    match = _SECURITY_HMAC_KEY_ID.fullmatch(current)
    if match is None:
        return CheckResult(
            KEY_VERSION_PIN,
            "",
            (f"the provider's current {SECURITY_HMAC_PURPOSE} key id is malformed (05 KEY-03)",),
        )
    current_version = int(match.group(1))
    if current_version != version:
        return CheckResult(
            KEY_VERSION_PIN,
            "",
            (
                f"{name}={version} differs from the provider's current {SECURITY_HMAC_PURPOSE} key "
                f"id version {current_version} (05 KEY-03)",
            ),
        )
    return CheckResult(
        KEY_VERSION_PIN,
        f"{SECURITY_HMAC_PURPOSE} pinned at version {version}, matching the provider's current "
        "key id",
    )


def recovery_provider(snapshot: SettingsSnapshot) -> CheckResult:
    """05 CFG-30 (D-95): NATIVE or MANAGED, consistent with the key provider; under production
    NATIVE requires both recovery URLs and MANAGED refuses them."""
    name = RECOVERY_PROVIDER_NAME
    if name in snapshot.undefined:  # Codex P4-R2: WARN instead of a result, whatever was supplied
        return _undefined_warning(RECOVERY_PROVIDER, name)
    expected = RECOVERY_PROVIDER_OF_KEY_PROVIDER.get(snapshot.key_provider)
    origin = ""
    if snapshot.recovery_provider is None:
        if expected is None:
            return CheckResult(
                RECOVERY_PROVIDER,
                "",
                (f"{name} is unset and EREV_KEY_PROVIDER={snapshot.key_provider} has no default",),
            )
        provider = expected
        origin = f" (defaulted from EREV_KEY_PROVIDER={snapshot.key_provider})"
    else:
        provider = snapshot.recovery_provider.strip().upper()
        if provider not in RECOVERY_PROVIDERS:
            return CheckResult(
                RECOVERY_PROVIDER, "", (f"{name} must be NATIVE or MANAGED (05 CFG-30, D-95)",)
            )
        if expected is not None and provider != expected:
            return CheckResult(
                RECOVERY_PROVIDER,
                "",
                (
                    f"{name}={provider} contradicts EREV_KEY_PROVIDER={snapshot.key_provider} "
                    "(D-95: local → NATIVE, gcp → MANAGED)",
                ),
            )
    urls = (
        (BACKUP_URL_NAME, snapshot.backup_url_set),
        (RESTORE_ADMIN_URL_NAME, snapshot.restore_admin_url_set),
    )
    if provider == NATIVE:
        failures = [
            f"{name}=NATIVE requires {url} under production (05 CFG-30)"
            for url, is_set in urls
            if not is_set
        ]
    else:
        failures = [
            f"{name}=MANAGED refuses a set {url} (05 CFG-30)" for url, is_set in urls if is_set
        ]
    return CheckResult(RECOVERY_PROVIDER, f"{name} is {provider}{origin}", tuple(failures))


def anthropic_key(snapshot: SettingsSnapshot, resolves: bool | None) -> CheckResult:
    """05 KEY-10: a warning, never a failure (SAR-40 exit 0)."""
    if snapshot.ai_provider != "anthropic":
        return CheckResult(ANTHROPIC_KEY, f"EREV_AI_PROVIDER is {snapshot.ai_provider}")
    resolved = snapshot.anthropic_api_key_set if resolves is None else resolves
    if not resolved:
        return CheckResult(
            ANTHROPIC_KEY,
            "",
            warnings=(
                "EREV_AI_PROVIDER is anthropic and no ANTHROPIC_API_KEY secret resolves "
                "(05 KEY-10); AI calls will fail",
            ),
        )
    return CheckResult(
        ANTHROPIC_KEY, "EREV_AI_PROVIDER is anthropic and ANTHROPIC_API_KEY resolves"
    )


def operator_alerts(snapshot: SettingsSnapshot) -> CheckResult:
    """05 OPR-24 / CFG-31 / SAR-40 rev 1.27: a production deployment names an alert recipient or
    acknowledges log-only delivery explicitly; otherwise the alerts would go silent unnoticed."""
    if snapshot.operator_alert_email_set:
        return CheckResult(OPERATOR_ALERTS, "EREV_OPERATOR_ALERT_EMAIL is set")
    if snapshot.operator_alert_delivery == "log-only":
        return CheckResult(
            OPERATOR_ALERTS, "EREV_OPERATOR_ALERT_DELIVERY is log-only (acknowledged; 05 CFG-31)"
        )
    return CheckResult(
        OPERATOR_ALERTS,
        "",
        (
            "neither EREV_OPERATOR_ALERT_EMAIL nor EREV_OPERATOR_ALERT_DELIVERY=log-only is set; "
            "operator alerts would go silent (05 OPR-24, CFG-31, SAR-40)",
        ),
    )


def lock_budget(observation: LockBudgetObservation | None) -> CheckResult:
    """05 §2.7 lock budget: PostgreSQL's shared lock table, ``max_locks_per_transaction ×
    (max_connections + max_prepared_transactions)`` slots for the whole server, holds the
    partition lock footprint for every session the connection rule admits (80% of
    ``max_connections``) plus every relation once. A full table answers SQLSTATE 53200 to
    whichever statement needs the next slot; the setting changes only with a server restart."""
    if observation is None:
        return _uncollected(LOCK_BUDGET, "the lock table settings")
    footprint = observation.partition_lock_footprint
    if footprint < 1:
        return CheckResult(
            LOCK_BUDGET,
            "",
            (
                "schema erev has no partitioned table, so the partition lock footprint cannot be "
                "measured (04 §1.6; 05 §2.7)",
            ),
        )
    backends = observation.max_connections + observation.max_prepared_transactions
    slots = observation.max_locks_per_transaction * backends
    numerator, denominator = LOCK_SESSION_SHARE
    sessions = observation.max_connections * numerator // denominator
    required = sessions * footprint + observation.relations
    demand = (
        f"{sessions} sessions × {footprint} partition locks + {observation.relations} relations"
    )
    if slots >= required:
        return CheckResult(
            LOCK_BUDGET,
            f"{slots} lock slots (max_locks_per_transaction "
            f"{observation.max_locks_per_transaction}) cover {demand} = {required} (05 §2.7)",
        )
    floor = -(-required // backends)
    return CheckResult(
        LOCK_BUDGET,
        "",
        (
            f"max_locks_per_transaction {observation.max_locks_per_transaction} × (max_connections "
            f"{observation.max_connections} + max_prepared_transactions "
            f"{observation.max_prepared_transactions}) gives {slots} lock slots; {demand} need "
            f"{required} (05 §2.7): set max_locks_per_transaction to at least {floor} and restart "
            "PostgreSQL",
        ),
    )


def index_conditions(observation: IndexConditionsObservation | None) -> CheckResult:
    """05 §2.7 index conditions under the policy (04 NC-20; dev-guide DG-KRN-DB-10): a warning,
    never a failure (SAR-40 rev 1.156, exit 0). ``make test-pg`` holds the migrated schema to
    no finding, so a finding on a deployment says that its schema is not the tested one — an
    index built by hand, or another revision's. Such a key costs time at volume and never a
    wrong answer, so it does not stop a rollout; an observation that was not collected does,
    as with every production check."""
    if observation is None:
        return _uncollected(INDEX_CONDITIONS, "the index catalogue")
    return CheckResult(
        INDEX_CONDITIONS,
        "every index of a table with a row-level-security policy has a key the policy can use, "
        f"or is one of the {observation.listed} listed with a reason (05 §2.7)",
        warnings=observation.findings,
    )


def production_checks(observations: ProductionObservations, *, now: datetime) -> list[CheckResult]:
    """The SAR-40 checks in ``PRODUCTION_CHECK_NAMES`` order under production; [] elsewhere."""
    snapshot = observations.settings
    if snapshot.env is not Environment.PRODUCTION:
        return []
    results = [
        email_backend(snapshot),
        integration_urls(observations.integration_connections),
        cors_origins(snapshot),
        session_cookie(snapshot),
        defusedxml(observations.defusedxml),
        partition_window(observations.partition_windows, now=now),
        release_stamp(observations.release),
        key_provider(snapshot, observations.provider),
        key_version_pin(snapshot, observations.provider),
        recovery_provider(snapshot),
        anthropic_key(snapshot, observations.anthropic_key_resolves),
        operator_alerts(snapshot),
        lock_budget(observations.lock_budget),
        master_keys(snapshot),
        index_conditions(observations.index_conditions),
    ]
    return [_with_collector_reason(result, observations) for result in results]


# Which checks read which observation member; the FAIL line of an uncollected member names
# the collector's reason from its provenance (RB-03 "How the command collects").
_MEMBER_OF_CHECK: Final[Mapping[str, str]] = {
    INTEGRATION_URLS: "integration_connections",
    PARTITION_WINDOW: "partition_windows",
    DEFUSEDXML: "defusedxml",
    RELEASE_STAMP: "release",
    KEY_PROVIDER: "provider",
    KEY_VERSION_PIN: "provider",
    LOCK_BUDGET: "lock_budget",
    INDEX_CONDITIONS: "index_conditions",
}


def _with_collector_reason(
    result: CheckResult, observations: ProductionObservations
) -> CheckResult:
    member = _MEMBER_OF_CHECK.get(result.check)
    if member is None or not result.failures:
        return result
    reason = next(
        (p.error for p in observations.provenance if p.member == member and p.error), None
    )
    if reason is None:
        return result
    failures = tuple(
        failure.replace(f" {NOT_COLLECTED}", f" was not collected: {reason}")
        if NOT_COLLECTED in failure
        else failure
        for failure in result.failures
    )
    return dataclasses.replace(result, failures=failures)


def observe_defusedxml() -> bool | None:
    """``openpyxl.DEFUSEDXML`` (05 UPL-05); None when openpyxl cannot be imported."""
    try:
        module = importlib.import_module("openpyxl")
    except ImportError:
        return None
    flag = getattr(module, "DEFUSEDXML", None)
    return flag if isinstance(flag, bool) else None


def observe_release(
    env: Environment,
    *,
    manifest_path: Path = MANIFEST_PATH,
    build_sha: Callable[[], str] = git_build_sha,
) -> ReleaseObservation:
    """The REL-03 release facts as an observation; a manifest problem becomes ``error``."""
    present = manifest_path.exists()
    try:
        facts = release_facts(env, manifest_path=manifest_path, build_sha=build_sha)
    except RuntimeError as exc:  # ReleaseManifestError, or code_head() finding no single head
        return ReleaseObservation(manifest_present=present, build_sha=None, error=str(exc))
    return ReleaseObservation(manifest_present=present, build_sha=facts.build_sha, error=None)


def _uncollected_observation() -> None:
    """Default for a collector the caller did not compose: the member stays not collected."""
    return None


def _anthropic_key_from_settings(snapshot: SettingsSnapshot) -> bool | None:
    return snapshot.anthropic_api_key_set


NO_COLLECTOR: Final = "no collector composed for this member (SOP-6)"
# What each collector attempts, in code-owned words: the FAIL line of a failed collector carries the
# exception type and this text, never the exception's message (Codex P4B-R1 ruling).
_ATTEMPTS: Final[Mapping[str, str]] = {
    "defusedxml": "importing openpyxl",
    "anthropic_key_resolves": "resolving the Anthropic key through the key ring",
    "integration_connections": "reading integration connections through the tenant directory",
    "partition_windows": "reading the partition bounds from pg_inherits",
    "release": "reading release-manifest.json",
    "provider": "probing the key provider",
    "lock_budget": "reading the lock table settings and the partition catalogue",
    "index_conditions": "reading the index keys from the catalogue",
}


def attempt_of(exc: BaseException, attempt: str) -> str:
    """A safe diagnostic for an untrusted failure: the exception type and the code-owned attempt."""
    return f"{type(exc).__name__} while {attempt}"


def _collect[T](
    member: str,
    source: str,
    fn: Callable[[], T | None],
    *,
    now: datetime,
    provenance: list[Provenance],
) -> T | None:
    """Run one collector; a failure is an observation with a reason, never an abort."""
    try:
        value = fn()
    except CollectorPending as exc:  # a code-owned reason: verbatim
        provenance.append(Provenance(member, source, now, f"CollectorPending: {exc.reason}"))
        return None
    except Exception as exc:  # untrusted message: type and the code-owned attempt only (P4B-R1)
        provenance.append(Provenance(member, source, now, attempt_of(exc, _ATTEMPTS[member])))
        return None
    provenance.append(Provenance(member, source, now, None if value is not None else NO_COLLECTOR))
    return value


def collect_production_observations(
    settings: Settings,
    *,
    now: datetime,
    environ: Mapping[str, str] | None = None,
    defusedxml: Callable[[], bool | None] = observe_defusedxml,
    anthropic_key_resolves: Callable[
        [SettingsSnapshot], bool | None
    ] = _anthropic_key_from_settings,
    integration_connections: Callable[
        [], tuple[IntegrationConnectionObservation, ...] | None
    ] = _uncollected_observation,
    partition_windows: Callable[
        [], tuple[PartitionWindowObservation, ...] | None
    ] = _uncollected_observation,
    release: Callable[[Environment], ReleaseObservation | None] = observe_release,
    provider: Callable[[], ProviderObservation | None] = _uncollected_observation,
    lock_budget: Callable[[], LockBudgetObservation | None] = _uncollected_observation,
    index_conditions: Callable[[], IndexConditionsObservation | None] = _uncollected_observation,
) -> ProductionObservations:
    """Collect every observation once, through injected collectors (composition roots pass
    ``production_collector``'s real ones; tests pass fakes), each with provenance. A collector
    left at its default, or one that raises, leaves its member None with the reason recorded;
    the checks then fail closed and name it."""
    snapshot = snapshot_settings(settings, environ)
    provenance: list[Provenance] = []
    return ProductionObservations(
        settings=snapshot,
        defusedxml=_collect("defusedxml", "openpyxl", defusedxml, now=now, provenance=provenance),
        anthropic_key_resolves=_collect(
            "anthropic_key_resolves",
            "Settings, key ring",
            lambda: anthropic_key_resolves(snapshot),
            now=now,
            provenance=provenance,
        ),
        integration_connections=_collect(
            "integration_connections",
            "erev.integration_connection (T-INT-01)",
            integration_connections,
            now=now,
            provenance=provenance,
        ),
        partition_windows=_collect(
            "partition_windows", "pg_inherits", partition_windows, now=now, provenance=provenance
        ),
        release=_collect(
            "release",
            "release-manifest.json",
            lambda: release(snapshot.env),
            now=now,
            provenance=provenance,
        ),
        provider=_collect("provider", "KeyRing", provider, now=now, provenance=provenance),
        lock_budget=_collect(
            "lock_budget",
            "pg_settings, pg_class, pg_inherits, pg_index",
            lock_budget,
            now=now,
            provenance=provenance,
        ),
        index_conditions=_collect(
            "index_conditions",
            "pg_index, pg_class, pg_attribute, pg_opclass, pg_amop, pg_proc",
            index_conditions,
            now=now,
            provenance=provenance,
        ),
        provenance=tuple(provenance),
    )


# ---- Real collectors (composed by ``production_collector`` for ``cli.py``) --------------------

# 05 KEY-10: Secret Manager ``erev-anthropic-api-key`` is the CFG-13 prefix plus this reference.
ANTHROPIC_SECRET_REF: Final = "anthropic-api-key"
SECURITY_HMAC_KEY_BYTES: Final = 32
_PARTITION_BOUNDS = text(
    """
    SELECT c.relname, pg_get_expr(c.relpartbound, c.oid)
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    WHERE i.inhparent = CAST(:parent AS regclass)
    ORDER BY c.relname
    """
)
# ``FOR VALUES FROM ('2032-12-01') TO ('2033-01-01')``, with or without a time and offset.
_UPPER_BOUND: Final = re.compile(r"TO \('(\d{4}-\d{2}-\d{2})")
ProductionCollector = Callable[[Sequence[_Tenant]], ProductionObservations]


def observe_anthropic_key(settings: Settings, keyring: KeyRing) -> bool:
    """Whether an ``ANTHROPIC_API_KEY`` secret resolves (05 KEY-10): the setting, or under
    ``gcp`` the Secret Manager reference through the key ring. Probed only for the
    ``anthropic`` provider; nothing about the value is kept."""
    if settings.anthropic_api_key is not None:
        return True
    if settings.ai_provider != "anthropic" or settings.key_provider != "gcp":
        return False
    try:
        keyring.secret(ANTHROPIC_SECRET_REF)
    except KeyError:
        return False
    return True


def observe_key_provider(settings: Settings, keyring: KeyRing) -> ProviderObservation:
    """The key provider's identity (05 CFG-11, CFG-13), its current ``security-hmac`` key id and
    a derivation probe of that id. ``KeyRing.current_security_key_id()`` arrives with lane P2;
    without it the observation is not collected (``CollectorPending``)."""
    accessor = getattr(keyring, "current_security_key_id", None)
    if accessor is None:
        raise CollectorPending(PENDING_KEY_ID_ACCESSOR)
    key_id = str(accessor())
    identity = (
        "LocalKeyProvider"
        if settings.key_provider == "local"
        else f"GcpKeyProvider project {settings.gcp_project} KEK {settings.gcp_kms_kek}"
    )
    try:
        material = keyring.security_event_key(key_id)
    except Exception as exc:  # the probe result is the observation; its message is untrusted
        detail = attempt_of(exc, f"deriving the current {SECURITY_HMAC_PURPOSE} key")
        return ProviderObservation(settings.key_provider, identity, False, key_id, detail)
    if len(material) != SECURITY_HMAC_KEY_BYTES:
        return ProviderObservation(
            settings.key_provider,
            identity,
            False,
            key_id,
            f"the {SECURITY_HMAC_PURPOSE} key is not {SECURITY_HMAC_KEY_BYTES} bytes",
        )
    return ProviderObservation(settings.key_provider, identity, True, key_id)


def observe_integration_connections(
    tenants: Sequence[_Tenant],
) -> tuple[IntegrationConnectionObservation, ...]:
    """Every T-INT-01 row of every workspace, through read-only tenant sessions (the tenant
    directory is the one ``run_doctor`` already read). Not collected until the INT lane's table
    exists on the build."""
    table = getattr(db_tables, "integration_connection", None)
    if table is None:
        raise CollectorPending(PENDING_INTEGRATION_TABLE)
    found: list[IntegrationConnectionObservation] = []
    for workspace in tenants:
        ctx = DbContext(tenant_id=workspace.id, user_id=None, entity_scope="*")
        with tenant_session(ctx, read_only=True) as session:
            rows = session.execute(
                select(table.c.code, table.c.status, table.c.base_url).order_by(table.c.code)
            ).all()
        found += [
            IntegrationConnectionObservation(
                workspace.code, str(code), str(status), None if url is None else str(url)
            )
            for code, status, url in rows
        ]
    return tuple(found)


def partition_upper_bound(bound: str) -> date | None:
    """The exclusive upper bound of one ``pg_get_expr(relpartbound)`` text; None for the
    ``DEFAULT`` partition or an unparsable bound."""
    match = _UPPER_BOUND.search(bound)
    return None if match is None else date.fromisoformat(match.group(1))


def observe_partition_windows(connection: Connection) -> tuple[PartitionWindowObservation, ...]:
    """The last bounded partition of every PT-MPE and PT-MOC parent (04 §1.6), from the
    catalogue as ``erev_app``."""
    windows: list[PartitionWindowObservation] = []
    for table_name in sorted(PARTITION_COLUMNS):
        rows = connection.execute(_PARTITION_BOUNDS, {"parent": f"erev.{table_name}"}).all()
        ends = [
            upper for _, bound in rows if (upper := partition_upper_bound(str(bound))) is not None
        ]
        windows.append(PartitionWindowObservation(table_name, max(ends) if ends else None))
    return tuple(windows)


# 05 §2.7: per partitioned table of schema erev the parent, its (partitioned) indexes, its
# partitions and their indexes — what one statement locks when it names no partition value.
_LOCK_BUDGET = text(
    """
    SELECT CAST(current_setting('max_locks_per_transaction') AS integer),
           CAST(current_setting('max_connections') AS integer),
           CAST(current_setting('max_prepared_transactions') AS integer),
           (SELECT coalesce(sum(
                       1
                       + (SELECT count(*) FROM pg_index x WHERE x.indrelid = p.oid)
                       + (SELECT count(*) FROM pg_inherits i WHERE i.inhparent = p.oid)
                       + (SELECT count(*) FROM pg_inherits i
                          JOIN pg_index x ON x.indrelid = i.inhrelid
                          WHERE i.inhparent = p.oid)), 0)
            FROM pg_class p
            JOIN pg_namespace n ON n.oid = p.relnamespace
            WHERE n.nspname = 'erev' AND p.relkind = 'p'),
           (SELECT count(*)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND c.relkind IN ('r', 'p', 'i', 'I', 'S', 't', 'm', 'v', 'f'))
    """
)


def observe_lock_budget(connection: Connection) -> LockBudgetObservation:
    """The server's lock-table settings and the catalogue counts of the 05 §2.7 rule, read as
    ``erev_app`` (the settings and the system catalogues are readable by every role)."""
    locks, connections, prepared, footprint, relations = connection.execute(_LOCK_BUDGET).one()
    return LockBudgetObservation(
        max_locks_per_transaction=int(locks),
        max_connections=int(connections),
        max_prepared_transactions=int(prepared),
        partition_lock_footprint=int(footprint),
        relations=int(relations),
    )


def observe_index_conditions(connection: Connection) -> IndexConditionsObservation:
    """The catalogue check of ``db.index_conditions`` on the schema this connection reaches,
    read as ``erev_app``: it reads the system catalogues and no table (05 §2.7)."""
    return IndexConditionsObservation(
        findings=tuple(str(finding) for finding in db_index_conditions.findings(connection)),
        listed=len(db_index_conditions.ALLOWED),
    )


def production_collector(
    settings: Settings,
    *,
    keyring: KeyRing,
    environ: Mapping[str, str],
    request_id: str,
    now: datetime,
) -> ProductionCollector:
    """The real composition ``cli.py`` passes to ``run_doctor`` under ``production``: every
    collector bound to the process settings, key ring and catalogue connection; the tenant
    directory arrives from ``run_doctor``."""

    def partitions() -> tuple[PartitionWindowObservation, ...]:
        with catalogue_connection(request_id=request_id) as connection:
            return observe_partition_windows(connection)

    def locks() -> LockBudgetObservation:
        with catalogue_connection(request_id=request_id) as connection:
            return observe_lock_budget(connection)

    def index_keys() -> IndexConditionsObservation:
        with catalogue_connection(request_id=request_id) as connection:
            return observe_index_conditions(connection)

    def collect(tenants: Sequence[_Tenant]) -> ProductionObservations:
        return collect_production_observations(
            settings,
            now=now,
            environ=environ,
            anthropic_key_resolves=lambda snapshot: observe_anthropic_key(settings, keyring),
            integration_connections=lambda: observe_integration_connections(tenants),
            partition_windows=partitions,
            release=lambda env: observe_release(env, manifest_path=MANIFEST_PATH),
            provider=lambda: observe_key_provider(settings, keyring),
            lock_budget=locks,
            index_conditions=index_keys,
        )

    return collect
