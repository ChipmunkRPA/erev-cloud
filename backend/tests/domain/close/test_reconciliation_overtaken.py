"""A reviewed reconciliation that the period has overtaken does not satisfy the gate (supervisor
ruling R-58 (e); 04 T-CLS-06 "Current reconciliation" rev 1.121; PRD BR-CLS-01; SCREENS_B §1.1 gate
label table rev 1.27; BUILD_SPEC CLO-16, CLO-17).

World: ``worlds.k01_pellworth`` through 31 Jan 2026 with both required reconciliations of January
reviewed — billing to subledger (INV-US-1001 is a billing event without a document of the billing
system: one difference, explained) and subledger to GL (an uploaded trial balance that states the
subledger's balances: its posted lines, and on the contract liability account the invoice the ERP
posts itself, which the subledger holds in the stored contract balance — supervisor rulings R-69,
R-74).

The clocks. A subledger line and a source invoice carry the application instant of their unit of
work, a contract event the start of its transaction on the server; a reconciliation's
``as_of_known_at`` is the later of the application instant and the transaction timestamp
(``freeze.freeze_cutoff``). The world stands on the RECORD clock (``worlds.on_record_clock``;
dev-guide DG-TST-14 rev 1.276): the frozen application clock is moved onto the server's present,
so a reconciliation's instant is the start of its transaction, as under the wall clock.

Until item CLO-RATE-AFTER-RUN-1's head the fixture held the application clock an HOUR AHEAD of
the server's. The time test of ruling R-58 (e) needed that for a line to be "recorded after" a
reconciliation; under the lead every row the server recorded within the hour lay before every
reconciliation, and the sixth case below could not occur — it stayed hidden for a day. Since
revision 0121 the gate decides by a position and by counts: the six tests that stood on that
fixture were tried once on the record clock, held, and were moved (the supervisor's ruling of
2026-10-02 08:53, point 4).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import combination_group, contract, contract_event, subledger_line
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates
from erev_api.domain.close import reconciliations as reconciliation_domain
from erev_api.domain.contracts import bundles, computation
from erev_api.enums import ComputationTrigger, ContractEventType
from erev_api.events.payloads import BillingRecordedV1, ProgressRecordedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from erev_api.schemas.periods import PeriodLockRequestIn
from fastapi import FastAPI
from sqlalchemy import func, select
from support import reconciliations as recon
from support.close_world import JOURNAL_RUNS, acknowledge_run
from support.db import TestDatabase
from support.factories import appended, computed
from support.principals import Actor, carrying, enrolled, step_up
from support.reference import PERIODS, assign, get, periods, post
from support.worlds import (
    K01,
    ReportWorld,
    journal_run,
    k01_pellworth,
    on_record_clock,
)

JANUARY = "FY2026-P01"
BOOK = "ASC606"
USD = "USD"
GATE = gates.RECONCILIATIONS_GENERATED
BILLING_OUT_OF_DATE = "Reconciliation out of date, generate it again: Billing to subledger"
LEDGER_OUT_OF_DATE = "Reconciliation out of date, generate it again: Subledger to GL"
STEP = timedelta(seconds=1)
# A January invoice of the billing system that WLD-K-01 does not hold.
LATE_INVOICE = (
    (K01, "INVOICE", "INV-US-1090", "2026-01-20", "", "false", "", "", "1",
     "O2", "AVM-IMPL-STD", "1", "750.00", "USD", "", "", "", "", ""),
)  # fmt: skip


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def pellworth(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """WLD-K-01 through January on the record clock (module docstring); the jump ends every
    session, so the actors sign in again."""
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 31))
    assign(world.priya.member, "revenue_reviewer")  # recon.signoff, import.approve
    return on_record_clock(world, clock)


def _net_by_account(world: ReportWorld, run_id: str) -> dict[str, Decimal]:
    listed = get(world.app, f"{JOURNAL_RUNS}/{run_id}/lines", world.maya, {"limit": 200})
    assert listed.status_code == 200, listed.text
    net: dict[str, Decimal] = {}
    for line in listed.json()["items"]:
        code = str(line["account"]["code"])
        net[code] = (
            net.get(code, Decimal(0))
            + Decimal(line["debit_functional"]["amount"])
            - Decimal(line["credit_functional"]["amount"])
        )
    return net


def _journalised(world: ReportWorld, clock: FrozenClock) -> dict[str, Decimal]:
    """A January journal run over what is not journalised yet, held by the GL (acknowledged, as
    the lock tests state it); its amounts by account."""
    run = journal_run(world, period_key=JANUARY)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        acknowledge_run(session, UUID(str(run["id"])), now=clock.now())
    return _net_by_account(world, str(run["id"]))


def _billing_reviewed(world: ReportWorld, maya: Actor, priya: Actor) -> dict[str, Any]:
    """January's billing reconciliation generated, its differences explained, prepared by Maya and
    reviewed by Priya."""
    draft = recon.generated(
        world.app, maya, world.runtime, entity_code="AVM-US", period_key=JANUARY
    )
    for item in recon.items_of(world.app, maya, draft["id"]):
        explained = recon.explain(
            world.app, maya, item, "Recorded from the order; the billing document follows."
        )
        assert explained.status_code == 200, explained.text
    assert recon.prepare(world.app, maya, draft["id"]).status_code == 200
    reviewed = recon.sign(world.app, priya, draft["id"])
    assert reviewed.status_code == 200, reviewed.text
    return dict(reviewed.json())


def _ledger_reviewed(
    world: ReportWorld, maya: Actor, priya: Actor, balances: dict[str, Decimal]
) -> dict[str, Any]:
    """January's subledger-to-GL reconciliation generated against a trial balance that states
    ``balances``, prepared and reviewed."""
    draft = recon.generated(
        world.app,
        maya,
        world.runtime,
        entity_code="AVM-US",
        period_key=JANUARY,
        kind=recon.SUBLEDGER_TO_GL,
    )
    content = recon.trial_balance_csv([(code, USD, balances[code]) for code in sorted(balances)])
    name = f"avm-us-tb-2026-01-{draft['reconciliation_no']}.csv"
    file_id = recon.uploaded(world.app, maya, name, content)
    compared = recon.attached(world.app, maya, world.runtime, draft["id"], {"file_id": file_id})
    assert compared["variance_count"] == 0, compared
    assert recon.prepare(world.app, maya, draft["id"]).status_code == 200
    reviewed = recon.sign(world.app, priya, draft["id"])
    assert reviewed.status_code == 200, reviewed.text
    return dict(reviewed.json())


def _gate(world: ReportWorld, period_id: UUID) -> tuple[str, int | None, str | None, int, int]:
    """(status, count, detail) of RECONCILIATIONS_GENERATED as evaluated now, then the cockpit's
    unsigned count and the number of required kinds it shows reviewed."""
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, world.entity_id, BOOK, period_id)
        scope = gates.scope_of_period(uow.session, world.entity_id, BOOK, period_id)
        assert scope is not None
        unsigned = gates.blocker_counts(uow.session, scope)["reconciliations_unsigned"]
        kpi = gates.reconciliations_reviewed(uow.session, scope, known_at=uow.now)
        uow.commit()
    assert kpi["required"] == 2
    (found,) = [result for result in results if result.gate_check_code == GATE]
    return found.status.value, found.count, found.detail, unsigned, kpi["reviewed"]


def test_r58_a_reviewed_reconciliation_overtaken_by_the_period_fails_the_gate(
    app: FastAPI, clock: FrozenClock, pellworth: ReportWorld
) -> None:
    """Supervisor ruling R-58 (e): the current reconciliation of a kind counts as reviewed only
    while its ``as_of_known_at`` is not earlier than the record time of the latest subledger line
    of its entity, book and period — and, for billing to subledger, of the latest source invoice
    of the period. Otherwise the gate names it out of date, the lock request is refused, and
    generating, preparing and reviewing it again satisfies the gate.

    Since item REC-GEN-LOCK-1 (04 T-CLS-06 "What a reconciliation read", rev 1.259) the same is
    read from what each generation recorded — the chain position and the counts — and every step
    keeps its value but the last, which the supervisor ruled a STALE EXPECTATION (2026-10-02
    00:09): the late invoice of the billing system is applied as a billing event, and both kinds
    are out of date."""
    world = pellworth
    maya = enrolled(app, clock, world.maya.member)  # a sign-off needs an MFA-verified session
    # From here Maya and the world work with the verified session: with a factor, her earlier
    # one owes the challenge (REQ-PLT-005).
    world = carrying(world, maya=maya)
    priya = step_up(app, clock, world.priya)
    (january,) = [
        item
        for item in periods(app, maya, entity="AVM-US")
        if item["period"]["period_key"] == JANUARY
    ]
    period_id = UUID(str(january["period"]["id"]))
    balances = _journalised(world, clock)
    # ``billing.posting = ERP``: the ledger also holds INV-US-1001 120,000.00, which the ERP posts
    # to the contract liability account itself (PRD WLD-K-01; POLICIES JET-03). On the role basis
    # the subledger states the same in the stored contract balance (supervisor rulings R-69, R-74).
    balances["2100"] -= Decimal("120000.00")

    # --- both kinds reviewed after the period's last posting: the gate passes -------------------
    _billing_reviewed(world, maya, priya)
    first_ledger = _ledger_reviewed(world, maya, priya, balances)
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)

    # --- a posting overtakes both ---------------------------------------------------------------
    clock.advance(STEP)
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    appended(
        world.place,
        contract_id,
        int(head),
        [
            EventIn(
                event_type=ContractEventType.PROGRESS_RECORDED,
                effective_date=date(2026, 1, 31),
                payload=ProgressRecordedV1(
                    obligation_key="O2",
                    cumulative_progress_ratio="0.50",
                    measure="OUTPUT_PERCENT",
                ),
            )
        ],
    )
    computed(world.place, UUID(str(booked.combination_group["id"])))
    overtaken = _gate(world, period_id)
    assert overtaken == ("FAILED", 2, f"{BILLING_OUT_OF_DATE}; {LEDGER_OUT_OF_DATE}", 2, 0)
    # Both rows are still REVIEWED: nothing was written to them, the gate reads them as they are.
    assert recon.shown(app, maya, first_ledger["id"])["status"] == "REVIEWED"

    # --- the lock request is refused by the gate ------------------------------------------------
    started = post(
        app,
        f"{PERIODS}/{january['id']}/start-close",
        maya,
        {"comment": "January close"},
        if_match=f'"r{january["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    with pytest.raises(Problem) as refused, world.place.uow() as uow:
        close_commands.request_lock(
            uow,
            state_id=UUID(str(january["id"])),
            body=PeriodLockRequestIn(certification_comment="January 2026 close complete"),
            check_version=lambda actual: None,
        )
    assert refused.value.slug == "close-gates-failed"
    named = {error.rule_id: error.message for error in refused.value.errors}
    assert named[GATE] == f"{BILLING_OUT_OF_DATE}; {LEDGER_OUT_OF_DATE}"

    # --- generated, prepared and reviewed again: the gate passes --------------------------------
    clock.advance(STEP)
    later = _journalised(world, clock)  # the posting, journalised and held by the GL
    balances = {code: balances[code] + later.get(code, Decimal(0)) for code in balances}
    _billing_reviewed(world, maya, priya)
    second_ledger = _ledger_reviewed(world, maya, priya, balances)
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)
    assert recon.shown(app, maya, first_ledger["id"])["is_current"] is False

    # --- a late document of the billing system overtakes both ------------------------------------
    # The import stores the document and applies it as a billing event of WLD-K-01 (DIN-9). It is
    # a document the billing reconciliation did not read; and it is an event of January the
    # subledger-to-GL reconciliation did not read either. Under ``billing.posting = ERP`` it
    # writes no subledger line, but on the role basis it moves the stored closing contract
    # liability — the subledger side of the role's row — once it is computed: the reviewed
    # comparison is of a balance the subledger no longer states. Until item REC-GEN-LOCK-1 the
    # gate named billing to subledger alone here, ("FAILED", 1, BILLING_OUT_OF_DATE, 1, 1); the
    # supervisor ruled that expectation stale (2026-10-02 00:09). "Billing to subledger only" has
    # no world through the import: it stores no document without applying it to its contract.
    clock.advance(STEP)
    recon.ingested(
        app,
        maya,
        priya,
        world.runtime,
        "avm-us-invoices-2026-01-late.csv",
        recon.invoices_csv(LATE_INVOICE),
    )
    assert _gate(world, period_id) == (
        "FAILED",
        2,
        f"{BILLING_OUT_OF_DATE}; {LEDGER_OUT_OF_DATE}",
        2,
        0,
    )
    assert recon.shown(app, maya, second_ledger["id"])["status"] == "REVIEWED"


# --- what a reconciliation read: a position and counts, not a time (item REC-GEN-LOCK-1) ---------
# 04 T-CLS-06 rev 1.259; the supervisor's rulings of 2026-10-01 21:41 and 22:52 and of 2026-10-02
# 00:09 and 01:41. Five ways a reviewed reconciliation missed a fact of its period while the gate
# counted it reviewed, each measured before the item (V1 to V3 on main 5310275d, V4 and V5 on the
# role basis's tree):
# V1 and V2 — a posting that began before the generation and committed after it;
# V3 — a billing event that writes no subledger line, against billing to subledger;
# V4 — the same event against subledger to GL on the role basis, whose subledger side for the
#      contract balance roles is the stored closing balance;
# V5 — that event recorded BEFORE the generation and computed after the review: the generation
#      counted it, the stored balance it compared did not hold it yet;
# V6 — that event recorded and computed WHILE the generation runs, after the generation's instant
#      is fixed and before it counts: counted, and beyond what the attach reads.
# The mirror of V6 (the supervisor's word of 2026-10-02 05:34) is witnessed with them: that event
# recorded BEFORE the generation's instant in a unit of work that commits after the generation
# counted — not in the generation's number, in the gate's.

ERP_INVOICE = Decimal("120000.00")  # INV-US-1001, which the ERP posts to 2100 itself
LATE_NUMBER = "INV-US-1095"
LATE_AMOUNT = Decimal("500.00")
BOTH_OUT_OF_DATE = f"{BILLING_OUT_OF_DATE}; {LEDGER_OUT_OF_DATE}"


def _january_signers(
    app: FastAPI, clock: FrozenClock, world: ReportWorld
) -> tuple[ReportWorld, Actor, Actor, dict[str, Any]]:
    """Maya on an MFA-verified session, Priya stepped up, and January's period row."""
    maya = enrolled(app, clock, world.maya.member)
    world = carrying(world, maya=maya)
    priya = step_up(app, clock, world.priya)
    (january,) = [
        item
        for item in periods(app, maya, entity="AVM-US")
        if item["period"]["period_key"] == JANUARY
    ]
    return world, maya, priya, january


