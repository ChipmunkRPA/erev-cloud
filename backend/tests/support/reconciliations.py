"""Reconciliations through the API-R-40 routes (BUILD_SPEC CLO-16, CLO-17; dev-guide DG-TST-16).

Tests generate, explain and sign reconciliations as the product does: ``POST /reconciliations``
answers 202 with the ``RECONCILIATION_GENERATE`` job, which the helpers run as the worker runs it
(``jobs.registry.run_job`` after the task is fetched), and every later step is its route. A trial
balance is attached the same way: uploaded through ``POST /files`` or pulled through a GL
connection, then the job.

``ingested_k01`` is ``worlds.k01_pellworth`` with its two invoices INGESTED — the CSV v2
``invoices`` template stores INV-US-1001 and INV-US-1044 as ``source_invoice`` rows and applies
them as ``BILLING_RECORDED`` events (DIN-9) — and the two O2 progress events appended after.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, control_execution, job
from erev_api.enums import ContractEventType
from erev_api.events.payloads import ProgressRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from fastapi import FastAPI
from sqlalchemy import select, text
from support.factories import ImportWorld, appended, computed, run_import_job
from support.http import HttpResponse, call
from support.legacy_replay import diffed, job_of, submit
from support.legacy_replay import shown as import_shown
from support.principals import Actor, cookie_headers
from support.reference import approve, assign, get, patch, post
from support.worlds import K01, ReportWorld, k01_pellworth

RECONCILIATIONS: Final = "/api/v1/reconciliations"
ID_HEADER: Final = "X-Erev-Reconciliation-Id"
BILLING: Final = "BILLING_TO_SUBLEDGER"
SUBLEDGER_TO_GL: Final = "SUBLEDGER_TO_GL"
FILES: Final = "/api/v1/files"
CSV_MEDIA_TYPE: Final = "text/csv"
_TASK_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
# The CSV v2 ``invoices`` template (DIN-9).
INVOICE_HEADERS: Final = (
    "contract",
    "document_kind",
    "invoice_number",
    "issue_date",
    "due_date",
    "is_cancellable",
    "credited_invoice_number",
    "reason",
    "lines.line_external_id",
    "lines.obligation_key",
    "lines.product_code",
    "lines.quantity",
    "lines.amount.amount",
    "lines.amount.currency",
    "lines.tax_lines.tax_type",
    "lines.tax_lines.jurisdiction",
    "lines.tax_lines.amount.amount",
    "lines.tax_lines.amount.currency",
    "lines.tax_lines.principal_or_agent",
)
# PRD WLD-K-01 "Seeded billing and events": the two invoices of SF-ORD-10001.
K01_INVOICES: Final = (
    (K01, "INVOICE", "INV-US-1001", "2026-01-01", "", "false", "", "", "1",
     "O1", "AVM-PLAT-ENT", "1", "120000.00", "USD", "", "", "", "", ""),
    (K01, "INVOICE", "INV-US-1044", "2026-02-27", "", "false", "", "", "1",
     "O2", "AVM-IMPL-STD", "1", "15000.00", "USD", "", "", "", "", ""),
)  # fmt: skip


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def job_run(
    tenant_id: UUID, runtime: JobRuntime, job_id: UUID, *, attempts: int = 3
) -> dict[str, Any]:
    """The worker fetches the job's current task and runs it, attempt by attempt, until the job
    settles or ``attempts`` are spent (a refused job ends FAILED after its retry policy's last
    attempt); the job row's state, result and problem."""

    def row() -> dict[str, Any]:
        with tenant_session(_context(tenant_id)) as session:
            return dict(
                session.execute(
                    select(job.c.kind, job.c.state, job.c.result, job.c.problem).where(
                        job.c.id == job_id
                    )
                )
                .mappings()
                .one()
            )

    for attempt in range(1, attempts + 1):
        with tenant_session(_context(tenant_id)) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(_TASK_FETCHED, {"id": task_id})
        run_job(job_id, tenant_id, attempt=attempt, runtime=runtime)
        current = row()
        if str(current["state"]) not in ("QUEUED", "RUNNING"):
            return current
    return row()


