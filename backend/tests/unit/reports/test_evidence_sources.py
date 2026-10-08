"""Persisted close sources must keep their population, cutoffs and pack-row identity."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_reports import PATHS
from erev_api.domain.reports.evidence_sources import CloseSources, checked_row
from erev_api.problems import Problem
from pydantic import ValidationError

NOW = datetime(2026, 10, 8, tzinfo=UTC)
DOCUMENT = {
    "format": "erev.close-evidence.sources.v1",
    "tenant_id": str(UUID(int=1)),
    "request": {
        "kind": "CLOSE",
        "entity_code": "AVM-US",
        "book": "ASC606",
        "period_key": "FY2026-P09",
        "period_lock_id": str(UUID(int=2)),
    },
    "requested_at": NOW.isoformat(),
    "entity_id": str(UUID(int=3)),
    "period_id": str(UUID(int=4)),
    "cutoff_known_at": NOW.isoformat(),
    "snapshot_manifest_sha256": "a" * 64,
    "frozen_report_run_ids": [str(UUID(int=5))],
    "audit_verification_id": str(UUID(int=6)),
    "supporting_reports": [
        {
            "run_id": str(UUID(int=10 + index)),
            "report_code": code,
            "parameters_sha256": "b" * 64,
            "entity_ids": [str(UUID(int=3))],
            "book_code": None,
            "as_of_date": None,
            "known_at": NOW.isoformat(),
            "job_id": str(UUID(int=20 + index)),
        }
        for index, code in enumerate(sorted(PATHS))
    ],
}


def test_database_json_round_trip_keeps_exact_bound_values() -> None:
    bound = CloseSources.model_validate(DOCUMENT)
    row = {**bound.pack_values(), "tenant_id": bound.tenant_id, "created_at": bound.requested_at}
    restored = checked_row(row)
    assert restored == bound
    assert CloseSources.model_validate_json(bound.model_dump_json()) == bound
    assert len(row["report_run_ids"]) == 6
    source = restored.supporting_reports[0].source()
    assert source.run_id == UUID(int=10)
    assert source.known_at == NOW
    assert source.entity_ids == (bound.entity_id,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", "future-format"),
        ("unexpected", True),
        ("supporting_reports", []),
        ("supporting_reports", DOCUMENT["supporting_reports"][:-1]),
        ("audit_verification_id", None),
        ("snapshot_manifest_sha256", "bad"),
        ("requested_at", "2026-10-08T00:00:00"),
        ("cutoff_known_at", "2026-10-08T00:00:00"),
        ("requested_at", NOW - timedelta(seconds=1)),
        ("frozen_report_run_ids", [str(UUID(int=5)), str(UUID(int=5))]),
        ("frozen_report_run_ids", [DOCUMENT["supporting_reports"][0]["run_id"]]),
    ],
)
def test_incomplete_or_unsupported_bindings_are_refused(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        CloseSources.model_validate({**DOCUMENT, field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("report_code", "another_report"),
        ("run_id", str(UUID(int=11))),
        ("job_id", str(UUID(int=21))),
        ("entity_ids", []),
        ("entity_ids", [str(UUID(int=99))]),
        ("entity_ids", [str(UUID(int=3)), str(UUID(int=99))]),
        ("known_at", NOW + timedelta(seconds=1)),
        ("parameters_sha256", "bad"),
        ("unexpected", True),
    ],
)
def test_one_wrong_source_invalidates_the_whole_binding(field: str, value: object) -> None:
    document = deepcopy(DOCUMENT)
    document["supporting_reports"][0][field] = value
    with pytest.raises(ValidationError):
        CloseSources.model_validate(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", UUID(int=99)),
        ("entity_id", UUID(int=99)),
        ("period_id", UUID(int=99)),
        ("period_lock_id", UUID(int=99)),
        ("book_code", "IFRS15"),
        ("kind", "ACCESS"),
        ("created_at", NOW + timedelta(seconds=1)),
        ("as_of_date", NOW.date()),
        ("from_date", NOW.date()),
        ("to_date", NOW.date()),
        ("contract_ids", [UUID(int=99)]),
        ("report_run_ids", []),
        ("report_run_ids", [UUID(int=10)] * 6),
        ("source_binding", None),
    ],
)
def test_pack_row_cannot_disagree_with_its_binding(field: str, value: object) -> None:
    bound = CloseSources.model_validate(DOCUMENT)
    row = {**bound.pack_values(), "tenant_id": bound.tenant_id, "created_at": NOW, field: value}
    with pytest.raises(Problem):
        checked_row(row)


def test_unversioned_document_cannot_be_assumed_to_be_current() -> None:
    with pytest.raises(ValidationError):
        CloseSources.model_validate(
            {key: value for key, value in DOCUMENT.items() if key != "format"}
        )
