"""CSV progress facts reconcile to original file rows, including optional refunds."""

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
    "scenario, corruption",
    [
        ("delivery", None),
        ("delivery", "quantity"),
        ("delivery", "missing_target"),
        ("progress", None),
        ("progress", "ratio"),
        ("progress", "hours"),
        ("milestone", None),
        ("milestone", "weight"),
        ("milestone", "obligation"),
        ("refund", None),
        ("refund", "amount"),
        ("refund_zero", None),
        ("refund_zero", "amount"),
        ("refund_absent", None),
        ("refund_absent", "amount"),
    ],
)
def test_progress_event_financial_fields(
    k11: K11World, monkeypatch: pytest.MonkeyPatch, scenario: str, corruption: str | None
) -> None:
    template = csv_v2.TEMPLATES["progress_events"]
    headers = [column.name for column in template.columns]
    assert {c.name for c in template.columns if c.type == "amount"} == {"refund_amount.amount"}
    base = dict.fromkeys(headers, "") | {
        "contract": K11_EXTERNAL_ID,
        "effective_date": "2026-09-30",
        "obligation_key": "O1",
    }
    if scenario.startswith("refund"):
        invoice_tests.committed(
            k11,
            "billing.csv",
            invoice_tests.csv_bytes(invoice_tests.HEADERS, [invoice_tests.ROWS[0]]),
            "invoices",
        )
        delivered = base | {
            "effective_date": "2026-09-15",
            "event_type": "DELIVERY_RECORDED",
            "quantity": "20",
            "trigger": "DELIVERY",
        }
        invoice_tests.committed(
            k11,
            "delivered.csv",
            invoice_tests.csv_bytes(headers, [[delivered[name] for name in headers]]),
            "progress_events",
        )
        base |= {"event_type": "RETURN_RECORDED", "quantity": "2", "reason": "Damaged units"}
        amount = "100" if scenario == "refund" else "0" if scenario == "refund_zero" else None
        if amount is not None:
            base |= {"refund_amount.amount": amount, "refund_amount.currency": "EUR"}
    elif scenario == "delivery":
        base |= {"event_type": "DELIVERY_RECORDED", "quantity": "12.5", "trigger": "DELIVERY"}
    elif scenario == "progress":
        base |= {
            "event_type": "PROGRESS_RECORDED",
            "obligation_key": "O2",
            "cumulative_progress_ratio": "0.25",
            "measure": "LABOUR_HOURS",
            "hours_to_date": "80.5",
        }
    else:
        base |= {
            "event_type": "MILESTONE_ACHIEVED",
            "milestone_code": "DESIGN-SIGNOFF",
            "cumulative_weight": "0.25",
        }
    imports = invoice_tests.importer(k11)
    import_id = diffed(
        imports,
        "progress-fields.csv",
        invoice_tests.csv_bytes(headers, [[base[name] for name in headers]]),
        "progress_events",
    )
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(k11.app, str(submitted.json()["approval_request_id"]), k11.priya)
    assert approved.status_code == 200, approved.text

    def changed(uow: Any, plan: Any, *, context: Any) -> Any:
        body = copy.deepcopy(plan.body)
        if corruption == "amount":
            body["refund_amount"] = {
                "amount": str(Decimal(base["refund_amount.amount"] or "0") + 1),
                "currency": "EUR",
            }
        for key, value in {
            "quantity": ("quantity", "13.5"),
            "ratio": ("cumulative_progress_ratio", "0.5"),
            "hours": ("hours_to_date", "81.5"),
            "weight": ("cumulative_weight", "0.5"),
            "obligation": ("obligation_key", "O2"),
        }.items():
            if corruption == key:
                body[value[0]] = value[1]
        applied = template.apply(uow, dataclasses.replace(plan, body=body), context=context)
        if corruption == "missing_target":
            applied.targets.clear()
        return applied

    monkeypatch.setattr(
        csv_v2,
        "TEMPLATES",
        {**csv_v2.TEMPLATES, "progress_events": dataclasses.replace(template, apply=changed)},
    )
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == ("COMMITTED" if corruption is None else "FAILED"), done
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    if corruption is None:
        assert check["source"] == check["stored"]
        (event,) = check["stored"]["events"]
        assert event["fields"]["obligation_key"] == base["obligation_key"]
        assert event["amount"] == (
            [base["refund_amount.amount"], "EUR"] if base["refund_amount.amount"] else None
        )
        assert (
            done["control_totals"]["loaded"]["amount_sums"]
            == done["control_totals"]["source"]["amount_sums"]
        )
    else:
        assert check["source"] != check["stored"]
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
        (finding,) = imports.rows(
            select(exception_item).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        assert finding["severity"] == "BLOCKING"
