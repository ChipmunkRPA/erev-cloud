"""Security event chain verification (05 SCH-02, SLO-06, RB-08; 04 T-PLT-06; dev-guide
DG-KRN-AUD-07; REQ-PLT-019; BUILD_SPEC PLF-23).

The global ``security_event`` chain is read through ``identity_session``, which DG-KRN-DB-02 keeps
in ``auth/**``. T-PLT-23 holds tenant rows only, so the result of the global chain is recorded as
the log line ``security_chain.verified``, at level error when the chain fails, which the RB-08
page follows (SPEC-Q-188).
"""

from __future__ import annotations

from typing import Final

from erev_api.audit.verify import ChainVerificationResult, verify_security_event_chain
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import identity_session
from erev_api.enums import ControlResult
from erev_api.logging import get_logger, register_logger_fields

_LOGGER: Final = "erev_api.auth.security_chain"

register_logger_fields(_LOGGER, ("result", "events_checked", "first_failure_seq", "last_chain_seq"))


def verify_security_chain(keyring: KeyRing, *, request_id: str) -> ChainVerificationResult:
    """Verify the whole global chain, log the result and return it."""
    with identity_session(request_id=request_id) as session:
        result = verify_security_event_chain(session, keyring=keyring)
    fields = {
        "result": result.result.value,
        "events_checked": result.events_checked,
        "first_failure_seq": result.first_failure_seq,
        "last_chain_seq": result.to_chain_seq,
    }
    logger = get_logger(_LOGGER)
    if result.result is ControlResult.PASS:
        logger.info("security_chain.verified", **fields)
    else:
        logger.error("security_chain.verified", **fields)
    return result
