"""The import's computations are reader-independent — supervisor ruling R-98 (3) with R-95, the
witnesses on the import side (ACCT backlog row 3; 05 IPL-07, IPL-10, RCP-18): a legacy progress
file and a legacy modification file for ONE member of a combination group of two contracting
entities, uploaded by a person scoped to that member's entity, leave what an unscoped upload of
the same files leaves — the dry run's figures, what an approval of the import has to satisfy,
every computation of the group and the committed group's versions, obligation by obligation, of
BOTH members. What an uploader is shown stays inside the uploader's scope; what the engine reads
does not.

World: TWO workspaces built alike — ``support.legacy_replay.legacy_world`` and the delivered
files of steps 01 and 02 (Contract 1 of Mock Entity 1, Contract 2 of Mock Entity 2), the two
contracts then combined into one group through the product (proposal, submission, Marcus's
approval). In the first workspace the files are uploaded by Lena, a Revenue Accountant for Mock
Entity 1 alone; in the second by Maya, whose role covers every entity. Both files name Contract
1 only. The outputs are read without an entity filter and compared by business names (a
contract's external id, an obligation's key), since the two workspaces share no id.

Two things the world needs, each a fact of the product and no part of the witness:

- An approved combination is dated by the clock (September 2026), and the engine places every
  date in a period of its entity (CV-12); the legacy calendar holds FY2023 and FY2024. The
  calendar is extended to the clock's year through the product, or the combined group is
  QUARANTINED before any file is uploaded.
- A legacy template is of ONE contract (ENGINE_SPEC S06-R-28) and its price must round to the
  allocation basis of the group (S06-INV-01). In a group of two contracts it does not: the
  engine refuses a legacy modification of a member for EVERY uploader. The dry run records the
  modification unevaluated (ruling R-98 (4)), the request takes its second step (R-92), and the
  commit stores the refusal and leaves the version of before in place. Without the combination
  the same file computes. The witness of the modification file is therefore that the scoped
  upload is refused exactly as the unscoped one is — the same invariant with the same two
  amounts: computed from Contract 1 alone, as it was inside the uploader's narrowed scope, the
  template WOULD round to its basis and a version of the group would be stored from one member.

Until lane QA-BE's slice of R-95 the commit's recompute and the dry run ran inside the
uploader's narrowed scope: Lena's group was computed from Contract 1 alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_computation,
    contract_version,
    exception_item,
    import_upload,
    legal_entity,
    obligation_version,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import golden_streams
from support.db import TestDatabase
from support.factories import IMPORTS_PATH, ImportWorld, imported, run_import_job, workbook_bytes
from support.legacy_replay import LegacyWorld, job_of, legacy_world, replayed, workbook_rows
from support.principals import colleague
from support.reference import approve, get, holding, post

GROUPS = "/api/v1/combination-groups"
CALENDARS = "/api/v1/calendars"
YEARS_TO_THE_CLOCK = (2025, 2026)
PROGRESS = "legacy_progress_tracking"
MODIFICATION = "legacy_contract_modification"
MEMBERS = ("Contract 1", "Contract 2")
MODIFICATION_HEADERS = (
    "Contract Unique Name",
    "POB Unique ID",
    "SKU Name",
    "Mod Start Date",
    "Mod End Date",
    "ASC 606 Stratification",
    "Mod Billing",
    "Mod Qty",
    "Selling Entity",
    "Deferred Revenue Account",
    "Unbilled A/R Account",
    "SSP Version",
    "Memo 1",
    "Memo 2",
    "Memo 3",
)
# what a version states of the group, and of each obligation of each member
VERSION_FIGURES = ("transaction_price", "net_position")
OBLIGATION_FIGURES = (
    "allocated_amount",
    "revenue_cum",
    "billed_cum",
    "catch_up_cum",
    "scheduled_amount",
    "remaining_allocation",
    "position_obligation",
    "netting_reclass_amount",
)
# a refusal's sentence ends with the reference of its own job, which the workspaces do not share
REFERENCE = " Reference "


def _figure(value: Any) -> Decimal | None:
    return None if value is None else Decimal(value)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _contract_id(world: LegacyWorld, name: str) -> UUID:
    (found,) = world.imports.rows(select(contract.c.id).where(contract.c.external_id == name))
    return UUID(str(found["id"]))


def _combined(world: LegacyWorld) -> UUID:
    """Contract 1 and Contract 2, of two entities, in ONE combination group: Maya proposes and
    submits, Marcus approves. The id of the group."""
    proposed = post(
        world.app,
        GROUPS,
        world.maya,
        {
            "contract_ids": [str(_contract_id(world, name)) for name in MEMBERS],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(str(proposed.json()["id"]))
    submitted = post(world.app, f"{GROUPS}/{group_id}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert approved.status_code == 200, approved.text
    members = world.imports.rows(
        select(contract.c.external_id, legal_entity.c.code)
        .join(combination_group_member, combination_group_member.c.contract_id == contract.c.id)
        .join(legal_entity, legal_entity.c.id == contract.c.contracting_entity_id)
        .where(
            combination_group_member.c.combination_group_id == group_id,
            combination_group_member.c.valid_to_known_at.is_(None),
        )
    )
    assert sorted((str(row["external_id"]), str(row["code"])) for row in members) == [
        ("Contract 1", "Mock Entity 1"),
        ("Contract 2", "Mock Entity 2"),
    ]
    return group_id


def _outputs(world: LegacyWorld, group_id: UUID) -> dict[str, Any]:
    """The latest version of the group in every book it is computed in, by business names: the
    version's figures and every obligation of BOTH members. Read without an entity filter."""
    names = {
        UUID(str(row["id"])): str(row["external_id"])
        for row in world.imports.rows(select(contract.c.id, contract.c.external_id))
    }
    found: dict[str, Any] = {}
    versions = world.imports.rows(
        select(contract_version)
        .where(contract_version.c.combination_group_id == group_id)
        .order_by(contract_version.c.book_code, contract_version.c.version_no)
    )
    latest = {str(row["book_code"]): row for row in versions}  # the last of each book wins
    for book, version in latest.items():
        obligations = world.imports.rows(
            select(obligation_version).where(
                obligation_version.c.contract_version_id == version["id"]
            )
        )
        found[book] = {
            "version": {name: _figure(version[name]) for name in VERSION_FIGURES},
            "obligations": {
                (names[UUID(str(row["contract_id"]))], str(row["obligation_key"])): {
                    name: _figure(row[name]) for name in OBLIGATION_FIGURES
                }
                for row in obligations
            },
        }
    return found


