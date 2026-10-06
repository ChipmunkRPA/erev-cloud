"""Who authors a registry version is asked by its commands (PRD BR-UX-06 rev 1.203; 04 §15.3
API-R-13 rev 1.309; dev-guide DG-KRN-AUTH-04 rev 1.289; item POLICY-TENANT-SCOPE-ALL-ENTITIES-1).

The routes of API-R-13 guard a version's lifecycle with ``config.author`` held for ANY entity:
a route's guard cannot ask for the scope a version is for, which is in the body of a create and
on the row of every other command. Since dev-guide rev 1.295 (DG-KRN-AUTH-03; 04 API-C-03 rev
1.319) the guard's transaction runs under the scope of that permission and so hides an ENTITY
version of another entity; what no guard can ask is "all entities" of a row that names none.
The command asks for the version's scope (``registry_versions.require_authority``): all
entities for a TENANT or BOOK version, the version's entity for an ENTITY version. Two places,
one rule — this test holds them together:

- every command a route guarded by ``command(AUTHOR)`` hands its unit of work to is a lifecycle
  command listed here, so a new route cannot reach a version past the rule;
- every lifecycle command asks the authority before it reads or writes anything else of the
  version: a create right after the scope key it resolved, every other command right after the
  version it locked — before the row's version, its state or its content is told.
"""

from __future__ import annotations

import ast

from support.architecture import read

ROUTES = "backend/erev_api/api/v1/policies.py"
COMMANDS = "backend/erev_api/domain/policies/registry_versions.py"
# The lifecycle commands of a registry version, with the call that must precede the question:
# the scope key of a version that does not exist yet, the lock of one that does.
LIFECYCLE = {
    "create_policy": "scope_key",
    "create_legacy_parity_preset": "scope_key",
    "update_policy": "lock",
    "request_test": "lock",
    "submit_policy": "lock",
    "withdraw_policy": "lock",
    "publish_policy": "lock",
}
QUESTIONS = frozenset({"require_authority", "_require_authority_over"})
# What a command route reads back to answer: no command.
READS = frozenset({"policy_out"})


def _called(node: ast.AST) -> str | None:
    """The name a call names: ``f(...)`` or ``module.f(...)``."""
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _guarded_by_author(function: ast.FunctionDef) -> bool:
    """Whether the route depends on ``command(AUTHOR, ...)``."""
    for argument in function.args.args:
        for node in ast.walk(argument):
            if (
                _called(node) == "command"
                and isinstance(node, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "AUTHOR"
            ):
                return True
    return False


def routed_commands() -> dict[str, set[str]]:
    """Per route guarded by ``command(AUTHOR)``: the functions of ``registry_versions`` it calls
    with its unit of work."""
    found: dict[str, set[str]] = {}
    for node in ast.parse(read(ROUTES)).body:
        if not isinstance(node, ast.FunctionDef) or not _guarded_by_author(node):
            continue
        calls = {
            call.func.attr
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "registry_versions"
            and call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "uow"
        }
        found[node.name] = calls - READS
    return found


def test_every_author_route_runs_a_lifecycle_command() -> None:
    found = routed_commands()
    assert len(found) == len(LIFECYCLE), sorted(found)
    assert all(len(calls) == 1 for calls in found.values()), found
    assert {name for calls in found.values() for name in calls} == set(LIFECYCLE)


def test_every_lifecycle_command_asks_the_authority_first() -> None:
    functions = {
        node.name: node
        for node in ast.parse(read(COMMANDS)).body
        if isinstance(node, ast.FunctionDef)
    }
    assert set(LIFECYCLE) <= set(functions)
    for name, before in LIFECYCLE.items():
        statements = [
            statement
            for statement in functions[name].body
            # the docstring and ``session = uow.session`` read nothing of a version
            if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
            and not (
                isinstance(statement, ast.Assign)
                and isinstance(statement.value, ast.Attribute)
                and statement.value.attr == "session"
            )
        ]
        calls = [
            [called for node in ast.walk(statement) if (called := _called(node)) is not None]
            for statement in statements
        ]
        asks = [index for index, names in enumerate(calls) if QUESTIONS & set(names)]
        assert asks == [1], (name, calls[:3])
        assert calls[0] == [before], (name, calls[0])
