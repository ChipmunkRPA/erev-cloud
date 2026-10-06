"""Float-rejecting column types and the cell conversion (dev-guide DG-KRN-MONEY-05, -07; FND-9)."""

from __future__ import annotations

import warnings
from decimal import Decimal, FloatOperation, getcontext, localcontext

import pytest
from erev_api.db.types import ExactType, FxRateType, MoneyType
from erev_api.money import decimal_from_cell
from sqlalchemy import Column, MetaData, Table, select
from sqlalchemy.dialects.postgresql import psycopg as postgresql_psycopg
from sqlalchemy.exc import SAWarning
from sqlalchemy.sql.cache_key import NO_CACHE

DIALECT = postgresql_psycopg.dialect()


def test_krn_money_05_types_reject_float() -> None:
    for column_type in (MoneyType(), ExactType(), FxRateType()):
        # The execution path: SQLAlchemy binds through the dialect implementation of the type.
        bind = column_type.dialect_impl(DIALECT).bind_processor(DIALECT)
        assert bind is not None, type(column_type).__name__
        with pytest.raises(TypeError):
            bind(12.3)
        with pytest.raises(TypeError):
            bind(True)
        assert bind(Decimal("12.30")) == Decimal("12.30")
        assert bind(None) is None
        with pytest.raises(ValueError):
            bind(Decimal("NaN"))
    assert (MoneyType().impl_instance.precision, MoneyType().impl_instance.scale) == (24, 4)
    assert (ExactType().impl_instance.precision, ExactType().impl_instance.scale) == (38, 18)
    assert (FxRateType().impl_instance.precision, FxRateType().impl_instance.scale) == (28, 12)


def test_krn_money_05_types_cacheable() -> None:
    # S-4: a TypeDecorator without its own cache_ok disables statement caching with a SAWarning.
    for column_type in (MoneyType(), ExactType(), FxRateType()):
        assert column_type._static_cache_key is not NO_CACHE, type(column_type).__name__
    probe = Table(
        "cache_probe",
        MetaData(),
        Column("amount", MoneyType()),
        Column("ratio", ExactType()),
        Column("rate", FxRateType()),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        statement = select(probe).where(probe.c.amount > 0)
        assert statement._generate_cache_key() is not None
        statement.compile(dialect=DIALECT)


def test_krn_money_07_decimal_from_cell() -> None:
    with localcontext() as ctx:
        ctx.traps[FloatOperation] = True
        assert decimal_from_cell(0.1) == Decimal("0.1")
        assert getcontext().traps[FloatOperation]
        with pytest.raises(FloatOperation):
            Decimal(0.1)
    with pytest.raises(ValueError):
        decimal_from_cell("x")
    assert decimal_from_cell(" 12.50 ") == Decimal("12.50")
    assert decimal_from_cell(7) == Decimal(7)
    for rejected in (True, float("inf"), None, "NaN"):
        with pytest.raises(ValueError):
            decimal_from_cell(rejected)
