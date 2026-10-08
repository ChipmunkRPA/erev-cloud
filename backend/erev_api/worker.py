"""The Procrastinate worker KRN-JOB (dev-guide §5.12 DG-KRN-JOB-02 to 11; 05 §5.6, §5.7, OPR-23).

``app`` registers the task ``erev.run_job``, which runs one ``job`` row through
``jobs.registry.run_job``, the minute sweepers ``erev.sweep_jobs`` (SCH-04), ``erev.sweep_outbox``
(SCH-03) and ``erev.webhook_delivery_due`` (SCH-12), the daily retention tasks
``erev.idempotency_purge`` (SCH-07) and ``erev.session_purge`` (SCH-08), the daily chain
verification tasks ``erev.audit_chain_verify_all`` (SCH-01) and ``erev.security_chain_verify``
(SCH-02), the support grant expiry ``erev.support_grant_expiry`` every 10 minutes (SCH-15), the
completion of decided shreds ``erev.file_shred_completion`` every 10 minutes (SCH-16) and the
six-hourly reconciliation sweeps ``erev.integration_sweeps`` (SCH-09).
``main`` is the composition root of ``erev worker``: it builds the job runtime from the settings,
writes the heartbeat file every 15 seconds (DG-KRN-JOB-08) and consumes all eight queues unless a
subset is named (DG-KRN-JOB-11).
"""

from __future__ import annotations

import asyncio
import importlib
import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import UUID

import procrastinate

from erev_api.adapters.billing import stripe
from erev_api.adapters.crm import salesforce
from erev_api.adapters.email import build_email_sender
from erev_api.adapters.gl import netsuite, quickbooks
from erev_api.adapters.gl.csv import CsvGl
from erev_api.adapters.http.adapter_client import client_factory
from erev_api.adapters.http.webhook_client import WebhookClient
from erev_api.adapters.storage.digests import build_digest_exporter
from erev_api.auth import security_events
from erev_api.auth.keyring import build_keyring, build_tenant_key_provisioner
from erev_api.clock import Clock, SystemClock
from erev_api.config import Settings, get_settings
from erev_api.controls import partition_window as sch13_partition_window
from erev_api.controls.operator_alert_sinks import build_alert_sinks
from erev_api.controls.release import EngineRelease, log_release, stamp_release
from erev_api.controls.startup import refuse_unsafe_production
from erev_api.db.session import dispose_engines, set_component
from erev_api.domain.close import data_quality_sweep as sch10_data_quality_sweep
from erev_api.domain.contracts import dirty_sweep
from erev_api.domain.integrations import sweeps as sch09_integration_sweeps
from erev_api.domain.integrations import sync as integrations_sync
from erev_api.domain.journals import ports as gl_ports
from erev_api.domain.platform import audit_jobs, retention, shred_completion, support_grants
from erev_api.domain.reference import period_auto_open as sch05_period_auto_open
from erev_api.enums import GlAdapter
from erev_api.events import outbox, webhooks
from erev_api.files import sweep as sch14_file_sweep
from erev_api.files.store import build_file_store
from erev_api.jobs import probes, registry, sweeper
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.pool import worker_pool
from erev_api.jobs.registry import QUEUES, QueueName
from erev_api.logging import configure_logging

if TYPE_CHECKING:
    from procrastinate.job_context import JobContext

