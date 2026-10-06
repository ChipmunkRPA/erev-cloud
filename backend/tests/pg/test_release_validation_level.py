"""T-PLT-38 ``validation_level`` (04 rev 1.29; revision 0055), the REL-03 stamping
decision and the consumers' selection against persisted releases (05 REL-03 rev 1.15; D-96 (3);
lane P5 integration slice 1).

DB-bound: written with the slice and NOT RUN on the lane worktree (no database stage); the first run
is ``make test-pg`` after the merge. The migration round trip itself is ``test_migrations.py::
test_upgrade_downgrade_upgrade``, which snapshots the column, its default and the check. No test
here inserts a row of another engine version: such a row would become the previous global release
for every later stamp in the shared database (the floor is proven DB-free in
``tests/unit/test_release_level_and_stamping.py``; the hook order is proven here by a decision that
refuses).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from erev_api.config import Environment
from erev_api.controls import release
from erev_api.controls.release import ReleaseManifestError, stamp_release
from erev_api.db.migration_ops import code_head
from erev_api.db.session import identity_session
from erev_api.db.tables import engine_release
from erev_api.domain.contracts import computation, compute_job
from erev_api.domain.journals import summarise
from erev_api.domain.reports import framework
from erev_engine import ENGINE_VERSION
from sqlalchemy import exc, insert, select, text
from support.db import TestDatabase

pytestmark = pytest.mark.pg

_DEFAULT = text(
    "SELECT column_default FROM information_schema.columns WHERE table_schema = 'erev' "
    "AND table_name = 'engine_release' AND column_name = 'validation_level'"
)


def _manifest(directory: Path, **changes: Any) -> Path:
    manifest: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "build_sha": f"vl-{uuid4().hex}",
        "schema_revision": code_head(),
        "created_at": "2026-09-19T00:00:00.000000Z",
        "control_impact_tags": [],
        "gate_results": {},
        **changes,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "release-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _row(build_sha: str) -> dict[str, Any] | None:
    with identity_session(request_id="tests-validation-level") as session:
        found = session.execute(
            select(engine_release).where(
                engine_release.c.engine_version == ENGINE_VERSION,
                engine_release.c.build_sha == build_sha,
            )
        ).mappings()
        rows = [dict(row) for row in found]
    return rows[0] if rows else None


@pytest.fixture
def process_state() -> Iterator[None]:
    before, env = release.current_release(), release.current_environment()
    try:
        yield
    finally:
        release.remember_release(before)
        release.remember_environment(env)


def test_stamping_persists_the_declaration_and_a_restart_checks_nothing(
    committed_db: TestDatabase, tmp_path: Path, process_state: None
) -> None:
    declared = _manifest(tmp_path / "minor", validation_level="MINOR")
    first = stamp_release(Environment.PRODUCTION, request_id="tests-vl", manifest_path=declared)
    row = _row(first.build_sha)
    assert row is not None and row["validation_level"] == "MINOR" == first.validation_level
    assert release.current_environment() is Environment.PRODUCTION
    again = stamp_release(Environment.PRODUCTION, request_id="tests-vl", manifest_path=declared)
    assert again == first  # RESTART: the row is reused, nothing is checked or rewritten
    undeclared = _manifest(tmp_path / "patch")
    second = stamp_release(Environment.PRODUCTION, request_id="tests-vl", manifest_path=undeclared)
    assert second.validation_level == "PATCH"  # absent key → PATCH, undeclared


def test_a_refusing_decision_stops_stamping_before_the_insert(
    committed_db: TestDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook order: ``stamping_decision`` runs before any insert (the floor itself is proven
    DB-free; here the decision is made to refuse)."""

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise ValueError("validation_level PATCH is below the semver floor MINOR (probe)")

    monkeypatch.setattr(release, "stamping_decision", refuse)
    path = _manifest(tmp_path / "refused")
    build = json.loads(path.read_text(encoding="utf-8"))["build_sha"]
    with pytest.raises(ReleaseManifestError, match="refused at stamping"):
        stamp_release(Environment.PRODUCTION, request_id="tests-vl-refused", manifest_path=path)
    assert _row(build) is None


def test_column_default_and_check(committed_db: TestDatabase) -> None:
    with identity_session(request_id="tests-vl-ddl") as session:
        assert session.execute(_DEFAULT).scalar_one() == "'PATCH'::text"
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            session.execute(
                insert(engine_release).values(
                    id=uuid4(),
                    engine_version=ENGINE_VERSION,
                    build_sha=f"vl-check-{uuid4().hex}",
                    schema_revision=code_head(),
                    validation_level="HUGE",
                )
            )
        savepoint.rollback()
    assert getattr(refused.value.orig, "sqlstate", None) == "23514"  # check_violation


def test_consumers_select_the_process_release_against_persisted_rows(
    committed_db: TestDatabase, tmp_path: Path, process_state: None
) -> None:
    """Two rows of the running version: the later-deployed one is the latest-per-version answer;
    the consumers stamp the process's own (older) row, and only an unstamped non-production
    process falls back to the latest."""
    older = stamp_release(
        Environment.PRODUCTION, request_id="tests-vl-a", manifest_path=_manifest(tmp_path / "a")
    )
    newer = stamp_release(
        Environment.PRODUCTION, request_id="tests-vl-b", manifest_path=_manifest(tmp_path / "b")
    )
    assert newer.deployed_at >= older.deployed_at and newer.id != older.id
    release.remember_release(older)
    release.remember_environment(Environment.PRODUCTION)
    with identity_session(request_id="tests-vl-consumers") as session:
        assert computation._engine_release_id(session, ENGINE_VERSION) == older.id
        assert compute_job._release_id(session, ENGINE_VERSION) == older.id
        assert summarise._release_id(session) == older.id
        assert framework._release_id(session) == older.id
        release.remember_release(None)
        release.remember_environment(Environment.TEST)
        latest = session.execute(
            select(engine_release.c.id)
            .where(engine_release.c.engine_version == ENGINE_VERSION)
            .order_by(engine_release.c.deployed_at.desc())
            .limit(1)
        ).scalar_one()
        assert summarise._release_id(session) == latest
