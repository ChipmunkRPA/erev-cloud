"""ERR-MAP-1 (D-98 candidate 141; 04 §15.2 rev 1.71; DG-KRN-ERR-02 rev 1.61): a lock wait that
outlives the platform's ``lock_timeout`` (10 s, ``db/session.py``) is answered BY NAME — 409
``lock-conflict`` with rule ``LOCK_TIMEOUT`` and its own detail, distinct from a deadlock's — never
``http.unhandled_error`` 500 (integrated batch #6 on 9e7d1031 measured two approvals answering
500 with 55P03 after 10.1 s). Two sessions: the holder keeps the contract's group row (the ruled
order's first lock) past ``lock_timeout``; the request's BILLING append waits on it
(participant-bound) until PostgreSQL cancels its statement. Nothing is saved. DB-bound, NOT RUN on
l12.
"""

from __future__ import annotations

import threading
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, contract_event
from erev_api.domain.contracts import repo
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import LOCK_CONFLICT_DETAIL, LOCK_TIMEOUT_DETAIL, RULE_LOCK_TIMEOUT
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    SeatWorld,
    activated_contract,
    booked_contract,
    computed,
    seat_body,
    seat_line,
    seat_world,
)
from support.http import HttpResponse, call
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import cookie_headers
from support.reference import post, slug

EVENTS: Final = "/api/v1/contracts/{contract_id}/events"
BILLING: Final = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-30",
    "payload": {
        "invoice_number": "INV-ERRMAP-1",
        "line_external_id": "INV-ERRMAP-1-1",
        "amount": {"amount": "1000.00", "currency": "USD"},
        "issue_date": "2026-09-01",
    },
}
LOCK_TIMEOUT_SECONDS: Final = 10.0  # db/session.py: -c lock_timeout=10000 and set_config per unit


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> SeatWorld:
    return seat_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _active(world: SeatWorld) -> UUID:
    line = seat_line("O1", seats="30", price="108000.00", start="2026-09-01", end="2029-08-31")
    body = seat_body(
        world.customers["C-09"], external_id="SF-ORD-ERRMAP", inception="2026-09-01", lines=[line]
    )
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    computed(world.place, UUID(str(booked.combination_group["id"])))
    return UUID(str(booked.contract["id"]))


def _events(world: SeatWorld, contract_id: UUID) -> list[str]:
    return [
        str(row["event_type"])
        for row in world.place.rows(
            select(contract_event.c.event_type)
            .where(contract_event.c.contract_id == contract_id)
            .order_by(contract_event.c.stream_version)
        )
    ]


def test_a_lock_wait_beyond_lock_timeout_is_the_named_lock_conflict(seats: SeatWorld) -> None:
    """The holder locks the contract's group row and KEEPS it; the request's append is observed
    waiting for it (participant-bound, in a ``combination_group`` statement), then PostgreSQL
    cancels the request's statement at ``lock_timeout`` (55P03): 409 ``lock-conflict``, rule
    ``LOCK_TIMEOUT``, the lock-timeout detail (not the deadlock's), no 500; the head and the event
    stream unchanged. No automatic retry is claimed or observed (one request, one response)."""
    contract_id = _active(seats)
    head = int(
        seats.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )
    events_before = _events(seats, contract_id)
    ctx = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = post(
                seats.app,
                EVENTS.format(contract_id=contract_id),
                seats.place.author,
                {"events": [BILLING]},
                if_match=f'"s{head}"',
            )
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    request = threading.Thread(target=run, name="lock-timeout-append")
    started = False
    try:
        with observing_checkouts() as backends:
            with tenant_session(ctx) as holder:
                holder_pid = backend_pid(holder)
                group_id = UUID(str(repo.get_contract(holder, contract_id)["combination_group_id"]))
                repo.lock_group(
                    holder, group_id
                )  # the ruled order's first lock, held past the timeout
                request.start()
                started = True
                blocked_pid, blocked_in = await_lock_wait(
                    holder,
                    holder_pid=holder_pid,
                    backends=backends,
                    timeout=20.0,
                    expect="combination_group",
                )
                assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
                # The holder keeps the row: the request must end on its own at lock_timeout.
                request.join(timeout=LOCK_TIMEOUT_SECONDS * 3)
                assert not request.is_alive(), "the request did not end at lock_timeout"
                holder.rollback()
    finally:
        if started:
            request.join(timeout=30)
    assert "error" not in outcome, outcome
    response = outcome["result"]
    assert (response.status_code, slug(response)) == (409, "lock-conflict"), response.text
    body = response.json()
    assert body["detail"] == LOCK_TIMEOUT_DETAIL and body["detail"] != LOCK_CONFLICT_DETAIL
    assert [error["rule_id"] for error in body["errors"]] == [RULE_LOCK_TIMEOUT], body
    assert body["code"] is None
    assert (
        int(
            seats.place.scalar(
                select(contract.c.head_stream_version).where(contract.c.id == contract_id)
            )
        )
        == head
    )
    assert _events(seats, contract_id) == events_before  # nothing saved


def test_the_same_key_runs_the_append_after_the_lock_conflict(seats: SeatWorld) -> None:
    """IDEM-LOCK-CONFLICT-1 on a real command (dev-guide DG-KRN-IDEM-03 rev 1.127; 04 DB-07 (3);
    supervisor ruling R-97 (6)): the append that met the held group row is answered 409
    ``lock-conflict`` at ``lock_timeout``; sent again with the SAME Idempotency-Key, body and
    ``If-Match`` once the holder is gone, it runs and is saved - no replay of the refusal.
    Fail-first: the second request was answered the stored 409 with ``Idempotent-Replay: true``
    and nothing was saved."""
    contract_id = _active(seats)
    head = int(
        seats.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )
    events_before = _events(seats, contract_id)
    ctx = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    author = seats.place.author
    headers = {
        **cookie_headers(author.token, author.csrf_token, key=False),
        "Idempotency-Key": "k-errmap-same-key-0001",
        "If-Match": f'"s{head}"',
    }

    def send() -> HttpResponse:
        return call(
            seats.app,
            "POST",
            EVENTS.format(contract_id=contract_id),
            json={"events": [BILLING]},
            headers=headers,
        )

    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = send()
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    request = threading.Thread(target=run, name="lock-conflict-same-key")
    started = False
    try:
        with observing_checkouts() as backends:
            with tenant_session(ctx) as holder:
                holder_pid = backend_pid(holder)
                group_id = UUID(str(repo.get_contract(holder, contract_id)["combination_group_id"]))
                repo.lock_group(holder, group_id)
                request.start()
                started = True
                blocked_pid, blocked_in = await_lock_wait(
                    holder,
                    holder_pid=holder_pid,
                    backends=backends,
                    timeout=20.0,
                    expect="combination_group",
                )
                assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
                request.join(timeout=LOCK_TIMEOUT_SECONDS * 3)
                assert not request.is_alive(), "the request did not end at lock_timeout"
                holder.rollback()
    finally:
        if started:
            request.join(timeout=30)
    assert "error" not in outcome, outcome
    refused = outcome["result"]
    assert (refused.status_code, slug(refused)) == (409, "lock-conflict"), refused.text
    assert "idempotent-replay" not in refused.headers
    assert _events(seats, contract_id) == events_before
    # The holder is gone: the same request - key, body and If-Match - now runs.
    again = send()
    assert again.status_code == 201, again.text
    assert "idempotent-replay" not in again.headers
    assert _events(seats, contract_id) == [*events_before, "BILLING_RECORDED"]
