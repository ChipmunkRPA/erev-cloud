"""Select FX paid origins from the original calendar, following S14's locked run."""

from collections.abc import Sequence

from erev_engine.bundle import PeriodInput
from erev_engine.dates import POSTABLE_STATES, period_state


def paid_origins(
    periods: Sequence[PeriodInput], *, book: str, target: str, previous: str | None, basis: str
) -> frozenset[str]:
    ordered = sorted(periods, key=lambda item: (item.start_date, item.end_date))
    positions = {item.period_key: index for index, item in enumerate(ordered)}
    if target not in positions or (previous is not None and previous not in positions):
        raise ValueError("FX paid-source periods are absent from the retained calendar.")
    if basis not in {"TIME", "EVENT", "ALL"}:
        raise ValueError("Unknown FX paid-source basis.")
    selected = {target}
    if basis != "TIME":
        return frozenset(selected)
    index = positions[target]
    if period_state(ordered[index], book) not in POSTABLE_STATES:
        raise ValueError("TIME FX must post into an originally postable period.")
    # S14 pools only the immediately preceding closed run, not every period
    # since a sparse cumulative target. An intervening open period ends the run.
    for period in reversed(ordered[:index]):
        if period.period_key == previous or period_state(period, book) not in {
            "closed",
            "permanently_locked",
        }:
            break
        selected.add(period.period_key)
    return frozenset(selected)
