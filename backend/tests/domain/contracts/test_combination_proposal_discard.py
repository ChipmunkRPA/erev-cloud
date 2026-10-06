"""A proposed combination is discarded with its group (item COMBINATION-PROPOSAL-DISCARD-1; the
supervisor's rulings of 2026-10-02 on lane F-RPS-REG's reading of the proposal's roads and on its
line; 04 T-CON-03, E-95, T-CON-19 "The `COMBINATION` topic", API-R-28; PRD SM-10, ACT-04,
BR-CON-03; 03 REQ-CON-009).

``POST /combination-groups/{id}/discard`` gives up a proposal that was not submitted: the group
goes ``PROPOSED`` → ``VOIDED`` and its record ``DRAFT`` → ``VOIDED`` in one transaction, for any
holder of what the proposal's ``POST`` asked — not its author alone. A correction is a discard
and a new proposal, so the record of a group is edited by nobody: ``PATCH /judgements/{id}``
answers 409 with the sentence that names the road.

Measured before the item (lane F-RPS-REG's reading of 2026-10-02, and this module's first run):
a ``PROPOSED`` group had one command, its submission. A proposal made by mistake was given up by
submitting it and withdrawing the request; one that named a contract since combined elsewhere
could be neither submitted (422) nor given up, and stood ``PROPOSED`` with its ``DRAFT`` record
for good. The one edit was the author's ``PATCH`` of the record, which corrected the record and
not the group row the approver's request is made from.

World: ``support.factories.seat_world`` (AVM-US, USD) with seat contracts of C-09. Maya (Revenue
Accountant) proposes; Ana is a second Revenue Accountant; Cy holds ``contract.create`` and no
``judgement.create``; Marcus (Controller) approves.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, combination_group, exception_item, judgement_record
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, update
from support.db import TestDatabase
from support.factories import SeatWorld, booked_contract, seat_body, seat_line, seat_world
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, get, patch, post, slug

API: Final = "/api/v1"
GROUPS: Final = f"{API}/combination-groups"
JUDGEMENTS: Final = f"{API}/judgements"
# The sentences as the routes answer them (literals: the witnesses are red on a tree that has
# none of the constants).
NOT_EDITED: Final = (
    "This record is the proposal of a combination group and is not edited. To change a proposal "
    "that is not submitted, discard it and propose the combination again."
)
WAITS: Final = "This combination waits for approval. Withdraw its request, or have it rejected."
NOT_DISCARDABLE: Final = "Only a proposed combination that is not submitted can be discarded."
ALREADY_COMBINED: Final = "The contract already belongs to a combination group."
RATIONALE: Final = "One package: both orders serve a single commercial objective."
ORDERS: Final = (
    ("SF-ORD-10417", "30", "108000.00", "2029-08-31"),
    ("SF-ORD-10418", "10", "48000.00", "2027-08-31"),
    ("SF-ORD-10419", "5", "24000.00", "2027-08-31"),
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def order_body(world: SeatWorld, index: int) -> dict[str, Any]:
    external_id, count, price, end = ORDERS[index]
    line = seat_line("O1", seats=count, price=price, start="2026-09-01", end=end)
    return seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )


def drafts(world: SeatWorld, count: int = 2) -> list[UUID]:
    """DRAFT seat contracts of C-09 from 2026-09-01, booked by the domain command."""
    return [
        UUID(
            str(
                booked_contract(world.place, order_body(world, index), activate=False).contract[
                    "id"
                ]
            )
        )
        for index in range(count)
    ]


def proposed(world: SeatWorld, first: UUID, second: UUID) -> dict[str, Any]:
    made = post(
        world.app,
        GROUPS,
        world.place.author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": RATIONALE,
        },
    )
    assert made.status_code == 201, made.text
    group: dict[str, Any] = made.json()
    assert (group["status"], group["proposal"]["status"]) == ("PROPOSED", "DRAFT")
    return group


def member_with(world: SeatWorld, clock: FrozenClock, name: str, role_code: str) -> Actor:
    someone = colleague(world.place.tenant_id, name)
    assign(someone, role_code)
    return enrolled(world.app, clock, someone)


def statuses(world: SeatWorld, group: dict[str, Any]) -> tuple[str, str]:
    """(the group's status, its record's status) as stored."""
    group_status = world.place.scalar(
        select(combination_group.c.status).where(combination_group.c.id == UUID(group["id"]))
    )
    record_status = world.place.scalar(
        select(judgement_record.c.status).where(
            judgement_record.c.id == UUID(group["judgement_record_id"])
        )
    )
    return str(group_status), str(record_status)


def actions_of(world: SeatWorld, object_id: str) -> list[str]:
    rows = world.place.rows(
        select(audit_event.c.action)
        .where(audit_event.c.object_id == UUID(object_id))
        .order_by(audit_event.c.chain_seq)
    )
    return [str(row["action"]) for row in rows]


def test_a_proposal_is_discarded_by_a_holder_who_is_not_its_author(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    """Maya proposes; Ana, who holds what the proposal's POST asks and did not write it,
    discards it: the group is VOIDED and its record VOIDED in one answer, each with its audit
    event; the group reads as history and names no proposal; the two orders are proposed again.
    Before: the route did not exist (404), and a proposal was given up by nobody but through
    its submission."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    group = proposed(seats, first, second)
    ana = member_with(seats, clock, "ana", "revenue_accountant")

    discarded = post(app, f"{GROUPS}/{group['id']}/discard", ana, {})
    assert discarded.status_code == 200, discarded.text
    shown = discarded.json()
    assert (shown["status"], shown["proposal"], shown["member_contract_ids"]) == (
        "VOIDED",
        None,
        [],
    )
    assert statuses(seats, group) == ("VOIDED", "VOIDED")
    assert actions_of(seats, group["id"])[-1] == "combination_group.voided"
    assert actions_of(seats, group["judgement_record_id"])[-1] == "judgement_record.voided"

    listed = get(app, GROUPS, maya, {"status": "VOIDED", "limit": "200"})
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [group["id"]]
    assert get(app, f"{GROUPS}/{group['id']}", maya).json()["status"] == "VOIDED"
    again = proposed(seats, first, second)
    assert again["id"] != group["id"]


