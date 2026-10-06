"""The WLD-B close world as rows (PRD §2.6 WLD-B-01 to WLD-B-06; J-13.1; BUILD_SPEC CLO-4).

Maya (Revenue Accountant) keeps AVM-US on a January calendar with FY2026-P01 to P09 open
(``support.factories.world_calendar``). ``wld_b`` writes three pending requests, two open
``PROGRESS_OVER_DELIVERY`` items, one open ``journal_export`` hold, one open
``VC_REASSESSMENT_MISSING`` item, and no journal run or reconciliation. The two findings name
AVM-US, or, with ``findings_named=False``, are written as ``validate._raise`` writes them: an
import-level item with no entity, contract or combination group ([J] D-88 L7-2-Q-1).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id, transitions
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    calc_trace,
    close_run,
    combination_group,
    contract,
    contract_computation,
    contract_event,
    contract_hold,
    contract_version,
    customer,
    engine_release,
    exception_item,
    file_object,
    gl_account,
    import_upload,
    job,
    journal_batch,
    journal_entry,
    journal_run,
    judgement_record,
    legal_entity,
    obligation,
    period,
    product,
    reconciliation,
    schedule,
    schedule_line,
    source_invoice,
    source_record,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates
from erev_api.domain.contracts import period_ends
from erev_api.enums import (
    ApprovalRequestStatus,
    ConfigStatus,
    FilePurpose,
    ImportStatus,
    LockKind,
    PeriodState,
)
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from fastapi import FastAPI
from sqlalchemy import bindparam, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from support.factories import Workspace, stamp_test_release, workspace, world_calendar
from support.principals import Actor, colleague, enrolled, member
from support.reference import assign, holding, periods, post
from support.rows import (
    ContractRows,
    JournalParts,
    JournalRows,
    LedgerParts,
    approval_request_values,
    calc_trace_values,
    close_run_steps,
    close_run_values,
    combination_group_values,
    contract_computation_values,
    contract_event_values,
    contract_hold_values,
    contract_values,
    contract_version_values,
    customer_values,
    engine_release_values,
    exception_item_values,
    file_object_values,
    gl_account_values,
    import_upload_values,
    insert_journal_rows,
    judgement_record_values,
    ledger_seal_values,
    legal_entity_values,
    obligation_values,
    product_values,
    reconciliation_values,
    schedule_line_values,
    schedule_values,
    source_invoice_values,
    source_record_values,
    subledger_line_values,
    subledger_posting_values,
)

BOOK = "ASC606"
ENTITY_CODE = "AVM-US"
# T-PLT-31 ``close.require_reconciliations_for_lock`` default: the kinds RECONCILIATIONS_GENERATED
# needs generated and reviewed (BR-CLS-01).
REQUIRED_RECONCILIATIONS = ("BILLING_TO_SUBLEDGER", "SUBLEDGER_TO_GL")


@dataclass(frozen=True, slots=True)
class CloseWorld:
    app: FastAPI
    place: Workspace
    maya: Actor
    entity_id: UUID
    september: Mapping[str, Any]

    @property
    def tenant_id(self) -> UUID:
        return self.place.tenant_id

    @property
    def period_id(self) -> UUID:
        return UUID(str(self.september["period"]["id"]))

    @property
    def state_id(self) -> UUID:
        return UUID(str(self.september["id"]))


def close_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> CloseWorld:
    """Maya and AVM-US with FY2026-P01 to P09 open; ``september`` is the FY2026-P09 API-S-Period.

    The world is a stamped process, as its sibling worlds are (``report_world``, ``k02_world``,
    ``seat_world``): the lock's CTL-016 evidence (``controls.evidence.record_execution``) and a
    journal run's batches stamp ``engine_release_id`` through ``process_release_id``, which fails
    closed with ``release-mismatch`` when this process stamped no release (05 REL-03; D-98 60).
    Without the stamp those scenarios passed only after another test of the same process had left
    its environment remembered (``conftest._forget_stamped_release`` forgets the release alone)."""
    stamp_test_release()
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    _, entity_id = world_calendar(app, maya)
    (september,) = [
        item
        for item in periods(app, maya, entity="AVM-US")
        if item["period"]["period_key"] == "FY2026-P09"
    ]
    return CloseWorld(
        app=app,
        place=workspace(app, clock, keyring, files, maya),
        maya=maya,
        entity_id=entity_id,
        september=september,
    )


@contextmanager
def system_session(world: CloseWorld) -> Iterator[Session]:
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        yield session


def periods_closed_before(
    place: Workspace,
    app: FastAPI,
    actor: Actor,
    *,
    entity_id: UUID,
    before: str,
    entity_code: str = ENTITY_CODE,
    permanently: bool = False,
) -> None:
    """PRD WLD-P-02 for a world that locks the period ``before``: every earlier period of the
    entity in the ASC606 book is ``closed`` (``permanently_locked`` with ``permanently``).
    Supervisor ruling R-6 (PRD BR-CLS-08): a period is submitted for lock, and locked, only when no
    earlier period of its entity and book is postable — a world that locks a period posts into the
    earlier ones first and closes them with this call before it asks for the lock.

    Each period still ``open`` is driven ``open → closing → closed`` through the close domain's own
    writers (CLO6-R3 (5)): the transition writer for the soft close, then ``_persist_lock`` with an
    APPROVED ``PERIOD_LOCK`` request, because T-REF-07 requires both references for ``closed`` and
    ``permanently_locked``. No gate is evaluated and nothing is frozen: this is fixture state for
    the order rules (BR-CLS-08; the SM-07 permanent-lock order, Q-6), never the rule. A period
    already ``closing`` or ``closed`` continues from where it is."""
    states = sorted(
        (
            item
            for item in periods(app, actor, entity=entity_code)
            if item["period"]["period_key"] < before
        ),
        key=lambda item: item["period"]["period_key"],
    )
    steps = [(LockKind.LOCK, PeriodState.CLOSING, PeriodState.CLOSED, close_commands.LOCK_ACTION)]
    if permanently:
        steps.append(
            (
                LockKind.PERMANENT_LOCK,
                PeriodState.CLOSED,
                PeriodState.PERMANENTLY_LOCKED,
                close_commands.PERMANENT_LOCK_ACTION,
            )
        )
    with place.uow() as uow:
        session = uow.session
        for item in states:
            state_id = UUID(str(item["id"]))
            scope = gates.period_scope(session, state_id, lock=True)
            assert scope is not None
            if scope.state == PeriodState.OPEN.value:
                close_commands._record_transition(
                    uow,
                    state_id=state_id,
                    current=close_commands._current(session, scope),
                    from_state=PeriodState.OPEN,
                    to_state=PeriodState.CLOSING,
                    action=close_commands.START_CLOSE_ACTION,
                    reason_code=None,
                    comment="Fixture soft close",
                )
            for kind, from_state, to_state, action in steps:
                scope = gates.period_scope(session, state_id, lock=True)
                assert scope is not None
                if scope.state != from_state.value:
                    continue
                request = approval_request_values(
                    place.tenant_id,
                    status=ApprovalRequestStatus.APPROVED,
                    entity_id=entity_id,
                    subject_type="PERIOD_LOCK",
                    subject_id=state_id,
                    summary="Fixture lock request",
                )
                session.execute(insert(approval_request).values(**request))
                close_commands._persist_lock(
                    uow,
                    scope,
                    kind=kind,
                    lock_id=new_id(),
                    transition_id=new_id(),
                    from_state=from_state,
                    to_state=to_state,
                    action=action,
                    approval_request_id=UUID(str(request["id"])),
                    comment="Fixture lock",
                    certification=[],
                    snapshot_manifest_sha256=None,
                    heads=close_commands._heads(session, scope),
                    # 04 T-CLS-04 rev 1.113 (R-40 (c)): a LOCK names the cutoff it freezes at
                    cutoff_known_at=uow.now if kind is LockKind.LOCK else None,
                )
        uow.commit()


def earlier_periods_closed(
    world: CloseWorld, *, before: str = "FY2026-P09", permanently: bool = False
) -> None:
    """``periods_closed_before`` for the close world: FY2026-P01 up to the period before
    ``before`` of AVM-US (default: January to August 2026, PRD WLD-P-02)."""
    periods_closed_before(
        world.place,
        world.app,
        world.maya,
        entity_id=world.entity_id,
        before=before,
        permanently=permanently,
    )


def contract_of(
    session: Session,
    world: CloseWorld,
    entity_id: UUID | None = None,
    *,
    event_effective_date: date | None = None,
    **contract_columns: Any,
) -> tuple[UUID, UUID, UUID]:
    """A contract of the entity (default AVM-US) at head 1 with its first event in its own
    combination group; (contract id, event id, group id)."""
    tenant_id = world.tenant_id
    entity = world.entity_id if entity_id is None else entity_id
    buyer = customer_values(tenant_id)
    session.execute(insert(customer).values(**buyer))
    group = combination_group_values(tenant_id)
    session.execute(insert(combination_group).values(**group))
    row = contract_values(
        tenant_id,
        customer_id=buyer["id"],
        contracting_entity_id=entity,
        combination_group_id=group["id"],
        head_stream_version=1,
        **contract_columns,
    )
    session.execute(insert(contract).values(**row))
    # T-CON-05 is append-only (IM-A): the first event's effective date is set at creation, never
    # updated afterwards (batch #4 on main c9110467: permission denied for table contract_event).
    event = contract_event_values(
        tenant_id,
        contract_id=row["id"],
        contracting_entity_id=entity,
        stream_version=1,
        **({} if event_effective_date is None else {"effective_date": event_effective_date}),
    )
    session.execute(insert(contract_event).values(**event))
    return UUID(str(row["id"])), UUID(str(event["id"])), UUID(str(group["id"]))


def other_entity(session: Session, world: CloseWorld, code: str = "AVM-UK") -> UUID:
    """A second entity of the tenant on AVM-US's calendar (no period states)."""
    calendar_id = session.execute(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
    ).scalar_one()
    row = legal_entity_values(
        world.tenant_id, calendar_id=calendar_id, code=code, time_zone="Europe/London"
    )
    session.execute(insert(legal_entity).values(**row))
    return UUID(str(row["id"]))


