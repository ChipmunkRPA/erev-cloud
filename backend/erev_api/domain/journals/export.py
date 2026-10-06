"""Journal export, acknowledgement and retry (05 §5.4 ADP-30 to ADP-34, §5.2 ADP-10 to ADP-12; 03
REQ-JE-011 to REQ-JE-013, REQ-JE-016; 04 T-SL-07, T-SL-10, T-INT-03, §16.7 "Journal commands",
DB-15; PRD SM-08, BR-JE-02, BR-JE-03, NTF-10; dev-guide DG-KRN-EVT-04, DG-KRN-EVT-05; CTL-021;
BUILD_SPEC CLO-13, CLO-14).

Approval writes the export intent: ``enqueue_run`` inserts one ``JOURNAL_EXPORT`` outbox message per
batch in the approving transaction, deduplicated on the batch's external id (ADP-30), and none in a
sandbox workspace (ADP-34). ``export_run`` is ``POST /journal-runs/{id}/export``: it writes any
missing message and defers the run's ``JOURNAL_EXPORT`` job, which dispatches the run's due
messages through the relay. Repeating it writes no second message and posts nothing twice
(BR-JE-02). On a run with ``failed`` batches it is the run's retry (04 §16.7 rev 1.244; item
JRN-RUN-RETRY-1): each failed batch is taken under the rule of ``retry_batch`` below, all or
nothing beside a claimed message — until that revision the command wrote nothing for a failed
batch, whose first message is ``DEAD``, and its job ended as a success over a failed run.

``dispatch_batch`` is the relay handler of topic ``JOURNAL_EXPORT``. After the relay's committed
claim of the message it re-reads the batch's state under the run and batch row locks (security
finding SC-N1, rulings R-32, R-71 (a) and R-75): ``cancel_run`` takes the same locks and refuses
while a message of the run is claimed (``unsettled``), so a batch cancelled first is never sent
and a batch being sent is never cancelled — and no database transaction is held across the
adapter call (DG-KRN-EVT-05). A claim a stopped relay left behind keeps refusing the cancel: the
relay that takes the message again 15 minutes later (ADP-32) completes the dispatch, the ledger
answering with the document it already holds, if any (BR-JE-02). A failed attempt refuses it as
well, until the message is taken again: the claim is gone, but only the ledger knows whether it
took the chunk (item JRN-CANCEL-APPROVED-PENDING-1, ruling R-119 (c)). It builds the batch's chunk,
checks its accounts against the active accounts that apply to the batch's entity and posts it
through the adapter a composition root registered for the batch's E-37 literal
(``ports.gl_adapter_for``). Before anything is sent the handler counts and totals the lines of the
chunk again and compares them with the batch's stored ``line_count`` and totals — the figures the
run was approved with (``recount``; item JRN-DISPATCH-RECOUNT-1, security finding N2 (a)): a
difference is a ``Permanent`` refusal, so a line that reached the batch after its calculation never
leaves with it. A retried message first asks the adapter for the posting by external id
(ADP-12 ``get_posting``). In one transaction it stores the export file, moves the batch to
``exported``, records a ``posting_ack`` and moves the batch to ``acknowledged`` when the adapter
answers with an ERP document id, emits the ``journal_batch.exported`` and
``journal_batch.acknowledged`` webhooks (REQ-PLT-034; ruling R-75 (c)) and rolls the run up
(SMAP-08). A batch that is neither ``approved`` nor ``failed`` dispatches nothing, so a repeated
message never posts twice.

A failed export (CLO-14; ADP-12, ADP-31; ruling R-71 (b)): when the batch's message dies — a
``Permanent`` failure, or the last attempt of the ADP-12 schedule — the relay calls ``batch_died``
before it records the message ``DEAD``, whatever the class of the error (item
JRN-DISPATCH-DEAD-1), so no message dies beside a batch that is still ``approved``. For an ADP-12
error that is the adapter's receipt that the batch was refused; an error of eRev's own is named as
one, because the ledger may hold the batch. In one transaction the batch moves ``approved`` →
``exported`` → ``failed`` (E-34 has no other way into ``failed``; the ``exported`` leg is not
observable: no export time, file, event, notification or message) with a ``posting_ack`` of kind
``REJECTED`` carrying the message, an exception item of source ``JOURNAL``
(``JOURNAL_EXPORT_FAILED``), notification ``EXPORT_FAILED`` to the exporter and the Controllers, a
CTL-021 control execution and the run roll-up.

``retry_batch`` is ``POST /journal-batches/{id}/retry``: it writes a new export message for a
``failed`` batch (T-INT-03 has no way out of ``DEAD``; the chunk's external id is unchanged, so
nothing posts twice, BR-JE-02) and defers the run's ``JOURNAL_EXPORT`` job; the batch is
``exported`` again once the adapter accepts it, and its exception item is resolved. It writes
that message only when the message the batch names is settled (item JRN-RETRY-CLAIMED-1; 04
§16.7 rev 1.221; 05 ADP-32 rev 1.160): a batch's ``failed`` and its message's ``DEAD`` are two
transactions, a worker can stop between them, and the message it leaves claimed is then the
retry — the command is refused beside the claim, and writes no second message while that
message, or a retry already written, is still to be sent or due again. The job it defers then
says what it left: ``result.waiting`` names each batch whose message is due again and the
instant from which it is sent (``waiting``); the message keeps its schedule.
``acknowledge_batch`` is ``POST /journal-batches/{id}/acknowledge`` (BR-JE-03): the person who
imported a CSV batch records the ERP document reference — a ``posting_ack``
``MANUAL_CONFIRMATION`` — and the batch, and the run once every batch is, become
``acknowledged`` (REQ-JE-016).

The ``JOURNAL_EXPORT`` job has two more modes, which ``failed_exits`` builds and registers in
``MODE_HANDLERS`` (04 T-SL-07 "The ways out of ``failed``", §16.7 rev 1.159; 05 §5.6 rev 1.98;
item JRN-FAILED-CANCEL-1, ruling R-112 (c)): ``CANCEL`` — a failed run is cancelled once the
ledger, asked by its external ids, holds none of its failed batches — and ``HAND_OVER`` — a
failed batch of an ERP adapter leaves as its file for manual posting. A mode ends with a decision,
not with an error: the kernel retries every error a handler raises, so a refusal is returned as
``Refused`` and stored in the job's ``result.refusal`` (dev-guide DG-KRN-JOB-05 rev 1.142); only a
ledger that could not be reached is raised.

``render_export`` is the REQ-JE-011 file: a CSV with the columns of ``CSV_COLUMNS`` and a JSON
manifest with the row count, the debit and credit totals and the SHA-256 of the CSV bytes, zipped
with fixed entry times, so a chunk always gives the same bytes. ``download_batch`` serves it; a
batch without a stored file is rendered from its lines, so they are counted and totalled first, as
a dispatch does (``recount``; PRD ERR-79). The
file states both amounts of every line (03 REQ-JE-011 rev 1.68; 04 T-SL-07 "The currencies of an
exported batch"; supervisor ruling R-110): ``currency``, ``debit`` and ``credit`` are the
transaction currency and amounts, ``functional_currency``, ``debit_functional`` and
``credit_functional`` the entity's; the manifest has ``totals`` and ``totals_functional``. Nothing
is converted here: a chunk line carries both pairs (T-SL-09).

[J] L6-3-Q-10: a ``Transient`` failure leaves the message ``FAILED`` with ``next_attempt_at``
30 s × 2^(n − 1) later, not ``PENDING``: T-INT-03 has no ``DISPATCHING`` → ``PENDING`` pair, and
``FAILED`` is the due-again state of DG-KRN-EVT-05. [J] L6-3-Q-11: a batch's adapter is fixed when
the run is calculated (T-SL-07 does not list ``adapter`` as updatable), so ``export`` naming another
adapter answers 422. [J] L6-3-Q-12: a download renders or reads the file and changes no state, also
in a sandbox; D-87 lets ``journal.export`` or ``report.export`` download, and the 409 for ``draft``
and ``cancelled`` batches stays. [J] L6-3-Q-13 (the ``failed`` state deferred to CLO-14) is
closed by the failed-export paragraph above.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.currencies import ISO_4217
from sqlalchemy import and_, any_, func, insert, or_, select
from sqlalchemy.orm import Session

from erev_api.approvals.subjects import JOURNAL_RUN_LINK
from erev_api.audit import writer as audit_writer
from erev_api.audit.writer import record_facts
from erev_api.auth.dependencies import require_for_entity
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import new_id, transitions
from erev_api.db.session import of_session_tenant, system_entity_scope, tenant_session
from erev_api.db.tables import (
    contract,
    exception_item,
    gl_account,
    integration_connection,
    job,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    outbox_message,
    period,
    posting_ack,
    tenant,
    tenant_membership,
)
from erev_api.domain.imports import exceptions
from erev_api.domain.imports.templates import safe_text
from erev_api.domain.journals import ports, queries
from erev_api.domain.platform import guards
from erev_api.domain.platform.jobs import job_out_of
from erev_api.enums import (
    ControlResult,
    ExceptionSeverity,
    ExceptionSource,
    FilePurpose,
    GlAdapter,
    JobKind,
    JournalState,
    MembershipStatus,
    NotificationKind,
    OutboxStatus,
    OutboxTopic,
    PostingAckKind,
    PrincipalKind,
    TenantKind,
)
from erev_api.events import outbox
from erev_api.events.notifications import notify, role_holders
from erev_api.events.webhooks import emit_webhook
from erev_api.files.store import open_file, store_file
from erev_api.jobs.registry import JobOutcome, task
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JOURNAL_EXPORT_MODE_PARAM, JOURNAL_EXPORT_MODES, JobOut
from erev_api.schemas.journals import JournalRunExportIn, PostingAckCreateIn, PostingAckOut

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import RequestContext
    from erev_api.files.store import FileStore
    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

EXPORT_PERMISSION: Final = "journal.export"
REPORT_EXPORT_PERMISSION: Final = "report.export"
# D-87 L6-3-Q-12: a batch download needs either permission for the batch's entity.
DOWNLOAD_PERMISSIONS: Final = (EXPORT_PERMISSION, REPORT_EXPORT_PERMISSION)
OBJECT_TYPE: Final = "journal_run"
BATCH_OBJECT: Final = "journal_batch"
EXPORT_ACTION: Final = "journal_run.request_export"
BATCH_EXPORT_ACTION: Final = "journal_batch.export"
BATCH_FAILURE_ACTION: Final = "journal_batch.export_failed"
ACKNOWLEDGE_ACTION: Final = "journal_batch.acknowledge"
RETRY_ACTION: Final = "journal_batch.retry"
DOWNLOAD_ACTION: Final = "journal_batch.download"
ACK_FACT: Final = "posting_ack.create"
CONTROL_ID: Final = (
    "CTL-021"  # 03 §4.1: acknowledgement matching; unacknowledged batches block lock
)
EXPORT_FAILED_CODE: Final = "JOURNAL_EXPORT_FAILED"  # 04 table 15.4-B (source JOURNAL)
CONTROLLER_ROLE: Final = "controller"  # PRD NTF-10 recipients: the exporter and the Controllers
RUN_HREF: Final = "/api/v1/journal-runs/{run_id}"
BATCH_HREF: Final = "/api/v1/journal-batches/{batch_id}"
JOB_HREF: Final = "/api/v1/jobs/{job_id}"
# 04 T-PLT-35 event kinds (03 REQ-PLT-034).
BATCH_EXPORTED_EVENT: Final = "journal_batch.exported"
BATCH_ACKNOWLEDGED_EVENT: Final = "journal_batch.acknowledged"
RULE_BATCH: Final = "T-SL-07"
RULE_STATES: Final = "E-34"
SANDBOX_DETAIL: Final = guards.SANDBOX_RESTRICTED  # PRD ERR-17
NOT_EXPORTABLE: Final = "Approve the journal run before exporting it."
NOT_DOWNLOADABLE: Final = "Approve the journal run before downloading its batches."
NOT_ACKNOWLEDGEABLE: Final = "Only an exported batch can be acknowledged."
NOT_RETRYABLE: Final = "Only a failed batch can be retried."
RETRY_CLAIMED: Final = (
    "Batch {external_id} is being sent. It cannot be retried while it is being sent. An "
    "interrupted export resumes about 15 minutes after it stopped."
)
# Item JRN-DISPATCH-RECOUNT-1 (independent security review, finding N2 (a)): what a dispatch
# compares with the batch's stored figures — the stored column and its name in the message.
RECOUNTED: Final = (
    ("line_count", "lines"),
    ("total_debit_txn", "transaction debits"),
    ("total_credit_txn", "transaction credits"),
    ("total_debit_functional", "functional debits"),
    ("total_credit_functional", "functional credits"),
)
LINES_DIFFER: Final = (
    "Batch {external_id} differs from what was calculated and approved: {differences}. "
    "{consequence}"
)
NOTHING_SENT: Final = "Nothing was sent."  # the message of the failed batch (05 ADP-31)
NOT_DOWNLOADED: Final = "It cannot be downloaded."  # PRD ERR-79
RULE_RECOUNT: Final = "BATCH_RECOUNT"  # PRD ERR-79 ``errors[].rule_id``, on field ``lines``
# Item JRN-DISPATCH-DEAD-1: the message of a batch whose dispatch died of an error of eRev's own.
NOT_COMPLETED: Final = (
    "eRev could not complete the export ({error}); the ledger may hold the batch."
)
CONNECTION_GONE: Final = "The batch's general ledger connection no longer exists."
CONNECTION_DISABLED: Final = (
    "General ledger connection {code} is disabled. Enable it, then retry the batch."
)
ACTIVE_CONNECTION: Final = "ACTIVE"
# PRD NTF-10 (title and body of EXPORT_FAILED).
FAILED_TITLE: Final = "Journal export failed: {run}"
FAILED_BODY: Final = (
    "{adapter} rejected {count} chunks: {reason}. Retry after correcting the cause; retries do "
    "not duplicate postings."
)
# PRD NTF-10 rev 1.133: the body when the dispatch ended with an error of eRev's own. The ledger
# rejected nothing, so the body says what the batch's own message says (``NOT_COMPLETED``).
NOT_COMPLETED_BODY: Final = (
    "eRev could not complete the export through {adapter} ({error}); the ledger may hold the "
    "batch. Retry it: a retry asks the ledger first, so nothing posts twice."
)
FAILED_ITEM_TITLE: Final = "Journal export failed: {external_id}"
RETRY_RESOLUTION: Final = "The batch was exported by a retry."
OTHER_ADAPTER: Final = (
    "The batches of this run export through {adapters}, so they cannot export through {requested}."
)
ZIP_MEDIA_TYPE: Final = "application/zip"
CSV_COLUMNS: Final = (
    "posting_period",
    "entity",
    "currency",
    "je_id",
    "external_id",
    "account",
    "debit",
    "credit",
    "dimensions",
    "memo",
    "source_references",
    # rev 1.68 (ruling R-110): the entity's functional currency and the line's functional amounts
    "functional_currency",
    "debit_functional",
    "credit_functional",
)
ZIP_ENTRY_TIME: Final = (1980, 1, 1, 0, 0, 0)
APPROVED: Final = JournalState.APPROVED.value
EXPORTED: Final = JournalState.EXPORTED.value
ACKNOWLEDGED: Final = JournalState.ACKNOWLEDGED.value
FAILED: Final = JournalState.FAILED.value
EXPORTABLE: Final = frozenset({APPROVED, EXPORTED, ACKNOWLEDGED, FAILED})
# The states a claimed export message still sends: a first export, or the retry of a failed one.
DISPATCHABLE: Final = frozenset({APPROVED, FAILED})
# ADP-12: 30 s × 2^(n − 1) after the n-th failed attempt, at most 15 minutes, at most 8 attempts.
RETRY_BASE: Final = timedelta(seconds=30)
RETRY_CAP: Final = timedelta(minutes=15)
RETRY_ATTEMPTS: Final = 8


def _text(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "value", value)).strip()


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _amount(value: Decimal, currency: str) -> str:
    """A non-negative amount at the currency's minor unit (API-C-06)."""
    exponent = Decimal(1).scaleb(-ISO_4217[currency].minor_unit)
    return format(Decimal(value).quantize(exponent), "f")


