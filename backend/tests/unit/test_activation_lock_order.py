"""Every unit of work that touches both the combination-group row and a contract row locks the
group row first (dev-guide DG-KRN-DB-08 rev 1.36; D-98 candidates 101a and 101b; lane P5 slices
P5-LOCK-R1 to R3). DB-free: a Session stand-in records the lock effect of every statement it is
handed — which table, ``FOR UPDATE`` or not — answers the three statements of
``erev_api.db.locking.lock_group_then_contract`` and stops the command right after the contract row
lock, so the ordering assertion needs no database. Fail-first on the pre-1.36 order, whose first
statement on the contract table was the ``FOR UPDATE`` row lock."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Literal
from uuid import UUID

import pytest
from erev_api.approvals import engine as approvals_engine
from erev_api.approvals import subjects
from erev_api.auth.principal import RequestContext
from erev_api.db import locking
from erev_api.db.session import TenantContextMissing
from erev_api.domain.contracts import (
    activation,
    combination,
    commands,
    estimates,
    events,
    holds,
    locks,
    repo,
)
from erev_api.domain.policies import judgements, overrides
from erev_api.enums import JudgementStatus, PrincipalKind, TenantKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from sqlalchemy import TextClause

CONTRACT = UUID(int=1)
GROUP = UUID(int=2)
OTHER_GROUP = UUID(int=3)
SUBMISSION = UUID(int=4)
SINGLETON = UUID(int=5)
ENTITY = UUID(int=6)
RECORD = UUID(int=7)
CONTRACT_ROW: dict[str, Any] = {
    "id": CONTRACT,
    "combination_group_id": GROUP,
    "contract_no": "C-1",
    "external_id": "SF-ORD-1",
    "contracting_entity_id": ENTITY,
    # Activatable, so the hooks run on to their write: a DRAFT. (``sorted(SUBMITTABLE)[0]`` named
    # it until supervisor ruling R-102 (a) admitted ACTIVE, whose criteria-met path reads the
    # stream for the books that move before it writes.)
    "status": "DRAFT",
    "head_stream_version": 1,
}
GROUP_ROW: dict[str, Any] = {
    "id": GROUP,
    "status": "PROPOSED",
    "is_singleton": False,
    "code": "CG-1",
}
RECORD_ROW: dict[str, Any] = {
    "id": RECORD,
    "contract_id": CONTRACT,
    "status": "SUBMITTED",
    "topic": "CONTRACT_TERM",
    "subject_type": "contract",
    "subject_id": CONTRACT,
    "judgement_no": "J-1",
    "book_code": None,
    "conclusion": "The term ends at the earliest termination.",
    "rationale": "No substantive penalty applies.",
    "alternatives_considered": None,
    "codification_refs": ["606-10-25-3"],
    "questionnaire": {
        "enforceable_end_date": "2026-12-31",
        "termination_penalty_substantive": False,
    },
}
APPROVAL_REQUEST = UUID(int=9)
V1_RULE = SimpleNamespace(rule_key="AUTO-JR-01", rule_set_code="P5-AUTO-JR")  # a matched rule
# A judgement of a contract: the contract's group, the record between, then the contract
# (DG-KRN-DB-08 rev 1.36; D-98 candidate 101c).
JUDGEMENT_ORDER = [
    ("judgement_record", False),
    ("contract", False),
    ("combination_group", True),
    ("judgement_record", True),
    ("contract", True),
]


def _bound(statement: Any) -> Any:
    """The id bound in a one-condition WHERE clause, when the statement has one."""
    return getattr(getattr(getattr(statement, "whereclause", None), "right", None), "value", None)


RULED_ORDER = [("contract", False), ("combination_group", True), ("contract", True)]
ESTIMATE_APPROVAL_ORDER = [("fx_publication_shared", True), *RULED_ORDER]


class _Stop(Exception):
    """Raised by the stand-in once the contract row lock — the second lock — is taken."""


class _Result:
    rowcount = 1

    def __init__(
        self, *, scalar: Any = None, row: Any = None, rows: list[Any] | None = None
    ) -> None:
        self._scalar, self._row, self._rows = scalar, row, rows

    def __iter__(self) -> Any:
        return iter(
            self._rows if self._rows is not None else ([] if self._row is None else [self._row])
        )

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalar_one(self) -> Any:
        return self._scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self._row

    def one(self) -> Any:
        return self._row

    def first(self) -> Any:
        return self._row

    def scalars(self) -> Any:
        return iter([] if self._scalar is None else [self._scalar])


class _Session:
    """Records ``(table, locked)`` for every contract / group statement; answers the helper's three
    statements; stops at the contract row lock unless ``regroup`` (then the contract has moved)."""

    def __init__(
        self,
        *,
        regroup: bool = False,
        stop: bool = True,
        record: dict[str, Any] | None = None,
        request: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.locked_groups: list[Any] = []  # the group ids taken FOR UPDATE, in order
        self.regroup = regroup
        self.stop = stop
        self.record = dict(RECORD_ROW if record is None else record)
        self.request = request  # an approval_request row read as a mapping, when a test needs one

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        if isinstance(statement, TextClause):
            # ``db.session.system_entity_scope`` (supervisor ruling R-64 (1)) reads the
            # transaction's entity scope before it widens it. This stand-in has no row-level
            # security: it answers "every entity", so the block runs as it is.
            assert "app.entity_scope" in statement.text, statement.text
            return _Result(scalar="*")
        froms = (
            statement.get_final_froms()
            if hasattr(statement, "get_final_froms")
            else [statement.table]
        )
        if not froms:
            # Estimate approval holds the tenant's shared FX gate before any row lock.
            # Recognize only this statement; do not silently accept arbitrary SELECTs.
            columns = list(statement.selected_columns)
            assert len(columns) == 1
            gate = columns[0]
            assert gate.name == "pg_advisory_xact_lock_shared"
            (key,) = list(gate.clauses)
            assert key.name == "hashtextextended"
            namespace, seed = list(key.clauses)
            assert namespace.value == f"erev:fx-publication:{PRINCIPAL.tenant_id}"
            assert seed.value == 0
            self.calls.append(("fx_publication_shared", True))
            return _Result()
        table = getattr(froms[0], "name", "join")  # a joined select (contract ⋈ legal_entity)
        locked = getattr(statement, "_for_update_arg", None) is not None
        if table in ("contract", "combination_group", "judgement_record"):
            self.calls.append((table, locked))
        if table == "contract" and not locked:
            bound = _bound(statement)
            if isinstance(bound, list):  # `contract.c.id.in_([...])`: one row per requested id
                return _Result(
                    rows=[SimpleNamespace(id=value, combination_group_id=GROUP) for value in bound]
                )
            return _Result(scalar=GROUP, row=dict(CONTRACT_ROW))
        if table == "combination_group" and locked:
            bound = _bound(statement)
            self.locked_groups.append(bound)
            return _Result(scalar=bound, row={**GROUP_ROW, "id": bound})
        if table == "combination_group":
            # Unlocked group reads: submit_group's preview of the target; a leave's singleton
            # lookup by code; _member_errors.
            if _bound(statement) == GROUP:
                return _Result(scalar=GROUP, row=dict(GROUP_ROW))
            return _Result(scalar=SINGLETON, row={"id": SINGLETON})
        if table == "judgement_record":
            return _Result(row=dict(self.record))
        if table == "join":
            return _Result(row=SimpleNamespace(head_stream_version=1, time_zone="UTC"))
        if table == "obligation_version":
            return _Result(scalar=None)  # no SSP pins
        if table == "contract" and locked:
            if self.regroup:
                return _Result(row={**CONTRACT_ROW, "combination_group_id": OTHER_GROUP})
            if not self.stop:
                return _Result(row=dict(CONTRACT_ROW))
            raise _Stop
        if table == "event_submission":
            return _Result(row={"id": SUBMISSION, "contract_id": CONTRACT, "events": []})
        if table == "approval_request":
            if self.request is not None:
                return _Result(scalar=None, row=dict(self.request))
            request = SimpleNamespace(preparer_id=None, reason_code=combination.LEAVE_REASON)
            return _Result(scalar=None, row=request)
        raise AssertionError(f"unexpected statement on {table}")


NOW = datetime(2026, 9, 20, tzinfo=UTC)
# Enough of a principal for the stamps (`updated_by`, `updated_by_kind`) of a transition and for
# `system_principal(uow.principal.tenant_id, …)` in the hooks' system units.
PRINCIPAL = SimpleNamespace(
    id=UUID(int=11),
    kind=PrincipalKind.USER,
    tenant_id=UUID(int=12),
    roles=(),
    membership_id=UUID(int=13),
    on_behalf_of_id=None,
)
CTX = RequestContext(
    principal=PRINCIPAL,  # type: ignore[arg-type]
    tenant_kind=TenantKind.PRODUCTION,
    request_id="r-unit",
    source_ip=None,
    user_agent=None,
    idempotency_key=None,
    if_match=None,
    now=NOW,
    format_locale="en-US",
)


class _Uow:
    """The unit-of-work stand-in; the hooks' system units rebuild it (``type(uow)(ctx=…)``) or
    build a real ``UnitOfWork`` on its session with its clock."""

    now = NOW
    ctx = CTX
    principal = PRINCIPAL
    clock = SimpleNamespace(now=lambda: NOW)
    keyring = None
    files = None

    def __init__(self, session: _Session, **parts: Any) -> None:
        self.session = session
        for name, value in parts.items():
            setattr(self, name, value)

    def audit(self, **kwargs: Any) -> None:
        return None

    def buffer_audit_event(self, event: Any) -> None:
        return None

    def discard(self) -> None:
        self.session.rollback()  # as UnitOfWork.discard: a transaction rollback


def _run(session: _Session, call: Any) -> None:
    with pytest.raises(_Stop):
        call(_Uow(session))


PATHS: list[tuple[str, Any]] = [
    (
        "activation.submit_activation",
        lambda uow: activation.submit_activation(
            uow, contract_id=CONTRACT, expected_stream_version=1, body=None
        ),
    ),
    (
        "activation.activate",
        lambda uow: activation.activate(
            uow, contract_id=CONTRACT, approval_request_id=None, on_behalf_of=None
        ),
    ),
    (
        "commands.replace_draft",
        lambda uow: commands.replace_draft(
            uow, contract_id=CONTRACT, expected_stream_version=1, body=None
        ),
    ),
    (
        "events.record_events",
        lambda uow: events.record_events(
            uow, contract_id=CONTRACT, expected_stream_version=1, body=None
        ),
    ),
    (
        "events.request_preview",
        lambda uow: events.request_preview(
            uow, contract_id=CONTRACT, expected_stream_version=1, body=None
        ),
    ),
    (
        "holds.apply_hold",
        lambda uow: holds.apply_hold(
            uow, contract_id=CONTRACT, expected_stream_version=1, body=None
        ),
    ),
    ("holds.apply_system_hold", lambda uow: holds.apply_system_hold(uow, CONTRACT, reason="R")),
    (
        "holds.release_system_holds",
        lambda uow: holds.release_system_holds(uow, CONTRACT, reason="R", comment="c"),
    ),
    (
        "locks.update_memos",
        lambda uow: locks.update_memos(
            uow, contract_id=CONTRACT, expected_stream_version=1, body=None
        ),
    ),
    (
        "approvals.subjects._apply_event_submission",
        lambda uow: subjects._apply_event_submission(uow, SUBMISSION, UUID(int=9)),
    ),
]


@pytest.mark.parametrize(("name", "call"), PATHS, ids=[name for name, _ in PATHS])
def test_entry_paths_lock_the_group_before_the_contract(name: str, call: Any) -> None:
    session = _Session()
    _run(session, call)
    assert session.calls == RULED_ORDER, name


def test_estimate_approval_locks_the_group_before_the_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``estimates._approve_version``, the ``ESTIMATE_VERSION`` approval hook (own rows first)."""
    monkeypatch.setattr(
        estimates,
        "_version_row",
        lambda session, version_id, *, lock=False: {
            "status": estimates.SUBMITTED,
            "estimate_id": UUID(int=5),
        },
    )
    monkeypatch.setattr(
        estimates,
        "_estimate_row",
        lambda session, estimate_id: {"id": UUID(int=5), "contract_id": CONTRACT},
    )
    session = _Session()
    _run(session, lambda uow: estimates._approve_version(uow, UUID(int=7), UUID(int=8)))
    assert session.calls == ESTIMATE_APPROVAL_ORDER