def submitted_judgement(session: Session, world: CloseWorld, contract_id: UUID) -> UUID:
    """WLD-B-03: a ``PRINCIPAL_AGENT`` judgement record on a contract of the entity, SUBMITTED."""
    row = judgement_record_values(
        world.tenant_id,
        topic="PRINCIPAL_AGENT",
        subject_type="contract",
        subject_id=contract_id,
        contract_id=contract_id,
        book_code=BOOK,
    )
    session.execute(insert(judgement_record).values(**row))
    session.execute(
        update(judgement_record)
        .where(judgement_record.c.id == row["id"])
        .values(status="SUBMITTED", content_sha256="a" * 64, updated_by_kind="SYSTEM")
    )
    return UUID(str(row["id"]))


def _findings_scope(session: Session, world: CloseWorld, *, named: bool) -> dict[str, Any]:
    """The WLD-B-04 finding columns: the entity, or the upload of an import-level item."""
    if named:
        return {"entity_id": world.entity_id}
    stored = file_object_values(world.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
    session.execute(insert(file_object).values(**stored))
    # INTERFACES_COMPLETE counts FAILED uploads with an open CONTROL_TOTALS_MISMATCH item
    # (``gates.interface_failures``); the import-level WLD-B-04 items hang off such an upload.
    upload = import_upload_values(
        world.tenant_id, file_object_id=stored["id"], status=ImportStatus.FAILED.value
    )
    session.execute(insert(import_upload).values(**upload))
    return {"import_upload_id": upload["id"]}


def wld_b(world: CloseWorld, *, findings_named: bool = True) -> dict[str, UUID]:
    """WLD-B-01 to WLD-B-06 as rows (module docstring)."""
    tenant_id = world.tenant_id
    maya_id = world.maya.member.user_id
    with system_session(world) as session:
        activation, _, _ = contract_of(session, world)
        adjusted, _, _ = contract_of(session, world)
        disputed, dispute_event, _ = contract_of(session, world)
        judged, _, _ = contract_of(session, world)
        vc_contract, _, _ = contract_of(session, world)
        judgement_id = submitted_judgement(session, world, judged)
        requests = (
            approval_request_values(
                tenant_id,
                subject_type="CONTRACT_ACTIVATION",
                subject_id=activation,
                preparer_id=maya_id,
                amount_functional=Decimal("146000.00"),
                amount_currency="USD",
                summary="Activate BG-AVM-0020",
            ),
            approval_request_values(
                tenant_id,
                subject_type="MANUAL_ADJUSTMENT",
                subject_id=adjusted,
                entity_id=world.entity_id,
                preparer_id=maya_id,
                amount_functional=Decimal("2400.00"),
                amount_currency="USD",
                summary="Schedule override on BG-AVM-0022",
            ),
            approval_request_values(
                tenant_id,
                subject_type="JUDGEMENT_RECORD",
                subject_id=judgement_id,
                preparer_id=maya_id,
                summary="Review principal and agent judgement",
            ),
        )
        for request in requests:
            session.execute(insert(approval_request).values(**request))
        findings = _findings_scope(session, world, named=findings_named)
        for _ in range(2):
            session.execute(
                insert(exception_item).values(
                    **exception_item_values(
                        tenant_id,
                        source="IMPORT",
                        code=(
                            "PROGRESS_OVER_DELIVERY"
                            if findings_named
                            else "CONTROL_TOTALS_MISMATCH"  # gates.CONTROL_TOTALS_MISMATCH
                        ),
                        title=(
                            "Delivery exceeds the contracted quantity"
                            if findings_named
                            else "Control totals differ from the file header"
                        ),
                        **findings,
                    )
                )
            )
        session.execute(
            insert(contract_hold).values(
                **contract_hold_values(
                    tenant_id,
                    contract_id=disputed,
                    applied_event_id=dispute_event,
                    hold_type="journal_export",
                    reason="Customer dispute on invoice INV-US-3988",
                )
            )
        )
        session.execute(
            insert(exception_item).values(
                **exception_item_values(
                    tenant_id,
                    source="CLOSE",
                    code="VC_REASSESSMENT_MISSING",
                    title="VC element without a period-end estimate",
                    entity_id=world.entity_id,
                    period_id=world.period_id,
                    contract_id=vc_contract,
                )
            )
        )
    return {
        "judgement": judgement_id,
        "judged_contract": judged,
        "manual_adjustment_request": UUID(str(requests[1]["id"])),
    }


def actor_with_role(
    app: FastAPI, clock: FrozenClock, tenant_id: UUID, role_code: str, *, name: str
) -> Actor:
    """An enrolled member of the world's tenant holding ``role_code`` with a fresh TOTP (BR-PLT-06):
    a Controller, Revenue Reviewer or any other persona a decision needs. ``member`` would provision
    another tenant; ``colleague`` joins this one (F-CLO record §20.1 (10))."""
    someone = colleague(tenant_id, name)
    assign(someone, role_code)
    # The confirmed enrolment already rotates the session as verified (``mfa.confirm`` →
    # ``sessions.reissue(mfa_verified_at=now)``); a second verification at the same frozen TOTP
    # step would replay the spent code and is refused by design (``totp.matching_step``,
    # ``last_used_step``) — the ci stage of the batch on main 0cb36c14 showed exactly that 422.
    return enrolled(app, clock, someone)


RECONCILIATION_PATHS: Mapping[str, tuple[str, ...]] = {
    "DRAFT": (),
    "PREPARED": ("PREPARED",),
    "REVIEWED": ("PREPARED", "REVIEWED"),
    "AUTO_CERTIFIED": ("AUTO_CERTIFIED",),
}


def acknowledged_run_for(
    session: Session, *, tenant_id: UUID, entity_id: UUID, period_id: UUID, now: datetime
) -> JournalRows:
    """An acknowledged, balanced USD journal run of an entity's period, so JE_BALANCED,
    BATCHES_ACKNOWLEDGED and the derived JOURNAL_RUN_NOT_CALCULATED clear. The probe rows of
    ``support.rows`` are built on the entity's own calendar and period — passing ``entity_id`` to
    ``insert_journal_parts`` would insert a second entity row and fall back to a fresh id when that
    insert is refused — and the run and batch move along E-34 through the allowed pairs with their
    set-once instants (DB-03): draft → approved → exported → acknowledged. The run's one entry
    takes the entity's next JE sequence: JE numbers are one series per entity across periods and
    books (04 T-SL-08 ``ux_journal_entry__no``, ``ux_journal_entry__seq``), so a second fixture run
    of the entity — another period of the same world — never repeats the first run's number."""
    calendar_id = session.execute(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == entity_id)
    ).scalar_one()
    account = gl_account_values(tenant_id)
    session.execute(insert(gl_account).values(**account))
    release = engine_release_values()
    session.execute(insert(engine_release).values(**release))
    parts = JournalParts(
        calendar_id=UUID(str(calendar_id)),
        entity_id=entity_id,
        period_id=period_id,
        account_id=UUID(str(account["id"])),
        release_id=UUID(str(release["id"])),
    )
    last_seq = session.execute(
        select(func.max(journal_entry.c.je_seq)).where(journal_entry.c.entity_id == entity_id)
    ).scalar_one()
    rows = insert_journal_rows(session, tenant_id, parts=parts, je_seqs=(int(last_seq or 0) + 1,))
    acknowledge_run(session, UUID(str(rows.run["id"])), now=now)
    return rows


