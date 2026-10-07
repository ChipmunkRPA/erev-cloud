"""DG-ARC-15 (dev-guide rev 1.57; GUARD-ORM-TYPE-1, D-98 candidate 136 — the supervisor's
engineering ruling on lane ENG-C6's design note; after Codex production-20260921-1118 accepted the
bounded 101996aa audit of the two ``migration_population_*`` tables and named the general guard as
the open engineering item).

For EVERY governed table one canonical column tuple — (name, base type, nullability, default, PK
membership) — is read from each of three sources and compared per table:

1. the ORM: ``erev_api.db.tables.metadata`` (SQLAlchemy Core; importable without a database);
2. the Alembic chain: every revision under ``db/migrations/versions`` replayed offline in
   ``down_revision`` order (single head asserted) under ``migration_ops.recording()`` — the
   helper's own no-database sink — and the final schema reconstructed by a small DDL interpreter
   over the recorded statements (``CREATE TABLE`` as ``sqlalchemy.schema.CreateTable`` compiles
   it, ``DROP TABLE``, ``ALTER TABLE … ADD / DROP / RENAME COLUMN``, ``ALTER COLUMN … SET / DROP
   NOT NULL | DEFAULT | TYPE``, ``ADD [CONSTRAINT …] PRIMARY KEY``, ``CREATE DOMAIN``, ``ALTER
   DOMAIN … RENAME``, ``CREATE TYPE … AS ENUM``); every other statement kind is skipped only
   through an explicit allow-list of statement heads, and a column statement the interpreter does
   not recognise FAILS BY NAME;
3. 04-DATA_MODEL: the ``| Column | Type | Null | Default | … |`` table under each
   ``### T-…-nn `<table>``` heading, with the ``SC-…`` rows expanded from 04 §1.3's OWN
   definitions and the primary key read from the block's ``PRIMARY KEY (…)`` statement or a
   ``PK`` notes cell.

Normalisation: domains resolve to their base through the chain's own ``CREATE DOMAIN`` statements
(``erev.sha256`` → ``char(64)``, ``erev.money`` → ``numeric(24,4)``, …), so the ORM's ``CHAR(64)``
/ ``MoneyType`` agree with 04's domain names; named enums are NEVER collapsed to text (the
batch-#5 ``book_code`` class); SQLAlchemy renderings map to PostgreSQL names (``TIMESTAMP WITH
TIME ZONE`` → ``timestamptz``). Nullability and PK membership are strict three-way. Defaults are
strict between 04 and the chain; an ORM column WITHOUT a declared ``server_default`` asserts
nothing about the default (database-owned — the Codex 1118 "handwritten-DDL contract"; Q-ORM-1
ruled) while a DECLARED one must equal the chain's. A generated column's ``GENERATED ALWAYS AS (…)
STORED`` expression is written in 04's notes cell with an empty Default cell and IS the column's
default for this comparison (04 §1.3, rev 1.69; D-98 candidate 136 amendment 1). ``ALLOWLIST``
names intentional divergences,
each citing its 04 sentence; an entry that no longer describes an actual divergence fails
(nothing silent). Partition children are out of scope by name (Q-ORM-2; the parents' columns are
in scope). The only revision allowed to reach Alembic directly is 0040
(``PARTITION_ENUMERATING_REVISIONS``); any other fails by name.

Amendment 2 (Codex production-20260921-1608 §2; D-98 candidate 136 amendment 2): G1 — the ORM
column's base type is the Numeric SQLAlchemy actually compiles, never a ``TypeDecorator``'s
informational ``domain`` label, so a wrong precision or scale under a correct label is a finding
(witness: a ``MoneyType`` subclass with scale 5 through ``orm_schema``); G2 — constraint names
are tracked per table from ``CREATE TABLE`` and ``ADD CONSTRAINT``, a ``DROP CONSTRAINT`` of the
primary key clears PK membership, an ``ADD … PRIMARY KEY`` replaces it exactly, and a drop naming
an unknown constraint is REFUSED by name because its effect on the tuples cannot be excluded
(witness: a synthetic statement stream through ``interpret``). Amendment 3 (Codex
production-20260921-1653 §4): an INLINE column ``PRIMARY KEY`` is refused by name — the grammar
the replay recognises is SQLAlchemy ``CreateTable`` output with a table-level primary key, and an
inline key it cannot attribute must not be cleared silently. No broader SQL-completeness credit
is claimed: the interpreter covers the statements this chain emits and refuses the rest by name.

CPU only — never a database. A green run is SOURCE AGREEMENT — the three sources say the same
thing — not applied-schema acceptance (that is the pg suite, ``tests/pg/test_migrations.py``) and
not accounting acceptance; partitions, live enum label order and trigger bodies stay pg-suite
matters.
"""

from __future__ import annotations

import copy
import importlib.util
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import alembic.op
import sqlalchemy as sa
from erev_api.db import migration_ops, tables, types
from sqlalchemy.schema import Computed, DefaultClause

