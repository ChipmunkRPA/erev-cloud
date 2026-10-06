"""CLO-3 soft close commands (PRD §5.2 SM-07, §5.3 BR-CLS-04, BR-DAT-07; 04 §16.8 "Period
commands", T-REF-07, table 3.4-R, DB-07; 03 REQ-CLS-001, REQ-CLS-003; dev-guide DG-CMD-06;
BUILD_SPEC CLO-3).

Worlds: Maya (Revenue Accountant, which holds ``period.close``) keeps AVM-US on a January calendar
with FY2026-P01 to P09 open (``support.factories.world_calendar``). The import test uses
``support.factories.k11_world`` with K-11 delivered and the API client ``svc-netsuite`` under an
``AUTO-IMP-01`` rule. The lock and reopen commands are post-rc (CLO-6, CLO-7), so a test that needs
a ``closed`` or ``reopened`` state writes the T-REF-07 transitions itself, as DB-07 requires.
"""

from __future__ import annotations

import dataclasses
import io
from collections.abc import Mapping
from datetime import UTC
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    approval_decision,
    approval_request,
    audit_event,
    job,
    period_lock,
    period_state,
    period_state_transition,
)
from erev_api.domain.imports import commit, upload
from erev_api.domain.imports.csv_v2.framework import flatten
from erev_api.domain.imports.csv_v2.progress_events import ProgressEventIn
from erev_api.enums import FilePurpose, PrincipalKind, RuleSetKind
from erev_api.files.store import LocalFileStore, store_file
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.schemas.imports import ImportCreateIn, ImportSubmitIn
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support.db import TestDatabase
from support.factories import (
    K11_EXTERNAL_ID,
    ImportWorld,
    K11World,
    delivered_k11,
    k11_world,
    maya_principal,
    run_import_job,
    world_calendar,
)
from support.principals import Actor, member
from support.reference import PERIODS, fields, holding, periods, post, slug
from support.rows import (
    CloseParts,
    api_client_values,
    insert_approval_request,
    period_lock_values,
    period_state_transition_values,
    publish_rule_set,
)

