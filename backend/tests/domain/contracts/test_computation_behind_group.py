"""A computation whose bundle is behind its group is not stored (item COMPUTE-BEHIND-GROUP-1; the
supervisor's rulings of 2026-10-02; 04 §14.1 "A computation behind its group" rev 1.298; 05
RCP-17, RCP-20 and RCP-22 rev 1.207; dev-guide DG-CMD-09 and DG-CMD-10 rev 1.282; PRD ERR-52).

A bundle admits what was recorded by its cutoff — the later of the application instant and the
transaction timestamp, both fixed when its unit of work and its transaction began — and reads
``posted``, the previous version and the period states as committed when it is built. Measured
before the item, in the world of ``test_fx_remeasurement_recompute.py``: a computation that began
before a second delivery was recorded and persisted after it posted the delivery's revenue back
out (USD 18,000.00), became the head and left the group clean; one that began before the approval
of a rate version ended the mark of a version it had not read; and one that persisted after
another computation had posted that version's difference posted the difference back out.

Every case here has the same shape. A computation BEGINS: its unit of work and its transaction
(``_begun``). Something then happens to its group and commits. The computation is then built and
persisted — and is refused 409 ``lock-conflict`` with the sentence of PRD ERR-52, by the way
``computation.behind_its_group`` names: ``event`` (a member's event beyond the bundle's stream
head), ``mark`` (``dirty_since`` later than the cutoff) or ``head`` (the group's head computation
made after the cutoff). What stands afterwards is what the other transaction left, and a
computation begun afterwards is stored.

Two clocks decide (dev-guide DG-TST-14). An event carries the DATABASE's clock — the start of the
transaction that recorded it — so the ``event`` case stands on the frozen clock of the world: it
lies behind the server's present, the cutoff is the transaction timestamp, and the later
transaction's event is after it by construction. A mark carries the APPLICATION's clock, and so
did a head until item COMPUTE-BEHIND-CUTOFF-1 (04 rev 1.302): their cases stand on the record
clock (``_on_record_clock``: the frozen clock moved onto the server's present) and move it on
before the writer acts, as time does. A head now carries the cutoff its computation admitted by —
the later of the two clocks — so on the frozen clock, too, a computation the other transaction
stored is a head this bundle is behind: where its event was computed in its own transaction the
ways are ``event`` and ``head``. Where a case needs both —
an event that is not admitted AND a mark that is later — the application clock stands ON the
server's present, not a second ahead of it (``_on_servers_present``). So does the
combination's case (``_seats_on_servers_present``): its member's event and the end of its
membership are on the database's clock, and that no mark and no head is later is read on the
application's. A second ahead, a computation begun within that second has the application's
instant for its cutoff, and a combination approved before the server's clock has reached it
ended the membership at or before the cutoff: the group the contract left has no member
there, and no bundle of it is built (the first-pass red of 2026-10-03, measured).

Each refusal is logged once, as ``contract.computation_behind_group`` with its ways in
``behind_codes``: the line an operator counts (``_logged``).
"""

from __future__ import annotations

import dataclasses
import io
import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api import problems
from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    combination_group,
    contract,
    contract_computation,
    contract_event,
    exception_item,
    fx_rate_set,
    idempotency_record,
    period,
    subledger_line,
)
from erev_api.domain.contracts import bundles, computation, compute_job, repo
from erev_api.enums import ComputationStatus, ComputationTrigger, ContractEventType
from erev_api.events.payloads import LATEST_SCHEMA_VERSION, PAYLOADS
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import LOCK_CONFLICT_DETAIL, Problem
from erev_api.uow import UnitOfWork
from erev_engine.errors import EngineError
from fastapi import FastAPI
from sqlalchemy import and_, func, select, update
from support.db import TestDatabase
from support.factories import (
    GATEWAY,
    STEP1_CHART,
    SeatWorld,
    Workspace,
    activated_contract,
    booked_contract,
    k09_body,
    open_periods,
    seat_world,
)
from support.http import HttpResponse, call
from support.principals import Actor, cookie_headers, sign_in, workspace
from support.reference import APPROVALS, approve, get, post, slug
from support.worlds import approved_manual_events
from test_combination import BILLING, GROUPS, _active, _combine
from test_fx_remeasurement_recompute import (
    ENTITY,
    USD_GBP,
    _invoice,
    _published_version,
    delivered,
)
from test_fx_remeasurement_recompute import World as FxWorld
from test_fx_remeasurement_recompute import world as fx  # noqa: F401  (the FX world's fixture)
from test_step1 import _record

EVENTS = "/api/v1/contracts/{contract_id}/events"
JOIN_SECONDS = 180
POLICY_OVERRIDES = "/api/v1/policy-overrides"
SECOND_DELIVERY = {
    "event_type": "DELIVERY_RECORDED",
    "effective_date": "2026-08-12",
    "payload": {"obligation_key": "O1", "quantity": "40", "trigger": "DELIVERY"},
}
JULY_CORRECTED = [
    {**USD_GBP, "rate": "0.820000", "period_key": "FY2026-P07"},
    {**USD_GBP, "rate": "0.830000", "period_key": "FY2026-P08"},
    {**USD_GBP, "rate": "0.835000", "period_key": "FY2026-P09"},
]
# The world's own rates with October's beside them, for the case that opens FY2026-P10.
AVERAGE_TO_OCTOBER = [
    {**USD_GBP, "rate": "0.810000", "period_key": "FY2026-P07"},
    {**USD_GBP, "rate": "0.830000", "period_key": "FY2026-P08"},
    {**USD_GBP, "rate": "0.835000", "period_key": "FY2026-P09"},
    {**USD_GBP, "rate": "0.840000", "period_key": "FY2026-P10"},
]
CLOSING_TO_OCTOBER = [
    {**USD_GBP, "rate": "0.820000", "period_key": "FY2026-P07"},
    {**USD_GBP, "rate": "0.850000", "period_key": "FY2026-P08"},
    {**USD_GBP, "rate": "0.860000", "period_key": "FY2026-P09"},
    {**USD_GBP, "rate": "0.870000", "period_key": "FY2026-P10"},
]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> SeatWorld:
    """The seat world of ``test_step1.py`` and ``test_combination.py`` (PRD WLD-K-09)."""
    return seat_world(
        app, keyring, clock, LocalFileStore(app_settings.file_root), chart=STEP1_CHART
    )


