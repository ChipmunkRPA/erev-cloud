"""One period of an entity and book brought to its lock as the product does (PRD §2.1 WLD-R-02,
§2.2 WLD-P-02; BR-CLS-01 to BR-CLS-03, BR-CLS-08, BR-JE-03, BR-PLT-06; BUILD_SPEC CLO-22; supervisor
ruling of 2026-10-01 on lane F-ADM-WEB's design line, items 12 and PERF-SEED-LOCK-1).

``close_period`` is what a seed calls for a period it wants ``closed``. It writes nothing itself:
every step is the command a person presses, as the persona who holds its permission, and a job a
command defers runs in place as the worker runs it (``jobs.registry.run_job``), because no worker
runs beside a seed.

1. ``start-close`` (``period.close``, the preparer).
2. The close run (``POST /close-runs``, the preparer): it recomputes what is dirty, posts the three
   period-end passes, checks the ledger, calculates the period's ``draft`` journal run and writes
   the twelve datasets. Periods close in order — a pass is refused over an earlier period end no
   close run has posted — so the caller closes a book's months from the earliest on.
3. The journal run: submitted by the preparer, approved by the reviewer, exported by the preparer.
   A batch takes its adapter when the run is calculated: ``CSV`` while the entity has no ACTIVE
   outbound GL connection. The export stores the file and leaves the batch ``exported``; the
   preparer then records the ledger's document reference (``POST /journal-batches/{id}/
   acknowledge``, BR-JE-03), which is what acknowledges a batch without a connection. A run
   without a line — a period without activity — is left as the close run calculated it
   (``stands_as_calculated``).
4. The reconciliations the lock requires (``close.require_reconciliations_for_lock``; a tenant
   that sets it false is asked for none). Billing to subledger: generated; a difference is
   explained by the preparer; prepared; reviewed. Subledger to GL: generated, then given its trial
   balance as an uploaded file, prepared and reviewed.
5. Manual close tasks, when the workspace has any, signed by the controller.
6. ``request-lock`` (the preparer, with the certification comment) and the ``PERIOD_LOCK``
   decision (the controller), which evaluates the gates again, freezes the datasets and certifies
   the reconciliations.

A reviewer's sign-off and the lock decision ask for a second-factor verification at most five
minutes old in the command itself (BR-PLT-06), so the persona verifies again first when hers is
older (``BuildContext.step_up``).

[J] The trial balance of a seeded period is written from the subledger's own closing balances — the
balance of every subledger-controlled account at the period end in the functional currency, a
balance sheet account cumulative and an income statement account for its fiscal year, as
``close.trial_balance`` measures both sides. It shows the form of the tie-out, not two independent
books (ruled for the demo world; PRD §2.2 WLD-P-02 says so). A variance after the attach stops the
seed: the file is meant to agree.

[J] The file is the ledger an ERP keeps (BUILD_SPEC CLO-17, the role basis; supervisor rulings R-69
(a) and R-74). Under ``billing.posting = ERP`` an invoice is ingested and never posted by the
subledger: the ERP posts it, Dr receivable / Cr contract liability, and the subledger holds it in
the stored contract balance — which is what the reconciliation compares the contract balance roles
with. So the contract liability account takes the subledger's lines AND the billing the ERP posts
itself (``reconciliations.erp_posted_billing``); from the lines alone it would differ by every
invoice. That billing is the engine's own figure, as the stored balance is: the file ties by
construction, and its tie shows that the two sides of the reconciliation are computed
consistently — not that an independent ledger agrees.

[J] A period that is already ``closed`` is left alone, and each step reads the state it finds — a
run that succeeded, a journal that is acknowledged, a reconciliation that is reviewed — so a seed
that resumes repeats nothing.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import and_, func, select

from erev_api.db.tables import (
    close_run,
    gl_account,
    job,
    journal_batch,
    journal_run,
    legal_entity,
    period,
    period_state,
    reconciliation,
    reconciliation_item,
    subledger_line,
)
from erev_api.domain.close import close_runs, gates, reconciliations
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import queries as close_queries
from erev_api.domain.contracts import compute_job
from erev_api.domain.demo.avenmoor import expect_version
from erev_api.domain.journals import commands as journal_commands
from erev_api.domain.journals import export as journal_export
from erev_api.domain.journals import ports as gl_ports
from erev_api.domain.journals import summarise
from erev_api.domain.platform import attachments
from erev_api.enums import (
    ApprovalSubjectType,
    BookCode,
    CloseRunStatus,
    FilePurpose,
    GlAdapter,
    JobState,
    JournalState,
    PeriodState,
    ReconciliationKind,
    ReconciliationStatus,
    SignoffRole,
)
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.schemas.close import ChecklistSignIn
from erev_api.schemas.close_runs import CloseRunCreateIn
from erev_api.schemas.journals import JournalRunExportIn, JournalRunSubmitIn, PostingAckCreateIn
from erev_api.schemas.periods import PeriodLockRequestIn, PeriodStartCloseIn
from erev_api.schemas.reconciliations import (
    ReconciliationAttachIn,
    ReconciliationCreateIn,
    ReconciliationItemUpdateIn,
    ReconciliationSignIn,
)

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

# The job handler modules ``run_job`` dispatches to (the worker's HANDLER_MODULES): the close run
# with the computations and the journal calculation it starts, the export and the reconciliations.
HANDLER_MODULES: Final = (close_runs, compute_job, summarise, journal_export, reconciliations)
FINISHED: Final = frozenset({JobState.SUCCEEDED.value, JobState.SUCCEEDED_WITH_EXCEPTIONS.value})
POSTABLE: Final = frozenset({PeriodState.OPEN.value, PeriodState.REOPENED.value})
LOCKED: Final = frozenset({PeriodState.CLOSED.value, PeriodState.PERMANENTLY_LOCKED.value})
# The route guards of the commands the personas run (04 §15.3 API-R-38 to API-R-40, §16.7, §16.8).
CLOSE: Final = close_runs.CLOSE_PERMISSION
JOURNAL_RUN: Final = journal_commands.RUN_PERMISSION
JOURNAL_EXPORT: Final = journal_export.EXPORT_PERMISSION
RECON_PREPARE: Final = reconciliations.PREPARE_PERMISSION
RECON_SIGNOFF: Final = reconciliations.SIGNOFF_PERMISSION
START_COMMENT: Final = "Month-end close."
JOURNAL_COMMENT: Final = "Journal of the month."
CERTIFICATION: Final = "Journals acknowledged and reconciliations reviewed: the month is complete."
ACKNOWLEDGED: Final = "Imported into the general ledger from the CSV export."
BILLING_EXPLANATION: Final = (
    "Recorded by hand from the invoice: no billing document reaches this workspace yet."
)
CSV_MEDIA_TYPE: Final = "text/csv"
NO_CSV_ADAPTER: Final = (
    "no CSV general-ledger adapter is registered: the command that runs the seed registers it "
    "(DG-LAY-03), as the worker does"
)


@dataclass(frozen=True, slots=True)
class ClosingCast:
    """Persona keys of a ``BuildContext.cast`` acting in a close (WLD-R-02: nobody decides what
    she prepared)."""

    preparer: str  # starts the close and its run, submits and exports the journal, reconciles
    reviewer: str  # approves the journal run and reviews the reconciliations
    controller: str  # signs manual close tasks and decides the lock


@dataclass(frozen=True, slots=True)
class _Period:
    state_id: UUID
    row_version: int
    state: str
    entity_id: UUID
    period_id: UUID
    end_date: date
    entity_code: str
    book: BookCode
    period_key: str

    @property
    def name(self) -> str:
        return f"{self.entity_code} {self.book.value} {self.period_key}"


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _period(ctx: BuildContext, entity_code: str, book: BookCode, period_key: str) -> _Period:
    with ctx.read() as session:
        row = session.execute(
            select(
                period_state.c.id,
                period_state.c.row_version,
                period_state.c.state,
                period_state.c.entity_id,
                period_state.c.period_id,
                period.c.end_date,
            )
            .select_from(
                period_state.join(
                    period,
                    and_(
                        period.c.tenant_id == period_state.c.tenant_id,
                        period.c.id == period_state.c.period_id,
                    ),
                ).join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == period_state.c.tenant_id,
                        legal_entity.c.id == period_state.c.entity_id,
                    ),
                )
            )
            .where(
                legal_entity.c.code == entity_code,
                period_state.c.book_code == book.value,
                period.c.period_key == period_key,
            )
        ).one()
    return _Period(
        state_id=UUID(str(row.id)),
        row_version=int(row.row_version),
        state=_value(row.state),
        entity_id=UUID(str(row.entity_id)),
        period_id=UUID(str(row.period_id)),
        end_date=row.end_date,
        entity_code=entity_code,
        book=book,
        period_key=period_key,
    )


def _expect(row_version: int) -> Callable[[int], None]:
    """The ``If-Match`` check of a command for the row version the persona just read."""
    return expect_version(row_version)


def _run(ctx: BuildContext, job_id: UUID, what: str) -> None:
    """Run a deferred job as the worker does; ``LookupError`` when it does not finish."""
    runtime = JobRuntime(clock=ctx.clock, keyring=ctx.keyring, files=ctx.files)
    run_job(job_id, ctx.tenant_id, attempt=1, runtime=runtime)
    with ctx.read() as session:
        state = _value(session.execute(select(job.c.state).where(job.c.id == job_id)).scalar_one())
    if state not in FINISHED:
        raise LookupError(f"{what}: job {job_id} ended {state}")


def _scope(ctx: BuildContext, at: _Period) -> gates.PeriodScope:
    with ctx.read() as session:
        scope = gates.period_scope(session, at.state_id)
    if scope is None:
        raise LookupError(f"{at.name} has no period state")
    return scope


# --- 1 and 2: the soft close and the close run ---------------------------------------------------


def _start_close(ctx: BuildContext, cast: ClosingCast, at: _Period) -> None:
    if at.state not in POSTABLE:
        return
    with ctx.command(cast.preparer, CLOSE) as uow:
        close_commands.start_close(
            uow,
            state_id=at.state_id,
            body=PeriodStartCloseIn(comment=START_COMMENT),
            check_version=_expect(at.row_version),
        )


def _latest_close_run(ctx: BuildContext, at: _Period) -> dict[str, Any] | None:
    with ctx.read() as session:
        row = (
            session.execute(
                select(close_run.c.id, close_run.c.close_run_no, close_run.c.status)
                .where(
                    close_run.c.entity_id == at.entity_id,
                    close_run.c.book_code == at.book.value,
                    close_run.c.period_id == at.period_id,
                )
                .order_by(close_run.c.created_at.desc(), close_run.c.id.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
    return None if row is None else {str(name): value for name, value in row.items()}


def _close_run(ctx: BuildContext, cast: ClosingCast, at: _Period) -> None:
    latest = _latest_close_run(ctx, at)
    if latest is not None and _value(latest["status"]) == CloseRunStatus.SUCCEEDED.value:
        return
    with ctx.command(cast.preparer, CLOSE) as uow:
        started = close_runs.start(
            uow,
            CloseRunCreateIn(entity_code=at.entity_code, book=at.book, period_key=at.period_key),
        )
    if started.job is not None:
        _run(ctx, started.job.id, f"close run of {at.name}")
    latest = _latest_close_run(ctx, at)
    if latest is None or _value(latest["status"]) != CloseRunStatus.SUCCEEDED.value:
        found = "none" if latest is None else f"{latest['close_run_no']} {_value(latest['status'])}"
        raise LookupError(f"the close run of {at.name} did not succeed: {found}")


# --- 3: the journal run ---------------------------------------------------------------------------


def _journal_runs(ctx: BuildContext, at: _Period) -> list[tuple[UUID, str, int]]:
    """The period's journal runs that are not cancelled: id, state and line count."""
    with ctx.read() as session:
        rows = session.execute(
            select(journal_run.c.id, journal_run.c.state, journal_run.c.line_count)
            .where(
                journal_run.c.entity_id == at.entity_id,
                journal_run.c.book_code == at.book.value,
                journal_run.c.period_id == at.period_id,
                journal_run.c.state != JournalState.CANCELLED.value,
            )
            .order_by(journal_run.c.created_at, journal_run.c.id)
        ).all()
    return [(UUID(str(run_id)), _value(state), int(lines)) for run_id, state, lines in rows]


