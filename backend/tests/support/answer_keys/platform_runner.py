"""The platform answer-key runner behind a port (dev-guide DG-AK-41; BUILD_SPEC PRP-1 to PRP-3).

``run_platform`` executes a platform key's command plan (``platform_plan``) in order against a
``PlatformPort``, stamps ``known_at[seq]`` after each timeline item commits — the close run and
the journal runs of a checkpoint among the plan's steps, where the checkpoint stands in the
timeline — produces the report runs the checkpoints name, reads the checkpoint blocks back and
compares them. Two ports implement the interface:

- ``InMemoryPlatform`` runs without a database. Its store is the key's own world and timeline as
  the engine runner's assembler builds them; commands append to per-contract streams under a frozen
  clock set to each item's record time; the checkpoint books are computed with ``erev_engine`` at
  ``known_at[after_seq]``; ``contracts``, ``subledger``, ``groups`` and ``exceptions`` blocks
  compare through the engine runner's ``_CheckpointComparison``; ``journals`` blocks are summarised
  from the posting intents (GROSS: the primary book's lines of the run's entity and period; DELTA:
  primary plus LEGACY lines per account, D-89 L7-6-Q-8 / S14-R-23), and ``period_states`` from the
  store. ``reports`` blocks are DB-bound (report runs read persisted versions and subledger rows
  through the report framework) and are marked **not run — databases not provisioned**, as is every
  DB-only step (tenant provisioning, personas, configuration lifecycles, the domain handlers).
- ``DbPlatform`` names the domain handler every step will call and raises ``NotProvisioned`` until
  the lane's databases exist; it is selected with ``EREV_AK_PLATFORM=db``.

Outcome rule (XR-12 kept honest): a platform key is ``passed`` only when every block compared
clean on the database platform. On the in-memory platform the best outcome is ``not_run`` with
the in-memory evidence in the message and notes; any mismatch is ``failed``. The engine
comparison ``runners.assert_checkpoints`` still refuses platform results
(``PLATFORM_RUNNER_MISSING``).

The key verdict combines the run's numeric comparisons with unsupported-policy findings.
Supported overrides use creation, submission and independent approval before activation.
Unsupported declarations are omitted from the plan and always produce a named failure, even
when every numeric comparison passes. In-memory evidence never establishes a database pass.

What is not run says why in its first words (item AK-NOT-RUN-REASON-1): a step's or a block's
reason is ``not run — <its reason>``, and a key's outcome opens with the first of them. One
reason is the lane's own and keeps its name, ``not run — databases not provisioned``: there is no
database behind the platform (``NotProvisioned(..., unprovisioned=True)``) — the in-memory
platform's DB-bound steps and blocks, a database platform without its adapter, an adapter without
its invoker, clock, reads, jobs or fingerprint collector, the mock adapter's reads. A world that
lacks a step, the runner's bound, an unbuilt command and a block whose step of the plan did not
run are reasons of their own and never carry those words.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Final, Protocol, cast

import erev_engine
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine.bundle import InputBundle, PostingIntent
from erev_engine.errors import EngineError
from support.answer_keys import runners
from support.answer_keys.loader import AnswerKeyError, LoadedKey
from support.answer_keys.models import (
    AnswerKey,
    Checkpoint,
    CommandItem,
    EventItem,
    JournalBlock,
    PeriodState,
    PeriodStateItem,
    ReportBlock,
    SubledgerBlock,
)
from support.answer_keys.platform_plan import (
    COMMAND_HANDLERS,
    PERIOD_STATE_HANDLERS,
    REPORT_GAPS,
    SUPPORTED_OVERRIDES,
    CommandPlan,
    Step,
    plan,
)
from support.answer_keys.report_cells import CellMismatch, compare_block
from support.answer_keys.runners import (
    ABSENT,
    CLOSE_PASSES,
    CheckpointMismatchError,
    CheckpointRun,
    Mismatch,
    _Assembler,
    _checkpoint_run,
    _CheckpointComparison,
    _intent_contract,
    _minor_unit,
    _money_text,
    _render_expected,
    _render_net,
    population_findings,
)

__all__ = [
    "IN_MEMORY",
    "NOT_PROVISIONED",
    "NOT_RUN_LEAD",
    "BlockOutcome",
    "DbPlatform",
    "DomainAdapter",
    "MockAdapter",
    "RefusalFailed",
    "InMemoryPlatform",
    "JournalLine",
    "NotProvisioned",
    "PassBlock",
    "PlatformCheckpoint",
    "PlatformPort",
    "PlatformRunResult",
    "assert_platform_checkpoints",
    "close_runs",
    "first_not_run",
    "journal_lines",
    "journal_totals",
    "key_verdict",
    "override_finding",
    "pass_blocks",
    "platform_outcome",
    "run_platform",
    "summarise_intents",
]

NOT_RUN_LEAD: Final = "not run — "  # the first words of every reason
NOT_PROVISIONED: Final = f"{NOT_RUN_LEAD}databases not provisioned"  # of one reason alone
SUBLEDGER: Final = "subledger"
JOURNALS: Final = "journals"
IN_MEMORY: Final = "in-memory"
DB: Final = "db"
PLATFORM_ENV: Final = "EREV_AK_PLATFORM"
COMPARED: Final = "compared"
NOT_RUN: Final = "not_run"
ERROR: Final = "error"  # the engine refused the checkpoint's bundle (EngineError)
EXECUTED: Final = "executed"
FAILED_STEP: Final = "failed"  # a verified refusal that raised another code or changed state
OPEN: Final = "open"  # E-04 default of an unlisted period (dev-guide §9.5.3)
LEGACY: Final = "LEGACY"
GROSS: Final = "GROSS"
DELTA: Final = "DELTA"
JOURNAL_MODES: Final = (GROSS, DELTA)
# Unsupported declarations produce one finding at world configuration, beside numeric failures.
OVERRIDES_CHECKPOINT: Final = "world"
OVERRIDES_SUBJECT: Final = "policy overrides"
OVERRIDES_FIELD: Final = "created"
OVERRIDES_EXPECTED: Final = "{count} APPROVED at booking (dev-guide §9.5.4): {declared}"
OVERRIDES_ACTUAL: Final = (
    "not created: public authoring is unavailable for {policies} "
    "(rule id POLICY_OVERRIDE_NOT_OFFERED)"
)


class NotProvisioned(RuntimeError):
    """A step or a block that is not run, refused by name. The message opens with its own reason,
    ``not run — <step> (<handler>)``. ``unprovisioned`` marks the one reason that is the lane's:
    the databases are not provisioned — nothing stands behind the platform — and only that
    message says so (module docstring; item AK-NOT-RUN-REASON-1). The class keeps the name it had
    when that was the only reason."""

    def __init__(self, step: str, handler: str = "", *, unprovisioned: bool = False) -> None:
        self.step = step
        self.handler = handler
        self.unprovisioned = unprovisioned
        lead = f"{NOT_PROVISIONED}: " if unprovisioned else NOT_RUN_LEAD
        super().__init__(f"{lead}{step}" + (f" ({handler})" if handler else ""))


class RefusalFailed(AssertionError):
    """PLAT-1: an ``expect_problem`` step was run and verified, and the verification failed: the
    command raised another code (or none) or left changed state."""

    def __init__(self, seq: int, expected: str, actual: str, unchanged: bool) -> None:
        self.seq = seq
        self.expected = expected
        self.actual = actual
        self.unchanged = unchanged
        state = "state unchanged" if unchanged else "STATE CHANGED"
        super().__init__(f"seq {seq}: expected refusal {expected}, got {actual}; {state}")


@dataclass(frozen=True, slots=True)
class JournalLine:
    """One summarised journal line: account, signed net (debit positive) in transaction units."""

    account: str
    net: Fraction
    currency: str
    contract: str | None = None

    @property
    def side(self) -> str:
        return "dr" if self.net >= 0 else "cr"


@dataclass(frozen=True, slots=True)
class BlockOutcome:
    """One checkpoint block: compared (with its mismatches) or not run (with the reason)."""

    # "contracts" | "subledger" | "groups" | "exceptions" | "identities" |
    # "journals <entity> <period> <mode>" | "reports <code>" | "period_states" |
    # "subledger <period> <entity>[ <contract>]" (one subledger block that is not run)
    block: str
    status: str  # COMPARED | NOT_RUN | ERROR
    mismatches: tuple[Mismatch, ...] = ()
    reason: str | None = None
    detail: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlatformCheckpoint:
    name: str
    after_seq: int
    known_at: datetime
    blocks: tuple[BlockOutcome, ...]


@dataclass(frozen=True, slots=True)
class ExecutedStep:
    step: Step
    at: datetime  # the clock when the step ran
    known_at: datetime | None  # the stamp captured after the item committed (timeline items)
    status: str  # EXECUTED (on the platform named by the result) | NOT_RUN | FAILED_STEP
    reason: str | None = None  # why a step is NOT_RUN or FAILED_STEP


@dataclass(frozen=True, slots=True)
class PlatformRunResult:
    key_id: str
    runner: str  # "platform"
    platform: str  # IN_MEMORY | DB
    executed: tuple[ExecutedStep, ...]
    known_at: Mapping[int, datetime]  # seq -> stamp after commit
    checkpoints: tuple[PlatformCheckpoint, ...]
    notes: tuple[str, ...] = ()

    @property
    def mismatches(self) -> tuple[Mismatch, ...]:
        return tuple(
            mismatch
            for checkpoint in self.checkpoints
            for block in checkpoint.blocks
            for mismatch in block.mismatches
        )

    @property
    def not_run(self) -> tuple[str, ...]:
        """Every block and step not run, ``<checkpoint> <block>`` / ``step <subject>``."""
        found = [
            f"{checkpoint.name} {block.block}"
            for checkpoint in self.checkpoints
            for block in checkpoint.blocks
            if block.status == NOT_RUN
        ]
        found.extend(
            f"step {item.step.phase} {item.step.subject}"
            for item in self.executed
            if item.status == NOT_RUN
        )
        return tuple(found)

    @property
    def compared(self) -> tuple[str, ...]:
        return tuple(
            f"{checkpoint.name} {block.block}"
            for checkpoint in self.checkpoints
            for block in checkpoint.blocks
            if block.status == COMPARED
        )


# --- the port -----------------------------------------------------------------------------------


class PlatformPort(Protocol):
    """What ``run_platform`` needs from a platform."""

    name: str

    def execute(self, step: Step) -> datetime | None:
        """Run one plan step at its clock; return the stamp captured after a timeline item commits
        (``known_at[seq]``), None for steps that stamp nothing. Raises ``NotProvisioned`` when the
        step needs the database."""

    def checkpoint_run(self, checkpoint: Checkpoint) -> CheckpointRun:
        """The computed books the checkpoint reads (contracts, subledger, groups, exceptions)."""

    def journal_run(
        self, checkpoint: Checkpoint, run: CheckpointRun, block: JournalBlock
    ) -> tuple[JournalLine, ...]:
        """The summarised lines of one journal run (entity, period, mode, grain)."""

    def report_rows(
        self, checkpoint: Checkpoint, block: ReportBlock
    ) -> Sequence[Mapping[str, object]]:
        """The data rows of one report run at the checkpoint's ``known_at`` and ``as_of``."""

    def period_state(self, entity: str, book: str, period_key: str, after_seq: int) -> str | None:
        """The state of one period as of the checkpoint cutoff ``after_seq`` (PLAT-2), never the
        timeline's final state."""

    def pending_blocks(self, checkpoint: Checkpoint) -> Mapping[str, str]:
        """The blocks of the checkpoint this platform cannot witness yet, block name → the reason
        they are not run; a block named here is not compared. A subledger block is named by its
        period, entity and contract (``_subledger_name``), a journal block as everywhere."""


