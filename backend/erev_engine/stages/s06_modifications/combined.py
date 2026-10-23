"""Resolve original lessor component references onto the reviewed combined obligation."""

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.state import AllocatedState


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


def view(st: AllocatedState, mod: ModificationView) -> ModificationView:
    names = aliases(st, mod.contract_key)
    if not names:
        return mod
    lines = []
    for line in mod.lines:
        host = names.get(line.obligation_key)
        if host is None or line.action == "ADD":
            lines.append(line)
            continue
        # A component quantity or transfer-term change can invalidate the reviewed combination.
        # It needs reassessment, not an inferred change to the host's synthetic quantity/term.
        if (
            line.action != "CHANGE"
            or line.quantity_delta != 0
            or any(line.members.get(name) is not None for name in ("start_date", "end_date"))
        ):
            raise ValueError("Combined component quantity or term changes require reassessment")
        # Keep the original immutable members for source evidence; only the calculation target
        # changes. Multiple component price deltas remain separate and are summed by the pool.
        lines.append(replace(line, obligation_key=host))
    return replace(mod, lines=tuple(lines), questionnaire=keyed(mod.questionnaire, names))
