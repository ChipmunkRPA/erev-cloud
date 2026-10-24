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

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.stages.s01_canonicalize import payload_fraction, payload_text
from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.state import AllocatedState, BookContext, EventView, SegmentCause

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


def future_service(mod: ModificationView, ev: EventView) -> ModificationView:
    """Incoming remaining service starts no earlier than the effective transfer date.

    Retain the original authored input and later starts, but do not let an incoming
    ADD reconstruct source service already performed before the regroup boundary.
    Amounts and quantities must separately come from the source's dated transfer basis.
    """
    if payload_text(ev.payload, "direction") != IN:
        return mod
    lines = []
    for line in mod.lines:
        if line.action != "ADD":
            raise ValueError("An incoming posted regroup must add its transferred obligations")
        members = dict(line.members)
        end = members.get("end_date")
        if end is not None and date.fromisoformat(str(end)) < ev.effective_date:
            raise ValueError("Incoming regroup service ends before its effective transfer date")
        start = members.get("start_date")
        if start is None or date.fromisoformat(str(start)) < ev.effective_date:
            members["start_date"] = ev.effective_date.isoformat()
        lines.append(replace(line, members=MappingProxyType(members)))
    return replace(mod, lines=tuple(lines))


def book_basis(
    mod: ModificationView, ev: EventView, book_code: str, *, currency: str
) -> ModificationView:
    """Read the complete frozen transfer lines for this book, preserving original input."""
    books = mod.questionnaire.get("regroup_book_lines")
    if books is None:
        return mod
    if not isinstance(books, Mapping) or book_code not in books:
        raise ValueError("Regroup transfer basis is missing the calculation book")
    rows = books[book_code]
    if not isinstance(rows, (list, tuple)) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("Regroup book lines must contain a complete original population")
    by_key = {str(row.get("obligation_key")): row for row in rows}
    if len(by_key) != len(rows) or set(by_key) != {line.obligation_key for line in mod.lines}:
        raise ValueError("Regroup book lines differ from the original obligation population")
    direction = payload_text(ev.payload, "direction")
    if direction not in (IN, OUT):
        raise ValueError("Regroup book basis requires an IN or OUT direction")
    sign = 1 if direction == IN else -1
    lines = []
    for line in mod.lines:
        row = by_key[line.obligation_key]
        action = "ADD" if direction == IN else "REMOVE"
        if line.action != action or row.get("action") != action:
            raise ValueError("Regroup book line action differs from its transfer direction")
        quantity = payload_fraction(row, "quantity_delta")
        raw_amount = row.get("consideration_delta")
        if isinstance(raw_amount, Mapping):
            if raw_amount.get("currency") != currency:
                raise ValueError("Regroup book consideration currency differs from the contract")
            amount = payload_fraction(raw_amount, "amount")
        else:
            amount = payload_fraction(row, "consideration_delta")
        if quantity is None or amount is None or quantity * sign <= 0 or amount * sign < 0:
            raise ValueError(
                "Regroup book amounts and quantities must follow the transfer direction"
            )
        members = dict(line.members)
        for field in ("start_date", "end_date"):
            if field in row:
                members[field] = row[field]
        lines.append(
            replace(
                line,
                quantity_delta=quantity,
                consideration_delta=amount,
                members=MappingProxyType(members),
            )
        )
    return replace(mod, lines=tuple(lines))


def validate_outgoing(
    ctx: BookContext,
    st: AllocatedState,
    mod: ModificationView,
    ev: EventView,
    treatments: Mapping[str, str],
) -> None:
    """A complete obligation move transfers only its current fixed remaining basis."""
    if payload_text(ev.payload, "direction") != OUT:
        return
    from erev_engine.stages.s06_modifications import segments

    own = {ob.obligation_key: ob for ob in st.obligations if ob.contract_key == mod.contract_key}
    names = ev.payload.get("obligation_keys")
    if (
        not isinstance(names, (list, tuple))
        or len(mod.lines) != len(set(names))
        or {line.obligation_key for line in mod.lines} != set(names)
    ):
        raise ValueError("Outgoing regroup requires the complete moved obligation population")
    for line in mod.lines:
        if line.action != "REMOVE" or line.obligation_key not in own:
            raise ValueError("Outgoing regroup must remove a resolved source obligation")
        if treatments.get(line.obligation_key) != "PROSPECTIVE":
            raise ValueError(
                "Outgoing regroup must preserve prior income with prospective treatment"
            )
        ob = own[line.obligation_key]
        segment = segments.in_force(st, ob, ev)
        if segment is None or ob.scope_flag != "IN_SCOPE_606":
            raise ValueError("Outgoing regroup requires a current in-scope fixed allocation")
        current = segments.measure(ctx, st, ob, segment, ev)
        remaining = segment.a_posted - current.posted
        if remaining < 0 or current.remaining_quantity <= 0:
            raise ValueError("Outgoing regroup has no transferable remaining service")
        if (
            line.quantity_delta != -current.remaining_quantity
            or line.consideration_delta != -Fraction(remaining, 10 ** segments.minor_unit(ctx))
        ):
            raise ValueError("Outgoing regroup basis changed; rebuild the paired transfer")
