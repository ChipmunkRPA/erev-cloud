"""Reverse drill from a journal line to its source file row (05 RCP-27; 04 API-R-38
``GET /journal-lines/{id}/drill``, API-S-SubledgerLine ``links``, API-R-26 ``GET /events/{id}`` and
API-S-Event ``source_row``, API-R-43 ``GET /imports/{id}/rows``; T-SL-06 drill-back, T-IMP-04
lineage; 03 REQ-RPT-017; BUILD_SPEC RPS-17).

World: ``support.worlds.journal_world`` (CLO-8): golden steps 01 to 03 replayed through the legacy
v1 import pipeline, so each contract event of Mock Entity 1 carries its import row lineage.

[J] L7-2-Q-19: the platform replay posts no subledger lines yet (L6-3-Q-1), so the test seals one
``ENGINE_COMPUTE`` posting of Contract 1 for January 2023 whose lines name the imported
``CONTRACT_BOOKED`` event, as a computed line names its source event (``computation.persist``), then
calculates the journal run of Mock Entity 1 as the worker does.

API-S-SubledgerLine ``contract_external_id`` (04 rev 1.159; supervisor ruling of 2026-10-01 on the
e2e row ``SF-06:run-lines``): the drill's rows name the contract of each line, so a reader makes
no read per contract; the second test holds the member, its order and the route's statement count.

API-S-SubledgerLine ``obligation_key`` (04 rev 1.245; register index 182; the supervisor's ruling
of 2026-10-01): the rows name the obligation of each line as they name its contract, joined
through the contract's row, so the key is null wherever the contract's name is; the third test
holds the member, and what API-S-JournalLine answers the reader to whom both are null.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_event
from erev_api.domain.journals import subledger
from erev_api.enums import SubledgerPostingKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import Engine, event, select
from support.db import TestDatabase
from support.principals import Actor, colleague
from support.reference import get, holding, slug
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    FEBRUARY,
    JANUARY,
    JournalWorld,
    calculated_run,
    journal_world,
    post_lines,
)

API: Final = "/api/v1"
CONTRACT: Final = "Contract 1"
OBLIGATION: Final = "POB #1"
DEFAULT_GRAIN: Final = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _booked_event(world: JournalWorld) -> UUID:
    found = world.contracts[CONTRACT]
    (row,) = world.legacy.imports.rows(
        select(contract_event.c.id).where(
            contract_event.c.contract_id == found.id,
            contract_event.c.event_type == "CONTRACT_BOOKED",
        )
    )
    return UUID(str(row["id"]))


def _post_revenue(world: JournalWorld, event_id: UUID) -> None:
    """Dr contract liability 21001 / Cr revenue 5001 of POB #1, 100.00 USD, naming the event."""
    found = world.contracts[CONTRACT]
    period_id, period_end = world.periods[JANUARY]
    obligation_id, legacy_key = found.obligations[OBLIGATION]
    dimensions = {"contract_key": CONTRACT, "obligation_key": OBLIGATION}
    lines: list[dict[str, Any]] = [
        {
            "period_end_date": period_end,
            "entity_id": found.entity_id,
            "period_id": period_id,
            "origin_period_id": None,
            "reason_code": None,
            "effective_date": period_end,
            "entry_no": 1,
            "entry_kind": "REVENUE_RECOGNITION",
            "account_role": role,
            "clearing_purpose": None,
            "gl_account_id": world.accounts[account],
            "dimensions": dimensions,
            "dimension_set_sha256": subledger.dimension_set_sha256(dimensions),
            "txn_currency": "USD",
            "amount_txn": Decimal(amount),
            "functional_currency": "USD",
            "amount_functional": Decimal(amount),
            "contract_id": found.id,
            "obligation_id": obligation_id,
            "contract_event_id": event_id,
            "legacy_key": legacy_key if role == "REVENUE" else CONTRACT,
        }
        for role, account, amount in (
            ("CONTRACT_LIABILITY", "21001", "100.00"),
            ("REVENUE", "5001", "-100.00"),
        )
    ]
    with world.legacy.place().uow() as uow:
        subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key="rps-17:drill-chain",
            description="RPS-17 drill chain probe",
            lines=lines,
            combination_group_id=found.group_id,
            contract_computation_id=found.computation_id,
        )
        uow.commit()


