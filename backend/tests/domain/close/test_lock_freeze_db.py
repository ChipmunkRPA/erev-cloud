"""The period lock's freeze cutoff, its coverage guard, its named refusals and its serialisation
against postings — DB witnesses of supervisor rulings R-19, R-31, R-40 (b) / (c) and R-42 (d) / (e)
(2026-09-30; security finding SC-1; ENGINE_SPEC_B S15-R-18, S15-R-18c; 04 DB-07, T-CLS-04,
T-CLS-05; 03 REQ-CLS-002, REQ-CLS-009, REQ-CLS-010). DB-bound.

The world is WLD-K-01 (``SF-ORD-10001``) through 31 Aug 2026 on the FROZEN application clock
(2026-09-12T12:00Z) — no move onto the record-time clock. Its subledger and journal rows carry that
clock; its contract version is known at the SERVER clock of the run (``contract_version.known_at``;
DB-08), days later. August is locked through the public path: start-close, the period's journal
really calculated and acknowledged, the reviewed reconciliations, ``request_lock`` and a second
Controller's approval.

Until R-19 the decision froze at the application clock alone: the version-based datasets were
frozen EMPTY beside a populated journal population and the period closed certified (lane FIX-D2
slice 1 finding; ``test_lock.py::test_contract_balances_snapshot_k01`` runs its close on the
record-time clock for that reason). The witnesses below keep the frozen clock.

Until revision 0084 a posting was not serialised against the decision (SC-1): the DB-07 guards
read the period's state without a lock, so a posting in flight at the decision committed after it
— the security review's two-session proof, ``.run/sec/sec-close/test_poc_lock_race.py``, inverted
here — and a posting could commit into the period while the lock was being decided (measured in
this lane: August went from 2 to 4 lines under a 200). The ``sc1`` witnesses are two-session
interleavings bound to their participants (``support.interleave``); the row lock itself is
witnessed in ``tests/pg/test_period_guard_row_lock.py``.
"""

from __future__ import annotations

import csv
import io
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    contract_version,
    control_execution,
    file_object,
    ledger_chain_head,
    lock_snapshot,
    period_lock,
    period_state,
    subledger_line,
    subledger_posting_seal,
    tenant,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import freeze, gates
from erev_api.domain.contracts import bundles, computation
from erev_api.domain.journals import subledger
from erev_api.domain.platform import setup
from erev_api.domain.reports import snapshots as registry
from erev_api.enums import (
    ComputationTrigger,
    ContractEventType,
    FilePurpose,
    LockKind,
    PeriodState,
    SnapshotKind,
    SubledgerPostingKind,
)
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore, open_file
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from erev_api.schemas.periods import PeriodLockRequestIn
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import exc, func, select
from sqlalchemy.orm import Session
from support.close_world import (
    JOURNAL_RUN_ID_HEADER,
    JOURNAL_RUNS,
    acknowledge_run,
    close_run_succeeded_for,
    periods_closed_before,
    reviewed_reconciliations_for,
)
from support.db import TestDatabase
from support.factories import appended, booked_contract, computed, engine
from support.interleave import (
    LOCKS_OF,
    await_lock_wait,
    backend_pid,
    format_lock_rows,
    fresh_activity,
    observing_checkouts,
)
from support.principals import Actor, colleague, enrolled
from support.reference import PERIODS, approve, assign, periods, post, slug
from support.worlds import (
    AUGUST_2026,
    AVM_US,
    K01,
    K04,
    SEPTEMBER_2026,
    ReportWorld,
    k01_body,
    k01_pellworth,
    k04_saltmarsh,
    run_now,
)

BOOK: Final = "ASC606"
K01_AUGUST: Final = "39708.49"  # PRD WLD-X-03
TWELVE_KINDS: Final = tuple(kind.value for kind in SnapshotKind)
NOT_LOCKED: Final = "FY2026-P08 of AVM-US in book ASC606 is not locked: "


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@dataclass(frozen=True)
class Close:
    """August of AVM-US in soft close with a pending lock request and a Controller to decide."""

    world: ReportWorld
    state_id: UUID
    period_id: UUID
    request_id: UUID
    controller: Actor
    t0: datetime  # the frozen application clock of the world and of the decision


