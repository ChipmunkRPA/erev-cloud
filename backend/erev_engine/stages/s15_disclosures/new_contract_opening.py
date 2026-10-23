"""Prove post-opening inception from retained headers and the entire event population."""

from collections.abc import Sequence
from datetime import date

from erev_engine.bundle import ContractInput, EventInput
from erev_engine.stages.state import EventView


def zero_contracts(
    contracts: Sequence[ContractInput],
    events: Sequence[EventInput | EventView],
    opening_date: date,
) -> set[str]:
    proven = set()
    for contract in contracts:
        if contract.inception_date <= opening_date:
            continue
        population = [event for event in events if event.contract_key == contract.external_id]
        bookings = [event for event in population if event.event_type == "CONTRACT_BOOKED"]
        if len(bookings) == 1 and all(
            event.effective_date > opening_date
            and event.event_type != "OPENING_BALANCE_ESTABLISHED"
            for event in population
        ):
            proven.add(contract.external_id)
    return proven
