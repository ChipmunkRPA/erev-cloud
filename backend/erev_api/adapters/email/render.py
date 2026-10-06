"""RFC 5322 rendering shared by the email adapters (05 NTR-05)."""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage as MimeMessage
from email.utils import format_datetime
from typing import Final

from erev_api.events.outbox import EmailMessage

MESSAGE_ID_DOMAIN: Final = "erev.invalid"


def mime_message(message: EmailMessage, *, sender: str, at: datetime) -> MimeMessage:
    """A plain-text message; the body is 8-bit so links stay on one line."""
    mime = MimeMessage()
    mime["From"] = sender
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["Date"] = format_datetime(at)
    mime["Message-ID"] = f"<{message.reference}@{MESSAGE_ID_DOMAIN}>"
    mime.set_content(message.text, cte="8bit")
    return mime
