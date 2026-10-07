"""The platform answer-key runner on the in-memory platform (dev-guide DG-AK-41; BUILD_SPEC PRP-1
to PRP-3; lane F-RPS + ENG-E1). No database: every DB-bound step or block is marked
``not run — databases not provisioned``; a clean in-memory run is ``not_run`` evidence, never
``passed`` (XR-12); mismatches and engine stops are ``failed``.

The five platform keys of PHASES §8.2.3 are run at their pinned oracles.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from fractions import Fraction

import pytest
from support.answer_keys import runners
from support.answer_keys.models import Checkpoint
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, load_platform_key, plan
from support.answer_keys.platform_runner import (
    COMPARED,
    ERROR,
    EXECUTED,
    IN_MEMORY,
    JOURNALS,
    NOT_PROVISIONED,
    NOT_RUN,
    SUBLEDGER,
    DbPlatform,
    InMemoryPlatform,
    NotProvisioned,
    PassBlock,
    PlatformRunResult,
    assert_platform_checkpoints,
    close_runs,
    journal_lines,
    pass_blocks,
    platform_outcome,
    run_platform,
)
from support.answer_keys.runners import ABSENT, CheckpointMismatchError, CheckpointRun

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS


@pytest.fixture(scope="module")
def results() -> dict[str, PlatformRunResult]:
    return {key_id: run_platform(load_platform_key(key_id)) for key_id in PLATFORM_KEY_IDS}


def _blocks(result: PlatformRunResult) -> dict[str, str]:
    return {
        f"{checkpoint.name} {block.block}": block.status
        for checkpoint in result.checkpoints
        for block in checkpoint.blocks
    }


def test_commands_run_in_plan_order_and_stamp_known_at(
    results: dict[str, PlatformRunResult],
) -> None:
    """Every non-checkpoint plan step runs in order on the in-memory platform; each timeline item
    that commits stamps ``known_at[seq]`` once, strictly increasing, at the engine runner's record
    time (the frozen clock is the server clock in memory)."""
    for key_id, result in results.items():
        loaded = load_platform_key(key_id)
        steps = [step for step in plan(loaded).steps if step.phase != "CHECKPOINT"]
        assert [item.step for item in result.executed] == steps, key_id
        assert all(item.status == EXECUTED for item in result.executed), key_id
        assert result.platform == IN_MEMORY and result.runner == "platform"
        seqs = [item.seq for item in loaded.key.timeline if item.expect_problem is None]
        assert sorted(result.known_at) == sorted(seqs), key_id
        stamps = [result.known_at[seq] for seq in sorted(result.known_at)]
        assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps), key_id
        times = runners._Assembler(loaded).times
        assert all(result.known_at[seq] == times[seq] for seq in result.known_at), key_id
    first = results[POS_012].known_at[1]
    assert first == datetime(2026, 1, 2, 17, tzinfo=UTC)


def test_pos_012_contracts_and_subledger_compare_clean_in_memory(
    results: dict[str, PlatformRunResult],
) -> None:
    """PRP-1 figures (CHK-012): both checkpoints' contracts and subledger blocks compare with zero
    mismatches on the in-memory platform; the outcome is still ``not_run`` (no database)."""
    result = results[POS_012]
    assert _blocks(result) == {
        "end-of-p1 contracts": COMPARED,
        "end-of-p1 subledger": COMPARED,
        "end-of-p2 contracts": COMPARED,
    }
    assert result.mismatches == ()
    status, message = platform_outcome(load_platform_key(POS_012), result)
    assert status == NOT_RUN
    assert message.startswith(NOT_PROVISIONED)
    assert (
        "blocks compared clean: end-of-p1 contracts, end-of-p1 subledger, end-of-p2 contracts"
        in message
    )
    assert_platform_checkpoints(load_platform_key(POS_012), result)  # no mismatch → no raise


def test_dlt_journals_gross_and_delta_from_posting_intents(
    results: dict[str, PlatformRunResult],
) -> None:
    """PRP-2 figures (CHK-020, CHK-022, GT-07): the four journal runs (ME1, ME2 × GROSS, DELTA)
    summarised from the checkpoint's posting intents match the key's lines; the DELTA runs balance
    (ME1 181.37 + ME2 58.85 = 240.22 debits = credits); the LEGACY subledger compares clean."""
    result = results[DLT]
    blocks = _blocks(result)
    assert blocks == {
        "asc606-january contracts": COMPARED,
        "asc606-january subledger": COMPARED,
        "asc606-january journals ME1 FY2023-P01 GROSS": COMPARED,
        "asc606-january journals ME1 FY2023-P01 DELTA": COMPARED,
        "asc606-january journals ME2 FY2023-P01 GROSS": COMPARED,
        "asc606-january journals ME2 FY2023-P01 DELTA": COMPARED,
        "legacy-january subledger": COMPARED,
    }
    assert result.mismatches == ()
    details = {
        block.block: dict(block.detail)
        for checkpoint in result.checkpoints
        for block in checkpoint.blocks
        if block.block.startswith("journals")
    }
    assert details["journals ME1 FY2023-P01 GROSS"] == {
        "debits USD": "dr 295.69",
        "credits USD": "cr 295.69",
        "balanced USD": "true",
    }
    assert details["journals ME1 FY2023-P01 DELTA"] == {
        "debits USD": "dr 181.37",
        "credits USD": "cr 181.37",
        "balanced USD": "true",
    }
    assert details["journals ME2 FY2023-P01 DELTA"] == {
        "debits USD": "dr 58.85",
        "credits USD": "cr 58.85",
        "balanced USD": "true",
    }
    assert Fraction("181.37") + Fraction("58.85") == Fraction("240.22")
    # The DELTA lines themselves: primary + LEGACY per account (D-89 L7-6-Q-8).
    loaded = load_platform_key(DLT)
    platform = InMemoryPlatform(loaded)
    checkpoint = loaded.key.checkpoints[0]
    run = platform.checkpoint_run(checkpoint)
    delta = journal_lines(
        run,
        entity="ME1",
        period_key="FY2023-P01",
        mode="DELTA",
        primary_book="ASC606",
        grain="ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
    )
    assert {line.account: (line.side, abs(line.net)) for line in delta} == {
        "21001": ("dr", Fraction("141.69")),
        "5003": ("dr", Fraction("39.68")),
        "5001": ("cr", Fraction("128.84")),
        "5002": ("cr", Fraction("52.53")),
    }
    gross = journal_lines(
        run,
        entity="ME1",
        period_key="FY2023-P01",
        mode="GROSS",
        primary_book="ASC606",
        grain="ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
    )
    assert {line.account: (line.side, abs(line.net)) for line in gross} == {
        "21001": ("dr", Fraction("295.69")),
        "5001": ("cr", Fraction("128.84")),
        "5002": ("cr", Fraction("118.53")),
        "5003": ("cr", Fraction("48.32")),
    }
    with pytest.raises(ValueError, match="GROSS or DELTA"):
        journal_lines(
            run, entity="ME1", period_key="FY2023-P01", mode="NET", primary_book="ASC606", grain="x"
        )


def test_report_blocks_are_db_bound(results: dict[str, PlatformRunResult]) -> None:
    """PRP-3: report runs read persisted rows through the report framework; on the in-memory
    platform every reports block is not run with the reason, and the key is ``not_run``."""
    ex21 = results[EX21]
    assert set(_blocks(ex21).values()) == {NOT_RUN}
    assert len(ex21.not_run) == 4 and all(
        item.startswith("reports-after-year-2 reports ") for item in ex21.not_run
    )
    reasons = [block.reason or "" for checkpoint in ex21.checkpoints for block in checkpoint.blocks]
    assert all(reason.startswith(NOT_PROVISIONED) for reason in reasons)
    status, message = platform_outcome(load_platform_key(EX21), ex21)
    assert (
        status == NOT_RUN
        and "blocks not run: reports-after-year-2 reports contract_balance_rollforward" in message
    )
    # No database stands behind the in-memory platform: its DB-bound blocks keep those words, and
    # the outcome opens with the first of them (item AK-NOT-RUN-REASON-1).
    assert message.startswith(
        f"{NOT_PROVISIONED}: reports contract_balance_rollforward: report runs read persisted "
        "versions and subledger rows through the report framework"
    )
    pos_117 = results[POS_117]
    assert _blocks(pos_117) == {
        "march-close contracts": COMPARED,
        "march-close subledger": COMPARED,
        "march-close reports balance_aging": NOT_RUN,
    }
    assert pos_117.mismatches == ()
    (aging,) = [
        block for block in pos_117.checkpoints[0].blocks if block.block.startswith("reports")
    ]
    assert "databases not provisioned" in (aging.reason or "")


def test_ex42_compares_clean_and_its_rpo_report_is_db_bound(
    results: dict[str, PlatformRunResult],
) -> None:
    """The RPO key's expedient contract (C-EX42-A, template TPL-RTI ``RIGHT_TO_INVOICE``) reaches
    the comparison since ENC-6 (D-98 candidate 28; ENGINE_SPEC 1.21 S04-R-06, ENGINE_SPEC_B
    S09-R-18: f = min(1, R/P)) and compares clean since D-98 candidates 91 / 91a (ENGINE_SPEC_B
    1.26 S15-R-08): ``rpo_amount`` carries the gross contractual remaining amount 9,000.00
    (12,000.00 − 3,000.00) under POL-198, so the contracts block is ``compared`` with no mismatch
    and no engine stop. The RPO report block stays ``not_run`` on the in-memory platform (DB-bound)
    and the outcome is ``not_run``, never ``passed`` (XR-12): this test establishes no acceptance of
    the key. History (F-RPS's bounded diagnostic, record §30, main c60529ab): before the
    calculation correction the block compared with exactly one mismatch — ``contract C-EX42-A``
    ``rpo_amount`` expected 9000.00, actual 0.00, the engine's defect, not the oracle's; before
    ENC-6 the engine stopped with ``ENGINE_INVARIANT_VIOLATED`` "the measure of progress is not
    built" (S09-R-02; shown obsolete on main a7347356 in
    ``.run/f-rps-e1/fail-first-ex42-enc6.log``)."""
    result = results[EX42]
    blocks = {
        block.block: block for checkpoint in result.checkpoints for block in checkpoint.blocks
    }
    assert all(block.status != ERROR for block in blocks.values())
    assert not any("ENGINE_INVARIANT_VIOLATED" in (block.reason or "") for block in blocks.values())
    assert blocks["contracts"].status == COMPARED
    assert blocks["contracts"].reason is None
    assert blocks["contracts"].mismatches == ()
    assert result.mismatches == ()
    assert blocks["reports rpo"].status == NOT_RUN
    status, message = platform_outcome(load_platform_key(EX42), result)
    assert status == NOT_RUN and message.startswith(NOT_PROVISIONED)
    assert_platform_checkpoints(load_platform_key(EX42), result)  # no DG-AK-55 error: 0 mismatches


def test_db_platform_marks_every_step_not_provisioned() -> None:
    """Until the databases exist the database platform refuses each step and block with the
    handler it will call; the runner records them as not run and never passes."""
    loaded = load_platform_key(POS_012)
    result = run_platform(loaded, DbPlatform(loaded))
    assert result.platform == "db"
    assert all(item.status == NOT_RUN for item in result.executed)
    assert result.known_at == {}
    assert set(_blocks(result).values()) == {NOT_RUN}
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN and message.startswith(NOT_PROVISIONED)
    with pytest.raises(NotProvisioned, match="provision_tenant"):
        DbPlatform(loaded).execute(plan(loaded).steps[1])


def test_the_database_platform_is_wired_to_the_real_adapter_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAT-G4-1 (record §35): under ``EREV_AK_PLATFORM=db`` the runner builds the ``DbPlatform``
    over the real adapter factory (``database_platform.database_adapter``) — never ``MockAdapter``,
    never the in-memory platform. When the factory refuses (no configured or reachable lane
    database) every step and block is not run with the same named refusal as before — the step,
    the handler it would call — now carrying the factory's reason (exception type, never a URL)."""
    from support.answer_keys import database_platform
    from support.answer_keys.platform_runner import PLATFORM_ENV, _platform

    loaded = load_platform_key(POS_012)
    monkeypatch.setenv(PLATFORM_ENV, "db")
    port = _platform(loaded, None)
    assert isinstance(port, DbPlatform) and port.name == "db"
    assert port.adapter is None and port.factory is database_platform.database_adapter
    monkeypatch.setenv(PLATFORM_ENV, "in-memory")
    assert isinstance(_platform(loaded, None), InMemoryPlatform)

    def refusing(_loaded: object) -> object:  # what the factory does without a lane database
        raise NotProvisioned(
            "database platform: database erev_rv_l17_test is not available (OperationalError)",
            "erev_api.db.session.owner_engine",
        )

    result = run_platform(loaded, DbPlatform(loaded, factory=refusing))
    assert result.platform == "db" and result.notes[0] == "platform: db"
    assert all(item.status == NOT_RUN for item in result.executed)
    provision = next(item for item in result.executed if item.step.phase == "PROVISION")
    assert provision.reason is not None
    assert provision.reason.startswith(NOT_PROVISIONED)
    assert "PROVISION" in provision.reason and "provision_tenant" in provision.reason
    assert "not available (OperationalError)" in provision.reason
    assert result.known_at == {} and set(_blocks(result).values()) == {NOT_RUN}
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN and message.startswith(NOT_PROVISIONED)
    assert "mock" not in message and "in-memory" not in message
    assert not any("mock" in note or "in-memory" in note for note in result.notes)


