"""Time-based one-time passwords KRN-AUTH (RFC 6238; 05 SAR-26, THR-03; dev-guide DG-KRN-AUTH-06;
04 T-PLT-04).

SHA-1, six digits, a 30-second step and a window of one step either side, through pyotp. A code
matches only a step later than the factor's ``last_used_step``, so each code is accepted once. The
functions hold no state and read no clock: callers pass the request time.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Final

import pyotp

ISSUER: Final = "eRev"
DIGITS: Final = 6
STEP: Final = timedelta(seconds=30)
WINDOW: Final = 1  # steps accepted either side of the current step
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)


def _totp(secret_base32: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret_base32, digits=DIGITS, interval=int(STEP.total_seconds()))


def new_secret() -> str:
    """A random 160-bit seed as 32 base32 characters."""
    return pyotp.random_base32()


def time_step(at: datetime) -> int:
    """The RFC 6238 time counter T of ``at``."""
    return (at - _EPOCH) // STEP


def code_at(secret_base32: str, step: int) -> str:
    return _totp(secret_base32).generate_otp(step)


def matching_step(
    secret_base32: str, code: str, *, at: datetime, last_used_step: int | None
) -> int | None:
    """The step in t−1 … t+1 whose code equals ``code`` and that is later than
    ``last_used_step``; None when no step matches (wrong, expired or replayed code)."""
    if len(code) != DIGITS or not (code.isascii() and code.isdigit()):
        return None
    current = time_step(at)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(code_at(secret_base32, step), code):
            return step
    return None


def provisioning_uri(secret_base32: str, *, account: str) -> str:
    """``otpauth://totp/eRev:<account>?secret=…&issuer=eRev`` for authenticator apps."""
    return _totp(secret_base32).provisioning_uri(name=account, issuer_name=ISSUER)
