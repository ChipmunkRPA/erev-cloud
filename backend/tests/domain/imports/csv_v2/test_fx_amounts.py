"""CTL-002: FX versions and inverses reconcile before import commit becomes durable."""

from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import (
    approval_request,
    exception_item,
    fx_rate,
    fx_rate_set_version,
    import_row_lineage,
    source_record,
)
from erev_api.domain.imports import csv_v2
from erev_api.domain.imports.csv_v2.framework import flatten
from erev_api.domain.imports.csv_v2.fx_rates import FxRatesIn
from erev_api.domain.reference import fx
from sqlalchemy import select
from support.factories import import_world, run_import_job
from support.legacy_replay import diffed, job_of, shown, submit
from support.principals import colleague, enrolled
from support.reference import approve, assign, calendar, post, put
from tests.domain.imports.csv_v2 import test_templates as shared

app = shared.app
files = shared.files


@pytest.mark.parametrize(
    "kind,corruption",
    [
        ("spot", None),
        ("closing", None),
        ("average", None),
        ("spot", "explicit_inverse"),
        ("spot", "half_up"),
        ("spot", "rate"),
        ("spot", "currency"),
        ("spot", "day"),
        ("closing", "period"),
        ("spot", "coverage"),
        ("spot", "set"),
        ("spot", "derived"),
        ("spot", "missing_inverse"),
        ("spot", "missing_target"),
        ("spot", "swapped_targets"),
        ("spot", "second_version"),
        ("spot", "second_version_bad"),
    ],
)
def test_fx_import_reconciles_complete_submitted_version(
    app: Any,
    keyring: Any,
    clock: Any,
    files: Any,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    corruption: str | None,
) -> None:
    world = import_world(app, keyring, clock, files)
    calendar(app, world.actor)
    people = {}
    for name, roles in (
        ("reviewer", ("revenue_reviewer",)),
        ("controller", ("controller", "tenant_admin")),
    ):
        person = colleague(world.tenant_id, name)
        for role in roles:
            assign(person, role)
        people[name] = enrolled(app, clock, person)
    enabled = put(
        app,
        "/api/v1/tenant-currencies",
        people["controller"],
        {"currency_codes": ["USD", "EUR", "GBP"]},
    )
    assert enabled.status_code == 200, enabled.text
    for code in ("RATES", "OTHER-RATES"):
        created = post(
            app,
            "/api/v1/fx-rate-sets",
            world.actor,
            {"code": code, "name": code, "rate_type": kind},
        )
        assert created.status_code == 201, created.text
    headers = [column.name for column in flatten(FxRatesIn)]
    row = dict.fromkeys(headers, "") | {
        "fx_rate_set_code": "RATES",
        "coverage_from": "2026-08-01",
        "coverage_to": "2026-09-30",
        "lines.base_currency": "EUR",
        "lines.quote_currency": "USD",
        "lines.rate": "8192" if corruption == "half_up" else "1.123456789012",
        "lines.effective_date": "2026-09-12" if kind == "spot" else "",
        "lines.period_key": "" if kind == "spot" else "FY2026-P09",
    }
    rows = [list(row.values())]
    if corruption in ("explicit_inverse", "swapped_targets"):
        rows.append(
            list(
                (
                    row
                    | {
                        "lines.base_currency": "USD",
                        "lines.quote_currency": "EUR",
                        "lines.rate": "0.9",
                    }
                ).values()
            )
        )
    if corruption in ("second_version", "second_version_bad"):
        rows.append(
            list(
                (
                    row
                    | {
                        "coverage_from": "2026-10-01",
                        "coverage_to": "2026-10-31",
                        "lines.effective_date": "2026-10-12",
                    }
                ).values()
            )
        )
    import_id = diffed(world, "fx.csv", shared.csv_bytes(headers, rows), "fx_rates")
    submitted = submit(world, import_id)
    assert submitted.status_code == 200, submitted.text
    decision = approve(app, submitted.json()["approval_request_id"], people["reviewer"])
    assert decision.status_code == 200, decision.text
    template = csv_v2.TEMPLATES["fx_rates"]

    def changed(uow: Any, plan: Any, *, context: Any) -> Any:
        body = copy.deepcopy(plan.body)
        if corruption == "second_version_bad" and body["coverage_from"] == "2026-10-01":
            body["lines"][0]["rate"] = "1.12"
        elif corruption == "rate":
            body["lines"][0]["rate"] = "1.123456789013"
        elif corruption == "currency":
            body["lines"][0]["base_currency"] = "GBP"
        elif corruption == "day":
            body["lines"][0]["effective_date"] = "2026-09-13"
        elif corruption == "period":
            body["lines"][0]["period_key"] = "FY2026-P08"
        elif corruption == "coverage":
            body["coverage_from"] = "2026-08-02"
        elif corruption == "set":
            body["fx_rate_set_code"] = "OTHER-RATES"
        applied = template.apply(uow, replace(plan, body=body), context=context)
        if corruption == "missing_target":
            applied.targets.clear()
        if corruption == "swapped_targets":
            first, second = plan.rows
            applied.row_targets[first.id], applied.row_targets[second.id] = (
                applied.row_targets[second.id],
                applied.row_targets[first.id],
            )
        return applied

    monkeypatch.setattr(
        csv_v2, "TEMPLATES", {**csv_v2.TEMPLATES, "fx_rates": replace(template, apply=changed)}
    )
    if corruption in ("derived", "missing_inverse"):
        original = fx.derived_inverses

        def altered_inverses(rows: Any) -> Any:
            derived, zero = original(rows)
            if corruption == "missing_inverse":
                return [], zero
            return [
                replace(value, rate=value.rate + Decimal("0.000000000001")) for value in derived
            ], zero

        monkeypatch.setattr(fx, "derived_inverses", altered_inverses)
    run_import_job(world, job_of(world, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(world, import_id)
    if corruption in (None, "explicit_inverse", "half_up", "second_version"):
        assert done["status"] == "COMMITTED", done
        checks = done["control_totals"]["loaded"]["monetary_checks"]
        assert len(checks) == (2 if corruption == "second_version" else 1)
        assert all(check["source"] == check["stored"] for check in checks)
        rates = checks[0]["stored"]["rates"]
        assert len(rates) == 2
        assert sum(rate["is_derived"] for rate in rates) == (
            0 if corruption == "explicit_inverse" else 1
        )
        if corruption == "half_up":
            assert rates[1]["rate"] == "0.000122070313"
        if kind != "spot":
            assert all(rate["effective_date"] == "2026-09-30" for rate in rates)
        versions = world.rows(select(fx_rate_set_version))
        assert len(versions) == len(checks)
        assert all(version["status"] == "SUBMITTED" for version in versions)
    else:
        assert done["status"] == "FAILED", done
        assert world.rows(
            select(exception_item.c.id).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        assert not world.rows(select(fx_rate_set_version))
        assert not world.rows(select(fx_rate))
        assert not world.rows(
            select(approval_request.c.id).where(
                approval_request.c.subject_type == "FX_RATE_SET_VERSION"
            )
        )
        for table in (source_record, import_row_lineage):
            assert not world.rows(
                select(table.c.id).where(table.c.import_upload_id == UUID(import_id))
            )
