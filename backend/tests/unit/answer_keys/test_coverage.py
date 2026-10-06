"""Answer-key corpus coverage (docs/dev-guide.md §9.5.8 DG-AK-33; docs/03-REQUIREMENTS.md §12;
BUILD_SPEC EKC-10)."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from support.answer_keys.loader import (
    COVERAGE_HEADING,
    REPO_ROOT,
    REQUIREMENTS_DOC,
    CoverageCount,
    CoverageReport,
    LoadedKey,
    coverage,
    load_all,
)


@pytest.fixture(scope="module")
def corpus() -> list[LoadedKey]:
    return load_all()


@pytest.fixture
def scratch_root() -> Iterator[Path]:
    base = REPO_ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="coverage-", dir=base))
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _without(corpus: list[LoadedKey], drop: Callable[[LoadedKey], bool]) -> list[LoadedKey]:
    kept = [item for item in corpus if not drop(item)]
    assert len(kept) < len(corpus)
    return kept


def _gap_subjects(report: CoverageReport) -> list[str]:
    return [gap.subject for gap in report.gaps]


def _register_copy(root: Path, replace: str, by: str) -> Path:
    text = REQUIREMENTS_DOC.read_text(encoding="utf-8")
    assert text.count(replace) == 1
    copy = root / "03-REQUIREMENTS.md"
    copy.write_text(text.replace(replace, by), encoding="utf-8")
    return copy


def test_corpus_has_zero_gaps(corpus: list[LoadedKey]) -> None:
    report = coverage(corpus)
    assert report.gaps == ()
    assert report.ok
    assert dict(report.counts) == {
        "List A": CoverageCount(49, 49),
        "List B": CoverageCount(46, 46),
        "List C": CoverageCount(76, 76),
        "AK: hints": CoverageCount(50, 50),
        "AK-FAM: slugs": CoverageCount(9, 9),
        "family codes": CoverageCount(28, 28),
    }
    assert COVERAGE_HEADING not in report.render()
    assert report.render().startswith("Corpus coverage: List A 49 of 49; List B 46 of 46;")


def test_each_gap_kind_is_reported(corpus: list[LoadedKey], scratch_root: Path) -> None:
    agent = {"POB-S2-EX45-AGENT-AGENT", "POB-S2-EX45-AGENT-PRINCIPAL"}
    report = coverage(_without(corpus, lambda item: item.key.id in agent))
    assert "AK:S2-EX45-AGENT" in _gap_subjects(report)
    hint = next(gap for gap in report.gaps if gap.subject == "AK:S2-EX45-AGENT")
    assert "REQ-POB-009" in hint.requirements
    assert "REQ-POB-009" in hint.message
    assert report.counts["AK: hints"] == CoverageCount(49, 50)
    assert report.render().splitlines()[2] == COVERAGE_HEADING

    rollover = _without(corpus, lambda item: "usage-rollover" in item.key.tags)
    assert len(corpus) - len(rollover) == 3
    report = coverage(rollover)
    assert "AK-FAM:usage-rollover" in _gap_subjects(report)
    assert report.counts["AK-FAM: slugs"] == CoverageCount(8, 9)

    report = coverage(_without(corpus, lambda item: "ROY" in item.key.families))
    assert "ROY" in _gap_subjects(report)
    assert report.counts["family codes"] == CoverageCount(27, 28)

    report = coverage(_without(corpus, lambda item: item.key.id == "VC-CHK-110"))
    assert _gap_subjects(report) == ["CHK-110"]
    assert report.counts["List C"] == CoverageCount(75, 76)
    assert f"{COVERAGE_HEADING}\n- List C CHK-110:" in report.render()

    condition = "`families` contains `IFRS` (book-difference behaviour, POLICIES §0.7 and §6.2)"
    register = _register_copy(scratch_root, condition, "any key computed in the IFRS15 book")
    report = coverage(corpus, requirements_doc=register)
    assert [gap.message for gap in report.gaps] == ["unparsed coverage row COV-B-46"]
    assert report.counts["List B"] == CoverageCount(45, 46)


def test_withdrawn_key_does_not_cover() -> None:
    # ER-G-05 (b): coverage counts active keys only (DG-AK-13, DG-AK-33).
    every = load_all(include_withdrawn=True)
    # 243 + eight ENG-D1 + three ENG-C6 keys (D-91, D-97) + one of R-116 (a)
    assert len(every) == 255
    assert coverage(every).gaps == ()
    flipped = [
        LoadedKey(item.key.model_copy(update={"status": "withdrawn"}), item.path, item.sha256)
        if item.key.id == "VC-CHK-110"
        else item
        for item in every
    ]
    assert sum(item.key.status == "withdrawn" for item in flipped) == 3
    assert _gap_subjects(coverage(flipped)) == ["CHK-110"]


def test_coverage_parses_register_at_run_time(corpus: list[LoadedKey], scratch_root: Path) -> None:
    last_row = "| COV-A-49 | D12 | WM-08 | Taxes and fees gross or net |"
    extra = f"{last_row}\n| COV-A-99 | D12 | XX-99 | Extra scenario |"
    register = _register_copy(scratch_root, last_row, extra)
    assert register.is_relative_to(REPO_ROOT / ".run" / "tmp")
    report = coverage(corpus, requirements_doc=register)
    assert _gap_subjects(report) == ["COV-A-99"]
    assert report.gaps[0].message == (
        "COV-A-99: no active key whose derived_from.research05 contains XX-99"
    )
    assert report.counts["List A"] == CoverageCount(49, 50)
    assert coverage(corpus).ok
