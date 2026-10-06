"""The proposal of a combination group has one writer and one discard (items
COMBINATION-PROPOSAL-RECORD-1 and COMBINATION-PROPOSAL-DISCARD-1; 04 T-CON-19 "The
`COMBINATION` topic").

``judgements.create_judgement`` refuses a ``COMBINATION`` record of a combination group unless its
caller passes ``proposal_of_group=True`` — the mark of the combination command that writes its
group's proposal. ``judgements.discard_judgement`` refuses to void such a record unless its
caller passes the same mark — the discard of the group itself. The mark is the whole of the
exception, so the tree is read for it: two calls pass it, inside
``combination._record_proposal`` and ``combination.discard_group``, and it is off unless
passed. Another caller would be a second writer, or a second way out, of a record the group's
commands and its approval read as THE proposal
(``tests/domain/contracts/test_combination_proposal_record.py`` and
``test_combination_proposal_discard.py`` hold the behaviour).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import erev_api
from erev_api.domain.policies import judgements

PACKAGE = Path(erev_api.__file__).parent
MARK = "proposal_of_group"


def _callers() -> list[tuple[str, str, str]]:
    """(module, enclosing function, called name) of every call that passes the mark."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for scope in ast.walk(tree):
            if not isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(scope):
                if isinstance(node, ast.Call) and any(k.arg == MARK for k in node.keywords):
                    found.append(
                        (path.relative_to(PACKAGE).as_posix(), scope.name, ast.unparse(node.func))
                    )
    return found


def test_the_mark_is_off_unless_the_command_passes_it() -> None:
    for command in (judgements.create_judgement, judgements.discard_judgement):
        parameter = inspect.signature(command).parameters[MARK]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is False


def test_one_caller_writes_the_proposal_of_a_group_and_one_discards_it() -> None:
    assert sorted(_callers()) == [
        ("domain/contracts/combination.py", "_record_proposal", "judgements.create_judgement"),
        ("domain/contracts/combination.py", "discard_group", "judgements.discard_judgement"),
    ]
