"""CLO-5 data-quality monitors (BUILD_SPEC CLO-5 acceptance; 04 table 15.4-E; REQ-CLS-019; T-IMP-05;
T-PLT-31; PRD NTF-11; supervisor rulings Q-4, Q-5, Q-8 of docs/reviews/loop/prod/F-CLO-prep.md).

DB-bound (``CloseWorld``). Written in the CLO-5 implementation slice on a worktree whose lane
databases were never provisioned: NOT RUN there; measured by the integrated batch on merged main.
Each test inserts the rows of one monitor's source and runs ``monitors.run_monitors`` for AVM-US,
ASC606, FY2026-P09 (1 to 30 September 2026), as the SYSTEM-principal cockpit refresh does.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_request,
    audit_event,
    calc_trace,
    contract,
    contract_computation,
    contract_version,
    contract_version_balance,
    engine_release,
    exception_item,
    fx_layer_movement,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    notification,
    obligation,
    obligation_version,
    period,
    period_state,
    pob_template,
    pob_template_version,
    product,
    rule,
    rule_set,
    rule_set_version,
    schedule,
    schedule_line,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.close import gates, monitor_rules, monitors
from erev_api.domain.imports.exceptions import raise_exception_item
from erev_api.enums import (
    ApprovalRequestStatus,
    BookCode,
    ChecklistStatus,
    ConfigStatus,
    ContractStatus,
    ExceptionSeverity,
    ExceptionSource,
    NotificationKind,
    RateType,
    RuleSetKind,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from support.close_world import (
    BOOK,
    CloseWorld,
    close_world,
    contract_of,
    identity_duplicates,
    other_entity,
    published_version,
    system_session,
)
from support.db import TestDatabase
from support.reference import PERIODS, get, post
from support.rows import (
    ContractRows,
    LedgerParts,
    approval_request_values,
    calc_trace_values,
    contract_computation_values,
    contract_version_balance_values,
    contract_version_values,
    engine_release_values,
    fx_rate_set_values,
    fx_rate_set_version_values,
    fx_rate_values,
    gl_account_values,
    ledger_seal_values,
    obligation_values,
    obligation_version_values,
    period_state_values,
    pob_template_values,
    pob_template_version_values,
    product_values,
    rule_set_values,
    rule_set_version_values,
    rule_values,
    schedule_line_values,
    schedule_values,
    subledger_line_values,
    subledger_posting_values,
)

PERIOD_END = date(2026, 9, 30)
ENTITY_CODE = "AVM-US"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


# --- helpers -------------------------------------------------------------------------------------


def _run(world: CloseWorld) -> monitors.MonitorRun:
    with world.place.uow() as uow:
        run = monitors.run_monitors(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    return run


def _items(world: CloseWorld, code: str) -> list[Mapping[str, Any]]:
    with system_session(world) as session:
        rows = (
            session.execute(
                select(exception_item)
                .where(exception_item.c.code == code)
                .order_by(exception_item.c.created_at, exception_item.c.id)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def _gate(world: CloseWorld) -> gates.GateResult:
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    return next(result for result in results if result.gate_check_code == gates.DATA_QUALITY_CLEAR)


def _version(
    session: Session,
    world: CloseWorld,
    *,
    version_columns: Mapping[str, Any] | None = None,
    **contract_columns: Any,
) -> tuple[UUID, UUID, UUID, UUID]:
    """A contract of AVM-US with a computation and version 1: (contract, event, group, version).
    ``contract_columns`` are set at creation — the projection changes only through appended events
    afterwards (EREV-CON-001)."""
    contract_id, event_id, group_id = contract_of(session, world, **contract_columns)
    release = engine_release_values()
    session.execute(insert(engine_release).values(**release))
    computation = contract_computation_values(
        world.tenant_id, combination_group_id=group_id, engine_release_id=release["id"]
    )
    session.execute(insert(contract_computation).values(**computation))
    trace = calc_trace_values(
        world.tenant_id, contract_version_id=UUID(int=0), combination_group_id=group_id
    )
    version = contract_version_values(
        world.tenant_id,
        combination_group_id=group_id,
        contract_computation_id=computation["id"],
        calc_trace_id=trace["id"],
        **dict(version_columns or {}),
    )
    trace["contract_version_id"] = version["id"]
    version_id = UUID(str(version["id"]))
    session.execute(insert(calc_trace).values(**trace))
    session.execute(insert(contract_version).values(**version))
    return contract_id, event_id, group_id, version_id


def _period(session: Session, world: CloseWorld, key: str) -> tuple[UUID, date]:
    row = session.execute(
        select(period.c.id, period.c.end_date).where(period.c.period_key == key)
    ).one()
    return UUID(str(row.id)), row.end_date


# --- the eight CLO-5 tests -----------------------------------------------------------------------


def test_dq_duplicate_invoice(world: CloseWorld) -> None:
    with system_session(world) as session:
        identity_duplicates(session, world, issue_date=date(2026, 9, 3))
    run = _run(world)
    (item,) = _items(world, "DQ_DUPLICATE_INVOICE")
    assert (item["severity"], item["source"], item["status"]) == (
        ExceptionSeverity.BLOCKING.value,
        ExceptionSource.DATA_QUALITY.value,
        "OPEN",
    )
    # D-98 57: the identity carries the affected scope (entity, period) before the subject.
    assert item["dedupe_key"] == (
        f"DATA_QUALITY:DQ_DUPLICATE_INVOICE:{world.entity_id}:{world.period_id}:"
        "CUST-7:A-1001:1200.00:2026-09-03"
    )
    assert (item["entity_id"], item["period_id"]) == (world.entity_id, world.period_id)
    assert run.created == 1 and run.open_blocking == 1
    # NTF-11 to the entity's Revenue Accountants (maya holds revenue_accountant; ruling Q-5).
    with system_session(world) as session:
        kinds = (
            session.execute(
                select(notification.c.kind).where(
                    notification.c.recipient_membership_id == world.maya.member.membership_id,
                    notification.c.subject_id == item["id"],
                )
            )
            .scalars()
            .all()
        )
    assert [str(kind) for kind in kinds] == [NotificationKind.EXCEPTION_ASSIGNED.value]


@pytest.mark.parametrize(
    ("first_revenue", "expected"),
    [(date(2026, 7, 31), 1), (date(2026, 8, 1), 0)],  # 61 days > 60; exactly 60 does not
    ids=["61-days", "60-days"],
)
def test_dq_revenue_without_billing_threshold(
    world: CloseWorld, first_revenue: date, expected: int
) -> None:
    with system_session(world) as session:
        # The chain of AVM-US itself: ``insert_version_rows(entity_id=<existing>)`` would try to
        # insert a second legal entity under that id, fall back to a phantom id and post lines into
        # a period without a state (EREV-LED-003 in the batch on main 0cb36c14).
        contract_id, _, group_id, version_id = _version(session, world)
        customer_id, computation_id = session.execute(
            select(contract.c.customer_id, contract_version.c.contract_computation_id)
            .select_from(contract.join(contract_version, contract_version.c.id == version_id))
            .where(contract.c.id == contract_id)
        ).one()
        chain = ContractRows(
            entity_id=world.entity_id,
            customer_id=UUID(str(customer_id)),
            group_id=group_id,
            contract_id=contract_id,
        )
        account = gl_account_values(world.tenant_id)
        session.execute(insert(gl_account).values(**account))
        july_id, july_end = _period(session, world, "FY2026-P07")
        parts = LedgerParts(
            chain=chain,
            computation_id=UUID(str(computation_id)),
            period_id=july_id,
            period_end_date=july_end,
            account_id=UUID(str(account["id"])),
        )
        posting = subledger_posting_values(world.tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        # A balanced revenue recognition entry (Dr contract liability / Cr revenue), sealed so the
        # deferred DB-06 seal constraint holds at commit (Codex R3).
        lines = [
            subledger_line_values(
                world.tenant_id,
                posting=posting,
                parts=parts,
                amount=amount,
                effective_date=first_revenue,
                entry_kind="REVENUE_RECOGNITION",
            )
            for amount in (Decimal("100.00"), Decimal("-100.00"))
        ]
        session.execute(insert(subledger_line), lines)
        seal = ledger_seal_values(session, world.tenant_id, posting=posting, lines=lines)
        session.execute(insert(subledger_posting_seal).values(**seal))
    run = _run(world)
    items = _items(world, "DQ_REVENUE_WITHOUT_BILLING")
    assert len(items) == expected
    if expected:
        assert items[0]["severity"] == ExceptionSeverity.WARNING.value
        assert items[0]["dedupe_key"] == (
            f"DATA_QUALITY:DQ_REVENUE_WITHOUT_BILLING:{world.entity_id}:{world.period_id}:"
            f"{contract_id}"
        )
        assert run.open_blocking == 0  # a WARNING never blocks the lock


def test_dq_negative_liability_layer(world: CloseWorld) -> None:
    """04 T-CON-09: every labelled balance column is non-negative — the CHECK
    ``ck_contract_version_balance__contract_liability_txn`` refuses the interim source's negative
    seed, so aggregate balances cannot represent the negative-layer condition. The monitor now
    reads T-CON-18; an old version without movement rows provides no layer coverage."""
    with system_session(world) as session:
        contract_id, _, _, version_id = _version(session, world)
        negative = contract_version_balance_values(
            world.tenant_id,
            contract_version_id=version_id,
            contract_id=contract_id,
            entity_id=world.entity_id,
            contract_liability_txn=Decimal("-0.01"),
        )
        savepoint = session.begin_nested()
        with pytest.raises(IntegrityError) as refused:
            session.execute(insert(contract_version_balance).values(**negative))
        savepoint.rollback()
        assert "ck_contract_version_balance__contract_liability_txn" in str(refused.value)
        session.execute(
            insert(contract_version_balance).values(
                **contract_version_balance_values(
                    world.tenant_id,
                    contract_version_id=version_id,
                    contract_id=contract_id,
                    entity_id=world.entity_id,
                    contract_liability_txn=Decimal("0.00"),
                )
            )
        )
    run = _run(world)
    assert _items(world, "DQ_NEGATIVE_LIABILITY_LAYER") == []
    assert run.open_blocking == 0
    assert _gate(world).status is ChecklistStatus.PASSED


def test_dq_recognition_after_pob_end(world: CloseWorld) -> None:
    with system_session(world) as session:
        # DB-17 V1 (0054, EREV-ALC-001): the obligation versions' allocations equal the version's
        # transaction price less consideration payable — the one obligation allocates 100.
        contract_id, event_id, group_id, version_id = _version(
            session, world, version_columns={"transaction_price": Decimal("100")}
        )
        item_product = product_values(world.tenant_id)
        session.execute(insert(product).values(**item_product))
        template = pob_template_values(world.tenant_id)
        session.execute(insert(pob_template).values(**template))
        template_version = published_version(
            session,
            world,
            pob_template_version,
            pob_template_version_values(world.tenant_id, pob_template_id=template["id"]),
        )
        pob = obligation_values(
            world.tenant_id,
            contract_id=contract_id,
            product_id=item_product["id"],
            created_by_event_id=event_id,
        )
        session.execute(insert(obligation).values(**pob))
        pob_version = obligation_version_values(
            world.tenant_id,
            contract_version_id=version_id,
            obligation_id=pob["id"],
            contract_id=contract_id,
            combination_group_id=group_id,
            product_id=item_product["id"],
            pob_template_version_id=template_version["id"],
            entity_id=world.entity_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 8, 31),  # the obligation ended before September starts
        )
        session.execute(insert(obligation_version).values(**pob_version))
        plan = schedule_values(
            world.tenant_id, contract_version_id=version_id, combination_group_id=group_id
        )
        session.execute(insert(schedule).values(**plan))
        line = schedule_line_values(
            world.tenant_id,
            schedule_id=plan["id"],
            contract_version_id=version_id,
            contract_id=contract_id,
            entity_id=world.entity_id,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            subject_type="obligation",
            subject_id=pob["id"],
            amount=Decimal("100.00"),
            cumulative_amount=Decimal("100.00"),
            cumulative_exact=Decimal(100),
        )
        session.execute(insert(schedule_line).values(**line))
    _run(world)
    (item,) = _items(world, "DQ_RECOGNITION_AFTER_POB_END")
    assert item["severity"] == ExceptionSeverity.WARNING.value
    assert item["obligation_id"] == pob["id"]
    assert item["dedupe_key"] == (
        f"DATA_QUALITY:DQ_RECOGNITION_AFTER_POB_END:{world.entity_id}:{world.period_id}:"
        f"{pob['id']}:2026-09-01"
    )


@pytest.mark.parametrize(
    ("last_event", "expected"),
    [(date(2026, 7, 1), 1), (date(2026, 7, 2), 0)],  # 91 days > 90; exactly 90 does not
    ids=["91-days", "90-days"],
)
def test_dq_inactive_contract(world: CloseWorld, last_event: date, expected: int) -> None:
    with system_session(world) as session:
        contract_id, event_id, _ = contract_of(
            session, world, status=ContractStatus.ACTIVE.value, event_effective_date=last_event
        )
    _run(world)
    items = _items(world, "DQ_INACTIVE_CONTRACT")
    assert len(items) == expected
    if expected:
        assert items[0]["severity"] == ExceptionSeverity.WARNING.value
        assert items[0]["contract_id"] == contract_id


def test_fx_rate_missing_monitor(world: CloseWorld) -> None:
    with system_session(world) as session:
        contract_id, _, _ = contract_of(
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            transaction_currency="EUR",
            event_effective_date=date(2026, 9, 15),  # recent: no inactivity finding (0829 R1)
        )  # AVM-US keeps USD functional currency
    run = _run(world)
    (item,) = _items(world, "FX_RATE_MISSING")
    assert item["severity"] == ExceptionSeverity.BLOCKING.value
    assert item["dedupe_key"] == (
        f"DATA_QUALITY:FX_RATE_MISSING:{world.entity_id}:{world.period_id}:EUR:USD:2026-09-30"
    )
    assert run.open_blocking == 1
    # An APPROVED closing rate for the period end clears the condition: the next run no longer
    # finds it, does not count the item again and settles it — RESOLVED by the system (04 T-IMP-05
    # rev 1.185; supervisor ruling R-111 (j), item DQ-RESOLVE-1). Until then the item stayed OPEN
    # (ruling Q-11), and nobody but an approver of a waiver could clear it.
    _approve_closing_rate(world)
    again = _run(world)
    assert again.outcome.findings == ()
    (same,) = _items(world, "FX_RATE_MISSING")
    assert (same["id"], same["occurrence_count"]) == (item["id"], 1)
    assert (same["status"], again.settled, again.open_blocking) == ("RESOLVED", (item["id"],), 0)


def test_monitor_rerun_is_idempotent(world: CloseWorld) -> None:
    with system_session(world) as session:
        contract_id, event_id, _ = contract_of(
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            event_effective_date=date(2026, 5, 1),
        )
    first = _run(world)
    second = _run(world)
    items = _items(world, "DQ_INACTIVE_CONTRACT")
    assert len(items) == 1
    assert items[0]["occurrence_count"] == 2
    assert (first.created, first.seen_again) == (1, 0)
    assert (second.created, second.seen_again) == (0, 1)
    assert first.outcome.dedupe_keys() == second.outcome.dedupe_keys()


def test_tenant_rule_overrides_severity(world: CloseWorld) -> None:
    with system_session(world) as session:
        tenant_set = rule_set_values(
            world.tenant_id, code="DQ-TENANT", kind=RuleSetKind.DATA_QUALITY
        )
        session.execute(insert(rule_set).values(**tenant_set))
        tenant_version = rule_set_version_values(
            world.tenant_id, rule_set_id=tenant_set["id"], kind=RuleSetKind.DATA_QUALITY
        )
        # The override rule is a child row of the version: written while the version is TESTED,
        # before publication (tg_rule__config_child; Codex production-20260921-0304).
        override = rule_values(
            world.tenant_id,
            rule_set_version_id=tenant_version["id"],
            rule_key="DQ_INACTIVE_CONTRACT",
            kind=RuleSetKind.DATA_QUALITY,
            conditions=[],
            outputs={"severity": "ERROR", "message": "Inactive contracts block the close here."},
        )
        published_version(
            session, world, rule_set_version, tenant_version, children=[(rule, override)]
        )
        contract_id, event_id, _ = contract_of(
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            event_effective_date=date(2026, 5, 1),
        )
    run = _run(world)
    (item,) = _items(world, "DQ_INACTIVE_CONTRACT")
    assert item["severity"] == ExceptionSeverity.BLOCKING.value  # table 15.4-E: ERROR → BLOCKING
    assert run.open_blocking == 1
    gate = _gate(world)
    assert (gate.status, gate.count, gate.detail) == (
        ChecklistStatus.FAILED,
        1,
        "Data-quality errors: 1",
    )


# --- D-98 57 / 58 (Codex CLO-5 review R1, R2) and the positive controls ---


def _run_for(world: CloseWorld, entity_id: UUID, period_id: UUID) -> monitors.MonitorRun:
    with world.place.uow() as uow:
        run = monitors.run_monitors(uow, entity_id, BOOK, period_id)
        uow.commit()
    return run


def test_scope_september_recurrence_of_an_august_duplicate_is_its_own_item(
    world: CloseWorld,
) -> None:
    # R1 native case 1: the same unresolved duplicate seen in August, then in September.
    with system_session(world) as session:
        identity_duplicates(session, world, issue_date=date(2026, 8, 3))
        august_id, _ = _period(session, world, "FY2026-P08")
    august = _run_for(world, world.entity_id, august_id)
    september = _run(world)
    items = _items(world, "DQ_DUPLICATE_INVOICE")
    assert [item["period_id"] for item in items] == [august_id, world.period_id]
    assert len({item["dedupe_key"] for item in items}) == 2
    assert all(item["occurrence_count"] == 1 for item in items)  # no bump on the first item
    assert (august.open_blocking, september.open_blocking) == (1, 1)
    assert _gate(world).status is ChecklistStatus.FAILED  # September's own scope blocks


def test_scope_entity_b_after_entity_a_missing_fx_rate(world: CloseWorld) -> None:
    # R1 native case 2: the same missing EUR→USD closing rate in entities A then B.
    with system_session(world) as session:
        contract_a, _, _ = contract_of(
            session, world, status=ContractStatus.ACTIVE.value, transaction_currency="EUR"
        )
        entity_b = other_entity(session, world, "AVM-UK")  # functional USD; own period state
        contract_b, _, _ = contract_of(
            session,
            world,
            entity_id=entity_b,
            status=ContractStatus.ACTIVE.value,
            transaction_currency="EUR",
        )
        session.execute(
            insert(period_state).values(
                **period_state_values(
                    world.tenant_id,
                    entity_id=entity_b,
                    period_id=world.period_id,
                    period_end_date=PERIOD_END,
                    state="open",
                )
            )
        )
    first = _run(world)
    second = _run_for(world, entity_b, world.period_id)
    items = _items(world, "FX_RATE_MISSING")
    assert sorted(item["entity_id"] for item in items) == sorted([world.entity_id, entity_b])
    assert all(item["occurrence_count"] == 1 for item in items)
    assert (first.open_blocking, second.open_blocking) == (1, 1)


def test_tenant_rule_overrides_severity_after_creation(world: CloseWorld) -> None:
    # R2 (D-98 58): WARNING first, then an effective ERROR override on re-evaluation.
    with system_session(world) as session:
        contract_id, event_id, _ = contract_of(
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            event_effective_date=date(2026, 5, 1),
        )
    first = _run(world)
    (item,) = _items(world, "DQ_INACTIVE_CONTRACT")
    assert item["severity"] == ExceptionSeverity.WARNING.value and first.open_blocking == 0
    with system_session(world) as session:
        tenant_set = rule_set_values(
            world.tenant_id, code="DQ-TENANT", kind=RuleSetKind.DATA_QUALITY
        )
        session.execute(insert(rule_set).values(**tenant_set))
        tenant_version = rule_set_version_values(
            world.tenant_id, rule_set_id=tenant_set["id"], kind=RuleSetKind.DATA_QUALITY
        )
        override = rule_values(
            world.tenant_id,
            rule_set_version_id=tenant_version["id"],
            rule_key="DQ_INACTIVE_CONTRACT",
            kind=RuleSetKind.DATA_QUALITY,
            conditions=[],
            outputs={"severity": "ERROR", "message": "Inactive contracts block here."},
        )
        published_version(
            session, world, rule_set_version, tenant_version, children=[(rule, override)]
        )
    second = _run(world)
    (same,) = _items(world, "DQ_INACTIVE_CONTRACT")
    assert same["id"] == item["id"] and same["status"] == "OPEN"  # status never changes
    assert same["severity"] == ExceptionSeverity.BLOCKING.value
    assert same["occurrence_count"] == 2
    assert second.severity_changed == 1
    assert second.open_blocking == 1 and _gate(world).status is ChecklistStatus.FAILED
    with system_session(world) as session:
        actions = (
            session.execute(
                select(audit_event.c.action).where(
                    audit_event.c.object_id == item["id"],
                    audit_event.c.action == "exception_item.severity_changed",
                )
            )
            .scalars()
            .all()
        )
    assert len(actions) == 1


def test_same_scope_open_repeat_keeps_blocking(world: CloseWorld) -> None:
    with system_session(world) as session:
        contract_id, _, _ = contract_of(
            session, world, status=ContractStatus.ACTIVE.value, transaction_currency="EUR"
        )
    first, second = _run(world), _run(world)
    (item,) = _items(world, "FX_RATE_MISSING")
    assert item["occurrence_count"] == 2
    assert (first.open_blocking, second.open_blocking) == (1, 1)


def test_in_progress_repeat_keeps_blocking(world: CloseWorld) -> None:
    with system_session(world) as session:
        contract_id, _, _ = contract_of(
            session, world, status=ContractStatus.ACTIVE.value, transaction_currency="EUR"
        )
    _run(world)
    with system_session(world) as session:
        session.execute(update(exception_item).values(status="IN_PROGRESS"))
    again = _run(world)
    (item,) = _items(world, "FX_RATE_MISSING")
    assert (item["status"], item["occurrence_count"]) == ("IN_PROGRESS", 2)
    assert again.open_blocking == 1


def _waive_by_rows(
    world: CloseWorld,
    item_id: UUID,
    *,
    request_status: ApprovalRequestStatus = ApprovalRequestStatus.APPROVED,
) -> UUID:
    """The item WAIVED as the approval of its ``EXCEPTION_WAIVER`` request leaves it
    (``exceptions._waived``; ck_exception_item__waiver: a WAIVED item names its waiver request).
    Returns the request id."""
    with system_session(world) as session:
        waiver = approval_request_values(
            world.tenant_id,
            status=request_status,
            entity_id=world.entity_id,
            subject_type="EXCEPTION_WAIVER",
            subject_id=item_id,
            summary="Waive the finding for this close",
        )
        session.execute(insert(approval_request).values(**waiver))
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == item_id)
            .values(
                status="WAIVED",
                resolved_at=date(2026, 10, 1),
                resolution="Handled once",
                waiver_approval_request_id=waiver["id"],
            )
        )
    return UUID(str(waiver["id"]))


def _eur_contract(world: CloseWorld) -> None:
    """An ACTIVE EUR contract of AVM-US: FX_RATE_MISSING (ERROR) for the September closing rate. A
    recent event keeps DQ_INACTIVE_CONTRACT out of the scenario (batch #4: the cleared set
    otherwise held two items and the rerun re-created both)."""
    with system_session(world) as session:
        contract_of(
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            transaction_currency="EUR",
            event_effective_date=date(2026, 9, 15),
        )


def _approve_closing_rate(world: CloseWorld) -> None:
    """An APPROVED EUR → USD closing rate for 30 Sep 2026: the EUR contract's FX_RATE_MISSING
    finding is gone. The rate is a child row of the version, written while the version is TESTED
    (DB-04 / 0030 admit children only in DRAFT / TESTED), a CLOSING rate of the closing period
    (0030's period CHECK) — Codex production-20260921-0829 R1."""
    with system_session(world) as session:
        rate_set = fx_rate_set_values(world.tenant_id, rate_type=RateType.CLOSING)
        session.execute(insert(fx_rate_set).values(**rate_set))
        fx_version = fx_rate_set_version_values(world.tenant_id, fx_rate_set_id=rate_set["id"])
        row = fx_rate_values(
            world.tenant_id,
            fx_rate_set_version_id=fx_version["id"],
            base_currency="EUR",
            quote_currency="USD",
            effective_date=PERIOD_END,
        )
        row["rate_type"] = RateType.CLOSING.value
        row["period_id"] = world.period_id
        published_version(
            session,
            world,
            fx_rate_set_version,
            fx_version,
            children=[(fx_rate, row)],
            final=ConfigStatus.APPROVED,
        )


def test_fresh_blocking_after_resolved_history_creates_a_new_item(world: CloseWorld) -> None:
    """A RESOLVED item claimed the condition was gone: when the monitors find it again, the
    finding is raised as a new OPEN item (04 T-IMP-05 "Standing waiver", last sentences; supervisor
    ruling R-62 (c) keeps this as it was). The WAIVED case this test also held until the ruling is
    ``test_r_62_c_an_approved_waiver_keeps_its_finding_cleared``."""
    _eur_contract(world)
    _run(world)
    with system_session(world) as session:
        (fx_item,) = session.execute(
            select(exception_item.c.id).where(exception_item.c.code == "FX_RATE_MISSING")
        ).all()
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == fx_item.id)
            .values(status="RESOLVED", resolved_at=date(2026, 10, 1), resolution="Handled once")
        )
    again = _run(world)
    items = _items(world, "FX_RATE_MISSING")
    assert [item["status"] for item in items] == ["RESOLVED", "OPEN"]
    assert (again.created, again.waived, again.open_blocking) == (1, (), 1)