# --- the shape of every case ---------------------------------------------------------------------


@contextmanager
def _begun(place: Workspace) -> Iterator[UnitOfWork]:
    """A computation that has BEGUN: its unit of work, and its transaction — both instants its
    cutoff is the later of are fixed (``bundles.record_cutoff``). Left without a commit, it is
    discarded."""
    with place.uow() as uow:
        uow.session.execute(select(func.transaction_timestamp())).scalar_one()
        yield uow


def _behind(uow: UnitOfWork, group_id: UUID) -> tuple[str, ...]:
    """The ways the bundle ``uow`` builds now is behind its group."""
    with uow.as_system():
        bundle = bundles.build(uow.session, group_id, uow.now, (), ComputationTrigger.COMMAND)
        return computation.behind_its_group(uow, bundle, bundles.index(uow.session, bundle))


def _refused(act: Callable[[], object]) -> None:
    """``act`` ends 409 ``lock-conflict`` with the sentence of PRD ERR-52 and no rule."""
    with pytest.raises(Problem) as caught:
        act()
    refused = caught.value
    assert (refused.slug, refused.detail, tuple(refused.errors)) == (
        "lock-conflict",
        LOCK_CONFLICT_DETAIL,
        (),
    )
    assert problems.is_lock_conflict(refused)


def _logged(stream: io.StringIO) -> list[tuple[str, tuple[str, ...], str]]:
    """(group, ways, trigger) of every refusal the product logged: one
    ``contract.computation_behind_group`` line each, with the ways in ``behind_codes``."""
    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    return [
        (str(line["combination_group_id"]), tuple(line["behind_codes"]), str(line["trigger_code"]))
        for line in lines
        if line["event"] == "contract.computation_behind_group"
    ]


def _ledger(place: Workspace, contract_id: UUID) -> list[tuple[str, str, Decimal, Decimal]]:
    """(period, account role, transaction amount, functional amount) of every sealed line."""
    rows = place.rows(
        select(
            period.c.period_key,
            subledger_line.c.account_role,
            subledger_line.c.amount_txn,
            subledger_line.c.amount_functional,
        )
        .select_from(
            subledger_line.join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
        )
        .where(subledger_line.c.contract_id == contract_id)
    )
    return sorted(
        (
            str(row["period_key"]),
            str(row["account_role"]),
            Decimal(row["amount_txn"]),
            Decimal(row["amount_functional"]),
        )
        for row in rows
    )


def _state(place: Workspace, group_id: UUID, contract_id: UUID) -> dict[str, Any]:
    """How the group stands: its head, its mark, its member's stream head and what is stored of
    it — computations by status, and exception items."""
    (group,) = place.rows(
        select(combination_group.c.head_computation_id, combination_group.c.dirty_since).where(
            combination_group.c.id == group_id
        )
    )
    statuses = place.rows(
        select(contract_computation.c.status).where(
            contract_computation.c.combination_group_id == group_id
        )
    )
    return {
        "head": group["head_computation_id"],
        "dirty_since": group["dirty_since"],
        "stream": int(
            place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
        ),
        "computations": sorted(
            str(getattr(row["status"], "value", row["status"])) for row in statuses
        ),
        "items": int(
            place.scalar(
                select(func.count())
                .select_from(exception_item)
                .where(exception_item.c.combination_group_id == group_id)
            )
        ),
    }


def _resigned(world: FxWorld, actor: Actor) -> Actor:
    """A fresh session of ``actor`` at the clock as it stands: a jump of days ends every session
    at its absolute limit."""
    return workspace(world.app, actor.member, sign_in(world.app, actor.member.email), actor.secret)


def _on_record_clock(world: FxWorld) -> tuple[Actor, Actor]:
    """The world's frozen clock moved onto the server's present — one second after
    ``clock_timestamp()``, never backwards — where a production request's would be, with fresh
    sessions of Maya and Marcus (``support.record_clock.on_record_time`` does the same for a
    report world)."""
    clock = world.place.clock
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(max(clock.now(), stamp + timedelta(seconds=1)))
    return _resigned(world, world.maya), _resigned(world, world.marcus)


def _on_servers_present(place: Workspace) -> None:
    """The application clock ON the server's present — not a second ahead of it, where
    ``_on_record_clock`` puts it. The cutoff of a unit of work begun now is its transaction's
    start, so an event another transaction records afterwards lies after it by construction,
    while a mark set a minute later on the application's clock is later than it as well."""
    stamp = place.scalar(select(func.clock_timestamp()))
    place.clock.set(max(place.clock.now(), stamp))


def _time_passes(place: Workspace) -> None:
    """A minute on the application clock: whoever acts next began after the computation did."""
    place.clock.set(place.clock.now() + timedelta(minutes=1))


def _marked_by_hand(world: FxWorld, group_id: UUID) -> Any:
    """A mark set by hand: ``dirty_since`` at the application's instant, in a transaction of
    its own, and no trigger — the stamp alone, whoever the marker. Until item
    FX-REPUBLISH-DIRTY-1 it also stood in for the mark of a rate version's approval; the
    approval sets that mark itself now, with its trigger (``close.rate_reach.marked``), and
    the cases about it rest on that mark."""
    instant = world.place.clock.now()
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(combination_group)
            .where(combination_group.c.id == group_id)
            .values(dirty_since=instant, row_version=combination_group.c.row_version + 1)
        )
    return instant


def _computed_now(place: Workspace, group_id: UUID) -> compute_job.GroupComputation:
    """A computation that begins now, as the close run's ``RECOMPUTE_DIRTY`` issues it."""
    with place.uow() as uow:
        outcome = compute_job.compute_group(uow, group_id, trigger=ComputationTrigger.COMMAND)
        uow.commit()
    return outcome


# --- (i) an event of a member beyond the bundle's stream head -------------------------------------


