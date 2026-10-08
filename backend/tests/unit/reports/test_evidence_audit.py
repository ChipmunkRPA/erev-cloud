"""Digest bytes must exactly match a successful, covering verification record."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from erev_api.audit.verify import ChainVerificationResult, digest_bytes
from erev_api.domain.reports.evidence_audit import checked_digest
from erev_api.enums import ControlResult
from erev_api.problems import Problem

TENANT = uuid4()
NOW = datetime(2026, 10, 8, tzinfo=UTC)
RECORD = {
    "tenant_id": TENANT,
    "from_chain_seq": 1,
    "to_chain_seq": 3,
    "events_checked": 3,
    "result": "PASS",
    "first_failure_seq": None,
    "failure_detail": None,
    "digest_last_hmac": "a" * 64,
    "started_at": NOW,
    "finished_at": NOW,
}
CONTENT = digest_bytes(
    tenant_id=TENANT,
    hmac_key_id="historical-key",
    verified_at=NOW,
    result=ChainVerificationResult(
        "audit_event", 1, 3, 3, ControlResult.PASS, None, None, "a" * 64
    ),
)


def test_successful_covering_digest_and_empty_historical_prefix() -> None:
    checked_digest(CONTENT, RECORD, tenant_id=TENANT, lock_seq=2, lock_hmac="b" * 64)
    empty = {**RECORD, "to_chain_seq": 0, "events_checked": 0, "digest_last_hmac": None}
    content = digest_bytes(
        tenant_id=TENANT,
        hmac_key_id="historical-key",
        verified_at=NOW,
        result=ChainVerificationResult(
            "audit_event", 1, 0, 0, ControlResult.PASS, None, None, None
        ),
    )
    checked_digest(content, empty, tenant_id=TENANT, lock_seq=0, lock_hmac=None)


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": uuid4()},
        {"result": "FAIL"},
        {"first_failure_seq": 1},
        {"failure_detail": {"reason": "bad"}},
        {"from_chain_seq": 2},
        {"to_chain_seq": 1},
        {"events_checked": 2},
        {"digest_last_hmac": "b" * 64},
        {"digest_last_hmac": None},
        {"started_at": NOW + timedelta(seconds=1)},
        {"finished_at": NOW + timedelta(seconds=1)},
    ],
)
def test_changed_verification_or_insufficient_prefix_is_refused(changes: dict) -> None:
    with pytest.raises(Problem):
        checked_digest(
            CONTENT, {**RECORD, **changes}, tenant_id=TENANT, lock_seq=2, lock_hmac="b" * 64
        )


@pytest.mark.parametrize("content", [b"", b"[]", b"null", b"{", CONTENT + b" ", b"x" * 65537])
def test_malformed_noncanonical_or_oversized_digest_is_refused(content: bytes) -> None:
    with pytest.raises(Problem):
        checked_digest(content, RECORD, tenant_id=TENANT, lock_seq=2, lock_hmac="b" * 64)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", str(uuid4())),
        ("last_chain_seq", 4),
        ("events_checked", 4),
        ("hmac_key_id", None),
        ("hmac_key_id", ""),
        ("extra", "not recorded"),
    ],
)
def test_rewritten_digest_metadata_is_refused(field: str, value: object) -> None:
    document = json.loads(CONTENT)
    document[field] = value
    content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    with pytest.raises(Problem):
        checked_digest(content, RECORD, tenant_id=TENANT, lock_seq=2, lock_hmac="b" * 64)


@pytest.mark.parametrize("seq,hmac", [(-1, None), (0, "a" * 64), (2, None), (4, "a" * 64)])
def test_invalid_or_uncovered_lock_anchor_is_refused(seq: int, hmac: str | None) -> None:
    with pytest.raises(Problem):
        checked_digest(CONTENT, RECORD, tenant_id=TENANT, lock_seq=seq, lock_hmac=hmac)
