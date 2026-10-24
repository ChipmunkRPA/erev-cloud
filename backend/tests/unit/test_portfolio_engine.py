"""Shared versions reach the native loader with explicit targets and stable source identity."""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID

import pytest
from erev_api.domain.contracts import bundles
from erev_engine.bundle import PortfolioInput
from erev_engine.errors import EngineError

P, A, B, OA, OB, E, V = (UUID(int=i) for i in range(1, 8))


def load(
    *,
    quantity=None,
    kind="RETURN_RATE",
    targets=None,
    currency="USD",
    population=True,
    basis=None,
    parameters=None,
):
    element = dict(
        id=E,
        contract_id=None,
        portfolio_id=P,
        element_code="RETURN/SHARED",
        estimate_kind=kind,
        method="RATE",
        vc_element_type=None,
        direction="INCREASE",
        allocation_target="CONTRACT",
        obligation_id=None,
        target_obligation_ids=[OA, OB] if targets is None else targets,
    )
    version = dict(
        id=V,
        estimate_id=E,
        version_no=1,
        scenarios=[],
        status="APPROVED",
        effective_date=date(2026, 1, 1),
        parameters={} if parameters is None else parameters,
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=None,
        rate=Decimal("0.08"),
        expected_total_amount=None,
        expected_quantity=quantity,
        amortization_months=None,
        currency="USD",
        supersedes_version_id=None,
        content_sha256="a" * 64,
        portfolio_application_basis=basis,
    )
    session = Mock()
    response1, response2 = Mock(), Mock()
    response1.mappings.return_value = [version]
    response2.mappings.return_value = [element]
    session.execute.side_effect = [response1, response2]
    return bundles._estimate_versions(
        session,
        [dict(estimate_version_id=V, event_type="ESTIMATE_CHANGED")],
        [],
        contracts={
            A: dict(external_id="A", transaction_currency="USD"),
            B: dict(external_id="B", transaction_currency=currency),
        },
        obligation_keys={OA: "GOODS", OB: "GOODS"},
        obligation_owners={OA: A, OB: B},
        portfolios=[PortfolioInput(str(P), ("A", "B"))] if population else [],
    )


def test_loads_shared_source_and_event_reference():
    inputs, keys = load()
    assert len(inputs) == 1
    item = inputs[0]
    assert item.estimate_key == f"PORTFOLIO:{P}/RETURN%2FSHARED"
    assert keys[str(V)] == item.version_key == f"{item.estimate_key}@v1"
    assert item.content_sha256 == "a" * 64
    assert item.rate == Decimal("0.08")
    assert item.target_obligation_keys == ("GOODS",)


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"quantity": Decimal(8)}, "total quantities"),
        ({"kind": "BREAKAGE"}, "frozen member allocations"),
        ({"targets": [OA]}, "matching targets"),
        ({"targets": []}, "matching targets"),
        (
            {"currency": "GBP", "parameters": {"carrying_cost_per_unit": "12"}},
            "member-currency conversion",
        ),
        ({"population": False}, "retained member population"),
    ],
)
def test_incomplete_shared_application_does_not_disappear(kwargs, reason):
    with pytest.raises(EngineError, match=reason):
        load(**kwargs)


@pytest.mark.parametrize("active", [("B",), ()])
def test_retired_targets_reach_loader_without_reactivating_members(active):
    bindings = [
        dict(contract_id=str(c), contract_key=k, obligation_ids=[str(o)], obligation_keys=["GOODS"])
        for c, k, o in [(A, "A", OA), (B, "B", OB)]
    ]
    inputs, _ = load(
        population=False,
        basis=dict(
            schema_version=1,
            portfolio_id=str(P),
            members=[m for m in bindings if m["contract_key"] in active],
            retired_members=[m for m in bindings if m["contract_key"] not in active],
        ),
    )
    assert inputs[0].portfolio_member_contract_keys == active
    assert inputs[0].target_obligation_keys == ("GOODS",)


def test_new_member_binding_can_use_its_own_original_obligation_id():
    inputs, _ = load(
        targets=[OA],
        basis=dict(
            schema_version=1,
            portfolio_id=str(P),
            members=[
                dict(
                    contract_id=str(B),
                    contract_key="B",
                    obligation_ids=[str(OB)],
                    obligation_keys=["GOODS"],
                )
            ],
            retired_members=[],
        ),
    )
    assert inputs[0].portfolio_member_contract_keys == ("B",)
    assert inputs[0].target_obligation_keys == ("GOODS",)


@pytest.mark.parametrize("target,key", [(OA, "GOODS"), (OB, "OTHER")])
def test_frozen_binding_rejects_wrong_member_or_obligation_key(target, key):
    from erev_api.problems import Problem

    with pytest.raises(Problem, match="Retained targets"):
        load(
            targets=[OA],
            basis=dict(
                schema_version=1,
                portfolio_id=str(P),
                members=[
                    dict(
                        contract_id=str(B),
                        contract_key="B",
                        obligation_ids=[str(target)],
                        obligation_keys=[key],
                    )
                ],
            ),
        )


@pytest.mark.parametrize(
    "parameters", [{}, {"carrying_cost_per_unit": "0.00", "recovery_cost_per_unit": "0"}]
)
def test_shared_rate_without_monetary_amounts_can_span_currencies(parameters):
    inputs, _ = load(currency="GBP", parameters=parameters)
    assert inputs[0].rate == Decimal("0.08")
    assert inputs[0].currency == "USD"


@pytest.mark.parametrize("cost", ["0.01", "-0.01", "NaN", "Infinity"])
def test_nonzero_or_invalid_recovery_cost_is_not_relabelled_as_member_currency(cost):
    with pytest.raises(EngineError):
        load(currency="GBP", parameters={"recovery_cost_per_unit": cost})
