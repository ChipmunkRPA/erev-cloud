"""Contract sample journal evidence, including contracts hidden by journal aggregation.

Retain the whole journal line and its source breakdown separately from the sampled
contracts' contribution. A sample is not a balanced batch, and these totals are not a
claim that the sampled contribution was exported as a separate GL document.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal, localcontext
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import func, select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    approval_request,
    contract,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    period,
    subledger_line,
)
from erev_api.domain.journals import subledger
from erev_api.domain.journals.queries import drill_ids
from erev_api.domain.reports import journal_history
from erev_api.domain.reports.builders.extract_journal_lines import COLUMNS, STATE_TIMES
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class SampleJournals:
    files: tuple[PackFile, ...]
    contract_ids: tuple[UUID, ...]
    entity_ids: tuple[UUID, ...]
    approval_request_ids: tuple[UUID, ...]


def _invalid() -> Problem:
    return Problem("validation-failed", "The sample journal cannot be reconciled to its sources.")


def collect(uow: UnitOfWork, selected: SourceSelection, *, as_of: date) -> SampleJournals:
    cutoff = selected.known_at
    if (
        selected.tenant_id != uow.principal.tenant_id
        or not selected.contract_ids
        or cutoff.tzinfo is None
        or cutoff > uow.now
        or not PERMISSIONS <= uow.principal.permissions
    ):
        raise Problem("forbidden")
    if as_of > cutoff.astimezone(UTC).date():
        raise Problem("validation-failed", "The sample date exceeds its source cutoff.")
    for entity in selected.entity_ids:
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity)
    tenant = selected.tenant_id
    # Posting entities may differ from the contracting entity (including intercompany
    # lines). Resolve the complete sample footprint before selecting journal candidates.
    with system_entity_scope(uow.session):
        owners = uow.session.execute(
            select(contract.c.id, contract.c.contracting_entity_id).where(
                contract.c.tenant_id == tenant,
                contract.c.id.in_(selected.contract_ids),
            )
        ).all()
        posting_entities = set(
            uow.session.execute(
                select(subledger_line.c.entity_id)
                .where(
                    subledger_line.c.tenant_id == tenant,
                    subledger_line.c.contract_id.in_(selected.contract_ids),
                    subledger_line.c.recorded_at <= cutoff,
                    subledger.recorded_by(cutoff, historical=True),
                    subledger_line.c.effective_date <= as_of,
                )
                .distinct()
            ).scalars()
        )
    if {owner.id for owner in owners} != set(selected.contract_ids):
        raise Problem("not-found")
    footprint = posting_entities | {owner.contracting_entity_id for owner in owners}
    for entity in footprint:
        if uow.principal.entity_scope != "*" and entity not in uow.principal.entity_scope:
            raise Problem("not-found")
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity)
    candidates = [
        dict(row)
        for row in uow.session.execute(
            select(
                *(journal_line.c[col.key] for col in COLUMNS[:-4]),
                func.erev.source_commit_time("journal_line", journal_line.c.id).label(
                    "line_committed_at"
                ),
                journal_entry.c.je_no,
                journal_run.c.run_no,
                journal_batch.c.external_id.label("batch_external_id"),
                period.c.period_key,
                period.c.end_date.label("period_end"),
                period.c.updated_at.label("period_updated_at"),
                journal_run.c.id.label("run_id"),
                journal_run.c.state.label("run_state"),
                *(journal_run.c[key.removeprefix("run_")].label(key) for key in STATE_TIMES[:-1]),
                journal_batch.c.acknowledged_at.label("batch_acknowledged_at"),
            )
            .select_from(journal_line)
            .join(
                journal_entry,
                (journal_entry.c.tenant_id == journal_line.c.tenant_id)
                & (journal_entry.c.id == journal_line.c.journal_entry_id)
                & (journal_entry.c.journal_batch_id == journal_line.c.journal_batch_id),
            )
            .join(
                journal_batch,
                (journal_batch.c.tenant_id == journal_line.c.tenant_id)
                & (journal_batch.c.id == journal_line.c.journal_batch_id),
            )
            .join(
                journal_run,
                (journal_run.c.tenant_id == journal_batch.c.tenant_id)
                & (journal_run.c.id == journal_batch.c.journal_run_id),
            )
            .join(
                period,
                (period.c.tenant_id == journal_line.c.tenant_id)
                & (period.c.id == journal_line.c.period_id),
            )
            .where(
                journal_line.c.tenant_id == tenant,
                journal_line.c.entity_id.in_(footprint),
                journal_line.c.created_at <= cutoff,
                func.erev.source_commit_time("journal_line", journal_line.c.id) <= cutoff,
                journal_entry.c.created_at <= cutoff,
                journal_batch.c.created_at <= cutoff,
                journal_run.c.created_at <= cutoff,
            )
            .order_by(journal_run.c.run_no, journal_entry.c.je_no, journal_line.c.line_no)
        ).mappings()
    ]
    candidates = journal_history.restore(
        uow.session, candidates, cutoff, batch_key="journal_batch_id"
    )
    records = []
    contracts = set(selected.contract_ids)
    entities = set(selected.entity_ids) | footprint
    runs: set[UUID] = set()
    for row in candidates:
        if row["period_updated_at"] > cutoff:
            raise Problem("validation-failed", "Historical journal period dates are unavailable.")
        if row["period_end"] > as_of:
            continue
        ids = drill_ids(uow.session, row["id"], files=uow.files, keyring=uow.keyring)
        sources = [
            dict(item)
            for item in uow.session.execute(
                select(
                    subledger_line,
                    func.erev.subledger_commit_time(subledger_line.c.subledger_posting_id).label(
                        "committed_server_at"
                    ),
                )
                .where(
                    subledger_line.c.tenant_id == tenant,
                    subledger_line.c.id.in_(ids),
                )
                .order_by(subledger_line.c.id)
            ).mappings()
        ]
        if (
            len(ids) != len(set(ids))
            or len(sources) != row["source_line_count"]
            or len(sources) != len(ids)
        ):
            raise _invalid()
        sampled = [item for item in sources if item["contract_id"] in selected.contract_ids]
        if not sampled:
            continue
        members = {item["contract_id"] for item in sources}
        with system_entity_scope(uow.session):
            owners = uow.session.execute(
                select(contract.c.id, contract.c.contracting_entity_id).where(
                    contract.c.tenant_id == tenant,
                    contract.c.id.in_(members),
                )
            ).all()
        if {owner.id for owner in owners} != members:
            raise Problem("not-found")
        source_entities = {owner.contracting_entity_id for owner in owners} | {
            item["entity_id"] for item in sources
        }
        for entity in source_entities:
            if uow.principal.entity_scope != "*" and entity not in uow.principal.entity_scope:
                raise Problem("not-found")
            for permission in PERMISSIONS:
                require_for_entity(uow.ctx, permission, entity)
        for item in sources:
            if (
                item["committed_server_at"] is None
                or item["committed_server_at"] > cutoff
                or item["recorded_at"] > cutoff
                or item["created_at"] > cutoff
                or item["recorded_server_at"] > cutoff
                or item["effective_date"] > as_of
                or item["entity_id"] != row["entity_id"]
                or item["txn_currency"] != row["txn_currency"]
                or item["functional_currency"] != row["functional_currency"]
            ):
                raise _invalid()
        with localcontext() as context:
            context.prec = 80
            contribution = {}
            for basis in ("txn", "functional"):
                total = sum((item[f"amount_{basis}"] for item in sources), Decimal(0))
                if total != row[f"debit_{basis}"] - row[f"credit_{basis}"]:
                    raise _invalid()
                contribution[f"net_{basis}"] = sum(
                    (item[f"amount_{basis}"] for item in sampled), Decimal(0)
                )
        records.append(
            {
                "line": {column.key: row[column.key] for column in COLUMNS},
                "run_id": row["run_id"],
                "run_state_as_of": row["run_state"],
                "approved_at_as_of": row["run_approved_at"],
                "batch_acknowledged_at_as_of": row["batch_acknowledged_at"],
                "cancelled_as_of": row["run_state"] == "cancelled",
                "commit_evidence": {
                    "line_committed_at": row["line_committed_at"],
                    "run_revision_id": row["_run_revision_id"],
                    "batch_revision_id": row["_batch_revision_id"],
                },
                "sample_contribution": contribution,
                "sources": [
                    {
                        **{key: value for key, value in item.items() if key != "tenant_id"},
                        "sampled": item["contract_id"] in selected.contract_ids,
                    }
                    for item in sources
                ],
            }
        )
        contracts.update(members)
        entities.update(source_entities)
        runs.add(row["run_id"])
    approvals = (
        tuple(
            uow.session.execute(
                select(approval_request.c.id)
                .where(
                    approval_request.c.tenant_id == tenant,
                    approval_request.c.subject_type == "JOURNAL_RUN",
                    approval_request.c.subject_id.in_(runs),
                    approval_request.c.submitted_at <= cutoff,
                )
                .order_by(approval_request.c.id)
            ).scalars()
        )
        if runs
        else ()
    )
    file = PackFile(
        "sample/journals.json",
        canonical_bytes(
            redact_contacts(
                {
                    "schema_version": 2,
                    "as_of": as_of,
                    "known_at": cutoff,
                    "lines": records,
                    "basis": (
                        "Whole journal lines and sampled contributions; "
                        "cancelled runs are labelled at committed cutoff. "
                        "Original journal and posting commits are retained "
                        "with lifecycle revisions."
                    ),
                }
            )
        ),
    )
    return SampleJournals((file,), tuple(sorted(contracts)), tuple(sorted(entities)), approvals)
