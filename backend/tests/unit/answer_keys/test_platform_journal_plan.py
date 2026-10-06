"""The journal run of a journals block (dev-guide DG-AK-41; item AK-JOURNAL-RUN-PLAN-1).

One run journalises a seal (04 DB-16: the runs of every mode count for one entity, book and
period), and a run's cutoff is compared with the instant its seals were written at — the
application clock's (``summarise.covered_to``). So a journals block is answered by a step of the
plan where the checkpoint stands in the timeline: it reads the run that stands when that run is
the period's whole journal in the block's form, and else cancels what stands, latest first, and
creates the block's own, which the runner works. No database here: the step's call and its
conversion, what the step reads, sends and keeps, what a refusal of the product does to the key,
and the step on each platform. The plan's side is in ``test_platform_plan.py``, the checkpoint's
read in ``test_platform_workspace_reads.py``, the runs against the product in
``tests/domain/answer_keys/test_platform_journal_plan_db.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from fractions import Fraction
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import Principal
from erev_api.clock import FrozenClock
from erev_api.domain.journals import commands
from erev_api.enums import BookCode, JournalRunGrain, JournalRunMode, PrincipalKind
from erev_api.jobs import registry
from erev_api.problems import Problem
from erev_api.schemas.journals import JournalRunCancelIn, JournalRunCreateIn
from support.answer_keys.platform_plan import (
    CLOSE,
    JOURNAL,
    PLATFORM_KEY_IDS,
    PREPARER,
    H,
    Step,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import (
    COMPARED,
    EXECUTED,
    DbPlatform,
    InMemoryPlatform,
    JournalLine,
    MockAdapter,
    NotProvisioned,
    run_platform,
)
from support.answer_keys.request_models import MockResolver, adapt
from support.answer_keys.workspace_adapter import (
    CANCEL_REASON,
    Call,
    JournalAnswer,
    JournalRunFailed,
    WorkspaceAdapter,
    real_invoker,
    standing_answer,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
START = datetime(2022, 12, 31, 12, tzinfo=UTC)
TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/journal-plan/tenant")
GRAIN = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"
PER_CONTRACT = "CONTRACT_ACCOUNT_DIMENSIONS"
# GT07's close run follows item 13 one second after its noon; the journal runs take that instant.
AT = datetime(2023, 1, 31, 17, 0, 9, tzinfo=UTC)


def uid(*parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, "erev://answer-keys/journal-plan/" + "/".join(map(str, parts)))


def _steps() -> dict[str, Step]:
    """GT07's four journal steps, by "<entity> <mode>"."""
    return {
        f"{step.detail['entity']} {step.detail['mode']}": step
        for step in plan(load_platform_key(DLT)).steps_of(JOURNAL)
    }


