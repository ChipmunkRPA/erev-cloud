"""Scenario-only input publication without a fabricated production approval (FCS-2).

Use the DB-04 freeze and overlap checks with the scenario lifecycle DRAFT -> PUBLISHED ->
SUPERSEDED. Production configuration keeps the shared approval-governed lifecycle unchanged.
"""

from erev_api.db import migration_ops as ops

revision = "0179"
down_revision = "0178"
branch_labels = None
depends_on = None

BODY = """
DECLARE
  old_row jsonb;
  new_row jsonb;
  changed text;
  approved boolean := false;
  overlapping boolean;
  scope_predicate text := '';
  i integer;
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
  IF NEW.approval_request_id IS NOT NULL THEN
    RAISE EXCEPTION 'EREV-CFG-002: forecast inputs do not carry a production approval request';
  END IF;
  IF NEW.status = 'PUBLISHED' AND (NEW.published_at IS NULL OR NEW.published_by IS NULL) THEN
    RAISE EXCEPTION 'EREV-CFG-002: forecast publication requires its actor and timestamp';
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
       WHERE n.key <> ALL (ARRAY['status', 'updated_at', 'updated_by', 'updated_by_kind', 'row_version']::text[])
         AND n.value IS DISTINCT FROM old_row -> n.key;
      IF changed IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
          MESSAGE = format('EREV-CFG-002: columns %s of %I.%I cannot change in status %s',
                           changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
      END IF;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status
       AND (OLD.status::text || '>' || NEW.status::text)
           <> ALL (ARRAY['DRAFT>PUBLISHED', 'PUBLISHED>SUPERSEDED']::text[]) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-002: status of %I.%I cannot change from %s to %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
    END IF;
    IF NEW.status = 'APPROVED' AND OLD.status <> 'APPROVED' THEN
      IF NEW.approval_request_id IS NOT NULL
         AND to_regclass('erev.approval_request') IS NOT NULL THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM erev.approval_request r '
                'WHERE r.tenant_id = $1 AND r.id = $2 AND r.status = ''APPROVED'')'
          INTO approved USING NEW.tenant_id, NEW.approval_request_id;
      END IF;
      IF NOT approved THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
          MESSAGE = format('EREV-CFG-002: a version of %I.%I needs an APPROVED approval request',
                           TG_TABLE_SCHEMA, TG_TABLE_NAME);
      END IF;
    END IF;
  END IF;
  IF NEW.status = 'PUBLISHED' THEN
    FOR i IN 0 .. TG_NARGS - 1 LOOP
      scope_predicate := scope_predicate
        || format(' AND (to_jsonb(r) -> %L) IS NOT DISTINCT FROM ($4 -> %L)',
                  TG_ARGV[i], TG_ARGV[i]);
    END LOOP;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I r WHERE r.tenant_id = $1 AND r.id <> $2 '
                   'AND r.status = ''PUBLISHED'' '
                   'AND tstzrange(r.effective_from, r.effective_to) && $3%s)',
                   TG_TABLE_SCHEMA, TG_TABLE_NAME, scope_predicate)
      INTO overlapping
      USING NEW.tenant_id, NEW.id, tstzrange(NEW.effective_from, NEW.effective_to), to_jsonb(NEW);
    IF overlapping THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-001: the effective range of %I.%I overlaps a PUBLISHED version',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def upgrade() -> None:
    ops.execute("DROP TRIGGER tg_forecast_event_set__config_version ON erev.forecast_event_set")
    ops.create_trigger(
        "forecast_event_set",
        "config_version",
        BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OR DELETE",
    )
    ops.execute("DROP TRIGGER tg_forecast_event_set__config_version ON erev.forecast_event_set")
    ops.execute(
        "CREATE TRIGGER tg_forecast_event_set__config_version BEFORE INSERT OR UPDATE OR DELETE "
        "ON erev.forecast_event_set FOR EACH ROW "
        "EXECUTE FUNCTION erev.tg_forecast_event_set__config_version('code')"
    )
    ops.execute(
        "CREATE UNIQUE INDEX ux_forecast_event_set__published ON erev.forecast_event_set "
        "(tenant_id, code) WHERE status = 'PUBLISHED'"
    )


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.forecast_event_set WHERE status <> 'DRAFT') THEN
        RAISE EXCEPTION 'Published forecast input evidence exists; downgrade refused';
      END IF;
    END $$""")
    ops.execute("DROP INDEX erev.ux_forecast_event_set__published")
    ops.execute("DROP TRIGGER tg_forecast_event_set__config_version ON erev.forecast_event_set")
    ops.execute("DROP FUNCTION erev.tg_forecast_event_set__config_version()")
    ops.add_config_version_trigger("forecast_event_set", scope_columns=["code"])
