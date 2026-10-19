"""RPT-53 Contract_Live dataset: all effective dates, exact trace inputs, retained reruns."""

import json
from dataclasses import replace
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import Date, DateTime

from erev_api.db.tables import contract_version, obligation_version
from erev_api.domain.reports import exact_sources, legacy_columns, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_history as history
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_legacy_contract_live"
EVIDENCE: Final = "extract_legacy_contract_live_v1"


def _restore(record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    for column in obligation_version.c:
        if row.get(column.name) is None:
            continue
        if isinstance(column.type, DateTime):
            row[column.name] = datetime.fromisoformat(row[column.name])
        elif isinstance(column.type, Date):
            row[column.name] = date.fromisoformat(row[column.name])
    for key in ("processed_at", "version_known_at"):
        if row.get(key) is not None:
            row[key] = datetime.fromisoformat(row[key])
    return row


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_legacy_contract_live has no lock dataset.")
    if params.book_code != legacy_columns.BOOK:
        raise tie_outs.invalid("book", "The legacy Contract_Live dataset requires ASC606.")
    cutoff = params.binding.cutoff if params.binding is not None else params.known_at
    if params.sources is not None:
        params.sources.record_cutoff(cutoff)
    mode = params.parameters.get("mode", "FULL")
    since = instant(params, "known_since")
    if mode not in {"FULL", "INCREMENTAL"}:
        raise tie_outs.invalid("mode", "Choose Full or Incremental.")
    if mode == "INCREMENTAL" and (since is None or since >= cutoff):
        raise tie_outs.invalid("known_since", "Enter a time before the source time.")
    if params.binding is None:
        where = [contract_version.c.created_at <= cutoff, obligation_version.c.created_at <= cutoff]
        if mode == "INCREMENTAL":
            where.append(obligation_version.c.created_at > since)
        rows = history.population(
            uow.session,
            replace(params, historical=True),
            book_code=legacy_columns.BOOK,
            where=where,
        )
        previous = history.previous_versions(uow.session, rows)
        exact_sources.attach_exact_texts(uow.session, [*rows, *previous.values()])
        evidence = json.loads(
            canonical_bytes(
                redact_contacts(
                    {
                        "rows": rows,
                        "previous": {str(key): value for key, value in previous.items()},
                    }
                )
            )
        )
        tie_outs.record_evidence(params, EVIDENCE, evidence)
    else:
        evidence = tie_outs.bound_evidence(params, EVIDENCE)
    rows = [_restore(row) for row in evidence["rows"]]
    previous = {UUID(key): _restore(value) for key, value in evidence["previous"].items()}
    scope = {str(entity) for entity in params.entity_ids}
    for row in [*rows, *previous.values()]:
        if str(row["contracting_entity_id"]) not in scope:
            raise Problem("forbidden", "The retained legacy input exceeds the report entity scope.")
    for row in rows:
        if (
            row["book_code"] != legacy_columns.BOOK
            or row["created_at"] > cutoff
            or row["version_known_at"] > cutoff
            or (mode == "INCREMENTAL" and since is not None and row["created_at"] <= since)
        ):
            raise Problem(
                "invalid-transition", "Retained legacy input lies outside the extract window."
            )
    items = tuple(
        {
            "row_key": (
                f"version:{row['contract_external_id']}:{row['chain_version_no']}"
                f":{row['obligation_key']}"
            ),
            **legacy_columns.legacy_row(row, history.previous_of(previous, row)),
        }
        for row in rows
    )
    return ReportData(legacy_columns.COLUMNS, items, {"row_count": len(items)})
