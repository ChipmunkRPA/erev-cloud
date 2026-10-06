"""``controls.validation_level`` and ``controls.stamping``: the REL-01 ``validation_level`` key, the
T-PLT-38 column contract, the semver floor and consumer stamping with the process's own release
(05 REL-03, REL-06; D-96 (3); SOP-2 remainder ruled to lane P5). DB-free."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from erev_api.config import Environment
from erev_api.controls.release import (
    EngineRelease,
    ReleaseManifestError,
    facts_from_manifest,
    release_identity,
)
from erev_api.controls.stamping import FALLBACK_ENVIRONMENTS, process_release_id
from erev_api.controls.validation_level import (
    LEVELS,
    SAME_VERSION_REBUILD,
    T_PLT_38_VALIDATION_LEVEL,
    VALIDATION_LEVEL_KEY,
    check_declaration,
    declared_validation_level,
    parse_engine_version,
    semver_level,
    stamping_decision,
    with_validation_level,
)
from erev_api.domain.contracts import release_validation
from erev_api.problems import Problem
from erev_engine import ENGINE_VERSION

MANIFEST = {
    "engine_version": "0.3.0",
    "build_sha": "a" * 40,
    "schema_revision": "0053",
    "created_at": "2026-09-19T00:00:00Z",
    "gate_results": {},
    "control_impact_tags": [],
}


def test_manifest_validation_level_key_and_column_contract() -> None:
    absent = declared_validation_level(MANIFEST)
    assert absent.level == "PATCH" and absent.declared is False
    declared = declared_validation_level(with_validation_level(MANIFEST, "MAJOR"))
    assert declared.level == "MAJOR" and declared.declared is True
    assert with_validation_level(MANIFEST, "MINOR")[VALIDATION_LEVEL_KEY] == "MINOR"
    assert MANIFEST.get(VALIDATION_LEVEL_KEY) is None  # the helper copies, never mutates
    with pytest.raises(ValueError, match="validation_level"):
        declared_validation_level({**MANIFEST, VALIDATION_LEVEL_KEY: "HUGE"})
    with pytest.raises(ValueError):
        declared_validation_level({**MANIFEST, VALIDATION_LEVEL_KEY: 2})
    with pytest.raises(ValueError):
        with_validation_level(MANIFEST, "MEDIUM")  # type: ignore[arg-type]
    assert LEVELS == ("PATCH", "MINOR", "MAJOR")
    name, sql_type, default, check = T_PLT_38_VALIDATION_LEVEL
    assert (name, sql_type, default) == ("validation_level", "text", "PATCH")
    assert check == "CHECK (validation_level IN ('PATCH','MINOR','MAJOR'))"


def test_semver_floor_and_the_shared_semver_level() -> None:
    assert release_validation.semver_level is semver_level  # one implementation, kernel-side
    assert semver_level("0.2.0", "0.3.0") == "MINOR"
    check_declaration("MAJOR", previous_version="0.2.0", candidate_version="0.3.0")  # above floor
    check_declaration("MINOR", previous_version="0.2.0", candidate_version="0.3.0")  # at floor
    check_declaration("PATCH", previous_version=None, candidate_version="0.3.0")  # first release
    with pytest.raises(ValueError, match="below the semver floor"):
        check_declaration("PATCH", previous_version="0.2.0", candidate_version="0.3.0")
    with pytest.raises(ValueError, match="below the semver floor"):
        check_declaration("MINOR", previous_version="0.9.0", candidate_version="1.0.0")


def _release(version: str = "0.3.0") -> EngineRelease:
    return EngineRelease(uuid4(), version, "b" * 40, "0053", datetime(2026, 9, 19, tzinfo=UTC))


def test_consumer_stamping_uses_the_process_release_and_fails_closed_in_production() -> None:
    current = _release()
    calls: list[int] = []

    def fallback() -> UUID | None:
        calls.append(1)
        return UUID(int=9)

    # The process's own row wins; the latest-per-version query is never consulted.
    for env in (Environment.PRODUCTION, Environment.DEV, Environment.TEST):
        assert process_release_id(current, env=env, latest_for_version=fallback) == current.id
    assert calls == []
    # Outside production a missing current release falls back to the latest row of the version,
    # with an explicit WARN-class line naming the fallback (team-lead ruling (4)).
    warnings: list[str] = []
    assert process_release_id(
        None, env=Environment.DEV, latest_for_version=fallback, warn=warnings.append
    ) == UUID(int=9)
    assert calls == [1] and len(warnings) == 1
    assert "latest-per-version fallback" in warnings[0] and "dev" in warnings[0]
    # In production a missing current release is a defect: fail closed with the REL-05 problem,
    # no fallback query and no warning line.
    with pytest.raises(Problem) as refused:
        process_release_id(
            None, env=Environment.PRODUCTION, latest_for_version=fallback, warn=warnings.append
        )
    assert refused.value.slug == "release-mismatch" and calls == [1] and len(warnings) == 1
    # No row at all, outside production: the same problem (REL-03 was not run).
    with pytest.raises(Problem):
        process_release_id(None, env=Environment.TEST, latest_for_version=lambda: None)


def test_stamping_decision_names_the_four_paths_and_applies_the_global_floor() -> None:
    """DG-ENG-10 rev 1.25 / 04 T-PLT-38 rev 1.29: what REL-03 stamping does with the declaration
    against the previous GLOBAL release (team-lead ruling (5))."""
    candidate = ("0.3.0", "b" * 40)
    restart = stamping_decision("PATCH", previous=candidate, candidate=candidate, row_exists=True)
    assert restart.path == "RESTART" and restart.floor is None
    # A restart of an older release after a newer one was deployed is not a downgrade.
    older = stamping_decision(
        "PATCH", previous=("0.4.0", "c" * 40), candidate=candidate, row_exists=True
    )
    assert older.path == "RESTART"
    first = stamping_decision("MAJOR", previous=None, candidate=candidate, row_exists=False)
    assert (first.path, first.declared, first.floor) == ("FIRST_RELEASE", "MAJOR", None)
    change = stamping_decision(
        "MINOR", previous=("0.2.0", "a" * 40), candidate=candidate, row_exists=False
    )
    assert (change.path, change.floor) == ("VERSION_CHANGE", "MINOR")
    with pytest.raises(ValueError, match="below the semver floor"):
        stamping_decision(
            "PATCH", previous=("0.2.0", "a" * 40), candidate=candidate, row_exists=False
        )
    with pytest.raises(ValueError, match="does not follow"):  # a rollback BUILD is refused
        stamping_decision(
            "MAJOR", previous=("0.4.0", "c" * 40), candidate=candidate, row_exists=False
        )
    same = stamping_decision(
        "PATCH", previous=("0.3.0", "a" * 40), candidate=candidate, row_exists=False
    )
    assert (same.path, same.declared, same.floor) == ("SAME_VERSION_REBUILD", "PATCH", None)
    # The bare declaration path still refuses that pair (Codex P5-PREP R2, closed at e0ea5aa): the
    # rule is evaluated at T-PLT-43 creation, where the PreparationRow exists — not dropped.
    with pytest.raises(ValueError, match=SAME_VERSION_REBUILD):
        check_declaration(
            "PATCH",
            previous_version="0.3.0",
            candidate_version="0.3.0",
            previous_build="a" * 40,
            candidate_build="b" * 40,
        )


def test_release_facts_carry_the_manifest_validation_level() -> None:
    manifest = {"engine_version": ENGINE_VERSION, "build_sha": "a" * 40, "schema_revision": "0055"}
    absent = facts_from_manifest(manifest, schema_revision="0055")
    assert (absent.validation_level, absent.validation_declared) == ("PATCH", False)
    declared = facts_from_manifest(
        {**manifest, "validation_level": "MINOR"}, schema_revision="0055"
    )
    assert (declared.validation_level, declared.validation_declared) == ("MINOR", True)
    with pytest.raises(ReleaseManifestError, match="validation_level"):
        facts_from_manifest({**manifest, "validation_level": "HUGE"}, schema_revision="0055")
    with pytest.raises(ReleaseManifestError, match="validation_level"):
        facts_from_manifest({**manifest, "validation_level": 1}, schema_revision="0055")
    # The row dataclass carries the persisted declaration; older constructors keep the default.
    assert _release().validation_level == "PATCH"
    stamped = EngineRelease(
        uuid4(), "0.3.0", "b" * 40, "0055", datetime(2026, 9, 19, tzinfo=UTC), "MAJOR"
    )
    assert stamped.validation_level == "MAJOR"


def test_consumer_stamping_guards_the_engine_version_and_unrecorded_environment() -> None:
    current = _release("0.3.0")
    assert (
        process_release_id(
            current, env=None, engine_version="0.3.0", latest_for_version=lambda: None
        )
        == current.id
    )
    # The process's row never stamps another engine version's output.
    with pytest.raises(Problem) as refused:
        process_release_id(
            current,
            env=Environment.PRODUCTION,
            engine_version="0.2.0",
            latest_for_version=lambda: None,
        )
    assert refused.value.slug == "release-mismatch"
    # D-98 60: an unknown or unremembered environment is production — no stamp, no fallback, and
    # e2e is not a fallback environment either.
    warnings: list[str] = []
    for env in (None, Environment.E2E, Environment.PRODUCTION):
        with pytest.raises(Problem) as closed:
            process_release_id(
                None, env=env, latest_for_version=lambda: UUID(int=7), warn=warnings.append
            )
        assert closed.value.slug == "release-mismatch", env
    assert warnings == []
    # Only a remembered dev / test environment may fall back, and it says so.
    assert FALLBACK_ENVIRONMENTS == frozenset({Environment.DEV, Environment.TEST})
    for env in sorted(FALLBACK_ENVIRONMENTS):
        assert process_release_id(
            None, env=env, latest_for_version=lambda: UUID(int=7), warn=warnings.append
        ) == UUID(int=7)
    assert len(warnings) == 2 and all("latest-per-version fallback" in w for w in warnings)


def test_run_record_release_identity_keeps_semver_and_sha_distinct() -> None:
    """05 REL-03 / 04 API-S-ReportRun ``engine_release``: the run record carries the process
    release's ``engine_version`` (semver) and ``build_sha`` (sha) as two distinct fields; a swapped
    pair — the sha where the version belongs — is refused, never rendered (CTL-029 shape)."""
    from erev_api.schemas.reports import EngineReleaseRefOut

    sha = "7605b060389524618aece72594dc26d5961c70ea"
    assert release_identity(ENGINE_VERSION, sha) == (ENGINE_VERSION, sha)
    assert release_identity("0.3.0", "tests-ctr-2") == ("0.3.0", "tests-ctr-2")
    assert parse_engine_version("0.3.0") == (0, 3, 0)
    ref = EngineReleaseRefOut(engine_version=ENGINE_VERSION, build_sha=sha)
    assert ref.model_dump() == {"engine_version": ENGINE_VERSION, "build_sha": sha}
    for swapped in ((sha, ENGINE_VERSION), ("tests-ctr-2", "0.3.0"), ("0.0.0-probe.abc", "x")):
        with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
            release_identity(*swapped)
