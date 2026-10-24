"""Effective combination membership within a retained original calculation envelope.

Original event order determines the population at a split. This is calculation lineage;
callers still persist approved membership changes and their source evidence separately.
"""

from collections.abc import Iterable, Mapping
from datetime import date

from erev_engine.stages.state import EventView, OrderKey


def validate_partition(current: Mapping[str, str], destinations: Mapping[str, str]) -> str:
    """Require a complete current group, without rejoining an already separated group."""
    keys = set(destinations)
    if len(keys) < 2 or not keys <= current.keys():
        raise ValueError("A split must partition every original member of one current group")
    sources = {current[key] for key in keys}
    if len(sources) != 1:
        raise ValueError("A split cannot rejoin members of previously separated groups")
    source = next(iter(sources))
    if keys != {key for key, group in current.items() if group == source}:
        raise ValueError("A split must partition every original member of its current group")
    if any(not isinstance(target, str) or not target.strip() for target in destinations.values()):
        raise ValueError("A split requires named destinations")
    targets = set(destinations.values())
    if len(targets) < 2:
        raise ValueError("A split requires at least two named destinations")
    if targets & {group for key, group in current.items() if key not in keys}:
        raise ValueError("A split destination cannot reuse another current group's identity")
    return source


def membership_at(
    group_code: str,
    members: Iterable[str],
    events: Iterable[EventView],
    *,
    effective_date: date | None = None,
    before_event: OrderKey | None = None,
) -> dict[str, str]:
    """Resolve original members after a date's retained events or before an exact event."""
    if (effective_date is None) == (before_event is None):
        raise ValueError("Choose an effective date or an original event position")
    current = dict.fromkeys(members, group_code)
    for event in sorted(events, key=lambda e: e.order_key):
        if before_event is not None and event.order_key >= before_event:
            break
        if effective_date is not None and event.effective_date > effective_date:
            break
        if event.event_type != "COMBINATION_CHANGED":
            continue
        if "prospective_split_destinations" not in event.payload:
            continue
        destinations = event.payload["prospective_split_destinations"]
        if event.payload.get("action") != "LEAVE" or not isinstance(destinations, Mapping):
            raise ValueError("Prospective membership requires a LEAVE event with destinations")
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in destinations.items()
        ):
            raise ValueError(
                "Prospective membership requires named original members and destinations"
            )
        validate_partition(current, destinations)
        if event.contract_key not in destinations:
            raise ValueError("A split event must belong to a member of the group being split")
        current.update(destinations)
    return current
