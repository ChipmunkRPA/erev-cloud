"""CPU guards of the SNP-2 period replay executor's pure seams (D-98 candidate 137 amendment 3;
Codex production-20260921-1623 §1 REPLAY-2 / LOCK-3): the REAL export serialization round trip
into the typed planner, the lock pairing, the plan-time end-state check and the refusal
classification. The governed execution itself is DB-bound (``tests/domain/platform/
test_sandbox_replay.py``, written NOT RUN on the lane)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from erev_api.domain.platform import sandbox_periods as sp
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_replay as replay
from erev_api.enums import LockKind, PeriodState
from erev_api.problems import Problem, ProblemError

SOURCE = UUID(int=0x51)
SANDBOX = UUID(int=0x52)
T0 = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
_STAMP = {"created_by": None, "created_by_kind": "SYSTEM"}


def _transition(
    state: dict[str, Any],
    pair: tuple[str | None, str],
    at: datetime,
    *,
    approval_request_id: UUID | None = None,
    period_lock_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        "tenant_id": SOURCE,
        "id": uuid4(),
        "period_state_id": state["id"],
        "entity_id": state["entity_id"],
        "book_code": state["book_code"],
        "period_id": state["period_id"],
        "from_state": pair[0],
        "to_state": pair[1],
        "reason_code": None,
        "comment": f"{pair[0]} → {pair[1]}",
        "approval_request_id": approval_request_id,
        "period_lock_id": period_lock_id,
        "close_run_id": None,
        "created_txid": 1000,
        "created_at": at,
        **_STAMP,
    }


def _source_chain() -> dict[str, list[dict[str, Any]]]:
    """One period state closed by a LOCK: NULL → future → open → closing → closed, the lock on the
    last transition, the state row naming the lock as current — a consistent export."""
    state = {
        "tenant_id": SOURCE,
        "id": uuid4(),
        "entity_id": uuid4(),
        "book_code": "ASC606",
        "period_id": uuid4(),
        "period_end_date": date(2026, 1, 31),
        "state": "closed",
        "current_lock_id": None,
        "state_changed_at": T0 + timedelta(hours=1),
        "updated_at": T0 + timedelta(hours=1),
        "updated_by": None,
        "updated_by_kind": "SYSTEM",
        "row_version": 5,
    }
    lock_id, request_id = uuid4(), uuid4()
    transitions = [
        _transition(state, (None, "future"), T0 - timedelta(days=40)),
        _transition(state, ("future", "open"), T0 - timedelta(days=39)),
        _transition(state, ("open", "closing"), T0),
        _transition(
            state,
            ("closing", "closed"),
            T0 + timedelta(hours=1),
            approval_request_id=request_id,
            period_lock_id=lock_id,
        ),
    ]
    lock = {
        "tenant_id": SOURCE,
        "id": lock_id,
        "kind": "LOCK",
        "entity_id": state["entity_id"],
        "book_code": "ASC606",
        "period_id": state["period_id"],
        "period_state_transition_id": transitions[-1]["id"],
        "approval_request_id": request_id,
        "reason_code": None,
        "comment": "January close",
        "certification": [],
        "ledger_head_chain_seq": 0,
        "ledger_head_sha256": None,
        "audit_head_chain_seq": 0,
        "audit_head_hmac": None,
        "snapshot_manifest_sha256": None,
        "previous_lock_id": None,
        "diff_report_file_id": None,
        "created_at": T0 + timedelta(hours=1),
        **_STAMP,
    }
    state["current_lock_id"] = lock_id
    return {"period_state": [state], "period_state_transition": transitions, "period_lock": [lock]}


def _exported(chain: dict[str, list[dict[str, Any]]]) -> dict[str, tuple[Any, ...]]:
    """The chain through the REAL export path: canonical JSONL bytes, then ``decode_rows``."""
    inventory = sd.inventory()
    return {
        name: sd.decode_rows(sd.encode_rows(inventory.dataset(name), rows).content)
        for name, rows in chain.items()
    }


def test_exported_references_reach_the_planner_only_when_typed() -> None:
    """REPLAY-2 fail-first and fix: the decoded JSONL carries strings, which the planner refuses;
    ``typed_references`` decodes the three populations by their schema and re-stamps the tenant,
    and ``prepare`` then plans, checks the end state and pairs the lock with its transition."""
    chain = _source_chain()
    decoded = _exported(chain)
    assert isinstance(decoded["period_state"][0]["id"], str)  # JSON-native, as exported
    with pytest.raises(ValueError, match="UUID is required"):
        replay.replay_plan(
            decoded["period_state"], decoded["period_state_transition"], decoded["period_lock"]
        )
    typed = sb.typed_references(decoded, tenant_id=SANDBOX)
    assert set(typed) == set(sp.REFERENCE_DATASETS)
    assert all(row["tenant_id"] == SANDBOX for rows in typed.values() for row in rows)
    assert isinstance(typed["period_state_transition"][0]["created_at"], datetime)
    assert typed["period_state_transition"][0]["created_at"].tzinfo is not None
    assert typed["period_state"][0]["period_end_date"] == date(2026, 1, 31)
    prepared = sp.prepare(typed)
    assert [step.kind for step in prepared.plan] == ["transition"] * 4 + ["lock"]
    assert [p.step.to_state for p in prepared.paired] == [
        PeriodState.FUTURE,
        PeriodState.OPEN,
        PeriodState.CLOSING,
        PeriodState.CLOSED,
    ]
    assert [p.lock is not None for p in prepared.paired] == [False, False, False, True]
    last = prepared.paired[-1]
    assert last.lock is not None and last.lock.lock_kind is LockKind.LOCK
    assert last.lock.id == chain["period_lock"][0]["id"]
    assert last.lock.transition_id == last.step.id == chain["period_state_transition"][-1]["id"]
    assert set(prepared.locks) == {chain["period_lock"][0]["id"]}
    assert len(prepared.transitions) == 4


def test_prepare_refuses_an_end_state_the_transitions_do_not_reach() -> None:
    """The exported state says ``closed`` with a lock, but the transitions stop at ``open``: the
    plan is refused by name before any write (``verify_end_state``)."""
    chain = _source_chain()
    chain["period_state_transition"] = chain["period_state_transition"][:2]
    chain["period_lock"] = []
    typed = sb.typed_references(_exported(chain), tenant_id=SANDBOX)
    with pytest.raises(ValueError, match="do not reproduce the exported period states"):
        sp.prepare(typed)


def _step(kind: str, **values: Any) -> replay.ReplayStep:
    base: dict[str, Any] = {
        "kind": kind,
        "at": T0,
        "id": uuid4(),
        "period_state_id": uuid4(),
        "entity_id": uuid4(),
        "book_code": "ASC606",
        "period_id": uuid4(),
        "from_state": None,
        "to_state": None,
        "reason_code": None,
        "approval_request_id": None,
        "lock_kind": None,
        "transition_id": None,
        "previous_lock_id": None,
    }
    return replay.ReplayStep(**{**base, **values})


def test_pair_steps_names_a_missing_or_orphan_lock() -> None:
    closing = _step("transition", from_state=PeriodState.OPEN, to_state=PeriodState.CLOSING)
    closed = _step("transition", from_state=PeriodState.CLOSING, to_state=PeriodState.CLOSED)
    lock = _step("lock", lock_kind=LockKind.LOCK, transition_id=closed.id)
    paired = sp.pair_steps([closing, closed, lock])
    assert [(p.step.id, None if p.lock is None else p.lock.id) for p in paired] == [
        (closing.id, None),
        (closed.id, lock.id),
    ]
    with pytest.raises(ValueError, match="without its period_lock row"):
        sp.pair_steps([closing, closed])
    with pytest.raises(ValueError, match="without its transition"):
        sp.pair_steps([lock, closing])
    reopen = _step("lock", lock_kind=LockKind.REOPEN, transition_id=closed.id)
    with pytest.raises(ValueError, match="without its period_lock row"):
        sp.pair_steps([closed, reopen])  # a REOPEN does not fit a transition to closed


def test_the_end_of_a_soft_close_under_reopen_is_paired_with_no_lock() -> None:
    """04 T-REF-07 rev 1.170: ``closing → reopened`` — the end of a soft close of a period that
    had been locked before — reaches a state the lock kinds target and writes no ``period_lock``
    row; the period stays under its ``REOPEN`` record. The pairing asks no lock after it.

    Fail-first (the pairing as item CLO-CANCEL-CLOSE-REOPENED-1 left it; found by the database
    witness of item REOPEN-CLOSING-FLAG-1): ``pair_steps`` raised "a transition to reopened
    without its period_lock row", so ``prepare`` refused every history that holds the pair and
    the loader answered not-loadable."""
    reopened = _step("transition", from_state=PeriodState.CLOSED, to_state=PeriodState.REOPENED)
    reopen = _step("lock", lock_kind=LockKind.REOPEN, transition_id=reopened.id)
    closing = _step("transition", from_state=PeriodState.REOPENED, to_state=PeriodState.CLOSING)
    ended = _step("transition", from_state=PeriodState.CLOSING, to_state=PeriodState.REOPENED)
    paired = sp.pair_steps([reopened, reopen, closing, ended])
    assert [(p.step.id, None if p.lock is None else p.lock.id) for p in paired] == [
        (reopened.id, reopen.id),
        (closing.id, None),
        (ended.id, None),
    ]
    # closed → reopened keeps asking for its REOPEN row …
    with pytest.raises(ValueError, match="without its period_lock row"):
        sp.pair_steps([reopened, closing, ended])
    # … and a lock step behind the pair has no transition to belong to
    stray = _step("lock", lock_kind=LockKind.REOPEN, transition_id=ended.id)
    with pytest.raises(ValueError, match="without its transition"):
        sp.pair_steps([closing, ended, stray])


def test_prepare_accepts_an_exported_history_that_ends_a_soft_close_under_reopen() -> None:
    """The same through the REAL export round trip and ``prepare``: the chain of ``_source_chain``
    goes on — reopened (its ``REOPEN`` row), soft-closed again, the soft close ended — and the
    exported state is ``reopened`` under the ``REOPEN``. The plan reproduces that end state and
    its last step carries the cancel reason and no lock."""
    chain = _source_chain()
    (state,) = chain["period_state"]
    (lock,) = chain["period_lock"]
    reopen_id, request_id = uuid4(), uuid4()
    reopened = {
        **_transition(
            state,
            ("closed", "reopened"),
            T0 + timedelta(hours=2),
            approval_request_id=request_id,
            period_lock_id=reopen_id,
        ),
        "reason_code": "ERROR_CORRECTION",
    }
    closing = _transition(state, ("reopened", "closing"), T0 + timedelta(hours=3))
    ended = {
        **_transition(state, ("closing", "reopened"), T0 + timedelta(hours=4)),
        "reason_code": "CLOSE_RESTARTED",
    }
    chain["period_state_transition"] += [reopened, closing, ended]
    chain["period_lock"].append(
        {
            **lock,
            "id": reopen_id,
            "kind": "REOPEN",
            "period_state_transition_id": reopened["id"],
            "approval_request_id": request_id,
            "reason_code": "ERROR_CORRECTION",
            "comment": "January reopened",
            "previous_lock_id": lock["id"],
            "created_at": T0 + timedelta(hours=2),
        }
    )
    state.update(state="reopened", current_lock_id=reopen_id)
    prepared = sp.prepare(sb.typed_references(_exported(chain), tenant_id=SANDBOX))
    assert [(p.step.to_state, p.lock is not None) for p in prepared.paired[-3:]] == [
        (PeriodState.REOPENED, True),
        (PeriodState.CLOSING, False),
        (PeriodState.REOPENED, False),
    ]
    last = prepared.paired[-1].step
    assert (last.id, last.from_state, last.reason_code) == (
        ended["id"],
        PeriodState.CLOSING,
        "CLOSE_RESTARTED",
    )
    assert set(prepared.locks) == {lock["id"], reopen_id}


class _Orig(Exception):
    def __init__(self, sqlstate: str, message: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def test_blocked_reason_classifies_normal_refusals_only() -> None:
    """A ``Problem`` and the database's own named guard are business refusals (a blocked period);
    a foreign-key violation, a KeyError or a ValueError are defects and are never disguised."""
    gates_failed = Problem(
        "close-gates-failed",
        "2 gates failed: JE complete, exceptions cleared.",
        errors=[
            ProblemError(rule_id="JE_COMPLETE", message="not evaluated"),
            ProblemError(rule_id="EXCEPTIONS_CLEARED", message="Open exceptions: 1"),
        ],
    )
    reason = sp.blocked_reason(gates_failed)
    assert reason is not None
    assert reason.startswith("close-gates-failed [EXCEPTIONS_CLEARED, JE_COMPLETE]: 2 gates failed")
    plain = sp.blocked_reason(Problem("not-found"))
    assert plain is not None and plain.startswith("not-found: ")
    guard = sa.exc.DBAPIError(
        "UPDATE erev.period_state",
        {},
        _Orig(
            "P0001",
            "EREV-PER-001: erev.period_state row x moved from closing to closed "
            "without a transition",
        ),
    )
    assert sp.blocked_reason(guard) is not None
    assert sp.blocked_reason(guard).startswith("EREV-PER-001: ")
    foreign_key = sa.exc.DBAPIError("INSERT", {}, _Orig("23503", "violates foreign key constraint"))
    assert sp.blocked_reason(foreign_key) is None
    assert sp.blocked_reason(KeyError("period_state")) is None
    assert sp.blocked_reason(ValueError("a UUID is required")) is None
    assert sp.blocked_reason(RuntimeError("previous_lock_id differs")) is None


def test_blocked_period_is_shared_with_the_loader() -> None:
    """One dataclass for the loader's report and the executor's result (no drift between them)."""
    assert sb.BlockedPeriod is sp.BlockedPeriod is replay.BlockedPeriod
    blocked = sp.BlockedPeriod(
        uuid4(), uuid4(), "ASC606", uuid4(), "closing → closed", "closing", "x"
    )
    assert blocked.reached == "closing" and blocked.attempted == "closing → closed"


def test_open_phase_selects_creation_and_opening_steps_only() -> None:
    """05 SBX-04 order (Codex 1713 §3 R1): the OPEN phase replays the creation transitions and
    every ``future → open``; closing, cancel and lock-bearing steps wait for the recompute."""
    creation = _step("transition", from_state=None, to_state=PeriodState.FUTURE)
    opening = _step("transition", from_state=PeriodState.FUTURE, to_state=PeriodState.OPEN)
    closing = _step("transition", from_state=PeriodState.OPEN, to_state=PeriodState.CLOSING)
    cancel = _step("transition", from_state=PeriodState.CLOSING, to_state=PeriodState.OPEN)
    closed = _step("transition", from_state=PeriodState.CLOSING, to_state=PeriodState.CLOSED)
    lock = _step("lock", lock_kind=LockKind.LOCK, transition_id=closed.id)
    paired = sp.pair_steps([creation, opening, closing, cancel, closed, lock])
    assert [sp.open_step(p) for p in paired] == [True, True, False, False, False]


# --- the replayed lock freezes as the product's lock does (R-19, R-42 (e), R-43 (d)) --------------


def _calls(function: Any) -> list[tuple[str, Any]]:
    """The dotted names a function calls, in source order, with the call node of each."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    found: list[tuple[int, int, str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts: list[str] = []
        target: Any = node.func
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
            found.append((node.lineno, node.col_offset, ".".join(reversed(parts)), node))
    return [(name, node) for _, _, name, node in sorted(found, key=lambda item: item[:2])]


