"""LMG-4 replay plan contract, the pure part (BUILD_SPEC LMG-4 ``test_plan_validation`` copies;
GPB-3 after-step-04 checkpoint; ENGINE_SPEC S07-R-12; legacy 07 §3; SCREENS_B §10.3 "Plan"; PRD
J-21.1, J-21.2; F-LMG record §4).

The required plan length is derived from the reference database: the shipped step-04 database
requires 4 files (GPB-3), the after-step-14 output 14 (LMG-4, J-21). Template inference is
checked against every golden ``step.json`` handler. Committing the batches, the sandbox and
promotion are the database slice. No database.
"""

from __future__ import annotations

import csv
import dataclasses
import json
from datetime import date
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest
from erev_api.domain.migration import legacy_db, replay
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.domain.migration.replay import PlanItem
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
GOLDEN = ROOT / "docs/legacy/golden"
STEP_14 = GOLDEN / "14-full-delivery-2023-10-31/contract_live.csv"
# legacy 07 §3 handler (the golden ``step.json`` ``handler``) → (template code, E-24 mode); this
# lane's own table — no import from the parity support (T1's files), which keeps the same six rows.
HANDLERS: dict[str, tuple[str, str | None]] = {
    "browse_file_SSPs": ("legacy_sku_ssp", None),
    "browse_file_Contracts": ("legacy_contract_setup", None),
    "browse_file_Deliveries": ("legacy_progress_tracking", None),
    "browse_file_ProsMod": ("legacy_contract_modification", "prospective"),
    "browse_file_RetroMod": ("legacy_contract_modification", "retrospective"),
    "browse_file_POB_specific_VC": ("legacy_contract_modification", "pob_price_change"),
}


def _steps() -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for path in sorted(GOLDEN.glob("[0-9][0-9]-*/step.json")):
        step = json.loads(path.read_text(encoding="utf-8"))
        if step["nn"] != "00":
            found.append(step)
    return found


def _plan(
    steps: list[dict[str, object]], *, dated: bool = True, with_mode: bool = True
) -> list[PlanItem]:
    items: list[PlanItem] = []
    for step in steps:
        name = Path(str(step["file"])).name
        template, mode = replay.infer_template(name)
        date_input = step.get("date_input")
        items.append(
            PlanItem(
                file_name=name,
                template_code=template,
                mode=mode if with_mode else None,
                effective_date=date.fromisoformat(str(date_input))
                if dated and date_input
                else None,
            )
        )
    return items


def test_infer_template_matches_every_golden_handler() -> None:
    for step in _steps():
        expected = HANDLERS[str(step["handler"])]
        assert replay.infer_template(Path(str(step["file"])).name) == expected, step["nn"]
    with pytest.raises(ValueError):
        replay.infer_template("Unrelated.xlsx")


def test_required_files_from_the_reference_database() -> None:
    # F-LMG record §4: one SSP file plus one file per Contract_Live version token.
    shipped = legacy_db.profile(FIXTURE)
    assert replay.required_files(shipped) == 4
    checkpoint = replay.checkpoint(shipped)
    assert checkpoint.reconcile_after == 4 and checkpoint.has_sku_ssp
    assert len(checkpoint.reference_versions) == 3
    with STEP_14.open(newline="", encoding="utf-8") as handle:
        tokens = sorted({record["Processing Time Log"] for record in csv.DictReader(handle)})
    after_14 = dataclasses.replace(shipped, version_tokens=tuple(tokens))
    assert len(tokens) == 13
    assert replay.required_files(after_14) == 14
    no_ssp = dataclasses.replace(shipped, sku_ssp_rows=0)
    assert replay.required_files(no_ssp) == 3


