"""Stage 06 legacy POB-specific VC template: legacy 05 TC-pob-vc-01 to 08, 12 and 17 (ENB-7).

ENGINE_SPEC §6.5 S06-R-28 to S06-R-32, §6.6; POLICIES ALG-04 §2.5.7, POL-107, §6.3; legacy 05 §7.3
(tolerance 1e-6; D-17); DEVIATIONS DEV-040, DEV-056, DEV-083.

Legacy 05 §7.3 numbers its snapshots from 00, so its "step 07" is golden step 08 (the 05.15
retrospective template), "step 10" is golden step 11 and "step 13" is golden step 14 (L2-3-Q-35).
Golden Contract 2 is folded by the real stages 01 to 05 under ``LEGACY_PARITY``, and golden steps
08 and 09 are applied by the real templates. TC-pob-vc-07 starts after golden step 11, which the
real legacy prospective template applies (ENB-8; L2-3-Q-31 closed). The fake stage 04 price
function follows ENGINE_SPEC §4.2 (D-81). Every stage 06 trace re-evaluates node for node
(DG-ENG-04).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.stages.state import AllocatedState, EventView
from erev_engine.trace import TraceBuilder, TraceNode
from support import golden_streams
from test_s06_prospective import checked, obligation, usd
from test_tc_rm import (
    Folded,
    amended,
    amendments,
    apply,
    catch_up,
    fold,
    near,
    remaining,
    template_line,
)

CHANGE_DATE = date(2023, 5, 31)


def after_retro(*changes: tuple[str, str, str]) -> tuple[Folded, AllocatedState, EventView]:
    """Golden Contract 2 after step 08, with a POB-specific price change of ``changes``
    ((obligation key, quantity, billing)) on 2023-05-31 that repeats the stored attributes."""
    value = golden_streams.stream("Contract 2", "08").input_bundle(preset="LEGACY_PARITY")
    lines = [template_line(value, key, quantity, billing) for key, quantity, billing in changes]
    folded = fold(amended(value, "MOD-PV", CHANGE_DATE, "pob_price_change", lines, "LEGACY_POB_VC"))
    step_08, change = amendments(folded.state)
    st = apply(folded, folded.state, step_08)
    assert st.findings == ()
    return folded, st, change


def changed(
    folded: Folded, st: AllocatedState, ev: EventView
) -> tuple[AllocatedState, dict[str, TraceNode]]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, st, ev, tb)
    return after, checked(tb)


def revenue(st: AllocatedState, key: str) -> Fraction:
    """Legacy ``Current Rev Rec - Cumulative``: E at the boundary of the last segment."""
    return obligation(st, key).segments[-1].base_revenue_exact


def cu(nodes: Mapping[str, TraceNode], ev: EventView, st: AllocatedState, key: str) -> Fraction:
    return catch_up(nodes, ev, obligation(st, key).subject_key)


def test_tc_pob_vc_01_contract2_pob1_minus_200() -> None:
    folded, st, ev = after_retro(("POB #1", "0", "-200"))
    after, nodes = changed(folded, st, ev)
    assert after.findings == ()
    assert near(remaining(after, "POB #1"), "519.661711")
    assert near(cu(nodes, ev, after, "POB #1"), "-18.681319")
    assert near(revenue(after, "POB #1"), "53.540904")
    assert near(remaining(after, "POB #2"), "385.185185")
    assert cu(nodes, ev, after, "POB #2") == 0
    assert near(remaining(after, "POB #3"), "84.967320")
    assert cu(nodes, ev, after, "POB #3") == 0
    segment = obligation(after, "POB #1").segments[-1]
    assert (segment.totals.quantity, segment.remaining_ssp, segment.unit_ssp) == (
        9,
        Fraction(1485, 2),
        Fraction(165, 2),
    )
    assert segment.remaining_billing_plan == 780  # DEV-083: the billing plan moves with M
    assert after.tp_history[-1].allocation_basis.posted == usd("1100.00")


def test_tc_pob_vc_02_pob2_plus_90() -> None:
    folded, st, ev = after_retro(("POB #2", "0", "90"))
    after, nodes = changed(folded, st, ev)
    assert after.findings == ()
    assert cu(nodes, ev, after, "POB #2") == 0  # nothing delivered: CU 0.00
    assert nodes[f"catch_up@{ev.event_key}:{obligation(after, 'POB #2').subject_key}:-"].value == (
        "0.00"
    )
    assert near(remaining(after, "POB #2"), "475.185185")


def test_tc_pob_vc_03_pob1_plus_100() -> None:
    folded, st, ev = after_retro(("POB #1", "0", "100"))
    after, nodes = changed(folded, st, ev)
    assert after.findings == ()
    assert near(cu(nodes, ev, after, "POB #1"), "9.340659")
    assert near(revenue(after, "POB #1"), "81.562882")
    assert near(remaining(after, "POB #1"), "791.639733")


def test_tc_pob_vc_04_nondistinct_pob3_plus_30() -> None:
    folded, st, ev = after_retro(("POB #3", "0", "30"))
    after, nodes = changed(folded, st, ev)
    assert after.findings == ()
    assert near(cu(nodes, ev, after, "POB #3"), "12.000000")  # +30 × 60 ÷ 150
    assert near(revenue(after, "POB #3"), "68.644880")
    assert near(remaining(after, "POB #3"), "102.967320")


def test_tc_pob_vc_05_two_lines_one_file() -> None:
    folded, st, ev = after_retro(("POB #1", "0", "-200"), ("POB #2", "0", "100"))
    after, nodes = changed(folded, st, ev)
    assert after.findings == ()
    assert near(remaining(after, "POB #1"), "519.661711")
    assert near(cu(nodes, ev, after, "POB #1"), "-18.681319")
    assert near(revenue(after, "POB #1"), "53.540904")
    assert near(remaining(after, "POB #2"), "485.185185")
    assert cu(nodes, ev, after, "POB #2") == 0


def test_tc_pob_vc_06_fully_delivered_pob2_plus_60() -> None:
    """After golden step 14 (full delivery 10.31): C2 POB #2 +60.00 on 2023-11-15."""
    value = golden_streams.stream("Contract 2", "14").input_bundle(preset="LEGACY_PARITY")
    lines = [template_line(value, "POB #2", "0", "60")]
    folded = fold(
        amended(value, "MOD-PV06", date(2023, 11, 15), "pob_price_change", lines, "LEGACY_POB_VC")
    )
    step_08, step_09, change = amendments(folded.state)
    st = folded.state
    for ev in (step_08, step_09):
        st = apply(folded, st, ev)
        assert st.findings == ()
    after, nodes = changed(folded, st, change)
    assert after.findings == ()
    subject = obligation(after, "POB #2").subject_key
    assert catch_up(nodes, change, subject) == 60
    assert nodes[f"catch_up@{change.event_key}:{subject}:-"].value == "60.00"
    assert near(revenue(after, "POB #2"), "445.185185")
    assert remaining(after, "POB #2") == 0  # exactly 0.00, never −5.684342e-14
    segment = obligation(after, "POB #2").segments[-1]
    assert (segment.totals.quantity, segment.unit_ssp) == (0, 0)


