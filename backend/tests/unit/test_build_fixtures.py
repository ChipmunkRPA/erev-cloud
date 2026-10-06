"""scripts/build_fixtures.py contract (docs/dev-guide.md DG-PAR-02, DG-MK-fixtures, DG-GIT-04;
BUILD_SPEC FND-17)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build_fixtures.py"
FIXTURES = ROOT / "backend" / "tests" / "fixtures"
GOLDEN = ROOT / "docs" / "legacy" / "golden"
MAX_BYTES = 5 * 1024 * 1024
ENTRY_KEYS = {"path", "sha256", "bytes", "source"}
PROBE_INPUTS = {
    "P1 progress 1.31.2023 - Memo 3 blank on Contract 1 POB #2 and POB #3.xlsx",
    "P2 no-op prospective mod - Contract 1 POB #1 qty 0 billing 0.xlsx",
    "P3 progress 1.31.2023 - Contract 1 POB #1 over-delivered.xlsx",
}
SSP_WORKBOOK = "legacy_uat/01-ssp-upload/SKU SSP Template.xlsx"
PROBE_P3 = "legacy_probes/P3 progress 1.31.2023 - Contract 1 POB #1 over-delivered.xlsx"


@pytest.fixture(scope="module")
def module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_fixtures", SCRIPT)
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


def _env() -> dict[str, str]:
    prefixes = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "PYTEST_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(prefixes)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(a) for a in args)],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _manifest(fixtures: Path = FIXTURES) -> list[dict[str, object]]:
    data = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data


def _file_times(root: Path) -> dict[str, int]:
    return {
        p.relative_to(root).as_posix(): p.stat().st_mtime_ns
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _contents(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _copy_fixtures(scratch: Path) -> Path:
    copy = scratch / "fixtures"
    shutil.copytree(FIXTURES, copy)
    return copy


def _sources_from_fixtures(module: ModuleType, scratch: Path) -> tuple[Path, Path]:
    """A harness and legacy root holding the committed bytes at each first candidate path."""
    harness, legacy = scratch / "harness", scratch / "legacy"
    for item in module.plan(GOLDEN, harness, legacy):
        source = item.candidates[0]
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURES / item.path, source)
    return harness, legacy


def _pycache_dirs(module: ModuleType) -> set[Path]:
    found: set[Path] = set()
    for root in (module.DEFAULT_HARNESS, module.DEFAULT_LEGACY):
        for directory, subdirs, _ in os.walk(root):
            found.update(Path(directory) / d for d in subdirs if d == "__pycache__")
    return found


def test_dg_par_02_manifest_lists_18_files() -> None:
    entries = _manifest()
    assert len(entries) == 18
    assert all(set(entry) == ENTRY_KEYS for entry in entries)
    by_path = {str(entry["path"]): entry for entry in entries}
    assert [entry["path"] for entry in entries] == sorted(by_path)

    steps = []
    for step_file in sorted(GOLDEN.glob("*/step.json")):
        step = json.loads(step_file.read_text(encoding="utf-8"))
        if step_file.parent.name[:2] in {f"{n:02d}" for n in range(1, 15)}:
            steps.append((step_file.parent.name, step["file"], step["file_sha256"]))
    assert len(steps) == 14
    for directory, file, digest in steps:
        entry = by_path[f"legacy_uat/{directory}/{Path(file).name}"]
        assert entry["sha256"] == digest
        assert entry["source"] == f"legacy:{file}"

    probes = {path.split("/", 1)[1] for path in by_path if path.startswith("legacy_probes/")}
    assert probes == PROBE_INPUTS
    assert by_path[SSP_WORKBOOK]["sha256"] == (
        "05c40a29f350b2fb71530b8136b12ab97458ddd0c950bd43c6cdd0b5b9e390c4"
    )
    assert by_path["legacy_uat/14-full-delivery-2023-10-31/Full delivery 10.31.2023.xlsx"][
        "sha256"
    ] == ("3d7de60f9fb76b3d3ddf37c9e41204bf139de67c222cd54473ffcea4d332295c")
    golden_manifest = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
    database = by_path["legacy_db/ASC606-shipped-step04.db"]
    assert database["sha256"] == golden_manifest["shipped_db_sha256"]
    assert len(by_path) == 14 + 3 + 1


def test_check_mode_writes_nothing_and_detects_tamper(scratch_dir: Path) -> None:
    before = _file_times(FIXTURES)
    result = subprocess.run(
        ["make", "--no-print-directory", "fixtures", "CHECK=1"],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "OK fixtures"
    assert _file_times(FIXTURES) == before

    copy = _copy_fixtures(scratch_dir)
    tampered = copy / SSP_WORKBOOK
    data = bytearray(tampered.read_bytes())
    data[len(data) // 2] ^= 0xFF
    tampered.write_bytes(bytes(data))
    result = _run("--check", "--fixtures", copy)
    assert result.returncode == 1
    failures = [line for line in result.stdout.splitlines() if line.startswith("FAIL")]
    assert len(failures) == 1
    assert SSP_WORKBOOK in failures[0]


def test_refuses_to_overwrite_committed_fixture(module: ModuleType, scratch_dir: Path) -> None:
    harness, legacy = _sources_from_fixtures(module, scratch_dir)
    probe_source = harness / "out" / "probes" / "inputs" / PROBE_P3.split("/", 1)[1]
    probe_source.write_bytes(probe_source.read_bytes() + b"\0")
    copy = _copy_fixtures(scratch_dir)
    (copy / SSP_WORKBOOK).unlink()  # a missing fixture must not be written by a failing run
    before_times, before_bytes = _file_times(copy), _contents(copy)

    result = _run("--harness", harness, "--legacy", legacy, "--fixtures", copy)

    assert result.returncode == 1
    assert "refusing to overwrite a committed fixture with different bytes" in result.stdout
    assert PROBE_P3 in result.stdout
    assert _file_times(copy) == before_times
    assert _contents(copy) == before_bytes


def test_rebuild_from_sources_reproduces_manifest(module: ModuleType, scratch_dir: Path) -> None:
    harness, legacy = _sources_from_fixtures(module, scratch_dir)
    target = scratch_dir / "rebuilt"
    result = _run("--harness", harness, "--legacy", legacy, "--fixtures", target)
    assert result.returncode == 0, result.stdout
    assert (target / "manifest.json").read_bytes() == (FIXTURES / "manifest.json").read_bytes()
    assert _run("--check", "--fixtures", target).returncode == 0


def test_missing_source_blocked_message(module: ModuleType, scratch_dir: Path) -> None:
    empty = scratch_dir / "empty"
    empty.mkdir()
    target = scratch_dir / "fixtures"

    result = _run("--harness", empty, "--legacy", empty, "--fixtures", target)

    assert result.returncode == 1
    planned = module.plan(GOLDEN, empty, empty)
    assert len(planned) == 18
    for item in planned:
        expected = f"BLOCKED: legacy fixture {module._display(target / item.path)} unavailable"
        assert expected in result.stdout.splitlines()
    assert not target.exists() or not any(p.is_file() for p in target.rglob("*"))


def test_builder_never_imports_legacy_code(
    module: ModuleType, scratch_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    caches_before = _pycache_dirs(module)
    copy = _copy_fixtures(scratch_dir)

    exit_code = module.main(["--fixtures", str(copy)])

    assert exit_code == 0, capsys.readouterr().out
    assert "eRev" not in sys.modules
    roots = (module.DEFAULT_HARNESS.resolve(), module.DEFAULT_LEGACY.resolve())
    for loaded in list(sys.modules.values()):
        origin = getattr(loaded, "__file__", None)
        if origin:
            assert not Path(origin).resolve().is_relative_to(roots[0])
            assert not Path(origin).resolve().is_relative_to(roots[1])
    assert _pycache_dirs(module) == caches_before
    assert (copy / "manifest.json").read_bytes() == (FIXTURES / "manifest.json").read_bytes()


def test_dg_git_04_fixture_size_limit() -> None:
    files = [p for p in FIXTURES.rglob("*") if p.is_file()]
    assert len(files) >= 19  # 18 fixtures and the manifest
    for file in files:
        assert file.stat().st_size <= MAX_BYTES, file
    for entry in _manifest():
        assert isinstance(entry["bytes"], int) and entry["bytes"] <= MAX_BYTES
