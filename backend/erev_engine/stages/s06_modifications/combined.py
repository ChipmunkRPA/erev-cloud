"""Resolve original lessor component references onto the reviewed combined obligation."""

from collections.abc import Mapping
from dataclasses import replace
from fractions import Fraction
from types import MappingProxyType

from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s01_canonicalize.convert import payload_fraction, payload_text
from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.s09_recognition import progress_events
from erev_engine.stages.state import AllocatedState, BookContext


def aliases(st: AllocatedState, contract_key: str) -> dict[str, str]:
    return {
        key: ob.obligation_key
        for ob in st.obligations
        if ob.contract_key == contract_key
        for key in ob.combined_component_keys
    }


def keyed[T](values: Mapping[str, T], names: Mapping[str, str]) -> Mapping[str, T]:
    resolved: dict[str, T] = {}
    for key, value in values.items():
        host = names.get(key, key)
        if host in resolved and resolved[host] != value:
            raise ValueError("Combined component modification instructions conflict")
        resolved[host] = value
    return MappingProxyType(resolved)


def _check_original_removals(
    ctx: BookContext, st: AllocatedState, mod: ModificationView, hosts: set[str]
) -> None:
    if not hosts or not st.combined_unit_boundaries:
        return
    contract = next(item for item in st.contracts if item.header.external_id == mod.contract_key)
    raw = contract.booking.get("lines")
    if not isinstance(raw, list | tuple):
        raise ValueError("Combined termination requires original booking lines")
    originals = {
        payload_text(line, "obligation_key"): line for line in raw if isinstance(line, Mapping)
    }
    aliases_by_key = aliases(st, mod.contract_key)
    by_host = {
        ob.obligation_key: ob for ob in st.obligations if ob.contract_key == mod.contract_key
    }
    changes: dict[str, Fraction] = {}
    for line in mod.lines:
        if aliases_by_key.get(line.obligation_key) in hosts:
            changes[line.obligation_key] = (
                changes.get(line.obligation_key, Fraction(0)) + line.quantity_delta
            )
    for key, change in changes.items():
        original = originals.get(key)
        quantity = None if original is None else payload_fraction(original, "quantity")
        if quantity is None:
            raise ValueError("Combined termination requires each original member quantity")
        ob = by_host[aliases_by_key[key]]
        remaining = quantity
        if ob.recognition_method in ("UNITS_DELIVERED", "POINT_IN_TIME"):
            component = replace(
                ob,
                obligation_key=key,
                subject_key=obligation_subject_key(mod.contract_key, key),
                combined_component_keys=(),
            )
            position = (
                None if mod.event is None else progress_events.Position(mod.event.order_key, False)
            )
            counts = progress_events.tally(
                ctx, st, contract, component, mod.effective_date, position
            )
            remaining -= counts.counted - counts.returned
        if remaining + change < 0:
            raise ValueError(
                f"Combined component {key} removal exceeds its original remaining quantity"
            )


def view(ctx: BookContext, st: AllocatedState, mod: ModificationView) -> ModificationView:
    names = aliases(st, mod.contract_key)
    if not names:
        return mod
    # Removing every original component ends the combination, so no surviving scope
    # needs reassessment. Retain separate original lines and their signed quantities.
    removed = {
        ob.obligation_key
        for ob in st.obligations
        if mod.kind == "TERMINATION"
        and (mod.event is None or mod.event.event_type == "CONTRACT_TERMINATED")
        and ob.contract_key == mod.contract_key
        and ob.combined_component_keys
        and {
            line.obligation_key
            for line in mod.lines
            if names.get(line.obligation_key) == ob.obligation_key
        }
        == set(ob.combined_component_keys)
        and all(
            line.action == "REMOVE"
            and line.quantity_delta <= 0
            and line.consideration_delta <= 0
            and all(line.members.get(name) is None for name in ("start_date", "end_date"))
            for line in mod.lines
            if names.get(line.obligation_key) == ob.obligation_key
        )
    }
    _check_original_removals(ctx, st, mod, removed)
    lines = []
    for line in mod.lines:
        host = names.get(line.obligation_key)
        if host is None or line.action == "ADD":
            lines.append(line)
            continue
        # A component quantity or transfer-term change can invalidate the reviewed combination.
        # It needs reassessment, not an inferred change to the host's synthetic quantity/term.
        if host not in removed and (
            line.action != "CHANGE"
            or line.quantity_delta != 0
            or any(line.members.get(name) is not None for name in ("start_date", "end_date"))
        ):
            raise ValueError("Combined component quantity or term changes require reassessment")
        # Keep the original immutable members for source evidence; only the calculation target
        # changes. Multiple component price deltas remain separate and are summed by the pool.
        lines.append(replace(line, obligation_key=host))
    return replace(mod, lines=tuple(lines), questionnaire=keyed(mod.questionnaire, names))
