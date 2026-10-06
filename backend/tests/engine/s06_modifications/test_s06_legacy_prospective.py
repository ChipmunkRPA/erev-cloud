"""Stage 06 legacy prospective template: ENGINE_SPEC EX-06-H and catch-up nodes by cause (ENB-8).

ENGINE_SPEC §6.5 S06-R-28 to S06-R-32, §6.7 EX-06-H, §0.9 CV-50, CV-56 and Table 0.9-A; POLICIES
ALG-04 §2.5.7, POL-081, POL-107; legacy 03 §3.1 to §3.6; golden ``catchup-10-Contract1-POB3``
(tolerance 1e-4; D-17); 03 REQ-MOD-015. Golden Contract 1 is folded by the real stages 01 to 05
under ``LEGACY_PARITY``, and the fake stage 04 price function follows ENGINE_SPEC §4.2 (D-81).
Every stage 06 trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.trace import TraceBuilder, TraceNode
from test_s06_prospective import checked, obligation, usd
from test_tc_rm import amendments, apply, catch_up, golden, near, remaining

EX_TOLERANCE = Fraction(1, 10**4)  # D-17: the worked examples show four places
KEYS = ("POB #1", "POB #2", "POB #3", "POB #4")


def column(node: TraceNode, name: str) -> dict[str, Fraction]:
    """One per-obligation column of a template ``allocated_exact@`` node, by subject key."""
    keys = node.params["keys"].split("|")
    return dict(zip(keys, (Fraction(item) for item in node.params[name].split("|")), strict=True))


def test_ex_06_h_prospective_reduction() -> None:
    """Golden Contract 1 after step 09: POB #1 −5 units for −500.00 on 2023-06-15 (step 10)."""
    folded = golden("Contract 1", "10")
    (step_10,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, step_10, tb)
    assert after.findings == ()
    nodes = checked(tb)
    subjects = {key: obligation(after, key).subject_key for key in KEYS}
    exact_node = nodes[f"allocated_exact@{step_10.event_key}:{subjects['POB #1']}:-"]
    assert exact_node.formula_id == "mod.legacy.prospective.v1"
    # Before the event (after the 2023-04-30 return restored POB #1 to 5 units).
    before_allocation = column(exact_node, "remaining_allocation")
    for key, value in zip(KEYS, ("322.1011", "118.5332", "48.3152", "644.2022"), strict=True):
        assert near(before_allocation[subjects[key]], value, EX_TOLERANCE), key
    before_ssp = column(exact_node, "remaining_ssp")
    assert [before_ssp[subjects[key]] for key in KEYS] == [500, 184, 75, 1000]
    revenue = column(exact_node, "revenue")
    assert near(revenue[subjects["POB #2"]], "118.5332", EX_TOLERANCE)
    assert revenue[subjects["POB #1"]] == revenue[subjects["POB #4"]] == 0
    # Band [−517.5, −382.5]; the billing lies inside, so the modification SSP is −500.
    ssp = nodes[f"mod_ssp@{step_10.event_key}:{subjects['POB #1']}:-"]
    assert (ssp.value, ssp.params["lows"], ssp.params["highs"]) == ("-500", "-1035/2", "-765/2")
    # Weights 0 / 184 / 75 / 1,000 (RemSSP POB #1 0) and pool 633.1516 = Σ (X′ − E before).
    weights = [obligation(after, key).segments[-1].remaining_ssp for key in KEYS]
    assert weights == [0, 184, 75, 1000]
    shares = {
        key: obligation(after, key).segments[-1].x_exact - revenue[subjects[key]] for key in KEYS
    }
    assert near(sum(shares.values(), Fraction(0)), "633.1516", EX_TOLERANCE)
    assert shares["POB #1"] == 0
    for key, value in {"POB #2": "92.5337", "POB #4": "502.9004"}.items():
        assert near(shares[key], value, EX_TOLERANCE), key
    # POB #3 before its catch-up: 633.1516 × 75 ÷ 1,259 = 37.717532 (legacy 03 §5.6). EX-06-H prints
    # "37.7178…", which its own CU −5.2988 and remaining 43.0163 contradict (L2-3-Q-44).
    assert shares["POB #3"] == shares["POB #4"] * 75 / 1000
    assert near(shares["POB #3"], "37.717532", Fraction(1, 10**6))
    # POB #3 is nondistinct: progress 0.5 ÷ (0.5 + 0.5) = 0.5.
    pob3 = obligation(after, "POB #3").segments[-1]
    assert pob3.base_revenue_exact == pob3.x_exact / 2
    assert near(catch_up(nodes, step_10, subjects["POB #3"]), "-5.2988", EX_TOLERANCE)
    assert near(remaining(after, "POB #3"), "43.0163", EX_TOLERANCE)
    # TP after 800.0000: Σ X′ exactly, and Σ a_posted is the allocation basis (S06-INV-01).
    total = sum((obligation(after, key).segments[-1].x_exact for key in KEYS), Fraction(0))
    assert total == 800
    assert sum(obligation(after, key).segments[-1].a_posted for key in KEYS) == usd("800.00")
    assert after.tp_history[-1].allocation_basis.posted == usd("800.00")


def test_mod_015_catch_up_nodes_by_cause() -> None:
    """REQ-MOD-015: the EX-06-H catch-up node of POB #3, with its exact value and its cause."""
    folded = golden("Contract 1", "10")
    (step_10,) = amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, folded.state, step_10, tb)
    assert after.findings == ()
    nodes = checked(tb)
    assert step_10.event_key.startswith("Contract 1/EV-")
    node = nodes[f"catch_up@{step_10.event_key}:Contract 1/POB %233:-"]
    assert (node.value, node.formula_id, node.params["cause"]) == (
        "-5.30",
        "mod.catch_up.v1",
        "MODIFICATION",
    )
    assert node.rounding_residue is not None
    exact = Fraction(Decimal(node.value)) + Fraction(Decimal(node.rounding_residue))
    assert near(exact, "-5.2988", EX_TOLERANCE)
    # Catch-up nodes exist only for the obligations that take a boundary segment at the event
    # (L2-3-Q-43); the distinct obligations publish no disclosure amount, posted or exact.
    published = {
        node_id.split(":", 1)[1].rsplit(":", 1)[0]
        for node_id in nodes
        if node_id.startswith(f"catch_up@{step_10.event_key}:")
    }
    boundary = {
        ob.subject_key for ob in after.obligations if ob.segments[-1].event_key == step_10.event_key
    }
    assert published == boundary == {obligation(after, key).subject_key for key in KEYS}
    for key in ("POB #1", "POB #2", "POB #4"):
        subject = obligation(after, key).subject_key
        assert nodes[f"catch_up@{step_10.event_key}:{subject}:-"].value == "0.00", key
        assert catch_up(nodes, step_10, subject) == 0, key
