"""Security event log and its HMAC chain (04 T-PLT-06; 05 KEY-03; dev-guide §5.5).

Events chain globally in ``chain_seq`` order: ``prev_hmac`` holds the ``hmac`` of the row before,
and ``hmac`` = HMAC-SHA256 with the platform security key over ``prev_hmac ‖ canonical(row without
hmac)``, the construction DG-KRN-AUD-03 fixes for audit events. Writers serialise on a
transaction-scoped advisory lock: ``erev_app`` holds only SELECT and INSERT on the table, which no
exclusive ``LOCK TABLE`` mode accepts. ``chain_seq`` comes from ``erev.security_event_seq``, so a
rolled-back writer leaves a gap; verification follows ``prev_hmac`` and needs no contiguous
sequence.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import Connection, insert, select, text
from sqlalchemy.orm import Session

from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.tables.platform import security_event
from erev_api.enums import AuditOutcome, SecurityEventKind

# "erevSECE" as a bigint; held by pg_advisory_xact_lock while one event is appended.
SECURITY_EVENT_CHAIN_LOCK_KEY: Final = 0x6572657653454345
# 05 KEY-03 key id. T-PLT-06 has no key id column, so every row uses version 1 (SPEC-Q-116).
# 04 T-PLT-06 rev 1.42 (SPEC-Q-116 ruling; DG-KRN-AUD-08): rows written before migration 0061 carry
# no key id and preimage form 1 and are attributed to the first key; new rows carry the pinned key
# id (`KeyRing.current_security_key_id`) and preimage form 2, which includes the attribution.
FIRST_SECURITY_HMAC_KEY_ID: Final = "security-hmac:1"
# Compatibility alias for lane P6's recovery inventory (d4fbc61): the FIRST key id, not the current
# one; callers list every required id through ``required_security_key_ids`` instead.
SECURITY_HMAC_KEY_ID: Final = FIRST_SECURITY_HMAC_KEY_ID
LEGACY_CANONICAL_VERSION: Final = 1
CANONICAL_VERSION: Final = 2
ATTRIBUTION_COLUMNS: Final = ("hmac_key_id", "canonical_version")
_SECURITY_KEY_ID: Final = re.compile(r"^security-hmac:(?P<version>[1-9][0-9]*)$")
USER_AGENT_MAX_CHARS: Final = 512

_LOCK = text("SELECT pg_advisory_xact_lock(:key)")
_NEXT_SEQ_AND_TIME = text("SELECT nextval('erev.security_event_seq'), now()")


@dataclass(frozen=True, slots=True)
class SecurityEventRecord:
    id: UUID
    chain_seq: int
    hmac: str


@dataclass(frozen=True, slots=True)
class ChainHead:
    """The last row of the chain as the writer sees it under the chain lock."""

    hmac: str | None  # None on an empty chain
    key_id: str  # security-hmac:<n> the head was signed with (NULL rows → version 1)
    canonical_version: int


class StaleSecurityKeyWriter(RuntimeError):
    """A writer pinned behind the chain head (DG-KRN-AUD-08 admission): the row is refused before
    the INSERT, because a later verifier would reject the whole chain for the downgrade."""

    def __init__(self, *, writer_key_id: str, writer_form: int, head: ChainHead) -> None:
        super().__init__(
            f"security event writer pinned to {writer_key_id} (canonical_version {writer_form}) "
            f"is behind the chain head {head.key_id} (canonical_version "
            f"{head.canonical_version}); refuse to append"
        )
        self.writer_key_id = writer_key_id
        self.head = head


_HEAD = (
    select(security_event.c.hmac, security_event.c.hmac_key_id, security_event.c.canonical_version)
    .order_by(security_event.c.chain_seq.desc())
    .limit(1)
)


def chain_head(bind: Session | Connection) -> ChainHead:
    """The head under the caller's lock (or a snapshot of it without the lock)."""
    mapping = bind.execute(_HEAD).mappings().one_or_none()
    if mapping is None:
        return ChainHead(None, FIRST_SECURITY_HMAC_KEY_ID, LEGACY_CANONICAL_VERSION)
    row: dict[str, Any] = dict(mapping)
    return ChainHead(str(row["hmac"]), security_event_key_id(row), canonical_version_of(row))


def assert_writer_admissible(head: ChainHead, *, writer_key_id: str, writer_form: int) -> None:
    """Forms and key versions never move backwards along the chain (04 T-PLT-06 rev 1.42): a
    writer whose pin is behind the head is refused deterministically, naming both key ids."""
    if writer_form < head.canonical_version or security_key_version(
        writer_key_id
    ) < security_key_version(head.key_id):
        raise StaleSecurityKeyWriter(
            writer_key_id=writer_key_id, writer_form=writer_form, head=head
        )


def required_security_key_ids(
    bind: Session | Connection, keyring: KeyRing, *, tenant_id: UUID | None = None
) -> list[str]:
    """P6 recovery interface (OPR-11 restore drill, RB-05 key inventory): every
    ``security-hmac:<n>`` id a restored deployment must be able to serve to verify the chain — the
    distinct key ids the T-PLT-06 rows name (NULL → ``security-hmac:1``), optionally only the rows
    of one tenant, plus the current pinned id — sorted by version. Key ids only, never material."""
    statement = select(security_event.c.hmac_key_id).distinct()
    if tenant_id is not None:
        statement = statement.where(security_event.c.tenant_id == tenant_id)
    ids = {
        security_event_key_id({"hmac_key_id": value}) for value in bind.execute(statement).scalars()
    }
    ids.add(keyring.current_security_key_id())
    return sorted(ids, key=security_key_version)


