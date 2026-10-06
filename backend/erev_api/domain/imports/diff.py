"""IPL-07 dry-run diff: the ``IMPORT_DIFF`` job and API-S-ImportDiff (05 §5.5 IPL-07, §5.6; 04
T-IMP-02, §16.6 API-S-Import ``diff_summary`` and API-S-ImportDiff, E-118; PRD SM-05, BR-DAT-02,
BR-DAT-05; 03 REQ-DAT-015; BUILD_SPEC DIN-3).

``compute_diff`` runs in the transaction of a DIFFING upload:

1. The stored state of every contract the file names gives ``before`` (primary book: the group's
   latest version ``transaction_price`` and each obligation's ``allocated_amount``).
2. Inside a savepoint the command plans of the usable rows run through the command services as
   the import principal (``import_unit``): a new contract is booked and computed provisionally, a
   draft is replaced, and the resulting versions give ``after``.
3. The savepoint rolls back and the audit events it buffered are dropped, so nothing is persisted
   before commit (BR-DAT-05).
4. ``diff_summary`` and the diff file (JSON of the counts, the items and the stream heads of the
   named contracts at diff time) are stored; DIFFING → DIFF_READY.

[J] L5-1-Q-7:
- A plan the command services refuse raises ``IMPORT_PROCESSING_FAILED`` (ERROR) on its first row
  and has no items; the import still reaches DIFF_READY.
- ``allocation_changes`` holds one entry per obligation in obligation-key order;
  ``revenue_by_period_delta`` and ``journal_preview`` stay empty until DIN-5 adds progress rows.
- The diff file uses purpose ``IMPACT_PREVIEW`` (E-68 has no diff purpose), and
  ``GET /imports/{id}/diff`` answers every item on one page.
- A template without an emitter (``emitter_of``: CSV v2 or legacy v1) diffs empty. Since DIN-4 the
  legacy SKU SSP and contract setup templates diff through their emitters.
"""

from __future__ import annotations

import dataclasses
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.currencies import ISO_4217
from pydantic import ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.db import locking
from erev_api.db.session import of_session_tenant
from erev_api.db.tables import (
    contract,
    contract_version,
    file_object,
    import_row,
    import_upload,
    obligation,
    obligation_version,
    period,
    schedule,
    schedule_line,
    tenant_membership,
)
from erev_api.db.transitions import apply
from erev_api.domain.contracts import period_ends, repo
from erev_api.domain.contracts import queries as contract_queries
from erev_api.domain.imports import csv_v2, findings, job_hooks, legacy_v1, scope
from erev_api.domain.imports.csv_v2.framework import (
    UNEVALUATED,
    ApplyContext,
    ContractChange,
    CsvRow,
    CsvTemplate,
    Performed,
    Plan,
)
from erev_api.domain.imports.exceptions import raise_exception_item, severity_of
from erev_api.enums import (
    ApprovalSubjectType,
    ExceptionSource,
    FilePurpose,
    ImportDiffChange,
    ImportStatus,
    JobKind,
    NotificationKind,
)
from erev_api.events.notifications import notify
from erev_api.files.store import FileStore, open_file, store_file
from erev_api.jobs.registry import (
    JOB_FAILED_BODY,
    JOB_FAILED_TITLE,
    JOB_LABELS,
    JOB_SUBJECT,
    JobOutcome,
    RetryPolicy,
    task,
)
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.imports import ImportDiffCountsOut, ImportDiffItemOut, ImportDiffOut
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext

__all__ = [
    "IMPORT_PERMISSIONS",
    "compute_diff",
    "diff_job_failed",
    "emitter_of",
    "fail_diff",
    "get_diff",
    "hand_over",
    "import_diff",
    "import_rows",
    "import_unit",
    "original_filename",
    "start_diff",
    "stored_bases",
]

