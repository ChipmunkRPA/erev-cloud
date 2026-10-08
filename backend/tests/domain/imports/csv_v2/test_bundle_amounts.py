"""CTL-002: bundle replacement reads quantities and identities back independently."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import (
    exception_item,
    import_row_lineage,
    product_bundle_component,
    source_record,
)
from erev_api.domain.imports import csv_v2
from erev_api.domain.imports.csv_v2.bundles import BundleIn
from erev_api.domain.imports.csv_v2.framework import flatten
from sqlalchemy import select
from support.factories import import_world, run_import_job
from support.legacy_replay import diffed, job_of, shown, submit
from support.principals import colleague, enrolled
from support.reference import approve, assign, post, put
from tests.domain.imports.csv_v2 import test_templates as shared

app = shared.app
files = shared.files


@pytest.mark.parametrize(
    "corruption",
    [
        None,
        "defaults",
        "quantity",
        "ratio",
        "component",
        "bundle",
        "date",
        "sequence",
        "missing_target",
        "extra_row",
    ],
)
def test_bundle_replacement_reconciles_and_restores_prior_rows(
    app: Any,
    keyring: Any,
    clock: Any,
    files: Any,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str | None,
) -> None:
    world = import_world(app, keyring, clock, files)
    person = colleague(world.tenant_id, "bundle-reviewer")
    assign(person, "revenue_reviewer")
    reviewer = enrolled(app, clock, person)
    ids = {}
    for code in ("BUNDLE", "OTHER-BUNDLE", "PART-A", "PART-B", "PART-C"):
        created = post(
            app,
            "/api/v1/products",
            world.actor,
            {
                "code": code,
                "name": code,
                "principal_agent": "PRINCIPAL",
                "is_bundle": "BUNDLE" in code,
            },
        )
        assert created.status_code == 201, created.text
        ids[code] = created.json()["id"]
    previous = put(
        app,
        f"/api/v1/products/{ids['BUNDLE']}/bundle-components",
        world.actor,
        {
            "components": [
                {
                    "component_product_id": ids["PART-C"],
                    "quantity_per_bundle": "9",
                    "sequence": 1,
                    "valid_from": "2026-01-01",
                }
            ],
        },
    )
    assert previous.status_code == 200, previous.text
    before = world.rows(select(product_bundle_component))
    headers = [column.name for column in flatten(BundleIn)]
    rows = []
    for start in ("2026-01-01", "2026-07-01"):
        for sequence, code in enumerate(("PART-A", "PART-B"), start=1):
            row = dict.fromkeys(headers, "") | {
                "product_code": "BUNDLE",
                "lines.component_product_id": ids[code],
                "lines.quantity_per_bundle": "1.123456789012345678",
                "lines.split_basis": "fixed_percentage",
                "lines.split_ratio": "0.5",
                "lines.sequence": str(sequence),
                "lines.valid_from": start,
            }
            if corruption == "defaults":
                for field in (
                    "lines.quantity_per_bundle",
                    "lines.split_basis",
                    "lines.split_ratio",
                ):
                    row[field] = ""
            rows.append(list(row.values()))
    import_id = diffed(world, "bundles.csv", shared.csv_bytes(headers, rows), "bundles")
    submitted = submit(world, import_id)
    assert submitted.status_code == 200, submitted.text
    decision = approve(app, submitted.json()["approval_request_id"], reviewer)
    assert decision.status_code == 200, decision.text
    template = csv_v2.TEMPLATES["bundles"]

    def changed(uow: Any, plan: Any, *, context: Any) -> Any:
        body = copy.deepcopy(plan.body)
        if corruption == "quantity":
            body["lines"][0]["quantity_per_bundle"] = "2"
        elif corruption == "ratio":
            body["lines"][0]["split_ratio"] = "0.4"
            body["lines"][1]["split_ratio"] = "0.6"
        elif corruption == "component":
            body["lines"][0]["component_product_id"] = ids["PART-C"]
        elif corruption == "bundle":
            body["product_code"] = "OTHER-BUNDLE"
        elif corruption == "date":
            body["lines"][0]["valid_to"] = "2026-06-01"
        elif corruption == "sequence":
            body["lines"][0]["sequence"] = "3"
        applied = template.apply(uow, replace(plan, body=body), context=context)
        if corruption == "missing_target":
            applied.targets.pop()
        elif corruption == "extra_row":
            # A valid extra historical component must also be caught by the complete-list read.
            extra = body["lines"] + [
                {**body["lines"][-1], "valid_from": "2027-01-01", "split_ratio": "1"}
            ]
            from erev_api.domain.reference.commands import put_bundle_components
            from erev_api.schemas.products import BundleComponentsIn

            put_bundle_components(
                uow, product_id=UUID(ids["BUNDLE"]), body=BundleComponentsIn(components=extra)
            )
        return applied

    monkeypatch.setattr(
        csv_v2, "TEMPLATES", {**csv_v2.TEMPLATES, "bundles": replace(template, apply=changed)}
    )
    run_import_job(world, job_of(world, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(world, import_id)
    if corruption in (None, "defaults"):
        assert done["status"] == "COMMITTED", done
        (check,) = done["control_totals"]["loaded"]["monetary_checks"]
        assert check["source"] == check["stored"]
        components = check["stored"]["components"]
        assert len(components) == 4
        assert components[0]["quantity_per_bundle"] == (
            "1" if corruption == "defaults" else "1.123456789012345678"
        )
        assert [item["valid_to"] for item in components] == ["2026-07-01", "2026-07-01", None, None]
    else:
        assert done["status"] == "FAILED", done
        assert world.rows(select(product_bundle_component)) == before
        assert world.rows(
            select(exception_item.c.id).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        for table in (source_record, import_row_lineage):
            assert not world.rows(
                select(table.c.id).where(table.c.import_upload_id == UUID(import_id))
            )
