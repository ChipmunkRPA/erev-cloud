"""CLO-8 journal run calculation (ENGINE_SPEC_B §14.3 S14-R-16 to S14-R-24; 04 T-SL-06 to T-SL-09,
§16.7; 05 RCP-27; POLICIES CHK-020, CHK-022; legacy 06 TC-JE-01, TC-JE-02; BUILD_SPEC CLO-8).

World: ``support.worlds.journal_world`` (golden steps 01 to 03 replayed under ``LEGACY_PARITY`` in a
fresh tenant, with the CHK-022 and CHK-020 engine intents posted through ``subledger.post``;
L6-3-Q-1). Maya (Revenue Accountant) requests the runs through ``POST /journal-runs``, and the
``JOURNAL_RUN_CALCULATE`` job runs as the worker runs it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_hold,
    journal_batch,
    journal_entry,
    journal_run,
    tenant,
)
from erev_api.domain.contracts import holds
from erev_api.domain.journals import summarise
from erev_api.enums import JournalRunGrain, PrincipalKind
from erev_api.files.store import LocalFileStore, open_file
from erev_api.main import create_app
from erev_api.schemas.events import HoldApplyIn, HoldReleaseIn
from fastapi import FastAPI
from sqlalchemy import select, update
from support.db import TestDatabase
from support.reference import get, post
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    FEBRUARY,
    JANUARY,
    JOURNAL_RUNS,
    JournalWorld,
    by_account,
    calculated_run,
    journal_world,
    post_chk_022,
    post_lines,
    post_pre_standard,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> Iterator[JournalWorld]:
    built = journal_world(app, keyring, clock, files)
    post_chk_022(built)
    yield built


def _entries(world: JournalWorld, run_id: str) -> list[dict[str, object]]:
    return world.legacy.imports.rows(
        select(
            journal_entry.c.je_seq,
            journal_entry.c.je_no,
            journal_entry.c.entry_kind,
            journal_entry.c.is_post_close,
        )
        .select_from(
            journal_entry.join(
                journal_batch, journal_batch.c.id == journal_entry.c.journal_batch_id
            )
        )
        .where(journal_batch.c.journal_run_id == UUID(run_id))
        .order_by(journal_entry.c.je_seq)
    )


def test_gross_run_january_2023_chk_022(world: JournalWorld) -> None:
    first, lines_1 = calculated_run(world, entity=ENTITY_1)
    assert by_account(lines_1) == [
        ("21001", "295.69", "0.00"),
        ("5001", "0.00", "128.84"),
        ("5002", "0.00", "118.53"),
        ("5003", "0.00", "48.32"),
    ]
    assert (
        first["totals"]["debit_functional"]["amount"],
        first["totals"]["credit_functional"]["amount"],
    ) == (
        "295.69",
        "295.69",
    )
    revenue = {
        item["account"]["code"]: item["legacy_key"]
        for item in lines_1
        if item["account_role"] == "REVENUE"
    }
    assert revenue == {
        "5001": "Contract 1 POB #1 Hardware 1",
        "5002": "Contract 1 POB #2 Software 1",
        "5003": "Contract 1 POB #3 Consulting 1",
    }
    assert {item["contract"]["external_id"] for item in lines_1} == {"Contract 1"}

    second, lines_2 = calculated_run(world, entity=ENTITY_2)
    # S14-R-18: 21002 nets to 0 across the relief and the JET-06 reclass, so no 21002 line.
    assert by_account(lines_2) == [("15002", "58.85", "0.00"), ("5001", "0.00", "58.85")]
    for run in (first, second):
        assert (run["state"], run["mode"], run["grain"], run["delta_book"]) == (
            "draft",
            "GROSS",
            "LEGACY_CONTRACT_POB",
            None,
        )
        assert run["totals"]["balanced"] is True
        (batch,) = run["batches"]
        assert batch["total_debit_txn"] == batch["total_credit_txn"]
    assert first["je_range"] == {
        "first_je_no": "JE-Mock Entity 1-000001",
        "last_je_no": "JE-Mock Entity 1-000001",
        "count": 1,
    }
    assert second["je_range"] == {
        "first_je_no": "JE-Mock Entity 2-000001",
        "last_je_no": "JE-Mock Entity 2-000001",
        "count": 1,
    }
    (mixed,) = _entries(world, second["id"])
    assert (
        mixed["entry_kind"] is None
    )  # REVENUE_RECOGNITION and NETTING_RECLASS in one entry (L6-3-Q-3)


def test_delta_run_january_2023_chk_020(world: JournalWorld) -> None:
    post_pre_standard(world)
    first, lines_1 = calculated_run(world, entity=ENTITY_1, mode="DELTA")
    assert by_account(lines_1) == [
        ("21001", "141.69", "0.00"),
        ("5001", "0.00", "128.84"),
        ("5002", "0.00", "52.53"),
        ("5003", "39.68", "0.00"),
    ]
    second, lines_2 = calculated_run(world, entity=ENTITY_2, mode="DELTA")
    assert by_account(lines_2) == [("15002", "58.85", "0.00"), ("5001", "0.00", "58.85")]
    for run in (first, second):
        assert (run["mode"], run["delta_book"]) == ("DELTA", "LEGACY")
        assert run["coverage"]["delta_from_chain_seq"] == 0
        assert run["coverage"]["delta_to_chain_seq"] >= 1
        (batch,) = run["batches"]
        assert batch["total_debit_txn"] == batch["total_credit_txn"]
        assert batch["total_debit_functional"] == batch["total_credit_functional"]
    assert first["totals"]["debit_functional"]["amount"] == "181.37"


def _net_by_account(*runs: list[tuple[str, str, str]]) -> dict[str, Decimal]:
    """Account code -> debit less credit over the ``by_account`` lines of the given runs; an
    account that nets to zero is left out."""
    net: dict[str, Decimal] = {}
    for lines in runs:
        for code, debit, credit in lines:
            net[code] = net.get(code, Decimal("0")) + Decimal(debit) - Decimal(credit)
    return {code: amount for code, amount in sorted(net.items()) if amount}


# CHK-020 (POLICIES JET-15): the January 2023 adjustment journal of Mock Entity 1, as nets.
CHK_020_ENTITY_1 = {
    "21001": Decimal("141.69"),
    "5001": Decimal("-128.84"),
    "5002": Decimal("-52.53"),
    "5003": Decimal("39.68"),
}


def test_sc_7_delta_run_never_journalises_seals_a_gross_run_covered(world: JournalWorld) -> None:
    """Security finding SC-7 (supervisor ruling R-32; 04 DB-16 rev 1.106, revision 0085). While the
    coverage key held the mode, a DELTA run beside a GROSS run of one entity, book and period
    started at chain sequence 0 again and journalised the same 295.69 a second time (the reviewer's
    PoC). A run of either mode now starts where the key's non-cancelled runs end: the DELTA run
    carries the LEGACY lines alone, and GROSS plus DELTA is the one adjustment journal of CHK-020.
    Positive control: once both runs are cancelled their ranges are covered again, and a single
    DELTA run is CHK-020 in full."""
    post_pre_standard(world)
    gross, gross_lines = calculated_run(world, entity=ENTITY_1)
    assert gross["totals"]["debit_functional"]["amount"] == "295.69"
    covered = gross["coverage"]["to_chain_seq"]
    assert gross["coverage"]["from_chain_seq"] == 0 and covered >= 1

    delta, delta_lines = calculated_run(world, entity=ENTITY_1, mode="DELTA")
    assert (delta["mode"], delta["delta_book"]) == ("DELTA", "LEGACY")
    # No primary-book seal is journalised again: the DELTA run's primary range is empty ...
    assert (delta["coverage"]["from_chain_seq"], delta["coverage"]["to_chain_seq"]) == (
        covered,
        covered,
    )
    # ... and it holds the LEGACY lines of CHK-020 only (pre-standard revenue 66.00 and 88.00).
    assert by_account(delta_lines) == [
        ("21001", "0.00", "154.00"),
        ("5002", "66.00", "0.00"),
        ("5003", "88.00", "0.00"),
    ]
    assert delta["coverage"]["delta_from_chain_seq"] == 0
    assert delta["coverage"]["delta_to_chain_seq"] >= 1
    assert delta["totals"]["debit_functional"]["amount"] == "154.00"
    assert delta["totals"]["balanced"] is True
    # What reaches the general ledger from the two runs together is the adjustment journal once.
    assert _net_by_account(by_account(gross_lines), by_account(delta_lines)) == CHK_020_ENTITY_1

    # A third run of either mode finds nothing left to journalise, and none is made: 409 by the
    # latest run's number (PRD ERR-96; item JRN-EMPTY-RUN-1). Until that item a run without a
    # line was calculated here, its coverage starting at ``covered``.
    for mode in ("GROSS", "DELTA"):
        body = {
            "entity_code": ENTITY_1,
            "period_key": JANUARY,
            "grain": "LEGACY_CONTRACT_POB",
            "mode": mode,
        }
        again = post(world.app, JOURNAL_RUNS, world.legacy.maya, body)
        assert again.status_code == 409, (mode, again.text)
        assert again.json()["errors"][0]["rule_id"] == "RUN_NOTHING_PENDING", mode
        named = f"Journal run {delta['run_no']} is the latest run of "
        assert again.json()["detail"].startswith(named), mode

    # Positive control (DB-16: a cancelled run's range is covered again): with every run of the key
    # cancelled, one DELTA run journalises the period from 0 and is CHK-020 in full.
    runs = world.legacy.imports.rows(
        select(journal_run.c.id, journal_run.c.state, journal_run.c.entity_id, journal_run.c.run_no)
    )
    entity_1 = world.entities[ENTITY_1]
    # Ruling R-52 (b) (CLO-14): a run is cancelled only while no later run of its key stands, so
    # the runs are cancelled newest first (T-PLT-26: a longer number is a later one).
    for row in sorted(runs, key=lambda item: (len(item["run_no"]), item["run_no"]), reverse=True):
        if row["entity_id"] != entity_1:
            continue
        cancelled = post(
            world.app,
            f"{JOURNAL_RUNS}/{row['id']}/cancel",
            world.legacy.maya,
            {"reason": "Recalculate as one adjustment journal (SC-7 witness)."},
        )
        assert cancelled.status_code == 200, cancelled.text
    single, single_lines = calculated_run(world, entity=ENTITY_1, mode="DELTA")
    assert single["coverage"]["from_chain_seq"] == 0
    assert single["coverage"]["delta_from_chain_seq"] == 0
    assert by_account(single_lines) == [
        ("21001", "141.69", "0.00"),
        ("5001", "0.00", "128.84"),
        ("5002", "0.00", "52.53"),
        ("5003", "39.68", "0.00"),
    ]
    assert _net_by_account(by_account(single_lines)) == CHK_020_ENTITY_1


def test_default_grain_and_drill(world: JournalWorld) -> None:
    run, lines = calculated_run(
        world, entity=ENTITY_1, grain="ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"
    )
    assert by_account(lines) == [
        ("21001", "295.69", "0.00"),
        ("5001", "0.00", "128.84"),
        ("5002", "0.00", "118.53"),
        ("5003", "0.00", "48.32"),
    ]
    assert {item["contract"] is None for item in lines} == {True}
    maya = world.legacy.maya
    (revenue,) = [item for item in lines if item["account"]["code"] == "5001"]
    drilled = get(world.app, revenue["links"]["drill"], maya)
    assert drilled.status_code == 200, drilled.text
    amounts = [Decimal(item["amount_txn"]["amount"]) for item in drilled.json()["items"]]
    assert (len(amounts), sum(amounts)) == (1, Decimal("-128.84"))
    (liability,) = [item for item in lines if item["account"]["code"] == "21001"]
    drilled = get(world.app, liability["links"]["drill"], maya)
    assert drilled.status_code == 200, drilled.text
    items = drilled.json()["items"]
    assert (len(items), sum(Decimal(item["amount_txn"]["amount"]) for item in items)) == (
        3,
        Decimal("295.69"),
    )
    assert run["grain"] == "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"


def test_contract_grain_sets_contract(world: JournalWorld) -> None:
    _, lines = calculated_run(world, entity=ENTITY_1, grain="CONTRACT_ACCOUNT_DIMENSIONS")
    assert by_account(lines)[0] == ("21001", "295.69", "0.00")
    assert [item["contract"]["id"] for item in lines] == [str(world.contracts["Contract 1"].id)] * 4


def test_batch_per_currency_and_external_id(world: JournalWorld) -> None:
    run, _ = calculated_run(world, entity=ENTITY_1)
    (batch,) = run["batches"]
    tenant_code = world.legacy.imports.scalar(
        select(tenant.c.code).where(tenant.c.id == world.legacy.tenant_id)
    )
    assert batch["external_id"] == f"erev:{tenant_code}:{run['run_no']}:1:1"
    assert (batch["batch_no"], batch["chunk_no"], batch["txn_currency"]) == (1, 1, "USD")
    shown = get(world.app, f"/api/v1/journal-batches/{batch['id']}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    detail_id, detail_sha = shown.json()["detail_file_id"], shown.json()["detail_sha256"]
    assert detail_id is not None and len(detail_sha) == 64
    runtime = world.legacy.imports.runtime
    assert runtime.keyring is not None and runtime.files is not None
    context = DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        _, stream = open_file(
            session, UUID(detail_id), files=runtime.files, keyring=runtime.keyring
        )
        document = json.loads(stream.read())
    assert (document["external_id"], len(document["lines"]), document["held"]) == (
        batch["external_id"],
        4,
        [],
    )

    # S14-R-21: one batch per transaction currency, in currency order.
    def line(
        currency: str, account: str, amount: str, role: str = "REVENUE"
    ) -> summarise.DetailLine:
        return summarise.DetailLine(
            id=UUID(int=len(currency + account + amount)),
            book_code="ASC606",
            sign=1,
            chain_seq=1,
            posting_kind="ENGINE_COMPUTE",
            entry_kind="REVENUE_RECOGNITION",
            account_role=role,
            gl_account_id=UUID(int=int(account)),
            gl_account_code=account,
            dimensions={},
            txn_currency=currency,
            amount_txn=Decimal(amount),
            functional_currency="USD",
            amount_functional=Decimal(amount),
        )

    planned = summarise.plan_batches(
        [
            line("USD", "21001", "10.00", "CONTRACT_LIABILITY"),
            line("USD", "5001", "-10.00"),
            line("EUR", "21001", "20.00", "CONTRACT_LIABILITY"),
            line("EUR", "5001", "-20.00"),
        ],
        grain=JournalRunGrain.ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS,
        dimension_codes=frozenset(),
    )
    assert [(currency, len(summary), len(plans)) for currency, summary, plans in planned] == [
        ("EUR", 2, 1),
        ("USD", 2, 1),
    ]


def test_je_numbers_gapless_per_entity(world: JournalWorld) -> None:
    january, _ = calculated_run(world, entity=ENTITY_1)
    post_lines(
        world,
        key="february-contract-1",
        contract_key="Contract 1",
        period_key=FEBRUARY,
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "10.00", "POB #1"),
                    ("REVENUE", "5001", "-10.00", "POB #1"),
                ],
            ),
            (
                "BILLING",
                [
                    ("ACCOUNTS_RECEIVABLE", "1100", "50.00", None),
                    ("CONTRACT_LIABILITY", "2100", "-50.00", None),
                ],
            ),
        ],
    )
    february, _ = calculated_run(world, entity=ENTITY_1, period_key=FEBRUARY)
    assert january["je_range"] == {
        "first_je_no": "JE-Mock Entity 1-000001",
        "last_je_no": "JE-Mock Entity 1-000001",
        "count": 1,
    }
    assert february["je_range"] == {
        "first_je_no": "JE-Mock Entity 1-000002",
        "last_je_no": "JE-Mock Entity 1-000003",
        "count": 2,
    }
    numbers = [
        (item["je_seq"], item["je_no"])
        for item in [*_entries(world, january["id"]), *_entries(world, february["id"])]
    ]
    assert numbers == [
        (1, "JE-Mock Entity 1-000001"),
        (2, "JE-Mock Entity 1-000002"),
        (3, "JE-Mock Entity 1-000003"),
    ]


def test_journal_export_hold_excludes_lines(world: JournalWorld, clock: FrozenClock) -> None:
    held_contract = world.contracts["Contract 1"]
    others = [
        item
        for key, item in world.contracts.items()
        if key != "Contract 1" and item.entity_id == held_contract.entity_id
    ]
    assert others, "the parity world keeps a second contract of Mock Entity 1"
    other = others[0]
    post_lines(
        world,
        key="hold-other-contract",
        contract_key=other.external_id,
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "12.00", "POB #1"),
                    ("REVENUE", "5001", "-12.00", "POB #1"),
                ],
            )
        ],
    )
    place = world.legacy.place()

    def head() -> int:
        return int(
            world.legacy.imports.scalar(
                select(contract.c.head_stream_version).where(contract.c.id == held_contract.id)
            )
        )

    with place.uow() as uow:
        holds.apply_hold(
            uow,
            contract_id=held_contract.id,
            expected_stream_version=head(),
            body=HoldApplyIn(
                hold_type="journal_export", reason="Customer dispute on invoice INV-C1"
            ),
        )
        uow.commit()
    held_run, lines = calculated_run(world, entity=ENTITY_1)
    assert by_account(lines) == [("21001", "12.00", "0.00"), ("5001", "0.00", "12.00")]
    (batch,) = held_run["batches"]
    runtime = world.legacy.imports.runtime
    assert runtime.keyring is not None and runtime.files is not None
    context = DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        _, stream = open_file(
            session, UUID(batch["detail_file_id"]), files=runtime.files, keyring=runtime.keyring
        )
        document = json.loads(stream.read())
    assert {item["contract_id"] for item in document["held"]} == {str(held_contract.id)}
    assert len(document["held"]) == 6

    hold_id = world.legacy.imports.scalar(
        select(contract_hold.c.id).where(contract_hold.c.contract_id == held_contract.id)
    )
    clock.advance(timedelta(minutes=5))
    with place.uow() as uow:
        holds.release_hold(
            uow,
            contract_id=held_contract.id,
            expected_stream_version=head(),
            body=HoldReleaseIn(hold_id=hold_id, comment="Dispute settled"),
        )
        uow.commit()
    with tenant_session(context) as session:
        session.execute(
            update(journal_run)
            .where(journal_run.c.id == UUID(held_run["id"]))
            .values(
                state="cancelled",
                cancelled_at=clock.now(),
                updated_by_kind=PrincipalKind.SYSTEM.value,
            )
        )
    recalculated, lines = calculated_run(world, entity=ENTITY_1)
    assert recalculated["coverage"]["from_chain_seq"] == 0
    # LEGACY_CONTRACT_POB keys liabilities by contract and revenue by legacy key, so each contract
    # keeps its own lines.
    assert by_account(lines) == [
        ("21001", "12.00", "0.00"),
        ("21001", "295.69", "0.00"),
        ("5001", "0.00", "12.00"),
        ("5001", "0.00", "128.84"),
        ("5002", "0.00", "118.53"),
        ("5003", "0.00", "48.32"),
    ]


def test_conversion_residue_rounding_line() -> None:
    lines = [
        (Decimal("10.00"), Decimal("0")),
        (Decimal("0"), Decimal("3.33")),
        (Decimal("0"), Decimal("3.33")),
        (Decimal("0"), Decimal("3.34")),
    ]
    converted = summarise.convert_batch(lines, rate=Decimal("1.005"), currency="EUR", minor_unit=2)
    assert converted.lines == (
        (Decimal("10.05"), Decimal("0.00")),
        (Decimal("0.00"), Decimal("3.35")),
        (Decimal("0.00"), Decimal("3.35")),
        (Decimal("0.00"), Decimal("3.36")),
    )
    assert converted.rounding == (Decimal("0.01"), Decimal("0"))
    debits = sum(debit for debit, _ in converted.lines) + converted.rounding[0]
    credits = sum(credit for _, credit in converted.lines) + converted.rounding[1]
    assert debits == credits == Decimal("10.06")
    exact = summarise.convert_batch(lines, rate=Decimal("2"), currency="EUR", minor_unit=2)
    assert exact.rounding is None
    yen = summarise.convert_batch(
        [
            (Decimal("1.00"), Decimal("0")),
            (Decimal("0"), Decimal("0.50")),
            (Decimal("0"), Decimal("0.50")),
        ],
        rate=Decimal("150.5"),
        currency="JPY",
        minor_unit=0,
    )
    # 150.5 → 151 (half up), 75.25 → 75 twice: one ROUNDING credit of 1 balances the batch.
    assert (yen.lines, yen.rounding) == (
        (
            (Decimal("151"), Decimal("0")),
            (Decimal("0"), Decimal("75")),
            (Decimal("0"), Decimal("75")),
        ),
        (Decimal("0"), Decimal("1")),
    )


def test_post_close_flag(world: JournalWorld) -> None:
    january, _ = calculated_run(world, entity=ENTITY_1)
    post_lines(
        world,
        key="late-contract-1",
        contract_key="Contract 1",
        period_key=FEBRUARY,
        origin_key=JANUARY,
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "7.00", "POB #1"),
                    ("REVENUE", "5001", "-7.00", "POB #1"),
                ],
            )
        ],
    )
    february, lines = calculated_run(world, entity=ENTITY_1, period_key=FEBRUARY)
    assert {item["is_post_close"] for item in lines} == {True}
    assert {item["origin_period_key"] for item in lines} == {JANUARY}
    assert [item["is_post_close"] for item in _entries(world, february["id"])] == [True]
    assert [item["is_post_close"] for item in _entries(world, january["id"])] == [False]
