"""Stage 01 estimate pins (ENGINE_SPEC §1.5 S01-R-18, S01-INV-04; S08-R-01).

``build`` also asserts the two bundle-level estimate invariants of CV-45: version keys are unique
and every version of one element resolves to one T-CON-12 ``direction`` (04 B3-D16).

D-92 (1)/(1a) (ENGINE_SPEC S06-R-15, S06-R-17 rev 1.7; ENGINE_SPEC_B S09-R-04, S09-R-35 rev 1.9):
an ``EAC`` or ``VARIABLE_CONSIDERATION`` version whose ``ESTIMATE_CHANGED`` event shares the
effective date of a later-recorded ``CONTRACT_AMENDED`` of the same contract, and whose estimate
the amendment's lines change or the class D / class N re-measurement of an amended obligation
reads, is the modification's updated estimate: its pin ``applies`` at the amendment's ENG-06
position (``EstimatePin.applies_order_key``), so the pre-boundary state is measured without it and
the boundary with it. The membership test: an ``EAC`` element naming an amended obligation
(``obligation_key`` or a target, or the unnamed element of a sole-obligation contract whose
obligation is amended); a ``VARIABLE_CONSIDERATION`` element with ``allocation_target`` ``CONTRACT``
(the pool re-allocates it, S06-R-12) or ``OBLIGATIONS`` naming an amended obligation; never an
``INCREMENTS`` element (realised amounts, S09-R-02). With several amendments on one date a version
belongs to the first amendment after it in ``record_seq``; an unrelated estimate, another date or
another contract keeps S09-R-04's ordering.

In force at inception (S01-R-18, S04-R-01; item ENG-INCEPTION-ESTIMATE-1): a version whose
``ESTIMATE_CHANGED`` event is effective on or before the group inception belongs to the inception
measurement, and stage 08 re-measures nothing at such an event. Its pin is therefore marked
``at_inception`` and applies before every position — a Step 1 assessment, a significant-change
flag, a line attribute change or an amendment of the inception date recorded before the event does
not keep the version out of the price — and its amount counts as promised before every boundary
when a later change of the estimate is routed (S08-R-05). A version that a same-date amendment
recorded after it takes (D-92) is not marked: the amendment applies it. Private to stage 01.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import ContractInput, EstimateVersionInput, EventInput, ModificationInput
from erev_engine.stages.s01_canonicalize.convert import contract_subject_key, payload_text
from erev_engine.stages.state import EstimatePin, EstimatePins, Finding, OrderKey

__all__ = ["APPROVED_STATUSES", "build"]

# A SUPERSEDED version was APPROVED when its ESTIMATE_CHANGED event was appended; bundle assembly
# supplies only pinned or effective versions (§0.4), so both statuses count as approved.
APPROVED_STATUSES: Final = frozenset({"APPROVED", "SUPERSEDED"})


def _version_key(event: EventInput) -> str | None:
    if event.estimate_version_key is not None:
        return event.estimate_version_key
    member = event.payload.get("estimate_version_key", event.payload.get("estimate_version_id"))
    return member if isinstance(member, str) else None


def build(
    events: Sequence[EventInput],
    versions: Sequence[EstimateVersionInput],
    *,
    contracts: Sequence[ContractInput] = (),
    inception_date: date | None = None,
) -> tuple[EstimatePins, tuple[Finding, ...]]:
    """The pin index over included ``ESTIMATE_CHANGED`` events and its findings (S01-R-18).

    An event naming a version absent from ``estimate_versions`` or not approved yields
    ``ESTIMATE_VERSION_NOT_APPROVED`` and pins nothing. ``EstimatePins.pin`` is then a function of
    (estimate key, date, event) and the bundle only (S01-INV-04). ``contracts`` supplies the
    T-CON-06 modifications the same-date ``CONTRACT_AMENDED`` events apply, for the D-92 (1)/(1a)
    membership of same-date versions (``applies_order_key``); without them no version defers.
    """
    amendments = _amendments(events, contracts)
    by_key = {version.version_key: version for version in versions}
    if len(by_key) != len(versions):
        raise ValueError("estimate version keys are unique within a bundle (CV-45)")
    # 04 B3-D16: the sign belongs to the element, so every version of one element resolves to the
    # same direction (an explicit member or the B3-DG-17 default; ENC-VC-direction).
    directions: dict[str, set[str]] = {}
    for item in versions:
        directions.setdefault(item.estimate_key, set()).add(item.resolved_direction())
    for estimate_key, found in sorted(directions.items()):
        if len(found) > 1:
            raise ValueError(
                f"{estimate_key}: the element's versions disagree on direction "
                f"{sorted(found)} (T-CON-12 B3-D16; CV-45)"
            )
    applied: dict[str, list[EstimatePin]] = {}
    findings: list[Finding] = []
    for event in events:
        if event.event_type != "ESTIMATE_CHANGED":
            continue
        key = _version_key(event)
        version = None if key is None else by_key.get(key)
        if version is None or version.status not in APPROVED_STATUSES:
            findings.append(
                Finding(
                    "ESTIMATE_VERSION_NOT_APPROVED",
                    "ERROR",
                    contract_subject_key(event.contract_key),
                    {"estimate_version_key": key or ""},
                    1,
                    event.event_key,
                )
            )
            continue
        order_key = (event.effective_date, event.record_seq, event.event_key)
        applies = _applies_at(event, version, amendments)
        # In force at inception: the event is effective on or before the group inception and no
        # same-date amendment takes the version (D-92). The inception price then holds it
        # wherever the event stands among the boundary events of that date (S04-R-01).
        at_inception = (
            inception_date is not None
            and applies == order_key
            and event.effective_date <= inception_date
        )
        applied.setdefault(version.estimate_key, []).append(
            EstimatePin(version, order_key, None if applies == order_key else applies, at_inception)
        )
    pins = EstimatePins(
        MappingProxyType({estimate: tuple(items) for estimate, items in sorted(applied.items())})
    )
    return pins, tuple(findings)


# --- D-92 (1)/(1a): same-date versions and the amendment they belong to ---------------------------

_MEMBER_KINDS: Final = frozenset({"EAC", "VARIABLE_CONSIDERATION"})
_INCREMENTS: Final = "INCREMENTS"


def _order_key(event: EventInput) -> OrderKey:
    return (event.effective_date, event.record_seq, event.event_key)


def _amendments(
    events: Sequence[EventInput], contracts: Sequence[ContractInput]
) -> tuple[tuple[EventInput, ModificationInput, frozenset[str], frozenset[str]], ...]:
    """Every ``CONTRACT_AMENDED`` with its T-CON-06 object, the obligation keys its lines change
    and the contract's booked obligation keys, in ENG-06 order; an amendment whose modification the
    bundle lacks is skipped here (stage 06 fails closed on it)."""
    headers = {contract.external_id: contract for contract in contracts}
    booked: dict[str, set[str]] = {}
    for event in events:
        if event.event_type != "CONTRACT_BOOKED":
            continue
        lines = event.payload.get("lines")
        keys = booked.setdefault(event.contract_key, set())
        for line in lines if isinstance(lines, list | tuple) else ():
            key = payload_text(line, "obligation_key") if isinstance(line, Mapping) else None
            if key is not None:
                keys.add(key)
    found: list[tuple[EventInput, ModificationInput, frozenset[str], frozenset[str]]] = []
    for event in sorted(events, key=_order_key):
        if event.event_type != "CONTRACT_AMENDED":
            continue
        header = headers.get(event.contract_key)
        reference = payload_text(event.payload, "modification_id")
        if header is None or reference is None:
            continue
        modification = next(
            (item for item in header.modifications if item.modification_key == reference), None
        )
        if modification is None:
            continue
        amended = frozenset(
            key
            for line in modification.lines
            if (key := payload_text(line, "obligation_key")) is not None
        )
        found.append(
            (event, modification, amended, frozenset(booked.get(event.contract_key, set())))
        )
    return tuple(found)


def _member(version: EstimateVersionInput, amended: frozenset[str], booked: frozenset[str]) -> bool:
    """D-92 (1a): the amendment's lines change the estimate or its re-measurement reads it."""
    if version.estimate_kind not in _MEMBER_KINDS or version.allocation_target == _INCREMENTS:
        return False
    named = {version.obligation_key, *version.target_obligation_keys} - {None}
    if named:
        return bool(named & amended)
    if version.estimate_kind == "EAC":
        # An unnamed EAC element measures the contract's only obligation (S09-R-14 ``eac_keys``).
        return len(booked) == 1 and bool(booked & amended)
    return version.allocation_target == "CONTRACT"  # the pool re-allocates it (S06-R-12)


def _applies_at(
    event: EventInput,
    version: EstimateVersionInput,
    amendments: Sequence[tuple[EventInput, ModificationInput, frozenset[str], frozenset[str]]],
) -> OrderKey:
    """The ENG-06 position at which ``version`` applies: the first same-date ``CONTRACT_AMENDED``
    of its contract recorded after ``event`` whose modification it belongs to, else the event."""
    own = _order_key(event)
    for amendment, _, amended, booked in amendments:
        if amendment.contract_key != event.contract_key:
            continue
        if amendment.effective_date != event.effective_date:
            continue
        key = _order_key(amendment)
        if key <= own:
            continue
        return key if _member(version, amended, booked) else own
    return own
