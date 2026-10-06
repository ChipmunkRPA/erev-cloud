"""Hash-chain verification KRN-AUD (dev-guide §5.5 DG-KRN-AUD-07; 04 T-PLT-06, T-PLT-19,
T-PLT-23; 05 SAR-31; PRD NTF-09; REQ-PLT-020, CTL-039; BUILD_SPEC PLF-23, BS1-D-13).

Verification recomputes every HMAC in ``chain_seq`` order and checks that each row's
``prev_hmac`` equals the ``hmac`` of the row before it. The first row that fails either check is
reported; nothing after it is trusted.

``record_tenant_verification`` records one run of a tenant as a T-PLT-23 row. A PASS exports the
SAR-31 digest; a FAIL notifies the Tenant Admins and Controllers (NTF-09) and alerts the platform
operators (05 OPR-24). No exception item is raised for it: BUILD_SPEC BS1-D-13 had deferred one
and it was ruled not built (05 JOB-07 rev 1.165). The verification still records its row, its
notification and its audit event, and the job reports the failure as an exception.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hmac import compare_digest
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from erev_api.audit.chain import compute_hmac
from erev_api.audit.digests import DigestExporter
from erev_api.audit.writer import record_facts
from erev_api.auth.keyring import KeyRing
from erev_api.auth.security_events import (
    FIRST_SECURITY_HMAC_KEY_ID,
    LEGACY_CANONICAL_VERSION,
    canonical_version_of,
    security_event_hmac,
    security_event_key_id,
    security_key_version,
)
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.controls.operator_alerts import AlertRaiser, audit_chain_alert
from erev_api.db import new_id
from erev_api.db.tables.platform import (
    audit_chain_head,
    audit_chain_verification,
    audit_event,
    security_event,
    tenant,
)
from erev_api.enums import ControlResult, FilePurpose, NotificationKind
from erev_api.files.store import put_file
from erev_api.logging import get_logger, register_logger_fields

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

SECURITY_EVENT_SCOPE: Final = "security_event"
AUDIT_EVENT_SCOPE: Final = "audit_event"
# T-PLT-23 ck_audit_chain_verification__trigger.
SCHEDULED: Final = "SCHEDULED"
ON_DEMAND: Final = "ON_DEMAND"
TRIGGERS: Final = frozenset({SCHEDULED, ON_DEMAND})
VERIFICATION_OBJECT: Final = "audit_chain_verification"
register_logger_fields(__name__, ("object", "status", "generation"))
VERIFICATION_ACTION: Final = "audit_chain_verification.create"  # AUD-FACT (SPEC-Q-188)
# PRD NTF-09, linked to SF-09:verification (SCREENS_B RT-38).
FAILED_TITLE: Final = "Audit chain verification failed"
FAILED_BODY: Final = (
    "Verification stopped at event {sequence}. "
    "Open the verification details and follow the runbook."
)
FAILED_LINK: Final = "/reports/audit-log/verifications/{verification_id}"
RECIPIENT_ROLES: Final = ("controller", "tenant_admin")
DIGEST_FILENAME: Final = "chain_digest.json"
DIGEST_MEDIA_TYPE: Final = "application/json"
# D-80 audit chain anchoring.
ENDS_BEFORE_HEAD: Final = "the chain ends before the head"
HEAD_MISSING: Final = "the audit chain head is missing"
VERIFIED_EVENT_CHANGED: Final = "a verified event is missing or changed"


@dataclass(frozen=True, slots=True)
class ChainVerificationResult:
    scope: str
    from_chain_seq: int
    to_chain_seq: int
    events_checked: int
    result: ControlResult
    first_failure_seq: int | None
    failure_detail: Mapping[str, Any] | None
    digest_last_hmac: str | None


def _failed(
    scope: str,
    *,
    first: int,
    seq: int,
    checked: int,
    reason: str,
    previous: str | None,
    last: int | None = None,
) -> ChainVerificationResult:
    """A FAIL at ``seq``; ``last`` is the last sequence checked when it differs from ``seq``."""
    return ChainVerificationResult(
        scope=scope,
        from_chain_seq=first,
        to_chain_seq=seq if last is None else last,
        events_checked=checked,
        result=ControlResult.FAIL,
        first_failure_seq=seq,
        failure_detail={"reason": reason},
        digest_last_hmac=previous,
    )


def _passed(
    scope: str, *, first: int, last: int, checked: int, previous: str | None
) -> ChainVerificationResult:
    return ChainVerificationResult(
        scope=scope,
        from_chain_seq=first,
        to_chain_seq=last,
        events_checked=checked,
        result=ControlResult.PASS,
        first_failure_seq=None,
        failure_detail=None,
        digest_last_hmac=previous,
    )


def verify_security_event_chain(session: Session, *, keyring: KeyRing) -> ChainVerificationResult:
    """Verify the global security event chain (DG-TST-22; DG-KRN-AUD-08).

    Each row is checked under the key it names (``hmac_key_id``; NULL is ``security-hmac:1``) and
    the preimage form of its ``canonical_version``; ``prev_hmac`` links rows across forms and keys.
    Along the chain the form and the key version never decrease (a rotation only moves forward),
    and a key the provider cannot serve fails the row naming the key id.
    """
    keys: dict[str, bytes] = {}
    rows = session.execute(select(security_event).order_by(security_event.c.chain_seq)).mappings()
    first = last = checked = 0
    previous: str | None = None
    previous_form = LEGACY_CANONICAL_VERSION
    previous_key_version = security_key_version(FIRST_SECURITY_HMAC_KEY_ID)
    for mapping in rows:
        row = dict(mapping)
        seq = int(row["chain_seq"])
        first = first or seq
        checked += 1
        key_id = security_event_key_id(row)
        form = canonical_version_of(row)
        reason: str | None = None
        if row["prev_hmac"] != previous:
            reason = "prev_hmac differs from the hmac of the previous event"
        else:
            try:
                key_version = security_key_version(key_id)
            except ValueError:
                reason = f"hmac_key_id {key_id!r} is not a security-hmac key id"
                key_version = previous_key_version
            if reason is None and (form < previous_form or key_version < previous_key_version):
                reason = (
                    f"canonical_version {form} under {key_id} follows canonical_version "
                    f"{previous_form} under security-hmac:{previous_key_version}; forms and key "
                    "versions never move backwards along the chain"
                )
            if reason is None:
                key = keys.get(key_id)
                if key is None:
                    try:
                        key = keyring.security_event_key(key_id)
                    except Exception as error:  # KeyError, GcpError, ValueError: fail closed
                        reason = (
                            f"key {key_id} is not available to the verifier "
                            f"({type(error).__name__})"
                        )
                    else:
                        keys[key_id] = key
            if reason is None:
                assert key is not None
                try:
                    expected = security_event_hmac(key, previous, row)
                except ValueError as error:
                    reason = str(error)
                else:
                    if not compare_digest(expected, str(row["hmac"])):
                        reason = f"hmac does not match the event content under {key_id}"
        if reason is not None:
            return _failed(
                SECURITY_EVENT_SCOPE,
                first=first,
                seq=seq,
                checked=checked,
                reason=reason,
                previous=previous,
            )
        previous = str(row["hmac"])
        previous_form, previous_key_version = form, key_version
        last = seq
    return _passed(SECURITY_EVENT_SCOPE, first=first, last=last, checked=checked, previous=previous)


def verify_tenant_chain(
    session: Session,
    *,
    tenant_id: UUID,
    keyring: KeyRing,
    from_seq: int = 1,
    to_seq: int | None = None,
    on_event: Callable[[int], None] | None = None,
) -> ChainVerificationResult:
    """Verify ``audit_event`` of one tenant from ``from_seq`` (DG-KRN-AUD-07; SPEC-Q-133).

    The session needs the tenant's context, or an owner connection that sees the rows. Unlike the
    security event chain, audit sequences are contiguous (DB-09), so a gap is a failure.
    ``on_event`` receives the number of events checked after each verified event, so a job can
    heartbeat during a long walk (D-80).
    """
    if from_seq < 1 or (to_seq is not None and to_seq < from_seq):
        raise ValueError("verification needs 1 <= from_seq <= to_seq")
    of_tenant = audit_event.c.tenant_id == tenant_id
    previous: str | None = None
    if from_seq > 1:
        found = session.execute(
            select(audit_event.c.hmac).where(of_tenant, audit_event.c.chain_seq == from_seq - 1)
        ).scalar_one_or_none()
        if found is None:
            return _failed(
                AUDIT_EVENT_SCOPE,
                first=from_seq,
                seq=from_seq,
                checked=0,
                reason="the event before from_seq is missing",
                previous=None,
            )
        previous = str(found)
    # D-80: a verification to the end is anchored to the head. The head is read before the events:
    # an append commits its event and the head together, so every event up to the head read here
    # is visible to the later statement, and events appended meanwhile lie beyond it.
    head = None
    if to_seq is None:
        head = session.execute(
            select(audit_chain_head.c.last_chain_seq, audit_chain_head.c.last_hmac).where(
                audit_chain_head.c.tenant_id == tenant_id
            )
        ).one_or_none()
    upper = to_seq if head is None else int(head.last_chain_seq)
    query = select(audit_event).where(of_tenant, audit_event.c.chain_seq >= from_seq)
    if upper is not None:
        query = query.where(audit_event.c.chain_seq <= upper)
    keys: dict[str, bytes] = {}
    expected, checked = from_seq, 0
    for mapping in session.execute(query.order_by(audit_event.c.chain_seq)).mappings():
        row = dict(mapping)
        checked += 1
        key_id = str(row["hmac_key_id"])
        key = keys.get(key_id) or keys.setdefault(key_id, keyring.tenant_audit_key(key_id))
        reason = None
        if int(row["chain_seq"]) != expected:
            reason = "chain_seq is not contiguous"
        elif row["prev_hmac"] != previous:
            reason = "prev_hmac differs from the hmac of the previous event"
        elif not compare_digest(compute_hmac(key, previous, row), str(row["hmac"])):
            reason = "hmac does not match the event content"
        if reason is not None:
            return _failed(
                AUDIT_EVENT_SCOPE,
                first=from_seq,
                seq=expected,
                checked=checked,
                reason=reason,
                previous=previous,
            )
        previous = str(row["hmac"])
        expected += 1
        if on_event is not None:
            on_event(checked)
    last = expected - 1
    if to_seq is None:
        ended = None
        if head is None:
            ended = HEAD_MISSING
        elif int(head.last_chain_seq) != last or head.last_hmac != previous:
            ended = ENDS_BEFORE_HEAD
        if ended is not None:
            return _failed(
                AUDIT_EVENT_SCOPE,
                first=from_seq,
                seq=expected,
                checked=checked,
                reason=ended,
                previous=previous,
                last=last,
            )
    return _passed(AUDIT_EVENT_SCOPE, first=from_seq, last=last, checked=checked, previous=previous)


def rfc3339(moment: datetime) -> str:
    """API-C-07: an RFC 3339 timestamp in UTC with ``Z``."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def digest_bytes(
    *, tenant_id: UUID, result: ChainVerificationResult, hmac_key_id: str, verified_at: datetime
) -> bytes:
    """The SAR-31 digest ``{tenant_id, last_chain_seq, last_hmac, hmac_key_id, events_checked,
    verified_at}`` as sorted, indented JSON."""
    document = {
        "tenant_id": str(tenant_id),
        "last_chain_seq": result.to_chain_seq,
        "last_hmac": result.digest_last_hmac,
        "hmac_key_id": hmac_key_id,
        "events_checked": result.events_checked,
        "verified_at": rfc3339(verified_at),
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("ascii")


def _anchored_to_last_pass(
    session: Session, tenant_id: UUID, result: ChainVerificationResult
) -> ChainVerificationResult:
    """D-80: the event at the latest earlier PASS row's ``to_chain_seq`` still carries that row's
    ``digest_last_hmac``; otherwise FAIL from that sequence. A head rewound together with deleted
    events verifies the remaining chain, so only the earlier digest reveals the deletion."""
    anchor = session.execute(
        select(audit_chain_verification.c.to_chain_seq, audit_chain_verification.c.digest_last_hmac)
        .where(
            audit_chain_verification.c.tenant_id == tenant_id,
            audit_chain_verification.c.result == ControlResult.PASS.value,
        )
        .order_by(
            audit_chain_verification.c.finished_at.desc(),
            audit_chain_verification.c.to_chain_seq.desc(),
            audit_chain_verification.c.id.desc(),
        )
        .limit(1)
    ).one_or_none()
    if anchor is None or anchor.digest_last_hmac is None:
        return result
    anchor_seq = int(anchor.to_chain_seq)
    found = session.execute(
        select(audit_event.c.hmac).where(
            audit_event.c.tenant_id == tenant_id, audit_event.c.chain_seq == anchor_seq
        )
    ).scalar_one_or_none()
    if found is not None and compare_digest(str(found), str(anchor.digest_last_hmac)):
        return result
    return replace(
        result,
        result=ControlResult.FAIL,
        first_failure_seq=anchor_seq,
        failure_detail={"reason": VERIFIED_EVENT_CHANGED},
    )


def verify_tenant_chain_anchored(
    session: Session, *, tenant_id: UUID, keyring: KeyRing
) -> ChainVerificationResult:
    """The whole chain of a tenant with both D-80 anchors: the head (inside ``verify_tenant_chain``)
    and the latest earlier PASS digest. ``record_tenant_verification`` records it; ``erev verify``
    (05 OPR-11 step (3); ``controls.recovery``) only reads it."""
    result = verify_tenant_chain(session, tenant_id=tenant_id, keyring=keyring)
    if result.result is ControlResult.PASS:
        result = _anchored_to_last_pass(session, tenant_id, result)
    return result


def record_tenant_verification(
    uow: UnitOfWork,
    *,
    trigger: str,
    job_id: UUID | None,
    on_event: Callable[[int], None] | None = None,
    digests: DigestExporter | None = None,
    alerts: AlertRaiser | None = None,
) -> Mapping[str, Any]:
    """Verify the unit of work's tenant chain and insert its T-PLT-23 row (DG-KRN-AUD-07).

    A PASS stores the digest as a file of purpose ``AUDIT_DIGEST`` and, when ``digests`` is given
    (the hosted worker), copies the same bytes create-only to the write-once digest bucket before
    the row is written (SAR-31); an export failure raises, so the job retries and re-verifies. A
    FAIL stores none, because
    the chain after ``first_failure_seq`` is not trusted, and notifies every ACTIVE membership
    holding ``tenant_admin`` or ``controller`` for all entities with ``CHAIN_VERIFICATION_FAILED``
    (NTF-09 rev 1.175: the chain is the workspace's; a workspace without such a holder is told by
    nobody but ``alerts``, the platform operator's alert). The row
    is audited as AUD-FACT. ``started_at`` is ``uow.now``; ``finished_at`` is read from the clock
    once the chain is checked (SPEC-Q-188). The caller commits.
    """
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown verification trigger {trigger!r}")
    # Imported here: notifications enqueue outbox messages, whose relay registers job handlers.
    from erev_api.events import notifications

    session = uow.session
    principal = uow.principal
    tenant_id = principal.tenant_id
    result = verify_tenant_chain(
        session, tenant_id=tenant_id, keyring=uow.keyring, on_event=on_event
    )
    if result.result is ControlResult.PASS:
        result = _anchored_to_last_pass(session, tenant_id, result)
    finished_at = uow.clock.now()
    digest_file_id: UUID | None = None
    if result.result is ControlResult.PASS:
        hmac_key_id = session.execute(
            select(tenant.c.audit_hmac_key_id).where(tenant.c.id == tenant_id)
        ).scalar_one()
        digest = digest_bytes(
            tenant_id=tenant_id,
            result=result,
            hmac_key_id=str(hmac_key_id),
            verified_at=finished_at,
        )
        stored = put_file(
            uow,
            purpose=FilePurpose.AUDIT_DIGEST,
            stream=io.BytesIO(digest),
            original_filename=DIGEST_FILENAME,
            media_type=DIGEST_MEDIA_TYPE,
        )
        digest_file_id = UUID(str(stored.row["id"]))
        if digests is not None:
            export = digests.export(tenant_id=tenant_id, digest=digest, verified_at=finished_at)
            get_logger(__name__).info(
                "audit.digest_export_recorded",
                tenant_id=str(tenant_id),
                object=export.name,
                status=export.status,
                generation=export.generation,
            )
    row: dict[str, Any] = {
        "tenant_id": tenant_id,
        "id": new_id(),
        "trigger": trigger,
        "from_chain_seq": result.from_chain_seq,
        "to_chain_seq": result.to_chain_seq,
        "events_checked": result.events_checked,
        "result": result.result.value,
        "first_failure_seq": result.first_failure_seq,
        "failure_detail": None if result.failure_detail is None else dict(result.failure_detail),
        "digest_last_hmac": result.digest_last_hmac,
        "digest_file_id": digest_file_id,
        "job_id": job_id,
        "started_at": uow.now,
        "finished_at": finished_at,
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    session.execute(insert(audit_chain_verification).values(**row))
    # SOP-1 CTL-039: one T-PLT-39 row per verification (population: events checked; a FAIL is
    # one exception). The row is AUD-FACT evidence next to the T-PLT-23 row.
    record_execution(
        uow,
        control_id="CTL-039",
        run_ref_type=RunRefType.AUDIT_CHAIN_VERIFICATION,
        run_ref_id=UUID(str(row["id"])),
        population_count=int(result.events_checked),
        exception_count=0 if result.result is ControlResult.PASS else 1,
        result=ControlResult.PASS if result.result is ControlResult.PASS else ControlResult.FAIL,
        detail={"trigger": trigger, "first_failure_seq": result.first_failure_seq},
    )
    record_facts(
        uow,
        action=VERIFICATION_ACTION,
        object_type=VERIFICATION_OBJECT,
        ids=[row["id"]],
        detail={
            "trigger": trigger,
            "result": row["result"],
            "first_failure_seq": result.first_failure_seq,
            "digest_file_id": None if digest_file_id is None else str(digest_file_id),
        },
    )
    if result.result is ControlResult.FAIL:
        notifications.notify(
            uow,
            # the chain is the workspace's: the holders of the two roles for all entities
            recipient_membership_ids=notifications.role_holders(
                session, role_codes=RECIPIENT_ROLES, entity_id=None, at=uow.now
            ),
            kind=NotificationKind.CHAIN_VERIFICATION_FAILED,
            title=FAILED_TITLE,
            body=FAILED_BODY.format(sequence=result.first_failure_seq),
            link_path=FAILED_LINK.format(verification_id=row["id"]),
            subject_type=VERIFICATION_OBJECT,
            subject_id=row["id"],
        )
        if alerts is not None:
            # 05 OPR-24 / RB-08: the platform operators, in addition to the tenant's NTF-09 notice.
            alerts.raise_alert(
                audit_chain_alert(
                    tenant_id=tenant_id,
                    verification_id=UUID(str(row["id"])),
                    events_checked=int(result.events_checked),
                    first_failure_seq=result.first_failure_seq,
                    raised_at=uow.now,
                )
            )
    return MappingProxyType(row)
