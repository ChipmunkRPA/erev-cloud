"""Emailed links in tests (05 NTR-04; 04 T-INT-03 ``payload`` rev 1.151).

An ``EMAIL`` outbox message never holds the token of a link: a password-reset or invitation
message keeps the place ``{token}`` in ``link_path`` and names the token by reference
(``link_token``). ``emailed_link`` answers the link as the recipient gets it — composed the way the
dispatcher composes it — after checking that the stored payload holds no token; ``emailed_token``
is the token of such a link.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Final

from erev_api.auth.keyring import KeyRing, build_keyring
from erev_api.config import get_settings
from erev_api.events import outbox

__all__ = ["TOKEN", "emailed_link", "emailed_token"]

# The 43 URL-safe characters of a 256-bit link token.
TOKEN: Final = r"[A-Za-z0-9_-]{43}"


@lru_cache(maxsize=1)
def _session_keyring() -> KeyRing:
    """The key ring of the test session, as the ``keyring`` fixture builds it (``conftest``)."""
    return build_keyring(get_settings())


def emailed_link(payload: Mapping[str, Any], keyring: KeyRing | None = None) -> str:
    """The link path of the message's email (without the public origin), composed with
    ``keyring`` — the session's own when none is given."""
    link = outbox.email_link_path(payload, keyring or _session_keyring())
    assert link is not None, payload
    named = payload.get(outbox.LINK_TOKEN)
    if named is not None:
        token = link.rsplit("token=", 1)[1]
        assert re.fullmatch(TOKEN, token), link
        # Rulings R-48 (g), R-53 (h): the row names the token; it never holds it.
        assert token not in json.dumps(payload), "the outbox payload holds the link's token"
        assert payload["link_path"].endswith(outbox.TOKEN_PLACE), payload["link_path"]
        assert set(named) == {"purpose", "reference", "key_id"}, named
    return link


def emailed_token(
    payload: Mapping[str, Any], keyring: KeyRing | None = None, *, prefix: str
) -> str:
    """The token of the message's link, which must be ``prefix`` followed by the token."""
    link = emailed_link(payload, keyring)
    matched = re.fullmatch(re.escape(prefix) + f"({TOKEN})", link)
    assert matched is not None, link
    return matched.group(1)
