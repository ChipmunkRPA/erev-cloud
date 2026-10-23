"""Commission comparison inputs must be complete and have meaningful denominators."""

import pytest
from pydantic import ValidationError

from erev_api.enums import EstimateKind
from erev_api.schemas.db_json import EstimateParameters


def test_renewal_parameters_validate_complete_comparison_and_preserve_legacy() -> None:
    valid = {
        "initial_commission": "2000",
        "initial_contract_value": "100000",
        "renewal_commission": "1000",
        "renewal_contract_value": "50000",
    }
    assert EstimateParameters.validate(EstimateKind.RENEWAL_EXPECTATION, valid) == valid
    assert EstimateParameters.validate(EstimateKind.RENEWAL_EXPECTATION, {}) == {}
    for invalid in (
        {"initial_commission": "2000"},
        {**valid, "initial_contract_value": "0.00"},
        {**valid, "renewal_commission": "-1"},
        {**valid, "renewal_contract_value": "NaN"},
    ):
        with pytest.raises(ValidationError):
            EstimateParameters.validate(EstimateKind.RENEWAL_EXPECTATION, invalid)
