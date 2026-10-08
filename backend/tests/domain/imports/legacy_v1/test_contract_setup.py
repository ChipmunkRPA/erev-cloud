"""DIN-4 legacy v1 contract setup template (ENGINE_SPEC S01-R-06, S03-R-18; 04 T-IMP-01, §17.4
LM-TPL-SETUP, T-REF-19 legacy note, table 15.4-A; PRD J-01.8, J-01.9, BR-DAT-06, WLD-X-26, IMP-16,
IMP-34; POLICIES POL-213, POL-214; DEVIATIONS DEV-032; legacy 01 §7.3 TC-setup-01, 08, 11, 22; 03
REQ-DAT-017, REQ-ALC-010, REQ-TP-016; BUILD_SPEC DIN-4, BS3-D-23).

World: ``support.legacy_replay.legacy_world`` (J-01.2 to J-01.5): Maya uploads WLD-F-01 and then the
setup files, Priya approves each import, and the jobs run as the worker runs them. The VC element
port (``contract_setup.vc_element_writer``) is the documented contract of BUILD_SPEC CTR-12: the
member tests observe its real writes, and its default stores the element (L5-1-Q-15, Q-35).
"""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    audit_event,
    contract,
    contract_event,
    contract_version,
    customer,
    estimate,
    estimate_version,
    exception_item,
    import_row,
    judgement_record,
    legal_entity,
    obligation_version,
)
from erev_api.domain.contracts import holds
from erev_api.domain.imports import diff, legacy_v1
from erev_api.domain.imports.csv_v2.framework import ApplyContext
from erev_api.domain.imports.legacy_v1 import contract_setup, progress
from erev_api.enums import ContractEventType
from erev_api.events.payloads import DeliveryRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import select
from support import golden_streams
from support.db import TestDatabase
from support.factories import (
    appended,
    booked_contract,
    create_import,
    imported,
    run_import_job,
    upload_import_source,
    workbook_bytes,
)
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.legacy_replay import (
    SETUP_2023,
    SKU_SSP,
    LegacyWorld,
    committed,
    diffed,
    job_of,
    legacy_world,
    replayed,
    shown,
    submit,
    workbook_rows,
)
from support.reference import APPROVALS, approve, get, post, slug

SETUP_NAME = "Contract Setup Template 1.1.2023.xlsx"
EXACT = Decimal("0.000000000001")
# Legacy 01 §7.3 TC-setup-01: the legacy exact allocations at 15 significant digits.
TC_SETUP_01_CONTRACT_1 = (
    Decimal("322.101090188305"),
    Decimal("237.066402378593"),
    Decimal("96.630327056492"),
    Decimal("644.202180376610"),
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files)


@pytest.fixture
def native(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files, preset=False)


@pytest.fixture
def elements(monkeypatch: pytest.MonkeyPatch) -> list[tuple[contract_setup.VcElement, bool]]:
    """Observe the real CTR-12 writer in dry runs and committed imports."""
    written: list[tuple[contract_setup.VcElement, bool]] = []

    def fake(
        uow: UnitOfWork, element: contract_setup.VcElement, *, context: ApplyContext
    ) -> UUID | None:
        written.append((element, context.dry_run))
        return contract_setup.store_vc_element(uow, element, context=context)

    monkeypatch.setattr(contract_setup, "vc_element_writer", fake)
    return written


