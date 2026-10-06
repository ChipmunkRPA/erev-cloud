"""SSP resolution by effective date and named version (04 §15.3 API-R-26 ``GET /ssp/resolve``,
§16.4 API-S-SspResolution; ENGINE_SPEC §5.3 S05-R-02 to S05-R-08; POLICIES §1.5, §3.4 CHK-035;
PRD §2.6, WLD-X-23, WLD-X-25, J-02-AC-4, IMP-09; 03 REQ-SSP-006; CTL-011; BUILD_SPEC RFD-14).

Maya holds Revenue Accountant and SSP Analyst and prepares the book US-LIST (USD); Priya and Marcus
hold SSP Approver and are enrolled in MFA. ``2026-H1`` (effective 2026-01-01) and ``2026-H2``
(effective 2026-10-01, a 12% mid change, so two approval steps) are approved through API-R-26 and
API-R-09; approving ``2026-H2`` ends ``2026-H1`` on 2026-09-30. The frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import product, ssp_entry
from erev_api.enums import BookCode, RegistryCategory
from erev_api.main import create_app
from erev_api.registry.resolve import resolve
from fastapi import FastAPI
from sqlalchemy import and_, select
from support import upload_fixtures
from support.db import TestDatabase
from support.http import call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.reference import approve, assign, fields, get, holding, new_product, post, slug
from support.rows import publish_registry_version

SSP_BOOKS = "/api/v1/ssp-books"
VERSIONS = "/api/v1/ssp-book-versions"
RESOLVE = "/api/v1/ssp/resolve"
METHODOLOGY = "Observable standalone sales, Jan-Aug 2026"
PLATFORM = "AVM-PLAT-100"
IMPLEMENTATION = "AVM-IMPL-PLUS"
PUBLISHED_AT = datetime(2026, 9, 1, tzinfo=UTC)


def observable(product_code: str, low: str, mid: str, high: str) -> dict[str, Any]:
    return {
        "product_code": product_code,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "ranges": [{"low_value": low, "mid_value": mid, "high_value": high}],
    }


# PRD §2.6: AVM-IMPL-PLUS is cost plus margin with a range in both halves of 2026.
IMPLEMENTATION_ENTRY = {
    **observable(IMPLEMENTATION, "18000.00", "20000.00", "22000.00"),
    "method": "cost_plus_margin",
}
H1_ENTRIES = (observable(PLATFORM, "85000.00", "100000.00", "115000.00"), IMPLEMENTATION_ENTRY)
H2_ENTRIES = (observable(PLATFORM, "95200.00", "112000.00", "128800.00"), IMPLEMENTATION_ENTRY)


def legacy(product_code: str, list_price: str, discount: str) -> dict[str, Any]:
    return {
        "product_code": product_code,
        "currency": "USD",
        "method": "legacy_range",
        "distinctness": "distinct",
        "unit_list_price": list_price,
        "midpoint_discount_ratio": discount,
        "range_ratio": "0.15",
    }


@dataclass(frozen=True, slots=True)
class World:
    app: FastAPI
    maya: Actor
    priya: Actor
    marcus: Actor
    book_id: str
    h1: dict[str, Any]
    h2: dict[str, Any]

    @property
    def tenant_id(self) -> UUID:
        return self.maya.member.tenant_id


def new_version(
    app: FastAPI,
    actor: Actor,
    book_id: str,
    *,
    label: str,
    effective_from: str | None,
    entries: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    body = {
        "legacy_version_label": label,
        "effective_from_date": effective_from,
        "methodology_label": METHODOLOGY,
    }
    created = post(app, f"{SSP_BOOKS}/{book_id}/versions", actor, body)
    assert created.status_code == 201, created.text
    stored = post(
        app, f"{VERSIONS}/{created.json()['id']}/entries", actor, {"entries": list(entries)}
    )
    assert stored.status_code == 200, stored.text
    result: dict[str, Any] = created.json()
    return result


def submitted(app: FastAPI, actor: Actor, version_id: str) -> str:
    """Attach the SSP study and submit; returns the approval request id."""
    uploaded = call(
        app,
        "POST",
        "/api/v1/files",
        data={"purpose": "SSP_STUDY"},
        files={"file": ("study.pdf", upload_fixtures.PDF, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    attached = post(
        app,
        "/api/v1/attachments",
        actor,
        {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "ssp_book_version",
            "subject_id": version_id,
        },
    )
    assert attached.status_code == 201, attached.text
    current = get(app, f"{VERSIONS}/{version_id}", actor)
    sent = post(
        app,
        f"{VERSIONS}/{version_id}/submit",
        actor,
        {"comment": "Supported by standalone sales."},
        if_match=current.headers["ETag"],
    )
    assert sent.status_code == 200, sent.text
    return str(sent.json()["approval_request_id"])


def approved(
    app: FastAPI,
    maya: Actor,
    approvers: Iterable[Actor],
    book_id: str,
    *,
    label: str,
    effective_from: str | None,
    entries: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    version = new_version(
        app, maya, book_id, label=label, effective_from=effective_from, entries=entries
    )
    request_id = submitted(app, maya, version["id"])
    for approver in approvers:
        response = approve(app, request_id, approver)
        assert response.status_code == 200, response.text
        if response.json()["status"] == "APPROVED":
            break
    shown = get(app, f"{VERSIONS}/{version['id']}", maya)
    assert shown.json()["status"] == "APPROVED", shown.text
    result: dict[str, Any] = shown.json()
    return result


def new_book(app: FastAPI, maya: Actor, **body: Any) -> str:
    created = post(app, SSP_BOOKS, maya, body)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: list[Actor] = []
    for name in ("priya", "marcus"):
        someone = colleague(maya_member.tenant_id, name)
        assign(someone, "ssp_approver")
        approvers.append(enrolled(app, clock, someone))
    for code in (PLATFORM, IMPLEMENTATION):
        new_product(app, maya, code=code, name=code)
    book_id = new_book(app, maya, code="US-LIST", name="US list prices", currency="USD")
    h1 = approved(
        app,
        maya,
        approvers,
        book_id,
        label="2026-H1",
        effective_from="2026-01-01",
        entries=H1_ENTRIES,
    )
    h2 = approved(
        app,
        maya,
        approvers,
        book_id,
        label="2026-H2",
        effective_from="2026-10-01",
        entries=H2_ENTRIES,
    )
    return World(
        app=app,
        maya=maya,
        priya=approvers[0],
        marcus=approvers[1],
        book_id=book_id,
        h1=h1,
        h2=h2,
    )


def resolved(world: World, **params: str) -> dict[str, Any]:
    response = get(world.app, RESOLVE, world.maya, params)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def figures(body: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        body["ssp_book_version"]["legacy_version_label"],
        body["method"],
        body["low"],
        body["mid"],
        body["high"],
        body["in_range"],
        body["selected_ssp"],
    )


def entry_id(world: World, version_id: str, product_code: str) -> str:
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    joined = ssp_entry.join(
        product,
        and_(product.c.tenant_id == ssp_entry.c.tenant_id, product.c.id == ssp_entry.c.product_id),
    )
    with tenant_session(ctx, read_only=True) as session:
        found = session.execute(
            select(ssp_entry.c.id)
            .select_from(joined)
            .where(
                ssp_entry.c.ssp_book_version_id == UUID(version_id), product.c.code == product_code
            )
        ).scalar_one()
    return str(found)


def publish_policy(world: World, values: Mapping[str, Any]) -> str:
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        version_id = publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values=values,
            at=PUBLISHED_AT,
        )
    return str(version_id)


def test_version_effective_on_inception_date(world: World) -> None:
    body = resolved(
        world,
        product=PLATFORM,
        date="2026-09-01",
        currency="USD",
        quantity="1",
        stated_price="96000.00",
    )
    assert body["ssp_book_version"] == {
        "id": world.h1["id"],
        "book_code": "US-LIST",
        "version_no": 1,
        "legacy_version_label": "2026-H1",
    }
    assert figures(body) == ("2026-H1", "observable", "85000", "100000", "115000", True, "96000")
    assert body["stated_price"] == {"amount": "96000.00", "currency": "USD"}
    assert body["ssp_entry_id"] == entry_id(world, world.h1["id"], PLATFORM)
    # The later version ended the earlier one the day before it starts (PRD BR-SSP-02).
    h1 = get(world.app, f"{VERSIONS}/{world.h1['id']}", world.maya).json()
    assert (h1["effective_from_date"], h1["effective_to_date"]) == ("2026-01-01", "2026-09-30")
    last_day = resolved(
        world, product=PLATFORM, date="2026-09-30", currency="USD", stated_price="96000.00"
    )
    assert last_day["ssp_book_version"]["legacy_version_label"] == "2026-H1"


def test_later_date_uses_later_version(world: World) -> None:
    body = resolved(
        world,
        product=PLATFORM,
        date="2026-11-01",
        currency="USD",
        quantity="1",
        stated_price="90000.00",
    )
    assert body["ssp_book_version"] == {
        "id": world.h2["id"],
        "book_code": "US-LIST",
        "version_no": 2,
        "legacy_version_label": "2026-H2",
    }
    assert figures(body) == ("2026-H2", "observable", "95200", "112000", "128800", False, "95200")
    first_day = resolved(
        world, product=PLATFORM, date="2026-10-01", currency="USD", stated_price="90000.00"
    )
    assert first_day["ssp_book_version"]["legacy_version_label"] == "2026-H2"
    # Without a stated price the midpoint answers (S05-R-06).
    unpriced = resolved(world, product=PLATFORM, date="2026-11-01", currency="USD")
    assert (unpriced["selected_ssp"], unpriced["in_range"], unpriced["stated_price"]) == (
        "112000",
        None,
        None,
    )
    # Quantity extends the values (04 §16.4).
    doubled = resolved(
        world,
        product=PLATFORM,
        date="2026-11-01",
        currency="USD",
        quantity="2",
        stated_price="300000.00",
    )
    assert figures(doubled) == (
        "2026-H2",
        "observable",
        "190400",
        "224000",
        "257600",
        False,
        "257600",
    )


def test_above_range_nearest_bound(world: World) -> None:
    body = resolved(
        world, product=IMPLEMENTATION, date="2026-09-01", currency="USD", stated_price="24000.00"
    )
    assert figures(body) == (
        "2026-H1",
        "cost_plus_margin",
        "18000",
        "20000",
        "22000",
        False,
        "22000",
    )
    # PRD WLD-X-25: 26,000.00 under 2026-H2 selects the high bound too.
    preview = resolved(
        world, product=IMPLEMENTATION, date="2026-11-01", currency="USD", stated_price="26000.00"
    )
    assert (preview["ssp_book_version"]["legacy_version_label"], preview["selected_ssp"]) == (
        "2026-H2",
        "22000",
    )
    below = resolved(
        world, product=IMPLEMENTATION, date="2026-09-01", currency="USD", stated_price="0.00"
    )
    assert (below["in_range"], below["selected_ssp"]) == (False, "18000")


def test_named_version_under_preset(world: World) -> None:
    app, maya = world.app, world.maya
    for code in ("Hardware 1", "Software 1"):
        new_product(app, maya, code=code, name=code)
    legacy_book = new_book(
        app,
        maya,
        code="LEGACY-SKU-SSP",
        name="Legacy SKU SSP",
        currency="USD",
        resolution_mode="BY_LABEL",
    )
    named = approved(
        app,
        maya,
        (world.priya, world.marcus),
        legacy_book,
        label="2023-01-01",
        effective_from=None,
        entries=(legacy("Hardware 1", "120", "0.25"), legacy("Software 1", "200", "0.20")),
    )
    policy_id = publish_policy(world, {"ssp.version_basis": "NAMED_VERSION"})
    common = {"date": "2023-03-15", "currency": "USD", "book_version": "2023-01-01"}
    hardware = resolved(world, product="Hardware 1", quantity="5", stated_price="500.00", **common)
    assert hardware["ssp_book_version"] == {
        "id": named["id"],
        "book_code": "LEGACY-SKU-SSP",
        "version_no": 1,
        "legacy_version_label": "2023-01-01",
    }
    assert figures(hardware) == ("2023-01-01", "legacy_range", "382.5", "450", "517.5", True, "500")
    software = resolved(world, product="Software 1", quantity="2", stated_price="400.00", **common)
    assert figures(software) == ("2023-01-01", "legacy_range", "272", "320", "368", False, "368")
    large = resolved(world, product="Hardware 1", quantity="8", stated_price="600.00", **common)
    assert figures(large) == ("2023-01-01", "legacy_range", "612", "720", "828", False, "612")
    # CHK-035: prices on the bounds are kept.
    on_high = resolved(world, product="Hardware 1", quantity="5", stated_price="517.50", **common)
    on_low = resolved(world, product="Software 1", quantity="2", stated_price="272.00", **common)
    assert (on_high["selected_ssp"], on_low["selected_ssp"]) == ("517.5", "272")
    # The policy set answered the version basis; the named label chose the version.
    assert kernel_value(world, "ssp.version_basis") == ("NAMED_VERSION", policy_id)
    unknown_label = get(
        app,
        RESOLVE,
        maya,
        {
            **common,
            "product": "Hardware 1",
            "book_version": "2024-01-01",
            "stated_price": "500.00",
            "quantity": "5",
        },
    )
    assert (unknown_label.status_code, fields(unknown_label)) == (
        422,
        [("product", "SSP_KEY_NOT_FOUND")],
    )
    assert unknown_label.json()["errors"][0]["message"] == (
        "No approved SSP for Hardware 1 / - / 2024-01-01."
    )


def kernel_value(world: World, code: str) -> tuple[Any, str | None]:
    """``registry.resolve`` at the frozen instant: value and source version."""
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        found = resolve(
            session,
            code,
            book_code=BookCode.ASC606,
            known_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
        )
    return found.value, None if found.source_id is None else str(found.source_id)


def test_no_version_gives_ssp_key_not_found(world: World) -> None:
    refused = get(
        world.app,
        RESOLVE,
        world.maya,
        {"product": PLATFORM, "date": "2025-12-01", "currency": "USD", "stated_price": "96000.00"},
    )
    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "validation-failed",
        [("product", "SSP_KEY_NOT_FOUND")],
    )
    assert refused.json()["errors"][0]["message"] == (
        "No approved SSP for AVM-PLAT-100 / - / 2025-12-01."
    )
    other_stratification = get(
        world.app,
        RESOLVE,
        world.maya,
        {"product": PLATFORM, "date": "2026-09-01", "currency": "USD", "stratification": "EMEA"},
    )
    assert other_stratification.json()["errors"][0]["message"] == (
        "No approved SSP for AVM-PLAT-100 / EMEA / 2026-09-01."
    )


def test_policy_sources_reported(world: World) -> None:
    body = resolved(
        world, product=PLATFORM, date="2026-11-01", currency="USD", stated_price="90000.00"
    )
    assert body["policy_sources"] == {
        "inside_range_point": {
            "value": "CONTRACT_PRICE",
            "level": "FRAMEWORK_DEFAULT",
            "source_id": None,
        },
        "outside_range_point": {
            "value": "NEAREST_BOUND",
            "level": "FRAMEWORK_DEFAULT",
            "source_id": None,
        },
    }
    policy_id = publish_policy(world, {"ssp.outside_range_point": "MIDPOINT"})
    midpoint = resolved(
        world, product=PLATFORM, date="2026-11-01", currency="USD", stated_price="90000.00"
    )
    assert (midpoint["selected_ssp"], midpoint["policy_sources"]["outside_range_point"]) == (
        "112000",
        {"value": "MIDPOINT", "level": "TENANT", "source_id": policy_id},
    )


def test_resolve_refusals(world: World) -> None:
    cases = (
        (
            {"product": "AVM-NONE", "date": "2026-09-01", "currency": "USD"},
            [("product", "T-REF-20")],
        ),
        (
            {"product": PLATFORM, "date": "2026-09-01", "currency": "USD", "quantity": "0"},
            [("quantity", "S03-R-04")],
        ),
        (
            {"product": PLATFORM, "date": "2026-09-01", "currency": "USD", "entity": "AVM-XX"},
            [("entity", "T-REF-01")],
        ),
        (
            {"product": PLATFORM, "date": "2026-09-01", "currency": "XXX"},
            [("currency", "API-C-06")],
        ),
        (
            {
                "product": PLATFORM,
                "date": "2026-09-01",
                "currency": "USD",
                "stated_price": "96000.005",
            },
            [("stated_price", "API-C-06")],
        ),
    )
    for params, expected in cases:
        refused = get(world.app, RESOLVE, world.maya, params)
        assert (refused.status_code, fields(refused)) == (422, expected), params
    malformed = get(
        world.app,
        RESOLVE,
        world.maya,
        {"product": PLATFORM, "date": "2026-09-01", "currency": "USD", "quantity": "1e3"},
    )
    assert malformed.status_code == 422, malformed.text


@pytest.mark.control("CTL-011")
def test_ctl_011_unapproved_version_never_resolved(world: World) -> None:
    app, maya = world.app, world.maya
    h3 = new_version(
        app,
        maya,
        world.book_id,
        label="2026-H3",
        effective_from="2026-12-01",
        entries=(observable(PLATFORM, "100000.00", "120000.00", "140000.00"), IMPLEMENTATION_ENTRY),
    )
    submitted(app, maya, h3["id"])
    assert get(app, f"{VERSIONS}/{h3['id']}", maya).json()["status"] == "SUBMITTED"
    body = resolved(
        world, product=PLATFORM, date="2026-12-15", currency="USD", stated_price="96000.00"
    )
    assert figures(body) == ("2026-H2", "observable", "95200", "112000", "128800", True, "96000")
    named = get(
        app,
        RESOLVE,
        maya,
        {"product": PLATFORM, "date": "2026-12-15", "currency": "USD", "book_version": "2026-H3"},
    )
    assert (named.status_code, fields(named)) == (422, [("product", "SSP_KEY_NOT_FOUND")])
