"""Exact GL reconciliation freshness beyond ledger positions and document counts."""

from dataclasses import replace
from decimal import Decimal

import pytest
from erev_api.domain.close.reconciliation_balances import matches_roles
from erev_api.domain.close.trial_balance import NotStated, RoleBalance

ROLES = (
    RoleBalance("CONTRACT_LIABILITY", ("2100",), Decimal("-100.000001")),
    RoleBalance("CONTRACT_ASSET", ("1200",), Decimal("30")),
    RoleBalance("UNBILLED_RECEIVABLE", ("1210",), Decimal("20")),
)
TOTALS = [
    {
        "account_role": "CONTRACT_LIABILITY",
        "account_codes": ["2100"],
        "currency": "USD",
        "subledger_amount": "-100.000001",
        "source_amount": "-99",
        "not_stated": None,
    },
    {
        "account_role": "CONTRACT_ASSET",
        "account_codes": ["1200"],
        "currency": "USD",
        "subledger_amount": "30.00",
        "source_amount": "29",
        "not_stated": None,
    },
    {
        "account_role": "UNBILLED_RECEIVABLE",
        "account_codes": ["1210"],
        "currency": "USD",
        "subledger_amount": "20",
        "source_amount": "19",
        "not_stated": None,
    },
]


def test_same_basis_ignores_source_variances_and_numeric_formatting() -> None:
    assert matches_roles(TOTALS, ROLES, "USD")
    assert matches_roles(list(reversed(TOTALS)), ROLES, "USD")


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("delta", [Decimal("-0.000001"), Decimal("0.000001")])
def test_every_role_detects_even_sub_minor_unit_movement(index: int, delta: Decimal) -> None:
    changed = list(ROLES)
    amount = changed[index].amount
    assert amount is not None
    changed[index] = replace(changed[index], amount=amount + delta)
    assert not matches_roles(TOTALS, changed, "USD")


def test_mapping_currency_missing_and_duplicate_roles_change_the_basis() -> None:
    changed = [replace(ROLES[0], account_codes=("2100", "2105")), *ROLES[1:]]
    assert not matches_roles(TOTALS, changed, "USD")
    assert not matches_roles(TOTALS, ROLES, "EUR")
    assert not matches_roles(TOTALS, ROLES[:2], "USD")
    assert not matches_roles(TOTALS[:2], ROLES, "USD")
    assert not matches_roles([*TOTALS, TOTALS[0]], ROLES, "USD")


def test_omitted_zero_role_is_zero_but_new_balance_or_unreadable_role_is_stale() -> None:
    zero = RoleBalance("CONTRACT_ASSET", ("1200",), Decimal(0))
    assert matches_roles([], [zero], "USD")
    assert not matches_roles([], [replace(zero, amount=Decimal("0.01"))], "USD")
    unknown = replace(zero, amount=None, not_stated=NotStated("Unavailable", ()))
    assert not matches_roles([], [unknown], "USD")


def test_unstated_basis_compares_reason_and_named_contracts() -> None:
    unknown = RoleBalance(
        "CONTRACT_ASSET",
        ("1200",),
        None,
        NotStated("No functional balance", (("contract-1", "C-1"),)),
    )
    totals = [
        {
            "account_role": "CONTRACT_ASSET",
            "account_codes": ["1200"],
            "currency": "USD",
            "subledger_amount": None,
            "not_stated": {
                "reason": "No functional balance",
                "contracts": [{"id": "contract-1", "external_id": "C-1"}],
            },
        }
    ]
    assert matches_roles(totals, [unknown], "USD")
    assert not matches_roles(
        totals, [replace(unknown, not_stated=NotStated("Unreadable", ()))], "USD"
    )
    assert not matches_roles(totals, [replace(unknown, amount=Decimal(0), not_stated=None)], "USD")
