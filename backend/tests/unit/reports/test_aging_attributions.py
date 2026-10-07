"""Aging reads the engine's selected period attribution, never a later balance or journal date."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from erev_api.domain.reports.builders.aging_attributions import attributions
from erev_api.problems import Problem
from erev_engine.trace import Trace, TraceNode

CONTRACT = "C:one/%"
ENTITY = "US:01"


def node(period: str, as_of: str, revenue: str, asset: str, receivable: str) -> TraceNode:
    return TraceNode(
        id=f"netting_reclass_amount:encoded-subject:{period}",
        measure="netting_reclass_amount",
        value=str(Decimal(asset) + Decimal(receivable)),
        currency="USD",
        formula_id="TEST",
        inputs=(),
        rounding_residue=None,
        narrative_key="test",
        params={
            "key": "encoded-subject",
            "as_of": as_of,
            "aging_contract": CONTRACT,
            "aging_entity": ENTITY,
            "aging_revenue_date": revenue,
            "aging_asset": asset,
            "aging_receivable": receivable,
        },
    )


def read(*nodes: TraceNode, end: date = date(2026, 3, 31)) -> list[tuple[date, str, Decimal]]:
    return attributions(
        Trace(1, "test", nodes, {}), contract=CONTRACT, entity=ENTITY, currency="USD", end=end
    )


def test_attributions_select_period_preserve_revenue_date_and_split_roles() -> None:
    january = node("FY2026-P01", "2026-01-31", "2026-01-05", "20", "10")
    march = node("FY2026-P03", "2026-03-31", "2026-03-10", "2000", "3000")
    april = node("FY2026-P04", "2026-04-30", "2026-04-10", "9999", "9999")
    version = replace(april, id="netting_reclass_amount:encoded-subject:-")
    other = replace(march, params={**march.params, "aging_contract": "other"})
    assert read(april, march, january, version, other) == [
        (date(2026, 3, 10), "UNBILLED_RECEIVABLE", Decimal("3000")),
        (date(2026, 3, 10), "CONTRACT_ASSET", Decimal("2000")),
    ]
    assert read(january, end=date(2025, 12, 31)) == []
    assert read(january, end=date(2026, 12, 31)) == read(january)
    zero = node("FY2026-P03", "2026-03-31", "2026-03-10", "0", "0")
    assert read(january, zero) == []


@pytest.mark.parametrize(
    "change",
    [
        {"aging_revenue_date": "2026-04-01"},
        {"aging_asset": "-1"},
        {"aging_asset": "NaN"},
        {"aging_receivable": "100"},
        {"aging_revenue_date": "bad"},
    ],
)
def test_inconsistent_attribution_refuses(change: dict[str, str]) -> None:
    found = node("FY2026-P03", "2026-03-31", "2026-03-10", "2000", "3000")
    with pytest.raises(Problem):
        read(replace(found, params={**found.params, **change}))


def test_older_trace_refuses_instead_of_guessing_dates_or_presentation() -> None:
    old = node("FY2026-P03", "2026-03-31", "2026-03-10", "2000", "3000")
    with pytest.raises(Problem):
        read(replace(old, params={"as_of": "2026-03-31", "key": "encoded-subject"}))
    with pytest.raises(Problem):
        attributions(None, contract=CONTRACT, entity=ENTITY, currency="USD", end=date(2026, 3, 31))
