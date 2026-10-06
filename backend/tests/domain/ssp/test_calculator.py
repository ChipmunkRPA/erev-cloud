"""Historical SSP calculator (04 T-REF-32 to T-REF-34, §15.3 API-R-27, §16.14; 05 §5.6
``SSP_CALCULATOR``; SCREENS §11.5; PRD §2.8 WLD-X-24, §2.12 WLD-F-18, BR-SSP-04, J-02.1 to J-02.5;
POLICIES §3.3; 03 REQ-SSP-009; BUILD_SPEC RFD-15, BS3-D-15, BS3-D-18).

Maya holds Revenue Accountant (``import.upload``) and SSP Analyst (``ssp.create``) and runs the
calculator over WLD-F-18 for the Avenmoor SSP book US-LIST (USD). Its version 2026-H1 (AVM-PLAT-100
85,000.00 / 100,000.00 / 115,000.00; AVM-PLAT-ENT point 132,000.00; PRD §2.6) is approved by Priya;
Priya and Marcus hold SSP Approver and are enrolled in MFA. The worker is simulated: a test marks
the job's Procrastinate task as fetched and runs ``jobs.registry.run_job``. The frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    job,
    ssp_book_version,
    ssp_calculator_exclusion,
    ssp_calculator_run,
)
from erev_api.domain.demo.fixtures import STANDALONE_SALES_POOL_FILENAME, standalone_sales_pool
from erev_api.domain.ssp import calculator
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore, open_file
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import func, select, text
from support.db import TestDatabase
from support.factories import (
    TPL_SUB_DAILY,
    booked_contract,
    computed,
    customer_id,
    fake_compute,
    published_template,
    set_default_template,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.reference import (
    APPROVALS,
    approve,
    assign,
    fields,
    get,
    holding,
    new_product,
    patch,
    slug,
)
from support.reference import post as post_json
from support.rows import publish_registry_version

SSP_BOOKS = "/api/v1/ssp-books"
VERSIONS = "/api/v1/ssp-book-versions"
RUNS = "/api/v1/ssp-calculator-runs"
RUN_ID_HEADER = "X-Erev-Ssp-Calculator-Run-Id"
PLATFORM = "AVM-PLAT-100"
ENTERPRISE = "AVM-PLAT-ENT"
RUN_NAME = "AVM-PLAT-100 standalone sales 2026"
METHODOLOGY = "Observable standalone sales, Jan-Aug 2026"
DISTRESSED = "Distressed sale to a customer in administration"
WARN = {"max_half_width_pct": "0.20", "min_coverage_pct": "0.50", "mode": "WARN"}
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@dataclass(frozen=True, slots=True)
class World:
    maya: Actor
    priya: Actor
    marcus: Actor
    book_id: str
    platform_id: str
    h1_id: str

    @property
    def tenant_id(self) -> UUID:
        return self.maya.member.tenant_id


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def post(app: FastAPI, path: str, actor: Actor, body: Mapping[str, Any]) -> HttpResponse:
    return post_json(app, path, actor, body)


def observable(product_code: str, low: str, mid: str, high: str) -> dict[str, Any]:
    return {
        "product_code": product_code,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "ranges": [{"low_value": low, "mid_value": mid, "high_value": high}],
    }


# PRD §2.6: US-LIST 2026-H1.
H1_ENTRIES = (
    observable(PLATFORM, "85000.00", "100000.00", "115000.00"),
    {
        "product_code": ENTERPRISE,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "ranges": [{"point_value": "132000.00"}],
    },
)


def attach(app: FastAPI, actor: Actor, version_id: str) -> str:
    """Upload a PDF study and attach it to the version; returns the attachment id."""
    uploaded = call(
        app,
        "POST",
        "/api/v1/files",
        data={"purpose": "SSP_STUDY"},
        files={"file": ("ssp-study-platform-2026H2.pdf", _PDF, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    attached = post(
        app,
        "/api/v1/attachments",
        actor,
        {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "ssp_book_version",
            "subject_id": version_id,
        },
    )
    assert attached.status_code == 201, attached.text
    return str(attached.json()["id"])


_PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def submit(app: FastAPI, actor: Actor, version_id: str) -> HttpResponse:
    current = get(app, f"{VERSIONS}/{version_id}", actor)
    assert current.status_code == 200, current.text
    return post_json(
        app,
        f"{VERSIONS}/{version_id}/submit",
        actor,
        {"comment": "Supported by standalone sales."},
        if_match=current.headers["ETag"],
    )


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


AS_IN_H1: Final[Mapping[str, Any]] = MappingProxyType({})
# The platform subscription as a contract line: twelve months from 01 Mar 2026 (PRD §2.6).
PLATFORM_LINE = {
    "obligation_key": "POB-01",
    "product_code": PLATFORM,
    "quantity": "1",
    "total_price": "96000.00",
    "start_date": "2026-03-01",
    "end_date": "2027-02-28",
}


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    return built_world(app, keyring, clock)


def built_world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    *,
    series: bool = False,
    platform_entry: Mapping[str, Any] | None = AS_IN_H1,
) -> World:
    """US-LIST with its approved version 2026-H1. With ``series`` the platform product is a series
    product before any entry is stored: its default obligation template is the published
    TPL-SUB-DAILY, so its entry declares a ``value_basis`` (D-97 (3a)). ``platform_entry`` holds
    the members the platform's entry states over PRD §2.6's; None leaves the product out of the
    version."""
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: list[Actor] = []
    for name in ("priya", "marcus"):
        someone = colleague(maya_member.tenant_id, name)
        assign(someone, "ssp_approver")
        approvers.append(enrolled(app, clock, someone))
    platform = new_product(app, maya, code=PLATFORM, name=PLATFORM)
    new_product(app, maya, code=ENTERPRISE, name=ENTERPRISE)
    entries = list(H1_ENTRIES)
    if series:
        someone = colleague(maya_member.tenant_id, "carmen")
        assign(someone, "controller")
        template = published_template(
            app,
            maya,
            enrolled(app, clock, someone),
            code="TPL-SUB-DAILY",
            outputs=TPL_SUB_DAILY,
            case_line=PLATFORM_LINE,
        )
        set_default_template(app, maya, str(platform["id"]), template["template_id"])
    if platform_entry is None:
        del entries[0]
    else:
        entries[0] = {**entries[0], **platform_entry}
    book = post(
        app, SSP_BOOKS, maya, {"code": "US-LIST", "name": "US list prices", "currency": "USD"}
    )
    assert book.status_code == 201, book.text
    book_id = str(book.json()["id"])
    created = post(
        app,
        f"{SSP_BOOKS}/{book_id}/versions",
        maya,
        {
            "legacy_version_label": "2026-H1",
            "effective_from_date": "2026-01-01",
            "methodology_label": "List-price study 2025",
        },
    )
    assert created.status_code == 201, created.text
    h1_id = str(created.json()["id"])
    stored = post(app, f"{VERSIONS}/{h1_id}/entries", maya, {"entries": entries})
    assert stored.status_code == 200, stored.text
    attach(app, maya, h1_id)
    submitted = submit(app, maya, h1_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.json()["approval_request_id"], approvers[0])
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    return World(
        maya=maya,
        priya=approvers[0],
        marcus=approvers[1],
        book_id=book_id,
        platform_id=str(platform["id"]),
        h1_id=h1_id,
    )


def upload_pool(
    app: FastAPI,
    actor: Actor,
    data: bytes | None = None,
    name: str = STANDALONE_SALES_POOL_FILENAME,
) -> dict[str, Any]:
    """Upload a pool CSV as an ``IMPORT_SOURCE`` file; returns the 201 body."""
    uploaded = call(
        app,
        "POST",
        "/api/v1/files",
        data={"purpose": "IMPORT_SOURCE"},
        files={"file": (name, standalone_sales_pool() if data is None else data, "text/csv")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    result: dict[str, Any] = uploaded.json()
    return result


def run_body(world: World, pool_file_id: str | None, **changes: Any) -> dict[str, Any]:
    """J-02.1: AVM-PLAT-100, entity AVM-US, 01 Jan 2026 to 31 Aug 2026, band ±15%, USD, US-LIST."""
    parameters = {
        "source": "source_order_lines",
        "product_ids": [world.platform_id],
        "dimensions": {"entity": "AVM-US"},
        "date_from": "2026-01-01",
        "date_to": "2026-08-31",
        "band_ratio": "0.15",
        "currency": "USD",
        "ssp_book_id": world.book_id,
        "pool_file_id": pool_file_id,
        **changes,
    }
    return {"name": RUN_NAME, "parameters": parameters}


def work(world: World, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it."""
    with tenant_session(_db(world.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, world.tenant_id, attempt=1, runtime=runtime)


def shown(app: FastAPI, actor: Actor, path: str) -> dict[str, Any]:
    response = get(app, path, actor)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def items(app: FastAPI, actor: Actor, path: str) -> list[dict[str, Any]]:
    response = get(app, path, actor, {"limit": "200"})
    assert response.status_code == 200, response.text
    result: list[dict[str, Any]] = response.json()["items"]
    return result


def completed(app: FastAPI, world: World, runtime: JobRuntime) -> dict[str, Any]:
    """A SUCCEEDED run over WLD-F-18; returns the run."""
    pool = upload_pool(app, world.maya)
    started = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    assert started.status_code == 202, started.text
    work(world, UUID(started.json()["id"]), runtime)
    run = shown(app, world.maya, f"{RUNS}/{started.headers[RUN_ID_HEADER]}")
    assert run["status"] == "SUCCEEDED", run
    return run


def by_price(observations: Iterable[Mapping[str, Any]], unit_price: str) -> Mapping[str, Any]:
    (found,) = [item for item in observations if item["unit_price"] == unit_price]
    return found


def in_band_prices(observations: Iterable[Mapping[str, Any]]) -> list[int]:
    return sorted(int(item["unit_price"]) for item in observations if item["in_band"])


def exclude(app: FastAPI, actor: Actor, run_id: str, reference: str, reason: str) -> HttpResponse:
    return post(
        app, f"{RUNS}/{run_id}/exclusions", actor, {"source_reference": reference, "reason": reason}
    )


def figures(result: Mapping[str, Any]) -> dict[str, Decimal]:
    return {name: Decimal(result[name]) for name in calculator.STATISTIC_COLUMNS}


def audits(world: World, action: str) -> list[dict[str, Any]]:
    statement = (
        select(audit_event.c.object_id, audit_event.c.after, audit_event.c.detail)
        .where(audit_event.c.action == action)
        .order_by(audit_event.c.chain_seq)
    )
    with tenant_session(_db(world.tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def count_rows(world: World, table: Any) -> int:
    with tenant_session(_db(world.tenant_id), read_only=True) as session:
        return int(session.execute(select(func.count()).select_from(table)).scalar_one())


def test_pool_of_forty_sales(app: FastAPI, world: World, runtime: JobRuntime) -> None:
    pool = upload_pool(app, world.maya)
    started = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    assert started.status_code == 202, started.text
    job_body = started.json()
    job_id = UUID(job_body["id"])
    assert (job_body["kind"], job_body["state"], job_body["result"]) == (
        "SSP_CALCULATOR",
        "QUEUED",
        None,
    )
    assert started.headers["Location"] == f"/api/v1/jobs/{job_id}"
    run_id = started.headers[RUN_ID_HEADER]
    queued = shown(app, world.maya, f"{RUNS}/{run_id}")
    assert (queued["name"], queued["status"], queued["job_id"]) == (RUN_NAME, "QUEUED", str(job_id))
    assert (queued["observation_count"], queued["result_file_id"], queued["started_at"]) == (
        None,
        None,
        None,
    )
    assert queued["parameters"] == {
        "source": "source_order_lines",
        "product_ids": [world.platform_id],
        "dimensions": {"entity": "AVM-US"},
        "date_from": "2026-01-01",
        "date_to": "2026-08-31",
        "band_ratio": "0.15",
        "currency": "USD",
        "ssp_book_id": world.book_id,
        "pool_file_id": pool["id"],
    }

    work(world, job_id, runtime)

    finished = shown(app, world.maya, f"/api/v1/jobs/{job_id}")
    assert (finished["state"], finished["result"]) == (
        "SUCCEEDED",
        {
            "href": f"/api/v1/ssp-calculator-runs/{run_id}",
            "counts": {"observations": 40, "results": 1},
        },
    )
    run = shown(app, world.maya, f"{RUNS}/{run_id}")
    assert (run["status"], run["observation_count"], run["draft_ssp_book_version_id"]) == (
        "SUCCEEDED",
        40,
        None,
    )
    assert run["started_at"] is not None and run["finished_at"] is not None
    assert run["result_file_id"] is not None
    (result,) = items(app, world.maya, f"{RUNS}/{run_id}/results")
    assert (
        result["ssp_calculator_run_id"],
        result["product_id"],
        result["product_code"],
        result["stratification"],
        result["dimension_key"],
        result["currency"],
    ) == (run_id, world.platform_id, PLATFORM, "", {"entity": "AVM-US"}, "USD")
    assert (result["observation_count"], result["excluded_count"], result["inside_count"]) == (
        40,
        0,
        16,
    )
    assert figures(result) == {
        "median_unit_price": Decimal("112000"),
        "mean_unit_price": Decimal("112000"),
        "p10_unit_price": Decimal("80800"),
        "p25_unit_price": Decimal("92500"),
        "p75_unit_price": Decimal("131500"),
        "p90_unit_price": Decimal("143200"),
        "band_ratio": Decimal("0.15"),
        "compliance_ratio": Decimal("0.40"),
        "proposed_low": Decimal("95200"),
        "proposed_mid": Decimal("112000"),
        "proposed_high": Decimal("128800"),
    }
    edges = [73000 + 7800 * index for index in range(10)] + [151000]
    assert result["histogram"] == [
        {"from": str(edges[index]), "to": str(edges[index + 1]), "count": 4} for index in range(10)
    ]
    observations = items(app, world.maya, f"{RUNS}/{run_id}/observations")
    assert len(observations) == 40
    assert observations[0] == {
        "date": "2026-01-03",
        "source_reference": "SO-AVM-2026-0001",
        "product_code": PLATFORM,
        "customer": None,
        "quantity": "1",
        "unit_price": "73000",
        "in_band": False,
        "exclusion_reason": None,
    }
    # Prices 97,000.00 to 127,000.00 lie inside 95,200.00 to 128,800.00.
    assert in_band_prices(observations) == list(range(97000, 127001, 2000))
    assert [item["action"] for item in _run_events(world, run_id)] == [
        "ssp_calculator_run.create",
        "ssp_calculator_run.start",
        "ssp_calculator_result.create",
        "ssp_calculator_run.succeed",
    ]


def _run_events(world: World, run_id: str) -> list[dict[str, Any]]:
    statement = (
        select(audit_event.c.action, audit_event.c.object_id, audit_event.c.detail)
        .where(audit_event.c.action.like("ssp_calculator%"))
        .order_by(audit_event.c.chain_seq)
    )
    with tenant_session(_db(world.tenant_id), read_only=True) as session:
        rows = [dict(row) for row in session.execute(statement).mappings()]
    return [
        row
        for row in rows
        if str(row["object_id"]) == run_id
        or (row["detail"] or {}).get("ssp_calculator_run_id") == run_id
    ]


def test_exclusion_recomputes_statistics(app: FastAPI, world: World, runtime: JobRuntime) -> None:
    run = completed(app, world, runtime)
    run_id = str(run["id"])
    lowest = by_price(items(app, world.maya, f"{RUNS}/{run_id}/observations"), "73000")

    response = exclude(app, world.maya, run_id, str(lowest["source_reference"]), DISTRESSED)
    assert response.status_code == 201, response.text
    body = response.json()
    sha256 = hashlib.sha256(standalone_sales_pool()).hexdigest()
    reference = uuid.uuid5(
        uuid.NAMESPACE_URL, f"https://erev.dev/ns/ssp-pool/{sha256}/SO-AVM-2026-0001"
    )
    assert (
        body["ssp_calculator_run_id"],
        body["source_ref_type"],
        body["source_ref_id"],
        body["source_reference"],
        body["reason"],
    ) == (run_id, "source_order_line", str(reference), "SO-AVM-2026-0001", DISTRESSED)
    assert body["created_by"]["id"] == str(world.maya.member.user_id)

    (result,) = items(app, world.maya, f"{RUNS}/{run_id}/results")
    assert (result["observation_count"], result["excluded_count"], result["inside_count"]) == (
        39,
        1,
        17,
    )
    stats = figures(result)
    assert (stats["median_unit_price"], stats["proposed_low"], stats["proposed_high"]) == (
        Decimal("113000"),
        Decimal("96050"),
        Decimal("129950"),
    )
    assert stats["compliance_ratio"] == Decimal("0.435897435897435897")
    observations = items(app, world.maya, f"{RUNS}/{run_id}/observations")
    assert len(observations) == 40
    assert by_price(observations, "73000")["exclusion_reason"] == DISTRESSED
    assert [item["exclusion_reason"] for item in observations].count(None) == 39
    # Prices 97,000.00 to 129,000.00 lie inside 96,050.00 to 129,950.00.
    assert in_band_prices(observations) == list(range(97000, 129001, 2000))
    assert shown(app, world.maya, f"{RUNS}/{run_id}")["observation_count"] == 39
    with tenant_session(_db(world.tenant_id), read_only=True) as session:
        stored = session.execute(
            select(
                ssp_calculator_exclusion.c.source_ref_type,
                ssp_calculator_exclusion.c.source_ref_id,
                ssp_calculator_exclusion.c.reason,
            ).where(ssp_calculator_exclusion.c.ssp_calculator_run_id == UUID(run_id))
        ).all()
    assert [tuple(row) for row in stored] == [("source_order_line", reference, DISTRESSED)]
    (recompute,) = audits(world, "ssp_calculator_run.recompute")
    assert recompute["after"]["observation_count"] == 39
    assert recompute["after"]["result_file_id"] != str(run["result_file_id"])

    # The same observation twice, an unknown one, and a run that has not succeeded are refused.
    again = exclude(app, world.maya, run_id, "SO-AVM-2026-0001", DISTRESSED)
    assert (again.status_code, slug(again), fields(again)) == (
        422,
        "validation-failed",
        [("source_reference", "T-REF-34")],
    )
    assert again.json()["errors"][0]["message"] == "This observation is already excluded."
    unknown = exclude(app, world.maya, run_id, "SO-AVM-2026-9999", DISTRESSED)
    assert (unknown.status_code, fields(unknown)) == (422, [("source_reference", "T-REF-34")])


def test_exclusion_reason_minimum_length(app: FastAPI, world: World, runtime: JobRuntime) -> None:
    run = completed(app, world, runtime)
    run_id = str(run["id"])
    lowest = by_price(items(app, world.maya, f"{RUNS}/{run_id}/observations"), "73000")
    for reason in ("Too cheap", "   Distress   "):
        refused = exclude(app, world.maya, run_id, str(lowest["source_reference"]), reason)
        assert (refused.status_code, slug(refused), fields(refused)) == (
            422,
            "validation-failed",
            [("reason", "T-REF-34")],
        ), refused.text
        assert refused.json()["errors"][0]["message"] == "Enter a reason of at least 10 characters."
    assert count_rows(world, ssp_calculator_exclusion) == 0
    (result,) = items(app, world.maya, f"{RUNS}/{run_id}/results")
    assert (result["observation_count"], result["excluded_count"]) == (40, 0)


def test_create_draft_version_from_results(app: FastAPI, world: World, runtime: JobRuntime) -> None:
    run = completed(app, world, runtime)
    run_id = str(run["id"])
    assert exclude(app, world.maya, run_id, "SO-AVM-2026-0001", DISTRESSED).status_code == 201

    created = post(
        app,
        f"{RUNS}/{run_id}/create-draft-version",
        world.maya,
        {"version_label": "2026-H2", "effective_from_date": "2026-10-01"},
    )
    assert created.status_code == 201, created.text
    version = created.json()
    assert created.headers["Location"] == f"/api/v1/ssp-book-versions/{version['id']}"
    assert created.headers["ETag"] == f'"r{version["row_version"]}"'
    assert (
        version["ssp_book_id"],
        version["version_no"],
        version["status"],
        version["legacy_version_label"],
        version["effective_from_date"],
        version["effective_to_date"],
        version["entry_count"],
        version["ssp_calculator_run_id"],
        version["methodology_label"],
    ) == (
        world.book_id,
        2,
        "DRAFT",
        "2026-H2",
        "2026-10-01",
        None,
        2,
        run_id,
        "Historical SSP calculator run: AVM-PLAT-100 standalone sales 2026",
    )
    entries = items(app, world.maya, f"{VERSIONS}/{version['id']}/entries")
    assert [
        (entry["product_code"], entry["method"], entry["distinctness"], entry["ranges"])
        for entry in entries
    ] == [
        (
            PLATFORM,
            "observable",
            "distinct",
            [
                {
                    "band_dimension": "NONE",
                    "band_from": None,
                    "band_to": None,
                    "point_value": None,
                    "low_value": "96050",
                    "mid_value": "113000",
                    "high_value": "129950",
                }
            ],
        ),
        (
            ENTERPRISE,
            "observable",
            "distinct",
            [
                {
                    "band_dimension": "NONE",
                    "band_from": None,
                    "band_to": None,
                    "point_value": "132000",
                    "low_value": None,
                    "mid_value": None,
                    "high_value": None,
                }
            ],
        ),
    ]
    with tenant_session(_db(world.tenant_id), read_only=True) as session:
        linked = session.execute(
            select(ssp_book_version.c.ssp_calculator_run_id).where(
                ssp_book_version.c.id == UUID(version["id"])
            )
        ).scalar_one()
    assert linked == UUID(run_id)
    assert shown(app, world.maya, f"{RUNS}/{run_id}")["draft_ssp_book_version_id"] == version["id"]
    (event,) = audits(world, "ssp_calculator_run.create_draft_version")
    assert event["detail"] == {
        "ssp_book_id": world.book_id,
        "copy_from_version_id": world.h1_id,
        "results": 1,
    }

    again = post(
        app,
        f"{RUNS}/{run_id}/create-draft-version",
        world.maya,
        {"version_label": "2026-H2b", "effective_from_date": "2026-10-01"},
    )
    assert (again.status_code, slug(again), fields(again)) == (
        409,
        "invalid-transition",
        [("draft_ssp_book_version_id", "T-REF-32")],
    )


@pytest.mark.parametrize(
    "declared",
    [
        {"value_basis": "PER_BOOKED_TERM"},
        {"value_basis": "PER_INCREMENT", "quantity_unit": "INCREMENTS"},
    ],
    ids=["per-booked-term", "per-increment-in-increments"],
)
def test_a_draft_from_a_study_keeps_the_basis_of_a_series_products_entry(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    declared: Mapping[str, str],
) -> None:
    """Item SSP-STUDY-SERIES-BASIS-1 (ruling R-50 (c); PRD J-02.3; 04 §16.14): the entry a result
    proposes keeps the pricing basis and the quantity unit of the approved entry it replaces, as
    it keeps its distinctness, account and observable point. Without them the entry of a series
    product is refused (D-97 (3a)), so no draft could be made from a study of one."""
    world = built_world(app, keyring, clock, series=True, platform_entry=declared)
    run_id = str(completed(app, world, runtime)["id"])

    created = post(
        app,
        f"{RUNS}/{run_id}/create-draft-version",
        world.maya,
        {"version_label": "2026-H2", "effective_from_date": "2026-10-01"},
    )

    assert created.status_code == 201, created.text
    entries = {
        entry["product_code"]: entry
        for entry in items(app, world.maya, f"{VERSIONS}/{created.json()['id']}/entries")
    }
    proposed = entries[PLATFORM]
    assert (
        proposed["method"],
        proposed["value_basis"],
        proposed["quantity_unit"],
        [(band["low_value"], band["mid_value"], band["high_value"]) for band in proposed["ranges"]],
    ) == (
        "observable",
        declared["value_basis"],
        declared.get("quantity_unit"),
        [("95200", "112000", "128800")],  # PRD J-02.1: forty sales, median 112,000.00, ±15%
    )
    # The entry no result names is copied as the approved version holds it.
    assert (entries[ENTERPRISE]["value_basis"], entries[ENTERPRISE]["quantity_unit"]) == (
        "AMOUNT",
        None,
    )


SERVICE_UNITS = {"value_basis": "PER_INCREMENT", "quantity_unit": "SERVICE_UNITS"}
SHARE_OF_LIST = {
    "value_basis": "PERCENT_OF_LIST",
    "unit_list_price": "100000.00",
    "ranges": [{"point_value": "1"}],
}


@pytest.mark.parametrize(
    ("series", "platform_entry", "sentence"),
    [
        (
            True,
            SERVICE_UNITS,
            "AVM-PLAT-100 is priced per increment of a service unit in the approved version, and "
            "the study states a price per unit of line quantity.",
        ),
        (
            False,
            SHARE_OF_LIST,
            "AVM-PLAT-100 is priced as a percentage of list price in the approved version, and "
            "the study states a price per unit of line quantity.",
        ),
        (
            True,
            None,
            "AVM-PLAT-100 is a series product, and no approved entry states its value basis.",
        ),
    ],
    ids=["per-increment-of-a-service-unit", "share-of-list", "series-without-an-entry"],
)
def test_a_draft_is_refused_by_product_for_what_a_study_proposes_nothing_for(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    series: bool,
    platform_entry: Mapping[str, Any] | None,
    sentence: str,
) -> None:
    """Item SSP-STUDY-SERIES-BASIS-1 (04 §16.14): a study states one price per unit of line
    quantity. It is not a price per increment of a service unit and not a share of list price,
    and a series product without an approved entry has no stated basis to keep. The command has
    no field for a result, so the refusal is one problem without a field whose detail names the
    product and what to do; a draft takes every result, and nothing is written."""
    world = built_world(app, keyring, clock, series=series, platform_entry=platform_entry)
    run_id = str(completed(app, world, runtime)["id"])

    refused = post(
        app,
        f"{RUNS}/{run_id}/create-draft-version",
        world.maya,
        {"version_label": "2026-H2", "effective_from_date": "2026-10-01"},
    )

    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "validation-failed",
        [(None, "T-REF-33")],
    )
    body = refused.json()
    assert body["detail"] == (
        f"No draft version was created. {sentence} Start a run without AVM-PLAT-100."
    )
    assert [error["message"] for error in body["errors"]] == [sentence]
    # Nothing was written: the book holds its one version and the run names no draft.
    assert count_rows(world, ssp_book_version) == 1
    assert shown(app, world.maya, f"{RUNS}/{run_id}")["draft_ssp_book_version_id"] is None
    assert audits(world, "ssp_calculator_run.create_draft_version") == []


def test_one_refused_product_refuses_the_whole_draft_and_a_run_without_it_is_the_remedy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """A draft takes every result of its run (04 §16.14): the command names none, a run's
    products are fixed when it starts and an exclusion cannot empty a result. So one product the
    study proposes nothing for refuses the draft whole — the other result is not written either —
    and the refusal says what to do: start a run without that product."""
    world = built_world(app, keyring, clock, series=True, platform_entry=SERVICE_UNITS)
    pool = upload_pool(
        app,
        world.maya,
        b"order_line_external_id,order_date,entity_code,product_code,quantity,unit_price,currency\n"
        b"SO-1,2026-02-01,AVM-US,AVM-PLAT-100,1,100000.00,USD\n"
        b"SO-2,2026-02-02,AVM-US,AVM-PLAT-ENT,1,130000.00,USD\n",
        name="two-products.csv",
    )
    products = {item["code"]: item["id"] for item in items(app, world.maya, "/api/v1/products")}

    def run_of(*codes: str) -> str:
        body = run_body(world, str(pool["id"]), product_ids=[products[code] for code in codes])
        started = post(app, RUNS, world.maya, body)
        assert started.status_code == 202, started.text
        work(world, UUID(started.json()["id"]), runtime)
        return str(started.headers[RUN_ID_HEADER])

    def draft_of(run_id: str, label: str) -> HttpResponse:
        return post(
            app, f"{RUNS}/{run_id}/create-draft-version", world.maya, {"version_label": label}
        )

    both = run_of(PLATFORM, ENTERPRISE)
    assert [item["product_code"] for item in items(app, world.maya, f"{RUNS}/{both}/results")] == [
        PLATFORM,
        ENTERPRISE,
    ]

    refused = draft_of(both, "2026-H2")

    assert (refused.status_code, fields(refused)) == (422, [(None, "T-REF-33")])
    assert refused.json()["detail"] == (
        "No draft version was created. AVM-PLAT-100 is priced per increment of a service unit in "
        "the approved version, and the study states a price per unit of line quantity. Start a "
        "run without AVM-PLAT-100."
    )
    assert count_rows(world, ssp_book_version) == 1

    created = draft_of(run_of(ENTERPRISE), "2026-H2")

    assert created.status_code == 201, created.text
    entries = {
        entry["product_code"]: entry
        for entry in items(app, world.maya, f"{VERSIONS}/{created.json()['id']}/entries")
    }
    assert entries[ENTERPRISE]["ranges"][0]["mid_value"] == "130000"
    # The entry the study proposes nothing for is copied as the approved version holds it.
    assert (entries[PLATFORM]["value_basis"], entries[PLATFORM]["quantity_unit"]) == (
        "PER_INCREMENT",
        "SERVICE_UNITS",
    )


def test_a_result_without_an_approved_entry_is_proposed_for_a_product_that_is_not_series(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """The control of the refusal above: only a series product needs a stated basis (D-97 (3a)).
    A product that is not series and has no approved entry is proposed as before — a ``distinct``
    entry on the ``AMOUNT`` basis with the study's band."""
    world = built_world(app, keyring, clock, platform_entry=None)
    run_id = str(completed(app, world, runtime)["id"])

    created = post(
        app,
        f"{RUNS}/{run_id}/create-draft-version",
        world.maya,
        {"version_label": "2026-H2", "effective_from_date": "2026-10-01"},
    )

    assert created.status_code == 201, created.text
    entries = {
        entry["product_code"]: entry
        for entry in items(app, world.maya, f"{VERSIONS}/{created.json()['id']}/entries")
    }
    proposed = entries[PLATFORM]
    assert (
        proposed["method"],
        proposed["distinctness"],
        proposed["value_basis"],
        proposed["quantity_unit"],
        proposed["ranges"][0]["mid_value"],
    ) == ("observable", "distinct", "AMOUNT", None, "112000")


def test_a_refusal_lists_its_products_in_plain_words() -> None:
    assert calculator._listed(["A"]) == "A"
    assert calculator._listed(["A", "B"]) == "A and B"
    assert calculator._listed(["A", "B", "C"]) == "A, B and C"


def test_publication_coverage_counts_linked_run(
    app: FastAPI, world: World, runtime: JobRuntime
) -> None:
    run = completed(app, world, runtime)
    run_id = str(run["id"])
    assert exclude(app, world.maya, run_id, "SO-AVM-2026-0001", DISTRESSED).status_code == 201
    created = post(
        app,
        f"{RUNS}/{run_id}/create-draft-version",
        world.maya,
        {"version_label": "2026-H2", "effective_from_date": "2026-10-01"},
    )
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    # J-02.4: mid 112,000.00 with range ±15%.
    edited = post(
        app,
        f"{VERSIONS}/{version_id}/entries",
        world.maya,
        {"entries": [observable(PLATFORM, "95200.00", "112000.00", "128800.00")]},
    )
    assert edited.status_code == 200, edited.text
    current = get(app, f"{VERSIONS}/{version_id}", world.maya)
    renamed = patch(
        app,
        f"{VERSIONS}/{version_id}",
        world.maya,
        {"methodology_label": METHODOLOGY},
        if_match=current.headers["ETag"],
    )
    assert renamed.status_code == 200, renamed.text
    with tenant_session(_db(world.tenant_id)) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values={"ssp.range_validation": dict(WARN)},
            at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    attach(app, world.maya, version_id)

    submitted = submit(app, world.maya, version_id)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    (event,) = [
        item
        for item in audits(world, "ssp_book_version.submit")
        if str(item["object_id"]) == version_id
    ]
    (finding,) = event["detail"]["range_findings"]
    assert (
        finding["code"],
        finding["severity"],
        finding["subject"],
        finding["message"],
        finding["half_width"],
    ) == (
        "COVERAGE_TOO_LOW",
        "WARNING",
        "entries[0].ranges[0]",
        "Fewer than 50% of observations fall inside the range (41.0%).",
        "0.15",
    )
    # 16 of the 39 non-excluded observations lie inside 95,200.00 to 128,800.00.
    coverage = Decimal(finding["coverage"])
    assert coverage.quantize(Decimal("0.000001")) == Decimal("0.410256")
    request = shown(app, world.priya, f"{APPROVALS}/{submitted.json()['approval_request_id']}")
    assert request["flags"] == ["ABOVE_THRESHOLD"]
    assert [step["step_no"] for step in request["steps"]] == [1, 2]


def test_pool_posts_nothing_and_needs_no_approval(
    app: FastAPI, world: World, runtime: JobRuntime, keyring: KeyRing
) -> None:
    requests_before = count_rows(world, approval_request)
    pool = upload_pool(app, world.maya)
    pool_sha256 = hashlib.sha256(standalone_sales_pool()).hexdigest()
    assert (pool["purpose"], pool["media_type"], pool["sha256"]) == (
        "IMPORT_SOURCE",
        "text/csv",
        pool_sha256,
    )
    started = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    assert started.status_code == 202, started.text
    work(world, UUID(started.json()["id"]), runtime)
    run_id = started.headers[RUN_ID_HEADER]
    assert shown(app, world.maya, f"{RUNS}/{run_id}")["status"] == "SUCCEEDED"
    assert count_rows(world, approval_request) == requests_before
    assert shown(app, world.maya, f"/api/v1/files/{pool['id']}")["sha256"] == pool_sha256
    assert runtime.files is not None
    with tenant_session(_db(world.tenant_id), read_only=True) as session:
        row, stream = open_file(session, UUID(pool["id"]), files=runtime.files, keyring=keyring)
        with stream:
            content = stream.read()
    assert (row["sha256"], hashlib.sha256(content).hexdigest()) == (pool_sha256, pool_sha256)
    actions = {item["action"] for item in _run_events(world, run_id)}
    assert not any(action.startswith("approval") for action in actions)


def test_committed_obligations_source_without_provider(
    app: FastAPI, world: World, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CTR-2 registers the provider (BS3-D-21); the test removes it to show the source without one.
    assert (
        calculator.PROVIDERS[calculator.SOURCE_COMMITTED_OBLIGATIONS]
        is calculator.committed_observations
    )
    monkeypatch.delitem(calculator.PROVIDERS, calculator.SOURCE_COMMITTED_OBLIGATIONS)
    body = run_body(world, None, source="committed_obligations", dimensions={})
    started = post(app, RUNS, world.maya, body)
    assert started.status_code == 202, started.text
    job_id = UUID(started.json()["id"])
    work(world, job_id, runtime)
    run_id = started.headers[RUN_ID_HEADER]
    run = shown(app, world.maya, f"{RUNS}/{run_id}")
    assert (run["status"], run["observation_count"], run["parameters"]["pool_file_id"]) == (
        "SUCCEEDED",
        0,
        None,
    )
    assert items(app, world.maya, f"{RUNS}/{run_id}/results") == []
    assert items(app, world.maya, f"{RUNS}/{run_id}/observations") == []
    finished = shown(app, world.maya, f"/api/v1/jobs/{job_id}")
    assert (finished["state"], finished["result"]["counts"]) == (
        "SUCCEEDED",
        {"observations": 0, "results": 0},
    )
    refused = post(
        app,
        f"{RUNS}/{run_id}/create-draft-version",
        world.maya,
        {"version_label": "2026-H2", "effective_from_date": "2026-10-01"},
    )
    assert (refused.status_code, fields(refused)) == (422, [(None, "T-REF-33")])
    # The sentence is the problem's detail: the dialog's banner reads it (DG-KRN-ERR-01).
    assert refused.json()["detail"] == "This run has no results to propose."


def test_committed_obligations_provider(
    app: FastAPI,
    world: World,
    runtime: JobRuntime,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    # BS3-D-21 (CTR-2): an ACTIVE contract with one AVM-PLAT-100 obligation at 96,000.00 booked on
    # 2026-03-01 is one standalone sale; a DRAFT single-line contract and an ACTIVE contract with
    # two obligations are not. Carmen (Controller) publishes TPL-SUB-DAILY, the product's default.
    # The contracts compute through the ENGINE_SPEC §0.5 fake: the provider reads the stated price
    # and quantity of the obligation versions, which the engine copies from the booking.
    someone = colleague(world.tenant_id, "carmen")
    assign(someone, "controller")
    carmen = enrolled(app, clock, someone)
    world_calendar(app, world.maya)
    buyer = customer_id(app, world.maya, code="C-12", name="Kinsley Marrow Foods Inc. (Demo)")
    line = {
        "obligation_key": "POB-01",
        "product_code": PLATFORM,
        "quantity": "1",
        "total_price": "96000.00",
        "start_date": "2026-03-01",
        "end_date": "2027-02-28",
    }
    template = published_template(
        app, world.maya, carmen, code="TPL-SUB-DAILY", outputs=TPL_SUB_DAILY, case_line=line
    )
    set_default_template(app, world.maya, world.platform_id, template["template_id"])
    stamp_test_release()
    place = workspace(app, clock, keyring, LocalFileStore(app_settings.file_root), world.maya)

    def booking(external_id: str, *prices: str) -> dict[str, Any]:
        return {
            "external_id": external_id,
            "customer_id": str(buyer),
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": "2026-03-01",
            "lines": [
                {
                    "obligation_key": f"O{index}",
                    "product_code": PLATFORM,
                    "quantity": "1",
                    "total_price": {"amount": price, "currency": "USD"},
                    "start_date": "2026-03-01",
                    "end_date": "2027-02-28",
                }
                for index, price in enumerate(prices, start=1)
            ],
        }

    for external_id, prices, activate in (
        ("SF-ORD-20101", ("96000.00",), True),
        ("SF-ORD-20102", ("150000.00",), False),
        ("SF-ORD-20103", ("90000.00", "91000.00"), True),
    ):
        booked = booked_contract(place, booking(external_id, *prices), activate=activate)
        computed(place, booked.combination_group["id"], run=fake_compute)
    body = run_body(world, None, source="committed_obligations", dimensions={"entity": "AVM-US"})
    started = post(app, RUNS, world.maya, body)
    assert started.status_code == 202, started.text
    work(world, UUID(started.json()["id"]), runtime)
    run_id = started.headers[RUN_ID_HEADER]
    run = shown(app, world.maya, f"{RUNS}/{run_id}")
    assert (run["status"], run["observation_count"]) == ("SUCCEEDED", 1)
    (result,) = items(app, world.maya, f"{RUNS}/{run_id}/results")
    assert (result["product_code"], figures(result)["median_unit_price"]) == (
        PLATFORM,
        Decimal(96000),
    )
    (observation,) = items(app, world.maya, f"{RUNS}/{run_id}/observations")
    assert (
        observation["source_reference"],
        observation["product_code"],
        Decimal(observation["quantity"]),
        Decimal(observation["unit_price"]),
        observation["date"],
        observation["customer"]["code"] if observation["customer"] else None,
    ) == ("SF-ORD-20101 O1", PLATFORM, Decimal(1), Decimal(96000), "2026-03-01", "C-12")
    # Another entity filter finds nothing.
    other = run_body(world, None, source="committed_obligations", dimensions={"entity": "AVM-DE"})
    again = post(app, RUNS, world.maya, other)
    assert again.status_code == 202, again.text
    work(world, UUID(again.json()["id"]), runtime)
    assert (
        shown(app, world.maya, f"{RUNS}/{again.headers[RUN_ID_HEADER]}")["observation_count"] == 0
    )


def test_run_findings_and_permissions(app: FastAPI, world: World, runtime: JobRuntime) -> None:
    pool = upload_pool(app, world.maya)
    refused = post(app, RUNS, world.priya, run_body(world, str(pool["id"])))
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    malformed = post(
        app,
        RUNS,
        world.maya,
        {
            "name": "  ",
            "parameters": run_body(
                world,
                None,
                product_ids=[world.platform_id, str(uuid.uuid4())],
                dimensions={"colour": "red", "region": " "},
                date_to="2025-12-31",
                band_ratio="1",
                currency="EUR",
            )["parameters"],
        },
    )
    assert (malformed.status_code, slug(malformed)) == (422, "validation-failed"), malformed.text
    assert fields(malformed) == [
        ("name", "T-REF-32"),
        ("parameters.product_ids", "T-REF-32"),
        ("parameters.dimensions.colour", "T-REF-32"),
        ("parameters.dimensions.region", "T-REF-32"),
        ("parameters.date_to", "T-REF-32"),
        ("parameters.band_ratio", "T-REF-32"),
        ("parameters.currency", "T-REF-32"),
        ("parameters.pool_file_id", "BR-SSP-04"),
    ]
    assert malformed.json()["errors"][6]["message"] == "This SSP book holds values in USD."
    committed = post(
        app,
        RUNS,
        world.maya,
        run_body(
            world,
            str(pool["id"]),
            source="committed_obligations",
            ssp_book_id=str(uuid.uuid4()),
        ),
    )
    assert fields(committed) == [
        ("parameters.ssp_book_id", "T-REF-32"),
        ("parameters.pool_file_id", "BR-SSP-04"),
    ]
    assert count_rows(world, ssp_calculator_run) == 0

    started = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    assert started.status_code == 202, started.text
    run_id = started.headers[RUN_ID_HEADER]
    # Before the job runs, nothing can be excluded.
    early = exclude(app, world.maya, run_id, "SO-AVM-2026-0001", DISTRESSED)
    assert (early.status_code, slug(early), fields(early)) == (
        409,
        "invalid-transition",
        [("status", "E-67")],
    )
    work(world, UUID(started.json()["id"]), runtime)
    listed = get(app, RUNS, world.priya, {"status": "SUCCEEDED"})
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [run_id]
    assert get(app, RUNS, world.priya, {"status": "FAILED"}).json()["items"] == []
    first = get(app, f"{RUNS}/{run_id}/observations", world.priya, {"limit": "30", "count": "true"})
    assert (first.status_code, first.headers["X-Erev-Total-Count"]) == (200, "40"), first.text
    rest = get(
        app,
        f"{RUNS}/{run_id}/observations",
        world.priya,
        {"limit": "30", "cursor": first.json()["next_cursor"]},
    )
    assert (len(first.json()["items"]), len(rest.json()["items"]), rest.json()["next_cursor"]) == (
        30,
        10,
        None,
    )
    assert (
        get(app, f"{RUNS}/{run_id}/observations", world.priya, {"product": ENTERPRISE}).json()[
            "items"
        ]
        == []
    )
    forbidden = exclude(app, world.priya, run_id, "SO-AVM-2026-0001", DISTRESSED)
    assert (forbidden.status_code, slug(forbidden)) == (403, "forbidden")
    unknown = f"{RUNS}/{uuid.uuid4()}"
    for path in (unknown, f"{unknown}/results", f"{unknown}/observations"):
        assert get(app, path, world.maya).status_code == 404, path
    assert exclude(app, world.maya, unknown.rsplit("/", 1)[1], "X", DISTRESSED).status_code == 404


def test_req_plt_012_a_run_names_only_a_pool_its_creator_may_read(
    app: FastAPI, world: World
) -> None:
    """Security review S2, its family (04 T-PLT-29 Read access, rev 1.151; the
    supervisor's ruling on the S2 report, item 3). ``POST /ssp-calculator-runs`` checked the
    pool's purpose and media type and nothing else, so a holder of ``ssp.create`` named another
    member's upload and read its rows back as the run's observations. The command asks the
    file-read question first and answers a pool its caller may not read as a missing one."""
    # A second analyst with Maya's two roles: import.upload for the pool, ssp.create for the run.
    someone = colleague(world.tenant_id, "sam")
    assign(someone, "revenue_accountant")
    sam = holding(app, someone, "ssp_analyst")
    pool = upload_pool(app, sam)  # Sam's upload; nothing owns it yet

    refused = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    unknown = post(app, RUNS, world.maya, run_body(world, str(uuid.uuid4())))
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("parameters.pool_file_id", "BR-SSP-04")]
    assert refused.json()["errors"] == unknown.json()["errors"]
    assert count_rows(world, ssp_calculator_run) == 0

    # Positive control: the uploader's own pool is accepted.
    started = post(app, RUNS, sam, run_body(world, str(pool["id"])))
    assert started.status_code == 202, started.text
    # ... and once a run names the pool, the readers of the run read it (T-PLT-29: ssp.read for
    # all entities), so Maya may name it too.
    again = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    assert again.status_code == 202, again.text
    assert count_rows(world, ssp_calculator_run) == 2


def test_malformed_pool_fails_run(app: FastAPI, world: World, runtime: JobRuntime) -> None:
    data = (
        b"order_line_external_id,order_date,product_code,quantity,unit_price,currency\n"
        b"SO-1,2026-13-01,AVM-PLAT-100,0,12.5x,usd\n"
        b"SO-2,2026-02-01,AVM-PLAT-100,1,100.00,USD\n"
        b"SO-2,2026-02-02,AVM-PLAT-100,1,100.00,USD\n"
    )
    pool = upload_pool(app, world.maya, data, name="bad-pool.csv")
    started = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    assert started.status_code == 202, started.text
    job_id = UUID(started.json()["id"])
    work(world, job_id, runtime)
    finished = shown(app, world.maya, f"/api/v1/jobs/{job_id}")
    assert finished["state"] == "FAILED"
    assert [
        (error["row"], error["field"], error["rule_id"]) for error in finished["problem"]["errors"]
    ] == [
        (2, "order_date", "BR-SSP-04"),
        (2, "quantity", "BR-SSP-04"),
        (2, "unit_price", "BR-SSP-04"),
        (2, "currency", "BR-SSP-04"),
        (4, "order_line_external_id", "BR-SSP-04"),
    ]
    run = shown(app, world.maya, f"{RUNS}/{started.headers[RUN_ID_HEADER]}")
    assert (run["status"], run["observation_count"], run["result_file_id"]) == (
        "FAILED",
        None,
        None,
    )
    assert run["finished_at"] is not None
    (failure,) = audits(world, "ssp_calculator_run.fail")
    assert failure["detail"]["problem"] == "validation-failed"


def test_start_failure_ends_run_failed(
    app: FastAPI, world: World, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = calculator.apply

    def refuse_start(session: Any, table: str, row_id: UUID, **changes: Any) -> Any:
        if changes.get("to_status") == "RUNNING":
            raise Problem("invalid-transition")
        return original(session, table, row_id, **changes)

    monkeypatch.setattr(calculator, "apply", refuse_start)
    pool = upload_pool(app, world.maya)
    started = post(app, RUNS, world.maya, run_body(world, str(pool["id"])))
    assert started.status_code == 202, started.text
    job_id = UUID(started.json()["id"])
    work(world, job_id, runtime)
    assert shown(app, world.maya, f"/api/v1/jobs/{job_id}")["state"] == "FAILED"
    run = shown(app, world.maya, f"{RUNS}/{started.headers[RUN_ID_HEADER]}")
    assert (run["status"], run["started_at"], run["observation_count"]) == ("FAILED", None, None)
    assert run["finished_at"] is not None
    (failure,) = audits(world, "ssp_calculator_run.fail")
    assert (failure["after"]["status"], failure["detail"]["problem"]) == (
        "FAILED",
        "invalid-transition",
    )


def test_pool_parsing_statistics_and_fixture() -> None:
    pool = standalone_sales_pool()
    assert pool == standalone_sales_pool()
    rows = calculator.parse_pool(pool)
    assert len(rows) == 40
    assert sorted(row.unit_price for row in rows) == [
        Decimal(73000 + 2000 * index) for index in range(40)
    ]
    assert {(row.product_code, row.currency, row.quantity) for row in rows} == {
        (PLATFORM, "USD", Decimal("1"))
    }
    assert (
        min(row.order_date for row in rows).isoformat(),
        max(row.order_date for row in rows).isoformat(),
    ) == (
        "2026-01-03",
        "2026-08-27",
    )
    assert {row.dimensions["entity"] for row in rows} == {"AVM-US"}

    # A byte order mark, optional columns and extra columns are accepted.
    bom = (
        "﻿order_line_external_id,order_date,product_code,quantity,unit_price,currency,region,"
        "note\nSO-9,2026-03-01,AVM-PLAT-100,2,10.5,USD,NA,first\n"
    ).encode()
    (row,) = calculator.parse_pool(bom)
    assert (row.row, row.quantity, row.unit_price, row.dimensions, row.stratification) == (
        2,
        Decimal("2"),
        Decimal("10.5"),
        {"region": "NA"},
        "",
    )
    with pytest.raises(Problem) as missing:
        calculator.parse_pool(b"order_line_external_id,order_date,product_code,quantity,currency\n")
    assert [(error.row, error.message) for error in missing.value.errors] == [
        (1, "The pool file needs the columns unit_price.")
    ]
    with pytest.raises(Problem) as encoding:
        calculator.parse_pool(b"\xff\xfe\x00")
    assert encoding.value.errors[0].message == "The pool file must be UTF-8 text."

    assert calculator.percentile([Decimal("5")], Decimal("0.9")) == Decimal("5")
    assert calculator.histogram([Decimal("5"), Decimal("5")]) == (
        {"from": "5", "to": "5", "count": 2},
    )
    stats = calculator.statistics(
        [Decimal(73000 + 2000 * index) for index in range(1, 40)],
        excluded_count=1,
        band_ratio=Decimal("0.15"),
    )
    assert (stats.observation_count, stats.median_unit_price, stats.inside_count) == (
        39,
        Decimal("113000"),
        17,
    )
    sha256 = hashlib.sha256(pool).hexdigest()
    assert calculator.pool_reference(sha256, "SO-AVM-2026-0001") == uuid.uuid5(
        uuid.NAMESPACE_URL, f"https://erev.dev/ns/ssp-pool/{sha256}/SO-AVM-2026-0001"
    )
