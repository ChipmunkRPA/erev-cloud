"""Supporting report bytes must belong to their explicit source and IPE manifest."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from erev_api.domain.reports.evidence_reports import ReportSource, check_binding, check_manifest
from erev_api.problems import Problem
from erev_engine.canonical import canonical_bytes, sha256_hex

NOW = datetime(2026, 10, 8, tzinfo=UTC)
ENTITY = uuid4()
SOURCE = ReportSource(uuid4(), "config_change_register", sha256_hex({}), (ENTITY,), None, None, NOW)
OUTPUT = b"Name\r\n'=formula\r\n"
ROW = {
    "id": SOURCE.run_id,
    "report_code": SOURCE.report_code,
    "parameters": {},
    "entity_ids": [ENTITY],
    "book_code": None,
    "as_of_date": None,
    "known_at": NOW,
    "period_lock_id": None,
    "output_format": "CSV",
    "status": "SUCCEEDED",
    "output_file_id": uuid4(),
    "manifest_file_id": uuid4(),
    "report_version": 1,
    "report_run_no": "RPT-1",
    "row_count": 1,
    "control_totals": {},
    "tie_out_results": [],
    "output_sha256": hashlib.sha256(OUTPUT).hexdigest(),
}
MANIFEST = {
    "report": {"code": SOURCE.report_code, "version": 1},
    "report_run_no": "RPT-1",
    "parameters": {},
    "book": None,
    "row_count": 1,
    "control_totals": {},
    "tie_out_results": [],
    "sha256": ROW["output_sha256"],
    "file": {"media_type": "text/csv", "bytes": len(OUTPUT)},
}


def test_original_source_and_manifest_are_accepted_without_rerendering() -> None:
    check_binding(ROW, SOURCE)
    check_manifest(canonical_bytes(MANIFEST), ROW, OUTPUT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", uuid4()),
        ("report_code", "ssp_change_log"),
        ("parameters", {"filter": "subset"}),
        ("entity_ids", []),
        ("entity_ids", [uuid4()]),
        ("book_code", "ASC606"),
        ("as_of_date", NOW.date()),
        ("known_at", NOW - timedelta(seconds=1)),
        ("period_lock_id", uuid4()),
        ("output_format", "JSON"),
        ("status", "FAILED"),
        ("status", "RUNNING"),
        ("output_file_id", None),
        ("manifest_file_id", None),
    ],
)
def test_different_or_unfinished_source_is_refused(field: str, value: object) -> None:
    with pytest.raises(Problem):
        check_binding({**ROW, field: value}, SOURCE)


def test_unadmitted_report_cannot_choose_a_payload_path() -> None:
    source = replace(SOURCE, report_code="../../other")
    with pytest.raises(Problem):
        check_binding({**ROW, "report_code": source.report_code}, source)


@pytest.mark.parametrize(
    "field,value",
    [
        ("report", {"code": "other", "version": 1}),
        ("report", {"code": SOURCE.report_code, "version": 2}),
        ("report_run_no", "RPT-2"),
        ("parameters", {"only_changes": True}),
        ("book", "ASC606"),
        ("row_count", 2),
        ("control_totals", {"count": 2}),
        ("tie_out_results", [{"result": "FAIL"}]),
        ("sha256", "a" * 64),
        ("file", {"media_type": "text/csv", "bytes": 0}),
        ("file", {"media_type": "text/plain", "bytes": len(OUTPUT)}),
    ],
)
def test_manifest_must_match_run_and_output(field: str, value: object) -> None:
    with pytest.raises(Problem):
        check_manifest(canonical_bytes({**MANIFEST, field: value}), ROW, OUTPUT)


@pytest.mark.parametrize("content", [b"", b"[]", b"null", b"{}", canonical_bytes(MANIFEST) + b" "])
def test_malformed_or_noncanonical_manifest_is_refused(content: bytes) -> None:
    with pytest.raises(Problem):
        check_manifest(content, ROW, OUTPUT)


def test_changed_output_cannot_reuse_original_manifest() -> None:
    with pytest.raises(Problem):
        check_manifest(canonical_bytes(MANIFEST), ROW, OUTPUT + b"altered\r\n")