@dataclass(frozen=True, slots=True)
class PassBlock:
    """A block of a checkpoint whose expected figures hold a period-end pass (``pass_blocks``)."""

    name: str  # as the result names the block (``_subledger_name``, ``_journal_name``)
    kind: str  # SUBLEDGER | JOURNALS
    entity: str
    period_key: str


# (digest of the key as loaded or as a test varied it, checkpoint name) → the blocks. A plan
# asks for every checkpoint each time it is built; the answer costs two engine runs.
_PASS_BLOCKS: dict[tuple[str, str], tuple[PassBlock, ...]] = {}


def pass_blocks(loaded: LoadedKey, checkpoint: Checkpoint) -> tuple[PassBlock, ...]:
    """The blocks of ``checkpoint`` whose expected figures hold a period-end pass, in the key's
    order. The oracle computes the close-run passes with every checkpoint (``_checkpoint_run``;
    D-85); the product posts them in a close run. A block is named exactly when the oracle's own
    books answer it differently with the passes than without them: a subledger block — one period
    and entity, and its contract where it names one — by its comparison, a journal block by its
    lines. A block the passes leave as it is (another period, entity or book; lines a subset
    block does not list) is not named. A bundle the engine refuses names nothing."""
    if not (checkpoint.subledger or checkpoint.journals):
        return ()
    # the key's content, never the file's digest: a test varies a loaded key in memory
    content = hashlib.sha256(loaded.key.model_dump_json().encode()).hexdigest()
    cached = (content, checkpoint.name)
    if cached not in _PASS_BLOCKS:
        _PASS_BLOCKS[cached] = _pass_blocks(loaded, checkpoint)
    return _PASS_BLOCKS[cached]


