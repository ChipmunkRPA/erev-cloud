"""PRD §2.12 fixture files built by deterministic generator functions (BUILD_SPEC BS3-D-18; PRD
WLD-R-01).

The seed and the tests both use these functions, so each fixture has one source and no committed
binary. ``standalone_sales_pool()`` produces WLD-F-18, the pool of standalone sales that the
historical SSP calculator reads (PRD §2.8 WLD-X-24, J-02.1; BUILD_SPEC RFD-15, BS3-D-15).
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Final

# PRD §2.12 WLD-F-18.
STANDALONE_SALES_POOL_FILENAME: Final = "avm-plat-100-standalone-sales-2026.csv"
# [J] The pool columns the calculator reads (L2-1-Q-55); every row carries its order line id.
POOL_COLUMNS: Final = (
    "order_line_external_id",
    "order_date",
    "entity_code",
    "customer_code",
    "product_code",
    "quantity",
    "unit_price",
    "currency",
)
POOL_SALES: Final = 40
POOL_LOWEST_PRICE: Final = Decimal("73000.00")
POOL_PRICE_STEP: Final = Decimal("2000.00")
POOL_DAYS: Final = (3, 9, 15, 21, 27)  # five sales a month, January to August 2026
# [J] US customers of PRD §2.7 (WLD-C-01 to 03, 08, 09, 12) buy in turn.
POOL_CUSTOMERS: Final = ("WLD-C-01", "WLD-C-02", "WLD-C-03", "WLD-C-08", "WLD-C-09", "WLD-C-12")
# 17 and 40 are coprime, so the prices are spread over the dates and each price appears once.
_PRICE_STRIDE: Final = 17


def standalone_sales_pool() -> bytes:
    """WLD-F-18 ``avm-plat-100-standalone-sales-2026.csv``: 40 standalone sales of AVM-PLAT-100
    for entity AVM-US in USD, quantity 1, dated 03 Jan 2026 to 27 Aug 2026, with the unit prices
    73,000.00 to 151,000.00 in steps of 2,000.00 each once. The bytes are the same on every call
    (UTF-8, LF line ends)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(POOL_COLUMNS)
    for index in range(POOL_SALES):
        month, slot = divmod(index, len(POOL_DAYS))
        price = POOL_LOWEST_PRICE + POOL_PRICE_STEP * ((index * _PRICE_STRIDE) % POOL_SALES)
        writer.writerow(
            (
                f"SO-AVM-2026-{index + 1:04d}",
                date(2026, month + 1, POOL_DAYS[slot]).isoformat(),
                "AVM-US",
                POOL_CUSTOMERS[index % len(POOL_CUSTOMERS)],
                "AVM-PLAT-100",
                "1",
                format(price, "f"),
                "USD",
            )
        )
    return buffer.getvalue().encode("utf-8")
