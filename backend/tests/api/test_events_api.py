"""API-R-30 events (04 §15.3 API-R-30, §16.3, table 3.4-R, table 15.4-A; 05 TZ-03, §3.9; dev-guide
DG-CMD-09, DG-KRN-IDEM-01; PRD IMP-22; 03 REQ-CST-001, REQ-CLS-005; CTL-008; BUILD_SPEC CTR-5).

Worlds: ``support.factories.seat_world`` (PRD §2.6 for K-09 on AVM-US) and
``support.factories.k11_world`` (K-11 on AVM-DE, Europe/Berlin). Contracts are booked through
``book_contract`` and activated as the SYSTEM principal (BS3-D-19). Maya (Revenue Accountant)
records events with ``event.record``; the computations run ``erev_engine.compute``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, contract_event, event_submission, job
from erev_api.domain.contracts.commands import BookedContract
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1, DeliveryRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.money import MoneyIn
from fastapi import FastAPI
from sqlalchemy import func, select, text
from support.db import TestDatabase
from support.factories import (
    K11World,
    SeatWorld,
    Workspace,
    activated_contract,
    appended,
    booked_contract,
    delivered_k11,
    k09_body,
    k11_body,
    k11_world,
    seat_world,
)
from support.http import call
from support.principals import cookie_headers
from support.reference import assign, fields, get, post, slug
from support.worlds import approved_manual_events

EVENTS = "/api/v1/contracts/{contract_id}/events"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
IMPACT_MEMBERS = {
    "transaction_price_before",
    "transaction_price_after",
    "catch_up_total",
    "catch_up_by_obligation",
    "remaining_allocation_before",
    "remaining_allocation_after",
    "revenue_by_period",
    "rpo_before",
    "rpo_after",
    "rpo_date",
    "balances_before",
    "balances_after",
    "journal_lines",
    "progress_before",
    "progress_after",
    "replay_from_date",
    "posting_period_key",
    "origin_period_key",
    # 04 API-S-ImpactSummary since item MOD-PREVIEW-JOURNAL-RULE-1: when the dry run was computed
    # and for which posting period.
    "computed_at",
    "computed_period_key",
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    return k11_world(app, keyring, clock, files)


@pytest.fixture
def runtime(keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


def _k09(world: SeatWorld) -> BookedContract:
    booked = booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    return activated_contract(world.place, booked)


def _billing(invoice: str, amount: str, currency: str, issued: str) -> dict[str, Any]:
    return {
        "event_type": "BILLING_RECORDED",
        "effective_date": issued,
        "payload": {
            "invoice_number": invoice,
            "line_external_id": f"{invoice}-1",
            "amount": {"amount": amount, "currency": currency},
            "issue_date": issued,
        },
    }


def _head(place: Workspace, contract_id: UUID) -> int:
    return int(
        place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    )


def _event_count(place: Workspace, contract_id: UUID) -> int:
    statement = select(func.count()).where(contract_event.c.contract_id == contract_id)
    return int(place.scalar(statement))


def _work(place: Workspace, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it."""
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, place.tenant_id, attempt=1, runtime=runtime)


