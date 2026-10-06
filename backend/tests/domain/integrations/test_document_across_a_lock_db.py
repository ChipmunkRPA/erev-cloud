"""A sync run whose document met a period lock applies its objects once more (PRD ERR-72; 04
§14.1 "A command recorded before a lock" rev 1.229; 05 §5.6 rev 1.195; supervisor rulings R-122
(j) and (l) and of 2026-10-02; item PIN-WINDOW-APPENDER-1). PostgreSQL-bound.

A run records the documents of its feed and computes nothing, so each document asks the period
pin after its appends (``period_ends.refuse_appends_a_lock_met``; the pin beside a lock decided
through the product is witnessed in ``tests/domain/close/test_pin_without_a_computation_db.py``).
What a run does with the pin's refusal is witnessed here. The refusal's sentence says "Send it
again", and a run has no sender: measured on 2026-10-02 with the refusal recorded as the
document's failure, the invoice was never recorded — the checkpoint had moved on, the sync run
again fetched nothing, a reconciliation sweep found three duplicates, and no exception item named
the stored record, so the queue offered no reprocess. So the refusal ends the run's apply
transaction, the job applies the objects it fetched once more, and a second refusal fails the
job.

World: ``support.integrations`` with the Stripe mock (WLD-F-31), as ``test_stripe_ingestion``:
subscription ``sub_DEMO0001``, invoice ``in_DEMO0001`` and credit note ``cn_DEMO0001`` of
QUAY-US. A first run brings the subscription alone and books its contract, which a fixture then
activates — the pin does not judge a draft. The next run brings the two documents; while it
applies them a period of QUAY-US is locked: fixture rows written and committed by another
session before the pin is asked — the period closed and its ``LOCK`` record with the server's
present as its cutoff, as ``tests/pg/test_late_events.py`` writes them. The pin is the one built.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api import problems
from erev_api.adapters import mocks
from erev_api.adapters.mocks import stripe as st_mock
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    approval_request,
    contract,
    contract_event,
    exception_item,
    integration_connection,
    period,
    period_lock,
    period_state,
    period_state_transition,
    source_invoice,
    source_record,
    sync_run,
)
from erev_api.domain.contracts import period_ends
from erev_api.domain.integrations import commands
from erev_api.enums import ApprovalRequestStatus, ContractEventType, PrincipalKind
from erev_api.events.payloads import ChecklistItemV1, ContractActivatedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from support.adapter_secrets import serve_adapter_secrets, tenant_ref
from support.db import TestDatabase
from support.factories import workspace
from support.http import asgi_client, call
from support.integrations import IntegrationWorld, connection, integration_world, run, sync
from support.reference import post
from support.rows import (
    CloseParts,
    approval_request_values,
    period_lock_values,
    period_state_transition_values,
)

pytestmark = pytest.mark.slow

MOCK_BASE = f"{mocks.MOCKS_PREFIX}{st_mock.PREFIX}"
BOOKED = ["CONTRACT_BOOKED", "CONTRACT_ACTIVATED"]
DOCUMENTS = ["BILLING_RECORDED", "CREDIT_MEMO_RECORDED"]
# A secret the test's store serves; the reference is its name in the workspace's own namespace.
WEBHOOK_SECRET_NAME = "stripe-webhook-secret"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> Iterator[IntegrationWorld]:
    with integration_world(app, keyring, clock, app_settings) as built:
        yield built


def _checkpoint(world: IntegrationWorld, target: dict[str, Any]) -> Any:
    [row] = world.rows(
        select(integration_connection.c.checkpoint).where(
            integration_connection.c.id == UUID(str(target["id"]))
        )
    )
    return row["checkpoint"]


def _events(world: IntegrationWorld) -> list[tuple[str, datetime]]:
    return [
        (str(getattr(row["event_type"], "value", row["event_type"])), row["recorded_at"])
        for row in world.rows(
            select(contract_event.c.event_type, contract_event.c.recorded_at).order_by(
                contract_event.c.stream_version
            )
        )
    ]


def _count(world: IntegrationWorld, table: Any) -> int:
    [row] = world.rows(select(func.count().label("n")).select_from(table))
    return int(row["n"])


def _stripe(world: IntegrationWorld, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "stripe-quayside",
        "name": "Stripe (mock)",
        "adapter": "STRIPE",
        "direction": "INBOUND",
        "base_url": MOCK_BASE,
        "config": {"default_legal_entity": "QUAY-US"},
    }
    return connection(world, **{**body, **over})


def _feed(world: IntegrationWorld, events: Sequence[Mapping[str, Any]]) -> None:
    """The mock's feed holds exactly ``events``; its objects are as the scenario has them."""
    mock = world.app.state.mocks.adapters[st_mock.CODE]
    mock.scenario = dataclasses.replace(mock.scenario, events=tuple(dict(e) for e in events))


