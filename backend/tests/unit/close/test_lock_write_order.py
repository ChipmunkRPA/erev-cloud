"""D-98 61 (Codex CLO-6 review R1): the lock writes are ordered so that every statement referencing
the new ``period_lock`` id follows the ``period_lock`` INSERT — 0047 defers only ``period_lock →
transition``; ``transition → lock`` and ``period_state.current_lock_id → lock`` are immediate keys.
Native emitted-order oracle over an inert statement-capturing session (no database): the index of
the ``period_lock`` INSERT precedes the ``period_state_transition`` INSERT and the ``period_state``
UPDATE, for the permanent lock and for the shared persist step the ordinary lock uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from erev_api.domain.close import commands, gates
from erev_api.enums import ChecklistStatus, LockKind, PeriodState
from sqlalchemy.sql.dml import Insert, Update

NOW = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
TENANT = UUID("00000000-0000-0000-0000-00000000aa01")
STATE = UUID("00000000-0000-0000-0000-00000000cc01")
ENTITY = UUID("00000000-0000-0000-0000-0000000000e1")
PERIOD = UUID("00000000-0000-0000-0000-000000000f09")
REQUEST = UUID("00000000-0000-0000-0000-00000000dd01")
APPROVER = UUID("00000000-0000-0000-0000-0000000000a2")
CUTOFF = datetime(2026, 10, 5, 14, 30, 2, tzinfo=UTC)  # the server clock, two seconds ahead of NOW
HEADS = {
    "ledger_head_chain_seq": 0,
    "ledger_head_sha256": None,
    "audit_head_chain_seq": 0,
    "audit_head_hmac": None,
}


class _Result:
    def one_or_none(self) -> None:
        return None

    def scalar_one_or_none(self) -> None:
        return None

    def mappings(self) -> _Result:
        return self

    def first(self) -> None:
        return None


@dataclass
class _Session:
    """Captures every statement in emission order; reads answer empty."""

    statements: list[Any] = field(default_factory=list)

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.statements.append(statement)
        return _Result()


@dataclass
class _Uow:
    session: _Session
    now: datetime = NOW
    principal: Any = field(
        default_factory=lambda: SimpleNamespace(
            tenant_id=TENANT, id=APPROVER, kind=SimpleNamespace(value="USER")
        )
    )
    audits: list[dict[str, Any]] = field(default_factory=list)

    def audit(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)


def _scope(state: PeriodState) -> gates.PeriodScope:
    return gates.PeriodScope(
        state_id=STATE,
        entity_id=ENTITY,
        entity_code="AVM-US",
        functional_currency="USD",
        book_code="ASC606",
        period_id=PERIOD,
        period_key="FY2026-P09",
        period_name="September 2026",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        state=state.value,
        current_lock_id=None,
        row_version=4,
    )


def _all_passed() -> tuple[gates.GateResult, ...]:
    return tuple(
        gates.GateResult(code, ChecklistStatus.PASSED, 0, None, NOW)
        for code in gates.GATE_CHECK_CODES
    )


def _writes(session: _Session) -> list[tuple[str, str]]:
    kinds: list[tuple[str, str]] = []
    for statement in session.statements:
        if isinstance(statement, Insert):
            kinds.append(("INSERT", statement.table.name))
        elif isinstance(statement, Update):
            kinds.append(("UPDATE", statement.table.name))
    return kinds


def _assert_lock_first(writes: list[tuple[str, str]]) -> None:
    lock = writes.index(("INSERT", "period_lock"))
    transition = writes.index(("INSERT", "period_state_transition"))
    state = writes.index(("UPDATE", "period_state"))
    assert lock < transition, writes  # the transition row names the lock (immediate FK)
    assert lock < state, writes  # current_lock_id names the lock (immediate FK)
    assert transition < state, writes  # DB-07: the transition row precedes the state change


def test_permanent_lock_inserts_the_lock_before_its_references() -> None:
    uow = _Uow(_Session())
    commands._execute_permanent_lock(
        uow,  # type: ignore[arg-type]
        _scope(PeriodState.CLOSED),
        _all_passed(),
        REQUEST,
        "Audit complete; freeze September 2026",
    )
    writes = _writes(uow.session)
    _assert_lock_first(writes)
    assert writes.count(("INSERT", "period_lock")) == 1
    actions = [a["action"] for a in uow.audits]
    assert actions == [commands.PERMANENT_LOCK_ACTION, commands.PERMANENT_LOCK_ACTION]


def test_persist_lock_step_shared_by_both_kinds_orders_the_writes() -> None:
    uow = _Uow(_Session())
    lock_id, transition_id = UUID(int=11), UUID(int=12)
    commands._persist_lock(
        uow,  # type: ignore[arg-type]
        _scope(PeriodState.CLOSING),
        kind=LockKind.LOCK,
        lock_id=lock_id,
        transition_id=transition_id,
        from_state=PeriodState.CLOSING,
        to_state=PeriodState.CLOSED,
        action=commands.LOCK_ACTION,
        approval_request_id=REQUEST,
        comment="September 2026 close complete",
        certification=[],
        snapshot_manifest_sha256="a" * 64,
        heads=HEADS,
        cutoff_known_at=CUTOFF,  # 04 T-CLS-04 rev 1.113: a LOCK row names its freeze cutoff
    )
    writes = _writes(uow.session)
    _assert_lock_first(writes)
    inserts = [s for s in uow.session.statements if isinstance(s, Insert)]
    lock_insert = next(s for s in inserts if s.table.name == "period_lock")
    transition_insert = next(s for s in inserts if s.table.name == "period_state_transition")
    lock_values = lock_insert.compile().params
    transition_values = transition_insert.compile().params
    assert (
        lock_values["id"] == lock_id and lock_values["period_state_transition_id"] == transition_id
    )
    assert (
        transition_values["id"] == transition_id and transition_values["period_lock_id"] == lock_id
    )
    # the cutoff is its own column; ``created_at`` stays the decision's application instant
    assert (lock_values["cutoff_known_at"], lock_values["created_at"]) == (CUTOFF, NOW)


def _persisted(kind: LockKind, cutoff: datetime | None) -> _Session:
    closed = kind is not LockKind.LOCK
    uow = _Uow(_Session())
    commands._persist_lock(
        uow,  # type: ignore[arg-type]
        _scope(PeriodState.CLOSED if closed else PeriodState.CLOSING),
        kind=kind,
        lock_id=UUID(int=21),
        transition_id=UUID(int=22),
        from_state=PeriodState.CLOSED if closed else PeriodState.CLOSING,
        to_state=PeriodState.REOPENED if kind is LockKind.REOPEN else PeriodState.CLOSED,
        action=commands.LOCK_ACTION,
        approval_request_id=REQUEST,
        comment="September 2026 close complete",
        certification=[],
        snapshot_manifest_sha256=None,
        heads=HEADS,
        cutoff_known_at=cutoff,
    )
    return uow.session


def test_a_lock_record_and_no_other_kind_names_its_freeze_cutoff() -> None:
    """Supervisor ruling R-40 (c) (04 T-CLS-04 ``cutoff_known_at``, ``ck_period_lock__
    cutoff_known_at``): the writer refuses a ``LOCK`` without its cutoff and a ``REOPEN`` or
    ``PERMANENT_LOCK`` with one before any statement — the database check states the same rule.
    Fail-first: the writer took no cutoff and the row had no such column."""
    for kind, cutoff in (
        (LockKind.LOCK, None),
        (LockKind.REOPEN, CUTOFF),
        (LockKind.PERMANENT_LOCK, CUTOFF),
    ):
        refused = _Uow(_Session())
        try:
            commands._persist_lock(
                refused,  # type: ignore[arg-type]
                _scope(PeriodState.CLOSING),
                kind=kind,
                lock_id=UUID(int=31),
                transition_id=UUID(int=32),
                from_state=PeriodState.CLOSING,
                to_state=PeriodState.CLOSED,
                action=commands.LOCK_ACTION,
                approval_request_id=REQUEST,
                comment="September 2026 close complete",
                certification=[],
                snapshot_manifest_sha256=None,
                heads=HEADS,
                cutoff_known_at=cutoff,
            )
        except ValueError as error:
            assert "names its freeze cutoff" in str(error), kind
        else:
            raise AssertionError(f"{kind} with cutoff {cutoff} was written")
        assert refused.session.statements == [], kind
    for kind in (LockKind.REOPEN, LockKind.PERMANENT_LOCK):
        inserted = next(
            s
            for s in _persisted(kind, None).statements
            if isinstance(s, Insert) and s.table.name == "period_lock"
        )
        assert inserted.compile().params["cutoff_known_at"] is None, kind
