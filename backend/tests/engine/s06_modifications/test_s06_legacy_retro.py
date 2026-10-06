"""Stage 06 legacy templates: ENGINE_SPEC EX-06-F (ENB-6) and EX-06-G (ENB-7).

ENGINE_SPEC §6.5 S06-R-28 to S06-R-32, §6.7 EX-06-F, EX-06-G; POLICIES ALG-04 §2.5.7; golden
``catchup-08-Contract2-POB1``, ``catchup-08-Contract2-POB3`` and ``catchup-09-Contract2-POB1``
(tolerance 1e-4; D-17). Golden Contract 2 is folded by the real stages 01 to 05 under
``LEGACY_PARITY``, and the fake stage 04 price function follows ENGINE_SPEC §4.2 (D-81). Every stage
06 trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.trace import TraceBuilder
from test_s06_prospective import checked, obligation
from test_tc_rm import amendments, apply, catch_up, golden, near, remaining

EX_TOLERANCE = Fraction(1, 10**4)  # D-17: the worked examples show four places


def test_ex_06_f_retrospective_increase() -> None:
    """Golden Contract 2 after step 07: POB #1 +2 units for 400.00 on 2023-05-15, band 153-207."""
    folded = golden("Contract 2", "08")
    (step_08,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, step_08, tb)
    assert after.findings == ()
    nodes = checked(tb)
    pob1, pob3 = obligation(after, "POB #1"), obligation(after, "POB #3")
    assert nodes[f"mod_ssp@{step_08.event_key}:{pob1.subject_key}:-"].value == "207"
    ratio = Fraction(1300, 1377)  # r_c = TP_c ÷ SSP_c
    assert pob1.segments[-1].x_exact == ratio * (Fraction(1485, 2) + Fraction(153, 2))
    assert pob1.segments[-1].base_revenue_exact == ratio * Fraction(153, 2)
    assert pob3.segments[-1].x_exact == ratio * (90 + 60)
    assert near(catch_up(nodes, step_08, pob1.subject_key), "13.3761", EX_TOLERANCE)
    assert near(catch_up(nodes, step_08, pob3.subject_key), "10.4910", EX_TOLERANCE)
    assert near(remaining(after, "POB #1"), "700.9804", EX_TOLERANCE)
    assert near(remaining(after, "POB #3"), "84.9673", EX_TOLERANCE)
    assert near(pob1.segments[-1].base_revenue_exact, "72.2222", EX_TOLERANCE)


def test_ex_06_g_pob_specific_vc() -> None:
    """Golden Contract 2 after step 08: M = −200.00 on POB #1 on 2023-05-31 (golden step 09)."""
    folded = golden("Contract 2", "09")
    step_08, step_09 = amendments(folded.state)
    st = apply(folded, folded.state, step_08)
    assert st.findings == ()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, st, step_09, tb)
    assert after.findings == ()
    nodes = checked(tb)
    pob1 = obligation(after, "POB #1")
    # Closed form M × D ÷ W, the latent term being 0: −200 × 76.5 ÷ 819.
    assert catch_up(nodes, step_09, pob1.subject_key) == Fraction(-200) * Fraction(153, 2) / 819
    assert near(catch_up(nodes, step_09, pob1.subject_key), "-18.6813", EX_TOLERANCE)
    assert near(remaining(after, "POB #1"), "519.6617", EX_TOLERANCE)
    assert near(pob1.segments[-1].base_revenue_exact, "53.5409", EX_TOLERANCE)
    for key in ("POB #2", "POB #3", "VC #1"):  # untargeted obligations unchanged (DEV-056)
        before, now = obligation(st, key).segments[-1], obligation(after, key).segments[-1]
        assert (now.x_exact, now.base_revenue_exact) == (before.x_exact, before.base_revenue_exact)
        assert catch_up(nodes, step_09, obligation(after, key).subject_key) == 0
