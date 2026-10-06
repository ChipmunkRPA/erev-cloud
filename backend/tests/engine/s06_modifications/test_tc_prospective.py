"""Stage 06 legacy prospective template: legacy 03 TC-01, TC-02, TC-03 and TC-05 (ENB-8).

ENGINE_SPEC §6.5 S06-R-28 to S06-R-32; POLICIES ALG-04 §2.5.7, POL-081, POL-107; legacy 03
§3.1 to §3.6, §5.4, §5.6 and §7.3 (tolerance 1e-6; D-17); DEVIATIONS DEV-052, DEV-053 and
DEV-055. The golden streams are folded by the real stages 01 to 05 under ``LEGACY_PARITY``, and
every golden modification step is applied by the real templates. TC-04 (the continuation fix) is
ENB-5's ``test_tc_prospective_04_continuation_values``. The fake stage 04 price function follows
ENGINE_SPEC §4.2 (D-81). Every stage 06 trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.trace import TraceBuilder
from test_s06_prospective import checked, obligation, usd
from test_tc_rm import amendments, apply, catch_up, golden, near, remaining


def test_tc_prospective_01_contract1_06_15() -> None:
    """UAT 06.15, Contract 1: POB #1 −5 / −500.00 (golden step 10)."""
    folded = golden("Contract 1", "10")
    (step_10,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, step_10, tb)
    assert after.findings == ()
    nodes = checked(tb)
    allocations = {
        "POB #1": "0",
        "POB #2": "92.533678",
        "POB #3": "43.016348",
        "POB #4": "502.900425",
    }
    for key, value in allocations.items():
        assert near(remaining(after, key), value), key
    assert near(catch_up(nodes, step_10, obligation(after, "POB #3").subject_key), "-5.298816")
    for key in ("POB #1", "POB #2", "POB #4"):  # distinct obligations take no catch-up (§3.5)
        assert catch_up(nodes, step_10, obligation(after, key).subject_key) == 0, key
    pob1 = obligation(after, "POB #1")
    segment = pob1.segments[-1]
    assert (segment.basis, segment.progress_measure) == ("PROSPECTIVE", "UNITS_SINCE_BOUNDARY")
    assert (segment.totals.quantity, segment.remaining_ssp, segment.unit_ssp) == (0, 0, 0)
    assert (segment.x_exact, segment.a_posted, segment.remaining_billing_plan) == (0, 0, 0)
    assert (pob1.quantity, pob1.stated_price, pob1.last_modification_key) == (0, 0, "MOD-10")
    assert after.tp_history[-1].allocation_basis.posted == usd("800.00")


def test_tc_prospective_02_contract3_07_15() -> None:
    """UAT 07.15, Contract 3: POB #1 +2 / +500.00, band [153, 207] (golden step 11)."""
    folded = golden("Contract 3", "11")
    (step_11,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, step_11, tb)
    assert after.findings == ()
    nodes = checked(tb)
    pob1 = obligation(after, "POB #1")
    assert nodes[f"mod_ssp@{step_11.event_key}:{pob1.subject_key}:-"].value == "207"
    segment = pob1.segments[-1]
    assert (segment.totals.quantity, segment.remaining_ssp, segment.unit_ssp) == (7, 707, 101)
    assert segment.remaining_billing_plan == 1000
    allocations = {
        "POB #1": "587.303258",
        "POB #2": "152.848373",
        "POB #3": "55.308745",
        "POB #4": "830.697678",
    }
    for key, value in allocations.items():
        assert near(remaining(after, key), value), key
    assert near(catch_up(nodes, step_11, obligation(after, "POB #3").subject_key), "6.993581")
    assert near(obligation(after, "POB #3").segments[-1].base_revenue_exact, "55.308745")
    assert after.tp_history[-1].allocation_basis.posted == usd("1800.00")


def test_tc_prospective_03_contract4_07_15() -> None:
    """UAT 07.15, Contract 4: POB #3 +2 / +300.00, band [300, 300] (golden step 11)."""
    folded = golden("Contract 4", "11")
    (step_11,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, step_11, tb)
    assert after.findings == ()
    nodes = checked(tb)
    pob3 = obligation(after, "POB #3")
    assert nodes[f"mod_ssp@{step_11.event_key}:{pob3.subject_key}:-"].value == "300"
    allocations = {
        "POB #1": "362.382747",
        "POB #2": "322.117998",
        "POB #3": "355.277203",
        "VC #1": "0",
    }
    for key, value in allocations.items():
        assert near(remaining(after, key), value), key
    for key in ("POB #1", "POB #2", "POB #3", "VC #1"):  # POB #3 has nothing delivered yet
        subject = obligation(after, key).subject_key
        assert catch_up(nodes, step_11, subject) == 0, key
        assert nodes[f"catch_up@{step_11.event_key}:{subject}:-"].value == "0.00", key
    segment = pob3.segments[-1]
    assert (segment.totals.start_date, segment.totals.end_date) == (
        date(2023, 6, 1),
        date(2024, 5, 31),
    )
    assert pob3.end_date == date(2024, 5, 31)
    assert (segment.totals.quantity, segment.remaining_ssp, segment.remaining_billing_plan) == (
        3,
        450,
        450,
    )
    vc = obligation(after, "VC #1").segments[-1]
    assert (vc.x_exact, vc.remaining_ssp, vc.remaining_billing_plan) == (0, 0, -100)
    assert after.tp_history[-1].allocation_basis.posted == usd("1250.00")


def test_tc_prospective_05_end_state() -> None:
    """UAT end state: golden Contract 3 through step 14, every template step applied for real."""
    folded = golden("Contract 3", "14")
    step_11, step_12, step_13 = amendments(folded.state)
    st = apply(folded, folded.state, step_11)
    assert st.findings == ()
    st = apply(folded, st, step_12)
    assert st.findings == ()
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    st = apply(folded, st, step_13, tb)
    assert st.findings == ()
    nodes = checked(tb)
    # Golden step 13 (legacy 03 §5.4): POB #3 catch-up +32.139412 and TP 2,600.00.
    assert near(catch_up(nodes, step_13, obligation(st, "POB #3").subject_key), "32.139412")
    assert st.tp_history[-1].allocation_basis.posted == usd("2600.00")
    # POB #5 added by the template with its creation values (S06-R-31; DEV-052).
    pob5 = obligation(st, "POB #5")
    assert (pob5.original_stated_price, pob5.original_quantity) == (1000, 5)
    assert pob5.ssp is not None
    assert (pob5.ssp.low, pob5.ssp.high, pob5.ssp.selected) == (750, 750, 750)
    assert (pob5.original_total_contract_price, pob5.original_total_contract_ssp) == (2600, 1410)
    assert near(pob5.original_allocation.x_exact, "1268.113933")
    expected = {
        "POB #1": "678.018250",
        "POB #2": "464.523854",
        "POB #3": "189.343962",
        "POB #4": "0",
        "POB #5": "1268.113933",
    }
    for key, value in expected.items():
        ob = obligation(st, key)
        segment = ob.segments[-1]
        assert segment.event_key == step_13.event_key, key
        point = st.ledger.at(ob.subject_key)  # after the 10.31 full delivery
        since = point.delivered_cum - point.returned_cum - segment.base_progress.delivered_cum
        assert segment.progress_measure == "UNITS_SINCE_BOUNDARY", key
        assert since == segment.totals.quantity, key  # f = 1 on the final segment (CV-62)
        assert near(segment.x_exact, value), key  # E = x_k at f = 1 (CV-63)
    assert sum((obligation(st, key).segments[-1].x_exact for key in expected), Fraction(0)) == 2600
