"""Different fiscal calendars must not merge amounts under one period label."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import revenue_waterfall as waterfall
from erev_api.domain.reports.tie_outs import PeriodRef
from tests.unit.reports.test_waterfall_row_keys import _obligation, _population, _rows


def period(key, start, end):
    return PeriodRef(
        UUID(int=1), key, key, 2026, 9, 3, date.fromisoformat(start), date.fromisoformat(end)
    )


@pytest.mark.parametrize("granularity", ["MONTH", "QUARTER", "YEAR"])
def test_different_dates_keep_entity_amounts_and_drill_sources_separate(monkeypatch, granularity):
    a, b = UUID(int=101), UUID(int=102)
    key = "FY2026-P09"
    buckets = waterfall._calendar_buckets(
        {
            a: (period(key, "2026-09-01", "2026-09-30"),),
            b: (period(key, "2026-08-31", "2026-09-27"),),
        },
        granularity,
    )
    first = replace(
        _obligation("C1", "O1", "100"),
        entity_id=a,
        subledger_lines={key: [(UUID(int=1), Decimal("100"))]},
    )
    second = replace(
        _obligation("C2", "O1", "200"),
        entity_id=b,
        subledger_lines={key: [(UUID(int=2), Decimal("200"))]},
    )
    population = replace(_population(first, second), buckets=buckets, entity_ids=(a, b))
    rows = _rows(monkeypatch, population, "PRODUCT")
    total = rows["TOTAL:USD"]
    assert total["period:date_2026-09-01_2026-09-30"]["amount"] == "100.00"
    assert total["period:date_2026-08-31_2026-09-27"]["amount"] == "200.00"
    assert total["total"]["amount"] == "300.00"
    params = ReportParams(
        report_code=waterfall.CODE,
        report_version=1,
        parameters={},
        entity_ids=(a, b),
        known_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    for bucket, identity, amount in [
        (buckets[0], UUID(int=2), "200.00"),
        (buckets[1], UUID(int=1), "100.00"),
    ]:
        value, contributors = waterfall.cell(None, params, "TOTAL:USD", "period:" + bucket.key)
        assert value["amount"] == amount
        assert [item["id"] for item in contributors] == [identity]


def test_identical_dates_with_different_local_keys_share_one_date_column():
    a, b = UUID(int=101), UUID(int=102)
    buckets = waterfall._calendar_buckets(
        {
            a: (period("FY2026-P09", "2026-09-01", "2026-09-30"),),
            b: (period("FY2027-P03", "2026-09-01", "2026-09-30"),),
        },
        "MONTH",
    )
    assert len(buckets) == 1
    assert buckets[0].key == "date_2026-09-01_2026-09-30"
    assert buckets[0].keys_for(a) == ("FY2026-P09",)
    assert buckets[0].keys_for(b) == ("FY2027-P03",)
    second = replace(
        _obligation("C2", "O1"), entity_id=b, recognized={"FY2027-P03": Decimal("200")}
    )
    first = replace(_obligation("C1", "O1", "100"), entity_id=a)
    assert waterfall._cell((first, second), buckets[0], None) == Decimal("300")


def test_aligned_calendars_preserve_existing_column_keys():
    a, b = UUID(int=101), UUID(int=102)
    periods = (period("FY2026-P09", "2026-09-01", "2026-09-30"),)
    (bucket,) = waterfall._calendar_buckets({a: periods, b: periods}, "MONTH")
    assert bucket.key == "FY2026-P09"
    assert bucket.keys_for(a) == bucket.keys_for(b) == ("FY2026-P09",)
    assert bucket.keys_for(UUID(int=103)) == ()


def test_new_runs_pin_calendar_interpretation_and_old_bindings_keep_shape(monkeypatch):
    from erev_api.domain.reports import tie_outs
    from erev_api.domain.reports.builders import SourceBinding, SourceCollector

    a, b = UUID(int=101), UUID(int=102)
    entities = [
        tie_outs.EntityRef(a, "A", a, "USD", "UTC"),
        tie_outs.EntityRef(b, "B", b, "USD", "UTC"),
    ]
    calendars = {
        a: tie_outs.Calendar((period("FY2026-P09", "2026-09-01", "2026-09-30"),)),
        b: tie_outs.Calendar((period("FY2026-P09", "2026-08-31", "2026-09-27"),)),
    }
    monkeypatch.setattr(tie_outs, "book_of", lambda *args: "ASC606")
    monkeypatch.setattr(tie_outs, "entities", lambda *args, **kwargs: entities)
    monkeypatch.setattr(tie_outs, "calendars", lambda *args, **kwargs: calendars)
    monkeypatch.setattr(tie_outs, "contract_named", lambda *args: None)
    monkeypatch.setattr(tie_outs, "cutoff_for", lambda session, params: params.known_at)
    monkeypatch.setattr(waterfall, "_obligations", lambda *args: ([], {}))
    collector = SourceCollector()
    params = ReportParams(
        report_code=waterfall.CODE,
        report_version=1,
        parameters={},
        entity_ids=(a, b),
        known_at=datetime(2026, 9, 15, tzinfo=UTC),
        sources=collector,
    )
    live = waterfall.population(None, params)
    assert len(live.buckets) == 2
    assert collector.evidence[waterfall.CALENDAR_BUCKETS] is True
    binding = SourceBinding(
        cutoff=params.known_at,
        versions={},
        labels={},
        row_keys=frozenset(),
        evidence=collector.evidence,
    )
    assert waterfall.population(None, replace(params, binding=binding)).buckets == live.buckets
    old = waterfall.population(None, replace(params, binding=replace(binding, evidence={})))
    assert len(old.buckets) == 1
    assert old.buckets[0].key == "FY2026-P09"
