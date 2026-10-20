from datetime import date

import pytest
from erev_api.domain.reports.fx_paid_periods import paid_origins
from erev_engine.bundle import PeriodInput


def calendar(states: tuple[str, ...]) -> tuple[PeriodInput, ...]:
    return tuple(
        PeriodInput(f"P{i}", 2026, i, date(2026, i, 1), date(2026, i, 28), (("ASC606", state),))
        for i, state in enumerate(states, 1)
    )


def test_sparse_target_does_not_pull_paid_lines_across_an_open_period() -> None:
    periods = calendar(("closed", "open", "closed", "permanently_locked", "open"))
    assert paid_origins(periods, book="ASC606", target="P5", previous=None, basis="TIME") == {
        "P3",
        "P4",
        "P5",
    }
    # An EVENT carry still subtracts only the event's origin, even when locked.
    assert paid_origins(periods, book="ASC606", target="P4", previous="P1", basis="EVENT") == {"P4"}


def test_retained_anchor_bounds_the_locked_run() -> None:
    periods = calendar(("closed", "closed", "open"))
    assert paid_origins(periods, book="ASC606", target="P3", previous="P1", basis="TIME") == {
        "P2",
        "P3",
    }
    with pytest.raises(ValueError, match="postable"):
        paid_origins(periods, book="ASC606", target="P2", previous=None, basis="TIME")