def test_a_computation_begun_before_a_later_event_is_not_stored(
    fx: FxWorld,  # noqa: F811
    log_stream: io.StringIO,
) -> None:
    """The measured case. ``NS-SO-UK-7001``: 120 units delivered on 10 July and computed, stream
    head 3. A computation begins. The product then records and computes a second delivery — 40
    units on 12 August, USD 18,000.00 at the August average 0.83, GBP 14,940.00 — and commits. The
    first computation is built now: the delivery's event lies after its cutoff, the delivery's
    lines are in its ``posted``, and target minus posted is the delivery's reversal.

    It is refused before it writes: no line of the delivery is reversed, the delivery's
    computation is still the head, the group is clean, nothing is stored of the refused one. A
    computation begun afterwards reads the delivery and posts nothing."""
    contract_id, group_id = delivered(fx)
    before = _ledger(fx.place, contract_id)
    with _begun(fx.place) as late:
        recorded = approved_manual_events(
            fx.place, fx.priya, contract_id, SECOND_DELIVERY, evidence_file_ids=[]
        )
        assert recorded["computation"]["status"] == "SUCCEEDED"
        after_event = _ledger(fx.place, contract_id)
        assert [line for line in after_event if line not in before] == [
            ("FY2026-P08", "CONTRACT_LIABILITY", Decimal("18000.0000"), Decimal("14940.0000")),
            ("FY2026-P08", "REVENUE", Decimal("-18000.0000"), Decimal("-14940.0000")),
        ]
        stood = _state(fx.place, group_id, contract_id)
        assert (stood["stream"], stood["dirty_since"]) == (4, None)
        # The event, and the head: the delivery's own computation admitted by a later cutoff.
        assert _behind(late, group_id) == (computation.BEHIND_EVENT, computation.BEHIND_HEAD)
        _refused(lambda: computation.recompute(late, group_id))
    assert _ledger(fx.place, contract_id) == after_event
    assert _state(fx.place, group_id, contract_id) == stood
    assert _logged(log_stream) == [
        (str(group_id), (computation.BEHIND_EVENT, computation.BEHIND_HEAD), "COMMAND")
    ]
    again = _computed_now(fx.place, group_id)
    assert again.status is ComputationStatus.SUCCEEDED
    assert _ledger(fx.place, contract_id) == after_event
    assert _state(fx.place, group_id, contract_id)["dirty_since"] is None


def _second_delivery() -> EventIn:
    kind = ContractEventType.DELIVERY_RECORDED
    payload = PAYLOADS[(kind, LATEST_SCHEMA_VERSION[kind])].model_validate(
        SECOND_DELIVERY["payload"]
    )
    return EventIn(kind, date(2026, 8, 12), payload, obligation_keys=("O1",))


def test_an_event_appended_after_the_cutoff_and_not_yet_computed_refuses_the_computation(
    fx: FxWorld,  # noqa: F811
    log_stream: io.StringIO,
) -> None:
    """The event append as a writer of the mark (``events.stream``): an event recorded in a
    transaction of its own whose computation is still to come — an import's commit, a command
    beyond the engine's budget. A computation that began before it is behind in both ways an
    appended event shows: the member's stream head is beyond the bundle's, and the append's mark
    is later than the cutoff. Refused, it leaves the mark, and the computation begun afterwards
    reads the delivery, posts it — USD 18,000.00 at 0.83, GBP 14,940.00 — and ends the mark."""
    contract_id, group_id = delivered(fx)
    _on_servers_present(fx.place)
    before = _ledger(fx.place, contract_id)
    head = _state(fx.place, group_id, contract_id)["head"]
    with _begun(fx.place) as late:
        _time_passes(fx.place)
        with fx.place.uow() as appender:
            append_events(
                appender,
                contract_id=contract_id,
                expected_stream_version=3,
                events=[_second_delivery()],
                origin="API",
            )
            appender.commit()
        marked = _state(fx.place, group_id, contract_id)
        assert (marked["stream"], marked["dirty_since"]) == (4, fx.place.clock.now())
        assert _behind(late, group_id) == (computation.BEHIND_EVENT, computation.BEHIND_MARK)
        _refused(lambda: computation.recompute(late, group_id))
    assert _state(fx.place, group_id, contract_id) == marked
    assert (marked["head"], _ledger(fx.place, contract_id)) == (head, before)
    assert _logged(log_stream) == [
        (str(group_id), (computation.BEHIND_EVENT, computation.BEHIND_MARK), "COMMAND")
    ]
    assert _computed_now(fx.place, group_id).status is ComputationStatus.SUCCEEDED
    assert _state(fx.place, group_id, contract_id)["dirty_since"] is None
    assert [line for line in _ledger(fx.place, contract_id) if line not in before] == [
        ("FY2026-P08", "CONTRACT_LIABILITY", Decimal("18000.0000"), Decimal("14940.0000")),
        ("FY2026-P08", "REVENUE", Decimal("-18000.0000"), Decimal("-14940.0000")),
    ]


# --- (ii) a mark later than the cutoff ------------------------------------------------------------


def _override_approved(world: FxWorld, maya: Actor, marcus: Actor, contract_id: UUID) -> None:
    """Create and independently approve a supported conditional-right override.

    The gateway already uses conditional consideration, so this changes no amount. Its
    approval still marks the group, which is the concurrency behavior under test.
    """
    created = post(
        world.app,
        POLICY_OVERRIDES,
        maya,
        {
            "contract_id": str(contract_id),
            "policy_key": "balance.right_to_consideration",
            "value": "CONDITIONAL",
            "obligation_key": "O1",
            "rationale": "The reviewed order retains a conditional right before invoicing.",
        },
    )
    assert created.status_code == 201, created.text
    override_id = created.json()["id"]
    submitted = post(
        world.app, f"{POLICY_OVERRIDES}/{override_id}/submit", maya, {"comment": "Ready"}
    )
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, str(submitted.json()["approval_request_id"]), marcus)
    assert approved.status_code == 200, approved.text


def _mark_refuses_and_its_repetition_clears(
    world: FxWorld, contract_id: UUID, group_id: UUID, write: Callable[[], None]
) -> None:
    """A computation begins; ``write`` marks its group at a later instant and commits; the
    computation is refused by the mark alone, which stands; a computation begun afterwards is
    stored and ends it."""
    ledger = _ledger(world.place, contract_id)
    head = _state(world.place, group_id, contract_id)["head"]
    with _begun(world.place) as late:
        _time_passes(world.place)
        write()
        marked = _state(world.place, group_id, contract_id)
        assert marked["dirty_since"] == world.place.clock.now()
        assert marked["dirty_since"] > late.now
        assert _behind(late, group_id) == (computation.BEHIND_MARK,)
        _refused(lambda: computation.recompute(late, group_id))
    assert _state(world.place, group_id, contract_id) == marked
    assert (marked["head"], _ledger(world.place, contract_id)) == (head, ledger)
    assert _computed_now(world.place, group_id).status is ComputationStatus.SUCCEEDED
    assert _state(world.place, group_id, contract_id)["dirty_since"] is None