def _activated(world: IntegrationWorld) -> None:
    """The one contract of the world, ``sub_DEMO0001``, is ACTIVE — by a fixture, as
    ``support.factories.booked_contract`` activates one: the pin does not judge a draft."""
    [booked] = world.rows(
        select(contract.c.id, contract.c.inception_date, contract.c.head_stream_version)
    )
    runtime = world.runtime
    assert isinstance(runtime.keyring, KeyRing) and isinstance(runtime.files, LocalFileStore)
    place = workspace(world.app, world.clock, runtime.keyring, runtime.files, world.nikhil)
    with place.uow(system_principal(world.tenant_id)) as uow:
        append_events(
            uow,
            contract_id=UUID(str(booked["id"])),
            expected_stream_version=int(booked["head_stream_version"]),
            events=[
                EventIn(
                    event_type=ContractEventType.CONTRACT_ACTIVATED,
                    effective_date=booked["inception_date"],
                    payload=ContractActivatedV1(
                        checklist=(ChecklistItemV1(code="SOURCE_REFERENCE", passed=True),)
                    ),
                )
            ],
            origin="UI",
        )
        uow.commit()


def _prepared(world: IntegrationWorld, **over: Any) -> dict[str, Any]:
    """The ACTIVE Stripe connection after a first run that brought the subscription alone:
    ``sub_DEMO0001`` is booked and activated (``_activated``). The mock's feed is whole again:
    the next poll brings the invoice and the credit note."""
    made = _stripe(world, **over)
    whole = world.app.state.mocks.adapters[st_mock.CODE].scenario.events
    _feed(world, [event for event in whole if event["ordinal"] == 1])
    first, _ = sync(world, made)
    assert first["status"] == "SUCCEEDED", first["problem"]
    _feed(world, whole)
    _activated(world)
    assert [kind for kind, _ in _events(world)] == BOOKED
    return made


@pytest.fixture
def target(world: IntegrationWorld) -> dict[str, Any]:
    return _prepared(world)


def _lock_the_next_open_period(world: IntegrationWorld) -> datetime:
    """The earliest open period of QUAY-US is closed under a ``LOCK`` record whose cutoff is the
    server's present, by a session of its own, committed. Returns the cutoff."""
    tenant_id = world.tenant_id
    with tenant_session(world.context) as session:
        state = (
            session.execute(
                select(period_state.c.id, period_state.c.period_id)
                .join(period, period.c.id == period_state.c.period_id)
                .where(
                    period_state.c.entity_id == world.entity_id,
                    period_state.c.book_code == "ASC606",
                    period_state.c.state == "open",
                )
                .order_by(period.c.start_date)
                .limit(1)
            )
            .mappings()
            .one()
        )
        cutoff: datetime = session.execute(select(func.clock_timestamp())).scalar_one()
        request = approval_request_values(tenant_id, status=ApprovalRequestStatus.APPROVED)
        session.execute(insert(approval_request).values(**request))
        for from_state, to_state in (("open", "closing"), ("closing", "closed")):
            transition = period_state_transition_values(
                tenant_id,
                period_state_id=state["id"],
                entity_id=world.entity_id,
                period_id=state["period_id"],
                from_state=from_state,
                to_state=to_state,
            )
            if to_state == "closed":
                parts = CloseParts(
                    calendar_id=UUID(int=0),
                    entity_id=world.entity_id,
                    period_id=state["period_id"],
                    period_state_transition_id=transition["id"],
                    approval_request_id=request["id"],
                    file_id=new_id(),
                )
                lock = period_lock_values(tenant_id, parts=parts, created_at=cutoff)
                session.execute(insert(period_lock).values(**lock))
                transition = {
                    **transition,
                    "approval_request_id": request["id"],
                    "period_lock_id": lock["id"],
                }
            session.execute(insert(period_state_transition).values(**transition))
            session.execute(
                update(period_state)
                .where(period_state.c.id == state["id"])
                .values(state=to_state, updated_by_kind=PrincipalKind.SYSTEM.value)
            )
    return cutoff


