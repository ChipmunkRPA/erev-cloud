"""Persist upgrade attribution and portion outcomes alongside the computation's postings."""

import hashlib
from typing import Any
from uuid import UUID

from erev_engine import upgrade
from erev_engine.bundle import InputBundle, OutputBundle
from sqlalchemy import insert, select, text

from erev_api.db import new_id
from erev_api.db.tables import (
    computation_evidence,
    contract_computation,
    period,
    posting_attribution,
    release_group_processing,
    release_validation,
    release_validation_group,
    subledger_line,
)
from erev_api.enums import UpgradeProcessingState
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from . import bundles, upgrade_report


def _previous_input(uow: UnitOfWork, predecessor: UUID | None, group_id: UUID) -> bytes | None:
    if predecessor is None:
        return None
    source = (
        uow.session.execute(
            select(computation_evidence, contract_computation.c.engine_version)
            .join(
                contract_computation,
                (contract_computation.c.tenant_id == computation_evidence.c.tenant_id)
                & (contract_computation.c.id == computation_evidence.c.contract_computation_id),
            )
            .where(
                computation_evidence.c.tenant_id == uow.principal.tenant_id,
                computation_evidence.c.contract_computation_id == predecessor,
                contract_computation.c.combination_group_id == group_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        return None  # Historical computations are never backfilled from current facts.
    metadata, stream = open_file(
        uow.session, source["input_file_id"], files=uow.files, keyring=uow.keyring
    )
    with stream:
        content = stream.read()
    digest = hashlib.sha256(content).hexdigest()
    if (
        metadata["purpose"] != "COMPUTATION_INPUT"
        or metadata["media_type"] != "application/json"
        or metadata["size_bytes"] != len(content)
        or metadata["sha256"] != digest
        or source["input_file_sha256"] != digest
    ):
        raise Problem("validation-failed", "Previous computation input failed integrity checks.")
    try:
        decoded = upgrade.decode_input(content)
    except (ValueError, TypeError):
        return None  # Unsupported historical encoding cannot establish an upgrade-only cause.
    if (
        decoded.sha256() != source["input_sha256"]
        or decoded.engine_version != source["engine_version"]
    ):
        raise Problem("validation-failed", "Previous computation input identity differs.")
    return content


def record(
    uow: UnitOfWork,
    bundle: InputBundle,
    output: OutputBundle,
    found: bundles.BundleIndex,
    *,
    computation_id: UUID,
    release_id: UUID,
    predecessor: UUID | None,
    posting_ids: dict[str, str],
) -> dict[str, list[UUID]]:
    """Append facts in the caller's transaction, before advancing computation heads.

    This is upgrade bookkeeping for enabled releases; admission of candidate computations
    is a separate gate. Every actual posting is attributed before any portion becomes terminal.
    """
    facts: dict[str, list[UUID]] = {"posting_attribution": [], "release_group_processing": []}
    tenant = uow.principal.tenant_id
    group_id = UUID(str(found.group["id"]))
    parent = (
        uow.session.execute(
            select(release_validation).where(
                release_validation.c.tenant_id == tenant,
                release_validation.c.engine_release_id == release_id,
                release_validation.c.effective_level.in_(("MINOR", "MAJOR")),
                release_validation.c.status.in_(("PASSED", "APPROVED")),
                release_validation.c.enabled_at.is_not(None),
            )
        )
        .mappings()
        .one_or_none()
    )
    if parent is None:
        return facts
    if parent["accepted_attempt_id"] is None or parent["processing_seed"] is None:
        raise Problem("validation-failed", "The enabled upgrade has no sealed processing queue.")
    if not uow.session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"erev:upgrade-group:{tenant}:{group_id}"},
    ):
        raise Problem("lock-conflict")
    latest = (
        uow.session.execute(
            select(release_group_processing)
            .where(
                release_group_processing.c.tenant_id == tenant,
                release_group_processing.c.release_validation_id == parent["id"],
                release_group_processing.c.combination_group_id == group_id,
            )
            .distinct(release_group_processing.c.entity_id, release_group_processing.c.book_code)
            .order_by(
                release_group_processing.c.entity_id,
                release_group_processing.c.book_code,
                release_group_processing.c.seq.desc(),
            )
        )
        .mappings()
        .all()
    )
    pending = [
        row for row in latest if row["upgrade_state"] in {"PENDING", "DEFERRED_NO_OPEN_PERIOD"}
    ]
    if not pending:
        return facts
    attempt_id = parent["accepted_attempt_id"]
    if any(row["release_validation_attempt_id"] != attempt_id for row in latest):
        raise Problem("validation-failed", "Processing rows name another accepted attempt.")
    stamps = {
        "tenant_id": tenant,
        "created_at": uow.now,
        "created_by": uow.principal.id,
        "created_by_kind": uow.principal.kind.value,
    }
    entities = {UUID(str(row["id"])): code for code, row in found.entities.items()}
    entity_inputs = {entity.code: entity for entity in bundle.entities}
    output_books = {book.book_code for book in output.books}
    lines_by_posting: dict[UUID, list[dict[str, Any]]] = {}
    if posting_ids:
        origin = period.alias("upgrade_origin")
        lines = (
            uow.session.execute(
                select(
                    subledger_line.c.subledger_posting_id,
                    subledger_line.c.entity_id,
                    subledger_line.c.book_code,
                    subledger_line.c.period_id,
                    subledger_line.c.origin_period_id,
                    period.c.period_key,
                    origin.c.period_key.label("origin_period_key"),
                )
                .join(
                    period,
                    (period.c.tenant_id == subledger_line.c.tenant_id)
                    & (period.c.id == subledger_line.c.period_id),
                )
                .outerjoin(
                    origin,
                    (origin.c.tenant_id == subledger_line.c.tenant_id)
                    & (origin.c.id == subledger_line.c.origin_period_id),
                )
                .where(
                    subledger_line.c.tenant_id == tenant,
                    subledger_line.c.subledger_posting_id.in_(
                        [UUID(v) for v in posting_ids.values()]
                    ),
                )
                .distinct()
            )
            .mappings()
            .all()
        )
        for line in lines:
            lines_by_posting.setdefault(line["subledger_posting_id"], []).append(dict(line))
        previous = _previous_input(uow, predecessor, group_id)
        sampled = (
            uow.session.scalar(
                select(release_validation_group.c.selection).where(
                    release_validation_group.c.tenant_id == tenant,
                    release_validation_group.c.release_validation_attempt_id == attempt_id,
                    release_validation_group.c.combination_group_id == group_id,
                )
            )
            == "SAMPLED"
        )
        for value in posting_ids.values():
            posting_id = UUID(value)
            rows = lines_by_posting.get(posting_id)
            if not rows:
                raise Problem("validation-failed", "An upgrade posting has no retained lines.")
            periods = [
                {
                    key: (None if value is None else str(value))
                    for key, value in row.items()
                    if key != "subledger_posting_id"
                }
                for row in rows
            ]
            periods.sort(key=lambda row: tuple(row[key] or "" for key in sorted(row)))
            attribution = upgrade_report.attribution_row(
                posting_id=posting_id,
                attempt_id=attempt_id,
                group_id=group_id,
                computation_id=computation_id,
                previous_computation_id=predecessor,
                previous_evidence=previous,
                current=bundle,
                sampled=sampled,
                origin_periods={"periods": periods},
                now=uow.now,
            )
            row_id = new_id()
            uow.session.execute(
                insert(posting_attribution).values(
                    **stamps,
                    id=row_id,
                    subledger_posting_id=posting_id,
                    release_validation_attempt_id=attempt_id,
                    combination_group_id=group_id,
                    contract_computation_id=computation_id,
                    previous_computation_id=predecessor,
                    cause=attribution.cause.value,
                    sampled=sampled,
                    origin_periods=dict(attribution.origin_periods),
                    input_comparison=dict(attribution.input_comparison),
                )
            )
            facts["posting_attribution"].append(row_id)
    for row in pending:
        entity_code = entities.get(row["entity_id"])
        entity = entity_inputs.get(entity_code or "")
        if entity is None or row["book_code"] not in output_books:
            raise Problem(
                "validation-failed", "The computation omits an unsettled upgrade portion."
            )
        prior = upgrade_report.PortionEvent(
            group_id,
            entity.code,
            row["book_code"],
            row["seq"],
            UpgradeProcessingState(row["upgrade_state"]),
            row["contract_computation_id"],
            tuple(row["subledger_posting_ids"]),
            tuple(row["unresolved_origin_period_keys"]),
            row["reason"],
            row["created_at"],
        )
        unresolved = upgrade_report.unresolved_origins(
            entity,
            row["book_code"],
            upgrade_report.conservative_origins(
                entity, row["book_code"], bundle=bundle, output=output
            ),
        )
        portion_postings = [
            posting
            for posting, lines in lines_by_posting.items()
            if any(
                line["entity_id"] == row["entity_id"] and line["book_code"] == row["book_code"]
                for line in lines
            )
        ]
        event = upgrade_report.portion_transition(
            prior,
            computation_id=computation_id,
            posting_ids=portion_postings,
            unresolved=unresolved,
            now=uow.now,
        )
        assert event is not None
        row_id = new_id()
        uow.session.execute(
            insert(release_group_processing).values(
                **stamps,
                id=row_id,
                release_validation_id=parent["id"],
                release_validation_attempt_id=attempt_id,
                combination_group_id=group_id,
                entity_id=row["entity_id"],
                book_code=row["book_code"],
                seq=event.seq,
                upgrade_state=event.state.value,
                contract_computation_id=computation_id,
                subledger_posting_ids=list(event.posting_ids),
                unresolved_origin_period_keys=list(event.unresolved_origin_period_keys),
                reason=event.reason,
            )
        )
        facts["release_group_processing"].append(row_id)
    return facts