def test_an_override_approved_after_the_cutoff_refuses_the_computation(fx: FxWorld) -> None:  # noqa: F811
    """The approval of a policy override marks the group and computes nothing (05 RCP-17). A
    computation that began before the approval admits no override approved after its cutoff:
    stored, it would end the mark of an override it had not read."""
    contract_id, group_id = delivered(fx)
    ledger = _ledger(fx.place, contract_id)
    maya, marcus = _on_record_clock(fx)
    _mark_refuses_and_its_repetition_clears(
        fx, contract_id, group_id, lambda: _override_approved(fx, maya, marcus, contract_id)
    )
    assert _ledger(fx.place, contract_id) == ledger


def test_a_period_opened_after_the_cutoff_refuses_the_computation_once(fx: FxWorld) -> None:  # noqa: F811
    """The one refusal the rule makes where nothing would have been lost (04 §14.1). The opening
    of FY2026-P10 marks the group (SCH-06). A computation that began before the opening and is
    built after it has READ the opened period — period states are read as committed — and is
    refused all the same, by the opening's mark; its repetition passes.

    October's rates are published first: the replay then reaches the opened period's end, and
    without its rates nothing is posted (ENGINE_SPEC S12-R-01)."""
    contract_id, group_id = delivered(fx)
    average_id = fx.place.scalar(
        select(fx_rate_set.c.id).where(fx_rate_set.c.code == "AVM-UK-AVERAGE")
    )
    for set_id, rates in (
        (str(average_id), AVERAGE_TO_OCTOBER),
        (fx.closing_set_id, CLOSING_TO_OCTOBER),
    ):
        _published_version(
            fx.app, fx.maya, fx.marcus, set_id, rates, coverage=("2026-07-01", "2026-10-31")
        )
    maya, _ = _on_record_clock(fx)
    _mark_refuses_and_its_repetition_clears(
        fx,
        contract_id,
        group_id,
        lambda: open_periods(fx.app, maya, entity_code=ENTITY, keys=["FY2026-P10"]),
    )
    with fx.place.uow() as uow, uow.as_system():
        bundle = bundles.build(uow.session, group_id, uow.now, (), ComputationTrigger.COMMAND)
    (entity,) = bundle.entities
    states = {item.period_key: dict(item.states) for item in entity.periods}
    assert states["FY2026-P10"]["ASC606"] == "open"