@pytest.mark.parametrize(
    ("owner", "function", "persist"),
    [
        ("erev_api.domain.close.commands", "_period_lock_approved", "_persist_lock"),
        ("erev_api.domain.platform.sandbox_periods", "_lock", "close._persist_lock"),
    ],
)
def test_the_replayed_lock_freezes_as_the_product_lock_does(
    owner: str, function: str, persist: str
) -> None:
    """ENGINE_SPEC_B S15-R-18c (supervisor rulings R-19, R-42 (e), R-43 (d)). The sandbox cannot
    reach a lock today (SNP-2b), so the shape is read from the source of both functions, the
    product's and the replay's: the cutoff is ``freeze.freeze_cutoff`` — once; the datasets are
    frozen AT it, passed as ``known_at`` and as ``frozen_at``; ``freeze.assert_covered`` is asked
    twice with that cutoff, after the freeze and before the lock row, and again after it; and
    the application clock alone is never the cutoff of a freeze.

    Since the rework of the product's lock on main (supervisor ruling R-42 (d); 04 T-CLS-04 rev
    1.113) the period's activity is read before the freeze and the coverage is asked under the
    tenant's SYSTEM scope — ``freeze.activity_before_freeze`` and ``freeze.assert_covered`` take
    the tenant id, not the decision's session — and the lock row records the cutoff as
    ``cutoff_known_at``. The replay follows each of them."""
    import ast
    import importlib

    calls = _calls(getattr(importlib.import_module(owner), function))
    names = [name for name, _ in calls]
    assert names.count("freeze.freeze_cutoff") == 1, names
    assert names.count("snapshots.freeze_datasets") == 1
    assert names.count("freeze.assert_covered") == 2
    assert names.count(persist) >= 1
    cut, frozen = names.index("freeze.freeze_cutoff"), names.index("snapshots.freeze_datasets")
    first = names.index("freeze.assert_covered")
    last = len(names) - 1 - names[::-1].index("freeze.assert_covered")
    before = names.index("freeze.activity_before_freeze")
    assert cut < before < frozen < first < names.index(persist) < last
    freeze_call = calls[frozen][1]
    assert isinstance(freeze_call.args[4], ast.Name) and freeze_call.args[4].id == "cutoff"
    keywords = {keyword.arg: keyword.value for keyword in freeze_call.keywords}
    assert isinstance(keywords["frozen_at"], ast.Name) and keywords["frozen_at"].id == "cutoff"
    for index in (before, first, last):
        tenant = calls[index][1].args[0]
        assert isinstance(tenant, ast.Attribute) and tenant.attr == "tenant_id"
    for index in (first, last):
        covered = calls[index][1]
        assert [arg.id for arg in covered.args if isinstance(arg, ast.Name)] == [
            "scope",
            "cutoff",
            "at_freeze",
        ]
    # 04 T-CLS-04 rev 1.113: the lock row records the instant its datasets were frozen at.
    stored = {keyword.arg: keyword.value for keyword in calls[names.index(persist)][1].keywords}
    recorded = stored["cutoff_known_at"]
    assert isinstance(recorded, ast.Name) and recorded.id == "cutoff"


