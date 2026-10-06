"""CLO-15 chunking, the run's general ledger and the export through the NetSuite mock
(ENGINE_SPEC_B S14-R-21, S14-R-22; 05 ADP-10 to ADP-12, ADP-20 to ADP-23, ADP-31; 04 T-SL-07,
T-INT-01; 03 REQ-JE-014, REQ-INT-009; PRD J-13.9; BUILD_SPEC CLO-15).

World: ``support.worlds.journal_world``. February 2023 of Mock Entity 1 receives one revenue
entry per contract — Contract 1 and the entity's second contract — on the shared contract
liability account 21001, so the default grain nets them into one entry of three lines. An
Integration Admin creates and enables the GL connections through ``/integrations``; the NetSuite
mock is the app's own, reached over ASGI as the worker reaches it over ``base_url`` (ADP-20).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.gl import netsuite
from erev_api.adapters.gl.csv import CsvGl
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import journal_batch, outbox_message, posting_ack
from erev_api.domain.journals import export, ports
from erev_api.enums import GlAdapter, JobKind, OutboxTopic
from erev_api.events import outbox
from erev_api.events.outbox import RelayStats
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobContext
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import run_import_job
from support.http import asgi_client
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, get, patch, post, slug
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    FEBRUARY,
    JOURNAL_RUNS,
    RUN_ID_HEADER,
    JournalWorld,
    journal_world,
    post_lines,
)

INTEGRATIONS: Final = "/api/v1/integrations"
MOCK_BASE: Final = f"{mocks.MOCKS_PREFIX}{ns_mock.PREFIX}"
DEFAULT_GRAIN: Final = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"
CONTRACT_1: Final = "Contract 1"
FEBRUARY_END: Final = "2023-02-28"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> JournalWorld:
    built = journal_world(app, keyring, clock, files)
    first, second = _pair(built)
    for key, contract_key, revenue, amount in (
        ("chunk-contract-1", first, "5001", "100.00"),
        ("chunk-contract-2", second, "5002", "50.00"),
    ):
        post_lines(
            built,
            key=key,
            contract_key=contract_key,
            period_key=FEBRUARY,
            entries=[
                (
                    "REVENUE_RECOGNITION",
                    [
                        ("CONTRACT_LIABILITY", "21001", amount, "POB #1"),
                        ("REVENUE", revenue, f"-{amount}", "POB #1"),
                    ],
                )
            ],
        )
    return built


def _pair(world: JournalWorld) -> tuple[str, str]:
    """Contract 1 and another contract of its entity (external ids): the two whose February
    revenue the world posts."""
    first = world.contracts[CONTRACT_1]
    others = sorted(
        key
        for key, item in world.contracts.items()
        if key != CONTRACT_1 and item.entity_id == first.entity_id
    )
    return CONTRACT_1, others[0]


def _rows(world: JournalWorld, statement: Any) -> list[dict[str, Any]]:
    return world.legacy.imports.rows(statement)


def _admin(world: JournalWorld, clock: FrozenClock) -> Actor:
    """An Integration Admin, enrolled: ``integration.manage`` needs a verified second factor."""
    someone = colleague(world.legacy.tenant_id, "nikhil")
    assign(someone, "integration_admin")
    return enrolled(world.app, clock, someone)


def _connection(world: JournalWorld, admin: Actor, **members: Any) -> dict[str, Any]:
    """An ``ACTIVE`` GL connection, created and enabled through the API."""
    body: dict[str, Any] = {
        "code": "netsuite-mock",
        "name": "NetSuite (mock)",
        "adapter": "NETSUITE",
        "direction": "BOTH",
        "base_url": MOCK_BASE,
    }
    body.update(members)
    created = post(world.app, INTEGRATIONS, admin, body)
    assert created.status_code == 201, created.text
    enabled = patch(
        world.app,
        f"{INTEGRATIONS}/{created.json()['id']}",
        admin,
        {"status": "ACTIVE"},
        if_match='"r1"',
    )
    assert enabled.status_code == 200, enabled.text
    return dict(enabled.json())


def _requested(world: JournalWorld, entity: str = ENTITY_1) -> tuple[UUID, str]:
    created = post(
        world.app,
        JOURNAL_RUNS,
        world.legacy.maya,
        {"entity_code": entity, "period_key": FEBRUARY, "grain": DEFAULT_GRAIN},
    )
    assert created.status_code == 202, created.text
    return UUID(str(created.json()["id"])), str(created.headers[RUN_ID_HEADER])


def _calculated(world: JournalWorld, entity: str = ENTITY_1) -> dict[str, Any]:
    job_id, run_id = _requested(world, entity)
    run_import_job(world.legacy.imports, job_id)
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _lines(world: JournalWorld, run_id: str) -> list[dict[str, Any]]:
    listed = get(world.app, f"{JOURNAL_RUNS}/{run_id}/lines", world.legacy.maya, {"limit": 200})
    assert listed.status_code == 200, listed.text
    return list(listed.json()["items"])


def _by_batch(world: JournalWorld, run: dict[str, Any]) -> dict[str, list[tuple[str, str, str]]]:
    """External id → (account, debit, credit) of the batch's lines, in line order."""
    ids = {batch["id"]: batch["external_id"] for batch in run["batches"]}
    found: dict[str, list[tuple[str, str, str]]] = {external: [] for external in ids.values()}
    for line in sorted(_lines(world, run["id"]), key=lambda item: item["line_no"]):
        found[ids[line["journal_batch_id"]]].append(
            (
                line["account"]["code"],
                line["debit_txn"]["amount"],
                line["credit_txn"]["amount"],
            )
        )
    return found


