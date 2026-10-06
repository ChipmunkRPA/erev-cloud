"""The approval of an FX rate set version marks the groups its changed rates can move, and the
computation that consumes the mark without an event is an ``FX_REPUBLISH`` (item
FX-REPUBLISH-DIRTY-1; supervisor ruling R-116 (b) and the rulings of 2026-10-02 on the lane's
pre-build line; 04 T-CON-03 ``dirty_trigger`` and T-REF-11 "The groups a changed rate reaches",
rev 1.297; 05 RCP-17 rev 1.206; ENGINE_SPEC_B S15-R-18b rev 1.166).

Measured before the item, in the world of ``test_fx_remeasurement_recompute.py`` (AVM-UK in GBP;
``NS-SO-UK-7001`` in USD, 120 units delivered on 10 July 2026 — USD 54,000.00 at the July average
0.81, GBP 43,740.00): after version 2 of the average set stated July at 0.82, no group was marked
and the ledger kept its lines; nothing asked for the GBP 540.00 before the lock. Behind a lock,
the recompute the product issues posted the 540.00 in August with origin July and no source event,
and the out-of-period register refused the run; or the next event of the contract carried it and
it was told as that event's.

The periods are locked here as state rows with their lock records (``_locked``): the mark and
the register ask what a period's state is, not how it came to it. The close runs around a
corrected rate are ``tests/domain/close/test_rate_reach_db.py``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    combination_group,
    contract,
    contract_computation,
    fx_rate_set,
    fx_rate_set_version,
    legal_entity,
    period,
    period_lock,
    period_state,
    period_state_transition,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.close import rate_reach
from erev_api.domain.contracts import compute_job
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import out_of_period_register as register
from erev_api.enums import (
    ApprovalRequestStatus,
    ComputationStatus,
    ComputationTrigger,
    PrincipalKind,
)
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, insert, select, update
from support.db import TestDatabase
from support.factories import GATEWAY, activated_contract, booked_contract, open_periods
from support.reference import approve, entity, post
from support.rows import (
    CloseParts,
    approval_request_values,
    period_lock_values,
    period_state_transition_values,
)
from support.worlds import approved_manual_events
from test_combination import GROUPS
from test_fx_remeasurement_recompute import ENTITY, USD_GBP, _published_version, delivered
from test_fx_remeasurement_recompute import World as FxWorld
from test_fx_remeasurement_recompute import world as fx  # noqa: F401  (the FX world's fixture)

JULY, AUGUST, SEPTEMBER = "FY2026-P07", "FY2026-P08", "FY2026-P09"
FX_REPUBLISH = ComputationTrigger.FX_REPUBLISH.value
SECOND_DELIVERY = {
    "event_type": "DELIVERY_RECORDED",
    "effective_date": "2026-08-12",
    "payload": {"obligation_key": "O1", "quantity": "40", "trigger": "DELIVERY"},
}

Line = tuple[str, str, str, str, Decimal, Decimal]  # trigger, period, origin, role, txn, functional


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


# --- the world's rates and what is read of a group ------------------------------------------------


def _average(july: str = "0.810000", august: str = "0.830000", september: str = "0.835000") -> Any:
    return [
        {**USD_GBP, "rate": july, "period_key": JULY},
        {**USD_GBP, "rate": august, "period_key": AUGUST},
        {**USD_GBP, "rate": september, "period_key": SEPTEMBER},
    ]


def _spot(first: str = "0.800000", second: str = "0.840000") -> Any:
    return [
        {**USD_GBP, "rate": first, "effective_date": "2026-07-01"},
        {**USD_GBP, "rate": second, "effective_date": "2026-08-20"},
    ]


def _published(world: FxWorld, rate_type: str, rates: Any) -> Any:
    """The next version of the world's ``rate_type`` set, approved; its ``published_at``."""
    set_id = world.place.scalar(
        select(fx_rate_set.c.id).where(fx_rate_set.c.code == f"AVM-UK-{rate_type.upper()}")
    )
    _published_version(world.app, world.maya, world.marcus, str(set_id), rates)
    return world.place.scalar(
        select(fx_rate_set_version.c.published_at)
        .where(fx_rate_set_version.c.fx_rate_set_id == set_id)
        .order_by(fx_rate_set_version.c.version_no.desc())
        .limit(1)
    )