OBJECT_TYPE: Final = "import_upload"
DIFF_ACTION: Final = "import_upload.diff"
DIFF_MEDIA: Final = "application/json"
DIFF_RULE: Final = "API-S-ImportDiff"
FAILED_CODE: Final = "IMPORT_PROCESSING_FAILED"
REVENUE_SCHEDULE: Final = "REVENUE"  # T-SL-01 schedule_kind of the revenue schedule (DIN-9)
IMPORT_HREF: Final = "/api/v1/imports/{import_id}"
# 05 §5.6: IMPORT_DIFF takes 2 attempts with a 10 second wait.
DIFF_RETRY: Final = RetryPolicy(max_attempts=2, backoff_seconds=(10,))
# PRD NTF-05, the step of the body: a failure hook runs after the job's last attempt and is not
# handed its number.
LAST_ATTEMPT: Final = "its last attempt"
# AGGREGATED rows are loaded with their lead row, whose template sums them (BUILD_SPEC DIN-5).
USABLE: Final = scope.USABLE
DIFFED: Final = frozenset(
    {
        ImportStatus.DIFF_READY.value,
        ImportStatus.SUBMITTED.value,
        ImportStatus.APPROVED.value,
        ImportStatus.COMMITTING.value,
        ImportStatus.COMMITTED.value,
        ImportStatus.FAILED.value,
        ImportStatus.REJECTED.value,
        ImportStatus.CANCELLED.value,
    }
)
# [J] L5-1-Q-11, narrowed by supervisor ruling R-29 (05 rev 1.46 IPL-07, IPL-10): the command
# services an import runs as SYSTEM on behalf of the uploader, whose upload permission and the
# approval authorised them — WITHIN the uploader's entity scope for the template's write permission
# (``scope.uploader_bounds``), no longer for every entity. A legacy setup import also prepares the
# BS3-D-23 judgement records (BUILD_SPEC DIN-4). The CSV v2 ``estimates`` template prepares DRAFT
# estimate versions (BUILD_SPEC DIN-9, D-86).
IMPORT_PERMISSIONS: Final = frozenset(
    {"contract.create", "estimate.create", "judgement.create", "masterdata.maintain"}
)


# --- shared with the commit ----------------------------------------------------------------------


def emitter_of(template_code: str) -> CsvTemplate | None:
    """The emitter of a template: a CSV v2 template (DIN-3, DIN-9) or a legacy v1 template (DIN-4 to
    DIN-6); None for a template without one."""
    return csv_v2.TEMPLATES.get(template_code) or legacy_v1.TEMPLATES.get(template_code)


def original_filename(session: Session, file_object_id: Any) -> str | None:
    """The original file name of an upload's file (BS3-D-23 ``document_ref``)."""
    found = session.execute(
        select(file_object.c.original_filename).where(file_object.c.id == file_object_id)
    ).scalar_one_or_none()
    return None if found is None else str(found)


def import_rows(session: Session, import_id: UUID) -> list[CsvRow]:
    """The VALID and WARNING rows of an upload in row order."""
    statement = (
        select(import_row)
        .where(import_row.c.import_upload_id == import_id, import_row.c.status.in_(USABLE))
        .order_by(import_row.c.sheet_name, import_row.c.row_number)
    )
    return [
        CsvRow(
            id=UUID(str(row["id"])),
            sheet_name=str(row["sheet_name"]),
            row_number=int(row["row_number"]),
            raw=dict(row["raw"] or {}),
            normalized=dict(row["normalized"] or {}),
            business_key=None if row["business_key"] is None else str(row["business_key"]),
        )
        for row in session.execute(statement).mappings()
    ]


def import_principal(tenant_id: UUID, uploader_id: UUID | None, bounds: scope.Bounds) -> Principal:
    """SYSTEM on behalf of the uploader, holding the import's command permissions for the
    uploader's scope only (ruling R-29)."""
    return scope.import_principal(
        system_principal(tenant_id, on_behalf_of_id=uploader_id),
        IMPORT_PERMISSIONS,
        bounds.db_scope,
    )


def import_unit(uow: UnitOfWork, uploader_id: UUID | None, bounds: scope.Bounds) -> UnitOfWork:
    """A unit of work of the import principal in the caller's transaction and instant. The caller
    narrows the transaction to the same scope (``scope.narrowed``)."""
    ctx = dataclasses.replace(
        uow.ctx, principal=import_principal(uow.principal.tenant_id, uploader_id, bounds)
    )
    unit = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    unit.now = uow.now
    return unit


