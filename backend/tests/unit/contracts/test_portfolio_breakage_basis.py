"""Frozen allocation identity preserves exact fractions and original source changes."""

from copy import deepcopy
from datetime import date
from uuid import UUID

import pytest

from erev_api.domain.contracts import portfolio_breakage_basis as basis
from erev_api.problems import Problem
from erev_api.schemas.portfolios import PortfolioBreakagePreviewOut, PortfolioBreakageShareOut
from erev_engine.canonical import sha256_hex


def preview():
    return PortfolioBreakagePreviewOut(
        portfolio_id=UUID(int=1),
        version_id=UUID(int=2),
        effective_date=date(2026, 9, 1),
        book_code="ASC606",
        currency="USD",
        total_breakage_quantity="3",
        allocated_total="3",
        shares=[
            PortfolioBreakageShareOut(
                contract_id=UUID(int=n),
                contract_external_id=f"K/{n}",
                contract_version_id=UUID(int=n + 10),
                obligation_id=UUID(int=n + 20),
                obligation_key="POINTS",
                computation_id=UUID(int=n + 30),
                computation_output_sha256=str(n) * 64,
                ssp=f"{n - 2}/3",
                entitlement_quantity="10",
                breakage_quantity=str(n - 2),
            )
            for n in (3, 4)
        ],
    )


def test_freeze_is_order_independent_and_retains_exact_original_basis():
    value = preview()
    frozen = basis.freeze(value)
    assert frozen == basis.freeze(value.model_copy(update={"shares": list(reversed(value.shares))}))
    assert basis.read(frozen) == value
    assert frozen["allocation"]["shares"][0]["ssp"] == "1/3"
    basis.require_fresh(frozen, value)


@pytest.mark.parametrize("change", ["computation", "book", "date", "population"])
def test_unchanged_total_does_not_hide_changed_approval_sources(change):
    value = preview()
    frozen = basis.freeze(value)
    if change == "computation":
        value.shares[0].computation_output_sha256 = "a" * 64
    elif change == "book":
        value.book_code = "IFRS15"
    elif change == "date":
        value.effective_date = date(2026, 9, 2)
    else:
        value.shares[0].obligation_id = UUID(int=99)
    with pytest.raises(Problem):
        basis.require_fresh(frozen, value)


def test_rehashed_wrong_allocation_cannot_replace_frozen_source():
    frozen = basis.freeze(preview())
    wrong = deepcopy(frozen)
    wrong["allocation"]["shares"][0]["breakage_quantity"] = "2"
    wrong["allocation"]["shares"][1]["breakage_quantity"] = "1"
    wrong["sha256"] = sha256_hex(wrong["allocation"])
    with pytest.raises(Problem):
        basis.read(wrong)
    wrong = deepcopy(frozen)
    wrong["allocation"]["shares"][0]["computation_output_sha256"] = "b" * 64
    with pytest.raises(Problem):
        basis.read(wrong)