def test_a_rate_mark_set_after_the_cutoff_refuses_the_computation(
    fx: FxWorld,  # noqa: F811
    log_stream: io.StringIO,
) -> None:
    """The mark the approval of an FX rate set version sets (item FX-REPUBLISH-DIRTY-1,
    ``close.rate_reach.marked``; until that item this case set it by hand): at the version's
    instant, with the trigger ``FX_REPUBLISH``. A computation that began before the approval
    does not admit the version (``published_at`` is later than its cutoff): it posts nothing,
    and stored it would end the mark. It is refused — its bundle brings no event and so is
    built under the trigger the mark carries (05 RCP-17), the trigger its refusal is logged
    with — and leaves the mark to the computation begun afterwards, which posts the
    difference: USD 54,000.00 at 0.82 instead of 0.81, GBP 540.00."""
    contract_id, group_id = delivered(fx)
    maya, marcus = _on_record_clock(fx)
    before = _ledger(fx.place, contract_id)
    set_id = fx.place.scalar(select(fx_rate_set.c.id).where(fx_rate_set.c.code == "AVM-UK-AVERAGE"))

    def approved() -> None:
        _published_version(fx.app, maya, marcus, str(set_id), JULY_CORRECTED)

    _mark_refuses_and_its_repetition_clears(fx, contract_id, group_id, approved)
    assert _logged(log_stream) == [(str(group_id), (computation.BEHIND_MARK,), "FX_REPUBLISH")]
    assert [line for line in _ledger(fx.place, contract_id) if line not in before] == [
        ("FY2026-P07", "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("540.0000")),
        ("FY2026-P07", "REVENUE", Decimal("0.0000"), Decimal("-540.0000")),
    ]


# --- (iii) a head computation made after the cutoff -----------------------------------------------


def test_a_head_made_after_the_cutoff_refuses_the_computation(
    fx: FxWorld,  # noqa: F811
    log_stream: io.StringIO,
) -> None:
    """The case the first two ways do not see. A computation begins. A rate version is approved
    and ANOTHER computation, begun after the approval, posts its difference (GBP 540.00) and is
    the head; no mark stands and no event was appended. The first computation, built now on the
    rates of its own cutoff over a ledger that holds the difference, would post the 540.00 back
    out. It is refused by the head alone."""
    contract_id, group_id = delivered(fx)
    maya, marcus = _on_record_clock(fx)
    set_id = fx.place.scalar(select(fx_rate_set.c.id).where(fx_rate_set.c.code == "AVM-UK-AVERAGE"))
    with _begun(fx.place) as late:
        _time_passes(fx.place)
        _published_version(fx.app, maya, marcus, str(set_id), JULY_CORRECTED)
        assert _computed_now(fx.place, group_id).status is ComputationStatus.SUCCEEDED
        corrected = _ledger(fx.place, contract_id)
        assert ("FY2026-P07", "REVENUE", Decimal("0.0000"), Decimal("-540.0000")) in corrected
        stood = _state(fx.place, group_id, contract_id)
        assert stood["dirty_since"] is None
        assert _behind(late, group_id) == (computation.BEHIND_HEAD,)
        _refused(lambda: computation.recompute(late, group_id))
    assert _ledger(fx.place, contract_id) == corrected
    assert _state(fx.place, group_id, contract_id) == stood
    assert _logged(log_stream) == [(str(group_id), (computation.BEHIND_HEAD,), "COMMAND")]


def _seats_resigned(world: SeatWorld) -> SeatWorld:
    """Fresh sessions of the seat world's three people at the clock as it stands
    (``_resigned``)."""

    def fresh(actor: Actor) -> Actor:
        return workspace(
            world.app, actor.member, sign_in(world.app, actor.member.email), actor.secret
        )

    place = dataclasses.replace(world.place, author=fresh(world.place.author))
    return dataclasses.replace(
        world, place=place, priya=fresh(world.priya), marcus=fresh(world.marcus)
    )


def _seats_on_record_clock(world: SeatWorld) -> SeatWorld:
    """The seat world with its clock on the server's present and fresh sessions of its three
    people (``_on_record_clock``)."""
    clock = world.place.clock
    stamp = world.place.scalar(select(func.clock_timestamp()))
    clock.set(max(clock.now(), stamp + timedelta(seconds=1)))
    return _seats_resigned(world)


def _seats_on_servers_present(world: SeatWorld) -> SeatWorld:
    """The seat world with its clock ON the server's present (``_on_servers_present``) and
    fresh sessions of its three people, for a case whose fact is on the database's clock: the
    cutoff of a unit of work begun now is its transaction's start, and what another transaction
    records afterwards — an event, the end of a membership — lies after it by construction,
    while a mark or a head made a minute later on the application's clock is later as well."""
    _on_servers_present(world.place)
    return _seats_resigned(world)


def test_a_review_computed_after_the_cutoff_refuses_the_computation(seats: SeatWorld) -> None:
    """A writer that computes in its own transaction leaves no mark behind. The review of a
    judgement record marks its contract's group and computes it in the decision's transaction
    (``policies.judgements.review_judgement``), and it appends no event: a computation that began
    before the review finds the stream heads covered and no mark — and admits no judgement
    reviewed after its cutoff. It is refused by the head the review made."""
    booked = booked_contract(
        seats.place,
        {
            **k09_body(seats.customers["C-09"]),
            "termination": {"party": "CUSTOMER", "has_penalty": False},
        },
        activate=False,
    )
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    world = _seats_on_record_clock(seats)
    _, request_id = _record(
        world,
        contract_id,
        "CONTRACT_TERM",
        {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
    )
    assert request_id is not None
    before = _state(world.place, group_id, contract_id)
    with _begun(world.place) as late:
        _time_passes(world.place)
        reviewed = approve(world.app, request_id, world.marcus)
        assert reviewed.status_code == 200, reviewed.text
        stood = _state(world.place, group_id, contract_id)
        assert stood["head"] != before["head"] and stood["dirty_since"] is None
        assert stood["stream"] == before["stream"]
        assert _behind(late, group_id) == (computation.BEHIND_HEAD,)
        _refused(lambda: computation.recompute(late, group_id))
    assert _state(world.place, group_id, contract_id) == stood


def test_a_combination_applied_after_the_cutoff_refuses_the_computation(seats: SeatWorld) -> None:
    """A combination by the approved command moves two contracts into one group, appends
    ``COMBINATION_CHANGED`` to each and computes the group in the decision's transaction. A
    computation of one contract's FORMER group that began before the approval still reads the
    contract as its member — membership is admitted by the cutoff — over a ledger the
    combination has reallocated. It is refused by the member's event alone: the group the
    contract left carries no mark later than the cutoff, and its head is the one it had.

    The membership's end is on the database's clock, so the case stands ON the server's
    present (``_seats_on_servers_present``): the cutoff is the transaction's start, and the
    approval's stamp lies after it however fast the approval follows."""
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    former = UUID(
        str(
            seats.place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == first)
            )
        )
    )
    world = _seats_on_servers_present(seats)
    ledger: list[Any] = []
    with _begun(world.place) as late:
        _time_passes(world.place)
        proposed = post(
            world.app,
            GROUPS,
            world.place.author,
            {
                "contract_ids": [str(first), str(second)],
                "criterion": "606-10-25-9(b)",
                "rationale": "One package: both orders serve a single commercial objective.",
            },
        )
        assert proposed.status_code == 201, proposed.text
        group_id = UUID(proposed.json()["id"])
        submitted = post(world.app, f"{GROUPS}/{group_id}/submit", world.place.author, {})
        assert submitted.status_code == 200, submitted.text
        approved = approve(world.app, submitted.json()["approval_request_id"], world.marcus)
        assert approved.status_code == 200, approved.text
        ledger = _ledger(world.place, first) + _ledger(world.place, second)
        stood = _state(world.place, group_id, first)
        assert stood["dirty_since"] is None and stood["head"] is not None
        assert _behind(late, former) == (computation.BEHIND_EVENT,)
        _refused(lambda: computation.recompute(late, former))
    assert _ledger(world.place, first) + _ledger(world.place, second) == ledger
    assert _state(world.place, group_id, first) == stood


# --- what a job leaves, and what is stored of the engine's answer ---------------------------------


def test_a_job_refused_behind_its_group_stores_nothing_and_leaves_the_group_owed(
    fx: FxWorld,  # noqa: F811
) -> None:
    """``compute_job.compute_group`` — the body of ``CONTRACT_COMPUTE`` and of the close run's
    ``RECOMPUTE_DIRTY`` — lets the refusal through as it lets every problem through: its
    savepoint is rolled back, no computation row and no exception item is stored, and the group
    is as it was — marked, so that the next run or the next command computes it."""
    contract_id, group_id = delivered(fx)
    _on_record_clock(fx)
    with _begun(fx.place) as late:
        _time_passes(fx.place)
        _marked_by_hand(fx, group_id)
        marked = _state(fx.place, group_id, contract_id)
        _refused(lambda: compute_job.compute_group(late, group_id))
        late.commit()  # what the job's unit of work would keep of the attempt: nothing
    assert _state(fx.place, group_id, contract_id) == marked
    assert marked["dirty_since"] is not None and marked["items"] == 0
    assert _computed_now(fx.place, group_id).status is ComputationStatus.SUCCEEDED
    assert _state(fx.place, group_id, contract_id)["dirty_since"] is None


def _engine_refuses(bundle: Any) -> Any:
    raise EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        "an answer the engine gives to the bundle it was handed",
        detail={"rule": "CV-45"},
    )


