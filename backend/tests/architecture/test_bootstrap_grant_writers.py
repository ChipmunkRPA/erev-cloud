"""DG-KRN-APR-08: the mark of the bootstrap Tenant Admin is written by the seed of a workspace,
and who writes its rows is a list (item SBX-EMPTY-BOOTSTRAP-1; 04 §14.3 item 2 rev 1.254;
dev-guide rev 1.242).

``approvals/routing.is_bootstrap_admin`` reads the grant the seed of a workspace wrote: the
``tenant_admin`` assignment whose ``approval_request_id`` names its own ``ROLE_ASSIGNMENT``
request, prepared by SYSTEM with no preparer and approved by rule ``AUTO-BOOTSTRAP``. That rule
approves the role requests of the member it names without a second person, so the mark must
stay what a seed writes, for the member the seed is for. That rests on who writes the rows:

- a request is inserted by ``engine.insert_request`` alone, which two functions call:
  ``engine.submit``, with the principal as the preparer, and
  ``provisioning.grant_bootstrap_admin``, with none;
- an automatic approval is recorded by ``engine.record_auto_approval`` alone, called by the
  same two. ``submit`` reaches it for a ``ROLE_ASSIGNMENT`` only where
  ``engine._seeded_admitted`` admitted the request, which it does for a signed-in member only
  (``tests/unit/approvals/test_seeded_admission.py``) — so the request of a job, which
  ``submit`` would write without a preparer, is never the rule's;
- a role assignment is inserted by ``subjects._apply_role_assignment``, as the subject of the
  request that was approved, and by ``provisioning.grant_bootstrap_admin``;
- ``grant_bootstrap_admin`` is called by the two seeds, ``provisioning.provision_tenant``
  (``tenant.provision``) and ``sandbox_reset.create_empty_sandbox`` (05 SBX-07), and each seed
  has its listed callers: a new one writes the pair for whoever it names.

The test fails when a listed function is referred to from anywhere else in the package — a
call, an alias, a hand-over — when one of the three tables is inserted into by name anywhere
else, when a listed site is gone, and when a caller of ``insert_request`` states its preparer
another way. A new site is a decision: it goes on the list once 04 §14.3 item 2 says why it
does not write the mark, or that it does and for whom.

What the scan reads is names. It does not see a table held in a variable or built into a
statement's text. The load of a snapshot inserts that way (``sandboxes.py``): it copies the
rows of its source as they are, so a sandbox copy holds the pair of its source, which is the
same user's (the witness of the item in ``tests/domain/platform/test_sandbox_reset.py``).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Mapping
from functools import lru_cache
from typing import Final

import pytest
from support.architecture import callee, iter_files, read

PY: Final = frozenset({".py"})
PACKAGE: Final = "backend/erev_api"
ENGINE: Final = "backend/erev_api/approvals/engine.py"
SUBJECTS: Final = "backend/erev_api/approvals/subjects.py"
PROVISIONING: Final = "backend/erev_api/domain/platform/provisioning.py"
SANDBOX_RESET: Final = "backend/erev_api/domain/platform/sandbox_reset.py"
CLI: Final = "backend/erev_api/cli.py"
OPERATOR_TENANTS: Final = "backend/erev_api/api/v1/operator_tenants.py"
DEMO_SEED: Final = "backend/erev_api/domain/demo/seed.py"
PERF_SEED: Final = "backend/erev_api/domain/demo/perf_seed.py"
MODULE: Final = "<module>"
# The rows of the mark, the functions that write them and the two seeds.
TABLES: Final = ("approval_request", "approval_decision", "role_assignment")
FUNCTIONS: Final = (
    "insert_request",
    "record_auto_approval",
    "grant_bootstrap_admin",
    "_grant_bootstrap_admin",
    "provision_tenant",
    "create_empty_sandbox",
)
INSERTS: Final = ("insert", "pg_insert")
# A statement written as text that puts rows into one of the tables, by its plain or quoted name.
SQL_WRITE: Final = re.compile(
    r"(?:INSERT\s+INTO|MERGE\s+INTO|COPY)\s+(?:\"?erev\"?\.)?\"?(" + "|".join(TABLES) + r")\b",
    re.IGNORECASE,
)

Site = tuple[str, str]  # repository-relative module path, enclosing module-level function

WRITERS: Final[Mapping[str, frozenset[Site]]] = {
    "insert_request": frozenset({(ENGINE, "submit"), (PROVISIONING, "grant_bootstrap_admin")}),
    "record_auto_approval": frozenset(
        {(ENGINE, "submit"), (PROVISIONING, "grant_bootstrap_admin")}
    ),
    "grant_bootstrap_admin": frozenset(
        {(PROVISIONING, "_grant_bootstrap_admin"), (SANDBOX_RESET, "create_empty_sandbox")}
    ),
    "_grant_bootstrap_admin": frozenset({(PROVISIONING, "provision_tenant")}),
    # `tenant.provision`: the operator's command and route, and the two seeds of a demo world.
    "provision_tenant": frozenset(
        {
            (CLI, "tenant_create"),
            (OPERATOR_TENANTS, MODULE),  # the import
            (OPERATOR_TENANTS, "create_tenant"),
            (DEMO_SEED, "_seed_tenant"),
            (PERF_SEED, "_provision"),
        }
    ),
    # The EMPTY reset of a sandbox, for its requester.
    "create_empty_sandbox": frozenset(
        {(SANDBOX_RESET, MODULE), (SANDBOX_RESET, "reset_sandbox")}  # `__all__`, and the job's step
    ),
    "insert(approval_request)": frozenset({(ENGINE, "insert_request")}),
    "insert(approval_decision)": frozenset(
        {(ENGINE, "record_auto_approval"), (ENGINE, "_apply_decision")}
    ),
    "insert(role_assignment)": frozenset(
        {(SUBJECTS, "_apply_role_assignment"), (PROVISIONING, "grant_bootstrap_admin")}
    ),
}
# How each caller of ``insert_request`` states the preparer, as its source reads — once each.
PREPARERS: Final[Mapping[Site, tuple[str, str]]] = {
    (ENGINE, "submit"): ("principal.id", "principal.kind.value"),
    (PROVISIONING, "grant_bootstrap_admin"): ("None", "PrincipalKind.SYSTEM.value"),
}
NOT_A_LITERAL: Final = ("<no literal>", "<no literal>")


def _named(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _functions(tree: ast.Module) -> Iterator[tuple[str, ast.AST]]:
    """Each module-level function with its name, and the rest of the module as ``<module>``; a
    closure and a method belong to what holds them."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node.name, node
        else:
            yield MODULE, node


