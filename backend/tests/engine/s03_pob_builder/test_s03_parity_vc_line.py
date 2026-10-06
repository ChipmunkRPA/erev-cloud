"""S03-R-18 and S03-R-04 under the parity preset: a VC row is a ``VC_LINE`` by its stratification
(ENGINE_SPEC §1 S01-R-06, §3 S03-R-04, S03-R-18; lane L5-5, LATE-CHK-091).

The legacy setup import gives a VC row the stratification ``VC`` and pins its contract-level VC
element. Stage 03 assigns ``LEGACY-VC`` by that stratification alone, so a VC row booked without it
is ``LEGACY-DISTINCT``, and its negative price raises ``NEGATIVE_BOOKING_LINE`` (``ERROR``). The
answer-key world build omitted the stratification for key lines whose product template is of kind
``VC_LINE``; the runner now carries it with the S01-R-06 element. Golden Contract 2, step 02
(legacy 02 §5.3): hardware, software, consulting and ``VC #1`` at −100.00. No database.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import pytest
from erev_engine import compute
from erev_engine.bundle import EventInput, InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from support import golden_streams


def _contract_2() -> InputBundle:
    return golden_streams.stream("Contract 2", "02").input_bundle(preset="LEGACY_PARITY")


def _without_vc_stratification(bundle: InputBundle) -> tuple[InputBundle, str]:
    booked = next(e for e in bundle.events if e.event_type == "CONTRACT_BOOKED")
    lines = [dict(line) for line in booked.payload["lines"]]  # type: ignore[union-attr]
    vc = next(line for line in lines if line.get("stratification") == "VC")
    del vc["stratification"]
    payload: Mapping[str, object] = {**booked.payload, "lines": lines}
    replaced: EventInput = dataclasses.replace(
        booked, payload=payload, payload_sha256=sha256_hex(payload)
    )
    events = tuple(replaced if e is booked else e for e in bundle.events)
    return dataclasses.replace(bundle, events=events), str(vc["obligation_key"])


def test_vc_row_with_stratification_is_a_vc_line() -> None:
    output = compute(_contract_2())
    (book,) = output.books
    assert book.contract_version is not None
    # The VC element counts −100.00 in the price (minor units; S01-R-06, POL-213).
    assert book.contract_version.columns["transaction_price"] == 90000


def test_vc_row_without_stratification_is_a_negative_booking_line() -> None:
    bundle, obligation_key = _without_vc_stratification(_contract_2())
    with pytest.raises(EngineError) as raised:
        compute(bundle)
    assert raised.value.code == "NEGATIVE_BOOKING_LINE"
    assert '"obligation_key":"' + obligation_key + '"' in raised.value.detail["findings"]
