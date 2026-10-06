"""A posted amount is read back under the subject it was posted under (item ENG-COST-READBACK-1;
supervisor ruling R-11 as amended on 2026-10-02; 04 T-SL-04 ``subject_key`` rev 1.282; 05 RCP-05
rev 1.202; ENGINE_SPEC_B S14-R-04 rev 1.165, S14-INV-02; dev-guide DG-CMD-10).

A ledger line stores the subject of the entry it belongs to, as the engine keys it, and the
read-back of posted amounts (``bundles._posted``) answers that key. Until revision 0124 the ledger
stored none and the read-back spelled every line without an obligation ``<contract>@<entity>``
(decision L3-1-Q-32), so each computation after the first took the lines of a cost asset
``<contract>/<event>``, of a refund-liability component ``<group>@<entity>/<kind>/<source>`` and
of a contract-level loss unit ``<contract>`` back under that spelling and posted them again under
their own subject: a pair of entries that nets to nil at every computation whose input moved, and,
behind a lock, lines of an earlier period without a source event, over which the next close run
stopped at its dataset freeze (ENGINE_SPEC_B S15-R-18b). Measured on main 51f9bbbe: the cost world
below went from 6 to 14 ledger lines at the second computation.

Each world is built through the product. The families:

- the cost asset (JET-09a, JET-09b): two computations without a fact, then a second asset;
- ``<contract>@<entity>`` (JET-01b, a receipt while the contract is not a contract): the family
  whose stored key is the spelling the read-back gave before;
- a line WITHOUT a key — a line a test builder writes through the door without the caller's
  requirement — is read back in the spelling of L3-1-Q-32, as before;
- behind a lock: a computation without a new fact posts nothing, and the next period's close run
  reaches its end;
- the refund-liability component (JET-04b, the rebate of K-06): two computations without a fact,
  then the estimate that takes it back; and its regrouping at a combination by the approved
  command, which posts only differences (S14-R-04).

The FX remeasurement (``test_fx_remeasurement_recompute.py``, with the line without a key), the
loss unit (``tests/domain/close/test_close_run_steps.py``), the manual adjustment
(``tests/domain/journals/test_adjustments.py``) and the door (``tests/domain/journals/
test_subledger.py``) are witnessed in their own modules; ``tests/unit/test_posted_subject.py``
holds the read-back's rule and ``tests/engine/s14_posting/test_s14_posted_subjects.py`` every
family over the engine alone.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    combination_group,
    contract,
    legal_entity,
    period,
    period_lock,
    period_state,
    period_state_transition,
    subledger_line,
    subledger_line_event,
    subledger_posting_seal,
)
from erev_api.domain.contracts import bundles, computation
from erev_api.enums import ApprovalRequestStatus, ComputationTrigger, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, func, insert, select, update
from support import close_runs as runs
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.factories import (
    STEP1_CHART,
    SeatWorld,
    Workspace,
    activated_contract,
    booked_contract,
    computed,
    k09_body,
    seat_body,
    seat_line,
    seat_world,
)
from support.ledger_door import keyless
from support.reference import approve, assign, post
from support.rows import (
    CloseParts,
    approval_request_values,
    period_lock_values,
    period_state_transition_values,
)
from support.worlds import approved_manual_events
from test_estimates import (
    ESTIMATES,
    REBATE,
    K06World,
    _k06_with_v1,
    _rebate_version,
    _submitted,
    _v2_body,
    k06_body,
    k06_world,
)
from test_step1 import _gated, _record_events

AVM_US = "AVM-US"
AVM_DE = "AVM-DE"
GROUPS = "/api/v1/combination-groups"
BOOK = "ASC606"
K09 = "SF-ORD-10417"
K06 = "NS-SO-DE-5002"
TWIN = "NS-SO-DE-5003"
REFUND = "REFUND_LIABILITY"
AUGUST, SEPTEMBER = "FY2026-P08", "FY2026-P09"
AUGUST_ORDER = "SF-ORD-10418"
CAPITALIZATION, AMORTIZATION = "CONTRACT_COST_CAPITALIZATION", "CONTRACT_COST_AMORTIZATION"
# The AVM-US chart with the accounts of a receipt while not a contract (JET-01b), of a capitalised
# cost to obtain with its amortisation (JET-09a, JET-09b) and the contract asset a netting reclass
# of a seat contract reaches (JET-06), so that a close run of the world reaches its end.
CHART = (
    *STEP1_CHART,
    ("1220", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"),
    ("1300", "Costs to obtain contracts", "ASSET", "D", "COST_TO_OBTAIN_ASSET"),
    ("2300", "Accrued commissions", "LIABILITY", "C", "CONTRACT_COST_CLEARING"),
    ("6100", "Amortisation of contract costs", "EXPENSE", "D", "CONTRACT_COST_AMORTIZATION"),
)

# (entry kind, stored subject key, account role, transaction amount — debit positive)
Line = tuple[str, str | None, str, Decimal]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    built = seat_world(app, keyring, clock, files, chart=CHART)
    # BUILD_SPEC CTR-6: a cost event a person records waits for the event reviewer.
    assign(built.priya.member, "revenue_reviewer")
    return built


@pytest.fixture
def rebates(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K06World:
    """PRD §2.6 for K-06: AVM-DE (EUR), 575 drive parts at EUR 100.00 with the rebate element
    ``REBATE-DR-01`` (``test_estimates.k06_world``)."""
    return k06_world(app, keyring, clock, files)


def _k09(world: SeatWorld) -> tuple[UUID, UUID, str]:
    """K-09 (30 seats x 36 months, 108,000.00 USD from 1 Sep 2026) booked, activated and computed:
    (contract id, group id, group code)."""
    booked = activated_contract(
        world.place, booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    )
    contract_id = UUID(str(booked.contract["id"]))
    return (contract_id, *_group(world.place, contract_id))


def _group(place: Workspace, contract_id: UUID) -> tuple[UUID, str]:
    group_id = UUID(
        str(
            place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == contract_id)
            )
        )
    )
    code = place.scalar(select(combination_group.c.code).where(combination_group.c.id == group_id))
    return group_id, str(code)


def _ledger(place: Workspace, contract_id: UUID) -> list[Line]:
    """The contract's ledger lines in posting order: by seal, then entry, role and amount."""
    seal = subledger_posting_seal
    rows = place.rows(
        select(
            seal.c.chain_seq,
            subledger_line.c.entry_no,
            subledger_line.c.entry_kind,
            subledger_line.c.subject_key,
            subledger_line.c.account_role,
            subledger_line.c.amount_txn,
        )
        .select_from(
            subledger_line.join(
                seal,
                and_(
                    seal.c.tenant_id == subledger_line.c.tenant_id,
                    seal.c.subledger_posting_id == subledger_line.c.subledger_posting_id,
                ),
            )
        )
        .where(subledger_line.c.contract_id == contract_id)
    )
    ordered = sorted(
        (
            int(row["chain_seq"]),
            int(row["entry_no"]),
            str(row["account_role"]),
            Decimal(row["amount_txn"]),
            str(row["entry_kind"]),
            row["subject_key"],
        )
        for row in rows
    )
    return [(kind, subject, role, amount) for _, _, role, amount, kind, subject in ordered]


