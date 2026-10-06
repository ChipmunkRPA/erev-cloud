"""dev-guide DG-KRN-DB-12 (rev 1.256; 04 §1.4 RLS-TM rev 1.272; item USERS-MEMBER-TENANT-1): a
statement that reads ``tenant_membership`` names the tenant whose members it reads.

Row-level security alone does not: the table has a second, permissive SELECT policy that shows a
user their own memberships of EVERY tenant (the workspace picker reads them), and it holds in a
tenant's transaction too. A loaded sandbox keeps the membership ids of its source. So a SELECT that
named no tenant listed a member of two workspaces twice in each, and a read by id returned two
rows for a member of a workspace and its copy — ``GET /users/{id}``, a role request, an exception
request, the ``preparer`` filter of the approvals list and the start of an access review answered
500 (measured; ``tests/domain/platform/test_sandbox_reset.py``). The same defect was repaired one
statement at a time before (``approvals.engine._membership_of``, ``imports.scope._user_grants``).

This test reads every statement of ``backend/erev_api`` that names the table and fails for a read
that leaves the tenant of a row source open. A row source is the table — under its own name, a
name it is imported or assigned under, or as ``<module>.tenant_membership`` — or an alias of it.
Within one Python statement every SELECT, and every INSERT, UPDATE or DELETE, is read by itself
with the row sources it reaches; a subquery also stands under what the statement around it
names. The tenant of a source is named by

- ``of_session_tenant(<source>)`` (``erev_api.db.session``): the transaction's tenant;
- ``<source>.c.tenant_id == <something>``: a tenant id the caller holds, or the ``tenant_id`` of a
  row the statement joins. The other side may not be a column of a table without the tenant
  policy (``erev_api.db.lint.GLOBAL_TABLES``, the directory ``tenant`` among them, or an alias
  of one), nor another column than ``tenant_id``; the ``tenant_id`` of another row source of
  this table counts when that source is bound;
- continuing ``users.member_select()``, which names it.

Either counts where it is a condition every row must meet: an argument of ``where``, ``filter``
or a join, alone or under ``and_`` or ``&`` — not under ``or_``, ``not_`` or ``case``, and not in
the SELECT list. A local name assigned from an expression stands for the sources that expression
reaches, with what it bound (``joined = tenant_membership.join(...)``, a list of conditions): a
plain assignment replaces what the name stood for, ``append`` adds to it, and what a branch or a
loop binds is not taken as bound.

What needs no condition is the row a statement locks or writes: a row that ``FOR UPDATE``, ``FOR
SHARE`` or ``UPDATE`` reaches passes the policies of UPDATE too, and the tenant policy is the only
one (``tests/pg/test_rls_isolation.py::test_rls_tm_in_a_tenant_transaction_of_a_user``; the table
has no DELETE, IM-M). That is the source a write names as its target and the sources a lock
covers (all of the statement's, or those ``of=`` names) — not a source the same statement only
reads. ``CROSSES_TENANTS`` is the closed list of the functions whose read is meant to cross
tenants — the identity repositories and ``me`` — each with one such read; ``EXPRESSIONS`` lists
the modules that name the table's columns outside a function, where no row source is made.

What the scan cannot read is held by lists of its own. A table taken from the model by name
(``metadata.tables[...]``) may be this one: ``BY_NAME`` lists the modules that do so, and a
SELECT of such a table names the tenant or its function is in ``BY_NAME_OPEN`` with the reason.
``of_session_tenant`` holds for no row in a transaction without a tenant: a module that opens an
identity session does not call it, but for ``IDENTITY_AND_BINDER``. SQL text that names the
table fails here. Not seen: a condition a helper builds (write it out in the statement, as
``audit_labels._member`` does), and a statement completed in a later Python statement — it is
read where it is made, so it names the tenant, or takes its lock, there. The two trigger
functions that read the table name the row's tenant (revisions 0013 and 0024), and the RLS-TN
policy of ``tenant`` reads the user's memberships of every tenant on purpose.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from erev_api.db.lint import GLOBAL_TABLES
from support.architecture import ROOT

APPLICATION: Final = ROOT / "backend" / "erev_api"
MIGRATIONS: Final = "db/migrations/"
TABLE: Final = "tenant_membership"
BINDER: Final = "of_session_tenant"
READS: Final = frozenset({"select", "exists"})
WRITES: Final = frozenset({"insert", "update", "delete"})
# What a condition may stand under and still be met by every row.
CONJUNCTS: Final = frozenset(
    {"where", "filter", "join", "outerjoin", "join_from", "append", "extend"}
)
THROUGH: Final = frozenset({"and_"})
# What a row source may be handed to outside a statement: the makers of a FROM object.
FROM_CALLS: Final = frozenset(
    {"join", "outerjoin", "join_from", "select_from", "alias", "aliased", BINDER}
)
ALIASES: Final = frozenset({"alias", "aliased"})
# A function that returns a SELECT of the table with the tenant named → its module: a statement
# that continues it reads the workspace's members. The test checks that it is what this says.
BUILDERS: Final = {"member_select": "domain/platform/users.py"}
# ``<module path under erev_api>:<function>`` → why its read names no tenant. A closed list: a
# read of the members of a workspace is never added to it, and each holds ONE such read.
CROSSES_TENANTS: Final = {
    "auth/credentials.py:_email_workspace": (
        "the password-reset request: the workspace the user opened last, among all of theirs — "
        "or, without an active membership, the workspace of the open invitation sent last; an "
        "identity transaction, which has no tenant (DG-KRN-DB-02)"
    ),
    "auth/mfa.py:_active_memberships": (
        "the user's ACTIVE memberships of every tenant, each told of a second-factor change; an "
        "identity transaction"
    ),
    "auth/mfa.py:user_memberships": (
        "every membership of the user, for the erasure that removes each (05 PRV-07); an "
        "identity transaction"
    ),
    "auth/sessions.py:_idle_tenants": (
        "the tenants whose idle limit governs a session without a workspace; an identity "
        "transaction"
    ),
    "auth/sessions.py:_workspace_query": (
        "the workspace picker: the workspaces of the user's ACTIVE memberships; an identity "
        "transaction"
    ),
    "auth/sessions.py:memberships": (
        "API-S-Me without a workspace: the user's memberships of every tenant; an identity "
        "transaction"
    ),
    "domain/platform/me.py:me": (
        "API-S-Me: the user's memberships of every tenant beside the active one — the workspace "
        "switcher — read through the user policy on purpose, by ``user_id``"
    ),
}
# Modules that name the table's columns outside a function → what the expression is.
EXPRESSIONS: Final = {
    "api/v1/users.py": "the sort keys of ``GET /users``, applied to ``users.member_select()``",
    "domain/platform/users.py": (
        "the columns API-S-User derives (identity withheld, the name shown), selected by "
        "``member_select()``"
    ),
}
# Modules that take a table from the model by name → which tables, so why not this one open.
BY_NAME: Final = {
    "db/transitions.py": "the tables of the DB-03 registry, which does not govern this one",
    "domain/platform/file_evidence.py": "the tables that hold a file id, each named in the code",
    "domain/platform/sandboxes.py": (
        "the datasets of a copy as it loads them: inserts, and updates that name the sandbox"
    ),
    "domain/platform/snapshot_dataset.py": "the key columns of a dataset's table; no statement",
    "domain/platform/snapshot_export.py": "the columns of a dataset's table; no statement",
    "domain/platform/snapshot_job.py": (
        "every dataset of a copy, this table among them: each read names the tenant"
    ),
}
# ``<module>:<function>`` → why its SELECT of a table taken by name names no tenant.
BY_NAME_OPEN: Final = {
    "db/transitions.py:apply": (
        "reads back the row it could not move, by its id: a table of the DB-03 registry, RLS-T"
    ),
}
# Modules that open an identity session AND call ``of_session_tenant`` → why it holds there.
IDENTITY_AND_BINDER: Final = {
    "auth/invitations.py": (
        "``find_invitation`` sets a tenant context, without a user, before it reads each tenant"
    ),
}
_BRANCHES: Final = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)
_BLOCKS: Final = (*_BRANCHES, ast.With, ast.AsyncWith)
_FUNCTION: Final = (ast.FunctionDef, ast.AsyncFunctionDef)
MODULE: Final = "<module>"


@dataclass(frozen=True, slots=True)
class Statement:
    ref: str  # ``<module path under erev_api>:<function>``, or ``:<module>``
    line: int
    kind: str  # READ, LOCK, WRITE, EXPRESSION or ROW SOURCE (outside a function)
    open: tuple[str, ...] = ()  # the row sources whose tenant the statement leaves open


@dataclass(slots=True)
class _Chain:
    """One SELECT, INSERT, UPDATE or DELETE of a Python statement: the call that begins it and
    the methods chained on it."""

    kind: str
    top: ast.AST
    target: str | None = None  # the source a write names first
    locked: frozenset[str] | None = None  # the sources ``with_for_update(of=...)`` names
    locks_all: bool = False  # ``with_for_update()``: every source of the statement
    outer: _Chain | None = None
    reached: set[str] = field(default_factory=set)
    bound: set[str] = field(default_factory=set)
    peers: list[tuple[str, str]] = field(default_factory=list)

    def all_bound(self) -> set[str]:
        return self.bound | (self.outer.all_bound() if self.outer else set())

    def open(self) -> set[str]:
        bound = self.all_bound()
        while any(peer in bound and source not in bound for source, peer in self.peers):
            bound |= {source for source, peer in self.peers if peer in bound}
        left = self.reached - bound
        if self.kind in WRITES:
            return left - {self.target}
        if self.locks_all:
            return set()
        return left - (self.locked or frozenset())


def _units(tree: ast.Module) -> Iterator[tuple[str, list[ast.stmt]]]:
    """What stands outside every function, then each function of the module with its statements
    — a method as ``Class.method``, a nested function with the one that holds it."""
    loose: list[ast.stmt] = []
    held: list[tuple[str, list[ast.stmt]]] = []
    for node in tree.body:
        if isinstance(node, _FUNCTION):
            held.append((node.name, [node]))
        elif isinstance(node, ast.ClassDef):
            for inner in node.body:
                if isinstance(inner, _FUNCTION):
                    held.append((f"{node.name}.{inner.name}", [inner]))
                else:
                    loose.append(inner)
        elif not isinstance(node, ast.Import | ast.ImportFrom):
            loose.append(node)
    yield MODULE, loose
    yield from held


def _pieces(
    nodes: Iterable[ast.stmt], depth: int = 0
) -> Iterator[tuple[ast.AST, list[ast.AST], int]]:
    """The innermost statements in source order with how many branches or loops stand around
    each: a compound statement gives its header expressions as one piece and then its bodies; a
    function gives its default values as one piece and then its statements."""
    for node in nodes:
        if isinstance(node, _FUNCTION):
            defaults = [d for d in (*node.args.defaults, *node.args.kw_defaults) if d is not None]
            if defaults:
                yield ast.Expr(value=ast.Tuple(elts=defaults), lineno=node.lineno), defaults, depth
            yield from _pieces(node.body, depth)
        elif isinstance(node, ast.ClassDef):
            yield from _pieces(node.body, depth)
        elif isinstance(node, _BLOCKS):
            header: list[ast.AST] = []
            for name in ("test", "iter", "items", "subject"):
                value = getattr(node, name, None)
                if value is not None:
                    header.extend(value if isinstance(value, list) else [value])
            if header:
                yield node, header, depth
            inner = depth + isinstance(node, _BRANCHES)
            for name in ("body", "orelse", "finalbody"):
                yield from _pieces(getattr(node, name, None) or [], inner)
            for handler in getattr(node, "handlers", None) or []:
                yield from _pieces(handler.body, inner)
            for case in getattr(node, "cases", None) or []:
                yield from _pieces(case.body, inner)
        else:
            yield node, [node], depth


def _called(call: ast.Call) -> tuple[str | None, str | None]:
    """(the name called, the name it is an attribute of): ``select`` is ``("select", None)``,
    ``sa.select`` is ``("select", "sa")``, a method of anything but a name ``(name, "")``."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id, None
    if isinstance(func, ast.Attribute):
        return func.attr, func.value.id if isinstance(func.value, ast.Name) else ""
    return None, None


