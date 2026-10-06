"""CLO-10 completeness assertions on a database (03 REQ-JE-005; BUILD_SPEC CLO-10 acceptance;
CTL-019; 04 T-CLS-02 ``JE_COMPLETE``, T-CLS-03 ``result``; F-CLO record §25.18).

DB-bound scenarios (``CloseWorld``): NOT RUN on the authoring worktree (databases not
provisioned); measured by the integrated batch on merged main. The sequence-gap scenario is a pure
call over a fixture list and runs on the CPU. The held-only witness carries Codex
production-20260921-0920 §3 (S14-R-17 retained held detail; release ≠ recovery) with the 1054 R5
ordering; the equal-instant boundary in both orders (1317 R5-ORDER-1: coverage reads each run's
recorded exclusions, never timestamps), the DELTA / LEGACY coverage witness (1054 R1) and the
per-run JE continuity witness (1054 R2) follow. Every posting is balanced with a genuine
counterpart line (1317 CLO-FIXTURE-SEAL-1); the finding unit is the sealed posting. Coverage
limits: the new-delivery case seeds sealed rows directly; the held cases are single-contract, USD
only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    audit_event,
    close_checklist_item,
    close_checklist_template,
    contract,
    contract_event,
    contract_hold,
    gl_account,
    journal_batch,
    journal_run,
)
from erev_api.domain.close import gates
from erev_api.domain.journals import completeness, summarise
from erev_api.enums import ChecklistStatus
from erev_api.events.payloads import HoldReleasedV1
from erev_api.files.store import LocalFileStore, open_file
from erev_api.main import create_app
from erev_engine.canonical import sha256_hex
from fastapi import FastAPI
from sqlalchemy import insert, select, text, update
from support.close_world import (
    BOOK,
    CloseWorld,
    close_world,
    requested_journal_run,
    run_journal_job,
    sealed_activity,
    system_session,
)
from support.db import TestDatabase
from support.reference import ENTITIES, PERIODS, periods, post, put
from support.rows import contract_event_values, contract_hold_values, gl_account_values

PERIOD_END: Final = date(2026, 9, 30)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _completeness(world: CloseWorld) -> completeness.CompletenessResult:
    with world.place.uow() as uow:
        return completeness.assert_completeness(uow, world.entity_id, BOOK, world.period_id)


def _je_complete(world: CloseWorld) -> gates.GateResult:
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    return next(result for result in results if result.gate_check_code == gates.JE_COMPLETE)


def _stored_result(world: CloseWorld) -> dict[str, Any] | None:
    with system_session(world) as session:
        return session.execute(
            select(close_checklist_item.c.result)
            .select_from(
                close_checklist_item.join(
                    close_checklist_template,
                    close_checklist_template.c.id
                    == close_checklist_item.c.close_checklist_template_id,
                )
            )
            .where(
                close_checklist_item.c.entity_id == world.entity_id,
                close_checklist_item.c.period_id == world.period_id,
                close_checklist_template.c.gate_check_code == gates.JE_COMPLETE,
            )
        ).scalar_one_or_none()


@pytest.mark.control("CTL-019")
def test_ctl_019_journal_totals_differ_from_waterfall(world: CloseWorld) -> None:
    """After a run is calculated, a delivery in the same open period adds revenue (a second sealed
    posting to account 5001 with its own schedule line): ``assert_completeness`` is FAILED naming
    account 5001 and the uncovered schedule line, ``JE_COMPLETE`` FAILED with count 1; a second run
    (contiguous coverage, DB-16) makes both PASSED and the checklist item stores the result."""
    with system_session(world) as session:
        revenue = gl_account_values(world.tenant_id, code="5001")
        unbilled = gl_account_values(world.tenant_id, code="1201")
        session.execute(insert(gl_account).values(**revenue))
        session.execute(insert(gl_account).values(**unbilled))
        # Each delivery is one balanced posting: the REVENUE credit on 5001 (the schedule line) and
        # its UNBILLED_RECEIVABLE debit on 1201 (Codex 1317 CLO-FIXTURE-SEAL-1).
        first = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-250.00")],
            external_id="SF-ORD-10001",
            obligation_key="O1",
            with_schedule_line=True,
            offset_account=unbilled,
            offset_columns={"account_role": "UNBILLED_RECEIVABLE"},
        )
    job_id, _ = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    covered = _completeness(world)
    assert (covered.status, covered.count, covered.run_count) == (ChecklistStatus.PASSED, 0, 1)
    assert covered.covered_to >= 1 and first.schedule_line_id is not None

    with system_session(world) as session:
        later = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-250.00")],
            external_id="SF-ORD-10002",
            obligation_key="O1",
            with_schedule_line=True,
            offset_account=unbilled,
            offset_columns={"account_role": "UNBILLED_RECEIVABLE"},
        )
    incomplete = _completeness(world)
    # One uncovered posting (count 1) naming both of its lines — the schedule line on 5001 and its
    # counterpart on 1201.
    assert (incomplete.status, incomplete.count) == (ChecklistStatus.FAILED, 1)
    assert len(incomplete.uncovered_postings) == 1
    assert {item.subledger_line_id for item in incomplete.uncovered} == set(later.line_ids)
    (uncovered,) = [item for item in incomplete.uncovered if item.account_code == "5001"]
    assert (uncovered.account_code, uncovered.schedule_line_id) == ("5001", later.schedule_line_id)
    assert incomplete.detail is not None
    assert "5001" in incomplete.detail and str(later.schedule_line_id) in incomplete.detail
    gate = _je_complete(world)
    assert (gate.status, gate.count, gate.detail) == (
        ChecklistStatus.FAILED,
        1,
        incomplete.detail,
    )

    job_id, _ = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    complete = _completeness(world)
    assert (complete.status, complete.count, complete.run_count) == (ChecklistStatus.PASSED, 0, 2)
    gate = _je_complete(world)
    assert (gate.status, gate.count, gate.detail) == (ChecklistStatus.PASSED, 0, None)
    stored = _stored_result(world)
    assert stored is not None and (stored["count"], stored["detail"]) == (0, None)


def test_sequence_gap_detected() -> None:
    """``assert_completeness`` over entries with ``je_seq`` 1, 2 and 4 returns FAILED with the
    detail "JE sequence gap after 2" — the pure rule the database wrapper feeds."""
    result = completeness.assess(
        activity=[],
        journal_totals={},
        entry_seqs=[[1, 2, 4]],
        covered_to=3,
        run_count=1,
    )
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        1,
        "JE sequence gap after 2",
    )
    assert result.gaps == (2,)


def test_interleaved_period_runs_are_not_a_sequence_gap() -> None:
    """1054 R2: JE numbers are allocated per entity across periods and books; this period's runs
    hold 1 and 3 while 2 belongs to another period — continuity is per run, so no gap."""
    result = completeness.assess(
        activity=[], journal_totals={}, entry_seqs=[[1], [3]], covered_to=0, run_count=2
    )
    assert (result.status, result.count, result.gaps) == (ChecklistStatus.PASSED, 0, ())


def test_no_run_is_a_named_failure(world: CloseWorld) -> None:
    """Without a run the assertion fails closed by name, as the gate does."""
    result = _completeness(world)
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        1,
        completeness.RUN_NOT_CALCULATED,
    )
    gate = _je_complete(world)
    assert (gate.status, gate.count, gate.detail) == (
        ChecklistStatus.FAILED,
        1,
        completeness.RUN_NOT_CALCULATED,
    )


def _release_hold(world: CloseWorld, hold_id: UUID, contract_id: UUID) -> None:
    """A release is an appended ``HOLD_RELEASED`` event of the held contract naming the hold, the
    head advanced first (DB-08; 04 §16.3; ck_contract_hold__release)."""
    now = world.place.clock.now()
    with system_session(world) as session:
        head, entity_id = session.execute(
            select(contract.c.head_stream_version, contract.c.contracting_entity_id).where(
                contract.c.id == contract_id
            )
        ).one()
        session.execute(
            update(contract)
            .where(contract.c.id == contract_id)
            .values(head_stream_version=int(head) + 1)
        )
        payload = HoldReleasedV1(hold_id=hold_id, comment="Dispute settled").model_dump(mode="json")
        release = contract_event_values(
            world.tenant_id,
            contract_id=contract_id,
            contracting_entity_id=entity_id,
            stream_version=int(head) + 1,
            event_type="HOLD_RELEASED",
            effective_date=now.date(),
            payload=payload,
            payload_sha256=sha256_hex(payload),
        )
        session.execute(insert(contract_event).values(**release))
        session.execute(
            update(contract_hold)
            .where(contract_hold.c.id == hold_id)
            .values(released_at=now, released_event_id=release["id"])
        )


def test_held_only_run_retains_held_detail_and_release_is_not_recovery(world: CloseWorld) -> None:
    """S14-R-17 held-only witness (Codex 0920 §3): every line the run reads belongs to a contract
    under an open ``journal_export`` hold, so the run writes no batch — yet the held lines are
    retained by id in the run's held detail file, named by the CALCULATE audit event, and the
    assertion names them as held blockers with the hold. Releasing the hold does not recover them:
    they become plain uncovered lines. The period's next run does: it starts after the prior range
    (DB-16) and takes the released lines over (item JRN-HELD-AFTER-EXPORT-1; ENGINE_SPEC_B
    S14-R-17 rev 1.164). The two lines net to zero, so the taking run has no journal line
    (S14-R-18) and covers them all the same. Until that item a fresh run did not reach the
    lines — it was made without them, and from item JRN-EMPTY-RUN-1 on refused by name — and
    they were journalised only once the run that left them out was cancelled."""
    with system_session(world) as session:
        revenue = gl_account_values(world.tenant_id, code="5001")
        session.execute(insert(gl_account).values(**revenue))
        activity = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-100.00"), Decimal("100.00")],
            external_id="SF-ORD-10003",
            obligation_key="O1",
        )
        applied_event_id = session.execute(
            select(contract_event.c.id).where(contract_event.c.contract_id == activity.contract_id)
        ).scalar_one()
        hold = contract_hold_values(
            world.tenant_id,
            contract_id=activity.contract_id,
            applied_event_id=applied_event_id,
            hold_type="journal_export",
            reason="Customer dispute on invoice INV-US-10003",
            # Applied before the run is calculated (S14-R-17 reads the open holds at calculation;
            # completeness compares applied_at with the run's created_at).
            applied_at=world.place.clock.now() - timedelta(days=1),
        )
        session.execute(insert(contract_hold).values(**hold))
    hold_id = UUID(str(hold["id"]))

    job_id, run_id = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    with system_session(world) as session:
        run = (
            session.execute(select(journal_run).where(journal_run.c.id == run_id)).mappings().one()
        )
        batches = session.execute(
            select(journal_batch.c.id).where(journal_batch.c.journal_run_id == run_id)
        ).all()
        audits = [
            dict(row)
            for row in session.execute(
                select(audit_event.c.object_id, audit_event.c.after).where(
                    audit_event.c.action == summarise.CALCULATE_ACTION
                )
            ).mappings()
            if str(row["object_id"]) == str(run_id)
        ]
        assert (int(run["line_count"]), batches, len(audits)) == (0, [], 1)
        after = audits[0]["after"]
        assert after["counts"]["held_lines"] == 2 and after["counts"]["batches"] == 0
        # The run's own record of what it excluded — the identity coverage binds to (1317
        # R5-ORDER-1).
        assert set(after["held_subledger_line_ids"]) == {str(line) for line in activity.line_ids}
        held_file_id = UUID(str(after["held_detail_file_id"]))
        _, stream = open_file(
            session, held_file_id, files=world.place.files, keyring=world.place.keyring
        )
        document = json.loads(stream.read())
    assert {UUID(item["subledger_line_id"]) for item in document["held"]} == set(activity.line_ids)
    assert {item["hold_id"] for item in document["held"]} == {str(hold_id)}
    assert {item["txn_currency"] for item in document["held"]} == {"USD"}
    assert (
        hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        == after["held_detail_sha256"]
    )

    held = _completeness(world)
    # One held posting (count 1) whose two lines are both named with the hold.
    assert (held.status, held.count, held.run_count) == (ChecklistStatus.FAILED, 1, 1)
    assert len(held.held_postings) == 1 and len(held.held) == 2
    assert {item.subledger_line_id for item in held.held} == set(activity.line_ids)
    assert {item.hold_id for item in held.held} == {hold_id}
    assert held.uncovered == () and held.differences == ()
    assert held.detail is not None and str(hold_id) in held.detail and "5001" in held.detail

    # 1054 R5 / 1317 R5-ORDER-1: the release happens AFTER the run was calculated — the clock
    # advances and the row order is asserted for the record; coverage itself reads the run's
    # recorded exclusions (above), not these timestamps.
    world.place.clock.advance(timedelta(minutes=5))
    _release_hold(world, hold_id, activity.contract_id)
    with system_session(world) as session:
        run_created_at = session.execute(
            select(journal_run.c.created_at).where(journal_run.c.id == run_id)
        ).scalar_one()
        released_at = session.execute(
            select(contract_hold.c.released_at).where(contract_hold.c.id == hold_id)
        ).scalar_one()
    assert released_at > run_created_at
    released = _completeness(world)
    assert (released.status, released.count) == (ChecklistStatus.FAILED, 1)
    assert released.held == () and len(released.uncovered_postings) == 1
    assert {item.subledger_line_id for item in released.uncovered} == set(activity.line_ids)

    job_id, taking_id = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    with system_session(world) as session:
        taking = (
            session.execute(select(journal_run).where(journal_run.c.id == taking_id))
            .mappings()
            .one()
        )
        took = next(
            dict(row)["after"]
            for row in session.execute(
                select(audit_event.c.object_id, audit_event.c.after).where(
                    audit_event.c.action == summarise.CALCULATE_ACTION
                )
            ).mappings()
            if str(row["object_id"]) == str(taking_id)
        )
    assert int(taking["line_count"]) == 0  # the two lines net to zero (S14-R-18)
    assert set(took["taken_over_subledger_line_ids"]) == {str(line) for line in activity.line_ids}
    again = _completeness(world)
    assert (again.status, again.count, again.run_count) == (ChecklistStatus.PASSED, 0, 2)
    assert again.uncovered == () and again.held == ()


def test_the_held_detail_file_is_read_in_a_savepoint_that_leaves_the_transaction_usable(
    world: CloseWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item JRN-COMPLETENESS-TRANSIENT-1 (dev-guide DG-CMD-09 rev 1.234), the guard against a real
    session. A run's held detail file — what stands in for a CALCULATE event written before it
    named the held lines — is read inside a savepoint: the file the event names answers the two
    held lines; a file id that names no row, and a file whose digest is not the recorded one,
    answer ``None``, "unverifiable". So does a read whose statement the database refuses for a
    reason that is not transient — and the session then runs its next statement in the same
    transaction: before the item the guard caught that error and left the transaction aborted,
    so the statement after the "unverifiable" failed. The rule of what is re-raised instead is
    ``tests/unit/journals/test_held_detail_guard.py``."""
    with system_session(world) as session:
        revenue = gl_account_values(world.tenant_id, code="5001")
        session.execute(insert(gl_account).values(**revenue))
        activity = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-100.00"), Decimal("100.00")],
            external_id="SF-ORD-10007",
            obligation_key="O1",
        )
        applied_event_id = session.execute(
            select(contract_event.c.id).where(contract_event.c.contract_id == activity.contract_id)
        ).scalar_one()
        hold = contract_hold_values(
            world.tenant_id,
            contract_id=activity.contract_id,
            applied_event_id=applied_event_id,
            hold_type="journal_export",
            reason="Customer dispute on invoice INV-US-10007",
            applied_at=world.place.clock.now() - timedelta(days=1),
        )
        session.execute(insert(contract_hold).values(**hold))
    job_id, run_id = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    files, keyring = world.place.files, world.place.keyring
    with system_session(world) as session:
        after = next(
            dict(row)["after"]
            for row in session.execute(
                select(audit_event.c.object_id, audit_event.c.after).where(
                    audit_event.c.action == summarise.CALCULATE_ACTION
                )
            ).mappings()
            if str(row["object_id"]) == str(run_id)
        )
        read = completeness._held_ids_from_file(session, after, files=files, keyring=keyring)
        assert read == set(activity.line_ids)
        nowhere = {**after, "held_detail_file_id": str(UUID(int=7))}
        assert (
            completeness._held_ids_from_file(session, nowhere, files=files, keyring=keyring) is None
        )
        mis_hashed = {**after, "held_detail_sha256": "0" * 64}
        assert (
            completeness._held_ids_from_file(session, mis_hashed, files=files, keyring=keyring)
            is None
        )
        assert session.execute(select(journal_run.c.id)).scalars().all() == [run_id]

        def refused_by_the_database(inner: Any, *_: Any, **__: Any) -> Any:
            inner.execute(text("SELECT 1 / 0"))  # 22012: deterministic, not transient

        monkeypatch.setattr(completeness, "open_file", refused_by_the_database)
        assert (
            completeness._held_ids_from_file(session, after, files=files, keyring=keyring) is None
        )
        # the transaction the guard read in goes on: the savepoint took the refused statement back
        assert session.execute(select(journal_run.c.id)).scalars().all() == [run_id]


