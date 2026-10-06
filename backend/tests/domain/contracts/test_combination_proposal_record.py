"""The proposal of a combination group is the record its command wrote (item
COMBINATION-PROPOSAL-RECORD-1; the supervisor's rulings of 2026-10-02 on lane F-RPS-REG's probe
and line; 04 T-CON-19, T-PLT-19, §16.10 "Subject content"; PRD BR-CON-03; 03 REQ-CON-009).

A ``COMBINATION`` record whose subject is a combination group is that group's proposal: the
combination commands write it — ``POST /combination-groups`` for a combination, ``POST
/combination-groups/{id}/submit`` with ``leave_contract_ids`` for a leave — and it is decided with
its group. A ``COMBINATION`` record of another subject is a record by hand like any other: the
judgement that two orders negotiated as a package were booked as ONE contract (606-10-25-9 (a);
answer key POB-BR-01-ROBOTS-PLATFORM-EXTENDED-WARRANTY, judgement JDG-BR01-COMBINE) names a
contract, no group and no proposal.

Measured before the item, on the route and by this module's first run:

- the group's commands, its answer and the content its approval hashes took "the latest record of
  the topic" for the proposal, so a record somebody else wrote for the group stood in for it: the
  command's own proposal could no longer be submitted (404), a pending request was voided as
  stale when it was approved, and a leave was answered with another record's contracts;
- ``POST /judgements`` wrote such a record for a group (201), and ``POST /judgements/{id}/submit``
  sent the command's own draft for a review of its own (200) — a proposal reviewed there can no
  longer be submitted with its group;
- the audit events of a ``COMBINATION`` record of ANY subject named the contracts of
  ``questionnaire.contract_ids``: a record by hand on the caller's own contract named another
  contract in the trail and not its own, and a list that named no contract answered 500.

World: ``support.factories.seat_world`` (AVM-US, USD) with two seat contracts of C-09. Maya
(Revenue Accountant) proposes and submits; Marcus (Controller) approves. A "record at rest" is a
row written into T-CON-19 directly: what a record made by hand before this item is in a
workspace's table — no route writes one any more.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.audit import contract_key
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, combination_group, judgement_record
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.factories import SeatWorld, booked_contract, seat_body, seat_line, seat_world
from support.reference import approve, get, post, slug
from support.rows import judgement_record_values
from tests.domain.contracts.test_combination import _combine, _current_group

API: Final = "/api/v1"
GROUPS: Final = f"{API}/combination-groups"
JUDGEMENTS: Final = f"{API}/judgements"
# The sentences as the routes answer them (literals: the witnesses are red on a tree that has
# neither constant).
BY_COMMAND: Final = (
    "A combination record of a combination group is written by the combination commands: "
    "propose the combination, or the leave, of its contracts."
)
PROPOSAL_OF_A_GROUP: Final = (
    "This record is the proposal of a combination group. It is decided with its group."
)
PACKAGE: Final = (
    "Robot order and extended warranty order negotiated as a package (606-10-25-9(a)); "
    "booked as one contract."
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


def drafts(world: SeatWorld) -> tuple[UUID, UUID]:
    """Two DRAFT seat contracts of C-09 from 2026-09-01."""
    found: list[UUID] = []
    for external_id, count, price, end in (
        ("SF-ORD-10417", "30", "108000.00", "2029-08-31"),
        ("SF-ORD-10418", "10", "48000.00", "2027-08-31"),
    ):
        line = seat_line("O1", seats=count, price=price, start="2026-09-01", end=end)
        body = seat_body(
            world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
        )
        found.append(UUID(str(booked_contract(world.place, body, activate=False).contract["id"])))
    return found[0], found[1]


def proposed(world: SeatWorld, first: UUID, second: UUID) -> dict[str, Any]:
    """``POST /combination-groups`` by Maya: the PROPOSED group of the two contracts."""
    made = post(
        world.app,
        GROUPS,
        world.place.author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert made.status_code == 201, made.text
    group: dict[str, Any] = made.json()
    assert (group["status"], group["proposal"]["status"]) == ("PROPOSED", "DRAFT")
    assert group["proposal"]["judgement_record_id"] == group["judgement_record_id"]
    return group


def at_rest(world: SeatWorld, group_id: Any, status: str, questionnaire: dict[str, Any]) -> UUID:
    """A ``COMBINATION`` record of the group written into the table directly, with a number that
    sorts after every number of the workspace's series (``JDG-P…``): "the latest of the topic"."""
    row = judgement_record_values(
        world.place.tenant_id,
        topic="COMBINATION",
        subject_type="combination_group",
        subject_id=UUID(str(group_id)),
        status=status,
        conclusion="Combine the orders.",
        rationale="A record made by hand.",
        questionnaire=questionnaire,
    )
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(judgement_record).values(**row))
    return UUID(str(row["id"]))


