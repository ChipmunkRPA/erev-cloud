"""CV-47 (a) memo pass-through with the ``MEMO_UPDATED`` presence set ``named`` (Codex T1F2-MEMO-R1;
lane ENG-T1F slice T1F-2). Golden Contract 1 through step 04 (version date 2023-01-31): the delivery
upload's memos "Delivery 1/2/3 01.31.23" stand on POB #1; the scenarios append one more
``MEMO_UPDATED`` event and read ``obligation_version.memo_1..3``:

- string replacement of a named member;
- omitted siblings unchanged although the stored form writes them as null (payload_json);
- explicit clear: a named member supplied as null;
- an older ambiguous V1 event without ``named``: strings replace, nulls are omissions;
- the version-date boundaries: a memo event recorded after ``known_at`` is refused at stage 01
  (RCP-15 — the known-at cut, so no later memo can reach an earlier version), and a memo event
  recorded before ``known_at`` but effective later than every other event moves d_v and applies.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest
from erev_engine import compute
from erev_engine.bundle import InputBundle
from support import bundles, golden_streams, intent_totals

CONTRACT = "Contract 1"
POB = "POB #1"
DELIVERED = ("Delivery 1 01.31.23", "Delivery 2 01.31.23", "Delivery 3 01.31.23")


def _base() -> InputBundle:
    stream = golden_streams.stream(CONTRACT, "04")
    return intent_totals.activated(stream.input_bundle(preset="LEGACY_PARITY", books=("ASC606",)))


def _with_memo_event(
    bundle: InputBundle, payload: dict[str, object], effective: date
) -> InputBundle:
    last = max(event.stream_version for event in bundle.events if event.contract_key == CONTRACT)
    event = bundles.event(
        CONTRACT, last + 1, "MEMO_UPDATED", effective, payload, obligation_keys=(POB,)
    )
    return dataclasses.replace(bundle, events=(*bundle.events, event))


def _memos(bundle: InputBundle) -> tuple[object, object, object]:
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    version = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == POB
    )
    return (
        version.columns["memo_1"],
        version.columns["memo_2"],
        version.columns["memo_3"],
    )


def test_baseline_delivery_memos() -> None:
    assert _memos(_base()) == DELIVERED


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(
            {"obligation_key": POB, "memo_1": "Changed", "named": ["memo_1"]},
            ("Changed", DELIVERED[1], DELIVERED[2]),
            id="string-replacement",
        ),
        pytest.param(
            # the stored form (payload_json) writes the omitted siblings as null
            {
                "obligation_key": POB,
                "memo_1": "Changed",
                "memo_2": None,
                "memo_3": None,
                "named": ["memo_1"],
            },
            ("Changed", DELIVERED[1], DELIVERED[2]),
            id="omitted-siblings-unchanged",
        ),
        pytest.param(
            {
                "obligation_key": POB,
                "memo_1": None,
                "memo_2": None,
                "memo_3": None,
                "named": ["memo_2"],
            },
            (DELIVERED[0], None, DELIVERED[2]),
            id="explicit-clear",
        ),
        pytest.param(
            # an older V1 event without the presence set: strings replace, nulls are omissions
            {"obligation_key": POB, "memo_1": "Older form", "memo_2": None, "memo_3": None},
            ("Older form", DELIVERED[1], DELIVERED[2]),
            id="ambiguous-v1-event",
        ),
    ],
)
def test_memo_updated_presence_set(
    payload: dict[str, object], expected: tuple[object, ...]
) -> None:
    assert _memos(_with_memo_event(_base(), payload, date(2023, 1, 31))) == expected


def test_memo_event_recorded_after_known_at_is_refused() -> None:
    """RCP-15: the bundle's known-at cut — a memo recorded after ``known_at`` never reaches the
    version (``bundles.event`` records at noon of its effective date, here after known_at)."""
    payload: dict[str, object] = {"obligation_key": POB, "memo_1": "Later", "named": ["memo_1"]}
    with pytest.raises(ValueError, match="RCP-15"):
        _memos(_with_memo_event(_base(), payload, date(2023, 2, 15)))


def test_memo_event_effective_later_moves_the_version_date_and_applies() -> None:
    """An event recorded before ``known_at`` but effective after every other event is part of
    this version: d_v moves to its date (CV-47 (a): effective date ≤ d_v) and the memo applies."""
    base = _base()
    payload: dict[str, object] = {"obligation_key": POB, "memo_1": "Later", "named": ["memo_1"]}
    with_event = _with_memo_event(base, payload, date(2023, 2, 15))
    *others, added = with_event.events
    recorded = dataclasses.replace(added, recorded_at=base.known_at)
    bundle = dataclasses.replace(with_event, events=(*others, recorded))
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    version = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == POB
    )
    assert version.columns["effective_date"] == date(2023, 2, 15)
    assert (version.columns["memo_1"], version.columns["memo_2"]) == ("Later", DELIVERED[1])
