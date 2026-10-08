"""IPL-08 to IPL-12: submit, approval, atomic commit, quarantine mode and control totals (05 §5.5
IPL-08 to IPL-12, §5.6; 04 T-IMP-02, T-IMP-04, §16.6 import commands, table 15.4-B
``CONTROL_TOTALS_MISMATCH``; PRD SM-05, §2.5 ``IMPORT_COMMIT``, BR-DAT-01 to BR-DAT-05, IMP-43,
NTF-11; 03 REQ-DAT-001, REQ-DAT-008, REQ-DAT-010; controls CTL-001, CTL-044; BUILD_SPEC DIN-3).

1. ``submit_import`` (uploader, ``DIFF_READY``) moves the import to SUBMITTED and opens the
   ``IMPORT_COMMIT`` request with the diff as impact preview. An upload by an API client whose
   control totals cover every data row and which has no ERROR finding may match an
   ``AUTO_APPROVAL`` rule such as ``AUTO-IMP-01`` (PRD §2.5).
2. Approval moves it to APPROVED and defers ``IMPORT_COMMIT``; rejection, and a void of the
   request, move it to REJECTED (L5-1-Q-8).
3. The job moves it to COMMITTING, then commits in one transaction: the contract heads recorded by
   the diff are checked, every usable row gets its ``source_record``, the plans run through the
   command services, ``import_row_lineage`` names every emitted object, and
   ``control_totals.loaded`` must account for every source row (loaded plus quarantined). With
   ``is_quarantine_mode`` the ERROR rows stay behind with their open exception items (REQ-DAT-008).
4. A successful commit queues one CONTRACT_COMPUTE child per affected group (IPL-11),
   dispatched after commit. Calculation failures cannot roll back the imported facts.
5. Any failure of the import transaction rolls the commit back; a new transaction sets FAILED
   and raises
   ``CONTROL_TOTALS_MISMATCH`` or ``IMPORT_PROCESSING_FAILED`` for the integration owner, who is
   notified ``EXCEPTION_ASSIGNED`` (IPL-12; L5-1-Q-9).

Supervisor ruling R-98 (04 rev 1.147; 05 rev 1.86 IPL-08, IPL-10):

- (1) *An import needs its source.* ``submit_import`` and ``commit_upload`` lock the upload's
  ``file_object`` row and refuse a source whose content was shredded, by name (``FILE_SHREDDED``,
  PRD IMP-50). ``file.shred`` takes the same row lock before it reads which records hold the file
  (``privacy.shred_file``), so a shred and a submission are serialised on that row: the later of
  the two sees what the earlier one committed — a submitted import holds its source
  (``FILE_EVIDENCE_HELD``), a shredded source is never submitted.
- (8) ``submit_import`` answers 404 for an upload outside the caller's ``contract.read`` scope,
  as the reads do (``scope.require_visible``), before the uploader check.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from sqlalchemy import func, insert, select, update

from erev_api.approvals import subjects
from erev_api.approvals.engine import ImpactPreview, consume_fresh_basis
from erev_api.approvals.engine import submit as submit_request
from erev_api.approvals.subjects import SubjectLifecycle, register_lifecycle
from erev_api.audit import writer as audit_writer
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import errors as db_errors
from erev_api.db import locking, new_id
from erev_api.db.session import of_session_tenant, system_entity_scope
from erev_api.db.tables import (
    contract,
    exception_item,
    file_object,
    import_row,
    import_row_lineage,
    import_upload,
    tenant_membership,
)
from erev_api.db.transitions import apply
from erev_api.domain.contracts import period_ends, repo
from erev_api.domain.imports import commands, diff, job_hooks, queries, scope
from erev_api.domain.imports.csv_v2.framework import ApplyContext, CsvRow, CsvTemplate
from erev_api.domain.imports.exceptions import raise_exception_item, severity_of
from erev_api.domain.integrations import normalise
from erev_api.enums import (
    ApprovalSubjectType,
    ComputationTrigger,
    ControlResult,
    ExceptionSeverity,
    ExceptionSource,
    ImportRowStatus,
    ImportStatus,
    JobKind,
    NotificationKind,
    PrincipalKind,
)
from erev_api.events.notifications import notify
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem, ProblemError, is_period_state_moved
from erev_api.schemas.imports import ImportOut, ImportSubmitIn

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "COMMIT_ACTION",
    "ControlTotalsMismatch",
    "SourceShredded",
    "commit_upload",
    "fail_commit",
    "import_commit",
    "start_commit",
    "submit_import",
]

OBJECT_TYPE: Final = "import_upload"
SUBMIT_ACTION: Final = "import_upload.submit"
APPROVE_ACTION: Final = "import_upload.approve"
REJECT_ACTION: Final = "import_upload.reject"
COMMIT_ACTION: Final = "import_upload.commit"
FAIL_ACTION: Final = "import_upload.fail"
MISMATCH_CODE: Final = "CONTROL_TOTALS_MISMATCH"
FAILED_CODE: Final = "IMPORT_PROCESSING_FAILED"
LIFECYCLE_RULE: Final = "SM-05"
SHREDDED_RULE: Final = "FILE_SHREDDED"  # 04 table 15.4-B (rev 1.147); PRD IMP-50
# PRD IMP-50, for the source of an import (ruling R-98 (1)).
SOURCE_SHREDDED: Final = (
    "The content of {file} was shredded on {date}. Its SHA-256 remains as evidence."
)
SOURCE_FILE: Final = "the source file"  # a file stored without a name
NOT_COMMITTED: Final = (
    "The import could not be committed and nothing was committed. Reference: {reference}."
)
# 05 §5.6: IMPORT_COMMIT takes no retry; a failed commit rolls back and the user resubmits. One
# refusal is run again inside the job, once: a period lock decided while the commit ran (rev
# 1.195; ``_commit_after_a_lock``).
COMMIT_RETRY: Final = RetryPolicy(max_attempts=1, backoff_seconds=())
IMPORT_HREF: Final = "/api/v1/imports/{import_id}"
_LOGGER: Final = "erev_api.domain.imports.commit"

register_logger_fields(_LOGGER, ("import_upload_id", "error_class"))


class ControlTotalsMismatch(Exception):
    """IPL-12: the loaded totals do not account for the source totals."""

    def __init__(self, source: Mapping[str, Any], loaded: Mapping[str, Any]) -> None:
        super().__init__("control totals mismatch")
        self.source = dict(source)
        self.loaded = dict(loaded)


class StaleImport(Exception):
    """IPL-10: a contract changed after the diff."""


class SourceShredded(Exception):
    """Ruling R-98 (1): the content of the import's source file was shredded; its message is the
    refusal by name (PRD IMP-50)."""


@dataclass(frozen=True, slots=True)
class Committed:
    rows: int
    quarantined: int
    objects: int


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _locked(session: Any, import_id: UUID) -> dict[str, Any] | None:
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


def _shredded_source(session: Any, row: Mapping[str, Any]) -> str | None:
    """Lock the ``file_object`` row of the upload's source and answer the refusal by name when
    its content was shredded, else None (ruling R-98 (1); module docstring). The lock is held to
    the end of the caller's transaction, after the upload row's own."""
    source = session.execute(
        select(file_object.c.original_filename, file_object.c.shredded_at)
        .where(file_object.c.id == row["file_object_id"])
        .with_for_update()
    ).one()
    if source.shredded_at is None:
        return None
    return SOURCE_SHREDDED.format(
        file=source.original_filename or SOURCE_FILE,
        date=source.shredded_at.astimezone(UTC).date().isoformat(),
    )


# --- submit (IPL-08) -----------------------------------------------------------------------------


def _auto_approvable(uow: UnitOfWork, row: Mapping[str, Any]) -> bool:
    """PRD §2.5 ``AUTO-IMP-01`` guards: an API client upload whose source totals cover every data
    row and which has no ERROR finding (L5-1-Q-10)."""
    if uow.principal.kind is not PrincipalKind.API_CLIENT:
        return False
    # Ruling R-38 (ii): an import commit never stands in for a stricter approval — a template whose
    # commit itself activates a contract or puts a version in force is decided by a person.
    if scope.scope_of(str(row["template_code"])).puts_in_force:
        return False
    source = (row["control_totals"] or {}).get("source") or {}
    usable = int(row["valid_row_count"] or 0) + int(row["warning_count"] or 0)
    blocking = uow.session.execute(
        select(func.count())
        .select_from(exception_item)
        .where(
            exception_item.c.import_upload_id == row["id"],
            exception_item.c.severity == ExceptionSeverity.BLOCKING.value,
        )
    ).scalar_one()
    if int(source.get("rows", -1)) != usable or int(blocking) != 0:
        return False
    # BR-DAT-07: no auto-approval for postings into a closing period (BUILD_SPEC CLO-3).
    return not commands.posts_into_closing_period(uow.session, row)


def submit_import(uow: UnitOfWork, *, import_id: UUID, body: ImportSubmitIn) -> ImportOut:
    """``POST /imports/{id}/submit``: DIFF_READY → SUBMITTED with the ``IMPORT_COMMIT`` request."""
    session = uow.session
    row = _locked(session, import_id)
    if row is None:
        raise Problem("not-found")
    # Ruling R-98 (8): an upload outside the caller's read scope answers as an unknown id.
    scope.require_visible(uow.principal, row)
    if row["created_by"] != uow.principal.id:
        raise Problem("forbidden", "Only the uploader submits an import for approval.")
    if _status(row) != ImportStatus.DIFF_READY.value:
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(
                    rule_id=LIFECYCLE_RULE,
                    message="Submit an import once its dry-run diff is ready.",
                )
            ],
        )
    # Ruling R-98 (1): the source is locked from here to the end of the submission, and an import
    # whose source was shredded is not submitted.
    shredded = _shredded_source(session, row)
    if shredded is not None:
        raise Problem(
            "invalid-transition",
            shredded,
            errors=[ProblemError(rule_id=SHREDDED_RULE, message=shredded)],
        )
    # Ruling R-29 (05 rev 1.46 IPL-08): the uploader's scope for the template's write permission
    # covers every entity the rows to commit name — read again here from the uploader's grants,
    # as the validation read it and the commit will.
    scope.require_covered(
        scope.committing_entity_ids(row),
        scope.uploader_bounds(session, row, str(row["template_code"]), at=uow.now),
    )
    apply(
        session,
        OBJECT_TYPE,
        import_id,
        to_status=ImportStatus.SUBMITTED.value,
        set_values=_stamps(uow),
        expected_status=ImportStatus.DIFF_READY.value,
    )
    request = submit_request(
        uow,
        subject_type=ApprovalSubjectType.IMPORT_COMMIT,
        subject_id=import_id,
        summary=f"Commit import {row['import_no']}",
        impact_preview=ImpactPreview(
            before={"import_no": str(row["import_no"]), "status": ImportStatus.DIFF_READY.value},
            after={"diff_summary": dict(row["diff_summary"] or {})},
        ),
        comment=body.comment,
        auto_approval=_auto_approvable(uow, row),
    )
    request_id = UUID(str(request["id"]))
    current = _locked(session, import_id)
    assert current is not None
    if current["approval_request_id"] is None:
        apply(
            session,
            OBJECT_TYPE,
            import_id,
            to_status=None,
            set_values={"approval_request_id": request_id, **_stamps(uow)},
        )
    uow.audit(
        action=SUBMIT_ACTION,
        object_type=OBJECT_TYPE,
        object_id=import_id,
        before={"status": ImportStatus.DIFF_READY.value},
        after={"status": _status(current), "approval_request_id": str(request_id)},
        comment=body.comment,
        approval_request_id=request_id,
    )
    return queries.get_import(session, import_id)


# --- approval (IPL-09) ---------------------------------------------------------------------------


def _approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    session = uow.session
    # Ruling R-38 (ii): an import commit never stands in for a stricter approval. The decision
    # that approves the request is refused here — and with it undone — unless the approvers
    # satisfy the own steps of every approval the commit performs.
    scope.require_floor_met(session, subject_id, approval_request_id, at=uow.now)
    apply(
        session,
        OBJECT_TYPE,
        subject_id,
        to_status=ImportStatus.APPROVED.value,
        set_values={"approval_request_id": approval_request_id, **_stamps(uow)},
        expected_status=ImportStatus.SUBMITTED.value,
    )
    job = uow.defer(
        JobKind.IMPORT_COMMIT,
        {"import_upload_id": str(subject_id)},
        subject_type=OBJECT_TYPE,
        subject_id=subject_id,
    )
    apply(session, OBJECT_TYPE, subject_id, to_status=None, set_values={"job_id": job["id"]})
    uow.audit(
        action=APPROVE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=subject_id,
        before={"status": ImportStatus.SUBMITTED.value},
        after={"status": ImportStatus.APPROVED.value, "job_id": str(job["id"])},
        approval_request_id=approval_request_id,
    )


def _closed(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    apply(
        uow.session,
        OBJECT_TYPE,
        subject_id,
        to_status=ImportStatus.REJECTED.value,
        set_values=_stamps(uow),
        expected_status=ImportStatus.SUBMITTED.value,
    )
    uow.audit(
        action=REJECT_ACTION,
        object_type=OBJECT_TYPE,
        object_id=subject_id,
        before={"status": ImportStatus.SUBMITTED.value},
        after={"status": ImportStatus.REJECTED.value},
        approval_request_id=approval_request_id,
    )


register_lifecycle(
    ApprovalSubjectType.IMPORT_COMMIT,
    SubjectLifecycle(
        on_approved=_approved,
        on_rejected=_closed,
        on_voided=_closed,
        # Supervisor rulings R-64 (6), R-87 (1) and R-92: the entities of the request, the
        # entities its uploader is held to, the further steps its commit demands and who may
        # give each of its approvals are the imports domain's to state (04 §16.10 rev 1.104;
        # ``approvals.subjects.import_commit_entities`` / ``import_commit_preparer_entities`` /
        # ``import_commit_floor`` / ``import_commit_deciders``).
        entities=scope.request_entities,
        preparer_entities=scope.preparer_entities,
        floor=scope.floor_steps,
        deciders=scope.decider_refusals,
    ),
)


# --- commit (IPL-10 to IPL-12) -------------------------------------------------------------------


def start_commit(uow: UnitOfWork, import_id: UUID) -> bool:
    """APPROVED → COMMITTING; True when the import is COMMITTING afterwards."""
    row = _locked(uow.session, import_id)
    if row is None:
        return False
    status = _status(row)
    if status == ImportStatus.APPROVED.value:
        apply(
            uow.session,
            OBJECT_TYPE,
            import_id,
            to_status=ImportStatus.COMMITTING.value,
            set_values=_stamps(uow),
            expected_status=status,
        )
        return True
    return status == ImportStatus.COMMITTING.value


def _approver(uow: UnitOfWork, approval_request_id: Any) -> UUID | None:
    """The person whose decision approved the request — the last of its approvers in the order
    of their approvals (``scope.approvers_in_order``); None for an automatic approval."""
    if approval_request_id is None:
        return None
    approvers = scope.approvers_in_order(uow.session, UUID(str(approval_request_id)))
    return approvers[-1] if approvers else None


def _answering_approvers(
    uow: UnitOfWork, import_id: UUID, approval_request_id: Any
) -> dict[ApprovalSubjectType, UUID]:
    """Who answered for each approval the commit performs (``scope.answering_approvers``; ruling
    R-98 (9) as refined, 04 §16.10 rev 1.198). The commit runs inside the uploader's scope; the
    request, its decisions and the routing are read under the tenant's SYSTEM scope."""
    if approval_request_id is None:
        return {}
    with system_entity_scope(uow.session):
        return scope.answering_approvers(
            uow.session, import_id, UUID(str(approval_request_id)), at=uow.now
        )


