"""CPU guards of the SBX-04 governed restoration of finalized approval graphs (Codex
production-20260921-1713 §3 R3; D-98 137 amendment 4): the registry's ``FINALIZATIONS`` name real
columns and statuses of the DB-03 registry, and ``hold_finalization`` inserts a finalized row in
its initial status with the held set-once columns NULL while every other row passes unchanged.
The DB witness is ``tests/domain/platform/test_sandbox_replay.py`` (written NOT RUN)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from erev_api.db.tables import metadata
from erev_api.db.transitions import TRANSITIONS
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd

AT = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)


def test_finalizations_name_real_columns_and_kernel_pairs() -> None:
    """Every rule's status column, held columns and ``when`` column exist on its table; every
    ``initial → final`` pair is a DB-03 pair of the kernel registry, the held columns are
    updatable there, and the ``after`` dataset loads after the table in LOAD_ORDER."""
    order = list(sd.LOAD_ORDER)
    for name, rule in sd.FINALIZATIONS.items():
        columns = {c.name for c in metadata.tables[f"erev.{name}"].columns}
        assert rule.status_column in columns and set(rule.held) <= columns, name
        assert rule.when is None or rule.when in columns, name
        if rule.kernel:
            kernel = TRANSITIONS[name]
            assert kernel.status_column == rule.status_column
            for final in rule.final:
                assert (rule.initial, final) in kernel.pairs, (name, rule.initial, final)
            assert set(rule.held) <= set(kernel.updatable_columns), name
        else:  # MEMBERSHIP-1: an SC-M status the DB-03 registry does not govern
            assert name not in TRANSITIONS, name
            assert name == "tenant_membership"
            assert rule.initial == "ACTIVE" and rule.final == {"SUSPENDED", "REMOVED"}
        assert order.index(rule.after) > order.index(name), (name, rule.after)
    assert set(sd.FINALIZATION_ORDER) == set(sd.FINALIZATIONS)
    assert sd.FINALIZATION_ORDER.index("approval_step") < sd.FINALIZATION_ORDER.index(
        "approval_request"
    )  # steps finalize before their request
    assert sd.FINALIZATION_ORDER[-1] == "tenant_membership"  # memberships after every graph


def test_hold_finalization_inserts_initial_status_and_holds_set_once_columns() -> None:
    request_id = uuid4()
    approved = {
        "id": request_id,
        "status": "APPROVED",
        "decided_at": AT,
        "voided_at": None,
        "void_reason": None,
        "current_step_no": 1,
        "comment": "January close complete",
    }
    inserted, held = sb.hold_finalization("approval_request", approved)
    assert inserted["status"] == "PENDING" and inserted["decided_at"] is None
    assert inserted["current_step_no"] == 1 and inserted["comment"] == approved["comment"]
    assert held is not None
    assert (held.table, held.row_id, held.final_status) == (
        "approval_request",
        request_id,
        "APPROVED",
    )
    assert dict(held.set_values) == {"decided_at": AT}  # only what the source set
    voided = {
        **approved,
        "status": "VOIDED",
        "decided_at": None,
        "voided_at": AT,
        "void_reason": "x",
    }
    inserted, held = sb.hold_finalization("approval_request", voided)
    assert inserted["status"] == "PENDING" and inserted["voided_at"] is None
    assert held is not None and held.final_status == "VOIDED"
    assert dict(held.set_values) == {"voided_at": AT, "void_reason": "x"}
    pending = {**approved, "status": "PENDING", "decided_at": None}
    assert sb.hold_finalization("approval_request", pending) == (pending, None)


def test_hold_finalization_steps_only_when_they_were_active() -> None:
    step_id = uuid4()
    approved = {"id": step_id, "status": "APPROVED", "activated_at": AT, "completed_at": AT}
    inserted, held = sb.hold_finalization("approval_step", approved)
    assert inserted == {"id": step_id, "status": "ACTIVE", "activated_at": AT, "completed_at": None}
    assert held is not None and held.final_status == "APPROVED"
    assert dict(held.set_values) == {"completed_at": AT}
    never_active = {"id": uuid4(), "status": "VOIDED", "activated_at": None, "completed_at": AT}
    assert sb.hold_finalization("approval_step", never_active) == (never_active, None)
    waiting = {"id": uuid4(), "status": "WAITING", "activated_at": None, "completed_at": None}
    assert sb.hold_finalization("approval_step", waiting) == (waiting, None)


def test_hold_finalization_holds_a_suspended_or_removed_membership() -> None:
    """MEMBERSHIP-1: a copied membership that ended SUSPENDED or REMOVED after being ACTIVE goes in
    ACTIVE (its ``removed_at`` held) so the approver's historical decisions pass the live 0013
    guard; an INVITED-then-REMOVED membership (never active) and an ACTIVE one are untouched; the
    INSERT carries the exported stamps (``updated_*``, ``row_version``) — the finalization UPDATE
    then receives the sandbox's own DB-02 stamps (STAMPS-1), asserted by the DB witness."""
    suspended = {
        "id": uuid4(),
        "status": "SUSPENDED",
        "activated_at": AT,
        "removed_at": None,
        "updated_at": AT + timedelta(days=2),
        "row_version": 3,
    }
    inserted, held = sb.hold_finalization("tenant_membership", suspended)
    assert inserted["status"] == "ACTIVE" and inserted["row_version"] == 3
    assert inserted["updated_at"] == AT + timedelta(days=2)
    assert held is not None and held.final_status == "SUSPENDED" and dict(held.set_values) == {}
    removed = {**suspended, "status": "REMOVED", "removed_at": AT + timedelta(days=2)}
    inserted, held = sb.hold_finalization("tenant_membership", removed)
    assert inserted["status"] == "ACTIVE" and inserted["removed_at"] is None
    assert held is not None and held.final_status == "REMOVED"
    assert dict(held.set_values) == {"removed_at": AT + timedelta(days=2)}
    never_active = {**removed, "activated_at": None}
    assert sb.hold_finalization("tenant_membership", never_active) == (never_active, None)
    active = {**suspended, "status": "ACTIVE"}
    assert sb.hold_finalization("tenant_membership", active) == (active, None)
    assert sd.FINALIZATIONS["tenant_membership"].kernel is False