def _subjects(lines: list[Line]) -> set[tuple[str, str | None]]:
    return {(kind, subject) for kind, subject, _, _ in lines}


def _of(lines: list[Line], kind: str) -> list[Line]:
    return sorted(line for line in lines if line[0] == kind)


def _commission(world: SeatWorld, contract_id: UUID, amount: str, on: str) -> str:
    """A commission of ``amount`` recorded by Maya and approved by Priya; the approval appends
    ``COST_INCURRED`` and computes the group. Returns the subject of its cost asset,
    ``<contract>/<event key>`` (ENGINE_SPEC_B S14-R-12)."""
    recorded = approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "COST_INCURRED",
            "effective_date": on,
            "payload": {
                "purpose": "COST_TO_OBTAIN",
                "payee": "Sales rep 12",
                "plan_code": "SALES-2026",
                "amount": {"amount": amount, "currency": "USD"},
                "is_incremental": True,
            },
        },
    )
    assert recorded["computation"]["status"] == "SUCCEEDED", recorded["computation"]
    head = int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )
    external_id = world.place.scalar(
        select(contract.c.external_id).where(contract.c.id == contract_id)
    )
    return f"{external_id}/EV-{head:06d}"


def _cost_lines(subject: str, capitalised: str, amortised: str) -> dict[str, list[Line]]:
    """JET-09a Dr COST_TO_OBTAIN_ASSET / Cr CONTRACT_COST_CLEARING and JET-09b Dr
    CONTRACT_COST_AMORTIZATION / Cr COST_TO_OBTAIN_ASSET of one asset, under its subject."""
    cost, share = Decimal(capitalised), Decimal(amortised)
    return {
        CAPITALIZATION: [
            (CAPITALIZATION, subject, "CONTRACT_COST_CLEARING", -cost),
            (CAPITALIZATION, subject, "COST_TO_OBTAIN_ASSET", cost),
        ],
        AMORTIZATION: [
            (AMORTIZATION, subject, "CONTRACT_COST_AMORTIZATION", share),
            (AMORTIZATION, subject, "COST_TO_OBTAIN_ASSET", -share),
        ],
    }