def _check_bases(uow: UnitOfWork, row: Mapping[str, Any]) -> None:
    for external_id, head in diff.stored_bases(uow, row):
        current = repo.contract_by_external_id(uow.session, external_id)
        found = None if current is None else int(current["head_stream_version"])
        if found != head:
            raise StaleImport(external_id)


def commit_upload(
    uow: UnitOfWork, import_id: UUID, *, parent_job_id: UUID | None = None
) -> Committed | None:
    """IPL-10 in the caller's transaction; None when the import is not COMMITTING."""
    session = uow.session
    row = _locked(session, import_id)
    if row is None or _status(row) != ImportStatus.COMMITTING.value:
        return None
    # Ruling R-98 (1): no import is committed without its original file (REQ-DAT-001). A source
    # is held from its submission on, so this is the backstop for an upload submitted before the
    # rule; it fails the commit by name and nothing is written.
    shredded = _shredded_source(session, row)
    if shredded is not None:
        raise SourceShredded(shredded)
    template = diff.emitter_of(str(row["template_code"]))
    rows = diff.import_rows(session, import_id)
    quarantined = (
        int(
            session.execute(
                select(func.count())
                .select_from(import_row)
                .where(
                    import_row.c.import_upload_id == import_id,
                    import_row.c.status == ImportRowStatus.ERROR.value,
                )
            ).scalar_one()
        )
        if row["is_quarantine_mode"]
        else 0
    )
    request_id = row["approval_request_id"]
    consumed = None
    if request_id is not None:
        # DG-KRN-APR-05 rev 1.51 (D-98 candidate 119; Codex 0216 / 0226): the import's approved
        # basis is consumed EXACTLY ONCE, here — under the authoritative locks (the named contracts'
        # groups, then the contracts; DG-KRN-DB-08), which this transaction then HOLDS to its
        # commit, so `_check_bases` below and every later plan's re-read run under them and no
        # external edit can land between the initial check and a later plan (Codex 0226's interval)
        # — and before any effect, so a stale basis is refused atomically (nothing written). The
        # relationship, with the approved bases, travels with the apply context into the hooks the
        # commit drives (contract activation, BR-DAT-06); activation never re-hashes the import
        # subject, whose heads this very commit moves.
        keys = subjects.import_contract_keys(session, import_id)
        bases = dict(diff.stored_bases(uow, row))  # the approved heads; None = expected absence
        # Integrated batch #5 (main 020e5fd3) return: the rows to lock are EVERY contract the
        # approved basis names — the diff-pinned heads (`stored_bases`) united with the template's
        # keys. Before 04 rev 1.65 `import_contract_keys` named contracts for a contract template
        # only, so a progress commit held no lock and an external append landed inside Codex
        # 0226's interval; since 1.65 the keys cover the contract-event / modification templates
        # too, and the union stays the lock set (the stored bases are the approved heads).
        named_keys = sorted({*keys, *bases})
        named = (
            [
                UUID(str(contract_id))
                for contract_id in session.scalars(
                    select(contract.c.id).where(contract.c.external_id.in_(named_keys))
                )
            ]
            if named_keys
            else []
        )
        locking.lock_groups_then_contracts(session, named)
        consumed = consume_fresh_basis(
            uow,
            UUID(str(request_id)),
            subject_type=ApprovalSubjectType.IMPORT_COMMIT,
            subject_id=import_id,
            keys=keys,
            bases=bases,
        )
    # 05 IPL-10 rev 1.46 (ruling R-29; SC-2): the uploader's scope for the template's write
    # permission is read NOW; an upload naming an entity it no longer covers commits nothing, and
    # the plans run inside that scope
    bounds = scope.uploader_bounds(session, row, str(row["template_code"]), at=uow.now)
    scope.require_covered(scope.committing_entity_ids(row), bounds)
    lineage: list[tuple[UUID, str, UUID]] = []
    with scope.narrowed(uow, bounds.db_scope):
        loaded, affected_groups, monetary_checks = _apply_plans(
            uow, row, template, rows, lineage, bounds, consumed
        )
    source = (row["control_totals"] or {}).get("source") or {}
    totals_loaded: dict[str, Any] = {"rows": loaded, "quarantined": quarantined}
    if monetary_checks:
        totals_loaded["monetary_checks"] = monetary_checks
    if template is not None and template.reconcile_amounts is not None:
        # Only sum cells after the template independently proved their stored monetary facts.
        # IPL-06 is a FILE-COLUMN total: repeated line amounts count once per source row.
        amounts = {
            column.name: sum(
                (
                    Decimal(str(item.normalized[column.name]))
                    for item in rows
                    if item.normalized.get(column.name) is not None
                ),
                Decimal(0),
            )
            for column in template.columns
            if column.type == "amount"
        }
        totals_loaded["amount_sums"] = {key: format(value, "f") for key, value in amounts.items()}
        if amounts != {
            key: Decimal(str(value)) for key, value in (source.get("amount_sums") or {}).items()
        }:
            raise ControlTotalsMismatch(source, totals_loaded)
    if template is not None and loaded + quarantined != int(source.get("rows", 0)):
        raise ControlTotalsMismatch(source, totals_loaded)
    # IPL-11: durable jobs share the import transaction; dispatch happens only after commit.
    # One group per child keeps a failed calculation from blocking unrelated imported groups.
    for group_id in sorted(affected_groups):
        uow.defer(
            JobKind.CONTRACT_COMPUTE,
            {
                "combination_group_ids": [str(group_id)],
                "trigger": ComputationTrigger.COMMAND.value,
                "import_upload_id": str(import_id),
            },
            parent_job_id=parent_job_id,
            subject_type="combination_group",
            subject_id=group_id,
        )
    return _recorded(uow, row, import_id, lineage, loaded, quarantined, totals_loaded)


