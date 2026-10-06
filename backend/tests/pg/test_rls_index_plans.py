"""The plans of the hot reads behind the keys revision 0112 reordered or replaced, as the
application runs them — ``erev_app`` under the tenant's row-level security (04 NC-20 and §1.4
"Index conditions under a policy", rev 1.181; dev-guide DG-KRN-DB-10, DG-LST-08; supervisor
ruling R-116; item PERF-RLS-INDEX-1).

Under a policy a condition bounds an index scan only when its operator is leakproof: an
enumeration in front of a selective column kept that column out of every scan, and the read
looked indexed in its SQL all the same. Only the plan shows it. Each test runs the product's own
read once, takes the statement and the values the application engine sent, and reads the plan
PostgreSQL makes of them for ``erev_app``: the selective column is an INDEX CONDITION, the
enumeration a filter (which is the policy at work), and a status read enters a partial index its
statement implies.

A plan test asks what an index CAN take, not what is cheapest for a table of a few rows: the
planner's alternatives are switched off for the ``EXPLAIN`` (``FORCED``), and a condition the
policy keeps out of an index shows as ``Filter`` however the plan is forced.
"""

from __future__ import annotations

import re
from calendar import monthrange
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.adapters.email import build_email_sender
from erev_api.approvals import engine as approvals
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    exception_item,
    job,
    period,
    period_state,
    source_record,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.integrations import normalise
from erev_api.domain.integrations.normalise import SourceIdentity
from erev_api.domain.journals import subledger
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ExceptionStatus,
    JobKind,
    JobState,
    OutboxTopic,
    PrincipalKind,
    SourceObjectType,
    SourceSystem,
    SubledgerPostingKind,
    TenantKind,
)
from erev_api.events import outbox, webhooks
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry, sweeper
from erev_api.jobs.context import JobAttempt, JobContext, JobRuntime, system_unit_of_work
from erev_api.main import create_app
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import insert, select, text
from support.db import TestDatabase
from support.http import call
from support.plans import FORCED, ROWS, analyse, bound_by, nodes, plan, reads, scan, sent
from support.principals import cookie_headers, enrolled, member
from support.reference import assign
from support.rows import (
    approval_request_values,
    exception_item_values,
    insert_close_parts,
    insert_ledger_parts,
    ledger_seal_values,
    period_state_values,
    period_values,
    subledger_line_values,
    subledger_posting_values,
)

pytestmark = pytest.mark.pg

# Sealed postings the replay test writes: each is a posting, two lines and a seal through the
# ledger's own triggers, so fewer than ``ROWS`` — enough for the costs to tell the keys apart.
POSTINGS = 300


def _context(tenant_id: UUID, clock: FrozenClock) -> RequestContext:
    return RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-rls-index-plans",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


@contextmanager
def _uow(
    tenant_id: UUID, keyring: KeyRing, clock: FrozenClock, settings: Settings
) -> Iterator[UnitOfWork]:
    with unit_of_work(
        _context(tenant_id, clock),
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(settings.file_root),
    ) as uow:
        yield uow