def test_release_at_the_run_instant_counts_as_held_when_calculated(world: CloseWorld) -> None:
    """1054 R5 / 1317 R5-ORDER-1 boundary: hold → calculate → release at one frozen instant. The
    run recorded the lines as held (``held_subledger_line_ids``), and coverage reads that record —
    not the equal timestamps — so the lines stay uncovered."""
    with system_session(world) as session:
        revenue = gl_account_values(world.tenant_id, code="5001")
        session.execute(insert(gl_account).values(**revenue))
        activity = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-100.00"), Decimal("100.00")],
            external_id="SF-ORD-10004",
            obligation_key="O1",
        )
        applied_event_id = session.execute(
            select(contract_event.c.id).where(contract_event.c.contract_id == activity.contract_id)
        ).scalar_one()
        hold = contract_hold_values(
            world.tenant_id,
            contract_id=activity.contract_id,
            applied_event_id=applied_event_id,
            hold_type="journal_export",
            reason="Customer dispute on invoice INV-US-10004",
            applied_at=world.place.clock.now() - timedelta(days=1),
        )
        session.execute(insert(contract_hold).values(**hold))
    hold_id = UUID(str(hold["id"]))
    job_id, run_id = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    _release_hold(world, hold_id, activity.contract_id)  # the clock did not advance
    with system_session(world) as session:
        run_created_at = session.execute(
            select(journal_run.c.created_at).where(journal_run.c.id == run_id)
        ).scalar_one()
        released_at = session.execute(
            select(contract_hold.c.released_at).where(contract_hold.c.id == hold_id)
        ).scalar_one()
    assert released_at == run_created_at
    result = _completeness(world)
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    assert {item.subledger_line_id for item in result.uncovered} == set(activity.line_ids)
    assert result.held == () and result.differences == ()


