"""Stage 13 framework switches: POLICIES §6.2 and ENGINE_SPEC_B §13.2.3 as data (C-12; REQ-BK-002).

A switch is a resolved policy value in the book's ``BookInput.policies`` (S13-R-06). No stage
branches on ``book_code`` except the Table 13-A ``book_code`` context members and a guard that
restates a FORCED IFRS15 value the orchestrator already supplies. ``IFRS15_SWITCHES`` holds the
18 rows of POLICIES §6.2 and its two extra rows: the POL ids, the policy codes with the literal the
IFRS15 book resolves (``None`` where the row states no literal: rows 15 and 16, the transition
definitions and the effective date), and the stages that declare the keys (§13.2.3). Rows 15 and
16 are read by platform reports only (L3-2-Q-8). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

__all__ = ["IFRS15_SWITCHES", "Switch"]


@dataclass(frozen=True, slots=True)
class Switch:
    """One row of POLICIES §6.2 with its consuming stages (ENGINE_SPEC_B §13.2.3)."""

    row: str  # "1" to "18", or "extra"
    area: str
    pol_ids: tuple[str, ...]
    ifrs15: Mapping[str, str | None]  # policy code -> IFRS15 book literal; None: no literal
    stages: tuple[str, ...]  # stages declaring the keys; () for platform reports


def _switch(
    row: str, area: str, pol_ids: tuple[str, ...], ifrs15: dict[str, str | None], *stages: str
) -> Switch:
    return Switch(row, area, pol_ids, MappingProxyType(ifrs15), stages)


_NONPUBLIC: Final = (
    "disclosure.nonpublic_disaggregation_relief",
    "disclosure.nonpublic_contract_balances_relief",
    "disclosure.nonpublic_rpo_relief",
    "disclosure.nonpublic_judgements_relief",
    "disclosure.nonpublic_expedient_relief",
    "disclosure.nonpublic_cost_relief",
)

IFRS15_SWITCHES: Final[tuple[Switch, ...]] = (
    _switch(
        "1",
        "Collectibility threshold",
        ("POL-011",),
        {"step1.collectibility_threshold": "IFRS_PROBABLE"},
        "02",
    ),
    _switch(
        "2",
        "Contracts failing Step 1, event (c)",
        ("POL-012",),
        {"step1.event_c_enabled": "DISABLED"},
        "02",
    ),
    _switch(
        "3",
        "Immaterial promises",
        ("POL-020",),
        {"pob.immaterial_promise_relief": "ASSESS_ALL"},
        "03",
    ),
    _switch(
        "4",
        "Shipping and handling after control",
        ("POL-021",),
        {"pob.shipping_as_fulfilment": "FALSE"},
        "03",
    ),
    _switch(
        "5", "Sales taxes", ("POL-045",), {"tp.sales_tax_exclusion": "ASSESS_EACH_TAX"}, "04", "10"
    ),
    _switch(
        "6",
        "Noncash consideration measurement date",
        ("POL-048",),
        {"noncash.measurement_date": "CONTRACT_INCEPTION"},  # tenant choice; the default
        "04",
    ),
    _switch(
        "7",
        "Nature of a licence",
        ("POL-024",),
        {"licence.nature_model": "ACTIVITIES_SIGNIFICANTLY_AFFECT_IP"},
        "03",
    ),
    _switch(
        "8",
        "Licence renewals",
        ("POL-025",),
        {"licence.renewal_start": "LATER_OF_AGREEMENT_AND_AVAILABILITY"},
        "03",
        "09",
    ),
    _switch(
        "9",
        "Licence inside a combined POB; attributes vs additional rights",
        ("POL-232",),
        {"licence.combined_pob_nature": "CONSIDER_NATURE"},  # same behaviour as ASC606
        "03",
    ),
    _switch(
        "10",
        "Contract cost impairment reversal",
        ("POL-144",),
        {"costs.impairment_reversal": "REQUIRED_CAPPED"},
        "11",
    ),
    _switch(
        "11",
        "Onerous contracts",
        ("POL-150", "POL-151", "POL-152"),
        {
            "loss.unit": "CONTRACT",
            "loss.scope": "ALL_CONTRACTS_WITH_EAC",
            "loss.cost_basis": "IAS37_68A_COSTS",
        },
        "11",
    ),
    _switch(
        "12",
        "Interim disclosures",
        ("POL-203",),
        {"disclosure.interim_revenue_pack": "IAS34_16A_L"},
        "15",
    ),
    _switch(
        "13",
        "Nonpublic relief",
        ("POL-191", "POL-192", "POL-193", "POL-194", "POL-195", "POL-196"),
        dict.fromkeys(_NONPUBLIC, "DO_NOT_ELECT"),  # not available
        "15",
    ),
    _switch(
        "14",
        "Franchisor expedient",
        ("POL-202",),
        {"franchisor.preopening_expedient": "NOT_ELECTED"},  # not available
        "03",
    ),
    _switch(
        "15",
        "Transition expedients and completed-contract definition",
        ("POL-218",),
        {"transition.first_time_application": None},  # IFRS 15.C3 to C8
    ),
    _switch(
        "16",
        "Effective date",
        ("POL-218",),
        {"transition.first_time_application": None},  # informational
    ),
    _switch(
        "17",
        "ASU 2016-20 disclosure additions",
        ("POL-199", "POL-200", "POL-204"),
        {
            "rpo.exemption_royalty_vc": "DO_NOT_APPLY",  # 50-14A exemptions not available
            "rpo.exemption_vc_wholly_unsatisfied": "DO_NOT_APPLY",
            "disclosure.prior_period_pob_revenue_basis": "ALG10_DECOMPOSITION",
        },
        "15",
    ),
    _switch(
        "18",
        "Repurchase lease outcome",
        ("POL-233", "POL-231"),
        {
            "scope.repurchase_classification": "DECISION_TABLE_55_66_TO_55_78",
            "scope.lessor_combination_expedient": "NOT_ELECTED",  # no lessor combination expedient
        },
        "03",
    ),
    _switch(
        "extra",
        "Business combinations",
        ("POL-215",),
        {"bc.acquired_contract_measurement": "FAIR_VALUE_IFRS3"},
        "07",
    ),
    _switch(
        "extra",
        "FX transaction date for advances (IFRIC 22)",
        ("POL-160", "POL-163"),
        {
            "fx.cl_layer_date": "EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE",
            "fx.cl_historical_layering": "ENABLED",
        },
        "12",
    ),
)
