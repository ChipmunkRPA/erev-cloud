"""Migration helpers used by every Alembic revision (docs/dev-guide.md §6.5; 04 §1, §14, §18).

Revisions are handwritten (DG-MIG-02) and create their objects only through these helpers, so
naming (NC-16), row-level security (04 §1.4), immutability classes and grants (04 §1.5, §14.2) and
partitions (04 §1.6) are written once. Statements run on the migration connection
(``op.get_bind()``). Tests run helpers on their own connection with ``bound_to`` or collect the SQL
without running it with ``recording``.

Identifiers are validated against NC-02 before they reach SQL; enum labels are quoted.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import sqlalchemy as sa
from alembic import op
from mako.template import Template
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import UserDefinedType

from erev_api.db.session import APP_ROLE, OWNER_ROLE

SCHEMA: Final = "erev"
MIGRATIONS_DIR: Final = Path(__file__).resolve().parent / "migrations"
VERSIONS_DIR: Final = MIGRATIONS_DIR / "versions"

ImClass = Literal["IM-A", "IM-S", "IM-P", "IM-M", "IM-X", "IM-E"]
RlsTemplate = Literal["RLS-T", "RLS-TE", "RLS-TN", "RLS-TM"]
StandardSet = Literal["SC-C", "SC-M", "SC-V"]

_TABLE_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{0,47}$")  # NC-02
_OBJECT_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}$")  # PostgreSQL NAMEDATALEN - 1
_ENUM_LABEL: Final = re.compile(r"^[A-Za-z0-9_.:/ -]{1,63}$")
_MONTH: Final = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_EVENT: Final = re.compile(
    r"^(INSERT|DELETE|TRUNCATE|UPDATE( OF [a-z][a-z0-9_]*(, [a-z][a-z0-9_]*)*)?)$"
)
_DIALECT: Final = postgresql.dialect()  # type: ignore[no-untyped-call]

# 04 §1.6: partitioned parents and their partition columns.
PARTITION_COLUMNS: Final = {
    "audit_event": "occurred_at",
    "schedule_line": "period_end_date",
    "subledger_line": "period_end_date",
}
# 04 §1.5 and §14.2: erev_app table privileges per immutability class.
PartitionColumn = Literal["period_end_date", "occurred_at"]
# DB-01: classes whose tables, and every child partition of them, carry the TRUNCATE trigger.
TRUNCATE_GUARDED_CLASSES: Final = frozenset({"IM-A", "IM-S"})
CLASS_PRIVILEGES: Final[dict[str, tuple[str, ...]]] = {
    "IM-A": ("SELECT", "INSERT"),
    "IM-S": ("SELECT", "INSERT", "UPDATE"),
    "IM-P": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "IM-M": ("SELECT", "INSERT", "UPDATE"),
    "IM-X": ("SELECT", "INSERT", "UPDATE"),
    "IM-E": ("SELECT", "INSERT", "UPDATE", "DELETE"),
}

_sink: ContextVar[Callable[[str], None] | None] = ContextVar("erev_migration_sink", default=None)
_bind: ContextVar[sa.Connection | None] = ContextVar("erev_migration_bind", default=None)


# --- execution ------------------------------------------------------------------------------


def _connection() -> sa.Connection:
    bound = _bind.get()
    return bound if bound is not None else op.get_bind()


def execute(statement: str) -> None:
    """Run one DDL statement on the migration connection, or record it under ``recording``."""
    sink = _sink.get()
    if sink is not None:
        sink(statement)
        return
    # Driver-level execution without parameters: no bind-parameter parsing of ':' or '%'.
    _connection().execution_options(no_parameters=True).exec_driver_sql(statement)


@contextmanager
def bound_to(connection: sa.Connection) -> Iterator[None]:
    """Run helpers on ``connection`` instead of the Alembic migration connection (tests)."""
    token = _bind.set(connection)
    try:
        yield
    finally:
        _bind.reset(token)


@contextmanager
def recording() -> Iterator[list[str]]:
    """Collect the statements helpers would run, without a database (tests)."""
    statements: list[str] = []
    token = _sink.set(statements.append)
    try:
        yield statements
    finally:
        _sink.reset(token)


# --- names ----------------------------------------------------------------------------------


def table_name(name: str) -> str:
    if not _TABLE_NAME.fullmatch(name):
        raise ValueError(f"invalid table or column name {name!r} (NC-02)")
    return name


def object_name(name: str) -> str:
    if not _OBJECT_NAME.fullmatch(name):
        raise ValueError(f"invalid object name {name!r}")
    return name


def qualified(name: str) -> str:
    return f"{SCHEMA}.{object_name(name)}"


def enum_literal(label: str) -> str:
    if not _ENUM_LABEL.fullmatch(label):
        raise ValueError(f"invalid enum label {label!r}")
    return "'" + label.replace("'", "''") + "'"


def _column_list(columns: Sequence[str]) -> str:
    if not columns:
        raise ValueError("a column list must not be empty")
    return ", ".join(table_name(column) for column in columns)


class NamedType(UserDefinedType[Any]):
    """A column type rendered by name, for domains and enum types in schema erev."""

    cache_ok = True

    def __init__(self, name: str) -> None:
        self.name = name

    def get_col_spec(self, **_: Any) -> str:
        return self.name


# --- schema foundation (04 §18 step 0001) ---------------------------------------------------

# TY-01 to TY-10 (04 §1.2).
DOMAINS: Final[tuple[tuple[str, str, str], ...]] = (
    ("money", "numeric(24,4)", "VALUE <> 'NaN'::numeric"),
    ("exact", "numeric(38,18)", "VALUE <> 'NaN'::numeric"),
    ("fx_rate", "numeric(28,12)", "VALUE <> 'NaN'::numeric AND VALUE > 0"),
    ("currency_code", "char(3)", "VALUE ~ '^[A-Z]{3}$'"),
    ("sha256", "char(64)", "VALUE ~ '^[0-9a-f]{64}$'"),
    ("code", "text", "VALUE ~ '^[A-Za-z0-9][A-Za-z0-9 _.:/#()+-]{0,127}$'"),
    ("label", "text", "char_length(VALUE) BETWEEN 1 AND 400"),
    ("memo", "text", "char_length(VALUE) <= 4000"),
    ("email", "text", r"VALUE = lower(VALUE) AND VALUE ~ '^[^@\s]+@[^@\s]+$'"),
    ("tz_name", "text", "VALUE ~ '^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$'"),
)
SEQUENCES: Final = ("contract_event_record_seq", "security_event_seq")

# 04 §1.4 helper functions, NC-18 attributes.
RLS_FUNCTIONS: Final[tuple[tuple[str, str], ...]] = (
    (
        "current_tenant_id()",
        "RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path = erev, pg_catalog\n"
        "  AS $fn$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $fn$",
    ),
    (
        "current_user_id()",
        "RETURNS uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path = erev, pg_catalog\n"
        "  AS $fn$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $fn$",
    ),
    (
        "entity_in_scope(e uuid)",
        "RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path = erev, pg_catalog\n"
        "  AS $fn$ SELECT coalesce(current_setting('app.entity_scope', true), '') = '*'\n"
        "           OR e = ANY (string_to_array("
        "nullif(current_setting('app.entity_scope', true), ''), ',')::uuid[]) $fn$",
    ),
)

# DB-01: append-only guard; a change passes only for erev_owner with a data-fix ticket.
FORBID_MUTATION_BODY: Final = f"""
BEGIN
  IF current_user = '{OWNER_ROLE}'
     AND coalesce(current_setting('app.data_fix_ticket', true), '') <> '' THEN
    IF TG_LEVEL = 'STATEMENT' THEN
      RETURN NULL;
    ELSIF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION USING ERRCODE = 'P0001',
    MESSAGE = format('EREV-IMM-001: %s on %I.%I is not permitted; the table is append-only',
                     TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME);
