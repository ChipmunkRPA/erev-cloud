"""Pydantic models of stored JSON documents (dev-guide DG-API; 04 T-CON-13, T-CON-19; BUILD_SPEC
CTR-7, CTR-12).

``JudgementQuestionnaire`` validates the T-CON-19 ``questionnaire`` of a judgement record per topic
(04 "Questionnaire schemas by topic"; ENGINE_SPEC Table 0.4-A; ENGINE_SPEC_B OQ-B-04). Booleans are
JSON booleans, dates ``YYYY-MM-DD`` strings and rates and amounts decimal strings (API-C-06).
Members a schema does not list are kept as evidence and never read by the engine, so every model
allows extra members. The records are validated at insert, update and submission.

``EstimateParameters`` validates the T-CON-13 ``parameters`` of an estimate version per estimate
kind (04 "Parameter schemas by estimate kind", rev 1.2; 05 OQ-ARC-03): JSON Schema 2020-12 objects
with ``additionalProperties: false``, non-negative decimal strings and ``YYYY-MM-DD`` dates. A kind
whose schema lists no property accepts ``{}`` only. Versions are validated at insert, update and
submission; ``EstimateParameters.json_schema`` exports each kind's schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Annotated, Any, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictStr,
    StringConstraints,
    ValidationError,
    model_validator,
)

from erev_api.enums import (
    Distinctness,
    EstimateKind,
    JudgementTopic,
    LicenceNature,
    PrincipalAgent,
    WarrantyType,
)
from erev_api.money import DecimalStr

__all__ = [
    "ESTIMATE_PARAMETERS",
    "QUESTIONNAIRES",
    "STEP1_CRITERIA",
    "EstimateParameters",
    "JudgementQuestionnaire",
    "Step1Criteria",
    "ValidationError",
]


class _Questionnaire(BaseModel):
    """Base of the per-topic schemas: unlisted members are evidence (T-CON-19)."""

    model_config = ConfigDict(extra="allow", frozen=True)


class EvidenceQuestionnaire(_Questionnaire):
    """``COMBINATION``, ``MODIFICATION_TREATMENT_OVERRIDE``, ``SSP_OVERRIDE`` and
    ``ESTIMATE_VS_ERROR``: no member is read or required."""


# 04 T-CON-19 "Step 1 criteria" (rev 1.150; supervisor rulings R-113 (f), R-115 (f)): the
# criteria of 606-10-25-1 (a) to (e) as a Step 1 review answers them.
STEP1_CRITERIA: Final = ("a", "b", "c", "d", "e")
YesNo = Literal["YES", "NO"]


class Step1Criteria(BaseModel):
    """``questionnaire.criteria`` of a record that serves Step 1: the keys a to e, each YES or
    NO, and no other key. A key that is absent — or null, which is not stored — is not answered
    yet: a draft may be partial; ``policies.judgements`` asks for all five at submission and
    holds (e) to the topic and (d) to the contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    a: YesNo | None = None
    b: YesNo | None = None
    c: YesNo | None = None
    d: YesNo | None = None
    e: YesNo | None = None


class CollectibilityQuestionnaire(_Questionnaire):
    """``COLLECTIBILITY``: the record is evidence — the ``COLLECTIBILITY_ASSESSED`` payload
    decides in the engine — and carries the Step 1 criteria the platform reads."""

    criteria: Step1Criteria | None = None


class NotAContractQuestionnaire(_Questionnaire):
    consideration_nonrefundable: StrictBool
    event_c_met_on: date | None = None
    criteria: Step1Criteria | None = None


class ContractTermQuestionnaire(_Questionnaire):
    enforceable_end_date: date
    termination_penalty_substantive: StrictBool


class PobDistinctOverrideQuestionnaire(_Questionnaire):
    obligation_key: StrictStr
    distinctness: Distinctness
    integrates_into_obligation_key: StrictStr | None = None


class SeriesClassificationQuestionnaire(_Questionnaire):
    obligation_key: StrictStr
    series_increment_unit: Literal["day", "month", "transaction", "unit"]


class PrincipalAgentQuestionnaire(_Questionnaire):
    product_code: StrictStr | None = None
    obligation_key: StrictStr | None = None
    conclusion: PrincipalAgent
    gross_to_net_basis: Literal["COMMISSION_RATE", "FIXED_FEE", "SUPPLIER_COST"] | None = None
    rate: DecimalStr | None = None
    amount: DecimalStr | None = None

    @model_validator(mode="after")
    def _agent_basis(self) -> Self:
        if (self.product_code is None) == (self.obligation_key is None):
            raise ValueError("Send exactly one of product_code and obligation_key.")
        if self.conclusion is PrincipalAgent.AGENT:
            if self.gross_to_net_basis is None:
                raise ValueError("An agent conclusion names gross_to_net_basis.")
            if self.gross_to_net_basis == "COMMISSION_RATE" and self.rate is None:
                raise ValueError("A commission rate basis names rate.")
            if self.gross_to_net_basis != "COMMISSION_RATE" and self.amount is None:
                raise ValueError("A fixed fee or supplier cost basis names amount.")
        return self