def _cancelled(world: JournalWorld, run_id: str) -> None:
    cancelled = post(
        world.app,
        f"{JOURNAL_RUNS}/{run_id}/cancel",
        world.legacy.maya,
        {"reason": "Recalculate for the general ledger connection."},
    )
    assert cancelled.status_code == 200, cancelled.text


@pytest.mark.slow
def test_chunks_never_split_entries(world: JournalWorld, clock: FrozenClock) -> None:
    """BUILD_SPEC CLO-15 (S14-R-21; ADP-11): with ``max_lines_per_chunk = 2``, an entry of three
    lines is re-summarised at grain ``CONTRACT_ACCOUNT_DIMENSIONS`` and split by contract; every
    chunk balances in transaction and functional currency; chunk external ids end ``:1``, ``:2``.

    Control first: without a GL connection the run is one ``CSV`` batch holding the entry whole."""
    whole = _calculated(world)
    [csv_batch] = whole["batches"]
    assert (csv_batch["adapter"], csv_batch["chunk_no"], csv_batch["line_count"]) == ("CSV", 1, 3)
    assert _by_batch(world, whole) == {
        csv_batch["external_id"]: [
            ("21001", "150.00", "0.00"),
            ("5001", "0.00", "100.00"),
            ("5002", "0.00", "50.00"),
        ]
    }
    assert whole["je_range"]["count"] == 1
    _cancelled(world, whole["id"])

    connection = _connection(world, _admin(world, clock), config={"max_lines_per_chunk": 2})
    run = _calculated(world)
    batches = sorted(run["batches"], key=lambda item: item["chunk_no"])
    prefix = f"erev:{batches[0]['external_id'].split(':')[1]}:{run['run_no']}:1"
    assert [(item["batch_no"], item["chunk_no"], item["external_id"]) for item in batches] == [
        (1, 1, f"{prefix}:1"),
        (1, 2, f"{prefix}:2"),
    ]
    assert {item["adapter"] for item in batches} == {"NETSUITE"}
    # each contract's part is a chunk of its own; no entry is split across chunks
    assert _by_batch(world, run) == {
        f"{prefix}:1": [("21001", "100.00", "0.00"), ("5001", "0.00", "100.00")],
        f"{prefix}:2": [("21001", "50.00", "0.00"), ("5002", "0.00", "50.00")],
    }
    for item, total in zip(batches, ("100.00", "50.00"), strict=True):
        assert item["line_count"] == 2
        # every chunk balances in transaction and functional currency
        assert {
            item[name]["amount"]
            for name in (
                "total_debit_txn",
                "total_credit_txn",
                "total_debit_functional",
                "total_credit_functional",
            )
        } == {total}
    stored = _rows(
        world,
        select(journal_batch.c.integration_connection_id, journal_batch.c.chunk_no).where(
            journal_batch.c.journal_run_id == UUID(run["id"])
        ),
    )
    assert {str(row["integration_connection_id"]) for row in stored} == {connection["id"]}
    # one entry per chunk — a contract's part of the entry — and every line names its contract
    lines = _lines(world, run["id"])
    by_batch: dict[str, set[tuple[str, str]]] = {}
    for line in lines:
        by_batch.setdefault(line["journal_batch_id"], set()).add(
            (line["je_no"], line["contract"]["external_id"])
        )
    parts = [by_batch[item["id"]] for item in batches]
    assert [len(part) for part in parts] == [1, 1]
    assert len({je_no for part in parts for je_no, _ in part}) == 2
    assert {contract for part in parts for _, contract in part} == set(_pair(world))
    assert (run["je_range"]["count"], run["totals"]["line_count"], run["totals"]["balanced"]) == (
        2,
        4,
        True,
    )


