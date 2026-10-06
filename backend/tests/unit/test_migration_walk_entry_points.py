"""FLMG-WALK-RESET-1 (integrated batch #9 on main 8b304854; DG-MIG-05, DG-MIG-06): both migration
walks descend from a DATA-FREE head — their first statement calls ``support.db.fresh_head``, which
resets the schema and upgrades to head before any ``downgrade``. A CPU pin over the test sources:
a walk that meets rows earlier tests committed (a new enum label in ``approval_request``, batch #9)
fails at the enum-removing downgrade and every later pg test cascades on the part-migrated schema.

The same holds for every other test of ``tests/pg`` that downgrades, however far: a descent from
head passes the downgrade of every later revision first. Since revision 0092 the MFA enrolment of
any earlier test leaves a ``security_event`` of a kind that revision added, and two such tests —
the 0067 guard and the 0070 body test — stopped there on the whole-suite run of main 91056811.
``test_every_downgrade_under_tests_pg_starts_from_a_fresh_head`` holds them all to the rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from support.architecture import ROOT

WALKS = (
    ("backend/tests/pg/test_migrations.py", "test_upgrade_downgrade_upgrade"),
    ("backend/tests/pg/test_registry_parameter.py", "_downgrade_to_base_or_skip"),
)


def _function(path: Path, name: str) -> ast.FunctionDef:
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{path}: no function {name}")


def _first_statement(function: ast.FunctionDef) -> ast.stmt:
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # the docstring
    assert body, f"{function.name}: empty body"
    return body[0]


def _called_name(statement: ast.stmt) -> str | None:
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        func = statement.value.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


@pytest.mark.parametrize(("relative", "name"), WALKS, ids=[name for _, name in WALKS])
def test_walk_entry_point_resets_to_a_fresh_head_first(relative: str, name: str) -> None:
    function = _function(ROOT / relative, name)
    assert _called_name(_first_statement(function)) == "fresh_head", (
        f"{relative}::{name} must call fresh_head() before any downgrade (FLMG-WALK-RESET-1)"
    )


def _calls(function: ast.AST, name: str) -> list[int]:
    """The lines of the function's calls of ``name`` or ``<something>.name``."""
    lines = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if called == name:
                lines.append(node.lineno)
    return sorted(lines)


def test_every_downgrade_under_tests_pg_starts_from_a_fresh_head() -> None:
    """A function of ``backend/tests/pg`` that runs a downgrade resets first: before its first
    ``downgrade`` it calls ``fresh_head()``, or a function of its module that does (DG-MIG-06: a
    row of a later revision's enum label makes that revision's downgrade refuse, whatever
    revision the test is about)."""
    walks: list[str] = []
    late: list[str] = []
    for path in sorted((ROOT / "backend/tests/pg").glob("test_*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"))
        functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
        # The functions that reset before they downgrade, found to a fixed point: a function may
        # reach its reset through another function of the module.
        resetting = {"fresh_head"}
        while True:
            found = {
                function.name
                for function in functions
                if _resets_first(function, resetting) and _calls(function, "downgrade")
            }
            if found <= resetting:
                break
            resetting |= found
        for function in functions:
            if not _calls(function, "downgrade"):
                continue
            walks.append(f"{path.name}::{function.name}")
            if not _resets_first(function, resetting):
                late.append(f"{path.name}::{function.name}")
    assert late == [], f"no reset before the first downgrade: {late}"
    # The walks this rule holds today; a new one joins the list and takes the rule with it.
    assert walks == [
        "test_migration_0067_downgrade_guard.py::"
        "test_0067_downgrade_refuses_by_name_over_a_populated_database_and_downgrades_compatible_data",
        "test_migration_0084_lock_cutoff.py::"
        "test_0084_applies_over_earlier_lock_rows_and_validates_its_check_without_them",
        "test_migration_0111_gate_check.py::"
        "test_0111_downgrade_keeps_a_tenants_gate_row_and_validates_its_check_without_one",
        "test_migration_0119_not_stated_downgrade.py::"
        "test_0119_downgrade_is_refused_by_name_over_a_not_stated_item_and_goes_through_without_one",
        "test_migration_0124_subject_key.py::"
        "test_0124_applies_to_an_empty_ledger_and_refuses_one_that_holds_a_line",
        "test_migration_0128_dirty_trigger.py::"
        "test_0128_a_trigger_is_carried_by_a_mark_only_and_the_descent_keeps_the_mark",
        "test_migration_0129.py::"
        "test_0129_adds_the_cutoff_over_stored_computations_and_its_descent_keeps_them",
        "test_migrations.py::test_upgrade_downgrade_upgrade",
        "test_registry_parameter.py::_downgrade_to_base_or_skip",
        "test_registry_parameter.py::test_old_seed_forward_upgrade_appends_a_correction",
        "test_transition_pair_guard.py::"
        "test_activation_pair_1_downgrade_to_0069_restores_the_previous_body_byte_exactly",
    ], walks


def _resets_first(function: ast.FunctionDef, resetting: set[str]) -> bool:
    """Whether the function calls one of ``resetting`` before its first ``downgrade``."""
    downgrades = _calls(function, "downgrade")
    resets = sorted(line for name in resetting for line in _calls(function, name))
    return bool(resets) and (not downgrades or resets[0] < downgrades[0])


def test_fresh_head_resets_the_schema_then_upgrades_to_head() -> None:
    function = _function(ROOT / "backend/tests/support/db.py", "fresh_head")
    calls = [_called_name(statement) for statement in function.body]
    calls = [call for call in calls if call is not None]
    assert calls == ["reset_schema", "upgrade"], calls
    upgrade = function.body[-1]
    assert isinstance(upgrade, ast.Expr) and isinstance(upgrade.value, ast.Call)
    target = upgrade.value.args[-1]
    assert isinstance(target, ast.Constant) and target.value == "head"
