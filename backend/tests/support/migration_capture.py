"""A valid, verifiable capture world for the T-MIG-04 / T-MIG-05 tests (04 rev 1.60; Codex 0515
R1): one engine input bundle — ``support.bundles.minimal_contract`` plus an
``OPENING_BALANCE_ESTABLISHED`` event naming a migration batch and cutover — its T-CON-25
evidence bytes, hashes and the facts a
capture row derives from it (cutoff, member keys, event key). Row builders and unit tests use it so
their evidence DECODES and re-hashes exactly as the reconcile's ``verify_input_evidence`` demands;
nothing here is a database row and nothing is a golden expectation.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from erev_engine.bundle import InputBundle
from erev_engine.upgrade import encode_input, raw_digest
from support import bundles

__all__ = ["CaptureWorld", "capture_world"]

CUTOVER = date(2023, 1, 31)


@dataclass(frozen=True, slots=True)
class CaptureWorld:
    bundle: InputBundle
    evidence: bytes  # encode_input(bundle)
    contract_key: str  # the member contract's external id
    opening_event_key: str

    @property
    def input_sha256(self) -> str:
        return self.bundle.sha256()

    @property
    def evidence_document(self) -> dict[str, Any]:
        return json.loads(self.evidence.decode("utf-8"))

    @property
    def evidence_sha256(self) -> str:
        return raw_digest(self.evidence)

    @property
    def opening_payload_sha256(self) -> str:
        """The bundle's opening event ``payload_sha256`` (the hash-bound side of the binding)."""
        return next(
            e.payload_sha256 for e in self.bundle.events if e.event_key == self.opening_event_key
        )


def capture_world(batch_id: UUID, *, cutover: date = CUTOVER) -> CaptureWorld:
    """``minimal_contract`` with the admitted opening event appended at stream version 2 (after the
    booking), payload ``reason LEGACY_MIGRATION``, ``cutover_date`` and ``migration_batch_id``."""
    base = bundles.minimal_contract()
    header = base.contracts[0]
    key = header.external_id
    line_key = str(base.events[0].payload["lines"][0]["obligation_key"])  # type: ignore[index]
    opening = bundles.event(
        key,
        2,
        "OPENING_BALANCE_ESTABLISHED",
        cutover,
        {
            "reason": "LEGACY_MIGRATION",
            "cutover_date": cutover.isoformat(),
            "migration_batch_id": str(batch_id),
            "obligations": [
                {
                    "obligation_key": line_key,
                    "delivered_quantity_cum": "1",
                    "ssp_delivered_cum": "100",
                    "remaining_quantity": "0",
                    "remaining_ssp": "0",
                    "revenue_cum": {"amount": "100.00", "currency": "USD"},
                    "billed_cum": {"amount": "100.00", "currency": "USD"},
                    "catch_up_cum": {"amount": "0.00", "currency": "USD"},
                    "pre_standard_revenue_cum": {"amount": "0.00", "currency": "USD"},
                    "remaining_allocation": {"amount": "0.00", "currency": "USD"},
                    "remaining_billing": {"amount": "0.00", "currency": "USD"},
                    "position_obligation": {"amount": "0.00", "currency": "USD"},
                    "netting_reclass_amount": {"amount": "0.00", "currency": "USD"},
                }
            ],
        },
        obligation_keys=[line_key],
    )
    events = tuple(
        sorted((*base.events, opening), key=lambda e: (e.effective_date, e.record_seq, e.event_key))
    )
    bundle = dataclasses.replace(base, events=events)
    return CaptureWorld(
        bundle=bundle,
        evidence=encode_input(bundle),
        contract_key=key,
        opening_event_key=opening.event_key,
    )