def test_estimate_version_creation_locks_the_group_before_the_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``estimates.create_version`` locks the contract through ``_visible_contract``."""
    monkeypatch.setattr(
        estimates,
        "_estimate_row",
        lambda session, estimate_id: {"id": UUID(int=5), "contract_id": CONTRACT},
    )
    session = _Session()
    _run(session, lambda uow: estimates.create_version(uow, estimate_id=UUID(int=5), body=None))
    assert session.calls == RULED_ORDER


def test_membership_is_re_verified_under_the_locks() -> None:
    """No pre-lock check is the last check: a contract that joined another group between the
    unlocked read and the row lock is refused as stale (412), never processed on the wrong group."""
    session = _Session(regroup=True)
    with pytest.raises(Problem) as refused:
        activation.activate(
            _Uow(session),  # type: ignore[arg-type]
            contract_id=CONTRACT,
            approval_request_id=None,
            on_behalf_of=None,
        )
    assert refused.value.slug == "precondition-failed"
    assert getattr(refused.value, "detail", None) == locking.REGROUPED
    assert session.calls == RULED_ORDER


def test_the_helper_is_shared_by_the_domain_and_the_approval_hooks() -> None:
    assert repo.lock_group_then_contract is locking.lock_group_then_contract
    assert repo.REGROUPED == locking.REGROUPED == activation.REGROUPED
    assert subjects.lock_group_then_contract is locking.lock_group_then_contract
    session = _Session(regroup=True)
    with pytest.raises(Problem):
        locking.lock_group_then_contract(session, CONTRACT)  # type: ignore[arg-type]
    assert session.calls == RULED_ORDER


def test_combination_locks_every_touched_group_before_the_member_contracts() -> None:
    """``combination._lock_groups_then_contracts`` (create_group, submit_group, apply_combination):
    every group — ``group_ids`` (the target, the leave singletons) and each contract's observed
    group — FOR UPDATE in one ascending id order, the target included; then ``between`` (the
    proposal record); then the member contracts in ascending id order (D-98 candidates 101b,
    101c)."""
    session = _Session(stop=False)
    at_between: list[list[tuple[str, bool]]] = []
    groups, rows = combination._lock_groups_then_contracts(
        session,  # type: ignore[arg-type]
        group_ids=[OTHER_GROUP, GROUP],
        expected={UUID(int=8): GROUP, CONTRACT: GROUP},
        between=lambda locked: at_between.append(list(session.calls)),
    )
    assert session.calls == [
        ("combination_group", True),
        ("combination_group", True),
        ("contract", True),
        ("contract", True),
    ]
    assert session.locked_groups == [GROUP, OTHER_GROUP]  # ascending; the target is not first
    assert at_between == [[("combination_group", True), ("combination_group", True)]]
    assert list(groups) == [GROUP, OTHER_GROUP] and len(rows) == 2


def test_membership_revalidation_proves_equality_not_presence() -> None:
    """D-98 candidate 101c (b): a contract whose group under the lock differs from the group
    observed at the unlocked read is refused REGROUPED even when its new group is among the locked
    rows — membership "in the locked set" was not the check."""
    session = _Session(regroup=True, stop=False)  # under the lock the contract says OTHER_GROUP
    with pytest.raises(Problem) as refused:
        combination._lock_groups_then_contracts(
            session,  # type: ignore[arg-type]
            group_ids=[OTHER_GROUP],  # locked too — and still not the group that was observed
            expected={CONTRACT: GROUP},
        )
    assert refused.value.slug == "precondition-failed"
    assert getattr(refused.value, "detail", None) == locking.REGROUPED
    assert session.locked_groups == [GROUP, OTHER_GROUP]


def _proposal(action: Literal["JOIN", "LEAVE"]) -> combination._Proposal:
    return combination._Proposal(
        record_id=RECORD, action=action, contract_ids=(CONTRACT,), status=JudgementStatus.SUBMITTED
    )


def test_visible_contracts_lock_their_own_groups_before_the_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``combination._visible_contracts`` (create_group; submit_group's JOIN and LEAVE branches):
    the proposal's contracts are read without locks for their current groups, those groups locked
    in ascending id order, then the contracts — and an unmoved population is ACCEPTED. An empty
    group set refused every contract (Codex packet production-20260920-1150 item 3; P5-LOCK-R3c)."""
    seen: list[tuple[str, UUID]] = []
    monkeypatch.setattr(
        combination,
        "require_for_entity",
        lambda ctx, permission, entity_id: seen.append((permission, entity_id)),
    )
    session = _Session(stop=False)
    groups, rows = combination._visible_contracts(_Uow(session), [CONTRACT])  # type: ignore[arg-type]
    assert session.calls == RULED_ORDER
    assert session.locked_groups == [GROUP] and list(groups) == [GROUP]
    assert [row["id"] for row in rows] == [CONTRACT]
    assert seen == [(combination.CREATE_PERMISSION, ENTITY)]


def test_visible_contracts_take_the_submit_target_in_the_sorted_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A submit passes its target into the sorted set: the target (id 3) is locked AFTER the
    member's group (id 2), never first; ``between`` runs after both and before the contract."""
    monkeypatch.setattr(combination, "require_for_entity", lambda ctx, permission, entity_id: None)
    session = _Session(stop=False)
    order: list[list[Any]] = []
    combination._visible_contracts(
        _Uow(session),  # type: ignore[arg-type]
        [CONTRACT],
        target=OTHER_GROUP,
        between=lambda groups: order.append([list(groups), list(session.calls)]),
    )
    assert session.locked_groups == [GROUP, OTHER_GROUP]
    assert order == [
        [[GROUP, OTHER_GROUP], [("contract", False)] + [("combination_group", True)] * 2]
    ]
    assert session.calls[-1] == ("contract", True)


@pytest.mark.parametrize(
    ("action", "target", "locked"),
    [("JOIN", OTHER_GROUP, [GROUP, OTHER_GROUP]), ("LEAVE", GROUP, [GROUP, SINGLETON])],
)
def test_apply_combination_lock_step_holds_every_touched_group(
    action: Literal["JOIN", "LEAVE"], target: UUID, locked: list[UUID]
) -> None:
    """``combination._lock_members``: a JOIN locks the member's original group and the target; a
    LEAVE — whose members belong to the target — locks the target and the member's singleton;
    one ascending id order, then the contract, and the population is accepted."""
    session = _Session(stop=False)
    groups, rows, singletons = combination._lock_members(
        session,  # type: ignore[arg-type]
        group_id=target,
        proposal=_proposal(action),
    )
    expected: list[tuple[str, bool]] = [("contract", False)]
    if action == "LEAVE":
        expected.append(("combination_group", False))  # the singleton looked up by code
    expected += [("combination_group", True)] * len(locked) + [("contract", True)]
    assert session.calls == expected
    assert session.locked_groups == locked and list(groups) == locked
    assert [row["id"] for row in rows] == [CONTRACT]
    assert singletons == ({CONTRACT: SINGLETON} if action == "LEAVE" else {})