def stands_as_calculated(state: str, line_count: int) -> bool:
    """A ``draft`` journal run without a line is the run of a period without activity, and it is
    the period's run as it stands: there is nothing a second person could approve and nothing
    leaves eRev, so the helper neither submits nor exports it. The lock asks a run of the period
    that is not cancelled and no batch still to acknowledge — both hold. Item JRN-EMPTY-RUN-1
    makes the submission of such a run a refusal (409), which would stop a seed that sent it.
    Pure."""
    return state == JournalState.DRAFT.value and line_count == 0


def _batches(ctx: BuildContext, run_id: UUID) -> list[dict[str, Any]]:
    with ctx.read() as session:
        rows = session.execute(
            select(
                journal_batch.c.id,
                journal_batch.c.state,
                journal_batch.c.batch_no,
                journal_batch.c.chunk_no,
                journal_batch.c.last_error,
            )
            .where(journal_batch.c.journal_run_id == run_id)
            .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
        ).mappings()
        return [{str(name): value for name, value in row.items()} for row in rows]


def document_reference(entity_code: str, period_key: str, batch_no: int, chunk_no: int) -> str:
    """The ledger's document number a person records for an imported CSV batch (BR-JE-03)."""
    return f"GL-{entity_code}-{period_key}-{batch_no:02d}-{chunk_no:02d}"


