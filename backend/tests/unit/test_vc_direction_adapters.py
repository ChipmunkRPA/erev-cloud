"""ENC-VC-direction: the eight adapter cases of Codex's independent probe, as an in-repo test.

The probe (``2026-09-19-vc-direction-independent-probe.py``, kept unchanged outside the repo) drove
the real production bundle assembler (``bundles.estimate_version_input``) and the answer-key adapter
(``_Assembler._estimate_input``) into stage 04 measurement for VOLUME_TIER and BONUS with explicit
INCREASE and DECREASE of 100. On 9467de0 three of eight failed: an explicit VOLUME_TIER INCREASE
measured −100 through both adapters, and a BONUS DECREASE measured +100 through the answer-key
adapter (the production ``_vc_sign`` workaround signed it). Expected signs derive from 04 B3-D16:
version amounts are magnitudes and the element's explicit direction gives the sign. No database.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from erev_api.domain.contracts.bundles import estimate_version_input
from erev_engine.stages.s04_transaction_price import vc
from support.answer_keys.models import Estimate
from support.answer_keys.runners import _Assembler
from support.recognition import book_context

CASES = [
    (kind, direction) for kind in ("VOLUME_TIER", "BONUS") for direction in ("INCREASE", "DECREASE")
]


def _element(kind: str, direction: str) -> dict[str, Any]:
    return {
        "element_code": "E",
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "method": "ENTERED_AMOUNT",
        "vc_element_type": kind,
        "direction": direction,
        "allocation_target": "CONTRACT",
        "target_obligation_ids": [],
        "obligation_id": None,
    }


def _stored_version() -> dict[str, Any]:
    return {
        "version_no": 1,
        "scenarios": [],
        "status": "APPROVED",
        "effective_date": date(2026, 1, 1),
        "parameters": {},
        "unconstrained_amount": None,
        "most_conservative_amount": None,
        "constrained_amount": Decimal("100"),
        "rate": None,
        "expected_total_amount": None,
        "expected_quantity": None,
        "amortization_months": None,
        "currency": "USD",
        "supersedes_version_id": None,
        "content_sha256": "0" * 64,
    }


def _measured(kind: str, direction: str, path: str) -> tuple[Any, Any]:
    ctx = book_context()
    entity = next(iter(ctx.entities))
    st = SimpleNamespace(
        identified=SimpleNamespace(
            canonical=SimpleNamespace(
                contracts={
                    "C": SimpleNamespace(header=SimpleNamespace(contracting_entity_code=entity))
                }
            )
        )
    )
    element = _element(kind, direction)
    if path == "production_bundle":
        version = estimate_version_input(
            _stored_version(), element, contract_key="C", obligation_keys={}, version_keys={}
        )
    else:
        key = {
            k: v for k, v in element.items() if k not in ("target_obligation_ids", "obligation_id")
        }
        key["versions"] = [
            {
                "version_no": "1",
                "effective_date": "2026-01-01",
                "constrained_amount": "100",
                "currency": "USD",
                "rationale": "Independent sign regression",
            }
        ]
        model = Estimate.model_validate(key)
        version = _Assembler._estimate_input("C/E", model, model.versions[0], "C/E@v1", None)
    result = vc._measure(ctx, st, version, "C", date(2026, 1, 1))  # type: ignore[arg-type]
    return version, result


@pytest.mark.parametrize(("kind", "direction"), CASES)
@pytest.mark.parametrize("path", ["production_bundle", "answer_key_adapter"])
def test_enc_vc_direction_adapter_sign(kind: str, direction: str, path: str) -> None:
    """The probe's eight cases: the measured constrained amount carries the explicit direction's
    sign (3 of 8 failed on 9467de0: VOLUME_TIER INCREASE through both adapters, BONUS DECREASE
    through the answer-key adapter)."""
    _, result = _measured(kind, direction, path)
    expected = Decimal("100") if direction == "INCREASE" else Decimal("-100")
    assert result.constrained == expected  # the probe's assertion, unchanged in substance


@pytest.mark.parametrize(("kind", "direction"), CASES)
@pytest.mark.parametrize("path", ["production_bundle", "answer_key_adapter"])
def test_enc_vc_direction_adapter_transmits_the_member(
    kind: str, direction: str, path: str
) -> None:
    """Both adapters carry the element's direction on the bundle and the amount as a magnitude."""
    version, _ = _measured(kind, direction, path)
    assert version.direction == direction
    assert version.constrained_amount == Decimal("100")
