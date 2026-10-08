"""Certification proof validation; not an accounting or complete-pack acceptance gate."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_reconciliations import certification_basis
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex

NOW = datetime(2026, 9, 30, tzinfo=UTC)
STATEMENT = {"totals": [{"currency": "USD", "difference": "0.00"}], "items": []}
ROW = {
    "tenant_id": UUID(int=1),
    "id": UUID(int=2),
    "entity_id": UUID(int=3),
    "book_code": "ASC606",
    "period_id": UUID(int=4),
    "status": "CERTIFIED",
    "certified_at": NOW,
    "auto_certify_rule_id": None,
    "auto_certify_rule_set_version_id": None,
}
SIGNS = [
    {
        "tenant_id": ROW["tenant_id"],
        "subject_type": "reconciliation",
        "subject_id": ROW["id"],
        "id": UUID(int=10 + index),
        "role": role,
        "signer_id": UUID(int=20 + index),
        "subject_content_sha256": sha256_hex(STATEMENT),
        "signed_at": NOW,
        "mfa_verified_at": NOW - timedelta(minutes=1),
    }
    for index, role in enumerate(("PREPARER", "REVIEWER"))
]
AUTO = {**ROW, "auto_certify_rule_id": UUID(int=5), "auto_certify_rule_set_version_id": UUID(int=6)}
EXECUTION = {
    "tenant_id": ROW["tenant_id"],
    "control_id": "CTL-026",
    "run_ref_type": "RECONCILIATION_RUN",
    "run_ref_id": ROW["id"],
    "entity_id": ROW["entity_id"],
    "book_code": ROW["book_code"],
    "period_id": ROW["period_id"],
    "result": "PASS",
    "population_count": 1,
    "exception_count": 0,
    "executed_at": NOW,
    "detail": {
        "auto_certified": True,
        "rule": {
            "rule_id": str(AUTO["auto_certify_rule_id"]),
            "rule_set_version_id": str(AUTO["auto_certify_rule_set_version_id"]),
        },
    },
}


def test_signed_content_is_identical_after_reopen() -> None:
    expected = certification_basis(ROW, STATEMENT, SIGNS, [], locked_at=NOW)
    assert expected["kind"] == "SIGNOFFS"
    assert expected["snapshot_sha256"] == sha256_hex(STATEMENT)
    assert (
        certification_basis({**ROW, "status": "REOPENED"}, STATEMENT, SIGNS, [], locked_at=NOW)
        == expected
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("subject_content_sha256", "0" * 64),
        ("subject_id", UUID(int=99)),
        ("tenant_id", UUID(int=99)),
        ("subject_type", "period_lock"),
        ("signed_at", NOW + timedelta(seconds=1)),
        ("mfa_verified_at", NOW + timedelta(seconds=1)),
    ],
)
def test_every_signature_must_bind_the_subject_and_precede_certification(
    field: str, value: object
) -> None:
    signs = deepcopy(SIGNS)
    signs[1][field] = value
    with pytest.raises(Problem):
        certification_basis(ROW, STATEMENT, signs, [], locked_at=NOW)


def test_missing_duplicate_or_same_person_signatures_cannot_certify() -> None:
    for signs in (
        [],
        SIGNS[:1],
        [*SIGNS, SIGNS[0]],
        [SIGNS[0], {**SIGNS[1], "signer_id": SIGNS[0]["signer_id"]}],
    ):
        with pytest.raises(Problem):
            certification_basis(ROW, STATEMENT, signs, [], locked_at=NOW)
    with pytest.raises(Problem):
        certification_basis(
            ROW, {**STATEMENT, "items": [{"difference": "0.01"}]}, SIGNS, [], locked_at=NOW
        )


def test_auto_certification_uses_control_evidence_not_invented_signatures() -> None:
    basis = certification_basis(AUTO, STATEMENT, [], [EXECUTION], locked_at=NOW)
    assert basis["kind"] == "AUTO_CERTIFICATION"
    assert basis["control_execution"] == EXECUTION
    assert "signoffs" not in basis
    for executions in ([], [EXECUTION, EXECUTION]):
        with pytest.raises(Problem):
            certification_basis(AUTO, STATEMENT, [], executions, locked_at=NOW)
    with pytest.raises(Problem):
        certification_basis(AUTO, STATEMENT, SIGNS, [EXECUTION], locked_at=NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", UUID(int=99)),
        ("run_ref_id", UUID(int=99)),
        ("entity_id", UUID(int=99)),
        ("period_id", UUID(int=99)),
        ("book_code", "IFRS15"),
        ("control_id", "CTL-025"),
        ("run_ref_type", "REPORT_RUN"),
        ("result", "FAIL"),
        ("exception_count", 1),
        ("population_count", 0),
        ("executed_at", NOW + timedelta(seconds=1)),
        ("detail", {"auto_certified": False, "rule": EXECUTION["detail"]["rule"]}),
        ("detail", {"auto_certified": True, "rule": {"rule_id": "wrong"}}),
    ],
)
def test_auto_evidence_must_match_the_whole_scope_rule_and_success(
    field: str, value: object
) -> None:
    with pytest.raises(Problem):
        certification_basis(AUTO, STATEMENT, [], [{**EXECUTION, field: value}], locked_at=NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "REVIEWED"},
        {"certified_at": None},
        {"certified_at": NOW + timedelta(seconds=1)},
        {"auto_certify_rule_id": UUID(int=5)},
        {"auto_certify_rule_set_version_id": UUID(int=6)},
    ],
)
def test_uncertified_or_partial_rule_references_are_refused(changes: dict) -> None:
    with pytest.raises(Problem):
        certification_basis({**ROW, **changes}, STATEMENT, SIGNS, [], locked_at=NOW)
