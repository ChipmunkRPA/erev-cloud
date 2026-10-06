"""Obligation template versions and a posted contract (item CFG-BACKDATE-1, supervisor ruling R-113;
PRD ERR-75; 03 REQ-POL-007; 04 §16.5 "Effective date of a superseding version"; ENGINE_SPEC
S03-R-02; dev-guide DG-KRN-REG-02; CTL-031).

The finding. The engine chooses the template version of an obligation by the contract's inception
date at EVERY computation (S03-R-02), and ``lifecycle.publish`` admitted any effective date later
than that of the published version. A second version of TPL-SUB-DAILY with the monthly-even
convention, dated on or before the inception of K-02 (100 seats × 24 months, 240,000.00 USD, ACTIVE
with posted lines) and published in September, re-timed the contract at its next computation from
10,191.78 / 9,205.48 / 10,191.78 to 10,000.00 a month.

Two ways lead from a template to a contract, and each is closed where it starts:

- a later version of the SAME template: it is dated after today (PRD ERR-75, the date form), so no
  contract dated up to today meets it; a contract dated on or after its effective date takes it;
- a first version of ANOTHER template, whose date is free: it reaches a contract only as the
  default template of the contract's product, and a contract past DRAFT keeps the product state
  its computation recorded (``pinned_refs.products``, security finding SN-7).

Maya (Revenue Accountant, SSP Analyst) prepares; Marcus (Controller, SSP Approver, Tenant Admin;
MFA) approves. The frozen clock reads 12 September 2026; AVM-US has FY2026-P01 to P09 open.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_computation, subledger_line
from erev_api.domain.policies import lifecycle
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    POB_TEMPLATE_VERSIONS,
    POB_TEMPLATES,
    SEAT_MONTH_CASE,
    TPL_SUB_DAILY,
    K02World,
    Workspace,
    activated_contract,
    booked_contract,
    computed,
    k02_body,
    k02_world,
    published_template,
    seat_body,
    seat_line,
    set_default_template,
)
from support.principals import Actor
from support.reference import approve, fields, get, patch, post, slug

PRODUCTS = "/api/v1/products"
CONTRACTS = "/api/v1/contracts"
SEAT = "AVM-SEAT-MO"
DAILY = "TPL-SUB-DAILY"
MONTHLY = "TPL-SUB-MONTHLY"
JANUARY = "2026-01-01T00:00:00Z"
OCTOBER = "2026-10-01T00:00:00Z"
FIRST_QUARTER = ("FY2026-P01", "FY2026-P02", "FY2026-P03")
LAST_QUARTER = ("FY2026-P10", "FY2026-P11", "FY2026-P12")
DAILY_AMOUNTS = ["10191.78", "9205.48", "10191.78"]  # 240,000.00 × days ÷ 730
MONTHLY_AMOUNTS = ["10000.00", "10000.00", "10000.00"]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k02(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K02World:
    return k02_world(app, keyring, clock, files)


def schedule(app: FastAPI, actor: Actor, contract_id: UUID) -> dict[str, str]:
    """The contract's revenue schedule: period key → amount."""
    listed = get(app, f"{CONTRACTS}/{contract_id}/schedule", actor, {"limit": 500})
    assert listed.status_code == 200, listed.text
    return {
        item["period"]["period_key"]: item["amount"]["amount"]
        for item in listed.json()["items"]
        if item["schedule_kind"] == "REVENUE"
    }


def line_count(place: Workspace, contract_id: UUID) -> int:
    return int(
        place.scalar(
            select(func.count())
            .select_from(subledger_line)
            .where(subledger_line.c.contract_id == contract_id)
        )
    )


def pins(place: Workspace, group_id: UUID) -> dict[str, Any]:
    """``pinned_refs.products`` of the group's latest SUCCEEDED computation."""
    rows = place.rows(
        select(contract_computation.c.pinned_refs)
        .where(
            contract_computation.c.combination_group_id == group_id,
            contract_computation.c.status == "SUCCEEDED",
        )
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )
    found: dict[str, Any] = rows[0]["pinned_refs"]["products"]
    return found


def posted_k02(k02: K02World) -> tuple[UUID, UUID, dict[str, str], int]:
    """K-02 ACTIVE and posted under the daily convention: ids, schedule and ledger line count."""
    active = activated_contract(
        k02.place, booked_contract(k02.place, k02_body(k02.customer_id), activate=False)
    )
    contract_id = UUID(str(active.contract["id"]))
    before = schedule(k02.app, k02.place.author, contract_id)
    assert [before[period_key] for period_key in FIRST_QUARTER] == DAILY_AMOUNTS
    posted = line_count(k02.place, contract_id)
    assert posted > 0
    return contract_id, UUID(str(active.combination_group["id"])), before, posted


def published_version_of(app: FastAPI, actor: Actor, code: str) -> tuple[str, str]:
    """The ids of the template ``code`` and of its PUBLISHED version."""
    listed = get(app, POB_TEMPLATES, actor, {"q": code})
    assert listed.status_code == 200, listed.text
    (template,) = [item for item in listed.json()["items"] if item["code"] == code]
    versions = get(app, f"{POB_TEMPLATES}/{template['id']}/versions", actor)
    assert versions.status_code == 200, versions.text
    (current,) = [item for item in versions.json()["items"] if item["status"] == "PUBLISHED"]
    return str(template["id"]), str(current["id"])


def cases_passed(app: FastAPI, actor: Actor, version_id: str) -> None:
    ran = post(app, f"{POB_TEMPLATE_VERSIONS}/{version_id}/test", actor, {})
    assert (ran.status_code, ran.json()["status"]) == (200, "TESTED"), ran.text