def hold_plan_windows(unit: UnitOfWork, template: CsvTemplate, plans: Sequence[Plan]) -> None:
    """dev-guide DG-KRN-DB-08 (1c) rev 1.218 (finding F4 of the independent review of 2026-10-01).
    A template whose plans compute contract by contract (``CsvTemplate.computes``) posts for its
    first contract — taking the book's chain head — before it reads the window of its second.
    Before the first plan runs, the group and contract rows of every contract the plans name are
    locked on the order of (1) — the commit of an approved import holds them already — and the
    windows of their groups are held (``period_ends.hold_windows``). A contract the caller's
    scope does not show is left to its plan, which refuses it by name."""
    if not template.computes or not plans:
        return
    session = unit.session
    named = sorted({plan.key for plan in plans})
    found = [
        UUID(str(contract_id))
        for contract_id in session.execute(
            select(contract.c.id).where(contract.c.external_id.in_(named))
        ).scalars()
    ]
    locked = locking.lock_groups_then_contracts(session, found)
    period_ends.hold_windows(
        unit, {UUID(str(row["combination_group_id"])) for row in locked.values()}
    )


def hand_over(unit: UnitOfWork, uow: UnitOfWork) -> None:
    """Move the audit events buffered by ``unit`` into the caller's unit of work."""
    for event in unit.drain_audit_events():
        uow.buffer_audit_event(event)


def stored_bases(uow: UnitOfWork, row: Mapping[str, Any]) -> list[tuple[str, int | None]]:
    """The stream heads the diff recorded for the contracts the file names."""
    if row["diff_file_id"] is None:
        return []
    document = _document(uow.session, row["diff_file_id"], files=uow.files, keyring=uow.keyring)
    return [(str(key), None if head is None else int(head)) for key, head in document["contracts"]]


# --- the dry run ---------------------------------------------------------------------------------


@dataclass(slots=True)
class ContractState:
    transaction_price: Decimal | None
    currency: str
    allocations: dict[str, Decimal] = field(default_factory=dict)
    revenue_cum: dict[str, Decimal] = field(default_factory=dict)  # by obligation key
    revenue: dict[str, Decimal] = field(default_factory=dict)  # REVENUE schedule by period key


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _locked(session: Session, import_id: UUID) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(import_upload).where(import_upload.c.id == import_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def _status(row: Mapping[str, Any]) -> str:
    return str(getattr(row["status"], "value", row["status"]))


def start_diff(uow: UnitOfWork, import_id: UUID) -> bool:
    """VALIDATED → DIFFING; True when the upload is DIFFING afterwards (a retried attempt)."""
    row = _locked(uow.session, import_id)
    if row is None:
        return False
    status = _status(row)
    if status == ImportStatus.VALIDATED.value:
        apply(
            uow.session,
            OBJECT_TYPE,
            import_id,
            to_status=ImportStatus.DIFFING.value,
            set_values=_stamps(uow),
            expected_status=status,
        )
        return True
    return status == ImportStatus.DIFFING.value


def _state(session: Session, contract_id: UUID, group_id: UUID, book_code: str) -> ContractState:
    currency = str(
        session.execute(
            select(contract.c.transaction_currency).where(contract.c.id == contract_id)
        ).scalar_one()
    ).strip()
    version = session.execute(
        select(contract_version.c.id, contract_version.c.transaction_price)
        .where(
            contract_version.c.combination_group_id == group_id,
            contract_version.c.book_code == book_code,
        )
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    ).one_or_none()
    if version is None:
        return ContractState(transaction_price=None, currency=currency)
    statement = (
        select(
            obligation.c.obligation_key,
            obligation_version.c.allocated_amount,
            obligation_version.c.revenue_cum,
        )
        .select_from(
            obligation_version.join(
                obligation,
                and_(
                    obligation.c.tenant_id == obligation_version.c.tenant_id,
                    obligation.c.id == obligation_version.c.obligation_id,
                ),
            )
        )
        .where(
            obligation_version.c.contract_version_id == version.id,
            obligation_version.c.contract_id == contract_id,
        )
    )
    obligations = list(session.execute(statement))
    revenue = (
        select(period.c.period_key, schedule_line.c.amount)
        .select_from(
            schedule_line.join(
                schedule,
                and_(
                    schedule.c.tenant_id == schedule_line.c.tenant_id,
                    schedule.c.id == schedule_line.c.schedule_id,
                ),
            ).join(
                period,
                and_(
                    period.c.tenant_id == schedule_line.c.tenant_id,
                    period.c.id == schedule_line.c.period_id,
                ),
            )
        )
        .where(
            schedule_line.c.contract_version_id == version.id,
            schedule_line.c.contract_id == contract_id,
            schedule.c.schedule_kind == REVENUE_SCHEDULE,
        )
    )
    by_period: dict[str, Decimal] = {}
    for key, amount in session.execute(revenue):
        by_period[str(key)] = by_period.get(str(key), Decimal(0)) + Decimal(amount)
    return ContractState(
        transaction_price=Decimal(version.transaction_price),
        currency=currency,
        allocations={str(row.obligation_key): Decimal(row.allocated_amount) for row in obligations},
        revenue_cum={str(row.obligation_key): Decimal(row.revenue_cum) for row in obligations},
        revenue=by_period,
    )


def _before(
    session: Session, plans: Sequence[Plan], book_code: str
) -> dict[str, tuple[int, ContractState]]:
    found: dict[str, tuple[int, ContractState]] = {}
    for plan in plans:
        current = repo.contract_by_external_id(session, plan.key)
        if current is None:
            continue
        state = _state(
            session, UUID(str(current["id"])), UUID(str(current["combination_group_id"])), book_code
        )
        found[plan.key] = (int(current["head_stream_version"]), state)
    return found


def _failure_text(error: Exception) -> str:
    if isinstance(error, Problem):
        details = [error.detail or error.slug] + [
            f"{item.field or 'row'}: {item.message}" for item in error.errors
        ]
        return "; ".join(str(part) for part in details if part)
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in item['loc']) or 'row'}: {item['msg']}"
            for item in error.errors()
        )
    return str(error)


