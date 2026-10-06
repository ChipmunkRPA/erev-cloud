"""What stands between a posting nobody approved and the lock of its period: the journal run and
its second person (item RESTRICTED-PERIOD-CHAIN-WITNESS-1, register index 282; PRD BR-CLS-01,
BR-CLS-06, BR-CLS-07, BR-DAT-07, BR-JE-01; 03 REQ-CLS-003, REQ-CLS-009, REQ-CLS-011, REQ-JE-005;
controls CTL-015, CTL-018 over CTL-016, CTL-019 and CTL-021; the supervisor's orders of
2026-10-02 on lane SECFIX-CLO's reading of main ``d6e7d0f8``).

PRD BR-CLS-06 asks a second person for every posting command in a reopened period, and BR-DAT-07
a human review for imports and adapter loads while a period is in soft close. The product asks
one for an import, a manual adjustment, a person's manual event and a journal run; an event sent
by an API client is appended and computed at once (PRD ACT-10), in every period state. Item
CLO-REOPEN-APPROVAL-1 would make such a batch wait; it is not built. The day it is built the
event of each test below waits for a second person: all three turn red, and the module is
restated with the item. These tests are the witness of the control that operates meanwhile, end
to end and through the product's own commands:

- the line such an event posts is locked only behind a journal run: the lock request is refused
  while no run carries the line (``JE_COMPLETE``, naming it), while the run is not approved
  (``APPROVALS_CLEARED``) and while its batch is not acknowledged (``BATCHES_ACKNOWLEDGED``);
- the run is approved by a second person: the user who calculated it and the user who submitted
  it are each refused (BR-JE-01; SM-01), and the request waits until a third user decides it;
- in a period under its ``REOPEN`` record the database marks the line (04 DB-07, T-SL-04
  ``is_post_reopen``), and the difference report of the re-lock comes into being with the
  Controller's decision, not before it.

And one test pins where that control ends today (``test_gap_...``): postings that net to zero
within a journal run leave no journal line, a run without lines is never submitted, and the
period is locked again although nobody approved a journal run. It asserts the delivered state of
a GAP and turns red the day the rule is built.

World. WLD-K-01 ``SF-ORD-10001`` on the record-time clock (a close runs on it). O2 (AVM-IMPL-STD,
16,200.00 allocated, WLD-X-01) is recognised by progress: 40 % is 6,480.00 and the remaining 60 %
9,720.00. API client ``svc-metering`` holds ``event.record`` and dates its events itself, so no
case depends on the day the suite runs. (A recognition hold, which one person applies and
releases without a request, is dated the entity's current date: a test of it would turn with
the calendar, so the lane measured it and did not pin it.) Rosa and Tomas hold Revenue
Accountant and Revenue Reviewer, so each may calculate, submit and try to approve a run; Priya
(Revenue Reviewer) approves it and Marcus (Controller) decides the lock.

Stand-ins, the ones every lock world uses (``support.worlds.period_locked``): the two required
reconciliations are rows reviewed through the SM-09 transitions and the period's close run is a
``SUCCEEDED`` row. Neither is under test; a refusal is read for the three gates of the chain
only.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import engine as approvals_engine
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import approval_request, contract, contract_event, subledger_line
from erev_api.domain.close import gates
from erev_api.domain.journals import commands as journal_commands
from erev_api.domain.journals import ports
from erev_api.enums import GlAdapter, LockKind, PeriodState
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.api_clients import access_approver, issued_client
from support.close_world import close_run_succeeded_for, reviewed_reconciliations_for
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, colleague, enrolled
from support.reference import APPROVALS, PERIODS, approve, assign, get, post, slug
from support.worlds import (
    AVM_US,
    FEBRUARY_2026,
    JANUARY_2026,
    JOURNAL_RUNS,
    K01,
    RUN_ID_HEADER,
    ErpLedger,
    ReportWorld,
    journal_run,
    k01_pellworth,
    on_record_clock,
    period_locked,
    period_reopened,
    posted_journal,
    run_now,
    verified,
)
from support.worlds import period_state as period_shown

EVENTS: Final = "/api/v1/contracts/{contract_id}/events"
LINES: Final = "/api/v1/subledger-lines"
CERTIFICATION: Final = "The period is complete."
# The three gates a line passes on its way into a locked period (04 T-CLS-02; PRD BR-CLS-01).
CHAIN: Final = (gates.JE_COMPLETE, gates.APPROVALS_CLEARED, gates.BATCHES_ACKNOWLEDGED)
UNACKNOWLEDGED: Final = gates.UNACKNOWLEDGED_DETAIL.format(n=1)
PENDING: Final = gates.APPROVALS_DETAIL.format(n=1)
# PRD WLD-X-01: O2 of K-01 is allocated 16,200.00.
O2_FORTY_PERCENT: Final = Decimal("6480.00")
O2_SIXTY_PERCENT: Final = Decimal("9720.00")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, *, through: date
) -> ReportWorld:
    world = k01_pellworth(app, keyring, clock, files, through=through)
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: a journal run is hers to approve
    return on_record_clock(world, clock)  # a close runs on the record-time clock


def _contract_id(world: ReportWorld) -> UUID:
    return UUID(str(world.contracts[K01].contract["id"]))


def _metering_token(world: ReportWorld) -> str:
    """API client ``svc-metering`` (PRD §2.5 integrations) with ``event.record``; its token. The
    client's scopes are an access grant (supervisor ruling R-38 (iii)): Marcus requests it, Ada —
    a second Tenant Admin — approves the grant, and Marcus issues its secret."""
    ada = access_approver(world.app, world.place.clock, world.marcus.member, "ada")
    client = issued_client(
        world.app,
        world.marcus,
        {"name": "svc-metering", "scopes": ["event.record", "contract.read"]},
        approver=ada,
    )
    issued = call(
        world.app,
        "POST",
        "/api/v1/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(client["client_id"], client["client_secret"]),
    )
    assert issued.status_code == 200, issued.text
    return str(issued.json()["access_token"])


def _requests(world: ReportWorld, subject_type: str | None = None) -> int:
    """How many approval requests the workspace holds, of one subject type or of any."""
    counted = select(func.count()).select_from(approval_request)
    if subject_type is not None:
        counted = counted.where(approval_request.c.subject_type == subject_type)
    return int(world.place.scalar(counted))


def _lines(world: ReportWorld, period_key: str) -> dict[str, dict[str, Any]]:
    """API-S-SubledgerLine of K-01 in one period of the ASC606 book, by id."""
    listed = get(
        world.app,
        LINES,
        world.maya,
        {
            "contract": str(_contract_id(world)),
            "period": period_key,
            "book": "ASC606",
            "limit": 200,
        },
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["next_cursor"] is None
    return {str(item["id"]): item for item in body["items"]}


def _stored_flags(world: ReportWorld, line_ids: Any) -> set[bool]:
    """``is_post_reopen`` as the DB-07 guard stored it on the lines."""
    stored = world.place.rows(
        select(subledger_line.c.is_post_reopen).where(
            subledger_line.c.id.in_([UUID(str(line_id)) for line_id in line_ids])
        )
    )
    return {bool(row["is_post_reopen"]) for row in stored}


def _progress_by_the_client(
    world: ReportWorld, token: str, *, period_key: str, day: str, ratio: str
) -> dict[str, dict[str, Any]]:
    """``svc-metering`` reports O2 at ``ratio`` on ``day``: appended and computed by that one
    request, with no approval request of any kind (PRD ACT-10). Returns the lines it posted into
    the period."""
    contract_id = _contract_id(world)
    place = world.place
    before = _lines(world, period_key)
    requests = _requests(world)
    head = place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    sent = call(
        world.app,
        "POST",
        EVENTS.format(contract_id=contract_id),
        json={
            "events": [
                {
                    "event_type": "PROGRESS_RECORDED",
                    "effective_date": day,
                    "payload": {
                        "obligation_key": "O2",
                        "cumulative_progress_ratio": ratio,
                        "measure": "OUTPUT_PERCENT",
                    },
                }
            ]
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"k-{uuid4()}",
            "If-Match": f'"s{int(head)}"',
        },
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["computation"]["status"] == "SUCCEEDED", sent.json()["computation"]
    stored = place.rows(
        select(contract_event)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )[-1]
    assert (str(stored["created_by_kind"]), stored["approval_request_id"], stored["is_manual"]) == (
        "API_CLIENT",
        None,
        False,
    )
    assert _requests(world) == requests  # nothing waits for anybody
    after = _lines(world, period_key)
    return {line_id: line for line_id, line in after.items() if line_id not in before}


def _amounts(lines: dict[str, dict[str, Any]]) -> list[tuple[str, Decimal]]:
    """(account role, signed transaction amount) of the lines, debit positive, sorted."""
    return sorted(
        (str(line["account_role"]), Decimal(str(line["amount_txn"]["amount"])))
        for line in lines.values()
    )


def _period(
    world: ReportWorld, period_key: str, command: str, body: dict[str, Any]
) -> HttpResponse:
    shown = period_shown(world, AVM_US, period_key)
    return post(
        world.app,
        f"{PERIODS}/{shown['id']}/{command}",
        world.maya,
        body,
        if_match=f'"r{shown["row_version"]}"',
    )


def _lock_request(world: ReportWorld, period_key: str) -> HttpResponse:
    return _period(world, period_key, "request-lock", {"certification_comment": CERTIFICATION})


def _chain_gates(refused: HttpResponse) -> dict[str, str]:
    """The entries of an ERR-14 refusal for the three gates of the chain: gate code → detail.
    A lock request that is not refused fails here."""
    assert refused.status_code == 409, f"the lock was requested: {refused.text}"
    assert slug(refused) == "close-gates-failed", refused.text
    return {
        str(entry["rule_id"]): str(entry["message"])
        for entry in refused.json()["errors"]
        if entry["rule_id"] in CHAIN
    }


def _both_roles(world: ReportWorld, clock: FrozenClock, name: str) -> Actor:
    """A user holding Revenue Accountant and Revenue Reviewer: ``journal.run`` and
    ``journal.approve``, so that a refusal is the rule's and not a missing permission's."""
    someone = colleague(world.tenant_id, name)
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(someone, code)
    return enrolled(world.app, clock, someone)


def _run(world: ReportWorld, run_id: str) -> dict[str, Any]:
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _reconciliations_reviewed_again(
    world: ReportWorld, clock: FrozenClock, period_key: str
) -> None:
    """The stand-in for "generated again and reviewed" (module docstring): not under test."""
    shown = period_shown(world, AVM_US, period_key)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(shown["entity"]["id"])),
            period_id=UUID(str(shown["period"]["id"])),
            now=clock.now(),
        )


def _exported_and_acknowledged(world: ReportWorld, run_id: str) -> None:
    """Maya exports the approved run and the ERP ledger of ``worlds.ErpLedger`` acknowledges it
    (PRD SM-08), as ``support.worlds.posted_journal`` does."""
    slot = GlAdapter.CSV
    kept = ports.GL_ADAPTERS.get(slot)
    ports.GL_ADAPTERS[slot] = ErpLedger().factory
    try:
        exported = post(
            world.app, f"{JOURNAL_RUNS}/{run_id}/export", world.maya, {"adapter": slot.value}
        )
        assert exported.status_code == 202, exported.text
        finished = run_now(world, UUID(str(exported.json()["id"])))
    finally:
        if kept is None:
            ports.GL_ADAPTERS.pop(slot, None)
        else:
            ports.GL_ADAPTERS[slot] = kept
    assert finished["state"] == "SUCCEEDED", finished
    assert _run(world, run_id)["state"] == "acknowledged"


def _locked_only_behind_an_approved_run(
    world: ReportWorld,
    clock: FrozenClock,
    period_key: str,
    posted: dict[str, dict[str, Any]],
) -> tuple[ReportWorld, str]:
    """The chain, link by link, for the lines ``posted`` into a period in soft close. Every lock
    request before the last link is refused; returns the world with the verified sessions and
    the id of the journal run that carries the lines, acknowledged."""
    app = world.app
    journal_requests = _requests(world, "JOURNAL_RUN")

    # 1. No journal run carries the lines: the completeness gate names each of them. It cannot
    #    be waived (04 §16.8), so nothing but a run moves it.
    refused = _chain_gates(_lock_request(world, period_key))
    assert set(refused) == {gates.JE_COMPLETE}, refused
    for line_id in posted:
        assert f"uncovered line {line_id}" in refused[gates.JE_COMPLETE], refused

    # 2. Rosa calculates the run that carries them. A draft run does not open the lock: its
    #    batch is not acknowledged.
    rosa = _both_roles(world, clock, "rosa")
    tomas = _both_roles(world, clock, "tomas")
    started = post(app, JOURNAL_RUNS, rosa, {"entity_code": AVM_US, "period_key": period_key})
    assert started.status_code == 202, started.text
    assert run_now(world, UUID(str(started.json()["id"])))["state"] == "SUCCEEDED"
    run_id = str(started.headers[RUN_ID_HEADER])
    run = _run(world, run_id)
    assert (run["state"], run["totals"]["line_count"]) == ("draft", len(posted)), run
    assert [(batch["state"], batch["line_count"]) for batch in run["batches"]] == [
        ("draft", len(posted))
    ]
    assert _chain_gates(_lock_request(world, period_key)) == {
        gates.BATCHES_ACKNOWLEDGED: UNACKNOWLEDGED
    }

    # 3. Tomas submits it. A pending request does not open the lock either.
    submitted = post(app, f"{JOURNAL_RUNS}/{run_id}/submit", tomas, {})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    waiting = {gates.APPROVALS_CLEARED: PENDING, gates.BATCHES_ACKNOWLEDGED: UNACKNOWLEDGED}
    assert _chain_gates(_lock_request(world, period_key)) == waiting

    # 4. The approval is a second person's. Both hold ``journal.approve``: the user who ran the
    #    calculation is refused by BR-JE-01, the user who submitted the run by SM-01. Nothing is
    #    decided and the lock stays shut.
    by_runner = approve(app, request_id, rosa)
    assert by_runner.status_code == 403, f"the runner approved the run: {by_runner.text}"
    assert slug(by_runner) == "self-approval", by_runner.text
    assert by_runner.json()["detail"] == journal_commands.RUNNER_DETAIL
    by_submitter = approve(app, request_id, tomas)
    assert by_submitter.status_code == 403, f"the submitter approved the run: {by_submitter.text}"
    assert slug(by_submitter) == "self-approval", by_submitter.text
    assert by_submitter.json()["detail"] == approvals_engine.SELF_APPROVAL_DETAIL
    pending = get(app, f"{APPROVALS}/{request_id}", tomas).json()
    assert (pending["status"], [step["decisions"] for step in pending["steps"]]) == (
        "PENDING",
        [[]],
    )
    assert _run(world, run_id)["state"] == "draft"
    assert _chain_gates(_lock_request(world, period_key)) == waiting

    # 5. Priya, who neither ran nor submitted it, approves. The request is the only one written
    #    for the lines, and she is its one decider. An approved run is not yet in the ledger: the
    #    lock still waits for the acknowledgement.
    world = verified(world, clock, "priya")
    decided = approve(app, request_id, world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    (decision,) = decided.json()["steps"][0]["decisions"]
    assert decision["approver"]["id"] == str(world.priya.member.user_id)
    assert _requests(world, "JOURNAL_RUN") == journal_requests + 1
    assert _run(world, run_id)["state"] == "approved"
    assert _chain_gates(_lock_request(world, period_key)) == {
        gates.BATCHES_ACKNOWLEDGED: UNACKNOWLEDGED
    }

    # 6. Exported and acknowledged: the chain is passed.
    _exported_and_acknowledged(world, run_id)
    return world, run_id


@pytest.mark.slow
@pytest.mark.control("CTL-015")
@pytest.mark.control("CTL-018")
def test_ctl_015_a_line_nobody_approved_is_locked_only_behind_an_approved_journal_run(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A period in soft close (PRD BR-DAT-07; REQ-CLS-003, REQ-CLS-009). WLD-K-01 through 30 Jan
    2026; January of AVM-US is soft-closed, its journal run is acknowledged, its reconciliations
    are reviewed and its close run has succeeded: every gate but the certification has passed.
    Then ``svc-metering`` reports O2 at 40 % on 31 Jan 2026. Nobody is asked: 6,480.00 of revenue
    is posted into the period in close. It is not a post-reopen line — the period was never
    locked — and nothing marks it as late. What stands between it and the lock is the chain."""
    world = _world(app, keyring, clock, files, through=date(2026, 1, 30))
    started = _period(world, JANUARY_2026, "start-close", {"comment": "January close"})
    assert started.status_code == 200, started.text
    first, world = posted_journal(world, clock, entity_code=AVM_US, period_key=JANUARY_2026)
    shown = period_shown(world, AVM_US, JANUARY_2026)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        for stand_in in (reviewed_reconciliations_for, close_run_succeeded_for):
            stand_in(
                session,
                tenant_id=world.tenant_id,
                entity_id=UUID(str(shown["entity"]["id"])),
                period_id=UUID(str(shown["period"]["id"])),
                now=clock.now(),
            )
    # The control of the test: before the event nothing but the certification holds the lock.
    checklist = get(app, f"{PERIODS}/{shown['id']}/checklist", world.maya)
    assert checklist.status_code == 200, checklist.text
    assert {
        item["gate_check_code"]
        for item in checklist.json()["items"]
        if item["is_blocking"] and item["status"] != "PASSED"
    } == {gates.CONTROLLER_CERTIFIED}

    posted = _progress_by_the_client(
        world, _metering_token(world), period_key=JANUARY_2026, day="2026-01-31", ratio="0.40"
    )
    assert _amounts(posted) == [
        ("CONTRACT_LIABILITY", O2_FORTY_PERCENT),
        ("REVENUE", -O2_FORTY_PERCENT),
    ]
    assert {line["is_post_reopen"] for line in posted.values()} == {False}
    assert _stored_flags(world, posted) == {False}
    assert period_shown(world, AVM_US, JANUARY_2026)["state"] == PeriodState.CLOSING.value

    world, run_id = _locked_only_behind_an_approved_run(world, clock, JANUARY_2026, posted)

    assert (first["run_no"], _run(world, run_id)["run_no"]) == ("JR-000001", "JR-000002")
    _reconciliations_reviewed_again(world, clock, JANUARY_2026)
    requested = _lock_request(world, JANUARY_2026)
    assert requested.status_code == 200, requested.text
    world = verified(world, clock, "marcus")
    locked = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (locked.status_code, locked.json()["status"]) == (200, "APPROVED"), locked.text
    assert period_shown(world, AVM_US, JANUARY_2026)["state"] == PeriodState.CLOSED.value


