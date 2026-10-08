"""Legacy source orders, additive draft bookings and VC amounts reconcile atomically."""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import (
    contract,
    contract_event,
    exception_item,
    import_row_lineage,
    source_order,
    source_record,
)
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.legacy_v1 import contract_setup
from sqlalchemy import select
from support.factories import run_import_job, workbook_bytes
from support.legacy_replay import (
    SETUP_2023,
    SKU_SSP,
    LegacyWorld,
    committed,
    diffed,
    job_of,
    shown,
    submit,
    workbook_rows,
)
from support.reference import approve, post
from tests.domain.imports.legacy_v1 import test_contract_setup as setup_tests

app = setup_tests.app
files = setup_tests.files
legacy = setup_tests.legacy


@pytest.mark.parametrize(
    "existing, corruption, existing_vc",
    [
        (False, None, False),
        (True, None, False),
        (True, None, True),
        (False, "booking", False),
        (True, "prior_booking", False),
        (False, "source", False),
        (True, "source", False),
        (False, "vc_amount", False),
        (False, "vc_direction", False),
        (False, "missing_vc", False),
    ],
)
def test_setup_reads_back_all_monetary_targets(
    legacy: LegacyWorld,
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
    corruption: str | None,
    existing_vc: bool,
) -> None:
    committed(legacy, "SSP.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    headers, rows = workbook_rows(SETUP_2023)
    rows = [row for row in rows if row[0] == "Contract 2"]
    if existing_vc:
        # The public estimate API uses identifier codes; legacy files can also carry spaces.
        rows = [list(row) for row in rows]
        for row in rows:
            if row[headers.index(columns.STRATIFICATION)] == "VC":
                row[headers.index(columns.POB)] = "VC1"
    parameters = {"activate_on_approval": False}
    if existing:
        committed(
            legacy,
            "first.xlsx",
            workbook_bytes("Sheet1", headers, rows[:2]),
            "legacy_contract_setup",
            parameters,
        )
        rows = rows[2:]
    imports = legacy.imports
    if existing_vc:
        (draft,) = imports.rows(select(contract.c.id).where(contract.c.external_id == "Contract 2"))
        created = post(
            legacy.app,
            f"/api/v1/contracts/{draft['id']}/estimates",
            imports.actor,
            {
                "estimate_kind": "VARIABLE_CONSIDERATION",
                "element_code": "VC-VC1",
                "vc_element_type": "BONUS",
                "method": "ENTERED_AMOUNT",
                "direction": "INCREASE",
            },
        )
        assert created.status_code == 201, created.text
    before_contracts = imports.rows(select(contract).order_by(contract.c.id))
    before_events = imports.rows(select(contract_event).order_by(contract_event.c.id))
    import_id = diffed(
        imports,
        "setup-readback.xlsx",
        workbook_bytes("Sheet1", headers, rows),
        "legacy_contract_setup",
        parameters,
    )
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert approved.status_code == 200, approved.text
    original_line = contract_setup._line
    original_order = contract_setup._source_order
    original_vc = contract_setup.vc_element_writer
    original_replace = contract_setup.replace_draft

    def changed_line(values: Any, currency: str) -> Any:
        line = original_line(values, currency)
        if corruption == "booking":
            line["total_price"]["amount"] = str(Decimal(line["total_price"]["amount"]) + 1)
        return line

    def changed_order(uow: Any, plan: Any, context: Any, customer_id: Any, currency: Any) -> None:
        if corruption == "source":
            plan = dataclasses.replace(
                plan,
                rows=tuple(
                    dataclasses.replace(
                        row,
                        normalized=dict(row.normalized)
                        | {columns.PRICE: str(Decimal(str(row.normalized[columns.PRICE])) + 1)},
                    )
                    for row in plan.rows
                ),
            )
        original_order(uow, plan, context, customer_id, currency)

    def changed_vc(uow: Any, element: Any, *, context: Any) -> Any:
        if corruption == "missing_vc":
            return None
        if corruption == "vc_amount":
            element = dataclasses.replace(
                element, constrained_amount=element.constrained_amount + 1
            )
        elif corruption == "vc_direction":
            element = dataclasses.replace(element, direction="INCREASE")
        return original_vc(uow, element, context=context)

    def changed_replace(uow: Any, **kwargs: Any) -> Any:
        if corruption == "prior_booking":
            body = kwargs["body"]
            values = body.model_dump(mode="json")
            values["lines"][0]["total_price"]["amount"] = "601"
            kwargs["body"] = type(body).model_validate(values)
        return original_replace(uow, **kwargs)

    monkeypatch.setattr(contract_setup, "_line", changed_line)
    monkeypatch.setattr(contract_setup, "_source_order", changed_order)
    monkeypatch.setattr(contract_setup, "vc_element_writer", changed_vc)
    monkeypatch.setattr(contract_setup, "replace_draft", changed_replace)
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == ("COMMITTED" if corruption is None else "FAILED"), done
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    if corruption is None:
        assert check["source"] == check["stored"]
        assert len(check["stored"]["bookings"][0]["lines"]) == 4
        assert len(check["stored"]["orders"][0]["lines"]) == len(rows)
        (vc,) = check["stored"]["vc_versions"]
        assert (vc["amount"], vc["direction"], vc["currency"]) == (
            "100",
            "INCREASE" if existing_vc else "DECREASE",
            "USD",
        )
        assert (
            done["control_totals"]["loaded"]["amount_sums"]
            == done["control_totals"]["source"]["amount_sums"]
        )
    else:
        assert check["source"] != check["stored"]
        assert imports.rows(select(contract).order_by(contract.c.id)) == before_contracts
        assert imports.rows(select(contract_event).order_by(contract_event.c.id)) == before_events
        for table in (source_record, import_row_lineage):
            assert (
                imports.rows(select(table.c.id).where(table.c.import_upload_id == UUID(import_id)))
                == []
            )
        assert (
            imports.rows(
                select(source_order.c.id).where(source_order.c.external_version == import_id)
            )
            == []
        )
        (finding,) = imports.rows(
            select(exception_item).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        assert finding["severity"] == "BLOCKING"
