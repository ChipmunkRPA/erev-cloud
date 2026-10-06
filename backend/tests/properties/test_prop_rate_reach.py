"""The groups a changed rate reaches, against the engine (BUILD_SPEC PRP-7; item
FX-REPUBLISH-DIRTY-1; 04 T-REF-11 "The groups a changed rate reaches" rev 1.297): examples of
the property ``RevenueMachine`` holds after every republication, and its fail-first witness.

The approval of an FX rate set version marks the contract groups its changed rates reach
(``erev_api.domain.close.rate_reach``). Which groups those are is a rule about what a line of a
period can be made of — ``reach_of`` for a changed key, ``at_work`` for a group — and the
machine holds it against the engine: whenever a republication moves a line the platform would
post, of the recompute or of a period-end pass, the group is at work in the reach of a changed
key (``RevenueMachine._the_reach_holds``). Here the same check on worlds chosen for one clause
each, in a USD world of a JPY entity:

- a balance left open is the ONLY thing that puts a group in the reach of a later closing rate,
  and with that clause switched off the property fails (DG-PROP-02);
- an event dated in the reach of a spot rate, and a schedule line in the period of an average
  rate, do the same for those kinds;
- a contract finished and settled before the reach is not at work there, and nothing of it
  moves: the rule is not "every group".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import test_prop_state_machine as machine_module
from erev_api.domain.close.rate_reach import at_work
from support import oracle, platform_props
from support.prop_worlds import LineSpec

pytestmark = pytest.mark.property

MARCH = (date(2026, 3, 1), date(2026, 3, 31))
APRIL = (date(2026, 4, 1), date(2026, 4, 30))
UNITS = LineSpec("POB-01", "PIT", 5000, 50, 2, 0, 0)  # two units for 50.00, point in time
SERVICE = LineSpec("POB-01", "DAILY", 120000, 100, 1, 0, 12)  # 1,200.00 over twelve months

Amounts = dict[tuple[object, ...], tuple[int, int]]


def _checked(machine: machine_module.RevenueMachine) -> tuple[Amounts, dict[str, Any]]:
    """The invariant over the world as it stands; the lines the run it checked posts, and the
    facts ``at_work`` reads of the group as that run leaves it."""
    machine.engine_agrees_with_the_oracle_and_the_properties_hold()
    assert machine.posted_amounts is not None and machine.reach_facts is not None
    return machine.posted_amounts, machine.reach_facts


def _moved(machine: machine_module.RevenueMachine, before: Amounts) -> bool:
    """Whether the world as it stands posts another line than ``before``."""
    run = platform_props.close_run(machine.bundle())
    return bool(machine._amounts(*run.outputs, sealed=machine.sealed) != before)


def _republished(machine: machine_module.RevenueMachine, kind: str, index: int) -> None:
    machine._publish([kind], index, [machine.rates[(kind, index)] + Decimal(1)])


def _delivered_and_unbilled() -> machine_module.RevenueMachine:
    """Two units delivered on 6 January and never billed: the revenue stands as an asset layer
    at January's average rate, remeasured at every later closing rate (S12-R-06, S12-R-09)."""
    machine = machine_module._two_currency_machine()
    machine._create_contract([UNITS])
    machine._record("K-1", UNITS, "DELIVERY", 5, 2)
    return machine


def test_a_position_alone_puts_a_group_in_the_reach_of_a_later_closing_rate() -> None:
    """March's closing rate is republished. Nothing of the group is dated in March or later — no
    event, no schedule line, no line its computation posts — and the remeasurement of March and
    of April moves all the same: the open balance is what the rate enters."""
    machine = _delivered_and_unbilled()
    before, facts = _checked(machine)
    assert facts["position"] is True
    assert not at_work(*MARCH, **{**facts, "position": False})

    _republished(machine, oracle.CLOSING, 2)

    assert machine.republished == [(oracle.CLOSING, 2)]
    assert _moved(machine, before)
    _checked(machine)  # the property holds: the reach finds the group at work
    assert machine.republished == []


def test_without_the_position_clause_the_property_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-first (DG-PROP-02): the same world against a rule that does not ask for a position —
    the republication moves lines of a group that rule calls at rest."""

    def no_position(first: date, last: date | None, **facts: Any) -> bool:
        return at_work(first, last, **{**facts, "position": False})

    machine = _delivered_and_unbilled()
    _checked(machine)
    _republished(machine, oracle.CLOSING, 2)
    monkeypatch.setattr(machine_module, "at_work", no_position)
    with pytest.raises(AssertionError, match="the reach"):
        machine.engine_agrees_with_the_oracle_and_the_properties_hold()


def test_a_contract_finished_and_settled_before_the_reach_is_not_at_work_and_nothing_moves() -> (
    None
):
    """The two units are delivered on 6 January and billed in full on 11 January: the asset layer
    is settled, nothing stays open. April's spot, average and closing rates are republished:
    the group is not at work in April, and no line moves — the mark would be a recompute that
    posts nothing."""
    machine = machine_module._two_currency_machine()
    machine._create_contract([UNITS])
    machine._record("K-1", UNITS, "DELIVERY", 5, 2)
    machine._record("K-1", UNITS, "BILLING", 10, 5000)
    before, facts = _checked(machine)
    assert facts["position"] is False
    assert not at_work(*APRIL, **facts)

    for kind in machine_module.RATE_KINDS:
        _republished(machine, kind, 3)

    assert sorted(machine.republished) == sorted((kind, 3) for kind in machine_module.RATE_KINDS)
    assert not _moved(machine, before)
    _checked(machine)


def test_an_event_in_the_reach_of_a_spot_rate_puts_its_group_there() -> None:
    """A service billed 600.00 on 10 February: the liability layer is created at February's spot
    rate, dated the first of the month and answering until the day before March's (S12-R-02).
    The rate is republished, the layer and every relief of it move, and the billing — an event
    dated in the reach — is why the group is at work there."""
    machine = machine_module._two_currency_machine()
    machine._create_contract([SERVICE])
    machine._record("K-1", SERVICE, "BILLING", 40, 60000)
    before, facts = _checked(machine)
    assert date(2026, 2, 10) in facts["events"]

    _republished(machine, oracle.SPOT, 1)

    assert _moved(machine, before)
    _checked(machine)


def test_a_schedule_line_in_the_period_of_an_average_rate_puts_its_group_there() -> None:
    """A service that is not billed: each month's revenue stands at that month's average rate
    (POL-162 ``PERIOD_AVERAGE``). June's average is republished and June's revenue moves; the
    group is at work in June by its schedule line of that month."""
    machine = machine_module._two_currency_machine()
    machine._create_contract([SERVICE])
    before, facts = _checked(machine)
    assert date(2026, 6, 30) in facts["scheduled"]

    _republished(machine, oracle.AVERAGE, 5)

    assert _moved(machine, before)
    _checked(machine)


def test_a_copy_of_the_machine_keeps_what_the_check_is_held_against() -> None:
    """The machine is deep-copied where it tries a step out (``_admits_contract``): the lines
    and the facts of the last check are plain data and are copied with it."""
    import copy

    machine = _delivered_and_unbilled()
    before, facts = _checked(machine)
    twin = copy.deepcopy(machine)
    assert (twin.posted_amounts, twin.reach_facts) == (before, facts)