def test_a_freeze_refusal_in_the_replay_is_a_blocked_period_not_a_defect() -> None:
    """The three refusals of the freeze are ``Problem``s, the class the replay records as a
    blocked period (05 SBX-04): the rule id is named and nothing is locked."""
    from erev_api.domain.close import freeze, gates

    scope = gates.PeriodScope(
        state_id=uuid4(),
        entity_id=uuid4(),
        entity_code="AVM-US",
        functional_currency="USD",
        book_code="ASC606",
        period_id=uuid4(),
        period_key="FY2026-P01",
        period_name="January 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        state="closing",
        current_lock_id=None,
        row_version=3,
    )
    for refused, rule in (
        (freeze.dataset_refused(scope, "CONTRACT_BALANCES", "no builder"), freeze.RULE_FREEZE),
        (freeze.artefact_refused(scope, "digest differs"), freeze.RULE_FREEZE),
        (
            freeze.not_covered(scope, ("2 subledger line(s) after the cutoff",)),
            freeze.RULE_COVERAGE,
        ),
    ):
        reason = sp.blocked_reason(refused)
        assert reason is not None and reason.startswith(f"invalid-transition [{rule}]: ")
        assert "FY2026-P01 of AVM-US in book ASC606 is not locked" in reason
    assert sp.blocked_reason(KeyError("a defect")) is None
