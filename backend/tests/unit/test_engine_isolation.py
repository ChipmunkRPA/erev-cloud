"""DG-TST-18 engine isolation at collection (docs/dev-guide.md §9.3; BUILD_SPEC EKC-7a, FR-C-01)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

import pytest

ENGINE_CONFTEST: Final = Path(__file__).resolve().parents[1] / "engine" / "conftest.py"
DATABASE_FIXTURES: Final = ("db", "committed_db", "test_database")
# Stand-ins for the database fixtures; each leaves a marker file when it is set up.
STUB_CONFTEST: Final = (
    "from pathlib import Path\n\nimport pytest\n\nROOT = Path(__file__).parent\n"
    + "".join(
        f"\n\n@pytest.fixture\ndef {name}():\n    (ROOT / '{name}.marker').write_text('set up')\n"
        for name in DATABASE_FIXTURES
    )
)


def _probe(pytester: pytest.Pytester, area: str, fixture: str | None) -> pytest.RunResult:
    directory = pytester.path / area
    directory.mkdir(exist_ok=True)
    shutil.rmtree(directory / "__pycache__", ignore_errors=True)
    (directory / "test_probe.py").write_text(
        f"def test_probe({fixture or ''}):\n    assert True\n", encoding="utf-8"
    )
    return pytester.runpytest_subprocess(f"{area}/test_probe.py", "-p", "no:cacheprovider")


def test_dg_tst_18_engine_test_requesting_database_fixture_fails(pytester: pytest.Pytester) -> None:
    pytester.makeini("[pytest]\n")
    pytester.makeconftest(STUB_CONFTEST)
    (pytester.path / "engine").mkdir()
    (pytester.path / "engine" / "conftest.py").write_bytes(ENGINE_CONFTEST.read_bytes())

    for fixture in DATABASE_FIXTURES:
        result = _probe(pytester, "engine", fixture)
        assert result.ret != pytest.ExitCode.OK
        output = result.stdout.str() + result.stderr.str()
        assert "DG-TST-18" in output, output
        assert fixture in output
        assert not list(pytester.path.glob("*.marker"))

    clean = _probe(pytester, "engine", None)
    assert clean.ret == pytest.ExitCode.OK, clean.stdout.str() + clean.stderr.str()
    unit = _probe(pytester, "unit", "db")
    assert unit.ret == pytest.ExitCode.OK, unit.stdout.str() + unit.stderr.str()
