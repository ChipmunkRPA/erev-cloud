"""Other materiality preserves currencies, offsets and the original setting."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from erev_api.domain.reports.builders import ReportParams, SourceCollector
from erev_api.domain.reports.builders import contract_balance_rollforward as builder


def lines(other: str, closing: str):
    return {
        "OTHER": {
            key: Decimal(other) if key == builder.LIABILITY else Decimal(0)
            for key in builder.ROLLFORWARD_BALANCES
        },
        "CLOSING": {
            key: Decimal(closing) if key == builder.LIABILITY else Decimal(0)
            for key in builder.ROLLFORWARD_BALANCES
        },
    }


def test_threshold_boundary_signed_balances_zero_denominator_and_offsets():
    entity = uuid4()
    items = [
        builder.ContractRollforward(uuid4(), key, None, entity, "US", "USD", lines(amount, "100"))
        for key, amount in (("A", "2"), ("B", "-2"))
    ]
    totals = {"USD": lines("0", "200"), "GBP": lines("-1", "-100"), "EUR": lines("0.01", "0")}
    result = builder.other_explanations(
        items, totals, Decimal("0.01"), book="ASC606", ending_periods={entity: "P09"}
    )
    assert [(x["contract"], x["currency"], x["other"]) for x in result] == [
        ("", "EUR", "0.01"),
        ("A", "USD", "2"),
        ("B", "USD", "-2"),
    ]
    assert result[1]["period"] == "P09"


def test_bound_threshold_never_reads_current_settings_and_old_reports_keep_shape(monkeypatch):
    now = datetime(2026, 10, 23, tzinfo=UTC)
    sources = SourceCollector()
    sources.record_cutoff(now)
    params = ReportParams(builder.CODE, 1, {}, (), now, sources=sources)
    monkeypatch.setattr(builder, "setting", lambda *a, **k: "0.02")
    original = builder._other_control(
        None, params, [], {"USD": lines("3", "100")}, book="ASC606", periods={}
    )
    binding = sources.binding(row_keys=[])

    def unexpected(*a, **k):
        raise AssertionError("Bound report must not read current threshold")

    monkeypatch.setattr(builder, "setting", unexpected)
    bound = replace(params, binding=binding)
    assert (
        builder._other_control(
            None, bound, [], {"USD": lines("3", "100")}, book="ASC606", periods={}
        )
        == original
    )
    legacy = replace(bound, binding=replace(binding, evidence={}))
    assert builder._other_control(None, legacy, [], {}, book="ASC606", periods={}) == {}
