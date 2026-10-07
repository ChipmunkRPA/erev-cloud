"""Scoped calculation inputs preserve O > C > P precedence and member isolation."""

from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.contracts.policy_inputs import scoped_inputs
from erev_engine.bundle import ResolvedPolicyInput
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.state import PolicyResolver

C1, C2, O1, O2 = (UUID(int=n) for n in range(1, 5))
CONTRACTS = {C1: "A", C2: "B"}
OBLIGATIONS = [
    {"id": O1, "contract_id": C1, "obligation_key": "O1"},
    {"id": O2, "contract_id": C2, "obligation_key": "O1"},
]
LINES = [(key, {"obligation_key": "O1"}) for key in CONTRACTS.values()]


def row(
    n: int,
    *,
    contract: UUID = C1,
    obligation: UUID | None = None,
    code: str = "returns.model",
    value: Any = "EXPECTED_RETURNS",
) -> dict[str, Any]:
    return {
        "id": UUID(int=n),
        "contract_id": contract,
        "obligation_id": obligation,
        "level": "CONTRACT" if obligation is None else "OBLIGATION",
        "policy_key": code,
        "value": value,
    }


def inputs(*rows: dict[str, Any], book: str = "ASC606") -> tuple[ResolvedPolicyInput, ...]:
    return scoped_inputs(
        rows, book_code=book, contracts=CONTRACTS, obligations=OBLIGATIONS, lines=LINES
    )


def test_contract_exception_overrides_product_without_leaking_to_other_members() -> None:
    code = "returns.model"
    products = [
        ResolvedPolicyInput(
            code, "OBLIGATION", obligation_subject_key(key, "O1"), "NO_RETURNS", "P", "product", "K"
        )
        for key in ("A", "B")
    ]
    merged = {(p.code, p.scope, p.subject_key): p for p in [*products, *inputs(row(10))]}
    resolver = PolicyResolver(tuple(merged[key] for key in sorted(merged)))
    assert (
        resolver.value(code, contract="A", obligation=obligation_subject_key("A", "O1"))
        == "EXPECTED_RETURNS"
    )
    assert (
        resolver.value(code, contract="B", obligation=obligation_subject_key("B", "O1"))
        == "NO_RETURNS"
    )
    assert resolver.value(code, contract="A") == "EXPECTED_RETURNS"


def test_obligation_exception_beats_contract_and_latest_approval_wins() -> None:
    rows = inputs(row(10, obligation=O1, value="NO_RETURNS"), row(9, obligation=O1), row(8))
    resolver = PolicyResolver(rows)
    found = resolver.resolved(
        "returns.model", contract="A", obligation=obligation_subject_key("A", "O1")
    )
    assert (found.value, found.level, found.source_ref) == ("NO_RETURNS", "O", str(UUID(int=10)))
    assert resolver.value("returns.model", contract="A") == "EXPECTED_RETURNS"


def test_disallowed_scopes_foreign_obligations_and_period_pins_are_not_admitted() -> None:
    assert inputs(row(10, code="balance.right_to_consideration", value="UNCONDITIONAL")) == ()
    assert inputs(row(10, obligation=O2)) == ()
    assert inputs(row(10, contract=UUID(int=99))) == ()
    assert inputs(row(10, code="fx.cl_historical_layering")) == ()
    assert inputs(row(10, code="not.a.policy")) == ()


def test_financing_rate_reaches_contract_reader() -> None:
    rate = {"basis": "CUSTOMER_CREDIT_RATE", "annual_rate": "0.05", "compounding": "ANNUAL"}
    resolver = PolicyResolver(inputs(row(10, code="sfc.discount_rate_basis", value=rate)))
    assert resolver.value("sfc.discount_rate_basis", contract="A") == rate


def test_product_fallback_is_retained_but_not_used_as_a_contract_default() -> None:
    policy = ResolvedPolicyInput(
        "returns.model", "PRODUCT", "WIDGET", "NO_RETURNS", "P", "product", "K"
    )
    resolver = PolicyResolver((policy,))
    with pytest.raises(ValueError, match="no value for the requested scope"):
        resolver.value("returns.model", contract="A")
