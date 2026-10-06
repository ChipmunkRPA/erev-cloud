"""SOP-1 control evidence registry against the database (04 T-PLT-39; 03 REQ-CTL-002; CTL-042).

``test_control_id_pattern_and_immutability`` and the round trip run here; the producer walk
``test_ctl_042_every_producer_records_execution`` lands with the producers (SOP-1 1c).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from erev_api.audit.verify import record_tenant_verification
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import control_execution, engine_release
from erev_api.domain.platform.provisioning import TenantProvisionResult
from erev_api.enums import ControlResult, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.uow import unit_of_work
from sqlalchemy import exc, insert, select, update
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import tenant_id_of
from support.rows import control_execution_values, engine_release_values, insert_audited_tenant

INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _release(tenant_id: UUID) -> UUID:
    with tenant_session(_db(tenant_id)) as session:
        values = engine_release_values()
        session.execute(insert(engine_release).values(**values))
        return UUID(str(values["id"]))


def test_control_id_pattern_and_immutability(
    acme: TenantProvisionResult, test_database: TestDatabase
) -> None:
    """``CTL-50`` violates the T-PLT-39 check; an ``UPDATE`` as ``erev_app`` fails with 42501
    (IM-A)."""
    tenant_id = tenant_id_of(acme)
    release_id = _release(tenant_id)
    with tenant_session(_db(tenant_id)) as session:
        with pytest.raises(exc.IntegrityError) as bad:
            session.execute(
                insert(control_execution).values(
                    **control_execution_values(
                        tenant_id, engine_release_id=release_id, control_id="CTL-50"
                    )
                )
            )
        assert getattr(bad.value.orig, "sqlstate", None) == CHECK_VIOLATION
    row = control_execution_values(tenant_id, engine_release_id=release_id)
    with tenant_session(_db(tenant_id)) as session:
        session.execute(insert(control_execution).values(**row))
    with tenant_session(_db(tenant_id)) as session:
        with pytest.raises(exc.ProgrammingError) as denied:
            session.execute(
                update(control_execution)
                .where(control_execution.c.id == row["id"])
                .values(exception_count=9)
            )
        assert getattr(denied.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE


def test_record_execution_round_trip(
    acme: TenantProvisionResult, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """The helper inserts the validated row with the running release and ``uow.now`` and returns
    its id; a FAIL carries its exception count."""
    tenant_id = tenant_id_of(acme)
    _release(tenant_id)
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-control-evidence",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=FROZEN_AT,
        format_locale="en-US",
    )
    run_id = new_id()
    with unit_of_work(
        ctx, clock=clock, keyring=keyring, files=LocalFileStore(tmp_path / "files")
    ) as uow:
        passed = record_execution(
            uow,
            control_id="CTL-039",
            run_ref_type=RunRefType.AUDIT_CHAIN_VERIFICATION,
            run_ref_id=run_id,
            population_count=120,
            exception_count=0,
            result=ControlResult.PASS,
            detail={"events_checked": 120},
        )
        failed = record_execution(
            uow,
            control_id="CTL-039",
            run_ref_type=RunRefType.AUDIT_CHAIN_VERIFICATION,
            run_ref_id=run_id,
            population_count=120,
            exception_count=1,
            result=ControlResult.FAIL,
            detail={"first_failure_seq": 7},
        )
        uow.commit()
    with tenant_session(_db(tenant_id), read_only=True) as session:
        rows = (
            session.execute(
                select(control_execution).where(control_execution.c.run_ref_id == run_id)
            )
            .mappings()
            .all()
        )
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {passed, failed}
    assert by_id[passed]["result"] == "PASS" and by_id[passed]["detail"] == {"events_checked": 120}
    assert by_id[failed]["exception_count"] == 1 and by_id[failed]["result"] == "FAIL"
    assert all(row["executed_at"] == FROZEN_AT for row in rows)
    assert len({row["engine_release_id"] for row in rows}) == 1


@pytest.mark.control("CTL-042")
def test_ctl_042_verification_producer_records_execution(
    keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """The chain-verification producer (CTL-039) inserts one T-PLT-39 row per verification with
    the events checked as its population and the running release; the remaining producers
    (CTL-001/044, CTL-012, CTL-022, CTL-029/030) are walked in their own scenarios when the lane
    database exists."""
    tenant_id = insert_audited_tenant(keyring, events=3, at=FROZEN_AT)
    _release(tenant_id)
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-ctl-042",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=FROZEN_AT,
        format_locale="en-US",
    )
    with unit_of_work(
        ctx, clock=clock, keyring=keyring, files=LocalFileStore(tmp_path / "files")
    ) as uow:
        row = record_tenant_verification(uow, trigger="ON_DEMAND", job_id=None)
        uow.commit()
    with tenant_session(_db(tenant_id), read_only=True) as session:
        executions = (
            session.execute(
                select(control_execution).where(control_execution.c.control_id == "CTL-039")
            )
            .mappings()
            .all()
        )
    assert len(executions) == 1
    execution = executions[0]
    assert execution["run_ref_type"] == "AUDIT_CHAIN_VERIFICATION"
    assert execution["run_ref_id"] == row["id"]
    assert execution["population_count"] == row["events_checked"] and execution["result"] == "PASS"
    assert execution["detail"] == {"trigger": "ON_DEMAND", "first_failure_seq": None}
