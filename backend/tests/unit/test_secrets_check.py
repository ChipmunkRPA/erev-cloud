"""scripts/secrets_check.py contract (docs/dev-guide.md DG-MK-secrets-check; BUILD_SPEC FND-3)."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "secrets_check.py"
FIXTURES = ROOT / "scripts" / "secrets_check_fixtures"
PATTERN_IDS = (
    "PRIVATE_KEY",
    "PEM_BLOCK",
    "ANTHROPIC_KEY",
    "AWS_ACCESS_KEY",
    "SLACK_TOKEN",
    "PASSWORD_ASSIGNMENT",
)
OUTPUT_LINE = re.compile(r"^[^\s:]+:\d+ SECRET [A-Z_]+$")


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("secrets_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _fixture_path(pattern_id: str) -> Path:
    matches = sorted(FIXTURES.glob(f"{pattern_id}.*"))
    assert len(matches) == 1, f"one fixture per pattern id: {pattern_id}"
    return matches[0]


def _findings(module: ModuleType, path: Path) -> set[str]:
    return {finding.pattern_id for finding in module.scan_text(path.read_text(), path.name)}


def _matched_texts(module: ModuleType, path: Path) -> list[str]:
    """The substrings the patterns match in a fixture, which output must never contain."""
    texts: list[str] = []
    for line in path.read_text().splitlines():
        for pattern in (module.PRIVATE_KEY, module.PASSWORD_ASSIGNMENT):
            texts.extend(match.group(0) for match in pattern.finditer(line))
        texts.extend(m.group(0) for _, p in module.TOKEN_PATTERNS for m in p.finditer(line))
        if line.startswith(module.PEM_PREFIX):
            texts.append(line.strip())
    return texts


@pytest.fixture
def scratch_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _write_allowlist(path: Path, entries: list[tuple[str, str, str]]) -> None:
    blocks = [
        f'[[allow]]\npath = "{p}"\npattern_id = "{pid}"\nline_sha256 = "{sha}"\nreason = "test"\n'
        for p, pid, sha in entries
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")


def test_mk_secrets_check_self_test(scratch_dir: Path) -> None:
    module = _load_module()
    assert module.PATTERN_IDS == PATTERN_IDS
    assert module.self_test(FIXTURES) == []
    for pattern_id in PATTERN_IDS:
        assert _findings(module, _fixture_path(pattern_id)) == {pattern_id}
    assert _findings(module, FIXTURES / "clean.txt") == set()

    # Scanning the fixtures as a directory prints one line per finding and never the matched text.
    root = scratch_dir / "repo"
    shutil.copytree(FIXTURES, root)
    allowlist = scratch_dir / "allow.toml"
    _write_allowlist(allowlist, [])
    result = _run("--root", str(root), "--allowlist", str(allowlist))
    assert result.returncode == 1, result.stdout + result.stderr
    finding_lines = [line for line in result.stdout.splitlines() if " SECRET " in line]
    assert all(OUTPUT_LINE.match(line) for line in finding_lines), finding_lines
    reported = {tuple(line.split(" SECRET ")) for line in finding_lines}
    expected = {
        (f"{finding.path}:{finding.line}", finding.pattern_id)
        for pattern_id in PATTERN_IDS
        for finding in module.scan_text(
            _fixture_path(pattern_id).read_text(), _fixture_path(pattern_id).name
        )
    }
    assert reported == expected
    assert {pattern_id for _, pattern_id in reported} == set(PATTERN_IDS)
    for pattern_id in PATTERN_IDS:
        for text in _matched_texts(module, _fixture_path(pattern_id)):
            assert text not in result.stdout

    # A fixture that yields the wrong ids fails the self-test before any scan.
    broken = scratch_dir / "fixtures"
    shutil.copytree(FIXTURES, broken)
    shutil.copyfile(FIXTURES / "AWS_ACCESS_KEY.txt", broken / "clean.txt")
    failed = _run("--root", str(root), "--allowlist", str(allowlist), "--fixtures", str(broken))
    assert failed.returncode == 1
    assert (
        "self-test: fixture clean.txt expected [] but yielded ['AWS_ACCESS_KEY']" in failed.stdout
    )
    assert " SECRET " not in failed.stdout


def test_mk_secrets_check_allow_list_rules(scratch_dir: Path) -> None:
    module = _load_module()
    root = scratch_dir / "repo"
    root.mkdir()
    shutil.copyfile(_fixture_path("PASSWORD_ASSIGNMENT"), root / "app.py")
    shutil.copyfile(ROOT / ".env.example", root / ".env.example")
    (finding,) = module.scan_text((root / "app.py").read_text(), "app.py")
    allowlist = scratch_dir / "allow.toml"

    # Without an entry the finding fails the run; .env.example yields nothing.
    _write_allowlist(allowlist, [])
    result = _run("--root", str(root), "--allowlist", str(allowlist))
    assert result.returncode == 1
    assert [line for line in result.stdout.splitlines() if " SECRET " in line] == [
        f"app.py:{finding.line} SECRET PASSWORD_ASSIGNMENT"
    ]
    assert module.scan_text((ROOT / ".env.example").read_text(), ".env.example") == []

    # A matching entry allows the finding.
    exact = ("app.py", "PASSWORD_ASSIGNMENT", finding.line_sha256)
    _write_allowlist(allowlist, [exact])
    result = _run("--root", str(root), "--allowlist", str(allowlist))
    assert result.returncode == 0, result.stdout
    assert "1 allow-listed, 0 findings, 0 unused allow-list entries" in result.stdout

    # An entry whose line_sha256 matches nothing makes the run exit 1.
    stale = ("app.py", "PASSWORD_ASSIGNMENT", "0" * 64)
    _write_allowlist(allowlist, [exact, stale])
    result = _run("--root", str(root), "--allowlist", str(allowlist))
    assert result.returncode == 1
    assert "allow.toml: entry for app.py PASSWORD_ASSIGNMENT matches nothing" in result.stdout

    # Editing the matching line invalidates its entry: a new finding and an unused entry.
    source = (root / "app.py").read_text().replace("fixture-not-a-secret", "fixture-edited-value")
    (root / "app.py").write_text(source)
    _write_allowlist(allowlist, [exact])
    result = _run("--root", str(root), "--allowlist", str(allowlist))
    assert result.returncode == 1
    assert f"app.py:{finding.line} SECRET PASSWORD_ASSIGNMENT" in result.stdout
    assert "matches nothing" in result.stdout

    # Malformed entries are rejected.
    allowlist.write_text('[[allow]]\npath = "app.py"\npattern_id = "NOPE"\n', encoding="utf-8")
    result = _run("--root", str(root), "--allowlist", str(allowlist))
    assert result.returncode == 1
    assert "secrets-check allow-list:" in result.stdout


def test_secrets_check_scope_skips_binary_ignored_and_legacy_fixtures(scratch_dir: Path) -> None:
    module = _load_module()
    root = scratch_dir / "repo"
    key_line = (FIXTURES / "AWS_ACCESS_KEY.txt").read_bytes()
    for relative in (
        "backend/tests/fixtures/legacy_uat/workbook.csv",
        "node_modules/pkg/index.js",
        ".run/api.log",
        ".env",
        "docs/scanned.md",
    ):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(key_line)
    (root / "binary.bin").write_bytes(b"\0" + key_line)
    assert module.list_files(root) == ["binary.bin", "docs/scanned.md"]
    scanned, findings = module.scan_repository(root)
    assert scanned == 1
    assert [(f.path, f.pattern_id) for f in findings] == [("docs/scanned.md", "AWS_ACCESS_KEY")]
    # PASSWORD_ASSIGNMENT applies to code files only; short values never match.
    assert module.scan_text('password = "short"', "app.py") == []
    fixture_line = _fixture_path("PASSWORD_ASSIGNMENT").read_text()
    assert module.scan_text(fixture_line, "notes.md") == []
    assert [f.pattern_id for f in module.scan_text(fixture_line, "values.yaml")] == [
        "PASSWORD_ASSIGNMENT"
    ]