def _column(node: ast.AST) -> tuple[ast.AST, str] | None:
    """(``X``, the column) of ``X.c.<column>``."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "c"
    ):
        return node.value.value, node.attr
    return None


class _Unit:
    """A function, or what stands outside every function, as the scan reads it."""

    def __init__(self, ref: str, sources: dict[str, str], foreign: set[str]) -> None:
        self.ref = ref
        self.sources = dict(sources)  # name → the row source it is: the table, or an alias
        self.foreign = set(foreign)  # names of tables without the tenant policy
        # a local name → (the sources it stands for, those whose tenant its expression names)
        self.stands: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
        self.found: list[Statement] = []

    def source(self, node: ast.AST) -> str | None:
        """The row source a node is: a name of one, or ``<module>.tenant_membership``."""
        if isinstance(node, ast.Name):
            return self.sources.get(node.id) if isinstance(node.ctx, ast.Load) else None
        if isinstance(node, ast.Attribute) and node.attr == TABLE:
            return TABLE
        return None

    def names_a_tenant(self, other: ast.AST) -> str | bool:
        """What stands on the other side of ``<source>.c.tenant_id ==``: the row source of this
        table whose ``tenant_id`` it is; False for a column that names no tenant; else True."""
        column = _column(other)
        if column is None:
            return True
        owner, name = column
        peer = self.source(owner)
        if peer is not None:
            return peer if name == "tenant_id" else False
        if isinstance(owner, ast.Name) and owner.id in self.foreign:
            return False
        return name == "tenant_id"

    def piece(self, node: ast.AST, pieces: list[ast.AST], depth: int) -> None:  # noqa: C901
        parents: dict[int, tuple[ast.AST, str]] = {}
        walked: list[ast.AST] = []
        for root in pieces:
            for parent in ast.walk(root):
                walked.append(parent)
                for name, value in ast.iter_fields(parent):
                    for child in value if isinstance(value, list) else [value]:
                        if isinstance(child, ast.AST):
                            parents[id(child)] = (parent, name)
        calls = [n for n in walked if isinstance(n, ast.Call)]
        # SQL text is not read: it fails wherever it names the table.
        for call in calls:
            if _called(call)[0] == "text" and any(
                isinstance(n, ast.Constant) and isinstance(n.value, str) and TABLE in n.value
                for n in ast.walk(call)
            ):
                self.found.append(Statement(self.ref, call.lineno, "READ", (TABLE,)))

        # The statements of the piece, each with the methods chained on it.
        tops: dict[int, _Chain] = {}
        for call in calls:
            name, owner = _called(call)
            if name in BUILDERS:
                kind = "select"
            elif name in READS | WRITES and (
                owner is None or owner == "sa" or (owner and owner in self.sources)
            ):
                kind = str(name)
            else:
                continue
            top: ast.AST = call
            locked: frozenset[str] | None = None
            locks_all = False
            while True:
                above = parents.get(id(top))
                if above is None or not (
                    isinstance(above[0], ast.Attribute)
                    and above[1] == "value"
                    and id(above[0]) in parents
                    and isinstance(parents[id(above[0])][0], ast.Call)
                    and parents[id(above[0])][1] == "func"
                ):
                    break
                method = parents[id(above[0])][0]
                assert isinstance(method, ast.Call)
                if above[0].attr == "with_for_update":
                    named = [k.value for k in method.keywords if k.arg == "of"]
                    covered: set[str] = set()
                    for value in named:
                        for one in (
                            value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
                        ):
                            covered.add(self.source(one) or "")
                    locked, locks_all = frozenset(covered - {""}), not named
                top = method
            chain = _Chain(kind=kind, top=top, locked=locked, locks_all=locks_all)
            if kind in WRITES and call.args:
                chain.target = self.source(call.args[0])
            if name in BUILDERS:
                chain.reached.add(TABLE)
                chain.bound.add(TABLE)
            tops[id(top)] = chain

        def chain_of(inner: ast.AST) -> _Chain | None:
            current: ast.AST | None = inner
            while current is not None:
                if id(current) in tops:
                    return tops[id(current)]
                above = parents.get(id(current))
                current = above[0] if above else None
            return None

        for chain in tops.values():
            above = parents.get(id(chain.top))
            chain.outer = chain_of(above[0]) if above else None

        def conjunct(inner: ast.AST) -> bool:
            """Whether every row must meet the condition, by what it stands under."""
            child = inner
            while id(child) in parents and id(child) not in tops:
                parent, name = parents[id(child)]
                if isinstance(parent, ast.Call):
                    called = _called(parent)[0]
                    if name == "func" or called not in CONJUNCTS | THROUGH:
                        return False
                    if called in CONJUNCTS:
                        return True
                elif isinstance(parent, ast.BinOp):
                    if not isinstance(parent.op, ast.BitAnd):
                        return False
                elif not isinstance(parent, ast.keyword | ast.Tuple | ast.List | ast.Starred):
                    return isinstance(
                        parent, ast.Assign | ast.AnnAssign | ast.AugAssign | ast.Return
                    )
                child = parent
            return False

        outside = _Chain(kind="expression", top=node)
        handed = False
        for inner in walked:
            chain = chain_of(inner) or outside
            source = self.source(inner)
            if source is not None:
                chain.reached.add(source)
                parent, name = parents.get(id(inner), (None, ""))
                column = isinstance(parent, ast.Attribute) and parent.attr == "c"
                if chain is outside and not column:
                    if isinstance(parent, ast.Call) and name != "func":
                        handed |= _called(parent)[0] not in FROM_CALLS
                    elif isinstance(parent, ast.keyword):
                        handed = True
                    elif not isinstance(parent, ast.Attribute | ast.Assign | ast.AnnAssign):
                        handed = True
            if (
                isinstance(inner, ast.Name)
                and isinstance(inner.ctx, ast.Load)
                and inner.id in self.stands
            ):
                chain.reached |= self.stands[inner.id][0]
                chain.bound |= self.stands[inner.id][1]
            if isinstance(inner, ast.Call) and _called(inner)[0] == BINDER and inner.args:
                bound = self.source(inner.args[0])
                if bound is not None and conjunct(inner):
                    chain.bound.add(bound)
            if isinstance(inner, ast.Compare) and len(inner.ops) == 1:
                if not isinstance(inner.ops[0], ast.Eq) or not conjunct(inner):
                    continue
                left, right = inner.left, inner.comparators[0]
                for one, other in ((left, right), (right, left)):
                    column_of = _column(one)
                    if column_of is None or column_of[1] != "tenant_id":
                        continue
                    source = self.source(column_of[0])
                    named = self.names_a_tenant(other)
                    if source is None or named is False:
                        continue
                    if named is True:
                        chain.bound.add(source)
                    else:
                        chain.peers.append((source, str(named)))

        chains = list(tops.values())
        reached = set(outside.reached).union(*(chain.reached for chain in chains))
        if not reached:
            return
        line = getattr(node, "lineno", 0)
        if chains:
            left = set(outside.open()).union(*(chain.open() for chain in chains))
            one = chains[0]
            if len(chains) == 1 and one.locked is not None and not outside.reached:
                kind = "LOCK" if one.locks_all or one.reached <= one.locked else "READ"
            elif all(chain.kind in WRITES for chain in chains) and all(
                chain.reached <= {chain.target} for chain in (*chains, outside)
            ):
                kind = "WRITE"
            else:
                kind = "READ"
            self.found.append(Statement(self.ref, line, kind, tuple(sorted(left))))
            return
        # No statement: an expression. An assignment makes its target stand for what the
        # expression reaches; an alias is a row source of its own, another name of one the same.
        targets: list[str] = []
        added = False
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign | ast.AugAssign) and isinstance(node.target, ast.Name):
            targets, added = [node.target.id], isinstance(node, ast.AugAssign)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            name, owner = _called(node.value)
            if name in {"append", "extend"} and owner:
                targets, added = [owner], True
        value = getattr(node, "value", None)
        alias = renamed = None
        if isinstance(value, ast.Call) and _called(value)[0] in ALIASES:
            owner_node = value.func.value if isinstance(value.func, ast.Attribute) else None
            first = (
                owner_node if owner_node is not None else (value.args[0] if value.args else None)
            )
            alias = self.source(first) if first is not None else None
        elif value is not None:
            renamed = self.source(value)
        bound = outside.all_bound()
        while any(peer in bound and source not in bound for source, peer in outside.peers):
            bound |= {source for source, peer in outside.peers if peer in bound}
        if self.ref.endswith(f":{MODULE}"):
            columns = all(
                isinstance(above := parents.get(id(n), (None, ""))[0], ast.Attribute)
                and above.attr == "c"
                for n in walked
                if self.source(n) is not None
            )
            kind = "EXPRESSION" if columns else "ROW SOURCE"
            self.found.append(Statement(self.ref, line, kind))
            return
        if handed:
            targets = []  # what a helper the scan cannot read answers stands for nothing
        for target in targets:
            if alias is not None and not added:
                self.sources[target] = target
            elif renamed is not None and not added:
                self.sources[target] = renamed
            else:
                before = self.stands.get(target, (frozenset(), frozenset()))
                sure = frozenset(bound) if depth == 0 else frozenset()
                if added:  # ``append``: what a branch adds is not taken as bound
                    self.stands[target] = (before[0] | reached, before[1] | sure)
                elif depth and target in self.stands:  # one of several assignments
                    self.stands[target] = (before[0] | reached, before[1] & frozenset(bound))
                else:
                    self.stands[target] = (frozenset(reached), frozenset(bound))
        if not targets:
            # The expression leaves the function — a ``return``, an argument, a default value —
            # and is read as the statement it joins.
            self.found.append(
                Statement(self.ref, line, "EXPRESSION", tuple(sorted(reached - bound)))
            )


def scan_module(relative: str, text: str) -> list[Statement]:
    """Every statement of the module that reaches the table, as what it is."""
    tree = ast.parse(text)
    sources = {TABLE: TABLE}
    foreign = set(GLOBAL_TABLES)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                if name.name == TABLE and name.asname:
                    sources[name.asname] = TABLE
                if name.name in GLOBAL_TABLES and name.asname:
                    foreign.add(name.asname)
    found: list[Statement] = []
    for name, nodes in _units(tree):
        unit = _Unit(f"{relative}:{name}", sources, foreign)
        for node, pieces, depth in _pieces(nodes):
            # an alias of a table without the tenant policy names no tenant either
            value = getattr(node, "value", None)
            if (
                isinstance(node, ast.Assign)
                and isinstance(value, ast.Call)
                and _called(value)[0] in ALIASES
            ):
                owner = value.func.value if isinstance(value.func, ast.Attribute) else None
                first = owner if owner is not None else (value.args[0] if value.args else None)
                if isinstance(first, ast.Name) and first.id in unit.foreign:
                    unit.foreign.update(t.id for t in node.targets if isinstance(t, ast.Name))
            unit.piece(node, pieces, depth)
        found.extend(unit.found)
    return found


def scan(root: Path = APPLICATION) -> list[Statement]:
    found: list[Statement] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(MIGRATIONS):
            continue
        text = path.read_text(encoding="utf-8")
        if TABLE in text or any(name in text for name in BUILDERS):
            found.extend(scan_module(relative, text))
    return found


def by_name(text: str) -> tuple[bool, list[str]]:
    """Whether the module takes a table from the model by name (``….tables[...]``), and the
    functions that SELECT such a table without ``<name>.c.tenant_id ==`` as a condition."""
    tree = ast.parse(text)
    taken = any(
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "tables"
        for node in ast.walk(tree)
    )
    open_in: list[str] = []
    for name, nodes in _units(tree):
        tables: set[str] = set()
        for node, pieces, _depth in _pieces(nodes):
            walked = [inner for piece in pieces for inner in ast.walk(piece)]
            subscripts = [
                n
                for n in walked
                if isinstance(n, ast.Subscript)
                and isinstance(n.value, ast.Attribute)
                and n.value.attr == "tables"
            ]
            if subscripts and isinstance(node, ast.Assign):
                tables.update(t.id for t in node.targets if isinstance(t, ast.Name))
            used = {n.id for n in walked if isinstance(n, ast.Name)} & tables
            selects = [n for n in walked if isinstance(n, ast.Call) and _called(n)[0] in READS]
            if not (selects and (used or subscripts)):
                continue
            named = {
                column[0].id
                for n in walked
                if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.Eq)
                for side in (n.left, n.comparators[0])
                if (column := _column(side)) is not None
                and column[1] == "tenant_id"
                and isinstance(column[0], ast.Name)
            }
            if subscripts and not isinstance(node, ast.Assign) or used - named:
                open_in.append(name)
    return taken, sorted(set(open_in))


def test_dg_krn_db_12_a_read_of_memberships_names_the_tenant() -> None:
    found = scan()
    inside = [statement for statement in found if not statement.ref.endswith(f":{MODULE}")]
    reads = [statement for statement in inside if statement.kind == "READ"]
    assert len(reads) >= 45, len(reads)  # the scan sees the product
    open_reads = Counter(statement.ref for statement in inside if statement.open)
    assert open_reads == Counter(dict.fromkeys(CROSSES_TENANTS, 1)), {
        "reads memberships without naming the tenant (of_session_tenant)": sorted(
            f"{statement.ref} line {statement.line}"
            for statement in inside
            if statement.open and statement.ref not in CROSSES_TENANTS
        ),
        "listed as crossing tenants: one such read each, and it is still there": {
            ref: open_reads[ref] for ref in CROSSES_TENANTS if open_reads[ref] != 1
        },
    }
    outside = [statement for statement in found if statement not in inside]
    made = [statement for statement in outside if statement.kind != "EXPRESSION"]
    assert made == [], made  # a row source of the table is made in a function
    modules = {statement.ref.removesuffix(f":{MODULE}") for statement in outside}
    assert modules == set(EXPRESSIONS), {
        "names the table's columns outside a function, and no entry says what for": sorted(
            modules - set(EXPRESSIONS)
        ),
        "listed and names them no longer": sorted(set(EXPRESSIONS) - modules),
    }
    # A builder is what its entry says: one SELECT, with the tenant named.
    for name, module in BUILDERS.items():
        built = [statement for statement in found if statement.ref == f"{module}:{name}"]
        assert [(statement.kind, statement.open) for statement in built] == [("READ", ())], built


def test_what_the_scan_cannot_read_is_listed() -> None:
    """A table taken from the model by name, and ``of_session_tenant`` where a transaction may
    have no tenant: each module that does either is listed with the reason it is right."""
    taking: set[str] = set()
    open_by_name: set[str] = set()
    both: set[str] = set()
    for path in sorted(APPLICATION.rglob("*.py")):
        relative = path.relative_to(APPLICATION).as_posix()
        if relative.startswith(MIGRATIONS) or relative == "db/session.py":
            continue
        text = path.read_text(encoding="utf-8")
        if ".tables[" in text:
            taken, open_in = by_name(text)
            if taken:
                taking.add(relative)
            open_by_name.update(f"{relative}:{name}" for name in open_in)
        if "identity_session" in text and f"{BINDER}(" in text:
            both.add(relative)
    assert taking == set(BY_NAME), {
        "takes a table from the model by name, and no entry says which": sorted(
            taking - set(BY_NAME)
        ),
        "listed and does so no longer": sorted(set(BY_NAME) - taking),
    }
    assert open_by_name == set(BY_NAME_OPEN), {
        "selects a table taken by name without naming the tenant": sorted(
            open_by_name - set(BY_NAME_OPEN)
        ),
        "listed and names it now": sorted(set(BY_NAME_OPEN) - open_by_name),
    }
    assert both == set(IDENTITY_AND_BINDER), {
        "opens an identity session and calls of_session_tenant": sorted(
            both - set(IDENTITY_AND_BINDER)
        ),
        "listed and does so no longer": sorted(set(IDENTITY_AND_BINDER) - both),
    }


# One function per form of statement: what ``scan`` must say of each is in the test below.
FORMS: Final = """
from erev_api.db.tables import tenant_membership as members

