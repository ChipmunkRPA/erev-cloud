"""Stage 05 targeted VC, discount exception, residual approach and pipeline order.

ENGINE_SPEC §5.4 S05-R-09, S05-R-11 to S05-R-15; §5.6 EX-05-C, EX-05-D; POLICIES §3.2 (CHK-032 to
CHK-034), POL-044, POL-075, POL-076 rev 1.2; BUILD_SPEC ENA-12. The FASB Example 34 bundles follow
the answer keys ``docs/accounting/answer-keys/alc/ALC-CHK-03[234]-*.yaml``. Stages 01 to 05 run for
real with one trace builder for stages 03 to 05. No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
import itertools
from fractions import Fraction

from erev_engine.money import format_exact
from erev_engine.stages import (
    s05_allocation,
)
from erev_engine.stages.state import (
    Quota,
    Quota1,
)
from support.allocation_worlds import (
    BUNDLE,
    CONTRACT,
    ELEMENT,
    ESTIMATED_D,
    EX_34,
    EX_35,
    GROUP,
    RESIDUAL_D,
    TOLERANCE,
    approval,
    by_key,
    element,
    entry,
    ex_34,
    exact,
    fold,
    line,
    native,
    override,
    posted,
    share_id,
)


def test_chk_034_discount_exception_case_a() -> None:
    _, priced, allocated, traced = fold(ex_34("40.00", "30.00", "30.00", judgements=[approval()]))
    assert priced.tp.allocation_basis.posted == 10_000
    assert allocated.findings == ()
    assert posted(allocated) == {"L1-A": 4_000, "L2-B": 3_300, "L3-C": 2_700}
    assert exact(allocated) == {"L1-A": 40, "L2-B": 33, "L3-C": 27}
    (proposal,) = allocated.proposals
    assert (proposal.kind, proposal.subject_key, proposal.summary) == (
        "DISCOUNT_EXCEPTION",
        CONTRACT,
        None,
    )
    assert dict(proposal.detail) == {
        "approved": "true",
        "bundle_price": "60",
        "bundle_product_code": BUNDLE,
        "component_ssp": "100",
        "d_bundle": "40",
        "d_contract": "40",
        "judgement_key": "J-DISC-EXC",
        "obligations": "K-01/L2-B|K-01/L3-C",
        "tolerance": "0.02",
    }
    discount = traced[f"discount_exception@{BUNDLE}:{CONTRACT}:-"]
    assert (discount.formula_id, discount.value, discount.params["mode"]) == (
        "alloc.discount_exception.v1",
        "60",
        "remainder",
    )
    assert discount.inputs == ("tp_allocation_basis:CG-1:-", "original_ssp_selected:K-01/L1-A:-")
    assert [traced[f"discount_exception_share:K-01/{key}:-"].value for key in ("L2-B", "L3-C")] == [
        "33",
        "27",
    ]
    assert traced["total_ssp:CG-1:-"].params == {"path": "exceptions", "role": "total"}

    # Without the reviewed judgement the exception is proposed only, and relative SSP applies.
    _, _, proposed, traced = fold(ex_34("40.00", "30.00", "30.00"))
    assert proposed.findings == ()
    (proposal,) = proposed.proposals
    assert (proposal.detail["approved"], proposal.detail["judgement_key"]) == ("false", "")
    assert posted(proposed) == {"L1-A": 2_857, "L2-B": 3_929, "L3-C": 3_214}
    assert f"discount_exception@{BUNDLE}:{CONTRACT}:-" not in traced

    # DISABLED (parity) never proposes, whatever the judgement.
    disabled = ex_34(
        "40.00",
        "30.00",
        "30.00",
        judgements=[approval()],
        overrides={"alloc.discount_exception": "DISABLED"},
    )
    _, _, parity, _ = fold(disabled)
    assert parity.proposals == ()
    assert posted(parity) == {"L1-A": 2_857, "L2-B": 3_929, "L3-C": 3_214}


def test_chk_033_residual_case_b() -> None:
    value = ex_34("40.00", "30.00", "30.00", "30.00", residual=RESIDUAL_D, judgements=[approval()])
    _, priced, allocated, traced = fold(value)
    assert priced.tp.allocation_basis.posted == 13_000
    assert allocated.findings == ()
    assert posted(allocated) == {"L1-A": 4_000, "L2-B": 3_300, "L3-C": 2_700, "L4-D": 3_000}
    assert exact(allocated) == {"L1-A": 40, "L2-B": 33, "L3-C": 27, "L4-D": 30}
    snapshot = by_key(allocated, "L4-D").ssp
    assert snapshot is not None
    assert (snapshot.method, snapshot.residual_candidate, snapshot.point_policy) == (
        "residual",
        True,
        "RESIDUAL",
    )
    assert (snapshot.low, snapshot.mid, snapshot.high, snapshot.selected) == (15, 30, 45, 0)
    residual = traced["residual_ssp:K-01/L4-D:-"]
    assert (residual.formula_id, residual.value) == ("alloc.residual.v1", "30")
    assert residual.inputs == (
        "tp_allocation_basis:CG-1:-",
        "original_ssp_selected:K-01/L1-A:-",
        f"discount_exception@{BUNDLE}:{CONTRACT}:-",
    )
    assert residual.params == {"high": "45", "low": "15", "signs": "+,-,-"}
    discount = traced[f"discount_exception@{BUNDLE}:{CONTRACT}:-"]
    assert (discount.value, discount.params["mode"], discount.params["proposed_residual"]) == (
        "60",
        "residual",
        "30",
    )
    (proposal,) = allocated.proposals
    assert (proposal.detail["d_bundle"], proposal.detail["d_contract"]) == ("40", "40")


def test_chk_032_residual_rejected_case_c() -> None:
    prices = ("30.00", "30.00", "25.00", "20.00")
    # D-88 L7-5-Q-7: the range failure refuses activation (the CONTRACT_ACTIVATED step bundle).
    _, priced, rejected, _ = fold(
        ex_34(*prices, residual=RESIDUAL_D, judgements=[approval()], activated=True)
    )
    assert priced.tp.allocation_basis.posted == 10_500
    assert rejected.obligations == ()
    (finding,) = rejected.findings
    assert (finding.code, finding.severity, finding.subject_key, finding.stage) == (
        "RESIDUAL_REJECTED",
        "ERROR",
        "K-01/L4-D",
        5,
    )
    assert dict(finding.detail) == {
        "high": "45",
        "low": "15",
        "policy": "REQUIRE_ESTIMATED_SSP",
        "reason": "OUTSIDE_RANGE",
        "residual": "5",
        "rule": "S05-R-12",
    }
    assert [proposal.detail["approved"] for proposal in rejected.proposals] == ["true"]
    blocking = ex_34(
        *prices,
        residual=RESIDUAL_D,
        judgements=[approval()],
        overrides={"ssp.residual_failure": "BLOCK"},
        activated=True,
    )
    _, _, blocked, _ = fold(blocking)
    assert [(f.code, f.severity, f.detail["policy"]) for f in blocked.findings] == [
        ("RESIDUAL_REJECTED", "ERROR", "BLOCK")
    ]

    # While the contract is DRAFT the range failure raises nothing and D takes R = 5.00.
    _, _, draft, _ = fold(ex_34(*prices, residual=RESIDUAL_D, judgements=[approval()]))
    assert draft.findings == ()
    assert posted(draft)["L4-D"] == 500
    assert exact(draft)["L4-D"] == 5

    # After an approved estimated SSP of 30 for D, test (c) fails (|40 − 65| ÷ 100 > 0.02), so no
    # exception is proposed and relative SSP applies over [40, 55, 45, 30].
    _, _, estimated, _ = fold(ex_34(*prices, residual=ESTIMATED_D, judgements=[approval()]))
    assert estimated.findings == ()
    assert estimated.proposals == ()
    assert posted(estimated) == {"L1-A": 2_471, "L2-B": 3_397, "L3-C": 2_779, "L4-D": 1_853}
    assert exact(estimated) == {
        "L1-A": Fraction(105 * 40, 170),
        "L2-B": Fraction(105 * 55, 170),
        "L3-C": Fraction(105 * 45, 170),
        "L4-D": Fraction(105 * 30, 170),
    }


def test_ex_05_d_royalty_not_targeted() -> None:
    lines = (line("L1-X", "LIC-X", "150.00"), line("L2-Y", "LIC-Y", "150.00"))
    ctx, priced, fixed, _ = fold(native(*lines, entries=EX_35))
    assert posted(fixed) == {"L1-X": 13_333, "L2-Y": 16_667}

    # The royalty whose 32-40(b) test fails is a contract-wide element: the whole basis follows the
    # inception SSPs, so it adds X 88.89 and Y 111.11.
    royalty = element("200.00", target="CONTRACT")
    _, _, contract_wide, traced = fold(native(*lines, entries=EX_35, estimates=[royalty]))
    assert contract_wide.findings == ()
    assert dict(contract_wide.targeted_vc_quotas) == {}
    assert posted(contract_wide) == {"L1-X": 22_222, "L2-Y": 27_778}
    assert not any(node_id.startswith("allocation_remainder:") for node_id in traced)

    # An OBLIGATIONS element without the 32-40 attestation is allocated the same way.
    unattested = element("200.00", evidence=False)
    _, _, same, _ = fold(native(*lines, entries=EX_35, estimates=[unattested]))
    assert (posted(same), dict(same.targeted_vc_quotas)) == (posted(contract_wide), {})

    # The month-1 realised royalty alone, on the inception basis.
    realised = dataclasses.replace(
        priced.tp, allocation_basis=Quota1(Fraction(200), 20_000), elements=()
    )
    weights = [Fraction(800), Fraction(1000)]
    quotas = s05_allocation.allocate(
        ctx, realised, weights, ["K-01/L1-X", "K-01/L2-Y"], group_key=GROUP
    )
    assert [quota.a_posted for quota in quotas] == [8_889, 11_111]
    assert [quota.x_exact for quota in quotas] == [Fraction(800, 9), Fraction(1000, 9)]


def test_ex_05_d_case_a_tolerance() -> None:
    lines = (line("L1-X", "LIC-X", "800.00"), line("L2-Y", "LIC-Y", "0.00"))
    _, priced, allocated, traced = fold(
        native(*lines, entries=EX_35, estimates=[element("1000.00")])
    )
    assert priced.tp.allocation_basis.posted == 180_000
    assert allocated.findings == ()
    targeted = {key: dict(quotas) for key, quotas in allocated.targeted_vc_quotas.items()}
    assert targeted == {ELEMENT: {"K-01/L2-Y": Quota(Fraction(1000), 100_000)}}
    assert posted(allocated) == {"L1-X": 35_556, "L2-Y": 144_444}
    share = traced[share_id("L2-Y")]
    assert (share.formula_id, share.value, share.inputs[0]) == (
        "alloc.targeted_vc.v1",
        "1000.00",
        f"vc_constrained:{ELEMENT}:-",
    )
    # r_Y = 1,000 ÷ 1,000 = 1 and r_c = 1,800 ÷ 1,800 = 1: within the POL-044 tolerance of 0.20.
    assert {name: share.params[name] for name in ("ratio", "contract_ratio", "tolerance")} == {
        "ratio": "1",
        "contract_ratio": "1",
        "tolerance": "0.2",
    }
    assert share.params["tolerance_exceeded"] == "false"
    remainder = traced["allocation_remainder:CG-1:-"]
    assert (remainder.formula_id, remainder.value, remainder.params["signs"]) == (
        "alloc.targeted_vc.v1",
        "800.00",
        "+,-",
    )
    assert traced["original_allocated_amount:K-01/L2-Y:-"].inputs[0] == remainder.id
    adjustment = traced["allocation_adjustment:K-01/L2-Y:-"]
    assert (adjustment.value, adjustment.params["signs"]) == ("1444.44", "+,+,-")

    # r_Y = 2 departs from r_c = 2,800 ÷ 1,800 by more than 0.20 × r_c.
    _, _, flagged, _ = fold(native(*lines, entries=EX_35, estimates=[element("2000.00")]))
    assert flagged.obligations == ()
    (finding,) = flagged.findings
    assert (finding.code, finding.severity, finding.subject_key, finding.stage) == (
        "VC_TARGET_TOLERANCE_EXCEEDED",
        "ERROR",
        "K-01/L2-Y",
        5,
    )
    assert dict(finding.detail) == {
        "contract_ratio": format_exact(Fraction(28, 18)),
        "estimate_key": ELEMENT,
        "ratio": "2",
        "rule": "S05-R-14",
        "tolerance": "0.2",
    }

    # A reviewed OTHER outcome pol_044_override = true naming the element clears the finding; the
    # params still record the excess.
    overridden = native(
        *lines, entries=EX_35, estimates=[element("2000.00")], judgements=[override()]
    )
    _, _, cleared, traced = fold(overridden)
    assert cleared.findings == ()
    assert traced[share_id("L2-Y")].params["tolerance_exceeded"] == "true"
    assert posted(cleared) == {"L1-X": 35_556, "L2-Y": 244_444}

    # NOT_ENFORCED (parity) skips the test.
    parity = native(
        *lines, entries=EX_35, estimates=[element("2000.00")], overrides={TOLERANCE: "NOT_ENFORCED"}
    )
    _, _, skipped, traced = fold(parity)
    assert skipped.findings == ()
    assert "tolerance_exceeded" not in traced[share_id("L2-Y")].params


def test_s05_r15_vc_allocation_negative() -> None:
    lines = (line("L1-X", "LIC-X", "800.00"), line("L2-Y", "LIC-Y", "0.00"))
    penalty = element("1200.00", kind="PENALTY")
    value = native(
        *lines, entries=EX_35, estimates=[penalty], overrides={TOLERANCE: "NOT_ENFORCED"}
    )
    _, priced, allocated, _ = fold(value)
    assert priced.tp.allocation_basis.posted == -40_000
    assert allocated.obligations == ()
    (finding,) = allocated.findings
    assert (finding.code, finding.severity, finding.subject_key, finding.stage) == (
        "VC_ALLOCATION_NEGATIVE",
        "ERROR",
        "K-01/L2-Y",
        5,
    )
    # Y takes 800.00 × 1,000 ÷ 1,800 of T and −1,200.00 of the targeted penalty.
    assert dict(finding.detail) == {
        "allocated_exact": format_exact(Fraction(4000, 9) - 1200),
        "estimate_keys": ELEMENT,
        "rule": "S05-R-15",
    }


def test_s05_r09_pipeline_order() -> None:
    value = native(
        line("L1-A", "PROD-A", "40.00"),
        line("L2-B", "PROD-B", "30.00"),
        line("L3-C", "PROD-C", "30.00"),
        line("L4-D", "PROD-D", "30.00"),
        entries=[*EX_34, RESIDUAL_D],
        estimates=[element("10.00", keys=("L1-A",))],
        judgements=[approval()],
        overrides={TOLERANCE: "NOT_ENFORCED"},
        bundle=True,
    )
    _, priced, allocated, traced = fold(value)
    assert priced.tp.allocation_basis.posted == 14_000
    assert allocated.findings == ()
    assert posted(allocated) == {"L1-A": 5_000, "L2-B": 3_300, "L3-C": 2_700, "L4-D": 3_000}
    assert traced[share_id("L1-A")].value == "10.00"
    chain = [
        "original_allocated_amount:K-01/L4-D:-",
        "allocation_weight:K-01/L4-D:-",
        "residual_ssp:K-01/L4-D:-",
        f"discount_exception@{BUNDLE}:{CONTRACT}:-",
        "allocation_remainder:CG-1:-",
    ]
    for later, earlier in itertools.pairwise(chain):
        assert earlier in traced[later].inputs
    order = [traced[node_id].formula_id for node_id in reversed(chain)]
    assert order == [
        "alloc.targeted_vc.v1",
        "alloc.discount_exception.v1",
        "alloc.residual.v1",
        "alloc.relative_ssp.v1",
        "alloc.largest_remainder.v1",
    ]
    # No allocation node reads a node of a later step of the pipeline (REQ-ALC-007).
    rank = {formula_id: index for index, formula_id in enumerate(order)}
    for node in traced.values():
        if node.formula_id not in rank:
            continue
        for item in node.inputs:
            if isinstance(item, str) and traced[item].formula_id in rank:
                assert rank[traced[item].formula_id] <= rank[node.formula_id], (node.id, item)


def test_l8_d_every_line_excluded_allocates_nothing() -> None:
    """D-88 L7-5-Q-10 (1) on the ONB-RB-06 world: the only line is excluded by S03-R-11
    (CONTRIBUTION_958_605), so allocation_basis.posted is 0; stage 05 allocates nothing and raises
    no TOTAL_SSP_ZERO. An obligation whose SSPs sum to 0 still raises (Σw = 0)."""
    grant = {
        **line("L1-GRANT", "RELIEF-GRANT", "250000.00"),
        "scope_flag": "CONTRIBUTION_958_605",
        "out_of_scope_amount": "250000.00",
    }
    _, priced, allocated, _ = fold(native(grant, entries=[entry("RELIEF-GRANT", point="0")]))
    assert priced.pob.obligations == ()
    assert [draft.obligation_key for draft in priced.pob.routed_out] == ["L1-GRANT"]
    assert (priced.tp.allocation_basis.posted, priced.tp.out_of_scope.posted) == (0, 25_000_000)
    assert (allocated.findings, allocated.obligations) == ((), ())

    free = line("L1-FREE", "RELIEF-GRANT", "0.00")
    _, _, refused, _ = fold(native(free, entries=[entry("RELIEF-GRANT", point="0")]))
    assert [finding.code for finding in refused.findings] == ["TOTAL_SSP_ZERO"]
