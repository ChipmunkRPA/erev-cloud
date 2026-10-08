"""Close supporting selectors follow the fiscal period and the selected freeze cutoff."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from erev_api.domain.reports.catalogue import DEFINITIONS
from erev_api.domain.reports.evidence_report_plan import requests
from erev_api.domain.reports.evidence_reports import PATHS
from erev_api.domain.reports.framework import parameter_errors
from erev_api.problems import Problem


def planned(start: date, end: date, cutoff: datetime):
    return requests(
        entity_code="ENTITY",
        book="IFRS15",
        period_key="FY2026-P04",
        start_date=start,
        end_date=end,
        cutoff=cutoff,
    )


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2025, 12, 28), date(2026, 1, 31)),
        (date(2026, 4, 1), date(2026, 4, 30)),
    ],
)
def test_full_fiscal_interval_and_period_end_instant_are_explicit(start: date, end: date) -> None:
    cutoff = datetime(2026, 10, 8, 12, tzinfo=timezone(timedelta(hours=-7)))
    result = planned(start, end, cutoff)
    assert {body.report_code for body in result} == set(PATHS)
    catalogue = {definition.code: definition for definition in DEFINITIONS}
    for body in result:
        assert body.output_format == "CSV"
        parameters = body.parameters
        assert parameters["entity_codes"] == ["ENTITY"]
        assert parameters["known_at"] == "2026-10-08T19:00:00+00:00"
        assert not parameter_errors(catalogue[body.report_code].parameters_schema, parameters)
        if body.report_code in {"config_change_register", "ssp_change_log"}:
            assert (parameters["from_date"], parameters["to_date"]) == (str(start), str(end))
        elif body.report_code == "late_entry_report":
            assert (parameters["book"], parameters["period_key"]) == ("IFRS15", "FY2026-P04")
        else:
            assert parameters["as_of"] == f"{end}T23:59:59.999999+00:00"
    assert (
        next(body for body in result if body.report_code == "user_access_listing").parameters[
            "include_removed"
        ]
        is False
    )


@pytest.mark.parametrize(
    "start,end,cutoff",
    [
        (date(2026, 2, 2), date(2026, 2, 1), datetime(2026, 3, 1, tzinfo=UTC)),
        (date(2026, 2, 1), date(2026, 2, 28), datetime(2026, 2, 27, tzinfo=UTC)),
        (date(2026, 2, 1), date(2026, 2, 28), datetime(2026, 2, 28, 23, 59, 59, tzinfo=UTC)),
        (date(2026, 2, 1), date(2026, 2, 28), datetime(2026, 3, 1)),
    ],
)
def test_invalid_interval_early_close_or_naive_cutoff_is_refused(start, end, cutoff) -> None:
    with pytest.raises(Problem):
        planned(start, end, cutoff)


def test_relock_uses_its_later_cutoff_but_same_fiscal_dates() -> None:
    first = planned(date(2026, 1, 1), date(2026, 1, 31), datetime(2026, 2, 2, tzinfo=UTC))
    second = planned(date(2026, 1, 1), date(2026, 1, 31), datetime(2026, 2, 5, tzinfo=UTC))
    for before, after in zip(first, second, strict=True):
        assert before.parameters["known_at"] != after.parameters["known_at"]
        assert {key: value for key, value in before.parameters.items() if key != "known_at"} == {
            key: value for key, value in after.parameters.items() if key != "known_at"
        }
