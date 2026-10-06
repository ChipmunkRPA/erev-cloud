"""Late events (D-19; dev-guide DG-KRN-TIME-04; 04 §14.1 DB-07, T-SL-04; 05 §3.9; CTL-017;
BUILD_SPEC CTR-5, BS3-D-20).

The DB-07 test writes probe rows through ``support.rows``. The CTL-017 world is
``support.factories.k11_world`` (AVM-DE, Europe/Berlin, FY2026-P01 to P09 open) with a K-11 variant
booked on 2026-08-01, activated as the SYSTEM principal and computed; FY2026-P08 is then set
``closed`` in a pg-marked test (BS3-D-20): the ``period_state`` update with its
``period_state_transition`` rows in one transaction, the closing row naming a stored lock
(``fk_period_state_transition__period_lock`` since CLO-2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    exception_item,
    legal_entity,
    period,
    period_lock,
    period_state,
    period_state_transition,
    subledger_line,
    subledger_posting,
)
from erev_api.enums import PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import exc, insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import (
    K11World,
    activated_contract,
    booked_contract,
    computed,
    k11_body,
    k11_world,
    tenant_factory,
    tenant_id_of,
)
from support.reference import assign
from support.rows import (
    CloseParts,
    approval_request_values,
    insert_ledger_parts,
    period_lock_values,
    period_state_transition_values,
    period_state_values,
    period_values,
    subledger_line_values,
    subledger_posting_values,
)
from support.worlds import approved_manual_events

pytestmark = pytest.mark.pg


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> K11World:
    return k11_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _failure(session: Session, statement: object) -> tuple[str | None, str]:
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        session.execute(statement)  # type: ignore[call-overload]
    savepoint.rollback()
    original = excinfo.value.orig
    sqlstate = getattr(original, "sqlstate", None)
    diag = getattr(original, "diag", None)
    message = getattr(diag, "message_primary", None) or str(original)
    return sqlstate, str(message)


def test_db_07_origin_period_precedes_posting_period(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id, state="open")
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == parts.chain.entity_id)
        ).scalar_one()
        february = period_values(
            tenant_id,
            calendar_id=calendar_id,
            period_no=2,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )
        session.execute(insert(period).values(**february))
        session.execute(
            insert(period_state).values(
                **period_state_values(
                    tenant_id,
                    entity_id=parts.chain.entity_id,
                    period_id=february["id"],
                    period_end_date=date(2026, 2, 28),
                    state="open",
                )
            )
        )
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        # A line in FY2026-P01 whose origin FY2026-P02 does not end before P01 starts.
        backwards = subledger_line_values(
            tenant_id,
            posting=posting,
            parts=parts,
            amount=Decimal("5.00"),
            origin_period_id=february["id"],
            reason_code="LATE_EVENT",
        )
        assert _failure(session, insert(subledger_line).values(**backwards)) == (
            "P0001",
            f"EREV-LED-003: origin period {february['id']} of line {backwards['id']} does not end "
            f"before period {parts.period_id} starts",
        )
        # The origin of the line equal to its own period fails the same way.
        own = subledger_line_values(
            tenant_id,
            posting=posting,
            parts=parts,
            amount=Decimal("5.00"),
            origin_period_id=parts.period_id,
            reason_code="LATE_EVENT",
        )
        sqlstate, message = _failure(session, insert(subledger_line).values(**own))
        assert (sqlstate, message.split(":", 1)[0]) == ("P0001", "EREV-LED-003")
        session.rollback()


def _close_period(world: K11World, period_key: str) -> tuple[UUID, UUID]:
    """BS3-D-20: AVM-DE ``period_key`` open → closing → closed for ASC606, each change with its
    transition row in one transaction; returns (period id, state id)."""
    tenant_id = world.place.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        ).scalar_one()
        period_id = session.execute(
            select(period.c.id).where(
                period.c.calendar_id == calendar_id, period.c.period_key == period_key
            )
        ).scalar_one()
        state_id = session.execute(
            select(period_state.c.id).where(
                period_state.c.entity_id == world.entity_id,
                period_state.c.period_id == period_id,
                period_state.c.book_code == "ASC606",
            )
        ).scalar_one()
        request = approval_request_values(tenant_id, status=_approved())
        session.execute(insert(approval_request).values(**request))
        for from_state, to_state in (("open", "closing"), ("closing", "closed")):
            transition = period_state_transition_values(
                tenant_id,
                period_state_id=state_id,
                entity_id=world.entity_id,
                period_id=period_id,
                from_state=from_state,
                to_state=to_state,
            )
            if to_state == "closed":
                # CLO-2 keys the closing transition to a stored lock; the lock's key back to the
                # transition is checked at commit (L4-2-Q-24).
                parts = CloseParts(
                    calendar_id=calendar_id,
                    entity_id=world.entity_id,
                    period_id=period_id,
                    period_state_transition_id=transition["id"],
                    approval_request_id=request["id"],
                    file_id=new_id(),
                )
                lock = period_lock_values(tenant_id, parts=parts)
                session.execute(insert(period_lock).values(**lock))
                transition = {
                    **transition,
                    "approval_request_id": request["id"],
                    "period_lock_id": lock["id"],
                }
            session.execute(insert(period_state_transition).values(**transition))
            session.execute(
                update(period_state)
                .where(period_state.c.id == state_id)
                .values(state=to_state, updated_by_kind=PrincipalKind.SYSTEM.value)
            )
    return UUID(str(period_id)), UUID(str(state_id))


def _approved() -> object:
    from erev_api.enums import ApprovalRequestStatus

    return ApprovalRequestStatus.APPROVED


@pytest.mark.control("CTL-017")
def test_ctl_017_late_event_posts_to_first_open_period_with_origin(world: K11World) -> None:
    body = k11_body(world.customer_id)
    body = {
        **body,
        "external_id": "NS-SO-DE-5020",
        "inception_date": "2026-08-01",
        "lines": [body["lines"][0]],
    }
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    contract_id = booked.contract["id"]
    computed(world.place, booked.combination_group["id"])
    august, _ = _close_period(world, "FY2026-P08")
    # BUILD_SPEC CTR-6: the late delivery is a person's, so it waits for another user; the
    # approval appends it and computes (04 §16.3 "Manual events").
    assign(world.priya.member, "revenue_reviewer")
    recorded = approved_manual_events(
        world.place,
        world.priya,
        UUID(str(contract_id)),
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-08-20",
            "payload": {"obligation_key": "O1", "quantity": "10", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    assert recorded["computation"]["status"] == "SUCCEEDED"
    september = world.place.scalar(select(period.c.id).where(period.c.period_key == "FY2026-P09"))
    revenue = world.place.rows(
        select(
            subledger_line.c.period_id,
            subledger_line.c.origin_period_id,
            subledger_line.c.amount_txn,
            subledger_line.c.reason_code,
        ).where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.account_role == "REVENUE",
            subledger_line.c.origin_period_id.is_not(None),
        )
    )
    assert revenue
    assert {(row["period_id"], row["origin_period_id"]) for row in revenue} == {(september, august)}
    # 10 of 200 units of 90,000.00 EUR (PRD WLD-K-11): 4,500.00 revenue credited.
    assert sum(Decimal(row["amount_txn"]) for row in revenue) == Decimal("-4500.00")
    raised = world.place.rows(
        select(
            exception_item.c.code,
            exception_item.c.source,
            exception_item.c.severity,
            exception_item.c.status,
            exception_item.c.contract_id,
            exception_item.c.period_id,
            exception_item.c.message,
        )
    )
    items = [
        item
        for item in raised
        if item["code"] == "LATE_EVENT" and item["contract_id"] == contract_id
    ]
    assert [
        (str(item["source"]), str(item["severity"]), str(item["status"])) for item in items
    ] == [("ENGINE", "WARNING", "OPEN")], raised
    assert items[0]["period_id"] == august
    assert items[0]["message"] == (
        "Effective 2026-08-20 in closed period FY2026-P08. The effect posts to FY2026-P09 with "
        "origin period FY2026-P08."
    )
