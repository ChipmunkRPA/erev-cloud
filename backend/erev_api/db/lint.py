"""Catalogue lint DB-14 (04 §14.1; REQ-PLT-002; CTL-036).

The checks read only the PostgreSQL catalogue, so they run on any connection: ``make migrate`` and
the test session fixture run them as ``erev_app`` (``lint_as_app``); lint tests run them inside a
rolled-back owner transaction that holds probe objects.

Immutability classes are not visible in the catalogue by themselves. ``migration_ops.apply_class``
records the class id (for example ``IM-A``) as the table comment, and check (g) reads it. Check (g)
also requires the DB-01 TRUNCATE trigger on each child partition of an IM-A parent (D-78).

Check (i) (04 rev 1.182; supervisor rulings R-97 (7) and R-116 (h)): the DB-07 period guard is
created on the table — for ``subledger_line`` a partitioned parent — and reaches the partitions
only because PostgreSQL clones a row trigger to each of them; a partition whose copy is missing or
disabled would admit a line into a closed period. The check names every table of
``PERIOD_GUARD_TABLES`` and every partition of it, the default partition included, that lacks the
enabled guard. ``journal_run`` joined those tables with its own guard (04 rev 1.205; revision
0104; item JR-CLOSED-PERIOD-GUARD-1): a run is neither inserted nor cancelled in a closed period.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, text

from erev_api.db.session import APP_ROLE, identity_session

CHECKS: Final = ("a", "b", "c", "d", "e", "f", "g", "h", "i")
# 04 §14.1 DB-07: the tables whose inserts the period guard ``tg_<table>__period_guard`` decides.
PERIOD_GUARD_TABLES: Final = ("journal_line", "journal_run", "subledger_line")

# DB-14 (b): tables without ``tenant_id`` that may exist in schema erev.
GLOBAL_TABLES: Final = frozenset(
    {
        "tenant",
        "app_user",
        "identity_provider",
        "user_mfa_factor",
        "user_recovery_code",
        "user_session",
        "security_event",
        "password_reset_token",
        "permission",
        "currency",
        "registry_parameter",
        "registry_parameter_correction",  # T-PLT-47 (04 rev 1.59)
        "report_definition",
        "import_template",
        "engine_release",
    }
)
# The Alembic version table lives in schema erev (DG-MIG-01); it holds no application data.
TOOLING_TABLES: Final = frozenset({"alembic_version"})

# pg_trigger.tgtype bits (PostgreSQL include/catalog/pg_trigger.h).
_ROW: Final = 1
_BEFORE: Final = 2
_INSERT: Final = 4
_DELETE: Final = 8
_UPDATE: Final = 16
_TRUNCATE: Final = 32

_TABLES = text(
    """
    SELECT c.relname,
           EXISTS (SELECT 1 FROM pg_attribute a
                   WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped)
             AS has_tenant_id,
           c.relrowsecurity,
           c.relforcerowsecurity,
           EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid) AS has_policy
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'erev' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
    ORDER BY c.relname
    """
)
_ROLE = text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :role")
_VIEWS = text(
    """
    SELECT c.relname, c.relkind, coalesce(c.reloptions, '{}') AS options
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'erev' AND c.relkind IN ('v', 'm')
    ORDER BY c.relname
    """
)
_PARTITION_PRIVILEGES = text(
    """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'erev' AND c.relispartition AND c.relkind IN ('r', 'p')
      AND (has_table_privilege(:role, c.oid,
             'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN')
           OR has_any_column_privilege(:role, c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'))
    ORDER BY c.relname
    """
)
_APPEND_ONLY_TRIGGERS = text(
    """
    SELECT c.relname, t.tgtype, t.tgenabled,
           t.tgfoid IS DISTINCT FROM 'erev.tg_forbid_mutation()'::regprocedure
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN (pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid)
      ON t.tgrelid = c.oid AND NOT t.tgisinternal
      AND (t.tgfoid = 'erev.tg_forbid_mutation()'::regprocedure
           OR (p.pronamespace = n.oid AND p.proname = 'tg_' || c.relname || '__transition'))
    WHERE n.nspname = 'erev' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
      AND obj_description(c.oid, 'pg_class') = 'IM-A'
    ORDER BY c.relname
    """
)
# Every child partition (at any depth) of an IM-A parent, with its DB-01 triggers (D-78).
_PARTITION_TRUNCATE_TRIGGERS = text(
    """
    SELECT child.relname, parent.relname, t.tgtype, t.tgenabled
    FROM pg_class parent
    JOIN pg_namespace n ON n.oid = parent.relnamespace
    CROSS JOIN LATERAL pg_partition_tree(parent.oid::regclass) tree
    JOIN pg_class child ON child.oid = tree.relid
    LEFT JOIN pg_trigger t ON t.tgrelid = child.oid AND NOT t.tgisinternal
      AND t.tgfoid = 'erev.tg_forbid_mutation()'::regprocedure
    WHERE n.nspname = 'erev' AND parent.relkind = 'p' AND NOT parent.relispartition
      AND obj_description(parent.oid, 'pg_class') = 'IM-A'
      AND tree.relid <> parent.oid
    ORDER BY child.relname
    """
)
# Each DB-07 table and every relation of its partition tree (the default partition included),
# with the period guard's trigger on that relation: the same function, a row trigger before insert.
_PERIOD_GUARD_TRIGGERS = text(
    """
    SELECT member.relname, root.relname, t.tgtype, t.tgenabled
    FROM pg_class root
    JOIN pg_namespace n ON n.oid = root.relnamespace
    CROSS JOIN LATERAL (
      SELECT root.oid AS relid
      UNION
      SELECT tree.relid FROM pg_partition_tree(root.oid::regclass) tree
    ) part
    JOIN pg_class member ON member.oid = part.relid
    LEFT JOIN pg_trigger t ON t.tgrelid = member.oid AND NOT t.tgisinternal
      AND t.tgfoid = to_regprocedure(format('erev.%I()', 'tg_' || root.relname || '__period_guard'))
    WHERE n.nspname = 'erev' AND root.relname = ANY(:tables) AND NOT root.relispartition
    ORDER BY member.relname
    """
)
_FORBID_MUTATION_EXISTS = text(
    "SELECT to_regprocedure('erev.tg_forbid_mutation()') IS NOT NULL"
    " OR NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'erev' AND obj_description(c.oid, 'pg_class') = 'IM-A')"
)
_SECURITY_DEFINER = text(
    """
    SELECT format('%I.%I(%s)', n.nspname, p.proname, pg_get_function_identity_arguments(p.oid))
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'erev' AND p.prosecdef
    ORDER BY 1
    """
)


@dataclass(frozen=True, slots=True)
class LintFinding:
    check: str  # "a" to "h", as lettered in 04 DB-14
    object_name: str
    message: str

    def __str__(self) -> str:
        return f"DB-14({self.check}) {self.object_name}: {self.message}"


def _table_checks(connection: Connection, selected: frozenset[str]) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for name, has_tenant_id, rls, forced, has_policy in connection.execute(_TABLES):
        missing = [
            label
            for label, present in (("ROW LEVEL SECURITY", rls), ("FORCE", forced))
            if not present
        ]
        # RLS-NONE-U tables such as security_event carry a nullable tenant_id without RLS (04 §1.4).
        tenant_table = has_tenant_id and name not in GLOBAL_TABLES
        if tenant_table and "a" in selected and (missing or not has_policy):
            missing += [] if has_policy else ["a policy"]
            findings.append(LintFinding("a", name, "tenant table lacks " + ", ".join(missing)))
        allowed = name in GLOBAL_TABLES or name in TOOLING_TABLES
        if not has_tenant_id and "b" in selected and not allowed:
            findings.append(
                LintFinding("b", name, "table without tenant_id is not in the global allow-list")
            )
        if name == "tenant" and "c" in selected and not (rls and forced):
            findings.append(LintFinding("c", name, "tenant lacks forced row level security"))
    return findings


def _role_check(connection: Connection) -> list[LintFinding]:
    row = connection.execute(_ROLE, {"role": APP_ROLE}).one_or_none()
    if row is None:
        return [LintFinding("d", APP_ROLE, "role does not exist")]
    flags = [label for label, value in (("SUPERUSER", row[0]), ("BYPASSRLS", row[1])) if value]
    return [LintFinding("d", APP_ROLE, "role has " + ", ".join(flags))] if flags else []


def _view_checks(connection: Connection) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for name, kind, options in connection.execute(_VIEWS):
        if kind == "m":
            findings.append(LintFinding("e", name, "materialized views are not used (NC-17)"))
            continue
        invoker = {option.lower() for option in options} & {
            "security_invoker=true",
            "security_invoker=on",
            "security_invoker=1",
        }
        if not invoker:
            findings.append(LintFinding("e", name, "view lacks security_invoker = true"))
    return findings


def _partition_check(connection: Connection) -> list[LintFinding]:
    return [
        LintFinding("f", name, f"{APP_ROLE} holds a privilege on a child partition")
        for (name,) in connection.execute(_PARTITION_PRIVILEGES, {"role": APP_ROLE})
    ]


def _append_only_check(connection: Connection) -> list[LintFinding]:
    if not connection.execute(_FORBID_MUTATION_EXISTS).scalar_one():
        return [LintFinding("g", "erev.tg_forbid_mutation", "DB-01 function is missing")]
    coverage: dict[str, int] = {}
    for name, tgtype, enabled, transition in connection.execute(_APPEND_ONLY_TRIGGERS):
        covered = coverage.setdefault(name, 0)
        if tgtype is None or enabled == "D" or not tgtype & _BEFORE:
            continue
        if transition:
            # An IM-A table with an update allow-list (04 T-PLT-29) guards UPDATE through its DB-03
            # transition trigger instead of DB-01.
            if tgtype & _ROW:
                covered |= tgtype & _UPDATE
                coverage[name] = covered
            continue
        if tgtype & _ROW:
            covered |= tgtype & (_UPDATE | _DELETE)
        else:
            covered |= tgtype & _TRUNCATE
        coverage[name] = covered
    required = _UPDATE | _DELETE | _TRUNCATE
    findings = [
        LintFinding(
            "g", name, "IM-A table lacks an enabled DB-01 trigger for UPDATE, DELETE and TRUNCATE"
        )
        for name, covered in sorted(coverage.items())
        if covered & required != required
    ]
    # TRUNCATE of a child partition does not fire the parent's statement trigger.
    guarded: dict[tuple[str, str], bool] = {}
    for name, parent, tgtype, enabled in connection.execute(_PARTITION_TRUNCATE_TRIGGERS):
        key = (name, parent)
        truncate = (
            tgtype is not None
            and enabled != "D"
            and bool(tgtype & _BEFORE)
            and not tgtype & _ROW
            and bool(tgtype & _TRUNCATE)
        )
        guarded[key] = guarded.get(key, False) or truncate
    findings += [
        LintFinding(
            "g",
            name,
            f"child partition of IM-A table {parent} lacks an enabled DB-01 TRUNCATE trigger",
        )
        for (name, parent), present in sorted(guarded.items())
        if not present
    ]
    return findings


def _period_guard_check(connection: Connection) -> list[LintFinding]:
    guarded: dict[tuple[str, str], bool] = {}
    rows = connection.execute(_PERIOD_GUARD_TRIGGERS, {"tables": list(PERIOD_GUARD_TABLES)})
    for name, root, tgtype, enabled in rows:
        key = (name, root)
        guard = (
            tgtype is not None
            and enabled != "D"
            and tgtype & (_ROW | _BEFORE | _INSERT) == _ROW | _BEFORE | _INSERT
        )
        guarded[key] = guarded.get(key, False) or guard
    return [
        LintFinding(
            "i",
            name,
            f"lacks the enabled DB-07 period guard of {root} (a row trigger before insert)",
        )
        for (name, root), present in sorted(guarded.items())
        if not present
    ]


def _definer_check(connection: Connection) -> list[LintFinding]:
    return [
        LintFinding("h", signature, "function is SECURITY DEFINER (NC-18)")
        for (signature,) in connection.execute(_SECURITY_DEFINER)
    ]


def run_lint(connection: Connection, *, checks: Sequence[str] = CHECKS) -> list[LintFinding]:
    """Run the selected DB-14 checks on ``connection``; an empty list means the catalogue passes."""
    unknown = sorted(set(checks) - set(CHECKS))
    if unknown:
        raise ValueError(f"unknown DB-14 checks: {', '.join(unknown)}")
    selected = frozenset(checks)
    findings = _table_checks(connection, selected) if selected & {"a", "b", "c"} else []
    if "d" in selected:
        findings += _role_check(connection)
    if "e" in selected:
        findings += _view_checks(connection)
    if "f" in selected:
        findings += _partition_check(connection)
    if "g" in selected:
        findings += _append_only_check(connection)
    if "h" in selected:
        findings += _definer_check(connection)
    if "i" in selected:
        findings += _period_guard_check(connection)
    return sorted(findings, key=lambda finding: (finding.check, finding.object_name))


@contextmanager
def catalogue_connection(*, request_id: str) -> Iterator[Connection]:
    """An ``erev_app`` connection without tenant context for catalogue and global-table reads:
    this lint and ``erev doctor`` (DG-KRN-DB-02 admits only this module besides ``auth``)."""
    with identity_session(request_id=request_id) as session:
        yield session.connection()


def lint_as_app(
    *, request_id: str = "db-lint", checks: Sequence[str] = CHECKS
) -> list[LintFinding]:
    """Run the lint as ``erev_app`` through an identity session (DG-MK-migrate step 3)."""
    with catalogue_connection(request_id=request_id) as connection:
        return run_lint(connection, checks=checks)
