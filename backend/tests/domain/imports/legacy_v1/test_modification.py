"""DIN-6 legacy v1 contract modification template modes (ENGINE_SPEC S01-R-09, §6.5 S06-R-28 to
S06-R-31; 04 T-IMP-01 ``legacy_contract_modification``, §3.4 E-23 to E-25, §16.3
``CONTRACT_AMENDED``; POLICIES POL-100; DEVIATIONS DEV-018, DEV-053, DEV-056; legacy 02 §7.3
TC-delivery-22, 03 §7.3 TC-01, 04 §7.3 TC-RM-01, 05 §7.3 TC-pob-vc-01; 03 REQ-DAT-002,
REQ-DAT-003; BUILD_SPEC DIN-6).

World: ``support.legacy_replay.legacy_world`` and ``replayed``, which replays the golden steps
through the import pipeline (DG-PAR-04 order). Maya uploads and Priya approves. [J] L5-1-Q-27: the
upload appends ``CONTRACT_AMENDED`` under the import approval and the engine bundle projects the
modification it applies. The Contract 2 figures of TC-RM-01 and TC-pob-vc-01 need the CTR-12 VC
element of its booking (L5-1-Q-15), so those tests assert the template invariants instead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_computation,
    contract_event,
    contract_source_link,
    contract_version,
    exception_item,
    import_row,
    modification,
    obligation,
    obligation_version,
)
from erev_api.domain.contracts import bundles
from erev_api.enums import RegistryCategory, RegistryScope
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.registry import presets
from erev_engine.bundle import ModificationInput
from erev_engine.canonical import sha256_hex
from fastapi import FastAPI
from sqlalchemy import select
from support import golden_streams
from support.db import TestDatabase
from support.factories import create_import, upload_import_source, workbook_bytes
from support.legacy_replay import LegacyWorld, committed, diffed, legacy_world, replayed
from support.reference import get
from support.rows import INVITED_AT, publish_registry_version

CODE = "legacy_contract_modification"
PROGRESS = "legacy_progress_tracking"
PROGRESS_HEADERS = (
    "Contract Unique Name",
    "POB Unique ID",
    "SKU Name",
    "Current Delivery",
    "Current Billing",
    "Current Pre-ASC606 Revenue (Net Design Only)",
    "Memo 1",
    "Memo 2",
    "Memo 3",
)
TOLERANCE = Decimal("0.0001")
INVARIANT = Decimal("0.000000001")


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


def _workbook(number: str) -> tuple[str, bytes]:
    """The verified workbook of golden step ``number``."""
    (step,) = [item for item in golden_streams.steps(number) if item.number == number]
    return step.workbook.name, step.workbook.read_bytes()


def _contract(world: LegacyWorld, name: str) -> dict[str, Any]:
    (found,) = world.imports.rows(select(contract).where(contract.c.external_id == name))
    return found


def _amended(world: LegacyWorld, import_id: str) -> list[dict[str, Any]]:
    return world.imports.rows(
        select(contract_event)
        .where(
            contract_event.c.import_upload_id == UUID(import_id),
            contract_event.c.event_type == "CONTRACT_AMENDED",
        )
        .order_by(contract_event.c.record_seq)
    )


def _latest(world: LegacyWorld, name: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    found = _contract(world, name)
    (version,) = world.imports.rows(
        select(contract_version)
        .where(
            contract_version.c.combination_group_id == found["combination_group_id"],
            contract_version.c.book_code == "ASC606",
        )
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )
    obligations = world.imports.rows(
        select(obligation_version).where(
            obligation_version.c.contract_version_id == version["id"],
            obligation_version.c.contract_id == found["id"],
        )
    )
    return version, {str(item["obligation_key"]): item for item in obligations}


def _previous(world: LegacyWorld, item: Mapping[str, Any]) -> dict[str, Any] | None:
    previous = item["previous_obligation_version_id"]
    if previous is None:
        return None
    (earlier,) = world.imports.rows(
        select(obligation_version).where(obligation_version.c.id == previous)
    )
    return earlier


def _exact(world: LegacyWorld, item: Mapping[str, Any]) -> Decimal:
    """The exact cumulative revenue behind a posted obligation version (API-S-Explain)."""
    response = get(
        world.app, f"/api/v1/explain/obligation_version/{item['id']}/revenue_cum", world.maya
    )
    assert response.status_code == 200, response.text
    body = response.json()
    (root,) = [node for node in body["nodes"] if node["id"] == body["root_node_id"]]
    return Decimal(root["value"]) + Decimal(root["rounding_residue"] or "0")


def _change(world: LegacyWorld, item: Mapping[str, Any]) -> Decimal:
    """The revenue of a version: the change of the exact cumulative revenue from the previous
    obligation version; at a template boundary without deliveries it is the catch-up (S06-R-30)."""
    found = _exact(world, item)
    earlier = _previous(world, item)
    return found if earlier is None else found - _exact(world, earlier)


def _allocation_change(world: LegacyWorld, obligations: Mapping[str, Mapping[str, Any]]) -> Decimal:
    """Σ (x′ − x) of the exact allocations over the obligations (S06-INV-04)."""
    total = Decimal(0)
    for item in obligations.values():
        total += Decimal(str(item["allocated_exact"]))
        earlier = _previous(world, item)
        if earlier is not None:
            total -= Decimal(str(earlier["allocated_exact"]))
    return total


def _computed(world: LegacyWorld, name: str) -> str:
    found = _contract(world, name)
    (row,) = world.imports.rows(
        select(contract_computation.c.status).where(
            contract_computation.c.id == found["latest_computation_id"]
        )
    )
    return str(row["status"])


def _projected(world: LegacyWorld, name: str) -> tuple[ModificationInput, ...]:
    """The modifications of a member as the engine bundle reads them (L5-1-Q-27)."""
    found = _contract(world, name)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        bundle = bundles.build(
            session, UUID(str(found["combination_group_id"])), world.imports.clock.now()
        )
    (header,) = [item for item in bundle.contracts if item.external_id == name]
    return header.modifications


def _by_key(items: Sequence[ModificationInput], key: object) -> ModificationInput:
    (found,) = [item for item in items if item.modification_key == str(key)]
    return found


def test_mode_and_effective_date_required(legacy: LegacyWorld) -> None:
    world = legacy.imports
    name, content = _workbook("10")
    file_id = upload_import_source(world, name, content)
    cases = (
        (
            {"effective_date": "2023-06-15"},
            "parameters.mode",
            "mode is required for the Contract Modification template.",
        ),
        (
            {"effective_date": "2023-06-15", "mode": "sideways"},
            "parameters.mode",
            "mode must be one of: prospective, retrospective, pob_price_change.",
        ),
        (
            {"mode": "prospective"},
            "parameters.effective_date",
            "effective_date is required for the Contract Modification template.",
        ),
    )
    for parameters, field, message in cases:
        response = create_import(world, file_id, CODE, parameters)
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["type"].endswith("validation-failed")
        assert [(error["field"], error["message"]) for error in body["errors"]] == [
            (field, message)
        ]
    accepted = create_import(
        world, file_id, CODE, {"effective_date": "2023-06-15", "mode": "prospective"}
    )
    assert accepted.status_code == 202, accepted.text


def test_step_08_dry_run_reaches_diff_ready_and_rolls_back(legacy: LegacyWorld) -> None:
    """MAIN DEFECT 2 (2026-09-21; 04 rev 1.80, the supervisor's (c)-QUALIFIED ruling): the
    IMPORT_DIFF dry run of a Contract Modification upload reaches DIFF_READY — the legacy
    ``CONTRACT_AMENDED`` stores NULL in the T-CON-05 column, so ``fk_contract_event__modification``
    (0068) no longer refuses it — and its savepoint rolls back: no event, no T-CON-06 row, the
    contract head unchanged. RED on main 0959b560 … (the upload ended FAILED at the dry run:
    ForeignKeyViolation)."""
    replayed(legacy, "07")
    contract_2 = _contract(legacy, "Contract 2")
    head = int(contract_2["head_stream_version"])
    name, content = _workbook("08")
    import_id = diffed(
        legacy.imports,
        name,
        content,
        CODE,
        {"effective_date": "2023-05-15", "mode": "retrospective"},
    )
    assert _amended(legacy, import_id) == []
    assert (
        legacy.imports.rows(
            select(modification).where(modification.c.contract_id == contract_2["id"])
        )
        == []
    )
    assert int(_contract(legacy, "Contract 2")["head_stream_version"]) == head


def test_retrospective_step_08(legacy: LegacyWorld) -> None:
    done = replayed(legacy, "08")["08"]
    import_id = done["id"]
    (event,) = _amended(legacy, import_id)
    contract_2 = _contract(legacy, "Contract 2")
    assert event["contract_id"] == contract_2["id"]
    assert (event["effective_date"], str(event["origin"])) == (date(2023, 5, 15), "IMPORT")
    assert event["approval_request_id"] == UUID(str(done["approval_request_id"]))
    # Q-3 / L5-1-Q-27 composed with 140-A3 R2 (04 rev 1.80): the T-CON-05 column is NULL, the
    # synthetic id lives in the payload, and a legacy upload creates no T-CON-06 row.
    assert event["modification_id"] is None
    assert event["idempotency_key"].startswith("imp:")
    payload = event["payload"]
    assert payload["modification_id"] == str(uuid5(UUID(import_id), "Contract 2"))
    assert (
        legacy.imports.rows(
            select(modification).where(modification.c.contract_id == contract_2["id"])
        )
        == []
    )
    # S06-R-28, DEV-053: every obligation of Contract 2 takes the retrospective template.
    assert payload["treatments"] == dict.fromkeys(
        ("POB #1", "POB #2", "POB #3", "VC #1"), "LEGACY_RETROSPECTIVE"
    )
    (line,) = payload["lines"]
    assert (
        line["obligation_key"],
        line["action"],
        line["product_code"],
        line["quantity_delta"],
        Decimal(line["consideration_delta"]["amount"]),
    ) == ("POB #1", "CHANGE", "Hardware 1", "2", Decimal("400"))
    assert (line["start_date"], line["end_date"], line["ssp_version_label"]) == (
        "2023-01-01",
        "2024-05-31",
        "2023-01-01",
    )
    assert line["account_codes"] == {
        "CONTRACT_ASSET": "15002",
        "CONTRACT_LIABILITY": "21002",
        "UNBILLED_RECEIVABLE": "15002",
    }
    assert (line["memo_1"], line["memo_2"], line["memo_3"]) == (
        "Mod 1 05.15.23",
        "Mod 2 05.15.23",
        "Mod 3 05.15.23",
    )
    assert payload["ssp_basis"]["POB #1"]["ssp_book_version_id"] is not None
    # payload / hash unchanged by the NULL column: the stored hash is the payload's (events/stream).
    assert str(event["payload_sha256"]).strip() == sha256_hex(payload)
    # The modification the event applies, as the bundle projects it (L5-1-Q-27); exactly one here.
    (only,) = _projected(legacy, "Contract 2")
    projected = _by_key((only,), payload["modification_id"])
    assert (
        projected.kind,
        projected.template_mode,
        projected.status,
        projected.treatment_summary,
        projected.effective_date,
    ) == ("QUANTITY_CHANGE", "retrospective", "APPLIED", "LEGACY_RETROSPECTIVE", date(2023, 5, 15))
    assert projected.chosen_treatments == payload["treatments"]
    assert projected.ssp_basis["POB #1"]["ssp_version_key"].startswith("LEGACY-SKU-SSP@v")
    # After approval the computation applies the template: TP rises by Mod Billing and the exact
    # allocation moves by Mod Billing (S06-INV-01, S06-INV-04). TC-RM-01's TP 1,300.00 and
    # catch-up 23.867102 need the CTR-12 VC element (L5-1-Q-15).
    assert _computed(legacy, "Contract 2") == "SUCCEEDED"
    version, c2 = _latest(legacy, "Contract 2")
    (earlier,) = legacy.imports.rows(
        select(contract_version).where(contract_version.c.id == version["previous_version_id"])
    )
    assert Decimal(version["transaction_price"]) - Decimal(earlier["transaction_price"]) == Decimal(
        "400"
    )
    assert abs(_allocation_change(legacy, c2) - Decimal("400")) <= INVARIANT
    assert sorted(c2) == ["POB #1", "POB #2", "POB #3", "VC #1"]
    # Row lineage: the row's source record is linked to the amendment (T-CON-02).
    links = legacy.imports.rows(
        select(contract_source_link.c.link_role, contract_source_link.c.contract_event_id).where(
            contract_source_link.c.contract_id == contract_2["id"],
            contract_source_link.c.link_role == "AMENDMENT",
        )
    )
    assert [(item["link_role"], item["contract_event_id"]) for item in links] == [
        ("AMENDMENT", event["id"])
    ]


def test_pob_price_change_step_09(legacy: LegacyWorld) -> None:
    done = replayed(legacy, "09")["09"]
    (event,) = _amended(legacy, done["id"])
    payload = event["payload"]
    assert event["effective_date"] == date(2023, 5, 31)
    assert payload["treatments"] == dict.fromkeys(
        ("POB #1", "POB #2", "POB #3", "VC #1"), "LEGACY_POB_VC"
    )
    (line,) = payload["lines"]
    assert (
        line["obligation_key"],
        line["action"],
        line["quantity_delta"],
        Decimal(line["consideration_delta"]["amount"]),
    ) == ("POB #1", "CHANGE", "0", Decimal("-200"))
    projections = _projected(legacy, "Contract 2")
    assert [item.template_mode for item in sorted(projections, key=lambda m: m.effective_date)] == [
        "retrospective",
        "pob_price_change",
    ]
    projected = _by_key(projections, event["payload"]["modification_id"])
    assert (projected.kind, projected.template_mode, projected.treatment_summary) == (
        "VC_CHANGE",
        "pob_price_change",
        "LEGACY_POB_VC",
    )
    assert _computed(legacy, "Contract 2") == "SUCCEEDED"
    _, c2 = _latest(legacy, "Contract 2")
    # DEV-056: only the targeted line catches up, and its allocation moves by Mod Billing.
    assert _change(legacy, c2["POB #2"]) == 0
    assert _change(legacy, c2["POB #3"]) == 0
    assert _change(legacy, c2["POB #1"]) < 0
    assert abs(_allocation_change(legacy, c2) - Decimal("-200")) <= INVARIANT
    # TC-pob-vc-01's catch-up −18.681319 needs the CTR-12 VC element (L5-1-Q-15).


def test_prospective_step_10(legacy: LegacyWorld) -> None:
    done = replayed(legacy, "10")["10"]
    (event,) = _amended(legacy, done["id"])
    contract_1 = _contract(legacy, "Contract 1")
    assert (event["contract_id"], event["effective_date"]) == (contract_1["id"], date(2023, 6, 15))
    payload = event["payload"]
    assert payload["treatments"] == dict.fromkeys(
        ("POB #1", "POB #2", "POB #3", "POB #4"), "LEGACY_PROSPECTIVE"
    )
    (line,) = payload["lines"]
    assert (
        line["obligation_key"],
        line["action"],
        line["quantity_delta"],
        Decimal(line["consideration_delta"]["amount"]),
    ) == ("POB #1", "CHANGE", "-5", Decimal("-500"))
    (projected,) = _projected(legacy, "Contract 1")
    assert (projected.kind, projected.template_mode, projected.treatment_summary) == (
        "QUANTITY_CHANGE",
        "prospective",
        "LEGACY_PROSPECTIVE",
    )
    assert _computed(legacy, "Contract 1") == "SUCCEEDED"
    _, c1 = _latest(legacy, "Contract 1")
    # TC-01: the catch-up on POB #3 is −5.298816.
    catch_up = _change(legacy, c1["POB #3"])
    assert abs(catch_up - Decimal("-5.298816")) <= TOLERANCE, catch_up
    assert abs(_allocation_change(legacy, c1) - Decimal("-500")) <= INVARIANT


def test_add_obligation_row_step_13(legacy: LegacyWorld) -> None:
    done = replayed(legacy, "13")["13"]
    (event,) = _amended(legacy, done["id"])
    contract_3 = _contract(legacy, "Contract 3")
    assert (event["contract_id"], event["effective_date"]) == (contract_3["id"], date(2023, 9, 15))
    payload = event["payload"]
    # DEV-053: every obligation of Contract 3, untouched ones included, and the added line.
    assert payload["treatments"] == dict.fromkeys(
        ("POB #1", "POB #2", "POB #3", "POB #4", "POB #5"), "LEGACY_PROSPECTIVE"
    )
    lines = {line["obligation_key"]: line for line in payload["lines"]}
    assert (lines["POB #4"]["action"], lines["POB #4"]["quantity_delta"]) == ("CHANGE", "-1000")
    added = lines["POB #5"]
    assert (
        added["action"],
        added["product_code"],
        added["quantity_delta"],
        Decimal(added["consideration_delta"]["amount"]),
        added["start_date"],
        added["end_date"],
        added["stratification"],
        added["selling_entity_code"],
        added["ssp_version_label"],
    ) == (
        "ADD",
        "Consulting 1",
        "5",
        Decimal("1000"),
        "2023-06-01",
        "2024-05-31",
        "Consulting 1",
        "Mock Entity 1",
        "2023-01-01",
    )
    assert sorted(event["obligation_ids"]) == sorted(
        {
            row["id"]
            for row in legacy.imports.rows(
                select(obligation.c.id).where(
                    obligation.c.contract_id == contract_3["id"],
                    obligation.c.obligation_key.in_(("POB #4", "POB #5")),
                )
            )
        }
    )
    (row,) = legacy.imports.rows(
        select(obligation).where(
            obligation.c.contract_id == contract_3["id"], obligation.c.obligation_key == "POB #5"
        )
    )
    assert (row["created_by_event_id"], row["legacy_record_key"], row["line_sequence"]) == (
        event["id"],
        "Contract 3 POB #5 Consulting 1",
        5,
    )
    projected = _by_key(_projected(legacy, "Contract 3"), event["payload"]["modification_id"])
    assert (projected.kind, projected.template_mode) == ("ADD_OBLIGATION", "prospective")
    assert _computed(legacy, "Contract 3") == "SUCCEEDED"
    _, c3 = _latest(legacy, "Contract 3")
    assert sorted(c3) == ["POB #1", "POB #2", "POB #3", "POB #4", "POB #5"]


def test_native_policy_mode_is_proposal_input(legacy: LegacyWorld) -> None:
    """[J] L5-1-Q-28: DRAFT modifications with stage 06 proposals are CTR-17 (R-RC-1); under
    ``ENGINE_PROPOSES_PREPARER_CONFIRMS`` the upload applies no legacy treatment."""
    replayed(legacy, "02")
    context = DbContext(tenant_id=legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        values = dict(presets.legacy_parity_values(scope=RegistryScope.TENANT, book_code=None))
        values["mod.route_selection"] = "ENGINE_PROPOSES_PREPARER_CONFIRMS"
        publish_registry_version(
            session,
            tenant_id=legacy.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values=values,
            at=INVITED_AT + timedelta(minutes=1),
            preset_code=presets.LEGACY_PARITY,
        )
    legacy.imports.clock.advance(timedelta(minutes=2))
    head = int(_contract(legacy, "Contract 1")["head_stream_version"])
    name, content = _workbook("10")
    import_id = diffed(
        legacy.imports, name, content, CODE, {"effective_date": "2023-06-15", "mode": "prospective"}
    )
    items = legacy.imports.rows(
        select(exception_item.c.code, exception_item.c.message, import_row.c.row_number)
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
    )
    assert [(item["code"], item["row_number"]) for item in items] == [
        ("IMPORT_PROCESSING_FAILED", 2)
    ]
    assert items[0]["message"].startswith("Row 2 (Contract 1) cannot be applied: ")
    assert "POL-100" in items[0]["message"]
    assert _amended(legacy, import_id) == []
    assert int(_contract(legacy, "Contract 1")["head_stream_version"]) == head


def test_tc_delivery_22_return_after_september_modification(legacy: LegacyWorld) -> None:
    """TC-delivery-22: after steps 01 to 13 Contract 1 POB #2 holds 1 delivered unit recognised at
    118.533201; returning it gives period revenue −118.533201 and cumulative revenue 0.

    [J] L5-1-Q-30: the rc engine refuses a return of units delivered before a legacy template
    boundary (``rec.progress.units.v1``: N − Y − N_k < 0, CV-32), so the computation is quarantined
    with ``NON_FINITE_AMOUNT`` and the stored version keeps its figures. The branch asserts the
    TC-delivery-22 figures once the engine computes the return (D-84 engine fix lanes)."""
    replayed(legacy, "13")
    _, before = _latest(legacy, "Contract 1")
    assert Decimal(before["POB #2"]["delivered_quantity_cum"]) == 1
    assert abs(_exact(legacy, before["POB #2"]) - Decimal("118.533201")) <= TOLERANCE
    done = committed(
        legacy,
        "return 9.30.2023.xlsx",
        workbook_bytes(
            "Progress Tracking",
            PROGRESS_HEADERS,
            [["Contract 1", "POB #2", "Software 1", -1, 0, 0, "Return 1", "Return 2", "Return 3"]],
        ),
        PROGRESS,
        {"effective_date": "2023-09-30"},
    )
    returned = legacy.imports.rows(
        select(contract_event.c.effective_date, contract_event.c.payload).where(
            contract_event.c.import_upload_id == UUID(done["id"]),
            contract_event.c.event_type == "RETURN_RECORDED",
        )
    )
    assert [(item["effective_date"], item["payload"]["obligation_key"]) for item in returned] == [
        (date(2023, 9, 30), "POB #2")
    ]
    assert returned[0]["payload"]["quantity"] == "1"
    _, c1 = _latest(legacy, "Contract 1")
    found = _contract(legacy, "Contract 1")
    # A quarantined computation leaves ``contract.latest_computation_id`` on the last success, so
    # the newest computation of the group is read.
    (latest, *_) = legacy.imports.rows(
        select(contract_computation.c.status, contract_computation.c.problem)
        .where(contract_computation.c.combination_group_id == found["combination_group_id"])
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
    )
    if str(latest["status"]) == "SUCCEEDED":
        revenue = _change(legacy, c1["POB #2"])
        assert abs(revenue - Decimal("-118.533201")) <= TOLERANCE, revenue
        assert abs(_exact(legacy, c1["POB #2"])) <= TOLERANCE
        return
    assert (str(latest["status"]), latest["problem"]["code"]) == (
        "QUARANTINED",
        "NON_FINITE_AMOUNT",
    )
    codes = [
        str(item["code"])
        for item in legacy.imports.rows(
            select(exception_item.c.code).where(exception_item.c.contract_id == found["id"])
        )
    ]
    assert "NON_FINITE_AMOUNT" in codes
    assert c1["POB #2"]["id"] == before["POB #2"]["id"]


def test_added_product_without_mandatory_attributes_is_quarantined(legacy: LegacyWorld) -> None:
    replayed(legacy, "12")
    before = _contract(legacy, "Contract 3")
    context = DbContext(tenant_id=legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=legacy.tenant_id,
            category=RegistryCategory.DISCLOSURE_ELECTION,
            values={"disclosure.mandatory_disaggregation_attributes": ["review_channel"]},
            at=legacy.imports.clock.now(),
        )
    name, content = _workbook("13")
    import_id = diffed(
        legacy.imports, name, content, CODE, {"effective_date": "2023-09-15", "mode": "prospective"}
    )
    items = legacy.imports.rows(
        select(exception_item.c.code, exception_item.c.message).where(
            exception_item.c.import_upload_id == UUID(import_id)
        )
    )
    assert any(
        item["code"] == "IMPORT_PROCESSING_FAILED"
        and "Product Consulting 1 is missing mandatory disaggregation attributes: review_channel."
        in item["message"]
        for item in items
    ), items
    assert _amended(legacy, import_id) == []
    assert _contract(legacy, "Contract 3")["head_stream_version"] == before["head_stream_version"]
    assert (
        legacy.imports.rows(
            select(obligation.c.id).where(
                obligation.c.contract_id == before["id"], obligation.c.obligation_key == "POB #5"
            )
        )
        == []
    )
