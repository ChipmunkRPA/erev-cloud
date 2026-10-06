"""SCH-13 ``partition_window_check`` (05 §SCH row 972; 04 §1.6 rule 2; RB-12; record §4.22).

Daily at 05:00 UTC the worker reads the last bounded partition of every PT-MPE and PT-MOC parent
through the doctor's own path — ``db.lint.catalogue_connection`` (the ``erev_app`` identity
session DG-KRN-DB-02 admits for catalogue reads) and ``controls.doctor.observe_partition_windows``
— and applies ``controls.doctor.partition_window`` with a 24-month horizon (the startup check keeps
its 12). The result is the log line ``partition_window.checked``: INFO when every window ends
after the horizon, WARNING with the failing tables otherwise. That WARNING line is the operator
notice the RB-12 runbook alert follows, as ``security_chain.verified`` at error is for RB-08
(SPEC-Q-188): no platform-level operator notification kind exists — the notification path
(``events.notifications``) is tenant-membership-scoped and platform operators hold no membership —
so such a kind is a named open item, not this task. No table is written. An ABSENT or
UNPARSEABLE observation is never a clean check (D-98 138-A1): a failing catalogue read yields the
doctor's "not collected" failure, a parent whose bound cannot be parsed its rule-1 failure, a parent
missing from the observation set its "no partition window observation" failure — all at WARNING.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from erev_api.controls.doctor import (
    CheckResult,
    PartitionWindowObservation,
    observe_partition_windows,
    partition_window,
)
from erev_api.controls.operator_alerts import partition_window_alert
from erev_api.jobs.context import JobRuntime
from erev_api.logging import get_logger, register_logger_fields

HORIZON_MONTHS: Final = 24  # 04 §1.6 rule 2: the current month plus 24 months exists
# The operator destination (D-98 138-A1): the WARNING line under the RB-12 runbook alert that
# operators read; a tenant notification is not a platform-operator destination.
OPERATOR_DESTINATION: Final = (
    "operator alert PARTITION_WINDOW_NEAR_END (05 OPR-24; RB-12) and the partition_window.checked "
    "WARNING line"
)
REQUEST_ID: Final = "partition-window-check"
_LOGGER: Final = "erev_api.controls.partition_window"

register_logger_fields(
    _LOGGER,
    (
        "result",
        "horizon_months",
        "summary",
        "failures",
        "tables",
        "checked_at",
        "destination",
        "error",
    ),
)


@dataclass(frozen=True, slots=True)
class PartitionWindowCheck:
    """The check's result and the level its log line carried (``info`` or ``warning``)."""

    result: CheckResult
    level: str
    tables: tuple[str, ...] = ()


def _observe_catalogue() -> tuple[PartitionWindowObservation, ...]:
    """The database-bound source: the partition catalogue as ``erev_app`` (NOT RUN on the lane)."""
    from erev_api.db.lint import catalogue_connection

    with catalogue_connection(request_id=REQUEST_ID) as connection:
        return observe_partition_windows(connection)


def check(
    *,
    now: datetime,
    observe: Callable[[], Sequence[PartitionWindowObservation]] | None = None,
) -> PartitionWindowCheck:
    """Observe (``observe``, else the catalogue), check against ``HORIZON_MONTHS`` and log
    ``partition_window.checked`` — WARNING when a window ends within the horizon, a parent has no
    bounded partition, a parent is missing from the observations or the observation itself failed
    (never a clean check), INFO otherwise. The WARNING line is the RB-12 operator notice
    (``OPERATOR_DESTINATION``)."""
    error: str | None = None
    windows: tuple[PartitionWindowObservation, ...] | None
    try:
        windows = tuple((observe or _observe_catalogue)())
    except Exception as raised:  # noqa: BLE001 — an unreadable catalogue is a failed check
        windows = None
        error = f"{type(raised).__name__}: {raised}"
    result = partition_window(windows, now=now, horizon_months=HORIZON_MONTHS)
    level = "info" if result.ok else "warning"
    fields = {
        "result": "PASS" if result.ok else "FAIL",
        "horizon_months": HORIZON_MONTHS,
        "summary": result.summary,
        "failures": list(result.failures),
        "tables": [window.table for window in windows or ()],
        "checked_at": now.isoformat(),
        "destination": OPERATOR_DESTINATION,
        "error": error,
    }
    logger = get_logger(_LOGGER)
    if result.ok:
        logger.info("partition_window.checked", **fields)
    else:
        logger.warning("partition_window.checked", **fields)
    return PartitionWindowCheck(result, level, tuple(window.table for window in windows or ()))


def run(runtime: JobRuntime) -> PartitionWindowCheck:
    """The worker task body: the catalogue observation at the process clock; a failed check also
    raises the ``PARTITION_WINDOW_NEAR_END`` operator alert (05 OPR-24; RB-12) when the runtime
    carries sinks."""
    now = runtime.clock.now()
    checked = check(now=now)
    if not checked.result.ok and runtime.alerts is not None:
        runtime.alerts.raise_alert(
            partition_window_alert(
                summary=checked.result.summary,
                tables=checked.tables,
                failures=len(checked.result.failures),
                horizon_months=HORIZON_MONTHS,
                raised_at=now,
            )
        )
    return checked
