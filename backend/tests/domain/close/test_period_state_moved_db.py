"""A command recorded before a period lock and committed after it is refused by name (PRD ERR-72,
rule ``PERIOD_STATE_MOVED``; 04 §14.1 "A command recorded before a lock" rev 1.157; 05 RCP-18 rev
1.96; dev-guide DG-CMD-10 rev 1.140; supervisor rulings R-105 (3) and of 2026-10-01 13:57;
register index 66).

A transaction stamps the event it records with its own start (04 DB-08). A lock decision that
begins after that start and commits before the transaction writes has frozen the period's
datasets without the event, at a cutoff the stamp precedes: the version the transaction then
wrote counted as known at the cutoff for every later reader, the frozen datasets did not hold it,
and the late entry report did not list the event — it was recorded before the lock's record.
``computation.persist`` therefore reads, once the window's rows are shared, the LOCK records of
the bundle's entities and books: one whose cutoff is later than the transaction's record instant
ends the command 409 ``lock-conflict`` before anything is written. Sent again, the command is
recorded after the lock and is a late event in every reader.

World: ``worlds.chk_010_position`` (POLICIES CHK-010) as ``test_close_run_gate.py`` builds it for
its interleaving witnesses — January 2026 of US01 in soft close on a succeeded close run, the
journal run through its life, the reconciliations reviewed, the lock requested. Marcus's approval
is the decision D. The late command T is ``POST /contracts/{id}/events`` on the two paths that
append and compute without an approval (BUILD_SPEC CTR-6; PRD ACT-10):

- a person's invoice of 1,000.00 on P2-MILESTONE dated 31 Jan 2026;
- an API client's report of the build of P3 at 75% on 31 Jan 2026.

A person's progress report is not such a path: it waits for another person, and while its request
is pending the lock decision of an entity the request names is refused by its
``APPROVALS_CLEARED`` gate. The request names the contracting entity; the lock of an entity that
only PERFORMS in the contract is not held by it, and there the approval — which appends and
computes in the decision's transaction — meets the same check and answers with the decision's
form of the sentence (the fourth witness, in PRD WLD-K-04).

Each T meets D in the two ways measured on main b90b74db (lane FIX-D2, 2026-10-01): T has built
its bundle and reaches the read of the window while D holds January's row, and waits there; or T
has recorded its event and builds its bundle only after D has committed.

Expected amounts are the documents': CHK-010 at 31 Jan 2026 holds a contract asset of 2,000.00;
the build at 75% instead of 50% is revenue of 2,000.00 x 0.25 = 500.00 more, which a computation
after January's lock posts in February with January as its origin (DG-KRN-TIME-04).

Two controls. The comparison is strict: under an application clock that stands still a command
recorded at the instant of a lock is saved (PRD WLD-K-01). And a computation that records nothing
is not judged: a recomputation that began before the lock and writes after it is stored, where a
command with an event of its own would be refused.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api import problems
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    api_token,
    approval_decision,
    approval_request,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    event_submission,
    period,
    period_lock,
    subledger_line,
    subledger_posting,
    tenant,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.contracts import bundles, computation
from erev_api.domain.platform import setup
from erev_api.domain.reports.outputs import utc_text
from erev_api.enums import ComputationTrigger
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import and_, func, insert, select
from sqlalchemy.orm import aliased
from support import close_runs as runs
from support import worlds
from support.close_world import (
    BOOK,
    close_run_succeeded_for,
    periods_closed_before,
    reviewed_reconciliations_for,
)
from support.db import TestDatabase
from support.factories import engine
from support.http import HttpResponse, call
from support.interleave import RequestBackends, await_lock_wait, backend_pid
from support.principals import cookie_headers
from support.reference import PERIODS, approve, assign, post, slug
from support.rows import api_client_values

pytestmark = pytest.mark.slow

US01 = worlds.US01
AVM_US = worlds.AVM_US
JANUARY = "FY2026-P01"
FEBRUARY = "FY2026-P02"
APRIL = "FY2026-P04"
MILESTONE = "P2-MILESTONE"
BUILD = "P3-BUILD"
JOIN_SECONDS = 120.0
WAIT_SECONDS = 30.0
# POLICIES CHK-010 at 31 Jan 2026 (module docstring).
CONTRACT_ASSET = "2000.00"
LATE_REVENUE = Decimal("500.00")
INVOICE: Mapping[str, Any] = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-01-31",
    "payload": {
        "invoice_number": "INV-POS-5",
        "line_external_id": "INV-POS-5-1",
        "obligation_key": MILESTONE,
        "amount": {"amount": "1000.00", "currency": "USD"},
        "issue_date": "2026-01-31",
    },
}
PROGRESS: Mapping[str, Any] = {
    "event_type": "PROGRESS_RECORDED",
    "effective_date": "2026-01-31",
    "payload": {
        "obligation_key": BUILD,
        "cumulative_progress_ratio": "0.75",
        "measure": "OUTPUT_PERCENT",
    },
}
# PRD WLD-K-04: O2 stands at 100% since 31 May 2026; the report of 30 Jun 2026 confirms it.
O2_CONFIRMED: Mapping[str, Any] = {
    "event_type": "PROGRESS_RECORDED",
    "effective_date": "2026-06-30",
    "payload": {
        "obligation_key": "O2",
        "cumulative_progress_ratio": "1",
        "measure": "OUTPUT_PERCENT",
    },
}
BALANCES: Mapping[str, Any] = {"entity_codes": [US01], "book": BOOK, "period_key": JANUARY}
CONTRACT_ROW = f"contract:{worlds.C_POS}:{US01}"
# Where the late command stands while the decision is taken.
WINDOW = "it waits at the read of the window"
BUNDLE = "it builds its bundle after the lock"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _present(world: worlds.ReportWorld) -> datetime:
    """The server's clock, which stamps ``recorded_at`` (04 DB-08)."""
    stamp = world.place.scalar(select(func.clock_timestamp()))
    assert isinstance(stamp, datetime)
    return stamp