@pytest.fixture
def tenant_id(test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> UUID:
    return member(keyring, clock).tenant_id


@pytest.fixture
def runtime(
    app_settings: Settings, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> JobRuntime:
    """A job runtime whose fake email sender writes under the test's own directory: the relay of
    the outbox test dispatches the invitation the tenant's provisioning enqueued."""
    settings = app_settings.model_copy(update={"run_dir": tmp_path / ".run"})
    return JobRuntime(
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(settings.file_root),
        email=build_email_sender(settings, clock),
        public_origin=settings.public_origin,
    )


def test_the_replay_check_of_a_posting_is_bound_by_its_idempotency_key(
    test_database: TestDatabase,
    tenant_id: UUID,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    """``subledger.post`` first asks whether the posting exists (RCP-21): once for EVERY posting.
    The key was ``(tenant_id, book_code, idempotency_key)`` and the read walked the tenant's whole
    key; with the book last the idempotency key bounds it."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:  # a ledger of sealed postings, each with two lines
        parts = insert_ledger_parts(session, tenant_id)
        for number in range(POSTINGS):
            posting = subledger_posting_values(
                tenant_id, parts=parts, idempotency_key=f"compute:probe-{number:04d}"
            )
            session.execute(insert(subledger_posting).values(**posting))
            lines = [
                subledger_line_values(tenant_id, posting=posting, parts=parts, amount=amount)
                for amount in (Decimal("10.00"), Decimal("-10.00"))
            ]
            session.execute(insert(subledger_line), lines)
            seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
            session.execute(insert(subledger_posting_seal).values(**seal))
    analyse(test_database, "subledger_posting", "subledger_posting_seal")
    with (
        sent() as seen,
        _uow(tenant_id, keyring, clock, app_settings) as uow,
        pytest.raises(ValueError, match="at least two lines"),
    ):
        subledger.post(
            uow,
            book_code=BookCode.ASC606.value,
            posting_kind=SubledgerPostingKind.VOID_REVERSAL,
            idempotency_key="tests-rls-index-plans",
            description="the replay check alone: the posting has no lines and is refused",
            lines=[],
        )
    (replay,) = reads(seen, "subledger_posting")
    found = scan(plan(tenant_id, replay), "subledger_posting")
    bound_by(found, "ux_subledger_posting__idempotency", "idempotency_key")
    assert "book_code" in found["Filter"], found  # the enumeration: a filter under the policy


def test_the_stored_version_of_a_source_record_is_bound_by_its_external_id(
    test_database: TestDatabase,
    tenant_id: UUID,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    """``normalise.store_source_record`` reads the stored record of the identity and the highest
    version of the object, once for EVERY ingested record: both are bound by the external id."""

    def store(uow: UnitOfWork, version: int) -> None:
        identity = SourceIdentity(
            SourceSystem.SALESFORCE, SourceObjectType.ORDER, "SO-0000001", str(version)
        )
        normalise.store_source_record(
            uow, identity=identity, version_order=version, payload={"order_number": "SO-0000001"}
        )

    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with _uow(tenant_id, keyring, clock, app_settings) as uow:
        store(uow, 1)
        uow.commit()
    with tenant_session(context) as session:  # ... and its later versions, written directly
        first = dict(session.execute(select(source_record)).mappings().one())
        session.execute(
            insert(source_record),
            [
                {
                    **first,
                    "id": new_id(),
                    "external_version": str(version),
                    "version_order": version,
                }
                for version in range(2, ROWS)
            ],
        )
    analyse(test_database, "source_record")
    with sent() as seen, _uow(tenant_id, keyring, clock, app_settings) as uow:
        store(uow, ROWS)
        uow.commit()
    stored, highest = reads(seen, "source_record")
    by_identity = scan(plan(tenant_id, stored), "source_record")
    bound_by(by_identity, "ux_source_record__identity", "external_id", "external_version")
    by_order = scan(plan(tenant_id, highest), "source_record")
    bound_by(by_order, "ix_source_record__order", "external_id")
    assert by_order["Scan Direction"] == "Backward", by_order  # the highest version first


_GUARD_LOOKUP = (
    "SELECT s.state::text FROM erev.period_state s "
    "WHERE s.tenant_id = %(tenant_id)s AND s.entity_id = %(entity_id)s "
    "AND s.book_code = %(book_code)s AND s.period_id = %(period_id)s FOR SHARE"
)
_GUARD_SOURCE = text("SELECT prosrc FROM pg_proc WHERE proname = :name")


def test_the_period_guard_reads_one_period_state(
    test_database: TestDatabase, tenant_id: UUID
) -> None:
    """DB-07: every subledger line and every journal line inserted looks its period's state up by
    entity, book and period, as the caller. The lookup is bound by the entity and the period."""
    wanted = " ".join(_GUARD_LOOKUP.split("WHERE")[1].split("FOR SHARE")[0].split())
    wanted = re.sub(r"%\((\w+)\)s", r"NEW.\1", wanted)
    with test_database.owner_engine.connect() as connection:
        for guard in ("tg_subledger_line__period_guard", "tg_journal_line__period_guard"):
            source = connection.execute(_GUARD_SOURCE, {"name": guard}).scalar_one()
            assert wanted in " ".join(str(source).split()), guard  # the statement read below
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)  # the entity, with January 2026
        months = [(year, month) for year in range(2026, 2046) for month in range(1, 13)][1:]
        periods = [
            period_values(
                tenant_id,
                calendar_id=parts.calendar_id,
                fiscal_year=year,
                period_no=month,
                start_date=date(year, month, 1),
                end_date=date(year, month, monthrange(year, month)[1]),
            )
            for year, month in months  # ... and the other periods of twenty years
        ]
        session.execute(insert(period), periods)
        session.execute(
            insert(period_state),
            [
                period_state_values(
                    tenant_id,
                    entity_id=parts.entity_id,
                    period_id=row["id"],
                    period_end_date=row["end_date"],
                )
                for row in periods
            ],
        )
    analyse(test_database, "period_state")
    parameters = {
        "tenant_id": tenant_id,
        "entity_id": parts.entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": parts.period_id,
    }
    state = scan(plan(tenant_id, (_GUARD_LOOKUP, parameters)), "period_state")
    bound_by(state, "ux_period_state__period", "entity_id", "period_id")


def test_the_live_jobs_are_read_through_the_partial_index(
    test_database: TestDatabase, tenant_id: UUID, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """The pending check of every single-flight defer, and the three reads of the sweeper for
    every tenant at every tick: each statement implies ``state IN ('QUEUED','RUNNING')`` and
    enters the partial index on it, however many finished jobs the tenant has."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    history = [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "kind": JobKind.OUTBOX_RELAY.value,
            "state": (JobState.QUEUED if number % 150 == 0 else JobState.SUCCEEDED).value,
            "params": {},
            "queue": "default",
            "created_at": clock.now() - timedelta(minutes=number),
            "created_by_kind": PrincipalKind.SYSTEM.value,
            "updated_by_kind": PrincipalKind.SYSTEM.value,
        }
        for number in range(300)  # two live jobs in a history of three hundred
    ]
    with tenant_session(context) as session:
        session.execute(insert(job), history)
    analyse(test_database, "job")
    with sent() as seen:
        with tenant_session(context, read_only=True) as session:
            registry.pending_job_id(session, JobKind.OUTBOX_RELAY)
        sweeper._requeue(tenant_id, clock.now())
        sweeper._redispatch_stranded(tenant_id, runtime, frozenset())
        sweeper._fail_stalled(tenant_id, runtime)
    of_jobs = reads(seen, "job")
    assert len(of_jobs) == 4, [statement for statement, _ in of_jobs]
    for read in of_jobs:
        live = scan(plan(tenant_id, read), "job")
        bound_by(live, "ix_job__live")


def test_a_jobs_unit_of_work_reaches_its_job_through_the_primary_key(
    test_database: TestDatabase, tenant_id: UUID, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """05 JOB-06 rev 1.200 (item JOB-STALL-COMMIT-RACE-1): every unit of work of a job reads its
    job's row where it begins and writes its heartbeat on it at its commit. The two statements
    name the job by its key, and each is one probe of the primary key, however many jobs the
    tenant has and however many of them are live - not a walk of the live jobs, which their
    condition on the state would also admit."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    running = new_id()
    history = [
        {
            "tenant_id": tenant_id,
            "id": running if number == 0 else new_id(),
            "kind": JobKind.OUTBOX_RELAY.value,
            "state": (
                JobState.RUNNING
                if number == 0
                else JobState.QUEUED
                if number % 2 == 0
                else JobState.SUCCEEDED
            ).value,
            "params": {},
            "queue": "default",
            "created_at": clock.now() - timedelta(minutes=number),
            "created_by_kind": PrincipalKind.SYSTEM.value,
            "updated_by_kind": PrincipalKind.SYSTEM.value,
        }
        for number in range(300)  # half of them live
    ]
    with tenant_session(context) as session:
        session.execute(insert(job), history)
    analyse(test_database, "job")
    worker = replace(runtime, attempt=JobAttempt(job_id=running, tenant_id=tenant_id, task_id=None))
    with sent() as seen:
        with system_unit_of_work(
            worker, system_principal(tenant_id), request_id="tests-rls-index-plans"
        ) as uow:
            uow.commit()
    (read,) = reads(seen, "job")
    (write,) = [sent_ for sent_ in seen if sent_[0].lstrip().startswith("UPDATE erev.job")]
    for statement in (read, write):
        (probe,) = [
            node
            for node in nodes(plan(tenant_id, statement))
            if node.get("Relation Name") == "job" and node["Node Type"] != "ModifyTable"
        ]
        bound_by(probe, "job_pkey", "id")


def test_the_outbox_claim_and_the_duplicate_are_bound(
    tenant_id: UUID,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    runtime: JobRuntime,
) -> None:
    """The relay's claim takes a PENDING or FAILED message that is due, or one left DISPATCHING.
    The partial index holds the messages that are not settled — ``status NOT IN
    ('DISPATCHED','DEAD')`` — which both arms of the claim imply and PostgreSQL can prove; a
    predicate listing the three statuses is the same rows and is proved from neither arm that is
    itself a list, so the claim read every message of the tenant. The stored message of a
    duplicate enqueue is bound by its dedupe key."""
    key = f"tests-rls-index-plans:{uuid4()}"
    with sent() as seen:
        with _uow(tenant_id, keyring, clock, app_settings) as uow:
            for _ in range(2):  # the second is the duplicate, and reads the first
                outbox.enqueue(
                    uow,
                    topic=OutboxTopic.EMAIL,
                    aggregate_type="tenant",
                    aggregate_id=tenant_id,
                    dedupe_key=key,
                    payload={},
                )
        relayer = JobContext(
            job_id=new_id(),
            tenant_id=tenant_id,
            kind=JobKind.OUTBOX_RELAY,
            principal=system_principal(tenant_id),
            runtime=runtime,
            persisted=False,
        )
        outbox.relay(relayer)
    of_messages = reads(seen, "outbox_message")
    duplicate = next(read for read in of_messages if "dedupe_key = " in read[0])
    claim = next(read for read in of_messages if "SKIP LOCKED" in read[0])
    stored = scan(plan(tenant_id, duplicate), "outbox_message")
    bound_by(stored, "ux_outbox_message__dedupe", "dedupe_key")
    due = scan(plan(tenant_id, claim), "outbox_message")
    bound_by(due, "ix_outbox_message__due")


def test_the_due_deliveries_and_the_pending_request_of_a_subject_are_bound(
    test_database: TestDatabase,
    tenant_id: UUID,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    """The webhook deliveries due now enter the partial index on PENDING and FAILED. The pending
    request of a subject — read by every command that changes a subject under approval — is
    bound by the subject's id within the pending requests."""
    due = scan(plan(tenant_id, webhooks.due_deliveries(clock.now())), "webhook_delivery")
    bound_by(due, "ix_webhook_delivery__due", "next_attempt_at")
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:  # a long inbox: the costs tell the two keys apart
        session.execute(
            insert(approval_request), [approval_request_values(tenant_id) for _ in range(ROWS)]
        )
    analyse(test_database, "approval_request")
    with sent() as seen, _uow(tenant_id, keyring, clock, app_settings) as uow:
        approvals.void_if_stale(
            uow, subject_type=ApprovalSubjectType.MODIFICATION, subject_id=uuid4()
        )
    (pending,) = reads(seen, "approval_request")
    request = scan(plan(tenant_id, pending), "approval_request")
    bound_by(request, "ux_approval_request__pending_subject", "subject_id")


def test_a_list_by_status_enters_the_partial_index_and_a_list_by_date_stops_at_the_page(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """The lists of jobs, approval requests and exception items, by date. With the statuses a
    reader of live work asks for, each statement proves the partial index on those statuses —
    the list kernel binds an enumeration literal as a constant of the column's type, where a
    text value cast when the statement runs proved nothing — and reads the few live rows in date
    order. Without a status the list pages through the plain ``(tenant_id, <date>)`` index, read
    backwards for the newest first, and stops at the page (DG-LST-08)."""
    app = create_app(app_settings, clock=clock)
    someone = member(keyring, clock)
    for role_code in ("auditor", "controller"):
        assign(someone, role_code)
    actor = enrolled(app, clock, someone)
    tenant_id = someone.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:  # ten live rows in a history of two thousand, each
        session.execute(
            insert(job),
            [
                {
                    "tenant_id": tenant_id,
                    "id": new_id(),
                    "kind": JobKind.OUTBOX_RELAY.value,
                    "state": (JobState.QUEUED if number % 200 == 0 else JobState.SUCCEEDED).value,
                    "params": {},
                    "queue": "default",
                    "created_at": clock.now() - timedelta(minutes=number),
                    "created_by_kind": PrincipalKind.SYSTEM.value,
                    "updated_by_kind": PrincipalKind.SYSTEM.value,
                }
                for number in range(ROWS)
            ],
        )
        session.execute(
            insert(approval_request),
            [
                {
                    **approval_request_values(
                        tenant_id,
                        preparer_id=someone.user_id,
                        status=(
                            ApprovalRequestStatus.PENDING
                            if number % 200 == 0
                            else ApprovalRequestStatus.APPROVED
                        ),
                    ),
                    "submitted_at": clock.now() - timedelta(minutes=number),
                }
                for number in range(ROWS)
            ],
        )
        session.execute(
            insert(exception_item),
            [
                {
                    **exception_item_values(tenant_id),
                    "status": (
                        ExceptionStatus.OPEN if number % 200 == 0 else ExceptionStatus.DISMISSED
                    ).value,
                    "created_at": clock.now() - timedelta(minutes=number),
                }
                for number in range(ROWS)
            ],
        )
    analyse(test_database, "job", "approval_request", "exception_item")
    live, newest = "created_at", "-created_at"
    lists: list[tuple[str, dict[str, Any], str, str, str]] = [
        ("jobs", {"state": ["QUEUED", "RUNNING"], "sort": live}, "job", "ix_job__live", "Forward"),
        ("jobs", {"sort": newest}, "job", "ix_job__created", "Backward"),
        (
            "approvals",
            {"status": "PENDING"},
            "approval_request",
            "ix_approval_request__pending",
            "Backward",
        ),
        ("approvals", {}, "approval_request", "ix_approval_request__submitted", "Backward"),
        (
            "exceptions",
            {"status": ["OPEN", "IN_PROGRESS"], "sort": newest},
            "exception_item",
            "ix_exception_item__open",
            "Backward",
        ),
        (
            "exceptions",
            {"sort": newest},
            "exception_item",
            "ix_exception_item__created",
            "Backward",
        ),
    ]
    headers = cookie_headers(actor.token, key=False)
    for resource, params, table, index, direction in lists:
        with sent() as seen:
            answered = call(app, "GET", f"/api/v1/{resource}", params=params, headers=headers)
        assert answered.status_code == 200, answered.text
        assert answered.json()["items"], (resource, params)
        (page,) = [read for read in reads(seen, table) if " LIMIT " in read[0]]
        found = plan(tenant_id, page, off=(*FORCED, "enable_sort"))
        entered = scan(found, table)
        assert (entered["Index Name"], entered["Scan Direction"]) == (index, direction), (
            resource,
            params,
            entered,
        )
        assert not [node for node in nodes(found) if node["Node Type"] == "Sort"], (
            resource,
            params,
        )
