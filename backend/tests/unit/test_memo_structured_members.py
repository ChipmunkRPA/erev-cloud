"""``MEMO_UPDATED`` presence set with the STRUCTURED members (Codex T1F2 structured-members finding
on 8628b6e3): ``locks.MEMO_MEMBERS`` holds the five ``update-memos`` members — ``memo_1..3``,
``custom_attributes``, ``dimensions`` — so ``named`` must admit every member the writer can supply;
a custom_attributes-only, dimensions-only or mixed memo + structured update is valid, the structured
members keep their sent-replaces semantics, and the header projection writes a named
``custom_attributes`` (ENGINE_SPEC CV-47 (a); 04 §16.3)."""

from __future__ import annotations

from erev_api.domain.contracts import events, locks
from erev_api.enums import ContractEventType
from erev_api.events import payloads, stream
from erev_api.schemas.events import EventAppendItemIn

TZ = "Europe/Berlin"


def _memo_event(payload: dict[str, object]) -> payloads.MemoUpdatedV1:
    item = EventAppendItemIn(
        event_type=ContractEventType.MEMO_UPDATED,
        effective_date="2026-01-31",  # type: ignore[arg-type]
        payload=payload,
    )
    (event,) = events.to_events([item], time_zone=TZ, is_manual=True)
    assert isinstance(event.payload, payloads.MemoUpdatedV1)
    return event.payload


def test_the_payload_model_admits_every_update_memos_member_in_named() -> None:
    for member in locks.MEMO_MEMBERS:
        value: object = {"k": "v"} if member != "dimensions" else {"d": "x"}
        payload = payloads.MemoUpdatedV1(
            **{member: value if member.startswith(("custom", "dim")) else "text"},
            named=(member,),  # type: ignore[arg-type]
        )
        assert payload.named == (member,)


def test_structured_only_and_mixed_updates_derive_the_structured_members() -> None:
    attributes = _memo_event({"custom_attributes": {"tier": "gold"}})
    assert attributes.named == ("custom_attributes",)
    dimensions = _memo_event({"obligation_key": "POB #1", "dimensions": {"region": "EMEA"}})
    assert dimensions.named == ("dimensions",)
    mixed = _memo_event({"memo_1": "Changed", "custom_attributes": {"tier": "gold"}})
    assert mixed.named == ("memo_1", "custom_attributes")
    assert mixed.custom_attributes == {"tier": "gold"} and mixed.memo_1 == "Changed"


def test_header_projection_writes_a_named_custom_attributes() -> None:
    payload = payloads.MemoUpdatedV1(
        custom_attributes={"tier": "gold"},
        named=("custom_attributes",),  # type: ignore[arg-type]
    )
    assert stream.memo_header_values(payload) == {"custom_attributes": {"tier": "gold"}}
    cleared = payloads.MemoUpdatedV1(
        custom_attributes=None,
        memo_1="x",
        named=("memo_1", "custom_attributes"),  # type: ignore[arg-type]
    )
    # a supplied None keeps its existing sent-replaces semantics: an empty attribute set
    assert stream.memo_header_values(cleared) == {"custom_attributes": {}, "memo_1": "x"}
