"""Account mapping routes (04 §15.3 API-R-20, T-REF-15, §15.2 ``unmapped-account-role``; SCREENS
§9.6 test resolution panel; PRD ERR-46; BUILD_SPEC RFD-7).

Maya holds Revenue Accountant (``config.author``) and authors the mapping; Carmen holds Controller
(``config.approve``) and approves it; Omar holds Viewer (``config.read``). The frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.principals import colleague, enrolled, member
from support.reference import (
    ACCOUNT_MAPPINGS,
    assign,
    calendar,
    entity,
    fields,
    get,
    gl_account,
    holding,
    mapping_draft,
    mapping_published,
    post,
    slug,
)

RESOLVE = f"{ACCOUNT_MAPPINGS}/resolve"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_resolve_route(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    carmen_member = colleague(maya_member.tenant_id, "carmen")
    assign(carmen_member, "controller")
    carmen = enrolled(app, clock, carmen_member)
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")
    us = entity(app, maya, code="AVM-US", calendar_id=calendar(app, maya))
    liability = gl_account(
        app,
        maya,
        code="2100",
        name="Contract liability",
        account_type="LIABILITY",
        normal_balance="C",
    )
    published = mapping_published(
        app,
        maya,
        carmen,
        name="AVM-MAP-2026-01",
        effective_from="2026-01-01T00:00:00Z",
        rules=[{"account_role": "CONTRACT_LIABILITY", "gl_account_id": liability}],
    )

    resolved = get(
        app, RESOLVE, maya, {"role": "CONTRACT_LIABILITY", "entity": "AVM-US", "book": "ASC606"}
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["gl_account"] == {"id": liability, "code": "2100", "name": "Contract liability"}
    assert body["source"]["type"] == "account_mapping_rule"
    assert (
        body["source"]["account_mapping_version_id"],
        body["source"]["version_no"],
        body["source"]["specificity"],
        body["source"]["priority"],
        body["source"]["override_key"],
    ) == (published["id"], 1, 0, 0, "CONTRACT_LIABILITY")
    assert (body["role"], body["entity"]["code"], body["book"], body["clearing_purpose"]) == (
        "CONTRACT_LIABILITY",
        "AVM-US",
        "ASC606",
        None,
    )
    assert datetime.fromisoformat(body["known_at"]) == datetime(2026, 9, 12, 12, tzinfo=UTC)

    # The Viewer holds config.read and may name the entity by id.
    by_id = get(app, RESOLVE, omar, {"role": "CONTRACT_LIABILITY", "entity": us["id"]})
    assert (by_id.status_code, by_id.json()["gl_account"]["code"]) == (200, "2100"), by_id.text

    # A purpose on another role, an unknown entity and any product are refused.
    refused = get(
        app,
        RESOLVE,
        maya,
        {
            "role": "CONTRACT_LIABILITY",
            "clearing_purpose": "BILLING",
            "entity": "AVM-XX",
            "product": "AVM-PLAT-ENT",
        },
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [
        ("clearing_purpose", "T-REF-15"),
        ("entity", "T-REF-01"),
        ("product", "T-REF-15"),
    ]

    # Before the version takes effect no account is mapped.
    early = get(
        app, RESOLVE, maya, {"role": "CONTRACT_LIABILITY", "known_at": "2025-12-31T00:00:00Z"}
    )
    assert (early.status_code, slug(early)) == (422, "unmapped-account-role"), early.text
    assert early.json()["detail"] == (
        "No account is mapped for role Contract liability for any entity. "
        "Publish an account mapping, then retry."
    )
    assert early.json()["errors"][0]["role"] == "CONTRACT_LIABILITY"


def test_mapping_commands_require_config_author(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")
    draft = mapping_draft(app, maya, name="AVM-MAP-2026-01", effective_from=None, rules=[])
    for suffix in ("/test", "/submit", "/publish"):
        denied = post(app, f"{ACCOUNT_MAPPINGS}/{draft['id']}{suffix}", omar, {})
        assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    shown = get(app, f"{ACCOUNT_MAPPINGS}/{draft['id']}", omar)
    assert (shown.status_code, shown.headers["ETag"], shown.json()["status"]) == (
        200,
        '"r1"',
        "DRAFT",
    )
    empty = post(app, f"{ACCOUNT_MAPPINGS}/{draft['id']}/test", maya, {})
    assert (empty.status_code, fields(empty)) == (422, [("rules", "T-REF-15")]), empty.text
    unknown = get(app, f"{ACCOUNT_MAPPINGS}/{maya_member.tenant_id}", omar)
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
