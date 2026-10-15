"""Resolve complete human field decisions without creating accounting commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from erev_api.domain.ai.extraction_fields import MAX_EXTRACTION_FIELDS, validate_contract_value
from erev_api.domain.ai.extraction_validation import OutputRefused
from erev_api.enums import AiFieldDecision
from erev_api.schemas.ai import AIFieldDecisionIn


class FieldReviewRefused(ValueError):
    """Stable refusal codes contain neither proposed text nor reviewer values."""


@dataclass(frozen=True)
class ReviewedFields:
    values: dict[str, Any]
    decisions: tuple[dict[str, Any], ...]


def review_fields(
    proposed: Sequence[Mapping[str, Any]], decisions: Sequence[AIFieldDecisionIn]
) -> ReviewedFields:
    """Require exact coverage; preserve accepted values, validate edits, omit rejections.

    Results are detached from caller-owned values. Decision records follow proposal order,
    independent of request order, and contain resolved values only for ACCEPT and EDIT.
    This does not resolve reference IDs, infer currency/quantity or classify accounting terms.
    The eventual command must separately check permission, source, status, expiry and SoD.
    """
    if not proposed or len(proposed) > MAX_EXTRACTION_FIELDS or len(decisions) != len(proposed):
        raise FieldReviewRefused("AI_REVIEW_FIELD_COVERAGE")
    originals: dict[str, Any] = {}
    for field in proposed:
        path = field.get("path")
        if not isinstance(path, str) or path in originals or "value" not in field:
            raise FieldReviewRefused("AI_REVIEW_INVALID_PROPOSAL")
        try:
            validate_contract_value(path, field["value"])
        except OutputRefused:
            raise FieldReviewRefused("AI_REVIEW_INVALID_PROPOSAL") from None
        originals[path] = field["value"]
    selected: dict[str, AIFieldDecisionIn] = {}
    for decision in decisions:
        if decision.path not in originals or decision.path in selected:
            raise FieldReviewRefused("AI_REVIEW_FIELD_COVERAGE")
        selected[decision.path] = decision
    if selected.keys() != originals.keys():
        raise FieldReviewRefused("AI_REVIEW_FIELD_COVERAGE")
    values: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    for path, original in originals.items():
        choice = selected[path]
        record: dict[str, Any] = {"path": path, "decision": choice.decision.value}
        if choice.reason is not None:
            record["reason"] = choice.reason
        if choice.decision is not AiFieldDecision.REJECT:
            value = original if choice.decision is AiFieldDecision.ACCEPT else choice.value
            try:
                validate_contract_value(path, value)
            except OutputRefused:
                raise FieldReviewRefused("AI_REVIEW_INVALID_VALUE") from None
            values[path] = deepcopy(value)
            record["value"] = deepcopy(value)
        records.append(record)
    return ReviewedFields(values=values, decisions=tuple(records))
