"""TOTP per RFC 6238 (05 SAR-26, THR-03; dev-guide DG-KRN-AUTH-06; BUILD_SPEC PLF-5)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from erev_api.auth import totp

# RFC 6238 Appendix B: the SHA-1 seed is the ASCII string "12345678901234567890".
SECRET = base64.b32encode(b"12345678901234567890").decode("ascii")
AT = datetime(1970, 1, 1, 0, 0, 59, tzinfo=UTC)


def test_sar_26_rfc6238_vector_and_window() -> None:
    step = totp.time_step(AT)
    assert step == 1
    # RFC 6238 lists 94287082 at T = 59 for eight digits; six digits keep the last six.
    assert totp.code_at(SECRET, step) == "287082"
    for candidate in (step - 1, step, step + 1):
        code = totp.code_at(SECRET, candidate)
        assert totp.matching_step(SECRET, code, at=AT, last_used_step=None) == candidate
    assert (
        totp.matching_step(SECRET, totp.code_at(SECRET, step + 2), at=AT, last_used_step=None)
        is None
    )
    # Replay: a code for a step at or before last_used_step fails.
    assert totp.matching_step(SECRET, "287082", at=AT, last_used_step=1) is None
    assert (
        totp.matching_step(SECRET, totp.code_at(SECRET, step - 1), at=AT, last_used_step=1) is None
    )
    assert totp.matching_step(SECRET, totp.code_at(SECRET, step + 1), at=AT, last_used_step=1) == 2


def test_malformed_codes_never_match() -> None:
    for code in ("28708", "2870820", "28708a", " 287082", "٢٨٧٠٨٢"):
        assert totp.matching_step(SECRET, code, at=AT, last_used_step=None) is None


def test_provisioning_uri_and_new_secret() -> None:
    uri = totp.provisioning_uri(SECRET, account="lena@avenmoor.test")
    assert uri.startswith("otpauth://totp/eRev:")
    assert f"secret={SECRET}" in uri
    assert "issuer=eRev" in uri
    first, second = totp.new_secret(), totp.new_secret()
    assert len(first) == 32
    assert first != second
    assert len(base64.b32decode(first)) == 20
