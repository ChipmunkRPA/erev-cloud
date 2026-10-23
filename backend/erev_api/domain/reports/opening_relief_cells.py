"""Retained pre-summary disclosure contributions, with group amounts kept indivisible.

Same-source builds recalculate the disclosure and compare these contributions. Cell reads
explain that retained calculation; they do not allocate its net result to historical layers.
"""

from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import calc_trace, contract
from erev_api.problems import Problem

from . import tie_outs
from .builders import ReportParams

KEY = "opening_relief_cells_v1"
COLUMNS = ("opening_contract_liability", "revenue_recognized", "revenue_from_opening")
POB_KEYS = (
    "opening_relief_pob_v1",
    "opening_relief_functional_pob_v1",
    "opening_relief_reporting_pob_v1",
)


def retain(
    session: Session,
    params: ReportParams,
    rows: list[dict[str, Any]],
    *,
    view: str,
    rates: list[dict[str, Any]],
) -> None:
    sources = [(row, row.pop("_opening_source")) for row in rows]
    # Do not change old bindings or the output they reproduce.
    if params.binding is not None and KEY not in params.binding.evidence:
        return
    evidence = (
        params.binding.evidence
        if params.binding is not None
        else (params.sources.evidence if params.sources is not None else {})
    )
    ids = {UUID(identity) for _, source in sources for identity in source["contracts"]}
    owners = {
        UUID(str(row[0])): UUID(str(row[1]))
        for row in session.execute(
            select(contract.c.id, contract.c.contracting_entity_id).where(contract.c.id.in_(ids))
        ).all()
    }
    if set(owners) != ids:
        raise tie_outs.invalid(
            "currency_view", "Opening disclosure source membership is incomplete."
        )
    retained = {}
    for row, source in sources:
        group_key = source.get("group_key")
        facts: dict[str, Any] = next(
            (evidence[key][group_key] for key in POB_KEYS if group_key in evidence.get(key, {})), {}
        )
        retained[row["row_key"]] = {
            **source,
            "source_entities": sorted(
                {str(owners[UUID(identity)]) for identity in source["contracts"]}
            ),
            "currency_view": view,
            "currency": row["currency"],
            "values": {column: row[column] for column in COLUMNS},
            "pob": facts,
            "translation_rates": [
                rate for rate in rates if rate["entity_code"] == row["entity_code"]
            ],
        }
    if params.binding is not None and params.binding.evidence[KEY] != retained:
        raise tie_outs.invalid(
            "currency_view", "Opening disclosure contributions differ from retained sources."
        )
    tie_outs.record_evidence(params, KEY, retained)


def _details(source: dict[str, Any]) -> list[str]:
    result = [
        "Retained disclosure contribution; no historical-layer ownership amounts are inferred.",
        "Original contracts: " + "; ".join(source["contracts"]),
        "Currency view: " + source["currency_view"],
    ]
    if len(source["contracts"]) > 1:
        result.append("Combined-contract group total. Member relief is not allocated.")
    labels = dict(
        zip(
            COLUMNS,
            ("Opening contract liability", "Revenue recognized", "Revenue from opening"),
            strict=True,
        )
    )
    for column in COLUMNS:
        value = source["values"][column]
        result.append(f"{labels[column]}: {value['amount']} {value['currency']}")
    facts = source["pob"]
    if not facts:
        result.append(
            "Retained contract balance-path contribution; "
            "obligation-level source detail is unavailable for this row."
        )
    members = facts.get("members", {"group": facts})
    # The group key is retained before reporting projection; its currency is the source basis.
    parts = source.get("group_key", "").split(":")
    currency = (
        parts[-1]
        if len(parts) == 3
        else (source["currency"] if source["currency_view"] != "reporting" else "original currency")
    )
    cap_labels = {
        "opening_cap": "Opening liability cap",
        "opening": "Opening liability cap",
        "consumption_cap": "Actual liability consumption",
        "consumed": "Actual liability consumption",
    }
    for name in ("opening_cap", "consumption_cap", "opening", "consumed"):
        if name in facts:
            result.append(f"{cap_labels[name]}: {facts[name]} {currency}")
    for member, detail in sorted(members.items()):
        if not detail:
            continue
        result.append(f"Source member: {member}; computation: {detail.get('version', '')}")
        for name in ("opening_cap", "consumption_cap"):
            if name in detail:
                result.append(f"{cap_labels[name]}: {detail[name]} {currency}")
        result.append(
            "Posted revenue sources: " + "; ".join(map(str, detail.get("posted_lines", [])))
        )
        for subject, obligation in sorted(detail.get("obligations", {}).items()):
            for field, label in (
                ("opening_billing", "Opening attributed billing"),
                ("opening_revenue", "Opening recognized revenue"),
                ("posted_revenue", "Selected-range net posted revenue"),
                ("eligible_relief", "Eligibility before group caps; not allocated group relief"),
            ):
                if field in obligation:
                    result.append(f"{subject} · {label}: {obligation[field]} {currency}")
            result.append(f"{subject}: opening sources {obligation.get('opening_nodes', [])}")
    if "period_relief" in facts:
        result.append(
            "Reporting relief uses signed period changes at each period's retained average rate."
        )
        for period, amount in sorted(facts["period_relief"].items()):
            result.append(f"{period} · Relief before reporting translation: {amount} {currency}")
    for rate in source["translation_rates"]:
        result.append(
            "Retained translation: " + "; ".join(f"{k}={v}" for k, v in sorted(rate.items()))
        )
    return result