def _exceptions_gate(world: CloseWorld) -> gates.GateResult:
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    return next(result for result in results if result.gate_check_code == gates.EXCEPTIONS_CLEARED)


def _monitor_events(world: CloseWorld) -> list[Mapping[str, Any]]:
    """The ``after`` of each ``close.run_monitors`` event, in chain order."""
    with system_session(world) as session:
        rows = session.execute(
            select(audit_event.c.after)
            .where(audit_event.c.action == monitors.RUN_ACTION)
            .order_by(audit_event.c.chain_seq)
        ).scalars()
        return [dict(after) for after in rows]


def _count(world: CloseWorld, table: Any) -> int:
    with system_session(world) as session:
        return int(session.execute(select(func.count()).select_from(table)).scalar_one())


def test_r_62_c_an_approved_waiver_keeps_its_finding_cleared(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """04 T-IMP-05 rev 1.106 "Standing waiver" (supervisor ruling R-62 (c), item
    DQ-WAIVER-STICKY-1; PRD BR-CLS-01 "exceptions resolved, waived or dismissed", SM-06). A
    BLOCKING finding whose item was waived by an approved request, and whose code, severity and
    message are unchanged, raises nothing on the next monitor run: the waived item's
    ``last_seen_at`` moves, no item, audit event of an item or notification is written, and both
    gates that count the finding stay passed. Until this ruling the run raised the finding again
    as a new OPEN item, so — the monitors running before ``request-lock`` since SC-8 — an approved
    waiver never reached the gate evaluation."""
    _eur_contract(world)
    first = _run(world)
    (item,) = _items(world, "FX_RATE_MISSING")
    assert (first.created, first.open_blocking, item["severity"]) == (1, 1, "BLOCKING")
    assert _gate(world).status is ChecklistStatus.FAILED
    assert _exceptions_gate(world).status is ChecklistStatus.FAILED
    _waive_by_rows(world, UUID(str(item["id"])))
    assert (_gate(world).count, _exceptions_gate(world).count) == (0, 0)
    items_before, notified_before = _count(world, exception_item), _count(world, notification)
    with system_session(world) as session:
        item_events = select(func.count()).where(audit_event.c.object_type == "exception_item")
        events_before = int(session.execute(item_events).scalar_one())

    clock.advance(timedelta(hours=1))
    again = _run(world)
    (waived,) = _items(world, "FX_RATE_MISSING")
    assert (again.created, again.seen_again, again.open_blocking) == (0, 0, 0)
    assert again.waived == (item["id"],)
    assert (waived["id"], waived["status"], waived["occurrence_count"]) == (item["id"], "WAIVED", 1)
    assert waived["last_seen_at"] == clock.now() > item["last_seen_at"]
    assert waived["row_version"] == item["row_version"] + 2  # SC-M: the waiver, then the run
    assert (_count(world, exception_item), _count(world, notification)) == (
        items_before,
        notified_before,
    )
    with system_session(world) as session:
        assert int(session.execute(item_events).scalar_one()) == events_before
    assert [
        (after["findings"], after["created"], after["waived"]) for after in _monitor_events(world)
    ] == [
        (1, 1, 0),
        (1, 0, 1),
    ]
    quality, cleared = _gate(world), _exceptions_gate(world)
    assert (quality.status, quality.count) == (ChecklistStatus.PASSED, 0)
    assert (cleared.status, cleared.count) == (ChecklistStatus.PASSED, 0)


def test_r_62_c_a_waiver_covers_only_the_facts_it_was_approved_for(world: CloseWorld) -> None:
    """The three limits of the standing waiver (04 T-IMP-05 rev 1.106; R-62 (c)). (1) A WAIVED
    item whose waiver request is not APPROVED covers nothing. (2) The key carries entity and
    period: a waiver of the September finding leaves another period's finding of the same
    contract to be raised. (3) A finding that differs in severity from the waived item — a tenant
    rule now rates an inactive contract ERROR — is raised as a new OPEN item and holds the gate."""
    with system_session(world) as session:
        contract_of(
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            event_effective_date=date(2026, 5, 1),
        )
        august_id, _ = _period(session, world, "FY2026-P08")

    def september() -> list[Mapping[str, Any]]:
        return [
            row
            for row in _items(world, "DQ_INACTIVE_CONTRACT")
            if row["period_id"] == world.period_id
        ]

    first = _run(world)
    (item,) = september()
    assert (item["severity"], first.open_blocking) == ("WARNING", 0)

    # (1) Not an approved waiver: the finding is raised again.
    _waive_by_rows(world, UUID(str(item["id"])), request_status=ApprovalRequestStatus.REJECTED)
    uncovered = _run(world)
    assert (uncovered.created, uncovered.waived) == (1, ())
    _, raised_again = september()
    assert [row["status"] for row in september()] == ["WAIVED", "OPEN"]

    # The new item is waived by an approved request: the finding stands waived from here on.
    _waive_by_rows(world, UUID(str(raised_again["id"])))
    standing = _run(world)
    assert (standing.created, standing.waived) == (0, (raised_again["id"],))

    # (2) August is evaluated for the first time: its finding has its own key and is raised.
    august = _run_for(world, world.entity_id, august_id)
    assert (august.created, august.waived) == (1, ())
    assert len(september()) == 2

    # (3) The facts change: the tenant rates the monitor ERROR. The finding's severity differs
    # from the waived item's, so it is raised and holds the gate.
    with system_session(world) as session:
        tenant_set = rule_set_values(
            world.tenant_id, code="DQ-TENANT", kind=RuleSetKind.DATA_QUALITY
        )
        session.execute(insert(rule_set).values(**tenant_set))
        tenant_version = rule_set_version_values(
            world.tenant_id, rule_set_id=tenant_set["id"], kind=RuleSetKind.DATA_QUALITY
        )
        override = rule_values(
            world.tenant_id,
            rule_set_version_id=tenant_version["id"],
            rule_key="DQ_INACTIVE_CONTRACT",
            kind=RuleSetKind.DATA_QUALITY,
            conditions=[],
            outputs={"severity": "ERROR"},
        )
        published_version(
            session, world, rule_set_version, tenant_version, children=[(rule, override)]
        )
    changed = _run(world)
    assert (changed.created, changed.waived, changed.open_blocking) == (1, (), 1)
    assert [(row["status"], row["severity"]) for row in september()] == [
        ("WAIVED", "WARNING"),
        ("WAIVED", "WARNING"),
        ("OPEN", "BLOCKING"),
    ]
    assert _gate(world).status is ChecklistStatus.FAILED


# --- DQ-RESOLVE-1: a finding that is gone settles its open item ----------------------------------

GONE_ASC606 = (
    "No longer found by the data-quality monitors for FY2026-P09 (books evaluated: ASC606)."
)


def _item_events(world: CloseWorld, item_id: UUID) -> list[Mapping[str, Any]]:
    """(action, before, after) of the audit events of one exception item, in chain order."""
    with system_session(world) as session:
        rows = session.execute(
            select(audit_event.c.action, audit_event.c.before, audit_event.c.after)
            .where(
                audit_event.c.object_type == "exception_item", audit_event.c.object_id == item_id
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [{"action": row.action, "before": row.before, "after": row.after} for row in rows]


def test_dq_resolve_1_a_finding_that_is_gone_is_settled_by_the_run(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """04 T-IMP-05 rev 1.185 "A monitor finding that is gone" (supervisor ruling R-111 (j), item
    DQ-RESOLVE-1; PRD SM-06 rev 1.114). A BLOCKING FX_RATE_MISSING item holds both gates. The
    missing rate is approved; the next run no longer finds the condition and settles the item:
    RESOLVED by the SYSTEM (no ``resolved_by``) at the run's instant with a resolution that says
    so, one audit event of the item, no notification; ``occurrence_count`` and ``last_seen_at``
    stay. Both gates pass. The positive control: a WARNING finding that still stands
    (DQ_INACTIVE_CONTRACT of another contract) keeps its item OPEN and counts it again.

    Until this item the FX item stayed OPEN (ruling Q-11): an item of this source offers a person
    neither resolve nor dismiss, so the corrected finding held the lock until a second person
    approved a waiver of a condition that no longer existed."""
    _eur_contract(world)
    with system_session(world) as session:
        contract_of(  # no event for 152 days at the period end: DQ_INACTIVE_CONTRACT (WARNING)
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            event_effective_date=date(2026, 5, 1),
        )
    first = _run(world)
    (fx,) = _items(world, "FX_RATE_MISSING")
    (inactive,) = _items(world, "DQ_INACTIVE_CONTRACT")
    assert (first.created, first.settled, first.open_blocking) == (2, (), 1)
    assert _gate(world).status is ChecklistStatus.FAILED
    assert _exceptions_gate(world).status is ChecklistStatus.FAILED
    notified = _count(world, notification)

    _approve_closing_rate(world)
    clock.advance(timedelta(hours=2))
    second = _run(world)

    assert (second.settled, second.kept_for_locked_book) == ((fx["id"],), 0)
    assert (second.created, second.seen_again, second.open_blocking) == (0, 1, 0)
    (settled,) = _items(world, "FX_RATE_MISSING")
    assert (settled["id"], settled["status"], settled["resolution"]) == (
        fx["id"],
        "RESOLVED",
        GONE_ASC606,
    )
    assert (settled["resolved_by"], str(settled["resolved_by_kind"])) == (None, "SYSTEM")
    assert settled["resolved_at"] == clock.now()
    assert (settled["occurrence_count"], settled["last_seen_at"]) == (1, fx["last_seen_at"])
    assert settled["row_version"] == fx["row_version"] + 1
    (kept,) = _items(world, "DQ_INACTIVE_CONTRACT")  # the control: its finding still stands
    assert (kept["id"], kept["status"], kept["occurrence_count"]) == (inactive["id"], "OPEN", 2)
    # audited as a status change of the item (AUD-CMD); no notification for a settled item
    events = _item_events(world, UUID(str(fx["id"])))
    assert [event["action"] for event in events] == [
        "exception_item.create",
        "exception_item.resolve",
    ]
    assert (events[-1]["before"]["status"], events[-1]["after"]["status"]) == ("OPEN", "RESOLVED")
    assert events[-1]["after"]["resolution"] == GONE_ASC606
    assert (events[-1]["after"]["resolved_by"], events[-1]["after"]["resolved_by_kind"]) == (
        None,
        "SYSTEM",
    )
    assert _count(world, notification) == notified
    assert [
        (after["findings"], after["created"], after["settled"], after["kept_for_locked_book"])
        for after in _monitor_events(world)
    ] == [(2, 2, 0, 0), (1, 0, 1, 0)]
    quality, cleared = _gate(world), _exceptions_gate(world)
    assert (quality.status, quality.count) == (ChecklistStatus.PASSED, 0)
    assert (cleared.status, cleared.count) == (ChecklistStatus.PASSED, 0)

    third = _run(world)  # nothing left to settle; the settled item is not touched again
    assert (third.settled, third.created) == ((), 0)
    (same,) = _items(world, "FX_RATE_MISSING")
    assert (same["status"], same["row_version"]) == ("RESOLVED", settled["row_version"])


def test_dq_resolve_1_a_finding_that_returns_is_a_new_item(
    world: CloseWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An item someone is working on (IN_PROGRESS) is settled as an OPEN one is, and a finding
    that returns after its item was settled is raised as a NEW item — the settled item is not
    reopened (04 T-IMP-05 rev 1.185, "Afterwards"). The real disappearance of a finding is
    ``test_dq_resolve_1_a_finding_that_is_gone_is_settled_by_the_run``; here the monitors' facts
    are withheld for one run, so that the same key can come back."""
    _eur_contract(world)
    _run(world)
    (first,) = _items(world, "FX_RATE_MISSING")
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == first["id"])
            .values(status="IN_PROGRESS")
        )
    with monkeypatch.context() as withheld:
        withheld.setattr(monitors, "collect_inputs", lambda *_: monitor_rules.MonitorInputs())
        gone = _run(world)
    assert (gone.outcome.findings, gone.settled) == ((), (first["id"],))
    clock.advance(timedelta(hours=1))
    back = _run(world)
    assert (back.created, back.settled, back.open_blocking) == (1, (), 1)
    items = _items(world, "FX_RATE_MISSING")
    assert [(item["id"] == first["id"], item["status"]) for item in items] == [
        (True, "RESOLVED"),
        (False, "OPEN"),
    ]
    assert items[0]["resolution"] == GONE_ASC606
    assert items[1]["exception_no"] != items[0]["exception_no"]
    assert items[1]["dedupe_key"] == items[0]["dedupe_key"]


def test_dq_resolve_1_the_run_before_start_close_settles_as_the_system(world: CloseWorld) -> None:
    """Through the product: ``POST /periods/{id}/start-close`` runs the monitors first, as the
    SYSTEM principal in a unit of work of its own (04 §16.8). Maya's command therefore settles the
    corrected finding without being its resolver: the item is RESOLVED by the SYSTEM, and both
    audit events — the run's and the item's — carry the SYSTEM actor."""
    _eur_contract(world)
    _run(world)
    (item,) = _items(world, "FX_RATE_MISSING")
    _approve_closing_rate(world)
    september = world.september
    started = post(
        world.app,
        f"{PERIODS}/{world.state_id}/start-close",
        world.maya,
        {"comment": "September close"},
        if_match=f'"r{september["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    (settled,) = _items(world, "FX_RATE_MISSING")
    assert (settled["id"], settled["status"]) == (item["id"], "RESOLVED")
    assert (settled["resolved_by"], str(settled["resolved_by_kind"])) == (None, "SYSTEM")
    with system_session(world) as session:
        actors = session.execute(
            select(audit_event.c.action, audit_event.c.actor_kind, audit_event.c.actor_id)
            .where(
                audit_event.c.action.in_(["exception_item.resolve", monitors.RUN_ACTION]),
                audit_event.c.request_id == started.headers["x-request-id"],
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    assert [(row.action, str(row.actor_kind), row.actor_id) for row in actors] == [
        ("exception_item.resolve", "SYSTEM", None),
        (monitors.RUN_ACTION, "SYSTEM", None),
    ]
    # the queue's read: resolved by the system, with the reason, and no action left
    shown = get(world.app, f"/api/v1/exceptions/{item['id']}", world.maya)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert (body["status"], body["resolution"], body["available_actions"]) == (
        "RESOLVED",
        GONE_ASC606,
        [],
    )
    assert (body["resolved_by"]["kind"], body["resolved_by"]["id"]) == ("SYSTEM", None)


def _run_book(world: CloseWorld, book: str) -> monitors.MonitorRun:
    with world.place.uow() as uow:
        run = monitors.run_monitors(uow, world.entity_id, book, world.period_id)
        uow.commit()
    return run


def _second_book(world: CloseWorld, state: str) -> None:
    """AVM-US keeps IFRS15 as well: its state row of FY2026-P09 in ``state``."""
    with system_session(world) as session:
        session.execute(
            insert(period_state).values(
                **period_state_values(
                    world.tenant_id,
                    entity_id=world.entity_id,
                    period_id=world.period_id,
                    period_end_date=PERIOD_END,
                    book_code=BookCode.IFRS15,
                    state=state,
                )
            )
        )


def _facts_by_book(
    monkeypatch: pytest.MonkeyPatch, world: CloseWorld
) -> dict[str, monitor_rules.MonitorInputs]:
    """The monitors' facts per book, set by the test: three monitors read rows of the book they
    are run for, so two books of one entity can disagree about a finding. Returns the mapping the
    test changes; a book without an entry has no facts."""
    facts: dict[str, monitor_rules.MonitorInputs] = {}
    monkeypatch.setattr(
        monitors,
        "collect_inputs",
        lambda _session, scope: facts.get(str(scope.book_code), monitor_rules.MonitorInputs()),
    )
    return facts


def _inactive(world: CloseWorld) -> tuple[UUID, monitor_rules.MonitorInputs]:
    """A contract of AVM-US and the facts that make it DQ_INACTIVE_CONTRACT (a WARNING)."""
    with system_session(world) as session:
        contract_id, _, _ = contract_of(
            session,
            world,
            status=ContractStatus.ACTIVE.value,
            event_effective_date=date(2026, 9, 15),
        )
    stale = monitor_rules.ContractActivityRef(
        contract_id=contract_id, is_active=True, last_event_date=date(2026, 5, 1)
    )
    return contract_id, monitor_rules.MonitorInputs(contracts=(stale,))


def test_dq_resolve_1_an_item_is_kept_while_another_book_of_the_entity_finds_it(
    world: CloseWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key of a data-quality item carries entity and period and no book, while a run
    evaluates one book (04 T-IMP-05 rev 1.185, "Books"). AVM-US keeps ASC606 and IFRS15, both
    open; the finding exists in ASC606's facts alone. The run of IFRS15 does not find it and does
    NOT settle it: it evaluates ASC606 as well, which finds it. Once neither book finds it, the
    run of either settles it and names both books. The item is never counted by a run that only
    looked at it for the other book."""
    _second_book(world, "open")
    facts = _facts_by_book(monkeypatch, world)
    _, facts[BOOK] = _inactive(world)
    assert _run_book(world, BOOK).created == 1
    (item,) = _items(world, "DQ_INACTIVE_CONTRACT")

    other = _run_book(world, "IFRS15")  # finds nothing itself; ASC606 still finds the item's key
    assert (other.outcome.findings, other.settled, other.kept_for_locked_book) == ((), (), 0)
    (kept,) = _items(world, "DQ_INACTIVE_CONTRACT")
    assert (kept["status"], kept["occurrence_count"]) == ("OPEN", 1)

    del facts[BOOK]  # the condition is corrected: no book finds it any more
    settled = _run_book(world, "IFRS15")
    assert settled.settled == (item["id"],)
    (done,) = _items(world, "DQ_INACTIVE_CONTRACT")
    assert (done["status"], done["resolution"]) == (
        "RESOLVED",
        "No longer found by the data-quality monitors for FY2026-P09 "
        "(books evaluated: ASC606, IFRS15).",
    )


@pytest.mark.parametrize(
    ("state", "settles"),
    [
        ("closed", False),  # that book is not evaluated and keeps the period's open items
        ("permanently_locked", False),
        ("future", True),  # a future period holds no finding of its own
    ],
)
def test_dq_resolve_1_nothing_is_settled_while_another_book_has_locked_the_period(
    world: CloseWorld, monkeypatch: pytest.MonkeyPatch, state: str, settles: bool
) -> None:
    """04 T-IMP-05 rev 1.185, "Books"; 05 SCH-10 rev 1.124 [J]: while another book of the entity
    has the period ``closed`` or ``permanently_locked``, a run settles nothing of that period —
    whether the locked book's finding still stands is not known — and counts what it kept in its
    audit event; a ``future`` state does not count."""
    _second_book(world, state)
    facts = _facts_by_book(monkeypatch, world)
    _, facts[BOOK] = _inactive(world)
    _run_book(world, BOOK)
    (item,) = _items(world, "DQ_INACTIVE_CONTRACT")
    del facts[BOOK]
    run = _run_book(world, BOOK)
    (after,) = _items(world, "DQ_INACTIVE_CONTRACT")
    if settles:
        assert (run.settled, run.kept_for_locked_book) == ((item["id"],), 0)
        assert (after["status"], after["resolution"]) == ("RESOLVED", GONE_ASC606)
    else:
        assert (run.settled, run.kept_for_locked_book) == ((), 1)
        assert (after["status"], after["resolution"], after["row_version"]) == (
            "OPEN",
            None,
            item["row_version"],
        )
    last = _monitor_events(world)[-1]
    assert (last["settled"], last["kept_for_locked_book"]) == ((1, 0) if settles else (0, 1))


def test_dq_resolve_1_an_item_another_transaction_holds_is_skipped(
    world: CloseWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The settling never waits for an item: a row another transaction holds — a run that counts
    it again, a person's command on it — is skipped and settled by a later run (``FOR UPDATE SKIP
    LOCKED``), so two runs of one entity and period cannot wait for each other's items."""
    facts = _facts_by_book(monkeypatch, world)
    _, facts[BOOK] = _inactive(world)
    _run_book(world, BOOK)
    (item,) = _items(world, "DQ_INACTIVE_CONTRACT")
    del facts[BOOK]
    with system_session(world) as holder:
        holder.execute(
            select(exception_item.c.id).where(exception_item.c.id == item["id"]).with_for_update()
        )
        skipped = _run_book(world, BOOK)  # the holder's transaction is still open
        assert skipped.settled == ()
        (held,) = _items(world, "DQ_INACTIVE_CONTRACT")
        assert held["status"] == "OPEN"
    later = _run_book(world, BOOK)
    assert later.settled == (item["id"],)


def test_repeat_raises_survive_a_generic_plan(world: CloseWorld) -> None:
    """Batch #5 on main 020e5fd3 (``test_same_scope_open_repeat_keeps_blocking``): the
    exception-item upsert's partial-index inference failed once the prepared statement ran under
    a generic plan, because SQLAlchemy rendered the ``ON CONFLICT … WHERE`` predicate with bound
    parameters. Under
    ``plan_cache_mode = force_generic_plan`` every PREPARED execution is generic; eight distinct
    raises in one unit of work cross psycopg's prepare threshold (5), so the prepared executions
    after it exercise the inference under a generic plan — with the literal ``OPEN_PREDICATE`` they
    all insert. The ninth raise of an already committed IN_PROGRESS key takes the existing-item
    fast path (``_seen_again`` finds and counts it before ``open_item_upsert`` runs) — it does not
    reach the conflict-UPDATE branch (Codex production-20260921-1354 B2-WITNESS-SCOPE-1); that
    branch's inference is literal by construction (the CPU witness), and no concurrent first-insert
    case is authored here. psycopg's preparation threshold and PostgreSQL's custom / generic plan
    selection are distinct mechanisms; the batch-#5 causation stays as the record attributes it."""
    # Codex production-20260921-1147 §3 (b): applied-DDL identity — the partial unique index is
    # present on this database as 0041 defines it (columns and predicate) before the statement that
    # infers it runs.
    with system_session(world) as session:
        indexdef = session.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'erev' "
                "AND indexname = 'ux_exception_item__open'"
            )
        ).scalar_one()
    assert "UNIQUE" in indexdef and "(tenant_id, dedupe_key)" in indexdef, indexdef
    assert "OPEN" in indexdef and "IN_PROGRESS" in indexdef and "WHERE" in indexdef, indexdef
    with world.place.uow() as uow:
        uow.session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
        raised = [
            raise_exception_item(
                uow,
                source=ExceptionSource.DATA_QUALITY,
                code="FX_RATE_MISSING",
                severity=ExceptionSeverity.BLOCKING,
                message=f"Generic-plan probe {index}.",
                dedupe=f"probe:generic-plan:{index}",
                entity_id=world.entity_id,
                period_id=world.period_id,
            )
            for index in range(8)
        ]
        uow.commit()
    assert len({item.id for item in raised}) == 8
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.dedupe_key == "probe:generic-plan:7")
            .values(status="IN_PROGRESS")
        )
    with world.place.uow() as uow:
        uow.session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
        again = raise_exception_item(
            uow,
            source=ExceptionSource.DATA_QUALITY,
            code="FX_RATE_MISSING",
            severity=ExceptionSeverity.BLOCKING,
            message="Generic-plan probe 7 again.",
            dedupe="probe:generic-plan:7",
            entity_id=world.entity_id,
            period_id=world.period_id,
        )
        uow.commit()
    assert again.id == raised[7].id
    (item,) = _items(world, "FX_RATE_MISSING")[7:8]
    assert (item["dedupe_key"], item["occurrence_count"]) == ("probe:generic-plan:7", 2)


def _layer_movement(
    session: Session,
    world: CloseWorld,
    contract_id: UUID,
    version_id: UUID,
    key: str,
    kind: str,
    txn: str,
    functional: str,
    *,
    on: date = PERIOD_END,
    book: str = BOOK,
    entity_id: UUID | None = None,
) -> None:
    session.execute(
        insert(fx_layer_movement).values(
            tenant_id=world.tenant_id,
            id=uuid4(),
            contract_version_id=version_id,
            contract_id=contract_id,
            book_code=book,
            entity_id=entity_id or world.entity_id,
            layer_key=key,
            movement_kind=kind,
            balance_role="CONTRACT_LIABILITY",
            effective_date=on,
            txn_currency="USD",
            functional_currency="USD",
            amount_txn=Decimal(txn),
            amount_functional=Decimal(functional),
            rate=Decimal("1"),
            created_by=None,
            created_by_kind="SYSTEM",
        )
    )


@pytest.mark.parametrize("functional_deficit", [False, True])
def test_negative_layer_cannot_hide_in_positive_total_and_blocks_close(
    world: CloseWorld,
    functional_deficit: bool,
) -> None:
    with system_session(world) as session:
        contract_id, _, _, version_id = _version(session, world)
        _layer_movement(
            session, world, contract_id, version_id, "bad", "LIABILITY_LAYER_CREATED", "100", "100"
        )
        _layer_movement(
            session,
            world,
            contract_id,
            version_id,
            "bad",
            "LIABILITY_LAYER_CONSUMED",
            "50" if functional_deficit else "120",
            "50" if functional_deficit else "120",
        )
        _layer_movement(
            session,
            world,
            contract_id,
            version_id,
            "bad",
            "LIABILITY_LAYER_REMEASURED",
            "100",
            "-60" if functional_deficit else "50",
        )
        _layer_movement(
            session, world, contract_id, version_id, "good", "LIABILITY_LAYER_CREATED", "200", "200"
        )
        # A future inflow cannot repair the deficit at this close date.
        _layer_movement(
            session,
            world,
            contract_id,
            version_id,
            "bad",
            "LIABILITY_LAYER_CREATED",
            "1000",
            "1000",
            on=date(2026, 10, 1),
        )
        # Neither another book's deficit nor a future deficit belongs to September ASC606.
        _layer_movement(
            session,
            world,
            contract_id,
            version_id,
            "other-book",
            "LIABILITY_LAYER_CONSUMED",
            "100",
            "100",
            book="IFRS15",
        )
        _layer_movement(
            session,
            world,
            contract_id,
            version_id,
            "future",
            "LIABILITY_LAYER_CONSUMED",
            "100",
            "100",
            on=date(2026, 10, 1),
        )
    result = _run(world)
    (item,) = _items(world, "DQ_NEGATIVE_LIABILITY_LAYER")
    assert item["status"] == "OPEN" and item["contract_id"] == contract_id
    assert "bad" in item["message"]
    assert ("-10" if functional_deficit else "-20") in item["message"]
    assert result.open_blocking == 1
    assert _gate(world).status is ChecklistStatus.FAILED
    _run(world)
    assert len(_items(world, "DQ_NEGATIVE_LIABILITY_LAYER")) == 1


def test_corrected_version_resolves_negative_layer_without_recounting_history(
    world: CloseWorld,
) -> None:
    with system_session(world) as session:
        contract_id, _, group_id, version_id = _version(session, world)
        _layer_movement(
            session, world, contract_id, version_id, "layer", "LIABILITY_LAYER_CONSUMED", "20", "20"
        )
    _run(world)
    (finding,) = _items(world, "DQ_NEGATIVE_LIABILITY_LAYER")
    assert finding["status"] == "OPEN"

    with system_session(world) as session:
        release_id = session.execute(
            select(contract_computation.c.engine_release_id).where(
                contract_computation.c.combination_group_id == group_id
            )
        ).scalar_one()
        computation = contract_computation_values(
            world.tenant_id, combination_group_id=group_id, engine_release_id=release_id
        )
        session.execute(insert(contract_computation).values(**computation))
        trace = calc_trace_values(
            world.tenant_id, contract_version_id=UUID(int=0), combination_group_id=group_id
        )
        version = contract_version_values(
            world.tenant_id,
            combination_group_id=group_id,
            contract_computation_id=computation["id"],
            calc_trace_id=trace["id"],
            version_no=2,
            known_at=computation["known_at"] + timedelta(seconds=1),
        )
        trace["contract_version_id"] = version["id"]
        session.execute(insert(calc_trace).values(**trace))
        session.execute(insert(contract_version).values(**version))
        # A replacement calculation's complete movement set is positive by itself. Adding
        # the obsolete version's consumption would incorrectly keep the exception open.
        _layer_movement(
            session, world, contract_id, version["id"], "layer", "LIABILITY_LAYER_CREATED", "5", "5"
        )
        entity_b = other_entity(session, world, "AVM-UK")
        contract_b, _, _, version_b = _version(session, world, entity_id=entity_b)
        _layer_movement(
            session,
            world,
            contract_b,
            version_b,
            "foreign-layer",
            "LIABILITY_LAYER_CONSUMED",
            "100",
            "100",
            entity_id=entity_b,
        )
    result = _run(world)
    (resolved,) = _items(world, "DQ_NEGATIVE_LIABILITY_LAYER")
    assert resolved["id"] == finding["id"] and resolved["status"] == "RESOLVED"
    assert result.open_blocking == 0 and result.settled == (finding["id"],)
    assert _gate(world).status is ChecklistStatus.PASSED


def test_liability_aging_keeps_creation_date_and_selected_version(world: CloseWorld) -> None:
    from erev_api.domain.reports.builders.balance_aging import _liability_layers
    from erev_api.domain.reports.tie_outs import BalanceRow

    with system_session(world) as session:
        contract_id, _, _, version_id = _version(session, world)
        _, _, _, unselected_version = _version(session, world)
        for version, key, kind, amount, day, book in (
            (version_id, "july", "LIABILITY_LAYER_CREATED", "100", date(2026, 7, 1), BOOK),
            (version_id, "july", "LIABILITY_LAYER_CONSUMED", "40", date(2026, 9, 1), BOOK),
            (version_id, "july", "LIABILITY_LAYER_REMEASURED", "60", PERIOD_END, BOOK),
            (version_id, "august", "LIABILITY_LAYER_CREATED", "20", date(2026, 8, 1), BOOK),
            (version_id, "july", "LIABILITY_LAYER_CONSUMED", "60", date(2026, 10, 1), BOOK),
            (version_id, "other-book", "LIABILITY_LAYER_CREATED", "999", PERIOD_END, "IFRS15"),
            (unselected_version, "unselected", "LIABILITY_LAYER_CREATED", "999", PERIOD_END, BOOK),
        ):
            _layer_movement(
                session, world, contract_id, version, key, kind, amount, amount, on=day, book=book
            )
        balance = BalanceRow(
            contract_id=contract_id,
            external_id="aging-contract",
            customer_name=None,
            entity_id=world.entity_id,
            entity_code=ENTITY_CODE,
            currency="USD",
            version_id=version_id,
            values={"contract_liability": Decimal("80")},
        )
        layers = _liability_layers(
            session, book_code=BOOK, period_ends={world.entity_id: PERIOD_END}, balances=[balance]
        )
    assert sorted((layer.effective_date, layer.amount) for layer in layers) == [
        (date(2026, 7, 1), Decimal("60")),
        (date(2026, 8, 1), Decimal("20")),
    ]
    assert all(layer.external_id == "aging-contract" for layer in layers)