def _erp_ledger(posted: dict[str, Decimal]) -> dict[str, Decimal]:
    """The ledger the ERP keeps: the journal's amounts, and on the contract liability account
    the invoice the ERP posts itself (``billing.posting = ERP``; rulings R-69, R-74)."""
    return {**posted, "2100": posted["2100"] - ERP_INVOICE}


def _january_lines(world: ReportWorld, period_id: UUID) -> tuple[int, datetime | None]:
    """(how many subledger lines January holds, the latest ``recorded_at`` among them)."""
    (row,) = world.place.rows(
        select(
            func.count().label("held"), func.max(subledger_line.c.recorded_at).label("latest")
        ).where(
            subledger_line.c.entity_id == world.entity_id, subledger_line.c.period_id == period_id
        )
    )
    return int(row["held"]), row["latest"]


def _progress_of_january() -> EventIn:
    return EventIn(
        event_type=ContractEventType.PROGRESS_RECORDED,
        effective_date=date(2026, 1, 31),
        payload=ProgressRecordedV1(
            obligation_key="O2", cumulative_progress_ratio="0.50", measure="OUTPUT_PERCENT"
        ),
    )


def _invoice(number: str, amount: str, day: date) -> EventIn:
    """A billing event of WLD-K-01's obligation O2: one invoice line, issued on ``day``."""
    payload = BillingRecordedV1(
        invoice_number=number,
        line_external_id=f"{number}-1",
        obligation_key="O2",
        amount=MoneyIn(amount=amount, currency=USD),
        issue_date=day,
    )
    return EventIn(
        event_type=ContractEventType.BILLING_RECORDED, effective_date=day, payload=payload
    )


