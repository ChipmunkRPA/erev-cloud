"""The void of an event is for a fact that was captured wrongly (04 §16.3 "Voids on this route",
rev 1.231; dev-guide DG-KRN-EVT-02 rev 1.222; item EVT-VOID-OWN-COMMANDS-1; controls CTL-007,
CTL-013, CTL-046; BUILD_SPEC CTR-5).

``POST /events/{id}/request-void`` took every event type but a void, the Step 1 status events and
an applied manual adjustment, under the ``MANUAL_EVENT`` approval: one step, ``event.approve``, no
stored preview. Measured through the product before the rule: the approved void of an applied
``CONTRACT_AMENDED`` took O1's allocation of K-02 from 233,273.47 back to 240,000.00 while the
modification still read ``APPLIED``; the void of an ``ESTIMATE_CHANGED`` took K-06 from 51,750.00
back to 57,500.00 while the estimate version still read ``APPROVED``; the void of a
``CONTRACT_BOOKED`` or a ``REGROUPED`` left the computation ``FAILED``; the void of a
``CONTRACT_VOIDED`` had the engine compute a voided contract as a live one.

Each test names types that have a command of their own. The void is refused by name with nothing
stored, and what the command's own object says still agrees with what the contract computes.

DB-bound. The worlds are those of the sibling modules of each command.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
import test_estimates as ests
import test_modifications as mods
import test_regroup as regroups
import test_void as voids
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    contract,
    contract_computation,
    contract_event,
    contract_hold,
    event_submission,
    obligation,
    obligation_version,
)
from erev_api.domain.contracts import events as contract_events
from erev_api.enums import ContractEventType
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from support.db import TestDatabase
from support.factories import (
    K02World,
    Workspace,
    activated_contract,
    booked_contract,
    computed,
    k02_world,
    k09_body,
    k11_world,
    seat_world,
)
from support.principals import Actor
from support.reference import approve, assign, fields, get, gl_account, post, slug
from support.rows import contract_event_values
from support.worlds import K01, approved_manual_events, k01_pellworth

CONTRACTS = "/api/v1/contracts"
VOID = {"reason_code": "CREATED_IN_ERROR", "comment": "Recorded in error."}
MODIFICATION = (
    "An applied modification is not voided as an event. Record a modification that reverses it."
)
ESTIMATE = "An applied estimate change is not voided as an event. Submit a new estimate version."
BOOKING = "A booking is not voided as an event. Replace the draft, or void the contract."
REGROUP = "A regroup is not voided as an event. Regroup the obligations back."
CONTRACT_VOID = "A contract void is not voided as an event. A voided contract stays voided."
HOLD = "A hold is not voided as an event. Release the hold."
RELEASE = "The release of a hold is not voided as an event. Apply the hold again."
ATTRIBUTES = (
    "An attribute change is not voided as an event. Record a further attribute change, or "
    "request an SSP override."
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _written(place: Workspace) -> tuple[int, ...]:
    """What a refused void leaves as it was: submissions, requests, events and computations."""
    return tuple(
        int(place.scalar(select(func.count()).select_from(table)))
        for table in (event_submission, approval_request, contract_event, contract_computation)
    )


def _allocated(place: Workspace, contract_id: UUID) -> dict[str, Decimal]:
    """The allocation in force per obligation: the latest ASC 606 version's."""
    rows = place.rows(
        select(obligation_version.c.obligation_key, obligation_version.c.allocated_amount)
        .where(
            obligation_version.c.contract_id == contract_id,
            obligation_version.c.book_code == "ASC606",
        )
        .order_by(obligation_version.c.version_no)
    )
    return {str(row["obligation_key"]): Decimal(str(row["allocated_amount"])) for row in rows}


def _refused(app: FastAPI, actor: Actor, event_id: Any, sentence: str) -> None:
    refused = post(app, f"/api/v1/events/{event_id}/request-void", actor, VOID)
    # the status first: without the rule the request is stored and answered 201
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "invalid-transition"
    assert refused.json()["detail"] == sentence
    assert fields(refused) == [("event_type", "API-R-30")]
    assert [error["message"] for error in refused.json()["errors"]] == [sentence]


