"""Independent persisted estimate monetary inputs and atomic import rollback."""

from __future__ import annotations

import copy
import dataclasses
from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import (
    contract,
    estimate,
    estimate_version,
    exception_item,
    import_row_lineage,
    source_record,
)
from erev_api.domain.imports import csv_v2
from sqlalchemy import select
from support.factories import K11_EXTERNAL_ID, K11World, run_import_job
from support.legacy_replay import diffed, job_of, shown, submit
from support.reference import approve, post
from tests.domain.imports.csv_v2 import test_invoices as invoice_tests

app = invoice_tests.app
k11 = invoice_tests.k11


@pytest.mark.parametrize(
    "corruption, existing",
    [
        (None, False),
        ("amount", False),
        ("scenario", False),
        ("parameters", False),
        ("direction", False),
        (None, True),
    ],
)
def test_estimate_import_reads_back_all_financial_inputs(
    k11: K11World,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str | None,
    existing: bool,
) -> None:
    template = csv_v2.TEMPLATES["estimates"]
    headers = [column.name for column in template.columns]
    base = dict.fromkeys(headers, "") | {
        "contract": K11_EXTERNAL_ID,
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "element_code": "RECONCILED-REBATE",
        "vc_element_type": "REBATE",
        "method": "EXPECTED_VALUE",
        "effective_date": "2026-09-30",
        "parameters.refund_liability_target": "1620.00",
        "unconstrained_amount": "1620.00",
        "most_conservative_amount": "0.00",
        "constrained_amount": "1620.00",
        "rationale": "Volume rebate scenarios.",
    }
    if existing:
        imports = invoice_tests.importer(k11)
        (current,) = imports.rows(
            select(contract.c.id).where(contract.c.external_id == K11_EXTERNAL_ID)
        )
        created = post(
            k11.app,
            f"/api/v1/contracts/{current['id']}/estimates",
            imports.actor,
            {
                "estimate_kind": "VARIABLE_CONSIDERATION",
                "element_code": "RECONCILED-REBATE",
                "vc_element_type": "REBATE",
                "direction": "INCREASE",
                "method": "EXPECTED_VALUE",
            },
        )
        assert created.status_code == 201, created.text
        base["vc_element_type"] = ""  # Omitted existing-element metadata is inherited.
    rows = []
    for outcome, amount, probability in (("Reached", "2700.00", "0.6"), ("Missed", "0.00", "0.4")):
        row = base | {
            "lines.outcome": outcome,
            "lines.amount": amount,
            "lines.probability": probability,
        }
        rows.append([row[name] for name in headers])
    imports = invoice_tests.importer(k11)
    import_id = diffed(
        imports, "estimate-inputs.csv", invoice_tests.csv_bytes(headers, rows), "estimates"
    )
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200
    assert (
        approve(k11.app, str(submitted.json()["approval_request_id"]), k11.priya).status_code == 200
    )

    def changed(uow: Any, plan: Any, *, context: Any) -> Any:
        body = copy.deepcopy(plan.body)
        if corruption == "amount":
            body["constrained_amount"] = "1500.00"
        elif corruption == "scenario":
            body["lines"][0]["amount"] = "2600.00"
            body["lines"][1]["amount"] = "100.00"
        elif corruption == "direction":
            body["direction"] = "INCREASE"
        elif corruption == "parameters":
            body["parameters"]["refund_liability_target"] = "1500.00"
        return template.apply(uow, dataclasses.replace(plan, body=body), context=context)

    monkeypatch.setattr(
        csv_v2,
        "TEMPLATES",
        {**csv_v2.TEMPLATES, "estimates": dataclasses.replace(template, apply=changed)},
    )
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == ("COMMITTED" if corruption is None else "FAILED"), done
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    elements = imports.rows(select(estimate).where(estimate.c.element_code == "RECONCILED-REBATE"))
    if corruption is None:
        assert check["source"] == check["stored"]
        (version,) = check["stored"]["versions"]
        assert version["currency"] == "EUR"
        assert version["direction"] == ("INCREASE" if existing else "DECREASE")
        assert version["constrained_amount"] == "1620"
        assert [line["amount"] for line in version["scenarios"]] == ["2700", "0"]
        assert len(elements) == 1
        assert (
            len(
                imports.rows(
                    select(estimate_version.c.id).where(
                        estimate_version.c.estimate_id == elements[0]["id"]
                    )
                )
            )
            == 1
        )
    else:
        assert check["source"] != check["stored"]
        assert elements == []
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