def test_release_before_the_run_at_the_same_instant_is_coverage(world: CloseWorld) -> None:
    """1317 R5-ORDER-1 reverse order: hold → release → calculate, all at one frozen instant. The
    run found no open hold (``open_holds`` reads ``released_at``), journalised the lines and
    recorded the explicit zero-held state — so completeness, reading that record, covers them: a
    timestamp comparison (``released_at >= created_at``) would have vetoed coverage falsely."""
    with system_session(world) as session:
        revenue = gl_account_values(world.tenant_id, code="5001")
        session.execute(insert(gl_account).values(**revenue))
        activity = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-100.00"), Decimal("100.00")],
            external_id="SF-ORD-10006",
            obligation_key="O1",
        )
        applied_event_id = session.execute(
            select(contract_event.c.id).where(contract_event.c.contract_id == activity.contract_id)
        ).scalar_one()
        hold = contract_hold_values(
            world.tenant_id,
            contract_id=activity.contract_id,
            applied_event_id=applied_event_id,
            hold_type="journal_export",
            reason="Customer dispute on invoice INV-US-10006",
            applied_at=world.place.clock.now() - timedelta(days=1),
        )
        session.execute(insert(contract_hold).values(**hold))
    hold_id = UUID(str(hold["id"]))
    _release_hold(world, hold_id, activity.contract_id)  # released first, clock unchanged
    job_id, run_id = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    with system_session(world) as session:
        run_created_at = session.execute(
            select(journal_run.c.created_at).where(journal_run.c.id == run_id)
        ).scalar_one()
        released_at = session.execute(
            select(contract_hold.c.released_at).where(contract_hold.c.id == hold_id)
        ).scalar_one()
        after = next(
            dict(row)["after"]
            for row in session.execute(
                select(audit_event.c.object_id, audit_event.c.after).where(
                    audit_event.c.action == summarise.CALCULATE_ACTION
                )
            ).mappings()
            if str(row["object_id"]) == str(run_id)
        )
    assert released_at == run_created_at
    assert after["counts"]["held_lines"] == 0 and after["held_subledger_line_ids"] == []
    result = _completeness(world)
    assert (result.status, result.count, result.run_count) == (ChecklistStatus.PASSED, 0, 1)


