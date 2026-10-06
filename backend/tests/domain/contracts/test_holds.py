"""Recognition and journal-export holds (04 T-CON-20, E-45, E-46, E-55, §16.1 ``apply-hold``,
``release-hold``, §16.3 ``HOLD_APPLIED``, ``HOLD_RELEASED``; ENGINE_SPEC_B §9.2.12 S09-R-42 to
S09-R-44; 03 REQ-POL-010, REQ-REC-022; BUILD_SPEC CTR-10).

World: ``support.factories.seat_world`` (AVM-US, USD; clock 2026-09-12 12:00 UTC). Maya (Revenue
Accountant) books, applies and releases holds and prepares judgement records; Marcus (Controller;
MFA) reviews them. Activation is the SYSTEM activation of the test factory (BS3-D-19). The
computations run ``erev_engine.compute``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    app_user,
    contract,
    contract_event,
    contract_hold,
    obligation,
    product,
)
from erev_api.domain.contracts import holds as hold_reads
from erev_api.enums import RuleSetKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    SEAT_MO,
    SeatWorld,
    activated_contract,
    booked_contract,
    k09_body,
    open_periods,
    product_with_template,
    seat_body,
    seat_line,
    seat_world,
    step1_criteria,
)
from support.principals import Actor, colleague, enrolled, sign_in
from support.principals import workspace as signed_in
from support.reference import approve, assign, get, patch, post, reject, slug
from support.rows import insert_contract_rows, publish_rule_set

CONTRACTS = "/api/v1/contracts"
JUDGEMENTS = "/api/v1/judgements"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> SeatWorld:
    return seat_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _activated(world: SeatWorld, body: dict[str, Any]) -> UUID:
    booked = booked_contract(world.place, body, activate=False)
    activated_contract(world.place, booked)
    return UUID(str(booked.contract["id"]))


def _holds(world: SeatWorld, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(contract_hold)
        .where(contract_hold.c.contract_id == contract_id)
        .order_by(contract_hold.c.applied_at, contract_hold.c.id)
    )


def _events(world: SeatWorld, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            contract_event.c.id,
            contract_event.c.event_type,
            contract_event.c.origin,
            contract_event.c.payload,
        )
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )


def _revenue(
    world: SeatWorld, contract_id: UUID, key: str, actor: Actor | None = None
) -> dict[str, Decimal]:
    shown = get(
        world.app,
        f"{CONTRACTS}/{contract_id}/schedule",
        actor or world.place.author,
        {"limit": 100},
    )
    assert shown.status_code == 200, shown.text
    return {
        item["period"]["period_key"]: Decimal(item["amount"]["amount"])
        for item in shown.json()["items"]
        if item["obligation_key"] == key and item["schedule_kind"] == "REVENUE"
    }


def test_recognition_hold_freezes_and_catches_up(world: SeatWorld, clock: FrozenClock) -> None:
    maya = world.place.author
    body = seat_body(
        world.customers["C-09"],
        external_id="SF-ORD-10450",
        inception="2026-09-01",
        lines=[
            seat_line("O1", seats="30", price="36000.00", start="2026-09-01", end="2027-08-31"),
            seat_line("O2", seats="10", price="12000.00", start="2026-09-01", end="2027-08-31"),
        ],
    )
    contract_id = _activated(world, body)
    assert _revenue(world, contract_id, "O2")["FY2026-P09"] == Decimal("986.30")

    applied = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/apply-hold",
        maya,
        {
            "hold_type": "recognition",
            "obligation_key": "O2",
            "reason": "Customer disputes the O2 seats.",
        },
        if_match='"s2"',
    )
    assert applied.status_code == 200, applied.text
    assert (applied.json()["on_hold"], applied.json()["head_stream_version"]) == (True, 3)
    (hold,) = _holds(world, contract_id)
    o2 = world.place.scalar(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O2"
        )
    )
    assert (
        str(hold["hold_type"]),
        str(hold["hold_source"]),
        hold["obligation_id"],
        hold["reason"],
        hold["released_at"],
    ) == ("recognition", "MANUAL", o2, "Customer disputes the O2 seats.", None)
    held_event = _events(world, contract_id)[-1]
    assert hold["id"] == hold["applied_event_id"] == held_event["id"]
    assert (str(held_event["event_type"]), held_event["payload"]["obligation_key"]) == (
        "HOLD_APPLIED",
        "O2",
    )
    frozen = _revenue(world, contract_id, "O2")
    # S09-R-43: O2 is frozen at its target of 2026-09-11 (11 of 365 days of 12,000.00).
    assert frozen["FY2026-P09"] == Decimal("361.64")
    assert _revenue(world, contract_id, "O1")["FY2026-P09"] == Decimal("2958.90")

    open_periods(world.app, maya, entity_code="AVM-US", keys=["FY2026-P10"])
    clock.set(datetime(2026, 10, 5, 16, 0, tzinfo=UTC))
    # The session of 12 September has reached its absolute limit (REQ-PLT-004): sign in again.
    maya = signed_in(world.app, maya.member, sign_in(world.app, maya.member.email))
    released = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/release-hold",
        maya,
        {"hold_id": str(hold["id"]), "comment": "Dispute settled with the customer."},
        if_match='"s3"',
    )
    assert released.status_code == 200, released.text
    assert (released.json()["on_hold"], released.json()["head_stream_version"]) == (False, 4)
    (done,) = _holds(world, contract_id)
    release_event = _events(world, contract_id)[-1]
    assert (str(release_event["event_type"]), release_event["payload"]["hold_id"]) == (
        "HOLD_RELEASED",
        str(hold["id"]),
    )
    assert done["released_event_id"] == release_event["id"]
    assert done["released_at"] is not None
    caught_up = _revenue(world, contract_id, "O2", maya)
    # S09-R-44: September stays frozen; October receives the held 624.66 (2,005.48 − 361.64).
    assert (caught_up["FY2026-P09"], caught_up["FY2026-P10"]) == (
        Decimal("361.64"),
        Decimal("1643.84"),
    )


def test_journal_export_hold_listed(world: SeatWorld) -> None:
    maya = world.place.author
    k09 = _activated(world, k09_body(world.customers["C-09"]))
    other = booked_contract(
        world.place,
        seat_body(
            world.customers["C-02"],
            external_id="SF-ORD-10451",
            inception="2026-09-01",
            lines=[
                seat_line("O1", seats="5", price="12000.00", start="2026-09-01", end="2027-08-31")
            ],
        ),
        activate=False,
    )
    held = post(
        world.app,
        f"{CONTRACTS}/{k09}/apply-hold",
        maya,
        {"hold_type": "journal_export", "reason": "Invoice dispute pending with the customer."},
        if_match='"s2"',
    )
    assert held.status_code == 200, held.text
    (hold,) = _holds(world, k09)
    assert (str(hold["hold_type"]), hold["obligation_id"]) == ("journal_export", None)
    listed = get(world.app, CONTRACTS, maya, {"on_hold": "true"})
    assert listed.status_code == 200, listed.text
    assert [(item["id"], item["on_hold"]) for item in listed.json()["items"]] == [(str(k09), True)]
    unheld = get(world.app, CONTRACTS, maya, {"on_hold": "false"})
    assert [item["id"] for item in unheld.json()["items"]] == [str(other.contract["id"])]


# --- Item HOLD-RELEASE-READ-1 (the supervisor's order of 2026-10-02, register index 281; 04
# §16.1 API-S-Contract ``holds``, §16.2 API-S-Obligation ``holds``, rev 1.299): the reads list
# the open holds, each with the id ``release-hold`` takes ------------------------------------------


def _two_seats(world: SeatWorld, external_id: str) -> UUID:
    """An active contract of two obligations, O1 and O2 (head 2)."""
    return _activated(
        world,
        seat_body(
            world.customers["C-09"],
            external_id=external_id,
            inception="2026-09-01",
            lines=[
                seat_line("O1", seats="30", price="36000.00", start="2026-09-01", end="2027-08-31"),
                seat_line("O2", seats="10", price="12000.00", start="2026-09-01", end="2027-08-31"),
            ],
        ),
    )


def _applied(world: SeatWorld, contract_id: UUID, head: int, body: dict[str, Any]) -> Any:
    done = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/apply-hold",
        world.place.author,
        body,
        if_match=f'"s{head}"',
    )
    assert done.status_code == 200, done.text
    return done


def _obligations(world: SeatWorld, contract_id: UUID) -> dict[str, dict[str, Any]]:
    shown = get(world.app, f"{CONTRACTS}/{contract_id}/obligations", world.place.author)
    assert shown.status_code == 200, shown.text
    return {str(item["obligation_key"]): dict(item) for item in shown.json()["items"]}


def test_hold_release_read_1_a_hold_applied_by_a_person_is_listed_with_its_id_and_released_by_it(
    world: SeatWorld,
) -> None:
    """Item HOLD-RELEASE-READ-1, a release blocker. Measured before: API-S-Contract had no member
    for a hold and API-S-Obligation answered ``holds: []`` whatever stood, so no read gave the id
    ``release-hold`` takes — a hold a person applied from a screen had no exit on the screens,
    and a journal-export hold kept its contract's lines out of every journal run. Now a hold of
    the whole contract is listed by the contract — in the answer of the command that applied it
    too — and the hold of one obligation by that obligation; ``id`` is the id of the hold's
    ``HOLD_APPLIED`` event, the release takes it, and the released hold is listed no more. The
    version reads list none: a hold is no fact of a version."""
    app, maya = world.app, world.place.author
    contract_id = _two_seats(world, "SF-ORD-10453")
    path = f"{CONTRACTS}/{contract_id}"
    before = get(app, path, maya).json()
    assert (before["holds"], before["on_hold"]) == ([], False)
    name = world.place.scalar(
        select(app_user.c.display_name).where(app_user.c.id == maya.member.user_id)
    )

    # --- the whole contract: listed by the contract, with the id of its HOLD_APPLIED event ---
    reason = "Invoice dispute pending with the customer."
    whole = _applied(world, contract_id, 2, {"hold_type": "journal_export", "reason": reason})
    (row,) = _holds(world, contract_id)
    assert row["id"] == _events(world, contract_id)[-1]["id"]
    (listed,) = whole.json()["holds"]  # the command's own answer lists it
    assert datetime.fromisoformat(listed.pop("applied_at")) == row["applied_at"]
    assert listed == {
        "id": str(row["id"]),
        "level": "contract",
        "hold_type": "journal_export",
        "hold_source": "MANUAL",
        "reason": reason,
        "applied_by": {"id": str(maya.member.user_id), "kind": "USER", "display_name": name},
        "release_refusal": None,
    }
    shown = get(app, path, maya).json()
    assert (shown["holds"], shown["on_hold"]) == (whole.json()["holds"], True)
    assert [item["holds"] for item in _obligations(world, contract_id).values()] == [[], []]

    # --- one obligation: listed by that obligation, not by the contract, not by the other ---
    one = _applied(
        world,
        contract_id,
        3,
        {"hold_type": "recognition", "obligation_key": "O2", "reason": "Customer disputes O2."},
    )
    assert one.json()["holds"] == shown["holds"]
    o2_row = _holds(world, contract_id)[1]
    held = _obligations(world, contract_id)
    assert held["O1"]["holds"] == []
    assert [
        (item["id"], item["level"], item["hold_type"], item["hold_source"], item["release_refusal"])
        for item in held["O2"]["holds"]
    ] == [(str(o2_row["id"]), "obligation", "recognition", "MANUAL", None)]
    obligation_path = f"/api/v1/obligations/{held['O2']['id']}"
    assert get(app, obligation_path, maya).json()["holds"] == held["O2"]["holds"]
    versions = get(app, f"{obligation_path}/versions", maya).json()["items"]
    assert versions and all(item["holds"] == [] for item in versions)

    # --- released with the id the read gave: listed no more ---
    for head, hold_id, on_hold in (
        (4, shown["holds"][0]["id"], True),  # the hold of O2 still stands
        (5, held["O2"]["holds"][0]["id"], False),
    ):
        released = post(
            app,
            f"{path}/release-hold",
            maya,
            {"hold_id": hold_id, "comment": "Dispute settled with the customer."},
            if_match=f'"s{head}"',
        )
        assert released.status_code == 200, released.text
        assert (released.json()["holds"], released.json()["on_hold"]) == ([], on_hold)
    assert [item["holds"] for item in _obligations(world, contract_id).values()] == [[], []]
    assert get(app, path, maya).json()["holds"] == []


def test_hold_release_read_1_the_hold_of_a_judgement_record_says_why_it_is_not_released_by_hand(
    world: SeatWorld,
) -> None:
    """``release_refusal`` is the sentence ``release-hold`` would answer for the hold, or null
    where the command would take it (04 §16.1 rev 1.299; as API-S-Event ``void_refusal``): the
    SYSTEM hold of a judgement record that waits for its review names that review, and the
    command answers the same sentence; once the review is rejected the member is null and the
    hold is released by hand with the listed id."""
    app, maya = world.app, world.place.author
    contract_id = _activated(world, k09_body(world.customers["C-09"]))
    path = f"{CONTRACTS}/{contract_id}"
    record = _collectibility_record(world, contract_id)
    sent = post(app, f"{JUDGEMENTS}/{record['id']}/submit", maya, {})
    assert sent.status_code == 200, sent.text

    (listed,) = get(app, path, maya).json()["holds"]
    refusal = f"This hold is released by the review of judgement record {record['judgement_no']}."
    assert (
        listed["level"],
        listed["hold_type"],
        listed["hold_source"],
        listed["reason"],
        listed["applied_by"],
        listed["release_refusal"],
    ) == (
        "contract",
        "recognition",
        "SYSTEM",
        f"Judgement record {record['judgement_no']} (COLLECTIBILITY) is not reviewed.",
        {"id": None, "kind": "SYSTEM", "display_name": "System"},
        refusal,
    )
    refused = _released_by_hand(world, contract_id, listed["id"])
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == listed["release_refusal"]

    rejected = reject(app, sent.json()["approval_request_id"], world.marcus, "Not enough.")
    assert rejected.status_code == 200, rejected.text
    (still,) = get(app, path, maya).json()["holds"]
    assert (still["id"], still["release_refusal"]) == (listed["id"], None)
    released = _released_by_hand(world, contract_id, still["id"])
    assert released.status_code == 200, released.text
    assert (released.json()["holds"], released.json()["on_hold"]) == ([], False)


def test_hold_release_read_1_a_reader_of_another_entity_sees_no_hold(
    world: SeatWorld, clock: FrozenClock
) -> None:
    """The holds are read in the entity scope of the obligation's read: with their contract.
    T-CON-20 is RLS-T — a session of another entity SEES the rows of ``contract_hold`` — so the
    reader reads each hold with its contract and with its ``HOLD_APPLIED`` event, both RLS-TE.
    Rob holds Revenue Accountant for another entity alone: the contract and its obligations
    answer 404, and the reader itself, asked in his scope for this contract, answers no hold;
    in the scope of the contract's entity it answers both."""
    app = world.app
    tenant_id = world.place.tenant_id
    contract_id = _two_seats(world, "SF-ORD-10454")
    _applied(world, contract_id, 2, {"hold_type": "journal_export", "reason": "Invoice dispute."})
    _applied(
        world,
        contract_id,
        3,
        {"hold_type": "recognition", "obligation_key": "O2", "reason": "Customer disputes O2."},
    )
    o2 = _obligations(world, contract_id)["O2"]["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        outside = insert_contract_rows(session, tenant_id)
    someone = colleague(tenant_id, "rob")
    assign(someone, "revenue_accountant", entity_ids=[outside.entity_id])
    rob = enrolled(app, clock, someone)
    for path in (
        f"{CONTRACTS}/{contract_id}",
        f"{CONTRACTS}/{contract_id}/obligations",
        f"/api/v1/obligations/{o2}",
    ):
        hidden = get(app, path, rob)
        assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text

    def read(*entities: UUID) -> tuple[int, list[str]]:
        """The rows of T-CON-20 a session of ``entities`` sees, and what the reader answers."""
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=entities)
        with tenant_session(context, read_only=True) as session:
            visible = session.execute(
                select(contract_hold.c.id).where(contract_hold.c.contract_id == contract_id)
            ).all()
            listed = hold_reads.listed_holds(session, [contract_id])
            return len(visible), [str(row["level"]) for row in listed]

    # the table itself hides nothing from the other entity; the reader does
    assert read(outside.entity_id) == (2, [])
    assert read(world.entity_id) == (2, ["contract", "obligation"])


