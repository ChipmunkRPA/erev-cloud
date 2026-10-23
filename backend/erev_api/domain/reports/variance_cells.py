"""Explain recorded variance contributions without recomputing under a read transaction."""

from __future__ import annotations

from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, contract_version, obligation_version
from erev_api.domain.reports.builders import ADAPTER, ReportParams
from erev_api.problems import Problem

from .variance_presentation import DRIVER_LABELS, LABELS, _money


def _refuse() -> Problem:
    return Problem(
        "not-found", "Verified variance contributors are unavailable. Run the report again."
    )


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    binding = params.binding
    if (
        column_key != "change"
        or binding is None
        or binding.strategy != ADAPTER
        or params.report_code != "variance_between_closes"
        or params.report_version != 1
    ):
        raise _refuse()
    try:
        evidence = binding.evidence["close_variance_contributors"]
        identity = binding.evidence["close_variance_sources"]
        if (
            identity.get("currency_view", "transaction")
            != params.parameters.get("currency_view", "transaction")
            or evidence.get("currency_view", "transaction")
            != params.parameters.get("currency_view", "transaction")
            or evidence["format"] != "erev.close_variance_presentation.v1"
            or identity["version"] != 1
            or binding.report_version != params.report_version
            or sha256_hex(evidence) != binding.evidence["close_variance_evidence_sha256"]
            or evidence["required_entity_ids"] != identity["required_entity_ids"]
            or set(identity["required_entity_ids"]) != {str(item) for item in params.entity_ids}
            or identity["sides"][0]["lock_id"] != params.parameters["from_period_lock_id"]
            or identity["sides"][1]["lock_id"] != params.parameters["to_period_lock_id"]
        ):
            raise _refuse()
        point = evidence["contributors"][row_key]
        value = point["value"]
        currency = value["currency"]
        measure = point["measure"]
        sources = point.get("contracts")
        if sources is None:
            sources = [
                {
                    "contract_external_id": point["contract_external_id"],
                    "group_id": point["group_id"],
                    "change": value,
                    "effects": point["effects"],
                    "event_keys": [
                        key for effect in point["effects"] for key in effect["event_keys"]
                    ],
                }
            ]
            if sum(
                (Fraction(effect["change"]["amount"]) for effect in point["effects"]), Fraction(0)
            ) != Fraction(value["amount"]):
                raise _refuse()
        items = []
        total = Fraction(0)
        for source in sources:
            name = source["contract_external_id"]
            amount = Fraction(source["change"]["amount"])
            if source["change"]["currency"] != currency:
                raise _refuse()
            group = evidence["groups"][source["group_id"]]
            for index, side in enumerate(("earlier", "later")):
                computation_id = identity["sides"][index]["contracts"].get(name)
                if computation_id is None:
                    if group[side] is not None:
                        raise _refuse()
                    continue
                if group[side] is None:
                    raise _refuse()
                original = identity["sides"][index]["computations"][computation_id]
                if (
                    group[side]["computation_id"] != computation_id
                    or original["group_id"] != group[side].get("group_id", source["group_id"])
                    or any(
                        group[side][field] != original[field]
                        for field in ("input_sha256", "output_sha256")
                    )
                ):
                    raise _refuse()
            existing = group["later"] or group["earlier"]
            if existing is None:
                raise _refuse()
            found = session.execute(
                select(contract.c.id)
                .select_from(contract)
                .join(
                    obligation_version,
                    (obligation_version.c.contract_id == contract.c.id)
                    & (obligation_version.c.tenant_id == contract.c.tenant_id),
                )
                .join(
                    contract_version,
                    (contract_version.c.id == obligation_version.c.contract_version_id)
                    & (contract_version.c.tenant_id == obligation_version.c.tenant_id),
                )
                .where(
                    contract.c.external_id == name,
                    contract_version.c.contract_computation_id == UUID(existing["computation_id"]),
                    contract_version.c.book_code == params.book_code,
                )
                .distinct()
            ).scalar_one_or_none()
            if found is None:
                raise _refuse()
            details = [
                name,
                f"Earlier lock: {identity['sides'][0]['lock_id']}",
                f"Later lock: {identity['sides'][1]['lock_id']}",
            ]
            drivers = (
                [point["driver"]]
                if "driver" in point
                else [
                    effect["driver"]
                    for effect in point["effects"]
                    if Fraction(effect["change"]["amount"])
                ]
            )
            details.append(
                "Drivers: " + ", ".join(dict.fromkeys(DRIVER_LABELS[driver] for driver in drivers))
            )
            details.extend(f"Event: {key}" for key in source["event_keys"])
            effects = source.get("effects")
            if effects is not None:
                if (
                    any(effect["change"]["currency"] != currency for effect in effects)
                    or sum(
                        (Fraction(effect["change"]["amount"]) for effect in effects), Fraction(0)
                    )
                    != amount
                ):
                    raise _refuse()
                for effect in effects:
                    effect_amount = Fraction(effect["change"]["amount"])
                    if not effect_amount:
                        continue
                    label = DRIVER_LABELS[effect.get("driver", point.get("driver"))]
                    rendered = _money(effect_amount, currency)
                    events = ", ".join(effect["event_keys"])
                    detail = f"{label}: {rendered['amount']} {currency}"
                    details.append(detail + (f"; Events: {events}" if events else ""))
            for step in group["executions"]:
                if step["driver"] in drivers and step.get("changed_fields"):
                    details.append("Changed inputs: " + ", ".join(step["changed_fields"]))

            for side in ("earlier", "later"):
                details.extend(
                    f"{side.title()} source row: {key}"
                    for key in point.get(f"{side}_source_rows", [])
                )
            items.append(
                {
                    "object_type": "contract",
                    "id": found,
                    "measure": LABELS[measure],
                    "value": _money(amount, currency),
                    "href": f"/contracts/{found}/history",
                    "details": details,
                }
            )
            total += amount
        if total != Fraction(value["amount"]):
            raise _refuse()
        return _money(total, currency), items
    except (KeyError, TypeError, ValueError, AttributeError, ZeroDivisionError) as error:
        raise _refuse() from error
