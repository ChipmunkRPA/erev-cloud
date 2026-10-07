"""The computation of a combination group is reader-independent (CTR-COMPUTE-CALLER-SCOPE-1; 05
RCP-18 and TXN-10, rev 1.82; dev-guide DG-KRN-DB-05, DG-KRN-UOW-05 and DG-CMD-09, rev 1.126;
supervisor rulings R-95, R-98 (3) and R-103 (b)).

A group is computed inside the transaction of the command that asked for it. Its bundle is read and
its outputs are written under the tenant's scope by SYSTEM on behalf of that command's principal,
whatever entities the principal may see and whatever scope an import narrowed the transaction to;
the command's own writes and every read after the computation stay the caller's.

World: PRD WLD-K-04 (``support.worlds.k04_saltmarsh``). ``SF-ORD-UK-2001`` is contracted by AVM-UK
in GBP; O1 (58,285.71) is performed by AVM-US, O2 (9,714.29) by AVM-UK. Una is a Revenue Accountant
of AVM-UK only; Maya holds the same role for every entity.

What "the same as for a user of every entity" can mean. An event takes ``record_seq`` from a
sequence and ``recorded_at`` from the server clock (04 DB-08), and both enter the bundle (CV-25),
so two executions of one command never have one input hash. The hashes are therefore compared
where the inputs are identical: one committed stream, computed under each caller's context in a
transaction that is rolled back. Through the routes the oracle is the ledger: after a scoped
caller's command, a computation of the same group by a caller of every entity finds nothing to
post and no figure to change.

The defect these tests were written against (measured on main 44b6c13a): Una recorded an invoice
on ``SF-ORD-UK-2001`` and the answer's computation was QUARANTINED — "the performing entity has no
calendar (rule CV-12)" — with a BLOCKING exception item, because bundle assembly read
``legal_entity`` under her entity scope.

The group's period-end mark is written by the computation too (04 T-CON-03), from a read of the
close runs and period states of the group's entities — rows of AVM-US among them. Since dev-guide
rev 1.245 that read enters no scope block of its own and is as wide as the computation that asks;
``test_a_fact_recorded_inside_another_entitys_window_…`` holds the mark to the rule of this module
(item WINDOW-MARK-NARROWED-1).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.approvals import engine as approvals
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import errors as db_errors
from erev_api.db.session import DbContext, ScopeNotTenantWide, app_engine, tenant_session
from erev_api.db.tables import (
    audit_event,
    calc_trace,
    close_run,
    combination_group,
    contract,
    contract_computation,
    contract_hold,
    contract_version,
    contract_version_balance,
    control_execution,
    exception_item,
    job,
    legal_entity,
    obligation,
    obligation_version,
    period_state,
    schedule_line,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.contracts import bundles, computation, compute_job
from erev_api.domain.imports import scope as import_scope
from erev_api.domain.imports.exceptions import raise_exception_item
from erev_api.enums import (
    AuditOutcome,
    ComputationStatus,
    ComputationTrigger,
    ContractEventType,
    ExceptionSeverity,
    ExceptionSource,
    PrincipalKind,
)
from erev_api.events.payloads import BillingRecordedV1, ProgressRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from support import close_runs as runs
from support.db import TestDatabase
from support.factories import (
    Workspace,
    appended,
    booked_contract,
    computed,
    engine,
    maya_principal,
    open_periods,
    step1_criteria,
)
from support.modifications import confirm_answers
from support.principals import Actor, Member, colleague, enrolled
from support.reference import approve, assign, entity, get, holding, post
from support.rows import insert_custom_role, revoke_role_assignments
from support.worlds import (
    AVM_UK,
    AVM_US,
    IMPLEMENTATION_UK,
    K04,
    PLATFORM_UK,
    K04World,
    evidence_file,
    k04_saltmarsh,
    run_now,
)

CONTRACTS: Final = "/api/v1/contracts"
GROUPS: Final = "/api/v1/combination-groups"
MODIFICATIONS: Final = "/api/v1/modifications"
DRY_RUN: Final = "DRY_RUN"
POOL_PROBES: Final = 4  # connections checked out at once to find the one a unit of work used
CUTOFF: Final = datetime(2027, 1, 1, tzinfo=UTC)
NORTHERN: Final = "AVM-NI"  # a second entity that keeps its books in GBP
# the second contracting entity of a combination group → its contract
OTHER_ORDER: Final = {NORTHERN: "SF-ORD-NI-3001", AVM_US: "SF-ORD-US-3001"}
SYSTEM: Final = "SYSTEM"
ENTITY_SCOPE: Final = text("SELECT current_setting('app.entity_scope', true)")
USER_ID: Final = text("SELECT current_setting('app.user_id', true)")
TENANT_WIDE: Final = text("SELECT set_config('app.entity_scope', '*', true)")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k04(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K04World:
    return k04_saltmarsh(app, keyring, clock, files)


def billing(number: str, amount: str, day: date) -> EventIn:
    return EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=day,
        payload=BillingRecordedV1(
            invoice_number=number,
            line_external_id=f"{number}-1",
            amount=MoneyIn(amount=amount, currency="GBP"),
            issue_date=day,
        ),
    )


def terms(k04: K04World, external_id: str) -> dict[str, Any]:
    """The booking of ``SF-ORD-UK-2001`` (PRD WLD-K-04) under another external id."""
    term = {"start_date": "2026-04-01", "end_date": "2027-03-31"}
    return {
        "external_id": external_id,
        "customer_id": str(k04.report.contracts[K04].contract["customer_id"]),
        "contracting_entity_code": AVM_UK,
        "transaction_currency": "GBP",
        "inception_date": "2026-04-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PLATFORM_UK,
                "quantity": "1",
                "total_price": {"amount": "60000.00", "currency": "GBP"},
                "performing_entity_code": AVM_US,
                **term,
            },
            {
                "obligation_key": "O2",
                "product_code": IMPLEMENTATION_UK,
                "quantity": "1",
                "total_price": {"amount": "8000.00", "currency": "GBP"},
                "performing_entity_code": AVM_UK,
            },
        ],
    }


def twin(k04: K04World, external_id: str) -> tuple[UUID, UUID]:
    """A second contract with the terms of ``SF-ORD-UK-2001`` — contracted by AVM-UK, O1 performed
    by AVM-US, O2 by AVM-UK — booked, activated, invoiced and delivered, and NOT computed since:
    its (contract id, group id). Its next computation posts April to September for both entities."""
    place = k04.report.place
    booked = booked_contract(place, terms(k04, external_id), activate=True)
    contract_id = UUID(str(booked.contract["id"]))
    appended(
        place,
        contract_id,
        2,
        [
            billing(f"INV-{external_id}", "68000.00", date(2026, 4, 1)),
            EventIn(
                event_type=ContractEventType.PROGRESS_RECORDED,
                effective_date=date(2026, 5, 31),
                payload=ProgressRecordedV1(
                    obligation_key="O2", cumulative_progress_ratio="1", measure="OUTPUT_PERCENT"
                ),
            ),
        ],
    )
    return contract_id, UUID(str(booked.combination_group["id"]))


def of_entities(person: Principal, *entity_ids: UUID) -> Principal:
    """``person`` with every permission held for ``entity_ids`` only."""
    scope = frozenset(entity_ids)
    return dataclasses.replace(
        person,
        entity_scope=tuple(sorted(entity_ids)),
        permission_scopes=MappingProxyType(dict.fromkeys(sorted(person.permissions), scope)),
    )


def visible_entities(session: Session) -> list[str]:
    """The entity codes the transaction can read now (``legal_entity`` is RLS-TE)."""
    return sorted(str(code) for code in session.execute(select(legal_entity.c.code)).scalars())


def _rows(session: Session, statement: Any) -> list[tuple[Any, ...]]:
    return sorted(
        (tuple(row) for row in session.execute(statement)),
        key=lambda row: tuple(str(value) for value in row),
    )


def stored(session: Session, computation_id: UUID) -> dict[str, Any]:
    """Everything the computation ``computation_id`` wrote, without ids and timestamps. The
    caller reads it under the tenant's scope."""
    entity = legal_entity.alias("line_entity")
    version_ids = select(contract_version.c.id).where(
        contract_version.c.contract_computation_id == computation_id
    )
    posting_ids = select(subledger_posting.c.id).where(
        subledger_posting.c.contract_computation_id == computation_id
    )
    computation = session.execute(
        select(
            contract_computation.c.status,
            contract_computation.c.input_sha256,
            contract_computation.c.trigger,
            contract_computation.c.stream_heads,
            contract_computation.c.created_by,
            contract_computation.c.created_by_kind,
        ).where(contract_computation.c.id == computation_id)
    ).one()
    obligations = obligation_version
    balances = contract_version_balance
    return {
        "computation": tuple(computation),
        "versions": _rows(
            session,
            select(
                contract_version.c.book_code,
                contract_version.c.version_no,
                contract_version.c.output_sha256,
                contract_version.c.transaction_price,
                contract_version.c.status_in_book,
                contract_version.c.created_by,
                contract_version.c.created_by_kind,
            ).where(contract_version.c.contract_computation_id == computation_id),
        ),
        "traces": _rows(
            session,
            select(
                calc_trace.c.book_code, calc_trace.c.trace_sha256, calc_trace.c.node_count
            ).where(calc_trace.c.contract_version_id.in_(version_ids)),
        ),
        "obligations": _rows(
            session,
            select(
                obligations.c.book_code,
                contract.c.external_id,
                obligations.c.obligation_key,
                entity.c.code,
                obligations.c.allocated_amount,
                obligations.c.revenue_cum,
                obligations.c.billed_cum,
                obligations.c.scheduled_amount,
                obligations.c.remaining_allocation,
                obligations.c.created_by_kind,
            )
            .join(entity, entity.c.id == obligations.c.performing_entity_id)
            .join(contract, contract.c.id == obligations.c.contract_id)
            .where(obligations.c.contract_version_id.in_(version_ids)),
        ),
        "balances": _rows(
            session,
            select(
                balances.c.book_code,
                entity.c.code,
                balances.c.revenue_cum_txn,
                balances.c.billed_cum_txn,
                balances.c.contract_liability_txn,
                balances.c.contract_asset_txn,
                balances.c.created_by_kind,
            )
            .join(entity, entity.c.id == balances.c.entity_id)
            .where(balances.c.contract_version_id.in_(version_ids)),
        ),
        "schedule": _rows(
            session,
            select(
                schedule_line.c.book_code,
                entity.c.code,
                func.count(),
                func.sum(schedule_line.c.amount),
            )
            .join(entity, entity.c.id == schedule_line.c.entity_id)
            .where(schedule_line.c.contract_version_id.in_(version_ids))
            .group_by(schedule_line.c.book_code, entity.c.code),
        ),
        "postings": _rows(
            session,
            select(
                subledger_posting.c.book_code,
                subledger_posting.c.posting_kind,
                subledger_posting.c.created_by,
                subledger_posting.c.created_by_kind,
            ).where(subledger_posting.c.contract_computation_id == computation_id),
        ),
        "ledger": _rows(
            session,
            select(
                subledger_line.c.book_code,
                entity.c.code,
                subledger_line.c.period_end_date,
                subledger_line.c.entry_kind,
                subledger_line.c.account_role,
                subledger_line.c.dr_cr,
                subledger_line.c.amount_txn,
                subledger_line.c.amount_functional,
                subledger_line.c.created_by_kind,
            )
            .join(entity, entity.c.id == subledger_line.c.entity_id)
            .where(subledger_line.c.subledger_posting_id.in_(posting_ids)),
        ),
        "control": _rows(
            session,
            select(control_execution.c.control_id, control_execution.c.result).where(
                control_execution.c.run_ref_id == computation_id
            ),
        ),
    }


