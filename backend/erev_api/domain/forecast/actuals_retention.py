"""Durable, idempotent actuals capture before scenario snapshot completion or replay."""

import io
from datetime import datetime
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import forecast_actuals_capture, legal_entity, tenant_snapshot
from erev_api.domain.platform import sandboxes
from erev_api.domain.reports import forecast_actuals
from erev_api.domain.reports.builders import ReportParams
from erev_api.enums import FilePurpose
from erev_api.files.store import store_file
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.problems import Problem


def retain(jc: JobContext, *, snapshot_id: UUID, requested_by: UUID, known_at: datetime) -> None:
    actor = sandboxes.sandbox_actor(jc.tenant_id, requested_by, at=jc.clock.now())
    if (
        "scenario.use" not in actor.permissions
        or actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    with system_unit_of_work(jc.runtime, actor, request_id=f"job-{jc.job_id}-actuals") as uow:
        snapshot = (
            uow.session.execute(
                select(tenant_snapshot)
                .where(
                    tenant_snapshot.c.id == snapshot_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if snapshot["job_id"] != jc.job_id or snapshot["known_at"] != known_at:
            raise Problem("precondition-failed", "The actuals capture does not match its snapshot.")
        previous = uow.session.scalar(
            select(forecast_actuals_capture.c.id).where(
                forecast_actuals_capture.c.tenant_snapshot_id == snapshot_id,
            )
        )
        if previous is not None:
            return
        if snapshot["status"] not in ("QUEUED", "RUNNING"):
            raise Problem("precondition-failed", "Completed snapshots cannot acquire new actuals.")
        entities = tuple(
            uow.session.scalars(
                select(legal_entity.c.id)
                .where(
                    legal_entity.c.created_at <= known_at,
                )
                .order_by(legal_entity.c.id)
            )
        )
        books = {}
        for book in ("ASC606", "IFRS15"):
            jc.heartbeat()
            books[book] = (
                forecast_actuals.capture(
                    uow,
                    ReportParams(
                        report_code="actual_vs_forecast",
                        report_version=1,
                        parameters={},
                        entity_ids=entities,
                        known_at=known_at,
                        book_code=book,
                        historical=True,
                    ),
                )
                if entities
                else {
                    "schema_version": 1,
                    "source_tenant_id": str(jc.tenant_id),
                    "known_at": known_at.isoformat(),
                    "book_code": book,
                    "entity_ids": [],
                    "rows": [],
                }
            )
        document = {"schema_version": 1, "tenant_snapshot_id": str(snapshot_id), "books": books}
        digest = sha256_hex(document)
        stored = store_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=io.BytesIO(canonical_bytes(document)),
            original_filename=f"forecast-actuals-{snapshot_id}.json",
            media_type="application/json",
        )
        identity = new_id()
        uow.session.execute(
            insert(forecast_actuals_capture).values(
                tenant_id=jc.tenant_id,
                id=identity,
                tenant_snapshot_id=snapshot_id,
                known_at=known_at,
                dataset_file_id=stored["id"],
                dataset_sha256=digest,
                entity_ids=[str(entity) for entity in entities],
                created_at=uow.now,
                created_by=actor.id,
                created_by_kind=actor.kind.value,
            )
        )
        uow.audit(
            action="scenario.capture_actuals",
            object_type="tenant_snapshot",
            object_id=snapshot_id,
            after={"capture_id": str(identity), "dataset_sha256": digest},
        )
        uow.commit()
