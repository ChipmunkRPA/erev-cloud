"""The lines of a regroup's pair are written as plain decimal text (04 API-C-06; the supervisor's
measurement order and ruling of 2026-10-02; BUILD_SPEC CTR-17).

``contracts/regroup.py`` wrote the two deltas of a moved line as ``str(Decimal * sign)``. Python
writes a value below 1e-6 with an exponent and a zero times -1 with a sign, so — measured through
``POST /contracts/{id}/regroup`` between two drafts — a moved line of quantity 0.0000005 stored
``quantity_delta`` "-5E-7" and "5E-7", which API-C-06 refuses on the way in and the line's own
payload model does not validate, and a moved line priced 0.00 stored the consideration "-0.00".
Every other writer of these two members writes ``format(value, "f")``.

Pure: the lines are built from the booking line alone before any line has posted, the one case
release 1.0 takes.
"""

from __future__ import annotations

from typing import Any

import pytest
from erev_api.domain.contracts import regroup
from erev_api.events.payloads import ModificationLineV1


def _pair(quantity: str, price: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The REMOVE line of the source and the ADD line of the target for one moved line."""
    booking = {
        "O2": {
            "obligation_key": "O2",
            "product_code": "AVM-SEAT-MO",
            "quantity": quantity,
            "total_price": {"amount": price, "currency": "USD"},
            "start_date": "2026-01-01",
            "end_date": "2027-12-31",
        }
    }
    (removed,), (added,) = (
        regroup._move_lines(
            booking,
            ["O2"],
            {},
            sign=sign,
            action=action,
            currency="USD",
            external_id="SF-ORD-10002",
            posted=False,
        )
        for sign, action in ((-1, "REMOVE"), (1, "ADD"))
    )
    return removed, added


@pytest.mark.parametrize(
    ("quantity", "price", "removed", "added"),
    [
        # a zero keeps its scale and takes no sign
        ("960", "0.00", ("-960", "0.00"), ("960", "0.00")),
        ("960", "0.0000", ("-960", "0.0000"), ("960", "0.0000")),
        # a quantity below 1e-6 is written without an exponent
        ("0.0000005", "96000.00", ("-0.0000005", "-96000.00"), ("0.0000005", "96000.00")),
        # the widest decimal text is kept as written
        (
            "960.000000000000000000",
            "96000.00",
            ("-960.000000000000000000", "-96000.00"),
            ("960.000000000000000000", "96000.00"),
        ),
        # the ordinary case is unchanged
        ("960", "96000.00", ("-960", "-96000.00"), ("960", "96000.00")),
    ],
)
def test_a_regroups_lines_carry_plain_decimal_text(
    quantity: str, price: str, removed: tuple[str, str], added: tuple[str, str]
) -> None:
    lines = _pair(quantity, price)
    assert [(line["quantity_delta"], line["consideration_delta"]["amount"]) for line in lines] == [
        removed,
        added,
    ]
    for line in lines:
        # the text is what the line's own payload model takes (API-C-06: no exponent)
        parsed = ModificationLineV1.model_validate(line)
        assert parsed.quantity_delta == line["quantity_delta"]