@pytest.mark.slow
def test_reverse_drill_to_source_row(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = journal_world(app, keyring, clock, files)
    maya = world.legacy.maya
    event_id = _booked_event(world)
    _post_revenue(world, event_id)
    run, lines = calculated_run(world, entity=ENTITY_1)
    assert run["state"] == "draft", run
    (revenue,) = [line for line in lines if line["account"]["code"] == "5001"]
    assert revenue["links"]["drill"] == f"{API}/journal-lines/{revenue['id']}/drill"

    # Journal line → contributing subledger lines (RCP-27).
    drilled = get(app, revenue["links"]["drill"], maya)
    assert drilled.status_code == 200, drilled.text
    (line,) = drilled.json()["items"]
    assert (line["account_role"], line["amount_txn"], line["contract_event_id"]) == (
        "REVENUE",
        {"amount": "-100.00", "currency": "USD"},
        str(event_id),
    )
    assert line["links"]["event"] == f"{API}/events/{event_id}"

    # Subledger line → event → the source file row.
    shown = get(app, line["links"]["event"], maya)
    assert shown.status_code == 200, shown.text
    event = shown.json()
    assert (event["id"], event["event_type"], event["contract_id"]) == (
        str(event_id),
        "CONTRACT_BOOKED",
        str(world.contracts[CONTRACT].id),
    )
    source = event["source_row"]
    assert source is not None, event
    assert source["import_upload_id"] == event["import_upload_id"] is not None
    upload = get(app, f"{API}/imports/{source['import_upload_id']}", maya)
    assert upload.status_code == 200, upload.text
    assert upload.json()["file"]["id"] is not None
    rows = get(
        app,
        f"{API}/imports/{source['import_upload_id']}/rows",
        maya,
        {"row_number": source["row_number"], "sheet_name": source["sheet"]},
    )
    assert rows.status_code == 200, rows.text
    (row,) = rows.json()["items"]
    assert (row["row_number"], row["sheet_name"]) == (source["row_number"], source["sheet"])

    # Out-of-scope ids answer 404 (API-C-03; REQ-PLT-012).
    outsider = holding(
        app,
        colleague(maya.member.tenant_id, "omar"),
        "revenue_accountant",
        entity_ids=[world.entities[ENTITY_2]],
    )
    for path in (revenue["links"]["drill"], line["links"]["event"]):
        refused = get(app, path, outsider)
        assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text


def _post_elsewhere(world: JournalWorld) -> None:
    """A February posting of Mock Entity 2 whose lines name Contract 1, a contract of Mock Entity
    1: Dr contract liability 21001 / Cr revenue 5001, 25.00 USD."""
    found = world.contracts[CONTRACT]
    period_id, period_end = world.periods[FEBRUARY]
    obligation_id, legacy_key = found.obligations[OBLIGATION]
    dimensions = {"contract_key": CONTRACT, "obligation_key": OBLIGATION}
    lines: list[dict[str, Any]] = [
        {
            "period_end_date": period_end,
            "entity_id": world.entities[ENTITY_2],
            "period_id": period_id,
            "origin_period_id": None,
            "reason_code": None,
            "effective_date": period_end,
            "entry_no": 1,
            "entry_kind": "REVENUE_RECOGNITION",
            "account_role": role,
            "clearing_purpose": None,
            "gl_account_id": world.accounts[account],
            "dimensions": dimensions,
            "dimension_set_sha256": subledger.dimension_set_sha256(dimensions),
            "txn_currency": "USD",
            "amount_txn": Decimal(amount),
            "functional_currency": "USD",
            "amount_functional": Decimal(amount),
            "contract_id": found.id,
            "obligation_id": obligation_id,
            "legacy_key": legacy_key if role == "REVENUE" else CONTRACT,
        }
        for role, account, amount in (
            ("CONTRACT_LIABILITY", "21001", "25.00"),
            ("REVENUE", "5001", "-25.00"),
        )
    ]
    with world.legacy.place().uow() as uow:
        subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key="drill:elsewhere",
            description="A line of another entity that names the contract",
            lines=lines,
            combination_group_id=found.group_id,
            contract_computation_id=found.computation_id,
        )
        uow.commit()


