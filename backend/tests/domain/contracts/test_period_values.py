"""A period carries the value in force at its own end, for its own entity (item
PINP-PERIOD-VALUE-1, supervisor ruling of 2026-10-01; POLICIES §0.5 rule 3; 05 RCP-15; dev-guide
DG-KRN-REG-03; 04 T-CON-07).

The finding. The bundle builder resolved every period-pinned parameter once — at the bundle's
``known_at``, for the entity of the member with the earliest inception — and stamped the value on
every period of every entity. POLICIES §0.5 rule 3 lets such a parameter change only from the
first day of a future open period; the builder then handed the changed value to the periods
before it as well. SF-ORD-30201 (O1 30 seats 108,000.00, O2 10 seats 20,000.00, from 1 March 2026)
is posted with an invoice of 12,000.00 on O1 dated 15 March under POL-004 ``billing.posting``
``ERP``. A TENANT version sets ``ENGINE`` from the first day of a later period. At the contract's
next computation after that day all 48 PERIOD rows read ``ENGINE`` and a BILLING intent of
12,000.00 was posted in FY2026-P03: Dr ACCOUNTS_RECEIVABLE, Cr CONTRACT_LIABILITY.

The repair. A period's row carries the value in force for its entity at the earlier of the
bundle's ``known_at`` and the period's last instant in the entity's time zone, among the versions
published at or before ``known_at``; ``pinned_refs.registry_version_ids`` names every version a
row came from, a superseded one included.

Maya (Revenue Accountant) prepares; Marcus (Controller, Tenant Admin; MFA) approves. The frozen
clock starts on 12 September 2026 and is moved to November and December 2029, the last months
of the seat world's calendar (November 2027 in the J-03 world); AVM-US (New York) has FY2026-P01
to P09 open, and in the J-03 world AVM-UK (London) performs one line of an AVM-US contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, job, subledger_line
from erev_api.domain.contracts import bundles
from erev_api.domain.policies.templates import engine_policy_value
from erev_api.enums import BookCode, ContractEventType
from erev_api.events.payloads import BillingRecordedV1, MoneyIn
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.registry import resolve as registry
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine.bundle import InputBundle, OutputBundle
from fastapi import FastAPI
from sqlalchemy import func, select, text
from support.db import TestDatabase
from support.factories import (
    J03World,
    SeatWorld,
    Workspace,
    activated_contract,
    appended,
    booked_contract,
    computed,
    j03_world,
    seat_body,
    seat_line,
    seat_world,
    sf_ord_20417_body,
)
from support.principals import Actor
from support.reference import approve, post

POLICIES = "/api/v1/policies"
BILLING = "billing.posting"  # POL-004: TENANT; framework default ERP; pin P
JE_MODE = "je.posting_mode"  # POL-005: ENTITY, TENANT; framework default GROSS; pin P
# The versions are dated in the last months of the worlds' calendars. A bundle's ``known_at``
# is the later of the application clock and the server's time (``bundles.record_cutoff``), so
# a version dated before the day a test runs is in force from the test's first computation.
NOVEMBER = "2029-11-01T04:00:00Z"  # 1 November 2029, 00:00 in New York: the first day of P11
DECEMBER = "2029-12-01T05:00:00Z"  # 1 December 2029, 00:00 in New York: the first day of P12
NOVEMBER_2027 = "2027-11-01T04:00:00Z"  # the J-03 world's calendar ends with 2027
DEFAULT_BILLING = ("ERP", "DEFAULT", "POL-004")
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


@pytest.fixture
def j03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> J03World:
    return j03_world(app, keyring, clock, files)


def _work(place: Workspace, job_id: str) -> None:
    """The worker fetches the job's task and runs it."""
    runtime = JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files)
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == UUID(job_id))
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(UUID(job_id), place.tenant_id, attempt=1, runtime=runtime)