def test_append_events_atomically_and_compute(world: SeatWorld) -> None:
    booked = _k09(world)
    contract_id = booked.contract["id"]
    path = EVENTS.format(contract_id=contract_id)
    body = {"events": [_billing("INV-US-3101", "36000.00", "USD", "2026-09-01")]}
    appended_response = post(world.app, path, world.place.author, body, if_match='"s2"')
    assert appended_response.status_code == 201, appended_response.text
    result = appended_response.json()
    (event,) = result["events"]
    assert (
        event["event_type"],
        event["stream_version"],
        event["effective_date"],
        event["origin"],
        event["is_manual"],
        event["payload"]["amount"],
        event["payload"]["invoice_number"],
    ) == (
        "BILLING_RECORDED",
        3,
        "2026-09-01",
        "UI",
        True,
        {"amount": "36000.00", "currency": "USD"},
        "INV-US-3101",
    )
    assert result["computation"]["status"] == "SUCCEEDED"
    assert set(result["computation"]["contract_version_ids"]) == {"ASC606"}
    assert result["contract"]["head_stream_version"] == 3
    assert appended_response.headers["ETag"] == '"s3"'
    assert _head(world.place, contract_id) == 3
    shown = get(world.app, f"/api/v1/events/{event['id']}", world.place.author)
    assert shown.status_code == 200, shown.text
    assert shown.json()["computation"] == {"id": result["computation"]["id"], "status": "SUCCEEDED"}

    stale = post(
        world.app,
        path,
        world.place.author,
        {"events": [_billing("INV-US-3102", "1000.00", "USD", "2026-09-02")]},
        if_match='"s2"',
    )
    assert stale.status_code == 412, stale.text
    assert slug(stale) == "precondition-failed"
    assert _head(world.place, contract_id) == 3
    listed = get(world.app, path, world.place.author)
    assert listed.status_code == 200, listed.text
    assert [item["event_type"] for item in listed.json()["items"]] == [
        "CONTRACT_BOOKED",
        "CONTRACT_ACTIVATED",
        "BILLING_RECORDED",
    ]
    filtered = get(world.app, path, world.place.author, {"event_type": "BILLING_RECORDED"})
    assert [item["id"] for item in filtered.json()["items"]] == [event["id"]]


def test_missing_idempotency_key(world: SeatWorld) -> None:
    booked = booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    author = world.place.author
    headers = cookie_headers(author.token, author.csrf_token, key=False)
    headers["If-Match"] = '"s1"'
    response = call(
        world.app,
        "POST",
        EVENTS.format(contract_id=booked.contract["id"]),
        json={"events": [_billing("INV-US-3101", "36000.00", "USD", "2026-09-01")]},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert slug(response) == "validation-failed"
    assert fields(response) == [("Idempotency-Key", "API-C-04")]
    assert _event_count(world.place, booked.contract["id"]) == 1


def test_return_and_refund_bounds(k11: K11World) -> None:
    booked = activated_contract(
        k11.place, booked_contract(k11.place, k11_body(k11.customer_id), activate=False)
    )
    contract_id = booked.contract["id"]
    appended(
        k11.place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.DELIVERY_RECORDED,
                effective_date=date(2026, 9, 5),
                payload=DeliveryRecordedV1(obligation_key="O1", quantity="2", trigger="DELIVERY"),
            ),
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 5),
                payload=BillingRecordedV1(
                    invoice_number="INV-DE-5004",
                    line_external_id="INV-DE-5004-1",
                    amount=MoneyIn(amount="100.00", currency="EUR"),
                    issue_date=date(2026, 9, 5),
                ),
            ),
        ],
    )
    path = EVENTS.format(contract_id=contract_id)
    returned = post(
        k11.app,
        path,
        k11.place.author,
        {
            "events": [
                {
                    "event_type": "RETURN_RECORDED",
                    "effective_date": "2026-09-10",
                    "payload": {"obligation_key": "O1", "quantity": "3"},
                }
            ]
        },
        if_match='"s4"',
    )
    assert returned.status_code == 422, returned.text
    assert slug(returned) == "validation-failed"
    assert fields(returned) == [("events.0.payload.quantity", "RETURN_EXCEEDS_DELIVERED")]
    assert returned.json()["errors"][0]["message"] == (
        "Return of 3 units exceeds the 2 units delivered on NS-SO-DE-5004, obligation O1 (AVM-GW)."
    )
    credited = post(
        k11.app,
        path,
        k11.place.author,
        {
            "events": [
                {
                    "event_type": "CREDIT_MEMO_RECORDED",
                    "effective_date": "2026-09-10",
                    "payload": {
                        "credit_memo_number": "CM-DE-5004",
                        "amount": {"amount": "150.00", "currency": "EUR"},
                        "issue_date": "2026-09-10",
                    },
                }
            ]
        },
        if_match='"s4"',
    )
    assert credited.status_code == 422, credited.text
    assert fields(credited) == [("events.0.payload.amount", "REFUND_EXCEEDS_BILLED")]
    assert credited.json()["errors"][0]["message"] == (
        "Credit of 150.00 exceeds the 100.00 billed on NS-SO-DE-5004."
    )
    assert _head(k11.place, contract_id) == 4
    assert _event_count(k11.place, contract_id) == 4


