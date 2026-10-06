"""04 table 15.4-I rev 1.81 (DIN-12 partial booking; team-lead's ruling on Codex 0339 §2, the
activation.py touch in its own commit): an open ``PRODUCT_UNMAPPED`` item naming the contract fails
``PRODUCT_TEMPLATE_SSP`` even when the group's latest computation SUCCEEDED — the refused-findings
path is unchanged and still covers the SSP codes while a computation was refused."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from erev_api.domain.contracts import activation
from sqlalchemy.dialects import postgresql

CONTRACT = UUID(int=0xC0)
GROUP = UUID(int=0x60)
PLAT = UUID(int=0xA1)


class _Rows:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows, self._scalar = rows or [], scalar

    def mappings(self) -> Any:
        return iter(self._rows)

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class _Session:
    """The computation status, the open items of the group / contract and the booking stream."""

    def __init__(
        self, *, status: str, naming: list[dict[str, Any]], group_items: list[dict[str, Any]]
    ) -> None:
        self.status, self.naming, self.group_items = status, naming, group_items

    def execute(self, statement: Any) -> Any:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        if "FROM erev.contract_computation" in sql:
            return _Rows(scalar=self.status)
        if "FROM erev.exception_item" in sql and "contract_id" in sql:
            return _Rows(self.naming)
        if "FROM erev.exception_item" in sql:
            return _Rows(self.group_items)
        raise AssertionError(sql)


def _obligation() -> dict[str, Any]:
    return {"id": UUID(int=0x0B), "obligation_key": "SF-OI-Q-003-1", "product_id": PLAT}


def _products() -> dict[UUID, dict[str, Any]]:
    return {
        PLAT: {
            "id": PLAT,
            "code": "QUAY-PLAT",
            "is_active": True,
            "default_pob_template_id": UUID(int=0x7),
        }
    }


def _named_item() -> dict[str, Any]:
    return {
        "code": "PRODUCT_UNMAPPED",
        "obligation_id": None,
        "source_payload": {
            "detail": {"product_code": "SF-PROD-X99", "line_external_ids": ["SF-OI-Q-003-2"]}
        },
    }


def test_open_product_unmapped_naming_the_contract_fails_the_item_after_a_succeeded_computation(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(activation, "_latest_booking", lambda session, contract_id: {"lines": []})
    session = _Session(status="SUCCEEDED", naming=[_named_item()], group_items=[])
    contract_row = {"id": CONTRACT, "combination_group_id": GROUP}
    item = activation.product_template_ssp(
        session,  # type: ignore[arg-type]
        contract_row,
        [_obligation()],
        _products(),
        {UUID(int=0x7): "distinct"},
    )
    assert item.code == "PRODUCT_TEMPLATE_SSP" and item.passed is False
    assert item.detail == "No product, template or SSP for SF-OI-Q-003-2 (SF-PROD-X99)."


def test_without_a_naming_item_a_succeeded_computation_passes_as_before(monkeypatch: Any) -> None:
    monkeypatch.setattr(activation, "_latest_booking", lambda session, contract_id: {"lines": []})
    session = _Session(status="SUCCEEDED", naming=[], group_items=[])
    item = activation.product_template_ssp(
        session,  # type: ignore[arg-type]
        {"id": CONTRACT, "combination_group_id": GROUP},
        [_obligation()],
        _products(),
        {UUID(int=0x7): "distinct"},
    )
    assert item.passed is True and item.detail is None