def _apply_plans(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    template: CsvTemplate | None,
    rows: Sequence[CsvRow],
    lineage: list[tuple[UUID, str, UUID]],
    bounds: scope.Bounds,
    consumed: Any,
) -> tuple[int, set[UUID], list[dict[str, Any]]]:
    """IPL-10: the source records and the plans of a COMMITTING upload, inside the uploader's
    scope (the caller narrowed the transaction). Appends the lineage of every emitted object to
    ``lineage`` and returns the loaded row count, affected groups and read-back amount evidence."""
    session = uow.session
    import_id = UUID(str(row["id"]))
    request_id = row["approval_request_id"]
    _check_bases(uow, row)
    unit = diff.import_unit(uow, row["created_by"], bounds)
    record_ids: dict[UUID, UUID] = {}
    loaded = 0
    applied_rows: set[UUID] = set()
    appended_to: set[UUID] = set()
    monetary_checks: list[dict[str, Any]] = []
    if template is not None:
        for csv_row in rows:
            stored = normalise.store_source_record(
                unit,
                identity=normalise.file_row_identity(
                    source_system=template.source_system,
                    object_type=template.object_type,
                    import_upload_id=import_id,
                    sheet_name=csv_row.sheet_name,
                    row_number=csv_row.row_number,
                ),
                version_order=1,
                payload=csv_row.raw,
                import_upload_id=import_id,
                import_row_id=csv_row.id,
            )
            record_ids[csv_row.id] = stored.id
        context = ApplyContext(
            import_upload_id=import_id,
            file_sha256=str(row["file_sha256"]).strip(),
            template_code=str(row["template_code"]),
            template_version=int(row["template_version"]),
            dry_run=False,
            record_ids=record_ids,
            import_no=str(row["import_no"]),
            original_filename=diff.original_filename(session, row["file_object_id"]),
            parameters=dict(row["parameters"] or {}),
            uploader_id=None if row["created_by"] is None else UUID(str(row["created_by"])),
            approval_request_id=None if request_id is None else UUID(str(request_id)),
            approver_id=_approver(uow, request_id),
            answered_by=_answering_approvers(uow, import_id, request_id),
            consumed=consumed,
        )
        plans = template.plans(rows)
        diff.hold_plan_windows(unit, template, plans)
        for plan in plans:
            applied = template.apply(unit, plan, context=context)
            if template.reconcile_amounts is not None:
                expected, actual = template.reconcile_amounts(
                    unit.session, plan, applied, context=context
                )
                check = {"source": dict(expected), "stored": dict(actual)}
                if expected != actual:
                    raise ControlTotalsMismatch(
                        {
                            **dict((row["control_totals"] or {}).get("source") or {}),
                            "monetary_expected": dict(expected),
                        },
                        {"rows": loaded, "monetary_checks": [*monetary_checks, check]},
                    )
                monetary_checks.append(check)
            appended_to.update(group_id for _, _, group_id, _ in applied.contracts)
            for row_id, targets in applied.row_targets.items():
                if row_id not in record_ids or row_id in applied_rows:
                    raise ControlTotalsMismatch(
                        (row["control_totals"] or {}).get("source") or {},
                        {"rows": loaded, "row_coverage_error": "unknown_or_repeated_row"},
                    )
                applied_rows.add(row_id)
                loaded += 1
                lineage.append((row_id, "source_record", record_ids[row_id]))
                lineage += [(row_id, target_type, target_id) for target_type, target_id in targets]
        # PRD ERR-72 for what the plans recorded and no computation of this commit stored — an
        # import of recorded facts leaves its groups to a later computation, which records
        # nothing and is not judged (supervisor ruling R-122 (j); item PIN-WINDOW-APPENDER-1).
        period_ends.refuse_appends_a_lock_met(unit, appended_to)
    diff.hand_over(unit, uow)
    return loaded, appended_to, monetary_checks