def _run_state(ctx: BuildContext, run_id: UUID) -> str:
    with ctx.read() as session:
        return _value(
            session.execute(
                select(journal_run.c.state).where(journal_run.c.id == run_id)
            ).scalar_one()
        )


def _journal(ctx: BuildContext, cast: ClosingCast, at: _Period) -> None:
    for run_id, state, lines in _journal_runs(ctx, at):
        if stands_as_calculated(state, lines):
            continue
        if state == JournalState.DRAFT.value:
            with ctx.command(cast.preparer, JOURNAL_RUN) as uow:
                journal_commands.submit_run(
                    uow, run_id, JournalRunSubmitIn(comment=JOURNAL_COMMENT)
                )
            # A workspace's auto-approval rule may have decided the request at the submit.
            if _run_state(ctx, run_id) == JournalState.DRAFT.value:
                ctx.approve(ApprovalSubjectType.JOURNAL_RUN, run_id, [cast.reviewer])
            state = _run_state(ctx, run_id)
        if state == JournalState.APPROVED.value:
            if GlAdapter.CSV not in gl_ports.GL_ADAPTERS:
                raise LookupError(NO_CSV_ADAPTER)
            with ctx.command(cast.preparer, JOURNAL_EXPORT) as uow:
                exporting = journal_export.export_run(uow, run_id, JournalRunExportIn())
            _run(ctx, exporting.id, f"journal export of {at.name}")
        for batch in _batches(ctx, run_id):
            batch_state = _value(batch["state"])
            if batch_state == JournalState.ACKNOWLEDGED.value:
                continue
            if batch_state != JournalState.EXPORTED.value:
                raise LookupError(
                    f"a journal batch of {at.name} is {batch_state}, not exported: "
                    f"{batch['last_error'] or 'no error recorded'}"
                )
            with ctx.command(cast.preparer, JOURNAL_EXPORT) as uow:
                journal_export.acknowledge_batch(
                    uow,
                    UUID(str(batch["id"])),
                    PostingAckCreateIn(
                        gl_document_id=document_reference(
                            at.entity_code,
                            at.period_key,
                            int(batch["batch_no"]),
                            int(batch["chunk_no"]),
                        ),
                        gl_posted_date=at.end_date,
                        message=ACKNOWLEDGED,
                    ),
                )


