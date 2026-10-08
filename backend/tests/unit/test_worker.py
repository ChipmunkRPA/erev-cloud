"""The worker entry point (dev-guide DG-KRN-JOB-08, DG-KRN-JOB-11; DG-RUN-02; 05 OPR-23, SCH-04;
BUILD_SPEC PLF-9)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import erev_api
import pytest
from erev_api import worker
from erev_api.cli import app
from erev_api.clock import FrozenClock
from erev_api.config import get_settings
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import QUEUES
from support.clock import FROZEN_AT, frozen_clock
from typer.testing import CliRunner


@pytest.fixture
def empty_queue_setting(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("EREV_WORKER_QUEUES", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_krn_job_11_queue_option(
    monkeypatch: pytest.MonkeyPatch, empty_queue_setting: None, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(worker, "main", lambda **kwargs: calls.append(kwargs))
    runner = CliRunner()

    refused = runner.invoke(app, ["worker", "--queues", "gpu"])
    assert refused.exit_code == 2, refused.output
    assert "unknown queue gpu" in refused.output
    assert calls == []

    beat = tmp_path / "worker.heartbeat"
    every = runner.invoke(app, ["worker", "--heartbeat-file", str(beat)])
    assert every.exit_code == 0, every.output
    assert calls == [{"queues": QUEUES, "heartbeat_file": beat}]
    assert len(QUEUES) == 8

    split = runner.invoke(
        app, ["worker", "--queues", "close,compute", "--heartbeat-file", str(beat)]
    )
    assert split.exit_code == 0, split.output
    assert calls[-1]["queues"] == ("compute", "close")


def test_krn_job_08_heartbeat_and_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clock: FrozenClock
) -> None:
    beat = tmp_path / "run" / "worker.heartbeat"
    writer = worker.HeartbeatWriter(beat, clock)
    touched: list[int] = []
    for second in range(31):
        if writer.tick():
            touched.append(second)
        assert beat.stat().st_mtime == (FROZEN_AT + timedelta(seconds=touched[-1])).timestamp()
        clock.advance(timedelta(seconds=1))
    assert touched == [0, 15, 30]

    probe = frozen_clock(FROZEN_AT + timedelta(seconds=30 + 59))
    monkeypatch.setattr(worker, "process_clock", lambda: probe)
    runner = CliRunner()
    fresh = runner.invoke(app, ["worker", "--check", "--heartbeat-file", str(beat)])
    assert fresh.exit_code == 0, fresh.output
    probe.advance(timedelta(seconds=1))
    stale = runner.invoke(app, ["worker", "--check", "--heartbeat-file", str(beat)])
    assert stale.exit_code == 1, stale.output
    absent = runner.invoke(app, ["worker", "--check", "--heartbeat-file", str(tmp_path / "none")])
    assert absent.exit_code == 1, absent.output


def test_krn_job_02_worker_tasks() -> None:
    run_job = worker.app.tasks[registry.RUN_JOB_TASK]
    sweep = worker.app.tasks[worker.SWEEP_TASK]
    assert (run_job.name, sweep.queue, sweep.queueing_lock) == (
        "erev.run_job",
        "maintenance",
        "erev.sweep_jobs",
    )
    # SCH-04 and SCH-03: the job and outbox sweepers run every minute.
    outbox_sweep = worker.app.tasks[worker.OUTBOX_SWEEP_TASK]
    assert (outbox_sweep.queue, outbox_sweep.queueing_lock) == ("outbox", "erev.sweep_outbox")
    # SCH-12: due webhook deliveries are retried every minute on outbox.
    delivery_due = worker.app.tasks[worker.WEBHOOK_DELIVERY_DUE_TASK]
    assert (delivery_due.queue, delivery_due.queueing_lock) == (
        "outbox",
        "erev.webhook_delivery_due",
    )
    # SCH-07 and SCH-08: the daily retention tasks run on maintenance.
    # SCH-01 and SCH-02: the daily chain verification tasks run on maintenance too, as do the
    # SCH-15 support grant expiry and the SCH-16 shred completion.
    for name in (
        worker.IDEMPOTENCY_PURGE_TASK,
        worker.SESSION_PURGE_TASK,
        worker.AUDIT_CHAIN_VERIFY_ALL_TASK,
        worker.SECURITY_CHAIN_VERIFY_TASK,
        worker.SUPPORT_GRANT_EXPIRY_TASK,
        worker.PARTITION_WINDOW_CHECK_TASK,
        worker.FILE_ORPHAN_SWEEP_TASK,
        worker.FILE_SHRED_COMPLETION_TASK,
        worker.PERIOD_AUTO_OPEN_TASK,
        worker.DATA_QUALITY_MONITORS_TASK,
        worker.INTEGRATION_SWEEPS_TASK,
        worker.DIRTY_CONTRACT_SWEEP_TASK,
    ):
        assert (worker.app.tasks[name].queue, worker.app.tasks[name].queueing_lock) == (
            "maintenance",
            name,
        )
    periodic = worker.app.periodic_registry.periodic_tasks
    assert [(key[0], task.cron) for key, task in periodic.items()] == [
        ("erev.sweep_jobs", "* * * * *"),
        ("erev.sweep_outbox", "* * * * *"),
        ("erev.webhook_delivery_due", "* * * * *"),
        ("erev.idempotency_purge", "0 3 * * *"),
        ("erev.session_purge", "10 3 * * *"),
        ("erev.audit_chain_verify_all", "0 2 * * *"),
        ("erev.security_chain_verify", "30 2 * * *"),
        ("erev.support_grant_expiry", "*/10 * * * *"),
        # SCH-13 and SCH-14 (record §4.22; D-98 138): the daily partition-window check and the
        # file-store orphan sweep, global tasks on maintenance.
        ("erev.partition_window_check", "0 5 * * *"),
        ("erev.file_orphan_sweep", "40 3 * * *"),
        # SCH-16 (05 PRV-07 b rev 1.171; item FILE-SHRED-DURABLE-ORDER-1): every ten minutes
        # the key of a file whose shred is decided and not completed is destroyed.
        ("erev.file_shred_completion", "*/10 * * * *"),
        # SCH-05 (record §4.29): the quarter-hourly automatic period opening; SCH-06 runs inside
        # it in the same transaction and is not a separate periodic (05 §SCH).
        ("erev.period_auto_open", "*/15 * * * *"),
        # SCH-10 (record §4.30): the daily data-quality monitor sweep over the published
        # DATA_QUALITY rule sets of every ACTIVE tenant.
        ("erev.data_quality_monitors", "0 4 * * *"),
        # SCH-09 (BUILD_SPEC DIN-13; REQ-INT-007): the six-hourly reconciliation sweep request
        # per ACTIVE inbound connection.
        ("erev.integration_sweeps", "0 */6 * * *"),
        ("erev.dirty_contract_sweep", "* * * * *"),
    ]


def test_every_handler_module_imports_first_in_a_fresh_process(tmp_path: Path) -> None:
    """ARCH-IMPORT-CYCLE-1 (dev-guide DG-ARC-17 rev 1.174): the worker imports its handler modules
    by name (``HANDLER_MODULES``), and a test or a script may import any one of them before
    anything else of the package. Each is imported first by an interpreter of its own, which also
    runs what the static replay of DG-ARC-17 cannot see: the registrations a handler module makes
    when it is imported. ``reference/period_redirty_job.py`` failed so until it imported
    ``platform.jobs`` whole."""
    assert len(set(worker.HANDLER_MODULES)) == len(worker.HANDLER_MODULES) >= 22
    package_root = str(Path(erev_api.__file__).resolve().parents[1])
    environment = {**os.environ, "PYTHONPATH": package_root, "PYTHONDONTWRITEBYTECODE": "1"}
    failed: dict[str, str] = {}
    for module in worker.HANDLER_MODULES:
        done = subprocess.run(
            [sys.executable, "-c", f"import importlib; importlib.import_module({module!r})"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if done.returncode != 0:
            failed[module] = (done.stderr.strip().splitlines() or ["no output"])[-1]
    assert failed == {}


def test_rel_05_worker_task_passes_the_delivered_task(
    monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    # The Procrastinate task receives its delivery context and hands the delivered task id to the
    # registry, which never derives delivery ownership from the job's current pointer (D-80).
    from types import SimpleNamespace
    from uuid import uuid4

    assert worker.run_job.pass_context is True
    runtime = JobRuntime(clock=clock, keyring=None, files=None)
    monkeypatch.setattr(worker, "_runtime", runtime)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(registry, "run_job", lambda *args, **kwargs: calls.append((args, kwargs)))
    job_id, tenant_id = uuid4(), uuid4()
    context = SimpleNamespace(job=SimpleNamespace(id=4242, attempts=0))
    worker.run_job(context, str(job_id), str(tenant_id), attempt=2, release_mismatch_deferrals=3)
    assert calls == [
        (
            (job_id, tenant_id),
            {
                "attempt": 2,
                "runtime": runtime,
                "release_mismatch_deferrals": 3,
                "delivered_task_id": 4242,
            },
        )
    ]