def _recorded(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    import_id: UUID,
    lineage: list[tuple[UUID, str, UUID]],
    loaded: int,
    quarantined: int,
    totals_loaded: Mapping[str, Any],
) -> Committed:
    """IPL-10 to IPL-12 after the plans: lineage, COMMITTED, the audit fact, CTL-001 and CTL-044."""
    session = uow.session
    principal = uow.principal
    request_id = row["approval_request_id"]
    if lineage:
        session.execute(
            insert(import_row_lineage),
            [
                {
                    "tenant_id": principal.tenant_id,
                    "id": new_id(),
                    "import_row_id": row_id,
                    "import_upload_id": import_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "created_at": uow.now,
                    "created_by": principal.id,
                    "created_by_kind": principal.kind.value,
                }
                for row_id, target_type, target_id in lineage
            ],
        )
    apply(
        session,
        OBJECT_TYPE,
        import_id,
        to_status=ImportStatus.COMMITTED.value,
        set_values={
            "committed_at": uow.now,
            "control_totals": {**dict(row["control_totals"] or {}), "loaded": totals_loaded},
            **_stamps(uow),
        },
        expected_status=ImportStatus.COMMITTING.value,
    )
    audit_writer.record_facts(
        uow,
        action=COMMIT_ACTION,
        object_type=OBJECT_TYPE,
        ids=[import_id],
        detail={"rows": loaded, "quarantined": quarantined, "objects": len(lineage)},
    )
    # SOP-1 CTL-001 (uniqueness and idempotency: rejected rows never reach the commit) and CTL-044
    # (the approver is not the uploader; the approval engine enforces it before this point).
    record_execution(
        uow,
        control_id="CTL-001",
        run_ref_type=RunRefType.IMPORT_UPLOAD,
        run_ref_id=import_id,
        population_count=loaded + quarantined,
        exception_count=0,
        result=ControlResult.PASS,
        detail={"rows": loaded, "quarantined": quarantined, "objects": len(lineage)},
    )
    approver_id = _approver(uow, request_id)
    record_execution(
        uow,
        control_id="CTL-044",
        run_ref_type=RunRefType.IMPORT_UPLOAD,
        run_ref_id=import_id,
        population_count=1,
        exception_count=0,
        result=ControlResult.PASS,
        detail={
            "uploader_id": None if row["created_by"] is None else str(row["created_by"]),
            "approver_id": None if approver_id is None else str(approver_id),
        },
    )
    return Committed(rows=loaded, quarantined=quarantined, objects=len(lineage))


