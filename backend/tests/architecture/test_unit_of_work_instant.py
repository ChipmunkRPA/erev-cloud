"""04 §14.1 "A computation behind its group" (rev 1.298; item COMPUTE-BEHIND-GROUP-1; the
supervisor's ruling of 2026-10-02), source guard for the rule's stated limit.

The rule compares stored instants: a bundle's cutoff — the later of its unit of work's instant and
its transaction's timestamp (``bundles.record_cutoff``) — with the ``created_at`` of the group's
head computation, which is the instant of the unit of work that made it. That comparison tells
two computations apart as long as a unit of work takes its instant INSIDE a transaction that has
already begun: the head's instant is then not earlier than its transaction's start, so the head
read nothing its ``created_at`` does not cover. A unit of work that took its instant first and
began its transaction later — that stood idle in between — would read later facts under an
earlier stamp, and a computation begun in that gap would not be refused.

So this test fails on the day somebody builds such a unit of work:

1. ``db.session._context_session`` issues the context statement (``setup(connection)``) BEFORE it
   yields the session: a tenant session is in its transaction when its caller receives it.
2. ``UnitOfWork.__init__`` takes ``now`` from the clock when it is constructed.
3. Every unit of work constructed in ``erev_api`` — ``UnitOfWork(...)``, or ``type(<unit>)(...)``
   — is constructed over a session whose transaction has begun: the session of another unit of
   work (``<unit>.session``, or a name the same function assigned it to), or the name a ``with
   tenant_session(...) as <name>`` of the same function binds.
4. A unit of work that serves another — constructed over that unit's session, or with its clock:
   the SYSTEM principal in the caller's transaction — is given that unit's instant (``<new>.now =
   <unit>.now``), and no unit of work is given any other instant. One transaction has one
   instant: a second unit that kept the later instant of its own construction would stamp a
   mark, or a head computation, later than the cutoff of the command it serves, and under a
   clock that moves the command's next computation would be refused as behind its own writes.
   (The frozen clock of the tests cannot show that: every instant it gives is the same.)

What no source guard can hold is the other way to the same gap: an application clock that runs
behind the database's (04 §14.1 states it with the limit).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import erev_api

ROOT = Path(erev_api.__file__).parent
SESSION_MODULE = "db/session.py"
UOW_MODULE = "uow.py"
# The context managers that hand out a session with its context statement issued.
BEGUN_SESSIONS = frozenset({"tenant_session"})
type Function = ast.FunctionDef | ast.AsyncFunctionDef


def _tree(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    (found,) = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    return found


def _functions() -> Iterator[tuple[str, Function]]:
    """Every function of ``erev_api`` with its module's path; a nested one is met on its own and
    inside each function that encloses it."""
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                yield relative, node


def _constructions(function: Function) -> Iterator[tuple[int, dict[str | None, ast.expr]]]:
    """The units of work ``function`` constructs: ``UnitOfWork(...)`` and ``type(<unit>)(...)``,
    each as its line and its keyword arguments."""
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        made = node.func
        by_name = isinstance(made, ast.Name) and made.id == "UnitOfWork"
        by_type = (
            isinstance(made, ast.Call)
            and isinstance(made.func, ast.Name)
            and made.func.id == "type"
            and any(keyword.arg == "session" for keyword in node.keywords)
        )
        if by_name or by_type:
            yield node.lineno, {keyword.arg: keyword.value for keyword in node.keywords}


def test_a_tenant_session_is_in_its_transaction_when_it_is_yielded() -> None:
    function = _function(_tree(SESSION_MODULE), "_context_session")
    setups = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setup"
    ]
    yields = [node.lineno for node in ast.walk(function) if isinstance(node, ast.Yield)]
    assert len(setups) == 1 and len(yields) == 1, (setups, yields)
    assert setups[0] < yields[0], "the context statement is issued before the session is yielded"


def test_a_unit_of_work_takes_its_instant_when_it_is_constructed() -> None:
    (unit,) = [
        node
        for node in ast.walk(_tree(UOW_MODULE))
        if isinstance(node, ast.ClassDef) and node.name == "UnitOfWork"
    ]
    init = _function(unit, "__init__")
    taken = [
        ast.unparse(node)
        for node in ast.walk(init)
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "self.now"
    ]
    assert taken == ["self.now = clock.now()"], taken


def _begun_names(function: ast.AST) -> set[str]:
    """The names of ``function`` that hold a session in its transaction: what a ``with <begun
    session>(...) as <name>`` binds, and a name assigned the session of a unit of work
    (``<name> = <unit>.session``)."""
    names: set[str] = set()
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "session"
        ):
            names.add(node.targets[0].id)
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            call = item.context_expr
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in BEGUN_SESSIONS
                and isinstance(item.optional_vars, ast.Name)
            ):
                names.add(item.optional_vars.id)
    return names


def test_every_unit_of_work_is_constructed_over_a_transaction_that_has_begun() -> None:
    accepted: dict[tuple[str, int], bool] = {}
    for relative, function in _functions():
        begun = _begun_names(function)
        # a construction inside a nested function is met once per enclosing function: it is
        # accepted when ANY of them opened the session it is given
        for line, given in _constructions(function):
            session = given.get("session")
            derived = isinstance(session, ast.Attribute) and session.attr == "session"
            opened = isinstance(session, ast.Name) and session.id in begun
            site = (relative, line)
            accepted[site] = accepted.get(site, False) or derived or opened
    refused = sorted(f"{relative}:{line}" for (relative, line), ok in accepted.items() if not ok)
    assert refused == [], refused
    # the walk found its subject: the construction of the kernel, and the derived ones
    assert any(relative == UOW_MODULE for relative, _ in accepted), sorted(accepted)
    assert len(accepted) > 1, sorted(accepted)


def _instants_given(function: ast.AST) -> list[ast.Assign]:
    """The assignments of ``function`` that give a unit of work an instant: ``<x>.now = ...``."""
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr == "now"
    ]


def test_a_unit_of_work_that_serves_another_keeps_its_instant() -> None:
    kept: dict[tuple[str, int], bool] = {}
    other: set[str] = set()
    for relative, function in _functions():
        given_instants = _instants_given(function)
        handed = any(
            isinstance(node.value, ast.Attribute) and node.value.attr == "now"
            for node in given_instants
        )
        # an instant that is not another unit's: only the kernel's own, in ``__init__``
        other |= {
            f"{relative}:{node.lineno} {ast.unparse(node)}"
            for node in given_instants
            if not (isinstance(node.value, ast.Attribute) and node.value.attr == "now")
            and not (relative == UOW_MODULE and ast.unparse(node) == "self.now = clock.now()")
        }
        for line, given in _constructions(function):
            session, clock = given.get("session"), given.get("clock")
            serves = (isinstance(session, ast.Attribute) and session.attr == "session") or (
                isinstance(clock, ast.Attribute) and clock.attr == "clock"
            )
            if serves:
                site = (relative, line)
                kept[site] = kept.get(site, False) or handed
    refused = sorted(f"{relative}:{line}" for (relative, line), ok in kept.items() if not ok)
    assert refused == [], refused
    assert sorted(other) == [], sorted(other)
    assert len(kept) > 1, sorted(kept)
