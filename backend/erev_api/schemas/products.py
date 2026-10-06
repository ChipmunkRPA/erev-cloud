"""API-R-23 product and bundle schemas (04 §15.3 API-R-23, T-REF-20, T-REF-21, E-89, E-105,
API-C-06; SCREENS §10.3 to §10.5; BUILD_SPEC RFD-9).

04 §16 defines no product schema. A product follows the T-REF-20 columns plus
``pending_approval_request_id`` (the PENDING ``PRINCIPAL_AGENT_CHANGE`` request, SCREENS §10.5),
``usability`` (REQ-REF-012), ``created_at``, ``updated_at`` and ``row_version`` (L2-1-Q-13).
Decimals travel as API-C-06 strings. ``PUT /products/{id}/bundle-components`` sends every
component row of the bundle and answers with the stored rows, whose ``valid_to`` the server derives
(L2-1-Q-17).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import Distinctness, PrincipalAgent
from erev_api.money import DecimalStr
from erev_api.schemas.common import RefOut
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

TEXT_LENGTH: Final = 255
MAX_COMPONENTS: Final = 200  # [J] rows per bundle in one PUT (API-C-17)
SplitBasis = Literal["relative_ssp", "fixed_percentage"]


class ProductIn(BaseModel):
    """``POST /products``: a T-REF-20 product."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH, description="Legacy SKU Name (LM-SSP-02)")
    sku_number: str | None = Field(
        default=None, max_length=TEXT_LENGTH, description="Legacy SKU Unique ID (LM-SSP-01)"
    )
    name: str = Field(max_length=LABEL_LENGTH)
    product_family: str | None = Field(default=None, max_length=LABEL_LENGTH)
    revenue_category: str | None = Field(default=None, max_length=CODE_LENGTH)
    default_pob_template_id: uuid.UUID | None = None
    disaggregation: dict[str, str] = Field(
        default_factory=dict, description="Attribute code → value (REQ-REF-012)"
    )
    principal_agent: PrincipalAgent = Field(
        default=PrincipalAgent.NOT_ASSESSED,
        description="The initial conclusion; later changes need approval (REQ-REF-012)",
    )
    distinctness_default: Distinctness = Distinctness.DISTINCT
    unit_of_measure: str = Field(default="EA", max_length=CODE_LENGTH)
    is_bundle: bool = False
    assurance_cost_per_unit: DecimalStr | None = Field(
        default=None, description="Expected assurance-warranty cost per unit; null = no accrual"
    )
    is_franchisor_preopening_service: bool = False
    policy_values: dict[str, Any] = Field(
        default_factory=dict, description="Level P policy values (POLICIES §0.5)"
    )
    is_active: bool = True


