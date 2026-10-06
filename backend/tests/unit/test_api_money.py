"""API money types KRN-MONEY (dev-guide §5.9; 04 API-C-06; REQ-PLT-031; BUILD_SPEC FND-9)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from erev_api.money import (
    MONEY_MESSAGE,
    DecimalStr,
    MoneyIn,
    RateStr,
    money_in_to_minor,
    money_out,
)
from erev_api.problems import Problem, install_handlers
from erev_engine.currencies import ISO_4217
from fastapi import FastAPI
from pydantic import TypeAdapter, ValidationError
from support.http import call


def build_app() -> FastAPI:
    app = FastAPI()
    install_handlers(app)

    @app.post("/probe/money")
    def post_money(body: MoneyIn) -> dict[str, int]:
        return {"minor": money_in_to_minor(body, ISO_4217)}

    return app


def test_req_plt_031_json_number_rejected() -> None:
    app = build_app()
    for number in (12.3, 12):
        response = call(app, "POST", "/probe/money", json={"amount": number, "currency": "USD"})
        assert response.status_code == 422
        body = response.json()
        assert body["type"] == "https://erev.dev/problems/validation-failed"
        assert body["errors"][0]["rule_id"] == "API-C-06"
        assert body["errors"][0]["field"] == "amount"
        assert body["errors"][0]["message"] == MONEY_MESSAGE
    accepted = call(app, "POST", "/probe/money", json={"amount": "12.30", "currency": "USD"})
    assert accepted.status_code == 200
    assert accepted.json() == {"minor": 1230}
    inexact = call(app, "POST", "/probe/money", json={"amount": "12.345", "currency": "USD"})
    assert inexact.status_code == 422
    assert inexact.json()["errors"][0]["rule_id"] == "API-C-06"


def test_api_c_06_non_ascii_digits_rejected() -> None:
    app = build_app()
    # Arabic-Indic and fullwidth digits, which Decimal would accept (D-78).
    for amount in ("\u0661\u0662.\u0663\u0660", "\uff11\uff12.\uff13\uff10"):
        response = call(app, "POST", "/probe/money", json={"amount": amount, "currency": "USD"})
        assert response.status_code == 422
        assert response.json()["errors"][0]["rule_id"] == "API-C-06"
    for adapter, value in (
        (TypeAdapter(DecimalStr), "\u0660.\u0662\u0665"),
        (TypeAdapter(RateStr), "\u0661.\u0660\u0668"),
    ):
        with pytest.raises(ValidationError) as rejected:
            adapter.validate_python(value)
        assert rejected.value.errors()[0]["ctx"]["rule_id"] == "API-C-06"
    accepted = call(app, "POST", "/probe/money", json={"amount": "12.30", "currency": "USD"})
    assert accepted.status_code == 200
    assert accepted.json() == {"minor": 1230}


def test_krn_money_06_money_out_minor_unit_strings() -> None:
    assert money_out(Decimal("1200.0000"), "JPY", ISO_4217).amount == "1200"
    assert money_out(Decimal("12.3000"), "USD", ISO_4217).amount == "12.30"
    assert money_out(Decimal("1.2500"), "BHD", ISO_4217).amount == "1.250"
    assert money_out(Decimal("-4000.0000"), "USD", ISO_4217).amount == "-4000.00"
    assert money_out(Decimal("-0.0000"), "USD", ISO_4217).amount == "0.00"
    with pytest.raises(ValueError):
        money_out(Decimal("12.3450"), "USD", ISO_4217)
    assert money_out(1230, "USD", ISO_4217, minor=True).model_dump() == {
        "amount": "12.30",
        "currency": "USD",
    }
    with pytest.raises(TypeError):
        money_out(12.3, "USD", ISO_4217)  # type: ignore[arg-type]


def test_money_in_to_minor_is_exact() -> None:
    assert money_in_to_minor(MoneyIn(amount="12.30", currency="USD"), ISO_4217) == 1230
    assert money_in_to_minor(MoneyIn(amount="1200", currency="JPY"), ISO_4217) == 1200
    assert money_in_to_minor(MoneyIn(amount="-1.250", currency="BHD"), ISO_4217) == -1250
    for amount, currency in (("12.345", "USD"), ("1200.5", "JPY")):
        with pytest.raises(Problem) as caught:
            money_in_to_minor(MoneyIn(amount=amount, currency=currency), ISO_4217)
        assert caught.value.slug == "validation-failed"
        assert caught.value.errors[0].rule_id == "API-C-06"
        assert caught.value.errors[0].field == "amount"
    with pytest.raises(ValidationError) as number:
        MoneyIn(amount=12.3, currency="USD")  # type: ignore[arg-type]
    assert number.value.errors()[0]["ctx"]["rule_id"] == "API-C-06"


def test_decimal_and_rate_strings() -> None:
    decimal = TypeAdapter(DecimalStr)
    rate = TypeAdapter(RateStr)
    assert decimal.validate_python("0.333333333333333333") == "0.333333333333333333"
    for rejected in ("0.3333333333333333333", "1e3"):
        with pytest.raises(ValidationError):
            decimal.validate_python(rejected)
    with pytest.raises(ValidationError) as number:
        decimal.validate_python(0.5)
    assert number.value.errors()[0]["ctx"]["rule_id"] == "API-C-06"
    for rejected in ("0", "-1.0"):
        with pytest.raises(ValidationError):
            rate.validate_python(rejected)
    assert rate.validate_python("1.083450") == "1.083450"