def heads(session: Session, group_id: UUID) -> tuple[Any, ...]:
    """The group's head and dirty mark with each member's latest computation."""
    group = session.execute(
        select(combination_group.c.head_computation_id, combination_group.c.dirty_since).where(
            combination_group.c.id == group_id
        )
    ).one()
    members = _rows(
        session,
        select(contract.c.external_id, contract.c.latest_computation_id).where(
            contract.c.combination_group_id == group_id
        ),
    )
    return (*group, members)


@dataclasses.dataclass(frozen=True, slots=True)
class Seen:
    """One caller's computation of the group: what it could read before and after, and what the
    computation stored."""

    before: list[str]
    after: list[str]
    scope_after: str
    user_after: str
    status: str
    heads_at_computation: bool
    dirty: Any
    exceptions: int
    stored: dict[str, Any]
    mark: dict[str, str]


@contextmanager
def narrowed_to(uow: UnitOfWork, entity_ids: frozenset[UUID] | None) -> Iterator[None]:
    with nullcontext() if entity_ids is None else import_scope.narrowed(uow, entity_ids):
        yield


def computed_as(
    place: Workspace,
    principal: Principal,
    group_id: UUID,
    *,
    narrow: frozenset[UUID] | None = None,
) -> Seen:
    """``compute_group`` of the committed stream in a unit of work of ``principal`` — inside an
    import's narrowed context when ``narrow`` — read back under the tenant's scope and ROLLED BACK,
    so the next caller starts from the same rows."""
    with place.uow(principal) as uow:
        session = uow.session
        with narrowed_to(uow, narrow):
            before = visible_entities(session)
            outcome = compute_job.compute_group(uow, group_id)
            after = visible_entities(session)
            scope_after = str(session.execute(ENTITY_SCOPE).scalar_one())
            user_after = str(session.execute(USER_ID).scalar_one())
            assert outcome.computation is not None and outcome.status is not None
            computation_id = UUID(str(outcome.computation["id"]))
            # the test's own widening, to read what was written for every entity
            session.execute(TENANT_WIDE)
            head_id, dirty, members = heads(session, group_id)
            seen = Seen(
                before=before,
                after=after,
                scope_after=scope_after,
                user_after=user_after,
                status=outcome.status.value,
                heads_at_computation=head_id == computation_id
                and all(latest == computation_id for _, latest in members),
                dirty=dirty,
                exceptions=int(
                    session.execute(
                        select(func.count())
                        .select_from(exception_item)
                        .where(exception_item.c.combination_group_id == group_id)
                    ).scalar_one()
                ),
                stored=stored(session, computation_id),
                mark=dict(
                    session.execute(
                        select(combination_group.c.period_ends_open).where(
                            combination_group.c.id == group_id
                        )
                    ).scalar_one()
                    or {}
                ),
            )
        uow.discard()
    return seen


def person(someone: Member, name: str) -> Principal:
    return dataclasses.replace(maya_principal(someone), display_name=name)


def test_a_group_is_computed_the_same_whoever_asks(k04: K04World) -> None:
    """One committed stream — ``SF-ORD-UK-2002``, the terms of WLD-K-04, activated, invoiced,
    delivered and never computed — computed by a user of every entity, by a user of AVM-UK and
    inside an import narrowed to AVM-UK. The three computations have one input hash and one
    output hash per book and store the same versions, obligations, balances, schedule lines and
    ledger lines — those of AVM-US included — stamped SYSTEM. Each caller reads after the
    computation exactly what it could read before it."""
    place = k04.report.place
    uk, us = k04.uk_entity_id, k04.us_entity_id
    una = colleague(k04.report.tenant_id, "una")
    _, group_id = twin(k04, "SF-ORD-UK-2002")
    every = computed_as(place, place.principal, group_id)
    scoped = computed_as(place, of_entities(person(una, "Una Lindqvist"), uk), group_id)
    narrowed = computed_as(
        place,
        system_principal(place.tenant_id, on_behalf_of_id=una.user_id),
        group_id,
        narrow=frozenset({uk}),
    )
    assert (every.status, scoped.status, narrowed.status) == ("SUCCEEDED",) * 3
    assert (every.exceptions, scoped.exceptions, narrowed.exceptions) == (0, 0, 0)
    # The reference: a user of every entity. Both books, both entities, everything SYSTEM's.
    assert every.heads_at_computation and every.dirty is None
    assert {row[0] for row in every.stored["versions"]} == {"ASC606"}
    assert {row[3] for row in every.stored["obligations"]} == {"AVM-UK", "AVM-US"}
    assert {row[1] for row in every.stored["schedule"]} == {"AVM-UK", "AVM-US"}
    assert {row[1] for row in every.stored["ledger"]} == {"AVM-UK", "AVM-US"}
    assert every.stored["computation"][4:] == (None, SYSTEM)
    for name in ("versions", "obligations", "balances", "postings", "ledger"):
        assert every.stored[name], name
        assert {row[-1] for row in every.stored[name]} == {SYSTEM}, name
    assert every.stored["control"] == [("CTL-012", "PASS")]
    # The same for a caller of AVM-UK and inside a narrowed import: hashes, rows and heads.
    assert scoped.stored == every.stored
    assert narrowed.stored == every.stored
    for seen in (scoped, narrowed):
        assert (seen.status, seen.exceptions, seen.heads_at_computation, seen.dirty) == (
            "SUCCEEDED",
            0,
            True,
            None,
        )
    # What stays the caller's: every read after the computation.
    assert (every.before, every.after, every.scope_after) == (
        ["AVM-UK", "AVM-US"],
        ["AVM-UK", "AVM-US"],
        "*",
    )
    assert (scoped.before, scoped.after, scoped.scope_after, scoped.user_after) == (
        ["AVM-UK"],
        ["AVM-UK"],
        str(uk),
        str(una.user_id),
    )
    assert (narrowed.before, narrowed.after, narrowed.scope_after, narrowed.user_after) == (
        ["AVM-UK"],
        ["AVM-UK"],
        str(uk),
        "",
    )
    assert us != uk


def _latest(place: Workspace, group_id: UUID) -> Mapping[str, Any]:
    (row,) = place.rows(
        select(contract_computation)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )
    return row


def _ledger(place: Workspace, group_id: UUID) -> list[tuple[Any, ...]]:
    """Every sealed line of the group, by entity."""
    entity = legal_entity.alias("line_entity")
    rows = place.rows(
        select(
            subledger_line.c.book_code,
            entity.c.code,
            subledger_line.c.period_end_date,
            subledger_line.c.account_role,
            subledger_line.c.dr_cr,
            subledger_line.c.amount_txn,
        )
        .join(entity, entity.c.id == subledger_line.c.entity_id)
        .join(subledger_posting, subledger_posting.c.id == subledger_line.c.subledger_posting_id)
        .where(subledger_posting.c.combination_group_id == group_id)
    )
    return sorted(tuple(str(value) for value in row.values()) for row in rows)


def _figures(place: Workspace, group_id: UUID) -> list[tuple[Any, ...]]:
    """The obligation figures of the group's current version per book."""
    latest = (
        select(
            contract_version.c.book_code,
            func.max(contract_version.c.version_no).label("version_no"),
        )
        .where(contract_version.c.combination_group_id == group_id)
        .group_by(contract_version.c.book_code)
        .subquery()
    )
    rows = place.rows(
        select(
            obligation_version.c.book_code,
            obligation_version.c.obligation_key,
            obligation_version.c.allocated_amount,
            obligation_version.c.revenue_cum,
            obligation_version.c.billed_cum,
            obligation_version.c.scheduled_amount,
        )
        .join(contract_version, contract_version.c.id == obligation_version.c.contract_version_id)
        .join(
            latest,
            (latest.c.book_code == contract_version.c.book_code)
            & (latest.c.version_no == contract_version.c.version_no),
        )
        .where(contract_version.c.combination_group_id == group_id)
    )
    return sorted(tuple(str(value) for value in row.values()) for row in rows)


def nothing_to_correct(place: Workspace, group_id: UUID) -> None:
    """The ledger as oracle: a computation of the group by a caller of every entity, after a
    scoped caller's command, posts nothing and changes no figure."""
    ledger, figures = _ledger(place, group_id), _figures(place, group_id)
    computed(place, group_id)
    assert _ledger(place, group_id) == ledger
    assert _figures(place, group_id) == figures


def recorded(app: FastAPI, actor: Actor, contract_id: UUID, event: Mapping[str, Any]) -> Any:
    head = get(app, f"{CONTRACTS}/{contract_id}", actor).json()["head_stream_version"]
    return post(
        app,
        f"{CONTRACTS}/{contract_id}/events",
        actor,
        {"events": [dict(event)]},
        if_match=f'"s{head}"',
    )


def manual_event_sent(
    app: FastAPI, preparer: Actor, contract_id: UUID, event: Mapping[str, Any]
) -> Any:
    """``POST /contracts/{id}/events`` with one manual event and an evidence file the preparer
    uploads, answered as it is (BUILD_SPEC CTR-6; 04 §16.3 "Manual events")."""
    head = get(app, f"{CONTRACTS}/{contract_id}", preparer).json()["head_stream_version"]
    return post(
        app,
        f"{CONTRACTS}/{contract_id}/events",
        preparer,
        {"events": [dict(event)], "evidence_file_ids": [evidence_file(app, preparer)]},
        if_match=f'"s{head}"',
    )


def manual_event_requested(
    app: FastAPI, preparer: Actor, contract_id: UUID, event: Mapping[str, Any]
) -> str:
    """A manual event as the product takes it since BUILD_SPEC CTR-6: the preparer's request
    stores the batch with its evidence file and appends nothing. The id of the approval request
    it answers."""
    sent = manual_event_sent(app, preparer, contract_id, event)
    assert sent.status_code == 201, sent.text
    assert set(sent.json()) == {"event_submission_id", "approval_request_id"}, sent.text
    return str(sent.json()["approval_request_id"])


def recorded_and_approved(
    app: FastAPI, preparer: Actor, approver: Actor, contract_id: UUID, event: Mapping[str, Any]
) -> None:
    """``manual_event_requested``, then the approval of another holder of ``event.approve``,
    which appends the events and computes the group in the approver's transaction."""
    decided = approve(app, manual_event_requested(app, preparer, contract_id, event), approver)
    assert decided.status_code == 200, decided.text


INVOICE: Final = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-06-05",
    "payload": {
        "invoice_number": "INV-UK-0777",
        "line_external_id": "INV-UK-0777-1",
        "amount": {"amount": "100.00", "currency": "GBP"},
        "issue_date": "2026-06-05",
    },
}


