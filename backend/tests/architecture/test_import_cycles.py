"""DG-ARC-17: no module-level import of the application depends on which module is imported first
(ARCH-IMPORT-CYCLE-1; dev-guide rev 1.174).

Inside an import cycle a module can meet another one that is still initialising: it is in
``sys.modules`` and has not yet run the statement that binds the name asked for. ``from M import
name`` then raises ``ImportError`` and a module-level read ``M.name`` raises ``AttributeError`` -
for the processes that enter the cycle on M's side, and for no other. The api, the worker, the CLI
and each test module import in an order of their own, so the failure shows in one of them and not
in the rest: ``reference/period_redirty_job.py`` read a name of ``platform.jobs`` and failed for
ten of 615 first imports until the import became a module import.

A component rule - no name import between two modules of one cycle - cannot tell that case from
the cycles that are safe in every order. The table modules read ``metadata`` from their package's
``__init__``, which always runs first and binds it before it imports them; ``imports.csv_v2`` and
``imports.legacy_v1`` load each other's package and read names of leaf modules only. So the rule
is what the interpreter does, replayed from the source: for EVERY module as the first import, the
ancestors' ``__init__`` first, then the module-level statements in order, each import followed at
the place it stands, a module's names bound as its statements run. Both branches of a module-level
``if`` and every handler of a ``try`` are followed, in the order they are written. Nothing scanned
is imported or executed.

Left out by construction: ``TYPE_CHECKING`` blocks and the bodies of functions and lambdas, which
do not run at import - and therefore whatever a function does when it is *called* during an
import (a decorator or a registry that imports, ``importlib.import_module`` with a computed name).
``tests/unit/test_worker.py`` imports each module of ``worker.HANDLER_MODULES`` first in a process
of its own for that reason. ``test_the_replay_is_what_the_interpreter_does`` holds the replay to
the interpreter on small packages.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import pytest
from support.architecture import Finding, iter_files, module_name, read, report

RULE: Final = "DG-ARC-17"
PY: Final = frozenset({".py"})
SCOPE: Final = ("backend/erev_api", "backend/erev_engine")
# How many first imports a finding names before it counts the rest.
NAMED_FIRST_IMPORTS: Final = 3

Chain = tuple[str, tuple[str, ...], int]  # a bare name, the attributes read from it, the line


@dataclass(frozen=True, slots=True)
class Binds:
    """A statement that binds module-level names once it has run."""

    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Reads:
    """The attribute chains a statement evaluates when it runs."""

    chains: tuple[Chain, ...]


@dataclass(frozen=True, slots=True)
class WholeImport:
    """``import a.b.c`` binds ``a``; ``import a.b.c as x`` binds ``x`` to ``a.b.c``."""

    module: str
    binds: str
    bound_module: str
    line: int


@dataclass(frozen=True, slots=True)
class NameImport:
    """``from base import name [as bound], ...`` with ``base`` made absolute."""

    base: str
    names: tuple[tuple[str, str], ...]
    line: int


Step = Binds | Reads | WholeImport | NameImport


@dataclass(frozen=True, slots=True, order=True)
class Failure:
    """What one first import cannot do. ``kind`` is ``import`` (a name asked of a module that is
    still initialising), ``read`` (the same by ``M.name`` at module level), ``star`` or
    ``unplaced`` (a name the replay cannot place: no module-level statement binds it)."""

    module: str
    line: int
    kind: str
    source: str
    name: str


@dataclass(slots=True)
class _Frame:
    """A module of one replay: the names bound so far, and which of them are modules."""

    bound: set[str] = field(default_factory=set)
    modules: dict[str, str] = field(default_factory=dict)
    done: bool = False


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _targets(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Tuple | ast.List):
        return [name for item in node.elts for name in _targets(item)]
    if isinstance(node, ast.Starred):
        return _targets(node.value)
    return []


class _ImportTimeReads(ast.NodeVisitor):
    """The attribute chains rooted at a bare name that are evaluated when a statement runs: not
    the body of a function or a lambda, and no annotation under ``from __future__ import
    annotations``. A decorator, a default value, a base class and a class body are evaluated."""

    def __init__(self, *, lazy_annotations: bool) -> None:
        self.lazy = lazy_annotations
        self.found: list[Chain] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attrs: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            attrs.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            self.visit(current)
            return
        attrs.reverse()
        if not isinstance(node.ctx, ast.Load):
            attrs.pop()  # ``module.name = value`` reads the module, not the name
        if attrs:
            self.found.append((current.id, tuple(attrs), node.lineno))

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._defaults(node.args)
        if not self.lazy:
            every = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            for arg in [*every, node.args.vararg, node.args.kwarg]:
                if arg is not None and arg.annotation is not None:
                    self.visit(arg.annotation)
            if node.returns is not None:
                self.visit(node.returns)

    def _defaults(self, arguments: ast.arguments) -> None:
        for default in [*arguments.defaults, *arguments.kw_defaults]:
            if default is not None:
                self.visit(default)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._defaults(node.args)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self.lazy:
            self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)

    def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
        return  # the value of ``type X = ...`` is evaluated when it is first asked for


def steps(module: str, source: str, *, is_package: bool) -> tuple[Step, ...]:
    """What importing ``module`` does at module level, in the order it does it."""
    tree = ast.parse(source)
    lazy = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )
    out: list[Step] = []

    def absolute(node: ast.ImportFrom) -> str:
        if not node.level:
            return node.module or ""
        package = module.split(".") if is_package else module.split(".")[:-1]
        package = package[: len(package) - (node.level - 1)]
        return ".".join([*package, *([node.module] if node.module else [])])

    def imported(node: ast.Import | ast.ImportFrom, *, binds: bool) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                out.append(
                    WholeImport(
                        alias.name,
                        (alias.asname or top) if binds else "",
                        alias.name if alias.asname else top,
                        node.lineno,
                    )
                )
            return
        names = tuple(
            (alias.name, (alias.asname or alias.name) if binds else "") for alias in node.names
        )
        out.append(NameImport(absolute(node), names, node.lineno))

    def reads(*nodes: ast.AST | None) -> None:
        visitor = _ImportTimeReads(lazy_annotations=lazy)
        for node in nodes:
            if node is not None:
                visitor.visit(node)
        if visitor.found:
            out.append(Reads(tuple(visitor.found)))

    def class_body(node: ast.ClassDef) -> None:
        reads(*node.decorator_list, *node.bases, *(keyword.value for keyword in node.keywords))
        for inner in node.body:  # runs at import; what it binds, it binds in the class
            if isinstance(inner, ast.Import | ast.ImportFrom):
                imported(inner, binds=False)
            elif isinstance(inner, ast.ClassDef):
                class_body(inner)
            else:
                reads(inner)

    def walk(body: Sequence[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.Import | ast.ImportFrom):
                imported(node, binds=True)
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                reads(node)
                out.append(Binds((node.name,)))
            elif isinstance(node, ast.ClassDef):
                class_body(node)
                out.append(Binds((node.name,)))
            elif isinstance(node, ast.Assign):
                reads(node)
                out.append(Binds(tuple(n for target in node.targets for n in _targets(target))))
            elif isinstance(node, ast.AnnAssign):
                reads(node)
                if node.value is not None:
                    out.append(Binds(tuple(_targets(node.target))))
            elif isinstance(node, ast.AugAssign):
                reads(node)
                out.append(Binds(tuple(_targets(node.target))))
            elif isinstance(node, ast.TypeAlias):
                out.append(Binds((node.name.id,)))
            elif isinstance(node, ast.If):
                if _is_type_checking(node.test):
                    walk(node.orelse)
                    continue
                reads(node.test)
                walk(node.body)
                walk(node.orelse)
            elif isinstance(node, ast.Try):
                walk(node.body)
                for handler in node.handlers:
                    reads(handler.type)
                    if handler.name:
                        out.append(Binds((handler.name,)))
                    walk(handler.body)
                walk(node.orelse)
                walk(node.finalbody)
            elif isinstance(node, ast.With | ast.AsyncWith):
                for item in node.items:
                    reads(item.context_expr)
                    if item.optional_vars is not None:
                        out.append(Binds(tuple(_targets(item.optional_vars))))
                walk(node.body)
            elif isinstance(node, ast.For | ast.AsyncFor):
                reads(node.iter)
                out.append(Binds(tuple(_targets(node.target))))
                walk(node.body)
                walk(node.orelse)
            elif isinstance(node, ast.While):
                reads(node.test)
                walk(node.body)
                walk(node.orelse)
            else:
                reads(node)

    walk(tree.body)
    return tuple(out)


def replay(programme: Mapping[str, tuple[Step, ...]], first: str) -> list[Failure]:
    """Import ``first`` into an interpreter that has imported nothing of ``programme``, as CPython
    does it, and return what could not be done. A failed step is recorded and passed over, so one
    replay names every failure of that first import."""
    frames: dict[str, _Frame] = {}
    failures: list[Failure] = []

    def name_import(module: str, frame: _Frame, step: NameImport) -> None:
        load(step.base)
        source = frames.get(step.base)
        for name, bound_as in step.names:
            is_module: str | None = None
            if source is None:
                pass  # not a module of the programme: the standard library, a dependency
            elif name == "*":
                failures.append(Failure(module, step.line, "star", step.base, name))
            elif name in source.bound:
                is_module = source.modules.get(name)
            elif f"{step.base}.{name}" in programme:
                # A submodule: imported now if it is not yet, and found in ``sys.modules`` when
                # it is still initialising (CPython's fallback for a circular ``from`` import).
                is_module = f"{step.base}.{name}"
                load(is_module)
            else:
                kind = "unplaced" if source.done else "import"
                failures.append(Failure(module, step.line, kind, step.base, name))
            if bound_as and name != "*":
                bind(frame, bound_as, is_module)

    def read(module: str, frame: _Frame, chain: Chain) -> None:
        root, attrs, line = chain
        current = frame.modules.get(root)
        for attr in attrs:
            if current is None:
                return
            source = frames[current]
            if attr in source.bound:
                current = source.modules.get(attr)
            elif not source.done or f"{current}.{attr}" in programme:
                # The module has not bound the name yet, or the name is a submodule that is not
                # an attribute of its package until its own import has ended.
                failures.append(Failure(module, line, "read", current, attr))
                return
            else:
                return  # a name set some other way: no order of imports changes it

    def bind(frame: _Frame, name: str, is_module: str | None) -> None:
        frame.bound.add(name)
        if is_module is None:
            frame.modules.pop(name, None)
        else:
            frame.modules[name] = is_module

    def load(module: str) -> None:
        if module not in programme:
            return
        parent, _, leaf = module.rpartition(".")
        if parent:
            load(parent)  # a package's ``__init__`` runs before anything inside the package
        if module in frames:
            return  # imported already, or still initialising further up
        frame = frames[module] = _Frame()
        for step in programme[module]:
            if isinstance(step, Binds):
                frame.bound.update(step.names)
                if frame.modules:
                    for name in step.names:
                        frame.modules.pop(name, None)
            elif isinstance(step, Reads):
                for chain in step.chains:
                    read(module, frame, chain)
            elif isinstance(step, WholeImport):
                load(step.module)
                if step.binds and step.bound_module in frames:
                    bind(frame, step.binds, step.bound_module)
                elif step.binds:
                    bind(frame, step.binds, None)
            else:
                name_import(module, frame, step)
        frame.done = True
        if parent in frames:  # only now is the module an attribute of its package
            bind(frames[parent], leaf, module)

    load(first)
    return failures


def programme_of(sources: Mapping[str, str]) -> dict[str, tuple[Step, ...]]:
    """``sources`` maps repository-relative paths to source text."""
    return {
        module_name(path): steps(module_name(path), source, is_package=path.endswith("__init__.py"))
        for path, source in sources.items()
    }


def failing_first_imports(sources: Mapping[str, str]) -> dict[Failure, list[str]]:
    """Every failure of every first import, with the first imports it happens for."""
    programme = programme_of(sources)
    found: dict[Failure, list[str]] = {}
    for first in sorted(programme):
        for failure in replay(programme, first):
            found.setdefault(failure, []).append(first)
    return found


def _message(failure: Failure, firsts: Sequence[str]) -> str:
    named = ", ".join(f"`{first}`" for first in firsts[:NAMED_FIRST_IMPORTS])
    more = len(firsts) - NAMED_FIRST_IMPORTS
    when = f"when {named}{f' or one of {more} more' if more > 0 else ''} is imported first"
    remedy = (
        "import the module whole and read the name when it is called, or move the name out of "
        "the cycle"
    )
    if failure.kind == "import":
        return (
            f"`from {failure.source} import {failure.name}` meets `{failure.source}` still "
            f"initialising, without `{failure.name}`, {when}: {remedy}"
        )
    if failure.kind == "read":
        return (
            f"`{failure.source}.{failure.name}` is read at module level before `{failure.source}` "
            f"has it, {when}: read it when it is called, or import what is read"
        )
    if failure.kind == "star":
        return (
            f"`from {failure.source} import *`: the replay cannot place the names of a star import"
        )
    return (
        f"`from {failure.source} import {failure.name}`: no module-level statement of "
        f"`{failure.source}` binds `{failure.name}`, so the replay cannot place it"
    )


def check_import_order(sources: Mapping[str, str]) -> list[Finding]:
    paths = {module_name(path): path for path in sources}
    return sorted(
        Finding(paths[failure.module], failure.line, RULE, _message(failure, firsts))
        for failure, firsts in failing_first_imports(sources).items()
    )


def test_dg_arc_17_no_import_depends_on_the_first_import() -> None:
    sources = {path: read(path) for path in iter_files(*SCOPE, suffixes=PY)}
    assert len(sources) > 600, len(sources)
    found = check_import_order(sources)
    assert found == [], report(found)


def _source(*lines: str) -> str:
    return "".join(f"{line}\n" for line in lines)


Expected = dict[tuple[str, int, str, str, str], list[str]]  # module, line, kind, source, name
# The four modules of the cycle that was repaired, in small: ``jobs`` reaches ``redirty`` again
# through ``queries`` and ``gates``.
_CYCLE: Final = {
    "pkg/__init__.py": "",
    "pkg/jobs.py": _source(
        "from pkg import queries", "", "", "def newest(job=None):", "    return job"
    ),
    "pkg/queries.py": _source("from pkg import gates"),
    "pkg/gates.py": _source("from pkg import redirty"),
}
# The table modules in small: every module reads ``metadata`` from its package.
_HUB: Final = {
    "tables/platform.py": _source("from tables import metadata", "", "users = (metadata, 'users')"),
    "tables/reference.py": _source(
        "from tables import metadata",
        "from tables.platform import users",
        "",
        "books = (metadata, users)",
    ),
}
_HUB_IMPORTS: Final = ("from tables.platform import users", "from tables.reference import books")
# ``imports.csv_v2`` and ``imports.legacy_v1`` in small: importing ``right.leaf`` runs
# ``right/__init__`` first, which reads the other package.
_TWO_PACKAGES: Final = {
    "left/__init__.py": _source("from right.leaf import NAME", "", "LEFT = NAME"),
    "left/leaf.py": _source("NAME = 'left'"),
    "right/leaf.py": _source("NAME = 'right'"),
}
CASES: Final[dict[str, tuple[dict[str, str], Expected]]] = {
    # The defect: a name of the module the cycle was entered at.
    "a name of the side that was entered": (
        {**_CYCLE, "pkg/redirty.py": _source("from pkg.jobs import newest", "", "JOB = newest")},
        {("pkg.redirty", 1, "import", "pkg.jobs", "newest"): ["pkg.jobs"]},
    ),
    # The repair: the module whole, the name read when the function is called.
    "the module whole, read when called": (
        {
            **_CYCLE,
            "pkg/redirty.py": _source(
                "from pkg import jobs", "", "", "def job():", "    return jobs.newest"
            ),
        },
        {},
    ),
    # The spelling the repair leaves possible.
    "the module whole, read at module level": (
        {**_CYCLE, "pkg/redirty.py": _source("from pkg import jobs", "", "JOB = jobs.newest")},
        {("pkg.redirty", 3, "read", "pkg.jobs", "newest"): ["pkg.jobs"]},
    ),
    "the module whole under another name, read by a decorator": (
        {
            **_CYCLE,
            "pkg/redirty.py": _source(
                "import pkg.jobs as platform_jobs",
                "",
                "",
                "@platform_jobs.newest",
                "def job():",
                "    return 1",
            ),
        },
        {("pkg.redirty", 4, "read", "pkg.jobs", "newest"): ["pkg.jobs"]},
    ),
    # A name bound before the cycle is entered is there in every order.
    "a name bound before the cycle is entered": (
        {
            **_CYCLE,
            "pkg/jobs.py": _source(
                "def newest(job=None):", "    return job", "", "", "from pkg import queries"
            ),
            "pkg/redirty.py": _source("from pkg.jobs import newest", "", "JOB = newest"),
        },
        {},
    ),
    # The table modules: the package binds what its modules read before it imports them, and a
    # package is always entered before anything inside it.
    "a package that binds before it imports its modules": (
        {**_HUB, "tables/__init__.py": _source("metadata = object()", *_HUB_IMPORTS)},
        {},
    ),
    "a package that imports its modules before it binds": (
        {**_HUB, "tables/__init__.py": _source(*_HUB_IMPORTS, "metadata = object()")},
        {
            (module, 1, "import", "tables", "metadata"): [
                "tables",
                "tables.platform",
                "tables.reference",
            ]
            for module in ("tables.platform", "tables.reference")
        },
    ),
    # ``from package import module`` finds a module that is still initialising.
    "a module of a package that is still initialising": (
        {
            "pkg/__init__.py": _source("from pkg import a"),
            "pkg/a.py": _source("from pkg import b", "", "A = 1"),
            "pkg/b.py": _source("from pkg import a", "", "B = 2"),
        },
        {},
    ),
    # ``package.module`` is no attribute of the package until the module's import has ended.
    "a module read through its package before its import has ended": (
        {
            "pkg/__init__.py": "",
            "pkg/a.py": _source("import pkg.b", "", "A = 1"),
            "pkg/b.py": _source("import pkg.a", "", "B = pkg.a.A"),
        },
        {("pkg.b", 3, "read", "pkg", "a"): ["pkg.a"]},
    ),
    # Two packages that load each other. Names of leaf modules are there in every order; a name
    # of the other package's ``__init__`` is not.
    "two packages that read each other's leaf modules": (
        {
            **_TWO_PACKAGES,
            "right/__init__.py": _source("from left.leaf import NAME", "", "RIGHT = NAME"),
        },
        {},
    ),
    "two packages, one reading the other's own name": (
        {
            **_TWO_PACKAGES,
            "right/__init__.py": _source("from left import LEFT", "", "RIGHT = LEFT"),
        },
        {("right", 1, "import", "left", "LEFT"): ["left", "left.leaf"]},
    ),
    # Not run at import: a TYPE_CHECKING block and a function body.
    "a cycle that only a TYPE_CHECKING block closes": (
        {
            "pkg/__init__.py": "",
            "pkg/a.py": _source(
                "from __future__ import annotations",
                "",
                "from typing import TYPE_CHECKING",
                "",
                "if TYPE_CHECKING:",
                "    from pkg.b import Thing",
                "",
                "VALUE = 1",
                "",
                "",
                "def thing(one: Thing) -> Thing:",
                "    return one",
            ),
            "pkg/b.py": _source(
                "from pkg.a import VALUE", "", "", "class Thing:", "    value = VALUE"
            ),
        },
        {},
    ),
    "a cycle that only a function body closes": (
        {
            "pkg/__init__.py": "",
            "pkg/a.py": _source(
                "def late():",
                "    from pkg.b import THING",
                "",
                "    return THING",
                "",
                "",
                "VALUE = 1",
            ),
            "pkg/b.py": _source("from pkg.a import VALUE", "", "THING = VALUE"),
        },
        {},
    ),
    # A relative import is the same import.
    "a relative name import of the side that was entered": (
        {
            "pkg/__init__.py": "",
            "pkg/a.py": _source("from . import b", "", "A = 1"),
            "pkg/b.py": _source("from .a import A", "", "B = A"),
        },
        {("pkg.b", 1, "import", "pkg.a", "A"): ["pkg.a"]},
    ),
}

# One first import in an interpreter of its own. The two errors a module that is still
# initialising causes end the process with a code of their own; any other error is the case's.
_IMPORT_ERROR: Final = 41
_ATTRIBUTE_ERROR: Final = 42
_FIRST_IMPORT: Final = f"""
import importlib, sys
sys.path.insert(0, sys.argv[1])
try:
    importlib.import_module(sys.argv[2])
