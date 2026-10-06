"""No statement locks an identity's row with its key (dev-guide DG-KRN-AUTH-08 rev 1.238; 05 SAR-09
rev 1.178; item AUTH-LOCK-ORDER-1).

``app_user`` is the row every security event, session and membership refers to. A lock that takes
its key (``FOR UPDATE``) makes each insert that refers to the identity wait for it - and the event
of a refused code step waits there while it holds the security chain's lock, which the password
step that holds the row asks for next: the deadlock measured on 2026-10-01 between two sign-ins
of one member. A statement that locks the row therefore says ``with_for_update(key_share=True)``
(``FOR NO KEY UPDATE``): it still keeps every other writer of the identity out.

The scan reads the source: a ``with_for_update`` call whose receiver names ``app_user`` and that
does not hand the lock to another table through ``of=``. A statement built in a variable before
it is locked is not seen; ``sessions.end_provider_sessions`` is the one such place, and its lock
is in the list because its ``order_by`` names the table.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Final

import erev_api

# The package as it is imported: the scan reads the code the tests run.
PRODUCT: Final = Path(erev_api.__file__).resolve().parent
_TABLE: Final = re.compile(r"\bapp_user\b")
# Where an identity's row is locked, by module: a new lock is added here with its reason.
IDENTITY_LOCKS: Final = {
    "auth/credentials.py": 2,  # a password change; a reset request
    "auth/mfa.py": 1,  # the code step, before it writes an event
    "auth/oidc.py": 1,  # the operator's invitation of an identity for a provider
    # two sign-ins, the password check, its second look where a later transaction opens the
    # session (an invitation's acceptance, rev 1.267), a rotation's hold, the command
    "auth/sessions.py": 6,
    "domain/platform/me.py": 1,  # a member's own preferences
    "domain/platform/privacy.py": 1,  # the erasure
    "domain/platform/users.py": 1,  # the person of an invited membership
}


def identity_locks(source: str) -> list[tuple[int, bool]]:
    """(line, taken without the key) of every row lock on a statement that names ``app_user``."""
    found: list[tuple[int, bool]] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "with_for_update"
        ):
            continue
        receiver = ast.get_source_segment(source, node.func.value) or ""
        if not _TABLE.search(receiver):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        of = keywords.get("of")
        if of is not None and not _TABLE.search(ast.get_source_segment(source, of) or ""):
            continue  # the lock is another table's: the identity is only joined
        share = keywords.get("key_share")
        found.append((node.lineno, isinstance(share, ast.Constant) and share.value is True))
    return found


def test_dg_krn_auth_08_an_identitys_row_is_locked_without_its_key() -> None:
    keyed: list[str] = []
    counted: Counter[str] = Counter()
    for path in sorted(PRODUCT.rglob("*.py")):
        relative = path.relative_to(PRODUCT).as_posix()
        for line, keyless in identity_locks(path.read_text(encoding="utf-8")):
            counted[relative] += 1
            if not keyless:
                keyed.append(f"{relative}:{line}")
    assert keyed == [], keyed
    assert dict(counted) == IDENTITY_LOCKS


def test_dg_krn_auth_08_the_scan_tells_a_keyed_lock_and_another_tables() -> None:
    """Every rule can fail."""
    keyed = "select(app_user.c.id).where(app_user.c.id == user_id).with_for_update()\n"
    keyless = keyed.replace("()", "(key_share=True)")
    skipped = keyed.replace("()", "(skip_locked=True)")
    other = "select(token).join(app_user, on).with_for_update(of=token)\n"
    own = "select(app_user).join(token, on).with_for_update(of=app_user)\n"
    unrelated = "select(user_session.c.id).with_for_update()\n"
    assert identity_locks(keyed) == [(1, False)]
    assert identity_locks(keyless) == [(1, True)]
    assert identity_locks(skipped) == [(1, False)]
    assert identity_locks(other) == []
    assert identity_locks(own) == [(1, False)]
    assert identity_locks(unrelated) == []
