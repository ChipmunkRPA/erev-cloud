"""Immutable E-65 draft snapshots published atomically with their disclosure report.

Drafts have no lock ID. Lock-time source capture must supply its own exact-cutoff evidence;
this writer never promotes a draft into an as-locked snapshot.
"""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import disclosure_snapshot, legal_entity, period, report_run
from erev_api.domain.reports import disclosure_inputs
from erev_api.enums import DisclosureKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

KINDS = (
    DisclosureKind.DISAGGREGATION,
    DisclosureKind.CONTRACT_BALANCE_ROLLFORWARD,
    DisclosureKind.REVENUE_FROM_OPENING_LIABILITY,
    DisclosureKind.PRIOR_PERIOD_POB_REVENUE,
    DisclosureKind.RPO,
    DisclosureKind.COST_ROLLFORWARD,
    DisclosureKind.EXPEDIENTS_USED,
)


def write_draft(uow: UnitOfWork, run_id: UUID, binding: Mapping[str, Any]) -> list[UUID]:
    """Serialize seven inserts with the parent; any inconsistency rolls back publication."""
    tenant_id = uow.principal.tenant_id
    found = (
        uow.session.execute(
            select(report_run)
            .where(report_run.c.tenant_id == tenant_id, report_run.c.id == run_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if (
        found is None
        or found["report_code"] != "disclosure_pack"
        or found["status"] != "RUNNING"
        or found["period_lock_id"] is not None
    ):
        raise Problem(
            "invalid-transition", "Draft disclosure snapshots require their running parent."
        )
    run = {**found, "source_binding": dict(binding)}
    pack, _, facts = disclosure_inputs.rebuild(run)
    entity_id = run["entity_ids"][0]
    period_id = uow.session.execute(
        select(period.c.id)
        .join(
            legal_entity,
            (legal_entity.c.tenant_id == period.c.tenant_id)
            & (legal_entity.c.calendar_id == period.c.calendar_id),
        )
        .where(
            period.c.tenant_id == tenant_id,
            legal_entity.c.id == entity_id,
            period.c.period_key == run["parameters"]["period_key"],
        )
    ).scalar_one_or_none()
    if period_id is None:
        raise Problem("validation-failed", "The disclosure source period is unavailable.")
    documents = {}
    for section, kind in zip(pack.sections, KINDS, strict=True):
        documents[kind.value] = {
            "schema_version": 1,
            "kind": kind.value,
            "section": section.number,
            "title": section.title,
            "entity_id": str(entity_id),
            "book": run["book_code"],
            "period_id": str(period_id),
            "period_key": run["parameters"]["period_key"],
            "known_at": run["known_at"].isoformat(),
            "quarter": bool(run["parameters"].get("quarter")),
            "period_lock_id": None,
            "interim_required": section.interim_required,
            "tables": [
                {"key": table.key, "omitted": table.omitted, "notes": list(table.notes)}
                for table in section.tables
            ],
            # Retain original inputs under elections; rendered reports stay separate.
            "children": [
                child for child in facts["children"] if section.number in child["sections"]
            ],
            "policies": facts["policies"],
            "policy_sha256": facts["policy_sha256"],
            "supporting_sources": [
                {
                    key: child[key]
                    for key in ("key", "run_id", "job_id", "parameters_sha256", "output_sha256")
                }
                for child in facts["children"]
                if not child["sections"]
            ],
        }
    existing_rows = list(
        uow.session.execute(
            select(disclosure_snapshot).where(
                disclosure_snapshot.c.tenant_id == tenant_id,
                disclosure_snapshot.c.report_run_id == run_id,
            )
        ).mappings()
    )
    existing = {str(row["disclosure_kind"]): row for row in existing_rows}
    if existing:
        if (
            len(existing_rows) != 7
            or set(existing) != set(documents)
            or any(
                row["entity_id"] != entity_id
                or row["book_code"] != run["book_code"]
                or row["period_id"] != period_id
                or row["period_lock_id"] is not None
                or row["data"] != documents[kind]
                or row["data_sha256"] != sha256_hex(documents[kind])
                for kind, row in existing.items()
            )
        ):
            raise Problem(
                "invalid-transition", "Existing disclosure snapshots differ from the inputs."
            )
        ids = [existing[kind.value]["id"] for kind in KINDS]
        if run["disclosure_snapshot_ids"] and list(run["disclosure_snapshot_ids"]) != ids:
            raise Problem("invalid-transition", "Disclosure snapshot attachment differs.")
        return ids
    if run["disclosure_snapshot_ids"]:
        raise Problem("invalid-transition", "Attached disclosure snapshots are unavailable.")
    rows = [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "disclosure_kind": kind,
            "entity_id": entity_id,
            "book_code": run["book_code"],
            "period_id": period_id,
            "period_lock_id": None,
            "report_run_id": run_id,
            "data": data,
            "data_sha256": sha256_hex(data),
            "created_at": uow.now,
            "created_by": uow.principal.id,
            "created_by_kind": uow.principal.kind.value,
        }
        for kind, data in documents.items()
    ]
    uow.session.execute(insert(disclosure_snapshot), rows)
    return [row["id"] for row in rows]
