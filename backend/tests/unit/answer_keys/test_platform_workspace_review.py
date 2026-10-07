"""Codex workspace-adapter review of 161f90f (PRODUCTION-F-RPS-WORKSPACE-REVIEW-161f90f.md): rules
WSA-1 and WSA-2 of record §15 and the declared source gaps, with Codex's exact counterexamples.

- WSA-1: call construction is side-effect-free; a contract's local stream head advances only from
  a successful committed result ([2, 2] then head 3 after a refused event and its retry; the
  POS-CHK-012 seq 12 expected-refusal billing and seq 13 billing both map the same expected head).
- WSA-2: refusal verification needs a real before/after fingerprint; with no collector the step is
  ``not_run``, never ``executed``; a collector over mutated state yields ``failed`` STATE CHANGED.
- Gaps: ``unit_price`` stays a decimal string; ``is_manual`` is routing, not a payload member;
  estimate calls carry their actual values; each mapping-rule call carries one rule;
  successful results are kept in a ledger with stream versions, principal and clocks. The
  review's override gap — override calls carry their actual values — has no call left to state
  it on: the adapter builds no override call (register index 308), and the case says so.

The controls reuse the exact original POS-CHK-012 key plus the review's added inputs in a
temporary copy; no key, oracle or expected figure changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from erev_api.problems import Problem
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, H, load_platform_key, plan
from support.answer_keys.platform_runner import (
    EXECUTED,
    FAILED_STEP,
    NOT_RUN,
    DbPlatform,
    NotProvisioned,
    run_platform,
)
from support.answer_keys.workspace_adapter import (
    Call,
    RecordingInvoker,
    WorkspaceAdapter,
    booking_body,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2025, 12, 31, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class _Ticks:
    """An explicit, named mock fingerprint fixture over one integer of fake state (WSA-2)."""

    def __init__(self) -> None:
        self.state = 0

    def __call__(self) -> str:
        return str(self.state)


class _MutatingRefuser:
    """An inert invoker that mutates explicit fake state and then raises the expected problem for
    the configured seqs; every other call succeeds without touching the state."""

    def __init__(self, ticks: _Ticks, refuse: set[int]) -> None:
        self.ticks = ticks
        self.refuse = refuse
        self.calls: list[Call] = []

    def __call__(self, call: Call) -> object:
        self.calls.append(call)
        if call.step.seq in self.refuse and call.handler == H["record_events"]:
            self.ticks.state += 1
            raise Problem("validation-failed")
        return None


class _RefuseOnce:
    """Refuses the first record_events call for a contract, accepts the retry (no state change)."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.refused = False

    def __call__(self, call: Call) -> object:
        self.calls.append(call)
        if call.handler == H["record_events"] and not self.refused:
            self.refused = True
            raise Problem("validation-failed")
        return None


def _extended(tmp_path: Path, *, refused_seq: int = 12, retry_seq: int | None = 13) -> LoadedKey:
    """POS-CHK-012 with a schema-clean expected-refusal billing at seq 12 and, optionally, a later
    billing at seq 13 on the same contract (Codex's composed control)."""
    source = yaml.safe_load((ANSWER_KEY_ROOT / "pos" / f"{POS_012}.yaml").read_text())
    template = next(item for item in source["timeline"] if item["event_type"] == "BILLING_RECORDED")
    refused = {
        **template,
        "seq": refused_seq,
        "expect_problem": {"code": "validation-failed", "status": 422},
    }
    refused["payload"] = {
        **template["payload"],
        "invoice_number": "INV-REFUSED",
        "line_external_id": "L-REFUSED",
    }
    source["timeline"].append(refused)
    if retry_seq is not None:
        retry = {**template, "seq": retry_seq}
        retry["payload"] = {
            **template["payload"],
            "invoice_number": "INV-RETRY",
            "line_external_id": "L-RETRY",
        }
        source["timeline"].append(retry)
    target = tmp_path / "pos" / f"{POS_012}.yaml"
    target.parent.mkdir()
    target.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    return load(target)