@contextmanager
def _statements() -> Iterator[list[str]]:
    """Every SQL statement the process sends while the block runs."""
    seen: list[str] = []

    def capture(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", capture)


def _drilled(app: FastAPI, line: dict[str, Any], actor: Actor) -> tuple[list[dict[str, Any]], int]:
    """The source lines of a journal line and the number of statements the read sent, after the
    same read once (the first request of a session may do work a later one does not)."""
    path = line["links"]["drill"]
    assert get(app, path, actor).status_code == 200
    with _statements() as seen:
        answer = get(app, path, actor)
    assert answer.status_code == 200, answer.text
    assert answer.json()["next_cursor"] is None
    return list(answer.json()["items"]), len(seen)


@pytest.mark.slow
def test_the_drill_names_the_contract_of_every_line_without_reading_it(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 API-S-SubledgerLine ``contract_external_id`` (rev 1.159; supervisor ruling of 2026-10-01
    on the e2e row ``SF-06:run-lines``). A journal line at the default grain sums the lines of many
    contracts, and the source-lines drawer read ``GET /contracts/{id}`` once per contract to name
    them before it showed a row — 91 reads for one line of the demo tenant. The row now carries
    the name: every line of the drill names its contract, in the route's order; the read sends
    the same number of statements for a line of one contract as for a line of two; and the two
    other reads of the schema — the subledger register and the contract's own lines — answer the
    member row for row."""
    world = journal_world(app, keyring, clock, files)
    maya = world.legacy.maya
    first = world.contracts[CONTRACT]
    second_key = sorted(
        key
        for key, item in world.contracts.items()
        if key != CONTRACT and item.entity_id == first.entity_id
    )[0]
    second = world.contracts[second_key]
    for key, contract_key, revenue, amount in (
        ("drill-contract-1", CONTRACT, "5001", "100.00"),
        ("drill-contract-2", second_key, "5002", "50.00"),
    ):
        post_lines(
            world,
            key=key,
            contract_key=contract_key,
            period_key=FEBRUARY,
            entries=[
                (
                    "REVENUE_RECOGNITION",
                    [
                        ("CONTRACT_LIABILITY", "21001", amount, OBLIGATION),
                        ("REVENUE", revenue, f"-{amount}", OBLIGATION),
                    ],
                )
            ],
        )
    run, lines = calculated_run(world, entity=ENTITY_1, grain=DEFAULT_GRAIN, period_key=FEBRUARY)
    assert run["state"] == "draft", run
    by_account = {line["account"]["code"]: line for line in lines}
    assert sorted(by_account) == ["21001", "5001", "5002"]
    # the liability line sums both contracts and names neither; each revenue line has one
    assert by_account["21001"]["source_line_count"] == 2

    shared, shared_statements = _drilled(app, by_account["21001"], maya)
    assert [(item["contract_id"], item["contract_external_id"]) for item in shared] == [
        (str(first.id), CONTRACT),
        (str(second.id), second_key),
    ]
    assert [item["id"] for item in shared] == sorted(item["id"] for item in shared)
    single, single_statements = _drilled(app, by_account["5001"], maya)
    assert [(item["contract_id"], item["contract_external_id"]) for item in single] == [
        (str(first.id), CONTRACT)
    ]
    # the name comes with the row: no statement per contract
    assert shared_statements == single_statements

    names = {str(first.id): CONTRACT, str(second.id): second_key}
    register = get(
        app, f"{API}/subledger-lines", maya, {"entity": ENTITY_1, "period": FEBRUARY, "limit": 200}
    )
    assert register.status_code == 200, register.text
    listed = register.json()["items"]
    assert len(listed) == 4
    assert all(item["contract_external_id"] == names[item["contract_id"]] for item in listed)
    # the contract's own lines are read as of a date of the entity's calendar (API-C-10)
    own = get(
        app,
        f"{API}/contracts/{second.id}/subledger-lines",
        maya,
        {"limit": 200, "as_of": "2023-02-28"},
    )
    assert own.status_code == 200, own.text
    assert [item["contract_external_id"] for item in own.json()["items"]] == [second_key] * 2

    # The member tells a reader nothing the reader may not read: a line of Mock Entity 2 that
    # names a contract of Mock Entity 1 keeps its contract id, as before, and no name for a
    # reader whose scope is Mock Entity 2 alone (T-CON-01 is RLS-TE); Maya reads the name.
    _post_elsewhere(world)
    omar = holding(
        app,
        colleague(maya.member.tenant_id, "omar"),
        "revenue_accountant",
        entity_ids=[world.entities[ENTITY_2]],
    )
    elsewhere = {"entity": ENTITY_2, "period": FEBRUARY, "limit": 200}
    scoped = get(app, f"{API}/subledger-lines", omar, elsewhere)
    assert scoped.status_code == 200, scoped.text
    assert [
        (item["contract_id"], item["contract_external_id"]) for item in scoped.json()["items"]
    ] == [(str(first.id), None)] * 2
    whole = get(app, f"{API}/subledger-lines", maya, elsewhere)
    assert whole.status_code == 200, whole.text
    assert [item["contract_external_id"] for item in whole.json()["items"]] == [CONTRACT] * 2


@pytest.mark.slow
def test_the_drill_names_the_obligation_of_every_line_through_its_contract(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 API-S-SubledgerLine ``obligation_key`` (rev 1.245; register index 182). The row carried
    the obligation's id and no key, so the source-lines drawer could name the obligation of a
    line only by a read per obligation. It now carries the key (T-CON-10): a line with an
    obligation names it, a line without one — a billing line — answers null, and the read sends
    the same number of statements for either. The subledger register and the contract's own lines
    answer the member row for row.

    The key is joined THROUGH the contract's row: T-CON-10 is RLS-T while the contract is RLS-TE,
    so a join by the obligation's id alone would name the obligation of a contract whose name the
    reader is not told. A line of Mock Entity 2 that names a contract of Mock Entity 1 keeps its
    obligation id, as before, and answers no key to a reader of Mock Entity 2 alone, as it
    answers no contract name; Maya reads both."""
    world = journal_world(app, keyring, clock, files)
    maya = world.legacy.maya
    first = world.contracts[CONTRACT]
    post_lines(
        world,
        key="key-contract-1",
        contract_key=CONTRACT,
        period_key=FEBRUARY,
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "100.00", OBLIGATION),
                    ("REVENUE", "5001", "-100.00", OBLIGATION),
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
    run, lines = calculated_run(world, entity=ENTITY_1, grain=DEFAULT_GRAIN, period_key=FEBRUARY)
    assert run["state"] == "draft", run
    by_account = {line["account"]["code"]: line for line in lines}
    assert sorted(by_account) == ["1100", "2100", "21001", "5001"]

    keyed, keyed_statements = _drilled(app, by_account["5001"], maya)
    assert [(item["obligation_id"] is None, item["obligation_key"]) for item in keyed] == [
        (False, OBLIGATION)
    ]
    plain, plain_statements = _drilled(app, by_account["1100"], maya)
    assert [(item["obligation_id"], item["obligation_key"]) for item in plain] == [(None, None)]
    # the key comes with the row: no statement per obligation
    assert keyed_statements == plain_statements

    expected = {"1100": None, "2100": None, "21001": OBLIGATION, "5001": OBLIGATION}
    register = get(
        app, f"{API}/subledger-lines", maya, {"entity": ENTITY_1, "period": FEBRUARY, "limit": 200}
    )
    assert register.status_code == 200, register.text
    assert {
        item["account"]["code"]: item["obligation_key"] for item in register.json()["items"]
    } == expected
    own = get(
        app,
        f"{API}/contracts/{first.id}/subledger-lines",
        maya,
        {"limit": 200, "as_of": "2023-02-28"},
    )
    assert own.status_code == 200, own.text
    assert {
        item["account"]["code"]: item["obligation_key"] for item in own.json()["items"]
    } == expected

    _post_elsewhere(world)
    omar = holding(
        app,
        colleague(maya.member.tenant_id, "omar"),
        "revenue_accountant",
        entity_ids=[world.entities[ENTITY_2]],
    )
    elsewhere = {"entity": ENTITY_2, "period": FEBRUARY, "limit": 200}
    scoped = get(app, f"{API}/subledger-lines", omar, elsewhere)
    assert scoped.status_code == 200, scoped.text
    assert [
        (item["contract_external_id"], item["obligation_id"] is None, item["obligation_key"])
        for item in scoped.json()["items"]
    ] == [(None, False, None)] * 2
    whole = get(app, f"{API}/subledger-lines", maya, elsewhere)
    assert whole.status_code == 200, whole.text
    assert [
        (item["contract_external_id"], item["obligation_key"]) for item in whole.json()["items"]
    ] == [(CONTRACT, OBLIGATION)] * 2

    # API-S-JournalLine (rev 1.245): the journal line of that posting names its contract and its
    # obligation to Maya; Omar reads the line — the read answered him 500 until the external id
    # of a contract outside the reader's scope could be null — with the contract's id, which is
    # the line's own, and no name and no key
    elsewhere_run, its_lines = calculated_run(world, entity=ENTITY_2, period_key=FEBRUARY)
    assert elsewhere_run["state"] == "draft", elsewhere_run
    (revenue,) = [line for line in its_lines if line["account"]["code"] == "5001"]
    assert (revenue["contract"], revenue["obligation_key"]) == (
        {"id": str(first.id), "external_id": CONTRACT},
        OBLIGATION,
    )
    listed = get(app, f"{API}/journal-runs/{elsewhere_run['id']}/lines", omar, {"limit": 200})
    assert listed.status_code == 200, listed.text
    (unnamed,) = [line for line in listed.json()["items"] if line["account"]["code"] == "5001"]
    assert (unnamed["contract"], unnamed["obligation_key"]) == (
        {"id": str(first.id), "external_id": None},
        None,
    )
    assert {**unnamed, "contract": None, "obligation_key": None} == {
        **revenue,
        "contract": None,
        "obligation_key": None,
    }
