"""Dev-guide DG-KRN-FILE-10 (rev 1.257); 05 §10 SBX-03 and §6.2 SAR-07 rev 1.196; item
SBX-FILE-READ-1: the associated data of a stored file is built in four places, from one rule.

The content of a stored file and its wrapped key are sealed with the workspace of the STORAGE
KEY in their associated data. A sandbox copy's rows carry their source's keys, so a reader that
names the row's own workspace opens no copied file (measured before the rule: every download of
one answered 500 and the verifier said ``undecryptable``), and a reader that named the key's
workspace without asking whose it is would open another workspace's object. Both mistakes are a
matter of who calls what, so they are closed here:

- ``files.store.encryption_context`` is called by ``put_file`` (the caller's own key), by
  ``open_file``, by the verifier's ``check_file`` and by ``lifecycle.rewrap_sidecar``, and by
  nothing else in the application;
- the two readers of a ROW pass it what ``files.store.content_tenant`` answered — the row's own
  workspace or the source of its sandbox — and never the row's ``tenant_id`` itself;
- the rewrap has no parameter for a workspace: it reads it from the key.

A new reader of a stored file's content is added here with its rule.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import erev_api

ROOT: Final = Path(erev_api.__file__).parent
STORE: Final = "files/store.py"
LIFECYCLE: Final = "files/lifecycle.py"
RECOVERY: Final = "controls/recovery.py"
CONTEXT: Final = "encryption_context"
RULE: Final = "content_tenant"
# (module, function) -> the workspace it names, and why that is the right one
CALLERS: Final = {
    (STORE, "put_file"): "the caller's own: the key it writes is `storage_key(tenant_id, …)`",
    (STORE, "open_file"): "`_content_workspace`: the row's own workspace or its sandbox's source",
    (LIFECYCLE, "rewrap_sidecar"): "`key_tenant`: the workspace the key itself names",
    (RECOVERY, "check_file"): "`content_tenant` with the source the tenant directory names",
}


def _tree(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


def _called(node: ast.Call) -> str | None:
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


def _context_arguments(relative: str, name: str) -> list[str]:
    """The first argument of each ``encryption_context`` call in the function, as source."""
    return [
        ast.unparse(node.args[0])
        for node in ast.walk(_function(relative, name))
        if isinstance(node, ast.Call) and _called(node) == CONTEXT
    ]


def test_dg_krn_file_10_the_associated_data_of_a_stored_file_is_built_in_four_places() -> None:
    assert _callers(CONTEXT) == set(CALLERS)
    assert all(CALLERS.values())


def test_dg_krn_file_10_a_reader_of_a_row_names_what_the_one_rule_answered() -> None:
    # The two readers of a row: the workspace is the rule's answer, bound to one name.
    assert _context_arguments(STORE, "open_file") == ["stored_by"]
    assert _context_arguments(RECOVERY, "check_file") == ["stored_by"]
    assert _callers(RULE) == {(STORE, "_content_workspace"), (RECOVERY, "check_file")}
    assert _callers("_content_workspace") == {(STORE, "open_file")}
    # The rewrap reads the workspace from the key and has no parameter to be handed another.
    rewrap = _function(LIFECYCLE, "rewrap_sidecar")
    parameters = {argument.arg for argument in (*rewrap.args.args, *rewrap.args.kwonlyargs)}
    assert "tenant_id" not in parameters, sorted(parameters)
    assert _context_arguments(LIFECYCLE, "rewrap_sidecar") == ["stored_by"]
    assert (LIFECYCLE, "rewrap_sidecar") in _callers("key_tenant")
    # The writer names its own workspace: the key it writes is its own by construction.
    assert _context_arguments(STORE, "put_file") == ["tenant_id"]
