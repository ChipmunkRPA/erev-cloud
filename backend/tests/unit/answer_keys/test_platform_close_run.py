"""The close run of a platform plan (dev-guide DG-AK-41 rev 1.246; item AK-CLOSE-RUN-STEP-1; the
supervisor's rulings of 2026-10-01 on the lane's measurement).

The oracle computes the period-end passes with every checkpoint; the product posts them in a close
run. So the plan starts the product's close run right after the last item of a checkpoint whose
blocks expect a pass, and the runner works its job to the end. No database here: the step's call
and its conversion, the invoker that is the job's worker, what a run that does not succeed does
to the key, and the stamp the step leaves on each platform. The plan's side is in
``test_platform_plan.py``, the reads' in ``test_platform_workspace_reads.py``, the run against the
product in ``tests/domain/answer_keys/test_platform_close_run_db.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import Principal
from erev_api.clock import FrozenClock
from erev_api.enums import BookCode, PrincipalKind
from erev_api.jobs import registry
from erev_api.schemas.close_runs import CloseRunCreateIn
from support.answer_keys import request_models, runners
from support.answer_keys.platform_plan import (
    CLOSE,
    PLATFORM_KEY_IDS,
    PREPARER,
    H,
    Step,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import (
    EXECUTED,
    DbPlatform,
    InMemoryPlatform,
    MockAdapter,
    NotProvisioned,
    run_platform,
)
from support.answer_keys.request_models import MockResolver, adapt
from support.answer_keys.workspace_adapter import (
    Call,
    CloseRunFailed,
    WorkspaceAdapter,
    _server_horizon,
    real_invoker,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
START = datetime(2025, 12, 31, 12, tzinfo=UTC)
TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/close-run/tenant")
RUN = uuid5(NAMESPACE_URL, "erev://answer-keys/close-run/run")
JOB = uuid5(NAMESPACE_URL, "erev://answer-keys/close-run/job")


def _close_step(key_id: str) -> Step:
    (step,) = plan(load_platform_key(key_id)).steps_of(CLOSE)
    return step


def _preparer(permissions: frozenset[str] | None = None) -> Principal:
    """The preparer as the API resolves a revenue accountant, or with ``permissions`` alone."""
    granted = DEFAULT_ROLES["revenue_accountant"] if permissions is None else permissions
    return Principal(
        kind=PrincipalKind.USER,
        id=uuid5(NAMESPACE_URL, "erev://answer-keys/close-run/preparer"),
        tenant_id=TENANT,
        membership_id=uuid5(NAMESPACE_URL, "erev://answer-keys/close-run/membership"),
        display_name="Ak Preparer",
        roles=("revenue_accountant",),
        permissions=frozenset(granted),
        permission_scopes={},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def test_the_close_run_step_is_one_call_of_the_products_command() -> None:
    """The step is ``POST /close-runs`` by the preparer: the adapter derives one call of
    ``close_runs.start`` naming the entity, book and period of the step, and the conversion
    builds API-S-CloseRunCreate from it — the book as its enum (CONV-1)."""
    expected = {
        POS_012: ("US01", "FY2026-P01"),
        DLT: ("ME2", "FY2023-P01"),
        POS_117: ("US01", "FY2026-P03"),
    }
    for key_id, (entity, period_key) in expected.items():
        loaded = load_platform_key(key_id)
        step = _close_step(key_id)
        call = WorkspaceAdapter(loaded).plan_call(step)
        assert call == Call(
            "erev_api.domain.close.close_runs.start",
            PREPARER,
            {"entity": entity, "book": "ASC606", "period_key": period_key},
            step,
        ), key_id
        (sent,) = adapt(call, loaded.key, MockResolver(key_id))
        assert sent == {
            "body": CloseRunCreateIn(
                entity_code=entity, book=BookCode.ASC606, period_key=period_key
            )
        }, key_id
        assert sent["body"].book is BookCode.ASC606


class _Workspace:
    """What the real invoker asks of a workspace for the close-run step, without a database: the
    application clock, a unit of work for the principal it proved, and the run's row once the
    job has ended. ``trail`` keeps the order of what happened."""

    tenant_id = TENANT
    keyring = None
    files = None

    def __init__(self, run_row: dict[str, Any]) -> None:
        self.clock = FrozenClock(START)
        self.run_row = run_row
        self.trail: list[tuple[str, object]] = []

    @contextmanager
    def uow(self, principal: Principal | None = None) -> Iterator[SimpleNamespace]:
        self.trail.append(("unit of work", principal))
        yield SimpleNamespace(commit=lambda: self.trail.append(("commit", self.clock.now())))

    def rows(self, statement: object) -> list[dict[str, Any]]:
        self.trail.append(("run row read", None))
        return [dict(self.run_row)]


def _steps(stopped: tuple[str, str, object] | None = None) -> list[dict[str, Any]]:
    """The fourteen steps of a run that worked to its end, or that stopped at ``stopped``."""
    codes = (
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
    )
    steps: list[dict[str, Any]] = []
    reached = False
    for code in codes:
        if stopped is not None and code == stopped[0]:
            steps.append({"step_code": code, "status": stopped[1], "problem": stopped[2]})
            reached = True
        else:
            status = "PENDING" if reached else "SUCCEEDED"
            steps.append({"step_code": code, "status": status, "problem": None})
    steps.append({"step_code": "LOCK", "status": "PENDING", "problem": None})  # no lock
    return steps


def _wired(
    monkeypatch: pytest.MonkeyPatch,
    workspace: _Workspace,
    *,
    job: object = SimpleNamespace(id=JOB),  # noqa: B008 - a constant stand-in
) -> tuple[list[CloseRunCreateIn], list[tuple[UUID, UUID, int, object]]]:
    """The product's command and the worker's entry point replaced by recorders: what the
    command was sent, and which job was run for which tenant under which clock."""
    sent: list[CloseRunCreateIn] = []
    worked: list[tuple[UUID, UUID, int, object]] = []
    real_handler_of = request_models.handler_of

    def start(uow: object, *, body: CloseRunCreateIn) -> SimpleNamespace:
        sent.append(body)
        workspace.trail.append(("command", workspace.clock.now()))
        return SimpleNamespace(run_id=RUN, job=job)

    def handler_of(path: str) -> Any:
        return start if path == H["close_run"] else real_handler_of(path)

    def run_job(job_id: UUID, tenant_id: UUID, *, attempt: int, runtime: Any) -> None:
        worked.append((job_id, tenant_id, attempt, runtime.clock))
        workspace.trail.append(("job", job_id))

    monkeypatch.setattr(request_models, "handler_of", handler_of)
    monkeypatch.setattr(registry, "run_job", run_job)
    return sent, worked


def test_the_runner_works_the_close_runs_job_to_its_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runner is the worker, as for a journal and a report run: the command is sent once, by
    the preparer the ledger proved, at the step's application instant; once it has committed,
    the ``CLOSE_RUN`` job it deferred is run — attempt 1, the tenant's, under the workspace's
    clock — and the run's row is read: ``SUCCEEDED`` with the lock still pending is the end.
    A preparer without ``period.close`` is refused before anything is sent (ACT-2)."""
    loaded = load_platform_key(POS_012)
    step = _close_step(POS_012)
    call = WorkspaceAdapter(loaded).plan_call(step)
    assert call is not None
    workspace = _Workspace({"close_run_no": "CLS-000001", "status": "SUCCEEDED", "steps": _steps()})
    sent, worked = _wired(monkeypatch, workspace)
    preparer = _preparer()
    assert "period.close" in preparer.permissions
    result = real_invoker(workspace, loaded.key, [], {PREPARER: preparer})(call)
    assert (result.run_id, result.job.id) == (RUN, JOB)  # type: ignore[attr-defined]
    assert sent == [
        CloseRunCreateIn(entity_code="US01", book=BookCode.ASC606, period_key="FY2026-P01")
    ]
    assert worked == [(JOB, TENANT, 1, workspace.clock)]
    at = datetime(2026, 1, 31, 17, 0, 1, tzinfo=UTC)  # the step's clock: noon in New York + 1 s
    assert workspace.clock.now() == at
    assert workspace.trail == [
        ("unit of work", preparer),
        ("command", at),
        ("commit", at),
        ("job", JOB),
        ("run row read", None),
    ]
    # ACT-2: without the permission nothing is sent and no job is run.
    refused = _Workspace({"close_run_no": "CLS-000002", "status": "SUCCEEDED", "steps": _steps()})
    sent, worked = _wired(monkeypatch, refused)
    without = _preparer(frozenset(preparer.permissions - {"period.close"}))
    with pytest.raises(NotProvisioned, match="lacks permission period.close"):
        real_invoker(refused, loaded.key, [], {PREPARER: without})(call)
    assert (sent, worked, refused.trail) == ([], [], [])