def _seat_add_applied(
    world: K02World, runtime: JobRuntime, clock: FrozenClock
) -> tuple[UUID, str, dict[str, Any]]:
    """K-02 with the WLD-X-06 seat add applied through its commands: the contract, the
    modification and its ``CONTRACT_AMENDED``."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = mods._k02_contract(world)
    created = mods._create(world, contract_id, mods._upgrade_body())
    mods._classify(world, created["id"])
    mods._preview(world, created["id"], runtime)
    request_id = mods._submit(world, created["id"])
    clock.advance(timedelta(minutes=1))
    decided = approve(world.app, request_id, world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    (amended,) = mods._events(world, contract_id, ContractEventType.CONTRACT_AMENDED)
    clock.advance(timedelta(minutes=1))
    return contract_id, str(created["id"]), amended


def test_evt_void_own_commands_1_an_applied_modification_is_not_voided_as_an_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """An applied modification is undone by a modification, which is classified, previewed and
    approved. Its ``CONTRACT_AMENDED`` is not voided: the modification would still read
    ``APPLIED`` while the contract computed as if it had never been."""
    world = k02_world(app, keyring, clock, files)
    place, maya = world.place, world.place.author
    booked_at = Decimal("240000.00")
    contract_id, modification_id, amended = _seat_add_applied(world, runtime, clock)
    applied = _allocated(place, contract_id)
    assert applied["O1"] != booked_at and set(applied) == {"O1", "O2"}  # the seat add is in force
    before = _written(place)

    _refused(app, maya, amended["id"], MODIFICATION)

    assert _written(place) == before
    # the modification's own object and what the contract computes still agree
    shown = get(app, f"{mods.MODIFICATIONS}/{modification_id}", maya)
    assert (shown.status_code, shown.json()["status"]) == (200, "APPLIED"), shown.text
    assert str(mods._row(world, modification_id)["applied_event_id"]) == str(amended["id"])
    assert _allocated(place, contract_id) == applied


def test_evt_void_own_commands_1_an_applied_estimate_change_is_not_voided_as_an_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """An approved estimate version is replaced by a new version, which is previewed and
    approved. Its ``ESTIMATE_CHANGED`` is not voided: the version would still read ``APPROVED``
    while the contract computed the earlier estimate."""
    world = ests.k06_world(app, keyring, clock, files)
    place, maya = world.place, world.place.author
    k06 = ests._k06_with_v1(world)
    first = _allocated(place, k06.contract_id)
    second = post(app, f"{ests.ESTIMATES}/{k06.estimate_id}/versions", maya, ests._v2_body())
    assert second.status_code == 201, second.text
    version_id = str(second.json()["id"])
    preview = post(app, f"{ests.VERSIONS}/{version_id}/preview", maya, {})
    assert preview.status_code == 202, preview.text
    ests._work(place, UUID(preview.json()["id"]), runtime)
    decided = approve(app, ests._submitted(world, version_id), world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    _, changed = ests._estimate_events(world, k06.contract_id)
    estimated = _allocated(place, k06.contract_id)
    assert estimated != first  # the second version is in force
    clock.advance(timedelta(minutes=1))
    before = _written(place)

    _refused(app, maya, changed["id"], ESTIMATE)

    assert _written(place) == before
    shown = get(app, f"{ests.VERSIONS}/{version_id}", maya)
    assert (shown.status_code, shown.json()["status"]) == (200, "APPROVED"), shown.text
    assert str(changed["id"]) in [str(value) for value in shown.json()["applied_event_ids"]]
    assert _allocated(place, k06.contract_id) == estimated


def test_evt_void_own_commands_1_a_booking_and_a_regroup_are_not_voided_as_events(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A booking is replaced (``replace-draft``) or its contract voided; a regroup is undone by a
    regroup. Voided as events, each left the computation of its contract ``FAILED``."""
    world = k02_world(app, keyring, clock, files)
    place, maya = world.place, world.place.author
    source_id, source_group = regroups._draft(world, "SF-ORD-10002")
    target_id, target_group = regroups._draft(world, "SF-ORD-10003", lines="one")
    computed(place, source_group)
    computed(place, target_group)
    moved = post(
        app,
        f"{CONTRACTS}/{source_id}/regroup",
        maya,
        {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "Same order."},
    )
    assert moved.status_code == 201, moved.text
    (booking,) = regroups._events(world, source_id, ContractEventType.CONTRACT_BOOKED)
    (moved_out,) = regroups._events(world, source_id, ContractEventType.REGROUPED)
    (moved_in,) = regroups._events(world, target_id, ContractEventType.REGROUPED)
    clock.advance(timedelta(minutes=1))
    before = _written(place)

    _refused(app, maya, booking["id"], BOOKING)
    _refused(app, maya, moved_out["id"], REGROUP)
    _refused(app, maya, moved_in["id"], REGROUP)

    assert _written(place) == before
    statuses = place.rows(
        select(contract_computation.c.status).where(
            contract_computation.c.id.in_(
                select(contract.c.latest_computation_id).where(
                    contract.c.id.in_([source_id, target_id])
                )
            )
        )
    )
    assert [str(row["status"]) for row in statuses] == ["SUCCEEDED", "SUCCEEDED"]


