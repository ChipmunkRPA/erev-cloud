"""LED-SEAL-REOPEN-RACE-1: a posting is sealed over its lines as they are STORED (supervisor ruling
R-97 (1) of 2026-09-30 — DEFECT of ledger integrity; finding F2 of the independent review of
revision 0084; 04 §14.1 DB-06 note, T-SL-02 and T-SL-04 rev 1.140; dev-guide DG-CMD-10 rev 1.123;
REQ-JE-006). PostgreSQL-bound: two-session interleavings bound to their participants
(``support.interleave``).

The DB-07 guard decides ``subledger_line.is_post_reopen`` from the period's state row, which it
reads ``FOR SHARE``: a line that reaches the guard while a change of the state is in flight waits
and is stored with the state the change COMMITS. Until this slice ``subledger.post`` sealed a value
of its own, read without a lock before the insert. When the two differed the seal did not match
the stored posting and ``verify_ledger_chain`` failed at that sequence for good — the rows are
append-only. Revision 0084 made the divergence certain: the insert now waits for the change.

Since revision 0113 (item REOPEN-CLOSING-FLAG-1, lane SECFIX-CLO; supervisor ruling R-117 (c);
04 DB-07 and T-SL-04 rev 1.184) the guard reads the flag from the period's current lock record —
a ``REOPEN``: locked once and not locked now — and not from the state literal. Start-close
therefore no longer changes what the guard stores: the lines of the first test are post-reopen
lines although the guard read ``closing`` after its wait (it stored false there until then), and
that interleaving no longer tells a writer that seals its own reading from one that seals the
stored value. The reopen approval, which writes the ``REOPEN`` record, still moves the flag: the
second test is the fail-first witness of R-97 (1).

World: WLD-K-01 (``SF-ORD-10001``) through 31 Aug 2026, closed on the record-time clock
(``support.worlds.on_record_clock``, as the report tests close their periods). August of AVM-US is
closed through the product (``support.worlds.period_locked``: soft close, the journal run through
its life, the lock request and Marcus's approval) and its reopen is requested by Priya and approved
by Marcus — one approval of two. The two changes of the state under test are the product's own:
the ``start_close`` command and the reopen decision of ``POST /approvals/{id}/approve``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import period_state, subledger_line, subledger_posting_seal, tenant
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates
from erev_api.domain.journals import subledger
from erev_api.domain.platform import setup
from erev_api.enums import ControlResult, PeriodState, SubledgerPostingKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.periods import PeriodStartCloseIn
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import select
from support.close_world import actor_with_role
from support.db import TestDatabase
from support.factories import booked_contract, computed
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import Actor
from support.reference import PERIODS, approve, assign, post
from support.worlds import (
    AUGUST_2026,
    AVM_US,
    K01,
    ReportWorld,
    k01_body,
    k01_pellworth,
    on_record_clock,
    period_locked,
    verified,
)
from support.worlds import (
    period_state as period_shown,
)

BOOK: Final = "ASC606"
LATE: Final = "LATE-ARRIVAL-01"
REASON: Final = "Costs of 20,500.00 incurred on 29 Aug 2026 were omitted."
JOIN_SECONDS: Final = 120.0
WAIT_SECONDS: Final = 30.0


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@dataclass(frozen=True)
class August:
    """WLD-K-01 with August of AVM-US ``closed`` and its reopen request one approval short."""

    world: ReportWorld
    state_id: UUID
    period_id: UUID
    reopen_request_id: str
    second_approver: Actor


def _session(world: ReportWorld) -> Any:
    return tenant_session(DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*"))


def _state(world: ReportWorld, state_id: UUID) -> str:
    with _session(world) as session:
        stored = session.execute(
            select(period_state.c.state).where(period_state.c.id == state_id)
        ).scalar_one()
    return str(getattr(stored, "value", stored))


def _setup_completed(world: ReportWorld) -> None:
    """Tenant setup complete before an interleaving: while ``tenant.setup_completed_at`` is NULL a
    decision takes the tenant row ``FOR UPDATE`` after its hook, which waits for every open
    transaction that inserted a row of the tenant — the posting under test among them."""
    with world.place.uow() as uow:
        setup.evaluate_setup_completion(uow)
        uow.commit()
    with _session(world) as session:
        completed = session.execute(
            select(tenant.c.setup_completed_at).where(tenant.c.id == world.tenant_id)
        ).scalar_one()
    assert completed is not None


@pytest.fixture
def august(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> August:
    files = LocalFileStore(app_settings.file_root)
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 8, 31))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run and the reopen
    world = on_record_clock(world, clock)  # a close runs on the record-time clock
    _, world = period_locked(world, clock, entity_code=AVM_US, period_key=AUGUST_2026)
    _setup_completed(world)
    second = actor_with_role(app, clock, world.tenant_id, "controller", name="elena")
    shown = period_shown(world, AVM_US, AUGUST_2026)
    state_id = UUID(str(shown["id"]))
    world = verified(world, clock, "priya")
    requested = post(
        app,
        f"{PERIODS}/{state_id}/request-reopen",
        world.priya,
        {"reason_code": "ERROR_CORRECTION", "comment": REASON},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    world = verified(world, clock, "marcus")
    first = approve(app, request_id, world.marcus)
    assert (first.status_code, first.json()["status"]) == (200, "PENDING"), first.text
    assert _state(world, state_id) == PeriodState.CLOSED.value  # one approval of two
    return August(
        world=world,
        state_id=state_id,
        period_id=UUID(str(shown["period"]["id"])),
        reopen_request_id=request_id,
        second_approver=second,
    )


def _verified(world: ReportWorld) -> subledger.LedgerChainVerification:
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return subledger.verify_ledger_chain(session, book_code=BOOK)


def _sealed(world: ReportWorld, posting_id: UUID, period_id: UUID) -> tuple[int, set[bool]]:
    """The chain position of a posting and the ``is_post_reopen`` values its lines of the period
    are stored with."""
    with _session(world) as session:
        chain_seq = session.execute(
            select(subledger_posting_seal.c.chain_seq).where(
                subledger_posting_seal.c.subledger_posting_id == posting_id
            )
        ).scalar_one()
        flags = set(
            session.scalars(
                select(subledger_line.c.is_post_reopen).where(
                    subledger_line.c.subledger_posting_id == posting_id,
                    subledger_line.c.period_id == period_id,
                )
            )
        )
    return int(chain_seq), {bool(flag) for flag in flags}


def _intact(world: ReportWorld) -> tuple[ControlResult, int | None, Any]:
    found = _verified(world)
    return found.result, found.first_failure_seq, found.failure_detail


INTACT: Final = (ControlResult.PASS, None, None)


def test_r97_1_a_posting_beside_start_close_is_sealed_over_the_lines_as_stored(
    august: August,
) -> None:
    """August is ``reopened``. T1 — the product's ``start_close`` — has taken the state row and
    moved it to ``closing``, NOT committed. T2 — the production computation of a second contract,
    whose lines reach back into August — is observed WAITING for that row, blocked by T1. T1
    commits. The guard read ``closing`` after the wait; T2's lines of August
    are post-reopen lines all the same — August stays under its ``REOPEN`` record through the
    soft close (revision 0113, supervisor ruling R-117 (c); while the guard stored the state
    literal these lines were stored false) — and the posting's seal matches what is stored: the
    ledger chain verifies.

    Where T2 waits (STALE EXPECTATION, item CLO-GATE-RUN-1; 04 rev 1.172 §14.1 "DB-07 row lock
    and lock order"; supervisor ruling of 2026-10-01 02:35). August was locked on a close run and
    is postable again, so T2 is inside that run's window: it takes the state row ``FOR SHARE`` in
    the read that finds the window, before it writes anything, and waits there. Until then it
    waited for the same row in its INSERT of subledger lines, where the DB-07 guard takes it;
    the guard now finds the row already shared by its own transaction.

    This interleaving was the fail-first of R-97 (1) while the two readings differed (``post``
    sealed the flag it had read before the insert — ``reopened``, true — over lines stored
    false). Under revision 0113 both are true, so it no longer fails first; the reopen approval
    of the next test does."""
    world = august.world
    body = k01_body(UUID(str(world.contracts[K01].contract["customer_id"])))
    body["external_id"] = LATE
    body["lines"] = [body["lines"][0]]
    late = booked_contract(world.place, body, activate=True)  # booked and activated, NOT computed
    group_id = UUID(str(late.combination_group["id"]))
    reopened = approve(world.app, august.reopen_request_id, august.second_approver)
    assert reopened.status_code == 200, reopened.text
    assert _state(world, august.state_id) == PeriodState.REOPENED.value
    assert _intact(world) == INTACT
    outcome: dict[str, Any] = {}

    def compute() -> None:
        try:
            outcome["stored"] = computed(world.place, group_id)[2]
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    poster = threading.Thread(target=compute, name="seal-race-computation")
    held = world.place.uow()
    uow = held.__enter__()
    started = False
    try:
        close_commands.start_close(  # T1: the state row FOR UPDATE, reopened → closing, in flight
            uow,
            state_id=august.state_id,
            body=PeriodStartCloseIn(comment="August close, again"),
            check_version=lambda actual: None,
        )
        with observing_checkouts() as backends:
            holder_pid = backend_pid(uow.session)
            poster.start()
            started = True
            blocked_pid, blocked_in = await_lock_wait(
                uow.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=WAIT_SECONDS,
                expect="period_state",
            )
        assert blocked_pid != holder_pid and "for share" in blocked_in.lower(), blocked_in
        assert poster.is_alive() and not outcome
        assert _state(world, august.state_id) == PeriodState.REOPENED.value  # as committed
        uow.commit()  # T1 commits while the posting waits for it
    finally:
        held.__exit__(None, None, None)
        if started:
            poster.join(timeout=JOIN_SECONDS)
    assert not poster.is_alive() and "error" not in outcome, outcome
    assert _state(world, august.state_id) == PeriodState.CLOSING.value
    posting_id = UUID(str(outcome["stored"]["subledger_posting_ids"][BOOK]))
    chain_seq, flags = _sealed(world, posting_id, august.period_id)
    assert flags == {True}  # under the REOPEN record, though the guard read ``closing``
    assert _intact(world) == INTACT, (chain_seq, _verified(world))


def test_r97_1_a_posting_beside_a_reopen_approval_is_sealed_over_the_lines_as_stored(
    august: August, monkeypatch: pytest.MonkeyPatch
) -> None:
    """August is ``closed``. The second Controller's approval of the reopen — the real decision —
    has written its ``REOPEN`` record and moved the state to ``reopened``, NOT committed, when
    ``subledger.post`` of a reversal of K-01's two lines of August reaches the guard: it is
    observed WAITING in its INSERT of subledger lines, blocked by the decision. The decision
    commits. The lines are stored as the guard read the state after its wait — ``reopened``:
    post-reopen lines (REQ-CLS-011) — and the posting's seal matches what is stored.

    Fail-first (``post`` seals the flag it read before the insert — ``closed``, false):
    ``verify_ledger_chain`` FAILS at this posting's sequence."""
    world = august.world
    group_id = UUID(str(world.contracts[K01].combination_group["id"]))
    with _session(world) as session:
        originals = [
            dict(row)
            for row in session.execute(
                select(subledger_line).where(subledger_line.c.period_id == august.period_id)
            ).mappings()
        ]
    assert len(originals) == 2  # K-01's revenue of August and its contract liability
    lines = [
        {
            **{name: row[name] for name in subledger.LINE_MEMBERS},
            "id": new_id(),
            "amount_txn": -row["amount_txn"],
            "amount_functional": -row["amount_functional"],
        }
        for row in originals
    ]
    posting: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def reverse() -> None:
        try:
            with world.place.uow() as uow:
                posting["posted"] = subledger.post(
                    uow,
                    book_code=BOOK,
                    posting_kind=SubledgerPostingKind.VOID_REVERSAL,
                    idempotency_key=f"r97-1:reversal:{august.period_id}",
                    description="R-97 (1) witness: K-01's August lines reversed",
                    lines=lines,
                    combination_group_id=group_id,
                )
                uow.commit()
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            posting["error"] = error

    poster = threading.Thread(target=reverse, name="seal-race-reversal")
    reopen_reconciliations = close_commands._reopen_reconciliations

    def reopen_then_meet_the_posting(uow: UnitOfWork, scope: gates.PeriodScope) -> int:
        moved = reopen_reconciliations(uow, scope)
        if poster.ident is None:  # once: the posting arrives after the state moved
            seen["state_in_the_decision"] = str(
                uow.session.execute(
                    select(period_state.c.state).where(period_state.c.id == august.state_id)
                ).scalar_one()
            )
            with observing_checkouts() as backends:
                decision_pid = backend_pid(uow.session)
                poster.start()
                _, seen["blocked_in"] = await_lock_wait(
                    uow.session,
                    holder_pid=decision_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="subledger_line",
                )
            seen["waiting"] = poster.is_alive() and not posting
        return moved

    monkeypatch.setattr(close_commands, "_reopen_reconciliations", reopen_then_meet_the_posting)
    assert _intact(world) == INTACT
    try:
        decided = approve(world.app, august.reopen_request_id, august.second_approver)
    finally:
        if poster.ident is not None:
            poster.join(timeout=JOIN_SECONDS)
    assert decided.status_code == 200, decided.text
    assert not poster.is_alive() and seen.get("waiting") is True, (seen, posting)
    assert "error" not in posting, posting
    assert seen["state_in_the_decision"].endswith("reopened"), seen
    assert "insert into" in seen["blocked_in"].lower(), seen["blocked_in"]
    assert _state(world, august.state_id) == PeriodState.REOPENED.value
    posted = posting["posted"]
    chain_seq, flags = _sealed(world, posted.posting_id, august.period_id)
    assert chain_seq == posted.chain_seq and flags == {True}  # the guard read ``reopened``
    assert _intact(world) == INTACT, (chain_seq, _verified(world))
