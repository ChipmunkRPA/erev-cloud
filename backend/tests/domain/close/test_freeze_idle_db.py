"""The idle bound of a dataset freeze outside the lock decision (05 TXN-03 rev 1.121; dev-guide
DG-AK-60 rev 1.165; supervisor ruling R-119 (d) of 2026-10-01). PostgreSQL-bound.

``snapshots.freeze_datasets`` works on two connections: the caller's transaction is idle while
the freeze's SYSTEM reader produces a dataset, and the reader's while the caller stores a file.
The lock decision's witness is
``test_lock_decision_db.py``; this one is the close run's DATASET_FREEZE step, a whole close run
through ``POST /close-runs`` and the ``CLOSE_RUN`` job over WLD-K-01. The sandbox period replay
cannot reach a lock today (SNP-2b): its call is held by the source test of
``tests/unit/test_idle_in_transaction.py``.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.domain.close import dependencies as close_dependencies
from erev_api.domain.close import freeze, snapshots
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import text
from support import close_runs as runs
from support import worlds
from support.db import TestDatabase

SEPTEMBER: Final = "FY2026-P09"
# The step's transaction and the freeze's reader start the freeze with 2 s instead of the
# connection's 60 s; one producer takes 4.5 s and one file takes 3 s to store — the proportions
# of a dataset that outlasts the default on either side.
LOWERED_IDLE_MS: Final = 2000
SLOW_PRODUCER_SECONDS: Final = 4.5
SLOW_STORE_SECONDS: Final = 3.0


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def test_txn_03_the_close_runs_dataset_freeze_outlives_the_connections_idle_timeout(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DATASET_FREEZE step of a close run. Its transaction and the freeze's reader reach the
    freeze with an idle-in-transaction timeout of 2 s — the connection default of 60 s, lowered.
    The first producer takes 4.5 s, during which the step's transaction is idle; the first file
    takes 3 s to store, during which the reader's is. The step sets the freeze's bound for its
    own transaction before it freezes (``freeze.allow_idle``) and the freeze for the reader it
    opens: the twelve datasets are frozen, the step and the run succeed, and both transactions
    show the setting (900 s).

    Fail-first: PostgreSQL ended the step's session after 2 s (SQLSTATE 25P03) and the run did
    not finish its step — with the real default, any dataset that takes more than 60 s to
    produce, or any file that takes more than 60 s to store."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    registry = close_dependencies.snapshot_registry()
    first_kind = close_dependencies.snapshot_engine().kinds[0]
    seen: dict[str, str] = {}
    show = text("SHOW idle_in_transaction_session_timeout")
    lower = text("SELECT set_config('idle_in_transaction_session_timeout', :idle, true)")
    lowered_to = {"idle": str(LOWERED_IDLE_MS)}
    real_cutoff, real_store, real_unit = (
        freeze.freeze_cutoff,
        snapshots.store_file,
        freeze.system_unit,
    )

    def lowered(session: Any, now: Any) -> Any:
        # the first statement of the step's freeze: its transaction, as a shorter default leaves it
        session.execute(lower, lowered_to)
        return real_cutoff(session, now)

    @contextmanager
    def lowered_unit(uow: Any) -> Iterator[Any]:
        with real_unit(uow) as reader:
            reader.session.execute(lower, lowered_to)  # the reader's transaction, likewise
            yield reader

    def slow(reader: Any, scope: Any) -> Any:
        seen["reader"] = str(reader.session.execute(show).scalar_one())
        time.sleep(SLOW_PRODUCER_SECONDS)
        return registry.datasets[first_kind](reader, scope)

    def stored(uow: Any, **kwargs: Any) -> Any:
        if "step" not in seen:
            seen["step"] = str(uow.session.execute(show).scalar_one())
            time.sleep(SLOW_STORE_SECONDS)
        return real_store(uow, **kwargs)

    delayed = dataclasses.replace(registry, datasets={**registry.datasets, first_kind: slow})
    with monkeypatch.context() as patched:
        patched.setattr(freeze, "freeze_cutoff", lowered)
        patched.setattr(freeze, "system_unit", lowered_unit)
        patched.setattr(close_dependencies, "snapshot_registry", lambda: delayed)
        patched.setattr(snapshots, "store_file", stored)
        run = runs.closed(world, monkeypatch, entity_code=worlds.AVM_US, period_key=SEPTEMBER)
    assert runs.step(run, "DATASET_FREEZE")["status"] == "SUCCEEDED", run
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None)
    assert runs.summary(run, "DATASET_FREEZE") == "12 datasets frozen"
    assert seen == {"reader": "15min", "step": "15min"}
