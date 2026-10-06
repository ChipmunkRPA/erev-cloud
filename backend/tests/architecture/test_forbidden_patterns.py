"""DG-ARC-05: forbidden patterns (DG-KRN-TIME-05, DG-KRN-DB-06, DG-ENV-14, DG-LOG-06, DG-LAY-11,
05 TZ-09, 05 ADP-14; BUILD_SPEC FND-13).

Line rules match raw text, comments and docstrings included. Product rules cover the application
packages. Shared-machine rules (docs/00-GOAL.md §5; REQ-OPS-010) cover the source files of
``backend/``, ``scripts/`` and ``frontend/`` and the Makefile. Interpolated ``text(`` covers the
Python of ``backend/`` and ``scripts/``. TZ-09 tokens are matched case-insensitively in string
literals under ``backend/erev_api/``, which holds the migration revisions. This module is exempt
because its snippets hold the patterns.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Final

from support.architecture import (
    DATABASE_ADMINISTRATION_OBJECTS,
    DATABASE_ADMINISTRATION_SERVER_STATEMENT,
    DATABASE_ADMINISTRATION_VERBS,
    Finding,
    callee,
    iter_files,
    read,
    report,
)

PRODUCT: Final = ("backend/erev_api", "backend/erev_engine")
SQL_CODE: Final = ("backend", "scripts")
MACHINE: Final = ("backend", "scripts", "frontend", "Makefile")
TEXT_SUFFIXES: Final = frozenset(
    {
        ".py",
        ".sh",
        ".toml",
        ".ini",
        ".cfg",
        ".mako",
        ".yaml",
        ".yml",
        ".json",
        ".ts",
        ".tsx",
        ".js",
        ".mjs",
        ".cjs",
        ".css",
        ".html",
        ".md",
        ".txt",
    }
)
EXEMPT: Final = frozenset(
    {
        "backend/tests/architecture/test_forbidden_patterns.py",
        # Package names, versions and hashes only.
        "frontend/package-lock.json",
    }
)


@dataclass(frozen=True, slots=True)
class LineRule:
    id: str
    pattern: re.Pattern[str]
    scope: tuple[str, ...]
    allowed: tuple[str, ...] = ()  # file paths, or directory prefixes ending in "/"
    python_only: bool = False


LINE_RULES: Final = (
    # problems.py registers the handler that maps Starlette HTTP errors to problems (SPEC-Q-33).
    LineRule(
        "HTTPException",
        re.compile(r"\bHTTPException\b"),
        PRODUCT,
        ("backend/erev_api/problems.py",),
    ),
    LineRule(
        "clock",
        re.compile(
            r"(?<!\w)(?:datetime\.(?:now|utcnow)|date\.today|time\.(?:time|monotonic))\b"
            r"|^\s*from\s+time\s+import\s+[^#\n]*\b(?:time|monotonic)\b"
        ),
        PRODUCT,
        ("backend/erev_api/clock.py", "backend/erev_api/logging.py"),
    ),
    LineRule("print", re.compile(r"(?<![\w.])print\("), PRODUCT),
    LineRule(
        "Session", re.compile(r"(?<!\w)Session\("), PRODUCT, ("backend/erev_api/db/session.py",)
    ),
    # D-78 on DG-ENV-14: CREATE, ALTER or DROP of each administered object, plus ALTER SYSTEM.
    LineRule(
        "database-administration",
        re.compile(
            rf"\b(?:{'|'.join(DATABASE_ADMINISTRATION_VERBS)})\s+"
            rf"(?:{'|'.join(DATABASE_ADMINISTRATION_OBJECTS)})\b"
            rf"|\b{DATABASE_ADMINISTRATION_SERVER_STATEMENT.replace(' ', r'\s+')}\b",
            re.IGNORECASE,
        ),
        MACHINE,
    ),
    LineRule(
        "legacy-import", re.compile(r"^\s*(?:import|from)\s+eRev\b"), MACHINE, python_only=True
    ),
    LineRule("legacy-path", re.compile(r"erev-legacy"), MACHINE, ("scripts/build_fixtures.py",)),
    LineRule("tmp", re.compile(r"(?<![\w.])/tmp\b"), MACHINE),
    LineRule(
        "requests", re.compile(r"^\s*(?:import|from)\s+requests\b"), MACHINE, python_only=True
    ),
    LineRule(
        "sqlite",
        re.compile(r"^\s*(?:import|from)\s+sqlite3\b|\bsqlite(?:\+\w+)?://"),
        MACHINE,
        (
            "backend/erev_api/domain/migration/",
            "scripts/build_fixtures.py",
            "backend/tests/support/parity/",
        ),
    ),
    # 05 ADP-14, KEY-09 rev 1.47 (security review 2026-09-29 P3-23): ``KeyRing.secret`` reads
    # whatever reference it is given. A reference a tenant wrote is read only through
    # ``KeyRing.adapter_secret``, which takes the tenant and serves nothing outside its namespace
    # of the secret store; the files allowed read references the platform's operator set — the
    # key ring itself, an identity provider's client secret and the deployment check's AI key.
    LineRule(
        "secret-read",
        re.compile(r"\.secret\("),
        ("backend/erev_api",),
        (
            "backend/erev_api/auth/keyring.py",
            "backend/erev_api/auth/oidc.py",
            "backend/erev_api/controls/doctor.py",
        ),
        python_only=True,
    ),
)

TZ09_TOKENS: Final = ("CURRENT_DATE", "LOCALTIMESTAMP", "now()::date", "date_trunc(")
TZ09_SCOPE: Final = ("backend/erev_api",)


@dataclass(frozen=True, slots=True)
class Tz09Allowance:
    path: str
    token: str
    reason: str  # audit timestamps or retention purges (05 TZ-09)


TZ09_ALLOWLIST: Final[tuple[Tz09Allowance, ...]] = ()


def _within(path: str, roots: Iterable[str]) -> bool:
    return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)


def _interpolated_text(tree: ast.AST) -> Iterator[int]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and callee(node) == "text" and node.args:
            sql = node.args[0]
            if (
                isinstance(sql, ast.JoinedStr)
                or (isinstance(sql, ast.BinOp) and isinstance(sql.op, ast.Mod))
                or (isinstance(sql, ast.Call) and callee(sql) == "format")
            ):
                yield node.lineno


def _tz09_hits(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            folded = node.value.casefold()
            for token in TZ09_TOKENS:
                if token.casefold() in folded:
                    yield node.lineno, token


def check_source(
    path: str, source: str, *, tz09_allowlist: Iterable[Tz09Allowance] = TZ09_ALLOWLIST
) -> list[Finding]:
    findings: list[Finding] = []
    is_python = path.endswith(".py")
    for rule in LINE_RULES:
        if not _within(path, rule.scope) or _within(path, rule.allowed):
            continue
        if rule.python_only and not is_python:
            continue
        for number, line in enumerate(source.splitlines(), start=1):
            if rule.pattern.search(line):
                findings.append(Finding(path, number, rule.id, rule.pattern.pattern))
    if is_python and (_within(path, SQL_CODE) or _within(path, TZ09_SCOPE)):
        tree = ast.parse(source, filename=path)
        if _within(path, SQL_CODE):
            findings += [
                Finding(path, line, "text-interpolation", "text( with f-string, % or .format(")
                for line in _interpolated_text(tree)
            ]
        if _within(path, TZ09_SCOPE):
            allowed = {(entry.path, entry.token) for entry in tz09_allowlist}
            findings += [
                Finding(path, line, "TZ-09", f"business-date SQL token {token}")
                for line, token in _tz09_hits(tree)
                if (path, token) not in allowed
            ]
    return sorted(findings)


def unused_tz09_entries(
    allowlist: Iterable[Tz09Allowance], source_of: Callable[[str], str] = read
) -> list[Finding]:
    return [
        Finding(entry.path, 0, "TZ-09", f"TZ09_ALLOWLIST entry for {entry.token} matches nothing")
        for entry in allowlist
        if entry.token not in {token for _, token in _tz09_hits(ast.parse(source_of(entry.path)))}
    ]


SNIPPETS: Final = (
    ("HTTPException", "backend/erev_api/api/v1/x.py", "raise HTTPException(status_code=404)\n"),
    ("clock", "backend/erev_api/api/v1/x.py", "stamp = datetime.utcnow()\n"),
    ("print", "backend/erev_api/api/v1/x.py", 'print("debug")\n'),
    ("Session", "backend/erev_api/api/v1/x.py", "session = Session(bind=engine)\n"),
    (
        "text-interpolation",
        "backend/erev_api/api/v1/x.py",
        'rows = connection.execute(text(f"select {x}"))\n',
    ),
    ("database-administration", "backend/erev_api/api/v1/x.py", 'op.execute("CREATE ROLE x")\n'),
    (
        "database-administration",
        "backend/erev_api/api/v1/x.py",
        'op.execute("ALTER SYSTEM RESET x")\n',
    ),
    ("tmp", "backend/erev_api/api/v1/x.py", 'scratch = Path("/tmp/erev")\n'),
    ("requests", "backend/erev_api/api/v1/x.py", "import requests\n"),
    ("sqlite", "backend/erev_api/api/v1/x.py", "import sqlite3\n"),
    ("TZ-09", "backend/erev_api/domain/x.py", 'sql = "SELECT CURRENT_DATE"\n'),
    (
        "secret-read",
        "backend/erev_api/domain/integrations/x.py",
        "value = uow.keyring.secret(ref)\n",
    ),
)


def test_dg_arc_05_detects_each_pattern() -> None:
    for rule, path, snippet in SNIPPETS:
        findings = check_source(path, snippet)
        assert [(finding.rule, finding.line) for finding in findings] == [(rule, 1)], (
            snippet,
            report(findings),
        )
    assert check_source("backend/erev_api/domain/migration/legacy_db.py", "import sqlite3\n") == []
    # The key ring's own read, and a read through ``adapter_secret``, are not findings.
    assert check_source("backend/erev_api/auth/keyring.py", "return self.secret(ref)\n") == []
    tenanted = "uow.keyring.adapter_secret(ref, tenant_id=uow.principal.tenant_id)\n"
    assert check_source("backend/erev_api/domain/integrations/x.py", tenanted) == []


def test_dg_arc_05_repository_clean() -> None:
    paths = sorted(
        set(iter_files(*MACHINE, suffixes=TEXT_SUFFIXES, names=frozenset({"Makefile"}))) - EXEMPT
    )
    assert "backend/erev_api/clock.py" in paths and "Makefile" in paths
    findings = [finding for path in paths for finding in check_source(path, read(path))]
    assert findings == [], report(findings)
    assert unused_tz09_entries(TZ09_ALLOWLIST) == []
    for entry in TZ09_ALLOWLIST:
        assert entry.token in TZ09_TOKENS and entry.reason.strip(), entry


def test_more_patterns_and_scopes() -> None:
    flagged = (
        ("clock", "backend/erev_engine/x.py", "today = date.today()\n"),
        ("clock", "backend/erev_api/auth/x.py", "started = time.monotonic()\n"),
        ("clock", "backend/erev_api/auth/x.py", "from time import monotonic\n"),
        ("text-interpolation", "backend/erev_api/db/x.py", 'text("select %s" % x)\n'),
        ("text-interpolation", "scripts/x.py", 'sa.text("select {}".format(x))\n'),
        ("text-interpolation", "backend/tests/pg/x.py", 'text(f"select {x}")\n'),
        ("database-administration", "scripts/x.sh", "psql -c 'create extension pgcrypto'\n"),
        ("database-administration", "backend/tests/x.py", 'sql = "CREATE DATABASE x"\n'),
        ("legacy-import", "backend/tests/x.py", "import eRev\n"),
        ("legacy-path", "backend/tests/support/x.py", 'LEGACY = "~/dev/erev-legacy"\n'),
        ("tmp", "Makefile", "\tcp x /tmp/x\n"),
        ("tmp", "frontend/vite.config.ts", 'const cache = "/tmp/vite";\n'),
        ("sqlite", "backend/tests/unit/x.py", 'url = "sqlite+pysqlite:///x.db"\n'),
        (
            "TZ-09",
            "backend/erev_api/db/migrations/versions/0009_x.py",
            'op.execute("SELECT localtimestamp")\n',
        ),
        ("TZ-09", "backend/erev_api/domain/x.py", "sql = f\"SELECT date_trunc('month', {x})\"\n"),
        ("TZ-09", "backend/erev_api/domain/x.py", 'sql = "WHERE d = NOW()::date"\n'),
    )
    for rule, path, snippet in flagged:
        findings = check_source(path, snippet)
        assert [finding.rule for finding in findings] == [rule], (snippet, report(findings))

    allowed = (
        ("backend/erev_api/problems.py", "app.add_exception_handler(HTTPException, handle)\n"),
        ("backend/erev_api/clock.py", "return datetime.now(UTC)\n"),
        ("backend/erev_api/db/session.py", "session = Session(bind=app_engine())\n"),
        ("scripts/x.py", 'print("report")\n'),
        ("scripts/x.py", "started = time.time()\n"),
        ("backend/tests/pg/x.py", "session = Session(test_database.app_engine)\n"),
        ("Makefile", "export TMPDIR := $(CURDIR)/.run/tmp\n"),
        ("scripts/build_fixtures.py", 'LEGACY = Path.home() / "dev" / "erev-legacy"\n'),
        ("backend/tests/support/parity/x.py", "import sqlite3\n"),
        ("backend/erev_api/domain/x.py", "current_date = entity_today(clock, tz)\n"),
        ("backend/erev_api/db/x.py", 'connection.execute(text("select :x"), {"x": x})\n'),
        ("docs/notes.md", "CREATE ROLE /tmp erev-legacy\n"),
    )
    for path, snippet in allowed:
        assert check_source(path, snippet) == [], (path, snippet)


def test_dg_env_14_database_administration_synonyms() -> None:
    revision = "backend/erev_api/db/migrations/versions/0009_x.py"
    flagged = [
        (revision, f'op.execute("{statement}")\n')
        for statement in (
            "ALTER USER erev_app BYPASSRLS",
            "CREATE USER x",
            "DROP USER x",
            "CREATE GROUP x",
            "DROP ROLE x",
            "DROP DATABASE x",
            "ALTER DATABASE x SET y = 1",
            "CREATE TABLESPACE t LOCATION 'p'",
            "DROP EXTENSION x",
            "ALTER EXTENSION x UPDATE",
        )
    ]
    flagged.append(("scripts/x.sh", "psql -c 'DROP DATABASE x'\n"))
    for path, snippet in flagged:
        findings = check_source(path, snippet)
        assert [finding.rule for finding in findings] == ["database-administration"], (
            snippet,
            report(findings),
        )
    assert check_source(revision, 'op.execute("DROP SCHEMA IF EXISTS erev CASCADE")\n') == []


def test_tz09_allowlist_suppresses_and_detects_stale_entries() -> None:
    path = "backend/erev_api/domain/audit/retention.py"
    source = 'PURGE = "DELETE FROM x WHERE created_at < CURRENT_DATE - 2555"\n'
    entry = Tz09Allowance(path, "CURRENT_DATE", "retention purge cutoff")
    assert [finding.rule for finding in check_source(path, source)] == ["TZ-09"]
    assert check_source(path, source, tz09_allowlist=(entry,)) == []
    assert unused_tz09_entries((entry,), source_of=lambda _: source) == []
    stale = Tz09Allowance(path, "LOCALTIMESTAMP", "retention purge cutoff")
    assert len(unused_tz09_entries((stale,), source_of=lambda _: source)) == 1
