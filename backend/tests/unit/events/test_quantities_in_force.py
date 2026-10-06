"""The quantity a delivery is checked against, folded from the live stream (04 §16.3 "The quantity
a delivery is checked against", rev 1.232; dev-guide DG-KRN-EVT-02 rev 1.223; item
EVT-BOUND-AFTER-MOD-1; control CTL-008).

Pure. ``events.quantities_in_force`` takes the live events of one contract in stream order — the
rows as ``repo.stream`` gives them, without the events a void names — and answers the quantity in
force and the product of every obligation, and the keys that take no further delivery. The
database witnesses, through the route and the approval, are in
``tests/domain/contracts/test_bound_in_force.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from erev_api.domain.contracts.events import quantities_in_force


def _booked(*lines: tuple[str, str, str]) -> dict[str, Any]:
    return {
        "event_type": "CONTRACT_BOOKED",
        "payload": {
            "lines": [
                {"obligation_key": key, "product_code": product, "quantity": quantity}
                for key, product, quantity in lines
            ]
        },
    }


def _amended(*lines: dict[str, Any]) -> dict[str, Any]:
    return {"event_type": "CONTRACT_AMENDED", "payload": {"lines": list(lines)}}


def _line(key: str, action: str, delta: str | None = None, product: str | None = None) -> Any:
    line: dict[str, Any] = {"obligation_key": key, "action": action, "product_code": product}
    if delta is not None:
        line["quantity_delta"] = delta
    return line


def _moved(direction: str, key: str, quantity: str | None = None) -> dict[str, Any]:
    lines = (
        []
        if quantity is None
        else [{"obligation_key": key, "product_code": "AVM-SEAT-MO", "quantity": quantity}]
    )
    return {
        "event_type": "REGROUPED",
        "payload": {"direction": direction, "obligation_keys": [key], "lines": lines},
    }


K11 = _booked(("O1", "AVM-GW", "200"), ("O2", "AVM-SUP-12", "1"))


def test_the_booking_alone_gives_its_quantities() -> None:
    terms = quantities_in_force([K11, {"event_type": "DELIVERY_RECORDED", "payload": {}}])

    assert terms.quantities == {"O1": Decimal(200), "O2": Decimal(1)}
    assert terms.products == {"O1": "AVM-GW", "O2": "AVM-SUP-12"}
    assert terms.ended == frozenset()
    # a stream without a booking states nothing, and nothing is bound
    assert quantities_in_force([]).quantities == {}


def test_a_change_line_adds_its_delta_and_an_add_line_starts_from_zero() -> None:
    terms = quantities_in_force(
        [
            K11,
            _amended(_line("O1", "CHANGE", "50")),
            _amended(_line("O1", "CHANGE", "-60"), _line("O3", "ADD", "10", "AVM-GW")),
            _amended(_line("O2", "CHANGE")),  # a price change states no quantity_delta
        ]
    )

    assert terms.quantities == {"O1": Decimal(190), "O2": Decimal(1), "O3": Decimal(10)}
    assert terms.products["O3"] == "AVM-GW"
    assert terms.ended == frozenset()


def test_a_remove_line_ends_the_obligation_whatever_its_delta() -> None:
    for delta in ("-80", "0", None):
        terms = quantities_in_force([K11, _amended(_line("O1", "REMOVE", delta))])
        assert terms.ended == frozenset({"O1"}), delta
        assert terms.products["O1"] == "AVM-GW"  # the refusal still names the product
    # an ADD line of the same key puts it in force again, from zero
    again = quantities_in_force(
        [K11, _amended(_line("O1", "REMOVE", "-80")), _amended(_line("O1", "ADD", "30", "AVM-GW"))]
    )
    assert (again.quantities["O1"], again.ended) == (Decimal(30), frozenset())


def test_a_quantity_taken_to_zero_ends_the_obligation_until_a_change_restores_it() -> None:
    gone = quantities_in_force([K11, _amended(_line("O1", "CHANGE", "-200"))])
    assert (gone.quantities["O1"], gone.ended) == (Decimal(0), frozenset({"O1"}))
    below = quantities_in_force([K11, _amended(_line("O1", "CHANGE", "-250"))])
    assert below.ended == frozenset({"O1"})
    back = quantities_in_force(
        [K11, _amended(_line("O1", "CHANGE", "-200")), _amended(_line("O1", "CHANGE", "40"))]
    )
    assert (back.quantities["O1"], back.ended) == (Decimal(40), frozenset())
    # a line that never stated a unit quantity is not bound and not ended (the bound asks 0 < q)
    unstated = quantities_in_force([K11, _amended(_line("O4", "ADD", None, "AVM-SUP-12"))])
    assert (unstated.quantities["O4"], unstated.ended) == (Decimal(0), frozenset())


def test_a_regroup_moves_the_quantity_wherever_it_stands_in_the_stream() -> None:
    source = quantities_in_force(
        [_booked(("O1", "AVM-SEAT-MO", "1440"), ("O2", "AVM-SEAT-MO", "960")), _moved("OUT", "O2")]
    )
    assert source.quantities == {"O1": Decimal(1440)}
    assert source.ended == frozenset({"O2"})
    assert source.products["O2"] == "AVM-SEAT-MO"

    target = quantities_in_force(
        [_booked(("O1", "AVM-SEAT-MO", "1440")), _moved("IN", "O2", "960")]
    )
    assert target.quantities == {"O1": Decimal(1440), "O2": Decimal(960)}
    assert target.ended == frozenset()

    # a draft replaced after the move: bundle assembly moves the lines of the booking that stands
    replaced = quantities_in_force(
        [
            _booked(("O1", "AVM-SEAT-MO", "1440"), ("O2", "AVM-SEAT-MO", "960")),
            _moved("OUT", "O2"),
            _booked(("O1", "AVM-SEAT-MO", "1200"), ("O2", "AVM-SEAT-MO", "960")),
        ]
    )
    assert replaced.quantities == {"O1": Decimal(1200)}
    assert replaced.ended == frozenset({"O2"})

    # a new contract booked with the moved line keeps its booking's quantity
    booked_with_it = quantities_in_force(
        [_booked(("O2", "AVM-SEAT-MO", "960")), _moved("IN", "O2", "960")]
    )
    assert booked_with_it.quantities == {"O2": Decimal(960)}

    # moved out and regrouped back: in force again
    back = quantities_in_force(
        [
            _booked(("O1", "AVM-SEAT-MO", "1440"), ("O2", "AVM-SEAT-MO", "960")),
            _moved("OUT", "O2"),
            _moved("IN", "O2", "960"),
        ]
    )
    assert (back.quantities["O2"], back.ended) == (Decimal(960), frozenset())

    # an IN event without lines states no quantity: the key is not bound, and not ended
    unstated = quantities_in_force([_booked(("O1", "AVM-SEAT-MO", "1440")), _moved("IN", "O2")])
    assert ("O2" in unstated.quantities, unstated.ended) == (False, frozenset())


def test_only_the_amendments_after_the_last_booking_change_it() -> None:
    terms = quantities_in_force(
        [
            _booked(("O1", "AVM-GW", "100")),
            _amended(_line("O1", "CHANGE", "50")),
            K11,
            _amended(_line("O1", "CHANGE", "5")),
        ]
    )

    assert terms.quantities == {"O1": Decimal(205), "O2": Decimal(1)}


def test_the_types_no_command_records_change_nothing() -> None:
    terms = quantities_in_force(
        [
            K11,
            {
                "event_type": "CONTRACT_TERMINATED",
                "payload": {"termination_kind": "PARTIAL", "obligation_keys": ["O1"]},
            },
            {
                "event_type": "MATERIAL_RIGHT_EXERCISED",
                "payload": {
                    "obligation_key": "O2",
                    "new_lines": [
                        {"obligation_key": "O9", "product_code": "AVM-GW", "quantity": "5"}
                    ],
                },
            },
            # a change that names a key the stream never stated is not a quantity either
            _amended(_line("O7", "CHANGE", "10")),
        ]
    )

    assert terms.quantities == {"O1": Decimal(200), "O2": Decimal(1)}
    assert terms.ended == frozenset()
