"""DG-ARC-02: ``erev_engine`` stays pure (D-10; DG-ENG-01 to DG-ENG-03; BUILD_SPEC FND-13; D-79).

Imports come from the DG-ARC-02 allow-list. ``datetime`` and ``uuid`` export only the types the
canonical encoder and the bundle need (DG-KRN-CAN-08, DG-KRN-CAN-09; §7 ``known_at``). These are
findings too:

- float literals, ``float(`` and the builtin ``round(``;
- bare-name calls of ``open``, ``__import__``, ``eval``, ``exec``, ``compile``, ``globals``,
  ``vars``, ``breakpoint`` and ``input``;
- any reference to the name ``__builtins__``;
- an attribute ``now``, ``today``, ``utcnow``, ``fromtimestamp`` or ``utcfromtimestamp`` on any
  owner, which covers import aliases (D-78);
- ``getattr(<x>, <one of those attribute names>)``.

Attribute calls such as ``re.compile(`` are not findings.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import Final

import pytest
from support.architecture import Finding, Import, imports, iter_files, read, report

RULE: Final = "DG-ARC-02"
PY: Final = frozenset({".py"})
ALLOWED_MODULES: Final = frozenset(
    {
        "__future__",
        "abc",
        "bisect",
        "calendar",
        "collections",
        "contextlib",
        "copy",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "fractions",
        "functools",
        "hashlib",
        "heapq",
        "itertools",
        "json",
        "operator",
        "re",
        "string",
        "types",
        "typing",
        "unicodedata",
        "erev_engine",
    }
)
# Names importable from modules that also offer clock or randomness access.
RESTRICTED_NAMES: Final = {
    "datetime": frozenset({"UTC", "date", "datetime", "timedelta", "timezone"}),
    "uuid": frozenset({"UUID"}),
}
CLOCK_READS: Final = frozenset({"now", "today", "utcnow", "fromtimestamp", "utcfromtimestamp"})
FORBIDDEN_CALLS: Final = {
    "float": "float( call",
    "round": "builtin round(; rounding goes through erev_engine.money (ALG-01)",
    "open": "open( reads the filesystem (DG-ENG-01)",
    "__import__": "__import__( dynamic import",
    "eval": "eval( dynamic code",
    "exec": "exec( dynamic code",
    "compile": "builtin compile( dynamic code",
    "globals": "globals( namespace access",
    "vars": "vars( namespace access",
    "breakpoint": "breakpoint( debugger hook",
    "input": "input( reads standard input (DG-ENG-01)",
}


def _import_problem(item: Import) -> str | None:
    top = item.module.split(".")[0]
    if top in RESTRICTED_NAMES:
        allowed = RESTRICTED_NAMES[top]
        if item.module != top:
            return f"import of {item.module}"
        if not item.names:
            return None if top == "datetime" else f"import {top}; import only {sorted(allowed)}"
        extra = [name for name in item.names if name not in allowed]
        return f"from {top} import {', '.join(extra)}" if extra else None
    if top not in ALLOWED_MODULES:
        return f"import of {item.module} outside the DG-ARC-02 allow-list"
    return None


def _getattr_clock_read(node: ast.Call) -> str | None:
    if len(node.args) < 2:
        return None
    name = node.args[1]
    if isinstance(name, ast.Constant) and name.value in CLOCK_READS:
        return str(name.value)
    return None


def _construct_problems(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float | complex):
            yield node.lineno, f"float literal {node.value!r}"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                yield node.lineno, FORBIDDEN_CALLS[node.func.id]
            elif node.func.id == "getattr" and (read_name := _getattr_clock_read(node)):
                yield node.lineno, f"clock read getattr(…, {read_name!r})"
        elif isinstance(node, ast.Name) and node.id == "__builtins__":
            yield node.lineno, "__builtins__ reference"
        elif isinstance(node, ast.Attribute) and node.attr in CLOCK_READS:
            yield node.lineno, f"clock read .{node.attr}"


def check_purity(path: str, source: str) -> list[Finding]:
    tree = ast.parse(source, filename=path)
    findings = [
        Finding(path, item.line, RULE, problem)
        for item in imports(path, tree)
        if (problem := _import_problem(item)) is not None
    ]
    findings += [Finding(path, line, RULE, problem) for line, problem in _construct_problems(tree)]
    return sorted(findings)


def _repository_findings() -> list[Finding]:
    return [
        finding
        for path in iter_files("backend/erev_engine", suffixes=PY)
        for finding in check_purity(path, read(path))
    ]


def test_dg_arc_02_detects_forbidden_constructs() -> None:
    for snippet in (
        "x = 1.5\n",
        "float(y)\n",
        "round(z)\n",
        "import math\n",
        "from datetime import datetime; datetime.now()\n",
    ):
        findings = check_purity("backend/erev_engine/x.py", snippet)
        assert [(finding.line, finding.rule) for finding in findings] == [(1, RULE)], (
            snippet,
            report(findings),
        )

    repository = _repository_findings()
    assert repository == [], report(repository)


@pytest.mark.parametrize(
    "snippet",
    [
        "import statistics\n",
        "import time\n",
        "import os\n",
        "import random\n",
        "import uuid\n",
        "from uuid import uuid4\n",
        "from datetime import time\n",
        "from erev_api.money import MoneyStr\n",
        "date.today()\n",
        "import datetime\nstamp = datetime.datetime.utcnow\n",
        "x = 2j\n",
        "open('bundle.json')\n",
    ],
)
def test_rejected_engine_constructs(snippet: str) -> None:
    findings = check_purity("backend/erev_engine/stages/x.py", snippet)
    assert len(findings) == 1, report(findings)


def test_dg_arc_02_aliased_clock_reads() -> None:
    for snippet in (
        "from datetime import datetime as dt\nknown_at = dt.now()\n",
        "from datetime import date as D\nday = D.today()\n",
        "from datetime import datetime as DT\nstamp = DT.utcnow()\n",
        "import datetime as dt\nstamp = dt.datetime.now()\n",
    ):
        findings = check_purity("backend/erev_engine/stages/x.py", snippet)
        assert [(finding.line, finding.rule) for finding in findings] == [(2, RULE)], (
            snippet,
            report(findings),
        )
    constructed = "from datetime import date as D\nday = D(2026, 9, 12)\n"
    assert check_purity("backend/erev_engine/stages/x.py", constructed) == []

    repository = _repository_findings()
    assert repository == [], report(repository)


def test_dg_arc_02_builtins_and_owner_free_clock_reads() -> None:
    for snippet in (
        'x = eval("1")\n',
        'exec("x = 1")\n',
        'code = compile("1", "x", "eval")\n',
        'f = __builtins__["__import__"]\n',
        "stamp = as_of.today()\n",
        "stamp = datetime.min.now()\n",
        "clock = datetime\nstamp = clock.now()\n",
        'stamp = getattr(datetime, "now")()\n',
    ):
        findings = check_purity("backend/erev_engine/stages/x.py", snippet)
        assert [finding.rule for finding in findings] == [RULE], (snippet, report(findings))

    for clean in (
        'pattern = re.compile("x")\n',
        "from datetime import date as D\nday = D(2026, 9, 12)\n",
    ):
        assert check_purity("backend/erev_engine/stages/x.py", clean) == [], clean

    repository = _repository_findings()
    assert repository == [], report(repository)


def test_allowed_engine_constructs() -> None:
    snippet = (
        "from __future__ import annotations\n"
        "import hashlib\n"
        "import datetime as dt\n"
        "from collections.abc import Mapping\n"
        "from datetime import UTC, date, datetime, timedelta\n"
        "from decimal import ROUND_HALF_UP, Decimal\n"
        "from fractions import Fraction\n"
        "from uuid import UUID\n"
        "from erev_engine.canonical import sha256_hex\n"
        "from . import currencies\n"
        "half = Fraction(1, 2)\n"
        "known_at = datetime(2026, 9, 12, tzinfo=UTC)\n"
        "day = date(2026, 9, 12) + timedelta(days=1)\n"
    )
    assert check_purity("backend/erev_engine/x.py", snippet) == []
