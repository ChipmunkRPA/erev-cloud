"""Publish synchronous disclosure evidence inside the close decision transaction.

Source reports record the historical calculations actually executed by the shared reader.
They have no queued job and retain their ordinary source bindings. Only the composed parent
and its seven snapshots claim the period lock as their source.
"""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import insert, select

from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import new_id
from erev_api.db.tables import disclosure_snapshot, period_lock, report_run
from erev_api.db.transitions import apply
from erev_api.domain.reports import (
    disclosure_assembly,
    disclosure_execution,
    disclosure_inputs,
    disclosure_plan,
    disclosure_results,
    disclosure_snapshots,
    framework,
    tie_outs,
)
from erev_api.domain.reports.builders import SourceBinding
from erev_api.domain.reports.outputs import ReportData, manifest, utc_text
from erev_api.enums import ControlResult
from erev_api.numbering import next_number
from erev_api.problems import Problem
from erev_api.registry.resolve import setting
from erev_api.uow import UnitOfWork


def _start(
    uow: UnitOfWork,
    *,
    code: str,
    parameters: dict[str, Any],
    entity_id: UUID,
    book: str,
    cutoff: datetime,
    lock_id: UUID | None,
) -> dict[str, Any]:
    raw_as_of = parameters.get("as_of_date")
    row = {
        "tenant_id": uow.principal.tenant_id,
        "id": new_id(),
        "report_run_no": next_number(uow, framework.SERIES),
        "report_code": code,
        "report_version": 1,
        "status": "RUNNING",
        "parameters": parameters,
        "entity_ids": [entity_id],
        "book_code": book,
        "as_of_date": None if raw_as_of is None else date.fromisoformat(raw_as_of),
        "known_at": cutoff,
        "period_lock_id": lock_id,
        "engine_release_id": framework._release_id(uow.session),
        "output_format": "JSON",
        "job_id": None,
        "started_at": uow.now,
        **framework._stamp(uow),
    }
    uow.session.execute(insert(report_run).values(**row))
    uow.audit(
        action=framework.ACTION_CREATE,
        object_type=framework.OBJECT_TYPE,
        object_id=row["id"],
        after={"report_code": code, "status": "RUNNING"},
        detail={"execution": "LOCK_CAPTURE"},
    )
    return row


