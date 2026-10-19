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
from erev_api.db.tables import import_upload, scenario, tenant
from erev_api.domain.forecast import input_order
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
    ordered = [] if previous is None else input_order.sequence(dict(previous))
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
            input_sequence=ordered,
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
    if publish or any(
        key in changes for key in ("api_commands", "import_upload_ids", "input_sequence")
    ):
        changes["input_sequence"] = input_order.sequence({**current, **changes})
    if publish:
        pending = uow.session.scalar(
            select(import_upload.c.id)
            .where(
                import_upload.c.forecast_event_set_id == identity,
                import_upload.c.status.not_in(
                    ("COMMITTED", "CANCELLED", "INVALID", "FAILED", "REJECTED")
                ),
            )
            .limit(1)
        )
        if pending is not None:
            raise Problem(
                "invalid-transition",
                "Finish or cancel pending forecast imports before publication.",
            )
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
        content = input_order.content({**current, **changes})
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


def capture_command[T](
    uow: UnitOfWork,
    identity: UUID,
    *,
    contract_id: UUID,
    body: Mapping[str, Any],
    execute: Callable[[], T],
) -> T:
    """Apply and retain one forecast command in the same transaction as its facts.

    Serialize with publication/version edits before acquiring contract locks. The caller
    still executes the ordinary contract authorization and validation path.
    """
    if (
        "scenario.use" not in uow.principal.permissions
        or uow.principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    scenario_id = _scenario(uow.session, uow.principal.db_context)
    initial = _row(uow.session, identity)
    _lock(uow.session, uow.principal.tenant_id, initial["code"])
    current = _row(uow.session, identity, lock=True)
    if current["production_scenario_id"] != scenario_id:
        raise Problem("invalid-transition", "The input set belongs to another scenario.")
    if current["status"] != "DRAFT":
        raise Problem("invalid-transition", "Create a draft version before adding forecast events.")
    ordered = input_order.sequence(current)
    with uow.savepoint():
        result = execute()
        commands = [
            *current["api_commands"],
            {"method": "POST", "path": f"/contracts/{contract_id}/events", "body": dict(body)},
        ]
        change(
            uow,
            identity,
            expected_version=current["row_version"],
            values={
                "api_commands": commands,
                "input_sequence": [*ordered, {"kind": "API_COMMAND", "index": len(commands) - 1}],
            },
        )
        uow.audit(
            action="forecast_event_set.capture_command",
            object_type="forecast_event_set",
            object_id=identity,
            contract_id=contract_id,
            detail={"command_index": len(commands) - 1},
        )
        return result


# Forecast facts have the same validation/emitters as their production imports. Configuration
# and contract-change templates have additional approval contracts and are not forecast facts.
FORECAST_TEMPLATES = frozenset({"progress_events", "usage", "cost_events", "invoices"})


def require_draft(uow: UnitOfWork, identity: UUID) -> dict[str, Any]:
    scenario_id = _scenario(uow.session, uow.principal.db_context)
    initial = _row(uow.session, identity)
    _lock(uow.session, uow.principal.tenant_id, initial["code"])
    current = _row(uow.session, identity, lock=True)
    if current["production_scenario_id"] != scenario_id or current["status"] != "DRAFT":
        raise Problem("invalid-transition", "Choose a draft input set of this scenario.")
    input_order.sequence(current)
    return current


def admit_import(uow: UnitOfWork, identity: UUID, template_code: str) -> None:
    if (
        "scenario.use" not in uow.principal.permissions
        or uow.principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    if template_code not in FORECAST_TEMPLATES:
        raise Problem(
            "validation-failed",
            "Choose a forecast fact template: progress_events, usage, cost_events or invoices.",
        )
    require_draft(uow, identity)


def attach_import(uow: UnitOfWork, current: Mapping[str, Any], import_id: UUID) -> None:
    change(
        uow,
        current["id"],
        expected_version=current["row_version"],
        values={
            "import_upload_ids": [*current["import_upload_ids"], import_id],
            "input_sequence": [
                *input_order.sequence(current),
                {"kind": "IMPORT_UPLOAD", "id": str(import_id)},
            ],
        },
    )
    uow.audit(
        action="forecast_event_set.capture_import",
        object_type="forecast_event_set",
        object_id=current["id"],
        detail={"import_upload_id": str(import_id)},
    )