def test_effective_at_converted_to_entity_date(k11: K11World) -> None:
    body = {
        **k11_body(k11.customer_id),
        "external_id": "NS-SO-DE-5010",
        "inception_date": "2026-03-01",
    }
    booked = booked_contract(k11.place, body, activate=False)
    contract_id = booked.contract["id"]
    item = _billing("INV-DE-5010", "900.00", "EUR", "2026-04-01")
    del item["effective_date"]
    item["effective_at"] = "2026-03-31T23:30:00-04:00"
    response = post(
        k11.app,
        EVENTS.format(contract_id=contract_id),
        k11.place.author,
        {"events": [item]},
        if_match='"s1"',
    )
    assert response.status_code == 201, response.text
    (event,) = response.json()["events"]
    assert event["effective_date"] == "2026-04-01"
    assert event["payload"]["effective_at"] == "2026-03-31T23:30:00-04:00"
    stored = k11.place.rows(
        select(contract_event.c.effective_date, contract_event.c.payload).where(
            contract_event.c.id == UUID(event["id"])
        )
    )
    assert [(row["effective_date"], row["payload"]["effective_at"]) for row in stored] == [
        (date(2026, 4, 1), "2026-03-31T23:30:00-04:00")
    ]
    both = post(
        k11.app,
        EVENTS.format(contract_id=contract_id),
        k11.place.author,
        {"events": [{**item, "effective_date": "2026-04-01"}]},
        if_match='"s2"',
    )
    assert both.status_code == 422, both.text
    assert fields(both) == [("events.0.effective_at", "API-C-07")]


def test_cost_incurred_commission_payload(world: SeatWorld) -> None:
    booked = _k09(world)
    contract_id = booked.contract["id"]
    path = EVENTS.format(contract_id=contract_id)
    commission = {
        "purpose": "COST_TO_OBTAIN",
        "payee": "Sales rep 12",
        "plan_code": "SALES-2026",
        "amount": {"amount": "6480.00", "currency": "USD"},
        "is_incremental": True,
    }
    # BUILD_SPEC CTR-6 (04 §16.3 "Manual events"): a cost event a person records is accepted as
    # an event submission with its evidence, and appended by another user's approval.
    assign(world.priya.member, "revenue_reviewer")
    accepted = approved_manual_events(
        world.place,
        world.priya,
        UUID(str(contract_id)),
        {"event_type": "COST_INCURRED", "effective_date": "2026-09-05", "payload": commission},
    )
    (event,) = accepted["events"]
    assert event["event_type"] == "COST_INCURRED"
    assert event["payload"] == {
        **commission,
        "obligation_key": None,
        "is_wasted": None,
        "is_uninstalled_material": None,
        "has_clawback": None,
        "cost_adjustment": None,
    }
    clawback = {
        "purpose": "COST_TO_OBTAIN",
        "plan_code": "SALES-2026",
        "amount": {"amount": "6480.00", "currency": "USD"},
        "cost_adjustment": "CLAWBACK",
    }
    refused = post(
        world.app,
        path,
        world.place.author,
        {
            "events": [
                {"event_type": "COST_INCURRED", "effective_date": "2026-09-06", "payload": clawback}
            ]
        },
        if_match='"s3"',
    )
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert [field for field, _ in fields(refused)] == ["events.0.payload"]
    assert _head(world.place, contract_id) == 3


