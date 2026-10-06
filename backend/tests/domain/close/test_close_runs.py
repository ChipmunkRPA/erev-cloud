"""CLO-19 close run orchestration, recompute and quarantine (BUILD_SPEC CLO-19 acceptance; 03
REQ-CLS-012, REQ-CLS-013, REQ-OPS-006; 04 T-CLS-01, E-62, §15.4 ``CLOSE_RUN_FAILED``, §16.8
API-S-CloseRun; 05 RCP-17, RCP-19, RCP-20, JOB-03, JOB-05, JOB-07; PRD SM-14, NFR-14, NTF-05;
SCREENS_B §1.2; dev-guide DG-KRN-JOB-03 to DG-KRN-JOB-05; supervisor ruling R-79).

World: ``support.factories.seat_world`` — AVM-US (USD) with FY2026-P01 to P09 open, Maya (Revenue
Accountant: ``period.close``), Marcus (Controller: ``period.lock``, ``exception.waive``), Priya
(SSP Approver). Each contract is its own combination group: booked, activated and computed through
the domain commands, so a group is clean until the test appends an event to it (05 RCP-17) or has
a policy override approved for it (the "approved re-pin").

The tests act as the worker: ``support.close_runs.work`` delivers the ``CLOSE_RUN`` job, and in
the job's pauses ``Workers`` stands for the rest of the pool or nobody does (``unattended``).

The assertions end at the step under test: the steps after ``RECOMPUTE_DIRTY`` are BUILD_SPEC
CLO-20's and have their own module.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    close_run,
    combination_group,
    contract,
    contract_computation,
    exception_item,
    file_object,
    import_upload,
    integration_connection,
    job,
    legal_entity,
    notification,
    sync_run,
)
from erev_api.domain.close import close_runs, gates
from erev_api.domain.contracts import bundles, computation, compute_job
from erev_api.domain.contracts.commands import BookedContract
from erev_api.enums import ComputationTrigger, ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support import close_runs as runs
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.factories import (
    AVM_US_CHART,
    SeatWorld,
    appended,
    booked_contract,
    computed,
    drafted_override,
    seat_body,
    seat_line,
    seat_world,
)
from support.principals import step_up
from support.reference import approve, entity, get, periods, post, slug
from support.rows import file_object_values, import_upload_values, integration_connection_values

AVM_US = "AVM-US"
BOOK = "ASC606"
SEPTEMBER = "FY2026-P09"
OCTOBER = "FY2026-P10"
POLICY_OVERRIDES = "/api/v1/policy-overrides"
GROUPS = "/api/v1/combination-groups"
PERIODS = "/api/v1/periods"
EXCEPTIONS = "/api/v1/exceptions"
CANCEL_REASON = "Restarting after the correction."
RECOMPUTE = "RECOMPUTE_DIRTY"
FIRST_STEPS = ("CUTOFF", "INTERFACE_COMPLETENESS", "EXCEPTION_CHECK")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


@pytest.fixture
def runtime(keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


# --- the world's contracts ------------------------------------------------------------------------


def _contract(world: SeatWorld, external_id: str) -> BookedContract:
    """Ten seats for a year from 1 Sep 2026, booked, activated and computed: a clean group."""
    line = seat_line("O1", seats="10", price="24000.00", start="2026-09-01", end="2027-08-31")
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )
    booked = booked_contract(world.place, body, activate=True)
    computed(world.place, UUID(str(booked.combination_group["id"])))
    return booked


def _group(booked: BookedContract) -> UUID:
    return UUID(str(booked.combination_group["id"]))


def _billed(world: SeatWorld, booked: BookedContract, invoice: str, *, head: int = 2) -> None:
    """A new event on the contract: its group is dirty until it is computed (05 RCP-17).
    ``head`` is the stream version it follows: 2 for a contract booked and activated."""
    contract_id = UUID(str(booked.contract["id"]))
    day = date(2026, 9, 1)
    appended(
        world.place,
        contract_id,
        head,
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=day,
                payload=BillingRecordedV1(
                    invoice_number=invoice,
                    line_external_id=f"{invoice}-1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="2000.00", currency="USD"),
                    issue_date=day,
                ),
            )
        ],
    )


def _combined(world: SeatWorld, *booked: BookedContract) -> UUID:
    """The contracts combined into one group by the approved command (REQ-CON-009): Maya
    proposes and submits, Marcus approves, and the approval computes the group, which is clean
    after it. Returns the group id."""
    app, maya = world.app, world.place.author
    proposed = post(
        app,
        GROUPS,
        maya,
        {
            "contract_ids": [str(item.contract["id"]) for item in booked],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(str(proposed.json()["id"]))
    submitted = post(app, f"{GROUPS}/{group_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert decided.status_code == 200, decided.text
    row = world.place.rows(
        select(combination_group.c.status, combination_group.c.dirty_since).where(
            combination_group.c.id == group_id
        )
    )[0]
    assert (str(row["status"]), row["dirty_since"]) == ("APPLIED", None)
    return group_id


def _head(world: SeatWorld, booked: BookedContract) -> int:
    return int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(
                contract.c.id == UUID(str(booked.contract["id"]))
            )
        )
    )


def _repinned(world: SeatWorld, booked: BookedContract) -> None:
    """An approved re-pin: a contract-level override of POL-053 ``returns.returned_units_scope``,
    submitted by Maya and approved by Marcus. The contract has no returns, so the value changes no
    figure; the approval marks its group dirty (05 RCP-17). Release 1.0 creates no override (04
    T-CON-23 rev 1.322), so the DRAFT row is the fixture's, written as Maya's; the submit and the
    approval, whose mark this helper is used for, are the product's own."""
    maya = world.place.author
    override_id = drafted_override(
        world.place,
        UUID(str(booked.contract["id"])),
        "returns.returned_units_scope",
        "RESTORE_REMAINING_QUANTITY",
        rationale="The order form restores returned seats to the remaining quantity.",
    )
    submitted = post(
        world.app, f"{POLICY_OVERRIDES}/{override_id}/submit", maya, {"comment": "Ready"}
    )
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def _dirty(world: SeatWorld) -> set[UUID]:
    return {
        UUID(str(row["id"]))
        for row in world.place.rows(
            select(combination_group.c.id).where(combination_group.c.dirty_since.is_not(None))
        )
    }


def _computations(world: SeatWorld, group_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            contract_computation.c.id,
            contract_computation.c.status,
            contract_computation.c.job_id,
            contract_computation.c.trigger,
        )
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at, contract_computation.c.id)
    )


