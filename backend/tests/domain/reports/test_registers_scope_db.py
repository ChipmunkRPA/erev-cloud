"""The registers of requests and of the chain under roles held for named entities (item
SCOPE-WORKSPACE-LISTS-1; supervisor rulings R-13, R-28 and R-121 (c); 03 REQ-PLT-012; 04 T-PLT-17
rev 1.104, API-R-41; SCREENS_B RPT-23, RPT-26, RPT-44).

WLD-K-04 (``worlds.k04_saltmarsh``): two entities, AVM-UK and AVM-US. Roles for named entities are
granted through the product (``test_entity_scoped_runs_db.scoped``: requested by Marcus, approved
by Grace). Six approval requests, each pending and approved, are rows of the test world — no one
command of the product makes each shape on demand: a request of AVM-UK and one of AVM-US by
``entity_id``; of AVM-US alone and of both entities by ``entity_ids``; of all entities; and a
tenant-level one.

Measured before the item, in the probe of its pre-build line: a run of the approvals register and
of the configuration change register over ONE entity stated the requests of the other entity, of
both and of all entities — every request whose ``entity_id`` is null — with their summaries; and
a declared permission was asked at any scope, so a Viewer of two entities who audits one ran the
approvals register over both. The chain verification report (RPT-44) stays at any scope: it
states counts and chain values, no entity's data.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import approval_request, approval_step, audit_event, role
from erev_api.enums import ApprovalRequestStatus, AuditOutcome
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support import worlds
from support.db import TestDatabase
from support.principals import Actor
from support.reference import approve, get, post
from support.rows import approval_request_values, approval_step_values
from support.worlds import AVM_UK, AVM_US, REPORT_RUNS, report_run
from tests.domain.reports.test_entity_scoped_runs_db import ASSIGNMENTS, scoped, second_admin

APPROVALS: Final = "approvals_register"
CONFIG_CHANGES: Final = "config_change_register"
VERIFICATIONS: Final = "chain_verification_report"
EXPORT: Final = "audit_log_export"
ROLLFORWARD: Final = "contract_balance_rollforward"
JUNE: Final = "FY2026-P06"
UK, US, US_ALONE, BOTH, ALL, TENANT = "uk", "us", "us alone", "both", "all", "tenant"
EVERY: Final = frozenset({UK, US, US_ALONE, BOTH, ALL, TENANT})
PENDING: Final = ApprovalRequestStatus.PENDING
APPROVED: Final = ApprovalRequestStatus.APPROVED


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def labelled_requests(k04: worlds.K04World, clock: FrozenClock) -> dict[str, tuple[str, str]]:
    """The six requests in two statuses, written as rows; request number → (label, status)."""
    uk, us = k04.uk_entity_id, k04.us_entity_id
    shapes: dict[str, dict[str, Any]] = {
        UK: {"entity_id": uk},
        US: {"entity_id": us},
        US_ALONE: {"entity_ids": [us]},
        BOTH: {"entity_ids": sorted([uk, us], key=str)},
        ALL: {"is_all_entities": True},
        TENANT: {},
    }
    tenant_id = k04.report.tenant_id
    numbers: dict[str, tuple[str, str]] = {}
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        for label, entities in shapes.items():
            for status in (PENDING, APPROVED):
                row = approval_request_values(
                    tenant_id,
                    status=status,
                    summary=f"Scope witness: {label}, {status.value}",
                    **entities,
                )
                row["submitted_at"] = clock.now() - timedelta(minutes=2)
                if row["decided_at"] is not None:
                    row["decided_at"] = clock.now() - timedelta(minutes=1)
                session.execute(insert(approval_request).values(**row))
                session.execute(
                    insert(approval_step).values(
                        **approval_step_values(tenant_id, approval_request_id=UUID(str(row["id"])))
                    )
                )
                numbers[str(row["request_no"])] = (label, status.value)
    return numbers


def today(clock: FrozenClock) -> dict[str, str]:
    day = clock.now().date().isoformat()
    return {"from_date": day, "to_date": day}


def stated(
    world: worlds.ReportWorld,
    numbers: dict[str, tuple[str, str]],
    code: str,
    parameters: dict[str, Any],
    *,
    actor: Actor | None = None,
) -> tuple[dict[str, Any], set[tuple[str, str]]]:
    """A run of a register of requests and the labelled requests its rows state."""
    run, rows = report_run(world, code, parameters, actor=actor)
    assert len(rows) < 200  # one page holds the register
    return run, {numbers[row["request_no"]] for row in rows if row["request_no"] in numbers}


def both_statuses(*labels: str) -> set[tuple[str, str]]:
    return {(label, status.value) for label in labels for status in (PENDING, APPROVED)}


def decided(*labels: str) -> set[tuple[str, str]]:
    return {(label, APPROVED.value) for label in labels}


def denials(world: worlds.ReportWorld, action: str) -> list[dict[str, Any]]:
    """The details of the DENIED events of ``action``, oldest first."""
    rows = world.place.rows(
        select(audit_event.c.detail)
        .where(
            audit_event.c.action == action,
            audit_event.c.outcome == AuditOutcome.DENIED.value,
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [dict(row["detail"]) for row in rows]


@pytest.mark.slow
def test_a_register_of_requests_states_the_requests_its_entities_cover(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """RPT-26 and RPT-23 (rulings R-28 and R-121 (c)): a request is stated when the run's entities
    cover EVERY entity it names, a request of all entities only by a run that names every entity
    of the workspace, a tenant-level request always. Una, Auditor for AVM-UK alone, gets the
    register of AVM-UK and nothing of AVM-US. Before: a run over AVM-UK stated five of the six —
    the request of AVM-US alone, of both entities and of all entities among them, each with its
    summary. The export of the log (RPT-43) refuses Una at the start, with one DENIED event that
    states the scope asked; the chain verification report (RPT-44) runs for her."""
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = k04.report
    una = scoped(world, clock, second_admin(world, clock), "una", ("auditor", AVM_UK))
    numbers = labelled_requests(k04, clock)
    span = today(clock)

    # RPT-26: every status. A run of one entity, of the other, and of both (every entity).
    _, of_uk = stated(world, numbers, APPROVALS, {**span, "entity_codes": [AVM_UK]})
    assert of_uk == both_statuses(UK, TENANT)
    _, of_us = stated(world, numbers, APPROVALS, {**span, "entity_codes": [AVM_US]})
    assert of_us == both_statuses(US, US_ALONE, TENANT)
    _, of_both = stated(world, numbers, APPROVALS, span)
    assert of_both == both_statuses(*EVERY)
    hers, una_sees = stated(world, numbers, APPROVALS, span, actor=una)
    assert [item["code"] for item in hers["entity_scope"]] == [AVM_UK]
    assert una_sees == of_uk

    # RPT-23: the decided requests of the configuration subjects, under the same rule.
    _, changes_of_uk = stated(world, numbers, CONFIG_CHANGES, {**span, "entity_codes": [AVM_UK]})
    assert changes_of_uk == decided(UK, TENANT)
    _, changes_of_both = stated(world, numbers, CONFIG_CHANGES, span)
    assert changes_of_both == decided(*EVERY)
    _, una_changes = stated(world, numbers, CONFIG_CHANGES, span, actor=una)
    assert una_changes == changes_of_uk

    # RPT-43 states the events themselves and asks for all entities; RPT-44 states counts and
    # chain values and runs at any scope, as the verifications are read (ruling of 2026-10-01).
    export = {"report_code": EXPORT, "parameters": {}, "output_format": "JSON"}
    refused = post(world.app, REPORT_RUNS, una, export)
    assert refused.status_code == 403, refused.text
    assert refused.json()["type"].endswith("/forbidden")
    assert denials(world, "audit.read") == [
        {"report_code": EXPORT, "scope": "*", "permission": "audit.read"}
    ]
    verifications = {"report_code": VERIFICATIONS, "parameters": {}, "output_format": "JSON"}
    assert post(world.app, REPORT_RUNS, una, verifications).status_code == 202


def viewer_of_both(world: worlds.ReportWorld, someone: Actor, approver: Actor) -> None:
    """The Viewer role for AVM-UK and AVM-US in one assignment — a member holds a role once, with
    the entities it names — requested by Marcus and approved by ``approver``."""
    role_id = world.place.scalar(select(role.c.id).where(role.c.code == "viewer"))
    granted = post(
        world.app,
        ASSIGNMENTS,
        world.marcus,
        {
            "membership_id": str(someone.member.membership_id),
            "role_id": str(role_id),
            "is_all_entities": False,
            "entity_codes": [AVM_UK, AVM_US],
        },
    )
    assert granted.status_code == 201, granted.text
    approved = approve(world.app, granted.json()["approval_request_id"], approver)
    assert approved.status_code == 200, approved.text


def refusal(
    world: worlds.ReportWorld, actor: Actor, code: str, parameters: dict[str, Any]
) -> list[tuple[str, str]]:
    started = post(
        world.app,
        REPORT_RUNS,
        actor,
        {"report_code": code, "parameters": parameters, "output_format": "JSON"},
    )
    assert started.status_code == 422, started.text
    return [(error["field"], error["message"]) for error in started.json()["errors"]]


@pytest.mark.slow
def test_a_run_names_no_entity_outside_a_permission_its_report_declares(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Rulings R-13 and R-28: the approvals register runs under ``report.run`` and declares
    ``audit.read``. Vik is Viewer for AVM-UK and AVM-US and Auditor for AVM-UK alone: his run
    takes AVM-UK — the entities inside both scopes — AVM-US answers as a code that names no
    entity, and a stored run of AVM-US is not his to read, although a report that declares
    nothing takes AVM-US from him. Before: the declared permission was asked at any scope, so
    his run of the approvals register took both entities."""
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = k04.report
    grace = second_admin(world, clock)
    vik = scoped(world, clock, grace, "vik", ("auditor", AVM_UK))
    viewer_of_both(world, vik, grace)
    numbers = labelled_requests(k04, clock)
    span = today(clock)

    his, vik_sees = stated(world, numbers, APPROVALS, span, actor=vik)
    assert [item["code"] for item in his["entity_scope"]] == [AVM_UK]
    assert vik_sees == both_statuses(UK, TENANT)
    assert refusal(world, vik, APPROVALS, {**span, "entity_codes": [AVM_US]}) == refusal(
        world, vik, APPROVALS, {**span, "entity_codes": ["AVM-FR"]}
    )
    assert refusal(world, vik, CONFIG_CHANGES, {**span, "entity_codes": [AVM_US]}) == refusal(
        world, vik, CONFIG_CHANGES, {**span, "entity_codes": ["AVM-FR"]}
    )

    # a report that declares no permission takes the entity his run permission covers
    rollforward = {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "from_period_key": JUNE,
        "to_period_key": JUNE,
    }
    plain, _ = report_run(world, ROLLFORWARD, rollforward, actor=vik)
    assert [item["code"] for item in plain["entity_scope"]] == [AVM_US]

    # a stored run of AVM-US: Maya's register is not his to read or to list, her rollforward is
    register, _ = report_run(world, APPROVALS, {**span, "entity_codes": [AVM_US]})
    theirs, _ = report_run(world, ROLLFORWARD, rollforward)
    assert get(world.app, f"{REPORT_RUNS}/{register['id']}", vik).status_code == 404
    assert get(world.app, f"{REPORT_RUNS}/{register['id']}/data", vik).status_code == 404
    assert get(world.app, f"{REPORT_RUNS}/{theirs['id']}", vik).status_code == 200
    listed = get(world.app, REPORT_RUNS, vik, {"limit": "200"})
    assert listed.status_code == 200, listed.text
    ids = {item["id"] for item in listed.json()["items"]}
    assert register["id"] not in ids and {his["id"], plain["id"], theirs["id"]} <= ids
