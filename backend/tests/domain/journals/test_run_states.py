"""CLO-11 journal run approval and states (04 §3.4 E-34, §16.7 "Journal commands", §14.1 DB-16;
PRD SM-08, §2.5 routing row ``JOURNAL_RUN``, BR-JE-01; REQ-JE-004; BUILD_SPEC CLO-11), and the
CLO-14 rule that only the latest run of a key is cancelled (ruling R-52 (b)).

World: ``support.worlds.journal_world`` with the CHK-022 intents posted (L6-3-Q-1). Rosa and Tomas
hold Revenue Accountant and Revenue Reviewer, so each can run, submit and try to approve; Priya
(Revenue Reviewer) approves. The transition table runs over probe rows
(``support.rows.insert_journal_rows``).

[J] L6-3-Q-8 (R-RC-1): ``test_reopened_period_needs_human_approval`` (BR-CLS-06) moves post-rc with
CLO-7, because no command reopens a period before CLO-7.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import transitions
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import journal_batch, journal_run
from erev_api.domain.journals import commands
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.journals import JournalRunCancelIn
from fastapi import FastAPI
from sqlalchemy import exc, select, text, update
from support.db import TestDatabase
from support.factories import run_import_job, tenant_factory, tenant_id_of
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import Actor, colleague, enrolled
from support.reference import (
    APPROVALS,
    approve,
    assert_approval_hidden,
    assign,
    fields,
    get,
    post,
    slug,
)
from support.rows import insert_journal_rows
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    JANUARY,
    JOURNAL_RUNS,
    RUN_ID_HEADER,
    JournalWorld,
    journal_world,
    post_chk_022,
    post_lines,
)

E34: Final = ("draft", "approved", "exported", "acknowledged", "failed", "cancelled")
ALLOWED: Final = frozenset(
    {
        ("draft", "approved"),
        ("approved", "exported"),
        ("exported", "acknowledged"),
        ("exported", "failed"),
        ("failed", "exported"),
        ("draft", "cancelled"),
        ("approved", "cancelled"),
        # 04 E-34 rev 1.159 (item JRN-FAILED-CANCEL-1; ruling R-112 (c); Alembic revision 0108):
        # the cancel of a failed run after its ledger was asked
        ("failed", "cancelled"),
    }
)
# The allowed moves from draft that reach each state.
PATHS: Final = {
    "draft": (),
    "approved": ("approved",),
    "exported": ("approved", "exported"),
    "acknowledged": ("approved", "exported", "acknowledged"),
    "failed": ("approved", "exported", "failed"),
    "cancelled": ("cancelled",),
}
PAIRS: Final = [(source, target) for source in E34 for target in E34 if source != target]
REQUEST_XMIN: Final = text("SELECT xmin::text FROM erev.approval_request WHERE id = :id")
RUN_XMIN: Final = text("SELECT xmin::text FROM erev.journal_run WHERE id = :id")
BATCH_XMIN: Final = text("SELECT xmin::text FROM erev.journal_batch WHERE journal_run_id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _preparer(world: JournalWorld, clock: FrozenClock, name: str) -> Actor:
    """A user holding Revenue Accountant and Revenue Reviewer: ``journal.run`` and
    ``journal.approve``."""
    someone = colleague(world.legacy.tenant_id, name)
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(someone, code)
    return enrolled(world.app, clock, someone)


def _calculated(world: JournalWorld, actor: Actor, entity: str) -> str:
    """``POST /journal-runs`` for January 2023 as ``actor``, then the job as the worker runs it."""
    created = post(world.app, JOURNAL_RUNS, actor, {"entity_code": entity, "period_key": JANUARY})
    assert created.status_code == 202, created.text
    run_import_job(world.legacy.imports, UUID(str(created.json()["id"])))
    return str(created.headers[RUN_ID_HEADER])


def _submitted(world: JournalWorld, actor: Actor, run_id: str) -> str:
    submitted = post(world.app, f"{JOURNAL_RUNS}/{run_id}/submit", actor, {})
    assert submitted.status_code == 200, submitted.text
    return str(submitted.json()["approval_request_id"])


def _cancelled(world: JournalWorld, actor: Actor, run_id: str) -> dict[str, Any]:
    cancelled = post(
        world.app,
        f"{JOURNAL_RUNS}/{run_id}/cancel",
        actor,
        {"reason": "Recalculate after the account mapping fix."},
    )
    assert cancelled.status_code == 200, cancelled.text
    body: dict[str, Any] = cancelled.json()
    return body


def _run(world: JournalWorld, run_id: str) -> dict[str, Any]:
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    body: dict[str, Any] = shown.json()
    return body


@pytest.mark.slow
def test_submit_and_approve(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    priya = world.legacy.priya
    rosa = _preparer(world, clock, "rosa")
    run_id = _calculated(world, rosa, ENTITY_1)

    submitted = post(
        app, f"{JOURNAL_RUNS}/{run_id}/submit", rosa, {"comment": "January 2023 journals"}
    )
    assert submitted.status_code == 200, submitted.text
    shown = submitted.json()
    assert shown["state"] == "draft"
    assert submitted.headers["ETag"] == f'"r{shown["row_version"]}"'
    request_id = str(shown["approval_request_id"])
    request = get(app, f"{APPROVALS}/{request_id}", priya)
    assert request.status_code == 200, request.text
    detail = request.json()
    assert (detail["subject"]["type"], detail["subject"]["id"], detail["status"]) == (
        "JOURNAL_RUN",
        run_id,
        "PENDING",
    )
    assert [(step["required_permission"], step["min_approvers"]) for step in detail["steps"]] == [
        ("journal.approve", 1)
    ]
    assert detail["subject"]["href"] == f"/journals/runs/{run_id}"

    # The submitter's own decision is refused and changes nothing (SM-01).
    refused = approve(app, request_id, rosa)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert _run(world, run_id)["state"] == "draft"

    approved = approve(app, request_id, priya)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    run = _run(world, run_id)
    assert (run["state"], run["approval_request_id"]) == ("approved", request_id)
    assert _instant(run["approved_at"]) == clock.now()
    assert [batch["state"] for batch in run["batches"]] == ["approved"]
    # One transaction (DB-16): the decided request, the run and its batch share one transaction id.
    context = DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        transaction_ids = [
            session.execute(query, {"id": UUID(value)}).scalar_one()
            for query, value in (
                (REQUEST_XMIN, request_id),
                (RUN_XMIN, run_id),
                (BATCH_XMIN, run_id),
            )
        ]
    assert len(set(transaction_ids)) == 1, transaction_ids

    # BR-JE-01: the user who ran the calculation cannot approve a run another user submitted.
    tomas = _preparer(world, clock, "tomas")
    second = _calculated(world, rosa, ENTITY_2)
    second_request = _submitted(world, tomas, second)
    by_runner = approve(app, second_request, rosa)
    assert (by_runner.status_code, slug(by_runner)) == (403, "self-approval"), by_runner.text
    assert by_runner.json()["detail"] == commands.RUNNER_DETAIL
    assert _run(world, second)["state"] == "draft"
    assert approve(app, second_request, priya).status_code == 200
    assert _run(world, second)["state"] == "approved"


def _scoped(world: JournalWorld, clock: FrozenClock, name: str, *grants: tuple[str, UUID]) -> Actor:
    """An enrolled member holding each (role code, entity) of ``grants`` and nothing else."""
    someone = colleague(world.legacy.tenant_id, name)
    for role_code, entity_id in grants:
        assign(someone, role_code, entity_ids=[entity_id])
    return enrolled(world.app, clock, someone)


@pytest.mark.slow
def test_journal_run_request_is_scoped_to_the_runs_entity(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Security review SC-5 (supervisor ruling R-25; 04 §16.10 rev 1.104 "Entity scope of a
    request"; REQ-PLT-012): the ``JOURNAL_RUN`` request names the run's entity, so
    ``journal.approve`` held for Mock Entity 2 neither reads nor decides the run of Mock Entity 1 —
    with no role on entity 1 (Ron) or with a read-only role on it (Rex, who approved the run
    before the fix). A Revenue Reviewer of entity 1 decides it."""
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    e1, e2 = world.entities[ENTITY_1], world.entities[ENTITY_2]
    rosa = _preparer(world, clock, "rosa")
    run_id = _calculated(world, rosa, ENTITY_1)
    request_id = _submitted(world, rosa, run_id)
    shown = get(app, f"{APPROVALS}/{request_id}", rosa)
    assert shown.status_code == 200, shown.text
    assert shown.json()["entity"]["id"] == str(e1)

    ron = _scoped(world, clock, "ron", ("revenue_reviewer", e2))
    rex = _scoped(world, clock, "rex", ("revenue_reviewer", e2), ("viewer", e1))
    assert_approval_hidden(app, request_id, ron, reader=rosa)
    assert_approval_hidden(app, request_id, rex, reader=rosa)
    run = _run(world, run_id)
    assert (run["state"], run["approved_at"]) == ("draft", None)

    # Positive control: journal.approve for entity 1 alone is enough.
    pia = _scoped(world, clock, "pia", ("revenue_reviewer", e1))
    detail = get(app, f"{APPROVALS}/{request_id}", pia)
    assert detail.status_code == 200 and detail.json()["can_decide"] is True, detail.text
    approved = approve(app, request_id, pia)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert _run(world, run_id)["state"] == "approved"


