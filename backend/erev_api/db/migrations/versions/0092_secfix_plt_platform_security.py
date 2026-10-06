"""Lane SECFIX-PLT, the platform security package (security review of 2026-09-29; supervisor
rulings R-48 and R-50 (b); number assigned in the package).

04 ids amended (rev 1.108):

- E-79 ``security_event_kind`` gains ``MFA_ENROLMENT_STARTED`` and ``RECOVERY_CODES_REGENERATED``
  (R-50 (b)) — issuing a TOTP seed and replacing the recovery-code batch are security-relevant
  writes that the log did not show (04 T-PLT-04, T-PLT-05; 05 SAR-26). Appended in this order.
- T-PLT-03 ``identity_provider`` gains ``email_domains text[] NOT NULL DEFAULT '{}'`` (R-48 (d);
  REQ-PLT-006): the email domains a provider is authoritative for; an empty list accepts no
  sign-in, so a provider row of before this revision signs nobody in until its operator names
  its domains (D-99: no compatibility work before a first release).
- T-PLT-02 ``app_user`` gains ``identity_provider_subject text`` — the subject under which the
  provider names the identity, recorded at its first sign-in — with
  ``ck_app_user__idp_subject`` (a subject belongs to a provider) and the unique index
  ``ux_app_user__idp_subject`` (one identity per provider subject); §14.2 DB-13: ``erev_app``
  may update the column, which the first sign-in writes and ``user.anonymise`` clears.

No function or trigger is added, so the erev function count is unchanged. The downgrade revokes
the grant, drops the index, the check and the two columns, and rewrites the enum type without the
labels through ``remove_enum_value`` (DG-MIG-06), which fails while a row still carries one.

Revision 0092 on 0087: main's head at the merge of main 87796c55 (the package: "down_revision =
the head you find after merging main"; supervisor ruling R-68 (e): a revision keeps its number
and follows main's head, so the chain is in merge order — 0095, 0084, 0087, then this one). A
revision imports nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): the role name is a
literal.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0092"
down_revision = "0087"
branch_labels = None
depends_on = None

# The application role of 04 §1.5 (``erev_api.db.session.APP_ROLE``), spelt as a literal.
APP_ROLE: Final = "erev_app"

SECURITY_EVENT_KIND: Final = "security_event_kind"
# 04 E-79 rev 1.108, in the order the type lists them.
SECURITY_EVENT_KINDS: Final = ("MFA_ENROLMENT_STARTED", "RECOVERY_CODES_REGENERATED")

PROVIDER: Final = "identity_provider"
USER: Final = "app_user"
SUBJECT: Final = "identity_provider_subject"
SUBJECT_CHECK: Final = "ck_app_user__idp_subject"
SUBJECT_INDEX: Final = "ux_app_user__idp_subject"


def upgrade() -> None:
    for value in SECURITY_EVENT_KINDS:
        ops.add_enum_value(SECURITY_EVENT_KIND, value)
    ops.execute(
        f"ALTER TABLE erev.{PROVIDER} ADD COLUMN email_domains text[] NOT NULL DEFAULT '{{}}'"
    )
    ops.execute(f"ALTER TABLE erev.{USER} ADD COLUMN {SUBJECT} text NULL")
    ops.execute(
        f"ALTER TABLE erev.{USER} ADD CONSTRAINT {SUBJECT_CHECK} "
        f"CHECK ({SUBJECT} IS NULL OR identity_provider_id IS NOT NULL)"
    )
    ops.create_indexes(
        USER,
        [(SUBJECT_INDEX, ["identity_provider_id", SUBJECT], f"{SUBJECT} IS NOT NULL")],
        unique=True,
        tenant_leading=False,
    )
    ops.execute(f"GRANT UPDATE ({SUBJECT}) ON TABLE erev.{USER} TO {APP_ROLE}")


def downgrade() -> None:
    ops.execute(f"REVOKE UPDATE ({SUBJECT}) ON TABLE erev.{USER} FROM {APP_ROLE}")
    ops.execute(f"DROP INDEX erev.{SUBJECT_INDEX}")
    ops.execute(f"ALTER TABLE erev.{USER} DROP CONSTRAINT {SUBJECT_CHECK}")
    ops.execute(f"ALTER TABLE erev.{USER} DROP COLUMN {SUBJECT}")
    ops.execute(f"ALTER TABLE erev.{PROVIDER} DROP COLUMN email_domains")
    for value in reversed(SECURITY_EVENT_KINDS):
        ops.remove_enum_value(SECURITY_EVENT_KIND, value)
