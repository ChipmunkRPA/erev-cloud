"""Email adapters (05 NTR-05; CFG-17, CFG-18): ``fake`` writes RFC 5322 files, ``smtp`` sends over
STARTTLS. Composition roots choose one with ``build_email_sender``."""

from __future__ import annotations

from erev_api.adapters.email.fake import FakeEmailSender
from erev_api.adapters.email.smtp import SmtpEmailSender
from erev_api.clock import Clock
from erev_api.config import Settings
from erev_api.events.outbox import EmailSender


def build_email_sender(settings: Settings, clock: Clock) -> EmailSender:
    """``EREV_EMAIL_BACKEND``: ``fake`` (required in dev, test and e2e; DG-KRN-CFG-02), else
    ``smtp``."""
    if settings.email_backend == "fake":
        return FakeEmailSender(settings.run_dir / "mail", clock)
    return SmtpEmailSender.from_settings(settings, clock)
