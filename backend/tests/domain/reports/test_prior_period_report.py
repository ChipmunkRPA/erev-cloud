"""RPT-05 ``revenue_from_prior_period_obligations`` database path (SCREENS_B §5.6.1 RPT-05 rev
1.12 and 1.16; ENGINE_SPEC_B S15-R-13, S15-R-14, §15.2.7 ``PRIOR_PERIOD_POB_REVENUE``; 04
T-CLS-05 rev 1.40 and 1.51; D-98 candidates 85, 96; lane ENG-C4).

World ``support.worlds.k01_pellworth`` (PRD §2.6 and §2.7): K-01 ``SF-ORD-10001`` is booked,
activated, billed and computed with no estimate change, modification, termination or late event,
so September 2026 has no revenue attributable to performance satisfied before the range. The run
proves the reader end to end — the REVENUE lines name the traces, every ``revenue_prior_period``
node of September is read and the ``revenue_prior_period_sum`` identity holds — with an empty
dataset: no rows, typed control totals ``row_count`` 0, ``revenue_total`` and
``prior_period_sum_total`` empty. A world with prior-period revenue (PRD WLD-X-16: AVM-DE
``NS-SO-DE-5002`` O1 re-priced by estimate version 2, one row, cause "Estimate change",
EUR (750.00)) is the follow-up once the platform records estimate versions in a report world.
Report runs play the worker as ``test_framework.py`` does. DB-bound: runs in an admitted slot.
"""

from __future__ import annotations

from typing import Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.domain.reports.builders import revenue_from_prior_period_obligations as pp
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.worlds import AVM_US, SEPTEMBER_2026, ReportWorld, k01_pellworth, report_run

SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    return k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))


@pytest.mark.slow
def test_prior_period_report_k01_september_2026_is_empty(world: ReportWorld) -> None:
    run, rows = report_run(world, pp.CODE, SEPTEMBER)
    assert rows == []
    assert run["control_totals"] == {
        "row_count": 0,
        "revenue_total": {},
        "prior_period_sum_total": {},
    }
    assert run["tie_out_results"] == []
