"""Two-session interleaving in the activation shape — and, since P5-LOCK-R2 / R3, for the replace-
draft command, the shared helper that the estimate-approval hook uses and the record-events path.
The waiting request is observed through pg_stat_activity — bound to the participants: one of the
request's own backends (every connection it checks out of the app engine while the interleaving is
open, by ``pg_backend_pid``) blocked on a lock held by the holder's backend (``pg_blocking_pids``)
in a statement against the group row — before the interleaving step, never assumed from a sleep or
matched on any same-database waiter (dev-guide DG-KRN-DB-08 rev 1.36; D-98 candidates 101a, 101c
(d); lane P5 slices P5-LOCK-R1, R3b, R3c). A compute-path session holds the group lock — its first
lock — and then takes the contract row FOR UPDATE — its second — while a submit-activation request
runs in another connection. Under the ruled order the request waits on the group and the holder's
contract lock never waits; under the pre-1.36 inverse order the request had already locked the
contract and waited on the group, the holder's contract lock waited on the request, and PostgreSQL
aborted one side with a deadlock (SQLSTATE 40P01) — so this test fails deterministically on the old
order.

DB-bound (``committed_db``): written with the slice, NOT RUN on l12 (no lane database); the next
integrated batch or a DB lane measures it.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.domain.contracts import repo
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.factories import (
    J03World,
    SeatWorld,
    j03_world,
    seat_body,
    seat_line,
    seat_world,
    sf_ord_20417_body,
)
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.reference import post

CONTRACTS = "/api/v1/contracts"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def j03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> J03World:
    return j03_world(app, keyring, clock, files)


def test_activation_waits_for_the_group_lock_and_never_deadlocks_the_compute_order(
    j03: J03World,
) -> None:
    author = j03.place.author
    created = post(j03.app, CONTRACTS, author, sf_ord_20417_body(j03.customer_id))
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    response = _interleave(
        j03,
        contract_id,
        lambda: post(
            j03.app, f"{CONTRACTS}/{contract_id}/submit-activation", author, {}, if_match='"s1"'
        ),
    )
    # The request reached its own verdict after the locks were released: the J03 draft fails the
    # checklist (409) — what matters here is that it neither deadlocked nor ran ahead of the lock.
    assert response.status_code in (200, 202, 409), response.text


def _interleave(
    j03: J03World, contract_id: UUID, run_request: Callable[[], Any], *, settle: float = 20.0
) -> Any:
    """Hold the group lock (the compute path's first lock), start ``run_request`` in another
    connection, take the contract row (the compute path's second lock) — immediate under the ruled
    order, a 40P01 deadlock under the inverse order — release, and return the request's result."""
    ctx = DbContext(tenant_id=j03.place.tenant_id, user_id=None, entity_scope="*")
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = run_request()
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    with observing_checkouts() as backends:
        with tenant_session(ctx) as holder:
            holder_pid = backend_pid(holder)
            group_id = UUID(str(repo.get_contract(holder, contract_id)["combination_group_id"]))
            repo.lock_group(holder, group_id)
            request = threading.Thread(target=run, name="interleaved-request")
            request.start()
            # Deterministic and bound to the participants: PostgreSQL reports one of the request's
            # backends blocked by the holder's backend, in a statement against the group row (the
            # request's first lock under the ruled order; its _mark_dirty UPDATE under the old one).
            blocked_pid, blocked_in = await_lock_wait(
                holder, holder_pid=holder_pid, backends=backends, timeout=settle
            )
            assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
            assert "combination_group" in blocked_in.lower(), blocked_in
            started = time.monotonic()
            # The holder's second lock: immediate under the ruled order; under the pre-1.36 order
            # the request already held the contract row while waiting for the group — a 40P01
            # deadlock here.
            repo.get_contract(holder, contract_id, for_update=True)
            assert time.monotonic() - started < 1.0
            holder.rollback()
    request.join(timeout=30)
    assert not request.is_alive() and "error" not in outcome, outcome
    return outcome["result"]


def test_replace_draft_waits_for_the_group_lock_and_never_deadlocks(j03: J03World) -> None:
    """P5-LOCK-R2: ``POST /contracts/{id}/replace-draft`` under the same interleaving."""
    author = j03.place.author
    body = sf_ord_20417_body(j03.customer_id)
    created = post(j03.app, CONTRACTS, author, body)
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    response = _interleave(
        j03,
        contract_id,
        lambda: post(
            j03.app, f"{CONTRACTS}/{contract_id}/replace-draft", author, body, if_match='"s1"'
        ),
    )
    # The replacement ran to its own verdict after the locks were released (200 = replaced; a 4xx
    # would be its own validation, never a deadlock or a run ahead of the lock).
    assert response.status_code in (200, 409, 422), response.text


def test_shared_helper_waits_for_the_group_lock_under_real_locks(j03: J03World) -> None:
    """P5-LOCK-R2: ``repo.lock_group_then_contract`` — the helper the estimate-approval hook
    (``estimates._approve_version``) now calls — under the same interleaving, driven directly
    because the approval flow needs a submitted estimate version to reach the hook."""
    author = j03.place.author
    created = post(j03.app, CONTRACTS, author, sf_ord_20417_body(j03.customer_id))
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    ctx = DbContext(tenant_id=j03.place.tenant_id, user_id=None, entity_scope="*")

    def locked_read() -> tuple[UUID, dict[str, Any]]:
        with tenant_session(ctx) as session:
            group_id, row = repo.lock_group_then_contract(session, contract_id)
            session.rollback()
        return group_id, row

    group_id, row = _interleave(j03, contract_id, locked_read)
    assert (
        UUID(str(row["combination_group_id"])) == group_id and UUID(str(row["id"])) == contract_id
    )


BILLING = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-01",
    "payload": {
        "invoice_number": "INV-US-4001",
        "line_external_id": "INV-US-4001-1",
        "amount": {"amount": "1000.00", "currency": "USD"},
        "issue_date": "2026-09-01",
    },
}


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def test_record_events_waits_for_the_group_lock_and_never_deadlocks(seats: SeatWorld) -> None:
    """P5-LOCK-R3 (Codex packet 1124): the actual path — ``POST /contracts/{id}/events`` appends
    (``_raise_head`` locks the contract, ``_mark_dirty`` the group) while another session holds the
    group and then takes the contract row. Under the pre-1.36 order the request held the contract
    and waited for the group at ``_mark_dirty`` while the holder waited for the contract: a 40P01
    deadlock. Under the ruled order the request waits on the group first."""
    author = seats.place.author
    body = seat_body(
        seats.customers["C-09"],
        external_id="SF-ORD-10600",
        inception="2026-09-01",
        lines=[seat_line("O1", seats="10", price="12000.00", start="2026-09-01", end="2027-08-31")],
    )
    created = post(seats.app, CONTRACTS, author, body)
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    response = _interleave(
        seats,  # type: ignore[arg-type]  # the helper reads .app / .place only
        contract_id,
        lambda: post(
            seats.app,
            f"{CONTRACTS}/{contract_id}/events",
            author,
            {"events": [BILLING]},
            if_match='"s1"',
        ),
    )
    # The append happened — 201 appended, or 202 API-S-Job when the compute was deferred (04 §16.3
    # API-S-EventAppend; api/v1/events.py contract_events_append; batch #4 ruling: 200 was never a
    # valid response of this endpoint) — so the path that reaches _mark_dirty was exercised, and it
    # neither deadlocked nor ran ahead of the group lock.
    assert response.status_code in (201, 202), response.text