def _computed_in(slow: Any, world: ReportWorld, fact: EventIn) -> None:
    """``fact`` appended to WLD-K-01 and its group computed INSIDE the unit of work ``slow``, as a
    command does it — the lines are written and sealed, and nothing is committed."""
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    head = slow.session.execute(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    ).scalar_one()
    append_events(
        slow, contract_id=contract_id, expected_stream_version=int(head), events=[fact], origin="UI"
    )
    group_id = UUID(str(booked.combination_group["id"]))
    bundle = bundles.build(slow.session, group_id, slow.now, (), ComputationTrigger.COMMAND)
    stored = computation.persist(slow, bundle, computation.default_engine()(bundle))
    assert str(stored["status"]) == "SUCCEEDED"


def _waits(world: ReportWorld, group_id: UUID) -> bool:
    """Whether the group waits for a computation (04 T-CON-03 ``dirty_since``)."""
    since = world.place.scalar(
        select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    )
    return since is not None


def _recorded(world: ReportWorld, fact: EventIn) -> None:
    """``fact`` appended to WLD-K-01 and computed, each in a unit of work of its own."""
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    appended(world.place, contract_id, int(head), [fact])
    computed(world.place, UUID(str(booked.combination_group["id"])))


@pytest.mark.parametrize(
    "written_before",
    [False, True],
    ids=["lines written after the generation", "lines written and uncommitted at the generation"],
)
def test_a_posting_that_began_before_a_generation_and_committed_after_it_overtakes_it(
    app: FastAPI, clock: FrozenClock, pellworth: ReportWorld, written_before: bool
) -> None:
    """V1 and V2. A unit of work begins at T and posts two lines of January; the subledger-to-GL
    reconciliation is generated, compared and reviewed at T + 1 s while that unit of work is
    open, and the unit of work commits afterwards. Its lines carry ``recorded_at`` = T — the
    START of their unit of work — so by every clock stored they are older than the
    reconciliation, which does not hold them. The reconciliation recorded the chain position it
    read; the posting was sealed after it, whichever of the two wrote first: the gate names both
    reconciliations out of date, and generating them again satisfies it.

    Fail-first (measured on main 5310275d, both variants): the gate named "Billing to subledger"
    alone — its ``as_of_known_at`` was earlier than T — and counted the subledger-to-GL
    reconciliation as reviewed, current, without a variance, two lines short of the ledger."""
    world, maya, priya, january = _january_signers(app, clock, pellworth)
    period_id = UUID(str(january["period"]["id"]))
    balances = _erp_ledger(_journalised(world, clock))
    _billing_reviewed(world, maya, priya)
    assert _january_lines(world, period_id)[0] == 4

    clock.advance(STEP)
    began = clock.now()
    with world.place.uow() as slow:
        assert slow.now == began
        slow.session.execute(select(func.now()))  # the unit of work's transaction has begun
        if written_before:
            _computed_in(slow, world, _progress_of_january())
        clock.advance(STEP)
        ledger = _ledger_reviewed(world, maya, priya, balances)
        # nothing of the posting is committed: the period reads as reconciled
        assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)
        if not written_before:
            _computed_in(slow, world, _progress_of_january())
        slow.commit()

    assert _january_lines(world, period_id) == (6, began)
    assert datetime.fromisoformat(ledger["as_of_known_at"]) > began  # "later" by no clock
    assert _gate(world, period_id) == ("FAILED", 2, BOTH_OUT_OF_DATE, 2, 0)
    assert recon.shown(app, maya, ledger["id"])["status"] == "REVIEWED"  # the row is as it was

    clock.advance(STEP)
    later = _journalised(world, clock)  # the posting, journalised and held by the GL
    balances = {
        code: balances.get(code, Decimal(0)) + later.get(code, Decimal(0))
        for code in {*balances, *later}
    }
    _billing_reviewed(world, maya, priya)
    _ledger_reviewed(world, maya, priya, balances)
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)