ROOT = Path(__file__).resolve().parents[3]
DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"
VERSIONS = ROOT / "backend" / "erev_api" / "db" / "migrations" / "versions"
SCHEMA = "erev"
ORM = "orm"
MIGRATION = "migration"
DOC = "04"
SOURCES = (ORM, MIGRATION, DOC)
# Q-ORM-2: partition children are out of scope by name; the parents' columns are compared.
PARTITIONED_PARENTS = frozenset({"audit_event", "schedule_line", "subledger_line"})
# The one revision allowed to reach Alembic directly (``op.get_bind()`` to enumerate existing
# partitions; ``op.get_context().autocommit_block()``); any other revision doing so fails by name.
PARTITION_ENUMERATING_REVISIONS = frozenset({"0040"})
# Statement heads the interpreter skips on purpose (grants, RLS, triggers, indexes, seeds).
SKIPPED_HEADS = (
    "GRANT ",
    "REVOKE ",
    "COMMENT ON ",
    "CREATE INDEX ",
    "CREATE UNIQUE INDEX ",
    "DROP INDEX ",
    "CREATE POLICY ",
    "DROP POLICY ",
    "CREATE TRIGGER ",
    "CREATE CONSTRAINT TRIGGER ",
    "DROP TRIGGER ",
    "CREATE FUNCTION ",
    "CREATE OR REPLACE FUNCTION ",
    "DROP FUNCTION ",
    "INSERT INTO ",
    "UPDATE ",
    "DELETE FROM ",
    "SELECT set_config(",
    "CREATE SEQUENCE ",
    "DROP SEQUENCE ",
    "ALTER SEQUENCE ",
    "CREATE SCHEMA ",
    "ALTER TYPE ",
    "DROP TYPE ",
    "DO $$",
    "--",
)
# ``ALTER TABLE`` verbs that never change a column's tuple.
SKIPPED_ALTER_VERBS = (
    "DISABLE TRIGGER ",  # no column/type change; guard enforcement has PostgreSQL tests
    "ENABLE TRIGGER ",
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "NO FORCE ROW LEVEL SECURITY",
    "DISABLE ROW LEVEL SECURITY",
    "VALIDATE CONSTRAINT ",
    "ATTACH PARTITION ",
    "DETACH PARTITION ",
    "OWNER TO ",
    "REPLICA IDENTITY ",
    "SET (",
    "RESET (",
)


@dataclass(frozen=True)
class Divergence:
    """An intentional divergence: the 04 sentence that makes it intentional is mandatory."""

    table: str
    column: str
    attribute: str  # "base_type" | "nullable" | "default" | "pk" | "presence"
    reason: str
    data_model_sentence: str


# Every entry cites the 04 sentence; a stale entry (no actual divergence) fails the guard.
ALLOWLIST: tuple[Divergence, ...] = ()

# 04 table specifications that are specified but not built (no ORM table, no migration): pinned by
# name so that building one moves it into the compared set in the same commit.
UNBUILT_04_TABLES: frozenset[str] = frozenset(
    {
        "ai_model_log",
        "ai_proposal",
        "contract_cost_asset",
        "cost_asset_version",
        "deal_preview",
        "forecast_event_set",
        "forecast_run",
        "material_right",
        # "modification" left this set with 0068_ctr_17_modifications (CTR-17, D-98 140): 17 → 16
        # pinned names; the table is now compared (ORM / migration / 04) like every built table.
        # "integration_connection", "sync_run" and "external_id_map" left this set with
        # 0072_din_12_integrations (DIN-12): 16 → 13 pinned names.
        "portfolio",
        "portfolio_member",
        "scenario",
    }
)


@dataclass(frozen=True)
class Column:
    name: str
    base_type: str
    nullable: bool
    default: str | None  # canonical text; None = not declared
    pk: bool


@dataclass
class Schema:
    source: str
    tables: dict[str, dict[str, Column]] = field(default_factory=dict)
    domains: dict[str, str] = field(default_factory=dict)  # erev.<domain> -> canonical base type
    enums: set[str] = field(default_factory=set)  # erev.<enum>
    # table -> constraint name -> "pk" | "other" (G2: a DROP CONSTRAINT must name a known one)
    constraints: dict[str, dict[str, str]] = field(default_factory=dict)


# --- canonical forms -------------------------------------------------------------------------

_TYPE_ALIASES = {
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamp",
    "character varying": "varchar",
    "double precision": "double precision",
    "int": "integer",
    "int4": "integer",
    "int8": "bigint",
    "int2": "smallint",
    "bool": "boolean",
}


def canonical_type(text: str, domains: Mapping[str, str]) -> str:
    """Lower-cased, whitespace-collapsed type; domains resolved to their base; arrays ``x[]``."""
    value = re.sub(r"\s+", " ", text.strip()).lower().replace("( ", "(").replace(" )", ")")
    value = re.sub(r",\s+", ",", value)
    if value.endswith("[]"):
        return canonical_type(value[:-2], domains) + "[]"
    if value.startswith("character("):
        value = "char(" + value[len("character(") :]
    value = _TYPE_ALIASES.get(value, value)
    if value in domains:
        return domains[value]
    return value


def canonical_default(text: str | None) -> str | None:
    """Default text without a trailing cast, whitespace collapsed; None when not declared."""
    if text is None:
        return None
    value = re.sub(r"\s+", " ", text.strip())
    value = re.sub(r"::[a-z_]+(\[\])?$", "", value)
    return value


# --- source 1: the ORM ------------------------------------------------------------------------

