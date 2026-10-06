"""FX rate sets and rate resolution (04 §15.3 API-R-19, T-REF-10 to T-REF-12, E-12, DB-04,
§15.2 ``missing-fx-rate``; PRD §2.5 routing row FX_RATE_SET_VERSION, SM-04, ERR-36; 03 REQ-REF-005,
REQ-REF-006; CTL-031; D-11; BUILD_SPEC RFD-3).

Maya holds Revenue Accountant (``config.author``, ``masterdata.maintain``) and prepares rate set
versions; Carmen holds Controller (``config.approve``), is enrolled in MFA and approves them
(docs/02-PRD.md §5.6). The workspace has a January calendar with FY2026 generated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, fx_rate
from erev_api.domain.contracts import bundles
from erev_api.domain.reference import fx
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled, member
from support.reference import assign, calendar, fields, get, holding, patch, post, slug

RATE_SETS = "/api/v1/fx-rate-sets"
VERSIONS = "/api/v1/fx-rate-set-versions"
RATES = "/api/v1/fx-rates"
APPROVALS = "/api/v1/approvals"


@dataclass(frozen=True, slots=True)
class World:
    maya: Actor
    carmen: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.maya.member.tenant_id


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    carmen_member = colleague(maya_member.tenant_id, "carmen")
    assign(carmen_member, "controller")
    carmen = enrolled(app, clock, carmen_member)
    calendar(app, maya)
    return World(maya=maya, carmen=carmen)


def rate_set(app: FastAPI, actor: Actor, *, code: str, rate_type: str) -> dict[str, Any]:
    body = {"code": code, "name": f"{code} rates", "rate_type": rate_type}
    created = post(app, RATE_SETS, actor, body)
    assert created.status_code == 201, created.text
    assert created.headers["ETag"] == '"r1"'
    result: dict[str, Any] = created.json()
    return result


def version(
    app: FastAPI,
    actor: Actor,
    set_id: str,
    *,
    coverage: tuple[str, str],
    rates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    body = {"coverage_from": coverage[0], "coverage_to": coverage[1], "rates": list(rates)}
    created = post(app, f"{RATE_SETS}/{set_id}/versions", actor, body)
    assert created.status_code == 201, created.text
    assert created.headers["Location"] == f"{VERSIONS}/{created.json()['id']}"
    result: dict[str, Any] = created.json()
    return result


def closing(base: str, rate: str, period_key: str, quote: str = "USD") -> dict[str, Any]:
    return {"base_currency": base, "quote_currency": quote, "rate": rate, "period_key": period_key}


def submit(app: FastAPI, actor: Actor, body: Mapping[str, Any]) -> HttpResponse:
    return post(
        app,
        f"{VERSIONS}/{body['id']}/submit",
        actor,
        {"comment": "Treasury month-end rates"},
        if_match=f'"r{body["row_version"]}"',
    )


def approve(app: FastAPI, request_id: str, approver: Actor) -> HttpResponse:
    detail = get(app, f"{APPROVALS}/{request_id}", approver)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    return post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        approver,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "comment": "Agreed to the treasury statement",
        },
    )


def shown(app: FastAPI, actor: Actor, version_id: str) -> dict[str, Any]:
    response = get(app, f"{VERSIONS}/{version_id}", actor)
    assert response.status_code == 200, response.text
    assert response.headers["ETag"] == f'"r{response.json()["row_version"]}"'
    result: dict[str, Any] = response.json()
    return result


def publish(app: FastAPI, world: World, draft: Mapping[str, Any]) -> dict[str, Any]:
    submitted = submit(app, world.maya, draft)
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["pending_approval_request_id"], world.carmen)
    assert approved.status_code == 200, approved.text
    return shown(app, world.maya, str(draft["id"]))


def in_force(app: FastAPI, actor: Actor, **params: str) -> list[tuple[Any, ...]]:
    listed = get(app, RATES, actor, params)
    assert listed.status_code == 200, listed.text
    return [
        (
            item["base_currency"],
            item["quote_currency"],
            item["effective_date"],
            item["period_key"],
            item["rate"],
            item["is_derived"],
            item["version_no"],
        )
        for item in listed.json()["items"]
    ]


def resolve(world: World, **kwargs: Any) -> Decimal:
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return fx.rate(session, **kwargs)


def actions(world: World, object_id: str) -> list[str]:
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [
            str(action)
            for action in session.scalars(
                select(audit_event.c.action)
                .where(audit_event.c.object_id == UUID(object_id))
                .order_by(audit_event.c.chain_seq)
            )
        ]


def test_manual_rates_effective_only_after_approval(app: FastAPI, world: World) -> None:
    created = rate_set(app, world.maya, code="AVM-RATES-CLOSING", rate_type="closing")
    assert (created["rate_type"], created["source"]) == ("closing", "MANUAL")
    draft = version(
        app,
        world.maya,
        created["id"],
        coverage=("2026-08-01", "2026-08-31"),
        rates=[closing("EUR", "1.105000", "FY2026-P08")],
    )
    assert (draft["version_no"], draft["status"], draft["rate_count"]) == (1, "DRAFT", 0)
    assert [
        (rate["base_currency"], rate["effective_date"], rate["period_key"], rate["rate"])
        for rate in draft["rates"]
    ] == [("EUR", "2026-08-31", "FY2026-P08", "1.105000000000")]
    query = {"rate_type": "closing", "base": "EUR", "quote": "USD", "period": "FY2026-P08"}

    # DRAFT: not returned, and resolution raises.
    assert in_force(app, world.maya, **query) == []
    with pytest.raises(Problem) as missing:
        resolve(world, rate_type="closing", base="EUR", quote="USD", period_key="FY2026-P08")
    assert missing.value.slug == "missing-fx-rate"

    submitted = submit(app, world.maya, draft)
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert (body["status"], body["rate_count"]) == ("SUBMITTED", 2)
    assert body["content_sha256"] is not None
    assert body["pending_approval_request_id"] is not None
    assert in_force(app, world.maya, **query) == []

    approved = approve(app, body["pending_approval_request_id"], world.carmen)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert in_force(app, world.maya, **query) == [
        ("EUR", "USD", "2026-08-31", "FY2026-P08", "1.105000000000", False, 1)
    ]
    assert resolve(
        world, rate_type="closing", base="EUR", quote="USD", period_key="FY2026-P08"
    ) == Decimal("1.105000")
    final = shown(app, world.maya, draft["id"])
    assert (
        final["status"],
        final["approval_request_id"],
        final["pending_approval_request_id"],
    ) == (
        "APPROVED",
        body["pending_approval_request_id"],
        None,
    )
    assert final["published_by"] == str(world.carmen.member.user_id)
    assert actions(world, draft["id"]) == [
        "fx_rate_set_version.create",
        "fx_rate_set_version.submit",
        "fx_rate_set_version.approve",
    ]


def test_zero_rate_rejected(app: FastAPI, world: World) -> None:
    created = rate_set(app, world.maya, code="AVM-RATES-CLOSING", rate_type="closing")
    draft = version(
        app,
        world.maya,
        created["id"],
        coverage=("2026-08-01", "2026-08-31"),
        rates=[closing("EUR", "1.105000", "FY2026-P08")],
    )
    path = f"{VERSIONS}/{draft['id']}"
    zero = patch(
        app, path, world.maya, {"rates": [closing("EUR", "0", "FY2026-P08")]}, if_match='"r1"'
    )
    assert (zero.status_code, slug(zero)) == (422, "validation-failed"), zero.text
    assert fields(zero) == [("rates.0.rate", "API-C-06")]
    number = {**closing("EUR", "1", "FY2026-P08"), "rate": 1.1}
    numeric = patch(app, path, world.maya, {"rates": [number]}, if_match='"r1"')
    assert fields(numeric) == [("rates.0.rate", "API-C-06")]
    unchanged = shown(app, world.maya, draft["id"])
    assert (unchanged["row_version"], unchanged["rates"][0]["rate"]) == (1, "1.105000000000")

    replaced = patch(
        app,
        path,
        world.maya,
        {"rates": [closing("EUR", "1.106000", "FY2026-P08")]},
        if_match='"r1"',
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.headers["ETag"] == '"r2"'
    assert [rate["rate"] for rate in replaced.json()["rates"]] == ["1.106000000000"]
    stale = patch(app, path, world.maya, {"coverage_to": "2026-09-30"}, if_match='"r1"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text


def test_highest_approved_version_wins(app: FastAPI, world: World) -> None:
    created = rate_set(app, world.maya, code="AVM-RATES-AVERAGE", rate_type="average")
    first = publish(
        app,
        world,
        version(
            app,
            world.maya,
            created["id"],
            coverage=("2026-08-01", "2026-09-30"),
            rates=[
                closing("EUR", "1.100000", "FY2026-P08"),
                closing("EUR", "1.110000", "FY2026-P09"),
            ],
        ),
    )
    second = publish(
        app,
        world,
        version(
            app,
            world.maya,
            created["id"],
            coverage=("2026-09-01", "2026-09-30"),
            rates=[closing("EUR", "1.115000", "FY2026-P09")],
        ),
    )
    assert [(first["version_no"], first["status"]), (second["version_no"], second["status"])] == [
        (1, "APPROVED"),
        (2, "APPROVED"),
    ]
    assert resolve(
        world, rate_type="average", base="EUR", quote="USD", period_key="FY2026-P09"
    ) == Decimal("1.115000")
    assert in_force(app, world.maya, rate_type="average", base="EUR", period="FY2026-P09") == [
        ("EUR", "USD", "2026-09-30", "FY2026-P09", "1.115000000000", False, 2)
    ]
    # Version 2 does not cover August, so version 1 still answers for it.
    assert in_force(app, world.maya, rate_type="average", base="EUR", period="FY2026-P08") == [
        ("EUR", "USD", "2026-08-31", "FY2026-P08", "1.100000000000", False, 1)
    ]


def test_inverse_derived_at_publication(app: FastAPI, world: World) -> None:
    created = rate_set(app, world.maya, code="AVM-RATES-CLOSING", rate_type="closing")
    draft = version(
        app,
        world.maya,
        created["id"],
        coverage=("2026-09-01", "2026-09-30"),
        rates=[closing("GBP", "1.280000", "FY2026-P09")],
    )
    assert [(rate["base_currency"], rate["is_derived"]) for rate in draft["rates"]] == [
        ("GBP", False)
    ]
    query = {"rate_type": "closing", "base": "USD", "quote": "GBP", "period": "FY2026-P09"}
    assert in_force(app, world.maya, **query) == []

    published = publish(app, world, draft)
    assert (published["status"], published["rate_count"]) == ("APPROVED", 2)
    assert [
        (rate["base_currency"], rate["quote_currency"], rate["rate"], rate["is_derived"])
        for rate in published["rates"]
    ] == [
        ("GBP", "USD", "1.280000000000", False),
        ("USD", "GBP", "0.781250000000", True),
    ]
    assert in_force(app, world.maya, **query) == [
        ("USD", "GBP", "2026-09-30", "FY2026-P09", "0.781250000000", True, 1)
    ]
    assert resolve(
        world, rate_type="closing", base="USD", quote="GBP", period_key="FY2026-P09"
    ) == Decimal("0.78125")


def test_missing_rate_problem(app: FastAPI, world: World) -> None:
    with pytest.raises(Problem) as excinfo:
        resolve(world, rate_type="closing", base="JPY", quote="USD", period_key="FY2026-P09")
    problem = excinfo.value
    assert (problem.slug, problem.status) == ("missing-fx-rate", 422)
    [error] = problem.errors
    assert (error.field, error.rule_id) == ("rate", "FX_RATE_MISSING")
    assert error.message == (
        "No closing rate from JPY to USD for 2026-09-30. "
        "Publish the rate, then rerun the affected contracts."
    )
    # A period key no calendar knows is a validation problem; a pair of one currency is 1.
    with pytest.raises(Problem) as unknown:
        resolve(world, rate_type="closing", base="JPY", quote="USD", period_key="FY2031-P01")
    assert [(item.field, item.rule_id) for item in unknown.value.errors] == [
        ("period_key", "T-REF-05")
    ]
    assert resolve(world, rate_type="spot", base="USD", quote="USD", on=date(2026, 9, 30)) == 1


def test_rate_stored_at_numeric_28_12(app: FastAPI, world: World) -> None:
    created = rate_set(app, world.maya, code="AVM-RATES-SPOT", rate_type="spot")
    spot = {
        "base_currency": "EUR",
        "quote_currency": "USD",
        "rate": "1.123456789012",
        "effective_date": "2026-09-15",
    }
    draft = version(
        app, world.maya, created["id"], coverage=("2026-09-01", "2026-09-30"), rates=[spot]
    )
    assert draft["rates"][0]["rate"] == "1.123456789012"
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(fx_rate.c.rate).where(fx_rate.c.fx_rate_set_version_id == UUID(draft["id"]))
        ).scalar_one()
    assert stored == Decimal("1.123456789012")
    assert str(stored) == "1.123456789012"
    assert shown(app, world.maya, draft["id"])["rates"][0]["rate"] == "1.123456789012"

    precise = post(
        app,
        f"{RATE_SETS}/{created['id']}/versions",
        world.maya,
        {
            "coverage_from": "2026-09-01",
            "coverage_to": "2026-09-30",
            "rates": [{**spot, "rate": "1.1234567890123"}],
        },
    )
    assert fields(precise) == [("rates.0.rate", "API-C-06")]


@pytest.mark.control("CTL-031")
def test_ctl_031_unapproved_rate_set_version_not_effective(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    tomas_member = colleague(world.tenant_id, "tomas")
    assign(tomas_member, "revenue_accountant")
    assign(tomas_member, "controller")
    tomas = enrolled(app, clock, tomas_member)
    created = rate_set(app, tomas, code="AVM-RATES-SPOT", rate_type="spot")
    spot = {
        "base_currency": "EUR",
        "quote_currency": "USD",
        "rate": "1.110000",
        "effective_date": "2026-09-15",
    }
    draft = version(app, tomas, created["id"], coverage=("2026-09-01", "2026-09-30"), rates=[spot])
    submitted = submit(app, tomas, draft)
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["pending_approval_request_id"]
    query = {"rate_type": "spot", "base": "EUR", "quote": "USD", "date": "2026-09-15"}

    # A SUBMITTED version is never used by rate resolution.
    assert in_force(app, tomas, **query) == []
    with pytest.raises(Problem) as missing:
        resolve(world, rate_type="spot", base="EUR", quote="USD", on=date(2026, 9, 15))
    assert missing.value.slug == "missing-fx-rate"

    # Its preparer, who holds config.approve, is refused.
    detail = get(app, f"{APPROVALS}/{request_id}", tomas)
    assert detail.status_code == 200, detail.text
    refused = post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        tomas,
        {"subject_content_sha256": detail.json()["subject"]["content_sha256"]},
    )
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert shown(app, tomas, draft["id"])["status"] == "SUBMITTED"
    assert in_force(app, tomas, **query) == []

    # Another user's approval makes it effective.
    approved = approve(app, request_id, world.carmen)
    assert approved.status_code == 200, approved.text
    assert in_force(app, tomas, **query) == [
        ("EUR", "USD", "2026-09-15", None, "1.110000000000", False, 1)
    ]


def test_version_findings_and_lifecycle(app: FastAPI, world: World, clock: FrozenClock) -> None:
    omar = holding(app, colleague(world.tenant_id, "omar"), "viewer")
    body = {"code": "AVM-RATES-CLOSING", "name": "Closing rates", "rate_type": "closing"}
    denied = post(app, RATE_SETS, omar, body)
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    created = rate_set(app, world.maya, code="AVM-RATES-CLOSING", rate_type="closing")
    taken = post(app, RATE_SETS, world.maya, {**body, "name": " ", "source": "treasury"})
    assert fields(taken) == [("code", "T-REF-10"), ("name", "T-REF-10"), ("source", "T-REF-10")]
    listed = get(app, RATE_SETS, omar, {"rate_type": "closing"})
    assert [item["code"] for item in listed.json()["items"]] == ["AVM-RATES-CLOSING"]
    unknown = post(
        app,
        f"{RATE_SETS}/{world.tenant_id}/versions",
        world.maya,
        {"coverage_from": "2026-09-01", "coverage_to": "2026-09-30"},
    )
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    findings = post(
        app,
        f"{RATE_SETS}/{created['id']}/versions",
        world.maya,
        {
            "coverage_from": "2026-09-01",
            "coverage_to": "2026-09-30",
            "rates": [
                closing("EUR", "1.1", "FY2026-P09", quote="EUR"),
                closing("ABC", "1.1", "FY2026-P08"),
                {"base_currency": "GBP", "quote_currency": "USD", "rate": "1.27"},
                closing("JPY", "0.0069", "FY2026-P09"),
                closing("JPY", "0.0070", "FY2026-P09"),
            ],
        },
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("rates.0.quote_currency", "T-REF-12"),
        ("rates.1.base_currency", "T-REF-12"),
        ("rates.1.effective_date", "T-REF-12"),
        ("rates.2.period_key", "T-REF-12"),
        ("rates.4.effective_date", "T-REF-12"),
    ]
    backwards = post(
        app,
        f"{RATE_SETS}/{created['id']}/versions",
        world.maya,
        {"coverage_from": "2026-09-30", "coverage_to": "2026-09-01"},
    )
    assert fields(backwards) == [("coverage_to", "T-REF-11")]

    empty = version(app, world.maya, created["id"], coverage=("2026-09-01", "2026-09-30"), rates=[])
    nothing = submit(app, world.maya, empty)
    assert fields(nothing) == [("rates", "T-REF-11")]
    filled = patch(
        app,
        f"{VERSIONS}/{empty['id']}",
        world.maya,
        {"rates": [closing("EUR", "1.120000", "FY2026-P09")]},
        if_match='"r1"',
    )
    assert filled.status_code == 200, filled.text
    narrowed = patch(
        app, f"{VERSIONS}/{empty['id']}", world.maya, {"coverage_to": "2026-09-29"}, if_match='"r2"'
    )
    assert fields(narrowed) == [("coverage_to", "T-REF-11")]

    submitted = submit(app, world.maya, filled.json())
    assert submitted.status_code == 200, submitted.text
    frozen = patch(
        app,
        f"{VERSIONS}/{empty['id']}",
        world.maya,
        {"coverage_from": "2026-09-02"},
        if_match=f'"r{submitted.json()["row_version"]}"',
    )
    assert (frozen.status_code, slug(frozen)) == (409, "configuration-frozen"), frozen.text
    resubmitted = submit(app, world.maya, submitted.json())
    assert (resubmitted.status_code, slug(resubmitted)) == (409, "invalid-transition")

    # The preparer withdraws: WITHDRAWN, then DRAFT again, without a pending request.
    withdrawn = post(
        app,
        f"{VERSIONS}/{empty['id']}/withdraw",
        world.maya,
        {"comment": "Wrong statement"},
        if_match=f'"r{submitted.json()["row_version"]}"',
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert (withdrawn.json()["status"], withdrawn.json()["pending_approval_request_id"]) == (
        "DRAFT",
        None,
    )
    again = post(
        app,
        f"{VERSIONS}/{empty['id']}/withdraw",
        world.maya,
        {},
        if_match=f'"r{withdrawn.json()["row_version"]}"',
    )
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text

    # Carmen rejects the resubmission: REJECTED, then DRAFT; the derived rows are derived again.
    resubmission = submit(app, world.maya, withdrawn.json())
    assert resubmission.status_code == 200, resubmission.text
    assert resubmission.json()["rate_count"] == 2
    rejected = post(
        app,
        f"{APPROVALS}/{resubmission.json()['pending_approval_request_id']}/reject",
        world.carmen,
        {"comment": "Use the ECB fixing"},
    )
    assert rejected.status_code == 200, rejected.text
    back = shown(app, world.maya, empty["id"])
    assert (back["status"], back["pending_approval_request_id"]) == ("DRAFT", None)
    assert actions(world, empty["id"]) == [
        "fx_rate_set_version.create",
        "fx_rate_set_version.update",
        "fx_rate_set_version.submit",
        "fx_rate_set_version.withdraw",
        "fx_rate_set_version.submit",
        "fx_rate_set_version.reject",
    ]
    versions = get(app, f"{RATE_SETS}/{created['id']}/versions", omar)
    assert [(item["version_no"], item["status"]) for item in versions.json()["items"]] == [
        (1, "DRAFT")
    ]


def pinned(world: World, known_at: datetime) -> list[tuple[Any, ...]]:
    """The GBP rates the contract input bundle carries at ``known_at`` (RCP-15)."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        found = bundles._fx_rates(session, ("GBP", "USD"), known_at)
    return [
        (r.version_key, r.rate_type, r.quote_currency, r.period_key, r.rate)
        for r in found
        if r.base_currency == "GBP"
    ]


