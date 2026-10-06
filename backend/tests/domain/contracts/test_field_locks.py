"""Field locks, memo edits and attribute changes (04 §15.2 ``field-locked-after-activation``, §16.1
``update-memos`` and ``replace-draft``, §16.3 ``LINE_ATTRIBUTES_CHANGED``, ``MEMO_UPDATED``; PRD
BR-CON-02, ERR-11, §2.5 routing row ``ATTRIBUTE_CHANGE``; 03 REQ-CON-007, REQ-CON-008, REQ-MOD-021
platform part; BUILD_SPEC CTR-10; control CTL-006).

World: ``support.factories.seat_world`` (AVM-US, USD); K-09 ``SF-ORD-10417`` (30 seats × 36 months,
108,000.00 USD from 2026-09-01) booked and activated as SYSTEM (BS3-D-19), so its head is 2. Maya
(Revenue Accountant) records events and edits memos; Priya is given Revenue Reviewer for
``event.approve``.
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
    approval_request,
    approval_step,
    audit_event,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    event_submission,
    obligation,
    obligation_version,
    subledger_line,
)
from erev_api.domain.contracts import locks
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    SeatWorld,
    activated_contract,
    booked_contract,
    k09_body,
    seat_world,
)
from support.reference import approve, assign, fields, get, gl_account, post, slug

CONTRACTS = "/api/v1/contracts"
EVENTS = "/api/v1/contracts/{contract_id}/events"
LOCKED = "Total price of an active contract changes only through a modification or price change."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> SeatWorld:
    return seat_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _active_k09(world: SeatWorld) -> UUID:
    booked = booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    activated_contract(world.place, booked)
    return UUID(str(booked.contract["id"]))


def _attribute_change(changes: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    return {
        "events": [
            {
                "event_type": "LINE_ATTRIBUTES_CHANGED",
                "effective_date": "2026-09-15",
                "obligation_key": "O1",
                "payload": {"obligation_key": "O1", "changes": changes, "diff": diff},
            }
        ]
    }


def _header(world: SeatWorld, contract_id: UUID) -> tuple[str, int]:
    row = world.place.rows(
        select(contract.c.status, contract.c.head_stream_version).where(
            contract.c.id == contract_id
        )
    )[0]
    return str(row["status"]), int(row["head_stream_version"])


def _denied(world: SeatWorld, contract_id: UUID) -> list[tuple[str, dict[str, Any]]]:
    rows = world.place.rows(
        select(audit_event.c.action, audit_event.c.detail)
        .where(audit_event.c.object_id == contract_id, audit_event.c.outcome == "DENIED")
        .order_by(audit_event.c.occurred_at, audit_event.c.chain_seq)
    )
    return [(str(row["action"]), dict(row["detail"])) for row in rows]


def _posted(world: SeatWorld, contract_id: UUID) -> dict[str, Decimal]:
    rows = world.place.rows(
        select(subledger_line.c.account_role, func.sum(subledger_line.c.amount_txn).label("total"))
        .where(subledger_line.c.contract_id == contract_id)
        .group_by(subledger_line.c.account_role)
    )
    return {str(row["account_role"]): Decimal(row["total"]) for row in rows}


def test_price_change_on_active_contract_refused(world: SeatWorld) -> None:
    contract_id = _active_k09(world)
    refused = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        _attribute_change(
            {"total_price": {"amount": "120000.00", "currency": "USD"}},
            {"total_price": {"before": "108000.00", "after": "120000.00"}},
        ),
        if_match='"s2"',
    )
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "field-locked-after-activation"
    body = refused.json()
    assert (body["errors"][0]["field"], body["errors"][0]["rule_id"]) == (
        "total_price",
        "REQ-CON-007",
    )
    assert body["detail"] == LOCKED
    assert body["errors"][0]["message"] == LOCKED
    assert _denied(world, contract_id) == [
        (
            "contract.record_events",
            {
                "rule_id": "REQ-CON-007",
                "fields": ["total_price"],
                "status": "ACTIVE",
                "permission": "event.record",
                # 04 T-PLT-19 "Contract key" (rev 1.154; supervisor ruling R-108): an event of a
                # contract's object names the contract in its detail.
                "contract_id": str(contract_id),
            },
        )
    ]
    assert _header(world, contract_id) == ("ACTIVE", 2)


def test_attribute_change_through_approval(world: SeatWorld) -> None:
    maya = world.place.author
    contract_id = _active_k09(world)
    gl_account(
        world.app,
        maya,
        code="4020",
        name="Revenue - enterprise subscriptions",
        account_type="REVENUE",
        normal_balance="C",
    )
    diff = {"account_overrides": {"before": {}, "after": {"REVENUE": "4020"}}}
    submitted = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        maya,
        _attribute_change({"account_overrides": {"REVENUE": "4020"}}, diff),
        if_match='"s2"',
    )
    assert submitted.status_code == 201, submitted.text
    created = submitted.json()
    assert set(created) == {"event_submission_id", "approval_request_id"}
    assert submitted.headers["Location"] == (
        f"/api/v1/event-submissions/{created['event_submission_id']}"
    )
    assert _header(world, contract_id) == ("ACTIVE", 2)
    request = world.place.rows(
        select(approval_request.c.subject_type, approval_request.c.subject_id).where(
            approval_request.c.id == UUID(created["approval_request_id"])
        )
    )[0]
    assert (str(request["subject_type"]), str(request["subject_id"])) == (
        "ATTRIBUTE_CHANGE",
        created["event_submission_id"],
    )
    steps = world.place.rows(
        select(approval_step.c.required_permission).where(
            approval_step.c.approval_request_id == UUID(created["approval_request_id"])
        )
    )
    assert [str(row["required_permission"]) for row in steps] == ["event.approve"]

    assign(world.priya.member, "revenue_reviewer")
    approved = approve(world.app, created["approval_request_id"], world.priya)
    assert approved.status_code == 200, approved.text
    events = world.place.rows(
        select(
            contract_event.c.event_type,
            contract_event.c.origin,
            contract_event.c.payload,
            contract_event.c.approval_request_id,
        )
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    last = events[-1]
    assert (str(last["event_type"]), str(last["origin"])) == ("LINE_ATTRIBUTES_CHANGED", "SYSTEM")
    assert last["payload"]["diff"] == diff
    assert last["payload"]["changes"]["account_overrides"] == {"REVENUE": "4020"}
    assert str(last["approval_request_id"]) == created["approval_request_id"]
    submission = world.place.rows(
        select(event_submission.c.status).where(
            event_submission.c.id == UUID(created["event_submission_id"])
        )
    )[0]
    assert str(submission["status"]) == "APPLIED"
    assert _header(world, contract_id) == ("ACTIVE", 3)
    group_id = world.place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    computed = world.place.rows(
        select(contract_computation.c.status, contract_computation.c.stream_heads)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )[0]
    assert (str(computed["status"]), computed["stream_heads"][str(contract_id)]) == (
        "SUCCEEDED",
        3,
    )
    version_id = world.place.scalar(
        select(contract_version.c.id)
        .where(
            contract_version.c.combination_group_id == group_id,
            contract_version.c.book_code == "ASC606",
        )
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )
    cause = world.place.scalar(
        select(obligation_version.c.id)
        .join(obligation, obligation.c.id == obligation_version.c.obligation_id)
        .where(
            obligation_version.c.contract_version_id == version_id,
            obligation.c.obligation_key == "O1",
        )
    )
    assert cause is not None
    # L4-1-Q-24: "the obligation override resolves 4020" needs the engine to fold the approved
    # LINE_ATTRIBUTES_CHANGED into the published obligation version or the posting intents; the rc
    # engine defines ``s06_modifications.attributes_at`` but no stage calls it, so
    # obligation_version.account_overrides keeps the booked {}.


def test_memo_edit_needs_comment_and_audits_diff(world: SeatWorld) -> None:
    maya = world.place.author
    contract_id = _active_k09(world)
    path = f"{CONTRACTS}/{contract_id}/update-memos"
    posted_before = _posted(world, contract_id)
    missing = post(world.app, path, maya, {"memo_1": "Renewal 2027"}, if_match='"s2"')
    assert (missing.status_code, slug(missing)) == (422, "validation-failed")
    assert [field for field, _ in fields(missing)] == ["comment"]

    updated = post(
        world.app,
        path,
        maya,
        {"memo_1": "Renewal 2027", "comment": "Renewal quote sent to the customer."},
        if_match='"s2"',
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["memo_1"], updated.json()["head_stream_version"]) == ("Renewal 2027", 3)
    assert updated.headers["ETag"] == '"s3"'
    last = world.place.rows(
        select(contract_event.c.event_type, contract_event.c.payload)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version.desc())
        .limit(1)
    )[0]
    assert (str(last["event_type"]), last["payload"]["memo_1"]) == ("MEMO_UPDATED", "Renewal 2027")
    audits = world.place.rows(
        select(audit_event.c.before, audit_event.c.after, audit_event.c.comment).where(
            audit_event.c.object_id == contract_id, audit_event.c.action == "contract.update_memos"
        )
    )
    assert [(row["before"], row["after"], row["comment"]) for row in audits] == [
        ({"memo_1": None}, {"memo_1": "Renewal 2027"}, "Renewal quote sent to the customer.")
    ]
    assert _posted(world, contract_id) == posted_before
    assert world.place.scalar(select(contract.c.memo_1).where(contract.c.id == contract_id)) == (
        "Renewal 2027"
    )


@pytest.mark.control("CTL-006")
def test_ctl_006_locked_fields_refused_on_every_channel(world: SeatWorld) -> None:
    maya = world.place.author
    contract_id = _active_k09(world)
    events_path = EVENTS.format(contract_id=contract_id)
    for member, value in (
        ("total_price", {"amount": "150000.00", "currency": "USD"}),
        ("quantity", "40"),
        ("start_date", "2026-10-01"),
        ("end_date", "2029-12-31"),
    ):
        refused = post(
            world.app,
            events_path,
            maya,
            _attribute_change({member: value}, {member: {"after": value}}),
            if_match='"s2"',
        )
        assert refused.status_code == 409, refused.text
        assert slug(refused) == "field-locked-after-activation"
        assert fields(refused) == [(member, "REQ-CON-007")]

    # Item ATTR-SSP-PIN-1 (04 §16.3 rev 1.231): the SSP version is not this route's to change.
    pinned = post(
        world.app,
        events_path,
        maya,
        _attribute_change(
            {"ssp_version_label": "2026-H2"},
            {"ssp_version_label": {"before": "2026-H1", "after": "2026-H2"}},
        ),
        if_match='"s2"',
    )
    assert pinned.status_code == 422, pinned.text  # without the rule: 201 with a submission
    assert slug(pinned) == "validation-failed"
    assert fields(pinned) == [("events.0.payload.changes.ssp_version_label", "REQ-SSP-006")]

    # [J] L4-1-Q-23: accounts and the entity never change directly; the events route appends
    # nothing and routes them for approval.
    routed = post(
        world.app,
        events_path,
        maya,
        _attribute_change(
            {"performing_entity_code": "AVM-US"},
            {"performing_entity_code": {"before": None, "after": "AVM-US"}},
        ),
        if_match='"s2"',
    )
    assert routed.status_code == 201, routed.text
    assert set(routed.json()) == {"event_submission_id", "approval_request_id"}

    body = k09_body(world.customers["C-09"])
    body["lines"][0] |= {
        "quantity": "40",
        "total_price": {"amount": "150000.00", "currency": "USD"},
        "start_date": "2026-10-01",
        "end_date": "2029-12-31",
        "account_overrides": {"REVENUE": "4020"},
        "performing_entity_code": "AVM-US",
        "ssp_version_label": "2026-H2",
    }
    replaced = post(
        world.app, f"{CONTRACTS}/{contract_id}/replace-draft", maya, body, if_match='"s2"'
    )
    assert (replaced.status_code, slug(replaced)) == (409, "invalid-transition")

    denied = _denied(world, contract_id)
    assert [action for action, _ in denied] == [
        "contract.record_events",
        "contract.record_events",
        "contract.record_events",
        "contract.record_events",
        "contract.replace_draft",
    ]
    assert [detail["fields"] for _, detail in denied[:4]] == [
        ["total_price"],
        ["quantity"],
        ["start_date"],
        ["end_date"],
    ]
    assert denied[4][1] == {
        "rule_id": "REQ-CON-007",
        "status": "ACTIVE",
        "permission": "contract.create",
        # 04 T-PLT-19 "Contract key" (rev 1.154; supervisor ruling R-108)
        "contract_id": str(contract_id),
    }
    assert _header(world, contract_id) == ("ACTIVE", 2)
    kinds = world.place.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    assert [str(row["event_type"]) for row in kinds] == ["CONTRACT_BOOKED", "CONTRACT_ACTIVATED"]
    shown = get(world.app, f"{CONTRACTS}/{contract_id}", maya).json()
    assert shown["head_stream_version"] == 2


def _routed(world: SeatWorld) -> tuple[int, int]:
    """The submissions and the approval requests of the workspace."""
    return (
        int(world.place.scalar(select(func.count()).select_from(event_submission))),
        int(world.place.scalar(select(func.count()).select_from(approval_request))),
    )


def test_attr_ssp_pin_1_the_events_route_refuses_a_version_pin(world: SeatWorld) -> None:
    """Item ATTR-SSP-PIN-1 (04 §16.3 ``LINE_ATTRIBUTES_CHANGED``, rev 1.231; 03 REQ-SSP-006). The
    SSP version of an obligation changes through the SSP override command, which an SSP approver
    decides and which RPT-22 lists. The events route stored a change that named a version — by
    id or by label — as an ``ATTRIBUTE_CHANGE`` request: one step, ``event.approve``, no preview;
    measured on K-02 O1, its approval pinned the obligation while a holder of ``ssp.approve``
    could not read the request. The route and its preview refuse the member for every caller,
    also beside a change the request may carry, and nothing is stored."""
    maya = world.place.author
    contract_id = _active_k09(world)
    events_path = EVENTS.format(contract_id=contract_id)
    before = _routed(world)
    for changes, member in (
        ({"ssp_version_label": "2026-H2"}, "ssp_version_label"),
        (
            {"ssp_book_version_id": world.version_id, "justification": "The H1 study applies."},
            "ssp_book_version_id",
        ),
        (
            {"account_overrides": {"REVENUE": "4020"}, "ssp_version_label": "2026-H2"},
            "ssp_version_label",
        ),
    ):
        for path in (events_path, f"{events_path}/preview"):
            refused = post(
                world.app,
                path,
                maya,
                _attribute_change(changes, {member: {"after": changes[member]}}),
                if_match='"s2"',
            )
            # the status first: without the rule the route answers 201 with a submission
            assert refused.status_code == 422, (path, refused.text)
            assert slug(refused) == "validation-failed"
            assert fields(refused) == [(f"events.0.payload.changes.{member}", "REQ-SSP-006")]
            assert [error["message"] for error in refused.json()["errors"]] == [
                "Change the SSP version of an obligation with an SSP override request, which an "
                "SSP approver decides."
            ]
    assert _routed(world) == before
    assert _header(world, contract_id) == ("ACTIVE", 2)


def test_attr_ssp_pin_1_a_stored_version_pin_is_stale_at_its_approval(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 T-CON-24 "Checked again where it is appended": a submission that names a version,
    stored before the rule or built below the route, pins nothing — its approval voids the
    request as stale. The stored submission is made here as the route made it before the rule
    (the refusal switched off for the one request)."""
    maya = world.place.author
    contract_id = _active_k09(world)
    with monkeypatch.context() as before_the_rule:
        before_the_rule.setattr(locks, "VERSION_PIN_MEMBERS", ())
        submitted = post(
            world.app,
            EVENTS.format(contract_id=contract_id),
            maya,
            _attribute_change(
                {"ssp_version_label": "2026-H2"},
                {"ssp_version_label": {"before": "2026-H1", "after": "2026-H2"}},
            ),
            if_match='"s2"',
        )
    assert submitted.status_code == 201, submitted.text
    stored = submitted.json()
    assign(world.priya.member, "revenue_reviewer")

    stale = approve(world.app, stored["approval_request_id"], world.priya)

    # the status first: without the check the event is appended and the obligation pinned
    assert stale.status_code == 409, stale.text
    assert slug(stale) == "stale-approval"
    request = world.place.rows(
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(stored["approval_request_id"])
        )
    )[0]
    assert (str(request["status"]), str(request["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    submission = world.place.rows(
        select(event_submission.c.status).where(
            event_submission.c.id == UUID(stored["event_submission_id"])
        )
    )[0]
    assert str(submission["status"]) == "VOIDED"
    assert _header(world, contract_id) == ("ACTIVE", 2)
    kinds = world.place.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    assert [str(row["event_type"]) for row in kinds] == ["CONTRACT_BOOKED", "CONTRACT_ACTIVATED"]