def _pass_blocks(loaded: LoadedKey, checkpoint: Checkpoint) -> tuple[PassBlock, ...]:
    key = loaded.key
    bundles = next(
        item for item in _Assembler(loaded).checkpoints() if item.name == checkpoint.name
    )
    compute = cast(Callable[[InputBundle], object], erev_engine.compute)
    try:
        with_passes = _checkpoint_run(compute, bundles, CLOSE_PASSES)
    except EngineError:
        return ()
    without = CheckpointRun(with_passes.checkpoint, with_passes.outputs)

    def answered(run: CheckpointRun, block: SubledgerBlock) -> list[Mismatch]:
        comparison = _CheckpointComparison(key, checkpoint, run)
        comparison.subledger(block)
        return comparison.found

    found: list[PassBlock] = []
    for block in checkpoint.subledger or ():
        if answered(with_passes, block) != answered(without, block):
            found.append(
                PassBlock(_subledger_name(block), SUBLEDGER, block.entity, block.period_key)
            )
    primary = next(book for book in key.books if book != LEGACY)
    for journal in checkpoint.journals or ():
        with_lines, without_lines = (
            journal_lines(
                run,
                entity=journal.run.entity,
                period_key=journal.run.period_key,
                mode=journal.run.mode,
                primary_book=primary,
                grain=journal.run.grain,
            )
            for run in (with_passes, without)
        )
        if with_lines != without_lines:
            found.append(
                PassBlock(
                    _journal_name(journal), JOURNALS, journal.run.entity, journal.run.period_key
                )
            )
    return tuple(found)


def close_runs(loaded: LoadedKey, checkpoint: Checkpoint) -> tuple[tuple[str, str], ...]:
    """The close runs a checkpoint's blocks expect — (entity, period key), each once, in the
    order of the blocks that expect them (``pass_blocks``). The plan runs each right after the
    checkpoint's last item (``platform_plan.close_run_steps``; item AK-CLOSE-RUN-STEP-1)."""
    found: list[tuple[str, str]] = []
    for block in pass_blocks(loaded, checkpoint):
        if (block.entity, block.period_key) not in found:
            found.append((block.entity, block.period_key))
    return tuple(found)


# --- in-memory platform ---------------------------------------------------------------------------