def test_an_event_recorded_by_a_user_of_one_entity_computes_the_whole_group(k04: K04World) -> None:
    """Una (AVM-UK) records an invoice on ``SF-ORD-UK-2001`` through the route: 201, the
    computation SUCCEEDED, no exception item, the head of the group and of the contract at it. The
    event and its audit event are hers; the computation, its version and its posting are SYSTEM's
    and its audit events name her as ``on_behalf_of_id``. She still cannot read AVM-US. A
    computation by Maya afterwards finds nothing to correct."""
    app, place = k04.app, k04.report.place
    una_member = colleague(k04.report.tenant_id, "una")
    una = holding(app, una_member, "revenue_accountant", entity_ids=[k04.uk_entity_id])
    sent = recorded(app, una, k04.contract_id, INVOICE)
    assert sent.status_code == 201, sent.text
    assert sent.json()["computation"]["status"] == "SUCCEEDED", sent.text
    latest = _latest(place, k04.group_id)
    computation_id = UUID(str(latest["id"]))
    assert (str(latest["status"]), latest["created_by"], str(latest["created_by_kind"])) == (
        "SUCCEEDED",
        None,
        SYSTEM,
    )
    assert (
        place.rows(
            select(exception_item.c.code).where(
                exception_item.c.combination_group_id == k04.group_id
            )
        )
        == []
    )
    group = place.rows(
        select(combination_group.c.head_computation_id, combination_group.c.dirty_since).where(
            combination_group.c.id == k04.group_id
        )
    )
    assert [(row["head_computation_id"], row["dirty_since"]) for row in group] == [
        (computation_id, None)
    ]
    # Whose rows: the command's are the caller's, the computation's are SYSTEM's on her behalf.
    events = place.rows(
        select(audit_event.c.action, audit_event.c.actor_kind, audit_event.c.actor_id)
        .where(audit_event.c.request_id == sent.headers["x-request-id"])
        .where(audit_event.c.object_type == "contract_event")
    )
    assert events and {(str(row["actor_kind"]), row["actor_id"]) for row in events} == {
        ("USER", una_member.user_id)
    }
    computations = place.rows(
        select(audit_event.c.actor_kind, audit_event.c.actor_id, audit_event.c.on_behalf_of_id)
        .where(audit_event.c.request_id == sent.headers["x-request-id"])
        .where(audit_event.c.object_type == "contract_computation")
    )
    assert [tuple(row.values()) for row in computations] == [(SYSTEM, None, una_member.user_id)]
    # What stays hers: the reads after the command.
    hidden = get(app, f"/api/v1/entities/{k04.us_entity_id}", una)
    assert hidden.status_code == 404, hidden.text
    nothing_to_correct(place, k04.group_id)


JANUARY: Final = "FY2026-P01"
# 04 T-CON-03 ``period_ends_open``: the period ends of AVM-US in the ASC606 book are posted for
# every period that ends before 1 Feb 2026.
POSTED_THROUGH_JANUARY: Final = MappingProxyType({f"{AVM_US}|ASC606": "2026-02-01"})


def _mark(place: Workspace, group_id: UUID) -> dict[str, str]:
    """``combination_group.period_ends_open`` of the group, read under the tenant's scope."""
    found = place.scalar(
        select(combination_group.c.period_ends_open).where(combination_group.c.id == group_id)
    )
    return dict(found or {})


def _window_rows(tenant_id: UUID, us: UUID, scope: Any) -> tuple[int, int]:
    """(close runs, period states) of AVM-US a transaction of ``scope`` reads: the rows the
    read of a window joins (``period_ends.window_held``)."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=scope)
    with tenant_session(context, read_only=True) as session:
        found = [
            session.execute(
                select(func.count()).select_from(table).where(table.c.entity_id == us)
            ).scalar_one()
            for table in (close_run, period_state)
        ]
    return int(found[0]), int(found[1])


def test_a_fact_recorded_inside_another_entitys_window_leaves_the_mark_of_a_user_of_every_entity(
    k04: K04World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item WINDOW-MARK-NARROWED-1 (the supervisor's ruling of 2026-10-01 on the window read's
    scope; 04 T-CON-03 "Period-end mark"; 05 RCP-08; dev-guide DG-ARC-16 (3) and DG-CMD-10, rev
    1.245). Inside a window — a close run of one of the group's entities has posted a period end
    that is still postable — a computation writes the group's mark, and the read that finds the
    window is as wide as the computation that asks.

    AVM-US runs January's close and January stays open: a window of AVM-US. A transaction scoped
    to AVM-UK reads neither that run nor a period state of AVM-US — the rows the window read
    joins. ``SF-ORD-UK-2004`` — the terms of WLD-K-04: contracted by AVM-UK, O1 performed by
    AVM-US — is committed inside the window and never computed, so its group holds no mark.

    One committed stream, computed by a user of every entity, by a user of AVM-UK and inside an
    import narrowed to AVM-UK, each rolled back: the three leave one mark — the period ends of
    AVM-US posted through January, the entry a computation inside a window gives a scope that
    holds none (item CLO-GATE-RUN-2). Then through the route: Una's invoice computes the group
    and commits that mark, and a computation by Maya afterwards changes neither the mark nor the
    ledger.

    The read is the one input of the mark a caller's scope could change:
    ``period_ends.after_computation`` is a function of the bundle and of what the read returned.
    Fail-first (measured on c862c175 with the read made under the entity scope in force when the
    computation began): the user of every entity still left the mark; the user of AVM-UK, the
    narrowed import and the route each left none — ``{}`` against the reference.

    Not witnessed here: a fact that LOWERS an entry. WLD-K-04 gives AVM-US no period-end amount
    — its lines are the intercompany pair a computation posts itself (POLICIES JET-13; class
    ``EVENT``), which POL-164 does not remeasure — so no fact of this world moves an entry of
    AVM-US back. The lowering is witnessed for a user of every entity in
    ``tests/domain/close/test_close_run_gate.py``
    (``test_a_computation_is_judged_by_the_passes_only_inside_a_window``)."""
    app, place = k04.app, k04.report.place
    tenant_id, uk, us = k04.report.tenant_id, k04.uk_entity_id, k04.us_entity_id
    run = runs.closed(k04.report, monkeypatch, entity_code=AVM_US, period_key=JANUARY)
    assert run["status"] == "SUCCEEDED", run
    assert runs.posted(tenant_id, run["id"]) == []  # nothing of AVM-US to post in January
    assert _mark(place, k04.group_id) == POSTED_THROUGH_JANUARY  # the run passed the group
    # the rows of the window, and what a transaction of AVM-UK reads of them
    close_runs, states = _window_rows(tenant_id, us, "*")
    assert close_runs == 1 and states > 0
    assert _window_rows(tenant_id, us, (uk,)) == (0, 0)

    contract_id, group_id = twin(k04, "SF-ORD-UK-2004")
    never_computed = place.scalar(
        select(combination_group.c.head_computation_id).where(combination_group.c.id == group_id)
    )
    assert never_computed is None
    assert _mark(place, group_id) == {}

    una_member = colleague(tenant_id, "una")
    every = computed_as(place, place.principal, group_id)
    scoped = computed_as(place, of_entities(person(una_member, "Una Lindqvist"), uk), group_id)
    narrowed = computed_as(
        place,
        system_principal(tenant_id, on_behalf_of_id=una_member.user_id),
        group_id,
        narrow=frozenset({uk}),
    )
    assert (every.status, scoped.status, narrowed.status) == ("SUCCEEDED",) * 3
    assert (every.before, scoped.before, narrowed.before) == (
        ["AVM-UK", "AVM-US"],
        ["AVM-UK"],
        ["AVM-UK"],
    )
    # the reference: a user of every entity
    assert every.mark == POSTED_THROUGH_JANUARY
    assert scoped.mark == every.mark
    assert narrowed.mark == every.mark
    assert _mark(place, group_id) == {}  # each of the three was rolled back

    # through the route: the fact of a user of AVM-UK
    una = holding(app, una_member, "revenue_accountant", entity_ids=[uk])
    sent = recorded(app, una, contract_id, INVOICE)
    assert sent.status_code == 201, sent.text
    assert sent.json()["computation"]["status"] == "SUCCEEDED", sent.text
    assert _mark(place, group_id) == POSTED_THROUGH_JANUARY
    nothing_to_correct(place, group_id)
    assert _mark(place, group_id) == POSTED_THROUGH_JANUARY


def _group_of(place: Workspace, contract_id: UUID) -> UUID:
    return UUID(
        str(
            place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == contract_id)
            )
        )
    )


def _statuses(place: Workspace, group_id: UUID) -> list[tuple[str, str]]:
    """Status and stamp of every computation of the group, oldest first."""
    rows = place.rows(
        select(contract_computation.c.status, contract_computation.c.created_by_kind)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at, contract_computation.c.id)
    )
    return [(str(row["status"]), str(row["created_by_kind"])) for row in rows]


def _exceptions(place: Workspace, group_id: UUID) -> list[str]:
    rows = place.rows(
        select(exception_item.c.code).where(exception_item.c.combination_group_id == group_id)
    )
    return sorted(str(row["code"]) for row in rows)


def _ledger_sums(place: Workspace, group_id: UUID) -> list[tuple[str, ...]]:
    """The group's sealed lines netted by book, entity, period and role (amounts are signed)."""
    entity = legal_entity.alias("line_entity")
    rows = place.rows(
        select(
            subledger_line.c.book_code,
            entity.c.code,
            subledger_line.c.period_end_date,
            subledger_line.c.account_role,
            func.sum(subledger_line.c.amount_txn).label("txn"),
            func.sum(subledger_line.c.amount_functional).label("functional"),
        )
        .join(entity, entity.c.id == subledger_line.c.entity_id)
        .join(subledger_posting, subledger_posting.c.id == subledger_line.c.subledger_posting_id)
        .where(subledger_posting.c.combination_group_id == group_id)
        .group_by(
            subledger_line.c.book_code,
            entity.c.code,
            subledger_line.c.period_end_date,
            subledger_line.c.account_role,
        )
    )
    return sorted(
        tuple(str(value) for value in row.values())
        for row in rows
        if row["txn"] != 0 or row["functional"] != 0
    )


def _events_of_k04() -> list[dict[str, Any]]:
    """The events ``k04_saltmarsh`` records after activation, as route bodies."""

    def progress(ratio: str, day: str) -> dict[str, Any]:
        return {
            "event_type": "PROGRESS_RECORDED",
            "effective_date": day,
            "payload": {
                "obligation_key": "O2",
                "cumulative_progress_ratio": ratio,
                "measure": "OUTPUT_PERCENT",
            },
        }

    return [
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-04-01",
            "payload": {
                "invoice_number": "INV-UK-0601",
                "line_external_id": "INV-UK-0601-1",
                "amount": {"amount": "68000.00", "currency": "GBP"},
                "issue_date": "2026-04-01",
            },
        },
        progress("0.50", "2026-04-30"),
        progress("1", "2026-05-31"),
    ]


