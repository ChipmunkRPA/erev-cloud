"""Calendars with periods before a book's first period (ENG-CAL-PREBOOK-1; ENGINE_SPEC §0.4
``EntityInput.periods``, CV-12, CV-13; 05 RCP-03, RCP-15, RCP-20; 04 T-REF-03, T-REF-06; PRD
WLD-P-05, IMP-75, ERR-61, ERR-62; supervisor rulings R-58 and R-61 (f)).

An entity keeps a book from a first period (T-REF-03), and ``period_state`` rows exist from that
period on (T-REF-06). Two calendar shapes leave earlier periods without a state:

- the April year of PRD WLD-P-05: FY2026 runs from April 2025, the book is kept from January 2026
  (``FY2026-P10``), so nine periods precede it;
- a calendar generated a year early: FY2025 to FY2027, the book kept from ``FY2026-P01``, so twelve
  periods precede it.

Bundle assembly hands the engine the calendar from the group's inception period on, preceded by
the earlier periods for which every kept book has a state; the engine refuses a period without a
state for a kept book (CV-13). The worlds are built through the routes: Maya (Revenue Accountant,
SSP Analyst) prepares, Priya (SSP Approver, Revenue Reviewer) and Marcus (Controller, SSP Approver,
Tenant Admin; MFA) approve. One daily-ratable seat contract of 24,000.00 USD over twelve months is
booked, its Step 1 recorded, and activated through the approval. The computations run
``erev_engine.compute``. The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    book,
    combination_group_member,
    contract,
    contract_computation,
    entity_book,
    exception_item,
    period,
    period_state,
    subledger_line,
)
from erev_api.domain.contracts import bundles
from erev_api.enums import ComputationTrigger
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, update
from support.db import TestDatabase
from support.factories import (
    AVM_US_CHART,
    SEAT_MO,
    SEAT_MO_CASE,
    STEP1_CHART,
    TPL_SUB_DAILY,
    Workspace,
    approved_ssp_version,
    customer_id,
    product_with_template,
    published_mapping,
    published_template,
    range_entry,
    set_default_template,
    ssp_book,
    stamp_test_release,
    step1_criteria,
    workspace,
)
from support.principals import Actor, colleague, enrolled, member
from support.reference import (
    BOOKS,
    CALENDARS,
    approve,
    assign,
    entity,
    fields,
    get,
    holding,
    patch,
    periods,
    post,
    put,
    slug,
)

CONTRACTS = "/api/v1/contracts"
JUDGEMENTS = "/api/v1/judgements"
ENTITY = "AVM-X"
PRICE = Decimal("24000.00")
CENT = Decimal("0.01")
APPROVAL_HEADER = "x-erev-approval-request"


@dataclass(frozen=True, slots=True)
class Shape:
    """A calendar and the first period of the entity's primary book."""

    name: str
    start_month: int
    years: tuple[int, ...]
    first_period_key: str | None  # None: the calendar's earliest period
    open_keys: tuple[str, ...]  # January to September 2026
    unstated: int  # periods before the book's first period


APRIL_YEAR = Shape(
    "april-year",
    4,
    (2026, 2027, 2028),
    "FY2026-P10",
    (
        *(f"FY2026-P{number:02d}" for number in (10, 11, 12)),
        *(f"FY2027-P{number:02d}" for number in range(1, 7)),
    ),
    9,
)
YEAR_EARLY = Shape(
    "year-early",
    1,
    (2025, 2026, 2027),
    "FY2026-P01",
    tuple(f"FY2026-P{number:02d}" for number in range(1, 10)),
    12,
)
JANUARY_YEAR = Shape(
    "january-year", 1, (2026, 2027), None, tuple(f"FY2026-P{n:02d}" for n in range(1, 10)), 0
)
LATE_BOOK = Shape(
    "late-book", 1, (2026, 2027), "FY2026-P04", tuple(f"FY2026-P{n:02d}" for n in range(4, 10)), 3
)


@dataclass(frozen=True, slots=True)
class World:
    place: Workspace
    priya: Actor
    marcus: Actor
    entity_id: UUID
    customer: UUID
    calendar_id: str

    @property
    def app(self) -> FastAPI:
        return self.place.app


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


# --- the world -----------------------------------------------------------------------------------


