"""Avenmoor data-in items: WLD-B-04, the rejected progress import and its corrected commit
(docs/02-PRD.md §2.1 WLD-R-01, WLD-R-02; §2.9 WLD-B-04; SCREENS §12.2 sample world, §13.2;
BUILD_SPEC DIN-15, XR-09).

``maya`` uploads ``avm-us-progress-2026-09-invalid.csv`` with the template "Progress events (CSV
v2)": one ``DELIVERY_RECORDED`` row effective 12 Sep 2026 for each AVM-US background contract
``BG-AVM-0001`` to ``BG-AVM-0014``. Rows 5 and 9 deliver twelve seat-months more than the booking,
so validation ends ``INVALID`` with two ``PROGRESS_OVER_DELIVERY`` findings and two ``OPEN``
exception items (source ``IMPORT``, severity ``BLOCKING`` by E-43). ``maya`` then uploads the
corrected file ``avm-us-progress-2026-09.csv``, which validates and diffs, and submits it for
approval; ``priya`` (Revenue Reviewer, ``import.approve``) approves the ``IMPORT_COMMIT`` request,
and the commit appends the fourteen events with origin ``IMPORT`` (WLD-R-02).

No worker runs while the seed runs, so each job the commands defer (``IMPORT_VALIDATE``,
``IMPORT_DIFF``, ``IMPORT_COMMIT``) runs as the worker runs it (``jobs.registry.run_job``), and its
row ends ``SUCCEEDED`` or ``SUCCEEDED_WITH_EXCEPTIONS``. A worker that later receives the task
leaves the settled row alone.

[J] L6-4-Q-11: PRD §2.9 names the file, its findings and the corrected commit, but no rows. The rows
follow the SCREENS §12.2 wireframe (14 rows, 12 valid, errors on rows 5 and 9, background
contracts); each row delivers twelve seat-months, and the corrected file keeps rows 5 and 9 within
the booking.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import import_upload, job
from erev_api.domain.demo.avenmoor import ACCOUNTANT, SSP_APPROVER, background
from erev_api.domain.imports import commit, diff, upload, validate
from erev_api.domain.imports.csv_v2 import progress_events
from erev_api.domain.platform import attachments
from erev_api.enums import ApprovalSubjectType, FilePurpose, ImportStatus, JobKind, JobState
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.schemas.imports import ImportCreateIn, ImportSubmitIn

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

# The job handler modules ``run_job`` dispatches to (the worker's HANDLER_MODULES).
HANDLER_MODULES: Final = (validate, diff, commit)
TEMPLATE_CODE: Final = progress_events.CODE
INVALID_FILE: Final = "avm-us-progress-2026-09-invalid.csv"  # WLD-B-04
CORRECTED_FILE: Final = "avm-us-progress-2026-09.csv"
CSV_MEDIA_TYPE: Final = "text/csv"
EFFECTIVE: Final = date(2026, 9, 12)
CONTRACTS: Final = tuple(f"{background.PREFIX}{number:04d}" for number in range(1, 15))
OVER_DELIVERED_ROWS: Final = (5, 9)  # CSV row numbers; the header is row 1
DELIVERED: Final = 12  # seat-months per row
EXTRA: Final = 12  # seat-months above the booking in rows 5 and 9
SUBMIT_COMMENT: Final = "Corrected delivery quantities for rows 5 and 9."
FINISHED: Final = frozenset({JobState.SUCCEEDED.value, JobState.SUCCEEDED_WITH_EXCEPTIONS.value})


@dataclass(frozen=True, slots=True)
class Delivery:
    contract: str
    quantity: int


def booked_quantities() -> dict[str, int]:
    """The booked seat-months of ``CONTRACTS`` from the background specs (WLD-R-01)."""
    specs = {spec.external_id: spec for spec in background.specs()}
    return {external_id: int(specs[external_id].lines[0].quantity) for external_id in CONTRACTS}


def deliveries(*, corrected: bool) -> tuple[Delivery, ...]:
    """The rows of the invalid file, or of the corrected file, in row order."""
    booked = booked_quantities()
    rows: list[Delivery] = []
    for index, external_id in enumerate(CONTRACTS):
        over = (index + 2) in OVER_DELIVERED_ROWS and not corrected
        rows.append(Delivery(external_id, booked[external_id] + EXTRA if over else DELIVERED))
    return tuple(rows)


def progress_document(rows: Sequence[Delivery]) -> bytes:
    """The CSV v2 progress file (UTF-8, LF line ends); the same bytes on every call."""
    headers = [column.name for column in progress_events.COLUMNS]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        values = dict.fromkeys(headers, "")
        values |= {
            "contract": row.contract,
            "event_type": "DELIVERY_RECORDED",
            "effective_date": EFFECTIVE.isoformat(),
            "obligation_key": "O1",
            "quantity": str(row.quantity),
            "trigger": "DELIVERY",
        }
        writer.writerow([values[name] for name in headers])
    return buffer.getvalue().encode("utf-8")


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _status(ctx: BuildContext, import_id: UUID) -> str:
    with ctx.read() as session:
        found = session.execute(
            select(import_upload.c.status).where(import_upload.c.id == import_id)
        ).scalar_one()
    return _value(found)


def _run(ctx: BuildContext, import_id: UUID, kind: JobKind) -> None:
    """Run the latest ``kind`` job of the import as the worker does; ``LookupError`` when there is
    none or it does not finish."""
    with ctx.read() as session:
        found = (
            session.execute(
                select(job.c.id)
                .where(job.c.subject_id == import_id, job.c.kind == kind.value)
                .order_by(job.c.created_at)
            )
            .scalars()
            .all()
        )
    if not found:
        raise LookupError(f"import {import_id} has no {kind.value} job")
    job_id = UUID(str(found[-1]))
    runtime = JobRuntime(clock=ctx.clock, keyring=ctx.keyring, files=ctx.files)
    run_job(job_id, ctx.tenant_id, attempt=1, runtime=runtime)
    with ctx.read() as session:
        state = _value(session.execute(select(job.c.state).where(job.c.id == job_id)).scalar_one())
    if state not in FINISHED:
        raise LookupError(f"{kind.value} job {job_id} of import {import_id} ended {state}")


def _expect(ctx: BuildContext, import_id: UUID, status: ImportStatus) -> None:
    found = _status(ctx, import_id)
    if found != status.value:
        raise LookupError(f"import {import_id} is {found}, not {status.value}")


def upload_and_validate(ctx: BuildContext, filename: str, content: bytes) -> UUID:
    """``POST /files`` (``IMPORT_SOURCE``) and ``POST /imports`` as ``maya``, then validation."""
    with ctx.command(ACCOUNTANT) as uow:
        stored = attachments.upload_file(
            uow,
            purpose=FilePurpose.IMPORT_SOURCE.value,
            stream=io.BytesIO(content),
            original_filename=filename,
            media_type=CSV_MEDIA_TYPE,
        )
    with ctx.command(ACCOUNTANT, upload.UPLOAD_PERMISSION) as uow:
        created = upload.create_import(
            uow,
            body=ImportCreateIn(file_id=UUID(str(stored["id"])), template_code=TEMPLATE_CODE),
        )
    _run(ctx, created.import_id, JobKind.IMPORT_VALIDATE)
    return created.import_id


def build(ctx: BuildContext) -> None:
    """WLD-B-04 (module docstring)."""
    invalid = upload_and_validate(ctx, INVALID_FILE, progress_document(deliveries(corrected=False)))
    _expect(ctx, invalid, ImportStatus.INVALID)
    corrected = upload_and_validate(
        ctx, CORRECTED_FILE, progress_document(deliveries(corrected=True))
    )
    _expect(ctx, corrected, ImportStatus.VALIDATED)
    _run(ctx, corrected, JobKind.IMPORT_DIFF)
    _expect(ctx, corrected, ImportStatus.DIFF_READY)
    with ctx.command(ACCOUNTANT, upload.UPLOAD_PERMISSION) as uow:
        commit.submit_import(uow, import_id=corrected, body=ImportSubmitIn(comment=SUBMIT_COMMENT))
    ctx.approve(ApprovalSubjectType.IMPORT_COMMIT, corrected, [SSP_APPROVER])
    _run(ctx, corrected, JobKind.IMPORT_COMMIT)
    _expect(ctx, corrected, ImportStatus.COMMITTED)
