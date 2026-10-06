"""T-PLT-06 rev 1.42 preimage forms and key attribution (DG-KRN-AUD-08; SPEC-Q-116 ruling; lane P2).

Form 1 is the preimage of every row written before migration 0061 and excludes the two attribution
columns, so stored hashes never change; form 2 includes them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.security_events import (
    ATTRIBUTION_COLUMNS,
    CANONICAL_VERSION,
    FIRST_SECURITY_HMAC_KEY_ID,
    LEGACY_CANONICAL_VERSION,
    canonical_security_event,
    canonical_version_of,
    security_event_hmac,
    security_event_key_id,
    security_key_version,
)
from erev_api.db.tables.platform import security_event
from erev_engine.canonical import canonical_bytes

ROW: dict[str, Any] = {
    "id": UUID("0191e0a0-0000-7000-8000-00000000000a"),
    "chain_seq": 7,
    "occurred_at": datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
    "kind": "LOGIN_FAILED",
    "outcome": "FAILED",
    "user_id": None,
    "email_sha256": "ab" * 32,
    "session_id": None,
    "tenant_id": None,
    "ip_address": "10.0.0.1",
    "user_agent": "pytest",
    "request_id": "r-canonical",
    "detail": {"attempt": 1},
    "prev_hmac": "cd" * 32,
    "hmac": "ef" * 32,
}


def test_form_1_preimage_is_the_pre_0055_form() -> None:
    legacy = {**ROW, "hmac_key_id": None, "canonical_version": LEGACY_CANONICAL_VERSION}
    pre_0055 = {
        name: ROW[name]
        for name in security_event.c.keys()
        if name not in ("hmac", *ATTRIBUTION_COLUMNS)
    }
    assert canonical_security_event(legacy) == canonical_bytes(pre_0055)
    assert canonical_security_event({k: v for k, v in ROW.items()}) == canonical_bytes(pre_0055), (
        "a row read without the columns (before 0061) is form 1"
    )
    assert canonical_version_of(ROW) == LEGACY_CANONICAL_VERSION
    assert security_event_key_id(ROW) == FIRST_SECURITY_HMAC_KEY_ID
    assert security_event_key_id(legacy) == FIRST_SECURITY_HMAC_KEY_ID


def test_form_2_preimage_includes_the_attribution() -> None:
    current = {**ROW, "hmac_key_id": "security-hmac:3", "canonical_version": CANONICAL_VERSION}
    expected = {name: current[name] for name in security_event.c.keys() if name != "hmac"}
    assert canonical_security_event(current) == canonical_bytes(expected)
    assert canonical_security_event(current) != canonical_security_event(
        {**ROW, "hmac_key_id": None}
    )
    assert security_event_key_id(current) == "security-hmac:3"
    assert security_key_version("security-hmac:3") == 3
    key = bytes(range(32))
    assert security_event_hmac(key, ROW["prev_hmac"], current) != security_event_hmac(
        key, ROW["prev_hmac"], {**ROW, "hmac_key_id": None, "canonical_version": 1}
    )


def test_unknown_forms_and_key_ids_are_refused() -> None:
    with pytest.raises(ValueError):
        canonical_security_event({**ROW, "hmac_key_id": "security-hmac:1", "canonical_version": 3})
    for bad in ("security-hmac:0", "audit-hmac:1", "latest", "security-hmac:latest"):
        with pytest.raises(ValueError):
            security_key_version(bad)