# --- 4: the reconciliations the lock requires -----------------------------------------------------


def _required_kinds(ctx: BuildContext, scope: gates.PeriodScope) -> Sequence[str]:
    """The kinds the lock still waits for: required by the registry and not yet reviewed."""
    now = ctx.clock.now()
    with ctx.read() as session:
        required = gates.required_kinds(session, scope, known_at=now)
        if not required:
            return ()
        reviewed = gates.reconciliations_reviewed(session, scope, known_at=now)
    return () if reviewed["reviewed"] == reviewed["required"] else required


def _generate(ctx: BuildContext, cast: ClosingCast, at: _Period, kind: ReconciliationKind) -> UUID:
    with ctx.command(cast.preparer, RECON_PREPARE) as uow:
        reconciliation_id, generating = reconciliations.request_generation(
            uow,
            ReconciliationCreateIn(
                kind=kind, entity_code=at.entity_code, book=at.book, period_key=at.period_key
            ),
        )
    _run(ctx, generating.id, f"{kind.value} reconciliation of {at.name}")
    return reconciliation_id


def _status(ctx: BuildContext, reconciliation_id: UUID) -> tuple[str, int, datetime]:
    with ctx.read() as session:
        row = session.execute(
            select(
                reconciliation.c.status,
                reconciliation.c.variance_count,
                reconciliation.c.as_of_known_at,
            ).where(reconciliation.c.id == reconciliation_id)
        ).one()
    return _value(row.status), int(row.variance_count), row.as_of_known_at


