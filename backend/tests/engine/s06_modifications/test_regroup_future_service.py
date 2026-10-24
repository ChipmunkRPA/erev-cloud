"""Incoming posted regroup cannot reconstruct the source's elapsed service."""

from dataclasses import replace
from datetime import date

import pytest

from erev_engine import compute
from erev_engine.trace import reevaluate
from tests.engine.s06_modifications.test_s06_prospective import INCEPTION, MOD_DATE, ex_09_a


def incoming(start=INCEPTION, end=None, revision=35, separate=False):
    value = ex_09_a()
    contract = value.contracts[0]
    mod = contract.modifications[0]
    line = {**mod.lines[0], "start_date": start.isoformat() if start else None}
    if end is not None:
        line["end_date"] = end.isoformat()
    mod = replace(mod, lines=(line,))
    event = next(e for e in value.events if e.event_type == "CONTRACT_AMENDED")
    event = replace(
        event,
        event_type="REGROUPED",
        payload={
            **event.payload,
            "lines": [line],
            **({"treatments": {"POB-02": "SEPARATE_CONTRACT"}} if separate else {}),
            "direction": "IN",
            "regroup_id": "RG-1",
            "counterpart_contract_id": "SOURCE",
            "modification_id": mod.modification_key,
            "obligation_keys": ["POB-02"],
        },
    )
    return replace(
        value,
        evidence_revision=revision,
        contracts=(replace(contract, modifications=(mod,)),),
        events=tuple(event if e.event_type == "CONTRACT_AMENDED" else e for e in value.events),
    )


@pytest.mark.parametrize("start", [INCEPTION, None, MOD_DATE])
def test_incoming_regroup_uses_future_service_and_preserves_authored_input(start):
    value = incoming(start)
    result = compute(value).books[0]
    expected = compute(incoming(MOD_DATE)).books[0]
    moved = next(o for o in result.obligation_versions if o.columns["obligation_key"] == "POB-02")
    assert moved.columns["start_date"] == MOD_DATE
    assert result.schedules == expected.schedules
    assert value.contracts[0].modifications[0].lines[0]["start_date"] == (
        start.isoformat() if start else None
    )
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}


def test_later_service_start_is_not_accelerated():
    later = date(2026, 10, 1)
    result = compute(incoming(later)).books[0]
    moved = next(o for o in result.obligation_versions if o.columns["obligation_key"] == "POB-02")
    assert moved.columns["start_date"] == later


def test_regroup_keeps_old_evidence_behavior_and_refuses_expired_service():
    result = compute(incoming(revision=34)).books[0]
    moved = next(o for o in result.obligation_versions if o.columns["obligation_key"] == "POB-02")
    assert moved.columns["start_date"] == INCEPTION
    with pytest.raises(ValueError, match="ends before"):
        compute(incoming(end=date(2026, 9, 15)))


def test_separate_contract_regroup_also_uses_only_future_service():
    value = incoming(separate=True)
    actual = compute(value).books[0]
    expected = compute(incoming(MOD_DATE, separate=True)).books[0]
    moved = next(o for o in actual.obligation_versions if o.columns["obligation_key"] == "POB-02")
    assert moved.columns["start_date"] == MOD_DATE
    assert actual.schedules == expected.schedules
    assert reevaluate(actual.trace) == {n.id: n.value for n in actual.trace.nodes}
