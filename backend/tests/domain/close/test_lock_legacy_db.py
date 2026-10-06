"""CLO-LOCK-LEGACY-1: the LEGACY book has no close of its own — its period is postable exactly
while the primary book's is (supervisor rulings R-97 (2) and R-112 (e) of 2026-09-30; finding F1 of
the independent review of revision 0084; 04 §14.1 DB-07, T-REF-06 and §16.8 rev 1.155; 05 RCP-15
rev 1.94; dev-guide DG-KRN-DB-08 rev 1.138; PRD §5.3 rev 1.84; revision 0105).
PostgreSQL-bound.

The LEGACY book (D-24) holds pre-standard revenue for delta posting. It takes no journal run of
its own (T-SL-06), so a LEGACY period could be soft-closed and never locked: it stayed postable
for ever, and a computation posted a LEGACY line into a period whose PRIMARY book was locked —
measured by the lane on 2026-09-30: 7,700.00 into a closed August, with no primary-book line to
serialise it behind the lock. Under ``DELTA`` no journal run could ever carry such a line.

World: answer key ONB-S11-MODRETRO-OWN through the product (``support.worlds.
onb_s11_modretro_own``): US01 keeps ASC606 (primary) and LEGACY, FY2025-P01 to FY2026-P09 open in
both; ``C-ADOPT`` records legacy revenue through ``PRE_STANDARD_REVENUE_RECORDED``, an event that
posts in the LEGACY book alone. August 2026 of the primary book is closed through the product on
the record-time clock.

PER-LEGACY-POSTING-PERIOD-1 (supervisor ruling R-118 (h) and the supervisor's ruling of 2026-10-01
on the lane's finding; PRD BR-CLS-03 rev 1.143; 04 §14.1 DB-07 rev 1.214; dev-guide DG-KRN-TIME-04
and DG-KRN-DB-08 rev 1.197). A lock decision opened the next period of the book it locked and of
no other. September 2026 is the last period the world opens, so its lock left the LEGACY book's
October ``future``: a legacy amount dated in September then had no period postable in both books —
measured by the lane on 2026-10-01: the event accepted, the computation ``SUCCEEDED``, the amount
posted in no period, and the later opening of the LEGACY period re-marked nothing. The lock of a
period of the primary book now opens the LEGACY book's next period with its own; the mirror on
``POST /contracts/{id}/events`` asks the books the entity keeps and refuses what would be posted
nowhere.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    close_run,
    contract,
    contract_event,
    job,
    journal_batch,
    journal_line,
    journal_run,
    period,
    period_lock,
    period_state,
    period_state_transition,
    subledger_line,
    tenant,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.contracts import bundles, computation
from erev_api.domain.platform import setup
from erev_api.enums import ComputationTrigger, ContractEventType, JobKind
from erev_api.events.payloads import PreStandardRevenueRecordedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from sqlalchemy.exc import DBAPIError
from support import close_runs as runs
from support.close_world import (
    JOURNAL_RUN_ID_HEADER,
    JOURNAL_RUNS,
    close_run_succeeded_for,
    periods_closed_before,
    reviewed_reconciliations_for,
)
from support.db import TestDatabase
from support.factories import engine
from support.http import HttpResponse
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.reference import PERIODS, approve, periods, post, put, slug
from support.rows import close_run_values
from support.worlds import (
    C_ADOPT,
    US01,
    ReportWorld,
    _appended_through_api,
    committed_import,
    on_record_clock,
    onb_s11_modretro_own,
    period_locked,
    period_reopened,
    posted_journal,
    run_now,
    verified,
)

PRIMARY: Final = "ASC606"
LEGACY: Final = "LEGACY"
AUGUST: Final = "FY2026-P08"
SEPTEMBER: Final = "FY2026-P09"
OCTOBER: Final = "FY2026-P10"
FOLLOWS: Final = "The legacy book follows the close of ASC 606."
RULE: Final = "LEGACY_FOLLOWS_PRIMARY"
SEPTEMBER_END: Final = "2026-09-30"
# PRD ERR-78 for the lock of September, and ERR-15 for a date in it (the world's period names)
OCTOBER_HELD: Final = (
    "Oct 2026 is in use by another request, so Sep 2026 was not locked. Nothing was saved. "
    "Decide again."
)
SEPTEMBER_CLOSED: Final = (
    "Sep 2026 is closed for US01 in book ASC606. Postings to a closed period are not allowed."
)
# September and October in the two books: as the world opens them, and after September's lock
AS_OPENED: Final = {
    (PRIMARY, SEPTEMBER): "open",
    (PRIMARY, OCTOBER): "future",
    (LEGACY, SEPTEMBER): "open",
    (LEGACY, OCTOBER): "future",
}
BOTH_OPENED: Final = {
    (PRIMARY, SEPTEMBER): "closed",
    (PRIMARY, OCTOBER): "open",
    (LEGACY, SEPTEMBER): "open",
    (LEGACY, OCTOBER): "open",
}
PRE_STANDARD_COLUMNS: Final = (
    "contract",
    "effective_date",
    "obligation_key",
    "amount.amount",
    "amount.currency",
)
JOIN_SECONDS: Final = 120.0
WAIT_SECONDS: Final = 30.0


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    built = onb_s11_modretro_own(app, keyring, clock, LocalFileStore(app_settings.file_root))
    return on_record_clock(built, clock)  # a close runs on the record-time clock


def _session(world: ReportWorld) -> Any:
    return tenant_session(DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*"))


def _contract_id(world: ReportWorld) -> UUID:
    return UUID(str(world.contracts[C_ADOPT].contract["id"]))


def _group_id(world: ReportWorld) -> UUID:
    return UUID(str(world.contracts[C_ADOPT].combination_group["id"]))


def _row(world: ReportWorld, book: str, period_key: str) -> dict[str, Any]:
    """API-S-Period of US01's period in ``book``."""
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity=US01, book=book)
        if item["period"]["period_key"] == period_key
    ]
    return dict(found)


