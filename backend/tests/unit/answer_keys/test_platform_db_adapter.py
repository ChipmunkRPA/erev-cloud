"""``DbPlatform`` over a ``DomainAdapter`` (dev-guide DG-AK-41; record §14 "DbPlatform ownership").

``MockAdapter`` records the dispatch and answers from fixtures, so the database platform's contract
is proven without a database or any live call: every plan step reaches the adapter in plan order,
``known_at[seq]`` is the adapter's server clock after each item's commit (strictly increasing and
never before the frozen application clock), an ``expect_problem`` step is verified through
``adapter.refusal`` (PLAT-1: expected code and unchanged state) and fails the key otherwise, and
the reads are refused by the mock (``not_run``) because it has no rows. The Workspace adapter over
the lane's database is the next slice and stays behind the Ray-side boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, H, Step, load_platform_key, plan
from support.answer_keys.platform_runner import (
    EXECUTED,
    FAILED_STEP,
    NOT_PROVISIONED,
    NOT_RUN,
    DbPlatform,
    MockAdapter,
    NotProvisioned,
    first_not_run,
    platform_outcome,
    run_platform,
)

POS_012 = PLATFORM_KEY_IDS[0]
START = datetime(2025, 12, 31, 12, tzinfo=UTC)


def _with_refusal(tmp_path: Path) -> LoadedKey:
    source = yaml.safe_load((ANSWER_KEY_ROOT / "pos" / f"{POS_012}.yaml").read_text())
    source["timeline"].append(
        {
            "seq": 12,
            "kind": "command",
            "command": {
                "name": "lock_period",
                "params": {"entity": "US01", "book": "ASC606", "period_key": "FY2026-P01"},
            },
            "expect_problem": {"code": "close-gates-failed", "status": 409},
        }
    )
    target = tmp_path / "pos" / f"{POS_012}.yaml"
    target.parent.mkdir()
    target.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    return load(target)


def test_db_platform_dispatches_every_step_in_plan_order_and_stamps_from_the_server_clock() -> None:
    loaded = load_platform_key(POS_012)
    adapter = MockAdapter(start=START)
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    steps = [step for step in plan(loaded).steps if step.phase != "CHECKPOINT"]
    assert result.platform == "db"
    assert [item.step for item in result.executed] == steps
    assert all(item.status == EXECUTED for item in result.executed)
    dispatched = [step for step in steps if step.phase != "RUNNER"]
    assert adapter.calls == [(step.handler, step.subject) for step in dispatched]
    # One stamp per committed timeline item, strictly increasing, never before the app clock.
    seqs = [item.seq for item in loaded.key.timeline]
    assert sorted(result.known_at) == seqs
    stamps = [result.known_at[seq] for seq in seqs]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
    clocks = {item.step.seq: item.at for item in result.executed if item.known_at is not None}
    assert all(result.known_at[seq] >= clocks[seq] or result.known_at[seq] > START for seq in seqs)
    # The mock has no rows: every checkpoint block is not run, so the key is not_run, never passed.
    assert all(
        block.status == NOT_RUN for checkpoint in result.checkpoints for block in checkpoint.blocks
    )
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN and "blocks compared clean: none" in message
    # A mock holds no rows — no database stands behind it — and its reads say so (item
    # AK-NOT-RUN-REASON-1): the checkpoint reads here, a journal and a report block below.
    assert {block.reason for checkpoint in result.checkpoints for block in checkpoint.blocks} == {
        f"{NOT_PROVISIONED}: checkpoint end-of-p1 reads (mock adapter has no rows)",
        f"{NOT_PROVISIONED}: checkpoint end-of-p2 reads (mock adapter has no rows)",
    }
    assert message.startswith(
        f"{NOT_PROVISIONED}: checkpoint end-of-p1 reads (mock adapter has no rows); db platform: "
    )
    dlt = load_platform_key(next(key for key in PLATFORM_KEY_IDS if key.startswith("DLT-")))
    with_journals = next(checkpoint for checkpoint in dlt.key.checkpoints if checkpoint.journals)
    assert with_journals.journals is not None
    with pytest.raises(NotProvisioned) as journal:
        adapter.journal_run(with_journals, with_journals.journals[0])
    assert str(journal.value) == (
        f"{NOT_PROVISIONED}: journals ME1 FY2023-P01 GROSS (mock adapter has no journal rows)"
    )
    pos_117 = load_platform_key(next(key for key in PLATFORM_KEY_IDS if "CHK-117" in key))
    aged = run_platform(pos_117, DbPlatform(pos_117, MockAdapter(start=START)))
    (report,) = [
        block.reason
        for checkpoint in aged.checkpoints
        for block in checkpoint.blocks
        if block.block.startswith("reports ")
    ]
    assert report == (f"{NOT_PROVISIONED}: reports balance_aging (mock adapter has no report rows)")


def test_plat_1_verified_refusal_counts_executed_without_a_stamp(tmp_path: Path) -> None:
    loaded = _with_refusal(tmp_path)
    adapter = MockAdapter(start=START, refusals={12: ("close-gates-failed", True)})
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == EXECUTED and refusal.known_at is None
    assert 12 not in result.known_at
    assert ("refusal:", "seq 12 expect_problem") in [
        (handler.split("erev_api")[0], subject) for handler, subject in adapter.calls
    ]


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (("period-locked", True), "expected refusal close-gates-failed, got period-locked"),
        ((None, True), "got no refusal"),
        (("close-gates-failed", False), "STATE CHANGED"),
    ],
)
def test_plat_1_wrong_code_or_changed_state_fails_the_key(
    tmp_path: Path, answer: tuple[str | None, bool], reason: str
) -> None:
    loaded = _with_refusal(tmp_path)
    adapter = MockAdapter(start=START, refusals={12: answer})
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == FAILED_STEP and reason in (refusal.reason or "")
    status, message = platform_outcome(loaded, result)
    assert status == "failed" and message.startswith("refusal verification failed (PLAT-1)")


def test_db_platform_without_an_adapter_stays_not_provisioned() -> None:
    loaded = load_platform_key(POS_012)
    result = run_platform(loaded, DbPlatform(loaded))
    assert all(item.status == NOT_RUN for item in result.executed)
    assert all("erev_api." in (item.reason or "") for item in result.executed[1:])
    assert result.known_at == {}


class _Refusing(MockAdapter):
    """The mock adapter over a world that lacks one step: it refuses that step by name."""

    def __init__(self, refused: Step) -> None:
        super().__init__(start=START)
        self.refused = refused

    def run(self, step: Step) -> None:
        if step == self.refused:
            raise NotProvisioned(f"{step.phase} {step.subject}: the world lacks it", step.handler)
        super().run(step)


def test_the_database_platform_stops_at_the_first_step_it_refuses() -> None:
    """DG-AK-41 (rev 1.213): after the first step the platform refuses by name, no later step is
    run — each is not run and names that step. A world that lacks a step would answer the later
    ones with refusals of the product's own, which say nothing of the key. The key ends not run,
    never failed, and its outcome names the refusal it waits for."""
    loaded = load_platform_key(POS_012)
    steps = [step for step in plan(loaded).steps if step.phase != "CHECKPOINT"]
    refused = next(step for step in steps if step.handler == H["judgement"])
    assert (refused.phase, refused.subject, refused.seq) == ("CONTRACTS", "contract C-POS-012-X", 2)
    at = steps.index(refused)
    adapter = _Refusing(refused)
    result = run_platform(loaded, DbPlatform(loaded, adapter))
    statuses = [item.status for item in result.executed]
    assert statuses == [EXECUTED] * at + [NOT_RUN] * (len(steps) - at)
    # nothing after the refused step reached the adapter
    assert adapter.calls == [(step.handler, step.subject) for step in steps[1:at]]
    first, *later = result.executed[at:]
    # each reason opens with its own words: the database is there (item AK-NOT-RUN-REASON-1)
    assert first.reason == (
        f"not run — CONTRACTS contract C-POS-012-X: the world lacks it ({H['judgement']})"
    )
    for item in later:
        where = f"{item.step.phase} {item.step.subject}"
        assert item.reason == (
            f"not run — {where}: not run after CONTRACTS contract C-POS-012-X "
            f"(create_judgement) ({item.step.handler})"
        )
    # Only the booking before it was stamped; without their items the checkpoints are not run.
    assert sorted(result.known_at) == [1]
    blocks = [block for checkpoint in result.checkpoints for block in checkpoint.blocks]
    assert blocks and all(block.status == NOT_RUN for block in blocks)
    assert "no known_at for after_seq 9" in (blocks[0].reason or "")
    assert result.mismatches == ()
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN
    waits_for = "CONTRACTS contract C-POS-012-X: the world lacks it"
    assert first_not_run(result) == f"{waits_for} ({H['judgement']})"
    assert message.startswith(f"not run — {waits_for} ({H['judgement']}); db platform: ")
    assert f"{at} steps applied, {len(steps) - at} refused" in message


def test_the_runner_marker_and_a_platform_without_an_adapter_are_not_a_stop() -> None:
    """The RUNNER marker runs nothing and is never refused for an earlier stop; and a platform
    without an adapter refuses every step with the handler it would call — its own reason, not
    "not run after"."""
    loaded = load_platform_key(POS_012)
    result = run_platform(loaded, DbPlatform(loaded))
    reasons = [item.reason or "" for item in result.executed]
    assert all(reason.startswith(NOT_PROVISIONED) for reason in reasons)
    assert not any("not run after" in reason for reason in reasons)
    platform = DbPlatform(loaded, MockAdapter(start=START))
    platform.halted = "WORLD something (a_command)"
    marker = plan(loaded).steps[0]
    assert marker.phase == "RUNNER" and platform.execute(marker) is None
    with pytest.raises(NotProvisioned, match=r"not run after WORLD something \(a_command\)"):
        platform.execute(plan(loaded).steps[1])


def test_a_step_that_is_not_run_opens_with_its_own_reason() -> None:
    """Item AK-NOT-RUN-REASON-1 (the supervisor's ruling of 2026-10-02 on the runner's report). A
    step or a block that is not run says why in its first words, and so does the key's outcome.
    "Databases not provisioned" is the reason of one case alone: there is no database behind the
    platform — a database platform without its adapter, a factory that could build none. Until
    this item every refusal carried those words, also where the database was there and the
    reason was the world, the runner's bound or a block that waits for a close run."""
    named = NotProvisioned("CONTRACTS contract C-1: the world lacks it", "a.handler")
    assert str(named) == "not run — CONTRACTS contract C-1: the world lacks it (a.handler)"
    assert named.unprovisioned is False
    absent = NotProvisioned("PROVISION tenant", "a.handler", unprovisioned=True)
    assert str(absent) == "not run — databases not provisioned: PROVISION tenant (a.handler)"
    assert (absent.step, absent.handler, absent.unprovisioned) == (
        "PROVISION tenant",
        "a.handler",
        True,
    )
    assert NOT_PROVISIONED == "not run — databases not provisioned"

    loaded = load_platform_key(POS_012)
    steps = [step for step in plan(loaded).steps if step.phase != "CHECKPOINT"]
    # No adapter and no factory: every step and every block waits for the databases.
    without = run_platform(loaded, DbPlatform(loaded))
    reasons = [item.reason or "" for item in without.executed]
    reasons += [b.reason or "" for c in without.checkpoints for b in c.blocks]
    assert reasons and all(reason.startswith(f"{NOT_PROVISIONED}: ") for reason in reasons)
    assert platform_outcome(loaded, without)[1].startswith(f"{NOT_PROVISIONED}: RUNNER ")

    # A factory that can build no adapter: its own sentence, under the same words — whatever
    # the factory's refusal said of itself.
    def refusing(_loaded: object) -> MockAdapter:
        raise NotProvisioned(
            "database platform: database erev_rv_x_test is not available (OperationalError)",
            "erev_api.db.session.owner_engine",
        )

    refused = run_platform(loaded, DbPlatform(loaded, factory=refusing))
    provision = next(item for item in refused.executed if item.step.phase == "PROVISION")
    assert provision.reason == (
        f"{NOT_PROVISIONED}: PROVISION {provision.step.subject}: database platform: database "
        f"erev_rv_x_test is not available (OperationalError) ({H['provision']})"
    )
    # An adapter is there and its world lacks one step: every reason is the step's own.
    lacking = next(step for step in steps if step.handler == H["judgement"])
    stopped = run_platform(loaded, DbPlatform(loaded, _Refusing(lacking)))
    own = [item.reason or "" for item in stopped.executed if item.status == NOT_RUN]
    own += [b.reason or "" for c in stopped.checkpoints for b in c.blocks]
    assert own and all(reason.startswith("not run — ") for reason in own)
    assert not any("databases not provisioned" in reason for reason in own)
    status, message = platform_outcome(loaded, stopped)
    assert status == NOT_RUN
    assert message.startswith(
        f"not run — CONTRACTS contract C-POS-012-X: the world lacks it ({H['judgement']}); "
        "db platform: "
    )
    assert "databases not provisioned" not in message
    assert message.endswith(
        "; blocks compared clean: none; blocks not run: end-of-p1 contracts, end-of-p1 "
        "subledger, end-of-p2 contracts"
    )