def test_an_attach_is_refused_over_a_posting_sealed_after_the_generation(
    app: FastAPI, clock: FrozenClock, pellworth: ReportWorld
) -> None:
    """The subledger side of a subledger-to-GL reconciliation is the lines of the postings sealed
    up to the chain position its generation read. A posting whose unit of work began before the
    generation and committed after it writes lines "recorded" before the reconciliation's
    ``as_of_known_at``; they are sealed after its position, the reconciliation does not hold
    them, and the attach is refused by name. Until the item the attach took such lines for its
    own — recorded at or before ``as_of_known_at`` — whenever they committed."""
    world, maya, _, january = _january_signers(app, clock, pellworth)
    period_id = UUID(str(january["period"]["id"]))
    balances = _erp_ledger(_journalised(world, clock))
    clock.advance(STEP)
    began = clock.now()
    with world.place.uow() as slow:
        slow.session.execute(select(func.now()))
        clock.advance(STEP)
        draft = recon.generated(
            world.app,
            maya,
            world.runtime,
            entity_code="AVM-US",
            period_key=JANUARY,
            kind=recon.SUBLEDGER_TO_GL,
        )
        _computed_in(slow, world, _progress_of_january())
        slow.commit()
    assert _january_lines(world, period_id) == (6, began)
    assert datetime.fromisoformat(draft["as_of_known_at"]) > began

    content = recon.trial_balance_csv([(code, USD, balances[code]) for code in sorted(balances)])
    file_id = recon.uploaded(world.app, maya, "avm-us-tb-2026-01-moved.csv", content)
    started = recon.attach(world.app, maya, draft["id"], {"file_id": file_id})
    assert started.status_code == 202, started.text
    finished = recon.job_run(world.tenant_id, world.runtime, UUID(str(started.json()["id"])))
    assert str(finished["state"]) == "FAILED", finished
    assert finished["problem"]["detail"] == (
        f"2 subledger line(s) were recorded after {draft['reconciliation_no']} was generated. "
        "Generate the reconciliation again."
    )
    assert recon.shown(app, maya, draft["id"])["source_file_id"] is None