def _calendar(app: FastAPI, actor: Actor, shape: Shape) -> str:
    created = post(
        app,
        CALENDARS,
        actor,
        {
            "code": shape.name.upper(),
            "name": f"{shape.name} calendar",
            "fiscal_year_start_month": shape.start_month,
        },
    )
    assert created.status_code == 201, created.text
    calendar_id = str(created.json()["id"])
    for year in shape.years:
        generated = post(
            app, f"{CALENDARS}/{calendar_id}/generate-year", actor, {"fiscal_year": year}
        )
        assert generated.status_code == 200, generated.text
    return calendar_id


def _open(app: FastAPI, actor: Actor, keys: Sequence[str], *, book: str = "ASC606") -> None:
    """``POST /periods/{id}/open`` for the named periods of ``book``, in order."""
    states = {
        item["period"]["period_key"]: item for item in periods(app, actor, entity=ENTITY, book=book)
    }
    for key in keys:
        opened = post(
            app,
            f"/api/v1/periods/{states[key]['id']}/open",
            actor,
            {"comment": "Open for contracts"},
            if_match=f'"r{states[key]["row_version"]}"',
        )
        assert opened.status_code == 200, opened.text


def _world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    shape: Shape,
    *,
    chart: Sequence[tuple[str, str, str, str, str]] = AVM_US_CHART,
) -> World:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("ssp_approver", "revenue_reviewer")),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    marcus = approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    calendar_id = _calendar(app, maya, shape)
    first = {} if shape.first_period_key is None else {"first_period_key": shape.first_period_key}
    created = entity(app, maya, code=ENTITY, calendar_id=calendar_id, **first)
    _open(app, maya, shape.open_keys)
    buyer = customer_id(app, maya, code="C-02", name="Marrowby Health Partners LLC (Demo)")
    seat = product_with_template(
        app, maya, code=SEAT_MO, name="Platform seat, monthly", revenue_category="SUBSCRIPTION"
    )
    daily = published_template(
        app, maya, marcus, code="TPL-SUB-DAILY", outputs=TPL_SUB_DAILY, case_line=SEAT_MO_CASE
    )
    set_default_template(app, maya, seat, daily["template_id"])
    approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        ssp_book(app, maya),
        label="2026-H1",
        effective_from="2026-01-01",
        entries=[range_entry(SEAT_MO, "2160.00", "2400.00", "2640.00", value_basis="AMOUNT")],
    )
    published_mapping(app, maya, marcus, chart=chart)
    stamp_test_release()
    return World(
        place=workspace(app, clock, keyring, files, maya),
        priya=approvers["priya"],
        marcus=marcus,
        entity_id=UUID(str(created["id"])),
        customer=buyer,
        calendar_id=calendar_id,
    )


# --- contracts through the routes ----------------------------------------------------------------


def _body(world: World, external_id: str, start: date, end: date) -> dict[str, Any]:
    return {
        "external_id": external_id,
        "customer_id": str(world.customer),
        "contracting_entity_code": ENTITY,
        "transaction_currency": "USD",
        "inception_date": start.isoformat(),
        "document_ref": external_id,
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": SEAT_MO,
                "quantity": "10",
                "total_price": {"amount": str(PRICE), "currency": "USD"},
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }
        ],
    }


def _booked(world: World, external_id: str, start: date, end: date) -> UUID:
    created = post(world.app, CONTRACTS, world.place.author, _body(world, external_id, start, end))
    assert created.status_code == 201, created.text
    return UUID(str(created.json()["id"]))


def _step1(world: World, contract_id: UUID, effective: date, books: Sequence[str]) -> int:
    """A reviewed COLLECTIBILITY record and a probable assessment per book; the new head. The
    record carries the five criteria of a Step 1 review (supervisor rulings R-113 (f),
    R-115 (f))."""
    maya = world.place.author
    created = post(
        world.app,
        JUDGEMENTS,
        maya,
        {
            "topic": "COLLECTIBILITY",
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "conclusion": "Collection of the consideration is probable.",
            "rationale": "Credit review of the customer and its payment history.",
            "questionnaire": {"criteria": step1_criteria()},
        },
    )
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    submitted = post(world.app, f"{JUDGEMENTS}/{record_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    reviewed = approve(world.app, submitted.json()["approval_request_id"], world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    appended = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/events",
        maya,
        {
            "events": [
                {
                    "event_type": "COLLECTIBILITY_ASSESSED",
                    "effective_date": effective.isoformat(),
                    "payload": {
                        "book": book,
                        "is_probable": True,
                        "judgement_record_id": record_id,
                    },
                }
                for book in books
            ]
        },
        if_match='"s1"',
    )
    assert appended.status_code == 201, appended.text
    return 1 + len(books)


