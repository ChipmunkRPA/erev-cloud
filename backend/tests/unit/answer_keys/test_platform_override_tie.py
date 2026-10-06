"""Register index 308 (POLICY-OVERRIDE-WITHDRAW-1; supervisor ruling R-126 (c); dev-guide §9.5.4
rev 1.299): how a platform key that declares policy overrides is judged.

Release 1.0 offers no policy override at contract or obligation level, and the plan creates none
(``test_platform_following_models``, "overrides"). Such a key is still run — the three keys that
declare overrides are the runner's own sample keys — and it is never passed:
``platform_runner.key_verdict``, the judge of the KEY, puts ONE finding beside the figures'
mismatches whatever the run's outcome was, while ``platform_outcome``, the judge of the RUN,
keeps its word. The pytest node of a key fails by the verdict and the report records it
(``tests/answer_keys/test_answer_keys.py``).

- the pin by name: POS-CHK-012, DLT-CHK-020-CHK-022-GT07 and POS-CHK-117 carry the finding, with
  the overrides each declares (2, 3 and 3 of POL-122, each at an obligation); the two other
  platform keys carry none (``test_platform_plan`` pins that the corpus holds no sixth);
- a run that compared clean on the database platform is ``failed`` by the finding alone, and the
  same run of a key that declares none is ``passed``;
- the finding stands beside the figures whatever the run did: not run, a figure's mismatch, an
  engine stop, a refusal that failed its verification;
- the node fails by the verdict and records its mismatches and its message.

No database: a result is the in-memory platform's, the unprovisioned database platform's, or
built by hand.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from support.answer_keys.loader import LoadedKey
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, load_platform_key
from support.answer_keys.platform_runner import (
    COMPARED,
    DB,
    ERROR,
    FAILED_STEP,
    NOT_PROVISIONED,
    NOT_RUN,
    BlockOutcome,
    DbPlatform,
    PlatformCheckpoint,
    PlatformRunResult,
    key_verdict,
    override_finding,
    platform_outcome,
    run_platform,
)
from support.answer_keys.report import OUTCOMES, KeyOutcome
from support.answer_keys.runners import Mismatch

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
# The finding, word for word. ``expected`` lists what the key declares, in the key's order.
EXPECTED = {
    POS_012: (
        "2 APPROVED at booking (dev-guide §9.5.4): POL-122 balance.right_to_consideration at "
        "C-POS-012-X/X1-LICENCE, C-POS-012-X/X2-SERVICES"
    ),
    DLT: (
        "3 APPROVED at booking (dev-guide §9.5.4): POL-122 balance.right_to_consideration at "
        "CONTRACT-2/POB #1, CONTRACT-2/POB #2, CONTRACT-2/POB #3"
    ),
    POS_117: (
        "3 APPROVED at booking (dev-guide §9.5.4): POL-122 balance.right_to_consideration at "
        "C-POS-117/P1, C-POS-117/P2, C-POS-117/P3"
    ),
}
ACTUAL = (
    "none: policy overrides are not offered in release 1.0 (rule id POLICY_OVERRIDE_NOT_OFFERED; "
    "register index 308) and the plan creates none; the key waits for the next release's road "
    "for POL-122"
)
CLEAN = "every block compared clean on the db platform"
AT = datetime(2026, 1, 31, 12, tzinfo=UTC)


def _finding(key_id: str) -> Mismatch:
    return Mismatch(key_id, "world", "policy overrides", "created", EXPECTED[key_id], ACTUAL)


def _told(key_id: str) -> str:
    """The last clause of every message of a key that carries the finding."""
    return f"finding: policy overrides created: expected {EXPECTED[key_id]}, actual {ACTUAL}"


def _clean_on_the_database(loaded: LoadedKey) -> PlatformRunResult:
    """A run of the key that compared every block clean on the database platform, built by hand:
    one compared block per checkpoint, nothing refused, nothing left out."""
    checkpoints = tuple(
        PlatformCheckpoint(
            checkpoint.name, checkpoint.after_seq, AT, (BlockOutcome("contracts", COMPARED),)
        )
        for checkpoint in loaded.key.checkpoints
    )
    return PlatformRunResult(loaded.key.id, "platform", DB, (), {}, checkpoints, ("platform: db",))


@pytest.fixture(scope="module")
def in_memory() -> tuple[LoadedKey, PlatformRunResult]:
    """POS-CHK-012 run on the in-memory platform, without its overrides: every step executed,
    every block compared clean, the run not passed for want of a database."""
    loaded = load_platform_key(POS_012)
    return loaded, run_platform(loaded)


def test_the_three_keys_that_declare_overrides_carry_the_finding_and_the_two_others_none() -> None:
    """The pin by name. Of the five platform keys three declare policy overrides — all POL-122
    ``balance.right_to_consideration`` at an obligation — and each carries ONE finding that
    counts and names them; the two others declare none and carry none."""
    declared = {}
    for key_id in PLATFORM_KEY_IDS:
        key = load_platform_key(key_id).key
        declared[key_id] = sum(len(contract.policy_overrides or ()) for contract in key.contracts)
        assert override_finding(key) == (_finding(key_id) if key_id in EXPECTED else None), key_id
    assert declared == {POS_012: 2, DLT: 3, EX21: 0, EX42: 0, POS_117: 3}
    one = _finding(POS_012)
    assert one.render() == (
        f"{POS_012} world policy overrides created: expected {EXPECTED[POS_012]}, actual {ACTUAL}"
    )
    assert one.to_json() == {
        "checkpoint": "world",
        "object": "policy overrides",
        "field": "created",
        "expected": EXPECTED[POS_012],
        "actual": ACTUAL,
    }


@pytest.mark.parametrize("key_id", [POS_012, DLT, POS_117])
def test_a_clean_run_on_the_database_platform_is_failed_by_the_finding_alone(key_id: str) -> None:
    """Whatever its figures do: every block compared clean on the database platform — the RUN
    passed, and ``platform_outcome`` says so — and the KEY is ``failed`` by its one finding: its
    world was not built as the key declares it."""
    loaded = load_platform_key(key_id)
    result = _clean_on_the_database(loaded)
    assert result.mismatches == () and result.not_run == ()
    assert platform_outcome(loaded, result) == ("passed", CLEAN)  # the judge of the run
    assert key_verdict(loaded, result) == (
        "failed",
        (_finding(key_id),),
        f"{CLEAN}; {_told(key_id)}",
    )


@pytest.mark.parametrize("key_id", [EX21, EX42])
def test_a_key_that_declares_no_override_is_judged_as_its_run_is(key_id: str) -> None:
    """The control: the same clean run of a key that declares no policy override is ``passed``,
    with no finding and the run's own message."""
    loaded = load_platform_key(key_id)
    result = _clean_on_the_database(loaded)
    assert key_verdict(loaded, result) == ("passed", (), CLEAN)
    assert key_verdict(loaded, result)[::2] == platform_outcome(loaded, result)


