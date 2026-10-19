"""Draft/version/publish lifecycle for scenario input sets; execution belongs to forecast jobs."""

import hashlib
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import Select, insert, select, text, update
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db import new_id
from erev_api.db.session import DbContext, set_tenant_context, tenant_session
from erev_api.db.tables import forecast_event_set as sets
from erev_api.db.tables import scenario, tenant
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def _scenario(session: Session, context: DbContext) -> UUID:
    source = session.execute(
        select(tenant.c.source_tenant_id).where(
            tenant.c.id == context.tenant_id, tenant.c.kind == "sandbox"
        )
    ).scalar_one_or_none()
    if source is None:
        raise Problem("sandbox-restricted", "Forecast inputs belong to a scenario sandbox.")
    set_tenant_context(
        session, DbContext(tenant_id=source, user_id=context.user_id, entity_scope="*")
    )
    try:
        found = session.execute(
            select(scenario.c.id).where(scenario.c.scenario_tenant_id == context.tenant_id)
        ).scalar_one_or_none()
    finally:
        set_tenant_context(session, context)
    if found is None:
        raise Problem("sandbox-restricted", "This sandbox is not a registered scenario.")
    return UUID(str(found))


def _lock(session: Session, tenant_id: UUID, code: str) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"forecast-event-set:{tenant_id}:{code}"},
    )


def _row(session: Session, event_set_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    statement = select(sets).where(sets.c.id == event_set_id)
    if lock:
        statement = statement.with_for_update(key_share=True)
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _range(values: Mapping[str, Any]) -> None:
    start, end = values.get("effective_from"), values.get("effective_to")
    if start is not None and end is not None and end <= start:
        raise Problem("validation-failed", "effective_to must be later than effective_from.")


def create(uow: UnitOfWork, values: Mapping[str, Any]) -> dict[str, Any]:
    scenario_id = _scenario(uow.session, uow.principal.db_context)
    code = str(values["code"])
    _range(values)
    _lock(uow.session, uow.principal.tenant_id, code)
    previous = (
        uow.session.execute(
            select(sets).where(sets.c.code == code).order_by(sets.c.version_no.desc()).limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if previous is not None and previous["status"] == "DRAFT":
        raise Problem(
            "invalid-transition", "Edit the existing draft before creating another version."
        )
    identity = new_id()
    uow.session.execute(
        insert(sets).values(
            tenant_id=uow.principal.tenant_id,
            id=identity,
            **dict(values),
            production_scenario_id=scenario_id,
            version_no=1 if previous is None else previous["version_no"] + 1,
            supersedes_version_id=None if previous is None else previous["id"],
            import_upload_ids=[] if previous is None else previous["import_upload_ids"],
            api_commands=[] if previous is None else previous["api_commands"],
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind.value,
            updated_at=uow.now,
            updated_by=uow.principal.id,
            updated_by_kind=uow.principal.kind.value,
        )
    )
    uow.audit(
        action="forecast_event_set.create",
        object_type="forecast_event_set",
        object_id=identity,
        after={"code": code, "status": "DRAFT"},
    )
    return _row(uow.session, identity)


def change(
    uow: UnitOfWork,
    identity: UUID,
    *,
    expected_version: int,
    values: Mapping[str, Any] | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    _scenario(uow.session, uow.principal.db_context)
    initial = _row(uow.session, identity)
    _lock(uow.session, uow.principal.tenant_id, initial["code"])
    current = _row(uow.session, identity, lock=True)
    if current["row_version"] != expected_version:
        raise Problem("precondition-failed", "The input set changed; reload it first.")
    if current["status"] != "DRAFT":
        raise Problem(
            "invalid-transition", "Published input sets are immutable; create a new version."
        )
    changes = dict(values or {})
    if not publish and not changes:
        raise Problem("validation-failed", "Provide at least one field to update.")
    _range({**current, **changes})
    if publish:
        if current["supersedes_version_id"] is not None:
            uow.session.execute(
                update(sets)
                .where(sets.c.id == current["supersedes_version_id"], sets.c.status == "PUBLISHED")
                .values(
                    status="SUPERSEDED",
                    updated_by=uow.principal.id,
                    updated_by_kind=uow.principal.kind.value,
                )
            )
        content = {
            key: current[key]
            for key in (
                "code",
                "name",
                "production_scenario_id",
                "version_no",
                "supersedes_version_id",
                "effective_from",
                "effective_to",
                "import_upload_ids",
                "api_commands",
            )
        }
        changes.update(
            status="PUBLISHED",
            content_sha256=hashlib.sha256(canonical_bytes(content)).hexdigest(),
            published_at=uow.now,
            published_by=uow.principal.id,
        )
    audited = tuple(changes)
    changes.update(
        updated_at=uow.now, updated_by=uow.principal.id, updated_by_kind=uow.principal.kind.value
    )
    uow.session.execute(update(sets).where(sets.c.id == identity).values(**changes))
    uow.audit(
        action="forecast_event_set.publish" if publish else "forecast_event_set.update",
        object_type="forecast_event_set",
        object_id=identity,
        before={key: current[key] for key in audited},
        after={key: changes[key] for key in audited},
        detail={
            "supersedes_version_id": str(current["supersedes_version_id"])
            if current["supersedes_version_id"]
            else None
        },
    )
    return _row(uow.session, identity)


def get(ctx: RequestContext, identity: UUID) -> dict[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _scenario(session, ctx.principal.db_context)
        return _row(session, identity)


def listing[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _scenario(session, ctx.principal.db_context)
        return page(session, select(sets))
