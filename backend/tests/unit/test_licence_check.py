"""scripts/licence_check.py contract (docs/dev-guide.md DG-MK-licence-check; REQ-SEC-010; BUILD_SPEC
FND-16)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "licence_check.py"
ALLOWED = {
    "MIT",
    "MIT-0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
    "ISC",
    "PSF-2.0",
    "MPL-2.0",
    "OFL-1.1",
}
NOTICE_WITH_PSYCOPG = "psycopg 3\n  Licence: LGPL-3.0\n"
NOTICE_WITHOUT_PSYCOPG = "Inter\n  Licence: OFL-1.1\n"


@pytest.fixture(scope="module")
def module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("licence_check", SCRIPT)
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


def _run_packages(
    scratch: Path, packages: list[dict[str, object]], *, notice: str, allowlist: str = ""
) -> subprocess.CompletedProcess[str]:
    (scratch / "packages.json").write_text(json.dumps(packages), encoding="utf-8")
    (scratch / "NOTICE").write_text(notice, encoding="utf-8")
    (scratch / "allow.toml").write_text(allowlist, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--packages",
            str(scratch / "packages.json"),
            "--notice",
            str(scratch / "NOTICE"),
            "--allowlist",
            str(scratch / "allow.toml"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _package(name: str, **metadata: object) -> dict[str, object]:
    return {"ecosystem": "python", "name": name, "version": "1.0.0", **metadata}


def _entry(name: str, licence: str, source: str | None) -> str:
    source_line = f'source = "{source}"\n' if source is not None else ""
    return (
        f'[[package]]\necosystem = "python"\nname = "{name}"\nlicence = "{licence}"\n'
        f'{source_line}reason = "wheel for another platform"\n'
    )


def test_req_sec_010_rejects_disallowed_licence(module: ModuleType, scratch_dir: Path) -> None:
    assert module.ALLOWED == ALLOWED
    ok = _package("clean", expression="MIT")

    # A GPL-3.0 runtime package fails the run and is named.
    result = _run_packages(
        scratch_dir, [ok, _package("copyleft", expression="GPL-3.0-only")], notice=""
    )
    assert result.returncode == 1
    assert "python:copyleft@1.0.0 LICENCE GPL-3.0: not on the REQ-SEC-010 allow-list" in (
        result.stdout
    )
    assert "clean" not in result.stdout.split("licence-check:")[0]

    # LGPL-3.0 passes for psycopg and psycopg-binary only while NOTICE names psycopg.
    lgpl = [
        _package("psycopg", expression="LGPL-3.0-only"),
        _package(
            "psycopg-binary",
            classifiers=[
                "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)"
            ],
        ),
    ]
    assert _run_packages(scratch_dir, lgpl, notice=NOTICE_WITH_PSYCOPG).returncode == 0
    without_notice = _run_packages(scratch_dir, lgpl, notice=NOTICE_WITHOUT_PSYCOPG)
    assert without_notice.returncode == 1
    assert "python:psycopg@1.0.0 LICENCE LGPL-3.0: LGPL-3.0 needs the psycopg entry in NOTICE" in (
        without_notice.stdout
    )
    other = _run_packages(
        scratch_dir, [_package("libother", expression="LGPL-3.0")], notice=NOTICE_WITH_PSYCOPG
    )
    assert other.returncode == 1
    assert "python:libother@1.0.0 LICENCE LGPL-3.0: not on the REQ-SEC-010 allow-list" in (
        other.stdout
    )

    # A package without metadata passes only with an entry holding a licence and a source URL.
    bare = [_package("platform-only")]
    missing = _run_packages(scratch_dir, bare, notice="")
    assert missing.returncode == 1
    assert "python:platform-only@1.0.0 LICENCE missing: no licence metadata" in missing.stdout
    url = "https://example.org/platform-only/LICENSE"
    listed = _run_packages(
        scratch_dir, bare, notice="", allowlist=_entry("platform-only", "MIT", url)
    )
    assert listed.returncode == 0, listed.stdout
    assert "1 packages (1 python, 0 npm), 1 allow-listed, 0 findings" in listed.stdout
    no_source = _run_packages(
        scratch_dir, bare, notice="", allowlist=_entry("platform-only", "MIT", None)
    )
    assert no_source.returncode == 1
    assert "licence-check allow-list:" in no_source.stdout
    not_url = _run_packages(
        scratch_dir, bare, notice="", allowlist=_entry("platform-only", "MIT", "verified")
    )
    assert not_url.returncode == 1
    assert "source must be an https URL" in not_url.stdout
    # An entry cannot admit a disallowed licence, and an entry naming no dependency fails.
    gpl_entry = _run_packages(
        scratch_dir, bare, notice="", allowlist=_entry("platform-only", "GPL-3.0", url)
    )
    assert gpl_entry.returncode == 1
    assert "LICENCE GPL-3.0: not on the REQ-SEC-010 allow-list" in gpl_entry.stdout
    stale = _run_packages(scratch_dir, [ok], notice="", allowlist=_entry("gone", "MIT", url))
    assert stale.returncode == 1
    assert "entry for python:gone names no dependency" in stale.stdout


def test_licence_resolution_rules(module: ModuleType) -> None:
    def resolved(**metadata: object) -> str | None:
        node = module.resolve(module.Package("python", "x", "1", **metadata))
        return None if node is None else str(module.render(node))

    assert resolved(expression="Apache-2.0 OR BSD-3-Clause") == "Apache-2.0 OR BSD-3-Clause"
    assert (
        resolved(expression="MIT AND (PSF-2.0 OR Apache-2.0)") == "MIT AND (PSF-2.0 OR Apache-2.0)"
    )
    assert resolved(expression="GPL-2.0-or-later WITH Classpath-exception-2.0") == "GPL-2.0"
    assert resolved(licence_text="ISC License") == "ISC"
    # defusedxml 0.7.1 publishes `License: PSFL` (PSF Licence Agreement v2).
    assert resolved(licence_text="PSFL") == "PSF-2.0"
    assert (
        resolved(licence_text="x" * 200, classifiers=("License :: OSI Approved :: MIT License",))
        == "MIT"
    )
    # Family classifiers without a version resolve nothing.
    assert resolved(classifiers=("License :: OSI Approved :: BSD License",)) is None
    assert resolved(expression="MIT OR (") is None

    def allowed(expression: str, name: str = "x", notice: bool = True) -> bool:
        node = module.parse_expression(expression)
        return bool(module.is_allowed(node, name, notice_names_psycopg=notice))

    assert allowed("MIT OR GPL-3.0")
    assert not allowed("MIT AND GPL-3.0")
    assert allowed("LGPL-3.0-only", "psycopg-binary")
    assert not allowed("LGPL-3.0-only", "psycopg-binary", notice=False)
    # PLF-9: the psycopg project's pool shares the psycopg entry.
    assert allowed("LGPL-3.0-only", "psycopg-pool")
    assert not allowed("LGPL-3.0-only", "psycopg-pool", notice=False)


def test_repository_dependencies_pass(
    module: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    # In process, so the session socket guard (DG-TST-15) covers the metadata reads; uv and npm
    # run with --offline.
    assert module.main([]) == 0
    output = capsys.readouterr().out
    summary = re.search(
        r"licence-check: (\d+) packages \((\d+) python, (\d+) npm\), (\d+) allow-listed, "
        r"0 findings, 0 allow-list errors",
        output,
    )
    assert summary is not None, output
    python_count, npm_count = int(summary.group(2)), int(summary.group(3))
    assert python_count > 0 and npm_count > 0
    names = {package.name for package in module.python_packages(ROOT)}
    assert {"psycopg", "psycopg-binary", "fastapi", "sqlalchemy"} <= names
    assert "erev-backend" not in names
    npm_names = {package.name for package in module.npm_packages(ROOT)}
    assert {"react", "react-dom", "react-router"} <= npm_names
    assert "vite" not in npm_names  # dev dependencies are out of scope