def _pre_standard(amount: str) -> dict[str, Any]:
    """``PRE_STANDARD_REVENUE_RECORDED`` of L2-PCS dated 31 Aug 2026: LEGACY-book lines only."""
    return {
        "event_type": "PRE_STANDARD_REVENUE_RECORDED",
        "effective_date": "2026-08-31",
        "payload": {"obligation_key": "L2-PCS", "amount": {"amount": amount, "currency": "USD"}},
    }


def _legacy_lines(world: ReportWorld, amount: str) -> list[tuple[str, str | None, bool]]:
    """(period key, origin period key, is_post_reopen) of the LEGACY pre-standard revenue lines of
    ``amount``."""
    origin = period.alias("origin_period")
    with _session(world) as session:
        return sorted(
            (str(key), None if origin_key is None else str(origin_key), bool(flag))
            for key, origin_key, flag in session.execute(
                select(period.c.period_key, origin.c.period_key, subledger_line.c.is_post_reopen)
                .select_from(
                    subledger_line.join(
                        period, period.c.id == subledger_line.c.period_id
                    ).outerjoin(origin, origin.c.id == subledger_line.c.origin_period_id)
                )
                .where(
                    subledger_line.c.book_code == LEGACY,
                    subledger_line.c.account_role == "PRE_STANDARD_REVENUE",
                    subledger_line.c.amount_txn == Decimal(amount),
                )
            )
        )


def _setup_completed(world: ReportWorld) -> None:
    """Tenant setup complete before an interleaving. Until dev-guide DG-KRN-DB-08 rev 1.165 a
    decision of a tenant whose setup was incomplete took the tenant row ``FOR UPDATE`` after its
    hook, which waited for every transaction that had inserted a row; the lock is ``FOR NO KEY
    UPDATE`` since (item SETUP-COMPLETION-LOCK-1, witnessed with setup incomplete in
    ``test_lock_decision_db.py``). The call stays: it is the world this interleaving was
    witnessed in."""
    with world.place.uow() as uow:
        setup.evaluate_setup_completion(uow)
        uow.commit()
    with _session(world) as session:
        completed = session.execute(
            select(tenant.c.setup_completed_at).where(tenant.c.id == world.tenant_id)
        ).scalar_one()
    assert completed is not None


