"""Retained version inputs shared by the two 71-column contract exports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes

from erev_api.domain.reports import legacy_columns, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_history as history
from erev_api.domain.reports.outputs import ReportData
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

EVIDENCE: Final = "legacy_contract_inputs_v1"
HISTORY: Final = "legacy_contract_history_export"


def selection(params: ReportParams) -> dict[str, Any]:
    return {
        key: params.parameters.get(key)
        for key in (
            "book",
            "as_of",
            "from_date",
            "to_date",
            "contract_external_id",
        )
    }


def bound_data(uow: UnitOfWork, params: ReportParams) -> ReportData | None:
    if params.binding is None:
        return None
    retained = tie_outs.bound_evidence(params, EVIDENCE)
    if retained["tenant_id"] != str(uow.principal.tenant_id) or set(retained["entity_ids"]) != {
        str(entity_id) for entity_id in params.entity_ids
    }:
        raise Problem("forbidden", "Retained legacy contract inputs exceed report scope.")
    if retained["report_code"] != params.report_code or retained["selection"] != selection(params):
        raise tie_outs.invalid("book", "Retained inputs use another legacy export selection.")
    return data_from_inputs(retained)


def pack_row(row: Mapping[str, Any]) -> dict[str, Any]:
    # Preserve source types used by the legacy date and processing-time formatters. Monetary
    # values remain canonical decimal strings; the legacy calculations parse these exactly.
    return {
        "values": dict(row),
        "dates": [key for key, value in row.items() if type(value) is date],
        "timestamps": [key for key, value in row.items() if isinstance(value, datetime)],
    }


def unpack_row(stored: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(stored["values"])
    for key in stored["dates"]:
        row[key] = date.fromisoformat(row[key])
    for key in stored["timestamps"]:
        row[key] = datetime.fromisoformat(row[key].replace("Z", "+00:00"))
    return row


def retain(
    uow: UnitOfWork,
    params: ReportParams,
    rows: Sequence[Mapping[str, Any]],
    previous: Mapping[UUID, Mapping[str, Any]],
    bounds: Mapping[str, date],
) -> ReportData:
    inputs = []
    for row in rows:
        prior = history.previous_of(previous, row)
        inputs.append(
            {"current": pack_row(row), "previous": None if prior is None else pack_row(prior)}
        )
    tie_outs.record_members(
        params,
        "legacy_export_obligation_versions",
        (row["id"] for row in [*rows, *previous.values()]),
    )
    retained = json.loads(
        canonical_bytes(
            {
                "tenant_id": uow.principal.tenant_id,
                "entity_ids": params.entity_ids,
                "report_code": params.report_code,
                "selection": selection(params),
                "bounds": dict(bounds),
                "inputs": inputs,
            }
        )
    )
    tie_outs.record_evidence(params, EVIDENCE, retained)
    return data_from_inputs(retained)


def data_from_inputs(retained: Mapping[str, Any]) -> ReportData:
    items = []
    for entry in retained["inputs"]:
        row = unpack_row(entry["current"])
        prior = None if entry["previous"] is None else unpack_row(entry["previous"])
        key = (
            f"version:{row['contract_external_id']}:{row['chain_version_no']}:{row['obligation_key']}"
            if retained["report_code"] == HISTORY
            else f"obligation:{row['contract_external_id']}:{row['obligation_key']}"
        )
        items.append({"row_key": key, **legacy_columns.legacy_row(row, prior)})
    return ReportData(
        columns=legacy_columns.COLUMNS,
        rows=tuple(items),
        control_totals={"row_count": len(items), **retained["bounds"]},
    )