_PG: sa.Dialect = sa.make_url("postgresql://").get_dialect()()


def orm_schema(metadata: sa.MetaData = tables.metadata) -> Schema:
    """The ORM's columns from the type SQLAlchemy actually compiles (G1, D-98 136 amendment 2): a
    ``TypeDecorator``'s informational ``domain`` label is never substituted, so a wrong precision or
    scale under a correct label is a base-type divergence."""
    schema = Schema(ORM)
    for table in metadata.tables.values():
        assert table.schema == SCHEMA, table
        columns: dict[str, Column] = {}
        for column in table.columns:
            type_ = column.type
            rendered = str(type_.compile(dialect=_PG))
            default: str | None = None
            if isinstance(column.server_default, Computed):
                default = "GENERATED ALWAYS AS (" + str(column.server_default.sqltext) + ") STORED"
            elif isinstance(column.server_default, DefaultClause):
                arg = column.server_default.arg
                default = arg.text if hasattr(arg, "text") else f"'{arg}'"
            columns[column.name] = Column(
                column.name,
                canonical_type(rendered, {}),
                bool(column.nullable),
                canonical_default(default),
                bool(column.primary_key),
            )
        schema.tables[table.name] = columns
    return schema


# --- source 2: the Alembic chain, replayed offline ---------------------------------------------


class _NoRows:
    def __iter__(self) -> Iterator[Any]:
        return iter(())

    def fetchall(self) -> list[Any]:
        return []

    def scalar(self) -> None:
        return None

    def mappings(self) -> _NoRows:
        return self


class _StubBind:
    """0040's partition enumeration sees an empty schema (no partitions before the chain runs)."""

    def execute(self, *_: Any, **__: Any) -> _NoRows:
        return _NoRows()

    def execution_options(self, **_: Any) -> _StubBind:
        return self

    def exec_driver_sql(self, *_: Any, **__: Any) -> _NoRows:
        return _NoRows()


class _StubContext:
    class _Block:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_: Any) -> None:
            return None

    def autocommit_block(self) -> _StubContext._Block:
        return self._Block()


@dataclass
class Replay:
    order: tuple[str, ...]
    statements: tuple[tuple[str, str], ...]  # (revision, statement text)
    direct_alembic: dict[str, set[str]]  # revision -> {"get_bind", "get_context"}


def _load_revisions() -> dict[str, ModuleType]:
    modules: dict[str, ModuleType] = {}
    for path in sorted(VERSIONS.glob("[0-9]*.py")):
        name = f"erev_arc15_revision_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None, path
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules[module.revision] = module
    return modules


def revision_order(modules: Mapping[str, ModuleType]) -> tuple[str, ...]:
    """The single chain from the root (``down_revision`` None) to the single head."""
    by_down: dict[str | None, list[str]] = {}
    for revision, module in modules.items():
        by_down.setdefault(module.down_revision, []).append(revision)
    for down, revisions in by_down.items():
        assert len(revisions) == 1, (
            f"two revisions share down_revision {down!r}: {sorted(revisions)}"
        )
    order: list[str] = []
    current: str | None = None
    while (nxt := by_down.get(current)) is not None:
        order.append(nxt[0])
        current = nxt[0]
    assert set(order) == set(modules), sorted(set(modules) - set(order))
    return tuple(order)


@cache
def replay_chain() -> Replay:
    modules = _load_revisions()
    order = revision_order(modules)
    direct: dict[str, set[str]] = {}
    current = {"revision": ""}
    saved = (alembic.op.get_bind, alembic.op.get_context)

    def get_bind() -> _StubBind:
        direct.setdefault(current["revision"], set()).add("get_bind")
        return _StubBind()

    def get_context() -> _StubContext:
        direct.setdefault(current["revision"], set()).add("get_context")
        return _StubContext()

    alembic.op.get_bind = get_bind  # type: ignore[assignment]
    alembic.op.get_context = get_context  # type: ignore[assignment]
    recorded: list[tuple[str, str]] = []
    try:
        for revision in order:
            current["revision"] = revision
            with migration_ops.recording() as statements:
                modules[revision].upgrade()
            recorded += [(revision, statement) for statement in statements]
    finally:
        alembic.op.get_bind, alembic.op.get_context = saved
    return Replay(order, tuple(recorded), direct)


_TABLE = rf"(?:{SCHEMA}\.)?([a-z_][a-z0-9_]*)"


