"""API-R-19 currencies and tenant currencies (04 §15.3 API-R-19, T-REF-08, T-REF-09, AUD-CMD;
03 REQ-REF-004; BUILD_SPEC RFD-3).

Omar holds Viewer (``config.read``); Maya holds Revenue Accountant (``masterdata.maintain``, not
``settings.manage``); Lena holds Tenant Admin (``settings.manage``, MFA-gated) (docs/02-PRD.md
§5.6).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.principals import colleague, enrolled, member
from support.reference import assign, fields, get, holding, put, slug

CURRENCIES = "/api/v1/currencies"
TENANT_CURRENCIES = "/api/v1/tenant-currencies"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_currency_minor_units(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    omar = holding(app, member(keyring, clock), "viewer")
    listed = get(app, CURRENCIES, omar, {"code": ["JPY", "USD", "BHD", "CLF"]})
    assert listed.status_code == 200, listed.text
    assert [(item["code"], item["minor_unit"]) for item in listed.json()["items"]] == [
        ("BHD", 3),
        ("CLF", 4),
        ("JPY", 0),
        ("USD", 2),
    ]
    euro = get(app, CURRENCIES, omar, {"q": "euro"}).json()["items"]
    assert ("EUR", "978", True) in [
        (item["code"], item["numeric_code"], item["is_active"]) for item in euro
    ]
    everything = get(app, CURRENCIES, omar, {"limit": 200})
    assert {item["minor_unit"] for item in everything.json()["items"]} <= {0, 1, 2, 3, 4}


def test_enable_currencies_requires_settings_manage(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    assert "masterdata.maintain" in DEFAULT_ROLES["revenue_accountant"]
    assert "settings.manage" not in DEFAULT_ROLES["revenue_accountant"]
    lena_member = member(keyring, clock)
    assign(lena_member, "tenant_admin")
    lena = enrolled(app, clock, lena_member)
    maya = holding(app, colleague(lena_member.tenant_id, "maya"), "revenue_accountant")
    provisioned = get(app, TENANT_CURRENCIES, maya).json()["items"]
    assert [(item["currency_code"], item["is_enabled"]) for item in provisioned] == [("USD", True)]

    body = {"currency_codes": ["USD", "EUR", "GBP", "JPY"]}
    denied = put(app, TENANT_CURRENCIES, maya, body)
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    enabled = put(app, TENANT_CURRENCIES, lena, body)
    assert enabled.status_code == 200, enabled.text
    assert [
        (
            item["currency_code"],
            item["is_enabled"],
            item["is_reporting_currency"],
            item["minor_unit"],
        )
        for item in enabled.json()["items"]
    ] == [
        ("EUR", True, False, 2),
        ("GBP", True, False, 2),
        ("JPY", True, False, 0),
        ("USD", True, True, 2),
    ]
    listed = get(app, TENANT_CURRENCIES, maya, {"is_enabled": "true"})
    assert [item["currency_code"] for item in listed.json()["items"]] == [
        "EUR",
        "GBP",
        "JPY",
        "USD",
    ]

    refused = put(app, TENANT_CURRENCIES, lena, {"currency_codes": ["EUR", "ABC", "EUR"]})
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [
        ("currency_codes.1", "T-REF-09"),
        ("currency_codes.2", "T-REF-09"),
        ("currency_codes", "T-REF-09"),
    ]
    narrowed = put(app, TENANT_CURRENCIES, lena, {"currency_codes": ["EUR", "USD"]})
    assert narrowed.status_code == 200, narrowed.text
    assert [(item["currency_code"], item["is_enabled"]) for item in narrowed.json()["items"]] == [
        ("EUR", True),
        ("GBP", False),
        ("JPY", False),
        ("USD", True),
    ]

    context = DbContext(tenant_id=lena_member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        events = session.execute(
            select(audit_event.c.action, audit_event.c.after, audit_event.c.actor_id)
            .where(audit_event.c.object_type == "tenant_currency")
            .order_by(audit_event.c.chain_seq)
        ).all()
    # One event per changed row; the order of events across commits is not asserted.
    assert sorted(
        (action, after["currency_code"], after["is_enabled"]) for action, after, _ in events
    ) == [
        ("tenant_currency.create", "EUR", True),
        ("tenant_currency.create", "GBP", True),
        ("tenant_currency.create", "JPY", True),
        ("tenant_currency.update", "GBP", False),
        ("tenant_currency.update", "JPY", False),
    ]
    assert {actor for _, _, actor in events} == {UUID(str(lena_member.user_id))}
