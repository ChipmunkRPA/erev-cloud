"""Legacy progress aggregation reconciles events and signed documents before commit."""

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
    source_invoice,
    source_record,
)
from erev_api.domain.imports.legacy_v1 import progress
from sqlalchemy import select
from support.factories import run_import_job
from support.legacy_replay import LegacyWorld, diffed, job_of, replayed, shown, submit
from support.reference import approve
from tests.domain.imports.legacy_v1 import test_progress as progress_tests

app = progress_tests.app
files = progress_tests.files
legacy = progress_tests.legacy


@pytest.mark.parametrize(
    "scenario, corruption",
    [
        ("positive", None),
        ("negative", None),
        ("zero", None),
        ("positive", "event"),
        ("negative", "event"),
        ("positive", "invoice"),
        ("negative", "invoice"),
        ("positive", "quantity"),
        ("positive", "missing"),
        ("positive", "revenue"),
        ("zero", "unexpected"),
    ],
)
def test_progress_readback(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch, scenario: str, corruption: str | None
) -> None:
    replayed(legacy, "02")
    row = progress_tests.row
    if scenario == "negative":
        progress_tests.progress(
            legacy,
            "delivered.xlsx",
            [row("Contract 1", "POB #1", "Hardware 1", 2, 100)],
            "2023-01-31",
        )
        figures = [(-1, -25, -7), (0, -10, 2)]
    elif scenario == "zero":
        figures = [(1, 25, 7), (-1, -25, -7)]
    else:
        figures = [(1, 50, 10), (1, 25, -3)]
    rows = [row("Contract 1", "POB #1", "Hardware 1", *values) for values in figures]
    imports = legacy.imports
    before_contracts = imports.rows(select(contract).order_by(contract.c.id))
    before_events = imports.rows(select(contract_event).order_by(contract_event.c.id))
    before_invoices = imports.rows(select(source_invoice).order_by(source_invoice.c.id))
    import_id = diffed(
        imports,
        "progress-readback.xlsx",
        progress_tests.progress_file(rows),
        "legacy_progress_tracking",
        {"effective_date": "2023-02-28"},
    )
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert approved.status_code == 200, approved.text
    original_events = progress._events
    original_invoice = progress._store_invoice

    def changed_invoice(uow: Any, context: Any, current: Any, item: Any, *args: Any) -> Any:
        if corruption == "invoice":
            item = dataclasses.replace(item, billing=item.billing + 1)
        return original_invoice(uow, context, current, item, *args)

    def changed_events(uow: Any, context: Any, current: Any, item: Any, *args: Any) -> Any:
        if corruption == "unexpected":
            item = dataclasses.replace(item, billing=Decimal(1))
        result = []
        for event, ordinal in original_events(uow, context, current, item, *args):
            kind = str(event.event_type)
            if corruption == "missing" and kind == "BILLING_RECORDED":
                continue
            payload = event.payload
            is_billing = kind in ("BILLING_RECORDED", "CREDIT_MEMO_RECORDED")
            if (corruption == "event" and is_billing) or (
                corruption == "revenue" and kind == "PRE_STANDARD_REVENUE_RECORDED"
            ):
                money = payload.amount.model_copy(
                    update={"amount": str(Decimal(payload.amount.amount) + 1)}
                )
                payload = payload.model_copy(update={"amount": money})
            elif corruption == "quantity" and kind == "DELIVERY_RECORDED":
                payload = payload.model_copy(update={"quantity": "3"})
            result.append((dataclasses.replace(event, payload=payload), ordinal))
        return result

    monkeypatch.setattr(progress, "_store_invoice", changed_invoice)
    monkeypatch.setattr(progress, "_events", changed_events)
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == ("COMMITTED" if corruption is None else "FAILED"), done
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    if corruption is None:
        assert check["source"] == check["stored"]
        assert done["counts"]["aggregated"] == 1
        assert (
            done["control_totals"]["loaded"]["amount_sums"]
            == done["control_totals"]["source"]["amount_sums"]
        )
        if scenario == "zero":
            assert check["stored"] == {"events": [], "documents": []}
        else:
            (document,) = check["stored"]["documents"]
            assert document["amount"] == ("-35" if scenario == "negative" else "75")
            billing = next(
                event
                for event in check["stored"]["events"]
                if event["type"] in ("BILLING_RECORDED", "CREDIT_MEMO_RECORDED")
            )
            assert billing["amount"] == ("35" if scenario == "negative" else "75")
    else:
        assert check["source"] != check["stored"]
        assert imports.rows(select(contract).order_by(contract.c.id)) == before_contracts
        assert imports.rows(select(contract_event).order_by(contract_event.c.id)) == before_events
        assert imports.rows(select(source_invoice).order_by(source_invoice.c.id)) == before_invoices
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
