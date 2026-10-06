"""PROP:P14 trace re-evaluation (dev-guide §9.7 P14, DG-KRN-EXP-04, DG-ENG-04; ENGINE_SPEC CV-52;
BUILD_SPEC END-13).

For generated groups computed in the ASC606 and IFRS15 books, and for the golden Contract 2 step
09 bundle in the ASC606 and LEGACY books, ``reevaluate(trace)`` recomputes every node from its
inputs and params and equals every stored value exactly; every node's formula id is registered in
``FORMULAS``. The answer-key runner (DG-AK-54) and the stage tests assert the same identity on
their own worlds.
"""

from __future__ import annotations

import pytest
from erev_engine import compute
from erev_engine.bundle import OutputBundle
from erev_engine.formulas import FORMULAS
from erev_engine.trace import reevaluate
from hypothesis import given
from support import golden_streams, intent_totals
from support.prop_worlds import WorldSpec, bundle
from support.strategies import world_specs

pytestmark = pytest.mark.property


def _assert_reproduced(output: OutputBundle) -> None:
    for book in output.books:
        stored = {node.id: node.value for node in book.trace.nodes}
        assert reevaluate(book.trace) == stored, book.book_code
        unregistered = sorted(
            {n.formula_id for n in book.trace.nodes if n.formula_id not in FORMULAS}
        )
        assert unregistered == [], book.book_code


@given(spec=world_specs())
def test_p14_reevaluate_reproduces_every_node(spec: WorldSpec) -> None:
    _assert_reproduced(compute(bundle(spec, books=("ASC606", "IFRS15"))))


def test_p14_golden_contract2_step09_reproduces_every_node() -> None:
    stream = golden_streams.stream("Contract 2", "09")
    value = intent_totals.activated(
        stream.input_bundle(preset="LEGACY_PARITY", books=intent_totals.BOOKS)
    )
    output = compute(value)
    assert [book.book_code for book in output.books] == list(intent_totals.BOOKS)
    _assert_reproduced(output)