def _keep_legacy_book(world: CloseWorld) -> None:
    """AVM-US keeps the LEGACY book with September open, as ``worlds._keep_legacy_book`` does for
    the CLO-8 journal world: a line posts only into an ``open``, ``closing`` or ``reopened`` period
    state of ITS OWN book (04 DB-07 ``tg_subledger_line__period_guard``, EREV-LED-003), an entity
    keeps a non-primary book through ``PUT /entities/{id}/books/{code}`` (T-REF-03) and the kept
    book's states start ``future`` (T-REF-07)."""
    kept = put(
        world.app,
        f"{ENTITIES}/{world.entity_id}/books/LEGACY",
        world.maya,
        # Kept from September: periods open in order (PRD SM-07 guard; supervisor ruling
        # R-58 (d)), and the first period a book keeps has no previous state.
        {"is_enabled": True, "first_period_key": "FY2026-P09"},
    )
    assert kept.status_code == 200, kept.text
    (september,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US", book="LEGACY")
        if item["period"]["period_key"] == "FY2026-P09"
    ]
    opened = post(
        world.app,
        f"{PERIODS}/{september['id']}/open",
        world.maya,
        {"comment": "LEGACY book of the DELTA witness"},
        if_match=f'"r{september["row_version"]}"',
    )
    assert opened.status_code == 200, opened.text


