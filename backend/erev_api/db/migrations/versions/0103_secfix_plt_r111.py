"""Lane SECFIX-PLT, the slice of the independent review of the platform security merge (supervisor
ruling R-111; the revision number and the table id T-PLT-49 assigned by the supervisor, register
index 98).

04 ids created or amended (rev 1.189; §18 rule 16):

- T-PLT-49 ``file_upload`` (R-111 (5), item FILE-DEDUPE-READER-1): one row per file and uploader
  with the uploader's own file name and time — ``PRIMARY KEY (tenant_id, file_object_id,
  uploaded_by, uploaded_by_kind)``, no surrogate id (NC-04: the database generates none), the key
  ``fk_file_upload__file_object`` and ``ck_file_upload__uploader`` (a member or an API client:
  ``POST /files`` is the only writer). IM-A (DB-01: ``erev_app`` holds SELECT and INSERT), RLS-T,
  not partitioned. Identical content of one purpose is one ``file_object`` row; this table lets an
  uploader of the same bytes read and use the upload and be shown their own facts, where the
  answer of ``POST /files`` was the first uploader's row.
- E-79 ``security_event_kind`` gains ``MFA_CHALLENGE_PASSED`` and ``MFA_PENDING_DENIED`` (R-111
  (6)), appended in this order: a passed second-factor challenge, and a request refused outside
  an open workspace because its session still owes the second-factor step.
- T-PLT-21 ``approval_delegation`` gains ``ck_approval_delegation__ends`` (R-111 (4); PRD
  BR-PLT-07): ``valid_to <= created_at + interval '90 days'`` — a delegation ends no later than 90
  days after the command that creates it; the check of revision 0013 lets the 90 days run from a
  ``valid_from`` of any date.
- §14.1 DB-20 ``tg_app_user__identity_provider`` ``BEFORE UPDATE OF identity_provider_id,
  identity_provider_subject … FOR EACH ROW`` (R-111 (7)): ``identity_provider_id`` changes only
  from NULL; ``identity_provider_subject`` changes only from NULL, or to NULL in the erased form
  of DB-19 (``user.anonymise``: the erased email and status ``DISABLED`` in the same UPDATE).
  ``erev_app`` keeps the UPDATE grant of both columns (revisions 0004 and 0092: the invitation
  and the first sign-in write them); the guard is what stops a defect running as the application
  from moving an identity to another provider or rebinding its subject. Refused as
  ``EREV-IMM-001`` (409 ``immutable-record``); the message names the row and no value.

Rows written before this revision (DG-MIG-13; D-99 (3); supervisor ruling R-119 (f)): nothing is
backfilled — a revision runs as ``erev_owner`` without a tenant context and sees no row of a
tenant table under the forced row-level security, and no revision lifts FORCE to read one (the
0084 and 0101 precedents: 0084 leaves the rows of before it as they are, 0101's link table starts
empty beside the events already written). T-PLT-49 starts empty and records every upload from
this revision on, the first uploader's included. For a file stored before it the first uploader
is the stored row's ``created_by``, which the read rule of T-PLT-29 keeps; a second uploader of
such a file has no row here, and reads the file again by uploading it again. The key holds one
row per file and uploader and IM-A forbids its change, so a member who uploads the same bytes
again under another name keeps the name and time of their first upload. The
delegation check is added ``NOT VALID`` — enforced for every row written from here on — and
validated in the same transaction: on a database without a longer delegation it ends validated;
on a pre-release database that holds one the validation's ``check_violation`` is caught, a NOTICE
names the revision and the constraint stays ``NOT VALID`` (the 0084 precedent). No row is changed.

One erev function is added (``tests/pg/test_migrations.py`` counts it): SECURITY INVOKER with
``search_path`` pinned and EXECUTE granted to ``erev_app`` by ``create_trigger`` (NC-18; DB-14
(h)); IM-A attaches the existing ``tg_forbid_mutation``. The downgrade drops the trigger and its
function, the check and the table, and rewrites the enum type without the two labels through
``remove_enum_value`` (DG-MIG-06), which fails while a row still carries one.

Revision 0103 on 0094: main's head at the lane's merge of main 4a3a6a4c, after 0112 at its merge
of 9b881b70, 0086 at its merge of 965ed2bd, 0113 at its merge of afab0c2a and 0099 at its merge of
20531d3b (supervisor ruling R-68 (e): a revision keeps its number and follows main's head at its
merge). A revision imports nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): every body
is a literal.
"""