def test_evt_void_own_commands_1_a_contract_void_is_not_voided_as_an_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A contract void takes two steps and posts its reversal; nothing undoes it. Voided as an
    event under one step, it had the engine write the versions of a live contract while the
    header stayed ``VOIDED``."""
    world = k11_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    place, maya = world.place, world.place.author
    contract_id, _group_id, _request = voids._void_and_approve_two_steps(world, clock)
    voided = voids._events(world, contract_id)[-1]
    assert str(voided["event_type"]) == "CONTRACT_VOIDED"
    versions = _allocated(place, contract_id)
    clock.advance(timedelta(minutes=1))
    before = _written(place)

    _refused(app, maya, voided["id"], CONTRACT_VOID)

    assert _written(place) == before
    shown = get(app, f"{CONTRACTS}/{contract_id}", maya)
    assert (shown.status_code, shown.json()["status"]) == (200, "VOIDED"), shown.text
    assert _allocated(place, contract_id) == versions


def test_evt_void_own_commands_1_a_hold_and_an_attribute_change_are_not_voided_as_events(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A hold is released and a release is undone by a new hold; an attribute change is followed
    by another, each through its own command."""
    world = seat_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    place, maya = world.place, world.place.author
    booked = booked_contract(place, k09_body(world.customers["C-09"]), activate=False)
    activated_contract(place, booked)
    contract_id = UUID(str(booked.contract["id"]))
    held = post(
        app,
        f"{CONTRACTS}/{contract_id}/apply-hold",
        maya,
        {"hold_type": "recognition", "obligation_key": "O1", "reason": "Customer disputes O1."},
        if_match='"s2"',
    )
    assert held.status_code == 200, held.text
    hold_id = place.scalar(
        select(contract_hold.c.id).where(contract_hold.c.contract_id == contract_id)
    )
    released = post(
        app,
        f"{CONTRACTS}/{contract_id}/release-hold",
        maya,
        {"hold_id": str(hold_id), "comment": "Dispute settled with the customer."},
        if_match='"s3"',
    )
    assert released.status_code == 200, released.text
    gl_account(
        app,
        maya,
        code="4020",
        name="Revenue - enterprise subscriptions",
        account_type="REVENUE",
        normal_balance="C",
    )
    changed = post(
        app,
        f"{CONTRACTS}/{contract_id}/events",
        maya,
        {
            "events": [
                {
                    "event_type": "LINE_ATTRIBUTES_CHANGED",
                    "effective_date": "2026-09-12",
                    "obligation_key": "O1",
                    "payload": {
                        "obligation_key": "O1",
                        "changes": {"account_overrides": {"REVENUE": "4020"}},
                        "diff": {"account_overrides": {"before": {}, "after": {"REVENUE": "4020"}}},
                    },
                }
            ]
        },
        if_match='"s4"',
    )
    assert changed.status_code == 201, changed.text
    approved = approve(app, changed.json()["approval_request_id"], world.priya)
    assert approved.status_code == 200, approved.text
    events = {
        str(row["event_type"]): row["id"]
        for row in place.rows(
            select(contract_event.c.event_type, contract_event.c.id).where(
                contract_event.c.contract_id == contract_id
            )
        )
    }
    clock.advance(timedelta(minutes=1))
    before = _written(place)

    _refused(app, maya, events["HOLD_APPLIED"], HOLD)
    _refused(app, maya, events["HOLD_RELEASED"], RELEASE)
    _refused(app, maya, events["LINE_ATTRIBUTES_CHANGED"], ATTRIBUTES)

    assert _written(place) == before


