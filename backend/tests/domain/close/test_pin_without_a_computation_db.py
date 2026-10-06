"""A transaction that records an event and stores no computation of it asks the period pin at
its end (PRD ERR-72 rev 1.187; 04 §14.1 "A command recorded before a lock" rev 1.229; 05 RCP-18
rev 1.169 and §5.6 rev 1.195; dev-guide DG-CMD-10 rev 1.218; supervisor rulings R-122 (j) and (l)
and of 2026-10-02; item PIN-WINDOW-APPENDER-1). PostgreSQL-bound.

The pin stands where a computation is stored (``computation.persist``;
``test_period_state_moved_db.py``). A transaction that appends to a stream and stores no
computation never got there: its event kept the stamp of its transaction, a period lock decided
after that stamp froze its datasets without the event, and the computation that read it later — a
job, which records nothing and is not judged — wrote a version known at the lock's cutoff.

World: PRD WLD-K-04 as the pin's fourth witness builds it — ``SF-ORD-UK-2001`` is contracted by
AVM-UK and AVM-US performs O1; April 2026 of AVM-US stands with its lock requested, and Marcus's
approval is the decision D. The lock is the PERFORMING entity's: the transactions below name
AVM-UK alone, so nothing but the stream says that AVM-US is concerned
(``bundles.entity_codes``). The late transaction T records its event, is held, D is decided at
the server's present, and T goes on:

- Maya's invoice through ``POST /contracts/{id}/events`` on a group beyond the obligation budget:
  the command appends and DEFERS its computation;
- the same invoice while the engine refuses the group: the computation would be stored
  ``QUARANTINED``, without a version, and the event would stay;
- the commit of an import of recorded facts (CSV v2 ``progress_events``): its job runs the commit
  once more, stamped after the lock, and the import is committed.

And, in PRD WLD-K-01, what the job does with a commit that is refused both times, and with a
refusal that is not the pin's.
"""

from __future__ import annotations

import csv
import io
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api import problems
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_computation,
    contract_event,
    exception_item,
    job,
    obligation,
    period_lock,
    ssp_book,
)
from erev_api.domain.contracts import bundles, compute_job, period_ends
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.contracts.commands import book_contract
from erev_api.domain.imports import commit as import_commit
from erev_api.domain.imports.csv_v2 import recorded
from erev_api.domain.platform import setup
from erev_api.enums import ContractEventType
from erev_api.events.payloads import ChecklistItemV1, ContractActivatedV1, ContractBookedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_engine.errors import EngineError
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.close_world import (
    close_run_succeeded_for,
    periods_closed_before,
    reviewed_reconciliations_for,
)
from support.db import TestDatabase
from support.factories import (
    ImportWorld,
    approved_ssp_version,
    point_entry,
    run_import_job,
)
from support.http import HttpResponse, call
from support.interleave import backend_pid
from support.legacy_replay import diffed, job_of, shown, submit
from support.principals import cookie_headers
from support.reference import PERIODS, approve, assign, post, slug

pytestmark = pytest.mark.slow

AVM_US = worlds.AVM_US
K04 = worlds.K04
APRIL = "FY2026-P04"
JOIN_SECONDS = 120.0
# An invoice of 100.00 GBP on O2, dated 30 Jun 2026: a person's invoice is appended and computed
# without an approval (BUILD_SPEC CTR-6).
INVOICE: Mapping[str, Any] = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-06-30",
    "payload": {
        "invoice_number": "INV-UK-2090",
        "line_external_id": "INV-UK-2090-1",
        "obligation_key": "O2",
        "amount": {"amount": "100.00", "currency": "GBP"},
        "issue_date": "2026-06-30",
    },
}
# PRD WLD-K-04: O2 stands at 100% since 31 May 2026; the file of 30 Jun 2026 confirms it.
PROGRESS_ROW = (K04, "PROGRESS_RECORDED", "2026-06-30", "O2", "1", "OUTPUT_PERCENT")


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


