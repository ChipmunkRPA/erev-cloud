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


def setup_preview(
    monkeypatch,
    *,
    dirty=False,
    currency="USD",
    identities=(("A", "POINTS"), ("B", "POINTS")),
    targets=(),
    extra=False,
    version_targets=None,
    stale_population=False,
    stale_target=False,
):
    portfolio, estimate, version = uuid4(), uuid4(), uuid4()
    members = []
    results = []
    computed = []
    for index, ((name, key), ssp) in enumerate(zip(identities, ("100", "200"), strict=True)):
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
                        "obligation_key": key,
                        "recognition_method": "REDEMPTION_PATTERN",
                        "txn_currency": currency if index == 0 else "USD",
                        "modification_boundary_no": 0,
                        "original_ssp_selected": Decimal(ssp),
                        "remaining_ssp": Decimal(ssp),
                        "quantity": Decimal(10),
                    }
                ],
            ]
        )
        if extra:
            results[-1].append(
                {
                    **results[-1][0],
                    "obligation_id": uuid4(),
                    "obligation_key": "OTHER",
                    "original_ssp_selected": Decimal(900),
                }
            )
        computed.append({"id": cv, "contract_computation_id": computation})
    from erev_api.schemas.estimates import SharedEstimateApplicationBasis

    binding = None
    if version_targets is not None:
        binding = SharedEstimateApplicationBasis(
            portfolio_id=portfolio,
            target_obligation_keys=list(version_targets),
            members=[
                {
                    "contract_id": uuid4() if stale_population else member["contract_id"],
                    "contract_key": results[index * 3]["external_id"],
                    "obligation_ids": [
                        uuid4() if stale_target else row["obligation_id"]
                        for row in results[index * 3 + 2]
                        if row["obligation_key"] in version_targets
                    ],
                    "obligation_keys": list(version_targets),
                }
                for index, member in enumerate(members)
            ],
        )
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
        Mock(
            return_value=SimpleNamespace(
                estimate_kind="BREAKAGE",
                target_obligation_keys=list(targets),
                allocation_target="OBLIGATIONS" if targets else "CONTRACT",
            )
        ),
    )
    monkeypatch.setattr(
        service.portfolio_estimate_versions,
        "get",
        Mock(
            return_value=SimpleNamespace(
                currency="USD",
                portfolio_application_basis=binding,
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


@pytest.mark.parametrize(
    "identities",
    [
        (("A/B", "C"), ("A", "B/C")),
        (("A%2FB", "C"), ("A/B", "C")),
    ],
)
def test_delimiters_preserve_independent_original_allocation_sources(monkeypatch, identities):
    value = service.preview(*setup_preview(monkeypatch, identities=identities))
    assert value.allocated_total == "9"
    assert {
        (row.contract_external_id, row.obligation_key): row.breakage_quantity
        for row in value.shares
    } == {
        identities[0]: "3",
        identities[1]: "6",
    }
    assert len({row.contract_version_id for row in value.shares}) == 2


def test_selected_targets_exclude_other_eligible_obligations(monkeypatch):
    value = service.preview(*setup_preview(monkeypatch, targets=("POINTS",), extra=True))
    assert [
        (s.contract_external_id, s.obligation_key, s.breakage_quantity) for s in value.shares
    ] == [("A", "POINTS", "3"), ("B", "POINTS", "6")]
    assert value.allocated_total == "9"


def test_selected_target_missing_from_one_member_refuses_preview(monkeypatch):
    args = setup_preview(
        monkeypatch, targets=("POINTS",), identities=(("A", "POINTS"), ("B", "OTHER"))
    )
    with pytest.raises(Problem, match="Every member must retain every selected"):
        service.preview(*args)


def test_breakage_definition_resolves_common_targets_for_each_member():
    from erev_api.schemas.portfolios import PortfolioEstimateIn

    a, b, oa, ob = uuid4(), uuid4(), uuid4(), uuid4()
    session = Mock()
    population = Mock()
    population.mappings.return_value.all.return_value = [{"contract_id": a}, {"contract_id": b}]
    targets = Mock()
    targets.all.return_value = [
        SimpleNamespace(id=oa, contract_id=a, obligation_key="POINTS"),
        SimpleNamespace(id=ob, contract_id=b, obligation_key="POINTS"),
    ]
    session.execute.side_effect = [population, targets]
    body = PortfolioEstimateIn(
        element_code="BREAKAGE",
        estimate_kind="BREAKAGE",
        method="RATE",
        target_obligation_keys=["POINTS"],
    )
    assert service.portfolios._shared_targets(session, uuid4(), body) == sorted([oa, ob])


def test_version_breakage_targets_override_definition(monkeypatch):
    args = setup_preview(monkeypatch, targets=("POINTS",), extra=True, version_targets=("OTHER",))
    value = service.preview(*args)
    assert {row.obligation_key for row in value.shares} == {"OTHER"}
    assert [row.breakage_quantity for row in value.shares] == ["4.5", "4.5"]


@pytest.mark.parametrize("changed", ["stale_population", "stale_target"])
def test_version_breakage_targets_reject_changed_original_identities(monkeypatch, changed):
    args = setup_preview(monkeypatch, version_targets=("POINTS",), **{changed: True})
    with pytest.raises(Problem, match="Save the draft again"):
        service.preview(*args)
