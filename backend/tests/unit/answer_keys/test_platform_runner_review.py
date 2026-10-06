"""Codex platform review of ca2e82c (PRODUCTION-F-RPS-E1-PLATFORM-REVIEW-ca2e82c.md): the two
runner-contract rules of record §14 and the journal helper's currency grain (lane F-RPS + ENG-E1).

- PLAT-1: an ``expect_problem`` step a platform cannot enforce and verify is ``not_run``, never
  ``executed``; the key cannot pass with such a step pending.
- PLAT-2: a ``period_states`` block reads the state as of the checkpoint's ``after_seq`` cutoff,
  never the timeline's final state.
- The journal helper's currency grain is tested in ``test_platform_journal_helper.py``.

The controls reuse the exact original POS-CHK-012 key plus the review's added inputs, written to a
temporary copy; the original file and its oracle are untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.platform_plan import (
    LOCK_COMMAND_GAP,
    PLATFORM_KEY_IDS,
    H,
    load_platform_key,
)
from support.answer_keys.platform_runner import (
    EXECUTED,
    NOT_PROVISIONED,
    NOT_RUN,
    InMemoryPlatform,
    platform_outcome,
    run_platform,
)

POS_012 = PLATFORM_KEY_IDS[0]
PERIOD = "FY2026-P01"


def _variant(
    tmp_path: Path,
    extra_items: list[dict[str, object]],
    checkpoints: list[dict[str, object]] | None = None,
) -> LoadedKey:
    """POS-CHK-012 with the review's added timeline items (and, optionally, checkpoint blocks)."""
    source = yaml.safe_load((ANSWER_KEY_ROOT / "pos" / f"{POS_012}.yaml").read_text())
    source["timeline"] = [*source["timeline"], *extra_items]
    if checkpoints is not None:
        source["checkpoints"] = checkpoints
    target = tmp_path / "pos" / f"{POS_012}.yaml"
    target.parent.mkdir()
    target.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    return load(target)


def test_plat_1_expected_refusal_is_not_run_on_the_in_memory_platform(tmp_path: Path) -> None:
    """A schema-clean ``lock_period`` with ``expect_problem`` close-gates-failed / 409 cannot be
    enforced or verified in memory: the step is ``not_run`` with the expected code in its reason,
    never ``executed``; the outcome stays ``not_run`` and names one refused step."""
    loaded = _variant(
        tmp_path,
        [
            {
                "seq": 12,
                "kind": "command",
                "command": {
                    "name": "lock_period",
                    "params": {"entity": "US01", "book": "ASC606", "period_key": PERIOD},
                },
                "expect_problem": {"code": "close-gates-failed", "status": 409},
            }
        ],
    )
    result = run_platform(loaded, InMemoryPlatform(loaded))
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == NOT_RUN
    assert "close-gates-failed" in "".join(result.notes)
    assert 12 not in result.known_at  # a refused item stamps nothing
    assert all(item.status == EXECUTED for item in result.executed if item.step.seq != 12)
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN and "1 refused" in message


def test_what_the_in_memory_platform_cannot_do_waits_for_the_databases(tmp_path: Path) -> None:
    """Item AK-NOT-RUN-REASON-1, beside PLAT-1. On the in-memory platform an event that expects
    a refusal and a built command wait for the database platform, and their reasons say so. A
    command the plan does not build has a reason of its own, which names no database."""
    items: dict[str, dict[str, object]] = {
        "event": {
            "seq": 12,
            "kind": "event",
            "contract": "C-POS-012-X",
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-02-28",
            "payload": {
                "invoice_number": "INV-X-004",
                "line_external_id": "INV-X-004-1",
                "obligation_key": "X1-LICENCE",
                "amount": "1.00",
                "issue_date": "2026-02-28",
            },
            "expect_problem": {"code": "validation-failed", "status": 422},
        },
        "command": {
            "seq": 12,
            "kind": "command",
            "command": {"name": "import_upload", "params": {"kind": "legacy_sku_ssp"}},
        },
        "gap": {
            "seq": 12,
            "kind": "command",
            "command": {
                "name": "lock_period",
                "params": {"entity": "US01", "book": "ASC606", "period_key": PERIOD},
            },
        },
    }
    reasons: dict[str, set[str]] = {}
    openings: dict[str, str] = {}
    for name, item in items.items():
        (tmp_path / name).mkdir()
        loaded = _variant(tmp_path / name, [item])
        result = run_platform(loaded, InMemoryPlatform(loaded))
        refused = [executed for executed in result.executed if executed.step.seq == 12]
        assert refused and {executed.status for executed in refused} == {NOT_RUN}, name
        reasons[name] = {executed.reason or "" for executed in refused}
        openings[name] = platform_outcome(loaded, result)[1]
    assert reasons["event"] == {
        f"{NOT_PROVISIONED}: expected refusal seq 12 validation-failed: the in-memory platform "
        "cannot enforce and verify the refusal (expected code + unchanged state, rule PLAT-1) "
        f"({H['record_events']})"
    }
    assert reasons["command"] == {
        f"{NOT_PROVISIONED}: command import_upload ({H['import_create']})"
    }
    (gap,) = reasons["gap"]
    # STALE EXPECTATION (the supervisor's ruling of 2026-10-02, point 4): until it the reason
    # read "(CLO-6: lock_period has no domain command …"; the product has the command.
    assert gap == f"not run — TIMELINE seq 12 command lock_period ({LOCK_COMMAND_GAP})"
    assert "databases not provisioned" not in gap
    # each outcome opens with its reason
    assert all(
        openings[name].startswith(f"{reason}; in-memory platform: ")
        for name in items
        for reason in reasons[name]
    )


def test_plat_2_period_state_reads_are_bound_to_the_checkpoint_cutoff(tmp_path: Path) -> None:
    """open → closing at seq 12: the block at after_seq 11 reads ``open`` and the block at
    after_seq 12 reads ``closing``; before the rule both read the final state."""
    loaded = _variant(
        tmp_path,
        [
            {
                "seq": 12,
                "kind": "period_state",
                "entity": "US01",
                "book": "ASC606",
                "period_key": PERIOD,
                "state": "closing",
            }
        ],
        checkpoints=[
            {
                "name": "before-close",
                "after_seq": 11,
                "as_of": "2026-01-31",
                "book": "ASC606",
                "period_states": [
                    {"entity": "US01", "book": "ASC606", "period_key": PERIOD, "state": "open"}
                ],
            },
            {
                "name": "closing",
                "after_seq": 12,
                "as_of": "2026-01-31",
                "book": "ASC606",
                "period_states": [
                    {"entity": "US01", "book": "ASC606", "period_key": PERIOD, "state": "closing"}
                ],
            },
        ],
    )
    result = run_platform(loaded, InMemoryPlatform(loaded))
    blocks = {checkpoint.name: checkpoint.blocks[0] for checkpoint in result.checkpoints}
    assert blocks["before-close"].status == "compared" and blocks["before-close"].mismatches == ()
    assert blocks["closing"].status == "compared" and blocks["closing"].mismatches == ()
    assert result.mismatches == ()


def test_five_keys_unchanged_under_the_rules() -> None:
    """The five keys carry no expect_problem item and no period_states block, so PLAT-1 and PLAT-2
    change none of their §13.3 outcomes."""
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        assert all(item.expect_problem is None for item in loaded.key.timeline), key_id
        assert all(checkpoint.period_states is None for checkpoint in loaded.key.checkpoints), (
            key_id
        )
    with pytest.raises(ValueError, match="platform keys"):
        load_platform_key("NOT-A-KEY")
