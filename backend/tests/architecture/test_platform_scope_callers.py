"""DG-ARC-18: the platform scope has one door, and a list of who opens it
(PLATFORM-SCOPE-ALLOWLIST-1; 05 TXN-07 rev 1.156; supervisor ruling R-108 (b) (6)).

``db/session.platform_session`` is the one way to a transaction that reads across tenants
(``tenant_directory``) or writes a tenant into being (``provisioning``); it sets
``app.platform_scope`` and records ``PLATFORM_SCOPE_USED``. Row-level security lets such a
transaction see what no tenant's own session may see, so every caller is a decision: the list
below names each one - the module, the function and the scope - with its reason, and 05 TXN-07
states the same uses. TXN-07 named three uses while thirteen modules opened the session.

The test fails when a call of ``platform_session`` is not on the list, when a listed call is
gone, when a call names another scope than its entry (a scope that is no string literal must be
a module-level constant of the same module), when anything outside ``db/session.py`` sets
``app.platform_scope`` by itself, and when TXN-07 does not name exactly the listed modules. The
callers of ``tenant_directory.active_tenants`` are listed as well: that function hands the
directory of tenants on to whoever calls it.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import pytest
from support.architecture import ROOT, Finding, iter_files, read, report

RULE: Final = "DG-ARC-18"
PY: Final = frozenset({".py"})
SCOPE: Final = ("backend/erev_api",)
PACKAGE: Final = "backend/erev_api/"
DOOR: Final = "backend/erev_api/db/session.py"
SCOPES: Final = ("tenant_directory", "provisioning")
# A statement that sets the scope without the door: `set_config('app.platform_scope', …)` or
# `SET [LOCAL] app.platform_scope`. Reading it (`current_setting`, a policy) is not setting it.
SETS_THE_SCOPE: Final = re.compile(
    r"set_config\(\s*'app\.platform_scope'|\bSET\s+(?:LOCAL\s+|SESSION\s+)?app\.platform_scope\b",
    re.IGNORECASE,
)

Call = tuple[str, str]  # repository-relative module path, enclosing function

# Who opens a platform session, under which scope, and why.
CALLERS: Final[Mapping[Call, tuple[str, str]]] = {
    ("backend/erev_api/auth/invitations.py", "find_invitation"): (
        "tenant_directory",
        "an invitation is found by its token before any tenant is known (04 §16.12)",
    ),
    ("backend/erev_api/controls/doctor.py", "_tenants"): (
        "tenant_directory",
        "`erev doctor` checks every tenant of the deployment (05 SAR-40)",
    ),
    ("backend/erev_api/controls/recovery.py", "_tenants"): (
        "tenant_directory",
        "`erev verify --all-tenants` verifies each tenant's chains, files and keys (05 OPR-11)",
    ),
    ("backend/erev_api/jobs/registry.py", "defer_for_active_tenants"): (
        "tenant_directory",
        "the periodic fan-out defers one job for each ACTIVE tenant (05 SCH-01, SCH-07)",
    ),
    ("backend/erev_api/jobs/registry.py", "defer_for_due_tenants"): (
        "tenant_directory",
        "the minute sweeps defer one job for each tenant with due work (05 SCH-03, SCH-12)",
    ),
    ("backend/erev_api/jobs/sweeper.py", "_tenant_ids"): (
        "tenant_directory",
        "the job sweeper requeues undispatched jobs tenant by tenant (DG-KRN-JOB-06)",
    ),
    ("backend/erev_api/jobs/sweeper.py", "_directory"): (
        "tenant_directory",
        "the job sweeper reads the tenants and the stalled tasks in one read (DG-KRN-JOB-06)",
    ),
    ("backend/erev_api/files/sweep.py", "tenant_directory"): (
        "tenant_directory",
        "the orphan sweep never deletes the prefix of a tenant of the directory (05 SCH-14)",
    ),
    ("backend/erev_api/domain/platform/support_grants.py", "request_as_operator"): (
        "tenant_directory",
        "`erev support-grant request` finds the tenant by its code",
    ),
    ("backend/erev_api/domain/platform/support_grants.py", "expire_due"): (
        "tenant_directory",
        "the expiry of support grants goes tenant by tenant (05 SCH-15)",
    ),
    ("backend/erev_api/domain/platform/shred_completion.py", "run"): (
        "tenant_directory",
        "the completion of decided shreds goes tenant by tenant, an archived one too (05 SCH-16)",
    ),
    ("backend/erev_api/domain/platform/tenant_directory.py", "active_tenants"): (
        "tenant_directory",
        "the ACTIVE tenants the SCH periodics work through (05 SCH-05, SCH-09, SCH-10)",
    ),
    ("backend/erev_api/domain/platform/provisioning.py", "reissue_admin_invitation"): (
        "tenant_directory",
        "`erev tenant resend-invitation` finds the tenant by its code (04 §14.3 step 5)",
    ),
    ("backend/erev_api/domain/demo/seed.py", "_directory"): (
        "tenant_directory",
        "`erev seed demo` reads which of the requested demo tenants exist",
    ),
    ("backend/erev_api/domain/demo/perf_seed.py", "read_tenant"): (
        "tenant_directory",
        "`erev perf seed` reads whether the volume tenant exists (05 PERF-11)",
    ),
    ("backend/erev_api/controls/reset.py", "unmarked_tenants"): (
        "tenant_directory",
        "`erev db reset` counts the tenants without the demo marker before it drops (DG-ENV-13)",
    ),
    ("backend/erev_api/domain/platform/provisioning.py", "provision_tenant"): (
        "provisioning",
        "`tenant.provision` writes the tenant and its first rows (04 §14.3)",
    ),
    ("backend/erev_api/domain/platform/sandboxes.py", "load_sandbox"): (
        "provisioning",
        "the load of a snapshot provisions the pre-allocated sandbox tenant (05 SBX-04)",
    ),
    ("backend/erev_api/domain/platform/sandboxes.py", "copy_transaction"): (
        "provisioning",
        "the copy phase of that load, in the sandbox tenant's context (04 §14.3 rev 1.85)",
    ),
    ("backend/erev_api/domain/platform/sandbox_reset.py", "create_empty_sandbox"): (
        "provisioning",
        "an empty sandbox is provisioned (05 SBX-02, SBX-07)",
    ),
}
# Who is handed the directory by `tenant_directory.active_tenants`.
DIRECTORY_READERS: Final[Mapping[Call, str]] = {
    ("backend/erev_api/domain/contracts/dirty_sweep.py", "run"): (
        "SCH-17 recovers booked dirty groups in separate SYSTEM tenant transactions"
    ),
    ("backend/erev_api/domain/reference/period_auto_open.py", "eligible_tenants"): (
        "the period tick opens due periods tenant by tenant (05 SCH-05)"
    ),
    ("backend/erev_api/domain/close/data_quality_sweep.py", "run"): (
        "the data-quality monitors run tenant by tenant (05 SCH-10)"
    ),
    ("backend/erev_api/domain/integrations/sweeps.py", "run"): (
        "the reconciliation sweeps are requested tenant by tenant (05 SCH-09)"
    ),
}


def _called(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _constants(tree: ast.Module) -> dict[str, str]:
    """The module-level names bound to one string literal."""
    found: dict[str, str] = {}
    for node in tree.body:
        value: ast.expr | None = None
        names: list[str] = []
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value, names = node.value, [node.target.id]
        elif isinstance(node, ast.Assign):
            value = node.value
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.update({name: value.value for name in names})
    return found


def calls_of(name: str, path: str, source: str) -> Iterator[tuple[str, int, str | None]]:
    """(enclosing function, line, scope) of every call of ``name`` in ``source``; the scope is the
    first argument or ``scope=`` when it is a string literal or a constant of the module."""
    tree = ast.parse(source, filename=path)
    constants = _constants(tree)

    def walk(node: ast.AST, function: str) -> Iterator[tuple[str, int, str | None]]:
        for child in ast.iter_child_nodes(node):
            inside = function
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) and function == "<module>":
                inside = child.name  # a closure belongs to the function that holds it
            if isinstance(child, ast.Call) and _called(child) == name:
                argument = child.args[0] if child.args else None
                for keyword in child.keywords:
                    if keyword.arg == "scope":
                        argument = keyword.value
                scope: str | None = None
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    scope = argument.value
                elif isinstance(argument, ast.Name):
                    scope = constants.get(argument.id)
                yield inside, child.lineno, scope
            yield from walk(child, inside)

    yield from walk(tree, "<module>")


@dataclass(frozen=True, slots=True)
class Facts:
    """What one module does with the platform scope."""

    sessions: tuple[tuple[str, int, str | None], ...]  # calls of ``platform_session``
    directory: tuple[tuple[str, int, str | None], ...]  # calls of ``active_tenants``
    sets: tuple[int, ...]  # the lines that set ``app.platform_scope`` by themselves


def facts_of(path: str, source: str) -> Facts:
    return Facts(
        sessions=tuple(calls_of("platform_session", path, source)),
        directory=tuple(calls_of("active_tenants", path, source)),
        sets=tuple(
            source.count("\n", 0, match.start()) + 1 for match in SETS_THE_SCOPE.finditer(source)
        ),
    )


def check_platform_scope(modules: Mapping[str, Facts]) -> list[Finding]:
    """``modules`` maps repository-relative paths to their facts; the door itself is not judged."""
    findings: list[Finding] = []
    seen: set[Call] = set()
    handed: set[Call] = set()
    for path, facts in sorted(modules.items()):
        if path == DOOR:
            continue
        findings += [
            Finding(path, line, RULE, "sets app.platform_scope without platform_session")
            for line in facts.sets
        ]
        for function, line, scope in facts.sessions:
            entry = CALLERS.get((path, function))
            seen.add((path, function))
            if entry is None:
                findings.append(
                    Finding(
                        path,
                        line,
                        RULE,
                        f"`{function}` opens a platform session and is not a listed caller: "
                        "add it to CALLERS with its reason and to 05 TXN-07, or do without",
                    )
                )
            elif scope != entry[0]:
                found = "no literal or module constant" if scope is None else f"`{scope}`"
                findings.append(
                    Finding(
                        path, line, RULE, f"`{function}` is listed for `{entry[0]}`, not {found}"
                    )
                )
        for function, line, _ in facts.directory:
            handed.add((path, function))
            if (path, function) not in DIRECTORY_READERS:
                findings.append(
                    Finding(
                        path,
                        line,
                        RULE,
                        f"`{function}` reads the tenant directory through `active_tenants` and "
                        "is not a listed reader",
                    )
                )
    for path, function in sorted(set(CALLERS) - seen):
        findings.append(Finding(path, 1, RULE, f"`{function}` is listed and opens no session"))
    for path, function in sorted(set(DIRECTORY_READERS) - handed):
        findings.append(Finding(path, 1, RULE, f"`{function}` is listed and reads no directory"))
    return sorted(findings)


@lru_cache(maxsize=1)
def _repository() -> Mapping[str, Facts]:
    return {path: facts_of(path, read(path)) for path in iter_files(*SCOPE, suffixes=PY)}


def test_dg_arc_18_every_platform_session_is_a_listed_caller() -> None:
    modules = _repository()
    # The door: one function, and the one statement of the package that sets the scope.
    assert "def platform_session(" in read(DOOR) and len(modules[DOOR].sets) == 1
    found = check_platform_scope(modules)
    assert found == [], report(found)
    assert {scope for scope, _ in CALLERS.values()} == set(SCOPES)
    assert all(reason for _, reason in CALLERS.values()) and all(DIRECTORY_READERS.values())


LISTED: Final = "backend/erev_api/jobs/sweeper.py"
_CALL: Final = 'with platform_session({scope}, actor_user_id=None, request_id="r") as db:\n'


def _module(function: str, scope: str, *, head: str = "") -> str:
    return f"{head}def {function}():\n    " + _CALL.format(scope=scope) + "        return db\n"


def _posed(path: str, source: str) -> dict[str, Facts]:
    """The repository with one module replaced, so that only the replacement is a finding."""
    return {**_repository(), path: facts_of(path, source)}


@pytest.mark.parametrize(
    ("path", "source", "expected"),
    [
        # A module that is on no list opens the session.
        (
            "backend/erev_api/domain/contracts/queries.py",
            _module("every_tenants_contracts", '"tenant_directory"'),
            ["`every_tenants_contracts` opens a platform session and is not a listed caller"],
        ),
        # A listed module opens it from another function, and its listed calls are gone.
        (
            LISTED,
            _module("_tenant_ids", '"tenant_directory"') + _module("_other", '"tenant_directory"'),
            [
                "`_directory` is listed and opens no session",
                "`_other` opens a platform session and is not a listed caller",
            ],
        ),
        # Another scope than the entry's, and a scope the source does not state.
        (
            LISTED,
            _module("_tenant_ids", '"provisioning"') + _module("_directory", "chosen"),
            [
                "`_directory` is listed for `tenant_directory`, not no literal or module constant",
                "`_tenant_ids` is listed for `tenant_directory`, not `provisioning`",
            ],
        ),
        # A module constant states the scope: the copy phase's way.
        (
            LISTED,
            _module("_tenant_ids", "DIRECTORY", head='DIRECTORY = "tenant_directory"\n')
            + _module("_directory", '"tenant_directory"'),
            [],
        ),
        # A second way to set the scope.
        (
            "backend/erev_api/domain/reports/framework.py",
            "STATEMENT = \"SELECT set_config('app.platform_scope', 'tenant_directory', true)\"\n",
            ["sets app.platform_scope without platform_session"],
        ),
        (
            "backend/erev_api/domain/reports/framework.py",
            "STATEMENT = \"SET LOCAL app.platform_scope = 'provisioning'\"\n",
            ["sets app.platform_scope without platform_session"],
        ),
        # Reading the scope is not setting it (the policies of `db/migration_ops.py` do).
        (
            "backend/erev_api/domain/reports/framework.py",
            "POLICY = \"current_setting('app.platform_scope', true) = 'tenant_directory'\"\n",
            [],
        ),
        # The directory handed on to a module that is not a listed reader.
        (
            "backend/erev_api/domain/reports/framework.py",
            "def every_tenant(runtime):\n    return active_tenants(runtime, request_id='r')\n",
            ["`every_tenant` reads the tenant directory through `active_tenants`"],
        ),
    ],
)
def test_platform_scope_rules(path: str, source: str, expected: list[str]) -> None:
    findings = check_platform_scope(_posed(path, source))
    assert [finding.rule for finding in findings] == [RULE] * len(expected), report(findings)
    messages = sorted(finding.message for finding in findings)
    assert len(messages) == len(expected), report(findings)
    for message, start in zip(messages, sorted(expected), strict=True):
        assert message.startswith(start), (message, start)


def test_txn_07_states_the_listed_callers() -> None:
    """05 TXN-07 rev 1.156 names every module that opens a platform session, by its path under
    ``backend/erev_api/``, and no other module; and the one door."""
    document = (ROOT / "docs" / "05-ARCHITECTURE.md").read_text(encoding="utf-8")
    (row,) = [line for line in document.split("\n") if line.startswith("| TXN-07 |")]
    named = set(re.findall(r"`([a-z_/]+\.py)`", row))
    listed = {path.removeprefix(PACKAGE) for path, _ in CALLERS}
    assert DOOR.removeprefix(PACKAGE) in named, "TXN-07 names the door"
    assert named - {DOOR.removeprefix(PACKAGE)} == listed
    assert "`platform_session`" in row and "`PLATFORM_SCOPE_USED`" in row
    for scope in SCOPES:
        assert f"`{scope}`" in row
    assert "the login tenant picker" not in row
