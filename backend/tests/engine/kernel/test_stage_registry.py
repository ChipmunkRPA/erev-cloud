"""Stage registry completeness (ENGINE_SPEC §0.2, §0.3, §0.10; B3-BS2-07; DG-ENG-10; EKC-6).

``PENDING_STAGES`` and ``PENDING_BOUNDARY_HANDLERS`` list what later phases build, each entry with
its phase code. The item that builds a stage or registers a handler removes its entries; GATE-EDS
requires both tuples to be empty.
"""

from __future__ import annotations

import re

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.enums import ContractEventType
from erev_engine.formulas import FORMULAS
from erev_engine.stages import (
    BOUNDARY_EVENT_TYPES,
    BOUNDARY_HANDLERS,
    STAGES,
    StageSpec,
    s02_contract_identification,
    s06_modifications,
    s07_onboarding,
    s08_estimates_late_events,
)

# EDS-1 registered stage 15, the last of Table 0.2-A.
PENDING_STAGES: tuple[tuple[str, str], ...] = ()
# ENB-13 registered every Table 0.3-A handler.
PENDING_BOUNDARY_HANDLERS: tuple[tuple[str, str], ...] = ()

# Table 0.2-A stages the book loop runs, with the phase that builds each (PHASES §3).
TABLE_0_2_A = {
    "02": "ENA",
    "03": "ENA",
    "04": "ENA",
    "05": "ENA",
    "06": "ENB",
    "07": "ENB",
    "08": "ENB",
    "09": "ENC",
    "10": "ENC",
    "11": "ENC",
    "12": "END",
    "14": "END",
    "15": "EDS",
}
TABLE_0_3_A = {
    "COLLECTIBILITY_ASSESSED",
    "CONTRACT_CRITERIA_MET",
    "SIGNIFICANT_CHANGE_FLAGGED",
    "CONTRACT_AMENDED",
    "CONTRACT_TERMINATED",
    "REGROUPED",
    "LINE_ATTRIBUTES_CHANGED",
    "MATERIAL_RIGHT_EXERCISED",
    "OPENING_BALANCE_ESTABLISHED",
    "ESTIMATE_CHANGED",
}


def test_stage_registry_complete() -> None:
    built = tuple(spec.stage for spec in STAGES)
    pending = tuple(stage for stage, _ in PENDING_STAGES)
    assert not set(built) & set(pending), "a stage is both built and pending"
    assert len(set(built)) == len(built) and len(set(pending)) == len(pending)
    assert set(built) | set(pending) == set(TABLE_0_2_A)
    # EDS-1 registered stage 15; END-14's pending clause is superseded by the empty tuple.
    assert PENDING_STAGES == ()
    order = list(TABLE_0_2_A)
    assert list(built) == sorted(built, key=order.index), "STAGES must follow Table 0.2-A order"
    assert all(TABLE_0_2_A[stage] == phase for stage, phase in PENDING_STAGES)
    for spec in STAGES:
        assert set(spec.formula_ids) <= set(FORMULAS), spec.stage

    assert BOUNDARY_EVENT_TYPES == TABLE_0_3_A
    assert BOUNDARY_EVENT_TYPES <= set(ContractEventType)
    handled = set(BOUNDARY_HANDLERS)
    waiting = {literal for literal, _ in PENDING_BOUNDARY_HANDLERS}
    assert not handled & waiting, "a boundary literal is both handled and pending"
    assert handled | waiting == TABLE_0_3_A
    assert list(PENDING_BOUNDARY_HANDLERS) == sorted(PENDING_BOUNDARY_HANDLERS)
    assert all(callable(handler) for handler in BOUNDARY_HANDLERS.values())
    with pytest.raises(TypeError):
        BOUNDARY_HANDLERS["REGROUPED"] = print  # type: ignore[index]