class InMemoryPlatform:
    """The key's world and timeline as the store; the engine as the computation; no database."""

    name = IN_MEMORY

    def __init__(self, loaded: LoadedKey) -> None:
        self.loaded = loaded
        self.key: AnswerKey = loaded.key
        self.assembler = _Assembler(loaded)
        self.clock: datetime = self.assembler.setup_at
        self.log: list[tuple[datetime, Step]] = []
        self.streams: dict[str, list[int]] = {}  # contract external id -> appended seqs
        # World initial states, then every transition with the seq that made it (PLAT-2 reads
        # the latest transition at or before a checkpoint's after_seq).
        self.initial: dict[tuple[str, str, str], str] = {
            (state.entity, state.book, state.period_key): state.state
            for state in self.key.world.period_states
        }
        self.transitions: list[tuple[int, str, str, str, str]] = []
        self._runs: dict[str, CheckpointRun] = {}
        self._tenant_provisioned = False

    # -- commands --

    def execute(self, step: Step) -> datetime | None:
        if step.clock_at is not None:
            self.clock = datetime.strptime(step.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if step.gap is not None and step.phase != "RUNNER":
            raise NotProvisioned(f"{step.phase} {step.subject}", step.gap)
        self.log.append((self.clock, step))
        if step.phase in ("PROVISION", "PERSONAS", "WORLD", "CONTRACTS", "RUNNER"):
            # Configuration exists in the store by construction (the world is the key's).
            self._tenant_provisioned = True
            return None
        if step.phase == "TIMELINE":
            return self._timeline(step)
        # A close run of the plan (phase CLOSE) runs nothing here and stamps nothing: the store
        # computes the oracle's passes with every checkpoint (``checkpoint_run``). Nor does the
        # journal run of a journals block (phase JOURNAL): the store summarises a block's lines
        # from the checkpoint's posting intents (``journal_run``).
        return None

    def _timeline(self, step: Step) -> datetime | None:
        item = next((i for i in self.assembler.timeline if i.seq == step.seq), None)
        if item is None:
            return None
        if item.expect_problem is not None:
            # PLAT-1: a refusal is asserted by its expected code AND unchanged state; the in-memory
            # store has no command layer that enforces either, so the step is not run here.
            raise NotProvisioned(
                f"expected refusal seq {item.seq} {item.expect_problem.code}: the in-memory "
                "platform cannot enforce and verify the refusal (expected code + unchanged state, "
                "rule PLAT-1)",
                step.handler,
                unprovisioned=True,
            )
        if isinstance(item, EventItem):
            self.streams.setdefault(item.contract, []).append(item.seq)
        elif isinstance(item, PeriodStateItem):
            handler, gap = PERIOD_STATE_HANDLERS.get(item.state, ("", None))
            if not handler:
                raise NotProvisioned(f"period_state {item.state}", gap or "")
            self.transitions.append((item.seq, item.entity, item.book, item.period_key, item.state))
        elif isinstance(item, CommandItem):
            handlers, gap = COMMAND_HANDLERS[item.command.name]
            if not handlers:
                raise NotProvisioned(f"command {item.command.name}", gap or "")
            if item.command.name in ("journal_run",):
                pass  # journal runs are produced at the checkpoint that names them
            else:  # a built command: it runs where its handler has a database
                raise NotProvisioned(
                    f"command {item.command.name}", handlers[0], unprovisioned=True
                )
        if not step.captures_known_at:
            return None
        # DB-08: the server stamps the record time at commit; the frozen clock is the server here.
        return self.assembler.times[item.seq]

    # -- reads --

    def checkpoint_run(self, checkpoint: Checkpoint) -> CheckpointRun:
        if checkpoint.name not in self._runs:
            bundles = next(
                item for item in self.assembler.checkpoints() if item.name == checkpoint.name
            )
            compute = cast(Callable[[InputBundle], object], erev_engine.compute)
            self._runs[checkpoint.name] = _checkpoint_run(compute, bundles, CLOSE_PASSES)
        return self._runs[checkpoint.name]

    def journal_run(
        self, checkpoint: Checkpoint, run: CheckpointRun, block: JournalBlock
    ) -> tuple[JournalLine, ...]:
        primary = next(book for book in self.key.books if book != LEGACY)
        return journal_lines(
            run,
            entity=block.run.entity,
            period_key=block.run.period_key,
            mode=block.run.mode,
            primary_book=primary,
            grain=block.run.grain,
        )

    def report_rows(
        self, checkpoint: Checkpoint, block: ReportBlock
    ) -> Sequence[Mapping[str, object]]:
        gap = REPORT_GAPS.get(block.report_code)
        reason = (
            "report runs read persisted versions and subledger rows through the report framework"
        )
        raise NotProvisioned(
            f"reports {block.report_code}: {reason}" + (f"; {gap}" if gap else ""),
            "erev_api.domain.reports.framework.create_run",
            unprovisioned=True,
        )

    def period_state(self, entity: str, book: str, period_key: str, after_seq: int) -> str | None:
        """PLAT-2: the latest transition at or before ``after_seq``, else the world's initial
        state, else ``open``."""
        state = self.initial.get((entity, book, period_key), OPEN)
        for seq, an_entity, a_book, a_period, new_state in self.transitions:
            if seq <= after_seq and (an_entity, a_book, a_period) == (entity, book, period_key):
                state = new_state
        return state

    def pending_blocks(self, checkpoint: Checkpoint) -> Mapping[str, str]:
        return {}  # the store computes the oracle's passes with every checkpoint


# --- database platform (declared; every step is DB-bound) -----------------------------------------


class DomainAdapter(Protocol):
    """What ``DbPlatform`` needs from the platform under test: the domain handlers behind a unit of
    work, the server clock, and the reads. The real adapter runs over
    ``support.factories.Workspace`` on the lane's database; ``MockAdapter`` records the dispatch
    without a database (no live calls)."""

    name: str

    def run(self, step: Step) -> None:
        """Run the domain handler ``step.handler`` names with the step's detail, and commit."""

    def clock_timestamp(self) -> datetime:
        """The server clock after the last commit (DB-08; ``SELECT clock_timestamp()``)."""

    def refusal(self, step: Step, expected_code: str) -> tuple[str | None, bool]:
        """Run the command expecting a refusal: (the ``Problem`` code raised, or None when the
        command succeeded; whether the rows are unchanged afterwards) — PLAT-1 verification."""

    def checkpoint_run(self, checkpoint: Checkpoint) -> CheckpointRun:
        """The persisted books of the checkpoint at its known_at, as a ``CheckpointRun``."""

    def journal_run(self, checkpoint: Checkpoint, block: JournalBlock) -> tuple[JournalLine, ...]:
        """The lines of the journal run the plan's step of the block read or created where the
        checkpoint stands in the timeline; nothing is created at the read."""

    def report_rows(
        self, checkpoint: Checkpoint, block: ReportBlock
    ) -> Sequence[Mapping[str, object]]:
        """Create and run one report run and read its data rows."""

    def period_state(self, entity: str, book: str, period_key: str, known_at: datetime) -> str:
        """The period state as of ``known_at`` (T-CLS period_state_transition history)."""


class DbPlatform:
    """The database platform: each plan step is dispatched to the domain handler ``platform_plan``
    names through a ``DomainAdapter``; ``known_at[seq]`` is the adapter's server clock after the
    item's commit (DB-08); an ``expect_problem`` step is run through ``adapter.refusal`` and counted
    executed only when the expected code was raised and the rows are unchanged (PLAT-1), otherwise
    it fails the key. Without an adapter (the lane's databases are not provisioned) every method
    raises ``NotProvisioned`` naming the handler it will call, so the runner marks the step or block
    not run rather than stubbing it. The real adapter over ``support.factories.Workspace`` is the
    lane's next implementation slice; ``MockAdapter`` proves the dispatch contract now.

    The platform stops at the first step it refuses by name (``halted``): the steps after it are
    not run and say so, naming that step. A world that lacks a step would answer the later ones
    with refusals of the product's own, which say nothing of the key.

    A block whose expected figures hold a period-end pass is answered after the close run the
    plan runs for it (``platform_plan.close_run_steps``; the step stamps the checkpoint's
    ``known_at`` again). A journals block is answered by the journal run its own step read or
    created right after that (``platform_plan.journal_run_steps``; item AK-JOURNAL-RUN-PLAN-1):
    one run journalises a seal (04 DB-16), so the step cancels the run that stands for the
    block's entity and period — the close run's own, or an earlier block's — before it creates
    the block's, unless that run is the block's answer as it stands. ``pending_blocks`` names
    nothing: no block waits for an item."""

    name = DB

    def __init__(
        self,
        loaded: LoadedKey,
        adapter: DomainAdapter | None = None,
        factory: Callable[[LoadedKey], DomainAdapter] | None = None,
    ) -> None:
        self.loaded = loaded
        self.adapter = adapter
        self.factory = factory  # PLAT-G4-1: builds the real adapter on first use, or refuses
        self.expectations = {
            item.seq: item.expect_problem.code
            for item in loaded.key.timeline
            if item.expect_problem is not None
        }
        self.known_at: dict[int, datetime] = {}
        # The first step the platform refused by name. The steps after it are not run: a world
        # that lacks a step would answer them with refusals of its own, which say nothing of the
        # key (dev-guide DG-AK-41).
        self.halted: str | None = None

    def _adapter(self, step: str, handler: str) -> DomainAdapter:
        if self.adapter is None and self.factory is not None:
            try:
                self.adapter = self.factory(self.loaded)
            except NotProvisioned as refused:  # the same named refusal, with the factory's reason
                # No adapter could be built: whatever the factory says, no database is there.
                raise NotProvisioned(
                    f"{step}: {refused.step}", handler, unprovisioned=True
                ) from None
        if self.adapter is None:
            raise NotProvisioned(step, handler, unprovisioned=True)
        return self.adapter

    def execute(self, step: Step) -> datetime | None:
        where = f"{step.phase} {step.subject}"
        adapter = self._adapter(where, step.handler or step.gap or "")
        if self.halted is not None and step.phase != "RUNNER":
            raise NotProvisioned(f"{where}: not run after {self.halted}", step.handler)
        try:
            return self._execute(adapter, step)
        except NotProvisioned:
            command = (step.handler or "no handler").rsplit(".", 1)[-1]
            self.halted = f"{where} ({command})"
            raise

    def _execute(self, adapter: DomainAdapter, step: Step) -> datetime | None:
        if step.gap is not None and step.phase != "RUNNER":
            raise NotProvisioned(f"{step.phase} {step.subject}", step.gap)
        if step.phase == "RUNNER":
            return None
        expected = self.expectations.get(step.seq) if step.seq is not None else None
        if expected is not None:
            code, unchanged = adapter.refusal(step, expected)
            if code != expected or not unchanged:
                raise RefusalFailed(step.seq or 0, expected, code or "no refusal", unchanged)
            return None  # a verified refusal stamps nothing
        adapter.run(step)
        if not step.captures_known_at or step.seq is None:
            return None
        stamp = adapter.clock_timestamp()
        self.known_at[step.seq] = stamp
        return stamp

    def _known_at(self, checkpoint: Checkpoint) -> datetime:
        try:
            return self.known_at[checkpoint.after_seq]
        except KeyError as missing:
            raise NotProvisioned(
                f"checkpoint {checkpoint.name}: no known_at for after_seq {checkpoint.after_seq}"
            ) from missing

    def checkpoint_run(self, checkpoint: Checkpoint) -> CheckpointRun:
        adapter = self._adapter(
            f"checkpoint {checkpoint.name} reads", "erev_api.domain.contracts.queries.get_version"
        )
        self._known_at(checkpoint)
        return adapter.checkpoint_run(checkpoint)

    def journal_run(
        self, checkpoint: Checkpoint, run: CheckpointRun, block: JournalBlock
    ) -> tuple[JournalLine, ...]:
        adapter = self._adapter(
            f"journals {block.run.entity} {block.run.period_key} {block.run.mode}",
            "erev_api.domain.journals.commands.create_run",
        )
        return adapter.journal_run(checkpoint, block)

    def report_rows(
        self, checkpoint: Checkpoint, block: ReportBlock
    ) -> Sequence[Mapping[str, object]]:
        adapter = self._adapter(
            f"reports {block.report_code}", "erev_api.domain.reports.framework.create_run"
        )
        return adapter.report_rows(checkpoint, block)

    def period_state(self, entity: str, book: str, period_key: str, after_seq: int) -> str | None:
        adapter = self._adapter(
            f"period {entity} {book} {period_key}", "erev_api.domain.close.queries.period_view"
        )
        try:
            known_at = self.known_at[after_seq]
        except KeyError as missing:
            raise NotProvisioned(f"period {entity} {book} {period_key}: no known_at") from missing
        return adapter.period_state(entity, book, period_key, known_at)

    def pending_blocks(self, checkpoint: Checkpoint) -> Mapping[str, str]:
        return {}  # AK-JOURNAL-RUN-PLAN-1: the plan makes the run of every journals block


class MockAdapter:
    """A ``DomainAdapter`` that records the dispatch and answers from fixtures: no database, no
    live call. It proves the DbPlatform contract (order, stamping, PLAT-1 verification) until the
    Workspace adapter exists."""

    name = "mock"

    def __init__(
        self,
        *,
        start: datetime,
        refusals: Mapping[int, tuple[str | None, bool]] | None = None,
        states: Mapping[tuple[str, str, str], str] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []  # (handler, subject)
        self.clock = start
        self.refusals = dict(refusals or {})
        self.states = dict(states or {})

    def run(self, step: Step) -> None:
        self.calls.append((step.handler, step.subject))
        self.clock = self.clock + timedelta(seconds=1)  # the commit advances the server clock

    def clock_timestamp(self) -> datetime:
        return self.clock

    def refusal(self, step: Step, expected_code: str) -> tuple[str | None, bool]:
        self.calls.append((f"refusal:{step.handler}", step.subject))
        return self.refusals.get(step.seq or -1, (expected_code, True))

    def checkpoint_run(self, checkpoint: Checkpoint) -> CheckpointRun:
        raise NotProvisioned(
            f"checkpoint {checkpoint.name} reads", "mock adapter has no rows", unprovisioned=True
        )

    def journal_run(self, checkpoint: Checkpoint, block: JournalBlock) -> tuple[JournalLine, ...]:
        raise NotProvisioned(
            _journal_name(block), "mock adapter has no journal rows", unprovisioned=True
        )

    def report_rows(
        self, checkpoint: Checkpoint, block: ReportBlock
    ) -> Sequence[Mapping[str, object]]:
        raise NotProvisioned(
            f"reports {block.report_code}", "mock adapter has no report rows", unprovisioned=True
        )

    def period_state(self, entity: str, book: str, period_key: str, known_at: datetime) -> str:
        return self.states.get((entity, book, period_key), OPEN)


# --- journals from posting intents ----------------------------------------------------------------


def _books(run: CheckpointRun, codes: Iterable[str]) -> list[tuple[InputBundle, object]]:
    """(bundle, book) of the checkpoint outputs and close-pass outputs for ``codes``."""
    wanted = set(codes)
    found: list[tuple[InputBundle, object]] = []
    for bundle, output in zip(run.checkpoint.bundles, run.outputs, strict=True):
        found.extend((bundle, book) for book in output.books if book.book_code in wanted)
    if run.passes:
        for bundle, outputs in zip(run.checkpoint.bundles, run.passes, strict=True):
            for output in outputs:
                found.extend((bundle, book) for book in output.books if book.book_code in wanted)
    return found


def journal_lines(
    run: CheckpointRun,
    *,
    entity: str,
    period_key: str,
    mode: str,
    primary_book: str,
    grain: str,
) -> tuple[JournalLine, ...]:
    """The summarised lines of a journal run over the checkpoint's posting intents.

    ``GROSS`` (JET-02): every line of the primary book's intents posted to ``period_key`` for
    ``entity``. ``DELTA`` (JET-15; S14-R-23; D-89 L7-6-Q-8): the primary book's lines plus the
    ``LEGACY`` book's lines (the reversal of what the ERP booked). Lines net per (contract, account,
    transaction currency) through ``summarise_intents``; a grain that carries the contract
    (``LEGACY_CONTRACT_POB``, ``CONTRACT_ACCOUNT_DIMENSIONS``) keeps the contract, the entity-level
    grains net across contracts.
    """
    if mode not in JOURNAL_MODES:
        raise ValueError(f"journal mode {mode!r} is not GROSS or DELTA")
    codes = (primary_book, LEGACY) if mode == DELTA else (primary_book,)
    per_contract = grain in ("LEGACY_CONTRACT_POB", "CONTRACT_ACCOUNT_DIMENSIONS")
    entries = [
        (bundle.group.group_key, bundle.group.member_contract_keys, intent)
        for bundle, book in _books(run, codes)
        for intent in cast(Sequence[PostingIntent], getattr(book, "posting_intents", ()))
    ]
    return summarise_intents(
        entries, entity=entity, period_key=period_key, per_contract=per_contract
    )


def summarise_intents(
    entries: Iterable[tuple[str, Sequence[str], PostingIntent]],
    *,
    entity: str,
    period_key: str,
    per_contract: bool,
) -> tuple[JournalLine, ...]:
    """Net the intents of ``entity`` and ``period_key`` per (contract, account, transaction
    currency), the grain the domain journal summariser keeps (``ENTITY_BOOK_CURRENCY_PERIOD_…``;
    POL-006): amounts of different currencies never net against each other. ``entries`` are
    (group key, member contract keys, intent). Zero nets are dropped."""
    totals: dict[tuple[str | None, str, str], Fraction] = {}
    for group_key, members, intent in entries:
        if intent.entity != entity or intent.posting_period_key != period_key:
            continue
        contract = _intent_contract(intent, group_key, members) if per_contract else None
        for line in intent.lines:
            sign = 1 if line.side == "D" else -1
            amount = Fraction(line.amount_txn, 10 ** _minor_unit(line.txn_currency))
            key = (contract, line.account_code, line.txn_currency)
            totals[key] = totals.get(key, Fraction(0)) + sign * amount
    return tuple(
        JournalLine(account, net, currency, contract)
        for (contract, account, currency), net in sorted(
            totals.items(), key=lambda item: (item[0][0] or "", item[0][1], item[0][2])
        )
        if net != 0
    )


def _compare_journals(
    key: AnswerKey, checkpoint: Checkpoint, block: JournalBlock, actual: Sequence[JournalLine]
) -> list[Mismatch]:
    run = block.run
    where = f"journals {run.entity} {run.period_key} {run.mode}"
    found: list[Mismatch] = []
    by_key: dict[tuple[str | None, str], list[JournalLine]] = {}
    for line in actual:
        by_key.setdefault((line.contract, line.account), []).append(line)
    per_contract = any(line.contract is not None for line in block.lines)
    listed: set[tuple[str | None, str]] = set()
    for line in block.lines:
        contract = line.contract if per_contract else None
        listed.add((contract, line.account))
        label = f"{where} account {line.account}" + (f" {contract}" if contract else "")
        side, amount = ("dr", line.dr) if line.dr is not None else ("cr", line.cr)
        expected = _money_text(line.dr) - _money_text(line.cr)
        got = by_key.get((contract, line.account), [])
        if not got:
            found.append(
                Mismatch(key.id, checkpoint.name, label, side, _render_expected(amount), ABSENT)
            )
        elif len(got) > 1:  # one key line, several transaction currencies: never netted silently
            mixed = ", ".join(_render_net(item.net, item.currency) for item in got)
            found.append(
                Mismatch(key.id, checkpoint.name, label, side, _render_expected(amount), mixed)
            )
        elif got[0].net != expected:
            found.append(
                Mismatch(
                    key.id,
                    checkpoint.name,
                    label,
                    side,
                    _render_expected(amount),
                    _render_net(got[0].net, got[0].currency),
                )
            )
    if block.match == "exact":
        for (contract, account), lines in sorted(
            by_key.items(), key=lambda item: (item[0][0] or "", item[0][1])
        ):
            if (contract, account) not in listed:
                label = f"{where} account {account}" + (f" {contract}" if contract else "")
                for line in lines:
                    found.append(
                        Mismatch(
                            key.id,
                            checkpoint.name,
                            label,
                            "line",
                            ABSENT,
                            _render_net(line.net, line.currency),
                        )
                    )
    return found


def journal_totals(lines: Sequence[JournalLine]) -> dict[str, str]:
    """HELPER-1: one debit total, one credit total and a balance flag per transaction currency,
    each at the currency's own precision (``debits <ISO>``, ``credits <ISO>``, ``balanced <ISO>``);
    amounts of different currencies are never summed together."""
    debits: dict[str, Fraction] = {}
    credits: dict[str, Fraction] = {}
    for line in lines:
        if line.net > 0:
            debits[line.currency] = debits.get(line.currency, Fraction(0)) + line.net
        elif line.net < 0:
            credits[line.currency] = credits.get(line.currency, Fraction(0)) - line.net
    totals: dict[str, str] = {}
    for currency in sorted(set(debits) | set(credits)):
        debit = debits.get(currency, Fraction(0))
        credit = credits.get(currency, Fraction(0))
        totals[f"debits {currency}"] = _render_net(debit, currency)
        totals[f"credits {currency}"] = _render_net(-credit, currency)
        totals[f"balanced {currency}"] = str(debit == credit).lower()
    return totals


# --- the runner -----------------------------------------------------------------------------------


def _platform(loaded: LoadedKey, platform: PlatformPort | None) -> PlatformPort:
    if platform is not None:
        return platform
    if os.environ.get(PLATFORM_ENV, IN_MEMORY) == DB:
        from support.answer_keys.database_platform import database_adapter  # local: import cycle

        return DbPlatform(loaded, factory=database_adapter)  # PLAT-G4-1: the real adapter
    return InMemoryPlatform(loaded)


def run_platform(loaded: LoadedKey, platform: PlatformPort | None = None) -> PlatformRunResult:
    """Execute the key's command plan on ``platform`` and read every checkpoint block back."""
    key = loaded.key
    if key.runner != "platform":
        raise AnswerKeyError(loaded.path, "/runner", "run_platform runs keys with runner: platform")
    port = _platform(loaded, platform)
    command_plan: CommandPlan = plan(loaded)
    executed: list[ExecutedStep] = []
    known_at: dict[int, datetime] = {}
    notes = [f"platform: {port.name}"]
    for step in command_plan.steps:
        if step.phase == "CHECKPOINT":
            continue  # checkpoint reads follow below, per block
        at = (
            datetime.strptime(step.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if step.clock_at
            else datetime.min.replace(tzinfo=UTC)
        )
        try:
            stamp = port.execute(step)
        except NotProvisioned as refused:
            executed.append(ExecutedStep(step, at, None, NOT_RUN, str(refused)))
            notes.append(str(refused))
            continue
        except RefusalFailed as failed:  # PLAT-1: verified and wrong
            executed.append(ExecutedStep(step, at, None, FAILED_STEP, str(failed)))
            notes.append(str(failed))
            continue
        executed.append(ExecutedStep(step, at, stamp, EXECUTED))
        if stamp is not None and step.seq is not None:
            previous = max(known_at.values(), default=None)
            if previous is not None and stamp <= previous:
                raise AnswerKeyError(
                    loaded.path, f"/timeline/{step.seq}", "known_at is not strictly increasing"
                )
            known_at[step.seq] = stamp
    findings = population_findings(loaded)
    checkpoints = tuple(
        _checkpoint(key, port, checkpoint, known_at, findings) for checkpoint in key.checkpoints
    )
    return PlatformRunResult(
        key.id, key.runner, port.name, tuple(executed), known_at, checkpoints, tuple(notes)
    )


def _checkpoint(
    key: AnswerKey,
    port: PlatformPort,
    checkpoint: Checkpoint,
    known_at: Mapping[int, datetime],
    findings: Sequence[object],
) -> PlatformCheckpoint:
    at = known_at.get(checkpoint.after_seq, datetime.min.replace(tzinfo=UTC))
    blocks: list[BlockOutcome] = []
    run: CheckpointRun | None = None
    engine_blocks = [
        name
        for name, present in (
            ("contracts", checkpoint.contracts),
            ("subledger", checkpoint.subledger),
            ("groups", checkpoint.groups),
            ("exceptions", checkpoint.exceptions),
        )
        if present is not None
    ]
    if engine_blocks or checkpoint.journals:
        try:
            run = port.checkpoint_run(checkpoint)
        except NotProvisioned as refused:
            for name in engine_blocks:
                blocks.append(BlockOutcome(name, NOT_RUN, reason=str(refused)))
            for block in checkpoint.journals or ():
                blocks.append(BlockOutcome(_journal_name(block), NOT_RUN, reason=str(refused)))
            run = None
        except EngineError as error:  # the key's bundle is refused by the engine: an engine stop
            reason = f"{type(error).__name__} {error}"
            for name in engine_blocks:
                blocks.append(BlockOutcome(name, ERROR, reason=reason))
            for block in checkpoint.journals or ():
                blocks.append(BlockOutcome(_journal_name(block), ERROR, reason=reason))
            run = None
    pending = port.pending_blocks(checkpoint) if run is not None else {}
    if run is not None and engine_blocks:
        # A subledger block the platform cannot witness yet is left out of the comparison and
        # reported not run under its own name; every other block is compared as it stands.
        waiting = [
            block for block in checkpoint.subledger or () if _subledger_name(block) in pending
        ]
        compared = checkpoint
        if waiting:
            rest = tuple(block for block in checkpoint.subledger or () if block not in waiting)
            compared = checkpoint.model_copy(update={"subledger": rest or None})
        comparison = _CheckpointComparison(
            key,
            compared,
            run,
            (),
            cast(Sequence[runners.range_validation.RangeFinding], findings),
        )
        mismatches = tuple(comparison.mismatches())
        for name in engine_blocks:
            if name == "subledger":
                for block in waiting:
                    part = _subledger_name(block)
                    blocks.append(BlockOutcome(part, NOT_RUN, reason=pending[part]))
                if compared.subledger is None:
                    continue  # every subledger block waits: none was compared
            own = tuple(m for m in mismatches if _belongs(m, name))
            blocks.append(BlockOutcome(name, COMPARED, own))
        identities = tuple(m for m in mismatches if not any(_belongs(m, n) for n in engine_blocks))
        if identities:
            blocks.append(BlockOutcome("identities", COMPARED, identities))
    if run is not None:
        for block in checkpoint.journals or ():
            name = _journal_name(block)
            if name in pending:
                blocks.append(BlockOutcome(name, NOT_RUN, reason=pending[name]))
                continue
            try:
                lines = port.journal_run(checkpoint, run, block)
            except NotProvisioned as refused:
                blocks.append(BlockOutcome(name, NOT_RUN, reason=str(refused)))
                continue
            blocks.append(
                BlockOutcome(
                    name,
                    COMPARED,
                    tuple(_compare_journals(key, checkpoint, block, lines)),
                    detail=journal_totals(lines),
                )
            )
    for block in checkpoint.reports or ():
        name = f"reports {block.report_code}"
        try:
            rows = port.report_rows(checkpoint, block)
        except NotProvisioned as refused:
            blocks.append(BlockOutcome(name, NOT_RUN, reason=str(refused)))
            continue
        cells = compare_block(key, block, rows)
        blocks.append(
            BlockOutcome(name, COMPARED, tuple(_cell_mismatch(key, checkpoint, c) for c in cells))
        )
    if checkpoint.period_states:
        mismatches: list[Mismatch] = []
        try:
            for state in checkpoint.period_states:
                actual = port.period_state(
                    state.entity, state.book, state.period_key, checkpoint.after_seq
                )
                if actual != state.state:
                    mismatches.append(
                        Mismatch(
                            key.id,
                            checkpoint.name,
                            f"period {state.entity} {state.book} {state.period_key}",
                            "state",
                            state.state,
                            ABSENT if actual is None else actual,
                        )
                    )
        except NotProvisioned as refused:
            blocks.append(BlockOutcome("period_states", NOT_RUN, reason=str(refused)))
        else:
            blocks.append(BlockOutcome("period_states", COMPARED, tuple(mismatches)))
    return PlatformCheckpoint(checkpoint.name, checkpoint.after_seq, at, tuple(blocks))


def _journal_name(block: JournalBlock) -> str:
    return f"journals {block.run.entity} {block.run.period_key} {block.run.mode}"


def _subledger_name(block: SubledgerBlock) -> str:
    """One subledger block by name, as the subjects of its mismatches begin
    (``_CheckpointComparison.subledger``)."""
    name = f"subledger {block.period_key} {block.entity}"
    return name if block.contract is None else f"{name} {block.contract}"


def _belongs(mismatch: Mismatch, block: str) -> bool:
    subject = mismatch.subject
    if block == "subledger":
        return subject.startswith("subledger ")
    if block == "contracts":
        return subject.startswith(
            (
                "contract ",
                "obligation ",
                "version ",
                "balance ",
                "schedule ",
                "modification ",
                "trace ",
                "proposal ",
            )
        )
    if block == "groups":
        return subject.startswith("group ")
    if block == "exceptions":
        return subject.startswith("exception")
    return False


def _cell_mismatch(key: AnswerKey, checkpoint: Checkpoint, cell: CellMismatch) -> Mismatch:
    return Mismatch(
        key.id,
        checkpoint.name,
        f"report {cell.report_code} {cell.row_key}",
        cell.column_key,
        cell.expected,
        cell.actual,
    )


def assert_platform_checkpoints(loaded: LoadedKey, result: PlatformRunResult) -> None:
    """Fail once with every mismatch (DG-AK-55); a clean in-memory run is not a pass (see
    ``platform_outcome``)."""
    if result.mismatches:
        raise CheckpointMismatchError(loaded.key.id, result.mismatches)


def platform_outcome(loaded: LoadedKey, result: PlatformRunResult) -> tuple[str, str]:
    """(result, message): ``failed`` on any mismatch or engine error; ``passed`` only when every
    block compared clean on the database platform; otherwise ``not_run`` with the evidence. A
    ``not_run`` message opens with what the key waits for (``first_not_run``; item
    AK-NOT-RUN-REASON-1); a run with nothing refused that still cannot pass — a clean run on the
    in-memory platform — waits for the databases and says so."""
    errors = [
        f"{checkpoint.name} {block.block}: {block.reason}"
        for checkpoint in result.checkpoints
        for block in checkpoint.blocks
        if block.status == ERROR
    ]
    if errors:
        return "failed", f"engine stop on the {result.platform} platform: {errors[0]}"
    failed_steps = [item for item in result.executed if item.status == FAILED_STEP]
    if failed_steps:
        return "failed", f"refusal verification failed (PLAT-1): {failed_steps[0].reason}"
    if result.mismatches:
        count = len(result.mismatches)
        noun = "mismatch" if count == 1 else "mismatches"
        return "failed", f"{count} {noun} on the {result.platform} platform"
    compared = ", ".join(result.compared) or "none"
    if result.platform == DB and not result.not_run:
        return "passed", f"every block compared clean on the {DB} platform"
    pending = ", ".join(item for item in result.not_run if not item.startswith("step ")) or "none"
    applied = sum(1 for item in result.executed if item.status == EXECUTED)
    refused = sum(1 for item in result.executed if item.status == NOT_RUN)
    first = first_not_run(result)
    opening = NOT_PROVISIONED if first is None else f"{NOT_RUN_LEAD}{first}"
    return (
        NOT_RUN,
        f"{opening}; {result.platform} platform: {applied} steps applied, "
        f"{refused} refused; blocks compared clean: {compared}; blocks not run: {pending}",
    )


def override_finding(key: AnswerKey) -> Mismatch | None:
    """Count and identify unsupported declarations without masking numeric mismatches."""
    declared: dict[str, list[str]] = {}
    for contract in key.contracts:
        for override in contract.policy_overrides or ():
            if override.policy_key in SUPPORTED_OVERRIDES:
                continue
            spec = POLICY_PARAMETERS.get(override.policy_key)
            name = override.policy_key if spec is None else f"{spec.pol_id} {override.policy_key}"
            place = contract.external_id
            if override.obligation_key is not None:
                place = f"{place}/{override.obligation_key}"
            declared.setdefault(name, []).append(place)
    if not declared:
        return None
    count = sum(len(places) for places in declared.values())
    listed = "; ".join(f"{name} at {', '.join(places)}" for name, places in declared.items())
    policies = ", ".join(sorted(name.split(" ", 1)[0] for name in declared))
    return Mismatch(
        key.id,
        OVERRIDES_CHECKPOINT,
        OVERRIDES_SUBJECT,
        OVERRIDES_FIELD,
        OVERRIDES_EXPECTED.format(count=count, declared=listed),
        OVERRIDES_ACTUAL.format(policies=policies),
    )


def key_verdict(
    loaded: LoadedKey, result: PlatformRunResult
) -> tuple[str, tuple[Mismatch, ...], str]:
    """(result, mismatches, message) of a platform KEY: what its pytest node fails by and what the
    report records (``tests/answer_keys/test_answer_keys.py``). The run is judged by
    ``platform_outcome``, whose word and whose figures' mismatches stand as they are for a key
    that declares no policy override. A key that declares one (register index 308; module
    docstring) is judged with its one finding beside the figures' mismatches, whatever the run's
    outcome: ``passed`` becomes ``failed`` — every block compared clean and the key's world was
    still not built as the key declares it — and the message ends with the finding."""
    status, message = platform_outcome(loaded, result)
    finding = override_finding(loaded.key)
    if finding is None:
        return status, result.mismatches, message
    told = (
        f"finding: {finding.subject} {finding.field}: expected {finding.expected}, "
        f"actual {finding.actual}"
    )
    return (
        "failed" if status == "passed" else status,
        (*result.mismatches, finding),
        f"{message}; {told}",
    )


def first_not_run(result: PlatformRunResult) -> str | None:
    """What a not-run key waits for, by name: the reason of the first step that was not run —
    the database platform runs nothing after it (``DbPlatform.execute``) — else of the first
    block that was not run. The reason is given without the words every reason opens with
    (``NOT_RUN_LEAD``), so the one that names the databases still names them."""
    reasons = [item.reason for item in result.executed if item.status == NOT_RUN]
    reasons.extend(
        block.reason
        for checkpoint in result.checkpoints
        for block in checkpoint.blocks
        if block.status == NOT_RUN
    )
    first = next((reason for reason in reasons if reason), None)
    return None if first is None else first.removeprefix(NOT_RUN_LEAD)


def period_states_of(key: AnswerKey) -> tuple[PeriodState, ...]:
    return tuple(key.world.period_states)
