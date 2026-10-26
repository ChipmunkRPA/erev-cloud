"""Original-member royalty corrections and accrual replacement before aggregation."""

from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import date

from erev_engine import royalties
from erev_engine.errors import EngineError
from erev_engine.stages.state import EstimatePin, EstimatePins, EventView, OrderKey


def realised(
    events: Iterable[EventView],
    pins: EstimatePins,
    contract: str,
    host: str,
    subject: str,
    *,
    component_keys: Sequence[str],
    at: date,
    cutoff: OrderKey | None,
    inclusive: bool,
    accrue: bool,
) -> royalties.Realisation:
    members = frozenset(component_keys)
    selected: dict[str, list[EventView]] = {}
    estimates: dict[str, dict[str, list[EstimatePin]]] = {}

    def fail(reason: str) -> None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            reason,
            subject_key=subject,
            detail={"rule": "COMBINED_ROYALTY_SCOPE"},
        )

    def scope(mode: object, targets: set[str]) -> str:
        if mode == "COMBINATION":
            if targets != {host}:
                fail("A group-wide royalty source must target the combined obligation")
            return "COMBINATION"
        if mode != "MEMBERS" or len(targets) != 1 or not targets <= members:
            fail("Specify royalty_scope COMBINATION or MEMBERS with one original member")
        return next(iter(targets))

    for event in events:
        if not royalties.is_statement(event) or event.contract_key != contract:
            continue
        if event.effective_date > at or not royalties._admits(event.order_key, cutoff, inclusive):
            continue
        targets = {
            key
            for key in members
            if royalties.names_obligation(
                event,
                contract,
                key,
                f"{royalties._encode(contract)}/{royalties._encode(key)}",
            )
        }
        if not targets:
            continue
        selected.setdefault(scope(event.payload.get("royalty_scope"), targets), []).append(event)
    for key, versions in pins.pins.items() if accrue else ():
        for pin in versions:
            v = pin.version
            if v.effective_date > at or not royalties._admits(
                pin.event_order_key, cutoff, inclusive
            ):
                continue
            targets = {member for member in members if royalties._targets(v, contract, member)}
            if not targets:
                continue
            owner = scope(v.parameters.get("royalty_scope"), targets)
            estimates.setdefault(owner, {}).setdefault(key, []).append(pin)

    statements: list[royalties.Statement] = []
    accruals: list[royalties.Accrual] = []
    for owner in sorted(set(selected) | (set(estimates) if accrue else set())):
        key = host if owner == "COMBINATION" else owner
        found = royalties.realised(
            selected.get(owner, ()),
            EstimatePins({key: tuple(items) for key, items in estimates.get(owner, {}).items()}),
            contract,
            key,
            f"{royalties._encode(contract)}/{royalties._encode(key)}",
            at=at,
            cutoff=cutoff,
            inclusive=inclusive,
            accrue=accrue,
        )
        statements.extend(replace(item, scope=owner) for item in found.statements)
        accruals.extend(replace(item, scope=owner) for item in found.accruals)

    all_items: list[royalties.Statement | royalties.Accrual] = [*statements, *accruals]
    for index, item in enumerate(all_items):
        for other in all_items[index + 1 :]:
            if (
                item.start <= other.end
                and other.start <= item.end
                and (item.scope == other.scope or "COMBINATION" in {item.scope, other.scope})
            ):
                fail("Royalty usage periods have overlapping group or member scopes")
    # Intermediate event positions intentionally show partial causal input sets. Final
    # measurements require a complete population, including explicit zero statements.
    if cutoff is None:
        for start, end in {(item.start, item.end) for item in all_items}:
            covered = {item.scope for item in all_items if (item.start, item.end) == (start, end)}
            if "COMBINATION" not in covered and covered != members:
                fail(
                    "Provide royalty statements or accruals for every original member "
                    "and usage period"
                )
    return royalties.Realisation(tuple(statements), tuple(accruals))
