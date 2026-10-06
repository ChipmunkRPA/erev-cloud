"""The subject the RCP-05 read-back gives a posted line (05 RCP-05 rev 1.202; 04 T-SL-04
``subject_key`` rev 1.282; supervisor ruling R-11 as amended on 2026-10-02; item
ENG-COST-READBACK-1; ``contracts.bundles.posted_subject``), without a database.

A line answers the subject stored on it — the subject the engine posted under. A line without a
key, which only a test builder writes, answers what every line answered before the key was stored:
a remeasurement line the group's subject of its entity, where stage 14 put it by its entry kind
until ENGINE_SPEC_B rev 1.165, and any other line the spelling of decision L3-1-Q-32.
"""

from __future__ import annotations

from erev_api.domain.contracts.bundles import posted_subject
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    group_entity_subject_key,
    obligation_subject_key,
)

CONTRACT = "SF-ORD-10417"
ENTITY = "AVM-US"
GROUP = "CG-CON-000041"
LINE = {"external_id": CONTRACT, "entity_code": ENTITY, "group_code": GROUP}
KINDS = ("REVENUE_RECOGNITION", "FX_REMEASUREMENT", "CONTRACT_COST_CAPITALIZATION")
# One subject of every family the engine posts under (ENGINE_SPEC_B S14-R-12).
STORED = (
    f"{CONTRACT}/O1",  # an obligation
    f"{CONTRACT}@{ENTITY}",  # the contract in its entity
    f"{GROUP}@{ENTITY}",  # the group in its entity: FX remeasurement
    f"{GROUP}@{ENTITY}/VARIABLE_CONSIDERATION/{CONTRACT}/REBATE-DR-01",  # a refund liability
    f"{CONTRACT}/EV-000003",  # a cost asset
    CONTRACT,  # a contract-level loss unit
    "CG-CON-000007@AVM-US",  # the subject of a former group: stage 14 regroups it, not the read
)


def test_a_stored_subject_is_answered_as_it_stands() -> None:
    for stored in STORED:
        for obligation_key in (None, "O1"):
            for entry_kind in KINDS:
                answered = posted_subject(
                    stored, obligation_key=obligation_key, entry_kind=entry_kind, **LINE
                )
                assert answered == stored, (stored, obligation_key, entry_kind)


def test_a_remeasurement_line_without_a_key_answers_the_group_subject_of_its_entity() -> None:
    expected = group_entity_subject_key(GROUP, ENTITY)
    assert expected == f"{GROUP}@{ENTITY}"
    for obligation_key in (None, "O1"):  # whatever else the line names
        assert (
            posted_subject(
                None, obligation_key=obligation_key, entry_kind="FX_REMEASUREMENT", **LINE
            )
            == expected
        )


def test_any_other_line_without_a_key_answers_the_spelling_of_l3_1_q_32() -> None:
    kinds = ("REVENUE_RECOGNITION", "DEPOSIT", "CONTRACT_COST_CAPITALIZATION", "LOSS_PROVISION")
    for entry_kind in kinds:
        of_an_obligation = posted_subject(None, obligation_key="O1", entry_kind=entry_kind, **LINE)
        assert of_an_obligation == obligation_subject_key(CONTRACT, "O1") == f"{CONTRACT}/O1"
        other = posted_subject(None, obligation_key=None, entry_kind=entry_kind, **LINE)
        assert other == f"{contract_subject_key(CONTRACT)}@{ENTITY}" == f"{CONTRACT}@{ENTITY}"


def test_the_spelling_is_the_engines_own() -> None:
    """A component with a reserved character is spelled by the engine's key functions (ENGINE_SPEC
    CV-21), so the answer is the key the engine has a target for."""
    odd = {"external_id": "ACME/7@EU", "entity_code": ENTITY, "group_code": "CG-ACME/7"}
    assert posted_subject(
        None, obligation_key="O/1", entry_kind="DEPOSIT", **odd
    ) == obligation_subject_key("ACME/7@EU", "O/1")
    assert (
        posted_subject(None, obligation_key=None, entry_kind="DEPOSIT", **odd)
        == f"{contract_subject_key('ACME/7@EU')}@{ENTITY}"
    )
    assert posted_subject(
        None, obligation_key=None, entry_kind="FX_REMEASUREMENT", **odd
    ) == group_entity_subject_key("CG-ACME/7", ENTITY)