def _column_clause(clause: str, domains: Mapping[str, str], where: str = "") -> Column:
    """``name TYPE [DEFAULT expr] [NOT NULL | NULL] [GENERATED ALWAYS AS (…) STORED]``.

    An inline ``PRIMARY KEY`` on a column is REFUSED by name (amendment 3): the grammar the replay
    recognises is SQLAlchemy ``CreateTable`` output, whose primary key is a table-level constraint;
    an inline key the interpreter cannot attribute must not be cleared silently.
    """
    text = re.sub(r"\s+", " ", clause.strip())
    if re.search(r"\bPRIMARY KEY\b", text, flags=re.I):
        raise AssertionError(
            f"{where}inline column PRIMARY KEY is outside the CreateTable grammar the replay "
            f"recognises: {text[:80]!r}"
        )
    # an inline column constraint (SQLAlchemy renders column-level CheckConstraints inline) is
    # not part of the tuple
    text = re.sub(r"\s+(?:CONSTRAINT \S+ )?CHECK \(.*\)$", "", text, flags=re.I)
    name, rest = text.split(" ", 1)
    nullable = True
    default: str | None = None
    generated = re.search(r"\s+GENERATED ALWAYS AS \((.*)\) STORED\b", rest, flags=re.I)
    if generated:
        default = "GENERATED ALWAYS AS (" + generated.group(1) + ") STORED"
        rest = rest[: generated.start()] + rest[generated.end() :]
    if re.search(r"\bNOT NULL\b", rest, flags=re.I):
        nullable = False
        rest = re.sub(r"\s*\bNOT NULL\b", "", rest, flags=re.I)
    elif re.search(r"\bNULL\b", rest, flags=re.I):
        rest = re.sub(r"\s*\bNULL\b", "", rest, flags=re.I)
    if (m := re.search(r"\s+DEFAULT\s+(.+)$", rest, flags=re.I)) is not None:
        default = m.group(1).strip()
        rest = rest[: m.start()]
    return Column(name, canonical_type(rest, domains), nullable, canonical_default(default), False)


_CONSTRAINT_KINDS = ("PRIMARY KEY", "FOREIGN KEY", "CHECK", "UNIQUE", "EXCLUDE")


def _record_constraint(schema: Schema, table: str, name: str, kind: str) -> None:
    schema.constraints.setdefault(table, {})[name] = (
        "pk" if kind.upper() == "PRIMARY KEY" else "other"
    )


def _set_pk(table: dict[str, Column], members: set[str], revision: str, name: str) -> None:
    """The primary key becomes exactly ``members`` (G2: a drop clears it, an add replaces it)."""
    for column_name in members:
        assert column_name in table, (
            f"{revision}: {name} PRIMARY KEY names unknown column {column_name}"
        )
    for column_name, column in list(table.items()):
        table[column_name] = Column(
            column_name, column.base_type, column.nullable, column.default, column_name in members
        )


def _create_table(schema: Schema, statement: str, revision: str) -> None:
    if re.search(r"\bPARTITION OF\b", statement):
        of = re.search(rf"PARTITION OF {_TABLE}", statement)
        assert of is not None, f"{revision}: {statement[:80]!r}"
        assert of.group(1) in PARTITIONED_PARENTS, f"{revision}: partition of an unlisted parent"
        return  # Q-ORM-2: children out of scope by name
    head, _, body = statement.partition("(")
    match = re.fullmatch(rf"CREATE TABLE (?:IF NOT EXISTS )?{_TABLE}\s*", head)
    assert match is not None, (
        f"{revision}: CREATE TABLE head the replay does not recognise: {head!r}"
    )
    name = match.group(1)
    close = body.rfind("\n)")  # the column list closes on its own line; PARTITION BY may follow
    assert close > 0, f"{revision}: CREATE TABLE {name} without a closing line"
    if re.search(r"\)\s*PARTITION BY\b", body[close:]):
        assert name in PARTITIONED_PARENTS, f"{revision}: {name} is partitioned but unlisted"
    entries = [entry.strip().rstrip(",").strip() for entry in body[:close].split("\n")]
    columns: dict[str, Column] = {}
    pk: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        upper = entry.upper()
        named = re.match(
            r"CONSTRAINT (\w+) (PRIMARY KEY|FOREIGN KEY|CHECK|UNIQUE|EXCLUDE)\b", entry, re.I
        )
        if named is not None:
            _record_constraint(schema, name, named.group(1), named.group(2))
        if upper.startswith("PRIMARY KEY") or (
            named is not None and named.group(2).upper() == "PRIMARY KEY"
        ):
            inner = re.search(r"\((.*?)\)", entry[entry.upper().index("PRIMARY KEY") :])
            assert inner is not None, f"{revision}: {entry!r}"
            pk |= {c.strip() for c in inner.group(1).split(",")}
            if named is None:
                _record_constraint(schema, name, f"{name}_pkey", "PRIMARY KEY")
        elif named is not None or upper.startswith(("FOREIGN KEY", "UNIQUE", "CHECK ")):
            continue
        else:
            # an inline column constraint carries its own name (dropped later by that name)
            inline = re.search(r"\bCONSTRAINT (\w+) (CHECK|UNIQUE)\b", entry, re.I)
            if inline is not None:
                _record_constraint(schema, name, inline.group(1), inline.group(2))
            column = _column_clause(entry, schema.domains, f"{revision}: CREATE TABLE {name}: ")
            columns[column.name] = column
    assert name not in schema.tables, f"{revision}: CREATE TABLE {name} but it exists"
    schema.tables[name] = columns
    _set_pk(columns, pk, revision, name)


def _split_actions(rest: str) -> list[str]:
    """Top-level comma-separated ALTER TABLE actions (commas inside parentheses stay put)."""
    actions: list[str] = []
    depth = 0
    current: list[str] = []
    for char in rest:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            actions.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    actions.append("".join(current).strip())
    return [action for action in actions if action]


