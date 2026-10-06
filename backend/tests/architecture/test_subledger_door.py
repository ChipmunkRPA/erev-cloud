"""The one door to the detail subledger and what every product caller says at it (04 T-SL-04
``subject_key`` rev 1.282; 05 RCP-05 rev 1.202; supervisor ruling R-11 as amended on 2026-10-02;
item ENG-COST-READBACK-1).

A ledger line stores the subject of the entry it belongs to, and the read-back of posted amounts
answers that key. A product line without one would be read back under a subject it was not posted
under — the defect of the item: every later computation took such lines back and posted them
again. The column is nullable for the lines of test builders, so the table does not hold the rule;
the door does, for the callers that say so:

- every call of ``journals.subledger.post`` inside ``erev_api`` passes
  ``require_subject_key=True``, and the callers are the three named here — a fourth writer states
  its subject or does not arrive;
- nothing inside ``erev_api`` inserts into ``subledger_line`` but ``journals/subledger.py``.
"""

from __future__ import annotations

import ast

from support.architecture import iter_files, read

DOOR = "backend/erev_api/domain/journals/subledger.py"
# The product writers of T-SL-04 lines, with the number of postings each makes.
WRITERS = {
    # a computation's posting of a book (DG-CMD-10); its lines come from ``book_lines``
    "backend/erev_api/domain/contracts/computation.py": 1,
    # the period-end passes of a close run; their lines come from ``computation.book_lines`` too
    "backend/erev_api/domain/close/period_end.py": 1,
    # the posting of an approved manual journal or reclassification
    "backend/erev_api/domain/journals/adjustments.py": 1,
}


def _is_post(node: ast.AST) -> bool:
    """``subledger.post(...)``: the door is always reached through its module."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subledger"
    )


def _inserts_lines(node: ast.AST) -> bool:
    """``insert(subledger_line)`` or ``subledger_line.insert()``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "insert":
        return any(isinstance(arg, ast.Name) and arg.id == "subledger_line" for arg in node.args)
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "insert"
        and isinstance(func.value, ast.Name)
        and func.value.id == "subledger_line"
    )


def postings() -> dict[str, list[bool]]:
    """Every call of the door in the product, per file: whether it requires the subject key."""
    found: dict[str, list[bool]] = {}
    for path in iter_files("backend/erev_api", suffixes=frozenset({".py"})):
        for node in ast.walk(ast.parse(read(path))):
            if not _is_post(node):
                continue
            assert isinstance(node, ast.Call)
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            flag = keywords.get("require_subject_key")
            found.setdefault(path, []).append(isinstance(flag, ast.Constant) and flag.value is True)
    return found


def test_every_product_posting_requires_the_subject_key() -> None:
    found = postings()
    assert {path: len(flags) for path, flags in found.items()} == WRITERS
    assert all(all(flags) for flags in found.values()), found


def test_nothing_inserts_a_ledger_line_but_the_door() -> None:
    writers = sorted(
        path
        for path in iter_files("backend/erev_api", suffixes=frozenset({".py"}))
        if "/db/migrations/" not in path
        and any(_inserts_lines(node) for node in ast.walk(ast.parse(read(path))))
    )
    assert writers == [DOOR]
