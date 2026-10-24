"""Disclosure child reports use fiscal quarters and valid, exact-cutoff report schemas."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.domain.reports.disclosure_plan import requests
from erev_api.domain.reports.framework import parameter_errors
from erev_api.domain.reports.tie_outs import Calendar, PeriodRef
from erev_api.problems import Problem

CALENDAR = Calendar(
    tuple(
        PeriodRef(
            UUID(int=month),
            f"FY2027-P{month - 3:02}",
            str(month),
            2027,
            month - 3,
            1,
            date(2026, month, 1),
            date(2026, month, 30),
        )
        for month in (4, 5, 6)
    )
)


@pytest.mark.parametrize("currency_view", ["transaction", "functional", "reporting"])
def test_child_schemas_and_fiscal_quarter_range(currency_view: str) -> None:
    plan = requests(
        entity_code="US",
        book="ASC606",
        calendar=CALENDAR,
        period_key="FY2027-P02",
        known_at=datetime(2026, 7, 1, tzinfo=UTC),
        quarter=True,
        currency_view=currency_view,
    )
    assert len(plan) == 16
    assert len({item.key for item in plan}) == 16
    for item in plan:
        assert (
            parameter_errors(
                DEFINITIONS_BY_CODE[item.body.report_code].parameters_schema, item.body.parameters
            )
            == []
        )
        assert item.body.parameters["known_at_basis"] == "historical"
        assert item.body.parameters["entity_codes"] == ["US"]
        assert item.body.parameters["book"] == "ASC606"
        assert item.body.parameters["currency_view"] == currency_view
        if item.basis == "QUARTER_TO_DATE":
            assert item.body.parameters["from_period_key"] == "FY2027-P01"
            assert item.body.parameters["to_period_key"] == "FY2027-P02"
    assert {item.body.report_code for item in plan if item.sections == (6,)} == {
        "contract_cost_rollforward"
    }
    assert sum(item.body.report_code == "rpo" for item in plan) == 1
    assert sum(item.body.report_code == "contract_balances" for item in plan) == 1


def test_month_only_and_missing_quarter() -> None:
    from dataclasses import replace

    args = dict(
        entity_code="US",
        book="ASC606",
        period_key="FY2027-P02",
        known_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert len(requests(calendar=CALENDAR, quarter=False, **args)) == 9
    unknown = Calendar(tuple(replace(p, quarter_no=None) for p in CALENDAR.periods))
    with pytest.raises(Problem, match="has no quarter"):
        requests(calendar=unknown, quarter=True, **args)
