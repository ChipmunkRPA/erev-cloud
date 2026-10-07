"""The close run of a platform plan, against the product (dev-guide DG-AK-41 rev 1.246; item
AK-CLOSE-RUN-STEP-1; the supervisor's rulings of 2026-10-01 on the lane's measurement). DB-bound.

POS-CHK-012's end-of-p1 subledger block expects the netting reclass of January (POLICIES JET-06):
the oracle computes the period-end passes with every checkpoint, the product posts them in a
close run. Until this item the block was not run by name; compared, it differed from the ledger
by the reclass's two lines. Here the key's world, contracts and timeline run through the real
adapter under the stand-in personas (``support.answer_keys.stand_in``), with the
plan's close run among the steps — ``POST /close-runs`` as the preparer, its job worked to the
end, no lock — and the runner compares every block of both checkpoints.

What the test holds of the product beside the comparison: what a whole close run needs of a
world that has only what a key's plan made (nothing more), and what it leaves — the period open,
one reclass posting of the entity with its reversal in the next open period, the groups' marks,
a draft journal run — so that the items after it still meet their checkpoint.

The same run verifies both declared POL-122 overrides are created and independently approved
before activation. Every checkpoint must compare clean and the complete key verdict must pass.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_request,
    close_run,
    combination_group,
    journal_run,
    legal_entity,
    period,
    period_state,
    period_state_transition,
    policy_override,
    subledger_line,
    subledger_posting,
)
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.answer_keys.platform_plan import CLOSE, PLATFORM_KEY_IDS, load_platform_key
from support.answer_keys.platform_runner import (
    COMPARED,
    EXECUTED,
    key_verdict,
    platform_outcome,
    run_platform,
)
from support.answer_keys.stand_in import StandInPlatform, stand_in_world
from support.db import TestDatabase

POS_012 = PLATFORM_KEY_IDS[0]
# 04 T-CLS-01: the order of the ``steps`` array (the job executes FX before the release, R-79 (b)).
STEP_ORDER = (
    "CUTOFF",
    "INTERFACE_COMPLETENESS",
    "EXCEPTION_CHECK",
    "RECOMPUTE_DIRTY",
    "RELEASE_SCHEDULES",
    "FX_REMEASUREMENT",
    "NETTING_RECLASS",
    "INVARIANTS",
    "JOURNAL_SUMMARIZATION",
    "EXPORT",
    "ACKNOWLEDGEMENT_WAIT",
    "GL_TIE_OUT",
    "DATASET_FREEZE",
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_pos_012_compares_clean_after_the_close_run_of_its_plan(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    loaded = load_platform_key(POS_012)
    adapter, place = stand_in_world(app, keyring, clock, app_settings, loaded)
    result = run_platform(loaded, StandInPlatform(loaded, adapter))

    # Every step ran, the close run among them, once, between item 9 and item 10.
    assert {item.status for item in result.executed} == {EXECUTED}
    (closed,) = [item for item in result.executed if item.step.phase == CLOSE]
    assert closed.step.subject == "close run US01 ASC606 FY2026-P01"
    stamped = [entry for entry in adapter.ledger if entry.known_at is not None]
    of_nine = [entry for entry in stamped if entry.call.step.seq == 9]
    assert [entry.call.step.phase for entry in of_nine] == ["TIMELINE", CLOSE]
    own, after_run = of_nine
    assert own.known_at is not None and after_run.known_at is not None
    assert own.known_at < after_run.known_at == result.known_at[9] < result.known_at[10]
    # the server's transaction horizon stands beside each stamp, and moved with the run
    assert isinstance(own.horizon, int) and isinstance(after_run.horizon, int)
    assert own.horizon < after_run.horizon == adapter.horizon_at(result.known_at[9])

    # The run: the product's own, worked to its end with nothing but what the plan made.
    (run,) = place.rows(select(close_run))
    assert (str(run["status"]), run["current_step_code"]) == ("SUCCEEDED", None)
    assert [(step["step_code"], step["status"]) for step in run["steps"]] == [
        *((code, "SUCCEEDED") for code in STEP_ORDER),
        ("LOCK", "PENDING"),  # no lock: the period is not decided
    ]
    counts = {step["step_code"]: step["counts"] for step in run["steps"]}
    assert counts["RECOMPUTE_DIRTY"]["groups_recomputed"] == 0  # no group was dirty
    assert (counts["NETTING_RECLASS"]["postings"], counts["NETTING_RECLASS"]["lines"]) == (1, 4)
    assert counts["RELEASE_SCHEDULES"]["lines"] == counts["FX_REMEASUREMENT"]["lines"] == 0
    assert counts["EXPORT"]["batches_exported"] == 0  # the run observes; it exports nothing
    assert counts["GL_TIE_OUT"]["trial_balance_attached"] is False
    assert counts["DATASET_FREEZE"]["datasets_frozen"] == 12

    # What it left. The period is as it was: open, with the transitions the world's setup wrote.
    states = {
        str(row["period_key"]): (str(row["state"]), row["state_id"])
        for row in place.rows(
            select(period.c.period_key, period_state.c.state, period_state.c.id.label("state_id"))
            .select_from(
                period_state.join(period, period.c.id == period_state.c.period_id).join(
                    legal_entity, legal_entity.c.id == period_state.c.entity_id
                )
            )
            .where(legal_entity.c.code == "US01", period_state.c.book_code == "ASC606")
        )
    }
    assert (states["FY2026-P01"][0], states["FY2026-P02"][0]) == ("open", "open")
    january = place.rows(
        select(period_state_transition).where(
            period_state_transition.c.period_state_id == states["FY2026-P01"][1]
        )
    )
    assert len(january) == 2
    assert {(row["from_state"], str(row["to_state"])) for row in january} == {
        (None, "future"),
        ("future", "open"),
    }
    assert all(int(row["created_txid"]) < own.horizon for row in january)  # before any item

    # One posting of the entity — no group, no computation — written between the two stamps of
    # item 9: the reclass on January's last day and its reversal on February's first.
    (posting,) = place.rows(
        select(subledger_posting).where(subledger_posting.c.close_run_id == run["id"])
    )
    assert str(posting["posting_kind"]) == "NETTING_RECLASS"
    assert (posting["combination_group_id"], posting["contract_computation_id"]) == (None, None)
    assert own.horizon <= int(posting["created_txid"]) < after_run.horizon
    assert posting["created_at"] == datetime(2026, 1, 31, 17, 0, 1, tzinfo=UTC)  # the step's clock
    periods = {row["id"]: str(row["period_key"]) for row in place.rows(select(period))}
    lines = sorted(
        (
            int(line["entry_no"]),
            str(line["entry_kind"]),
            periods[line["period_id"]],
            line["effective_date"].isoformat(),
            str(line["account_role"]),
            Decimal(str(line["amount_txn"])),
        )
        for line in place.rows(
            select(subledger_line).where(subledger_line.c.subledger_posting_id == posting["id"])
        )
    )
    reclass, reversal = (
        ("NETTING_RECLASS", "FY2026-P01", "2026-01-31"),
        (
            "NETTING_RECLASS_REVERSAL",
            "FY2026-P02",
            "2026-02-01",
        ),
    )
    assert lines == [
        (1, *reclass, "CONTRACT_ASSET", Decimal("30000")),
        (1, *reclass, "CONTRACT_LIABILITY", Decimal("-30000")),
        (2, *reversal, "CONTRACT_ASSET", Decimal("-30000")),
        (2, *reversal, "CONTRACT_LIABILITY", Decimal("30000")),
    ]
    # The first period-end step marked both groups it passed, and the items after it left the
    # marks where they were: nothing of January is unposted.
    marks = [row["period_ends_open"] for row in place.rows(select(combination_group))]
    assert marks == [{"US01|ASC606": "2026-02-01"}, {"US01|ASC606": "2026-02-01"}]
    (journal,) = place.rows(select(journal_run))
    assert (str(journal["state"]), journal["close_run_id"], int(journal["line_count"])) == (
        "draft",
        run["id"],
        4,
    )

    # The comparison: every block of both checkpoints, the block that expects the pass included.
    assert {
        f"{checkpoint.name} {block.block}": (block.status, len(block.mismatches))
        for checkpoint in result.checkpoints
        for block in checkpoint.blocks
    } == {
        "end-of-p1 contracts": (COMPARED, 0),
        "end-of-p1 subledger": (COMPARED, 0),
        "end-of-p2 contracts": (COMPARED, 0),
    }
    assert platform_outcome(loaded, result) == (
        "passed",
        "every block compared clean on the db platform",
    )

    # Both declared POL-122 overrides were independently approved before activation.
    declared = [o for c in loaded.key.contracts for o in c.policy_overrides or ()]
    assert [(o.policy_key, o.obligation_key) for o in declared] == [
        ("balance.right_to_consideration", "X1-LICENCE"),
        ("balance.right_to_consideration", "X2-SERVICES"),
    ]
    overrides = place.rows(select(policy_override))
    assert len(overrides) == 2
    assert all(str(row["status"]) == "APPROVED" for row in overrides)
    assert all(row["created_by"] != row["updated_by"] for row in overrides)
    assert sorted(row["value"] for row in overrides) == sorted(o.value for o in declared)
    requests = place.rows(
        select(approval_request).where(approval_request.c.subject_type == "POLICY_OVERRIDE")
    )
    assert len(requests) == 2
    assert all(str(row["status"]) == "APPROVED" for row in requests)
    assert key_verdict(loaded, result) == (
        "passed",
        (),
        "every block compared clean on the db platform",
    )