@pytest.mark.control("CTL-031")
def test_err_75_a_later_template_version_never_reaches_a_posted_contract(k02: K02World) -> None:
    """The inverted proof of concept and the positive control. (1) Version 2 of the template, dated
    on K-02's inception, is refused at submission and nothing of K-02 moves. (2) Dated ahead it is
    published; K-02 recomputes on version 1: same schedule, same ledger, no intent. (3) A contract
    dated on the effective date takes version 2."""
    app, maya, marcus = k02.app, k02.place.author, k02.marcus
    contract_id, group_id, before, posted = posted_k02(k02)
    template_id, first_id = published_version_of(app, maya, DAILY)

    # (1) the backdated version of the proof of concept
    created = post(
        app,
        f"{POB_TEMPLATES}/{template_id}/versions",
        maya,
        {
            "source_version_id": first_id,
            "ratable_convention": "MONTHLY_EVEN",
            "effective_from": JANUARY,
        },
    )
    assert created.status_code == 201, created.text
    second_id = str(created.json()["id"])
    cases_passed(app, maya, second_id)
    submit = f"{POB_TEMPLATE_VERSIONS}/{second_id}/submit"
    refused = post(app, submit, maya, {"comment": "Monthly convention"})
    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "validation-failed",
        [("effective_from", "REQ-POL-007")],
    ), refused.text
    assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_DATE_PASSED
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_DATE_PASSED
    _, output, _ = computed(k02.place, group_id)
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert schedule(app, maya, contract_id) == before
    assert line_count(k02.place, contract_id) == posted

    # (2) dated ahead, the version is published and K-02 keeps version 1
    shown = get(app, f"{POB_TEMPLATE_VERSIONS}/{second_id}", maya)
    moved = patch(
        app,
        f"{POB_TEMPLATE_VERSIONS}/{second_id}",
        maya,
        {"effective_from": OCTOBER},
        if_match=shown.headers["ETag"],
    )
    assert moved.status_code == 200, moved.text
    cases_passed(app, maya, second_id)
    sent = post(app, submit, maya, {"comment": "Monthly convention from October"})
    assert sent.status_code == 200, sent.text
    decided = approve(app, str(sent.json()["pending_approval_request_id"]), marcus)
    assert decided.status_code == 200, decided.text
    bundle, output, _ = computed(k02.place, group_id)
    assert [
        (item.version_key, item.effective_from, item.effective_to, item.ratable_convention)
        for item in bundle.pob_template_versions
    ] == [
        (f"{DAILY}@v1", date(2026, 1, 1), date(2026, 10, 1), "DAILY"),
        (f"{DAILY}@v2", date(2026, 10, 1), None, "MONTHLY_EVEN"),
    ]
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert schedule(app, maya, contract_id) == before
    assert line_count(k02.place, contract_id) == posted

    # (3) positive control: a contract dated on the effective date takes version 2
    line = seat_line("O1", seats="100", price="120000.00", start="2026-10-01", end="2027-09-30")
    later_body = seat_body(
        k02.customer_id, external_id="SF-ORD-20002", inception="2026-10-01", lines=[line]
    )
    later = activated_contract(k02.place, booked_contract(k02.place, later_body, activate=False))
    amounts = schedule(app, maya, UUID(str(later.contract["id"])))
    assert [amounts[period_key] for period_key in LAST_QUARTER] == MONTHLY_AMOUNTS


def test_a_first_version_reaches_a_contract_only_through_its_product_and_the_pin_holds_it(
    k02: K02World,
) -> None:
    """A first version keeps a free date (ruling R-113 point 2). TPL-SUB-MONTHLY, version 1, is
    published in September with effect from 1 January and made the seat product's default
    template: K-02 recomputes on the template its pin names; the next contract takes the new one."""
    app, maya, marcus = k02.app, k02.place.author, k02.marcus
    contract_id, group_id, before, posted = posted_k02(k02)
    pinned = pins(k02.place, group_id)
    assert pinned[SEAT]["default_template_code"] == DAILY

    monthly = published_template(
        app,
        maya,
        marcus,
        code=MONTHLY,
        outputs={**TPL_SUB_DAILY, "ratable_convention": "MONTHLY_EVEN"},
        case_line=SEAT_MONTH_CASE,
    )
    listed = get(app, PRODUCTS, maya, {"q": SEAT})
    assert listed.status_code == 200, listed.text
    (product,) = [item for item in listed.json()["items"] if item["code"] == SEAT]
    set_default_template(app, maya, str(product["id"]), monthly["template_id"])

    bundle, output, _ = computed(k02.place, group_id)
    (seat,) = [item for item in bundle.group.products if item.code == SEAT]
    assert seat.default_template_code == DAILY
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert schedule(app, maya, contract_id) == before
    assert line_count(k02.place, contract_id) == posted
    assert pins(k02.place, group_id) == pinned

    # Positive control: the next contract of the product is built on the new default template.
    later_body = {
        **k02_body(k02.customer_id),
        "external_id": "SF-ORD-10003",
        "document_ref": "SF-ORD-10003",
    }
    later = activated_contract(k02.place, booked_contract(k02.place, later_body, activate=False))
    amounts = schedule(app, maya, UUID(str(later.contract["id"])))
    assert [amounts[period_key] for period_key in FIRST_QUARTER] == MONTHLY_AMOUNTS
    later_pin = pins(k02.place, UUID(str(later.combination_group["id"])))[SEAT]
    assert later_pin["default_template_code"] == MONTHLY