def open_by_id(session, membership_id):
    return session.execute(
        select(tenant_membership.c.status).where(tenant_membership.c.id == membership_id)
    ).one_or_none()

def by_the_session(session, membership_id):
    return session.execute(
        select(tenant_membership.c.status).where(
            of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id
        )
    ).one_or_none()

def by_the_session_through_its_module(session):
    return session.execute(
        select(tenant_membership.c.id).where(db_session.of_session_tenant(tenant_membership))
    )

def by_a_held_id(session, tenant_id):
    return session.scalars(
        sa.select(tenant_membership.c.id).where(tenant_membership.c.tenant_id == tenant_id)
    )

def by_a_joined_row(session):
    joined = role_assignment.join(
        tenant_membership,
        and_(
            tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
            tenant_membership.c.id == role_assignment.c.membership_id,
        ),
    )
    conditions = [role_assignment.c.revoked_at.is_(None)]
    conditions.append(tenant_membership.c.status == "ACTIVE")
    return session.execute(select(role_assignment.c.id).select_from(joined).where(*conditions))

def by_a_joined_row_with_an_ampersand(session):
    return session.execute(
        select(role_assignment.c.id).join(
            tenant_membership,
            (tenant_membership.c.tenant_id == role_assignment.c.tenant_id)
            & (tenant_membership.c.id == role_assignment.c.membership_id),
        )
    )