def export_delay(attempt: int) -> timedelta:
    """The wait after failed attempt ``attempt`` (ADP-12)."""
    delay: timedelta = RETRY_BASE * 2 ** max(attempt - 1, 0)
    return delay if delay < RETRY_CAP else RETRY_CAP


# --- the chunk and its file (REQ-JE-011) ----------------------------------------------------------


def _references(row: Mapping[Any, Any]) -> str:
    """The source references of a line: its legacy key or contract, and the drill-back identity."""
    business = row["legacy_key"] or row["contract_external_id"]
    parts = [str(business)] if business else []
    parts += [f"journal_line={row['id']}", f"source_lines={row['source_line_count']}"]
    return "; ".join(parts)


def chunk_of(session: Session, batch_id: UUID) -> ports.JournalChunk:
    """The chunk of a visible batch, lines in journal entry and line order; 404 otherwise. The
    chunk is the batch as it leaves: the same for the job that sends it and for every reader who
    downloads it (04 §16.7 rev 1.245)."""
    batch = (
        session.execute(select(journal_batch).where(journal_batch.c.id == batch_id))
        .mappings()
        .one_or_none()
    )
    if batch is None:
        raise Problem("not-found")
    run_no = session.execute(
        select(journal_run.c.run_no).where(journal_run.c.id == batch["journal_run_id"])
    ).scalar_one()
    entity_code = session.execute(
        select(legal_entity.c.code).where(legal_entity.c.id == batch["entity_id"])
    ).scalar_one()
    found = session.execute(
        select(period.c.period_key, period.c.end_date).where(period.c.id == batch["period_id"])
    ).one()
    tenant_id = journal_line.c.tenant_id
    joined = (
        journal_line.join(
            journal_entry,
            and_(
                journal_entry.c.tenant_id == tenant_id,
                journal_entry.c.id == journal_line.c.journal_entry_id,
            ),
        )
        .join(
            gl_account,
            and_(
                gl_account.c.tenant_id == tenant_id, gl_account.c.id == journal_line.c.gl_account_id
            ),
        )
        .outerjoin(
            contract,
            and_(contract.c.tenant_id == tenant_id, contract.c.id == journal_line.c.contract_id),
        )
    )
    # 04 §16.7 rev 1.245 (register index 182): a line's reference is part of the entry and reads
    # the same for every reader. The contract's external id is read under the tenant's scope for
    # this one statement, as the export job reads it: under a caller's entity scope the outer
    # join finds no row for a contract of another entity (T-CON-01 is RLS-TE), and the file a
    # download rendered — with the digest of its audit event — depended on who asked. The
    # statement names one batch, and that batch was read above under the caller's own scope.
    with system_entity_scope(session):
        rows = (
            session.execute(
                select(
                    journal_line,
                    journal_entry.c.je_no,
                    journal_entry.c.description,
                    gl_account.c.name.label("account_name"),
                    contract.c.external_id.label("contract_external_id"),
                )
                .select_from(joined)
                .where(journal_line.c.journal_batch_id == batch_id)
                .order_by(journal_entry.c.je_seq, journal_line.c.line_no)
            )
            .mappings()
            .all()
        )
    lines = tuple(
        ports.ChunkLine(
            je_no=str(row["je_no"]),
            line_no=int(row["line_no"]),
            account_code=str(row["gl_account_code"]),
            account_name=str(row["account_name"]),
            account_role=str(_text(row["account_role"])),
            debit=Decimal(row["debit_txn"]),
            credit=Decimal(row["credit_txn"]),
            debit_functional=Decimal(row["debit_functional"]),
            credit_functional=Decimal(row["credit_functional"]),
            dimensions={str(code): str(value) for code, value in (row["dimensions"] or {}).items()},
            memo=str(row["memo"] if row["memo"] is not None else row["description"]),
            source_references=_references(row),
        )
        for row in rows
    )
    return ports.JournalChunk(
        external_id=str(batch["external_id"]),
        run_no=str(run_no),
        batch_no=int(batch["batch_no"]),
        chunk_no=int(batch["chunk_no"]),
        entity_code=str(entity_code),
        posting_period=str(found.period_key),
        period_end_date=found.end_date,
        txn_currency=str(_text(batch["txn_currency"])),
        functional_currency=str(_text(batch["functional_currency"])),
        lines=lines,
    )


