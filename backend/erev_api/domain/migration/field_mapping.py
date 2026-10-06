"""Legacy field mapping: ``Contract_Live`` → eRev (BUILD_SPEC LMG-2; 04 §17.2 LM-CL-01 to LM-CL-71;
POLICIES POL-211 to POL-214; 04 T-MIG-01 seeded parity templates; REQ-MIG-006; SCREENS_B §10.3
"Field mapping", "Entity mapping", "Batch parameters"; legacy 01 PAR-04).

``FIELD_MAPPING`` restates the 71 rows of 04 §17.2 as data (id, legacy column, target, rule) for
the read-only "Field mapping" table. ``map_row`` applies the rows that decide how a legacy
obligation is booked: ``ASC 606 Stratification`` is the revenue category, except that ``VC``
rows become transaction-price components (obligation kind ``VC_LINE``, template ``LEGACY-VC``;
POL-213); ``Distinct or Nondistinct`` maps to distinctness (LM-CL-18); ``Selling Entity`` names
the contracting and performing entity (LM-CL-09, created when absent); the three account columns
become account overrides (LM-CL-11, -12, -22: both asset roles map to the one Unbilled A/R
account under the parity preset, D-15); ``SSP Version`` is the SSP version label of book
``LEGACY-SKU-SSP`` (LM-CL-10); a row in the legacy material-right convention (unit list price 1,
discount 0, range 0, stated price 0, quantity = SSP dollars; legacy 01 PAR-04) takes template
``LEGACY-MATERIAL-RIGHT`` under POL-212 ``KEEP_QUANTITY_CONVENTION`` and, under
``CONVERT_TO_OPTION_RECORD``, becomes the option record (kind ``MATERIAL_RIGHT``, quantity 1, an
``OptionRecord`` with ``ssp_method`` ``ENTERED_AMOUNT`` and option SSP = legacy quantity × 1,
exercise per POL-028; POLICIES POL-212, ENGINE_SPEC S03-R-07, 04 T-CON-14); every other row
takes ``LEGACY-DISTINCT`` or, for a ``Nondistinct`` row, the POL-211 choice: ``SINGLE_POB`` one
``STANDARD`` obligation on ``LEGACY-NONDISTINCT``; ``SERIES`` a ``series`` row that stays
``pending`` until its ``series_increment_unit`` is known (S03-R-06); ``REVIEW_QUEUE`` a row
``pending`` the questionnaire before commit. A pending row is never booked silently
(``opening_balances.booking_payload`` refuses the contract). Batch parameters: POL-213 and
POL-214 are FORCED (``validate_batch_parameters`` refuses another value); POL-211 accepts its
three literals and POL-212 its two. Codex's review of ed5173f (finding R2) found the earlier
fall-through of the conversion choice to a plain line; corrected docs-first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal

from erev_api.domain.imports import legacy_templates as legacy
from erev_api.domain.migration import legacy_db
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.domain.reports import legacy_columns
from erev_api.problems import ProblemError

__all__ = [
    "BOOK_LEGACY_SKU_SSP",
    "FIELD_MAPPING",
    "FORCED_PARAMETERS",
    "LEGACY_DISTINCT",
    "LEGACY_MATERIAL_RIGHT",
    "LEGACY_NONDISTINCT",
    "LEGACY_VC",
    "LEGACY_VC_ROWS",
    "MATERIAL_RIGHT_CONVENTION",
    "MATERIAL_RIGHT_OPTIONS",
    "NONDISTINCT_MAPPING",
    "NONDISTINCT_OPTIONS",
    "SPLIT_UPLOAD_ALLOCATION",
    "VC",
    "BatchParameters",
    "EntityMapping",
    "FieldMapping",
    "MappedObligation",
    "OptionRecord",
    "PendingDecision",
    "entity_mapping",
    "is_material_right",
    "map_row",
    "validate_batch_parameters",
]

# Seeded parity templates (04 T-MIG-01 note; DIN-4 / DIN-5 seed them).
LEGACY_DISTINCT: Final = "LEGACY-DISTINCT"
LEGACY_NONDISTINCT: Final = "LEGACY-NONDISTINCT"
LEGACY_VC: Final = "LEGACY-VC"
LEGACY_MATERIAL_RIGHT: Final = "LEGACY-MATERIAL-RIGHT"
BOOK_LEGACY_SKU_SSP: Final = "LEGACY-SKU-SSP"  # LM-CL-10, LM-SSP-08
VC: Final = "VC"  # LM-CL-06 stratification of a transaction-price component
# POLICIES §1.13 import batch parameters.
NONDISTINCT_MAPPING: Final = "migration.nondistinct_mapping"  # POL-211
MATERIAL_RIGHT_CONVENTION: Final = "migration.material_right_convention"  # POL-212
LEGACY_VC_ROWS: Final = "migration.legacy_vc_rows"  # POL-213 FORCED
SPLIT_UPLOAD_ALLOCATION: Final = "migration.split_upload_allocation"  # POL-214 FORCED
NONDISTINCT_OPTIONS: Final = ("SINGLE_POB", "SERIES", "REVIEW_QUEUE")
MATERIAL_RIGHT_OPTIONS: Final = ("CONVERT_TO_OPTION_RECORD", "KEEP_QUANTITY_CONVENTION")
FORCED_PARAMETERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        LEGACY_VC_ROWS: "VC_ELEMENT_PLUS_CREDIT_EVENTS",
        SPLIT_UPLOAD_ALLOCATION: "ALLOCATE_ACROSS_ALL_POBS",
    }
)
_POLICY_IDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        NONDISTINCT_MAPPING: "POL-211",
        MATERIAL_RIGHT_CONVENTION: "POL-212",
        LEGACY_VC_ROWS: "POL-213",
        SPLIT_UPLOAD_ALLOCATION: "POL-214",
    }
)
# Legacy column names read here come from the allow-listed home of the legacy wording
# (``domain.imports.legacy_templates``; DG-MK-vocab-check; D-33).
_DISTINCT_FLAG: Final = legacy.DISTINCT_FLAG
_PRICE: Final = legacy.PRICE
_QUANTITY: Final = legacy.QUANTITY
_START: Final = legacy.POB_START
_END: Final = legacy.POB_END
_DEFERRED_ACCOUNT: Final = legacy.DEFERRED_ACCOUNT
_UNBILLED_ACCOUNT: Final = legacy.UNBILLED_ACCOUNT
_REVENUE_ACCOUNT: Final = legacy.REVENUE_ACCOUNT
_SKU_ID: Final = legacy.SKU_ID
_LIST_PRICE: Final = legacy.LIST_PRICE
_DISCOUNT: Final = legacy.DISCOUNT
_RANGE: Final = legacy.RANGE
_MEMOS: Final = legacy.MEMOS
_DISTINCT_TEXT: Final[Mapping[str, str]] = MappingProxyType(
    {"Distinct": "distinct", "Nondistinct": "nondistinct"}
)
_MATCHED: Final = "Matched"
_WILL_BE_CREATED: Final = "Will be created"
ZERO: Final = Decimal(0)
ONE: Final = Decimal(1)
# POL-212 CONVERT_TO_OPTION_RECORD terms (04 T-CON-14 ``material_right``; POL-026; POL-028).
ENTERED_AMOUNT: Final = "ENTERED_AMOUNT"  # T-CON-14 ssp_method (POL-026 material_right.ssp_method)
EXERCISE_POLICY: Final = (
    "material_right.exercise"  # POL-028: the tenant's value (parity MODIFICATION)
)
_KEEP: Final = "KEEP_QUANTITY_CONVENTION"
_CONVERT: Final = "CONVERT_TO_OPTION_RECORD"
_SINGLE_POB: Final = "SINGLE_POB"
_SERIES: Final = "SERIES"
_REVIEW_QUEUE: Final = "REVIEW_QUEUE"
SERIES_PENDING: Final = (
    "A series obligation needs its series_increment_unit (ENGINE_SPEC S03-R-06; T-CON-19 "
    "SERIES_CLASSIFICATION): no legacy series template is seeded and Contract_Live carries no "
    "increment unit."
)
REVIEW_QUEUE_PENDING: Final = (
    "POL-211 REVIEW_QUEUE routes each Nondistinct obligation to the questionnaire (over time? "
    "same measure for each increment? substantially the same?) before commit."
)

type Rule = Literal[
    "TEXT",
    "DATE",
    "DECIMAL",
    "STRATIFICATION",
    "DISTINCTNESS",
    "ENTITY",
    "SSP_VERSION",
    "ACCOUNT",
    "PREVIOUS",
    "DERIVED",
    "EXCLUDED",
]


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """One 04 §17.2 row: id, legacy column, eRev target and the transformation rule."""

    id: str
    legacy: str
    target: str
    rule: Rule


# The eRev target and transformation rule of every 04 §17.2 row, by LM-CL number; the legacy
# column names come from ``legacy_columns.CONTRACT_LIVE`` (the allow-listed home, D-33).
_TARGETS: Final[Mapping[int, tuple[str, Rule]]] = {
    1: ("contract.external_id", "TEXT"),
    2: ("obligation.obligation_key", "TEXT"),
    3: ("product.code; obligation_version.product_code", "TEXT"),
    4: ("obligation_version.start_date", "DATE"),
    5: ("obligation_version.end_date", "DATE"),
    6: ("obligation_version.stratification", "STRATIFICATION"),
    7: ("obligation_version.original_stated_price", "DECIMAL"),
    8: ("obligation_version.original_quantity", "DECIMAL"),
    9: ("legal_entity.code (contracting and performing)", "ENTITY"),
    10: ("obligation_version.ssp_version_label", "SSP_VERSION"),
    11: ("account_overrides.CONTRACT_LIABILITY", "ACCOUNT"),
    12: ("account_overrides.CONTRACT_ASSET, .UNBILLED_RECEIVABLE", "ACCOUNT"),
    13: ("obligation_version.effective_date", "DATE"),
    14: ("obligation_version.memo_1", "TEXT"),
    15: ("obligation_version.memo_2", "TEXT"),
    16: ("obligation_version.memo_3", "TEXT"),
    17: ("obligation_version.sku_number", "TEXT"),
    18: ("obligation_version.distinctness", "DISTINCTNESS"),
    19: ("obligation_version.ssp_unit_list_price", "DECIMAL"),
    20: ("obligation_version.ssp_midpoint_discount_ratio", "DECIMAL"),
    21: ("obligation_version.ssp_range_ratio", "DECIMAL"),
    22: ("account_overrides.REVENUE", "ACCOUNT"),
    23: ("obligation_version.original_ssp_mid", "DECIMAL"),
    24: ("obligation_version.original_ssp_high", "DECIMAL"),
    25: ("obligation_version.original_ssp_low", "DECIMAL"),
    26: ("obligation_version.original_ssp_selected", "DECIMAL"),
    27: ("obligation_version.original_total_contract_price", "DECIMAL"),
    28: ("obligation_version.original_total_contract_ssp", "DECIMAL"),
    29: ("obligation_version.original_allocated_exact", "DECIMAL"),
    30: ("obligation_version.original_unit_ssp", "DECIMAL"),
    31: ("obligation_version.original_unit_revenue_rate", "DECIMAL"),
    32: ("previous version effective_date", "PREVIOUS"),
    33: ("previous version remaining_quantity", "PREVIOUS"),
    34: ("previous version remaining_ssp", "PREVIOUS"),
    35: ("previous version remaining_allocation", "PREVIOUS"),
    36: ("previous version remaining_billing", "PREVIOUS"),
    37: ("previous version unit_ssp", "PREVIOUS"),
    38: ("previous version remaining_unit_revenue_rate", "PREVIOUS"),
    39: ("previous version delivered_quantity_cum", "PREVIOUS"),
    40: ("previous version revenue_cum", "PREVIOUS"),
    41: ("previous version pre_standard_revenue_cum", "PREVIOUS"),
    42: ("previous version billed_cum", "PREVIOUS"),
    43: ("previous version catch_up_cum", "PREVIOUS"),
    44: ("previous version ssp_delivered_cum", "PREVIOUS"),
    45: ("previous version position_obligation", "PREVIOUS"),
    46: ("previous version position_contract_entity", "PREVIOUS"),
    47: ("previous version netting_reclass_amount", "PREVIOUS"),
    48: ("obligation_version.remaining_quantity", "DECIMAL"),
    49: ("obligation_version.remaining_ssp", "DECIMAL"),
    50: ("obligation_version.remaining_allocation", "DECIMAL"),
    51: ("obligation_version.remaining_billing", "DECIMAL"),
    52: ("obligation_version.unit_ssp", "DECIMAL"),
    53: ("obligation_version.remaining_unit_revenue_rate", "DECIMAL"),
    54: ("obligation_version.delivered_quantity", "DECIMAL"),
    55: ("obligation_version.revenue_amount", "DECIMAL"),
    56: ("obligation_version.pre_standard_revenue_amount", "DECIMAL"),
    57: ("obligation_version.billed_amount", "DECIMAL"),
    58: ("obligation_version.catch_up_amount", "DECIMAL"),
    59: ("obligation_version.ssp_delivered", "DECIMAL"),
    60: ("obligation_version.delivered_quantity_cum", "DECIMAL"),
    61: ("obligation_version.revenue_cum", "DECIMAL"),
    62: ("obligation_version.pre_standard_revenue_cum", "DECIMAL"),
    63: ("obligation_version.billed_cum", "DECIMAL"),
    64: ("obligation_version.catch_up_cum", "DECIMAL"),
    65: ("obligation_version.ssp_delivered_cum", "DECIMAL"),
    66: ("obligation_version.position_obligation", "DECIMAL"),
    67: ("obligation_version.position_contract_entity", "DECIMAL"),
    68: ("obligation_version.netting_reclass_amount", "DECIMAL"),
    69: ("contract_computation.created_at", "EXCLUDED"),
    70: ("obligation.legacy_record_key", "TEXT"),
    71: ("derived: <Processing Time Log> <Record Unique ID without time>", "DERIVED"),
}


def _mapping(column: legacy_columns.LegacyColumn) -> FieldMapping:
    number = int(column.id.rsplit("-", 1)[1])
    target, rule = _TARGETS[number]
    return FieldMapping(column.id, column.name, target, rule)


FIELD_MAPPING: Final[tuple[FieldMapping, ...]] = tuple(
    _mapping(column) for column in legacy_columns.CONTRACT_LIVE
)


@dataclass(frozen=True, slots=True)
class BatchParameters:
    """The POLICIES §1.13 import batch parameters of a legacy import (T-IMP-02 shape)."""

    nondistinct_mapping: str = "SINGLE_POB"  # POL-211 legacy column
    material_right_convention: str = "KEEP_QUANTITY_CONVENTION"  # POL-212 legacy column
    legacy_vc_rows: str = FORCED_PARAMETERS[LEGACY_VC_ROWS]
    split_upload_allocation: str = FORCED_PARAMETERS[SPLIT_UPLOAD_ALLOCATION]

    def as_mapping(self) -> dict[str, str]:
        return {
            NONDISTINCT_MAPPING: self.nondistinct_mapping,
            MATERIAL_RIGHT_CONVENTION: self.material_right_convention,
            LEGACY_VC_ROWS: self.legacy_vc_rows,
            SPLIT_UPLOAD_ALLOCATION: self.split_upload_allocation,
        }


def validate_batch_parameters(values: Mapping[str, object]) -> list[ProblemError]:
    """422 ``validation-failed`` errors for a batch-parameter object (SCREENS_B §10.3 "Batch
    parameters"): a FORCED key with another value, an unknown literal, or an unknown key.
    """
    errors: list[ProblemError] = []
    allowed: Mapping[str, tuple[str, ...]] = {
        NONDISTINCT_MAPPING: NONDISTINCT_OPTIONS,
        MATERIAL_RIGHT_CONVENTION: MATERIAL_RIGHT_OPTIONS,
    }
    for key in sorted(values):
        value = values[key]
        if key in FORCED_PARAMETERS:
            if value != FORCED_PARAMETERS[key]:
                errors.append(
                    ProblemError(
                        field=f"batch_parameters.{key}",
                        rule_id=_POLICY_IDS[key],
                        message=(
                            f"{key} is fixed at {FORCED_PARAMETERS[key]} and cannot be changed."
                        ),
                    )
                )
        elif key in allowed:
            if value not in allowed[key]:
                errors.append(
                    ProblemError(
                        field=f"batch_parameters.{key}",
                        rule_id=_POLICY_IDS[key],
                        message=f"Choose one of {', '.join(allowed[key])}.",
                    )
                )
        else:
            errors.append(
                ProblemError(
                    field=f"batch_parameters.{key}",
                    rule_id="T-IMP-02",
                    message="Unknown batch parameter.",
                )
            )
    return errors


@dataclass(frozen=True, slots=True)
class OptionRecord:
    """POL-212 ``CONVERT_TO_OPTION_RECORD``: the option terms of a converted legacy material-right
    row — what the writer establishes for the obligation besides its booking line (04 T-CON-14
    ``material_right``: ``ssp_method`` ``ENTERED_AMOUNT``, ``is_legacy_quantity_ssp_dollars``
    false; the option SSP = legacy quantity × list price 1 as the obligation's SSP point,
    ENGINE_SPEC S03-R-07; exercise per POL-028). A booking line carries no SSP amount (04 §16.1
    API-S-ContractLine), so the record travels with the staging."""

    ssp_method: str
    option_ssp: Decimal
    quantity: Decimal
    exercise_policy: str
    is_legacy_quantity_ssp_dollars: bool
    source_quantity: Decimal


@dataclass(frozen=True, slots=True)
class PendingDecision:
    """A row the batch parameters leave undecided (POL-211 ``SERIES`` / ``REVIEW_QUEUE``): the
    rule, the choice and why the row cannot be booked yet. No queue schema — the row is staged
    and listed; the contract has no booking payload until the decision is made."""

    rule_id: str
    choice: str
    reason: str


@dataclass(frozen=True, slots=True)
class MappedObligation:
    """One legacy obligation row mapped to its eRev booking terms (04 §17.2; REQ-MIG-006)."""

    contract_external_id: str
    obligation_key: str
    product_code: str
    stratification: str | None
    obligation_kind: str  # E-18: STANDARD, VC_LINE or MATERIAL_RIGHT
    distinctness: str  # E-105: distinct or nondistinct
    template_code: str
    entity_code: str
    ssp_version_label: str | None
    ssp_book: str
    quantity: Decimal
    stated_price: Decimal
    start_date: date | None
    end_date: date | None
    sku_number: str | None
    account_overrides: Mapping[str, str] = field(default_factory=dict)
    memos: Mapping[str, str] = field(default_factory=dict)
    option: OptionRecord | None = None  # POL-212 CONVERT_TO_OPTION_RECORD
    pending: PendingDecision | None = None  # POL-211 SERIES / REVIEW_QUEUE


def _decimal(row: LegacyRow, name: str) -> Decimal:
    value = legacy_db.decimal_of(row.values.get(name))
    return ZERO if value is None else value


def is_vc(row: LegacyRow) -> bool:
    """LM-CL-06: a ``VC`` stratification row is a transaction-price component (POL-213)."""
    return row.values.get(legacy_db.STRATIFICATION) == VC


def is_material_right(row: LegacyRow) -> bool:
    """The legacy material-right convention (legacy 01 PAR-04; POL-212): unit list price 1,
    discount 0, range 0 and a stated price of 0, the quantity being the option's SSP in dollars.
    """
    if is_vc(row):
        return False
    return (
        _decimal(row, _LIST_PRICE) == ONE
        and _decimal(row, _DISCOUNT) == ZERO
        and _decimal(row, _RANGE) == ZERO
        and _decimal(row, _PRICE) == ZERO
        and _decimal(row, _QUANTITY) > ZERO
    )


def _accounts(row: LegacyRow) -> dict[str, str]:
    overrides: dict[str, str] = {}
    deferred = row.values.get(_DEFERRED_ACCOUNT)
    if deferred:
        overrides["CONTRACT_LIABILITY"] = deferred
    unbilled = row.values.get(_UNBILLED_ACCOUNT)
    if unbilled:
        overrides["CONTRACT_ASSET"] = unbilled  # LM-CL-12: one account for both roles (D-15)
        overrides["UNBILLED_RECEIVABLE"] = unbilled
    revenue = row.values.get(_REVENUE_ACCOUNT)
    if revenue:
        overrides["REVENUE"] = revenue
    return dict(sorted(overrides.items()))


def map_row(
    row: LegacyRow,
    params: BatchParameters | None = None,
    entity_codes: Mapping[str, str] | None = None,
) -> MappedObligation:
    """Map one legacy ``Contract_Live`` row to its eRev booking terms (04 §17.2; REQ-MIG-006).
    ``entity_codes`` is the CONFIRMED entity mapping of the import (LM-CL-09 rev 1.64; Codex 1227
    F1): legacy ``Selling Entity`` text → the entity code the row's contracting / performing entity
    identity carries downstream (staging, booking, the dry run's prerequisites); an unmapped text is
    its own code (the identity mapping). The original text stays in the row (T-MIG-02 evidence)."""
    params = BatchParameters() if params is None else params
    distinct_text = row.values.get(_DISTINCT_FLAG) or ""
    if distinct_text not in _DISTINCT_TEXT:
        raise ValueError(f"{row.record_key}: {_DISTINCT_FLAG} must be Distinct or Nondistinct")
    distinctness = _DISTINCT_TEXT[distinct_text]
    if params.material_right_convention not in MATERIAL_RIGHT_OPTIONS:
        raise ValueError(f"{MATERIAL_RIGHT_CONVENTION}: {params.material_right_convention!r}")
    if params.nondistinct_mapping not in NONDISTINCT_OPTIONS:
        raise ValueError(f"{NONDISTINCT_MAPPING}: {params.nondistinct_mapping!r}")
    quantity = _decimal(row, _QUANTITY)
    option: OptionRecord | None = None
    pending: PendingDecision | None = None
    if is_vc(row):
        kind, template = "VC_LINE", LEGACY_VC
    elif is_material_right(row) and params.material_right_convention == _KEEP:
        kind, template = "MATERIAL_RIGHT", LEGACY_MATERIAL_RIGHT
    elif is_material_right(row):
        # POL-212 CONVERT_TO_OPTION_RECORD: option SSP = quantity × 1 as ENTERED_AMOUNT, quantity 1
        kind, template = "MATERIAL_RIGHT", LEGACY_MATERIAL_RIGHT
        option = OptionRecord(
            ssp_method=ENTERED_AMOUNT,
            option_ssp=quantity * _decimal(row, _LIST_PRICE),
            quantity=ONE,
            exercise_policy=EXERCISE_POLICY,
            is_legacy_quantity_ssp_dollars=False,
            source_quantity=quantity,
        )
        quantity = ONE
    elif distinctness == "distinct":
        kind, template = "STANDARD", LEGACY_DISTINCT
    else:
        kind, template = "STANDARD", LEGACY_NONDISTINCT
        if params.nondistinct_mapping == _SERIES:
            distinctness = "series"
            pending = PendingDecision("POL-211", _SERIES, SERIES_PENDING)
        elif params.nondistinct_mapping == _REVIEW_QUEUE:
            pending = PendingDecision("POL-211", _REVIEW_QUEUE, REVIEW_QUEUE_PENDING)
    entity = row.values.get(legacy_db.SELLING_ENTITY) or ""
    if not entity:
        raise ValueError(f"{row.record_key}: {legacy_db.SELLING_ENTITY} is blank")
    entity = (entity_codes or {}).get(entity, entity)  # the confirmed target (Codex 1227 F1)
    return MappedObligation(
        contract_external_id=row.contract_external_id,
        obligation_key=row.obligation_key,
        product_code=row.product_code,
        stratification=row.values.get(legacy_db.STRATIFICATION),
        obligation_kind=kind,
        distinctness=distinctness,
        template_code=template,
        entity_code=entity,
        ssp_version_label=row.values.get(legacy_db.SSP_VERSION),
        ssp_book=BOOK_LEGACY_SKU_SSP,
        quantity=quantity,
        stated_price=_decimal(row, _PRICE),
        start_date=legacy_db.parse_period(row.values.get(_START)),
        end_date=legacy_db.parse_period(row.values.get(_END)),
        sku_number=row.values.get(_SKU_ID),
        account_overrides=_accounts(row),
        memos={
            target: text
            for legacy, target in _MEMOS
            if (text := row.values.get(legacy)) not in (None, "")
        },
        option=option,
        pending=pending,
    )


@dataclass(frozen=True, slots=True)
class EntityMapping:
    """One "Entity mapping" row (SCREENS_B §10.3; LM-CL-09)."""

    legacy_name: str
    entity_code: str
    status: str  # "Matched" or "Will be created"


def entity_mapping(
    rows: Iterable[LegacyRow], existing_codes: Iterable[str]
) -> tuple[EntityMapping, ...]:
    """The automatic entity mapping: the legacy ``Selling Entity`` text is the entity code; a code
    the tenant already has is "Matched", any other "Will be created" (LM-CL-09).
    """
    existing = set(existing_codes)
    names = sorted({row.values.get(legacy_db.SELLING_ENTITY) or "" for row in rows} - {""})
    return tuple(
        EntityMapping(name, name, _MATCHED if name in existing else _WILL_BE_CREATED)
        for name in names
    )
