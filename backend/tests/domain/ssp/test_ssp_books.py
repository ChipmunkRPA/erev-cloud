"""SSP books, versions and entries (04 T-REF-28 to T-REF-31, E-47, E-49, API-R-26, §16.4, table
15.4-A; 03 REQ-SSP-002, REQ-SSP-003, REQ-SSP-007; ENGINE_SPEC §1.4 S01-R-05; PRD §2.6; SCREENS
§11.4; BUILD_SPEC RFD-12).

Maya holds Revenue Accountant (``masterdata.maintain``, ``config.author``) and SSP Analyst
(``ssp.create``; docs/02-PRD.md §5.6 PRS-01) and prepares the Avenmoor SSP books of PRD §2.6; Omar
holds Viewer. The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, ssp_entry, ssp_range
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, update
from support import upload_fixtures
from support.db import TestDatabase
from support.factories import (
    TPL_SUB_DAILY,
    published_template,
    set_default_template,
)
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.reference import (
    PRODUCTS,
    assign,
    calendar,
    delete,
    entity,
    fields,
    get,
    gl_account,
    holding,
    new_product,
    patch,
    post,
    slug,
)

SSP_BOOKS = "/api/v1/ssp-books"
VERSIONS = "/api/v1/ssp-book-versions"
METHODOLOGY = "Observable standalone sales, 2025"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def maya(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    someone = member(keyring, clock)
    assign(someone, "revenue_accountant")
    return holding(app, someone, "ssp_analyst")


def new_book(app: FastAPI, actor: Actor, *, code: str, **extra: Any) -> dict[str, Any]:
    """``POST /ssp-books``; returns the 201 body."""
    created = post(app, SSP_BOOKS, actor, {"code": code, "name": f"{code} prices", **extra})
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


def new_version(app: FastAPI, actor: Actor, book_id: str, **extra: Any) -> dict[str, Any]:
    """``POST /ssp-books/{id}/versions``; returns the 201 body."""
    body = {"methodology_label": METHODOLOGY, **extra}
    created = post(app, f"{SSP_BOOKS}/{book_id}/versions", actor, body)
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


def draft(app: FastAPI, actor: Actor, *product_codes: str) -> dict[str, Any]:
    """The products, book ``US-LIST`` and its DRAFT version 1."""
    for code in product_codes:
        new_product(app, actor, code=code, name=code)
    book = new_book(app, actor, code="US-LIST")
    return new_version(app, actor, book["id"], legacy_version_label="2026-H1")


def entries_path(version_id: str) -> str:
    return f"{VERSIONS}/{version_id}/entries"


def put_entries(
    app: FastAPI, actor: Actor, version_id: str, entries: Iterable[Mapping[str, Any]]
) -> HttpResponse:
    return post(app, entries_path(version_id), actor, {"entries": [dict(item) for item in entries]})


def entry(product_code: str, **extra: Any) -> dict[str, Any]:
    """An observable USD entry of a distinct good; ``extra`` replaces or adds members."""
    return {
        "product_code": product_code,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        **extra,
    }


def listed(app: FastAPI, actor: Actor, version_id: str, **params: Any) -> list[dict[str, Any]]:
    response = get(app, entries_path(version_id), actor, {"limit": 200, **params})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def summary(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        item["product_code"],
        item["method"],
        item["currency"],
        item["distinctness"],
        [
            (band["band_dimension"], band["point_value"], band["low_value"], band["mid_value"])
            + (band["high_value"],)
            for band in item["ranges"]
        ],
    )


def facts(actor: Actor) -> dict[str, list[int]]:
    """The id counts of the AUD-FACT summaries of entries and bands, per action."""
    ctx = DbContext(tenant_id=actor.member.tenant_id, user_id=None, entity_scope="*")
    statement = (
        select(audit_event.c.action, audit_event.c.detail)
        .where(audit_event.c.object_type.in_(["ssp_entry", "ssp_range"]))
        .order_by(audit_event.c.chain_seq)
    )
    found: dict[str, list[int]] = {}
    with tenant_session(ctx, read_only=True) as session:
        for action, detail in session.execute(statement).tuples():
            found.setdefault(str(action), []).append(len(detail["ids"]))
    return found


def test_book_version_and_entries(app: FastAPI, maya: Actor) -> None:
    entity(app, maya, code="AVM-US", calendar_id=calendar(app, maya))
    for code in ("AVM-PLAT-100", "AVM-PLAT-ENT", "AVM-IMPL-STD"):
        new_product(app, maya, code=code, name=code)
    created = post(
        app,
        SSP_BOOKS,
        maya,
        {
            "code": "US-LIST",
            "name": "US list prices",
            "entity_code": "AVM-US",
            "currency": "USD",
            "resolution_mode": "EFFECTIVE_DATE",
        },
    )
    assert created.status_code == 201, created.text
    book = created.json()
    assert (created.headers["Location"], created.headers["ETag"]) == (
        f"{SSP_BOOKS}/{book['id']}",
        '"r1"',
    )
    assert {name: value for name, value in book.items() if name not in ("id", "created_at")} == {
        "code": "US-LIST",
        "name": "US list prices",
        "description": None,
        "entity_code": "AVM-US",
        "currency": "USD",
        "channel": None,
        "segment": None,
        "resolution_mode": "EFFECTIVE_DATE",
        "current_version": None,
        "draft_version_id": None,
        "row_version": 1,
        "updated_at": book["updated_at"],
    }

    started = post(
        app,
        f"{SSP_BOOKS}/{book['id']}/versions",
        maya,
        {
            "legacy_version_label": "2026-H1",
            "effective_from_date": "2026-01-01",
            "methodology_label": METHODOLOGY,
        },
    )
    assert started.status_code == 201, started.text
    version = started.json()
    assert (started.headers["Location"], started.headers["ETag"]) == (
        f"{VERSIONS}/{version['id']}",
        '"r1"',
    )
    assert {
        name: version[name]
        for name in (
            "ssp_book_id",
            "version_no",
            "status",
            "legacy_version_label",
            "effective_from_date",
            "effective_to_date",
            "methodology_label",
            "is_methodology_change",
            "entry_count",
            "diff_summary",
            "study_attachment_ids",
            "approval_request_id",
            "content_sha256",
            "published_at",
        )
    } == {
        "ssp_book_id": book["id"],
        "version_no": 1,
        "status": "DRAFT",
        "legacy_version_label": "2026-H1",
        "effective_from_date": "2026-01-01",
        "effective_to_date": None,
        "methodology_label": METHODOLOGY,
        "is_methodology_change": False,
        "entry_count": 0,
        "diff_summary": None,
        "study_attachment_ids": [],
        "approval_request_id": None,
        "content_sha256": None,
        "published_at": None,
    }
    assert (version["created_by"]["id"], version["created_by"]["kind"]) == (
        str(maya.member.user_id),
        "USER",
    )

    saved = put_entries(
        app,
        maya,
        version["id"],
        [
            entry(
                "AVM-PLAT-100",
                distinctness="series",
                ranges=[
                    {"low_value": "85000.00", "mid_value": "100000.00", "high_value": "115000.00"}
                ],
            ),
            entry("AVM-PLAT-ENT", distinctness="series", ranges=[{"point_value": "132000.00"}]),
            entry("AVM-IMPL-STD", method="cost_plus_margin", ranges=[{"point_value": "18000.00"}]),
        ],
    )
    assert saved.status_code == 200, saved.text
    stored = saved.json()["entries"]
    assert [summary(item) for item in stored] == [
        (
            "AVM-PLAT-100",
            "observable",
            "USD",
            "series",
            [("NONE", None, "85000", "100000", "115000")],
        ),
        ("AVM-PLAT-ENT", "observable", "USD", "series", [("NONE", "132000", None, None, None)]),
        (
            "AVM-IMPL-STD",
            "cost_plus_margin",
            "USD",
            "distinct",
            [("NONE", "18000", None, None, None)],
        ),
    ]
    assert {name: value for name, value in stored[0].items() if name != "id"} == {
        "product_code": "AVM-PLAT-100",
        "stratification": "",
        "region": None,
        "channel": None,
        "segment": None,
        "deal_size_band": None,
        "term_band": None,
        "currency": "USD",
        "method": "observable",
        "value_basis": "AMOUNT",
        "quantity_unit": None,
        "unit_list_price": None,
        "midpoint_discount_ratio": None,
        "range_ratio": None,
        "cost_basis": None,
        "margin_ratio": None,
        "observable_point": None,
        "revenue_account_code": None,
        "distinctness": "series",
        "ranges": [
            {
                "band_dimension": "NONE",
                "band_from": None,
                "band_to": None,
                "point_value": None,
                "low_value": "85000",
                "mid_value": "100000",
                "high_value": "115000",
            }
        ],
    }
    items = listed(app, maya, version["id"])
    assert [item["product_code"] for item in items] == [
        "AVM-IMPL-STD",
        "AVM-PLAT-100",
        "AVM-PLAT-ENT",
    ]
    assert sorted(items, key=lambda item: str(item["id"])) == sorted(
        stored, key=lambda item: str(item["id"])
    )
    assert [
        item["product_code"] for item in listed(app, maya, version["id"], product="AVM-PLAT-ENT")
    ] == ["AVM-PLAT-ENT"]
    shown = get(app, f"{VERSIONS}/{version['id']}", maya)
    assert (shown.json()["entry_count"], shown.headers["ETag"]) == (3, '"r2"')
    book_shown = get(app, f"{SSP_BOOKS}/{book['id']}", maya).json()
    assert (book_shown["draft_version_id"], book_shown["current_version"]) == (version["id"], None)
    assert facts(maya) == {"ssp_entry.create": [3], "ssp_range.create": [3]}


def test_formula_method_rejected(app: FastAPI, maya: Actor) -> None:
    version = draft(app, maya, "AVM-PLAT-100")
    refused = put_entries(
        app,
        maya,
        version["id"],
        [entry("AVM-PLAT-100", method="formula", ranges=[{"point_value": "100"}])],
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("entries[0].method", "E-47")]
    assert refused.json()["errors"][0]["message"] == (
        "Formula SSPs are not available yet. Choose another method."
    )
    assert listed(app, maya, version["id"]) == []


def test_legacy_range_band_derived_by_server(app: FastAPI, maya: Actor) -> None:
    new_product(app, maya, code="Hardware 1", name="Hardware 1")
    book = new_book(app, maya, code="LEGACY-SKU-SSP", resolution_mode="BY_LABEL")
    version = new_version(app, maya, book["id"], legacy_version_label="2023-01-01")
    legacy = entry(
        "Hardware 1",
        method="legacy_range",
        unit_list_price="120",
        midpoint_discount_ratio="0.25",
        range_ratio="0.15",
    )
    saved = put_entries(app, maya, version["id"], [legacy])
    assert saved.status_code == 200, saved.text
    (stored,) = saved.json()["entries"]
    assert (
        stored["unit_list_price"],
        stored["midpoint_discount_ratio"],
        stored["range_ratio"],
    ) == (
        "120",
        "0.25",
        "0.15",
    )
    assert stored["ranges"] == [
        {
            "band_dimension": "NONE",
            "band_from": None,
            "band_to": None,
            "point_value": None,
            "low_value": "76.5",
            "mid_value": "90",
            "high_value": "103.5",
        }
    ]
    ctx = DbContext(tenant_id=maya.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        bands = session.execute(
            select(ssp_range.c.low_value, ssp_range.c.mid_value, ssp_range.c.high_value)
        ).all()
    assert [tuple(row) for row in bands] == [(Decimal("76.5"), Decimal("90"), Decimal("103.5"))]

    client_band = {
        **legacy,
        "ranges": [{"low_value": "70", "mid_value": "90", "high_value": "110"}],
    }
    refused = put_entries(app, maya, version["id"], [client_band])
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("entries[0].ranges", "T-REF-31")]
    assert refused.json()["errors"][0]["message"] == (
        "The band of a legacy range entry is derived from its list price, discount and range. "
        "Leave out ranges."
    )
    assert listed(app, maya, version["id"])[0]["ranges"] == stored["ranges"]

    missing = put_entries(
        app, maya, version["id"], [entry("Hardware 1", method="legacy_range", range_ratio="0.15")]
    )
    assert fields(missing) == [
        ("entries[0].unit_list_price", "T-REF-30"),
        ("entries[0].midpoint_discount_ratio", "T-REF-30"),
    ], missing.text


def test_percent_of_list_basis(app: FastAPI, maya: Actor) -> None:
    version = draft(app, maya, "AVM-ENG-BUILD")
    saved = put_entries(
        app,
        maya,
        version["id"],
        [
            entry(
                "AVM-ENG-BUILD",
                method="cost_plus_margin",
                value_basis="PERCENT_OF_LIST",
                ranges=[{"point_value": "1"}],
            )
        ],
    )
    assert saved.status_code == 200, saved.text
    (stored,) = saved.json()["entries"]
    assert (stored["method"], stored["value_basis"], stored["ranges"][0]["point_value"]) == (
        "cost_plus_margin",
        "PERCENT_OF_LIST",
        "1",
    )


def test_dimension_keys_and_duplicate_key(app: FastAPI, maya: Actor) -> None:
    version = draft(app, maya, "AVM-PLAT-ENT")
    keys = ({"region": "EU"}, {"channel": "direct"}, {"deal_size_band": "L"}, {"term_band": "36M"})
    saved = put_entries(
        app,
        maya,
        version["id"],
        [entry("AVM-PLAT-ENT", ranges=[{"point_value": "132000"}], **key) for key in keys],
    )
    assert saved.status_code == 200, saved.text
    stored = saved.json()["entries"]
    assert len({item["id"] for item in stored}) == 4
    assert {
        (item["region"], item["channel"], item["deal_size_band"], item["term_band"])
        for item in listed(app, maya, version["id"])
    } == {
        ("EU", None, None, None),
        (None, "direct", None, None),
        (None, None, "L", None),
        (None, None, None, "36M"),
    }

    repeated = put_entries(
        app,
        maya,
        version["id"],
        [
            entry("AVM-PLAT-ENT", region="EU", ranges=[{"point_value": "125000"}]),
            entry("AVM-PLAT-ENT", region=" EU ", ranges=[{"point_value": "126000"}]),
        ],
    )
    assert (repeated.status_code, slug(repeated)) == (422, "validation-failed"), repeated.text
    assert fields(repeated) == [("entries[1]", "SSP_DUPLICATE_KEY")]
    assert repeated.json()["errors"][0]["message"] == (
        "Entry 1 already uses this product, stratification, dimension keys and currency."
    )

    # An entry with a stored key replaces that entry.
    replaced = put_entries(
        app,
        maya,
        version["id"],
        [entry("AVM-PLAT-ENT", region="EU", ranges=[{"point_value": "125000"}])],
    )
    assert replaced.status_code == 200, replaced.text
    (europe,) = replaced.json()["entries"]
    assert (europe["id"], europe["ranges"][0]["point_value"]) == (stored[0]["id"], "125000")
    assert get(app, f"{VERSIONS}/{version['id']}", maya).json()["entry_count"] == 4


def test_midpoint_discount_bounds(app: FastAPI, maya: Actor) -> None:
    version = draft(app, maya, "Hardware 1")
    for ratio in ("1", "-0.1"):
        refused = put_entries(
            app,
            maya,
            version["id"],
            [
                entry(
                    "Hardware 1",
                    method="legacy_range",
                    unit_list_price="120",
                    midpoint_discount_ratio=ratio,
                    range_ratio="0.15",
                )
            ],
        )
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("entries[0].midpoint_discount_ratio", "T-REF-30")]
        assert refused.json()["errors"][0]["message"] == (
            "Enter a midpoint discount of at least 0% and below 100%."
        )
    assert listed(app, maya, version["id"]) == []


def test_diff_against_prior_version(app: FastAPI, maya: Actor) -> None:
    for code in ("AVM-PLAT-100", "AVM-PLAT-ENT"):
        new_product(app, maya, code=code, name=code)
    book = new_book(app, maya, code="US-LIST", currency="USD")
    first = new_version(
        app, maya, book["id"], legacy_version_label="2026-H1", effective_from_date="2026-01-01"
    )
    platform = {"low_value": "85000.00", "mid_value": "100000.00", "high_value": "115000.00"}
    loaded = put_entries(
        app,
        maya,
        first["id"],
        [
            entry("AVM-PLAT-100", ranges=[platform]),
            entry("AVM-PLAT-ENT", ranges=[{"point_value": "132000.00"}]),
        ],
    )
    assert loaded.status_code == 200, loaded.text

    second = new_version(
        app,
        maya,
        book["id"],
        copy_from_version_id=first["id"],
        legacy_version_label="2026-H2",
        effective_from_date="2026-10-01",
        methodology_label="Observable standalone sales, Jan-Aug 2026",
    )
    assert (second["version_no"], second["entry_count"]) == (2, 2)

    def without_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{name: value for name, value in item.items() if name != "id"} for item in items]

    assert without_ids(listed(app, maya, second["id"])) == without_ids(
        listed(app, maya, first["id"])
    )
    edited = put_entries(
        app,
        maya,
        second["id"],
        [entry("AVM-PLAT-100", ranges=[{**platform, "mid_value": "112000.00"}])],
    )
    assert edited.status_code == 200, edited.text

    compared = get(app, f"{VERSIONS}/{second['id']}/diff", maya, {"against": first["id"]})
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert (body["added"], body["removed"], len(body["changed"])) == ([], [], 1)
    (change,) = body["changed"]
    assert change["key"] == {
        "product_code": "AVM-PLAT-100",
        "stratification": "",
        "region": None,
        "channel": None,
        "segment": None,
        "deal_size_band": None,
        "term_band": None,
        "currency": "USD",
    }
    before, after = change["before"]["ranges"][0], change["after"]["ranges"][0]
    assert (before["mid_value"], after["mid_value"]) == ("100000", "112000")
    assert (before["low_value"], after["low_value"], before["high_value"], after["high_value"]) == (
        "85000",
        "85000",
        "115000",
        "115000",
    )
    assert change["mid_change_ratio"] == "0.12"
    reverse = get(app, f"{VERSIONS}/{first['id']}/diff", maya, {"against": second["id"]}).json()
    assert reverse["changed"][0]["mid_change_ratio"] == "-0.107142857142857143"

    other = new_version(app, maya, new_book(app, maya, code="DE-LIST")["id"])
    refused = get(app, f"{VERSIONS}/{second['id']}/diff", maya, {"against": other["id"]})
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("against", "T-REF-29")]
    assert refused.json()["errors"][0]["message"] == "Choose a version of the same SSP book."
    unknown = get(app, f"{VERSIONS}/{book['id']}/diff", maya, {"against": first["id"]})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text


def test_observable_point_stored(app: FastAPI, maya: Actor) -> None:
    version = draft(app, maya, "AVM-PLAT-100")
    band = {"low_value": "136.00", "mid_value": "160.00", "high_value": "184.00"}
    saved = put_entries(
        app, maya, version["id"], [entry("AVM-PLAT-100", observable_point="150", ranges=[band])]
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["entries"][0]["observable_point"] == "150"
    assert listed(app, maya, version["id"])[0]["observable_point"] == "150"
    negative = put_entries(
        app, maya, version["id"], [entry("AVM-PLAT-100", observable_point="-1", ranges=[band])]
    )
    assert fields(negative) == [("entries[0].observable_point", "T-REF-30")], negative.text


def test_book_findings_and_permissions(app: FastAPI, maya: Actor) -> None:
    omar = holding(app, colleague(maya.member.tenant_id, "omar"), "viewer")
    book = new_book(app, maya, code="US-LIST")
    denied = post(app, SSP_BOOKS, omar, {"code": "UK-LIST", "name": "UK list prices"})
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    denied_version = post(
        app, f"{SSP_BOOKS}/{book['id']}/versions", omar, {"methodology_label": METHODOLOGY}
    )
    assert denied_version.status_code == 403, denied_version.text
    assert [item["code"] for item in get(app, SSP_BOOKS, omar).json()["items"]] == ["US-LIST"]

    findings = post(
        app,
        SSP_BOOKS,
        maya,
        {"code": "US-LIST", "name": "  ", "entity_code": "AVM-XX", "currency": "ZZZ"},
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("code", "T-REF-28"),
        ("name", "T-REF-28"),
        ("entity_code", "T-REF-28"),
        ("currency", "T-REF-28"),
    ]
    assert findings.json()["errors"][0]["message"] == "SSP book code US-LIST is already used."
    assert fields(post(app, SSP_BOOKS, maya, {"code": "!bad", "name": "Bad"})) == [
        ("code", "T-REF-28")
    ]

    path = f"{SSP_BOOKS}/{book['id']}"
    unconditional = patch(app, path, maya, {"name": "US list prices 2026"}, if_match=None)
    assert (unconditional.status_code, slug(unconditional)) == (428, "precondition-required")
    renamed = patch(
        app, path, maya, {"name": "US list prices 2026", "channel": " direct "}, if_match='"r1"'
    )
    assert renamed.status_code == 200, renamed.text
    assert (renamed.headers["ETag"], renamed.json()["channel"]) == ('"r2"', "direct")
    assert fields(patch(app, path, maya, {"name": None}, if_match='"r2"')) == [("name", "T-REF-28")]
    missing = get(app, f"{SSP_BOOKS}/{maya.member.tenant_id}", maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text
    new_book(app, maya, code="UK-LIST")
    searched = get(app, SSP_BOOKS, maya, {"q": "us-"})
    assert [item["code"] for item in searched.json()["items"]] == ["US-LIST"]


def test_version_findings_and_several_drafts(app: FastAPI, maya: Actor) -> None:
    book = new_book(app, maya, code="US-LIST")
    first = new_version(app, maya, book["id"], legacy_version_label="2026-H1")
    foreign = new_version(app, maya, new_book(app, maya, code="UK-LIST")["id"])
    findings = post(
        app,
        f"{SSP_BOOKS}/{book['id']}/versions",
        maya,
        {
            "copy_from_version_id": foreign["id"],
            "legacy_version_label": " 2026-H1 ",
            "effective_from_date": "2026-10-01",
            "effective_to_date": "2026-09-30",
            "methodology_label": " ",
        },
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("copy_from_version_id", "T-REF-29"),
        ("legacy_version_label", "T-REF-29"),
        ("effective_to_date", "T-REF-29"),
        ("methodology_label", "T-REF-29"),
    ]
    unknown = post(app, f"{SSP_BOOKS}/{first['id']}/versions", maya, {"methodology_label": "M"})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    path = f"{VERSIONS}/{first['id']}"
    changed = patch(
        app,
        path,
        maya,
        {"effective_from_date": "2026-01-01", "is_methodology_change": True},
        if_match='"r1"',
    )
    assert changed.status_code == 200, changed.text
    assert (changed.headers["ETag"], changed.json()["is_methodology_change"]) == ('"r2"', True)
    blank = patch(
        app,
        path,
        maya,
        {"methodology_label": None, "effective_to_date": "2025-12-31"},
        if_match='"r2"',
    )
    assert fields(blank) == [
        ("methodology_label", "T-REF-29"),
        ("effective_to_date", "T-REF-29"),
    ], blank.text

    # [J] Several versions of a book may be DRAFT at once (L2-1-Q-25).
    second = new_version(app, maya, book["id"], legacy_version_label="2026-H2")
    assert (second["version_no"], second["entry_count"]) == (2, 0)
    assert get(app, f"{SSP_BOOKS}/{book['id']}", maya).json()["draft_version_id"] == second["id"]
    versions = get(app, f"{SSP_BOOKS}/{book['id']}/versions", maya, {"status": "DRAFT"})
    assert [item["version_no"] for item in versions.json()["items"]] == [2, 1], versions.text


def test_entry_findings_upsert_and_delete(app: FastAPI, maya: Actor) -> None:
    version = draft(app, maya, "AVM-SUP-12")
    findings = put_entries(
        app,
        maya,
        version["id"],
        [
            entry("AVM-NOPE", currency="EUR", ranges=[{"point_value": "1"}]),
            entry("AVM-SUP-12", revenue_account_code="9999", ranges=[]),
            entry(
                "AVM-SUP-12",
                stratification="BANDS",
                ranges=[
                    {"band_from": "5"},
                    {"band_dimension": "QUANTITY", "point_value": "1"},
                    {
                        "band_dimension": "QUANTITY",
                        "band_from": "10",
                        "band_to": "5",
                        "low_value": "3",
                        "mid_value": "2",
                    },
                    {"band_dimension": "QUANTITY", "band_from": "10", "point_value": "1"},
                ],
            ),
        ],
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("entries[0].product_code", "T-REF-30"),
        ("entries[1].revenue_account_code", "T-REF-30"),
        ("entries[1].ranges", "T-REF-31"),
        ("entries[2].ranges[0].band_from", "T-REF-31"),
        ("entries[2].ranges[0].point_value", "T-REF-31"),
        ("entries[2].ranges[1].band_from", "T-REF-31"),
        ("entries[2].ranges[2].band_to", "T-REF-31"),
        ("entries[2].ranges[2].mid_value", "T-REF-31"),
        ("entries[2].ranges[3].band_from", "T-REF-31"),
    ]
    # A book scoped to a currency holds values in that currency only.
    scoped = new_book(app, maya, code="EUR-LIST", currency="EUR")
    scoped_version = new_version(app, maya, scoped["id"])
    usd = put_entries(
        app, maya, scoped_version["id"], [entry("AVM-SUP-12", ranges=[{"point_value": "1"}])]
    )
    assert fields(usd) == [("entries[0].currency", "T-REF-30")], usd.text
    assert usd.json()["errors"][0]["message"] == "This SSP book holds values in EUR."

    gl_account(app, maya, code="4010", name="Revenue - services and subscriptions")
    body = entry(
        "AVM-SUP-12",
        revenue_account_code="4010",
        ranges=[
            {"band_dimension": "TERM_MONTHS", "band_from": "36", "mid_value": "19500"},
            {"low_value": "19000", "mid_value": "20000", "high_value": "21000"},
        ],
    )
    saved = put_entries(app, maya, version["id"], [body])
    assert saved.status_code == 200, saved.text
    (stored,) = saved.json()["entries"]
    assert stored["revenue_account_code"] == "4010"
    assert [
        (band["band_dimension"], band["band_from"], band["mid_value"]) for band in stored["ranges"]
    ] == [
        ("NONE", None, "20000"),
        ("TERM_MONTHS", "36", "19500"),
    ]
    unchanged = put_entries(app, maya, version["id"], [body])
    assert unchanged.json()["entries"] == [stored], unchanged.text
    assert facts(maya) == {"ssp_entry.create": [1], "ssp_range.create": [2]}
    replaced = put_entries(
        app, maya, version["id"], [{**body, "ranges": [{"point_value": "20000"}]}]
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["entries"][0]["id"] == stored["id"]
    assert facts(maya) == {
        "ssp_entry.create": [1],
        "ssp_range.create": [2, 1],
        "ssp_entry.update": [1],
        "ssp_range.delete": [2],
    }

    removed = delete(app, f"{entries_path(version['id'])}/{stored['id']}", maya)
    assert removed.status_code == 204, removed.text
    assert listed(app, maya, version["id"]) == []
    assert get(app, f"{VERSIONS}/{version['id']}", maya).json()["entry_count"] == 0
    again = delete(app, f"{entries_path(version['id'])}/{stored['id']}", maya)
    assert (again.status_code, slug(again)) == (404, "not-found"), again.text


def test_study_attachment_ids(app: FastAPI, maya: Actor) -> None:
    version = draft(app, maya)
    ids: dict[str, str] = {}
    for purpose in ("SSP_STUDY", "ATTACHMENT"):
        uploaded = call(
            app,
            "POST",
            "/api/v1/files",
            data={"purpose": purpose},
            files={"file": (f"{purpose.lower()}.pdf", upload_fixtures.PDF, "application/pdf")},
            headers=cookie_headers(maya.token, maya.csrf_token),
        )
        assert uploaded.status_code == 201, uploaded.text
        attached = post(
            app,
            "/api/v1/attachments",
            maya,
            {
                "file_object_id": uploaded.json()["id"],
                "subject_type": "ssp_book_version",
                "subject_id": version["id"],
            },
        )
        assert attached.status_code == 201, attached.text
        ids[purpose] = str(attached.json()["id"])
    shown = get(app, f"{VERSIONS}/{version['id']}", maya).json()
    assert shown["study_attachment_ids"] == [ids["SSP_STUDY"]]
    assert UUID(ids["ATTACHMENT"]) not in {UUID(value) for value in shown["study_attachment_ids"]}


def _template_approver(app: FastAPI, maya: Actor, clock: FrozenClock) -> Actor:
    """Marcus (Controller, SSP Approver, Tenant Admin), who publishes obligation templates."""
    someone = colleague(maya.member.tenant_id, "marcus")
    for code in ("controller", "ssp_approver", "tenant_admin"):
        assign(someone, code)
    return enrolled(app, clock, someone)


def _series_world(app: FastAPI, maya: Actor, clock: FrozenClock) -> str:
    """A product whose default POB template is ``series`` (a PUBLISHED TPL-SUB-DAILY version —
    T-REF-20 admits only a template with a published version), a distinct good and a DRAFT version
    of book US-LIST; returns the version id."""
    series = new_product(app, maya, code="AVM-SER", name="Series subscription")
    template = published_template(
        app,
        maya,
        _template_approver(app, maya, clock),
        code="TPL-SER",
        outputs=TPL_SUB_DAILY,
        case_line={
            "obligation_key": "POB-01",
            "product_code": "AVM-SER",
            "quantity": "1",
            "total_price": "1200.00",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    template_id = template["template_id"]
    set_default_template(app, maya, str(series["id"]), template_id)
    good = new_product(app, maya, code="AVM-GOOD", name="Distinct good")
    # SSP-ADMISSION-R1: the product read model exposes the admission guard's own predicate — the
    # series product is `distinct` by attribute (Codex's differing-attribute control) yet requires
    # the explicit basis because its default template is series; the good does not.
    for product_id, expected in ((series["id"], True), (good["id"], False)):
        product = get(app, f"{PRODUCTS}/{product_id}", maya).json()
        assert (product["distinctness_default"], product["requires_explicit_ssp_basis"]) == (
            "distinct",
            expected,
        )
    book = new_book(app, maya, code="US-LIST")
    return str(new_version(app, maya, book["id"], legacy_version_label="2026-H1")["id"])


def test_d97_3a_series_product_entry_without_a_basis_is_refused(
    app: FastAPI, maya: Actor, clock: FrozenClock
) -> None:
    """D-97 (3a): an SSP entry for a product whose default POB template is ``series`` carries an
    explicit E-49 ``value_basis``; the API refuses the omission (422 ``validation-failed`` at the
    entry's ``value_basis``) — the corpus-loader pass is not API evidence."""
    version_id = _series_world(app, maya, clock)
    refused = put_entries(
        app, maya, version_id, [entry("AVM-SER", ranges=[{"point_value": "1200.00"}])]
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("entries[0].value_basis", "T-REF-30")]
    # An explicit basis on the series product stores (AMOUNT here: the remaining increments at d).
    saved = put_entries(
        app,
        maya,
        version_id,
        [entry("AVM-SER", value_basis="AMOUNT", ranges=[{"point_value": "1200.00"}])],
    )
    assert saved.status_code == 200, saved.text
    (stored,) = saved.json()["entries"]
    assert (stored["value_basis"], stored["quantity_unit"]) == ("AMOUNT", None)


def test_d97_3a_non_series_entry_keeps_the_amount_default(
    app: FastAPI, maya: Actor, clock: FrozenClock
) -> None:
    """D-97 (3a): the T-REF-30 ``'AMOUNT'`` default stays for a non-series product — an omitted
    basis stores AMOUNT, an explicit AMOUNT or PERCENT_OF_LIST stores as sent; nothing else
    changes for these entries."""
    version_id = _series_world(app, maya, clock)
    saved = put_entries(
        app,
        maya,
        version_id,
        [
            entry("AVM-GOOD", ranges=[{"point_value": "100.00"}]),
            entry("AVM-GOOD", region="EU", value_basis="AMOUNT", ranges=[{"point_value": "90.00"}]),
            entry(
                "AVM-GOOD",
                region="APAC",
                method="cost_plus_margin",
                value_basis="PERCENT_OF_LIST",
                ranges=[{"point_value": "1"}],
            ),
        ],
    )
    assert saved.status_code == 200, saved.text
    assert [
        (item["region"], item["value_basis"], item["quantity_unit"])
        for item in saved.json()["entries"]
    ] == [(None, "AMOUNT", None), ("EU", "AMOUNT", None), ("APAC", "PERCENT_OF_LIST", None)]


def test_d97_3_per_increment_entry_declares_its_quantity_unit(
    app: FastAPI, maya: Actor, clock: FrozenClock
) -> None:
    """D-97 (3): a PER_INCREMENT entry carries E-125 ``quantity_unit`` (422 when absent), no other
    basis carries one, the entries of one product in the request agree on it, and the declared
    unit is stored and listed."""
    version_id = _series_world(app, maya, clock)
    refused = put_entries(
        app,
        maya,
        version_id,
        [
            entry("AVM-SER", value_basis="PER_INCREMENT", ranges=[{"point_value": "110.00"}]),
            entry(
                "AVM-SER",
                region="EU",
                value_basis="PER_INCREMENT",
                quantity_unit="SERVICE_UNITS",
                ranges=[{"point_value": "110.00"}],
            ),
            entry(
                "AVM-SER",
                region="APAC",
                value_basis="PER_INCREMENT",
                quantity_unit="INCREMENTS",
                ranges=[{"point_value": "110.00"}],
            ),
            entry(
                "AVM-GOOD",
                value_basis="AMOUNT",
                quantity_unit="SERVICE_UNITS",
                ranges=[{"point_value": "100.00"}],
            ),
        ],
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [
        ("entries[0].quantity_unit", "T-REF-30"),
        ("entries[3].quantity_unit", "T-REF-30"),
        ("entries[2].quantity_unit", "T-REF-30"),
    ]
    saved = put_entries(
        app,
        maya,
        version_id,
        [
            entry(
                "AVM-SER",
                value_basis="PER_INCREMENT",
                quantity_unit="INCREMENTS",
                ranges=[{"point_value": "110.00"}],
            )
        ],
    )
    assert saved.status_code == 200, saved.text
    (stored,) = saved.json()["entries"]
    assert (stored["value_basis"], stored["quantity_unit"]) == ("PER_INCREMENT", "INCREMENTS")
    assert [item["quantity_unit"] for item in listed(app, maya, version_id)] == ["INCREMENTS"]


def test_d97_3_quantity_unit_agrees_across_the_book(
    app: FastAPI, maya: Actor, clock: FrozenClock
) -> None:
    """D-97 (3) agreement scope: all dated entries of one product identity within one book carry
    the same ``quantity_unit`` — a later version declaring another unit is refused against the
    book's stored declaration, and a rewrite of one entry cannot depart from the other stored
    entries of the product."""
    version_id = _series_world(app, maya, clock)
    first = put_entries(
        app,
        maya,
        version_id,
        [
            entry(
                "AVM-SER",
                value_basis="PER_INCREMENT",
                quantity_unit="INCREMENTS",
                ranges=[{"point_value": "110.00"}],
            )
        ],
    )
    assert first.status_code == 200, first.text
    # Codex admission control: a STORED region=US INCREMENTS entry and a request carrying a valid
    # region=EU SERVICE_UNITS entry of the same product in the same version — the request alone is
    # consistent, so only the stored-versus-request comparison can refuse it, at admission.
    stored_conflict = put_entries(
        app,
        maya,
        version_id,
        [
            entry(
                "AVM-SER",
                region="EU",
                value_basis="PER_INCREMENT",
                quantity_unit="SERVICE_UNITS",
                ranges=[{"point_value": "112.00"}],
            )
        ],
    )
    assert (stored_conflict.status_code, slug(stored_conflict)) == (422, "validation-failed"), (
        stored_conflict.text
    )
    assert fields(stored_conflict) == [("entries[0].quantity_unit", "T-REF-30")]
    assert "INCREMENTS" in stored_conflict.json()["errors"][0]["message"]
    assert [item["region"] for item in listed(app, maya, version_id)] == [None]  # nothing inserted
    shown = get(app, f"{VERSIONS}/{version_id}", maya).json()
    second = new_version(app, maya, shown["ssp_book_id"], legacy_version_label="2026-H2")
    refused = put_entries(
        app,
        maya,
        second["id"],
        [
            entry(
                "AVM-SER",
                value_basis="PER_INCREMENT",
                quantity_unit="SERVICE_UNITS",
                ranges=[{"point_value": "115.00"}],
            )
        ],
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("entries[0].quantity_unit", "T-REF-30")]
    assert "INCREMENTS" in refused.json()["errors"][0]["message"]
    agreed = put_entries(
        app,
        maya,
        second["id"],
        [
            entry(
                "AVM-SER",
                value_basis="PER_INCREMENT",
                quantity_unit="INCREMENTS",
                ranges=[{"point_value": "115.00"}],
            )
        ],
    )
    assert agreed.status_code == 200, agreed.text
    # Rewriting the first version's entry cannot re-declare the unit while the second version's
    # entry still declares INCREMENTS (the replaced entry itself no longer counts).
    rewritten = put_entries(
        app,
        maya,
        version_id,
        [
            entry(
                "AVM-SER",
                value_basis="PER_INCREMENT",
                quantity_unit="SERVICE_UNITS",
                ranges=[{"point_value": "110.00"}],
            )
        ],
    )
    assert (rewritten.status_code, slug(rewritten)) == (422, "validation-failed"), rewritten.text
    # Codex 8/9 supplemental: a contradictory RETAINED population (fabricated below the API — the
    # second version's stored row re-labelled SERVICE_UNITS while the first keeps INCREMENTS) is
    # detected before writing: any request entry of the product is refused naming both units; the
    # historical rows are neither discarded nor reinterpreted.
    (second_entry,) = agreed.json()["entries"]
    ctx = DbContext(tenant_id=maya.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        session.execute(
            update(ssp_entry)
            .where(ssp_entry.c.id == UUID(str(second_entry["id"])))
            .values(quantity_unit="SERVICE_UNITS")
        )
        session.commit()
    for target, unit in ((version_id, "INCREMENTS"), (second["id"], "SERVICE_UNITS")):
        contradicted = put_entries(
            app,
            maya,
            target,
            [
                entry(
                    "AVM-SER",
                    region="APAC",
                    value_basis="PER_INCREMENT",
                    quantity_unit=unit,
                    ranges=[{"point_value": "120.00"}],
                )
            ],
        )
        assert (contradicted.status_code, slug(contradicted)) == (422, "validation-failed"), (
            contradicted.text
        )
        assert fields(contradicted) == [("entries[0].quantity_unit", "T-REF-30")]
        assert "INCREMENTS, SERVICE_UNITS" in contradicted.json()["errors"][0]["message"]
    assert [item["region"] for item in listed(app, maya, version_id)] == [None]  # nothing written
