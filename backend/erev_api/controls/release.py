"""Engine release stamping (05 REL-03; 04 T-PLT-38; dev-guide DG-ENG-10; BUILD_SPEC PLF-20).

The api (``main.create_app`` lifespan) and the worker (``worker.main``) call ``stamp_release`` when
they start. It reads ``release-manifest.json`` at the repository root; when the manifest is absent
outside ``production`` it derives ``{engine_version, build_sha, schema_revision}`` from
``erev_engine.ENGINE_VERSION``, ``git rev-parse HEAD`` (``"dev"`` without git) and the code's
Alembic head. It inserts the ``engine_release`` row when the ``(engine_version, build_sha)`` pair is
new and returns the row, which the process keeps to stamp its computations and runs.

``MANIFEST_PATH`` is read when a call passes no ``manifest_path``: the repository root's
``release-manifest.json``, which is ``/app/release-manifest.json`` in the api and worker images
(``make docker-build`` writes the manifest through ``make release-manifest`` and the Dockerfiles
copy it; DG-MK-docker-build, DPL-01).
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_engine import ENGINE_VERSION
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from erev_api.config import REPO_ROOT, Environment
from erev_api.controls.validation_level import (
    Level,
    declared_validation_level,
    parse_engine_version,
    stamping_decision,
)
from erev_api.db import new_id
from erev_api.db.migration_ops import code_head
from erev_api.db.session import release_session
from erev_api.db.tables import engine_release
from erev_api.logging import get_logger, register_logger_fields

MANIFEST_PATH: Final = REPO_ROOT / "release-manifest.json"
_LOGGER: Final = "erev_api.controls.release"
register_logger_fields(
    _LOGGER,
    (
        "engine_release_id",
        "engine_version",
        "build_sha",
        "schema_revision",
        "source",
        "validation_level",
    ),
)
DEV_BUILD_SHA: Final = "dev"
# 04 T-PLT-38 gate_results: the manifest also records e2e and perf, which the row does not keep.
GATE_KEYS: Final = ("ci", "parity", "answer-keys", "properties", "test-pg", "controls-report")
_GIT_SHA: Final = re.compile(r"^[0-9a-f]{40}$")


class ReleaseManifestError(RuntimeError):
    """The manifest is absent in production, malformed, or describes another release."""


# 05 REL-05: the release this process stamped at startup; `jobs.registry.insert_job` records its id
# as the enqueuer of every deferred job, and the worker compares it with the job's.
_current_release: EngineRelease | None = None


def current_release() -> EngineRelease | None:
    """The release ``stamp_release`` recorded in this process, or None before startup (tests,
    ``run_inline``)."""
    return _current_release


def remember_release(release: EngineRelease | None) -> None:
    global _current_release
    _current_release = release


# The environment the entrypoint boundary recorded (05 REL-03 consumers, rev 1.15; D-98 60):
# ``stamp_release`` (api lifespan, worker start, ``erev seed``) and ``cli.cli_services()`` record
# it, so domain code never reads ``get_settings()`` (DG-KRN-CFG-01). None means unremembered, which
# the stamping consumers treat as production (fail closed) — never as a licence to fall back.
_current_env: Environment | None = None


def current_environment() -> Environment | None:
    return _current_env


def remember_environment(env: Environment | None) -> None:
    global _current_env
    _current_env = env


@dataclass(frozen=True, slots=True)
class ReleaseFacts:
    engine_version: str
    build_sha: str
    schema_revision: str
    control_impact_tags: tuple[str, ...] = ()
    gate_results: Mapping[str, Mapping[str, str | None]] = field(default_factory=dict)
    # REL-01 ``validation_level`` (D-96 (3)); absent from the manifest → PATCH, undeclared.
    validation_level: Level = "PATCH"
    validation_declared: bool = False


@dataclass(frozen=True, slots=True)
class EngineRelease:
    """The T-PLT-38 row of the running process."""

    id: UUID
    engine_version: str
    build_sha: str
    schema_revision: str
    deployed_at: datetime
    validation_level: str = "PATCH"  # T-PLT-38 rev 1.29; the row's persisted declaration


def release_identity(engine_version: object, build_sha: object) -> tuple[str, str]:
    """The ``(engine_version, build_sha)`` pair a run record or view exposes (05 REL-03; 04
    API-S-ReportRun ``engine_release`` "of the running process"): the semver in ``engine_version``,
    the sha in ``build_sha``, both kept distinct — a pair whose version does not parse as
    MAJOR.MINOR.PATCH (a swapped pair puts the sha there) is refused, never rendered."""
    version, sha = str(engine_version), str(build_sha)
    parse_engine_version(version)
    return version, sha


def git_build_sha(root: Path = REPO_ROOT) -> str:
    """``git rev-parse HEAD`` of the checkout, or ``"dev"`` without git or a repository."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return DEV_BUILD_SHA
    sha = completed.stdout.strip()
    return sha if completed.returncode == 0 and _GIT_SHA.fullmatch(sha) else DEV_BUILD_SHA


