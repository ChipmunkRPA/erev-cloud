"""Prepare cited explanation proposals and select the deterministic fallback.

The gateway still owns authorized trace retrieval, job admission, provider execution
and durable proposal/audit writes. This module never changes accounting records.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from types import MappingProxyType
from typing import Any
from uuid import UUID

from erev_api.domain.ai.numbers import MAX_TEXT_BYTES, validate_numbers
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.domain.ai.preparation import PreparationRefused, prepare_request
from erev_api.domain.ai.templates import load_template
from erev_api.explain.service import Explanation


@dataclass(frozen=True, slots=True)
class NarrativeSelection:
    proposed: bool
    narrative: tuple[str, ...]
    node_ids: tuple[str, ...]
    problem_code: str | None


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("AI_INVALID_NARRATIVE")
        value[key] = item
    return value


def _no_number(_: str) -> None:
    # The response envelope contains strings and string arrays only.
    raise ValueError("AI_INVALID_NARRATIVE")


@dataclass(frozen=True, slots=True)
class PreparedNarrative:
    request: AIRequest
    trace_id: UUID
    values: Mapping[str, Decimal]
    minor_unit: int
    deterministic: tuple[str, ...]

    def select(self, response: AIResponse) -> NarrativeSelection:
        """Never return model text or citations from a refused response."""

        def fallback(code: str) -> NarrativeSelection:
            return NarrativeSelection(False, self.deterministic, (), code)

        if response.stop_reason != "end_turn":
            return fallback(
                "AI_REFUSAL" if response.stop_reason == "refusal" else "AI_INCOMPLETE_RESPONSE"
            )
        try:
            raw = response.text.encode("utf-8")
        except UnicodeEncodeError:
            return fallback("AI_INVALID_ENCODING")
        if len(raw) > MAX_TEXT_BYTES:
            return fallback("AI_RESPONSE_TOO_LARGE")
        if sha256(raw).hexdigest() != response.response_sha256:
            return fallback("AI_RESPONSE_HASH_MISMATCH")
        try:
            output = json.loads(
                raw,
                object_pairs_hook=_unique,
                parse_int=_no_number,
                parse_float=_no_number,
                parse_constant=_no_number,
            )
        except (ValueError, RecursionError):
            return fallback("AI_INVALID_NARRATIVE")
        if not isinstance(output, dict) or set(output) != {"narrative", "node_ids"}:
            return fallback("AI_INVALID_NARRATIVE")
        narrative, ids = output["narrative"], output["node_ids"]
        if not isinstance(narrative, str) or not narrative.strip():
            return fallback("AI_INVALID_NARRATIVE")
        if (
            not isinstance(ids, list)
            or not ids
            or len(ids) > len(self.values)
            or any(not isinstance(item, str) or item not in self.values for item in ids)
            or len(set(ids)) != len(ids)
        ):
            return fallback("AI_INVALID_CITATION")
        # Uncited nodes cannot make an invented narrative figure appear supported.
        checked = validate_numbers(
            narrative, [self.values[item] for item in ids], minor_unit=self.minor_unit
        )
        if not checked.valid:
            return fallback(checked.code or "AI_INVALID_NARRATIVE")
        return NarrativeSelection(True, (narrative,), tuple(ids), None)


def prepare_narrative(
    *,
    explanation: Explanation,
    trace_id: UUID,
    minor_unit: int,
    model: str,
    max_tokens: int,
    redact_contact_details: bool = True,
) -> PreparedNarrative:
    """Snapshot an already authorized explanation; send only required trace fields.

    Callers supply the book currency's minor unit. Mixed-currency nodes are excluded
    from this single-currency explanation rather than implicitly converted. The
    deterministic narrative is retained locally and is never derived from AI output.
    """
    values: dict[str, Decimal] = {}
    nodes: list[dict[str, str | None]] = []
    for node in explanation.nodes:
        if node.currency not in (None, explanation.currency):
            continue
        if (
            not node.id
            or node.id in values
            or len(node.value) > 128
            or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", node.value) is None
        ):
            raise PreparationRefused("AI_INVALID_TRACE_EVIDENCE")
        values[node.id] = Decimal(node.value)
        nodes.append(
            {"id": node.id, "value": node.value, "currency": node.currency, "measure": node.measure}
        )
    if explanation.root_node_id not in values:
        raise PreparationRefused("AI_INVALID_TRACE_EVIDENCE")
    try:
        validate_numbers("", values.values(), minor_unit=minor_unit)
    except ValueError:
        raise PreparationRefused("AI_INVALID_TRACE_EVIDENCE") from None
    facts = {
        "trace_id": str(trace_id),
        "root_node_id": explanation.root_node_id,
        "currency": explanation.currency,
        "nodes": nodes,
    }
    request = prepare_request(
        template=load_template("explain-narrative", 1),
        model=model,
        max_tokens=max_tokens,
        inputs=facts,
        redact_contact_details=redact_contact_details,
    )
    # Privacy normalization must not change ids or numeric evidence after snapshotting.
    if json.loads(request.messages[0]["content"])["facts"] != facts:
        raise PreparationRefused("AI_NARRATIVE_PREPARATION_MISMATCH")
    return PreparedNarrative(
        request, trace_id, MappingProxyType(values), minor_unit, tuple(explanation.narrative)
    )