def under_another_name(session, tenant_id):
    table = tenant_membership
    return session.execute(select(table.c.id).where(table.c.tenant_id == tenant_id))

def open_by_a_join_on_the_id(session):
    joined = role_assignment.join(
        tenant_membership, tenant_membership.c.id == role_assignment.c.membership_id
    )
    return session.execute(select(role_assignment.c.id).select_from(joined))

def open_through_the_directory(session, user_id):
    return session.execute(
        select(tenant.c.code)
        .join(tenant_membership, tenant_membership.c.tenant_id == tenant.c.id)
        .where(tenant_membership.c.user_id == user_id)
    )

def open_through_an_alias_of_the_directory(session, user_id):
    workspace = tenant.alias("workspace")
    return session.execute(
        select(workspace.c.code)
        .join(tenant_membership, tenant_membership.c.tenant_id == workspace.c.id)
        .where(tenant_membership.c.user_id == user_id)
    )

def open_by_a_table_without_the_tenant_policy(session, user_id):
    return session.execute(
        select(tenant_membership.c.id)
        .join(security_event, security_event.c.tenant_id == tenant_membership.c.tenant_id)
        .where(tenant_membership.c.user_id == user_id)
    )

def open_by_another_column(session, user_id):
    return session.execute(
        select(tenant_membership.c.id)
        .join(saved_view, tenant_membership.c.tenant_id == saved_view.c.membership_id)
        .where(tenant_membership.c.user_id == user_id)
    )

