"""Contract-sample event history and source provenance (REQ-RPT-015).

This is the event section of a sample, not a complete sample pack. Computed versions,
allocation, schedules, journals, approvals, audit and document bytes have separate
collectors. Never fetch a document URL or include an entire shared import payload.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import func, select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import contract, contract_event, source_record
from erev_api.domain.reports import contract_identity_history
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.domain.reports.evidence_selection import SourceSelection, resolve
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.schemas.evidence_packs import ContractSamplePackCreateIn
from erev_api.uow import UnitOfWork

EVENT_KEYS = (
    "id",
    "contract_id",
    "contracting_entity_id",
    "stream_version",
    "event_type",
    "schema_version",
    "effective_date",
    "recorded_at",
    "record_seq",
    "origin",
    "is_manual",
    "obligation_ids",
    "payload",
    "payload_sha256",
    "supersedes_event_id",
    "approval_request_id",
    "modification_id",
    "estimate_version_id",
    "manual_adjustment_id",
    "import_upload_id",
    "source_record_id",
    "sync_run_id",
)
SOURCE_KEYS = (
    "id",
    "source_system",
    "object_type",
    "payload_sha256",
    "received_at",
    "created_at",
)


@dataclass(frozen=True, slots=True)
class SampleEvents:
    selection: SourceSelection
    files: tuple[PackFile, ...]
    event_ids: tuple[UUID, ...]
    approval_request_ids: tuple[UUID, ...]


def event_records(
    rows: Sequence[Mapping[str, Any]],
    *,
    contract_ids: Sequence[UUID],
    entity_ids: Sequence[UUID],
    as_of: date,
    known_at: datetime,
) -> tuple[dict[str, Any], ...]:
    """Validate source facts before redaction; never silently drop a corrupt population.

    Superseded events remain evidence. Effective date and knowledge time are independent;
    events effective later than the sample date are not part of this section.
    """
    seen: set[UUID] = set()
    records = []
    for row in rows:
        if (
            row["id"] in seen
            or row["contract_id"] not in contract_ids
            or row["contracting_entity_id"] not in entity_ids
            or row["effective_date"] > as_of
            or row["recorded_at"] > known_at
            or sha256_hex(row["payload"]) != row["payload_sha256"]
        ):
            raise Problem("validation-failed", "The sample event evidence is inconsistent.")
        if "committed_server_at" in row and (
            row["committed_server_at"] is None or row["committed_server_at"] > known_at
        ):
            raise Problem("validation-failed", "The sample event exceeds its committed cutoff.")
        seen.add(row["id"])
        record = {key: row[key] for key in EVENT_KEYS}
        if "committed_server_at" in row:
            record["committed_server_at"] = row["committed_server_at"]
        # The source digest authenticates pre-redaction bytes, not the exported payload.
        record["source_payload_sha256"] = record.pop("payload_sha256")
        record["payload"] = redact_contacts(record["payload"])
        record["exported_payload_sha256"] = sha256_hex(record["payload"])
        records.append(record)
    return tuple(sorted(records, key=lambda row: (row["record_seq"], str(row["id"]))))


def collect(
    uow: UnitOfWork,
    request: ContractSamplePackCreateIn,
    *,
    known_at: datetime | None = None,
) -> SampleEvents:
    """Read one authorized, date-bound sample; no queueing, writes or commit.

    The caller must retain these bytes atomically with the future pack binding. Retries
    must consume that binding rather than call this collector with a new knowledge time.
    """
    cutoff = uow.now if known_at is None else known_at
    if cutoff.tzinfo is None or cutoff > uow.now or request.as_of > cutoff.astimezone(UTC).date():
        raise Problem("validation-failed", "Sample dates must not exceed the source cutoff.")
    if not PERMISSIONS <= uow.principal.permissions:
        raise Problem("forbidden")
    selected = resolve(uow, request)
    for entity_id in selected.entity_ids:
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity_id)
    tenant_id = selected.tenant_id
    current_identities = list(
        uow.session.execute(
            select(
                contract.c.id,
                contract.c.external_id,
                contract.c.contract_no,
                contract.c.contracting_entity_id,
            ).where(
                contract.c.tenant_id == tenant_id,
                contract.c.id.in_(selected.contract_ids),
                contract.c.created_at <= cutoff,
            )
        ).mappings()
    )
    if len(current_identities) != len(selected.contract_ids):
        raise Problem("not-found")
    historical = contract_identity_history.identities(
        uow.session, tenant_id, selected.contract_ids, cutoff
    )
    historical_entities = {row["contracting_entity_id"] for row in historical.values()}
    for entity_id in historical_entities:
        if uow.principal.entity_scope != "*" and entity_id not in uow.principal.entity_scope:
            raise Problem("not-found")
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity_id)
    selected = SourceSelection(
        tenant_id,
        cutoff,
        tuple(sorted(set(selected.entity_ids) | historical_entities)),
        selected.contract_ids,
    )
    identities = list(historical.values())
    rows = (
        uow.session.execute(
            select(
                *(contract_event.c[key] for key in EVENT_KEYS),
                func.erev.source_commit_time("contract_event", contract_event.c.id).label(
                    "committed_server_at"
                ),
            ).where(
                contract_event.c.tenant_id == tenant_id,
                contract_event.c.contract_id.in_(selected.contract_ids),
                contract_event.c.contracting_entity_id.in_(selected.entity_ids),
                contract_event.c.recorded_at <= cutoff,
                func.erev.source_commit_time("contract_event", contract_event.c.id) <= cutoff,
                contract_event.c.effective_date <= request.as_of,
            )
        )
        .mappings()
        .all()
    )
    records = event_records(
        [dict(row) for row in rows],
        contract_ids=selected.contract_ids,
        entity_ids=selected.entity_ids,
        as_of=request.as_of,
        known_at=cutoff,
    )
    source_ids = {row["source_record_id"] for row in records if row["source_record_id"] is not None}
    sources = (
        list(
            uow.session.execute(
                select(*(source_record.c[key] for key in SOURCE_KEYS))
                .where(
                    source_record.c.tenant_id == tenant_id,
                    source_record.c.id.in_(source_ids),
                    source_record.c.received_at <= cutoff,
                    source_record.c.created_at <= cutoff,
                )
                .order_by(source_record.c.id)
            ).mappings()
        )
        if source_ids
        else []
    )
    if {row["id"] for row in sources} != source_ids:
        raise Problem("validation-failed", "A sample event's source provenance is unavailable.")
    by_id = {row["id"]: dict(row) for row in identities}
    files = [
        PackFile(
            "sample/selection.json",
            canonical_bytes(
                {
                    "schema_version": 2,
                    "tenant_id": tenant_id,
                    "as_of": request.as_of,
                    "known_at": cutoff,
                    "contracts": [by_id[key] for key in selected.contract_ids],
                }
            ),
        ),
        PackFile(
            "sample/source_records.json",
            canonical_bytes(
                {
                    "records": [dict(row) for row in sources],
                    "basis": "Source metadata only; shared raw payloads are not included.",
                }
            ),
        ),
    ]
    for contract_id in selected.contract_ids:
        files.append(
            PackFile(
                f"contracts/{contract_id}/events.json",
                canonical_bytes(
                    {
                        "schema_version": 2,
                        "contract_id": contract_id,
                        "as_of": request.as_of,
                        "known_at": cutoff,
                        "events": [row for row in records if row["contract_id"] == contract_id],
                    }
                ),
            )
        )
    return SampleEvents(
        SourceSelection(tenant_id, cutoff, selected.entity_ids, selected.contract_ids),
        tuple(files),
        tuple(row["id"] for row in records),
        tuple(
            sorted(
                {
                    row["approval_request_id"]
                    for row in records
                    if row["approval_request_id"] is not None
                }
            )
        ),
    )
