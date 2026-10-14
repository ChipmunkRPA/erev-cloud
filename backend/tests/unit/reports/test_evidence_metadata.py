"""Register/header metadata must not advertise unfinished or inconsistent manifests."""

from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_queries import _retained_manifest
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex

DOCUMENT = {
    "files": [{"path": "lock/source.json", "sha256": "a" * 64, "bytes": 42, "report_run_id": None}]
}


def row(**changes: Any) -> dict[str, Any]:
    return {
        "status": "SUCCEEDED",
        "file_id": UUID(int=1),
        "manifest": DOCUMENT,
        "manifest_sha256": sha256_hex(DOCUMENT),
        **changes,
    }


def test_retained_metadata_exposes_exact_payload_population() -> None:
    result = _retained_manifest(row())
    assert result is not None
    assert result.model_dump(mode="json") == DOCUMENT


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "FAILED"])
def test_unfinished_status_never_advertises_a_manifest_even_with_leftover_metadata(
    status: str,
) -> None:
    assert _retained_manifest(row(status=status)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"file_id": None},
        {"manifest": None},
        {"manifest_sha256": None},
        {"manifest_sha256": "b" * 64},
        {"manifest": {"files": []}},
    ],
)
def test_inconsistent_retained_metadata_fails_closed(changes: dict[str, Any]) -> None:
    with pytest.raises(Problem) as error:
        _retained_manifest(row(**changes))
    assert error.value.slug == "validation-failed"


def test_hash_consistency_alone_does_not_make_malformed_metadata_valid() -> None:
    malformed = {"files": [{"path": "lock/source.json"}]}
    with pytest.raises(Problem) as error:
        _retained_manifest(row(manifest=malformed, manifest_sha256=sha256_hex(malformed)))
    assert error.value.slug == "validation-failed"
