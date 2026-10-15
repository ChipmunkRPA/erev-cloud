"""Bind reviewed line suggestions to an explicit human-authored draft; no persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from erev_api.domain.ai.field_review import FieldReviewRefused, ReviewedFields, review_fields
from erev_api.schemas.ai import AIExtractionDraftIn


def review_draft_lines(
    proposed: Sequence[Mapping[str, Any]], request: AIExtractionDraftIn
) -> ReviewedFields:
    """Require an explicit one-to-one mapping for every retained line suggestion.

    Rejected suggestions cannot be mapped. Additional human-authored draft lines are allowed.
    Quantity, obligation identity, currency and other required draft data come from the request;
    no missing value is inferred. Header/reference/structured-term binding and approval remain
    separate required work before this can participate in an acceptance command.
    """
    reviewed = review_fields(proposed, request.field_decisions)
    lines = {path: value for path, value in reviewed.values.items() if path.startswith("lines.")}
    if lines.keys() != request.line_bindings.keys():
        raise FieldReviewRefused("AI_REVIEW_LINE_BINDINGS")
    draft_lines = {line.obligation_key: line for line in request.draft.lines}
    for path, value in lines.items():
        target = draft_lines[request.line_bindings[path]]
        if (
            target.product_code != value["product_code"]
            or Decimal(target.total_price.amount) != Decimal(value["amount"])
            or target.total_price.currency != request.draft.transaction_currency
        ):
            raise FieldReviewRefused("AI_REVIEW_DRAFT_MISMATCH")
    return reviewed
