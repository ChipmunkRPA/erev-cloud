"""Engine error vocabulary (dev-guide §7 DG-ENG-06; 04 §15.4; BUILD_SPEC EKC-5).

Every string literal passed as the code of ``EngineError(...)`` under ``backend/erev_engine/`` is a
04 §15.4 code or one of the DG-ENG-06 engine codes. Withdrawn codes (table 15.4-H) and synonyms
(table 15.4-S) are never emitted, so they do not count. The test stays in force for every later
stage; it reads the sources with ``ast`` and 04 read-only.
"""

from __future__ import annotations

import ast
import re
from functools import cache

from support.architecture import ROOT, callee, iter_files, read

DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"
ENGINE_CODES = frozenset(
    {
        "ENGINE_VERSION_MISMATCH",
        "FLOAT_DETECTED",
        "TRACE_DUPLICATE_NODE",
        "ENGINE_INVARIANT_VIOLATED",
    }
)
NEVER_EMITTED_TABLES = frozenset({"H", "S"})
_CODE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")


@cache
def catalogue_codes() -> frozenset[str]:
    """Codes of the lettered 04 §15.4 tables other than 15.4-H and 15.4-S."""
    text = DATA_MODEL.read_text(encoding="utf-8")
    begin = text.index("\n### 15.4 Finding")
    section = text[begin : text.index("\n## 16. ", begin)]
    codes: set[str] = set()
    letter: str | None = None
    for line in section.splitlines():
        heading = re.match(r"^\*\*Table 15\.4-([A-Z]) ", line)
        if heading:
            letter = heading.group(1)
            continue
        if letter is None or letter in NEVER_EMITTED_TABLES or not line.startswith("| `"):
            continue
        first = line.strip().strip("|").split("|")[0].strip()
        literal = re.fullmatch(r"`([^`]+)`", first)
        if literal and _CODE.fullmatch(literal.group(1)):
            codes.add(literal.group(1))
    return frozenset(codes)


def engine_error_codes(path: str, source: str) -> list[tuple[str, int, str]]:
    """(path, line, code) per literal code given to ``EngineError``, positionally or as ``code``."""
    found: list[tuple[str, int, str]] = []
    for node in ast.walk(ast.parse(source, filename=path)):
        if not isinstance(node, ast.Call) or callee(node) != "EngineError":
            continue
        arguments = [*node.args[:1], *(kw.value for kw in node.keywords if kw.arg == "code")]
        for argument in arguments:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.append((path, argument.lineno, argument.value))
    return sorted(found)


def test_engine_error_codes_catalogued() -> None:
    allowed = catalogue_codes() | ENGINE_CODES
    used = [
        item
        for path in iter_files("backend/erev_engine", suffixes=frozenset({".py"}))
        for item in engine_error_codes(path, read(path))
    ]
    unknown = [f"{path}:{line} {code}" for path, line, code in used if code not in allowed]
    assert unknown == []
    # The scan sees the kernel's codes, so an empty result cannot pass silently.
    assert {
        "NEGATIVE_WEIGHT",
        "TOTAL_WEIGHT_ZERO",
        "FLOAT_DETECTED",
        "TRACE_DUPLICATE_NODE",
        "ENGINE_INVARIANT_VIOLATED",
    } <= {code for _, _, code in used}
    # DG-ENG-06 examples come from 04 §15.4 tables A and C; withdrawn codes are excluded.
    assert {
        "NEGATIVE_WEIGHT",
        "TOTAL_WEIGHT_ZERO",
        "MOD_REMAINING_NEGATIVE",
        "MOD_PROGRESS_UNDEFINED",
        "VC_ALLOCATION_NEGATIVE",
        "NON_FINITE_AMOUNT",
        "BILL_AND_HOLD_CRITERIA_UNMET",
        "FX_RATE_MISSING",
        "STEP1_RECORD",
    } <= catalogue_codes()
    assert "TERM_NOT_WHOLE_MONTHS" not in catalogue_codes()


def test_collector_reads_positional_and_keyword_codes() -> None:
    path = "backend/erev_engine/snippet.py"
    source = (
        "from erev_engine import errors\n"
        'raise errors.EngineError("TERM_NOT_WHOLE_MONTHS", "withdrawn")\n'
        'raise EngineError(code="NEGATIVE_WEIGHT", message="m")\n'
        'raise EngineError(code_variable, "not a literal")\n'
        'raise ValueError("NOT_AN_ENGINE_ERROR")\n'
    )
    assert engine_error_codes(path, source) == [
        (path, 2, "TERM_NOT_WHOLE_MONTHS"),
        (path, 3, "NEGATIVE_WEIGHT"),
    ]
    assert "TERM_NOT_WHOLE_MONTHS" not in catalogue_codes() | ENGINE_CODES
