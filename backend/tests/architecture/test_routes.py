"""DG-ARC-04 every route guarded (dev-guide §6.8; DG-KRN-AUTH-03; DG-KRN-IDEM-01; D-72), the
routes that answer a session which still owes its second factor are exactly the documented ones
(03 REQ-PLT-005; DG-KRN-AUTH-03), and every guarded route asks one session question before its
body is read, whose kept answer no handler outlives (DG-KRN-AUTH-09; 05 §2.5)."""

from __future__ import annotations

import ast
import json
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Annotated, Any

import erev_api
from erev_api.api.deps import PUBLIC_PATHS, CommandContext, GuardedRoute, command
from erev_api.api.middleware import UPLOAD_PATHS
from erev_api.api.uploads import UploadRoute
from erev_api.auth.dependencies import (
    ANY_PENDING_STEP,
    CHALLENGE_PENDING,
    ENROLMENT_PENDING,
    PERMISSION_EXTENSION,
    open_steps,
    require_authenticated,
    session_questions,
)
from erev_api.auth.principal import RequestContext
from erev_api.config import Environment, Settings
from erev_api.controls.registry import REPOSITORY_ROOT
from erev_api.main import create_app
from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

GUARD_FACTORIES = frozenset({"require", "require_authenticated", "require_operator"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MOCK_PREFIX = "/api/v1/__mocks__/"
# DG-KRN-TEN-05: the operator provisioning route is guarded by require_operator without command.
COMMAND_EXEMPT = frozenset({("POST", "/api/v1/operator/tenants")})
SYNTHETIC = "/api/v1/__synthetic__"
MULTIPART = "multipart/form-data"
# DG-KRN-AUTH-03 (04 API-C-03): what answers a session that owes enrolment or the challenge,
# besides ``GET /session``, an API-C-01 route whose handler reads the session itself. Every other
# route refuses such a session; a route is added here only with the documents.
OPEN_TO_PENDING_SESSION = {
    ("POST", "/api/v1/session/logout"): ANY_PENDING_STEP,
    ("POST", "/api/v1/session/mfa"): CHALLENGE_PENDING,
    ("POST", "/api/v1/me/mfa/enroll"): ENROLMENT_PENDING,
    ("POST", "/api/v1/me/mfa/confirm"): ENROLMENT_PENDING,
}


def routes_of(app: FastAPI) -> list[RouteContext]:
    """Every registered route with its effective path and dependant, included routers expanded."""
    return list(iter_route_contexts(app.routes))


def dependency_calls(dependant: Dependant | None) -> Iterator[Callable[..., Any]]:
    for dependency in dependant.dependencies if dependant is not None else ():
        if dependency.call is not None:
            yield dependency.call
        yield from dependency_calls(dependency)


def factory_of(call: Callable[..., Any]) -> str | None:
    """The helper that built a dependency: ``require.<locals>.dependency`` → ``require``."""
    qualname = getattr(call, "__qualname__", "")
    return qualname.split(".<locals>.", 1)[0] if ".<locals>." in qualname else None


def factories_of(route: RouteContext) -> set[str | None]:
    return {factory_of(call) for call in dependency_calls(getattr(route, "dependant", None))}


def command_failures(routes: Sequence[RouteContext]) -> list[str]:
    """Write routes other than the API-C-01, mock and operator routes lacking ``command(...)``."""
    failures: list[str] = []
    for route in routes:
        path = route.path or ""
        if path.startswith(MOCK_PREFIX) or path in PUBLIC_PATHS:
            continue
        unexempt = {
            method
            for method in frozenset(route.methods or ()) & WRITE_METHODS
            if (method, path) not in COMMAND_EXEMPT
        }
        if unexempt and "command" not in factories_of(route):
            failures.append(f"{sorted(unexempt)} {path}: no command(...)")
    return failures


def test_dg_arc_04_every_route_guarded(app_settings: Settings) -> None:
    routes = routes_of(create_app(app_settings))
    failures: list[str] = []
    for route in routes:
        path = route.path or ""
        if path.startswith(MOCK_PREFIX):
            continue
        methods = sorted(route.methods or ())
        factories = factories_of(route)
        guards = sorted(GUARD_FACTORIES & factories) + (
            ["allow-list"] if path in PUBLIC_PATHS else []
        )
        if len(guards) != 1:
            failures.append(f"{methods} {path}: guards {guards}")
        # DG-KRN-AUTH-03: a require guard is recorded as x-erev-permission by GuardedRoute.
        original = route.original_route
        if isinstance(original, APIRoute) and not isinstance(original, GuardedRoute):
            failures.append(f"{methods} {path}: route class {type(original).__name__}")
        extra = getattr(original, "openapi_extra", None) or {}
        if "require" in factories and PERMISSION_EXTENSION not in extra:
            failures.append(f"{methods} {path}: no {PERMISSION_EXTENSION}")
    assert failures == []
    assert PUBLIC_PATHS <= {route.path for route in routes}


def multipart_routes(routes: Sequence[RouteContext]) -> dict[tuple[str, str], APIRoute]:
    """(method, path) of every route whose request body is a multipart form."""
    found: dict[tuple[str, str], APIRoute] = {}
    for route in routes:
        original = route.original_route
        body = getattr(original, "body_field", None)
        media_type = getattr(getattr(body, "field_info", None), "media_type", None)
        if isinstance(original, APIRoute) and media_type == MULTIPART:
            for method in sorted(route.methods or ()):
                found[(method, route.path or "")] = original
    return found


def test_dg_api_12_a_multipart_route_authenticates_before_its_body(
    app_settings: Settings,
) -> None:
    """dev-guide DG-API-12 (04 API-C-17 rev 1.189; ruling R-111 (8)): FastAPI parses a form
    before it solves a route's dependencies, so a multipart route that is not an ``UploadRoute``
    receives and spools its body before its guard runs. Every multipart route is one, and the
    middleware's upload paths — the routes whose limit is the upload limit — are exactly
    those."""
    uploads = multipart_routes(routes_of(create_app(app_settings)))
    assert uploads, "the upload route is gone: this test holds nothing"
    assert {key: type(route).__name__ for key, route in uploads.items()} == {
        ("POST", "/api/v1/files"): UploadRoute.__name__
    }
    assert all(isinstance(route, UploadRoute) for route in uploads.values())
    assert {path for _, path in uploads} == set(UPLOAD_PATHS)

    # The check sees a plain multipart route: a synthetic one is found and is not an UploadRoute.
    app = FastAPI()
    app.router.route_class = GuardedRoute

    @app.post(f"{SYNTHETIC}/upload")
    def synthetic(
        ctx: Annotated[CommandContext, Depends(command(per_subject=True))],
        file: Annotated[UploadFile, File()],
    ) -> dict[str, str]:
        return {"name": str(file.filename)}

    plain = multipart_routes(routes_of(app))
    assert list(plain) == [("POST", f"{SYNTHETIC}/upload")]
    assert not isinstance(plain[("POST", f"{SYNTHETIC}/upload")], UploadRoute)


def steps_of(route: RouteContext) -> frozenset[str]:
    """The pending second-factor steps the route's session guards answer (none for a route
    without dependencies, such as the generated document routes)."""
    dependant = getattr(route, "dependant", None)
    return frozenset() if dependant is None else frozenset(open_steps(dependant))


def test_dg_krn_auth_03_routes_open_to_a_pending_second_factor(app_settings: Settings) -> None:
    """The second factor is the user's rule: a session guard answers a session that owes a step
    only where the route is declared open to that step, and those routes are the documented four.
    A guard opened on another route fails here until the documents name the route."""
    declared = {
        (method, route.path or ""): steps
        for route in routes_of(create_app(app_settings))
        for method in sorted(route.methods or ())
        if (steps := steps_of(route)) and method != "HEAD"
    }
    assert declared == OPEN_TO_PENDING_SESSION

    synthetic = FastAPI()

    @synthetic.get(f"{SYNTHETIC}/closed")
    def closed(
        auth: Annotated[object, Depends(require_authenticated(tenant=False))],
    ) -> dict[str, str]:
        return {}

    @synthetic.get(f"{SYNTHETIC}/open")
    def opened(
        auth: Annotated[
            object, Depends(require_authenticated(tenant=False, open_to=ENROLMENT_PENDING))
        ],
    ) -> dict[str, str]:
        return {}

    assert {
        route.path: steps_of(route)
        for route in routes_of(synthetic)
        if (route.path or "").startswith(SYNTHETIC)
    } == {f"{SYNTHETIC}/closed": frozenset(), f"{SYNTHETIC}/open": ENROLMENT_PENDING}
    # A tenant route is never open to a pending step.
    for tenant in (True, "optional"):
        try:
            require_authenticated(tenant=tenant, open_to=CHALLENGE_PENDING)  # type: ignore[call-overload]
        except ValueError as refused:
            assert "session route" in str(refused)
        else:
            raise AssertionError(f"tenant={tenant!r} accepted open_to")


def test_dg_arc_04_commands_depend_on_command(app_settings: Settings) -> None:
    assert command_failures(routes_of(create_app(app_settings))) == []

    synthetic = FastAPI()
    synthetic.router.route_class = GuardedRoute

    @synthetic.post(f"{SYNTHETIC}/without-command")
    def without_command(
        ctx: Annotated[RequestContext, Depends(require_authenticated())],
    ) -> dict[str, str]:
        return {}

    @synthetic.post(f"{SYNTHETIC}/with-command")
    def with_command(
        cmd: Annotated[CommandContext, Depends(command("report.run"))],
    ) -> dict[str, str]:
        return {}

    @synthetic.delete(f"{SYNTHETIC}/session-command")
    def session_command(key: Annotated[str, Depends(command())]) -> dict[str, str]:
        return {}

    assert command_failures(routes_of(synthetic)) == [
        f"['POST'] {SYNTHETIC}/without-command: no command(...)"
    ]


def test_dg_krn_auth_09_every_guarded_route_asks_one_session_question(
    app_settings: Settings,
) -> None:
    """dev-guide DG-KRN-AUTH-09 (05 §2.5 rev 1.203; item AUTH-BEFORE-BODY-1): ``GuardedRoute``
    asks a route's session question before the route's body is read, and finds the question by
    its mark. Every route with a guard (DG-ARC-04) carries exactly one; a route of the
    allow-list carries none, and reads its body unasked. A guard factory written later without
    the mark — its routes would answer a caller without a session for the body first — fails
    here by its route."""
    failures: list[str] = []
    guarded = 0
    for route in routes_of(create_app(app_settings)):
        path = route.path or ""
        if path.startswith(MOCK_PREFIX):
            continue
        dependant = getattr(route, "dependant", None)
        questions = () if dependant is None else session_questions(dependant)
        has_guard = bool(GUARD_FACTORIES & factories_of(route))
        guarded += has_guard
        if len(questions) != int(has_guard):
            methods = sorted(route.methods or ())
            failures.append(f"{methods} {path}: {len(questions)} session questions")
    assert failures == []
    assert guarded > 350, guarded

    # The check sees a guard without the mark: a synthetic factory's route is found.
    def unmarked() -> Callable[..., object]:
        def dependency(ctx: Annotated[RequestContext, Depends(command())]) -> object:
            return ctx

        return dependency

    synthetic = FastAPI()
    synthetic.router.route_class = GuardedRoute

    @synthetic.post(f"{SYNTHETIC}/unmarked")
    def without_question(ctx: object = Depends(unmarked())) -> dict[str, str]:  # noqa: B008
        return {}

    @synthetic.post(f"{SYNTHETIC}/marked")
    def with_question(
        ctx: Annotated[RequestContext, Depends(require_authenticated())],
    ) -> dict[str, str]:
        return {}

    assert {
        route.path: len(session_questions(route.dependant))  # type: ignore[attr-defined]
        for route in routes_of(synthetic)
        if (route.path or "").startswith(SYNTHETIC)
    } == {f"{SYNTHETIC}/unmarked": 0, f"{SYNTHETIC}/marked": 1}


# DG-KRN-AUTH-09: the functions that end the session they are called with, by the name the api
# calls them under — a rotation ends the presented session and opens its successor, the sign-out
# ends it. A handler that calls one drops the kept answer (``forget_session``).
SESSION_ENDERS = {
    ("sessions", "select_tenant"): "the workspace opens in a new session",
    ("operators", "select_support_tenant"): "an operator's workspace opens in a new session",
    ("sessions", "sign_out"): "the session ends",
    ("mfa", "verify"): "the challenge rotates the session",
    ("mfa", "confirm"): "the confirmed enrolment rotates the session",
    ("credentials", "change_password"): "the session continues under a new token",
}
# (module under erev_api/api, handler): the five that call them.
SESSION_ENDING_HANDLERS = {
    ("api/v1/session.py", "session_verify_mfa"),
    ("api/v1/session.py", "session_logout"),
    ("api/v1/session.py", "session_select_tenant"),
    ("api/v1/me.py", "me_change_password"),
    ("api/v1/me.py", "me_mfa_confirm"),
}
PACKAGE = Path(erev_api.__file__).parent


def _attribute_calls(node: ast.AST) -> set[tuple[str, str]]:
    """``(module alias, function)`` of every ``alias.function(...)`` call under ``node``."""
    return {
        (call.func.value.id, call.func.attr)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
    }


def _named_calls(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def test_dg_krn_auth_09_a_handler_that_ends_its_session_forgets_the_kept_answer() -> None:
    """dev-guide DG-KRN-AUTH-09: what the identity store answered is kept for the request, and
    a kept answer must not outlive the session it was given for. The handlers that end the
    session they were called with are the five named here, each calls ``forget_session``, and
    the functions of ``erev_api.auth`` that rotate a session (``sessions.reissue``) are exactly
    the rotating ones of ``SESSION_ENDERS`` — a new rotation, or a new handler of one, fails
    here until it forgets."""
    ending: set[tuple[str, str]] = set()
    forgetful: set[tuple[str, str]] = set()
    for path in sorted((PACKAGE / "api").rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if _attribute_calls(node) & set(SESSION_ENDERS):
                ending.add((relative, node.name))
                if "forget_session" in _named_calls(node):
                    forgetful.add((relative, node.name))
    assert ending == SESSION_ENDING_HANDLERS
    assert forgetful == ending

    rotating: set[tuple[str, str]] = set()
    for path in sorted((PACKAGE / "auth").glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if "reissue" in _named_calls(node) or ("sessions", "reissue") in _attribute_calls(node):
                rotating.add((path.stem, node.name))
    assert rotating == set(SESSION_ENDERS) - {("sessions", "sign_out")}
    assert all(SESSION_ENDERS.values())


def mock_paths(app: FastAPI) -> list[str]:
    return [route.path for route in routes_of(app) if (route.path or "").startswith(MOCK_PREFIX)]


def test_dg_arc_04_mocks_excluded(app_settings: Settings) -> None:
    # Under test the mocks are mounted, yet never documented (D-72).
    local = create_app(app_settings)
    assert "/api/v1/__mocks__/oidc/token" in mock_paths(local)
    assert "/api/v1/__mocks__/__admin/faults" in mock_paths(local)
    assert [path for path in local.openapi()["paths"] if path.startswith(MOCK_PREFIX)] == []

    production = create_app(app_settings.model_copy(update={"env": Environment.PRODUCTION}))
    assert mock_paths(production) == []
    assert [path for path in production.openapi()["paths"] if path.startswith(MOCK_PREFIX)] == []

    committed = json.loads((REPOSITORY_ROOT / "docs" / "api" / "openapi.json").read_text("utf-8"))
    assert [path for path in committed["paths"] if path.startswith(MOCK_PREFIX)] == []


# BUILD_SPEC CLO-15: the routes of the two ledger mocks — journals, trial balance and the
# administration of what the ERP itself holds (05 ADP-20 to ADP-23).
LEDGER_MOCKS = ("/api/v1/__mocks__/netsuite/", "/api/v1/__mocks__/qbo/")
LEDGER_MOCK_ROUTES = (
    "/api/v1/__mocks__/netsuite/record/v1/journalEntry/{key}",
    "/api/v1/__mocks__/netsuite/restlet/v1/trialBalance",
    "/api/v1/__mocks__/netsuite/__erp/documents",
    "/api/v1/__mocks__/netsuite/__erp/accounts",
    # 05 ADP-21 rev 1.175: the end of the fault kind READ_LAG
    "/api/v1/__mocks__/netsuite/__erp/journals/release",
    "/api/v1/__mocks__/qbo/v3/company/{realm}/journalentry",
    "/api/v1/__mocks__/qbo/v3/company/{realm}/query",
    "/api/v1/__mocks__/qbo/v3/company/{realm}/reports/TrialBalance",
    "/api/v1/__mocks__/qbo/v3/company/{realm}/reports/TransactionList",
    "/api/v1/__mocks__/qbo/__erp/documents",
)


def test_mock_routes_absent_in_production(app_settings: Settings) -> None:
    """DG-ARC-04 (BUILD_SPEC CLO-15): an app built for production has no route under
    ``/api/v1/__mocks__/netsuite`` or ``/api/v1/__mocks__/qbo``, and ``docs/api/openapi.json``
    lists none; under test every ledger route is mounted, out of the schema."""
    local = create_app(app_settings)
    mounted = mock_paths(local)
    assert [path for path in LEDGER_MOCK_ROUTES if path not in mounted] == []
    assert [path for path in local.openapi()["paths"] if path.startswith(LEDGER_MOCKS)] == []

    production = create_app(app_settings.model_copy(update={"env": Environment.PRODUCTION}))
    assert [path for path in mock_paths(production) if path.startswith(LEDGER_MOCKS)] == []
    assert [path for path in production.openapi()["paths"] if path.startswith(LEDGER_MOCKS)] == []

    committed = json.loads((REPOSITORY_ROOT / "docs" / "api" / "openapi.json").read_text("utf-8"))
    assert [path for path in committed["paths"] if path.startswith(LEDGER_MOCKS)] == []