def test_plan_validation_copies() -> None:
    steps = _steps()
    full = _plan(steps)
    assert replay.validate_plan(full, required=14) == []
    # 13 files against the after-step-14 reference (BUILD_SPEC LMG-4 test_plan_validation)
    errors = replay.validate_plan(full[:13], required=14)
    assert [(error.field, error.message) for error in errors] == [
        ("plan", "Add 14 files in order.")
    ]
    # a modification file without a mode
    without_mode = _plan(steps, with_mode=False)
    modification = next(
        item for item in without_mode if item.template_code == "legacy_contract_modification"
    )
    errors = replay.validate_plan(without_mode, required=14)
    assert (
        f"plan[{without_mode.index(modification)}].mode",
        f"Choose a mode for {modification.file_name}.",
    ) in [(error.field, error.message) for error in errors]
    # a progress file without a date
    undated = _plan(steps, dated=False)
    progress = next(item for item in undated if item.template_code == "legacy_progress_tracking")
    errors = replay.validate_plan(undated, required=14)
    assert (
        f"plan[{undated.index(progress)}].effective_date",
        f"Enter the effective date for {progress.file_name}.",
    ) in [(error.field, error.message) for error in errors]
    # the SSP file comes first; a setup file takes no mode; an unknown template is refused
    swapped = [full[1], full[0], *full[2:]]
    assert any(
        "first position" in error.message for error in replay.validate_plan(swapped, required=14)
    )
    with_mode = [dataclasses.replace(full[1], mode="prospective"), *full[2:]]
    assert any(
        "takes no mode" in error.message
        for error in replay.validate_plan([full[0], *with_mode], required=14)
    )
    unknown = [dataclasses.replace(full[0], template_code="csv_v2_contracts"), *full[1:]]
    assert any(
        "Choose a legacy template" in error.message
        for error in replay.validate_plan(unknown, required=14)
    )


def test_four_file_plan_for_the_shipped_reference() -> None:
    # GPB-3: steps 01 to 04 against WLD-F-15 through the same plan contract.
    steps = _steps()[:4]
    plan = _plan(steps)
    assert (
        replay.validate_plan(plan, required=replay.required_files(legacy_db.profile(FIXTURE))) == []
    )
    batches = replay.batches(plan)
    assert [batch.order for batch in batches] == [1, 2, 3, 4]
    assert [batch.template_code for batch in batches] == [
        "legacy_sku_ssp",
        "legacy_contract_setup",
        "legacy_contract_setup",
        "legacy_progress_tracking",
    ]
    assert batches[3].date_input == date(2023, 1, 31) and batches[3].mode is None
    assert replay.validate_plan(plan, required=14)[0].message == "Add 14 files in order."


def test_sandbox_display_name() -> None:
    assert replay.sandbox_display_name("Pembrey Gauges") == "Pembrey Gauges replay (Sandbox)"