def requested(
    app: FastAPI,
    actor: Actor,
    *,
    entity_code: str,
    period_key: str,
    kind: str = BILLING,
    book: str | None = None,
) -> HttpResponse:
    """``POST /reconciliations``."""
    body: dict[str, Any] = {"kind": kind, "entity_code": entity_code, "period_key": period_key}
    if book is not None:
        body["book"] = book
    return post(app, RECONCILIATIONS, actor, body)


def generated(
    app: FastAPI,
    actor: Actor,
    runtime: JobRuntime,
    *,
    entity_code: str,
    period_key: str,
    kind: str = BILLING,
    book: str | None = None,
) -> dict[str, Any]:
    """``POST /reconciliations`` (202), the job run as the worker runs it, then
    API-S-Reconciliation of the reconciliation the job inserted."""
    started = requested(
        app, actor, entity_code=entity_code, period_key=period_key, kind=kind, book=book
    )
    assert started.status_code == 202, started.text
    body = started.json()
    assert body["kind"] == "RECONCILIATION_GENERATE", body
    reconciliation_id = started.headers[ID_HEADER]
    assert started.headers["Location"] == f"/api/v1/jobs/{body['id']}"
    finished = job_run(actor.member.tenant_id, runtime, UUID(str(body["id"])))
    assert str(finished["state"]) == "SUCCEEDED", finished
    assert finished["result"]["href"] == f"{RECONCILIATIONS}/{reconciliation_id}", finished
    return shown(app, actor, reconciliation_id)


def shown(app: FastAPI, actor: Actor, reconciliation_id: str) -> dict[str, Any]:
    """``GET /reconciliations/{id}``."""
    response = get(app, f"{RECONCILIATIONS}/{reconciliation_id}", actor)
    assert response.status_code == 200, response.text
    return dict(response.json())


def items_of(app: FastAPI, actor: Actor, reconciliation_id: str) -> list[dict[str, Any]]:
    """``GET /reconciliations/{id}/items``: every difference in the order it was itemised."""
    response = get(app, f"{RECONCILIATIONS}/{reconciliation_id}/items", actor, {"limit": 500})
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def explain(app: FastAPI, actor: Actor, item: Mapping[str, Any], explanation: str) -> HttpResponse:
    """``PATCH /reconciliations/{id}/items/{item_id}`` with the item's ``If-Match``."""
    return patch(
        app,
        f"{RECONCILIATIONS}/{item['reconciliation_id']}/items/{item['id']}",
        actor,
        {"explanation": explanation},
        if_match=f'"r{item["row_version"]}"',
    )


def prepare(app: FastAPI, actor: Actor, reconciliation_id: str) -> HttpResponse:
    """``POST /reconciliations/{id}/prepare``."""
    return post(app, f"{RECONCILIATIONS}/{reconciliation_id}/prepare", actor, {})


def sign(app: FastAPI, actor: Actor, reconciliation_id: str) -> HttpResponse:
    """``POST /reconciliations/{id}/sign`` as reviewer."""
    return post(
        app,
        f"{RECONCILIATIONS}/{reconciliation_id}/sign",
        actor,
        {"role": "REVIEWER", "statement_accepted": True},
    )


def reopen(app: FastAPI, actor: Actor, reconciliation_id: str, reason: str) -> HttpResponse:
    """``POST /reconciliations/{id}/reopen``."""
    return post(app, f"{RECONCILIATIONS}/{reconciliation_id}/reopen", actor, {"reason": reason})


def control_executions(
    tenant_id: UUID, control_id: str, reconciliation_id: str
) -> list[dict[str, Any]]:
    """The T-PLT-39 rows a reconciliation recorded for ``control_id``, oldest first."""
    with tenant_session(_context(tenant_id)) as session:
        return [
            dict(row)
            for row in session.execute(
                select(
                    control_execution.c.run_ref_type,
                    control_execution.c.population_count,
                    control_execution.c.exception_count,
                    control_execution.c.result,
                    control_execution.c.detail,
                    control_execution.c.executed_at,
                )
                .where(
                    control_execution.c.control_id == control_id,
                    control_execution.c.run_ref_id == UUID(reconciliation_id),
                )
                .order_by(control_execution.c.executed_at, control_execution.c.id)
            ).mappings()
        ]


