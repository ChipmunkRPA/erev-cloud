"""Supervisor ruling R-116 (g): in quarantine mode (``data.quarantine_failed_rows``, REQ-DAT-008)
EVERY object a file builds from several rows loads whole or not at all — the bundle of a
``bundles`` file, the DRAFT mapping version of an ``account_mapping`` file, the DRAFT version an
``ssp_values`` file builds for a book and the rate set version an ``fx_rates`` file submits —
"because the reviewer of a DRAFT sees what the version holds, not what the file meant to put
there" (05 IPL-05; PRD IMP-134; ``imports.scope.TemplateScope.unit``).

Measured before the change, each of the four with one row of its object refused at validation:
the bundle, which had two components, was left with ONE, in force at once; the mapping version
held one of its two rules; the SSP version one of its two entries; the rate set version, already
submitted for approval, one of its two rates.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    import_row,
    product,
    product_bundle_component,
    ssp_book_version,
)
from erev_api.domain.imports.csv_v2.account_mapping import AccountMappingRowsIn
from erev_api.domain.imports.csv_v2.bundles import BundleIn
from erev_api.domain.imports.csv_v2.framework import flatten
from erev_api.domain.imports.csv_v2.fx_rates import FxRatesIn
from erev_api.domain.imports.csv_v2.ssp_values import SspValuesIn
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.schemas.accounts import GlAccountIn
from erev_api.schemas.products import ProductIn
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    ImportWorld,
    Workspace,
    import_world,
    imported,
    j03_world,
    run_import_job,
)
from support.legacy_replay import job_of, shown, submit
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, calendar, get, post, put
from support.rows import publish_registry_version

INCOMPLETE = "IMPORT_CONTRACT_INCOMPLETE"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def csv_bytes(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def importer(place: Workspace) -> ImportWorld:
    return ImportWorld(
        app=place.app,
        actor=place.author,
        runtime=JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files),
        clock=place.clock,
    )


def committed(
    imports: ImportWorld, approver: Actor, name: str, content: bytes, template_code: str
) -> dict[str, Any]:
    """A file every row of which is usable, through to COMMITTED."""
    import_id, validated = imported(imports, name, content, template_code)
    assert validated["status"] == "VALIDATED", validated
    done = taken(imports, approver, import_id)
    assert done["status"] == "COMMITTED", done
    return done


def quarantine_mode(imports: ImportWorld) -> None:
    context = DbContext(tenant_id=imports.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=imports.tenant_id,
            category=RegistryCategory.INTEGRATION,
            values={"data.quarantine_failed_rows": True},
        )


def rows_of(imports: ImportWorld, import_id: str) -> list[tuple[int, str]]:
    return [
        (int(row["row_number"]), str(row["status"]))
        for row in imports.rows(
            select(import_row.c.row_number, import_row.c.status)
            .where(import_row.c.import_upload_id == UUID(import_id))
            .order_by(import_row.c.row_number)
        )
    ]


def findings_of(imports: ImportWorld, import_id: str) -> dict[int, list[tuple[str, str]]]:
    """row number -> (code, message) of each finding, from the import's own read."""
    listed = get(imports.app, f"/api/v1/imports/{import_id}/rows", imports.actor, {"limit": "50"})
    assert listed.status_code == 200, listed.text
    return {
        int(item["row_number"]): [
            (str(message["rule_id"]), str(message["message"])) for message in item["messages"]
        ]
        for item in listed.json()["items"]
        if item["messages"]
    }


