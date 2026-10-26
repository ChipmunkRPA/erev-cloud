"""Exact ledger roles admitted to original revenue-component evidence."""

from collections.abc import Mapping
from typing import Any

SUPPLIER_ROLE = "BILLING_CLEARING:AP_SUPPLIER"
HISTORY_ROLES = ("REVENUE", "INTERCOMPANY_DUE_TO", SUPPLIER_ROLE, "CONTRACT_LIABILITY")


def is_supplier(line: Mapping[Any, Any]) -> bool:
    return (
        line["entry_kind"] in {"REVENUE_RECOGNITION", "INTERCOMPANY"}
        and line["account_role"] == "BILLING_CLEARING"
        and line.get("clearing_purpose") == "AP_SUPPLIER"
    )


def allowed(line: Mapping[Any, Any]) -> bool:
    if is_supplier(line) or (
        line["entry_kind"] in {"REVENUE_RECOGNITION", "INTERCOMPANY"}
        and line["account_role"] == "CONTRACT_LIABILITY"
    ):
        return True
    return line["entry_kind"] in {"REVENUE_RECOGNITION", "INTERCOMPANY"} and (
        line["account_role"] == "REVENUE"
        or (line["account_role"] == "INTERCOMPANY_DUE_TO" and line["entry_kind"] == "INTERCOMPANY")
    )


def trace_role(line: Mapping[Any, Any]) -> str:
    return "BILLING_CLEARING%3AAP_SUPPLIER" if is_supplier(line) else str(line["account_role"])