def _referred(node: ast.AST) -> str | None:
    """The listed function a node refers to: its name read, an attribute of that name, an import
    of it under any alias, or the name as a whole string (``getattr``, ``__all__``)."""
    name: object = None
    if isinstance(node, ast.Name | ast.Attribute):
        name = _named(node)
    elif isinstance(node, ast.alias):
        name = node.name.rsplit(".", 1)[-1]
    elif isinstance(node, ast.Constant):
        name = node.value
    return name if isinstance(name, str) and name in FUNCTIONS else None


def writes(path: str, source: str) -> Iterator[tuple[str, str]]:
    """(what, enclosing function) of every reference to a listed function and of every insert
    that names a table of the mark in ``source``: ``insert(table)``, ``sa.insert(table)``,
    ``table.insert()`` and an ``INSERT``, ``MERGE`` or ``COPY`` written as text."""
    for function, body in _functions(ast.parse(source, filename=path)):
        for node in ast.walk(body):
            referred = _referred(node)
            if referred is not None:
                yield referred, function
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for match in SQL_WRITE.finditer(node.value):
                    yield f"insert({match.group(1).lower()})", function
            if not isinstance(node, ast.Call):
                continue
            called = callee(node)
            if called in INSERTS and node.args and _named(node.args[0]) in TABLES:
                yield f"insert({_named(node.args[0])})", function
            elif (
                called == "insert"
                and isinstance(node.func, ast.Attribute)
                and _named(node.func.value) in TABLES
            ):
                yield f"insert({_named(node.func.value)})", function


