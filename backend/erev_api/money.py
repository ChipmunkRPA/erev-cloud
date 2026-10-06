"""API money and decimal types (dev-guide §5.9 KRN-MONEY; 04 API-C-06, §16.0 API-S-Money).

Money travels as ``{"amount": "<string>", "currency": "<ISO 4217>"}``. A JSON number in a money or
decimal field fails validation with ``errors[].rule_id = "API-C-06"`` (REQ-PLT-031): the
validators raise ``PydanticCustomError`` with the rule id in ``ctx``, which the
``RequestValidationError`` handler of ``erev_api.problems`` copies into ``errors[].rule_id``. Minor
units come only from the currency table (DG-KRN-MONEY-04).
"""

from __future__ import annotations

import re
from decimal import Context, Decimal, FloatOperation, InvalidOperation, localcontext
from typing import Annotated, Final

from erev_engine.currencies import CurrencySpec, CurrencyTable
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints
from pydantic_core import PydanticCustomError

from erev_api.problems import Problem, ProblemError

RULE_ID: Final = "API-C-06"
# PRD §5.5 ERR-35 errors[].message.
MONEY_MESSAGE: Final = 'Send money amounts as decimal strings, for example "1250.00".'
DECIMAL_MESSAGE: Final = 'Send decimal values as strings without an exponent, for example "0.25".'
RATE_MESSAGE: Final = 'Send rates as positive decimal strings, for example "1.083450".'

# ASCII digits only: ``\d`` also matches other Unicode digits, which ``Decimal`` accepts (D-78).
_MONEY: Final = re.compile(r"^-?[0-9]{1,20}(\.[0-9]{1,4})?$")
_DECIMAL: Final = re.compile(r"^-?[0-9]{1,20}(\.[0-9]{1,18})?$")
_RATE: Final = re.compile(r"^[0-9]{1,16}(\.[0-9]{1,12})?$")
# Wide enough for NUMERIC(38,18) values; inexact results are detected by comparison, not trapped.
_CONTEXT: Final = Context(prec=38, traps=[InvalidOperation])


def _rule_error(message: str) -> PydanticCustomError:
    return PydanticCustomError("api_c_06", message, {"rule_id": RULE_ID})


def _reject_number(message: str) -> BeforeValidator:
    def check(value: object) -> object:
        if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
            raise _rule_error(message)
        return value

    return BeforeValidator(check)


def validate_money_string(value: str) -> str:
    if not _MONEY.fullmatch(value):
        raise _rule_error(MONEY_MESSAGE)
    return value


def validate_decimal_string(value: str) -> str:
    if not _DECIMAL.fullmatch(value):
        raise _rule_error(DECIMAL_MESSAGE)
    return value


def validate_rate_string(value: str) -> str:
    if not _RATE.fullmatch(value) or Decimal(value) <= 0:
        raise _rule_error(RATE_MESSAGE)
    return value


MoneyStr = Annotated[str, _reject_number(MONEY_MESSAGE), AfterValidator(validate_money_string)]
DecimalStr = Annotated[
    str, _reject_number(DECIMAL_MESSAGE), AfterValidator(validate_decimal_string)
]
RateStr = Annotated[str, _reject_number(RATE_MESSAGE), AfterValidator(validate_rate_string)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class MoneyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    amount: MoneyStr
    currency: CurrencyCode


class ExactMoneyIn(BaseModel):
    """API-S-ExactMoney (04 §16.0 rev 1.61; D-98 candidate 127): the ``{amount, currency}`` shape of
    API-S-Money with ``amount`` a plain signed decimal string of at most 20 integer and 18
    fractional digits (``DecimalStr``, the API-C-06 bound), carried exactly and never quantized to
    the minor unit. Admitted only where a governing rule requires the exact legacy value — the
    eight money members of an ``OPENING_BALANCE_ESTABLISHED`` obligation (ENGINE_SPEC S07-R-03,
    S07-R-11). An out-of-bound or exponent-notation amount fails validation with rule API-C-06 on
    the member path; nothing rounds it."""

    model_config = ConfigDict(extra="forbid", strict=True)

    amount: DecimalStr
    currency: CurrencyCode


def exact_plain_decimal(text: str) -> str:
    """The exact plain-decimal form of a numeric text for an ExactMoney amount (04 §16.0 rev 1.61):
    a plain decimal within the API-C-06 bound is returned unchanged; exponent notation (the
    shortest ``repr`` of a legacy REAL may read ``1e-05`` or ``1.5e+16``) is rewritten to the plain
    string of the same numerical value, exactly; a text that is not a finite decimal, or whose exact
    plain form leaves the 20-integer / 18-fractional-digit bound, raises ``ValueError`` naming
    API-C-06 — never rounded. The producer keeps the original text as its evidence (T-MIG-02)."""
    if _DECIMAL.fullmatch(text):
        return text
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"{RULE_ID}: {text!r} is not a decimal. {DECIMAL_MESSAGE}") from error
    if not value.is_finite():
        raise ValueError(f"{RULE_ID}: {text!r} is not a finite decimal. {DECIMAL_MESSAGE}")
    plain = format(value, "f")
    if not _DECIMAL.fullmatch(plain):
        raise ValueError(
            f"{RULE_ID}: the exact plain form of {text!r} is {plain!r}, outside the ExactMoney "
            "bound of 20 integer and 18 fractional digits; it is refused, not rounded."
        )
    return plain