def _amounts(totals: Mapping[str, Any]) -> str:
    sums = totals.get("amount_sums") or {}
    return ", ".join(f"{name} {value}" for name, value in sorted(sums.items())) or "no amounts"


def mismatch_message(import_no: str, source: Mapping[str, Any], loaded: Mapping[str, Any]) -> str:
    """PRD IMP-43."""
    detail = (
        "Written amounts do not match the file. "
        if any(check["source"] != check["stored"] for check in loaded.get("monetary_checks", ()))
        else ""
    )
    return (
        f"Control totals do not match for {import_no}: source {source.get('rows', 0)} records, "
        f"{_amounts(source)}; loaded {loaded.get('rows', 0)} records, {_amounts(loaded)}. "
        f"{detail}Nothing was committed."
    )


def _owner(uow: UnitOfWork, row: Mapping[str, Any]) -> UUID | None:
    """[J] L5-1-Q-9: the integration owner of a file import is its uploader's membership."""
    if row["created_by"] is None:
        return None
    found = uow.session.execute(
        select(tenant_membership.c.id).where(
            of_session_tenant(tenant_membership), tenant_membership.c.user_id == row["created_by"]
        )
    ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def fail_commit(
    uow: UnitOfWork,
    import_id: UUID,
    *,
    code: Literal["CONTROL_TOTALS_MISMATCH", "IMPORT_PROCESSING_FAILED"],
    message: str,
    loaded: Mapping[str, Any] | None = None,
) -> UUID | None:
    """COMMITTING → FAILED with one exception item for the integration owner; None when the import
    is not COMMITTING."""
    session = uow.session
    row = _locked(session, import_id)
    if row is None or _status(row) != ImportStatus.COMMITTING.value:
        return None
    values: dict[str, Any] = dict(_stamps(uow))
    if loaded is not None:
        values["control_totals"] = {**dict(row["control_totals"] or {}), "loaded": dict(loaded)}
    apply(
        session,
        OBJECT_TYPE,
        import_id,
        to_status=ImportStatus.FAILED.value,
        set_values=values,
        expected_status=ImportStatus.COMMITTING.value,
    )
    item = raise_exception_item(
        uow,
        source=ExceptionSource.IMPORT,
        code=code,
        severity=severity_of("ERROR"),
        message=message,
        dedupe=f"{ExceptionSource.IMPORT.value}:{code}:{import_id}",
        import_upload_id=import_id,
    )
    owner = _owner(uow, row)
    if owner is not None:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == item.id)
            .values(owner_membership_id=owner, row_version=exception_item.c.row_version + 1)
        )
        notify(
            uow,
            recipient_membership_ids=[owner],
            kind=NotificationKind.EXCEPTION_ASSIGNED,
            title=f"Exception: {code}",
            body=message,
            link_path=subjects.EXCEPTION_LINK.format(item_id=item.id),  # NTF-11 (DIN-11)
            subject_type="exception_item",
            subject_id=item.id,
        )
    uow.audit(
        action=FAIL_ACTION,
        object_type=OBJECT_TYPE,
        object_id=import_id,
        before={"status": ImportStatus.COMMITTING.value},
        after={
            "status": ImportStatus.FAILED.value,
            "code": code,
            "exception_item_id": str(item.id),
        },
    )
    return item.id


