"""Item JRN-HELD-AFTER-EXPORT-1 (release blocker; the supervisor's ruling of 2026-10-02 on this
lane's measurement; register index 223; ENGINE_SPEC_B rev 1.164 S14-R-16 and S14-R-17; 04 rev 1.267
DB-16, T-SL-06 and §16.7; PRD rev 1.184; BUILD_SPEC CLO-8): the next run of an entity, book and
period takes over what a run of that key left out under a journal-export hold.

Measured before the item, through the product: a posting left out under a hold by a run that was
then exported was reached by no run after the hold's release — a new calculation had nothing to
summarize, the exported run could not be cancelled, the close run's step calculated nothing, the
lock was refused on ``JE_COMPLETE`` and the gate cannot be waived. September 2026 of AVM-US could
not be locked, and 9,863.01 of WLD-K-02's revenue reached no ledger. That road, turned, is
``tests/domain/close/test_close_run_steps.py::
test_journal_summarization_takes_over_what_an_exported_run_left_out_and_the_period_locks``.

The rule. Beside its range — which starts where the runs end, as before (DB-16) — a run
summarizes every line that a run of its key which is not cancelled left out as held, that no such
run has taken over since, and whose contract is under no open journal-export hold now. It names
them by id in its ``CALCULATE`` event and in a detail file of its own. ``JE_COMPLETE`` counts a
line as covered by the run whose range holds it and that did not leave it out, or by the run that
took it over. A line is taken over once; the cancel of the taking run gives it back; a line left
out by a run that was cancelled is in the next run's range, as before, and is not taken over too.

World: the close world's September 2026 of AVM-US with sealed postings of contracts of their own
(those of ``test_empty_run``); every run is asked for by ``POST /journal-runs`` and calculated by
its job.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event
from erev_api.domain.journals import summarise
from erev_api.enums import ChecklistStatus
from erev_api.files.store import LocalFileStore, open_file
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.close_world import (
    CloseWorld,
    close_world,
    requested_journal_run,
    run_journal_job,
    sealed_activity,
    system_session,
)
from support.db import TestDatabase
from support.reference import get, post
from support.worlds import JOURNAL_RUNS
from test_closed_period_guard import KEY as SEPTEMBER
from test_closed_period_guard import _calculated as _run_of_september
from test_closed_period_guard import _runs as _runs_of_september
from test_completeness import PERIOD_END, _completeness, _keep_legacy_book, _release_hold
from test_empty_run import REASON, RULE, _accounts, _delivery, _held


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def close(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


# --- helpers --------------------------------------------------------------------------------------


def _calculated_event(close: CloseWorld, run_id: str) -> dict[str, Any]:
    """The ``after`` of the run's ``CALCULATE`` audit event."""
    with system_session(close) as session:
        after = session.execute(
            select(audit_event.c.after).where(
                audit_event.c.action == summarise.CALCULATE_ACTION,
                audit_event.c.object_id == UUID(run_id),
            )
        ).scalar_one()
    return dict(after)


def _event_ids(event: dict[str, Any], member: str) -> set[UUID]:
    return {UUID(str(value)) for value in event[member]}