def test_in_memory_never_passes_and_mismatches_fail() -> None:
    """XR-12: the in-memory platform never yields ``passed``; a fabricated mismatch is ``failed``
    and ``assert_platform_checkpoints`` raises the DG-AK-55 error."""
    loaded = load_platform_key(POS_012)
    result = run_platform(loaded)
    status, _ = platform_outcome(loaded, result)
    assert status == NOT_RUN
    from dataclasses import replace

    from support.answer_keys.platform_runner import BlockOutcome
    from support.answer_keys.runners import Mismatch

    broken_block = BlockOutcome(
        "contracts",
        COMPARED,
        (
            Mismatch(
                loaded.key.id,
                "end-of-p1",
                "contract C-POS-012-X",
                "revenue_cum",
                "80000.00",
                "0.00",
            ),
        ),
    )
    checkpoint = replace(result.checkpoints[0], blocks=(broken_block,))
    broken = replace(result, checkpoints=(checkpoint, *result.checkpoints[1:]))
    status, message = platform_outcome(loaded, broken)
    assert status == "failed" and message == "1 mismatch on the in-memory platform"
    with pytest.raises(CheckpointMismatchError, match="1 checkpoint mismatches"):
        assert_platform_checkpoints(loaded, broken)


def test_engine_runner_still_refuses_platform_results() -> None:
    """``runners.assert_checkpoints`` keeps its fail-closed guard for platform keys; the platform
    path lives in ``platform_runner`` (``runners.run_platform`` stays absent)."""
    assert not hasattr(runners, "run_platform")
    assert "never the engine runner" in runners.PLATFORM_RUNNER_MISSING


