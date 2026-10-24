"""Posted-transfer previews use the application event and preserve original bookings."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from erev_api.domain.contracts import bundles, modifications
from erev_api.problems import Problem
from tests.engine.s06_modifications.test_s06_prospective import ex_09_a


@pytest.mark.parametrize("kind,direction", [("REMOVE_OBLIGATION", "OUT"), ("ADD_OBLIGATION", "IN")])
def test_pair_preview_uses_the_same_regroup_boundary_as_application(kind, direction):
    row = {
        "id": uuid4(),
        "regroup_id": uuid4(),
        "contract_id": uuid4(),
        "kind": kind,
        "effective_date": date(2026, 9, 16),
        "lines": [{"obligation_key": "POB-01"}],
    }
    counterpart = {"id": uuid4(), "contract_id": uuid4()}
    event = modifications._preview_event(row, [row, counterpart])
    assert event.event_type == "REGROUPED"
    assert event.payload.direction == direction
    assert event.payload.counterpart_contract_id == counterpart["contract_id"]
    assert event.payload.obligation_keys == ("POB-01",)
    assert event == modifications._regrouped_event(row, counterpart, approval_request_id=None)
    with pytest.raises(Problem, match="invalid-transition"):
        modifications._preview_event(row, [row])


def test_retained_draft_preview_does_not_rewrite_booking_from_inception():
    original = ex_09_a()
    identity = uuid4()
    old_event = next(e for e in original.events if e.event_type == "CONTRACT_AMENDED")
    event = replace(
        old_event,
        event_type="REGROUPED",
        payload={
            "direction": "OUT",
            "regroup_id": str(uuid4()),
            "modification_id": str(identity),
            "obligation_keys": ["POB-01"],
            "counterpart_contract_id": str(uuid4()),
        },
    )
    stream = tuple(event if e == old_event else e for e in original.events)
    row = {
        "approval_request_id": None,
        "questionnaire": {"regroup_book_lines": {"ASC606": [{"obligation_key": "POB-01"}]}},
    }
    assert bundles._apply_regroups(stream, {identity: row}) == stream
    # The historical draft-edit path still moves booking lines from inception.
    legacy = bundles._apply_regroups(stream, {identity: {"approval_request_id": None}})
    booked = next(e for e in legacy if e.event_type == "CONTRACT_BOOKED")
    assert not booked.payload["lines"]
    original_booking = next(e for e in stream if e.event_type == "CONTRACT_BOOKED")
    assert original_booking.payload["lines"]


def test_retained_pair_cannot_preview_a_different_separate_contract_destination():
    row = {
        "regroup_id": uuid4(),
        "chosen_treatments": {"O1": "SEPARATE_CONTRACT"},
        "questionnaire": {"regroup_book_lines": {"ASC606": []}},
    }
    errors = modifications.separate_errors(row)
    assert errors
    assert errors[0].field == "chosen_treatments"