def test_tc_pob_vc_07_untargeted_obligations_unchanged() -> None:
    """After golden step 11 (07.15 prospective +2 / +500.00): C3 POB #1 +100.00 on 2023-07-31."""
    value = golden_streams.stream("Contract 3", "11").input_bundle(preset="LEGACY_PARITY")
    lines = [template_line(value, "POB #1", "0", "100")]
    folded = fold(
        amended(value, "MOD-PV07", date(2023, 7, 31), "pob_price_change", lines, "LEGACY_POB_VC")
    )
    step_11, change = amendments(folded.state)
    st = apply(folded, folded.state, step_11)  # the real prospective template (ENB-8)
    assert st.findings == ()
    after, nodes = changed(folded, st, change)
    assert after.findings == ()
    assert cu(nodes, change, after, "POB #1") == 0
    assert near(remaining(after, "POB #1"), "687.303258")
    # DEV-056: no latent true-up on the untargeted software (legacy +17.157586).
    assert cu(nodes, change, after, "POB #2") == 0
    assert near(revenue(after, "POB #2"), "118.533201")
    assert near(remaining(after, "POB #2"), "152.848373")
    assert after.tp_history[-1].allocation_basis.posted == usd("1900.00")


def test_tc_pob_vc_08_quantity_on_vc_event_rejected() -> None:
    folded, st, ev = after_retro(("POB #1", "2", "-200"))
    after, nodes = changed(folded, st, ev)
    (finding,) = after.findings
    assert (finding.code, finding.severity, finding.stage) == (
        "VC_QUANTITY_NOT_ALLOWED",
        "ERROR",
        6,
    )
    assert finding.detail["obligation_key"] == "POB #1"
    assert nodes == {}
    assert after.obligations == st.obligations  # CV-15: no segment


def test_tc_pob_vc_12_vc_pseudo_line_target_rejected() -> None:
    folded, st, ev = after_retro(("VC #1", "0", "-50"))
    after, nodes = changed(folded, st, ev)
    # The template checks in order (S06-R-28): the zero-allocation VC line also goes below 0.
    codes = [(finding.code, finding.severity) for finding in after.findings]  # CV-43 order
    assert codes == [("VC_ALLOCATION_NEGATIVE", "ERROR"), ("VC_TARGET_INVALID", "ERROR")]
    assert {finding.detail["obligation_key"] for finding in after.findings} == {"VC #1"}
    assert nodes == {}
    assert after.obligations == st.obligations


def test_tc_pob_vc_17_line_total_below_zero() -> None:
    """DEV-040: POB #1 −900.00 against a line total of 773.202614."""
    folded, st, ev = after_retro(("POB #1", "0", "-900"))
    after, nodes = changed(folded, st, ev)
    (finding,) = after.findings
    assert (finding.code, finding.severity) == ("VC_ALLOCATION_NEGATIVE", "ERROR")
    assert near(Fraction(finding.detail["allocation"]), "-126.797386")
    assert nodes == {}
    assert after.obligations == st.obligations