def _mark(world: FxWorld, group_id: UUID) -> tuple[Any, str | None]:
    (row,) = world.place.rows(
        select(combination_group.c.dirty_since, combination_group.c.dirty_trigger).where(
            combination_group.c.id == group_id
        )
    )
    trigger = row["dirty_trigger"]
    return row["dirty_since"], None if trigger is None else str(getattr(trigger, "value", trigger))


def _lines(world: FxWorld, contract_id: UUID) -> list[Line]:
    """Every sealed line of the contract with the trigger of the computation that posted it."""
    origin = period.alias("origin_period")
    rows = world.place.rows(
        select(
            contract_computation.c.trigger,
            period.c.period_key,
            origin.c.period_key.label("origin_key"),
            subledger_line.c.account_role,
            subledger_line.c.amount_txn,
            subledger_line.c.amount_functional,
        )
        .select_from(
            subledger_line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == subledger_line.c.tenant_id,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
            .join(
                contract_computation,
                and_(
                    contract_computation.c.tenant_id == subledger_line.c.tenant_id,
                    contract_computation.c.id == subledger_posting.c.contract_computation_id,
                ),
            )
            .join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
            .outerjoin(
                origin,
                and_(
                    origin.c.tenant_id == subledger_line.c.tenant_id,
                    origin.c.id == subledger_line.c.origin_period_id,
                ),
            )
        )
        .where(subledger_line.c.contract_id == contract_id)
    )
    return sorted(
        (
            str(getattr(row["trigger"], "value", row["trigger"])),
            str(row["period_key"]),
            str(row["origin_key"] or "-"),
            str(row["account_role"]),
            Decimal(row["amount_txn"]),
            Decimal(row["amount_functional"]),
        )
        for row in rows
    )


def _recomputed(world: FxWorld, group_id: UUID) -> dict[str, Any]:
    """The group computed as the close run's ``RECOMPUTE_DIRTY`` and a job compute it: asked under
    ``COMMAND``, bringing no event. The stored computation row."""
    with world.place.uow() as uow:
        outcome = compute_job.compute_group(uow, group_id, trigger=ComputationTrigger.COMMAND)
        uow.commit()
    assert outcome.status is ComputationStatus.SUCCEEDED and outcome.computation is not None
    return dict(outcome.computation)


def _locked(world: FxWorld, period_key: str) -> None:
    """The period of AVM-UK closed as fixture state: its state row ``closed`` through ``closing``,
    with the transitions and the lock record a lock decision writes."""
    tenant_id = world.place.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        entity_id, calendar_id = session.execute(
            select(legal_entity.c.id, legal_entity.c.calendar_id).where(
                legal_entity.c.code == ENTITY
            )
        ).one()
        period_id = session.execute(
            select(period.c.id).where(
                period.c.calendar_id == calendar_id, period.c.period_key == period_key
            )
        ).scalar_one()
        state_id = session.execute(
            select(period_state.c.id).where(
                period_state.c.entity_id == entity_id,
                period_state.c.period_id == period_id,
                period_state.c.book_code == "ASC606",
            )
        ).scalar_one()
        request = approval_request_values(tenant_id, status=ApprovalRequestStatus.APPROVED)
        session.execute(insert(approval_request).values(**request))
        for from_state, to_state in (("open", "closing"), ("closing", "closed")):
            transition = period_state_transition_values(
                tenant_id,
                period_state_id=state_id,
                entity_id=entity_id,
                period_id=period_id,
                from_state=from_state,
                to_state=to_state,
            )
            if to_state == "closed":
                parts = CloseParts(
                    calendar_id=calendar_id,
                    entity_id=entity_id,
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


def _register(world: FxWorld) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """RPT-16, the out-of-period register of AVM-UK over 2026, built as a live run: its rows and
    its control totals."""
    entity_id = world.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == ENTITY))
    with world.place.uow() as uow:
        data = register.build(
            uow,
            ReportParams(
                report_code=register.CODE,
                report_version=1,
                parameters={"from_period_key": "FY2026-P01", "to_period_key": "FY2026-P12"},
                entity_ids=(UUID(str(entity_id)),),
                known_at=world.place.clock.now(),
                historical=False,
            ),
        )
    return [dict(row) for row in data.rows], dict(data.control_totals)