HEARTBEAT_INTERVAL: Final = timedelta(seconds=15)  # DG-KRN-JOB-08
HEARTBEAT_MAX_AGE: Final = timedelta(seconds=60)  # DG-RUN-02 readiness; `erev worker --check`
SWEEP_TASK: Final = "erev.sweep_jobs"
OUTBOX_SWEEP_TASK: Final = "erev.sweep_outbox"
WEBHOOK_DELIVERY_DUE_TASK: Final = "erev.webhook_delivery_due"
IDEMPOTENCY_PURGE_TASK: Final = "erev.idempotency_purge"
SESSION_PURGE_TASK: Final = "erev.session_purge"
AUDIT_CHAIN_VERIFY_ALL_TASK: Final = "erev.audit_chain_verify_all"
SECURITY_CHAIN_VERIFY_TASK: Final = "erev.security_chain_verify"
SUPPORT_GRANT_EXPIRY_TASK: Final = "erev.support_grant_expiry"
PARTITION_WINDOW_CHECK_TASK: Final = "erev.partition_window_check"
FILE_ORPHAN_SWEEP_TASK: Final = "erev.file_orphan_sweep"
FILE_SHRED_COMPLETION_TASK: Final = "erev.file_shred_completion"
PERIOD_AUTO_OPEN_TASK: Final = "erev.period_auto_open"
DATA_QUALITY_MONITORS_TASK: Final = "erev.data_quality_monitors"
INTEGRATION_SWEEPS_TASK: Final = "erev.integration_sweeps"
DIRTY_CONTRACT_SWEEP_TASK: Final = "erev.dirty_contract_sweep"
STARTUP_REQUEST_ID: Final = "startup-worker"
# Modules whose `jobs.registry.task` handlers the worker registers; items that build handlers add
# their module here (DG-KRN-JOB-01; BS-D-07).
HANDLER_MODULES: Final[tuple[str, ...]] = (
    "erev_api.events.outbox",
    "erev_api.events.webhooks",
    "erev_api.domain.platform.retention",
    "erev_api.domain.platform.audit_jobs",
    "erev_api.domain.ssp.calculator",
    "erev_api.domain.policies.simulation",
    "erev_api.domain.policies.registry_versions",
    "erev_api.domain.contracts.compute_job",
    "erev_api.domain.imports.validate",
    "erev_api.domain.imports.diff",
    "erev_api.domain.imports.commit",
    "erev_api.domain.journals.summarise",
    "erev_api.domain.journals.export",
    # JRN-FAILED-CANCEL-1: the CANCEL and HAND_OVER modes of JOURNAL_EXPORT (export.MODE_HANDLERS)
    "erev_api.domain.journals.failed_exits",
    "erev_api.domain.close.reconciliations",  # CLO-16 RECONCILIATION_GENERATE (lane F-CLO-B)
    "erev_api.domain.close.close_runs",  # CLO-19 CLOSE_RUN (lane F-CLO-B)
    "erev_api.domain.reference.period_redirty_job",  # PERIOD_OPEN_REDIRTY (R-101 (a))
    "erev_api.domain.reports.framework",
    "erev_api.domain.platform.snapshot_job",  # SNP-1 TENANT_SNAPSHOT (lane F-SNP, merge prep)
    "erev_api.domain.platform.sandbox_reset_job",  # SNP-3 SANDBOX_RESET (lane F-SNP)
    "erev_api.domain.migration.jobs",  # LMG-3 MIGRATION_RECONCILE (lane F-LMG)
    "erev_api.domain.integrations.sync",  # DIN-12 SYNC_RUN (lane F-ADM on F-DIN's branch)
    "erev_api.domain.integrations.outbox",  # DIN-12 SYNC_REQUEST outbox handler
)

for _module in HANDLER_MODULES:
    importlib.import_module(_module)

# DG-LAY-03: the GL adapters the export relay dispatches through (05 §5.2; BUILD_SPEC CLO-13).
gl_ports.register_gl_adapter(GlAdapter.CSV, CsvGl)
# DG-LAY-03: the inbound CRM and billing adapters the SYNC_RUN job builds (05 §5.2 ADP-16, ADP-17;
# BUILD_SPEC DIN-12, DIN-13).
salesforce.register()
stripe.register()
# DG-LAY-03: the NETSUITE chart source a COA_SYNC run reads (03 REQ-INT-008; BUILD_SPEC DIN-14).
netsuite.register()