def test_users_of_one_entity_book_activate_bill_and_hold_a_contract_of_two(
    k04: K04World, clock: FrozenClock
) -> None:
    """Every command family that computes in its own transaction, through its route, by people
    whose roles cover AVM-UK only — Una (Revenue Accountant) and Ulrich (Revenue Reviewer) — on a
    contract whose O1 is performed by AVM-US:

    - booking: ``POST /contracts`` names AVM-US as a line's performing entity and is not refused;
      the provisional computation succeeds;
    - a reviewed judgement and the Step 1 event, the approved activation (the decision computes in
      the approver's transaction and posts April to September for AVM-US), the invoice and the
      progress events, a recognition hold on O1 and its release.

    Every computation of the group SUCCEEDED as SYSTEM and nothing was raised. After the events
    of WLD-K-04 the contract holds the figures of ``SF-ORD-UK-2001`` itself, which users of every
    entity built — obligation by obligation and, in the ledger, entity by entity and period by
    period — and a computation by a user of every entity finds nothing to correct at any step."""
    app, place = k04.app, k04.report.place
    tenant_id, uk = k04.report.tenant_id, k04.uk_entity_id
    una = holding(app, colleague(tenant_id, "una"), "revenue_accountant", entity_ids=[uk])
    reviewer = colleague(tenant_id, "ulrich")
    assign(reviewer, "revenue_reviewer", entity_ids=[uk])
    ulrich = enrolled(app, clock, reviewer)
    path = f"{CONTRACTS}/{{contract_id}}"

    body = {**terms(k04, "SF-ORD-UK-2003"), "document_ref": "SF-ORD-UK-2003"}
    created = post(app, CONTRACTS, una, body)
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    group_id = _group_of(place, contract_id)
    assert _statuses(place, group_id) == [("SUCCEEDED", SYSTEM)]

    # Step 1: a judgement Una prepares and Ulrich reviews, then the assessment event. The record
    # answers the five criteria of 606-10-25-1 before it is sent for review (04 T-CON-19 rev
    # 1.150; supervisor rulings R-113 (f), R-115 (f)).
    record = post(
        app,
        "/api/v1/judgements",
        una,
        {
            "topic": "COLLECTIBILITY",
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "book": "ASC606",
            "conclusion": "Collection of the consideration is probable.",
            "rationale": "Credit review of the customer and its payment history.",
            "questionnaire": {"criteria": step1_criteria()},
        },
    )
    assert record.status_code == 201, record.text
    sent = post(app, f"/api/v1/judgements/{record.json()['id']}/submit", una, {})
    assert sent.status_code == 200, sent.text
    reviewed = approve(app, sent.json()["approval_request_id"], ulrich)
    assert reviewed.status_code == 200, reviewed.text
    assessed = recorded(
        app,
        una,
        contract_id,
        {
            "event_type": "COLLECTIBILITY_ASSESSED",
            "effective_date": "2026-04-01",
            "payload": {
                "book": "ASC606",
                "is_probable": True,
                "judgement_record_id": record.json()["id"],
            },
        },
    )
    assert assessed.status_code == 201, assessed.text

    # The distinct review of the implementation line (a decision of Ulrich's) and the
    # suggestion to combine with SF-ORD-UK-2001, which Una dismisses.
    review = post(
        app,
        f"{path.format(contract_id=contract_id)}/obligations/O2/distinct-review",
        una,
        {
            "distinctness": "distinct",
            "rationale": "Customer can benefit with readily available resources (606-10-25-19).",
        },
    )
    assert review.status_code == 201, review.text
    distinct = approve(app, review.json()["approval_request_id"], ulrich)
    assert distinct.status_code == 200, distinct.text
    suggested = get(app, "/api/v1/combination-suggestions", una, {"contract": str(contract_id)})
    assert suggested.status_code == 200, suggested.text
    for suggestion in suggested.json()["items"]:
        dismissed = post(
            app,
            f"/api/v1/combination-suggestions/{suggestion['id']}/dismiss",
            una,
            {"rationale": "Separate purchasing entities; negotiated independently."},
        )
        assert dismissed.status_code == 200, dismissed.text

    # Activation: Una submits, Ulrich decides; the decision computes and posts.
    head = get(app, path.format(contract_id=contract_id), una).json()["head_stream_version"]
    submitted = post(
        app,
        f"{path.format(contract_id=contract_id)}/submit-activation",
        una,
        {},
        if_match=f'"s{head}"',
    )
    assert submitted.status_code == 200, submitted.text
    clock.advance(timedelta(minutes=1))
    decided = approve(app, submitted.headers["x-erev-approval-request"], ulrich)
    assert decided.status_code == 200, decided.text
    shown = get(app, path.format(contract_id=contract_id), una).json()
    assert shown["status"] == "ACTIVE", shown
    nothing_to_correct(place, group_id)

    # The events of WLD-K-04, each its own command. The invoice is appended and computed by Una's
    # request; a progress event is a manual event (BUILD_SPEC CTR-6): her request stores it with
    # its evidence, and Ulrich's approval appends it and computes the group of both entities.
    for event in _events_of_k04():
        if event["event_type"] == "PROGRESS_RECORDED":
            recorded_and_approved(app, una, ulrich, contract_id, event)
            assert str(_latest(place, group_id)["status"]) == "SUCCEEDED"
            continue
        answered = recorded(app, una, contract_id, event)
        assert answered.status_code == 201, answered.text
        assert answered.json()["computation"]["status"] == "SUCCEEDED", answered.text
    assert _exceptions(place, group_id) == []
    assert {status for status in _statuses(place, group_id)} == {("SUCCEEDED", SYSTEM)}
    # The same figures as the contract users of every entity built (WLD-X-14: 58,285.71 and
    # 9,714.29), and the same ledger by entity and period.
    figures = _figures(place, group_id)
    assert figures == _figures(place, k04.group_id)
    assert [(row[1], Decimal(row[2])) for row in figures] == [
        ("O1", Decimal("58285.71")),
        ("O2", Decimal("9714.29")),
    ]
    sums = _ledger_sums(place, group_id)
    assert sums == _ledger_sums(place, k04.group_id)
    assert {row[1] for row in sums} == {AVM_UK, AVM_US}
    nothing_to_correct(place, group_id)

    # A recognition hold on the obligation AVM-US performs, and its release.
    head = get(app, path.format(contract_id=contract_id), una).json()["head_stream_version"]
    held = post(
        app,
        f"{path.format(contract_id=contract_id)}/apply-hold",
        una,
        {"hold_type": "recognition", "obligation_key": "O1", "reason": "Disputed by the customer."},
        if_match=f'"s{head}"',
    )
    assert held.status_code == 200, held.text
    (hold,) = place.rows(
        select(contract_hold.c.id).where(contract_hold.c.contract_id == contract_id)
    )
    nothing_to_correct(place, group_id)
    released = post(
        app,
        f"{path.format(contract_id=contract_id)}/release-hold",
        una,
        {"hold_id": str(hold["id"]), "comment": "Dispute settled."},
        if_match=f'"s{head + 1}"',
    )
    assert released.status_code == 200, released.text
    assert _exceptions(place, group_id) == []
    assert {status for status in _statuses(place, group_id)} == {("SUCCEEDED", SYSTEM)}
    # held and released on one day: the ledger of both entities is where it was
    assert _ledger_sums(place, group_id) == sums
    nothing_to_correct(place, group_id)


# --- the bundle, the writer's guard and the transaction's settings --------------------------------


def test_a_bundle_has_one_hash_under_every_scope_and_the_writer_refuses_a_narrow_one(
    k04: K04World,
) -> None:
    """Bundle assembly is the choke point of every computation and of every dry run. The bundle
    of ``SF-ORD-UK-2002`` — and the dry-run bundle that carries a pending invoice — has one hash
    in a session of every entity, in a session of AVM-UK and inside an import narrowed to AVM-UK,
    and holds both entities each time; the caller's scope is its own again after each build.
    ``computation._persist``, reached past its wrapper under an entity scope, refuses by name."""
    place = k04.report.place
    uk = k04.uk_entity_id
    una = colleague(k04.report.tenant_id, "una")
    contract_id, group_id = twin(k04, "SF-ORD-UK-2002")
    pending = [billing("INV-DRY-RUN", "250.00", date(2026, 7, 1))]

    def built(principal: Principal, narrow: frozenset[UUID] | None = None) -> tuple[Any, ...]:
        with place.uow(principal) as uow, narrowed_to(uow, narrow):
            session = uow.session
            before = visible_entities(session)
            real = bundles.build(session, group_id, uow.now, (), ComputationTrigger.COMMAND)
            dry = bundles.build(
                session,
                group_id,
                uow.now,
                pending,
                DRY_RUN,
                pending_contract_id=contract_id,
                cutoff=CUTOFF,  # a pending event is recorded at the cutoff, which enters the hash
            )
            found = bundles.index(session, real)
            return (
                real.sha256(),
                dry.sha256(),
                sorted(item.code for item in real.entities),
                sorted(found.entities),
                before == visible_entities(session),
            )

    every = built(place.principal)
    assert every[2:] == (["AVM-UK", "AVM-US"], ["AVM-UK", "AVM-US"], True)
    assert every[0] != every[1]
    scoped_user = of_entities(person(una, "Una Lindqvist"), uk)
    assert built(scoped_user) == every
    assert built(
        system_principal(place.tenant_id, on_behalf_of_id=una.user_id), frozenset({uk})
    ) == (every)
    # The writer's own guard: nothing is written under an entity scope.
    with place.uow(scoped_user) as uow:
        bundle = bundles.build(uow.session, group_id, uow.now, (), ComputationTrigger.COMMAND)
        output = engine()(bundle)
        with pytest.raises(ScopeNotTenantWide):
            computation._persist(uow, bundle, output, duration_ms=0, job_id=None, close_run_id=None)
        assert (
            uow.session.execute(
                select(func.count())
                .select_from(contract_computation)
                .where(contract_computation.c.combination_group_id == group_id)
            ).scalar_one()
            == 0
        )
        uow.discard()


class Boom(Exception):
    """An error raised inside the manager by a test."""


def _settings_of_the_pool() -> list[tuple[int, str | None, str | None]]:
    """Idle connections of the application's pool, checked out at once (the pool hands out the
    most recently returned first): each one's backend and the two settings as its next
    transaction finds them. Read through the driver, because the application's engine refuses
    SQL outside a tenant session (DG-KRN-DB-04)."""
    engine_ = app_engine()
    held = [engine_.raw_connection() for _ in range(POOL_PROBES)]
    try:
        found = []
        for raw in held:
            cursor = raw.cursor()
            cursor.execute(
                "SELECT pg_backend_pid(), current_setting('app.entity_scope', true), "
                "current_setting('app.user_id', true)"
            )
            found.append(tuple(cursor.fetchone()))
            cursor.close()
        return found
    finally:
        for raw in held:
            raw.rollback()
            raw.close()


