"""Admission of retained after-posting boundaries to analytical event replay."""

from collections.abc import Sequence

from erev_api.problems import Problem
from erev_engine.bundle import EventInput, InputBundle


def require_retained_basis(source: InputBundle, events: Sequence[EventInput]) -> None:
    modifications = {
        (contract.external_id, item.modification_key): item
        for contract in source.contracts
        for item in contract.modifications
    }
    for event in events:
        if event.event_type != "REGROUPED":
            continue
        retained = modifications.get(
            (
                event.contract_key,
                event.modification_key or str(event.payload.get("modification_id")),
            )
        )
        if (
            (source.evidence_revision or 0) < 37
            or retained is None
            or not retained.questionnaire.get("regroup_book_lines")
            or not retained.questionnaire.get("regroup_source_basis")
            or event.payload.get("direction") not in {"OUT", "IN"}
            or not event.payload.get("regroup_id")
        ):
            raise Problem(
                "validation-failed",
                "Regroup analysis requires retained after-posting transfer evidence.",
            )
