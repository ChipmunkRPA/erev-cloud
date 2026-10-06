"""Legacy v1 template column definitions (04 T-IMP-01, §17.3, §17.4, table 15.4-A; D-33; BUILD_SPEC
DIN-1).

This is the home that dev-guide DG-MK-vocab-check allow-lists for legacy template column names,
which keep the legacy wording (D-33). ``LEGACY_HEADERS`` equals the headers revision 0044 seeds from
``0044_din_1_import_templates.json``; ``test_import_templates_seeded`` compares the two.

Each header is ``(name, type, required, rule_ids)``: the exact legacy column name, its coercion type
(``identifier``, ``text``, ``label``, ``amount``, ``quantity``, ``ratio``, ``date``), whether a
blank cell is ``REQUIRED_VALUE_BLANK``, and the table 15.4-A type-stage codes of the column
(L4-1-Q-28). ``KEY_COLUMNS`` builds T-IMP-03 ``business_key``; ``EXAMPLES`` is the example row of
each download.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

__all__ = [
    "BILLING",
    "CONTRACT",
    "CURRENT_PERIOD",
    "DEFERRED_ACCOUNT",
    "DELIVERY",
    "DISCOUNT",
    "DISTINCT_FLAG",
    "EXAMPLES",
    "KEY_COLUMNS",
    "LEGACY_HEADERS",
    "LEGACY_HEADER_TYPES",
    "LIST_PRICE",
    "MEMOS",
    "MOD_BILLING",
    "MOD_END",
    "MOD_QTY",
    "MOD_START",
    "POB",
    "POB_END",
    "POB_START",
    "PRE_STANDARD",
    "PRICE",
    "QUANTITY",
    "RANGE",
    "REVENUE_ACCOUNT",
    "SELLING_ENTITY",
    "SKU",
    "SKU_ID",
    "SSP_VERSION",
    "STRATIFICATION",
    "UNBILLED_ACCOUNT",
    "HeaderSpec",
]

type HeaderSpec = tuple[str, str, bool, tuple[str, ...]]

# The legacy column names the emitters read (BUILD_SPEC DIN-4, DIN-5): named once here, the
# allow-listed home of legacy wording (DG-MK-vocab-check; D-33).
CONTRACT: Final = "Contract Unique Name"
POB: Final = "POB Unique ID"
SKU: Final = "SKU Name"
SKU_ID: Final = "SKU Unique ID"
DISTINCT_FLAG: Final = "Distinct or Nondistinct"
LIST_PRICE: Final = "SKU Unit List Price"
STRATIFICATION: Final = "ASC 606 Stratification"
DISCOUNT: Final = "Midpoint Discount Percentage"
RANGE: Final = "SSP Range Method (+-)"
SSP_VERSION: Final = "SSP Version"
REVENUE_ACCOUNT: Final = "Revenue Account"
POB_START: Final = "POB Start Date"
POB_END: Final = "POB End Date"
PRICE: Final = "Original POB Total Selling Price"
QUANTITY: Final = "Original POB Total Qty"
SELLING_ENTITY: Final = "Selling Entity"
DEFERRED_ACCOUNT: Final = "Deferred Revenue Account"
UNBILLED_ACCOUNT: Final = "Unbilled A/R Account"
CURRENT_PERIOD: Final = "Current Period"
DELIVERY: Final = "Current Delivery"
BILLING: Final = "Current Billing"
PRE_STANDARD: Final = "Current Pre-ASC606 Revenue (Net Design Only)"
MEMOS: Final = (("Memo 1", "memo_1"), ("Memo 2", "memo_2"), ("Memo 3", "memo_3"))
MOD_START: Final = "Mod Start Date"  # BUILD_SPEC DIN-6
MOD_END: Final = "Mod End Date"
MOD_BILLING: Final = "Mod Billing"
MOD_QTY: Final = "Mod Qty"

_BLANK: Final = "REQUIRED_VALUE_BLANK"
_NUMBER: Final = "VALUE_NOT_NUMERIC"
_DATE: Final = "DATE_INVALID"
_RANGE: Final = "DATE_RANGE_INVERTED"
_KEYS: Final[tuple[HeaderSpec, ...]] = (
    ("Contract Unique Name", "identifier", True, (_BLANK,)),
    ("POB Unique ID", "identifier", True, (_BLANK,)),
    ("SKU Name", "identifier", True, (_BLANK,)),
)


def _memos(*rule_ids: str) -> tuple[HeaderSpec, ...]:
    return tuple((f"Memo {number}", "text", False, rule_ids) for number in (1, 2, 3))


LEGACY_HEADERS: Final[Mapping[str, tuple[HeaderSpec, ...]]] = MappingProxyType(
    {
        "legacy_sku_ssp": (
            ("SKU Unique ID", "identifier", False, ()),
            ("SKU Name", "identifier", True, (_BLANK,)),
            ("Distinct or Nondistinct", "text", True, (_BLANK, "SSP_DISTINCT_FLAG_INVALID")),
            ("SKU Unit List Price", "amount", True, (_BLANK, _NUMBER)),
            ("ASC 606 Stratification", "identifier", True, (_BLANK,)),
            (
                "Midpoint Discount Percentage",
                "ratio",
                True,
                (_BLANK, _NUMBER, "SSP_PERCENT_OUT_OF_RANGE"),
            ),
            ("SSP Range Method (+-)", "ratio", True, (_BLANK, _NUMBER, "SSP_PERCENT_OUT_OF_RANGE")),
            ("SSP Version", "label", True, (_BLANK,)),
            ("Revenue Account", "identifier", False, ()),
        ),
        "legacy_contract_setup": (
            *_KEYS,
            ("POB Start Date", "date", True, (_BLANK, _DATE, _RANGE)),
            ("POB End Date", "date", True, (_BLANK, _DATE, _RANGE)),
            ("ASC 606 Stratification", "identifier", True, (_BLANK,)),
            ("Original POB Total Selling Price", "amount", True, (_BLANK, _NUMBER)),
            (
                "Original POB Total Qty",
                "quantity",
                True,
                (_BLANK, _NUMBER, "SETUP_QUANTITY_ZERO", "NEGATIVE_BOOKING_LINE"),
            ),
            ("Selling Entity", "identifier", True, (_BLANK,)),
            ("SSP Version", "label", True, (_BLANK,)),
            ("Deferred Revenue Account", "identifier", False, ()),
            ("Unbilled A/R Account", "identifier", False, ()),
            ("Current Period", "date", True, (_BLANK, _DATE)),
            *_memos(),
        ),
        "legacy_progress_tracking": (
            *_KEYS,
            ("Current Delivery", "quantity", True, (_BLANK, _NUMBER)),
            ("Current Billing", "amount", True, (_BLANK, _NUMBER)),
            ("Current Pre-ASC606 Revenue (Net Design Only)", "amount", True, (_BLANK, _NUMBER)),
            *_memos("PROGRESS_MEMO_BLANK"),
        ),
        "legacy_contract_modification": (
            *_KEYS,
            ("Mod Start Date", "date", False, (_DATE, _RANGE)),
            ("Mod End Date", "date", False, (_DATE, _RANGE)),
            ("ASC 606 Stratification", "identifier", False, ()),
            ("Mod Billing", "amount", True, (_BLANK, _NUMBER, "MOD_SIGN_MISMATCH")),
            (
                "Mod Qty",
                "quantity",
                True,
                (_BLANK, _NUMBER, "MOD_SIGN_MISMATCH", "VC_QUANTITY_NOT_ALLOWED"),
            ),
            ("Selling Entity", "identifier", False, ()),
            ("Deferred Revenue Account", "identifier", False, ()),
            ("Unbilled A/R Account", "identifier", False, ()),
            ("SSP Version", "label", False, ()),
            *_memos(),
        ),
    }
)
# The names, types and required flags the per-row models are built from.
LEGACY_HEADER_TYPES: Final[Mapping[str, tuple[tuple[str, str, bool], ...]]] = MappingProxyType(
    {
        code: tuple((name, kind, required) for name, kind, required, _ in headers)
        for code, headers in LEGACY_HEADERS.items()
    }
)
# T-IMP-03 ``business_key``: "Contract 1 / POB #1 / Hardware 1"; SSP rows use the IMP-08 key.
KEY_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "legacy_sku_ssp": ("SKU Name", "ASC 606 Stratification", "SSP Version"),
        "legacy_contract_setup": ("Contract Unique Name", "POB Unique ID", "SKU Name"),
        "legacy_progress_tracking": ("Contract Unique Name", "POB Unique ID", "SKU Name"),
        "legacy_contract_modification": ("Contract Unique Name", "POB Unique ID", "SKU Name"),
    }
)
_CONTRACT_EXAMPLE: Final = {
    "Contract Unique Name": "Contract 1",
    "POB Unique ID": "POB #1",
    "SKU Name": "Hardware 1",
}
# The example row of each download (legacy 01 sample world: WLD-F-01 and the UAT files).
EXAMPLES: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "legacy_sku_ssp": {
            "SKU Unique ID": "1",
            "SKU Name": "Hardware 1",
            "Distinct or Nondistinct": "Distinct",
            "SKU Unit List Price": "100",
            "ASC 606 Stratification": "Hardware 1",
            "Midpoint Discount Percentage": "0.1",
            "SSP Range Method (+-)": "0.15",
            "SSP Version": "2023-01-01",
            "Revenue Account": "5001",
        },
        "legacy_contract_setup": {
            **_CONTRACT_EXAMPLE,
            "POB Start Date": "2023-01-01",
            "POB End Date": "2023-12-31",
            "ASC 606 Stratification": "Hardware 1",
            "Original POB Total Selling Price": "1000",
            "Original POB Total Qty": "10",
            "Selling Entity": "Mock Entity 1",
            "SSP Version": "2023-01-01",
            "Deferred Revenue Account": "2001",
            "Unbilled A/R Account": "1201",
            "Current Period": "2023-01-01",
            "Memo 1": "Booked",
            "Memo 2": "Sales order 1",
            "Memo 3": "Region A",
        },
        "legacy_progress_tracking": {
            **_CONTRACT_EXAMPLE,
            "Current Delivery": "5",
            "Current Billing": "500",
            "Current Pre-ASC606 Revenue (Net Design Only)": "0",
            "Memo 1": "Delivered",
            "Memo 2": "Invoice 1001",
            "Memo 3": "Region A",
        },
        "legacy_contract_modification": {
            **_CONTRACT_EXAMPLE,
            "Mod Start Date": "2023-05-15",
            "Mod End Date": "2023-12-31",
            "ASC 606 Stratification": "Hardware 1",
            "Mod Billing": "200",
            "Mod Qty": "2",
            "Selling Entity": "Mock Entity 1",
            "Deferred Revenue Account": "2001",
            "Unbilled A/R Account": "1201",
            "SSP Version": "2023-01-01",
            "Memo 1": "Amended",
            "Memo 2": "Change order 1",
            "Memo 3": "Region A",
        },
    }
)
