"""API-R-25 rule set and API-R-57 configuration test case schemas (04 §15.3 API-R-25, API-R-57,
T-REF-24 to T-REF-27, §16.2 API-S-VersionSummary and API-S-SimulationSummary, §16.14 list additions;
SCREENS §11.1 decision-table editor; BUILD_SPEC RFD-4, RFD-5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import ConfigStatus, RuleSetKind
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

CODE_LENGTH: Final = 128  # TY-06
CODE_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9 _.:/#()+-]{0,127}$"  # TY-06 erev.code
FIELD_LENGTH: Final = 100
OPERATOR_LENGTH: Final = 20
MAX_CONDITIONS: Final = 50
PRIORITY_MIN: Final = -2_147_483_648  # T-REF-26 `priority integer`
PRIORITY_MAX: Final = 2_147_483_647

LintStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE"]
CaseResult = Literal["PASS", "FAIL"]
# 04 T-REF-27 `ck_rule_test_case__subject_type`.
ConfigSubjectType = Literal[
    "rule_set_version", "pob_template_version", "account_mapping_version", "registry_version"
]


class RuleSetIn(BaseModel):
    """``POST /rule-sets``: a decision table of one E-55 kind; ``name`` defaults to the code."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH, pattern=CODE_PATTERN)
    kind: RuleSetKind
    name: str | None = Field(default=None, min_length=1, max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)


class VersionSummaryOut(BaseModel):
    """API-S-VersionSummary (04 §16.2; SCREENS R-29). ``published_at`` since 04 rev 1.183: a
    version published without an effective instant takes effect at its publication, so a list
    can say from when."""

    id: uuid.UUID
    version_no: int
    status: ConfigStatus
    effective_from: datetime | None
    published_at: datetime | None
    rule_count: int | None
    lint_status: LintStatus | None


class RuleSetOut(BaseModel):
    """API-S-RuleSet: the T-REF-24 columns with ``current_version`` (the latest PUBLISHED version)
    and ``latest_version`` (the highest ``version_no``)."""

    id: uuid.UUID
    code: str
    name: str
    kind: RuleSetKind
    description: str | None
    current_version: VersionSummaryOut | None
    latest_version: VersionSummaryOut | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class RuleSetVersionIn(BaseModel):
    """``POST /rule-sets/{id}/versions``: the next version as DRAFT; ``source_version_id`` copies
    the rules and example cases of that version of the set."""

    model_config = ConfigDict(extra="forbid")

    effective_from: AwareDatetime | None = None
    source_version_id: uuid.UUID | None = None


class RuleSetVersionUpdateIn(BaseModel):
    """``PATCH /rule-set-versions/{id}`` with ``If-Match`` while the version is DRAFT or TESTED."""

    model_config = ConfigDict(extra="forbid")

    effective_from: AwareDatetime | None = None


class LintFindingOut(BaseModel):
    """One lint finding: two rules that tie on specificity and priority (REQ-POL-002)."""

    rule_id: str
    severity: Literal["ERROR"]
    rule_keys: list[str]
    message: str


class LintResultOut(BaseModel):
    """T-REF-25 ``lint_result``."""

    status: Literal["PASS", "FAIL"]
    findings: list[LintFindingOut]
    linted_at: datetime


class CaseEvidenceOut(BaseModel):
    """``test_evidence``: the example cases of the version by last result (REQ-POL-003)."""

    total: int
    passed: int
    failed: int
    not_run: int
    last_run_at: datetime | None


class SimulationSummaryOut(BaseModel):
    """API-S-SimulationSummary (04 §16.2; SCREENS R-31) with the report's ``statement``."""

    contracts_affected: int
    revenue_delta_by_period: list[dict[str, Any]]
    balance_delta: list[dict[str, Any]]
    journal_delta: list[dict[str, Any]]
    statement: str


class ImpactSimulationOut(BaseModel):
    file_id: uuid.UUID
    summary: SimulationSummaryOut