def _drilled(world: JournalWorld, run: dict[str, Any]) -> dict[tuple[str, str | None], list[str]]:
    """(account, contract named by the journal line) → the amounts of the subledger lines the
    line drills to. Every drill names as many lines as the journal line counts, and their
    amounts sum to it."""
    found: dict[tuple[str, str | None], list[str]] = {}
    for line in _lines(world, run["id"]):
        answered = get(world.app, line["links"]["drill"], world.legacy.maya, {"limit": 200})
        assert answered.status_code == 200, answered.text
        amounts = [Decimal(item["amount_txn"]["amount"]) for item in answered.json()["items"]]
        net = Decimal(line["debit_txn"]["amount"]) - Decimal(line["credit_txn"]["amount"])
        key = (line["account"]["code"], line["contract"] and line["contract"]["external_id"])
        assert len(amounts) == line["source_line_count"], (key, amounts)
        assert sum(amounts, Decimal(0)) == net, (key, amounts)
        found[key] = sorted(str(amount) for amount in amounts)
    return found


@pytest.mark.slow
def test_the_drill_of_a_line_of_a_split_entry_names_its_source_lines(
    world: JournalWorld, clock: FrozenClock
) -> None:
    """04 T-SL-06 drill-back rev 1.288 (item SUBLEDGER-LINE-JOURNAL-RUN-1 — PRODUCT DEFECT of the
    drill, measured through the product on 2026-10-02). With ``max_lines_per_chunk = 2`` the
    entry of three lines is split by contract (S14-R-21), and each of its four journal lines
    carries the grouping hash of grain ``CONTRACT_ACCOUNT_DIMENSIONS``, the grain it was
    summarised at. The drill hashed the run's lines at the run's own grain: for each of the four
    it answered 200 with an EMPTY list, where the journal line counts one source line. It now
    names that line, and its amount is the journal line's.

    Control first: without a ledger connection the entry is whole, at the run's grain, and its
    three lines drill to two, one and one."""
    first, second = _pair(world)
    whole = _calculated(world)
    assert _drilled(world, whole) == {
        ("21001", None): ["100.00", "50.00"],
        ("5001", None): ["-100.00"],
        ("5002", None): ["-50.00"],
    }
    _cancelled(world, whole["id"])

    _connection(world, _admin(world, clock), config={"max_lines_per_chunk": 2})
    split = _calculated(world)
    assert {batch["adapter"] for batch in split["batches"]} == {"NETSUITE"}
    assert _drilled(world, split) == {
        ("21001", first): ["100.00"],
        ("5001", first): ["-100.00"],
        ("21001", second): ["50.00"],
        ("5002", second): ["-50.00"],
    }