def test_apply_combination_hands_the_held_target_to_the_lock_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``apply_combination`` up to its lock step, for a LEAVE whose members belong to the target:
    the proposal is read without a lock, the target and the member's observed group are handed to
    ``_lock_groups_then_contracts`` in one set (no lock is taken before it), and the proposal record
    lock is the ``between`` step (P5-LOCK-R3c; D-98 candidate 101c)."""
    handed: list[tuple[set[UUID], dict[UUID, UUID], bool]] = []

    def recorder(
        session: Any,
        *,
        group_ids: Iterable[UUID],
        expected: Mapping[UUID, UUID],
        between: Any = None,
    ) -> tuple[dict[UUID, dict[str, Any]], list[dict[str, Any]]]:
        handed.append(
            (set(group_ids) | set(expected.values()), dict(expected), between is not None)
        )
        raise _Stop

    monkeypatch.setattr(combination, "_lock_groups_then_contracts", recorder)
    monkeypatch.setattr(
        combination, "_proposal", lambda session, group_id, *, lock=False: _proposal("LEAVE")
    )
    session = _Session(stop=False)
    with pytest.raises(_Stop):
        combination.apply_combination(_Uow(session), GROUP, UUID(int=9))  # type: ignore[arg-type]
    assert handed == [({GROUP, SINGLETON}, {CONTRACT: GROUP}, True)]
    assert ("combination_group", True) not in session.calls  # the target is never taken first


@pytest.mark.parametrize(
    ("name", "call"),
    [
        (
            "judgements.review_judgement",
            lambda uow: judgements.review_judgement(uow, RECORD, UUID(int=9)),
        ),
        (
            "judgements.submit_judgement",
            lambda uow: judgements.submit_judgement(uow, judgement_id=RECORD, body=None),
        ),
    ],
    ids=["review_judgement", "submit_judgement"],
)
def test_judgement_paths_lock_the_group_then_the_record_then_the_contract(
    name: str, call: Any
) -> None:
    """D-98 candidate 101c (a): a judgement of a contract reads its record without a lock, locks
    the contract's group, then the record (``between``), then the contract — before this slice the
    record was locked first and the group taken afterwards by the hold / recompute."""
    session = _Session()
    _run(session, call)
    assert session.calls == JUDGEMENT_ORDER, name


# --- D-98 candidate 101d: the approved basis (P5-LOCK-R3d) ----------------------------------------


def test_submit_judgement_holds_the_active_contract_before_the_basis_is_hashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DG-KRN-APR-05 rev 1.40 (Codex SELF-STALE-R1): for a contract judgement that will wait for a
    person, ``submit_judgement`` applies the REQ-POL-010 hold BEFORE ``approvals.submit`` hashes
    the subject content — the hold's HOLD_APPLIED raises the head, so a hash taken first was stale
    at once and the first unchanged approval was refused STALE_SUBJECT."""
    order: list[str] = []
    monkeypatch.setattr(judgements, "require_for_entity", lambda ctx, permission, entity_id: None)
    monkeypatch.setattr(  # raising=False: absent on the pre-101d engine — the test then observes
        judgements.approvals,  # the old order ["submit"] instead of erroring
        "route_submission",
        lambda uow, subject_type, subject_id, **kwargs: SimpleNamespace(auto_rule=None),
        raising=False,
    )
    monkeypatch.setattr(
        judgements.holds,
        "apply_system_hold",
        lambda uow, contract_id, *, reason: order.append("hold"),
    )

    def submit(uow: Any, **kwargs: Any) -> None:
        order.append("submit")
        raise _Stop

    monkeypatch.setattr(judgements.approvals, "submit", submit)
    session = _Session(stop=False, record={**RECORD_ROW, "status": "DRAFT"})
    with pytest.raises(_Stop):
        judgements.submit_judgement(
            _Uow(session),  # type: ignore[arg-type]
            judgement_id=RECORD,
            body=SimpleNamespace(comment=None),  # type: ignore[arg-type]
        )
    assert order == ["hold", "submit"]
    assert session.calls[:5] == JUDGEMENT_ORDER  # the record's own locks come first, unchanged


def test_submit_judgement_never_holds_for_an_auto_approved_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hold is decided from the same auto-approval evaluation ``submit`` makes: a matching
    AUTO_APPROVAL rule → no hold (the review would release it at once)."""
    order: list[str] = []
    monkeypatch.setattr(judgements, "require_for_entity", lambda ctx, permission, entity_id: None)
    monkeypatch.setattr(
        judgements.approvals,
        "route_submission",
        lambda uow, subject_type, subject_id, **kwargs: SimpleNamespace(auto_rule=V1_RULE),
        raising=False,
    )
    monkeypatch.setattr(
        judgements.holds,
        "apply_system_hold",
        lambda uow, contract_id, *, reason: order.append("hold"),
    )

    def submit(uow: Any, **kwargs: Any) -> None:
        order.append("submit")
        raise _Stop

    monkeypatch.setattr(judgements.approvals, "submit", submit)
    session = _Session(stop=False, record={**RECORD_ROW, "status": "DRAFT"})
    with pytest.raises(_Stop):
        judgements.submit_judgement(
            _Uow(session),  # type: ignore[arg-type]
            judgement_id=RECORD,
            body=SimpleNamespace(comment=None),  # type: ignore[arg-type]
        )
    assert order == ["submit"]


# --- item STEP1-HOLD-RELEASE-1 (the supervisor's ruling of 2026-10-01; 04 T-CON-20 rev 1.209) -----

NOT_A_CONTRACT_ROW: dict[str, Any] = {
    **RECORD_ROW,
    "status": "DRAFT",
    "topic": "NOT_A_CONTRACT",
    "book_code": "ASC606",
    "conclusion": "Collection is not probable after the downgrade.",
    "rationale": "Credit review.",
    "codification_refs": ["606-10-25-1"],
    # (d) Yes agrees with the stand-in's contract, which answers a truthy commercial substance.
    "questionnaire": {
        "consideration_nonrefundable": False,
        "criteria": {"a": "YES", "b": "YES", "c": "YES", "d": "YES", "e": "NO"},
    },
}
STEP1_REASON = (
    "Judgement record J-1 (NOT_A_CONTRACT) is not reviewed, or the Step 1 assessment that cites "
    "it is not recorded."
)


def test_step1_hold_release_1_an_auto_approved_not_a_contract_record_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor's ruling on Q-H3: the hold of a ``NOT_A_CONTRACT`` record is released by
    the assessment that cites it, not by the review, so it is placed at the submission whatever
    the routing — an auto-approved record (a machine's, under a published rule) left the book
    recognising from the review to the assessment. Control: the record of another topic above
    (``test_submit_judgement_never_holds_for_an_auto_approved_record``) still places none."""
    order: list[str] = []
    monkeypatch.setattr(judgements, "require_for_entity", lambda ctx, permission, entity_id: None)
    monkeypatch.setattr(
        judgements.approvals,
        "route_submission",
        lambda uow, subject_type, subject_id, **kwargs: SimpleNamespace(auto_rule=V1_RULE),
    )
    monkeypatch.setattr(
        judgements.holds,
        "apply_system_hold",
        lambda uow, contract_id, *, reason: order.append(f"hold: {reason}"),
    )

    def submit(uow: Any, **kwargs: Any) -> None:
        order.append("submit")
        raise _Stop

    monkeypatch.setattr(judgements.approvals, "submit", submit)
    session = _Session(stop=False, record=dict(NOT_A_CONTRACT_ROW))
    with pytest.raises(_Stop):
        judgements.submit_judgement(
            _Uow(session),  # type: ignore[arg-type]
            judgement_id=RECORD,
            body=SimpleNamespace(comment=None),  # type: ignore[arg-type]
        )
    assert order == [f"hold: {STEP1_REASON}", "submit"]


class _SubjectSession(_Session):
    """``_Session`` that also answers the status read of a record's modification."""

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        froms = (
            statement.get_final_froms()
            if hasattr(statement, "get_final_froms")
            else [statement.table]
        )
        if getattr(froms[0], "name", "") == "modification":
            return _Result(scalar="DRAFT")
        return super().execute(statement, *args, **kwargs)


@pytest.mark.parametrize(
    ("subject_type", "names_contract", "held"),
    [
        ("contract", True, True),
        ("obligation", True, True),
        ("product", True, True),
        ("combination_group", True, True),
        ("registry_version", True, True),
        ("migration_batch", True, True),
        ("product", False, False),
        ("combination_group", False, False),
        ("modification", True, False),
        ("estimate_version", True, False),
    ],
)
def test_step1_hold_release_1_the_hold_follows_the_contract_the_record_names(
    monkeypatch: pytest.MonkeyPatch, subject_type: str, names_contract: bool, held: bool
) -> None:
    """Supervisor ruling R-23, second order (04 T-CON-20 "Judgement holds" rev 1.209): the
    REQ-POL-010 hold is the hold of the contract the record NAMES (``contract_id``), whatever
    the record's subject — before, only a record whose subject was a contract or an obligation
    held, and a record of a product or a combination group that named a contract placed nothing.
    A record that names no contract holds nothing. The two subjects that take their contract
    from the subject and change nothing of it before their own approval — a modification, an
    estimate version — place none."""
    order: list[str] = []
    monkeypatch.setattr(judgements, "require_for_entity", lambda ctx, permission, entity_id: None)
    monkeypatch.setattr(
        judgements.approvals,
        "route_submission",
        lambda uow, subject_type, subject_id, **kwargs: SimpleNamespace(auto_rule=None),
    )
    monkeypatch.setattr(
        judgements.holds,
        "apply_system_hold",
        lambda uow, contract_id, *, reason: order.append(f"hold {contract_id}"),
    )

    def submit(uow: Any, **kwargs: Any) -> None:
        order.append("submit")
        raise _Stop

    monkeypatch.setattr(judgements.approvals, "submit", submit)
    record = {
        **RECORD_ROW,
        "status": "DRAFT",
        "subject_type": subject_type,
        "subject_id": UUID(int=77),
        "contract_id": CONTRACT if names_contract else None,
    }
    with pytest.raises(_Stop):
        judgements.submit_judgement(
            _Uow(_SubjectSession(stop=False, record=record)),  # type: ignore[arg-type]
            judgement_id=RECORD,
            body=SimpleNamespace(comment=None),  # type: ignore[arg-type]
        )
    assert order == ([f"hold {CONTRACT}", "submit"] if held else ["submit"])


