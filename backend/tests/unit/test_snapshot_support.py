"""The load-chain helpers of ``support.snapshots`` (05 SBX-06 rev 1.34; supervisor ruling R-7).
CPU-only: what explains an audit event of a loaded sandbox and what does not — so the DB
witnesses built on ``unexplained_load_events`` can fail, and the two enumerated action sets change
only deliberately."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from erev_api.domain.platform import sandboxes as sb
from support.snapshots import (
    LOAD_RECOMPUTE_ACTIONS,
    LOAD_REPLAY_ACTIONS,
    LoadChain,
    load_outcome,
    load_step,
    unexplained_load_events,
)

JOB = UUID("01a0c1a2-0000-7000-8000-00000000000a")
OTHER_JOB = UUID("01a0c1a2-0000-7000-8000-00000000000b")
GROUP = UUID("01a0c1a2-0000-7000-8000-00000000000c")
TRANSITION = UUID("01a0c1a2-0000-7000-8000-00000000000d")
ITEM_CREATED = "exception_item.create"


def _event(action: str, step: str, *, job: UUID = JOB) -> dict[str, Any]:
    return {"action": action, "request_id": f"job-{job}-{step}"}


def _chain(
    before: list[dict[str, Any]],
    *,
    summary: dict[str, Any] | None = None,
    after: list[dict[str, Any]] | None = None,
) -> LoadChain:
    return LoadChain(
        tuple(before),
        summary if summary is not None else _event(sb.ACTION_LOADED, "report"),
        tuple(after or ()),
    )


def test_the_enumerated_actions_are_pinned() -> None:
    """The actions a load's own steps write before its summary, by name: a new writer on the
    replay or the recompute path changes one of these sets first."""
    assert LOAD_REPLAY_ACTIONS == {
        "period_state_transition.create",
        "period.open",
        "period.start_close",
        "period.cancel_close",
        "period.lock",
        "period.reopen",
        "period.permanent_lock",
    }
    assert LOAD_RECOMPUTE_ACTIONS == {
        "contract_computation.create",
        "contract_version.create",
        "calc_trace.create",
        "obligation_version.create",
        "contract_version_balance.create",
        "schedule.create",
        "schedule_line.create",
        "subledger_posting.create",
        "subledger_line.create",
        "subledger_posting_seal.create",
        ITEM_CREATED,
        "exception_item.severity_changed",
    }
    assert not LOAD_REPLAY_ACTIONS & LOAD_RECOMPUTE_ACTIONS
    assert sb.ACTION_LOADED not in LOAD_REPLAY_ACTIONS | LOAD_RECOMPUTE_ACTIONS


def test_load_step_reads_the_step_from_the_request_id_of_the_load_job() -> None:
    assert load_step(_event("period_state_transition.create", "periods"), JOB) == "replay"
    assert load_step(_event("period.open", f"replay-{TRANSITION}"), JOB) == "replay"
    assert load_step(_event("schedule.create", f"recompute-{GROUP}"), JOB) == "recompute"
    assert load_step(_event(sb.ACTION_LOADED, "report"), JOB) == "report"
    # steps of the load that write no audit event, another job, and a request of no job at all
    for step in ("provision", "load-contract", "fixup", "groups", "verify", "replayed"):
        assert load_step(_event("period.open", step), JOB) is None, step
    assert load_step(_event("period.open", "periods", job=OTHER_JOB), JOB) is None
    assert load_step({"action": "period.open", "request_id": "01a0c1a2-request"}, JOB) is None


def test_a_sound_load_chain_is_explained() -> None:
    sound = _chain(
        [
            _event("period_state_transition.create", "periods"),
            _event("period.open", f"replay-{TRANSITION}"),
            _event("subledger_posting.create", f"recompute-{GROUP}"),
            _event("contract_computation.create", f"recompute-{GROUP}"),
            _event(ITEM_CREATED, f"recompute-{GROUP}"),
            _event("period.start_close", f"replay-{TRANSITION}"),
        ],
        after=[_event(ITEM_CREATED, "report"), _event(ITEM_CREATED, "report")],
    )
    assert unexplained_load_events(sound, JOB) == []
    assert unexplained_load_events(_chain([]), JOB) == []  # nothing to replay or recompute


def test_every_event_the_load_does_not_explain_is_named() -> None:
    """One unexplained event at a time, each returned exactly: a command of someone else, another
    job, an action of the other step, an action of neither set, a second summary, a summary the
    report step did not write, and anything but the report step's warning items after it."""
    foreign = {"action": "contract.update", "request_id": "01a0c1a2-a-user-request"}
    for stray in (
        foreign,
        _event("period.open", "periods", job=OTHER_JOB),
        _event("period.open", f"recompute-{GROUP}"),  # a replay action under a recompute
        _event("schedule.create", f"replay-{TRANSITION}"),  # a recompute action under a replay
        _event("contract.update", f"recompute-{GROUP}"),  # the right step, not an enumerated action
        _event("tenant.sandbox_requested", "periods"),
        _event(sb.ACTION_LOADED, "report"),  # an earlier summary is not a replay or a recompute
        _event("contract_computation.create", "groups"),  # a step that writes no audit event
    ):
        chain = _chain([_event("period.open", f"replay-{TRANSITION}"), stray])
        assert unexplained_load_events(chain, JOB) == [stray], stray
    misplaced = _event(sb.ACTION_LOADED, f"recompute-{GROUP}")
    assert unexplained_load_events(_chain([], summary=misplaced), JOB) == [misplaced]
    for late in (
        _event("period.open", "report"),  # not a warning item
        _event(ITEM_CREATED, f"recompute-{GROUP}"),  # an item, but not the report step's
        foreign,
    ):
        chain = _chain([], after=[_event(ITEM_CREATED, "report"), late])
        assert unexplained_load_events(chain, JOB) == [late], late
    # the same chain read for another job explains nothing
    sound = _chain([_event("period.open", f"replay-{TRANSITION}")])
    assert len(unexplained_load_events(sound, OTHER_JOB)) == 2  # the event and the summary


def test_the_outcome_line_names_a_failed_recompute() -> None:
    """The assertion message of the sandbox witnesses: short enough that pytest shows it whole,
    and it says ``not recomputed`` beside the mismatch count; a missing member reads ``None``."""
    counts = {"groups_recomputed": 0, "groups_not_recomputed": 1, "derived_mismatches": 1}
    assert load_outcome(counts) == (
        "groups recomputed 0, not recomputed 1, mismatches 1, blocked periods None"
    )
