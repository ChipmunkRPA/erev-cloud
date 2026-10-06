"""Stage 06 regrouping (ENGINE_SPEC §6.4 S06-R-27; REQ-CON-012).

``REGROUPED`` events come in pairs that share ``regroup_id``: ``direction = OUT`` on the contract
the obligations leave, and ``IN`` on ``counterpart_contract_id``.

Before any line of either contract has posted, bundle assembly moves the obligations into the
target contract's booking. They are treated as booked in the target contract from its inception,
and the event is no boundary: the obligations an ``OUT`` event names are absent from its contract,
and those an ``IN`` event names are booked in its contract from inception.

After posting, the obligations are still where they were booked, and the paired events are a
modification of both contracts. The approved modification named by ``modification_id`` carries
``REMOVE`` lines on the ``OUT`` contract with ΔC = −(moved remaining consideration), and ``ADD``
lines on the ``IN`` contract with ΔC = +(moved remaining consideration); §6.3 applies each.

The engine reads no posted amounts (CV-14): where bundle assembly booked the obligations shows
which case applies. Private to stage 06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from typing import Final

from erev_engine.stages.s01_canonicalize import payload_text
from erev_engine.stages.state import AllocatedState, EventView, SegmentCause

__all__ = ["IN", "OUT", "before_posting"]

OUT: Final = "OUT"
IN: Final = "IN"


def before_posting(st: AllocatedState, ev: EventView) -> bool:
    """Whether bundle assembly has already moved the obligations the event names (S06-R-27).

    ``True``: the event is no boundary. ``False``: the paired events are a modification. Some
    obligations moved and others not, or a moved obligation not booked from inception, raises
    ``ValueError`` (CV-45).
    """
    for name in ("regroup_id", "counterpart_contract_id", "modification_id"):
        if payload_text(ev.payload, name) is None:
            raise ValueError(f"{ev.event_key}: REGROUPED needs {name} (04 §16.3)")
    direction = payload_text(ev.payload, "direction")
    if direction not in (OUT, IN):
        raise ValueError(f"{ev.event_key}: direction is OUT or IN (04 §16.3)")
    raw = ev.payload.get("obligation_keys")
    if not isinstance(raw, tuple | list) or not raw or not all(isinstance(k, str) for k in raw):
        raise ValueError(f"{ev.event_key}: REGROUPED needs obligation_keys (04 §16.3)")
    names = sorted(set(raw))
    own = {ob.obligation_key: ob for ob in st.obligations if ob.contract_key == ev.contract_key}
    present = [key for key in names if key in own]
    if direction == OUT:
        if not present:
            return True
        if len(present) == len(names):
            return False
    else:
        if len(present) == len(names):
            late = [key for key in names if own[key].segments[0].cause != SegmentCause.INCEPTION]
            if late:
                raise ValueError(
                    f"{ev.event_key}: {late[0]} is not booked in the target contract from its "
                    "inception (S06-R-27)"
                )
            return True
        if not present:
            return False
    raise ValueError(
        f"{ev.event_key}: the regroup names obligations both moved and not moved (S06-R-27)"
    )
