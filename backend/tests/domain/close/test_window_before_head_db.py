"""A transaction holds the rows of a window before it takes a ledger chain head, and under a head
it waits for none (finding F4 of the independent review of 2026-10-01; dev-guide DG-KRN-DB-08 (1c)
rev 1.218; 04 §14.1 DB-07 rev 1.229; 05 rev 1.169). PostgreSQL-bound.

``computation.persist`` reads the window — the state rows of the postable periods that have a
close run whose first period-end step is ``SUCCEEDED`` — ``FOR SHARE`` before its first write, and
a lock decision takes its period's row ``FOR UPDATE``. A command that posts BEFORE it computes
reached that read with the book's chain head held: the approval of a manual journal posts the
approved lines, then recomputes. While a lock decision held a window row the approval waited up to
``lock_timeout`` with the head, and every posting of the book in the workspace queued behind it.
A command that computes a SECOND group after the first one posted reached the second group's
window read the same way — a legacy import of progress or of modifications, which computes
contract by contract inside one job, and a combination's leave, which computes the contract that
left and then the remainder. A second read of rows the transaction shares waits for nothing, so
those commands waited only where the later group names an entity the earlier ones did not.

Worlds:

- PRD WLD-K-01 (``support.worlds.k01_pellworth``): AVM-US with ``SF-ORD-10001`` through September
  2026. AUGUST holds a ``SUCCEEDED`` close run (a fixture row, ``close_run_succeeded_for``) and is
  open, so its state row is the window's. A manual journal of SEPTEMBER — its two lines post into
  September, whose row nobody holds — is approved by Priya while a second session holds August's
  row ``FOR UPDATE``, as a lock decision of August does.
- PRD WLD-K-04 (``k04_saltmarsh``): ``SF-ORD-UK-2001``, contracted by AVM-UK, whose O1 AVM-US
  performs; April 2026 of AVM-US holds the ``SUCCEEDED`` run.
- PRD J-01 (``support.legacy_replay.legacy_world`` with the golden steps replayed): Contract 1
  and Contract 3 are Mock Entity 1's, Contract 2 and Contract 4 Mock Entity 2's, and a legacy
  import plans one contract after the other in ascending order — so the last plan of a file of
  both entities is Mock Entity 2's. January 2023 of Mock Entity 2 holds the ``SUCCEEDED`` run.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api import problems
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import locking
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    gl_account,
    ledger_chain_head,
    legal_entity,
    period_state,
)
from erev_api.domain.contracts import bundles, period_ends
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from support import golden_streams, worlds
from support.close_world import close_run_succeeded_for
from support.db import TestDatabase
from support.factories import booked_contract, computed, imported, open_periods, run_import_job
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.legacy_replay import LegacyWorld, job_of, legacy_world, replayed, shown, submit
from support.reference import approve, assign, entity, post
from support.worlds import (
    AUGUST_2026,
    AVM_UK,
    AVM_US,
    K01,
    SEPTEMBER_2026,
    ReportWorld,
    k01_pellworth,
)
from support.worlds import (
    period_state as shown_state,
)

ADJUSTMENTS: Final = "/api/v1/manual-adjustments"
BOOK: Final = "ASC606"
APRIL: Final = "FY2026-P04"
ENTITY_2: Final = "Mock Entity 2"
JANUARY_2023: Final = "FY2023-P01"
CA: Final = "AVM-CA"  # an entity on AVM-US's calendar
CA_CONTRACT: Final = "CA-ORD-0001"
GROUPS: Final = "/api/v1/combination-groups"
LOCK_NOT_AVAILABLE: Final = "55P03"
WAIT_SECONDS: Final = 30.0
JOIN_SECONDS: Final = 120.0
AT_ONCE_SECONDS: Final = 5.0  # the platform's lock_timeout is 10 s


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ReportWorld:
    built = k01_pellworth(app, keyring, clock, files)
    # PRD §5.6: ``adjustment.approve`` is the Revenue Reviewer's and the Controller's.
    assign(built.priya.member, "revenue_reviewer")
    return built


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files)


def _session(tenant_id: UUID, *entities: UUID) -> Any:
    scope: Any = entities or "*"
    return tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope=scope))


def _window(world: ReportWorld | LegacyWorld, entity_code: str, period_key: str) -> UUID:
    """A ``SUCCEEDED`` close run of the period, which stays open: its state row — the id returned
    — is now a row of a window. The window statement itself says so."""
    state = shown_state(world, entity_code, period_key)  # type: ignore[arg-type]
    state_id = UUID(str(state["id"]))
    clock = world.imports.clock if isinstance(world, LegacyWorld) else world.place.clock
    with _session(world.tenant_id) as session:
        close_run_succeeded_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )
    with _session(world.tenant_id) as session:
        rows = session.execute(period_ends._window_statement([entity_code])).scalars().all()
        session.rollback()
    assert [UUID(str(row)) for row in rows] == [state_id]
    return state_id


def _submitted_journal(world: ReportWorld) -> str:
    """Maya's manual journal of September on O1 — Dr contract liability 2100 / Cr revenue 4010,
    USD 2,400.00 — submitted; the id of its posting request."""
    accounts = {str(row["code"]): str(row["id"]) for row in world.place.rows(select(gl_account))}
    (obligation,) = [
        item for item in world.contracts[K01].obligations if item["obligation_key"] == "O1"
    ]
    body = {
        "kind": "MANUAL_JOURNAL",
        "contract_id": str(world.contracts[K01].contract["id"]),
        "effective_date": "2026-09-10",
        "reason_code": "DATA_CORRECTION",
        "memo": "Customer accepted phase 2 on 10 Sep 2026",
        "payload": {
            "obligation_id": str(obligation["id"]),
            "lines": [
                {
                    "account_role": "CONTRACT_LIABILITY",
                    "gl_account_id": accounts["2100"],
                    "amount_txn": {"amount": "2400.00", "currency": "USD"},
                },
                {
                    "account_role": "REVENUE",
                    "gl_account_id": accounts["4010"],
                    "amount_txn": {"amount": "-2400.00", "currency": "USD"},
                },
            ],
        },
    }
    created = post(world.app, ADJUSTMENTS, world.maya, body)
    assert created.status_code == 201, created.text
    assert created.json()["period"]["period_key"] == SEPTEMBER_2026
    submitted = post(world.app, f"{ADJUSTMENTS}/{created.json()['id']}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    return str(submitted.json()["approval_request_id"])


@contextmanager
def _statements() -> Iterator[list[str]]:
    """Every statement the application sends while the block runs, in order."""
    seen: list[str] = []

    def capture(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        seen.append(" ".join(statement.split()))

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", capture)


def _is_window_read(statement: str) -> bool:
    return "FOR SHARE OF period_state" in statement and "erev.close_run" in statement


def _takes_the_head(statement: str) -> bool:
    return "FROM erev.ledger_chain_head" in statement and statement.endswith("FOR UPDATE")


def _heads_are_free(tenant_id: UUID) -> bool | str:
    """Whether another session can take every ledger chain head of the workspace now, as a
    posting of any book does — the primary book's among them. A head that is held answers the
    SQLSTATE."""
    with _session(tenant_id) as other:
        try:
            taken = other.execute(
                select(ledger_chain_head.c.book_code).with_for_update(nowait=True)
            ).scalars()
            return BOOK in {str(getattr(code, "value", code)) for code in taken}
        except DBAPIError as error:
            return str(getattr(error.orig, "sqlstate", None))
        finally:
            other.rollback()


def _beside_a_lock_decision(
    tenant_id: UUID, state_id: UUID, command: Callable[[], Any], *, name: str
) -> Any:
    """``command`` run in a thread of its own while a second session holds the window row
    ``state_id`` ``FOR UPDATE``, as the lock decision of its period does. The command waits for
    the row — at a window read — and holds no ledger chain head meanwhile: another session takes
    every head of the workspace at once, as a posting of any other contract would. When the
    holder ends, the command completes. Returns what the command returned."""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["returned"] = command()
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    thread = threading.Thread(target=run, name=name)
    started = False
    with _session(tenant_id) as holder:
        try:
            held = holder.execute(
                select(period_state.c.state).where(period_state.c.id == state_id).with_for_update()
            ).scalar_one()
            assert str(getattr(held, "value", held)) == "open"
            with observing_checkouts() as backends:
                holder_pid = backend_pid(holder)
                thread.start()
                started = True
                blocked_pid, blocked_in = await_lock_wait(
                    holder,
                    holder_pid=holder_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="period_state",
                )
            assert blocked_pid != holder_pid and "for share" in blocked_in.lower(), blocked_in
            assert thread.is_alive() and not outcome, outcome
            assert _heads_are_free(tenant_id) is True
        finally:
            holder.rollback()
            if started:
                thread.join(timeout=JOIN_SECONDS)
    assert not thread.is_alive() and "error" not in outcome, outcome
    return outcome["returned"]


@pytest.mark.slow
def test_a_manual_journals_approval_reads_the_window_before_it_takes_the_chain_head(
    world: ReportWorld,
) -> None:
    """The order, recorded from the statements of Priya's real approval: the window read stands
    before the first ``ledger_chain_head … FOR UPDATE``, and the adjustment is posted. And the
    posting marks its transaction (``subledger.post``): the window read the recomputation makes
    after the head — its rows are held by then — is the one that does not wait.

    Fail-first: the first window read came after the head — the manual posting took the head
    and the recomputation's ``persist`` then read the window, in the form that waits."""
    _window(world, AVM_US, AUGUST_2026)
    request_id = _submitted_journal(world)
    with _statements() as seen:
        decided = approve(world.app, request_id, world.priya)
    assert decided.status_code == 200, decided.text
    windows = [index for index, text in enumerate(seen) if _is_window_read(text)]
    heads = [index for index, text in enumerate(seen) if _takes_the_head(text)]
    assert windows and heads, (len(seen), windows, heads)
    assert windows[0] < heads[0], (windows, heads)
    waits = {index: not seen[index].endswith("NOWAIT") for index in windows}
    assert waits[windows[0]] is True  # with no head held the read waits for a lock decision
    under_the_head = [waits[index] for index in windows if index > heads[0]]
    assert under_the_head and not any(under_the_head), (windows, heads, waits)


