"""Canonical serialisation and hashing (dev-guide §5.17; BUILD_SPEC FND-3, EKC-3).

Moved from `backend/tests/engine/test_canonical.py` (FND-3) because test basenames are unique.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

import pydantic
import pytest
from erev_engine.canonical import canonical_bytes, sha256_hex


class _Book(enum.StrEnum):
    ASC606 = "ASC606"


@dataclass(frozen=True)
class _Line:
    pob_key: str
    amount: Decimal


def test_encoding_table() -> None:
    plus_two = timezone(timedelta(hours=2))
    cases: list[tuple[Any, bytes]] = [
        ({"b": 1, "a": "é"}, '{"a":"é","b":1}'.encode()),  # CAN-01
        ("é", '"é"'.encode()),  # CAN-02
        (True, b"true"),  # CAN-03
        (42, b"42"),  # CAN-03
        (Decimal("1.2300"), b'"1.2300"'),  # CAN-04
        (Fraction(1, 4), b'"0.25"'),  # CAN-05
        (date(2026, 9, 12), b'"2026-09-12"'),  # CAN-07
        (datetime(2026, 9, 12, 12, 0, 0, tzinfo=plus_two), b'"2026-09-12T10:00:00.000000Z"'),
        (UUID("0191E0A0-0000-7000-8000-00000000000A"), b'"0191e0a0-0000-7000-8000-00000000000a"'),
        (_Book.ASC606, b'"ASC606"'),  # CAN-10
        ((2, "a", [1]), b'[2,"a",[1]]'),  # CAN-11
        (frozenset({"b", "a"}), b'["a","b"]'),  # CAN-12
        (_Line("P1", Decimal("10.00")), b'{"amount":"10.00","pob_key":"P1"}'),  # CAN-13
        (None, b"null"),  # CAN-14
    ]
    for value, expected in cases:
        assert canonical_bytes(value) == expected
    with pytest.raises(TypeError):
        canonical_bytes(1.5)  # CAN-06
    with pytest.raises(ValueError):
        canonical_bytes(datetime(2026, 9, 12, 12, 0, 0))  # CAN-08
    with pytest.raises(TypeError):
        canonical_bytes(object())  # CAN-15
    with pytest.raises(ValueError):
        canonical_bytes(Decimal("NaN"))  # CAN-04


def test_sha256_hex_matches_ex_14_a_vector() -> None:
    line_key = {
        "account_role": "CONTRACT_LIABILITY",
        "book_code": "ASC606",
        "clearing_purpose": None,
        "counterparty_entity": None,
        "entity": "US01",
        "entry_kind": "REVENUE_RECOGNITION",
        "origin_period_key": "FY2026-P02",
        "posting_class": "EVENT",
        "posting_period_key": "FY2026-P03",
        "subject_key": "TKT-001/POB-01",
    }
    assert sha256_hex(line_key) == (
        "83300736c63604193d4d84963e7a4730332dce8962cf245e22f2b15cb5e99b0a"
    )


def test_krn_can_01_sorted_keys_no_whitespace() -> None:
    assert canonical_bytes({"b": 1, "a": "é"}) == b'{"a":"\xc3\xa9","b":1}'
    # Unicode code point order, nested mappings and arrays without whitespace.
    assert canonical_bytes({"é": [1, 2], "Z": {"y": None, "x": "q"}, "a": []}) == (
        '{"Z":{"x":"q","y":null},"a":[],"é":[1,2]}'.encode()
    )
    with pytest.raises(TypeError):
        canonical_bytes({1: "one"})


def test_krn_can_02_strings_are_not_normalised() -> None:
    composed = "\u00e9"
    decomposed = "e\u0301"
    assert len(composed) == 1
    assert len(decomposed) == 2
    assert canonical_bytes(composed) != canonical_bytes(decomposed)
    assert canonical_bytes('quote " and \\ backslash') == b'"quote \\" and \\\\ backslash"'


def test_krn_can_03_bool_is_not_int() -> None:
    assert canonical_bytes({"t": True}) == b'{"t":true}'
    assert canonical_bytes([False, 0, 1]) == b"[false,0,1]"


def test_krn_can_04_decimal_keeps_scale() -> None:
    assert canonical_bytes(Decimal("1.50")) == b'"1.50"'
    assert canonical_bytes(Decimal("1E+3")) == b'"1000"'
    assert canonical_bytes(Decimal("-0.0001")) == b'"-0.0001"'
    for value in ("NaN", "sNaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError):
            canonical_bytes(Decimal(value))


def test_krn_can_05_fraction_exact() -> None:
    assert canonical_bytes(Fraction(1, 3)) == b'"0.333333333333333333"'
    assert canonical_bytes(Fraction(2, 3)) == b'"0.666666666666666667"'
    assert canonical_bytes(Fraction(1, 2)) == b'"0.5"'
    assert canonical_bytes(Fraction(-1, 8)) == b'"-0.125"'
    assert canonical_bytes(Fraction(5, 1)) == b'"5"'
    # ROUND_HALF_UP ties away from zero at 18 places; a value that rounds to zero has no sign.
    assert canonical_bytes(Fraction(-2, 3)) == b'"-0.666666666666666667"'
    assert canonical_bytes(Fraction(5, 10**19)) == b'"0.000000000000000001"'
    assert canonical_bytes(Fraction(-1, 10**19)) == b'"0"'


def test_krn_can_06_float_raises() -> None:
    with pytest.raises(TypeError):
        canonical_bytes(1.5)
    with pytest.raises(TypeError):
        canonical_bytes({"amount": 0.1})


def test_krn_can_07_date() -> None:
    assert canonical_bytes(date(2026, 9, 12)) == b'"2026-09-12"'


def test_krn_can_08_datetimes() -> None:
    with pytest.raises(ValueError):
        canonical_bytes(datetime(2026, 9, 12, 14, 0, 0))
    plus_two = timezone(timedelta(hours=2))
    assert canonical_bytes(datetime(2026, 9, 12, 14, 0, 0, tzinfo=plus_two)) == (
        b'"2026-09-12T12:00:00.000000Z"'
    )
    assert canonical_bytes(date(2026, 9, 12)) == b'"2026-09-12"'
    assert canonical_bytes(datetime(2026, 9, 12, 23, 59, 59, 7, tzinfo=UTC)) == (
        b'"2026-09-12T23:59:59.000007Z"'
    )


def test_krn_can_09_uuid_lowercase() -> None:
    value = UUID("0191E0A0-0000-7000-8000-00000000000A")
    assert canonical_bytes(value) == b'"0191e0a0-0000-7000-8000-00000000000a"'


def test_krn_can_10_enum_value() -> None:
    class Book(enum.StrEnum):
        ASC606 = "ASC606"

    class Level(enum.IntEnum):
        TWO = 2

    assert canonical_bytes([Book.ASC606, Level.TWO]) == b'["ASC606",2]'


def test_krn_can_11_list_and_tuple_in_order() -> None:
    assert canonical_bytes(("b", "a", [3, 1])) == b'["b","a",[3,1]]'


def test_krn_can_12_sets_sorted_by_canonical_bytes() -> None:
    assert canonical_bytes({"b", "a"}) == b'["a","b"]'
    assert canonical_bytes(frozenset({10, 9})) == b"[10,9]"


def test_krn_can_13_dataclass_as_mapping() -> None:
    @dataclass(frozen=True)
    class Line:
        pob_key: str
        amount: Decimal

    assert canonical_bytes(Line("P1", Decimal("10.00"))) == b'{"amount":"10.00","pob_key":"P1"}'
    assert canonical_bytes(Line("P1", Decimal("10.00"))) == canonical_bytes(
        {"pob_key": "P1", "amount": Decimal("10.00")}
    )


def test_krn_can_14_none_is_null() -> None:
    assert canonical_bytes(None) == b"null"


def test_krn_can_15_other_objects_raise() -> None:
    class Model(pydantic.BaseModel):
        name: str

    with pytest.raises(TypeError):
        canonical_bytes(Model(name="x"))
    with pytest.raises(TypeError):
        canonical_bytes(b"bytes")
    with pytest.raises(TypeError):
        canonical_bytes(Fraction)  # a class, not an instance


def test_sha256_hex_of_empty_mapping() -> None:
    assert sha256_hex({}) == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