class RuleSetVersionOut(BaseModel):
    """API-S-RuleSetVersion: the T-REF-25 and SC-V columns with the set's code, rule count, test
    evidence, simulation report and pending approval request."""

    id: uuid.UUID
    rule_set_id: uuid.UUID
    rule_set_code: str
    kind: RuleSetKind
    version_no: int
    status: ConfigStatus
    effective_from: datetime | None
    effective_to: datetime | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    pending_approval_request_id: uuid.UUID | None
    published_at: datetime | None
    published_by: uuid.UUID | None
    supersedes_version_id: uuid.UUID | None
    rule_count: int
    lint_result: LintResultOut | None
    test_evidence: CaseEvidenceOut
    impact_simulation: ImpactSimulationOut | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class RuleSetVersionSubmitIn(BaseModel):
    """``POST /rule-set-versions/{id}/submit``."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class ConditionIn(BaseModel):
    """One T-REF-26 condition; ``field`` and ``op`` follow ``erev_engine.rules``, and decimal
    values travel as text (API-C-06)."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(max_length=FIELD_LENGTH)
    op: str = Field(max_length=OPERATOR_LENGTH)
    value: Any


class RuleIn(BaseModel):
    """``POST /rule-set-versions/{id}/rules``: creates the rule, or replaces the rule with the same
    ``rule_key``, while the version is DRAFT or TESTED."""

    model_config = ConfigDict(extra="forbid")

    rule_key: str = Field(max_length=CODE_LENGTH, pattern=CODE_PATTERN)
    priority: int = Field(default=0, ge=PRIORITY_MIN, le=PRIORITY_MAX)
    conditions: list[ConditionIn] = Field(max_length=MAX_CONDITIONS)
    outputs: dict[str, Any]
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)


class RuleOut(BaseModel):
    """API-S-Rule: a T-REF-26 row; ``specificity`` counts the distinct condition fields."""

    id: uuid.UUID
    rule_set_version_id: uuid.UUID
    rule_key: str
    priority: int
    specificity: int
    conditions: list[dict[str, Any]]
    outputs: dict[str, Any]
    description: str | None


class RuleSetEvaluateIn(BaseModel):
    """``POST /rule-sets/{id}/evaluate``: facts named by ``erev_engine.rules.FIELDS``, evaluated
    against ``version_id`` or else the PUBLISHED version in force at ``at`` (default now)."""

    model_config = ConfigDict(extra="forbid")

    facts: dict[str, Any]
    version_id: uuid.UUID | None = None
    at: AwareDatetime | None = None


class RuleSetEvaluationOut(BaseModel):
    """The winning rule, or ``matched = false`` with null members when no rule matches."""

    matched: bool
    rule_key: str | None
    rule_id: uuid.UUID | None
    rule_set_version_id: uuid.UUID | None
    specificity: int | None
    priority: int | None
    outputs: dict[str, Any] | None


class RuleTestCaseIn(BaseModel):
    """``POST /rule-set-versions/{id}/test-cases``: facts in ``input``; ``expected_output`` names
    the expected evaluation through ``matched``, ``rule_key`` or ``outputs``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=LABEL_LENGTH)
    input: dict[str, Any]
    expected_output: dict[str, Any]


class ConfigTestCaseIn(RuleTestCaseIn):
    """``POST /config-test-cases``: an example case of any configuration version (API-R-57)."""

    subject_type: ConfigSubjectType
    subject_id: uuid.UUID


class ConfigTestCaseUpdateIn(BaseModel):
    """``PATCH /config-test-cases/{id}`` with ``If-Match``; the last result is cleared."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=LABEL_LENGTH)
    input: dict[str, Any] | None = None
    expected_output: dict[str, Any] | None = None


class ConfigTestCaseOut(BaseModel):
    """API-S-ConfigTestCase: a T-REF-27 row."""

    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    name: str
    input: dict[str, Any]
    expected_output: dict[str, Any]
    last_result: CaseResult | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    row_version: int
