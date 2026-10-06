"""As-locked report runs on a database (ENGINE_SPEC_B S15-R-19 rev 1.31; supervisor ruling D-98
candidate 96; 04 T-RPT-02 rev 1.53; SCREENS_B RV-04 rev 1.17; BUILD_SPEC CLO-8).

DB-bound (the ``k01_pellworth`` world). NOT RUN on the authoring worktree (databases not
provisioned); measured by the integrated batch on merged main. Two facts about this tree shape the
fixtures: the September lock is written by the domain's own writers as
``tests/domain/close/test_reopen.py`` does (the public lock path is ``test_lock.py``'s witness);
and — CLO-8c (F-CLO record §25.35) — the CONTRACT_BALANCES dataset OF RECORD is frozen THROUGH
the F-RPS registry (``erev_api.domain.reports.snapshots.SNAPSHOT_DATASETS``, twelve of twelve)
at the lock instant and stored as F-CLO's machine artefact (``close/snapshots.py`` MEDIA_TYPE /
FILE_SUFFIX); the EDS-6 engine-encoded hand-made dataset (``_frozen_from``) remains ONLY as the
negative control of the hand-made-inconsistent scenario. What the run reads is the frozen file —
never the live builder.

First run on a database in lane FIX-D2 (2026-09-29; supervisor ruling R-4). The world lives on
the RECORD-TIME clock (``support.record_clock``): the registry freezes on the historical basis at
the lock instant, and on the business clock that instant precedes every contract version's
server ``known_at`` — the dataset of record came back EMPTY (three scenarios failed on the missing
K-01 row). The frozen dataset carries no presentation ``TOTAL:<ISO>`` row (ruling Q7, D-98 139
amendment 3), so its row count is the live report's DATA rows.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    contract,
    job,
    journal_batch,
    legal_entity,
    lock_snapshot,
)
from erev_api.db.tables import journal_run as journal_run_table
from erev_api.db.tables import report_run as report_run_table
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates, relock_diff
from erev_api.domain.close import snapshots as close_snapshots
from erev_api.domain.reports import framework, locked
from erev_api.domain.reports import snapshots as registry
from erev_api.enums import (
    ApprovalRequestStatus,
    ContractEventType,
    FilePurpose,
    JobKind,
    LockKind,
    PeriodState,
    RunStatus,
    SnapshotKind,
)
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore, store_file
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_engine.stages.s15_disclosures import snapshots as engine
from fastapi import FastAPI
from sqlalchemy import insert, select, text, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import appended, computed
from support.principals import Actor, colleague, enrolled, step_up
from support.record_clock import on_record_time
from support.reference import assign, entity, get, holding, periods, post
from support.rows import approval_request_values
from support.worlds import (
    AVM_US,
    JOBS,
    K01,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    SEPTEMBER_2026,
    ReportWorld,
    journal_run,
    k01_pellworth,
    report_run,
    run_now,
)

CODE: Final = "contract_balances"
KIND: Final = SnapshotKind.CONTRACT_BALANCES.value
BALANCES: Final = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026}
RANGE: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}
K01_ROW: Final = f"contract:{K01}:{AVM_US}"
CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"
TEXT_COLUMNS: Final = ("contract_external_id", "customer_name", "entity_code", "currency")
MONEY_COLUMNS: Final = (
    "contract_liability",
    "contract_asset",
    "unbilled_receivable",
    "accounts_receivable",
    "refund_liability",
)
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ReportWorld:
    """``k01_pellworth`` through September, on the record-time clock: the fixture lock is written —
    and its dataset of record frozen by the registry — at an instant that follows the contract
    versions' server record stamps, as a production lock's does (module docstring)."""
    return on_record_time(k01_pellworth(app, keyring, clock, files))


# --- fixtures: the lock and its frozen dataset ----------------------------------------------------


def _state_id(world: ReportWorld) -> UUID:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity=AVM_US)
        if item["period"]["period_key"] == SEPTEMBER_2026
    ]
    return UUID(str(found["id"]))


def _scope(session: Session, state_id: UUID) -> gates.PeriodScope:
    scope = gates.period_scope(session, state_id, lock=True)
    assert scope is not None
    return scope


def _approved_lock_request(session: Session, world: ReportWorld, state_id: UUID) -> UUID:
    request = approval_request_values(
        world.tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        entity_id=world.entity_id,
        subject_type="PERIOD_LOCK",
        subject_id=state_id,
        summary="Fixture lock request",
    )
    session.execute(insert(approval_request).values(**request))
    return UUID(str(request["id"]))


def _lock_by_writer(world: ReportWorld) -> UUID:
    """September ``open → closing → closed`` through the domain's own writers (record §20.1 (4),
    (5)); returns the LOCK id. No dataset is frozen here."""
    state_id = _state_id(world)
    lock_id = new_id()
    with world.place.uow() as uow:
        session = uow.session
        scope = _scope(session, state_id)
        assert scope.state == PeriodState.OPEN.value
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
        scope = _scope(session, state_id)
        close_commands._persist_lock(
            uow,
            scope,
            kind=LockKind.LOCK,
            lock_id=lock_id,
            transition_id=new_id(),
            from_state=PeriodState.CLOSING,
            to_state=PeriodState.CLOSED,
            action=close_commands.LOCK_ACTION,
            approval_request_id=_approved_lock_request(session, world, state_id),
            comment="Fixture lock",
            certification=[],
            snapshot_manifest_sha256=None,
            heads=close_commands._heads(session, scope),
            cutoff_known_at=uow.now,  # 04 T-CLS-04 rev 1.113 (R-40 (c)): a LOCK names its cutoff
        )
        uow.commit()
    return lock_id


def _amount(cell: Any) -> str:
    return "" if cell is None else str(cell["amount"])


def _frozen_by_registry(world: ReportWorld, lock_id: UUID) -> engine.Encoded:
    """CLO-8c: the CONTRACT_BALANCES dataset OF RECORD, produced by the F-RPS registry adapter for
    the lock's scope at the lock instant (the wrapped real ``build`` without presentation totals —
    F-RPS's DB witness pins it equal to the live report); the registry writes nothing itself."""
    with world.place.uow() as uow:
        scope = _scope(uow.session, _state_id(world))
        encoded = registry.SNAPSHOT_DATASETS[KIND](
            uow,
            registry.SnapshotScope(
                entity_id=scope.entity_id,
                book_code=scope.book_code,
                period_id=scope.period_id,
                known_at=uow.now,
            ),
        )
        uow.commit()
    assert encoded.kind == KIND and lock_id is not None
    return encoded


