"""Bind reviewed line suggestions to an explicit human-authored draft; no persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

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


def review_draft(
    proposed: Sequence[Mapping[str, Any]],
    request: AIExtractionDraftIn,
    *,
    resolved_customer: tuple[UUID, str] | None = None,
) -> ReviewedFields:
    """Bind supported header facts as well as lines, refusing every unbound retained fact.

    An existing customer must be freshly resolved by the eventual command under tenant/source
    authorization; the tuple's ID must match the explicit draft customer ID. Names are compared
    exactly, never searched or inferred. The human selects whether an extracted effective date
    represents inception or signature. Structured review terms require a separate implementation.
    This function performs no reads or writes and is not an acceptance authorization boundary.
    """
    reviewed = review_draft_lines(proposed, request)
    headers = {
        path: value for path, value in reviewed.values.items() if not path.startswith("lines.")
    }
    if headers.keys() != request.header_bindings.keys():
        raise FieldReviewRefused("AI_REVIEW_HEADER_BINDINGS")
    for path, target in request.header_bindings.items():
        value = headers[path]
        actual: Any
        if path == "customer_name" and target == "customer":
            if request.draft.customer_id is not None:
                if resolved_customer is None or resolved_customer[0] != request.draft.customer_id:
                    raise FieldReviewRefused("AI_REVIEW_CUSTOMER_UNRESOLVED")
                actual = resolved_customer[1]
            else:
                if request.draft.customer is None:
                    raise FieldReviewRefused("AI_REVIEW_CUSTOMER_UNRESOLVED")
                actual = request.draft.customer.name
        elif path == "effective_date" and target in ("inception_date", "signature_date"):
            date_value = getattr(request.draft, target)
            actual = None if date_value is None else date_value.isoformat()
        elif path == "payment_terms" and target == "payment_terms":
            actual = request.draft.payment_terms
        else:
            raise FieldReviewRefused("AI_REVIEW_HEADER_BINDINGS")
        if actual != value:
            raise FieldReviewRefused("AI_REVIEW_DRAFT_MISMATCH")
    return reviewed