def test_r112_e_a_legacy_amount_dated_in_a_locked_primary_period_lands_in_the_next_open_one(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-112 (e) (1), (2): August of the PRIMARY book is locked through the product; the LEGACY
    row of August is still ``open``. Legacy revenue dated 31 August then arrives: the bundle hands
    the engine August of the LEGACY book as ``closed`` — the primary's state — so the amount is
    planned into September, the first later period postable in both books, with August as its
    origin period. Nothing of the LEGACY book is posted into August after its lock, in the default
    ``GROSS`` journal mode as in any other.

    Fail-first (the lane's measurement): the computation SUCCEEDED and posted both lines into
    August, the period the primary book had locked."""
    _, world = period_locked(world, clock, entity_code=US01, period_key=AUGUST)
    assert (_row(world, PRIMARY, AUGUST)["state"], _row(world, LEGACY, AUGUST)["state"]) == (
        "closed",
        "open",
    )
    with _session(world) as session:
        bundle = bundles.build(
            session, _group_id(world), clock.now(), (), ComputationTrigger.COMMAND
        )
    (entity,) = bundle.entities
    states = {item.period_key: dict(item.states) for item in entity.periods}
    assert states[AUGUST] == {PRIMARY: "closed", LEGACY: "closed"}  # the primary's state
    assert states[SEPTEMBER] == {PRIMARY: "open", LEGACY: "open"}
    appended = _appended_through_api(world.place, _contract_id(world), _pre_standard("7700.00"))
    assert appended["computation"]["status"] == "SUCCEEDED", appended["computation"]
    assert _legacy_lines(world, "7700.00") == [(SEPTEMBER, AUGUST, False)]


def test_r112_e_the_delta_run_of_the_next_period_carries_the_late_legacy_amount(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-112 (e) (1) for ``DELTA`` (the review's F1): the late legacy amount is in September, so
    September's ``DELTA`` run journalises it (ENGINE_SPEC_B S14-R-23: primary plus LEGACY lines).
    Fail-first: the amount sat in August, whose primary book is closed — September's run did not
    hold it, and a journal line of a closed period is refused (DB-07), so no run could."""
    _, world = period_locked(world, clock, entity_code=US01, period_key=AUGUST)
    _appended_through_api(world.place, _contract_id(world), _pre_standard("7700.00"))
    requested = post(
        world.app,
        JOURNAL_RUNS,
        world.maya,
        {"entity_code": US01, "period_key": SEPTEMBER, "mode": "DELTA"},
    )
    assert requested.status_code == 202, requested.text
    assert run_now(world, UUID(str(requested.json()["id"])))["state"] == "SUCCEEDED"
    run_id = UUID(str(requested.headers[JOURNAL_RUN_ID_HEADER]))
    with _session(world) as session:
        mode, delta_book = session.execute(
            select(journal_run.c.mode, journal_run.c.delta_book_code).where(
                journal_run.c.id == run_id
            )
        ).one()
        carried = [
            Decimal(debit) - Decimal(credit)
            for debit, credit in session.execute(
                select(journal_line.c.debit_txn, journal_line.c.credit_txn)
                .select_from(
                    journal_line.join(
                        journal_batch, journal_batch.c.id == journal_line.c.journal_batch_id
                    )
                )
                .where(
                    journal_batch.c.journal_run_id == run_id,
                    journal_line.c.account_role == "PRE_STANDARD_REVENUE",
                )
            )
        ]
    assert (str(getattr(mode, "value", mode)), str(getattr(delta_book, "value", delta_book))) == (
        "DELTA",
        LEGACY,
    )
    assert sum(carried, Decimal(0)) == Decimal("7700.00"), carried
    assert _legacy_lines(world, "7700.00") == [(SEPTEMBER, AUGUST, False)]  # none left in August


@dataclass(frozen=True)
class Pending:
    """A period of the primary book in soft close with a pending lock request."""

    world: ReportWorld
    state_id: UUID
    request_id: str


def _lock_requested(world: ReportWorld, clock: FrozenClock, period_key: str = AUGUST) -> Pending:
    """``support.worlds.period_locked`` up to the request, for ``period_key`` of the primary book:
    the earlier periods closed as fixture state (BR-CLS-08), the soft close, the journal run
    through its life, the two reconciliations reviewed, the period's close run succeeded (a row:
    fixture state for the gate ``CLOSE_RUN_COMPLETED``, item CLO-GATE-RUN-1), the lock request —
    and Marcus verified, ready to decide."""
    shown = _row(world, PRIMARY, period_key)
    entity_id = UUID(str(shown["entity"]["id"]))
    periods_closed_before(
        world.place, world.app, world.maya, entity_id=entity_id, before=period_key, entity_code=US01
    )
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": f"{period_key} close"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    _, world = posted_journal(world, clock, entity_code=US01, period_key=period_key)
    with _session(world) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=entity_id,
            period_id=UUID(str(shown["period"]["id"])),
            now=clock.now(),
        )
        close_run_succeeded_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=entity_id,
            period_id=UUID(str(shown["period"]["id"])),
            now=clock.now(),
        )
    shown = _row(world, PRIMARY, period_key)
    requested = post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-lock",
        world.maya,
        {"certification_comment": f"{period_key} close complete"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    world = verified(world, clock, "marcus")
    return Pending(world, UUID(str(shown["id"])), str(requested.json()["approval_request_id"]))


def _legacy_only_computation(uow: UnitOfWork, world: ReportWorld) -> Mapping[str, Any]:
    """The production computation of a LEGACY-only event inside ``uow``, NOT committed: the event
    appended, the bundle built, the engine run, ``computation.persist`` — whose ``subledger.post``
    inserts the two LEGACY lines of August."""
    head = int(
        uow.session.execute(
            select(contract.c.head_stream_version).where(contract.c.id == _contract_id(world))
        ).scalar_one()
    )
    append_events(
        uow,
        contract_id=_contract_id(world),
        expected_stream_version=head,
        events=[
            EventIn(
                event_type=ContractEventType.PRE_STANDARD_REVENUE_RECORDED,
                effective_date=date(2026, 8, 31),
                payload=PreStandardRevenueRecordedV1(
                    obligation_key="L2-PCS",
                    amount=MoneyIn(amount="5500.00", currency="USD"),
                ),
                obligation_keys=("L2-PCS",),
            )
        ],
        origin="UI",
    )
    bundle = bundles.build(uow.session, _group_id(world), uow.now, (), ComputationTrigger.COMMAND)
    stored = computation.persist(uow, bundle, engine()(bundle))
    uow.session.flush()
    return stored


def test_r112_e_a_legacy_posting_in_flight_is_waited_for_by_the_primary_lock_decision(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-112 (e) (3): T1 — the production computation of a LEGACY-only event dated in August — has
    inserted its two LEGACY lines and is NOT committed. Its guard read the PRIMARY book's state row
    of August ``FOR SHARE`` first. T2 — Marcus's real approval of August's lock — is observed
    WAITING for T1, blocked in its ``FOR UPDATE`` of that row. T1 commits; the decision then
    locks August, and the two LEGACY lines are in the period it locked — committed before it.

    Fail-first: the LEGACY guard held the LEGACY row alone, so the decision of the primary book did
    not wait (no backend of the request was ever blocked by T1)."""
    _setup_completed(world)
    pending = _lock_requested(world, clock)
    world = pending.world
    outcome: dict[str, Any] = {}

    def decide() -> None:
        try:
            outcome["response"] = approve(world.app, pending.request_id, world.marcus)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    request = threading.Thread(target=decide, name="legacy-lock-decision")
    held = world.place.uow()
    uow = held.__enter__()
    started = False
    try:
        stored = _legacy_only_computation(uow, world)  # T1: inserted, in flight
        assert stored["status"] == "SUCCEEDED"
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
        uow.commit()  # T1 commits while the decision waits for it
    finally:
        held.__exit__(None, None, None)
        if started:
            request.join(timeout=JOIN_SECONDS)
    assert not request.is_alive() and "error" not in outcome, outcome
    decided = outcome["response"]
    assert decided.status_code == 200, decided.text
    assert _row(world, PRIMARY, AUGUST)["state"] == "closed"
    assert _legacy_lines(world, "5500.00") == [(AUGUST, None, False)]


def test_r112_e_a_legacy_line_beside_a_reopened_primary_period_is_a_post_reopen_line(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-112 (e) (4): August of the primary book is locked and reopened; its LEGACY row was
    ``open`` throughout. A legacy amount dated in August posts into August again — the primary is
    postable — and its lines carry ``is_post_reopen``: the flag follows the primary's ``REOPEN``
    record (REQ-CLS-011; the record instead of the state literal since revision 0113), since the
    LEGACY row is never closed. Fail-first: the flag was false."""
    _, world = period_locked(world, clock, entity_code=US01, period_key=AUGUST)
    world = period_reopened(
        world,
        clock,
        entity_code=US01,
        period_key=AUGUST,
        comment="Pre-standard revenue of 31 Aug 2026 was omitted.",
    )
    assert (_row(world, PRIMARY, AUGUST)["state"], _row(world, LEGACY, AUGUST)["state"]) == (
        "reopened",
        "open",
    )
    appended = _appended_through_api(world.place, _contract_id(world), _pre_standard("3300.00"))
    assert appended["computation"]["status"] == "SUCCEEDED", appended["computation"]
    assert _legacy_lines(world, "3300.00") == [(AUGUST, None, True)]


@pytest.mark.parametrize(
    ("command", "persona", "body"),
    [
        ("start-close", "maya", {"comment": "Legacy August"}),
        ("request-lock", "maya", {"certification_comment": "Legacy August complete"}),
        (
            "request-reopen",
            "priya",
            {"reason_code": "ERROR_CORRECTION", "comment": "Legacy August"},
        ),
        # the permanent-lock request is a Controller's (04 §16.8 rev 1.156; ruling R-83 (a))
        ("request-permanent-lock", "marcus", {"comment": "Legacy August"}),
    ],
)
def test_r112_e_the_legacy_book_has_no_close_of_its_own(
    world: ReportWorld, clock: FrozenClock, command: str, persona: str, body: dict[str, Any]
) -> None:
    """R-112 (e) (5): the four commands that move a period through its close refuse a LEGACY period
    state by name — 409 ``invalid-transition``, rule ``LEGACY_FOLLOWS_PRIMARY`` — whatever its
    state, and leave it as it is. Fail-first (the lane's measurement): start-close answered 200 and
    left a soft close that no lock could ever follow."""
    august = _row(world, LEGACY, AUGUST)
    if persona == "priya":  # the reopen request is a Revenue Reviewer's (PRD §5.6)
        world = verified(world, clock, "priya")
    refused = post(
        world.app,
        f"{PERIODS}/{august['id']}/{command}",
        getattr(world, persona),
        body,
        if_match=f'"r{august["row_version"]}"',
    )
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    problem = refused.json()
    assert problem["detail"] == FOLLOWS
    assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
        (RULE, FOLLOWS)
    ]
    after = _row(world, LEGACY, AUGUST)
    assert (after["state"], after["row_version"]) == (august["state"], august["row_version"])


def test_r112_e_a_legacy_period_reads_what_it_follows_and_still_opens(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-112 (e) (5), R-114 (d): API-S-Period of a LEGACY row names the primary book's state it
    follows — ``follows`` — and keeps its own state, which the primary's lock does not touch; a
    posting book's row has none. ``open`` is unchanged: a ``future`` LEGACY period opens through
    ``POST /periods/{id}/open`` as before, and reads the ``future`` primary period it follows."""
    assert _row(world, PRIMARY, AUGUST)["follows"] is None
    assert _row(world, LEGACY, AUGUST)["follows"] == {"book_code": PRIMARY, "state": "open"}
    _, world = period_locked(world, clock, entity_code=US01, period_key=AUGUST)
    legacy = _row(world, LEGACY, AUGUST)
    assert (legacy["state"], legacy["follows"]) == (
        "open",
        {"book_code": PRIMARY, "state": "closed"},
    )
    with _session(world) as session:  # the LEGACY row itself is untouched by the primary's lock
        stored = session.execute(
            select(period_state.c.state).where(period_state.c.id == UUID(str(legacy["id"])))
        ).scalar_one()
    assert str(stored) == "open"
    october = _row(world, LEGACY, OCTOBER)
    assert (october["state"], october["follows"]) == (
        "future",
        {"book_code": PRIMARY, "state": "future"},
    )
    opened = post(
        world.app,
        f"{PERIODS}/{october['id']}/open",
        world.maya,
        {"comment": "Open October of the legacy book"},
        if_match=f'"r{october["row_version"]}"',
    )
    assert opened.status_code == 200, opened.text
    october = _row(world, LEGACY, OCTOBER)
    assert (october["state"], october["follows"]) == (
        "open",
        {"book_code": PRIMARY, "state": "future"},
    )


# --- PER-LEGACY-POSTING-PERIOD-1: BR-CLS-03 for the book that follows -----------------------------


def _states(world: ReportWorld) -> dict[tuple[str, str], str]:
    """The state of September and October 2026 in the primary and in the LEGACY book."""
    return {
        (book, key): str(_row(world, book, key)["state"])
        for book in (PRIMARY, LEGACY)
        for key in (SEPTEMBER, OCTOBER)
    }


def _late(amount: str) -> dict[str, Any]:
    """Legacy revenue of L2-PCS dated 30 Sep 2026: the last day of the period these tests lock."""
    return {**_pre_standard(amount), "effective_date": SEPTEMBER_END}


def _record(world: ReportWorld, event: Mapping[str, Any]) -> HttpResponse:
    """``POST /contracts/{id}/events`` of ``C-ADOPT`` at its head, answered as it is."""
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == _contract_id(world))
    )
    return post(
        world.app,
        f"/api/v1/contracts/{_contract_id(world)}/events",
        world.place.author,
        {"events": [dict(event)]},
        if_match=f'"s{int(head)}"',
    )


def _events(world: ReportWorld) -> int:
    """The number of events ``C-ADOPT`` holds."""
    with _session(world) as session:
        return len(
            session.execute(
                select(contract_event.c.id).where(
                    contract_event.c.contract_id == _contract_id(world)
                )
            ).all()
        )


def test_br_cls_03_a_lock_of_the_primary_book_opens_the_legacy_books_next_period(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """PRD BR-CLS-03 rev 1.143 (04 §14.1 DB-07 rev 1.214): September is the last period the world
    opens, in both books. Its lock through the product opens October in the primary book and in
    the LEGACY book: one ``future → open`` transition each, with the comment of the lock's opening,
    one ``PERIOD_OPEN_REDIRTY`` job for each period state, and the lock's audit record names both.

    Fail-first (the decision opened the next period of the book it locked alone): the LEGACY
    book's October stayed ``future``, with no transition and no job of its own."""
    assert _states(world) == AS_OPENED
    _, world = period_locked(world, clock, entity_code=US01, period_key=SEPTEMBER)
    assert _states(world) == BOTH_OPENED
    opened = {book: UUID(str(_row(world, book, OCTOBER)["id"])) for book in (PRIMARY, LEGACY)}
    september = UUID(str(_row(world, PRIMARY, SEPTEMBER)["id"]))
    transition = period_state_transition
    with _session(world) as session:
        written = {
            str(row.book_code): (str(row.from_state), str(row.to_state), row.comment)
            for row in session.execute(
                select(
                    transition.c.book_code,
                    transition.c.from_state,
                    transition.c.to_state,
                    transition.c.comment,
                ).where(transition.c.period_state_id.in_(sorted(opened.values(), key=str)))
            )
        }
        deferred = sorted(
            (str(row.subject_type), str(row.subject_id))
            for row in session.execute(
                select(job.c.subject_type, job.c.subject_id).where(
                    job.c.kind == JobKind.PERIOD_OPEN_REDIRTY.value
                )
            )
        )
        lock_id = session.execute(
            select(period_state.c.current_lock_id).where(period_state.c.id == september)
        ).scalar_one()
        (after,) = session.execute(
            select(audit_event.c.after).where(
                audit_event.c.action == close_commands.LOCK_ACTION,
                audit_event.c.object_id == lock_id,
            )
        ).scalars()
    comment = close_commands.NEXT_OPENED.format(period_key=SEPTEMBER)
    assert written == {
        PRIMARY: ("future", "open", comment),
        LEGACY: ("future", "open", comment),
    }
    assert deferred == sorted(("period_state", str(state_id)) for state_id in opened.values())
    assert (after["next_period_opened"], after["legacy_next_period_opened"]) == (
        str(opened[PRIMARY]),
        str(opened[LEGACY]),
    )


def test_br_cls_03_a_late_legacy_amount_posts_in_the_period_the_lock_opened(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """The consequence BR-CLS-03 names — "so late events always have a first open period" — for
    a legacy amount: after September's lock, legacy revenue dated 30 September is recorded, its
    computation succeeds, and its two LEGACY lines are in October with September as their origin.

    Fail-first, measured through the product on the code before the item (2026-10-01): 201, the
    computation ``SUCCEEDED``, and no LEGACY line of the amount in any period — the LEGACY book's
    October was ``future``; opening it later re-marked nothing. With the posting-period helper
    alone, before the lock opened that period: 409 ``period-closed``."""
    _, world = period_locked(world, clock, entity_code=US01, period_key=SEPTEMBER)
    appended = _appended_through_api(world.place, _contract_id(world), _late("7700.00"))
    assert appended["computation"]["status"] == "SUCCEEDED", appended["computation"]
    assert _legacy_lines(world, "7700.00") == [(OCTOBER, SEPTEMBER, False)]


def test_br_cls_03_an_imported_late_legacy_amount_posts_in_the_period_the_lock_opened(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """The same amount through an import (template ``pre_standard_revenue``), which does not pass
    the mirror on ``POST /contracts/{id}/events`` and starts no computation: after September's
    lock Maya uploads legacy revenue dated 30 September, Priya approves the commit, and the next
    command on the contract — a note dated 1 October — computes. The amount's LEGACY lines are in
    October with September as their origin.

    Fail-first, on the code before the item: the commit and the note are accepted and no LEGACY
    line of the amount exists in any period."""
    _, world = period_locked(world, clock, entity_code=US01, period_key=SEPTEMBER)
    world, upload = committed_import(
        world,
        clock,
        name="us01-pre-standard-2026-09.csv",
        template="pre_standard_revenue",
        columns=PRE_STANDARD_COLUMNS,
        rows=[(C_ADOPT, SEPTEMBER_END, "L2-PCS", "6600.00", "USD")],
    )
    assert upload["status"] == "COMMITTED"
    assert _legacy_lines(world, "6600.00") == []  # an import commit starts no computation
    noted = _appended_through_api(
        world.place,
        _contract_id(world),
        {
            "event_type": "MEMO_UPDATED",
            "effective_date": "2026-10-01",
            "payload": {"memo_1": "Legacy revenue of September confirmed"},
        },
    )
    assert noted["computation"]["status"] == "SUCCEEDED", noted["computation"]
    assert _legacy_lines(world, "6600.00") == [(OCTOBER, SEPTEMBER, False)]


def test_err_78_a_held_legacy_next_period_refuses_the_lock_decision_by_name(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """PRD ERR-78 for the row the decision now takes (04 §14.1 DB-07 rev 1.214): another
    transaction holds the LEGACY book's ``future`` October — as an opening of that period in
    flight does. Marcus's approval of September's lock is refused at once, 409 ``lock-conflict``
    under rule ``NEXT_PERIOD_HELD``; the sentence names the period, which the rows of the two
    books share. Nothing is saved: September is still in soft close, October ``future`` in both
    books — the primary's row, taken first, went with the transaction — no lock record exists and
    the request is still pending. Once the holder is gone the request is decided again and both
    Octobers open.

    Fail-first (no LEGACY row was taken): the decision locked September while the LEGACY row was
    held, and left it ``future``."""
    pending = _lock_requested(world, clock, SEPTEMBER)
    world = pending.world
    soft_close = {**AS_OPENED, (PRIMARY, SEPTEMBER): "closing"}
    assert _states(world) == soft_close
    october = UUID(str(_row(world, LEGACY, OCTOBER)["id"]))
    with _session(world) as holder:
        held = holder.execute(
            select(period_state.c.state).where(period_state.c.id == october).with_for_update()
        ).scalar_one()
        assert str(held) == "future"
        refused = approve(world.app, pending.request_id, world.marcus)
        assert refused.status_code == 409, refused.text  # the status first: a 200 has no slug
        assert slug(refused) == "lock-conflict"
        problem = refused.json()
        assert problem["detail"] == OCTOBER_HELD
        assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
            (close_commands.RULE_NEXT_PERIOD_HELD, OCTOBER_HELD)
        ]
        holder.rollback()
    assert _states(world) == soft_close
    with _session(world) as session:
        locks = session.execute(
            select(period_lock.c.id).where(
                period_lock.c.period_id
                == UUID(str(_row(world, PRIMARY, SEPTEMBER)["period"]["id"]))
            )
        ).all()
        status = session.execute(
            select(approval_request.c.status).where(
                approval_request.c.id == UUID(pending.request_id)
            )
        ).scalar_one()
    assert locks == [] and str(getattr(status, "value", status)) == "PENDING"
    decided = approve(world.app, pending.request_id, world.marcus)
    assert decided.status_code == 200, decided.text
    assert _states(world) == BOTH_OPENED


def test_a_legacy_book_kept_again_after_the_lock_refuses_until_its_next_period_is_opened(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """The state the lock's opening does not reach, through the product: US01 stops keeping the
    LEGACY book (``PUT /entities/{id}/books/LEGACY``), September is locked — a book the entity
    does not keep opens no period, so the LEGACY book's October stays ``future`` — and US01 keeps
    the book again.

    While the book is not kept the mirror does not ask it (dev-guide DG-KRN-TIME-04 rev 1.197):
    a note dated in the locked period is recorded. Kept again, no period is postable in both
    books for a date in September, and the mirror refuses the event before anything is saved:
    409 ``period-closed`` (PRD ERR-15, ``EREV-LED-003``), naming the primary book, whose period
    is the closed one. The way out is the opening of the LEGACY book's October: the same event is
    then recorded and its amount is in October with September as its origin.

    Fail-first. With the helper following the primary and the mirror asking every book with
    period states: the note was refused, 409, for a book the entity did not keep, with no way
    out. On the code before the item: the legacy event was accepted while October was ``future``
    and its amount was posted in no period."""
    entity_id = _row(world, PRIMARY, SEPTEMBER)["entity"]["id"]
    book_path = f"/api/v1/entities/{entity_id}/books/LEGACY"
    dropped = put(world.app, book_path, world.marcus, {"is_enabled": False})
    assert (dropped.status_code, dropped.json()["is_enabled"]) == (200, False), dropped.text
    _, world = period_locked(world, clock, entity_code=US01, period_key=SEPTEMBER)
    not_reached = {**BOTH_OPENED, (LEGACY, OCTOBER): "future"}
    assert _states(world) == not_reached
    note = {
        "event_type": "MEMO_UPDATED",
        "effective_date": SEPTEMBER_END,
        "payload": {"memo_1": "A note dated in the locked period"},
    }
    noted = _record(world, note)
    assert noted.status_code == 201, noted.text
    kept = put(world.app, book_path, world.marcus, {"is_enabled": True})
    assert (kept.status_code, kept.json()["is_enabled"]) == (200, True), kept.text
    assert _states(world) == not_reached
    before = _events(world)
    refused = _record(world, _late("7700.00"))
    assert refused.status_code == 409, refused.text  # the status first: a 201 has no slug
    assert slug(refused) == "period-closed"
    assert (refused.json()["detail"], refused.json()["code"]) == (SEPTEMBER_CLOSED, "EREV-LED-003")
    assert _events(world) == before and _legacy_lines(world, "7700.00") == []
    october = _row(world, LEGACY, OCTOBER)
    opened = post(
        world.app,
        f"{PERIODS}/{october['id']}/open",
        world.maya,
        {"comment": "Open October of the legacy book"},
        if_match=f'"r{october["row_version"]}"',
    )
    assert opened.status_code == 200, opened.text
    recorded = _record(world, _late("7700.00"))
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["computation"]["status"] == "SUCCEEDED", recorded.json()["computation"]
    assert _legacy_lines(world, "7700.00") == [(OCTOBER, SEPTEMBER, False)]


# --- CLO-RUN-LEGACY-1: a close run is a command of a close (PRD ERR-76 rev 1.160) ---------------


def _run_writes(world: ReportWorld) -> dict[str, int]:
    """What the start of a close run leaves behind: run rows, ``CLOSE_RUN`` jobs and the audit
    events of a run."""
    with _session(world) as session:
        found = {
            "runs": session.execute(select(func.count()).select_from(close_run)).scalar_one(),
            "jobs": session.execute(
                select(func.count()).select_from(job).where(job.c.kind == JobKind.CLOSE_RUN.value)
            ).scalar_one(),
            "audit events": session.execute(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.object_type == "close_run")
            ).scalar_one(),
        }
    return {name: int(count) for name, count in found.items()}


def _told_the_books_rule(refused: HttpResponse) -> None:
    """409 ``invalid-transition`` under ``LEGACY_FOLLOWS_PRIMARY`` with the sentence of PRD
    ERR-76, as the four period commands answer."""
    assert refused.status_code == 409, refused.text  # the status first: a 202 has no slug
    assert slug(refused) == "invalid-transition", refused.text
    problem = refused.json()
    assert problem["detail"] == FOLLOWS
    assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
        (RULE, FOLLOWS)
    ]


def test_clo_run_legacy_1_a_close_run_of_the_legacy_book_is_refused_by_name(
    world: ReportWorld,
) -> None:
    """``POST /close-runs`` with ``book`` ``LEGACY`` (item CLO-RUN-LEGACY-1; the supervisor's
    ruling of 2026-10-01; 04 T-REF-06 "The LEGACY book's rows" rev 1.230): the LEGACY book has no
    close of its own, and a close run is a command of a close — 409 by ERR-76's name and
    sentence, before anything is written: no run, no job, no audit event, and the number series
    is untouched — the primary book's run that follows takes the series' first number.

    Fail-first (measured on 38889398): 202; the job passed its period-end steps, stopped at
    ``JOURNAL_SUMMARIZATION`` on an unhandled error — "The job stopped with an unexpected
    error." — and left the LEGACY period a row of a window."""
    before = _run_writes(world)
    assert before["runs"] == 0
    refused = runs.start(world.app, world.maya, entity_code=US01, period_key=SEPTEMBER, book=LEGACY)
    _told_the_books_rule(refused)
    assert runs.ID_HEADER not in refused.headers
    assert _run_writes(world) == before
    started = runs.start(
        world.app, world.maya, entity_code=US01, period_key=SEPTEMBER, book=PRIMARY
    )
    assert started.status_code == 202, started.text
    first = runs.shown(world.app, world.maya, str(started.headers[runs.ID_HEADER]))
    assert first["close_run_no"] == "CLS-000001"


def test_clo_run_legacy_1_only_a_caller_who_may_close_is_told_the_books_rule(
    world: ReportWorld,
) -> None:
    """The order of the refusals. Priya, a Revenue Reviewer, holds no ``period.close``: she is
    answered for the LEGACY book exactly as for the primary one, and nothing is written for
    either. Maya, who may run the close of US01, is told the book's rule."""
    before = _run_writes(world)
    denied = {
        book: runs.start(world.app, world.priya, entity_code=US01, period_key=SEPTEMBER, book=book)
        for book in (PRIMARY, LEGACY)
    }
    answers = {book: (found.status_code, slug(found)) for book, found in denied.items()}
    assert answers == {PRIMARY: (403, "forbidden"), LEGACY: (403, "forbidden")}
    assert denied[LEGACY].json()["detail"] == denied[PRIMARY].json()["detail"]
    assert _run_writes(world) == before
    _told_the_books_rule(
        runs.start(world.app, world.maya, entity_code=US01, period_key=SEPTEMBER, book=LEGACY)
    )
    assert _run_writes(world) == before


def test_clo_run_legacy_1_a_legacy_run_is_not_resumed_and_can_still_be_cancelled(
    world: ReportWorld,
) -> None:
    """``POST /close-runs/{id}/resume`` of a run of the LEGACY book — put in place as a fixture
    row, since the start refuses and no deployment holds one — is refused by the same name and
    leaves the run as it is; a caller without ``period.close`` is answered as for any run.
    ``cancel`` stays: it ends a run and starts nothing.

    Fail-first: the resume answered 202 and deferred a ``CLOSE_RUN`` job for the LEGACY run."""
    september = _row(world, LEGACY, SEPTEMBER)
    blocked = close_run_values(
        world.tenant_id,
        entity_id=UUID(str(september["entity"]["id"])),
        period_id=UUID(str(september["period"]["id"])),
        book_code=LEGACY,
        status="BLOCKED",
    )
    with _session(world) as session:
        session.execute(insert(close_run).values(**blocked))
    run_id = str(blocked["id"])
    before = _run_writes(world)
    denied = runs.resume(world.app, world.priya, run_id)
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    _told_the_books_rule(runs.resume(world.app, world.maya, run_id))
    assert _run_writes(world) == before
    assert runs.shown(world.app, world.maya, run_id)["status"] == "BLOCKED"
    cancelled = runs.cancel(world.app, world.maya, run_id, "The LEGACY book has no close")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"


# --- F11: the next period's row is not kept when it opened between the two reads --------------


@pytest.mark.parametrize("book", [PRIMARY, LEGACY])
def test_f11_a_next_period_opened_between_the_two_reads_is_given_back(
    world: ReportWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch, book: str
) -> None:
    """Finding F11 of the independent review of 2026-10-01 (04 §14.1 DB-07 rev 1.229; dev-guide
    DG-KRN-DB-08 (1a) rev 1.218). The decision reads the next period's row without a lock and
    takes it ``FOR UPDATE NOWAIT`` only when it is ``future``. October of ``book`` is opened —
    through the product, and committed — between those two reads. The decision then holds
    NOTHING of that October: when it comes to its gates, another session takes the row ``FOR
    SHARE NOWAIT``, as a posting into the period that has just opened does.

    How the decision ends is the product's as it was. The LEGACY book's October opened: the
    decision completes and opens the primary's. The primary's October opened: the opening
    re-marked the contract that has lines there (05 SCH-06), so the gate ``NO_DIRTY_GROUPS``
    refuses the lock, nothing of the decision is saved, and that October stays open.

    Fail-first: the locking read took the row it found ``open`` and kept it — the other
    session's read answered SQLSTATE 55P03 — to the decision's end: for the LEGACY row through
    the gates, the freeze of twelve datasets and the commit, with every posting into the opened
    period waiting."""
    pending = _lock_requested(world, clock, SEPTEMBER)
    world = pending.world
    october = _row(world, book, OCTOBER)
    assert october["state"] == "future"
    read = close_commands._next_period_state
    seen: dict[str, Any] = {}

    def opened_between(
        session: Any, scope: Any, *, lock: bool, book_code: str | None = None
    ) -> Any:
        found = read(session, scope, lock=lock, book_code=book_code)
        of_book = scope.book_code if book_code is None else book_code
        if not lock and of_book == book and "opened" not in seen:
            opened = post(
                world.app,
                f"{PERIODS}/{october['id']}/open",
                world.maya,
                {"comment": "Open October while September is being locked"},
                if_match=f'"r{october["row_version"]}"',
            )
            seen["opened"] = opened.status_code
            seen["found"] = None if found is None else str(found["state"])
        return found

    evaluate_gates = close_commands.gates.evaluate_gates

    def share_then_evaluate(*args: Any, **kwargs: Any) -> Any:
        if "shared" not in seen:
            with _session(world) as other:
                try:
                    other.execute(
                        select(period_state.c.id)
                        .where(period_state.c.id == UUID(str(october["id"])))
                        .with_for_update(read=True, nowait=True)
                    ).scalar_one()
                    seen["shared"] = True
                except DBAPIError as error:
                    seen["shared"] = getattr(error.orig, "sqlstate", None)
                other.rollback()
        return evaluate_gates(*args, **kwargs)

    monkeypatch.setattr(close_commands, "_next_period_state", opened_between)
    monkeypatch.setattr(close_commands.gates, "evaluate_gates", share_then_evaluate)
    decided = approve(world.app, pending.request_id, world.marcus)
    assert seen == {"opened": 200, "found": "future", "shared": True}, decided.text
    if book == LEGACY:
        assert decided.status_code == 200, decided.text
        assert _states(world) == BOTH_OPENED
        return
    assert decided.status_code == 409, decided.text  # the status first: a 200 has no slug
    assert slug(decided) == "close-gates-failed"
    assert [error["rule_id"] for error in decided.json()["errors"]] == ["NO_DIRTY_GROUPS"]
    assert _states(world) == {
        **AS_OPENED,
        (PRIMARY, SEPTEMBER): "closing",
        (PRIMARY, OCTOBER): "open",
    }
