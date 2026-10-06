"""The journal runs of a platform plan, against the product (dev-guide DG-AK-41; item
AK-JOURNAL-RUN-PLAN-1). DB-bound.

A journals block is answered by a step of the plan where the checkpoint stands in the timeline:
after the checkpoint's last item and its close run, before the next item. One run journalises a
seal (04 DB-16), so the step reads the run that stands when that run is the period's journal in
the block's form, and else cancels what stands and creates the block's own; and a run's cutoff
is compared with ``sealed_at`` — the application clock's — so the step gives none and the run
holds what is sealed at the step's instant.

The witness is a STAND-IN. The one platform key with journals blocks, GT07, stops before its
first item (its contract's nondistinct obligation; dev-guide DG-AK-41), so no authored key
reaches a journals block. Here POS-CHK-012 is given two in memory — GROSS and DELTA of US01
FY2026-P01 at end-of-p1 — whose expected lines are the ORACLE'S own for that checkpoint. The
key's world, contracts and timeline run through the real adapter under the stand-in personas
(``support.answer_keys.stand_in``) and the runner compares every block. It witnesses the runner
— the place of a run, its cutoff, the read, the cancel and the create — and that the product's
journal is the oracle's; it does not witness a journal's figures against an authored key, nor a
DELTA run beside a LEGACY book (POS-CHK-012 keeps one book).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from fractions import Fraction

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import close_run, journal_run, subledger_posting_seal
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.answer_keys.loader import LoadedKey
from support.answer_keys.models import JournalBlock, JournalRun
from support.answer_keys.models import JournalLine as ExpectedLine
from support.answer_keys.platform_plan import (
    CLOSE,
    JOURNAL,
    PLATFORM_KEY_IDS,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import (
    COMPARED,
    EXECUTED,
    InMemoryPlatform,
    JournalLine,
    journal_lines,
    platform_outcome,
    run_platform,
)
from support.answer_keys.stand_in import StandInPlatform, stand_in_world
from support.answer_keys.workspace_adapter import JournalAnswer
from support.db import TestDatabase

POS_012 = PLATFORM_KEY_IDS[0]
ENTITY, PERIOD = "US01", "FY2026-P01"
GRAIN = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"
# The step's application instant: the close run's — noon of 31 Jan 2026 in New York, one second
# after item 9 — the latest of any step before it.
AT = datetime(2026, 1, 31, 17, 0, 1, tzinfo=UTC)
# January's journal of US01 as the oracle's books hold it at end-of-p1, the netting reclass in
# it (debit positive): the contract asset and liability of the key's own subledger block
# (CONTRACT_ASSET/1200 dr 30,000.00; CONTRACT_LIABILITY/2100 dr 50,000.00) and the revenue of
# the two contracts.
JANUARY = (
    JournalLine("1200", Fraction(30000), "USD", None),
    JournalLine("2100", Fraction(50000), "USD", None),
    JournalLine("4010", Fraction(-20000), "USD", None),
    JournalLine("4020", Fraction(-60000), "USD", None),
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _expected(lines: tuple[JournalLine, ...]) -> tuple[ExpectedLine, ...]:
    """The oracle's lines as a key states them: an account with its debit or its credit."""
    return tuple(
        ExpectedLine(account=line.account, dr=f"{line.net:.2f}")
        if line.net > 0
        else ExpectedLine(account=line.account, cr=f"{-line.net:.2f}")
        for line in lines
    )


def _with_journals(loaded: LoadedKey) -> LoadedKey:
    """POS-CHK-012 with a GROSS and a DELTA journals block at end-of-p1, each expecting the
    oracle's own lines for that checkpoint — computed here from the key as authored."""
    first, second = loaded.key.checkpoints
    oracle = InMemoryPlatform(loaded).checkpoint_run(first)
    blocks = []
    for mode in ("GROSS", "DELTA"):
        lines = journal_lines(
            oracle, entity=ENTITY, period_key=PERIOD, mode=mode, primary_book="ASC606", grain=GRAIN
        )
        assert lines == JANUARY, mode  # one book: a DELTA run adds no LEGACY line
        run = JournalRun(entity=ENTITY, period_key=PERIOD, mode=mode, grain=GRAIN)
        blocks.append(JournalBlock(run=run, match="exact", lines=_expected(lines)))
    varied = first.model_copy(update={"journals": tuple(blocks)})
    return dataclasses.replace(
        loaded, key=loaded.key.model_copy(update={"checkpoints": (varied, second)})
    )