def _csv_legacy_rows(path: Path) -> tuple[LegacyRow, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(
            LegacyRow(
                index, MappingProxyType({k: (v if v != "" else None) for k, v in record.items()})
            )
            for index, record in enumerate(csv.DictReader(handle), start=1)
        )


def test_replay_plan_shape_from_the_shipped_reference() -> None:
    # Ruling Q-1 (F-LMG record §4): the shipped step-04 database requires 4 slots — the SSP file,
    # two setup uploads (Previous Period NULL on every row) and one dated upload on 2023-01-31.
    profile = legacy_db.profile(FIXTURE)
    shape = replay.replay_plan(profile, legacy_db.rows(FIXTURE))
    assert shape.required_files == 4 == replay.required_files(profile)
    assert [
        (slot.order, slot.template_code, slot.is_setup, slot.effective_date) for slot in shape.slots
    ] == [
        (1, "legacy_sku_ssp", False, None),
        (2, "legacy_contract_setup", True, None),
        (3, "legacy_contract_setup", True, None),
        (4, None, False, date(2023, 1, 31)),
    ]
    assert [slot.version_token for slot in shape.slots[1:]] == list(profile.version_tokens)
    plan = _plan(_steps()[:4])
    assert replay.slot_mismatches(plan, shape) == []
    # a wrong date on the dated slot, a setup file in the dated slot, and a short plan are refused
    wrong_date = [*plan[:3], dataclasses.replace(plan[3], effective_date=date(2023, 2, 28))]
    assert [e.field for e in replay.slot_mismatches(wrong_date, shape)] == [
        "plan[3].effective_date"
    ]
    setup_in_dated = [*plan[:3], dataclasses.replace(plan[1])]
    assert [e.field for e in replay.slot_mismatches(setup_in_dated, shape)] == [
        "plan[3].template_code"
    ]
    assert [e.message for e in replay.slot_mismatches(plan[:3], shape)] == ["Add 4 files in order."]


def test_replay_plan_shape_from_the_after_step_14_output() -> None:
    # The 14 golden steps: 14 slots; every dated slot's date equals the step's date_input and the
    # golden 14-file plan fits the shape (LMG-4 / J-21 unchanged).
    rows = _csv_legacy_rows(STEP_14)
    profile = dataclasses.replace(
        legacy_db.profile(FIXTURE),
        version_tokens=tuple(sorted({row.processing_time_log for row in rows})),
    )
    shape = replay.replay_plan(profile, rows)
    steps = _steps()
    assert shape.required_files == 14 == len(steps)
    dated = {str(step["date_input"]) for step in steps if step.get("date_input")}
    assert {slot.effective_date.isoformat() for slot in shape.slots if slot.effective_date} == dated
    assert [slot.is_setup for slot in shape.slots] == [False, True, True] + [False] * 11
    assert replay.slot_mismatches(_plan(steps), shape) == []


def test_replay_sandbox_request_names_its_implementer() -> None:
    request = replay.ReplaySandboxRequest(
        UUID(int=1), replay.sandbox_display_name("Pembrey Gauges")
    )
    assert request.permission == "migration.run"
    assert request.display_name == "Pembrey Gauges replay (Sandbox)"
    assert "empty_sandbox_plan" in (replay.ReplaySandboxRequest.__doc__ or "")
    assert "6a6206b" in (replay.ReplaySandboxRequest.__doc__ or "")


def test_plan_params_carry_the_derivation_inputs() -> None:
    # Ruling Q-1 (D-98 candidate 42): the derived plan length is re-evaluable from recorded inputs —
    # the reference database digest, the version count and the SKU_SSP row count.
    profile = legacy_db.profile(FIXTURE)
    shape = replay.replay_plan(profile, legacy_db.rows(FIXTURE))
    assert dict(shape.params) == {
        "source_sha256": profile.source_sha256,
        "version_count": 3,
        "sku_ssp_rows": 7,
        "required_files": 4,
    }
    assert shape.params["source_sha256"].startswith("6e35b508")
    assert dict(replay.checkpoint(profile).params) == dict(shape.params)


def test_upload_parameters_of_a_batch() -> None:
    # The v1 import upload parameters of one planned batch (template_code, mode, date_input,
    # file_sha256) in the vocabulary the golden handlers use — T1's reader calls this.
    plan = _plan(_steps()[:4])
    batch = replay.batches(plan)[3]
    upload = replay.upload_parameters(batch, file_sha256="ab" * 32)
    assert upload == replay.UploadParameters(
        template_code="legacy_progress_tracking",
        mode=None,
        date_input=date(2023, 1, 31),
        file_sha256="ab" * 32,
    )
    assert upload.as_json() == {
        "template_code": "legacy_progress_tracking",
        "mode": None,
        "date_input": "2023-01-31",
        "file_sha256": "ab" * 32,
    }
    first_modification = next(
        batch
        for batch in replay.batches(_plan(_steps()))
        if batch.template_code == "legacy_contract_modification"
    )  # golden step 08, the retrospective modification of 2023-05-15
    modification = replay.upload_parameters(first_modification, file_sha256="cd" * 32)
    assert (modification.template_code, modification.mode, modification.date_input) == (
        "legacy_contract_modification",
        "retrospective",
        date(2023, 5, 15),
    )
    with pytest.raises(ValueError):
        replay.upload_parameters(batch, file_sha256="not-a-digest")
