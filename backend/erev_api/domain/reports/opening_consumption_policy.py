"""Retain the resolved policy behind opening-liability disclosure explanations."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.enums import BookCode
from erev_api.registry.resolve import resolve

KEY = "opening_consumption_policies_v1"
POLICY = "rollforward.opening_liability_consumption"
OPTIONS = frozenset({"FIFO_WITHIN_CONTRACT", "FIFO_WITHIN_POB"})


def read(
    session: Session, params: ReportParams, entities: Sequence[tie_outs.EntityRef], book: str
) -> list[str]:
    expected = {str(entity.id) for entity in entities}
    if params.binding is not None and KEY in params.binding.evidence:
        retained = params.binding.evidence[KEY]
        if (
            not isinstance(retained, dict)
            or set(retained) != {"book", "entities"}
            or retained["book"] != book
            or not isinstance(retained["entities"], dict)
            or set(retained["entities"]) != expected
            or any(
                not isinstance(value, str) or value not in OPTIONS
                for value in retained["entities"].values()
            )
        ):
            raise tie_outs.invalid("book", "Retained opening-consumption policies are invalid.")
        return sorted(set(retained["entities"].values()))
    # Existing saved runs without this evidence preserve their original read behavior.
    values: dict[str, Any] = {
        str(entity.id): str(
            resolve(
                session,
                POLICY,
                book_code=BookCode(book),
                entity_id=entity.id,
                known_at=params.known_at,
            ).value
        )
        for entity in entities
    }
    if not set(values.values()) <= OPTIONS:
        raise tie_outs.invalid("book", "An opening-consumption policy is unsupported.")
    tie_outs.record_evidence(params, KEY, {"book": book, "entities": values})
    return sorted(set(values.values()))