class LicenceNatureQuestionnaire(_Questionnaire):
    """04 T-CON-19 ``LICENCE_NATURE`` (rev 1.11; D-91 gaps (viii)): the IFRS15 activities flag and
    the two ASC606 606-10-55-62 criteria, answered together and for ``FUNCTIONAL`` IP only."""

    obligation_key: StrictStr
    nature: LicenceNature
    activities_significantly_affect_ip: StrictBool | None = None  # IFRS15 book
    functionality_expected_to_change_substantively: StrictBool | None = None  # 55-62(a), ASC606
    customer_required_to_use_updated_ip: StrictBool | None = None  # 55-62(b), ASC606

    @model_validator(mode="after")
    def _criteria_55_62(self) -> Self:
        first = self.functionality_expected_to_change_substantively
        second = self.customer_required_to_use_updated_ip
        if (first is None) != (second is None):
            raise ValueError(
                "The 606-10-55-62 criteria are answered together: send both "
                "functionality_expected_to_change_substantively and "
                "customer_required_to_use_updated_ip, or neither."
            )
        if first is not None and self.nature is not LicenceNature.FUNCTIONAL:
            raise ValueError(
                "The 606-10-55-62 criteria apply to FUNCTIONAL intellectual property only."
            )
        return self


class WarrantyTypeQuestionnaire(_Questionnaire):
    obligation_key: StrictStr
    warranty_type: WarrantyType


class SfcAssessmentQuestionnaire(_Questionnaire):
    obligation_key: StrictStr  # "" names the contract
    significant: StrictBool
    exception_32_17: Literal["A", "B", "C", "NONE"]


class ConstraintQuestionnaire(_Questionnaire):
    estimate_key: StrictStr
    remote: StrictBool


class RepurchaseClassificationQuestionnaire(_Questionnaire):
    obligation_key: StrictStr
    outcome: Literal["FINANCING", "LEASE", "RIGHT_OF_RETURN", "SALE"]


class BillAndHoldQuestionnaire(_Questionnaire):
    obligation_key: StrictStr
    reason_substantive: StrictBool
    identified_as_customer_product: StrictBool
    ready_for_physical_transfer: StrictBool
    cannot_use_or_direct_to_another_customer: StrictBool


class OtherQuestionnaire(_Questionnaire):
    pol_044_override: StrictBool | None = None
    claim_enforceable: StrictBool | None = None
    returns_immaterial: StrictBool | None = None
    estimate_key: StrictStr | None = None
    obligation_key: StrictStr | None = None
    discount_exception_bundle: StrictStr | None = None

    @model_validator(mode="after")
    def _keys_named(self) -> Self:
        estimate_flags = (self.pol_044_override, self.claim_enforceable)
        if any(flag is not None for flag in estimate_flags) and self.estimate_key is None:
            raise ValueError("pol_044_override and claim_enforceable come with estimate_key.")
        if self.returns_immaterial is not None and self.obligation_key is None:
            raise ValueError("returns_immaterial comes with obligation_key.")
        return self


QUESTIONNAIRES: Final[Mapping[JudgementTopic, type[_Questionnaire]]] = MappingProxyType(
    {
        JudgementTopic.COLLECTIBILITY: CollectibilityQuestionnaire,
        JudgementTopic.NOT_A_CONTRACT: NotAContractQuestionnaire,
        JudgementTopic.CONTRACT_TERM: ContractTermQuestionnaire,
        JudgementTopic.COMBINATION: EvidenceQuestionnaire,
        JudgementTopic.POB_DISTINCT_OVERRIDE: PobDistinctOverrideQuestionnaire,
        JudgementTopic.SERIES_CLASSIFICATION: SeriesClassificationQuestionnaire,
        JudgementTopic.PRINCIPAL_AGENT: PrincipalAgentQuestionnaire,
        JudgementTopic.LICENCE_NATURE: LicenceNatureQuestionnaire,
        JudgementTopic.WARRANTY_TYPE: WarrantyTypeQuestionnaire,
        JudgementTopic.CONSTRAINT: ConstraintQuestionnaire,
        JudgementTopic.SFC_ASSESSMENT: SfcAssessmentQuestionnaire,
        JudgementTopic.MODIFICATION_TREATMENT_OVERRIDE: EvidenceQuestionnaire,
        JudgementTopic.SSP_OVERRIDE: EvidenceQuestionnaire,
        JudgementTopic.REPURCHASE_CLASSIFICATION: RepurchaseClassificationQuestionnaire,
        JudgementTopic.ESTIMATE_VS_ERROR: EvidenceQuestionnaire,
        JudgementTopic.OTHER: OtherQuestionnaire,
        JudgementTopic.BILL_AND_HOLD: BillAndHoldQuestionnaire,
    }
)