def _locked_while_it_applies(
    monkeypatch: pytest.MonkeyPatch, world: IntegrationWorld, *, attempts: int
) -> tuple[list[datetime], list[datetime]]:
    """During each of the first ``attempts`` apply transactions of the run, before the pin is
    first asked, a period of QUAY-US is locked (``_lock_the_next_open_period``): a lock decided
    while the transaction stood. The pin is the one built. Returns the transaction timestamp of
    every question, in order, and the cutoffs of the locks."""
    real = period_ends.refuse_appends_a_lock_met
    asked: list[datetime] = []
    cutoffs: list[datetime] = []

    def ask(uow: Any, group_ids: Any) -> None:
        stamp = uow.session.execute(select(func.transaction_timestamp())).scalar_one()
        if stamp not in asked and len(cutoffs) < attempts:
            cutoffs.append(_lock_the_next_open_period(world))
        asked.append(stamp)
        real(uow, group_ids)

    monkeypatch.setattr(period_ends, "refuse_appends_a_lock_met", ask)
    return asked, cutoffs


def test_a_run_whose_document_met_a_lock_applies_its_objects_once_more(
    world: IntegrationWorld, target: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A period of QUAY-US is locked while the run applies the invoice. The invoice's question is
    refused; the run's transaction ends there with nothing stored, and the job applies the two
    objects it had fetched once more, in a new transaction. The run ends as an undisturbed run
    ends: both documents, each stored once, and their two events recorded by the second
    transaction — after the lock's cutoff, as the refusal's sentence promises of what is sent
    again.

    Fail-first (the refusal as the document's failure, as first built): the run ended FAILED
    with two failures — the invoice under ``PERIOD_STATE_MOVED`` and the credit note behind it —
    and neither document was ever recorded."""
    asked, cutoffs = _locked_while_it_applies(monkeypatch, world, attempts=1)
    row, finished = sync(world, target)
    assert row["status"] == "SUCCEEDED", row["problem"]
    counts = finished["result"]["counts"]
    assert counts["failures"] == 0 and counts["records"] == 2 and counts["fetched"] == 2
    assert (counts["documents"], counts["billing_events"], counts["credit_memo_events"]) == (
        2,
        1,
        1,
    )
    # asked by the invoice of the first attempt, then by both documents of the second
    (cutoff,) = cutoffs
    assert len(asked) == 3 and asked[0] < cutoff < asked[1] == asked[2], (asked, cutoff)
    events = _events(world)
    assert [kind for kind, _ in events] == BOOKED + DOCUMENTS
    assert [stamp for _, stamp in events[2:]] == [asked[1], asked[1]]  # after the lock's cutoff
    assert _count(world, source_record) == 3  # the subscription's, and each document's once
    assert _count(world, source_invoice) == 2


def test_a_run_refused_twice_leaves_nothing_and_the_next_run_brings_its_objects(
    world: IntegrationWorld, target: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second period of QUAY-US is locked while the job applies the objects once more. The
    second refusal is the job's failure: the run ends FAILED with the rule's own problem — 409
    ``lock-conflict``, the sentence of PRD ERR-72 and no other advice — nothing of either attempt
    is stored, and the connection's checkpoint is where it was. The next run fetches the same
    two objects and applies them, after both locks.

    Fail-first (as first built): the run finished with the checkpoint moved on and two failure
    records; the next run fetched nothing."""
    before = _checkpoint(world, target)
    asked, cutoffs = _locked_while_it_applies(monkeypatch, world, attempts=2)
    row, finished = sync(world, target)
    assert len(asked) == 2 and len(cutoffs) == 2, (asked, cutoffs)  # the invoice, in each attempt
    assert asked[0] < cutoffs[0] < asked[1] < cutoffs[1], (asked, cutoffs)
    assert (row["status"], finished["state"]) == ("FAILED", "FAILED")
    _told_by_the_rule(row)
    assert _checkpoint(world, target) == before
    assert [kind for kind, _ in _events(world)] == BOOKED
    assert _count(world, source_record) == 1 and _count(world, source_invoice) == 0
    later, done = sync(world, target)
    assert later["status"] == "SUCCEEDED", later["problem"]
    counts = done["result"]["counts"]
    assert counts["fetched"] == 2 and counts["records"] == 2 and counts["failures"] == 0
    events = _events(world)
    assert [kind for kind, _ in events] == BOOKED + DOCUMENTS
    assert asked[2] == asked[3] and [stamp for _, stamp in events[2:]] == [asked[2], asked[2]]
    assert asked[2] > cutoffs[1]
    assert _checkpoint(world, target) != before


def _told_by_the_rule(failed_run: Mapping[str, Any]) -> None:
    """What a person who opens the FAILED run reads (SCREENS §14.5: the problem's title and
    detail): the rule's own problem — 409 ``lock-conflict`` with the sentence of PRD ERR-72 — and
    not the advice of a run whose objects the source must fix; no object is named as a failure."""
    problem = failed_run["problem"]
    assert problem["type"].endswith("/lock-conflict") and problem["status"] == 409
    assert problem["detail"] == problems.PERIOD_STATE_MOVED_DETAIL
    assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
        (problems.RULE_PERIOD_STATE_MOVED, problems.PERIOD_STATE_MOVED_DETAIL)
    ]
    assert "failures" not in problem


def test_a_webhook_batch_refused_twice_is_brought_by_the_next_poll(
    world: IntegrationWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 ADP-01: a webhook is a notification, and its batch moves no checkpoint. A webhook names
    the events of the invoice and the credit note, and a period of QUAY-US is locked in each
    apply transaction of its job. What stands for a person who looks meanwhile: the
    ``WEBHOOK_BATCH`` run FAILED with the rule's problem, nothing of it stored, and no exception
    item. The next poll starts from the connection's checkpoint — where it was — fetches the two
    objects the webhook named and applies them."""
    secret_ref = tenant_ref(world.tenant_id, WEBHOOK_SECRET_NAME)
    serve_adapter_secrets(world.app, {secret_ref: st_mock.SHARED_SECRET})
    target = _prepared(world, secret_ref=secret_ref)
    before = _checkpoint(world, target)
    receiver = commands.receiver_id(world.tenant_id, UUID(str(target["id"])))
    now = int(world.clock.now().timestamp())
    with asgi_client(world.app) as client:
        feed = client.get(f"{MOCK_BASE}/v1/events?starting_after=1&limit=5").json()
        body = json.dumps(feed).encode()
        signed = client.post(f"{MOCK_BASE}/webhooks/sign?t={now}", content=body).json()
    accepted = call(
        world.app,
        "POST",
        f"/api/v1/webhooks/STRIPE/{receiver}",
        content=body,
        headers={signed["header"]: signed["signature"]},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["notifications"] == 4
    asked, cutoffs = _locked_while_it_applies(monkeypatch, world, attempts=2)
    finished = run(world, UUID(accepted.json()["job_id"]))
    assert len(asked) == 2 and asked[0] < cutoffs[0] < asked[1] < cutoffs[1], (asked, cutoffs)
    [batch] = world.rows(select(sync_run).where(sync_run.c.kind == "WEBHOOK_BATCH"))
    assert (batch["status"], finished["state"]) == ("FAILED", "FAILED")
    _told_by_the_rule(batch)
    assert [kind for kind, _ in _events(world)] == BOOKED
    assert _count(world, source_record) == 1 and _count(world, source_invoice) == 0
    assert _count(world, exception_item) == 0
    assert _checkpoint(world, target) == before
    polled, done = sync(world, target)
    assert polled["status"] == "SUCCEEDED", polled["problem"]
    counts = done["result"]["counts"]
    assert counts["fetched"] == 2 and counts["records"] == 2 and counts["failures"] == 0
    events = _events(world)
    assert [kind for kind, _ in events] == BOOKED + DOCUMENTS
    assert [stamp for _, stamp in events[2:]] == [asked[2], asked[2]] and asked[2] > cutoffs[1]


def test_a_reprocess_refused_twice_settles_nothing_and_is_asked_again(
    world: IntegrationWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 §16.14: a reprocess applies a stored record again, in a run of its own. The invoice
    arrived before its subscription and left the remediable item ``CONTRACT_NOT_FOUND`` naming
    its stored record; the subscription arrived, and its contract is active. The item's
    reprocess is refused twice — a period of QUAY-US locked in each of its apply transactions:
    its run ends FAILED with the rule's problem, the item is as it was — open, not marked as
    reprocessed — and nothing of the record is applied. Asked again, the reprocess applies the
    invoice after both locks and resolves the item."""
    target = _stripe(world)
    whole = world.app.state.mocks.adapters[st_mock.CODE].scenario.events
    paid = next(event for event in whole if event["ordinal"] == 2)
    _feed(world, [paid])
    early, _ = sync(world, target)
    assert early["status"] == "SUCCEEDED", early["problem"]
    [item] = world.rows(select(exception_item))
    assert (item["code"], item["disposition"], str(item["status"])) == (
        "CONTRACT_NOT_FOUND",
        "remediable",
        "OPEN",
    )
    late = {
        "ordinal": 3,
        "id": "evt_DEMO_LATE",
        "type": "customer.subscription.created",
        "object": "subscription",
        "object_id": "sub_DEMO0001",
        "version": "1",
    }
    _feed(world, [paid, late])
    booked, _ = sync(world, target)
    assert booked["status"] == "SUCCEEDED", booked["problem"]
    _activated(world)
    assert [kind for kind, _ in _events(world)] == BOOKED and _count(world, source_invoice) == 0
    asked, cutoffs = _locked_while_it_applies(monkeypatch, world, attempts=2)
    path = f"/api/v1/exceptions/{item['id']}/reprocess"
    requested = post(world.app, path, world.nikhil, {})
    assert requested.status_code == 202, requested.text
    failed = run(world, UUID(requested.json()["id"]))
    assert failed["state"] == "FAILED"
    assert len(asked) == 2 and asked[0] < cutoffs[0] < asked[1] < cutoffs[1], (asked, cutoffs)
    [refused_run] = world.rows(select(sync_run).where(sync_run.c.status == "FAILED"))
    _told_by_the_rule(refused_run)
    [still] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert (str(still["status"]), still["reprocessed_at"]) == ("OPEN", None)
    assert [kind for kind, _ in _events(world)] == BOOKED and _count(world, source_invoice) == 0
    again = post(world.app, path, world.nikhil, {})
    assert again.status_code == 202, again.text
    done = run(world, UUID(again.json()["id"]))
    counts = done["result"]["counts"]
    assert counts["reprocessed"] == 1 and counts["billing_events"] == 1 and counts["fetched"] == 0
    [settled] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert str(settled["status"]) == "RESOLVED" and settled["reprocessed_at"] is not None
    events = _events(world)
    assert [kind for kind, _ in events] == [*BOOKED, "BILLING_RECORDED"]
    assert events[2][1] == asked[2] and asked[2] > cutoffs[1]