def _explain(ctx: BuildContext, cast: ClosingCast, reconciliation_id: UUID, text: str) -> None:
    with ctx.read() as session:
        items = session.execute(
            select(
                reconciliation_item.c.id,
                reconciliation_item.c.row_version,
                reconciliation_item.c.difference,
                reconciliation_item.c.explanation,
            )
            .where(reconciliation_item.c.reconciliation_id == reconciliation_id)
            .order_by(reconciliation_item.c.created_at, reconciliation_item.c.id)
        ).all()
    for item in items:
        if Decimal(item.difference) == 0 or item.explanation:
            continue
        with ctx.command(cast.preparer, RECON_PREPARE) as uow:
            reconciliations.explain_item(
                uow,
                reconciliation_id=reconciliation_id,
                item_id=UUID(str(item.id)),
                body=ReconciliationItemUpdateIn(explanation=text),
                check_version=_expect(int(item.row_version)),
            )


def _sign_off(ctx: BuildContext, cast: ClosingCast, reconciliation_id: UUID) -> None:
    """The preparer's sign-off, then the reviewer's with a verification inside the window."""
    with ctx.command(cast.preparer, RECON_PREPARE) as uow:
        reconciliations.prepare(uow, reconciliation_id)
    ctx.step_up(cast.reviewer)
    with ctx.command(cast.reviewer, RECON_SIGNOFF) as uow:
        reconciliations.sign(
            uow,
            reconciliation_id,
            ReconciliationSignIn(role=SignoffRole.REVIEWER, statement_accepted=True),
        )