def _collectibility_record(world: SeatWorld, contract_id: UUID) -> dict[str, Any]:
    """A COLLECTIBILITY record of the contract that Maya prepares (DRAFT)."""
    created = post(
        world.app,
        JUDGEMENTS,
        world.place.author,
        {
            "topic": "COLLECTIBILITY",
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "book": "ASC606",
            "conclusion": "Collection remains probable after the credit downgrade.",
            "rationale": "Letter of credit in place.",
            "questionnaire": {"criteria": step1_criteria()},  # R-113 (f): whole at submission
        },
    )
    assert created.status_code == 201, created.text
    return dict(created.json())


def _released_by_hand(world: SeatWorld, contract_id: UUID, hold_id: Any) -> Any:
    head = get(world.app, f"{CONTRACTS}/{contract_id}", world.place.author).json()
    return post(
        world.app,
        f"{CONTRACTS}/{contract_id}/release-hold",
        world.place.author,
        {"hold_id": str(hold_id), "comment": "Released by hand by the preparer."},
        if_match=f'"s{head["head_stream_version"]}"',
    )


def test_system_hold_for_unreviewed_judgement(world: SeatWorld) -> None:
    maya = world.place.author
    contract_id = _activated(world, k09_body(world.customers["C-09"]))
    record = _collectibility_record(world, contract_id)
    submitted = post(world.app, f"{JUDGEMENTS}/{record['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    (hold,) = _holds(world, contract_id)
    # Item STEP1-HOLD-RELEASE-1 (04 T-CON-20 "Judgement holds" rev 1.209): "is not reviewed" —
    # the sentence stays true after a rejected, a withdrawn or a stale-voided review, which
    # "awaits review" did not.
    reason = f"Judgement record {record['judgement_no']} (COLLECTIBILITY) is not reviewed."
    assert (
        str(hold["hold_type"]),
        str(hold["hold_source"]),
        hold["obligation_id"],
        hold["reason"],
        hold["released_at"],
    ) == ("recognition", "SYSTEM", None, reason, None)
    applied = _events(world, contract_id)[-1]
    assert (str(applied["event_type"]), str(applied["origin"])) == ("HOLD_APPLIED", "SYSTEM")
    assert get(world.app, f"{CONTRACTS}/{contract_id}", maya).json()["on_hold"] is True

    approved = approve(world.app, submitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    (released,) = _holds(world, contract_id)
    assert released["released_at"] is not None
    last = _events(world, contract_id)[-1]
    assert (str(last["event_type"]), str(last["origin"]), last["payload"]["comment"]) == (
        "HOLD_RELEASED",
        "SYSTEM",
        f"Judgement record {record['judgement_no']} was reviewed.",
    )
    assert get(world.app, f"{CONTRACTS}/{contract_id}", maya).json()["on_hold"] is False


def test_step1_hold_release_1_a_judgement_hold_is_not_released_by_hand_before_its_review(
    world: SeatWorld,
) -> None:
    """Item STEP1-HOLD-RELEASE-1, the supervisor's addition (04 §16.1 ``release-hold`` rev
    1.209). Measured before it: while her record waited for its review, the preparer released
    the SYSTEM hold that record had placed — one holder of ``contract.create``, alone. The
    release by hand of a judgement record's hold is refused by name while the record is
    SUBMITTED. A rejected and a withdrawn review leave the hold open under the same reason —
    the record is still not reviewed — and then it is released by hand, as before; a record
    sent again after that holds again, and its review releases the hold. The contract's head
    does not move at a refusal."""
    maya = world.place.author
    contract_id = _activated(world, k09_body(world.customers["C-09"]))
    record = _collectibility_record(world, contract_id)
    path = f"{JUDGEMENTS}/{record['id']}"
    reason = f"Judgement record {record['judgement_no']} (COLLECTIBILITY) is not reviewed."
    refusal = f"This hold is released by the review of judgement record {record['judgement_no']}."

    def state() -> list[tuple[str, bool]]:
        return [
            (str(row["reason"]), row["released_at"] is None) for row in _holds(world, contract_id)
        ]

    def head() -> int:
        return int(get(world.app, f"{CONTRACTS}/{contract_id}", maya).json()["head_stream_version"])

    first = post(world.app, f"{path}/submit", maya, {})
    assert first.status_code == 200, first.text
    (hold,) = _holds(world, contract_id)
    held_at = head()
    refused = _released_by_hand(world, contract_id, hold["id"])
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == refusal
    assert (state(), head()) == ([(reason, True)], held_at)

    # A rejected review: the hold stays, under a reason that is still true; now a person ends it.
    rejected = reject(world.app, first.json()["approval_request_id"], world.marcus, "Not enough.")
    assert rejected.status_code == 200, rejected.text
    assert get(world.app, path, maya).json()["status"] == "REJECTED"
    assert (state(), head()) == ([(reason, True)], held_at)
    released = _released_by_hand(world, contract_id, hold["id"])
    assert released.status_code == 200, released.text
    assert (released.json()["on_hold"], state()) == (False, [(reason, False)])

    # Revised and sent again: it holds again; a withdrawn review leaves that hold as well.
    revised = patch(
        world.app, path, maya, {"rationale": "Letter of credit, confirmed."}, if_match=None
    )
    assert revised.status_code == 200, revised.text
    second = post(world.app, f"{path}/submit", maya, {})
    assert second.status_code == 200, second.text
    assert state() == [(reason, False), (reason, True)]
    again = _holds(world, contract_id)[1]
    assert _released_by_hand(world, contract_id, again["id"]).status_code == 409
    withdrawn = post(
        world.app,
        f"/api/v1/approvals/{second.json()['approval_request_id']}/withdraw",
        maya,
        {"comment": "Withdrawn for one more document."},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert get(world.app, path, maya).json()["status"] == "REJECTED"
    assert state() == [(reason, False), (reason, True)]

    # Sent a third time, the open hold answers (no second one); the review releases it.
    back = patch(world.app, path, maya, {"rationale": "Letter of credit, on file."}, if_match=None)
    assert back.status_code == 200, back.text
    third = post(world.app, f"{path}/submit", maya, {})
    assert third.status_code == 200, third.text
    assert state() == [(reason, False), (reason, True)]
    approved = approve(world.app, third.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    assert state() == [(reason, False), (reason, False)]
    last = _events(world, contract_id)[-1]
    assert (str(last["event_type"]), str(last["origin"]), last["payload"]["comment"]) == (
        "HOLD_RELEASED",
        "SYSTEM",
        f"Judgement record {record['judgement_no']} was reviewed.",
    )


def test_step1_hold_release_1_a_record_that_names_the_contract_holds_it_whatever_its_subject(
    world: SeatWorld,
) -> None:
    """Supervisor ruling R-23, second order (04 T-CON-20 "Judgement holds" rev 1.209; 03
    REQ-POL-010 "unreviewed judgement on the contract"). Measured before the fix: a judgement
    record whose subject is a product or a combination group and which names an active contract
    placed no hold — only a record whose SUBJECT was a contract or an obligation did — although
    its review recomputes that contract. The hold follows the record's ``contract_id``: such a
    record holds the contract it names while it waits for its review, the release by hand is
    refused by name, and the review releases the hold. A record that names no contract holds
    nothing."""
    maya = world.place.author
    contract_id = _activated(world, k09_body(world.customers["C-09"]))
    subjects = [
        ("product", world.place.scalar(select(product.c.id).order_by(product.c.code).limit(1))),
        (
            "combination_group",
            world.place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == contract_id)
            ),
        ),
    ]

    def record_of(subject_type: str, subject_id: Any, *, named: bool) -> dict[str, Any]:
        body = {
            "topic": "OTHER",
            "subject_type": subject_type,
            "subject_id": str(subject_id),
            "conclusion": f"A judgement of a {subject_type} for SF-ORD-10417.",
            "rationale": "The terms of SF-ORD-10417 were read with the customer's order form.",
        }
        if named:
            body["contract_id"] = str(contract_id)
        created = post(world.app, JUDGEMENTS, maya, body)
        assert created.status_code == 201, created.text
        return dict(created.json())

    def on_hold() -> bool:
        return bool(get(world.app, f"{CONTRACTS}/{contract_id}", maya).json()["on_hold"])

    for index, (subject_type, subject_id) in enumerate(subjects):
        record = record_of(subject_type, subject_id, named=True)
        assert record["contract_id"] == str(contract_id)
        submitted = post(world.app, f"{JUDGEMENTS}/{record['id']}/submit", maya, {})
        assert submitted.status_code == 200, submitted.text
        found = _holds(world, contract_id)
        assert len(found) == index + 1, subject_type
        reason = f"Judgement record {record['judgement_no']} (OTHER) is not reviewed."
        (hold,) = [row for row in found if row["reason"] == reason]
        assert (str(hold["hold_type"]), str(hold["hold_source"]), hold["released_at"]) == (
            "recognition",
            "SYSTEM",
            None,
        )
        assert on_hold() is True
        refused = _released_by_hand(world, contract_id, hold["id"])
        assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
        assert refused.json()["detail"] == (
            f"This hold is released by the review of judgement record {record['judgement_no']}."
        )
        approved = approve(world.app, submitted.json()["approval_request_id"], world.marcus)
        assert approved.status_code == 200, approved.text
        last = _events(world, contract_id)[-1]
        assert (str(last["event_type"]), str(last["origin"]), last["payload"]["comment"]) == (
            "HOLD_RELEASED",
            "SYSTEM",
            f"Judgement record {record['judgement_no']} was reviewed.",
        )
        assert on_hold() is False

    # A record that names no contract is of no contract: nothing is held, nothing appended.
    appended = len(_events(world, contract_id))
    for subject_type, subject_id in subjects:
        unnamed = record_of(subject_type, subject_id, named=False)
        assert unnamed["contract_id"] is None
        sent = post(world.app, f"{JUDGEMENTS}/{unnamed['id']}/submit", maya, {})
        assert sent.status_code == 200, sent.text
    assert len(_events(world, contract_id)) == appended
    assert len(_holds(world, contract_id)) == len(subjects)
    assert on_hold() is False


def test_user_hold_rule_applies_on_booking(world: SeatWorld) -> None:
    maya = world.place.author
    product_with_template(
        world.app, maya, code="AVM-KIT", name="Clinic starter kit", revenue_category="PRODUCT"
    )
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        version_id, rule_ids = publish_rule_set(
            session,
            tenant_id=world.place.tenant_id,
            kind=RuleSetKind.HOLD,
            code="AVM-HOLDS",
            rules=[
                {
                    "rule_key": "HOLD-KIT",
                    "conditions": [{"field": "product.code", "op": "eq", "value": "AVM-KIT"}],
                    "outputs": {"hold_type": "recognition", "level": "obligation"},
                }
            ],
        )
    body = seat_body(
        world.customers["C-09"],
        external_id="SF-ORD-10452",
        inception="2026-09-03",
        lines=[
            {
                "obligation_key": "O1",
                "product_code": "AVM-KIT",
                "quantity": "100",
                "total_price": {"amount": "10000.00", "currency": "USD"},
            },
            seat_line(
                "O2",
                seats="5",
                price="12000.00",
                start="2026-09-03",
                end="2027-09-02",
                product_code=SEAT_MO,
            ),
        ],
    )
    created = post(world.app, CONTRACTS, maya, body)
    assert created.status_code == 201, created.text
    assert (created.json()["on_hold"], created.json()["head_stream_version"]) == (True, 2)
    assert created.headers["ETag"] == '"s2"'
    contract_id = UUID(str(created.json()["id"]))
    o1 = world.place.scalar(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O1"
        )
    )
    assert [
        (
            str(row["hold_source"]),
            str(row["hold_type"]),
            row["obligation_id"],
            row["rule_set_version_id"],
            row["rule_id"],
            row["reason"],
        )
        for row in _holds(world, contract_id)
    ] == [
        (
            "USER_RULE",
            "recognition",
            o1,
            version_id,
            rule_ids["HOLD-KIT"],
            "Hold rule HOLD-KIT of rule set AVM-HOLDS.",
        )
    ]
    applied = _events(world, contract_id)[-1]
    assert (
        str(applied["event_type"]),
        applied["payload"]["rule_id"],
        applied["payload"]["hold_source"],
    ) == (
        "HOLD_APPLIED",
        str(rule_ids["HOLD-KIT"]),
        "USER_RULE",
    )