@dataclass(frozen=True, slots=True)
class _Pending:
    """January of US01 with its lock requested on a succeeded close run."""

    world: worlds.ReportWorld
    request_id: str
    contract_id: UUID
    group_id: UUID
    period_id: UUID


def _pending(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> _Pending:
    """``worlds.chk_010_position`` with January in soft close, closed by its close run, the
    journal run through its life, the reconciliations reviewed and the lock requested: the
    decision is all that is left (the world of ``test_close_run_gate._january_lock_pending``;
    Marcus is verified where the decision is taken). Tenant setup is complete — while
    ``tenant.setup_completed_at`` is NULL an approval takes the tenant row ``FOR UPDATE``, a wait
    that would stand in for the one under test."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    booked = world.contracts[worlds.C_POS]
    state = worlds.period_state(world, US01, JANUARY)
    started = post(
        world.app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "January close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    run = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert run["status"] == "SUCCEEDED"
    world = runs.journal_posted(world, clock, run["journal_run_id"])
    state = worlds.period_state(world, US01, JANUARY)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )
    requested = post(
        world.app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": "January close complete"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    with world.place.uow() as uow:
        setup.evaluate_setup_completion(uow)
        uow.commit()
    (completed,) = _rows(world.tenant_id, select(tenant.c.setup_completed_at))
    assert completed["setup_completed_at"] is not None
    return _Pending(
        world=world,
        request_id=str(requested.json()["approval_request_id"]),
        contract_id=UUID(str(booked.contract["id"])),
        group_id=UUID(str(booked.combination_group["id"])),
        period_id=UUID(str(state["period"]["id"])),
    )


def _client_token(world: worlds.ReportWorld, clock: FrozenClock) -> str:
    """An API client of every entity that may record events, and one open token of it — put in
    place by its rows (04 T-PLT-15, T-PLT-16), as ``tests/api/test_periods_api.py`` does."""
    tenant_id = world.tenant_id
    token = f"erevt_{tenant_id.hex}_{secrets.token_urlsafe(32)}"
    scopes = ["contract.read", "event.record"]
    client = api_client_values(tenant_id, name="svc-delivery-feed", scopes=scopes)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(api_client).values(**client))
        session.execute(
            insert(api_token).values(
                tenant_id=tenant_id,
                id=new_id(),
                api_client_id=client["id"],
                token_sha256=hashlib.sha256(token.encode("ascii")).hexdigest(),
                scopes=scopes,
                issued_at=clock.now(),
                expires_at=clock.now() + timedelta(hours=1),
            )
        )
    return token


def _stored(pending: _Pending) -> dict[str, int]:
    """What a recorded and computed command leaves on the contract, its group and the ledger."""
    tenant_id = pending.world.tenant_id

    def count(table: Any, *where: Any) -> int:
        (row,) = _rows(tenant_id, select(func.count().label("n")).select_from(table).where(*where))
        return int(row["n"])

    (head,) = _rows(
        tenant_id,
        select(contract.c.head_stream_version).where(contract.c.id == pending.contract_id),
    )
    return {
        "head": int(head["head_stream_version"]),
        "events": count(contract_event, contract_event.c.contract_id == pending.contract_id),
        "computations": count(
            contract_computation, contract_computation.c.combination_group_id == pending.group_id
        ),
        "versions": count(
            contract_version, contract_version.c.combination_group_id == pending.group_id
        ),
        "lines": count(subledger_line),
    }


class _Late:
    """The late command, sent from a thread of its own and held once: before its computation
    builds its bundle — its event is recorded by then — or before the computation persists, with
    the bundle built. A request runs in a worker thread of the application, so the command is
    known by the arming, not by its thread: the first computation after it is the command's."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, send: Callable[[], HttpResponse], *, hold: str
    ) -> None:
        self.reached, self.go = threading.Event(), threading.Event()
        self.seen: dict[str, Any] = {}
        self.out: dict[str, Any] = {}
        self.armed = False
        build, persist = bundles.build, computation.persist
        late = self

        def stand(session: Any) -> None:
            late.seen["started"] = session.execute(
                select(func.transaction_timestamp())
            ).scalar_one()
            late.seen["pid"] = backend_pid(session)
            late.reached.set()
            assert late.go.wait(JOIN_SECONDS)

        def held_build(session: Any, *args: Any, **kwargs: Any) -> Any:
            pending_events = args[2] if len(args) > 2 else kwargs.get("pending_events", ())
            if late.armed and hold == BUNDLE and not late.seen and not pending_events:
                stand(session)
            return build(session, *args, **kwargs)

        def held_persist(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
            if late.armed and hold == WINDOW and not late.seen:
                stand(uow.session)
            return persist(uow, *args, **kwargs)

        monkeypatch.setattr(bundles, "build", held_build)
        monkeypatch.setattr(computation, "persist", held_persist)

        def run() -> None:
            try:
                late.out["response"] = send()
            except Exception as error:  # noqa: BLE001 - surfaced by the assertions
                late.out["error"] = error

        self.thread = threading.Thread(target=run, name="period-state-moved-late-command")


@dataclass(frozen=True, slots=True)
class _Met:
    """The late command's answer to a decision taken while it ran, and the lock it met."""

    pending: _Pending
    world: worlds.ReportWorld
    refused: HttpResponse
    before: Mapping[str, int]
    lock: Mapping[str, Any]
    send: Callable[[worlds.ReportWorld], HttpResponse]


def _met(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    *,
    event: Mapping[str, Any],
    by_client: bool,
    hold: str,
) -> _Met:
    """T — ``event`` through ``POST /contracts/{id}/events``, sent by the author or by an API
    client — is sent and held; D — Marcus's approval of January's lock — is taken while T stands
    there, at the server's present; T goes on. With ``hold`` ``WINDOW`` T is released inside D's
    freeze and is observed waiting for January's state row before D commits."""
    pending = _pending(app, keyring, clock, files, monkeypatch)
    world = pending.world
    token = _client_token(world, clock) if by_client else None
    before = _stored(pending)
    key = f"k-{uuid4()}"

    def send(now: worlds.ReportWorld) -> HttpResponse:
        """The one request, under one idempotency key however often it is sent."""
        author = now.place.author
        caller = (
            cookie_headers(author.token, author.csrf_token, key=False)
            if token is None
            else {"Authorization": f"Bearer {token}"}
        )
        return call(
            now.app,
            "POST",
            f"/api/v1/contracts/{pending.contract_id}/events",
            json={"events": [dict(event)]},
            headers={**caller, "Idempotency-Key": key, "If-Match": f'"s{before["head"]}"'},
        )

    late = _Late(monkeypatch, lambda: send(world), hold=hold)
    seen: dict[str, Any] = {}
    if hold == WINDOW:
        freeze_datasets = close_commands.snapshots.freeze_datasets

        def freeze_then_meet(d_uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
            datasets = freeze_datasets(d_uow, *args, **kwargs)
            if not seen:  # once: D holds January's row, has judged its gates and frozen
                backends = RequestBackends()
                backends.pids.add(int(late.seen["pid"]))
                late.go.set()
                _, seen["blocked_in"] = await_lock_wait(
                    d_uow.session,
                    holder_pid=backend_pid(d_uow.session),
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="period_state",
                )
                seen["waiting"] = late.thread.is_alive() and not late.out
            return datasets

        monkeypatch.setattr(close_commands.snapshots, "freeze_datasets", freeze_then_meet)
    late.armed = True
    late.thread.start()
    decided = None
    try:
        assert late.reached.wait(JOIN_SECONDS), (late.seen, late.out)
        # The decision's application instant is the server's present, as in production — after
        # T began. (The frozen clock lags the server by the time the world took to build.)
        clock.set(max(clock.now(), _present(world)) + timedelta(milliseconds=1))
        world = worlds.verified(world, clock, "marcus")
        decided = approve(world.app, pending.request_id, world.marcus)
    finally:
        late.go.set()
        late.thread.join(timeout=JOIN_SECONDS)
    assert decided is not None
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert not late.thread.is_alive() and "error" not in late.out, late.out
    if hold == WINDOW:
        assert seen["waiting"] is True and "for share" in seen["blocked_in"].lower(), seen
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"
    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.id, period_lock.c.created_at, period_lock.c.cutoff_known_at).where(
            period_lock.c.period_id == pending.period_id
        ),
    )
    # T began before the decision's cutoff: the lock froze its datasets without T's event
    assert late.seen["started"] < lock["cutoff_known_at"], (late.seen, lock)
    return _Met(
        pending=pending,
        world=world,
        refused=late.out["response"],
        before=before,
        lock=lock,
        send=send,
    )