def test_wsa_1_direct_refused_event_then_retry_keeps_the_head() -> None:
    """From committed head 2: the refused event and its retry both map expected version 2; the head
    is 3 afterwards (a refused command appends nothing). The head reaches 2 with the approval of
    the activation, which appends CONTRACT_ACTIVATED; its submission appends nothing. (The
    runner's own steps before an activation are left out here: the head is the subject.)"""
    loaded = load_platform_key(POS_012)
    invoker = _RefuseOnce()
    adapter = WorkspaceAdapter(loaded, invoker=invoker, clock=_Clock(), fingerprint=_Ticks())
    steps = plan(loaded).steps
    contract = loaded.key.contracts[0].external_id
    booking = next(s for s in steps if s.handler == H["book"] and contract in s.subject)
    submission = next(
        s for s in steps if s.handler == H["submit_activation"] and contract in s.subject
    )
    activation = next(
        s
        for s in steps
        if s.handler == H["decide"]
        and s.detail.get("emits") == "CONTRACT_ACTIVATED"
        and contract in s.subject
    )
    event = next(
        s
        for s in steps
        if s.handler == H["record_events"] and s.phase == "TIMELINE" and contract in s.subject
    )
    adapter.run(booking)
    adapter.run(submission)
    assert adapter.stream[contract] == 1
    adapter.run(activation)
    assert adapter.stream[contract] == 2
    with pytest.raises(Problem):
        adapter.run(event)  # refused: the head must not move
    assert adapter.stream[contract] == 2
    adapter.run(event)  # the retry succeeds
    versions = [
        c.kwargs["expected_stream_version"]
        for c in invoker.calls
        if c.handler == H["record_events"]
    ]
    assert versions == [2, 2]
    assert adapter.stream[contract] == 3


def test_wsa_1_composed_refusal_at_seq_12_leaves_seq_13_on_the_same_head(tmp_path: Path) -> None:
    loaded = _extended(tmp_path)
    ticks = _Ticks()
    invoker = _MutatingRefuser(
        ticks, refuse=set()
    )  # seq 12 is verified by refusal(); state untouched
    invoker.refuse = {12}

    class _Stable(_MutatingRefuser):
        def __call__(self, call: Call) -> object:
            self.calls.append(call)
            if call.step.seq in self.refuse and call.handler == H["record_events"]:
                raise Problem("validation-failed")  # refuses without mutating state
            return None

    stable = _Stable(ticks, {12})
    adapter = WorkspaceAdapter(loaded, invoker=stable, clock=_Clock(), fingerprint=ticks)
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    by_seq = {c.step.seq: c for c in stable.calls if c.handler == H["record_events"]}
    assert (
        by_seq[12].kwargs["expected_stream_version"] == by_seq[13].kwargs["expected_stream_version"]
    )
    statuses = {item.step.seq: item.status for item in result.executed if item.step.seq in (12, 13)}
    assert statuses == {12: EXECUTED, 13: EXECUTED}  # the verified refusal counts, unstamped
    assert 12 not in result.known_at and 13 in result.known_at


def test_wsa_2_no_fingerprint_collector_means_not_run(tmp_path: Path) -> None:
    loaded = _extended(tmp_path, retry_seq=None)
    ticks = _Ticks()
    mutating = _MutatingRefuser(ticks, {12})
    adapter = WorkspaceAdapter(loaded, invoker=mutating, clock=_Clock())  # no collector
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == NOT_RUN and "fingerprint" in (refusal.reason or "")
    with pytest.raises(NotProvisioned, match="fingerprint"):
        WorkspaceAdapter(loaded, invoker=mutating, clock=_Clock()).refusal(
            next(s for s in plan(loaded).steps if s.seq == 12), "validation-failed"
        )


def test_wsa_2_collector_over_mutated_state_fails_the_refusal(tmp_path: Path) -> None:
    loaded = _extended(tmp_path, retry_seq=None)
    ticks = _Ticks()
    mutating = _MutatingRefuser(ticks, {12})
    adapter = WorkspaceAdapter(loaded, invoker=mutating, clock=_Clock(), fingerprint=ticks)
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == FAILED_STEP and "STATE CHANGED" in (refusal.reason or "")