def test_evt_void_own_commands_1_a_stored_void_is_stale_at_its_approval(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 T-CON-24 "Checked again where it is appended". A void requested before the rule — or
    built below the route — waits as a stored submission; its approval reads the same list, so
    the request is voided as stale and nothing is appended. The stored void is made here as the
    route made it before the rule (the allow-list switched off for the one request)."""
    world = k02_world(app, keyring, clock, files)
    place, maya = world.place, world.place.author
    contract_id, modification_id, amended = _seat_add_applied(world, runtime, clock)
    applied = _allocated(place, contract_id)
    with monkeypatch.context() as before_the_rule:
        before_the_rule.setattr(contract_events, "VOIDABLE_TYPES", frozenset(ContractEventType))
        requested = post(app, f"/api/v1/events/{amended['id']}/request-void", maya, VOID)
    assert requested.status_code == 201, requested.text
    stored = requested.json()
    head = place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    clock.advance(timedelta(minutes=1))

    stale = approve(app, stored["approval_request_id"], world.priya)

    # the status first: without the check the void is appended and the allocation goes back
    assert stale.status_code == 409, stale.text
    assert slug(stale) == "stale-approval"
    request = place.rows(
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(stored["approval_request_id"])
        )
    )[0]
    assert (str(request["status"]), str(request["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    submission = place.rows(
        select(event_submission.c.status).where(
            event_submission.c.id == UUID(stored["event_submission_id"])
        )
    )[0]
    assert str(submission["status"]) == "VOIDED"
    assert not place.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(stored["approval_request_id"])
        )
    )
    assert head == place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    assert mods._events(world, contract_id, ContractEventType.EVENT_VOIDED) == []
    assert str(mods._row(world, modification_id)["status"]) == "APPLIED"
    assert _allocated(place, contract_id) == applied


# --- API-S-Event ``void_refusal`` (04 rev 1.273; the supervisor's ruling of 2026-10-02) ----------


def _raw_events(
    place: Workspace,
    contract_id: UUID,
    entity_id: UUID,
    after: int,
    kinds: Sequence[tuple[ContractEventType, Sequence[UUID]]],
) -> None:
    """One stored row per kind after stream version ``after``, written below the routes: T-CON-05
    takes every E-03 literal, and no command of 1.0 records some of them."""
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        # DB-08 (EREV-EVT-001): an event is stored at or below its contract's head, which the
        # append command raises first.
        session.execute(
            update(contract)
            .where(contract.c.id == contract_id)
            .values(head_stream_version=after + len(kinds), row_version=contract.c.row_version + 1)
        )
        for offset, (kind, obligation_ids) in enumerate(kinds, start=1):
            session.execute(
                insert(contract_event).values(
                    **contract_event_values(
                        place.tenant_id,
                        contract_id=contract_id,
                        contracting_entity_id=entity_id,
                        stream_version=after + offset,
                        event_type=kind.value,
                        effective_date=date(2026, 9, 1),
                        obligation_ids=list(obligation_ids),
                    )
                )
            )


def _route_answer(app: FastAPI, actor: Actor, event_id: Any) -> str | None:
    """What ``POST /events/{id}/request-void`` answers: None when it takes the event (201), the
    sentence of its 409 otherwise."""
    asked = post(app, f"/api/v1/events/{event_id}/request-void", actor, VOID)
    if asked.status_code == 201:
        return None
    assert (asked.status_code, slug(asked)) == (409, "invalid-transition"), asked.text
    return str(asked.json()["detail"])


def test_api_s_event_void_refusal_is_what_the_void_route_answers_for_every_type(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 API-S-Event ``void_refusal`` (rev 1.273; §16.3 "Voids on this route"): the reads of an
    event answer the sentence ``POST /events/{id}/request-void`` would answer, or null where the
    route takes the event — for every literal of E-03, read from the enumeration, so that a type
    E-03 gains is compared as well; for a voided event; and for a void. A screen then offers the
    void where it can be requested and keeps no list of voidable types of its own.

    The stream is one draft's: its booking, a memo recorded and voided through the product, and
    one stored row of every other literal, written below the routes."""
    world = seat_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # event.approve (PRD §2.5)
    place, maya = world.place, world.place.author
    booked = booked_contract(place, k09_body(world.customers["C-09"]), activate=False)
    contract_id = UUID(str(booked.contract["id"]))
    entity_id = UUID(str(booked.contract["contracting_entity_id"]))
    (obligation_id,) = [UUID(str(row["id"])) for row in booked.obligations]
    events_path = f"{CONTRACTS}/{contract_id}/events"

    # A fact recorded and voided through the product: a voided event and its void.
    memo = {
        "event_type": "MEMO_UPDATED",
        "effective_date": "2026-09-01",
        "payload": {"memo_1": "Recorded on the wrong contract"},
    }
    recorded = post(app, events_path, maya, {"events": [memo]}, if_match='"s1"')
    assert recorded.status_code == 201, recorded.text
    voided_id = str(recorded.json()["events"][0]["id"])
    asked = post(app, f"/api/v1/events/{voided_id}/request-void", maya, VOID)
    assert asked.status_code == 201, asked.text
    decided = approve(app, asked.json()["approval_request_id"], world.priya)
    assert decided.status_code == 200, decided.text
    (void,) = place.rows(
        select(contract_event.c.id).where(contract_event.c.supersedes_event_id == UUID(voided_id))
    )
    void_id = str(void["id"])

    # Every other literal as a stored row; a delivery and a hold name the obligation, so that
    # its own event list holds one event the route takes and one it refuses.
    naming = {ContractEventType.DELIVERY_RECORDED, ContractEventType.HOLD_APPLIED}
    stored = {ContractEventType.CONTRACT_BOOKED, ContractEventType.EVENT_VOIDED}
    _raw_events(
        place,
        contract_id,
        entity_id,
        3,
        [
            (kind, [obligation_id] if kind in naming else [])
            for kind in ContractEventType
            if kind not in stored
        ],
    )
    rows = place.rows(
        select(contract_event.c.id, contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    live = {
        ContractEventType(str(getattr(row["event_type"], "value", row["event_type"]))): str(
            row["id"]
        )
        for row in rows
        if str(row["id"]) != voided_id
    }
    assert set(live) == set(ContractEventType)  # a literal E-03 gains is compared as well

    shown_list = get(app, events_path, maya, {"limit": 100})
    assert shown_list.status_code == 200, shown_list.text
    listed = {str(item["id"]): item["void_refusal"] for item in shown_list.json()["items"]}
    assert set(listed) == {str(row["id"]) for row in rows}
    compared: dict[ContractEventType, tuple[str | None, str | None]] = {}
    for kind, event_id in live.items():
        shown = get(app, f"/api/v1/events/{event_id}", maya)
        assert shown.status_code == 200, shown.text
        member = shown.json()["void_refusal"]
        assert listed[event_id] == member, kind
        compared[kind] = (member, _route_answer(app, maya, event_id))
    assert {kind: member for kind, (member, _) in compared.items()} == {
        kind: route for kind, (_, route) in compared.items()
    }
    # null for the twelve fact-capture types and for no other
    assert {kind for kind, (member, _) in compared.items() if member is None} == set(
        contract_events.VOIDABLE_TYPES
    )

    # A void and the event it voided: one sentence, the route's.
    for event_id in (void_id, voided_id):
        assert listed[event_id] == contract_events.NOT_VOIDABLE
        assert _route_answer(app, maya, event_id) == contract_events.NOT_VOIDABLE

    # The obligation's own list answers the member as the event does.
    of_obligation = get(app, f"/api/v1/obligations/{obligation_id}/events", maya, {"limit": 100})
    assert of_obligation.status_code == 200, of_obligation.text
    named = {str(item["id"]): item["void_refusal"] for item in of_obligation.json()["items"]}
    assert {live[kind] for kind in naming} <= set(named)
    assert all(listed[event_id] == refusal for event_id, refusal in named.items())
    assert named[live[ContractEventType.DELIVERY_RECORDED]] is None
    assert named[live[ContractEventType.HOLD_APPLIED]] == HOLD


def test_api_s_event_is_whole_on_the_obligations_route_for_an_applied_manual_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 API-S-Event rev 1.273 (the supervisor's ruling of 2026-10-02): ``GET
    /obligations/{id}/events`` — the route the Events panel of an obligation reads — answers an
    event WHOLE, as ``GET /events/{id}`` answers it: one model, one builder. Measured before, for
    an applied manual event: the route answered neither ``prepared_by`` nor ``approved_by``, so
    the panel could show the SYSTEM principal that appended the event and neither of its two
    people (PRD J-08-AC-3; control CTL-009).

    WLD-K-01 through 30 January 2026: Maya records O2's progress with its evidence and Priya
    approves. Every event on the route of each obligation is compared with the events resource's
    answer for the same event. One member keeps a rule of this route: ``obligation_keys`` also
    names the obligation of an event that names it only in its payload ([J] L4-2-Q-7) — here
    the invoice the world appends below the routes."""
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 30))
    assign(world.priya.member, "revenue_reviewer")  # event.approve (PRD §2.5)
    place, maya = world.place, world.maya
    contract_id = UUID(str(world.contracts[K01].contract["id"]))
    progress = {
        "event_type": "PROGRESS_RECORDED",
        "effective_date": "2026-01-31",
        "payload": {
            "obligation_key": "O2",
            "cumulative_progress_ratio": "0.40",
            "measure": "OUTPUT_PERCENT",
        },
    }
    applied = approved_manual_events(place, world.priya, contract_id, progress)
    (event,) = applied["events"]  # as ``GET /events/{id}`` answers it

    listed = get(app, f"{CONTRACTS}/{contract_id}/events", maya, {"limit": 100})
    assert listed.status_code == 200, listed.text
    on_contract = {str(item["id"]): item for item in listed.json()["items"]}
    assert on_contract[str(event["id"])] == event
    keys = {
        str(row["obligation_key"]): row["id"]
        for row in place.rows(
            select(obligation.c.id, obligation.c.obligation_key).where(
                obligation.c.contract_id == contract_id
            )
        )
    }
    assert sorted(keys) == ["O1", "O2"]

    found: dict[str, dict[str, Any]] = {}
    for key, obligation_id in keys.items():
        panel = get(app, f"/api/v1/obligations/{obligation_id}/events", maya, {"limit": 100})
        assert panel.status_code == 200, panel.text
        for item in panel.json()["items"]:
            other = on_contract[str(item["id"])]
            # the status first: before the rule this route answered two members fewer
            assert set(item) == set(other), item["event_type"]
            assert {**item, "obligation_keys": None} == {**other, "obligation_keys": None}
            assert key in item["obligation_keys"], item["event_type"]
            found[f"{key}:{item['event_type']}"] = item
    assert found["O2:PROGRESS_RECORDED"] == event
    assert (
        event["created_by"]["kind"],
        event["prepared_by"]["id"],
        event["approved_by"]["id"],
        event["source_row"],
        event["void_refusal"],
    ) == ("SYSTEM", str(maya.member.user_id), str(world.priya.member.user_id), None, None)
    # the route's own rule for the one member: the invoice names O1 in its payload alone
    invoice = found["O1:BILLING_RECORDED"]
    assert (invoice["obligation_keys"], on_contract[str(invoice["id"])]["obligation_keys"]) == (
        ["O1"],
        [],
    )
