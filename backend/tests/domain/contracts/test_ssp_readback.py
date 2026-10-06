"""The SSP version an obligation was priced from is read back (item PIN-READBACK-1, supervisor
ruling R-116 (d); POLICIES POL-070; ENGINE_SPEC S05-R-03; 05 RCP-15; dev-guide DG-KRN-REG-02; 04
T-CON-11; ASC 606-10-32-43, IFRS 15.88).

The finding. Every computation selected the SSP book and version of every line again — the book by
scope (S05-R-02), the version by date among those approved by then (S05-R-03) — and the version
recorded on the obligation (``obligation_version.ssp_book_version_id``) was never read.
SF-ORD-30201 (O1 30 seats for 36 months, 108,000.00, above the range; O2 10 seats for 12 months,
20,000.00, below it), ACTIVE from 1 March 2026 with 35,718.53 of revenue posted under US-LIST
2026-H1 (2,160.00 / 2,400.00 / 2,640.00 a seat), was re-allocated from 100,571.43 / 27,428.57 to
97,156.63 / 30,843.37 at its next computation — 14 posting intents over the seven open periods —
by an approval that named no contract and showed its approver no figure: a second version of the
book dated 1 February, a first version of a narrower book dated 1 January, or a book of equal
scope whose code sorts first.

The repair. The bundle builder hands the engine, for every obligation that already has a version
in the book of account, the version its own pricing was made from, and the engine prices the
obligation itself from it: the transaction price is not reallocated for later changes in
standalone selling prices. An obligation priced for the first time selects by date as before —
and so does a contract still DRAFT, whose computations are provisional — a modification prices at
the version in force on its date (01-DECISIONS D-18), and an approved SSP override stays a
correction at its event (S06-R-26).

The figures, derived from the two ranges and the NEAREST_BOUND point (POL-072). Under 2026-H1: O1
30 × 2,640.00 = 79,200.00 and O2 10 × 2,160.00 = 21,600.00, so 128,000.00 × 79,200 ÷ 100,800 =
100,571.43 and 27,428.57. Under the later range (1,900.00 / 2,000.00 / 2,100.00): O1 30 ×
2,100.00 = 63,000.00 and O2 at its price inside the range, 20,000.00, so 128,000.00 × 63,000 ÷
83,000 = 97,156.63 and 30,843.37. O1 alone under the later range beside O2 under 2026-H1:
128,000.00 × 63,000 ÷ 84,600 = 95,319.15 and 32,680.85.

Maya (Revenue Accountant, SSP Analyst) prepares; Priya (SSP Approver) and Marcus (Controller, SSP
Approver, Tenant Admin; MFA) approve. The frozen clock reads 12 September 2026; AVM-US has
FY2026-P01 to P09 open.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    combination_group,
    contract_computation,
    contract_version,
    obligation,
    obligation_version,
    subledger_line,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_engine.bundle import InputBundle, OutputBundle
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    SSP_BOOKS,
    SeatWorld,
    activated_contract,
    approved_ssp_version,
    booked_contract,
    computed,
    range_entry,
    seat_body,
    seat_line,
    seat_world,
)
from support.reference import approve, post

GROUPS = "/api/v1/combination-groups"
OBLIGATIONS = "/api/v1/obligations"
SEAT = "AVM-SEAT-MO"
VERSION_BASIS = "ssp.version_basis"  # POL-070: T, override O; pin K
H1 = "US-LIST@v1"  # the version key of US-LIST 2026-H1
LATER_RANGE = ("1900.00", "2000.00", "2100.00")
UNDER_H1 = {"O1": Decimal("100571.43"), "O2": Decimal("27428.57")}
UNDER_LATER = {"O1": Decimal("97156.63"), "O2": Decimal("30843.37")}
O1_OVERRIDDEN = {"O1": Decimal("95319.15"), "O2": Decimal("32680.85")}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def posted_order(world: SeatWorld, external_id: str = "SF-ORD-30201") -> tuple[UUID, UUID]:
    """The two-line order from 1 March 2026, activated and posted; contract id and group id."""
    lines = [
        seat_line("O1", seats="30", price="108000.00", start="2026-03-01", end="2029-02-28"),
        seat_line("O2", seats="10", price="20000.00", start="2026-03-01", end="2027-02-28"),
    ]
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-03-01", lines=lines
    )
    active = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    return UUID(str(active.contract["id"])), UUID(str(active.combination_group["id"]))


def seat_order(world: SeatWorld, external_id: str, seat_count: str, price: str, end: str) -> UUID:
    """A one-line order from 1 September 2026, activated in its own group; the contract id."""
    line = seat_line("O1", seats=seat_count, price=price, start="2026-09-01", end=end)
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )
    active = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    return UUID(str(active.contract["id"]))


def later_version(world: SeatWorld, book_id: str, *, label: str, effective_from: str) -> str:
    """An APPROVED version of ``book_id`` with the later range; its id."""
    return approved_ssp_version(
        world.app,
        world.place.author,
        [world.priya, world.marcus],
        book_id,
        label=label,
        effective_from=effective_from,
        entries=[range_entry(SEAT, *LATER_RANGE, value_basis="AMOUNT")],
    )


def priced(world: SeatWorld, contract_id: UUID) -> dict[str, tuple[Decimal, str]]:
    """Per obligation key of the contract, the allocation and the SSP book version of its latest
    obligation version (the latest computation wins, whatever group it belongs to)."""
    rows = world.place.rows(
        select(
            obligation_version.c.obligation_key,
            obligation_version.c.allocated_amount,
            obligation_version.c.ssp_book_version_id,
        )
        .select_from(
            obligation_version.join(
                contract_version, contract_version.c.id == obligation_version.c.contract_version_id
            )
        )
        .where(obligation_version.c.contract_id == contract_id)
        .order_by(contract_version.c.known_at, contract_version.c.version_no)
    )
    return {
        str(row["obligation_key"]): (
            Decimal(row["allocated_amount"]).quantize(Decimal("0.01")),
            str(row["ssp_book_version_id"]),
        )
        for row in rows
    }


def on_version(amounts: dict[str, Decimal], version_id: str) -> dict[str, tuple[Decimal, str]]:
    return {key: (amount, version_id) for key, amount in amounts.items()}


def ledger(world: SeatWorld, contract_id: UUID) -> tuple[int, Decimal]:
    """The contract's sealed lines and its posted revenue."""
    line = subledger_line
    count = world.place.scalar(
        select(func.count()).select_from(line).where(line.c.contract_id == contract_id)
    )
    revenue = world.place.scalar(
        select(func.coalesce(func.sum(line.c.amount_txn), 0)).where(
            line.c.contract_id == contract_id, line.c.account_role == "REVENUE"
        )
    )
    return int(count), Decimal(revenue)


