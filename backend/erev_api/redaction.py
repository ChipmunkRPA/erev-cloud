"""Contact data in stored source payloads (04 §16.14 API-S-SourceRecord; 05 ADP-04, PRV-05; 03
REQ-SEC-007; BUILD_SPEC DIN-2).

``CONTACT_FIELDS`` names the payload members that hold person names, email addresses, phone
numbers or postal addresses. Ingestion tokenises their values before ``source_record.payload`` is
written (``erev_api.domain.integrations.tokenise``), and API reads replace them with
``"[redacted]"``.

[J] L5-1-Q-2: 05 PRV-05 lists the Stripe members ``customer_email``, ``customer_name``,
``customer_phone`` and ``customer_address.*`` and the CSV member ``customers.contact_email``; the
set adds the plain and contact forms of the same four kinds. A member is matched by name at any
depth, and an object member (an address) counts with every value under it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = ["CONTACT_FIELDS", "REDACTED", "redact_contacts"]

REDACTED: Final = "[redacted]"
CONTACT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "address",
        "billing_address",
        "contact_address",
        "contact_email",
        "contact_name",
        "contact_phone",
        "customer_address",
        "customer_email",
        "customer_name",
        "customer_phone",
        "email",
        "first_name",
        "full_name",
        "last_name",
        "phone",
        "shipping_address",
    }
)


def redact_contacts(value: Any) -> Any:
    """``value`` with every ``CONTACT_FIELDS`` member, at any depth, set to ``"[redacted]"``."""
    if isinstance(value, Mapping):
        return {
            str(name): REDACTED if name in CONTACT_FIELDS else redact_contacts(item)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [redact_contacts(item) for item in value]
    return value
