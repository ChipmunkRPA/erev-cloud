"""PRF-4 month-24 close measurement (dev-guide DG-PERF-02 (2), DG-PERF-04; 05 PERF-01, PERF-03;
REQ-CLS-014; G9). Runs only under ``make perf`` (``EREV_PERF_RUN=1``) against the perf sandbox on
database ``erev`` — Ray-side; NOT RUN in the lane. Dependencies recorded in the lane record: the
API-R-39 close-run routes, the API-R-38 acknowledge command and the API-R-40 reconciliation attach.
"""

from __future__ import annotations

import pytest

from perf.support import close, report
from perf.support.client import PerfClients

pytestmark = pytest.mark.perf


def test_month_24_close(
    perf_prepared: object,
    perf_clients: PerfClients,
    perf_report: report.PerfReport,
) -> None:
    """In the perf sandbox with ``platform.job_concurrency = 8`` approved by perf-reviewer: as
    perf-controller ``POST /close-runs`` for VOL-DE, VOL-UK, VOL-US (FY2026-P12, ASC606), poll
    every 2 s; after the first pass perf-accountant submits, perf-reviewer approves, perf-controller
    exports (CSV) and acknowledges every journal run and attaches the trial balance; a second close
    run per entity records the export, acknowledgement
    and tie-out. Wall time from the first 202 to the last second-pass DATASET_FREEZE ≤ 600 s; no
    step ends with a problem (BS4-D-16)."""
    accountant, controller, reviewer = perf_clients
    # Preflight (Codex 2353 §4): every route of the window is BOUND or the window refuses by name
    # before its first request — today the API-R-40 attach is BLOCKED on CLO-17, so this test
    # refuses up front until F-CLO lands it; the month-24 preparation (perf_prepared) ran before.
    window = close.run_close_window(accountant, controller, reviewer)
    perf_report.close = report.close_section(window)
    perf_report.notes.append(
        "engine median time per group and the step breakdown are reported, not asserted "
        "(DG-PERF-04)"
    )
    assert not window.problems, window.problems
    assert all(close.FREEZE_STEP in ew.steps_second for ew in window.entities.values())
    assert window.seconds <= close.CLOSE_LIMIT_SECONDS, (
        f"month-24 close took {window.seconds:.1f} s"
    )
