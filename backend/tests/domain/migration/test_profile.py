"""LMG-1 legacy database profiling and read-only source handling, the pure part (BUILD_SPEC LMG-1
``test_profile_shipped_step04_database``, ``test_source_read_only_from_copy``; 04 T-MIG-01
``profile``, T-MIG-02; ENGINE_SPEC S07-R-11; REQ-MIG-004; PRD J-20.1, J-20-ALT-2, WLD-F-15,
WLD-F-35; DG-LAY-11).

The shipped fixture is a file opened read-only (``mode=ro&immutable=1``); no database server, no
tenant (the migration batch row, the job and the routes are the database slice). No database.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import MappingProxyType

import pytest
from erev_api.domain.migration import legacy_db
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.problems import Problem
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
SHIPPED_SHA256 = "6e35b508218420c670f3f19d0fb1df83b32ff498bb45e6bd47df68cbdf1aafc2"


def test_profile_shipped_step04_database() -> None:
    # PRD J-20.1: Contract_Live 24; contracts 4; legacy POB rows 16; SKU_SSP 7; SSP versions
    # 2023-01-01; entities Mock Entity 1 and 2; latest Current Period 31 Jan 2023 (the period of the
    # latest processed version, legacy 01 §4.3).
    profile = legacy_db.profile(FIXTURE)
    assert profile.source_sha256 == SHIPPED_SHA256
    assert profile.tables == {"Contract_Live": 24, "SKU_SSP": 7}
    assert (profile.contract_live_rows, profile.contracts, profile.legacy_pob_rows) == (24, 4, 16)
    assert profile.sku_ssp_rows == 7
    assert profile.ssp_versions == ("2023-01-01",)
    assert profile.selling_entities == ("Mock Entity 1", "Mock Entity 2")
    assert profile.latest_current_period == date(2023, 1, 31)
    assert len(profile.version_tokens) == 3
    assert [column.name for column in profile.columns][:3] == [
        "Contract Unique Name",
        "POB Unique ID",
        "SKU Name",
    ]
    assert len(profile.columns) == 71
    as_json = profile.as_json()
    assert as_json["latest_current_period"] == "2023-01-31"
    assert as_json["columns"][0] == ["Contract Unique Name", "TEXT"]


def test_profile_binds_the_sku_ssp_digest_findings_and_keys() -> None:
    """04 rev 1.72 (D-98 133 AMENDMENT 4): the PROFILE carries what the MIGRATION_SSP_REPLAY request
    binds — the canonical SKU_SSP digest, the LM-SSP-01..09 row findings (none on the shipped file)
    and
    the (label, SKU, stratification) keys; the digest is a pure function of the rows."""
    profile = legacy_db.profile(FIXTURE)
    ssp = legacy_db.sku_ssp_rows(FIXTURE)
    assert len(profile.sku_ssp_sha256) == 64 and profile.sku_ssp_sha256 == legacy_db.sku_ssp_digest(
        ssp
    )
    assert profile.sku_ssp_findings == ()
    assert len(profile.sku_ssp_keys) == 7 and profile.sku_ssp_keys[0] == (
        "2023-01-01",
        "Consulting 1",
        "Consulting 1",
    )
    assert ("2023-01-01", "Variable Consideration", "VC") in profile.sku_ssp_keys
    as_json = profile.as_json()
    assert as_json["sku_ssp_sha256"] == profile.sku_ssp_sha256 and as_json["sku_ssp_findings"] == []
    assert as_json["sku_ssp_keys"][0] == ["2023-01-01", "Consulting 1", "Consulting 1"]
    # a changed row changes the digest (the import re-verifies it over the spooled source)
    changed = (*ssp[:-1], {**ssp[-1], "SKU Unit List Price": "1"})
    assert legacy_db.sku_ssp_digest(changed) != profile.sku_ssp_sha256


def test_sku_ssp_findings_type_the_rows_as_the_legacy_template_does() -> None:
    """A bad flag, a non-numeric price and a blank required cell are named by row and column with
    the template's codes (LM-SSP-03 / LM-SSP-04 / LM-SSP-06); a clean row yields nothing."""
    clean = {
        "SKU Unique ID": "1",
        "SKU Name": "Hardware 1",
        "Distinct or Nondistinct": "Distinct",
        "SKU Unit List Price": "100",
        "ASC 606 Stratification": "Hardware 1",
        "Midpoint Discount Percentage": "0.1",
        "SSP Range Method (+-)": "0.15",
        "SSP Version": "2023-01-01",
        "Revenue Account": "5001",
    }
    assert legacy_db.sku_ssp_findings((clean,)) == []
    bad = {
        **clean,
        "Distinct or Nondistinct": "Maybe",
        "SKU Unit List Price": "abc",
        "SSP Version": None,
    }
    found = legacy_db.sku_ssp_findings((clean, bad))
    assert [(f["row"], f["code"], f["column"]) for f in found] == [
        (2, "VALUE_NOT_NUMERIC", "SKU Unit List Price"),
        (2, "REQUIRED_VALUE_BLANK", "SSP Version"),
        (2, "SSP_DISTINCT_FLAG_INVALID", "Distinct or Nondistinct"),
    ]
    over = {**clean, "Midpoint Discount Percentage": "1.5"}
    assert [f["code"] for f in legacy_db.sku_ssp_findings((over,))] == ["SSP_PERCENT_OUT_OF_RANGE"]


