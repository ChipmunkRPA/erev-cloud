"""Component choices are identities of the selected calculation, never guessed history."""

from dataclasses import replace

import pytest

from erev_api.domain.contracts.combined_components import keys
from erev_engine.trace import Trace, TraceNode


def test_retained_keys_preserve_delimiters_and_require_matching_subject():
    node = TraceNode(
        id="stated_price:C/HOST:-",
        measure="stated_price",
        value="100",
        currency="USD",
        formula_id="pob.merge.v1",
        inputs=(),
        params={
            "lessor_judgement_keys": "JDG-1",
            "lessor_component_keys": '["HOST", "SERVICE,1", "HOST"]',
        },
        rounding_residue=None,
        narrative_key="pob.merge.v1",
    )
    trace = Trace(1, "test", (node,), {})
    assert keys(trace, "C", "HOST") == ["HOST", "SERVICE,1"]
    assert keys(trace, "OTHER", "HOST") == []
    assert keys(None, "C", "HOST") == []
    legacy = replace(trace, nodes=(replace(node, params={"lessor_judgement_keys": "JDG-1"}),))
    assert keys(legacy, "C", "HOST") == []
    malformed = replace(
        trace,
        nodes=(
            replace(
                node,
                params={
                    **node.params,
                    "lessor_component_keys": '["HOST", 1]',
                },
            ),
        ),
    )
    with pytest.raises(ValueError, match="Invalid retained"):
        keys(malformed, "C", "HOST")