def open_under_an_or(session, tenant_id, user_id):
    return session.execute(
        select(tenant_membership.c.id).where(
            or_(tenant_membership.c.tenant_id == tenant_id, tenant_membership.c.user_id == user_id)
        )
    )

def open_when_negated(session, tenant_id):
    return session.execute(
        select(tenant_membership.c.id).where(not_(tenant_membership.c.tenant_id == tenant_id))
    )

def open_in_the_select_list(session, tenant_id, user_id):
    return session.execute(
        select(
            tenant_membership.c.id,
            case((tenant_membership.c.tenant_id == tenant_id, 1), else_=0),
        ).where(tenant_membership.c.user_id == user_id)
    )

def an_alias_is_its_own_source(session):
    delegate = tenant_membership.alias("delegate")
    return session.execute(
        select(delegate.c.id).where(
            of_session_tenant(tenant_membership),
            delegate.c.user_id == tenant_membership.c.user_id,
        )
    )

def an_alias_by_the_function(session, user_id):
    other = alias(tenant_membership, "other")
    return session.execute(select(other.c.id).where(other.c.user_id == user_id))

def an_alias_bound_through_the_table(session):
    delegate = tenant_membership.alias("delegate")
    return session.execute(
        select(delegate.c.id).where(
            of_session_tenant(tenant_membership),
            delegate.c.tenant_id == tenant_membership.c.tenant_id,
        )
    )