def _retryable(error: BaseException) -> bool:
    """Whether the work that met ``error`` may succeed when it is done again (supervisor rulings
    R-105 (2) and R-108 (2); ``db.errors.is_transient``): a database error of a transient class —
    a lock that was not granted, a deadlock, a serialization failure, a cancelled statement,
    resources, a lost connection. Such an error says nothing about the file: the handler stores
    nothing for the upload and lets it through, the attempt fails, and the job is settled by its
    retry policy (dev-guide DG-KRN-JOB-05); the kind's failure hook ends the upload when the job
    ends FAILED."""
    raised = db_errors.database_error_in(error)
    return raised is not None and db_errors.is_transient(raised)


def commit_job_failed(
    uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]
) -> None:
    """The job's failure hook (05 §5.6 rev 1.165 and 1.185; item JOB-FAILED-ITEM-1; supervisor
    rulings R-108 (2) and R-105 (2) and the supervisor's ruling of 2026-10-02; ``job_hooks``). The
    handler ends the upload itself for every error it STORES; this is for the job that ends
    FAILED without the handler's own ending: an attempt that met a transient database error, which
    the handler lets through (``_retryable``); a fault before the import was ``COMMITTING``, which
    stands outside the handler's catch-all; and a worker that died, which the sweeper settles ten
    minutes later. The import it finds ``APPROVED`` or ``COMMITTING`` ends ``FAILED`` with
    ``IMPORT_PROCESSING_FAILED``, as after a stored error: nothing of the commit was kept, the
    uploader is assigned the item and told of it, and the file can be uploaded again. Before,
    an import left ``COMMITTING`` stayed so for good, and so did one left ``APPROVED`` — which
    could be neither cancelled nor submitted again.

    An import in any other status is left alone: the handler ended it, or the commit's
    transaction committed before the worker died. A competing command may hold the upload
    only to refuse it, so settlement waits for that row instead of silently skipping it.
    The job's own work has already ended before this hook runs (05 JOB-06).
    """
    import_id = UUID(str(params["import_upload_id"]))
    found = job_hooks.held_status(
        uow.session, import_id, (ImportStatus.APPROVED, ImportStatus.COMMITTING), wait=True
    )
    if found is None:
        return
    if found == ImportStatus.APPROVED.value:
        start_commit(uow, import_id)
    job_id = str(problem.get("instance") or "").rsplit("/", 1)[-1]
    fail_commit(uow, import_id, code=FAILED_CODE, message=NOT_COMMITTED.format(reference=job_id))