def export_name(chunk: ports.JournalChunk) -> str:
    """The file name stem of a chunk: its external id with colons replaced."""
    return chunk.external_id.replace(":", "_")


def render_csv(chunk: ports.JournalChunk) -> bytes:
    """The CSV of REQ-JE-011; text that a spreadsheet would evaluate is neutralised
    (REQ-SEC-011)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    currency, functional = chunk.txn_currency, chunk.functional_currency
    for line in chunk.lines:
        dimensions = json.dumps(dict(line.dimensions), sort_keys=True, separators=(",", ":"))
        writer.writerow(
            [
                safe_text(chunk.posting_period),
                safe_text(chunk.entity_code),
                currency,
                safe_text(line.je_no),
                safe_text(chunk.external_id),
                safe_text(line.account_code),
                _amount(line.debit, currency),
                _amount(line.credit, currency),
                safe_text(dimensions),
                "" if line.memo is None else safe_text(line.memo),
                safe_text(line.source_references),
                functional,
                _amount(line.debit_functional, functional),
                _amount(line.credit_functional, functional),
            ]
        )
    return buffer.getvalue().encode("utf-8")


def render_manifest(chunk: ports.JournalChunk, csv_bytes: bytes) -> bytes:
    """The JSON manifest: row count, the debit and credit totals in the transaction currency
    (``totals``) and in the functional currency (``totals_functional``; ruling R-110) and the
    SHA-256 of the CSV bytes."""
    currency, functional = chunk.txn_currency, chunk.functional_currency
    debit = sum((line.debit for line in chunk.lines), Decimal(0))
    credit = sum((line.credit for line in chunk.lines), Decimal(0))
    debit_functional = sum((line.debit_functional for line in chunk.lines), Decimal(0))
    credit_functional = sum((line.credit_functional for line in chunk.lines), Decimal(0))
    document = {
        "external_id": chunk.external_id,
        "run_no": chunk.run_no,
        "batch_no": chunk.batch_no,
        "chunk_no": chunk.chunk_no,
        "entity": chunk.entity_code,
        "posting_period": chunk.posting_period,
        "currency": currency,
        "functional_currency": chunk.functional_currency,
        "file": f"{export_name(chunk)}.csv",
        "columns": list(CSV_COLUMNS),
        "row_count": len(chunk.lines),
        "totals": {"debit": _amount(debit, currency), "credit": _amount(credit, currency)},
        "totals_functional": {
            "debit": _amount(debit_functional, functional),
            "credit": _amount(credit_functional, functional),
        },
        "sha256": hashlib.sha256(csv_bytes).hexdigest(),
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_export(chunk: ports.JournalChunk) -> bytes:
    """The ZIP of the CSV and its manifest, with fixed entry times, so equal chunks give equal
    bytes."""
    csv_bytes = render_csv(chunk)
    name = export_name(chunk)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry, content in (
            (f"{name}.csv", csv_bytes),
            (f"{name}.manifest.json", render_manifest(chunk, csv_bytes)),
        ):
            info = zipfile.ZipInfo(entry, date_time=ZIP_ENTRY_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


# --- the export intent (ADP-30, ADP-34) -----------------------------------------------------------


def _run_batches(session: Session, run_id: UUID) -> list[Mapping[str, Any]]:
    """The run's batches in batch and chunk order, locked in that order (DG-CMD-02)."""
    return [
        dict(row)
        for row in session.execute(
            select(
                journal_batch.c.id,
                journal_batch.c.external_id,
                journal_batch.c.state,
                journal_batch.c.outbox_message_id,
                journal_batch.c.row_version,
                journal_batch.c.attempt_count,
                journal_batch.c.last_error,
            )
            .where(journal_batch.c.journal_run_id == run_id)
            .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
            .with_for_update()
        ).mappings()
    ]


def enqueue_run(uow: UnitOfWork, run_id: UUID) -> int:
    """One ``JOURNAL_EXPORT`` message per exportable batch of the run in the caller's transaction,
    deduplicated on the batch's external id; none in a sandbox (ADP-34). Returns the number of
    batches that received their message here."""
    if uow.ctx.tenant_kind is TenantKind.SANDBOX:
        return 0
    return _first_messages(uow, _run_batches(uow.session, run_id))


def _first_messages(uow: UnitOfWork, batches: Sequence[Mapping[str, Any]]) -> int:
    """``enqueue_run`` over the run's locked batches. A ``failed`` batch has been dispatched, so
    it has its first message: what it gets is a retry (``export_run``)."""
    session = uow.session
    written = 0
    for batch in batches:
        state = _text(batch["state"])
        if state not in EXPORTABLE or state == FAILED:
            continue
        external_id = str(batch["external_id"])
        message = outbox.enqueue(
            uow,
            topic=OutboxTopic.JOURNAL_EXPORT,
            aggregate_type=BATCH_OBJECT,
            aggregate_id=batch["id"],
            dedupe_key=external_id,
            payload={"journal_batch_id": str(batch["id"]), "external_id": external_id},
        )
        if batch["outbox_message_id"] is None:
            transitions.apply(
                session,
                BATCH_OBJECT,
                batch["id"],
                to_status=None,
                expected_status=state,
                set_values={
                    "outbox_message_id": message["id"],
                    "row_version": int(batch["row_version"]) + 1,
                    **_stamps(uow),
                },
            )
            written += 1
    return written


def claimed_failure(named: Sequence[NamedMessage]) -> str | None:
    """Of ``named_messages``, the external id of the first ``failed`` batch whose export message
    a relay has claimed — what refuses the retry of a run whole (04 §16.7 ``export`` rev 1.244)
    — else None."""
    return next(
        (
            item.external_id
            for item in named
            if item.batch_state == FAILED and item.status is OutboxStatus.DISPATCHING
        ),
        None,
    )


