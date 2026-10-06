"""LMG-2 legacy field mapping, the pure part (BUILD_SPEC LMG-2 ``test_legacy_field_mapping``,
``test_batch_parameters_forced_values``, ``test_entity_mapping_creates_missing_entities``
mapping statuses; 04 §17.2 LM-CL-01 to LM-CL-71; POLICIES POL-211 to POL-214; REQ-MIG-006;
legacy 01 PAR-04).

Rows come from the shipped fixture WLD-F-15 and from the golden step 13 replay output
(``docs/legacy/golden/13-…/contract_live.csv``, the material-right convention). No database.
"""

from __future__ import annotations

import csv
import dataclasses
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import pytest
from erev_api.domain.migration import field_mapping, legacy_db, opening_balances
from erev_api.domain.migration.field_mapping import BatchParameters, LegacyRow
from erev_api.domain.reports import legacy_columns
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
STEP_13 = (
    ROOT
    / "docs/legacy/golden/13-prospective-mod-2023-09-15-material-right-new-pob/contract_live.csv"
)


def _latest() -> tuple[LegacyRow, ...]:
    return legacy_db.latest_rows(legacy_db.rows(FIXTURE))


def _csv_row(path: object, contract: str, pob: str, token: str, rowid: int) -> LegacyRow:
    with open(str(path), newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            if (
                record["Contract Unique Name"] == contract
                and record["POB Unique ID"] == pob
                and record["Processing Time Log"] == token
            ):
                return LegacyRow(
                    rowid,
                    MappingProxyType({k: (v if v != "" else None) for k, v in record.items()}),
                )
    raise AssertionError(f"{contract} {pob} {token} not in {path}")


def _synthetic_row(
    key: str = "P1",
    rowid: int = 1,
    token: str = "2026-01-02 09:00:00",
    period: str = "2026-01-01",
    **updates: str,
) -> LegacyRow:
    """The synthetic ``Contract_Live`` row of Codex's ed5173f probe (``row()`` there), verbatim
    defaults: a Distinct service line, quantity 10 at list price 100, opening columns 0 then the
    stated current values; ``updates`` override columns by legacy name."""
    values: dict[str, str | None] = {c.name: None for c in legacy_columns.CONTRACT_LIVE}
    values.update(
        {
            legacy_db.CONTRACT: "SYN-C1",
            legacy_db.POB: key,
            legacy_db.SKU: "SYN-SKU",
            legacy_db.STRATIFICATION: "Service",
            legacy_db.SELLING_ENTITY: "ENTITY-Z",
            legacy_db.SSP_VERSION: "2026-01-01",
            legacy_db.CURRENT_PERIOD: period,
            legacy_db.PROCESSING_TIME_LOG: token,
            legacy_db.RECORD_KEY: "SYN-C1/" + key,
            legacy_db.RECORD_UNIQUE_ID: token + " SYN-C1/" + key,
            "Distinct or Nondistinct": "Distinct",
            "Original POB Total Selling Price": "1000",
            "Original POB Total Qty": "10",
            "POB Start Date": "2026-01-01",
            "POB End Date": "2026-12-31",
            "SKU Unit List Price": "100",
            "Midpoint Discount Percentage": "0",
            "SSP Range Method (+-)": "0",
            "Original Total Contract Price": "900",
            "Original Allocation": "1000",
            "Original Extended SSP": "1000",
            "Deferred Revenue Account": "2100",
            "Unbilled A/R Account": "1300",
            "Revenue Account": "4000",
        }
    )
    for column in opening_balances.OPENING_COLUMNS.values():
        values[column] = "0"
    values.update(
        {
            "Current Remaining Qty": "8",
            "Current Remaining SSP": "800",
            "Current Remaining Allocation": "800",
            "Current Remaining Billing": "750",
            "Current Unit SSP": "100",
            "Current Remaining Unit Rev Rec": "100",
            "Current Delivery - Cumulative": "2",
            "Current Rev Rec - Cumulative": "200",
            "Current Billing - Cumulative": "250",
            "Current SSP Delivered - Cumulative": "200",
            "Current Contract Position - POB": "50",
            "Current Contract Position - Contract Level": "70",
        }
    )
    values.update(updates)
    return LegacyRow(rowid, MappingProxyType(values))


# Codex's material-right row: the legacy convention (list price 1, discount 0, range 0, stated
# price 0) with quantity 25 = the option's SSP in dollars, a Nondistinct line.
CODEX_MATERIAL_RIGHT: dict[str, str] = {
    "Distinct or Nondistinct": "Nondistinct",
    "Original POB Total Selling Price": "0",
    "Original POB Total Qty": "25",
    "SKU Unit List Price": "1",
    "Original Total Contract Price": "25",
    "Original Allocation": "25",
    "Original Extended SSP": "25",
    "Current Remaining Qty": "25",
    "Current Remaining Allocation": "25",
    "Current Rev Rec - Cumulative": "0",
    "Current Delivery - Cumulative": "0",
}
CUTOVER = date(2026, 1, 31)


def test_legacy_field_mapping() -> None:
    # REQ-MIG-006 over the WLD-F-15 rows: stratification → revenue category, VC rows → VC_LINE
    # (LM-CL-06; POL-213); Distinct/Nondistinct → distinctness (LM-CL-18); Selling Entity → entity
    # (LM-CL-09); accounts → overrides (LM-CL-11, -12, -22); SSP Version → label of LEGACY-SKU-SSP
    # (LM-CL-10); the seeded parity templates (T-MIG-01 note).
    mapped = [field_mapping.map_row(row) for row in _latest()]
    assert Counter(item.template_code for item in mapped) == {
        "LEGACY-DISTINCT": 8,
        "LEGACY-NONDISTINCT": 4,
        "LEGACY-MATERIAL-RIGHT": 2,
        "LEGACY-VC": 2,
    }
    assert Counter(item.obligation_kind for item in mapped) == {
        "STANDARD": 12,
        "MATERIAL_RIGHT": 2,
        "VC_LINE": 2,
    }
    vc = [item for item in mapped if item.stratification == "VC"]
    assert all(
        item.obligation_kind == "VC_LINE" and item.template_code == "LEGACY-VC" for item in vc
    )
    assert {item.distinctness for item in mapped} == {"distinct", "nondistinct"}
    assert {item.entity_code for item in mapped} == {"Mock Entity 1", "Mock Entity 2"}
    assert {item.ssp_version_label for item in mapped} == {"2023-01-01"}
    assert {item.ssp_book for item in mapped} == {"LEGACY-SKU-SSP"}
    first = next(item for item in mapped if item.contract_external_id == "Contract 1")
    assert first.account_overrides == {
        "CONTRACT_ASSET": "15001",
        "CONTRACT_LIABILITY": "21001",
        "REVENUE": "5001",
        "UNBILLED_RECEIVABLE": "15001",
    }
    assert first.quantity == Decimal(5) and first.stated_price == Decimal(500)
    assert first.start_date is not None and first.end_date is not None


def test_material_right_row_maps_to_the_parity_template() -> None:
    # Golden step 13, Contract 3 POB #4 "Material Right - Services": L = 1, d = 0, r = 0, stated
    # price 0, quantity = SSP dollars (legacy 01 PAR-04) → LEGACY-MATERIAL-RIGHT under POL-212
    # KEEP_QUANTITY_CONVENTION; under CONVERT_TO_OPTION_RECORD the row is the option record
    # (POLICIES POL-212: option SSP = quantity × 1 as ENTERED_AMOUNT, quantity 1) — corrected
    # docs-first after Codex R2, which found the earlier expectation (a plain nondistinct line)
    # contrary to the policy text.
    row = _csv_row(STEP_13, "Contract 3", "POB #4", "step-13", 1)
    assert field_mapping.is_material_right(row)
    keep = field_mapping.map_row(
        row, BatchParameters(material_right_convention="KEEP_QUANTITY_CONVENTION")
    )
    assert (keep.template_code, keep.obligation_kind) == ("LEGACY-MATERIAL-RIGHT", "MATERIAL_RIGHT")
    assert keep.quantity == Decimal(1000) and keep.stated_price == Decimal(0)
    convert = field_mapping.map_row(
        row, BatchParameters(material_right_convention="CONVERT_TO_OPTION_RECORD")
    )
    assert (convert.template_code, convert.obligation_kind) == (
        "LEGACY-MATERIAL-RIGHT",
        "MATERIAL_RIGHT",
    )
    assert convert.quantity == Decimal(1) and convert.stated_price == Decimal(0)
    assert convert.option is not None
    assert (convert.option.ssp_method, convert.option.option_ssp) == (
        "ENTERED_AMOUNT",
        Decimal(1000),
    )
    ordinary = _csv_row(STEP_13, "Contract 3", "POB #1", "step-13", 2)
    assert not field_mapping.is_material_right(ordinary)


def test_material_right_conversion_to_option_record() -> None:
    # Codex R2 (PRODUCTION-F-LMG-SLICE1-INDEPENDENT-ed5173f, D-98 candidate 44), exact inputs: on
    # ed5173f the accepted CONVERT_TO_OPTION_RECORD choice mapped this row to STANDARD /
    # LEGACY-NONDISTINCT with quantity 25 and the booking payload emitted quantity "25". POL-212:
    # option SSP = quantity × 1 as ENTERED_AMOUNT (POL-026), quantity 1, exercise per POL-028.
    mr = _synthetic_row("MR", 7, **CODEX_MATERIAL_RIGHT)
    assert field_mapping.is_material_right(mr)
    convert_params = BatchParameters(material_right_convention="CONVERT_TO_OPTION_RECORD")
    assert field_mapping.validate_batch_parameters(convert_params.as_mapping()) == []
    keep = field_mapping.map_row(
        mr, BatchParameters(material_right_convention="KEEP_QUANTITY_CONVENTION")
    )
    assert (keep.obligation_kind, keep.quantity) == (
        "MATERIAL_RIGHT",
        Decimal(25),
    )  # positive stays
    convert = field_mapping.map_row(mr, convert_params)
    assert convert.obligation_kind == "MATERIAL_RIGHT"
    assert convert.quantity == Decimal(1)
    staged = opening_balances.stage([mr], CUTOVER, convert_params)
    booking = opening_balances.booking_payload(staged.contracts[0])
    assert booking["lines"][0]["quantity"] == "1"
    # the option record carried with the staging (04 T-CON-14 terms; ENGINE_SPEC S03-R-07)
    option = convert.option
    assert option is not None
    assert (
        option.ssp_method,
        option.option_ssp,
        option.quantity,
        option.is_legacy_quantity_ssp_dollars,
        option.source_quantity,
    ) == ("ENTERED_AMOUNT", Decimal(25), Decimal(1), False, Decimal(25))
    assert option.exercise_policy == "material_right.exercise"  # POL-028, the tenant's value
    assert convert.template_code == "LEGACY-MATERIAL-RIGHT" and convert.pending is None
    records = opening_balances.option_records(staged.contracts[0])
    assert records == [
        {
            "obligation_key": "MR",
            "product_code": "SYN-SKU",
            "ssp_method": "ENTERED_AMOUNT",
            "option_ssp": "25",
            "quantity": "1",
            "exercise_policy": "material_right.exercise",
            "is_legacy_quantity_ssp_dollars": False,
            "source_quantity": "25",
            "ssp_book": "LEGACY-SKU-SSP",
            "ssp_version_label": "2026-01-01",
        }
    ]
    assert staged.option_records == tuple(records)
    assert (
        opening_balances.option_records(opening_balances.stage([mr], CUTOVER).contracts[0]) == []
    )  # keep-convention default: no option record


def test_nondistinct_mapping_choices_do_not_collapse() -> None:
    # Codex R2 observation: on ed5173f the three POL-211 literals produced identical outputs and
    # map_row never read nondistinct_mapping. SINGLE_POB books one STANDARD obligation; SERIES is
    # a series row pending its series_increment_unit (ENGINE_SPEC S03-R-06); REVIEW_QUEUE is
    # pending the questionnaire before commit (POL-211). No queue schema is invented.
    nd = _synthetic_row("ND", 8, **{"Distinct or Nondistinct": "Nondistinct"})
    outputs = {
        mode: field_mapping.map_row(nd, BatchParameters(nondistinct_mapping=mode))
        for mode in field_mapping.NONDISTINCT_OPTIONS
    }
    serialised = {
        json.dumps(dataclasses.asdict(item), default=str, sort_keys=True)
        for item in outputs.values()
    }
    assert len(serialised) == 3
    single = outputs["SINGLE_POB"]
    assert (single.obligation_kind, single.template_code, single.distinctness, single.pending) == (
        "STANDARD",
        "LEGACY-NONDISTINCT",
        "nondistinct",
        None,
    )
    series = outputs["SERIES"]
    assert series.distinctness == "series" and series.pending is not None
    assert (series.pending.rule_id, series.pending.choice) == ("POL-211", "SERIES")
    assert "series_increment_unit" in series.pending.reason
    queue = outputs["REVIEW_QUEUE"]
    assert queue.pending is not None and queue.pending.choice == "REVIEW_QUEUE"
    assert "questionnaire" in queue.pending.reason and queue.distinctness == "nondistinct"
    # a Distinct row is untouched by POL-211
    distinct = {
        json.dumps(
            dataclasses.asdict(
                field_mapping.map_row(_synthetic_row(), BatchParameters(nondistinct_mapping=mode))
            ),
            default=str,
            sort_keys=True,
        )
        for mode in field_mapping.NONDISTINCT_OPTIONS
    }
    assert len(distinct) == 1
    # the staging lists the pending row and refuses the booking payload until it is resolved
    staged = opening_balances.stage(
        [nd], CUTOVER, BatchParameters(nondistinct_mapping="REVIEW_QUEUE")
    )
    assert [(c, k, d.choice) for c, k, d in staged.pending] == [("SYN-C1", "ND", "REVIEW_QUEUE")]
    with pytest.raises(ValueError, match="ND"):
        opening_balances.booking_payload(staged.contracts[0])
    booked = opening_balances.stage([nd], CUTOVER)  # SINGLE_POB default books
    assert booked.pending == ()
    assert opening_balances.booking_payload(booked.contracts[0])["lines"][0]["quantity"] == "10"


def test_field_mapping_table_covers_the_71_columns() -> None:
    table = field_mapping.FIELD_MAPPING
    assert [item.id for item in table] == [f"LM-CL-{n:02d}" for n in range(1, 72)]
    assert [item.legacy for item in table] == [
        column.name for column in legacy_columns.CONTRACT_LIVE
    ]
    rules = {item.id: item.rule for item in table}
    assert rules["LM-CL-06"] == "STRATIFICATION"
    assert rules["LM-CL-09"] == "ENTITY"
    assert rules["LM-CL-10"] == "SSP_VERSION"
    assert {rules["LM-CL-11"], rules["LM-CL-12"], rules["LM-CL-22"]} == {"ACCOUNT"}
    assert rules["LM-CL-18"] == "DISTINCTNESS"
    assert rules["LM-CL-69"] == "EXCLUDED" and rules["LM-CL-71"] == "DERIVED"
    assert all(item.rule == "PREVIOUS" for item in table[31:47])


def test_batch_parameters_forced_values() -> None:
    # POL-213 and POL-214 are FORCED; POL-211 accepts SINGLE_POB (and its other literals).
    forced = field_mapping.FORCED_PARAMETERS
    assert forced == {
        "migration.legacy_vc_rows": "VC_ELEMENT_PLUS_CREDIT_EVENTS",
        "migration.split_upload_allocation": "ALLOCATE_ACROSS_ALL_POBS",
    }
    assert (
        field_mapping.validate_batch_parameters({"migration.nondistinct_mapping": "SINGLE_POB"})
        == []
    )
    assert field_mapping.validate_batch_parameters(BatchParameters().as_mapping()) == []
    errors = field_mapping.validate_batch_parameters(
        {
            "migration.legacy_vc_rows": "POB_PER_ROW",
            "migration.split_upload_allocation": "PER_UPLOAD",
            "migration.nondistinct_mapping": "BOGUS",
            "migration.other": "x",
        }
    )
    assert [(error.field, error.rule_id) for error in errors] == [
        ("batch_parameters.migration.legacy_vc_rows", "POL-213"),
        ("batch_parameters.migration.nondistinct_mapping", "POL-211"),
        ("batch_parameters.migration.other", "T-IMP-02"),
        ("batch_parameters.migration.split_upload_allocation", "POL-214"),
    ]
    assert "cannot be changed" in errors[0].message


def test_entity_mapping_statuses() -> None:
    mapping = field_mapping.entity_mapping(_latest(), existing_codes={"Mock Entity 1"})
    assert [(item.legacy_name, item.entity_code, item.status) for item in mapping] == [
        ("Mock Entity 1", "Mock Entity 1", "Matched"),
        ("Mock Entity 2", "Mock Entity 2", "Will be created"),
    ]
