"""The lists of the whole workspace under a role held for named entities (item
SCOPE-WORKSPACE-LISTS-1; supervisor ruling R-28; 03 REQ-PLT-012; 04 API-R-10, API-R-11, API-R-52,
API-R-56; dev-guide DG-KRN-AUTH-03, DG-KRN-AUTH-05).

An audit event, a job, an execution of a workspace control and a source record carry no entity
and may hold the data of any. A holder of the guarding permission for named entities is therefore
refused the tenant-wide list — 403 ``forbidden``, never a list that looks filtered — keeps the
jobs he started, and reads a source record through a contract in his reach. The verifications of
the chain state counts and chain values, no entity's data: they are read at any scope, and only
the command that starts one, a tenant-wide act, asks for all entities (the supervisor's ruling of
2026-10-01 on the item's pre-build line).

WLD-K-04 (``worlds.k04_saltmarsh``): AVM-UK contracts ``SF-ORD-UK-2001``, AVM-US performs one of
its obligations. The roles for named entities are granted through the product
(``test_entity_scoped_runs_db.scoped``); Maya holds hers for all entities. The two source records
and the T-CON-02 link are rows of the test world: only an import links a contract to its source.

Measured before the item (the probe of its pre-build line): a member holding Auditor for one
entity was answered the whole audit log, its actors and the verifications, queued a verification
of the chain, was listed every job of the workspace and every control execution without an
entity, and read by id a source record linked to another entity's contract.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, contract_source_link, source_record
from erev_api.enums import AuditOutcome, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support import worlds
from support.db import TestDatabase
from support.http import call
from support.principals import Actor, cookie_headers
from support.reference import get, post
from support.rows import source_record_values
from support.worlds import AVM_UK, AVM_US, report_run
from tests.domain.reports.test_entity_scoped_runs_db import scoped, second_admin

AUDIT_READ: Final = "audit.read"
EVENTS: Final = "/api/v1/audit-events"
ACTORS: Final = "/api/v1/audit-events/actors"
VERIFICATIONS: Final = "/api/v1/audit-events/verifications"
VERIFICATION: Final = "/api/v1/audit-events/verifications/{verification_id}"
VERIFY: Final = "/api/v1/audit-events/verify"
EXECUTIONS: Final = "/api/v1/control-executions"
JOBS: Final = "/api/v1/jobs"
SOURCE_RECORDS: Final = "/api/v1/source-records"
ACCESS_LISTING: Final = "user_access_listing"
# the routes that ask for all entities: method, route template
TENANT_WIDE: Final = (
    ("GET", EVENTS),
    ("GET", ACTORS),
    ("POST", VERIFY),
    ("GET", EXECUTIONS),
)
# the reads of the chain's verifications, open at any scope
AT_ANY_SCOPE: Final = (("GET", VERIFICATIONS), ("GET", VERIFICATION))


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def asked(world: worlds.ReportWorld, actor: Actor, method: str, template: str) -> Any:
    path = template.replace("{verification_id}", str(uuid4()))
    if method == "POST":
        return post(world.app, path, actor, {})
    return get(world.app, path, actor)


def slug(response: Any) -> str:
    """The problem slug of an answer; empty for an answer that is no problem."""
    body = response.json()
    return str(body.get("type", "")).rsplit("/", 1)[-1] if isinstance(body, dict) else ""


def denials(world: worlds.ReportWorld) -> list[dict[str, Any]]:
    """The details of the DENIED events of ``audit.read``, oldest first."""
    rows = world.place.rows(
        select(audit_event.c.detail)
        .where(
            audit_event.c.action == AUDIT_READ,
            audit_event.c.outcome == AuditOutcome.DENIED.value,
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [dict(row["detail"]) for row in rows]


@pytest.mark.slow
def test_the_audit_log_and_the_control_evidence_are_for_holders_of_all_entities(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Una is Auditor for AVM-UK alone, a grant of the product. The audit log, its actors, the
    command that starts a verification of the chain and the control executions answer her 403
    ``forbidden``, each after one DENIED event that names the route and the scope it asks for;
    the verifications themselves she reads, as before. Maya, who holds ``audit.read`` for all
    entities, is answered everywhere. Before: 200 on every read, with every row, and 202 for the
    verification."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    una = scoped(world, clock, second_admin(world, clock), "una", ("auditor", AVM_UK))

    for method, template in TENANT_WIDE:
        refused = asked(world, una, method, template)
        assert (refused.status_code, slug(refused)) == (403, "forbidden"), (template, refused.text)
    assert denials(world) == [
        {"method": method, "path": template, "scope": "*", "permission": AUDIT_READ}
        for method, template in TENANT_WIDE
    ]

    # the verifications: the list, and an id that names none (the guard passes)
    assert [asked(world, una, *route).status_code for route in AT_ANY_SCOPE] == [200, 404]

    answers = {
        (method, template): asked(world, world.maya, method, template).status_code
        for method, template in (*TENANT_WIDE, *AT_ANY_SCOPE)
    }
    assert answers == {
        ("GET", EVENTS): 200,
        ("GET", ACTORS): 200,
        ("POST", VERIFY): 202,
        ("GET", EXECUTIONS): 200,
        ("GET", VERIFICATIONS): 200,
        ("GET", VERIFICATION): 404,
    }
    assert len(denials(world)) == len(TENANT_WIDE)  # no denial but Una's four


def job_ids(world: worlds.ReportWorld, actor: Actor, **params: str) -> set[str]:
    listed = get(world.app, JOBS, actor, {"limit": "200", **params})
    assert listed.status_code == 200, listed.text
    assert listed.json()["next_cursor"] is None
    return {str(item["id"]) for item in listed.json()["items"]}


@pytest.mark.slow
def test_a_member_of_one_entity_sees_the_jobs_he_started(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 API-R-11: a job is visible to the user who started it and to holders of ``audit.read``
    for all entities. Una, Auditor for AVM-UK alone, is listed the job of her own report run and
    no other; another member's job answers her 404, by id, by its subject and to the cancel
    command. Maya is listed every job. Before: ``audit.read`` at any scope opened every job, so
    Una was listed the jobs of the whole workspace."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    una = scoped(world, clock, second_admin(world, clock), "una", ("auditor", AVM_UK))
    hers, _ = report_run(world, ACCESS_LISTING, {}, actor=una)
    mayas, _ = report_run(world, ACCESS_LISTING, {})
    her_job, maya_job = str(hers["job_id"]), str(mayas["job_id"])

    assert job_ids(world, una) == {her_job}
    assert get(world.app, f"{JOBS}/{her_job}", una).status_code == 200
    assert get(world.app, f"{JOBS}/{maya_job}", una).status_code == 404
    assert job_ids(world, una, subject_type="report_run", subject_id=str(mayas["id"])) == set()
    cancelled = post(world.app, f"{JOBS}/{maya_job}/cancel", una, {})
    assert (cancelled.status_code, slug(cancelled)) == (404, "not-found")

    assert {her_job, maya_job} <= job_ids(world, world.maya)
    assert get(world.app, f"{JOBS}/{her_job}", world.maya).status_code == 200


def stored_records(k04: worlds.K04World) -> tuple[UUID, UUID]:
    """Two source records written as rows: one a T-CON-02 link ties to ``SF-ORD-UK-2001``, one no
    contract names."""
    tenant_id = k04.report.tenant_id
    linked, loose = source_record_values(tenant_id), source_record_values(tenant_id)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        session.execute(insert(source_record), [linked, loose])
        session.execute(
            insert(contract_source_link).values(
                tenant_id=tenant_id,
                id=new_id(),
                contract_id=k04.contract_id,
                source_record_id=linked["id"],
                link_role="BOOKING",
                contract_event_id=None,
                created_by_kind=PrincipalKind.SYSTEM.value,
            )
        )
    return UUID(str(linked["id"])), UUID(str(loose["id"]))


@pytest.mark.slow
def test_a_source_record_is_read_through_a_contract_in_reach(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 API-R-56: a source record is read with ``contract.read`` for all entities, or through
    a contract the caller reads that names it. Ula, Revenue Accountant for AVM-UK, reads the
    record of ``SF-ORD-UK-2001`` — AVM-UK's contract — and not the record no contract names;
    Uma, Revenue Accountant for AVM-US, reads neither, as she does not read the contract; Maya
    reads both. A record out of reach answers 404, as an id that names none. Before: 200 for
    every holder of ``contract.read`` at any scope, payload included."""
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = k04.report
    grace = second_admin(world, clock)
    ula = scoped(world, clock, grace, "ula", ("revenue_accountant", AVM_UK))
    uma = scoped(world, clock, grace, "uma", ("revenue_accountant", AVM_US))
    linked, loose = stored_records(k04)

    def read(actor: Actor, record_id: UUID) -> int:
        answered = call(
            world.app,
            "GET",
            f"{SOURCE_RECORDS}/{record_id}",
            headers=cookie_headers(actor.token, key=False),
        )
        if answered.status_code == 404:
            assert slug(answered) == "not-found"
        return answered.status_code

    assert get(world.app, f"/api/v1/contracts/{k04.contract_id}", ula).status_code == 200
    assert get(world.app, f"/api/v1/contracts/{k04.contract_id}", uma).status_code == 404
    assert (read(ula, linked), read(ula, loose)) == (200, 404)
    assert (read(uma, linked), read(uma, loose)) == (404, 404)
    assert (read(world.maya, linked), read(world.maya, loose)) == (200, 200)
    assert read(world.maya, uuid4()) == 404