def _present(world: worlds.ReportWorld) -> Any:
    """The server's clock, which stamps ``recorded_at`` (04 DB-08)."""
    return world.place.scalar(select(func.clock_timestamp()))


@dataclass(frozen=True, slots=True)
class _Pending:
    """April 2026 of AVM-US with its lock requested; ``SF-ORD-UK-2001`` is AVM-UK's."""

    world: worlds.ReportWorld
    lock_request: str
    contract_id: UUID
    group_id: UUID
    entity_id: UUID
    period_id: UUID


def _pending(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> _Pending:
    """``worlds.k04_saltmarsh`` on the record-time clock with April of AVM-US up to its lock
    request, by the steps of the pin's fourth witness; tenant setup is complete, so that an
    approval takes no tenant row."""
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = worlds.on_record_clock(k04.report, clock)
    state = worlds.period_state(world, AVM_US, APRIL)
    entity_id = UUID(str(state["entity"]["id"]))
    period_id = UUID(str(state["period"]["id"]))
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
    return _Pending(
        world=world,
        lock_request=str(requested.json()["approval_request_id"]),
        contract_id=k04.contract_id,
        group_id=k04.group_id,
        entity_id=entity_id,
        period_id=period_id,
    )


@dataclass(slots=True)
class _Stand:
    """Where the late transaction is held, once: what it was when it got there."""

    reached: threading.Event = field(default_factory=threading.Event)
    go: threading.Event = field(default_factory=threading.Event)
    seen: dict[str, Any] = field(default_factory=dict)


def _held(monkeypatch: pytest.MonkeyPatch, owner: Any, name: str, *, after: bool = False) -> _Stand:
    """``owner.name(uow, ...)`` stands at its first call — before the call, or with ``after``
    once it has returned — until it is told to go on. The first call is the late transaction's:
    nothing else of the world reaches the function while it stands."""
    real = getattr(owner, name)
    stand = _Stand()

    def stood(uow: Any) -> None:
        session = uow.session
        stand.seen["started"] = session.execute(select(func.transaction_timestamp())).scalar_one()
        stand.seen["pid"] = backend_pid(session)
        stand.reached.set()
        assert stand.go.wait(JOIN_SECONDS)

    def held(uow: Any, *args: Any, **kwargs: Any) -> Any:
        first = not stand.seen
        if first and not after:
            stood(uow)
        result = real(uow, *args, **kwargs)
        if first and after:
            stood(uow)
        return result

    monkeypatch.setattr(owner, name, held)
    return stand


def _on_the_servers_clock(world: worlds.ReportWorld, clock: FrozenClock) -> None:
    """The application clock set to the server's present. A second-factor step moves the frozen
    clock on by thirty seconds (``worlds.verified``), which no production clock does: the server
    is waited for first. Nothing stands in a transaction meanwhile."""
    limit = time.monotonic() + JOIN_SECONDS
    while _present(world) <= clock.now():
        assert time.monotonic() < limit, (clock.now(), _present(world))
        time.sleep(0.25)
    clock.set(_present(world))


def _decided_while_it_stands(
    pending: _Pending, clock: FrozenClock, stand: _Stand, late: threading.Thread
) -> tuple[worlds.ReportWorld, dict[str, Any]]:
    """Marcus verifies; the late transaction is started and stands; his approval of April's lock
    is decided at the server's present and commits; the late transaction goes on. The application
    clock is the server's at every step, as in production, so the lock's two instants lie between
    the late transaction's start and whatever begins after the decision. Returns the world with
    fresh sessions on that clock, and the lock's row."""
    world = pending.world
    deciding = worlds.verified(world, clock, "marcus")
    _on_the_servers_clock(world, clock)
    late.start()
    try:
        assert stand.reached.wait(JOIN_SECONDS), stand.seen
        clock.set(_present(world))
        decided = approve(deciding.app, pending.lock_request, deciding.marcus)
        assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
        decided_at = _present(world)
    finally:
        stand.go.set()
        late.join(timeout=JOIN_SECONDS)
    assert not late.is_alive()
    assert worlds.period_state(world, AVM_US, APRIL)["state"] == "closed"
    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.id, period_lock.c.created_at, period_lock.c.cutoff_known_at).where(
            period_lock.c.period_id == pending.period_id,
            period_lock.c.entity_id == pending.entity_id,
        ),
    )
    # the late transaction began before the lock's record, which was written before the decision
    # answered: the lock froze its datasets without the late transaction's event
    assert (
        stand.seen["started"]
        < min(lock["created_at"], lock["cutoff_known_at"])
        <= max(lock["created_at"], lock["cutoff_known_at"])
        < decided_at
    ), (stand.seen, lock, decided_at)
    clock.set(_present(world))
    return worlds.resigned(world), lock