def preparers_of(path: str, source: str, function: str) -> list[tuple[str, str]]:
    """The sources of ``preparer_id`` and ``preparer_kind`` in the ``values`` mapping of every
    ``insert_request`` call in ``function``; a call without such a literal is named as one."""
    found: list[tuple[str, str]] = []
    for name, body in _functions(ast.parse(source, filename=path)):
        if name != function:
            continue
        for node in ast.walk(body):
            if not isinstance(node, ast.Call) or callee(node) != "insert_request":
                continue
            stated: dict[str, str] = {}
            for keyword in node.keywords:
                if keyword.arg == "values" and isinstance(keyword.value, ast.Dict):
                    stated = {
                        key.value: ast.unparse(value)
                        for key, value in zip(keyword.value.keys, keyword.value.values, strict=True)
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    }
            if {"preparer_id", "preparer_kind"} <= set(stated):
                found.append((stated["preparer_id"], stated["preparer_kind"]))
            else:
                found.append(NOT_A_LITERAL)
    return found


Writes = frozenset[tuple[str, str]]  # (what, enclosing function) pairs of one module


def found_writers(modules: Mapping[str, Writes]) -> dict[str, set[Site]]:
    """``modules`` maps repository-relative paths to what each writes."""
    found: dict[str, set[Site]] = {what: set() for what in WRITERS}
    for path, written in sorted(modules.items()):
        for what, function in written:
            found.setdefault(what, set()).add((path, function))
    return found


@lru_cache(maxsize=1)
def _sources() -> Mapping[str, str]:
    return {path: read(path) for path in iter_files(PACKAGE, suffixes=PY)}


@lru_cache(maxsize=1)
def _repository() -> Mapping[str, Writes]:
    return {path: frozenset(writes(path, source)) for path, source in _sources().items()}


def test_dg_krn_apr_08_the_rows_of_the_bootstrap_mark_have_the_listed_writers() -> None:
    found = found_writers(_repository())
    listed = {what: set(sites) for what, sites in WRITERS.items()}
    assert found == listed, (
        "a writer of approval_request, approval_decision or role_assignment, or a caller of a "
        "seed, appeared or went: read routing.is_bootstrap_admin and 04 §14.3 item 2 before "
        "the list is changed"
    )


def test_dg_krn_apr_08_only_the_seed_states_a_request_without_a_preparer() -> None:
    sources = _sources()
    stated = {site: preparers_of(site[0], sources[site[0]], site[1]) for site in PREPARERS}
    assert stated == {site: [preparer] for site, preparer in PREPARERS.items()}
    assert set(PREPARERS) == set(WRITERS["insert_request"])


def _posed(path: str, source: str) -> dict[str, set[Site]]:
    """What is found beyond the list when one module of the repository is replaced."""
    found = found_writers({**_repository(), path: frozenset(writes(path, source))})
    return {
        what: sites - WRITERS.get(what, frozenset())
        for what, sites in found.items()
        if sites - WRITERS.get(what, frozenset())
    }


