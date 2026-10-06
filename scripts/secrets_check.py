#!/usr/bin/env python3
"""Secrets pattern scan (docs/dev-guide.md DG-MK-secrets-check; 05 SAR-18; REQ-SEC-003).

Steps, stopping at the first failing step:
  1. self-test: every fixture in scripts/secrets_check_fixtures/ named <PATTERN_ID>.<ext> yields
     exactly that pattern id, and clean.txt yields none;
  2. scan the repository files (tracked plus untracked, not ignored) other than binary files and
     backend/tests/fixtures/legacy_*; outside a git repository, every file under the root except
     .git/ and the DG-LAY-08 ignore entries;
  3. compare findings with scripts/secrets_allowlist.toml entries {path, pattern_id, line_sha256,
     reason}, where line_sha256 is the SHA-256 of the stripped matching line.

Output lines are `path:line SECRET <pattern id>`; the matched text is never printed. Exit 1 on any
finding without an allow-list entry, on any allow-list entry that matches nothing, and on an
invalid allow-list or a failing self-test.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "scripts" / "secrets_check_fixtures"
DEFAULT_ALLOWLIST = ROOT / "scripts" / "secrets_allowlist.toml"
CLEAN_FIXTURE = "clean.txt"

PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
PEM_PREFIX = "-----BEGIN "
TOKEN_PATTERNS = (
    ("ANTHROPIC_KEY", re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")),
    ("AWS_ACCESS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("SLACK_TOKEN", re.compile(r"xox[abprs]-[A-Za-z0-9-]{8,}")),
)
PASSWORD_ASSIGNMENT = re.compile(
    r"""(?i)\b(password|passwd|secret|api_key|token)\b\s*[:=]\s*["'][^"'\s]{8,}["']"""
)
# PASSWORD_ASSIGNMENT applies to these suffixes only.
CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".yaml", ".yml", ".tf"})
PATTERN_IDS = (
    "PRIVATE_KEY",
    "PEM_BLOCK",
    "ANTHROPIC_KEY",
    "AWS_ACCESS_KEY",
    "SLACK_TOKEN",
    "PASSWORD_ASSIGNMENT",
)
SKIPPED_PREFIXES = ("backend/tests/fixtures/legacy_",)
BINARY_PROBE_BYTES = 8192

# Walk fallback outside git: .git/ plus the .gitignore entries of docs/dev-guide.md DG-LAY-08.
IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".data",
        ".run",
        ".scratch",
        ".ralph",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "dist",
        "coverage",
    }
)
IGNORED_DIRECTORY_PATHS = frozenset(
    {
        "backend/.hypothesis",
        "backend/.pytest_cache",
        "frontend/dist",
        "frontend/e2e/.screens",
        "frontend/e2e/.results",
        "deploy/terraform/gcp/.terraform",
    }
)
IGNORED_FILE_PATTERNS = (".env", "*.pyc", ".DS_Store", "*.tfstate", "*.tfstate.*")
IGNORED_FILE_PATHS = frozenset({"release-manifest.json"})

_ALLOW_KEYS = frozenset({"path", "pattern_id", "line_sha256", "reason"})
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int
    pattern_id: str
    line_sha256: str

    def render(self) -> str:
        return f"{self.path}:{self.line} SECRET {self.pattern_id}"


@dataclass(frozen=True, slots=True)
class AllowEntry:
    path: str
    pattern_id: str
    line_sha256: str
    reason: str


class AllowListError(ValueError):
    """The allow-list file is missing, unparsable or holds an invalid entry."""


def line_sha256(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()


def pattern_ids_in_line(line: str, *, code: bool) -> list[str]:
    ids: list[str] = []
    if PRIVATE_KEY.search(line):
        ids.append("PRIVATE_KEY")
    elif line.lstrip().startswith(PEM_PREFIX):
        ids.append("PEM_BLOCK")
    ids.extend(pattern_id for pattern_id, pattern in TOKEN_PATTERNS if pattern.search(line))
    if code and PASSWORD_ASSIGNMENT.search(line):
        ids.append("PASSWORD_ASSIGNMENT")
    return ids


def scan_text(text: str, path: str) -> list[Finding]:
    """Findings in ``text``; ``path`` is the repository-relative POSIX path."""
    code = Path(path).suffix.lower() in CODE_SUFFIXES
    findings: list[Finding] = []
    for number, line in enumerate(text.split("\n"), start=1):
        for pattern_id in pattern_ids_in_line(line, code=code):
            findings.append(Finding(path, number, pattern_id, line_sha256(line)))
    return findings


def read_text(path: Path) -> str | None:
    """File content as text, or None for binary files."""
    data = path.read_bytes()
    if b"\0" in data[:BINARY_PROBE_BYTES]:
        return None
    return data.decode("utf-8", errors="replace")


def _is_git_toplevel(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and Path(result.stdout.strip()).resolve() == root.resolve()


def _git_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    )
    return sorted({name for name in result.stdout.decode("utf-8").split("\0") if name})


def _walk_files(root: Path) -> list[str]:
    files: list[str] = []
    for directory, subdirectories, names in os.walk(root):
        relative = Path(directory).relative_to(root).as_posix()
        prefix = "" if relative == "." else f"{relative}/"
        subdirectories[:] = sorted(
            name
            for name in subdirectories
            if name not in IGNORED_DIRECTORY_NAMES
            and f"{prefix}{name}" not in IGNORED_DIRECTORY_PATHS
        )
        for name in names:
            if f"{prefix}{name}" in IGNORED_FILE_PATHS:
                continue
            if any(fnmatch.fnmatchcase(name, pattern) for pattern in IGNORED_FILE_PATTERNS):
                continue
            files.append(f"{prefix}{name}")
    return sorted(files)


def list_files(root: Path) -> list[str]:
    names = _git_files(root) if _is_git_toplevel(root) else _walk_files(root)
    return [name for name in names if not name.startswith(SKIPPED_PREFIXES)]


def scan_repository(root: Path) -> tuple[int, list[Finding]]:
    scanned = 0
    findings: list[Finding] = []
    for name in list_files(root):
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        text = read_text(path)
        if text is None:
            continue
        scanned += 1
        findings.extend(scan_text(text, name))
    return scanned, findings


def load_allowlist(path: Path) -> list[AllowEntry]:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AllowListError(f"{path.name}: file not found") from error
    except tomllib.TOMLDecodeError as error:
        raise AllowListError(f"{path.name}: {error}") from error
    unknown = set(document) - {"allow"}
    if unknown:
        raise AllowListError(f"{path.name}: unknown top-level keys {sorted(unknown)}")
    raw_entries = document.get("allow", [])
    if not isinstance(raw_entries, list):
        raise AllowListError(f"{path.name}: 'allow' must be an array of tables")
    entries: list[AllowEntry] = []
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict) or set(raw) != _ALLOW_KEYS:
            raise AllowListError(
                f"{path.name}: entry {index} must have exactly {sorted(_ALLOW_KEYS)}"
            )
        if not all(isinstance(value, str) and value.strip() for value in raw.values()):
            raise AllowListError(f"{path.name}: entry {index} values must be non-empty strings")
        if raw["pattern_id"] not in PATTERN_IDS:
            raise AllowListError(f"{path.name}: entry {index} has an unknown pattern_id")
        if not _SHA256_HEX.match(raw["line_sha256"]):
            raise AllowListError(f"{path.name}: entry {index} line_sha256 must be 64 lowercase hex")
        entries.append(
            AllowEntry(raw["path"], raw["pattern_id"], raw["line_sha256"], raw["reason"])
        )
    return entries


def self_test(fixtures: Path) -> list[str]:
    """Error messages; empty when every fixture yields exactly its expected pattern ids."""
    errors: list[str] = []
    if not fixtures.is_dir():
        return [f"fixture directory {fixtures.name} not found"]
    covered: set[str] = set()
    for path in sorted(p for p in fixtures.iterdir() if p.is_file()):
        if path.name == CLEAN_FIXTURE:
            expected: set[str] = set()
        elif path.stem in PATTERN_IDS:
            expected = {path.stem}
            covered.add(path.stem)
        else:
            errors.append(f"fixture {path.name} names no pattern id")
            continue
        text = read_text(path)
        actual = {finding.pattern_id for finding in scan_text(text or "", path.name)}
        if actual != expected:
            errors.append(
                f"fixture {path.name} expected {sorted(expected)} but yielded {sorted(actual)}"
            )
    if not (fixtures / CLEAN_FIXTURE).is_file():
        errors.append(f"fixture {CLEAN_FIXTURE} not found")
    for pattern_id in PATTERN_IDS:
        if pattern_id not in covered:
            errors.append(f"pattern {pattern_id} has no fixture")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="directory to scan")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args(argv)

    errors = self_test(args.fixtures)
    if errors:
        for message in errors:
            print(f"secrets-check self-test: {message}")
        return 1

    try:
        allowlist = load_allowlist(args.allowlist)
    except AllowListError as error:
        print(f"secrets-check allow-list: {error}")
        return 1

    root = args.root.resolve()
    scanned, findings = scan_repository(root)
    allowed = {(entry.path, entry.pattern_id, entry.line_sha256) for entry in allowlist}
    used: set[tuple[str, str, str]] = set()
    unallowed: list[Finding] = []
    for finding in findings:
        key = (finding.path, finding.pattern_id, finding.line_sha256)
        if key in allowed:
            used.add(key)
        else:
            unallowed.append(finding)
    unused = [
        entry
        for entry in allowlist
        if (entry.path, entry.pattern_id, entry.line_sha256) not in used
    ]

    for finding in unallowed:
        print(finding.render())
    for entry in unused:
        print(f"{args.allowlist.name}: entry for {entry.path} {entry.pattern_id} matches nothing")
    print(
        f"secrets-check: {scanned} files scanned, {len(findings) - len(unallowed)} allow-listed, "
        f"{len(unallowed)} findings, {len(unused)} unused allow-list entries"
    )
    return 1 if unallowed or unused else 0


if __name__ == "__main__":
    sys.exit(main())
