"""Migration review distinguishes pending judgements from failed activation prerequisites."""

from dataclasses import replace
from typing import Any

import pytest
from erev_api.domain.contracts import activation
from erev_api.domain.migration import activation_review
from erev_api.problems import Problem
from erev_engine.bundle import InputBundle
from support import bundles


def _input(checks: list[dict[str, Any]]) -> InputBundle:
    value = bundles.minimal_contract()
    header = value.contracts[0]
    activated = bundles.event(
        header.external_id,
        2,
        "CONTRACT_ACTIVATED",
        header.inception_date,
        {"checklist": checks},
    )
    return replace(value, events=(*value.events, activated))


def _checks(*failed: str) -> list[dict[str, Any]]:
    return [
        {
            "code": code,
            "passed": code not in failed,
            "detail": "Review required" if code in failed else None,
        }
        for code in activation.CODES
    ]


def test_pending_judgements_remain_failed_and_visible() -> None:
    value = _input(_checks("DISTINCT_REVIEW", "STEP1_RECORD"))
    result = activation_review.preview(value, value.contracts[0].external_id)
    assert result["ready_for_activation"] is False
    assert result["pending_review_checks"] == ["DISTINCT_REVIEW", "STEP1_RECORD"]
    assert [item for item in result["checks"] if not item["passed"]] == [
        {"code": code, "passed": False, "detail": "Review required"}
        for code in result["pending_review_checks"]
    ]


def test_complete_checklist_has_no_pending_reviews() -> None:
    value = _input(_checks())
    result = activation_review.preview(value, value.contracts[0].external_id)
    assert result["ready_for_activation"] is True
    assert result["pending_review_checks"] == []


@pytest.mark.parametrize(
    "code",
    [
        "MANDATORY_FIELDS",
        "SOURCE_REFERENCE",
        "PRODUCT_TEMPLATE_SSP",
        "COMBINATION_SUGGESTIONS",
        "JUDGEMENT_RECORDS",
    ],
)
def test_nonreview_failure_cannot_be_deferred_to_promotion(code: str) -> None:
    value = _input(_checks(code, "STEP1_RECORD"))
    with pytest.raises(Problem) as refused:
        activation_review.preview(value, value.contracts[0].external_id)
    assert refused.value.slug == "activation-checklist-failed"
    assert [error.rule_id for error in refused.value.errors] == [code]


@pytest.mark.parametrize(
    "fault",
    ["missing", "duplicate", "foreign", "incomplete", "duplicate_code", "unknown", "malformed"],
)
def test_incomplete_or_ambiguous_checklist_is_refused(fault: str) -> None:
    checks = _checks()
    if fault == "incomplete":
        checks.pop()
    elif fault == "duplicate_code":
        checks.append(checks[0])
    elif fault == "unknown":
        checks[0]["code"] = "UNKNOWN"
    elif fault == "malformed":
        checks[0]["passed"] = "not-a-boolean"
    value = _input(checks)
    if fault == "missing":
        value = replace(value, events=value.events[:-1])
    elif fault == "duplicate":
        value = replace(value, events=(*value.events, value.events[-1]))
    elif fault == "foreign":
        value = replace(
            value, events=(*value.events[:-1], replace(value.events[-1], contract_key="OTHER"))
        )
    with pytest.raises(Problem) as refused:
        activation_review.preview(value, value.contracts[0].external_id)
    assert refused.value.errors[0].rule_id == "MIGRATION_ACTIVATION_EVIDENCE"
