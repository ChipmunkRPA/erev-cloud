"""scripts/design_check.py contract (DESIGN_SYSTEM §12; docs/dev-guide.md DG-MK-design-check;
BUILD_SPEC FND-15)."""

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
SCRIPT = ROOT / "scripts" / "design_check.py"
CONFIG = ROOT / "scripts" / "design_check.toml"
FIXTURES = ROOT / "scripts" / "design_check_fixtures"
TOKENS = ROOT / "docs" / "design" / "tokens.css"
IMPLEMENTED = {f"DS-LINT-{number:02d}" for number in (*range(1, 19), 20, 22, 23)}
OUTPUT_LINE = re.compile(r"^[^\s:]+:\d+:\d+ DS-LINT-\d{2} \S.*$")
TOKEN_MESSAGE = "Token copy differs from docs/design/tokens.css. Run make tokens."


@pytest.fixture(scope="module")
def module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("design_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(loaded)
    return loaded


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(CONFIG), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _finding_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if OUTPUT_LINE.match(line)]


def _rules(module: ModuleType, path: str, text: str) -> set[tuple[str, int]]:
    paths = module.load_config(CONFIG).paths
    return {(finding.rule, finding.line) for finding in module.lint_source(path, text, paths)}


@pytest.fixture
def scratch_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


@pytest.fixture
def scratch_root(scratch_dir: Path) -> Path:
    """A minimal repository: the normative tokens and an identical token copy."""
    (scratch_dir / "docs" / "design").mkdir(parents=True)
    (scratch_dir / "frontend" / "src" / "styles").mkdir(parents=True)
    shutil.copyfile(TOKENS, scratch_dir / "docs" / "design" / "tokens.css")
    shutil.copyfile(TOKENS, scratch_dir / "frontend" / "src" / "styles" / "tokens.css")
    return scratch_dir


def test_ds_lint_21_self_test(module: ModuleType) -> None:
    config = module.load_config(CONFIG)
    expected = {fixture.file: set(fixture.expect) for fixture in config.fixtures}
    assert sorted(path.name for path in FIXTURES.iterdir()) == sorted(expected)
    assert {Path(name).stem for name in expected if name != "clean.tsx"} == IMPLEMENTED

    token_source = TOKENS.read_bytes()
    for fixture in config.fixtures:
        findings = module.fixture_findings(fixture, FIXTURES, config.paths, token_source)
        assert {finding.rule for finding in findings} == expected[fixture.file], fixture.file

    assert expected["DS-LINT-23.ts"] == {"DS-LINT-23"}
    assert "new Date(line.period.end_date)" in (FIXTURES / "DS-LINT-23.ts").read_text()
    assert expected["DS-LINT-09.tsx"] == {"DS-LINT-09", "DS-LINT-23"}
    assert re.search(r'new Date\("\d{4}-\d{2}-\d{2}"\)', (FIXTURES / "DS-LINT-09.tsx").read_text())
    assert expected["clean.tsx"] == set()
    assert module.self_test(config, FIXTURES, token_source) == []


def test_ds_lint_21_self_test_failure_stops_the_run(scratch_dir: Path) -> None:
    fixtures = scratch_dir / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    with (fixtures / "clean.tsx").open("a", encoding="utf-8") as handle:
        handle.write('export const Card = () => <div className="bg-gray-100">Card</div>;\n')
    (fixtures / "DS-LINT-04.tsx").unlink()

    result = _run("--fixtures", str(fixtures))

    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert (
        "design-check self-test: fixture clean.tsx expected [] but yielded ['DS-LINT-02']" in lines
    )
    assert "design-check self-test: fixture DS-LINT-04.tsx not found" in lines
    assert _finding_lines(result.stdout) == []


def test_ds_lint_14_token_copy_mismatch(scratch_root: Path) -> None:
    assert _run("--root", str(scratch_root)).returncode == 0

    copy = scratch_root / "frontend" / "src" / "styles" / "tokens.css"
    copy.write_bytes(copy.read_bytes() + b"\n")
    result = _run("--root", str(scratch_root))

    assert result.returncode == 1
    assert _finding_lines(result.stdout) == [
        f"frontend/src/styles/tokens.css:1:1 DS-LINT-14 {TOKEN_MESSAGE}"
    ]


def test_ds_lint_15_dark_blocks_in_sync(module: ModuleType) -> None:
    text = TOKENS.read_text(encoding="utf-8")
    media, attribute = module.dark_blocks(text)
    assert media is not None and len(media) > 50
    assert media == attribute
    assert module.check_dark_blocks("docs/design/tokens.css", text) == []

    selector = ':root[data-theme="dark"] {'
    drifted = text.replace(selector, f"{selector}\n  --drift: 0;", 1)
    findings = module.check_dark_blocks("docs/design/tokens.css", drifted)
    assert [(finding.rule, finding.line) for finding in findings] == [
        ("DS-LINT-15", text[: text.index(selector)].count("\n") + 1)
    ]


