"""Command plans of the five platform answer keys (dev-guide DG-AK-41; BUILD_SPEC PRP-1 to PRP-3
prep; lane F-RPS + ENG-E1).

No database: the plans name domain handlers by dotted path and the tests prove each resolves on
main, that the five oracles are unchanged, that every timeline item captures ``known_at[seq]``
under the record-time rule the engine runner uses, and where each key stops next (PRP-1: the
runner). ``PLATFORM_RUNNER_MISSING`` stays in force.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from erev_api.domain.reports import framework
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load_all
from support.answer_keys.platform_plan import (
    APPROVER,
    CLOSE,
    COMMAND_HANDLERS,
    INTEGRATION,
    JOURNAL,
    LOCK_COMMAND_GAP,
    LOCK_COMMANDS,
    LOCK_GAP,
    ORACLES,
    PERIOD_STATE_HANDLERS,
    PLATFORM_KEY_IDS,
    PREPARER,
    REOPEN_COMMAND,
    REOPEN_COMMAND_GAP,
    REOPEN_GAP,
    REPORT_GAPS,
    RUNNER,
    SSP_ANALYST,
    SSP_APPROVER,
    CommandPlan,
    H,
    Step,
    _at_the_latest_instant,
    handler_exists,
    load_platform_key,
    oracle_mismatches,
    plan,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS


@pytest.fixture(scope="module")
def plans() -> dict[str, CommandPlan]:
    return {key_id: plan(load_platform_key(key_id)) for key_id in PLATFORM_KEY_IDS}


def test_five_platform_oracles_unchanged(tmp_path: Path) -> None:
    """The five keys of PHASES §8.2.3 are the only platform keys and hash to the pinned oracles;
    a changed key is refused."""
    assert oracle_mismatches() == []
    platform = sorted(item.key.id for item in load_all() if item.key.runner == "platform")
    assert platform == sorted(ORACLES)
    copy = tmp_path / "pos" / f"{POS_012}.yaml"
    copy.parent.mkdir()
    copy.write_text((ANSWER_KEY_ROOT / "pos" / f"{POS_012}.yaml").read_text() + "# changed\n")
    with pytest.raises(ValueError, match="sha256"):
        load_platform_key(POS_012, root=tmp_path)
    assert oracle_mismatches(root=ANSWER_KEY_ROOT) == []


def test_every_handler_resolves_on_main(plans: dict[str, CommandPlan]) -> None:
    """Each named domain handler is an attribute of an importable module; gaps name no handler
    they cannot back, and the runner itself is the one unresolvable path."""
    for item in plans.values():
        for step in item.steps:
            if step.phase == "RUNNER":  # PLAT-G4-1: the runner is built and wired (record §35)
                assert step.handler == RUNNER == "support.answer_keys.platform_runner.run_platform"
                assert handler_exists(step.handler) and step.gap is None
                continue
            assert step.handler == "" or handler_exists(step.handler), (item.key_id, step)
            if step.handler == "":
                assert step.gap is not None, (item.key_id, step)
    assert not hasattr(runners, "run_platform")  # the engine runner never runs a platform key
    assert "never the engine runner" in runners.PLATFORM_RUNNER_MISSING


def test_every_plan_starts_at_the_wired_runner(plans: dict[str, CommandPlan]) -> None:
    """PLAT-G4-1: the RUNNER marker names the built ``platform_runner.run_platform`` and carries no
    gap; four keys stop nowhere before the database, POS-CHK-117 at its report gap."""
    for item in plans.values():
        assert item.steps[0].phase == "RUNNER" and item.steps[0].gap is None
        assert item.first_stop == ("none" if item.key_id != POS_117 else item.gaps[0])
        assert (
            item.steps[1].phase == "PROVISION" and item.steps[1].detail["database"] == "erev_test"
        )
        personas = item.steps_of("PERSONAS")
        assert {step.subject for step in personas} >= {PREPARER, APPROVER}


def test_known_at_capture_per_timeline_item(plans: dict[str, CommandPlan]) -> None:
    """One ``known_at[seq]`` capture per timeline item by its own steps, in seq order; the clock
    before each item is the engine runner's record time (explicit ``recorded_at``, else local noon
    of the effective date in the entity's zone, at least one second after the previous item), so
    the order is preserved although DB-08 assigns the real record time. Since dev-guide rev 1.246
    the item a close run follows is stamped once more, by that run: the later stamp is the
    checkpoint's (the supervisor's ruling of 2026-10-01 on AK-CLOSE-RUN-STEP-1, (a))."""
    for key_id, item in plans.items():
        loaded = load_platform_key(key_id)
        seqs = [timeline.seq for timeline in loaded.key.timeline if timeline.expect_problem is None]
        own = [step.seq for step in item.steps_of("TIMELINE") if step.captures_known_at]
        assert own == sorted(seqs), key_id
        closes = [step.seq for step in item.steps_of(CLOSE) if step.captures_known_at]
        assert list(item.known_at_captures) == sorted([*seqs, *closes]), key_id
        clocks = [
            datetime.strptime(step.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            for step in item.steps_of("TIMELINE")
            if step.captures_known_at and step.clock_at is not None
        ]
        assert clocks == sorted(clocks) and len(set(clocks)) == len(clocks), key_id
    # POS-012's first item: 2026-01-02 noon New York = 17:00Z.
    first = next(step for step in plans[POS_012].steps_of("TIMELINE") if step.seq == 1)
    zone = ZoneInfo(load_platform_key(POS_012).key.world.entities[0].time_zone)
    noon = datetime(2026, 1, 2, 12, tzinfo=zone).astimezone(UTC)
    assert first.clock_at == noon.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-01-02T17:00:00Z"


def _close_steps(item: CommandPlan) -> list[tuple[object, ...]]:
    return [
        (step.subject, step.seq, step.clock_at, step.actor, step.handler, dict(step.detail))
        for step in item.steps_of(CLOSE)
    ]


def test_a_close_run_follows_the_checkpoint_whose_blocks_expect_a_pass(
    plans: dict[str, CommandPlan],
) -> None:
    """DG-AK-41 rev 1.246 (item AK-CLOSE-RUN-STEP-1; the supervisor's rulings of 2026-10-01 on
    the lane's measurement). The oracle computes the period-end passes with every checkpoint; the
    product posts them in a close run. So the plan runs the product's close run — as the
    preparer, who holds ``period.close`` — for the entity, book and period of the blocks that
    expect a pass, right after the checkpoint's last item and before the next one. Three of the
    five keys have such a block; the two disclosure keys have none."""

    def close(entity: str, period_key: str, checkpoint: str) -> dict[str, str]:
        return {
            "entity": entity,
            "book": "ASC606",
            "period_key": period_key,
            "checkpoint": checkpoint,
        }

    start = H["close_run"]
    assert start == "erev_api.domain.close.close_runs.start" and handler_exists(start)
    assert {key_id: _close_steps(item) for key_id, item in plans.items()} == {
        POS_012: [
            (
                "close run US01 ASC606 FY2026-P01",
                9,
                "2026-01-31T17:00:01Z",
                PREPARER,
                start,
                close("US01", "FY2026-P01", "end-of-p1"),
            )
        ],
        DLT: [
            (
                "close run ME2 ASC606 FY2023-P01",
                13,
                "2023-01-31T17:00:09Z",
                PREPARER,
                start,
                close("ME2", "FY2023-P01", "asc606-january"),
            )
        ],
        EX21: [],
        EX42: [],
        POS_117: [
            (
                "close run US01 ASC606 FY2026-P03",
                7,
                "2026-03-31T16:00:01Z",
                PREPARER,
                start,
                close("US01", "FY2026-P03", "march-close"),
            )
        ],
    }
    for item in plans.values():
        assert all(step.captures_known_at and step.gap is None for step in item.steps_of(CLOSE))
    # Its place: right after the last step of the item it follows, before the next item's first.
    steps = plans[POS_012].steps
    at = next(index for index, step in enumerate(steps) if step.phase == CLOSE)
    assert (steps[at - 1].phase, steps[at - 1].seq) == ("TIMELINE", 9)
    assert (steps[at + 1].phase, steps[at + 1].seq) in (("TIMELINE", 10), ("CONTRACTS", 10))
    assert [step.seq for step in steps[:at] if step.seq is not None][-1] == 9
    assert 9 not in [step.seq for step in steps[at + 1 :] if step.phase != "CHECKPOINT"]
    # GT07's run follows the key's last item. The journal runs of the checkpoint's four journals
    # blocks come next (item AK-JOURNAL-RUN-PLAN-1), then the checkpoint reads.
    steps = plans[DLT].steps
    at = next(index for index, step in enumerate(steps) if step.phase == CLOSE)
    assert steps[at - 1].seq == 13
    assert [step.phase for step in steps[at + 1 : at + 6]] == [JOURNAL] * 4 + ["CHECKPOINT"]


def test_a_journal_run_follows_the_checkpoint_that_names_its_block(
    plans: dict[str, CommandPlan],
) -> None:
    """Item AK-JOURNAL-RUN-PLAN-1. A journals block is answered by a step of the plan where the
    checkpoint stands in the timeline: right after the checkpoint's last item and the close run
    the plan runs there, before the next item — as the preparer, who holds ``journal.run``. One
    step per block, the blocks in the key's order; GT07 is the one platform key that has any.
    The step names the block's entity, period, mode and grain and gives no cutoff; it stamps
    nothing, and its application instant is the latest of any step before it — here the close
    run's, one second after item 13."""
    grain = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"

    def block(entity: str, mode: str) -> tuple[object, ...]:
        return (
            f"journals {entity} FY2023-P01 {mode}",
            13,
            "2023-01-31T17:00:09Z",
            PREPARER,
            H["journal_create"],
            {
                "entity": entity,
                "period_key": "FY2023-P01",
                "mode": mode,
                "grain": grain,
                "checkpoint": "asc606-january",
            },
        )

    found = {
        key_id: [
            (step.subject, step.seq, step.clock_at, step.actor, step.handler, dict(step.detail))
            for step in item.steps_of(JOURNAL)
        ]
        for key_id, item in plans.items()
    }
    assert found == {
        POS_012: [],
        DLT: [
            block("ME1", "GROSS"),
            block("ME1", "DELTA"),
            block("ME2", "GROSS"),
            block("ME2", "DELTA"),
        ],
        EX21: [],
        EX42: [],
        POS_117: [],
    }
    steps = plans[DLT].steps
    journal_runs = [step for step in steps if step.phase == JOURNAL]
    assert all(not step.captures_known_at and step.gap is None for step in journal_runs)
    (close,) = plans[DLT].steps_of(CLOSE)
    assert {step.clock_at for step in journal_runs} == {close.clock_at}
    assert handler_exists(H["journal_create"]) and handler_exists(H["journal_cancel"])
    # nothing of the plan creates a run when a checkpoint is read
    assert not [
        step
        for item in plans.values()
        for step in item.steps_of("CHECKPOINT")
        if step.handler in (H["journal_create"], H["journal_cancel"], H["journal_submit"])
    ]


def test_a_journal_run_takes_the_latest_instant_of_any_step_before_it() -> None:
    """A journal run covers the seals whose ``sealed_at`` — the application clock's — is at or
    before its cutoff, and the step gives none: the command takes the clock of the step. So the
    step's instant is the LATEST of any step before it, not the instant of the step just before:
    a close run stands at noon of its checkpoint's as-of date, which may lie after the item that
    follows it, and a run made at that item's instant would leave the close run's seals out. A
    step of another phase keeps its own instant."""

    def step(phase: str, seq: int, at: str | None = None) -> Step:
        return Step(phase, PREPARER, "handler", f"{phase} {seq}", seq=seq, clock_at=at)

    steps = [
        step("PROVISION", 0, "2026-01-01T00:00:00Z"),
        step("TIMELINE", 1, "2026-01-15T17:00:00Z"),
        step(CLOSE, 1, "2026-01-31T17:00:00Z"),  # noon of the as-of date
        step(JOURNAL, 1),
        step("TIMELINE", 2, "2026-01-20T17:00:00Z"),  # an item recorded before that noon
        step(JOURNAL, 2),
        step("TIMELINE", 3, "2026-02-10T17:00:00Z"),
        step(JOURNAL, 3),
        step(JOURNAL, 3),
    ]
    placed = _at_the_latest_instant(steps)
    assert [item.clock_at for item in placed if item.phase == JOURNAL] == [
        "2026-01-31T17:00:00Z",
        "2026-01-31T17:00:00Z",  # after item 2: still the close run's noon
        "2026-02-10T17:00:00Z",
        "2026-02-10T17:00:00Z",
    ]
    assert [item for item in placed if item.phase != JOURNAL] == [
        item for item in steps if item.phase != JOURNAL
    ]
    # a journal run before any step that has an instant has none of its own to take
    assert _at_the_latest_instant([step(JOURNAL, 1)])[0].clock_at is None


def test_the_reasons_of_a_period_that_locks_or_reopens_say_what_is_true() -> None:
    """The supervisor's ruling of 2026-10-02, point 4. The two reasons said "lock_period has no
    domain command" and "reopen_period has no domain command"; the product has had the commands
    since BUILD_SPEC CLO-6 and CLO-7 — a lock, a permanent lock and a reopen, each a request an
    approval decides. What the plan lacks differs by the item: a period state names its entity,
    book and period and the plan builds no sequence for it; a key's own command names no
    parameters (§9.5.3). No platform key holds either, so no outcome moves."""
    assert all(handler_exists(command) for command in (*LOCK_COMMANDS, REOPEN_COMMAND))
    for command in LOCK_COMMANDS:
        assert command.rsplit(".", 1)[1] in LOCK_GAP
    assert REOPEN_COMMAND.rsplit(".", 1)[1] in REOPEN_GAP
    assert LOCK_COMMANDS[0].rsplit(".", 1)[1] in LOCK_COMMAND_GAP
    assert REOPEN_COMMAND.rsplit(".", 1)[1] in REOPEN_COMMAND_GAP
    for reason in (LOCK_GAP, REOPEN_GAP, LOCK_COMMAND_GAP, REOPEN_COMMAND_GAP):
        assert "no domain command" not in reason
    assert {
        state: gap for state, (handler, gap) in PERIOD_STATE_HANDLERS.items() if not handler
    } == {"closed": LOCK_GAP, "permanently_locked": LOCK_GAP, "reopened": REOPEN_GAP}
    assert COMMAND_HANDLERS["lock_period"] == ((), LOCK_COMMAND_GAP)
    assert COMMAND_HANDLERS["reopen_period"] == ((), REOPEN_COMMAND_GAP)
    for key_id in PLATFORM_KEY_IDS:
        gaps = plan(load_platform_key(key_id)).gaps
        assert not {LOCK_GAP, REOPEN_GAP, LOCK_COMMAND_GAP, REOPEN_COMMAND_GAP} & set(gaps), key_id


def test_a_close_runs_clock_and_the_run_two_checkpoints_share() -> None:
    """Ruling (c): the application instant of the close run is local noon of the checkpoint's
    as-of date in the entity's zone, at least one second after the item it follows. In POS-012
    the last item stands at that noon itself, so the run is one second later. Where the
    checkpoint follows an earlier item the run stands at noon of the as-of date — which may be
    the very instant of the next item, whose own record time follows the same rule. And two
    checkpoints after one item, with blocks of one entity and period, share one run."""
    loaded = load_platform_key(POS_012)
    first, second = loaded.key.checkpoints
    assert (first.after_seq, first.as_of, second.after_seq) == (9, "2026-01-31", 11)
    times = runners._Assembler(loaded).times
    assert times[9] == datetime(2026, 1, 31, 17, tzinfo=UTC)  # noon in New York
    (run,) = plan(loaded).steps_of(CLOSE)
    assert run.clock_at == "2026-01-31T17:00:01Z"
    # After item 8 (20 January) the checkpoint's as-of noon is later than the item: noon it is.
    early = dataclasses.replace(
        loaded,
        key=loaded.key.model_copy(
            update={"checkpoints": (first.model_copy(update={"after_seq": 8}), second)}
        ),
    )
    assert times[8] == datetime(2026, 1, 20, 17, 0, 5, tzinfo=UTC)  # 20 January, noon and after
    (run,) = plan(early).steps_of(CLOSE)
    assert (run.seq, run.clock_at) == (8, "2026-01-31T17:00:00Z")
    following = next(step for step in plan(early).steps if step.seq == 9)
    assert following.clock_at == run.clock_at  # item 9 keeps its own record time
    # Two checkpoints after item 9 that expect the same pass: one run, named for the first.
    twice = dataclasses.replace(
        loaded,
        key=loaded.key.model_copy(
            update={
                "checkpoints": (first, first.model_copy(update={"name": "end-of-p1-again"}), second)
            }
        ),
    )
    (run,) = plan(twice).steps_of(CLOSE)
    assert (run.seq, run.detail["checkpoint"]) == (9, "end-of-p1")


def test_bookings_activations_and_events_use_the_command_layer(
    plans: dict[str, CommandPlan],
) -> None:
    """The approval IS the activation (04 §16.1; DG-CMD-09): the approver's decision appends
    CONTRACT_ACTIVATED and computes in its own transaction, so that step stamps known_at and
    no step calls the activation hook by itself — a second call after the decision is refused as
    stale. The SYSTEM principal runs the compute job after a recorded event, nothing else."""
    timeline = plans[POS_012].steps_of("TIMELINE")
    booked = [step for step in timeline if step.handler.endswith(".book_contract")]
    submitted = [step for step in timeline if step.handler.endswith(".submit_activation")]
    recorded = [step for step in timeline if step.handler.endswith(".record_events")]
    computed = [step for step in timeline if step.handler.endswith(".compute_group")]
    assert len(booked) == 2 and all(step.captures_known_at for step in booked)
    assert len(submitted) == 2 and all(step.actor == PREPARER for step in submitted)
    assert not any(step.captures_known_at for step in submitted)
    approvals = [step for step in timeline if step.handler.endswith(".decide")]
    assert [step.detail.get("emits") for step in approvals] == ["CONTRACT_ACTIVATED"] * 2
    assert [step.detail["contract"] for step in approvals] == ["C-POS-012-X", "C-POS-012-Y"]
    assert all(step.actor == APPROVER and step.captures_known_at for step in approvals)
    assert [step.seq for step in approvals] == [step.seq for step in submitted] == [2, 4]
    assert not [step for step in plans[POS_012].steps if step.handler.endswith(".activate")]
    assert len(recorded) == len(computed) == 7
    # BUILD_SPEC CTR-6 (supervisor ruling of 2026-10-01): no item of the key is marked manual, so
    # every event is an integrated source's and is sent by the world's API client (PRD ACT-10) —
    # a person's delivery or progress event would wait for another user's approval.
    assert all(step.actor == INTEGRATION for step in recorded)
    assert all(step.captures_known_at for step in recorded)
    assert all(step.actor == "system" for step in computed)
    assert {step.actor for step in timeline} == {PREPARER, APPROVER, INTEGRATION, "system"}


def test_world_configuration_is_published_through_lifecycles(plans: dict[str, CommandPlan]) -> None:
    """Every configuration version is created and submitted by ak-preparer and approved by
    ak-approver; SSP book versions by ak-ssp-analyst and ak-ssp-approver (D-98 candidate 107a, the
    only catalogue roles carrying ``ssp.create`` / ``ssp.approve``); publication follows
    (DG-AK-41 rev 1.42)."""
    world = plans[EX21].steps_of("WORLD")
    handlers = [step.handler.rsplit(".", 1)[1] for step in world]
    for name in (
        "create_pob_template_version",
        "submit_pob_template_version",
        "publish_pob_template_version",
    ):
        assert name in handlers
    assert (
        "submit_account_mapping_version" in handlers
        and "publish_account_mapping_version" in handlers
    )
    assert "create_policy" in handlers and "publish_policy" in handlers  # billing.posting ERP
    submits = [
        step
        for step in world
        if step.handler.endswith(
            (
                "_submit",
                "submit_ssp_book_version",
                "submit_policy",
                "submit_pob_template_version",
                "submit_account_mapping_version",
            )
        )
    ]
    ssp_submits = [s for s in submits if s.handler.endswith("submit_ssp_book_version")]
    assert ssp_submits and all(step.actor == SSP_ANALYST for step in ssp_submits)
    others = [s for s in submits if s not in ssp_submits]
    assert others and all(step.actor == PREPARER for step in others)
    decisions = [step for step in world if step.handler.endswith(".decide")]
    ssp_approvals = [step for step in decisions if step.subject.startswith("ssp_book ")]
    assert ssp_approvals and all(step.actor == SSP_APPROVER for step in ssp_approvals)
    configuration = [step for step in decisions if step not in ssp_approvals]
    assert configuration and all(step.actor == APPROVER for step in configuration)
    # REQ-SSP-008: a version is submitted with its study — uploaded, attached, then submitted, by
    # the analyst — and approved by a decision; nothing calls the engine's approval hook itself.
    for approval in ssp_approvals:
        index = world.index(approval)
        before = world[index - 3 : index]
        assert [step.handler.rsplit(".", 1)[1] for step in before] == [
            "upload_file",
            "attach",
            "submit_ssp_book_version",
        ]
        assert {step.actor for step in before} == {SSP_ANALYST}
        assert {step.subject for step in before} == {approval.subject}
    assert not [step for step in world if step.handler.endswith("publication.approve")]
    assert [step for step in world if step.gap is not None] == []


def test_checkpoint_blocks_name_their_reads_and_runs(plans: dict[str, CommandPlan]) -> None:
    """Journals blocks are read per (entity, period, mode) from the run their own step of the
    plan made (item AK-JOURNAL-RUN-PLAN-1; until it the checkpoint created the run itself);
    reports blocks become report runs compared with ``report_cells.compare_block``; contracts and
    subledger blocks are reads."""
    dlt = plans[DLT].steps_of("CHECKPOINT")
    journal_reads = [step for step in dlt if step.handler == H["read_journal"]]
    assert handler_exists(H["read_journal"])
    assert [(s.detail["entity"], s.detail["mode"]) for s in journal_reads] == [
        ("ME1", "GROSS"),
        ("ME1", "DELTA"),
        ("ME2", "GROSS"),
        ("ME2", "DELTA"),
    ]
    assert {step.detail["book"] for step in dlt} == {"ASC606", "LEGACY"}
    ex21 = plans[EX21].steps_of("CHECKPOINT")
    reports = [
        step.detail["report_code"] for step in ex21 if step.handler.endswith("framework.create_run")
    ]
    assert reports == [
        "contract_balance_rollforward",
        "revenue_from_opening_liability",
        "disaggregation",
        "disaggregation",
    ]
    assert all(code in framework.BUILDERS for code in reports)
    assert [step for step in ex21 if step.gap is not None] == []
    compares = [step for step in ex21 if step.handler.endswith("report_cells.compare_block")]
    assert len(compares) == 4 and compares[0].detail["known_at"] == compares[0].clock_at
    ex42 = plans[EX42].steps_of("CHECKPOINT")
    (rpo,) = [step for step in ex42 if step.handler.endswith("framework.create_run")]
    assert (
        rpo.detail["parameters"].startswith("book=ASC606")
        and "time_bands=" in rpo.detail["parameters"]
    )
    pos = plans[POS_012].steps_of("CHECKPOINT")
    # end-of-p1 carries contracts (with balances) and a subledger block; end-of-p2 contracts only.
    assert [step.subject.split()[-1] for step in pos] == [
        "contracts",
        "contracts.balances",
        "subledger",
        "contracts",
        "contracts.balances",
    ]
    assert [step.detail["as_of"] for step in pos] == ["2026-01-31"] * 3 + ["2026-02-28"] * 2


def test_gaps_per_key(plans: dict[str, CommandPlan]) -> None:
    """Where each key stops (PLAT-G4-1: the runner gap is retired): four keys have no gap before
    the database; POS-CHK-117 needs the balance_aging builder (RPS-12) over persisted layers
    (CTR-14); no plan needs lock, reopen or close-run commands."""
    assert plans[POS_012].gaps == ()
    assert plans[DLT].gaps == ()
    assert plans[EX21].gaps == ()
    assert plans[EX42].gaps == ()
    assert len(plans[POS_117].gaps) == 1
    assert plans[POS_117].gaps == ("RPS-12: balance_aging builder is not registered",)
    assert "balance_aging" not in framework.BUILDERS
    for item in plans.values():
        assert not any("CLO-6" in gap or "CLO-7" in gap or "CLO-19" in gap for gap in item.gaps)


def test_report_gaps_name_unregistered_builders_only() -> None:
    """``REPORT_GAPS`` explains why a report of the catalogue cannot run yet: an entry for a
    registered builder would state a gap that no longer exists (the in-memory platform adds the
    entry to its refusal without asking the framework). ``contract_cost_rollforward`` (RPS-12) and
    ``revenue_from_prior_period_obligations`` (EDS-4 / RPS-3) are registered and have none."""
    assert not set(REPORT_GAPS) & set(framework.BUILDERS)
    assert set(REPORT_GAPS) == {"balance_aging"}
    for code in ("contract_cost_rollforward", "revenue_from_prior_period_obligations"):
        assert code in framework.BUILDERS
        assert code not in REPORT_GAPS


def test_engine_keys_are_refused() -> None:
    engine_key = next(item for item in load_all() if item.key.runner == "engine")
    with pytest.raises(ValueError, match="not planned here"):
        plan(engine_key)
