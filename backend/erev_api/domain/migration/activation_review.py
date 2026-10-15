"""Expose the actual pre-activation checks and pending migration judgement reviews.

BS3-D-23/26 require the promotion approver to review distinctness and collectibility records.
This preview neither creates those records nor marks their failed checks as passed. The future
promotion writer must create/review them under the approved basis and require all checks to pass.
"""

from __future__ import annotations

from typing import Any

from erev_engine.bundle import InputBundle
from pydantic import ValidationError

from erev_api.domain.contracts import activation
from erev_api.events.payloads import ContractActivatedV1
from erev_api.problems import Problem, ProblemError

_PENDING_REVIEWS = frozenset({activation.DISTINCT_REVIEW, activation.STEP1_RECORD})


def _invalid() -> Problem:
    message = "Migration reproduction needs one complete pre-activation checklist per contract."
    return Problem(
        "invalid-transition",
        message,
        errors=[
            ProblemError(
                field="migration_id", rule_id="MIGRATION_ACTIVATION_EVIDENCE", message=message
            )
        ],
    )


def preview(bundle: InputBundle, contract_key: str) -> dict[str, Any]:
    events = [
        event
        for event in bundle.events
        if event.contract_key == contract_key and event.event_type == "CONTRACT_ACTIVATED"
    ]
    if len(events) != 1:
        raise _invalid()
    try:
        payload = ContractActivatedV1.model_validate(events[0].payload)
    except ValidationError as error:
        raise _invalid() from error
    checks = {item.code: item for item in payload.checklist}
    if len(checks) != len(payload.checklist) or set(checks) != set(activation.CODES):
        raise _invalid()
    failed = [checks[code] for code in activation.CODES if not checks[code].passed]
    blockers = [item for item in failed if item.code not in _PENDING_REVIEWS]
    if blockers:
        raise Problem(
            "activation-checklist-failed",
            f"Migration contract {contract_key} has failed activation prerequisites.",
            errors=[
                ProblemError(rule_id=item.code, message=item.detail or item.code)
                for item in blockers
            ],
        )
    return {
        "ready_for_activation": not failed,
        "pending_review_checks": [item.code for item in failed],
        "checks": [checks[code].model_dump(mode="json") for code in activation.CODES],
    }