def _activated(
    world: World, external_id: str, start: date, end: date, books: Sequence[str] = ("ASC606",)
) -> UUID:
    """Booked, Step 1 recorded, submitted (the dry run) and approved by Priya."""
    contract_id = _booked(world, external_id, start, end)
    head = _step1(world, contract_id, start, books)
    submitted = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/submit-activation",
        world.place.author,
        {},
        if_match=f'"s{head}"',
    )
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    shown = get(world.app, f"{CONTRACTS}/{contract_id}", world.place.author).json()
    assert shown["status"] == "ACTIVE", shown
    return contract_id


# --- reads ---------------------------------------------------------------------------------------


def _group_id(world: World, contract_id: UUID) -> UUID:
    return UUID(
        str(
            world.place.scalar(
                select(combination_group_member.c.combination_group_id).where(
                    combination_group_member.c.contract_id == contract_id
                )
            )
        )
    )


def _computations(world: World, contract_id: UUID) -> list[dict[str, Any]]:
    """The group's computations, oldest first."""
    return world.place.rows(
        select(contract_computation.c.status, contract_computation.c.problem)
        .where(contract_computation.c.combination_group_id == _group_id(world, contract_id))
        .order_by(contract_computation.c.created_at, contract_computation.c.id)
    )


def _unstated(world: World, book: str = "ASC606") -> list[str]:
    """The keys of the entity's calendar periods without a ``period_state`` row for ``book``."""
    stated = (
        select(period_state.c.period_id)
        .where(period_state.c.entity_id == world.entity_id, period_state.c.book_code == book)
        .scalar_subquery()
    )
    rows = world.place.rows(
        select(period.c.period_key).where(period.c.id.not_in(stated)).order_by(period.c.start_date)
    )
    return [str(row["period_key"]) for row in rows]


def _revenue(world: World, contract_id: UUID) -> dict[str, dict[date, Decimal]]:
    """Per book, the contract's posted REVENUE by period start date, credits positive (T-SL-04
    ``amount_txn`` is signed, debit positive)."""
    rows = world.place.rows(
        select(
            subledger_line.c.book_code,
            period.c.start_date,
            subledger_line.c.amount_txn,
            subledger_line.c.origin_period_id,
        )
        .select_from(
            subledger_line.join(
                period,
                (period.c.tenant_id == subledger_line.c.tenant_id)
                & (period.c.id == subledger_line.c.period_id),
            )
        )
        .where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.account_role == "REVENUE",
        )
    )
    found: dict[str, dict[date, Decimal]] = {}
    for row in rows:
        assert row["origin_period_id"] is None, row  # nothing is carried from another period
        per_book = found.setdefault(str(row["book_code"]), {})
        per_book[row["start_date"]] = per_book.get(row["start_date"], Decimal(0)) - Decimal(
            row["amount_txn"]
        )
    return {book: dict(sorted(per_book.items())) for book, per_book in found.items()}


def _month_starts(first: date, last: date) -> list[date]:
    found = [first.replace(day=1)]
    while found[-1] < last.replace(day=1):
        found.append((found[-1] + timedelta(days=32)).replace(day=1))
    return found


