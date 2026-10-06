"""Identity-scope reads the recovery verifier needs (05 OPR-11 (3), OPR-12; RB-04, RB-06), kept in
the auth layer because ``identity_session`` belongs to the ``erev_api.auth`` repositories
(DG-KRN-DB-02 as amended by D-78; guard ``test_dg_krn_db_02_identity_session_importers``).

What is read here, and why through the identity scope: the platform security-event chain (auth's
T-PLT-06, written by ``erev_api.auth.security_events``), the MFA factor envelopes
(``user_mfa_factor``, an RLS-NONE-U identity table whose seeds are opened only to prove the KEK
still serves them, the
plaintext discarded) and the schema revision. Nothing here writes, and no session is handed back to
the kernel: the verifier receives a snapshot of rows and results.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select, text

from erev_api.audit.verify import ChainVerificationResult, verify_security_event_chain
from erev_api.db.session import identity_session
from erev_api.db.tables import security_event, user_mfa_factor

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.auth.keyring import KeyRing

SECURITY_HEAD: Final = select(func.coalesce(func.max(security_event.c.chain_seq), 0))
ALEMBIC_VERSION: Final = text("SELECT version_num FROM erev.alembic_version")

# (session, keyring) -> (required key ids, current pin id, chain head key id); supplied by the
# verifier so this module does not import the kernel's recovery module (no import cycle).
KeyInventory = Callable[["Session", "KeyRing"], tuple[list[str], str, str]]


@dataclass(frozen=True, slots=True)
class SecurityChainSnapshot:
    """Everything the verifier needs from one identity-scope read of the security chain."""

    result: ChainVerificationResult
    head_seq: int
    head_hmac: str | None
    head_occurred_at: datetime | None
    recovered_latest: datetime | None
    mfa_rows: Sequence[dict[str, Any]]
    schema_revision: str | None
    required_keys: list[str]
    current_key: str
    head_key: str


def security_head_seq(*, request_id: str) -> int:
    """The security chain head before a verifier run appends anything (review P6-R7)."""
    with identity_session(request_id=request_id) as session:
        return int(session.execute(SECURITY_HEAD).scalar_one())


def security_chain_snapshot(
    *, keyring: KeyRing, request_id: str, head_before_run: int, inventory: KeyInventory
) -> SecurityChainSnapshot:
    """Verify the chain and read its head, the recovered freshness, the MFA envelopes, the schema
    revision and the security-key inventory in one identity-scope transaction."""
    with identity_session(request_id=request_id) as session:
        result = verify_security_event_chain(session, keyring=keyring)
        head = session.execute(
            select(security_event.c.chain_seq, security_event.c.hmac, security_event.c.occurred_at)
            .order_by(security_event.c.chain_seq.desc())
            .limit(1)
        ).one_or_none()
        # Recovered freshness stops at the head that existed before the verifier ran: the
        # PLATFORM_SCOPE_USED event this run appended is not recovered data (P6-R7).
        recovered_latest = session.execute(
            select(func.max(security_event.c.occurred_at)).where(
                security_event.c.chain_seq <= head_before_run
            )
        ).scalar_one_or_none()
        mfa_rows = [
            dict(mapping)
            for mapping in session.execute(
                select(
                    user_mfa_factor.c.id,
                    user_mfa_factor.c.secret_ciphertext,
                    user_mfa_factor.c.secret_key_id,
                    user_mfa_factor.c.disabled_at,
                )
            ).mappings()
        ]
        try:
            schema_revision: str | None = str(session.execute(ALEMBIC_VERSION).scalar_one())
        except Exception:  # noqa: BLE001 - no version table: an unmigrated database
            schema_revision = None
        required_keys, current_key, head_key = inventory(session, keyring)
    return SecurityChainSnapshot(
        result=result,
        head_seq=0 if head is None else int(head.chain_seq),
        head_hmac=None if head is None else str(head.hmac),
        head_occurred_at=None if head is None else head.occurred_at,
        recovered_latest=recovered_latest,
        mfa_rows=mfa_rows,
        schema_revision=schema_revision,
        required_keys=required_keys,
        current_key=current_key,
        head_key=head_key,
    )


def security_anchor(chain_seq: int, *, request_id: str) -> str | None:
    """The HMAC the security chain holds at ``chain_seq``, or None when the row is absent."""
    with identity_session(request_id=request_id) as session:
        found = session.execute(
            select(security_event.c.hmac).where(security_event.c.chain_seq == chain_seq)
        ).scalar_one_or_none()
    return None if found is None else str(found)