def test_what_the_engine_answers_to_a_bundle_behind_its_group_is_not_stored(fx: FxWorld) -> None:  # noqa: F811
    """05 RCP-20 rev 1.207. An ``EngineError`` is stored ``QUARANTINED`` with a blocking exception
    item — a finding about the group. Of a bundle that is behind its group it is no finding
    about the group as it stands: nothing is stored and the attempt ends 409 ``lock-conflict``,
    as the computation itself would have ended. The same answer to a bundle that is not behind
    is stored as before."""
    contract_id, group_id = delivered(fx)
    _on_record_clock(fx)
    with _begun(fx.place) as late:
        _time_passes(fx.place)
        _marked_by_hand(fx, group_id)
        marked = _state(fx.place, group_id, contract_id)
        _refused(lambda: compute_job.compute_group(late, group_id, engine=_engine_refuses))
        late.commit()
    assert _state(fx.place, group_id, contract_id) == marked
    with fx.place.uow() as uow:
        outcome = compute_job.compute_group(uow, group_id, engine=_engine_refuses)
        uow.commit()
    assert outcome.status is ComputationStatus.QUARANTINED
    after = _state(fx.place, group_id, contract_id)
    assert (after["computations"].count("QUARANTINED"), after["items"]) == (1, 1)
    assert after["head"] == marked["head"]


# --- a mark is never moved back ---------------------------------------------------------------


def test_an_append_begun_before_a_mark_does_not_move_it_back(fx: FxWorld) -> None:  # noqa: F811
    """05 RCP-17 rev 1.207. A command begins. A mark is then set on its group at a later instant
    and committed. The command now appends its event: it stamps the LATER of the mark that stands
    and its own instant, so the mark stays where it was — and the command's computation, whose
    cutoff the mark is later than, is refused. Stamped with its own, earlier instant the mark
    would read "not later than the cutoff", and the computation would be stored and would end
    it."""
    contract_id, group_id = delivered(fx)
    _on_record_clock(fx)
    with _begun(fx.place) as late:
        _time_passes(fx.place)
        later = _marked_by_hand(fx, group_id)
        assert later > late.now
        append_events(
            late,
            contract_id=contract_id,
            expected_stream_version=3,
            events=[_second_delivery()],
            origin="API",
        )
        stamped = late.session.execute(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        ).scalar_one()
        assert stamped == later
        _refused(lambda: compute_job.compute_group(late, group_id))
    stood = _state(fx.place, group_id, contract_id)
    assert (stood["dirty_since"], stood["stream"]) == (later, 3)


# --- refused in flight: a command, and an approval's decision ---------------------------------


class _Held:
    """A request sent from a thread of its own and held ONCE, where it is about to take the row
    of its contract's group (``seam``: the module whose ``lock_group_then_contract`` the request
    calls). Its unit of work and its transaction have begun — its cutoff is fixed — and it holds
    no row another transaction on the group would wait for: the place a command stands in while
    it does the work that comes before its group."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, seam: ModuleType, send: Callable[[], HttpResponse]
    ) -> None:
        self.reached, self.go = threading.Event(), threading.Event()
        self.seen: dict[str, Any] = {}
        self.out: dict[str, Any] = {}
        lock = seam.lock_group_then_contract
        held = self

        def stand_then_lock(session: Any, *args: Any, **kwargs: Any) -> Any:
            if not held.seen:
                held.seen["started"] = session.execute(
                    select(func.transaction_timestamp())
                ).scalar_one()
                held.reached.set()
                assert held.go.wait(JOIN_SECONDS)
            return lock(session, *args, **kwargs)

        monkeypatch.setattr(seam, "lock_group_then_contract", stand_then_lock)

        def run() -> None:
            try:
                held.out["response"] = send()
            except Exception as error:  # noqa: BLE001 - surfaced by the assertions
                held.out["error"] = error

        self.thread = threading.Thread(target=run, name="behind-group-held-request")

    def answer(self, meanwhile: Callable[[], None]) -> HttpResponse:
        """Send the request, let ``meanwhile`` happen while it stands, release it; its answer."""
        self.thread.start()
        try:
            assert self.reached.wait(JOIN_SECONDS), (self.seen, self.out)
            meanwhile()
        finally:
            self.go.set()
            self.thread.join(timeout=JOIN_SECONDS)
        assert not self.thread.is_alive() and "error" not in self.out, self.out
        response: HttpResponse = self.out["response"]
        return response


def _kept(place: Workspace, contract_id: UUID) -> dict[str, int]:
    """What a command leaves behind it: events of the contract, and the audit rows and approval
    requests of the workspace."""
    return {
        "events": int(
            place.scalar(
                select(func.count())
                .select_from(contract_event)
                .where(contract_event.c.contract_id == contract_id)
            )
        ),
        "audit": int(place.scalar(select(func.count()).select_from(audit_event))),
        "requests": int(place.scalar(select(func.count()).select_from(approval_request))),
    }


def _records(place: Workspace, key: str) -> list[str]:
    """The state of the idempotency record kept under ``key`` (04 T-PLT-28), if one is."""
    rows = place.rows(
        select(idempotency_record.c.state).where(idempotency_record.c.idempotency_key == key)
    )
    return [str(row["state"]) for row in rows]


def _refused_in_flight(refused: HttpResponse) -> None:
    assert refused.status_code == 409, refused.text  # the status first: a 201 has no slug
    assert slug(refused) == "lock-conflict", refused.text
    body = refused.json()
    assert (body["detail"], body["errors"]) == (LOCK_CONFLICT_DETAIL, []), body


def test_a_command_refused_behind_its_group_saves_nothing_and_is_sent_again(
    fx: FxWorld,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the route. Maya records an invoice (``POST /contracts/{id}/events``, one
    idempotency key). While the command stands before its group, the group is marked at a later
    instant. The command goes on: it appends, its computation is behind the mark, and the whole
    command ends 409 ``lock-conflict`` — "nothing was saved" is true of its event, of its audit
    rows and of the ledger, and the mark stands. Sent again under the SAME key it is recorded and
    computed, and its computation ends the mark."""
    contract_id, group_id = delivered(fx)
    maya, _ = _on_record_clock(fx)
    ledger = _ledger(fx.place, contract_id)
    key = f"k-{uuid4()}"

    def send() -> HttpResponse:
        return call(
            fx.app,
            "POST",
            EVENTS.format(contract_id=contract_id),
            json={"events": [_invoice("INV-UK-7001-1", "2026-08-20", "54000.00")]},
            headers={
                **cookie_headers(maya.token, maya.csrf_token, key=False),
                "Idempotency-Key": key,
                "If-Match": '"s3"',
            },
        )

    marks: dict[str, Any] = {}

    def marked_meanwhile() -> None:
        marks["kept"] = _kept(fx.place, contract_id)
        marks["records"] = _records(fx.place, key)
        _time_passes(fx.place)
        marks["at"] = _marked_by_hand(fx, group_id)
        marks["stood"] = _state(fx.place, group_id, contract_id)

    refused = _Held(monkeypatch, repo, send).answer(marked_meanwhile)
    _refused_in_flight(refused)
    assert _kept(fx.place, contract_id) == marks["kept"]
    assert (marks["records"], _records(fx.place, key)) == (["IN_PROGRESS"], [])
    assert _state(fx.place, group_id, contract_id) == marks["stood"]
    assert marks["stood"]["dirty_since"] == marks["at"]
    assert _ledger(fx.place, contract_id) == ledger

    again = send()
    assert again.status_code == 201, again.text
    assert again.json()["computation"]["status"] == "SUCCEEDED", again.text
    after = _state(fx.place, group_id, contract_id)
    assert (after["stream"], after["dirty_since"]) == (4, None)
    assert _kept(fx.place, contract_id)["events"] == marks["kept"]["events"] + 1
    assert _records(fx.place, key) == ["COMPLETED"]