def acknowledge_run(session: Session, run_id: UUID, *, now: datetime) -> None:
    """Move a draft run and every batch of it along E-34 through the allowed pairs with their
    set-once instants (DB-03): draft → approved → exported → acknowledged — the fixture state
    BATCHES_ACKNOWLEDGED reads. The run is a fixture run of ``acknowledged_run_for`` or a run the
    product calculated (``POST /journal-runs`` and its job), whose lines are then the period's real
    journalisation (``JE_COMPLETE`` over sealed activity)."""
    run_steps: tuple[tuple[str, dict[str, Any]], ...] = (
        ("approved", {"approved_at": now}),
        ("exported", {"exported_at": now}),
        ("acknowledged", {"acknowledged_at": now}),
    )
    batch_steps: tuple[tuple[str, dict[str, Any]], ...] = (
        ("approved", {}),
        ("exported", {"exported_at": now, "attempt_count": 1}),
        ("acknowledged", {"acknowledged_at": now}),
    )
    for state, stamps in run_steps:
        session.execute(
            update(journal_run).where(journal_run.c.id == run_id).values(state=state, **stamps)
        )
    for state, stamps in batch_steps:
        session.execute(
            update(journal_batch)
            .where(journal_batch.c.journal_run_id == run_id)
            .values(state=state, **stamps)
        )


