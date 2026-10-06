"""Composed check for the stored-approval path (Codex packet 1510 item 1 (b)): a MIXED record-events
batch (``LINE_ATTRIBUTES_CHANGED`` + ``MEMO_UPDATED``) is not appended but stored as an approval
submission whose items hold ``payload_json`` bodies — every model member serialized, so an OMITTED
``custom_attributes`` appears as null; on approval the stored body is re-parsed and appended, and
the
header projection must retain the existing attributes. The presence set ``named`` travels in the
stored body and governs the projection: submission → stored body → parse → projection."""

from __future__ import annotations

from erev_api.domain.contracts import events
from erev_api.enums import ContractEventType
from erev_api.events import payloads, stream
from erev_api.schemas.events import EventAppendItemIn

TZ = "Europe/Berlin"


def _stored_then_parsed(payload: dict[str, object]) -> payloads.MemoUpdatedV1:
    """The submission path: validate as ``to_events`` does, store ``payload_json``, re-parse the
    stored body as the approval does (``parse_payload`` from schema version 1)."""
    item = EventAppendItemIn(
        event_type=ContractEventType.MEMO_UPDATED,
        effective_date="2026-01-31",  # type: ignore[arg-type]
        payload=payload,
    )
    (event,) = events.to_events([item], time_zone=TZ, is_manual=True)
    stored = payloads.payload_json(event.payload)
    parsed = payloads.parse_payload(ContractEventType.MEMO_UPDATED, 1, stored)
    assert isinstance(parsed, payloads.MemoUpdatedV1)
    return parsed


def test_omitted_custom_attributes_survive_the_stored_approval_body() -> None:
    parsed = _stored_then_parsed({"memo_1": "Changed"})
    assert parsed.named == ("memo_1",) and parsed.custom_attributes is None  # stored as null
    # the projection writes the named memo only: existing header attributes are retained
    assert stream.memo_header_values(parsed) == {"memo_1": "Changed"}


def test_explicit_null_replacement_and_dimensions_through_the_stored_body() -> None:
    cleared = _stored_then_parsed({"memo_2": None, "custom_attributes": None})
    assert cleared.named == ("memo_2", "custom_attributes")
    assert stream.memo_header_values(cleared) == {"custom_attributes": {}, "memo_2": None}
    replaced = _stored_then_parsed({"custom_attributes": {"tier": "gold"}, "memo_3": "New"})
    assert stream.memo_header_values(replaced) == {
        "custom_attributes": {"tier": "gold"},
        "memo_3": "New",
    }
    dimensions = _stored_then_parsed({"obligation_key": "POB #1", "dimensions": {"region": "EMEA"}})
    assert dimensions.named == ("dimensions",) and dimensions.dimensions == {"region": "EMEA"}
    assert stream.memo_header_values(dimensions) == {}  # dimensions are not a header member


def test_a_stored_body_without_named_keeps_the_earlier_reading() -> None:
    """A pending submission stored before ``named`` existed: no presence set is invented; the
    re-parsed body follows the earlier ``model_fields_set`` reading exactly as before."""
    older = payloads.parse_payload(
        ContractEventType.MEMO_UPDATED,
        1,
        {"obligation_key": None, "memo_1": "Older", "memo_2": None, "memo_3": None},
    )
    assert isinstance(older, payloads.MemoUpdatedV1) and older.named is None
    assert stream.memo_header_values(older) == {"memo_1": "Older", "memo_2": None, "memo_3": None}