def test_source_read_only_from_copy() -> None:
    # REQ-MIG-004 / J-20-AC-2: the reader opens the immutable read-only URI and the file's SHA-256
    # is unchanged after profiling and reading every row.
    uri = legacy_db.read_only_uri(FIXTURE)
    assert uri.startswith("file:") and uri.endswith("?mode=ro&immutable=1")
    before = legacy_db.file_sha256(FIXTURE)
    legacy_db.profile(FIXTURE)
    rows = legacy_db.rows(FIXTURE)
    legacy_db.sku_ssp_rows(FIXTURE)
    assert legacy_db.file_sha256(FIXTURE) == before == SHIPPED_SHA256
    assert len(rows) == 24


def test_not_a_legacy_database(tmp_path: Path) -> None:
    # PRD J-20-ALT-2 / ERR-20: a SQLite file without Contract_Live (WLD-F-35 shape). A zero-length
    # file is a valid, empty SQLite database (no tables); a file of other bytes is no database at
    # all. Neither test builds a database here: sqlite3 stays inside domain/migration (DG-ARC-05).
    other = tmp_path / "not-a-legacy-db.sqlite"
    other.write_bytes(b"")
    with pytest.raises(Problem) as refused:
        legacy_db.recognise(other)
    assert refused.value.slug == "legacy-database-unrecognized"
    assert refused.value.status == 422
    assert refused.value.detail == legacy_db.UNRECOGNISED_DETAIL
    with pytest.raises(Problem):
        legacy_db.profile(other)
    garbage = tmp_path / "garbage.sqlite"
    garbage.write_bytes(b"not a database")
    with pytest.raises(Problem):
        legacy_db.recognise(garbage)


def test_rows_carry_the_71_columns_as_stored_text() -> None:
    rows = legacy_db.rows(FIXTURE)
    first = rows[0]
    assert first.source_rowid == 1
    assert len(first.values) == 71
    assert first.contract_external_id == "Contract 1"
    assert first.record_unique_id.startswith(first.processing_time_log)
    assert first.record_key in first.record_unique_id
    assert len(first.sha256) == 64 and int(first.sha256, 16) >= 0
    # integers as digits, reals as their shortest round-trip decimal, text as is
    assert first.values["Deferred Revenue Account"] == "21001"
    assert first.values["Original POB Total Selling Price"] == "500"
    assert first.values["Selling Entity"] == "Mock Entity 1"
    assert legacy_db.text_of(500) == "500"
    assert legacy_db.text_of(322.10109018830525) == "322.10109018830525"
    assert legacy_db.text_of(None) is None
    assert legacy_db.text_of("text") == "text"
    assert legacy_db.decimal_of("322.10109018830525") is not None
    assert legacy_db.parse_period("2023-01-31 00:00:00") == date(2023, 1, 31)


def test_latest_version_per_record() -> None:
    # S07-R-11 / legacy 01 §4.3: 16 latest rows (14 obligations, 2 VC rows), one per record key.
    rows = legacy_db.rows(FIXTURE)
    latest = legacy_db.latest_rows(rows)
    assert len(latest) == 16
    assert len({row.record_key for row in latest}) == 16
    vc = [row for row in latest if row.values["ASC 606 Stratification"] == "VC"]
    assert len(vc) == 2
    # the later processing time wins; among equal times the greater rowid wins
    older = LegacyRow(
        1,
        MappingProxyType(
            {
                "Record Unique ID without time": "K",
                "Processing Time Log": "2025-05-09 09:11:44.708286",
            }
        ),
    )
    newer = LegacyRow(
        2,
        MappingProxyType(
            {
                "Record Unique ID without time": "K",
                "Processing Time Log": "2025-05-09 09:12:33.441992",
            }
        ),
    )
    duplicate = LegacyRow(
        3,
        MappingProxyType(
            {
                "Record Unique ID without time": "K",
                "Processing Time Log": "2025-05-09 09:12:33.441992",
            }
        ),
    )
    assert legacy_db.latest_rows([newer, older]) == (newer,)
    assert legacy_db.latest_rows([duplicate, newer, older]) == (duplicate,)


def test_load_legacy_rows_is_the_plain_row_view() -> None:
    loaded = legacy_db.load_legacy_rows(FIXTURE)
    assert len(loaded) == 24 and all(len(row) == 71 for row in loaded)
    assert loaded[0] == legacy_db.rows(FIXTURE)[0].values


def test_sku_ssp_rows() -> None:
    ssp = legacy_db.sku_ssp_rows(FIXTURE)
    assert len(ssp) == 7
    assert set(ssp[0]) == {
        "SKU Unique ID",
        "SKU Name",
        "Distinct or Nondistinct",
        "SKU Unit List Price",
        "ASC 606 Stratification",
        "Midpoint Discount Percentage",
        "SSP Range Method (+-)",
        "SSP Version",
        "Revenue Account",
    }
    assert {row["SSP Version"] for row in ssp} == {"2023-01-01"}