RUN_AUDIT_ACTION = "journal_run.calculate"  # summarise.CALCULATE_ACTION (pinned by the unit rules)
RUN_AUDIT_OBJECT_TYPE = "journal_run"  # summarise.OBJECT_TYPE


def run_audit_after(rows: JournalRows) -> dict[str, Any]:
    """The ``journal_run.calculate`` audit ``after`` a real run writes (``summarise.calculate``),
    for a fixture run: the explicit zero-held state (``held_subledger_line_ids`` []) that
    ``completeness.run_exclusions`` reads — without it a run is unverifiable by design and
    ``JE_COMPLETE`` names it (batch #7 on main 104a954c; F-CLO record §25.22) — and the explicit
    state of no line taken over (``taken_over_subledger_line_ids`` [], no detail file; item
    JRN-HELD-AFTER-EXPORT-1, ENGINE_SPEC_B S14-R-17 rev 1.164)."""
    run = rows.run
    return {
        "run_no": str(run["run_no"]),
        "entity_id": str(run["entity_id"]),
        "book_code": str(run["book_code"]),
        "period_id": str(run["period_id"]),
        "mode": str(run["mode"]),
        "grain": str(run["grain"]),
        "coverage": [
            int(run["from_chain_seq"]),
            int(run["to_chain_seq"]),
            None if run.get("delta_from_chain_seq") is None else int(run["delta_from_chain_seq"]),
            None if run.get("delta_to_chain_seq") is None else int(run["delta_to_chain_seq"]),
        ],
        "total_debit_functional": format(Decimal(str(run["total_debit_functional"])), "f"),
        "total_credit_functional": format(Decimal(str(run["total_credit_functional"])), "f"),
        "counts": {
            "batches": 1,
            "entries": len(rows.entries),
            "lines": len(rows.lines),
            "detail_lines": len(rows.lines),
            "held_lines": 0,
        },
        "held_detail_file_id": None,
        "held_detail_sha256": None,
        "held_subledger_line_ids": [],
        "taken_over_subledger_line_ids": [],
        "taken_over_detail_file_id": None,
        "taken_over_detail_sha256": None,
    }


