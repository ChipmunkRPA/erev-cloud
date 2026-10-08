"""Audit chain verification jobs (04 T-PLT-23; 05 §5.6, SCH-01, SCH-02, SAR-31; dev-guide
DG-KRN-AUD-07, DG-KRN-JOB-07; REQ-PLT-019, REQ-PLT-020, CTL-039; BUILD_SPEC PLF-23, BS1-D-13).

``AUDIT_CHAIN_VERIFY`` verifies the tenant's whole chain in one transaction and records the result
through ``audit.verify.record_tenant_verification``: the T-PLT-23 row, the digest of a PASS and the
notification of a FAIL. ``params.trigger`` is ``SCHEDULED`` (the default) or ``ON_DEMAND``. A FAIL
ends the job ``SUCCEEDED_WITH_EXCEPTIONS``, the conservative signal while the exception item it
will raise fails closed (BS1-D-13). The job heartbeats at least every 1,000 verified events or 30
seconds (D-80).

A retry after the verification transaction committed reuses that exact historical result,
including a FAIL, without re-verifying a newer prefix. The outcome identifies it with
``result.verification_id``. Multiple committed results for one job or a mismatched trigger
refuse; no arbitrary latest-result fallback is permitted. This does not certify current
chain state or replace downstream digest-integrity checks.

The periodic task ``audit_chain_verify_all`` (02:00 UTC) defers one SCHEDULED verification per
ACTIVE tenant that has none QUEUED or RUNNING; ``security_chain_verify`` (02:30 UTC) verifies the
global security event chain.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Final

from sqlalchemy import select

from erev_api.audit import verify
from erev_api.audit.verify import ChainVerificationResult
from erev_api.auth.security_chain import verify_security_chain
from erev_api.clock import Clock
from erev_api.controls.operator_alerts import security_chain_alert
from erev_api.db.tables import audit_chain_verification
from erev_api.enums import ControlResult, JobKind
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.problems import Problem

# 05 §5.6 execution profile: 3 attempts.
VERIFY_RETRY: Final = RetryPolicy(max_attempts=3)
VERIFICATIONS_HREF: Final = "/api/v1/audit-events/verifications"
HEARTBEAT_EVENTS: Final = 1_000  # D-80
HEARTBEAT_INTERVAL: Final = timedelta(seconds=30)  # DG-KRN-JOB-04


class ChainHeartbeat:
    """The ``on_event`` of a verification job: ``jc.heartbeat()`` after 1,000 verified events since
    the last heartbeat, or sooner once 30 seconds have passed (D-80; DG-KRN-JOB-04)."""

    def __init__(self, jc: JobContext) -> None:
        self._jc = jc
        self._events = 0
        self._at = jc.clock.now()

    def __call__(self, checked: int) -> None:
        now = self._jc.clock.now()
        if checked - self._events < HEARTBEAT_EVENTS and now - self._at < HEARTBEAT_INTERVAL:
            return
        self._jc.heartbeat()
        self._events, self._at = checked, now


@task(JobKind.AUDIT_CHAIN_VERIFY, retry=VERIFY_RETRY)
def audit_chain_verify(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``AUDIT_CHAIN_VERIFY``: verify the tenant chain and record the result."""
    trigger = str(params.get("trigger", verify.SCHEDULED))
    with jc.unit_of_work() as uow:
        # A worker can die after this transaction commits but before job settlement.
        # Reuse that historical result, including FAIL, instead of verifying a newer
        # prefix or emitting another digest/control result/notification for the same job.
        saved = (
            uow.session.execute(
                select(audit_chain_verification)
                .where(
                    audit_chain_verification.c.tenant_id == uow.principal.tenant_id,
                    audit_chain_verification.c.job_id == jc.job_id,
                )
                .limit(2)
            )
            .mappings()
            .all()
        )
        if len(saved) > 1 or (saved and saved[0]["trigger"] != trigger):
            raise Problem("validation-failed", "The audit job has inconsistent retained results.")
        row = (
            saved[0]
            if saved
            else verify.record_tenant_verification(
                uow,
                trigger=trigger,
                job_id=jc.job_id,
                on_event=ChainHeartbeat(jc),
                digests=jc.runtime.digests,
                alerts=jc.runtime.alerts,
            )
        )
        uow.commit()
    passed = row["result"] == ControlResult.PASS.value
    return JobOutcome(
        state="SUCCEEDED" if passed else "SUCCEEDED_WITH_EXCEPTIONS",
        result={
            "href": VERIFICATIONS_HREF,
            "verification_id": str(row["id"]),
            "counts": {"events_checked": row["events_checked"], "failures": 0 if passed else 1},
        },
    )


def defer_verifications(clock: Clock, *, request_id: str = "audit-chain-verify-all") -> int:
    """SCH-01: one SCHEDULED ``AUDIT_CHAIN_VERIFY`` per ACTIVE tenant without one QUEUED or
    RUNNING; returns the number deferred."""
    return registry.defer_for_active_tenants(
        JobKind.AUDIT_CHAIN_VERIFY,
        {"trigger": verify.SCHEDULED},
        clock=clock,
        request_id=request_id,
    )


def security_chain_verify(
    runtime: JobRuntime, *, request_id: str = "security-chain-verify"
) -> ChainVerificationResult:
    """SCH-02: verify the global security event chain with the worker's key ring."""
    if runtime.keyring is None:
        raise RuntimeError("this job runtime has no key ring")
    result = verify_security_chain(runtime.keyring, request_id=request_id)
    if result.result is ControlResult.FAIL and runtime.alerts is not None:
        # 05 OPR-24 / RB-08: the global chain has no tenant to notify; the operators are alerted.
        runtime.alerts.raise_alert(
            security_chain_alert(
                scope=result.scope,
                from_seq=result.from_chain_seq,
                to_seq=result.to_chain_seq,
                first_failure_seq=result.first_failure_seq,
                raised_at=runtime.clock.now(),
            )
        )
    return result