def _gateways(world: FxWorld, external_id: str, inception: str) -> tuple[UUID, UUID]:
    """Another USD contract of AVM-UK — 200 gateway units for USD 90,000.00 — booked and
    activated on ``inception``; nothing delivered. Returns (contract id, group id)."""
    body = {
        "external_id": external_id,
        "customer_id": str(world.customer_id),
        "contracting_entity_code": ENTITY,
        "transaction_currency": "USD",
        "inception_date": inception,
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
    return UUID(str(booked.contract["id"])), UUID(str(booked.combination_group["id"]))


# --- the mark, and the computation that consumes it -----------------------------------------------


def test_the_approval_marks_the_group_and_its_recompute_is_an_fx_republish(
    fx: FxWorld,  # noqa: F811
) -> None:
    """July open. The approval of the version that states July at 0.82 marks the group — at the
    version's own instant, with the trigger ``FX_REPUBLISH`` — and posts nothing. The group's
    next computation that brings no event (the close run's ``RECOMPUTE_DIRTY``, a job) is stored
    under that trigger, posts the difference in July — USD 54,000.00 at 0.82 less 0.81, GBP
    540.00, no transaction amount — and ends the mark and its trigger together."""
    contract_id, group_id = delivered(fx)
    assert _mark(fx, group_id) == (None, None)
    before = _lines(fx, contract_id)

    published_at = _published(fx, "average", _average(july="0.820000"))

    assert _mark(fx, group_id) == (published_at, FX_REPUBLISH)
    assert _lines(fx, contract_id) == before
    stored = _recomputed(fx, group_id)
    assert str(getattr(stored["trigger"], "value", stored["trigger"])) == FX_REPUBLISH
    assert [line for line in _lines(fx, contract_id) if line not in before] == [
        (FX_REPUBLISH, JULY, "-", "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("540.0000")),
        (FX_REPUBLISH, JULY, "-", "REVENUE", Decimal("0.0000"), Decimal("-540.0000")),
    ]
    assert _mark(fx, group_id) == (None, None)


def test_a_second_correction_before_any_recompute_moves_the_stamp_to_its_own_instant(
    fx: FxWorld,  # noqa: F811
) -> None:
    """05 RCP-17: the mark is the later of the stamp that stands and the approval's instant.
    July's average is corrected to 0.82 and the group is marked at that version's instant.
    Before anything recomputes it a second version corrects July again, a minute later: the
    group keeps its trigger and its stamp is the second version's instant, not the first's.

    Fail-first, measured 2026-10-03 with the update keeping a stamp that stands
    (``coalesce(dirty_since, now)``, the mutation ``stamp-kept``): the stamp stayed at the
    first version's instant, and no other database witness of the item saw it — each marks
    a group that is clean."""
    _, group_id = delivered(fx)
    first = _published(fx, "average", _average(july="0.820000"))
    assert _mark(fx, group_id) == (first, FX_REPUBLISH)

    fx.place.clock.advance(timedelta(minutes=1))
    second = _published(fx, "average", _average(july="0.825000"))

    assert second > first
    assert _mark(fx, group_id) == (second, FX_REPUBLISH)


def test_a_version_that_repeats_the_rates_in_force_marks_nothing(fx: FxWorld) -> None:  # noqa: F811
    """A version changes a key when the rate in force for it differs with the version and
    without it. One that restates what is in force changes none: no group is marked."""
    _, group_id = delivered(fx)
    _published(fx, "average", _average())
    _published(fx, "spot", _spot())
    assert _mark(fx, group_id) == (None, None)


def test_behind_a_lock_the_difference_is_listed_as_an_fx_republish(fx: FxWorld) -> None:  # noqa: F811
    """July closed. The approval marks the group all the same (the rule's reach holds locked
    periods: the engine carries the difference at the next computation whatever is marked). The
    recompute posts the GBP 540.00 in August with July as its origin, under ``FX_REPUBLISH`` —
    and the out-of-period register lists it: ONE row, attributed to the trigger, "Fx republish",
    two lines, no effect in the transaction currency. Before the item the same two lines were
    posted under ``COMMAND`` with no source event, and the register refused."""
    contract_id, group_id = delivered(fx)
    before = _lines(fx, contract_id)
    _locked(fx, JULY)

    published_at = _published(fx, "average", _average(july="0.820000"))

    assert _mark(fx, group_id) == (published_at, FX_REPUBLISH)
    stored = _recomputed(fx, group_id)
    assert [line for line in _lines(fx, contract_id) if line not in before] == [
        (FX_REPUBLISH, AUGUST, JULY, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("540.0000")),
        (FX_REPUBLISH, AUGUST, JULY, "REVENUE", Decimal("0.0000"), Decimal("-540.0000")),
    ]
    assert _mark(fx, group_id) == (None, None)
    (row,), totals = _register(fx)
    assert {
        "origin": row["origin_period_key"],
        "posting": row["posting_period_key"],
        "attribution": row["attribution_kind"],
        "event": row["event_key"],
        "label": row["event_type_label"],
        "currency": row["currency"],
        "revenue": Decimal(str(row["revenue_effect"]["amount"])),
        "balance": Decimal(str(row["balance_effect"]["amount"])),
    } == {
        "origin": JULY,
        "posting": AUGUST,
        "attribution": "TRIGGER",
        "event": f"trigger:{FX_REPUBLISH}:{stored['id']}",
        "label": "Fx republish",
        "currency": "USD",
        "revenue": Decimal(0),
        "balance": Decimal(0),
    }
    assert (totals["row_count"], totals["line_count"]) == (1, 2)


def test_an_event_that_comes_first_carries_the_difference_as_its_own(fx: FxWorld) -> None:  # noqa: F811
    """July closed and the group marked. Before any recompute a second delivery is recorded — 40
    units on 12 August. Its computation brings an event: it stays ``COMMAND``, posts August's
    revenue (USD 18,000.00 at 0.83, GBP 14,940.00) and, as a second entry, July's GBP 540.00 with
    its origin, and ends the mark. The register lists that entry under the delivery."""
    contract_id, group_id = delivered(fx)
    before = _lines(fx, contract_id)
    _locked(fx, JULY)
    _published(fx, "average", _average(july="0.820000"))
    assert _mark(fx, group_id)[1] == FX_REPUBLISH

    recorded = approved_manual_events(
        fx.place, fx.priya, contract_id, SECOND_DELIVERY, evidence_file_ids=[]
    )

    assert recorded["computation"]["status"] == "SUCCEEDED"
    assert [line for line in _lines(fx, contract_id) if line not in before] == [
        (
            "COMMAND",
            AUGUST,
            "-",
            "CONTRACT_LIABILITY",
            Decimal("18000.0000"),
            Decimal("14940.0000"),
        ),
        ("COMMAND", AUGUST, "-", "REVENUE", Decimal("-18000.0000"), Decimal("-14940.0000")),
        ("COMMAND", AUGUST, JULY, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("540.0000")),
        ("COMMAND", AUGUST, JULY, "REVENUE", Decimal("0.0000"), Decimal("-540.0000")),
    ]
    assert _mark(fx, group_id) == (None, None)
    (row,), totals = _register(fx)
    assert (
        row["attribution_kind"],
        row["lineage_scope"],
        row["event_key"],
        row["event_type_label"],
    ) == ("EVENT_SET", "SUBJECT", "event:NS-SO-UK-7001:4:SUBJECT", "Delivery recorded")
    assert (totals["row_count"], totals["line_count"]) == (1, 2)


# --- the reach ------------------------------------------------------------------------------------


def test_the_reach_leaves_out_what_no_line_of_the_period_can_be_made_of(fx: FxWorld) -> None:  # noqa: F811
    """Three USD contracts of AVM-UK. ``NS-SO-UK-7001`` delivered in July and holds a contract
    asset; ``NS-SO-UK-7002`` was booked and activated on 1 July and has nothing else;
    ``NS-SO-UK-7003`` begins on 1 September.

    A corrected AUGUST average reaches August. It marks the first for its position alone — no
    event, schedule line or sealed line of it is dated in August or later — and neither of the
    others: the second is at rest before the reach, the third has not begun by its end. A
    corrected SEPTEMBER average then marks the first again and the third, which is at work in
    September, and still not the second."""
    _, held = delivered(fx)
    _, at_rest = _gateways(fx, "NS-SO-UK-7002", "2026-07-01")
    _, later = _gateways(fx, "NS-SO-UK-7003", "2026-09-01")

    stamped = _published(fx, "average", _average(august="0.840000"))

    assert _mark(fx, held) == (stamped, FX_REPUBLISH)
    assert _mark(fx, at_rest) == (None, None)
    assert _mark(fx, later) == (None, None)
    _recomputed(fx, held)
    assert _mark(fx, held) == (None, None)

    stamped = _published(fx, "average", _average(august="0.840000", september="0.845000"))

    assert _mark(fx, held) == (stamped, FX_REPUBLISH)
    assert _mark(fx, later) == (stamped, FX_REPUBLISH)
    assert _mark(fx, at_rest) == (None, None)


def test_a_spot_rate_reaches_to_the_day_before_the_next_spot_date(fx: FxWorld) -> None:  # noqa: F811
    """The world's spot rates are dated 1 July and 20 August. The rate of 1 July answers for a
    flow dated up to 19 August: corrected, it reaches July and August — the contract that
    delivered in July is marked, the one that begins on 1 September is not. The rate of 20
    August has no successor: corrected, it reaches from August onward, and both are marked."""
    _, delivered_in_july = delivered(fx)
    _, begins_in_september = _gateways(fx, "NS-SO-UK-7003", "2026-09-01")

    stamped = _published(fx, "spot", _spot(first="0.805000"))

    assert _mark(fx, delivered_in_july) == (stamped, FX_REPUBLISH)
    assert _mark(fx, begins_in_september) == (None, None)
    _recomputed(fx, delivered_in_july)

    stamped = _published(fx, "spot", _spot(first="0.805000", second="0.845000"))

    assert _mark(fx, delivered_in_july) == (stamped, FX_REPUBLISH)
    assert _mark(fx, begins_in_september) == (stamped, FX_REPUBLISH)


def test_a_rate_a_version_takes_away_reaches_like_a_changed_one(fx: FxWorld) -> None:  # noqa: F811
    """04 T-REF-11: a version answers for its whole coverage. One that covers July and does not
    state July's average takes that rate away — a changed key like a value that differs: the
    group at work in July is marked."""
    _, group_id = delivered(fx)

    stamped = _published(fx, "average", [row for row in _average() if row["period_key"] != JULY])

    assert _mark(fx, group_id) == (stamped, FX_REPUBLISH)


def test_the_reach_is_by_pair_and_by_the_entity_that_posts(fx: FxWorld) -> None:  # noqa: F811
    """A second entity, AVM-US in USD, on AVM-UK's calendar, with a USD contract of its own
    activated on 1 July. The version that corrects the USD to GBP average of July changes two
    keys — the rate entered and the inverse its submission derived, GBP to USD — and each
    reaches the entities of ITS quote currency: AVM-UK for USD to GBP, AVM-US for GBP to USD.

    The USD group of AVM-UK is marked. The USD group of AVM-US is at work in July as well and is
    not marked: AVM-UK does not post for it, and the key that reaches AVM-US is of another base
    currency. (Measured on the statement before its correction: the performing clause was
    joined to the whole reach, and this group was marked through AVM-UK's row.)"""
    _, uk_group = delivered(fx)
    uk_id, calendar_id = fx.place.rows(
        select(legal_entity.c.id, legal_entity.c.calendar_id).where(legal_entity.c.code == ENTITY)
    )[0].values()
    created = entity(
        fx.app,
        fx.maya,
        code="AVM-US",
        calendar_id=str(calendar_id),
        functional_currency="USD",
        time_zone="America/New_York",
    )
    open_periods(
        fx.app, fx.maya, entity_code="AVM-US", keys=[f"FY2026-P{m:02d}" for m in range(1, 10)]
    )
    booked = activated_contract(
        fx.place,
        booked_contract(
            fx.place,
            {
                "external_id": "NS-SO-US-7100",
                "customer_id": str(fx.customer_id),
                "contracting_entity_code": "AVM-US",
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
            },
            activate=False,
        ),
    )
    us_group = UUID(str(booked.combination_group["id"]))

    stamped = _published(fx, "average", _average(july="0.820000"))

    set_id = fx.place.scalar(select(fx_rate_set.c.id).where(fx_rate_set.c.code == "AVM-UK-AVERAGE"))
    version_id = fx.place.scalar(
        select(fx_rate_set_version.c.id)
        .where(fx_rate_set_version.c.fx_rate_set_id == set_id)
        .order_by(fx_rate_set_version.c.version_no.desc())
        .limit(1)
    )
    reached = fx.place.rows(rate_reach.reach_statement(UUID(str(version_id))))
    assert sorted(
        (str(row["entity_id"]), str(row["base_currency"]).strip()) for row in reached
    ) == (sorted([(str(uk_id), "USD"), (str(created["id"]), "GBP")]))
    assert _mark(fx, uk_group) == (stamped, FX_REPUBLISH)
    assert _mark(fx, us_group) == (None, None)


# --- the mark and a combination -------------------------------------------------------------------


def test_a_marked_group_a_combination_empties_keeps_neither_mark_nor_trigger(
    fx: FxWorld,  # noqa: F811
) -> None:
    """04 T-CON-03: a trigger is carried by a mark only. The group of ``NS-SO-UK-7001`` is marked
    by a corrected rate; the contract then joins another in a new group by the approved command.
    The combination ends the mark of the group it leaves without a member
    (COMBINE-EMPTY-GROUP-DIRTY-1) — and the trigger with it — and computes the new group, which
    is clean and carries none."""
    contract_id, own_group = delivered(fx)
    other_id, _ = _gateways(fx, "NS-SO-UK-7002", "2026-07-01")
    _published(fx, "average", _average(july="0.820000"))
    assert _mark(fx, own_group)[1] == FX_REPUBLISH

    proposed = post(
        fx.app,
        GROUPS,
        fx.maya,
        {
            "contract_ids": [str(contract_id), str(other_id)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(fx.app, f"{GROUPS}/{group_id}/submit", fx.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(fx.app, submitted.json()["approval_request_id"], fx.marcus)

    assert approved.status_code == 200, approved.text
    assert _mark(fx, own_group) == (None, None)
    assert _mark(fx, group_id) == (None, None)
    assert (
        fx.place.scalar(select(contract.c.combination_group_id).where(contract.c.id == contract_id))
        == group_id
    )