@pytest.mark.slow
@pytest.mark.control("CTL-018")
def test_ctl_018_a_post_reopen_line_nobody_approved_is_relocked_only_behind_an_approved_run(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A reopened period (PRD BR-CLS-06, BR-CLS-07; REQ-CLS-011). WLD-K-01 through 26 Feb 2026;
    February of AVM-US is locked through the product and reopened by two approvals. Then
    ``svc-metering`` reports O2 complete on 27 Feb 2026. Nobody is asked: 9,720.00 of revenue is
    posted into the reopened period. The database marks both lines as post-reopen lines; the
    period is soft-closed again, and the chain stands between the lines and the re-lock.

    The re-lock itself is one Controller's decision, taken without the difference report: the
    request shows no preview and no attachment, no lock record names a report before the
    decision, and the record the decision writes names one."""
    world = _world(app, keyring, clock, files, through=date(2026, 2, 26))
    first, world = period_locked(world, clock, entity_code=AVM_US, period_key=FEBRUARY_2026)
    world = period_reopened(
        world,
        clock,
        entity_code=AVM_US,
        period_key=FEBRUARY_2026,
        comment="Implementation completed on 27 Feb 2026 was not recorded.",
    )
    shown = period_shown(world, AVM_US, FEBRUARY_2026)
    assert (shown["state"], shown["current_lock"]["kind"]) == (
        PeriodState.REOPENED.value,
        LockKind.REOPEN.value,
    )

    posted = _progress_by_the_client(
        world, _metering_token(world), period_key=FEBRUARY_2026, day="2026-02-27", ratio="1"
    )
    assert _amounts(posted) == [
        ("CONTRACT_LIABILITY", O2_SIXTY_PERCENT),
        ("REVENUE", -O2_SIXTY_PERCENT),
    ]
    # 04 DB-07: the guard, not the command, states the flag — and the read shows it.
    assert _stored_flags(world, posted) == {True}
    assert {line["is_post_reopen"] for line in posted.values()} == {True}
    restarted = _period(world, FEBRUARY_2026, "start-close", {"comment": "February close, again"})
    assert restarted.status_code == 200, restarted.text

    world, run_id = _locked_only_behind_an_approved_run(world, clock, FEBRUARY_2026, posted)

    assert (first["run_no"], _run(world, run_id)["run_no"]) == ("JR-000001", "JR-000002")
    _reconciliations_reviewed_again(world, clock, FEBRUARY_2026)
    requested = _lock_request(world, FEBRUARY_2026)
    assert requested.status_code == 200, requested.text
    lock_request_id = str(requested.json()["approval_request_id"])
    # What the Controller decides on: a summary, no preview, no file — and no difference yet.
    world = verified(world, clock, "marcus")
    panel = get(app, f"{APPROVALS}/{lock_request_id}", world.marcus)
    assert panel.status_code == 200, panel.text
    assert (panel.json()["impact_preview"], panel.json()["attachments"]) == (None, [])
    locks = f"{PERIODS}/{shown['id']}/locks"
    before = get(app, locks, world.marcus)
    assert before.status_code == 200, before.text
    assert sorted((row["kind"], row["diff_report_file_id"]) for row in before.json()["items"]) == [
        (LockKind.LOCK.value, None),
        (LockKind.REOPEN.value, None),
    ]
    locked = approve(app, lock_request_id, world.marcus)
    assert (locked.status_code, locked.json()["status"]) == (200, "APPROVED"), locked.text
    after = period_shown(world, AVM_US, FEBRUARY_2026)
    assert (after["state"], after["current_lock"]["kind"]) == (
        PeriodState.CLOSED.value,
        LockKind.LOCK.value,
    )
    records = {str(row["id"]): row for row in get(app, locks, world.marcus).json()["items"]}
    relock = records[str(after["current_lock"]["id"])]
    assert relock["approval_request_id"] == lock_request_id
    assert relock["diff_report_file_id"] is not None  # BR-CLS-07: written by the decision
    assert _stored_flags(world, posted) == {True}


@pytest.mark.slow
def test_gap_postings_that_net_to_zero_are_relocked_without_any_journal_approval(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A GAP of CTL-018, pinned as the delivered state; item CLO-REOPEN-APPROVAL-1 closes it, and
    this test turns red when it does (PRD BR-CLS-06; REQ-CLS-011 "Posting in a reopened period
    without a second approval is blocked"; ENGINE_SPEC_B S14-R-18; 04 §16.7 ``submit`` rev
    1.248).

    WLD-K-01 through 26 Feb 2026; February of AVM-US is locked and reopened through the product.
    ``svc-metering`` reports O2 complete on 27 Feb 2026 and back at 40 % on 28 Feb 2026: 9,720.00
    of revenue into the reopened period and out of it again, four lines, nobody asked. The
    completeness gate names all four, so a journal run is calculated over them — and holds no
    journal line, because the two postings net to zero in their accounts, dimensions and
    currency. A run without lines is never submitted ("there is nothing to approve"), has no
    batch to acknowledge and leaves no request pending: every gate of the chain passes and the
    Controller locks the period again. No ``JOURNAL_RUN`` request was written since the reopen.

    What remains of the four lines is the flag the database put on each. The journal run shows
    none of them, and the Controller who re-locks is shown neither them nor a difference."""
    world = _world(app, keyring, clock, files, through=date(2026, 2, 26))
    first, world = period_locked(world, clock, entity_code=AVM_US, period_key=FEBRUARY_2026)
    world = period_reopened(
        world,
        clock,
        entity_code=AVM_US,
        period_key=FEBRUARY_2026,
        comment="Implementation completed on 27 Feb 2026 was not recorded.",
    )
    journal_requests = _requests(world, "JOURNAL_RUN")
    token = _metering_token(world)
    forth = _progress_by_the_client(
        world, token, period_key=FEBRUARY_2026, day="2026-02-27", ratio="1"
    )
    back = _progress_by_the_client(
        world, token, period_key=FEBRUARY_2026, day="2026-02-28", ratio="0.40"
    )
    assert _amounts(forth) == [
        ("CONTRACT_LIABILITY", O2_SIXTY_PERCENT),
        ("REVENUE", -O2_SIXTY_PERCENT),
    ]
    assert _amounts(back) == [
        ("CONTRACT_LIABILITY", -O2_SIXTY_PERCENT),
        ("REVENUE", O2_SIXTY_PERCENT),
    ]
    posted = {**forth, **back}
    assert len(posted) == 4 and _stored_flags(world, posted) == {True}
    restarted = _period(world, FEBRUARY_2026, "start-close", {"comment": "February close, again"})
    assert restarted.status_code == 200, restarted.text

    # The completeness gate holds: all four lines are named until a run carries them.
    refused = _chain_gates(_lock_request(world, FEBRUARY_2026))
    assert set(refused) == {gates.JE_COMPLETE}, refused
    for line_id in posted:
        assert f"uncovered line {line_id}" in refused[gates.JE_COMPLETE], refused

    # The run that carries them holds no journal line and cannot be submitted.
    run = journal_run(world, period_key=FEBRUARY_2026)
    assert (first["run_no"], run["run_no"], run["state"]) == ("JR-000001", "JR-000002", "draft")
    assert (run["totals"]["line_count"], run["batches"]) == (0, [])
    submitted = post(app, f"{JOURNAL_RUNS}/{run['id']}/submit", world.maya, {})
    assert (submitted.status_code, slug(submitted)) == (409, "invalid-transition"), submitted.text
    assert submitted.json()["detail"] == journal_commands.NO_LINES.format(run_no=run["run_no"])

    # With that, no gate of the chain holds the lock any more.
    assert _chain_gates(_lock_request(world, FEBRUARY_2026)) == {}
    _reconciliations_reviewed_again(world, clock, FEBRUARY_2026)
    requested = _lock_request(world, FEBRUARY_2026)
    assert requested.status_code == 200, requested.text
    lock_request_id = str(requested.json()["approval_request_id"])
    world = verified(world, clock, "marcus")
    panel = get(app, f"{APPROVALS}/{lock_request_id}", world.marcus)
    assert panel.status_code == 200, panel.text
    assert (panel.json()["impact_preview"], panel.json()["attachments"]) == (None, [])
    locked = approve(app, lock_request_id, world.marcus)
    assert (locked.status_code, locked.json()["status"]) == (200, "APPROVED"), locked.text
    after = period_shown(world, AVM_US, FEBRUARY_2026)
    assert (after["state"], after["current_lock"]["kind"]) == (
        PeriodState.CLOSED.value,
        LockKind.LOCK.value,
    )

    # THE GAP: the period is locked again and nobody approved a journal run for the four lines.
    assert _requests(world, "JOURNAL_RUN") == journal_requests
    final = _run(world, str(run["id"]))
    assert (final["state"], final["approval_request_id"]) == ("draft", None)
    # What a reviewer can still find them by.
    assert _stored_flags(world, posted) == {True}