def _session(world: ReportWorld) -> Any:
    return tenant_session(DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*"))


@pytest.fixture
def close(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> Close:
    files = LocalFileStore(app_settings.file_root)
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 8, 31))
    maya = world.maya
    # PRD WLD-P-02 / BR-CLS-08 (supervisor ruling R-6): K-01's January to July are closed before
    # August is brought to its lock — fixture state; their sealed lines stay as they are.
    periods_closed_before(world.place, app, maya, entity_id=world.entity_id, before=AUGUST_2026)
    (august,) = [
        item
        for item in periods(app, maya, entity=AVM_US)
        if item["period"]["period_key"] == AUGUST_2026
    ]
    started = post(
        app,
        f"{PERIODS}/{august['id']}/start-close",
        maya,
        {"comment": "August close"},
        if_match=f'"r{august["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    period_id = UUID(str(august["period"]["id"]))
    requested = post(app, JOURNAL_RUNS, maya, {"entity_code": AVM_US, "period_key": AUGUST_2026})
    assert requested.status_code == 202, requested.text
    calculated = run_now(world, UUID(str(requested.json()["id"])))
    assert calculated["state"] == "SUCCEEDED", calculated
    with _session(world) as session:
        acknowledge_run(
            session, UUID(str(requested.headers[JOURNAL_RUN_ID_HEADER])), now=clock.now()
        )
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=world.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
        # fixture state for the gate CLOSE_RUN_COMPLETED (supervisor ruling R-114 (b))
        close_run_succeeded_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=world.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
    with world.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=UUID(str(august["id"])),
            body=PeriodLockRequestIn(certification_comment="August 2026 close complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    someone = colleague(world.tenant_id, "cora")
    assign(someone, "controller")
    return Close(
        world=world,
        state_id=UUID(str(august["id"])),
        period_id=period_id,
        request_id=UUID(str(out.approval_request_id)),
        controller=enrolled(app, clock, someone),  # the enrolment is the fresh TOTP (BR-PLT-06)
        t0=clock.now(),
    )


def _value(stored: Any) -> str:
    return str(getattr(stored, "value", stored))


def _observed(close: Close) -> dict[str, Any]:
    """Everything a lock decision writes, read back."""
    with _session(close.world) as session:

        def count(table: Any, *where: Any) -> int:
            return int(
                session.execute(select(func.count()).select_from(table).where(*where)).scalar_one()
            )

        return {
            "state": _value(
                session.execute(
                    select(period_state.c.state).where(period_state.c.id == close.state_id)
                ).scalar_one()
            ),
            "locks": count(period_lock, period_lock.c.period_id == close.period_id),
            "snapshots": count(lock_snapshot),
            "dataset_files": count(
                file_object, file_object.c.purpose == FilePurpose.SNAPSHOT_DATASET.value
            ),
            "decisions": count(
                approval_decision, approval_decision.c.approval_request_id == close.request_id
            ),
            "request_status": _value(
                session.execute(
                    select(approval_request.c.status).where(
                        approval_request.c.id == close.request_id
                    )
                ).scalar_one()
            ),
        }


NOTHING_WRITTEN: Final = {
    "state": PeriodState.CLOSING.value,
    "locks": 0,
    "snapshots": 0,
    "dataset_files": 0,
    "decisions": 0,
    "request_status": "PENDING",
}


def _refused(close: Close, rule_id: str) -> list[str]:
    """The decision answers 409 ``invalid-transition`` by name and writes nothing: the period
    stays in soft close and the request stays pending. Returns the ``errors[]`` messages."""
    decided = approve(close.world.app, str(close.request_id), close.controller)
    assert (decided.status_code, slug(decided)) == (409, "invalid-transition"), decided.text
    problem = decided.json()
    assert str(problem["detail"]).startswith(NOT_LOCKED), problem["detail"]
    assert {error["rule_id"] for error in problem["errors"]} == {rule_id}
    assert _observed(close) == NOTHING_WRITTEN
    return [str(error["message"]) for error in problem["errors"]]


def _august_lines(close: Close) -> int:
    with _session(close.world) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(subledger_line)
                .where(subledger_line.c.period_id == close.period_id)
            ).scalar_one()
        )


def _frozen(session: Session, close: Close, lock_id: UUID) -> dict[str, list[dict[str, str]]]:
    """The rows of each dataset the lock stored, read back from the file store."""
    found: dict[str, list[dict[str, str]]] = {}
    for kind, file_id in session.execute(
        select(lock_snapshot.c.snapshot_kind, lock_snapshot.c.file_id).where(
            lock_snapshot.c.period_lock_id == lock_id
        )
    ):
        place = close.world.place
        _, stream = open_file(session, UUID(str(file_id)), files=place.files, keyring=place.keyring)
        with stream:
            text = stream.read().decode("utf-8")
        found[_value(kind)] = [dict(row) for row in csv.DictReader(io.StringIO(text))]
    return found


