"""Retained acquisition-cell contributions, including the presented reporting amounts."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import calc_trace
from erev_api.problems import Problem

from . import tie_outs
from .acquisition_flows import KEY as FLOW_KEY
from .builders import ReportParams
from .builders.contract_balance_rollforward import ContractRollforward

KEY = "acquisition_rollforward_cells_v1"
KIND = "acquisition_disclosure_contribution"


def retain(
    params: ReportParams,
    items: Sequence[ContractRollforward],
    rows: Sequence[Mapping[str, Any]],
    role: str,
    rates: list[dict[str, Any]],
) -> None:
    if params.binding is None and params.sources is None:
        return  # Internal close calculations do not create an explainable report run.
    if params.binding is not None and KEY not in params.binding.evidence:
        return
    evidence = (
        params.binding.evidence
        if params.binding is not None
        else (params.sources.evidence if params.sources is not None else {})
    )
    facts = evidence.get(FLOW_KEY, {})
    sources: dict[str, dict[str, Any]] = {}
    for item in items:
        original = {
            key: value
            for key, value in facts.items()
            if key.split(":")[1:3] == [str(item.contract_id), str(item.entity_id)]
        }
        amounts = item.lines["BUSINESS_COMBINATIONS"]
        if not original:
            if any(amounts[name] != 0 for name in tie_outs.ROLLFORWARD_BALANCES):
                raise tie_outs.invalid(
                    "currency_view", "Acquisition cell lacks retained original sources."
                )
            continue
        row_key = f"contract:{item.external_id}:{item.entity_code}"
        sources[row_key] = {
            "contract_id": str(item.contract_id),
            "entity_id": str(item.entity_id),
            "currency": item.currency,
            "values": {
                name: tie_outs.money(amounts[name], item.currency)
                for name in tie_outs.ROLLFORWARD_BALANCES
            },
            "original": original,
            "rates": [rate for rate in rates if rate["entity_code"] == item.entity_code],
        }
    cells: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("line_code") == "BUSINESS_COMBINATIONS":
            selected = [
                key for key, value in sources.items() if value["currency"] == row["currency"]
            ]
            values = {name: row[name] for name in tie_outs.ROLLFORWARD_BALANCES}
        elif row["row_key"] in sources:
            selected = [row["row_key"]]
            values = {"business_combinations": row["business_combinations"]}
        else:
            continue
        for column, value in values.items():
            measure = role if column == "business_combinations" else column
            total = sum(
                (Decimal(sources[key]["values"][measure]["amount"]) for key in selected), Decimal(0)
            )
            if total != Decimal(value["amount"]):
                raise tie_outs.invalid(
                    "currency_view", "Acquisition contributions do not reconcile to the cell."
                )
        cells[row["row_key"]] = {"values": values, "sources": sorted(selected)}
    captured = {"role": role, "cells": cells, "sources": sources}
    if params.binding is not None and params.binding.evidence[KEY] != captured:
        raise tie_outs.invalid("currency_view", "Retained acquisition cell contributions differ.")
    tie_outs.record_evidence(params, KEY, captured)


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    evidence = {} if params.binding is None else params.binding.evidence.get(KEY, {})
    held = evidence.get("cells", {}).get(row_key)
    if held is None or column_key not in held["values"]:
        raise Problem("not-found", "This cell has no retained acquisition contributions.")
    selected = [(key, evidence["sources"][key]) for key in held["sources"]]
    versions = {UUID(key.split(":")[0]) for _, source in selected for key in source["original"]}
    traces = (
        {
            str(row[0]): str(row[1])
            for row in session.execute(
                select(calc_trace.c.contract_version_id, calc_trace.c.id).where(
                    calc_trace.c.contract_version_id.in_(versions)
                )
            )
        }
        if versions
        else {}
    )
    if set(traces) != {str(version) for version in versions}:
        raise Problem("not-found", "Original acquisition trace is unavailable.")
    measure = evidence["role"] if column_key == "business_combinations" else column_key
    items = []
    for key, source in selected:
        details = ["Acquired carrying balance; not billing or current-period revenue."]
        links = [
            {
                "label": "Original contract history",
                "href": f"/contracts/{source['contract_id']}/history",
            }
        ]
        for identity, original in sorted(source["original"].items()):
            version, _, _, period = identity.split(":")
            details.extend(
                [
                    f"Original opening event: {original['event_key']}; cutover period: {period}",
                    f"Original {measure}: {original['amounts'][measure]} {original['currency']}",
                    f"Input SHA-256: {original['input_sha256']}",
                    f"Output SHA-256: {original['output_sha256']}",
                ]
            )
            for node in original["nodes"]:
                if node.split(":", 1)[0] in {measure, f"{measure}_functional"}:
                    links.append(
                        {
                            "label": f"Original acquisition calculation · {node}",
                            "href": f"/trace/{traces[version]}?node={quote(node, safe='')}",
                        }
                    )
        if source["rates"]:
            details.append(
                "Reporting translation uses the retained period-average rate; "
                "translation and rounding remain separate lines."
            )
            details.extend(
                f"{rate['period_key']} {rate['rate_type']}: "
                f"{rate['base_currency']} to {rate['quote_currency']} at {rate['rate']}"
                for rate in source["rates"]
            )
        items.append(
            {
                "object_type": KIND,
                "id": uuid5(NAMESPACE_URL, f"erev:acquisition:{source['entity_id']}:{key}"),
                "measure": measure,
                "value": source["values"][measure],
                "href": "",
                "details": [],
                "_entity_id": source["entity_id"],
                "_source_set_entity_ids": [source["entity_id"]],
                "_source_set_details": details,
                "_source_set_links": links,
            }
        )
    value = held["values"][column_key]
    if sum((Decimal(item["value"]["amount"]) for item in items), Decimal(0)) != Decimal(
        value["amount"]
    ):
        raise Problem("not-found", "Acquisition cell contributions differ from its retained value.")
    return value, items