def _alter_table(schema: Schema, flat: str, revision: str) -> None:
    m = re.fullmatch(rf"ALTER TABLE (?:ONLY )?{_TABLE} (.*)", flat, flags=re.S)
    assert m is not None, flat
    name, rest = m.group(1), m.group(2).strip()
    if name not in schema.tables:
        assert any(name.startswith(p + "_") for p in PARTITIONED_PARENTS), (
            f"{revision}: ALTER TABLE of unknown table {name}"
        )
        return  # a partition child (Q-ORM-2)
    for action in _split_actions(rest):
        _alter_action(schema, name, action, revision)


def _alter_action(schema: Schema, name: str, action: str, revision: str) -> None:
    table = schema.tables[name]
    upper = action.upper()
    if any(upper.startswith(verb) for verb in SKIPPED_ALTER_VERBS):
        return
    if (
        m := re.match(r"ADD CONSTRAINT (\w+) (FOREIGN KEY|CHECK|UNIQUE|EXCLUDE)\b", action, re.I)
    ) is not None:
        _record_constraint(schema, name, m.group(1), m.group(2))
        return
    if (
        m := re.fullmatch(r"ADD (?:CONSTRAINT (\w+) )?PRIMARY KEY \((.*?)\)", action, re.I)
    ) is not None:
        constraint = m.group(1) or f"{name}_pkey"
        _record_constraint(schema, name, constraint, "PRIMARY KEY")
        _set_pk(table, {c.strip() for c in m.group(2).split(",")}, revision, name)
        return
    if (
        m := re.fullmatch(
            r"DROP CONSTRAINT (?:IF EXISTS )?(\w+)(?: (?:CASCADE|RESTRICT))?", action, re.I
        )
    ) is not None:
        known = schema.constraints.get(name, {})
        kind = known.pop(m.group(1), None)
        if kind == "pk":
            _set_pk(table, set(), revision, name)  # G2: the key is gone until one is added again
            return
        if kind == "other":
            return
        raise AssertionError(
            f"{revision}: ALTER TABLE {name} DROP CONSTRAINT {m.group(1)}: unknown constraint — "
            "its effect on the column tuples cannot be excluded"
        )
    if upper.startswith("ADD COLUMN "):
        where = f"{revision}: ALTER TABLE {name} ADD COLUMN: "
        column = _column_clause(action[len("ADD COLUMN ") :], schema.domains, where)
        assert column.name not in table, f"{revision}: {name}.{column.name} added twice"
        table[column.name] = column
        return
    if (
        m := re.fullmatch(r"DROP COLUMN (?:IF EXISTS )?(\w+)(?: CASCADE)?", action, re.I)
    ) is not None:
        assert m.group(1) in table, f"{revision}: {name}.{m.group(1)} dropped but unknown"
        del table[m.group(1)]
        return
    if (m := re.fullmatch(r"RENAME COLUMN (\w+) TO (\w+)", action, re.I)) is not None:
        old, new = m.groups()
        column = table.pop(old)
        table[new] = Column(new, column.base_type, column.nullable, column.default, column.pk)
        return
    if (m := re.fullmatch(r"RENAME TO (\w+)", action, re.I)) is not None:
        schema.tables[m.group(1)] = schema.tables.pop(name)
        schema.constraints[m.group(1)] = schema.constraints.pop(name, {})
        return
    if (m := re.fullmatch(r"ALTER COLUMN (\w+) (.*)", action, re.I)) is not None:
        column_name, change = m.group(1), m.group(2).strip()
        column = table[column_name]
        change_upper = change.upper()
        if change_upper == "SET NOT NULL":
            table[column_name] = Column(
                column_name, column.base_type, False, column.default, column.pk
            )
        elif change_upper == "DROP NOT NULL":
            table[column_name] = Column(
                column_name, column.base_type, True, column.default, column.pk
            )
        elif change_upper.startswith("SET DEFAULT "):
            default = canonical_default(change[len("SET DEFAULT ") :])
            table[column_name] = Column(
                column_name, column.base_type, column.nullable, default, column.pk
            )
        elif change_upper == "DROP DEFAULT":
            table[column_name] = Column(
                column_name, column.base_type, column.nullable, None, column.pk
            )
        elif change_upper.startswith(("TYPE ", "SET DATA TYPE ")):
            new_type = re.sub(r"^(SET DATA )?TYPE ", "", change, flags=re.I)
            new_type = re.sub(r"\s+USING\s+.*$", "", new_type, flags=re.I)
            base = canonical_type(new_type, schema.domains)
            table[column_name] = Column(
                column_name, base, column.nullable, column.default, column.pk
            )
        else:
            raise AssertionError(
                f"{revision}: unrecognised ALTER COLUMN on {name}.{column_name}: {change[:80]}"
            )
        return
    raise AssertionError(f"{revision}: unrecognised ALTER TABLE {name} action: {action[:100]}")