def opening_nodes(source: dict[str, Any]) -> list[tuple[str, str, str]]:
    nodes: list[tuple[str, str, str]] = []
    facts = source["pob"]
    for detail in facts.get("members", {"group": facts}).values():
        # An explicit absent frozen opening must never fall back to a newer version.
        frozen = detail.get("frozen_opening")
        version = frozen.get("version") if frozen is not None else detail.get("version")
        if version is None:
            continue
        UUID(version)
        for subject, obligation in sorted(detail.get("obligations", {}).items()):
            nodes.extend((version, subject, node) for node in obligation.get("opening_nodes", []))
    return nodes


def source_links(source: dict[str, Any], traces: dict[str, str]) -> list[dict[str, str]]:
    """Resolve original version IDs to actual trace IDs; they are distinct identities."""
    links = []
    for identity in source["contracts"]:
        links.extend(
            [
                {
                    "label": f"Contract history · {identity}",
                    "href": f"/contracts/{identity}/history",
                },
                {
                    "label": f"Posted journals · {identity}",
                    "href": f"/contracts/{identity}/journals",
                },
            ]
        )
    for version, subject, node in opening_nodes(source):
        if version in traces:
            links.append(
                {
                    "label": f"Opening calculation · {subject} · {node}",
                    "href": f"/trace/{traces[version]}?node={quote(node, safe='')}",
                }
            )
    return list({link["href"]: link for link in links}.values())


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if params.binding is None or KEY not in params.binding.evidence or column_key not in COLUMNS:
        raise Problem("not-found", "This run has no retained opening-liability cell contributions.")
    sources = params.binding.evidence[KEY]
    selected = [
        (key, source)
        for key, source in sorted(sources.items())
        if key == row_key or (row_key == f"summary:{source['currency']}")
    ]
    if not selected:
        raise Problem("not-found", "No such opening-liability contribution.")
    versions = {UUID(version) for _, source in selected for version, _, _ in opening_nodes(source)}
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
    currency = selected[0][1]["currency"]
    items = []
    total = Decimal(0)
    for key, source in selected:
        value = source["values"][column_key]
        if value["currency"] != currency:
            raise Problem("not-found", "Opening-liability contribution currencies differ.")
        total += Decimal(value["amount"])
        items.append(
            {
                "object_type": "opening_disclosure_contribution",
                "id": uuid5(NAMESPACE_URL, f"erev:opening:{source['entity_id']}:{key}"),
                "measure": column_key,
                "value": value,
                "href": "",
                "details": [],
                "_entity_id": source["entity_id"],
                "_source_set_entity_ids": source["source_entities"],
                "_source_set_details": _details(source),
                "_source_set_links": source_links(source, traces),
            }
        )
    return tie_outs.money(total, currency), items
