"""The ledger-chain verifier the recovery verifier calls, registered by the domain at import
(DG-ARC-01: a kernel module never imports the domain; the domain fills a registry the kernel
defines, the pattern of ``erev_api.jobs.registry``). ``erev_api.domain.journals.subledger`` its
registers
``verify_ledger_chain``; the CLI ``verify`` command and the PG tests import that module first."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# (session, book_code=...) -> the domain's LedgerChainVerification (result, seals checked, head).
LedgerChainVerifier = Callable[..., Any]

_VERIFIER: list[LedgerChainVerifier] = []


def register_ledger_chain_verifier(verifier: LedgerChainVerifier) -> LedgerChainVerifier:
    """Register (or replace) the domain's ledger-chain verifier; returns it for decorator use."""
    _VERIFIER[:] = [verifier]
    return verifier


def ledger_chain_verifier() -> LedgerChainVerifier:
    """The registered verifier; a clear error when the domain module was never imported."""
    if not _VERIFIER:
        raise LookupError(
            "no ledger-chain verifier is registered: import erev_api.domain.journals.subledger "
            "before verifying (DG-ARC-01 registry)"
        )
    return _VERIFIER[0]


def verify_ledger_chain(session: Session, *, book_code: str) -> Any:
    """Call the registered verifier (the domain's ``verify_ledger_chain``)."""
    return ledger_chain_verifier()(session, book_code=book_code)