def _refused_by_name(met: _Met) -> None:
    """409 ``lock-conflict`` with the rule and the sentence of PRD ERR-72, and nothing saved."""
    refused = met.refused
    assert refused.status_code == 409, refused.text  # the status first: a 201 has no slug
    assert slug(refused) == "lock-conflict", refused.text
    body = refused.json()
    assert body["detail"] == problems.PERIOD_STATE_MOVED_DETAIL
    assert [(error["rule_id"], error["message"]) for error in body["errors"]] == [
        (problems.RULE_PERIOD_STATE_MOVED, problems.PERIOD_STATE_MOVED_DETAIL)
    ]
    assert _stored(met.pending) == met.before


def _plain(value: Any) -> str:
    """A cell as text: a JSON money cell and a frozen file's amount compare by the amount."""
    if isinstance(value, Mapping) and "amount" in value:
        return str(value["amount"])
    return "" if value is None else str(value)


def _after_the_lock(
    world: worlds.ReportWorld, clock: FrozenClock, lock: Mapping[str, Any]
) -> worlds.ReportWorld:
    """The world once the server's present is past the lock's two instants — each is the later of
    the application instant and the transaction timestamp, and a second-factor step can put the
    first one ahead — with the application clock at that present and fresh sessions."""
    limit = time.monotonic() + 60.0
    while _present(world) <= max(lock["created_at"], lock["cutoff_known_at"]):
        assert time.monotonic() < limit
        time.sleep(0.25)
    clock.set(max(clock.now(), _present(world)) + timedelta(seconds=1))
    return worlds.resigned(world)


