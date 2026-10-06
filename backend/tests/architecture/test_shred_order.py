"""Dev-guide DG-KRN-FILE-09 (rev 1.225); 05 §6.17 PRV-07 b rev 1.171; item
FILE-SHRED-DURABLE-ORDER-1: the key of a stored file is destroyed only by the completion of a
shred that is already decided.

The destruction of a wrapped key is irreversible, so the record of it is made durable first: the
transaction that decides a shred marks the row and writes the event and calls nothing of the
store, and ``privacy._complete`` destroys the key afterwards, in a transaction of its own, on one
of three roads. This is a rule about who calls whom, and it is closed here in both directions:

- ``lifecycle.shred_sidecar`` — the one function that deletes a wrapped key — has exactly one
  caller in the application, ``domain.platform.privacy._complete``;
- ``privacy._decide`` takes no file store and names neither the lifecycle module nor a store;
- ``_complete`` is called by ``complete_shred`` (the continuation and the sweep) and by
  ``shred_file`` (the command sent again), and by nothing else; ``complete_shred`` by the
  continuation and by the sweep SCH-16, and by nothing else.

A new road is added here with the code that takes it; a call of the store that moves back into
a deciding transaction fails this module before any database test runs.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import erev_api

ROOT: Final = Path(erev_api.__file__).parent
PRIVACY: Final = "domain/platform/privacy.py"
SWEEP: Final = "domain/platform/shred_completion.py"
LIFECYCLE: Final = "files/lifecycle.py"
DESTROY: Final = "shred_sidecar"


def _tree(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


def _called(node: ast.Call) -> str | None:
    """The name a call names: ``f(...)`` and ``module.f(...)`` both give ``f``."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _callers(name: str) -> set[tuple[str, str]]:
    """(module, enclosing top-level function) of every call of ``name`` in the application."""
    found: set[tuple[str, str]] = set()
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        for top in _tree(relative).body:
            enclosing = top.name if isinstance(top, ast.FunctionDef | ast.ClassDef) else "<module>"
            for node in ast.walk(top):
                if isinstance(node, ast.Call) and _called(node) == name:
                    found.add((relative, enclosing))
    return found


def _function(relative: str, name: str) -> ast.FunctionDef:
    for node in _tree(relative).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{relative}: no function {name}")


def test_dg_krn_file_09_only_the_completion_destroys_a_wrapped_key() -> None:
    assert _function(LIFECYCLE, DESTROY).name == DESTROY
    assert _callers(DESTROY) == {(PRIVACY, "_complete")}


def test_dg_krn_file_09_the_decision_touches_nothing_of_the_store() -> None:
    decide = _function(PRIVACY, "_decide")
    parameters = {argument.arg for argument in (*decide.args.args, *decide.args.kwonlyargs)}
    assert "files" not in parameters, "the decision takes no file store"
    names = {node.id for node in ast.walk(decide) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(decide) if isinstance(node, ast.Attribute)}
    assert not {"lifecycle", "files", "_versioned"} & names, sorted(names)
    assert not {"files", DESTROY} & attributes, sorted(attributes)
    # The approved shred is the decision alone: it takes no file store either, and calls the
    # decision and never the completion or its store step.
    approved = _function(PRIVACY, "shred_approved")
    assert "files" not in {
        argument.arg for argument in (*approved.args.args, *approved.args.kwonlyargs)
    }
    calls = {_called(node) for node in ast.walk(approved) if isinstance(node, ast.Call)}
    assert "_decide" in calls and not {"_complete", "complete_shred", DESTROY} & calls, calls


def test_dg_krn_file_09_three_roads_one_function() -> None:
    assert _callers("_complete") == {(PRIVACY, "complete_shred"), (PRIVACY, "shred_file")}
    assert _callers("complete_shred") == {(PRIVACY, "continuation"), (SWEEP, "run")}
    # The continuation is registered by the two commands that decide, on the unit of work that
    # commits: the direct command, and the hook of the approved request.
    assert _callers("continuation") == {
        (PRIVACY, "shred_file"),
        ("domain/platform/evidence_shred.py", "_approved"),
    }
    assert _callers("_decide") == {(PRIVACY, "shred_file"), (PRIVACY, "shred_approved")}