def _september(world: SeatWorld) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.place.author, entity=AVM_US)
        if item["period"]["period_key"] == SEPTEMBER
    ]
    return found


def _september_blockers(world: SeatWorld) -> dict[str, int]:
    """API-S-Period ``blockers`` of September, from ``GET /periods/{id}``: a row of the list
    answers them null (04 §16.8 rev 1.199)."""
    shown = get(world.app, f"/api/v1/periods/{_september(world)['id']}", world.place.author)
    assert shown.status_code == 200, shown.text
    return dict(shown.json()["blockers"])


def _gates(world: SeatWorld) -> dict[str, tuple[str, int | None]]:
    """(status, count) of each gate of AVM-US September as evaluated now."""
    period_id = UUID(str(_september(world)["period"]["id"]))
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, world.entity_id, BOOK, period_id)
        uow.commit()
    return {result.gate_check_code: (result.status.value, result.count) for result in results}


def _started(world: SeatWorld) -> tuple[str, UUID]:
    return runs.started(world.app, world.place.author, entity_code=AVM_US, period_key=SEPTEMBER)


def _statuses(run: dict[str, Any], codes: tuple[str, ...] = runs.STEP_CODES) -> list[str]:
    return [runs.step(run, code)["status"] for code in codes]


def _refusing(monkeypatch: pytest.MonkeyPatch, *external_ids: str) -> None:
    """The engine raises ``ENGINE_INVARIANT_VIOLATED`` for the group of each of
    ``external_ids`` and computes every other group as it does."""
    real = computation.default_engine()

    def run(bundle: InputBundle) -> OutputBundle:
        for external_id in external_ids:
            if any(event.contract_key == external_id for event in bundle.events):
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "the allocated amounts do not sum to the transaction price",
                    subject_key=f"{external_id}/O1",
                    detail={"identity": "DB-17 V1"},
                )
        return real(bundle)

    monkeypatch.setattr(computation, "default_engine", lambda: run)


def _breaking(monkeypatch: pytest.MonkeyPatch, times: int) -> list[UUID]:
    """``compute_group`` raises an unexpected error the first ``times`` calls: a step that fails.
    Returns the groups it was asked for."""
    real: Callable[..., Any] = compute_job.compute_group
    asked: list[UUID] = []

    def compute(uow: Any, group_id: UUID, **options: Any) -> Any:
        asked.append(group_id)
        if len(asked) <= times:
            raise RuntimeError("the database connection was lost")
        return real(uow, group_id, **options)

    monkeypatch.setattr(compute_job, "compute_group", compute)
    return asked


# --- the fixed steps ------------------------------------------------------------------------------