def interpret(statements: Iterable[tuple[str, str]]) -> Schema:
    """The final schema of an ordered statement stream ``(revision, statement)``; the migration
    source when fed the replayed chain, and the G2 witnesses' entry point for synthetic streams."""
    schema = Schema(MIGRATION)
    for revision, statement in statements:
        stripped = statement.strip()
        flat = re.sub(r"\s+", " ", stripped)
        if stripped.upper().startswith("CREATE TABLE "):
            _create_table(schema, stripped, revision)
        elif (
            m := re.fullmatch(rf"DROP TABLE (?:IF EXISTS )?{_TABLE}(?: CASCADE)?", flat, flags=re.I)
        ) is not None:
            name = m.group(1)
            if name in schema.tables:
                del schema.tables[name]
                schema.constraints.pop(name, None)
            else:
                assert any(name.startswith(p + "_") for p in PARTITIONED_PARENTS), (
                    f"{revision}: DROP of unknown table {name}"
                )
        elif flat.upper().startswith("ALTER TABLE "):
            _alter_table(schema, flat, revision)
        elif (
            m := re.match(
                rf"CREATE DOMAIN {SCHEMA}\.(\w+) AS (.+?)(?: CONSTRAINT | CHECK |$)",
                flat,
                flags=re.I,
            )
        ) is not None:
            schema.domains[f"{SCHEMA}.{m.group(1)}"] = canonical_type(m.group(2), {})
        elif (
            m := re.fullmatch(rf"ALTER DOMAIN {SCHEMA}\.(\w+) RENAME TO (\w+)", flat, flags=re.I)
        ) is not None:
            schema.domains[f"{SCHEMA}.{m.group(2)}"] = schema.domains.pop(f"{SCHEMA}.{m.group(1)}")
        elif flat.upper().startswith("ALTER DOMAIN "):
            continue  # constraint changes on a domain do not change its base
        elif (m := re.match(rf"CREATE TYPE {SCHEMA}\.(\w+) AS ENUM", flat, flags=re.I)) is not None:
            schema.enums.add(f"{SCHEMA}.{m.group(1)}")
        elif any(flat.startswith(head) for head in SKIPPED_HEADS):
            continue
        else:
            raise AssertionError(
                f"{revision}: statement kind the replay does not recognise: {flat[:100]}"
            )
    return schema


@cache
def migration_schema() -> Schema:
    return interpret(replay_chain().statements)


# --- source 3: 04-DATA_MODEL ------------------------------------------------------------------


@cache
def data_model() -> str:
    return DATA_MODEL.read_text(encoding="utf-8")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


_SC_DEF = re.compile(
    r"`(\w+) (\S+)( NOT NULL| NULL)?( PRIMARY KEY)?(?: DEFAULT (\S+))?(?: CHECK \([^`]*\))?`"
)


@cache
def standard_sets() -> dict[str, tuple[Column, ...]]:
    """04 §1.3's own column definitions per standard set (types as written; no migration input)."""
    text = data_model()
    section = text[text.index("### 1.3 Standard column sets") : text.index("### 1.4 ")]
    sets: dict[str, tuple[Column, ...]] = {}
    for line in section.splitlines():
        if not line.startswith("| SC-"):
            continue
        name, definition = _cells(line)[0], _cells(line)[1]
        if " or " in definition:
            continue  # SC-G offers alternatives and is never used as a row
        columns = []
        for m in _SC_DEF.finditer(definition):
            col, type_, null, pk, default = m.groups()
            if type_.startswith("("):
                continue  # a reference such as `tenant (id)`, not a column definition
            columns.append(
                Column(col, type_, (null or "").strip() != "NOT NULL", default, pk is not None)
            )
        sets[name] = tuple(columns)
    assert {"SC-T", "SC-C", "SC-M", "SC-V"} <= set(sets), sorted(sets)
    return sets


@cache
def data_model_specs() -> dict[str, tuple[tuple[Column, ...], frozenset[str]]]:
    """table -> (columns as written, PK column names)."""
    specs: dict[str, tuple[tuple[Column, ...], frozenset[str]]] = {}
    for block in re.finditer(
        r"^### (T-[A-Z]+-\d+[a-z]?) `([a-z_]+)`\n(.*?)(?=^### |\Z)", data_model(), flags=re.M | re.S
    ):
        table, body = block.group(2), block.group(3)
        header = re.search(
            r"^\| Column \| Type \| Null \| Default \|.*\n\|---.*\n", body, flags=re.M
        )
        if header is None:
            continue
        rows: list[Column] = []
        rest = body[header.end() :]
        for line in rest.splitlines():
            if not line.startswith("|"):
                break
            cells = _cells(line)
            if cells[0].startswith("SC-"):
                for set_name in (s.strip() for s in cells[0].split(",")):
                    rows += list(standard_sets()[set_name])
                continue
            m = re.fullmatch(r"`([a-z0-9_]+)`", cells[0])
            assert m is not None, f"{table}: {line}"
            notes = cells[4] if len(cells) > 4 else ""
            default = cells[3].strip("`") or None
            generated = re.search(r"`(GENERATED ALWAYS AS \(.*\) STORED)`", notes)
            if generated is not None and default is None:
                default = generated.group(
                    1
                )  # 04 §1.3 (rev 1.69): the notes-cell expression is the default
            rows.append(
                Column(
                    m.group(1),
                    cells[1],
                    cells[2] == "Y",
                    default,
                    bool(re.search(r"\bPK\b", notes)),
                )
            )
        outside = "\n".join(line for line in body.splitlines() if not line.startswith("|"))
        pk_statement = re.search(r"PRIMARY KEY \(([^)]*)\)", outside)
        pk = (
            {c.strip().strip("`") for c in pk_statement.group(1).split(",")}
            if pk_statement
            else set()
        )
        pk |= {row.name for row in rows if row.pk}
        assert table not in specs, f"04 specifies {table} twice"
        specs[table] = (tuple(rows), frozenset(pk))
    return specs


