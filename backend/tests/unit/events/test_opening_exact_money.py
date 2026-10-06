"""D-98 candidate 127 (revision 1; Codex production-20260921-0442, report
``PRODUCTION-LMG-OPENING-PRECISION-0dea7b88.md``; 04 rev 1.61 §16.0 API-S-ExactMoney, §16.3
``OPENING_BALANCE_ESTABLISHED`` version 2;
ENGINE_SPEC S07-R-03 / S07-R-11): the eight money members of an opening obligation carry the exact
legacy value through the admitted event boundary to the engine's exact operands.

CPU only: no database; the append itself (``stream.append_events``) and the migration applier are
DB-bound and NOT RUN here. Witnesses per Codex: original over-precision strings through the actual
admitted payload and bundle boundary; exact engine operands checked separately from posted outputs;
negative, zero and currency behaviour; old (version 1) stored payloads unchanged in bytes and hash;
refusal by name for out-of-bound values and exponent notation with no model — hence no capture.
Fail-first on the docs head 0f6462d3: ``OpeningBalanceEstablishedV2``, ``ExactMoneyIn`` and
``exact_plain_decimal`` do not exist and version 1 refuses a 15-place amount.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest
from erev_api import money
from erev_api.enums import ContractEventType
from erev_api.events import payloads
from erev_api.events.payloads import LATEST_SCHEMA_VERSION, PAYLOADS
from erev_engine.canonical import sha256_hex
from erev_engine.money import to_fraction
from erev_engine.stages.s07_onboarding import opening
from pydantic import ValidationError
from support.recognition import event_view

OPENING = ContractEventType.OPENING_BALANCE_ESTABLISHED
# WLD-F-15-shaped over-precision values (14 and 15 places), not asserted to be particular rows.
REVENUE = "322.10109018830525"
REMAINING = "977.89890981169475"
POSITION = "-1299.999999999999995"
RECLASS = "0.00000000000001"


def _usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _row(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "obligation_key": "POB-01",
        "delivered_quantity_cum": "5",
        "ssp_delivered_cum": "500.0",
        "remaining_quantity": "0",
        "remaining_ssp": "0",
        "revenue_cum": _usd(REVENUE),
        "billed_cum": _usd("1300"),
        "catch_up_cum": _usd("0"),
        "pre_standard_revenue_cum": _usd("0"),
        "remaining_allocation": _usd(REMAINING),
        "remaining_billing": _usd("0"),
        "position_obligation": _usd(POSITION),
        "netting_reclass_amount": _usd(RECLASS),
    }
    base.update(changes)
    return base


def _body(*rows: dict[str, Any], **members: Any) -> dict[str, Any]:
    return {
        "reason": "LEGACY_MIGRATION",
        "cutover_date": "2023-01-31",
        "migration_batch_id": None,
        "obligations": list(rows) or [_row()],
        **members,
    }


def test_version_2_admits_the_exact_over_precision_amounts_and_stores_them_verbatim() -> None:
    """The admitted representation: version 2 validates 14- and 15-place amounts as ExactMoneyIn,
    the stored JSON carries the original strings (no rounding, no re-formatting), and the registry
    names version 2 as the latest with the DG-KRN-EVT-03 model name."""
    assert LATEST_SCHEMA_VERSION[OPENING] == 2
    assert PAYLOADS[(OPENING, 2)] is payloads.OpeningBalanceEstablishedV2
    assert payloads.model_name(OPENING, 2) == "OpeningBalanceEstablishedV2"
    parsed = payloads.parse_payload(OPENING, 2, _body())
    assert isinstance(parsed, payloads.OpeningBalanceEstablishedV2)
    (row,) = parsed.obligations
    assert isinstance(row, payloads.OpeningObligationV2)
    assert isinstance(row.revenue_cum, money.ExactMoneyIn)
    assert row.revenue_cum.amount == REVENUE and row.position_obligation.amount == POSITION
    stored = payloads.payload_json(parsed)
    assert stored["obligations"][0]["revenue_cum"] == _usd(REVENUE)
    assert stored["obligations"][0]["position_obligation"] == _usd(POSITION)
    assert stored["obligations"][0]["netting_reclass_amount"] == _usd(RECLASS)
    # the stored form validates again as the same payload
    assert payloads.parse_payload(OPENING, 2, stored) == parsed


def test_engine_operands_are_the_exact_legacy_values() -> None:
    """Through the actual bundle boundary: ``engine_payload`` unwraps the money object to its
    amount string without rounding and stage 07 parses it to the exact rational — checked against
    ``Fraction(Decimal(text))``, separately from any posted output."""
    from erev_api.domain.contracts import bundles

    stored = payloads.payload_json(payloads.parse_payload(OPENING, 2, _body()))
    unwrapped = bundles.engine_payload(stored)
    item = unwrapped["obligations"][0]
    # The stored form carries ``fair_value_contract_liability: null`` (the unset optional member);
    # it is handed to the engine UNMODIFIED — stage 07 reads that null as absence (Codex 0533 F1;
    # the intact parse / apply pipeline is witnessed in test_opening_optional_null_boundary.py).
    assert unwrapped["fair_value_contract_liability"] is None
    assert item["revenue_cum"] == REVENUE and item["position_obligation"] == POSITION
    assert to_fraction(item["revenue_cum"]) == Fraction(Decimal(REVENUE))
    assert to_fraction(item["position_obligation"]) == Fraction(Decimal(POSITION))
    assert to_fraction(item["netting_reclass_amount"]) == Fraction(1, 10**14)
    view = event_view("K-01", 3, "OPENING_BALANCE_ESTABLISHED", date(2023, 1, 31), unwrapped)
    parsed = opening.parse(view)
    assert parsed.findings == ()
    row = parsed.rows["POB-01"]
    assert row.values["revenue_cum"] == Fraction(Decimal(REVENUE))
    assert row.values["remaining_allocation"] == Fraction(Decimal(REMAINING))
    assert row.values["position_obligation"] == Fraction(Decimal(POSITION))
    # S07-R-03: X_i = revenue_cum + remaining_allocation, exact
    assert row.values["revenue_cum"] + row.values["remaining_allocation"] == Fraction(1300)


def test_negative_zero_and_currency_behaviour_is_preserved() -> None:
    body = _body(
        _row(
            revenue_cum=_usd("-0.000000000000001"),
            catch_up_cum=_usd("0"),
            billed_cum={"amount": "1300", "currency": "EUR"},
        )
    )
    (row,) = payloads.parse_payload(OPENING, 2, body).obligations
    assert row.revenue_cum.amount == "-0.000000000000001" and row.catch_up_cum.amount == "0"
    assert row.billed_cum.currency == "EUR"
    with pytest.raises(ValidationError):  # currency stays an ISO 4217 code
        payloads.parse_payload(
            OPENING, 2, _body(_row(billed_cum={"amount": "1", "currency": "usd"}))
        )
    with pytest.raises(ValidationError):  # a JSON number still fails API-C-06
        payloads.parse_payload(
            OPENING, 2, _body(_row(revenue_cum={"amount": 1.5, "currency": "USD"}))
        )
    with pytest.raises(ValidationError):  # the money object keeps its two members only
        payloads.parse_payload(
            OPENING, 2, _body(_row(revenue_cum={"amount": "1", "currency": "USD", "x": 1}))
        )


def test_stored_version_1_bodies_upcast_unchanged_bytes_and_hash() -> None:
    """A stored version-1 body (four-place amounts) parses through the identity upcast as the
    version-2 model; its stored form and hash are byte-identical; ``LATEST`` upcasts 1 → 2 and
    refuses versions 0 and 3."""
    # the stored form of a version-1 append: payload_json of the version-1 model (every member,
    # fair_value_contract_liability as null), as stream.append_events wrote it
    v1_body = payloads.payload_json(
        payloads.OpeningBalanceEstablishedV1.model_validate(
            _body(
                _row(
                    revenue_cum=_usd("322.1011"),
                    remaining_allocation=_usd("977.8989"),
                    position_obligation=_usd("-1300.0000"),
                    netting_reclass_amount=_usd("0.0000"),
                )
            )
        )
    )
    assert v1_body["fair_value_contract_liability"] is None
    digest = sha256_hex(v1_body)
    version, upcast_body = payloads.upcast(OPENING, 1, v1_body)
    assert (version, upcast_body) == (2, v1_body)
    parsed = payloads.parse_payload(OPENING, 1, v1_body)
    assert isinstance(parsed, payloads.OpeningBalanceEstablishedV2)
    assert payloads.payload_json(parsed) == v1_body  # bytes preserved: "322.1011" stays "322.1011"
    assert sha256_hex(payloads.payload_json(parsed)) == digest
    for version in (0, 3):
        with pytest.raises(ValueError):
            payloads.upcast(OPENING, version, v1_body)
    # version 1 is still registered and still admits four places only
    assert PAYLOADS[(OPENING, 1)] is payloads.OpeningBalanceEstablishedV1
    with pytest.raises(ValidationError):
        payloads.OpeningBalanceEstablishedV1.model_validate(_body())


def test_out_of_bound_and_exponent_amounts_are_refused_by_name_with_no_model() -> None:
    """Never rounded: 19 fractional digits, 21 integer digits and exponent notation each fail with
    rule API-C-06 on the member path, and no model (hence nothing to append) exists."""
    cases = {
        "19 fractional digits": "0.1234567890123456789",
        "21 integer digits": "123456789012345678901",
        "exponent": "1e-05",
        "exponent, capital": "1.5E+16",
    }
    for label, amount in cases.items():
        with pytest.raises(ValidationError) as raised:
            payloads.parse_payload(OPENING, 2, _body(_row(position_obligation=_usd(amount))))
        errors = raised.value.errors()
        named = [e for e in errors if e["type"] == "api_c_06"]
        (error,) = named
        assert error["ctx"]["rule_id"] == money.RULE_ID == "API-C-06", label
        assert error["loc"] == ("obligations", 0, "position_obligation", "amount"), label
        # pydantic's only other report is the derived tuple-length consequence of the refused
        # item (min_length=1 on ``obligations``, unchanged from version 1) — no rounding, no model.
        assert {(e["loc"], e["type"]) for e in errors} - {(error["loc"], "api_c_06")} <= {
            (("obligations",), "too_short")
        }, label
    # the bound itself is admitted: 18 fractional and 20 integer digits
    edge = payloads.parse_payload(
        OPENING,
        2,
        _body(
            _row(
                revenue_cum=_usd("0.123456789012345678"),
                remaining_allocation=_usd("12345678901234567890"),
            )
        ),
    )
    assert edge.obligations[0].revenue_cum.amount == "0.123456789012345678"


def test_exact_plain_decimal_normalises_exponents_exactly_or_refuses() -> None:
    """The producer's normalisation of shortest-repr exponent text (Codex): the exact plain decimal
    of the same numerical value, never rounded; a value whose exact form leaves the bound is
    refused by name; non-numeric or non-finite text is refused; plain text is returned unchanged."""
    assert money.exact_plain_decimal("1e-05") == "0.00001"
    assert money.exact_plain_decimal("1.5e+16") == "15000000000000000"
    assert money.exact_plain_decimal("-2.5E-3") == "-0.0025"
    assert money.exact_plain_decimal("322.10109018830525") == "322.10109018830525"
    assert money.exact_plain_decimal("1300") == "1300"
    assert Decimal(money.exact_plain_decimal("1e-05")) == Decimal("1e-05")
    for text in ("1e-19", "1e21", "NaN", "Infinity", "abc", "1,5", ""):
        with pytest.raises(ValueError, match="API-C-06"):
            money.exact_plain_decimal(text)