@pytest.mark.slow
def test_a_proposal_that_can_no_longer_be_submitted_is_discarded(seats: SeatWorld) -> None:
    """Two proposals share an order; the second is submitted and approved, so the first names a
    contract combined elsewhere and its submission answers 422. It is discarded all the same —
    the discard runs none of the members' checks. Before: it could be neither submitted nor
    given up, and stood PROPOSED with its DRAFT record for good."""
    app, maya = seats.app, seats.place.author
    first, second, third = drafts(seats, 3)
    stuck = proposed(seats, first, second)
    other = proposed(seats, first, third)
    submitted = post(app, f"{GROUPS}/{other['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], seats.marcus)
    assert approved.status_code == 200, approved.text

    refused = post(app, f"{GROUPS}/{stuck['id']}/submit", maya, {})
    assert refused.status_code == 422, refused.text
    assert ALREADY_COMBINED in [error["message"] for error in refused.json()["errors"]]

    discarded = post(app, f"{GROUPS}/{stuck['id']}/discard", maya, {})
    assert discarded.status_code == 200, discarded.text
    assert statuses(seats, stuck) == ("VOIDED", "VOIDED")
    assert statuses(seats, other)[0] == "APPLIED"


def test_a_discard_is_refused_once_the_proposal_is_submitted_and_to_a_repeat(
    seats: SeatWorld,
) -> None:
    """A SUBMITTED group is not discarded — its request is withdrawn or rejected — and a second
    discard of a VOIDED group is refused: 409 on ``status``, each with the sentence of its
    state, and nothing is written."""
    app, maya = seats.app, seats.place.author
    first, second, third = drafts(seats, 3)
    waiting = proposed(seats, first, second)
    submitted = post(app, f"{GROUPS}/{waiting['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    refused = post(app, f"{GROUPS}/{waiting['id']}/discard", maya, {})
    assert refused.status_code == 409, refused.text
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", WAITS)
    assert [error["field"] for error in refused.json()["errors"]] == ["status"]
    assert statuses(seats, waiting) == ("SUBMITTED", "SUBMITTED")

    given_up = proposed(seats, first, third)
    assert post(app, f"{GROUPS}/{given_up['id']}/discard", maya, {}).status_code == 200
    events = actions_of(seats, given_up["id"])
    repeat = post(app, f"{GROUPS}/{given_up['id']}/discard", maya, {})
    assert repeat.status_code == 409, repeat.text
    assert (slug(repeat), repeat.json()["detail"]) == ("invalid-transition", NOT_DISCARDABLE)
    assert actions_of(seats, given_up["id"]) == events


def test_a_discard_asks_what_the_proposal_asked(seats: SeatWorld, clock: FrozenClock) -> None:
    """WHO. The proposal's POST asks ``contract.create`` for the entity of every contract it
    names and ``judgement.create`` for any entity — the record's own writer asks the second —
    and the discard asks the same two. Ana, a Revenue Accountant, holds both: 200. Cy holds the
    first and not the second: the POST answers her 404, and so does the discard, which leaves
    the proposal as it was."""
    app = seats.app
    first, second, third = drafts(seats, 3)
    ana = member_with(seats, clock, "ana", "revenue_accountant")
    cy = member_with(seats, clock, "cy", "service_account")

    by_ana = proposed(seats, first, second)
    discarded = post(app, f"{GROUPS}/{by_ana['id']}/discard", ana, {})
    assert discarded.status_code == 200, discarded.text

    body = {
        "contract_ids": [str(first), str(third)],
        "criterion": "606-10-25-9(b)",
        "rationale": RATIONALE,
    }
    unwritten = post(app, GROUPS, cy, body)
    assert (unwritten.status_code, slug(unwritten)) == (404, "not-found"), unwritten.text
    standing = proposed(seats, first, third)
    refused = post(app, f"{GROUPS}/{standing['id']}/discard", cy, {})
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert statuses(seats, standing) == ("PROPOSED", "DRAFT")


def test_the_record_of_a_group_is_edited_by_nobody(seats: SeatWorld, clock: FrozenClock) -> None:
    """``PATCH /judgements/{id}`` of a draft proposal: 409 with the sentence that names the road,
    for its author as for another preparer, and the record is as proposed. Before: the author's
    edit answered 200 and parted the record's rationale from the group's, which the approver's
    request is made from."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    group = proposed(seats, first, second)
    ana = member_with(seats, clock, "ana", "revenue_accountant")
    record = f"{JUDGEMENTS}/{group['judgement_record_id']}"

    for actor in (maya, ana):
        refused = patch(app, record, actor, {"rationale": "Rewritten by hand."}, if_match=None)
        assert refused.status_code == 409, refused.text
        assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", NOT_EDITED)
    assert get(app, record, maya).json()["rationale"] == RATIONALE
    assert get(app, f"{GROUPS}/{group['id']}", maya).json()["rationale"] == RATIONALE


def test_a_discard_leaves_the_open_suggestion_open(seats: SeatWorld) -> None:
    """A discard gives up the proposal, not the question: the open ``COMBINATION_SUGGESTED`` item
    of the two orders — raised when the second was booked through the product — stays open, to
    be combined again or dismissed (PRD BR-CON-03)."""
    app, maya = seats.app, seats.place.author
    booked = [post(app, f"{API}/contracts", maya, order_body(seats, index)) for index in (0, 1)]
    assert [answer.status_code for answer in booked] == [201, 201], [a.text for a in booked]
    first, second = (UUID(answer.json()["id"]) for answer in booked)

    def suggestions() -> list[tuple[Any, str]]:
        rows = seats.place.rows(
            select(exception_item.c.id, exception_item.c.status)
            .where(exception_item.c.code == "COMBINATION_SUGGESTED")
            .order_by(exception_item.c.id)
        )
        return [(row["id"], str(row["status"])) for row in rows]

    before = suggestions()
    assert [status for _, status in before] == ["OPEN"]
    group = proposed(seats, first, second)
    discarded = post(app, f"{GROUPS}/{group['id']}/discard", maya, {})
    assert discarded.status_code == 200, discarded.text
    assert suggestions() == before


def test_a_proposal_whose_record_is_no_longer_a_draft_is_discarded_and_the_record_left(
    seats: SeatWorld,
) -> None:
    """A workspace's table may hold a PROPOSED group whose record is not a draft: until item
    COMBINATION-PROPOSAL-RECORD-1 the record could be sent for review by hand, and the group
    could then be neither submitted nor given up. The state is written here as rows. The group
    is discarded, and the record — no draft — is left as it is (04 T-CON-19 rev 1.289)."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    group = proposed(seats, first, second)
    record_id = UUID(group["judgement_record_id"])
    context = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(judgement_record)
            .where(judgement_record.c.id == record_id)
            .values(status="SUBMITTED")
        )
    assert statuses(seats, group) == ("PROPOSED", "SUBMITTED")
    events = actions_of(seats, group["judgement_record_id"])

    discarded = post(app, f"{GROUPS}/{group['id']}/discard", maya, {})
    assert discarded.status_code == 200, discarded.text
    assert (discarded.json()["status"], discarded.json()["proposal"]) == ("VOIDED", None)
    assert statuses(seats, group) == ("VOIDED", "SUBMITTED")
    assert actions_of(seats, group["id"])[-1] == "combination_group.voided"
    assert actions_of(seats, group["judgement_record_id"]) == events