def _ratable(start: date, end: date, through: date) -> dict[date, Decimal]:
    """POLICIES ALG-01 for a DAILY series of ``PRICE`` over [``start``, ``end``]: per calendar
    month through ``through``, the rounded cumulative amount less the previous month's."""
    days = Decimal((end - start).days + 1)
    found: dict[date, Decimal] = {}
    previous = Decimal(0)
    for month in _month_starts(start, through):
        month_end = (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        elapsed = Decimal((min(month_end, end) - start).days + 1)
        cumulative = (PRICE * elapsed / days).quantize(CENT, rounding=ROUND_HALF_UP)
        found[month] = cumulative - previous
        previous = cumulative
    return found


# --- ENG-CAL-PREBOOK-1 ---------------------------------------------------------------------------

SEPTEMBER = date(2026, 9, 30)  # the end of the last open period


@pytest.mark.parametrize("shape", [APRIL_YEAR, YEAR_EARLY], ids=lambda shape: shape.name)
@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 1, 1), date(2026, 12, 31)), (date(2026, 4, 1), date(2027, 3, 31))],
    ids=["from-the-first-period", "from-a-later-period"],
)
def test_calendar_with_periods_before_the_book_computes(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    shape: Shape,
    start: date,
    end: date,
) -> None:
    """A draft and an activated contract of an entity whose calendar starts before its book
    compute; revenue posts in the periods of the book as in a calendar that starts with it."""
    world = _world(app, keyring, clock, files, shape)
    assert len(_unstated(world)) == shape.unstated

    contract_id = _booked(world, "PB-0001", start, end)
    # the booking's provisional computation (API-S-ContractCreate)
    assert [str(row["status"]) for row in _computations(world, contract_id)] == ["SUCCEEDED"]
    draft = get(world.app, f"{CONTRACTS}/{contract_id}", world.place.author).json()
    assert draft["status"] == "DRAFT"

    head = _step1(world, contract_id, start, ("ASC606",))
    submitted = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/submit-activation",
        world.place.author,
        {},
        if_match=f'"s{head}"',
    )
    assert submitted.status_code == 200, submitted.text  # the activation dry run
    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    status = world.place.scalar(select(contract.c.status).where(contract.c.id == contract_id))
    assert str(status) == "ACTIVE"
    assert {str(row["status"]) for row in _computations(world, contract_id)} == {"SUCCEEDED"}
    assert (
        world.place.rows(
            select(exception_item.c.code).where(
                exception_item.c.combination_group_id == _group_id(world, contract_id),
                exception_item.c.source == "ENGINE",
            )
        )
        == []
    )

    expected = _ratable(start, end, SEPTEMBER)
    assert sum(expected.values()) == (
        PRICE * Decimal((SEPTEMBER - start).days + 1) / Decimal((end - start).days + 1)
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    assert _revenue(world, contract_id) == {"ASC606": expected}

    # 05 RCP-15: the bundle starts where every kept book has a state, never before.
    with world.place.uow() as uow:
        bundle = bundles.build(
            uow.session, _group_id(world, contract_id), uow.now, (), ComputationTrigger.COMMAND
        )
    (calendar,) = bundle.entities
    assert calendar.periods[0].period_key == shape.first_period_key
    assert all(dict(item.states).get("ASC606") for item in calendar.periods)
    # ENGINE_SPEC §0.4: every period from the group's inception on is there.
    assert calendar.periods[0].start_date <= start
    assert calendar.periods[-1].end_date >= end


def test_second_book_kept_later_computes_in_both_books(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """IFRS15 is kept from July 2026 by an entity that keeps ASC606 from January: a contract that
    begins in August, activated before the second book was kept, and one activated after it,
    compute in both books; the periods before July carry no IFRS15 state and are not part of
    their bundles."""
    world = _world(app, keyring, clock, files, JANUARY_YEAR)
    maya = world.place.author
    august, september = date(2026, 8, 1), date(2026, 9, 1)
    earlier = _activated(world, "SB-0001", august, date(2027, 7, 31))
    assert _revenue(world, earlier) == {"ASC606": _ratable(august, date(2027, 7, 31), SEPTEMBER)}

    # The ACTIVE contract began in August, after FY2026-P07 starts, and holds no adoption.
    kept = put(
        world.app,
        f"/api/v1/entities/{world.entity_id}/books/IFRS15",
        world.marcus,
        {"is_enabled": True, "first_period_key": "FY2026-P07"},
    )
    assert kept.status_code == 200, kept.text
    _open(world.app, maya, ("FY2026-P07", "FY2026-P08", "FY2026-P09"), book="IFRS15")
    assert _unstated(world, "IFRS15") == [f"FY2026-P{number:02d}" for number in range(1, 7)]
    assert _unstated(world, "ASC606") == []

    # the contract booked before the second book was kept: its next computation covers both books
    billed = post(
        world.app,
        f"{CONTRACTS}/{earlier}/events",
        maya,
        {
            "events": [
                {
                    "event_type": "BILLING_RECORDED",
                    "effective_date": "2026-08-05",
                    "payload": {
                        "invoice_number": "INV-SB-0001",
                        "line_external_id": "INV-SB-0001-1",
                        "amount": {"amount": "6000.00", "currency": "USD"},
                        "issue_date": "2026-08-05",
                    },
                }
            ]
        },
        if_match='"s3"',
    )
    assert billed.status_code == 201, billed.text
    computed = billed.json()["computation"]
    assert computed["status"] == "SUCCEEDED"
    assert sorted(computed["contract_version_ids"]) == ["ASC606", "IFRS15"]
    # The first book's postings stand. What the second book recognises for a contract activated
    # before it was kept is the Step 1 question of ruling R-20, so its amounts are not asserted.
    assert _revenue(world, earlier)["ASC606"] == _ratable(august, date(2027, 7, 31), SEPTEMBER)

    later = _activated(world, "SB-0002", september, date(2027, 8, 31), books=("ASC606", "IFRS15"))
    assert {str(row["status"]) for row in _computations(world, later)} == {"SUCCEEDED"}
    expected = _ratable(september, date(2027, 8, 31), SEPTEMBER)
    assert _revenue(world, later) == {"ASC606": expected, "IFRS15": expected}

    with world.place.uow() as uow:
        bundle = bundles.build(
            uow.session, _group_id(world, later), uow.now, (), ComputationTrigger.COMMAND
        )
    (calendar,) = bundle.entities
    assert [book.book_code for book in bundle.books] == ["ASC606", "IFRS15"]
    assert calendar.periods[0].period_key == "FY2026-P07"
    assert all({"ASC606", "IFRS15"} <= set(dict(item.states)) for item in calendar.periods)

    # A contract booked now that began in March, before the second book's first period, is not
    # supported in 1.0 (04 T-REF-03): its computation is quarantined and says which book and period.
    older = _booked(world, "SB-0003", date(2026, 3, 1), date(2027, 2, 28))
    (refused,) = _computations(world, older)
    assert str(refused["status"]) == "QUARANTINED"
    assert [item["message"] for item in refused["problem"]["errors"]] == [
        "the period carries no state for the book "
        "(book_code IFRS15, period_key FY2026-P03, rule CV-13)"
    ]


def test_quarantine_names_the_rule_the_period_and_the_book(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A contract that begins before the first period of its entity's book: the periods from its
    inception on are the engine's input (ENGINE_SPEC §0.4), two of them carry no state, and the
    engine refuses them (CV-13). The stored problem and the exception item say which rule, which
    period and which book (05 RCP-20; PRD IMP-75), so the reader can act."""
    world = _world(app, keyring, clock, files, LATE_BOOK)
    assert _unstated(world) == ["FY2026-P01", "FY2026-P02", "FY2026-P03"]
    contract_id = _booked(world, "PB-0002", date(2026, 2, 1), date(2027, 1, 31))

    (computed,) = _computations(world, contract_id)
    problem = computed["problem"]
    assert (str(computed["status"]), problem["code"]) == (
        "QUARANTINED",
        "ENGINE_INVARIANT_VIOLATION",
    )
    assert [(item["field"], item["rule_id"], item["message"]) for item in problem["errors"]] == [
        (
            None,
            "ENGINE_INVARIANT_VIOLATION",
            "the period carries no state for the book "
            "(book_code ASC606, period_key FY2026-P02, rule CV-13)",
        )
    ]
    reference = str(problem["instance"]).removeprefix("urn:erev:request:")
    expected = (
        "PB-0002 failed invariant CV-13 (the period carries no state for the book: "
        "book_code ASC606, period_key FY2026-P02) and was quarantined. "
        f"Nothing was posted for it. Reference {reference}."
    )
    assert problem["detail"] == expected
    (item,) = world.place.rows(
        select(
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.message,
            exception_item.c.source_payload,
        ).where(exception_item.c.combination_group_id == _group_id(world, contract_id))
    )
    assert (item["code"], str(item["severity"]), item["message"]) == (
        "ENGINE_INVARIANT_VIOLATION",
        "BLOCKING",
        expected,
    )
    assert item["source_payload"]["detail"] == {
        "book_code": "ASC606",
        "period_key": "FY2026-P02",
        "rule": "CV-13",
    }
    assert _revenue(world, contract_id) == {}


def _keep(world: World, book_code: str, body: dict[str, Any]) -> Any:
    """``PUT /entities/{id}/books/{code}`` as Marcus (Tenant Admin)."""
    return put(
        world.app, f"/api/v1/entities/{world.entity_id}/books/{book_code}", world.marcus, body
    )


def _kept(world: World, book_code: str) -> list[tuple[str, bool]]:
    rows = world.place.rows(
        select(period.c.period_key, entity_book.c.is_enabled)
        .select_from(
            entity_book.join(
                period,
                (period.c.tenant_id == entity_book.c.tenant_id)
                & (period.c.id == entity_book.c.first_period_id),
            )
        )
        .where(entity_book.c.entity_id == world.entity_id, entity_book.c.book_code == book_code)
    )
    return [(str(row["period_key"]), bool(row["is_enabled"])) for row in rows]


def test_book_does_not_start_after_a_contract_of_the_entity_began(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 T-REF-03 rev 1.123 (PRD ERR-61): an entity does not begin to keep a book, or keep it
    again, from a first period that starts after one of its contracts began — that contract could
    not be computed (05 RCP-15; ENGINE_SPEC CV-13). A draft counts; the period that contains the
    inception date is the latest first period."""
    world = _world(app, keyring, clock, files, JANUARY_YEAR)
    draft = _booked(world, "RF-0001", date(2026, 8, 15), date(2027, 8, 14))

    refused = _keep(world, "IFRS15", {"is_enabled": True, "first_period_key": "FY2026-P09"})
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("first_period_key", "T-REF-03")]
    assert [error["message"] for error in refused.json()["errors"]] == [
        "AVM-X has a contract that began on 2026-08-15 (RF-0001), before FY2026-P09 starts. "
        "Keep IFRS 15 from a period that starts on or before that date."
    ]
    assert _kept(world, "IFRS15") == []
    assert _unstated(world, "IFRS15") == _unstated(world, "LEGACY")  # no IFRS15 state was written
    enabled = world.place.scalar(select(book.c.is_enabled).where(book.c.code == "IFRS15"))
    assert enabled is False

    # FY2026-P08 starts on 1 August, on or before the day the contract began. The draft does not
    # hold the adoption either: only a contract behind the not-a-contract gate does (ERR-62).
    kept = _keep(world, "IFRS15", {"is_enabled": True, "first_period_key": "FY2026-P08"})
    assert kept.status_code == 200, kept.text
    assert _kept(world, "IFRS15") == [("FY2026-P08", True)]

    # While the book is not kept, a contract that began in July is booked in ASC606 alone.
    disabled = _keep(world, "IFRS15", {"is_enabled": False})
    assert disabled.status_code == 200, disabled.text
    july = _booked(world, "RF-0002", date(2026, 7, 1), date(2027, 6, 30))
    assert [str(row["status"]) for row in _computations(world, july)] == ["SUCCEEDED"]

    again = _keep(world, "IFRS15", {"is_enabled": True})
    assert again.status_code == 422, again.text
    assert slug(again) == "validation-failed"
    assert fields(again) == [("first_period_key", "T-REF-03")]
    assert [error["message"] for error in again.json()["errors"]] == [
        "AVM-X has a contract that began on 2026-07-01 (RF-0002), before FY2026-P08 starts. "
        "Keep IFRS 15 from a period that starts on or before that date."
    ]
    assert _kept(world, "IFRS15") == [("FY2026-P08", False)]
    # The contracts go on computing in the book the entity keeps.
    assert {str(row["status"]) for row in _computations(world, draft)} == {"SUCCEEDED"}


# --- STEP1-BOOK-ADOPTION-1 (supervisor ruling R-61 (f)) -------------------------------------------


def _record(world: World, contract_id: UUID, topic: str, **members: Any) -> str:
    """A judgement record Maya prepares and Marcus reviews; returns its id. It carries the
    five criteria of a Step 1 review (supervisor rulings R-113 (f), R-115 (f))."""
    maya = world.place.author
    answers = {"criteria": step1_criteria(topic), **members.pop("questionnaire", {})}
    created = post(
        world.app,
        JUDGEMENTS,
        maya,
        {
            "topic": topic,
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "book": "ASC606",
            "conclusion": f"{topic} assessed.",
            "rationale": "Credit review of the customer and the contract terms.",
            "questionnaire": answers,
            **members,
        },
    )
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    submitted = post(world.app, f"{JUDGEMENTS}/{record_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    reviewed = approve(world.app, submitted.json()["approval_request_id"], world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    return record_id


def _head(world: World, contract_id: UUID) -> int:
    return int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )


def _assessed(world: World, contract_id: UUID, record_id: str, *, probable: bool, on: date) -> Any:
    """``COLLECTIBILITY_ASSESSED`` of ASC606 recorded by Maya; the 201 body."""
    appended = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/events",
        world.place.author,
        {
            "events": [
                {
                    "event_type": "COLLECTIBILITY_ASSESSED",
                    "effective_date": on.isoformat(),
                    "payload": {
                        "book": "ASC606",
                        "is_probable": probable,
                        "judgement_record_id": record_id,
                    },
                }
            ]
        },
        if_match=f'"s{_head(world, contract_id)}"',
    )
    assert appended.status_code == 201, appended.text
    return appended.json()


def _gated(world: World, external_id: str, start: date) -> UUID:
    """A draft brought behind the not-a-contract gate through the Step 1 route: a reviewed
    NOT_A_CONTRACT record and the not-probable assessment that cites it (PRD SM-02)."""
    contract_id = _booked(world, external_id, start, start.replace(year=start.year + 1))
    record = _record(
        world, contract_id, "NOT_A_CONTRACT", questionnaire={"consideration_nonrefundable": False}
    )
    body = _assessed(world, contract_id, record, probable=False, on=start)
    assert body["contract"]["status"] == "NOT_A_CONTRACT"
    return contract_id


def _stored_status(world: World, contract_id: UUID) -> str:
    return str(world.place.scalar(select(contract.c.status).where(contract.c.id == contract_id)))


def test_book_is_not_kept_while_a_contract_is_behind_the_step_1_gate(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 T-REF-03 rev 1.123 (PRD ERR-62; ruling R-61 (f)): a group is computed in every enabled
    book kept by an entity of the group and its whole stream is replayed there, so a book adopted
    while a contract stands behind the not-a-contract gate would activate it with no approved
    activation. The command refuses and names the contract; once the contract is void, or
    activated through the approved criteria-met path, the same command succeeds."""
    world = _world(app, keyring, clock, files, JANUARY_YEAR, chart=STEP1_CHART)
    maya = world.place.author
    # Two months apart, so that no combination suggestion joins them (S02-R-14).
    first = _gated(world, "GT-0001", date(2026, 9, 1))
    second = _gated(world, "GT-0002", date(2026, 7, 1))
    keep = {"is_enabled": True}

    refused = _keep(world, "IFRS15", keep)
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("code", "T-REF-03")]
    assert [error["message"] for error in refused.json()["errors"]] == [
        "GT-0001 is not yet a contract under Step 1. "
        "Activate or void it before AVM-X keeps IFRS 15."
    ]
    assert _kept(world, "IFRS15") == []
    # With a first period after the July contract began both refusals are returned: ERR-62 and
    # ERR-61.
    both = _keep(world, "IFRS15", {"is_enabled": True, "first_period_key": "FY2026-P09"})
    assert both.status_code == 422, both.text
    assert fields(both) == [("code", "T-REF-03"), ("first_period_key", "T-REF-03")]

    # The first contract is voided (requested by Maya, approved by Priya): the second still holds.
    requested = post(
        world.app,
        f"{CONTRACTS}/{first}/request-void",
        maya,
        {"reason_code": "CREATED_IN_ERROR", "comment": "Booked twice."},
        if_match=f'"s{_head(world, first)}"',
    )
    assert requested.status_code == 200, requested.text
    voided = approve(world.app, requested.json()["approval_request_id"], world.priya)
    assert voided.status_code == 200, voided.text
    assert _stored_status(world, first) == "VOIDED"
    refused = _keep(world, "IFRS15", keep)
    assert refused.status_code == 422, refused.text
    assert [error["message"] for error in refused.json()["errors"]] == [
        "GT-0002 is not yet a contract under Step 1. "
        "Activate or void it before AVM-X keeps IFRS 15."
    ]

    # The second meets the criteria: a reviewed record, the probable re-assessment, the activation
    # submitted; while the request is pending the stored contract is still behind the gate. Time
    # passes first: the criteria-met record is reviewed AFTER the gate was recorded (supervisor
    # rulings R-77 (3), R-82 (d)), and the clock of this test stands still unless moved.
    clock.advance(timedelta(minutes=1))
    met = _record(world, second, "COLLECTIBILITY")
    _assessed(world, second, met, probable=True, on=date(2026, 7, 10))
    submitted = post(
        world.app,
        f"{CONTRACTS}/{second}/submit-activation",
        maya,
        {"comment": "Collection is now probable."},
        if_match=f'"s{_head(world, second)}"',
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "PENDING_REVIEW"
    assert _stored_status(world, second) == "NOT_A_CONTRACT"
    pending = _keep(world, "IFRS15", keep)
    assert pending.status_code == 422, pending.text
    assert fields(pending) == [("code", "T-REF-03")]

    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    assert _stored_status(world, second) == "ACTIVE"
    kept = _keep(world, "IFRS15", keep)
    assert kept.status_code == 200, kept.text
    assert _kept(world, "IFRS15") == [("FY2026-P01", True)]


def _tenant_book(world: World, code: str) -> dict[str, Any]:
    (row,) = world.place.rows(
        select(book.c.is_enabled, book.c.row_version).where(book.c.code == code)
    )
    return row


def test_enabling_a_tenant_book_that_an_entity_still_keeps_takes_the_same_guards(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-80: ``PATCH /books/{code}`` that enables a tenant book while entity rows
    still keep it adopts the book for those entities, so it takes the guards of
    ``PUT /entities/{id}/books/{code}`` (04 T-REF-03 rev 1.123; PRD ERR-61, ERR-62), on the member
    it changes. The state — the tenant's book off while an entity still keeps it — arose when a
    user whose scope was another entity disabled the tenant book: the row of the entity that
    keeps it was outside that user's sight (04 RLS-TE). Since item SCOPE-WORKSPACE-LISTS-1 (d)
    (04 API-C-03 rev 1.276; the supervisor's ruling of 2026-10-02) that command asks the
    permission for all entities and its keep-guard reads every keeper, so the route no longer
    makes the state: Omar is refused, and the state is written here as rows, as a workspace's
    table may hold it from before. The adoption guards are asked as before."""
    world = _world(app, keyring, clock, files, JANUARY_YEAR, chart=STEP1_CHART)
    maya = world.place.author
    kept = _keep(world, "IFRS15", {"is_enabled": True, "first_period_key": "FY2026-P08"})
    assert kept.status_code == 200, kept.text
    other = entity(app, maya, code="AVM-Y", calendar_id=world.calendar_id)
    omar = holding(
        app,
        colleague(world.place.tenant_id, "omar"),
        "revenue_accountant",
        entity_ids=[UUID(str(other["id"]))],
    )
    version = _tenant_book(world, "IFRS15")["row_version"]
    by_omar = patch(app, f"{BOOKS}/IFRS15", omar, {"is_enabled": False}, if_match=f'"r{version}"')
    assert (by_omar.status_code, slug(by_omar)) == (403, "forbidden"), by_omar.text
    assert _tenant_book(world, "IFRS15")["is_enabled"] is True
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(book)
            .where(book.c.code == "IFRS15")
            .values(is_enabled=False, row_version=book.c.row_version + 1)
        )
    assert _tenant_book(world, "IFRS15")["is_enabled"] is False
    assert _kept(world, "IFRS15") == [("FY2026-P08", True)]  # AVM-X still keeps it

    # While the book is off for the tenant: a July contract, and a draft behind the Step 1 gate.
    july = _booked(world, "TB-0001", date(2026, 7, 1), date(2027, 6, 30))
    assert [str(row["status"]) for row in _computations(world, july)] == ["SUCCEEDED"]
    _gated(world, "TB-0002", date(2026, 9, 1))

    version = _tenant_book(world, "IFRS15")["row_version"]
    refused = patch(
        app, f"{BOOKS}/IFRS15", world.marcus, {"is_enabled": True}, if_match=f'"r{version}"'
    )
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in refused.json()["errors"]
    ] == [
        (
            "is_enabled",
            "T-REF-03",
            "TB-0002 is not yet a contract under Step 1. "
            "Activate or void it before AVM-X keeps IFRS 15.",
        ),
        (
            "is_enabled",
            "T-REF-03",
            "AVM-X has a contract that began on 2026-07-01 (TB-0001), before FY2026-P08 starts. "
            "Keep IFRS 15 from a period that starts on or before that date.",
        ),
    ]
    assert _tenant_book(world, "IFRS15")["is_enabled"] is False
    # The contracts go on computing in the book the tenant has.
    assert {str(row["status"]) for row in _computations(world, july)} == {"SUCCEEDED"}
