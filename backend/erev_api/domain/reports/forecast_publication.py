"""Publish a completed forecast capture inside the forecast worker's transaction.

This creates an ordinary immutable report run, encrypted output and control/audit evidence.
The caller owns computation, the parent forecast transition and commit. No child job can read
later scenario changes between capture and publication.
"""

from dataclasses import replace
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert, select, update

from erev_api.auth.dependencies import require_for_entity
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import new_id
from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import forecast_run, report_run, scenario, tenant
from erev_api.db.transitions import apply
from erev_api.domain.forecast import event_sets, input_order
from erev_api.domain.reports import framework, requester
from erev_api.domain.reports.builders import OPEN, SourceBinding
from erev_api.domain.reports.forecast_capture import Captured
from erev_api.domain.reports.forecast_exports import Identity, render
from erev_api.enums import ControlResult, TenantKind
from erev_api.numbering import next_number
from erev_api.problems import Problem
from erev_api.registry.resolve import setting
from erev_api.uow import UnitOfWork


def publish(uow: UnitOfWork, parent_id: UUID, captured: Captured, identity: Identity) -> UUID:
    """Roll back all effects on error; the caller commits the parent and report together."""
    with uow.savepoint():
        return _publish(uow, parent_id, captured, identity)


def _publish(uow: UnitOfWork, parent_id: UUID, captured: Captured, identity: Identity) -> UUID:
    if (
        uow.ctx.tenant_kind != TenantKind.SANDBOX
        or uow.principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    parent = (
        uow.session.execute(
            select(forecast_run)
            .where(
                forecast_run.c.id == parent_id,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if parent is None:
        raise Problem("not-found")
    if parent["status"] != "RUNNING" or parent["forecast_event_set_id"] != identity.event_set_id:
        raise Problem("invalid-transition", "Forecast publication requires its running parent.")
    if (parent["created_by"], str(parent["created_by_kind"])) != (
        uow.principal.id,
        uow.principal.kind.value,
    ):
        raise Problem("forbidden", "Publish as the forecast requester.")
    selected = event_sets._row(uow.session, identity.event_set_id, lock=True)
    scenario_id = event_sets._scenario(uow.session, uow.principal.db_context)
    if (
        selected["status"] != "PUBLISHED"
        or selected["production_scenario_id"] != scenario_id
        or identity.scenario_id != scenario_id
        or selected["name"] != identity.event_set_name
        or selected["version_no"] != identity.event_set_version
        or selected["content_sha256"] != identity.event_set_sha256
        or sha256_hex(input_order.content(selected)) != identity.event_set_sha256
    ):
        raise Problem(
            "precondition-failed", "Forecast publication identity differs from its inputs."
        )
    source_id = uow.session.scalar(
        select(tenant.c.source_tenant_id).where(
            tenant.c.id == uow.principal.tenant_id,
        )
    )
    if source_id is None:
        raise Problem("invalid-transition", "The scenario source is unavailable.")
    set_tenant_context(
        uow.session, DbContext(tenant_id=source_id, user_id=uow.principal.id, entity_scope="*")
    )
    try:
        source = uow.session.execute(
            select(scenario.c.name, scenario.c.status).where(
                scenario.c.id == scenario_id,
                scenario.c.scenario_tenant_id == uow.principal.tenant_id,
            )
        ).one_or_none()
        if source is None or source.status != "ACTIVE":
            raise Problem("invalid-transition", "The forecast scenario is no longer active.")
        identity = replace(identity, scenario_name=source.name)
    finally:
        set_tenant_context(uow.session, uow.principal.db_context)
    input_order.sequence(selected)
    parameters = parent["parameters"]
    entities = tuple(sorted(captured.entity_periods, key=str))
    if (
        set(str(e) for e in entities) != set(parameters["entity_ids"])
        or captured.book != parameters["book_code"]
        or any(
            [p.key for p in horizon] != parameters["horizon_periods"]
            for horizon in captured.entity_periods.values()
        )
    ):
        raise Problem("precondition-failed", "Forecast capture differs from the requested scope.")
    for entity in entities:
        require_for_entity(uow.ctx, "report.run", entity)
    format = captured.output_format
    if format not in {"JSON", "XLSX", "CSV"}:
        raise Problem("validation-failed", "Choose a forecast output format.")
    requester.require_export(uow.principal, format, entities)
    definition = framework.definition_row(uow.session, "forecast_outputs", 1)
    if definition is None:
        raise Problem("invalid-transition", "Forecast report definition is unavailable.")
    # A retry must reuse/settle the parent transaction, not append another output of one format.
    if (
        uow.session.scalar(
            select(report_run.c.id).where(
                report_run.c.id.in_(parent["report_run_ids"]),
                report_run.c.output_format == format,
            )
        )
        is not None
    ):
        raise Problem("invalid-transition", "This forecast output format is already published.")
    run_id = new_id()
    run_parameters = {
        "forecast_run_id": str(parent_id),
        "book": captured.book,
        "entity_codes": list(captured.entity_codes),
        "known_at": captured.known_at.isoformat(),
        "known_at_basis": framework.HISTORICAL_BASIS,
        "currency_view": captured.currency_view,
    }
    row = {
        "tenant_id": uow.principal.tenant_id,
        "id": run_id,
        "report_run_no": next_number(uow, framework.SERIES),
        "report_code": "forecast_outputs",
        "report_version": 1,
        "status": "QUEUED",
        "parameters": run_parameters,
        "entity_ids": list(entities),
        "book_code": captured.book,
        "as_of_date": None,
        "known_at": captured.known_at,
        "period_lock_id": None,
        "engine_release_id": framework._release_id(uow.session),
        "output_format": format,
        "job_id": parent["job_id"],
        **framework._stamp(uow),
    }
    uow.session.execute(insert(report_run).values(**row))
    uow.audit(
        action=framework.ACTION_CREATE,
        object_type="report_run",
        object_id=run_id,
        after={"forecast_run_id": str(parent_id), "output_format": format},
    )
    apply(
        uow.session,
        framework.TABLE,
        run_id,
        to_status="RUNNING",
        expected_status="QUEUED",
        set_values={"started_at": uow.now},
    )
    uow.audit(
        action=framework.ACTION_START,
        object_type="report_run",
        object_id=run_id,
        after={"status": "RUNNING"},
    )
    stamp = framework._run_stamp(
        uow.session,
        {**row, "started_at": uow.now},
        definition,
        output_sha256="",
        style=str(setting(uow.session, framework.NEGATIVE_NUMBER_STYLE, known_at=uow.now)),
    )
    output = render(captured, identity, stamp, format=format)
    file_id = framework._store(
        uow,
        output.content,
        name=framework._file_name(row, output.extension),
        media_type=output.media_type,
    )
    manifest_id = (
        None
        if output.manifest is None
        else framework._store(
            uow,
            output.manifest,
            name=framework._file_name(row, output.extension) + ".manifest.json",
            media_type="application/json",
        )
    )
    # Keep the canonical forecast data independently of the chosen download format. Future
    # comparisons read these saved values, never recompute a historical forecast.
    dataset_file_id = (
        file_id
        if format == "JSON"
        else framework._store(
            uow,
            output.dataset,
            name=framework._file_name(row, "json"),
            media_type="application/json",
        )
    )
    binding = SourceBinding(
        cutoff=captured.known_at,
        versions={},
        labels={},
        row_keys=frozenset(s.key for s in captured.sections),
        strategy=OPEN,
        report_version=1,
        open=(
            "Original saved forecast; rerun re-exports its verified dataset without recomputation.",
        ),
        evidence={
            "forecast_run_id": str(parent_id),
            "forecast_dataset_file_id": str(dataset_file_id),
            "event_set_sha256": identity.event_set_sha256,
            "children": {key: source.to_stored() for key, source in captured.sources.items()},
        },
    )
    values: dict[str, Any] = {
        "output_file_id": file_id,
        "manifest_file_id": manifest_id,
        "output_sha256": output.dataset_sha256,
        "row_count": len(captured.sections),
        "control_totals": {},
        "tie_out_results": [],
        "source_binding": binding.to_stored(),
        "finished_at": uow.now,
        "ledger_heads": framework._ledger_heads(uow.session),
    }
    apply(
        uow.session,
        framework.TABLE,
        run_id,
        to_status="SUCCEEDED",
        expected_status="RUNNING",
        set_values=values,
    )
    uow.audit(
        action=framework.ACTION_SUCCEED,
        object_type="report_run",
        object_id=run_id,
        after={
            "status": "SUCCEEDED",
            "output_file_id": str(file_id),
            "output_sha256": output.dataset_sha256,
            "forecast_run_id": str(parent_id),
        },
    )
    fact = framework.ctl029_fact({**row, **values}, None, rerun_of=None)
    record_execution(
        uow,
        control_id="CTL-029",
        run_ref_type=RunRefType.REPORT_RUN,
        run_ref_id=run_id,
        population_count=fact.population_count,
        exception_count=fact.exception_count,
        result=fact.result,
        detail=fact.detail,
    )
    record_execution(
        uow,
        control_id="CTL-030",
        run_ref_type=RunRefType.REPORT_RUN,
        run_ref_id=run_id,
        population_count=0,
        exception_count=0,
        result=ControlResult.NOT_APPLICABLE,
        detail={"tie_outs": []},
    )
    uow.session.execute(
        update(forecast_run)
        .where(forecast_run.c.id == parent_id)
        .values(
            report_run_ids=[*parent["report_run_ids"], run_id],
            updated_at=uow.now,
            updated_by=uow.principal.id,
            updated_by_kind=uow.principal.kind.value,
        )
    )
    uow.audit(
        action="forecast_run.attach_report",
        object_type="forecast_run",
        object_id=parent_id,
        before={"report_run_ids": [str(i) for i in parent["report_run_ids"]]},
        after={"report_run_ids": [str(i) for i in (*parent["report_run_ids"], run_id)]},
        detail={"report_run_id": str(run_id), "output_format": format},
    )
    return run_id
