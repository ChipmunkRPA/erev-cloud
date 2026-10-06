"""Opening-balance staging of a legacy database (BUILD_SPEC LMG-2; D-31 mode (a); ENGINE_SPEC §7.3
S07-R-01 to S07-R-05, §7.4 S07-R-11; 04 T-MIG-01 note, §16.3 ``OPENING_BALANCE_ESTABLISHED``,
table 15.4-C ``OPENING_BALANCE_INCONSISTENT``; BUILD_SPEC BS3-D-26; PRD WLD-X-27; SCREENS_B
§10.3).

``stage`` takes every ``Contract_Live`` row of the copy and a cutover date and computes, without
a database, what the import job stages until promotion: per contract the booking terms of the
latest version's ``Original …`` columns (S07-R-02; inception = the legacy minimum ``Current
Period``), the ``OPENING_BALANCE_ESTABLISHED`` rows from LM-CL-39 to LM-CL-68 (S07-R-11; one per
obligation, the ``VC`` rows as transaction-price elements, POL-213), and the S07-R-03
consistency findings. Values are exact decimals from the stored text (the importer's shortest
decimal string). ``validate_cutover`` carries the SCREENS_B copy for a cutover after the latest
legacy period. Under POL-212 ``CONVERT_TO_OPTION_RECORD`` the staging also carries one option
record per converted material-right row (``option_records``; 04 T-CON-14 terms and the option
SSP the writer establishes — a booking line has no SSP amount), and a row left ``pending`` by
POL-211 (``SERIES``, ``REVIEW_QUEUE``) is listed in ``Staging.pending`` and refused by
``booking_payload`` rather than booked silently (Codex review of ed5173f, finding R2).
Promotion (the approval that appends the events and publishes the preset) and the event writes
belong to the database slice.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final

from erev_api.domain.migration import field_mapping, legacy_db
from erev_api.domain.migration.field_mapping import (
    BatchParameters,
    MappedObligation,
    PendingDecision,
)
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.problems import ProblemError

__all__ = [
    "CUTOVER_COPY",
    "OPENING_BALANCE_INCONSISTENT",
    "OPENING_COLUMNS",
    "REASON",
    "TOLERANCE",
    "ContractOpening",
    "Finding",
    "ObligationOpening",
    "Staging",
    "booking_payload",
    "consistency",
    "opening_payload",
    "option_records",
    "stage",
    "validate_cutover",
]

REASON: Final = "LEGACY_MIGRATION"  # E-03 OPENING_BALANCE_ESTABLISHED payload reason (D-31 mode a)
OPENING_BALANCE_INCONSISTENT: Final = "OPENING_BALANCE_INCONSISTENT"  # 04 table 15.4-C, X MIGRATION
CUTOVER_COPY: Final = "Choose a cutover date on or before the latest legacy period."
TOLERANCE: Final = Fraction(1, 10000)  # D-17
_RULE: Final = "S07-R-03"
# LM-CL-39 to LM-CL-68: the legacy column of every payload member of the opening row.
OPENING_COLUMNS: Final[Mapping[str, str]] = {
    "remaining_quantity": "Current Remaining Qty",
    "remaining_ssp": "Current Remaining SSP",
    "remaining_allocation": "Current Remaining Allocation",
    "remaining_billing": "Current Remaining Billing",
    "unit_ssp": "Current Unit SSP",
    "remaining_unit_revenue_rate": "Current Remaining Unit Rev Rec",
    "delivered_quantity_cum": "Current Delivery - Cumulative",
    "revenue_cum": "Current Rev Rec - Cumulative",
    "pre_standard_revenue_cum": "Current Pre-ASC606 Revenue (Net Design Only) - Cumulative",
    "billed_cum": "Current Billing - Cumulative",
    "catch_up_cum": "Current Cumulative Catchup - Cumulative - Disclosure Only",
    "ssp_delivered_cum": "Current SSP Delivered - Cumulative",
    "position_obligation": "Current Contract Position - POB",
    "position_contract_entity": "Current Contract Position - Contract Level",
    "netting_reclass_amount": "Current Reclass to UAR",
}
_ORIGINAL_ALLOCATION: Final = "Original Allocation"
_ORIGINAL_TOTAL_PRICE: Final = "Original Total Contract Price"
_ORIGINAL_SSP: Final = "Original Extended SSP"
ZERO: Final = Decimal(0)


@dataclass(frozen=True, slots=True)
class Finding:
    """A staging finding (04 table 15.4-C; source ``MIGRATION``)."""

    code: str
    subject_key: str
    detail: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ObligationOpening:
    """One legacy obligation row at the cutover: its mapping and the LM-CL-39 to -68 values."""

    mapped: MappedObligation
    source: LegacyRow
    values: Mapping[str, Decimal]  # OPENING_COLUMNS keys, exact
    original_allocation: Decimal | None
    original_ssp: Decimal | None

    @property
    def is_vc(self) -> bool:
        return self.mapped.obligation_kind == "VC_LINE"

    @property
    def allocation(self) -> Decimal:
        """X_i = ``revenue_cum`` + ``remaining_allocation`` (S07-R-03)."""
        return self.values["revenue_cum"] + self.values["remaining_allocation"]


@dataclass(frozen=True, slots=True)
class ContractOpening:
    """One migrated contract at the cutover (S07-R-02, S07-R-11)."""

    external_id: str
    entity_code: str
    inception_date: date
    latest_period: date
    transaction_price: Decimal
    obligations: tuple[ObligationOpening, ...]  # non-VC rows
    vc_elements: tuple[ObligationOpening, ...]  # VC rows (POL-213)

    @property
    def rows(self) -> tuple[ObligationOpening, ...]:
        return (*self.obligations, *self.vc_elements)

    @property
    def pending(self) -> tuple[ObligationOpening, ...]:
        """Rows the batch parameters leave undecided (POL-211 SERIES / REVIEW_QUEUE)."""
        return tuple(row for row in self.rows if row.mapped.pending is not None)

    def total(self, member: str) -> Decimal:
        return sum((row.values[member] for row in self.rows), ZERO)


@dataclass(frozen=True, slots=True)
class Staging:
    """What ``/import`` stages for an opening-balance migration (BS3-D-26)."""

    cutover_date: date
    contracts: tuple[ContractOpening, ...]
    migrated_rows: int  # every legacy row, labelled "migrated, unattributed"
    findings: tuple[Finding, ...]

    @property
    def legacy_pob_rows(self) -> int:
        return sum(len(contract.rows) for contract in self.contracts)

    @property
    def obligation_count(self) -> int:
        return sum(len(contract.obligations) for contract in self.contracts)

    @property
    def vc_count(self) -> int:
        return sum(len(contract.vc_elements) for contract in self.contracts)

    @property
    def pending(self) -> tuple[tuple[str, str, PendingDecision], ...]:
        """(contract external id, obligation key, decision) of every pending row."""
        return tuple(
            (contract.external_id, row.mapped.obligation_key, row.mapped.pending)
            for contract in self.contracts
            for row in contract.pending
            if row.mapped.pending is not None
        )

    @property
    def option_records(self) -> tuple[dict[str, Any], ...]:
        """The POL-212 option records of every contract (``option_records``)."""
        return tuple(record for contract in self.contracts for record in option_records(contract))


def validate_cutover(cutover_date: date, latest_period: date | None) -> ProblemError | None:
    """SCREENS_B §10.3: the cutover is on or before the latest legacy ``Current Period``."""
    if latest_period is not None and cutover_date > latest_period:
        return ProblemError(field="cutover_date", rule_id="S07-R-11", message=CUTOVER_COPY)
    return None


def _opening(
    row: LegacyRow, params: BatchParameters, entity_codes: Mapping[str, str] | None = None
) -> ObligationOpening:
    values = {
        member: legacy_db.decimal_of(row.values.get(column)) or ZERO
        for member, column in OPENING_COLUMNS.items()
    }
    return ObligationOpening(
        mapped=field_mapping.map_row(row, params, entity_codes),
        source=row,
        values=values,
        original_allocation=legacy_db.decimal_of(row.values.get(_ORIGINAL_ALLOCATION)),
        original_ssp=legacy_db.decimal_of(row.values.get(_ORIGINAL_SSP)),
    )


def _transaction_price(rows: Iterable[ObligationOpening]) -> Decimal:
    """The contract transaction price of the latest legacy version: the ``Original Total Contract
    Price`` the rows agree on, else Σ ``Original Allocation`` (S07-R-02; LM-CL-27, LM-CL-29).
    """
    rows = tuple(rows)
    totals = {
        legacy_db.decimal_of(row.source.values.get(_ORIGINAL_TOTAL_PRICE)) for row in rows
    } - {None}
    if len(totals) == 1:
        (total,) = totals
        assert total is not None
        return total
    return sum((row.original_allocation or ZERO for row in rows), ZERO)


def stage(
    rows: Iterable[LegacyRow],
    cutover_date: date,
    params: BatchParameters | None = None,
    entity_codes: Mapping[str, str] | None = None,
) -> Staging:
    """Stage the opening balances of every contract from the latest version per record key
    (S07-R-11): per contract the booking terms, the opening rows and the S07-R-03 findings.
    ``entity_codes`` is the confirmed entity mapping (legacy text → entity code; LM-CL-09 rev 1.64,
    Codex 1227 F1) applied to every staged row's entity identity; the legacy rows themselves are
    stored unchanged (T-MIG-02).
    """
    params = BatchParameters() if params is None else params
    every = tuple(rows)
    latest = legacy_db.latest_rows(every)
    by_contract: dict[str, list[ObligationOpening]] = {}
    for row in latest:
        by_contract.setdefault(row.contract_external_id, []).append(
            _opening(row, params, entity_codes)
        )
    periods: dict[str, list[date]] = {}
    for row in every:
        if row.current_period is not None:
            periods.setdefault(row.contract_external_id, []).append(row.current_period)
    contracts: list[ContractOpening] = []
    findings: list[Finding] = []
    for external_id in sorted(by_contract):
        openings = by_contract[external_id]
        entities = sorted({item.mapped.entity_code for item in openings})
        contract = ContractOpening(
            external_id=external_id,
            entity_code=entities[0],
            inception_date=min(periods.get(external_id, [cutover_date])),
            latest_period=max(periods.get(external_id, [cutover_date])),
            transaction_price=_transaction_price(openings),
            obligations=tuple(item for item in openings if not item.is_vc),
            vc_elements=tuple(item for item in openings if item.is_vc),
        )
        contracts.append(contract)
        findings.extend(consistency(contract))
    return Staging(cutover_date, tuple(contracts), len(every), tuple(findings))


def _sign(value: Decimal) -> int:
    return 0 if value == 0 else (1 if value > 0 else -1)


def consistency(contract: ContractOpening) -> tuple[Finding, ...]:
    """S07-R-03: per row X_i = revenue_cum + remaining_allocation and revenue_cum share a sign or
    are 0, |revenue_cum| ≤ |X_i| and remaining_quantity ≥ 0; Σ X_i equals the contract
    transaction price within 1e-4. Each failure is one ``OPENING_BALANCE_INCONSISTENT`` finding
    with detail rule ``S07-R-03`` (04 table 15.4-C; source ``MIGRATION``).
    """
    findings: list[Finding] = []
    for row in contract.rows:
        subject = f"{contract.external_id}/{row.mapped.obligation_key}"
        revenue = row.values["revenue_cum"]
        allocation = row.allocation
        problems: list[str] = []
        if _sign(revenue) * _sign(allocation) < 0:
            problems.append("revenue_cum and allocation differ in sign")
        if abs(revenue) > abs(allocation):
            problems.append("|revenue_cum| exceeds |allocation|")
        if row.values["remaining_quantity"] < 0:
            problems.append("remaining_quantity is negative")
        for problem in problems:
            findings.append(
                Finding(
                    OPENING_BALANCE_INCONSISTENT,
                    subject,
                    {
                        "rule": _RULE,
                        "reason": problem,
                        "revenue_cum": str(revenue),
                        "allocation": str(allocation),
                        "remaining_quantity": str(row.values["remaining_quantity"]),
                    },
                )
            )
    total = sum((row.allocation for row in contract.rows), ZERO)
    if abs(Fraction(total) - Fraction(contract.transaction_price)) > TOLERANCE:
        findings.append(
            Finding(
                OPENING_BALANCE_INCONSISTENT,
                contract.external_id,
                {
                    "rule": _RULE,
                    "reason": "sum of allocations differs from the transaction price",
                    "sum_allocations": str(total),
                    "transaction_price": str(contract.transaction_price),
                },
            )
        )
    return tuple(findings)


def booking_payload(contract: ContractOpening) -> dict[str, Any]:
    """The ``CONTRACT_BOOKED`` terms of a migrated contract (S07-R-02): lines from the latest
    version's ``Original …`` columns, quantities and prices as decimal strings. A converted
    material right (POL-212) books with quantity 1; its option terms are ``option_records``. A
    contract with a row still ``pending`` a POL-211 decision has no payload (``ValueError``).
    """
    if contract.pending:
        keys = ", ".join(row.mapped.obligation_key for row in contract.pending)
        raise ValueError(
            f"{contract.external_id}: obligations pending a POL-211 decision cannot be booked: "
            f"{keys}"
        )
    lines = [
        {
            "obligation_key": row.mapped.obligation_key,
            "product_code": row.mapped.product_code,
            "quantity": str(row.mapped.quantity),
            "total_price": str(row.mapped.stated_price),
            "start_date": None
            if row.mapped.start_date is None
            else row.mapped.start_date.isoformat(),
            "end_date": None if row.mapped.end_date is None else row.mapped.end_date.isoformat(),
            "stratification": row.mapped.stratification,
            "performing_entity_code": row.mapped.entity_code,
            "ssp_version_label": row.mapped.ssp_version_label,
            "account_overrides": dict(row.mapped.account_overrides),
            "pob_template_code": row.mapped.template_code,
            **row.mapped.memos,
        }
        for row in contract.rows
    ]
    return {
        "external_id": contract.external_id,
        "contracting_entity_code": contract.entity_code,
        "inception_date": contract.inception_date.isoformat(),
        "transaction_currency": None,  # the tenant reporting currency (LM-CL-09; set by the job)
        "lines": lines,
    }


def option_records(contract: ContractOpening) -> list[dict[str, Any]]:
    """POL-212 ``CONVERT_TO_OPTION_RECORD``: one record per converted material-right row — the
    04 T-CON-14 ``material_right`` terms (``ssp_method`` ``ENTERED_AMOUNT``,
    ``is_legacy_quantity_ssp_dollars`` false, exercise per POL-028) and the option SSP (legacy
    quantity × 1) the writer establishes as the obligation's SSP point (ENGINE_SPEC S03-R-07),
    with the SSP book and version label the row names. Empty under ``KEEP_QUANTITY_CONVENTION``.
    """
    return [
        {
            "obligation_key": row.mapped.obligation_key,
            "product_code": row.mapped.product_code,
            "ssp_method": row.mapped.option.ssp_method,
            "option_ssp": str(row.mapped.option.option_ssp),
            "quantity": str(row.mapped.option.quantity),
            "exercise_policy": row.mapped.option.exercise_policy,
            "is_legacy_quantity_ssp_dollars": row.mapped.option.is_legacy_quantity_ssp_dollars,
            "source_quantity": str(row.mapped.option.source_quantity),
            "ssp_book": row.mapped.ssp_book,
            "ssp_version_label": row.mapped.ssp_version_label,
        }
        for row in contract.rows
        if row.mapped.option is not None
    ]


def opening_payload(contract: ContractOpening, cutover_date: date) -> dict[str, Any]:
    """The ``OPENING_BALANCE_ESTABLISHED`` payload (S07-R-11; 04 §16.3): ``reason``
    ``LEGACY_MIGRATION``, the cutover date and one row per obligation from LM-CL-39 to LM-CL-68.
    """
    return {
        "reason": REASON,
        "cutover_date": cutover_date.isoformat(),
        "rows": [
            {
                "obligation_key": row.mapped.obligation_key,
                **{member: str(value) for member, value in row.values.items()},
            }
            for row in contract.rows
        ],
    }
