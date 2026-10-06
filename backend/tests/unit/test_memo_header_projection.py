"""Header-scope ``MEMO_UPDATED`` projection (``erev_api.events.stream.memo_header_values``): the
T-CON-01 memo members written at append time follow the presence set ``named`` — a supplied null
clears, unnamed siblings are not written — and a payload without ``named`` keeps the earlier
``model_fields_set`` reading, so header projection and the engine's replay agree for new events
(ENGINE_SPEC CV-47 (a); Codex T1F2-MEMO-R1)."""

from __future__ import annotations

from erev_api.events import payloads, stream


def test_named_members_are_written_and_a_null_clears() -> None:
    payload = payloads.MemoUpdatedV1(memo_1="Changed", memo_2=None, named=("memo_1", "memo_2"))
    assert stream.memo_header_values(payload) == {"memo_1": "Changed", "memo_2": None}


def test_unnamed_siblings_are_not_written() -> None:
    """The projection runs at append time on the LIVE model (never on a re-parsed stored body,
    whose ``model_fields_set`` would hold every serialized member); a live model naming memo_1
    writes memo_1 only, and the stored form still carries the omitted siblings as null."""
    live = payloads.MemoUpdatedV1(memo_1="Changed", named=("memo_1",))
    assert stream.memo_header_values(live) == {"memo_1": "Changed"}
    stored = payloads.payload_json(live)
    assert stored["memo_2"] is None and stored["named"] == ["memo_1"]
    # a re-parsed stored body (the approval path): every header member follows ``named``, so the
    # null the stored form wrote for the omitted ``custom_attributes`` clears nothing.
    reparsed = payloads.MemoUpdatedV1.model_validate(stored)
    assert stream.memo_header_values(reparsed) == {"memo_1": "Changed"}  # no attribute clearing
    attributes = payloads.MemoUpdatedV1(custom_attributes={"k": "v"}, named=("custom_attributes",))
    assert stream.memo_header_values(attributes) == {"custom_attributes": {"k": "v"}}
    nothing_named = payloads.MemoUpdatedV1(custom_attributes={"k": "v"}, named=())
    assert stream.memo_header_values(nothing_named) == {}  # only the presence set is written
