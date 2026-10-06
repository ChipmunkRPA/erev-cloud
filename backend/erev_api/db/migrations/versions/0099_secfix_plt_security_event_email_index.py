"""Lane SECFIX-PLT, the lead's finding 5 (security review of 2026-09-29; supervisor ruling R-48
(e); number assigned by the supervisor, register index 60).

04 id amended (rev 1.151): T-PLT-06 ``security_event`` gains the index
``ix_security_event__email_chain (email_sha256, chain_seq) WHERE email_sha256 IS NOT NULL``. The
failed sign-ins of an email without an account are counted from its events (REQ-PLT-004), so that
its lockout answers as an account's does; the index makes that count one probe.

No table, column, type, grant, function or trigger changes, so the erev function count is
unchanged. The downgrade drops the index.

Revision 0099 on 0105: written on 0092 and re-pointed to main's head at each merge of main —
to 0093 at 094f7174, to 0098 at b4e293c5, to 0105 by the supervisor at the lane's merge
(supervisor ruling R-68 (e): a revision keeps its number and follows main's head at its merge).
A revision imports nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0099"
down_revision = "0105"
branch_labels = None
depends_on = None

EVENTS: Final = "security_event"
EMAIL_INDEX: Final = "ix_security_event__email_chain"


def upgrade() -> None:
    ops.create_indexes(
        EVENTS,
        [(EMAIL_INDEX, ["email_sha256", "chain_seq"], "email_sha256 IS NOT NULL")],
        unique=False,
        tenant_leading=False,
    )


def downgrade() -> None:
    ops.execute(f"DROP INDEX erev.{EMAIL_INDEX}")