def export_run(uow: UnitOfWork, run_id: UUID, body: JournalRunExportIn) -> JobOut:
    """``POST /journal-runs/{id}/export``: 202 API-S-Job ``JOURNAL_EXPORT`` (module docstring).

    A run with ``failed`` batches is retried here (04 §16.7 rev 1.244; item JRN-RUN-RETRY-1):
    each failed batch is taken under the rule of ``retry_batch``, on ONE read of the messages
    the run's batches name. A batch whose message is settled gets its retry message and its
    ``journal_batch.retry`` event; one whose message is still to be sent or due again gets
    nothing — that message is the retry; and a claimed message of a failed batch refuses the
    whole command before anything is written for any batch, so that the answer says one thing.
    A run without a failed batch reads no message."""
    session = uow.session
    row = (
        session.execute(
            select(journal_run.c.entity_id, journal_run.c.state)
            .where(journal_run.c.id == run_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, EXPORT_PERMISSION, UUID(str(row["entity_id"])))
    requested = None if body.adapter is None else GlAdapter(body.adapter)
    # SBX-08 (CTL-043): a sandbox exports nothing; the refused attempt is audited DENIED in its
    # own transaction. The CSV download (`download_batch`) stays available.
    guards.ensure_production(
        uow,
        action=EXPORT_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        detail={"adapter": None if requested is None else requested.value},
        message=SANDBOX_DETAIL,
    )
    if _text(row["state"]) not in EXPORTABLE:
        error = ProblemError(field="state", rule_id=RULE_STATES, message=NOT_EXPORTABLE)
        raise Problem("invalid-transition", NOT_EXPORTABLE, errors=[error])
    adapters = sorted(
        {
            str(_text(value))
            for value in session.scalars(
                select(journal_batch.c.adapter).where(journal_batch.c.journal_run_id == run_id)
            )
        }
    )
    if requested is not None and any(value != requested.value for value in adapters):
        message = OTHER_ADAPTER.format(adapters=", ".join(adapters), requested=requested.value)
        error = ProblemError(field="adapter", rule_id=RULE_BATCH, message=message)
        raise Problem("validation-failed", "1 field needs attention.", errors=[error])
    batches = _run_batches(session, run_id)
    failed = [batch for batch in batches if _text(batch["state"]) == FAILED]
    sent_later: frozenset[str] = frozenset()
    if failed:
        named = named_messages(session, run_id)
        claimed = claimed_failure(named)
        if claimed is not None:
            raise _state_problem(RETRY_CLAIMED.format(external_id=claimed))
        sent_later = frozenset(external_id for external_id, _ in unsettled_of(named))
    written = _first_messages(uow, batches)
    job_row = uow.defer(
        JobKind.JOURNAL_EXPORT,
        {"journal_run_id": str(run_id), MODE_PARAM: MODE_EXPORT},
        subject_type=OBJECT_TYPE,
        subject_id=run_id,
    )
    for batch in failed:
        if str(batch["external_id"]) in sent_later:
            continue  # its message is still to be sent or due again: that message is the retry
        message_id, version = _write_retry(uow, batch)
        _retry_event(uow, batch, message_id=message_id, version=version, job_id=job_row["id"])
        written += 1
    uow.audit(
        action=EXPORT_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        after={"adapters": adapters, "job_id": str(job_row["id"]), "messages_written": written},
    )
    return job_out_of(session, UUID(str(job_row["id"])))


# --- the relay handler (ADP-31) -------------------------------------------------------------------

# SMAP-08: the path of the run's state to the state its batches roll up to, along the E-34 pairs.
_RUN_PATHS: Final[Mapping[tuple[str, str], tuple[str, ...]]] = {
    (APPROVED, EXPORTED): (EXPORTED,),
    (APPROVED, ACKNOWLEDGED): (EXPORTED, ACKNOWLEDGED),
    (APPROVED, FAILED): (EXPORTED, FAILED),
    (EXPORTED, ACKNOWLEDGED): (ACKNOWLEDGED,),
    (EXPORTED, FAILED): (FAILED,),
    (FAILED, EXPORTED): (EXPORTED,),
    (FAILED, ACKNOWLEDGED): (EXPORTED, ACKNOWLEDGED),
}


def rolled_up(current: str, states: Sequence[str]) -> str:
    """SMAP-08, pure: the run state its batches' states roll up to. ``acknowledged`` when every
    batch is; ``failed`` when at least one batch is failed and none is exported; ``exported`` when
    no batch is still waiting to be sent; otherwise the run stays as it is."""
    if not states:
        return current
    if all(item == ACKNOWLEDGED for item in states):
        return ACKNOWLEDGED
    if FAILED in states and EXPORTED not in states:
        return FAILED
    if all(item in (EXPORTED, ACKNOWLEDGED, FAILED) for item in states):
        return EXPORTED
    return current


def _roll_up(uow: UnitOfWork, run_id: UUID) -> str:
    """SMAP-08: move the run to the state its batches roll up to (``rolled_up``), in the
    transaction that changed a batch; its state after the roll-up."""
    session = uow.session
    run = session.execute(
        select(journal_run.c.state, journal_run.c.row_version)
        .where(journal_run.c.id == run_id)
        .with_for_update()
    ).one()
    states = [
        str(_text(value))
        for value in session.scalars(
            select(journal_batch.c.state).where(journal_batch.c.journal_run_id == run_id)
        )
    ]
    current = str(_text(run.state))
    version = int(run.row_version)
    target = rolled_up(current, states)
    for state in _RUN_PATHS.get((current, target), ()):
        version += 1
        values: dict[str, Any] = {"row_version": version, **_stamps(uow)}
        # A run on its way to ``failed`` passes ``exported`` only because E-34 has no other pair:
        # nothing was exported, so it takes no export time (ruling R-71 (b)).
        if state == EXPORTED and target != FAILED:
            values["exported_at"] = uow.now
        elif state == ACKNOWLEDGED:
            values["acknowledged_at"] = uow.now
        transitions.apply(
            session,
            OBJECT_TYPE,
            run_id,
            to_status=state,
            expected_status=current,
            set_values=values,
        )
        current = state
    return current


def _locked_batch(session: Session, batch_id: UUID) -> dict[str, Any] | None:
    """The batch under the run row lock, then its own (the order of the run commands, DG-CMD-02);
    None when it is not visible."""
    run_id = session.execute(
        select(journal_batch.c.journal_run_id).where(journal_batch.c.id == batch_id)
    ).scalar_one_or_none()
    if run_id is None:
        return None
    session.execute(
        select(journal_run.c.id).where(journal_run.c.id == run_id).with_for_update()
    ).one()
    row = (
        session.execute(
            select(journal_batch).where(journal_batch.c.id == batch_id).with_for_update()
        )
        .mappings()
        .one()
    )
    return dict(row)


def _insert_ack(
    uow: UnitOfWork,
    batch_id: UUID,
    *,
    kind: PostingAckKind,
    gl_document_id: str | None,
    gl_posted_date: date | None,
    response_sha256: str | None,
    message: str | None,
) -> UUID:
    """One T-SL-10 receipt of the batch, recorded by the unit of work's principal."""
    ack_id = new_id()
    uow.session.execute(
        insert(posting_ack).values(
            tenant_id=uow.principal.tenant_id,
            id=ack_id,
            journal_batch_id=batch_id,
            ack_kind=kind.value,
            gl_document_id=gl_document_id,
            gl_posted_date=gl_posted_date,
            response_sha256=response_sha256,
            response_file_id=None,
            message=message,
            received_at=uow.now,
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind.value,
        )
    )
    record_facts(uow, action=ACK_FACT, object_type="posting_ack", ids=[ack_id])
    return ack_id


def _record_control(
    uow: UnitOfWork,
    batch: Mapping[str, Any],
    *,
    status: str,
    ack_kind: PostingAckKind,
    gl_document_id: str | None,
) -> None:
    """CTL-021 evidence of one receipt (F-CLO record §10): run reference the batch, population 1,
    one exception for a rejection."""
    rejected = ack_kind is PostingAckKind.REJECTED
    record_execution(
        uow,
        control_id=CONTROL_ID,
        run_ref_type=RunRefType.JOURNAL_BATCH,
        run_ref_id=UUID(str(batch["id"])),
        population_count=1,
        exception_count=1 if rejected else 0,
        result=ControlResult.FAIL if rejected else ControlResult.PASS,
        entity_id=UUID(str(batch["entity_id"])),
        book_code=str(_text(batch["book_code"])),
        period_id=UUID(str(batch["period_id"])),
        detail={"status": status, "ack_kind": ack_kind.value, "gl_document_id": gl_document_id},
    )


def _announce(uow: UnitOfWork, event_kind: str, batch_id: UUID, run_id: UUID) -> None:
    """One webhook delivery per endpoint subscribed to ``event_kind``, in the transaction that
    moves the batch (03 REQ-PLT-034; ruling R-75 (c)); ids and hrefs only (05 NTR-10)."""
    emit_webhook(
        uow,
        event_kind=event_kind,
        payload={
            "id": batch_id,
            "href": BATCH_HREF.format(batch_id=batch_id),
            "journal_run_id": run_id,
            "journal_run_href": RUN_HREF.format(run_id=run_id),
        },
    )


def _failure_key(batch_id: UUID) -> str:
    return exceptions.dedupe_key(ExceptionSource.JOURNAL, EXPORT_FAILED_CODE, batch_id)


def _settle_failure(uow: UnitOfWork, batch_id: UUID, *, resolution: str = RETRY_RESOLUTION) -> None:
    """Resolve the batch's open ``JOURNAL_EXPORT_FAILED`` item with ``resolution``: a retry
    exported the batch, or it left ``failed`` another way (``failed_exits``)."""
    item_id = uow.session.execute(
        select(exception_item.c.id).where(
            exception_item.c.dedupe_key == _failure_key(batch_id),
            exception_item.c.status.in_(sorted(exceptions.OPEN_STATUSES)),
        )
    ).scalar_one_or_none()
    if item_id is not None:
        exceptions.settle_record_reprocess(
            uow, UUID(str(item_id)), resolved=True, resolution=resolution
        )


def apply_posting(
    uow: UnitOfWork,
    batch: Mapping[str, Any],
    result: ports.PostingResult,
    *,
    action: str = BATCH_EXPORT_ACTION,
    resolution: str = RETRY_RESOLUTION,
    decided: Mapping[str, Any] | None = None,
) -> str:
    """Record ``result`` for the locked ``approved`` or ``failed`` ``batch`` in the caller's
    transaction: store the file, move the batch along ``exported`` and, with a document id,
    ``acknowledged``, record the acknowledgement and roll the run up. A ``failed`` batch returns
    to ``exported`` and its exception item is resolved with ``resolution``. ``decided`` is what
    the job that decides here adds to the ``after`` of the audit event — its ``job_id`` and
    ``counts``, by which an attempt of that job that is run again finds its decision (04 §16.7
    rev 1.246). Returns the reference of the posting: the ledger's document, else the file's
    digest, else the external id."""
    session = uow.session
    batch_id = UUID(str(batch["id"]))
    before = str(_text(batch["state"]))
    run_id = UUID(str(batch["journal_run_id"]))
    version = int(batch["row_version"]) + 1
    values: dict[str, Any] = {
        "exported_at": uow.now,
        "attempt_count": int(batch["attempt_count"]) + 1,
        "last_error": None,
        "row_version": version,
        **_stamps(uow),
    }
    if result.artifact is not None:
        stored = store_file(
            uow,
            purpose=FilePurpose.JOURNAL_EXPORT,
            stream=io.BytesIO(result.artifact),
            original_filename=result.artifact_name,
            media_type=ZIP_MEDIA_TYPE,
        )
        values["export_file_id"] = stored["id"]
        values["export_sha256"] = hashlib.sha256(result.artifact).hexdigest()
    transitions.apply(
        session,
        BATCH_OBJECT,
        batch_id,
        to_status=EXPORTED,
        expected_status=before,
        set_values=values,
    )
    state = EXPORTED
    _announce(uow, BATCH_EXPORTED_EVENT, batch_id, run_id)
    ack_id: UUID | None = None
    if result.gl_document_id is not None:
        kind = PostingAckKind.DUPLICATE if result.status == "DUPLICATE" else PostingAckKind.POSTED
        ack_id = _insert_ack(
            uow,
            batch_id,
            kind=kind,
            gl_document_id=result.gl_document_id,
            gl_posted_date=result.gl_posted_date,
            response_sha256=result.response_sha256,
            message=result.message,
        )
        version += 1
        transitions.apply(
            session,
            BATCH_OBJECT,
            batch_id,
            to_status=ACKNOWLEDGED,
            expected_status=EXPORTED,
            set_values={"acknowledged_at": uow.now, "row_version": version, **_stamps(uow)},
        )
        state = ACKNOWLEDGED
        _announce(uow, BATCH_ACKNOWLEDGED_EVENT, batch_id, run_id)
        _record_control(
            uow, batch, status=state, ack_kind=kind, gl_document_id=result.gl_document_id
        )
    if before == FAILED:
        _settle_failure(uow, batch_id, resolution=resolution)
    run_state = _roll_up(uow, run_id)
    uow.audit(
        action=action,
        object_type=BATCH_OBJECT,
        object_id=batch_id,
        object_version=str(version),
        before={"state": before},
        after={
            "state": state,
            "external_id": result.external_id,
            "posting_status": result.status,
            "export_file_id": None
            if values.get("export_file_id") is None
            else str(values["export_file_id"]),
            "export_sha256": values.get("export_sha256"),
            "posting_ack_id": None if ack_id is None else str(ack_id),
            "gl_document_id": result.gl_document_id,
            "run_state": run_state,
            **(decided or {}),
        },
    )
    return str(result.gl_document_id or values.get("export_sha256") or result.external_id)


def record_posting(
    jc: JobContext,
    batch_id: UUID,
    result: ports.PostingResult,
    *,
    resolution: str = RETRY_RESOLUTION,
) -> str | None:
    """``apply_posting`` in one transaction of its own, under the run and batch locks; None, and
    nothing written, for a batch that is no longer ``approved`` or ``failed``."""
    with jc.unit_of_work() as uow:
        batch = _locked_batch(uow.session, batch_id)
        if batch is None or str(_text(batch["state"])) not in DISPATCHABLE:
            return None
        reference = apply_posting(uow, batch, result, resolution=resolution)
        uow.commit()
    return reference


def _exporter(session: Session, run_id: UUID) -> list[UUID]:
    """The membership of the person who last asked for an export of the run (``POST
    /journal-runs/{id}/export`` or a batch retry), when a person did (PRD NTF-10 "Exporter")."""
    user_id = session.execute(
        select(job.c.created_by)
        .where(
            job.c.kind == JobKind.JOURNAL_EXPORT.value,
            job.c.subject_id == run_id,
            job.c.created_by_kind == PrincipalKind.USER.value,
            job.c.created_by.is_not(None),
        )
        .order_by(job.c.created_at.desc(), job.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if user_id is None:
        return []
    found = session.execute(
        select(tenant_membership.c.id).where(
            of_session_tenant(tenant_membership),
            tenant_membership.c.user_id == user_id,
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
        )
    ).scalar_one_or_none()
    return [] if found is None else [UUID(str(found))]


def _record_failure(
    jc: JobContext, batch_id: UUID, message: str, *, own_error: str | None = None
) -> None:
    """The adapter's refusal of a batch (module docstring): ``failed`` through ``exported`` with a
    ``REJECTED`` receipt, the exception item, ``EXPORT_FAILED``, the CTL-021 execution and the run
    roll-up, in one transaction. A batch a concurrent dispatch already exported, or a cancelled
    one, keeps its state. ``own_error`` names an error of eRev's own — the slug of a problem, else
    the class: the notification then does not say that the ledger rejected the batch (PRD NTF-10
    rev 1.133)."""
    with jc.unit_of_work() as uow:
        session = uow.session
        batch = _locked_batch(session, batch_id)
        if batch is None:
            return
        before = str(_text(batch["state"]))
        if before not in DISPATCHABLE:
            return
        run_id = UUID(str(batch["journal_run_id"]))
        attempts = int(batch["attempt_count"]) + 1
        version = int(batch["row_version"])
        counted: dict[str, Any] = {"attempt_count": attempts, "last_error": message}
        if before == APPROVED:
            # E-34 has no pair approved → failed, so the batch passes ``exported`` inside this
            # transaction. That leg is never observable (ruling R-71 (b)): it takes no export
            # time and writes no file, event, notification or message of its own.
            version += 1
            transitions.apply(
                session,
                BATCH_OBJECT,
                batch_id,
                to_status=EXPORTED,
                expected_status=APPROVED,
                set_values={"row_version": version, **_stamps(uow)},
            )
            version += 1
            transitions.apply(
                session,
                BATCH_OBJECT,
                batch_id,
                to_status=FAILED,
                expected_status=EXPORTED,
                set_values={**counted, "row_version": version, **_stamps(uow)},
            )
        else:
            version += 1
            transitions.apply(
                session,
                BATCH_OBJECT,
                batch_id,
                to_status=None,
                expected_status=FAILED,
                set_values={**counted, "row_version": version, **_stamps(uow)},
            )
        ack_id = _insert_ack(
            uow,
            batch_id,
            kind=PostingAckKind.REJECTED,
            gl_document_id=None,
            gl_posted_date=None,
            response_sha256=None,
            message=message,
        )
        run_no = str(
            session.execute(
                select(journal_run.c.run_no).where(journal_run.c.id == run_id)
            ).scalar_one()
        )
        external_id = str(batch["external_id"])
        adapter = str(_text(batch["adapter"]))
        raised = exceptions.raise_exception_item(
            uow,
            source=ExceptionSource.JOURNAL,
            code=EXPORT_FAILED_CODE,
            severity=ExceptionSeverity.BLOCKING,  # 04 table 15.4-B: ERROR → BLOCKING
            message=message,
            dedupe=_failure_key(batch_id),
            title=FAILED_ITEM_TITLE.format(external_id=external_id),
            business_key=external_id,
            entity_id=UUID(str(batch["entity_id"])),
            period_id=UUID(str(batch["period_id"])),
        )
        notify(
            uow,
            recipient_membership_ids=[
                *role_holders(
                    session,
                    role_codes=[CONTROLLER_ROLE],
                    entity_id=UUID(str(batch["entity_id"])),
                    at=uow.now,
                ),
                *_exporter(session, run_id),
            ],
            kind=NotificationKind.EXPORT_FAILED,
            title=FAILED_TITLE.format(run=run_no),
            body=(
                FAILED_BODY.format(adapter=adapter, count=1, reason=message.rstrip("."))
                if own_error is None
                else NOT_COMPLETED_BODY.format(adapter=adapter, error=own_error)
            ),
            link_path=JOURNAL_RUN_LINK.format(run_id=run_id),
            subject_type=BATCH_OBJECT,
            subject_id=batch_id,
        )
        _record_control(
            uow, batch, status=FAILED, ack_kind=PostingAckKind.REJECTED, gl_document_id=None
        )
        run_state = _roll_up(uow, run_id)
        uow.audit(
            action=BATCH_FAILURE_ACTION,
            object_type=BATCH_OBJECT,
            object_id=batch_id,
            object_version=str(version),
            before={"state": before},
            after={
                "state": FAILED,
                "attempt_count": attempts,
                "last_error": message,
                "posting_ack_id": str(ack_id),
                "exception_item_id": str(raised.id),
                "run_state": run_state,
            },
        )
        uow.commit()


def _connection_of(session: Session, batch: Mapping[str, Any]) -> dict[str, Any] | str:
    """The ``GLContext`` members of the batch's general ledger connection (BUILD_SPEC CLO-15) —
    its ``base_url`` and non-secret ``config`` — none for a batch without one (``CSV``); the
    refusal, as text, when the connection is gone or no longer ACTIVE: a disabled connection
    sends nothing."""
    connection_id = batch["integration_connection_id"]
    if connection_id is None:
        return {}
    row = session.execute(
        select(
            integration_connection.c.code,
            integration_connection.c.status,
            integration_connection.c.base_url,
            integration_connection.c.config,
        ).where(integration_connection.c.id == connection_id)
    ).one_or_none()
    if row is None:
        return CONNECTION_GONE
    if str(row.status) != ACTIVE_CONNECTION:
        return CONNECTION_DISABLED.format(code=row.code)
    return {"base_url": row.base_url, "config": dict(row.config or {})}


def recount(
    batch: Mapping[str, Any], chunk: ports.JournalChunk, *, consequence: str = NOTHING_SENT
) -> str | None:
    """The refusal of a batch whose lines are not the ones it was calculated and approved with
    (item JRN-DISPATCH-RECOUNT-1; security finding N2 (a)), else None. The run's approval covers
    the batch's stored ``line_count`` and totals in both currencies (T-SL-07); a line that
    reached the batch afterwards changes what is about to leave and none of those figures, so
    the dispatch counts and totals the lines again and sends nothing on a difference.
    ``consequence`` ends the sentence for the other two places a batch leaves through — the
    rendered download and the manual hand-over (04 §16.7 rev 1.159)."""
    txn, functional = chunk.txn_currency, chunk.functional_currency
    lines = chunk.lines
    sent: dict[str, tuple[Decimal, str]] = {
        "line_count": (Decimal(len(lines)), ""),
        "total_debit_txn": (sum((line.debit for line in lines), Decimal(0)), txn),
        "total_credit_txn": (sum((line.credit for line in lines), Decimal(0)), txn),
        "total_debit_functional": (
            sum((line.debit_functional for line in lines), Decimal(0)),
            functional,
        ),
        "total_credit_functional": (
            sum((line.credit_functional for line in lines), Decimal(0)),
            functional,
        ),
    }
    differences = []
    for column, name in RECOUNTED:
        found, currency = sent[column]
        stored = Decimal(batch[column])
        if found != stored:
            shown = (
                (str(int(found)), str(int(stored)))
                if not currency
                else (f"{_amount(found, currency)} {currency}", _amount(stored, currency))
            )
            differences.append(f"{name} {shown[0]}, stored {shown[1]}")
    if not differences:
        return None
    return LINES_DIFFER.format(
        external_id=chunk.external_id, differences="; ".join(differences), consequence=consequence
    )


def dispatch_batch(jc: JobContext, payload: Mapping[str, Any]) -> outbox.DispatchResult:
    """The relay handler of topic ``JOURNAL_EXPORT`` (ADP-31; module docstring)."""
    batch_id = UUID(str(payload["journal_batch_id"]))
    with tenant_session(jc.principal.db_context) as session:
        # SC-N1 (ruling R-32): the state that decides the dispatch is read under the run and batch
        # row locks, after the relay's committed claim of this message. The locks end with this
        # transaction, before the adapter is called (DG-KRN-EVT-05).
        found = _locked_batch(session, batch_id)
        if found is None or _text(found["state"]) not in DISPATCHABLE:
            return outbox.DispatchResult()
        retried = _text(found["state"]) == FAILED
        chunk = chunk_of(session, batch_id)
        tenant_code = str(
            session.execute(select(tenant.c.code).where(tenant.c.id == jc.tenant_id)).scalar_one()
        )
        # The chart of the batch's entity: active accounts for all entities or this one (T-REF-13).
        chart = tuple(
            ports.AccountRef(code=str(code), name=str(name), account_type=_text(account_type))
            for code, name, account_type in session.execute(
                select(gl_account.c.code, gl_account.c.name, gl_account.c.account_type)
                .where(
                    gl_account.c.is_active.is_(True),
                    or_(
                        func.cardinality(gl_account.c.entity_ids) == 0,
                        any_(gl_account.c.entity_ids) == found["entity_id"],
                    ),
                )
                .order_by(gl_account.c.code)
            )
        )
        attempts = (
            0
            if found["outbox_message_id"] is None
            else int(
                session.execute(
                    select(outbox_message.c.attempt_count).where(
                        outbox_message.c.id == found["outbox_message_id"]
                    )
                ).scalar_one_or_none()
                or 0
            )
        )
        connection = _connection_of(session, found)
        changed = recount(found, chunk)
    # An error raised from here on is the relay's to settle: while attempts remain the message is
    # due again, and when it dies — ``Permanent``, or the last attempt of the ADP-12 schedule,
    # whatever failed — ``batch_died`` records the batch ``failed`` (ADP-31).
    if changed is not None:
        raise ports.Permanent(changed)
    if isinstance(connection, str):
        raise ports.Permanent(connection)
    adapter = ports.gl_adapter_for(
        GlAdapter(str(_text(found["adapter"]))),
        ports.GLContext(tenant_code=tenant_code, accounts=chart, **connection),
    )
    checked = adapter.validate_accounts(chunk.accounts, chunk.dimensions)
    if not checked.ok:
        raise ports.Permanent(" ".join(checked.errors))
    # ADP-12: a retry first asks the ledger for the posting, so a timeout after the ledger
    # posted never posts the chunk twice.
    result = adapter.get_posting(chunk.external_id) if attempts > 0 or retried else None
    if result is None:
        try:
            result = adapter.post_chunk(chunk)
        except ports.Duplicate as duplicate:
            result = ports.PostingResult(
                external_id=chunk.external_id,
                status="DUPLICATE",
                gl_document_id=duplicate.gl_document_id,
                message=str(duplicate),
            )
    return outbox.DispatchResult(reference=record_posting(jc, batch_id, result))


def batch_died(jc: JobContext, payload: Mapping[str, Any], error: Exception) -> None:
    """The relay's last word on an export message (``outbox.DEAD_HOOKS``; 05 ADP-31 rev 1.98;
    item JRN-DISPATCH-DEAD-1): the batch is recorded ``failed`` whatever the class of the error,
    so that a message never dies beside a batch that is still ``approved`` — which nothing would
    send again, which no exit of a failed batch would reach, and which could be cancelled without
    its ledger being asked. An ADP-12 error — the ledger's refusal, or its silence at the last
    attempt — keeps the adapter's message. Any other error is eRev's own (a database error while
    the dispatch read or recorded, an adapter nobody registered) and may have followed the
    ledger's acceptance: the batch says so — as does its notification, which does not say that
    the ledger rejected it (PRD NTF-10 rev 1.133) — and its retry, its hand-over and the cancel
    of its run all ask the ledger first. Raising here leaves the message unsettled for the next
    relay."""
    port = isinstance(error, ports.Permanent | ports.Transient)
    name = outbox.error_name(error)
    message = str(error) if port else NOT_COMPLETED.format(error=name)
    _record_failure(
        jc, UUID(str(payload["journal_batch_id"])), message, own_error=None if port else name
    )


# --- acknowledgement and retry (04 §16.7 "Journal commands"; BUILD_SPEC CLO-14) -------------------


def _state_problem(message: str) -> Problem:
    error = ProblemError(field="state", rule_id=RULE_STATES, message=message)
    return Problem("invalid-transition", message, errors=[error])


def _command_batch(uow: UnitOfWork, batch_id: UUID) -> dict[str, Any]:
    """The batch of an acknowledgement or a retry under the run and batch locks: 404 when it is
    not visible or ``journal.export`` is not held for its entity (DG-KRN-AUTH-04; ruling R-28)."""
    batch = _locked_batch(uow.session, batch_id)
    if batch is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, EXPORT_PERMISSION, UUID(str(batch["entity_id"])))
    return batch


def acknowledge_batch(uow: UnitOfWork, batch_id: UUID, body: PostingAckCreateIn) -> PostingAckOut:
    """``POST /journal-batches/{id}/acknowledge``: 201 API-S-PostingAck (module docstring)."""
    session = uow.session
    batch = _command_batch(uow, batch_id)
    if _text(batch["state"]) != EXPORTED:
        raise _state_problem(NOT_ACKNOWLEDGEABLE)
    kind = PostingAckKind.MANUAL_CONFIRMATION
    ack_id = _insert_ack(
        uow,
        batch_id,
        kind=kind,
        gl_document_id=body.gl_document_id,
        gl_posted_date=body.gl_posted_date,
        response_sha256=None,
        message=body.message,
    )
    version = int(batch["row_version"]) + 1
    transitions.apply(
        session,
        BATCH_OBJECT,
        batch_id,
        to_status=ACKNOWLEDGED,
        expected_status=EXPORTED,
        set_values={"acknowledged_at": uow.now, "row_version": version, **_stamps(uow)},
    )
    run_id = UUID(str(batch["journal_run_id"]))
    _announce(uow, BATCH_ACKNOWLEDGED_EVENT, batch_id, run_id)
    _record_control(
        uow, batch, status=ACKNOWLEDGED, ack_kind=kind, gl_document_id=body.gl_document_id
    )
    run_state = _roll_up(uow, run_id)
    uow.audit(
        action=ACKNOWLEDGE_ACTION,
        object_type=BATCH_OBJECT,
        object_id=batch_id,
        object_version=str(version),
        before={"state": EXPORTED},
        after={
            "state": ACKNOWLEDGED,
            "posting_ack_id": str(ack_id),
            "ack_kind": kind.value,
            "gl_document_id": body.gl_document_id,
            "gl_posted_date": None
            if body.gl_posted_date is None
            else body.gl_posted_date.isoformat(),
            "run_state": run_state,
        },
        comment=body.message,
    )
    (recorded,) = [
        ack for ack in queries.get_batch(session, batch_id).acknowledgements if ack.id == ack_id
    ]
    return recorded


def retry_batch(uow: UnitOfWork, batch_id: UUID) -> JobOut:
    """``POST /journal-batches/{id}/retry``: 202 API-S-Job ``JOURNAL_EXPORT`` (module docstring)."""
    session = uow.session
    batch = _command_batch(uow, batch_id)
    run_id = UUID(str(batch["journal_run_id"]))
    # SBX-08 (CTL-043): a retry is an export, so a sandbox is refused as `export_run` refuses it —
    # through the one guard, the attempt audited DENIED in its own transaction.
    guards.ensure_production(
        uow,
        action=RETRY_ACTION,
        object_type=BATCH_OBJECT,
        object_id=batch_id,
        message=SANDBOX_DETAIL,
    )
    if _text(batch["state"]) != FAILED:
        raise _state_problem(NOT_RETRYABLE)
    external_id = str(batch["external_id"])
    # Item JRN-RETRY-CLAIMED-1 (04 §16.7 rev 1.221; 05 ADP-32 rev 1.160): a retry writes a message
    # only when the message the batch names is settled. The batch's ``failed`` and its message's
    # ``DEAD`` are two transactions, so a worker that stops between them leaves a ``failed`` batch
    # beside a message that is still claimed — and, once a relay has taken that message again and
    # its attempt has failed, beside one that is due again. That message IS the retry: the relay
    # that takes it dispatches the failed batch once more and asks the ledger first. A second
    # message would be the one the batch names, and the first — still to be dispatched — the
    # batch's message for no cancel and no hand-over, which read the message the batch names.
    held = unsettled(session, run_id, batch_id)
    if first_with(held, OutboxStatus.DISPATCHING) is not None:
        raise _state_problem(RETRY_CLAIMED.format(external_id=external_id))
    message_id, version = batch["outbox_message_id"], int(batch["row_version"])
    if not held:
        message_id, version = _write_retry(uow, batch)
    job_row = uow.defer(
        JobKind.JOURNAL_EXPORT,
        {"journal_run_id": str(run_id), MODE_PARAM: MODE_RETRY, BATCH_PARAM: str(batch_id)},
        subject_type=OBJECT_TYPE,
        subject_id=run_id,
    )
    _retry_event(uow, batch, message_id=message_id, version=version, job_id=job_row["id"])
    return job_out_of(session, UUID(str(job_row["id"])))


def _write_retry(uow: UnitOfWork, batch: Mapping[str, Any]) -> tuple[Any, int]:
    """The retry message of the locked ``failed`` ``batch`` whose message is settled, and the
    batch re-pointed to it: (the message's id, the batch's row version). T-INT-03 has no way out
    of ``DEAD``, so a retry is a new message; its dedupe key names the attempt and the chunk
    keeps its external id (ADP-10). The one writer of a retry message, for the batch's own
    command and for the run's (``export_run``)."""
    batch_id, external_id = batch["id"], str(batch["external_id"])
    message_id = outbox.enqueue(
        uow,
        topic=OutboxTopic.JOURNAL_EXPORT,
        aggregate_type=BATCH_OBJECT,
        aggregate_id=batch_id,
        dedupe_key=f"{external_id}#{int(batch['attempt_count'])}",
        payload={"journal_batch_id": str(batch_id), "external_id": external_id},
    )["id"]
    version = int(batch["row_version"])
    if batch["outbox_message_id"] != message_id:
        version += 1
        transitions.apply(
            uow.session,
            BATCH_OBJECT,
            batch_id,
            to_status=None,
            expected_status=FAILED,
            set_values={
                "outbox_message_id": message_id,
                "row_version": version,
                **_stamps(uow),
            },
        )
    return message_id, version


def _retry_event(
    uow: UnitOfWork, batch: Mapping[str, Any], *, message_id: Any, version: int, job_id: Any
) -> None:
    """The ``journal_batch.retry`` event of a failed batch: the message that is its retry and
    the job that dispatches it."""
    uow.audit(
        action=RETRY_ACTION,
        object_type=BATCH_OBJECT,
        object_id=batch["id"],
        object_version=str(version),
        before={"state": FAILED, "last_error": batch["last_error"]},
        after={
            "state": FAILED,
            "attempt_count": int(batch["attempt_count"]),
            "outbox_message_id": str(message_id),
            "job_id": str(job_id),
        },
    )


# The statuses of an export message that is not settled (04 T-INT-03): a relay has claimed it; an
# attempt failed and it is due again; no relay has taken it yet.
UNSETTLED: Final = (OutboxStatus.DISPATCHING, OutboxStatus.FAILED, OutboxStatus.PENDING)


@dataclass(frozen=True, slots=True)
class NamedMessage:
    """The export message a batch names, as a command or a job reads it under the run and batch
    locks: the batch's external id, state and adapter, and the message's status, the name its
    last failed attempt left (``outbox.error_name``) and ``updated_at`` — for a ``DEAD`` message
    the instant its last attempt ended."""

    external_id: str
    batch_state: str
    adapter: str
    status: OutboxStatus
    last_error: str | None
    updated_at: datetime


def named_messages(
    session: Session, run_id: UUID, batch_id: UUID | None = None
) -> list[NamedMessage]:
    """The export message each batch of the run — or ``batch_id`` alone — names, in batch and
    chunk order; a batch without a message has none. Everything a cancel, a hand-over or a retry
    decides about the messages of its run it decides on this read (04 §16.7 rev 1.204, 1.247).

    ONE statement, so one snapshot: a relay claims a message without the run's locks, and two
    reads — one for a claim, one for a message due again, or one for what is not settled and one
    for what died — would each miss a message that changed between them."""
    statement = (
        select(
            journal_batch.c.external_id,
            journal_batch.c.state,
            journal_batch.c.adapter,
            outbox_message.c.status,
            outbox_message.c.last_error,
            outbox_message.c.updated_at,
        )
        .select_from(
            journal_batch.join(
                outbox_message,
                and_(
                    outbox_message.c.tenant_id == journal_batch.c.tenant_id,
                    outbox_message.c.id == journal_batch.c.outbox_message_id,
                ),
            )
        )
        .where(journal_batch.c.journal_run_id == run_id)
        .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
    )
    if batch_id is not None:
        statement = statement.where(journal_batch.c.id == batch_id)
    return [
        NamedMessage(
            external_id=str(row.external_id),
            batch_state=str(_text(row.state)),
            adapter=str(_text(row.adapter)),
            status=OutboxStatus(str(_text(row.status))),
            last_error=_text(row.last_error),
            updated_at=row.updated_at,
        )
        for row in session.execute(statement)
    ]


def unsettled_of(named: Sequence[NamedMessage]) -> list[tuple[str, OutboxStatus]]:
    """Of ``named_messages``, the batches whose export message is not settled, in their order:
    (the batch's external id, the message's status). What a cancel or a hand-over reads before
    it decides (04 §16.7 rev 1.204):

    ``DISPATCHING`` — a relay has claimed the message: the adapter is, or may have been, called
    (SC-N1). The age of the claim is not read (ruling R-75): a relay that stopped may have
    stopped after the ledger accepted the chunk, and the relay that takes the message again
    after 15 minutes (ADP-32) completes the dispatch.

    ``FAILED`` — an attempt failed and the message is due again: the claim is gone and the batch
    reads as before, but the adapter was called, or may have been, and a timeout can follow an
    acceptance. The next attempt asks the ledger first (ADP-12; item
    JRN-CANCEL-APPROVED-PENDING-1, ruling R-119 (c)).

    ``PENDING`` — no relay has taken the message: nothing was sent for it. Beside a failed batch
    it is a retry, or a batch the relay has not reached (ruling R-112 (c))."""
    return [(item.external_id, item.status) for item in named if item.status in UNSETTLED]


def unsettled(
    session: Session, run_id: UUID, batch_id: UUID | None = None
) -> list[tuple[str, OutboxStatus]]:
    """``unsettled_of`` the one read of the run's — or the batch's — named messages."""
    return unsettled_of(named_messages(session, run_id, batch_id))


def first_with(held: Sequence[tuple[str, OutboxStatus]], *statuses: OutboxStatus) -> str | None:
    """The external id of the first batch of ``unsettled`` whose message has one of ``statuses``,
    else None."""
    return next((external_id for external_id, status in held if status in statuses), None)


def waiting(session: Session, run_id: UUID) -> list[dict[str, str]]:
    """``result.waiting`` of a ``JOURNAL_EXPORT`` job without a mode (04 §16.7 rev 1.221; the
    supervisor's ruling of 2026-10-01 11:30): the batches of the run whose export message is
    ``FAILED`` and due again, in batch and chunk order — ``journal_batch_id``, ``external_id``
    and ``next_attempt_at``, the instant from which a relay takes the message again (RFC 3339,
    UTC). What a screen reads to say that the job sent nothing for a batch, or failed to, and
    when the batch is sent next. The message keeps its schedule: the wait a ledger stated
    (``Retry-After``; 05 ADP-12) is part of ``next_attempt_at`` and is stored nowhere else, so a
    retry beside such a message does not make it due earlier."""
    rows = session.execute(
        select(journal_batch.c.id, journal_batch.c.external_id, outbox_message.c.next_attempt_at)
        .select_from(
            journal_batch.join(
                outbox_message,
                and_(
                    outbox_message.c.tenant_id == journal_batch.c.tenant_id,
                    outbox_message.c.id == journal_batch.c.outbox_message_id,
                ),
            )
        )
        .where(
            journal_batch.c.journal_run_id == run_id,
            outbox_message.c.status == OutboxStatus.FAILED.value,
        )
        .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
    )
    return [
        {
            "journal_batch_id": str(batch_id),
            "external_id": str(external_id),
            "next_attempt_at": due.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
        for batch_id, external_id, due in rows
    ]


# --- the job (05 §5.6) ----------------------------------------------------------------------------

MODE_PARAM: Final = JOURNAL_EXPORT_MODE_PARAM
# The two modes of the relay itself (04 API-S-Job rev 1.281; item JRN-JOB-MODE-1): which command
# deferred the job — the run's export, or the retry of one batch, which names its batch. The
# relay does the same for both; the mode is what a reader of the job is told (API-S-Job ``mode``,
# ``result.mode``), so that a frame which finds the job under way tells an export of the run from
# a retry of a batch. A job deferred before rev 1.281 stores neither and is relayed all the same.
MODE_EXPORT: Final = "EXPORT"
MODE_RETRY: Final = "RETRY"
RELAY_MODES: Final = frozenset({MODE_EXPORT, MODE_RETRY})
BATCH_PARAM: Final = "journal_batch_id"
type ModeHandler = Callable[[JobContext, Mapping[str, Any]], JobOutcome]
# The modes of ``JOURNAL_EXPORT`` beside the relay of a run's messages, by ``params.mode``. The
# module that builds a mode registers it here on import (``failed_exits``: ``CANCEL``,
# ``HAND_OVER``); the worker imports it with its handler modules (``worker.HANDLER_MODULES``).
MODE_HANDLERS: Final[dict[str, ModeHandler]] = {}


@dataclass(frozen=True, slots=True)
class Refused:
    """The decision of a ``JOURNAL_EXPORT`` mode not to do what was asked (dev-guide
    DG-KRN-JOB-05 rev 1.142; 05 §5.6 rev 1.98). The kernel retries every error a handler raises
    while attempts remain, so a refusal another attempt cannot change is not raised: the mode
    returns it, after it committed what the ledger said, and the job ends
    ``SUCCEEDED_WITH_EXCEPTIONS`` with ``result.outcome`` and the problem object as
    ``result.refusal`` — what a screen reads to tell "done" from "not done, and why" (04 §16.7)."""

    outcome: str
    problem: Problem

    def job_outcome(self, jc: JobContext, run_id: UUID, counts: Mapping[str, int]) -> JobOutcome:
        return JobOutcome(
            state="SUCCEEDED_WITH_EXCEPTIONS",
            result={
                "href": RUN_HREF.format(run_id=run_id),
                "counts": dict(counts),
                "outcome": self.outcome,
                "refusal": self.problem.to_json(instance=JOB_HREF.format(job_id=jc.job_id)),
            },
        )


@task(JobKind.JOURNAL_EXPORT, retry=outbox.RELAY_RETRY)
def export_job(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``JOURNAL_EXPORT`` (05 §5.6 queue ``outbox``): dispatch the run's due export messages, or
    run the mode ``params.mode`` names (``MODE_HANDLERS``). The relay's ``result`` holds
    ``counts`` — the messages of the run's batches and what this job did with them —,
    ``waiting``, the batches that are sent again later (``waiting``), and what the job states of
    the command that deferred it (``stated_mode``, 04 §16.7 rev 1.281)."""
    mode = params.get(MODE_PARAM)
    if mode is not None and str(mode) not in RELAY_MODES:
        handler = MODE_HANDLERS.get(str(mode))
        if handler is None:
            raise LookupError(f"no handler is registered for JOURNAL_EXPORT mode {mode}")
        return handler(jc, params)
    run_id = UUID(str(params["journal_run_id"]))
    with jc.read_session() as session:
        message_ids = [
            UUID(str(value))
            for value in session.scalars(
                select(journal_batch.c.outbox_message_id)
                .where(
                    journal_batch.c.journal_run_id == run_id,
                    journal_batch.c.outbox_message_id.is_not(None),
                )
                .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
            )
        ]
    stats = outbox.relay_messages(jc, message_ids, topic=OutboxTopic.JOURNAL_EXPORT)
    counts = {
        "messages": len(message_ids),
        "claimed": stats.claimed,
        "dispatched": stats.dispatched,
        "failed": stats.failed,
        "dead": stats.dead,
    }
    with jc.read_session() as session:
        due_again = waiting(session, run_id)
        stated = stated_mode(session, params)
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": RUN_HREF.format(run_id=run_id),
            "counts": counts,
            "waiting": due_again,
            **stated,
        },
    )


def stated_mode(session: Session, params: Mapping[str, Any]) -> dict[str, Any]:
    """What the relay's result says of the command that deferred it (04 §16.7 ``retry`` rev
    1.281; item JRN-JOB-MODE-1): ``mode``, in the word API-S-Job ``mode`` answers, and for a
    retry ``batch`` — the id and the external id of the batch the command named, so that a
    screen says the batch's sentence whoever watches the job. Nothing for a job that stores no
    mode: it was deferred before rev 1.281 and may have been either."""
    stored = params.get(MODE_PARAM)
    if stored is None:
        return {}
    stated: dict[str, Any] = {"mode": JOURNAL_EXPORT_MODES[str(stored)]}
    batch_id = params.get(BATCH_PARAM)
    if str(stored) == MODE_RETRY and batch_id is not None:
        external_id = session.execute(
            select(journal_batch.c.external_id).where(journal_batch.c.id == UUID(str(batch_id)))
        ).scalar_one_or_none()
        if external_id is not None:
            stated["batch"] = {"id": str(batch_id), "external_id": str(external_id)}
    return stated


# --- download (REQ-JE-011) ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Download:
    content: bytes
    file_name: str
    sha256: str


def _require_download(ctx: RequestContext, entity_id: UUID) -> None:
    """Pass when ``journal.export`` or ``report.export`` is held for ``entity_id``; else 404."""
    for code in DOWNLOAD_PERMISSIONS:
        try:
            require_for_entity(ctx, code, entity_id)
        except Problem:
            continue
        return
    raise Problem("not-found")


def download_batch(
    ctx: RequestContext, batch_id: UUID, *, files: FileStore, keyring: KeyRing
) -> Download:
    """``GET /journal-batches/{id}/download``: the stored export file, or the file rendered from the
    batch's lines before its export; one ``journal_batch.download`` audit event.

    D-87 L6-3-Q-12: the caller needs ``journal.export`` or ``report.export``. Holding neither is
    403 ``forbidden`` with one ``DENIED`` event (DG-KRN-AUTH-05); holding one but not for the
    batch's entity is 404 ``not-found`` (DG-KRN-AUTH-04). A ``draft`` or ``cancelled`` batch stays
    409. A batch that is rendered — ``approved`` and not yet exported, or ``failed`` — is counted
    and totalled first, as a dispatch does (``recount``): lines that are not the ones the batch
    was approved with answer 409 ``invalid-transition``, rule ``BATCH_RECOUNT`` (PRD ERR-79; 04
    §16.7 rev 1.159).

    One artifact, one digest (04 §16.7 rev 1.245): the caller's permission and entity scope
    decide whether the batch is downloaded; what is downloaded is the batch as it leaves
    (``chunk_of``), so two readers of one batch receive equal bytes and their events record one
    ``sha256``."""
    if all(ctx.principal.permission_scopes.get(code) is None for code in DOWNLOAD_PERMISSIONS):
        audit_writer.record_denied(
            ctx,
            action=DOWNLOAD_ACTION,
            object_type=BATCH_OBJECT,
            object_id=batch_id,
            permission=EXPORT_PERMISSION,
            detail={"accepted_permissions": list(DOWNLOAD_PERMISSIONS)},
            keyring=keyring,
        )
        raise Problem("forbidden")
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        batch = (
            session.execute(
                select(
                    journal_batch.c.entity_id,
                    journal_batch.c.state,
                    journal_batch.c.export_file_id,
                    *(journal_batch.c[column] for column, _ in RECOUNTED),
                ).where(journal_batch.c.id == batch_id)
            )
            .mappings()
            .one_or_none()
        )
        if batch is None:
            raise Problem("not-found")
        _require_download(ctx, UUID(str(batch["entity_id"])))
        if _text(batch["state"]) not in EXPORTABLE:
            error = ProblemError(field="state", rule_id=RULE_STATES, message=NOT_DOWNLOADABLE)
            raise Problem("invalid-transition", NOT_DOWNLOADABLE, errors=[error])
        chunk = chunk_of(session, batch_id)
        if batch["export_file_id"] is None:
            changed = recount(dict(batch), chunk, consequence=NOT_DOWNLOADED)
            if changed is not None:
                error = ProblemError(field="lines", rule_id=RULE_RECOUNT, message=changed)
                raise Problem("invalid-transition", changed, errors=[error])
            content = render_export(chunk)
        else:
            _, stream = open_file(
                session, UUID(str(batch["export_file_id"])), files=files, keyring=keyring
            )
            with stream:
                content = stream.read()
    digest = hashlib.sha256(content).hexdigest()
    audit_writer.record_now(
        ctx,
        action=DOWNLOAD_ACTION,
        object_type=BATCH_OBJECT,
        object_id=batch_id,
        detail={"external_id": chunk.external_id, "sha256": digest},
        keyring=keyring,
    )
    return Download(content=content, file_name=f"{export_name(chunk)}.zip", sha256=digest)


outbox.SCHEDULES[OutboxTopic.JOURNAL_EXPORT] = outbox.DispatchSchedule(
    max_attempts=RETRY_ATTEMPTS, delay=export_delay
)
outbox.HANDLERS[OutboxTopic.JOURNAL_EXPORT] = dispatch_batch
outbox.DEAD_HOOKS[OutboxTopic.JOURNAL_EXPORT] = batch_died