def test_a_billing_event_that_writes_no_line_overtakes_both_reconciliations(
    app: FastAPI, clock: FrozenClock, pellworth: ReportWorld
) -> None:
    """V3 and V4. WLD-K-01 keeps ``billing.posting = ERP``: a billing event writes no subledger
    line. One recorded after both reconciliations were reviewed is a document the billing
    reconciliation did not read, and it moves the stored closing contract liability — the
    subledger side of the role's row in the subledger-to-GL reconciliation — by its amount. No
    line and no source invoice says so; the counts each generation recorded do: the gate names
    both out of date. Generated again, the billing reconciliation shows the event as a second
    difference and the ledger one states the contract liability 500.00 further from a ledger
    that does not hold the invoice yet; with the invoice in the ledger it ties.

    A billing event of a LATER period — February's invoice of the same contract — is no document
    of January and moves no balance of 31 January: it leaves January's gate as it is.

    Fail-first (measured before the item): the gate read PASSED, 2 of 2 reviewed, after the
    January event (V3 on main 5310275d for billing to subledger; V4 on the role basis's tree for
    subledger to GL: generated again against the same ledger, −103,930.14 against −103,430.14)."""
    world, maya, priya, january = _january_signers(app, clock, pellworth)
    period_id = UUID(str(january["period"]["id"]))
    balances = _erp_ledger(_journalised(world, clock))
    _billing_reviewed(world, maya, priya)
    _ledger_reviewed(world, maya, priya, balances)
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)

    # --- February's invoice: not January's document, not January's balance ----------------------
    clock.advance(STEP)
    _recorded(world, _invoice("INV-US-1101", "900.00", date(2026, 2, 10)))
    assert _january_lines(world, period_id)[0] == 4
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)

    # --- January's invoice, recorded after the reviews -------------------------------------------
    clock.advance(STEP)
    _recorded(world, _invoice(LATE_NUMBER, str(LATE_AMOUNT), date(2026, 1, 25)))
    assert _january_lines(world, period_id)[0] == 4  # no line was written
    assert _gate(world, period_id) == ("FAILED", 2, BOTH_OUT_OF_DATE, 2, 0)

    # --- generated again -------------------------------------------------------------------------
    clock.advance(STEP)
    billing = recon.generated(
        world.app, maya, world.runtime, entity_code="AVM-US", period_key=JANUARY
    )
    assert sorted(
        (item["item_kind"], item["invoice_number"])
        for item in recon.items_of(world.app, maya, billing["id"])
    ) == [("UNMATCHED_SUBLEDGER", "INV-US-1001"), ("UNMATCHED_SUBLEDGER", LATE_NUMBER)]
    stale = recon.generated(
        world.app,
        maya,
        world.runtime,
        entity_code="AVM-US",
        period_key=JANUARY,
        kind=recon.SUBLEDGER_TO_GL,
    )
    content = recon.trial_balance_csv([(code, USD, balances[code]) for code in sorted(balances)])
    file_id = recon.uploaded(world.app, maya, "avm-us-tb-2026-01-before-the-invoice.csv", content)
    compared = recon.attached(world.app, maya, world.runtime, stale["id"], {"file_id": file_id})
    (liability,) = [
        row for row in compared["totals"] if row["account_role"] == "CONTRACT_LIABILITY"
    ]
    assert compared["variance_count"] == 1
    assert (
        liability["subledger_amount"]["amount"],
        liability["source_amount"]["amount"],
        liability["difference"]["amount"],
    ) == ("-103930.14", "-103430.14", "500.00")

    # --- the ERP posts the invoice too: reviewed again, the gate passes --------------------------
    clock.advance(STEP)
    balances["2100"] -= LATE_AMOUNT
    _billing_reviewed(world, maya, priya)
    _ledger_reviewed(world, maya, priya, balances)
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)


