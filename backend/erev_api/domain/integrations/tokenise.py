"""Tokenisation at ingestion (05 ADP-04, PRV-05; 04 T-SRC-01; BUILD_SPEC DIN-2).

Before ``source_record.payload`` is written, the value of every
``erev_api.redaction.CONTACT_FIELDS`` member is replaced with
``{"$pii": "hmac:<hex HMAC-SHA256>"}`` under the tenant's audit HMAC key
(05 KEY-05). An object member is tokenised leaf by leaf (``customer_address.*``), nulls stay null,
and a value already tokenised is kept, so tokenising twice changes nothing. The clear values are
stored nowhere (PRV-05).

[J] L5-1-Q-2: the HMAC input is the string itself, or the canonical JSON of any other value
(dev-guide §5.17), as ``audit.redact.pseudonym`` does for the audit chain.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import tenant
from erev_api.redaction import CONTACT_FIELDS

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["TOKEN_MEMBER", "TOKEN_PREFIX", "is_token", "token", "token_key", "tokenise"]

TOKEN_MEMBER: Final = "$pii"
TOKEN_PREFIX: Final = "hmac:"


def token_key(uow: UnitOfWork) -> bytes:
    """The HMAC key of the caller's tenant (KEY-05 through ``tenant.audit_hmac_key_id``)."""
    key_id = uow.session.execute(
        select(tenant.c.audit_hmac_key_id).where(tenant.c.id == uow.principal.tenant_id)
    ).scalar_one()
    return uow.keyring.tenant_audit_key(str(key_id))


def token(key: bytes, value: Any) -> dict[str, str]:
    """``{"$pii": "hmac:<hex>"}`` of one value."""
    text = value if isinstance(value, str) else canonical_bytes(value).decode("utf-8")
    digest = hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()
    return {TOKEN_MEMBER: TOKEN_PREFIX + digest}


def is_token(value: Any) -> bool:
    """True for a value ``token`` produced."""
    return (
        isinstance(value, Mapping)
        and set(value) == {TOKEN_MEMBER}
        and isinstance(value[TOKEN_MEMBER], str)
        and str(value[TOKEN_MEMBER]).startswith(TOKEN_PREFIX)
    )


def _leaves(key: bytes, value: Any) -> Any:
    if value is None or is_token(value):
        return value
    if isinstance(value, Mapping):
        return {str(name): _leaves(key, item) for name, item in value.items()}
    if isinstance(value, list):
        return [_leaves(key, item) for item in value]
    return token(key, value)


def tokenise(key: bytes, payload: Any, fields: frozenset[str] = CONTACT_FIELDS) -> Any:
    """``payload`` with the values of ``fields`` members, at any depth, tokenised."""
    if isinstance(payload, Mapping):
        return {
            str(name): _leaves(key, item) if name in fields else tokenise(key, item, fields)
            for name, item in payload.items()
        }
    if isinstance(payload, list):
        return [tokenise(key, item, fields) for item in payload]
    return payload
