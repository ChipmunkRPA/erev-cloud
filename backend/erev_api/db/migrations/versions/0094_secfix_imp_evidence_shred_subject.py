"""Lane SECFIX-IMP, security finding SC-6 (supervisor rulings R-49 (a) and R-86 (b), (c); 04 rev
1.142): E-08 ``approval_subject_type`` gains ``EVIDENCE_SHRED`` — the request to shred a file that
a record holds as its evidence (the source of a committed import, the source file of a signed
reconciliation, the legacy database of a migration, an SSP study, the attachment of a manual
adjustment), made by the privacy-side administrator (``POST /files/{id}/request-shred``) and
decided by a Controller; on approval the SYSTEM principal shreds on behalf of the requester (05
rev 1.81 PRV-07 b; PRD §2.5 rev 1.71).

Revision 0094 assigned by the supervisor (register index 51); ``down_revision`` is the head of
main when the lane brought this part onto it (ruling R-68 (e): the chain follows merge order;
re-pointed at the merge if the head has moved). Enum value only: no table, column, function or
trigger changes. The downgrade rewrites the type without the label through
``remove_enum_value`` (DG-MIG-06), which fails while a row still carries it.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0094"
down_revision = "0111"
branch_labels = None
depends_on = None

ENUM = "approval_subject_type"
VALUE = "EVIDENCE_SHRED"


def upgrade() -> None:
    ops.add_enum_value(ENUM, VALUE)


def downgrade() -> None:
    ops.remove_enum_value(ENUM, VALUE)
