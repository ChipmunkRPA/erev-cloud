"""A manual journal approved after its period was locked posts late, with its period as origin
(BUILD_SPEC CLO-12; PRD SM-10; 03 REQ-JE-019; 04 T-SL-05; ENGINE_SPEC_B S08-R-08, S14-R-09a;
supervisor ruling R-51 (c)).

The database witness of the engine-level
``tests/engine/s14_posting/test_s14_manual_lines.py::test_s14_r09a_a_closed_adjustment_period_posts_late_with_its_origin``
(observation (d) of the CLO-12 report, ruled to be witnessed here).

World: ``support.worlds.k01_pellworth`` through 31 August 2026 — AVM-US (USD) with WLD-K-01
``SF-ORD-10001``. Maya (Revenue Accountant) prepares a manual journal for August, Dr contract
liability 2100 / Cr revenue 4010 USD 2,400.00, and its deferral past the lock is approved by Priya
(Revenue Reviewer), so the adjustment no longer holds the close. August is then closed through
the product (``period_locked``). Everything after that is the subject: the deferred adjustment is
routed again, approved, and posted while its own period is closed.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import gl_account, period, subledger_line, subledger_posting
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.factories import computed
from support.reference import APPROVALS, approve, assign, get, post
from support.worlds import (
    AUGUST_2026,
    AVM_US,
    K01,
    SEPTEMBER_2026,
    ReportWorld,
    k01_pellworth,
    on_record_clock,
    period_locked,
    period_state,
)

ADJUSTMENTS: Final = "/api/v1/manual-adjustments"
AMOUNT: Final = "2400.00"
POSTED_LATE: Final = [
    ("CONTRACT_LIABILITY", "2100", Decimal("2400.00"), SEPTEMBER_2026, AUGUST_2026),
    ("REVENUE", "4010", Decimal("-2400.00"), SEPTEMBER_2026, AUGUST_2026),
]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    built = k01_pellworth(
        app, keyring, clock, LocalFileStore(app_settings.file_root), through=date(2026, 8, 31)
    )
    # PRD §5.6: ``adjustment.approve`` is the Revenue Reviewer's and the Controller's.
    assign(built.priya.member, "revenue_reviewer")
    return on_record_clock(built, clock)  # a close runs on the record-time clock


def _contract_id(world: ReportWorld) -> UUID:
    return UUID(str(world.contracts[K01].contract["id"]))


def _august_journal(world: ReportWorld) -> dict[str, Any]:
    """A ``MANUAL_JOURNAL`` of August on O1: Dr contract liability 2100 / Cr revenue 4010."""
    accounts = {str(row["code"]): str(row["id"]) for row in world.place.rows(select(gl_account))}
    (obligation,) = [
        item for item in world.contracts[K01].obligations if item["obligation_key"] == "O1"
    ]
    return {
        "kind": "MANUAL_JOURNAL",
        "contract_id": str(_contract_id(world)),
        "effective_date": "2026-08-31",
        "reason_code": "DATA_CORRECTION",
        "memo": "Customer accepted phase 2 on 31 Aug 2026; the acceptance arrived in September",
        "payload": {
            "obligation_id": str(obligation["id"]),
            "lines": [
                {
                    "account_role": "CONTRACT_LIABILITY",
                    "gl_account_id": accounts["2100"],
                    "amount_txn": {"amount": AMOUNT, "currency": "USD"},
                },
                {
                    "account_role": "REVENUE",
                    "gl_account_id": accounts["4010"],
                    "amount_txn": {"amount": f"-{AMOUNT}", "currency": "USD"},
                },
            ],
        },
    }


def _shown(world: ReportWorld, adjustment_id: str) -> dict[str, Any]:
    shown = get(world.app, f"{ADJUSTMENTS}/{adjustment_id}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _manual_lines(world: ReportWorld) -> list[tuple[str, str, Decimal, str, str | None]]:
    """(role, account, signed functional amount, posting period, origin period) of the contract's
    sealed lines of posting kind ``MANUAL_ADJUSTMENT``."""
    posting, origin = aliased(period), aliased(period)
    tenant_id = subledger_line.c.tenant_id
    rows = world.place.rows(
        select(
            subledger_line.c.account_role,
            gl_account.c.code,
            subledger_line.c.amount_functional,
            posting.c.period_key.label("posted_in"),
            origin.c.period_key.label("origin"),
        )
        .select_from(
            subledger_line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == tenant_id,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
            .join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == tenant_id,
                    gl_account.c.id == subledger_line.c.gl_account_id,
                ),
            )
            .join(
                posting,
                and_(posting.c.tenant_id == tenant_id, posting.c.id == subledger_line.c.period_id),
            )
            .outerjoin(
                origin,
                and_(
                    origin.c.tenant_id == tenant_id,
                    origin.c.id == subledger_line.c.origin_period_id,
                ),
            )
        )
        .where(
            subledger_line.c.contract_id == _contract_id(world),
            subledger_posting.c.posting_kind == "MANUAL_ADJUSTMENT",
        )
    )
    return sorted(
        (
            str(row["account_role"]),
            str(row["code"]),
            Decimal(row["amount_functional"]),
            str(row["posted_in"]),
            None if row["origin"] is None else str(row["origin"]),
        )
        for row in rows
    )


def _lines_in(world: ReportWorld, period_key: str) -> tuple[int, Decimal]:
    """(count, Σ|functional amount|) of the contract's sealed lines posted in ``period_key``."""
    (row,) = world.place.rows(
        select(
            func.count().label("lines"),
            func.coalesce(func.sum(func.abs(subledger_line.c.amount_functional)), 0).label("total"),
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
        .where(
            subledger_line.c.contract_id == _contract_id(world),
            period.c.period_key == period_key,
        )
    )
    return int(row["lines"]), Decimal(row["total"])


@pytest.mark.slow
def test_a_deferred_adjustment_approved_after_the_lock_posts_late_with_its_origin(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """PRD SM-10 / REQ-JE-019: an adjustment deferred past the lock is routed again once its
    period is closed, and its approval posts the approved lines in the first open period with the
    adjustment's period as origin (S08-R-08). The closed period keeps every figure it was locked
    with, and later computations of the contract post nothing for the adjustment (S14-R-09a)."""
    created = post(world.app, ADJUSTMENTS, world.maya, _august_journal(world))
    assert created.status_code == 201, created.text
    adjustment = created.json()
    assert (adjustment["status"], adjustment["period"]["period_key"]) == ("DRAFT", AUGUST_2026)
    path = f"{ADJUSTMENTS}/{adjustment['id']}"
    submitted = post(world.app, f"{path}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    asked = post(
        world.app,
        f"{path}/request-defer-past-lock",
        world.maya,
        {"comment": "The signed acceptance arrives after the August close"},
    )
    assert asked.status_code == 200, asked.text
    deferral = approve(world.app, str(asked.json()["approval_request_id"]), world.priya)
    assert deferral.status_code == 200, deferral.text
    deferred = _shown(world, adjustment["id"])
    assert (deferred["status"], deferred["is_deferred_past_lock"], deferred["pending_request"]) == (
        "SUBMITTED",
        True,
        None,
    )

    # August is closed through the product; the deferred adjustment did not hold the lock. The
    # lock is chronological (PRD BR-CLS-08; supervisor ruling R-6), so January to July are closed
    # first — fixture state of the order rule, nothing of the subject.
    periods_closed_before(
        world.place, world.app, world.maya, entity_id=world.entity_id, before=AUGUST_2026
    )
    _, world = period_locked(world, clock, entity_code=AVM_US, period_key=AUGUST_2026)
    assert period_state(world, AVM_US, AUGUST_2026)["state"] == "closed"
    assert _manual_lines(world) == []
    august, september = _lines_in(world, AUGUST_2026), _lines_in(world, SEPTEMBER_2026)

    # a new draft can no longer be prepared for the closed period: it would take September
    late_draft = post(world.app, ADJUSTMENTS, world.maya, _august_journal(world))
    assert late_draft.status_code == 201, late_draft.text
    assert late_draft.json()["period"]["period_key"] == SEPTEMBER_2026
    discarded = post(
        world.app,
        f"{ADJUSTMENTS}/{late_draft.json()['id']}/discard",
        world.maya,
        {"reason": "Control case of the test"},
    )
    assert discarded.status_code == 200, discarded.text

    # the deferred one is routed for posting although its period is closed, and keeps that period
    routed = post(world.app, f"{path}/submit", world.maya, {})
    assert routed.status_code == 200, routed.text
    again = routed.json()
    assert (again["status"], again["period"]["period_key"], again["is_deferred_past_lock"]) == (
        "SUBMITTED",
        AUGUST_2026,
        True,
    )
    assert again["pending_request"] == {"id": again["approval_request_id"], "purpose": "POSTING"}
    request = get(world.app, f"{APPROVALS}/{again['approval_request_id']}", world.priya)
    assert request.status_code == 200, request.text
    assert _manual_lines(world) == []  # pending: nothing posted

    decided = approve(world.app, str(again["approval_request_id"]), world.priya)
    assert decided.status_code == 200, decided.text
    posted = _shown(world, adjustment["id"])
    assert (posted["status"], posted["period"]["period_key"]) == ("POSTED", AUGUST_2026)
    assert posted["applied_event_id"] and posted["subledger_posting_id"]
    # the approved lines, in September, with August as their origin
    assert _manual_lines(world) == POSTED_LATE
    # the locked period holds exactly what it was locked with; September gained the two lines
    assert _lines_in(world, AUGUST_2026) == august
    assert _lines_in(world, SEPTEMBER_2026) == (
        september[0] + 2,
        september[1] + Decimal("4800.00"),
    )
    assert period_state(world, AVM_US, AUGUST_2026)["state"] == "closed"

    # S14-R-09a: the engine's targets carry the same origin, so recomputations emit nothing
    group_id = UUID(str(world.contracts[K01].combination_group["id"]))
    for _ in range(2):
        world.place.clock.advance(timedelta(minutes=1))
        computed(world.place, group_id)
    assert _manual_lines(world) == POSTED_LATE
    assert _lines_in(world, AUGUST_2026) == august
    assert _lines_in(world, SEPTEMBER_2026) == (
        september[0] + 2,
        september[1] + Decimal("4800.00"),
    )
