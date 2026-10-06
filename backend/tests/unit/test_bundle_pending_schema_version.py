"""D-98 candidate 127 — Codex production-20260921-0533 F2
(``PRODUCTION-B4-EXACT-OPENING-7916266a.md``): the bundle's pending branch stamps
``EventInput.schema_version`` from the registry's latest version of the event type (the version
``stream`` appends at, stream.py ``LATEST_SCHEMA_VERSION``), while a stored row keeps its stored
version. First version-2 witness: a pending ``OPENING_BALANCE_ESTABLISHED`` is version 2; a pending
``CONTRACT_ACTIVATED`` is version 1; a stored version-1 opening row stays 1.

CPU only: ``bundles._events`` over in-memory rows, no database. Fail-first on 7916266a: the pending
branch hard-coded ``schema_version=1`` (bundles.py 430).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from erev_api.domain.contracts import bundles
from erev_api.enums import ContractEventType
from erev_api.events import payloads
from erev_api.events.payloads import LATEST_SCHEMA_VERSION
from erev_api.events.stream import EventIn
from erev_engine.canonical import sha256_hex

OPENING = ContractEventType.OPENING_BALANCE_ESTABLISHED
ACTIVATED = ContractEventType.CONTRACT_ACTIVATED
CUTOVER = date(2025, 12, 31)
KNOWN_AT = datetime(2026, 1, 31, 12, tzinfo=UTC)


def _usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _body(revenue: str, remaining: str) -> dict[str, Any]:
    row = {
        "obligation_key": "SUB-01",
        "delivered_quantity_cum": "0",
        "ssp_delivered_cum": "0",
        "remaining_quantity": "1",
        "remaining_ssp": "240000",
        "revenue_cum": _usd(revenue),
        "billed_cum": _usd("240000.00"),
        "catch_up_cum": _usd("0.00"),
        "pre_standard_revenue_cum": _usd("0.00"),
        "remaining_allocation": _usd(remaining),
        "remaining_billing": _usd("0.00"),
        "position_obligation": _usd("0.00"),
        "netting_reclass_amount": _usd("0.00"),
    }
    return {"reason": "LEGACY_MIGRATION", "cutover_date": CUTOVER.isoformat(), "obligations": [row]}


def test_pending_events_carry_the_registered_latest_version_and_stored_rows_keep_theirs() -> None:
    contract_id = uuid4()
    contracts = {contract_id: {"external_id": "C-127", "head_stream_version": 3}}
    stored_body = payloads.payload_json(
        payloads.OpeningBalanceEstablishedV1.model_validate(_body("120000.00", "120000.00"))
    )
    stored_row = {
        "id": uuid4(),
        "contract_id": contract_id,
        "stream_version": 3,
        "event_type": OPENING.value,
        "schema_version": 1,
        "effective_date": CUTOVER,
        "recorded_at": KNOWN_AT,
        "record_seq": 7,
        "origin": "API",
        "is_manual": False,
        "obligation_ids": [],
        "payload": stored_body,
        "payload_sha256": sha256_hex(stored_body),
        "idempotency_key": None,
        "supersedes_event_id": None,
        "estimate_version_id": None,
    }
    exact = payloads.parse_payload(
        OPENING, 2, _body("119999.876543210987654321", "120000.123456789012345679")
    )
    activated = payloads.parse_payload(
        ACTIVATED, 1, {"checklist": [{"code": "ACT", "passed": True}]}
    )
    pending = [
        EventIn(event_type=OPENING, effective_date=CUTOVER, payload=exact),
        EventIn(event_type=ACTIVATED, effective_date=CUTOVER, payload=activated),
    ]
    found = bundles._events(
        [stored_row],
        pending,
        contracts=contracts,
        obligation_keys={},
        known_at=KNOWN_AT,
        pending_contract_id=contract_id,
    )
    stored, opening, activation = found
    assert (stored.event_key, stored.stream_version, stored.schema_version) == (
        "C-127/EV-000003",
        3,
        1,
    )
    assert (opening.event_key, opening.stream_version, opening.schema_version) == (
        "C-127/EV-000004",
        4,
        2,
    )
    assert opening.schema_version == LATEST_SCHEMA_VERSION[OPENING] == 2
    assert (activation.event_key, activation.schema_version) == ("C-127/EV-000005", 1)
    assert activation.schema_version == LATEST_SCHEMA_VERSION[ACTIVATED] == 1
    # the pending payload reaches the engine exactly (the amount string, unwrapped, unrounded)
    assert opening.payload["obligations"][0]["revenue_cum"] == "119999.876543210987654321"
    assert opening.payload_sha256 == sha256_hex(payloads.payload_json(exact))
    # the stored row's identity is untouched: its version, hash and body
    assert stored.payload_sha256 == stored_row["payload_sha256"]
    assert stored.payload["obligations"][0]["revenue_cum"] == "120000.00"