class JudgementQuestionnaire:
    """The per-topic union of T-CON-19 questionnaire schemas."""

    @staticmethod
    def validate(topic: JudgementTopic, value: Mapping[str, Any] | None) -> dict[str, Any]:
        """The questionnaire as stored (dates ISO strings); ``ValidationError`` when it fails the
        topic's schema. A missing questionnaire validates as ``{}``."""
        model = QUESTIONNAIRES[JudgementTopic(topic)]
        validated = model.model_validate(dict(value or {}))
        dumped: dict[str, Any] = validated.model_dump(mode="json", exclude_none=True)
        return dumped


# --- T-CON-13 estimate version parameters (CTR-12) ------------------------------------------------

# 04 T-CON-13: "Decimal values are strings matching ^[0-9]+(\\.[0-9]+)?$ (non-negative; D-11)".
NonNegativeDecimal = Annotated[str, StringConstraints(pattern=r"^[0-9]+(\.[0-9]+)?$")]


class _Parameters(BaseModel):
    """Base of the per-kind schemas: ``additionalProperties: false`` (04 T-CON-13)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NoParameters(_Parameters):
    """``BREAKAGE``, ``EXERCISE_LIKELIHOOD``, ``IMPLICIT_PRICE_CONCESSION``,
    ``RENEWAL_EXPECTATION`` and ``EXPECTED_PURCHASES``: their measurements live in the columns."""


class ReturnRateParameters(_Parameters):
    carrying_cost_per_unit: NonNegativeDecimal
    recovery_cost_per_unit: NonNegativeDecimal
    window_end_date: date


class VariableConsiderationParameters(_Parameters):
    no_change_attestation: StrictBool = False
    refund_liability_target: NonNegativeDecimal | None = None


class RoyaltyAccrualParameters(_Parameters):
    usage_period_start_date: date
    usage_period_end_date: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.usage_period_end_date < self.usage_period_start_date:
            raise ValueError("usage_period_end_date must not be before usage_period_start_date.")
        return self


class EacParameters(_Parameters):
    uninstalled_materials_cost: NonNegativeDecimal | None = None


class ShareBasedConsiderationParameters(_Parameters):
    grant_date: date
    grant_date_fair_value: NonNegativeDecimal
    vesting_probable: StrictBool
    expected_forfeiture_ratio: NonNegativeDecimal | None = None

    @model_validator(mode="after")
    def _ratio(self) -> Self:
        ratio = self.expected_forfeiture_ratio
        if ratio is not None and _above_one(ratio):
            raise ValueError("expected_forfeiture_ratio must not be above 1.")
        return self


def _above_one(value: str) -> bool:
    """Whether a non-negative decimal string exceeds 1, compared without floats."""
    whole, _, fraction = value.partition(".")
    return int(whole) > 1 or (int(whole) == 1 and fraction.strip("0") != "")


ESTIMATE_PARAMETERS: Final[Mapping[EstimateKind, type[_Parameters]]] = MappingProxyType(
    {
        EstimateKind.VARIABLE_CONSIDERATION: VariableConsiderationParameters,
        EstimateKind.RETURN_RATE: ReturnRateParameters,
        EstimateKind.BREAKAGE: NoParameters,
        EstimateKind.EAC: EacParameters,
        EstimateKind.EXERCISE_LIKELIHOOD: NoParameters,
        EstimateKind.IMPLICIT_PRICE_CONCESSION: NoParameters,
        EstimateKind.RENEWAL_EXPECTATION: NoParameters,
        EstimateKind.ROYALTY_ACCRUAL: RoyaltyAccrualParameters,
        EstimateKind.EXPECTED_PURCHASES: NoParameters,
        EstimateKind.SHARE_BASED_CONSIDERATION: ShareBasedConsiderationParameters,
    }
)


class EstimateParameters:
    """The discriminated union of T-CON-13 parameter schemas, keyed on
    ``estimate.estimate_kind``."""

    @staticmethod
    def validate(kind: EstimateKind, value: Mapping[str, Any] | None) -> dict[str, Any]:
        """The parameters as stored (dates ISO strings, members sent only); ``ValidationError`` when
        they fail the kind's schema. Missing parameters validate as ``{}``."""
        model = ESTIMATE_PARAMETERS[EstimateKind(kind)]
        validated = model.model_validate(dict(value or {}))
        dumped: dict[str, Any] = validated.model_dump(mode="json", exclude_unset=True)
        return dumped

    @staticmethod
    def json_schema(kind: EstimateKind) -> dict[str, Any]:
        """The kind's exported JSON Schema (04 T-CON-13 table)."""
        schema: dict[str, Any] = ESTIMATE_PARAMETERS[EstimateKind(kind)].model_json_schema()
        return schema