def test_preview_appends_nothing(world: SeatWorld, runtime: JobRuntime) -> None:
    booked = _k09(world)
    contract_id = booked.contract["id"]
    preview = post(
        world.app,
        f"{EVENTS.format(contract_id=contract_id)}/preview",
        world.place.author,
        {"events": [_billing("INV-US-3101", "36000.00", "USD", "2026-09-01")]},
        if_match='"s2"',
    )
    assert preview.status_code == 202, preview.text
    queued = preview.json()
    assert (queued["kind"], queued["state"]) == ("CONTRACT_COMPUTE", "QUEUED")
    assert preview.headers["Location"] == f"/api/v1/jobs/{queued['id']}"
    assert _head(world.place, contract_id) == 2
    _work(world.place, UUID(queued["id"]), runtime)
    finished = get(world.app, f"/api/v1/jobs/{queued['id']}", world.place.author)
    assert finished.status_code == 200, finished.text
    shown = finished.json()
    assert shown["state"] == "SUCCEEDED", shown
    summary = shown["result"]["summary"]
    assert set(summary) == IMPACT_MEMBERS
    assert (
        summary["transaction_price_after"],
        summary["replay_from_date"],
        summary["rpo_date"],
        summary["posting_period_key"],
        summary["origin_period_key"],
        [row["period_key"] for row in summary["revenue_by_period"]],
    ) == (
        {"amount": "108000.00", "currency": "USD"},
        "2026-09-01",
        "2026-09-01",
        "FY2026-P09",
        None,
        ["FY2026-P09", "FY2026-P10", "FY2026-P11", "FY2026-P12", "FY2027-P01", "FY2027-P02"],
    )
    assert shown["result"]["counts"] == {"events": 1}
    assert _head(world.place, contract_id) == 2
    assert _event_count(world.place, contract_id) == 2