def doc_schema(domains: Mapping[str, str]) -> Schema:
    schema = Schema(DOC)
    for table, (rows, pk) in data_model_specs().items():
        columns: dict[str, Column] = {}
        for row in rows:
            columns[row.name] = Column(
                row.name,
                canonical_type(row.default and row.base_type or row.base_type, domains),
                row.nullable,
                canonical_default(row.default),
                row.name in pk,
            )
        schema.tables[table] = columns
    return schema


# --- the comparison ---------------------------------------------------------------------------


def compare(orm: Schema, migration: Schema, doc: Schema) -> list[str]:
    findings: list[str] = []
    built = set(orm.tables) | set(migration.tables)
    for table in sorted(set(orm.tables) ^ set(migration.tables)):
        findings.append(
            f"{table}: table presence orm={table in orm.tables} | "
            f"migration={table in migration.tables}"
        )
    for table in sorted(built - set(doc.tables)):
        findings.append(f"{table}: no 04 table specification")
    unbuilt = set(doc.tables) - built
    if unbuilt != UNBUILT_04_TABLES:
        findings.append(
            "04 specified-but-unbuilt tables differ from the pin: "
            f"+{sorted(unbuilt - UNBUILT_04_TABLES)} -{sorted(UNBUILT_04_TABLES - unbuilt)}"
        )
    for table in sorted(set(orm.tables) & set(migration.tables) & set(doc.tables)):
        by_source = {
            ORM: orm.tables[table],
            MIGRATION: migration.tables[table],
            DOC: doc.tables[table],
        }
        for column in sorted(set().union(*(set(cols) for cols in by_source.values()))):
            present = {source: column in cols for source, cols in by_source.items()}
            if not all(present.values()):
                findings.append(
                    f"{table}.{column} presence: "
                    + " | ".join(f"{s}={present[s]}" for s in SOURCES)
                )
                continue
            values = {source: by_source[source][column] for source in SOURCES}
            for attribute in ("base_type", "nullable", "pk"):
                got = {source: getattr(values[source], attribute) for source in SOURCES}
                if len(set(got.values())) > 1:
                    findings.append(
                        f"{table}.{column} {attribute}: "
                        + " | ".join(f"{s}={got[s]}" for s in SOURCES)
                    )
            defaults = {source: values[source].default for source in SOURCES}
            if defaults[MIGRATION] != defaults[DOC] or (
                defaults[ORM] is not None and defaults[ORM] != defaults[MIGRATION]
            ):
                findings.append(
                    f"{table}.{column} default: "
                    + " | ".join(f"{s}={defaults[s]!r}" for s in SOURCES)
                )
    return findings


def apply_allowlist(findings: list[str]) -> tuple[list[str], list[Divergence]]:
    """Findings not covered by the allowlist, and allowlist entries that cover nothing (stale)."""
    remaining: list[str] = []
    used: set[Divergence] = set()
    for finding in findings:
        head = finding.split(":")[0]
        matched = [
            d
            for d in ALLOWLIST
            if head == f"{d.table}.{d.column} {d.attribute}"
            or head == f"{d.table}.{d.column} {d.attribute}"
        ]
        if matched:
            used.update(matched)
        else:
            remaining.append(finding)
    return remaining, [d for d in ALLOWLIST if d not in used]


@cache
def real_schemas() -> tuple[Schema, Schema, Schema]:
    migration = migration_schema()
    return orm_schema(), migration, doc_schema(migration.domains)


# --- the guard --------------------------------------------------------------------------------


def test_dg_arc_15_replay_is_one_chain_and_alembic_is_reached_only_by_0040() -> None:
    replay = replay_chain()
    assert replay.order[0] == "0001" and len(replay.order) == len(set(replay.order))
    assert set(replay.direct_alembic) <= PARTITION_ENUMERATING_REVISIONS, replay.direct_alembic
    assert len(replay.statements) > 1000


def test_dg_arc_15_every_allowlist_entry_cites_04() -> None:
    for entry in ALLOWLIST:
        assert entry.data_model_sentence and entry.data_model_sentence in data_model(), entry


def test_dg_arc_15_orm_migration_and_04_agree() -> None:
    orm, migration, doc = real_schemas()
    remaining, stale = apply_allowlist(compare(orm, migration, doc))
    assert stale == [], f"allowlist entries that describe no actual divergence: {stale}"
    assert remaining == [], "\n".join(remaining)


# --- fail-first witnesses on scratch copies ------------------------------------------------------


def test_witness_orm_text_where_the_chain_and_04_say_an_enum_is_named() -> None:
    """The batch-#5 class: a ``book_code`` column typed ``Text()`` in the ORM on a SCRATCH copy."""
    _, migration, doc = real_schemas()
    scratch = sa.MetaData(schema=SCHEMA)
    for table in tables.metadata.tables.values():
        table.to_metadata(scratch)
    copy_table = scratch.tables[f"{SCHEMA}.contract_version"]
    copy_table.columns["book_code"].type = sa.Text()
    findings = compare(orm_schema(scratch), migration, doc)
    base = compare(*real_schemas())
    new = sorted(set(findings) - set(base))
    expected = "contract_version.book_code base_type: orm=text | migration=erev.book_code | 04="
    assert new == [expected + "erev.book_code"]


