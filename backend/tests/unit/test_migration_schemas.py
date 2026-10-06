"""API-R-48 migration schemas (04 §15.3 API-R-48; T-MIG-01 to T-MIG-03; BUILD_SPEC LMG-1 to LMG-4;
F-LMG record §2): the request and response contracts validate their examples and refuse the
wrong shape. No database, no routes.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from erev_api.schemas import migrations
from pydantic import TypeAdapter, ValidationError

FILE = uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_create_and_submit_bodies() -> None:
    body = migrations.MigrationCreateIn.model_validate(
        {"mode": "REPLAY", "source_file_id": str(FILE)}
    )
    assert body.mode == "REPLAY" and body.source_file_id == FILE
    with pytest.raises(ValidationError):
        migrations.MigrationCreateIn.model_validate(
            {"mode": "SOMETHING", "source_file_id": str(FILE)}
        )
    with pytest.raises(ValidationError):
        migrations.MigrationCreateIn.model_validate(
            {"mode": "REPLAY", "source_file_id": str(FILE), "extra": 1}
        )
    assert migrations.MigrationSubmitIn.model_validate({}).comment is None


def test_import_body_is_discriminated_on_mode() -> None:
    adapter: TypeAdapter[migrations.OpeningBalancesImportIn | migrations.ReplayImportIn] = (
        TypeAdapter(migrations.MigrationImportIn)
    )
    opening = adapter.validate_python(
        {
            "mode": "OPENING_BALANCES",
            "cutover_date": "2023-01-31",
            "entity_mapping": [{"legacy_name": "Mock Entity 2", "entity_code": "Mock Entity 2"}],
            "batch_parameters": {"migration.nondistinct_mapping": "SINGLE_POB"},
        }
    )
    assert isinstance(opening, migrations.OpeningBalancesImportIn)
    assert opening.cutover_date == date(2023, 1, 31) and opening.create_missing_entities is True
    replay = adapter.validate_python(
        {
            "mode": "REPLAY",
            "plan": [
                {
                    "file_id": str(FILE),
                    "file_name": "SKU SSP Template.xlsx",
                    "template_code": "legacy_sku_ssp",
                },
                {
                    "file_id": str(FILE),
                    "file_name": "Contract Modification Template 05.15.2023 - retrospective.xlsx",
                    "template_code": "legacy_contract_modification",
                    "mode": "retrospective",
                    "effective_date": "2023-05-15",
                },
            ],
        }
    )
    assert isinstance(replay, migrations.ReplayImportIn)
    assert [item.template_code for item in replay.plan] == [
        "legacy_sku_ssp",
        "legacy_contract_modification",
    ]
    assert replay.plan[1].mode == "retrospective" and replay.plan[1].effective_date == date(
        2023, 5, 15
    )
    with pytest.raises(ValidationError):
        adapter.validate_python({"mode": "REPLAY", "cutover_date": "2023-01-31"})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "mode": "REPLAY",
                "plan": [{"file_id": str(FILE), "file_name": "x", "template_code": "csv_v2"}],
            }
        )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "mode": "REPLAY",
                "plan": [
                    {
                        "file_id": str(FILE),
                        "file_name": "x",
                        "template_code": "legacy_contract_modification",
                        "mode": "sideways",
                    }
                ],
            }
        )


def test_reconciliation_line_and_legacy_row_outputs() -> None:
    line = migrations.MigrationReconciliationLineOut.model_validate(
        {
            "contract_external_id": "Contract 1",
            "obligation_key": None,
            "measure": "TRANSACTION_PRICE",
            "source_value": "1300",
            "erev_value": "1300.00",
            "difference": "0",
            "is_within_tolerance": True,
        }
    )
    assert line.tolerance == "0.0001" and line.deviation_ref is None
    with pytest.raises(ValidationError):
        migrations.MigrationReconciliationLineOut.model_validate(
            {
                "contract_external_id": "Contract 1",
                "obligation_key": None,
                "measure": "TRANSACTION_PRICE",
                "source_value": "1e3",
                "erev_value": "1300",
                "difference": "0",
                "is_within_tolerance": True,
            }
        )
    row = migrations.MigratedLegacyRowOut.model_validate(
        {
            "source_rowid": 1,
            "contract_external_id": "Contract 1",
            "obligation_key": "POB #1",
            "product_code": "Hardware 1",
            "current_period": "2023-01-01",
            "processing_time_log": "2025-05-09 09:11:44.708286",
            "record_unique_id": "2025-05-09 09:11:44.708286 Contract 1 POB #1 Hardware 1",
            "legacy_row": {"Contract Unique Name": "Contract 1"},
            "legacy_row_sha256": "0" * 64,
        }
    )
    assert row.label == "migrated, unattributed" and row.contract_id is None
    with pytest.raises(ValidationError):
        migrations.MigratedLegacyRowOut.model_validate({**row.model_dump(), "label": "attributed"})


def test_profile_output_round_trip() -> None:
    profile = migrations.MigrationProfileOut.model_validate(
        {
            "source_sha256": "6e35b508218420c670f3f19d0fb1df83b32ff498bb45e6bd47df68cbdf1aafc2",
            "tables": {"Contract_Live": 24, "SKU_SSP": 7},
            "contract_live_rows": 24,
            "contracts": 4,
            "legacy_pob_rows": 16,
            "sku_ssp_rows": 7,
            "ssp_versions": ["2023-01-01"],
            "selling_entities": ["Mock Entity 1", "Mock Entity 2"],
            "latest_current_period": "2023-01-31",
            "version_tokens": ["a", "b", "c"],
        }
    )
    assert profile.latest_current_period == date(2023, 1, 31)
    assert profile.model_dump()["tables"] == {"Contract_Live": 24, "SKU_SSP": 7}