def _recompute_posts_nothing(place: Workspace, contract_id: UUID, group_id: UUID) -> list[Line]:
    """S14-INV-02 on the database: the group computed again over the same events and its own
    postings emits no intent, the ledger is unchanged and the read-back answers exactly the stored
    subjects. Returns the ledger."""
    before = _ledger(place, contract_id)
    bundle, output, stored = computed(place, group_id)
    assert stored["replayed"] is False  # a computation of its own: its input holds the postings
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _ledger(place, contract_id) == before
    assert {(item.entry_kind, item.subject_key) for item in bundle.posted} == _subjects(before)
    return before


def test_a_cost_asset_is_read_back_under_its_own_subject(world: SeatWorld) -> None:
    """K-09 with a commission of 6,480.00 on 5 Sep 2026. The computation of its approval posts
    the capitalisation and September's amortisation — 6,480.00 x 30 / 1,096 = 177.37, the share
    of the term's 1,096 days that September holds — under the asset's subject
    ``<contract>/<event>``; the revenue stays under the obligation's. A second computation with
    no fact between posts nothing. A second commission of 1,200.00 on 10 Sep then posts under its
    own asset's subject only (32.85 = 1,200.00 x 30 / 1,096), and the next computation again
    nothing."""
    contract_id, group_id, _ = _k09(world)
    first = _commission(world, contract_id, "6480.00", "2026-09-05")
    assert first == f"{K09}/EV-000003"
    ledger = _recompute_posts_nothing(world.place, contract_id, group_id)
    assert _subjects(ledger) == {
        ("REVENUE_RECOGNITION", f"{K09}/O1"),
        (CAPITALIZATION, first),
        (AMORTIZATION, first),
    }
    expected = _cost_lines(first, "6480.00", "177.37")
    assert _of(ledger, CAPITALIZATION) == sorted(expected[CAPITALIZATION])
    assert _of(ledger, AMORTIZATION) == sorted(expected[AMORTIZATION])

    second = _commission(world, contract_id, "1200.00", "2026-09-10")
    assert second == f"{K09}/EV-000004"
    now = _ledger(world.place, contract_id)
    added = now[len(ledger) :]
    assert now[: len(ledger)] == ledger
    assert _subjects(added) == {(CAPITALIZATION, second), (AMORTIZATION, second)}
    expected = _cost_lines(second, "1200.00", "32.85")
    assert _of(added, CAPITALIZATION) == sorted(expected[CAPITALIZATION])
    assert _of(added, AMORTIZATION) == sorted(expected[AMORTIZATION])
    _recompute_posts_nothing(world.place, contract_id, group_id)


def _receipt(reference: str, amount: str, on: str) -> dict[str, Any]:
    return {
        "event_type": "PAYMENT_RECEIVED",
        "effective_date": on,
        "payload": {
            "receipt_reference": reference,
            "amount": {"amount": amount, "currency": "USD"},
            "receipt_date": on,
        },
    }


def test_a_deposit_is_read_back_under_the_contract_and_entity_subject(world: SeatWorld) -> None:
    """K-09 assessed as not a contract (collection not probable), then a receipt of 36,000.00 on
    5 Sep 2026: JET-01b Dr BILLING_CLEARING / Cr DEPOSIT_LIABILITY, stored under
    ``<contract>@<entity>`` — the family whose stored key is the spelling the read-back gave
    before. A second computation posts nothing; a second receipt of 12,000.00 posts its own two
    lines under the same subject."""
    booked = booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    contract_id = UUID(str(booked.contract["id"]))
    group_id, _ = _group(world.place, contract_id)
    _gated(world, contract_id)
    paid = _record_events(world, contract_id, _receipt("RCPT-US-4410", "36000.00", "2026-09-05"))
    assert paid.status_code == 201, paid.text
    assert paid.json()["computation"]["status"] == "SUCCEEDED", paid.json()["computation"]
    subject = f"{K09}@{AVM_US}"
    ledger = _recompute_posts_nothing(world.place, contract_id, group_id)
    assert ledger == [
        ("DEPOSIT", subject, "BILLING_CLEARING", Decimal("36000.00")),
        ("DEPOSIT", subject, "DEPOSIT_LIABILITY", Decimal("-36000.00")),
    ]

    again = _record_events(world, contract_id, _receipt("RCPT-US-4522", "12000.00", "2026-09-10"))
    assert again.status_code == 201, again.text
    assert _ledger(world.place, contract_id) == [
        *ledger,
        ("DEPOSIT", subject, "BILLING_CLEARING", Decimal("12000.00")),
        ("DEPOSIT", subject, "DEPOSIT_LIABILITY", Decimal("-12000.00")),
    ]
    _recompute_posts_nothing(world.place, contract_id, group_id)


