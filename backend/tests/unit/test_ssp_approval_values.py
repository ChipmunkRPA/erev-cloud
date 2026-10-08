"""Second-review routing measures the effective SSP, independent of Decimal ambient precision."""

from decimal import Decimal, localcontext
from typing import Any

import pytest
from erev_api.domain.ssp.publication import above_threshold


def entry(point: str | None = "100", **changes: Any) -> dict[str, Any]:
    return {
        "method": "observable",
        "value_basis": "AMOUNT",
        "quantity_unit": None,
        "unit_list_price": None,
        "observable_point": None,
        "cost_basis": None,
        "margin_ratio": None,
        "ranges": []
        if point is None
        else [
            {"band_dimension": "NONE", "band_from": None, "mid_value": None, "point_value": point}
        ],
        **changes,
    }


@pytest.mark.control("CTL-010")
@pytest.mark.parametrize(
    ("before", "after", "required"),
    [
        (entry("0"), entry("0"), False),
        (entry("0"), entry("0.000000000000000001"), True),
        (entry("100"), entry("110"), False),
        (entry("100"), entry("110.000000000000000001"), True),
        (entry("100"), entry("90"), False),
        (entry("100"), entry("89.999999999999999999"), True),
        (entry("100"), entry("0"), True),
        (
            entry("1", value_basis="PERCENT_OF_LIST", unit_list_price="100"),
            entry("0.5", value_basis="PERCENT_OF_LIST", unit_list_price="200"),
            False,
        ),
        (
            entry("1", value_basis="PERCENT_OF_LIST", unit_list_price="100"),
            entry("1.06", value_basis="PERCENT_OF_LIST", unit_list_price="106"),
            True,
        ),
        (
            entry(
                "80", method="legacy_range", value_basis="PERCENT_OF_LIST", unit_list_price="100"
            ),
            entry(
                "84", method="legacy_range", value_basis="PERCENT_OF_LIST", unit_list_price="105"
            ),
            False,
        ),
        (
            entry(None, method="cost_plus_margin", cost_basis="80", margin_ratio="0.25"),
            entry(None, method="cost_plus_margin", cost_basis="80", margin_ratio="0.5"),
            True,
        ),
        (
            entry(None, method="cost_plus_margin", cost_basis="80", margin_ratio="0.25"),
            entry(None, method="cost_plus_margin", cost_basis="100", margin_ratio="0"),
            False,
        ),
        (
            entry("100", method="cost_plus_margin", cost_basis="80", margin_ratio="0.25"),
            entry("100", method="cost_plus_margin", cost_basis="200", margin_ratio="0.25"),
            False,
        ),
        (entry(observable_point="100"), entry(observable_point="110"), False),
        (entry(observable_point="100"), entry(observable_point="111"), True),
        (entry(), entry(observable_point="100"), True),
        (entry(observable_point="100"), entry(), True),
        (entry(), entry(value_basis="PERCENT_OF_LIST", unit_list_price="1"), True),
        (entry(), entry(method="cost_plus_margin"), True),
    ],
)
def test_effective_values_determine_second_review(
    before: dict[str, Any],
    after: dict[str, Any],
    required: bool,
) -> None:
    with localcontext() as context:
        context.prec = 6
        assert above_threshold({"before": before, "after": after}, Decimal("0.10")) is required
