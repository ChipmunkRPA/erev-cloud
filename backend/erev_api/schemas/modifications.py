"""API-S-Modification (04 §16.14 rev 1.70; API-R-31; BUILD_SPEC CTR-17; D-98 140).

The T-CON-06 columns as fields plus ``impact_preview`` (API-S-ImpactSummary of the latest stored
preview, or null), ``approver`` / ``approved_at`` and the row's stored classification — its three
members ``prefill_reasons``, ``proposal_detail`` and ``price_tests`` (rev 1.210, 1.250, 1.286).
List items omit ``lines``, ``questionnaire`` and ``impact_preview`` and add ``impact_summary``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import (
    ConfigStatus,
    EstimateKind,
    ModificationKind,
    ModificationStatus,
    ModificationTreatment,
)
from erev_api.events.payloads import (
    ConsiderationPayableV1,
    ModificationLineV1,
    NoncashConsiderationV1,
    SspBasisV1,
)
from erev_api.money import DecimalStr, MoneyOut
from erev_api.schemas.common import ActorOut
from erev_api.schemas.events import ImpactSummaryOut

__all__ = [
    "RegroupIn",
    "RegroupOut",
    "LinkedEstimateVersionOut",
    "ModificationCreateIn",
    "ModificationImpactOut",
    "ModificationListItemOut",
    "ModificationOut",
    "ModificationSubmitIn",
    "ModificationUpdateIn",
    "ModificationWithdrawIn",
]

QUESTION_KEYS = (
    "added_goods_distinct",
    "priced_at_ssp",
    "remaining_goods_distinct_from_transferred",
)


class ModificationCreateIn(BaseModel):
    """``POST /contracts/{id}/modifications``: the authored T-CON-06 members of a DRAFT."""

    model_config = ConfigDict(extra="forbid")

    effective_date: date
    kind: ModificationKind
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    lines: tuple[ModificationLineV1, ...] = Field(min_length=1, max_length=500)
    # obligation key → {added_goods_distinct, priced_at_ssp,
    # remaining_goods_distinct_from_transferred} (booleans, or absent) plus the contract-level
    # member ``price_change_settlement``.
    questionnaire: dict[str, Any] = Field(default_factory=dict)
    price_change_amount: DecimalStr | None = None
    noncash_consideration: tuple[NoncashConsiderationV1, ...] | None = Field(
        default=None, max_length=50
    )
    consideration_payable: tuple[ConsiderationPayableV1, ...] | None = Field(
        default=None, max_length=50
    )
    scope_605_35: bool | None = None
    chosen_treatments: dict[str, ModificationTreatment] = Field(default_factory=dict)
    ssp_basis: dict[str, SspBasisV1] = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)
    judgement_record_id: uuid.UUID | None = None


class ModificationUpdateIn(BaseModel):
    """``PATCH /modifications/{id}``: every member optional. A member that is left out leaves the
    stored value; a nullable authored member sent as null — ``reference``,
    ``price_change_amount``, ``noncash_consideration``, ``consideration_payable``,
    ``scope_605_35``, ``rationale``, ``judgement_record_id`` — is cleared (04 §16.14 rev 1.188;
    item MOD-PATCH-CLEAR-1); null for any other member leaves the stored value."""

    model_config = ConfigDict(extra="forbid")

    effective_date: date | None = None
    kind: ModificationKind | None = None
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    lines: tuple[ModificationLineV1, ...] | None = Field(default=None, min_length=1, max_length=500)
    questionnaire: dict[str, Any] | None = None
    price_change_amount: DecimalStr | None = None
    noncash_consideration: tuple[NoncashConsiderationV1, ...] | None = Field(
        default=None, max_length=50
    )
    consideration_payable: tuple[ConsiderationPayableV1, ...] | None = Field(
        default=None, max_length=50
    )
    scope_605_35: bool | None = None
    chosen_treatments: dict[str, ModificationTreatment] | None = None
    ssp_basis: dict[str, SspBasisV1] | None = None
    rationale: str | None = Field(default=None, max_length=4000)
    judgement_record_id: uuid.UUID | None = None


class ModificationSubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=4000)


class ModificationWithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=1, max_length=4000)


class ModificationImpactOut(BaseModel):
    """The list item's ``impact_summary`` (04 §16.14): the stored preview's catch-up total."""

    catch_up_total: MoneyOut | None


class ModificationListItemOut(BaseModel):
    id: uuid.UUID
    modification_no: str
    contract_id: uuid.UUID
    contracting_entity_id: uuid.UUID
    effective_date: date
    kind: ModificationKind
    template_mode: str | None
    status: ModificationStatus
    reference: str | None
    currency: str
    proposed_treatments: dict[str, str]
    chosen_treatments: dict[str, str]
    treatment_summary: ModificationTreatment | None
    rationale: str | None
    judgement_record_id: uuid.UUID | None
    impact_preview_sha256: str | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    applied_event_id: uuid.UUID | None
    regroup_id: uuid.UUID | None
    impact_summary: ModificationImpactOut
    preparer: ActorOut
    approver: ActorOut | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class LinkedEstimateVersionOut(BaseModel):
    """One estimate version created inside the modification (04 §16.14 rev 1.210; T-CON-13
    ``modification_id``; PRD BR-MOD-02); its figures are read from the version itself."""

    id: uuid.UUID
    estimate_id: uuid.UUID
    element_code: str
    estimate_kind: EstimateKind
    version_no: int
    status: ConfigStatus
    effective_date: date


class ModificationOut(ModificationListItemOut):
    """API-S-Modification: the list item plus the authored detail and the stored preview."""

    lines: list[dict[str, Any]]
    questionnaire: dict[str, Any]
    price_change_amount: str | None
    noncash_consideration: list[dict[str, Any]] | None
    consideration_payable: list[dict[str, Any]] | None
    scope_605_35: bool | None
    ssp_basis: dict[str, Any]
    impact_preview_file_id: uuid.UUID | None
    impact_preview: ImpactSummaryOut | None
    # 04 §16.10 "Who reads a stored preview" (rev 1.300; item MOD-PREVIEW-READ-SCOPE-1): true
    # when the row stores a preview this caller is not answered — ``impact_preview`` and
    # ``impact_preview_file_id`` are then null — so that a screen tells it from "no preview yet".
    impact_preview_withheld: bool = False
    # What the latest ``POST /modifications/{id}/classify`` answered (04 T-CON-06
    # ``classification``, §16.14 rev 1.210): obligation key → question → {value, reason_key,
    # params} — the BR-MOD-01 answers the system can compute, never stored as answers. Every key
    # is an obligation key (rev 1.286; item MOD-CLASSIFICATION-KEYS-1); ``{}`` for a row that is
    # not classified or was edited since, and for one classified before that revision. The
    # answer of ``/classify`` alone also shows them in ``questionnaire`` beside the stored ones.
    prefill_reasons: dict[str, Any] = Field(default_factory=dict)
    # The engine's proposal detail of that classification (CV-16: ``class[<key>]``,
    # ``modification_key``, ``ssp_version[<key>]``), a member of its own since rev 1.286 — before
    # it lay in ``prefill_reasons`` under the key ``proposal``, where an obligation of that name
    # met it. Never empty for a classified row; ``{}`` wherever ``prefill_reasons`` is ``{}``
    # for the reasons named there.
    proposal_detail: dict[str, Any] = Field(default_factory=dict)
    # The engine's price test of each added line as that classification read it, whatever the
    # preparer answered (04 §16.14 rev 1.250; item MOD-PRICE-TEST-FACT-1): obligation key →
    # {value, reason_key, params}. A fact, never a proposal: it is not under ``prefill_reasons``.
    # An added line the engine does not test has no entry; ``{}`` for a row that is not
    # classified or was edited since.
    price_tests: dict[str, Any] = Field(default_factory=dict)
    # The estimate versions whose ``modification_id`` names the row, by element code and version
    # number (04 §16.14 rev 1.210; item MOD-LINKED-ESTIMATES-1). They are approved before the
    # modification is submitted (PRD ERR-87).
    linked_estimate_versions: list[LinkedEstimateVersionOut] = Field(default_factory=list)


class RegroupIn(BaseModel):
    """``POST /contracts/{id}/regroup`` (04 §16.1; REQ-CON-012): the obligations to move, the
    target (a new contract when absent) and the preparer's comment."""

    model_config = ConfigDict(extra="forbid")

    obligation_keys: list[str] = Field(min_length=1, max_length=500)
    target_contract_id: uuid.UUID | None = None
    comment: str = Field(min_length=1, max_length=4000)


class RegroupOut(BaseModel):
    """201 ``{modification_ids}``: the REMOVE row of the source and the ADD row of the target."""

    modification_ids: list[uuid.UUID]