@pytest.mark.slow
def test_the_entity_scope_and_the_number_of_connections_decide_the_ledger(
    world: JournalWorld, clock: FrozenClock
) -> None:
    """04 T-INT-01 / T-SL-07 (CLO-15): the run takes the entity's ACTIVE outbound GL connection. A
    connection that names other entities leaves the run ``CSV``; two connections that both cover
    the entity refuse the calculation by name — journals are never sent to a ledger picked by
    sort order."""
    admin = _admin(world, clock)
    elsewhere = _connection(
        world, admin, code="netsuite-entity-2", entity_ids=[str(world.entities[ENTITY_2])]
    )
    run = _calculated(world)
    assert [item["adapter"] for item in run["batches"]] == ["CSV"]
    _cancelled(world, run["id"])

    covering = patch(
        world.app,
        f"{INTEGRATIONS}/{elsewhere['id']}",
        admin,
        {"entity_ids": []},
        if_match=f'"r{elsewhere["row_version"]}"',
    )
    assert covering.status_code == 200, covering.text
    _connection(
        world,
        admin,
        code="quickbooks-mock",
        name="QuickBooks (mock)",
        adapter="QUICKBOOKS_ONLINE",
        base_url=f"{mocks.MOCKS_PREFIX}/qbo",
        config={"realm_id": "4620816365012345670"},
    )
    job_id, run_id = _requested(world)
    run_import_job(world.legacy.imports, job_id)
    finished = get(world.app, f"/api/v1/jobs/{job_id}", world.legacy.maya).json()
    assert finished["state"] == "FAILED", finished
    assert finished["problem"]["detail"] == (
        "Mock Entity 1 has more than one active general ledger connection (netsuite-entity-2, "
        "quickbooks-mock). Disable all but one before calculating journals."
    )
    assert [(item["field"], item["rule_id"]) for item in finished["problem"]["errors"]] == [
        ("entity_code", "T-SL-07")
    ]
    # nothing was calculated: the run the job would have written does not exist
    missing = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.legacy.maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text


# --- the export through the NetSuite mock ---------------------------------------------------------


def _netsuite(world: JournalWorld, monkeypatch: pytest.MonkeyPatch) -> ns_mock.NetSuiteMock:
    """The worker's NETSUITE factory over the app's own mock (ASGI), and the company's chart of
    accounts stated to the mock as NetSuite holds it."""
    monkeypatch.setitem(
        ports.GL_ADAPTERS,
        GlAdapter.NETSUITE,
        netsuite.connection_factory(lambda base_url: asgi_client(world.app)),
    )
    accounts = [
        {"acctNumber": "21001", "acctName": "Contract liability", "acctType": "DeferRevenue"},
        {"acctNumber": "5001", "acctName": "Revenue 1", "acctType": "Income"},
        {"acctNumber": "5002", "acctName": "Revenue 2", "acctType": "Income"},
    ]
    with asgi_client(world.app) as client:
        seeded = client.post(f"{MOCK_BASE}/__erp/accounts", json={"accounts": accounts})
        assert seeded.status_code == 201, seeded.text
    mock = world.app.state.mocks.adapters[ns_mock.CODE]
    assert isinstance(mock, ns_mock.NetSuiteMock)
    return mock


def _approved(world: JournalWorld) -> dict[str, Any]:
    run = _calculated(world)
    submitted = post(world.app, f"{JOURNAL_RUNS}/{run['id']}/submit", world.legacy.maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.legacy.priya)
    assert decided.status_code == 200, decided.text
    return run


def _exported(world: JournalWorld, run_id: str) -> None:
    requested = post(world.app, f"{JOURNAL_RUNS}/{run_id}/export", world.legacy.maya, {})
    assert requested.status_code == 202, requested.text
    run_import_job(world.legacy.imports, UUID(str(requested.json()["id"])))