def test_a_close_run_that_does_not_succeed_fails_the_key_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The product was asked for its close run and did not give it: the key fails with the run,
    its status, the step it stopped at and that step's problem — a failed pass (the product
    closes periods in order, R-112), a run blocked on a quarantined group, a command that
    answered a run already active. Never a step "not run": nothing of the plan refused it."""
    loaded = load_platform_key(POS_012)
    call = WorkspaceAdapter(loaded).plan_call(_close_step(POS_012))
    assert call is not None
    principals = {PREPARER: _preparer()}
    where = "CLOSE close run US01 ASC606 FY2026-P01"
    unposted = {"type": "invalid-transition", "detail": "FY2025-P12 holds an unposted period end"}
    failed = _Workspace(
        {
            "close_run_no": "CLS-000007",
            "status": "FAILED",
            "steps": _steps(("NETTING_RECLASS", "FAILED", unposted)),
        }
    )
    _wired(monkeypatch, failed)
    with pytest.raises(CloseRunFailed) as stopped:
        real_invoker(failed, loaded.key, [], principals)(call)
    assert str(stopped.value) == (
        f"{where}: close run CLS-000007 ended FAILED at NETTING_RECLASS (FAILED): {unposted}"
    )
    assert isinstance(stopped.value, AssertionError)
    assert not isinstance(stopped.value, NotProvisioned)
    blocked = _Workspace(
        {
            "close_run_no": "CLS-000008",
            "status": "BLOCKED",
            "steps": _steps(("RECOMPUTE_DIRTY", "BLOCKED", None)),
        }
    )
    _wired(monkeypatch, blocked)
    with pytest.raises(CloseRunFailed) as waits:
        real_invoker(blocked, loaded.key, [], principals)(call)
    assert str(waits.value) == (
        f"{where}: close run CLS-000008 ended BLOCKED at RECOMPUTE_DIRTY (BLOCKED): None"
    )
    # The command answered the run that was already active and deferred no job: nothing to work.
    active = _Workspace({"close_run_no": "CLS-000009", "status": "RUNNING", "steps": _steps()})
    _, worked = _wired(monkeypatch, active, job=None)
    with pytest.raises(CloseRunFailed) as answered:
        real_invoker(active, loaded.key, [], principals)(call)
    assert str(answered.value) == (
        f"{where}: the command answered a run that was already active and deferred no job"
    )
    assert worked == [] and ("run row read", None) not in active.trail


def test_the_close_run_stamps_its_checkpoint_again_on_the_database_platform() -> None:
    """Ruling (a): the checkpoint reads at the stamp taken after its close run. On the database
    platform the step reaches the adapter after the last step of item 9 and before item 10, and
    its commit stamps ``known_at[9]`` again, later than the item's own stamp and before item
    10's. On the in-memory platform the step runs nothing and stamps nothing — its store
    computes the passes with every checkpoint — so item 9 keeps its record time."""
    loaded = load_platform_key(POS_012)
    adapter = MockAdapter(start=START)
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    of_nine = [item for item in result.executed if item.step.seq == 9 and item.known_at is not None]
    assert [item.step.phase for item in of_nine] == ["TIMELINE", CLOSE]
    own, closed = of_nine
    assert closed.status == EXECUTED
    assert own.known_at is not None and closed.known_at is not None
    assert own.known_at < closed.known_at == result.known_at[9] < result.known_at[10]
    at = adapter.calls.index((H["close_run"], "close run US01 ASC606 FY2026-P01"))
    assert adapter.calls[at - 1][1].startswith("seq 9 ")
    assert adapter.calls[at + 1][1].startswith("seq 10 ")
    assert [handler for handler, _ in adapter.calls].count(H["close_run"]) == 1
    memory = run_platform(loaded, InMemoryPlatform(loaded))
    (unrun,) = [item for item in memory.executed if item.step.phase == CLOSE]
    assert (unrun.status, unrun.known_at) == (EXECUTED, None)
    assert memory.known_at[9] == runners._Assembler(loaded).times[9]
    assert memory.mismatches == ()  # the store's books hold the passes: both subledgers agree


def test_a_workspace_that_answers_no_transaction_id_keeps_no_horizon() -> None:
    """The horizon is the server's first transaction id not yet assigned, one read through the
    workspace. A workspace that answers anything else — a stand-in without a database — keeps
    none: the ledger records None and the reads that need a horizon refuse by name."""
    asked: list[str] = []

    def answering(value: object) -> SimpleNamespace:
        def scalar(statement: object) -> object:
            asked.append(str(statement))
            return value

        return SimpleNamespace(scalar=scalar)

    assert _server_horizon(answering(4711)) == 4711
    assert "txid_snapshot_xmax(txid_current_snapshot())" in asked[0]
    assert "txid_current()" not in asked[0]  # a read that assigns no transaction id
    for other in (None, "4711", 47.11, True, START):
        assert _server_horizon(answering(other)) is None, other
