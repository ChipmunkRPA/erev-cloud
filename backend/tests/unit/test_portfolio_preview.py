"""Preview uses retained member SSP and refuses incomplete computation populations."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from erev_api.domain.contracts import portfolio_preview as service
from erev_api.problems import Problem


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
                        "txn_currency": currency,
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
                currency="USD", parameters={"portfolio_total_breakage_quantity": "9"}
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


@pytest.mark.parametrize(
    "kwargs,detail", [({"dirty": True}, "Recompute"), ({"currency": "GBP"}, "cross-currency")]
)
def test_refuses_partial_or_unconverted_population(monkeypatch, kwargs, detail):
    with pytest.raises(Problem, match=detail):
        service.preview(*setup_preview(monkeypatch, **kwargs))