def test_witness_migration_nullability_flip_names_the_migration() -> None:
    orm, migration, doc = real_schemas()
    scratch = copy.deepcopy(migration)
    column = scratch.tables["contract"]["external_id"]
    scratch.tables["contract"]["external_id"] = Column(
        column.name, column.base_type, not column.nullable, column.default, column.pk
    )
    new = sorted(set(compare(orm, scratch, doc)) - set(compare(*real_schemas())))
    flipped = not column.nullable
    assert new == [
        f"contract.external_id nullable: orm={column.nullable} | migration={flipped} | "
        f"04={column.nullable}"
    ]


def test_dg_arc_15_orm_domain_labels_agree_with_the_chain() -> None:
    """G1 belt and braces: every ``_ExactNumeric`` label (``MoneyType.domain`` …) resolves in the
    chain to exactly the Numeric the ORM compiles — the label is informational, the compiled type
    is what the guard compares."""
    migration = migration_schema()
    for type_ in (types.MoneyType(), types.ExactType(), types.FxRateType()):
        compiled = canonical_type(str(type_.compile(dialect=_PG)), {})
        assert migration.domains[type_.domain] == compiled, (type_.domain, compiled)


class _WrongScaleMoney(types.MoneyType):
    """A money type carrying the correct ``erev.money`` label over the WRONG scale (G1 witness)."""

    cache_ok = True
    scale = 5


def test_witness_orm_wrong_scale_under_a_correct_domain_label_is_named() -> None:
    """G1: the ORM's compiled ``NUMERIC(24, 5)`` disagrees with the chain's ``numeric(24,4)`` even
    though the type still says ``erev.money`` — THROUGH ``orm_schema`` on a scratch copy."""
    _, migration, doc = real_schemas()
    table_name, column_name = next(
        (table.name, column.name)
        for table in tables.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, types.MoneyType)
    )
    scratch = sa.MetaData(schema=SCHEMA)
    for table in tables.metadata.tables.values():
        table.to_metadata(scratch)
    scratch.tables[f"{SCHEMA}.{table_name}"].columns[column_name].type = _WrongScaleMoney()
    new = sorted(set(compare(orm_schema(scratch), migration, doc)) - set(compare(*real_schemas())))
    assert new == [
        f"{table_name}.{column_name} base_type: orm=numeric(24,5) | migration=numeric(24,4) | "
        "04=numeric(24,4)"
    ]


def test_witness_migration_primary_key_drop_and_replacement_are_tracked() -> None:
    """G2, through the migration parser path on a synthetic stream: a dropped primary key clears
    PK membership, a replacement sets it exactly, and a DROP CONSTRAINT naming an unknown
    constraint is REFUSED by name (its effect on the tuples cannot be excluded)."""
    create = (
        "CREATE TABLE erev.t (\n\ta UUID NOT NULL, \n\tb UUID NOT NULL, \n\tPRIMARY KEY (a, b)\n)"
    )
    schema = interpret([("r1", create)])
    assert {c for c, v in schema.tables["t"].items() if v.pk} == {"a", "b"}
    schema = interpret([("r1", create), ("r2", "ALTER TABLE erev.t DROP CONSTRAINT t_pkey")])
    assert {c for c, v in schema.tables["t"].items() if v.pk} == set()
    schema = interpret(
        [
            ("r1", create),
            (
                "r2",
                "ALTER TABLE erev.t DROP CONSTRAINT t_pkey, ADD CONSTRAINT t_pkey PRIMARY KEY (a)",
            ),
        ]
    )
    assert {c for c, v in schema.tables["t"].items() if v.pk} == {"a"}
    try:
        interpret([("r1", create), ("r2", "ALTER TABLE erev.t DROP CONSTRAINT mystery")])
    except AssertionError as refused:
        assert "r2: ALTER TABLE t DROP CONSTRAINT mystery: unknown constraint" in str(refused)
    else:
        raise AssertionError("an unknown constraint drop was not refused")


def test_witness_inline_column_primary_key_is_refused_by_name() -> None:
    """Amendment 3: an inline ``PRIMARY KEY`` on a column — outside the CreateTable grammar — is
    refused naming the revision, the table and the clause, in CREATE TABLE and in ADD COLUMN."""
    inline = "CREATE TABLE erev.t (\n\ta UUID NOT NULL PRIMARY KEY, \n\tb UUID\n)"
    try:
        interpret([("r1", inline)])
    except AssertionError as refused:
        assert str(refused).startswith("r1: CREATE TABLE t: inline column PRIMARY KEY is outside")
    else:
        raise AssertionError("an inline column PRIMARY KEY was not refused")
    plain = "CREATE TABLE erev.t (\n\ta UUID NOT NULL, \n\tPRIMARY KEY (a)\n)"
    try:
        interpret([("r1", plain), ("r2", "ALTER TABLE erev.t ADD COLUMN c UUID PRIMARY KEY")])
    except AssertionError as refused:
        assert str(refused).startswith("r2: ALTER TABLE t ADD COLUMN: inline column PRIMARY KEY")
    else:
        raise AssertionError("an inline column PRIMARY KEY in ADD COLUMN was not refused")
