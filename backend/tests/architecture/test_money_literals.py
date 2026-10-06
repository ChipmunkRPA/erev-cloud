"""DG-ARC-06: two-decimal money literals only in ``erev_engine/money.py`` (D-11; ALG-01;
BUILD_SPEC FND-13).

Rounding to a minor unit happens only through ``erev_engine.money``, which takes the minor unit
from ``ISO_4217``; a hard-coded cent is wrong for JPY, BHD and every other non-2-decimal currency.
"""

from __future__ import annotations

import ast
import re
from typing import Final

from support.architecture import Finding, callee, iter_files, read, report

RULE: Final = "DG-ARC-06"
PY: Final = frozenset({".py"})
ROUNDING_MODULE: Final = "backend/erev_engine/money.py"
TWO_DECIMALS: Final = re.compile(r"[+-]?\d*\.\d{2}")
CENT: Final = re.compile(r"[+-]?0*\.01")


def _decimal_literal(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Call)
        and callee(node) == "Decimal"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value.strip()
    return None


def check_money_literals(path: str, source: str) -> list[Finding]:
    if path == ROUNDING_MODULE:
        return []
    tree = ast.parse(source, filename=path)
    findings: list[Finding] = []
    quantized: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and callee(node) == "quantize" and node.args:
            literal = _decimal_literal(node.args[0])
            if literal is not None and TWO_DECIMALS.fullmatch(literal):
                quantized.add(id(node.args[0]))
                findings.append(Finding(path, node.lineno, RULE, f"quantize to {literal!r}"))
    for node in ast.walk(tree):
        literal = _decimal_literal(node)
        if literal is not None and id(node) not in quantized and CENT.fullmatch(literal):
            findings.append(Finding(path, node.lineno, RULE, f"Decimal({literal!r})"))
    return sorted(findings)


def test_dg_arc_06_detects_two_decimal_literal() -> None:
    for path in ("backend/erev_api/domain/x.py", "backend/erev_engine/stages/x.py"):
        literal = check_money_literals(path, 'CENT = Decimal("0.01")\n')
        assert [(finding.line, finding.rule) for finding in literal] == [(1, RULE)], report(literal)
        quantize = check_money_literals(path, "amount = value.quantize(Decimal('0.01'))\n")
        assert [(finding.line, finding.rule) for finding in quantize] == [(1, RULE)], report(
            quantize
        )
    assert len(check_money_literals("backend/erev_api/x.py", 'v.quantize(Decimal("1.00"))\n')) == 1
    assert check_money_literals(ROUNDING_MODULE, 'CENT = Decimal("0.01")\n') == []
    assert check_money_literals("backend/erev_api/x.py", 'v.quantize(Decimal("0.0001"))\n') == []
    assert check_money_literals("backend/erev_api/x.py", 'v = Decimal("12.30")\n') == []


def test_dg_arc_06_repository_clean() -> None:
    findings = [
        finding
        for path in iter_files("backend/erev_api", "backend/erev_engine", suffixes=PY)
        for finding in check_money_literals(path, read(path))
    ]
    assert findings == [], report(findings)