def test_suppression_rules(module: ModuleType) -> None:
    row = 'export const Row = () => <div className="gap-[3px]">Row</div>;\n'
    assert _rules(module, "frontend/src/Row.tsx", row) == {("DS-LINT-12", 1)}

    unreasoned = "// design-check-ignore DS-LINT-12\n" + row
    assert _rules(module, "frontend/src/Row.tsx", unreasoned) == {
        ("DS-LINT-00", 1),
        ("DS-LINT-12", 2),
    }
    unreasoned_jsx = row.replace("Row</div>", "Row</div>{/* design-check-ignore DS-LINT-12 */}", 1)
    assert ("DS-LINT-00", 1) in _rules(module, "frontend/src/Row.tsx", unreasoned_jsx)

    reasoned = "// design-check-ignore DS-LINT-12: sticky header offset\n" + row
    assert _rules(module, "frontend/src/Row.tsx", reasoned) == set()
    same_line = row.rstrip("\n") + " // design-check-ignore DS-LINT-12: sticky header offset\n"
    assert _rules(module, "frontend/src/Row.tsx", same_line) == set()

    colour = (
        '// design-check-ignore DS-LINT-01: legacy chart colour\nexport const tone = "#1f2937";\n'
    )
    assert _rules(module, "frontend/src/tone.ts", colour) == {("DS-LINT-01", 2)}


def test_output_format_and_exit_codes(scratch_root: Path) -> None:
    catalogue = scratch_root / "frontend" / "src" / "messages" / "en.json"
    catalogue.parent.mkdir(parents=True)
    text = '{\n  "save.done": "Changes saved!"\n}\n'
    catalogue.write_text(text, encoding="utf-8")

    result = _run("--root", str(scratch_root))

    assert result.returncode == 0, result.stdout
    column = text.splitlines()[1].index("!") + 1
    lines = _finding_lines(result.stdout)
    assert lines == [
        f"frontend/src/messages/en.json:2:{column} DS-LINT-18 No exclamation marks in UI copy."
    ]
    assert all(OUTPUT_LINE.match(line) for line in lines)
    assert result.stdout.splitlines()[-1] == ("design-check: 1 files scanned, 0 errors, 1 warnings")

    card = 'export const Card = () => <div className="bg-gray-100">Card</div>;\n'
    (scratch_root / "frontend" / "src" / "Card.tsx").write_text(card, encoding="utf-8")
    result = _run("--root", str(scratch_root))

    assert result.returncode == 1
    lines = _finding_lines(result.stdout)
    assert f"frontend/src/Card.tsx:1:{card.index('bg-gray-100') + 1} DS-LINT-02 " in "\n".join(
        lines
    )
    assert all(OUTPUT_LINE.match(line) for line in lines)
    assert result.stdout.splitlines()[-1] == ("design-check: 2 files scanned, 1 errors, 1 warnings")


def test_path_scoped_rules(module: ModuleType) -> None:
    to_fixed = "export const f = (n: number) => n.toFixed(2);\n"
    assert _rules(module, "frontend/src/lib/format/money.ts", to_fixed) == set()
    assert _rules(module, "frontend/src/app/total.ts", to_fixed) == {("DS-LINT-09", 1)}

    test_file = 'const tone = "#fff";\nconst s = (1).toFixed(2);\nconst d = new Date(value);\n'
    assert _rules(module, "frontend/src/app/total.test.ts", test_file) == {("DS-LINT-23", 3)}

    phosphor = 'export { House } from "@phosphor-icons/react";\n'
    assert _rules(module, "frontend/src/components/icons/registry.ts", phosphor) == set()
    assert _rules(module, "frontend/src/app/Nav.tsx", phosphor) == {("DS-LINT-07", 1)}

    sparkle = 'import { Sparkle } from "../icons/registry";\n'
    assert _rules(module, "frontend/src/components/ai/Proposal.tsx", sparkle) == set()
    assert _rules(module, "frontend/src/components/data/Grid.tsx", sparkle) == {("DS-LINT-07", 1)}

    bars = 'import { BarChart } from "recharts";\n'
    assert _rules(module, "frontend/src/components/charts/Bars.tsx", bars) == set()
    assert _rules(module, "frontend/src/app/Bars.tsx", bars) == {("DS-LINT-08", 1)}


def test_repository_frontend_src_is_clean() -> None:
    result = _run()

    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines()[-1].endswith(" 0 errors, 0 warnings")
