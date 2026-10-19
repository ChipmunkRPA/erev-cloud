"""Disclosure reads intersect parent report permission and snapshot entity scope."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import Select, and_, any_, func, or_, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import Principal
from erev_api.db.tables import disclosure_snapshot as snapshot
from erev_api.db.tables import legal_entity, period, report_run
from erev_api.domain.reports import framework
from erev_api.problems import Problem
from erev_api.schemas.disclosures import DisclosureSnapshotOut, DisclosureSnapshotSummaryOut


def statement(
    principal: Principal, *, detail: bool = False, attached_to: UUID | None = None
) -> Select[Any]:
    columns = [
        snapshot.c.id,
        snapshot.c.disclosure_kind,
        snapshot.c.entity_id,
        legal_entity.c.code.label("entity_code"),
        snapshot.c.book_code.label("book"),
        snapshot.c.period_id,
        period.c.period_key,
        snapshot.c.period_lock_id,
        snapshot.c.report_run_id,
        snapshot.c.data_sha256,
        snapshot.c.created_at,
    ]
    if detail:
        columns.extend((snapshot.c.data, report_run.c.known_at))
    query = (
        select(*columns)
        .select_from(
            snapshot.join(
                report_run,
                and_(
                    snapshot.c.tenant_id == report_run.c.tenant_id,
                    snapshot.c.report_run_id == report_run.c.id,
                ),
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == snapshot.c.tenant_id,
                    legal_entity.c.id == snapshot.c.entity_id,
                ),
            )
            .join(
                period,
                and_(
                    period.c.tenant_id == snapshot.c.tenant_id, period.c.id == snapshot.c.period_id
                ),
            )
        )
        .where(
            snapshot.c.tenant_id == principal.tenant_id,
            report_run.c.status == "SUCCEEDED",
            report_run.c.report_code == "disclosure_pack",
            snapshot.c.id == any_(report_run.c.disclosure_snapshot_ids),
            func.cardinality(report_run.c.entity_ids) == 1,
            snapshot.c.entity_id == any_(report_run.c.entity_ids),
            snapshot.c.book_code == report_run.c.book_code,
            period.c.period_key == report_run.c.parameters["period_key"].astext,
            period.c.calendar_id == legal_entity.c.calendar_id,
            or_(
                snapshot.c.period_lock_id == report_run.c.period_lock_id,
                and_(snapshot.c.period_lock_id.is_(None), report_run.c.period_lock_id.is_(None)),
            ),
        )
    )
    if attached_to is not None:
        attachments = framework.visible(
            select(func.unnest(report_run.c.disclosure_snapshot_ids)).where(
                report_run.c.tenant_id == principal.tenant_id,
                report_run.c.id == attached_to,
                report_run.c.report_code == "disclosure_pack",
                report_run.c.status == "SUCCEEDED",
            ),
            principal,
            "report.run",
        ).correlate(None)
        query = query.where(snapshot.c.id.in_(attachments))
    return framework.visible(query, principal, "report.run")


def summary(row: Mapping[str, Any]) -> DisclosureSnapshotSummaryOut:
    return DisclosureSnapshotSummaryOut.model_validate(
        {
            **row,
            "source": "DRAFT" if row["period_lock_id"] is None else "LOCKED",
        }
    )


def get(session: Session, principal: Principal, identity: UUID) -> DisclosureSnapshotOut:
    found = (
        session.execute(statement(principal, detail=True).where(snapshot.c.id == identity))
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    row = dict(found)
    data = row["data"]
    if (
        not isinstance(data, dict)
        or sha256_hex(data) != row["data_sha256"]
        or data.get("schema_version") != 1
        or data.get("kind") != row["disclosure_kind"]
        or data.get("entity_id") != str(row["entity_id"])
        or data.get("book") != row["book"]
        or data.get("period_id") != str(row["period_id"])
        or data.get("period_key") != row["period_key"]
        or data.get("known_at") != row["known_at"].isoformat()
        or data.get("period_lock_id")
        != (None if row["period_lock_id"] is None else str(row["period_lock_id"]))
    ):
        raise Problem("validation-failed", "The retained disclosure snapshot is inconsistent.")
    return DisclosureSnapshotOut(**summary(row).model_dump(), data=data)
