"""Selector boundaries for the retained CHANGE/ACCESS report sections."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from erev_api.domain.reports.evidence_register_sources import requests
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import AccessPackCreateIn, ChangePackCreateIn


def test_access_date_has_explicit_utc_instant_and_includes_removed_members() -> None:
    cutoff = datetime(2026, 10, 19, 9, 30, tzinfo=timezone(timedelta(hours=-7)))
    for selected, expected in (
        (date(2026, 10, 18), "2026-10-18T23:59:59.999999+00:00"),
        (date(2026, 10, 19), "2026-10-19T16:30:00+00:00"),
    ):
        plan = requests(
            AccessPackCreateIn(kind="ACCESS", as_of=selected),
            entity_codes=("US", "UK"),
            known_at=cutoff,
        )
        assert {item.report_code for item in plan} == {"user_access_listing", "sod_conflict_report"}
        assert all(item.parameters["as_of"] == expected for item in plan)
        assert all(item.parameters["known_at"] == "2026-10-19T16:30:00+00:00" for item in plan)
        users = next(item for item in plan if item.report_code == "user_access_listing")
        assert users.parameters["include_removed"] is True


def test_change_dates_are_inclusive_and_never_expand_to_other_days() -> None:
    day = date(2026, 10, 18)
    plan = requests(
        ChangePackCreateIn(kind="CHANGE", from_date=day, to_date=day),
        entity_codes=("US",),
        known_at=datetime(2026, 10, 19, tzinfo=UTC),
    )
    assert {item.report_code for item in plan} == {"config_change_register", "ssp_change_log"}
    assert all(
        item.parameters["from_date"] == item.parameters["to_date"] == day.isoformat()
        for item in plan
    )


@pytest.mark.parametrize("kind", ["ACCESS", "CHANGE"])
def test_future_dates_cannot_be_silently_clipped(kind: str) -> None:
    request = (
        AccessPackCreateIn(kind="ACCESS", as_of=date(2026, 10, 20))
        if kind == "ACCESS"
        else ChangePackCreateIn(
            kind="CHANGE", from_date=date(2026, 10, 19), to_date=date(2026, 10, 20)
        )
    )
    with pytest.raises(Problem, match="future"):
        requests(request, entity_codes=("US",), known_at=datetime(2026, 10, 19, tzinfo=UTC))


def test_no_entities_or_naive_cutoff_refuse_before_queueing() -> None:
    request = AccessPackCreateIn(kind="ACCESS", as_of=date(2026, 10, 19))
    for codes, cutoff in (
        ((), datetime(2026, 10, 19, tzinfo=UTC)),
        (("US",), datetime(2026, 10, 19)),
    ):
        with pytest.raises(Problem):
            requests(request, entity_codes=codes, known_at=cutoff)
