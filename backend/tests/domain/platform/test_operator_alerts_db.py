"""05 OPR-24 / RB-08 database witness (record §4.31): a FAIL tenant audit-chain verification
raises the AUDIT_CHAIN_VERIFICATION_FAILED platform alert IN ADDITION to the tenant's NTF-09
CHAIN_VERIFICATION_FAILED notification. NOT RUN on the lane (database-bound; the integrated batch
measures). The chain verification itself is replaced by a FAIL result: this witness measures the
recorder's wiring, not chain arithmetic (tests/pg cover that)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from erev_api.audit import verify
from erev_api.audit.verify import ChainVerificationResult
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.controls.operator_alerts import OperatorAlert, OperatorAlertKind
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import notification
from erev_api.enums import ControlResult, NotificationKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.principals import member
from support.reference import assign


class Recording:
    def __init__(self) -> None:
        self.alerts: list[OperatorAlert] = []

    def raise_alert(self, alert: OperatorAlert) -> tuple[str, ...]:
        self.alerts.append(alert)
        return ("recorded",)


def _failed(*args: Any, **kwargs: Any) -> ChainVerificationResult:
    return ChainVerificationResult(
        scope="tenant",
        from_chain_seq=1,
        to_chain_seq=12,
        events_checked=12,
        result=ControlResult.FAIL,
        first_failure_seq=7,
        failure_detail={"reason": "hmac mismatch"},
        digest_last_hmac=None,
    )


def test_a_failed_tenant_verification_alerts_the_operators_and_notifies_the_tenant(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # NTF-09 addresses "Tenant Admins; Controllers" (PRD §5.4) through their role assignments in
    # force; ``support.principals.member`` revokes the provisioned ``tenant_admin`` grant ("tests
    # assign the roles they need"), so the recipient is given the role back.
    admin = member(keyring, clock)
    assign(admin, "tenant_admin")
    recording = Recording()
    # 05 REL-03 (rev 1.15; D-98 60): the recorder's CTL-039 evidence (``record_execution``) stamps
    # the process release and fails closed with ``release-mismatch`` in a process that never
    # stamped one, so the runtime stamps as the world factories do (P5-DOCTOR-R1; the
    # ``test_audit_verification.py`` runtime fixture).
    stamp_test_release()
    runtime = JobRuntime(
        clock=clock, keyring=keyring, files=LocalFileStore(tmp_path / "files"), alerts=recording
    )
    monkeypatch.setattr(verify, "verify_tenant_chain", _failed)
    principal = system_principal(admin.tenant_id)
    with system_unit_of_work(runtime, principal, request_id="test-operator-alerts") as uow:
        row = verify.record_tenant_verification(
            uow, trigger=verify.SCHEDULED, job_id=None, alerts=runtime.alerts
        )
        uow.commit()
    assert row["result"] == ControlResult.FAIL.value
    (alert,) = recording.alerts
    assert (alert.kind, alert.severity, alert.runbook) == (
        OperatorAlertKind.AUDIT_CHAIN_VERIFICATION_FAILED,
        "SEV-1",
        "RB-08",
    )
    assert alert.fields == {
        "tenant_id": str(admin.tenant_id),
        "verification_id": str(row["id"]),
        "events_checked": 12,
        "first_failure_seq": 7,
    }
    with tenant_session(
        DbContext(tenant_id=admin.tenant_id, user_id=None, entity_scope="*"), read_only=True
    ) as session:
        kinds = session.scalars(
            select(notification.c.kind).where(
                notification.c.recipient_membership_id == admin.membership_id,
                notification.c.subject_id == row["id"],
            )
        ).all()
    assert [str(kind) for kind in kinds] == [NotificationKind.CHAIN_VERIFICATION_FAILED.value]
