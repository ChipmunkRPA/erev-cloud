"""Exact numeric column types that reject floats (dev-guide §5.9 DG-KRN-MONEY-05; 04 §1.2).

``MoneyType``, ``ExactType`` and ``FxRateType`` bind the TY-01 ``erev.money`` NUMERIC(24,4), TY-02
``erev.exact`` NUMERIC(38,18) and TY-03 ``erev.fx_rate_value`` NUMERIC(28,12) domains. Binding a
``float`` (or a ``bool``) raises ``TypeError``; ``Decimal`` and ``int`` values bind unchanged, and
non-finite decimals raise ``ValueError``. Results are returned as ``Decimal``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Dialect
from sqlalchemy.types import Numeric, TypeDecorator


class _ExactNumeric(TypeDecorator[Decimal]):
    impl = Numeric
    cache_ok = True
    domain = "numeric"
    precision = 38
    scale = 18

    def __init__(self) -> None:
        super().__init__(precision=self.precision, scale=self.scale, asdecimal=True)

    def process_bind_param(self, value: object, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, Decimal | int):
            raise TypeError(
                f"{type(self).__name__} ({self.domain}) binds Decimal or int, not "
                f"{type(value).__name__}"
            )
        exact = Decimal(value)
        if not exact.is_finite():
            raise ValueError(f"{type(self).__name__} ({self.domain}) rejects non-finite values")
        return exact

    def process_result_value(self, value: Any | None, dialect: Dialect) -> Decimal | None:
        return value if value is None or isinstance(value, Decimal) else Decimal(value)


class MoneyType(_ExactNumeric):
    """TY-01 ``erev.money``: posted and quantized amounts."""

    # SQLAlchemy reads cache_ok from each class's own namespace, so every subclass declares it.
    cache_ok = True
    domain = "erev.money"
    precision = 24
    scale = 4


class ExactType(_ExactNumeric):
    """TY-02 ``erev.exact``: full-precision rates, ratios and quantities."""

    cache_ok = True
    domain = "erev.exact"
    precision = 38
    scale = 18


class FxRateType(_ExactNumeric):
    """TY-03 ``erev.fx_rate_value``: FX rates (04 rev 1.69; revision 0030 renamed the domain because
    ``erev.fx_rate`` is the T-REF-12 table's row type)."""

    cache_ok = True
    domain = "erev.fx_rate_value"
    precision = 28
    scale = 12