def _frozen_from(
    rows: Sequence[Mapping[str, Any]], *, liability: Mapping[str, str] | None = None
) -> engine.Encoded:
    """NEGATIVE CONTROL ONLY (CLO-8c): a CONTRACT_BALANCES dataset hand-encoded from a live run's
    rows by the engine encoder — text cells, money as canonical amount text; ``liability``
    overrides a row's contract_liability. The fixture of record is ``_frozen_by_registry``."""
    overrides = dict(liability or {})
    columns = (
        engine.Column(engine.ROW_KEY, "text"),
        *(engine.Column(name, "text") for name in (*TEXT_COLUMNS, *MONEY_COLUMNS)),
    )
    frozen: list[dict[str, object]] = []
    for row in rows:
        key = str(row["row_key"])
        cells: dict[str, object] = {engine.ROW_KEY: key}
        cells.update({name: str(row[name]) for name in TEXT_COLUMNS})
        cells.update({name: _amount(row.get(name)) for name in MONEY_COLUMNS})
        if key in overrides:
            cells["contract_liability"] = overrides[key]
        frozen.append(cells)
    total = sum(Decimal(str(row["contract_liability"]) or "0") for row in frozen)
    return engine.encode(
        engine.Dataset(KIND, columns, tuple(frozen)), {"contract_liability:USD": str(total)}
    )


def _freeze(world: ReportWorld, lock_id: UUID, encoded: engine.Encoded) -> UUID:
    """Store the encoded bytes as a SNAPSHOT_DATASET file and write the T-CLS-05 row of the lock
    (``report_run_id`` NULL, ruling Q-10); returns the snapshot row id."""
    with world.place.uow() as uow:
        stored = store_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=BytesIO(encoded.content),
            original_filename=f"{encoded.kind}{close_snapshots.FILE_SUFFIX}",
            media_type=close_snapshots.MEDIA_TYPE,  # the machine artefact F-CLO's writer stores
        )
        assert str(stored["sha256"]) == encoded.file_sha256  # S15-INV-06
        row = {
            "tenant_id": world.tenant_id,
            "id": new_id(),
            "period_lock_id": lock_id,
            "snapshot_kind": encoded.kind,
            "report_run_id": None,
            "file_id": stored["id"],
            "file_sha256": encoded.file_sha256,
            "row_count": encoded.row_count,
            "control_totals": dict(encoded.control_totals),
            "created_at": uow.now,
            "created_by": None,
            "created_by_kind": "SYSTEM",
        }
        uow.session.execute(insert(lock_snapshot).values(**row))
        uow.commit()
    return UUID(str(row["id"]))


def _settle(world: ReportWorld, job_id: UUID) -> dict[str, Any]:
    """The worker's attempts until the job settles (RV-14: a refused build ends FAILED after the
    second of REPORT_RUN_RETRY's attempts); returns API-S-Job."""
    state = run_now(world, job_id)
    if state["state"] not in ("SUCCEEDED", "FAILED"):
        context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(_FETCHED, {"id": task_id})
        run_job(job_id, world.tenant_id, attempt=2, runtime=world.runtime)
        state = dict(get(world.app, f"{JOBS}/{job_id}", world.maya).json())
    assert state["state"] in ("SUCCEEDED", "FAILED"), state
    return state