def published(place: Workspace, approver: Actor, **body: Any) -> str:
    """A registry version created, tested and submitted by the author and approved, so
    published, by ``approver``; its id."""
    app = place.app
    created = post(app, POLICIES, place.author, body)
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    requested = post(app, f"{POLICIES}/{version_id}/test", place.author, {})
    assert requested.status_code == 202, requested.text
    _work(place, str(requested.json()["id"]))
    submitted = post(app, f"{POLICIES}/{version_id}/submit", place.author, {"comment": "Ready"})
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, str(submitted.json()["approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    return version_id


def period_rows(bundle: InputBundle, code: str) -> dict[str, tuple[Any, str, str]]:
    """``<entity>@<period>`` -> (value, level, source) of the parameter in the first book."""
    return {
        policy.subject_key: (policy.value, policy.level, policy.source_ref)
        for policy in bundle.books[0].policies
        if policy.code == code and policy.scope == "PERIOD"
    }


def sources(rows: Mapping[str, tuple[Any, str, str]], entity: str = "AVM-US") -> dict[str, str]:
    """Per source reference, the first and last period key of ``entity`` it answers for."""
    found: dict[str, list[str]] = {}
    for key, (_, _, source) in sorted(rows.items()):
        code, period_key = key.split("@")
        if code == entity:
            found.setdefault(source, []).append(period_key)
    return {source: f"{keys[0]}..{keys[-1]} ({len(keys)})" for source, keys in found.items()}


def intents(output: OutputBundle) -> list[tuple[str, str]]:
    return [
        (intent.posting_period_key, intent.entry_kind)
        for book in output.books
        for intent in book.posting_intents
    ]


def ledger(place: Workspace, contract_id: UUID) -> list[tuple[str, int, Decimal]]:
    line = subledger_line
    rows = place.rows(
        select(
            line.c.account_role,
            func.count().label("lines"),
            func.sum(line.c.amount_txn).label("total"),
        )
        .where(line.c.contract_id == contract_id)
        .group_by(line.c.account_role)
        .order_by(line.c.account_role)
    )
    return [(str(row["account_role"]), int(row["lines"]), row["total"]) for row in rows]


def registry_ids(place: Workspace, bundle: InputBundle, output: OutputBundle) -> set[str]:
    with place.uow() as uow:
        found = bundles.index(uow.session, bundle)
        refs = bundles.pinned_refs(uow.session, bundle, found, output)
    return set(refs["registry_version_ids"])


def invoiced_order(world: SeatWorld) -> tuple[UUID, UUID]:
    """SF-ORD-30201 from 1 March 2026, activated and posted, with an invoice of 12,000.00 on O1
    dated 15 March; contract id and group id."""
    lines = [
        seat_line("O1", seats="30", price="108000.00", start="2026-03-01", end="2029-02-28"),
        seat_line("O2", seats="10", price="20000.00", start="2026-03-01", end="2027-02-28"),
    ]
    body = seat_body(
        world.customers["C-09"], external_id="SF-ORD-30201", inception="2026-03-01", lines=lines
    )
    active = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    contract_id = UUID(str(active.contract["id"]))
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    billed = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 3, 15),
        payload=BillingRecordedV1(
            invoice_number="INV-30201-1",
            line_external_id="1",
            obligation_key="O1",
            amount=MoneyIn(amount="12000.00", currency="USD"),
            issue_date=date(2026, 3, 15),
        ),
        obligation_keys=("O1",),
    )
    appended(world.place, contract_id, int(head), [billed])
    return contract_id, UUID(str(active.combination_group["id"]))


