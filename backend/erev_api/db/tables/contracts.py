"""Contract tables (04 §6: T-CON-01, T-CON-03 to T-CON-05, T-CON-10, T-CON-12, T-CON-13,
T-CON-19, T-CON-23, T-CON-24; BUILD_SPEC CTR-1, CTR-7, CTR-12, CTR-15).

Created by revision 0038; revision 0042 adds ``judgement_record``, revision 0045 (CTR-15) creates
``policy_override`` (T-CON-23) and revision 0051 (CTR-12) ``estimate`` and ``estimate_version``
(T-CON-12, T-CON-13). The later CTR revisions add the tables of computed state and the foreign keys
that name them (DG-MIG-03).
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Column,
    Date,
    Integer,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.engine_output import computation_trigger, hold_type
from erev_api.db.tables.platform import (
    _enum,
    _sc_c,
    _sc_c_sc_m,
    _timestamp,
    config_status,
    registry_scope,
)
from erev_api.db.tables.reference import book_code_type, source_system
from erev_api.db.types import ExactType, MoneyType
from erev_api.enums import (
    CombinationStatus,
    ContractEventType,
    ContractStatus,
    EstimateKind,
    EstimateMethod,
    HoldSource,
    JudgementStatus,
    JudgementTopic,
    ModificationKind,
    ModificationStatus,
    ModificationTemplateMode,
    ModificationTreatment,
)

# Created by revision 0038 (CTR-1): E-03, E-17, E-26, E-95.
contract_event_type: Final = _enum(ContractEventType, "contract_event_type")
contract_status: Final = _enum(ContractStatus, "contract_status")
modification_status: Final = _enum(ModificationStatus, "modification_status")
combination_status: Final = _enum(CombinationStatus, "combination_status")
# Created by revision 0042 (CTR-7): E-56, E-57.
judgement_topic: Final = _enum(JudgementTopic, "judgement_topic")
judgement_status: Final = _enum(JudgementStatus, "judgement_status")
# Created by revision 0068 (CTR-17): E-23, E-24, E-25.
modification_treatment: Final = _enum(ModificationTreatment, "modification_treatment")
modification_template_mode: Final = _enum(ModificationTemplateMode, "modification_template_mode")
modification_kind: Final = _enum(ModificationKind, "modification_kind")

# T-CON-01: contract identity and header projection (IM-X, RLS-TE on ``contracting_entity_id``);
# DB-18 ``tg_contract__projection``. Revision 0125 (item ACT-FLAGS-1) adds ``acceptance_clause``
# and ``side_letter`` after the standard columns.
contract: Final = Table(
    "contract",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_no", Text(), nullable=False),
    Column("external_id", Text(), nullable=False),
    Column("customer_id", Uuid(), nullable=False),
    Column("contracting_entity_id", Uuid(), nullable=False),
    Column("transaction_currency", CHAR(3), nullable=False),
    Column("inception_date", Date(), nullable=False),
    Column("status", contract_status, nullable=False, server_default=text("'DRAFT'")),
    Column("combination_group_id", Uuid(), nullable=False),
    Column("head_stream_version", Integer(), nullable=False, server_default=text("0")),
    Column("latest_computation_id", Uuid(), nullable=True),
    Column("signature_date", Date(), nullable=True),
    Column("document_ref", Text(), nullable=True),
    Column("payment_terms", Text(), nullable=True),
    Column("termination_party", Text(), nullable=True),
    Column("termination_has_penalty", Boolean(), nullable=True),
    Column("termination_notice_days", Integer(), nullable=True),
    Column("has_commercial_substance", Boolean(), nullable=False, server_default=text("true")),
    Column("region", Text(), nullable=True),
    Column("channel", Text(), nullable=True),
    Column("contract_type", Text(), nullable=True),
    Column("memo_1", Text(), nullable=True),
    Column("memo_2", Text(), nullable=True),
    Column("memo_3", Text(), nullable=True),
    Column("custom_attributes", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("activation_checklist", JSONB(none_as_null=True), nullable=True),
    _timestamp("activated_at"),
    _timestamp("completed_at"),
    _timestamp("terminated_at"),
    _timestamp("voided_at"),
    Column("renewal_of_contract_id", Uuid(), nullable=True),
    Column("portfolio_id", Uuid(), nullable=True),
    Column("scope_605_35", Boolean(), nullable=False, server_default=text("false")),
    Column("source_system", source_system, nullable=False),
    *_sc_c_sc_m(),
    # 04 rev 1.287 (revision 0125): what the booking states of two terms no other member holds;
    # NULL is "not stated" (API-S-ContractBooked ``acceptance_clause``, ``side_letter``).
    Column("acceptance_clause", Boolean(), nullable=True),
    Column("side_letter", Boolean(), nullable=True),
)

# T-CON-03: accounting unit of Steps 2 to 5 (IM-S, RLS-T); DB-03
# ``tg_combination_group__transition``. Revision 0111 (item CLO-GATE-RUN-1) adds
# ``period_ends_open`` after the standard columns, and revision 0128 (item FX-REPUBLISH-DIRTY-1)
# ``dirty_trigger`` after it.
combination_group: Final = Table(
    "combination_group",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("is_singleton", Boolean(), nullable=False),
    Column("status", combination_status, nullable=False),
    Column("transaction_currency", CHAR(3), nullable=False),
    Column("criterion", Text(), nullable=True),
    Column("rationale", Text(), nullable=True),
    Column("judgement_record_id", Uuid(), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("inception_date", Date(), nullable=False),
    Column("head_computation_id", Uuid(), nullable=True),
    _timestamp("dirty_since"),
    *_sc_c_sc_m(),
    Column("period_ends_open", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("dirty_trigger", computation_trigger, nullable=True),
)

# T-CON-04: membership of contracts in groups over record time (IM-S, RLS-T); DB-03
# ``tg_combination_group_member__transition``.
combination_group_member: Final = Table(
    "combination_group_member",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("combination_group_id", Uuid(), nullable=False),
    Column("contract_id", Uuid(), nullable=False),
    _timestamp("valid_from_known_at", nullable=False),
    _timestamp("valid_to_known_at"),
    Column("join_event_id", Uuid(), nullable=False),
    Column("leave_event_id", Uuid(), nullable=True),
    *_sc_c(),
)

# T-CON-05: the append-only event stream of a contract (IM-A, RLS-TE on ``contracting_entity_id``);
# DB-01, DB-08 ``tg_contract_event__insert``.
contract_event: Final = Table(
    "contract_event",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), nullable=False),
    Column("contracting_entity_id", Uuid(), nullable=False),
    Column("stream_version", Integer(), nullable=False),
    Column("event_type", contract_event_type, nullable=False),
    Column("schema_version", SmallInteger(), nullable=False, server_default=text("1")),
    Column("effective_date", Date(), nullable=False),
    _timestamp("recorded_at", nullable=False, now_default=True),
    Column(
        "record_seq",
        BigInteger(),
        nullable=False,
        server_default=text("nextval('erev.contract_event_record_seq')"),
    ),
    Column("origin", Text(), nullable=False),
    Column("is_manual", Boolean(), nullable=False, server_default=text("false")),
    Column("obligation_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'::uuid[]")),
    Column("payload", JSONB(), nullable=False),
    Column("payload_sha256", CHAR(64), nullable=False),
    Column("idempotency_key", Text(), nullable=True),
    Column("supersedes_event_id", Uuid(), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("modification_id", Uuid(), nullable=True),
    Column("estimate_version_id", Uuid(), nullable=True),
    Column("manual_adjustment_id", Uuid(), nullable=True),
    Column("import_upload_id", Uuid(), nullable=True),
    Column("source_record_id", Uuid(), nullable=True),
    Column("sync_run_id", Uuid(), nullable=True),
    Column("request_id", Text(), nullable=False),
    *_sc_c(),
)

# T-CON-10: continuous identity of a performance obligation (IM-A, RLS-T).
obligation: Final = Table(
    "obligation",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), nullable=False),
    Column("obligation_key", Text(), nullable=False),
    Column("product_id", Uuid(), nullable=False),
    Column("legacy_record_key", Text(), nullable=False),
    Column("created_by_event_id", Uuid(), nullable=False),
    Column("parent_obligation_id", Uuid(), nullable=True),
    Column("regrouped_from_obligation_id", Uuid(), nullable=True),
    Column("line_sequence", Integer(), nullable=False),
    *_sc_c(),
)

# T-CON-24: events waiting for approval (IM-S, RLS-TE on ``contracting_entity_id``); DB-03
# ``tg_event_submission__transition``.
event_submission: Final = Table(
    "event_submission",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), nullable=False),
    Column("contracting_entity_id", Uuid(), nullable=False),
    Column("events", JSONB(), nullable=False),
    Column("status", modification_status, nullable=False, server_default=text("'DRAFT'")),
    Column("comment", Text(), nullable=True),
    Column("content_sha256", CHAR(64), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("applied_event_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'::uuid[]")),
    *_sc_c_sc_m(),
)

# T-CON-06: the modification object with questionnaire, proposed and chosen treatments, impact
# preview and approval (IM-S, RLS-TE on ``contracting_entity_id``); DB-03
# ``tg_modification__transition``. Created by the CTR-17 revision 0068 (D-98 140; 04 rev 1.70).
modification: Final = Table(
    "modification",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("modification_no", Text(), nullable=False),
    Column("contract_id", Uuid(), nullable=False),
    Column("contracting_entity_id", Uuid(), nullable=False),
    Column("effective_date", Date(), nullable=False),
    Column("kind", modification_kind, nullable=False),
    Column("template_mode", modification_template_mode, nullable=True),
    Column("status", modification_status, nullable=False, server_default=text("'DRAFT'")),
    Column("reference", Text(), nullable=True),
    Column("questionnaire", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("lines", JSONB(), nullable=False),
    Column("price_change_amount", MoneyType(), nullable=True),
    Column("noncash_consideration", JSONB(none_as_null=True), nullable=True),
    Column("consideration_payable", JSONB(none_as_null=True), nullable=True),
    Column("scope_605_35", Boolean(), nullable=True),
    Column("currency", CHAR(3), nullable=False),
    Column("proposed_treatments", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("chosen_treatments", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("treatment_summary", modification_treatment, nullable=True),
    Column("ssp_basis", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("rationale", Text(), nullable=True),
    Column("judgement_record_id", Uuid(), nullable=True),
    Column("impact_preview_file_id", Uuid(), nullable=True),
    Column("impact_preview_sha256", CHAR(64), nullable=True),
    Column("content_sha256", CHAR(64), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("applied_event_id", Uuid(), nullable=True),
    Column("regroup_id", Uuid(), nullable=True),
    Column("import_upload_id", Uuid(), nullable=True),
    # 04 rev 1.210 (revision 0114): what ``/classify`` answered as ``prefill_reasons``; NULL until
    # the row is classified and again after every edit.
    Column("classification", JSONB(none_as_null=True), nullable=True),
    *_sc_c_sc_m(),
)

# T-CON-19: documented accounting judgement with preparer and reviewer (IM-S, RLS-T); DB-03
# ``tg_judgement_record__transition`` and DB-10 ``tg_judgement_record__review``.
judgement_record: Final = Table(
    "judgement_record",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("judgement_no", Text(), nullable=False),
    Column("topic", judgement_topic, nullable=False),
    Column("subject_type", Text(), nullable=False),
    Column("subject_id", Uuid(), nullable=False),
    Column("contract_id", Uuid(), nullable=True),
    Column("book_code", book_code_type, nullable=True),
    Column("conclusion", Text(), nullable=False),
    Column("rationale", Text(), nullable=False),
    Column("alternatives_considered", Text(), nullable=True),
    Column("codification_refs", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    Column("questionnaire", JSONB(none_as_null=True), nullable=True),
    Column("status", judgement_status, nullable=False, server_default=text("'DRAFT'")),
    Column("reviewer_id", Uuid(), nullable=True),
    _timestamp("reviewed_at"),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("content_sha256", CHAR(64), nullable=True),
    Column("supersedes_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
)

# Created by revision 0043 (CTR-10): E-46; E-45 ``hold_type`` exists since 0039.
hold_source: Final = _enum(HoldSource, "hold_source")

# T-CON-20: current and historical holds, the projection of HOLD_APPLIED and HOLD_RELEASED (IM-X,
# RLS-T). [J] L4-1-Q-22: ``id`` equals the id of the hold's HOLD_APPLIED event.
contract_hold: Final = Table(
    "contract_hold",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), nullable=False),
    Column("obligation_id", Uuid(), nullable=True),
    Column("hold_type", hold_type, nullable=False),
    Column("hold_source", hold_source, nullable=False),
    Column("reason", Text(), nullable=False),
    Column("rule_set_version_id", Uuid(), nullable=True),
    Column("rule_id", Uuid(), nullable=True),
    Column("applied_event_id", Uuid(), nullable=False),
    _timestamp("applied_at", nullable=False),
    Column("released_event_id", Uuid(), nullable=True),
    _timestamp("released_at"),
)

# T-CON-23: a contract-level or obligation-level policy value under OVR approval (IM-S, RLS-T);
# DB-03 ``tg_policy_override__transition``. Created by the CTR-15 revision.
policy_override: Final = Table(
    "policy_override",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), nullable=False),
    Column("obligation_id", Uuid(), nullable=True),
    Column("level", registry_scope, nullable=False),
    Column("policy_key", Text(), nullable=False),
    Column("value", JSONB(), nullable=False),
    Column("rationale", Text(), nullable=False),
    Column("judgement_record_id", Uuid(), nullable=True),
    Column("status", config_status, nullable=False, server_default=text("'DRAFT'")),
    Column("content_sha256", CHAR(64), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    _timestamp("approved_at"),
    Column("supersedes_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
)

# Created by revision 0051 (CTR-12): E-09, E-10.
estimate_kind: Final = _enum(EstimateKind, "estimate_kind")
estimate_method: Final = _enum(EstimateMethod, "estimate_method")

# T-CON-12: identity of an estimated element (IM-A, RLS-T). ``portfolio_id`` gains its foreign key
# with CTR-13.
estimate: Final = Table(
    "estimate",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), nullable=True),
    Column("portfolio_id", Uuid(), nullable=True),
    Column("obligation_id", Uuid(), nullable=True),
    Column("estimate_kind", estimate_kind, nullable=False),
    Column("element_code", Text(), nullable=False),
    Column("vc_element_type", Text(), nullable=True),
    Column("direction", Text(), nullable=False, server_default=text("'INCREASE'")),
    Column("method", estimate_method, nullable=False),
    Column("allocation_target", Text(), nullable=False, server_default=text("'CONTRACT'")),
    Column("target_obligation_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'")),
    Column("allocation_criteria_evidence", Text(), nullable=True),
    *_sc_c(),
)

# T-CON-13: an immutable estimate version with preparer, approver and rationale (IM-S, RLS-T); DB-03
# ``tg_estimate_version__transition``. Created by the CTR-12 revision; revision 0114 adds
# ``modification_id`` and the pair DRAFT → VOIDED; revision 0117 adds the partial unique index
# ``ux_estimate_version__open`` — one DRAFT or SUBMITTED version of an element.
estimate_version: Final = Table(
    "estimate_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("estimate_id", Uuid(), nullable=False),
    Column("version_no", Integer(), nullable=False),
    Column("status", config_status, nullable=False, server_default=text("'DRAFT'")),
    Column("effective_date", Date(), nullable=False),
    Column("scenarios", JSONB(), nullable=False, server_default=text("'[]'")),
    Column("parameters", JSONB(), nullable=False, server_default=text("'{}'")),
    Column("unconstrained_amount", MoneyType(), nullable=True),
    Column("most_conservative_amount", MoneyType(), nullable=True),
    Column("constrained_amount", MoneyType(), nullable=True),
    Column("rate", ExactType(), nullable=True),
    Column("expected_total_amount", MoneyType(), nullable=True),
    Column("expected_quantity", ExactType(), nullable=True),
    Column("amortization_months", Integer(), nullable=True),
    Column("currency", CHAR(3), nullable=True),
    Column("constraint_checklist", JSONB(none_as_null=True), nullable=True),
    Column("rationale", Text(), nullable=False),
    Column("judgement_record_id", Uuid(), nullable=True),
    Column("content_sha256", CHAR(64), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("applied_event_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'")),
    Column("supersedes_version_id", Uuid(), nullable=True),
    # 04 rev 1.210 (revision 0114): the modification the version was created inside; written by
    # the INSERT only (no column UPDATE grant).
    Column("modification_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
)
