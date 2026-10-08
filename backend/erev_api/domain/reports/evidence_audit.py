"""RPS-16 original audit digest, explicitly bound to a verification and close anchor.

Never select 'latest' on retry, create a verification, or export tenant-wide event
contents. The caller persists the verification ID with the other pack sources. The
read-only verifier rechecks the recorded prefix; a valid shorter prefix is insufficient.
This proves historical prefix integrity, not a current tenant-wide clean-chain claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.audit import verify
from erev_api.db.tables import audit_chain_verification, audit_event
from erev_api.domain.reports import evidence_close
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.enums import ControlResult, FilePurpose
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

MAX_DIGEST_BYTES = 65536


def checked_digest(
    content: bytes,
    record: Mapping[str, Any],
    *,
    tenant_id: UUID,
    lock_seq: int,
    lock_hmac: str | None,
) -> None:
    """The original canonical digest must state precisely the successful verification row."""
    try:
        if (
            record["tenant_id"] != tenant_id
            or record["result"] != ControlResult.PASS
            or record["first_failure_seq"] is not None
            or record["failure_detail"] is not None
            or record["from_chain_seq"] != 1
            or record["events_checked"] != record["to_chain_seq"]
            or record["to_chain_seq"] < lock_seq
            or lock_seq < 0
            or (lock_seq == 0) != (lock_hmac is None)
            or (record["to_chain_seq"] == 0) != (record["digest_last_hmac"] is None)
            or record["started_at"] > record["finished_at"]
            or len(content) > MAX_DIGEST_BYTES
        ):
            raise ValueError("verification does not cover the lock's audit head")
        document = json.loads(content)
        key_id = document["hmac_key_id"]
        if not isinstance(key_id, str) or not key_id:
            raise ValueError("digest has no key identity")
        result = verify.ChainVerificationResult(
            verify.AUDIT_EVENT_SCOPE,
            record["from_chain_seq"],
            record["to_chain_seq"],
            record["events_checked"],
            ControlResult.PASS,
            None,
            None,
            record["digest_last_hmac"],
        )
        expected = verify.digest_bytes(
            tenant_id=tenant_id,
            result=result,
            hmac_key_id=key_id,
            verified_at=record["finished_at"],
        )
        if content != expected:
            raise ValueError("digest differs from its verification record")
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        raise Problem("validation-failed", "The saved audit digest is inconsistent.") from error


def collect(
    uow: UnitOfWork,
    selection: SourceSelection,
    *,
    verification_id: UUID,
) -> tuple[PackFile, ...]:
    source = evidence_close.read_locked(uow, selection)
    record = (
        uow.session.execute(
            select(audit_chain_verification).where(
                audit_chain_verification.c.tenant_id == selection.tenant_id,
                audit_chain_verification.c.id == verification_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if record is None:
        raise Problem("not-found")
    if record["digest_file_id"] is None or record["finished_at"] > uow.now:
        raise Problem(
            "validation-failed", "The selected audit verification has no eligible digest."
        )
    metadata, stream = open_file(
        uow.session,
        record["digest_file_id"],
        files=uow.files,
        keyring=uow.keyring,
    )
    with stream:
        content = stream.read(MAX_DIGEST_BYTES + 1)
    if (
        metadata["purpose"] != FilePurpose.AUDIT_DIGEST
        or metadata["media_type"] != verify.DIGEST_MEDIA_TYPE
        or len(content) != metadata["size_bytes"]
        or hashlib.sha256(content).hexdigest() != metadata["sha256"]
    ):
        raise Problem("validation-failed", "The stored audit digest file failed verification.")
    lock_seq, lock_hmac = source.record["audit_head_chain_seq"], source.record["audit_head_hmac"]
    checked_digest(
        content, dict(record), tenant_id=selection.tenant_id, lock_seq=lock_seq, lock_hmac=lock_hmac
    )
    if record["to_chain_seq"]:
        checked = verify.verify_tenant_chain(
            uow.session,
            tenant_id=selection.tenant_id,
            keyring=uow.keyring,
            to_seq=record["to_chain_seq"],
        )
        if (
            checked.result is not ControlResult.PASS
            or checked.to_chain_seq != record["to_chain_seq"]
            or checked.events_checked != record["events_checked"]
            or checked.digest_last_hmac != record["digest_last_hmac"]
        ):
            raise Problem(
                "validation-failed", "The saved audit verification prefix no longer verifies."
            )
    if lock_seq:
        anchor = uow.session.execute(
            select(audit_event.c.hmac).where(
                audit_event.c.tenant_id == selection.tenant_id,
                audit_event.c.chain_seq == lock_seq,
            )
        ).scalar_one_or_none()
        if anchor != lock_hmac:
            raise Problem(
                "validation-failed", "The audit digest does not bind the selected lock's head."
            )
    return (
        PackFile("audit/chain_digest.json", content),
        PackFile(
            "audit/sources.json",
            canonical_bytes(
                {
                    "period_lock_id": source.scope.lock_id,
                    "audit_head_chain_seq": lock_seq,
                    "audit_head_hmac": lock_hmac,
                    "verification_id": verification_id,
                    "from_chain_seq": record["from_chain_seq"],
                    "to_chain_seq": record["to_chain_seq"],
                    "events_checked": record["events_checked"],
                    "verified_at": record["finished_at"],
                    "digest_file_id": record["digest_file_id"],
                    "digest_sha256": metadata["sha256"],
                }
            ),
        ),
    )