def _finish(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    data: ReportData,
    rendered: framework._Rendered,
    *,
    lock_id: UUID,
    binding: Mapping[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> None:
    file_id = framework._store(
        uow,
        rendered.content,
        name=framework._file_name(row, rendered.extension),
        media_type=rendered.media_type,
    )
    values = {
        "output_file_id": file_id,
        "output_sha256": rendered.sha256,
        "row_count": data.row_count,
        "control_totals": dict(data.control_totals),
        "tie_out_results": [dict(item) for item in data.tie_out_results],
        "source_binding": None if binding is None else dict(binding),
        "finished_at": uow.now,
        **(extra or {}),
    }
    apply(
        uow.session,
        framework.TABLE,
        row["id"],
        to_status="SUCCEEDED",
        set_values=values,
        expected_status="RUNNING",
    )
    uow.audit(
        action=framework.ACTION_SUCCEED,
        object_type=framework.OBJECT_TYPE,
        object_id=row["id"],
        before={"status": "RUNNING"},
        after={
            "status": "SUCCEEDED",
            "output_sha256": rendered.sha256,
            "output_file_id": str(file_id),
            "row_count": data.row_count,
        },
        detail={"execution": "LOCK_CAPTURE", "period_lock_id": str(lock_id)},
    )
    fact = framework.ctl029_fact({**row, **values}, None, rerun_of=None)
    record_execution(
        uow,
        control_id="CTL-029",
        run_ref_type=RunRefType.REPORT_RUN,
        run_ref_id=row["id"],
        population_count=fact.population_count,
        exception_count=fact.exception_count,
        result=fact.result,
        detail=fact.detail,
    )
    failed = sum(tie["result"] == "FAIL" for tie in data.tie_out_results)
    result = (
        ControlResult.NOT_APPLICABLE
        if not data.tie_out_results
        else ControlResult.FAIL
        if failed
        else ControlResult.PASS
    )
    record_execution(
        uow,
        control_id="CTL-030",
        run_ref_type=RunRefType.REPORT_RUN,
        run_ref_id=row["id"],
        population_count=len(data.tie_out_results),
        exception_count=failed,
        result=result,
        detail={
            "tie_outs": [
                {"code": tie["code"], "result": tie["result"]} for tie in data.tie_out_results
            ]
        },
    )


def publish(uow: UnitOfWork, lock_id: UUID, captured: Mapping[str, Any]) -> UUID:
    """Save real source identities, parent artifact and seven immutable snapshots atomically."""
    lock = (
        uow.session.execute(
            select(period_lock).where(
                period_lock.c.tenant_id == uow.principal.tenant_id,
                period_lock.c.id == lock_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        lock is None
        or lock["kind"] != "LOCK"
        or any(
            (
                captured.get("schema_version") != 1,
                captured.get("tenant_id") != str(uow.principal.tenant_id),
                captured.get("entity_id") != str(lock["entity_id"]),
                captured.get("book") != lock["book_code"],
                captured.get("period_id") != str(lock["period_id"]),
                captured.get("known_at") != lock["cutoff_known_at"].isoformat(),
                lock["created_at"] != uow.now,
            )
        )
    ):
        raise Problem("validation-failed", "Disclosure capture differs from the new period lock.")
    if (
        uow.session.scalar(
            select(disclosure_snapshot.c.id)
            .where(
                disclosure_snapshot.c.tenant_id == uow.principal.tenant_id,
                disclosure_snapshot.c.period_lock_id == lock_id,
            )
            .limit(1)
        )
        is not None
    ):
        raise Problem("invalid-transition", "The lock already has disclosure snapshots.")
    if sha256_hex(captured["policies"]) != captured["policy_sha256"]:
        raise Problem("validation-failed", "Disclosure policy capture digest differs.")
    cutoff = lock["cutoff_known_at"]
    entity_id = lock["entity_id"]
    book = lock["book_code"]
    entities = tie_outs.entities(uow.session, (entity_id,))
    if len(entities) != 1 or entities[0].code != captured["entity_code"]:
        raise Problem("validation-failed", "Disclosure entity capture differs.")
    calendar = tie_outs.calendars(uow.session, entities)[entity_id]
    selected_period = calendar.named(captured["period_key"], "period_key")
    if selected_period.id != lock["period_id"] or not isinstance(captured["quarter"], bool):
        raise Problem("validation-failed", "Disclosure reporting period differs.")
    planned = disclosure_plan.requests(
        entity_code=entities[0].code,
        book=book,
        calendar=calendar,
        period_key=selected_period.key,
        known_at=cutoff,
        quarter=captured["quarter"],
    )
    if [item["key"] for item in captured["children"]] != [item.key for item in planned]:
        raise Problem("validation-failed", "Disclosure source capture plan differs.")
    for item, request in zip(captured["children"], planned, strict=True):
        expected = {**request.body.parameters, "known_at": utc_text(cutoff)}
        if any(item["dataset"]["parameters"].get(key) != value for key, value in expected.items()):
            raise Problem("validation-failed", "Disclosure source period selectors differ.")
    # All rows, metadata and file writes share the decision UoW. The nested transaction also
    # prevents a caller catching a malformed capture from retaining a partial source population.
    style = str(setting(uow.session, framework.NEGATIVE_NUMBER_STYLE, known_at=cutoff))
    with uow.savepoint():
        parent_parameters = {
            "entity_codes": [captured["entity_code"]],
            "book": book,
            "period_key": captured["period_key"],
            "quarter": captured["quarter"],
            "known_at": utc_text(cutoff),
            "known_at_basis": "historical",
            "period_lock_id": str(lock_id),
        }
        parent = _start(
            uow,
            code="disclosure_pack",
            parameters=parent_parameters,
            entity_id=entity_id,
            book=book,
            cutoff=cutoff,
            lock_id=lock_id,
        )
        children = []
        stamps = {}
        for item in captured["children"]:
            document = item["dataset"]
            code = document["report"]["code"]
            source_binding = SourceBinding.from_stored(item["source_binding"])
            contract = framework.SOURCE_CONTRACTS.get(code)
            if (
                contract is None
                or source_binding is None
                or source_binding.cutoff != cutoff
                or source_binding.report_version != 1
                or source_binding.strategy != contract.strategy
                or source_binding.open != contract.open
                or source_binding.dataset
                != {"output_sha256": item["output_sha256"], "format": "JSON"}
                or document["report"]["version"] != 1
                or item["key"] != f"{code}:{item['basis']}"
                or tuple(item["sections"]) != disclosure_plan.SECTIONS.get(code)
                or item["basis"] not in {"PERIOD", "QUARTER_TO_DATE"}
                or document["parameters"].get("entity_codes") != [captured["entity_code"]]
                or document["parameters"].get("book") != book
                or document["parameters"].get("known_at") != utc_text(cutoff)
                or document["parameters"].get("known_at_basis") != "historical"
            ):
                raise Problem("validation-failed", "Disclosure source capture identity differs.")
            row = _start(
                uow,
                code=code,
                parameters=document["parameters"],
                entity_id=entity_id,
                book=book,
                cutoff=cutoff,
                lock_id=None,
            )
            row.update(
                output_sha256=item["output_sha256"],
                row_count=document["row_count"],
                control_totals=document["control_totals"],
                tie_out_results=document["tie_out_results"],
            )
            source = disclosure_plan.ChildSource(
                item["key"],
                tuple(item["sections"]),
                item["basis"],
                row["id"],
                None,
                item["parameters_sha256"],
            )
            content = canonical_bytes(document)
            data = disclosure_results.decode(content, row, source)
            if source_binding.row_keys != frozenset(str(record["row_key"]) for record in data.rows):
                raise Problem("validation-failed", "Disclosure source population differs.")
            rendered = framework._Rendered(
                content, item["output_sha256"], manifest.MEDIA_TYPE, manifest.EXTENSION
            )
            _finish(uow, row, data, rendered, lock_id=lock_id, binding=item["source_binding"])
            child = disclosure_results.CompletedChild(source, data, row, item["output_sha256"])
            children.append(child)
            definition = framework.definition_row(uow.session, code, 1)
            if definition is None:
                raise Problem("validation-failed", "Disclosure source definition is unavailable.")
            stamps[row["id"]] = framework._run_stamp(
                uow.session, row, definition, output_sha256=item["output_sha256"], style=style
            )
        parent["child_report_run_ids"] = [child.source.run_id for child in children]
        pack = disclosure_assembly.assemble(
            parent, disclosure_results.Collected((), tuple(children)), dict(captured["policies"])
        )
        facts = disclosure_inputs.capture(parent, pack, stamps)
        definition = framework.definition_row(uow.session, "disclosure_pack", 1)
        if definition is None:
            raise Problem("validation-failed", "Disclosure definition is unavailable.")
        data, rendered, _ = disclosure_execution.render(
            uow, parent, definition, style, pack, stamps, facts
        )
        documents = disclosure_snapshots.documents_for(parent, pack, facts, lock["period_id"])
        # The seventh snapshot retains supporting waterfall inputs once. A future locked
        # rebuild can recover all sixteen inputs without depending on live child output files.
        documents["EXPEDIENTS_USED"]["supporting_children"] = [
            child for child in facts["children"] if not child["sections"]
        ]
        rows = [
            {
                "tenant_id": uow.principal.tenant_id,
                "id": new_id(),
                "disclosure_kind": kind,
                "entity_id": entity_id,
                "book_code": book,
                "period_id": lock["period_id"],
                "period_lock_id": lock_id,
                "report_run_id": parent["id"],
                "data": document,
                "data_sha256": sha256_hex(document),
                "created_at": uow.now,
                "created_by": uow.principal.id,
                "created_by_kind": uow.principal.kind.value,
            }
            for kind, document in documents.items()
        ]
        uow.session.execute(insert(disclosure_snapshot), rows)
        _finish(
            uow,
            parent,
            data,
            rendered,
            lock_id=lock_id,
            binding=None,
            extra={
                "child_report_run_ids": parent["child_report_run_ids"],
                "disclosure_snapshot_ids": [row["id"] for row in rows],
            },
        )
        return UUID(str(parent["id"]))