def record_run_calculation(world: Any, rows: JournalRows) -> None:
    """Write the producer's CALCULATE audit event for a fixture run through the world's unit of
    work (``world.place.uow()``), as ``summarise.calculate`` does in the same transaction."""
    with world.place.uow() as uow:
        uow.audit(
            action=RUN_AUDIT_ACTION,
            object_type=RUN_AUDIT_OBJECT_TYPE,
            object_id=UUID(str(rows.run["id"])),
            object_version="1",
            after=run_audit_after(rows),
        )
        uow.commit()


def acknowledged_run(
    session: Session, world: CloseWorld, period_id: UUID | None = None
) -> JournalRows:
    """``acknowledged_run_for`` on the world's entity and period (default September), with the
    producer's CALCULATE audit fact written through the world's unit of work (§25.22)."""
    rows = acknowledged_run_for(
        session,
        tenant_id=world.tenant_id,
        entity_id=world.entity_id,
        period_id=world.period_id if period_id is None else period_id,
        now=world.place.clock.now(),
    )
    record_run_calculation(world, rows)
    return rows


def reviewed_reconciliations_for(
    session: Session,
    *,
    tenant_id: UUID,
    entity_id: UUID,
    period_id: UUID,
    now: datetime,
    kinds: tuple[str, ...] = REQUIRED_RECONCILIATIONS,
    status: str = "REVIEWED",
) -> list[UUID]:
    """The required reconciliations of an entity's period in ``status``, each inserted DRAFT (the
    builder's state) and moved there along the admitted SM-09 pairs through ``transitions.apply``
    (DRAFT → PREPARED → REVIEWED; DRAFT → AUTO_CERTIFIED; Codex CLO6-R3 residual (2)); their ids.
    RECONCILIATIONS_GENERATED passes for REVIEWED or AUTO_CERTIFIED.

    Each row is generated now, as the product generates one: ``as_of_known_at`` is the later of
    ``now`` and the server clock (``freeze.freeze_cutoff``), so it is not earlier than any
    subledger line or source invoice the world already holds — a reviewed reconciliation that the
    period has overtaken does not satisfy the gate (supervisor ruling R-58 (e))."""
    steps = RECONCILIATION_PATHS[status]
    stamps = {"updated_at": now, "updated_by": None, "updated_by_kind": "SYSTEM"}
    as_of = max(now, session.execute(select(func.clock_timestamp())).scalar_one())
    ids: list[UUID] = []
    for kind in kinds:
        row = reconciliation_values(
            tenant_id, entity_id=entity_id, period_id=period_id, kind=kind, as_of_known_at=as_of
        )
        session.execute(insert(reconciliation).values(**row))
        current = "DRAFT"
        for step in steps:
            transitions.apply(
                session,
                "reconciliation",
                UUID(str(row["id"])),
                to_status=step,
                expected_status=current,
                set_values=dict(stamps),
            )
            current = step
        ids.append(UUID(str(row["id"])))
    return ids


def reviewed_reconciliations(
    session: Session,
    world: CloseWorld,
    period_id: UUID | None = None,
    *,
    kinds: tuple[str, ...] = REQUIRED_RECONCILIATIONS,
    status: str = "REVIEWED",
) -> list[UUID]:
    """``reviewed_reconciliations_for`` on the world's entity and period (default September)."""
    return reviewed_reconciliations_for(
        session,
        tenant_id=world.tenant_id,
        entity_id=world.entity_id,
        period_id=world.period_id if period_id is None else period_id,
        now=world.place.clock.now(),
        kinds=kinds,
        status=status,
    )