def test_an_event_recorded_before_a_generation_and_computed_after_the_review_overtakes_it(
    app: FastAPI, clock: FrozenClock, pellworth: ReportWorld
) -> None:
    """V5. A January invoice is recorded and its group waits for a computation. Both
    reconciliations are generated and reviewed while it waits. Billing to subledger reads the
    events themselves and shows the invoice. Subledger to GL reads the stored closing balance of
    the contract version known at its ``as_of_known_at`` — and that version, computed before the
    invoice, does not hold it: the contract liability ties to a ledger without the invoice. Then
    the group is computed. No line is written (``billing.posting = ERP``), the pending mark is
    cleared, and the stored contract liability moves by the invoice, in a version that is
    "known" at the record time of its newest event — before the reconciliation.

    The generation counted the event when it was recorded; what it could not count is the
    event's inclusion in a contract version of the book, which did not exist yet. The ledger
    kind's number holds both (``gates.ledger_documents``), so the computation moves it: the gate
    names "Subledger to GL" out of date, and billing to subledger — which read the event —
    stays reviewed. Generated again, the role's row states what the subledger states now.

    Fail-first (measured on the role basis's tree with the count of events alone): the gate read
    PASSED, 2 of 2 reviewed, after the computation; generated again against the same ledger,
    −103,930.14 against −103,430.14, with the same position and the same count."""
    world, maya, priya, january = _january_signers(app, clock, pellworth)
    period_id = UUID(str(january["period"]["id"]))
    balances = _erp_ledger(_journalised(world, clock))
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))

    # --- the invoice is recorded; its group waits for a computation ------------------------------
    clock.advance(STEP)
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    late = _invoice(LATE_NUMBER, str(LATE_AMOUNT), date(2026, 1, 25))
    appended(world.place, contract_id, int(head), [late])
    assert _waits(world, group_id)

    # --- both kinds are generated and reviewed while it waits ------------------------------------
    clock.advance(STEP)
    billing = _billing_reviewed(world, maya, priya)
    assert sorted(
        (item["item_kind"], item["invoice_number"])
        for item in recon.items_of(world.app, maya, billing["id"])
    ) == [("UNMATCHED_SUBLEDGER", "INV-US-1001"), ("UNMATCHED_SUBLEDGER", LATE_NUMBER)]
    ledger = _ledger_reviewed(world, maya, priya, balances)  # ties: the balance of before
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)
    assert _waits(world, group_id)  # NO_DIRTY_GROUPS holds the lock meanwhile

    # --- the computation: no line, and the ledger kind is out of date -----------------------------
    clock.advance(STEP)
    computed(world.place, group_id)
    assert not _waits(world, group_id)
    assert _january_lines(world, period_id)[0] == 4
    assert _gate(world, period_id) == ("FAILED", 1, LEDGER_OUT_OF_DATE, 1, 1)
    assert recon.shown(app, maya, ledger["id"])["status"] == "REVIEWED"  # the row is as it was

    # --- generated again: the role's row states the balance the subledger states now -------------
    clock.advance(STEP)
    again = recon.generated(
        world.app,
        maya,
        world.runtime,
        entity_code="AVM-US",
        period_key=JANUARY,
        kind=recon.SUBLEDGER_TO_GL,
    )
    content = recon.trial_balance_csv([(code, USD, balances[code]) for code in sorted(balances)])
    file_id = recon.uploaded(world.app, maya, "avm-us-tb-2026-01-before-the-invoice.csv", content)
    compared = recon.attached(world.app, maya, world.runtime, again["id"], {"file_id": file_id})
    (liability,) = [
        row for row in compared["totals"] if row["account_role"] == "CONTRACT_LIABILITY"
    ]
    assert compared["variance_count"] == 1
    assert (
        liability["subledger_amount"]["amount"],
        liability["source_amount"]["amount"],
        liability["difference"]["amount"],
    ) == ("-103930.14", "-103430.14", "500.00")

    # --- the ERP posts the invoice too: reviewed again, the gate passes --------------------------
    clock.advance(STEP)
    balances["2100"] -= LATE_AMOUNT
    _ledger_reviewed(world, maya, priya, balances)
    assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)