class _Records:
    """A session that answers the judgement records of a contract as ``_judgement_refusal``
    reads them: (number, topic, status)."""

    def __init__(self, *rows: tuple[str, str, str]) -> None:
        self.rows = list(rows)

    def execute(self, statement: Any) -> Any:
        return SimpleNamespace(all=lambda: list(self.rows))


def test_step1_hold_release_1_one_sentence_writes_and_finds_a_judgement_hold() -> None:
    """04 T-CON-20 "Judgement holds" (rev 1.209): T-CON-20 names no record, so the hold of a
    judgement record is found by its reason text, and ``holds.judgement_hold_reason`` is the one
    writer and the one reader of that sentence. The two sentences as ruled; and what
    ``release_hold`` answers when it is asked to release such a hold by hand — refused while the
    record waits for its review, and for a ``NOT_A_CONTRACT`` record while it is REVIEWED (its
    assessment releases it); a record that is DRAFT, REJECTED or SUPERSEDED refuses nothing, and
    neither does a hold that is not a record's."""
    plain = holds.judgement_hold_reason("J-7", "COLLECTIBILITY")
    step1_reason = holds.judgement_hold_reason("J-1", "NOT_A_CONTRACT")
    assert plain == "Judgement record J-7 (COLLECTIBILITY) is not reviewed."
    assert step1_reason == STEP1_REASON
    assert holds.judgement_hold_reason("J-7", "CONTRACT_TERM") == (
        "Judgement record J-7 (CONTRACT_TERM) is not reviewed."
    )

    def refusal(reason: str, *rows: tuple[str, str, str], source: str = "SYSTEM") -> str | None:
        hold = {"hold_source": source, "contract_id": CONTRACT, "reason": reason}
        return holds._judgement_refusal(_Records(*rows), hold)  # type: ignore[arg-type]

    by_review = "This hold is released by the review of judgement record J-7."
    by_assessment = (
        "This hold is released when the Step 1 assessment that cites judgement record J-1 is "
        "recorded."
    )
    assert refusal(plain, ("J-7", "COLLECTIBILITY", "SUBMITTED")) == by_review
    assert refusal(step1_reason, ("J-1", "NOT_A_CONTRACT", "SUBMITTED")) == (
        "This hold is released by the review of judgement record J-1."
    )
    assert refusal(step1_reason, ("J-1", "NOT_A_CONTRACT", "REVIEWED")) == by_assessment
    # the record among others of the contract is found by the sentence, not by its position
    others = (("J-0", "CONTRACT_TERM", "REVIEWED"), ("J-7", "COLLECTIBILITY", "SUBMITTED"))
    assert refusal(plain, *others) == by_review
    for status in ("DRAFT", "REJECTED", "SUPERSEDED"):
        assert refusal(plain, ("J-7", "COLLECTIBILITY", status)) is None, status
        assert refusal(step1_reason, ("J-1", "NOT_A_CONTRACT", status)) is None, status
    # a reviewed record of another topic has no hold left to keep
    assert refusal(plain, ("J-7", "COLLECTIBILITY", "REVIEWED")) is None
    # a hold a person applied with the same words, and a SYSTEM hold of no record
    assert refusal(plain, ("J-7", "COLLECTIBILITY", "SUBMITTED"), source="MANUAL") is None
    assert refusal("Product AVM-KIT has no approved SSP.", *others) is None
    assert refusal(plain) is None


def test_assert_fresh_basis_refuses_a_changed_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    """``engine.assert_fresh_basis``: the subject's content hash under the hook's locks must equal
    the request's stored basis; a difference is ``StaleBasis`` (409 ``stale-approval``)."""
    request = {
        "id": APPROVAL_REQUEST,
        "subject_type": "COMBINATION_GROUP",
        "subject_id": GROUP,
        "subject_content_sha256": "a" * 64,
    }
    session = _Session(request=request)
    monkeypatch.setattr(approvals_engine, "current_content_sha256", lambda uow, spec, req: "b" * 64)
    with pytest.raises(Problem) as refused:
        approvals_engine.assert_fresh_basis(_Uow(session), APPROVAL_REQUEST)  # type: ignore[arg-type]
    assert isinstance(refused.value, approvals_engine.StaleBasis)
    assert refused.value.slug == "stale-approval"
    monkeypatch.setattr(approvals_engine, "current_content_sha256", lambda uow, spec, req: "a" * 64)
    approvals_engine.assert_fresh_basis(_Uow(session), APPROVAL_REQUEST)  # type: ignore[arg-type]


def test_apply_combination_revalidates_the_basis_under_every_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex WAIT-FRESH-R2: ``apply_combination`` calls ``assert_fresh_basis`` after the groups,
    the proposal record and the contracts are locked and before anything is applied."""
    seen: list[list[tuple[str, bool]]] = []

    def fresh(uow: Any, approval_request_id: UUID) -> None:
        seen.append(list(uow.session.calls))
        raise _Stop

    monkeypatch.setattr(combination.approvals, "assert_fresh_basis", fresh, raising=False)
    monkeypatch.setattr(
        combination, "_proposal", lambda session, group_id, *, lock=False: _proposal("LEAVE")
    )
    monkeypatch.setattr(
        combination,
        "_review",
        lambda uow, record_id, approval_request_id: pytest.fail("applied before the basis check"),
    )
    session = _Session(stop=False)
    with pytest.raises(_Stop):
        combination.apply_combination(_Uow(session), GROUP, APPROVAL_REQUEST)  # type: ignore[arg-type]
    assert seen == [
        [
            ("contract", False),
            ("combination_group", False),
            ("combination_group", True),
            ("combination_group", True),
            ("contract", True),
        ]
    ]


def test_review_judgement_revalidates_the_basis_under_every_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``review_judgement`` calls ``assert_fresh_basis`` once the group, the record and the
    contract are locked, before the REVIEWED transition, the hold release and the recompute."""
    seen: list[list[tuple[str, bool]]] = []

    def fresh(uow: Any, approval_request_id: UUID) -> None:
        seen.append(list(uow.session.calls))
        raise _Stop

    monkeypatch.setattr(judgements.approvals, "assert_fresh_basis", fresh, raising=False)
    session = _Session(stop=False)
    with pytest.raises(_Stop):
        judgements.review_judgement(_Uow(session), RECORD, APPROVAL_REQUEST)  # type: ignore[arg-type]
    assert seen == [JUDGEMENT_ORDER]


# --- R3d-b: every on_approved hook re-validates the basis under its locks -------------------------


def _fresh_recorder(seen: list[list[tuple[str, bool]]]) -> Any:
    def fresh(uow: Any, approval_request_id: UUID) -> None:
        seen.append(list(uow.session.calls))
        raise _Stop

    return fresh


def _applied_too_early(*args: Any, **kwargs: Any) -> None:
    pytest.fail("applied before the basis check")


def test_activation_revalidates_the_basis_under_its_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    """``activation.activate`` (CONTRACT_ACTIVATION; content pins the contract's head and group):
    the check runs after the group and contract locks, before CONTRACT_ACTIVATED is appended."""
    seen: list[list[tuple[str, bool]]] = []

    def fresh_own(
        uow: Any, approval_request_id: UUID, *, subject_type: Any, subject_id: UUID
    ) -> None:
        # P5-RET-1: activate checks its OWN request through assert_own_fresh_basis.
        assert (subject_type, subject_id) == (
            approvals_engine.ApprovalSubjectType.CONTRACT_ACTIVATION,
            CONTRACT,
        )
        seen.append(list(uow.session.calls))
        raise _Stop

    monkeypatch.setattr(activation.approvals, "assert_own_fresh_basis", fresh_own, raising=False)
    monkeypatch.setattr(
        activation,
        "evaluate",
        lambda session, row, *, now, stored=False: SimpleNamespace(failed=False, items=[]),
    )
    monkeypatch.setattr(activation, "_activated", lambda *args, **kwargs: None)
    monkeypatch.setattr(activation, "append_events", _applied_too_early)
    session = _Session(stop=False)
    with pytest.raises(_Stop):
        activation.activate(
            _Uow(session),  # type: ignore[arg-type]
            contract_id=CONTRACT,
            approval_request_id=APPROVAL_REQUEST,
            on_behalf_of=None,
        )
    assert seen == [RULED_ORDER]