def _settled_run(
    world: ReportWorld, code: str, parameters: Mapping[str, Any], *, output_format: str = "JSON"
) -> dict[str, Any]:
    """``POST /report-runs`` and the worker's attempts until the job settles (RV-14: a refused
    build ends FAILED after the second of REPORT_RUN_RETRY's attempts); returns API-S-ReportRun."""
    started = post(
        world.app,
        REPORT_RUNS,
        world.maya,
        {"report_code": code, "parameters": dict(parameters), "output_format": output_format},
    )
    assert started.status_code == 202, started.text
    _settle(world, UUID(str(started.json()["id"])))
    shown = get(world.app, f"{REPORT_RUNS}/{started.headers[REPORT_RUN_ID_HEADER]}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def _data_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """A live run's rows without its presentation ``TOTAL:<ISO>`` rows — the rows a lock freezes.
    Ruling Q7 (D-98 139 amendment 3; design note PRODUCTION-F-RPS-RPS-SNAP-DESIGN.md §12.7): "Q7 —
    ACCEPTED: no presentation ``TOTAL:<ISO>`` row in any dataset (the totals live in
    ``control_totals``)"; 04 T-CLS-05 producer registry: "the ten other kinds wrap the real
    ``build()`` with the presentation ``TOTAL:<ISO>`` rows removed (their totals are the control
    totals)"."""
    return [row for row in rows if not str(row["row_key"]).startswith(registry.TOTAL_PREFIX)]


def _refusal(run: Mapping[str, Any]) -> Mapping[str, Any]:
    assert run["status"] == "FAILED", run
    problem = run["problem"]
    assert problem is not None
    assert problem["type"].endswith("/validation-failed")
    (error,) = problem["errors"]
    assert (error["field"], error["rule_id"]) == (locked.FIELD, locked.RULE)
    assert error["message"] == problem["detail"]
    return problem


# --- scenarios ------------------------------------------------------------------------------------


def test_as_locked_run_reads_the_lock_dataset_not_live(
    world: ReportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S15-R-19: the run with period_lock_id reads the frozen CONTRACT_BALANCES file; the live
    builder is never called."""
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    encoded = _frozen_by_registry(world, lock_id)
    _freeze(world, lock_id, encoded)

    def never(*_: Any, **__: Any) -> Any:
        raise AssertionError("the live builder was called on an as-locked run")

    monkeypatch.setattr(
        framework, "BUILDERS", MappingProxyType({**framework.BUILDERS, CODE: never})
    )
    run, rows = report_run(world, CODE, {**BALANCES, "period_lock_id": str(lock_id)})
    assert run["period_lock_id"] == str(lock_id)
    # Q7: the dataset of record holds the live DATA rows; the live run adds one total per currency
    assert run["row_count"] == encoded.row_count == len(_data_rows(live_rows)) == 1
    assert {str(row["row_key"]) for row in live_rows} == {K01_ROW, f"{registry.TOTAL_PREFIX}USD"}
    assert len(live_rows) == 2
    assert run["control_totals"] == dict(encoded.control_totals)
    assert run["tie_out_results"] == []
    frozen = _keyed(rows)[K01_ROW]
    live = _keyed(live_rows)[K01_ROW]
    assert frozen["contract_liability"] == _amount(live["contract_liability"]) == "29944.11"
    assert frozen["contract_external_id"] == K01 and frozen["entity_code"] == AVM_US


def test_as_locked_csv_output_is_the_frozen_file(world: ReportWorld) -> None:
    """The CSV output of an as-locked run is the snapshot file itself: same bytes, output_sha256 =
    the snapshot's file_sha256 (CTL-029 reproduces both)."""
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    encoded = _frozen_by_registry(world, lock_id)
    _freeze(world, lock_id, encoded)
    run, _ = report_run(
        world, CODE, {**BALANCES, "period_lock_id": str(lock_id)}, output_format="CSV"
    )
    assert run["output"] is not None
    assert run["output"]["sha256"] == encoded.file_sha256
    downloaded = get(world.app, f"{REPORT_RUNS}/{run['id']}/output", world.maya)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == encoded.content
    rerun, _ = report_run(
        world, CODE, {**BALANCES, "period_lock_id": str(lock_id)}, output_format="CSV"
    )
    assert rerun["output"]["sha256"] == encoded.file_sha256
    assert rerun["control_totals"] == run["control_totals"]


def test_changed_live_source_after_the_lock_returns_the_locked_figures(
    world: ReportWorld,
) -> None:
    """A billing of 5,000.00 appended to SF-ORD-10001 after the lock moves the live September
    balances; the as-locked run still returns the frozen figures."""
    before_run, before_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    encoded = _frozen_by_registry(world, lock_id)
    _freeze(world, lock_id, encoded)
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    # F-RPS (Codex 2048): the fixture's ACTUAL admitted head — k01_pellworth appends four seeded
    # events after activation (head 6), so the former literal 3 would have refused the append.
    head = int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )
    appended(
        world.place,
        contract_id,
        head,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 9, 15),
                payload=BillingRecordedV1(
                    invoice_number="INV-US-1099",
                    line_external_id="INV-US-1099-1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="5000.00", currency="USD"),
                    issue_date=date(2026, 9, 15),
                ),
            )
        ],
    )
    computed(world.place, UUID(str(booked.combination_group["id"])))
    after_run, after_rows = report_run(world, CODE, BALANCES)
    before, after = _keyed(before_rows)[K01_ROW], _keyed(after_rows)[K01_ROW]
    assert after["contract_liability"] != before["contract_liability"]  # the live source moved
    assert after_run["control_totals"] != before_run["control_totals"]

    locked_run, locked_rows = report_run(world, CODE, {**BALANCES, "period_lock_id": str(lock_id)})
    frozen = _keyed(locked_rows)[K01_ROW]
    assert frozen["contract_liability"] == _amount(before["contract_liability"])
    assert frozen["contract_liability"] != _amount(after["contract_liability"])
    assert locked_run["control_totals"] == dict(encoded.control_totals)


