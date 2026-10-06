"""D-98 candidate 20 (lane F-ADM; 04 rev 1.38): E-79 ``security_event_kind``
gains ``INVITATION_LOOKUP_FAILED``.

Revision 0058 on 0057, assigned by the team-lead at the merge preparation of 2026-09-20 (04 §18
rule 9; sequence P5 0055 → F-LMG 0056 → P4 0057 → F-ADM 0058); the ``down_revision`` was provisional
(0054, then 0055) until P4's 0057 reached main at 746ff16c and is final here.

A ``POST /session/invitations/lookup`` or ``POST /session/accept-invitation`` whose token is
malformed, unknown, expired or already used writes a ``security_event`` of this kind (T-PLT-07
"Invitation lookup failures"). Enum value only; no table, column, function or trigger changes. The
downgrade rewrites the type without the label through ``remove_enum_value`` (DG-MIG-06), which
fails while a row still carries it.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

ENUM = "security_event_kind"
VALUE = "INVITATION_LOOKUP_FAILED"


def upgrade() -> None:
    ops.add_enum_value(ENUM, VALUE)


def downgrade() -> None:
    ops.remove_enum_value(ENUM, VALUE)
