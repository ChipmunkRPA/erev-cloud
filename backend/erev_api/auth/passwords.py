"""Password policy and hashing (03 REQ-PLT-004; 05 SAR-06; dev-guide DG-KRN-AUTH-06; BS1-D-07).

Hashes are argon2id with the argon2-cffi defaults (time cost 3, memory 65,536 KiB, parallelism 4).
The policy rejects passwords shorter than 12 characters, equal to the user's email, or found in the
bundled list of 10,000 common passwords, with the PRD ERR-21 copy. The list is the 10,000 most
frequent passwords of 12 or more characters, in frequency order; ``data/NOTICE.md`` records its
source, commit, licence, derivation and SHA-256 (PR-C-06, D-86a). ``verify_dummy`` runs one
verification against a fixed hash, so a login for an unknown email costs what a known one costs.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from erev_api.problems import Problem, ProblemError

MIN_LENGTH: Final = 12
COMMON_PASSWORDS_FILE: Final = Path(__file__).resolve().parent / "data" / "common-passwords.txt"
# PRD ERR-21 detail copy.
TOO_SHORT: Final = "Use at least 12 characters."
EQUALS_EMAIL: Final = "The password cannot be your email address."
TOO_COMMON: Final = "Choose a less common password."

_HASHER: Final = PasswordHasher()


@lru_cache(maxsize=1)
def common_passwords() -> frozenset[str]:
    """The bundled list; entries are lowercase, so lookups compare case-insensitively."""
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line for line in lines if line)


def policy_violation(password: str, *, email: str) -> str | None:
    """The ERR-21 message of the first failing rule, or None when the password is acceptable."""
    if len(password) < MIN_LENGTH:
        return TOO_SHORT
    if password.casefold() == email.strip().casefold():
        return EQUALS_EMAIL
    if password.lower() in common_passwords():
        return TOO_COMMON
    return None


def check_policy(password: str, *, email: str, field: str = "password") -> None:
    """Raise 422 ``password-policy`` naming the field when the password fails the policy."""
    message = policy_violation(password, email=email)
    if message is not None:
        raise Problem(
            "password-policy", message, errors=[ProblemError(field=field, message=message)]
        )


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time argon2 verification; a malformed hash verifies as false."""
    try:
        return _HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _HASHER.check_needs_rehash(password_hash)


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    """A hash of a random secret nobody knows; built once per process."""
    return hash_password(secrets.token_urlsafe(32))


def verify_dummy(password: str) -> bool:
    """One verification against ``dummy_hash`` to equalise timing (SAR-06); always false."""
    verify_password(dummy_hash(), password)
    return False