def _commit_after_a_lock(ctx: JobContext, import_id: UUID) -> Committed | None:
    """The commit's transaction — and, when a period lock was decided while it ran, the same
    transaction once more (PRD ERR-72; 05 §5.6 rev 1.195; supervisor rulings R-122 (l) and of
    2026-10-02).

    A commit refused under ``PERIOD_STATE_MOVED`` wrote nothing and left the upload
    ``COMMITTING``. The refusal says what cures it: sent again, the events are recorded after
    the lock. An import has no sender to send it again — its file would be uploaded, validated,
    compared, submitted and approved a second time for a lock that fell into the seconds of its
    commit — so the job runs the transaction once more, stamped after the lock: the import is
    what it would have been had its job started a moment later. Only this rule is run again; a
    second refusal is the commit's failure, told by the rule's sentence."""
    try:
        with ctx.unit_of_work() as uow:
            committed = commit_upload(uow, import_id, parent_job_id=ctx.job_id)
            uow.commit()
        return committed
    except Problem as problem:
        if not is_period_state_moved(problem):
            raise
    with ctx.unit_of_work() as uow:
        committed = commit_upload(uow, import_id, parent_job_id=ctx.job_id)
        uow.commit()
    return committed


def commit_job_cancelled(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    """End an unstarted commit's upload so its source can be uploaded again.

    The caller holds the QUEUED job row: dispatch cannot start it. Cleanup and cancellation
    commit together; a failure of cleanup rolls back the cancellation as well.
    """
    commit_job_failed(uow, params, {"instance": f"/api/v1/jobs/{job_id}"})


@task(
    JobKind.IMPORT_COMMIT,
    retry=COMMIT_RETRY,
    on_failure=commit_job_failed,
    on_cancel=commit_job_cancelled,
    failure_hook_required=True,
)
def import_commit(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``IMPORT_COMMIT`` (05 §5.6 queue ``imports``): commit one approved import."""
    import_id = UUID(str(params["import_upload_id"]))
    href = IMPORT_HREF.format(import_id=import_id)
    with ctx.unit_of_work() as uow:
        started = start_commit(uow, import_id)
        uow.commit()
    if not started:
        return JobOutcome(state="SUCCEEDED", result={"href": href, "counts": {}})
    try:
        committed = _commit_after_a_lock(ctx, import_id)
    except ControlTotalsMismatch as mismatch:
        with ctx.unit_of_work() as uow:
            row = _locked(uow.session, import_id)
            number = "" if row is None else str(row["import_no"])
            fail_commit(
                uow,
                import_id,
                code=MISMATCH_CODE,
                message=mismatch_message(number, mismatch.source, mismatch.loaded),
                loaded=mismatch.loaded,
            )
            uow.commit()
        return JobOutcome(state="SUCCEEDED_WITH_EXCEPTIONS", result={"href": href, "counts": {}})
    except Exception as error:
        if _retryable(error):
            # R-108 (2), R-105 (2): a wait is no finding about the file. The unit of work rolled
            # back; the attempt fails, and ``commit_job_failed`` ends the upload with the job.
            raise
        get_logger(_LOGGER).error(
            "import.commit_failed",
            import_upload_id=str(import_id),
            error_class=type(error).__name__,
        )
        failure = NOT_COMMITTED.format(reference=ctx.job_id)
        if isinstance(error, SourceShredded):
            failure = f"{error} {failure}"
        elif isinstance(error, Problem) and is_period_state_moved(error):
            # The second refusal by a period lock (``_commit_after_a_lock``): told by its rule.
            failure = f"{error.detail} {failure}"
        with ctx.unit_of_work() as uow:
            fail_commit(uow, import_id, code=FAILED_CODE, message=failure)
            uow.commit()
        return JobOutcome(state="SUCCEEDED_WITH_EXCEPTIONS", result={"href": href, "counts": {}})
    counts = (
        {}
        if committed is None
        else {
            "rows": committed.rows,
            "quarantined": committed.quarantined,
            "objects": committed.objects,
        }
    )
    return JobOutcome(state="SUCCEEDED", result={"href": href, "counts": counts})
