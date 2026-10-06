"""DG-ARC-08 for the binding of caller-named files (04 T-PLT-29 "Binding"; 03 REQ-PLT-012;
independent review of the platform security merge, ruling R-111 (1), item FILE-BIND-READABLE-1).

A command that takes a file id from its caller binds it through ``file_access.bound``, which
answers the row only for a file the caller may read. ``file_access.FILE_BINDINGS`` names every
request member that names a file with the function that binds it; these tests keep that list
whole as the API grows — a new request member that names a file fails here until someone binds
it — hold each named function to the helper, and keep the table of 04 word for word what the
code states.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
import textwrap

from erev_api import schemas
from erev_api.domain.platform import file_access
from erev_api.domain.platform.file_access import FILE_BINDINGS
from erev_api.main import create_app
from pydantic import BaseModel
from support.architecture import ROOT

DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"
BINDING_HEADING = "**Binding (authoritative"
BINDING_HEADER = (
    "| Request member | Route | A file that is missing or that the caller may not read |"
)
# A member of a request model that names a file: ``file_id``, ``<something>_file_id``,
# ``file_object_id`` and their plurals.
FILE_MEMBER = re.compile(r"^(?:\w+_)?file(?:_object)?_ids?$")
# The routes whose PATH names a file: the file's own reads, which ask the read question
# themselves, and the shred and its request (04 rev 1.142), which bind nothing (04 T-PLT-29
# "Binding", last sentence).
FILE_PATHS = frozenset(
    {
        ("GET", "/api/v1/files/{file_id}"),
        ("GET", "/api/v1/files/{file_id}/content"),
        ("POST", "/api/v1/files/{file_id}/request-shred"),
        ("POST", "/api/v1/files/{file_id}/shred"),
    }
)


def request_models() -> list[type[BaseModel]]:
    """Every request model of the API: the ``…In`` models of ``erev_api.schemas``."""
    found: dict[str, type[BaseModel]] = {}
    for module_info in pkgutil.iter_modules(schemas.__path__):
        module = importlib.import_module(f"{schemas.__name__}.{module_info.name}")
        for name, value in vars(module).items():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
                and name.endswith("In")
            ):
                found[name] = value
    return list(found.values())


def file_members() -> set[str]:
    """``<Model>.<member>`` of every request member that names a file."""
    return {
        f"{model.__name__}.{member}"
        for model in request_models()
        for member in model.model_fields
        if FILE_MEMBER.fullmatch(member)
    }


def binder_function(binder: str) -> ast.FunctionDef:
    module_name, _, function_name = binder.partition(":")
    function = getattr(importlib.import_module(module_name), function_name)
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    node = tree.body[0]
    assert isinstance(node, ast.FunctionDef), binder
    return node


def calls_bound(node: ast.AST) -> bool:
    """Whether the function calls ``file_access.bound(…)``."""
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "bound"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "file_access"
        for call in ast.walk(node)
    )


def test_dg_arc_08_every_request_member_that_names_a_file_is_registered() -> None:
    members = file_members()
    assert len(request_models()) >= 100
    assert members == set(FILE_BINDINGS)
    # Only the replay plan is not bound: its command refuses the mode whole (LMG-4, not built).
    assert {member for member, binding in FILE_BINDINGS.items() if binding.binder is None} == {
        "ReplayPlanItemIn.file_id"
    }


def test_dg_arc_08_every_binder_asks_through_the_helper_and_reads_no_file_row_itself() -> None:
    for member, binding in FILE_BINDINGS.items():
        if binding.binder is None:
            continue
        function = binder_function(binding.binder)
        assert calls_bound(function), f"{member}: {binding.binder} does not call file_access.bound"
        # The helper is the only way to the row: the binder never selects the file table itself,
        # so it cannot look at a property of a file before the read question is answered.
        names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        assert "file_object" not in names, f"{member}: {binding.binder} reads file_object itself"


def test_dg_arc_08_the_replay_plan_is_refused_before_its_files_are_used() -> None:
    """``POST /migrations/{id}/import`` refuses a REPLAY body by name before anything else of it
    is read; the day mode (b) is built its ``file_id`` binds through the helper (this test and
    the registry row change together)."""
    from erev_api.domain.migration import commands

    source = inspect.getsource(commands.import_batch)
    refusal = source.index("if isinstance(body, ReplayImportIn):")
    assert "raise _refuse(REPLAY_NOT_BUILT_COPY" in source[refusal : refusal + 120]
    assert ".plan" not in source and "file_id" not in source


def test_dg_arc_08_only_the_file_routes_name_a_file_in_their_path() -> None:
    document = create_app().openapi()
    found = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", [])
        if parameter.get("in") in {"path", "query"} and FILE_MEMBER.fullmatch(parameter["name"])
    }
    assert found == FILE_PATHS


def documented_rows() -> list[tuple[str, str, str]]:
    """The rows of the table under the Binding heading in 04, cells stripped of code marks."""
    lines = DATA_MODEL.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(BINDING_HEADING))
    top = next(index for index in range(start, start + 6) if lines[index].strip() == BINDING_HEADER)
    rows: list[tuple[str, str, str]] = []
    for line in lines[top + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 3, line
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def test_dg_arc_08_the_04_binding_table_equals_the_registry() -> None:
    assert documented_rows() == file_access.binding_rows()
