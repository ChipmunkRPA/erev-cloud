"""Catalogue adapters preserve original outputs and refuse missing or corrupt artifacts."""

import hashlib
import json
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from erev_api.domain.reports.evidence_archive import PackFile, build
from erev_api.domain.reports.evidence_catalogue import CatalogueEvidence, select_output
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ContractSamplePackCreateIn
from pydantic import ValidationError


def binding(output_format: str = "ZIP") -> CatalogueEvidence:
    return CatalogueEvidence.model_validate(
        {
            "tenant_id": uuid4(),
            "pack_id": uuid4(),
            "job_id": uuid4(),
            "report_code": "contract_sample_pack",
            "output_format": output_format,
            "request": ContractSamplePackCreateIn(
                kind="CONTRACT_SAMPLE", contract_external_ids=["C-1"], as_of=date(2026, 9, 30)
            ),
            "entity_ids": [uuid4()],
            "known_at": datetime(2026, 10, 1, tzinfo=UTC),
            "source_binding_sha256": "a" * 64,
        }
    )


@pytest.mark.parametrize("output_format", ["ZIP", "PDF", "XLSX"])
def test_original_bytes_and_bound_provenance(output_format: str) -> None:
    bound = binding(output_format)
    payloads = {
        "reports/contract_sample.pdf": b"original PDF",
        "reports/contract_sample.xlsx": b"original workbook",
    }
    archive = build(tuple(PackFile(path, content) for path, content in payloads.items()))
    output = select_output(bound, archive.content, archive.manifest_sha256)
    expected = (
        archive.content
        if output_format == "ZIP"
        else payloads[f"reports/contract_sample.{output_format.lower()}"]
    )
    assert output.content == expected
    assert output.sha256 == hashlib.sha256(expected).hexdigest()
    provenance = json.loads(output.manifest)
    assert provenance["source"] == bound.model_dump(mode="json")
    assert provenance["pack_manifest_sha256"] == archive.manifest_sha256
    assert provenance["sha256"] == output.sha256


def test_missing_chapter_and_corrupt_archive_are_refused() -> None:
    archive = build((PackFile("source.json", b"{}"),))
    with pytest.raises(Problem):
        select_output(binding("PDF"), archive.content, archive.manifest_sha256)
    with pytest.raises(Problem):
        select_output(binding(), archive.content, "f" * 64)


def test_inconsistent_catalogue_kind_is_refused() -> None:
    values = binding().model_dump()
    values["report_code"] = "period_evidence_pack"
    with pytest.raises(ValidationError):
        CatalogueEvidence.model_validate(values)