def _sent_again(met: _Met, clock: FrozenClock) -> tuple[worlds.ReportWorld, dict[str, Any]]:
    """The same request once more under the same idempotency key, after the lock — a
    ``lock-conflict`` is not kept (DG-KRN-IDEM-03), so it runs: 201, its event recorded after
    the lock's record, its version known after the lock's cutoff. Returns the world and the
    event's row with its computation id."""
    lock = met.lock
    world = _after_the_lock(met.world, clock, lock)
    again = met.send(world)
    assert again.status_code == 201, again.text
    assert "Idempotent-Replay" not in again.headers
    after = _stored(met.pending)
    assert (after["head"], after["events"]) == (met.before["head"] + 1, met.before["events"] + 1)
    assert (after["computations"], after["versions"]) == (
        met.before["computations"] + 1,
        met.before["versions"] + 1,
    )
    (event,) = _rows(
        world.tenant_id,
        select(
            contract_event.c.id,
            contract_event.c.stream_version,
            contract_event.c.recorded_at,
        ).where(
            contract_event.c.contract_id == met.pending.contract_id,
            contract_event.c.stream_version == after["head"],
        ),
    )
    assert event["recorded_at"] > lock["created_at"]
    (version,) = _rows(
        world.tenant_id,
        select(contract_version.c.known_at, contract_version.c.contract_computation_id)
        .where(contract_version.c.combination_group_id == met.pending.group_id)
        .order_by(contract_version.c.version_no.desc())
        .limit(1),
    )
    assert version["known_at"] == event["recorded_at"] > lock["cutoff_known_at"]
    return world, {**event, "computation_id": version["contract_computation_id"]}


