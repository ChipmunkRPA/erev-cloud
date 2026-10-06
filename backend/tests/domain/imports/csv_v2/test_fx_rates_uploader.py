"""The uploader of an ``fx_rates`` import does not decide the rate set version it created
(supervisor ruling R-98, the authorship family of R-66 (1); 04 T-REF-11 ``import_upload_id``,
§16.10 rev 1.104; PRD §2.5 routing row ``FX_RATE_SET_VERSION``; 03 REQ-PLT-011, REQ-PLT-016,
REQ-REF-006; control CTL-031).

The commit of the import creates the version and submits it as SYSTEM on behalf of the uploader,
so the ``FX_RATE_SET_VERSION`` request names no preparer. The uploader wrote its rates all the
same: they are an excluded decider of the request, in person and as the delegator of whoever
decides, and the request is not waiting for them. A stored ``AUTO_APPROVAL`` rule that names the
subject does not approve it either: the subject is not on the allow-list of REQ-PLT-016.

World ``support.factories.import_world``: Maya uploads and is a Controller as well
(``config.approve``); Priya approves imports; Carmen is another Controller.
"""

from __future__ import annotations

import csv
import dataclasses
import io
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.approvals.engine import EXCLUDED_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_delegation,
    approval_request,
    fx_rate_set_version,
)
from erev_api.domain.imports.csv_v2.framework import flatten
from erev_api.domain.imports.csv_v2.fx_rates import FxRatesIn
from erev_api.enums import RuleSetKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.factories import ImportWorld, import_world, run_import_job
from support.legacy_replay import diffed, job_of, shown, submit
from support.principals import Actor, colleague, enrolled
from support.reference import APPROVALS, approve, assign, calendar, get, post, put, slug
from support.rows import approval_delegation_values, publish_rule_set


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def csv_bytes(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def person(world: ImportWorld, clock: FrozenClock, name: str, *roles: str) -> Actor:
    someone = colleague(world.tenant_id, name)
    for code in roles:
        assign(someone, code)
    return enrolled(world.app, clock, someone)


def waiting_for(world: ImportWorld, someone: Actor) -> set[str]:
    listed = get(world.app, APPROVALS, someone, {"assigned_to_me": "true"})
    assert listed.status_code == 200, listed.text
    return {str(item["id"]) for item in listed.json()["items"]}


def can_decide(world: ImportWorld, request_id: str, someone: Actor) -> bool:
    shown_to = get(world.app, f"{APPROVALS}/{request_id}", someone)
    assert shown_to.status_code == 200, shown_to.text
    return bool(shown_to.json()["can_decide"])


@pytest.mark.control("CTL-031")
def test_r98_the_uploader_of_an_fx_rates_import_does_not_decide_its_rate_set_version(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Maya uploads the rates and holds ``config.approve`` herself. After the import is approved
    and committed the version waits for its own approval, submitted by SYSTEM: not auto-approved
    although a stored rule names the subject, not waiting for Maya, and refused to her — 403
    ``self-approval`` — in person and through Dana, to whom she delegated ``config.approve``.
    Carmen, another Controller, approves it and the rate resolves.

    Fail-first: without the excluded decider Maya's own approval puts her rates in force."""
    base = import_world(app, keyring, clock, files)
    assign(base.actor.member, "controller")
    world = dataclasses.replace(base, actor=enrolled(app, clock, base.actor.member))
    maya = world.actor
    calendar(app, maya)
    priya = person(world, clock, "priya", "revenue_reviewer")
    carmen = person(world, clock, "carmen", "controller", "tenant_admin")
    dana = person(world, clock, "dana")
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        # A stored rule authoring would refuse (R-26 (b)): it names a subject off the allow-list.
        publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            code="WS-AUTO-FX",
            rules=[
                {
                    "rule_key": "AUTO-FX-01",
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": "FX_RATE_SET_VERSION"}
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
        )
        delegation = approval_delegation_values(
            world.tenant_id,
            delegator_membership_id=maya.member.membership_id,
            delegate_membership_id=dana.member.membership_id,
            valid_from=clock.now() - timedelta(days=1),
            valid_to=clock.now() + timedelta(days=29),
        )
        delegation["permissions"] = ["config.approve"]
        session.execute(insert(approval_delegation).values(**delegation))
    enabled = put(app, "/api/v1/tenant-currencies", carmen, {"currency_codes": ["USD", "EUR"]})
    assert enabled.status_code == 200, enabled.text
    created = post(
        app,
        "/api/v1/fx-rate-sets",
        maya,
        {"code": "AVM-RATES-SPOT", "name": "Spot rates", "rate_type": "spot"},
    )
    assert created.status_code == 201, created.text
    headers = [column.name for column in flatten(FxRatesIn)]
    row = dict.fromkeys(headers, "")
    row |= {
        "fx_rate_set_code": "AVM-RATES-SPOT",
        "coverage_from": "2026-09-01",
        "coverage_to": "2026-09-30",
        "lines.base_currency": "EUR",
        "lines.quote_currency": "USD",
        "lines.rate": "1.105",
        "lines.effective_date": "2026-09-12",
    }
    import_id = diffed(
        world, "avm-rates-2026-09.csv", csv_bytes(headers, [list(row.values())]), "fx_rates"
    )
    submitted = submit(world, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, str(submitted.json()["approval_request_id"]), priya)
    assert decided.status_code == 200, decided.text
    run_import_job(world, job_of(world, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(world, import_id)["status"] == "COMMITTED"

    (version,) = world.rows(
        select(fx_rate_set_version.c.id, fx_rate_set_version.c.status).where(
            fx_rate_set_version.c.import_upload_id == UUID(import_id)
        )
    )
    assert str(version["status"]) == "SUBMITTED"
    (request,) = world.rows(
        select(
            approval_request.c.id,
            approval_request.c.status,
            approval_request.c.preparer_id,
            approval_request.c.preparer_kind,
        ).where(
            approval_request.c.subject_type == "FX_RATE_SET_VERSION",
            approval_request.c.subject_id == version["id"],
        )
    )
    # Submitted by SYSTEM for the uploader, and waiting for a person in spite of the stored rule.
    assert (str(request["status"]), request["preparer_id"], str(request["preparer_kind"])) == (
        "PENDING",
        None,
        "SYSTEM",
    )
    request_id = str(request["id"])

    def decisions() -> list[str]:
        found = world.rows(
            select(approval_decision.c.decision).where(
                approval_decision.c.approval_request_id == request["id"]
            )
        )
        return [str(item["decision"]) for item in found]

    assert decisions() == []
    assert can_decide(world, request_id, maya) is False
    assert request_id not in waiting_for(world, maya)
    own = approve(app, request_id, maya)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    assert own.json()["detail"] == EXCLUDED_DETAIL
    assert can_decide(world, request_id, dana) is False
    through = approve(app, request_id, dana)
    assert (through.status_code, slug(through)) == (403, "self-approval"), through.text
    assert decisions() == []
    query = {"rate_type": "spot", "base": "EUR", "quote": "USD", "date": "2026-09-12"}
    before = get(app, "/api/v1/fx-rates", maya, query)
    assert (before.status_code, before.json()["items"]) == (200, []), before.text

    # Positive control: another Controller decides, and the rate is in force.
    assert can_decide(world, request_id, carmen) is True
    assert request_id in waiting_for(world, carmen)
    approved = approve(app, request_id, carmen)
    assert approved.status_code == 200, approved.text
    assert decisions() == ["APPROVE"]
    after = get(app, "/api/v1/fx-rates", maya, query)
    assert after.status_code == 200, after.text
    assert [
        (item["base_currency"], item["quote_currency"], Decimal(item["rate"]))
        for item in after.json()["items"]
    ] == [("EUR", "USD", Decimal("1.105"))]
