"""Complete reporting intervals align by dates without redistributing partial periods."""

from dataclasses import replace
from uuid import UUID

from erev_api.domain.reports.builders.disaggregation import period_layout
from tests.unit.reports.test_waterfall_calendars import period


def test_same_key_different_dates_get_separate_columns():
    a = period("FY2026-P09", "2026-09-01", "2026-09-30")
    b = replace(period("FY2026-P09", "2025-12-01", "2025-12-31"), id=UUID(int=2))
    key_of, labels = period_layout({UUID(int=11): (a,), UUID(int=12): (b,)}, dated=True)
    assert key_of[a.id] == "date_2026-09-01_2026-09-30"
    assert key_of[b.id] == "date_2025-12-01_2025-12-31"
    assert list(labels) == [key_of[b.id], key_of[a.id]]
    legacy, _ = period_layout({UUID(int=11): (a,), UUID(int=12): (b,)}, dated=False)
    assert legacy[a.id] == legacy[b.id] == "FY2026-P09"


def test_different_local_keys_same_dates_combine_but_partial_overlap_does_not():
    a = period("FY2026-P09", "2026-09-01", "2026-09-30")
    b = replace(a, id=UUID(int=2), key="FY2027-P06")
    c = replace(period("FY2026-P09", "2026-08-31", "2026-09-27"), id=UUID(int=3))
    keys, labels = period_layout(
        {UUID(int=11): (a,), UUID(int=12): (b,), UUID(int=13): (c,)}, dated=True
    )
    assert keys[a.id] == keys[b.id]
    assert keys[c.id] != keys[a.id]
    assert len(labels) == 2
    keys, _ = period_layout({UUID(int=11): (a,), UUID(int=12): (a,)}, dated=True)
    assert keys[a.id] == a.key