def test_l6_5_contract_bundle_pins_the_approved_rate_versions(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """ENGINE_SPEC_B §12.2.1 "pinned APPROVED versions"; 04 T-REF-11 lifecycle DRAFT → SUBMITTED →
    APPROVED → SUPERSEDED. The engine bundle carries the rates of an approved version published by
    ``known_at``, and none of a draft or submitted one. It selected PUBLISHED and SUPERSEDED
    versions, so no rate ever reached the engine and the CTR-20 K-04 activation dry run answered
    FX_RATE_MISSING for the GBP→USD average of FY2026-P04 (L5-4-Q-10; lane L6-5)."""
    created = rate_set(app, world.maya, code="AVM-RATES-AVERAGE", rate_type="average")
    average = {"base_currency": "GBP", "quote_currency": "USD", "rate": "1.270000"}
    draft = version(
        app,
        world.maya,
        created["id"],
        coverage=("2026-04-01", "2026-04-30"),
        rates=[{**average, "period_key": "FY2026-P04"}],
    )
    assert pinned(world, clock.now()) == []
    submitted = submit(app, world.maya, draft)
    assert submitted.status_code == 200, submitted.text
    assert pinned(world, clock.now()) == []
    approved = approve(app, submitted.json()["pending_approval_request_id"], world.carmen)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert pinned(world, clock.now()) == [
        ("AVM-RATES-AVERAGE@v1", "average", "USD", "FY2026-P04", Decimal("1.270000000000"))
    ]
    assert pinned(world, clock.now() - timedelta(seconds=1)) == []  # published after known_at


def test_l7_6_contract_bundle_carries_the_rate_set_versions_in_force_at_known_at(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """D-87 L6-5-Q-23: the bundle carries only the versions in force at ``known_at`` (APPROVED or
    SUPERSEDED, published by ``known_at``, no superseding version published by then); for each
    (set, rate type, pair, date or period) the highest such version whose coverage contains the
    date answers. Before the ruling a v1 and v2 of one April average both reached stage 12, which
    found two rows for FY2026-P04 and answered FX_RATE_MISSING (S12-R-01)."""
    created = rate_set(app, world.maya, code="AVM-RATES-AVERAGE", rate_type="average")
    average = {"base_currency": "GBP", "quote_currency": "USD"}
    first = publish(
        app,
        world,
        version(
            app,
            world.maya,
            created["id"],
            coverage=("2026-04-01", "2026-05-31"),
            rates=[
                {**average, "rate": "1.270000", "period_key": "FY2026-P04"},
                {**average, "rate": "1.271000", "period_key": "FY2026-P05"},
            ],
        ),
    )
    first_known = clock.now()
    clock.advance(timedelta(minutes=5))
    second = publish(
        app,
        world,
        version(
            app,
            world.maya,
            created["id"],
            coverage=("2026-04-01", "2026-04-30"),
            rates=[{**average, "rate": "1.280000", "period_key": "FY2026-P04"}],
        ),
    )
    assert (first["version_no"], second["version_no"]) == (1, 2)
    v1_april = ("AVM-RATES-AVERAGE@v1", "average", "USD", "FY2026-P04", Decimal("1.270000000000"))
    v1_may = ("AVM-RATES-AVERAGE@v1", "average", "USD", "FY2026-P05", Decimal("1.271000000000"))
    v2_april = ("AVM-RATES-AVERAGE@v2", "average", "USD", "FY2026-P04", Decimal("1.280000000000"))
    # Version 2 covers April only: it answers for FY2026-P04, and version 1 still answers for May.
    assert pinned(world, clock.now()) == [v2_april, v1_may]
    # As of the first publication version 2 is not yet in force.
    assert pinned(world, first_known) == [v1_april, v1_may]
    assert pinned(world, first_known - timedelta(seconds=1)) == []
