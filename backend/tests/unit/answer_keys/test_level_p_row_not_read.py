"""A level P value of ``reference.products.LEVEL_P_NOT_READ`` on the whole engine: it stands in
the bundle and no figure moves, and the same value at the scope the reader passes moves them
(item PRODUCT-POLICY-VALUE-NOT-READ-1, register index 309; POLICIES §0.5 rule 1 rev 1.125; the
lane's measurement of 2026-10-03, kept as a test). No database.

The vehicle is a key of the corpus, run by the engine runner in three forms; none is written
anywhere and no key, oracle or expected figure changes:

* A — the key as it is: every figure as the key expects;
* B — every template of its world states the other value of the parameter. That is level P:
  the runner puts it at ``OBLIGATION`` scope for each booked line, as the product's bundle
  assembly does (``runners._product_levels``; ``contracts.bundles._policies``). The row is in
  the bundle and EVERY FIGURE IS AS IN A;
* C — a contract of the key states the same value, a ``CONTRACT`` row: the scope each reader
  passes. The figures move. This is the control: the value is one the engine has a rule for, and
  B's silence is the scope, not the value.

POL-240 ``usage.tier_minimum_method`` on REC-USAGE-STAND-READY-FEE-SCHEDULED-TO-TERM-END, a usage
obligation with 63,750.00 of reported fees; POL-021 ``pob.shipping_as_fulfilment`` on
POB-S2-SHIPPING-OWN-ON, a product and its freight of 50.00 under the workspace's election. No
key of the corpus reaches the read of POL-029 ``upfront_fee.recognition_period``, which acts
for a renewal option with a start date; its witness is the reader's call, pinned with the other
four in ``tests/architecture/test_level_p_readers.py``.

When a reader of the next release passes the obligation, form B of its parameter moves the
figures and this module turns red with that one: the parameter then leaves the door's set.
"""

from __future__ import annotations

import dataclasses

import pytest
from erev_api.domain.reference import products
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.models import PolicyOverride
from support.answer_keys.runners import CheckpointMismatchError, assert_checkpoints, run_engine

TIER = "usage.tier_minimum_method"  # POL-240
SHIPPING = "pob.shipping_as_fulfilment"  # POL-021
BENEFIT = "upfront_fee.recognition_period"  # POL-029: no key reaches its read
# parameter: (the key, the value stated, the registry's row in the key, the obligations booked)
USAGE_KEY = ("rec", "REC-USAGE-STAND-READY-FEE-SCHEDULED-TO-TERM-END")
SHIPPING_KEY = ("pob", "POB-S2-SHIPPING-OWN-ON")
Row = tuple[str, str, str, str]  # scope, subject, value, level
CASES: dict[str, tuple[tuple[str, str], str, Row, tuple[str, ...]]] = {
    TIER: (
        USAGE_KEY,
        "ESTIMATE_MEASUREMENT_PERIOD_TP",
        ("GROUP", "", "DERIVED", "DEFAULT"),
        ("NS-ROUTE-01/L1-ROUTING",),
    ),
    SHIPPING: (
        SHIPPING_KEY,
        "FALSE",
        ("GROUP", "", "TRUE", "T"),
        ("C-SHIP/L1-PROD", "C-SHIP/L2-SHIP"),
    ),
}
# The control: what the value does where the reader looks — (checkpoint, subject, field,
# expected, actual) of the first figure that moves, and how many move.
MOVED: dict[str, tuple[int, tuple[str, str, str, str, str]]] = {
    TIER: (
        10,
        ("september-2026", "contract NS-ROUTE-01", "transaction_price", "363750.00", "300000.00"),
    ),
    SHIPPING: (8, ("end-of-december", "contract C-SHIP", "revenue_cum", "1050.00", "1000.00")),
}


def _key(parameter: str) -> LoadedKey:
    family, key_id = CASES[parameter][0]
    return load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")


