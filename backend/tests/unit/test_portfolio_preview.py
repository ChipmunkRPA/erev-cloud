"""Preview uses retained member SSP and refuses incomplete computation populations."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from erev_api.domain.contracts import portfolio_preview as service
from erev_api.problems import Problem
from erev_engine.bundle import FxRateInput


def setup_preview(monkeypatch, *, dirty=False, currency="USD"):
    portfolio, estimate, version = uuid4(), uuid4(), uuid4()
    members = []
    results = []
    computed = []
    for name, ssp in [("A", "100"), ("B", "200")]:
        contract, group, computation, cv = uuid4(), uuid4(), uuid4(), uuid4()
        members.append({"contract_id": contract})
        results.extend(
            [
                {"id": contract, "external_id": name, "combination_group_id": group},
                {"dirty_since": "changed" if dirty else None, "head_computation_id": computation},
                [
                    {
                        "contract_id": contract,
                        "contract_version_id": cv,
                        "obligation_id": uuid4(),
                        "obligation_key": "POINTS",
                        "recognition_method": "REDEMPTION_PATTERN",
                        "txn_currency": currency if name == "A" else "USD",
                        "modification_boundary_no": 0,
                        "original_ssp_selected": Decimal(ssp),
                        "remaining_ssp": Decimal(ssp),
                        "quantity": Decimal(10),
                    }
                ],
            ]
        )
        computed.append({"id": cv, "contract_computation_id": computation})
    session = Mock()

    def result(value):
        r = Mock()
        r.mappings.return_value.all.return_value = value
        r.mappings.return_value.one.return_value = value
        r.mappings.return_value.one_or_none.return_value = value
        return r

    session.execute.side_effect = [result(members), *map(result, results)]
    session.scalars.return_value = []
    monkeypatch.setattr(
        service.portfolios,
        "get_estimate_definition",
        Mock(return_value=SimpleNamespace(estimate_kind="BREAKAGE")),
    )
    monkeypatch.setattr(
        service.portfolio_estimate_versions,
        "get",
        Mock(
            return_value=SimpleNamespace(
                currency="USD",
                effective_date=date(2026, 10, 1),
                parameters={"portfolio_total_breakage_quantity": "9"},
            )
        ),
    )
    monkeypatch.setattr(service.queries, "primary_book", Mock(return_value="PRIMARY"))
    monkeypatch.setattr(service.queries, "version_at", Mock(side_effect=computed))
    return session, Mock(), portfolio, estimate, version


def test_retained_ssp_source_and_total(monkeypatch):
    args = setup_preview(monkeypatch)
    value = service.preview(*args)
    assert value.basis == "CURRENT_COMPUTED_SSP_PREVIEW"
    assert value.allocated_total == value.total_breakage_quantity == "9"
    assert [(row.contract_external_id, row.ssp, row.breakage_quantity) for row in value.shares] == [
        ("A", "100", "3"),
        ("B", "200", "6"),
    ]
    assert len({row.contract_version_id for row in value.shares}) == 2
    service.portfolios.get_estimate_definition.assert_called_once()
    service.portfolio_estimate_versions.get.assert_called_once()


def test_refuses_dirty_population(monkeypatch):
    with pytest.raises(Problem, match="Recompute"):
        service.preview(*setup_preview(monkeypatch, dirty=True))


def rate(**changes):
    return FxRateInput(
        **{
            **dict(
                rate_key="GBP-USD",
                version_key="v1",
                rate_type="spot",
                base_currency="GBP",
                quote_currency="USD",
                effective_date=date(2026, 9, 30),
                period_key=None,
                rate=Decimal("2"),
            ),
            **changes,
        }
    )


def test_foreign_weights_change_allocation_and_expose_original_source(monkeypatch):
    args = setup_preview(monkeypatch, currency="GBP")
    monkeypatch.setattr(
        service.bundles,
        "fx_rate_inputs",
        Mock(
            return_value=[
                rate(),
                rate(
                    rate_key="future",
                    effective_date=date(2026, 10, 2),
                    rate=Decimal("3"),
                ),
            ]
        ),
    )
    value = service.preview(*args)
    assert [row.breakage_quantity for row in value.shares] == ["4.5", "4.5"]
    assert value.allocated_total == "9"
    a, b = value.shares
    assert a.ssp == "200"
    assert a.ssp_conversion.original_ssp == "100"
    assert a.ssp_conversion.rate_key == "GBP-USD"
    assert a.ssp_conversion.rate_version_key == "v1"
    assert a.ssp_conversion.rate_date == date(2026, 9, 30)
    assert b.ssp_conversion is None


@pytest.mark.parametrize(
    "rates",
    [
        [],
        [rate(base_currency="USD", quote_currency="GBP")],
        [rate(effective_date=date(2026, 10, 2))],
    ],
)
def test_missing_inverse_or_future_rates_refuse_complete_preview(monkeypatch, rates):
    args = setup_preview(monkeypatch, currency="GBP")
    monkeypatch.setattr(service.bundles, "fx_rate_inputs", Mock(return_value=rates))
    with pytest.raises(Problem, match="Publish a direct GBP/USD"):
        service.preview(*args)


def test_ssp_conversion_does_not_round_small_weights():
    value = service.portfolio_ssp_fx.convert(
        Decimal("0.000000000000000001"),
        "GBP",
        "USD",
        date(2026, 10, 1),
        [rate(rate=Decimal("1.234567890123"))],
    )
    assert value.converted_ssp == "0.000000000000000001234567890123"