def _shown(close: CloseWorld, run_id: str) -> dict[str, Any]:
    shown = get(close.app, f"{JOURNAL_RUNS}/{run_id}", close.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _september(close: CloseWorld) -> list[tuple[str, int]]:
    """(state, line count) of September's journal runs, oldest first."""
    return [(state, lines) for _, state, lines in _runs_of_september(close)]


def _cancelled(close: CloseWorld, run_id: str) -> None:
    done = post(close.app, f"{JOURNAL_RUNS}/{run_id}/cancel", close.maya, {"reason": REASON})
    assert (done.status_code, done.json()["state"]) == (200, "cancelled"), done.text


def _drilled(close: CloseWorld, run_id: str) -> set[UUID]:
    """The subledger lines the journal lines of the run drill to (``GET /journal-lines/{id}/
    drill``)."""
    listed = get(close.app, f"{JOURNAL_RUNS}/{run_id}/lines", close.maya, {"limit": 200})
    assert listed.status_code == 200, listed.text
    found: set[UUID] = set()
    for line in listed.json()["items"]:
        drill = get(close.app, line["links"]["drill"], close.maya, {"limit": 200})
        assert drill.status_code == 200, drill.text
        found |= {UUID(str(item["id"])) for item in drill.json()["items"]}
    return found


# --- the rules of the set -------------------------------------------------------------------------


@pytest.mark.slow
def test_a_line_is_taken_over_once_and_given_back_by_the_cancel_of_the_taking_run(
    close: CloseWorld,
) -> None:
    """A run leaves a posting out under a journal-export hold; the hold is released. The next
    run takes the posting's two lines over: its range is empty — it starts where the runs end,
    DB-16 as before — and it holds 100.00, names the lines in its ``CALCULATE`` event and in its
    detail file with the run that left them out, and its journal lines drill to them. Before the
    item that calculation was refused, and the posting stayed uncovered until the first run was
    cancelled.

    A line is taken over once. The run after the taking run is made for a posting sealed since
    and holds that posting alone: its event names no line taken over. The cancel of the taking
    run — after the run that follows it, latest first (R-52 (b)) — gives the lines back: a
    cancelled run's record counts for nothing, the lines are uncovered again, and the period's
    next run takes them over beside the posting of its range."""
    with system_session(close) as session:
        accounts = _accounts(session, close)
        _delivery(session, close, accounts, "SF-ORD-30001", "-250.00")
        disputed = _delivery(session, close, accounts, "SF-ORD-30002", "-100.00")
        hold_id = _held(session, close, disputed, "Customer dispute on invoice INV-US-30002")
    first_id = _run_of_september(close)  # leaves the disputed posting out
    first = _shown(close, first_id)
    left = _calculated_event(close, first_id)
    assert _event_ids(left, "held_subledger_line_ids") == set(disputed.line_ids)
    assert left["taken_over_subledger_line_ids"] == []
    close.place.clock.advance(timedelta(minutes=5))
    _release_hold(close, hold_id, disputed.contract_id)

    taking_id = _run_of_september(close)  # before the item: 409, PRD ERR-96
    taking = _shown(close, taking_id)
    assert (taking["totals"]["line_count"], taking["totals"]["debit_functional"]["amount"]) == (
        2,
        "100.00",
    )
    covered = first["coverage"]["to_chain_seq"]
    assert (taking["coverage"]["from_chain_seq"], taking["coverage"]["to_chain_seq"]) == (
        covered,
        covered,
    )
    took = _calculated_event(close, taking_id)
    assert _event_ids(took, "taken_over_subledger_line_ids") == set(disputed.line_ids)
    assert (took["held_subledger_line_ids"], took["counts"]["detail_lines"]) == ([], 2)
    with system_session(close) as session:
        _, stream = open_file(
            session,
            UUID(str(took["taken_over_detail_file_id"])),
            files=close.place.files,
            keyring=close.place.keyring,
        )
        content = stream.read()
    assert hashlib.sha256(content).hexdigest() == took["taken_over_detail_sha256"]
    assert {
        (item["subledger_line_id"], item["left_out_by_run_no"], item["left_out_by_run_id"])
        for item in json.loads(content)["taken_over"]
    } == {(str(line), first["run_no"], first_id) for line in disputed.line_ids}
    assert _drilled(close, taking_id) == set(disputed.line_ids)
    assert _drilled(close, first_id).isdisjoint(disputed.line_ids)
    assert _september(close) == [("draft", 2), ("draft", 2)]
    whole = _completeness(close)
    assert (whole.status, whole.count, whole.run_count) == (ChecklistStatus.PASSED, 0, 2)

    with system_session(close) as session:
        later = _delivery(session, close, accounts, "SF-ORD-30003", "-40.00")
    third_id = _run_of_september(close)
    third = _calculated_event(close, third_id)
    assert (third["taken_over_subledger_line_ids"], third["counts"]["detail_lines"]) == ([], 2)
    assert third["taken_over_detail_file_id"] is None
    assert _shown(close, third_id)["totals"]["debit_functional"]["amount"] == "40.00"
    assert _drilled(close, third_id) == set(later.line_ids)
    once = _completeness(close)
    assert (once.status, once.count, once.run_count) == (ChecklistStatus.PASSED, 0, 3)

    _cancelled(close, third_id)
    _cancelled(close, taking_id)
    back = _completeness(close)
    assert (back.status, back.count, back.run_count) == (ChecklistStatus.FAILED, 2, 1)
    assert {item.subledger_line_id for item in back.uncovered} == {
        *disputed.line_ids,
        *later.line_ids,
    }
    again_id = _run_of_september(close)
    again = _calculated_event(close, again_id)
    assert _event_ids(again, "taken_over_subledger_line_ids") == set(disputed.line_ids)
    assert again["counts"]["detail_lines"] == 4
    assert _shown(close, again_id)["totals"]["debit_functional"]["amount"] == "140.00"
    assert _drilled(close, again_id) == {*disputed.line_ids, *later.line_ids}
    last = _completeness(close)
    assert (last.status, last.count, last.run_count) == (ChecklistStatus.PASSED, 0, 2)


@pytest.mark.slow
def test_a_line_left_out_by_a_cancelled_run_lies_in_the_next_runs_range_and_is_not_taken_over(
    close: CloseWorld,
) -> None:
    """The ordinary road stays as it was. September's first run left the period's one posting
    out; the hold is released and that run is cancelled. Its record counts for nothing, so the
    set of lines to take over is empty, and the posting lies in the next run's range, which
    starts at the first seal: the run holds it once — two lines, 100.00 — and names no line taken
    over."""
    with system_session(close) as session:
        accounts = _accounts(session, close)
        disputed = _delivery(session, close, accounts, "SF-ORD-30004", "-100.00")
        hold_id = _held(session, close, disputed, "Customer dispute on invoice INV-US-30004")
    first_id = _run_of_september(close)
    assert _september(close) == [("draft", 0)]
    close.place.clock.advance(timedelta(minutes=5))
    _release_hold(close, hold_id, disputed.contract_id)
    _cancelled(close, first_id)

    second_id = _run_of_september(close)
    second = _shown(close, second_id)
    assert second["coverage"]["from_chain_seq"] == 0
    assert (second["totals"]["line_count"], second["totals"]["debit_functional"]["amount"]) == (
        2,
        "100.00",
    )
    event = _calculated_event(close, second_id)
    assert (event["taken_over_subledger_line_ids"], event["held_subledger_line_ids"]) == ([], [])
    assert event["taken_over_detail_file_id"] is None
    assert _drilled(close, second_id) == set(disputed.line_ids)
    whole = _completeness(close)
    assert (whole.status, whole.count, whole.run_count) == (ChecklistStatus.PASSED, 0, 1)


@pytest.mark.slow
def test_a_line_whose_contract_is_still_under_a_hold_is_not_taken_over(close: CloseWorld) -> None:
    """A run left the postings of two contracts out, each under a hold of its own. One hold is
    released: the next run takes that contract's lines over and leaves the other's where they
    are — with the record of the run that left them out; it does not list them as held again,
    for they are in no range of its own — and ``JE_COMPLETE`` goes on naming them as held. The
    second release makes the run that takes them."""
    with system_session(close) as session:
        accounts = _accounts(session, close)
        _delivery(session, close, accounts, "SF-ORD-30005", "-250.00")
        one = _delivery(session, close, accounts, "SF-ORD-30006", "-100.00")
        other = _delivery(session, close, accounts, "SF-ORD-30007", "-60.00")
        hold_one = _held(session, close, one, "Customer dispute on invoice INV-US-30006")
        hold_other = _held(session, close, other, "Customer dispute on invoice INV-US-30007")
    first_id = _run_of_september(close)
    left = _calculated_event(close, first_id)
    assert _event_ids(left, "held_subledger_line_ids") == {*one.line_ids, *other.line_ids}
    close.place.clock.advance(timedelta(minutes=5))
    _release_hold(close, hold_one, one.contract_id)

    second_id = _run_of_september(close)
    took = _calculated_event(close, second_id)
    assert _event_ids(took, "taken_over_subledger_line_ids") == set(one.line_ids)
    assert took["held_subledger_line_ids"] == []
    assert _shown(close, second_id)["totals"]["debit_functional"]["amount"] == "100.00"
    held = _completeness(close)
    assert (held.status, held.count, held.uncovered) == (ChecklistStatus.FAILED, 1, ())
    assert {item.subledger_line_id for item in held.held} == set(other.line_ids)
    assert {item.hold_id for item in held.held} == {hold_other}

    close.place.clock.advance(timedelta(minutes=5))
    _release_hold(close, hold_other, other.contract_id)
    third_id = _run_of_september(close)
    last = _calculated_event(close, third_id)
    assert _event_ids(last, "taken_over_subledger_line_ids") == set(other.line_ids)
    whole = _completeness(close)
    assert (whole.status, whole.count, whole.run_count) == (ChecklistStatus.PASSED, 0, 3)


@pytest.mark.slow
def test_a_legacy_line_left_out_is_taken_over_by_a_delta_run_alone(close: CloseWorld) -> None:
    """ENGINE_SPEC_B S14-R-17 rev 1.164 with S14-R-23: a ``DELTA`` run reads the LEGACY book
    beside the primary book, so it is the run that leaves a LEGACY line out under a hold, and a
    ``DELTA`` run is the run that takes it over. September's ``DELTA`` run holds the primary
    posting and leaves the LEGACY posting of a contract under a hold out; the hold is released. A
    ``GROSS`` run reads no LEGACY line: asked for now, it would hold no line and is refused (PRD
    ERR-96). The next ``DELTA`` run takes the two LEGACY lines over — 100.00, no negation — and
    the assertion, which compares the ``DELTA`` journals with what the ``DELTA`` runs covered in
    both books, passes."""
    _keep_legacy_book(close)
    with system_session(close) as session:
        revenue, unbilled = accounts = _accounts(session, close)
        _delivery(session, close, accounts, "SF-ORD-30008", "-250.00")
        legacy = sealed_activity(
            session,
            close,
            account=revenue,
            period_id=close.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("100.00")],
            external_id="LEG-0003",
            obligation_key="O1",
            book_code="LEGACY",
            account_role="REVENUE",
            legacy_key="LEG-0003",
            offset_account=unbilled,
            offset_columns={"account_role": "UNBILLED_RECEIVABLE", "legacy_key": "LEG-0003"},
        )
        hold_id = _held(session, close, legacy, "Pre-standard revenue of LEG-0003 under review")

    def delta_run() -> str:
        job_id, run_id = requested_journal_run(close, mode="DELTA")
        finished = run_journal_job(close, job_id)
        assert finished["state"] == "SUCCEEDED", finished
        return str(run_id)

    first_id = delta_run()
    left = _calculated_event(close, first_id)
    assert _event_ids(left, "held_subledger_line_ids") == set(legacy.line_ids)
    assert _shown(close, first_id)["totals"]["debit_functional"]["amount"] == "250.00"
    close.place.clock.advance(timedelta(minutes=5))
    _release_hold(close, hold_id, legacy.contract_id)

    gross = post(
        close.app, JOURNAL_RUNS, close.maya, {"entity_code": "AVM-US", "period_key": SEPTEMBER}
    )
    assert gross.status_code == 409, gross.text
    assert gross.json()["errors"][0]["rule_id"] == RULE

    taking_id = delta_run()
    took = _calculated_event(close, taking_id)
    assert _event_ids(took, "taken_over_subledger_line_ids") == set(legacy.line_ids)
    taking = _shown(close, taking_id)
    assert (taking["mode"], taking["totals"]["debit_functional"]["amount"]) == ("DELTA", "100.00")
    whole = _completeness(close)
    assert (whole.status, whole.count, whole.modes, whole.run_count) == (
        ChecklistStatus.PASSED,
        0,
        ("DELTA",),
        2,
    )