def closing_balances(
    ctx: BuildContext, scope: gates.PeriodScope, as_of: datetime
) -> dict[str, Decimal]:
    """The closing balance of every subledger-controlled account of the entity and book at the
    period end, in the functional currency, as a ledger the ERP keeps holds it (module docstring
    [J]): the subledger's lines recorded by ``as_of`` — a balance sheet account over every period
    through the end, an income statement account over the periods of the period's fiscal year —
    and, on the contract liability account, the billing the ERP posts itself under
    ``billing.posting = ERP``."""
    posting = period.alias("posting_period")
    with ctx.read() as session:
        fiscal_year = int(
            session.execute(
                select(period.c.fiscal_year).where(period.c.id == scope.period_id)
            ).scalar_one()
        )
        accounts = reconciliations.controlled_accounts(session, scope, as_of)
        rows = session.execute(
            select(
                gl_account.c.code,
                gl_account.c.account_type,
                posting.c.fiscal_year,
                func.sum(subledger_line.c.amount_functional),
            )
            .select_from(
                subledger_line.join(
                    gl_account,
                    and_(
                        gl_account.c.tenant_id == subledger_line.c.tenant_id,
                        gl_account.c.id == subledger_line.c.gl_account_id,
                    ),
                ).join(
                    posting,
                    and_(
                        posting.c.tenant_id == subledger_line.c.tenant_id,
                        posting.c.id == subledger_line.c.period_id,
                    ),
                )
            )
            .where(
                subledger_line.c.entity_id == scope.entity_id,
                subledger_line.c.book_code == scope.book_code,
                subledger_line.c.period_end_date <= scope.end_date,
                subledger_line.c.recorded_at <= as_of,
            )
            .group_by(gl_account.c.code, gl_account.c.account_type, posting.c.fiscal_year)
        ).all()
        by_the_erp = reconciliations.erp_posted_billing(session, scope, as_of)
    balances = dict.fromkeys(accounts, Decimal(0))
    for code, account_type, year, amount in rows:
        if str(code) not in balances:
            continue
        if _value(account_type) in reconciliations.BALANCE_SHEET_TYPES or int(year) == fiscal_year:
            balances[str(code)] += Decimal(amount)
    for code, amount in by_the_erp.items():
        balances[code] = balances.get(code, Decimal(0)) + amount
    return balances