def _stream(pending: _Pending) -> dict[str, int]:
    """What a recorded command leaves: the stream's head and events, the group's computations
    and the jobs of the workspace."""
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
        "compute jobs": count(job, job.c.kind == "CONTRACT_COMPUTE"),
    }


def _invoice(
    pending: _Pending, key: str, head: int
) -> Callable[[worlds.ReportWorld], HttpResponse]:
    """The one request, under one idempotency key however often it is sent."""

    def send(now: worlds.ReportWorld) -> HttpResponse:
        author = now.place.author
        return call(
            now.app,
            "POST",
            f"/api/v1/contracts/{pending.contract_id}/events",
            json={"events": [dict(INVOICE)]},
            headers={
                **cookie_headers(author.token, author.csrf_token, key=False),
                "Idempotency-Key": key,
                "If-Match": f'"s{head}"',
            },
        )

    return send


def _refused_by_name(refused: HttpResponse) -> None:
    """409 ``lock-conflict`` with the rule and the sentence of PRD ERR-72, in the command's form."""
    assert refused.status_code == 409, refused.text  # the status first: a 2xx has no slug
    assert slug(refused) == "lock-conflict", refused.text
    body = refused.json()
    assert body["detail"] == problems.PERIOD_STATE_MOVED_DETAIL
    assert [(error["rule_id"], error["message"]) for error in body["errors"]] == [
        (problems.RULE_PERIOD_STATE_MOVED, problems.PERIOD_STATE_MOVED_DETAIL)
    ]


def _head_event(pending: _Pending) -> dict[str, Any]:
    (event,) = _rows(
        pending.world.tenant_id,
        select(
            contract_event.c.event_type,
            contract_event.c.recorded_at,
            contract_event.c.import_upload_id,
        )
        .select_from(
            contract_event.join(
                contract,
                (contract.c.tenant_id == contract_event.c.tenant_id)
                & (contract.c.id == contract_event.c.contract_id),
            )
        )
        .where(
            contract.c.id == pending.contract_id,
            contract_event.c.stream_version == contract.c.head_stream_version,
        ),
    )
    return event