def test_the_tenant_scope_never_outlives_the_computation(k04: K04World) -> None:
    """R-103 (b) (3). A unit of work of a user of AVM-UK computes a group that reaches AVM-US and
    ends by commit, by rollback and by an exception raised inside the manager. Inside the
    manager the transaction reads both entities as SYSTEM; at its exit the caller reads, and may
    write, AVM-UK only — an exception item naming AVM-US is refused by row-level security — and
    afterwards the pooled connection that served it carries neither ``*`` nor the SYSTEM user
    into its next transaction."""
    place = k04.report.place
    uk, us = k04.uk_entity_id, k04.us_entity_id
    una = of_entities(person(colleague(k04.report.tenant_id, "una"), "Una Lindqvist"), uk)
    _, group_id = twin(k04, "SF-ORD-UK-2002")
    served: dict[str, int] = {}

    def after_the_manager(uow: UnitOfWork) -> None:
        session = uow.session
        assert uow.principal is una
        assert visible_entities(session) == ["AVM-UK"]
        assert str(session.execute(ENTITY_SCOPE).scalar_one()) == str(uk)
        unseen = session.execute(
            update(legal_entity).where(legal_entity.c.id == us).values(name=legal_entity.c.name)
        )
        assert unseen.rowcount == 0
        refused = session.begin_nested()
        with pytest.raises(DBAPIError) as raised:
            raise_exception_item(
                uow,
                source=ExceptionSource.ENGINE,
                code="ENGINE_INVARIANT_VIOLATION",
                severity=ExceptionSeverity.WARNING,
                message="A row of another entity, written after the computation.",
                dedupe=f"TEST:{uow.ctx.request_id}",
                combination_group_id=group_id,
                entity_id=us,
            )
        refused.rollback()
        assert db_errors.sqlstate(raised.value) == db_errors.INSUFFICIENT_PRIVILEGE

    # by commit
    with place.uow(una) as uow:
        served["commit"] = int(uow.session.execute(text("SELECT pg_backend_pid()")).scalar_one())
        outcome = compute_job.compute_group(uow, group_id)
        assert outcome.status is ComputationStatus.SUCCEEDED
        after_the_manager(uow)
        uow.commit()
    committed = _settings_of_the_pool()
    # by rollback
    with place.uow(una) as uow:
        served["rollback"] = int(uow.session.execute(text("SELECT pg_backend_pid()")).scalar_one())
        with uow.as_system():
            assert visible_entities(uow.session) == ["AVM-UK", "AVM-US"]
            assert uow.principal.kind is PrincipalKind.SYSTEM
            assert uow.principal.on_behalf_of_id == una.id
            assert str(uow.session.execute(USER_ID).scalar_one()) == ""
        after_the_manager(uow)
        uow.discard()
    rolled_back = _settings_of_the_pool()
    # by an exception raised inside the manager: the settings are the caller's when it leaves
    with pytest.raises(Boom), place.uow(una) as uow:
        served["exception"] = int(uow.session.execute(text("SELECT pg_backend_pid()")).scalar_one())
        try:
            with uow.as_system():
                assert visible_entities(uow.session) == ["AVM-UK", "AVM-US"]
                raise Boom
        except Boom:
            after_the_manager(uow)
            raise
    raised = _settings_of_the_pool()
    # a database error inside the manager aborts the transaction: nothing can be re-issued, and
    # the caller's rollback to its own savepoint brings its settings back
    with place.uow(una) as uow:
        served["aborted"] = int(uow.session.execute(text("SELECT pg_backend_pid()")).scalar_one())
        own = uow.session.begin_nested()
        with pytest.raises(DBAPIError), uow.as_system():
            uow.session.execute(text("SELECT 1 / 0"))
        own.rollback()
        after_the_manager(uow)
        uow.discard()
    aborted = _settings_of_the_pool()
    for name, found in (
        ("commit", committed),
        ("rollback", rolled_back),
        ("exception", raised),
        ("aborted", aborted),
    ):
        assert served[name] in {pid for pid, _, _ in found}, (name, served[name], found)
        assert {(scope or "", user or "") for _, scope, user in found} == {("", "")}, (name, found)


# --- a group of two contracting entities (R-98 (3)) -----------------------------------------------