def test_request_void_reason_subset(world: SeatWorld) -> None:
    booked = _k09(world)
    contract_id = booked.contract["id"]
    appended(
        world.place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 1),
                payload=BillingRecordedV1(
                    invoice_number="INV-US-3101",
                    line_external_id="INV-US-3101-1",
                    amount=MoneyIn(amount="36000.00", currency="USD"),
                    issue_date=date(2026, 9, 1),
                ),
            )
        ],
    )
    event_id = world.place.scalar(
        select(contract_event.c.id).where(
            contract_event.c.contract_id == contract_id, contract_event.c.stream_version == 3
        )
    )
    path = f"/api/v1/events/{event_id}/request-void"
    requested = post(
        world.app,
        path,
        world.place.author,
        {"reason_code": "DUPLICATE", "comment": "Invoice INV-US-3101 was recorded twice."},
    )
    assert requested.status_code == 201, requested.text
    created = requested.json()
    assert set(created) == {"event_submission_id", "approval_request_id"}
    assert requested.headers["Location"] == (
        f"/api/v1/event-submissions/{created['event_submission_id']}"
    )
    submission = get(
        world.app, f"/api/v1/event-submissions/{created['event_submission_id']}", world.place.author
    )
    assert submission.status_code == 200, submission.text
    shown = submission.json()
    assert (shown["status"], shown["approval_request_id"], shown["events"][0]["event_type"]) == (
        "SUBMITTED",
        created["approval_request_id"],
        "EVENT_VOIDED",
    )
    assert shown["events"][0]["supersedes_event_id"] == str(event_id)
    assert shown["events"][0]["payload"] == {
        "reason_code": "DUPLICATE",
        "comment": "Invoice INV-US-3101 was recorded twice.",
    }
    assert _head(world.place, contract_id) == 3

    refused = post(
        world.app,
        path,
        world.place.author,
        {"reason_code": "ERROR_CORRECTION", "comment": "Wrong reason for a void."},
    )
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("reason_code", "REASON_CODE_NOT_ALLOWED")]

    withdrawn = post(
        world.app,
        f"/api/v1/event-submissions/{created['event_submission_id']}/withdraw",
        world.place.author,
        {"comment": "Recorded once after all."},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "VOIDED"
    statuses = world.place.rows(select(event_submission.c.status))
    assert [str(row["status"]) for row in statuses] == ["VOIDED"]


@pytest.mark.control("CTL-008")
def test_ctl_008_api_over_delivery_rejected_without_state_change(k11: K11World) -> None:
    booked = delivered_k11(k11)
    contract_id = booked.contract["id"]
    assert _head(k11.place, contract_id) == 3
    response = post(
        k11.app,
        EVENTS.format(contract_id=contract_id),
        k11.place.author,
        {
            "events": [
                {
                    "event_type": "DELIVERY_RECORDED",
                    "effective_date": "2026-09-14",
                    "payload": {"obligation_key": "O1", "quantity": "90", "trigger": "DELIVERY"},
                }
            ]
        },
        if_match='"s3"',
    )
    assert response.status_code == 422, response.text
    body: Mapping[str, Any] = response.json()
    assert fields(response) == [("events.0.payload.quantity", "PROGRESS_OVER_DELIVERY")]
    detail = "NS-SO-DE-5004, obligation O1 (AVM-GW): requested 90, remaining 80."
    assert (body["detail"], body["errors"][0]["message"]) == (detail, detail)
    assert _head(k11.place, contract_id) == 3
    assert _event_count(k11.place, contract_id) == 3


# --- S10-R-07 billing identity at the channel (04 table 15.4-B rev 1.45; D-97 (30); PR-1.3) -------

IDENTITY = {"invoice_number": "INV-DE-5004", "line_external_id": "INV-DE-5004-1"}


def _stored_billing(k11: K11World) -> UUID:
    """K-11 activated (head 2) with one stored line INV-DE-5004 / INV-DE-5004-1 of 100.00 EUR on O1
    (head 3)."""
    booked = activated_contract(
        k11.place, booked_contract(k11.place, k11_body(k11.customer_id), activate=False)
    )
    contract_id = UUID(str(booked.contract["id"]))
    appended(
        k11.place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 5),
                payload=BillingRecordedV1(
                    obligation_key="O1",
                    amount=MoneyIn(amount="100.00", currency="EUR"),
                    issue_date=date(2026, 9, 5),
                    **IDENTITY,
                ),
                obligation_keys=("O1",),
            )
        ],
    )
    return contract_id


def _repeat(**payload: Any) -> dict[str, Any]:
    """A BILLING_RECORDED item repeating the stored identity unless the payload overrides it."""
    return {
        "event_type": "BILLING_RECORDED",
        "effective_date": "2026-09-10",
        "payload": {
            **IDENTITY,
            "amount": {"amount": "100.00", "currency": "EUR"},
            "issue_date": "2026-09-10",
            **payload,
        },
    }