def test_unsupported_source_refuses_by_name(world: ReportWorld) -> None:
    """A report without a lock dataset kind is refused at creation; a lock without the report's
    kind ends the run FAILED — each with the S15-R-19 refusal naming report, kind and lock, never
    live figures under an "as locked" label."""
    lock_id = _lock_by_writer(world)  # no dataset frozen
    # CLO8-SCOPE-R1: a report without a lock dataset is refused at creation, by name (no run).
    unsupported = post(
        world.app,
        REPORT_RUNS,
        world.maya,
        {
            "report_code": "revenue_from_opening_liability",
            "parameters": {**RANGE, "period_lock_id": str(lock_id)},
            "output_format": "JSON",
        },
    )
    assert unsupported.status_code == 422, unsupported.text
    (error,) = [
        item
        for item in unsupported.json()["errors"]
        if item["field"] == "parameters.period_lock_id"
    ]
    assert error["rule_id"] == locked.RULE
    assert error["message"] == locked.NO_DATASET.format(code="revenue_from_opening_liability")

    missing = _settled_run(world, CODE, {**BALANCES, "period_lock_id": str(lock_id)})
    problem = _refusal(missing)
    assert problem["detail"] == locked.SNAPSHOT_MISSING.format(lock=lock_id, kind=KIND, code=CODE)
    assert str(lock_id) in problem["detail"]