# What the test's own platform says of a block it leaves out: it ran no close run.
NO_CLOSE_RUN = "this platform posts the period-end passes in a close run and ran none"


class _PostsNoPasses(InMemoryPlatform):
    """The in-memory store as a platform that posts the period-end passes only in a close run
    and runs none: its checkpoint books carry no pass — the database platform before the plan
    had its close-run step (dev-guide rev 1.246). ``waits`` says whether it names the blocks
    that expect a pass (``pass_blocks``) or lets them be compared."""

    def __init__(self, loaded: object, *, waits: bool) -> None:
        super().__init__(loaded)  # type: ignore[arg-type]
        self.waits = waits

    def checkpoint_run(self, checkpoint: Checkpoint) -> CheckpointRun:
        run = super().checkpoint_run(checkpoint)
        return CheckpointRun(run.checkpoint, run.outputs)

    def pending_blocks(self, checkpoint: Checkpoint) -> dict[str, str]:
        if not self.waits:
            return {}
        return {block.name: NO_CLOSE_RUN for block in pass_blocks(self.loaded, checkpoint)}


def test_pass_blocks_names_exactly_the_blocks_a_period_end_pass_changes() -> None:
    """The oracle computes the close-run passes with every checkpoint (D-85). A block expects
    one exactly when the oracle's own books answer it differently with the passes than without:
    the subledger block of the entity, period and contract a pass posts lines of that the block
    lists, and the journal runs that read those lines. GT07's netting reclass is of ME2 in the
    ASC 606 book — its ME1 blocks and both LEGACY subledger blocks expect none. The close runs
    the plan runs are the entities and periods of those blocks, each once (dev-guide rev 1.246;
    item AK-CLOSE-RUN-STEP-1)."""
    keys = {key_id: load_platform_key(key_id) for key_id in PLATFORM_KEY_IDS}
    found = {
        (key_id, checkpoint.name): pass_blocks(loaded, checkpoint)
        for key_id, loaded in keys.items()
        for checkpoint in loaded.key.checkpoints
    }
    assert found == {
        (POS_012, "end-of-p1"): (
            PassBlock("subledger FY2026-P01 US01 C-POS-012-X", SUBLEDGER, "US01", "FY2026-P01"),
        ),
        (POS_012, "end-of-p2"): (),
        (DLT, "asc606-january"): (
            PassBlock("subledger FY2023-P01 ME2", SUBLEDGER, "ME2", "FY2023-P01"),
            PassBlock("journals ME2 FY2023-P01 GROSS", JOURNALS, "ME2", "FY2023-P01"),
            PassBlock("journals ME2 FY2023-P01 DELTA", JOURNALS, "ME2", "FY2023-P01"),
        ),
        (DLT, "legacy-january"): (),
        (EX21, "reports-after-year-2"): (),
        (EX42, "december-2026-rpo"): (),
        (POS_117, "march-close"): (
            PassBlock("subledger FY2026-P03 US01", SUBLEDGER, "US01", "FY2026-P03"),
        ),
    }
    runs = {
        where: close_runs(keys[where[0]], checkpoint)
        for where in found
        for checkpoint in keys[where[0]].key.checkpoints
        if checkpoint.name == where[1]
    }
    assert {where: run for where, run in runs.items() if run} == {
        (POS_012, "end-of-p1"): (("US01", "FY2026-P01"),),
        (DLT, "asc606-january"): (("ME2", "FY2023-P01"),),  # three blocks, one run
        (POS_117, "march-close"): (("US01", "FY2026-P03"),),
    }
    # A key a test varies in memory keeps the file's digest and its checkpoint's name; the
    # answer follows its content. Here the block asks for contract Y, which no pass touches.
    pos = keys[POS_012]
    first = pos.key.checkpoints[0]
    assert first.subledger is not None
    (block,) = first.subledger
    of_y = block.model_copy(update={"contract": "C-POS-012-Y"})
    varied = dataclasses.replace(
        pos,
        key=pos.key.model_copy(
            update={"checkpoints": (first.model_copy(update={"subledger": (of_y,)}),)}
        ),
    )
    assert (varied.sha256, varied.key.checkpoints[0].name) == (pos.sha256, first.name)
    assert pass_blocks(varied, varied.key.checkpoints[0]) == ()
    assert pass_blocks(pos, first) == found[(POS_012, "end-of-p1")]


