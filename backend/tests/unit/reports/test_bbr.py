"""BBR fiscal aggregation, signed movements and period attribution."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.reports.builders import bookings_billings_revenue as bbr
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef
from erev_api.problems import Problem

ENTITY = EntityRef(UUID(int=1), "US:1", UUID(int=2), "USD", "UTC")
PERIODS = (
    PeriodRef(UUID(int=3), "P01", "July", 2027, 1, 1, date(2026, 7, 1), date(2026, 7, 31)),
    PeriodRef(UUID(int=4), "P02", "August", 2027, 2, 1, date(2026, 8, 1), date(2026, 8, 31)),
)


def contribution(amount: str, day: date) -> Contribution:
    return Contribution(
        "contract_event",
        UUID(int=5),
        UUID(int=6),
        ENTITY.id,
        day,
        "USD",
        Decimal(amount),
    )


def test_fiscal_quarter_signed_totals_and_posting_period() -> None:
    booked = contribution("100", date(2026, 7, 4))
    modification = contribution("-20", date(2026, 8, 4))
    invoice = contribution("80", date(2026, 7, 15))
    credit = contribution("-10", date(2026, 8, 4))
    # A June-effective late-event carry belongs to August's journal, not June.
    revenue = replace(contribution("35", date(2026, 6, 4)), period_id=PERIODS[1].id)
    sources = {
        "booked_new": [booked],
        "booked_modifications": [modification],
        "billings": [invoice, credit],
        "revenue": [revenue],
    }
    args: dict[str, Any] = dict(
        entities=(ENTITY,),
        periods={ENTITY.id: PERIODS},
        currency_view="transaction",
        journal_revenue={"USD": Decimal("35")},
    )
    quarter = bbr.dataset(sources, granularity="QUARTER", **args)
    assert len(quarter.rows) == 1
    row = quarter.rows[0]
    assert row["row_key"] == "period:FY2027-Q1:US%3A1"
    assert [row[m]["amount"] for m in bbr.MEASURES] == ["100.00", "-20.00", "70.00", "35.00"]
    assert quarter.tie_out_results[0]["result"] == "PASS"
    months = bbr.dataset(sources, granularity="MONTH", **args)
    assert [r["revenue"]["amount"] for r in months.rows] == ["0.00", "35.00"]


def test_currency_split_and_missing_valuation_refuse() -> None:
    usd = contribution("100", date(2026, 7, 4))
    eur = replace(usd, source_id=UUID(int=7), currency="EUR", amount=Decimal("60"))
    sources = {"booked_new": [usd, eur], "booked_modifications": [], "billings": [], "revenue": []}
    args: dict[str, Any] = dict(
        entities=(ENTITY,), periods={ENTITY.id: PERIODS}, granularity="MONTH", journal_revenue={}
    )
    result = bbr.dataset(sources, currency_view="transaction", **args)
    assert {r["row_key"] for r in result.rows} == {"period:P01:US%3A1:USD", "period:P01:US%3A1:EUR"}
    with pytest.raises(Problem, match="FX valuation"):
        bbr.dataset(sources, currency_view="functional", **args)
    with pytest.raises(Problem, match="all four"):
        bbr.dataset({"billings": []}, currency_view="transaction", **args)


def test_activation_booking_identity_and_separate_modification_exclusion() -> None:
    from erev_api.domain.reports.builders.bbr_bookings import new_contracts

    booking = {
        "id": str(UUID(int=10)),
        "contract_id": str(UUID(int=20)),
        "contracting_entity_id": str(ENTITY.id),
        "event_type": "CONTRACT_BOOKED",
        "record_seq": 1,
        "effective_date": "2026-07-01",
        "supersedes_event_id": None,
        "payload": {
            "transaction_currency": "USD",
            "lines": [
                {"total_price": {"amount": "100", "currency": "USD"}},
                {"total_price": {"amount": "-10", "currency": "USD"}},
            ],
        },
    }
    activation = {
        **booking,
        "id": str(UUID(int=11)),
        "event_type": "CONTRACT_ACTIVATED",
        "record_seq": 2,
        "effective_date": "2026-07-02",
        "payload": {},
    }
    source = {"events": [booking], "modification_booking_ids": []}
    assert new_contracts(source) == ()
    source["events"] = [
        booking,
        activation,
        {**activation, "id": str(UUID(int=12)), "record_seq": 3},
    ]
    values = new_contracts(source)
    assert len(values) == 1 and values[0].amount == Decimal("90")
    assert values[0].effective_date == date(2026, 7, 2)
    assert values[0].basis_ids == (UUID(int=10), UUID(int=11))
    assert new_contracts({**source, "modification_booking_ids": [booking["id"]]}) == ()
    with pytest.raises(Problem, match="no booking source"):
        new_contracts({**source, "events": [activation]})
    void = {**activation, "event_type": "CONTRACT_VOIDED", "id": str(UUID(int=13)), "record_seq": 4}
    assert new_contracts({**source, "events": [booking, activation, void]}) == ()


def test_modification_uses_application_group_and_requires_complete_price_basis() -> None:
    from erev_api.domain.reports.builders import bbr_modifications

    group, later_group = str(UUID(int=30)), str(UUID(int=31))
    event, before_id, version_id = (str(UUID(int=n)) for n in (32, 33, 34))
    before = {
        "id": before_id,
        "combination_group_id": group,
        "book_code": "ASC606",
        "transaction_currency": "USD",
        "transaction_price": "240000.00",
    }
    version = {
        **before,
        "id": version_id,
        "previous_version_id": before_id,
        "transaction_price": "300000.00",
        "cause_event_ids": [event],
    }
    source = {
        "modifications": [
            {
                "id": str(UUID(int=35)),
                "contract_id": str(UUID(int=36)),
                "contracting_entity_id": str(ENTITY.id),
                "effective_date": "2026-09-16",
                "applied_event_id": event,
            }
        ],
        "applications": [{"id": event, "combination_group_id": group}],
        "versions": [
            version,
            {
                **version,
                "id": str(UUID(int=37)),
                "combination_group_id": later_group,
                "transaction_price": "900000.00",
            },
        ],
        "predecessors": [before],
        "cause_types": {event: "CONTRACT_AMENDED"},
    }
    assert bbr_modifications.values(source)[0].amount == Decimal("60000.00")
    with pytest.raises(Problem, match="predecessor is unavailable"):
        bbr_modifications.values({**source, "predecessors": []})
    with pytest.raises(Problem, match="unique application version"):
        bbr_modifications.values(
            {**source, "versions": [version, {**version, "id": str(UUID(int=38))}]}
        )
    extra = str(UUID(int=39))
    with pytest.raises(Problem, match="shared or unknown"):
        bbr_modifications.values(
            {
                **source,
                "versions": [{**version, "cause_event_ids": [event, extra]}],
                "cause_types": {event: "CONTRACT_AMENDED", extra: "ESTIMATE_CHANGED"},
            }
        )


def test_functional_valuation_reuses_retained_spot_rate_without_live_reads() -> None:
    from datetime import UTC, datetime
    from unittest.mock import Mock

    from erev_api.domain.reports.builders import ReportParams, SourceBinding, bbr_currency

    rate = {
        "id": str(UUID(int=41)),
        "fx_rate_set_version_id": str(UUID(int=42)),
        "base_currency": "EUR",
        "quote_currency": "USD",
        "effective_date": "2026-07-04",
        "rate_type": "spot",
        "rate": "1.2345",
    }
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    binding = SourceBinding(
        cutoff=cutoff,
        versions={},
        labels={},
        row_keys=frozenset(),
        evidence={bbr_currency.EVIDENCE: [rate]},
    )
    params = ReportParams(
        "bookings_billings_revenue",
        1,
        {},
        (ENTITY.id,),
        cutoff,
        book_code="ASC606",
        binding=binding,
    )
    source = replace(contribution("100.01", date(2026, 7, 4)), currency="EUR")
    uow = Mock()
    result = bbr_currency.functional(uow, params, {"billings": [source]}, (ENTITY,))
    valued = result["billings"][0]
    assert valued.functional_amount == Decimal("123.46")
    assert valued.functional_currency == "USD"
    assert valued.basis_ids == (UUID(int=41), UUID(int=42))
    assert valued.amount == Decimal("100.01") and valued.currency == "EUR"
    uow.session.execute.assert_not_called()
    with pytest.raises(Problem, match="one approved spot rate"):
        bbr_currency.functional(
            uow,
            replace(params, binding=replace(binding, evidence={bbr_currency.EVIDENCE: []})),
            {"billings": [source]},
            (ENTITY,),
        )
