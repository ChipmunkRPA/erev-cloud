"""Stage 01 classification (ENGINE_SPEC §0.3 Table 0.3-A, CV-10, CV-11; §1.5 S01-R-14, S01-R-17).

Private to stage 01. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from erev_engine.stages import BOUNDARY_EVENT_TYPES
from erev_engine.stages.s01_canonicalize.convert import obligation_subject_key, payload_text
from erev_engine.stages.state import EventView

__all__ = ["QUANTITY_BOUNDARY_TYPES", "Classification", "classify", "quantity_changed"]

# S01-R-17: boundary types that change an obligation's quantity; stage 06 checks those
# obligations (S06-R-08), stage 07 replaces their cutover state.
QUANTITY_BOUNDARY_TYPES: Final = frozenset(
    {
        "CONTRACT_AMENDED",
        "CONTRACT_TERMINATED",
        "MATERIAL_RIGHT_EXERCISED",
        "OPENING_BALANCE_ESTABLISHED",
        "REGROUPED",
    }
)
# Payload members listing obligation-bearing objects (04 §16.3).
_LINE_MEMBERS: Final = ("lines", "new_lines", "obligations")


@dataclass(frozen=True, slots=True)
class Classification:
    """S01-INV-02: ``boundary`` ∪ ``measure`` ∪ ``bookings`` = the included events, disjointly."""

    boundary: tuple[EventView, ...]  # Table 0.3-A types, ENG-06 order
    measure: tuple[EventView, ...]  # every other included event (CV-11), ENG-06 order
    bookings: Mapping[str, EventView]  # contract key -> its CONTRACT_BOOKED (CV-10)


def classify(events: Sequence[EventView]) -> Classification:
    """Split the included events (S01-R-14).

    Each member's ``CONTRACT_BOOKED`` enters the inception fold and neither list (CV-10). After
    voids a contract holds one booking (REQ-DAT-017); a second one is a malformed bundle (CV-45).
    ``MATERIAL_RIGHT_EXERCISED`` is a boundary under both POL-028 options.
    """
    bookings: dict[str, EventView] = {}
    boundary: list[EventView] = []
    measure: list[EventView] = []
    for event in events:
        if event.event_type == "CONTRACT_BOOKED":
            if event.contract_key in bookings:
                raise ValueError(f"{event.event_key}: a contract has one booking (REQ-DAT-017)")
            bookings[event.contract_key] = event
        elif event.event_type in BOUNDARY_EVENT_TYPES:
            boundary.append(event)
        else:
            measure.append(event)
    return Classification(
        boundary=tuple(boundary),
        measure=tuple(measure),
        bookings=MappingProxyType(dict(sorted(bookings.items()))),
    )


def named_obligations(event: EventView) -> frozenset[str]:
    """Obligation subject keys an event names in ``obligation_keys`` or its payload members."""
    names: set[str] = set(event.obligation_subject_keys)
    payload = event.payload
    single = payload_text(payload, "obligation_key")
    if single is not None:
        names.add(obligation_subject_key(event.contract_key, single))
    listed = payload.get("obligation_keys")
    for key in listed if isinstance(listed, tuple | list) else ():
        if isinstance(key, str):
            names.add(obligation_subject_key(event.contract_key, key))
    for member in _LINE_MEMBERS:
        rows = payload.get(member)
        for row in rows if isinstance(rows, tuple | list) else ():
            if isinstance(row, Mapping):
                key = payload_text(row, "obligation_key")
                if key is not None:
                    names.add(obligation_subject_key(event.contract_key, key))
    return frozenset(names)


def quantity_changed(
    boundary: Iterable[EventView], obligations_of: Mapping[str, Sequence[str]]
) -> frozenset[str]:
    """Obligation subject keys touched by a quantity-changing boundary (S01-R-17).

    A full termination touches every booked obligation of its contract.
    """
    changed: set[str] = set()
    for event in boundary:
        if event.event_type not in QUANTITY_BOUNDARY_TYPES:
            continue
        changed.update(named_obligations(event))
        full = event.payload.get("termination_kind") == "FULL"
        if event.event_type == "CONTRACT_TERMINATED" and full:
            changed.update(obligations_of.get(event.contract_key, ()))
    return frozenset(changed)