def records(world: SeatWorld) -> dict[str, dict[str, Any]]:
    """Every judgement record of the workspace by id."""
    rows = world.place.rows(select(judgement_record))
    return {str(row["id"]): row for row in rows}


def by_hand(subject_type: str, subject_id: Any, **more: Any) -> dict[str, Any]:
    return {
        "topic": "COMBINATION",
        "subject_type": subject_type,
        "subject_id": str(subject_id),
        "conclusion": PACKAGE,
        "rationale": "Both orders were negotiated in one meeting and signed on one day.",
        "codification_refs": ["606-10-25-9"],
        **more,
    }


def named_by(world: SeatWorld, record_id: str) -> list[set[str]]:
    """The contracts each audit event of the record names (04 T-PLT-19 "Contract key")."""
    events = world.place.rows(
        select(audit_event.c.detail)
        .where(
            audit_event.c.object_type == "judgement_record",
            audit_event.c.object_id == UUID(record_id),
        )
        .order_by(audit_event.c.chain_seq)
    )
    found: list[set[str]] = []
    for event in events:
        detail = event["detail"]
        one = detail.get(contract_key.CONTRACT_ID)
        found.append({*([] if one is None else [one]), *detail.get(contract_key.CONTRACT_IDS, [])})
    return found


# --- (a) the proposal is the record the command wrote ------------------------------------------


def test_a_record_at_rest_does_not_make_the_proposal_impossible_to_submit(
    seats: SeatWorld,
) -> None:
    """A PROPOSED group and, beside its proposal, a DRAFT record at rest that names a contract
    the workspace does not have. The group is submitted with the proposal its command wrote:
    both orders, the record the group names. Before: 404 — the group's submission read the
    record at rest as the proposal and looked for its contract."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    group = proposed(seats, first, second)
    stray = at_rest(seats, group["id"], "DRAFT", {"action": "JOIN", "contract_ids": [str(uuid4())]})

    submitted = post(app, f"{GROUPS}/{group['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    shown = submitted.json()
    assert (shown["status"], shown["proposal"]["status"]) == ("SUBMITTED", "SUBMITTED")
    assert shown["proposal"]["judgement_record_id"] == group["judgement_record_id"]
    assert sorted(shown["proposal"]["contract_ids"]) == sorted([str(first), str(second)])
    stored = records(seats)
    assert str(stored[group["judgement_record_id"]]["status"]) == "SUBMITTED"
    assert str(stored[str(stray)]["status"]) == "DRAFT"  # evidence beside it: it moves nothing


def test_a_record_at_rest_does_not_change_what_a_pending_request_approves(
    seats: SeatWorld,
) -> None:
    """A SUBMITTED group whose request is pending and, written after it, a SUBMITTED record at
    rest of the same group that names one order alone. Marcus approves what he was shown: the
    combination of both orders is applied, the command's record is reviewed and the record at
    rest is as it was. Before: 409 — the content the approval hashes took the record at rest,
    the request was voided as stale and the record at rest was rejected in the proposal's
    place."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    group = proposed(seats, first, second)
    submitted = post(app, f"{GROUPS}/{group['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["approval_request_id"]
    stray = at_rest(
        seats, group["id"], "SUBMITTED", {"action": "JOIN", "contract_ids": [str(first)]}
    )

    decided = approve(app, request_id, seats.marcus)
    assert decided.status_code == 200, decided.text
    shown = get(app, f"{GROUPS}/{group['id']}", maya)
    assert shown.status_code == 200, shown.text
    assert (shown.json()["status"], sorted(shown.json()["member_contract_ids"])) == (
        "APPLIED",
        sorted([str(first), str(second)]),
    )
    stored = records(seats)
    assert str(stored[group["judgement_record_id"]]["status"]) == "REVIEWED"
    assert str(stored[str(stray)]["status"]) == "SUBMITTED"


@pytest.mark.slow
def test_a_leave_is_decided_on_the_record_its_submission_wrote(seats: SeatWorld) -> None:
    """An APPLIED group of two orders and a DRAFT record at rest that would separate the first.
    Maya submits the leave of the SECOND order: the group's answer states that leave — the
    record the submission wrote, SUBMITTED — and its approval separates the second order alone.
    Before: the answer stated the record at rest (the first order, DRAFT), the latest of the
    topic."""
    app, maya = seats.app, seats.place.author
    first, second, group_id = _combine(seats)
    stray = at_rest(seats, group_id, "DRAFT", {"action": "LEAVE", "contract_ids": [str(first)]})

    requested = post(
        app,
        f"{GROUPS}/{group_id}/submit",
        maya,
        {
            "leave_contract_ids": [str(second)],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-10418 was combined with the wrong order.",
        },
    )
    assert requested.status_code == 200, requested.text
    proposal = requested.json()["proposal"]
    assert (proposal["action"], proposal["status"], proposal["contract_ids"]) == (
        "LEAVE",
        "SUBMITTED",
        [str(second)],
    )
    assert proposal["judgement_record_id"] != str(stray)

    approved = approve(app, requested.json()["approval_request_id"], seats.marcus)
    assert approved.status_code == 200, approved.text
    assert _current_group(seats, first) == group_id
    assert _current_group(seats, second) != group_id
    stored = records(seats)
    assert str(stored[proposal["judgement_record_id"]]["status"]) == "REVIEWED"
    assert str(stored[str(stray)]["status"]) == "DRAFT"


# --- (b) a group's record is the commands'; a contract's stays a record by hand ----------------


def test_a_combination_record_of_a_group_is_not_written_by_hand(seats: SeatWorld) -> None:
    """``POST /judgements`` with topic ``COMBINATION`` and a combination group as its subject —
    a proposed group, and the singleton group of a contract — answers 422 on ``topic`` with the
    sentence that names the commands, and stores nothing. Another topic on the group is taken as
    before, and the command writes its record as before. Before: 201 for each."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    group = proposed(seats, first, second)
    singleton = seats.place.scalar(
        select(combination_group.c.id)
        .where(combination_group.c.is_singleton.is_(True), combination_group.c.status == "APPLIED")
        .limit(1)
    )
    before = sorted(records(seats))

    for subject_id in (group["id"], singleton):
        refused = post(app, JUDGEMENTS, maya, by_hand("combination_group", subject_id))
        assert refused.status_code == 422, refused.text
        assert slug(refused) == "validation-failed"
        (error,) = refused.json()["errors"]
        assert (error["field"], error["message"]) == ("topic", BY_COMMAND)
    assert sorted(records(seats)) == before

    plain = post(
        app,
        JUDGEMENTS,
        maya,
        {**by_hand("combination_group", group["id"]), "topic": "ESTIMATE_VS_ERROR"},
    )
    assert plain.status_code == 201, plain.text
    written = records(seats)[group["judgement_record_id"]]
    assert (str(written["topic"]), str(written["subject_type"])) == (
        "COMBINATION",
        "combination_group",
    )


def test_a_combination_record_of_a_contract_names_its_own_contract(seats: SeatWorld) -> None:
    """The answer key's record (POB-BR-01, JDG-BR01-COMBINE): topic ``COMBINATION``, subject the
    CONTRACT — two orders booked as one contract. It is written by hand as before (201) and
    read as any record of its contract. Its audit events name ITS contract, whatever its
    questionnaire lists: before, they named the contract of ``questionnaire.contract_ids`` — the
    other order — and not its own, so a record by hand on the caller's own contract wrote into
    the trail of another."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    made = post(
        app,
        JUDGEMENTS,
        maya,
        by_hand("contract", first, questionnaire={"contract_ids": [str(second)]}),
    )
    assert made.status_code == 201, made.text
    record = made.json()
    assert (record["topic"], record["subject_type"], record["contract_id"]) == (
        "COMBINATION",
        "contract",
        str(first),
    )
    assert named_by(seats, record["id"]) == [{str(first)}]
    assert get(app, f"{JUDGEMENTS}/{record['id']}", maya).json()["conclusion"] == PACKAGE


