"""Contract labels from committed header revisions, within an already authorized population."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import report_source_revision
from erev_api.problems import Problem


def identities(
    session: Session, tenant_id: UUID, contract_ids: Iterable[UUID], cutoff: datetime
) -> dict[UUID, dict[str, Any]]:
    ids = set(contract_ids)
    if not ids:
        return {}
    revision = report_source_revision
    committed = func.erev.source_commit_time("report_source_revision", revision.c.id)
    rows = session.execute(
        select(
            revision.c.id,
            revision.c.source_id,
            revision.c.document,
            committed.label("committed_server_at"),
        )
        .where(
            revision.c.tenant_id == tenant_id,
            revision.c.source_kind == "contract",
            revision.c.source_id.in_(ids),
            revision.c.recorded_at <= cutoff,
            committed <= cutoff,
        )
        .distinct(revision.c.source_id)
        .order_by(revision.c.source_id, revision.c.revision_no.desc())
    ).mappings()
    found = {}
    for row in rows:
        document = row["document"]
        if datetime.fromisoformat(document["created_at"]) > cutoff:
            continue
        found[row["source_id"]] = {
            "id": row["source_id"],
            "external_id": document["external_id"],
            "contract_no": document["contract_no"],
            "contracting_entity_id": UUID(document["contracting_entity_id"]),
            "source_revision_id": row["id"],
            "committed_server_at": row["committed_server_at"],
        }
    if found.keys() != ids:
        raise Problem(
            "historical-evidence-unavailable", "Contract identities are unavailable at cutoff."
        )
    return found