def _preparer(permissions: frozenset[str] | None = None) -> Principal:
    """The preparer as the API resolves a revenue accountant, or with ``permissions`` alone."""
    granted = DEFAULT_ROLES["revenue_accountant"] if permissions is None else permissions
    return Principal(
        kind=PrincipalKind.USER,
        id=uid("preparer"),
        tenant_id=TENANT,
        membership_id=uid("membership"),
        display_name="Ak Preparer",
        roles=("revenue_accountant",),
        permissions=frozenset(granted),
        permission_scopes={},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def _run(number: int, mode: str = "GROSS", **columns: Any) -> dict[str, Any]:
    """A ``journal_run`` row as the step reads it: draft, the whole primary range 0 to 3."""
    row: dict[str, Any] = {
        "id": uid("run", number),
        "run_no": f"JR-{number:06d}",
        "state": "draft",
        "mode": mode,
        "grain": GRAIN,
        "from_chain_seq": 0,
        "to_chain_seq": 3,
        "delta_from_chain_seq": 0 if mode == "DELTA" else None,
        "delta_to_chain_seq": 0 if mode == "DELTA" else None,
    }
    return {**row, **columns}


def test_the_journal_step_is_one_call_of_the_products_command() -> None:
    """The step is ``POST /journal-runs`` by the preparer: the adapter derives one call of
    ``create_run`` naming the block's entity, period, mode and grain and its checkpoint, and the
    conversion builds API-S-JournalRunCreate from it — in the key's primary book, the book the
    oracle's journals are of, the enums as enums (CONV-1) — WITHOUT a cutoff: the command then
    takes the clock of the step."""
    loaded = load_platform_key(DLT)
    steps = _steps()
    assert list(steps) == ["ME1 GROSS", "ME1 DELTA", "ME2 GROSS", "ME2 DELTA"]
    for name, step in steps.items():
        entity, mode = name.split(" ")
        call = WorkspaceAdapter(loaded).plan_call(step)
        assert call == Call(
            "erev_api.domain.journals.commands.create_run",
            PREPARER,
            {
                "subject": f"journals {entity} FY2023-P01 {mode}",
                "entity": entity,
                "period_key": "FY2023-P01",
                "mode": mode,
                "grain": GRAIN,
                "checkpoint": "asc606-january",
            },
            step,
        ), name
        (sent,) = adapt(call, loaded.key, MockResolver(DLT))
        assert sent == {
            "body": JournalRunCreateIn(
                entity_code=entity,
                book=BookCode.ASC606,
                period_key="FY2023-P01",
                mode=JournalRunMode(mode),
                grain=JournalRunGrain(GRAIN),
            )
        }, name
        body = sent["body"]
        assert body.cutoff_known_at is None and body.close_run_id is None
        assert (body.book, body.mode) == (BookCode.ASC606, JournalRunMode(mode))


def test_a_block_reads_the_run_that_stands_only_when_it_is_the_periods_journal_in_its_form() -> (
    None
):
    """``standing_answer``: the standing runs of the block's entity, book and period, oldest
    first, with the last seal of the book and of the LEGACY book. One run answers the block when
    it is the only one, has the block's mode and grain, starts at the first seal and ends at the
    last: the whole journal of the period as it is now, in the block's form — the close run's own
    draft run right after the close run. Anything else is replaced."""
    gross = _run(2)

    def answer(standing: list[dict[str, Any]], mode: str = "GROSS", **given: Any) -> object:
        facts: dict[str, Any] = {"grain": GRAIN, "sealed_to": 3, "legacy_to": 0, **given}
        return standing_answer(standing, mode=mode, **facts)

    assert answer([gross]) is gross
    assert answer([]) is None  # nothing stands: the block's run is created
    assert answer([gross], mode="DELTA") is None  # another mode
    assert answer([gross], grain=PER_CONTRACT) is None  # another grain
    assert answer([gross], sealed_to=4) is None  # something was sealed since the run
    assert answer([_run(2, from_chain_seq=2)]) is None  # a run that continues an earlier one
    assert answer([_run(1, to_chain_seq=2), _run(2, from_chain_seq=2)]) is None  # two runs
    # … also when the later of two looks whole by itself (the earlier covered nothing): the
    # rule is "the only run that stands", and both are replaced
    assert answer([_run(1, to_chain_seq=0), _run(2)]) is None
    # a GROSS run states no LEGACY range, whatever the LEGACY book holds
    assert answer([gross], legacy_to=7) is gross
    delta = _run(3, "DELTA", delta_to_chain_seq=5)
    assert answer([delta], mode="DELTA", legacy_to=5) is delta
    assert answer([delta], mode="DELTA", legacy_to=6) is None  # a LEGACY seal since the run
    assert (
        answer(
            [_run(3, "DELTA", delta_from_chain_seq=2, delta_to_chain_seq=5)],
            mode="DELTA",
            legacy_to=5,
        )
        is None
    )


class _Product:
    """The product as the step meets it, without a database: the journal runs of one entity,
    book and period, the two commands and the worker's entry point. ``trail`` keeps the order
    of what happened; ``refuse`` names a command that answers a problem."""

    tenant_id = TENANT
    keyring = None
    files = None

    def __init__(self, *standing: dict[str, Any]) -> None:
        self.clock = FrozenClock(START)
        self.runs: list[dict[str, Any]] = [dict(row) for row in standing]
        self.trail: list[tuple[Any, ...]] = []
        self.asked: list[tuple[str, str, str]] = []
        self.refuse: dict[str, Problem] = {}
        self.leaves_no_run = False
        self._created: dict[str, Any] | None = None

    # -- the workspace
    @contextmanager
    def uow(self, principal: Principal | None = None) -> Iterator[SimpleNamespace]:
        self.trail.append(("unit of work", principal))
        yield SimpleNamespace(commit=lambda: self.trail.append(("commit", self.clock.now())))

    def rows(self, statement: object) -> list[dict[str, Any]]:
        self.trail.append(("job row read",))
        return [{"state": "FAILED", "problem": {"type": "validation-failed"}}]

    # -- the reads
    def journal_runs(self, entity: str, book: str, period_key: str) -> list[dict[str, Any]]:
        self.asked.append((entity, book, period_key))
        return [dict(row) for row in self.runs]

    def sealed_to(self, book: str) -> int:
        return 0 if book == "LEGACY" else 3

    def journal_lines(self, run_id: UUID, *, per_contract: bool) -> tuple[JournalLine, ...]:
        (row,) = [row for row in self.runs if row["id"] == run_id]
        self.trail.append(("lines read", row["run_no"], per_contract))
        return (JournalLine(f"of {row['run_no']}", Fraction(1), "USD", None),)

    # -- the product's commands and its worker
    def create_run(self, uow: object, body: JournalRunCreateIn) -> tuple[UUID, SimpleNamespace]:
        if "create" in self.refuse:
            raise self.refuse["create"]
        number = len(self.runs) + 1
        assert body.mode is not None and body.grain is not None
        self._created = _run(number, body.mode.value, grain=body.grain.value)
        self.trail.append(("create", body, self.clock.now()))
        return self._created["id"], SimpleNamespace(id=uid("job", number))

    def cancel_run(self, uow: object, run_id: UUID, body: JournalRunCancelIn) -> None:
        (row,) = [row for row in self.runs if row["id"] == run_id]
        if "cancel" in self.refuse:
            raise self.refuse["cancel"]
        row["state"] = "cancelled"
        self.trail.append(("cancel", row["run_no"], body.reason))

    def run_job(self, job_id: UUID, tenant_id: UUID, *, attempt: int, runtime: Any) -> None:
        assert (tenant_id, attempt) == (TENANT, 1) and runtime.clock is self.clock
        self.trail.append(("job", job_id))
        if self._created is not None and not self.leaves_no_run:
            self.runs.append(self._created)


def _wired(monkeypatch: pytest.MonkeyPatch, product: _Product) -> None:
    monkeypatch.setattr(commands, "create_run", product.create_run)
    monkeypatch.setattr(commands, "cancel_run", product.cancel_run)
    monkeypatch.setattr(registry, "run_job", product.run_job)


def _answer(product: _Product, step: Step, principal: Principal | None = None) -> JournalAnswer:
    loaded = load_platform_key(DLT)
    call = WorkspaceAdapter(loaded).plan_call(step)
    assert call is not None
    acting = _preparer() if principal is None else principal
    answer = real_invoker(product, loaded.key, [], {PREPARER: acting}, product)(call)  # type: ignore[arg-type]
    assert isinstance(answer, JournalAnswer)
    return answer


def test_the_step_reads_the_run_that_stands_or_cancels_it_and_creates_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GT07's two blocks of ME2, after the close run the plan ran. The close run's own draft run
    is GROSS in the block's grain and ends at the last seal: the GROSS block READS it — no
    command is sent — and keeps its lines. The DELTA block cannot use it: the run is cancelled,
    as the preparer and with the plan's reason, the DELTA run is created at the step's
    application instant without a cutoff, its job is worked by the runner, and its lines are
    read at once. Each answer names the run, how it came and what was cancelled for it."""
    steps = _steps()
    own = _run(1)  # the close run's own
    product = _Product(own)
    _wired(monkeypatch, product)
    preparer = _preparer()
    assert "journal.run" in preparer.permissions

    read = _answer(product, steps["ME2 GROSS"], preparer)
    assert read == JournalAnswer(
        own["id"], True, (), (JournalLine("of JR-000001", Fraction(1), "USD", None),)
    )
    assert product.asked == [("ME2", "ASC606", "FY2023-P01")]
    assert product.trail == [("lines read", "JR-000001", False)]
    assert product.clock.now() == AT  # the step's clock: the close run's instant

    product.trail.clear()
    created = _answer(product, steps["ME2 DELTA"], preparer)
    delta = uid("run", 2)
    assert created == JournalAnswer(
        delta, False, (own["id"],), (JournalLine("of JR-000002", Fraction(1), "USD", None),)
    )
    body = JournalRunCreateIn(
        entity_code="ME2",
        book=BookCode.ASC606,
        period_key="FY2023-P01",
        mode=JournalRunMode.DELTA,
        grain=JournalRunGrain(GRAIN),
    )
    assert product.trail == [
        ("unit of work", preparer),
        ("cancel", "JR-000001", CANCEL_REASON),
        ("commit", AT),
        ("unit of work", preparer),
        ("create", body, AT),
        ("commit", AT),
        ("job", uid("job", 2)),
        ("lines read", "JR-000002", False),
    ]
    assert [(row["run_no"], row["state"], row["mode"]) for row in product.runs] == [
        ("JR-000001", "cancelled", "GROSS"),
        ("JR-000002", "draft", "DELTA"),
    ]


def test_the_step_cancels_every_standing_run_latest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """GT07's two blocks of ME1, for which the plan runs no close run, and a period that holds
    two standing runs. With nothing standing the first block's run is created. The second block
    cancels it and creates its own. And where two runs stand — the second continues the first
    — neither is the period's journal: both are cancelled, the LATEST first, as the product
    demands (ruling R-52 (b)), and the block's run starts at the first seal again."""
    steps = _steps()
    product = _Product()
    _wired(monkeypatch, product)
    first = _answer(product, steps["ME1 GROSS"])
    assert (first.read, first.cancelled, first.run_id) == (False, (), uid("run", 1))
    second = _answer(product, steps["ME1 DELTA"])
    assert (second.read, second.cancelled, second.run_id) == (
        False,
        (uid("run", 1),),
        uid("run", 2),
    )
    assert [name for name, *_ in product.trail if name in ("cancel", "create")] == [
        "create",
        "cancel",
        "create",
    ]
    # two standing runs, the second a continuation of the first
    continued = _Product(_run(1, to_chain_seq=2), _run(2, from_chain_seq=2))
    _wired(monkeypatch, continued)
    answer = _answer(continued, steps["ME1 GROSS"])
    assert answer.cancelled == (uid("run", 2), uid("run", 1)) and answer.read is False
    assert [entry[1] for entry in continued.trail if entry[0] == "cancel"] == [
        "JR-000002",
        "JR-000001",
    ]
    assert [(row["run_no"], row["state"]) for row in continued.runs] == [
        ("JR-000001", "cancelled"),
        ("JR-000002", "cancelled"),
        ("JR-000003", "draft"),
    ]
    # a cancelled run stands for nothing: a block of its mode and grain creates its own
    again = _Product(_run(1, state="cancelled"))
    _wired(monkeypatch, again)
    fresh = _answer(again, steps["ME1 GROSS"])
    assert (fresh.read, fresh.cancelled, fresh.run_id) == (False, (), uid("run", 2))


def test_what_the_product_refuses_fails_the_key_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The product was asked for a journal run and did not give it: the key fails with the
    block and what the product answered — a cancel it refuses, a create it refuses, a
    calculation that leaves no draft run. Never a step "not run": nothing of the plan refused
    it. A preparer without ``journal.run`` is the plan's own refusal (ACT-2), and nothing is
    sent."""
    steps = _steps()
    where = "JOURNAL journals ME2 FY2023-P01 DELTA"
    later = Problem("invalid-transition", "Journal run JR-000009 was calculated after this run.")
    held = _Product(_run(1))
    held.refuse["cancel"] = later
    _wired(monkeypatch, held)
    with pytest.raises(JournalRunFailed) as cancel:
        _answer(held, steps["ME2 DELTA"])
    assert str(cancel.value) == (
        f"{where}: the cancel of journal run JR-000001 (draft) was refused: "
        "invalid-transition: Journal run JR-000009 was calculated after this run."
    )
    assert isinstance(cancel.value, AssertionError)
    assert not isinstance(cancel.value, NotProvisioned)
    assert not [entry for entry in held.trail if entry[0] in ("create", "job")]

    closed = _Product(_run(1))
    closed.refuse["create"] = Problem("period-closed", "January 2023 is closed for ME2.")
    _wired(monkeypatch, closed)
    with pytest.raises(JournalRunFailed) as create:
        _answer(closed, steps["ME2 DELTA"])
    assert str(create.value) == (
        f"{where}: the journal run was refused: period-closed: January 2023 is closed for ME2."
    )

    failing = _Product(_run(1))
    failing.leaves_no_run = True
    _wired(monkeypatch, failing)
    with pytest.raises(JournalRunFailed) as calculation:
        _answer(failing, steps["ME2 DELTA"])
    assert str(calculation.value) == (
        f"{where}: the calculation left no run; its job ended FAILED: "
        "{'type': 'validation-failed'}"
    )
    assert failing.trail[-1] == ("job row read",)

    # ACT-2: without the permission nothing is read, cancelled or created.
    untouched = _Product(_run(1))
    _wired(monkeypatch, untouched)
    without = _preparer(frozenset(_preparer().permissions - {"journal.run"}))
    with pytest.raises(NotProvisioned, match="lacks permission journal.run"):
        _answer(untouched, steps["ME2 DELTA"], without)
    assert (untouched.trail, untouched.asked) == ([], [])


def test_the_cancel_is_checked_against_its_own_declared_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACT-2 for the cancel the step sends: the declaration of the cancel's own route is checked
    before each cancel, as the create's is before the step. Both routes ask for ``journal.run``
    today, so the step's first check answers for both; here the cancel is declared with a code
    of its own, which the preparer does not hold: the plan refuses the step by name, and
    nothing is cancelled or created."""
    from support.answer_keys import step_permissions

    declared = step_permissions.declared

    def with_its_own_code(handler: str) -> step_permissions.StepPermission:
        found = declared(handler)
        if handler != H["journal_cancel"]:
            return found
        return step_permissions.StepPermission(
            found.kind, found.method, found.path, frozenset({"journal.cancel"})
        )

    monkeypatch.setattr(step_permissions, "declared", with_its_own_code)
    product = _Product(_run(1))
    _wired(monkeypatch, product)
    with pytest.raises(NotProvisioned, match="lacks permission journal.cancel"):
        _answer(product, _steps()["ME2 DELTA"])
    assert product.trail == []
    assert [(row["run_no"], row["state"]) for row in product.runs] == [("JR-000001", "draft")]


def test_the_journal_steps_follow_the_close_run_on_both_platforms_and_stamp_nothing() -> None:
    """On the database platform GT07's four journal steps reach the adapter right after the
    close run of item 13, in the key's order, and stamp nothing: the checkpoint keeps the stamp
    its close run took. On the in-memory platform they run nothing — the store summarises a
    block's lines from the checkpoint's posting intents — and the four blocks compare as
    before."""
    loaded = load_platform_key(DLT)
    adapter = MockAdapter(start=START)
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    journal = [item for item in result.executed if item.step.phase == JOURNAL]
    assert [(item.step.subject, item.status, item.known_at) for item in journal] == [
        ("journals ME1 FY2023-P01 GROSS", EXECUTED, None),
        ("journals ME1 FY2023-P01 DELTA", EXECUTED, None),
        ("journals ME2 FY2023-P01 GROSS", EXECUTED, None),
        ("journals ME2 FY2023-P01 DELTA", EXECUTED, None),
    ]
    (closed,) = [item for item in result.executed if item.step.phase == CLOSE]
    assert result.known_at[13] == closed.known_at
    at = adapter.calls.index((H["close_run"], "close run ME2 ASC606 FY2023-P01"))
    assert adapter.calls[at + 1 : at + 5] == [
        (H["journal_create"], item.step.subject) for item in journal
    ]
    assert adapter.calls[at + 1 :] == adapter.calls[at + 1 : at + 5]  # the plan ends with them
    memory = run_platform(loaded, InMemoryPlatform(loaded))
    unrun = [item for item in memory.executed if item.step.phase == JOURNAL]
    assert [(item.status, item.known_at) for item in unrun] == [(EXECUTED, None)] * 4
    blocks = {
        block.block: block.status
        for checkpoint in memory.checkpoints
        for block in checkpoint.blocks
        if block.block.startswith("journals")
    }
    assert blocks == {
        "journals ME1 FY2023-P01 GROSS": COMPARED,
        "journals ME1 FY2023-P01 DELTA": COMPARED,
        "journals ME2 FY2023-P01 GROSS": COMPARED,
        "journals ME2 FY2023-P01 DELTA": COMPARED,
    }
    assert memory.mismatches == ()
    # No other platform key holds a journals block: no journal step in its plan.
    for key_id in (POS_012, EX21, EX42, POS_117):
        assert plan(load_platform_key(key_id)).steps_of(JOURNAL) == ()
