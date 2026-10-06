"""SCH-06 database witnesses (record §4.31; Codex production-20260922-0349 §1–§2, 0403 §1, 0644 §1,
0708 §2, 0720). NOT RUN on the lane (database-bound; the integrated batch measures).

(1) A real MANUAL ``POST /periods/{id}/open`` by a person who sees the contract re-marks the clean
group with an event in the period, in the same transaction; the retried open is refused and the
stamp survives. (2) Opening the first later postable period re-marks the groups with deferred CLOSED
origins — an event in the closed period and a balanced sealed posting of that period, both written
while the period was postable, the period then closed through the governed transition seam — and
leaves a group without activity clean. (3) SCH06-PERFORMING-ENTITY-1: a person scoped to the
PERFORMING entity B alone, who cannot see the contracting entity's contract, opens B's period
through the API and wakes the group of the contract B performs for — the schedule-line channel
through the CURRENT membership, the moved contract's current group only, the event-only case through
the persisted B-performing obligation version — while an unrelated entity's opening, an
already-dirty group and a contract without any persisted B relationship (the documented limit, Codex
0720) are left as they were. (4) The SYSTEM caller (the SCH-05 route) does the same through the
shared core.

Fixtures are lawful: entities come from ``POST /entities`` (T-REF-03 keeps the enabled ASC606 book
and its period states); every contract chain carries the CURRENT ``combination_group_member`` row
production writes at creation (``contracts/commands.py``) and rolls at a move
(``combination._move``); ledger activity is a balanced, sealed posting written while its period is
postable (WITNESS-BOOK-1, WITNESS-LEDGER-1 — Codex production-20260922-0644 §1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id, transitions
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    calc_trace,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    customer,
    engine_release,
    gl_account,
    obligation,
    obligation_version,
    period,
    period_state,
    pob_template,
    pob_template_version,
    product,
    schedule,
    schedule_line,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates
from erev_api.domain.contracts import combination
from erev_api.domain.reference import commands
from erev_api.enums import ApprovalRequestStatus, BookCode, LockKind, PeriodState
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import open_periods
from support.principals import Actor, colleague, member
from support.reference import PERIODS, calendar, entity, holding, post, slug
from support.rows import (
    ContractRows,
    LedgerParts,
    approval_request_values,
    calc_trace_values,
    combination_group_member_values,
    combination_group_values,
    contract_computation_values,
    contract_event_values,
    contract_values,
    contract_version_values,
    customer_values,
    engine_release_values,
    gl_account_values,
    ledger_seal_values,
    obligation_values,
    obligation_version_values,
    pob_template_values,
    pob_template_version_values,
    product_values,
    schedule_line_values,
    schedule_values,
    subledger_line_values,
    subledger_posting_values,
)

BOOK = BookCode.ASC606.value
# The single T-CON-11 obligation's allocation: DB-17 V1 (migration 0054, EREV-ALC-001) sums the
# IN_SCOPE_606 obligation versions of a contract version against transaction_price − consideration
# payable at commit, so every performing case's version carries this price (Codex 1454 §1
# SCH06-WITNESS-ALLOCATION-1); the posted-gap fixtures have no obligation version and keep 0 = 0.
ALLOCATED = Decimal("100")
OUTSIDE_THE_CALENDAR = date(2025, 12, 15)  # no FY2026 period holds it: never an origin


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _runtime(clock: FrozenClock, keyring: KeyRing, tmp_path: Path) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(tmp_path / "files"))


# --- the world: a tenant, one FY2026 calendar, entities kept through the API ----------------------


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    maya: Actor  # tenant-wide revenue accountant: sets the world up and opens periods she sees
    entities: dict[str, UUID]  # code -> id


def _world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    *,
    codes: tuple[str, ...],
    first_period_key: str | None = None,
) -> World:
    """Maya (``revenue_accountant``, every entity) keeps a January FY2026 calendar and one entity
    per code through ``POST /entities``, each with its enabled ASC606 book and future states —
    from ``first_period_key`` on when given, by default from January. Periods open in order (PRD
    SM-07 guard; supervisor ruling R-58 (d)), so a world whose first opening is October keeps its
    books from October."""
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya)
    kept = {} if first_period_key is None else {"first_period_key": first_period_key}
    entities = {
        code: UUID(str(entity(app, maya, code=code, calendar_id=calendar_id, **kept)["id"]))
        for code in codes
    }
    return World(tenant_id=maya_member.tenant_id, maya=maya, entities=entities)


def _scoped(app: FastAPI, world: World, name: str, code: str) -> Actor:
    """A revenue accountant whose role assignment names ONE entity: the manual route then runs under
    that entity scope alone (RLS-TE hides every other entity's contract rows)."""
    return holding(
        app,
        colleague(world.tenant_id, name),
        "revenue_accountant",
        entity_ids=[world.entities[code]],
    )


def _state(tenant_id: UUID, entity_id: UUID, key: str) -> dict[str, Any]:
    """The ASC606 period state of ``entity_id`` for period ``key`` with its period's dates."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = (
            session.execute(
                select(
                    period_state.c.id,
                    period_state.c.row_version,
                    period_state.c.state,
                    period.c.id.label("period_id"),
                    period.c.period_key,
                    period.c.start_date,
                    period.c.end_date,
                )
                .select_from(
                    period_state.join(
                        period,
                        and_(
                            period.c.tenant_id == period_state.c.tenant_id,
                            period.c.id == period_state.c.period_id,
                        ),
                    )
                )
                .where(
                    period_state.c.entity_id == entity_id,
                    period_state.c.book_code == BOOK,
                    period.c.period_key == key,
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


def _open(app: FastAPI, actor: Actor, state: dict[str, Any], comment: str) -> Any:
    return post(
        app,
        f"{PERIODS}/{state['id']}/open",
        actor,
        {"comment": comment},
        if_match=f'"r{state["row_version"]}"',
    )


# --- contract chains, as production leaves them -------------------------------------------------


@dataclass(frozen=True, slots=True)
class Chain:
    customer_id: UUID
    group_id: UUID
    contract_id: UUID
    event_id: UUID
    member_id: UUID

    def rows(self, entity_id: UUID) -> ContractRows:
        return ContractRows(
            entity_id=entity_id,
            customer_id=self.customer_id,
            group_id=self.group_id,
            contract_id=self.contract_id,
        )


@dataclass(frozen=True, slots=True)
class Computed:
    computation_id: UUID
    version_id: UUID
    obligation_id: UUID
    product_id: UUID
    pob_template_version_id: UUID


def _contract_of(
    session: Session,
    tenant_id: UUID,
    *,
    entity_id: UUID,
    effective: date,
    group_id: UUID | None = None,
    dirty_since: datetime | None = None,
) -> Chain:
    """A contract of ``entity_id`` with one event on ``effective`` and the CURRENT membership row of
    its group (a fresh clean singleton unless ``group_id`` names one), as ``contracts/commands.py``
    writes them at creation."""
    buyer = customer_values(tenant_id)
    session.execute(insert(customer).values(**buyer))
    if group_id is None:
        group = combination_group_values(tenant_id, dirty_since=dirty_since)
        session.execute(insert(combination_group).values(**group))
        group_id = UUID(str(group["id"]))
    row = contract_values(
        tenant_id,
        customer_id=buyer["id"],
        contracting_entity_id=entity_id,
        combination_group_id=group_id,
        head_stream_version=1,
    )
    session.execute(insert(contract).values(**row))
    event = contract_event_values(
        tenant_id,
        contract_id=row["id"],
        contracting_entity_id=entity_id,
        stream_version=1,
        effective_date=effective,
    )
    session.execute(insert(contract_event).values(**event))
    membership = combination_group_member_values(
        tenant_id, combination_group_id=group_id, contract_id=row["id"], join_event_id=event["id"]
    )
    session.execute(insert(combination_group_member).values(**membership))
    return Chain(
        customer_id=UUID(str(buyer["id"])),
        group_id=group_id,
        contract_id=UUID(str(row["id"])),
        event_id=UUID(str(event["id"])),
        member_id=UUID(str(membership["id"])),
    )


def _computed(
    session: Session,
    tenant_id: UUID,
    chain: Chain,
    *,
    entity_id: UUID,
    transaction_price: Decimal = Decimal(0),
) -> Computed:
    """A computation, a trace, version 1 and one obligation of the chain — the rows the engine
    persists (``insert_version_rows`` / ``insert_obligation_rows`` against a chain of our own).
    ``transaction_price`` is what the version's IN_SCOPE_606 obligation versions must allocate
    (DB-17 V1): 0 for a version without one, ``ALLOCATED`` for a performing case."""
    release = engine_release_values()
    session.execute(insert(engine_release).values(**release))
    computation = contract_computation_values(
        tenant_id, combination_group_id=chain.group_id, engine_release_id=release["id"]
    )
    session.execute(insert(contract_computation).values(**computation))
    version_id, trace_id = new_id(), new_id()
    session.execute(
        insert(calc_trace).values(
            **calc_trace_values(
                tenant_id,
                contract_version_id=version_id,
                combination_group_id=chain.group_id,
                id=trace_id,
            )
        )
    )
    session.execute(
        insert(contract_version).values(
            **contract_version_values(
                tenant_id,
                combination_group_id=chain.group_id,
                contract_computation_id=computation["id"],
                calc_trace_id=trace_id,
                transaction_price=transaction_price,
                id=version_id,
            )
        )
    )
    product_row = product_values(tenant_id)
    session.execute(insert(product).values(**product_row))
    template = pob_template_values(tenant_id)
    session.execute(insert(pob_template).values(**template))
    template_version = pob_template_version_values(tenant_id, pob_template_id=template["id"])
    session.execute(insert(pob_template_version).values(**template_version))
    obligation_row = obligation_values(
        tenant_id,
        contract_id=chain.contract_id,
        product_id=product_row["id"],
        created_by_event_id=chain.event_id,
        obligation_key="O1",
    )
    session.execute(insert(obligation).values(**obligation_row))
    return Computed(
        computation_id=UUID(str(computation["id"])),
        version_id=version_id,
        obligation_id=UUID(str(obligation_row["id"])),
        product_id=UUID(str(product_row["id"])),
        pob_template_version_id=UUID(str(template_version["id"])),
    )


def _performed_by(
    session: Session,
    tenant_id: UUID,
    chain: Chain,
    computed: Computed,
    *,
    contracting_id: UUID,
    performing_id: UUID,
    allocated_amount: Decimal = ALLOCATED,
) -> None:
    """JET-13: the obligation version names the entity that performs (and posts) it; it allocates
    ``allocated_amount`` of the version's transaction price (DB-17 V1)."""
    session.execute(
        insert(obligation_version).values(
            **obligation_version_values(
                tenant_id,
                contract_version_id=computed.version_id,
                obligation_id=computed.obligation_id,
                contract_id=chain.contract_id,
                combination_group_id=chain.group_id,
                product_id=computed.product_id,
                pob_template_version_id=computed.pob_template_version_id,
                entity_id=contracting_id,
                performing_entity_id=performing_id,
                allocated_amount=allocated_amount,
            )
        )
    )


def _scheduled(
    session: Session,
    tenant_id: UUID,
    chain: Chain,
    computed: Computed,
    *,
    entity_id: UUID,
    state: dict[str, Any],
) -> None:
    """A schedule line of the version in the period of ``state`` carried by ``entity_id``
    (T-ENG-02: the performing entity)."""
    plan = schedule_values(
        tenant_id, contract_version_id=computed.version_id, combination_group_id=chain.group_id
    )
    session.execute(insert(schedule).values(**plan))
    session.execute(
        insert(schedule_line).values(
            **schedule_line_values(
                tenant_id,
                schedule_id=plan["id"],
                contract_version_id=computed.version_id,
                contract_id=chain.contract_id,
                entity_id=entity_id,
                period_id=state["period_id"],
                period_end_date=state["end_date"],
                trace_node_id=f"revenue:EXT:{state['period_key']}",
            )
        )
    )


def _moved(
    session: Session,
    tenant_id: UUID,
    chain: Chain,
    *,
    entity_id: UUID,
    target_group_id: UUID,
    effective: date,
    at: datetime,
) -> None:
    """Move the contract to ``target_group_id`` as ``combination._move`` does: a second event, the
    current membership ended at ``at`` through the domain's own transition writer, a new current row
    in the target, and the contract's denormalised group following (DB-18 lists that column)."""
    session.execute(
        update(contract)
        .where(contract.c.tenant_id == tenant_id, contract.c.id == chain.contract_id)
        .values(head_stream_version=2, row_version=contract.c.row_version + 1)
    )
    event = contract_event_values(
        tenant_id,
        contract_id=chain.contract_id,
        contracting_entity_id=entity_id,
        stream_version=2,
        effective_date=effective,
    )
    session.execute(insert(contract_event).values(**event))
    transitions.apply(
        session,
        combination.MEMBER_OBJECT,
        chain.member_id,
        to_status=None,
        set_values={"valid_to_known_at": at, "leave_event_id": event["id"]},
    )
    session.execute(
        insert(combination_group_member).values(
            **combination_group_member_values(
                tenant_id,
                combination_group_id=target_group_id,
                contract_id=chain.contract_id,
                join_event_id=event["id"],
                valid_from_known_at=at,
            )
        )
    )
    session.execute(
        update(contract)
        .where(contract.c.tenant_id == tenant_id, contract.c.id == chain.contract_id)
        .values(combination_group_id=target_group_id, row_version=contract.c.row_version + 1)
    )


def _dirty_since(tenant_id: UUID, group_id: UUID) -> datetime | None:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        value = session.execute(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        ).scalar_one()
    return None if value is None else value.astimezone(UTC)


# --- (1) the manual route ------------------------------------------------------------------------


def test_a_manual_opening_re_marks_the_clean_group_and_the_retry_is_refused(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    world = _world(app, keyring, clock, codes=("AVM-US",))
    tenant_id, us = world.tenant_id, world.entities["AVM-US"]
    earlier = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    with tenant_session(_context(tenant_id)) as session:
        in_january = _contract_of(session, tenant_id, entity_id=us, effective=date(2026, 1, 15))
        in_february = _contract_of(session, tenant_id, entity_id=us, effective=date(2026, 2, 15))
        already_dirty = _contract_of(
            session, tenant_id, entity_id=us, effective=date(2026, 1, 20), dirty_since=earlier
        )
        session.commit()
    january = _state(tenant_id, us, "FY2026-P01")

    opened = _open(app, world.maya, january, "Setup")
    assert opened.status_code == 200, opened.text

    assert _dirty_since(tenant_id, in_january.group_id) == clock.now()
    assert _dirty_since(tenant_id, in_february.group_id) is None
    assert _dirty_since(tenant_id, already_dirty.group_id) == earlier
    # Idempotent retry: the state is no longer future; nothing is re-stamped.
    retried = _open(app, world.maya, _state(tenant_id, us, "FY2026-P01"), "Again")
    assert (retried.status_code, slug(retried)) == (409, "invalid-transition"), retried.text
    assert _dirty_since(tenant_id, in_january.group_id) == clock.now()


# --- (2) the deferred closed origins -------------------------------------------------------------


def _close_through_the_seam(
    runtime: JobRuntime, tenant_id: UUID, *, entity_id: UUID, state_id: UUID, request_id: str
) -> None:
    """``open → closing → closed`` with the close domain's own writers, as ``test_lock`` drives its
    fixture: the transition writer for the soft close, ``_persist_lock`` with an APPROVED
    ``PERIOD_LOCK`` request for the lock (T-REF-07 names both)."""
    with system_unit_of_work(runtime, system_principal(tenant_id), request_id=request_id) as uow:
        session = uow.session
        scope = gates.period_scope(session, state_id, lock=True)
        assert scope is not None and scope.state == PeriodState.OPEN.value
        close_commands._record_transition(
            uow,
            state_id=state_id,
            current=close_commands._current(session, scope),
            from_state=PeriodState.OPEN,
            to_state=PeriodState.CLOSING,
            action=close_commands.START_CLOSE_ACTION,
            reason_code=None,
            comment="Witness soft close",
        )
        scope = gates.period_scope(session, state_id, lock=True)
        assert scope is not None and scope.state == PeriodState.CLOSING.value
        request = approval_request_values(
            tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            entity_id=entity_id,
            subject_type="PERIOD_LOCK",
            subject_id=state_id,
            summary="Witness lock request",
        )
        session.execute(insert(approval_request).values(**request))
        close_commands._persist_lock(
            uow,
            scope,
            kind=LockKind.LOCK,
            lock_id=new_id(),
            transition_id=new_id(),
            from_state=PeriodState.CLOSING,
            to_state=PeriodState.CLOSED,
            action=close_commands.LOCK_ACTION,
            approval_request_id=UUID(str(request["id"])),
            comment="Witness lock",
            certification=[],
            snapshot_manifest_sha256=None,
            heads=close_commands._heads(session, scope),
            cutoff_known_at=uow.now,  # 04 T-CLS-04 rev 1.113 (R-40 (c)): a LOCK names its cutoff
        )
        uow.commit()


def _posted_in(
    session: Session,
    tenant_id: UUID,
    chain: Chain,
    *,
    entity_id: UUID,
    state: dict[str, Any],
    account_id: UUID,
) -> None:
    """A balanced, sealed ENGINE_COMPUTE posting of the chain in the period of ``state`` — written
    while that period is postable, as the ledger guards require (WITNESS-LEDGER-1)."""
    computed = _computed(session, tenant_id, chain, entity_id=entity_id)
    parts = LedgerParts(
        chain=chain.rows(entity_id),
        computation_id=computed.computation_id,
        period_id=UUID(str(state["period_id"])),
        period_end_date=state["end_date"],
        account_id=account_id,
    )
    posting = subledger_posting_values(tenant_id, parts=parts)
    session.execute(insert(subledger_posting).values(**posting))
    lines = tuple(
        subledger_line_values(tenant_id, posting=posting, parts=parts, amount=amount)
        for amount in (Decimal("10.00"), Decimal("-10.00"))
    )
    session.execute(insert(subledger_line), [dict(line) for line in lines])
    seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
    session.execute(insert(subledger_posting_seal).values(**seal))


def test_opening_the_first_later_postable_period_wakes_the_deferred_closed_origins(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """FY2026-P01 is opened through the API, receives two balanced sealed postings (origin P01) and
    a third group's event while postable, and is then closed through the governed seam; P02 is
    future. One posted contract has since moved G0 → H (supervisor ruling on ``posted_in_gap``).
    Opening P02 — the first later postable period — re-marks the posted group, the event group, the
    moved contract's CURRENT group H and, conservatively, its historical G0; a group whose only
    event lies outside the calendar stays clean."""
    world = _world(app, keyring, clock, codes=("AVM-US",))
    tenant_id, us = world.tenant_id, world.entities["AVM-US"]
    open_periods(app, world.maya, entity_code="AVM-US", keys=["FY2026-P01"])
    january = _state(tenant_id, us, "FY2026-P01")
    assert january["state"] == "open"
    with tenant_session(_context(tenant_id)) as session:
        account = gl_account_values(tenant_id)
        session.execute(insert(gl_account).values(**account))
        account_id = UUID(str(account["id"]))
        posted = _contract_of(session, tenant_id, entity_id=us, effective=OUTSIDE_THE_CALENDAR)
        _posted_in(session, tenant_id, posted, entity_id=us, state=january, account_id=account_id)
        moved = _contract_of(session, tenant_id, entity_id=us, effective=OUTSIDE_THE_CALENDAR)
        _posted_in(session, tenant_id, moved, entity_id=us, state=january, account_id=account_id)
        h = combination_group_values(tenant_id, dirty_since=None)
        session.execute(insert(combination_group).values(**h))
        _moved(
            session,
            tenant_id,
            moved,
            entity_id=us,
            target_group_id=UUID(str(h["id"])),
            effective=OUTSIDE_THE_CALENDAR,
            at=clock.now() - timedelta(days=1),
        )
        event_in_january = _contract_of(
            session, tenant_id, entity_id=us, effective=date(2026, 1, 10)
        )
        no_activity = _contract_of(session, tenant_id, entity_id=us, effective=OUTSIDE_THE_CALENDAR)
        session.commit()
    runtime = _runtime(clock, keyring, tmp_path)
    _close_through_the_seam(
        runtime,
        tenant_id,
        entity_id=us,
        state_id=UUID(str(january["id"])),
        request_id="test-sch06-close-p01",
    )
    assert _state(tenant_id, us, "FY2026-P01")["state"] == "closed"
    assert _dirty_since(tenant_id, posted.group_id) is None  # closing marks nothing
    february = _state(tenant_id, us, "FY2026-P02")

    with system_unit_of_work(
        runtime, system_principal(tenant_id), request_id="test-sch06-r1"
    ) as uow:
        opening = commands.open_future_period(
            uow, state_id=UUID(str(february["id"])), comment="Opened for the witness"
        )
        uow.commit()

    assert opening.period.state == "open" and opening.redirtied == 4
    stamp = clock.now()
    assert _dirty_since(tenant_id, posted.group_id) == stamp  # posted line in closed P01
    assert _dirty_since(tenant_id, event_in_january.group_id) == stamp  # event in closed P01
    assert (
        _dirty_since(tenant_id, UUID(str(h["id"]))) == stamp
    )  # the moved contract's CURRENT group
    assert _dirty_since(tenant_id, moved.group_id) == stamp  # its historical group, conservatively
    assert _dirty_since(tenant_id, no_activity.group_id) is None


# --- (3) the performing entity, manual and B-only ------------------------------------------------


def test_a_person_scoped_to_the_performing_entity_wakes_the_groups_it_posts_for(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """SCH06-PERFORMING-ENTITY-1 (Codex production-20260922-0403 §1, 0644 §1): Bea holds
    ``revenue_accountant`` for AVM-B alone, so RLS-TE hides every AVM-A contract and event from her
    session. Contracts of A performed by B (JET-13), A's October open, B's October future, the
    groups computed and clean while B's posting defers. Cara (AVM-C alone) opening C's October marks
    nothing; Bea opening B's October marks — through B-visible rows only — the group with B's
    October schedule line (G), the moved contract's CURRENT group (H, not its former G0), and the
    event-only group with a persisted B-performing obligation version (E); it leaves the
    already-dirty group's stamp (D) and the contract without any persisted B relationship (L, the
    documented limit) as they were; the retry is 409 and nothing is re-stamped; Bea cannot open A's
    period at all (404)."""
    world = _world(
        app, keyring, clock, codes=("AVM-A", "AVM-B", "AVM-C"), first_period_key="FY2026-P10"
    )
    tenant_id = world.tenant_id
    a, b, c = (world.entities[code] for code in ("AVM-A", "AVM-B", "AVM-C"))
    open_periods(app, world.maya, entity_code="AVM-A", keys=["FY2026-P10"])
    b_october = _state(tenant_id, b, "FY2026-P10")
    earlier = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    in_october = date(2026, 10, 15)
    with tenant_session(_context(tenant_id)) as session:
        # G: B's October schedule line.
        g = _contract_of(session, tenant_id, entity_id=a, effective=in_october)
        g_rows = _computed(session, tenant_id, g, entity_id=a, transaction_price=ALLOCATED)
        _performed_by(session, tenant_id, g, g_rows, contracting_id=a, performing_id=b)
        _scheduled(session, tenant_id, g, g_rows, entity_id=b, state=b_october)
        # G0 -> H: the same shape, then the contract moves to H before B's October opens.
        moved = _contract_of(session, tenant_id, entity_id=a, effective=in_october)
        moved_rows = _computed(session, tenant_id, moved, entity_id=a, transaction_price=ALLOCATED)
        _performed_by(session, tenant_id, moved, moved_rows, contracting_id=a, performing_id=b)
        _scheduled(session, tenant_id, moved, moved_rows, entity_id=b, state=b_october)
        h = combination_group_values(tenant_id, dirty_since=None)
        session.execute(insert(combination_group).values(**h))
        _moved(
            session,
            tenant_id,
            moved,
            entity_id=a,
            target_group_id=UUID(str(h["id"])),
            effective=in_october,
            at=clock.now() - timedelta(days=1),
        )
        # E: the event-only deferred case — a persisted B-performing obligation version, no line.
        e = _contract_of(session, tenant_id, entity_id=a, effective=in_october)
        e_rows = _computed(session, tenant_id, e, entity_id=a, transaction_price=ALLOCATED)
        _performed_by(session, tenant_id, e, e_rows, contracting_id=a, performing_id=b)
        # D: already dirty, with B's October schedule line — the stamp must survive.
        d = _contract_of(session, tenant_id, entity_id=a, effective=in_october, dirty_since=earlier)
        d_rows = _computed(session, tenant_id, d, entity_id=a, transaction_price=ALLOCATED)
        _performed_by(session, tenant_id, d, d_rows, contracting_id=a, performing_id=b)
        _scheduled(session, tenant_id, d, d_rows, entity_id=b, state=b_october)
        # L: an A contract with an October event and no persisted B relationship at all.
        limit = _contract_of(session, tenant_id, entity_id=a, effective=in_october)
        session.commit()
    h_id = UUID(str(h["id"]))
    for group_id in (g.group_id, moved.group_id, h_id, e.group_id, limit.group_id):
        assert _dirty_since(tenant_id, group_id) is None  # computed and clean: the case Codex names
    bea = _scoped(app, world, "bea", "AVM-B")
    cara = _scoped(app, world, "cara", "AVM-C")

    unrelated = _open(app, cara, _state(tenant_id, c, "FY2026-P10"), "C October")
    assert unrelated.status_code == 200, unrelated.text
    for group_id in (g.group_id, moved.group_id, h_id, e.group_id, limit.group_id):
        assert _dirty_since(tenant_id, group_id) is None
    assert _dirty_since(tenant_id, d.group_id) == earlier

    hidden = _open(app, bea, _state(tenant_id, a, "FY2026-P11"), "Not mine")
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    opened = _open(app, bea, b_october, "B October")
    assert opened.status_code == 200, opened.text

    stamp = clock.now()
    assert _dirty_since(tenant_id, g.group_id) == stamp  # the schedule-line channel
    assert _dirty_since(tenant_id, h_id) == stamp  # the CURRENT group of the moved contract
    assert _dirty_since(tenant_id, moved.group_id) is None  # its former group is not a member's
    assert _dirty_since(tenant_id, e.group_id) == stamp  # rule (c): the obligation version
    assert _dirty_since(tenant_id, d.group_id) == earlier  # an existing stamp survives
    assert _dirty_since(tenant_id, limit.group_id) is None  # no persisted B relationship: the limit
    retried = _open(app, bea, _state(tenant_id, b, "FY2026-P10"), "Again")
    assert (retried.status_code, slug(retried)) == (409, "invalid-transition"), retried.text
    assert _dirty_since(tenant_id, g.group_id) == stamp


# --- (4) the performing entity through the shared core (the SCH-05 route) ------------------------


def test_the_scheduler_route_wakes_the_performing_entitys_group_through_the_shared_core(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """The SYSTEM caller sees every row; the core marks G once when B's October opens, nothing when
    an unrelated entity's October opens, and leaves G's stamp when B's November opens later.
    Marking never posts: the recompute posts once (RCP-06)."""
    world = _world(
        app, keyring, clock, codes=("AVM-A", "AVM-B", "AVM-C"), first_period_key="FY2026-P10"
    )
    tenant_id = world.tenant_id
    a, b, c = (world.entities[code] for code in ("AVM-A", "AVM-B", "AVM-C"))
    open_periods(app, world.maya, entity_code="AVM-A", keys=["FY2026-P10"])
    b_october = _state(tenant_id, b, "FY2026-P10")
    with tenant_session(_context(tenant_id)) as session:
        g = _contract_of(session, tenant_id, entity_id=a, effective=date(2026, 10, 15))
        rows = _computed(session, tenant_id, g, entity_id=a, transaction_price=ALLOCATED)
        _performed_by(session, tenant_id, g, rows, contracting_id=a, performing_id=b)
        _scheduled(session, tenant_id, g, rows, entity_id=b, state=b_october)
        session.commit()
    assert _dirty_since(tenant_id, g.group_id) is None
    runtime = _runtime(clock, keyring, tmp_path)
    principal = system_principal(tenant_id)

    with system_unit_of_work(runtime, principal, request_id="test-sch06-c") as uow:
        unrelated = commands.open_future_period(
            uow, state_id=UUID(str(_state(tenant_id, c, "FY2026-P10")["id"])), comment="C"
        )
        uow.commit()
    assert unrelated.redirtied == 0 and _dirty_since(tenant_id, g.group_id) is None

    with system_unit_of_work(runtime, principal, request_id="test-sch06-b-oct") as uow:
        opening = commands.open_future_period(
            uow, state_id=UUID(str(b_october["id"])), comment="B October"
        )
        uow.commit()
    stamp = clock.now()
    assert opening.redirtied == 1 and _dirty_since(tenant_id, g.group_id) == stamp

    clock.advance(timedelta(minutes=5))
    with system_unit_of_work(runtime, principal, request_id="test-sch06-b-nov") as uow:
        later = commands.open_future_period(
            uow, state_id=UUID(str(_state(tenant_id, b, "FY2026-P11")["id"])), comment="B November"
        )
        uow.commit()
    assert later.redirtied == 0 and _dirty_since(tenant_id, g.group_id) == stamp
