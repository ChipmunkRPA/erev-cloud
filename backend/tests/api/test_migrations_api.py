"""API-R-48 migrations over a database (04 §15.3 API-R-48, §15.2 ``duplicate-import``,
``legacy-database-unrecognized``, ``upload-type-not-allowed``; T-MIG-01 E-76; SCREENS_B §10.1 to
§10.3; PRD J-20, J-20-ALT-1, J-20-ALT-2; BUILD_SPEC LMG-1 named cases
``test_tc_setup_25_same_database_twice_creates_no_duplicates``, ``test_not_a_legacy_database``,
``test_legacy_database_size_limit``, ``test_migration_permission``; lane record §25).

WRITTEN, NOT RUN on the lane (the databases ``erev_rv_l24_*`` are Ray-side). World: a Revenue
Accountant (``migration.run``) of a provisioned tenant through ``support.factories.import_world``;
the legacy database is WLD-F-15 ``backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db``
uploaded with purpose ``LEGACY_DATABASE``; the jobs the commands defer run through
``run_import_job`` under the world's runtime.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    file_object,
    job,
    migrated_legacy_row,
    migration_batch,
)
from erev_api.domain.migration import legacy_db
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import ImportWorld, import_world, run_import_job
from support.http import call
from support.legacy_replay import _publish_parity_templates
from support.principals import (
    carrying,
    colleague,
    cookie_headers,
    enrolled,
    sign_in,
    workspace,
)
from support.reference import fields, get, post, slug
from support.rows import insert_role_assignment
from support.shred_in_flight import beside_a_shred

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
FILES_PATH = "/api/v1/files"
MIGRATIONS_PATH = "/api/v1/migrations"
CUTOVER = "2023-01-31"
KEY_FIGURES = {
    "contract_live_rows": 24,
    "contracts": 4,
    "legacy_pob_rows": 16,
    "sku_ssp_rows": 7,
    "ssp_versions": ["2023-01-01"],
    "selling_entities": ["Mock Entity 1", "Mock Entity 2"],
    "latest_current_period": CUTOVER,
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ImportWorld:
    # batch #5 ci return (A): ``Settings.file_root`` — ``file_store_root`` never existed, so every
    # case of this module ERRORED at setup on main 020e5fd3 and no body executed
    built = import_world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    # batch #6 ci return (b): since W2 (04 1.64 LM-CL-09) the /import confirmation resolves EVERY
    # "Will be created" selling entity — a calendar with one period is the only provisioning the
    # confirmation needs (the tenant's ONLY calendar; the time zone comes from entity_defaults)
    from datetime import date as _date

    from erev_api.db.tables import fiscal_calendar, period
    from sqlalchemy import insert
    from support.rows import fiscal_calendar_values, period_values

    context = DbContext(tenant_id=built.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        calendar = fiscal_calendar_values(built.tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        session.execute(
            insert(period).values(
                **period_values(
                    built.tenant_id,
                    calendar_id=calendar["id"],
                    fiscal_year=2023,
                    period_no=1,
                    start_date=_date(2023, 1, 1),
                    end_date=_date(2023, 1, 31),
                )
            )
        )
    return built


def _upload(
    world: ImportWorld, name: str, content: bytes, *, purpose: str = "LEGACY_DATABASE"
) -> str:
    response = call(
        world.app,
        "POST",
        FILES_PATH,
        data={"purpose": purpose},
        files={"file": (name, content, "application/octet-stream")},
        headers=cookie_headers(world.actor.token, world.actor.csrf_token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _create(world: ImportWorld, file_id: str, mode: str = "OPENING_BALANCES") -> Any:
    return post(world.app, MIGRATIONS_PATH, world.actor, {"mode": mode, "source_file_id": file_id})


def _created(
    world: ImportWorld, content: bytes = b"", name: str = "ASC606-shipped-step04.db"
) -> dict[str, Any]:
    file_id = _upload(world, name, content or FIXTURE.read_bytes())
    response = _create(world, file_id)
    assert response.status_code == 201, response.text
    return dict(response.json())


def _rows(world: ImportWorld, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        return [dict(row) for row in session.execute(statement).mappings().all()]


def _run(world: ImportWorld, job_id: str) -> dict[str, Any]:
    run_import_job(world, UUID(job_id))
    return _rows(world, select(job).where(job.c.id == UUID(job_id)))[0]


def _profiled(world: ImportWorld) -> dict[str, Any]:
    created = _created(world)
    response = post(world.app, f"{MIGRATIONS_PATH}/{created['id']}/profile", world.actor, {})
    assert response.status_code == 202, response.text
    assert response.headers["Location"] == f"/api/v1/jobs/{response.json()['id']}"
    finished = _run(world, response.json()["id"])
    assert finished["state"] == "SUCCEEDED", finished["problem"]
    shown = get(world.app, f"{MIGRATIONS_PATH}/{created['id']}", world.actor)
    assert shown.status_code == 200 and shown.json()["status"] == "PROFILED"
    return dict(shown.json())


# ---- LMG-1 named cases ---------------------------------------------------------------------------


def test_tc_setup_25_same_database_twice_creates_no_duplicates(world: ImportWorld) -> None:
    # legacy 01 §7.3 TC-setup-25; PRD J-20-ALT-1; BR-MIG-01: the second creation of the same
    # database in the same mode is refused by name with the ERR-19 copy naming the first
    first = _created(world)
    assert first["status"] == "UPLOADED" and first["cutover_date"] is None
    assert first["source_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    again = _create(world, first["source_file_id"])
    assert again.status_code == 409 and slug(again) == "duplicate-import"
    assert fields(again) == [("source_file_id", "IMPORT_FILE_DUPLICATE")]
    assert again.json()["detail"] == (
        f"This legacy database was already imported in migration {first['migration_no']} on "
        f"{first['created_at'][:10]}."
    )
    batches = _rows(world, select(migration_batch))
    assert len(batches) == 1
    # batch #6 ci return (a): an unlabelled func.count() is `count_1` — the column is labelled
    assert _rows(world, select(func.count().label("count")).select_from(migrated_legacy_row)) == [
        {"count": 0}
    ]


def test_not_a_legacy_database(world: ImportWorld, tmp_path: Path) -> None:
    # PRD J-20-ALT-2 (ERR-20): WLD-F-35 — a SQLite file without Contract_Live
    from support.parity.sqlite_fixtures import sqlite_without_contract_live

    other = sqlite_without_contract_live(tmp_path / "not-a-legacy-db.sqlite")
    file_id = _upload(world, "not-a-legacy-db.sqlite", other.read_bytes())
    response = _create(world, file_id)
    assert response.status_code == 422 and slug(response) == "legacy-database-unrecognized"
    assert response.json()["detail"] == (
        "The file is not a legacy eRev database: table Contract_Live was not found."
    )
    assert _rows(world, select(migration_batch)) == []


def test_legacy_database_size_limit(world: ImportWorld, tmp_path: Path) -> None:
    # T-PLT-29 / SCREENS_B §10.2 ERR-37 (Codex 0920 R1): an ACTUAL oversize LEGACY_DATABASE body
    # through the real upload route — a sparse file of the policy limit + 1 byte that starts with
    # the SQLite header, so only the size refuses. The store spools up to the limit and refuses by
    # name; no file_object and no migration_batch row remains. End to end (Codex 0920 R2; DPL-12,
    # F-CTR's item accepted by the supervisor): the proxy serves /api/v1/files with
    # client_max_body_size 501m = 525,336,576 bytes ≥ the api's multipart envelope
    # UPLOAD_LIMIT_BYTES 524,353,536, so this 524,288,001-byte body passes the proxy and the
    # envelope and it is the per-purpose policy that refuses it; the JSON routes stay at 1m.
    import os

    from erev_api.db.tables import file_object
    from erev_api.enums import FilePurpose
    from erev_api.files import policy

    limit = policy.UPLOAD_LIMITS[FilePurpose.LEGACY_DATABASE]
    assert limit == 500 * 1024 * 1024  # the 500 MiB policy is preserved, not narrowed for the test
    oversize = tmp_path / "oversize.db"
    oversize.write_bytes(b"SQLite format 3\x00")
    os.truncate(oversize, limit + 1)  # sparse: reads as zeros, no 500 MiB written
    files_before = _rows(world, select(func.count()).select_from(file_object))
    with oversize.open("rb") as body:
        response = call(
            world.app,
            "POST",
            FILES_PATH,
            data={"purpose": "LEGACY_DATABASE"},
            files={"file": ("oversize.db", body, "application/octet-stream")},
            headers=cookie_headers(world.actor.token, world.actor.csrf_token),
        )
    assert response.status_code == 422 and slug(response) == "upload-type-not-allowed"
    assert response.json()["detail"] == "Legacy databases must be SQLite files of at most 500 MiB."
    assert _rows(world, select(func.count()).select_from(file_object)) == files_before
    assert _rows(world, select(migration_batch)) == []


def test_migration_refuses_a_source_uploaded_for_another_purpose(world: ImportWorld) -> None:
    # API-R-48 POST /migrations (distinct from the size limit): a stored file of another purpose —
    # an actually uploadable CSV as IMPORT_SOURCE — is refused by name with the T-PLT-29 rule; the
    # source must be a LEGACY_DATABASE upload
    file_id = _upload(world, "rows.csv", b"a,b\n1,2\n", purpose="IMPORT_SOURCE")
    response = _create(world, file_id)
    assert response.status_code == 422 and slug(response) == "upload-type-not-allowed"
    assert response.json()["detail"] == "Legacy databases must be SQLite files of at most 500 MiB."
    assert fields(response) == [("source_file_id", "T-PLT-29")]
    assert _rows(world, select(migration_batch)) == []


def test_migration_permission(
    world: ImportWorld, app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    # a Viewer's POST /migrations is 403 forbidden; the migration.run holder receives 201 UPLOADED
    someone = colleague(world.tenant_id, "vera")  # a second member of the SAME tenant
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=someone.membership_id,
            role_code="viewer",
        )
    viewer = workspace(app, someone, sign_in(app, someone.email))
    file_id = _upload(world, "ASC606-shipped-step04.db", FIXTURE.read_bytes())
    refused = post(
        app, MIGRATIONS_PATH, viewer, {"mode": "OPENING_BALANCES", "source_file_id": file_id}
    )
    assert refused.status_code == 403 and slug(refused) == "forbidden"
    listed = get(app, MIGRATIONS_PATH, viewer)
    assert listed.status_code == 403
    accepted = _create(world, file_id)
    assert accepted.status_code == 201 and accepted.json()["status"] == "UPLOADED"
    assert accepted.headers["Location"] == f"{MIGRATIONS_PATH}/{accepted.json()['id']}"
    assert accepted.headers["ETag"]


def test_req_plt_012_a_migration_names_only_a_legacy_database_its_creator_may_read(
    world: ImportWorld, app: FastAPI
) -> None:
    """Security review S2, its family (04 T-PLT-29 Read access, rev 1.151; the
    supervisor's ruling on the S2 report, item 3). ``POST /migrations`` checked the purpose of the
    file it was given and nothing else, so a holder of ``migration.run`` named another member's
    upload and had it captured into a migration it could then read. The command asks the
    file-read question first and answers a file its caller may not read as a missing one."""
    someone = colleague(world.tenant_id, "ingrid")  # a second Revenue Accountant: migration.run
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=someone.membership_id,
            role_code="revenue_accountant",
        )
    ingrid = carrying(world, actor=workspace(app, someone, sign_in(app, someone.email)))
    file_id = _upload(ingrid, "ASC606-shipped-step04.db", FIXTURE.read_bytes())

    # Ingrid's upload, which nothing owns yet, named by another holder of migration.run.
    refused = _create(world, file_id)
    unknown = _create(world, str(uuid4()))
    assert refused.status_code == 404, refused.text
    assert slug(refused) == "not-found"
    assert {**refused.json(), "instance": None} == {**unknown.json(), "instance": None}
    assert _rows(world, select(migration_batch)) == []

    # Positive control: the uploader's own database is accepted.
    created = _create(ingrid, file_id)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "UPLOADED"
    # ... and once a migration owns the database, the holders of migration.run read it (T-PLT-29):
    # the same request is then the BR-MIG-01 duplicate, not a missing file.
    duplicate = _create(world, file_id)
    assert (duplicate.status_code, slug(duplicate)) == (409, "duplicate-import"), duplicate.text


# ---- the route cases -----------------------------------------------------------------------------


def test_profile_runs_the_profiling_phase_and_shows_the_key_figures(world: ImportWorld) -> None:
    shown = _profiled(world)
    profile = shown["profile"]
    assert {key: profile[key] for key in KEY_FIGURES} == KEY_FIGURES
    assert profile["source_sha256"] == shown["source_sha256"]
    assert shown["job_id"] is not None and shown["cutover_date"] is None
    # profiling is UPLOADED-only: a second request is refused by name, nothing deferred
    jobs_before = _rows(world, select(func.count()).select_from(job))
    again = post(world.app, f"{MIGRATIONS_PATH}/{shown['id']}/profile", world.actor, {})
    assert again.status_code == 409 and slug(again) == "invalid-transition"
    assert "PROFILED" in again.json()["detail"]
    assert _rows(world, select(func.count()).select_from(job)) == jobs_before
    # AUD-CMD: the command's audit event names the batch
    actions = _rows(
        world,
        select(audit_event.c.action).where(audit_event.c.object_id == UUID(shown["id"])),
    )
    assert {row["action"] for row in actions} >= {
        "migration_batch.create",
        "migration_batch.profile",
    }


def test_import_requires_the_cutover_once_and_refuses_invalid_bodies_by_name(
    world: ImportWorld,
) -> None:
    shown = _profiled(world)
    path = f"{MIGRATIONS_PATH}/{shown['id']}/import"
    # D-98 candidate 128: the cutover is REQUIRED at /import for OPENING_BALANCES
    missing = post(world.app, path, world.actor, {"mode": "OPENING_BALANCES"})
    assert missing.status_code == 422 and slug(missing) == "validation-failed"
    # after the latest legacy period (S07-R-11) and an unknown selling entity (LM-CL-09)
    invalid = post(
        world.app,
        path,
        world.actor,
        {
            "mode": "OPENING_BALANCES",
            "cutover_date": "2023-02-28",
            "entity_mapping": [{"legacy_name": "Nobody", "entity_code": "X"}],
        },
    )
    assert invalid.status_code == 422
    assert ("cutover_date", "S07-R-11") in fields(invalid)
    assert ("entity_mapping[0].legacy_name", "LM-CL-09") in fields(invalid)
    # a REPLAY body on an opening-balances batch
    wrong_mode = post(
        world.app,
        path,
        world.actor,
        {
            "mode": "REPLAY",
            "plan": [
                {
                    "file_id": str(UUID(int=1)),
                    "file_name": "x.xlsx",
                    "template_code": "legacy_sku_ssp",
                }
            ],
        },
    )
    assert wrong_mode.status_code == 422 and fields(wrong_mode)[0][0] == "mode"
    assert _rows(world, select(migration_batch.c.cutover_date))[0]["cutover_date"] is None
    # the accepted body writes the cutover once and defers the import phase (202 + Location)
    accepted = post(
        world.app,
        path,
        world.actor,
        {
            "mode": "OPENING_BALANCES",
            "cutover_date": CUTOVER,
            "entity_mapping": [
                {"legacy_name": "Mock Entity 1", "entity_code": "Mock Entity 1"},
                {"legacy_name": "Mock Entity 2", "entity_code": "Mock Entity 2"},
            ],
            # batch #6 ci return (b): the landed LM-CL-09 confirmation resolves both "Will be
            # created" entities — the world's only calendar and this default time zone; the
            # pre-W2 body (no calendar / zone) is refused by name (four findings), exercised below
            "entity_defaults": {"time_zone": "UTC"},
            "batch_parameters": {},
        },
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.headers["Location"] == f"/api/v1/jobs/{accepted.json()['id']}"
    row = _rows(world, select(migration_batch))[0]
    assert str(row["cutover_date"]) == CUTOVER and row["status"] == "PROFILED"
    assert str(row["job_id"]) == accepted.json()["id"]
    deferred = _rows(world, select(job).where(job.c.id == UUID(accepted.json()["id"])))[0]
    assert deferred["kind"] == "MIGRATION_IMPORT" and deferred["params"]["phase"] == "IMPORT"
    # a different cutover afterwards is refused: set once (the job is not run here — the import
    # phase's own end-to-end case is tests/pg/test_migration_capture_pg.py)
    changed = post(
        world.app,
        path,
        world.actor,
        {"mode": "OPENING_BALANCES", "cutover_date": "2023-01-15"},
    )
    assert changed.status_code == 422 or changed.status_code == 409


def test_reconcile_needs_an_imported_batch(world: ImportWorld) -> None:
    shown = _profiled(world)
    response = post(world.app, f"{MIGRATIONS_PATH}/{shown['id']}/reconcile", world.actor, {})
    assert response.status_code == 409 and slug(response) == "invalid-transition"
    assert "reconciling needs a IMPORTED" in response.json()["detail"]
    lines = get(world.app, f"{MIGRATIONS_PATH}/{shown['id']}/reconciliation-lines", world.actor)
    assert lines.status_code == 200 and lines.json() == {"items": [], "next_cursor": None}


def test_cancel_from_uploaded_and_from_profiled_then_terminal_refusal(world: ImportWorld) -> None:
    created = _created(world)
    cancelled = post(world.app, f"{MIGRATIONS_PATH}/{created['id']}/cancel", world.actor, {})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert cancelled.headers["ETag"]
    again = post(world.app, f"{MIGRATIONS_PATH}/{created['id']}/cancel", world.actor, {})
    assert again.status_code == 409 and "cannot be cancelled" in again.json()["detail"]
    # a cancelled batch frees the source digest: the same database can be created again
    recreated = _create(world, created["source_file_id"])
    assert recreated.status_code == 201


def test_list_filters_sorts_counts_and_carries_unexplained_count(world: ImportWorld) -> None:
    created = _created(world)
    listed = get(world.app, MIGRATIONS_PATH, world.actor, {"count": "true"})
    assert listed.status_code == 200 and listed.headers["X-Erev-Total-Count"] == "1"
    item = listed.json()["items"][0]
    assert item["id"] == created["id"] and item["unexplained_count"] == 0
    filtered = get(world.app, MIGRATIONS_PATH, world.actor, {"status": "PROFILED"})
    assert filtered.json()["items"] == []
    by_mode = get(world.app, MIGRATIONS_PATH, world.actor, {"mode": "OPENING_BALANCES"})
    assert [row["id"] for row in by_mode.json()["items"]] == [created["id"]]
    bad = get(world.app, MIGRATIONS_PATH, world.actor, {"status": "NOPE"})
    assert bad.status_code == 422 and slug(bad) == "validation-failed"
    other_tenant = get(world.app, f"{MIGRATIONS_PATH}/{UUID(int=99)}", world.actor)
    assert other_tenant.status_code == 404


def test_legacy_rows_page_with_cursor_is_empty_before_the_import(world: ImportWorld) -> None:
    shown = _profiled(world)
    page = get(
        world.app, f"{MIGRATIONS_PATH}/{shown['id']}/legacy-rows", world.actor, {"limit": "5"}
    )
    assert page.status_code == 200 and page.json() == {"items": [], "next_cursor": None}
    bad_cursor = get(
        world.app, f"{MIGRATIONS_PATH}/{shown['id']}/legacy-rows", world.actor, {"cursor": "x"}
    )
    assert bad_cursor.status_code == 422 and fields(bad_cursor) == [("cursor", "API-C-09")]
    unknown = get(world.app, f"{MIGRATIONS_PATH}/{UUID(int=7)}/legacy-rows", world.actor)
    assert unknown.status_code == 404


def test_field_mapping_read_is_static_tenant_scoped_and_verbatim(world: ImportWorld) -> None:
    # D-98 133 AMENDMENT 1 (b): the migration.run holder reads the 71 rows in legacy order with the
    # exact legacy names (SCREENS_B §10.3 renders them verbatim); the literal path never reaches
    # the UUID route
    from erev_api.domain.reports import legacy_columns

    listed = get(world.app, f"{MIGRATIONS_PATH}/field-mapping", world.actor)
    assert listed.status_code == 200, listed.text
    rows = listed.json()["rows"]
    assert [row["legacy_column"] for row in rows] == list(legacy_columns.NAMES)
    assert rows[0] == {
        "id": "LM-CL-01",
        "legacy_column": "Contract Unique Name",
        "target": "contract.external_id",
        "rule": rows[0]["rule"],
    }
    assert all(set(row) == {"id", "legacy_column", "target", "rule"} for row in rows)


def test_import_refuses_the_pre_w2_body_by_name_when_nothing_resolves_the_entities(
    world: ImportWorld,
) -> None:
    # batch #6 ci return (b), kept as the named negative: no calendar / time zone on the rows and
    # no entity_defaults → the world's ONLY calendar resolves calendar_id, nothing resolves the time
    # zone: 2 entities × time_zone = two findings on the submitted rows' fields before deferral
    # (04 1.64 LM-CL-09; Codex 1106 R2; Codex 1854 §4 wording); the refusal is never relaxed
    profiled = _profiled(
        world
    )  # the module's PROFILED batch (the profile job run under the runtime)
    refused = post(
        world.app,
        f"{MIGRATIONS_PATH}/{profiled['id']}/import",
        world.actor,
        {
            "mode": "OPENING_BALANCES",
            "cutover_date": CUTOVER,
            "entity_mapping": [
                {"legacy_name": "Mock Entity 1", "entity_code": "Mock Entity 1"},
                {"legacy_name": "Mock Entity 2", "entity_code": "Mock Entity 2"},
            ],
            "batch_parameters": {},
        },
    )
    assert refused.status_code == 422, refused.text
    assert sorted(fields(refused)) == [
        ("entity_mapping[0].time_zone", "LM-CL-09"),
        ("entity_mapping[1].time_zone", "LM-CL-09"),
    ]  # the world's ONLY calendar resolves calendar_id; nothing resolves the time zone


# ---- EVIDENCE-COUNT-SHREDDED-1: the import and a shred of its legacy database see each other ----
# (04 T-PLT-29 "A document a rule asks for"; dev-guide DG-KRN-FILE-08; rulings R-119 (g), R-120 (g))

SHRED_REASON = "DSR-2026-0917: erase the person's data in this document"
IN_FLIGHT = ("Contract 1", "Contract 2")  # set up 1 Jan 2023 — on or before the 31 Jan cutover


def _import_confirmed(world: ImportWorld) -> tuple[dict[str, Any], str]:
    """A PROFILED migration whose import is confirmed: its row, and the id of the deferred job."""
    shown = _profiled(world)
    accepted = post(
        world.app,
        f"{MIGRATIONS_PATH}/{shown['id']}/import",
        world.actor,
        {
            "mode": "OPENING_BALANCES",
            "cutover_date": CUTOVER,
            "entity_mapping": [
                {"legacy_name": "Mock Entity 1", "entity_code": "Mock Entity 1"},
                {"legacy_name": "Mock Entity 2", "entity_code": "Mock Entity 2"},
            ],
            "entity_defaults": {"time_zone": "UTC"},
            "batch_parameters": {},
        },
    )
    assert accepted.status_code == 202, accepted.text
    return _rows(world, select(migration_batch))[0], str(accepted.json()["id"])


def _shredded_at(world: ImportWorld, file_id: UUID) -> Any:
    (row,) = _rows(world, select(file_object.c.shredded_at).where(file_object.c.id == file_id))
    return row["shredded_at"]


def test_evidence_count_shredded_1_the_import_waits_for_a_shred_of_its_legacy_database(
    world: ImportWorld, clock: FrozenClock
) -> None:
    """A migration holds its legacy database from IMPORTING on, and the import job moves it there
    in the transaction that reads the source. The job locks the file's row before that read, as
    a shred does, so the later of the two sees what the earlier committed. A shred in flight —
    the row locked and marked, not committed — holds the job back; when it commits, the job
    finds the database shredded and fails by that name, and the migration is FAILED with nothing
    imported. Measured without the lock: the job did not wait — it read the source past the
    shred in flight and went on to this world's own refusal (``(False, "FAILED",
    ["LM-CL-03"])``; the world has no parity template)."""
    batch, job_id = _import_confirmed(world)
    file_id = UUID(str(batch["source_file_id"]))
    ran = beside_a_shred(
        world.tenant_id, file_id, lambda: _run(world, job_id), at=clock.now(), settle=45.0
    )
    finished = ran.response
    rules = [error["rule_id"] for error in (finished["problem"] or {}).get("errors", [])]
    assert (ran.waited, finished["state"], rules) == (True, "FAILED", ["FILE_SHREDDED"])
    assert _shredded_at(world, file_id) is not None
    assert _rows(world, select(migration_batch.c.status)) == [{"status": "FAILED"}]
    assert _rows(world, select(func.count().label("n")).select_from(migrated_legacy_row)) == [
        {"n": 0}
    ]


def test_evidence_count_shredded_1_a_shred_after_the_import_finds_the_migration_holding_the_file(
    world: ImportWorld, app: FastAPI, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other order, and the positive control of the lock: a job that nothing holds back
    imports — IMPORTED, with its legacy rows — and a shred that comes afterwards finds the
    migration holding the database: one administrator is refused by reference and the file
    stays. The job reads its stored source as it does in production — under the lock — and of
    the rows it reads the contracts in flight at the cutover are handed on, the population
    ``tests/pg/test_migration_capture_pg.py`` imports (Contracts 3 and 4 of the shipped database
    were set up after the cutover; their capture is an open item)."""
    _publish_parity_templates(world.tenant_id)
    batch, job_id = _import_confirmed(world)
    file_id = UUID(str(batch["source_file_id"]))
    read_rows = legacy_db.rows
    handed: list[int] = []

    def in_flight(path: Path) -> tuple[Any, ...]:
        rows = tuple(row for row in read_rows(path) if row.contract_external_id in IN_FLIGHT)
        handed.append(len(rows))
        return rows

    monkeypatch.setattr(legacy_db, "rows", in_flight)
    finished = _run(world, job_id)
    assert finished["state"] == "SUCCEEDED", finished["problem"]
    assert _rows(world, select(migration_batch.c.status)) == [{"status": "IMPORTED"}]
    assert handed == [16]
    assert _rows(world, select(func.count().label("n")).select_from(migrated_legacy_row)) == [
        {"n": 16}
    ]

    someone = colleague(world.tenant_id, "tess")
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=someone.membership_id,
            role_code="tenant_admin",
        )
    tess = enrolled(app, clock, someone)
    refused = post(app, f"{FILES_PATH}/{file_id}/shred", tess, {"reason": SHRED_REASON})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert [error["rule_id"] for error in refused.json()["errors"]] == [
        "FILE_SHRED_APPROVAL_REQUIRED"
    ]
    assert _shredded_at(world, file_id) is None
