"""BUILD_SPEC item DIN-1: import registry, uploads, rows and row lineage.

04 ids created: E-40 ``import_status`` and E-41 ``import_row_status``; T-IMP-01 ``import_template``
(IM-A, RLS-NONE-G, seeded with the 19 templates of 04 T-IMP-01, DG-MIG-07; the legacy rows come from
``0044_din_1_import_templates.json``); T-IMP-02
``import_upload`` (IM-S, RLS-T) with ``ux_import_upload__no``, the partial
``ux_import_upload__duplicate`` (REQ-DAT-001), the foreign keys to ``import_template``,
``file_object`` (source and diff file), ``approval_request`` and ``job``, and the DB-03 trigger
``tg_import_upload__transition`` rendered from ``erev_api.db.transitions``; T-IMP-03 ``import_row``
(IM-A, RLS-T) with the 04 key ``ux_import_row`` named ``ux_import_row__sheet_row`` (NC-16),
``ix_import_row__status``, ``ck_import_row__aggregated`` and the keys to the upload and itself;
T-IMP-04 ``import_row_lineage`` (IM-A, RLS-T) with ``ix_import_row_lineage__row``,
``ix_import_row_lineage__target``, ``ck_import_row_lineage__target_type`` and the keys to the row
and the upload.

Foreign keys that name the new tables (DG-MIG-03): ``exception_item.import_upload_id`` and
``import_row_id`` (BS3-D-02), ``ssp_book_version.import_upload_id`` (0034),
``fx_rate_set_version.import_upload_id`` (0030) and ``contract_event.import_upload_id`` (0038).
``import_upload.mapping_profile_id`` waits for T-IMP-06 (DIN-10). One function is added.

[J] L4-1-Q-26: the 15 ``CSV_V2`` rows are seeded with an empty header array; their flattened command
fields (NC-19) belong to the items that build their emitters (DIN-3, DIN-9).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

# 04 §3.4 E-40 and E-41 (DG-MIG-06).
IMPORT_STATUS = (
    "UPLOADED",
    "VALIDATING",
    "INVALID",
    "VALIDATED",
    "DIFFING",
    "DIFF_READY",
    "SUBMITTED",
    "APPROVED",
    "COMMITTING",
    "COMMITTED",
    "FAILED",
    "REJECTED",
    "CANCELLED",
)
IMPORT_ROW_STATUS = ("VALID", "WARNING", "ERROR", "BLANK", "AGGREGATED")
_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 T-IMP-02 IM-S: the columns erev_app may update.
UPLOAD_UPDATE_COLUMNS = (
    "status",
    "row_count",
    "valid_row_count",
    "warning_count",
    "error_count",
    "control_totals",
    "diff_summary",
    "diff_file_id",
    "approval_request_id",
    "committed_at",
    "job_id",
    *_SC_M,
)
# 04 T-IMP-04 ``target_type``.
LINEAGE_TARGETS = (
    "source_record",
    "contract_event",
    "modification",
    "ssp_book_version",
    "ssp_entry",
    "product",
    "customer",
    "estimate_version",
    "fx_rate",
    "gl_account",
    "account_mapping_rule",
    "contract_cost_asset",
    "product_bundle_component",
    "migrated_legacy_row",
)

# DB-03: erev_api.db.transitions.transition_trigger_sql("import_upload") at DIN-1; DG-ARC-07
# compares the installed function with a fresh rendering.
UPLOAD_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'committed_at', 'control_totals', 'diff_file_id', 'diff_summary', 'error_count', 'job_id', 'row_count', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind', 'valid_row_count', 'warning_count']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.committed_at IS NOT NULL AND NEW.committed_at IS DISTINCT FROM OLD.committed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: committed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>COMMITTING', 'COMMITTING>COMMITTED', 'COMMITTING>FAILED', 'DIFFING>CANCELLED', 'DIFFING>DIFF_READY', 'DIFF_READY>CANCELLED', 'DIFF_READY>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'UPLOADED>CANCELLED', 'UPLOADED>VALIDATING', 'VALIDATED>CANCELLED', 'VALIDATED>DIFFING', 'VALIDATING>CANCELLED', 'VALIDATING>INVALID', 'VALIDATING>VALIDATED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The four LEGACY_V1 rows of 04 T-IMP-01: exact headers with LM-SSP and LM-TPL types and the table
# 15.4-A type-stage codes of each column (L4-1-Q-28), the required parameters, row models and the
# aggregation rule. The adjacent JSON file keeps the legacy column names, which use legacy wording,
# out of Python string constants (DG-MK-vocab-check, D-33); it equals
# ``erev_api.domain.imports.legacy_templates.LEGACY_HEADERS``.
LEGACY_SEED = Path(__file__).with_name("0044_din_1_import_templates.json")
_CSV_MODULE = "erev_api.domain.imports.csv_v2"
# 04 T-IMP-01 CSV_V2 codes in table order, with their names and the command family they emit.
CSV_TEMPLATES: Sequence[tuple[str, str, str]] = (
    ("customers", "Customers", "customer"),
    ("products", "Products", "product"),
    ("bundles", "Bundles", "product_bundle_component"),
    ("ssp_values", "SSP values", "ssp_book_version"),
    ("contracts", "Contracts", "contract"),
    ("invoices", "Invoices", "contract_event"),
    ("progress_events", "Progress events", "contract_event"),
    ("usage", "Usage", "contract_event"),
    ("modifications", "Modifications", "modification"),
    ("estimates", "Estimates", "estimate_version"),
    ("fx_rates", "FX rates", "fx_rate"),
    ("cost_events", "Cost events", "contract_event"),
    ("pre_standard_revenue", "Pre-standard revenue", "contract_event"),
    ("gl_accounts", "GL accounts", "gl_account"),
    ("account_mapping", "Account mapping", "account_mapping_rule"),
)
TEMPLATE_COLUMNS = (
    "code",
    "version",
    "name",
    "family",
    "target_object",
    "file_format",
    "header_match",
    "headers",
    "required_parameters",
    "row_model",
    "aggregation_rule",
)
# Foreign keys of earlier tables to the new tables: (table, column, target).
EXISTING_KEYS = (
    ("exception_item", "import_upload_id", "import_upload"),
    ("exception_item", "import_row_id", "import_row"),
    ("ssp_book_version", "import_upload_id", "import_upload"),
    ("fx_rate_set_version", "import_upload_id", "import_upload"),
    ("contract_event", "import_upload_id", "import_upload"),
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def legacy_templates() -> list[dict[str, Any]]:
    """The LEGACY_V1 seed entries, in table order."""
    entries: list[dict[str, Any]] = json.loads(LEGACY_SEED.read_text(encoding="utf-8"))
    return entries


def template_rows() -> list[tuple[str | int | None, ...]]:
    """The 19 seed rows of 04 T-IMP-01, in table order."""
    rows: list[tuple[str | int | None, ...]] = [
        (
            entry["code"],
            1,
            entry["name"],
            "LEGACY_V1",
            entry["target_object"],
            "XLSX",
            "EXACT_SET",
            _json(entry["headers"]),
            _json(entry["required_parameters"]),
            entry["row_model"],
            entry["aggregation_rule"],
        )
        for entry in legacy_templates()
    ]
    rows += [
        (
            code,
            1,
            name,
            "CSV_V2",
            target,
            "CSV",
            "ALIASES",
            "[]",
            "[]",
            f"{_CSV_MODULE}.{code}",
            None,
        )
        for code, name, target in CSV_TEMPLATES
    ]
    return rows


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _integer(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Integer(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _create_import_template() -> None:
    ops.create_global_table(
        "import_template",
        _text("code", nullable=False),
        _integer("version", nullable=False),
        _named("name", "erev.label", nullable=False),
        _text("family", nullable=False),
        _text("target_object", nullable=False),
        _text("file_format", nullable=False),
        sa.Column("sheet_rule", sa.Text(), nullable=False, server_default=sa.text("'FIRST_SHEET'")),
        _text("header_match", nullable=False),
        _named("headers", "jsonb", nullable=False),
        _named("required_parameters", "jsonb", nullable=False, default="'[]'"),
        _text("row_model", nullable=False),
        _text("aggregation_rule"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        primary_key=["code", "version"],
        checks=[
            ("ck_import_template__family", "family IN ('LEGACY_V1','CSV_V2')"),
            ("ck_import_template__file_format", "file_format IN ('XLSX','CSV')"),
            ("ck_import_template__header_match", "header_match IN ('EXACT_SET','ALIASES')"),
        ],
    )
    ops.insert_rows("import_template", TEMPLATE_COLUMNS, template_rows())
    ops.apply_class("import_template", "IM-A", global_reference=True)


def _create_import_upload() -> None:
    table = "import_upload"
    ops.create_tenant_table(
        table,
        _text("import_no", nullable=False),
        _text("template_code", nullable=False),
        _integer("template_version", nullable=False),
        _uuid("file_object_id", nullable=False),
        _named("file_sha256", "erev.sha256", nullable=False),
        _named("parameters", "jsonb", nullable=False, default="'{}'"),
        _uuid("mapping_profile_id"),
        _named("status", "erev.import_status", nullable=False, default="'UPLOADED'"),
        _integer("row_count"),
        _integer("valid_row_count"),
        _integer("warning_count"),
        _integer("error_count"),
        sa.Column(
            "is_quarantine_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        _named("control_totals", "jsonb", nullable=True),
        _named("diff_summary", "jsonb", nullable=True),
        _uuid("diff_file_id"),
        _uuid("approval_request_id"),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("job_id"),
        standard_sets=["SC-C", "SC-M"],
        unique=[
            ("ux_import_upload__no", ["tenant_id", "import_no"], None),
            (
                "ux_import_upload__duplicate",
                ["tenant_id", "template_code", "template_version", "file_sha256"],
                "status NOT IN ('INVALID','REJECTED','CANCELLED','FAILED')",
            ),
        ],
    )
    ops.execute(
        "ALTER TABLE erev.import_upload ADD CONSTRAINT fk_import_upload__template "
        "FOREIGN KEY (template_code, template_version) REFERENCES erev.import_template "
        "(code, version) ON DELETE RESTRICT ON UPDATE RESTRICT"
    )
    ops.add_tenant_fk(table, "file_object_id", "file_object")
    ops.add_tenant_fk(table, "diff_file_id", "file_object")
    ops.add_tenant_fk(table, "approval_request_id", "approval_request")
    ops.add_tenant_fk(table, "job_id", "job")
    ops.apply_class(table, "IM-S", update_columns=UPLOAD_UPDATE_COLUMNS)
    ops.enable_rls(table, "RLS-T")
    ops.create_trigger(
        table, "transition", UPLOAD_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def _create_import_row() -> None:
    table = "import_row"
    ops.create_tenant_table(
        table,
        _uuid("import_upload_id", nullable=False),
        _text("sheet_name", nullable=False),
        _integer("row_number", nullable=False),
        _named("raw", "jsonb", nullable=False),
        _named("normalized", "jsonb", nullable=True),
        _named("row_sha256", "erev.sha256", nullable=False),
        _named("status", "erev.import_row_status", nullable=False),
        _text("business_key"),
        _uuid("aggregated_into_row_id"),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_import_row__aggregated",
                "(status = 'AGGREGATED') = (aggregated_into_row_id IS NOT NULL)",
            )
        ],
        unique=[
            (
                "ux_import_row__sheet_row",
                ["tenant_id", "import_upload_id", "sheet_name", "row_number"],
                None,
            )
        ],
        indexes=[("ix_import_row__status", ["tenant_id", "import_upload_id", "status"], None)],
    )
    ops.add_tenant_fk(table, "import_upload_id", "import_upload")
    ops.add_tenant_fk(table, "aggregated_into_row_id", table)
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")


def _create_import_row_lineage() -> None:
    table = "import_row_lineage"
    targets = ", ".join(f"'{target}'" for target in LINEAGE_TARGETS)
    ops.create_tenant_table(
        table,
        _uuid("import_row_id", nullable=False),
        _uuid("import_upload_id", nullable=False),
        _text("target_type", nullable=False),
        _uuid("target_id", nullable=False),
        standard_sets=["SC-C"],
        checks=[("ck_import_row_lineage__target_type", f"target_type IN ({targets})")],
        indexes=[
            ("ix_import_row_lineage__row", ["tenant_id", "import_row_id"], None),
            ("ix_import_row_lineage__target", ["tenant_id", "target_type", "target_id"], None),
        ],
    )
    ops.add_tenant_fk(table, "import_row_id", "import_row")
    ops.add_tenant_fk(table, "import_upload_id", "import_upload")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("import_status", IMPORT_STATUS)
    ops.create_enum("import_row_status", IMPORT_ROW_STATUS)
    _create_import_template()
    _create_import_upload()
    _create_import_row()
    _create_import_row_lineage()
    for table, column, target in EXISTING_KEYS:
        ops.add_tenant_fk(table, column, target)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for table, column, _target in reversed(EXISTING_KEYS):
        stem = column.removesuffix("_id")
        ops.execute(f"ALTER TABLE erev.{table} DROP CONSTRAINT fk_{table}__{stem}")
    ops.drop_tenant_table("import_row_lineage")
    ops.drop_tenant_table("import_row")
    ops.drop_tenant_table("import_upload")
    ops.drop_global_table("import_template")
    ops.drop_enum("import_row_status")
    ops.drop_enum("import_status")