def test_s10_r07_repeated_cancellable_identity_refused_at_api(k11: K11World) -> None:
    """D-97 (30); 04 table 15.4-B rev 1.45 ``INVOICE_IDENTITY_REPEATED``: a ``BILLING_RECORDED``
    that repeats a stored identity of the contract with ``is_cancellable = true`` is 422 before
    anything is appended (a re-issued cancellable invoice carries a new identity); the same holds
    inside one append against an earlier item; a first cancellable line and a same-amount
    non-cancellable status update stay accepted (ENGINE_SPEC_B S10-R-07)."""
    contract_id = _stored_billing(k11)
    path = EVENTS.format(contract_id=contract_id)
    repeated = post(
        k11.app, path, k11.place.author, {"events": [_repeat(is_cancellable=True)]}, if_match='"s3"'
    )
    assert repeated.status_code == 422, repeated.text
    assert slug(repeated) == "validation-failed"
    assert fields(repeated) == [("events.0.payload.invoice_number", "INVOICE_IDENTITY_REPEATED")]
    assert repeated.json()["errors"][0]["message"] == (
        "Invoice INV-DE-5004, line INV-DE-5004-1 is already recorded on NS-SO-DE-5004; a re-issued "
        "cancellable invoice carries a new invoice number or line reference."
    )
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (3, 3)

    fresh = _repeat(
        invoice_number="INV-DE-5005", line_external_id="INV-DE-5005-1", is_cancellable=True
    )
    batch = post(k11.app, path, k11.place.author, {"events": [fresh, fresh]}, if_match='"s3"')
    assert batch.status_code == 422, batch.text
    assert fields(batch) == [("events.1.payload.invoice_number", "INVOICE_IDENTITY_REPEATED")]
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (3, 3)

    accepted = post(
        k11.app, path, k11.place.author, {"events": [fresh, _repeat()]}, if_match='"s3"'
    )
    assert accepted.status_code == 201, accepted.text
    assert [item["payload"]["invoice_number"] for item in accepted.json()["events"]] == [
        "INV-DE-5005",
        "INV-DE-5004",
    ]
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (5, 5)


def test_s10_r07_status_update_mismatch_refused_at_api(k11: K11World) -> None:
    """PR-1.3 (04 table 15.4-B ``INVOICE_STATUS_UPDATE_MISMATCH``, API clause since rev 1.2): a
    non-cancellable repeat is a status update, refused with 422 when it changes the amount or moves
    the line between two non-null obligation keys; a null key preserves the first line's
    attribution and is appended."""
    contract_id = _stored_billing(k11)
    path = EVENTS.format(contract_id=contract_id)
    changed = post(
        k11.app,
        path,
        k11.place.author,
        {"events": [_repeat(amount={"amount": "120.00", "currency": "EUR"})]},
        if_match='"s3"',
    )
    assert changed.status_code == 422, changed.text
    assert fields(changed) == [("events.0.payload.amount", "INVOICE_STATUS_UPDATE_MISMATCH")]
    assert changed.json()["errors"][0]["message"] == (
        "Invoice INV-DE-5004, line INV-DE-5004-1: the status update carries 120.00 EUR, but the "
        "original line is 100.00 EUR. A status update cannot change the amount; send a credit memo "
        "or a new invoice."
    )
    moved = post(
        k11.app, path, k11.place.author, {"events": [_repeat(obligation_key="O2")]}, if_match='"s3"'
    )
    assert moved.status_code == 422, moved.text
    assert fields(moved) == [("events.0.payload.obligation_key", "INVOICE_STATUS_UPDATE_MISMATCH")]
    assert moved.json()["errors"][0]["message"] == (
        "Invoice INV-DE-5004, line INV-DE-5004-1: the status update names obligation O2, but the "
        "original line is on O1. A status update cannot move the line; send a credit memo of the "
        "original line and a new invoice."
    )
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (3, 3)

    kept = post(k11.app, path, k11.place.author, {"events": [_repeat()]}, if_match='"s3"')
    assert kept.status_code == 201, kept.text
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (4, 4)


def _credit(amount: str) -> dict[str, Any]:
    return {
        "event_type": "CREDIT_MEMO_RECORDED",
        "effective_date": "2026-09-12",
        "payload": {
            "credit_memo_number": "CM-DE-5004",
            "credited_invoice_number": "INV-DE-5004",
            "obligation_key": "O1",
            "amount": {"amount": amount, "currency": "EUR"},
            "issue_date": "2026-09-12",
        },
    }