# The worker opens the connector with its own role-guarded pool (``main``).
app: Final[procrastinate.App] = procrastinate.App(connector=procrastinate.PsycopgConnector())
_runtime: JobRuntime | None = None
_ready: bool = False  # 05 OPR-23 rev 1.28: /startupz readiness


def _require_runtime() -> JobRuntime:
    if _runtime is None:
        raise RuntimeError("the worker runtime is not configured; run erev worker")
    return _runtime


@app.task(name=registry.RUN_JOB_TASK, pass_context=True)
def run_job(
    context: JobContext,
    job_id: str,
    tenant_id: str,
    attempt: int = 1,
    release_mismatch_deferrals: int = 0,
) -> None:
    """``erev.run_job(job_id, tenant_id)``: one job row through the registry (DG-KRN-JOB-02).

    ``context`` is Procrastinate's delivery context: ``context.job.id`` is the task this delivery
    stands for, which the registry compares with the job's pointer before acting (D-80; a stale
    delivery is a no-op). ``release_mismatch_deferrals`` counts the 05 REL-05 re-deferrals this
    delivery stands for.
    """
    registry.run_job(
        UUID(job_id),
        UUID(tenant_id),
        attempt=attempt,
        runtime=_require_runtime(),
        release_mismatch_deferrals=release_mismatch_deferrals,
        delivered_task_id=context.job.id,
    )


@app.periodic(cron="* * * * *", periodic_id="stalled_job_sweeper")
@app.task(name=SWEEP_TASK, queue="maintenance", queueing_lock=SWEEP_TASK, pass_context=False)
def sweep_jobs(timestamp: int) -> None:
    """SCH-04 every minute on ``maintenance``: lost dispatches and stalled jobs (DG-KRN-JOB-06,
    DG-KRN-JOB-10)."""
    sweeper.sweep(_require_runtime())


@app.periodic(cron="* * * * *", periodic_id="outbox_sweeper")
@app.task(
    name=OUTBOX_SWEEP_TASK, queue="outbox", queueing_lock=OUTBOX_SWEEP_TASK, pass_context=False
)
def sweep_outbox(timestamp: int) -> None:
    """SCH-03 every minute on ``outbox``: relay due and stranded messages (ADP-32)."""
    outbox.sweep(_require_runtime().clock)


@app.periodic(cron="* * * * *", periodic_id="webhook_delivery_due")
@app.task(
    name=WEBHOOK_DELIVERY_DUE_TASK,
    queue="outbox",
    queueing_lock=WEBHOOK_DELIVERY_DUE_TASK,
    pass_context=False,
)
def webhook_delivery_due(timestamp: int) -> None:
    """SCH-12 every minute on ``outbox``: retry due webhook deliveries (T-PLT-36)."""
    webhooks.sweep(_require_runtime().clock)


@app.periodic(cron="0 3 * * *", periodic_id="idempotency_purge")
@app.task(
    name=IDEMPOTENCY_PURGE_TASK,
    queue="maintenance",
    queueing_lock=IDEMPOTENCY_PURGE_TASK,
    pass_context=False,
)
def idempotency_purge(timestamp: int) -> None:
    """SCH-07 daily at 03:00 UTC: one ``RETENTION_SWEEP`` per ACTIVE tenant (DG-KRN-JOB-07)."""
    retention.defer_sweeps(_require_runtime().clock)


@app.periodic(cron="10 3 * * *", periodic_id="session_purge")
@app.task(
    name=SESSION_PURGE_TASK,
    queue="maintenance",
    queueing_lock=SESSION_PURGE_TASK,
    pass_context=False,
)
def session_purge(timestamp: int) -> None:
    """SCH-08 daily at 03:10 UTC: expired global sessions and password reset tokens."""
    retention.purge_global(_require_runtime().clock)