def test_hold_finalization_leaves_other_tables_alone() -> None:
    row = {"id": uuid4(), "status": "APPLIED", "decided_at": AT}
    assert sb.hold_finalization("combination_group", row) == (row, None)


def test_graphs_name_real_columns_and_load_order() -> None:
    """Every graph's root and dependants are LOAD_ORDER datasets, the dependants after the root,
    naming the root through a real column; every KERNEL finalization belongs to a graph (a
    finalized row is restored with its whole graph, never table by table) and the membership
    finalization waits for a graph dataset."""
    order = list(sd.LOAD_ORDER)
    graph_tables: set[str] = set()
    for root, graph in sd.GRAPHS.items():
        assert graph.root == root and root in order
        root_columns = {c.name for c in metadata.tables[f"erev.{root}"].columns}
        assert set(graph.order) <= root_columns
        graph_tables.add(root)
        for name, column in graph.dependants:
            columns = {c.name for c in metadata.tables[f"erev.{name}"].columns}
            assert column in columns and set(graph.dependant_order[name]) <= columns, name
            assert order.index(name) > order.index(root), (root, name)
            graph_tables.add(name)
    # a KERNEL finalization is restored with its whole graph; the non-kernel membership finalization
    # waits for the graphs' last dataset instead (MEMBERSHIP-1)
    assert {n for n, r in sd.FINALIZATIONS.items() if r.kernel} <= graph_tables
    assert all(r.after in graph_tables for r in sd.FINALIZATIONS.values() if not r.kernel)


def _request(subject: object, submitted: datetime, status: str = "APPROVED") -> dict:
    return {
        "id": uuid4(),
        "subject_type": "PERIOD_LOCK",
        "subject_id": subject,
        "status": status,
        "submitted_at": submitted,
        "decided_at": None if status == "PENDING" else submitted + timedelta(minutes=10),
    }


def test_graph_batches_restore_one_subject_s_requests_in_submission_order() -> None:
    """APPROVAL-UNIQUE-1: the lock, the re-lock and a current PENDING request of ONE period state
    come out in ``submitted_at`` order — each graph with its own steps (by step_no) and decisions
    (by decided_at) — so no two are PENDING together when each finalizes before the next inserts;
    a decision naming an unknown request is an inconsistent export."""
    graph = sd.GRAPHS["approval_request"]
    subject = uuid4()
    relock = _request(subject, AT + timedelta(hours=2))
    lock = _request(subject, AT)
    pending = _request(subject, AT + timedelta(hours=4), status="PENDING")
    other = _request(uuid4(), AT + timedelta(hours=1))
    # the explicit partition (Codex 1757 §2): a current PENDING root submitted EARLIER than a
    # finalized one still comes last; equal submitted_at values fall back to the id
    early_pending = _request(uuid4(), AT - timedelta(hours=1), status="PENDING")
    tie_a, tie_b = (
        _request(uuid4(), AT + timedelta(hours=3)),
        _request(uuid4(), AT + timedelta(hours=3)),
    )
    partitioned = sb.graph_batches(
        graph,
        [early_pending, tie_b, tie_a, lock],
        {"approval_step": [], "approval_decision": []},
    )
    assert [b.root["id"] for b in partitioned] == [
        lock["id"],
        *sorted((tie_a["id"], tie_b["id"]), key=str),
        early_pending["id"],
    ]
    steps = [
        {"id": uuid4(), "approval_request_id": r["id"], "step_no": 1}
        for r in (relock, lock, pending, other)
    ]
    later, earlier = (
        {"id": uuid4(), "approval_request_id": lock["id"], "decided_at": AT + timedelta(minutes=9)},
        {"id": uuid4(), "approval_request_id": lock["id"], "decided_at": AT + timedelta(minutes=3)},
    )
    batches = sb.graph_batches(
        graph,
        [relock, lock, pending, other],
        {"approval_step": steps, "approval_decision": [later, earlier]},
    )
    assert [b.root["id"] for b in batches] == [lock["id"], other["id"], relock["id"], pending["id"]]
    assert [d["id"] for d in batches[0].dependants["approval_decision"]] == [
        earlier["id"],
        later["id"],
    ]
    assert [s["id"] for s in batches[0].dependants["approval_step"]] == [steps[1]["id"]]
    assert batches[-1].dependants["approval_decision"] == ()  # the current PENDING request, last
    orphan = {"id": uuid4(), "approval_request_id": uuid4(), "decided_at": AT}
    with pytest.raises(ValueError, match="names no approval_request"):
        sb.graph_batches(graph, [lock], {"approval_step": [], "approval_decision": [orphan]})