def check_writer_admission_at_startup(keyring: KeyRing, *, request_id: str) -> ChainHead:
    """Startup fence for api and worker (KEY-03 rev 1.17): a process whose pin is behind the chain
    head refuses to start, so a stale writer never gets to append. Returns the head seen."""
    # Imported here: db.session builds platform_session on record_security_event (DG-KRN-DB-03),
    # so a module-level import would be circular.
    from erev_api.db.session import identity_session

    with identity_session(request_id=request_id) as session:
        head = chain_head(session)
    assert_writer_admissible(
        head, writer_key_id=keyring.current_security_key_id(), writer_form=CANONICAL_VERSION
    )
    return head


def canonical_version_of(row: Mapping[str, Any]) -> int:
    """The row's preimage form; a row without the column (written before 0061) is form 1."""
    version = row.get("canonical_version")
    return LEGACY_CANONICAL_VERSION if version is None else int(version)


def security_event_key_id(row: Mapping[str, Any]) -> str:
    """The key id a row was signed with; NULL attributes the row to ``security-hmac:1``."""
    key_id = row.get("hmac_key_id")
    return FIRST_SECURITY_HMAC_KEY_ID if key_id is None else str(key_id)


def security_key_version(key_id: str) -> int:
    """``<n>`` of ``security-hmac:<n>``; any other id is malformed (DG-KRN-KEY-02)."""
    match = _SECURITY_KEY_ID.fullmatch(key_id)
    if match is None:
        raise ValueError(f"{key_id!r} is not a security-hmac key id")
    return int(match["version"])


def canonical_security_event(row: Mapping[str, Any]) -> bytes:
    """Canonical bytes (§5.17) of the row's HMAC preimage columns, by its preimage form: form 1
    (rows before 0061) is every T-PLT-06 column except ``hmac``, ``hmac_key_id`` and
    ``canonical_version``, so stored hashes never change; form 2 is every column except ``hmac``
    (DG-KRN-AUD-08)."""
    version = canonical_version_of(row)
    if version == CANONICAL_VERSION:
        excluded = {"hmac"}
    elif version == LEGACY_CANONICAL_VERSION:
        excluded = {"hmac", *ATTRIBUTION_COLUMNS}
    else:
        raise ValueError(f"unknown security_event canonical_version {version}")
    values = {name: row[name] for name in security_event.c.keys() if name not in excluded}
    if values["ip_address"] is not None:
        values["ip_address"] = str(ipaddress.ip_address(str(values["ip_address"])))
    return canonical_bytes(values)


def security_event_hmac(key: bytes, prev_hmac: str | None, row: Mapping[str, Any]) -> str:
    message = (prev_hmac or "").encode("ascii") + canonical_security_event(row)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def hold_chain_lock(bind: Session | Connection) -> None:
    """Take the chain lock now, until the transaction ends: for a caller that reads the log and
    appends to it as one step (the lockout count of an email without an account, REQ-PLT-004).
    ``record_security_event`` takes the same lock again; the lock is re-entrant."""
    bind.execute(_LOCK, {"key": SECURITY_EVENT_CHAIN_LOCK_KEY})


def record_security_event(
    bind: Session | Connection,
    *,
    keyring: KeyRing,
    kind: SecurityEventKind,
    outcome: AuditOutcome,
    request_id: str,
    user_id: UUID | None = None,
    email_sha256: str | None = None,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> SecurityEventRecord:
    """Append one event to the chain inside the caller's transaction.

    ``occurred_at`` is the transaction start time (``now()``), as for the SC-C defaults.
    """
    bind.execute(_LOCK, {"key": SECURITY_EVENT_CHAIN_LOCK_KEY})
    head = chain_head(bind)
    key_id = keyring.current_security_key_id()
    # Admission before the INSERT and before the sequence advances (Codex 76cbee4 finding): a
    # stale writer is refused here, under the same lock every writer holds, not detected later.
    assert_writer_admissible(head, writer_key_id=key_id, writer_form=CANONICAL_VERSION)
    prev_hmac = head.hmac
    chain_seq, occurred_at = bind.execute(_NEXT_SEQ_AND_TIME).one()
    row: dict[str, Any] = {
        "id": new_id(),
        "chain_seq": int(chain_seq),
        "occurred_at": occurred_at,
        "kind": kind.value,
        "outcome": outcome.value,
        "user_id": user_id,
        "email_sha256": email_sha256,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "ip_address": None if ip_address is None else str(ipaddress.ip_address(ip_address)),
        "user_agent": None if user_agent is None else user_agent[:USER_AGENT_MAX_CHARS],
        "request_id": request_id,
        "detail": dict(detail or {}),
        "prev_hmac": prev_hmac,
        # DG-KRN-AUD-08: the pinned current key id and the preimage form that includes it.
        "hmac_key_id": key_id,
        "canonical_version": CANONICAL_VERSION,
    }
    row["hmac"] = security_event_hmac(keyring.security_event_key(key_id), prev_hmac, row)
    bind.execute(insert(security_event).values(**row))
    return SecurityEventRecord(id=row["id"], chain_seq=row["chain_seq"], hmac=row["hmac"])