def _setup(world: LegacyWorld) -> dict[str, Any]:
    committed(world, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    return committed(world, SETUP_NAME, SETUP_2023.read_bytes(), "legacy_contract_setup")


def _contract(world: LegacyWorld, name: str) -> dict[str, Any]:
    (found,) = world.imports.rows(select(contract).where(contract.c.external_id == name))
    return found


def _latest(world: LegacyWorld, name: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """The latest ASC606 version of a contract's group and its obligation versions by key."""
    found = _contract(world, name)
    versions = world.imports.rows(
        select(contract_version)
        .where(
            contract_version.c.combination_group_id == found["combination_group_id"],
            contract_version.c.book_code == "ASC606",
        )
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )
    assert versions, f"{name} has no computed version"
    version = versions[0]
    obligations = world.imports.rows(
        select(obligation_version).where(
            obligation_version.c.contract_version_id == version["id"],
            obligation_version.c.contract_id == found["id"],
        )
    )
    return version, {str(row["obligation_key"]): row for row in obligations}


def _close(values: list[Decimal], expected: tuple[Decimal, ...]) -> bool:
    """Equal within 1e-12, the precision of the legacy figures."""
    return len(values) == len(expected) and all(
        abs(value - figure) <= EXACT for value, figure in zip(values, expected, strict=True)
    )


def _amounts(obligations: Mapping[str, Mapping[str, Any]], member: str) -> list[Decimal]:
    return [Decimal(obligations[key][member]) for key in sorted(obligations)]


def test_setup_1_1_2023_contracts_and_allocations(
    legacy: LegacyWorld, elements: list[tuple[contract_setup.VcElement, bool]]
) -> None:
    done = _setup(legacy)
    assert (done["counts"]["rows"], done["counts"]["errors"]) == (8, 0), done

    for name in ("Contract 1", "Contract 2"):
        assert str(_contract(legacy, name)["status"]) == "ACTIVE"
    first, c1 = _latest(legacy, "Contract 1")
    assert Decimal(first["transaction_price"]) == Decimal("1300.00")
    assert sorted(c1) == ["POB #1", "POB #2", "POB #3", "POB #4"]
    assert _amounts(c1, "allocated_amount") == [
        Decimal("322.10"),
        Decimal("237.07"),
        Decimal("96.63"),
        Decimal("644.20"),
    ]
    # TC-setup-01 exact allocations; TC-setup-08 posted amounts sum to the price.
    assert _close(_amounts(c1, "allocated_exact"), TC_SETUP_01_CONTRACT_1)
    assert sum(_amounts(c1, "allocated_amount")) == Decimal("1300.00")

    second, c2 = _latest(legacy, "Contract 2")
    assert sorted(c2) == ["POB #1", "POB #2", "POB #3", "VC #1"]
    assert _amounts(c2, "original_ssp_selected") == [
        Decimal("612"),
        Decimal("408"),
        Decimal("150"),
        Decimal("0"),
    ]
    assert str(c2["VC #1"]["obligation_kind"]) == "VC_LINE"
    assert Decimal(c2["VC #1"]["allocated_amount"]) == Decimal("0.00")
    assert sum(_amounts(c2, "allocated_amount")) == Decimal(second["transaction_price"])
    (element,) = [item for item, dry_run in elements if not dry_run]
    assert element.estimate_key == "Contract 2/VC-VC #1"

    customers = legacy.imports.rows(
        select(customer.c.code, customer.c.source_system)
        .where(customer.c.code.like("LEGACY-%"))
        .order_by(customer.c.code)
    )
    assert [(row["code"], str(row["source_system"])) for row in customers] == [
        ("LEGACY-Contract 1", "LEGACY_TEMPLATE_V1"),
        ("LEGACY-Contract 2", "LEGACY_TEMPLATE_V1"),
    ]
    assert [
        row["code"]
        for row in legacy.imports.rows(
            select(legal_entity.c.code)
            .where(legal_entity.c.code.like("Mock Entity %"))
            .order_by(legal_entity.c.code)
        )
    ] == ["Mock Entity 1", "Mock Entity 2"]
    assert str(_contract(legacy, "Contract 1")["contracting_entity_id"]) == str(
        legacy.entity_ids["Mock Entity 1"]
    )
    assert str(_contract(legacy, "Contract 2")["contracting_entity_id"]) == str(
        legacy.entity_ids["Mock Entity 2"]
    )


def test_setup_import_approval_activates_contracts(legacy: LegacyWorld) -> None:
    done = _setup(legacy)
    import_no = done["import_no"]
    request_id = UUID(done["approval_request_id"])
    maya, priya = legacy.maya.member.user_id, legacy.priya.member.user_id
    for name, obligations, estimated in (("Contract 1", 4, False), ("Contract 2", 4, True)):
        found = _contract(legacy, name)
        assert str(found["status"]) == "ACTIVE"
        assert found["document_ref"] == f"import:{import_no}:{SETUP_NAME}"
        checklist = get(
            legacy.app, f"/api/v1/contracts/{found['id']}/activation-checklist", legacy.maya
        )
        assert checklist.status_code == 200, checklist.text
        assert [(item["code"], item["passed"]) for item in checklist.json()["items"]] == [
            (code, True)
            for code in (
                "MANDATORY_FIELDS",
                "SOURCE_REFERENCE",
                "PRODUCT_TEMPLATE_SSP",
                "DISTINCT_REVIEW",
                "COMBINATION_SUGGESTIONS",
                "JUDGEMENT_RECORDS",
                "STEP1_RECORD",
            )
        ], checklist.json()
        records = legacy.imports.rows(
            select(judgement_record).where(judgement_record.c.contract_id == found["id"])
        )
        topics = sorted(str(row["topic"]) for row in records)
        assert topics == ["COLLECTIBILITY"] + ["POB_DISTINCT_OVERRIDE"] * obligations
        for row in records:
            assert (str(row["status"]), row["reviewer_id"], row["approval_request_id"]) == (
                "REVIEWED",
                priya,
                request_id,
            )
            assert str(row["created_by_kind"]) == "SYSTEM"
        prepared = legacy.imports.rows(
            select(audit_event.c.object_id, audit_event.c.on_behalf_of_id).where(
                audit_event.c.action == "judgement_record.create",
                audit_event.c.object_id.in_([row["id"] for row in records]),
            )
        )
        assert {row["on_behalf_of_id"] for row in prepared} == {maya}
        assert len(prepared) == len(records)
        events = legacy.imports.rows(
            select(
                contract_event.c.event_type,
                contract_event.c.payload,
                contract_event.c.approval_request_id,
            )
            .where(contract_event.c.contract_id == found["id"])
            .order_by(contract_event.c.stream_version)
        )
        # Since the L5 merge the VC row of Contract 2 appends ESTIMATE_CHANGED after the booking
        # through the CTR-12 port (store_vc_element; S01-R-18; L5-1-Q-35).
        assert [str(row["event_type"]) for row in events] == [
            "CONTRACT_BOOKED",
            *(["ESTIMATE_CHANGED"] if estimated else []),
            "COLLECTIBILITY_ASSESSED",
            "CONTRACT_ACTIVATED",
        ]
        assert events[-2]["payload"]["is_probable"] is True
        assert events[-1]["approval_request_id"] == request_id


def test_vc_rows_become_vc_elements(
    legacy: LegacyWorld, elements: list[tuple[contract_setup.VcElement, bool]]
) -> None:
    _setup(legacy)
    _, c2 = _latest(legacy, "Contract 2")
    vc = c2["VC #1"]
    assert (str(vc["obligation_kind"]), vc["stratification"]) == ("VC_LINE", "VC")
    assert (Decimal(vc["original_ssp_selected"]), Decimal(vc["allocated_amount"])) == (
        Decimal("0"),
        Decimal("0.00"),
    )
    # The dry-run diff and the commit each write the element through the port.
    assert [dry_run for _, dry_run in elements] == [True, False]
    element = elements[-1][0]
    assert element.contract_id == UUID(str(_contract(legacy, "Contract 2")["id"]))
    assert (
        element.estimate_key,
        element.element_code,
        element.obligation_key,
        element.estimate_kind,
        element.method,
        element.version_no,
        element.allocation_target,
    ) == (
        "Contract 2/VC-VC #1",
        "VC-VC #1",
        "VC #1",
        "VARIABLE_CONSIDERATION",
        "ENTERED_AMOUNT",
        1,
        "CONTRACT",
    )
    # Version 1 constrained amount equals the row price: 100.00 as a DECREASE element (B3-D16).
    assert (element.direction, element.constrained_amount, element.currency) == (
        "DECREASE",
        Decimal("100"),
        "USD",
    )
    assert element.effective_date == date(2023, 1, 1)


def _value(item: Any) -> str:
    return str(getattr(item, "value", item))


def test_l5_merge_vc_element_stored_through_ctr_12(legacy: LegacyWorld) -> None:
    """L5 merge (L5-1-Q-15, L5-1-Q-35; S01-R-06, S01-R-18, B3-D16): the default port stores the
    element, its APPROVED version 1 and ``ESTIMATE_CHANGED``, so Contract 2 prices at 900.00."""
    _setup(legacy)
    found = _contract(legacy, "Contract 2")
    assert _value(found["status"]) == "ACTIVE"
    (element,) = legacy.imports.rows(select(estimate).where(estimate.c.contract_id == found["id"]))
    assert (element["element_code"], element["direction"], _value(element["method"])) == (
        "VC-VC #1",
        "DECREASE",
        "ENTERED_AMOUNT",
    )
    (version,) = legacy.imports.rows(
        select(estimate_version).where(estimate_version.c.estimate_id == element["id"])
    )
    assert (_value(version["status"]), version["version_no"]) == ("APPROVED", 1)
    assert Decimal(version["constrained_amount"]) == Decimal("100")
    changed = legacy.imports.rows(
        select(contract_event).where(
            contract_event.c.contract_id == found["id"],
            contract_event.c.event_type == ContractEventType.ESTIMATE_CHANGED,
        )
    )
    assert [row["estimate_version_id"] for row in changed] == [version["id"]]
    assert list(version["applied_event_ids"]) == [changed[0]["id"]]
    second, c2 = _latest(legacy, "Contract 2")
    assert Decimal(second["transaction_price"]) == Decimal("900.00")
    assert _amounts(c2, "allocated_amount") == [
        Decimal("470.77"),
        Decimal("313.85"),
        Decimal("115.38"),
        Decimal("0.00"),
    ]


def test_native_policy_rejects_vc_pseudo_lines(native: LegacyWorld) -> None:
    # DIN-7: setup rows resolve against an approved SKU SSP version (SSP_KEY_NOT_FOUND).
    committed(native, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    import_id, validated = imported(
        native.imports, SETUP_NAME, SETUP_2023.read_bytes(), "legacy_contract_setup"
    )
    assert validated["status"] == "INVALID", validated
    assert validated["counts"]["errors"] == 1, validated
    items = native.imports.rows(
        select(
            exception_item.c.code,
            exception_item.c.field,
            exception_item.c.message,
            import_row.c.row_number,
        )
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
    )
    assert [(row["code"], row["field"], row["row_number"]) for row in items] == [
        ("VC_TARGET_INVALID", "ASC 606 Stratification", 9)
    ]
    assert items[0]["message"] == (
        "Sheet1 row 9, column ASC 606 Stratification: A price change cannot target VC element "
        "Contract 2/VC-VC #1. Target an obligation. Key Contract 2 / VC #1 / Variable "
        "Consideration. (VC_TARGET_INVALID)"
    )


def test_tc_setup_11_split_upload_allocates_whole_contract(legacy: LegacyWorld) -> None:
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    headers, rows = workbook_rows(SETUP_2023)
    contract_1 = [row for row in rows if row[0] == "Contract 1"]
    first = workbook_bytes("Sheet1", headers, contract_1[:2])
    committed(
        legacy,
        "Contract 1 part 1.xlsx",
        first,
        "legacy_contract_setup",
        {"activate_on_approval": False},
    )
    draft = _contract(legacy, "Contract 1")
    assert str(draft["status"]) == "DRAFT"

    second = workbook_bytes("Sheet1", headers, contract_1[2:])
    committed(legacy, "Contract 1 part 2.xlsx", second, "legacy_contract_setup")
    assert str(_contract(legacy, "Contract 1")["status"]) == "ACTIVE"
    version, c1 = _latest(legacy, "Contract 1")
    assert sorted(c1) == ["POB #1", "POB #2", "POB #3", "POB #4"]
    assert Decimal(version["transaction_price"]) == Decimal("1300.00")
    assert _close(_amounts(c1, "allocated_exact"), TC_SETUP_01_CONTRACT_1)


def test_tc_setup_22_existing_contract_rejected_with_pointer(legacy: LegacyWorld) -> None:
    _setup(legacy)
    found = _contract(legacy, "Contract 1")
    appended(
        legacy.place(),
        UUID(str(found["id"])),
        int(found["head_stream_version"]),
        [
            EventIn(
                event_type=ContractEventType.DELIVERY_RECORDED,
                effective_date=date(2023, 1, 31),
                payload=DeliveryRecordedV1(
                    obligation_key="POB #1", quantity="2", trigger="DELIVERY"
                ),
                obligation_keys=("POB #1",),
            )
        ],
    )
    head = int(_contract(legacy, "Contract 1")["head_stream_version"])

    headers, rows = workbook_rows(SETUP_2023)
    memo = headers.index("Memo 1")
    changed = [list(row) for row in rows if row[0] == "Contract 1"]
    changed[0][memo] = "Initial setup 1 (corrected)"
    import_id, validated = imported(
        legacy.imports,
        "Contract Setup Template 1.1.2023 corrected.xlsx",
        workbook_bytes("Sheet1", headers, changed),
        "legacy_contract_setup",
    )
    assert validated["status"] == "INVALID", validated
    items = legacy.imports.rows(
        select(exception_item.c.code, exception_item.c.message, import_row.c.row_number)
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number)
    )
    assert [(row["code"], row["row_number"]) for row in items] == [
        ("SETUP_CONTRACT_EXISTS", number) for number in (2, 3, 4, 5)
    ]
    assert items[0]["message"] == (
        "Sheet1 row 2, column Contract Unique Name: Contract Contract 1 already exists. Change it "
        "through a Contract Modification upload or the modification workflow. Key Contract 1 / "
        "POB #1 / Hardware 1. (SETUP_CONTRACT_EXISTS)"
    )
    assert shown(legacy.imports, import_id)["counts"]["errors"] == 4

    file_id = upload_import_source(legacy.imports, SETUP_NAME, SETUP_2023.read_bytes())
    again = create_import(legacy.imports, file_id, "legacy_contract_setup")
    assert again.status_code == 409, again.text
    assert again.json()["type"].endswith("/duplicate-import")
    assert int(_contract(legacy, "Contract 1")["head_stream_version"]) == head


# --- P5-RET-1 (DG-KRN-APR-05 rev 1.51; D-98 candidate 119; Codex 0216 / 0226 / 0342) ------------


def _patched_template(monkeypatch: pytest.MonkeyPatch, template: Any, apply: Any) -> None:
    """The fixture seam (Codex production-20260921-0737; batch #4 on main c9110467):
    ``commit_upload`` resolves the emitter through ``diff.emitter_of(code)`` → the REGISTERED
    frozen ``CsvTemplate`` whose ``apply`` was captured at construction (``progress.TEMPLATE``,
    ``contract_setup.TEMPLATE``) and calls ``template.apply`` — rebinding the module attribute
    (``progress.apply``, ``contract_setup.apply``) never reached the job, so the adversaries never
    ran and the imports committed untouched. ONLY that registry entry is replaced, in a copied
    mapping that preserves every other entry, and the resolution is asserted before the job runs.
    Production dispatch is untouched; no frozen template is mutated."""
    patched = dataclasses.replace(template, apply=apply)
    registry = MappingProxyType({**legacy_v1.TEMPLATES, template.code: patched})
    assert len(registry) == len(legacy_v1.TEMPLATES) and template.code in legacy_v1.TEMPLATES
    monkeypatch.setattr(legacy_v1, "TEMPLATES", registry)
    resolved = diff.emitter_of(template.code)
    assert resolved is not None and resolved.apply is apply, resolved
    assert all(  # every other entry is the original object
        diff.emitter_of(code) is original
        for code, original in registry.items()
        if code != template.code
    )


def _golden(number: str) -> Any:
    (step,) = [item for item in golden_streams.steps(number) if item.number == number]
    return step


def _approved_import(legacy: LegacyWorld, step: Any) -> tuple[str, str]:
    """A golden step diffed, submitted and approved by Priya, NOT yet committed: (import id,
    approval request id)."""
    parameters: dict[str, Any] = {}
    if step.date_input is not None:
        parameters["effective_date"] = step.date_input.isoformat()
    if step.mode is not None:
        parameters["mode"] = step.mode
    import_id = diffed(
        legacy.imports,
        step.workbook.name,
        step.workbook.read_bytes(),
        step.template_code,
        parameters or None,
    )
    submitted = submit(legacy.imports, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    decided = approve(legacy.app, request_id, legacy.priya)
    assert decided.status_code == 200, decided.text
    return import_id, request_id


def _events_of(legacy: LegacyWorld, name: str) -> list[str]:
    found = _contract(legacy, name)
    return [
        str(row["event_type"])
        for row in legacy.imports.rows(
            select(contract_event.c.event_type)
            .where(contract_event.c.contract_id == found["id"])
            .order_by(contract_event.c.stream_version)
        )
    ]


def _invoices_of(legacy: LegacyWorld, name: str) -> list[str]:
    """The invoice numbers of a contract's BILLING_RECORDED events, in stream order."""
    found = _contract(legacy, name)
    return [
        str(row["payload"]["invoice_number"])
        for row in legacy.imports.rows(
            select(contract_event.c.payload)
            .where(
                contract_event.c.contract_id == found["id"],
                contract_event.c.event_type == "BILLING_RECORDED",
            )
            .order_by(contract_event.c.stream_version)
        )
    ]


def _billing(legacy: LegacyWorld, name: str) -> dict[str, Any]:
    found = _contract(legacy, name)
    return {
        "event_type": "BILLING_RECORDED",
        "effective_date": "2023-01-31",
        "payload": {
            "invoice_number": f"INV-P5-{name[-1]}",
            "line_external_id": f"INV-P5-{name[-1]}-1",
            "amount": {"amount": "100.00", "currency": str(found["transaction_currency"]).strip()},
            "issue_date": "2023-01-31",
        },
    }


def test_progress_import_refuses_an_external_head_change_before_consumption_atomically(
    legacy: LegacyWorld,
) -> None:
    """Steps 01–02 committed (Contracts 1 and 2 ACTIVE); golden step 04 (progress over both) is
    approved — its basis pins their heads. Between Priya's approval and the IMPORT_COMMIT job a
    SYSTEM hold reaches Contract 1 (HOLD_APPLIED, head + 1). The job consumes the basis once, under
    the named contracts' locks and before any effect: refused atomically — the import ends FAILED,
    no event of the step reaches either contract, the approval stays decided. DB-bound, NOT RUN on
    l12."""
    replayed(legacy, "02")
    import_id, request_id = _approved_import(legacy, _golden("04"))
    first = _contract(legacy, "Contract 1")
    with legacy.place().uow() as uow:
        assert (
            holds.apply_system_hold(uow, UUID(str(first["id"])), reason="P5-RET-1 external change")
            is not None
        )
        uow.commit()
    before = {name: _events_of(legacy, name) for name in ("Contract 1", "Contract 2")}
    assert before["Contract 1"][-1] == "HOLD_APPLIED"
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(legacy.imports, import_id)["status"] == "FAILED"
    assert {name: _events_of(legacy, name) for name in ("Contract 1", "Contract 2")} == before
    request = get(legacy.app, f"{APPROVALS}/{request_id}", legacy.priya).json()
    assert request["status"] == "APPROVED"  # the decision stands; the consumption refused the job


def test_named_contracts_stay_locked_from_the_consumption_to_the_commit(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 0226's interval, on an EXISTING committed contract (Codex 0342 R2): steps 01–02
    committed; golden step 04 (progress over Contracts 1 and 2) approved. At the job's LATER plan an
    external BILLING append to that plan's contract — committed, visible, If-Match at its committed
    head — is started: the consumption locked every named contract and the transaction holds them,
    so the append is witnessed BLOCKED by the job's backend (participant-bound), the job commits
    whole (COMMITTED, both contracts carry the step's events), and the append then answers 412 — its
    head is behind. Never interleaved. DB-bound, NOT RUN on l12."""
    replayed(legacy, "02")
    import_id, _ = _approved_import(legacy, _golden("04"))
    heads_before = {
        name: int(_contract(legacy, name)["head_stream_version"])
        for name in ("Contract 1", "Contract 2")
    }
    outcome: dict[str, Any] = {}
    plans: list[str] = []
    real_apply = progress.apply

    def apply_with_interleaving(uow: UnitOfWork, plan: Any, *, context: Any) -> Any:
        name = str(plan.key).split(" / ", 1)[0]
        plans.append(name)
        if len(plans) == 2:  # between the initial check and the LATER plan's consumption
            body = _billing(legacy, name)
            found = _contract(legacy, name)

            def external_append() -> None:
                try:
                    outcome["result"] = post(
                        legacy.app,
                        f"/api/v1/contracts/{found['id']}/events",
                        legacy.maya,
                        {"events": [body]},
                        if_match=f'"s{heads_before[name]}"',
                    )
                except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
                    outcome["error"] = exc

            with observing_checkouts() as backends:
                writer = threading.Thread(target=external_append, name="external-append")
                writer.start()
                outcome["writer"] = writer  # registered first: finally joins it whatever follows
                outcome["target"] = name
                blocked_pid, blocked_in = await_lock_wait(
                    uow.session,
                    holder_pid=backend_pid(uow.session),
                    backends=backends,
                    timeout=20.0,
                )
                outcome["blocked"] = (blocked_pid, blocked_in)
                assert writer.is_alive()
        return real_apply(uow, plan, context=context)

    _patched_template(monkeypatch, progress.TEMPLATE, apply_with_interleaving)
    try:
        run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    finally:
        writer = outcome.get("writer")
        if writer is not None:
            writer.join(timeout=30)
            assert not writer.is_alive(), "the external writer did not terminate"
    assert shown(legacy.imports, import_id)["status"] == "COMMITTED"
    assert len(plans) == 2 and "blocked" in outcome and "error" not in outcome, outcome
    target = outcome["target"]
    assert int(_contract(legacy, target)["head_stream_version"]) > heads_before[target]
    assert outcome["result"].status_code == 412, outcome["result"].text  # behind the job's head
    assert _events_of(legacy, target)[-1] != "BILLING_RECORDED"  # the external append did not land


def test_setup_import_refuses_a_contract_that_appeared_for_an_approved_absent_key(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 0342 R1's adversary, fixture-corrected per Codex 0438: golden step 03 (setup of
    Contracts 3 and 4, both approved ABSENT) is approved; after the job's initial check and before
    plan 1 allocates Contract 3's number, an external transaction creates and commits a compatible
    DRAFT "Contract 4" (Contract 1's booking payload under the new key). Plan 1 writes Contract 3;
    plan 2's ``_book`` admits only against the approved basis — approved absence, a contract now
    exists → StaleBasis (the named refusal, captured at the plan) — and the whole job rolls back:
    the import ends FAILED, Contract 3 does not exist, Contract 4 carries only its external booking,
    the approval stays decided. DB-bound, NOT RUN on l12."""
    replayed(legacy, "02")
    import_id, request_id = _approved_import(legacy, _golden("03"))
    first = _contract(legacy, "Contract 1")
    (booking,) = legacy.imports.rows(
        select(contract_event.c.payload).where(
            contract_event.c.contract_id == first["id"],
            contract_event.c.event_type == "CONTRACT_BOOKED",
        )
    )
    plans: list[str] = []
    refusals: list[str] = []
    real_apply = contract_setup.apply

    def apply_with_adversary(uow: UnitOfWork, plan: Any, *, context: Any) -> Any:
        plans.append(str(plan.key))
        if len(plans) == 1:
            # Codex 0438: committed by another transaction AFTER the initial check (consumption and
            # _check_bases ran before plan 1) and BEFORE plan 1 allocates Contract 3's number — the
            # numbering_series row is still free, so the external booking commits at once; at
            # plan 2 it would wait on the row plan 1 holds until the job's transaction ends.
            booked_contract(
                legacy.place(),
                {**dict(booking["payload"]), "external_id": "Contract 4", "document_ref": None},
                activate=False,
            )
        try:
            return real_apply(uow, plan, context=context)
        except Exception as exc:
            refusals.append(f"{plan.key}:{type(exc).__name__}")
            raise

    _patched_template(monkeypatch, contract_setup.TEMPLATE, apply_with_adversary)
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(legacy.imports, import_id)["status"] == "FAILED"
    assert plans == ["Contract 3", "Contract 4"]
    # The NAMED refusal: plan 1 booked Contract 3; plan 2 found a contract where the approval said
    # absent and refused StaleBasis — the whole job then rolled back.
    assert refusals == ["Contract 4:StaleBasis"], refusals
    assert (
        legacy.imports.rows(select(contract.c.id).where(contract.c.external_id == "Contract 3"))
        == []
    )
    assert _events_of(legacy, "Contract 4") == ["CONTRACT_BOOKED"]  # the external draft only
    request = get(legacy.app, f"{APPROVALS}/{request_id}", legacy.priya).json()
    assert request["status"] == "APPROVED"


def test_progress_import_approval_is_stale_after_an_external_member_event(
    legacy: LegacyWorld,
) -> None:
    """P5-SUBJ-1 (04 §16.10 rev 1.65; D-98 candidate 135). Steps 01–02 committed; golden step 04
    (progress over Contracts 1 and 2) diffed and SUBMITTED — its approval content now names both
    contracts with their heads. An external BILLING append on Contract 1 commits (head + 1) before
    Priya decides. The approval recomputes the content, finds Contract 1's head moved and refuses:
    409 ``stale-approval``, the request VOIDED ``STALE_SUBJECT`` (the request keeps the reviewed
    hash; the void audit carries the current one), the import REJECTED by ``_closed`` — no
    IMPORT_COMMIT job, no step event on either contract. Before rev 1.65 the same approval answered
    200 and the commit later ended FAILED (``_check_bases``) — that refusal is RETAINED for a change
    an approval could not see (``test_progress_import_refuses_an_external_head_change_before_
    consumption_atomically``). DB-bound, NOT RUN on l12."""
    replayed(legacy, "02")
    step = _golden("04")
    parameters: dict[str, Any] = {}
    if step.date_input is not None:
        parameters["effective_date"] = step.date_input.isoformat()
    if step.mode is not None:
        parameters["mode"] = step.mode
    import_id = diffed(
        legacy.imports,
        step.workbook.name,
        step.workbook.read_bytes(),
        step.template_code,
        parameters or None,
    )
    submitted = submit(legacy.imports, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    reviewed = get(legacy.app, f"{APPROVALS}/{request_id}", legacy.priya).json()
    assert reviewed["status"] == "PENDING", reviewed
    first = _contract(legacy, "Contract 1")
    head_before = int(first["head_stream_version"])
    events_before = {name: _events_of(legacy, name) for name in ("Contract 1", "Contract 2")}
    appended = post(
        legacy.app,
        f"/api/v1/contracts/{first['id']}/events",
        legacy.maya,
        {"events": [_billing(legacy, "Contract 1")]},
        if_match=f'"s{head_before}"',
    )
    assert appended.status_code in (201, 202), appended.text  # 04 §16.3 API-S-EventAppend
    assert int(_contract(legacy, "Contract 1")["head_stream_version"]) == head_before + 1
    stale = approve(legacy.app, request_id, legacy.priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    after = get(legacy.app, f"{APPROVALS}/{request_id}", legacy.priya).json()
    assert (after["status"], after["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert after["subject"]["content_sha256"] == reviewed["subject"]["content_sha256"]
    assert shown(legacy.imports, import_id)["status"] == "REJECTED"  # on_voided → _closed
    assert _events_of(legacy, "Contract 1") == [*events_before["Contract 1"], "BILLING_RECORDED"]
    assert _events_of(legacy, "Contract 2") == events_before["Contract 2"]  # no step event landed


RENAMED: dict[str, str] = {"Contract 1": "ACME / West", "Contract 2": "ACME"}


def _renamed_world(legacy: LegacyWorld) -> tuple[list[str], list[list[Any]], Any]:
    """Steps 01–02 through the REAL legacy importer with the contracts renamed so that one
    identifier contains the T-IMP-03 key separator (" / ") and another is its prefix:
    `ACME / West` and `ACME` (Codex production-20260921-1521 §1; D-98 candidate 135 amendment 1).
    Returns the golden step 04 progress headers / rows (renamed) and the step."""
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    headers, rows = workbook_rows(SETUP_2023)
    setup_rows = [[RENAMED.get(str(row[0]), row[0]), *row[1:]] for row in rows]
    committed(
        legacy,
        "Contract Setup Template 1.1.2023 renamed.xlsx",
        workbook_bytes("Sheet1", headers, setup_rows),
        "legacy_contract_setup",
    )
    assert str(_contract(legacy, "ACME / West")["status"]) == "ACTIVE"
    assert str(_contract(legacy, "ACME")["status"]) == "ACTIVE"
    step = _golden("04")
    p_headers, p_rows = workbook_rows(step.workbook)
    progress_rows = [[RENAMED.get(str(row[0]), row[0]), *row[1:]] for row in p_rows]
    return p_headers, progress_rows, step


def _submitted_progress(
    legacy: LegacyWorld, headers: list[str], rows: list[list[Any]], step: Any, name: str
) -> tuple[str, str]:
    """A progress upload over ``rows`` diffed and SUBMITTED (request PENDING): (import id,
    request id)."""
    parameters = {} if step.date_input is None else {"effective_date": step.date_input.isoformat()}
    import_id = diffed(
        legacy.imports,
        name,
        workbook_bytes("Progress Tracking", headers, rows),
        step.template_code,
        parameters or None,
    )
    submitted = submit(legacy.imports, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    reviewed = get(legacy.app, f"{APPROVALS}/{request_id}", legacy.priya).json()
    assert reviewed["status"] == "PENDING", reviewed
    return import_id, request_id


def _subject_contracts(legacy: LegacyWorld, import_id: str) -> list[list[Any]]:
    """The actual `IMPORT_COMMIT` subject content's `contracts` (full external ids and heads)."""
    with legacy.place().uow() as uow:
        return [
            list(pair)
            for pair in subjects.import_commit_content(uow.session, UUID(import_id))["contracts"]
        ]


def test_progress_approval_of_a_slash_named_contract_is_stale_after_its_own_event(
    legacy: LegacyWorld,
) -> None:
    """D-98 candidate 135 amendment 1 witness (1), through the REAL registered legacy importer with
    persisted validated rows / diff / submit: the progress upload names `ACME / West` (its display
    business_key reads "ACME / West / POB #n / SKU"); the PENDING request's subject content pins
    `["ACME / West", head]` — the FULL identifier. An external BILLING event on `ACME / West`
    commits (head + 1); the FIRST approval attempt is 409 ``stale-approval``, the request VOIDED
    ``STALE_SUBJECT``, the import REJECTED (``_closed``), the only effect the external event. On
    db77bd3f the key was parsed from the display key as `ACME` and the real move was missed.
    DB-bound, NOT RUN on l12."""
    headers, rows, step = _renamed_world(legacy)
    west_rows = [row for row in rows if row[0] == "ACME / West"]
    import_id, request_id = _submitted_progress(
        legacy, headers, west_rows, step, "Progress West.xlsx"
    )
    pinned = _subject_contracts(legacy, import_id)
    west = _contract(legacy, "ACME / West")
    head_before = int(west["head_stream_version"])
    assert pinned == [["ACME / West", head_before]], pinned  # the full id, its current head
    events_before = {name: _events_of(legacy, name) for name in ("ACME / West", "ACME")}
    appended = post(
        legacy.app,
        f"/api/v1/contracts/{west['id']}/events",
        legacy.maya,
        {"events": [_billing(legacy, "ACME / West")]},
        if_match=f'"s{head_before}"',
    )
    assert appended.status_code in (201, 202), appended.text
    assert int(_contract(legacy, "ACME / West")["head_stream_version"]) == head_before + 1
    stale = approve(legacy.app, request_id, legacy.priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    after = get(legacy.app, f"{APPROVALS}/{request_id}", legacy.priya).json()
    assert (after["status"], after["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert shown(legacy.imports, import_id)["status"] == "REJECTED"
    assert _events_of(legacy, "ACME / West") == [*events_before["ACME / West"], "BILLING_RECORDED"]
    assert _events_of(legacy, "ACME") == events_before["ACME"]


def test_progress_approval_ignores_an_unrelated_prefix_named_contract(legacy: LegacyWorld) -> None:
    """D-98 candidate 135 amendment 1 witness (2): the upload names `ACME / West` only; an external
    BILLING event on the UNRELATED contract `ACME` (the identifier's prefix) commits before the
    decision. The subject content still pins `["ACME / West", head]` and nothing else, so the
    approval is 200 (APPROVED), the IMPORT_COMMIT job COMMITS the step onto `ACME / West`, and
    `ACME` carries only its external event. On db77bd3f the truncated key `ACME` pinned the
    unrelated contract's head and its move voided the request falsely. DB-bound, NOT RUN on l12."""
    headers, rows, step = _renamed_world(legacy)
    west_rows = [row for row in rows if row[0] == "ACME / West"]
    import_id, request_id = _submitted_progress(
        legacy, headers, west_rows, step, "Progress West 2.xlsx"
    )
    acme = _contract(legacy, "ACME")
    acme_head = int(acme["head_stream_version"])
    west_head = int(_contract(legacy, "ACME / West")["head_stream_version"])
    assert _subject_contracts(legacy, import_id) == [["ACME / West", west_head]]
    events_before = {name: _events_of(legacy, name) for name in ("ACME / West", "ACME")}
    appended = post(
        legacy.app,
        f"/api/v1/contracts/{acme['id']}/events",
        legacy.maya,
        {"events": [_billing(legacy, "ACME")]},
        if_match=f'"s{acme_head}"',
    )
    assert appended.status_code in (201, 202), appended.text
    assert int(_contract(legacy, "ACME")["head_stream_version"]) == acme_head + 1
    decided = approve(legacy.app, request_id, legacy.priya)
    assert decided.status_code == 200, decided.text  # not stale: `ACME` is not pinned
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(legacy.imports, import_id)["status"] == "COMMITTED"
    assert _events_of(legacy, "ACME") == [*events_before["ACME"], "BILLING_RECORDED"]
    west_after = _events_of(legacy, "ACME / West")
    assert west_after[: len(events_before["ACME / West"])] == events_before["ACME / West"]
    assert len(west_after) > len(events_before["ACME / West"])  # the step's events landed
    # Integrated batch #7 (main 104a954c) measured the former oracle wrong: golden step 04's
    # progress rows carry "Current Billing", so the step ITSELF appends BILLING_RECORDED on West.
    # The claim is that the EXTERNAL event — the `ACME` invoice — landed on `ACME` only.
    external = _billing(legacy, "ACME")["payload"]["invoice_number"]
    assert _invoices_of(legacy, "ACME")[-1] == external
    assert external not in _invoices_of(legacy, "ACME / West")


def test_exc_import_scope_the_item_of_a_failed_activation_names_the_contracts_entity(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 T-IMP-05 "An item that names no entity: who reads it" (rev 1.218; item
    EXC-IMPORT-SCOPE-1): the item a Contract Setup commit raises when the activation checklist of
    a contract fails (BR-DAT-06; L5-1-Q-17) names the contract and its group and — from this
    revision — the contract's contracting entity, so it is an item of that entity, bound by the
    row policy, and not one every member reads. The contract stays DRAFT and the commit
    completes. The checklist is made to fail by a stand-in for ``activation.activate``: no file
    of the tree reaches a failing checklist at a setup commit."""
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")

    def refused(_uow: UnitOfWork, **_members: Any) -> None:
        raise Problem(
            contract_setup.CHECKLIST_FAILED,
            errors=[
                ProblemError(
                    field="checklist",
                    rule_id="PRODUCT_TEMPLATE_SSP",
                    message="An obligation's product has no SSP entry.",
                )
            ],
        )

    monkeypatch.setattr(contract_setup.activation, "activate", refused)
    done = committed(legacy, SETUP_NAME, SETUP_2023.read_bytes(), "legacy_contract_setup")
    booked = {
        row["id"]: row
        for row in legacy.imports.rows(
            select(
                contract.c.id,
                contract.c.contracting_entity_id,
                contract.c.combination_group_id,
                contract.c.status,
            )
        )
    }
    assert booked and {str(row["status"]) for row in booked.values()} == {"DRAFT"}
    items = legacy.imports.rows(
        select(
            exception_item.c.code,
            exception_item.c.contract_id,
            exception_item.c.combination_group_id,
            exception_item.c.entity_id,
        ).where(exception_item.c.import_upload_id == UUID(str(done["id"])))
    )
    assert {row["code"] for row in items} == {"PRODUCT_TEMPLATE_SSP"}
    assert {row["contract_id"] for row in items} == set(booked)
    for row in items:
        named = booked[row["contract_id"]]
        assert (row["combination_group_id"], row["entity_id"]) == (
            named["combination_group_id"],
            named["contracting_entity_id"],
        )