def test_a_list_on_a_contracts_record_is_evidence(seats: SeatWorld) -> None:
    """A ``COMBINATION`` record of a contract whose questionnaire lists something that is no
    contract id: evidence, taken as written (201), and the record's audit event names its
    contract. Before: 500 — the list was parsed for the audit event's contracts."""
    app, maya = seats.app, seats.place.author
    first, _ = drafts(seats)
    made = post(
        app,
        JUDGEMENTS,
        maya,
        by_hand("contract", first, questionnaire={"contract_ids": ["the robot order"]}),
    )
    assert made.status_code == 201, made.text
    assert named_by(seats, made.json()["id"]) == [{str(first)}]


# --- the proposal is decided with its group ------------------------------------------------------


def test_the_proposal_of_a_group_is_not_submitted_by_hand(seats: SeatWorld) -> None:
    """``POST /judgements/{id}/submit`` of the draft a combination command wrote: 409 with the
    sentence that says where it is decided, and the record stays DRAFT. The group is then
    submitted as before. Before: 200 — the record went for a review of its own, and a proposal
    reviewed there can no longer be submitted with its group."""
    app, maya = seats.app, seats.place.author
    first, second = drafts(seats)
    group = proposed(seats, first, second)
    record_id = group["judgement_record_id"]

    refused = post(app, f"{JUDGEMENTS}/{record_id}/submit", maya, {"comment": "Review"})
    assert refused.status_code == 409, refused.text
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", PROPOSAL_OF_A_GROUP)
    assert str(records(seats)[record_id]["status"]) == "DRAFT"

    submitted = post(app, f"{GROUPS}/{group['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["proposal"]["status"] == "SUBMITTED"
