"""scripts/vocab_check.py contract (docs/dev-guide.md DG-MK-vocab-check; REQ-UX-010; BUILD_SPEC
FND-16)."""

from __future__ import annotations

import importlib.util
import json
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
SCRIPT = ROOT / "scripts" / "vocab_check.py"
FIXTURES = ROOT / "scripts" / "vocab_check_fixtures"
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
OUTPUT_LINE = re.compile(r"^[^\s:]+:\d+:\d+ VOCAB \S.*$")


@pytest.fixture(scope="module")
def module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vocab_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def scratch_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _terms(module: ModuleType, text: str, path: str) -> list[str]:
    return [finding.term for finding in module.scan_file(text, path)]


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_mk_vocab_check_self_test(module: ModuleType, scratch_dir: Path) -> None:
    assert module.TERMS == TERMS
    assert module.self_test(FIXTURES) == []
    for term in TERMS:
        (fixture,) = sorted(FIXTURES.glob(f"{module.term_slug(term)}.*"))
        assert _terms(module, fixture.read_text("utf-8"), fixture.name) == [term], fixture.name
    assert _terms(module, (FIXTURES / "clean.tsx").read_text("utf-8"), "clean.tsx") == []

    # The repository scan is clean and prints the summary line.
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(r"vocab-check: \d+ files scanned, 0 findings", result.stdout)

    # A fixture that yields the wrong terms fails the self-test before any scan.
    broken = scratch_dir / "fixtures"
    shutil.copytree(FIXTURES, broken)
    shutil.copyfile(FIXTURES / "carve-out.tsx", broken / "clean.tsx")
    failed = _run("--fixtures", str(broken))
    assert failed.returncode == 1
    assert "self-test: fixture clean.tsx expected [] but yielded ['Carve-out']" in failed.stdout
    assert " VOCAB " not in failed.stdout

    # A fixture directory missing a term fails too.
    (broken / "clean.tsx").write_text("export const ok = true;\n", encoding="utf-8")
    (broken / "revi.py").unlink()
    failed = _run("--fixtures", str(broken))
    assert failed.returncode == 1
    assert "self-test: term 'Revi' has no fixture" in failed.stdout


def test_whole_word_case_insensitive_matching(module: ModuleType, scratch_dir: Path) -> None:
    path = "frontend/src/x.tsx"
    assert _terms(module, "<p>carved</p>", path) == []
    assert _terms(module, "<p>Net   Position</p>", path) == ["net position"]
    assert _terms(module, "<p>Net\n\tposition</p>", path) == ["net position"]
    assert _terms(module, "<p>POB’s</p>", path) == ["POB's"]
    assert _terms(module, "<p>pob's</p>", path) == ["POB's"]
    assert _terms(module, "<p>Carve-out</p>", path) == ["Carve-out"]
    assert _terms(module, "<p>CARVES</p>", path) == ["Carves"]
    # Letters, digits and underscores on either side prevent a match.
    assert _terms(module, "Review revision net_position unplanned_x xRevi Revi2", path) == []
    assert _terms(module, "Revenue Desk 3600", path) == []

    # Output lines name path, 1-based line and column, and the longest term.
    root = scratch_dir / "repo"
    _write(
        root, "frontend/src/routes/home.tsx", 'const a = "ok";\nexport const b = "  Carve-out";\n'
    )
    result = _run("--root", str(root))
    assert result.returncode == 1
    lines = [line for line in result.stdout.splitlines() if " VOCAB " in line]
    assert lines == ["frontend/src/routes/home.tsx:2:21 VOCAB Carve-out"]
    assert all(OUTPUT_LINE.match(line) for line in lines)
    assert "1 files scanned, 1 findings" in result.stdout


def test_allow_list_paths(module: ModuleType, scratch_dir: Path) -> None:
    root = scratch_dir / "repo"
    constant = 'LABEL = "Unbilled A/R"\n'
    _write(root, "backend/erev_api/domain/reports/legacy_columns.py", constant)
    _write(root, "backend/erev_api/domain/imports/legacy_templates.py", constant)
    _write(root, "backend/erev_api/domain/reports/modern_columns.py", constant)
    _write(
        root,
        "backend/erev_api/domain/reports/documented.py",
        '"""Legacy Unbilled A/R column."""\n\n\ndef f() -> str:\n'
        '    """Carve-out."""\n    return "ok"\n\n\nclass C:\n    """net position"""\n',
    )
    messages = {
        "help.legacy-transition.unbilled": "Unbilled A/R becomes Unbilled receivable.",
        "help": {"legacy-transition": {"allocation": "Carves are now allocation adjustments."}},
        "balances.unbilled": "Unbilled A/R",
    }
    _write(root, "frontend/src/messages/en.json", json.dumps(messages, indent=2) + "\n")
    _write(root, "frontend/src/messages/fr.json", json.dumps(messages, indent=2) + "\n")

    scanned, findings, errors = module.scan_repository(root)
    assert errors == []
    assert scanned == 4  # the two legacy column modules are allow-listed files
    reported = sorted((finding.path, finding.line, finding.term) for finding in findings)
    assert reported == [
        ("backend/erev_api/domain/reports/modern_columns.py", 1, "Unbilled A/R"),
        ("frontend/src/messages/en.json", 8, "Unbilled A/R"),
        ("frontend/src/messages/fr.json", 2, "Unbilled A/R"),
        ("frontend/src/messages/fr.json", 5, "Carves"),
        ("frontend/src/messages/fr.json", 8, "Unbilled A/R"),
    ]
    # Keys are scanned as well; only values under help.legacy-transition. are allow-listed.
    keyed = json.dumps({"help.legacy-transition.carves": "ok"})
    assert _terms(module, keyed, "frontend/src/messages/en.json") == ["Carves"]

    # Terms reached only through escapes or implicit concatenation are reported at the constant;
    # the literal "Carve" before the escape is not a separate finding. F-string text keeps its
    # source column.
    source = 'A = "net " "position"\nB = "Carve\\u002dout"\nC = f"{A} Revi"\n'
    positions = [(f.line, f.col, f.term) for f in module.scan_python(source, "x.py")]
    assert positions == [(1, 5, "net position"), (2, 5, "Carve-out"), (3, 11, "Revi")]


def test_makefile_vocab_check_step_follows_design_check() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    steps = re.findall(r"--no-print-directory ([a-z-]+),", makefile.split("\nlint:", 1)[1])
    assert steps[:4] == ["design-check", "vocab-check", "licence-check", "secrets-check"]