def test_a_line_without_a_subject_key_is_read_back_in_the_spelling_of_l3_1_q_32(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The column is nullable: a line a test builder writes stores no key (the supervisor's
    ruling of 2026-10-02). Such a line is read back as every line was before — a line of an
    obligation under its obligation subject key, any other line under ``<contract>@<entity>``
    (decision L3-1-Q-32, which stands for such lines alone). K-09 with its commission, every
    line written without a key: the revenue answers ``<contract>/O1`` and the cost asset's lines
    answer ``<contract>@<entity>``. (The FX line without a key, which answers
    ``<group>@<entity>``, is ``test_fx_remeasurement_recompute.py``.)"""
    keyless(monkeypatch)
    contract_id, group_id, _ = _k09(world)
    _commission(world, contract_id, "6480.00", "2026-09-05")
    ledger = _ledger(world.place, contract_id)
    assert _subjects(ledger) == {
        ("REVENUE_RECOGNITION", None),
        (CAPITALIZATION, None),
        (AMORTIZATION, None),
    }
    with world.place.uow() as uow:
        bundle = bundles.build(uow.session, group_id, uow.now, (), ComputationTrigger.COMMAND)
    assert {(item.entry_kind, item.subject_key) for item in bundle.posted} == {
        ("REVENUE_RECOGNITION", f"{K09}/O1"),
        (CAPITALIZATION, f"{K09}@{AVM_US}"),
        (AMORTIZATION, f"{K09}@{AVM_US}"),
    }


def _locked(world: SeatWorld, period_key: str) -> None:
    """The period closed for ASC606 as BS3-D-20 lays it — open, closing, closed, each change with
    its transition row, the closing row naming a stored lock — after the period's close run
    posted its period end. The lock's gates are not what this witness is about."""
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
                period_state.c.book_code == BOOK,
            )
        ).scalar_one()
        request = approval_request_values(tenant_id, status=ApprovalRequestStatus.APPROVED)
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


def _closed(
    world: SeatWorld, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch, period_key: str
) -> dict[str, Any]:
    """A close run of AVM-US and the period, started by Maya and worked to its end."""
    maya = world.place.author
    runs.unattended(monkeypatch)
    run_id, job_id = runs.started(world.app, maya, entity_code=AVM_US, period_key=period_key)
    runs.work(world.place.tenant_id, runtime, job_id)
    return runs.shown(world.app, maya, run_id)


def _stopped(run: dict[str, Any]) -> list[tuple[str, Any]]:
    return [
        (step["step_code"], step["problem"]) for step in run["steps"] if step["status"] == "FAILED"
    ]


def _out_of_period(place: Workspace, contract_id: UUID) -> list[tuple[str, int]]:
    """(entry kind, source events) of the contract's lines posted outside their origin period."""
    events = (
        select(func.count())
        .where(subledger_line_event.c.subledger_line_id == subledger_line.c.id)
        .correlate(subledger_line)
        .scalar_subquery()
    )
    rows = place.rows(
        select(subledger_line.c.entry_kind, events.label("events")).where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.origin_period_id.is_not(None),
        )
    )
    return sorted((str(row["entry_kind"]), int(row["events"])) for row in rows)


