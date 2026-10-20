"""Deal preview boundary: reject invalid proposals rather than producing substitute figures."""

from dataclasses import replace

import pytest
from erev_api.domain.forecast.deal_compute import compute
from erev_api.schemas.deal_previews import DealInputIn
from erev_engine.errors import EngineError
from pydantic import ValidationError
from support.bundles import minimal_contract


def proposed(**changes: object) -> dict[str, object]:
    return {
        "customer_name": "New customer",
        "entity_code": "US01",
        "start_date": "2026-11-01",
        "lines": [
            {
                "product_code": "SKU",
                "quantity": "1",
                "price": {"amount": "90000.00", "currency": "USD"},
                "term_months": 12,
            }
        ],
        **changes,
    }


def test_decimal_proposal_preserves_amount_and_requires_one_customer() -> None:
    parsed = DealInputIn.model_validate(proposed())
    assert parsed.lines[0].price.amount == "90000.00"
    with pytest.raises(ValidationError, match="Choose one customer"):
        DealInputIn.model_validate(proposed(customer_id="00000000-0000-0000-0000-000000000001"))
    with pytest.raises(ValidationError, match="Choose one customer"):
        DealInputIn.model_validate(proposed(customer_name=None))


def test_proposal_rejects_float_money_and_mixed_currencies() -> None:
    with pytest.raises(ValidationError):
        DealInputIn.model_validate(
            proposed(
                lines=[
                    {
                        "product_code": "SKU",
                        "quantity": "1",
                        "price": {"amount": 90000.0, "currency": "USD"},
                    }
                ]
            )
        )
    with pytest.raises(ValidationError, match="one transaction currency"):
        DealInputIn.model_validate(
            proposed(
                lines=[
                    {
                        "product_code": "SKU",
                        "quantity": "1",
                        "price": {"amount": "1.00", "currency": currency},
                    }
                    for currency in ("USD", "EUR")
                ]
            )
        )


def test_missing_product_mapping_propagates_engine_refusal() -> None:
    with pytest.raises(EngineError, match="PRODUCT_UNMAPPED"):
        compute(minimal_contract())


def test_preview_rejects_multi_contract_baseline() -> None:
    bundle = minimal_contract()
    with pytest.raises(ValueError, match="exactly one"):
        compute(replace(bundle, contracts=(*bundle.contracts, *bundle.contracts)))