def intents(output: OutputBundle) -> list[Any]:
    return [intent for book in output.books for intent in book.posting_intents]


def recorded_rows(bundle: InputBundle) -> dict[str, tuple[Any, str, str]]:
    """The read-back rows of the bundle's first book: subject key → (value, level, source)."""
    return {
        policy.subject_key: (dict(policy.value), policy.level, policy.source_ref)
        for policy in bundle.books[0].policies
        if (policy.code, policy.scope) == (VERSION_BASIS, "OBLIGATION")
    }


def narrower_book(world: SeatWorld) -> str:
    """AVM-US-LIST: entity AVM-US and currency USD — one scope member more than US-LIST."""
    created = post(
        world.app,
        SSP_BOOKS,
        world.place.author,
        {
            "code": "AVM-US-LIST",
            "name": "AVM-US list prices",
            "currency": "USD",
            "entity_code": "AVM-US",
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def equal_scope_book(world: SeatWorld) -> str:
    """AAA-LIST: the scope of US-LIST (currency USD) under a code that sorts before it."""
    created = post(
        world.app,
        SSP_BOOKS,
        world.place.author,
        {"code": "AAA-LIST", "name": "AAA list prices", "currency": "USD"},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


@pytest.mark.parametrize(
    ("effective_from", "reaches_march"),
    [("2026-02-01", True), ("2026-10-01", False)],
    ids=["dated before the pricing date", "dated after today (control)"],
)
def test_a_later_version_of_the_book_does_not_reprice_a_posted_order(
    seats: SeatWorld, effective_from: str, reaches_march: bool
) -> None:
    """Form (i): a second version of US-LIST approved on 12 September. Dated 1 February it covers
    the order's pricing date and, selected by date, re-allocated it; dated 1 October it never did
    (the control passes with and without the read-back). The order keeps 2026-H1 and posts
    nothing; an order priced for the first time afterwards takes the version in force on its
    date, so a past effective date keeps its use for what was not yet priced (PRD BR-SSP-02)."""
    contract_id, group_id = posted_order(seats)
    before = priced(seats, contract_id), ledger(seats, contract_id)
    assert before[0] == on_version(UNDER_H1, seats.version_id)
    assert before[1] == (28, Decimal("-35718.53"))

    later = later_version(seats, seats.book_id, label="2026 revised", effective_from=effective_from)
    _, output, _ = computed(seats.place, group_id)

    assert intents(output) == []
    assert (priced(seats, contract_id), ledger(seats, contract_id)) == before

    second, _ = posted_order(seats, "SF-ORD-30202")
    assert priced(seats, second) == (
        on_version(UNDER_LATER, later) if reaches_march else on_version(UNDER_H1, seats.version_id)
    )


def test_a_first_version_of_a_narrower_book_does_not_reprice_a_posted_order(
    seats: SeatWorld,
) -> None:
    """Form (ii): AVM-US-LIST matches one scope member more than US-LIST, so S05-R-02 prefers it;
    its first version, dated 1 January and approved on 12 September by one approver, re-allocated
    the order to the cent as form (i) did. The order keeps the book and version it was priced
    from; the next order of the entity is priced from the narrower book."""
    contract_id, group_id = posted_order(seats)
    before = priced(seats, contract_id), ledger(seats, contract_id)
    narrower = later_version(
        seats, narrower_book(seats), label="2026 entity list", effective_from="2026-01-01"
    )

    _, output, _ = computed(seats.place, group_id)

    assert intents(output) == []
    assert (priced(seats, contract_id), ledger(seats, contract_id)) == before
    assert before[0] == on_version(UNDER_H1, seats.version_id)
    second, _ = posted_order(seats, "SF-ORD-30202")
    assert priced(seats, second) == on_version(UNDER_LATER, narrower)


def test_a_book_of_equal_scope_does_not_reprice_a_posted_order(seats: SeatWorld) -> None:
    """A path that is not a date: AAA-LIST has the scope of US-LIST, and S05-R-02 breaks the tie
    by ascending code. Its first version covers the same dates as 2026-H1; only the code decides.
    The posted order keeps US-LIST; the next order takes the book the rule now selects."""
    contract_id, group_id = posted_order(seats)
    before = priced(seats, contract_id), ledger(seats, contract_id)
    rival = later_version(
        seats, equal_scope_book(seats), label="2026 AAA", effective_from="2026-01-01"
    )

    _, output, _ = computed(seats.place, group_id)

    assert intents(output) == []
    assert (priced(seats, contract_id), ledger(seats, contract_id)) == before
    assert before[0] == on_version(UNDER_H1, seats.version_id)
    second, _ = posted_order(seats, "SF-ORD-30202")
    assert priced(seats, second) == on_version(UNDER_LATER, rival)


def test_a_draft_takes_the_version_in_force_when_it_is_activated(seats: SeatWorld) -> None:
    """The record starts at the activation. SF-ORD-30201 is booked and computed while DRAFT
    under 2026-H1 — a provisional computation that posts nothing (ENGINE_SPEC S02-R-02). A
    version dated 1 February is then approved, as a study is that is finished after its period
    began, and the order is activated: it is priced from the version in force on its date, as
    an order booked after the approval is, and not from the one its draft was shown under. From
    its activation on it keeps that version: a third version dated 15 February (1,700.00 /
    1,800.00 / 1,900.00, which by date would give 96,000.00 / 32,000.00) moves nothing."""
    lines = [
        seat_line("O1", seats="30", price="108000.00", start="2026-03-01", end="2029-02-28"),
        seat_line("O2", seats="10", price="20000.00", start="2026-03-01", end="2027-02-28"),
    ]
    body = seat_body(
        seats.customers["C-09"], external_id="SF-ORD-30201", inception="2026-03-01", lines=lines
    )
    draft = booked_contract(seats.place, body, activate=False)
    contract_id = UUID(str(draft.contract["id"]))
    group_id = UUID(str(draft.combination_group["id"]))
    computed(seats.place, group_id)
    assert priced(seats, contract_id) == on_version(UNDER_H1, seats.version_id)
    assert ledger(seats, contract_id) == (0, Decimal(0))

    later = later_version(seats, seats.book_id, label="2026 revised", effective_from="2026-02-01")
    activated_contract(seats.place, draft)

    assert priced(seats, contract_id) == on_version(UNDER_LATER, later)
    posted = ledger(seats, contract_id)
    assert posted[0] == 28
    approved_ssp_version(
        seats.app,
        seats.place.author,
        [seats.priya, seats.marcus],
        seats.book_id,
        label="2026 revised again",
        effective_from="2026-02-15",
        entries=[range_entry(SEAT, "1700.00", "1800.00", "1900.00", value_basis="AMOUNT")],
    )
    _, output, _ = computed(seats.place, group_id)
    assert intents(output) == []
    assert (priced(seats, contract_id), ledger(seats, contract_id)) == (
        on_version(UNDER_LATER, later),
        posted,
    )


def test_a_combination_keeps_the_version_each_member_was_priced_from(seats: SeatWorld) -> None:
    """The read-back follows the obligation, not the group. SF-ORD-10417 (30 seats, 108,000.00)
    and SF-ORD-10418 (10 seats, 20,000.00), both from 1 September, are posted under 2026-H1, each
    in its own group. A version dated 1 February is approved, and the approved combination then
    forms a group that has no version of its own: its first computation prices both members from
    2026-H1 and allocates what the combination alone gives."""
    first = seat_order(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = seat_order(seats, "SF-ORD-10418", "10", "20000.00", "2027-08-31")
    later_version(seats, seats.book_id, label="2026 revised", effective_from="2026-02-01")

    proposed = post(
        seats.app,
        GROUPS,
        seats.place.author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(seats.app, f"{GROUPS}/{group_id}/submit", seats.place.author, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(seats.app, submitted.json()["approval_request_id"], seats.marcus)
    assert decided.status_code == 200, decided.text
    status = seats.place.scalar(
        select(combination_group.c.status).where(combination_group.c.id == group_id)
    )
    assert str(status) == "APPLIED"

    assert priced(seats, first) == {"O1": (UNDER_H1["O1"], seats.version_id)}
    assert priced(seats, second) == {"O1": (UNDER_H1["O2"], seats.version_id)}
    _, output, _ = computed(seats.place, group_id)
    assert intents(output) == []


def test_an_approved_ssp_override_stays_a_correction_at_its_event(seats: SeatWorld) -> None:
    """An approved override wins over the read-back, and the read-back does not undo it. A
    version dated 1 October prices nothing of the order by date; the approved ``SSP_OVERRIDE``
    names it for O1. The computation that applies it re-allocates from inception and posts the
    difference as a catch-up in September (S06-R-26): 95,319.15 / 32,680.85, +2,053.89. The next
    computation posts nothing — the inception is still priced from 2026-H1, the version recorded
    before the override, and the override's event names the corrected version again."""
    contract_id, group_id = posted_order(seats)
    october = later_version(seats, seats.book_id, label="2026-H2", effective_from="2026-10-01")
    _, output, _ = computed(seats.place, group_id)
    assert intents(output) == []

    o1 = seats.place.scalar(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O1"
        )
    )
    asked = post(
        seats.app,
        f"{OBLIGATIONS}/{o1}/request-ssp-override",
        seats.place.author,
        {
            "ssp_book_version_id": october,
            "justification": "The October list applies to this order by agreement.",
        },
    )
    assert asked.status_code == 200, asked.text
    decided = approve(seats.app, str(asked.json()["approval_request_id"]), seats.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text

    _, output, _ = computed(seats.place, group_id)
    assert len(intents(output)) == 2
    corrected = {
        "O1": (O1_OVERRIDDEN["O1"], october),
        "O2": (O1_OVERRIDDEN["O2"], seats.version_id),
    }
    assert priced(seats, contract_id) == corrected
    assert ledger(seats, contract_id) == (32, Decimal("-37772.42"))  # 35,718.53 + 2,053.89

    _, output, _ = computed(seats.place, group_id)
    assert intents(output) == []
    assert priced(seats, contract_id) == corrected
    assert ledger(seats, contract_id) == (32, Decimal("-37772.42"))


def test_the_read_back_is_stated_where_the_version_is_recorded(seats: SeatWorld) -> None:
    """What a pinned obligation says about its basis. The obligation version keeps the version id
    and label it was priced from (04 T-CON-11); the stored computation's product pin carries no
    SSP row (the row is the obligation's, not the product's); ``pinned_policies`` keeps the
    tenant's option, a GROUP value; and the trace node of the selected SSP names the recorded
    version, which the stored bundle carries for a replay."""
    contract_id, group_id = posted_order(seats)
    later_version(seats, seats.book_id, label="2026 revised", effective_from="2026-02-01")

    bundle, output, _ = computed(seats.place, group_id)

    labels = seats.place.rows(
        select(
            obligation_version.c.obligation_key,
            obligation_version.c.ssp_book_version_id,
            obligation_version.c.ssp_version_label,
        )
        .where(obligation_version.c.contract_id == contract_id)
        .order_by(obligation_version.c.version_no.desc(), obligation_version.c.obligation_key)
        .limit(2)
    )
    assert [
        (row["obligation_key"], str(row["ssp_book_version_id"]), row["ssp_version_label"])
        for row in labels
    ] == [("O1", seats.version_id, "2026-H1"), ("O2", seats.version_id, "2026-H1")]
    latest = seats.place.rows(
        select(contract_version.c.pinned_policies, contract_computation.c.pinned_refs)
        .select_from(
            contract_version.join(
                contract_computation,
                contract_computation.c.id == contract_version.c.contract_computation_id,
            )
        )
        .where(contract_version.c.combination_group_id == group_id)
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )[0]
    assert latest["pinned_policies"][VERSION_BASIS] == {
        "level": "DEFAULT",
        "value": "LATEST_APPROVED_EFFECTIVE_AT_INCEPTION",
        "source_id": "POL-070",
    }
    assert VERSION_BASIS not in latest["pinned_refs"]["products"][SEAT]["obligation_policies"]
    selected = {
        node.id: node.params["version_key"]
        for node in output.books[0].trace.nodes
        if node.measure == "original_ssp_selected"
    }
    assert selected == {
        "original_ssp_selected:SF-ORD-30201/O1:-": H1,
        "original_ssp_selected:SF-ORD-30201/O2:-": H1,
    }
    assert recorded_rows(bundle) == {
        "SF-ORD-30201/O1": ({"recorded": H1}, "O", "RECORDED"),
        "SF-ORD-30201/O2": ({"recorded": H1}, "O", "RECORDED"),
    }
