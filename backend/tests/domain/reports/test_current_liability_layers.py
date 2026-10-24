"""Current classification uses native release ordering and cumulative rounding."""

import pytest

from erev_engine.stages.s12_fx_entities.current_layers import classify


def layers():
    return [
        {
            "layer_key": "A",
            "txn_open": 2,
            "functional_carrying": 67,
            "movements": [
                {"kind": "LIABILITY_LAYER_CREATED", "amount_txn": 3, "amount_functional": 101}
            ],
        },
        {
            "layer_key": "B",
            "txn_open": 5,
            "functional_carrying": 1000,
            "movements": [
                {"kind": "LIABILITY_LAYER_CREATED", "amount_txn": 5, "amount_functional": 1000}
            ],
        },
    ]


@pytest.mark.parametrize("policy,expected", [("FIFO", [67, 200]), ("PRO_RATA", [33, 400])])
def test_current_layers_preserve_release_order_and_original_rounding(policy, expected):
    result = classify(layers(), 3, policy=policy, minor_unit=2)
    assert [part["current_functional"] for part in result] == expected
    assert sum(part["current_txn"] for part in result) == 3
    assert (
        sum(part["current_functional"] + part["noncurrent_functional"] for part in result) == 1067
    )
    assert classify(layers(), 1, policy="FIFO", minor_unit=2)[0]["current_functional"] == 33
    full = classify(layers(), 7, policy=policy, minor_unit=2)
    assert all(part["noncurrent_functional"] == 0 for part in full)
    with pytest.raises(ValueError):
        classify(layers(), 8, policy=policy, minor_unit=2)
