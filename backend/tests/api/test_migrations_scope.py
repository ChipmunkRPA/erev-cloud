"""A legacy migration under a role held for named entities (item SCOPE-WORKSPACE-LISTS-1, part
(c2); supervisor rulings R-28 and R-115 (c) and the supervisor's ruling of 2026-10-01, answer Q2;
03 REQ-PLT-012; 04 API-C-03, API-R-48, T-MIG-01).

A migration is an act on the workspace: a legacy database holds the contracts of any entity, its
batch carries no entity (T-MIG-01 is RLS-T) and its import creates entities. So every route of
``/migrations`` asks ``migration.run`` for ALL entities: a holder of named entities is answered
403 ``forbidden`` after one DENIED event that states the route and the scope it asks for, never
a list that looks filtered. A reader per batch, by the entities its mapping names, is item
MIG-BATCH-ENTITY-SCOPE-1 and not built here.

WLD-K-04 (``worlds.k04_saltmarsh``; AVM-UK and AVM-US). Mira is Revenue Accountant of AVM-US
alone, granted through the product (``POST /role-assignments``, requested by Marcus, approved by
Grace); Maya is Revenue Accountant of all entities. The legacy database is WLD-F-15
``backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db``, uploaded by Maya.

Measured before the item, with the same grant: Mira listed and read the batch, read its legacy
rows — the 71 legacy columns of every contract in it — and profiled and cancelled it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import migration_batch
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.db import TestDatabase
from support.http import call
from support.principals import Actor, cookie_headers
from support.reference import get, post
from support.worlds import AVM_US
from tests.api.test_tenant_wide_acts_scope import denials, slug
from tests.domain.reports.test_entity_scoped_runs_db import scoped, second_admin

ROOT: Final = Path(__file__).resolve().parents[3]
FIXTURE: Final = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
PERMISSION: Final = "migration.run"
FILES: Final = "/api/v1/files"
MIGRATIONS: Final = "/api/v1/migrations"
ONE: Final = f"{MIGRATIONS}/{{migration_id}}"
# the ten routes of 04 API-R-48, as the router declares them: method, route template
ROUTES: Final = (
    ("GET", MIGRATIONS),
    ("POST", MIGRATIONS),
    ("GET", f"{MIGRATIONS}/field-mapping"),
    ("GET", ONE),
    ("POST", f"{ONE}/profile"),
    ("POST", f"{ONE}/import"),
    ("POST", f"{ONE}/reconcile"),
    ("POST", f"{ONE}/cancel"),
    ("GET", f"{ONE}/reconciliation-lines"),
    ("GET", f"{ONE}/legacy-rows"),
)
IMPORT_BODY: Final = {"mode": "OPENING_BALANCES", "cutover_date": "2023-01-31"}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def uploaded(app: FastAPI, actor: Actor) -> str:
    """The legacy database stored with purpose ``LEGACY_DATABASE``; the file's id."""
    response = call(
        app,
        "POST",
        FILES,
        data={"purpose": "LEGACY_DATABASE"},
        files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "application/octet-stream")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def asked(app: FastAPI, actor: Actor, method: str, template: str, migration_id: str) -> Any:
    path = template.replace("{migration_id}", migration_id)
    if method == "GET":
        return get(app, path, actor)
    body: dict[str, Any] = {}
    if template == MIGRATIONS:
        body = {"mode": "OPENING_BALANCES", "source_file_id": migration_id}
    elif template.endswith("/import"):
        body = dict(IMPORT_BODY)
    return post(app, path, actor, body)


@pytest.mark.slow
def test_every_route_of_a_migration_is_for_holders_of_all_entities(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Each of the ten routes answers Mira, who holds ``migration.run`` for AVM-US alone, 403
    ``forbidden`` after one DENIED event naming the route and the scope ``"*"``, and nothing of
    the batch changes; Maya, who holds it for all entities, is answered by the route itself.
    Before: every route answered Mira as it answers Maya."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    grace = second_admin(world, clock)
    mira = scoped(world, clock, grace, "mira", ("revenue_accountant", AVM_US))
    maya = world.maya

    created = post(
        app, MIGRATIONS, maya, {"mode": "OPENING_BALANCES", "source_file_id": uploaded(app, maya)}
    )
    assert created.status_code == 201, created.text
    migration_id = str(created.json()["id"])

    def batch() -> dict[str, Any]:
        (row,) = world.place.rows(select(migration_batch))
        return row

    before = batch()
    for method, template in ROUTES:
        refused = asked(app, mira, method, template, migration_id)
        assert (refused.status_code, slug(refused)) == (403, "forbidden"), (
            method,
            template,
            refused.text,
        )
    assert denials(world, PERMISSION) == [
        {"method": method, "path": template, "scope": "*", "permission": PERMISSION}
        for method, template in ROUTES
    ]
    assert batch() == before

    # the holder for all entities: each route answers with its own result
    answered: dict[tuple[str, str], tuple[int, str]] = {}
    for method, template in ROUTES:
        if template == MIGRATIONS and method == "POST":
            continue  # asked above: 201
        response = asked(app, maya, method, template, migration_id)
        answered[method, template] = (response.status_code, slug(response))
    assert answered == {
        ("GET", MIGRATIONS): (200, ""),
        ("GET", f"{MIGRATIONS}/field-mapping"): (200, ""),
        ("GET", ONE): (200, ""),
        ("POST", f"{ONE}/profile"): (202, ""),
        # the batch is PROFILING, its job not run: the commands' own refusals, past the guard
        ("POST", f"{ONE}/import"): (409, "invalid-transition"),
        ("POST", f"{ONE}/reconcile"): (409, "invalid-transition"),
        ("POST", f"{ONE}/cancel"): (200, ""),
        ("GET", f"{ONE}/reconciliation-lines"): (200, ""),
        ("GET", f"{ONE}/legacy-rows"): (200, ""),
    }
    listed = get(app, MIGRATIONS, maya)
    assert [item["id"] for item in listed.json()["items"]] == [migration_id]
    # no denial but Mira's: one per route
    assert len(denials(world, PERMISSION)) == len(ROUTES)
