"""Operational guides contract, foundation part (PHASES BS-D-13; docs/dev-guide.md DG-LAY-01,
DG-DONE-07; BUILD_SPEC FND-18, FR-M-03, FR-M-04).

This module stays at the path FND-18 and the FR-M items name. The DEP-6, DEP-7, DMO-11 and PRF-6
tests, which BS4-D-17 and those items place in ``backend/tests/unit/docs/test_guides.py``, live
there (moved unchanged by lane OPS, package of 2026-09-29). Shared readers: ``support.guides``."""

from __future__ import annotations

from support.architecture import (
    DATABASE_ADMINISTRATION_OBJECTS,
    DATABASE_ADMINISTRATION_SERVER_STATEMENT,
    DATABASE_ADMINISTRATION_VERBS,
)
from support.guides import GUIDES, HEADING
from support.guides import headings as _headings
from support.guides import section as _section

REQUIRED_HEADINGS = {
    "runbook.md": ("Start and stop by PID files", "Migrations", "erev doctor", "Job monitoring"),
    "user-guide.md": ("Vocabulary", "Money and dates on the wire"),
    "migration-guide.md": ("Legacy fixtures and provenance",),
    "itgc-guide.md": ("Database roles and prerequisites", "Deployment self-check"),
}


def _series(items: tuple[str, ...], *, code: bool) -> str:
    words = [f"`{item}`" if code else item.lower() for item in items]
    return ", ".join(words[:-1]) + f" or {words[-1]}"


def test_dg_env_14_itgc_guide_matches_enforced_rule() -> None:
    section = _section("itgc-guide.md", "Database roles and prerequisites")
    assert "DG-ENV-14" in section and "DG-ARC-05" in section
    rule = (
        f"{_series(DATABASE_ADMINISTRATION_VERBS, code=True)} of a "
        f"{_series(DATABASE_ADMINISTRATION_OBJECTS, code=False)}, "
        f"plus `{DATABASE_ADMINISTRATION_SERVER_STATEMENT}`"
    )
    sentences = [sentence for sentence in section.split(". ") if "build fails" in sentence]
    assert len(sentences) == 1, sentences
    assert rule in sentences[0], (rule, sentences[0])


def test_rb_02_failed_migration_rollback_is_clone_and_cutover() -> None:
    section = _section("runbook.md", "Migrations")
    hosted = _section("runbook.md", "Hosted deployments")
    assert hosted in section
    assert "clone and cutover (05 OPR-11)" in hosted
    assert "pre-migration backup point (05 OPR-16)" in hosted
    assert "never restored in place" in hosted
    assert "restoring that backup" not in section


def test_bs_d_13_guides_exist_with_sections() -> None:
    for name, required in REQUIRED_HEADINGS.items():
        path = GUIDES / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        first_line = next(line for line in text.splitlines() if line.strip())
        assert HEADING.match(first_line) and first_line.startswith("# "), name
        titles = {title for level, title in _headings(text) if level >= 2}
        for heading in required:
            assert heading in titles, f"{name}: {heading}"