def _run(world: JournalWorld, run_id: str) -> dict[str, Any]:
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _receipts(world: JournalWorld, run: dict[str, Any]) -> list[tuple[int, str, str | None]]:
    """(chunk no, receipt kind, GL document) of the run's receipts, in chunk order."""
    rows = _rows(
        world,
        select(journal_batch.c.chunk_no, posting_ack.c.ack_kind, posting_ack.c.gl_document_id)
        .select_from(
            posting_ack.join(journal_batch, journal_batch.c.id == posting_ack.c.journal_batch_id)
        )
        .where(journal_batch.c.journal_run_id == UUID(run["id"]))
        .order_by(journal_batch.c.chunk_no, posting_ack.c.received_at),
    )
    return [(int(row["chunk_no"]), str(row["ack_kind"]), row["gl_document_id"]) for row in rows]


@pytest.mark.slow
def test_export_to_netsuite_acknowledges_every_chunk_once(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """PRD J-13.9 (REQ-JE-014; ADP-10, ADP-23, ADP-31): the relay posts each chunk of the run to
    the NetSuite mock by its external id; every batch is ``acknowledged`` with its NetSuite
    document, so the run is; a repeated export posts nothing again; and the mock's trial balance
    of the period is what was posted to it (REQ-INT-009)."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock), config={"max_lines_per_chunk": 2})
    run = _approved(world)
    _exported(world, run["id"])
    shown = _run(world, run["id"])
    assert (shown["state"], sorted(item["state"] for item in shown["batches"])) == (
        "acknowledged",
        ["acknowledged", "acknowledged"],
    )
    assert _receipts(world, run) == [(1, "POSTED", "JE-NS-88001"), (2, "POSTED", "JE-NS-88002")]
    assert mock.posting_count == 2
    batches = sorted(shown["batches"], key=lambda item: item["chunk_no"])
    for item, document in zip(batches, ("JE-NS-88001", "JE-NS-88002"), strict=True):
        record = mock.journal(item["external_id"])
        assert record is not None and (record["tranId"], record["tranDate"]) == (
            document,
            FEBRUARY_END,
        )
    # BR-JE-02: the export command again, and the adapter asked again, post nothing twice
    _exported(world, run["id"])
    assert mock.posting_count == 2 and len(_receipts(world, run)) == 2

    # REQ-INT-009: the ledger's closing balances of February are the two chunks
    gl = ports.gl_adapter_for(
        GlAdapter.NETSUITE,
        ports.GLContext(tenant_code=_tenant_code(batches[0]), accounts=(), base_url=MOCK_BASE),
    )
    start, end = world.periods[FEBRUARY][1].replace(day=1), world.periods[FEBRUARY][1]
    pulled = gl.pull_trial_balance(
        ports.EntityRef(ENTITY_1),
        ports.PeriodRef(FEBRUARY, start, end),
        ["21001", "5001", "5002"],
    )
    assert {line.account_code: line.amount for line in pulled.lines} == {
        "21001": Decimal("150.00"),
        "5001": Decimal("-100.00"),
        "5002": Decimal("-50.00"),
    }
    assert {item.external_id for item in pulled.details} == {
        item["external_id"] for item in batches
    }
    assert {item.document_reference for item in pulled.details} == {"JE-NS-88001", "JE-NS-88002"}


@pytest.mark.slow
def test_a_chunk_the_ledger_already_holds_is_recorded_as_a_duplicate(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """ADP-12 ``Duplicate`` through the relay and the mock (BR-JE-02): the ledger took the chunk
    from an attempt whose answer never reached the product, and reports on the next one that it
    holds the external id. The batch is recorded with a ``DUPLICATE`` receipt that carries the
    ledger's document, the run is acknowledged, and the ledger holds one posting."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))  # the NetSuite default of 500 lines: one chunk
    run = _approved(world)
    [batch] = run["batches"]
    assert (batch["adapter"], batch["chunk_no"], batch["line_count"]) == ("NETSUITE", 1, 3)
    [message] = _rows(
        world,
        select(outbox_message.c.id).where(
            outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value
        ),
    )
    # the attempt whose answer was lost: the ledger holds the document, the product no receipt
    lost = ports.gl_adapter_for(
        GlAdapter.NETSUITE,
        ports.GLContext(tenant_code=_tenant_code(batch), accounts=(), base_url=MOCK_BASE),
    )
    context = DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        chunk = export.chunk_of(session, UUID(batch["id"]))
    assert lost.post_chunk(chunk).gl_document_id == "JE-NS-88001"
    assert (mock.posting_count, _receipts(world, run)) == (1, [])

    _fault(world, "DUPLICATE")
    stats = outbox.relay_messages(
        _relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT
    )
    assert stats == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    assert _receipts(world, run) == [(1, "DUPLICATE", "JE-NS-88001")]
    assert mock.posting_count == 1
    shown = _run(world, run["id"])
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "acknowledged",
        ["acknowledged"],
    )


