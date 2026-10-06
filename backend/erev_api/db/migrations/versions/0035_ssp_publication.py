"""BUILD_SPEC item RFD-13: SSP publication.

04 ids created: DB-04 for T-REF-29 ``ssp_book_version`` among APPROVED versions and DB-05 for
T-REF-28 ``ssp_book`` (04 §14.1), as triggers on the RFD-12 tables.

- ``tg_ssp_book_version__config_version`` over the new function
  ``erev.tg_ssp_book_version__config_version()`` replaces the trigger over the shared
  ``erev.tg_config_version('ssp_book_id')``. It keeps every rule of the shared function (frozen
  after DRAFT and TESTED, E-12 pairs, APPROVED only with an APPROVED approval request, a content
  hash outside DRAFT, DELETE of DRAFT rows only, DRAFT inserts outside provisioning) and adds the
  SSP rules. ``effective_to_date`` of an APPROVED version may be set once, from none, by
  supersession (PRD BR-SSP-02). A version of an ``EFFECTIVE_DATE`` book needs
  ``effective_from_date`` outside DRAFT (T-REF-29). APPROVED versions of such a book never overlap
  on ``[effective_from_date, effective_to_date]``, inclusive, with ``EREV-CFG-001``; the shared
  function compares PUBLISHED ``effective_from``/``effective_to`` ranges, which an SSP version
  never has (L2-1-Q-32).
- ``tg_ssp_book__scope_frozen`` over the new function ``erev.tg_ssp_book__scope_frozen()``: the
  scope columns ``entity_id``, ``currency``, ``channel`` and ``segment``, and ``resolution_mode``,
  change only while no version of the book is APPROVED (DB-05, ``EREV-REF-001``; L2-1-Q-33).

The function count becomes 41.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

# DB-04 for T-REF-29 (see the module docstring). The column and pair lists equal
# ``migration_ops.CONFIG_MUTABLE_COLUMNS`` and ``CONFIG_STATUS_PAIRS`` at revision 0035.
SSP_VERSION_CONFIG_BODY = """
DECLARE
  old_row jsonb;
  new_row jsonb;
  changed text;
  approved boolean := false;
  book_mode text;
  overlapping text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'DRAFT' THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-002: a %s version of %I.%I cannot be deleted',
                         OLD.status, TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'INSERT' AND NEW.status <> 'DRAFT'
     AND current_setting('app.platform_scope', true) IS DISTINCT FROM 'provisioning' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-CFG-002: a version of %I.%I is inserted as DRAFT, not %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.status);
  END IF;
  IF NEW.status <> 'DRAFT' AND NEW.content_sha256 IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-CFG-002: content_sha256 of %I.%I is required outside DRAFT',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.status::text <> ALL (ARRAY['DRAFT', 'TESTED']::text[]) THEN
      old_row := to_jsonb(OLD);
      new_row := to_jsonb(NEW);
      SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
        FROM jsonb_each(new_row) n
       WHERE n.key <> ALL (ARRAY['approval_request_id', 'effective_to', 'published_at',
                                 'published_by', 'row_version', 'status', 'updated_at',
                                 'updated_by', 'updated_by_kind']::text[])
         AND n.value IS DISTINCT FROM old_row -> n.key
         AND NOT (n.key = 'effective_to_date' AND OLD.status = 'APPROVED'
                  AND NEW.status = 'APPROVED' AND OLD.effective_to_date IS NULL);
      IF changed IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
          MESSAGE = format('EREV-CFG-002: columns %s of %I.%I cannot change in status %s',
                           changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
      END IF;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status
       AND (OLD.status::text || '>' || NEW.status::text)
           <> ALL (ARRAY['APPROVED>PUBLISHED', 'DRAFT>TESTED', 'PUBLISHED>SUPERSEDED',
                         'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED',
                         'SUBMITTED>WITHDRAWN', 'TESTED>SUBMITTED', 'WITHDRAWN>DRAFT']::text[]) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-002: status of %I.%I cannot change from %s to %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
    END IF;
    IF NEW.status = 'APPROVED' AND OLD.status <> 'APPROVED' THEN
      IF NEW.approval_request_id IS NOT NULL THEN
        SELECT EXISTS (
          SELECT 1 FROM erev.approval_request r
           WHERE r.tenant_id = NEW.tenant_id AND r.id = NEW.approval_request_id
             AND r.status = 'APPROVED'
        ) INTO approved;
      END IF;
      IF NOT approved THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
          MESSAGE = format('EREV-CFG-002: a version of %I.%I needs an APPROVED approval request',
                           TG_TABLE_SCHEMA, TG_TABLE_NAME);
      END IF;
    END IF;
  END IF;
  IF NEW.status <> 'DRAFT' THEN
    SELECT b.resolution_mode INTO book_mode
      FROM erev.ssp_book b
     WHERE b.tenant_id = NEW.tenant_id AND b.id = NEW.ssp_book_id
       FOR UPDATE;
    IF coalesce(book_mode, 'EFFECTIVE_DATE') = 'EFFECTIVE_DATE' THEN
      IF NEW.effective_from_date IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
          MESSAGE = format('EREV-CFG-002: a %s version of %I.%I needs effective_from_date, '
                           'because its book resolves by effective date',
                           NEW.status, TG_TABLE_SCHEMA, TG_TABLE_NAME);
      END IF;
      IF NEW.status = 'APPROVED' THEN
        SELECT string_agg(v.version_no::text, ', ' ORDER BY v.version_no) INTO overlapping
          FROM erev.ssp_book_version v
         WHERE v.tenant_id = NEW.tenant_id AND v.ssp_book_id = NEW.ssp_book_id
           AND v.id <> NEW.id AND v.status = 'APPROVED'
           AND daterange(v.effective_from_date, v.effective_to_date, '[]')
               && daterange(NEW.effective_from_date, NEW.effective_to_date, '[]');
        IF overlapping IS NOT NULL THEN
          RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = format('EREV-CFG-001: the effective dates of version %s of %I.%I overlap '
                             'APPROVED version %s of the same book',
                             NEW.version_no, TG_TABLE_SCHEMA, TG_TABLE_NAME, overlapping);
        END IF;
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END
"""

# DB-05 for T-REF-28: the scope and resolution mode of a book with an APPROVED version are frozen.
SSP_BOOK_SCOPE_FROZEN_BODY = """
BEGIN
  IF (NEW.entity_id, NEW.currency, NEW.channel, NEW.segment, NEW.resolution_mode)
     IS NOT DISTINCT FROM
     (OLD.entity_id, OLD.currency, OLD.channel, OLD.segment, OLD.resolution_mode) THEN
    RETURN NEW;
  END IF;
  IF EXISTS (
    SELECT 1 FROM erev.ssp_book_version v
     WHERE v.tenant_id = OLD.tenant_id AND v.ssp_book_id = OLD.id
       AND v.status::text = ANY (ARRAY['APPROVED', 'SUPERSEDED']::text[])
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: the scope of SSP book %s of %I.%I is frozen: a version is '
                       'approved', OLD.code, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """Replace the DB-04 trigger of ``ssp_book_version``; add the DB-05 trigger of ``ssp_book``."""
    ops.execute("DROP TRIGGER tg_ssp_book_version__config_version ON erev.ssp_book_version")
    ops.create_trigger(
        "ssp_book_version",
        "config_version",
        SSP_VERSION_CONFIG_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OR DELETE",
    )
    ops.create_trigger(
        "ssp_book", "scope_frozen", SSP_BOOK_SCOPE_FROZEN_BODY, timing="BEFORE", events="UPDATE"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order, and restore the RFD-12 trigger."""
    ops.execute("DROP TRIGGER tg_ssp_book__scope_frozen ON erev.ssp_book")
    ops.execute("DROP FUNCTION erev.tg_ssp_book__scope_frozen()")
    ops.execute("DROP TRIGGER tg_ssp_book_version__config_version ON erev.ssp_book_version")
    ops.execute("DROP FUNCTION erev.tg_ssp_book_version__config_version()")
    ops.add_config_version_trigger("ssp_book_version", scope_columns=["ssp_book_id"])
