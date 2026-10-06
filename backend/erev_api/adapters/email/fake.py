"""Fake email adapter (05 NTR-05; PRD WLD-U-R4; CFG-17).

``FakeEmailSender`` writes each message as an RFC 5322 file
``<root>/<tenant code>/<UTC timestamp>-<reference>.eml``, where the root is ``${EREV_RUN_DIR}/mail``
and the reference is the notification id, or the aggregate id of a message without one. dev, test
and e2e use it (DG-KRN-CFG-02); it opens no network connection.
"""

from __future__ import annotations

import re
from datetime import UTC
from email.policy import SMTP
from pathlib import Path
from typing import Final

from erev_api.adapters.email.render import mime_message
from erev_api.clock import Clock
from erev_api.events.outbox import EmailMessage

SENDER: Final = "eRev <no-reply@erev.invalid>"
_TENANT_CODE: Final = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # DG-KRN-TEN-03


class FakeEmailSender:
    def __init__(self, root: Path, clock: Clock) -> None:
        self._root = root
        self._clock = clock

    def send(self, message: EmailMessage) -> str:
        """Write the message file and return its name."""
        if not _TENANT_CODE.fullmatch(message.tenant_code):
            raise ValueError("the tenant code is not a path-safe workspace code")
        at = self._clock.now().astimezone(UTC)
        directory = self._root / message.tenant_code
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{at.strftime('%Y%m%dT%H%M%S%fZ')}-{message.reference}.eml"
        path.write_bytes(mime_message(message, sender=SENDER, at=at).as_bytes(policy=SMTP))
        return path.name
