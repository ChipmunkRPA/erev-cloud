"""API-R-52 control evidence (04 §15.3 API-R-52, T-PLT-39, T-PLT-38; 03 REQ-CTL-002; BUILD_SPEC
SOP-1). Maya reads executions as an auditor holding ``audit.read``; Victor is a viewer without it.
The executions are recorded through ``record_execution`` in units of work at chosen instants.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.enums import ControlResult, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

EXECUTIONS = "/api/v1/control-executions"
RELEASES = "/api/v1/releases"
PROBLEM_BASE = "https://erev.dev/problems/"
ITEM_KEYS = {
    "id",
    "control_id",
    "run_ref_type",
    "run_ref_id",
    "entity_id",
    "book_code",
    "period_id",
    "population_count",
    "exception_count",
    "result",
    "detail",
    "exceptions_file_id",
    "engine_release_id",
    "executed_at",
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    """The tests/api convention: each module builds its own application over the committed
    database (as test_account_mappings_api.py and 44 sibling modules do; no shared fixture)."""
    return create_app(app_settings, clock=clock)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _people(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> tuple[Member, Actor, Actor]:
    maya_member = member(keyring, clock)
    victor_member = colleague(maya_member.tenant_id, "victor")
    with tenant_session(_db(maya_member.tenant_id)) as session:
        for someone, role_code in ((maya_member, "auditor"), (victor_member, "viewer")):
            insert_role_assignment(
                session,
                tenant_id=someone.tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
            )
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    victor = workspace(app, victor_member, sign_in(app, victor_member.email))
    return maya_member, maya, victor


def _record(
    tenant_id: UUID,
    keyring: KeyRing,
    files: LocalFileStore,
    *,
    at: datetime,
    control_id: str,
    result: ControlResult = ControlResult.PASS,
) -> UUID:
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-control-evidence-api",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=at,
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=frozen_clock(at), keyring=keyring, files=files) as uow:
        row_id = record_execution(
            uow,
            control_id=control_id,
            run_ref_type=RunRefType.AUDIT_CHAIN_VERIFICATION,
            run_ref_id=new_id(),
            population_count=10,
            exception_count=0 if result is ControlResult.PASS else 1,
            result=result,
            detail={"at": at.isoformat()},
        )
        uow.commit()
    return row_id


def _stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def test_req_ctl_002_query_and_export(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    maya_member, maya, victor = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    files = LocalFileStore(app_settings.file_root)
    t0, t1 = FROZEN_AT - timedelta(hours=2), FROZEN_AT - timedelta(hours=1)
    recorded = {
        seconds: _record(
            tenant_id, keyring, files, at=t0 + timedelta(seconds=seconds), control_id=cid
        )
        for seconds, cid in (
            (-60, "CTL-039"),
            (0, "CTL-039"),
            (60, "CTL-012"),
            (180, "CTL-039"),
            (3600, "CTL-039"),
        )
    }
    failed = _record(
        tenant_id,
        keyring,
        files,
        at=t0 + timedelta(seconds=240),
        control_id="CTL-039",
        result=ControlResult.FAIL,
    )

    listed = _get(
        app, EXECUTIONS, maya, control_id="CTL-039", **{"from": _stamp(t0), "to": _stamp(t1)}
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    # Newest first; `from` is inclusive and `to` exclusive; the other control is filtered out.
    assert [UUID(item["id"]) for item in items] == [failed, recorded[180], recorded[0]]
    assert set(items[0]) == ITEM_KEYS
    assert items[0]["result"] == "FAIL" and items[0]["exception_count"] == 1
    assert items[0]["run_ref_type"] == "AUDIT_CHAIN_VERIFICATION"
    assert items[0]["detail"] == {"at": (t0 + timedelta(seconds=240)).isoformat()}
    assert items[0]["exceptions_file_id"] is None and items[0]["engine_release_id"]

    forbidden = _get(app, EXECUTIONS, victor)
    assert forbidden.status_code == 403
    assert str(forbidden.json()["type"]).removeprefix(PROBLEM_BASE) == "forbidden"

    releases = _get(app, RELEASES, maya)
    assert releases.status_code == 200, releases.text
    rows = releases.json()["items"]
    assert rows and {"engine_version", "build_sha", "schema_revision", "gate_results"} <= set(
        rows[0]
    )
    assert isinstance(rows[0]["gate_results"], dict)
    assert _get(app, RELEASES, victor).status_code == 403