def a_subquery_under_the_tenant_of_its_statement(session):
    return session.execute(
        select(tenant_membership.c.id).where(
            of_session_tenant(tenant_membership),
            exists().where(notification.c.recipient_membership_id == tenant_membership.c.id),
        )
    )

def locks(session, membership_id):
    session.execute(
        select(tenant_membership.c.id)
        .where(tenant_membership.c.id == membership_id)
        .with_for_update()
    )

def locks_the_table_beside_another(session, membership_id):
    session.execute(
        select(tenant_membership.c.id, app_user.c.email)
        .join(app_user, app_user.c.id == tenant_membership.c.user_id)
        .where(tenant_membership.c.id == membership_id)
        .with_for_update(of=[tenant_membership])
    )

def locks_another_table(session, membership_id):
    session.execute(
        select(tenant_membership.c.id, role_assignment.c.id)
        .where(tenant_membership.c.id == role_assignment.c.membership_id)
        .with_for_update(of=role_assignment)
    )

def locks_the_table_beside_an_open_alias(session):
    other = tenant_membership.alias("other")
    session.execute(
        select(tenant_membership.c.id, other.c.tenant_id)
        .where(other.c.user_id == tenant_membership.c.user_id)
        .with_for_update(of=tenant_membership)
    )

def writes(session, membership_id):
    session.execute(
        update(tenant_membership)
        .where(tenant_membership.c.id == membership_id)
        .values(status="SUSPENDED")
    )

