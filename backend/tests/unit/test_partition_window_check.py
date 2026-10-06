"""SCH-13 ``partition_window_check`` (05 §SCH row 972; 04 §1.6 rule 2; RB-12): the daily task
reuses the doctor's partition observation and check with a 24-month horizon, logs the result and
returns it; the doctor's own startup horizon stays 12 months. CPU only: the observation source is
injected; the catalogue read (``db.lint.catalogue_connection``) is database-bound and NOT RUN
here (record §4.22 (e))."""

from __future__ import annotations

from datetime import UTC, date, datetime

from erev_api.controls import partition_window as sch13
from erev_api.controls.doctor import (
    PARTITION_COLUMNS,
    PARTITION_HORIZON_MONTHS,
    PARTITION_WINDOW,
    PartitionWindowObservation,
    partition_window,
)

NOW = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)


def _windows(ends_on: date | None) -> tuple[PartitionWindowObservation, ...]:
    return tuple(PartitionWindowObservation(table, ends_on) for table in sorted(PARTITION_COLUMNS))


def test_the_doctor_default_horizon_stays_twelve_months() -> None:
    # 13 months ahead: clear for the startup check (12), within the SCH-13 horizon (24).
    assert PARTITION_HORIZON_MONTHS == 12
    thirteen = _windows(date(2027, 10, 1))
    assert partition_window(thirteen, now=NOW).ok
    within = partition_window(thirteen, now=NOW, horizon_months=sch13.HORIZON_MONTHS)
    assert not within.ok and all("24 months" in failure for failure in within.failures)


def test_sch_13_warns_when_a_window_ends_within_twenty_four_months() -> None:
    checked = sch13.check(now=NOW, observe=lambda: _windows(date(2028, 6, 1)))
    assert checked.result.check == PARTITION_WINDOW and not checked.result.ok
    assert checked.level == "warning"
    assert sorted(PARTITION_COLUMNS) == [
        failure.split(" ")[3] for failure in checked.result.failures
    ]  # "partition window of <table> ends ..."
    assert all("04 §1.6 rule 2" in failure for failure in checked.result.failures)


def test_sch_13_is_quiet_when_every_window_ends_after_the_horizon() -> None:
    checked = sch13.check(now=NOW, observe=lambda: _windows(date(2033, 1, 1)))
    assert checked.result.ok and checked.level == "info"
    assert "after 2028-09-21" in checked.result.summary  # NOW + 24 months


def test_sch_13_reports_an_unbounded_parent_as_a_rule_1_failure() -> None:
    windows = (
        PartitionWindowObservation("audit_event", None),
        PartitionWindowObservation("schedule_line", date(2033, 1, 1)),
        PartitionWindowObservation("subledger_line", date(2033, 1, 1)),
    )
    checked = sch13.check(now=NOW, observe=lambda: windows)
    assert checked.level == "warning"
    assert checked.result.failures == (
        "table audit_event has no bounded partition (04 §1.6 rule 1)",
    )


def test_sch_13_names_the_operator_notice_limit() -> None:
    """No platform-level operator notification kind exists (the notification path is
    membership-scoped); the WARNING line under RB-12 is the notice — a named open item."""
    assert "RB-12" in (sch13.check.__doc__ or "") and "open item" in (sch13.__doc__ or "")


def test_sch_13_a_failing_observation_source_is_not_healthy_by_name() -> None:
    def broken() -> tuple[PartitionWindowObservation, ...]:
        raise RuntimeError("catalogue unavailable")

    checked = sch13.check(now=NOW, observe=broken)
    assert checked.level == "warning" and not checked.result.ok
    (failure,) = checked.result.failures
    assert failure.startswith("the partition windows")  # the doctor's "not collected" failure


def test_sch_13_a_parent_missing_from_the_observations_is_a_failure() -> None:
    two = tuple(w for w in _windows(date(2033, 1, 1)) if w.table != "audit_event")
    checked = sch13.check(now=NOW, observe=lambda: two)
    assert checked.level == "warning"
    assert checked.result.failures == ("table audit_event has no partition window observation",)


def test_sch_13_names_its_operator_destination() -> None:
    assert "RB-12" in sch13.OPERATOR_DESTINATION and "WARNING" in sch13.OPERATOR_DESTINATION