END
"""

# DB-02: monotonic row version; identity and creation columns never change.
TOUCH_BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  frozen text;
BEGIN
  FOREACH frozen IN ARRAY ARRAY['id', 'tenant_id', 'created_at', 'created_by'] LOOP
    IF (old_row -> frozen) IS DISTINCT FROM (new_row -> frozen) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-ROW-001: column %I of %I.%I cannot change',
                         frozen, TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
  END LOOP;
  NEW.updated_at := now();
  NEW.row_version := OLD.row_version + 1;
  RETURN NEW;
END
"""

TRIGGER_FUNCTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("tg_forbid_mutation()", FORBID_MUTATION_BODY),
    ("tg_touch()", TOUCH_BODY),
)


def _trigger_function_sql(signature: str, body: str, *, replace: bool = False) -> str:
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    verb = "CREATE OR REPLACE FUNCTION" if replace else "CREATE FUNCTION"
    return (
        f"{verb} {SCHEMA}.{signature} RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER "
        f"SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def _function_grants(signature: str) -> list[str]:
    target = f"{SCHEMA}.{signature}"
    return [
        f"REVOKE ALL ON FUNCTION {target} FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {target} TO {APP_ROLE}",
    ]


def schema_foundation_statements() -> list[str]:
    statements = [
        f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC",
        f"GRANT USAGE ON SCHEMA {SCHEMA} TO {APP_ROLE}",
    ]
    for name, base, check in DOMAINS:
        statements.append(
            f"CREATE DOMAIN {qualified(name)} AS {base} CONSTRAINT ck_{name}__value CHECK ({check})"
        )
    for name in SEQUENCES:
        statements += [
            f"CREATE SEQUENCE {qualified(name)} AS bigint",
            f"REVOKE ALL ON SEQUENCE {qualified(name)} FROM PUBLIC",
            f"GRANT USAGE ON SEQUENCE {qualified(name)} TO {APP_ROLE}",
        ]
    for signature, definition in RLS_FUNCTIONS:
        statements.append(f"CREATE FUNCTION {SCHEMA}.{signature} {definition}")
        statements += _function_grants(_signature_types(signature))
    for signature, body in TRIGGER_FUNCTIONS:
        statements.append(_trigger_function_sql(signature, body))
        statements += _function_grants(signature)
    return statements


def _signature_types(signature: str) -> str:
    # "entity_in_scope(e uuid)" -> "entity_in_scope(uuid)" for GRANT and DROP statements.
    name, _, arguments = signature.partition("(")
    types = [argument.split()[-1] for argument in arguments.rstrip(")").split(",") if argument]
    return f"{name}({', '.join(types)})"


def create_schema_foundation() -> None:
    """Domains TY-01 to TY-10, sequences, §1.4 helpers, DB-01 and DB-02 functions and grants."""
    for statement in schema_foundation_statements():
        execute(statement)


def drop_schema_foundation() -> None:
    """Reverse ``create_schema_foundation`` (DG-MIG-04); env.py drops the empty schema."""
    for signature, _ in reversed(TRIGGER_FUNCTIONS):
        execute(f"DROP FUNCTION {SCHEMA}.{signature}")
    for signature, _ in reversed(RLS_FUNCTIONS):
        execute(f"DROP FUNCTION {SCHEMA}.{_signature_types(signature)}")
    for name in reversed(SEQUENCES):
        execute(f"DROP SEQUENCE {qualified(name)}")
    for name, _, _ in reversed(DOMAINS):
        execute(f"DROP DOMAIN {qualified(name)}")
    execute(f"REVOKE USAGE ON SCHEMA {SCHEMA} FROM {APP_ROLE}")


# --- enumerations (DG-MIG-06) ---------------------------------------------------------------


def create_enum(name: str, values: Sequence[str]) -> None:
    if not values:
        raise ValueError("an enum type needs at least one value")
    labels = ", ".join(enum_literal(value) for value in values)
    execute(f"CREATE TYPE {qualified(name)} AS ENUM ({labels})")


def drop_enum(name: str) -> None:
    """Drop an enum type in the downgrade of the revision that created it (DG-MIG-04)."""
    execute(f"DROP TYPE {qualified(name)}")


def add_enum_value(name: str, value: str, *, after: str | None = None) -> None:
    position = "" if after is None else f" AFTER {enum_literal(after)}"
    execute(f"ALTER TYPE {qualified(name)} ADD VALUE {enum_literal(value)}{position}")


@dataclass(frozen=True, slots=True)
class EnumColumn:
    """A column typed by an enum (or an array of it) that ``remove_enum_value`` converts."""

    table: str
    column: str
    is_array: bool = False
    default: str | None = None  # the column default as pg_get_expr prints it


@dataclass(frozen=True, slots=True)
class EnumDependent:
    """A check constraint or an index whose stored expression holds a constant of the enum (its
    catalogue row depends on the type): a status check, the predicate of a partial index.
    ``remove_enum_value`` drops it before the type is replaced and re-creates it afterwards from
    ``definition`` — ``pg_get_constraintdef`` or ``pg_get_indexdef`` as printed BEFORE the
    rename. Left in place, the expression keeps constants of the renamed type and ``ALTER COLUMN
    ... TYPE`` finds no operator between the two types."""

    table: str
    name: str
    definition: str
    is_index: bool = False


def remove_enum_value_sql(
    name: str,
    remaining: Sequence[str],
    columns: Sequence[EnumColumn],
    dependents: Sequence[EnumDependent] = (),
) -> list[str]:
    """Drop the dependents, rename the type, create it without the value, convert each column,
    drop the old type, re-create the dependents."""
    type_name = qualified(name)
    old_name = object_name(f"{name}__old")
    statements = [
        f"DROP INDEX {qualified(item.name)}"
        if item.is_index
        else f"ALTER TABLE {qualified(item.table)} DROP CONSTRAINT {object_name(item.name)}"
        for item in dependents
    ]
    statements += [
        f"ALTER TYPE {type_name} RENAME TO {old_name}",
        f"CREATE TYPE {type_name} AS ENUM ({', '.join(enum_literal(v) for v in remaining)})",
    ]
    for column in columns:
        table, col = qualified(column.table), table_name(column.column)
        target, via = (f"{type_name}[]", "text[]") if column.is_array else (type_name, "text")
        if column.default is not None:
            statements.append(f"ALTER TABLE {table} ALTER COLUMN {col} DROP DEFAULT")
        statements.append(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {target} USING {col}::{via}::{target}"
        )
        if column.default is not None:
            statements.append(
                f"ALTER TABLE {table} ALTER COLUMN {col} SET DEFAULT {column.default}"
            )
    statements.append(f"DROP TYPE {qualified(old_name)}")
    statements += [
        item.definition
        if item.is_index
        else f"ALTER TABLE {qualified(item.table)} ADD CONSTRAINT {object_name(item.name)} "
        f"{item.definition}"
        for item in dependents
    ]
    return statements


_ENUM_LABELS = sa.text(
    "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
    "JOIN pg_namespace n ON n.oid = t.typnamespace "
    "WHERE n.nspname = 'erev' AND t.typname = :name ORDER BY e.enumsortorder"
)
_ENUM_COLUMNS = sa.text(
    "SELECT c.relname, a.attname, a.atttypid = t.typarray, pg_get_expr(d.adbin, d.adrelid) "
    "FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
    "JOIN pg_attribute a ON a.atttypid IN (t.oid, t.typarray) AND NOT a.attisdropped "
    "JOIN pg_class c ON c.oid = a.attrelid AND c.relkind IN ('r', 'p') AND NOT c.relispartition "
    "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
    "WHERE n.nspname = 'erev' AND t.typname = :name ORDER BY c.relname, a.attnum"
)


# Check constraints and indexes of ``erev`` tables that depend on the type itself (or on its array
# type): their stored expression holds a constant of it. A constraint or index that only reads
# the column depends on the column, and ``ALTER COLUMN ... TYPE`` rebuilds it.
_ENUM_DEPENDENTS = sa.text(
    "SELECT DISTINCT c.relname, k.conname, pg_get_constraintdef(k.oid), false "
    "FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
    "JOIN pg_depend d ON d.refclassid = 'pg_type'::regclass AND d.refobjid IN (t.oid, t.typarray) "
    "AND d.classid = 'pg_constraint'::regclass "
    "JOIN pg_constraint k ON k.oid = d.objid AND k.contype = 'c' "
    "JOIN pg_class c ON c.oid = k.conrelid "
    "WHERE n.nspname = 'erev' AND t.typname = :name "
    "UNION "
    "SELECT DISTINCT c.relname, i.relname, pg_get_indexdef(i.oid), true "
    "FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
    "JOIN pg_depend d ON d.refclassid = 'pg_type'::regclass AND d.refobjid IN (t.oid, t.typarray) "
    "AND d.classid = 'pg_class'::regclass "
    "JOIN pg_class i ON i.oid = d.objid AND i.relkind IN ('i', 'I') "
    "JOIN pg_index x ON x.indexrelid = i.oid JOIN pg_class c ON c.oid = x.indrelid "
    "WHERE n.nspname = 'erev' AND t.typname = :name "
    "ORDER BY 1, 2"
)


def remove_enum_value(name: str, value: str) -> None:
    """Downgrade helper; fails when a stored row still uses ``value`` (DG-MIG-06). Check
    constraints and indexes that compare a column with a constant of the type are carried across
    the swap (``EnumDependent``; dev-guide rev 1.171)."""
    connection = _connection()
    labels = list(connection.execute(_ENUM_LABELS, {"name": object_name(name)}).scalars())
    if value not in labels:
        raise ValueError(f"enum {name} has no value {value!r}")
    columns = [
        EnumColumn(table=row[0], column=row[1], is_array=bool(row[2]), default=row[3])
        for row in connection.execute(_ENUM_COLUMNS, {"name": name})
    ]
    dependents = [
        EnumDependent(table=row[0], name=row[1], definition=row[2], is_index=bool(row[3]))
        for row in connection.execute(_ENUM_DEPENDENTS, {"name": object_name(name)})
    ]
    remaining = [v for v in labels if v != value]
    for statement in remove_enum_value_sql(name, remaining, columns, dependents):
        execute(statement)


# --- tables ---------------------------------------------------------------------------------


def _standard_columns(name: str, standard_sets: Sequence[StandardSet]) -> list[sa.Column[Any]]:
    now = sa.text("now()")
    columns: list[sa.Column[Any]] = []
    if "SC-C" in standard_sets:
        columns += [
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("created_by_kind", NamedType("erev.principal_kind"), nullable=False),
        ]
    if "SC-M" in standard_sets:
        columns += [
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by_kind", NamedType("erev.principal_kind"), nullable=False),
            sa.Column(
                "row_version",
                sa.Integer(),
                sa.CheckConstraint("row_version >= 1", name=f"ck_{name}__row_version"),
                nullable=False,
                server_default=sa.text("1"),
            ),
        ]
    if "SC-V" in standard_sets:
        columns += [
            sa.Column(
                "version_no",
                sa.Integer(),
                sa.CheckConstraint("version_no >= 1", name=f"ck_{name}__version_no"),
                nullable=False,
            ),
            sa.Column(
                "status",
                NamedType("erev.config_status"),
                nullable=False,
                server_default=sa.text("'DRAFT'"),
            ),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("content_sha256", NamedType("erev.sha256"), nullable=True),
            sa.Column("approval_request_id", sa.Uuid(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_by", sa.Uuid(), nullable=True),
            sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
        ]
    return columns


def _create_table_sql(
    name: str, columns: Sequence[sa.Column[Any]], constraints: Sequence[Any], **dialect: Any
) -> str:
    table = sa.Table(
        table_name(name), sa.MetaData(schema=SCHEMA), *columns, *constraints, **dialect
    )
    return str(CreateTable(table).compile(dialect=_DIALECT)).strip()


def _index_sql(
    table: str,
    specs: Sequence[tuple[str, Sequence[str], str | None]],
    *,
    unique: bool,
    tenant_leading: bool = True,
) -> list[str]:
    prefix = f"{'ux' if unique else 'ix'}_{table}__"
    statements: list[str] = []
    for index_name, columns, where in specs:
        if not index_name.startswith(prefix):
            raise ValueError(f"index {index_name!r} must start with {prefix!r} (NC-16)")
        if tenant_leading and tuple(columns[:1]) != ("tenant_id",):
            raise ValueError(f"index {index_name!r} must lead with tenant_id (NC-03, NC-07)")
        kind = "UNIQUE INDEX" if unique else "INDEX"
        predicate = "" if where is None else f" WHERE {where}"
        statements.append(
            f"CREATE {kind} {object_name(index_name)} ON {qualified(table)} "
            f"({_column_list(columns)}){predicate}"
        )
    return statements


def _foreign_key_sql(
    table: str, constraint: str, columns: Sequence[str], target: str, target_columns: Sequence[str]
) -> str:
    return (
        f"ALTER TABLE {qualified(table)} ADD CONSTRAINT {object_name(constraint)} "
        f"FOREIGN KEY ({_column_list(columns)}) REFERENCES {qualified(target)} "
        f"({_column_list(target_columns)}) ON DELETE RESTRICT ON UPDATE RESTRICT"
    )


def create_tenant_table(
    name: str,
    *columns: sa.Column[Any],
    standard_sets: Sequence[StandardSet] = (),
    primary_key: Sequence[str] | None = None,
    partition_by: Literal["period_end_date", "occurred_at"] | None = None,
    checks: Sequence[tuple[str, str]] = (),
    unique: Sequence[tuple[str, Sequence[str], str | None]] = (),
    indexes: Sequence[tuple[str, Sequence[str], str | None]] = (),
    include_id: bool = True,
    approval_request_fk: bool = True,
) -> None:
    """A tenant table: SC-T, own columns, then SC-C, SC-M and SC-V in that order (04 §1.3).

    ``include_id=False`` omits the ``id`` column for tables whose 04 specification lists its own
    key columns (``audit_chain_head``) or places ``id`` after the partition column
    (``audit_event``); such tables name ``primary_key`` explicitly. ``approval_request_fk=False``
    omits the SC-V foreign key to ``approval_request`` for tables created before it; the revision
    that creates ``approval_request`` adds the key (DG-MIG-03).
    """
    table_name(name)
    if not include_id and primary_key is None:
        raise ValueError("a tenant table without SC-T id names its primary key")
    identity = [sa.Column("id", sa.Uuid(), nullable=False)] if include_id else []
    all_columns = [
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        *identity,
        *columns,
        *_standard_columns(name, standard_sets),
    ]
    key = primary_key or (
        ["tenant_id", partition_by, "id"] if partition_by else ["tenant_id", "id"]
    )
    constraints: list[Any] = [sa.PrimaryKeyConstraint(*key), *_check_constraints(name, checks)]
    if "SC-V" in standard_sets:
        constraints.append(
            sa.CheckConstraint(
                "effective_to IS NULL OR effective_to > effective_from",
                name=f"ck_{name}__effective_range",
            )
        )
    dialect = {"postgresql_partition_by": f"RANGE ({partition_by})"} if partition_by else {}
    execute(_create_table_sql(name, all_columns, constraints, **dialect))
    execute(f"REVOKE ALL ON TABLE {qualified(name)} FROM PUBLIC")
    execute(_foreign_key_sql(name, f"fk_{name}__tenant", ["tenant_id"], "tenant", ["id"]))
    if "SC-V" in standard_sets:
        if approval_request_fk:
            execute(
                _foreign_key_sql(
                    name,
                    f"fk_{name}__approval_request",
                    ["tenant_id", "approval_request_id"],
                    "approval_request",
                    ["tenant_id", "id"],
                )
            )
        execute(
            _foreign_key_sql(
                name,
                f"fk_{name}__supersedes_version",
                ["tenant_id", "supersedes_version_id"],
                name,
                ["tenant_id", "id"],
            )
        )
    for statement in _index_sql(name, unique, unique=True) + _index_sql(
        name, indexes, unique=False
    ):
        execute(statement)


def _check_constraints(table: str, checks: Sequence[tuple[str, str]]) -> list[sa.CheckConstraint]:
    """Table-level CHECK constraints named ``ck_<table>__<rule>`` (NC-16)."""
    prefix = f"ck_{table}__"
    constraints: list[sa.CheckConstraint] = []
    for name, expression in checks:
        if not name.startswith(prefix):
            raise ValueError(f"check {name!r} must start with {prefix!r} (NC-16)")
        constraints.append(sa.CheckConstraint(expression, name=object_name(name)))
    return constraints


def create_global_table(
    name: str,
    *columns: sa.Column[Any],
    primary_key: Sequence[str],
    standard_sets: Sequence[StandardSet] = (),
    checks: Sequence[tuple[str, str]] = (),
    unique: Sequence[tuple[str, Sequence[str], str | None]] = (),
    indexes: Sequence[tuple[str, Sequence[str], str | None]] = (),
) -> None:
    """A global table without tenant_id (RLS-NONE-G or RLS-NONE-U; 04 §1.4).

    Own columns come first, then SC-C and SC-M (04 §1.3). SC-V is not offered, because its
    foreign keys reference tenant rows.
    """
    if "SC-V" in standard_sets:
        raise ValueError("SC-V columns belong to tenant tables only (04 §1.3)")
    all_columns = [*columns, *_standard_columns(table_name(name), standard_sets)]
    constraints: list[Any] = [sa.PrimaryKeyConstraint(*primary_key)]
    constraints += _check_constraints(name, checks)
    execute(_create_table_sql(name, all_columns, constraints))
    execute(f"REVOKE ALL ON TABLE {qualified(name)} FROM PUBLIC")
    for statement in _index_sql(name, unique, unique=True, tenant_leading=False) + _index_sql(
        name, indexes, unique=False, tenant_leading=False
    ):
        execute(statement)


def create_indexes(
    table: str,
    specs: Sequence[tuple[str, Sequence[str], str | None]],
    *,
    unique: bool,
    tenant_leading: bool = True,
) -> None:
    """Indexes named per NC-16; ``tenant_leading=False`` admits the cross-tenant lookups that 04
    specifies on tenant tables (for example ``ix_tenant_membership__user_id``)."""
    for statement in _index_sql(table, specs, unique=unique, tenant_leading=tenant_leading):
        execute(statement)


def add_global_fk(table: str, column: str, target: str, *, target_column: str = "id") -> None:
    """Single-column foreign key to a global table, named ``fk_<table>__<column stem>``.

    NC-06 composite keys apply to tenant-owned targets; global targets (``app_user``, ``tenant``,
    ``currency``) take one column (04 T-PLT-07 ``user_id``).
    """
    stem = column.removesuffix("_id")
    execute(_foreign_key_sql(table, f"fk_{table}__{stem}", [column], target, [target_column]))


def add_tenant_fk(
    table: str, column: str, target: str, *, target_partition_column: str | None = None
) -> None:
    """Composite foreign key ``(tenant_id, <column>)`` to ``target (tenant_id, id)`` (NC-06)."""
    stem = column.removesuffix("_id")
    suffix = target if stem == target else stem
    local = ["tenant_id", column]
    remote = ["tenant_id", "id"]
    if target_partition_column is not None:
        prefix = f"{target}_"
        if not target_partition_column.startswith(prefix):
            raise ValueError(f"partition column must be named {prefix}<column> (NC-06)")
        local.insert(1, target_partition_column)
        remote.insert(1, target_partition_column.removeprefix(prefix))
    execute(_foreign_key_sql(table, f"fk_{table}__{suffix}", local, target, remote))


def drop_tenant_table(name: str) -> None:
    """Drop a table (with its partitions) and the ``tg_<table>__*`` functions its revision made."""
    execute(f"DROP TABLE {qualified(name)}")
    functions = _connection().execute(
        sa.text(
            "SELECT format('%I.%I(%s)', n.nspname, p.proname, "
            "pg_get_function_identity_arguments(p.oid)) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'erev' AND starts_with(p.proname, :prefix) ORDER BY 1"
        ),
        {"prefix": f"tg_{table_name(name)}__"},
    )
    for (signature,) in functions:
        execute(f"DROP FUNCTION {signature}")


def drop_global_table(name: str) -> None:
    execute(f"DROP TABLE {qualified(name)}")


# --- row-level security (04 §1.4) -----------------------------------------------------------


def _tenant_policy(table: str) -> str:
    return (
        f"CREATE POLICY pl_{table}__tenant ON {qualified(table)} FOR ALL TO {APP_ROLE} "
        "USING (tenant_id = (SELECT erev.current_tenant_id())) "
        "WITH CHECK (tenant_id = (SELECT erev.current_tenant_id()))"
    )


def rls_statements(
    table: str,
    template: RlsTemplate,
    *,
    entity_column: str | None = None,
    entity_nullable: bool = False,
) -> list[str]:
    """``entity_nullable`` lets a NULL entity column pass the RLS-TE policy: a tenant-wide row
    visible to every scope (04 T-PLT-17)."""
    target = qualified(table)
    if (template == "RLS-TE") != (entity_column is not None):
        raise ValueError("entity_column is required for RLS-TE and only for RLS-TE")
    if entity_nullable and entity_column is None:
        raise ValueError("entity_nullable applies to RLS-TE only")
    statements = [
        f"ALTER TABLE {target} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {target} FORCE ROW LEVEL SECURITY",
    ]
    if template in ("RLS-T", "RLS-TE", "RLS-TM"):
        statements.append(_tenant_policy(table))
    if template == "RLS-TE" and entity_column is not None:
        scope = f"(SELECT erev.entity_in_scope({table_name(entity_column)}))"
        if entity_nullable:
            scope = f"({entity_column} IS NULL OR {scope})"
        statements.append(
            f"CREATE POLICY pl_{table}__entity ON {target} AS RESTRICTIVE FOR ALL TO {APP_ROLE} "
            f"USING ({scope}) WITH CHECK ({scope})"
        )
    if template == "RLS-TM":
        statements.append(
            f"CREATE POLICY pl_{table}__self ON {target} FOR SELECT TO {APP_ROLE} "
            "USING (user_id = (SELECT erev.current_user_id()))"
        )
    if template == "RLS-TN":
        statements += [
            f"CREATE POLICY pl_{table}__select ON {target} FOR SELECT TO {APP_ROLE} "
            "USING (id = (SELECT erev.current_tenant_id()) "
            "OR id IN (SELECT m.tenant_id FROM erev.tenant_membership m "
            "WHERE m.user_id = (SELECT erev.current_user_id()) AND m.status = 'ACTIVE') "
            "OR current_setting('app.platform_scope', true) = 'tenant_directory')",
            f"CREATE POLICY pl_{table}__update ON {target} FOR UPDATE TO {APP_ROLE} "
            "USING (id = (SELECT erev.current_tenant_id())) "
            "WITH CHECK (id = (SELECT erev.current_tenant_id()))",
            f"CREATE POLICY pl_{table}__provisioning ON {target} FOR INSERT TO {APP_ROLE} "
            "WITH CHECK (current_setting('app.platform_scope', true) = 'provisioning')",
        ]
    return statements


def enable_rls(
    table: str,
    template: RlsTemplate,
    *,
    entity_column: str | None = None,
    entity_nullable: bool = False,
) -> None:
    for statement in rls_statements(
        table, template, entity_column=entity_column, entity_nullable=entity_nullable
    ):
        execute(statement)


# --- global catalogue seeds (DG-MIG-07) -----------------------------------------------------

SeedValue = str | int | bool | None


def _seed_literal(value: SeedValue) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("a seed string must not contain NUL")
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(f"unsupported seed value type {type(value).__name__}")


def insert_rows_sql(table: str, columns: Sequence[str], rows: Sequence[Sequence[SeedValue]]) -> str:
    """One multi-row INSERT with SQL literals, so seeds run through driver-level execution."""
    if not rows:
        raise ValueError("a seed needs at least one row")
    values: list[str] = []
    for row in rows:
        if len(row) != len(columns):
            raise ValueError("every seed row has one value per column")
        values.append("(" + ", ".join(_seed_literal(value) for value in row) + ")")
    return f"INSERT INTO {qualified(table)} ({_column_list(columns)}) VALUES\n  " + ",\n  ".join(
        values
    )


def insert_rows(table: str, columns: Sequence[str], rows: Sequence[Sequence[SeedValue]]) -> None:
    """Seed a global catalogue (DG-MIG-07); tenant data is never seeded by migrations."""
    execute(insert_rows_sql(table, columns, rows))


# --- immutability classes and triggers (04 §1.5, §14.1, §14.2) ------------------------------


def class_statements(
    table: str,
    klass: ImClass,
    *,
    update_columns: Sequence[str] = (),
    delete_allowed: bool = False,
    global_reference: bool = False,
    select_only: bool = False,
    update_forbidden: bool = False,
    without_sc_m: bool = False,
) -> list[str]:
    """Grants to erev_app, the class triggers and the class marker comment read by DB-14 (g).

    ``global_reference`` marks an IM-A global reference table (RLS-NONE-G), on which erev_app holds
    SELECT only (04 §1.4, §14.2). ``select_only`` marks an IM-M identity table that erev_app only
    reads (``identity_provider``, 04 §14.2). ``update_forbidden`` marks an IM-M table on which DB-01
    blocks UPDATE, so it carries the DB-01 row trigger instead of the touch trigger
    (``role_permission``, 04 T-PLT-12). IM-P tables carry SC-M and therefore the touch trigger,
    except an IM-P child without SC-M (``without_sc_m``; ``rule``, 04 T-REF-26).
    The DB-03 transition trigger of IM-S tables is added with ``create_trigger``, and the DB-04
    triggers of IM-P tables with ``add_config_version_trigger`` and ``add_config_child_trigger``.
    An IM-A table with ``update_columns`` (``file_object``, 04 T-PLT-29) guards only DELETE and
    TRUNCATE with DB-01; its revision adds the DB-03 transition trigger that allow-lists the
    updatable columns.
    """
    target = qualified(table)
    if klass not in CLASS_PRIVILEGES:
        raise ValueError(f"unknown immutability class {klass!r}")
    if delete_allowed and klass != "IM-M":
        raise ValueError("delete_allowed applies to IM-M tables only (04 §14.2)")
    if global_reference and klass != "IM-A":
        raise ValueError("global_reference applies to IM-A global reference tables only (04 §14.2)")
    if select_only and (klass != "IM-M" or update_columns or delete_allowed):
        raise ValueError("select_only applies to IM-M tables without other grants (04 §14.2)")
    if update_forbidden and (klass != "IM-M" or select_only):
        raise ValueError("update_forbidden applies to IM-M tables only (04 T-PLT-12)")
    if klass == "IM-S" and not update_columns:
        raise ValueError("IM-S tables grant UPDATE on listed columns only (04 §1.5)")
    if without_sc_m and klass != "IM-P":
        raise ValueError("without_sc_m applies to IM-P child tables only (04 T-REF-26)")
    privileges = [p for p in CLASS_PRIVILEGES[klass] if p != "UPDATE" or not update_columns]
    if global_reference or select_only:
        privileges = ["SELECT"]
    if delete_allowed:
        privileges.append("DELETE")
    statements = [f"GRANT {', '.join(privileges)} ON TABLE {target} TO {APP_ROLE}"]
    if update_columns:
        statements.append(
            f"GRANT UPDATE ({_column_list(update_columns)}) ON TABLE {target} TO {APP_ROLE}"
        )
    if klass in ("IM-A", "IM-S"):
        events = "UPDATE OR DELETE" if klass == "IM-A" and not update_columns else "DELETE"
        statements += [
            f"CREATE TRIGGER tg_{table}__immutable BEFORE {events} ON {target} "
            "FOR EACH ROW EXECUTE FUNCTION erev.tg_forbid_mutation()",
            f"CREATE TRIGGER tg_{table}__truncate BEFORE TRUNCATE ON {target} "
            "FOR EACH STATEMENT EXECUTE FUNCTION erev.tg_forbid_mutation()",
        ]
    if klass == "IM-M" and update_forbidden:
        statements.append(
            f"CREATE TRIGGER tg_{table}__immutable BEFORE UPDATE ON {target} "
            "FOR EACH ROW EXECUTE FUNCTION erev.tg_forbid_mutation()"
        )
    elif klass in ("IM-M", "IM-P") and not without_sc_m:
        statements.append(
            f"CREATE TRIGGER tg_{table}__touch BEFORE UPDATE ON {target} "
            "FOR EACH ROW EXECUTE FUNCTION erev.tg_touch()"
        )
    statements.append(f"COMMENT ON TABLE {target} IS '{klass}'")
    return statements


def partition_truncate_trigger_sql(partition: str) -> str:
    """DB-01 TRUNCATE trigger of one child partition; TRUNCATE of a partition skips the parent's."""
    name = object_name(f"tg_{object_name(partition)}__truncate")
    return (
        f"CREATE TRIGGER {name} BEFORE TRUNCATE ON {qualified(partition)} "
        "FOR EACH STATEMENT EXECUTE FUNCTION erev.tg_forbid_mutation()"
    )


_CHILD_PARTITIONS = sa.text(
    "SELECT c.relname FROM pg_partition_tree(CAST(:parent AS regclass)) t "
    "JOIN pg_class c ON c.oid = t.relid "
    "WHERE t.relid <> CAST(:parent AS regclass) ORDER BY c.relname"
)
_TABLE_CLASS = sa.text("SELECT obj_description(to_regclass(:table), 'pg_class')")


def _child_partitions(table: str) -> list[str]:
    # Under ``recording`` there is no catalogue to read, so no partition statements are recorded.
    if _sink.get() is not None:
        return []
    rows = _connection().execute(_CHILD_PARTITIONS, {"parent": qualified(table)})
    return [str(name) for (name,) in rows]


def _table_class(table: str) -> str | None:
    if _sink.get() is not None:
        return None
    value = _connection().execute(_TABLE_CLASS, {"table": qualified(table)}).scalar()
    return None if value is None else str(value)


def apply_class(
    table: str,
    klass: ImClass,
    *,
    update_columns: Sequence[str] = (),
    delete_allowed: bool = False,
    global_reference: bool = False,
    select_only: bool = False,
    update_forbidden: bool = False,
    without_sc_m: bool = False,
) -> None:
    """Run ``class_statements``; IM-A and IM-S tables also guard their existing child partitions.

    ``create_monthly_partitions`` guards partitions created after the class, so the triggers exist
    whichever of the two helpers runs first (DB-01; D-78).
    """
    for statement in class_statements(
        table,
        klass,
        update_columns=update_columns,
        delete_allowed=delete_allowed,
        global_reference=global_reference,
        select_only=select_only,
        update_forbidden=update_forbidden,
        without_sc_m=without_sc_m,
    ):
        execute(statement)
    if klass in TRUNCATE_GUARDED_CLASSES:
        for partition in _child_partitions(table):
            execute(partition_truncate_trigger_sql(partition))


def create_trigger(
    table: str,
    purpose: str,
    function_sql: str,
    *,
    timing: Literal["BEFORE", "AFTER"],
    events: str,
    for_each: Literal["ROW", "STATEMENT"] = "ROW",
    deferrable: bool = False,
) -> None:
    """Function ``erev.tg_<table>__<purpose>()`` from a plpgsql body, and its trigger (NC-16)."""
    name = object_name(f"tg_{table_name(table)}__{purpose}")
    for event in events.split(" OR "):
        if not _EVENT.fullmatch(event):
            raise ValueError(f"invalid trigger event {event!r}")
    if deferrable and (timing != "AFTER" or for_each != "ROW"):
        raise ValueError("a deferrable constraint trigger is AFTER … FOR EACH ROW")
    execute(_trigger_function_sql(f"{name}()", function_sql))
    for statement in _function_grants(f"{name}()"):
        execute(statement)
    target = qualified(table)
    if deferrable:
        execute(
            f"CREATE CONSTRAINT TRIGGER {name} AFTER {events} ON {target} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.{name}()"
        )
    else:
        execute(
            f"CREATE TRIGGER {name} {timing} {events} ON {target} "
            f"FOR EACH {for_each} EXECUTE FUNCTION {SCHEMA}.{name}()"
        )


# --- configuration versions DB-04 (04 §1.3 SC-V, §1.5 IM-P, §14.1) --------------------------

# 04 §1.5 IM-P: the columns that may change once a version has left DRAFT and TESTED, plus the SC-M
# columns the DB-02 touch trigger maintains (it fires after tg_<table>__config_version).
CONFIG_MUTABLE_COLUMNS: Final = (
    "approval_request_id",
    "effective_to",
    "published_at",
    "published_by",
    "row_version",
    "status",
    "updated_at",
    "updated_by",
    "updated_by_kind",
)
# 04 E-12 configuration lifecycle: DRAFT→TESTED→SUBMITTED→APPROVED→PUBLISHED→SUPERSEDED, and
# SUBMITTED→REJECTED→DRAFT or SUBMITTED→WITHDRAWN→DRAFT.
CONFIG_STATUS_PAIRS: Final = (
    "APPROVED>PUBLISHED",
    "DRAFT>TESTED",
    "PUBLISHED>SUPERSEDED",
    "REJECTED>DRAFT",
    "SUBMITTED>APPROVED",
    "SUBMITTED>REJECTED",
    "SUBMITTED>WITHDRAWN",
    "TESTED>SUBMITTED",
    "WITHDRAWN>DRAFT",
)


def _text_array(values: Sequence[str]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::text[]"


# D-80 (WEB-3d; SPEC-Q-151 overruled): outside the provisioning platform scope a version is inserted
# as DRAFT, so a version leaves DRAFT only along E-12.
CONFIG_INSERT_GUARD: Final = """
  IF TG_OP = 'INSERT' AND NEW.status <> 'DRAFT'
     AND current_setting('app.platform_scope', true) IS DISTINCT FROM 'provisioning' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-CFG-002: a version of %I.%I is inserted as DRAFT, not %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.status);
  END IF;"""


def _config_version_body(insert_guard: str) -> str:
    """DB-04: frozen after DRAFT and TESTED; E-12 pairs; APPROVED only with an APPROVED approval
    request (fail closed while approval_request does not exist, XR-12); content_sha256 outside
    DRAFT; DELETE of DRAFT rows only; no overlapping effective ranges among PUBLISHED rows of one
    scope key, whose columns are the trigger arguments; then ``insert_guard`` on INSERT."""
    return f"""
DECLARE
  old_row jsonb;
  new_row jsonb;
  changed text;
  approved boolean := false;
  overlapping boolean;
  scope_predicate text := '';
  i integer;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'DRAFT' THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-002: a %s version of %I.%I cannot be deleted',
                         OLD.status, TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
    RETURN OLD;
  END IF;{insert_guard}
  IF NEW.status <> 'DRAFT' AND NEW.content_sha256 IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-CFG-002: content_sha256 of %I.%I is required outside DRAFT',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.status::text <> ALL ({_text_array(("DRAFT", "TESTED"))}) THEN
      old_row := to_jsonb(OLD);
      new_row := to_jsonb(NEW);
      SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
        FROM jsonb_each(new_row) n
       WHERE n.key <> ALL ({_text_array(CONFIG_MUTABLE_COLUMNS)})
         AND n.value IS DISTINCT FROM old_row -> n.key;
      IF changed IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
          MESSAGE = format('EREV-CFG-002: columns %s of %I.%I cannot change in status %s',
                           changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
      END IF;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status
       AND (OLD.status::text || '>' || NEW.status::text)
           <> ALL ({_text_array(CONFIG_STATUS_PAIRS)}) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-002: status of %I.%I cannot change from %s to %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
    END IF;
    IF NEW.status = 'APPROVED' AND OLD.status <> 'APPROVED' THEN
      IF NEW.approval_request_id IS NOT NULL
         AND to_regclass('erev.approval_request') IS NOT NULL THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM erev.approval_request r '
                'WHERE r.tenant_id = $1 AND r.id = $2 AND r.status = ''APPROVED'')'
          INTO approved USING NEW.tenant_id, NEW.approval_request_id;
      END IF;
      IF NOT approved THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
          MESSAGE = format('EREV-CFG-002: a version of %I.%I needs an APPROVED approval request',
                           TG_TABLE_SCHEMA, TG_TABLE_NAME);
      END IF;
    END IF;
  END IF;
  IF NEW.status = 'PUBLISHED' THEN
    FOR i IN 0 .. TG_NARGS - 1 LOOP
      scope_predicate := scope_predicate
        || format(' AND (to_jsonb(r) -> %L) IS NOT DISTINCT FROM ($4 -> %L)',
                  TG_ARGV[i], TG_ARGV[i]);
    END LOOP;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I r WHERE r.tenant_id = $1 AND r.id <> $2 '
                   'AND r.status = ''PUBLISHED'' '
                   'AND tstzrange(r.effective_from, r.effective_to) && $3%s)',
                   TG_TABLE_SCHEMA, TG_TABLE_NAME, scope_predicate)
      INTO overlapping
      USING NEW.tenant_id, NEW.id, tstzrange(NEW.effective_from, NEW.effective_to), to_jsonb(NEW);
    IF overlapping THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-001: the effective range of %I.%I overlaps a PUBLISHED version',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
  END IF;
  RETURN NEW;
END
"""


# The body revision 0009 created, and the body revision 0026 installs (D-80 configuration inserts).
CONFIG_VERSION_BODY_0009: Final = _config_version_body("")
CONFIG_VERSION_BODY: Final = _config_version_body(CONFIG_INSERT_GUARD)
CONFIG_VERSION_FUNCTION: Final = "tg_config_version()"


def create_config_version_function() -> None:
    """``erev.tg_config_version()`` (DB-04) as the revision of the first IM-P table created it."""
    execute(_trigger_function_sql(CONFIG_VERSION_FUNCTION, CONFIG_VERSION_BODY_0009))
    for statement in _function_grants(CONFIG_VERSION_FUNCTION):
        execute(statement)


def replace_config_version_function(body: str) -> None:
    """Replace the body of ``erev.tg_config_version()``; its triggers and grants stay."""
    execute(_trigger_function_sql(CONFIG_VERSION_FUNCTION, body, replace=True))


def drop_config_version_function() -> None:
    execute(f"DROP FUNCTION {SCHEMA}.{CONFIG_VERSION_FUNCTION}")


def add_config_version_trigger(table: str, *, scope_columns: Sequence[str] = ()) -> None:
    """Trigger ``tg_<table>__config_version`` over DB-04, with the overlap scope key columns."""
    arguments = ", ".join(f"'{table_name(column)}'" for column in scope_columns)
    name = object_name(f"tg_{table_name(table)}__config_version")
    execute(
        f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OR DELETE ON {qualified(table)} "
        f"FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.tg_config_version({arguments})"
    )


# The polymorphic parent argument: the row's ``subject_type`` names the parent table (T-REF-27).
CONFIG_CHILD_SUBJECT: Final = "*"
# DB-04: a child row is written only while its parent version is DRAFT or TESTED. The trigger
# arguments are the parent table (or ``*``, the row's subject_type) and the parent id column. For
# UPDATE both the old and the new parent must be editable. A missing parent table or an invisible
# parent row fails closed; a row outside the tenant context is left to row-level security, which
# checks after BEFORE triggers. The one exception: provisioning inserts the children of the system
# versions it seeds as PUBLISHED in the same transaction (04 §14.3 item 2, AUTO-BOOTSTRAP).
CONFIG_CHILD_BODY: Final = f"""
DECLARE
  targets jsonb[];
  target jsonb;
  parent_table text;
  parent_status text;
BEGIN
  IF TG_OP = 'INSERT' AND current_setting('app.platform_scope', true) = 'provisioning' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' THEN
    targets := ARRAY[to_jsonb(NEW)];
  ELSIF TG_OP = 'UPDATE' THEN
    targets := ARRAY[to_jsonb(OLD), to_jsonb(NEW)];
  ELSE
    targets := ARRAY[to_jsonb(OLD)];
  END IF;
  FOREACH target IN ARRAY targets LOOP
    IF (target ->> 'tenant_id')::uuid IS DISTINCT FROM erev.current_tenant_id() THEN
      CONTINUE;
    END IF;
    parent_table := TG_ARGV[0];
    IF parent_table = '{CONFIG_CHILD_SUBJECT}' THEN
      parent_table := target ->> 'subject_type';
    END IF;
    parent_status := NULL;
    IF to_regclass(format('%I.%I', TG_TABLE_SCHEMA, parent_table)) IS NOT NULL THEN
      EXECUTE format('SELECT p.status::text FROM %I.%I p WHERE p.tenant_id = $1 AND p.id = $2',
                     TG_TABLE_SCHEMA, parent_table)
        INTO parent_status
        USING (target ->> 'tenant_id')::uuid, (target ->> TG_ARGV[1])::uuid;
    END IF;
    IF parent_status IS NULL OR parent_status <> ALL ({_text_array(("DRAFT", "TESTED"))}) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-002: rows of %I.%I cannot change while %s %s is %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME, parent_table, target ->> TG_ARGV[1],
                         coalesce(parent_status, 'not visible'));
    END IF;
  END LOOP;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
"""
CONFIG_CHILD_FUNCTION: Final = "tg_config_child()"


def create_config_child_function() -> None:
    """``erev.tg_config_child()`` (DB-04), created by the revision of the first IM-P child table."""
    execute(_trigger_function_sql(CONFIG_CHILD_FUNCTION, CONFIG_CHILD_BODY))
    for statement in _function_grants(CONFIG_CHILD_FUNCTION):
        execute(statement)


def drop_config_child_function() -> None:
    execute(f"DROP FUNCTION {SCHEMA}.{CONFIG_CHILD_FUNCTION}")


def add_config_child_trigger(table: str, *, parent_table: str | None, parent_column: str) -> None:
    """Trigger ``tg_<table>__config_child`` over DB-04; ``parent_table=None`` reads the parent
    table from the row's ``subject_type`` (04 T-REF-27)."""
    parent = CONFIG_CHILD_SUBJECT if parent_table is None else table_name(parent_table)
    name = object_name(f"tg_{table_name(table)}__config_child")
    execute(
        f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OR DELETE ON {qualified(table)} "
        f"FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.tg_config_child("
        f"'{parent}', '{table_name(parent_column)}')"
    )


# --- partitions (04 §1.6) -------------------------------------------------------------------


def _months(first: str, last: str) -> list[tuple[int, int]]:
    start, end = _MONTH.fullmatch(first), _MONTH.fullmatch(last)
    if start is None or end is None:
        raise ValueError("partition window bounds are YYYY-MM")
    year, month = int(start.group(1)), int(start.group(2))
    stop = (int(end.group(1)), int(end.group(2)))
    if (year, month) > stop:
        raise ValueError("first partition month is after the last")
    months: list[tuple[int, int]] = []
    while (year, month) <= stop:
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _partition_column(table: str, partition_column: PartitionColumn | None) -> PartitionColumn:
    known = PARTITION_COLUMNS.get(table)
    if partition_column is None:
        if known is None:
            raise ValueError(f"{table!r} is not a partitioned table of 04 §1.6")
        return "occurred_at" if known == "occurred_at" else "period_end_date"
    if known is not None and known != partition_column:
        raise ValueError(f"{table!r} is partitioned by {known} (04 §1.6)")
    if partition_column not in ("period_end_date", "occurred_at"):
        raise ValueError(f"invalid partition column {partition_column!r}")
    return partition_column


def monthly_partition_statements(
    table: str,
    *,
    first: str = "2018-01",
    last: str = "2032-12",
    partition_column: PartitionColumn | None = None,
) -> list[str]:
    """``CREATE TABLE … PARTITION OF`` per month plus the default partition.

    ``partition_column`` admits a probe table outside 04 §1.6; 04 tables use their own column.
    """
    column = _partition_column(table_name(table), partition_column)
    suffix = " 00:00:00+00" if column == "occurred_at" else ""
    statements: list[str] = []
    for year, month in _months(first, last):
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        statements.append(
            f"CREATE TABLE {qualified(f'{table}_p{year:04d}{month:02d}')} "
            f"PARTITION OF {qualified(table)} FOR VALUES "
            f"FROM ('{year:04d}-{month:02d}-01{suffix}') "
            f"TO ('{next_year:04d}-{next_month:02d}-01{suffix}')"
        )
    statements.append(
        f"CREATE TABLE {qualified(f'{table}_pdefault')} PARTITION OF {qualified(table)} DEFAULT"
    )
    return statements


def create_monthly_partitions(
    table: str,
    *,
    first: str = "2018-01",
    last: str = "2032-12",
    partition_column: PartitionColumn | None = None,
) -> None:
    """Monthly partitions ``<table>_pYYYYMM`` plus ``<table>_pdefault`` (DG-MIG-10).

    Child partitions receive no grants; access goes through the parent (04 §1.6 rule 3). When the
    parent already has class IM-A or IM-S, each new partition gets its DB-01 TRUNCATE trigger.
    """
    statements = monthly_partition_statements(
        table, first=first, last=last, partition_column=partition_column
    )
    for statement in statements:
        execute(statement)
    if _table_class(table) in TRUNCATE_GUARDED_CLASSES:
        for statement in statements:
            # "CREATE TABLE erev.<partition> PARTITION OF …"
            execute(partition_truncate_trigger_sql(statement.split()[2].removeprefix(f"{SCHEMA}.")))


_PARTITIONED_PARENTS: Final = sa.text(
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'erev' AND c.relkind = 'p' ORDER BY c.relname"
)


def drop_partitioned_tables(engine: sa.Engine) -> list[str]:
    """Drop each partitioned table of schema erev and return their names: every partition in its
    own transaction, then the parent, so that no transaction locks more objects than the shared
    lock table holds (``max_locks_per_transaction``; BUILD_SPEC CTR-2, L3-1-Q-24). Dropping a
    partition also locks its constraints, triggers and row types, which for ``subledger_line``
    exceeds the table when the parent is dropped with its partitions at once (CTR-3, L3-1-Q-33)."""
    with engine.connect() as connection:
        parents = [str(name) for (name,) in connection.execute(_PARTITIONED_PARENTS)]
    for parent in parents:
        with engine.connect() as connection:
            children = [
                str(name)
                for (name,) in connection.execute(_CHILD_PARTITIONS, {"parent": qualified(parent)})
            ]
        for child in children:
            with engine.begin() as connection:
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {qualified(child)}")
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {qualified(parent)} CASCADE")
    return parents


# --- revision files (DG-MIG-02; DG-MK-revision) ---------------------------------------------

_REVISION_FILE: Final = re.compile(r"^(\d{4})_[a-z0-9_]+\.py$")


# --- Procrastinate schema DG-MIG-09 (04 NC-01, §14.2) ---------------------------------------

PROCRASTINATE_SCHEMA: Final = "public"
# The library's schema opens with a DO block that creates plpgsql, which PostgreSQL 17 always
# provides; DG-ENV-14 forbids extension administration, so execution starts at the enums.
_PROCRASTINATE_BODY_START: Final = "-- Enums"
# No '%' in this SQL: without bind parameters psycopg would receive SQLAlchemy's '%%' escapes.
_PROCRASTINATE_CATALOGUE = sa.text(
    "SELECT o.kind, o.name FROM ("
    "SELECT 'function' AS kind, 'public.' || quote_ident(p.proname) || '(' || "
    "pg_get_function_identity_arguments(p.oid) || ')' AS name FROM pg_proc p "
    "JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'public' AND starts_with(p.proname, 'procrastinate_') "
    "UNION ALL SELECT CASE c.relkind WHEN 'r' THEN 'table' ELSE 'sequence' END, "
    "'public.' || quote_ident(c.relname) FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'S') "
    "AND starts_with(c.relname, 'procrastinate_') "
    "UNION ALL SELECT 'trigger', quote_ident(g.tgname) || ' ON public.' || quote_ident(c.relname) "
    "FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND starts_with(c.relname, 'procrastinate_') "
    "AND NOT g.tgisinternal "
    "UNION ALL SELECT 'type', 'public.' || quote_ident(t.typname) FROM pg_type t "
    "JOIN pg_namespace n ON n.oid = t.typnamespace LEFT JOIN pg_class c ON c.oid = t.typrelid "
    "WHERE n.nspname = 'public' AND starts_with(t.typname, 'procrastinate_') "
    "AND t.typtype IN ('e', 'c') AND (c.oid IS NULL OR c.relkind = 'c')"
    ") o ORDER BY o.kind, o.name"
)


def procrastinate_schema_sql() -> str:
    """The pinned library's ``schema.sql`` from its enums onwards (DG-MIG-09)."""
    from procrastinate.schema import SchemaManager

    source = SchemaManager.get_schema()
    preamble, start, body = source.partition(_PROCRASTINATE_BODY_START)
    if not start or "plpgsql" not in preamble or "CREATE TABLE" in preamble:
        raise RuntimeError("unexpected Procrastinate schema layout; review DG-MIG-09 first")
    return start + body


def _procrastinate_objects() -> list[tuple[str, str]]:
    """``(kind, qualified name)`` of every ``procrastinate_`` table, sequence, function and type."""
    if _sink.get() is not None:
        return []
    rows = _connection().execute(_PROCRASTINATE_CATALOGUE)
    return [(str(kind), str(name)) for kind, name in rows]


def procrastinate_grant_statements(objects: Sequence[tuple[str, str]]) -> list[str]:
    """04 §14.2: SELECT, INSERT, UPDATE, DELETE on the library tables, sequence use for their
    keys, and EXECUTE on its functions, for erev_app only."""
    statements: list[str] = []
    for kind, name in objects:
        if kind == "table":
            statements += [
                f"REVOKE ALL ON TABLE {name} FROM PUBLIC",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {name} TO {APP_ROLE}",
            ]
        elif kind == "sequence":
            statements.append(f"GRANT USAGE, SELECT ON SEQUENCE {name} TO {APP_ROLE}")
        elif kind == "function":
            statements += [
                f"REVOKE ALL ON FUNCTION {name} FROM PUBLIC",
                f"GRANT EXECUTE ON FUNCTION {name} TO {APP_ROLE}",
            ]
    return statements


def install_procrastinate_schema() -> None:
    """Create the library objects in ``public`` as erev_owner, then grant erev_app (DG-MIG-09).

    The schema names its objects without a schema, so the transaction's search path is ``public``
    while it runs; the NC-01 path ``erev, public`` is restored afterwards.
    """
    execute(f"SELECT set_config('search_path', '{PROCRASTINATE_SCHEMA}', true)")
    execute(procrastinate_schema_sql())
    execute("SELECT set_config('search_path', 'erev, public', true)")
    for statement in procrastinate_grant_statements(_procrastinate_objects()):
        execute(statement)


def drop_procrastinate_schema() -> None:
    """Drop every ``procrastinate_`` trigger, function, table and type of ``public`` (DG-MIG-04,
    DG-MIG-09; DG-MK-db-reset), in that order: triggers use functions, functions use table row
    types, and tables and functions use the types. Sequences go with their tables."""
    objects = _procrastinate_objects()
    for kind, name in objects:
        if kind == "trigger":
            execute(f"DROP TRIGGER {name}")
    for kind, name in objects:
        if kind == "function":
            execute(f"DROP FUNCTION {name}")
    tables = [name for kind, name in objects if kind == "table"]
    if tables:
        execute("DROP TABLE " + ", ".join(tables))
    types = [name for kind, name in objects if kind == "type"]
    if types:
        execute("DROP TYPE " + ", ".join(types))


def slugify(message: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", message.lower()).strip("_")[:40].rstrip("_")
    if not slug:
        raise ValueError("MSG must contain letters or digits")
    return slug


def render_revision(*, number: str, slug: str, item: str, down_revision: str | None) -> str:
    """Render ``script.py.mako`` for revision ``number`` with the item named in its docstring."""
    if not re.fullmatch(r"\d{4}", number):
        raise ValueError("revision numbers have four digits")
    if not re.fullmatch(r"[A-Z]{2,5}-\d+[a-z]?|GATE-[A-Z]{2,5}|REL-\d+", item):
        raise ValueError(f"invalid BUILD_SPEC item id {item!r}")
    template = Template(filename=str(MIGRATIONS_DIR / "script.py.mako"))
    rendered = template.render(
        number=number, down_revision=down_revision, item=item, message=slug.replace("_", " ")
    )
    return str(rendered)


def _revision_graph(versions_dir: Path) -> dict[str, str | None]:
    graph: dict[str, str | None] = {}
    for path in sorted(versions_dir.glob("*.py")):
        if not _REVISION_FILE.fullmatch(path.name):
            continue
        values: dict[str, Any] = {}
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in ("revision", "down_revision"):
                    values[target.id] = ast.literal_eval(node.value)
        graph[str(values["revision"])] = values.get("down_revision")
    return graph


def _heads(graph: dict[str, str | None]) -> list[str]:
    parents = {parent for parent in graph.values() if parent is not None}
    return sorted(set(graph) - parents)


def code_head(versions_dir: Path = VERSIONS_DIR) -> str:
    """The single head revision of the code, which readiness compares with the database."""
    heads = _heads(_revision_graph(versions_dir))
    if len(heads) != 1:
        raise RuntimeError(f"expected one head, found {', '.join(heads) or 'none'}")
    return heads[0]


def write_revision(message: str, item: str, *, versions_dir: Path = VERSIONS_DIR) -> Path:
    """Write ``NNNN_<slug>.py`` after the single current head and return its path."""
    graph = _revision_graph(versions_dir)
    heads = _heads(graph)
    if len(heads) > 1:
        raise RuntimeError(f"several heads: {', '.join(heads)}")
    number = f"{max((int(r) for r in graph), default=0) + 1:04d}"
    slug = slugify(message)
    path = versions_dir / f"{number}_{slug}.py"
    down = heads[0] if heads else None
    path.write_text(render_revision(number=number, slug=slug, item=item, down_revision=down))
    return path