def _readers_agree(met: _Met, world: worlds.ReportWorld, event: Mapping[str, Any]) -> None:
    """After the command was sent again (the application clock is past the lock's cutoff since
    then): the late entry report lists its event as entered after the lock, and the contract's
    balances as locked equal a historical run at the lock's cutoff — CHK-010's contract asset of
    2,000.00 in both."""
    late_run, late_rows = worlds.report_run(world, "late_entry_report", BALANCES)
    entered = [row for row in late_rows if _plain(row.get("section")) == "1"]
    assert [row["event_key"] for row in entered] == [
        f"event:{worlds.C_POS}:{event['stream_version']}"
    ]
    assert late_run["control_totals"]["section_1_count"] == 1
    lock = met.lock
    _, as_locked = worlds.report_run(
        world, "contract_balances", {**BALANCES, "period_lock_id": str(lock["id"])}
    )
    _, at_cutoff = worlds.report_run(
        world, "contract_balances", {**BALANCES, "known_at": utc_text(lock["cutoff_known_at"])}
    )
    (locked,) = [row for row in as_locked if row.get("row_key") == CONTRACT_ROW]
    (historical,) = [row for row in at_cutoff if row.get("row_key") == CONTRACT_ROW]
    assert {key: _plain(value) for key, value in locked.items()} == {
        key: _plain(historical.get(key)) for key in locked
    }
    assert _plain(locked["contract_asset"]) == CONTRACT_ASSET
    assert _plain(historical["contract_asset"]) == CONTRACT_ASSET


def _lines(world: worlds.ReportWorld, computation_id: Any) -> list[tuple[str, str | None, str]]:
    """(posting period, origin period, "<account role> <functional amount>") of each line a
    computation posted; a debit is positive."""
    origin = aliased(period)
    rows = _rows(
        world.tenant_id,
        select(
            period.c.period_key,
            origin.c.period_key.label("origin_key"),
            subledger_line.c.account_role,
            subledger_line.c.amount_functional,
        )
        .select_from(
            subledger_line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == subledger_line.c.tenant_id,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
            .join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
            .outerjoin(
                origin,
                and_(
                    origin.c.tenant_id == subledger_line.c.tenant_id,
                    origin.c.id == subledger_line.c.origin_period_id,
                ),
            )
        )
        .where(subledger_posting.c.contract_computation_id == UUID(str(computation_id))),
    )
    return [
        (
            str(row["period_key"]),
            None if row["origin_key"] is None else str(row["origin_key"]),
            f"{getattr(row['account_role'], 'value', row['account_role'])} "
            f"{Decimal(row['amount_functional']):.2f}",
        )
        for row in rows
    ]


@pytest.mark.parametrize("hold", [WINDOW, BUNDLE])
def test_an_invoice_recorded_before_the_lock_and_computed_after_it_is_refused_and_sent_again(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    hold: str,
) -> None:
    """Maya's invoice of 31 Jan 2026 is sent before January's lock is decided and its
    computation writes after the decision: 409 ``lock-conflict``, rule ``PERIOD_STATE_MOVED``,
    the sentence of PRD ERR-72, and no event, computation, version or line is left. The same
    request under the same idempotency key then runs and answers 201: its event is recorded
    after the lock's record, its version is known after the cutoff, the late entry report lists
    it as entered after the lock, and January's balances as locked equal a historical run at the
    cutoff. The workspace bills in its ERP: the invoice posts no line.

    Fail-first (measured on main b90b74db, cases M1 and M2): 201 at the first sending; the event
    stamped before the lock's cutoff and before its record; the frozen contract asset 2,000.00
    against 1,000.00 in a historical run at the cutoff; the late entry report's first section
    empty."""
    met = _met(app, keyring, clock, files, monkeypatch, event=INVOICE, by_client=False, hold=hold)
    _refused_by_name(met)
    world, event = _sent_again(met, clock)
    assert _lines(world, event["computation_id"]) == []
    _readers_agree(met, world, event)