def test_an_event_recorded_and_computed_while_a_generation_runs_is_not_counted_as_read(
    app: FastAPI,
    clock: FrozenClock,
    pellworth: ReportWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V6. A generation fixes its ``as_of_known_at`` when its transaction begins and counts its
    documents some statements later — after it has waited for the period's row and for another
    generation of its series, if it must. An event recorded and computed in between is committed
    when the generation counts, and carries a record time AFTER the generation's instant; so does
    the contract version computed from it. The attach reads the versions known at or before that
    instant: it does not read this one, and the reconciliation ties on the balance of before.

    A generation therefore counts the rows it will be able to read — recorded, or known, at or
    before its own instant — and the gate counts every row there is: the ledger kind is out of
    date, and generating it again gives the balance the subledger states.

    The case needs the record clock, as under the wall clock: the application instant is not
    ahead of the server's, so a reconciliation's instant is the start of its transaction. Under
    a clock held ahead of the server's every record time lies before every reconciliation, and
    the event would be "known" at the reconciliation's instant whenever it was recorded.

    Fail-first (measured with the generation's count unbounded): the gate read PASSED, 2 of 2
    reviewed, over a contract liability 500.00 from the one the subledger states."""
    world, maya, priya, january = _january_signers(app, clock, pellworth)
    period_id = UUID(str(january["period"]["id"]))
    balances = _erp_ledger(_journalised(world, clock))

    # on_record_clock deliberately starts one second ahead for other close fixtures.
    # This case requires the opposite ordering; do not depend on setup taking a second.
    clock.set(world.place.scalar(select(func.clock_timestamp())))
    assert clock.now() <= world.place.scalar(select(func.clock_timestamp()))

    read_position = reconciliation_domain.chain_position
    recorded: list[str] = []

    def while_the_generation_runs(session: Any, scope: Any) -> int:
        # the generation's transaction has begun and its instant is fixed; nothing is counted yet
        if not recorded:
            recorded.append(LATE_NUMBER)
            _recorded(world, _invoice(LATE_NUMBER, str(LATE_AMOUNT), date(2026, 1, 25)))
        return read_position(session, scope)

    monkeypatch.setattr(reconciliation_domain, "chain_position", while_the_generation_runs)
    ledger = _ledger_reviewed(world, maya, priya, balances)  # ties: the balance of before
    assert recorded == [LATE_NUMBER]
    # Prove the interleaving actually produced a later recorded event, rather than
    # merely obtaining the desired gate result under an accidentally advanced clock.
    recorded_at = world.place.scalar(
        select(contract_event.c.recorded_at).where(
            contract_event.c.contract_id == UUID(str(world.contracts[K01].contract["id"])),
            contract_event.c.event_type == ContractEventType.BILLING_RECORDED.value,
            contract_event.c.payload["invoice_number"].astext == LATE_NUMBER,
        )
    )
    assert recorded_at > datetime.fromisoformat(ledger["as_of_known_at"])
    assert _january_lines(world, period_id)[0] == 4  # the event wrote no line
    # billing to subledger is generated after the event and reads it
    _billing_reviewed(world, maya, priya)
    assert _gate(world, period_id) == ("FAILED", 1, LEDGER_OUT_OF_DATE, 1, 1)
    assert recon.shown(app, maya, ledger["id"])["status"] == "REVIEWED"

    # --- generated again: the balance the subledger states -----------------------------------
    again = recon.generated(
        world.app,
        maya,
        world.runtime,
        entity_code="AVM-US",
        period_key=JANUARY,
        kind=recon.SUBLEDGER_TO_GL,
    )
    content = recon.trial_balance_csv([(code, USD, balances[code]) for code in sorted(balances)])
    file_id = recon.uploaded(world.app, maya, "avm-us-tb-2026-01-before-the-invoice.csv", content)
    compared = recon.attached(world.app, maya, world.runtime, again["id"], {"file_id": file_id})
    (liability,) = [
        row for row in compared["totals"] if row["account_role"] == "CONTRACT_LIABILITY"
    ]
    assert (
        liability["subledger_amount"]["amount"],
        liability["source_amount"]["amount"],
        liability["difference"]["amount"],
    ) == ("-103930.14", "-103430.14", "500.00")


def test_an_event_that_began_before_a_generation_and_committed_after_it_overtakes_it(
    app: FastAPI, clock: FrozenClock, pellworth: ReportWorld
) -> None:
    """The mirror of V6 (the supervisor's word of 2026-10-02 05:34). A January invoice is recorded
    and computed in a unit of work that begins BEFORE both generations and commits after both
    reviews. Its record time — and the instant its contract version is known at — lies before
    each reconciliation's ``as_of_known_at``, so the bound of a generation's count admits it; but
    a generation counts the rows it reads, and it does not read a row that is not committed. The
    row is not in the generation's number and is in the gate's: the gate reads the
    reconciliation short of it and asks for a new generation. The bound cannot let it through —
    it only ever takes rows out of a generation's count.

    Nothing else says so. ``billing.posting = ERP``: the invoice writes no subledger line, so no
    posting is sealed after the position either reconciliation read; and no stored time is later
    than a reconciliation. The gate names both kinds out of date by their numbers. Generated
    again, the contract liability row states the balance the subledger states.

    Fail-first (measured on the item's own build): with the ledger kind's number not recorded the
    gate named "Billing to subledger" alone, and with the billing kind's numbers not recorded
    "Subledger to GL" alone — each kind is caught by its own number and by nothing else."""
    world, maya, priya, january = _january_signers(app, clock, pellworth)
    period_id = UUID(str(january["period"]["id"]))
    balances = _erp_ledger(_journalised(world, clock))
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))

    with world.place.uow() as slow:
        slow.session.execute(select(func.now()))  # the unit of work's transaction has begun
        _computed_in(slow, world, _invoice(LATE_NUMBER, str(LATE_AMOUNT), date(2026, 1, 25)))
        # --- both kinds are generated and reviewed while it is open: neither reads the invoice ---
        billing = _billing_reviewed(world, maya, priya)
        assert [
            item["invoice_number"] for item in recon.items_of(world.app, maya, billing["id"])
        ] == ["INV-US-1001"]
        ledger = _ledger_reviewed(world, maya, priya, balances)  # ties: the balance of before
        assert _gate(world, period_id) == ("PASSED", 0, None, 0, 2)
        slow.commit()

    # --- committed: older than both reconciliations by every clock stored, and without a line ----
    recorded_at = world.place.scalar(
        select(func.max(contract_event.c.recorded_at)).where(
            contract_event.c.contract_id == contract_id
        )
    )
    assert recorded_at < datetime.fromisoformat(billing["as_of_known_at"])
    assert recorded_at < datetime.fromisoformat(ledger["as_of_known_at"])
    assert _january_lines(world, period_id)[0] == 4
    assert not _waits(world, group_id)  # computed in its own unit of work
    assert _gate(world, period_id) == ("FAILED", 2, BOTH_OUT_OF_DATE, 2, 0)
    assert recon.shown(app, maya, ledger["id"])["status"] == "REVIEWED"  # the row is as it was

    # --- generated again: the balance the subledger states -----------------------------------
    again = recon.generated(
        world.app,
        maya,
        world.runtime,
        entity_code="AVM-US",
        period_key=JANUARY,
        kind=recon.SUBLEDGER_TO_GL,
    )
    content = recon.trial_balance_csv([(code, USD, balances[code]) for code in sorted(balances)])
    file_id = recon.uploaded(world.app, maya, "avm-us-tb-2026-01-before-the-invoice.csv", content)
    compared = recon.attached(world.app, maya, world.runtime, again["id"], {"file_id": file_id})
    (liability,) = [
        row for row in compared["totals"] if row["account_role"] == "CONTRACT_LIABILITY"
    ]
    assert (
        liability["subledger_amount"]["amount"],
        liability["source_amount"]["amount"],
        liability["difference"]["amount"],
    ) == ("-103930.14", "-103430.14", "500.00")