def _at_level_p(loaded: LoadedKey, parameter: str, value: str) -> LoadedKey:
    """Form B: every template of the key's world states ``value`` of ``parameter``."""
    world = loaded.key.world
    templates = tuple(
        template.model_copy(
            update={"policy_values": {**(template.policy_values or {}), parameter: value}}
        )
        for template in world.pob_templates
    )
    key = loaded.key.model_copy(
        update={"world": world.model_copy(update={"pob_templates": templates})}
    )
    return dataclasses.replace(loaded, key=key)


def _at_the_contract(loaded: LoadedKey, parameter: str, value: str) -> LoadedKey:
    """Form C: every contract of the key states ``value`` of ``parameter`` for itself."""
    stated = PolicyOverride(policy_key=parameter, value=value, rationale="the control of form B")
    contracts = tuple(
        contract.model_copy(
            update={"policy_overrides": (*(contract.policy_overrides or ()), stated)}
        )
        for contract in loaded.key.contracts
    )
    return dataclasses.replace(loaded, key=loaded.key.model_copy(update={"contracts": contracts}))


def _rows(loaded: LoadedKey, parameter: str) -> list[Row]:
    """The rows of ``parameter`` in the bundles the runner builds for the key."""
    found: set[Row] = set()
    for checkpoint in runners._build_checkpoint_bundles(loaded):
        for bundle in checkpoint.bundles:
            for book in bundle.books:
                found |= {
                    (policy.scope, policy.subject_key, str(policy.value), policy.level)
                    for policy in book.policies
                    if policy.code == parameter
                }
    return sorted(found)


def test_the_two_cases_are_parameters_of_the_doors_set() -> None:
    """Two of the three are witnessed by a run; the third by its reader's call alone."""
    assert set(products.LEVEL_P_NOT_READ) == {*CASES, BENEFIT}
    assert set(MOVED) == set(CASES)


@pytest.mark.parametrize("parameter", sorted(CASES), ids=["POL-021", "POL-240"])
def test_a_level_p_value_stands_in_the_bundle_and_moves_no_figure(parameter: str) -> None:
    """Forms A and B: the registry's row alone, then the registry's row and one ``OBLIGATION``
    row of level ``P`` for each booked line with the value stated — and the key's checkpoints
    hold in both, figure for figure."""
    _, value, of_the_registry, obligations = CASES[parameter]
    as_it_is = _key(parameter)
    assert _rows(as_it_is, parameter) == [of_the_registry]
    assert_checkpoints(as_it_is, run_engine(as_it_is))

    stated = _at_level_p(as_it_is, parameter, value)
    assert value != of_the_registry[2]
    assert _rows(stated, parameter) == [
        of_the_registry,
        *(("OBLIGATION", subject, value, "P") for subject in obligations),
    ]
    assert_checkpoints(stated, run_engine(stated))


@pytest.mark.parametrize("parameter", sorted(CASES), ids=["POL-021", "POL-240"])
def test_the_same_value_at_the_contract_moves_the_figures(parameter: str) -> None:
    """Form C, the control: one ``CONTRACT`` row beside the registry's, and the key's figures
    are no longer met — the engine has a rule for the value, and takes it where it looks."""
    (_, key_id), value, of_the_registry, _ = CASES[parameter]
    stated = _at_the_contract(_key(parameter), parameter, value)
    contract = stated.key.contracts[0].external_id
    assert _rows(stated, parameter) == sorted([of_the_registry, ("CONTRACT", contract, value, "C")])
    with pytest.raises(CheckpointMismatchError) as caught:
        assert_checkpoints(stated, run_engine(stated))
    moved = caught.value.mismatches
    count, first = MOVED[parameter]
    assert len(moved) == count, key_id
    assert (
        moved[0].checkpoint,
        moved[0].subject,
        moved[0].field,
        str(moved[0].expected),
        str(moved[0].actual),
    ) == first