def _change(before: ContractState | None, after: ContractState) -> ContractChange:
    """What a plan did to one contract, as an underlying approval's thresholds read it (04
    API-S-ImpactSummary: the transaction price on both sides and ``catch_up_total``, the change of
    cumulative revenue summed over the obligations)."""
    earlier = {} if before is None else before.revenue_cum
    keys = set(after.revenue_cum) | set(earlier)
    return ContractChange(
        currency=after.currency,
        transaction_price_before=Decimal(0)
        if before is None or before.transaction_price is None
        else before.transaction_price,
        transaction_price_after=Decimal(0)
        if after.transaction_price is None
        else after.transaction_price,
        catch_up_total=sum(
            (after.revenue_cum.get(key, Decimal(0)) - earlier.get(key, Decimal(0)) for key in keys),
            Decimal(0),
        ),
    )


def _dry_run(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    template: CsvTemplate,
    plans: Sequence[Plan],
    book_code: str,
    bounds: scope.Bounds,
    before: Mapping[str, tuple[int, ContractState]],
) -> tuple[
    dict[str, ContractState],
    list[tuple[Plan, str]],
    dict[ApprovalSubjectType, list[Performed]],
]:
    """The plans applied inside a savepoint that is rolled back: the contract states after them,
    the plans that failed and — for a template whose commit performs an approval-coded act — the
    approvals the commit would perform, each with the routing facts a request of its subject
    would carry: the flags of its content and its functional amount (rulings R-38 (ii) and R-98;
    item IMP-FLOOR-AMOUNT-1; ``CsvTemplate.underlying``). A plan that fails states one
    unevaluated approval of every subject the template can perform."""
    session = uow.session
    after: dict[str, ContractState] = {}
    failures: list[tuple[Plan, str]] = []
    performed: dict[ApprovalSubjectType, list[Performed]] = {}
    unit = import_unit(uow, row["created_by"], bounds)
    context = ApplyContext(
        import_upload_id=UUID(str(row["id"])),
        file_sha256=str(row["file_sha256"]).strip(),
        template_code=str(row["template_code"]),
        template_version=int(row["template_version"]),
        dry_run=True,
        import_no=str(row["import_no"]),
        original_filename=original_filename(session, row["file_object_id"]),
        parameters=dict(row["parameters"] or {}),
        uploader_id=None if row["created_by"] is None else UUID(str(row["created_by"])),
    )
    kept = uow.drain_audit_events()
    savepoint = session.begin_nested()
    try:
        hold_plan_windows(unit, template, plans)
        for plan in plans:
            inner = session.begin_nested()
            try:
                applied = template.apply(unit, plan, context=context)
            except (Problem, ValidationError, ValueError, LookupError) as error:
                inner.rollback()
                failures.append((plan, _failure_text(error)))
                if template.underlying is not None:
                    for subject in scope.scope_of(template.code).puts_in_force:
                        performed.setdefault(subject, []).append(UNEVALUATED)
                continue
            inner.commit()
            changes: dict[str, ContractChange] = {}
            for external_id, contract_id, group_id, _head in applied.contracts:
                after[external_id] = _state(session, contract_id, group_id, book_code)
                earlier = before.get(external_id)
                changes[external_id] = _change(
                    None if earlier is None else earlier[1], after[external_id]
                )
            if template.underlying is not None:
                found = template.underlying(session, plan, applied, context, changes)
                for subject, approvals in found.items():
                    performed.setdefault(subject, []).extend(approvals)
    finally:
        savepoint.rollback()
        unit.drain_audit_events()
        uow.drain_audit_events()
        for event in kept:
            uow.buffer_audit_event(event)
    return after, failures, performed


