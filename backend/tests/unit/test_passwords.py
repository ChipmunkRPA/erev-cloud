"""Password policy and hashing (03 REQ-PLT-004; 05 SAR-06; dev-guide DG-KRN-AUTH-06; BS1-D-07)."""

from __future__ import annotations

import hashlib
import re

import pytest
from erev_api.auth import passwords
from erev_api.problems import Problem

PASSING = "Lena!Revenue2026"


def _policy_detail(password: str, email: str) -> str | None:
    with pytest.raises(Problem) as refused:
        passwords.check_policy(password, email=email)
    assert refused.value.slug == "password-policy"
    assert refused.value.status == 422
    assert [error.field for error in refused.value.errors] == ["password"]
    return refused.value.detail


def test_req_plt_004_password_policy() -> None:
    assert _policy_detail("Short1!pass", "maya@demo.erev") == "Use at least 12 characters."
    assert _policy_detail("password1234", "maya@demo.erev") == "Choose a less common password."
    assert _policy_detail("PASSWORD1234", "maya@demo.erev") == "Choose a less common password."
    assert (
        _policy_detail("maya@demo.erev", "maya@demo.erev")
        == "The password cannot be your email address."
    )
    assert (
        _policy_detail("Maya@Demo.erev", " maya@demo.erev ")
        == "The password cannot be your email address."
    )
    passwords.check_policy(PASSING, email="maya@demo.erev")

    stored = passwords.hash_password(PASSING)
    assert stored.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert passwords.verify_password(stored, PASSING)
    assert not passwords.verify_password(stored, "Lena!Revenue2027")
    assert not passwords.needs_rehash(stored)


def test_common_password_list_is_bundled() -> None:
    entries = passwords.common_passwords()
    lines = passwords.COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10_000
    assert len(entries) == 10_000
    assert all(entry == entry.lower() for entry in entries)
    # The list only holds entries the length rule does not already refuse (NOTICE.md derivation).
    assert all(len(entry) >= passwords.MIN_LENGTH for entry in entries)
    # Frequency order of the source corpus, most frequent first.
    assert lines[:4] == ["123qweasdzxc", "1qaz2wsx3edc", "q1w2e3r4t5y6", "1q2w3e4r5t6y"]


def test_common_password_list_notice_records_provenance() -> None:
    """PR-C-06, SPEC-Q-128, D-86a: the vendored file equals the digest its NOTICE records."""
    notice = (passwords.COMMON_PASSWORDS_FILE.parent / "NOTICE.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(passwords.COMMON_PASSWORDS_FILE.read_bytes()).hexdigest()
    recorded = re.search(r"SHA-256 of `common-passwords.txt`: `([0-9a-f]{64})`", notice)
    assert recorded is not None
    assert recorded.group(1) == digest
    assert "https://github.com/danielmiessler/SecLists" in notice
    assert "8f4c1846cdb02a7024bd09decce1afc1ef5df46b" in notice
    assert "MIT License" in notice


def test_pr_c_06_frequent_long_passwords_are_refused() -> None:
    for common in ("111111111111", "123123123123", "1q2w3e4r5t6y", "qwertyuiop12"):
        assert _policy_detail(common, "maya@demo.erev") == "Choose a less common password."


def test_verification_of_malformed_or_dummy_hash_is_false() -> None:
    assert not passwords.verify_password("not-an-argon2-hash", PASSING)
    assert passwords.dummy_hash().startswith("$argon2id$")
    assert passwords.verify_dummy(PASSING) is False
