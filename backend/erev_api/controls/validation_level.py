"""Release validation level: the REL-01 manifest key, the T-PLT-38 column contract and the semver
floor (05 REL-06; 04 T-PLT-38 rev 1.13 pending column; D-96 (3); lane P5, ruled owner 2026-09-19).

Kernel module (DG-LAY-03 ``controls``): ``domain.contracts.release_validation`` imports
``semver_level`` from here; nothing here imports the domain layer. Pure: the manifest is a mapping,
the column is a contract tuple that Alembic revision 0055 implements (04 rev 1.29,
§18 rule 9), and ``stamping_decision`` is the rule ``controls.release.stamp_release`` applies
(integration slice 1, 2026-09-19).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

__all__ = [
    "LEVELS",
    "SAME_VERSION_REBUILD",
    "T_PLT_38_VALIDATION_LEVEL",
    "VALIDATION_LEVEL_KEY",
    "DeclaredLevel",
    "Level",
    "PreparationRow",
    "StampingDecision",
    "StampingPath",
    "check_declaration",
    "declared_validation_level",
    "parse_engine_version",
    "semver_level",
    "stamping_decision",
    "with_validation_level",
]

Level = Literal["PATCH", "MINOR", "MAJOR"]
LEVELS: Final[tuple[Level, ...]] = ("PATCH", "MINOR", "MAJOR")
_RANK: Final[Mapping[str, int]] = {"PATCH": 0, "MINOR": 1, "MAJOR": 2}
VALIDATION_LEVEL_KEY: Final = "validation_level"
# 04 T-PLT-38 rev 1.13 pending column, as the revision creates it: (name, type, default, check).
T_PLT_38_VALIDATION_LEVEL: Final = (
    "validation_level",
    "text",
    "PATCH",
    "CHECK (validation_level IN ('PATCH','MINOR','MAJOR'))",
)


def _parse(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"{version!r} is not a MAJOR.MINOR.PATCH engine version (DG-ENG-10)")
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def parse_engine_version(version: str) -> tuple[int, int, int]:
    """``(major, minor, patch)`` of a DG-ENG-10 engine version; ``ValueError`` for anything else —
    including a 40-hex build sha, so a swapped ``(engine_version, build_sha)`` pair is refused."""
    return _parse(version)


def semver_level(from_version: str, to_version: str) -> Level:
    """The transition level the version digits imply; a downgrade or an equal version raises."""
    source, target = _parse(from_version), _parse(to_version)
    if target <= source:
        raise ValueError(f"{to_version} does not follow {from_version}")
    if target[0] != source[0]:
        return "MAJOR"
    if target[1] != source[1]:
        return "MINOR"
    return "PATCH"


@dataclass(frozen=True, slots=True)
class DeclaredLevel:
    """The author's declaration read from the manifest; ``declared`` is False when the key is
    absent and the T-PLT-38 default ``PATCH`` applies (an undeclared release is recorded as
    such)."""

    level: Level
    declared: bool


def declared_validation_level(manifest: Mapping[str, object]) -> DeclaredLevel:
    """``validation_level`` of a REL-01 manifest: absent → ``PATCH`` undeclared; any other literal
    than PATCH / MINOR / MAJOR is malformed (the manifest stops the process at startup, REL-03)."""
    if VALIDATION_LEVEL_KEY not in manifest:
        return DeclaredLevel("PATCH", False)
    value = manifest[VALIDATION_LEVEL_KEY]
    if not isinstance(value, str) or value not in LEVELS:
        raise ValueError(f"{VALIDATION_LEVEL_KEY} is not one of {', '.join(LEVELS)}")
    level: Level = "PATCH" if value == "PATCH" else ("MINOR" if value == "MINOR" else "MAJOR")
    return DeclaredLevel(level, True)


def with_validation_level(manifest: Mapping[str, object], level: Level) -> dict[str, object]:
    """The manifest with the author's declaration set (the generator's helper; REL-01 key set)."""
    if level not in LEVELS:
        raise ValueError(f"{level!r} is not a validation level")
    return {**manifest, VALIDATION_LEVEL_KEY: level}


@dataclass(frozen=True, slots=True)
class PreparationRow:
    """The preparation artifact's binding (P5-PREP-R2; D-98 candidate REL-06-SAME-VERSION-REBUILD,
    supervisor): the artifact's own ``(engine_version, build_sha)``, the release row it is stamped
    as and the BASELINE row it binds — its **own** row — plus a typed authorization reference (a
    ticket / change reference recorded on the release row; never a live actor). Build facts are
    identity of the artifact only: they do **not** infer that the calculation code is byte-identical
    to the enabled release — that is the artifact author's declaration under DG-ENG-10, checked by
    the gates, not by this row."""

    engine_version: str
    build_sha: str
    preparation_release_id: UUID
    baseline_release_id: UUID
    authorization_ref: str

    def __post_init__(self) -> None:
        if not self.authorization_ref.strip():
            raise ValueError("a preparation row carries an authorization reference")
        if self.baseline_release_id != self.preparation_release_id:
            raise ValueError("the preparation artifact binds the BASELINE row of its own release")

    def covers(self, engine_version: str, build_sha: str | None) -> bool:
        return self.engine_version == engine_version and self.build_sha == build_sha


SAME_VERSION_REBUILD: Final = "REL-06-SAME-VERSION-REBUILD"


def check_declaration(
    declared: Level,
    *,
    previous_version: str | None,
    candidate_version: str,
    previous_build: str | None = None,
    candidate_build: str | None = None,
    preparation: PreparationRow | None = None,
) -> None:
    """D-96 (3): a declaration may exceed the digit-derived level (the 0.x changed-result case is
    declared MAJOR) but never fall below it; stamping refuses a declaration under the floor between
    the previous **global** release and the candidate (team-lead ruling (5), 2026-09-19: the
    per-tenant chain is evaluated at T-PLT-43 creation by ``effective_level``, not here). No
    previous release → nothing to compare.

    Same-version pairs (P5-PREP-R2; D-98 candidate REL-06-SAME-VERSION-REBUILD, supervisor): an
    equal ``(engine_version, build)`` pair is the same release restarting — accepted; a same-version
    **new build** is the preparation artifact of REL-06 and is accepted **only** through the
    preparation path — a ``PreparationRow`` covering exactly that pair — never through the bare
    declaration; "does not follow" applies only when the version differs (downgrade, unchanged).
    Build facts never infer calculation-code identity (see ``PreparationRow``)."""
    if previous_version is None:
        return
    if candidate_version == previous_version:
        if candidate_build is not None and candidate_build == previous_build:
            return  # the same release, restarted
        if preparation is not None and preparation.covers(candidate_version, candidate_build):
            return  # the authorised preparation artifact, bound to its own BASELINE row
        raise ValueError(
            f"{SAME_VERSION_REBUILD}: a same-version new build of {candidate_version} is accepted "
            "only through the preparation path (a PreparationRow for that build), never through "
            "the bare declaration"
        )
    floor = semver_level(previous_version, candidate_version)
    if _RANK[declared] < _RANK[floor]:
        raise ValueError(
            f"validation_level {declared} is below the semver floor {floor} "
            f"({previous_version} → {candidate_version})"
        )


StampingPath = Literal["FIRST_RELEASE", "RESTART", "VERSION_CHANGE", "SAME_VERSION_REBUILD"]


@dataclass(frozen=True, slots=True)
class StampingDecision:
    """What REL-03 stamping does with the manifest's declaration (DG-ENG-10 rev 1.25)."""

    path: StampingPath
    declared: Level
    floor: Level | None  # the semver floor that was checked (VERSION_CHANGE only)