# --- (a) the freeze cutoff ------------------------------------------------------------------------


def test_r19_the_lock_freezes_the_versions_recorded_on_the_server_clock(close: Close) -> None:
    """R-19 (a): the cutoff is the later of the decision's application instant and its transaction
    timestamp, so the contract version known at the server clock is inside it. All twelve
    datasets are frozen with the period's real populations — CONTRACT_BALANCES holds
    ``SF-ORD-10001`` at 39,708.49 (WLD-X-03) beside the journal population — and the cutoff is on
    the lock (``period_lock.cutoff_known_at``, R-40 (c)), on its audit event and on its CTL-016
    evidence. Fail-first: frozen at the application clock, CONTRACT_BALANCES, WATERFALL, RPO and
    both rollforwards were empty, and the lock certified; the lock row had no cutoff column."""
    decided = approve(close.world.app, str(close.request_id), close.controller)
    assert decided.status_code == 200, decided.text
    with _session(close.world) as session:
        lock = (
            session.execute(
                select(period_lock).where(
                    period_lock.c.period_id == close.period_id,
                    period_lock.c.kind == LockKind.LOCK.value,
                )
            )
            .mappings()
            .one()
        )
        lock_id = UUID(str(lock["id"]))
        frozen = _frozen(session, close, lock_id)
        known_at = session.execute(select(func.max(contract_version.c.known_at))).scalar_one()
        audited = session.execute(
            select(audit_event.c.after).where(
                audit_event.c.action == close_commands.LOCK_ACTION,
                audit_event.c.object_id == lock_id,
            )
        ).scalar_one()
        evidence = session.execute(
            select(control_execution.c.detail).where(
                control_execution.c.run_ref_id == close.request_id
            )
        ).scalar_one()
    assert sorted(frozen) == sorted(TWELVE_KINDS)
    (balance,) = frozen[SnapshotKind.CONTRACT_BALANCES.value]
    assert (balance["contract_external_id"], Decimal(balance["contract_liability"])) == (
        K01,
        Decimal(K01_AUGUST),
    )
    for kind in (SnapshotKind.WATERFALL, SnapshotKind.RPO, SnapshotKind.JE_POPULATION):
        assert frozen[kind.value], kind.value  # version-based and line-based kinds both hold rows
    by_contract = [
        row
        for row in frozen[SnapshotKind.CONTRACT_BALANCE_ROLLFORWARD.value]
        if row["contract_external_id"]
    ]
    assert [row["contract_external_id"] for row in by_contract] == [K01]
    # the cutoff: after the application instant the lock row carries, at or after the version;
    # R-40 (c): it is part of the lock record, and the audit event and the evidence carry the same
    cutoff = lock["cutoff_known_at"]
    assert lock["created_at"] == close.t0  # the decision's application instant, unchanged
    assert cutoff >= known_at > close.t0
    assert audited["cutoff_known_at"] == cutoff.isoformat() == evidence["cutoff_known_at"]
    assert _observed(close)["state"] == PeriodState.CLOSED.value


# --- (b) the coverage guard -----------------------------------------------------------------------


