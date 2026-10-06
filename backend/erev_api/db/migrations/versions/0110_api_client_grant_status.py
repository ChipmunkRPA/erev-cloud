"""Lane SECFIX-APR, supervisor ruling R-38 (iii): an API client's scopes are an access grant
(number assigned by the supervisor, register index 77).

04 ids amended (rev 1.168): E-103 ``api_client_status`` gains ``PENDING_APPROVAL`` and
``REJECTED``, appended in this order. The T-PLT-15 row of an API client is written
``PENDING_APPROVAL`` when the client is requested, becomes ``ACTIVE`` when its ``ROLE_ASSIGNMENT``
request is approved and ``REJECTED`` when that request is rejected, withdrawn or voided (03
REQ-PLT-033 rev 1.83). The column default stays ``ACTIVE``: the creating command names the status.

No table, column, function, trigger or grant changes, so the erev function count is unchanged.
The downgrade rewrites the type without the two labels through ``remove_enum_value`` (DG-MIG-06),
which fails while a row still carries one — the rule of revision 0092: it is walked from a head
without data.

Revision 0110 on 0122: the integration branch's head at the supervisor's merge. It was written
on 0104 and stood on 0117, main's head at the lane's merge of main (supervisor ruling R-68 (e):
a revision keeps its number and follows the head, so the chain is in merge order).
``ALTER TYPE … ADD
VALUE`` stands in a revision of its own. A revision imports nothing of ``erev_api`` beyond the DDL
helpers (DG-MIG-12).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0110"
down_revision = "0122"
branch_labels = None
depends_on = None

API_CLIENT_STATUS: Final = "api_client_status"
# 04 E-103 rev 1.168, in the order the type lists them.
GRANT_STATUSES: Final = ("PENDING_APPROVAL", "REJECTED")


def upgrade() -> None:
    for value in GRANT_STATUSES:
        ops.add_enum_value(API_CLIENT_STATUS, value)


def downgrade() -> None:
    for value in reversed(GRANT_STATUSES):
        ops.remove_enum_value(API_CLIENT_STATUS, value)
