"""Dated transaction-currency acquisition entries alongside ordinary member activity."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import TYPE_CHECKING

from erev_engine.errors import EngineError
from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s12_fx_entities import ControlFlow
from erev_engine.stages.state import BookContext, EventView, ObligationState

if TYPE_CHECKING:
    from .rollforward import BalanceInputs


@dataclass(frozen=True)
class Acquisition:
    amounts: Mapping[str, int]


def is_mixed(own: Sequence[ObligationState]) -> bool:
    acquired = [
        ob for ob in own if ob.opening and ob.opening.get("reason") == "BUSINESS_COMBINATION"
    ]
    return bool(acquired) and len(acquired) != len(own)


def cutovers(own: Sequence[ObligationState]) -> dict[str, date]:
    result = {}
    for ob in own:
        if ob.opening is None:
            continue
        baseline = baseline_of(ob)
        if (
            ob.opening.get("reason") != "BUSINESS_COMBINATION"
            or baseline is None
            or baseline.method != "OPENING_BALANCES_AT_CUTOVER"
            or ob.principal_agent.value != "PRINCIPAL"
        ):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "Mixed acquisition requires original principal cutover baselines.",
            )
        result[ob.subject_key] = baseline.cutover_date
    return result


def items(
    ctx: BookContext,
    records: "BalanceInputs",
    own: Sequence[ObligationState],
    events: Sequence[EventView],
    entity: str,
    start: date,
    end: date,
) -> list[ControlFlow | Acquisition]:
    from .rollforward import _entered, _established, _order

    dates = cutovers(own)
    by_subject = {ob.subject_key: ob for ob in own}
    by_event: dict[str, list[ObligationState]] = {}
    for ob in own:
        if ob.subject_key in dates and ob.opening is not None:
            by_event.setdefault(str(ob.opening["event_key"]), []).append(ob)
    source_events = {event.event_key: event for event in events}
    ordered: list[tuple[date, tuple[int, int, str, str, str], ControlFlow | Acquisition]] = []
    for key, members in by_event.items():
        event = source_events.get(key)
        cutover = dates[members[0].subject_key]
        if not start <= cutover <= end:
            continue
        if event is None or any(dates[ob.subject_key] != cutover for ob in members):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED", "Acquisition event order is unavailable."
            )
        ordered.append(
            (
                cutover,
                (1, event.record_seq, key, "", "ACQUISITION"),
                Acquisition(_established(ctx, records, members, entity, cutover)),
            )
        )
    for flow in records.flows:
        when = _entered(flow)
        if flow.entity != entity or when is None or not start <= when <= end:
            continue
        selected = flow
        if flow.kind in {"BILLING", "CREDIT_MEMO"}:
            shares = records.attribution.get(flow.source_key, {})
            sign = 1 if flow.kind == "BILLING" else -1
            if shares:
                if set(shares) - set(by_subject) or sum(shares.values()) != sign * flow.amount:
                    raise EngineError(
                        "ENGINE_INVARIANT_VIOLATED",
                        "Mixed acquisition billing attribution is incomplete.",
                    )
                amount = sign * sum(
                    value
                    for subject, value in shares.items()
                    if subject not in dates or when > dates[subject]
                )
                if amount < 0:
                    raise EngineError("ENGINE_INVARIANT_VIOLATED", "Mixed billing signs differ.")
                if not amount:
                    continue
                selected = replace(flow, amount=amount)
            else:
                owners = [ob for ob in own if ob.contract_key == flow.contract_key]
                if not owners or any(ob.subject_key in dates for ob in owners):
                    raise EngineError(
                        "ENGINE_INVARIANT_VIOLATED",
                        "Acquired billing requires original obligation attribution.",
                    )
        elif flow.subject_key in by_subject:
            if flow.subject_key in dates and when <= dates[flow.subject_key]:
                continue
        else:
            owners = [ob for ob in own if ob.contract_key == flow.contract_key]
            if not owners:
                raise EngineError("ENGINE_INVARIANT_VIOLATED", "Mixed flow owner is unavailable.")
            owner_dates = {dates[ob.subject_key] for ob in owners if ob.subject_key in dates}
            if owner_dates:
                if len(owner_dates) != 1 or any(ob.subject_key not in dates for ob in owners):
                    raise EngineError(
                        "ENGINE_INVARIANT_VIOLATED", "Mixed flow cutover is ambiguous."
                    )
                if when <= next(iter(owner_dates)):
                    continue
        ordered.append((when, _order(selected), selected))
    return [item for _, _, item in sorted(ordered, key=lambda entry: (entry[0], entry[1]))]


def enter(
    entry: Acquisition,
    layers: list[list[int]],
    asset: dict[str, int],
    lines: dict[str, dict[str, int]],
) -> None:
    """Measure acquisition's change in presented positions, including existing netting."""
    liability, receivable, contract_asset = (
        "CONTRACT_LIABILITY",
        "UNBILLED_RECEIVABLE",
        "CONTRACT_ASSET",
    )
    caption = "BUSINESS_COMBINATIONS"
    credit = entry.amounts[liability]
    if credit:
        for role in (receivable, contract_asset):
            take = min(asset[role], credit)
            asset[role] -= take
            credit -= take
            lines[role][caption] -= take
        if credit:
            layers.append([0, credit])
            lines[liability][caption] += credit
        return
    debit = entry.amounts[receivable] + entry.amounts[contract_asset]
    for layer in layers:
        take = min(layer[1], debit)
        layer[1] -= take
        debit -= take
        lines[liability][caption] -= take
    receivable_part = min(debit, entry.amounts[receivable])
    for role, amount in ((receivable, receivable_part), (contract_asset, debit - receivable_part)):
        asset[role] += amount
        lines[role][caption] += amount