def inserts(session, row):
    session.execute(sa.insert(tenant_membership).values(**row))

def writes_another_table_from_it(session, user_id):
    session.execute(
        update(notification)
        .where(
            notification.c.recipient_membership_id == tenant_membership.c.id,
            tenant_membership.c.user_id == user_id,
        )
        .values(read_at=None)
    )

def writes_from_an_open_read(session):
    session.execute(
        update(notification).where(
            notification.c.recipient_membership_id.in_(select(tenant_membership.c.id))
        )
    )

def continues_the_builder(session, membership_id):
    return session.execute(users.member_select().where(tenant_membership.c.id == membership_id))

def an_open_read_beside_the_builder(session, user_id):
    return session.execute(
        union_all(
            users.member_select(),
            select(tenant_membership.c.id).where(tenant_membership.c.user_id == user_id),
        )
    )

def two_reads_in_one_statement(session, user_id):
    return (
        session.execute(
            select(tenant_membership.c.id).where(of_session_tenant(tenant_membership))
        ),
        session.execute(
            select(tenant_membership.c.id).where(tenant_membership.c.user_id == user_id)
        ),
    )

def a_binding_lost_by_reassignment(session, tenant_id, user_id):
    conditions = [tenant_membership.c.tenant_id == tenant_id]
    conditions = [tenant_membership.c.user_id == user_id]
    return session.execute(select(tenant_membership.c.id).where(*conditions))

def bound_in_one_branch(session, user_id, strict):
    if strict:
        conditions = [of_session_tenant(tenant_membership)]
    else:
        conditions = [tenant_membership.c.user_id == user_id]
    return session.execute(select(tenant_membership.c.id).where(*conditions))

