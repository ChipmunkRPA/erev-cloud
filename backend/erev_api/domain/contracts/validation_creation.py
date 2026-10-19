"""Create the current process's tenant validation from authoritative release history."""

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from erev_api.controls.release import EngineRelease, current_release
from erev_api.controls.validation_level import Level
from erev_api.db import new_id
from erev_api.db.tables import (
    contract_computation,
    engine_release,
    release_validation,
    subledger_posting,
)
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .release_validation import TenantHistory, initial_validation
from .validation_fence import hold

_RANK = {"PATCH": 0, "MINOR": 1, "MAJOR": 2}


def ensure(uow: UnitOfWork, *, process: EngineRelease | None = None) -> dict[str, Any]:
    """Create once under the population fence; an existing validation is read-only.

    A first-use tenant is enabled only after proving it has neither a successful computation
    nor an engine posting. Historical tenants without an enabled predecessor are never guessed
    safe. Skipped releases contribute their strongest declared validation level.
    """
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden")
    candidate = current_release() if process is None else process
    if candidate is None:
        raise Problem("release-mismatch", "The running process has not stamped its release.")
    tenant = uow.principal.tenant_id
    stored = (
        uow.session.execute(select(engine_release).where(engine_release.c.id == candidate.id))
        .mappings()
        .one_or_none()
    )
    if stored is None or any(
        stored[key] != getattr(candidate, key)
        for key in ("engine_version", "build_sha", "schema_revision", "validation_level")
    ):
        raise Problem(
            "release-mismatch", "The process release identity differs from its stored row."
        )
    query = select(release_validation).where(
        release_validation.c.tenant_id == tenant,
        release_validation.c.engine_release_id == candidate.id,
    )
    existing = uow.session.execute(query).mappings().one_or_none()
    if existing is not None:
        return dict(existing)
    hold(uow)
    existing = uow.session.execute(query).mappings().one_or_none()
    if existing is not None:
        return dict(existing)
    previous = (
        uow.session.execute(
            select(release_validation, engine_release.c.engine_version)
            .join(engine_release, engine_release.c.id == release_validation.c.engine_release_id)
            .where(
                release_validation.c.tenant_id == tenant,
                release_validation.c.enabled_at.is_not(None),
            )
            .order_by(release_validation.c.enabled_at.desc(), release_validation.c.id.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    has_computation = bool(
        uow.session.scalar(
            select(contract_computation.c.id)
            .where(
                contract_computation.c.tenant_id == tenant,
                contract_computation.c.status == "SUCCEEDED",
            )
            .limit(1)
        )
    )
    has_posting = bool(
        uow.session.scalar(
            select(subledger_posting.c.id)
            .where(
                subledger_posting.c.tenant_id == tenant,
                subledger_posting.c.posting_kind == "ENGINE_COMPUTE",
            )
            .limit(1)
        )
    )
    declarations: dict[str, Level] = {}
    for version, level in uow.session.execute(
        select(engine_release.c.engine_version, engine_release.c.validation_level)
    ):
        if version not in declarations or _RANK[level] > _RANK[declarations[version]]:
            declarations[version] = cast(Level, level)
    try:
        creation = initial_validation(
            candidate_release_id=candidate.id,
            candidate_version=candidate.engine_version,
            history=TenantHistory(
                has_computation,
                has_posting,
                None if previous is None else previous["engine_version"],
                None
                if previous is None or previous["effective_level"] != "BASELINE"
                else previous["engine_release_id"],
            ),
            declared=declarations,
            source_release_id=None if previous is None else previous["engine_release_id"],
        )
    except ValueError as error:
        raise Problem(
            "release-mismatch", "The candidate does not follow the tenant's enabled release."
        ) from error
    row = {
        "tenant_id": tenant,
        "id": new_id(),
        "engine_release_id": creation.engine_release_id,
        "source_engine_release_id": creation.source_engine_release_id,
        "effective_level": creation.effective_level,
        "status": creation.status.value,
        "enabled_at": uow.now if creation.enabled_at_creation else None,
        "created_at": uow.now,
        "created_by": uow.principal.id,
        "created_by_kind": uow.principal.kind.value,
        "updated_at": uow.now,
        "updated_by": uow.principal.id,
        "updated_by_kind": uow.principal.kind.value,
    }
    inserted = uow.session.scalar(
        insert(release_validation)
        .values(**row)
        .on_conflict_do_nothing(index_elements=["tenant_id", "engine_release_id"])
        .returning(release_validation.c.id)
    )
    if inserted is None:
        return dict(uow.session.execute(query).mappings().one())
    uow.audit(
        action="release_validation.create",
        object_type="release_validation",
        object_id=row["id"],
        after={
            "engine_release_id": candidate.id,
            "source_engine_release_id": creation.source_engine_release_id,
            "effective_level": creation.effective_level,
            "status": creation.status.value,
        },
        detail={
            "population": dict(creation.population),
            "reason": creation.reason,
            "has_successful_computation": has_computation,
            "has_engine_posting": has_posting,
        },
    )
    return dict(uow.session.execute(query).mappings().one())