def close_run_succeeded_for(
    session: Session,
    *,
    tenant_id: UUID,
    entity_id: UUID,
    period_id: UUID,
    now: datetime,
    book_code: str = BOOK,
) -> UUID:
    """A ``SUCCEEDED`` close run of an entity's period: fixture state for the lock's gate
    ``CLOSE_RUN_COMPLETED`` (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and R-116 (e); 04
    §16.8 "The close-run gate"), never the rule. It is the row a finished run leaves — its thirteen
    executed steps ``SUCCEEDED``, ``LOCK`` ``PENDING``, created at ``now`` so that it is the
    period's latest run — and, of what a run does, only the marks its first period-end step
    leaves: every computed contract group of the world is marked as posted through the period
    (item CLO-GATE-RUN-2; 04 §16.8 rev 1.228: the gate counts a group of the entity that holds no
    mark, so a world with computed contracts could not pass it on the row alone). No computation
    and no posting: a world that computes period-end amounts (an FX remeasurement, a loss
    provision, a reclass) and locks through the product runs the run
    (``support.close_runs.closed``).

    Write it last, right before the lock is requested: a ``SUCCEEDED`` run of a period that is
    still postable opens a window in which every later computation of the entity's groups runs the
    period-end passes dry and marks what it finds unposted (04 T-CON-03 "Period-end mark")."""
    row = close_run_values(
        tenant_id,
        entity_id=entity_id,
        period_id=period_id,
        book_code=book_code,
        status="SUCCEEDED",
        steps=close_run_steps("SUCCEEDED", lock_status="PENDING"),
        cutoff_known_at=now,
        started_at=now,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )
    session.execute(insert(close_run).values(**row))
    entity_code = session.execute(
        select(legal_entity.c.code).where(legal_entity.c.id == entity_id)
    ).scalar_one()
    last_day = session.execute(
        select(period.c.end_date).where(period.c.id == period_id)
    ).scalar_one()
    key = period_ends.scope_key(str(entity_code), book_code)
    entry = {key: (last_day + timedelta(days=1)).isoformat()}
    session.execute(
        update(combination_group)
        .where(combination_group.c.head_computation_id.is_not(None))
        .values(
            period_ends_open=combination_group.c.period_ends_open.op("||")(
                bindparam("entry", entry, type_=JSONB)
            )
        )
    )
    return UUID(str(row["id"]))


def close_run_succeeded(session: Session, world: CloseWorld, period_id: UUID | None = None) -> UUID:
    """``close_run_succeeded_for`` on the world's entity and period (default September)."""
    return close_run_succeeded_for(
        session,
        tenant_id=world.tenant_id,
        entity_id=world.entity_id,
        period_id=world.period_id if period_id is None else period_id,
        now=world.place.clock.now(),
    )


def identity_duplicates(session: Session, world: CloseWorld, *, issue_date: date) -> None:
    """Two source invoices with distinct external ids and one identity tuple (customer, number,
    amount, date): the admitted duplicate of ruling Q-8 rule 2 and a BLOCKING
    ``DQ_DUPLICATE_INVOICE`` finding once the monitors run. The source unique key
    ``ux_source_invoice__external`` (tenant, system, external id, version) admits them. Moved here
    from ``tests/domain/close/test_monitors.py`` so the gates tests can seed a reachable blocking
    data-quality condition (T-CON-09 keeps every balance column non-negative)."""
    record = source_record_values(world.tenant_id)
    session.execute(insert(source_record).values(**record))
    for external_id in ("INV-US-1001", "INV-US-1001-R"):
        row = source_invoice_values(
            world.tenant_id,
            source_record_id=record["id"],
            external_invoice_id=external_id,
            external_version="1",
            invoice_number="A-1001",
            customer_external_id="CUST-7",
            total_amount=Decimal("1200.00"),
            issue_date=issue_date,
            legal_entity_code=ENTITY_CODE,
        )
        session.execute(insert(source_invoice).values(**row))


SUBJECT_OF_TABLE = {
    "rule_set_version": "RULE_SET_VERSION",
    "pob_template_version": "POB_TEMPLATE_VERSION",
    "fx_rate_set_version": "FX_RATE_SET_VERSION",
}


def published_version(
    session: Session,
    world: CloseWorld,
    table: Any,
    row: Mapping[str, Any],
    *,
    children: Sequence[tuple[Any, Mapping[str, Any]]] = (),
    final: ConfigStatus = ConfigStatus.PUBLISHED,
) -> dict[str, Any]:
    """A configuration version PUBLISHED the way the platform publishes one (DB-04 / E-12 pairs of
    ``erev.tg_config_version``): inserted DRAFT, then ``DRAFT → TESTED`` with its content hash, the
    ``children`` rows (for example T-REF-26 ``rule`` rows) inserted while the parent is still
    editable — ``tg_<child>__config_child`` admits child writes only while the parent is DRAFT or
    TESTED (Codex production-20260921-0304) — then ``TESTED → SUBMITTED``, ``SUBMITTED → APPROVED``
    naming an APPROVED approval request of the version, ``APPROVED → PUBLISHED``. Never the
    ``provisioning`` scope, which is the platform's own seed path. Returns the row as stored."""
    tenant_id = world.tenant_id
    content = str(row.get("content_sha256") or ("c" * 64))
    draft = {**row, "status": ConfigStatus.DRAFT.value, "content_sha256": None}
    session.execute(insert(table).values(**draft))
    where = table.c.id == row["id"]
    session.execute(
        update(table).where(where).values(status=ConfigStatus.TESTED.value, content_sha256=content)
    )
    for child_table, child in children:
        session.execute(insert(child_table).values(**child))
    session.execute(update(table).where(where).values(status=ConfigStatus.SUBMITTED.value))
    request = approval_request_values(
        tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        subject_type=SUBJECT_OF_TABLE[table.name],
        subject_id=row["id"],
        summary=f"Publish {table.name} {row['id']}",
    )
    session.execute(insert(approval_request).values(**request))
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.APPROVED.value, approval_request_id=request["id"])
    )
    if final is ConfigStatus.APPROVED:
        # FX rate set versions are never PUBLISHED: the highest APPROVED version wins (0030).
        return {
            **draft,
            "status": final.value,
            "content_sha256": content,
            "approval_request_id": request["id"],
        }
    assert final is ConfigStatus.PUBLISHED, final
    now = world.place.clock.now()
    session.execute(
        update(table).where(where).values(status=ConfigStatus.PUBLISHED.value, published_at=now)
    )
    return {
        **draft,
        "status": ConfigStatus.PUBLISHED.value,
        "content_sha256": content,
        "approval_request_id": request["id"],
        "published_at": now,
    }