@app.periodic(cron="0 2 * * *", periodic_id="audit_chain_verify_all")
@app.task(
    name=AUDIT_CHAIN_VERIFY_ALL_TASK,
    queue="maintenance",
    queueing_lock=AUDIT_CHAIN_VERIFY_ALL_TASK,
    pass_context=False,
)
def audit_chain_verify_all(timestamp: int) -> None:
    """SCH-01 daily at 02:00 UTC: one ``AUDIT_CHAIN_VERIFY`` per ACTIVE tenant (DG-KRN-JOB-07)."""
    audit_jobs.defer_verifications(_require_runtime().clock)


@app.periodic(cron="30 2 * * *", periodic_id="security_chain_verify")
@app.task(
    name=SECURITY_CHAIN_VERIFY_TASK,
    queue="maintenance",
    queueing_lock=SECURITY_CHAIN_VERIFY_TASK,
    pass_context=False,
)
def security_chain_verify(timestamp: int) -> None:
    """SCH-02 daily at 02:30 UTC: the global security event chain."""
    audit_jobs.security_chain_verify(_require_runtime())


@app.periodic(cron="*/10 * * * *", periodic_id="support_grant_expiry")
@app.task(
    name=SUPPORT_GRANT_EXPIRY_TASK,
    queue="maintenance",
    queueing_lock=SUPPORT_GRANT_EXPIRY_TASK,
    pass_context=False,
)
def support_grant_expiry(timestamp: int) -> None:
    """SCH-15 every 10 minutes: approved support grants past ``valid_to`` expire, and their
    operator sessions end."""
    support_grants.expire_due(_require_runtime())


@app.periodic(cron="0 5 * * *", periodic_id="partition_window_check")
@app.task(
    name=PARTITION_WINDOW_CHECK_TASK,
    queue="maintenance",
    queueing_lock=PARTITION_WINDOW_CHECK_TASK,
    pass_context=False,
)
def partition_window_check(timestamp: int) -> None:
    """SCH-13 daily at 05:00 UTC: the partition windows against a 24-month horizon (04 §1.6 rule
    2); a window ending within it is the ``partition_window.checked`` WARNING line and the
    ``PARTITION_WINDOW_NEAR_END`` operator alert under RB-12 (05 OPR-24; record §4.22 (b),
    §4.32)."""
    sch13_partition_window.run(_require_runtime())


@app.periodic(cron="40 3 * * *", periodic_id="file_orphan_sweep")
@app.task(
    name=FILE_ORPHAN_SWEEP_TASK,
    queue="maintenance",
    queueing_lock=FILE_ORPHAN_SWEEP_TASK,
    pass_context=False,
)
def file_orphan_sweep(timestamp: int) -> None:
    """SCH-14 daily at 03:40 UTC: delete file-store objects older than 24 hours that no
    ``file_object`` row references (OPR-13; record §4.22 (c))."""
    sch14_file_sweep.run(_require_runtime())


@app.periodic(cron="*/10 * * * *", periodic_id="file_shred_completion")
@app.task(
    name=FILE_SHRED_COMPLETION_TASK,
    queue="maintenance",
    queueing_lock=FILE_SHRED_COMPLETION_TASK,
    pass_context=False,
)
def file_shred_completion(timestamp: int) -> None:
    """SCH-16 every 10 minutes: destroy the key of every file whose shred was decided and not
    completed — the third road of 05 PRV-07 b, after the command's own continuation and the
    command sent again — and, on the run at the full hour, raise the ``FILE_SHRED_INCOMPLETE``
    operator alert under RB-14 for a workspace that still holds one 60 minutes after its
    decision (05 OPR-24)."""
    shred_completion.run(
        _require_runtime(), alert=datetime.fromtimestamp(timestamp, UTC).minute == 0
    )


@app.periodic(cron="*/15 * * * *", periodic_id="period_auto_open")
@app.task(
    name=PERIOD_AUTO_OPEN_TASK,
    queue="maintenance",
    queueing_lock=PERIOD_AUTO_OPEN_TASK,
    pass_context=False,
)
def period_auto_open(timestamp: int) -> None:
    """SCH-05 every 15 minutes: open, as SYSTEM, every ``future`` period whose start date the
    entity's local date has reached, and (SCH-06, same transaction) re-mark dirty the groups with
    events in it (record §4.29)."""
    sch05_period_auto_open.run(_require_runtime())