def test_boundary_handlers_table_0_3_a() -> None:
    """ENGINE_SPEC Table 0.3-A as registered by ENB-13 (CV-11)."""
    expected = {
        "COLLECTIBILITY_ASSESSED": s02_contract_identification.apply,
        "CONTRACT_CRITERIA_MET": s02_contract_identification.apply,
        "SIGNIFICANT_CHANGE_FLAGGED": s02_contract_identification.apply,
        "CONTRACT_AMENDED": s06_modifications.apply,
        "CONTRACT_TERMINATED": s06_modifications.apply,
        "REGROUPED": s06_modifications.apply,
        "LINE_ATTRIBUTES_CHANGED": s06_modifications.apply,
        "MATERIAL_RIGHT_EXERCISED": s06_modifications.apply,
        "OPENING_BALANCE_ESTABLISHED": s07_onboarding.apply,
        "ESTIMATE_CHANGED": s08_estimates_late_events.apply,
    }
    assert set(BOUNDARY_HANDLERS) == set(expected) == TABLE_0_3_A
    for literal, handler in expected.items():
        assert BOUNDARY_HANDLERS[literal] is handler, literal
    assert PENDING_BOUNDARY_HANDLERS == ()
    # CONTRACT_BOOKED is absorbed by the inception fold and MATERIAL_RIGHT_EXPIRED is no boundary.
    assert "CONTRACT_BOOKED" not in BOUNDARY_HANDLERS
    assert "MATERIAL_RIGHT_EXPIRED" not in BOUNDARY_HANDLERS
    built = [spec.stage for spec in STAGES]
    assert built[:7] == ["02", "03", "04", "05", "06", "07", "08"]
    entries = {spec.stage: spec.entry for spec in STAGES}
    assert entries["06"] is s06_modifications.apply
    assert entries["07"] is s07_onboarding.apply
    assert entries["08"] is s08_estimates_late_events.apply


def test_stage_spec_validation() -> None:
    def entry(ctx: object, state: object, tb: object) -> object:
        return state

    spec = StageSpec(
        "09",
        "s09_recognition",
        entry,
        ("recognition.time_convention", "rounding.schedule"),
        ("sched.cumulative_posted.v1", "sched.period_difference.v1"),
    )
    assert spec.run(None, "state", None) == "state"
    for stage, package in (("01", "s01_canonicalize"), ("13", "s13_books")):
        with pytest.raises(ValueError, match="not one of"):
            StageSpec(stage, package, entry, (), ())
    with pytest.raises(ValueError, match="does not name"):
        StageSpec("09", "s10_billing_balances", entry, (), ())
    with pytest.raises(ValueError, match="sorted"):
        StageSpec(
            "09", "s09_recognition", entry, ("rounding.schedule", "recognition.time_convention"), ()
        )
    with pytest.raises(ValueError, match="unregistered"):
        StageSpec("09", "s09_recognition", entry, (), ("sched.unknown.v1",))


def test_engine_version_semver() -> None:
    assert re.fullmatch(r"^\d+\.\d+\.\d+$", ENGINE_VERSION)
    # 0.1.0 → 0.2.0: D-91 C606-01 changed result (DG-ENG-10), once, in ENG-B1.
    # 0.2.0 → 0.3.0 (D-93 (5); ENC-VC-direction): a changed-result minor bump under the D-91 A4
    # reading of DG-ENG-10 for the 0.x line. Normalised value compatibility (engine_version
    # blanked: 654/658 inputs and all 583 common successful outputs value-equal except the four
    # intended VC-FS-02 changes) is a separate fact from the actual hashes (all 658 input and 583
    # common output hashes differ). Replay is version-pinned to the stored engine_release; no
    # silent rewriting or reposting of history; historical-integrity replay (RCP-28/29) and
    # candidate-upgrade validation (REL-06) remain mandatory; new computations use 0.3.0. Once, in
    # ENG-C2a.
    # OWED at the next release cut (supervisor, lane ENG-C8 Q-1; D-98 candidate 19; S14-R-27): one
    # DG-ENG-10 minor step 0.3.0 → 0.4.0 for PostedAmountInput.reason_code (CV-25 view omits None,
    # historical inputs hash identically) with the identity D-96 INPUT_TRANSFORM; a version names a
    # release, not a lane merge, so the lane stays at 0.3.0.
    assert ENGINE_VERSION == "0.3.0"