def _delegated(world: JournalWorld, clock: FrozenClock, delegator: Actor, delegate: Actor) -> None:
    """``delegator`` delegates ``journal.approve`` to ``delegate`` from now on (BR-PLT-07)."""
    now = clock.now()
    created = post(
        world.app,
        "/api/v1/approval-delegations",
        delegator,
        {
            "delegate_membership_id": str(delegate.member.membership_id),
            "permissions": ["journal.approve"],
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "reason": "Out of office during the close",
        },
    )
    assert created.status_code == 201, created.text


@pytest.mark.slow
def test_runner_cannot_approve_through_a_delegate(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """BR-JE-01 through delegation (supervisor ruling R-25; PRD rev 1.33; REQ-PLT-011 "across UI,
    API, delegation and role switching"): Rosa runs the calculation and Tomas submits the run.
    Rosa delegates ``journal.approve`` to Dora, who holds no approval permission of her own: Dora's
    decision would be taken on the runner's behalf and is refused 403 ``self-approval`` with the
    runner's copy; the run stays ``draft`` and no decision is recorded. Dan, the delegate of
    Priya — who neither ran nor submitted the run — decides it on her behalf."""
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    rosa = _preparer(world, clock, "rosa")
    tomas = _preparer(world, clock, "tomas")
    priya = _preparer(world, clock, "priya")
    dora_member = colleague(world.legacy.tenant_id, "dora")
    assign(dora_member, "viewer")
    dora = enrolled(app, clock, dora_member)
    run_id = _calculated(world, rosa, ENTITY_1)
    request_id = _submitted(world, tomas, run_id)

    _delegated(world, clock, rosa, dora)
    detail = get(app, f"{APPROVALS}/{request_id}", dora)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is False
    on_behalf = approve(app, request_id, dora)
    assert (on_behalf.status_code, slug(on_behalf)) == (403, "self-approval"), on_behalf.text
    assert on_behalf.json()["detail"] == commands.RUNNER_DETAIL
    in_person = approve(app, request_id, rosa)
    assert (in_person.status_code, slug(in_person)) == (403, "self-approval"), in_person.text
    assert in_person.json()["detail"] == commands.RUNNER_DETAIL
    assert _run(world, run_id)["state"] == "draft"
    pending = get(app, f"{APPROVALS}/{request_id}", tomas).json()
    assert pending["status"] == "PENDING"
    assert [step["decisions"] for step in pending["steps"]] == [[]]

    # Positive control: Priya neither ran nor submitted the run; her delegate decides for her.
    dan_member = colleague(world.legacy.tenant_id, "dan")
    assign(dan_member, "viewer")
    dan = enrolled(app, clock, dan_member)
    _delegated(world, clock, priya, dan)
    allowed = get(app, f"{APPROVALS}/{request_id}", dan)
    assert allowed.status_code == 200 and allowed.json()["can_decide"] is True, allowed.text
    approved = approve(app, request_id, dan)
    assert approved.status_code == 200, approved.text
    (decision,) = approved.json()["steps"][0]["decisions"]
    assert decision["approver"]["id"] == str(dan.member.user_id)
    assert decision["on_behalf_of"]["id"] == str(priya.member.user_id)
    assert _run(world, run_id)["state"] == "approved"


@pytest.mark.slow
def test_cancel_rules(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    maya, priya = world.legacy.maya, world.legacy.priya

    draft = _calculated(world, maya, ENTITY_1)
    unreasoned = post(app, f"{JOURNAL_RUNS}/{draft}/cancel", maya, {})
    assert (unreasoned.status_code, slug(unreasoned)) == (422, "validation-failed"), unreasoned.text
    assert [field for field, _ in fields(unreasoned)] == ["reason"]
    assert _run(world, draft)["state"] == "draft"
    cancelled = _cancelled(world, maya, draft)
    assert cancelled["state"] == "cancelled"
    assert _instant(cancelled["cancelled_at"]) == clock.now()
    assert [batch["state"] for batch in cancelled["batches"]] == ["cancelled"]

    # Cancelling a submitted run voids its pending request (PRD SM-08).
    pending = _calculated(world, maya, ENTITY_1)
    request_id = _submitted(world, maya, pending)
    assert _cancelled(world, maya, pending)["state"] == "cancelled"
    voided = get(app, f"{APPROVALS}/{request_id}", priya).json()
    assert (voided["status"], voided["void_reason"]) == ("VOIDED", "SUBJECT_VOIDED")

    approved = _calculated(world, maya, ENTITY_1)
    assert approve(app, _submitted(world, maya, approved), priya).status_code == 200
    shown = _cancelled(world, maya, approved)
    assert (shown["state"], [batch["state"] for batch in shown["batches"]]) == (
        "cancelled",
        ["cancelled"],
    )
    assert _instant(shown["cancelled_at"]) == clock.now()
    assert shown["approved_at"] is not None

    exported = _calculated(world, maya, ENTITY_1)
    assert approve(app, _submitted(world, maya, exported), priya).status_code == 200
    context = DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")
    system = {"updated_by": None, "updated_by_kind": "SYSTEM"}
    with tenant_session(context) as session:
        batch_ids = session.scalars(
            select(journal_batch.c.id).where(journal_batch.c.journal_run_id == UUID(exported))
        ).all()
        for batch_id in batch_ids:
            transitions.apply(
                session,
                "journal_batch",
                batch_id,
                to_status="exported",
                expected_status="approved",
                set_values={"exported_at": clock.now(), **system},
            )
        transitions.apply(
            session,
            "journal_run",
            UUID(exported),
            to_status="exported",
            expected_status="approved",
            set_values={"exported_at": clock.now(), **system},
        )
    refused = post(app, f"{JOURNAL_RUNS}/{exported}/cancel", maya, {"reason": "Too late."})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert _run(world, exported)["state"] == "exported"


@pytest.mark.slow
def test_r52b_only_the_latest_run_of_a_key_is_cancelled(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Ruling R-52 (b): a new run starts at the highest sealed position the non-cancelled runs of
    its key cover (DB-16), so an earlier run cancelled while a later one stands would leave its
    seals covered by no run and open to none. The earlier run is refused 409
    ``invalid-transition`` naming the later one; cancelling the later run first admits it, and the
    next run then covers the key from its first seal. Before the rule the first cancel answered
    200 and the January activity of CHK-022 could never be journalised again."""
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    maya = world.legacy.maya
    first = _calculated(world, maya, ENTITY_1)
    post_lines(
        world,
        key="r52b-later-activity",
        contract_key="Contract 1",
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "10.00", "POB #1"),
                    ("REVENUE", "5001", "-10.00", "POB #1"),
                ],
            )
        ],
    )
    second = _calculated(world, maya, ENTITY_1)
    earlier, later = _run(world, first), _run(world, second)
    assert earlier["coverage"]["from_chain_seq"] == 0
    assert later["coverage"]["from_chain_seq"] == earlier["coverage"]["to_chain_seq"]
    assert later["coverage"]["to_chain_seq"] > later["coverage"]["from_chain_seq"]

    refused = post(app, f"{JOURNAL_RUNS}/{first}/cancel", maya, {"reason": "Recalculate."})
    assert refused.status_code == 409, refused.text  # before the rule: 200
    assert slug(refused) == "invalid-transition"
    assert refused.json()["detail"] == (
        f"Journal run {later['run_no']} was calculated after this run for the same entity, book "
        f"and period. Cancel {later['run_no']} first."
    )
    assert fields(refused) == [("state", "E-34")]
    assert (_run(world, first)["state"], _run(world, second)["state"]) == ("draft", "draft")

    # positive control: the latest run first, then the earlier one
    assert _cancelled(world, maya, second)["state"] == "cancelled"
    assert _cancelled(world, maya, first)["state"] == "cancelled"
    third = _run(world, _calculated(world, maya, ENTITY_1))
    assert (third["coverage"]["from_chain_seq"], third["coverage"]["to_chain_seq"]) == (
        0,
        later["coverage"]["to_chain_seq"],
    )
    assert third["totals"]["line_count"] > 0

    # a run of another entity is another key: it never stands in the way. The later run of the
    # first entity has a posting of its own to summarize — a further run without a line is not
    # made (PRD ERR-96; item JRN-EMPTY-RUN-1).
    other = _calculated(world, maya, ENTITY_2)
    post_lines(
        world,
        key="r52b-activity-after-the-third",
        contract_key="Contract 1",
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "5.00", "POB #1"),
                    ("REVENUE", "5001", "-5.00", "POB #1"),
                ],
            )
        ],
    )
    fourth = _calculated(world, maya, ENTITY_1)
    assert _cancelled(world, maya, other)["state"] == "cancelled"
    assert _run(world, fourth)["state"] == "draft"


@pytest.mark.slow
def test_r52b_a_cancel_and_a_calculation_of_one_key_do_not_cross(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The rule under concurrency, observed: the cancel of the key's only run is open (not
    committed) when the calculation of the next run of the key starts. The calculation is seen
    WAITING for the key's coverage lock, and once the cancel commits it covers the key from its
    first seal. Without the lock the calculation read the run being cancelled as standing and
    started after it, so the cancelled run's seals were left to no run."""
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    maya = world.legacy.maya
    # The next calculation of the key is accepted while the key has no run: beside a run, with
    # nothing for a new one to summarize, the command itself answers 409 (PRD ERR-96; item
    # JRN-EMPTY-RUN-1).
    # Its job starts below, once the key's only run is being cancelled.
    created = post(app, JOURNAL_RUNS, maya, {"entity_code": ENTITY_1, "period_key": JANUARY})
    assert created.status_code == 202, created.text
    job_id, second = UUID(str(created.json()["id"])), str(created.headers[RUN_ID_HEADER])
    first = _calculated(world, maya, ENTITY_1)
    covered = _run(world, first)["coverage"]
    assert covered["from_chain_seq"] == 0 and covered["to_chain_seq"] > 0
    outcome: dict[str, Any] = {}

    def calculate() -> None:
        try:
            run_import_job(world.legacy.imports, job_id)
        except Exception as error:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = error

    worker = threading.Thread(target=calculate, name="r52b-calculate")
    started = False
    try:
        with observing_checkouts() as backends, world.legacy.place().uow() as uow:
            holder_pid = backend_pid(uow.session)
            cancelled = commands.cancel_run(
                uow, UUID(first), JournalRunCancelIn(reason="Recalculate.")
            )
            assert cancelled.state.value == "cancelled"
            worker.start()
            started = True
            blocked_pid, blocked_in = await_lock_wait(
                uow.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=20.0,
                expect="pg_advisory_xact_lock",
            )
            assert blocked_pid != holder_pid and worker.is_alive(), (blocked_pid, blocked_in)
            uow.commit()
    finally:
        if started:
            worker.join(timeout=60.0)
    assert not worker.is_alive() and "error" not in outcome, outcome
    shown = _run(world, second)
    assert (shown["state"], shown["coverage"]) == ("draft", covered)
    assert shown["totals"]["line_count"] > 0
    assert _run(world, first)["state"] == "cancelled"


@pytest.mark.parametrize(
    ("source", "target"), PAIRS, ids=[f"{source}-{target}" for source, target in PAIRS]
)
def test_transition_table(
    committed_db: TestDatabase, keyring: KeyRing, source: str, target: str
) -> None:
    """Every E-34 pair on ``journal_run`` and ``journal_batch``: the eight allowed pairs succeed;
    DB-03 refuses every other pair in Python and in the database with ``EREV-TRN-001``."""
    allowed = (source, target) in ALLOWED
    for name in ("journal_run", "journal_batch"):
        errors = transitions.violations(
            transitions.TRANSITIONS[name], to_status=target, set_values={}, expected_status=source
        )
        assert (errors == []) is allowed, errors

    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, tenant_id)
        for table, row_id in ((journal_batch, rows.batch["id"]), (journal_run, rows.run["id"])):
            for step in PATHS[source]:
                session.execute(update(table).where(table.c.id == row_id).values(state=step))
            statement = update(table).where(table.c.id == row_id).values(state=target)
            savepoint = session.begin_nested()
            if allowed:
                session.execute(statement)
                savepoint.commit()
                stored = session.execute(
                    select(table.c.state).where(table.c.id == row_id)
                ).scalar_one()
                assert str(stored) == target
                continue
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(statement)
            savepoint.rollback()
            orig = excinfo.value.orig
            assert getattr(orig, "sqlstate", None) == "P0001"
            message = str(getattr(getattr(orig, "diag", None), "message_primary", ""))
            assert message.startswith("EREV-TRN-001: state of "), message
            assert f"cannot change from {source} to {target}" in message, message
