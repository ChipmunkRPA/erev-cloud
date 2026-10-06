"""API-R-41 report runs (04 §15.3 API-R-41, §16.9, T-RPT-01 rule 1, T-RPT-02; SCREENS_B RV-01,
RV-06, RV-08, RV-11, RPT-27; 03 REQ-RPT-012, REQ-RPT-024, REQ-RPT-027, REQ-PLT-019; BUILD_SPEC
RPS-2).

Maya is a Revenue Accountant (``report.run``, ``report.export`` and ``audit.read``); Sam is an
Integration Admin, who holds ``report.run`` and ``audit.read`` without ``report.export`` — the API
client inventory these tests run answers to ``audit.read`` since supervisor ruling R-63 (a), which
an SSP Analyst (Sam's role before it) does not hold. Their workspace has API clients created on
1 Sep 2026. The tests play the worker as ``tests/api/test_jobs_api.py`` does.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client, audit_event, job, report_run
from erev_api.domain.reports import legacy_columns
from erev_api.domain.reports.builders import contract_history
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.principals import Actor, Member, colleague, member
from support.reference import fields, get, holding, post, slug
from support.rows import api_client_values
from support.worlds import AVM_US, report_world
from support.worlds import report_run as world_report_run

RUNS: Final = "/api/v1/report-runs"
DEFINITIONS: Final = "/api/v1/report-definitions"
INVENTORY: Final = "api_client_inventory"
HISTORY: Final = "contract_history"
LEGACY_HISTORY: Final = "legacy_contract_history_export"
CREATED: Final = datetime(2026, 9, 1, 9, tzinfo=UTC)
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def insert_clients(tenant_id: UUID, names: Sequence[str]) -> None:
    with tenant_session(_db(tenant_id)) as session:
        session.execute(
            insert(api_client),
            [
                api_client_values(tenant_id, name=name, created_at=CREATED, updated_at=CREATED)
                for name in names
            ],
        )


def maya_of(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> tuple[Member, Actor]:
    someone = member(keyring, clock)
    return someone, holding(app, someone, "revenue_accountant")


def create(
    app: FastAPI, actor: Actor, report_code: str, parameters: dict[str, object], output_format: str
) -> tuple[int, dict[str, object], dict[str, str]]:
    response = post(
        app,
        RUNS,
        actor,
        {"report_code": report_code, "parameters": parameters, "output_format": output_format},
    )
    return response.status_code, response.json(), dict(response.headers)


def finish(tenant_id: UUID, run_id: UUID, runtime: JobRuntime) -> None:
    """The worker runs the run's job."""
    with tenant_session(_db(tenant_id)) as session:
        job_id, task_id = session.execute(
            select(job.c.id, job.c.procrastinate_job_id).where(job.c.subject_id == run_id)
        ).one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)


def runs_and_jobs(tenant_id: UUID) -> tuple[int, int]:
    with tenant_session(_db(tenant_id)) as session:
        runs = session.execute(select(func.count()).select_from(report_run)).scalar_one()
        jobs = session.execute(
            select(func.count()).select_from(job).where(job.c.kind == "REPORT_RUN")
        ).scalar_one()
    return int(runs), int(jobs)