@app.periodic(cron="0 4 * * *", periodic_id="data_quality_monitors")
@app.task(
    name=DATA_QUALITY_MONITORS_TASK,
    queue="maintenance",
    queueing_lock=DATA_QUALITY_MONITORS_TASK,
    pass_context=False,
)
def data_quality_monitors(timestamp: int) -> None:
    """SCH-10 daily at 04:00 UTC: evaluate the published ``DATA_QUALITY`` rule sets of every
    ACTIVE tenant through the CLO-5 monitors for every period in an evaluated state; exception
    items and notifications follow (REQ-CLS-019; record §4.30)."""
    sch10_data_quality_sweep.run(_require_runtime())


@app.periodic(cron="0 */6 * * *", periodic_id="integration_sweeps")
@app.task(
    name=INTEGRATION_SWEEPS_TASK,
    queue="maintenance",
    queueing_lock=INTEGRATION_SWEEPS_TASK,
    pass_context=False,
)
def integration_sweeps(timestamp: int) -> None:
    """SCH-09 every six hours: one ``SYNC_RUN`` of kind ``RECONCILIATION_SWEEP`` asked for per
    ACTIVE inbound connection of every ACTIVE tenant, through the ``SYNC_REQUEST`` outbox so a
    six-hour bucket asks once per connection (REQ-INT-007; BUILD_SPEC DIN-13)."""
    sch09_integration_sweeps.run(_require_runtime())


@app.periodic(cron="* * * * *", periodic_id="dirty_contract_sweep")
@app.task(
    name=DIRTY_CONTRACT_SWEEP_TASK,
    queue="maintenance",
    queueing_lock=DIRTY_CONTRACT_SWEEP_TASK,
    pass_context=False,
)
def dirty_contract_sweep(timestamp: int) -> None:
    """Recover dirty booked groups through durable CONTRACT_COMPUTE jobs each minute."""
    dirty_sweep.run(_require_runtime())


def process_clock() -> Clock:
    """The clock of ``erev worker``; tests replace it with a frozen clock (DG-TST-14)."""
    return SystemClock()


@dataclass(slots=True)
class HeartbeatWriter:
    """Touches the heartbeat file at most every 15 seconds, stamped with the clock's time."""

    path: Path
    clock: Clock
    _last: datetime | None = field(default=None, init=False)

    def tick(self) -> bool:
        now = self.clock.now()
        if self._last is not None and now - self._last < HEARTBEAT_INTERVAL:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        stamp = now.timestamp()
        os.utime(self.path, (stamp, stamp))
        self._last = now
        return True


def heartbeat_is_fresh(path: Path, clock: Clock) -> bool:
    """Whether the heartbeat file was touched less than 60 seconds ago (DPL-02 health check)."""
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except FileNotFoundError:
        return False
    return clock.now() - modified < HEARTBEAT_MAX_AGE


def _beat(writer: HeartbeatWriter, stop: threading.Event) -> None:
    while not stop.wait(1.0):
        writer.tick()


async def _run_worker(settings: Settings, queues: Sequence[QueueName]) -> None:
    # The pool's connections start with the TXN-03 settings and pass the role guard
    # (``jobs.pool``; dev-guide DG-KRN-DB-11); its sizes are the worker's (05 §2.7).
    pool = worker_pool(
        settings.app_database_url(),
        min_size=1,
        max_size=settings.worker_concurrency + 2,
    )
    await pool.open(wait=True)
    try:
        async with app.open_async(pool=pool):
            await app.run_worker_async(queues=list(queues), concurrency=settings.worker_concurrency)
    finally:
        await pool.close()


