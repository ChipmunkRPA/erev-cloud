"""Engine release stamping T-PLT-38 (05 REL-03; 04 §14.2; DG-ENG-10; BUILD_SPEC PLF-20)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from erev_api.config import Environment, Settings
from erev_api.controls import release
from erev_api.controls.release import (
    DEV_BUILD_SHA,
    GATE_KEYS,
    EngineRelease,
    ReleaseManifestError,
    release_facts,
    stamp_release,
)
from erev_api.db.session import identity_session
from erev_api.db.tables import engine_release
from erev_api.main import create_app
from erev_engine import ENGINE_VERSION
from fastapi import FastAPI
from sqlalchemy import exc, select, text, update
from support.db import TestDatabase, alembic_config
from support.production import production_settings
from support.release_manifest import ROOT, commit, gate_report, git, scratch_repo

pytestmark = pytest.mark.pg

MANIFEST_BUILD = "a" * 40
_GRANTS = text(
    "SELECT privilege_type FROM information_schema.role_table_grants "
    "WHERE grantee = 'erev_app' AND table_schema = 'erev' AND table_name = 'engine_release'"
)


async def _start(app: FastAPI) -> EngineRelease:
    """Run the app's startup and shutdown as uvicorn does."""
    async with app.router.lifespan_context(app):
        release = app.state.engine_release
    assert isinstance(release, EngineRelease)
    return release


def _head() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def _releases(build_sha: str) -> list[dict[str, Any]]:
    with identity_session(request_id="tests-engine-release") as session:
        rows = session.execute(
            select(engine_release).where(
                engine_release.c.engine_version == ENGINE_VERSION,
                engine_release.c.build_sha == build_sha,
            )
        ).mappings()
        return [dict(row) for row in rows]


def _manifest(**changes: Any) -> dict[str, Any]:
    gates = {
        key: {
            "result": "PASS",
            "command": f"make {key}",
            "output_sha256": "b" * 64,
            "finished_at": "2026-09-13T10:00:00.000000Z",
        }
        for key in (*GATE_KEYS, "e2e", "perf")
    }
    manifest: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "build_sha": MANIFEST_BUILD,
        "schema_revision": _head(),
        "created_at": "2026-09-13T10:05:00.000000Z",
        "control_impact_tags": ["CTL-032", "CTL-022"],
        "gate_results": gates,
    }
    return {**manifest, **changes}


def test_rel_03_startup_inserts_release_once(
    committed_db: TestDatabase,
    app_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Derived facts need their precondition stated: `make release-manifest` (and `make
    # docker-build`) leave a manifest at the repository root that REL-03 reads in every environment,
    # and another test that ran the lifespan first (test_me under make test) may already have
    # stamped HEAD's row from it. An absent manifest path and a build of this test's own keep the
    # row its own.
    monkeypatch.setattr(release, "MANIFEST_PATH", tmp_path / "absent-release-manifest.json")
    derived_build = f"derived-{uuid4().hex}"
    monkeypatch.setattr(release, "git_build_sha", lambda root=None: derived_build)

    first = asyncio.run(_start(create_app(app_settings)))
    second = asyncio.run(_start(create_app(app_settings)))
    assert second == first
    assert first.build_sha == derived_build == release_facts(app_settings.env).build_sha

    rows = _releases(first.build_sha)
    assert len(rows) == 1
    row = rows[0]
    assert (row["id"], row["engine_version"], row["schema_revision"]) == (
        first.id,
        ENGINE_VERSION,
        _head(),
    )
    assert (row["control_impact_tags"], row["gate_results"]) == ([], {})

    with identity_session(request_id="tests-engine-release-update") as session:
        grants = {str(privilege) for privilege in session.scalars(_GRANTS)}
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(
                update(engine_release)
                .where(engine_release.c.id == first.id)
                .values(release_notes="tampered")
            )
        savepoint.rollback()
    assert grants == {"SELECT", "INSERT"}
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"


@pytest.mark.control("CTL-032")
def test_rel_03_manifest_supplies_build_tags_and_gates(
    committed_db: TestDatabase, tmp_path: Path
) -> None:
    """CTL-032, the manifest's half on the release row: the ``engine_release`` row a
    production process stamps carries the manifest's build, its control-impact
    tags and, for each of the six gates of 03 REQ-CTL-003, the result with its
    output hash; a second stamp of the same release writes no second row. Not
    witnessed here: that the run records name the row
    (``tests/domain/platform/test_release_stamping.py``) and what the generator
    writes (``tests/unit/test_release_manifest.py``).
    """
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    release = stamp_release(Environment.PRODUCTION, request_id="tests-manifest", manifest_path=path)
    assert (release.engine_version, release.build_sha, release.schema_revision) == (
        ENGINE_VERSION,
        MANIFEST_BUILD,
        _head(),
    )
    rows = _releases(MANIFEST_BUILD)
    assert len(rows) == 1
    assert rows[0]["control_impact_tags"] == ["CTL-022", "CTL-032"]
    assert rows[0]["gate_results"] == {
        key: {"result": "PASS", "output_sha256": "b" * 64} for key in GATE_KEYS
    }
    again = stamp_release(Environment.PRODUCTION, request_id="tests-manifest", manifest_path=path)
    assert again == release
    assert len(_releases(MANIFEST_BUILD)) == 1


@pytest.mark.control("CTL-032")
def test_rel_03_refuses_absent_or_foreign_manifest(
    committed_db: TestDatabase, tmp_path: Path
) -> None:
    """CTL-032, the manifest's half where it prevents: production stamps no release
    without its manifest, nor from a manifest of another engine version, of another
    migration head, without a build, with a gate that has no result, or that is
    not JSON; outside production the facts are derived. Not witnessed here: the
    refusal of a process that never stamped
    (``tests/unit/test_consumer_release_identity.py``).
    """
    absent = tmp_path / "absent.json"
    with pytest.raises(ReleaseManifestError, match="required in production"):
        stamp_release(Environment.PRODUCTION, request_id="tests-manifest", manifest_path=absent)

    path = tmp_path / "release-manifest.json"
    for changes in (
        {"engine_version": "9.9.9"},
        {"schema_revision": "9999"},
        {"build_sha": ""},
        {"gate_results": {"ci": {"output_sha256": "b" * 64}}},
    ):
        path.write_text(json.dumps(_manifest(**changes)), encoding="utf-8")
        with pytest.raises(ReleaseManifestError):
            stamp_release(Environment.PRODUCTION, request_id="tests-manifest", manifest_path=path)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReleaseManifestError, match="not valid JSON"):
        stamp_release(Environment.PRODUCTION, request_id="tests-manifest", manifest_path=path)

    derived = stamp_release(
        Environment.DEV,
        request_id="tests-derived",
        manifest_path=absent,
        build_sha=lambda: DEV_BUILD_SHA,
    )
    assert (derived.build_sha, derived.schema_revision) == (DEV_BUILD_SHA, _head())


