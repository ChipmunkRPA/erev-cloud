"""Stage 01 voids (ENGINE_SPEC §1.5 S01-R-12, S01-R-13; CV-45).

Private to stage 01. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence

from erev_engine.bundle import EventInput

__all__ = ["resolve"]


def resolve(events: Sequence[EventInput]) -> tuple[EventInput, ...]:
    """The included events after voids, in bundle (ENG-06) order.

    S01-R-12: an ``EVENT_VOIDED`` and its target ``supersedes_event_key`` both leave the stream,
    so the replay equals a stream in which the target never existed. A void without a target, of
    an absent event, of a void, of another contract's event, or of an event voided already is a
    programming error of bundle assembly (CV-45).

    S01-R-13: an included ``CONTRACT_VOIDED`` removes every other event of its contract. The void
    itself stays, so stage 02 records status ``VOIDED`` in every book.
    """
    by_key = {event.event_key: event for event in events}
    if len(by_key) != len(events):
        raise ValueError("event keys are unique within a bundle (CV-22)")
    removed: set[str] = set()
    for event in events:
        if event.event_type != "EVENT_VOIDED":
            continue
        target_key = event.supersedes_event_key
        if target_key is None:
            raise ValueError(f"{event.event_key}: EVENT_VOIDED names no target (S01-R-12)")
        target = by_key.get(target_key)
        if target is None:
            raise ValueError(f"{event.event_key}: the voided event is absent (S01-R-12)")
        if target.event_type == "EVENT_VOIDED":
            raise ValueError(f"{event.event_key}: a void of a void (S01-R-12)")
        if target.contract_key != event.contract_key:
            raise ValueError(f"{event.event_key}: a void of another contract's event (S01-R-12)")
        if target_key in removed:
            raise ValueError(f"{event.event_key}: {target_key} is voided twice (S01-R-12)")
        removed.update((target_key, event.event_key))
    voided_contracts = {
        event.contract_key
        for event in events
        if event.event_type == "CONTRACT_VOIDED" and event.event_key not in removed
    }
    return tuple(
        event
        for event in events
        if event.event_key not in removed
        and (event.contract_key not in voided_contracts or event.event_type == "CONTRACT_VOIDED")
    )