def test_the_journals_blocks_of_a_checkpoint_are_answered_where_the_checkpoint_stands(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    loaded = _with_journals(load_platform_key(POS_012))
    steps = plan(loaded).steps
    at = next(index for index, step in enumerate(steps) if step.phase == CLOSE)
    assert [(step.phase, step.subject, step.clock_at) for step in steps[at + 1 : at + 3]] == [
        (JOURNAL, f"journals {ENTITY} {PERIOD} GROSS", "2026-01-31T17:00:01Z"),
        (JOURNAL, f"journals {ENTITY} {PERIOD} DELTA", "2026-01-31T17:00:01Z"),
    ]
    assert (steps[at + 3].phase, steps[at + 3].seq) != (JOURNAL, 9)  # then item 10

    adapter, place = stand_in_world(app, keyring, clock, app_settings, loaded)
    result = run_platform(loaded, StandInPlatform(loaded, adapter))
    assert {item.status for item in result.executed} == {EXECUTED}

    # The two steps ran right after the close run and before item 10, and stamped nothing: the
    # checkpoint keeps the stamp its close run took.
    order = [entry.call.step for entry in adapter.ledger]
    closed = next(index for index, step in enumerate(order) if step.phase == CLOSE)
    assert [step.phase for step in order[closed + 1 : closed + 3]] == [JOURNAL, JOURNAL]
    assert order[closed + 3].seq == 10
    made = [entry for entry in adapter.ledger if entry.call.step.phase == JOURNAL]
    assert [(entry.app_at, entry.known_at) for entry in made] == [(AT, None), (AT, None)]
    assert result.known_at[9] == adapter.ledger[closed].known_at

    # What the product holds. The close run calculated its own draft run, GROSS in the block's
    # grain: the GROSS block READ it. The DELTA block could not use it: that run was cancelled
    # and the DELTA run created, at the step's application instant and with no cutoff of its
    # own — the command took the clock — from the first seal again.
    (run,) = place.rows(select(close_run))
    runs = place.rows(select(journal_run).order_by(journal_run.c.run_no))
    assert [
        (
            str(row["state"]),
            str(row["mode"]),
            str(row["grain"]),
            row["close_run_id"],
            int(row["from_chain_seq"]),
            int(row["to_chain_seq"]),
            row["cutoff_known_at"],
        )
        for row in runs
    ] == [
        ("cancelled", "GROSS", GRAIN, run["id"], 0, 3, AT),
        ("draft", "DELTA", GRAIN, None, 0, 3, AT),
    ]
    own, delta = runs
    assert (delta["delta_from_chain_seq"], delta["delta_to_chain_seq"]) == (0, 0)  # no LEGACY book
    read, created = (entry.result for entry in made)
    assert read == JournalAnswer(own["id"], True, (), JANUARY)
    assert created == JournalAnswer(delta["id"], False, (own["id"],), JANUARY)

    # The cutoff. Items 10 and 11 sealed after the checkpoint, with a later business time; a
    # run made in place does not hold them, and nothing was created when the checkpoints were
    # read, after the whole plan: two runs, as above. (A run made then, with the checkpoint's
    # server stamp as its cutoff, covered every seal — measured before this item.)
    sealed = place.scalar(select(func.max(subledger_posting_seal.c.chain_seq)))
    assert int(sealed) > int(delta["to_chain_seq"]) == 3

    # The comparison: every block of both checkpoints, the two journals blocks among them.
    assert {
        f"{checkpoint.name} {block.block}": (block.status, len(block.mismatches))
        for checkpoint in result.checkpoints
        for block in checkpoint.blocks
    } == {
        "end-of-p1 contracts": (COMPARED, 0),
        "end-of-p1 subledger": (COMPARED, 0),
        f"end-of-p1 journals {ENTITY} {PERIOD} GROSS": (COMPARED, 0),
        f"end-of-p1 journals {ENTITY} {PERIOD} DELTA": (COMPARED, 0),
        "end-of-p2 contracts": (COMPARED, 0),
    }
    assert platform_outcome(loaded, result) == (
        "passed",
        "every block compared clean on the db platform",
    )
