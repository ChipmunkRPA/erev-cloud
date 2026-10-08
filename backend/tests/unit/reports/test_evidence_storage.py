"""Retained output must match both database metadata and independently assembled source bytes."""

import hashlib
from dataclasses import replace
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_archive import PackFile, build
from erev_api.domain.reports.evidence_storage import checked_stored
from erev_api.problems import Problem

ARCHIVE = build([PackFile("source.json", b"original source")])
TENANT = UUID(int=1)
FILE = UUID(int=2)
ROW = {
    "tenant_id": TENANT,
    "status": "SUCCEEDED",
    "file_id": FILE,
    "manifest": ARCHIVE.manifest_document(),
    "manifest_sha256": ARCHIVE.manifest_sha256,
}
METADATA = {
    "id": FILE,
    "tenant_id": TENANT,
    "purpose": "EVIDENCE_PACK",
    "media_type": "application/zip",
    "size_bytes": len(ARCHIVE.content),
    "sha256": hashlib.sha256(ARCHIVE.content).hexdigest(),
}


def test_original_archive_matches_its_retained_metadata_and_sources() -> None:
    checked_stored(ROW, METADATA, ARCHIVE.content, ARCHIVE)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "RUNNING"),
        ("file_id", UUID(int=3)),
        ("tenant_id", UUID(int=4)),
        ("manifest", {"files": []}),
        ("manifest_sha256", "0" * 64),
    ],
)
def test_changed_pack_metadata_is_refused(field: str, value: object) -> None:
    with pytest.raises(Problem, match="failed verification"):
        checked_stored({**ROW, field: value}, METADATA, ARCHIVE.content, ARCHIVE)


@pytest.mark.parametrize(
    "field,value",
    [
        ("purpose", "REPORT_OUTPUT"),
        ("media_type", "application/octet-stream"),
        ("size_bytes", 1),
        ("sha256", "0" * 64),
    ],
)
def test_changed_file_metadata_is_refused(field: str, value: object) -> None:
    with pytest.raises(Problem, match="failed verification"):
        checked_stored(ROW, {**METADATA, field: value}, ARCHIVE.content, ARCHIVE)


def test_self_consistent_substituted_zip_is_not_the_bound_close() -> None:
    other = build([PackFile("source.json", b"substituted source")])
    row = {**ROW, "manifest": other.manifest_document(), "manifest_sha256": other.manifest_sha256}
    metadata = {
        **METADATA,
        "sha256": hashlib.sha256(other.content).hexdigest(),
        "size_bytes": len(other.content),
    }
    with pytest.raises(Problem, match="failed verification"):
        checked_stored(row, metadata, other.content, ARCHIVE)


def test_even_matching_outer_hashes_do_not_allow_a_corrupted_zip() -> None:
    content = b"not a ZIP"
    metadata = {
        **METADATA,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    with pytest.raises(Problem, match="archive is invalid"):
        checked_stored(ROW, metadata, content, replace(ARCHIVE, content=content))
