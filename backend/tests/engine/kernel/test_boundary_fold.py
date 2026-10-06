"""Boundary fold over stages 01 to 08 (ENGINE_SPEC §0.3 ``fold_book``; CV-10, CV-11; ENB-13).

``support.fold.fold_book`` folds the inception state and then every Table 0.3-A event through
``BOUNDARY_HANDLERS``, with the real stage 04 price function bound (L2-3-Q-1). Tolerance 1e-4
(golden `catchup-09-Contract2-POB1`; legacy 05 TC-pob-vc-01). No database (DG-TST-18).
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from erev_engine.money import format_money
from erev_engine.stages.state import AllocatedState
from erev_engine.trace import reevaluate
from support import golden_streams
from support.fold import fold_trace

TOLERANCE = Fraction(1, 10**4)


def remaining(st: AllocatedState, key: str) -> Fraction:
    """Legacy ``Current Remaining Allocation``: X − E at the boundary of the last segment."""
    ob = next(item for item in st.obligations if item.obligation_key == key)
    segment = ob.segments[-1]
    return segment.x_exact - segment.base_revenue_exact


def near(value: Fraction, expected: str) -> bool:
    return abs(value - Fraction(Decimal(expected))) <= TOLERANCE


def test_fold_golden_contract2_through_step_09() -> None:
    value = golden_streams.stream("Contract 2", "09").input_bundle(preset="LEGACY_PARITY")
    st, trace = fold_trace(value, "ASC606")
    assert st.findings == ()
    # Golden steps 08 (retrospective template) and 09 (POB-specific VC) through the real handlers.
    assert near(remaining(st, "POB #1"), "519.6617")
    assert near(remaining(st, "POB #3"), "84.9673")
    assert [ob.last_modification_key for ob in st.obligations] == ["MOD-09"] * 4
    # Stage 04 prices the booking lines; the binding adds +400.00 (step 08) and −200.00 (step 09).
    assert [format_money(tp.allocation_basis.posted, 2) for tp in st.tp_history] == [
        "900.00",
        "1300.00",
        "1100.00",
    ]
    assert sum(ob.segments[-1].a_posted for ob in st.obligations) == 110000  # S06-INV-01
    # The fold trace re-evaluates: posted nodes exactly; exact nodes within 1e-12, because stage
    # 05 exact nodes are re-evaluated from inputs encoded at 18 places (L2-2-Q-38, L2-2-Q-40).
    recomputed = reevaluate(trace)
    for node in trace.nodes:
        if node.rounding_residue is not None:
            assert recomputed[node.id] == node.value, node.id
        else:
            gap = abs(Fraction(Decimal(recomputed[node.id])) - Fraction(Decimal(node.value)))
            assert gap <= Fraction(1, 10**12), (node.id, node.value, recomputed[node.id])
    assert any(node.id.startswith("catch_up@Contract 2/EV-000010:") for node in trace.nodes)