def test_the_finding_stands_beside_the_figures_whatever_the_run_did(
    in_memory: tuple[LoadedKey, PlatformRunResult],
) -> None:
    """Not run, a figure's mismatch, an engine stop, a refusal that failed its verification: the
    verdict keeps the run's result, puts the finding after the figures' mismatches and ends the
    run's message with it. Nothing but ``passed`` changes its result."""
    loaded, result = in_memory
    finding, told = _finding(POS_012), _told(POS_012)

    # Not run on the in-memory platform: the blocks compare clean, no database stands behind.
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN and message.startswith(NOT_PROVISIONED) and result.mismatches == ()
    assert key_verdict(loaded, result) == (NOT_RUN, (finding,), f"{message}; {told}")

    # Not run on a database platform without its databases: nothing was applied.
    unprovisioned = run_platform(loaded, DbPlatform(loaded))
    status, message = platform_outcome(loaded, unprovisioned)
    assert status == NOT_RUN and "0 steps applied" in message
    assert key_verdict(loaded, unprovisioned) == (NOT_RUN, (finding,), f"{message}; {told}")

    # A figure's mismatch: the finding stands beside it, after it.
    figure = Mismatch(
        POS_012, "end-of-p1", "contract C-POS-012-X", "revenue_cum", "80000.00", "0.00"
    )
    first, *rest = result.checkpoints
    wrong = replace(first, blocks=(BlockOutcome("contracts", COMPARED, (figure,)),))
    mismatched = replace(result, checkpoints=(wrong, *rest))
    assert platform_outcome(loaded, mismatched) == (
        "failed",
        "1 mismatch on the in-memory platform",
    )
    assert key_verdict(loaded, mismatched) == (
        "failed",
        (figure, finding),
        f"1 mismatch on the in-memory platform; {told}",
    )

    # An engine stop.
    stopped_block = replace(first, blocks=(BlockOutcome("contracts", ERROR, reason="E-1 x"),))
    stopped = replace(result, checkpoints=(stopped_block, *rest))
    status, message = platform_outcome(loaded, stopped)
    assert (status, message) == (
        "failed",
        "engine stop on the in-memory platform: end-of-p1 contracts: E-1 x",
    )
    assert key_verdict(loaded, stopped) == ("failed", (finding,), f"{message}; {told}")

    # A refusal that was verified and wrong (PLAT-1).
    refused = replace(result.executed[-1], status=FAILED_STEP, reason="seq 12: wrong code")
    failing = replace(result, executed=(*result.executed[:-1], refused))
    status, message = platform_outcome(loaded, failing)
    assert (status, message) == (
        "failed",
        "refusal verification failed (PLAT-1): seq 12: wrong code",
    )
    assert key_verdict(loaded, failing) == ("failed", (finding,), f"{message}; {told}")


def _node_module() -> ModuleType:
    """``tests/answer_keys/test_answer_keys.py``, the module of the keys' pytest nodes, loaded
    under a name of its own (the test directories are no packages)."""
    path = Path(__file__).resolve().parents[2] / "answer_keys" / "test_answer_keys.py"
    spec = importlib.util.spec_from_file_location("answer_key_nodes_for_the_override_tie", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_the_node_fails_by_the_verdict_and_the_report_records_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_platform_key`` — what the node ``test_answer_key[<id>]`` runs for a platform key — on a
    run that compared clean on the database platform: POS-CHK-012 fails with the verdict's
    message and its outcome is recorded ``failed`` with the finding among the mismatches; EX21,
    which declares no override, passes and is recorded ``passed``."""
    node = _node_module()
    monkeypatch.setattr(node, "run_platform", _clean_on_the_database)
    outcomes: dict[str, KeyOutcome] = {}
    request: Any = SimpleNamespace(config=SimpleNamespace(stash={OUTCOMES: outcomes}))

    pos = load_platform_key(POS_012)
    with pytest.raises(pytest.fail.Exception) as failed:
        node._platform_key(pos, request)
    assert str(failed.value) == f"{POS_012}: failed: {CLEAN}; {_told(POS_012)}"
    assert outcomes[POS_012] == KeyOutcome(
        "failed", (_finding(POS_012),), f"{CLEAN}; {_told(POS_012)}", ("platform: db",)
    )

    ex21 = load_platform_key(EX21)
    node._platform_key(ex21, request)  # passed: the node does not fail
    assert outcomes[EX21] == KeyOutcome("passed", (), CLEAN, ("platform: db",))
