"""Persist each engine loss test and its complete, pinned EAC lineage atomically."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.money import minor_to_decimal
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import (
    estimate,
    estimate_version,
    loss_provision_eac,
    loss_provision_version,
)
from erev_api.domain.contracts import bundles
from erev_api.uow import UnitOfWork

AMOUNTS = (
    "expected_consideration",
    "expected_total_costs",
    "costs_to_date",
    "revenue_to_date",
    "expected_margin",
    "provision_balance",
    "provision_movement",
)


def _eac_ids(
    uow: UnitOfWork, bundle: InputBundle, found: bundles.BundleIndex
) -> dict[str, tuple[UUID, UUID]]:
    contracts = {row["id"]: key for key, row in found.contracts.items()}
    pinned = {item.version_key for item in bundle.estimate_versions if item.estimate_kind == "EAC"}
    rows = uow.session.execute(
        select(
            estimate.c.contract_id,
            estimate.c.element_code,
            estimate_version.c.version_no,
            estimate_version.c.id,
        )
        .select_from(
            estimate.join(
                estimate_version,
                (estimate.c.tenant_id == estimate_version.c.tenant_id)
                & (estimate.c.id == estimate_version.c.estimate_id),
            )
        )
        .where(estimate.c.contract_id.in_(contracts), estimate.c.estimate_kind == "EAC")
    )
    result = {}
    for contract_id, code, version_no, version_id in rows:
        key = f"{obligation_subject_key(contracts[contract_id], str(code))}@v{version_no}"
        if key in pinned:
            result[key] = (UUID(str(version_id)), UUID(str(contract_id)))
    return result


def persist(
    uow: UnitOfWork,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    book: BookOutput,
    version_id: UUID,
) -> dict[str, list[UUID]]:
    facts: dict[str, list[UUID]] = {"loss_provision_version": [], "loss_provision_eac": []}
    if not book.loss_provision_versions:
        return facts
    eacs = _eac_ids(uow, bundle, found)
    rows: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    stamps = {
        "tenant_id": uow.principal.tenant_id,
        "created_at": uow.now,
        "created_by": uow.principal.id,
        "created_by_kind": uow.principal.kind.value,
    }
    for output in book.loss_provision_versions:
        values = output.columns
        contract_key, entity = str(values["contract_key"]), str(values["entity"])
        owner = found.contracts.get(contract_key)
        if owner is None:
            raise ValueError("Loss test names an unknown contract")
        period = found.periods.get((entity, output.period_key))
        if period is None or period[1] != values["as_of"]:
            raise ValueError("Loss test names an unknown period end")
        obligation_id = None
        if values["unit"] == "POB":
            key = obligation_subject_key(contract_key, str(values["obligation_key"]))
            obligation = found.obligations.get(key)
            if obligation is None:
                raise ValueError("Loss test names an unknown obligation")
            obligation_id = obligation["id"]
        elif values["unit"] != "CONTRACT" or values["obligation_key"] is not None:
            raise ValueError("Loss test has inconsistent unit ownership")
        expected_key = contract_key if obligation_id is None else key
        if output.subject_key != expected_key or values["unit_key"] != expected_key:
            raise ValueError("Loss test has an inconsistent unit key")
        version_keys = values["eac_version_keys"]
        if not isinstance(version_keys, tuple) or any(key not in eacs for key in version_keys):
            raise ValueError("Loss test names an unpinned EAC version")
        if any(eacs[key][1] != owner["id"] for key in version_keys):
            raise ValueError("Loss test references another contract's EAC version")
        eac_ids = sorted({eacs[key][0] for key in version_keys})
        currency = str(values["currency"])
        if any(type(values[name]) is not int for name in AMOUNTS):
            raise ValueError("Loss test amounts must be integer minor units")
        if type(values["in_scope"]) is not bool:
            raise ValueError("Loss test scope must be boolean")
        row_id = new_id()
        row = {
            **stamps,
            "id": row_id,
            "contract_version_id": version_id,
            "contract_id": owner["id"],
            "entity_id": found.entities[entity]["id"],
            "book_code": book.book_code,
            "unit": values["unit"],
            "unit_key": output.subject_key,
            "obligation_id": obligation_id,
            "period_id": period[0],
            "period_key": output.period_key,
            "as_of": values["as_of"],
            "measurement_basis": values["measurement_basis"],
            "currency": currency,
            "in_scope": values["in_scope"],
            "trace_nodes": dict(output.trace_nodes),
            "eac_estimate_version_id": eac_ids[0] if len(eac_ids) == 1 else None,
            **{
                name: minor_to_decimal(
                    int(str(values[name])), bundle.currencies[currency].minor_unit
                )
                for name in AMOUNTS
            },
        }
        rows.append(row)
        facts["loss_provision_version"].append(row_id)
        for eac_id in eac_ids:
            link_id = new_id()
            links.append(
                {
                    **stamps,
                    "id": link_id,
                    "loss_provision_version_id": row_id,
                    "estimate_version_id": eac_id,
                    "entity_id": row["entity_id"],
                }
            )
            facts["loss_provision_eac"].append(link_id)
    uow.session.execute(insert(loss_provision_version), rows)
    if links:
        uow.session.execute(insert(loss_provision_eac), links)
    return facts
