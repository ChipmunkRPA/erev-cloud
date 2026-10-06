"""The trigger a bundle is built under, without a database (item FX-REPUBLISH-DIRTY-1; 05 RCP-17
rev 1.206; 04 T-CON-03 ``dirty_trigger`` rev 1.297): ``contracts.bundles.marked_trigger``.

A mark set by the approval of an FX rate set version carries ``FX_REPUBLISH``. The computation
that consumes it is stored under that trigger only when its caller asked under ``COMMAND`` and
its bundle first-includes no event — no member event beyond the stream heads of the group's
latest computation. Then its lineage is empty and its trigger is no event's: the proof the
out-of-period register asks before it attributes a line posted behind a lock to a trigger
(ENGINE_SPEC_B S15-R-18b). The database witnesses are
``tests/domain/contracts/test_fx_republish_mark.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from erev_api.domain.contracts.bundles import marked_trigger
from erev_api.enums import ComputationTrigger

COMMAND = ComputationTrigger.COMMAND
FX_REPUBLISH = ComputationTrigger.FX_REPUBLISH
MARKED = {"dirty_trigger": FX_REPUBLISH}
HEADS = (("K-01", 3), ("K-02", 5))


@dataclass(frozen=True)
class _Event:
    """The two members of an ``EventInput`` the rule reads."""

    contract_key: str
    stream_version: int


def _included(*events: tuple[str, int]) -> list[Any]:
    return [_Event(key, version) for key, version in events]


INCLUDED = _included(("K-01", 1), ("K-01", 2), ("K-01", 3), ("K-02", 5))


def test_a_marked_group_computed_without_a_new_event_takes_the_marks_trigger() -> None:
    """Every event of the bundle was in the group's latest computation: the close run's
    ``RECOMPUTE_DIRTY``, a job, a command's recompute — whoever asks under ``COMMAND``."""
    assert marked_trigger(COMMAND, MARKED, INCLUDED, HEADS) == "FX_REPUBLISH"
    assert marked_trigger("COMMAND", MARKED, INCLUDED, HEADS) == "FX_REPUBLISH"
    assert marked_trigger(COMMAND, MARKED, [], HEADS) == "FX_REPUBLISH"


def test_the_trigger_is_read_as_the_row_gives_it() -> None:
    """A row read through the table gives the enumeration's member, a raw row its text."""
    assert marked_trigger(COMMAND, {"dirty_trigger": "FX_REPUBLISH"}, INCLUDED, HEADS) == (
        "FX_REPUBLISH"
    )


@pytest.mark.parametrize("new", [("K-01", 4), ("K-02", 6)])
def test_a_computation_that_brings_an_event_stays_command(new: tuple[str, int]) -> None:
    """One event beyond a member's head is enough: the lines carry it (S14-R-13a)."""
    assert marked_trigger(COMMAND, MARKED, [*INCLUDED, _Event(*new)], HEADS) == "COMMAND"


def test_a_member_the_latest_computation_never_read_brings_its_events() -> None:
    """A contract that joined the group since: no head of it is known, so each of its events is
    first-included here."""
    assert marked_trigger(COMMAND, MARKED, [*INCLUDED, _Event("K-03", 1)], HEADS) == "COMMAND"
    assert marked_trigger(COMMAND, MARKED, _included(("K-01", 1)), ()) == "COMMAND"


def test_a_group_without_a_mark_is_computed_under_what_its_caller_asks() -> None:
    assert marked_trigger(COMMAND, {"dirty_trigger": None}, INCLUDED, HEADS) == "COMMAND"
    assert marked_trigger(COMMAND, {}, INCLUDED, HEADS) == "COMMAND"


@pytest.mark.parametrize(
    "asked",
    [trigger for trigger in ComputationTrigger if trigger is not ComputationTrigger.COMMAND],
)
def test_a_caller_that_names_another_trigger_keeps_it(asked: ComputationTrigger) -> None:
    """Only ``COMMAND`` yields: a restatement, a policy rerun, a replay, an upgrade's validation,
    a period-end pass and a migration say what they are, on a marked group too."""
    assert marked_trigger(asked, MARKED, INCLUDED, HEADS) == asked.value
    assert marked_trigger(asked.value, MARKED, INCLUDED, HEADS) == asked.value