def taken(imports: ImportWorld, approver: Actor, import_id: str) -> dict[str, Any]:
    """A VALIDATED upload diffed, submitted, approved and committed; API-S-Import afterwards."""
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_DIFF"))
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(imports.app, str(submitted.json()["approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    return shown(imports, import_id)


def refusal(kind: str, name: str, short: str) -> str:
    return (
        f"Another row of {kind} {name} was refused, so none of its rows is loaded. "
        f"Correct that row and upload the {short}'s rows again."
    )


def products(
    imports: ImportWorld, approver: Actor, codes: Sequence[tuple[str, str]]
) -> dict[str, str]:
    headers = [column.name for column in flatten(ProductIn)]
    rows = []
    for code, bundle in codes:
        values = dict.fromkeys(headers, "")
        values |= {"code": code, "name": code, "principal_agent": "PRINCIPAL", "is_bundle": bundle}
        rows.append(list(values.values()))
    committed(imports, approver, "products.csv", csv_bytes(headers, rows), "products")
    return {
        str(row["code"]): str(row["id"])
        for row in imports.rows(
            select(product.c.code, product.c.id).where(
                product.c.code.in_([code for code, _ in codes])
            )
        )
    }


def test_a_bundle_keeps_its_components_when_a_row_of_its_file_is_refused(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``bundles``: the rows of one bundle REPLACE its component rows, in force at once. A file
    states AVM-BUNDLE-01 again — one of its two rows with a date that is no date — and
    AVM-BUNDLE-02 whole. The usable row of the first bundle is refused with the other, by name;
    the bundle keeps the two components it had, and the second bundle is loaded. Before: the
    first bundle was left with the one component of the row that passed."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")
    imports = importer(j03.place)
    ids = products(
        imports,
        j03.priya,
        [
            ("AVM-KIT-10", "false"),
            ("AVM-KIT-11", "false"),
            ("AVM-BUNDLE-01", "true"),
            ("AVM-BUNDLE-02", "true"),
        ],
    )
    headers = [column.name for column in flatten(BundleIn)]

    def component(
        bundle: str, part: str, sequence: int, valid_from: str = "2026-01-01"
    ) -> list[str]:
        values = dict.fromkeys(headers, "")
        values |= {
            "product_code": bundle,
            "lines.component_product_id": ids[part],
            "lines.quantity_per_bundle": "1",
            "lines.split_basis": "relative_ssp",
            "lines.sequence": str(sequence),
            "lines.valid_from": valid_from,
        }
        return list(values.values())

    def components(bundle: str) -> list[str]:
        return [
            str(row["component_product_id"])
            for row in imports.rows(
                select(product_bundle_component.c.component_product_id)
                .where(product_bundle_component.c.bundle_product_id == UUID(ids[bundle]))
                .order_by(product_bundle_component.c.sequence)
            )
        ]

    whole = [
        component("AVM-BUNDLE-01", "AVM-KIT-10", 1),
        component("AVM-BUNDLE-01", "AVM-KIT-11", 2),
    ]
    committed(imports, j03.priya, "bundles.csv", csv_bytes(headers, whole), "bundles")
    assert components("AVM-BUNDLE-01") == [ids["AVM-KIT-10"], ids["AVM-KIT-11"]]

    quarantine_mode(imports)
    again = [
        component("AVM-BUNDLE-01", "AVM-KIT-10", 1),
        component("AVM-BUNDLE-01", "AVM-KIT-11", 2, valid_from="01/13/2026x"),
        component("AVM-BUNDLE-02", "AVM-KIT-10", 1),
    ]
    import_id, validated = imported(imports, "bundles-q.csv", csv_bytes(headers, again), "bundles")
    assert validated["status"] == "VALIDATED", validated
    assert rows_of(imports, import_id) == [(2, "ERROR"), (3, "ERROR"), (4, "VALID")]
    found = findings_of(imports, import_id)
    assert [code for code, _ in found[2]] == [INCOMPLETE]
    assert refusal("bundle", "AVM-BUNDLE-01", "bundle") in found[2][0][1]
    assert INCOMPLETE not in [code for code, _ in found[3]]
    done = taken(imports, j03.priya, import_id)
    assert done["status"] == "COMMITTED", done
    assert done["control_totals"]["loaded"] == {"rows": 1, "quarantined": 2}
    assert components("AVM-BUNDLE-01") == [ids["AVM-KIT-10"], ids["AVM-KIT-11"]]
    assert components("AVM-BUNDLE-02") == [ids["AVM-KIT-10"]]


def test_a_mapping_version_is_built_whole_or_not_at_all(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``account_mapping``: the rows of one ``name`` make one DRAFT version. A file states
    AVM-MAP-A, one of whose two rules names an entity that is none, and AVM-MAP-B whole. No
    version AVM-MAP-A is created; AVM-MAP-B is, with its rule. Before: AVM-MAP-A was created
    with the one rule that passed."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")
    imports = importer(j03.place)
    account_headers = [column.name for column in flatten(GlAccountIn)]
    values = dict.fromkeys(account_headers, "")
    values |= {"code": "4020", "name": "Revenue", "account_type": "REVENUE", "normal_balance": "C"}
    committed(
        imports,
        j03.priya,
        "gl.csv",
        csv_bytes(account_headers, [list(values.values())]),
        "gl_accounts",
    )
    account_id = imports.scalar(select(gl_account.c.id).where(gl_account.c.code == "4020"))
    headers = [column.name for column in flatten(AccountMappingRowsIn)]

    def rule(name: str, role: str, entity: str = "") -> list[str]:
        values = dict.fromkeys(headers, "")
        values |= {
            "name": name,
            "effective_from": "2026-07-01T00:00:00Z",
            "lines.account_role": role,
            "lines.gl_account_id": str(account_id),
            "lines.priority": "10",
            "lines.entity_id": entity,
        }
        return list(values.values())

    quarantine_mode(imports)
    stated = [
        rule("AVM-MAP-A", "REVENUE"),
        rule("AVM-MAP-A", "CONTRACT_LIABILITY", entity="not-a-uuid"),
        rule("AVM-MAP-B", "REVENUE"),
    ]
    import_id, validated = imported(
        imports, "mapping-q.csv", csv_bytes(headers, stated), "account_mapping"
    )
    assert validated["status"] == "VALIDATED", validated
    assert rows_of(imports, import_id) == [(2, "ERROR"), (3, "ERROR"), (4, "VALID")]
    found = findings_of(imports, import_id)
    assert [code for code, _ in found[2]] == [INCOMPLETE]
    assert refusal("mapping version", "AVM-MAP-A", "version") in found[2][0][1]
    done = taken(imports, j03.priya, import_id)
    assert done["status"] == "COMMITTED", done
    versions = {
        str(row["name"]): (str(row["status"]), row["id"])
        for row in imports.rows(
            select(
                account_mapping_version.c.name,
                account_mapping_version.c.status,
                account_mapping_version.c.id,
            ).where(account_mapping_version.c.name.in_(["AVM-MAP-A", "AVM-MAP-B"]))
        )
    }
    assert sorted(versions) == ["AVM-MAP-B"]
    assert versions["AVM-MAP-B"][0] == "DRAFT"
    assert (
        imports.scalar(
            select(func.count()).where(
                account_mapping_rule.c.account_mapping_version_id == versions["AVM-MAP-B"][1]
            )
        )
        == 1
    )


def test_the_version_of_an_ssp_book_is_built_whole_or_not_at_all(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``ssp_values``: the rows of one book make one DRAFT version. A file of two entries for
    US-LIST, one with a date that is no date: the other is refused with it, by the book's name,
    nothing is usable and no version is created. Before: a DRAFT version with the one entry that
    passed."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")
    imports = importer(j03.place)
    products(imports, j03.priya, [("AVM-KIT-10", "false"), ("AVM-KIT-11", "false")])
    headers = [column.name for column in flatten(SspValuesIn)]

    def entry(product_code: str, effective_from: str) -> list[str]:
        values = dict.fromkeys(headers, "")
        values |= {
            "ssp_book_code": "US-LIST",
            "legacy_version_label": "2026-Q",
            "effective_from_date": effective_from,
            "methodology_label": "Q3 list-price study",
            "lines.product_code": product_code,
            "lines.currency": "USD",
            "lines.method": "observable",
            "lines.distinctness": "distinct",
            "lines.ranges.low_value": "900.00",
            "lines.ranges.mid_value": "1000.00",
            "lines.ranges.high_value": "1100.00",
        }
        return list(values.values())

    quarantine_mode(imports)
    study = [entry("AVM-KIT-10", "2026-07-01"), entry("AVM-KIT-11", "first of July")]
    import_id, validated = imported(imports, "ssp-q.csv", csv_bytes(headers, study), "ssp_values")
    assert validated["status"] == "INVALID", validated
    assert rows_of(imports, import_id) == [(2, "ERROR"), (3, "ERROR")]
    found = findings_of(imports, import_id)
    assert [code for code, _ in found[2]] == [INCOMPLETE]
    assert refusal("SSP book", "US-LIST", "book") in found[2][0][1]
    assert (
        imports.rows(
            select(ssp_book_version.c.id).where(ssp_book_version.c.legacy_version_label == "2026-Q")
        )
        == []
    )


def test_a_rate_set_version_is_submitted_whole_or_not_at_all(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``fx_rates``: the rows of one rate set and coverage make one version, which the commit
    SUBMITS for approval. A file states two rates for AVM-RATES-SPOT, one with a date that is no
    date, and one rate for AVM-RATES-DESK whole. No version of the first set is created; the
    second set's is, with its rate. Before: the first set's version was submitted with the one
    rate that passed."""
    world = import_world(app, keyring, clock, files)
    calendar(app, world.actor)
    people: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer",)),
        ("carmen", ("controller", "tenant_admin")),
    ):
        someone = colleague(world.tenant_id, name)
        for code in roles:
            assign(someone, code)
        people[name] = enrolled(app, clock, someone)
    enabled = put(
        app,
        "/api/v1/tenant-currencies",
        people["carmen"],
        {"currency_codes": ["USD", "EUR", "GBP"]},
    )
    assert enabled.status_code == 200, enabled.text
    for code, name, rate_type in (
        ("AVM-RATES-SPOT", "Spot rates", "spot"),
        ("AVM-RATES-DESK", "Desk rates", "spot"),
    ):
        created = post(
            app,
            "/api/v1/fx-rate-sets",
            world.actor,
            {"code": code, "name": name, "rate_type": rate_type},
        )
        assert created.status_code == 201, created.text
    headers = [column.name for column in flatten(FxRatesIn)]

    def rate(code: str, base: str, value: str, effective: str = "2026-09-12") -> list[str]:
        row = dict.fromkeys(headers, "")
        row |= {
            "fx_rate_set_code": code,
            "coverage_from": "2026-09-01",
            "coverage_to": "2026-09-30",
            "lines.base_currency": base,
            "lines.quote_currency": "USD",
            "lines.rate": value,
            "lines.effective_date": effective,
        }
        return list(row.values())

    quarantine_mode(world)
    content = csv_bytes(
        headers,
        [
            rate("AVM-RATES-SPOT", "EUR", "1.105"),
            rate("AVM-RATES-SPOT", "GBP", "1.31", effective="12/09/2026x"),
            rate("AVM-RATES-DESK", "EUR", "1.1"),
        ],
    )
    import_id, validated = imported(world, "avm-rates-q.csv", content, "fx_rates")
    assert validated["status"] == "VALIDATED", validated
    assert rows_of(world, import_id) == [(2, "ERROR"), (3, "ERROR"), (4, "VALID")]
    found = findings_of(world, import_id)
    assert [code for code, _ in found[2]] == [INCOMPLETE]
    assert refusal("rate set", "AVM-RATES-SPOT", "set") in found[2][0][1]
    done = taken(world, people["priya"], import_id)
    assert done["status"] == "COMMITTED", done
    versions = world.rows(
        select(fx_rate_set.c.code, fx_rate_set_version.c.id, fx_rate_set_version.c.status)
        .select_from(
            fx_rate_set_version.join(
                fx_rate_set,
                (fx_rate_set.c.tenant_id == fx_rate_set_version.c.tenant_id)
                & (fx_rate_set.c.id == fx_rate_set_version.c.fx_rate_set_id),
            )
        )
        .where(fx_rate_set_version.c.import_upload_id == UUID(import_id))
    )
    assert [(str(row["code"]), str(row["status"])) for row in versions] == [
        ("AVM-RATES-DESK", "SUBMITTED")
    ]
    entered = world.rows(
        select(fx_rate.c.base_currency, fx_rate.c.quote_currency).where(
            fx_rate.c.fx_rate_set_version_id == versions[0]["id"]
        )
    )
    assert {str(row["base_currency"]) for row in entered} | {
        str(row["quote_currency"]) for row in entered
    } == {"EUR", "USD"}