def trial_balance_csv(balances: Mapping[str, Decimal], currency: str) -> bytes:
    """The uploaded form of a trial balance (BUILD_SPEC CLO-17): ``account,currency,amount``."""
    rows = ["account,currency,amount"]
    rows += [
        f"{code},{currency},{reconciliations.amount_text(balances[code], currency)}"
        for code in sorted(balances)
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def _reconcile_billing(ctx: BuildContext, cast: ClosingCast, at: _Period) -> None:
    reconciliation_id = _generate(ctx, cast, at, ReconciliationKind.BILLING_TO_SUBLEDGER)
    status, _, _ = _status(ctx, reconciliation_id)
    if status != ReconciliationStatus.DRAFT.value:
        return  # certified by a published rule: nothing differs
    _explain(ctx, cast, reconciliation_id, BILLING_EXPLANATION)
    _sign_off(ctx, cast, reconciliation_id)


def _reconcile_ledger(
    ctx: BuildContext, cast: ClosingCast, at: _Period, scope: gates.PeriodScope
) -> None:
    reconciliation_id = _generate(ctx, cast, at, ReconciliationKind.SUBLEDGER_TO_GL)
    _, _, as_of = _status(ctx, reconciliation_id)
    currency = scope.functional_currency.strip()
    content = trial_balance_csv(closing_balances(ctx, scope, as_of), currency)
    name = f"trial-balance-{at.entity_code}-{at.book.value}-{at.period_key}.csv".lower()
    with ctx.command(cast.preparer) as uow:
        stored = attachments.upload_file(
            uow,
            purpose=FilePurpose.IMPORT_SOURCE.value,
            stream=io.BytesIO(content),
            original_filename=name,
            media_type=CSV_MEDIA_TYPE,
        )
    with ctx.command(cast.preparer, RECON_PREPARE) as uow:
        attaching = reconciliations.request_trial_balance(
            uow, reconciliation_id, ReconciliationAttachIn(file_id=UUID(str(stored["id"])))
        )
    _run(ctx, attaching.id, f"trial balance of {at.name}")
    status, variances, _ = _status(ctx, reconciliation_id)
    if variances:
        raise LookupError(
            f"the trial balance written for {at.name} differs from the subledger in "
            f"{variances} place(s); the reconciliation stays {status}"
        )
    _sign_off(ctx, cast, reconciliation_id)


def _reconcile(ctx: BuildContext, cast: ClosingCast, at: _Period) -> None:
    scope = _scope(ctx, at)
    kinds = _required_kinds(ctx, scope)
    if ReconciliationKind.BILLING_TO_SUBLEDGER.value in kinds:
        _reconcile_billing(ctx, cast, at)
    if ReconciliationKind.SUBLEDGER_TO_GL.value in kinds:
        _reconcile_ledger(ctx, cast, at, scope)


# --- 5 and 6: the manual tasks and the lock -------------------------------------------------------


def _sign_tasks(ctx: BuildContext, cast: ClosingCast, at: _Period) -> None:
    scope = _scope(ctx, at)
    with ctx.read() as session:
        items = close_queries.checklist_items(session, scope)
    for item in items:
        if _value(item["gate_kind"]).upper() != "MANUAL" or _value(item["status"]).upper() != (
            "PENDING"
        ):
            continue
        with ctx.command(cast.controller) as uow:
            fresh = gates.period_scope(uow.session, at.state_id)
            assert fresh is not None
            close_commands.sign_checklist_item(
                uow,
                state_id=at.state_id,
                item_id=UUID(str(item["id"])),
                body=ChecklistSignIn(statement_accepted=True),
                check_version=_expect(fresh.row_version),
            )


def _lock(ctx: BuildContext, cast: ClosingCast, at: _Period, certification: str) -> None:
    with ctx.command(cast.preparer, CLOSE) as uow:
        fresh = gates.period_scope(uow.session, at.state_id)
        assert fresh is not None
        close_commands.request_lock(
            uow,
            state_id=at.state_id,
            body=PeriodLockRequestIn(certification_comment=certification),
            check_version=_expect(fresh.row_version),
        )
    ctx.step_up(cast.controller)
    ctx.approve(ApprovalSubjectType.PERIOD_LOCK, at.state_id, [cast.controller])


def close_period(
    ctx: BuildContext,
    cast: ClosingCast,
    *,
    entity_code: str,
    book: BookCode,
    period_key: str,
    certification: str = CERTIFICATION,
    before_lock: Callable[[UUID], object] | None = None,
) -> None:
    """Bring the period of ``entity_code`` and ``book`` to ``closed`` (module docstring). A
    ``Problem`` of a command propagates — a refused lock names every gate that has not passed —
    and ``LookupError`` names a job, a batch or a reconciliation that did not end as it must.

    ``certification`` is the comment of the lock request: a world whose lock asks no
    reconciliation says its own. ``before_lock`` is called with the period state's id after the
    close run — the last step that computes — and the journal run, and before the
    reconciliations: a world whose people clear findings of its own before a lock — the volume
    tenant waives its generator's late events (``perf_seed``) — does it there. Nothing stands
    between the review of a reconciliation and the lock: what is recorded for the period after
    a review makes the gate ask for the reconciliation again."""
    at = _period(ctx, entity_code, book, period_key)
    if at.state in LOCKED:
        return
    _start_close(ctx, cast, at)
    _close_run(ctx, cast, at)
    _journal(ctx, cast, at)
    if before_lock is not None:
        before_lock(at.state_id)
    _reconcile(ctx, cast, at)
    _sign_tasks(ctx, cast, at)
    _lock(ctx, cast, at, certification)
    after = _period(ctx, entity_code, book, period_key)
    if after.state not in LOCKED:
        raise LookupError(f"{at.name} is {after.state} after its lock decision")