def test_no_platform_names_a_block_that_waits() -> None:
    """Item AK-JOURNAL-RUN-PLAN-1. One run journalises a seal (04 DB-16: the runs of every mode
    count for one entity, book and period), so the journals blocks of an entity and period a
    close run or an earlier block already ran for had no run to be answered by, and the database
    platform named them not run (dev-guide rev 1.246, ruling (d) of 2026-10-01): GT07's two of
    ME2 and the second of ME1. The plan now has a step for every journals block that cancels
    the run in its way and creates the block's own (``platform_plan.journal_run_steps``), so no
    platform names a block any more. The mechanism stays for a platform that has to
    (``_PostsNoPasses`` below).

    STALE EXPECTATION under that item: until it this test pinned the three blocks and the
    reason "AK-JOURNAL-RUN-PLAN-1: one run journalises a seal … is not built"."""
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        for checkpoint in loaded.key.checkpoints:
            assert DbPlatform(loaded).pending_blocks(checkpoint) == {}, (key_id, checkpoint.name)
            assert InMemoryPlatform(loaded).pending_blocks(checkpoint) == {}


def test_a_block_the_platform_names_is_not_run_and_every_other_block_is_compared() -> None:
    """Why the plan runs a close run, and what a platform's ``pending_blocks`` does. Without the
    passes POS-012's end-of-p1 subledger block reads the liability gross and no contract asset
    (JET-06 nets them at period end): compared, two mismatches that say nothing of the product.
    A platform that names such a block leaves it out — it is not run, with the platform's
    reason, and the key ends not run — while every block it does not name is compared: GT07's
    ME1 subledger block and journal runs and its LEGACY subledger compare clean beside the ME2
    blocks left out."""
    pos = load_platform_key(POS_012)
    compared = run_platform(pos, _PostsNoPasses(pos, waits=False))
    assert [(m.subject, m.field, m.expected, m.actual) for m in compared.mismatches] == [
        (
            "subledger FY2026-P01 US01 C-POS-012-X CONTRACT_LIABILITY/2100",
            "dr",
            "50000.00",
            "dr 80000.00",
        ),
        ("subledger FY2026-P01 US01 C-POS-012-X CONTRACT_ASSET/1200", "dr", "30000.00", ABSENT),
    ]
    assert platform_outcome(pos, compared)[0] == "failed"
    waiting = run_platform(pos, _PostsNoPasses(pos, waits=True))
    assert _blocks(waiting) == {
        "end-of-p1 contracts": COMPARED,
        "end-of-p1 subledger FY2026-P01 US01 C-POS-012-X": NOT_RUN,
        "end-of-p2 contracts": COMPARED,
    }
    assert waiting.mismatches == ()
    (waits,) = [
        block
        for checkpoint in waiting.checkpoints
        for block in checkpoint.blocks
        if block.status == NOT_RUN
    ]
    assert waits.reason == NO_CLOSE_RUN
    status, message = platform_outcome(pos, waiting)
    # the key waits for what its platform names, and its outcome opens with that (item
    # AK-NOT-RUN-REASON-1)
    assert status == NOT_RUN and message.startswith(f"not run — {NO_CLOSE_RUN}; ")
    assert "databases not provisioned" not in message
    dlt = load_platform_key(DLT)
    compared = run_platform(dlt, _PostsNoPasses(dlt, waits=False))
    assert [
        (m.checkpoint, m.subject, m.field, m.expected, m.actual) for m in compared.mismatches
    ] == [
        (
            "asc606-january",
            "subledger FY2023-P01 ME2 UNBILLED_RECEIVABLE/15002",
            "dr",
            "58.85",
            ABSENT,
        ),
        (
            "asc606-january",
            "subledger FY2023-P01 ME2 CONTRACT_LIABILITY/21002",
            "line",
            ABSENT,
            "dr 58.85; functional dr 58.85",
        ),
        ("asc606-january", "journals ME2 FY2023-P01 GROSS account 15002", "dr", "58.85", ABSENT),
        (
            "asc606-january",
            "journals ME2 FY2023-P01 GROSS account 21002",
            "line",
            ABSENT,
            "dr 58.85",
        ),
        ("asc606-january", "journals ME2 FY2023-P01 DELTA account 15002", "dr", "58.85", ABSENT),
        (
            "asc606-january",
            "journals ME2 FY2023-P01 DELTA account 21002",
            "line",
            ABSENT,
            "dr 58.85",
        ),
    ]
    waiting = run_platform(dlt, _PostsNoPasses(dlt, waits=True))
    assert _blocks(waiting) == {
        "asc606-january contracts": COMPARED,
        "asc606-january subledger FY2023-P01 ME2": NOT_RUN,
        "asc606-january subledger": COMPARED,  # the ME1 block
        "asc606-january journals ME1 FY2023-P01 GROSS": COMPARED,
        "asc606-january journals ME1 FY2023-P01 DELTA": COMPARED,
        "asc606-january journals ME2 FY2023-P01 GROSS": NOT_RUN,
        "asc606-january journals ME2 FY2023-P01 DELTA": NOT_RUN,
        "legacy-january subledger": COMPARED,
    }
    assert waiting.mismatches == ()
    # A subledger block that waits takes none of the other blocks' mismatches with it: ME1's
    # block is still compared line by line (a line the books lack is a mismatch as before).
    me1 = [
        block
        for checkpoint in waiting.checkpoints
        for block in checkpoint.blocks
        if block.block == "subledger" and checkpoint.name == "asc606-january"
    ]
    assert len(me1) == 1 and me1[0].mismatches == () and me1[0].reason is None