@pytest.mark.parametrize("hold", [WINDOW, BUNDLE])
def test_a_progress_report_of_an_api_client_across_the_lock_is_refused_and_sent_again(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    hold: str,
) -> None:
    """An API client reports the build of P3 at 75% on 31 Jan 2026 — appended and computed
    directly (PRD ACT-10) — before January's lock is decided, and its computation writes after
    the decision: the same refusal, nothing left. Sent again it answers 201: the event is
    recorded after the lock, and its revenue of 500.00 is posted in February with January as its
    origin; the readers agree as for the invoice.

    Fail-first (measured on main b90b74db, cases M3 and M4): waiting at the window the command
    met the period guard — 409 ``period-closed`` without a sentence; with its bundle built after
    the lock it answered 201 and posted the 500.00 in February, its event stamped before the
    lock's record — a historical run at the cutoff then stated 2,500.00 against the frozen
    2,000.00."""
    met = _met(app, keyring, clock, files, monkeypatch, event=PROGRESS, by_client=True, hold=hold)
    _refused_by_name(met)
    world, event = _sent_again(met, clock)
    posted = _lines(world, event["computation_id"])
    assert posted and {key for key, _, _ in posted} == {FEBRUARY}  # nothing in the locked period
    assert [(origin, text) for _, origin, text in posted if text.startswith("REVENUE ")] == [
        (JANUARY, f"REVENUE {-LATE_REVENUE:.2f}")
    ]
    _readers_agree(met, world, event)


def test_a_command_recorded_at_the_instant_of_a_lock_is_saved(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The comparison is strict (04 §14.1 "A command recorded before a lock"). Under an
    application clock that stands still — here an hour ahead of the server's, so that it is the
    later instant of every stamp — January 2026 of AVM-US is locked (PRD WLD-K-01) and Maya then
    records a note at the same instant: the lock's cutoff EQUALS the command's record-time
    cutoff, and the command is saved. A lock is met only when it was decided after the command
    began.

    Pinned by mutation: with >= in the comparison this command is refused."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    clock.advance(timedelta(hours=1))
    world = worlds.resigned(world)
    _, world = worlds.period_locked(world, clock, entity_code=worlds.AVM_US, period_key=JANUARY)
    state = worlds.period_state(world, worlds.AVM_US, JANUARY)
    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.cutoff_known_at).where(
            period_lock.c.period_id == UUID(str(state["period"]["id"])),
            period_lock.c.entity_id == UUID(str(state["entity"]["id"])),
        ),
    )
    assert lock["cutoff_known_at"] == clock.now() > _present(world)
    noted = worlds._appended_through_api(
        world.place,
        UUID(str(world.contracts[worlds.K01].contract["id"])),
        {
            "event_type": "MEMO_UPDATED",
            "effective_date": "2026-02-10",
            "payload": {"memo_1": "Recorded at the instant of January's lock"},
        },
    )
    assert noted["computation"]["status"] == "SUCCEEDED", noted["computation"]


