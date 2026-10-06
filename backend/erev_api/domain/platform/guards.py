"""The production guard of sandbox tenants (BUILD_SPEC SNP-4; 05 §10 SBX-08 rev 1.64; build-spec
header XR-08; 03 REQ-PLT-022; CTL-043; PRD ERR-17).

A sandbox never posts, exports or calls out, and it destroys nothing it shares with the workspace
it was copied from. Every command that would — the journal export, the creation and activation of
an inbound connection with its sync and webhook intake, the activation of an outbound adapter
other than ``CSV_GL``, the creation and activation of a webhook endpoint — calls
:func:`ensure_production` before it reads or writes anything else of its own; the shred of a
file, the request for it and the effect of its approval (rev 1.164, item FILE-SHRED-SCOPE-1)
call it once they hold the file's row, for a file whose storage key is not the sandbox's own
(``privacy.refuse_shared_in_sandbox``: what a sandbox stored itself is its own). In a sandbox
the attempt is written as an audit event with outcome ``DENIED`` in a transaction of its own (the
command's transaction rolls back; the evidence does not) and the command answers 403
``sandbox-restricted``; in a production tenant the call does nothing.

The database backs the guard for the writes it can see (04 DB-15: ``tg_journal_batch__sandbox``,
``tg_integration_connection__sandbox``, ``tg_webhook_endpoint__sandbox``); the guard is what audits
the attempt and what refuses before a row is touched. ``tests/architecture/
test_ensure_production.py`` holds the list of restricted commands and fails when one of them
stops calling the guard, or calls it more than once.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_api.audit import writer as audit_writer
from erev_api.enums import AuditOutcome, TenantKind
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["SANDBOX_RESTRICTED", "SLUG", "ensure_production"]

SLUG: Final = "sandbox-restricted"
# PRD ERR-17: the catalogue copy of the slug, the reason line of SCREENS_B SB-R-08.
SANDBOX_RESTRICTED: Final = "Sandbox workspaces cannot post or export journals."


def ensure_production(
    uow: UnitOfWork,
    *,
    action: str,
    object_type: str,
    object_id: UUID | None,
    detail: Mapping[str, Any] | None = None,
    message: str = SANDBOX_RESTRICTED,
) -> None:
    """Pass in a production tenant; in a sandbox, audit the attempt ``DENIED`` in its own
    transaction and refuse 403 ``sandbox-restricted`` with ``message`` (05 SBX-08).

    ``action``, ``object_type`` and ``object_id`` are those of the command's own success event, so
    the denial reads as the same command refused; ``detail`` carries what was asked for and gains
    ``problem``. Nothing of the command's transaction is written: the caller raises out of it."""
    if uow.ctx.tenant_kind is not TenantKind.SANDBOX:
        return
    audit_writer.record_now(
        uow.ctx,
        action=action,
        object_type=object_type,
        object_id=object_id,
        outcome=AuditOutcome.DENIED,
        detail={**dict(detail or {}), "problem": SLUG},
        keyring=uow.keyring,
    )
    raise Problem(SLUG, message)
