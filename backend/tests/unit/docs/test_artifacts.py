"""Release artefact presence (BUILD_SPEC DEP-8; PHASES BS-D-13; dev-guide §1.1; D-75).

The documents a release ships, the licence and the third-party notices, and the README's pointers
to the developer guide and the guides. The OpenAPI currency check (``make openapi`` leaving the
tree unchanged) is ``scripts/openapi_check.sh`` under ``make lint`` (see
tests/unit/test_openapi_export.py); ``make release-manifest`` is exercised by
tests/unit/test_makefile_targets.py.

This module sits at the path DEP-8 and BS4-D-17 name (``backend/tests/unit/docs/``); lane OPS
moved it here unchanged from ``tests/unit/test_artifacts.py`` (package of 2026-09-29).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DOCUMENTS = (
    "docs/guides/runbook.md",
    "docs/guides/user-guide.md",
    "docs/guides/migration-guide.md",
    "docs/guides/itgc-guide.md",
    "docs/security/threat-model.md",
    "docs/security/ASVS-L2.md",
    "docs/security/SUBPROCESSORS.md",
    "docs/security/DPA-TEMPLATE.md",
)
# Third-party notices owed by the dependency set of this tree (dev-guide §1.1 NOTICE line):
# psycopg 3 (LGPL-3.0) with the libpq the binary wheel bundles, and the two OFL 1.1 fonts.
NOTICES = (
    ("psycopg", "LGPL-3.0", "libpq"),
    ("Inter", "OFL-1.1", None),
    ("JetBrains Mono", "OFL-1.1", None),
)
# BUILD_SPEC DEP-8 also lists anthropic (MIT) and pypdf (BSD-3-Clause); neither is a dependency of
# this tree (backend/uv.lock, frontend/package-lock.json), so no notice is owed for them today.
# The moment one is locked, NOTICE must name it.
CONDITIONAL_NOTICES = (("anthropic", "MIT"), ("pypdf", "BSD-3-Clause"))
LOCKS = ("backend/uv.lock", "frontend/package-lock.json")
README_LINKS = (
    "docs/dev-guide.md",
    "docs/guides/runbook.md",
    "docs/guides/user-guide.md",
    "docs/guides/migration-guide.md",
    "docs/guides/itgc-guide.md",
    "docs/security/threat-model.md",
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _notice_entry(notice: str, component: str) -> str:
    """The paragraph of NOTICE that starts with the component's name."""
    blocks = [block for block in notice.split("\n\n") if block.startswith(component)]
    assert len(blocks) == 1, (component, len(blocks))
    return blocks[0]


def test_bs_d_13_documents_present() -> None:
    for path in DOCUMENTS:
        file = ROOT / path
        assert file.is_file(), path
        text = file.read_text(encoding="utf-8")
        assert text.strip(), f"{path} is empty"
        assert text.lstrip().startswith("# "), f"{path} does not start with a level-1 heading"


def test_licence_and_notice() -> None:
    licence = _read("LICENSE")
    assert licence.startswith("# PolyForm Noncommercial License 1.0.0")
    assert "## Noncommercial Purposes" in licence
    notice = _read("NOTICE")
    assert "Copyright (c) 2025-2026 ChipmunkRPA" in notice
    for component, licence_id, bundled in NOTICES:
        entry = _notice_entry(notice, component)
        assert licence_id in entry, (component, licence_id)
        if bundled:
            assert bundled in entry, (component, bundled)
    locked = "\n".join(_read(path) for path in LOCKS)
    for component, licence_id in CONDITIONAL_NOTICES:
        present = (
            re.search(rf'name = "{component}"', locked) or f'"node_modules/{component}"' in locked
        )
        if present:
            assert licence_id in _notice_entry(notice, component), component


def test_readme_quick_start_points_to_guides() -> None:
    readme = _read("README.md")
    assert readme.startswith("# eRev Cloud")
    assert "## Quick start" in readme
    for path in README_LINKS:
        assert f"]({path})" in readme, path
    assert "make setup" in readme and "make ci" in readme
