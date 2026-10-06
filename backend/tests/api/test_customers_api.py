"""API-R-22 customer maintenance permissions (04 §15.3 API-R-22; SCREENS §9.1; docs/02-PRD.md §5.6;
BUILD_SPEC RFD-8).

Reads need ``contract.read``, which Viewer carries. Creating or changing a customer or a
related-party group needs ``masterdata.maintain``, which Revenue Accountant carries and Viewer does
not.
"""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.principals import colleague, member
from support.reference import get, holding, patch, post, slug

CUSTOMERS = "/api/v1/customers"
GROUPS = "/api/v1/related-party-groups"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_maintenance_requires_masterdata_maintain(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")
    pellworth = {"code": "C-01", "name": "Pellworth Logistics Inc. (Demo)", "country_code": "US"}

    denied = post(app, CUSTOMERS, omar, pellworth)
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    group_denied = post(app, GROUPS, omar, {"code": "HOLLENBRAND", "name": "Hollenbrand (Demo)"})
    assert (group_denied.status_code, slug(group_denied)) == (403, "forbidden"), group_denied.text

    created = post(app, CUSTOMERS, maya, pellworth)
    assert created.status_code == 201, created.text
    group = post(app, GROUPS, maya, {"code": "HOLLENBRAND", "name": "Hollenbrand (Demo)"})
    assert group.status_code == 201, group.text
    customer_path = f"{CUSTOMERS}/{created.json()['id']}"
    group_path = f"{GROUPS}/{group.json()['id']}"
    refused = patch(app, customer_path, omar, {"is_active": False}, if_match='"r1"')
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    group_refused = patch(app, group_path, omar, {"name": "Renamed"}, if_match='"r1"')
    assert (group_refused.status_code, slug(group_refused)) == (403, "forbidden")

    # contract.read reads customers and related-party groups; nothing changed.
    listed = get(app, CUSTOMERS, omar)
    assert listed.status_code == 200, listed.text
    assert [(item["code"], item["is_active"]) for item in listed.json()["items"]] == [
        ("C-01", True)
    ]
    one = get(app, customer_path, omar)
    assert (one.status_code, one.headers["ETag"]) == (200, '"r1"'), one.text
    groups = get(app, GROUPS, omar)
    assert groups.status_code == 200, groups.text
    assert [(item["name"], item["member_count"]) for item in groups.json()["items"]] == [
        ("Hollenbrand (Demo)", 0)
    ]
