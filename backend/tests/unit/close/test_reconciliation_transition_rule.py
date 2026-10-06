"""D-98 63 (F-CLO Q-12): T-CLS-06 ``reconciliation.period_lock_id`` is updatable write-once — set
at lock certification while NULL, never changed afterwards. The DB-03 rule of
``erev_api.db.transitions`` is the single source of truth; the CLO-6 migration
(``<NNNN>_clo_6_reconciliation_period_lock_id.py``; provisional 0055 on 0054 on the lane, 0059 on
0058 once F-ADM's 0058 is on main) freezes its rendering (the DG-ARC-07 comparison here runs
without a database). At merge prep the file is held out of the tree until its parent lands; the
freeze test then skips with that reason rather than passing on nothing.

Supervisor ruling R-54 (a) (04 rev 1.121; BUILD_SPEC CLO-16): revision 0095 re-renders the rule —
``source_file_id`` and ``sync_run_id`` are write-once updatable (the trial-balance attachment) and
the pair ``REOPENED`` → ``DRAFT`` is retired (D-98 79). The current rendering is therefore frozen by
0095, whose downgrade restores the CLO-6 body verbatim; the CLO-6 revision keeps the rendering of
its own time."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from erev_api.db import transitions

VERSIONS = Path(__file__).resolve().parents[3] / "erev_api" / "db" / "migrations" / "versions"
MIGRATION_SUFFIX = "_clo_6_reconciliation_period_lock_id.py"
GENERATION_SUFFIX = "_clo_16_reconciliation_generation.py"  # revision 0095 (ruling R-54 (a))
HELD_OUT = (
    "the CLO-6 migration is held out of the tree until F-ADM's 0058 is on main "
    "(F-CLO record §24); it returns as 0059 on 0058"
)


def _migration(suffix: str = MIGRATION_SUFFIX) -> Path | None:
    found = sorted(VERSIONS.glob(f"*{suffix}"))
    assert len(found) <= 1, found
    return found[0] if found else None


def _loaded(migration: Path) -> ModuleType:
    loaded = importlib.util.spec_from_file_location(f"migration_{migration.name[:4]}", migration)
    assert loaded is not None and loaded.loader is not None
    module = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(module)
    return module


def test_period_lock_id_is_updatable_write_once() -> None:
    spec = transitions.TRANSITIONS["reconciliation"]
    assert "period_lock_id" in spec.updatable_columns
    assert "period_lock_id" in spec.set_once
    body = transitions.transition_trigger_sql("reconciliation")
    assert "'period_lock_id'" in body
    assert (
        "IF OLD.period_lock_id IS NOT NULL "
        "AND NEW.period_lock_id IS DISTINCT FROM OLD.period_lock_id"
    ) in body


def test_clo_6_migration_freezes_the_rendered_body() -> None:
    migration = _migration()
    if migration is None:
        pytest.skip(HELD_OUT)
    module = _loaded(migration)
    revision = migration.name[:4]
    assert (module.revision, module.down_revision) == (revision, f"{int(revision) - 1:04d}")
    assert "period_lock_id" in module.UPDATE_COLUMNS
    assert "'period_lock_id'" not in module.PREVIOUS_TRANSITION_BODY
    # R-54 (a): the rule was re-rendered by revision 0095, which freezes today's rendering and
    # restores the CLO-6 body on downgrade; the CLO-6 body still admitted REOPENED → DRAFT.
    generation = _migration(GENERATION_SUFFIX)
    assert generation is not None
    latest = _loaded(generation)
    assert latest.TRANSITION_BODY == transitions.transition_trigger_sql("reconciliation")
    assert latest.PREVIOUS_TRANSITION_BODY == module.TRANSITION_BODY
    assert "'REOPENED>DRAFT'" in module.TRANSITION_BODY
    assert "'REOPENED>DRAFT'" not in latest.TRANSITION_BODY


def test_trial_balance_columns_are_write_once_and_reopened_is_final() -> None:
    """04 T-CLS-06 rev 1.121 (supervisor ruling R-54 (a), (b))."""
    spec = transitions.TRANSITIONS["reconciliation"]
    assert {"source_file_id", "sync_run_id"} <= spec.updatable_columns
    assert spec.set_once == {"period_lock_id", "source_file_id", "sync_run_id"}
    assert ("REOPENED", "DRAFT") not in spec.pairs
    assert not [pair for pair in spec.pairs if pair[0] == "REOPENED"]
    refused = transitions.violations(
        spec, to_status="DRAFT", set_values={}, expected_status="REOPENED"
    )
    assert [error.field for error in refused] == ["status"]
    body = transitions.transition_trigger_sql("reconciliation")
    for column in ("source_file_id", "sync_run_id"):
        assert (
            f"IF OLD.{column} IS NOT NULL AND NEW.{column} IS DISTINCT FROM OLD.{column}"
        ) in body