def build_runtime(
    settings: Settings, clock: Clock, *, release: EngineRelease | None = None
) -> JobRuntime:
    """The services of ``erev worker`` from the settings: key ring by EREV_KEY_PROVIDER, file
    store by EREV_FILE_BACKEND (CFG-05) and, under the gcs backend, the SAR-31 digest exporter
    to the write-once bucket. Constructing them performs no network call."""
    # DG-LAY-03: how the SYNC_RUN job reaches ``integration_connection.base_url`` (SAR-15 guard;
    # loopback and http admitted in the local environments for the in-process mocks, ADP-20).
    build_client = client_factory(settings.env)
    integrations_sync.register_http_client_factory(build_client)
    # DG-LAY-03: the ERP GL adapters of the export relay and of the trial-balance pull reach the
    # connection a batch or a pull names over the same guarded client (05 §5.2; BUILD_SPEC
    # CLO-15). ``CSV`` is registered above: it needs neither a client nor a connection.
    gl_ports.register_gl_adapter(GlAdapter.NETSUITE, netsuite.connection_factory(build_client))
    gl_ports.register_gl_adapter(
        GlAdapter.QUICKBOOKS_ONLINE, quickbooks.connection_factory(build_client)
    )
    email = build_email_sender(settings, clock)
    keyring = build_keyring(settings)
    return JobRuntime(
        clock=clock,
        keyring=keyring,
        files=build_file_store(settings),
        email=email,
        public_origin=settings.public_origin,
        webhooks=WebhookClient(env=settings.env),
        digests=build_digest_exporter(settings),
        engine_release=release,
        alerts=build_alert_sinks(settings, clock, email=email),
        # KEY-05: a sandbox load creates a tenant and therefore its audit key (05 SBX-02)
        key_provisioner=build_tenant_key_provisioner(settings, keyring),
    )


def main(*, queues: Sequence[QueueName] = QUEUES, heartbeat_file: Path) -> None:
    """Run the worker on ``queues``, all eight by default (DG-KRN-JOB-11)."""
    global _runtime, _ready
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    set_component("worker")
    # 05 SAR-40 startup subset (rev 1.53): a production worker refuses fake email and placeholder
    # or repeated master keys before it listens, stamps or connects.
    refuse_unsafe_production(settings)
    # 05 OPR-23 rev 1.28: the probe listener answers /startupz 503 until the checks below pass
    # and /livez by the heartbeat file; it opens only when CFG-32 names a port.
    clock = process_clock()
    probe_server = probes.probe_server_if_configured(
        settings.worker_probe_port,
        ready=lambda: _ready,
        live=lambda: heartbeat_is_fresh(heartbeat_file, clock),
    )
    if probe_server is not None:
        probe_server.start()
    # 05 REL-03: record the running release before consuming jobs, and keep it: REL-05 compares
    # every job's enqueuing release with it.
    release = stamp_release(settings.env, request_id=STARTUP_REQUEST_ID)
    log_release(release)
    _runtime = build_runtime(settings, clock, release=release)
    # 05 KEY-03 hosted acceptance: the requested security key version is the one served, before
    # any job runs (an outage or a wrong pin stops the process, never a silent fallback).
    assert _runtime.keyring is not None
    _runtime.keyring.verify_current_security_key()
    # A worker whose pin is behind the chain head never starts consuming (DG-KRN-AUD-08 fence).
    security_events.check_writer_admission_at_startup(
        _runtime.keyring, request_id=STARTUP_REQUEST_ID
    )
    _ready = True  # /startupz turns 200: runtime built, key verified, admission passed
    writer = HeartbeatWriter(heartbeat_file, clock)
    writer.tick()
    stop = threading.Event()
    beat = threading.Thread(target=_beat, args=(writer, stop), name="erev-heartbeat", daemon=True)
    beat.start()
    try:
        asyncio.run(_run_worker(settings, queues))
    finally:
        stop.set()
        beat.join(timeout=5)
        if probe_server is not None:
            probe_server.stop()
        dispose_engines()
