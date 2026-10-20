"""Retained registry provenance must not claim source bytes or successful absent gates."""

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_change_releases import ReleaseEvidence, ReleaseRecord, files
from pydantic import ValidationError

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


def record(**changes: object) -> ReleaseRecord:
    return ReleaseRecord.model_validate(
        {
            "id": str(UUID(int=1)),
            "engine_version": "1.0.0",
            "build_sha": "build",
            "schema_revision": "0188",
            "deployed_at": NOW,
            "validation_level": "PATCH",
            "control_impact_tags": ["CTL-041"],
            "gate_results": {},
            **changes,
        }
    )


def source(**changes: object) -> ReleaseEvidence:
    return ReleaseEvidence.model_validate(
        {
            "from_date": "2026-10-19",
            "to_date": "2026-10-19",
            "known_at": NOW,
            "requesting_release": record(),
            "registered_in_range": [record()],
            **changes,
        }
    )


def test_retained_manifest_preserves_missing_and_failed_gates() -> None:
    failed = record(gate_results={"GK-01": {"result": "FAIL", "output_sha256": None}})
    bound = source(requesting_release=failed, registered_in_range=[failed])
    output = files(bound)[0]
    assert output.path == "release/registered_manifest.json"
    document = json.loads(output.content)
    assert "not original build-manifest bytes" in document["basis"]
    assert document["source"]["requesting_release"]["gate_results"] == failed.gate_results
    assert files(bound) == files(ReleaseEvidence.model_validate_json(bound.model_dump_json()))
    assert (
        json.loads(files(source())[0].content)["source"]["requesting_release"]["gate_results"] == {}
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"registered_in_range": [record(), record()]},
        {"registered_in_range": [record(deployed_at=datetime(2026, 10, 18, tzinfo=UTC))]},
        {"registered_in_range": [record(build_sha="different")]},
        {"requesting_release": record(deployed_at=datetime(2026, 10, 20, tzinfo=UTC))},
        {"to_date": "2026-10-20"},
    ],
)
def test_wrong_cutoff_or_conflicting_identity_refuses(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        source(**changes)


def test_requesting_release_can_precede_the_change_interval() -> None:
    older = record(deployed_at=datetime(2026, 10, 1, tzinfo=UTC))
    bound = source(requesting_release=older, registered_in_range=[])
    assert bound.requesting_release == older
    assert bound.registered_in_range == ()
