"""Legacy amendment money, treatment and added obligations reconcile atomically."""

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
    obligation,
    source_record,
)
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.legacy_v1 import modification
from erev_api.enums import ModificationTreatment
from sqlalchemy import select
from support.factories import run_import_job, workbook_bytes
from support.legacy_replay import LegacyWorld, diffed, job_of, replayed, shown, submit
from support.reference import approve
from tests.domain.imports.legacy_v1 import test_modification as modification_tests

app = modification_tests.app
files = modification_tests.files
legacy = modification_tests.legacy


@pytest.mark.parametrize(
    "mode, scenario, corruption",
    [
        ("prospective", "change", None),
        ("retrospective", "change", None),
        ("pob_price_change", "price", None),
        ("prospective", "negative", None),
        ("prospective", "add", None),
        ("prospective", "change", "amount"),
        ("prospective", "change", "quantity"),
        ("prospective", "change", "treatment"),
        ("prospective", "add", "basis"),
        ("prospective", "add", "product"),
    ],
)
def test_modification_readback(
    legacy: LegacyWorld,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
    corruption: str | None,
) -> None:
    replayed(legacy, "02")
    headers = [name for name, *_ in columns.LEGACY_HEADERS[modification.CODE]]
    adding = scenario == "add"
    values = dict.fromkeys(headers, "") | {
        columns.CONTRACT: "Contract 1",
        columns.POB: "NEW-POB" if adding else "POB #1",
        columns.SKU: "Consulting 1" if adding else "Hardware 1",
        columns.MOD_BILLING: "-50" if scenario == "negative" else "50",
        columns.MOD_QTY: "0" if scenario == "price" else "-1" if scenario == "negative" else "1",
        columns.MOD_START: "2023-02-01",
        columns.MOD_END: "2023-12-31",
        columns.STRATIFICATION: "Consulting 1" if adding else "Hardware 1",
        columns.SELLING_ENTITY: "Mock Entity 1",
        columns.SSP_VERSION: "2023-01-01",
    }
    if adding:
        values[columns.DEFERRED_ACCOUNT] = "21001"
        values[columns.UNBILLED_ACCOUNT] = "15001"
    imports = legacy.imports
    before = {
        table.name: imports.rows(select(table).order_by(table.c.id))
        for table in (contract, contract_event, obligation)
    }
    import_id = diffed(
        imports,
        "modification-readback.xlsx",
        workbook_bytes("Modification", headers, [[values[name] for name in headers]]),
        modification.CODE,
        {"mode": mode, "effective_date": "2023-02-01"},
    )
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert approved.status_code == 200, approved.text
    original_line = modification._line
    original_catalogue = modification.catalogue
    original_added = modification._insert_added

    def changed_line(values: Any, currency: Any, action: Any) -> Any:
        line = original_line(values, currency, action)
        if corruption == "amount":
            line = line.model_copy(
                update={
                    "consideration_delta": line.consideration_delta.model_copy(
                        update={"amount": str(Decimal(line.consideration_delta.amount) + 1)}
                    )
                }
            )
        elif corruption == "quantity":
            line = line.model_copy(update={"quantity_delta": "2"})
        return line

    def changed_catalogue(session: Any) -> Any:
        catalogue = original_catalogue(session)
        return (
            dataclasses.replace(catalogue, version_ids={}) if corruption == "basis" else catalogue
        )

    def changed_added(
        uow: Any, plan: Any, contract_id: Any, event: Any, keys: Any, lines: Any
    ) -> None:
        if corruption == "product":
            lines = [line.model_copy(update={"product_code": "Software 1"}) for line in lines]
        original_added(uow, plan, contract_id, event, keys, lines)

    monkeypatch.setattr(modification, "_line", changed_line)
    monkeypatch.setattr(modification, "catalogue", changed_catalogue)
    monkeypatch.setattr(modification, "_insert_added", changed_added)
    if corruption == "treatment":
        monkeypatch.setattr(
            modification,
            "TREATMENTS",
            dict(modification.TREATMENTS)
            | {"prospective": ModificationTreatment.LEGACY_RETROSPECTIVE},
        )
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == ("COMMITTED" if corruption is None else "FAILED"), done
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    if corruption is None:
        assert check["source"] == check["stored"]
        (event,) = check["stored"]["events"]
        (line,) = event["lines"]
        assert (line["amount"], line["currency"]) == (values[columns.MOD_BILLING], "USD")
        assert line["quantity"] == values[columns.MOD_QTY]
        assert len(check["stored"]["added"]) == int(adding)
        assert (
            done["control_totals"]["loaded"]["amount_sums"]
            == done["control_totals"]["source"]["amount_sums"]
        )
    else:
        assert check["source"] != check["stored"]
        for table in (contract, contract_event, obligation):
            assert imports.rows(select(table).order_by(table.c.id)) == before[table.name]
        for table in (source_record, import_row_lineage):
            assert (
                imports.rows(select(table.c.id).where(table.c.import_upload_id == UUID(import_id)))
                == []
            )
        (finding,) = imports.rows(
            select(exception_item).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        assert finding["severity"] == "BLOCKING"