def facts_from_manifest(manifest: Any, *, schema_revision: str) -> ReleaseFacts:
    """The release a manifest describes; it must name the running engine and schema head."""
    if not isinstance(manifest, dict):
        raise ReleaseManifestError("the release manifest is not a JSON object")
    if manifest.get("engine_version") != ENGINE_VERSION:
        raise ReleaseManifestError("the release manifest names another engine version")
    if manifest.get("schema_revision") != schema_revision:
        raise ReleaseManifestError("the release manifest names another schema revision")
    build_sha = manifest.get("build_sha")
    if not isinstance(build_sha, str) or not build_sha:
        raise ReleaseManifestError("the release manifest carries no build_sha")
    tags = manifest.get("control_impact_tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ReleaseManifestError("control_impact_tags is not a list of control ids")
    gates = manifest.get("gate_results", {})
    if not isinstance(gates, dict):
        raise ReleaseManifestError("gate_results is not an object")
    results: dict[str, dict[str, str | None]] = {}
    for key in GATE_KEYS:
        gate = gates.get(key)
        if gate is None:
            continue
        digest = gate.get("output_sha256") if isinstance(gate, dict) else None
        if (
            not isinstance(gate, dict)
            or not isinstance(gate.get("result"), str)
            or not (digest is None or isinstance(digest, str))
        ):
            raise ReleaseManifestError(f"gate_results.{key} is not {{result, output_sha256}}")
        results[key] = {"result": gate["result"], "output_sha256": digest}
    try:
        declared = declared_validation_level(manifest)
    except ValueError as exc:  # another literal than PATCH / MINOR / MAJOR, or not a string
        raise ReleaseManifestError(f"the release manifest's {exc}") from exc
    return ReleaseFacts(
        engine_version=ENGINE_VERSION,
        build_sha=build_sha,
        schema_revision=schema_revision,
        control_impact_tags=tuple(sorted(tags)),
        gate_results=results,
        validation_level=declared.level,
        validation_declared=declared.declared,
    )


def release_facts(
    env: Environment,
    *,
    manifest_path: Path | None = None,
    build_sha: Callable[[], str] | None = None,
) -> ReleaseFacts:
    """The manifest's release, or the derived one when the manifest is absent outside production.

    The manifest is evaluated before any database access: ``stamp_release`` calls this first, so a
    production process without a manifest exits before it opens a connection. ``MANIFEST_PATH`` and
    ``git_build_sha`` are read at call time when the arguments are omitted.
    """
    path = MANIFEST_PATH if manifest_path is None else manifest_path
    derive = git_build_sha if build_sha is None else build_sha
    head = code_head()
    if not path.exists():
        if env is Environment.PRODUCTION:
            raise ReleaseManifestError(f"{path.name} is required in production (REL-03)")
        return ReleaseFacts(engine_version=ENGINE_VERSION, build_sha=derive(), schema_revision=head)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseManifestError(f"{path.name} cannot be read") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseManifestError("the release manifest is not valid JSON") from exc
    return facts_from_manifest(manifest, schema_revision=head)


def stamp_release(
    env: Environment,
    *,
    request_id: str,
    manifest_path: Path | None = None,
    build_sha: Callable[[], str] | None = None,
) -> EngineRelease:
    """Insert the release row once per ``(engine_version, build_sha)`` and return it (REL-03).

    Rev 1.15 / 04 rev 1.29 (D-96 (3)): the manifest's ``validation_level`` is persisted on the new
    row, and ``stamping_decision`` is applied first — a version-changing new row whose declaration
    is below the semver floor against the previous **global** release (the latest ``deployed_at``
    row), or whose version does not follow it, stops the process here with ``ReleaseManifestError``
    before any insert; a restart checks nothing; a same-version new build is recorded. The
    environment is remembered for the stamping consumers (``current_environment``)."""
    facts = release_facts(env, manifest_path=manifest_path, build_sha=build_sha)
    remember_environment(env)
    pair = (
        engine_release.c.engine_version == facts.engine_version,
        engine_release.c.build_sha == facts.build_sha,
    )
    with release_session(request_id=request_id) as session:
        existing = session.execute(select(engine_release.c.id).where(*pair)).scalar_one_or_none()
        latest = session.execute(
            select(engine_release.c.engine_version, engine_release.c.build_sha)
            .order_by(engine_release.c.deployed_at.desc(), engine_release.c.id.desc())
            .limit(1)
        ).one_or_none()
        previous = None if latest is None else (str(latest[0]), str(latest[1]))
        try:
            stamping_decision(
                facts.validation_level,
                previous=previous,
                candidate=(facts.engine_version, facts.build_sha),
                row_exists=existing is not None,
            )
        except ValueError as exc:
            raise ReleaseManifestError(
                f"validation_level {facts.validation_level} is refused at stamping "
                f"(REL-03; D-96 (3)): {exc}"
            ) from exc
        session.execute(
            insert(engine_release)
            .values(
                id=new_id(),
                engine_version=facts.engine_version,
                build_sha=facts.build_sha,
                schema_revision=facts.schema_revision,
                control_impact_tags=list(facts.control_impact_tags),
                gate_results={key: dict(value) for key, value in facts.gate_results.items()},
                validation_level=facts.validation_level,
            )
            .on_conflict_do_nothing(index_elements=["engine_version", "build_sha"])
        )
        row = session.execute(
            select(
                engine_release.c.id,
                engine_release.c.engine_version,
                engine_release.c.build_sha,
                engine_release.c.schema_revision,
                engine_release.c.deployed_at,
                engine_release.c.validation_level,
            ).where(*pair)
        ).one()
    release = EngineRelease(
        id=row.id,
        engine_version=row.engine_version,
        build_sha=row.build_sha,
        schema_revision=row.schema_revision,
        deployed_at=row.deployed_at,
        validation_level=str(row.validation_level),
    )
    remember_release(release)
    return release


def log_release(release: EngineRelease, *, manifest_path: Path | None = None) -> None:
    """``release.stamped``: the identity a serving process (api lifespan, worker main) runs under,
    so a deployment's api and worker are compared from their logs. CLI commands that stamp
    (``erev seed``) stay silent (DG-KRN-TEN-04)."""
    path = MANIFEST_PATH if manifest_path is None else manifest_path
    get_logger(_LOGGER).info(
        "release.stamped",
        engine_release_id=str(release.id),
        engine_version=release.engine_version,
        build_sha=release.build_sha,
        schema_revision=release.schema_revision,
        source="manifest" if path.exists() else "derived",
        validation_level=release.validation_level,
    )
