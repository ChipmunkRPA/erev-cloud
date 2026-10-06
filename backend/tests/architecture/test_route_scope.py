"""DG-KRN-AUTH-03 (rev 1.295): a guarded transaction is a transaction of the permission that
admitted it — no route's transaction opens under the union of its caller's roles where a
permission guard admitted the caller (04 API-C-03 rev 1.319; 03 REQ-PLT-012 rev 1.146; item
READ-SCOPE-BY-PERMISSION-1, register index 301; the supervisor's ruling of 2026-10-03).

``auth.dependencies.require`` hands on a request context whose principal carries the scope of
the route's OWN permission (``admitted_by``), and every session and unit of work a route opens
takes its entity scope from the context it is handed (``Principal.db_context``). The rule is in
one place; this test holds the three ways it could come apart, by reading the routes and the
source:

1. The guard answers the narrowed context and nothing else: ``require``'s dependency has one
   ``return``, of ``admitted_by(ctx, permission)``; the two guards built on it —
   ``require_all_entities`` and ``api.deps.command`` — take their context from a ``require``
   guard and hand that one on.
2. No guarded route takes a context beside its guard: in the dependency tree of every route
   that declares a permission, the session question — the function that answers whose request
   this is — is asked under a permission guard only. A handler that also declared
   ``Depends(get_request_context)`` would hold the union again.
3. The context of a transaction is its guard's alone: nothing outside ``auth.dependencies``
   rebuilds a principal's ``entity_scope`` from the session (``admitted_by`` has one caller).

A route without a permission guard — the session, the approvals, the jobs, the files, a command
whose permission depends on its body — keeps the union, as ruled; what it asks, it asks in its
handler. The scope a guarded route's transaction reads under is witnessed on the database in
``tests/api/test_read_scope_by_permission.py``.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Annotated, Any

from erev_api.api.deps import GuardedRoute, command
from erev_api.auth import dependencies
from erev_api.auth.dependencies import declared_permissions, get_request_context, require
from erev_api.auth.principal import RequestContext
from erev_api.config import Settings
from erev_api.main import create_app
from fastapi import Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import iter_route_contexts
from support.architecture import iter_files, read

DEPENDENCIES = "backend/erev_api/auth/dependencies.py"
DEPS = "backend/erev_api/api/deps.py"
PERMISSION = dependencies._PERMISSION_ATTRIBUTE
QUESTION = dependencies._SESSION_QUESTION_ATTRIBUTE
SYNTHETIC = "/api/v1/__synthetic__"


def beside_the_guard(dependant: Dependant) -> list[str]:
    """The session questions in a route's dependency tree that are asked anywhere but directly
    under a permission guard, by the name of whoever asks."""
    found: list[str] = []

    def walk(node: Dependant, asked_by: Callable[..., Any] | None) -> None:
        for child in node.dependencies:
            call = child.call
            if getattr(call, QUESTION, False) and getattr(asked_by, PERMISSION, None) is None:
                found.append(getattr(asked_by, "__qualname__", "the route itself"))
            walk(child, call)

    walk(dependant, None)
    return found


def test_no_guarded_route_takes_a_context_beside_its_guard(app_settings: Settings) -> None:
    failures: list[str] = []
    guarded = 0
    for route in iter_route_contexts(create_app(app_settings).routes):
        dependant = getattr(route, "dependant", None)
        if dependant is None or not declared_permissions(dependant):
            continue
        guarded += 1
        for asker in beside_the_guard(dependant):
            failures.append(f"{sorted(route.methods or ())} {route.path}: asked by {asker}")
    assert failures == []
    assert guarded > 300, guarded  # 350 operations declared a permission when the rule was written

    # The check sees a context taken beside the guard: a synthetic route that declares both.
    synthetic = FastAPI()
    synthetic.router.route_class = GuardedRoute

    @synthetic.get(f"{SYNTHETIC}/beside")
    def beside(
        ctx: Annotated[RequestContext, Depends(require("contract.read"))],
        whole: Annotated[RequestContext, Depends(get_request_context)],
    ) -> dict[str, str]:
        return {}

    @synthetic.get(f"{SYNTHETIC}/guard-alone")
    def alone(ctx: Annotated[RequestContext, Depends(require("contract.read"))]) -> dict[str, str]:
        return {}

    @synthetic.post(f"{SYNTHETIC}/all-entities")
    def tenant_wide(cmd: Annotated[Any, Depends(command("audit.read", all_entities=True))]) -> None:
        return None

    assert {
        route.path: beside_the_guard(route.dependant)  # type: ignore[attr-defined]
        for route in iter_route_contexts(synthetic.routes)
        if (route.path or "").startswith(SYNTHETIC)
    } == {
        f"{SYNTHETIC}/beside": ["the route itself"],
        f"{SYNTHETIC}/guard-alone": [],
        f"{SYNTHETIC}/all-entities": [],
    }


def _function(tree: ast.AST, *names: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """The function ``names[-1]`` nested in ``names[:-1]``; of several definitions of a name —
    the overloads of ``command`` — the last, which is the one that runs."""
    node: ast.AST = tree
    for name in names:
        node = [
            child
            for child in ast.walk(node)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and child.name == name
            and child is not node
        ][-1]
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return node


def _returns(function: ast.AST) -> list[str]:
    return [
        ast.unparse(node.value) if node.value is not None else ""
        for node in ast.walk(function)
        if isinstance(node, ast.Return)
    ]


def test_the_guard_answers_the_context_of_its_own_permission() -> None:
    """(1): the three guards, by their source."""
    tree = ast.parse(read(DEPENDENCIES))
    # ``require``: its dependency returns the narrowed context, and only that
    assert _returns(_function(tree, "require", "dependency")) == ["admitted_by(ctx, permission)"]
    # ``require_all_entities``: built on ``require(permission)``, hands on what that guard answered
    tenant_wide = _function(tree, "require_all_entities")
    assert "guard = require(permission)" in ast.unparse(tenant_wide)
    inner = _function(tree, "require_all_entities", "dependency")
    assert _returns(inner) == ["ctx"]
    defaults = [ast.unparse(default) for default in inner.args.defaults]
    assert defaults == ["Depends(guard)"]
    # ``api.deps.command``: a named permission is guarded by one of the two, and the command
    # context carries that guard's context
    deps = ast.parse(read(DEPS))
    built = ast.unparse(_function(deps, "command"))
    assert (
        "guard = require_all_entities(permission) if all_entities else require(permission)" in built
    )
    inner = _function(deps, "command", "command_dependency")
    assert [ast.unparse(default) for default in inner.args.defaults] == ["Depends(guard)"]
    assert _returns(inner) == ["CommandContext(ctx=ctx, started=outcome, expected_version=version)"]


def test_the_scope_of_a_transaction_is_its_guards_alone() -> None:
    """(3): ``admitted_by`` is called by ``require`` and by nothing else in the product, and no
    module but ``auth.dependencies`` replaces a principal's ``entity_scope`` on a request
    context. (The import job narrows its own SYSTEM principal — ``imports.scope`` — and the
    exception queue builds another member's principal to ask what she reads; neither is a
    request's context.)"""
    callers: list[str] = []
    for path in iter_files("backend/erev_api", suffixes=frozenset({".py"})):
        for node in ast.walk(ast.parse(read(path))):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = (
                callee.id
                if isinstance(callee, ast.Name)
                else callee.attr
                if isinstance(callee, ast.Attribute)
                else None
            )
            if name == "admitted_by":
                callers.append(path)
    assert callers == [DEPENDENCIES]
