"""Actual FX layer evidence must reconcile before reports can attribute it."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from erev_api.domain.reports.functional_revenue_activity import RevenueActivityUnavailable, read
from tests.engine.s12_fx_entities.test_s12_layers import (
    ENTITY,
    SERVICES,
    _context,
    _invoice,
    _release,
    _run,
    _spot,
)


def _trace():
    return _run(
        _context(months=2),
        [
            _invoice(1, date(2026, 1, 1), "100.00"),
            _invoice(2, date(2026, 1, 15), "100.00"),
            _release(SERVICES, date(2026, 1, 31), "150.00"),
            _release(SERVICES, date(2026, 2, 28), "20.00", "NEGATIVE_REVENUE"),
        ],
        [
            _spot(date(2026, 1, 1), "1.10"),
            _spot(date(2026, 1, 15), "1.20"),
            _spot(date(2026, 1, 31), "1.40"),
            _spot(date(2026, 2, 28), "1.30"),
        ],
    )[1]


def _read(trace, period="FY2026-P01", currency="USD"):
    return read(
        trace,
        obligation_subject=SERVICES,
        entity_code=ENTITY,
        period_key=period,
        transaction_currency="EUR",
        functional_currency=currency,
    )


def test_reports_read_actual_historical_pieces_and_period_delta():
    trace = _trace()
    (first,) = _read(trace)
    assert (first.transaction_amount, first.functional_amount) == (Decimal("150"), Decimal("170"))
    assert len(first.signed_piece_ids) == 2
    (second,) = _read(trace, "FY2026-P02")
    assert (second.transaction_amount, second.functional_amount) == (Decimal("-20"), Decimal("-26"))
    assert second.effective_date == date(2026, 2, 28)
    assert second.kind == "NEGATIVE_REVENUE"


def test_old_or_inconsistent_activity_is_not_substituted_with_spot():
    trace = _trace()
    missing = replace(
        trace, nodes=tuple(n for n in trace.nodes if n.measure != "revenue_activity_functional")
    )
    with pytest.raises(RevenueActivityUnavailable, match="reconcile"):
        _read(missing)
    with pytest.raises(RevenueActivityUnavailable, match="currency"):
        _read(trace, currency="GBP")
    altered = replace(
        trace,
        nodes=tuple(
            replace(n, params={**n.params, "amount_txn": "15001"})
            if n.measure == "revenue_activity_functional" and n.id.endswith("FY2026-P01")
            else n
            for n in trace.nodes
        ),
    )
    with pytest.raises(RevenueActivityUnavailable, match="reconcile"):
        _read(altered)
    bad = replace(
        trace,
        nodes=tuple(
            replace(n, value="170.01") if n.measure == "revenue_activity_functional" else n
            for n in trace.nodes
        ),
    )
    with pytest.raises(RevenueActivityUnavailable, match="reproduce"):
        _read(bad)


def test_report_reader_keeps_native_recognition_source_link():
    from tests.engine.s12_fx_entities.test_s12_functional_member_links import _revenue_output

    output = _revenue_output()
    book = output.books[0]
    node = next(n for n in book.trace.nodes if n.measure == "revenue_activity_functional")
    activities = read(
        book.trace,
        obligation_subject=node.params["obligation_subject"],
        entity_code=node.params["entity"],
        period_key=node.id.rsplit(":", 1)[1],
        transaction_currency=node.params["txn_currency"],
        functional_currency=node.currency,
    )
    activity = next(item for item in activities if item.node_id == node.id)
    assert activity.recognition_source_node == node.params["recognition_source_node"]
    broken = replace(
        book.trace,
        nodes=tuple(
            replace(n, params={**n.params, "recognition_source_node": "missing"})
            if n.id == node.id
            else n
            for n in book.trace.nodes
        ),
    )
    with pytest.raises(RevenueActivityUnavailable):
        read(
            broken,
            obligation_subject=node.params["obligation_subject"],
            entity_code=node.params["entity"],
            period_key=node.id.rsplit(":", 1)[1],
            transaction_currency=node.params["txn_currency"],
            functional_currency=node.currency,
        )