def test_estimate_approval_revalidates_the_basis_under_its_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``estimates._approve_version`` (ESTIMATE_VERSION; content lists the version's own fields,
    none decision-derived): the check runs after the version row, the group, the contract and the
    earlier approved versions are locked, before the first transition."""
    seen: list[list[tuple[str, bool]]] = []
    monkeypatch.setattr(
        estimates.approvals, "assert_fresh_basis", _fresh_recorder(seen), raising=False
    )
    monkeypatch.setattr(
        estimates,
        "_version_row",
        lambda session, version_id, *, lock=False: {
            "status": estimates.SUBMITTED,
            "estimate_id": UUID(int=5),
        },
    )
    monkeypatch.setattr(
        estimates,
        "_estimate_row",
        lambda session, estimate_id: {"id": UUID(int=5), "contract_id": CONTRACT},
    )
    monkeypatch.setattr(
        estimates, "_approved_versions", lambda session, estimate_id, *, lock=False: []
    )
    monkeypatch.setattr(estimates.transitions, "apply", _applied_too_early)
    session = _Session(stop=False)
    with pytest.raises(_Stop):
        estimates._approve_version(_Uow(session), UUID(int=7), APPROVAL_REQUEST)  # type: ignore[arg-type]
    assert seen == [ESTIMATE_APPROVAL_ORDER]


def test_event_submission_revalidates_the_basis_under_its_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``subjects._apply_event_submission`` (MANUAL_EVENT / MODIFICATION; content = the
    submission's contract id and stored events, immutable after submission): the uniform check
    still runs after the submission, group and contract locks, before the events are appended."""
    seen: list[list[tuple[str, bool]]] = []
    monkeypatch.setattr(
        approvals_engine, "assert_fresh_basis", _fresh_recorder(seen), raising=False
    )
    monkeypatch.setattr(subjects, "append_events", _applied_too_early)
    session = _Session(stop=False)
    with pytest.raises(_Stop):
        subjects._apply_event_submission(_Uow(session), SUBMISSION, APPROVAL_REQUEST)  # type: ignore[arg-type]
    assert seen == [RULED_ORDER]


