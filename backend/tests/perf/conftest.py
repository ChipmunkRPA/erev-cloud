"""Performance harness session (BUILD_SPEC PRF-3; dev-guide DG-PERF-01 to DG-PERF-08; 05 PERF-11,
PERF-20, SBX-05, SBX-07, AIA-02).

Deselection: without ``EREV_PERF_RUN=1`` every test here is deselected (DG-PERF-06), so ``pytest
backend/tests`` never runs a perf test. With it, ``backend/tests/conftest.py`` has set
``EREV_ENV=dev``
and collects only this directory; this conftest then asserts that the app database is ``erev``,
refuses the database fixtures, checks the perf tenant, restores the stored snapshot into a
``perf-run-*`` sandbox, and starts and stops the five harness processes by PID file. Database and
process work here is authored for ``make perf`` (Ray-side, DG-MK-perf) and NOT RUN in the lane.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from perf.support import client as perf_client
from perf.support import prepare, processes, report, rules, sandbox, tenant

ROOT = Path(__file__).resolve().parents[3]
PERF_RUN = rules.is_perf_run(os.environ)


PERF_DIR = Path(__file__).resolve().parent


def _is_perf_item(item: pytest.Item) -> bool:
    """An item collected under this directory (the hook sees the whole session; R1)."""
    path = getattr(item, "path", None) or Path(str(item.fspath))
    try:
        Path(path).resolve().relative_to(PERF_DIR)
    except ValueError:
        return False
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """DG-PERF-06: deselect every perf test unless ``EREV_PERF_RUN=1``; ordinary tests elsewhere in
    the session are never touched (Codex 2316 R1)."""
    kept, deselected = rules.deselect_unless_perf_run(
        items, perf_run=PERF_RUN, is_perf=_is_perf_item
    )
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


def pytest_runtest_setup(item: pytest.Item) -> None:
    """DG-PERF-06: a perf test that requests a database fixture fails before it runs."""
    names = getattr(item, "fixturenames", ())
    name = rules.forbidden_fixture(names)
    if name is not None:
        pytest.fail(rules.forbidden_fixture_message(name), pytrace=False)


@pytest.fixture(scope="session")
def perf_settings() -> Any:
    """The process settings of the run: ``EREV_ENV=dev``, database ``erev`` (05 PERF-11), the AIA-02
    provider rule enforced by ``Settings`` itself before any process starts."""
    from erev_api.config import Environment, get_settings

    settings = get_settings()
    if settings.env is not Environment.DEV:
        pytest.exit(f"perf tests run under EREV_ENV=dev, not {settings.env.value}", returncode=1)
    try:
        rules.require_perf_database(settings.database_name())
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=1)
    return settings


@pytest.fixture(scope="session")
def perf_manifest() -> Any:
    from erev_api.domain.demo import volume

    return volume.manifest()


def _directory_row(settings: Any) -> tuple[UUID, str | None] | None:
    """Step 1 (Codex 2316 R2 (a)): the tenant identity from the tenant directory — a platform read
    that the ``tenant_directory`` policy admits; no tenant rows are read here."""
    from erev_api.db.session import platform_session
    from erev_api.db.tables import tenant as tenant_table
    from sqlalchemy import select

    with platform_session(
        "tenant_directory", actor_user_id=None, request_id="perf-tenant"
    ) as session:
        row = session.execute(
            select(tenant_table.c.id, tenant_table.c.industry_cluster).where(
                tenant_table.c.code == tenant.TENANT_CODE
            )
        ).one_or_none()
    return None if row is None else (UUID(str(row.id)), row.industry_cluster)


def _snapshot_row(tenant_id: UUID) -> tenant.SnapshotFacts | None:
    """Step 2: the latest succeeded stored snapshot, read in an authorised TENANT read context
    (forced RLS of T-PLT-34 admits the tenant's own rows; no owner role, no bypass)."""
    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import tenant_snapshot
    from sqlalchemy import select

    scope = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as session:
        row = session.execute(
            select(
                tenant_snapshot.c.id,
                tenant_snapshot.c.status,
                tenant_snapshot.c.known_at,
                tenant_snapshot.c.purpose,
            )
            .where(
                tenant_snapshot.c.purpose == tenant.SEED_PURPOSE,
                tenant_snapshot.c.status == tenant.SUCCEEDED,
            )
            .order_by(tenant_snapshot.c.known_at.desc())
            .limit(1)
        ).one_or_none()
    if row is None:
        return None
    return tenant.SnapshotFacts(UUID(str(row.id)), str(row.status), row.known_at, str(row.purpose))


def _tenant_lookup(settings: Any) -> tenant.TenantFacts | None:
    return tenant.compose_facts(lambda: _directory_row(settings), _snapshot_row)


@pytest.fixture(scope="session")
def perf_tenant(perf_settings: Any, perf_manifest: Any) -> tenant.PerfTenant:
    """``perf-volume`` current for this manifest, else fail with the DG-PERF-06 message."""
    try:
        return tenant.check_perf_tenant(
            lambda: _tenant_lookup(perf_settings), expected_cluster=perf_manifest.industry_cluster
        )
    except tenant.PerfTenantStale as exc:
        pytest.exit(str(exc), returncode=1)


SANDBOX_RESET_WAIT = (
    "this run's perf-run-* sandbox stays ACTIVE after the run: SANDBOX_RESET has no handler on "
    "main (F-SNP), so the next make perf refuses by name until it lands (D-98 148 AMENDMENT 4)"
)
# The seed's cast (perf_seed.CAST): the accountant prepares, the controller closes and exports and
# is the restore's requesting user (period authority in the sandbox), the reviewer approves.
ACCOUNTANT_EMAIL = "perf-accountant@demo.erev"
CONTROLLER_EMAIL = "perf-controller@demo.erev"
REVIEWER_EMAIL = "perf-reviewer@demo.erev"


def _requester_row(tenant_id: UUID) -> UUID | None:
    """The perf-controller's ``app_user.id`` with an ACTIVE membership of ``perf-volume``, read in
    the tenant's authorised read context (the membership rows are the tenant's; the user row is
    the one the invite command itself reads by email). This real, authorised persona is the
    restore's ``requested_by``: the loader copies its membership into the sandbox, which is what
    makes the sandbox visible and gives the period authority (Codex 2353 PRF3-RESTORE-ACTOR-1)."""
    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import app_user, tenant_membership
    from sqlalchemy import select

    scope = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as session:
        row = session.execute(
            select(tenant_membership.c.user_id)
            .select_from(
                tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
            )
            .where(
                tenant_membership.c.tenant_id == tenant_id,
                tenant_membership.c.status == "ACTIVE",
                app_user.c.email == CONTROLLER_EMAIL,
            )
        ).scalar_one_or_none()
    return None if row is None else UUID(str(row))


def _active_perf_sandbox_codes(source_tenant_id: UUID) -> list[str]:
    """Codes of the ACTIVE sandbox tenants copied from ``perf-volume`` (directory scope, like
    ``_directory_row``): the A4 prior-active condition is checked from them."""
    from erev_api.db.session import platform_session
    from erev_api.db.tables import tenant as tenant_table
    from sqlalchemy import select

    with platform_session(
        "tenant_directory", actor_user_id=None, request_id="perf-prior-active"
    ) as session:
        rows = session.execute(
            select(tenant_table.c.code).where(
                tenant_table.c.kind == "sandbox",
                tenant_table.c.status == "ACTIVE",
                tenant_table.c.source_tenant_id == source_tenant_id,
            )
        ).scalars()
        return [str(code) for code in rows]


def _contract_events(tenant_id: UUID, until: datetime | None) -> int:
    """The contract events of a tenant in its authorised read context, recorded at or before
    ``until`` when one is given (DB-08 ``recorded_at``, the column the snapshot's cutoff reads:
    ``snapshot_dataset.CUTOFF_RULES``)."""
    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import contract_event
    from sqlalchemy import func, select

    counted = select(func.count()).select_from(contract_event)
    if until is not None:
        counted = counted.where(contract_event.c.recorded_at <= until)
    scope = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as session:
        return int(session.execute(counted).scalar_one())


@pytest.fixture(scope="session")
def perf_sandbox(perf_settings: Any, perf_tenant: tenant.PerfTenant) -> sandbox.RestoredSandbox:
    """DG-PERF-02 (1), not measured. BEFORE the restore and before any process starts: the A4
    condition — an EXISTING ACTIVE ``perf-run-*`` sandbox requires SANDBOX_RESET, whose handler is
    not on main, so the run refuses by name; a first run proceeds. Then the requesting user is
    resolved: the real perf-controller (ACTIVE member of ``perf-volume``), never ``None`` and never
    an invented actor. Then the stored snapshot is restored into a new ``perf-run-*``
    sandbox through ``run_inline(JobKind.TENANT_SNAPSHOT, …)`` with the snapshot's authoritative
    ``known_at`` and ``purpose`` (``snapshot_job.parse_params``) and a ``load`` entry naming that
    user, as the source tenant's system principal (the loader's contract), with the configured
    services (``worker.build_runtime``). The wait note reaches the report."""
    from erev_api import worker
    from erev_api.auth.principal import system_principal
    from erev_api.clock import SystemClock
    from erev_api.db import new_id
    from erev_api.domain.platform import sandboxes
    from erev_api.enums import JobKind
    from erev_api.jobs import registry

    refusal = sandbox.prior_active_refusal(
        _active_perf_sandbox_codes(perf_tenant.tenant_id),
        reset_available=JobKind.SANDBOX_RESET in registry.HANDLERS,
    )
    if refusal is not None:
        pytest.exit(refusal, returncode=1)
    try:
        requested_by = sandbox.require_requester(_requester_row(perf_tenant.tenant_id))
    except sandbox.RequesterMissing as exc:
        pytest.exit(str(exc), returncode=1)
    clock = SystemClock()
    runtime = worker.build_runtime(perf_settings, clock)  # key ring and file store (R2 (c))
    sandbox_tenant_id = new_id()
    name = f"{sandbox.SANDBOX_PREFIX}{secrets.token_hex(4)}"
    load_params = sandboxes.load_params_of(
        sandbox_tenant_id=sandbox_tenant_id, name=name, requested_by=requested_by, restore=True
    )
    principal = system_principal(perf_tenant.tenant_id)

    def run(params: dict[str, Any]) -> dict[str, Any]:
        outcome = registry.run_inline(
            JobKind.TENANT_SNAPSHOT,
            params,
            tenant_id=perf_tenant.tenant_id,
            principal=principal,
            clock=clock,
            runtime=runtime,
        )
        return dict(outcome.result)

    try:
        restored = sandbox.restore_seed(
            run,
            snapshot=perf_tenant.snapshot,
            sandbox_tenant_id=sandbox_tenant_id,
            load_params=load_params,
        )
        # A load that compared nothing proves nothing (DG-PERF-02 (1), rev 1.243): before the
        # month-24 events are appended, the sandbox holds what perf-volume recorded by the cutoff.
        restored = sandbox.verify_copy(
            restored,
            source_tenant_id=perf_tenant.tenant_id,
            known_at=perf_tenant.snapshot.known_at,
            events=_contract_events,
        )
    except (sandbox.SandboxNotDeterministic, sandbox.SandboxNotVerified) as exc:
        pytest.exit(str(exc), returncode=1)
    if JobKind.SANDBOX_RESET not in registry.HANDLERS:
        restored = sandbox.with_note(restored, SANDBOX_RESET_WAIT)
    return restored


@pytest.fixture(scope="session")
def perf_processes(
    perf_settings: Any, perf_sandbox: sandbox.RestoredSandbox
) -> Iterator[processes.PerfStack]:
    """DG-PERF-08: api-perf and perf-worker-1 to -4 through scripts/proc.sh; stopped by PID file in
    ``finally`` whatever happens (DG-PERF-05)."""
    run_dir = Path(os.environ.get("EREV_RUN_DIR", str(ROOT / ".run")))
    stack = processes.PerfStack(ROOT, run_dir)
    try:
        stack.start_all()
        yield stack
    finally:
        stack.stop_all()


# --- PRF-4 / PRF-5 session pieces (authored for make perf; NOT RUN in the lane) -------------------


def _totp() -> Callable[[], str]:
    """A current TOTP code from EREV_DEMO_TOTP_SECRET (DG-PERF-03)."""
    from datetime import UTC, datetime

    from erev_api.auth import totp

    secret = os.environ["EREV_DEMO_TOTP_SECRET"]
    return lambda: totp.code_at(secret, totp.time_step(datetime.now(UTC)))


def _signed_in(email: str, sandbox_tenant_id: str) -> perf_client.PerfClient:
    client = perf_client.PerfClient(f"http://127.0.0.1:{processes.API_PORT}")
    client.sign_in(email, os.environ["EREV_DEMO_PASSWORD"], _totp())
    client.select_tenant(sandbox_tenant_id)
    return client


@pytest.fixture(scope="session")
def perf_clients(
    perf_processes: processes.PerfStack, perf_sandbox: sandbox.RestoredSandbox
) -> Iterator[perf_client.PerfClients]:
    """(accountant, controller, reviewer) signed in against api-perf with the perf sandbox
    selected (Codex 0105 PERSONA-1: the preparer, the closer and the approver are three users)."""
    clients = perf_client.PerfClients(
        accountant=_signed_in(ACCOUNTANT_EMAIL, str(perf_sandbox.sandbox_tenant_id)),
        controller=_signed_in(CONTROLLER_EMAIL, str(perf_sandbox.sandbox_tenant_id)),
        reviewer=_signed_in(REVIEWER_EMAIL, str(perf_sandbox.sandbox_tenant_id)),
    )
    try:
        yield clients
    finally:
        for client in clients:
            client.close()


@pytest.fixture(scope="session")
def perf_client_factory(
    perf_sandbox: sandbox.RestoredSandbox, perf_processes: processes.PerfStack
) -> Callable[[], perf_client.PerfClient]:
    """A new signed-in controller client per measuring thread (DG-PERF-03: 4 concurrent clients)."""
    return lambda: _signed_in(CONTROLLER_EMAIL, str(perf_sandbox.sandbox_tenant_id))


@pytest.fixture(scope="session")
def perf_prepared(perf_clients: perf_client.PerfClients, perf_manifest: Any) -> prepare.Prepared:
    """DG-PERF-02 (1), not measured: the month-24 events appended by the accountant — a request
    that holds a manual event approved by the reviewer (BUILD_SPEC CTR-6) — and
    platform.job_concurrency = 8 authored by the accountant, approved by the reviewer."""
    from erev_api.domain.demo import volume

    prepared = prepare.append_month_24(
        perf_clients.accountant, perf_clients.reviewer, perf_manifest
    )
    effective = volume.month_start(prepare.MONTH_24).isoformat() + "T00:00:00+00:00"
    policy_id = prepare.publish_concurrency(
        perf_clients.accountant, perf_clients.reviewer, effective_from=effective
    )
    return prepare.Prepared(
        prepared.events_appended, prepared.events_deferred, prepared.contracts_touched, policy_id
    )


@pytest.fixture(scope="session")
def perf_report(
    perf_manifest: Any, perf_sandbox: sandbox.RestoredSandbox
) -> Iterator[report.PerfReport]:
    """The session report, written to EREV_REPORTS_DIR/perf/report.json at the end (DG-PERF-05)."""
    doc = report.PerfReport(command=os.environ.get("EREV_PERF_COMMAND", "make perf"))
    doc.manifest_sha256 = perf_manifest.sha256
    doc.with_sandbox(perf_sandbox)  # identity and notes (the SANDBOX_RESET wait reaches the report)
    try:
        yield doc
    finally:
        reports = Path(os.environ.get("EREV_REPORTS_DIR", str(ROOT / ".run" / "reports")))
        doc.finished_at = perf_client.utc_now()
        doc.write(reports / "perf" / "report.json")
