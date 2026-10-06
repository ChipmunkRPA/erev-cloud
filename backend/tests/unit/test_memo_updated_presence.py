"""``MEMO_UPDATED`` through the generic record-events / preview validation (``events.to_events``):
the presence set ``named`` is server-derived from the members the client actually submitted, before
default serialization writes the omitted siblings as null (ENGINE_SPEC CV-47 (a); 04 §16.3; Codex
T1F2-MEMO-R1). A client-supplied ``named`` never overrides the submitted members: it must equal the
derived set, else the item is a 422 finding; an unknown member is refused by the payload model."""

from __future__ import annotations

import pytest
from erev_api.domain.contracts import events
from erev_api.enums import ContractEventType
from erev_api.events import payloads
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendItemIn

TZ = "Europe/Berlin"


def _item(payload: dict[str, object]) -> EventAppendItemIn:
    return EventAppendItemIn(
        event_type=ContractEventType.MEMO_UPDATED,
        effective_date="2026-01-31",  # type: ignore[arg-type]
        payload=payload,
    )


def _memo_event(payload: dict[str, object]) -> payloads.MemoUpdatedV1:
    (event,) = events.to_events([_item(payload)], time_zone=TZ, is_manual=True)
    assert isinstance(event.payload, payloads.MemoUpdatedV1)
    return event.payload


def test_named_is_derived_from_the_submitted_members() -> None:
    payload = _memo_event({"obligation_key": "POB #1", "memo_1": "Changed"})
    assert payload.named == ("memo_1",) and payload.memo_1 == "Changed"
    # the stored form writes the omitted siblings as null; ``named`` keeps the intent
    stored = payloads.payload_json(payload)
    assert stored["named"] == ["memo_1"] and stored["memo_2"] is None


def test_submitted_null_is_a_clear_and_omitted_siblings_are_not_named() -> None:
    payload = _memo_event({"obligation_key": "POB #1", "memo_2": None})
    assert payload.named == ("memo_2",) and payload.memo_2 is None
    header = _memo_event({"memo_1": None, "memo_3": "Kept"})  # header scope: no obligation key
    assert header.obligation_key is None and header.named == ("memo_1", "memo_3")


def test_client_supplied_named_must_equal_the_derived_set() -> None:
    same = _memo_event({"obligation_key": "POB #1", "memo_1": "x", "named": ["memo_1"]})
    assert same.named == ("memo_1",)
    with pytest.raises(Problem) as failure:
        events.to_events(
            [_item({"obligation_key": "POB #1", "memo_1": "x", "named": ["memo_1", "memo_2"]})],
            time_zone=TZ,
            is_manual=True,
        )
    assert any(error.field == "events.0.payload.named" for error in failure.value.errors)


def test_unknown_named_member_is_refused_by_the_payload_model() -> None:
    with pytest.raises(Problem):
        events.to_events(
            [_item({"obligation_key": "POB #1", "memo_1": "x", "named": ["memo_9"]})],
            time_zone=TZ,
            is_manual=True,
        )