def test_a_manual_events_approval_across_the_lock_of_a_performing_entity_is_decided_again(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRD WLD-K-04: ``SF-ORD-UK-2001`` is contracted by AVM-UK, and AVM-US performs O1. Maya
    reports O2's progress again — a manual event, whose request names the contracting entity,
    AVM-UK. Priya's approval, which appends the event and computes the group of both entities,
    is in flight when Marcus locks April 2026 of AVM-US: that lock's ``APPROVALS_CLEARED`` gate
    counts the requests of AVM-US and not this one, so the decision locks. The approval's
    computation then meets the lock record of an entity of its bundle: 409 ``lock-conflict``
    under rule ``PERIOD_STATE_MOVED`` with the sentence in its decision form — "Decide again" —,
    the decision rolls back whole, the request stays pending and the submission is not applied.
    Priya decides again: approved, the submission applied, its event recorded after the lock.

    Fail-first: the approval answered 200 and appended the event with a stamp before the
    lock's cutoff."""
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = worlds.on_record_clock(k04.report, clock)
    state = worlds.period_state(world, AVM_US, APRIL)
    entity_id = UUID(str(state["entity"]["id"]))
    period_id = UUID(str(state["period"]["id"]))
    # April of AVM-US up to its lock request, by the steps of ``worlds.period_locked``
    periods_closed_before(
        world.place, app, world.maya, entity_id=entity_id, before=APRIL, entity_code=AVM_US
    )
    started = post(
        app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "April close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    _, world = worlds.posted_journal(world, clock, entity_code=AVM_US, period_key=APRIL)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=entity_id,
            period_id=period_id,
            now=clock.now(),
        )
        close_run_succeeded_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=entity_id,
            period_id=period_id,
            now=clock.now(),
        )
    state = worlds.period_state(world, AVM_US, APRIL)
    requested = post(
        app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": "April close complete"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    with world.place.uow() as uow:
        setup.evaluate_setup_completion(uow)
        uow.commit()
    # Maya's manual event, and what its request names
    created = worlds.submitted_manual_events(world.place, k04.contract_id, O2_CONFIRMED)
    request_id = UUID(created["approval_request_id"])
    submission_id = UUID(created["event_submission_id"])

    def waiting() -> tuple[str, str, int, int]:
        """(request status, submission status, decisions of the request, the stream's head)."""
        (request,) = _rows(
            world.tenant_id,
            select(approval_request.c.status).where(approval_request.c.id == request_id),
        )
        (submission,) = _rows(
            world.tenant_id,
            select(event_submission.c.status).where(event_submission.c.id == submission_id),
        )
        decisions = _rows(
            world.tenant_id,
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == request_id
            ),
        )
        (head,) = _rows(
            world.tenant_id,
            select(contract.c.head_stream_version).where(contract.c.id == k04.contract_id),
        )
        return (
            str(request["status"]),
            str(submission["status"]),
            len(decisions),
            int(head["head_stream_version"]),
        )

    (named,) = _rows(
        world.tenant_id,
        select(approval_request.c.entity_id, approval_request.c.entity_ids).where(
            approval_request.c.id == request_id
        ),
    )
    assert (named["entity_id"], list(named["entity_ids"] or [])) == (k04.uk_entity_id, [])
    before = waiting()
    assert before[:3] == ("PENDING", "SUBMITTED", 0)
    late = _Late(monkeypatch, lambda: approve(world.app, str(request_id), world.priya), hold=BUNDLE)
    late.armed = True
    late.thread.start()
    decided = None
    try:
        assert late.reached.wait(JOIN_SECONDS), (late.seen, late.out)
        clock.set(max(clock.now(), _present(world)) + timedelta(milliseconds=1))
        deciding = worlds.verified(world, clock, "marcus")
        lock_request = str(requested.json()["approval_request_id"])
        decided = approve(deciding.app, lock_request, deciding.marcus)
    finally:
        late.go.set()
        late.thread.join(timeout=JOIN_SECONDS)
    # the lock of the performing entity is not held by the request of the contracting one
    assert decided is not None
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, AVM_US, APRIL)["state"] == "closed"
    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.id, period_lock.c.created_at, period_lock.c.cutoff_known_at).where(
            period_lock.c.period_id == period_id, period_lock.c.entity_id == entity_id
        ),
    )
    assert late.seen["started"] < lock["cutoff_known_at"], (late.seen, lock)
    # the approval: refused in the decision's form, and nothing of it is left
    assert not late.thread.is_alive() and "error" not in late.out, late.out
    refused = late.out["response"]
    assert refused.status_code == 409, refused.text  # the status first: a 200 has no slug
    assert slug(refused) == "lock-conflict", refused.text
    assert refused.json()["detail"] == problems.PERIOD_STATE_MOVED_DECISION_DETAIL
    assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
        (problems.RULE_PERIOD_STATE_MOVED, problems.PERIOD_STATE_MOVED_DECISION_DETAIL)
    ]
    assert waiting() == before
    # decided again, after the lock
    world = _after_the_lock(world, clock, lock)
    again = approve(world.app, str(request_id), world.priya)
    assert (again.status_code, again.json()["status"]) == (200, "APPROVED"), again.text
    status, applied, decisions, head = waiting()
    assert (status, applied, decisions, head) == ("APPROVED", "APPLIED", 1, before[3] + 1)
    (event,) = _rows(
        world.tenant_id,
        select(contract_event.c.recorded_at).where(
            contract_event.c.contract_id == k04.contract_id,
            contract_event.c.stream_version == head,
        ),
    )
    assert event["recorded_at"] > lock["created_at"]