def stamping_decision(
    declared: Level,
    *,
    previous: tuple[str, str] | None,
    candidate: tuple[str, str],
    row_exists: bool,
) -> StampingDecision:
    """The path a starting process takes at REL-03 stamping (D-96 (3); team-lead ruling (5)).

    ``previous`` is the previous **global** release — the latest ``deployed_at`` row at insert time
    as ``(engine_version, build_sha)`` — or None on an empty table; ``candidate`` is the process's
    own pair; ``row_exists`` says whether that pair is already stamped.

    - ``RESTART``: the pair exists; nothing is checked (the declaration was checked when the row
      was first inserted, and a restart of an older release after a newer one is not a downgrade).
    - ``FIRST_RELEASE``: nothing to compare.
    - ``VERSION_CHANGE``: ``check_declaration`` against the previous global release; a declaration
      below ``semver_level`` or a version that does not follow raises ``ValueError`` and the caller
      stops the process before the insert.
    - ``SAME_VERSION_REBUILD``: same ``engine_version``, new build — recorded with its declaration.
      The R2 rule (a same-version rebuild is accepted only through the preparation path) is
      evaluated at T-PLT-43 creation, where the ``PreparationRow`` exists: the artifact's own row
      must exist before a ``PreparationRow`` can name it, and every non-engine release (api or
      frontend change, ``ENGINE_VERSION`` unchanged) is a same-version new build.
    """
    if row_exists:
        return StampingDecision("RESTART", declared, None)
    if previous is None:
        return StampingDecision("FIRST_RELEASE", declared, None)
    previous_version, _previous_build = previous
    candidate_version, _candidate_build = candidate
    if previous_version == candidate_version:
        return StampingDecision("SAME_VERSION_REBUILD", declared, None)
    check_declaration(
        declared, previous_version=previous_version, candidate_version=candidate_version
    )
    return StampingDecision(
        "VERSION_CHANGE", declared, semver_level(previous_version, candidate_version)
    )