except ImportError:
    sys.exit({_IMPORT_ERROR})
except AttributeError:
    sys.exit({_ATTRIBUTE_ERROR})
"""


def _interpreter_fails(root: Path, module: str) -> bool:
    done = subprocess.run(
        [sys.executable, "-S", "-E", "-c", _FIRST_IMPORT, str(root), module],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.returncode in {0, _IMPORT_ERROR, _ATTRIBUTE_ERROR}, (module, done.stderr[-400:])
    return done.returncode != 0


def _modules(files: Mapping[str, str]) -> Iterator[str]:
    for path in sorted(files):
        yield module_name(path)


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_replay_names_the_failing_first_imports(case: str) -> None:
    files, expected = CASES[case]
    found = {
        (failure.module, failure.line, failure.kind, failure.source, failure.name): firsts
        for failure, firsts in failing_first_imports(files).items()
    }
    assert found == expected


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_replay_is_what_the_interpreter_does(case: str, tmp_path: Path) -> None:
    """Each module of the case is imported first by a real interpreter, in a process of its own;
    the first imports that fail are the ones the replay names, and no other."""
    files, expected = CASES[case]
    for path, source in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    replayed = {first for firsts in expected.values() for first in firsts}
    failed = {module for module in _modules(files) if _interpreter_fails(tmp_path, module)}
    assert failed == replayed


def test_a_finding_names_the_import_and_the_first_imports() -> None:
    files, _ = CASES["a name of the side that was entered"]
    posed = {
        f"backend/erev_api/{path.removeprefix('pkg/')}": source.replace("pkg", "erev_api")
        for path, source in files.items()
    }
    findings = check_import_order(posed)
    assert [(finding.path, finding.line, finding.rule) for finding in findings] == [
        ("backend/erev_api/redirty.py", 1, RULE)
    ], report(findings)
    assert findings[0].message == (
        "`from erev_api.jobs import newest` meets `erev_api.jobs` still initialising, without "
        "`newest`, when `erev_api.jobs` is imported first: import the module whole and read the "
        "name when it is called, or move the name out of the cycle"
    )
    package = {"backend/erev_api/__init__.py": "", "backend/erev_api/a.py": "X = 1\n"}
    star = check_import_order({**package, "backend/erev_api/b.py": "from erev_api.a import *\n"})
    assert [(finding.line, "star import" in finding.message) for finding in star] == [(1, True)]
    absent = check_import_order({**package, "backend/erev_api/b.py": "from erev_api.a import Y\n"})
    assert [(finding.line, "cannot place it" in finding.message) for finding in absent] == [
        (1, True)
    ]