from __future__ import annotations

from typing import Final

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0103"
down_revision = "0094"
branch_labels = None
depends_on = None

UPLOADS: Final = "file_upload"

SECURITY_EVENT_KIND: Final = "security_event_kind"
# 04 E-79 rev 1.189, in the order the type lists them.
SECURITY_EVENT_KINDS: Final = ("MFA_CHALLENGE_PASSED", "MFA_PENDING_DENIED")

DELEGATION: Final = "approval_delegation"
ENDS_CHECK: Final = "ck_approval_delegation__ends"
# A constant statement (DG-MIG-13): the validation scans every physical row, whatever the forced
# row-level security hides from an EXISTS on the owner connection. A delegation of before this
# revision that ends later than 90 days after its creation keeps the constraint NOT VALID —
# enforced for every new row — and the revision continues; nothing is rewritten.
VALIDATE_ENDS_CHECK: Final = """
DO $$
BEGIN
  ALTER TABLE erev.approval_delegation VALIDATE CONSTRAINT ck_approval_delegation__ends;
EXCEPTION
  WHEN check_violation THEN
    RAISE NOTICE 'EREV-MIG-0103: approval_delegation holds rows written before revision 0103 that '
                 'end later than 90 days after their creation; ck_approval_delegation__ends stays '
                 'NOT VALID (it is enforced for every row written from this revision on)';
END
$$;
"""

USER: Final = "app_user"
GUARD: Final = "identity_provider"
GUARD_COLUMNS: Final = "identity_provider_id, identity_provider_subject"
# DB-20 (04 §14.1 rev 1.189). ``IS NOT TRUE`` so that a predicate that does not evaluate to true —
# NULL included — refuses; the erased form is DB-19's (revision 0073), verbatim.
GUARD_BODY: Final = """
BEGIN
  IF OLD.identity_provider_id IS NOT NULL
     AND NEW.identity_provider_id IS DISTINCT FROM OLD.identity_provider_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-IMM-001: identity_provider_id of %I.%I row %s is set once',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id);
  END IF;
  IF OLD.identity_provider_subject IS NOT NULL
     AND NEW.identity_provider_subject IS DISTINCT FROM OLD.identity_provider_subject
     AND (NEW.identity_provider_subject IS NULL
          AND NEW.email = 'erased+' || NEW.id::text || '@invalid.erev'
          AND NEW.status = 'DISABLED') IS NOT TRUE THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-IMM-001: identity_provider_subject of %I.%I row %s is written once '
                       'and cleared only in the erased form of user.anonymise',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """T-PLT-49 through the §6.5 helpers, then the enum labels, the check and DB-20."""
    ops.create_tenant_table(
        UPLOADS,
        sa.Column("file_object_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_kind", ops.NamedType("erev.principal_kind"), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        include_id=False,
        primary_key=["tenant_id", "file_object_id", "uploaded_by", "uploaded_by_kind"],
        checks=[(f"ck_{UPLOADS}__uploader", "uploaded_by_kind IN ('USER', 'API_CLIENT')")],
    )
    ops.add_tenant_fk(UPLOADS, "file_object_id", "file_object")
    ops.apply_class(UPLOADS, "IM-A")
    ops.enable_rls(UPLOADS, "RLS-T")
    for value in SECURITY_EVENT_KINDS:
        ops.add_enum_value(SECURITY_EVENT_KIND, value)
    ops.execute(
        f"ALTER TABLE erev.{DELEGATION} ADD CONSTRAINT {ENDS_CHECK} "
        "CHECK (valid_to <= created_at + interval '90 days') NOT VALID"
    )
    ops.execute(VALIDATE_ENDS_CHECK)
    ops.create_trigger(
        USER, GUARD, GUARD_BODY, timing="BEFORE", events=f"UPDATE OF {GUARD_COLUMNS}"
    )


def downgrade() -> None:
    """Remove exactly what ``upgrade`` created, in reverse order (DG-MIG-04)."""
    ops.execute(f"DROP TRIGGER tg_{USER}__{GUARD} ON erev.{USER}")
    ops.execute(f"DROP FUNCTION erev.tg_{USER}__{GUARD}()")
    ops.execute(f"ALTER TABLE erev.{DELEGATION} DROP CONSTRAINT {ENDS_CHECK}")
    for value in reversed(SECURITY_EVENT_KINDS):
        ops.remove_enum_value(SECURITY_EVENT_KIND, value)
    ops.drop_tenant_table(UPLOADS)