def test_steps_in_fixed_order(
    app: FastAPI,
    clock: FrozenClock,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-19: a new run's ``steps`` array holds the 14 codes ``CUTOFF``,
    ``INTERFACE_COMPLETENESS``, ``EXCEPTION_CHECK``, ``RECOMPUTE_DIRTY``, ``RELEASE_SCHEDULES``,
    ``FX_REMEASUREMENT``, ``NETTING_RECLASS``, ``INVARIANTS``, ``JOURNAL_SUMMARIZATION``,
    ``EXPORT``, ``ACKNOWLEDGEMENT_WAIT``, ``GL_TIE_OUT``, ``DATASET_FREEZE``, ``LOCK`` in that
    order, each ``PENDING``; ``cutoff_known_at`` is fixed at start (T-CLS-01)."""
    maya = world.place.author
    _contract(world, "SF-ORD-10700")
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)

    run = runs.shown(app, maya, run_id)
    assert [step["step_code"] for step in run["steps"]] == [
        "CUTOFF",
        "INTERFACE_COMPLETENESS",
        "EXCEPTION_CHECK",
        "RECOMPUTE_DIRTY",
        "RELEASE_SCHEDULES",
        "FX_REMEASUREMENT",
        "NETTING_RECLASS",
        "INVARIANTS",
        "JOURNAL_SUMMARIZATION",
        "EXPORT",
        "ACKNOWLEDGEMENT_WAIT",
        "GL_TIE_OUT",
        "DATASET_FREEZE",
        "LOCK",
    ]
    assert all(
        (
            step["status"],
            step["started_at"],
            step["finished_at"],
            step["counts"],
            step["problem"],
        )
        == ("PENDING", None, None, {}, None)
        for step in run["steps"]
    )
    assert (run["status"], run["current_step_code"], run["started_at"], run["finished_at"]) == (
        "PENDING",
        None,
        None,
        None,
    )
    assert (run["entity"]["code"], run["book"], run["period"]["period_key"]) == (
        AVM_US,
        BOOK,
        SEPTEMBER,
    )
    assert run["close_run_no"].startswith("CLS-") and run["counts"] == {}
    assert run["job"] == {
        "id": str(job_id),
        "state": "QUEUED",
        "progress": {"done": 0, "total": None},
    }
    assert run["created_by"]["id"] == str(maya.member.user_id)
    # The cutoff is fixed when the run is started: the record-time instant of the command, which
    # is not earlier than the application instant.
    cutoff = run["cutoff_known_at"]
    assert datetime.fromisoformat(cutoff) >= clock.now()
    (stored,) = world.place.rows(
        select(close_run.c.job_id, close_run.c.cutoff_known_at).where(
            close_run.c.id == UUID(run_id)
        )
    )
    assert (stored["job_id"], stored["cutoff_known_at"]) == (
        job_id,
        datetime.fromisoformat(cutoff),
    )

    # The job executes the steps; the array keeps its order and the cutoff its instant.
    clock.advance(timedelta(minutes=5))
    runs.work(world.place.tenant_id, runtime, job_id)
    after = runs.shown(app, maya, run_id)
    assert [step["step_code"] for step in after["steps"]] == list(runs.STEP_CODES)
    assert after["cutoff_known_at"] == cutoff
    first = [runs.step(after, code) for code in (*FIRST_STEPS, RECOMPUTE)]
    assert [step["status"] for step in first] == ["SUCCEEDED"] * 4
    at = clock.now().isoformat().replace("+00:00", "Z")
    assert all((step["started_at"], step["finished_at"]) == (at, at) for step in first)
    assert datetime.fromisoformat(after["started_at"]) == clock.now()
    assert runs.step(after, "LOCK")["status"] == "PENDING"  # the lock job's (BS4-D-03)
    # What the two checks recorded (T-CLS-01 step counts): no interface run, no open exception.
    assert runs.step(after, "INTERFACE_COMPLETENESS")["counts"] == {
        "interface_runs_complete": 0,
        "interface_failures": 0,
    }
    assert runs.step(after, "EXCEPTION_CHECK")["counts"] == {"blocking_exceptions": 0}
    assert runs.step(after, RECOMPUTE)["counts"] == {
        "groups_recomputed": 0,
        "groups_quarantined": 0,
        "groups_waived": 0,
    }


def test_interface_completeness_counts_the_runs_entity(
    app: FastAPI,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-103 (a) (04 T-CLS-01 "Step counts"): ``INTERFACE_COMPLETENESS`` counts
    the imports ``COMMITTED`` and the sync runs ``SUCCEEDED`` that name the run's entity or name
    none — a figure of one entity's close is not drawn from another entity's interfaces. For
    AVM-US: an upload whose rows name AVM-US, a workspace-level upload and one whose entities are
    not resolved count, an upload of AVM-UK does not; a sync run of a connection that serves
    AVM-US and one of a connection that serves every entity count, one of AVM-UK's does not."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    us = world.entity_id
    calendar_id = world.place.scalar(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == us)
    )
    uk = UUID(str(entity(app, maya, code="AVM-UK", calendar_id=str(calendar_id))["id"]))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        for named in ([us], [uk], [], None):
            stored = file_object_values(tenant_id)
            session.execute(insert(file_object).values(**stored))
            session.execute(
                insert(import_upload).values(
                    **import_upload_values(
                        tenant_id,
                        file_object_id=stored["id"],
                        status="COMMITTED",
                        named_entity_ids=named,
                    )
                )
            )
        for served in ([us], [uk], []):
            connection = integration_connection_values(tenant_id, entity_ids=served)
            session.execute(insert(integration_connection).values(**connection))
            session.execute(
                insert(sync_run).values(
                    tenant_id=tenant_id,
                    id=runs.new_row_id(),
                    integration_connection_id=connection["id"],
                    kind="INBOUND_POLL",
                    status="SUCCEEDED",
                    checkpoint_before={},
                    created_by_kind="SYSTEM",
                    updated_by_kind="SYSTEM",
                )
            )
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    runs.work(tenant_id, runtime, job_id)
    counted = runs.step(runs.shown(app, maya, run_id), "INTERFACE_COMPLETENESS")
    # three of the four uploads and two of the three sync runs are AVM-US's
    assert (counted["status"], counted["counts"]) == (
        "SUCCEEDED",
        {"interface_runs_complete": 5, "interface_failures": 0},
    )


def test_execution_order_is_fx_release_netting() -> None:
    """Supervisor ruling R-79 (b): the array of T-CLS-01 is the display order; the job executes
    ``FX_REMEASUREMENT`` before ``RELEASE_SCHEDULES`` (05 RCP-08 rev 1.9: the FX pass, then the
    release pass, then the netting reclass) and every other step in the order of the array;
    ``LOCK`` is not executed by the job (BS4-D-03)."""
    assert close_runs.STEP_CODES == runs.STEP_CODES
    assert close_runs.EXECUTED_STEPS == (
        "CUTOFF",
        "INTERFACE_COMPLETENESS",
        "EXCEPTION_CHECK",
        "RECOMPUTE_DIRTY",
        "FX_REMEASUREMENT",
        "RELEASE_SCHEDULES",
        "NETTING_RECLASS",
        "INVARIANTS",
        "JOURNAL_SUMMARIZATION",
        "EXPORT",
        "ACKNOWLEDGEMENT_WAIT",
        "GL_TIE_OUT",
        "DATASET_FREEZE",
    )
    assert sorted(close_runs.EXECUTED_STEPS) == sorted(runs.STEP_CODES[:-1])
    assert set(close_runs.STEPS) == set(close_runs.EXECUTED_STEPS)


def test_chunks_of_250_groups() -> None:
    """05 RCP-19: the dirty groups are split into chunks of 250 groups, one child job each."""
    ids = [UUID(int=number) for number in range(1, 502)]
    found = close_runs.chunks(ids)
    assert close_runs.CHUNK_SIZE == 250
    assert [len(chunk) for chunk in found] == [250, 250, 1]
    assert [group_id for chunk in found for group_id in chunk] == ids
    assert close_runs.chunks([]) == []
    assert close_runs.chunks(ids[:250]) == [ids[:250]]


# --- recompute ------------------------------------------------------------------------------------


def test_recompute_only_dirty_groups(
    app: FastAPI,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-19: with two groups dirty (one new event, one approved re-pin) and three
    clean, ``RECOMPUTE_DIRTY`` defers child ``CONTRACT_COMPUTE`` jobs in chunks of 250 groups with
    ``parent_job_id`` = the close-run job and summary counts ``groups_recomputed = 2``,
    ``groups_quarantined = 0``; the clean groups get no ``contract_computation`` row (REQ-CLS-013;
    RCP-17, RCP-19)."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    booked = [_contract(world, f"SF-ORD-1071{index}") for index in range(1, 6)]
    with_event, repinned, *clean = booked
    _billed(world, with_event, "INV-US-7101")
    _repinned(world, repinned)
    dirty = {_group(with_event), _group(repinned)}
    assert _dirty(world) == dirty
    before = {_group(item): _computations(world, _group(item)) for item in booked}
    assert all(len(found) == 1 for found in before.values())

    workers = runs.attended(monkeypatch, runs.Workers(tenant_id, runtime))
    run_id, job_id = _started(world)
    runs.work(tenant_id, runtime, job_id)

    # One child job for the two groups (one chunk of at most 250), run by the pool.
    (child,) = runs.children(tenant_id, job_id)
    assert (str(child["kind"]), str(child["queue"]), child["parent_job_id"]) == (
        "CONTRACT_COMPUTE",
        "compute",
        job_id,
    )
    assert child["params"]["combination_group_ids"] == sorted(str(group) for group in dirty)
    assert child["params"]["trigger"] == "COMMAND"
    assert (str(child["state"]), child["result"]["counts"]) == (
        "SUCCEEDED",
        {"groups": 2, "succeeded": 2, "quarantined": 0, "failed": 0},
    )
    assert workers.delivered == [child["id"]]

    run = runs.shown(app, maya, run_id)
    step = runs.step(run, RECOMPUTE)
    assert (step["status"], step["counts"]) == (
        "SUCCEEDED",
        {"groups_recomputed": 2, "groups_quarantined": 0, "groups_waived": 0},
    )
    assert (run["counts"]["groups_recomputed"], run["counts"]["groups_quarantined"]) == (2, 0)
    # The dirty groups were computed once more, by the child job; the clean ones were not.
    for item in booked:
        found = _computations(world, _group(item))
        if _group(item) in dirty:
            assert [str(row["status"]) for row in found] == ["SUCCEEDED", "SUCCEEDED"]
            assert (found[-1]["job_id"], str(found[-1]["trigger"])) == (child["id"], "COMMAND")
        else:
            assert found == before[_group(item)]
    assert _dirty(world) == set()
    assert _gates(world)[gates.NO_DIRTY_GROUPS] == ("PASSED", 0)


def test_queued_child_is_taken_over(
    app: FastAPI,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 RCP-19 (rev 1.73): a child no worker has started by the second poll is cancelled and its
    chunk is computed by the close-run job itself, one transaction per group, so a close run whose
    children find no free worker still finishes; the child's task, delivered later, finds nothing
    to do."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    first, second = (_contract(world, f"SF-ORD-1072{index}") for index in (1, 2))
    _billed(world, first, "INV-US-7201")
    _billed(world, second, "INV-US-7202")
    pauses = runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    finished = runs.work(tenant_id, runtime, job_id)

    assert pauses == [close_runs.POLL_SECONDS]  # seen queued twice: taken over at the second poll
    (child,) = runs.children(tenant_id, job_id)
    assert (str(child["state"]), child["result"]) == ("CANCELLED", None)
    assert child["cancel_requested_at"] is not None and child["finished_at"] is not None
    step = runs.step(runs.shown(app, maya, run_id), RECOMPUTE)
    assert (step["status"], step["counts"]["groups_recomputed"]) == ("SUCCEEDED", 2)
    for booked in (first, second):
        found = _computations(world, _group(booked))
        assert [str(row["status"]) for row in found] == ["SUCCEEDED", "SUCCEEDED"]
        assert found[-1]["job_id"] == job_id  # computed by the close-run job
    assert _dirty(world) == set()
    assert finished["progress_total"] == 2
    # A worker that fetches the cancelled child's task afterwards computes nothing (05 JOB-02).
    again = runs.work(tenant_id, runtime, child["id"])
    assert str(again["state"]) == "CANCELLED"
    assert [len(_computations(world, _group(booked))) for booked in (first, second)] == [2, 2]


def test_child_jobs_exempt_from_slots(
    app: FastAPI,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-19: with ``platform.job_concurrency = 1``, child ``CONTRACT_COMPUTE`` jobs of
    a ``RUNNING`` close run acquire no per-tenant slot and complete (DG-KRN-JOB-03; 05 JOB-03)."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    dirty = _contract(world, "SF-ORD-10731")
    other = _contract(world, "SF-ORD-10732")
    _billed(world, dirty, "INV-US-7301")
    # A compute job that is nobody's child, queued before the run: it needs the tenant's one slot.
    with world.place.uow() as uow:
        loose = UUID(str(compute_job.defer_compute(uow, _group(other))["id"]))
        uow.commit()

    seen: dict[str, Any] = {}

    def while_waiting() -> None:
        # The close-run job is RUNNING and holds the tenant's only slot.
        seen.setdefault("parent", str(runs.job_row(tenant_id, job_id)["state"]))

    workers = runs.attended(
        monkeypatch, runs.Workers(tenant_id, runtime, concurrency=1, before=while_waiting)
    )
    run_id, job_id = _started(world)
    finished = runs.work(tenant_id, runtime, job_id, concurrency=1)

    assert seen["parent"] == "RUNNING"
    (child,) = runs.children(tenant_id, job_id)
    # Both were delivered in the same pause, the loose job first: it found no slot and stays
    # queued; the child took none and completed.
    assert workers.delivered[:2] == [loose, child["id"]]
    assert str(child["state"]) == "SUCCEEDED"
    assert str(runs.job_row(tenant_id, loose)["state"]) == "QUEUED"
    assert len(_computations(world, _group(other))) == 1
    step = runs.step(runs.shown(app, maya, run_id), RECOMPUTE)
    assert (step["status"], step["counts"]["groups_recomputed"]) == ("SUCCEEDED", 1)
    assert str(finished["state"]) != "QUEUED"
    # With the close-run job ended its slot is free again: the loose job runs.
    assert str(runs.work(tenant_id, runtime, loose, concurrency=1)["state"]) == "SUCCEEDED"


# --- quarantine -----------------------------------------------------------------------------------


def _quarantined_run(
    world: SeatWorld, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, UUID, list[BookedContract]]:
    """Three dirty groups, the second of which the engine refuses: the run as the job left it."""
    booked = [_contract(world, f"SF-ORD-1074{index}") for index in (1, 2, 3)]
    for index, item in enumerate(booked, start=1):
        _billed(world, item, f"INV-US-740{index}")
    _refusing(monkeypatch, "SF-ORD-10742")
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    finished = runs.work(world.place.tenant_id, runtime, job_id)
    assert str(finished["state"]) == "SUCCEEDED_WITH_EXCEPTIONS"
    return run_id, job_id, booked


def _engine_items(world: SeatWorld, group_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(exception_item)
        .where(exception_item.c.combination_group_id == group_id)
        .order_by(exception_item.c.created_at, exception_item.c.id)
    )


def test_quarantine_continues_and_blocks_lock(
    app: FastAPI,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-19: a group whose computation raises ``ENGINE_INVARIANT_VIOLATED`` receives a
    ``QUARANTINED`` computation and one exception item ``ENGINE_INVARIANT_VIOLATION`` (source
    ``ENGINE``, severity ``BLOCKING``, ``dedupe_key``
    ``ENGINE:ENGINE_INVARIANT_VIOLATION:<group id>``); the other groups finish; the run ends
    ``BLOCKED``; ``NO_DIRTY_GROUPS`` and ``EXCEPTIONS_CLEARED`` fail (RCP-20)."""
    maya = world.place.author
    run_id, job_id, (first, refused, third) = _quarantined_run(world, runtime, monkeypatch)

    found = _computations(world, _group(refused))
    assert [str(row["status"]) for row in found] == ["SUCCEEDED", "QUARANTINED"]
    (item,) = _engine_items(world, _group(refused))
    assert (
        str(item["source"]),
        item["code"],
        str(item["severity"]),
        str(item["status"]),
        item["dedupe_key"],
        item["occurrence_count"],
    ) == (
        "ENGINE",
        "ENGINE_INVARIANT_VIOLATION",
        "BLOCKING",
        "OPEN",
        f"ENGINE:ENGINE_INVARIANT_VIOLATION:{_group(refused)}",
        1,
    )
    # The other groups finish.
    for booked in (first, third):
        assert [str(row["status"]) for row in _computations(world, _group(booked))] == [
            "SUCCEEDED",
            "SUCCEEDED",
        ]
    assert _dirty(world) == {_group(refused)}

    run = runs.shown(app, maya, run_id)
    assert (run["status"], run["current_step_code"]) == ("BLOCKED", RECOMPUTE)
    assert run["finished_at"] is not None
    step = runs.step(run, RECOMPUTE)
    assert (step["status"], step["counts"]) == (
        "BLOCKED",
        {"groups_recomputed": 2, "groups_quarantined": 1, "groups_waived": 0},
    )
    assert (run["counts"]["groups_recomputed"], run["counts"]["groups_quarantined"]) == (2, 1)
    assert _statuses(run, FIRST_STEPS) == ["SUCCEEDED"] * 3
    assert set(_statuses(run, runs.STEP_CODES[4:])) == {"PENDING"}
    assert run["job"]["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    # The lock stays blocked through the two gates.
    found_gates = _gates(world)
    assert found_gates[gates.NO_DIRTY_GROUPS] == ("FAILED", 1)
    assert found_gates[gates.EXCEPTIONS_CLEARED] == ("FAILED", 1)
    # A blocked run is the active run of its period: starting again answers it (SCREENS_B §1.2).
    again = runs.start(app, maya, entity_code=AVM_US, period_key=SEPTEMBER)
    assert (again.status_code, again.json()["id"], again.json()["status"]) == (
        200,
        run_id,
        "BLOCKED",
    )


def test_waived_quarantine_does_not_block(
    app: FastAPI,
    clock: FrozenClock,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 T-CLS-01 "Ends of a run" (SCREENS_B §1.2 "Resolve or waive them, then resume"): a
    quarantined group whose exception item was waived, and whose streams have not moved since, is
    not computed again — it would raise the waived item anew — and no longer blocks the run; it
    stays dirty for the gate. A blocked run whose quarantine still stands blocks again."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    run_id, _, (_, refused, _) = _quarantined_run(world, runtime, monkeypatch)
    group_id = _group(refused)

    # Resumed as it is: computed again, refused again, blocked again; the open item counts it.
    clock.advance(timedelta(minutes=1))
    resumed = runs.resume(app, maya, run_id)
    assert resumed.status_code == 202, resumed.text
    assert runs.shown(app, maya, run_id)["status"] == "RUNNING"
    runs.work(tenant_id, runtime, UUID(str(resumed.json()["id"])))
    blocked = runs.shown(app, maya, run_id)
    assert (blocked["status"], runs.step(blocked, RECOMPUTE)["counts"]) == (
        "BLOCKED",
        {"groups_recomputed": 0, "groups_quarantined": 1, "groups_waived": 0},
    )
    (item,) = _engine_items(world, group_id)
    assert (str(item["status"]), item["occurrence_count"]) == ("OPEN", 2)
    assert len(_computations(world, group_id)) == 3

    # Maya asks for a waiver; Marcus (exception.waive, another person) grants it.
    requested = post(
        app,
        f"{EXCEPTIONS}/{item['id']}/request-waiver",
        maya,
        {"comment": "The allocation of SF-ORD-10742 is corrected by a manual adjustment."},
    )
    assert requested.status_code == 200, requested.text
    granted = approve(
        app, str(requested.json()["approval_request_id"]), step_up(app, clock, world.marcus)
    )
    assert (granted.status_code, granted.json()["status"]) == (200, "APPROVED"), granted.text
    (waived,) = _engine_items(world, group_id)
    assert str(waived["status"]) == "WAIVED"

    clock.advance(timedelta(minutes=1))
    again = runs.resume(app, maya, run_id)
    assert again.status_code == 202, again.text
    runs.work(tenant_id, runtime, UUID(str(again.json()["id"])))
    run = runs.shown(app, maya, run_id)
    step = runs.step(run, RECOMPUTE)
    assert (step["status"], step["counts"]) == (
        "SUCCEEDED",
        {"groups_recomputed": 0, "groups_quarantined": 0, "groups_waived": 1},
    )
    assert run["status"] != "BLOCKED"
    # Nothing was computed or raised for the waived group, and it is still dirty for the gate.
    assert len(_computations(world, group_id)) == 3
    assert [str(row["status"]) for row in _engine_items(world, group_id)] == ["WAIVED"]
    assert _dirty(world) == {group_id}
    assert _gates(world)[gates.NO_DIRTY_GROUPS] == ("FAILED", 1)


def test_a_quarantined_group_of_several_contracts_is_listed_by_what_blocks_the_period(
    app: FastAPI,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-QUARANTINE-READ-1 (04 §15.3 API-R-44, §16.14 rev 1.206; 05 RCP-20; SCREENS_B
    §1.2). Two contracts are combined into one group and a third keeps its own; both groups are
    dirty and the engine refuses both, so the run ends ``BLOCKED`` with two quarantined groups.
    The item of the single contract names its contract and its entity; the item of the combined
    group names neither, and no engine item names a period. ``blockers.exceptions_open`` counts
    both — for September, and for October as well, whose lock an open quarantine also holds.
    The grid's read as it was — source ``ENGINE``, ``BLOCKING``, open, ``entity`` — names both
    since the one attribution (supervisor ruling R-121 (i): the group's item is the entity's by
    the gates' rule, a group holding a contract of it); by the item's own column it listed the
    single contract's item alone. Under ``blocking`` the list names both, the group's item with
    the group's code where it has no contract."""
    maya = world.place.author
    first, second, single = (_contract(world, f"SF-ORD-1078{index}") for index in (1, 2, 3))
    group_id = _combined(world, first, second)
    _billed(world, first, "INV-US-7811", head=_head(world, first))
    _billed(world, single, "INV-US-7813")
    # (the two groups the combined contracts left are empty: no gate and no run reads them)
    assert {group_id, _group(single)} <= _dirty(world)
    _refusing(monkeypatch, "SF-ORD-10781", "SF-ORD-10783")
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    finished = runs.work(world.place.tenant_id, runtime, job_id)
    assert str(finished["state"]) == "SUCCEEDED_WITH_EXCEPTIONS"
    run = runs.shown(app, maya, run_id)
    assert (run["status"], runs.step(run, RECOMPUTE)["counts"]) == (
        "BLOCKED",
        {"groups_recomputed": 0, "groups_quarantined": 2, "groups_waived": 0},
    )

    (of_group,) = _engine_items(world, group_id)
    (of_single,) = _engine_items(world, _group(single))
    assert (
        of_group["contract_id"],
        of_group["entity_id"],
        of_group["period_id"],
        str(of_group["status"]),
    ) == (None, None, None, "OPEN")
    assert "SF-ORD-10781, SF-ORD-10782 failed invariant" in of_group["message"]
    assert (
        of_single["contract_id"],
        of_single["entity_id"],
        of_single["period_id"],
        str(of_single["status"]),
    ) == (UUID(str(single.contract["id"])), world.entity_id, None, "OPEN")
    both = {str(of_group["id"]), str(of_single["id"])}

    states = {
        str(item["period"]["period_key"]): str(item["id"])
        for item in periods(app, maya, entity=AVM_US)
    }
    for key in (SEPTEMBER, OCTOBER):
        shown = get(app, f"{PERIODS}/{states[key]}", maya)
        assert shown.status_code == 200, shown.text
        assert shown.json()["blockers"]["exceptions_open"] == 2
    assert _gates(world)[gates.EXCEPTIONS_CLEARED] == ("FAILED", 2)

    quarantined = {"source": "ENGINE", "severity": "BLOCKING"}
    by_entity = get(
        app,
        EXCEPTIONS,
        maya,
        {**quarantined, "entity": AVM_US, "status": ["OPEN", "IN_PROGRESS"]},
    )
    assert by_entity.status_code == 200, by_entity.text
    # STALE EXPECTATION by supervisor ruling R-121 (i): this read listed ``of_single`` alone while
    # ``entity`` took the item's own column; by the gates' rule the group's item is AVM-US's too
    assert {str(item["id"]) for item in by_entity.json()["items"]} == both

    codes = {
        UUID(str(row["id"])): str(row["code"])
        for row in world.place.rows(select(combination_group.c.id, combination_group.c.code))
    }
    for key in (SEPTEMBER, OCTOBER):
        listed = get(app, EXCEPTIONS, maya, {**quarantined, "blocking": states[key]})
        assert listed.status_code == 200, listed.text
        found = {str(item["id"]): item for item in listed.json()["items"]}
        assert set(found) == both
        item = found[str(of_group["id"])]
        assert (
            item["contract_id"],
            item["contract_external_id"],
            item["combination_group_id"],
            item["combination_group_code"],
        ) == (None, None, str(group_id), codes[group_id])
        item = found[str(of_single["id"])]
        assert (
            item["contract_id"],
            item["contract_external_id"],
            item["combination_group_code"],
        ) == (str(single.contract["id"]), "SF-ORD-10783", codes[_group(single)])


# ``AVM_US_CHART`` with the contract asset a netting reclass of a seat contract reaches (JET-06).
RECLASS_CHART = (*AVM_US_CHART, ("1220", "Contract asset", "ASSET", "D", "CONTRACT_ASSET"))


def _marks(world: SeatWorld) -> dict[UUID, dict[str, str]]:
    """``period_ends_open`` of every group."""
    return {
        UUID(str(row["id"])): dict(row["period_ends_open"])
        for row in world.place.rows(
            select(combination_group.c.id, combination_group.c.period_ends_open)
        )
    }


def test_a_group_a_combination_left_empty_is_not_read_by_a_period_end_step(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-GROUPS-EMPTY-MEMBER-1 (04 T-CLS-01 "Period-end steps" rev 1.255; 05 RCP-08 rev
    1.183; the supervisor's order of 2026-10-01 16:43). January to August are closed, so
    September's close run marks the groups it passes. Two contracts, each in its own group, are
    passed and marked 1 Oct 2026. They are then combined: the approval moves both into one group
    and leaves their two groups empty — computed, marked, without a member. A period-end step
    lists a group by its mark only while the group holds a member: no bundle can be built of
    none, and such a group has no period end. September's next run reads the combined group
    alone in each of its three period-end steps, ends ``SUCCEEDED`` and marks it; the two empty
    groups keep what they held, and the gate passes — it never counts a group without a contract.

    The combination settles the two groups it empties (item COMBINE-EMPTY-GROUP-DIRTY-1, lane
    SECFIX-ACT; 04 T-CON-03): before that item it left them dirty, so that every step skipped
    them before it read them, and this test cleared ``dirty_since`` by a fixture row.

    Fail-first (measured on the head before the guard): the second run ended ``FAILED`` at
    ``FX_REMEASUREMENT`` with the job's 500, "The job stopped with an unexpected error." — a
    ``ValueError``: the step listed an empty group by its mark and asked for its bundle."""
    # the seat world with the one account its chart lacks for a netting reclass, so that a close
    # run of it reaches its end
    world = seat_world(app, keyring, clock, files, chart=RECLASS_CHART)
    maya = world.place.author
    tenant_id = world.place.tenant_id
    key = f"{AVM_US}|{BOOK}"
    periods_closed_before(world.place, app, maya, entity_id=world.entity_id, before=SEPTEMBER)
    first, second = (_contract(world, f"SF-ORD-1079{index}") for index in (1, 2))
    left = {_group(first), _group(second)}
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    runs.work(tenant_id, runtime, job_id)
    once = runs.shown(app, maya, run_id)
    assert once["status"] == "SUCCEEDED"
    assert runs.step(once, "FX_REMEASUREMENT")["counts"]["groups"] == 2
    assert {group_id: _marks(world)[group_id] for group_id in left} == dict.fromkeys(
        left, {key: "2026-10-01"}
    )

    group_id = _combined(world, first, second)
    assert _dirty(world) == set()  # the combination left neither emptied group dirty
    # why no step may read such a group: there is no bundle of it
    with world.place.uow() as uow, pytest.raises(ValueError, match="has no members"):
        bundles.build(
            uow.session, min(left, key=str), uow.now, (), ComputationTrigger.CLOSE_RELEASE
        )

    again_id, again_job = _started(world)
    runs.work(tenant_id, runtime, again_job)
    again = runs.shown(app, maya, again_id)
    stopped = [
        (step["step_code"], step["problem"])
        for step in again["steps"]
        if step["status"] == "FAILED"
    ]
    assert again["status"] == "SUCCEEDED", stopped
    for code in ("FX_REMEASUREMENT", "RELEASE_SCHEDULES", "NETTING_RECLASS"):
        counts = runs.step(again, code)["counts"]
        assert (code, counts["groups"], counts["groups_skipped"]) == (code, 1, 0)
    marks = _marks(world)
    assert marks[group_id] == {key: "2026-10-01"}
    assert {empty: marks[empty] for empty in left} == dict.fromkeys(left, {key: "2026-10-01"})
    assert _gates(world)[gates.CLOSE_RUN_COMPLETED] == ("PASSED", 0)


# --- resume, cancel, failure ----------------------------------------------------------------------


def test_resume_from_failed_step(
    app: FastAPI,
    clock: FrozenClock,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-19: a run failing at ``RECOMPUTE_DIRTY`` resumes at that step without
    re-executing ``CUTOFF`` to ``EXCEPTION_CHECK`` (their ``finished_at`` unchanged) (NFR-14)."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    booked = _contract(world, "SF-ORD-10751")
    _billed(world, booked, "INV-US-7501")
    asked = _breaking(monkeypatch, times=1)
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    assert str(runs.work(tenant_id, runtime, job_id)["state"]) == "FAILED"

    failed = runs.shown(app, maya, run_id)
    assert (failed["status"], failed["current_step_code"]) == ("FAILED", RECOMPUTE)
    step = runs.step(failed, RECOMPUTE)
    assert (step["status"], step["finished_at"] is not None) == ("FAILED", True)
    # The step's problem is the job's, in its four base members: an unexpected error shows no
    # message (DG-KRN-JOB-05).
    assert step["problem"] == {
        "type": "about:blank",
        "title": "Job failed",
        "status": 500,
        "detail": "The job stopped with an unexpected error.",
    }
    assert _statuses(failed, FIRST_STEPS) == ["SUCCEEDED"] * 3
    done = {code: runs.step(failed, code) for code in FIRST_STEPS}
    assert _dirty(world) == {_group(booked)}  # nothing of the step was kept
    assert len(_computations(world, _group(booked))) == 1
    assert _september_blockers(world)["jobs_failed"] == 1  # BLK-08: the run's newest job
    # A run that failed is not active: it does not answer a new start, and only it is resumed.
    refused = runs.cancel(app, maya, run_id, CANCEL_REASON)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text

    clock.advance(timedelta(minutes=10))
    resumed = runs.resume(app, maya, run_id)
    assert resumed.status_code == 202, resumed.text
    second_job = UUID(str(resumed.json()["id"]))
    assert (resumed.json()["kind"], resumed.headers[runs.ID_HEADER]) == ("CLOSE_RUN", run_id)
    assert second_job != job_id
    queued = runs.shown(app, maya, run_id)
    assert (queued["status"], queued["finished_at"], queued["job"]["id"]) == (
        "RUNNING",
        None,
        str(second_job),
    )
    twice = runs.resume(app, maya, run_id)
    assert (twice.status_code, slug(twice)) == (409, "invalid-transition"), twice.text
    runs.work(tenant_id, runtime, second_job)

    after = runs.shown(app, maya, run_id)
    # CUTOFF to EXCEPTION_CHECK were not executed again: their times are those of the first job.
    assert {code: runs.step(after, code) for code in FIRST_STEPS} == done
    again = runs.step(after, RECOMPUTE)
    at = clock.now().isoformat().replace("+00:00", "Z")
    assert (again["status"], again["started_at"], again["problem"]) == ("SUCCEEDED", at, None)
    assert again["counts"]["groups_recomputed"] == 1
    assert asked == [_group(booked), _group(booked)]
    assert _dirty(world) == set()
    # The first job stays the run's `job_id`; the run's job is the newest.
    (stored,) = world.place.rows(select(close_run.c.job_id).where(close_run.c.id == UUID(run_id)))
    assert stored["job_id"] == job_id and after["job"]["id"] == str(second_job)
    # The job that failed is done with the run: delivered again it changes nothing.
    assert str(runs.job_row(tenant_id, job_id)["state"]) == "FAILED"
    # BLK-08 counts the newest job of a run (supervisor ruling R-103 (a), item
    # CLO-BLK08-NEWEST-1): resumed to success, the run shows no failed job.
    assert (after["status"], after["job"]["state"]) == ("SUCCEEDED", "SUCCEEDED")
    assert _september_blockers(world)["jobs_failed"] == 0


def test_cancel_after_current_step(
    app: FastAPI,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-19: ``cancel`` with reason "Restarting after the correction." stops after the
    current step; completed steps stay ``SUCCEEDED``; the run is ``CANCELLED``."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    booked = _contract(world, "SF-ORD-10761")
    _billed(world, booked, "INV-US-7601")
    answered: list[Any] = []

    def while_recomputing() -> None:
        # The cancellation arrives while RECOMPUTE_DIRTY waits for its child.
        if not answered:
            answered.append(runs.cancel(app, maya, run_id, CANCEL_REASON))

    runs.unattended(monkeypatch, before=while_recomputing)
    run_id, job_id = _started(world)
    short = runs.cancel(app, maya, run_id, "Too short")
    assert (short.status_code, slug(short)) == (422, "validation-failed"), short.text
    finished = runs.work(tenant_id, runtime, job_id)

    (requested,) = answered
    assert requested.status_code == 200, requested.text
    # The request was recorded while the step ran: the run was still RUNNING at that step.
    assert (requested.json()["status"], requested.json()["current_step_code"]) == (
        "RUNNING",
        RECOMPUTE,
    )
    run = runs.shown(app, maya, run_id)
    assert (run["status"], run["current_step_code"]) == ("CANCELLED", None)
    assert run["finished_at"] is not None
    # The step in progress ended first; the completed steps stay SUCCEEDED, the rest PENDING.
    assert _statuses(run, (*FIRST_STEPS, RECOMPUTE)) == ["SUCCEEDED"] * 4
    assert runs.step(run, RECOMPUTE)["counts"]["groups_recomputed"] == 1
    assert set(_statuses(run, runs.STEP_CODES[4:])) == {"PENDING"}
    assert _dirty(world) == set()
    assert str(finished["state"]) == "CANCELLED" and run["job"]["state"] == "CANCELLED"
    # The reason is kept in the audit event of the command.
    (event,) = world.place.rows(
        select(audit_event.c.after, audit_event.c.actor_id).where(
            audit_event.c.action == "close_run.cancel", audit_event.c.object_id == UUID(run_id)
        )
    )
    assert event["after"]["reason"] == CANCEL_REASON
    assert event["actor_id"] == maya.member.user_id
    # A cancelled run has ended: it is not cancelled or resumed, and a new run can start.
    for response in (runs.cancel(app, maya, run_id, CANCEL_REASON), runs.resume(app, maya, run_id)):
        assert (response.status_code, slug(response)) == (409, "invalid-transition")
    fresh, _ = _started(world)
    assert fresh != run_id


def test_cancel_before_the_job_starts(app: FastAPI, world: SeatWorld, runtime: JobRuntime) -> None:
    """04 §16.8: a run whose job has not started is ``CANCELLED`` at once, and the job, delivered
    afterwards, executes nothing."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    _contract(world, "SF-ORD-10771")
    run_id, job_id = _started(world)
    cancelled = runs.cancel(app, maya, run_id, CANCEL_REASON)
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert (body["status"], body["job"]["state"]) == ("CANCELLED", "CANCELLED")
    assert set(_statuses(body)) == {"PENDING"}
    assert body["started_at"] is not None and body["finished_at"] is not None
    assert str(runs.work(tenant_id, runtime, job_id)["state"]) == "CANCELLED"
    assert set(_statuses(runs.shown(app, maya, run_id))) == {"PENDING"}


def test_dead_lettered_job_fails_the_run(
    app: FastAPI,
    clock: FrozenClock,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 JOB-06, JOB-07: a close-run job whose worker died is settled ``FAILED`` with problem
    ``job-stalled`` by the sweeper, and the handler's failure hook fails the run it left behind —
    here before its first step — and raises the blocker; the run is resumed like any failed run."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    booked = _contract(world, "SF-ORD-10791")
    _billed(world, booked, "INV-US-7901")
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    assert str(runs.dead_lettered(tenant_id, runtime, job_id)["state"]) == "FAILED"

    failed = runs.shown(app, maya, run_id)
    assert (failed["status"], failed["current_step_code"], failed["job"]["state"]) == (
        "FAILED",
        None,
        "FAILED",
    )
    assert failed["started_at"] is not None and failed["finished_at"] is not None
    assert set(_statuses(failed)) == {"PENDING"}  # no step had begun
    (item,) = world.place.rows(
        select(exception_item).where(exception_item.c.code == "CLOSE_RUN_FAILED")
    )
    assert item["message"] == (
        f"Close run {failed['close_run_no']} for AVM-US {failed['period']['name']} failed at the "
        "start: no heartbeat for 10 minutes. Nothing was committed for that step. Resume the "
        "close run once the cause is fixed."
    )
    assert item["source_payload"]["problem"]["type"].endswith("/job-stalled")

    clock.advance(timedelta(minutes=1))
    resumed = runs.resume(app, maya, run_id)
    assert resumed.status_code == 202, resumed.text
    runs.work(tenant_id, runtime, UUID(str(resumed.json()["id"])))
    after = runs.shown(app, maya, run_id)
    assert _statuses(after, (*FIRST_STEPS, RECOMPUTE)) == ["SUCCEEDED"] * 4
    assert runs.step(after, RECOMPUTE)["counts"]["groups_recomputed"] == 1


def test_failed_close_run_notifies_controllers(
    app: FastAPI,
    clock: FrozenClock,
    world: SeatWorld,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-19: a failed run writes notification ``JOB_FAILED`` to the initiator and the
    Controllers of the entity and a close-cockpit blocker exception item (NTF-05; DG-KRN-JOB-05)."""
    maya = world.place.author
    tenant_id = world.place.tenant_id
    booked = _contract(world, "SF-ORD-10781")
    _billed(world, booked, "INV-US-7801")
    _breaking(monkeypatch, times=2)
    runs.unattended(monkeypatch)
    run_id, job_id = _started(world)
    assert str(runs.work(tenant_id, runtime, job_id)["state"]) == "FAILED"
    run = runs.shown(app, maya, run_id)
    september = _september(world)

    # NTF-05: the initiator (by the job kernel) and the Controller of the entity (Marcus holds
    # period.lock); Priya approves SSP and hears nothing.
    sent = world.place.rows(
        select(notification).where(notification.c.kind == "JOB_FAILED").order_by(notification.c.id)
    )
    by_recipient = {row["recipient_membership_id"]: row for row in sent}
    assert set(by_recipient) == {maya.member.membership_id, world.marcus.member.membership_id}
    to_initiator = by_recipient[maya.member.membership_id]
    assert (to_initiator["title"], to_initiator["subject_type"], to_initiator["subject_id"]) == (
        "Job failed: Close run",
        "job",
        job_id,
    )
    to_controller = by_recipient[world.marcus.member.membership_id]
    assert (to_controller["title"], to_controller["subject_type"], to_controller["subject_id"]) == (
        "Job failed: Close run",
        "close_run",
        UUID(run_id),
    )
    assert to_controller["body"] == (
        "Close run failed at Recompute changed contracts: The job stopped with an unexpected "
        "error. Nothing was committed."
    )
    assert to_controller["link_path"] == f"/close/{AVM_US}/{BOOK}/{SEPTEMBER}/close-run"

    # The close-cockpit blocker: one blocking item of the entity, book and period.
    (item,) = world.place.rows(
        select(exception_item).where(exception_item.c.code == "CLOSE_RUN_FAILED")
    )
    assert (
        str(item["source"]),
        str(item["severity"]),
        str(item["status"]),
        item["dedupe_key"],
        item["entity_id"],
        item["period_id"],
        item["close_run_id"],
        item["occurrence_count"],
    ) == (
        "CLOSE",
        "BLOCKING",
        "OPEN",
        f"CLOSE:CLOSE_RUN_FAILED:{september['id']}",
        world.entity_id,
        UUID(str(september["period"]["id"])),
        UUID(run_id),
        1,
    )
    assert item["message"] == (
        f"Close run {run['close_run_no']} for AVM-US {september['period']['name']} failed at "
        "Recompute changed contracts: The job stopped with an unexpected error. Nothing was "
        "committed for that step. Resume the close run once the cause is fixed."
    )
    assert item["source_payload"]["step_code"] == RECOMPUTE
    shown = get(app, f"{EXCEPTIONS}/{item['id']}", maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["close_run_id"] == run_id
    blockers = _september_blockers(world)
    assert (blockers["jobs_failed"], blockers["exceptions_open"]) == (1, 1)
    assert _gates(world)[gates.EXCEPTIONS_CLEARED] == ("FAILED", 1)

    # Failing again at the resume counts on the same open item: one blocker per period.
    clock.advance(timedelta(minutes=1))
    resumed = runs.resume(app, maya, run_id)
    assert resumed.status_code == 202, resumed.text
    assert str(runs.work(tenant_id, runtime, UUID(str(resumed.json()["id"])))["state"]) == "FAILED"
    (again,) = world.place.rows(
        select(exception_item).where(exception_item.c.code == "CLOSE_RUN_FAILED")
    )
    assert (again["id"], again["occurrence_count"], str(again["status"])) == (item["id"], 2, "OPEN")
    assert (
        world.place.scalar(select(func.count()).select_from(job).where(job.c.state == "FAILED"))
        == 2
    )
    # BLK-08 counts the run once, by its newest job (R-103 (a), CLO-BLK08-NEWEST-1).
    assert _september_blockers(world)["jobs_failed"] == 1
