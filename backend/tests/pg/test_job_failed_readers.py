"""The readers of a failed job's subject on real rows, and the plan of the one read a succeeding
job makes (05 JOB-07 rev 1.165; 04 §15.4 ``JOB_FAILED`` rev 1.226; dev-guide DG-KRN-JOB-05 rev
1.212, DG-KRN-DB-10; item JOB-FAILED-ITEM-1).

A reader answers the one legal entity of the record a failed job works on, or None — and then
no item is raised, because an item without an entity is read by every scope. The rows are the
probe rows of ``support.rows``, written as ``erev_app`` under the tenant's context and rolled
back. The readers of ``JOURNAL_RUN_CALCULATE`` and ``RECONCILIATION_GENERATE`` read the job's
params and no row (``tests/unit/test_job_failed_kinds.py``).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    exception_item,
    integration_connection,
    registry_version,
    sync_run,
)
from erev_api.domain.contracts import compute_job
from erev_api.domain.imports import job_items
from erev_api.domain.integrations import sync
from erev_api.domain.policies import simulation
from erev_api.domain.reference import period_redirty_job
from erev_api.enums import ExceptionSource, ExceptionStatus, JobKind, RegistryScope
from erev_api.jobs.registry import FailedSubject
from sqlalchemy import Select, insert
from sqlalchemy.dialects import postgresql
from support.db import TestDatabase
from support.plans import FORCED, ROWS, analyse, bound_by, plan, scan
from support.principals import member
from support.rows import (
    ROW_BUILDERS,
    RowContext,
    contract_values,
    exception_item_values,
    insert_app_user,
    insert_contract_rows,
    insert_probe_row,
    integration_connection_values,
    registry_version_values,
)

pytestmark = pytest.mark.pg


@pytest.fixture
def tenant_id(test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> UUID:
    return member(keyring, clock).tenant_id


def _generic_plan(tenant_id: UUID, statement: Select[Any]) -> dict[str, Any]:
    """The plan PostgreSQL makes of ``statement`` without its values (``EXPLAIN (GENERIC_PLAN)``,
    the statement written with ``$n`` and sent with nothing): what a prepared statement runs once
    the server plans it for every value at once, and what ``plan_cache_mode =
    force_generic_plan`` always runs. ``support.plans.plan`` explains with the values the read
    binds, and with them a bound value is a constant like a literal."""
    compiled = statement.compile(dialect=postgresql.dialect(paramstyle="numeric_dollar"))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        connection = session.connection()
        for setting in FORCED:
            connection.exec_driver_sql(f"SET LOCAL {setting} = off")
        raw = connection.exec_driver_sql(
            "EXPLAIN (GENERIC_PLAN, FORMAT JSON) " + str(compiled)
        ).scalar_one()
        session.rollback()
    document = json.loads(raw) if isinstance(raw, str) else raw
    found: dict[str, Any] = document[0]["Plan"]
    return found


def test_job_failed_item_1_the_readers_name_one_entity_or_none(tenant_id: UUID) -> None:
    """Each reader on the rows of its kind's subject: the contract and its contracting entity; a
    contract group of one entity, and none for a group of two; none for a preview, an unknown
    record and a subject type the kind does not read; the period state's entity and period; a
    registry version of entity scope; a sync run whose connection serves one entity, under the
    record ``<connection>:<run kind>``. The import kinds have no reader (05 §5.6 rev 1.185): their
    hooks end the upload with an item of its own."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        ctx = RowContext(tenant_id, insert_app_user(session))
        chain = insert_contract_rows(session, tenant_id)
        other = insert_contract_rows(session, tenant_id)
        assert chain.entity_id != other.entity_id

        # --- CONTRACT_COMPUTE
        compute = compute_job.failed_compute
        assert compute(session, "contract", chain.contract_id, {}) == FailedSubject(
            entity_id=chain.entity_id, contract_id=chain.contract_id
        )
        for mode in (
            compute_job.PREVIEW_MODE,
            compute_job.ESTIMATE_PREVIEW_MODE,
            compute_job.MODIFICATION_PREVIEW_MODE,
            compute_job.ADJUSTMENT_PREVIEW_MODE,
        ):
            assert compute(session, "contract", chain.contract_id, {"mode": mode}) is None, mode
        assert compute(session, "contract", new_id(), {}) is None
        assert compute(session, "modification", chain.contract_id, {}) is None
        assert compute(session, None, chain.contract_id, {}) is None
        assert compute(session, "combination_group", chain.group_id, {}) == FailedSubject(
            entity_id=chain.entity_id, combination_group_id=chain.group_id
        )
        session.execute(  # a contract of the other entity joins the group
            insert(contract).values(
                **contract_values(
                    tenant_id,
                    customer_id=other.customer_id,
                    contracting_entity_id=other.entity_id,
                    combination_group_id=chain.group_id,
                )
            )
        )
        assert compute(session, "combination_group", chain.group_id, {}) is None
        assert compute(session, "combination_group", new_id(), {}) is None

        # --- PERIOD_OPEN_REDIRTY
        state = insert_probe_row(session, "period_state", ctx)
        assert period_redirty_job.failed_remark(
            session, period_redirty_job.SUBJECT_TYPE, state["id"], {}
        ) == FailedSubject(entity_id=state["entity_id"], period_id=state["period_id"])
        assert period_redirty_job.failed_remark(session, "period_state", new_id(), {}) is None

        # --- POLICY_SIMULATION
        versions: dict[str, UUID] = {}
        for label, values in (
            ("workspace", {}),
            ("entity", {"scope": RegistryScope.ENTITY, "entity_id": chain.entity_id}),
        ):
            row = registry_version_values(tenant_id, version_no=90 + len(versions), **values)
            session.execute(insert(registry_version).values(**row))
            versions[label] = row["id"]
        simulate = simulation.failed_simulation
        assert simulate(session, "registry_version", versions["entity"], {}) == FailedSubject(
            entity_id=chain.entity_id
        )
        assert simulate(session, "registry_version", versions["workspace"], {}) is None
        assert simulate(session, "rule_set_version", versions["entity"], {}) is None

        # --- SYNC_RUN
        runs: dict[int, tuple[UUID, UUID]] = {}
        for count, entities in enumerate(
            ([], [chain.entity_id], [chain.entity_id, other.entity_id])
        ):
            connection = integration_connection_values(tenant_id, entity_ids=entities)
            session.execute(insert(integration_connection).values(**connection))
            run = dict(ROW_BUILDERS["sync_run"](ctx, session))
            run["integration_connection_id"] = connection["id"]
            session.execute(insert(sync_run).values(**run))
            runs[count] = (run["id"], connection["id"])
        failed_sync = sync.failed_sync
        assert failed_sync(session, "sync_run", runs[0][0], {}) is None
        assert failed_sync(session, "sync_run", runs[1][0], {}) == FailedSubject(
            entity_id=chain.entity_id, key=f"{runs[1][1]}:INBOUND_POLL", sync_run_id=runs[1][0]
        )
        assert failed_sync(session, "sync_run", runs[2][0], {}) is None
        assert failed_sync(session, "sync_run", new_id(), {}) is None
        session.rollback()