POSED: Final = "backend/erev_api/domain/platform/users.py"
_CALL: Final = "{}(session, values={{'preparer_id': {}, 'preparer_kind': {}}}, routed=r, now=n)\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    ids=[
        "second callers",
        "an alias and a hand-over",
        "a third seed",
        "a seed for someone else",
        "inserts past the writers",
        "statements as text",
        "reads",
    ],
    argvalues=[
        (
            "def restore_admin(session):\n"
            "    approvals.insert_request(session, values={}, routed=None, now=None)\n"
            "    approvals.record_auto_approval(session)\n",
            {
                "insert_request": {(POSED, "restore_admin")},
                "record_auto_approval": {(POSED, "restore_admin")},
            },
        ),
        # The name under another one, and the function handed to a caller.
        (
            "from erev_api.approvals.engine import insert_request as open_request\n"
            "def a(session):\n    return retrying(approvals.record_auto_approval)(session)\n"
            "def b(session):\n    return getattr(provisioning, 'grant_bootstrap_admin')(session)\n",
            {
                "insert_request": {(POSED, MODULE)},
                "record_auto_approval": {(POSED, "a")},
                "grant_bootstrap_admin": {(POSED, "b")},
            },
        ),
        (
            "def clone_workspace(session):\n"
            "    def inner():\n"
            "        return provisioning.grant_bootstrap_admin(session)\n"
            "    return inner()\n",
            {"grant_bootstrap_admin": {(POSED, "clone_workspace")}},
        ),
        # A second way into a seed writes the pair for whoever it names.
        (
            "def blank_sandbox(runtime, for_user_id):\n"
            "    return sandbox_reset.create_empty_sandbox(runtime, requested_by=for_user_id)\n"
            "def second_tenant(request):\n    return provisioning.provision_tenant(request)\n",
            {
                "create_empty_sandbox": {(POSED, "blank_sandbox")},
                "provision_tenant": {(POSED, "second_tenant")},
            },
        ),
        (
            "def a(session):\n    session.execute(insert(role_assignment).values())\n"
            "def b(session):\n    session.execute(sa.insert(tables.approval_request))\n"
            "def c(session):\n    session.execute(approval_decision.insert())\n"
            "def d(session):\n    session.execute(pg_insert(role_assignment))\n",
            {
                "insert(role_assignment)": {(POSED, "a"), (POSED, "d")},
                "insert(approval_request)": {(POSED, "b")},
                "insert(approval_decision)": {(POSED, "c")},
            },
        ),
        (
            'A = "insert into erev.approval_request (tenant_id, id) values (:t, :i)"\n'
            'B = \'INSERT INTO "erev"."role_assignment" (id) VALUES (:i)\'\n'
            'def c():\n    return text("COPY erev.approval_decision FROM STDIN")\n'
            'def d():\n    return "MERGE INTO role_assignment USING incoming ON true"\n',
            {
                "insert(approval_request)": {(POSED, MODULE)},
                "insert(role_assignment)": {(POSED, MODULE), (POSED, "d")},
                "insert(approval_decision)": {(POSED, "c")},
            },
        ),
        # Reading the tables, inserting into another one, and prose that names a function.
        (
            "def e(session):\n"
            '    """Like ``provision_tenant``, it calls grant_bootstrap_admin for nobody."""\n'
            "    session.execute(select(role_assignment))\n"
            "    session.execute(insert(role_permission).values())\n"
            '    return "SELECT 1 FROM erev.approval_request"\n',
            {},
        ),
    ],
)
def test_bootstrap_writer_rules(source: str, expected: dict[str, set[Site]]) -> None:
    assert _posed(POSED, source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    ids=["one call", "a second call without a preparer", "values built elsewhere"],
    argvalues=[
        (
            "def submit(session):\n    " + _CALL.format("insert_request", "p.id", "p.kind"),
            [("p.id", "p.kind")],
        ),
        (
            "def submit(session):\n"
            "    "
            + _CALL.format("insert_request", "p.id", "p.kind")
            + "    "
            + _CALL.format("approvals.insert_request", "None", "'SYSTEM'"),
            [("p.id", "p.kind"), ("None", "'SYSTEM'")],
        ),
        (
            "def submit(session):\n    insert_request(session, values=built, routed=r, now=n)\n",
            [NOT_A_LITERAL],
        ),
    ],
)
def test_preparer_rules(source: str, expected: list[tuple[str, str]]) -> None:
    assert preparers_of(POSED, source, "submit") == expected