class ProductUpdateIn(BaseModel):
    """``PATCH /products/{id}``: the members sent replace the stored values. A changed
    ``principal_agent`` is refused: it changes through ``propose-principal-agent-change``."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=CODE_LENGTH)
    sku_number: str | None = Field(default=None, max_length=TEXT_LENGTH)
    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    product_family: str | None = Field(default=None, max_length=LABEL_LENGTH)
    revenue_category: str | None = Field(default=None, max_length=CODE_LENGTH)
    default_pob_template_id: uuid.UUID | None = None
    disaggregation: dict[str, str] | None = None
    principal_agent: PrincipalAgent | None = None
    distinctness_default: Distinctness | None = None
    unit_of_measure: str | None = Field(default=None, max_length=CODE_LENGTH)
    is_bundle: bool | None = None
    assurance_cost_per_unit: DecimalStr | None = None
    is_franchisor_preopening_service: bool | None = None
    policy_values: dict[str, Any] | None = None
    is_active: bool | None = None


class UsabilityOut(BaseModel):
    """Whether contracts may use the product (REQ-REF-012)."""

    usable: bool
    missing: list[str] = Field(description="Mandatory disaggregation attributes without a value")


class ProductOut(BaseModel):
    """A T-REF-20 product (L2-1-Q-13)."""

    id: uuid.UUID
    code: str
    sku_number: str | None
    name: str
    product_family: str | None
    revenue_category: str | None
    default_pob_template_id: uuid.UUID | None
    disaggregation: dict[str, Any]
    principal_agent: PrincipalAgent
    distinctness_default: Distinctness
    unit_of_measure: str
    is_bundle: bool
    assurance_cost_per_unit: str | None
    is_franchisor_preopening_service: bool
    policy_values: dict[str, Any]
    is_active: bool
    pending_approval_request_id: uuid.UUID | None = Field(
        description=(
            "The PENDING PRINCIPAL_AGENT_CHANGE request of the product: a proposed conclusion or"
            " proposed policy values"
        )
    )
    requires_explicit_ssp_basis: bool = Field(
        description=(
            "Derived, read-only: the product's default POB template has a version of series"
            " distinctness, so its SSP entries send an explicit value_basis (and quantity_unit when"
            " PER_INCREMENT) — the same predicate the entry admission guard applies (D-97 (3a);"
            " SSP-ADMISSION-R1)."
        )
    )
    code_frozen: bool = Field(
        description=(
            "Derived, read-only: a contract line, an SSP entry or an account mapping rule"
            " references the product, so PATCH refuses a changed code with rule DB-05 — the same"
            " predicate that refusal applies (04 DB-05; item PRODUCT-CODE-FREEZE-1)."
        )
    )
    usability: UsabilityOut
    created_at: datetime
    updated_at: datetime
    row_version: int


class PrincipalAgentChangeIn(BaseModel):
    """``POST /products/{id}/propose-principal-agent-change``: the proposed conclusion."""

    model_config = ConfigDict(extra="forbid")

    principal_agent: PrincipalAgent
    rationale: str = Field(max_length=MEMO_LENGTH)


class PrincipalAgentChangeOut(BaseModel):
    """The ``PRINCIPAL_AGENT_CHANGE`` request the proposal opened (API-R-09)."""

    approval_request_id: uuid.UUID


class PolicyValuesChangeIn(BaseModel):
    """``POST /products/{id}/propose-policy-values-change``: the whole proposed level-P map of the
    product (POL key → value) and the rationale (04 API-R-23 rev 1.110)."""

    model_config = ConfigDict(extra="forbid")

    policy_values: dict[str, Any]
    rationale: str = Field(max_length=MEMO_LENGTH)


class PolicyValuesChangeOut(BaseModel):
    """The ``PRINCIPAL_AGENT_CHANGE`` request the proposal opened (API-R-09)."""

    approval_request_id: uuid.UUID


class BundleComponentIn(BaseModel):
    """One T-REF-21 component row of a bundle."""

    model_config = ConfigDict(extra="forbid")

    component_product_id: uuid.UUID
    quantity_per_bundle: DecimalStr = "1"
    split_basis: SplitBasis = "relative_ssp"
    split_ratio: DecimalStr | None = Field(
        default=None, description="Required for fixed_percentage; above 0 and at most 1"
    )
    sequence: int = Field(ge=1, le=99, description="Order of the component in its set")
    valid_from: date
    valid_to: date | None = None


class BundleComponentsIn(BaseModel):
    """``PUT /products/{id}/bundle-components``: every component row of the bundle."""

    model_config = ConfigDict(extra="forbid")

    components: list[BundleComponentIn] = Field(max_length=MAX_COMPONENTS)


class BundleComponentOut(BaseModel):
    """A stored T-REF-21 row with its component as API-S-Ref."""

    id: uuid.UUID
    component_product_id: uuid.UUID
    component_product: RefOut
    quantity_per_bundle: str
    split_basis: SplitBasis
    split_ratio: str | None
    sequence: int
    valid_from: date
    valid_to: date | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class BundleComponentsOut(BaseModel):
    """The component rows of a bundle in ``valid_from``, then ``sequence`` order."""

    bundle_product_id: uuid.UUID
    components: list[BundleComponentOut]
