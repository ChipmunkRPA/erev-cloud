"""The pg test-support probe release (``support.rows.engine_release_values``) is a compliant
T-PLT-38 row under the REL-03 stamping rule (D-96 (3); team-lead ruling D-98 candidate 94,
2026-09-20).

Before this slice the probe carried its identity in the version string (``0.0.0-probe.<token>``);
once such a row is the latest ``engine_release`` of a shared test database, the next
``stamp_release`` (a world factory) takes the VERSION_CHANGE path and ``semver_level`` refuses the
non MAJOR.MINOR.PATCH version — the ``ReleaseManifestError`` seen in F-CTR's chain on main
316177c9. The stamping rule stays strict; the support becomes compliant. DB-free."""

from __future__ import annotations

import pytest
from erev_api.controls.validation_level import declared_validation_level, stamping_decision
from erev_engine import ENGINE_VERSION
from support.factories import RELEASE_BUILD
from support.rows import engine_release_values


def test_probe_release_is_a_compliant_previous_global_release() -> None:
    values = engine_release_values()
    version, build = str(values["engine_version"]), str(values["build_sha"])
    # A plain MAJOR.MINOR.PATCH version: the probe identity lives in build_sha and the
    # schema_revision marker, never in the version string.
    assert "probe" not in version and version.count(".") == 2
    assert all(part.isdigit() for part in version.split("."))
    assert build.startswith("probe-") and values["schema_revision"] == "probe"
    # The row's declaration is a valid REL-01 level.
    assert declared_validation_level(values).level == "PATCH"
    # The stamp that follows a probe insert in a shared database — the world factories' undeclared
    # PATCH of ENGINE_VERSION with a new build — is recorded, not refused: the probe shares the
    # running engine version, so the path is SAME_VERSION_REBUILD (no floor); a restart is RESTART.
    decision = stamping_decision(
        "PATCH",
        previous=(version, build),
        candidate=(ENGINE_VERSION, RELEASE_BUILD),
        row_exists=False,
    )
    assert decision.path == "SAME_VERSION_REBUILD"
    restart = stamping_decision(
        "PATCH",
        previous=(version, build),
        candidate=(ENGINE_VERSION, RELEASE_BUILD),
        row_exists=True,
    )
    assert restart.path == "RESTART"
    # Two probe rows are distinct T-PLT-38 pairs (ux_engine_release__version).
    other = engine_release_values()
    assert (other["engine_version"], other["build_sha"]) != (version, build)


def test_a_lower_plain_version_would_be_refused_by_the_floor() -> None:
    """Why the probe shares ENGINE_VERSION rather than e.g. ``0.0.0``: a version-changing new row
    must declare at least the semver floor, and the world factories stamp an undeclared PATCH."""
    with pytest.raises(ValueError, match="below the semver floor"):
        stamping_decision(
            "PATCH",
            previous=("0.0.0", "probe-x"),
            candidate=(ENGINE_VERSION, RELEASE_BUILD),
            row_exists=False,
        )
