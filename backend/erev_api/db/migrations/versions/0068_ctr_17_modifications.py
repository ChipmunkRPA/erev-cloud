"""BUILD_SPEC item CTR-17 (D-98 140): the modification object.

04 ids created: E-23 ``modification_treatment``, E-24 ``modification_template_mode``, E-25
``modification_kind`` (the D-98 66 pending entries of ``tests/support/enum_mirrors.py`` close) and
T-CON-06 ``modification`` (04 rev 1.70) with its DB-03 function.

- T-CON-06 ``modification`` (IM-S, RLS-TE on ``contracting_entity_id``): primary key
  ``(tenant_id, id)``; ``ux_modification__no``; ``ux_modification__reference`` (partial, a repeat of
  an external reference on one contract is refused, REQ-MOD-019); ``ix_modification__contract``;
  ``ix_modification__regroup`` (partial; the D-98 140 Q-4 link of the two modifications a regroup
  after posting creates); the JSON shape checks ``ck_modification__questionnaire``,
  ``ck_modification__lines``, ``ck_modification__proposed_treatments``,
  ``ck_modification__chosen_treatments``, ``ck_modification__ssp_basis``; the foreign keys to
  ``contract``, ``legal_entity``, ``judgement_record``, ``import_upload`` (the legacy import that
  recorded the row), ``file_object`` (the impact preview), ``approval_request`` and
  ``contract_event`` (the applied amendment, or the separate contract's booking event under
  ENGINE_SPEC S06-R-03); and the incoming ``fk_contract_event__modification`` on T-CON-05
  ``contract_event.modification_id``, whose target table this revision creates (dropped first
  on downgrade). DB-03 ``tg_modification__transition``: editable while
  DRAFT, afterwards ``status``, ``approval_request_id``, ``applied_event_id`` and SC-M only, along
  PRD SM-03 (``erev_api.db.transitions``).

One function is added. A revision imports nothing of ``erev_api`` beyond the DDL helpers
(DG-MIG-12): the enum labels and the trigger body are literals.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

TABLE = "modification"
_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 §3.4 E-23, E-24, E-25 (rev 1.70 values; equal to the ``erev_api.enums`` mirrors, DG-MIG-12).
MODIFICATION_TREATMENT = (
    "SEPARATE_CONTRACT",
    "PROSPECTIVE",
    "CUMULATIVE_CATCH_UP",
    "MIXED",
    "LEGACY_PROSPECTIVE",
    "LEGACY_RETROSPECTIVE",
    "LEGACY_POB_VC",
)
MODIFICATION_TEMPLATE_MODE = (
    "prospective",
    "retrospective",
    "pob_price_change",
)
MODIFICATION_KIND = (
    "ADD_OBLIGATION",
    "REMOVE_OBLIGATION",
    "QUANTITY_CHANGE",
    "PRICE_CHANGE",
    "TERM_CHANGE",
    "UPGRADE",
    "DOWNGRADE",
    "CO_TERM",
    "RENEWAL",
    "CANCELLATION",
    "TERMINATION",
    "VC_CHANGE",
    "OTHER",
    "EARLY_RENEWAL",
)
CHECKS = (
    ("ck_modification__questionnaire", "jsonb_typeof(questionnaire) = 'object'"),
    ("ck_modification__lines", "jsonb_typeof(lines) = 'array'"),
    ("ck_modification__proposed_treatments", "jsonb_typeof(proposed_treatments) = 'object'"),
    ("ck_modification__chosen_treatments", "jsonb_typeof(chosen_treatments) = 'object'"),
    ("ck_modification__ssp_basis", "jsonb_typeof(ssp_basis) = 'object'"),
)
# 04 T-CON-06 class IM-S: the columns granted for UPDATE (every editable column while DRAFT; the
# DB-03 trigger narrows them afterwards).
UPDATE_COLUMNS = (
    "effective_date",
    "kind",
    "template_mode",
    "status",
    "reference",
    "questionnaire",
    "lines",
    "price_change_amount",
    "noncash_consideration",
    "consideration_payable",
    "scope_605_35",
    "currency",
    "proposed_treatments",
    "chosen_treatments",
    "treatment_summary",
    "ssp_basis",
    "rationale",
    "judgement_record_id",
    "impact_preview_file_id",
    "impact_preview_sha256",
    "content_sha256",
    "approval_request_id",
    "applied_event_id",
    "regroup_id",
    *_SC_M,
)

# DB-03: erev_api.db.transitions.transition_trigger_sql("modification") at CTR-17 (regenerated for
# D-98 candidate 143 GUARD-TRN-1: the pair guard precedes the editable early-return); DG-ARC-07
# compares the installed function with a fresh rendering.
TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPLIED>VOIDED', 'APPROVED>APPLIED', 'DRAFT>SUBMITTED', 'DRAFT>VOIDED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>DRAFT', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_id', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _create_modification() -> None:
    ops.create_tenant_table(
        TABLE,
        sa.Column("modification_no", sa.Text(), nullable=False),
        _uuid("contract_id", nullable=False),
        _uuid("contracting_entity_id", nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        _named("kind", "erev.modification_kind", nullable=False),
        _named("template_mode", "erev.modification_template_mode", nullable=True),
        _named("status", "erev.modification_status", nullable=False, default="'DRAFT'"),
        sa.Column("reference", sa.Text(), nullable=True),
        _named("questionnaire", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("lines", "jsonb", nullable=False),
        _named("price_change_amount", "erev.money", nullable=True),
        _named("noncash_consideration", "jsonb", nullable=True),
        _named("consideration_payable", "jsonb", nullable=True),
        sa.Column("scope_605_35", sa.Boolean(), nullable=True),
        _named("currency", "erev.currency_code", nullable=False),
        _named("proposed_treatments", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("chosen_treatments", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("treatment_summary", "erev.modification_treatment", nullable=True),
        _named("ssp_basis", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("rationale", "erev.memo", nullable=True),
        _uuid("judgement_record_id"),
        _uuid("impact_preview_file_id"),
        _named("impact_preview_sha256", "erev.sha256", nullable=True),
        _named("content_sha256", "erev.sha256", nullable=True),
        _uuid("approval_request_id"),
        _uuid("applied_event_id"),
        _uuid("regroup_id"),
        _uuid("import_upload_id"),
        standard_sets=["SC-C", "SC-M"],
        checks=CHECKS,
        unique=[
            ("ux_modification__no", ["tenant_id", "modification_no"], None),
            (
                "ux_modification__reference",
                ["tenant_id", "contract_id", "reference"],
                "reference IS NOT NULL",
            ),
        ],
        indexes=[
            ("ix_modification__contract", ["tenant_id", "contract_id", "effective_date"], None),
            ("ix_modification__regroup", ["tenant_id", "regroup_id"], "regroup_id IS NOT NULL"),
        ],
    )
    ops.add_tenant_fk(TABLE, "contract_id", "contract")
    ops.add_tenant_fk(TABLE, "contracting_entity_id", "legal_entity")
    ops.add_tenant_fk(TABLE, "judgement_record_id", "judgement_record")
    ops.add_tenant_fk(TABLE, "import_upload_id", "import_upload")
    ops.add_tenant_fk(TABLE, "impact_preview_file_id", "file_object")
    ops.add_tenant_fk(TABLE, "approval_request_id", "approval_request")
    ops.add_tenant_fk(TABLE, "applied_event_id", "contract_event")
    ops.add_global_fk(TABLE, "currency", "currency", target_column="code")
    ops.apply_class(TABLE, "IM-S", update_columns=UPDATE_COLUMNS)
    ops.enable_rls(TABLE, "RLS-TE", entity_column="contracting_entity_id")
    ops.create_trigger(TABLE, "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("modification_treatment", MODIFICATION_TREATMENT)
    ops.create_enum("modification_template_mode", MODIFICATION_TEMPLATE_MODE)
    ops.create_enum("modification_kind", MODIFICATION_KIND)
    _create_modification()
    # T-CON-05 ``contract_event.modification_id`` (04 rev 1.70: CONTRACT_AMENDED,
    # CONTRACT_TERMINATED, REGROUPED) now has its target table (D-98 140-A3 R2):
    # fk_contract_event__modification.
    ops.add_tenant_fk("contract_event", "modification_id", TABLE)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute("ALTER TABLE erev.contract_event DROP CONSTRAINT fk_contract_event__modification")
    ops.drop_tenant_table(TABLE)
    ops.drop_enum("modification_kind")
    ops.drop_enum("modification_template_mode")
    ops.drop_enum("modification_treatment")
