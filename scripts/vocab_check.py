#!/usr/bin/env python3
"""Vocabulary lint (docs/dev-guide.md DG-MK-vocab-check; REQ-UX-010; DESIGN_SYSTEM DS-LINT-19).

Steps, stopping at the first failing step:
  1. self-test: every fixture in scripts/vocab_check_fixtures/ named <term slug>.<ext> yields
     exactly that term, and clean.tsx yields none;
  2. scan frontend/src/**/*.{ts,tsx,json} as text, and the string constants of
     backend/erev_api/**/*.py other than docstrings (read with ast);
  3. skip the allow-list: the legacy column definitions (D-33) and, in
     frontend/src/messages/en.json, the values of keys starting with help.legacy-transition.

Matching is case-insensitive and whole-word; a space inside a term matches one or more whitespace
characters and the apostrophe matches ' or U+2019. Output lines are
`path:line:col VOCAB <longest matching term>`. Exit 1 on any finding or a failing self-test.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "scripts" / "vocab_check_fixtures"
CLEAN_FIXTURE = "clean.tsx"

# The REQ-UX-010 list, verbatim; reported spellings are these.
TERMS = (
    "Revenue Desk 360",
    "Planned revenue",
    "Revenue planned",
    "Unplanned",
    "Carve",
    "Carves",
    "Carve-in",
    "Carve-out",
    "Revi",
    "Unbilled A/R",
    "POB's",
    "net position",
)

FRONTEND_ROOT = "frontend/src"
FRONTEND_SUFFIXES = frozenset({".ts", ".tsx", ".json"})
BACKEND_ROOT = "backend/erev_api"
ALLOWED_FILES = frozenset(
    {
        "backend/erev_api/domain/reports/legacy_columns.py",
        "backend/erev_api/domain/imports/legacy_templates.py",
    }
)
MESSAGES_FILE = "frontend/src/messages/en.json"
ALLOWED_MESSAGE_PREFIX = "help.legacy-transition."


def term_slug(term: str) -> str:
    """Fixture file stem of a term, for example `unbilled-a-r` for "Unbilled A/R"."""
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def _term_source(term: str) -> str:
    parts = []
    for character in term:
        if character == " ":
            parts.append(r"\s+")
        elif character == "'":
            parts.append("['’]")
        else:
            parts.append(re.escape(character))
    return "".join(parts)


# Longest terms first, so that "Carve-out" wins over "Carve" at the same position.
_ORDERED = sorted(range(len(TERMS)), key=lambda index: (-len(TERMS[index]), index))
PATTERN = re.compile(
    r"(?<!\w)(?:"
    + "|".join(f"(?P<t{index}>{_term_source(TERMS[index])})" for index in _ORDERED)
    + r")(?!\w)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int
    col: int
    term: str

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.col} VOCAB {self.term}"


class _Positions:
    """Maps character offsets of a text to 1-based line and column numbers."""

    def __init__(self, text: str) -> None:
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer("\n", text))

    def at(self, offset: int) -> tuple[int, int]:
        low, high = 0, len(self.line_starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if self.line_starts[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return low + 1, offset - self.line_starts[low] + 1


def matches(text: str) -> Iterator[tuple[int, str]]:
    """(offset, term) for every forbidden term in ``text``."""
    for match in PATTERN.finditer(text):
        assert match.lastgroup is not None
        yield match.start(), TERMS[int(match.lastgroup[1:])]


def _json_string_spans(text: str) -> list[tuple[str, int, int]]:
    """(dotted key path, start, end) of every string value of a valid JSON document."""
    spans: list[tuple[str, int, int]] = []
    index = 0

    def skip_whitespace() -> None:
        nonlocal index
        while index < len(text) and text[index] in " \t\r\n":
            index += 1

    def string() -> tuple[int, int]:
        nonlocal index
        start = index
        index += 1
        while text[index] != '"':
            index += 2 if text[index] == "\\" else 1
        index += 1
        return start, index

    def value(path: tuple[str, ...]) -> None:
        nonlocal index
        skip_whitespace()
        opener = text[index]
        if opener in "{[":
            closer = "}" if opener == "{" else "]"
            index += 1
            skip_whitespace()
            position = 0
            while text[index] != closer:
                if opener == "{":
                    key_start, key_end = string()
                    key = str(json.loads(text[key_start:key_end]))
                    skip_whitespace()
                    index += 1  # the colon
                    value((*path, key))
                else:
                    value((*path, str(position)))
                position += 1
                skip_whitespace()
                if text[index] == ",":
                    index += 1
                    skip_whitespace()
            index += 1
        elif opener == '"':
            start, end = string()
            spans.append((".".join(path), start, end))
        else:
            while index < len(text) and text[index] not in ",}] \t\r\n":
                index += 1

    value(())
    return spans


def scan_text(text: str, path: str) -> list[Finding]:
    """Findings in a frontend source file; ``path`` is the repository-relative POSIX path."""
    allowed: list[tuple[int, int]] = []
    if path == MESSAGES_FILE:
        json.loads(text)
        allowed = [
            (start, end)
            for key, start, end in _json_string_spans(text)
            if key.startswith(ALLOWED_MESSAGE_PREFIX)
        ]
    positions = _Positions(text)
    findings: list[Finding] = []
    for offset, term in matches(text):
        if any(start <= offset < end for start, end in allowed):
            continue
        line, col = positions.at(offset)
        findings.append(Finding(path, line, col, term))
    return findings


def _docstring_nodes(tree: ast.Module) -> set[int]:
    owners: list[ast.AST] = [tree]
    owners.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    )
    docstrings: set[int] = set()
    for owner in owners:
        body = getattr(owner, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    return docstrings


def scan_python(source: str, path: str) -> list[Finding]:
    """Findings in the string constants of a Python module, docstrings excluded."""
    tree = ast.parse(source, filename=path)
    docstrings = _docstring_nodes(tree)
    lines = source.split("\n")
    line_starts = [0]
    for line in lines[:-1]:
        line_starts.append(line_starts[-1] + len(line) + 1)
    positions = _Positions(source)

    def offset(line: int, byte_col: int) -> int:
        encoded = lines[line - 1].encode("utf-8")[:byte_col]
        return line_starts[line - 1] + len(encoded.decode("utf-8", errors="replace"))

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings or node.end_lineno is None or node.end_col_offset is None:
            continue
        start = offset(node.lineno, node.col_offset)
        end = offset(node.end_lineno, node.end_col_offset)
        # The string value decides which terms occur. Source positions come from the literal
        # text; a term that only appears once escapes or implicit concatenation are resolved is
        # reported at the start of the constant, and literal-text artefacts of escapes are dropped.
        value_terms = {term for _, term in matches(node.value)}
        located: set[str] = set()
        for relative, term in matches(source[start:end]):
            if term in value_terms:
                line, col = positions.at(start + relative)
                findings.append(Finding(path, line, col, term))
                located.add(term)
        for term in sorted(value_terms - located):
            line, col = positions.at(start)
            findings.append(Finding(path, line, col, term))
    return sorted(findings, key=lambda finding: (finding.line, finding.col, finding.term))


def scan_file(text: str, path: str) -> list[Finding]:
    if path.endswith(".py"):
        return scan_python(text, path)
    return scan_text(text, path)


def list_files(root: Path) -> list[str]:
    names: list[str] = []
    frontend = root / FRONTEND_ROOT
    if frontend.is_dir():
        names.extend(
            path.relative_to(root).as_posix()
            for path in frontend.rglob("*")
            if path.suffix in FRONTEND_SUFFIXES and path.is_file() and not path.is_symlink()
        )
    backend = root / BACKEND_ROOT
    if backend.is_dir():
        names.extend(
            path.relative_to(root).as_posix()
            for path in backend.rglob("*.py")
            if path.is_file() and not path.is_symlink()
        )
    return sorted(name for name in names if name not in ALLOWED_FILES)


def scan_repository(root: Path) -> tuple[int, list[Finding], list[str]]:
    """(files scanned, findings, parse errors)."""
    findings: list[Finding] = []
    errors: list[str] = []
    names = list_files(root)
    for name in names:
        text = (root / name).read_text(encoding="utf-8")
        try:
            findings.extend(scan_file(text, name))
        except (SyntaxError, ValueError) as error:
            errors.append(f"{name}: cannot parse ({error.__class__.__name__})")
    return len(names), findings, errors


def self_test(fixtures: Path) -> list[str]:
    """Error messages; empty when every fixture yields exactly its expected terms."""
    if not fixtures.is_dir():
        return [f"fixture directory {fixtures.name} not found"]
    by_slug = {term_slug(term): term for term in TERMS}
    errors: list[str] = []
    covered: set[str] = set()
    for path in sorted(p for p in fixtures.iterdir() if p.is_file()):
        if path.name == CLEAN_FIXTURE:
            expected: set[str] = set()
        elif path.stem in by_slug:
            expected = {by_slug[path.stem]}
            covered.add(by_slug[path.stem])
        else:
            errors.append(f"fixture {path.name} names no term")
            continue
        actual = {finding.term for finding in scan_file(path.read_text("utf-8"), path.name)}
        if actual != expected:
            errors.append(
                f"fixture {path.name} expected {sorted(expected)} but yielded {sorted(actual)}"
            )
    if not (fixtures / CLEAN_FIXTURE).is_file():
        errors.append(f"fixture {CLEAN_FIXTURE} not found")
    errors.extend(f"term {term!r} has no fixture" for term in TERMS if term not in covered)
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to scan")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args(argv)

    errors = self_test(args.fixtures)
    if errors:
        for message in errors:
            print(f"vocab-check self-test: {message}")
        return 1

    scanned, findings, parse_errors = scan_repository(args.root.resolve())
    for finding in findings:
        print(finding.render())
    for message in parse_errors:
        print(f"vocab-check: {message}")
    print(f"vocab-check: {scanned} files scanned, {len(findings)} findings")
    return 1 if findings or parse_errors else 0


if __name__ == "__main__":
    sys.exit(main())