def test_a_command_that_defers_across_the_lock_of_a_performing_entity_is_refused_and_sent_again(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The group is beyond the obligation budget, so Maya's invoice is appended and its
    computation deferred to ``CONTRACT_COMPUTE`` (05 RCP-18). The command stands at the deferral
    while April of AVM-US — the entity that performs O1, not the one the contract is booked
    under — is locked. It then asks the pin: 409 ``lock-conflict``, rule ``PERIOD_STATE_MOVED``,
    and no event and no job is left. Sent again under the same key it answers 202 with its job,
    and its event is recorded after the lock's record.

    Fail-first: 202 at the first sending; the event stamped before the lock's cutoff, and the
    job's computation — which records nothing and is not judged — known at that stamp."""
    pending = _pending(app, keyring, clock, files)
    monkeypatch.setattr(contract_events, "OBLIGATION_BUDGET", -1)  # every group is beyond it
    stand = _held(monkeypatch, contract_events, "defer_compute")
    before = _stream(pending)
    send = _invoice(pending, f"k-{uuid4()}", before["head"])
    out: dict[str, Any] = {}
    late = threading.Thread(
        target=lambda: out.__setitem__("response", send(pending.world)), name="deferring-command"
    )
    world, lock = _decided_while_it_stands(pending, clock, stand, late)
    _refused_by_name(out["response"])
    assert _stream(pending) == before
    again = send(world)
    assert again.status_code == 202, again.text
    assert "Idempotent-Replay" not in again.headers
    after = _stream(pending)
    assert after == {
        "head": before["head"] + 1,
        "events": before["events"] + 1,
        "computations": before["computations"],
        "compute jobs": before["compute jobs"] + 1,
    }
    event = _head_event(pending)
    assert event["event_type"] == "BILLING_RECORDED"
    assert event["recorded_at"] > max(lock["created_at"], lock["cutoff_known_at"])


def test_a_computation_stored_without_a_version_across_the_lock_is_refused_instead(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The road nobody named. The engine refuses the group — an answer about the group that is
    stored ``QUARANTINED``, without a version, while the command's event stays (05 RCP-20). The
    command stands where that computation is stored while April of AVM-US is locked: it asks the
    pin first and is refused by name; no event, no computation and no exception item is left.

    Fail-first: 201 with a quarantined computation; the event stamped before the lock's cutoff,
    which the computation that later succeeds without a new event is known at."""
    pending = _pending(app, keyring, clock, files)
    compute = contract_events.compute_group

    def refusing(_bundle: Any) -> Any:
        raise EngineError("ENGINE_INVARIANT_VIOLATED", "allocation does not sum", detail={})

    def computed_by_a_refusing_engine(uow: Any, group_id: UUID, **kwargs: Any) -> Any:
        return compute(uow, group_id, **{**kwargs, "engine": refusing})

    monkeypatch.setattr(contract_events, "compute_group", computed_by_a_refusing_engine)
    stand = _held(monkeypatch, compute_job, "_refused")
    before = _stream(pending)
    items = _rows(
        pending.world.tenant_id, select(func.count().label("n")).select_from(exception_item)
    )
    send = _invoice(pending, f"k-{uuid4()}", before["head"])
    out: dict[str, Any] = {}
    late = threading.Thread(
        target=lambda: out.__setitem__("response", send(pending.world)), name="quarantined-command"
    )
    _decided_while_it_stands(pending, clock, stand, late)
    _refused_by_name(out["response"])
    assert _stream(pending) == before
    assert items == _rows(
        pending.world.tenant_id, select(func.count().label("n")).select_from(exception_item)
    )


def test_a_draft_and_a_group_nothing_was_recorded_in_are_not_judged(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """What the check leaves alone (04 §14.1 rev 1.229), with
    ``period_ends.refuse_appends_a_lock_met`` asked as a transaction that began before a lock
    asks it.

    A draft is not judged (the class ``DRAFT`` of dev-guide DG-ARC-19: the commit of a contract
    import, an adapter's order). The transaction books ``SF-ORD-UK-2002``, whose one line AVM-US
    performs, and April of AVM-US is locked while it stands: the booking is stamped before the
    lock's cutoff, AVM-US is an entity of the draft's group, and the check does not refuse —
    nothing of a draft is in a frozen dataset or in the ledger, and its activation records
    events of its own. In the same transaction the contract is then activated as a fixture
    activates one, and the same question is refused by name: the draft was spared for being a
    draft, and for nothing else.

    Nor is a group the transaction recorded nothing in: asked for the group of
    ``SF-ORD-UK-2001`` — active, AVM-US among its entities — the same transaction is not
    refused. A job that computes what an earlier transaction recorded asks so and is not judged.

    Fail-first (the condition on the contract's status taken out): the draft was refused; (the
    condition on the event's stamp taken out): the group nothing was recorded in was refused."""
    pending = _pending(app, keyring, clock, files)
    world = pending.world
    (first,) = _rows(
        world.tenant_id, select(contract.c.customer_id).where(contract.c.id == pending.contract_id)
    )
    body = {
        "external_id": "SF-ORD-UK-2002",
        "customer_id": str(first["customer_id"]),
        "contracting_entity_code": worlds.AVM_UK,
        "transaction_currency": "GBP",
        "inception_date": "2026-04-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": worlds.PLATFORM_UK,
                "quantity": "1",
                "total_price": {"amount": "60000.00", "currency": "GBP"},
                "performing_entity_code": AVM_US,
                "start_date": "2026-04-01",
                "end_date": "2027-03-31",
            }
        ],
    }
    deciding = worlds.verified(world, clock, "marcus")
    _on_the_servers_clock(world, clock)
    with world.place.uow() as uow:
        booked = book_contract(uow, body=ContractBookedV1.model_validate(body), origin="UI")
        contract_id = UUID(str(booked.contract["id"]))
        group_id = UUID(str(booked.combination_group["id"]))
        started = uow.session.execute(select(func.transaction_timestamp())).scalar_one()
        assert bundles.entity_codes(uow.session, [group_id]) == [worlds.AVM_UK, AVM_US]
        clock.set(_present(world))
        decided = approve(deciding.app, pending.lock_request, deciding.marcus)
        assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
        (lock,) = _rows(
            world.tenant_id,
            select(period_lock.c.cutoff_known_at).where(
                period_lock.c.period_id == pending.period_id,
                period_lock.c.entity_id == pending.entity_id,
            ),
        )
        assert started < lock["cutoff_known_at"]
        period_ends.refuse_appends_a_lock_met(uow, [group_id])  # a draft: not judged
        # nothing recorded in this group by this transaction: not judged
        period_ends.refuse_appends_a_lock_met(uow, [pending.group_id])
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=1,
            events=[
                EventIn(
                    event_type=ContractEventType.CONTRACT_ACTIVATED,
                    effective_date=booked.contract["inception_date"],
                    payload=ContractActivatedV1(
                        checklist=(ChecklistItemV1(code="SOURCE_REFERENCE", passed=True),)
                    ),
                )
            ],
            origin="UI",
        )
        with pytest.raises(problems.Problem) as refused:
            period_ends.refuse_appends_a_lock_met(uow, [group_id])
    assert problems.is_period_state_moved(refused.value)
    assert (refused.value.status, refused.value.detail) == (
        409,
        problems.PERIOD_STATE_MOVED_DETAIL,
    )


def test_an_ssp_override_approved_across_the_lock_is_refused_and_decided_again(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approval hook of an SSP override appends the line's attributes and computes nothing
    (``policies.overrides._apply_ssp_override``), so it asks the pin after its append. Priya's
    approval of an override on O1 of ``SF-ORD-UK-2001`` — the obligation AVM-US performs — stands
    at that question while April of AVM-US is locked. The decision is refused in its own form:
    409 ``lock-conflict``, rule ``PERIOD_STATE_MOVED``, "… Decide again: it is then recorded
    after the lock."; the request is still pending and no event is left. Decided again it is
    approved, and the event is recorded after the lock's record.

    Fail-first (the hook without its question): the question is never reached — the approval
    answers by itself, with its event stamped before a lock that comes afterwards."""
    pending = _pending(app, keyring, clock, files)
    world = pending.world
    (book,) = _rows(world.tenant_id, select(ssp_book.c.id).where(ssp_book.c.code == "UK-LIST"))
    later = approved_ssp_version(
        world.app,
        world.maya,
        [world.priya],
        str(book["id"]),
        label="2026-H2",
        effective_from="2026-10-01",
        entries=[
            point_entry(worlds.PLATFORM_UK, "60000.00", currency="GBP", value_basis="AMOUNT"),
            point_entry(worlds.IMPLEMENTATION_UK, "10000.00", "cost_plus_margin", currency="GBP"),
        ],
    )
    (o1,) = _rows(
        world.tenant_id,
        select(obligation.c.id).where(
            obligation.c.contract_id == pending.contract_id, obligation.c.obligation_key == "O1"
        ),
    )
    asked = post(
        world.app,
        f"/api/v1/obligations/{o1['id']}/request-ssp-override",
        world.maya,
        {
            "ssp_book_version_id": later,
            "justification": "The October list applies to this order by agreement.",
        },
    )
    assert asked.status_code == 200, asked.text
    request_id = str(asked.json()["approval_request_id"])
    before = _stream(pending)
    deciding = worlds.verified(world, clock, "priya")
    # The hook's question, before it is asked: the event is appended, nothing is committed.
    stand = _held(monkeypatch, period_ends, "refuse_appends_a_lock_met")
    out: dict[str, Any] = {}
    late = threading.Thread(
        target=lambda: out.__setitem__(
            "response", approve(deciding.app, request_id, deciding.priya)
        ),
        name="override-approval",
    )
    world, lock = _decided_while_it_stands(pending, clock, stand, late)
    refused = out["response"]
    assert refused.status_code == 409, refused.text  # the status first: a 2xx has no slug
    assert slug(refused) == "lock-conflict", refused.text
    assert refused.json()["detail"] == problems.PERIOD_STATE_MOVED_DECISION_DETAIL
    assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
        (problems.RULE_PERIOD_STATE_MOVED, problems.PERIOD_STATE_MOVED_DECISION_DETAIL)
    ]
    assert _stream(pending) == before
    # A fresh sign-in answers its challenge with the earliest step of the window its factor has
    # not used, which may be the NEXT one (``principals.next_code``; T-PLT-04): two steps on, no
    # code of Priya's is spent — and the server is waited for, as at every step of this module.
    clock.advance(timedelta(seconds=60))
    _on_the_servers_clock(world, clock)
    again = worlds.verified(world, clock, "priya")
    decided = approve(again.app, request_id, again.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    after = _stream(pending)
    assert (after["head"], after["events"]) == (before["head"] + 1, before["events"] + 1)
    event = _head_event(pending)
    assert event["event_type"] == "LINE_ATTRIBUTES_CHANGED"
    assert event["recorded_at"] > max(lock["created_at"], lock["cutoff_known_at"])


def _approved_import(
    report: worlds.ReportWorld, clock: FrozenClock, *, name: str, rows: list[tuple[str, ...]]
) -> tuple[worlds.ReportWorld, ImportWorld, str, UUID]:
    """Maya uploads the CSV v2 ``progress_events`` file ``name`` and submits it, and Priya
    approves it: the commit job is deferred and has not run (the steps of
    ``worlds.committed_import`` up to the job, on the clock as it stands). Returns the world, the
    import world, the upload's id and the job's."""
    imports = ImportWorld(app=report.app, actor=report.maya, runtime=report.runtime, clock=clock)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(worlds.PROGRESS_COLUMNS)
    writer.writerows(rows)
    import_id = diffed(imports, name, buffer.getvalue().encode("utf-8"), "progress_events")
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    report = worlds.verified(report, clock, "priya")
    decided = approve(report.app, str(submitted.json()["approval_request_id"]), report.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    return report, imports, import_id, job_of(imports, UUID(import_id), "IMPORT_COMMIT")


def test_an_imports_commit_across_the_lock_is_run_once_more_and_committed_after_it(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An approved import of recorded facts names ``SF-ORD-UK-2001``. Its commit has appended
    the event — it computes nothing — when April of AVM-US is locked. After its plans the commit
    asks the pin and is refused: nothing was written and the upload is still ``COMMITTING``. An
    import has no sender to send it again, so the job runs the commit once more: the second
    transaction is stamped after the lock, the upload is ``COMMITTED``, its one event is
    recorded after the lock's record, and the job succeeded.

    Fail-first: one commit, ``COMMITTED``, with the event stamped before the lock's cutoff."""
    pending = _pending(app, keyring, clock, files)
    report, imports, import_id, job_id = _approved_import(
        pending.world, clock, name="avm-uk-progress-2026-06.csv", rows=[PROGRESS_ROW]
    )
    pending = _Pending(
        world=report,
        lock_request=pending.lock_request,
        contract_id=pending.contract_id,
        group_id=pending.group_id,
        entity_id=pending.entity_id,
        period_id=pending.period_id,
    )
    before = _stream(pending)
    commits: list[Any] = []
    commit_upload = import_commit.commit_upload

    def counted(uow: Any, upload_id: UUID) -> Any:
        commits.append(uow.session.execute(select(func.transaction_timestamp())).scalar_one())
        return commit_upload(uow, upload_id)

    monkeypatch.setattr(import_commit, "commit_upload", counted)
    stand = _held(monkeypatch, recorded, "append", after=True)
    out: dict[str, Any] = {}

    def run() -> None:
        try:
            run_import_job(imports, job_id)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            out["error"] = error

    late = threading.Thread(target=run, name="import-commit")
    _, lock = _decided_while_it_stands(pending, clock, stand, late)
    assert "error" not in out, out
    assert shown(imports, import_id)["status"] == "COMMITTED"
    assert len(commits) == 2 and commits[0] == stand.seen["started"] < commits[1], commits
    after = _stream(pending)
    assert (after["head"], after["events"]) == (before["head"] + 1, before["events"] + 1)
    event = _head_event(pending)
    assert (event["event_type"], str(event["import_upload_id"])) == ("PROGRESS_RECORDED", import_id)
    assert event["recorded_at"] == commits[1] > max(lock["created_at"], lock["cutoff_known_at"])
    (state,) = _rows(pending.world.tenant_id, select(job.c.state).where(job.c.id == job_id))
    assert str(getattr(state["state"], "value", state["state"])) == "SUCCEEDED"


@pytest.mark.parametrize(
    ("refusal", "commits", "told"),
    [
        # the pin's refusal both times: once more, then the commit's failure by the rule's sentence
        (problems.period_state_moved, 2, problems.PERIOD_STATE_MOVED_DETAIL + " "),
        # another refusal is the commit's failure at once: only the pin's is run again
        (lambda: problems.Problem("validation-failed", "Another refusal."), 1, ""),
    ],
    ids=["a period lock both times", "another refusal"],
)
def test_only_the_pins_refusal_is_run_again_and_a_second_one_fails_the_import_by_its_sentence(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    refusal: Callable[[], problems.Problem],
    commits: int,
    told: str,
) -> None:
    """05 §5.6 rev 1.195 (supervisor ruling R-122 (l): a policy retries only what another
    attempt can cure). PRD WLD-K-01 with an approved import of O2's progress. A commit that the
    pin refuses a second time ends the upload ``FAILED``, and its exception item says the rule's
    sentence before the reference; a commit refused for another reason is not run again.

    Fail-first: the commit ran once whatever refused it, and the item named no rule."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: journal runs and imports are hers
    clock.advance(timedelta(minutes=5))  # past the step Priya's sign-in spent (T-PLT-04)
    report, imports, import_id, job_id = _approved_import(
        world,
        clock,
        name=worlds.LATE_PROGRESS_FILE,
        rows=[(worlds.K01, "PROGRESS_RECORDED", "2026-01-31", "O2", "0.40", "OUTPUT_PERCENT")],
    )
    calls: list[UUID] = []

    def refused(_uow: Any, upload_id: UUID) -> Any:
        calls.append(upload_id)
        raise refusal()

    monkeypatch.setattr(import_commit, "commit_upload", refused)
    run_import_job(imports, job_id)
    assert calls == [UUID(import_id)] * commits
    assert shown(imports, import_id)["status"] == "FAILED"
    (item,) = _rows(
        report.tenant_id,
        select(exception_item.c.code, exception_item.c.message).where(
            exception_item.c.import_upload_id == UUID(import_id)
        ),
    )
    assert item["code"] == import_commit.FAILED_CODE
    assert item["message"] == told + import_commit.NOT_COMMITTED.format(reference=job_id)
    (state,) = _rows(report.tenant_id, select(job.c.state).where(job.c.id == job_id))
    assert str(getattr(state["state"], "value", state["state"])) == "SUCCEEDED_WITH_EXCEPTIONS"