@pytest.mark.control("CTL-032")
def test_rel_03_production_lifespan_starts_with_generated_manifest(
    committed_db: TestDatabase,
    app_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CTL-032, the manifest's half end to end: the manifest the generator writes is
    the one a production api stamps at its start — the build, the control-impact
    tag of the changed path, the ``ci`` gate PASS with its report's digest, a gate
    without a report NOT_RUN — and the same process without its manifest does not
    start. Not witnessed here: the run records
    (``tests/domain/platform/test_release_stamping.py``).
    """
    # SOP-2 / lane P1: the manifest `scripts/release_manifest.py` writes (DG-MK-release-manifest)
    # is the one a production api reads at startup. A scratch repository gives the release a build
    # of its own, so the row is this test's: build from the manifest, CTL-022 from the changed
    # `backend/erev_engine/money.py` (REL-04), the `ci` gate PASS with the report's digest (REL-02).
    repo = scratch_repo(tmp_path / "repo")
    build = commit(repo, {"backend/erev_engine/money.py": "# scratch\n"}, "money")
    reports = tmp_path / "reports"
    ci_report = gate_report(reports, "ci", build_sha=build)
    manifest_path = tmp_path / "release-manifest.json"
    generated = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release_manifest.py"),
            "--root",
            str(repo),
            "--reports-dir",
            str(reports),
            "--out",
            str(manifest_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert git(repo, "rev-parse", "HEAD") == build

    monkeypatch.setattr(release, "MANIFEST_PATH", manifest_path)
    # A production process holds the smtp backend (05 SAR-40 rev 1.53: the fake one is refused
    # before the manifest is read, and this test is about the manifest).
    production = production_settings(app_settings)
    started = asyncio.run(_start(create_app(production)))
    assert (started.engine_version, started.build_sha, started.schema_revision) == (
        ENGINE_VERSION,
        build,
        _head(),
    )
    rows = _releases(build)
    assert len(rows) == 1
    assert rows[0]["id"] == started.id
    assert "CTL-022" in rows[0]["control_impact_tags"]
    digest = hashlib.sha256(ci_report.read_bytes()).hexdigest()
    assert rows[0]["gate_results"]["ci"] == {"result": "PASS", "output_sha256": digest}
    assert rows[0]["gate_results"]["test-pg"] == {"result": "NOT_RUN", "output_sha256": None}
    assert set(rows[0]["gate_results"]) == set(GATE_KEYS)

    # The same production process without its manifest does not start (REL-03).
    manifest_path.unlink()
    with pytest.raises(ReleaseManifestError, match="required in production"):
        asyncio.run(_start(create_app(production)))
    assert len(_releases(build)) == 1
