"""DG-ARC-10: ``controls.yaml`` equals docs/03-REQUIREMENTS.md §4.1 (BUILD_SPEC FND-12).

The register is read read-only. Phases come from docs/build-spec/PHASES.md §7 and the CTL-022 impact
globs from the docs/05-ARCHITECTURE.md REL-04 example.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from erev_api.controls.registry import RELEASE, load_controls

ROOT: Final = Path(__file__).resolve().parents[3]
REQUIREMENTS: Final = ROOT / "docs" / "03-REQUIREMENTS.md"
PHASES: Final = ROOT / "docs" / "build-spec" / "PHASES.md"
ARCHITECTURE: Final = ROOT / "docs" / "05-ARCHITECTURE.md"
TOP_LEVEL_SOURCES: Final = ("backend/", "scripts/")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _control_rows(path: Path, start: str, end: str) -> list[list[str]]:
    block = _between(path.read_text(encoding="utf-8"), start, end)
    return [_cells(line) for line in block.splitlines() if line.startswith("| CTL-")]


def _listed(cell: str) -> tuple[str, ...]:
    return () if cell == "none" else tuple(part.strip() for part in cell.split(","))


def test_dg_arc_10_ids_and_titles_equal_register() -> None:
    controls = load_controls()
    register = _control_rows(REQUIREMENTS, "### 4.1 Designated controls", "### 4.2 ")
    phases = _control_rows(PHASES, "## 7. Controls by phase", "## 8. ")

    expected_ids = [f"CTL-{number:03d}" for number in range(1, 50)]
    assert [control.id for control in controls] == expected_ids
    assert [row[0] for row in register] == expected_ids
    assert {control.id: control.title for control in controls} == {
        row[0]: row[1] for row in register
    }
    assert {control.id: control.phase for control in controls} == {row[0]: row[4] for row in phases}
    assert {control.release for control in controls} == {RELEASE}


def test_register_columns_equal_register() -> None:
    register = {
        row[0]: row
        for row in _control_rows(REQUIREMENTS, "### 4.1 Designated controls", "### 4.2 ")
    }
    for control in load_controls():
        _, _, catalogue, feature, kind, reqs, evidence = register[control.id]
        assert control.r07_catalogue_id == catalogue, control.id
        assert control.r07_feature == _listed(feature), control.id
        assert control.type == kind, control.id
        assert control.reqs == _listed(reqs), control.id
        assert control.evidence == evidence, control.id


def test_impact_paths_are_repository_globs() -> None:
    controls = {control.id: control for control in load_controls()}
    for control in controls.values():
        assert control.impact_paths, control.id
        for path in control.impact_paths:
            assert path.startswith(TOP_LEVEL_SOURCES), (control.id, path)
            assert ".." not in path.split("/"), (control.id, path)

    rel_04 = next(
        line
        for line in ARCHITECTURE.read_text(encoding="utf-8").splitlines()
        if line.startswith("| REL-04 |")
    )
    example = re.findall(r"`([^`]+)`", rel_04.split("for example CTL-022 declares", 1)[1])
    assert controls["CTL-022"].impact_paths == tuple(example)