def test_gaps_unit_price_string_manual_routing_rule_per_call_and_actual_values() -> None:
    """EX42's unit_price 25 stays a decimal string; the event body carries no is_manual member
    (manual events route through approval); each mapping-rule call carries its one rule;
    estimate calls carry their actual values. POS-CHK-012 declares two policy overrides and the
    adapter builds no call of the product's override commands (register index 308; until that
    item each override call carried the key's value and rationale)."""
    ex42 = load_platform_key(EX42)
    expedient = next(
        c for c in ex42.key.contracts if any(line.unit_price is not None for line in c.lines)
    )
    body = booking_body(expedient)
    priced = next(line for line in body["lines"] if "unit_price" in line)
    assert isinstance(priced["unit_price"], str) and priced["unit_price"] == "25"
    pos = load_platform_key(POS_012)
    invoker = RecordingInvoker()
    adapter = WorkspaceAdapter(pos, invoker=invoker, clock=_Clock(), fingerprint=_Ticks())
    for step in plan(pos).steps:
        if step.phase in ("CHECKPOINT", "RUNNER") or step.gap is not None:
            continue
        adapter.run(step)
    events = [c for c in invoker.calls if c.handler == H["record_events"]]
    assert events and all("is_manual" not in c.kwargs["events"][0] for c in events)
    assert all("route" in c.kwargs for c in events)
    rules = [c for c in invoker.calls if c.handler == H["mapping_rule"]]
    assert len(rules) == len(pos.key.world.account_mapping)
    assert [c.kwargs["rule"] for c in rules] == [
        row.model_dump(exclude_none=True) for row in pos.key.world.account_mapping
    ]
    declared = [o for c in pos.key.contracts for o in c.policy_overrides or ()]
    assert len(declared) == 2
    calls = [c for c in invoker.calls if c.handler == H["override"]]
    assert len(calls) == len(declared)
    assert [c.kwargs["value"] for c in calls] == [o.value for o in declared]
    assert [c.kwargs["rationale"] for c in calls] == [o.rationale for o in declared]
    ex42_adapter = WorkspaceAdapter(
        ex42, invoker=RecordingInvoker(), clock=_Clock(), fingerprint=_Ticks()
    )
    estimates = [
        ex42_adapter.plan_call(step) for step in plan(ex42).steps if step.handler == H["estimate"]
    ]
    assert estimates
    for call in estimates:
        assert call is not None
        assert {"contract", "element_code", "estimate_kind", "method", "versions"} <= set(
            call.kwargs
        )


def test_ledger_keeps_results_versions_principal_and_clocks() -> None:
    """Every successful invocation is kept: handler, actor (principal), application clock, server
    clock and the result; timeline items keep known_at; refused calls leave no ledger entry."""
    loaded = load_platform_key(POS_012)

    class _Ids:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self, call: Call) -> object:
            self.n += 1
            return {"id": f"id-{self.n}", "handler": call.handler}

    invoker = _Ids()
    adapter = WorkspaceAdapter(loaded, invoker=invoker, clock=_Clock(), fingerprint=_Ticks())
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    assert len(adapter.ledger) == invoker.n
    entry = adapter.ledger[-1]
    assert entry.result == {"id": f"id-{invoker.n}", "handler": entry.call.handler}
    assert entry.actor == entry.call.actor and entry.server_at is not None
    stamped = [entry for entry in adapter.ledger if entry.known_at is not None]
    assert {entry.call.step.seq for entry in stamped} == set(result.known_at)
    # Each item keeps the stamp of the last step that stamped it: its own, or — item 9 — the
    # close run the plan runs after it (dev-guide rev 1.246, ruling (a) of 2026-10-01).
    last = {entry.call.step.seq: entry.known_at for entry in stamped}
    assert last == dict(result.known_at)
    twice = [entry for entry in stamped if entry.call.step.seq == 9]
    assert [entry.call.step.phase for entry in twice] == ["TIMELINE", "CLOSE"]
    assert twice[0].known_at is not None and twice[1].known_at is not None
    assert twice[0].known_at < twice[1].known_at == result.known_at[9]
    assert len(stamped) == len(result.known_at) + 1  # no other item is stamped twice
    # booking 1, the runner's Step 1 assessment of the one enabled book (layer 4), then one per
    # key item after the booking — the approved activation among them
    assert adapter.stream[loaded.key.contracts[0].external_id] == 2 + sum(
        1
        for item in loaded.key.timeline
        if item.contract == loaded.key.contracts[0].external_id
        and item.event_type != "CONTRACT_BOOKED"
    )