def test_job_failed_item_1_the_read_of_a_succeeding_job_is_one_probe_of_the_open_index(
    test_database: TestDatabase, tenant_id: UUID
) -> None:
    """Every job of a kind with a reader that runs to its end asks whether its kind and record
    have an open item (``job_items.open_item``). As ``erev_app`` under the tenant's policy the
    read is bound by the tenant and the ``dedupe_key`` in ``ux_exception_item__open``: the status
    condition is the index's own predicate, written as a literal, so the planner proves the
    partial index whatever the plan mode — a history of items is not read."""
    key = job_items.item_key(ExceptionSource.ENGINE, JobKind.CONTRACT_COMPUTE, str(new_id()))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:  # ten open items in a history of two thousand
        session.execute(
            insert(exception_item),
            [
                {
                    **exception_item_values(tenant_id),
                    "status": (
                        ExceptionStatus.OPEN if number % 200 == 0 else ExceptionStatus.DISMISSED
                    ).value,
                }
                for number in range(ROWS)
            ],
        )
        session.execute(
            insert(exception_item).values(
                **exception_item_values(
                    tenant_id, code="JOB_FAILED", severity="INFO", dedupe_key=key
                )
            )
        )
    analyse(test_database, "exception_item")
    found = plan(tenant_id, job_items.open_item(key).limit(1))
    bound_by(scan(found, "exception_item"), "ux_exception_item__open", "dedupe_key")
    # Planned without its values the read is the same probe. A status that is bound leaves the
    # planner unable to prove the index's predicate, and the read walks another key.
    generic = _generic_plan(tenant_id, job_items.open_item(key).limit(1))
    bound_by(scan(generic, "exception_item"), "ux_exception_item__open", "dedupe_key")
    with tenant_session(context, read_only=True) as session:
        assert job_items.is_open(
            ExceptionSource.ENGINE, session, JobKind.CONTRACT_COMPUTE, key.rsplit(":", 1)[1]
        )
        assert not job_items.is_open(
            ExceptionSource.ENGINE, session, JobKind.CONTRACT_COMPUTE, str(new_id())
        )