def test_delta_run_completeness_covers_the_legacy_book(world: CloseWorld) -> None:
    """1054 R1 witness: a ``DELTA`` run journalises the primary book's revenue (−250.00, its
    schedule line) and the LEGACY book's booked revenue (+100.00, no negation — S14-R-23) as one
    −150.00 group. Mode-aware completeness compares the DELTA journal with the activity that run
    covered in both books: PASSED, count 0 (a primary-only comparison would report −150 vs −250).
    A LEGACY line sealed afterwards is uncovered and named with its book."""
    _keep_legacy_book(world)
    with system_session(world) as session:
        revenue = gl_account_values(world.tenant_id, code="5001")
        unbilled = gl_account_values(world.tenant_id, code="1201")
        session.execute(insert(gl_account).values(**revenue))
        session.execute(insert(gl_account).values(**unbilled))
        # Balanced postings (1317 CLO-FIXTURE-SEAL-1): each 5001 amount has its 1201 counterpart,
        # so the DELTA comparison is 5001: −250 + 100 = −150 and 1201: +250 − 100 = +150.
        primary = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-250.00")],
            external_id="SF-ORD-10005",
            obligation_key="O1",
            with_schedule_line=True,
            offset_account=unbilled,
            offset_columns={"account_role": "UNBILLED_RECEIVABLE"},
        )
        legacy = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("100.00")],
            external_id="LEG-0001",
            obligation_key="O1",
            book_code="LEGACY",
            account_role="REVENUE",
            legacy_key="LEG-0001",
            offset_account=unbilled,
            offset_columns={"account_role": "UNBILLED_RECEIVABLE", "legacy_key": "LEG-0001"},
        )
    job_id, _ = requested_journal_run(world, mode="DELTA")
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    covered = _completeness(world)
    assert (covered.status, covered.count, covered.modes, covered.run_count) == (
        ChecklistStatus.PASSED,
        0,
        ("DELTA",),
        1,
    )
    assert covered.differences == () and covered.uncovered == ()
    assert primary.schedule_line_id is not None and legacy.line_ids
    with system_session(world) as session:
        later = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("50.00")],
            external_id="LEG-0002",
            obligation_key="O1",
            book_code="LEGACY",
            account_role="REVENUE",
            legacy_key="LEG-0002",
            offset_account=unbilled,
            offset_columns={"account_role": "UNBILLED_RECEIVABLE", "legacy_key": "LEG-0002"},
        )
    incomplete = _completeness(world)
    assert (incomplete.status, incomplete.count) == (ChecklistStatus.FAILED, 1)
    assert {item.subledger_line_id for item in incomplete.uncovered} == set(later.line_ids)
    (uncovered,) = [item for item in incomplete.uncovered if item.account_code == "5001"]
    assert (uncovered.subledger_line_id, uncovered.book_code) == (
        later.target_line_ids[0],
        "LEGACY",
    )
    assert incomplete.detail is not None and "(LEGACY)" in incomplete.detail
    assert incomplete.differences == ()
