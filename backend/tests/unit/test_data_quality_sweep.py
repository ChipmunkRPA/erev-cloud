"""SCH-10 pure rules (record §4.30): the empty report, the evaluated-state set and the run over
no tenants (the tenant directory monkeypatched — no database). The database path is measured by
``tests/domain/close/test_data_quality_sweep_db.py``."""

from __future__ import annotations

from typing import Any

import pytest
from erev_api.clock import FrozenClock
from erev_api.domain.close import data_quality_sweep, gates
from erev_api.jobs.context import JobRuntime
from support.clock import FROZEN_AT


def test_only_open_closing_and_reopened_periods_are_evaluated() -> None:
    assert gates.EVALUATED_STATES == frozenset({"open", "closing", "reopened"})
    assert data_quality_sweep.SweepReport() == data_quality_sweep.SweepReport(0, 0, 0, 0, 0, 0, 0)


def test_a_run_over_no_tenants_touches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def no_tenants(runtime: JobRuntime, **kwargs: Any) -> list[Any]:
        calls.append(kwargs)
        return []

    monkeypatch.setattr(data_quality_sweep, "active_tenants", no_tenants)
    runtime = JobRuntime(clock=FrozenClock(FROZEN_AT), keyring=None, files=None)
    assert data_quality_sweep.run(runtime, only_tenants=[]) == data_quality_sweep.SweepReport()
    assert calls == [{"request_id": data_quality_sweep.REQUEST_ID, "only": []}]