@dataclass(frozen=True, slots=True)
class SealedActivity:
    """A contract chain of the world's entity with one sealed ENGINE_COMPUTE posting: the ids the
    CLO-10 journal tests read back (record §25.18)."""

    contract_id: UUID
    obligation_id: UUID
    group_id: UUID
    computation_id: UUID
    posting_id: UUID
    line_ids: tuple[UUID, ...]
    account_id: UUID
    schedule_line_id: UUID | None
    target_line_ids: tuple[UUID, ...] = ()
    offset_line_ids: tuple[UUID, ...] = ()


def sealed_activity(
    session: Session,
    world: CloseWorld,
    *,
    account: Mapping[str, Any],
    period_id: UUID,
    period_end_date: date,
    amounts: Sequence[Decimal],
    external_id: str = "Contract 2",
    obligation_key: str = "POB #1",
    with_schedule_line: bool = False,
    schedule_amount: Decimal | None = None,
    line_overrides: Sequence[Mapping[str, Any]] = (),
    book_code: str = BOOK,
    offset_account: Mapping[str, Any] | None = None,
    offset_columns: Mapping[str, Any] | None = None,
    **line_columns: Any,
) -> SealedActivity:
    """Genuine sealed activity of the world's entity in ``period_id``: a contract (``external_id``)
    with one obligation (``obligation_key``), a computation, version 1, an optional REVENUE
    schedule line of the period, and one sealed posting whose lines carry ``amounts`` (functional
    = txn, USD unless ``line_columns`` say otherwise) to ``account``. The seal makes the lines what
    a journal run reads (``summarise.detail_statement``) and what ``completeness`` assesses.
    ``line_overrides[i]`` are columns of line ``i`` alone (an account of its own, a role, no
    schedule line); ``schedule_amount`` is the schedule line's amount (default: the credits'
    total, ``-sum(amounts)``); ``book_code`` places the posting in another book (LEGACY for a
    ``DELTA`` run's addition — its own chain head). ``offset_account`` adds, for every supplied
    amount, a genuine balancing counterpart line of the opposite amount to that account inside the
    same posting (0040's seal requires at least two lines balanced in transaction and functional
    currency — Codex production-20260921-1317 CLO-FIXTURE-SEAL-1); ``offset_columns`` are the
    counterparts' own columns (role, rate facts; they carry no schedule line). ``line_ids`` lists
    targets then offsets; ``target_line_ids`` / ``offset_line_ids`` split them."""
    tenant_id = world.tenant_id
    contract_id, event_id, group_id = contract_of(
        session, world, status="ACTIVE", external_id=external_id
    )
    release = engine_release_values()
    session.execute(insert(engine_release).values(**release))
    computation = contract_computation_values(
        tenant_id, combination_group_id=group_id, engine_release_id=release["id"]
    )
    session.execute(insert(contract_computation).values(**computation))
    trace = calc_trace_values(
        tenant_id, contract_version_id=UUID(int=0), combination_group_id=group_id
    )
    version = contract_version_values(
        tenant_id,
        combination_group_id=group_id,
        contract_computation_id=computation["id"],
        calc_trace_id=trace["id"],
    )
    trace["contract_version_id"] = version["id"]
    session.execute(insert(calc_trace).values(**trace))
    session.execute(insert(contract_version).values(**version))
    item_product = product_values(tenant_id)
    session.execute(insert(product).values(**item_product))
    pob = obligation_values(
        tenant_id,
        contract_id=contract_id,
        product_id=item_product["id"],
        created_by_event_id=event_id,  # required since 808caf73 (batch #7 on main 104a954c)
        obligation_key=obligation_key,
    )
    session.execute(insert(obligation).values(**pob))
    schedule_line_id: UUID | None = None
    if with_schedule_line:
        plan = schedule_values(
            tenant_id, contract_version_id=version["id"], combination_group_id=group_id
        )
        session.execute(insert(schedule).values(**plan))
        line = schedule_line_values(
            tenant_id,
            schedule_id=plan["id"],
            contract_version_id=version["id"],
            contract_id=contract_id,
            entity_id=world.entity_id,
            period_id=period_id,
            period_end_date=period_end_date,
            amount=-sum(amounts, Decimal(0)) if schedule_amount is None else schedule_amount,
            cumulative_amount=(
                -sum(amounts, Decimal(0)) if schedule_amount is None else schedule_amount
            ),
        )
        session.execute(insert(schedule_line).values(**line))
        schedule_line_id = UUID(str(line["id"]))
    chain = ContractRows(
        entity_id=world.entity_id,
        customer_id=UUID(int=0),
        group_id=group_id,
        contract_id=contract_id,
    )
    parts = LedgerParts(
        chain=chain,
        computation_id=UUID(str(computation["id"])),
        period_id=period_id,
        period_end_date=period_end_date,
        account_id=UUID(str(account["id"])),
    )
    posting = subledger_posting_values(tenant_id, parts=parts, book_code=book_code)
    session.execute(insert(subledger_posting).values(**posting))
    assert len(line_overrides) <= len(amounts), "one override per line at most"

    def columns(index: int) -> dict[str, Any]:
        merged: dict[str, Any] = {
            "obligation_id": pob["id"],
            "schedule_line_id": schedule_line_id,
            **line_columns,
            **(line_overrides[index] if index < len(line_overrides) else {}),
        }
        # ck_subledger_line__schedule_line (0040): the schedule line id and its period end date are
        # both set or both null (Codex production-20260921-1054 R3).
        if merged.get("schedule_line_id") is None:
            merged["schedule_line_id"] = None
            merged["schedule_period_end_date"] = None
        else:
            merged.setdefault("schedule_period_end_date", period_end_date)
        return merged

    targets = [
        subledger_line_values(
            tenant_id, posting=posting, parts=parts, amount=amount, **columns(index)
        )
        for index, amount in enumerate(amounts)
    ]
    offsets: list[dict[str, Any]] = []
    if offset_account is not None:
        for amount in amounts:
            counterpart: dict[str, Any] = {
                **line_columns,
                "obligation_id": pob["id"],
                "gl_account_id": offset_account["id"],
                "schedule_line_id": None,
                "schedule_period_end_date": None,
                **(offset_columns or {}),
            }
            counterpart.pop("dimensions", None) if "dimensions" not in (
                offset_columns or {}
            ) else None
            offsets.append(
                subledger_line_values(
                    tenant_id, posting=posting, parts=parts, amount=-amount, **counterpart
                )
            )
    lines = [*targets, *offsets]
    session.execute(insert(subledger_line), lines)
    seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
    session.execute(insert(subledger_posting_seal).values(**seal))
    return SealedActivity(
        contract_id=contract_id,
        obligation_id=UUID(str(pob["id"])),
        group_id=group_id,
        computation_id=UUID(str(computation["id"])),
        posting_id=UUID(str(posting["id"])),
        line_ids=tuple(UUID(str(line["id"])) for line in lines),
        account_id=UUID(str(account["id"])),
        schedule_line_id=schedule_line_id,
        target_line_ids=tuple(UUID(str(line["id"])) for line in targets),
        offset_line_ids=tuple(UUID(str(line["id"])) for line in offsets),
    )