PROBE_ID = UUID("01920000-0000-7000-8000-00000000c103")
PROGRESS_HEADERS = [column.name for column in flatten(ProgressEventIn)]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def maya(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    actor = holding(app, member(keyring, clock), "revenue_accountant")
    world_calendar(app, actor)
    return actor


def _state(app: FastAPI, actor: Actor, key: str, *, entity: str = "AVM-US") -> dict[str, Any]:
    (found,) = [
        item for item in periods(app, actor, entity=entity) if item["period"]["period_key"] == key
    ]
    return found


def _command(
    app: FastAPI, actor: Actor, state: Mapping[str, Any], verb: str, body: Mapping[str, Any]
) -> Any:
    return post(
        app,
        f"{PERIODS}/{state['id']}/{verb}",
        actor,
        body,
        if_match=f'"r{state["row_version"]}"',
    )


def _forced(actor: Actor, state_id: str, *moves: tuple[str, str, str, str | None]) -> None:
    """Write T-REF-07 moves whose commands are post-rc (CLO-6, CLO-7), one transaction per move:
    an approval request, the ``period_lock`` of the move's kind, the transition naming both, and the
    projection update (DB-07)."""
    tenant_id = actor.member.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    for from_state, to_state, kind, reason_code in moves:
        with tenant_session(context) as session:
            row = (
                session.execute(select(period_state).where(period_state.c.id == UUID(state_id)))
                .mappings()
                .one()
            )
            transition_id = new_id()
            parts = CloseParts(
                calendar_id=PROBE_ID,
                entity_id=row["entity_id"],
                period_id=row["period_id"],
                period_state_transition_id=transition_id,
                approval_request_id=insert_approval_request(
                    session, tenant_id=tenant_id, entity_id=row["entity_id"]
                ),
                file_id=PROBE_ID,
            )
            lock = period_lock_values(tenant_id, parts=parts, kind=kind, reason_code=reason_code)
            session.execute(insert(period_lock).values(**lock))
            session.execute(
                insert(period_state_transition).values(
                    **period_state_transition_values(
                        tenant_id,
                        period_state_id=row["id"],
                        entity_id=row["entity_id"],
                        period_id=row["period_id"],
                        from_state=from_state,
                        to_state=to_state,
                        id=transition_id,
                        reason_code=reason_code,
                        approval_request_id=parts.approval_request_id,
                        period_lock_id=lock["id"],
                    )
                )
            )
            session.execute(
                update(period_state)
                .where(period_state.c.id == row["id"])
                .values(state=to_state, updated_by_kind=PrincipalKind.SYSTEM.value)
            )


def _rows(actor: Actor, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=actor.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def test_start_close_open_to_closing(app: FastAPI, maya: Actor) -> None:
    september = _state(app, maya, "FY2026-P09")
    moved = _command(app, maya, september, "start-close", {"comment": "September close started"})
    assert moved.status_code == 200, moved.text
    version = september["row_version"] + 1
    assert (moved.json()["state"], moved.json()["row_version"], moved.headers["ETag"]) == (
        "closing",
        version,
        f'"r{version}"',
    )
    transitions = _rows(
        maya,
        select(period_state_transition).where(
            period_state_transition.c.period_state_id == UUID(september["id"]),
            period_state_transition.c.to_state == "closing",
        ),
    )
    assert len(transitions) == 1
    (row,) = transitions
    assert (str(row["from_state"]), row["comment"], row["reason_code"]) == (
        "open",
        "September close started",
        None,
    )
    assert (row["created_by"], str(row["created_by_kind"])) == (maya.member.user_id, "USER")
    assert row["created_at"].utcoffset() == UTC.utcoffset(None)
    events = _rows(
        maya,
        select(audit_event).where(
            audit_event.c.action == "period.start_close",
            audit_event.c.object_id == UUID(september["id"]),
        ),
    )
    assert len(events) == 1
    (event,) = events
    assert (event["actor_id"], event["before"], event["comment"]) == (
        maya.member.user_id,
        {"state": "open"},
        "September close started",
    )
    assert (event["after"]["state"], event["after"]["period_state_transition_id"]) == (
        "closing",
        str(row["id"]),
    )


def test_start_close_from_reopened(app: FastAPI, maya: Actor) -> None:
    august = _state(app, maya, "FY2026-P08")
    started = _command(app, maya, august, "start-close", {})
    assert started.status_code == 200, started.text
    _forced(
        maya,
        august["id"],
        ("closing", "closed", "LOCK", None),
        ("closed", "reopened", "REOPEN", "ERROR_CORRECTION"),
    )
    reopened = _state(app, maya, "FY2026-P08")
    assert reopened["state"] == "reopened"
    moved = _command(app, maya, reopened, "start-close", {"comment": "Second pass"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["state"] == "closing"
    latest = _rows(
        maya,
        select(period_state_transition.c.from_state, period_state_transition.c.comment)
        .where(period_state_transition.c.period_state_id == UUID(august["id"]))
        .order_by(period_state_transition.c.id.desc())
        .limit(1),
    )
    assert [(str(item["from_state"]), item["comment"]) for item in latest] == [
        ("reopened", "Second pass")
    ]


def test_cancel_close_reason_subset(app: FastAPI, maya: Actor) -> None:
    september = _state(app, maya, "FY2026-P09")
    started = _command(app, maya, september, "start-close", {})
    assert started.status_code == 200, started.text
    closing = started.json()
    refused = _command(app, maya, closing, "cancel-close", {"reason_code": "ERROR_CORRECTION"})
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused)[0] == ("reason_code", "REASON_CODE_NOT_ALLOWED")
    assert _state(app, maya, "FY2026-P09")["state"] == "closing"
    ended = _command(
        app, maya, closing, "cancel-close", {"reason_code": "CLOSE_RESTARTED", "comment": "Redo"}
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["state"] == "open"
    restarted = _rows(
        maya,
        select(period_state_transition.c.reason_code, period_state_transition.c.from_state).where(
            period_state_transition.c.period_state_id == UUID(september["id"]),
            period_state_transition.c.to_state == "open",
            period_state_transition.c.from_state == "closing",
        ),
    )
    assert [(str(item["reason_code"]), str(item["from_state"])) for item in restarted] == [
        ("CLOSE_RESTARTED", "closing")
    ]
    events = _rows(
        maya, select(audit_event.c.reason_code).where(audit_event.c.action == "period.cancel_close")
    )
    assert [item["reason_code"] for item in events] == ["CLOSE_RESTARTED"]


def test_start_close_from_future_refused(app: FastAPI, maya: Actor) -> None:
    october = _state(app, maya, "FY2026-P10")
    assert october["state"] == "future"
    refused = _command(app, maya, october, "start-close", {})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["code"] == "EREV-PER-001"
    assert fields(refused) == [(None, "DB-07")]
    assert _state(app, maya, "FY2026-P10")["state"] == "future"


# --- BR-DAT-07: imports into a closing period wait for human review ------------------------------


def _progress_csv(effective_date: str, quantity: str) -> bytes:
    row = dict.fromkeys(PROGRESS_HEADERS, "")
    row |= {
        "contract": K11_EXTERNAL_ID,
        "event_type": "DELIVERY_RECORDED",
        "effective_date": effective_date,
        "obligation_key": "O1",
        "quantity": quantity,
        "trigger": "DELIVERY",
    }
    buffer = io.StringIO()
    buffer.write(",".join(PROGRESS_HEADERS) + "\n")
    buffer.write(",".join(row.values()) + "\n")
    return buffer.getvalue().encode("utf-8")


def _diffed_upload(
    world: K11World, imports: ImportWorld, service: Any, name: str, content: bytes
) -> UUID:
    with world.place.uow(service) as uow:
        stored = store_file(
            uow,
            purpose=FilePurpose.IMPORT_SOURCE,
            stream=io.BytesIO(content),
            original_filename=name,
            media_type="text/csv",
        )
        created = upload.create_import(
            uow, body=ImportCreateIn(file_id=stored["id"], template_code="progress_events")
        )
        uow.commit()
    run_import_job(imports, created.job.id)
    (diff_job,) = imports.rows(
        select(job.c.id).where(job.c.subject_id == created.import_id, job.c.kind == "IMPORT_DIFF")
    )
    run_import_job(imports, diff_job["id"])
    return created.import_id


def _submitted(world: K11World, service: Any, import_id: UUID) -> Any:
    with world.place.uow(service) as uow:
        out = commit.submit_import(uow, import_id=import_id, body=ImportSubmitIn())
        uow.commit()
    return out


def test_soft_close_suspends_import_auto_approval(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k11_world(app, keyring, clock, files)
    delivered_k11(world)
    maya = world.place.author
    tenant_id = world.place.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    # The client's stored scopes hold the write permission of the template it uploads: an import
    # runs within its uploader's own scope for that permission (04 §16.6 rev 1.107; ruling R-29).
    permissions = frozenset({"import.upload", "contract.read", "event.record"})
    client = api_client_values(tenant_id, name="svc-netsuite", scopes=sorted(permissions))
    with tenant_session(context) as session:
        session.execute(insert(api_client).values(**client))
        version_id, _ = publish_rule_set(
            session,
            tenant_id=tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            code="AVM-AUTO-APPROVAL",
            rules=[
                {
                    "rule_key": "AUTO-IMP-01",
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": "IMPORT_COMMIT"},
                        {"field": "source.channel", "op": "eq", "value": "API_CLIENT"},
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
        )
    service = dataclasses.replace(
        maya_principal(maya.member),
        kind=PrincipalKind.API_CLIENT,
        id=UUID(str(client["id"])),
        membership_id=None,
        display_name="svc-netsuite",
        roles=(),
        permissions=permissions,
        permission_scopes=MappingProxyType({code: "*" for code in permissions}),
    )
    imports = ImportWorld(
        app=app,
        actor=maya,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )

    # 20 more gateway units delivered on 20 Sep 2026: the effect posts into FY2026-P09.
    september_import = _diffed_upload(
        world, imports, service, "svc-netsuite-progress-sep.csv", _progress_csv("2026-09-20", "20")
    )
    september = _state(app, maya, "FY2026-P09", entity="AVM-DE")
    started = _command(app, maya, september, "start-close", {"comment": "September close"})
    assert started.status_code == 200, started.text

    held = _submitted(world, service, september_import)
    assert held.status == "SUBMITTED"
    assert held.approval_request_id is not None
    (request,) = imports.rows(
        select(approval_request.c.status, approval_request.c.subject_type).where(
            approval_request.c.id == held.approval_request_id
        )
    )
    assert (str(request["status"]), str(request["subject_type"])) == ("PENDING", "IMPORT_COMMIT")
    assert (
        imports.rows(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == held.approval_request_id
            )
        )
        == []
    )

    # Control: an upload whose effect posts into the open FY2026-P08 is still auto-approved.
    august_import = _diffed_upload(
        world, imports, service, "svc-netsuite-progress-aug.csv", _progress_csv("2026-08-20", "10")
    )
    approved = _submitted(world, service, august_import)
    assert approved.status == "APPROVED"
    (decision,) = imports.rows(
        select(approval_decision.c.decision, approval_decision.c.auto_rule_set_version_id).where(
            approval_decision.c.approval_request_id == approved.approval_request_id
        )
    )
    assert (str(decision["decision"]), decision["auto_rule_set_version_id"]) == (
        "AUTO_APPROVE",
        version_id,
    )
