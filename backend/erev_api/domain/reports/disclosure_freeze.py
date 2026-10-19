"""Read-only disclosure source capture at the lock decision's exact cutoff.

Produces typed JSON evidence without invented job/run IDs. The lock transaction publishes
source reports and seven snapshots through disclosure_lock before the close can succeed.
"""

from typing import Any

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import text

from erev_api.domain.reports import (
    disclosure_expedients,
    disclosure_plan,
    framework,
    snapshots,
    tie_outs,
)
from erev_api.domain.reports.builders import ReportParams, SourceCollector
from erev_api.domain.reports.evidence_archive import MAX_PAYLOAD_BYTES
from erev_api.domain.reports.outputs import manifest, utc_text
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def capture(uow: UnitOfWork, scope: snapshots.SnapshotScope, *, quarter: bool) -> dict[str, Any]:
    """Use one existing SYSTEM reader and never enqueue jobs or widen the supplied cutoff."""
    if (
        uow.principal.kind is not PrincipalKind.SYSTEM
        or uow.session.scalar(text("SHOW transaction_read_only")) != "on"
    ):
        raise Problem("forbidden")
    if (
        scope.known_at.tzinfo is None
        or scope.book_code not in {"ASC606", "IFRS15"}
        or (scope.frozen_at is not None and scope.frozen_at != scope.known_at)
    ):
        raise Problem("validation-failed", "Disclosure freeze requires one aware source cutoff.")
    entities = tie_outs.entities(uow.session, (scope.entity_id,))
    if len(entities) != 1:
        raise Problem("validation-failed", "The disclosure freeze entity is unavailable.")
    entity = entities[0]
    calendar = tie_outs.calendars(uow.session, entities)[entity.id]
    period = next((item for item in calendar.periods if item.id == scope.period_id), None)
    if period is None:
        raise Problem("validation-failed", "The disclosure period is outside the entity calendar.")
    planned = disclosure_plan.requests(
        entity_code=entity.code,
        book=scope.book_code,
        calendar=calendar,
        period_key=period.key,
        known_at=scope.known_at,
        quarter=quarter,
    )
    policies = disclosure_expedients.capture_for_lock(
        uow, entity_id=entity.id, book=scope.book_code, known_at=scope.known_at
    )
    children = []
    size = len(canonical_bytes(policies))
    for request in planned:
        code = request.body.report_code
        definition = framework.definition_row(uow.session, code, 1)
        builder = framework.BUILDERS.get(code)
        if definition is None or builder is None:
            raise Problem("validation-failed", f"Disclosure freeze producer {code} is unavailable.")
        parameters, historical = snapshots.scope_parameters(
            definition,
            scope,
            entity_code=entity.code,
            period_key=period.key,
            known_at=scope.known_at,
        )
        parameters.update(request.body.parameters)
        parameters["known_at"] = utc_text(scope.known_at)
        if (
            framework.parameter_errors(definition["parameters_schema"], parameters)
            or not historical
        ):
            raise Problem("validation-failed", f"Disclosure freeze parameters for {code} differ.")
        collector = SourceCollector()
        data = builder(
            uow,
            ReportParams(
                report_code=code,
                report_version=1,
                parameters=parameters,
                entity_ids=(entity.id,),
                known_at=scope.known_at,
                book_code=scope.book_code,
                historical=True,
                output_format="JSON",
                sources=collector,
            ),
        )
        if collector.cutoff not in {None, scope.known_at}:
            raise Problem("validation-failed", f"Disclosure freeze cutoff changed in {code}.")
        if len({row["row_key"] for row in data.rows}) != data.row_count:
            raise Problem("validation-failed", f"Disclosure freeze row identity repeats in {code}.")
        document = manifest.dataset_document(
            manifest.report_reference(code, str(definition["name"]), 1), parameters, data
        )
        digest = sha256_hex(document)
        collector.record_cutoff(scope.known_at)
        contract = framework.SOURCE_CONTRACTS[code]
        inputs = collector.binding(
            row_keys=[str(row["row_key"]) for row in data.rows],
            strategy=contract.strategy,
            open=contract.open,
            report_version=1,
            dataset={"output_sha256": digest, "format": "JSON"},
        ).to_stored()
        child = {
            "key": request.key,
            "sections": list(request.sections),
            "basis": request.basis,
            "parameters_sha256": sha256_hex(parameters),
            "output_sha256": digest,
            "dataset": document,
            "source_binding": inputs,
        }
        size += len(canonical_bytes(child))
        if size > MAX_PAYLOAD_BYTES:
            raise Problem(
                "validation-failed", "Disclosure freeze exceeds the retained input limit."
            )
        children.append(child)
    return {
        "schema_version": 1,
        "tenant_id": str(uow.principal.tenant_id),
        "entity_id": str(entity.id),
        "entity_code": entity.code,
        "book": scope.book_code,
        "period_id": str(period.id),
        "period_key": period.key,
        "known_at": scope.known_at.isoformat(),
        "quarter": quarter,
        "children": children,
        "policies": policies,
        "policy_sha256": sha256_hex(policies),
    }
