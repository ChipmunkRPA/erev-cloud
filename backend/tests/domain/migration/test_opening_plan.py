"""Promotion reconstruction retains confirmed choices instead of applying new defaults."""

from copy import deepcopy

import pytest
from erev_api.domain.migration import opening_balances, opening_plan
from erev_api.domain.migration.field_mapping import BatchParameters
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex
from tests.domain.migration.test_option_opening_units import CUTOVER, converted


def test_confirmed_conversion_and_entity_mapping_round_trip() -> None:
    source = converted().rows[0].source
    parameters = BatchParameters(material_right_convention="CONVERT_TO_OPTION_RECORD")
    entities = {str(source.values["Selling Entity"]): "TARGET"}
    staging = opening_balances.stage([source], CUTOVER, parameters, entity_codes=entities)
    document = opening_plan.record(staging, parameters, entities)
    restored = opening_plan.restore([source], CUTOVER, document)
    assert restored == staging
    assert restored.contracts[0].entity_code == "TARGET"
    assert restored.contracts[0].rows[0].mapped.quantity == 1
    assert restored.option_records[0]["option_ssp"] == "25"
    assert document["batch_parameters"] == parameters.as_mapping()


@pytest.mark.parametrize(
    "fault",
    [
        "absent",
        "hash",
        "version",
        "parameters",
        "mapping",
        "choices",
        "boolean_version",
        "float_value",
    ],
)
def test_missing_or_changed_plan_is_refused_without_defaulting(fault: str) -> None:
    source = converted().rows[0].source
    parameters = BatchParameters(material_right_convention="CONVERT_TO_OPTION_RECORD")
    staging = opening_balances.stage([source], CUTOVER, parameters)
    document = deepcopy(opening_plan.record(staging, parameters, {}))
    if fault == "absent":
        with pytest.raises(Problem, match="no supported confirmed opening plan"):
            opening_plan.restore([source], CUTOVER, None)
        return
    if fault == "hash":
        document["sha256"] = "0" * 64
    elif fault == "version":
        document["version"] = 2
    elif fault == "boolean_version":
        document["version"] = True
    elif fault == "float_value":
        document["batch_parameters"]["migration.material_right_convention"] = 1.5
    elif fault == "parameters":
        document["batch_parameters"] = {}
    elif fault == "mapping":
        document["entity_mapping"] = []
    else:
        document["batch_parameters"]["migration.material_right_convention"] = (
            "KEEP_QUANTITY_CONVENTION"
        )
    if fault not in {"hash", "float_value"}:
        document["sha256"] = sha256_hex(
            {key: value for key, value in document.items() if key != "sha256"}
        )
    with pytest.raises(Problem):
        opening_plan.restore([source], CUTOVER, document)
