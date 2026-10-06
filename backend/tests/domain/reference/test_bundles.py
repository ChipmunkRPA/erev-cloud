"""Bundle components (04 T-REF-21, API-R-23; 03 REQ-REF-013; ENGINE_SPEC §3.3 S03-R-03; SCREENS
§10.4; BUILD_SPEC RFD-9).

Maya holds Revenue Accountant (``masterdata.maintain``, ``contract.read``; docs/02-PRD.md §5.6) and
maintains the products of PRD §2.6 and the bundle BUNDLE-X. A PUT sends every component row of the
bundle; rows sharing a ``valid_from`` form one set, and a later set ends the earlier one.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event
from erev_api.domain.reference import products
from erev_api.main import create_app
from erev_engine.bundle import BundleComponentInput
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.principals import Actor, member
from support.reference import PRODUCTS, fields, get, holding, new_product, patch, put, slug


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def maya(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    return holding(app, member(keyring, clock), "revenue_accountant")


def components_path(product_id: str) -> str:
    return f"{PRODUCTS}/{product_id}/bundle-components"


def row(component: Mapping[str, Any], *, sequence: int, **extra: Any) -> dict[str, Any]:
    return {
        "component_product_id": component["id"],
        "sequence": sequence,
        "valid_from": "2026-01-01",
        **extra,
    }


def bundle_x(app: FastAPI, maya: Actor) -> dict[str, Any]:
    return new_product(app, maya, code="BUNDLE-X", name="Platform bundle X", is_bundle=True)


def tenant_context(actor: Actor) -> DbContext:
    return DbContext(tenant_id=actor.member.tenant_id, user_id=None, entity_scope="*")


def audit_counts(actor: Actor) -> dict[str, int]:
    statement = (
        select(audit_event.c.action, func.count())
        .where(audit_event.c.object_type == "product_bundle_component")
        .group_by(audit_event.c.action)
    )
    with tenant_session(tenant_context(actor), read_only=True) as session:
        return {str(action): int(count) for action, count in session.execute(statement)}


def summary(body: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            item["component_product"]["code"],
            item["quantity_per_bundle"],
            item["split_basis"],
            item["split_ratio"],
            item["sequence"],
            item["valid_from"],
            item["valid_to"],
        )
        for item in body["components"]
    ]


def test_fixed_percentages_sum_to_one(app: FastAPI, maya: Actor) -> None:
    bundle = bundle_x(app, maya)
    platform = new_product(app, maya, code="AVM-PLAT-ENT", name="Platform, enterprise tier")
    implementation = new_product(app, maya, code="AVM-IMPL-STD", name="Implementation, standard")
    fixed = {"split_basis": "fixed_percentage"}

    short = put(
        app,
        components_path(bundle["id"]),
        maya,
        {
            "components": [
                row(platform, sequence=1, split_ratio="0.60", **fixed),
                row(implementation, sequence=2, split_ratio="0.30", **fixed),
            ]
        },
    )
    assert (short.status_code, slug(short)) == (422, "validation-failed"), short.text
    assert fields(short) == [("components", "REQ-REF-013")]
    assert short.json()["errors"][0]["message"] == (
        "The split percentages of the components valid from 2026-01-01 total 90%. "
        "They must total 100%."
    )
    assert get(app, components_path(bundle["id"]), maya).json()["components"] == []

    whole = put(
        app,
        components_path(bundle["id"]),
        maya,
        {
            "components": [
                row(platform, sequence=1, split_ratio="0.60", **fixed),
                row(implementation, sequence=2, split_ratio="0.40", **fixed),
            ]
        },
    )
    assert whole.status_code == 200, whole.text
    body = whole.json()
    assert body["bundle_product_id"] == bundle["id"]
    assert summary(body) == [
        ("AVM-PLAT-ENT", "1", "fixed_percentage", "0.6", 1, "2026-01-01", None),
        ("AVM-IMPL-STD", "1", "fixed_percentage", "0.4", 2, "2026-01-01", None),
    ]
    assert get(app, components_path(bundle["id"]), maya).json() == body


def test_bundle_components_valid_at_date(app: FastAPI, maya: Actor) -> None:
    bundle = bundle_x(app, maya)
    platform = new_product(app, maya, code="AVM-PLAT-ENT", name="Platform, enterprise tier")
    implementation = new_product(app, maya, code="AVM-IMPL-STD", name="Implementation, standard")
    support = new_product(app, maya, code="AVM-SUP-12", name="Platform support, 12 months")

    saved = put(
        app,
        components_path(bundle["id"]),
        maya,
        {
            "components": [
                row(platform, sequence=1),
                row(implementation, sequence=2, quantity_per_bundle="2"),
                row(support, sequence=1, valid_from="2026-07-01"),
                row(platform, sequence=2, valid_from="2026-07-01"),
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    # The replacement set from 2026-07-01 ends the first set there.
    assert summary(saved.json()) == [
        ("AVM-PLAT-ENT", "1", "relative_ssp", None, 1, "2026-01-01", "2026-07-01"),
        ("AVM-IMPL-STD", "2", "relative_ssp", None, 2, "2026-01-01", "2026-07-01"),
        ("AVM-SUP-12", "1", "relative_ssp", None, 1, "2026-07-01", None),
        ("AVM-PLAT-ENT", "1", "relative_ssp", None, 2, "2026-07-01", None),
    ]

    bundle_id = UUID(bundle["id"])
    with tenant_session(tenant_context(maya), read_only=True) as session:
        september = products.bundle_components(session, bundle_id, at=date(2026, 9, 1))
        march = products.bundle_components(session, bundle_id, at=date(2026, 3, 1))
        switch = products.bundle_components(session, bundle_id, at=date(2026, 7, 1))
        before = products.bundle_components(session, bundle_id, at=date(2025, 12, 31))
    assert september == (
        BundleComponentInput(
            component_product_code="AVM-SUP-12",
            quantity_per_bundle=Decimal(1),
            split_basis="relative_ssp",
            split_ratio=None,
            sequence=1,
            valid_from=date(2026, 7, 1),
            valid_to=None,
        ),
        BundleComponentInput(
            component_product_code="AVM-PLAT-ENT",
            quantity_per_bundle=Decimal(1),
            split_basis="relative_ssp",
            split_ratio=None,
            sequence=2,
            valid_from=date(2026, 7, 1),
            valid_to=None,
        ),
    )
    assert [
        (item.component_product_code, item.sequence, item.quantity_per_bundle) for item in march
    ] == [
        ("AVM-PLAT-ENT", 1, Decimal(1)),
        ("AVM-IMPL-STD", 2, Decimal(2)),
    ]
    assert [item.component_product_code for item in switch] == ["AVM-SUP-12", "AVM-PLAT-ENT"]
    assert before == ()


def test_component_differs_from_bundle(app: FastAPI, maya: Actor) -> None:
    bundle = bundle_x(app, maya)
    itself = put(
        app, components_path(bundle["id"]), maya, {"components": [row(bundle, sequence=1)]}
    )
    assert (itself.status_code, slug(itself)) == (422, "validation-failed"), itself.text
    assert fields(itself) == [("components[0].component_product_id", "T-REF-21")]
    assert itself.json()["errors"][0]["message"] == (
        "A component must be another product than the bundle."
    )
    assert get(app, components_path(bundle["id"]), maya).json()["components"] == []


def test_bundle_component_findings_and_replacement(app: FastAPI, maya: Actor) -> None:
    kit = new_product(app, maya, code="AVM-KIT", name="Sensor kit")
    fleet = new_product(app, maya, code="AVM-FLEET", name="Gateway fleet package", is_bundle=True)
    gateway = new_product(app, maya, code="AVM-GW", name="Sensor gateway unit")
    part = new_product(app, maya, code="AVM-PART", name="Automotive sensor part")

    not_bundle = put(
        app, components_path(kit["id"]), maya, {"components": [row(gateway, sequence=1)]}
    )
    assert fields(not_bundle) == [("is_bundle", "T-REF-21")], not_bundle.text

    unknown = {"id": str(maya.member.tenant_id)}
    findings = put(
        app,
        components_path(fleet["id"]),
        maya,
        {
            "components": [
                row(unknown, sequence=9),
                row(gateway, sequence=1, quantity_per_bundle="0", split_ratio="0.5"),
                row(part, sequence=1, split_basis="fixed_percentage", valid_to="2026-01-01"),
                row(gateway, sequence=3, split_basis="fixed_percentage", split_ratio="1.5"),
            ]
        },
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("components[0].component_product_id", "T-REF-21"),
        ("components[1].quantity_per_bundle", "T-REF-21"),
        ("components[1].split_ratio", "T-REF-21"),
        ("components[2].split_ratio", "T-REF-21"),
        ("components[2].valid_to", "T-REF-21"),
        ("components[2].sequence", "T-REF-21"),
        ("components[3].split_ratio", "T-REF-21"),
        ("components[3].component_product_id", "T-REF-21"),
        ("components", "REQ-REF-013"),
    ]
    missing = get(app, components_path(str(maya.member.tenant_id)), maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text

    first = put(
        app,
        components_path(fleet["id"]),
        maya,
        {"components": [row(gateway, sequence=1, quantity_per_bundle="10"), row(part, sequence=2)]},
    )
    assert first.status_code == 200, first.text
    replacement = {
        "components": [row(gateway, sequence=1, quantity_per_bundle="12"), row(kit, sequence=2)]
    }
    second = put(app, components_path(fleet["id"]), maya, replacement)
    assert second.status_code == 200, second.text
    assert [
        (item["component_product"]["code"], item["quantity_per_bundle"], item["row_version"])
        for item in second.json()["components"]
    ] == [("AVM-GW", "12", 2), ("AVM-KIT", "1", 1)]
    counts = {
        "product_bundle_component.create": 3,
        "product_bundle_component.update": 1,
        "product_bundle_component.delete": 1,
    }
    assert audit_counts(maya) == counts
    unchanged = put(app, components_path(fleet["id"]), maya, replacement)
    assert unchanged.status_code == 200, unchanged.text
    assert audit_counts(maya) == counts

    # Bundle cannot be cleared while components exist.
    clearing = patch(app, f"{PRODUCTS}/{fleet['id']}", maya, {"is_bundle": False}, if_match='"r1"')
    assert fields(clearing) == [("is_bundle", "T-REF-21")], clearing.text
    emptied = put(app, components_path(fleet["id"]), maya, {"components": []})
    assert (emptied.status_code, emptied.json()["components"]) == (200, []), emptied.text
    cleared = patch(app, f"{PRODUCTS}/{fleet['id']}", maya, {"is_bundle": False}, if_match='"r1"')
    assert (cleared.status_code, cleared.json()["is_bundle"]) == (200, False), cleared.text
