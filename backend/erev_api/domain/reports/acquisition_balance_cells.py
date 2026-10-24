"""Explain retained native acquisition balances and their maturity presentation."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import calc_trace
from erev_api.problems import Problem

from . import acquisition_balances, tie_outs
from .acquisition_cells import KIND
from .builders import ReportParams

KEY = "acquisition_balance_cells_v1"
COLUMN = "acquisition_source_period"
MEASURES = frozenset(
    {
        "contract_liability",
        "contract_asset",
        "unbilled_receivable",
        "contract_liability_current",
        "contract_asset_current",
        "contract_liability_noncurrent",
        "contract_asset_noncurrent",
    }
)


def retain(
    params: ReportParams,
    balances: Sequence[tie_outs.BalanceRow],
    rows: list[dict[str, Any]],
    periods: Mapping[UUID, tie_outs.PeriodRef | None],
    rates: Mapping[UUID, Mapping[str, Any]],
) -> bool:
    if params.binding is not None and KEY not in params.binding.evidence:
        return False
    evidence = (
        params.binding.evidence
        if params.binding is not None
        else (params.sources.evidence if params.sources is not None else {})
    )
    by_key = {f"contract:{item.external_id}:{item.entity_code}": item for item in balances}
    captured = {}
    for row in rows:
        member = by_key.get(row["row_key"])
        at = None if member is None else periods.get(member.entity_id)
        if member is None or at is None:
            continue
        identity = (
            f"{acquisition_balances.KEY}:{member.version_id}:{member.contract_id}:"
            f"{member.entity_id}:{at.key}"
        )
        original = evidence.get(identity)
        if original is None:
            continue
        snapshot = original["snapshot"]
        captured[row["row_key"]] = {
            "contract_id": str(member.contract_id),
            "entity_id": str(member.entity_id),
            "version_id": str(member.version_id),
            "original": original,
            "values": {key: row[key] for key in sorted(MEASURES) if key in row},
            "rate": dict(rates.get(member.entity_id, {})),
        }
        row[COLUMN] = snapshot["period_key"]
    if params.binding is not None and params.binding.evidence[KEY] != captured:
        raise tie_outs.invalid("currency_view", "Retained acquisition balance cells differ.")
    tie_outs.record_evidence(params, KEY, captured)
    return True


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    cells = {} if params.binding is None else params.binding.evidence.get(KEY, {})
    source = cells.get(row_key)
    if source is None or column_key not in source["values"]:
        raise Problem("not-found", "This cell has no retained acquisition balance sources.")
    trace = session.execute(
        select(calc_trace.c.id).where(
            calc_trace.c.contract_version_id == UUID(source["version_id"])
        )
    ).scalar_one_or_none()
    if trace is None:
        raise Problem("not-found", "Original acquisition trace is unavailable.")
    original = source["original"]
    snapshot = original["snapshot"]
    scale = Decimal(10) ** -snapshot["minor_unit"]
    details = [
        f"Original acquisition measurement: {snapshot['period_key']}; requested balance period: "
        f"{original['requested_period_key']}. "
        "Later periods carry this observation until a new measurement.",
        f"Original opening event: {snapshot['event_key']}",
        f"Measurement basis: {snapshot.get('basis', 'Original cutover observation')}",
        f"Input SHA-256: {original['input_sha256']}",
        f"Output SHA-256: {original['output_sha256']}",
    ]
    for name, amount in sorted(original["amounts"].items()):
        details.append(f"Original {name}: {amount} {snapshot['currency']}")
    if snapshot.get("unmeasured", {}).get("accounts_receivable") == "ERP_MODE_EXTERNAL_BALANCE":
        details.append(
            "Accounts receivable is ERP-managed: zero is the engine reporting default, "
            "not a confirmed ERP balance."
        )
    functional = snapshot.get("functional")
    if functional is not None:
        scale_fn = Decimal(10) ** -functional["minor_unit"]
        details.extend(
            f"Original functional {role}: {Decimal(amount) * scale_fn} {functional['currency']}"
            for role, amount in sorted(functional["amounts"].items())
        )
        classification = functional.get("liability_current")
        if classification is None:
            details.append("Functional current liability classification is unavailable.")
        else:
            details.append(
                f"Current liability follows original {classification['policy']} layer release."
            )
            for part in classification["allocations"]:
                details.append(
                    f"Layer {part['layer_key']}: current "
                    f"{Decimal(part['current_functional']) * scale_fn} {functional['currency']}; "
                    f"noncurrent {Decimal(part['noncurrent_functional']) * scale_fn} "
                    f"{functional['currency']}."
                )
        for layer in functional.get("liability_layers", ()):
            details.append(
                f"Original liability layer {layer['layer_key']}: remaining "
                f"{Decimal(layer['txn_open']) * scale} {snapshot['currency']}; carrying "
                f"{Decimal(layer['functional_carrying']) * scale_fn} {functional['currency']}."
            )
            for move in layer["movements"]:
                details.append(
                    f"{move['effective_date']} {move['kind']}: "
                    f"{Decimal(move['amount_txn']) * scale} {snapshot['currency']}; "
                    f"{Decimal(move['amount_functional']) * scale_fn} {functional['currency']}; "
                    f"rate {move['rate']} ({move['rate_key']}, {move['version_key']}); "
                    f"source {move['source_key'] or 'period-end remeasurement'}."
                )
    maturity = snapshot.get("maturity", {})
    details.append(f"Current/noncurrent policy: {maturity.get('policy', 'unavailable')}")
    attribution = maturity.get("asset_attribution")
    if attribution is not None:
        details.append(f"Original asset attribution policy: {attribution['policy']}")
        details.append(
            "Original allocation basis: "
            + "; ".join(
                f"{key}: {value}" for key, value in sorted(attribution.get("basis", {}).items())
            )
        )
        for subject, parts in sorted(attribution["parts"].items()):
            details.append(
                f"{subject}: original asset share {Decimal(parts['contract_asset']) * scale} "
                f"{snapshot['currency']}; "
                f"current eligible: {maturity['obligations'][subject]['asset_current_eligible']}"
            )
    for subject, item in sorted(maturity.get("obligations", {}).items()):
        details.append(
            f"{subject}: maturity horizon {item['horizon']}; "
            f"current asset eligible: {item['asset_current_eligible']}"
        )
    if column_key.endswith("_noncurrent"):
        details.append("Noncurrent equals displayed total less displayed current.")
    rate = source["rate"]
    if rate:
        details.append(
            f"Retained closing FX rate: {rate['base_currency']} to {rate['quote_currency']} "
            f"at {rate['rate']}. Noncurrent equals displayed total less displayed current."
        )
    nodes = set(snapshot["nodes"])
    if functional is not None:
        nodes.update(functional["nodes"].values())
        nodes.update(
            move["node"]
            for layer in functional.get("liability_layers", ())
            for move in layer["movements"]
        )
    for item in maturity.get("obligations", {}).values():
        nodes.update(item["sources"])
    links = [
        {
            "label": "Original contract history",
            "href": f"/contracts/{source['contract_id']}/history",
        }
    ]
    links.extend(
        {
            "label": f"Original acquisition calculation · {node}",
            "href": f"/trace/{trace}?node={quote(node, safe='')}",
        }
        for node in sorted(nodes)
    )
    value = source["values"][column_key]
    return value, [
        {
            "object_type": KIND,
            "id": uuid5(
                NAMESPACE_URL, f"erev:acquisition-balance:{source['version_id']}:{row_key}"
            ),
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