def bound_by_an_append_in_a_branch(session, user_id, strict):
    conditions = [tenant_membership.c.user_id == user_id]
    if strict:
        conditions.append(of_session_tenant(tenant_membership))
    return session.execute(select(tenant_membership.c.id).where(*conditions))

def imported_under_another_name(session, user_id):
    return session.execute(select(members.c.id).where(members.c.user_id == user_id))

def as_an_attribute_of_its_module(session, user_id):
    return session.execute(
        select(tables.tenant_membership.c.id).where(tables.tenant_membership.c.user_id == user_id)
    )

def in_a_default_value(session, statement=select(tenant_membership.c.id)):
    return session.execute(statement)

def handed_to_a_helper(session, user_id):
    rows = read_all(session, tenant_membership, user_id)
    return rows

def in_sql_text(session, user_id):
    return session.execute(
        text("SELECT id FROM erev.tenant_membership WHERE user_id = :u"), {"u": user_id}
    )

def lets_an_open_join_out():
    return tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)

def lets_a_bound_join_out():
    joined = role_assignment.join(
        tenant_membership,
        and_(
            tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
            tenant_membership.c.id == role_assignment.c.membership_id,
        ),
    )
    return joined, [tenant_membership.c.status == "ACTIVE"]

def reads_nothing_of_it(session):
    return session.execute(select(role_assignment.c.id))

SORT_KEYS = {"id": tenant_membership.c.id}
OTHER = tenant_membership.alias("other")
"""


def test_the_scan_reads_each_form_of_statement(tmp_path: Path) -> None:
    """The check can fail, and each way of naming the tenant — and of leaving it open — is read
    as what it is."""
    module = tmp_path / "domain" / "platform"
    module.mkdir(parents=True)
    (module / "example.py").write_text(FORMS, encoding="utf-8")
    found: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for statement in scan(tmp_path):
        found.setdefault(statement.ref.partition(":")[2], []).append(
            (statement.kind, statement.open)
        )
    table = (TABLE,)
    held: list[tuple[str, tuple[str, ...]]] = [("READ", ())]
    left: list[tuple[str, tuple[str, ...]]] = [("READ", table)]
    assert found == {
        "open_by_id": left,
        "by_the_session": held,
        "by_the_session_through_its_module": held,
        "by_a_held_id": held,
        "by_a_joined_row": held,
        "by_a_joined_row_with_an_ampersand": held,
        "under_another_name": held,
        "open_by_a_join_on_the_id": left,
        "open_through_the_directory": left,
        "open_through_an_alias_of_the_directory": left,
        "open_by_a_table_without_the_tenant_policy": left,
        "open_by_another_column": left,
        "open_under_an_or": left,
        "open_when_negated": left,
        "open_in_the_select_list": left,
        "an_alias_is_its_own_source": [("READ", ("delegate",))],
        "an_alias_by_the_function": [("READ", ("other",))],
        "an_alias_bound_through_the_table": held,
        "a_subquery_under_the_tenant_of_its_statement": held,
        "locks": [("LOCK", ())],
        "locks_the_table_beside_another": [("LOCK", ())],
        "locks_another_table": left,
        "locks_the_table_beside_an_open_alias": [("READ", ("other",))],
        "writes": [("WRITE", ())],
        "inserts": [("WRITE", ())],
        "writes_another_table_from_it": left,
        "writes_from_an_open_read": left,
        "continues_the_builder": held,
        "an_open_read_beside_the_builder": left,
        "two_reads_in_one_statement": left,
        "a_binding_lost_by_reassignment": left,
        "bound_in_one_branch": left,
        "bound_by_an_append_in_a_branch": left,
        "imported_under_another_name": left,
        "as_an_attribute_of_its_module": left,
        "in_a_default_value": left,
        "handed_to_a_helper": [("EXPRESSION", table)],
        "in_sql_text": left,
        "lets_an_open_join_out": [("EXPRESSION", table)],
        "lets_a_bound_join_out": [("EXPRESSION", ())],
        MODULE: [("EXPRESSION", ()), ("ROW SOURCE", ())],
    }


def test_a_table_taken_by_name_is_read_with_its_tenant() -> None:
    """``by_name`` sees a SELECT of a table taken from the model by name, and whether it names
    the tenant."""
    taken, open_in = by_name(
        "def whole(session, name):\n"
        "    table = metadata.tables[f'erev.{name}']\n"
        "    return session.execute(select(table)).all()\n"
        "\n"
        "def of_the_tenant(session, name, tenant_id):\n"
        "    table = metadata.tables[f'erev.{name}']\n"
        "    return session.execute(select(table).where(table.c.tenant_id == tenant_id)).all()\n"
        "\n"
        "def at_once(session, name):\n"
        "    return session.execute(select(metadata.tables[f'erev.{name}'])).all()\n"
        "\n"
        "def writes(session, name, row):\n"
        "    table = metadata.tables[f'erev.{name}']\n"
        "    session.execute(insert(table).values(**row))\n"
    )
    assert (taken, open_in) == (True, ["at_once", "whole"])
    assert by_name("def none(session):\n    return session.execute(select(role)).all()\n") == (
        False,
        [],
    )