def test_unknown_parameter_rejected(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    someone, maya = maya_of(app, keyring, clock)
    response = post(
        app,
        RUNS,
        maya,
        {
            "report_code": INVENTORY,
            "parameters": {"include_revoked": True, "period_key": "FY2026-P09"},
            "output_format": "JSON",
        },
    )
    assert response.status_code == 422, response.text
    assert slug(response) == "validation-failed"
    assert fields(response) == [("parameters.period_key", "T-RPT-01")]
    assert (
        response.json()["errors"][0]["message"] == "period_key is not a parameter of this report."
    )
    wrong_type = post(
        app,
        RUNS,
        maya,
        {
            "report_code": INVENTORY,
            "parameters": {"include_revoked": "yes"},
            "output_format": "JSON",
        },
    )
    assert (wrong_type.status_code, fields(wrong_type)) == (
        422,
        [("parameters.include_revoked", "T-RPT-01")],
    )
    assert runs_and_jobs(someone.tenant_id) == (0, 0)


def test_start_after_end_rejected(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    stamp_test_release()  # 05 REL-03: the accepted run below names the process's release row
    someone, maya = maya_of(app, keyring, clock)
    status, body, _ = create(
        app,
        maya,
        "revenue_from_prior_period_obligations",
        {"from_period_key": "FY2026-P09", "to_period_key": "FY2026-P08"},
        "JSON",
    )
    assert status == 422, body
    assert body["type"] == "https://erev.dev/problems/validation-failed"
    assert [
        (error["field"], error["rule_id"], error["message"])
        for error in body["errors"]  # type: ignore[attr-defined]
    ] == [
        (
            "parameters.from_period_key",
            "REQ-RPT-012",
            "Start period must be on or before end period.",
        )
    ]
    assert runs_and_jobs(someone.tenant_id) == (0, 0)  # a refused request writes nothing
    # An ordered range passes validation and — RPT-05's builder registered by ENG-C4 — the run is
    # accepted (the former "not available" probe is no longer one): `_insert_run` inserts the
    # report row and defers its job (Codex production-20260921-0304 R1).
    status, body, _ = create(
        app,
        maya,
        "revenue_from_prior_period_obligations",
        {"from_period_key": "FY2026-P08", "to_period_key": "FY2026-P09"},
        "JSON",
    )
    assert status == 202, body
    assert body["kind"] == "REPORT_RUN"  # type: ignore[index]
    assert runs_and_jobs(someone.tenant_id) == (1, 1)


def test_ipe_logic_requires_export_permission(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    someone, maya = maya_of(app, keyring, clock)
    sam = holding(app, colleague(someone.tenant_id, "sam"), "integration_admin")

    without = get(app, f"{DEFINITIONS}/{INVENTORY}", sam)
    assert without.status_code == 200, without.text
    body = without.json()
    assert "ipe_logic" not in body
    assert (body["code"], body["version"], body["name"], body["kind"]) == (
        INVENTORY,
        1,
        "API client inventory",
        "REGISTER",
    )
    assert body["output_formats"] == ["XLSX", "CSV", "PDF", "JSON"]
    assert body["parameters_schema"]["additionalProperties"] is False
    # jsonb keeps no key order.
    assert sorted(body["parameters_schema"]["properties"]) == [
        "entity_codes",
        "include_revoked",
        "known_at",
        "known_at_basis",  # CUTOFF-R1 (04 §16.9 rev 1.54)
    ]
    listed = get(app, DEFINITIONS, sam).json()["items"]
    assert len(listed) == 56 and listed[0]["code"] == "revenue_waterfall"
    assert all("ipe_logic" not in item for item in listed)

    holder = get(app, f"{DEFINITIONS}/{INVENTORY}", maya)
    assert holder.status_code == 200, holder.text
    assert holder.json()["ipe_logic"] == {
        "version": 1,
        # Supervisor ruling R-38 (iii) (CTL-037 evidence; 04 T-PLT-15 rev 1.168): the inventory
        # shows the approval of each client's scopes, so it reads the grant request, its
        # approving decisions and the rule behind an automatic one.
        "source_tables": [
            "api_client",
            "app_user",
            "approval_request",
            "approval_decision",
            "rule",
        ],
        "joins": [
            "api_client.created_by = app_user.id",
            "approval_request.subject_type = ROLE_ASSIGNMENT and approval_request.subject_id = "
            "api_client.id",
            "approval_decision.approval_request_id = approval_request.id",
            "approval_decision.approver_id = app_user.id",
            "approval_decision.auto_rule_id = rule.id",
        ],
        "filters": [
            "include_revoked false: clients not revoked",
            "clients whose entity scope includes an entity of entity_codes",
            "secret hashes are never selected",
            "the latest approval request of each client submitted by the record cutoff, with its "
            "approving decisions by the cutoff",
        ],
        # CUTOFF-R1 (04 §16.9 rev 1.54): every run stores `known_at_basis`; the IPE-logic document
        # lists the definition's parameters as served (the same list the schema check above pins).
        "parameters": ["entity_codes", "include_revoked", "known_at", "known_at_basis"],
    }
    assert get(app, f"{DEFINITIONS}/no_such_report", maya).status_code == 404

    # RV-06: a file output needs report.export, and the refusal is audited.
    status, body, _ = create(app, sam, INVENTORY, {}, "CSV")
    assert (status, body["type"]) == (403, "https://erev.dev/problems/forbidden")
    with tenant_session(_db(someone.tenant_id)) as session:
        denied = session.execute(
            select(audit_event.c.action, audit_event.c.outcome).where(
                audit_event.c.object_type == "report_run"
            )
        ).all()
    assert [tuple(item) for item in denied] == [("report.export", "DENIED")]


def test_output_download_audited(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    stamp_test_release()
    someone, maya = maya_of(app, keyring, clock)
    insert_clients(someone.tenant_id, ["svc-billing", "svc-crm", "svc-tax"])
    status, body, headers = create(app, maya, INVENTORY, {"include_revoked": True}, "XLSX")
    assert status == 202, body
    run_id = UUID(headers["x-erev-report-run-id"])
    finish(someone.tenant_id, run_id, runtime)

    def exports() -> list[tuple[str, UUID | None, str]]:
        with tenant_session(_db(someone.tenant_id)) as session:
            rows = session.execute(
                select(audit_event.c.object_type, audit_event.c.object_id, audit_event.c.detail)
                .where(audit_event.c.action == "report.export")
                .order_by(audit_event.c.chain_seq)
            ).all()
        return [(str(kind), object_id, str(detail["part"])) for kind, object_id, detail in rows]

    assert exports() == []
    record = get(app, f"{RUNS}/{run_id}", maya).json()
    assert (record["status"], record["row_count"]) == ("SUCCEEDED", 3)
    downloaded = get(app, record["output"]["href"], maya)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content.startswith(b"PK")
    assert downloaded.headers["content-disposition"] == (
        f'attachment; filename="{INVENTORY}-{record["report_run_no"]}.xlsx"'
    )
    assert exports() == [("report_run", run_id, "output")]


def test_data_pages_of_200(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    stamp_test_release()
    someone, maya = maya_of(app, keyring, clock)
    names = [f"svc-{index:04d}" for index in range(1, 451)]
    insert_clients(someone.tenant_id, names)
    status, body, headers = create(app, maya, INVENTORY, {}, "JSON")
    assert status == 202, body
    run_id = UUID(headers["x-erev-report-run-id"])
    data = f"{RUNS}/{run_id}/data"
    queued = get(app, data, maya, {"limit": "200"})
    assert (queued.status_code, slug(queued)) == (409, "invalid-transition")
    finish(someone.tenant_id, run_id, runtime)

    keys: list[str] = []
    sizes: list[int] = []
    cursor: str | None = None
    while True:
        params = {"limit": "200", "count": "true"}
        if cursor is not None:
            params["cursor"] = cursor
        page = get(app, data, maya, params)
        assert page.status_code == 200, page.text
        assert page.headers["x-erev-total-count"] == "450"
        items = page.json()["items"]
        sizes.append(len(items))
        keys += [item["row_key"] for item in items]
        cursor = page.json()["next_cursor"]
        if cursor is None:
            break
    assert sizes == [200, 200, 50]
    assert keys == [f"client:{name}" for name in names]
    assert slug(get(app, data, maya, {"limit": "200", "sort": "name"})) == "validation-failed"

    record = get(app, f"{RUNS}/{run_id}", maya).json()
    assert record["row_count"] == 450
    output = get(app, record["output"]["href"], maya)
    assert output.status_code == 200, output.text
    # A streamed response announces no length; its bytes are the stored output.
    assert "content-length" not in output.headers
    assert hashlib.sha256(output.content).hexdigest() == record["output"]["sha256"]
    listed = get(app, RUNS, maya, {"report_code": INVENTORY, "status": "SUCCEEDED"})
    assert [item["id"] for item in listed.json()["items"]] == [str(run_id)]


def test_data_columns_in_builder_order(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    # [J] D-88 L7-1-Q-5: every page of GET /report-runs/{id}/data carries `columns`, copied in order
    # from the stored dataset document (builder order), while the rows keep their sorted keys.
    world = report_world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    parameters = {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "from_date": "2026-01-01",
        "to_date": "2026-12-31",
    }
    builder_columns = {
        LEGACY_HISTORY: [(name, name) for name in legacy_columns.NAMES],
        HISTORY: [(column.key, column.header) for column in contract_history.COLUMNS],
    }
    assert len(legacy_columns.NAMES) == 71
    for code, expected in builder_columns.items():
        run, rows = world_report_run(world, code, parameters)
        assert len(rows) >= 2, run
        data = f"{RUNS}/{run['id']}/data"
        first = get(app, data, world.maya, {"limit": "1"})
        assert first.status_code == 200, first.text
        cursor = first.json()["next_cursor"]
        assert cursor is not None
        later = get(app, data, world.maya, {"limit": "1", "cursor": cursor})
        assert later.status_code == 200, later.text
        for page in (first.json(), later.json()):
            assert len(page["items"]) == 1
            assert [column["key"] for column in page["columns"]] == [key for key, _ in expected]
            assert [(column["key"], column["header"]) for column in page["columns"]] == expected
    contract_history_run, _ = world_report_run(world, HISTORY, parameters)
    shown = get(app, f"{RUNS}/{contract_history_run['id']}/data", world.maya, {"limit": "200"})
    assert [(column["key"], column["kind"]) for column in shown.json()["columns"]] == [
        (column.key, column.kind) for column in contract_history.COLUMNS
    ]


def test_run_names_its_job(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """API-S-ReportRun ``job_id`` (04 rev 1.17; D-90e L9-PLT-Q-5; SCREENS_B RV-14 rev 1.7): the
    run answers the job the 202 ``Location`` named, while QUEUED and after the job ran, on the
    record and in the list, so a stored run names its own job on every report surface."""
    stamp_test_release()
    someone, maya = maya_of(app, keyring, clock)
    insert_clients(someone.tenant_id, ["svc-billing"])
    status, body, headers = create(app, maya, INVENTORY, {"include_revoked": True}, "JSON")
    assert status == 202, body
    run_id = UUID(headers["x-erev-report-run-id"])
    job_id = headers["location"].rsplit("/", 1)[1]

    queued = get(app, f"{RUNS}/{run_id}", maya)
    assert queued.status_code == 200, queued.text
    assert (queued.json()["status"], queued.json()["job_id"]) == ("QUEUED", job_id)

    finish(someone.tenant_id, run_id, runtime)
    finished = get(app, f"{RUNS}/{run_id}", maya).json()
    assert (finished["status"], finished["job_id"]) == ("SUCCEEDED", job_id)
    listed = get(app, RUNS, maya).json()["items"]
    assert [item["job_id"] for item in listed if item["id"] == str(run_id)] == [job_id]