def test_s10_r07_refund_bound_reads_kept_lines_at_api(k11: K11World) -> None:
    """VOID-3a: the channel's cumulative billing counts kept lines only (the first-seen identity and
    cancellable repeats, ``billing_identity.kept_lines``); an accepted same-amount status update on
    the same obligation adds nothing, so a credit above the kept billing is 422
    ``REFUND_EXCEEDS_BILLED`` at the channel (05 §3.9; REQ-TP-009) rather than left to the engine's
    CV-15 re-check, and a credit within it is appended."""
    contract_id = _stored_billing(k11)  # INV-DE-5004 / -1, 100.00 EUR on O1 (head 3)
    path = EVENTS.format(contract_id=contract_id)
    updated = post(
        k11.app, path, k11.place.author, {"events": [_repeat(obligation_key="O1")]}, if_match='"s3"'
    )
    assert updated.status_code == 201, updated.text  # a same-amount status update of the line
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (4, 4)

    over = post(k11.app, path, k11.place.author, {"events": [_credit("150.00")]}, if_match='"s4"')
    assert over.status_code == 422, over.text
    assert fields(over) == [("events.0.payload.amount", "REFUND_EXCEEDS_BILLED")]
    assert over.json()["errors"][0]["message"] == (
        "Credit of 150.00 exceeds the 100.00 billed on NS-SO-DE-5004, obligation O1 (AVM-GW)."
    )
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (4, 4)

    within = post(k11.app, path, k11.place.author, {"events": [_credit("100.00")]}, if_match='"s4"')
    assert within.status_code == 201, within.text
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (5, 5)


def _referenced_credit(number: str, key: str, amount: str) -> dict[str, Any]:
    return {
        "event_type": "CREDIT_MEMO_RECORDED",
        "effective_date": "2026-09-12",
        "payload": {
            "credit_memo_number": number,
            "obligation_key": key,
            "amount": {"amount": amount, "currency": "EUR"},
            "issue_date": "2026-09-12",
        },
    }


def test_d98_103_referenced_credit_draws_on_unreferenced_billing_at_api(k11: K11World) -> None:
    """D-98 103 (Codex BOUND-R1; D-87 L6-5-Q-15; stage 01 ``referenced_cover``): K-11 bills 300.00
    without an obligation; a referenced credit of 200.00 on O1 draws on that unreferenced billing
    (the engine covers it; the own-bucket channel refused it); a second referenced credit on O2 may
    draw only on the 100.00 not yet drawn — 150.00 is refused with the remaining cover named and
    nothing appended, 100.00 is appended."""
    booked = activated_contract(
        k11.place, booked_contract(k11.place, k11_body(k11.customer_id), activate=False)
    )
    contract_id = UUID(str(booked.contract["id"]))
    appended(
        k11.place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 5),
                payload=BillingRecordedV1(
                    invoice_number="INV-DE-5010",
                    line_external_id="INV-DE-5010-1",
                    amount=MoneyIn(amount="300.00", currency="EUR"),
                    issue_date=date(2026, 9, 5),
                ),
            )
        ],
    )
    path = EVENTS.format(contract_id=contract_id)
    first = post(
        k11.app, path, k11.place.author,
        {"events": [_referenced_credit("CM-DE-5010", "O1", "200.00")]}, if_match='"s3"',
    )  # fmt: skip
    assert first.status_code == 201, first.text
    over = post(
        k11.app, path, k11.place.author,
        {"events": [_referenced_credit("CM-DE-5011", "O2", "150.00")]}, if_match='"s4"',
    )  # fmt: skip
    assert over.status_code == 422, over.text
    assert fields(over) == [("events.0.payload.amount", "REFUND_EXCEEDS_BILLED")]
    assert over.json()["errors"][0]["message"] == (
        "Credit of 150.00 exceeds the 100.00 billed on NS-SO-DE-5004, obligation O2 (AVM-SUP-12)."
    )
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (4, 4)
    within = post(
        k11.app, path, k11.place.author,
        {"events": [_referenced_credit("CM-DE-5011", "O2", "100.00")]}, if_match='"s4"',
    )  # fmt: skip
    assert within.status_code == 201, within.text
    assert (_head(k11.place, contract_id), _event_count(k11.place, contract_id)) == (5, 5)