class _Busy:
    """A ledger that answers every posting 429 and asks for ``wait`` seconds (ADP-12). The
    accounts are validated as the CSV adapter validates them, against the entity's chart."""

    def __init__(self, wait: float) -> None:
        self.wait = wait
        self.calls = 0
        self._csv: CsvGl | None = None

    def __call__(self, context: ports.GLContext) -> _Busy:
        self._csv = CsvGl(context)
        return self

    def validate_accounts(
        self, accounts: Sequence[ports.AccountRef], dimensions: Sequence[ports.DimensionRef]
    ) -> ports.ValidationResult:
        assert self._csv is not None
        return self._csv.validate_accounts(accounts, dimensions)

    def post_chunk(self, chunk: ports.JournalChunk) -> ports.PostingResult:
        self.calls += 1
        raise ports.Transient("The ledger is busy.", retry_after=self.wait)

    def get_posting(self, external_id: str) -> ports.PostingResult | None:
        return None


@pytest.mark.slow
@pytest.mark.parametrize(("asked", "waited"), [(1.0, 30), (120.0, 120)])
def test_the_relay_waits_as_long_as_the_ledger_asks(
    world: JournalWorld,
    monkeypatch: pytest.MonkeyPatch,
    clock: FrozenClock,
    asked: float,
    waited: int,
) -> None:
    """ADP-12 (429 with ``Retry-After``): the batch stays ``approved`` and the message is due
    again after the later of the ADP-12 wait of the attempt (30 s for the first) and the wait the
    ledger states — never earlier than the ledger asked."""
    ledger = _Busy(asked)
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.NETSUITE, ledger)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [message] = _rows(
        world,
        select(outbox_message.c.id).where(
            outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value
        ),
    )
    start = clock.now()
    stats = outbox.relay_messages(
        _relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT
    )
    assert stats == RelayStats(claimed=1, dispatched=0, failed=1, dead=0)
    [waiting] = _rows(world, select(outbox_message).where(outbox_message.c.id == message["id"]))
    assert (waiting["status"], waiting["attempt_count"], waiting["next_attempt_at"]) == (
        "FAILED",
        1,
        start + timedelta(seconds=waited),
    )
    assert ledger.calls == 1
    shown = _run(world, run["id"])
    assert (shown["state"], _receipts(world, run)) == ("approved", [])


def _tenant_code(batch: dict[str, Any]) -> str:
    """The workspace code of an ADP-10 external id ``erev:<workspace code>:…``."""
    return str(batch["external_id"]).split(":")[1]


def _fault(world: JournalWorld, kind: str) -> None:
    """Queue one ADP-21 fault on the mock's journal route."""
    with asgi_client(world.app) as client:
        queued = client.post(
            f"{mocks.MOCKS_PREFIX}/__admin/faults",
            json={"route": ns_mock.JOURNAL_ROUTE, "kind": kind, "count": 1},
        )
        assert queued.status_code == 201, queued.text


def _relayer(world: JournalWorld) -> JobContext:
    tenant_id = world.legacy.tenant_id
    return JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=JobKind.OUTBOX_RELAY,
        principal=system_principal(tenant_id),
        runtime=world.legacy.imports.runtime,
        persisted=False,
    )