def test_ssp_override_revalidates_the_basis_under_its_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``overrides._apply_ssp_override`` (SSP_OVERRIDE; the proposal with its base state — the
    obligation, its SSP pins, the proposed version's status; none decision-derived): the check runs
    after the group and contract locks, before LINE_ATTRIBUTES_CHANGED is appended."""
    seen: list[list[tuple[str, bool]]] = []
    monkeypatch.setattr(
        overrides.approvals, "assert_fresh_basis", _fresh_recorder(seen), raising=False
    )
    monkeypatch.setattr(
        overrides.preview,
        "request_proposal",
        lambda uow, request_id: {
            "contract_id": str(CONTRACT),
            "obligation_id": str(UUID(int=13)),
            "obligation_key": "O1",
            "ssp_book_version_id": str(UUID(int=14)),
            "justification": "Priced from the newer study.",
        },
    )
    monkeypatch.setattr(overrides, "append_events", _applied_too_early)
    session = _Session(stop=False)
    with pytest.raises(_Stop):
        overrides._apply_ssp_override(_Uow(session), UUID(int=13), APPROVAL_REQUEST)  # type: ignore[arg-type]
    assert seen == [RULED_ORDER]


# --- CONTEXT-R1: the stale-basis refusal keeps the tenant context --------------------------------


class _ContextSession:
    """A session whose transaction rollback drops ``erev.context`` (the app engine's DG-KRN-DB-04
    listener) and refuses the next statement, while a savepoint rollback keeps it."""

    def __init__(self, *, request: dict[str, Any]) -> None:
        self.context = True
        self.request = request
        self.calls: list[str] = []
        self.nested: list[str] = []

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        if not self.context:
            raise TenantContextMissing("SQL on the app engine requires tenant_session")
        self.calls.append(statement.get_final_froms()[0].name)
        return _Result(row=dict(self.request))

    def rollback(self) -> None:
        self.calls.append("ROLLBACK")
        self.context = False

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.calls.append("COMMIT")

    def begin_nested(self) -> Any:
        session = self

        class _Nested:
            def rollback(self) -> None:
                session.nested.append("ROLLBACK TO SAVEPOINT")

            def commit(self) -> None:
                session.nested.append("RELEASE SAVEPOINT")

        self.nested.append("SAVEPOINT")
        return _Nested()


def _pending_request() -> dict[str, Any]:
    return {
        "id": APPROVAL_REQUEST,
        "subject_type": "COMBINATION_GROUP",
        "subject_id": GROUP,
        "subject_content_sha256": "a" * 64,
        "status": "PENDING",
    }


def test_refuse_stale_basis_keeps_the_tenant_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex CONTEXT-R1 (packet 1330): on 5ce7c458 ``_refuse_stale_basis`` rolled the transaction
    back (``uow.discard()``), the app engine dropped ``erev.context`` and the very next statement —
    re-locking the request — was refused ``TenantContextMissing``: the void and the 409 were never
    reached. Now the caller's savepoint has undone the writes; the refusal re-locks the request,
    voids it, commits and raises 409 ``stale-approval`` on a session that kept its context."""
    voided: list[UUID] = []
    monkeypatch.setattr(
        approvals_engine,
        "_void",
        lambda uow, request, spec, **kwargs: voided.append(UUID(str(request["id"]))),
    )
    monkeypatch.setattr(approvals_engine, "current_content_sha256", lambda uow, spec, req: "b" * 64)
    session = _ContextSession(request=_pending_request())
    uow = _Uow(session)  # type: ignore[arg-type]
    uow.commit = lambda: session.commit()  # type: ignore[method-assign]
    spec = approvals_engine.spec_for(approvals_engine.ApprovalSubjectType.COMBINATION_GROUP)
    with pytest.raises(Problem) as refused:
        approvals_engine._refuse_stale_basis(uow, APPROVAL_REQUEST, spec)  # type: ignore[arg-type]
    assert refused.value.slug == "stale-approval"
    assert voided == [APPROVAL_REQUEST]
    assert session.context and "ROLLBACK" not in session.calls
    assert session.calls == ["approval_request", "COMMIT"]  # re-lock, void (stubbed), commit


def test_savepoint_undoes_the_writes_and_keeps_the_context() -> None:
    """``UnitOfWork.savepoint()`` (DG-KRN-UOW-03 rev 1.40): an exception inside rolls back to the
    savepoint — never the transaction — and drops the audit events and hooks buffered inside it;
    the session keeps its context; the exception propagates. Success releases the savepoint."""
    session = _ContextSession(request=_pending_request())
    uow = UnitOfWork(
        ctx=CTX,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        clock=_Uow.clock,  # type: ignore[arg-type]
        keyring=None,  # type: ignore[arg-type]
        files=None,  # type: ignore[arg-type]
    )
    uow.buffer_audit_event({"n": 1})
    uow.after_commit(lambda: None)
    with pytest.raises(approvals_engine.StaleBasis):
        with uow.savepoint():
            uow.buffer_audit_event({"n": 2})
            uow.after_commit(lambda: None)
            raise approvals_engine.StaleBasis()
    assert session.nested == ["SAVEPOINT", "ROLLBACK TO SAVEPOINT"]
    assert session.context and "ROLLBACK" not in session.calls
    assert uow.drain_audit_events() == [{"n": 1}]
    assert len(uow._hooks) == 1
    with uow.savepoint():
        uow.buffer_audit_event({"n": 3})
    assert session.nested[-1] == "RELEASE SAVEPOINT"
    assert uow.drain_audit_events() == [{"n": 3}]


# --- ROUTING-R1: one routing decision for the hold and the outcome -------------------------------


def _routing_stubs(monkeypatch: pytest.MonkeyPatch, versions: list[Any]) -> list[Any]:
    """``routing.resolve_steps`` answers ``versions`` in order (the published routing state v1,
    then v2 …) and records each reading; the other reads of the published state are stubbed away
    from the database.

    Supervisor ruling R-26 (b) (04 §16.10 rev 1.104): no ``AUTO_APPROVAL`` rule is read for a
    judgement record a user prepares, so the reading these cases count is the one that still
    happens — the routed steps (agreed with the supervisor, question 2 of lane SECFIX-APR). The
    allow-list is the real one: ``routing.auto_approval`` raises here, because reaching it for
    this subject would be the defect of finding SN-9.

    Supervisor rulings R-64 (1) and R-66 (8): a command that routes before it submits also reads
    the subject's entities, whose codes are the ``entity.code`` fact. These cases count the
    readings of the published routing, so the record of this stand-in world names no entity —
    stubbed like the other reads, with the scope statement the stand-in session answers."""
    seen: list[Any] = []

    def resolve_steps(session: Any, facts: Any, *, fallback: Any, at: Any) -> Any:
        found = versions[min(len(seen), len(versions) - 1)]
        seen.append(found)
        return found

    def auto_approval(session: Any, facts: Any, **kwargs: Any) -> Any:
        raise AssertionError("no AUTO_APPROVAL rule is read for a judgement record of a user")

    monkeypatch.setattr(approvals_engine.routing, "resolve_steps", resolve_steps)
    monkeypatch.setattr(approvals_engine.routing, "auto_approval", auto_approval)
    monkeypatch.setattr(
        approvals_engine.routing, "setup_completed", lambda session, tenant_id: True
    )
    monkeypatch.setattr(approvals_engine, "_role_id", lambda session, spec, code: None)
    monkeypatch.setattr(
        approvals_engine,
        "subject_entities",
        lambda session, spec, subject_id: approvals_engine.TENANT_LEVEL,
    )
    return seen


def _routing(*names: str) -> Any:
    """A published routing state: the steps ``names`` of one ``judgement.review`` approver each."""
    return approvals_engine.routing.Routing(
        steps=tuple(
            approvals_engine.routing.StepPlan(
                name=name, permission="judgement.review", min_approvers=1
            )
            for name in names
        ),
        rule=None,
    )


V1_ROUTING = _routing("Judgement review")
V2_ROUTING = _routing("Judgement review", "Controller review")


def test_submit_judgement_binds_the_hold_and_the_outcome_to_one_routing_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex ROUTING-R1 (packet 1337): the published routing state changes between the hold
    decision and the request's routing (v1, then a superseding v2). On 5ce7c458 the two reads were
    independent — then of the AUTO_APPROVAL state: the hold was skipped on a matching v1 and
    ``approvals.submit`` re-read v2 and returned PENDING, an unheld ACTIVE contract with a pending
    review (REQ-POL-010 broken). Now one ``route_submission`` reading decides both, and
    ``submit`` is handed that decision. Since ruling R-26 (b) a judgement record of a user is
    never auto-approved, so the one reading is of the routed steps: the contract is held, the
    request is PENDING, and its steps are v1's although v2 is published by then."""
    seen = _routing_stubs(monkeypatch, [V1_ROUTING, V2_ROUTING])
    order: list[str] = []
    handed: list[Any] = []
    monkeypatch.setattr(judgements, "require_for_entity", lambda ctx, permission, entity_id: None)
    monkeypatch.setattr(
        judgements.holds,
        "apply_system_hold",
        lambda uow, contract_id, *, reason: order.append("hold"),
    )

    def submit(uow: Any, **kwargs: Any) -> None:
        # The real submit's outcome: the decision it was handed, else its own (second) reading.
        decision = kwargs.get("routing_decision")
        if decision is None:
            decision = approvals_engine.route_submission(
                uow, kwargs["subject_type"], kwargs["subject_id"]
            )
        handed.append(decision)
        order.append("APPROVED" if decision.auto_rule is not None else "PENDING")
        raise _Stop

    monkeypatch.setattr(judgements.approvals, "submit", submit)
    session = _Session(stop=False, record={**RECORD_ROW, "status": "DRAFT"})
    with pytest.raises(_Stop):
        judgements.submit_judgement(
            _Uow(session),  # type: ignore[arg-type]
            judgement_id=RECORD,
            body=SimpleNamespace(comment=None),  # type: ignore[arg-type]
        )
    # Consistent: an ACTIVE contract's judgement is held exactly when a person decides.
    assert ("hold" in order) == ("PENDING" in order), order
    assert order == ["hold", "PENDING"] and len(seen) == 1  # one reading: held, a person decides
    assert handed[0].routed is V1_ROUTING  # the steps of THAT reading, not of the later v2


def test_route_submission_reads_the_published_routing_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """``engine.route_submission`` takes the steps and the auto-approval rule in one reading; the
    decision names its subject so ``submit`` can refuse another subject's decision. For a
    judgement record a user prepares no ``AUTO_APPROVAL`` rule is read at all (R-26 (b))."""
    seen = _routing_stubs(monkeypatch, [V1_ROUTING, V2_ROUTING])
    session = _Session(stop=False)
    decision = approvals_engine.route_submission(
        _Uow(session),  # type: ignore[arg-type]
        approvals_engine.ApprovalSubjectType.JUDGEMENT_RECORD,
        RECORD,
    )
    assert (decision.subject_type.value, decision.subject_id, decision.auto_rule) == (
        "JUDGEMENT_RECORD",
        RECORD,
        None,
    )
    assert (decision.amount, decision.flags, decision.routed) == (None, [], V1_ROUTING)
    assert len(seen) == 1


# --- P5-RET-1: the import approval's basis is consumed once; activation takes the composition -----


IMPORT_REQUEST: dict[str, Any] = {
    "id": APPROVAL_REQUEST,
    "subject_type": "IMPORT_COMMIT",
    "subject_id": UUID(int=20),
    "subject_content_sha256": "a" * 64,
    "status": "APPROVED",
}
ACTIVATION_REQUEST: dict[str, Any] = {
    **IMPORT_REQUEST,
    "subject_type": "CONTRACT_ACTIVATION",
    "subject_id": CONTRACT,
}


def _activation_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reads and the first write of ``activate`` after its locks and its basis step."""
    monkeypatch.setattr(
        activation,
        "evaluate",
        lambda session, row, *, now, stored=False: SimpleNamespace(failed=False, items=[]),
    )
    monkeypatch.setattr(activation, "_activated", lambda *args, **kwargs: None)

    def append(*args: Any, **kwargs: Any) -> None:
        raise _Stop  # the first write: reached only past the basis step

    monkeypatch.setattr(activation, "append_events", append)


def _consumed(session: Any, *, keys: frozenset[str] = frozenset({"SF-ORD-1"})) -> Any:
    return approvals_engine.ConsumedBasis(
        approval_request_id=APPROVAL_REQUEST,
        subject_type=approvals_engine.ApprovalSubjectType.IMPORT_COMMIT,
        subject_id=UUID(int=20),
        keys=keys,
        bases={key: None for key in keys},
        session=session,
    )


def test_activation_under_a_consumed_import_basis_proceeds_without_rehashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returned item P5-RET-1 (integrated batch on main 0cb36c14: every legacy import COMMIT failed
    `import.commit_failed error_class=StaleBasis`; 134 ci failures, all parity cases): the legacy
    import hands its IMPORT_COMMIT approval to ``activate`` (BR-DAT-06) after booking the very
    contracts that approval's content pins. The job consumed that basis once, before any effect,
    and carries the composition; ``activate`` verifies it — same transaction, this contract's key,
    the same request — and never re-hashes the import subject."""
    _activation_stubs(monkeypatch)
    hashed: list[UUID] = []

    def moved(uow: Any, spec: Any, request: Any) -> str:
        hashed.append(UUID(str(request["subject_id"])))
        return "b" * 64  # the import content moved — its own booking advanced the heads

    monkeypatch.setattr(approvals_engine, "current_content_sha256", moved)
    session = _Session(stop=False, request=IMPORT_REQUEST)
    with pytest.raises(_Stop):  # reached append_events: no StaleBasis, no refusal
        activation.activate(
            _Uow(session),  # type: ignore[arg-type]
            contract_id=CONTRACT,
            approval_request_id=APPROVAL_REQUEST,
            on_behalf_of=None,
            consumed=_consumed(session),
        )
    assert hashed == []  # the import subject is not hashed here at all
    assert session.calls[:3] == RULED_ORDER


def test_activation_under_a_bare_foreign_request_is_refused_not_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 0216: a bare foreign request id is never admitted — neither re-hashed as the wrong
    subject (main 0cb36c14: StaleBasis) nor skipped (687229c8): ``LookupError`` before any write."""
    _activation_stubs(monkeypatch)
    monkeypatch.setattr(
        approvals_engine, "current_content_sha256", lambda uow, spec, request: "b" * 64
    )
    session = _Session(stop=False, request=IMPORT_REQUEST)
    with pytest.raises(LookupError):
        activation.activate(
            _Uow(session),  # type: ignore[arg-type]
            contract_id=CONTRACT,
            approval_request_id=APPROVAL_REQUEST,
            on_behalf_of=None,
        )


def test_activation_under_its_own_approval_still_refuses_a_moved_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No weakening: the CONTRACT_ACTIVATION request of this contract is re-validated under the
    locks and a moved basis is refused StaleBasis before any write."""
    _activation_stubs(monkeypatch)
    monkeypatch.setattr(
        approvals_engine, "current_content_sha256", lambda uow, spec, request: "b" * 64
    )
    session = _Session(stop=False, request=ACTIVATION_REQUEST)
    with pytest.raises(approvals_engine.StaleBasis):
        activation.activate(
            _Uow(session),  # type: ignore[arg-type]
            contract_id=CONTRACT,
            approval_request_id=APPROVAL_REQUEST,
            on_behalf_of=None,
        )
    assert ("contract", True) in session.calls  # the locks were taken first


@pytest.mark.parametrize(
    "case",
    ["another transaction", "a contract outside the keys", "another request"],
)
def test_activation_refuses_a_composition_that_does_not_cover_it(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """The composition is verified, not trusted: it must be this transaction's, cover this
    contract's external id and name the request handed along."""
    _activation_stubs(monkeypatch)
    session = _Session(stop=False, request=IMPORT_REQUEST)
    consumed = _consumed(session)
    request_id = APPROVAL_REQUEST
    if case == "another transaction":
        consumed = _consumed(_Session(stop=False, request=IMPORT_REQUEST))
    elif case == "a contract outside the keys":
        consumed = _consumed(session, keys=frozenset({"SF-ORD-2"}))
    else:
        request_id = UUID(int=21)
    with pytest.raises(LookupError):
        activation.activate(
            _Uow(session),  # type: ignore[arg-type]
            contract_id=CONTRACT,
            approval_request_id=request_id,
            on_behalf_of=None,
            consumed=consumed,
        )


def test_consume_fresh_basis_validates_once_and_yields_the_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``engine.consume_fresh_basis``: the request must name the subject (``LookupError``
    otherwise), its basis is hashed once and a difference is ``StaleBasis`` — nothing else happens,
    so the refusal is atomic — and a fresh basis yields the composition bound to the transaction."""
    hashed: list[str] = []

    def unchanged(uow: Any, spec: Any, request: Any) -> str:
        hashed.append(str(request["subject_type"]))
        return "a" * 64

    monkeypatch.setattr(approvals_engine, "current_content_sha256", unchanged)
    session = _Session(request=IMPORT_REQUEST)
    uow = _Uow(session)
    consumed = approvals_engine.consume_fresh_basis(
        uow,  # type: ignore[arg-type]
        APPROVAL_REQUEST,
        subject_type=approvals_engine.ApprovalSubjectType.IMPORT_COMMIT,
        subject_id=UUID(int=20),
        keys=["SF-ORD-1", "SF-ORD-2"],
        bases={"SF-ORD-1": 3, "SF-ORD-2": None},  # the approved heads; None = expected absence
    )
    assert hashed == ["IMPORT_COMMIT"]
    assert consumed.keys == frozenset({"SF-ORD-1", "SF-ORD-2"}) and consumed.session is session
    assert dict(consumed.bases) == {"SF-ORD-1": 3, "SF-ORD-2": None}
    assert consumed.covers(uow, key="SF-ORD-1", approval_request_id=APPROVAL_REQUEST)  # type: ignore[arg-type]
    assert not consumed.covers(uow, key="SF-ORD-9", approval_request_id=APPROVAL_REQUEST)  # type: ignore[arg-type]
    with pytest.raises(LookupError):  # a request for another subject is not this consumption
        approvals_engine.consume_fresh_basis(
            uow,  # type: ignore[arg-type]
            APPROVAL_REQUEST,
            subject_type=approvals_engine.ApprovalSubjectType.CONTRACT_ACTIVATION,
            subject_id=CONTRACT,
            keys=[],
        )
    monkeypatch.setattr(
        approvals_engine, "current_content_sha256", lambda uow, spec, request: "b" * 64
    )
    with pytest.raises(approvals_engine.StaleBasis):
        approvals_engine.consume_fresh_basis(
            uow,  # type: ignore[arg-type]
            APPROVAL_REQUEST,
            subject_type=approvals_engine.ApprovalSubjectType.IMPORT_COMMIT,
            subject_id=UUID(int=20),
            keys=["SF-ORD-1"],
        )


def test_lock_groups_then_contracts_takes_every_group_before_every_contract() -> None:
    """``locking.lock_groups_then_contracts`` (the import's consumption locks): groups ascending,
    then contracts ascending, equality re-verified; an empty set locks nothing."""
    session = _Session(stop=False)
    rows = locking.lock_groups_then_contracts(session, [UUID(int=8), CONTRACT])  # type: ignore[arg-type]
    assert session.calls == [
        ("contract", False),
        ("combination_group", True),
        ("contract", True),
        ("contract", True),
    ]
    assert set(rows) == {CONTRACT, UUID(int=8)} and session.locked_groups == [GROUP]
    assert locking.lock_groups_then_contracts(_Session(), []) == {}  # type: ignore[arg-type]
    with pytest.raises(Problem) as refused:
        locking.lock_groups_then_contracts(_Session(regroup=True, stop=False), [CONTRACT])  # type: ignore[arg-type]
    assert refused.value.slug == "precondition-failed"


# --- P5-LOCK-R4: the cross-group schedule (Codex's OPEN residual of 101c) -------------------------
# Members in DISTINCT groups; the target below, between or above them. Every unit of work's FOR
# UPDATE set is asserted as an EXACT list: one globally ascending id order, the target included and
# taken first only when its id is the lowest (DG-KRN-DB-08 rev 1.36; D-98 candidate 101c).

X, Y = UUID(int=21), UUID(int=22)  # two members, ascending contract ids (read in the order Y, X)
GX, GY = UUID(int=32), UUID(int=34)  # their groups
T_LOWEST, T_BETWEEN, T_HIGHEST = UUID(int=31), UUID(int=33), UUID(int=35)
TARGETS = [T_LOWEST, T_BETWEEN, T_HIGHEST]
TARGET_IDS = ["target-lowest", "target-between", "target-highest"]
# A leave from T_BETWEEN: the members' singletons both below, around, or both above the target.
SINGLETON_PAIRS = [
    (UUID(int=31), UUID(int=32)),
    (UUID(int=32), UUID(int=34)),
    (UUID(int=34), UUID(int=35)),
]
SINGLETON_IDS = ["singletons-below", "singletons-around", "singletons-above"]


def _member(contract_id: UUID, group_id: UUID) -> dict[str, Any]:
    return {
        **CONTRACT_ROW,
        "id": contract_id,
        "combination_group_id": group_id,
        "contract_no": f"C-{contract_id.int}",
        "external_id": f"SF-ORD-{contract_id.int}",
    }


def _record(action: Literal["JOIN", "LEAVE"], status: str) -> dict[str, Any]:
    """A COMBINATION proposal record naming Y before X: the locks must still sort the contracts."""
    return {
        **RECORD_ROW,
        "status": status,
        "questionnaire": {"action": action, "contract_ids": [str(Y), str(X)]},
    }


def _code_bound(statement: Any) -> str | None:
    """The ``code`` literal of a WHERE clause list — the leave's singleton lookup by group code."""
    where = getattr(statement, "whereclause", None)
    for clause in getattr(where, "clauses", ()):
        if getattr(getattr(clause, "left", None), "name", None) == "code":
            return str(clause.right.value)
    return None


def _stop(*args: Any, **kwargs: Any) -> None:
    raise _Stop


class _CrossGroupSession(_Session):
    """Members in DISTINCT groups. ``contracts``: each member's row by id — its own group and
    contract number — answering the unlocked and the locked contract reads (one id or ``IN``);
    ``singletons``: the leave's singleton group by code; every member group answers ``is_singleton``
    True so the JOIN paths run on to their locks. Records ``locked_groups`` (as ``_Session``) and
    ``locked_contracts``; ``stop_at_contract_lock`` ends a single-contract path there."""

    def __init__(
        self,
        contracts: Mapping[UUID, Mapping[str, Any]],
        *,
        singletons: Mapping[str, UUID] | None = None,
        record: dict[str, Any] | None = None,
        stop_at_contract_lock: bool = False,
    ) -> None:
        super().__init__(stop=False, record=record)
        self.contracts = {cid: dict(row) for cid, row in contracts.items()}
        self.singletons = dict(singletons or {})
        self.locked_contracts: list[UUID] = []
        self.stop_at_contract_lock = stop_at_contract_lock

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        froms = (
            statement.get_final_froms()
            if hasattr(statement, "get_final_froms")
            else [statement.table]
        )
        table = getattr(froms[0], "name", "join")
        locked = getattr(statement, "_for_update_arg", None) is not None
        if table == "contract":
            self.calls.append((table, locked))
            bound = _bound(statement)
            if isinstance(bound, list):
                return _Result(
                    rows=[
                        SimpleNamespace(
                            id=value,
                            combination_group_id=self.contracts[value]["combination_group_id"],
                        )
                        for value in bound
                    ]
                )
            row = self.contracts[bound]  # KeyError: a contract the case did not declare
            if locked:
                self.locked_contracts.append(bound)
                if self.stop_at_contract_lock:
                    raise _Stop
            return _Result(scalar=row["combination_group_id"], row=dict(row))
        if table == "combination_group" and not locked:
            code = _code_bound(statement)
            if code is not None:
                return _Result(scalar=self.singletons[code], row={"id": self.singletons[code]})
            bound = _bound(statement)
            member_groups = {row["combination_group_id"] for row in self.contracts.values()}
            singleton = bound in member_groups
            return _Result(
                scalar=singleton, row={**GROUP_ROW, "id": bound, "is_singleton": singleton}
            )
        return super().execute(statement, *args, **kwargs)


def _two_groups(**kwargs: Any) -> _CrossGroupSession:
    return _CrossGroupSession({X: _member(X, GX), Y: _member(Y, GY)}, **kwargs)


def _between_recorder(session: _CrossGroupSession, seen: list[tuple[list[Any], list[UUID]]]) -> Any:
    """Records, when ``between`` runs, the groups locked so far and the contracts locked so far."""
    return lambda groups: seen.append((list(session.locked_groups), list(session.locked_contracts)))


def _assert_one_order(
    session: _CrossGroupSession, touched: Iterable[UUID], *, target: UUID | None = None
) -> None:
    expected = sorted(set(touched))
    assert session.locked_groups == expected, (session.locked_groups, expected)
    assert session.locked_contracts == [X, Y], session.locked_contracts
    if target is not None:  # the target is taken first only when its id is the lowest
        assert (session.locked_groups[0] == target) is (target == expected[0])
    # every group lock precedes every contract lock
    first_contract_lock = session.calls.index(("contract", True))
    assert ("combination_group", True) not in session.calls[first_contract_lock:]


@pytest.mark.parametrize("target", TARGETS, ids=TARGET_IDS)
def test_lock_step_sorts_the_target_among_members_from_two_groups(target: UUID) -> None:
    """``combination._lock_groups_then_contracts`` with members in two DIFFERENT groups: the exact
    order is ``sorted({target, GX, GY})`` wherever the target's id falls; ``between`` runs after all
    three group locks and before the first contract lock; the contracts follow ascending."""
    session = _two_groups()
    seen: list[tuple[list[Any], list[UUID]]] = []
    groups, rows = combination._lock_groups_then_contracts(
        session,  # type: ignore[arg-type]
        group_ids=[target],
        expected={Y: GY, X: GX},
        between=_between_recorder(session, seen),
    )
    _assert_one_order(session, [target, GX, GY], target=target)
    assert seen == [(sorted([target, GX, GY]), [])]
    assert list(groups) == sorted([target, GX, GY]) and [row["id"] for row in rows] == [X, Y]


@pytest.mark.parametrize("target", TARGETS, ids=TARGET_IDS)
def test_submit_step_sorts_the_target_among_members_from_two_groups(
    target: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``combination._visible_contracts(target=)`` — the submit's lock step — with members from two
    groups, read in the order Y, X: groups ``sorted({target, GX, GY})``, contracts ``[X, Y]``."""
    monkeypatch.setattr(combination, "require_for_entity", lambda ctx, permission, entity_id: None)
    session = _two_groups()
    seen: list[tuple[list[Any], list[UUID]]] = []
    combination._visible_contracts(
        _Uow(session),  # type: ignore[arg-type]
        [Y, X],
        target=target,
        between=_between_recorder(session, seen),
    )
    _assert_one_order(session, [target, GX, GY], target=target)
    assert seen == [(sorted([target, GX, GY]), [])]


@pytest.mark.parametrize("target", TARGETS, ids=TARGET_IDS)
def test_apply_join_step_sorts_the_target_among_members_from_two_groups(target: UUID) -> None:
    """``combination._lock_members`` for a JOIN of X (in GX) and Y (in GY) into ``target``."""
    session = _two_groups()
    proposal = combination._Proposal(
        record_id=RECORD, action="JOIN", contract_ids=(Y, X), status=JudgementStatus.SUBMITTED
    )
    groups, rows, singletons = combination._lock_members(
        session,  # type: ignore[arg-type]
        group_id=target,
        proposal=proposal,
    )
    _assert_one_order(session, [target, GX, GY], target=target)
    assert list(groups) == sorted([target, GX, GY]) and singletons == {}
    assert [row["id"] for row in rows] == [X, Y]  # by external id — SF-ORD-21 before SF-ORD-22


@pytest.mark.parametrize(("first", "second"), SINGLETON_PAIRS, ids=SINGLETON_IDS)
def test_apply_leave_step_sorts_the_target_among_the_singletons(first: UUID, second: UUID) -> None:
    """``combination._lock_members`` for a LEAVE of X and Y from ``T_BETWEEN`` into their singletons
    (looked up by group code, unlocked): ``sorted({T_BETWEEN, SX, SY})`` whether both singletons sit
    below the target, around it, or above it."""
    codes = {
        f"{combination.GROUP_PREFIX}C-{X.int}": first,
        f"{combination.GROUP_PREFIX}C-{Y.int}": second,
    }
    session = _CrossGroupSession(
        {X: _member(X, T_BETWEEN), Y: _member(Y, T_BETWEEN)}, singletons=codes
    )
    proposal = combination._Proposal(
        record_id=RECORD, action="LEAVE", contract_ids=(Y, X), status=JudgementStatus.SUBMITTED
    )
    groups, rows, singletons = combination._lock_members(
        session,  # type: ignore[arg-type]
        group_id=T_BETWEEN,
        proposal=proposal,
    )
    _assert_one_order(session, [T_BETWEEN, first, second], target=T_BETWEEN)
    assert list(groups) == sorted({T_BETWEEN, first, second})
    assert singletons == {X: first, Y: second} and [row["id"] for row in rows] == [X, Y]


def test_import_consumption_locks_two_groups_ascending_then_the_contracts() -> None:
    """``locking.lock_groups_then_contracts`` over contracts of two groups (the import's
    consumption step): ``[GX, GY]`` then ``[X, Y]`` — asked for in the order Y, X."""
    session = _two_groups()
    rows = locking.lock_groups_then_contracts(session, [Y, X])  # type: ignore[arg-type]
    _assert_one_order(session, [GX, GY])
    assert list(rows) == [X, Y]


@pytest.mark.parametrize("target", TARGETS, ids=TARGET_IDS)
def test_submit_group_entry_path_never_takes_the_target_first(
    target: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``submit_group`` (JOIN branch) from its entry: the group is previewed WITHOUT a lock, then
    the lock step takes ``sorted({target, GX, GY})`` — the target first only when it is the lowest
    id — then the proposal record (``between``), then ``[X, Y]``; stopped at ``_member_errors``,
    the first statement after the locks. Pre-101c ``submit_group`` locked the target before
    ``_visible_contracts`` (target first for every position but the lowest)."""
    monkeypatch.setattr(combination, "require_for_entity", lambda ctx, permission, entity_id: None)
    monkeypatch.setattr(combination, "_member_errors", _stop)
    session = _two_groups(record=_record("JOIN", "DRAFT"))
    body = SimpleNamespace(leave_contract_ids=None, reason_code=None, comment=None)
    with pytest.raises(_Stop):
        combination.submit_group(_Uow(session), group_id=target, body=body)  # type: ignore[arg-type]
    _assert_one_order(session, [target, GX, GY], target=target)
    assert session.calls[0] == ("judgement_record", False) or session.calls[0] == (
        "contract",
        False,
    )
    assert ("judgement_record", True) in session.calls  # the proposal record, between the tiers
    record_lock = session.calls.index(("judgement_record", True))
    assert session.calls[record_lock + 1 :] == [("contract", True), ("contract", True)]


@pytest.mark.parametrize("target", TARGETS, ids=TARGET_IDS)
def test_apply_combination_join_entry_path_never_takes_the_target_first(
    target: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``apply_combination`` (JOIN) from its entry to its basis revalidation: no lock before the
    lock step; ``sorted({target, GX, GY})``; the record between; ``[X, Y]``; stopped at
    ``assert_fresh_basis`` — the first call after the locks."""
    monkeypatch.setattr(approvals_engine, "assert_fresh_basis", _stop)
    session = _two_groups(record=_record("JOIN", "SUBMITTED"))
    with pytest.raises(_Stop):
        combination.apply_combination(_Uow(session), target, APPROVAL_REQUEST)  # type: ignore[arg-type]
    _assert_one_order(session, [target, GX, GY], target=target)
    record_lock = session.calls.index(("judgement_record", True))
    assert session.calls[record_lock + 1 :] == [("contract", True), ("contract", True)]


@pytest.mark.parametrize(("first", "second"), SINGLETON_PAIRS, ids=SINGLETON_IDS)
def test_apply_combination_leave_entry_path_sorts_the_singletons_with_the_target(
    first: UUID, second: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``apply_combination`` (LEAVE from ``T_BETWEEN``) from its entry: the singletons are looked up
    by code WITHOUT locks, then ``sorted({T_BETWEEN, SX, SY})``, the record, ``[X, Y]``."""
    monkeypatch.setattr(approvals_engine, "assert_fresh_basis", _stop)
    codes = {
        f"{combination.GROUP_PREFIX}C-{X.int}": first,
        f"{combination.GROUP_PREFIX}C-{Y.int}": second,
    }
    session = _CrossGroupSession(
        {X: _member(X, T_BETWEEN), Y: _member(Y, T_BETWEEN)},
        singletons=codes,
        record=_record("LEAVE", "SUBMITTED"),
    )
    with pytest.raises(_Stop):
        combination.apply_combination(_Uow(session), T_BETWEEN, APPROVAL_REQUEST)  # type: ignore[arg-type]
    _assert_one_order(session, [T_BETWEEN, first, second], target=T_BETWEEN)


def test_create_group_entry_path_locks_the_members_groups_ascending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``create_group`` (no target yet: the group row is inserted after the locks) with members
    from two groups named Y, X: ``[GX, GY]`` then ``[X, Y]``; stopped at ``_member_errors``."""
    monkeypatch.setattr(combination, "require_for_entity", lambda ctx, permission, entity_id: None)
    monkeypatch.setattr(combination, "_member_errors", _stop)
    session = _two_groups()
    body = SimpleNamespace(contract_ids=[Y, X], criterion="25_9_B", rationale="One package.")
    with pytest.raises(_Stop):
        combination.create_group(_Uow(session), body=body)  # type: ignore[arg-type]
    _assert_one_order(session, [GX, GY])


def _consistent(first: list[UUID], second: list[UUID]) -> bool:
    """Two lock sequences agree on the relative order of every row they share."""
    shared = set(first) & set(second)
    return [row for row in first if row in shared] == [row for row in second if row in shared]


def test_every_unit_of_work_is_a_chain_of_the_one_global_order() -> None:
    """The schedule proof (Codex's residual: "target-first cross-group order"). The lock sequences
    of the enumerated units of work — two proposals over the SAME two singletons with their targets
    on OPPOSITE sides (``[T_LOWEST, GX, GY]`` vs ``[GX, GY, T_HIGHEST]``), a leave, an import's
    consumption, a submit, and a single-group append — are each ascending and pairwise consistent
    on their shared rows: no two of them can take two shared rows in opposite orders, so no cycle
    over ``combination_group`` rows exists among these paths."""
    sequences: dict[str, list[UUID]] = {}

    def join(name: str, target: UUID) -> None:
        session = _two_groups()
        proposal = combination._Proposal(
            record_id=RECORD, action="JOIN", contract_ids=(Y, X), status=JudgementStatus.SUBMITTED
        )
        combination._lock_members(session, group_id=target, proposal=proposal)  # type: ignore[arg-type]
        sequences[name] = list(session.locked_groups)

    join("proposal T_LOWEST over X, Y", T_LOWEST)
    join("proposal T_HIGHEST over X, Y", T_HIGHEST)
    session = _CrossGroupSession(
        {X: _member(X, T_BETWEEN), Y: _member(Y, T_BETWEEN)},
        singletons={
            f"{combination.GROUP_PREFIX}C-{X.int}": GX,
            f"{combination.GROUP_PREFIX}C-{Y.int}": GY,
        },
    )
    combination._lock_members(
        session,  # type: ignore[arg-type]
        group_id=T_BETWEEN,
        proposal=combination._Proposal(
            record_id=RECORD, action="LEAVE", contract_ids=(Y, X), status=JudgementStatus.SUBMITTED
        ),
    )
    sequences["leave from T_BETWEEN"] = list(session.locked_groups)
    session = _two_groups()
    locking.lock_groups_then_contracts(session, [Y, X])  # type: ignore[arg-type]
    sequences["import consumption of X, Y"] = list(session.locked_groups)
    session = _two_groups(stop_at_contract_lock=True)
    with pytest.raises(_Stop):
        locking.lock_group_then_contract(session, X)  # type: ignore[arg-type]
    sequences["append on X"] = list(session.locked_groups)

    assert sequences["proposal T_LOWEST over X, Y"] == [T_LOWEST, GX, GY]
    assert sequences["proposal T_HIGHEST over X, Y"] == [GX, GY, T_HIGHEST]
    assert sequences["leave from T_BETWEEN"] == [GX, T_BETWEEN, GY]
    assert sequences["import consumption of X, Y"] == [GX, GY]
    assert sequences["append on X"] == [GX]
    for name, sequence in sequences.items():
        assert sequence == sorted(sequence), name
    pairs = [(a, b) for a in sequences for b in sequences if a < b]
    assert pairs and all(_consistent(sequences[a], sequences[b]) for a, b in pairs), [
        (a, b) for a, b in pairs if not _consistent(sequences[a], sequences[b])
    ]
