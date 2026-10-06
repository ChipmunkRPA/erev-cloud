"""Platform registry parameters: 04 T-PLT-31 catalogue rule 2 (dev-guide §5.15).

Hand-maintained; ``test_registry_seed.py`` compares codes, categories, defaults and legacy parity
values with the 04 table. Descriptions are short copy written for the catalogue (04 gives none).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from erev_api.enums import RegistryCategory, RegistryScope
from erev_api.registry.policies import RegistryParameterSpec

SECTION: Final = "Platform"  # T-PLT-31 `section` for platform parameters


def _integer(minimum: int, maximum: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer", "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _decimal(minimum: str | None = None, maximum: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "format": "decimal"}
    if minimum is not None:
        schema["x-minimum"] = minimum
    if maximum is not None:
        schema["x-maximum"] = maximum
    return schema


_BOOLEAN: Final[Mapping[str, Any]] = {"type": "boolean"}
# T-PLT-31 rule 2 `platform.snapshot_retention_families` (04 rev 1.19): the copied snapshot
# families (SBX-03) and the P8 retention literals; snapshot_dataset pins both against these.
_SNAPSHOT_FAMILIES: Final = (
    "file_object",
    "import_row",
    "source_record",
    "contract_event",
    "manual_adjustment",
)
_RETENTION_LITERALS: Final = (
    "TENANT_LIFETIME",
    "AUDIT_RETENTION_YEARS",
    "EXPIRES_AT_SWEEP",
    "FILE_RETENTION",
)
# Ruling D-98 cand. 86: a version carrying one of these parameters never auto-approves — the CFG
# approval needs a named human approver (the registry-version submit withholds AUTO_APPROVAL).
HUMAN_APPROVAL_REQUIRED: Final = frozenset({"platform.snapshot_retention_families"})


def _platform(
    code: str,
    category: RegistryCategory,
    value_schema: Mapping[str, Any],
    default: Any,
    parity: Any,
    description: str,
    source_ref: str,
) -> RegistryParameterSpec:
    """Rule 2: `allowed_levels = {TENANT}`, `pin = 'P'`, `approval_code = 'CFG'`."""
    return RegistryParameterSpec(
        code=code,
        pol_id=None,
        category=category,
        value_schema=dict(value_schema),
        default_asc606=default,
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=parity,
        allowed_levels=frozenset({RegistryScope.TENANT}),
        pin="P",
        approval_code="CFG",
        description=description,
        source_ref=source_ref,
        section=SECTION,
    )


_SPECS: Final[tuple[RegistryParameterSpec, ...]] = (
    _platform(
        "approval.ssp_second_approver_threshold_ratio",
        RegistryCategory.PLATFORM,
        _decimal(),
        "0.10",
        "0.10",
        "SSP change ratio above which an SSP book version needs a second approver.",
        "REQ-SSP-007",
    ),
    _platform(
        "disclosure.mandatory_disaggregation_attributes",
        RegistryCategory.DISCLOSURE_ELECTION,
        {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        [],
        [],
        "Attribute codes every revenue disaggregation disclosure includes.",
        "REQ-REF-012; research 07 RP-04",
    ),
    _platform(
        "close.require_reconciliations_for_lock",
        RegistryCategory.CLOSE,
        _BOOLEAN,
        True,
        True,
        "Whether locking a period requires completed reconciliations.",
        "Research 07 PC-02",
    ),
    _platform(
        "close.unacknowledged_export_block_days",
        RegistryCategory.CLOSE,
        _integer(0, 30),
        5,
        5,
        "Days a journal export may stay unacknowledged before it blocks the close.",
        "Research 07 JE-03",
    ),
    _platform(
        "close.late_entry_window_days",
        RegistryCategory.CLOSE,
        _integer(0, 31),
        5,
        5,
        "Days after period end in which late entries are accepted.",
        "REQ-CLS-007",
    ),
    _platform(
        "close.rollforward_other_threshold_ratio",
        RegistryCategory.CLOSE,
        _decimal(),
        "0.01",
        "0.01",
        "Ratio above which the Other line of a rollforward is flagged.",
        "REQ-RPT-006",
    ),
    _platform(
        "platform.session_idle_minutes",
        RegistryCategory.SECURITY,
        _integer(5, 240),
        30,
        30,
        "Minutes of inactivity after which a session expires.",
        "REQ-PLT-004",
    ),
    _platform(
        "platform.role_assignment_requires_approval",
        RegistryCategory.SECURITY,
        _BOOLEAN,
        True,
        True,
        "Whether role assignments need an approval.",
        "Research 07 AC-02",
    ),
    _platform(
        "platform.job_concurrency",
        RegistryCategory.PLATFORM,
        _integer(1, 16),
        4,
        4,
        "Background jobs a tenant may run at the same time.",
        "REQ-PLT-029",
    ),
    _platform(
        "platform.audit_retention_years",
        RegistryCategory.PLATFORM,
        _integer(7, 30),
        7,
        7,
        "Years audit events are retained.",
        "Research 07 AU-02",
    ),
    _platform(
        "ai.enabled",
        RegistryCategory.AI,
        _BOOLEAN,
        False,
        False,
        "Whether AI assistance is enabled for the tenant.",
        "D-46; REQ-AI-002",
    ),
    _platform(
        "ai.send_contract_text",
        RegistryCategory.AI,
        _BOOLEAN,
        False,
        False,
        "Whether contract text may be sent to the AI provider.",
        "D-46; REQ-AI-002",
    ),
    _platform(
        "ai.model",
        RegistryCategory.AI,
        {"type": "string", "minLength": 1},
        "claude-opus-5",
        "claude-opus-5",
        "Model id the AI provider adapter uses.",
        "D-46",
    ),
    _platform(
        "ai.monthly_token_budget",
        RegistryCategory.AI,
        _integer(0),
        2000000,
        2000000,
        "Tokens the tenant may use for AI requests per month.",
        "REQ-AI-009",
    ),
    _platform(
        "ai.redact_contact_details",
        RegistryCategory.AI,
        _BOOLEAN,
        True,
        True,
        "Whether contact details are redacted before an AI request.",
        "REQ-AI-009",
    ),
    _platform(
        "data.quarantine_failed_rows",
        RegistryCategory.INTEGRATION,
        _BOOLEAN,
        False,
        False,
        "Whether failed import rows are quarantined instead of blocking the commit.",
        "REQ-DAT-008",
    ),
    _platform(
        "integration.grouping_fields",
        RegistryCategory.INTEGRATION,
        {"type": "array", "items": {"type": "string"}, "maxItems": 5, "uniqueItems": True},
        ["order_number"],
        ["contract_unique_name"],
        "Canonical order fields, at most five, that group inbound orders into contracts.",
        "REQ-CON-011",
    ),
    _platform(
        "ai.anomaly.revenue_change_ratio",
        RegistryCategory.AI,
        _decimal("0", "10"),
        "0.50",
        "0.50",
        "ANOMALY_REVENUE_CHANGE flags period revenue that departs from the trailing three-period "
        "mean by more than this ratio; no flag when the mean is 0.",
        "REQ-AI-007; B1-036",
    ),
    _platform(
        "ai.anomaly.revenue_ahead_of_billing_days",
        RegistryCategory.AI,
        _integer(1, 365),
        60,
        60,
        "ANOMALY_REVENUE_AHEAD_OF_BILLING flags revenue ahead of billing for more than this many "
        "days.",
        "REQ-AI-007; B1-036",
    ),
    _platform(
        "ai.anomaly.allocation_adjustment_ratio",
        RegistryCategory.AI,
        _decimal("0", "1"),
        "0.20",
        "0.20",
        "ANOMALY_ALLOCATION_ADJUSTMENT flags an allocation that differs from the stated price by "
        "more than this ratio of the stated price.",
        "REQ-AI-007; B1-036",
    ),
    _platform(
        "close.dq_revenue_without_billing_days",
        RegistryCategory.CLOSE,
        _integer(1, 365),
        60,
        60,
        "DQ_REVENUE_WITHOUT_BILLING flags revenue recognised without billing for more than this "
        "many days.",
        "REQ-CLS-019; B1-036",
    ),
    _platform(
        "close.dq_inactive_contract_days",
        RegistryCategory.CLOSE,
        _integer(1, 730),
        90,
        90,
        "DQ_INACTIVE_CONTRACT flags an active contract without any event for more than this many "
        "days.",
        "REQ-CLS-019; B1-036",
    ),
    _platform(
        "ui.negative_number_style",
        RegistryCategory.PLATFORM,
        {"type": "string", "enum": ["PARENTHESES", "MINUS"]},
        "PARENTHESES",
        "PARENTHESES",
        "How negative amounts are displayed.",
        "REQ-UX-006; D-75",
    ),
    _platform(
        "platform.snapshot_retention_families",
        RegistryCategory.PLATFORM,
        {
            # 04 rev 1.56: `{}` (the refusing default) validates against its own schema — the
            # catalogue invariant every storable default meets; anything else is all five families.
            "anyOf": [
                {"const": {}},
                {
                    "type": "object",
                    "properties": {
                        family: {"type": "string", "enum": list(_RETENTION_LITERALS)}
                        for family in _SNAPSHOT_FAMILIES
                    },
                    "required": list(_SNAPSHOT_FAMILIES),
                    "additionalProperties": False,
                },
            ],
        },
        {},
        {},
        "Retention literal per copied snapshot family; {} confirms nothing and TENANT_SNAPSHOT "
        "refuses until counsel confirms all five (ruling Q-4).",
        "F-SNP SNP-1 slice I-5; D-98 cand. 25 Q-4",
    ),
)
# 04 T-PLT-31 platform parameter table, in table order, keyed by code.
PLATFORM_PARAMETERS: Final[Mapping[str, RegistryParameterSpec]] = MappingProxyType(
    {spec.code: spec for spec in _SPECS}
)
