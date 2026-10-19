"""Capture production journal revenue for the scenario's fixed snapshot cutoff.

Sandbox snapshots deliberately do not copy journals (SBX-03). Refresh orchestration must
retain this capture separately before replay; scenario-generated journals are not actuals.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_api.auth.dependencies import require_for_entity
from erev_api.domain.reports import forecast_actual_labels
from erev_api.domain.reports.builders import ReportParams, SourceCollector, extract_journal_lines
from erev_api.domain.reports.builders.je_population import Transition, state_as_of
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def capture(uow: UnitOfWork, params: ReportParams) -> dict[str, Any]:
    """Read under the source requester's production permissions; never widen the cutoff."""
    if (
        uow.ctx.tenant_kind != TenantKind.PRODUCTION
        or uow.principal.kind != PrincipalKind.USER
        or uow.principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    if (
        params.known_at.utcoffset() is None
        or params.known_at > uow.now
        or params.book_code not in ("ASC606", "IFRS15")
        or not params.entity_ids
        or len(set(params.entity_ids)) != len(params.entity_ids)
        or params.binding is not None
        or params.period_lock_id is not None
        or params.filters
    ):
        raise Problem("validation-failed", "Invalid production actuals capture scope.")
    for entity_id in params.entity_ids:
        require_for_entity(uow.ctx, "report.run", entity_id)
    sources = SourceCollector()
    extract_journal_lines.build(
        uow,
        replace(
            params,
            report_code="extract_journal_lines",
            report_version=1,
            parameters={"mode": "FULL"},
            historical=True,
            sources=sources,
        ),
    )
    records = sources.evidence.get(extract_journal_lines.EVIDENCE)
    if not isinstance(records, list):
        raise Problem("precondition-failed", "The production journal capture is unavailable.")
    return {
        "schema_version": 1,
        "source_tenant_id": str(uow.principal.tenant_id),
        "known_at": params.known_at.isoformat(),
        "book_code": params.book_code,
        "entity_ids": sorted(str(entity) for entity in params.entity_ids),
        "rows": forecast_actual_labels.attach(
            uow.session,
            posted_rows(
                records,
                known_at=params.known_at,
                entity_ids=params.entity_ids,
                book_code=params.book_code,
            ),
            known_at=params.known_at,
            book_code=params.book_code,
        ),
    }


def posted_rows(
    records: Sequence[Mapping[str, Any]],
    *,
    known_at: datetime,
    entity_ids: Sequence[UUID],
    book_code: str,
) -> list[dict[str, Any]]:
    """Retain signed debit/credit source amounts only for batches acknowledged by the cutoff.

    A partial export may have only some batches acknowledged. Run approval/export alone does
    not establish a posting. Cancellation is evaluated historically, not from today's status.
    """
    scope = {str(entity) for entity in entity_ids}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if record["account_role"] != "REVENUE":
            continue
        if record["entity_id"] not in scope or record["book_code"] != book_code:
            raise Problem("precondition-failed", "A captured journal exceeds the actuals scope.")
        if datetime.fromisoformat(record["created_at"]) > known_at:
            raise Problem("precondition-failed", "A captured journal exceeds the actuals cutoff.")
        state_input = dict(record)
        for key in extract_journal_lines.STATE_TIMES:
            if state_input.get(key) is not None:
                state_input[key] = datetime.fromisoformat(state_input[key])
        history = tuple(
            Transition(datetime.fromisoformat(item["at"]), item["seq"], item["state"])
            for item in record["_transitions"]
        )
        state = state_as_of(state_input, known_at, history)
        if state.cancelled or state.acknowledged_at is None:
            continue
        identity = str(record["id"])
        if identity in seen:
            raise Problem("precondition-failed", "The actuals capture contains duplicate lines.")
        seen.add(identity)
        rows.append(
            {
                key: record[key]
                for key in (
                    "id",
                    "journal_entry_id",
                    "journal_batch_id",
                    "run_id",
                    "entity_id",
                    "book_code",
                    "period_id",
                    "period_key",
                    "contract_id",
                    "obligation_id",
                    "dimensions",
                    "txn_currency",
                    "debit_txn",
                    "credit_txn",
                    "functional_currency",
                    "debit_functional",
                    "credit_functional",
                    "created_at",
                )
            }
            | {
                "acknowledged_at": state.acknowledged_at.isoformat(),
                "run_state_at_cutoff": state.run_state,
            }
        )
    return sorted(rows, key=lambda row: row["id"])
