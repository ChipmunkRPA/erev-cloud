"""Retained group split-report cell values and complete original source sets."""

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import calc_trace
from erev_api.problems import Problem

from . import acquisition_cells, split_groups, tie_outs
from .builders import ReportParams
from .builders.contract_balance_rollforward import ContractRollforward

KEY = "foreign_split_cells_v1"
KIND = "split_disclosure_contribution"


def retain(
    params: ReportParams,
    items: Sequence[ContractRollforward],
    rows: Sequence[Mapping[str, Any]],
    role: str,
    rates: list[dict[str, Any]],
) -> None:
    if (params.binding is None and params.sources is None) or (
        params.binding is not None and KEY not in params.binding.evidence
    ):
        return
    if params.binding is not None:
        evidence = params.binding.evidence
    else:
        assert params.sources is not None
        evidence = params.sources.evidence
    groups = evidence.get(split_groups.KEY, {})
    cells = {}
    for item in items:
        source = groups.get(str(item.contract_id))
        if source is None:
            continue
        keys = {
            f"contract:{item.external_id}:{item.entity_code}",
            *[f"member-endpoints:{m.external_id}:{m.entity_code}" for m in item.group_members],
        }
        for row in rows:
            if row["row_key"] not in keys:
                continue
            values = {
                k: v
                for k, v in row.items()
                if isinstance(v, dict) and set(v) >= {"amount", "currency"}
            }
            cells[row["row_key"]] = {
                "values": values,
                "entity_id": str(item.entity_id),
                "currency": item.currency,
                "members": [
                    {"contract_id": str(m.contract_id), "external_id": m.external_id}
                    for m in item.group_members
                ],
                "source": source,
                "rates": [r for r in rates if r["entity_code"] == item.entity_code],
            }
    captured = {"role": role, "cells": cells}
    if params.binding is not None and params.binding.evidence[KEY] != captured:
        raise tie_outs.invalid("currency_view", "Retained split cell sources differ.")
    tie_outs.record_evidence(params, KEY, captured)


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[Mapping[str, str], list[dict[str, Any]]]:
    held = {} if params.binding is None else params.binding.evidence.get(KEY, {}).get("cells", {})
    source = held.get(row_key)
    if source is None or column_key not in source["values"]:
        return acquisition_cells.cell(session, params, row_key, column_key)
    versions = set(source["source"]["member_versions"].values())
    traces = {
        str(v): str(t)
        for v, t in session.execute(
            select(calc_trace.c.contract_version_id, calc_trace.c.id).where(
                calc_trace.c.contract_version_id.in_([UUID(v) for v in versions])
            )
        )
    }
    if set(traces) != versions:
        raise Problem("not-found", "Original split trace is unavailable.")
    details = [
        "Original group movements; member movements are unallocated.",
        "Collection dates and FX layers retain their original sources.",
        f"Input SHA-256: {source['source']['input_sha256']}",
        f"Output SHA-256: {source['source']['output_sha256']}",
    ]
    links = [
        {
            "label": f"Member history · {m['external_id']}",
            "href": f"/contracts/{m['contract_id']}/history",
        }
        for m in source["members"]
    ]
    for version, nodes in source["source"].get("trace_nodes", {}).items():
        links.extend(
            {
                "label": f"Original split calculation · {node}",
                "href": f"/trace/{traces[version]}?node={quote(node, safe='')}",
            }
            for node in nodes
        )
    details.extend(
        f"Original {s['period_key']} {s['view']} snapshot; movements and FX shown separately."
        for s in source["source"]["snapshots"]
    )
    details.extend(
        f"{r['period_key']} {r['rate_type']}: {r['base_currency']} "
        f"to {r['quote_currency']} at {r['rate']}"
        for r in source["rates"]
    )
    value = source["values"][column_key]
    return value, [
        {
            "object_type": KIND,
            "id": uuid5(NAMESPACE_URL, f"erev:split-cell:{row_key}:{column_key}"),
            "measure": column_key,
            "value": value,
            "href": "",
            "details": [],
            "_entity_id": source["entity_id"],
            "_source_set_entity_ids": [source["entity_id"]],
            "_source_set_details": details,
            "_source_set_links": links,
        }
    ]