@pytest.mark.slow
def test_a_manual_journals_approval_waits_for_a_lock_decision_without_the_chain_head(
    world: ReportWorld,
) -> None:
    """A second session holds August's state row ``FOR UPDATE``, as the lock decision of August
    does. Priya's approval of September's manual journal waits for it — at the window read — and
    holds no chain head meanwhile: another session takes the book's head at once, as a posting
    of any other contract would. When the holder ends, the approval completes.

    Fail-first: the approval had posted its two lines and held the head while it waited; the
    other session's read of the head answered SQLSTATE 55P03."""
    august = _window(world, AVM_US, AUGUST_2026)
    request_id = _submitted_journal(world)
    decided = _beside_a_lock_decision(
        world.tenant_id,
        august,
        lambda: approve(world.app, request_id, world.priya),
        name="adjustment-approval",
    )
    assert decided.status_code == 200, decided.text


@pytest.mark.slow
def test_under_a_chain_head_a_held_window_row_ends_the_read_at_once(world: ReportWorld) -> None:
    """The backstop, for a path nobody listed: a transaction that holds a ledger chain head and
    then comes to a window read does not wait for a row a lock decision holds. The read ends at
    once and is refused by its own name — 409 ``lock-conflict`` under rule
    ``PERIOD_LOCK_IN_FLIGHT`` with the sentence of PRD ERR-98, not the sentence of a wait that
    ran out — where the same read without the head waits (the witness above). The read ran in a
    savepoint: the transaction can still answer.

    Fail-first: the read waited for the holder, up to ``lock_timeout``, with the head held."""
    august = _window(world, AVM_US, AUGUST_2026)
    group_id = UUID(str(world.contracts[K01].combination_group["id"]))
    with world.place.uow() as uow, _session(world.tenant_id) as holder:
        try:
            holder.execute(
                select(period_state.c.state).where(period_state.c.id == august).with_for_update()
            ).scalar_one()
            uow.session.execute(
                select(ledger_chain_head.c.book_code)
                .where(ledger_chain_head.c.book_code == BOOK)
                .with_for_update()
            ).scalar_one()
            locking.mark_chain_head(uow.session)  # what ``subledger.post`` does with the head
            began = time.monotonic()
            with pytest.raises(problems.Problem) as refused:
                period_ends.hold_windows(uow, [group_id])
            waited = time.monotonic() - began
            usable = uow.session.execute(select(period_state.c.id).limit(1)).first() is not None
        finally:
            holder.rollback()
    assert waited < AT_ONCE_SECONDS, waited
    answered = refused.value
    assert (answered.status, answered.slug) == (409, "lock-conflict")
    assert answered.detail == problems.PERIOD_LOCK_IN_FLIGHT_DETAIL
    assert answered.detail == (
        "A period of this contract is being locked. Nothing was saved. Send it again."
    )
    assert [(error.rule_id, error.message) for error in answered.errors] == [
        ("PERIOD_LOCK_IN_FLIGHT", answered.detail)
    ]
    assert isinstance(answered.__cause__, DBAPIError)
    assert getattr(answered.__cause__.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE
    assert usable is True


@pytest.mark.slow
def test_the_window_rows_of_a_performing_entity_are_held_whoever_asks(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``hold_windows`` reads the entities a bundle of the group names and holds their windows
    under the tenant's scope. ``SF-ORD-UK-2001`` is contracted by AVM-UK and AVM-US performs its
    O1: the entities read from the stream are those of the group's bundle, both. A transaction
    whose scope is AVM-UK alone — a person of one entity, an import narrowed to its uploader —
    then holds the window row of AVM-US: another session's ``FOR UPDATE NOWAIT`` on it, which is
    what a lock decision of April for AVM-US asks, is refused while that transaction is open and
    taken once it has ended; and the transaction's own scope is what it was."""
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = k04.report
    april = _window(world, AVM_US, APRIL)
    with _session(world.tenant_id) as session:
        named = bundles.entity_codes(session, [k04.group_id])
        bundle = bundles.build(session, k04.group_id, world.place.clock.now())
    assert named == sorted(entity.code for entity in bundle.entities) == [AVM_UK, AVM_US]

    def asked_for_update() -> bool | str:
        with _session(world.tenant_id) as decision:
            try:
                decision.execute(
                    select(period_state.c.id)
                    .where(period_state.c.id == april)
                    .with_for_update(nowait=True)
                ).scalar_one()
                return True
            except DBAPIError as error:
                return str(getattr(error.orig, "sqlstate", None))
            finally:
                decision.rollback()

    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope=(k04.uk_entity_id,))
    with tenant_session(context) as narrow:
        uow: Any = SimpleNamespace(session=narrow, principal=SimpleNamespace(db_context=context))
        own = select(period_state.c.id).where(period_state.c.id == april)
        assert narrow.execute(own).first() is None  # AVM-US's row is outside this scope
        period_ends.hold_windows(uow, [k04.group_id])
        assert narrow.execute(own).first() is None  # and still is: the scope was given back
        assert asked_for_update() == LOCK_NOT_AVAILABLE
        narrow.rollback()
    assert asked_for_update() is True


def _golden_upload(number: str) -> tuple[str, bytes, str, dict[str, Any] | None]:
    """The golden step ``number`` as an upload — file name, bytes, template and parameters, as
    ``legacy_replay.replayed`` sends them."""
    step = golden_streams.steps(number)[-1]
    assert step.number == number
    parameters: dict[str, Any] = {}
    if step.date_input is not None:
        parameters["effective_date"] = step.date_input.isoformat()
    if step.mode is not None:
        parameters["mode"] = step.mode
    return step.workbook.name, step.workbook.read_bytes(), step.template_code, parameters or None


@pytest.mark.slow
@pytest.mark.parametrize(
    ("through", "number", "template"),
    [
        # progress of 31 Jan 2023: Contract 1 (Mock Entity 1), then Contract 2 (Mock Entity 2)
        ("03", "04", "legacy_progress_tracking"),
        # modifications of 15 Jul 2023: Contract 3 (Mock Entity 1), then Contract 4 (Mock Entity 2)
        ("10", "11", "legacy_contract_modification"),
    ],
    ids=["progress", "modifications"],
)
def test_a_legacy_import_of_two_entities_waits_for_a_lock_decision_without_the_chain_head(
    legacy: LegacyWorld, through: str, number: str, template: str
) -> None:
    """A legacy import that computes contract by contract (``CsvTemplate.computes``) holds the
    windows of every contract its file names before its first plan runs — in the comparison's dry
    run and in the commit (``imports.diff.hold_plan_windows``). The file names a contract of Mock
    Entity 1 and then one of Mock Entity 2, whose January holds a ``SUCCEEDED`` run; a second
    session holds that row ``FOR UPDATE``, as the lock decision of January does. Each of the two
    jobs waits for the row at a window read and holds no chain head meanwhile; when the holder
    ends the job completes — the comparison is ready, the import committed.

    Fail-first: the job computed and posted the first contract, which took the head, and came to
    the row at the second contract's window read: it waited with the head held, and the other
    session's read of the heads answered SQLSTATE 55P03."""
    replayed(legacy, through)
    name, content, code, parameters = _golden_upload(number)
    assert code == template
    imports = legacy.imports
    import_id, validated = imported(imports, name, content, code, parameters)
    assert validated["status"] == "VALIDATED", validated
    january = _window(legacy, ENTITY_2, JANUARY_2023)
    compare = job_of(imports, UUID(import_id), "IMPORT_DIFF")
    _beside_a_lock_decision(
        legacy.tenant_id, january, lambda: run_import_job(imports, compare), name="import-diff"
    )
    ready = shown(imports, import_id)
    assert ready["status"] == "DIFF_READY", ready
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert decided.status_code == 200, decided.text
    commit = job_of(imports, UUID(import_id), "IMPORT_COMMIT")
    _beside_a_lock_decision(
        legacy.tenant_id, january, lambda: run_import_job(imports, commit), name="import-commit"
    )
    done = shown(imports, import_id)
    assert done["status"] == "COMMITTED", done


def _combined_with_a_contract_of_another_entity(world: ReportWorld) -> tuple[UUID, UUID]:
    """AVM-CA on AVM-US's calendar with January to September 2026 open, and under it
    ``CA-ORD-0001`` — the lines of ``SF-ORD-10001`` with O1 at 96,000.00, so that the two
    contracts are discounted differently and a combination moves what each is allocated —
    activated and computed; then the two contracts combined by Maya's proposal and Marcus's
    approval. Returns the id of ``SF-ORD-10001`` and the group's."""
    app, maya = world.app, world.maya
    calendar_id = world.place.scalar(
        select(legal_entity.c.calendar_id).where(legal_entity.c.code == AVM_US)
    )
    entity(app, maya, code=CA, calendar_id=str(calendar_id))
    open_periods(app, maya, entity_code=CA, keys=[f"FY2026-P{month:02d}" for month in range(1, 10)])
    first = world.contracts[K01].contract
    body = worlds.k01_body(UUID(str(first["customer_id"])))
    lines = [dict(line) for line in body["lines"]]
    lines[0]["total_price"] = {"amount": "96000.00", "currency": "USD"}
    booked = booked_contract(
        world.place,
        {**body, "external_id": CA_CONTRACT, "contracting_entity_code": CA, "lines": lines},
        activate=True,
    )
    computed(world.place, UUID(str(booked.combination_group["id"])))
    proposed = post(
        app,
        GROUPS,
        maya,
        {
            "contract_ids": [str(first["id"]), str(booked.contract["id"])],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(str(proposed.json()["id"]))
    submitted = post(app, f"{GROUPS}/{group_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    joined = approve(app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert joined.status_code == 200, joined.text
    return UUID(str(first["id"])), group_id


@pytest.mark.slow
def test_a_leave_across_two_entities_waits_for_a_lock_decision_without_the_chain_head(
    world: ReportWorld,
) -> None:
    """``SF-ORD-10001`` (AVM-US) and ``CA-ORD-0001`` (AVM-CA) are one combination group, and
    ``SF-ORD-10001`` leaves it by an approved correction. The leave computes the contract that
    left, then the remainder — ``CA-ORD-0001``, of AVM-CA, whose August holds a ``SUCCEEDED``
    run; a second session holds that row ``FOR UPDATE``, as the lock decision of August does.
    Marcus's approval of the leave waits for the row at a window read and holds no chain head
    meanwhile; when the holder ends, the leave is applied.

    Fail-first: the approval had computed and posted ``SF-ORD-10001`` alone — the head taken —
    and waited for the row at the remainder's window read with the head held."""
    left, group_id = _combined_with_a_contract_of_another_entity(world)
    august = _window(world, CA, AUGUST_2026)
    requested = post(
        world.app,
        f"{GROUPS}/{group_id}/submit",
        world.maya,
        {
            "leave_contract_ids": [str(left)],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-10001 was combined with the wrong order.",
        },
    )
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    decided = _beside_a_lock_decision(
        world.tenant_id,
        august,
        lambda: approve(world.app, request_id, world.marcus),
        name="leave-approval",
    )
    assert decided.status_code == 200, decided.text
    now_in = world.place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == left)
    )
    assert UUID(str(now_in)) != group_id  # the leave was applied: a group of its own