class MoneyOut(BaseModel):
    """API-S-Money: ``amount`` carries exactly the currency's minor-unit decimals."""

    amount: str
    currency: str


def _invalid(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[ProblemError(field=field, rule_id=RULE_ID, message=message)],
    )


def _spec(currency: str, currencies: CurrencyTable) -> CurrencySpec:
    spec = currencies.get(currency)
    if spec is None:
        raise ValueError(f"{currency} is not in the currency table")
    return spec


def money_in_to_minor(value: MoneyIn, currencies: CurrencyTable) -> int:
    """The amount in integer minor units; more decimals than the minor unit fail with API-C-06."""
    spec = currencies.get(value.currency)
    if spec is None:
        raise _invalid("currency", f"{value.currency} is not an ISO 4217 currency code.")
    amount = Decimal(value.amount)
    exponent = amount.as_tuple().exponent
    assert isinstance(exponent, int)  # the MoneyStr pattern admits finite values only
    if -exponent > spec.minor_unit:
        raise _invalid(
            "amount",
            f"{spec.code} amounts have at most {spec.minor_unit} decimal places. {MONEY_MESSAGE}",
        )
    return int(amount.scaleb(spec.minor_unit, _CONTEXT))


def money_out(
    amount: Decimal | int, currency: str, currencies: CurrencyTable, *, minor: bool = False
) -> MoneyOut:
    """Serialise an amount with exactly the minor-unit decimals (DG-KRN-MONEY-06).

    ``minor=True`` reads ``amount`` as integer minor units. An amount that is not exact at the
    minor unit raises ``ValueError``; negative zero is written without its sign.
    """
    spec = _spec(currency, currencies)
    if isinstance(amount, bool) or not isinstance(amount, Decimal | int):
        raise TypeError(f"money_out takes Decimal or int, not {type(amount).__name__}")
    if minor and not isinstance(amount, int):
        raise TypeError("money_out(minor=True) takes integer minor units")
    value = Decimal(amount).scaleb(-spec.minor_unit, _CONTEXT) if minor else Decimal(amount)
    if not value.is_finite():
        raise ValueError("money_out rejects non-finite amounts")
    quantized = value.quantize(Decimal(1).scaleb(-spec.minor_unit), context=_CONTEXT)
    if quantized != value:
        raise ValueError(f"amount is not exact at the {spec.code} minor unit ({spec.minor_unit})")
    if quantized.is_zero():
        quantized = quantized.copy_abs()
    return MoneyOut(amount=f"{quantized:f}", currency=spec.code)


def decimal_from_cell(value: object) -> Decimal:
    """The only float-to-number conversion (DG-KRN-MONEY-07; REQ-DAT-007).

    A float becomes ``Decimal(repr(value))`` inside a local context with ``FloatOperation``
    untrapped; the caller's context, and its traps, are restored afterwards. ``int``, ``Decimal``
    and numeric strings convert exactly. Booleans, other types, unparsable strings and non-finite
    values raise ``ValueError``.
    """
    if isinstance(value, bool):
        raise ValueError("a boolean cell is not a number")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        with localcontext() as ctx:
            ctx.traps[FloatOperation] = False
            result = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation:
            raise ValueError("the cell is not a number") from None
    else:
        raise ValueError(f"a {type(value).__name__} cell is not a number")
    if not result.is_finite():
        raise ValueError("the cell is not a finite number")
    return result
