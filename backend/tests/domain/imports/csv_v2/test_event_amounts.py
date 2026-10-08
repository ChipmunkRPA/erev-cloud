"""Stored monetary evidence and atomic rollback for CSV single-event templates."""

from __future__ import annotations

import copy
import dataclasses
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import (
    contract_event,
    exception_item,
    import_row_lineage,
    job,
    source_record,
)
from erev_api.domain.imports import csv_v2
from sqlalchemy import select
from support.factories import K11_EXTERNAL_ID, K11World, run_import_job
from support.legacy_replay import diffed, job_of, shown, submit
from support.reference import approve
from tests.domain.imports.csv_v2 import test_invoices as invoice_tests

app = invoice_tests.app
k11 = invoice_tests.k11


@pytest.mark.parametrize(
    "template_code, amount, corruption",
    [
        (template, amount, corruption)
        for template, amount in (
            ("cost_events", "250.00"),
            ("pre_standard_revenue", "-120.00"),
            ("usage", "250.00"),
            ("usage", None),
            ("usage", "0.00"),
        )
        for corruption in (None, "amount", "missing_target", "obligation")
    ]
    + [("usage", amount, "quantity") for amount in ("250.00", None, "0.00")],
)
def test_event_amounts_match_stored_targets(
    k11: K11World,
    monkeypatch: pytest.MonkeyPatch,
    template_code: str,
    amount: str | None,
    corruption: str | None,
) -> None:
    template = csv_v2.TEMPLATES[template_code]
    headers = [column.name for column in template.columns]
    field = "rated_amount" if template_code == "usage" else "amount"
    # A new monetary field must gain independent read-back before the template claims coverage.
    assert {column.name for column in template.columns if column.type == "amount"} == {
        f"{field}.amount"
    }
    cells = dict.fromkeys(headers, "")
    cells.update(
        {
            "contract": K11_EXTERNAL_ID,
            "effective_date": "2026-09-30",
            "obligation_key": "O2",
            f"{field}.amount": amount or "",
            f"{field}.currency": "EUR" if amount is not None else "",
        }
    )
    if template_code == "cost_events":
        cells["purpose"] = "PROGRESS_INPUT"
    elif template_code == "usage":
        cells.update(
            {
                "usage_period_start": "2026-09-15",
                "usage_period_end": "2026-09-30",
                "metric": "SUPPORT_TICKETS",
                "quantity": "14",
            }
        )
    imports = invoice_tests.importer(k11)
    import_id = diffed(
        imports,
        "monetary-events.csv",
        invoice_tests.csv_bytes(headers, [[cells[key] for key in headers]]),
        template_code,
    )
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    assert (
        approve(k11.app, str(submitted.json()["approval_request_id"]), k11.priya).status_code == 200
    )

    def changed(uow: Any, plan: Any, *, context: Any) -> Any:
        body = copy.deepcopy(plan.body)
        if corruption == "amount":
            body[field] = {"amount": str(Decimal(amount or "0") + 1), "currency": "EUR"}
        if corruption == "obligation":
            body["obligation_key"] = "O1"
        elif corruption == "quantity":
            body["quantity"] = "15"
        applied = template.apply(uow, dataclasses.replace(plan, body=body), context=context)
        if corruption == "missing_target":
            applied.targets.clear()
        return applied

    monkeypatch.setattr(
        csv_v2,
        "TEMPLATES",
        {**csv_v2.TEMPLATES, template_code: dataclasses.replace(template, apply=changed)},
    )
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == ("COMMITTED" if corruption is None else "FAILED"), done
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    if corruption is None:
        assert check["source"] == check["stored"]
        assert check["stored"]["events"][0]["amount"] == (
            None if amount is None else [format(Decimal(amount).normalize(), "f"), "EUR"]
        )
        assert Decimal(
            done["control_totals"]["loaded"]["amount_sums"][f"{field}.amount"]
        ) == Decimal(amount or "0")
    else:
        assert check["source"] != check["stored"]
        (finding,) = imports.rows(
            select(exception_item).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        assert finding["severity"] == "BLOCKING"
        for table in (contract_event, source_record, import_row_lineage):
            assert (
                imports.rows(select(table.c.id).where(table.c.import_upload_id == UUID(import_id)))
                == []
            )
        assert (
            imports.rows(
                select(job.c.id).where(
                    job.c.kind == "CONTRACT_COMPUTE",
                    job.c.params["import_upload_id"].astext == import_id,
                )
            )
            == []
        )