def test_a_value_answers_from_its_first_period_and_its_predecessor_for_the_earlier_ones(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    contract_id, group_id = invoiced_order(seats)
    bundle, output, _ = computed(seats.place, group_id)
    assert set(period_rows(bundle, BILLING).values()) == {DEFAULT_BILLING}
    assert len(period_rows(bundle, BILLING)) == 48
    posted = ledger(seats.place, contract_id)

    # Two versions are published on 12 September 2026: ENGINE from 1 November 2029 and,
    # superseding it, ERP again from 1 December 2029. Neither is in force: no period carries
    # one, and no computation names one.
    first = published(
        seats.place,
        seats.marcus,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={BILLING: "ENGINE"},
        effective_from=NOVEMBER,
    )
    second = published(
        seats.place,
        seats.marcus,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={BILLING: "ERP"},
        effective_from=DECEMBER,
    )
    bundle, output, _ = computed(seats.place, group_id)
    assert set(period_rows(bundle, BILLING).values()) == {DEFAULT_BILLING}
    assert intents(output) == []
    assert {first, second}.isdisjoint(registry_ids(seats.place, bundle, output))

    # 2 November 2029: the first is in force. November and December carry it — the successor
    # is known and takes effect later — and March 2026 keeps ERP, so the invoice of 15 March
    # posts nothing. Before the repair all 48 rows read ENGINE and a BILLING intent of 12,000.00
    # was posted in FY2026-P03.
    clock.set(datetime(2029, 11, 2, 12, tzinfo=UTC))
    bundle, output, _ = computed(seats.place, group_id)
    rows = period_rows(bundle, BILLING)
    assert sources(rows) == {
        "POL-004": "FY2026-P01..FY2029-P10 (46)",
        first: "FY2029-P11..FY2029-P12 (2)",
    }
    assert rows["AVM-US@FY2026-P03"] == DEFAULT_BILLING
    assert rows["AVM-US@FY2029-P11"] == ("ENGINE", "T", first)
    assert intents(output) == []
    assert ledger(seats.place, contract_id) == posted
    found = registry_ids(seats.place, bundle, output)
    assert first in found and second not in found

    # 2 December 2029: the successor is in force. November keeps the first version, which is
    # superseded and no longer in force, and the computation names both.
    clock.set(datetime(2029, 12, 2, 12, tzinfo=UTC))
    bundle, output, _ = computed(seats.place, group_id)
    rows = period_rows(bundle, BILLING)
    assert sources(rows) == {
        "POL-004": "FY2026-P01..FY2029-P10 (46)",
        first: "FY2029-P11..FY2029-P11 (1)",
        second: "FY2029-P12..FY2029-P12 (1)",
    }
    assert rows["AVM-US@FY2029-P12"] == ("ERP", "T", second)
    assert intents(output) == []
    assert ledger(seats.place, contract_id) == posted
    assert {first, second} <= registry_ids(seats.place, bundle, output)


def test_a_value_a_successor_carries_forward_answers_from_the_successor(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    """The whole value set through the period rows (04 T-PLT-32 "Whole value set" rev 1.183; the
    lane's join with item REG-VERSION-WHOLE-SET-1). A version past TESTED holds every value of its
    category at its scope key, so the successor of a version that states POL-005 holds it too,
    though it states POL-004 alone. Each period's row names the version in force at the period's
    own end: November the first version, December its successor — with the value the first one
    stated. Resolution reads one version a level and never looks behind it; without the whole set
    December would have read the framework default."""
    _, group_id = invoiced_order(seats)
    first = published(
        seats.place,
        seats.marcus,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={BILLING: "ENGINE", JE_MODE: "DELTA"},
        effective_from=NOVEMBER,
    )
    second = published(
        seats.place,
        seats.marcus,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={BILLING: "ERP"},
        effective_from=DECEMBER,
    )
    clock.set(datetime(2029, 12, 2, 12, tzinfo=UTC))
    with seats.place.uow() as uow:
        bundle = bundles.build(uow.session, group_id, uow.now)
    rows = period_rows(bundle, JE_MODE)
    assert sources(rows) == {
        "POL-005": "FY2026-P01..FY2029-P10 (46)",
        first: "FY2029-P11..FY2029-P11 (1)",
        second: "FY2029-P12..FY2029-P12 (1)",
    }
    assert rows["AVM-US@FY2029-P11"] == ("DELTA", "T", first)
    assert rows["AVM-US@FY2029-P12"] == ("DELTA", "T", second)  # carried forward, not restated
    billing = period_rows(bundle, BILLING)
    assert billing["AVM-US@FY2029-P11"] == ("ENGINE", "T", first)
    assert billing["AVM-US@FY2029-P12"] == ("ERP", "T", second)


def test_an_entitys_version_answers_for_that_entitys_periods_only(
    j03: J03World, clock: FrozenClock
) -> None:
    """SF-ORD-20417 is AVM-US's contract with one line performed by AVM-UK, so its bundle holds
    both entities. A version of AVM-UK answers for AVM-UK's periods from its date on, and AVM-US
    keeps the framework default. Before the repair every row was resolved for AVM-US, the
    contracting entity, and AVM-UK's own version reached no period."""
    booked = booked_contract(j03.place, sf_ord_20417_body(j03.customer_id), activate=False)
    group_id = UUID(str(booked.combination_group["id"]))
    with j03.place.uow() as uow:
        bundle = bundles.build(uow.session, group_id, uow.now)
    assert [entity.code for entity in bundle.entities] == ["AVM-UK", "AVM-US"]
    default = ("GROSS", "DEFAULT", "POL-005")
    assert set(period_rows(bundle, JE_MODE).values()) == {default}

    uk = published(
        j03.place,
        j03.marcus,
        category="ACCOUNTING_POLICY",
        scope="ENTITY",
        entity_code="AVM-UK",
        values={JE_MODE: "DELTA"},
        effective_from=NOVEMBER_2027,
    )
    clock.set(datetime(2027, 11, 2, 12, tzinfo=UTC))
    with j03.place.uow() as uow:
        bundle = bundles.build(uow.session, group_id, uow.now)
    rows = period_rows(bundle, JE_MODE)
    of_uk = sources(rows, "AVM-UK")
    assert of_uk == {"POL-005": "FY2026-P01..FY2027-P10 (22)", uk: "FY2027-P11..FY2027-P12 (2)"}
    assert rows["AVM-UK@FY2027-P10"] == default
    assert rows["AVM-UK@FY2027-P11"] == ("DELTA", "E", uk)
    assert {value for key, value in rows.items() if key.startswith("AVM-US@")} == {default}


def test_a_contract_computed_with_a_stamped_value_is_corrected_at_its_next_computation(
    seats: SeatWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the repair does to a contract that was computed before it. The state before the
    repair is reproduced for ONE computation — every period read at ``known_at`` — and posts the
    BILLING entry of 12,000.00 into March; the next computation, as built, hands March its own
    value again and posts the entry back: the receivable returns to 0.00 and the contract
    liability to its amount, as the differences of a re-run do (05 RCP-04, RCP-15)."""
    contract_id, group_id = invoiced_order(seats)
    computed(seats.place, group_id)
    posted = ledger(seats.place, contract_id)
    assert [role for role, _, _ in posted] == ["REVENUE", "CONTRACT_LIABILITY"]
    first = published(
        seats.place,
        seats.marcus,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={BILLING: "ENGINE"},
        effective_from=NOVEMBER,
    )
    clock.set(datetime(2029, 11, 2, 12, tzinfo=UTC))
    with monkeypatch.context() as before_the_repair:
        far = datetime.max.replace(tzinfo=UTC)
        before_the_repair.setattr(bundles, "period_end_instant", lambda end_date, time_zone: far)
        bundle, output, _ = computed(seats.place, group_id)
    assert sources(period_rows(bundle, BILLING)) == {first: "FY2026-P01..FY2029-P12 (48)"}
    assert intents(output) == [("FY2026-P03", "BILLING")]
    stamped = {role: total for role, _, total in ledger(seats.place, contract_id)}
    assert stamped["ACCOUNTS_RECEIVABLE"] == Decimal("12000.00")

    clock.set(datetime(2029, 11, 2, 13, tzinfo=UTC))
    bundle, output, _ = computed(seats.place, group_id)
    assert sources(period_rows(bundle, BILLING)) == {
        "POL-004": "FY2026-P01..FY2029-P10 (46)",
        first: "FY2029-P11..FY2029-P12 (2)",
    }
    assert intents(output) == [("FY2026-P03", "BILLING")]
    corrected = {role: total for role, _, total in ledger(seats.place, contract_id)}
    assert corrected["ACCOUNTS_RECEIVABLE"] == Decimal("0.00")
    before = {role: total for role, _, total in posted}
    assert {role: corrected[role] for role in before} == before


def test_the_rows_of_the_running_period_are_the_registrys_answer_at_known_at(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    """For the period that holds ``known_at`` and every later one, the row of each period-pinned
    parameter is what ``registry.resolve`` answers at ``known_at`` for the period's entity: the
    in-memory reading of the versions and the registry's own query agree."""
    _, group_id = invoiced_order(seats)
    published(
        seats.place,
        seats.marcus,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={BILLING: "ENGINE", JE_MODE: "DELTA"},
        effective_from=NOVEMBER,
    )
    published(
        seats.place,
        seats.marcus,
        category="ACCOUNTING_POLICY",
        scope="ENTITY",
        entity_code="AVM-US",
        values={JE_MODE: "GROSS"},
        effective_from=DECEMBER,
    )
    for moment in (datetime(2029, 11, 2, 12, tzinfo=UTC), datetime(2029, 12, 2, 12, tzinfo=UTC)):
        clock.set(moment)
        with seats.place.uow() as uow:
            bundle = bundles.build(uow.session, group_id, uow.now)
            (entity,) = bundle.entities
            running = [
                item.period_key
                for item in entity.periods
                if bundles.period_end_instant(item.end_date, entity.time_zone) >= bundle.known_at
            ]
            assert running[0] == f"FY2029-P{moment.month:02d}"
            compared = 0
            for code, spec in sorted(POLICY_PARAMETERS.items()):
                if spec.pin != "P":
                    continue
                answer = registry.resolve(
                    uow.session,
                    code,
                    book_code=BookCode.ASC606,
                    entity_id=seats.entity_id,
                    known_at=bundle.known_at,
                )
                rows = period_rows(bundle, code)
                for period_key in running:
                    row = rows.get(f"{entity.code}@{period_key}")
                    if answer.value is None:
                        assert row is None, (code, period_key)
                        continue
                    assert row is not None, (code, period_key)
                    source = spec.source_ref if answer.source_id is None else str(answer.source_id)
                    expected = (engine_policy_value(answer.value), answer.level, source)
                    assert row == expected, (code, period_key)
                    compared += 1
            assert compared >= len(running) * 40
