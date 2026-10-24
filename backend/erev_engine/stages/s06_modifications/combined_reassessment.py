"""Explicit effective-date continuation of an original combined unit population."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from fractions import Fraction
from types import MappingProxyType

from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s01_canonicalize.convert import payload_fraction
from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.s09_recognition import progress_events
from erev_engine.stages.state import AllocatedState, BookContext, ObligationState


def originals(st: AllocatedState, ob: ObligationState) -> dict[str, Mapping[str, object]]:
    contract = next(c for c in st.contracts if c.header.external_id == ob.contract_key)
    lines = contract.booking.get("lines")
    if not isinstance(lines, (list, tuple)) or any(not isinstance(line, Mapping) for line in lines):
        raise ValueError("Combined reassessment requires original booking lines")
    return {str(line["obligation_key"]): line for line in lines}


def quantities(st: AllocatedState, ob: ObligationState) -> dict[str, Fraction]:
    if ob.combined_component_quantities:
        return dict(ob.combined_component_quantities)
    rows = originals(st, ob)
    return {
        key: payload_fraction(rows[key], "quantity") or Fraction(0)
        for key in ob.combined_component_keys
    }


def continued(ctx: BookContext, st: AllocatedState, mod: ModificationView) -> set[str]:
    if not ctx.combined_quantity_reassessment:
        return set()
    decisions = mod.questionnaire.get("combined_reassessment", {})
    if not isinstance(decisions, Mapping):
        raise ValueError("Combined reassessment must name each original host")
    result = set()
    for ob in st.obligations:
        if ob.contract_key != mod.contract_key or not ob.combined_component_keys:
            continue
        changes = [line for line in mod.lines if line.obligation_key in ob.combined_component_keys]
        term_change = any(
            line.members.get(k) is not None for line in changes for k in ("start_date", "end_date")
        )
        if not any(line.quantity_delta for line in changes) and not (
            ctx.combined_unit_term_reassessment and term_change
        ):
            continue
        decision = decisions.get(ob.obligation_key)
        if not isinstance(decision, Mapping):
            continue  # Existing refusal explains the required reassessment.
        members = decision.get("component_keys")
        if (
            decision.get("decision") != "CONTINUE"
            or decision.get("effective_date") != mod.effective_date.isoformat()
            or not isinstance(members, (tuple, list))
            or len(members) != len(ob.combined_component_keys)
            or set(members) != set(ob.combined_component_keys)
            or decision.get("same_transfer_pattern") is not True
            or decision.get("operating_lease") is not True
            or decision.get("nonlease_predominates") is not (ob.scope_flag == "IN_SCOPE_606")
        ):
            raise ValueError("Combined continuation requires complete dated eligibility assessment")
        if mod.template_mode is not None or ob.scope_flag != "IN_SCOPE_606":
            raise ValueError("Combined quantity continuation requires native in-scope treatment")
        time_terms = (
            ctx.combined_time_term_reassessment
            and term_change
            and ob.recognition_method == "TIME_ELAPSED"
        )
        if ob.recognition_method not in {"UNITS_DELIVERED", "POINT_IN_TIME"} and not time_terms:
            raise ValueError("Combined quantity continuation requires an original unit measure")
        if any(line.action != "CHANGE" for line in changes):
            raise ValueError("Combined member removal requires separate reassessment")
        if term_change:
            ends = [line.members.get("end_date") for line in changes]
            if (
                not ctx.combined_unit_term_reassessment
                or mod.kind != "TERM_CHANGE"
                or len(changes) != len(ob.combined_component_keys)
                or {line.obligation_key for line in changes} != set(ob.combined_component_keys)
                or any(
                    line.quantity_delta or line.members.get("start_date") is not None
                    for line in changes
                )
                or any(end is None for end in ends)
                or len({str(end) for end in ends}) != 1
            ):
                raise ValueError(
                    "Combined term continuation requires every original member "
                    "and one common end date"
                )
            if date.fromisoformat(str(ends[0])) < mod.effective_date:
                raise ValueError("Combined term continuation cannot end before its effective date")
        current = quantities(st, ob)
        contract = next(c for c in st.contracts if c.header.external_id == ob.contract_key)
        for key, total in current.items():
            delta = sum(
                (line.quantity_delta for line in changes if line.obligation_key == key), Fraction(0)
            )
            if time_terms:
                # A time-only change keeps quantities intact. Original delivery counters
                # do not measure elapsed service; the prospective boundary measures it.
                continue
            component = replace(
                ob,
                obligation_key=key,
                subject_key=obligation_subject_key(ob.contract_key, key),
                combined_component_keys=(),
            )
            counts = progress_events.tally(
                ctx,
                st,
                contract,
                component,
                mod.effective_date,
                None if mod.event is None else progress_events.Position(mod.event.order_key, False),
            )
            if total + delta <= 0 or total + delta < counts.counted - counts.returned:
                raise ValueError(
                    "Combined continuation must retain each member and transferred units"
                )
        result.add(ob.obligation_key)
    return result


def install(
    before: AllocatedState, after: AllocatedState, mod: ModificationView, hosts: set[str]
) -> AllocatedState:
    if mod.event is None or not hosts:
        return after
    old = {ob.subject_key: ob for ob in before.obligations}
    result = []
    for ob in after.obligations:
        if (
            ob.contract_key == mod.contract_key
            and ob.obligation_key in hosts
            and any(seg.event_key == mod.event.event_key for seg in ob.segments)
        ):
            current = quantities(before, old[ob.subject_key])
            for line in mod.lines:
                if line.obligation_key in current:
                    current[line.obligation_key] += line.quantity_delta
            ob = replace(ob, combined_component_quantities=MappingProxyType(current))
        result.append(ob)
    return replace(after, obligations=tuple(result))