# --- trial balances (BUILD_SPEC CLO-17) -----------------------------------------------------------


def trial_balance_csv(
    rows: Sequence[tuple[str, str, Decimal | str]],
    headers: Sequence[str] = ("account", "currency", "amount"),
) -> bytes:
    """A trial balance file: one row per account of (account, currency, amount)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows((account, currency, str(amount)) for account, currency, amount in rows)
    return buffer.getvalue().encode("utf-8")


def uploaded(
    app: FastAPI, actor: Actor, name: str, content: bytes, media_type: str = CSV_MEDIA_TYPE
) -> str:
    """``POST /files`` with purpose ``IMPORT_SOURCE``; the file id."""
    stored = call(
        app,
        "POST",
        FILES,
        data={"purpose": "IMPORT_SOURCE"},
        files={"file": (name, content, media_type)},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert stored.status_code == 201, stored.text
    return str(stored.json()["id"])


def attach(
    app: FastAPI, actor: Actor, reconciliation_id: str, body: Mapping[str, Any]
) -> HttpResponse:
    """``POST /reconciliations/{id}/attach-trial-balance``."""
    path = f"{RECONCILIATIONS}/{reconciliation_id}/attach-trial-balance"
    return post(app, path, actor, dict(body))


def attached(
    app: FastAPI,
    actor: Actor,
    runtime: JobRuntime,
    reconciliation_id: str,
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """``attach-trial-balance`` (202), the job run as the worker runs it, then
    API-S-Reconciliation with its totals."""
    started = attach(app, actor, reconciliation_id, body)
    assert started.status_code == 202, started.text
    accepted = started.json()
    assert accepted["kind"] == "RECONCILIATION_GENERATE", accepted
    assert started.headers["Location"] == f"/api/v1/jobs/{accepted['id']}"
    finished = job_run(actor.member.tenant_id, runtime, UUID(str(accepted["id"])))
    assert str(finished["state"]) == "SUCCEEDED", finished
    assert finished["result"]["href"] == f"{RECONCILIATIONS}/{reconciliation_id}", finished
    return shown(app, actor, reconciliation_id)


# --- worlds ---------------------------------------------------------------------------------------


def invoices_csv(rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(INVOICE_HEADERS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def ingested(
    app: FastAPI, maya: Actor, approver: Actor, runtime: JobRuntime, name: str, content: bytes
) -> None:
    """Upload, validate, diff, submit, approve and commit a CSV v2 ``invoices`` file: the documents
    are stored (T-SRC-04, T-SRC-05) and applied as billing events (DIN-9)."""
    imports = ImportWorld(app=app, actor=maya, runtime=runtime, clock=runtime.clock)  # type: ignore[arg-type]
    import_id = diffed(imports, name, content, "invoices")
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, str(submitted.json()["approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = import_shown(imports, import_id)
    assert done["status"] == "COMMITTED", done


def ingested_k01(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> ReportWorld:
    """``worlds.k01_pellworth`` with INV-US-1001 120,000.00 and INV-US-1044 15,000.00 ingested and
    applied (module docstring), then O2's progress 40% (2026-01-31) and 100% (2026-02-27)."""
    # The seeded events of WLD-K-01 start on the inception date: a world through the day before
    # holds the booked, activated and computed contract and none of them.
    world = k01_pellworth(app, keyring, clock, files, through=date(2025, 12, 31))
    assign(world.priya.member, "revenue_reviewer")  # import.approve (PRD ACT-24)
    ingested(
        app,
        world.maya,
        world.priya,
        runtime,
        "avm-us-invoices-2026-02.csv",
        invoices_csv(K01_INVOICES),
    )
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        head = session.execute(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        ).scalar_one()
    appended(
        world.place,
        contract_id,
        int(head),
        [
            EventIn(
                event_type=ContractEventType.PROGRESS_RECORDED,
                effective_date=day,
                payload=ProgressRecordedV1(
                    obligation_key="O2", cumulative_progress_ratio=ratio, measure="OUTPUT_PERCENT"
                ),
            )
            for ratio, day in (("0.40", date(2026, 1, 31)), ("1", date(2026, 2, 27)))
        ],
    )
    computed(world.place, UUID(str(booked.combination_group["id"])))
    return world