def test_a_recomputation_that_records_nothing_is_not_judged_beside_a_later_lock(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control of the rule's first condition. A recomputation of the group begins before
    January's lock is decided and records nothing. While the decision holds January's row — its
    gates judged, its datasets frozen — the recomputation builds its bundle and waits at the read
    of the window. The decision commits with a cutoff later than the recomputation's record-time
    cutoff: a command with an event of its own would be refused there. The recomputation holds
    none — every event of its bundle carries an earlier transaction's stamp — and is stored.

    Pinned by mutation: judged without the first condition, the recomputation is refused."""
    pending = _pending(app, keyring, clock, files, monkeypatch)
    world = pending.world
    arriving: dict[str, Any] = {}
    seen: dict[str, Any] = {}
    begun, go = threading.Event(), threading.Event()

    def recompute() -> None:
        try:
            with world.place.uow() as uow:
                session = uow.session
                arriving["started"] = session.execute(
                    select(func.transaction_timestamp())
                ).scalar_one()
                arriving["pid"] = backend_pid(session)
                begun.set()
                assert go.wait(JOIN_SECONDS)
                bundle = bundles.build(
                    session, pending.group_id, uow.now, (), ComputationTrigger.COMMAND
                )
                arriving["known_at"] = bundle.known_at
                arriving["own"] = [
                    event.event_key
                    for event in bundle.events
                    if event.recorded_at == arriving["started"]
                ]
                stored = computation.persist(uow, bundle, engine()(bundle))
                uow.commit()
                arriving["stored"] = dict(stored)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions
            arriving["error"] = error

    computing = threading.Thread(target=recompute, name="period-state-moved-recomputation")
    freeze_datasets = close_commands.snapshots.freeze_datasets

    def freeze_then_meet(d_uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        datasets = freeze_datasets(d_uow, *args, **kwargs)
        if not seen:  # once: the decision holds January's row, has judged its gates and frozen
            backends = RequestBackends()
            backends.pids.add(int(arriving["pid"]))
            go.set()
            _, seen["blocked_in"] = await_lock_wait(
                d_uow.session,
                holder_pid=backend_pid(d_uow.session),
                backends=backends,
                timeout=WAIT_SECONDS,
                expect="period_state",
            )
        return datasets

    monkeypatch.setattr(close_commands.snapshots, "freeze_datasets", freeze_then_meet)
    # Marcus's second factor first (it can move the application clock on), then the server's
    # present past that clock: every stamp below is then the server's, as in production
    deciding = worlds.verified(world, clock, "marcus")
    limit = time.monotonic() + 60.0
    while _present(world) <= clock.now():
        assert time.monotonic() < limit
        time.sleep(0.25)
    computing.start()
    decided = None
    try:
        assert begun.wait(JOIN_SECONDS), arriving
        clock.set(_present(world) + timedelta(milliseconds=1))
        decided = approve(deciding.app, pending.request_id, deciding.marcus)
    finally:
        go.set()
        computing.join(timeout=JOIN_SECONDS)
    assert decided is not None
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert not computing.is_alive() and "error" not in arriving, arriving
    assert "for share" in seen["blocked_in"].lower(), seen
    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.cutoff_known_at).where(period_lock.c.period_id == pending.period_id),
    )
    # the lock's cutoff is later than the recomputation's record-time cutoff, and the
    # recomputation recorded no event of its bundle
    assert arriving["started"] <= arriving["known_at"] < lock["cutoff_known_at"], (arriving, lock)
    assert arriving["own"] == []
    stored = arriving["stored"]
    assert (stored["status"], stored["replayed"]) == ("SUCCEEDED", False)
    assert stored["known_at"] < arriving["started"]  # the stamp of an earlier transaction's event