def test_r19_a_freeze_at_the_application_clock_alone_is_refused_by_name(
    close: Close, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-19 (b): with the former cutoff — the application clock alone — the contract's lines of
    the period are within the cutoff and its version is not: the lock is refused naming the
    contract, and nothing is written. The same request is then decided under the ruled cutoff.
    Fail-first (guard absent): 200, five version-based datasets empty."""
    with monkeypatch.context() as patched:
        patched.setattr(freeze, "freeze_cutoff", lambda session, now: now)
        (message,) = _refused(close, "S15-R-18c")
    assert message.startswith(
        f"contract {K01} has subledger lines of the period within the freeze cutoff "
        f"{close.t0.isoformat()}, and the contract version that posted them is known only at "
    )
    decided = approve(close.world.app, str(close.request_id), close.controller)
    assert decided.status_code == 200, decided.text
    assert _observed(close)["state"] == PeriodState.CLOSED.value


def test_r19_lines_and_runs_recorded_after_the_cutoff_are_refused_by_name(
    close: Close, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-19 (b): a cutoff earlier than the period's own rows (a decision whose clocks lag the
    clock that stamped them): the period's subledger lines and its journal run lie beyond it and
    the lock is refused naming both, with their count and latest instant."""
    early = close.t0 - timedelta(days=1)
    monkeypatch.setattr(freeze, "freeze_cutoff", lambda session, now: early)
    lines, runs = _refused(close, "S15-R-18c")
    assert lines == (
        f"2 subledger line(s) of the period are recorded after the freeze cutoff "
        f"{early.isoformat()} (the latest at {close.t0.isoformat()}); the frozen datasets would "
        "not hold them."
    )
    assert runs == (
        f"1 journal run(s) of the period are created after the freeze cutoff {early.isoformat()} "
        f"(the latest at {close.t0.isoformat()}); the frozen journal population would not hold "
        "them."
    )


# --- (c) a registry refusal is a named 4xx --------------------------------------------------------


def test_r19_a_dataset_the_registry_refuses_is_a_named_409(
    close: Close, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-19 (c): the registry refuses one kind's freeze (``SnapshotRefusal``): the decision
    answers 409 ``invalid-transition`` naming the kind and the reason — never a bare 500 — and
    writes nothing. Fail-first: the ``RuntimeError`` left the handler as ERR-34."""
    reason = "row OPENING lacks the required column contract_external_id"

    def refusing(uow: Any, scope: Any) -> Any:
        raise registry.SnapshotRefusal(SnapshotKind.RPO_ROLLFORWARD.value, reason)

    datasets: Mapping[str, Any] = {
        **registry.SNAPSHOT_DATASETS,
        SnapshotKind.RPO_ROLLFORWARD.value: refusing,
    }
    monkeypatch.setattr(registry, "SNAPSHOT_DATASETS", datasets)
    (message,) = _refused(close, "S15-R-18")
    assert message == f"the RPO_ROLLFORWARD dataset cannot be frozen ({reason})."


# --- (d) serialisation against postings: SC-1 (R-31, R-40 (b), R-42 (e)) --------------------------

LATE: Final = "LATE-ARRIVAL-01"
LATE_INVOICE: Final = "INV-US-1090"
JOIN_SECONDS: Final = 120.0
WAIT_SECONDS: Final = 30.0


def _setup_completed(world: ReportWorld) -> None:
    """Tenant setup complete before an interleaving (the security review's fixture note): while
    ``tenant.setup_completed_at`` is NULL an approval takes the tenant row ``FOR UPDATE``, which
    waits for every open transaction that inserted a row of the tenant — a wait that would stand
    in for the one under test."""
    with world.place.uow() as uow:
        setup.evaluate_setup_completion(uow)
        uow.commit()
    with _session(world) as session:
        completed = session.execute(
            select(tenant.c.setup_completed_at).where(tenant.c.id == world.tenant_id)
        ).scalar_one()
    assert completed is not None


def _late_contract(close: Close) -> tuple[UUID, UUID]:
    """A second contract of the K-01 customer — one PLATFORM line of 120,000.00 from 1 August to
    the end of 2026 — booked and activated, NOT computed: its (contract id, group id). Its
    computation posts into August and into no earlier period: January to July are closed
    before August is locked (PRD BR-CLS-08; supervisor ruling R-6), and a contract that began
    in one of them would post its earlier months late into August.

    It is invoiced in full on its first day, as K-01 is (INV-US-1001), the invoice recorded and
    not computed either. Since 04 rev 1.172 (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and
    R-116 (e)) a contract computed after the period's close run is judged by the period-end
    passes, and the lock waits for a new run when it leaves a period end to post. Without an
    invoice the contract's August revenue is a contract asset, an account role the chart of this
    world does not hold: its period end could not be posted, and August could not be locked
    (STALE TEST WORLD). Invoiced in advance it leaves none, like K-01."""
    world = close.world
    body = k01_body(UUID(str(world.contracts[K01].contract["customer_id"])))
    body["external_id"] = LATE
    body["inception_date"] = "2026-08-01"
    body["lines"] = [{**body["lines"][0], "start_date": "2026-08-01"}]
    late = booked_contract(world.place, body, activate=True)
    contract_id = UUID(str(late.contract["id"]))
    invoice = BillingRecordedV1(
        invoice_number=LATE_INVOICE,
        line_external_id=f"{LATE_INVOICE}-1",
        obligation_key=str(body["lines"][0]["obligation_key"]),
        amount=MoneyIn(amount="120000.00", currency="USD"),
        issue_date=date(2026, 8, 1),
    )
    billed = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 8, 1),
        payload=invoice,
    )
    appended(world.place, contract_id, 2, [billed])  # after CONTRACT_BOOKED and its activation
    return contract_id, UUID(str(late.combination_group["id"]))


def _persist(uow: UnitOfWork, group_id: UUID) -> Mapping[str, Any]:
    """The production computation of a group inside ``uow`` — bundle, engine,
    ``computation.persist``, whose ``subledger.post`` inserts the lines — NOT committed
    (``support.factories.computed`` without its commit)."""
    bundle = bundles.build(uow.session, group_id, uow.now, (), ComputationTrigger.COMMAND)
    stored = computation.persist(uow, bundle, engine()(bundle))
    uow.session.flush()
    return stored


def _period(close: Close, period_key: str) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(close.world.app, close.world.maya, entity=AVM_US)
        if item["period"]["period_key"] == period_key
    ]
    return found


def _lines_of(close: Close, contract_id: UUID) -> list[tuple[UUID, UUID | None]]:
    """(period, origin period) of every subledger line of a contract."""
    with _session(close.world) as session:
        return [
            (UUID(str(period_id)), None if origin is None else UUID(str(origin)))
            for period_id, origin in session.execute(
                select(subledger_line.c.period_id, subledger_line.c.origin_period_id).where(
                    subledger_line.c.contract_id == contract_id
                )
            )
        ]


def _lock_row(close: Close) -> Mapping[str, Any]:
    with _session(close.world) as session:
        return dict(
            session.execute(
                select(period_lock).where(
                    period_lock.c.period_id == close.period_id,
                    period_lock.c.kind == LockKind.LOCK.value,
                )
            )
            .mappings()
            .one()
        )


def _period_seals(close: Close) -> list[int]:
    """The chain positions of the seals that hold a line of the period."""
    with _session(close.world) as session:
        return sorted(
            int(seq)
            for seq in session.execute(
                select(subledger_posting_seal.c.chain_seq)
                .where(
                    subledger_posting_seal.c.subledger_posting_id.in_(
                        select(subledger_line.c.subledger_posting_id).where(
                            subledger_line.c.period_id == close.period_id
                        )
                    )
                )
                .distinct()
            ).scalars()
        )


def _head(close: Close) -> int:
    with _session(close.world) as session:
        return int(
            session.execute(
                select(ledger_chain_head.c.last_chain_seq).where(
                    ledger_chain_head.c.book_code == BOOK
                )
            ).scalar_one()
        )


@pytest.mark.control("CTL-015")
def test_sc1_a_posting_in_flight_is_waited_for_and_seen_by_the_lock_decision(close: Close) -> None:
    """SC-1, the security review's two-session proof inverted (R-31, R-40 (b)). T1 — the production
    computation of a second contract — has inserted its lines of August and is NOT committed. T2 —
    the Controller's real approval — is observed WAITING for T1, blocked in its ``FOR UPDATE`` of
    the period's state row, and writes nothing meanwhile. T1 commits; the decision then SEES the
    four lines of August: they are not journalised, so the gates refuse the lock by name
    (``JE_COMPLETE``) and nothing is written. Once the journal covers them the same request locks
    August, and the lock holds the posting: its ledger head is at or after every seal of the
    period (R-42 (e)) and its balances dataset holds both contracts.

    Fail-first (the proof itself, run on this lane's base before revision 0084): the approval did
    not wait — it answered 200 with two lines, head 0, while T1's seal 1 was uncommitted — and T1
    then committed two more lines into the CLOSED period."""
    world = close.world
    _setup_completed(world)
    late_contract_id, group_id = _late_contract(close)
    outcome: dict[str, Any] = {}

    def decide() -> None:
        try:
            outcome["response"] = approve(world.app, str(close.request_id), close.controller)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    request = threading.Thread(target=decide, name="sc1-lock-decision")
    held = world.place.uow()
    uow = held.__enter__()
    started = False
    try:
        stored = _persist(uow, group_id)  # T1: inserted, in flight
        assert _august_lines(close) == 2  # no other transaction sees T1's lines yet
        with observing_checkouts() as backends:
            holder_pid = backend_pid(uow.session)
            request.start()
            started = True
            blocked_pid, blocked_in = await_lock_wait(
                uow.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=WAIT_SECONDS,
                expect="period_state",
            )
        assert blocked_pid != holder_pid and "for update" in blocked_in.lower(), blocked_in
        assert request.is_alive() and "response" not in outcome
        assert _observed(close) == NOTHING_WRITTEN
        uow.commit()  # T1 commits while the decision waits for it
    finally:
        held.__exit__(None, None, None)
        if started:
            request.join(timeout=JOIN_SECONDS)
    assert not request.is_alive() and "error" not in outcome, outcome
    refused = outcome["response"]
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert "JE_COMPLETE" in {error["rule_id"] for error in refused.json()["errors"]}
    assert _observed(close) == NOTHING_WRITTEN and _august_lines(close) == 4
    posting_id = UUID(str(stored["subledger_posting_ids"][BOOK]))

    # the journal covers the new lines; the same request is decided again and locks the period
    maya = world.maya
    requested = post(
        world.app, JOURNAL_RUNS, maya, {"entity_code": AVM_US, "period_key": AUGUST_2026}
    )
    assert requested.status_code == 202, requested.text
    assert run_now(world, UUID(str(requested.json()["id"])))["state"] == "SUCCEEDED"
    with _session(world) as session:
        acknowledge_run(session, UUID(str(requested.headers[JOURNAL_RUN_ID_HEADER])), now=close.t0)
    decided = approve(world.app, str(close.request_id), close.controller)
    assert decided.status_code == 200, decided.text
    lock = _lock_row(close)
    with _session(world) as session:
        late_seal = int(
            session.execute(
                select(subledger_posting_seal.c.chain_seq).where(
                    subledger_posting_seal.c.subledger_posting_id == posting_id
                )
            ).scalar_one()
        )
        frozen = _frozen(session, close, UUID(str(lock["id"])))
    seals = _period_seals(close)
    assert late_seal in seals and int(lock["ledger_head_chain_seq"]) >= max(seals)
    assert int(lock["ledger_head_chain_seq"]) == _head(close)
    assert sorted(
        row["contract_external_id"] for row in frozen[SnapshotKind.CONTRACT_BALANCES.value]
    ) == sorted([K01, LATE])
    assert _observed(close)["state"] == PeriodState.CLOSED.value
    assert (close.period_id, None) in _lines_of(close, late_contract_id)


@pytest.mark.control("CTL-015")
def test_sc1_a_posting_that_arrives_while_the_lock_is_decided_waits_and_is_refused(
    close: Close, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-1, the other order (R-31, R-40 (b); the successor of this module's first witness of
    R-19 (d), whose scenario — a posting COMMITTING into the period during the decision — revision
    0084 removes). The decision has frozen its datasets and holds the period's state row; the
    production computation of a second contract then asks for that row: it is observed WAITING —
    blocked by the decision's backend, holding the tuple lock of ``period_state`` and not the
    ledger chain head, which a third session takes at once (the order: state row, then head).
    Since 04 rev 1.172 (item CLO-GATE-RUN-1; supervisor ruling of 2026-10-01 02:35; dev-guide
    DG-KRN-DB-08 (1c)) it waits before it writes anything, in the read that finds the window of
    the period's close run and takes its state rows ``FOR SHARE``; until then it waited for the
    same row in its INSERT of subledger lines, where the DB-07 guard takes it (STALE
    EXPECTATION: the statement it is blocked in). The decision completes: August is closed with
    its two lines, and the lock's head is every seal of the period. The posting is then refused
    by the guard, ``EREV-LED-003``, and nothing of it is saved. Computed again, the contract's
    August amounts land in September with August as origin period — the late-event rule of
    ``periods.posting_period`` (DG-KRN-TIME-04).

    Fail-first (measured in this lane before revision 0084): the computation did not wait — it
    committed during the decision, August went from 2 to 4 lines and the decision answered 200
    (slice 3 then refused it by ``S15-R-18c`` after the fact)."""
    world = close.world
    _setup_completed(world)
    freeze_datasets = close_commands.snapshots.freeze_datasets
    posting: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def post_late() -> None:
        try:
            posting["stored"] = computed(world.place, seen["group_id"])[2]
        except Exception as error:  # noqa: BLE001 - the refusal under test
            posting["error"] = error

    poster = threading.Thread(target=post_late, name="sc1-late-posting")

    def freeze_then_meet_the_posting(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        datasets = freeze_datasets(uow, *args, **kwargs)
        if poster.ident is None:  # once: the posting arrives after the gates and the freeze
            # booked and activated now (a contract waiting for its computation fails the gates)
            seen["contract_id"], seen["group_id"] = _late_contract(close)
            with observing_checkouts() as backends:
                decision_pid = backend_pid(uow.session)
                poster.start()
                blocked_pid, seen["blocked_in"] = await_lock_wait(
                    uow.session,
                    holder_pid=decision_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="period_state",
                )
            seen["locks"] = fresh_activity(uow.session, LOCKS_OF, {"pids": [blocked_pid]}).all()
            with _session(world) as third:  # the waiting posting does not hold the chain head
                seen["head"] = third.execute(
                    select(ledger_chain_head.c.last_chain_seq)
                    .where(ledger_chain_head.c.book_code == BOOK)
                    .with_for_update(nowait=True)
                ).scalar_one()
                third.rollback()
            seen["waiting"] = poster.is_alive() and not posting
        return datasets

    monkeypatch.setattr(close_commands.snapshots, "freeze_datasets", freeze_then_meet_the_posting)
    before = _august_lines(close)
    try:
        decided = approve(world.app, str(close.request_id), close.controller)
    finally:
        if poster.ident is not None:
            poster.join(timeout=JOIN_SECONDS)
    assert decided.status_code == 200, decided.text
    assert not poster.is_alive() and seen["waiting"] is True, (seen, posting)
    evidence = format_lock_rows(seen["locks"])
    assert "for share" in seen["blocked_in"].lower(), seen["blocked_in"]
    assert any(
        row.locktype == "tuple" and str(row.relation).endswith("period_state")
        for row in seen["locks"]
    ), evidence
    # the decision closed the period it froze: two lines, and a head that is every seal of it
    lock = _lock_row(close)
    assert _observed(close)["state"] == PeriodState.CLOSED.value
    assert (before, _august_lines(close)) == (2, 2)
    assert int(lock["ledger_head_chain_seq"]) == seen["head"] == _head(close)
    assert int(lock["ledger_head_chain_seq"]) >= max(_period_seals(close))
    # the posting: refused by the guard once the decision committed, nothing of it saved
    refused = posting["error"]
    assert isinstance(refused, exc.DBAPIError), posting
    assert getattr(refused.orig, "sqlstate", None) == "P0001"
    message = str(refused.orig.diag.message_primary)
    assert message.startswith(
        f"EREV-LED-003: period {close.period_id} of entity {world.entity_id} is closed in book "
        "ASC606"
    ), message
    assert _lines_of(close, seen["contract_id"]) == []
    # computed again, the posting-period rule plans August's amounts into September, origin August
    computed(world.place, seen["group_id"])
    september = UUID(str(_period(close, SEPTEMBER_2026)["period"]["id"]))
    placed = _lines_of(close, seen["contract_id"])
    assert placed and all(period_id != close.period_id for period_id, _ in placed)
    late_events = [item for item in placed if item[1] == close.period_id]
    assert late_events and {period_id for period_id, _ in late_events} == {september}
    assert _august_lines(close) == 2


@pytest.mark.control("CTL-015")
def test_sc1_the_lock_decision_does_not_wait_for_a_posting_into_the_next_period(
    close: Close,
) -> None:
    """The lock order of 04 DB-07 (R-40 (b)): the decision takes the NEXT period's state row only
    when that period is ``future``. Here September is open and a posting into it — the production
    ``subledger.post`` — is in flight, holding September's state row ``FOR SHARE`` and the ledger
    chain head: the decision of August locks the period without waiting for it, and the posting
    then commits into September, which stays open.

    Fail-first (``_open_next_period`` taking the next row ``FOR UPDATE`` whatever its state): the
    decision waits for the posting — 409 ``lock-conflict`` after ``lock_timeout`` here, where the
    posting outlives it, and a deadlock when the posting also holds lines of August."""
    world = close.world
    _setup_completed(world)
    september = _period(close, SEPTEMBER_2026)
    assert september["state"] == PeriodState.OPEN.value
    september_id = UUID(str(september["period"]["id"]))
    with _session(world) as session:
        august = (
            session.execute(
                select(subledger_line)
                .where(subledger_line.c.period_id == close.period_id)
                .order_by(subledger_line.c.amount_functional)
            )
            .mappings()
            .all()
        )
    group_id = UUID(str(world.contracts[K01].combination_group["id"]))
    lines = [
        {
            **{name: row[name] for name in subledger.LINE_MEMBERS},
            "id": new_id(),
            "period_id": september_id,
            "period_end_date": date(2026, 9, 30),
            "effective_date": date(2026, 9, 30),
        }
        for row in august
    ]
    with world.place.uow() as uow:
        posted = subledger.post(
            uow,
            book_code=BOOK,
            posting_kind=SubledgerPostingKind.VOID_REVERSAL,
            idempotency_key="sc1:next-period",
            description="SC-1 witness: a posting into the next period, in flight at the lock",
            lines=lines,
            combination_group_id=group_id,
        )
        uow.session.flush()  # in flight: September's state row FOR SHARE, the chain head held
        decided = approve(world.app, str(close.request_id), close.controller)
        assert decided.status_code == 200, decided.text
        assert _observed(close)["state"] == PeriodState.CLOSED.value
        uow.commit()  # and the posting is not harmed: it commits into September
    with _session(world) as session:
        stored = session.execute(
            select(func.count())
            .select_from(subledger_line)
            .where(subledger_line.c.subledger_posting_id == posted.posting_id)
        ).scalar_one()
        state = session.execute(
            select(period_state.c.state).where(period_state.c.id == UUID(str(september["id"])))
        ).scalar_one()
    assert (int(stored), _value(state)) == (2, PeriodState.OPEN.value)


@pytest.mark.control("CTL-015")
def test_sc1_a_request_that_leaves_the_state_as_it_is_does_not_wait_for_a_posting(
    close: Close,
) -> None:
    """The lock order of 04 DB-07 (R-40 (b)): a close command that leaves the period's state as
    it is pins the state row ``FOR SHARE``, which a posting's lines hold in the same mode. Here
    the production computation of a second contract is in flight — its August lines inserted,
    not committed — and a request for the lock answers beside it, by name and for its own reason
    (the contract's group is not computed yet for every other transaction): it does not wait.

    Fail-first (the request taking the row ``FOR UPDATE``): the request waits for the posting and
    is answered 409 ``lock-conflict`` at ``lock_timeout``; and, holding the row, it takes its
    ``APPROVAL`` number after it, while an auto-approved submission holds that number before its
    first line reaches the guard — a cycle."""
    world = close.world
    _setup_completed(world)
    _, group_id = _late_contract(close)
    august = _period(close, AUGUST_2026)
    with world.place.uow() as uow:
        _persist(uow, group_id)  # in flight: August's state row held FOR SHARE
        requested = post(
            world.app,
            f"{PERIODS}/{close.state_id}/request-lock",
            world.maya,
            {"certification_comment": "August 2026 close complete"},
            if_match=f'"r{august["row_version"]}"',
        )
        assert (requested.status_code, slug(requested)) == (409, "close-gates-failed"), (
            requested.text
        )
        assert "NO_DIRTY_GROUPS" in {error["rule_id"] for error in requested.json()["errors"]}
        uow.discard()
    assert _observed(close) == NOTHING_WRITTEN and _august_lines(close) == 2


# --- (e) the guard's result does not depend on who decides: R-42 (d) ------------------------------


def test_r42_the_coverage_guard_sees_a_line_whose_contract_belongs_to_another_entity(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """R-42 (d): the guard reads under the tenant's SYSTEM scope. WLD-K-04: ``SF-ORD-UK-2001`` is
    contracted by AVM-UK and its obligation O1 is performed by AVM-US, so AVM-US's April holds
    subledger lines of a contract whose row belongs to another contracting entity. At a cutoff
    before the contract version is known — the frozen application clock — the guard names the
    contract; the refusal is the same whoever decides, because ``assert_covered`` takes the
    tenant, not the decider's session. Fail-first (the guard read through the decider's session):
    for a decider scoped to AVM-US row-level security hides the contract row, the join drops its
    lines and the guard finds nothing — shown here as the read under that scope."""
    world = k04_saltmarsh(app, keyring, clock, LocalFileStore(app_settings.file_root))
    tenant_id = world.report.tenant_id
    (april,) = [
        item
        for item in periods(app, world.report.maya, entity=AVM_US)
        if item["period"]["period_key"] == "FY2026-P04"
    ]
    cutoff = clock.now()
    with freeze.system_reads(tenant_id) as reader:
        scope = gates.scope_of_period(
            reader, world.us_entity_id, BOOK, UUID(str(april["period"]["id"]))
        )
        assert scope is not None
        seen = freeze.coverage(reader, scope, cutoff)
        before = freeze.activity(reader, scope)
    narrow = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(world.us_entity_id,))
    with tenant_session(narrow, read_only=True) as decider:
        hidden = freeze.coverage(decider, scope, cutoff)
        assert freeze.activity(decider, scope) == before  # the lines themselves are in scope
    assert before.lines > 0 and (seen.late_lines, hidden.late_lines) == (0, 0)
    assert [item.external_id for item in seen.late_versions] == [K04]
    assert hidden.late_versions == ()  # the former read: nothing found, the lock would proceed
    with pytest.raises(Problem) as refused:
        freeze.assert_covered(tenant_id, scope, cutoff, before)
    problem = refused.value
    assert (problem.slug, [error.rule_id for error in problem.errors]) == (
        "invalid-transition",
        ["S15-R-18c"],
    )
    assert str(problem.errors[0].message).startswith(
        f"contract {K04} has subledger lines of the period within the freeze cutoff "
        f"{cutoff.isoformat()}, and the contract version that posted them is known only at "
    )