JOURNAL_RUNS = "/api/v1/journal-runs"
JOURNAL_RUN_ID_HEADER = "X-Erev-Journal-Run-Id"
_TASK_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def requested_journal_run(
    world: CloseWorld, *, period_key: str = "FY2026-P09", **body: Any
) -> tuple[UUID, UUID]:
    """``POST /journal-runs`` as Maya for AVM-US and ``period_key`` (``body``: further
    API-S-JournalRunCreate members, e.g. ``mode="DELTA"``): (job id, run id)."""
    started = post(
        world.app,
        JOURNAL_RUNS,
        world.maya,
        {"entity_code": "AVM-US", "period_key": period_key, **body},
    )
    assert started.status_code == 202, started.text
    return UUID(str(started.json()["id"])), UUID(str(started.headers[JOURNAL_RUN_ID_HEADER]))


def run_journal_job(world: CloseWorld, job_id: UUID, *, attempts: int = 3) -> Mapping[str, Any]:
    """The worker fetches the job's task and runs it, attempt by attempt, until the job settles
    (SUCCEEDED or FAILED — a refused generation ends FAILED after its retry policy's last attempt)
    or ``attempts`` are spent; returns the job row (``state``, ``problem``, ``result``)."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    runtime = JobRuntime(
        clock=world.place.clock, keyring=world.place.keyring, files=world.place.files
    )

    def row() -> dict[str, Any]:
        with tenant_session(context) as session:
            return dict(
                session.execute(
                    select(job.c.state, job.c.problem, job.c.result).where(job.c.id == job_id)
                )
                .mappings()
                .one()
            )

    for attempt in range(1, attempts + 1):
        with tenant_session(context) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(_TASK_FETCHED, {"id": task_id})
        run_job(job_id, world.tenant_id, attempt=attempt, runtime=runtime)
        current = row()
        if str(current["state"]) in ("SUCCEEDED", "FAILED"):
            return current
    return row()