def _two_entities(
    k04: K04World, second: str = NORTHERN, *, events: Sequence[EventIn] = ()
) -> tuple[UUID, UUID, UUID]:
    """``SF-ORD-UK-2004`` — contracted and performed by AVM-UK — and a contract of ``second``
    for the same customer, in GBP as well, each active and computed, combined through the routes
    by people of every entity: (the AVM-UK contract, the other contract, the group). The other
    contract is ``SF-ORD-NI-3001`` of AVM-NI, an entity created here with GBP books and the
    calendar of AVM-UK, or ``SF-ORD-US-3001`` of AVM-US, whose books are in USD; ``events`` are
    appended to it before it is computed."""
    place, app = k04.report.place, k04.app
    maya = k04.report.maya
    if second == NORTHERN:
        (uk,) = [
            item
            for item in get(app, "/api/v1/entities", maya).json()["items"]
            if item["code"] == AVM_UK
        ]
        entity(
            app,
            maya,
            code=NORTHERN,
            calendar_id=str(uk["calendar_id"]),
            functional_currency="GBP",
            time_zone="Europe/London",
        )
        open_periods(
            app,
            maya,
            entity_code=NORTHERN,
            keys=[f"FY2026-P{month:02d}" for month in range(1, 10)],
        )
    customer = str(k04.report.contracts[K04].contract["customer_id"])
    term = {"start_date": "2026-04-01", "end_date": "2027-03-31"}
    base = {"customer_id": customer, "transaction_currency": "GBP", "inception_date": "2026-04-01"}
    british = booked_contract(
        place,
        {
            **base,
            "external_id": "SF-ORD-UK-2004",
            "contracting_entity_code": AVM_UK,
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": PLATFORM_UK,
                    "quantity": "1",
                    "total_price": {"amount": "60000.00", "currency": "GBP"},
                    **term,
                },
                {
                    "obligation_key": "O2",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity": "1",
                    "total_price": {"amount": "8000.00", "currency": "GBP"},
                },
            ],
        },
        activate=True,
    )
    american = booked_contract(
        place,
        {
            **base,
            "external_id": OTHER_ORDER[second],
            "contracting_entity_code": second,
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity": "1",
                    "total_price": {"amount": "5000.00", "currency": "GBP"},
                }
            ],
        },
        activate=True,
    )
    ids = [UUID(str(booked.contract["id"])) for booked in (british, american)]
    if events:
        appended(place, ids[1], 2, events)
    for booked in (british, american):
        computed(place, UUID(str(booked.combination_group["id"])))
    proposed = post(
        app,
        GROUPS,
        k04.report.maya,
        {
            "contract_ids": [str(value) for value in ids],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(str(proposed.json()["id"]))
    submitted = post(app, f"{GROUPS}/{group_id}/submit", k04.report.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], k04.report.marcus)
    assert approved.status_code == 200, approved.text
    assert {_group_of(place, value) for value in ids} == {group_id}
    return ids[0], ids[1], group_id


@pytest.mark.parametrize("second", [NORTHERN, AVM_US], ids=["gbp-books", "usd-books"])
def test_an_event_on_one_member_computes_the_group_of_two_contracting_entities(
    k04: K04World, clock: FrozenClock, second: str
) -> None:
    """R-98 (3). A combination group {SF-ORD-UK-2004 of AVM-UK, a contract of a second
    contracting entity}; a delivery is recorded on the AVM-UK member. Computed for a user of
    AVM-UK, and inside an import narrowed to AVM-UK, the group stores what it stores for a user of
    every entity: both members' obligations in one allocation, one output hash, both heads.
    Through the route an invoice Una records — a fact that is appended at once — answers
    SUCCEEDED for the whole group. Her progress event is a manual event (BUILD_SPEC CTR-6): its
    request names both contracting entities of the group (R-25), and she is held to the
    contracting entity of the contract she records it on (item MANUAL-EVENT-PREPARER-SCOPE-1; 04
    §16.10 rev 1.269), so her request is stored; approved by a reviewer of every entity it is
    appended, the group is computed SUCCEEDED, and a user of every entity finds nothing to
    correct. Until that item the kernel held her to both entities and refused the submission.

    As built the member contract of the second entity was not in the bundle of a caller of AVM-UK:
    the group computed as if it were the AVM-UK contract alone, SUCCEEDED, with another
    allocation.

    The second entity is AVM-NI, with GBP books, and AVM-US, with USD books: until item
    CTR-BALANCE-ROWS-1 a group whose contracting entities keep different functional currencies
    was not stored at all, for any caller."""
    place, app = k04.report.place, k04.app
    uk = k04.uk_entity_id
    other = OTHER_ORDER[second]
    british, american, group_id = _two_entities(k04, second)
    una_member = colleague(k04.report.tenant_id, "una")
    delivered = EventIn(
        event_type=ContractEventType.PROGRESS_RECORDED,
        effective_date=date(2026, 5, 31),
        payload=ProgressRecordedV1(
            obligation_key="O2", cumulative_progress_ratio="0.50", measure="OUTPUT_PERCENT"
        ),
    )
    head = int(place.scalar(select(contract.c.head_stream_version).where(contract.c.id == british)))
    appended(place, british, head, [delivered])
    every = computed_as(place, place.principal, group_id)
    scoped = computed_as(place, of_entities(person(una_member, "Una Lindqvist"), uk), group_id)
    narrowed = computed_as(
        place,
        system_principal(place.tenant_id, on_behalf_of_id=una_member.user_id),
        group_id,
        narrow=frozenset({uk}),
    )
    assert every.status == "SUCCEEDED" and every.heads_at_computation
    assert {row[1] for row in every.stored["obligations"]} == {"SF-ORD-UK-2004", other}
    assert every.stored["ledger"], "the delivery posts revenue"
    assert scoped.stored == every.stored and scoped.heads_at_computation
    assert narrowed.stored == every.stored and narrowed.heads_at_computation
    assert (scoped.after, narrowed.after) == (["AVM-UK"], ["AVM-UK"])
    # through the route: an invoice of Una's, appended at once, computes the whole group
    una = holding(app, una_member, "revenue_accountant", entity_ids=[uk])
    invoiced = recorded(app, una, british, INVOICE)
    assert invoiced.status_code == 201, invoiced.text
    assert invoiced.json()["computation"]["status"] == "SUCCEEDED", invoiced.text
    # A progress event is a manual event (BUILD_SPEC CTR-6). Its request names the group's two
    # contracting entities; its preparer is held to the contracting entity of the contract she
    # records it on (item MANUAL-EVENT-PREPARER-SCOPE-1), so Una of AVM-UK alone prepares it;
    # approved by a reviewer of every entity, it is appended and the group is computed.
    progress = {
        "event_type": "PROGRESS_RECORDED",
        "effective_date": "2026-06-30",
        "payload": {
            "obligation_key": "O2",
            "cumulative_progress_ratio": "1",
            "measure": "OUTPUT_PERCENT",
        },
    }
    reviewer = colleague(k04.report.tenant_id, "rosa")
    assign(reviewer, "revenue_reviewer")
    rosa = enrolled(app, clock, reviewer)
    recorded_and_approved(app, una, rosa, british, progress)
    latest = _latest(place, group_id)
    assert str(latest["status"]) == "SUCCEEDED"
    members = place.rows(
        select(contract.c.external_id, contract.c.latest_computation_id).where(
            contract.c.combination_group_id == group_id
        )
    )
    assert {str(row["external_id"]): row["latest_computation_id"] for row in members} == {
        "SF-ORD-UK-2004": latest["id"],
        other: latest["id"],
    }
    # The deliveries are dated before the combination: the platform's LATE_EVENT warnings (D-19),
    # and nothing else.
    assert set(_exceptions(place, group_id)) == {"LATE_EVENT"}
    assert american != british
    nothing_to_correct(place, group_id)


def test_a_combination_decided_by_a_reviewer_of_one_entity_computes_the_group(
    k04: K04World, clock: FrozenClock
) -> None:
    """The combination family: Una proposes to combine ``SF-ORD-UK-2001`` and ``SF-ORD-UK-2002``
    — both of AVM-UK, each with an obligation AVM-US performs — and Ulrich, a Revenue Reviewer of
    AVM-UK, decides. The decision computes the group in his transaction: SUCCEEDED, nothing
    raised, and nothing for a user of every entity to correct."""
    app, place = k04.app, k04.report.place
    tenant_id, uk = k04.report.tenant_id, k04.uk_entity_id
    other, other_group = twin(k04, "SF-ORD-UK-2002")
    computed(place, other_group)
    una = holding(app, colleague(tenant_id, "una"), "revenue_accountant", entity_ids=[uk])
    reviewer = colleague(tenant_id, "ulrich")
    assign(reviewer, "revenue_reviewer", entity_ids=[uk])
    ulrich = enrolled(app, clock, reviewer)
    proposed = post(
        app,
        GROUPS,
        una,
        {
            "contract_ids": [str(k04.contract_id), str(other)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(str(proposed.json()["id"]))
    submitted = post(app, f"{GROUPS}/{group_id}/submit", una, {})
    assert submitted.status_code == 200, submitted.text
    clock.advance(timedelta(minutes=1))
    decided = approve(app, submitted.json()["approval_request_id"], ulrich)
    assert decided.status_code == 200, decided.text
    assert {_group_of(place, value) for value in (k04.contract_id, other)} == {group_id}
    assert _statuses(place, group_id) == [("SUCCEEDED", SYSTEM)]
    assert _exceptions(place, group_id) == []
    nothing_to_correct(place, group_id)


def test_a_modification_prepared_and_decided_by_people_of_one_entity_reallocates_the_contract(
    k04: K04World, clock: FrozenClock
) -> None:
    """The modification family on ``SF-ORD-UK-2001``: Una adds an implementation line below its
    standalone selling price from 1 July, classifies it, has the worker compute the preview and
    submits; Ulrich, a Revenue Reviewer of AVM-UK, approves. The approval appends
    ``CONTRACT_AMENDED`` and computes in his transaction — the obligation AVM-US performs is
    reallocated with the rest: SUCCEEDED, nothing blocking raised, and nothing for a user of every
    entity to correct."""
    app, place = k04.app, k04.report.place
    tenant_id, uk = k04.report.tenant_id, k04.uk_entity_id
    una = holding(app, colleague(tenant_id, "una"), "revenue_accountant", entity_ids=[uk])
    reviewer = colleague(tenant_id, "ulrich")
    assign(reviewer, "revenue_reviewer", entity_ids=[uk])
    ulrich = enrolled(app, clock, reviewer)
    created = post(
        app,
        f"{CONTRACTS}/{k04.contract_id}/modifications",
        una,
        {
            "effective_date": "2026-07-01",
            "kind": "ADD_OBLIGATION",
            "reference": "CR-SALTMARSH-2026-07",
            "lines": [
                {
                    "obligation_key": "O3",
                    "action": "ADD",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity_delta": "1",
                    "consideration_delta": {"amount": "5000.00", "currency": "GBP"},
                }
            ],
            "rationale": "Saltmarsh adds a second implementation phase at a negotiated price.",
        },
    )
    assert created.status_code == 201, created.text
    modification_id = created.json()["id"]
    classified = post(app, f"{MODIFICATIONS}/{modification_id}/classify", una, {})
    assert classified.status_code == 200, classified.text
    assert set(classified.json()["proposed_treatments"].values()) == {"PROSPECTIVE"}, (
        classified.text
    )
    confirm_answers(app, modification_id, una)
    queued = post(app, f"{MODIFICATIONS}/{modification_id}/preview", una, {})
    assert queued.status_code == 202, queued.text
    finished = run_now(k04.report, UUID(str(queued.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    submitted = post(
        app,
        f"{MODIFICATIONS}/{modification_id}/submit",
        una,
        {"comment": "Approve the second implementation phase."},
    )
    assert submitted.status_code == 200, submitted.text
    clock.advance(timedelta(minutes=1))
    decided = approve(app, submitted.json()["approval_request_id"], ulrich)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    shown = get(app, f"{MODIFICATIONS}/{modification_id}", una).json()
    assert shown["status"] == "APPLIED", shown
    assert _statuses(place, k04.group_id)[-1] == ("SUCCEEDED", SYSTEM)
    assert set(_exceptions(place, k04.group_id)) <= {"LATE_EVENT"}
    keys = {(row[1]) for row in _figures(place, k04.group_id)}
    assert keys == {"O1", "O2", "O3"}
    nothing_to_correct(place, k04.group_id)


# --- who may ask for a preview (item CTR-PREVIEW-GROUP-SCOPE-1) -----------------------------------

ESTIMATES: Final = "/api/v1/estimates"
VERSIONS: Final = "/api/v1/estimate-versions"
ADJUSTMENTS: Final = "/api/v1/manual-adjustments"
JOBS: Final = "/api/v1/jobs"


@dataclasses.dataclass(frozen=True)
class PreviewRoute:
    """One of the four preview routes, asked about a subject of one contract: the request, and
    what the ``DENIED`` audit event of a refusal names (04 §16.10 rev 1.295) — the action of
    the refused command, the subject as its caller holds it and the route's permission."""

    path: str
    body: Mapping[str, Any]
    precondition: bool  # the events route takes ``If-Match``
    action: str
    subject_type: str
    subject_id: str
    permission: str


def _classified(app: FastAPI, actor: Actor, contract_id: UUID, reference: str) -> str:
    """A DRAFT modification of the contract — a second implementation phase below its
    standalone selling price from 1 July — created and classified by ``actor``; its id."""
    created = post(
        app,
        f"{CONTRACTS}/{contract_id}/modifications",
        actor,
        {
            "effective_date": "2026-07-01",
            "kind": "ADD_OBLIGATION",
            "reference": reference,
            "lines": [
                {
                    "obligation_key": "O3",
                    "action": "ADD",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity_delta": "1",
                    "consideration_delta": {"amount": "5000.00", "currency": "GBP"},
                }
            ],
            "rationale": "A second implementation phase at a negotiated price.",
        },
    )
    assert created.status_code == 201, created.text
    modification_id = str(created.json()["id"])
    classified = post(app, f"{MODIFICATIONS}/{modification_id}/classify", actor, {})
    assert classified.status_code == 200, classified.text
    confirm_answers(app, modification_id, actor)
    return modification_id


def _estimated(app: FastAPI, actor: Actor, contract_id: UUID, code: str) -> str:
    """A rebate of the contract with a DRAFT version of 500.00 GBP from 1 July, prepared by
    ``actor``; the version's id."""
    element = post(
        app,
        f"{CONTRACTS}/{contract_id}/estimates",
        actor,
        {
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "element_code": code,
            "vc_element_type": "REBATE",
            "method": "MOST_LIKELY_AMOUNT",
        },
    )
    assert element.status_code == 201, element.text
    version = post(
        app,
        f"{ESTIMATES}/{element.json()['id']}/versions",
        actor,
        {
            "effective_date": "2026-07-01",
            "scenarios": [{"outcome": "Threshold met", "amount": "500.00"}],
            "unconstrained_amount": "500.00",
            "most_conservative_amount": "500.00",
            "constrained_amount": "500.00",
            "rationale": "The customer is expected to reach the rebate threshold.",
        },
    )
    assert version.status_code == 201, version.text
    return str(version.json()["id"])


def _adjusted(app: FastAPI, place: Workspace, actor: Actor, contract_id: UUID) -> str:
    """A DRAFT manual release of 100.00 GBP on O2 of the contract, prepared by ``actor``; its
    id."""
    (found,) = place.rows(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O2"
        )
    )
    created = post(
        app,
        ADJUSTMENTS,
        actor,
        {
            "kind": "MANUAL_RELEASE",
            "contract_id": str(contract_id),
            "effective_date": "2026-06-30",
            "reason_code": "ESTIMATE_CORRECTION",
            "memo": "Phase accepted on 30 June 2026",
            "payload": {
                "obligation_id": str(found["id"]),
                "amount": {"amount": "100.00", "currency": "GBP"},
            },
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _preview_routes(
    contract_id: UUID, modification_id: str, version_id: str, adjustment_id: str
) -> list[PreviewRoute]:
    """The four routes that defer a dry run, each with a subject of ``contract_id``: an invoice
    that is not recorded yet, the modification, the estimate version, the manual adjustment."""
    return [
        PreviewRoute(
            f"{CONTRACTS}/{contract_id}/events/preview",
            {"events": [dict(INVOICE)]},
            True,
            "contract.preview_events",
            approvals.CONTRACT_SUBJECT,  # pending events are stored nowhere
            str(contract_id),
            "event.record",
        ),
        PreviewRoute(
            f"{MODIFICATIONS}/{modification_id}/preview",
            {},
            False,
            "modification.preview",
            "MODIFICATION",
            modification_id,
            "modification.create",
        ),
        PreviewRoute(
            f"{VERSIONS}/{version_id}/preview",
            {},
            False,
            "estimate_version.preview",
            "ESTIMATE_VERSION",
            version_id,
            "estimate.create",
        ),
        PreviewRoute(
            f"{ADJUSTMENTS}/{adjustment_id}/preview",
            {},
            False,
            "manual_adjustment.preview",
            "MANUAL_ADJUSTMENT",
            adjustment_id,
            "adjustment.create",
        ),
    ]


def _asked(app: FastAPI, actor: Actor, contract_id: UUID, route: PreviewRoute) -> Any:
    if not route.precondition:
        return post(app, route.path, actor, dict(route.body))
    head = get(app, f"{CONTRACTS}/{contract_id}", actor).json()["head_stream_version"]
    return post(app, route.path, actor, dict(route.body), if_match=f'"s{head}"')


def _denied(place: Workspace, response: Any) -> list[dict[str, Any]]:
    """The ``DENIED`` audit events of one request: what was refused, on what, and why. The
    kernel's events are events of the request that is not opened (``approval_request``,
    no id) and name the subject in ``detail``."""
    return place.rows(
        select(
            audit_event.c.action,
            audit_event.c.object_type,
            audit_event.c.object_id,
            audit_event.c.detail,
        )
        .where(audit_event.c.request_id == response.headers["x-request-id"])
        .where(audit_event.c.outcome == AuditOutcome.DENIED)
    )


def _job_count(place: Workspace) -> int:
    return int(place.scalar(select(func.count()).select_from(job)))


def test_a_preview_is_asked_by_who_could_submit_the_subject(k04: K04World) -> None:
    """Item CTR-PREVIEW-GROUP-SCOPE-1 (04 §16.10 rev 1.295 "Who may ask for a preview"; supervisor
    ruling R-103 (b) (5)). A combination group {SF-ORD-UK-2004 of AVM-UK, SF-ORD-US-3001 of
    AVM-US}. Una, a Revenue Accountant of AVM-UK alone, prepares a modification, an estimate
    version and a manual adjustment of the AVM-UK member — her entity's contract, which she
    reads. A dry run of any of them, or of an invoice she has yet to record, reads the whole
    group, and its summary holds the group's transaction price and the journal lines of both
    entities. Each of the four preview routes refuses her by name, 403, defers nothing and leaves
    one ``DENIED`` audit event that names the subject, its contract and no entity; Maya, who
    holds the role for every entity, is answered 202 for the same subjects, and the summary of
    her job is the group's. A contract Una cannot read answers 404 and leaves no event.

    As built (measured on main a101c4c0) the four routes answered Una 202, and the summary of
    her job held 73,000.00 — the group's price, for her contract of 68,000.00."""
    app, place = k04.app, k04.report.place
    maya = k04.report.maya
    british, american, _ = _two_entities(k04, AVM_US)
    una = holding(
        app,
        colleague(k04.report.tenant_id, "una"),
        "revenue_accountant",
        entity_ids=[k04.uk_entity_id],
    )
    routes = _preview_routes(
        british,
        _classified(app, una, british, "CR-UK-2004-2026-07"),
        _estimated(app, una, british, "REBATE-2004"),
        _adjusted(app, place, una, british),
    )
    for route in routes:
        jobs = _job_count(place)
        refused = _asked(app, una, british, route)
        assert refused.status_code == 403, (route.path, refused.text)
        assert refused.json()["detail"] == approvals.OUTSIDE_PREVIEW_DETAIL, route.path
        assert _job_count(place) == jobs, route.path
        assert _denied(place, refused) == [
            {
                "action": route.action,
                "object_type": approvals.OBJECT_TYPE,
                "object_id": None,
                "detail": {
                    "subject_type": route.subject_type,
                    "subject_id": route.subject_id,
                    "reason": approvals.DENIED_PREPARER_SCOPE,
                    "permission": route.permission,
                },
            }
        ], route.path
    for route in routes:
        taken = _asked(app, maya, british, route)
        assert taken.status_code == 202, (route.path, taken.text)
        assert _denied(place, taken) == [], route.path
        finished = run_now(k04.report, UUID(str(taken.json()["id"])))
        assert finished["state"] == "SUCCEEDED", (route.path, finished.get("problem"))
        # the group's price before the change: her contract's own is 68,000.00
        assert finished["result"]["summary"]["transaction_price_before"] == {
            "amount": "73000.00",
            "currency": "GBP",
        }, route.path
    # the order of the answers: her refusal comes before the state of what she asks about —
    # a stale ``If-Match`` is refused to her as before, and is a 412 to Maya
    stale = {"events": [dict(INVOICE)]}
    path = f"{CONTRACTS}/{british}/events/preview"
    assert post(app, path, una, stale, if_match='"s999"').status_code == 403
    assert post(app, path, maya, stale, if_match='"s999"').status_code == 412
    # a contract she cannot read answers as an unknown id does, and nothing is on record
    unknown = post(
        app,
        f"{CONTRACTS}/{american}/events/preview",
        una,
        {"events": [dict(INVOICE)]},
        if_match='"s1"',
    )
    assert unknown.status_code == 404, unknown.text
    assert _denied(place, unknown) == []


def test_a_modification_is_submitted_by_who_covers_its_group(k04: K04World) -> None:
    """04 §16.10 rev 1.295 "A modification's submission asks first" (supervisor rulings R-64 (1)
    and (6)). In the group of two contracting entities Una prepares and classifies a
    modification of the AVM-UK member, and Maya has its preview computed and stored. Una's
    submission is refused by name, 403 — before any finding of the submission is computed —
    with one ``DENIED`` audit event of the submission that names the subject; the row stays a
    draft, and Maya then submits it with the same preview. The refusal comes before the
    row's state for a preview too.

    As built (measured on main a101c4c0) Una was answered 422 ``REQ-PLT-015``, "The stored
    preview is not of this modification as it stands; run the preview again.", for a preview
    that was not stale: its basis holds every member's head, and the submission re-derived it
    under her entity scope, where the AVM-US member is not read. Running it again could not
    help her."""
    app, place = k04.app, k04.report.place
    maya = k04.report.maya
    british, _, _ = _two_entities(k04, AVM_US)
    una = holding(
        app,
        colleague(k04.report.tenant_id, "una"),
        "revenue_accountant",
        entity_ids=[k04.uk_entity_id],
    )
    modification_id = _classified(app, una, british, "CR-UK-2004-2026-07")
    queued = post(app, f"{MODIFICATIONS}/{modification_id}/preview", maya, {})
    assert queued.status_code == 202, queued.text
    stored = run_now(k04.report, UUID(str(queued.json()["id"])))
    assert stored["state"] == "SUCCEEDED", stored
    comment = {"comment": "Approve the second implementation phase."}
    refused = post(app, f"{MODIFICATIONS}/{modification_id}/submit", una, comment)
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == approvals.OUTSIDE_SCOPE_DETAIL
    assert _denied(place, refused) == [
        {
            "action": approvals.SUBMIT_ACTION,
            "object_type": approvals.OBJECT_TYPE,
            "object_id": None,
            "detail": {
                "subject_type": "MODIFICATION",
                "subject_id": modification_id,
                "reason": approvals.DENIED_PREPARER_SCOPE,
                "permission": "",
            },
        }
    ]
    assert get(app, f"{MODIFICATIONS}/{modification_id}", una).json()["status"] == "DRAFT"
    # the control: the preview Una's submission was refused over is the row's as it stands
    submitted = post(app, f"{MODIFICATIONS}/{modification_id}/submit", maya, comment)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    assert _denied(place, submitted) == []
    # the order of the answers: a row that is no draft any more is still refused to her by
    # name, and is a state refusal to Maya
    again = f"{MODIFICATIONS}/{modification_id}/preview"
    assert post(app, again, una, {}).status_code == 403
    assert post(app, again, maya, {}).status_code == 409


def test_the_contracting_entity_previews_a_contract_another_entity_performs(
    k04: K04World,
) -> None:
    """The control of the rule (supervisor ruling R-87 (1); 04 §16.10: a contract subject belongs
    to the entity that CONTRACTS). ``SF-ORD-UK-2001`` is contracted by AVM-UK and alone in its
    group; AVM-US performs one of its obligations. Una, of AVM-UK alone, covers every entity its
    subjects are bound to: the four preview routes answer her 202 with a job of her own,
    nothing is refused on record, and the dry run of the invoice she has yet to record — the
    group's, whole, AVM-US's obligation in it — computes. (The existing test of the family
    above holds her modification's preview and its approval.)"""
    app, place = k04.app, k04.report.place
    contract_id = k04.contract_id
    una = holding(
        app,
        colleague(k04.report.tenant_id, "una"),
        "revenue_accountant",
        entity_ids=[k04.uk_entity_id],
    )
    routes = _preview_routes(
        contract_id,
        _classified(app, una, contract_id, "CR-SALTMARSH-2026-07"),
        _estimated(app, una, contract_id, "REBATE-2001"),
        _adjusted(app, place, una, contract_id),
    )
    jobs: list[str] = []
    for route in routes:
        taken = _asked(app, una, contract_id, route)
        assert taken.status_code == 202, (route.path, taken.text)
        assert _denied(place, taken) == [], route.path
        jobs.append(str(taken.json()["id"]))
        assert get(app, f"{JOBS}/{jobs[-1]}", una).status_code == 200, route.path
    finished = run_now(k04.report, UUID(jobs[0]))
    assert finished["state"] == "SUCCEEDED", finished.get("problem")


# --- who reads a stored preview (item MOD-PREVIEW-READ-SCOPE-1) -----------------------------------

FILES: Final = "/api/v1/files"
SUBMISSION: Final = MappingProxyType({"comment": "Approve the second implementation phase."})


def _document(app: FastAPI, actor: Actor, file_id: Any) -> tuple[int, int]:
    """What the file's own routes answer ``actor`` for a stored document: its row, its content."""
    return (
        get(app, f"{FILES}/{file_id}", actor).status_code,
        get(app, f"{FILES}/{file_id}/content", actor).status_code,
    )


def _previewed(k04: K04World, actor: Actor, modification_id: str) -> None:
    """The dry run of the modification, asked by ``actor`` and worked: its preview is stored."""
    queued = post(k04.app, f"{MODIFICATIONS}/{modification_id}/preview", actor, {})
    assert queued.status_code == 202, queued.text
    stored = run_now(k04.report, UUID(str(queued.json()["id"])))
    assert stored["state"] == "SUCCEEDED", stored


def _stored_preview(body: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    """The three members of API-S-Modification that state the stored preview."""
    return (body["impact_preview"], body["impact_preview_file_id"], body["impact_preview_withheld"])


def _retained_preview(body: Mapping[str, Any]) -> tuple[Any, Any]:
    """The two members of API-S-ManualAdjustment that state the preview the row retains."""
    return (body["impact_preview_file_id"], body["impact_preview_withheld"])


def test_a_stored_preview_is_answered_to_who_reads_every_entity_of_its_group(
    k04: K04World,
) -> None:
    """Item MOD-PREVIEW-READ-SCOPE-1 (04 §16.10 rev 1.300 "Who reads a stored preview"; T-PLT-29
    "Read access"). A combination group {SF-ORD-UK-2004 of AVM-UK, SF-ORD-US-3001 of AVM-US}. The
    preview a modification or a manual adjustment retains is the dry run of the whole group, so
    it is answered to who holds the read permission for every entity of the group. Una, a Revenue
    Accountant of AVM-UK alone, reads the rows — they are her entity's — and each tells her that
    a preview is withheld: no summary, no file id, and the document answers her as a file that
    does not exist, by both of its routes. Maya, who holds the role for every entity, is
    answered all of it. It stays so in the answer of a command of Una's, and once Maya has
    submitted the modification, when the same document is the request's impact preview as well.

    As built (measured on the head of rev 1.295) the read answered Una the group's transaction
    price — 73,000.00 before and 78,000.00 after, for her contract of 68,000.00 — with the
    journal lines, the figures the preview route refuses her, and both file routes answered her
    200 for the modification's document and for the adjustment's."""
    app, place = k04.app, k04.report.place
    maya = k04.report.maya
    british, _, _ = _two_entities(k04, AVM_US)
    una = holding(
        app,
        colleague(k04.report.tenant_id, "una"),
        "revenue_accountant",
        entity_ids=[k04.uk_entity_id],
    )

    # --- a modification: Una's draft, and the preview Maya had computed for it
    modification_id = _classified(app, una, british, "CR-UK-2004-2026-07")
    _previewed(k04, maya, modification_id)
    path = f"{MODIFICATIONS}/{modification_id}"
    whole = get(app, path, maya).json()
    assert whole["impact_preview_withheld"] is False
    assert (
        whole["impact_preview"]["transaction_price_before"],
        whole["impact_preview"]["transaction_price_after"],
    ) == ({"amount": "73000.00", "currency": "GBP"}, {"amount": "78000.00", "currency": "GBP"})
    file_id = whole["impact_preview_file_id"]
    assert file_id is not None
    assert _document(app, maya, file_id) == (200, 200)
    shown = get(app, path, una)
    assert shown.status_code == 200, shown.text
    hers = shown.json()
    assert _stored_preview(hers) == (None, None, True)
    assert _document(app, una, file_id) == (404, 404)
    # not withheld: the row with its lines, the hash of the preview, and — in the read as in
    # the list — the catch-up of the contract's own obligations
    assert (hers["status"], hers["lines"]) == ("DRAFT", whole["lines"])
    assert hers["impact_summary"] == whole["impact_summary"]
    assert whole["impact_summary"] == {"catch_up_total": {"amount": "0.00", "currency": "GBP"}}
    assert hers["impact_preview_sha256"] is not None
    assert hers["impact_preview_sha256"] == whole["impact_preview_sha256"]
    for actor in (una, maya):
        items = get(app, f"{CONTRACTS}/{british}/modifications", actor).json()["items"]
        (item,) = [found for found in items if found["id"] == modification_id]
        assert item["impact_summary"] == {"catch_up_total": {"amount": "0.00", "currency": "GBP"}}
        assert item["impact_preview_sha256"] == whole["impact_preview_sha256"]

    # --- the answer of a command that keeps the preview: Una discards a second draft of hers
    second = _classified(app, una, british, "CR-UK-2004-2026-08")
    _previewed(k04, maya, second)
    discarded = post(app, f"{MODIFICATIONS}/{second}/discard", una, {})
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["status"] == "VOIDED"
    assert _stored_preview(discarded.json()) == (None, None, True)
    kept = get(app, f"{MODIFICATIONS}/{second}", maya).json()
    assert kept["impact_preview"] is not None
    assert kept["impact_preview_file_id"] is not None
    assert kept["impact_preview_withheld"] is False

    # --- once it is submitted the same document is the request's impact preview as well
    submitted = post(app, f"{path}/submit", maya, dict(SUBMISSION))
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["impact_preview_file_id"] == file_id
    assert _stored_preview(get(app, path, una).json()) == (None, None, True)
    assert _document(app, una, file_id) == (404, 404)
    assert _document(app, maya, file_id) == (200, 200)

    # --- a manual adjustment retains its preview at its submission
    adjustment_id = _adjusted(app, place, maya, british)
    row = f"{ADJUSTMENTS}/{adjustment_id}"
    # a draft retains none yet, which is not "withheld"
    assert _retained_preview(get(app, row, una).json()) == (None, False)
    sent = post(app, f"{row}/submit", maya, {"comment": "Review the release."})
    assert sent.status_code == 200, sent.text
    retained = sent.json()["impact_preview_file_id"]
    assert (retained is None, sent.json()["impact_preview_withheld"]) == (False, False)
    read = get(app, row, una)
    assert read.status_code == 200, read.text
    assert read.json()["status"] == "SUBMITTED"
    assert _retained_preview(read.json()) == (None, True)
    assert _document(app, una, retained) == (404, 404)
    assert _document(app, maya, retained) == (200, 200)
    # the list answers each reader as the read does
    for actor, answered in ((una, (None, True)), (maya, (retained, False))):
        items = get(app, f"{ADJUSTMENTS}?entity={AVM_UK}", actor).json()["items"]
        (item,) = [found for found in items if found["id"] == adjustment_id]
        assert _retained_preview(item) == answered


def test_the_contracting_entity_reads_the_stored_preview_of_a_contract_another_entity_performs(
    k04: K04World,
) -> None:
    """The control of the rule (04 §16.10 rev 1.300; supervisor ruling R-87 (1): a contract subject
    belongs to the entity that CONTRACTS). ``SF-ORD-UK-2001`` is contracted by AVM-UK and alone
    in its group; AVM-US performs one of its obligations. Una, of AVM-UK alone, holds the read
    permission for every entity its subjects are bound to: she is answered the preview she had
    computed for her modification, and the document by both of its routes; and the preview her
    manual adjustment retains at her own submission."""
    app, place = k04.app, k04.report.place
    contract_id = k04.contract_id
    una = holding(
        app,
        colleague(k04.report.tenant_id, "una"),
        "revenue_accountant",
        entity_ids=[k04.uk_entity_id],
    )
    modification_id = _classified(app, una, contract_id, "CR-SALTMARSH-2026-07")
    _previewed(k04, una, modification_id)
    shown = get(app, f"{MODIFICATIONS}/{modification_id}", una).json()
    assert shown["impact_preview"] is not None
    assert shown["impact_preview_withheld"] is False
    assert _document(app, una, shown["impact_preview_file_id"]) == (200, 200)
    adjustment_id = _adjusted(app, place, una, contract_id)
    sent = post(app, f"{ADJUSTMENTS}/{adjustment_id}/submit", una, {"comment": "Review."})
    assert sent.status_code == 200, sent.text
    retained = sent.json()["impact_preview_file_id"]
    assert (retained is None, sent.json()["impact_preview_withheld"]) == (False, False)
    assert _retained_preview(get(app, f"{ADJUSTMENTS}/{adjustment_id}", una).json()) == (
        retained,
        False,
    )
    assert _document(app, una, retained) == (200, 200)


# --- who a job answers the summary of a dry run (item PREVIEW-JOB-RESULT-SCOPE-1) -----------------

GROUP_PRICE: Final = MappingProxyType({"amount": "73000.00", "currency": "GBP"})
# roles of the workspace's own, each holding ONE permission: every default role holds
# ``contract.read``, so the member the rule is about holds a role without it
ONE_PERMISSION: Final = MappingProxyType(
    {
        "uploads_only": "import.upload",
        "contracts_only": "contract.read",
        "audit_only": "audit.read",
    }
)


def _accountant_of_uk(k04: K04World, name: str, role: str, *entity_ids: UUID) -> Actor:
    """A Revenue Accountant of AVM-UK who holds ``role`` besides — for ``entity_ids``, or for all
    entities when none is named — signed in after both assignments."""
    found = colleague(k04.report.tenant_id, name)
    assign(found, role, entity_ids=entity_ids)
    return holding(k04.app, found, "revenue_accountant", entity_ids=[k04.uk_entity_id])


def _summary(result: Mapping[str, Any]) -> tuple[Any, Any]:
    """What a job's result says of the summary of its dry run: the figure this group is told
    apart by — its price before the change — and whether the summary is withheld."""
    summary = result["summary"]
    price = None if summary is None else summary["transaction_price_before"]
    return price, result.get("summary_withheld")


def test_a_job_answers_the_summary_of_a_dry_run_to_who_reads_every_entity_of_its_group(
    k04: K04World,
) -> None:
    """Item PREVIEW-JOB-RESULT-SCOPE-1 (04 API-S-Job and §16.10 "Who reads a stored preview", rev
    1.314). A combination group {SF-ORD-UK-2004 of AVM-UK, SF-ORD-US-3001 of AVM-US}. The summary
    in the result of a preview job is the dry run of the whole group, so the job answers it to a
    reader who holds the read permission of the dry run's subject for every entity of the group.

    Bea is a Revenue Accountant of AVM-UK. When she asks the four previews she reads AVM-US
    too — a role of the workspace's own with ``contract.read`` alone — so each route takes her:
    since 04 rev 1.319 a preview is asked by who READS every entity of the group, and the
    member whose second role reads nothing is refused at the command
    (``tests/api/test_read_scope_by_permission.py``; until that revision the union of her
    roles' entities let her ask). Then that role is withdrawn and she holds, for AVM-US, a
    role with ``import.upload`` alone: the jobs are still hers, and ``contract.read`` is hers
    for AVM-UK only. Her own jobs end ``SUCCEEDED`` and answer her everything but the summary —
    ``summary`` null, ``summary_withheld`` true — on the read and in the list. Maya, who reads
    every job and every entity, is answered the summaries of the same jobs. Ava reads every
    job (``audit.read`` for all entities) and one entity: no summary. Cara, whose second role
    holds ``contract.read`` for AVM-US, asks the same four previews and is answered their
    summaries: the permission for every entity decides, through whichever roles. Nothing is
    taken from the stored job.

    As built (measured by lane F-CTR-WEB on 94241243c) ``GET /jobs/{id}`` of the own job of a
    member whose second role held ``import.upload`` alone answered her the group's price,
    73,000.00 before and 78,000.00 after, with the journal lines — for her contract of
    68,000.00, and while the read of the modification withheld the stored preview from her.

    Restated with item READ-SCOPE-BY-PERMISSION-1 (register index 301; STALE TEST WORLD by the
    supervisor's ruling of 2026-10-03): Bea asked her previews with that second role from the
    start, which the kernel's question now refuses. What the test holds is unchanged — the
    summary is answered by the read permission for every entity, asked when the job is READ."""
    app, place = k04.app, k04.report.place
    maya = k04.report.maya
    british, _, _ = _two_entities(k04, AVM_US)
    tenant_id = k04.report.tenant_id
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        for code, permission in ONE_PERMISSION.items():
            insert_custom_role(session, tenant_id=tenant_id, code=code, permissions=[permission])
    bea = _accountant_of_uk(k04, "bea", "contracts_only", k04.us_entity_id)
    cara = _accountant_of_uk(k04, "cara", "contracts_only", k04.us_entity_id)
    ava = _accountant_of_uk(k04, "ava", "audit_only")
    routes = _preview_routes(
        british,
        _classified(app, bea, british, "CR-UK-2004-2026-07"),
        _estimated(app, bea, british, "REBATE-2004"),
        _adjusted(app, place, bea, british),
    )

    hers: dict[str, dict[str, Any]] = {}
    asked: dict[str, PreviewRoute] = {}
    for route in routes:
        taken = _asked(app, bea, british, route)
        assert taken.status_code == 202, (route.path, taken.text)
        job_id = str(taken.json()["id"])
        # the worker runs it; Maya reads every job and holds the read permission for all entities
        whole = run_now(k04.report, UUID(job_id))
        assert whole["state"] == "SUCCEEDED", (route.path, whole.get("problem"))
        assert _summary(whole["result"]) == (GROUP_PRICE, None), route.path
        hers[job_id] = whole["result"]
        asked[job_id] = route
        # while she reads every entity of the group, her job answers her its summary
        assert _summary(get(app, f"{JOBS}/{job_id}", bea).json()["result"]) == (GROUP_PRICE, None)
    # her read of AVM-US is withdrawn: the second role now holds ``import.upload`` alone
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        revoke_role_assignments(
            session,
            tenant_id=tenant_id,
            membership_id=bea.member.membership_id,
            at=place.clock.now(),
        )
    assign(bea.member, "uploads_only", entity_ids=[k04.us_entity_id])
    assign(bea.member, "revenue_accountant", entity_ids=[k04.uk_entity_id])
    for job_id, route in asked.items():
        whole = {"result": hers[job_id]}
        # Bea, who asked: her job, without the summary — and with every other member of it
        read = get(app, f"{JOBS}/{job_id}", bea)
        assert read.status_code == 200, (route.path, read.text)
        answered = read.json()
        assert answered["state"] == "SUCCEEDED", route.path
        assert _summary(answered["result"]) == (None, True), route.path
        assert answered["result"] == {
            **whole["result"],
            "summary": None,
            "summary_withheld": True,
        }, route.path
        # Ava reads every job, and AVM-UK alone
        seen = get(app, f"{JOBS}/{job_id}", ava)
        assert seen.status_code == 200, (route.path, seen.text)
        assert _summary(seen.json()["result"]) == (None, True), route.path
        # Cara reads every entity of the group and not this job: it is neither hers nor an
        # auditor's to read
        assert get(app, f"{JOBS}/{job_id}", cara).status_code == 404, route.path
    assert len(hers) == len(routes) == 4
    # the modification's job keeps its hash beside the withheld summary; the events' its count
    assert sorted(key for result in hers.values() for key in result if key != "summary") == sorted(
        ["href", "counts"] * 4 + ["impact_preview_sha256"]
    )

    # the list answers each reader as the read does
    listed = get(app, f"{JOBS}?kind=CONTRACT_COMPUTE", bea)
    assert listed.status_code == 200, listed.text
    items = {str(item["id"]): item["result"] for item in listed.json()["items"]}
    assert sorted(items) == sorted(hers)  # her jobs, and no other
    assert [_summary(result) for result in items.values()] == [(None, True)] * 4
    everything = get(app, f"{JOBS}?kind=CONTRACT_COMPUTE", maya).json()["items"]
    shown = {str(item["id"]): item["result"] for item in everything if str(item["id"]) in hers}
    assert shown == hers
    # nothing is taken from the job: the stored result holds the summary
    ids = [UUID(value) for value in sorted(hers)]
    stored = place.rows(select(job.c.id, job.c.result).where(job.c.id.in_(ids)))
    assert {str(row["id"]): row["result"]["summary"] for row in stored} == {
        job_id: result["summary"] for job_id, result in hers.items()
    }

    # the control: the read permission for every entity, held through two roles
    for route in routes:
        taken = _asked(app, cara, british, route)
        assert taken.status_code == 202, (route.path, taken.text)
        job_id = str(taken.json()["id"])
        assert run_now(k04.report, UUID(job_id))["state"] == "SUCCEEDED", route.path
        own = get(app, f"{JOBS}/{job_id}", cara)
        assert own.status_code == 200, (route.path, own.text)
        assert _summary(own.json()["result"]) == (GROUP_PRICE, None), route.path