def _computations(world: LegacyWorld, group_id: UUID) -> list[tuple[str, str | None]]:
    """Every computation of the group, oldest first: its status and, for one the engine refused,
    the sentence of its problem up to the job's reference — the invariant and the amounts it
    names, which a bundle of other members would not reproduce."""
    rows = world.imports.rows(
        select(contract_computation.c.status, contract_computation.c.problem)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.known_at, contract_computation.c.id)
    )
    found: list[tuple[str, str | None]] = []
    for row in rows:
        problem = row["problem"]
        said = None if problem is None else str(problem["detail"]).split(REFERENCE)[0]
        found.append((str(row["status"]), said))
    return found


def _diff(world: LegacyWorld, reader: Any, import_id: str) -> list[dict[str, Any]]:
    answered = get(world.app, f"{IMPORTS_PATH}/{import_id}/diff", reader, {"limit": 200})
    assert answered.status_code == 200, answered.text
    return list(answered.json()["items"])


def _dry_run(
    world: LegacyWorld,
    uploader: ImportWorld,
    name: str,
    content: bytes,
    template: str,
    parameters: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Upload, validate and diff as ``uploader``: the import id and API-S-Import at DIFF_READY,
    no row or plan of it refused."""
    import_id, validated = imported(uploader, name, content, template, parameters)
    assert validated["status"] == "VALIDATED", validated
    run_import_job(uploader, job_of(world.imports, UUID(import_id), "IMPORT_DIFF"))
    ready = get(world.app, f"{IMPORTS_PATH}/{import_id}", uploader.actor)
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "DIFF_READY", ready.json()
    # a plan the dry run refuses is a finding of the diff, and the import still reads DIFF_READY
    refused = world.imports.rows(
        select(exception_item.c.code, exception_item.c.message).where(
            exception_item.c.import_upload_id == UUID(import_id)
        )
    )
    assert refused == [], (name, refused, ready.json().get("diff_summary"))
    return import_id, dict(ready.json())


def _commit(world: LegacyWorld, uploader: ImportWorld, import_id: str) -> int:
    """The uploader submits; Priya approves and, when the request asks for a second step, Marcus
    takes it; the worker commits. The number of steps the request asked for."""
    submitted = post(
        world.app, f"{IMPORTS_PATH}/{import_id}/submit", uploader.actor, {"comment": "R-98 (3)"}
    )
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    steps = 0
    status = "PENDING"
    for approver in (world.priya, world.marcus):
        decided = approve(world.app, request_id, approver)
        assert decided.status_code == 200, decided.text
        steps += 1
        status = str(decided.json()["status"])
        if status != "PENDING":
            break
    assert status == "APPROVED", status
    run_import_job(uploader, job_of(world.imports, UUID(import_id), "IMPORT_COMMIT"))
    committed = world.imports.scalar(
        select(import_upload.c.status).where(import_upload.c.id == UUID(import_id))
    )
    assert str(committed) == "COMMITTED", committed
    return steps


def _progress_of_contract_1() -> bytes:
    """The rows of Contract 1 in the delivered progress file of 31 January 2023 (step 04)."""
    step = golden_streams.steps("04")[-1]
    headers, rows = workbook_rows(step.workbook)
    name = headers.index("Contract Unique Name")
    own = [row for row in rows if row[name] == "Contract 1"]
    assert own and len(own) < len(rows)  # the delivered file holds Contract 2's rows too
    return workbook_bytes("Progress Tracking", headers, own)


def _modification_of_contract_1() -> bytes:
    """A change of POB #1 of Contract 1, sold by its own entity: 100.00 more for one unit more.
    Alone in its group, Contract 1 takes it (1,300.00 becomes 1,400.00)."""
    row = [
        "Contract 1",
        "POB #1",
        "Hardware 1",
        "2023-01-01",
        "2024-05-31",
        "Hardware 1",
        100,
        1,
        "Mock Entity 1",
        21001,
        15001,
        "2023-01-01",
        "Delivery 1",
        "Delivery 2",
        "Delivery 3",
    ]
    return workbook_bytes("Contract Modification", MODIFICATION_HEADERS, [row])


def _calendar_to_the_clock(world: LegacyWorld) -> None:
    """The legacy world's one calendar holds FY2023 and FY2024, and the clock stands in
    September 2026 (module docstring): Maya generates the years between."""
    listed = get(world.app, CALENDARS, world.maya)
    assert listed.status_code == 200, listed.text
    (calendar,) = listed.json()["items"]
    for year in YEARS_TO_THE_CLOCK:
        generated = post(
            world.app,
            f"{CALENDARS}/{calendar['id']}/generate-year",
            world.maya,
            {"fiscal_year": year},
        )
        assert generated.status_code == 200, generated.text


def _world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> Any:
    """One workspace of the pair: the legacy world with steps 01 and 02 committed, its calendar
    reaching the clock, and its two contracts combined. (the world, the group id)"""
    world = legacy_world(app, keyring, clock, files)
    replayed(world, "02")
    _calendar_to_the_clock(world)
    return world, _combined(world)


def test_r98_3_legacy_files_of_a_scoped_uploader_compute_the_whole_group(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """R-98 (3): Lena, a Revenue Accountant for Mock Entity 1 alone, uploads a legacy progress
    file and then a legacy modification file for Contract 1, a member of a group whose other
    member, Contract 2, is of Mock Entity 2. In a second workspace built alike Maya, whose role
    covers every entity, uploads the same two files. After each file the two workspaces hold the
    same: the dry run's items as a reader of every entity reads them, what an approval of the
    import has to satisfy, the steps the request asks for, every computation of the group and
    its latest version in every book, obligation by obligation of BOTH members. Lena is shown
    nothing of Contract 2: the items of the diff Lena reads name Contract 1 alone.

    The progress file computes and moves the group's figures. The modification file is refused
    by the engine for both uploaders (module docstring) — with the same invariant and the same
    two amounts, which a group read from Contract 1 alone would not give."""
    scoped, scoped_group = _world(app, keyring, clock, files)
    whole, whole_group = _world(app, keyring, clock, files)
    lena = ImportWorld(
        app=app,
        actor=holding(
            app,
            colleague(scoped.tenant_id, "lena"),
            "revenue_accountant",
            entity_ids=[scoped.entity_ids["Mock Entity 1"]],
        ),
        runtime=scoped.imports.runtime,
        clock=clock,
    )
    # the two workspaces start alike, and the combined group holds both members' obligations
    before = _outputs(scoped, scoped_group)
    assert before == _outputs(whole, whole_group)
    assert before, "the combined group is computed"
    for book in before.values():
        assert {name for name, _ in book["obligations"]} == set(MEMBERS)
    computed = _computations(scoped, scoped_group)
    assert computed == _computations(whole, whole_group) == [("SUCCEEDED", None)]

    # --- the progress file: it computes
    name, content = "Progress Contract 1.xlsx", _progress_of_contract_1()
    parameters: dict[str, Any] = {"effective_date": "2023-01-31"}
    scoped_id, scoped_ready = _dry_run(scoped, lena, name, content, PROGRESS, parameters)
    whole_id, whole_ready = _dry_run(whole, whole.imports, name, content, PROGRESS, parameters)
    # the dry run's figures: every item, as a reader of every entity reads it
    items = _diff(scoped, scoped.maya, scoped_id)
    assert items == _diff(whole, whole.maya, whole_id)
    assert items, "the progress file changes figures"
    assert scoped_ready["diff_summary"] == whole_ready["diff_summary"]
    # what the uploader is shown stays inside the uploader's scope
    shown = _diff(scoped, lena.actor, scoped_id)
    assert shown and {item["contract_external_id"] for item in shown} == {"Contract 1"}
    assert _commit(scoped, lena, scoped_id) == _commit(whole, whole.imports, whole_id) == 1
    after = _outputs(scoped, scoped_group)
    assert after == _outputs(whole, whole_group)
    assert after != before  # the file moved the group's figures
    computed = _computations(scoped, scoped_group)
    assert computed == _computations(whole, whole_group) == [("SUCCEEDED", None)] * 2

    # --- the modification file: the engine refuses it, for both uploaders alike
    name, content = "Modification Contract 1.xlsx", _modification_of_contract_1()
    parameters = {"effective_date": "2023-02-15", "mode": "prospective"}
    scoped_id, scoped_ready = _dry_run(scoped, lena, name, content, MODIFICATION, parameters)
    whole_id, whole_ready = _dry_run(whole, whole.imports, name, content, MODIFICATION, parameters)
    assert _diff(scoped, scoped.maya, scoped_id) == _diff(whole, whole.maya, whole_id) == []
    assert scoped_ready["diff_summary"] == whole_ready["diff_summary"]
    # R-98 (4): a floor is evaluated only on a computation that succeeded
    (underlying,) = scoped_ready["diff_summary"]["underlying_approvals"]
    assert (underlying["subject_type"], underlying["evaluated"]) == ("MODIFICATION", False)
    # R-92: the unevaluated modification asks for its second step
    assert _commit(scoped, lena, scoped_id) == _commit(whole, whole.imports, whole_id) == 2
    computed = _computations(scoped, scoped_group)
    assert computed == _computations(whole, whole_group)
    assert [status for status, _ in computed] == ["SUCCEEDED", "SUCCEEDED", "QUARANTINED"]
    refusal = computed[-1][1]
    assert refusal is not None and "S06-INV-01" in refusal, refusal
    # the refused amendment leaves the version of before in place, in both workspaces
    assert _outputs(scoped, scoped_group) == _outputs(whole, whole_group) == after
