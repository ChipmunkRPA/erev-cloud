"""D-93 (3): the S04-R-04 claim gate and the S05-R-14 override accept the element code and the
obligation subject.

ENGINE_SPEC Table 0.4-A rev 1.7 (``CONSTRAINT`` / ``OTHER`` outcome ``estimate_key`` is the element
code of the record's contract; the engine also accepts the §0.4 qualified key
``<contract external_id>/<element_code>``; the record may sit on the contract or on the element's
obligation); 04 T-CON-19; dev-guide §9.5.4. MOD-GE-02's reviewed judgement is obligation-scoped
(``subject_obligation_key: L1-WORK``) and names ``estimate_key: VC-GE02-CLAIM``, which the gate
refused at e467e25 (TP 5,480,000.00 against the key's 5,580,000.00). The stage 04 world is
``test_s04_buildup``'s (K-01, POB-01, rebate and claim elements); the stage 05 world is the EX-35
tolerance world of ``support.allocation_worlds``. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses

import pytest
from erev_engine.bundle import EstimateVersionInput, JudgementInput
from erev_engine.stages.s01_canonicalize.convert import obligation_subject_key
from support.allocation_worlds import CONTRACT as ALC_CONTRACT
from support.allocation_worlds import EX_35, element, line, native, posted
from support.allocation_worlds import fold as fold_allocation
from test_s04_buildup import CONTRACT, booking, bundle, changed, fold, version

REBATE_AND_CLAIM = (
    version("VC-REBATE", method="ENTERED_AMOUNT", vc_type="REBATE", constrained="300.00"),
    # The claim element names its obligation, as MOD-GE-02's VC-GE02-CLAIM names L1-WORK.
    dataclasses.replace(
        version("VC-CLAIM", method="ENTERED_AMOUNT", vc_type="CLAIM", constrained="1000.00"),
        allocation_target="OBLIGATIONS",
        target_obligation_keys=("POB-01",),
        obligation_key="POB-01",
    ),
)


def _claim_world(judgement: JudgementInput) -> tuple[int, int]:
    rebate, claim = REBATE_AND_CLAIM
    events = (booking(price="10000.00"), changed(2, rebate), changed(3, claim))
    _, priced, _ = fold(bundle(*events, versions=(rebate, claim), judgements=(judgement,)))
    return priced.tp.vc_constrained.posted, priced.tp.total.posted


def _enforceable(subject_key: str, estimate_key: str) -> JudgementInput:
    return JudgementInput(
        judgement_key="J-CLAIM-1",
        topic="OTHER",
        subject_key=subject_key,
        book_code=None,
        outcome={"claim_enforceable": "true", "estimate_key": estimate_key},
    )


@pytest.mark.parametrize(
    ("subject_key", "estimate_key"),
    [
        (CONTRACT, "K-01/VC-CLAIM"),  # the contract subject with the §0.4 qualified key (today)
        (CONTRACT, "VC-CLAIM"),  # the T-CON-19 element code (D-93 (3))
        (f"{CONTRACT}/POB-01", "VC-CLAIM"),  # the record on the element's obligation (D-93 (3))
        (f"{CONTRACT}/POB-01", "K-01/VC-CLAIM"),
    ],
)
def test_d93_3_claim_gate_accepts_element_code_and_obligation_subject(
    subject_key: str, estimate_key: str
) -> None:
    # The rebate (−300.00) and the claim (+1,000.00) both enter: constrained +700.00, TP 10,700.00.
    assert _claim_world(_enforceable(subject_key, estimate_key)) == (70_000, 1_070_000)


def test_d93_3_claim_gate_still_refuses_another_element_contract_or_obligation() -> None:
    # The gate keeps its substance: the outcome must name this element, on this contract or on
    # the element's obligation.
    assert _claim_world(_enforceable(CONTRACT, "VC-OTHER")) == (-30_000, 970_000)
    assert _claim_world(_enforceable("K-99", "VC-CLAIM")) == (-30_000, 970_000)
    assert _claim_world(_enforceable(f"{CONTRACT}/POB-02", "K-01/VC-CLAIM")) == (-30_000, 970_000)


def _override(subject_key: str, estimate_key: str) -> JudgementInput:
    outcome = {"estimate_key": estimate_key, "pol_044_override": "true"}
    return JudgementInput("J-POL-044", "OTHER", subject_key, None, outcome)


@pytest.mark.parametrize(
    ("subject_key", "estimate_key"),
    [
        (ALC_CONTRACT, "VC-1"),  # the element code on the contract
        (
            f"{ALC_CONTRACT}/L2-Y",
            f"{ALC_CONTRACT}/VC-1",
        ),  # the qualified key on the target obligation
        (f"{ALC_CONTRACT}/L2-Y", "VC-1"),
    ],
)
def test_d93_3_pol_044_override_accepts_element_code_and_obligation_subject(
    subject_key: str, estimate_key: str
) -> None:
    # The EX-35 tolerance world of test_s05_exceptions: r_Y = 2 departs from r_c by more than
    # 0.20 × r_c, and the reviewed override clears the finding.
    lines = (line("L1-X", "LIC-X", "800.00"), line("L2-Y", "LIC-Y", "0.00"))
    overridden = native(
        *lines,
        entries=EX_35,
        estimates=[element("2000.00")],
        judgements=[_override(subject_key, estimate_key)],
    )
    _, _, cleared, _ = fold_allocation(overridden)
    assert cleared.findings == ()
    assert posted(cleared) == {"L1-X": 35_556, "L2-Y": 244_444}


# --- Codex PRODUCTION-C1B-ENCODED-JUDGEMENT-4778d5e: reserved characters in the element code -----
#
# TY-06 (04 §1) admits '/', '#' and ':' in an element code; the §0.4 qualified key encodes them
# (CV-21: VC/CLAIM → K-01/VC%2FCLAIM). The outcome ``estimate_key`` names the element by its raw
# code or by the encoded qualified key; the matcher compares the raw code against the element's own
# ``element_code``, never against a component split off the encoded key.

RESERVED_CODES = ("VC/CLAIM", "VC#CLAIM", "VC:CLAIM")


def _claim_element(code: str) -> EstimateVersionInput:
    return dataclasses.replace(
        version(code, method="ENTERED_AMOUNT", vc_type="CLAIM", constrained="1000.00"),
        allocation_target="OBLIGATIONS",
        target_obligation_keys=("POB-01",),
        obligation_key="POB-01",
    )


def _claim_world_for(code: str, judgement: JudgementInput) -> tuple[int, int]:
    rebate = REBATE_AND_CLAIM[0]
    claim = _claim_element(code)
    events = (booking(price="10000.00"), changed(2, rebate), changed(3, claim))
    _, priced, _ = fold(bundle(*events, versions=(rebate, claim), judgements=(judgement,)))
    return priced.tp.vc_constrained.posted, priced.tp.total.posted


@pytest.mark.parametrize("code", RESERVED_CODES)
def test_codex_c1b_claim_gate_matches_the_raw_element_code_with_reserved_characters(
    code: str,
) -> None:
    # The obligation-scoped judgement names the raw code: the claim enters (700.00 / 10,700.00).
    assert _claim_world_for(code, _enforceable(f"{CONTRACT}/POB-01", code)) == (70_000, 1_070_000)
    assert _claim_world_for(code, _enforceable(CONTRACT, code)) == (70_000, 1_070_000)


@pytest.mark.parametrize("code", RESERVED_CODES)
def test_codex_c1b_claim_gate_matches_the_encoded_qualified_key(code: str) -> None:
    encoded = obligation_subject_key(CONTRACT, code)
    assert encoded != f"{CONTRACT}/{code}"
    assert _claim_world_for(code, _enforceable(CONTRACT, encoded)) == (70_000, 1_070_000)


@pytest.mark.parametrize("code", RESERVED_CODES)
def test_codex_c1b_claim_gate_still_refuses_on_reserved_codes(code: str) -> None:
    # Another element (the split tail of the encoded key), another contract, a false flag or another
    # book never admit the claim.
    assert _claim_world_for(code, _enforceable(CONTRACT, code.rpartition("/")[2] + "X")) == (
        -30_000,
        970_000,
    )
    assert _claim_world_for(code, _enforceable("K-99", code)) == (-30_000, 970_000)
    off = dataclasses.replace(
        _enforceable(CONTRACT, code),
        outcome={"claim_enforceable": "false", "estimate_key": code},
    )
    assert _claim_world_for(code, off) == (-30_000, 970_000)
    other_book = dataclasses.replace(_enforceable(CONTRACT, code), book_code="IFRS15")
    assert _claim_world_for(code, other_book) == (-30_000, 970_000)


def _override_element(code: str) -> EstimateVersionInput:
    key = obligation_subject_key(ALC_CONTRACT, code)
    return dataclasses.replace(
        element("2000.00"), estimate_key=key, element_code=code, version_key=f"{key}@v1"
    )


def _override_world(code: str, judgement: JudgementInput) -> tuple[tuple[object, ...], dict]:
    lines = (line("L1-X", "LIC-X", "800.00"), line("L2-Y", "LIC-Y", "0.00"))
    overridden = native(
        *lines, entries=EX_35, estimates=[_override_element(code)], judgements=[judgement]
    )
    _, _, cleared, _ = fold_allocation(overridden)
    return cleared.findings, posted(cleared)


@pytest.mark.parametrize("code", ("VC/1", "VC#1", "VC:1"))
def test_codex_c1b_pol_044_override_matches_the_raw_element_code_with_reserved_characters(
    code: str,
) -> None:
    for subject in (f"{ALC_CONTRACT}/L2-Y", ALC_CONTRACT):
        findings, allocated = _override_world(code, _override(subject, code))
        assert findings == ()
        assert allocated == {"L1-X": 35_556, "L2-Y": 244_444}
    findings, allocated = _override_world(
        code, _override(ALC_CONTRACT, obligation_subject_key(ALC_CONTRACT, code))
    )
    assert (findings, allocated) == ((), {"L1-X": 35_556, "L2-Y": 244_444})


@pytest.mark.parametrize("code", ("VC/1", "VC#1", "VC:1"))
def test_codex_c1b_pol_044_override_still_refuses_another_element(code: str) -> None:
    findings, allocated = _override_world(code, _override(ALC_CONTRACT, "VC-1"))
    assert [finding.code for finding in findings] == ["VC_TARGET_TOLERANCE_EXCEEDED"]
    assert allocated == {}
