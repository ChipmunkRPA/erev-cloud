"""Final assembly guards over synthetic files; actual evidence is covered by the DB witness."""

from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_archive import PackFile, verify
from erev_api.domain.reports.evidence_assembly import REQUIRED_PATHS, checked_archive
from erev_api.problems import Problem

FILES = tuple(PackFile(path, b"synthetic assembly fixture\n") for path in sorted(REQUIRED_PATHS))


@pytest.mark.parametrize(
    "missing",
    [
        "certification.json",
        "lock/snapshots.json",
        "lock/approvals.json",
        "lock/source_binding.json",
        "journals/batch_register.json",
        "journals/je_population.csv",
        "reconciliations/index.json",
        "reconciliations/population.json",
        "reports/contract_balance_rollforward.csv",
        "reports/rpo_rollforward.csv",
        "reports/rpo.csv",
        "reports/disaggregation.csv",
        "registers/late_entries.csv",
        "registers/out_of_period.csv",
        "registers/config_change_register.csv",
        "registers/ssp_change_log.csv",
        "access/user_access_listing.csv",
        "access/sod_conflict_report.csv",
        "audit/chain_digest.json",
    ],
)
def test_missing_required_evidence_never_becomes_a_zip(missing: str) -> None:
    assert missing in {file.path for file in FILES}
    with pytest.raises(Problem, match="missing required"):
        checked_archive([file for file in FILES if file.path != missing], report_run_ids=set())


def test_archive_is_deterministic_and_every_payload_has_a_manifest_hash() -> None:
    archive = checked_archive(FILES, report_run_ids=set())
    assert checked_archive(list(reversed(FILES)), report_run_ids=set()) == archive
    manifest = verify(archive.content, expected_manifest_sha256=archive.manifest_sha256)
    assert {row["path"] for row in manifest["files"]} == {file.path for file in FILES}


@pytest.mark.parametrize(
    "reported,expected", [(None, {UUID(int=1)}), (UUID(int=1), set()), (UUID(int=1), {UUID(int=2)})]
)
def test_report_population_must_match_the_binding(
    reported: UUID | None, expected: set[UUID]
) -> None:
    files = [*FILES, PackFile("reports/extra.csv", b"data", report_run_id=reported)]
    with pytest.raises(Problem, match="report population differs"):
        checked_archive(files, report_run_ids=expected)


@pytest.mark.parametrize("extra", [FILES[0], PackFile("../outside.json", b"data")])
def test_invalid_archive_cannot_escape_as_a_partial_success(extra: PackFile) -> None:
    with pytest.raises(Problem, match="cannot be assembled"):
        checked_archive([*FILES, extra], report_run_ids=set())