def _combined_with_a_second_contract(world: FxWorld, first: UUID) -> tuple[UUID, UUID]:
    """``NS-SO-UK-7002`` — the same 200 gateway units for USD 90,000.00 from 1 July 2026 —
    booked, activated and combined with ``first`` into one group by the approved command
    (606-10-25-9(b)); both are priced at list, so the combination moves no amount. Returns
    (the second contract, the combined group)."""
    body = {
        "external_id": "NS-SO-UK-7002",
        "customer_id": str(world.customer_id),
        "contracting_entity_code": ENTITY,
        "transaction_currency": "USD",
        "inception_date": "2026-07-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": GATEWAY,
                "quantity": "200",
                "total_price": {"amount": "90000.00", "currency": "USD"},
            }
        ],
    }
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    second = UUID(str(booked.contract["id"]))
    proposed = post(
        world.app,
        GROUPS,
        world.maya,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(world.app, f"{GROUPS}/{group_id}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    return second, group_id


def test_a_command_behind_another_contracts_delivery_reverses_no_line(
    fx: FxWorld,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """Case 1 through the route, where two people work on one group at the same moment — the
    ledger. ``NS-SO-UK-7001`` (120 units delivered) and ``NS-SO-UK-7002`` are one combination
    group. Maya records an invoice on the first (``POST /contracts/{id}/events``, one idempotency
    key). While that command stands before its group, a delivery on the SECOND contract — 40
    units on 12 August, USD 18,000.00 at 0.83, GBP 14,940.00 — is approved, recorded and
    computed: the group's head is its computation. The first command goes on. Its own contract's
    stream has not moved, so its event is appended; its bundle — cut off where its transaction
    began — does not admit the other contract's delivery, whose lines are in ``posted``, and
    target minus posted is that delivery's reversal.

    It is refused by the member's event, on the frozen clock: an event is on the database's
    clock. Nothing of it is saved — no event, no audit row, no request, no record under its key
    — and the ledger of both contracts and the group stand as the delivery's computation left
    them. (The repetition of a command refused this way:
    ``test_a_command_behind_another_contracts_event_saves_nothing_and_is_sent_again``.)"""
    first, _ = delivered(fx)
    second, group_id = _combined_with_a_second_contract(fx, first)
    head = int(
        fx.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == first))
    )
    before = _ledger(fx.place, first) + _ledger(fx.place, second)
    key = f"k-{uuid4()}"

    def send() -> HttpResponse:
        return call(
            fx.app,
            "POST",
            EVENTS.format(contract_id=first),
            json={"events": [_invoice("INV-UK-7001-1", "2026-08-20", "54000.00")]},
            headers={
                **cookie_headers(fx.maya.token, fx.maya.csrf_token, key=False),
                "Idempotency-Key": key,
                "If-Match": f'"s{head}"',
            },
        )

    marks: dict[str, Any] = {}

    def delivered_meanwhile() -> None:
        recorded = approved_manual_events(
            fx.place, fx.priya, second, SECOND_DELIVERY, evidence_file_ids=[]
        )
        assert recorded["computation"]["status"] == "SUCCEEDED", recorded["computation"]
        marks["kept"] = _kept(fx.place, first)
        marks["stood"] = _state(fx.place, group_id, first)
        marks["ledger"] = _ledger(fx.place, first) + _ledger(fx.place, second)

    refused = _Held(monkeypatch, repo, send).answer(delivered_meanwhile)
    _refused_in_flight(refused)
    assert _logged(log_stream) == [
        (str(group_id), (computation.BEHIND_EVENT, computation.BEHIND_HEAD), "COMMAND")
    ]
    assert (_kept(fx.place, first), _records(fx.place, key)) == (marks["kept"], [])
    assert _state(fx.place, group_id, first) == marks["stood"]
    assert (marks["stood"]["stream"], marks["stood"]["dirty_since"]) == (head, None)
    ledger = _ledger(fx.place, first) + _ledger(fx.place, second)
    assert ledger == marks["ledger"]
    assert [line for line in ledger if line not in before] == [
        ("FY2026-P08", "CONTRACT_LIABILITY", Decimal("18000.0000"), Decimal("14940.0000")),
        ("FY2026-P08", "REVENUE", Decimal("-18000.0000"), Decimal("-14940.0000")),
    ]
    revenue = sum((txn for _, role, txn, _ in ledger if role == "REVENUE"), Decimal(0))
    assert revenue == Decimal("-72000.0000")


def _billing(number: str) -> dict[str, Any]:
    """An invoice of USD 1,000.00 of 1 September, as ``test_combination.BILLING`` records one."""
    payload = {**BILLING["payload"], "invoice_number": number, "line_external_id": f"{number}-1"}
    return {**BILLING, "payload": payload}


def _head_covers(place: Workspace, group_id: UUID) -> dict[UUID, int]:
    """Per member contract, the stream head the group's head computation was computed over."""
    heads = place.scalar(
        select(contract_computation.c.stream_heads)
        .select_from(
            combination_group.join(
                contract_computation,
                and_(
                    contract_computation.c.tenant_id == combination_group.c.tenant_id,
                    contract_computation.c.id == combination_group.c.head_computation_id,
                ),
            )
        )
        .where(combination_group.c.id == group_id)
    )
    return {UUID(str(contract_id)): int(head) for contract_id, head in dict(heads).items()}


def test_a_command_behind_another_contracts_event_saves_nothing_and_is_sent_again(
    seats: SeatWorld, monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    """Case 1 through the route — the whole cycle of the command. ``SF-ORD-10417`` and
    ``SF-ORD-10418`` are one combination group (606-10-25-9(b)). An invoice is recorded on the
    first (``POST /contracts/{id}/events``, one idempotency key). While that command stands
    before its group, an invoice on the SECOND contract is recorded and computed: the group's
    head is its computation, over both streams as they then stand. The first command goes on:
    its own contract's stream has not moved, so its event is appended, and its bundle — cut off
    where its transaction began — does not admit the other contract's invoice.

    It is refused by the member's event, on the frozen clock. Nothing of it is saved — no event,
    no audit row, no request, no record under its key — and the group stands as the second
    invoice's computation left it. Sent again under the SAME key it is recorded and computed,
    and the head it makes is computed over both invoices."""
    first, second, group_id = _combine(seats)
    author = seats.place.author
    heads = {
        contract_id: int(
            seats.place.scalar(
                select(contract.c.head_stream_version).where(contract.c.id == contract_id)
            )
        )
        for contract_id in (first, second)
    }
    key = f"k-{uuid4()}"

    def send() -> HttpResponse:
        return call(
            seats.app,
            "POST",
            EVENTS.format(contract_id=first),
            json={"events": [_billing("INV-US-4201")]},
            headers={
                **cookie_headers(author.token, author.csrf_token, key=False),
                "Idempotency-Key": key,
                "If-Match": f'"s{heads[first]}"',
            },
        )

    marks: dict[str, Any] = {}

    def other_invoice_meanwhile() -> None:
        other = post(
            seats.app,
            EVENTS.format(contract_id=second),
            author,
            {"events": [_billing("INV-US-4202")]},
            if_match=f'"s{heads[second]}"',
        )
        assert other.status_code == 201, other.text
        assert other.json()["computation"]["status"] == "SUCCEEDED", other.text
        marks["kept"] = _kept(seats.place, first)
        marks["stood"] = _state(seats.place, group_id, first)

    refused = _Held(monkeypatch, repo, send).answer(other_invoice_meanwhile)
    _refused_in_flight(refused)
    assert _logged(log_stream) == [
        (str(group_id), (computation.BEHIND_EVENT, computation.BEHIND_HEAD), "COMMAND")
    ]
    assert (_kept(seats.place, first), _records(seats.place, key)) == (marks["kept"], [])
    assert _state(seats.place, group_id, first) == marks["stood"]
    assert (marks["stood"]["stream"], marks["stood"]["dirty_since"]) == (heads[first], None)
    assert _head_covers(seats.place, group_id) == {first: heads[first], second: heads[second] + 1}

    again = send()
    assert again.status_code == 201, again.text
    assert again.json()["computation"]["status"] == "SUCCEEDED", again.text
    after = _state(seats.place, group_id, first)
    assert (after["stream"], after["dirty_since"]) == (heads[first] + 1, None)
    assert after["head"] != marks["stood"]["head"]
    assert _records(seats.place, key) == ["COMPLETED"]
    assert _head_covers(seats.place, group_id) == {
        first: heads[first] + 1,
        second: heads[second] + 1,
    }


def test_a_decision_refused_behind_its_group_leaves_its_request_pending(
    fx: FxWorld,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An approval's decision with its hook. Maya's second delivery waits for Priya (BUILD_SPEC
    CTR-6); Priya's approval appends it and computes, in the decision's transaction. While the
    decision stands before the group, the group is marked at a later instant. The decision goes
    on and is refused: nothing of it is saved — no decision, no event — the request is still
    pending, and decided again it is approved, recorded and computed."""
    contract_id, group_id = delivered(fx)
    maya, _ = _on_record_clock(fx)
    priya = _resigned(fx, fx.priya)
    sent = post(
        fx.app,
        EVENTS.format(contract_id=contract_id),
        maya,
        {"events": [SECOND_DELIVERY], "evidence_file_ids": []},
        if_match='"s3"',
    )
    assert sent.status_code == 201, sent.text
    request_id = str(sent.json()["approval_request_id"])
    ledger = _ledger(fx.place, contract_id)
    marks: dict[str, Any] = {}

    def marked_meanwhile() -> None:
        marks["kept"] = _kept(fx.place, contract_id)
        _time_passes(fx.place)
        marks["at"] = _marked_by_hand(fx, group_id)
        marks["stood"] = _state(fx.place, group_id, contract_id)

    held = _Held(monkeypatch, subjects, lambda: approve(fx.app, request_id, priya))
    _refused_in_flight(held.answer(marked_meanwhile))
    assert _kept(fx.place, contract_id) == marks["kept"]
    assert _state(fx.place, group_id, contract_id) == marks["stood"]
    assert _ledger(fx.place, contract_id) == ledger
    status = fx.place.scalar(
        select(approval_request.c.status).where(approval_request.c.id == UUID(request_id))
    )
    assert str(getattr(status, "value", status)) == "PENDING"
    shown = get(fx.app, f"{APPROVALS}/{request_id}", priya)
    assert shown.status_code == 200 and shown.json()["status"] == "PENDING", shown.text

    decided = approve(fx.app, request_id, priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    after = _state(fx.place, group_id, contract_id)
    assert (after["stream"], after["dirty_since"]) == (4, None)
    assert ("FY2026-P08", "REVENUE", Decimal("-18000.0000"), Decimal("-14940.0000")) in _ledger(
        fx.place, contract_id
    )