def test_a_computation_behind_a_lock_posts_nothing_and_the_next_close_run_reaches_its_end(
    world: SeatWorld,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case lane F-ADM-WEB measured on the volume seed (item PERF-SEED-LOCK-1), on two months.
    January to July are closed. An order of 30 seats for 36 months from 1 Aug 2026 (108,000.00)
    with a commission of 6,480.00 on 5 Aug is computed: the asset's lines of August and September
    stand in their periods. August's close run posts its period end and August is locked. The
    group is then computed again with no new fact — the bulk recompute of a seed, a command of
    any kind; the period's state is in the computation's input, so it is a computation of its
    own. It posts nothing: no line of August is carried into September, hence none without a
    source event, and September's close run reaches its end.

    Before revision 0124 that computation took the cost asset's lines back under
    ``<contract>@<entity>`` and posted them again: August's halves in September with origin
    August, reason ``LATE_EVENT`` and no source event, and September's run ended ``FAILED`` at
    its dataset freeze, "out-of-period subledger line(s) carry no source event attribution
    (S15-R-18b)"."""
    maya = world.place.author
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    periods_closed_before(world.place, world.app, maya, entity_id=world.entity_id, before=AUGUST)
    line = seat_line("O1", seats="30", price="108000.00", start="2026-08-01", end="2029-07-31")
    body = seat_body(
        world.customers["C-09"], external_id=AUGUST_ORDER, inception="2026-08-01", lines=[line]
    )
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    contract_id = UUID(str(booked.contract["id"]))
    group_id, _ = _group(world.place, contract_id)
    asset = _commission(world, contract_id, "6480.00", "2026-08-05")
    assert asset == f"{AUGUST_ORDER}/EV-000003"

    august = _closed(world, runtime, monkeypatch, AUGUST)
    assert august["status"] == "SUCCEEDED", _stopped(august)
    _locked(world, AUGUST)
    ledger = _ledger(world.place, contract_id)
    assert {(CAPITALIZATION, asset), (AMORTIZATION, asset)} <= _subjects(ledger)

    with world.place.uow() as uow:
        again = computation.recompute(uow, group_id)
        uow.commit()
    assert (str(again["status"]), again["replayed"]) == ("SUCCEEDED", False)
    assert _ledger(world.place, contract_id) == ledger
    assert _out_of_period(world.place, contract_id) == []

    september = _closed(world, runtime, monkeypatch, SEPTEMBER)
    assert september["status"] == "SUCCEEDED", _stopped(september)
    assert runs.step(september, "DATASET_FREEZE")["status"] == "SUCCEEDED"


def _version(world: K06World, estimate_id: str, body: dict[str, Any]) -> None:
    """One version of the rebate estimate, prepared by Maya with what its submission asks and
    approved by Priya; the approval appends ``ESTIMATE_CHANGED`` and computes the group."""
    created = post(world.app, f"{ESTIMATES}/{estimate_id}/versions", world.place.author, body)
    assert created.status_code == 201, created.text
    request_id = _submitted(world, str(created.json()["id"]))
    decided = approve(world.app, request_id, world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def _not_after_all() -> dict[str, Any]:
    """Version 3: the threshold is not expected after all — refund target 0.00 from 30 Sep 2026."""
    return _rebate_version(
        "2026-09-30",
        "0.00",
        "Threshold not expected after all",
        "Tessen Werke moved its orders to the next framework year.",
        parameters={"refund_liability_target": "0.00"},
    )


def _component_lines(subject: str, amount: str) -> list[Line]:
    """JET-04b under the component's subject: Dr CONTRACT_LIABILITY / Cr REFUND_LIABILITY of
    ``amount`` (negative: taken back)."""
    value = Decimal(amount)
    return sorted(
        [(REFUND, subject, "CONTRACT_LIABILITY", value), (REFUND, subject, REFUND, -value)]
    )


def _taken_back(subject: str) -> list[Line]:
    """Version 3 on the ledger: the component's 5,750.00 taken back under ``subject`` and the
    revenue of the obligation with it."""
    return sorted(
        [
            *_component_lines(subject, "-5750.00"),
            ("REVENUE_RECOGNITION", f"{K06}/O1", "CONTRACT_LIABILITY", Decimal("5750.00")),
            ("REVENUE_RECOGNITION", f"{K06}/O1", "REVENUE", Decimal("-5750.00")),
        ]
    )


def test_a_refund_liability_component_is_read_back_under_its_own_subject(
    rebates: K06World,
) -> None:
    """K-06 with both shipments (75 and 500 units) and version 2 of the rebate estimate —
    threshold expected, refund target 5,750.00 (PRD J-07.2): JET-04b posts Dr CONTRACT_LIABILITY /
    Cr REFUND_LIABILITY 5,750.00 under the component's subject
    ``<group>@<entity>/VARIABLE_CONSIDERATION/<contract>/<element>``. A second computation with no
    fact between posts nothing. Version 3 (threshold not expected after all) then takes exactly
    the 5,750.00 back under the same subject, and the revenue with it; the next computation
    again nothing."""
    place = rebates.place
    k06 = _k06_with_v1(rebates)
    _, code = _group(place, k06.contract_id)
    _version(rebates, k06.estimate_id, _v2_body())
    component = f"{code}@{AVM_DE}/VARIABLE_CONSIDERATION/{K06}/{REBATE}"
    ledger = _recompute_posts_nothing(place, k06.contract_id, k06.group_id)
    assert _subjects(ledger) == {("REVENUE_RECOGNITION", f"{K06}/O1"), (REFUND, component)}
    assert _of(ledger, REFUND) == _component_lines(component, "5750.00")

    _version(rebates, k06.estimate_id, _not_after_all())
    now = _ledger(place, k06.contract_id)
    assert now[: len(ledger)] == ledger
    assert sorted(now[len(ledger) :]) == _taken_back(component)
    _recompute_posts_nothing(place, k06.contract_id, k06.group_id)


def _combined(world: K06World, *contract_ids: UUID) -> UUID:
    """The contracts combined into one group by the approved command (03 REQ-CON-009; ENGINE_SPEC
    S02-R-09): Maya proposes and submits, Marcus approves, and the approval computes the group
    with every member in it. Returns the group id."""
    maya = world.place.author
    proposed = post(
        world.app,
        GROUPS,
        maya,
        {
            "contract_ids": [str(contract_id) for contract_id in contract_ids],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(world.app, f"{GROUPS}/{group_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert decided.status_code == 200, decided.text
    return group_id


def test_a_combination_posts_only_differences_for_a_component_stored_under_the_former_group(
    rebates: K06World,
) -> None:
    """The regrouping rule of ENGINE_SPEC_B S14-R-04 on the database (supervisor rulings R-11 as
    amended and R-44 (b)). K-06 posts its rebate component (5,750.00) under the key of its own
    singleton group and is then combined with a second order of the same customer by the approved
    command. The ledger keeps the component under the former group's key and the read-back answers
    that key; stage 14 reads it as the same component of the combined group, so the combination
    posts nothing under either key. The stored keys alone would reverse the 5,750.00 under the
    former group's key and post it again under the combined group's. A changed estimate
    afterwards (threshold not expected after all) takes the 5,750.00 back once, under the
    combined group's key."""
    place = rebates.place
    k06 = _k06_with_v1(rebates)
    _, former_code = _group(place, k06.contract_id)
    _version(rebates, k06.estimate_id, _v2_body())
    source = f"{AVM_DE}/VARIABLE_CONSIDERATION/{K06}/{REBATE}"
    former = f"{former_code}@{source}"
    before = _ledger(place, k06.contract_id)
    assert _of(before, REFUND) == _component_lines(former, "5750.00")

    # A second order of the same customer, a group of its own until the combination.
    twin_body = {**k06_body(rebates.customer_id), "external_id": TWIN}
    twin = activated_contract(place, booked_contract(place, twin_body, activate=False))
    twin_id = UUID(str(twin.contract["id"]))
    group_id = _combined(rebates, k06.contract_id, twin_id)
    now_group, now_code = _group(place, k06.contract_id)
    assert (now_group, now_code != former_code) == (group_id, True)
    current = f"{now_code}@{source}"

    # The combination's computation posted nothing for either contract: the lines posted before
    # stand, and the twin, undelivered, has none.
    assert _ledger(place, k06.contract_id) == before
    assert _ledger(place, twin_id) == []
    # The read-back answers the stored key of the former group; a further computation posts
    # nothing.
    bundle, output, _ = computed(place, group_id)
    assert {item.subject_key for item in bundle.posted if item.entry_kind == REFUND} == {former}
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _ledger(place, k06.contract_id) == before

    # A changed estimate posts its difference once, under the combined group's key.
    _version(rebates, k06.estimate_id, _not_after_all())
    after = _ledger(place, k06.contract_id)
    assert after[: len(before)] == before
    assert sorted(after[len(before) :]) == _taken_back(current)
    bundle, output, _ = computed(place, group_id)
    assert {item.subject_key for item in bundle.posted if item.entry_kind == REFUND} == {
        former,
        current,
    }
    assert [intent for book in output.books for intent in book.posting_intents] == []