def test_run_without_period_lock_id_is_unchanged(
    world: ReportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A current run after the lock still calls the live builder and never reads the frozen file
    (frozen here with a liability of 1.00 that a current run must not show)."""
    before_run, before_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    _freeze(world, lock_id, _frozen_from(before_rows, liability={K01_ROW: "1.00"}))
    calls: list[str] = []
    original = framework.BUILDERS[CODE]

    def counted(uow: Any, params: Any) -> Any:
        calls.append(CODE)
        return original(uow, params)

    monkeypatch.setattr(
        framework, "BUILDERS", MappingProxyType({**framework.BUILDERS, CODE: counted})
    )
    after_run, after_rows = report_run(world, CODE, BALANCES)
    assert calls == [CODE]
    assert after_run["period_lock_id"] is None
    assert after_rows == before_rows
    assert after_run["control_totals"] == before_run["control_totals"]
    assert _keyed(after_rows)[K01_ROW]["contract_liability"] == {
        "amount": "29944.11",
        "currency": "USD",
    }


def test_cell_explanation_is_not_offered_on_an_as_locked_run(world: ReportWorld) -> None:
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    _freeze(world, lock_id, _frozen_by_registry(world, lock_id))
    run, _ = report_run(world, CODE, {**BALANCES, "period_lock_id": str(lock_id)})
    response = get(
        world.app,
        CELL.format(run_id=run["id"]),
        world.maya,
        {"row_key": K01_ROW, "column_key": "contract_liability"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == locked.EXPLAIN_LOCKED


# --- CLO8-SCOPE-R1: the scope of an as-locked run is the lock's ----------------------------------

UK: Final = "AVM-UK"


def _uk_entity(world: ReportWorld) -> UUID:
    """A second entity of the tenant on AVM-US's calendar (Maya may create entities)."""
    (calendar,) = world.place.rows(
        select(legal_entity.c.calendar_id).where(legal_entity.c.code == AVM_US)
    )
    created = entity(world.app, world.maya, code=UK, calendar_id=str(calendar["calendar_id"]))
    return UUID(str(created["id"]))


def _uk_only_reader(world: ReportWorld, uk_id: UUID) -> Actor:
    """A same-tenant Revenue Accountant whose ``report.run`` / ``report.export`` scope is AVM-UK
    only."""
    return holding(
        world.app, colleague(world.tenant_id, "bo"), "revenue_accountant", entity_ids=[uk_id]
    )


def _posted(
    world: ReportWorld, parameters: Mapping[str, Any], *, actor: Actor | None = None
) -> Any:
    return post(
        world.app,
        REPORT_RUNS,
        world.maya if actor is None else actor,
        {"report_code": CODE, "parameters": dict(parameters), "output_format": "JSON"},
    )


def _runs_with_lock(world: ReportWorld, lock_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(report_run_table.c.id).where(report_run_table.c.period_lock_id == lock_id)
    )


def test_selectors_that_differ_from_the_lock_are_refused_at_creation(world: ReportWorld) -> None:
    """Maya (AVM-US and AVM-UK) with a valid AVM-US lock: another entity, both entities, another
    admitted book, another period or a filter each end 422 by name; no run is persisted."""
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    _freeze(world, lock_id, _frozen_by_registry(world, lock_id))
    _uk_entity(world)
    cases: tuple[tuple[dict[str, Any], str, str], ...] = (
        (
            {"entity_codes": [UK]},
            "parameters.entity_codes",
            locked.ENTITY_MISMATCH.format(entity=AVM_US, lock=lock_id),
        ),
        (
            {"entity_codes": [AVM_US, UK]},
            "parameters.entity_codes",
            locked.ENTITY_MISMATCH.format(entity=AVM_US, lock=lock_id),
        ),
        (
            {"book": "IFRS15"},
            "parameters.book",
            locked.BOOK_MISMATCH.format(book="ASC606", lock=lock_id),
        ),
        (
            {"period_key": "FY2026-P08"},
            "parameters.period_key",
            locked.PERIOD_MISMATCH.format(key="period_key", period=SEPTEMBER_2026, lock=lock_id),
        ),
        (
            {"contract_external_id": K01},
            "parameters.contract_external_id",
            locked.NOT_A_LOCK_SELECTOR.format(key="contract_external_id", kind=KIND, lock=lock_id),
        ),
    )
    for extra, field, message in cases:
        response = _posted(world, {**BALANCES, **extra, "period_lock_id": str(lock_id)})
        assert response.status_code == 422, (extra, response.text)
        found = [item for item in response.json()["errors"] if item["field"] == field]
        assert [(item["rule_id"], item["message"]) for item in found] == [(locked.RULE, message)], (
            extra,
            response.json()["errors"],
        )
    assert _runs_with_lock(world, lock_id) == []


def test_same_scope_control_is_unchanged_and_the_persisted_scope_is_the_locks(
    world: ReportWorld,
) -> None:
    """Explicit matching selectors and omitted selectors both persist the lock's entity, book and
    period and produce the frozen CSV bytes; nothing else lands in the parameters."""
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    encoded = _frozen_by_registry(world, lock_id)
    _freeze(world, lock_id, encoded)
    explicit, _ = report_run(
        world, CODE, {**BALANCES, "period_lock_id": str(lock_id)}, output_format="CSV"
    )
    derived, _ = report_run(world, CODE, {"period_lock_id": str(lock_id)}, output_format="CSV")
    for run in (explicit, derived):
        assert run["output"]["sha256"] == encoded.file_sha256
        assert [ref["code"] for ref in run["entity_scope"]] == [AVM_US]
        assert run["book"] == "ASC606"
        assert {key: value for key, value in run["parameters"].items() if key != "known_at"} == {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "period_key": SEPTEMBER_2026,
            "known_at_basis": "record",  # CUTOFF-R1 (04 §16.9 rev 1.54): stored with every run
            "period_lock_id": str(lock_id),
        }
        downloaded = get(world.app, f"{REPORT_RUNS}/{run['id']}/output", world.maya)
        assert downloaded.content == encoded.content


def test_a_uk_only_reader_cannot_reach_an_avm_us_locked_run(world: ReportWorld) -> None:
    """The run's scope is the lock's entity; a same-tenant reader scoped to AVM-UK sees neither the
    listing nor the detail, data, output or explanation of an AVM-US as-locked run."""
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    _freeze(world, lock_id, _frozen_by_registry(world, lock_id))
    run, _ = report_run(world, CODE, {**BALANCES, "period_lock_id": str(lock_id)})
    reader = _uk_only_reader(world, _uk_entity(world))
    listed = get(world.app, REPORT_RUNS, reader, {"limit": "200"})
    assert listed.status_code == 200, listed.text
    assert run["id"] not in [item["id"] for item in listed.json()["items"]]
    # route-specific query parameters: the helper replaces a path query string (Codex -0304 R2)
    for path, params in (
        (f"{REPORT_RUNS}/{run['id']}", {}),
        (f"{REPORT_RUNS}/{run['id']}/data", {}),
        (f"{REPORT_RUNS}/{run['id']}/output", {}),
        (f"{REPORT_RUNS}/{run['id']}/output", {"part": "manifest"}),
        (CELL.format(run_id=run["id"]), {"row_key": K01_ROW, "column_key": "contract_liability"}),
    ):
        response = get(world.app, path, reader, params)
        assert response.status_code == 404, (path, params, response.text)
    # Maya, whose scope holds AVM-US, still reads it.
    assert get(world.app, f"{REPORT_RUNS}/{run['id']}", world.maya).status_code == 200


def test_an_inconsistent_as_locked_run_is_served_to_no_one(world: ReportWorld) -> None:
    """A QUEUED as-locked run whose persisted scope names AVM-UK behind the framework (the pre-fix
    defect, planted as a QUEUED copy of a real as-locked run with its own job): hidden from every
    list, refused by name when addressed by either reader, and FAILED by name when the job runs —
    the frozen AVM-US rows never leave."""
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    _freeze(world, lock_id, _frozen_by_registry(world, lock_id))
    uk_id = _uk_entity(world)
    # No UPDATE can plant the inconsistency: `parameters` and `entity_ids` are outside the IM-S
    # UPDATE allow-list (04 §14.2; DG-TST-21) AND the 0065 transition trigger refuses a change of
    # either in every status, QUEUED included (Codex 0727 (2)) — so a real as-locked run of the
    # lock is the model and its QUEUED copy is inserted with the AVM-UK scope under the tenant
    # context, as _completed_copy inserts the finished ones. RLS, grants and triggers unchanged.
    control, _ = report_run(world, CODE, {**BALANCES, "period_lock_id": str(lock_id)})
    (model,) = world.place.rows(
        select(report_run_table).where(report_run_table.c.id == UUID(str(control["id"])))
    )
    run_id, run_no, job_id = _queued_copy(
        world,
        model,
        entity_ids=[uk_id],
        parameters={**dict(model["parameters"]), "entity_codes": [UK]},
    )
    reader = _uk_only_reader(world, uk_id)
    for who in (world.maya, reader):
        listed = get(world.app, REPORT_RUNS, who, {"limit": "200"})
        assert str(run_id) not in [item["id"] for item in listed.json()["items"]]
        shown = get(world.app, f"{REPORT_RUNS}/{run_id}", who)
        assert shown.status_code == 404, shown.text
        assert shown.json()["detail"] == locked.RUN_SCOPE_INCONSISTENT.format(run_no=run_no)
    state = _settle(world, job_id)
    assert state["state"] == "FAILED", state
    (row,) = world.place.rows(
        select(
            report_run_table.c.status,
            report_run_table.c.problem,
            report_run_table.c.output_file_id,
        ).where(report_run_table.c.id == run_id)
    )
    assert (row["status"], row["output_file_id"]) == ("FAILED", None)
    assert row["problem"]["detail"] == locked.RUN_SCOPE_INCONSISTENT.format(run_no=run_no)
    assert row["problem"]["errors"][0]["rule_id"] == locked.RULE


# --- CLO8-SCOPE-R1 residual (Codex 1622): completed same-entity rows with inconsistent metadata ---


def _copy_number(model_no: str, changes: Mapping[str, Any]) -> str:
    """The report number of one completed copy: the model's suffix plus the first six hex characters
    of the SHA-256 of the sorted JSON of ``changes`` — deterministic and distinct per copy under
    ``ux_report_run__no (tenant_id, report_run_no)`` (migration 0048; Codex 1649 (b))."""
    digest = hashlib.sha256(json.dumps(changes, sort_keys=True, default=str).encode()).hexdigest()
    return f"RPT-S{model_no[-5:]}{digest[:6]}"


COPY_CHANGES: Final = (
    {"book_code": "IFRS15", "parameters": {"book": "IFRS15"}},
    {"parameters": {"period_key": "FY2026-P08"}},
    {"parameters": {"contract_external_id": K01}},
)


def test_completed_copy_numbers_are_distinct() -> None:
    """CPU: the three copies of the scenario below never collide on the unique report number."""
    numbers = [_copy_number("RPT-000012", changes) for changes in COPY_CHANGES]
    assert len(set(numbers)) == len(COPY_CHANGES), numbers
    assert all(number.startswith("RPT-S00012") for number in numbers)


def _completed_copy(
    world: ReportWorld, model: Mapping[str, Any], **changes: Any
) -> tuple[UUID, str]:
    """A SUCCEEDED copy of a real as-locked run with chosen stored values, inserted directly
    because a finished T-RPT-02 row is immutable (DB-03) — the shape the pre-fix resolver could
    have persisted; returns (id, report_run_no)."""
    row = {
        **model,
        "id": new_id(),
        "report_run_no": _copy_number(str(model["report_run_no"]), changes),
        "job_id": None,
        **changes,
    }
    with world.place.uow() as uow:
        uow.session.execute(insert(report_run_table).values(**row))
        uow.commit()
    return UUID(str(row["id"])), str(row["report_run_no"])


_UNFINISHED: Final = (
    "output_file_id",
    "output_sha256",
    "manifest_file_id",
    "row_count",
    "control_totals",
    "tie_out_results",
    "ledger_heads",
    "source_binding",
    "started_at",
    "finished_at",
    "problem",
)


def _queued_copy(
    world: ReportWorld, model: Mapping[str, Any], **changes: Any
) -> tuple[UUID, str, UUID]:
    """A QUEUED copy of a real as-locked run with chosen stored values and its own ``REPORT_RUN``
    job, inserted under the tenant context by the domain's unit of work in the framework's own
    ``_insert_run`` order (the job deferred, then the row naming it): the shape the pre-fix resolver
    could have persisted, which no UPDATE can make — ``parameters`` / ``entity_ids`` are outside the
    IM-S allow-list and the 0065 transition trigger refuses them in every status; returns
    (id, report_run_no, job_id)."""
    run_id = new_id()
    row: dict[str, Any] = {
        **model,
        "id": run_id,
        "report_run_no": _copy_number(str(model["report_run_no"]), changes),
        "status": RunStatus.QUEUED.value,
        **dict.fromkeys(_UNFINISHED),
        "child_report_run_ids": [],
        "disclosure_snapshot_ids": [],
        **changes,
    }
    with world.place.uow() as uow:
        deferred = uow.defer(
            JobKind.REPORT_RUN,
            {"report_run_id": str(run_id)},
            subject_type=framework.OBJECT_TYPE,
            subject_id=run_id,
        )
        row["job_id"] = deferred["id"]
        uow.session.execute(insert(report_run_table).values(**row))
        uow.commit()
    return run_id, str(row["report_run_no"]), UUID(str(deferred["id"]))


def test_completed_runs_with_inconsistent_metadata_are_hidden_and_refused_by_name(
    world: ReportWorld,
) -> None:
    """Same entity as the lock, but a completed row with book IFRS15, period FY2026-P08 or a
    formerly admitted contract filter: absent from the list; detail, data, output and explanation
    refused by name — without any worker execution. The matching completed control is served."""
    _, live_rows = report_run(world, CODE, BALANCES)
    lock_id = _lock_by_writer(world)
    encoded = _frozen_by_registry(world, lock_id)
    _freeze(world, lock_id, encoded)
    control, _ = report_run(world, CODE, {**BALANCES, "period_lock_id": str(lock_id)})
    (model,) = world.place.rows(
        select(report_run_table).where(report_run_table.c.id == UUID(str(control["id"])))
    )
    stored = dict(model["parameters"])
    copies = tuple(
        _completed_copy(
            world,
            model,
            **{
                key: ({**stored, **value} if key == "parameters" else value)
                for key, value in changes.items()
            },
        )
        for changes in COPY_CHANGES
    )
    assert len({run_no for _, run_no in copies}) == len(COPY_CHANGES)  # Codex 1649 (b)
    listed = get(world.app, REPORT_RUNS, world.maya, {"limit": "200"})
    assert listed.status_code == 200, listed.text
    ids = [item["id"] for item in listed.json()["items"]]
    assert control["id"] in ids
    for copy_id, run_no in copies:
        assert str(copy_id) not in ids
        # route-specific query parameters (Codex -0304 R2): the manifest part through `params`,
        # the explain cell with its row / column, ordinary reads with none.
        for path, params in (
            (f"{REPORT_RUNS}/{copy_id}", {}),
            (f"{REPORT_RUNS}/{copy_id}/data", {}),
            (f"{REPORT_RUNS}/{copy_id}/output", {}),
            (f"{REPORT_RUNS}/{copy_id}/output", {"part": "manifest"}),
            (CELL.format(run_id=copy_id), {"row_key": K01_ROW, "column_key": "contract_liability"}),
        ):
            response = get(world.app, path, world.maya, params)
            assert response.status_code == 404, (path, params, response.text)
            assert response.json()["detail"] == locked.RUN_SCOPE_INCONSISTENT.format(run_no=run_no)
        rerun = post(world.app, f"{REPORT_RUNS}/{copy_id}/rerun", world.maya, {})
        assert rerun.status_code == 404, rerun.text
    # The matching completed control is served unchanged.
    shown = get(world.app, f"{REPORT_RUNS}/{control['id']}", world.maya)
    assert shown.status_code == 200 and shown.json()["status"] == "SUCCEEDED"
    rows = get(world.app, f"{REPORT_RUNS}/{control['id']}/data", world.maya, {"limit": "200"})
    assert rows.status_code == 200
    assert _keyed(rows.json()["items"])[K01_ROW]["contract_liability"] == "29944.11"


def test_as_locked_register_without_its_snapshot_refuses_by_name(world: ReportWorld) -> None:
    """CLO-8b (F-CLO record §25.27): the modification register admits ``period_lock_id`` like every
    dataset report; a lock holding no MODIFICATION_REGISTER snapshot ends the run FAILED with the
    S15-R-19 refusal naming report, kind and lock — never live rows under an "as locked" label. The
    manual-adjustment register joins this scenario with its producer (creation needs a builder)."""
    lock_id = _lock_by_writer(world)  # no dataset frozen
    kind = SnapshotKind.MODIFICATION_REGISTER.value
    missing = _settled_run(world, "modification_register", {"period_lock_id": str(lock_id)})
    problem = _refusal(missing)
    assert problem["detail"] == locked.SNAPSHOT_MISSING.format(
        lock=lock_id, kind=kind, code="modification_register"
    )


def _fresh_controller(app: FastAPI, clock: FrozenClock, tenant_id: UUID) -> Actor:
    """An enrolled Controller of the tenant (``colleague`` joins it; ``member`` would provision
    another) with a fresh TOTP verification (BR-PLT-06). The step-up moves the clock one TOTP step
    first: a code of the enrolment's step is a replay (T-PLT-04 ``last_used_step``)."""
    someone = colleague(tenant_id, "cora")
    assign(someone, "controller")
    actor = enrolled(app, clock, someone)
    clock.advance(totp.STEP)
    return step_up(app, clock, actor)


def _acknowledged_journal(world: ReportWorld, period_key: str) -> None:
    """The period's journal REALLY calculated by the worker (``worlds.journal_run``): it covers the
    period's sealed activity, which ``JE_COMPLETE`` compares chain range by chain range and account
    by account — a probe run (``close_world.acknowledged_run_for``) covers none of K-01's and the
    gate refuses the lock request. The run and then its batches move along E-34 draft → approved →
    exported → acknowledged with their set-once instants (DB-03), as the probe's do: the
    acknowledgement command (CLO-14) is not on this tree."""
    run_id = UUID(str(journal_run(world, period_key=period_key)["id"]))
    now = world.place.clock.now()
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        for state, stamps in (
            ("approved", {"approved_at": now}),
            ("exported", {"exported_at": now}),
            ("acknowledged", {"acknowledged_at": now}),
        ):
            session.execute(
                update(journal_run_table)
                .where(journal_run_table.c.id == run_id)
                .values(state=state, **stamps)
            )
        batch_steps: tuple[tuple[str, dict[str, Any]], ...] = (
            ("approved", {}),
            ("exported", {"exported_at": now, "attempt_count": 1}),
            ("acknowledged", {"acknowledged_at": now}),
        )
        for state, stamps in batch_steps:
            session.execute(
                update(journal_batch)
                .where(journal_batch.c.journal_run_id == run_id)
                .values(state=state, **stamps)
            )


def test_as_locked_run_on_the_august_lock_returns_the_wld_x_03_liability(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """BUILD_SPEC RPS-3 acceptance (WLD-X-03), the OWED as-locked RUN witness (team lead,
    2026-09-22) and the witness of supervisor ruling R-4 (2026-09-29; P1):
    ``k01_pellworth`` through 31 Aug 2026, August locked through the PUBLIC path (start-close, the
    period's calculated and acknowledged journal, the reviewed reconciliations, ``request_lock``, a
    Controller's approval) on the record-time clock, so the decision's freeze reads the period's
    real populations: ALL TWELVE datasets are frozen by the F-RPS registry — the two rollforwards
    with their line rows and the by-contract row of ``SF-ORD-10001``, the rows whose key column
    the builders left out until lane FIX-D2 (the decision answered 500: ``row OPENING lacks the
    required column contract_external_id``) — and a ``contract_balances`` run WITH
    ``period_lock_id`` of that lock returns contract liability 39,708.49 for ``SF-ORD-10001``: the
    frozen dataset served by the framework, never the live builder."""
    from erev_api.db.tables import period_lock
    from erev_api.domain.reports.builders import contract_balance_rollforward, rpo
    from erev_api.schemas.periods import PeriodLockRequestIn
    from support.close_world import (
        close_run_succeeded_for,
        periods_closed_before,
        reviewed_reconciliations_for,
    )
    from support.reference import PERIODS, approve
    from support.worlds import AUGUST_2026

    pellworth = on_record_time(k01_pellworth(app, keyring, clock, files, through=date(2026, 8, 31)))
    maya = pellworth.maya
    # PRD WLD-P-02 / BR-CLS-08 (supervisor ruling R-6): K-01's January to July are closed before
    # August is brought to its lock — fixture state; their sealed lines stay as they are.
    periods_closed_before(
        pellworth.place, app, maya, entity_id=pellworth.entity_id, before=AUGUST_2026
    )
    (august,) = [
        item
        for item in periods(app, maya, entity=AVM_US)
        if item["period"]["period_key"] == AUGUST_2026
    ]
    started = post(
        app,
        f"{PERIODS}/{august['id']}/start-close",
        maya,
        {"comment": "August close"},
        if_match=f'"r{august["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    period_id = UUID(str(august["period"]["id"]))
    _acknowledged_journal(pellworth, AUGUST_2026)
    context = DbContext(tenant_id=pellworth.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=pellworth.tenant_id,
            entity_id=pellworth.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
        # fixture state for the gate CLOSE_RUN_COMPLETED (supervisor ruling R-114 (b))
        close_run_succeeded_for(
            session,
            tenant_id=pellworth.tenant_id,
            entity_id=pellworth.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
    with pellworth.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=UUID(str(august["id"])),
            body=PeriodLockRequestIn(certification_comment="August 2026 close complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    controller = _fresh_controller(app, clock, pellworth.tenant_id)
    decided = approve(app, str(out.approval_request_id), controller)
    assert decided.status_code == 200, decided.text
    with pellworth.place.uow() as uow:
        lock_id = uow.session.execute(
            select(period_lock.c.id).where(
                period_lock.c.period_id == period_id, period_lock.c.kind == LockKind.LOCK.value
            )
        ).scalar_one()
        frozen = {
            str(getattr(kind, "value", kind)): int(row_count)
            for kind, row_count in uow.session.execute(
                select(lock_snapshot.c.snapshot_kind, lock_snapshot.c.row_count).where(
                    lock_snapshot.c.period_lock_id == lock_id
                )
            )
        }
    # R-4: twelve of twelve through the public path, the rollforwards populated — their line
    # rows (nine and ten) and the by-contract row of the one contract.
    assert sorted(frozen) == sorted(kind.value for kind in SnapshotKind) and len(frozen) == 12
    assert frozen[SnapshotKind.CONTRACT_BALANCE_ROLLFORWARD.value] == (
        len(contract_balance_rollforward.LINES) + 1
    )
    assert frozen[SnapshotKind.RPO_ROLLFORWARD.value] == len(rpo.ROLLFORWARD_LINES) + 1
    assert frozen[SnapshotKind.CONTRACT_BALANCES.value] == 1
    # The datasets as the lock STORED them (read back and verified, S15-INV-06): both rollforwards
    # are accepted by the re-lock consumer under their key, and CONTRACT_BALANCES holds WLD-X-03.
    with pellworth.place.uow() as uow:
        stored = {
            code: locked.locked_dataset(uow, report_code=code, lock_id=UUID(str(lock_id)))
            for code in ("contract_balance_rollforward", "rpo_rollforward", CODE)
        }
    for code, lines in (
        ("contract_balance_rollforward", contract_balance_rollforward.LINES),
        ("rpo_rollforward", rpo.ROLLFORWARD_LINES),
    ):
        dataset = stored[code]
        headers, dataset_rows = locked._rows(dataset.content)
        keyed = relock_diff._keyed(
            dataset.kind, headers, dataset_rows, relock_diff.key_columns_of(dataset.kind)
        )
        assert set(keyed) == {*((line, "", "USD") for line in lines), ("", K01, "USD")}, code
    _, balance_rows = locked._rows(stored[CODE].content)
    assert [(row["contract_external_id"], row["contract_liability"]) for row in balance_rows] == [
        (K01, "39708.49")
    ]
    run, rows = report_run(
        pellworth,
        CODE,
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "period_key": AUGUST_2026,
            "period_lock_id": str(lock_id),
        },
    )
    assert run["status"] == "SUCCEEDED" and run["period_lock_id"] == str(lock_id)
    (k01,) = [row for row in rows if row["contract_external_id"] == K01]
    assert k01["contract_liability"] == "39708.49"  # WLD-X-03: the frozen text cell, not live
