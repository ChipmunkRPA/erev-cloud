"""A production-shaped ``Settings`` for tests (05 CFG-01, CFG-17, CFG-18, CFG-26; SAR-40).

Since 05 SAR-40 rev 1.53 a production api or worker refuses to start on the fake email backend
and on placeholder or repeated master keys, so a test that starts one under ``production`` needs
the rest of the production configuration too: the smtp backend with its relay and sender. The
master keys of the test environment are generated ones (DG-ENV-16), which the rule accepts.
"""

from __future__ import annotations

from erev_api.config import Environment, Settings

SMTP = {
    "email_backend": "smtp",
    "smtp_host": "smtp.erev.example",
    "smtp_from": "erev@erev.example",
}


def production_settings(settings: Settings, **update: object) -> Settings:
    """``settings`` as a production process would hold them: ``EREV_ENV=production`` and the
    smtp email backend; ``update`` overrides any member (a test of a refusal passes the bad
    value it is about)."""
    return settings.model_copy(update={"env": Environment.PRODUCTION, **SMTP, **update})
