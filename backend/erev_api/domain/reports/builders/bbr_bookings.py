"""Activated contract booking values for RPT-37, with original event provenance.

Booked contract value is the signed stated line consideration, not an allocated group transaction
price. Read each contract's standing booking at its first activation. Separate-contract
modifications are excluded here: their linked booking must be counted once by the modification
adapter. This module does not value amendments or invent a missing pre-activation valuation.
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID

from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.problems import Problem


def new_contracts(source: Mapping[str, Any]) -> tuple[Contribution, ...]:
    events = source["events"]
    voided = {
        r["supersedes_event_id"]
        for r in events
        if r["event_type"] == "EVENT_VOIDED" and r["supersedes_event_id"] is not None
    }
    void_contracts = {r["contract_id"] for r in events if r["event_type"] == "CONTRACT_VOIDED"}
    modification_bookings = set(source["modification_booking_ids"])
    streams: dict[str, list[Mapping[str, Any]]] = {}
    for row in events:
        if row["id"] not in voided and row["contract_id"] not in void_contracts:
            streams.setdefault(row["contract_id"], []).append(row)
    result = []
    for cid, stream in streams.items():
        activations = [r for r in stream if r["event_type"] == "CONTRACT_ACTIVATED"]
        if not activations:
            continue  # A draft contributes no activated booking.
        activation = min(activations, key=lambda r: (r["effective_date"], r["record_seq"], r["id"]))
        bookings = [
            r
            for r in stream
            if r["event_type"] == "CONTRACT_BOOKED" and r["record_seq"] < activation["record_seq"]
        ]
        if not bookings:
            raise Problem("invalid-transition", f"Activated contract {cid} has no booking source.")
        booking = max(bookings, key=lambda r: r["record_seq"])
        if booking["id"] in modification_bookings:
            continue
        if booking["contracting_entity_id"] != activation["contracting_entity_id"]:
            raise Problem("invalid-transition", "Activation and booking entity scopes differ.")
        if any(
            r["event_type"] in {"CONTRACT_AMENDED", "CONTRACT_TERMINATED", "REGROUPED"}
            and booking["record_seq"] < r["record_seq"] < activation["record_seq"]
            for r in stream
        ):
            raise Problem(
                "invalid-transition",
                "Pre-activation changes require an attributed booking valuation.",
            )
        payload = booking["payload"]
        currency = payload["transaction_currency"]
        amount = Decimal(0)
        lines = payload["lines"]
        if not lines:
            raise Problem("invalid-transition", "Booking source has no stated lines.")
        with localcontext() as context:
            context.prec = 80
            for line in lines:
                price = line.get("total_price")
                if not isinstance(price, Mapping) or price.get("currency") != currency:
                    raise Problem(
                        "invalid-transition",
                        "Booking line lacks consideration in the contract currency.",
                    )
                value = Decimal(str(price["amount"]))
                if not value.is_finite():
                    raise Problem("invalid-transition", "Booking consideration must be finite.")
                amount += value
        result.append(
            Contribution(
                "contract_event",
                UUID(activation["id"]),
                UUID(cid),
                UUID(activation["contracting_entity_id"]),
                date.fromisoformat(activation["effective_date"]),
                currency,
                amount,
                basis_ids=(UUID(booking["id"]), UUID(activation["id"])),
            )
        )
    return tuple(sorted(result, key=lambda r: (r.effective_date, str(r.source_id))))