def _amount(value: Decimal | None, currency: str) -> str | None:
    if value is None:
        return None
    minor = ISO_4217[currency].minor_unit
    return format(value.quantize(Decimal(1).scaleb(-minor)), "f")


def _summarise(
    plans: Sequence[Plan],
    before: Mapping[str, tuple[int, ContractState]],
    after: Mapping[str, ContractState],
    underlying: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    counts = {
        "contracts_added": 0,
        "contracts_changed": 0,
        "obligations_added": 0,
        "obligations_changed": 0,
    }
    items: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    revenue_delta: dict[str, tuple[Decimal, str]] = {}
    # A contract that several plans name (one event row per plan, DIN-9) is summarised once.
    keys_in_order = list(dict.fromkeys(plan.key for plan in plans))
    for external_id in keys_in_order:
        state = after.get(external_id)
        if state is None:
            continue
        prior = before.get(external_id)
        old = None if prior is None else prior[1]
        added = old is None
        counts["contracts_added" if added else "contracts_changed"] += 1
        if added or old is None or old.transaction_price != state.transaction_price:
            items.append(
                {
                    "change": (ImportDiffChange.ADDED if added else ImportDiffChange.CHANGED).value,
                    "contract_external_id": external_id,
                    "obligation_key": None,
                    "measure": "transaction_price",
                    "before": None if old is None else _amount(old.transaction_price, old.currency),
                    "after": _amount(state.transaction_price, state.currency),
                }
            )
        keys = sorted(set(state.allocations) | set({} if old is None else old.allocations))
        for key in keys:
            was = None if old is None else old.allocations.get(key)
            now = state.allocations.get(key)
            if was is not None and was == now:
                continue
            counts["obligations_added" if was is None else "obligations_changed"] += 1
            items.append(
                {
                    "change": (
                        ImportDiffChange.ADDED if was is None else ImportDiffChange.CHANGED
                    ).value,
                    "contract_external_id": external_id,
                    "obligation_key": key,
                    "measure": "allocated_amount",
                    "before": _amount(was, state.currency),
                    "after": _amount(now, state.currency),
                }
            )
            changes.append(
                {
                    "contract_external_id": external_id,
                    "before": _amount(was, state.currency),
                    "after": _amount(now, state.currency),
                }
            )
        for key in sorted(state.revenue_cum):
            was = None if old is None else old.revenue_cum.get(key)
            now = state.revenue_cum[key]
            if old is None or was == now:
                continue
            items.append(
                {
                    "change": ImportDiffChange.CHANGED.value,
                    "contract_external_id": external_id,
                    "obligation_key": key,
                    "measure": "revenue_cum",
                    "before": _amount(was, state.currency),
                    "after": _amount(now, state.currency),
                }
            )
        periods = set(state.revenue) | set({} if old is None else old.revenue)
        for period_key in periods:
            was_amount = Decimal(0) if old is None else old.revenue.get(period_key, Decimal(0))
            delta = state.revenue.get(period_key, Decimal(0)) - was_amount
            total, _ = revenue_delta.get(period_key, (Decimal(0), state.currency))
            revenue_delta[period_key] = (total + delta, state.currency)
    summary = {
        "contracts_affected": len(after),
        "contracts_created": counts["contracts_added"],
        "allocation_changes": changes,
        "revenue_by_period_delta": [
            {"period_key": period_key, "amount": _amount(amount, currency)}
            for period_key, (amount, currency) in sorted(revenue_delta.items())
            if amount != 0
        ],
        "journal_preview": [],
    }
    document: dict[str, Any] = {
        "summary_counts": counts,
        "items": items,
        "contracts": [
            [key, None if key not in before else before[key][0]] for key in keys_in_order
        ],
    }
    if underlying is not None:
        # 04 §16.6 rev 1.107 (ruling R-38 (ii)): stated in the summary the approver reads and in
        # the diff file, whose hash the approved content holds (05 IPL-08)
        summary[scope.UNDERLYING_MEMBER] = underlying
        document[scope.UNDERLYING_MEMBER] = underlying
    return summary, document


def compute_diff(uow: UnitOfWork, import_id: UUID) -> dict[str, Any] | None:
    """IPL-07 for a DIFFING upload; None when the upload is no longer DIFFING."""
    session = uow.session
    row = _locked(session, import_id)
    if row is None or _status(row) != ImportStatus.DIFFING.value:
        return None
    template = emitter_of(str(row["template_code"]))
    plans = [] if template is None else template.plans(import_rows(session, import_id))
    primary = contract_queries.primary_book(session)
    book_code = str(getattr(primary, "value", primary))
    after: dict[str, ContractState] = {}
    failures: list[tuple[Plan, str]] = []
    performed: dict[ApprovalSubjectType, list[Performed]] = {}
    # 05 IPL-07 rev 1.46 (ruling R-29; SC-2): `before` is read and the plans run INSIDE the
    # uploader's scope for the template's write permission, read from the uploader's grants now
    bounds = scope.uploader_bounds(session, row, str(row["template_code"]), at=uow.now)
    # EXC-IMPORT-SCOPE-1 (04 T-IMP-05 rev 1.218): the existing contract a failed plan's first
    # row names in the template's contract column — as validation reads it, the plan's key is
    # not always the contract's — with its contracting entity. Read inside the uploader's scope,
    # so a contract outside it is named by no finding, as an unknown one.
    named: dict[str, tuple[UUID, UUID]] = {}
    column = scope.scope_of(str(row["template_code"])).contract_column
    with scope.narrowed(uow, bounds.db_scope):
        before = _before(session, plans, book_code)
        if template is not None and plans:
            after, failures, performed = _dry_run(
                uow, row, template, plans, book_code, bounds, before
            )
        if column is not None:
            for plan, _ in failures:
                first = plan.rows[0]
                key = scope.key_text({**first.raw, **(first.normalized or {})}.get(column))
                current = None if key is None else repo.contract_by_external_id(session, key)
                if current is not None:
                    named[plan.key] = (
                        UUID(str(current["id"])),
                        UUID(str(current["contracting_entity_id"])),
                    )
    summary, document = _summarise(
        plans,
        before,
        after,
        None
        if template is None or template.underlying is None
        else scope.underlying_record(performed),
    )
    for plan, failure in failures:
        first = plan.rows[0]
        message = f"Row {first.row_number} ({plan.key}) cannot be applied: {failure}"
        if template is not None and template.code in csv_v2.TEMPLATES:
            # D-87 L6-1-Q-2: the CSV form of CPY-06. [J] L7-4-Q-4: the column is the key column,
            # which names the object the command applies to.
            message = findings.csv_located(
                f"{plan.key} cannot be applied: {failure}",
                FAILED_CODE,
                row_number=first.row_number,
                column=template.key_column,
            )
        raise_exception_item(
            uow,
            source=ExceptionSource.IMPORT,
            code=FAILED_CODE,
            severity=severity_of("ERROR"),
            message=message,
            dedupe=f"{ExceptionSource.IMPORT.value}:{FAILED_CODE}:{import_id}:{first.row_number}",
            business_key=plan.key,
            import_upload_id=import_id,
            import_row_id=first.id,
            contract_id=named[plan.key][0] if plan.key in named else None,
            entity_id=named[plan.key][1] if plan.key in named else None,
        )
    content = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    stored = store_file(
        uow,
        purpose=FilePurpose.IMPACT_PREVIEW,
        stream=io.BytesIO(content.encode("utf-8")),
        original_filename=f"{row['import_no']}-diff.json",
        media_type=DIFF_MEDIA,
    )
    apply(
        session,
        OBJECT_TYPE,
        import_id,
        to_status=ImportStatus.DIFF_READY.value,
        set_values={"diff_summary": summary, "diff_file_id": stored["id"], **_stamps(uow)},
        expected_status=ImportStatus.DIFFING.value,
    )
    uow.audit(
        action=DIFF_ACTION,
        object_type=OBJECT_TYPE,
        object_id=import_id,
        before={"status": ImportStatus.DIFFING.value},
        after={
            "status": ImportStatus.DIFF_READY.value,
            "contracts_affected": summary["contracts_affected"],
            "contracts_created": summary["contracts_created"],
            "failures": len(failures),
        },
    )
    return {"summary": summary, "failures": len(failures)}


def _uploader(session: Session, row: Mapping[str, Any]) -> list[UUID]:
    """The memberships of the person who uploaded the file; none for an API client's upload."""
    if row["created_by"] is None:
        return []
    return [
        UUID(str(value))
        for value in session.scalars(
            select(tenant_membership.c.id).where(
                of_session_tenant(tenant_membership),
                tenant_membership.c.user_id == row["created_by"],
            )
        )
    ]


def fail_diff(uow: UnitOfWork, import_id: UUID, problem: Mapping[str, Any]) -> UUID | None:
    """DIFFING → INVALID with one ``IMPORT_PROCESSING_FAILED`` item under the job's reference
    (04 T-IMP-02 rev 1.270; PRD SM-05 rev 1.186), and the uploader told that the dry run failed
    (PRD NTF-05): the system starts the dry run, so the job's own notification reaches nobody.
    None when the upload is not DIFFING. The rows the validation stored stay as they are; the
    file is uploaded again."""
    session = uow.session
    row = _locked(session, import_id)
    if row is None or _status(row) != ImportStatus.DIFFING.value:
        return None
    apply(
        session,
        OBJECT_TYPE,
        import_id,
        to_status=ImportStatus.INVALID.value,
        set_values=_stamps(uow),
        expected_status=ImportStatus.DIFFING.value,
    )
    item = raise_exception_item(
        uow,
        source=ExceptionSource.IMPORT,
        code=FAILED_CODE,
        severity=severity_of("ERROR"),
        message=findings.processing_failed(uow.ctx.request_id),
        dedupe=f"{ExceptionSource.IMPORT.value}:{FAILED_CODE}:{import_id}",
        import_upload_id=import_id,
    )
    uow.audit(
        action=DIFF_ACTION,
        object_type=OBJECT_TYPE,
        object_id=import_id,
        before={"status": ImportStatus.DIFFING.value},
        after={
            "status": ImportStatus.INVALID.value,
            "code": FAILED_CODE,
            "exception_item_id": str(item.id),
        },
    )
    job_id = str(problem.get("instance") or "").rsplit("/", 1)[-1]
    label = JOB_LABELS[JobKind.IMPORT_DIFF]
    reason = str(problem.get("detail") or problem["title"]).rstrip(".")
    notify(
        uow,
        recipient_membership_ids=_uploader(session, row),
        kind=NotificationKind.JOB_FAILED,
        title=JOB_FAILED_TITLE.format(label=label),
        body=JOB_FAILED_BODY.format(label=label, step=LAST_ATTEMPT, reason=reason),
        subject_type=JOB_SUBJECT,
        subject_id=UUID(job_id),
    )
    return item.id


def diff_job_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The job's failure hook (05 §5.6 rev 1.185; the supervisor's ruling of 2026-10-02;
    ``job_hooks``), as the validation's and the commit's. ``import_diff`` has no catch-all — an
    error leaves it and the job is retried — so every dry run that ends FAILED comes here: its
    last attempt met an error, before the upload was ``DIFFING`` or while it was, or its worker
    died. The upload it finds ``VALIDATED`` or ``DIFFING`` ends ``INVALID`` with
    ``IMPORT_PROCESSING_FAILED`` (``fail_diff``). Before, it stayed where it was for good, and
    nobody was told: no pair left ``DIFFING`` on a failure (revision 0122).

    An upload in any other status is left alone — the diff was stored before the job failed, or
    the uploader cancelled — and so is one whose row another transaction holds
    (``job_hooks.held_status``). The kind registers no ``failed_item``: the upload's
    finding is the item of a failed dry run, and an ``INFO`` item that closes with a
    later run of the record would promise what an ``INVALID`` import cannot keep
    (``jobs.registry.task``; the supervisor's ruling of 2026-10-02)."""
    import_id = UUID(str(params["import_upload_id"]))
    found = job_hooks.held_status(
        uow.session, import_id, (ImportStatus.VALIDATED, ImportStatus.DIFFING)
    )
    if found is None:
        return
    if found == ImportStatus.VALIDATED.value:
        start_diff(uow, import_id)
    fail_diff(uow, import_id, problem)


@task(JobKind.IMPORT_DIFF, retry=DIFF_RETRY, on_failure=diff_job_failed)
def import_diff(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``IMPORT_DIFF`` (05 §5.6 queue ``imports``): the dry-run diff of one validated upload."""
    import_id = UUID(str(params["import_upload_id"]))
    href = IMPORT_HREF.format(import_id=import_id)
    with ctx.unit_of_work() as uow:
        started = start_diff(uow, import_id)
        uow.commit()
    if not started:
        return JobOutcome(state="SUCCEEDED", result={"href": href, "counts": {}})
    with ctx.unit_of_work() as uow:
        outcome = compute_diff(uow, import_id)
        uow.commit()
    if outcome is None:
        return JobOutcome(state="SUCCEEDED", result={"href": href, "counts": {}})
    summary = outcome["summary"]
    counts = {
        "contracts_affected": summary["contracts_affected"],
        "contracts_created": summary["contracts_created"],
        "failures": outcome["failures"],
    }
    state: Literal["SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS"] = (
        "SUCCEEDED" if outcome["failures"] == 0 else "SUCCEEDED_WITH_EXCEPTIONS"
    )
    return JobOutcome(state=state, result={"href": href, "counts": counts})


# --- API-S-ImportDiff ----------------------------------------------------------------------------


def _document(
    session: Session, file_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    _, stream = open_file(session, file_id, files=files, keyring=keyring)
    with stream:
        loaded: dict[str, Any] = json.loads(stream.read().decode("utf-8"))
    return loaded


def get_diff(
    session: Session, import_id: UUID, *, files: FileStore, keyring: KeyRing
) -> ImportDiffOut:
    """``GET /imports/{id}/diff``; 404 when absent, 409 ``invalid-transition`` before DIFF_READY."""
    row = (
        session.execute(select(import_upload).where(import_upload.c.id == import_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    if _status(dict(row)) not in DIFFED or row["diff_file_id"] is None:
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(
                    rule_id=DIFF_RULE,
                    message="The dry-run diff is available once the import is ready for review.",
                )
            ],
        )
    document = _document(session, row["diff_file_id"], files=files, keyring=keyring)
    return ImportDiffOut(
        summary_counts=ImportDiffCountsOut.model_validate(document["summary_counts"]),
        items=[ImportDiffItemOut.model_validate(item) for item in document["items"]],
        next_cursor=None,
    )
