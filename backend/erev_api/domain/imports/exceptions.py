"""The shared exception queue (04 T-IMP-05, E-42 to E-44, E-106, E-117, §15.3 API-R-44, §15.4,
§16.14; 05 RCP-20, §3.9; PRD SM-06, BR-DAT-04, ACT-17, ACT-18, §2.5 routing row
``EXCEPTION_WAIVER``, NTF-11; SCREENS §13; 03 REQ-DAT-009, REQ-CLS-013; BUILD_SPEC CTR-5, DIN-11,
BS3-D-02).

``raise_exception_item`` records a finding as an ``exception_item`` in the caller's unit of work:

1. An OPEN or IN_PROGRESS item with the same ``dedupe_key`` (``ux_exception_item__open``) is not
   raised again: its ``occurrence_count`` rises by one and ``last_seen_at`` becomes ``uow.now``
   (AUD-OPS, logged). A concurrent insert of the same key takes the same path through
   ``ON CONFLICT``.
2. Otherwise the item takes the next ``EXCEPTION`` number (``EXC-nnnnnn``), status ``OPEN``, the
   given disposition (``remediable`` by default) and the catalogue title of its code, and the
   creation is audited (AUD-CMD ``exception_item.create``).

``dedupe_key`` is ``<source>:<code>:<subject id or business key>`` (T-IMP-05). The stored severity
is E-43 of the finding severity (``ERROR`` → ``BLOCKING``).

[J] L4-1-Q-2: SCREENS §13.5 fixes the titles of nine codes; the other codes use their PRD IMP
message's first clause, which carries placeholders, so this module titles them from the code words
in sentence case with the known acronyms kept ("SSP key not found") until the catalogue
``finding.<code>.title`` exists. ``erev_api.findings.CODES`` does not exist yet, so a code is
checked against the §15.4 format only (``ck_exception_item__code``).

The queue commands (BUILD_SPEC DIN-11) need ``exception.resolve`` for the item's entity — for an
item that names none, for the entities of everything it is about (``actable``; 04 T-IMP-05 "An
item that names no entity: who reads it, and who acts on it", rev 1.218). No item is
ever deleted (IM-M; REQ-DAT-009 "never disappears"): a cleared item keeps its message, suggestion
and source payload. ``available_actions`` answers 04 §16.14 in E-117 order for an OPEN or
IN_PROGRESS item and a caller who may act on it:

- ``ASSIGN``: always. ``assign`` records the owner membership, moves OPEN to IN_PROGRESS and sends
  NTF-11 ``EXCEPTION_ASSIGNED`` with ``link_path`` ``/data/exceptions/<id>`` (SCREENS SCR-IA-06).
- ``REPROCESS``: a ``remediable`` item this release can reprocess. [J] L6-1-Q-11: only ``ENGINE``
  items naming a combination group; ``request_reprocess`` defers ``CONTRACT_COMPUTE`` for the group
  (202 API-S-Job), and ``settle_reprocess`` resolves the item when the computation SUCCEEDED
  without raising it again ("Input processed", SM-06). A ``SYNC`` item naming a
  ``source_record_id`` is reprocessed by the reprocessor the integrations domain registers in
  ``REPROCESSORS`` at import (04 §16.14 rev 1.81; DIN-12: the stored record is applied again and the
  same item resolved). Reprocessing ``IMPORT``, ``JOURNAL`` and ``MIGRATION`` input needs the re-run
  of that input, which this release does not build.
- ``RESOLVE``: the server finds the condition cleared. [J] L6-1-Q-11: an ``ENGINE`` item whose
  group's head computation succeeded after the item was last seen.
- ``REQUEST_WAIVER``: a ``BLOCKING`` or ``WARNING`` item without a PENDING ``EXCEPTION_WAIVER``
  request, for a caller whose own entities cover those the request names (``asking``; rev 1.218:
  the approvals kernel takes the request from nobody else, R-64 (6)).
  ``request_waiver`` opens the request (comment required); its approval by an
  ``exception.waive`` holder other than the requester and the item owner, with step-up MFA
  (``approvals_approve``), sets ``WAIVED`` and ``waiver_approval_request_id``.
- ``DISMISS``: the item's input was never committed, or the item is ``COMBINATION_SUGGESTED``
  (BR-DAT-04) or ``JOB_FAILED`` (04 §16.14 rev 1.226: the item says that a job failed, and its
  dismissal discards no input). ``dismiss`` sets ``DISMISSED`` with the comment as ``resolution``.

An OPEN or IN_PROGRESS item without ``DISMISS`` has ``dismiss_blocked_reason = 'INPUT_COMMITTED'``.
[J] L6-1-Q-14: input is never committed for an ``IMPORT`` or ``MIGRATION`` item whose upload is not
COMMITTING or COMMITTED, or whose row stayed behind as ``ERROR`` (quarantine mode), and for a
``SYNC`` item that names no contract and no source record linked to a contract. Items of every
other source, and items without an upload, name committed input.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Exists,
    Select,
    Uuid,
    and_,
    case,
    cast,
    column,
    exists,
    false,
    func,
    or_,
    select,
    text,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import ReturningInsert

from erev_api import numbering
from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.auth.permissions import effective_grants
from erev_api.db import new_id
from erev_api.db.tables import (
    approval_request,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_source_link,
    exception_item,
    import_row,
    import_upload,
    integration_connection,
    sync_run,
    tenant_membership,
)
from erev_api.domain.platform import actors
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    ComputationStatus,
    ComputationTrigger,
    ExceptionAction,
    ExceptionDisposition,
    ExceptionSeverity,
    ExceptionSource,
    ExceptionStatus,
    ImportRowStatus,
    ImportStatus,
    JobKind,
    MembershipStatus,
    NotificationKind,
    PrincipalKind,
)
from erev_api.events.notifications import notify
from erev_api.logging import get_logger
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut
from erev_api.schemas.exceptions import ExceptionItemOut, WaiverRequestedOut

if TYPE_CHECKING:
    from erev_api.auth.principal import Principal
    from erev_api.schemas.common import JobOut
    from erev_api.uow import UnitOfWork

__all__ = [
    "INPUT_COMMITTED",
    "JOB_FAILED",
    "OPEN_STATUSES",
    "READ_PERMISSION",
    "RESOLVE_PERMISSION",
    "QueueFacts",
    "RaisedItem",
    "actable",
    "acting",
    "actions_of",
    "asking",
    "assign",
    "available_actions",
    "dedupe_key",
    "dismiss",
    "dismiss_blocked_reason",
    "finding_title",
    "get_item",
    "item_contracts",
    "item_outs",
    "item_select",
    "queue_facts",
    "REPROCESSORS",
    "raise_exception_item",
    "readable",
    "standing_waiver",
    "request_reprocess",
    "request_waiver",
    "resolve",
    "settle_record_reprocess",
    "settle_reprocess",
    "severity_of",
]

SERIES: Final = "EXCEPTION"
OBJECT_TYPE: Final = "exception_item"
# What ``item_contracts`` reads of an item.
_KEY_COLUMNS: Final = (
    exception_item.c.code,
    exception_item.c.contract_id,
    exception_item.c.combination_group_id,
    exception_item.c.source_payload,
)
CREATE_ACTION: Final = "exception_item.create"
CODE_FORMAT: Final = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")  # 04 §15.4 format

# 04 §16.14 rev 1.81 (DIN-12): a remediable item of a non-ENGINE source that names a
# ``source_record_id`` is reprocessed by the reprocessor its source's domain registers here at
# import (the DG-ARC-01 pattern: this module never imports that domain). The reprocessor queues the
# job in the caller's unit of work and answers its API-S-Job. ENGINE keeps CONTRACT_COMPUTE below.
type Reprocessor = Callable[[UnitOfWork, Mapping[str, Any]], JobOut]
REPROCESSORS: Final[dict[ExceptionSource, Reprocessor]] = {}
INPUT_PROCESSED: Final = "Input processed"  # SM-06
OPEN_STATUSES: Final = (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
# The predicate of the partial unique index ``ux_exception_item__open`` (0041), rendered LITERALLY:
# Postgres infers a partial index for ``ON CONFLICT`` only while it can prove the statement's
# predicate implies the index predicate, and a parameterised predicate cannot be proven once the
# prepared statement runs under a generic plan (batch #5 on main 020e5fd3; ``open_item_upsert``).
OPEN_PREDICATE: Final = "status IN (" + ", ".join(f"'{value}'" for value in OPEN_STATUSES) + ")"
TITLE_LIMIT: Final = 200
MESSAGE_LIMIT: Final = 4000
# E-43: finding severity → exception severity.
SEVERITIES: Final[Mapping[str, ExceptionSeverity]] = {
    "ERROR": ExceptionSeverity.BLOCKING,
    "WARNING": ExceptionSeverity.WARNING,
    "INFO": ExceptionSeverity.INFO,
}
# SCREENS §13.5: the catalogue titles fixed for the sample world.
TITLES: Final[Mapping[str, str]] = {
    "PROGRESS_OVER_DELIVERY": "Delivery exceeds the remaining quantity",
    "VC_REASSESSMENT_MISSING": "Variable consideration reassessment missing",
    "PRODUCT_UNMAPPED": "Product without an approved product record",
    "LATE_EVENT": "Event in a closed period",
    "CONTRACT_NOT_FOUND": "Contract not found",
    "TEMPLATE_HEADER_MISMATCH": "File headers do not match the template",
    "ACCOUNT_MAPPING_MISSING": "Account mapping missing",
    "ENGINE_INVARIANT_VIOLATION": "Calculation quarantined",
    "CONTROL_TOTALS_MISMATCH": "Control totals do not match",
}
ACRONYMS: Final = frozenset({"SSP", "VC", "FX", "POB", "EAC", "SFC", "DQ", "AI", "GL", "RPO"})


@dataclass(frozen=True, slots=True)
class RaisedItem:
    """The item a finding names: created now, or an open item seen again (and, when re-evaluated
    at a different effective severity, moved to the current one; D-98 58)."""

    id: UUID
    exception_no: str
    created: bool
    occurrence_count: int
    severity_changed: bool = False
    previous_severity: str | None = None


SEVERITY_ACTION: Final = "exception_item.severity_changed"  # D-98 58 history entry (AUD-CMD)


@dataclass(frozen=True, slots=True)
class SeverityChange:
    """An existing unresolved item re-evaluated at a different effective severity: the auditable
    history entry (from, to, evaluated_at, cause). Status is never part of it (D-98 55, 58)."""

    previous: str
    current: str
    evaluated_at: datetime
    cause: str

    def history_entry(self) -> dict[str, str]:
        return {
            "from": self.previous,
            "to": self.current,
            "evaluated_at": self.evaluated_at.isoformat(),
            "cause": self.cause,
        }


def severity_change(
    stored: ExceptionSeverity | str, current: ExceptionSeverity, *, at: datetime, cause: str
) -> SeverityChange | None:
    """The change an existing item takes when its finding's effective severity differs from the
    stored one (an escalation or a lowering alike); None when equal. ``ValueError`` for a stored
    literal outside E-43."""
    previous = ExceptionSeverity(str(getattr(stored, "value", stored)))
    if previous is ExceptionSeverity(current):
        return None
    return SeverityChange(
        previous=previous.value,
        current=ExceptionSeverity(current).value,
        evaluated_at=at,
        cause=cause,
    )


def dedupe_key(source: ExceptionSource, code: str, subject: object) -> str:
    """T-IMP-05 ``<source>:<code>:<subject id or business key>``."""
    return f"{source.value}:{code}:{subject}"


def severity_of(finding_severity: str) -> ExceptionSeverity:
    """E-43 of a §15.4 finding severity."""
    found = SEVERITIES.get(finding_severity)
    if found is None:
        raise ValueError(f"unknown finding severity {finding_severity!r}")
    return found


def finding_title(code: str) -> str:
    """The catalogue title of a code (L4-1-Q-2)."""
    fixed = TITLES.get(code)
    if fixed is not None:
        return fixed
    words = [word if word in ACRONYMS else word.lower() for word in code.split("_")]
    first = words[0]
    words[0] = first if first in ACRONYMS else first.capitalize()
    return " ".join(words)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def item_contracts(session: Session, row: Mapping[str, Any]) -> list[UUID]:
    """The contracts an audit event of an item names (04 T-PLT-19 ``detail.contract_id`` /
    ``detail.contract_ids``, rev 1.154): the contract the item is about; for a combination
    suggestion the contracts it would combine, which its payload names; for an item about a group
    and no one contract (a refused computation of several members) the group's members as the
    event is written. An item about none of them names none. ``row`` carries ``code``,
    ``contract_id``, ``combination_group_id`` and ``source_payload``."""
    stated = _stated_contracts(row)
    if stated is not None:
        return stated
    group_id = _uuid(row["combination_group_id"])
    return _group_members(session, [group_id])[group_id]


def _stated_contracts(row: Mapping[str, Any]) -> list[UUID] | None:
    """The contracts the row of an item states itself (``item_contracts``): those the payload of
    a combination suggestion names, else the contract it names, none for an item that names
    neither a contract nor a group. None for an item about a group and no one contract — its
    contracts are the group's members (``_group_members``)."""
    if str(row["code"]) == SUGGESTED:
        named = (row["source_payload"] or {}).get("contract_ids") or ()
        if named:
            return [_uuid(value) for value in named]
    if row["contract_id"] is not None:
        return [_uuid(row["contract_id"])]
    if row["combination_group_id"] is None:
        return []
    return None


def _group_members(session: Session, group_ids: Sequence[UUID]) -> dict[UUID, list[UUID]]:
    """The current member contracts of each group of ``group_ids`` (T-CON-04, the open
    memberships), in one statement."""
    members: dict[UUID, list[UUID]] = {group_id: [] for group_id in group_ids}
    if not members:
        return members
    member = combination_group_member.c
    for group_id, contract_id in session.execute(
        select(member.combination_group_id, member.contract_id).where(
            member.combination_group_id.in_(sorted(members, key=str)),
            member.valid_to_known_at.is_(None),
        )
    ):
        members[_uuid(group_id)].append(_uuid(contract_id))
    return members


def _key_members(row: Any) -> dict[str, Any]:
    """``_KEY_COLUMNS`` of a result row, by name."""
    return {column.name: getattr(row, column.name) for column in _KEY_COLUMNS}


def _record_severity_change(
    uow: UnitOfWork,
    item_id: UUID,
    change: SeverityChange,
    *,
    version: int,
    contract_ids: Sequence[UUID],
) -> None:
    """The D-98 58 history entry as an audit event: the actual prior and current severities, the
    evaluation instant and cause, and the row version the change was written at."""
    uow.audit(
        action=SEVERITY_ACTION,
        object_type=OBJECT_TYPE,
        object_id=item_id,
        object_version=str(version),
        before={"severity": change.previous},
        after={"severity": change.current, **change.history_entry()},
        contract_ids=contract_ids,
    )


def _reconcile_winner(
    uow: UnitOfWork,
    row: Any,
    *,
    severity: ExceptionSeverity,
    severity_cause: str | None,
) -> SeverityChange | None:
    """D-98 69: the row the insert's ``ON CONFLICT`` landed on (a concurrent first creation the
    existing-item read did not see) takes the current effective severity in the same transaction
    when it differs — one UPDATE keyed on the row version the upsert returned, one history event
    with the actual prior and current severities; scope and status untouched, no second occurrence
    increment. None when the severities agree."""
    change = severity_change(
        row.severity, severity, at=uow.now, cause=severity_cause or "re-evaluation"
    )
    if change is None:
        return None
    principal = uow.principal
    written = uow.session.execute(
        update(exception_item)
        .where(
            exception_item.c.tenant_id == principal.tenant_id,
            exception_item.c.id == row.id,
            exception_item.c.row_version == int(row.row_version),
        )
        .values(
            severity=change.current,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=exception_item.c.row_version + 1,
        )
        .returning(exception_item.c.row_version, *_KEY_COLUMNS)
    ).one()
    _record_severity_change(
        uow,
        UUID(str(row.id)),
        change,
        version=int(written.row_version),
        contract_ids=item_contracts(uow.session, _key_members(written)),
    )
    return change


def _seen_again(
    uow: UnitOfWork,
    key: str,
    *,
    severity: ExceptionSeverity | None = None,
    severity_cause: str | None = None,
) -> RaisedItem | None:
    """Count an open item again; with ``severity``, move it to the current effective severity when
    that differs, writing the D-98 58 history entry as an audit event. Scope columns (entity,
    period, contract) are never touched (D-98 57)."""
    session = uow.session
    row = session.execute(
        select(
            exception_item.c.id,
            exception_item.c.exception_no,
            exception_item.c.severity,
            *_KEY_COLUMNS,
        )
        .where(exception_item.c.dedupe_key == key, exception_item.c.status.in_(OPEN_STATUSES))
        .with_for_update()
    ).one_or_none()
    if row is None:
        return None
    principal = uow.principal
    change = (
        None
        if severity is None
        else severity_change(
            row.severity, severity, at=uow.now, cause=severity_cause or "re-evaluation"
        )
    )
    values: dict[str, Any] = {
        "occurrence_count": exception_item.c.occurrence_count + 1,
        "last_seen_at": uow.now,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
        "row_version": exception_item.c.row_version + 1,
    }
    if change is not None:
        values["severity"] = change.current
    count, version = session.execute(
        update(exception_item)
        .where(exception_item.c.tenant_id == principal.tenant_id, exception_item.c.id == row.id)
        .values(**values)
        .returning(exception_item.c.occurrence_count, exception_item.c.row_version)
    ).one()
    if change is not None:
        _record_severity_change(
            uow,
            UUID(str(row.id)),
            change,
            version=int(version),
            contract_ids=item_contracts(session, _key_members(row)),
        )
    get_logger(__name__).info(
        "exception_item.seen_again",
        exception_item_id=str(row.id),
        dedupe_key=key,
        occurrence_count=int(count),
    )
    return RaisedItem(
        id=UUID(str(row.id)),
        exception_no=str(row.exception_no),
        created=False,
        occurrence_count=int(count),
        severity_changed=change is not None,
        previous_severity=None if change is None else change.previous,
    )


def standing_waiver(
    uow: UnitOfWork, key: str, *, code: str, severity: ExceptionSeverity, message: str
) -> UUID | None:
    """The item whose approved waiver still covers a finding evaluated again, or None (04 T-IMP-05
    rev 1.106; supervisor ruling R-62 (c), item DQ-WAIVER-STICKY-1).

    A finding stands waived when its ``dedupe_key`` has no OPEN or IN_PROGRESS item, the latest
    item of the key is WAIVED under an APPROVED ``EXCEPTION_WAIVER`` request, and the finding's
    code, severity and message equal that item's — the facts the approver decided on have not
    changed. The item's ``last_seen_at`` moves (AUD-OPS: no audit event) and the caller raises
    nothing. A finding that differs in severity or message is not covered and is raised as a new
    OPEN item; so is a finding whose latest item is RESOLVED or DISMISSED (the resolution claimed
    the condition was gone). The key of a data-quality finding carries entity and period, so a
    waiver never reaches another period."""
    session = uow.session
    rows = session.execute(
        select(
            exception_item.c.id,
            exception_item.c.status,
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.message,
            exception_item.c.waiver_approval_request_id,
        )
        .where(exception_item.c.dedupe_key == key)
        .order_by(exception_item.c.created_at.desc(), exception_item.c.exception_no.desc())
    ).all()
    if not rows or any(_value(row.status) in OPEN_STATUSES for row in rows):
        return None
    latest = rows[0]
    if (
        _value(latest.status) != ExceptionStatus.WAIVED.value
        or latest.waiver_approval_request_id is None
    ):
        return None
    current = (code, ExceptionSeverity(severity).value, _clip(message, MESSAGE_LIMIT))
    if (str(latest.code), _value(latest.severity), str(latest.message)) != current:
        return None
    approved = session.execute(
        select(approval_request.c.id).where(
            approval_request.c.id == latest.waiver_approval_request_id,
            approval_request.c.subject_type == ApprovalSubjectType.EXCEPTION_WAIVER.value,
            approval_request.c.status == ApprovalRequestStatus.APPROVED.value,
        )
    ).scalar_one_or_none()
    if approved is None:
        return None
    principal = uow.principal
    item_id = _uuid(latest.id)
    session.execute(
        update(exception_item)
        .where(exception_item.c.tenant_id == principal.tenant_id, exception_item.c.id == item_id)
        .values(
            last_seen_at=uow.now,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=exception_item.c.row_version + 1,
        )
    )
    get_logger(__name__).info(
        "exception_item.seen_under_waiver", exception_item_id=str(item_id), dedupe_key=key
    )
    return item_id


def open_item_upsert(values: Mapping[str, Any], now: datetime) -> ReturningInsert[Any]:
    """``INSERT … ON CONFLICT (tenant_id, dedupe_key) WHERE <OPEN_PREDICATE> DO UPDATE`` of one
    exception item: a new row, or one more occurrence of the open item with the same dedupe key.
    The inference predicate is the literal ``OPEN_PREDICATE`` — the index
    ``ux_exception_item__open`` is inferred whatever the plan mode (module constant; the CPU witness
    ``tests/unit/imports/test_exception_upsert.py`` pins the compiled clause)."""
    return (
        insert(exception_item)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[exception_item.c.tenant_id, exception_item.c.dedupe_key],
            index_where=text(OPEN_PREDICATE),
            set_={
                "occurrence_count": exception_item.c.occurrence_count + 1,
                "last_seen_at": now,
                "updated_at": now,
                "row_version": exception_item.c.row_version + 1,
            },
        )
        .returning(
            exception_item.c.id,
            exception_item.c.exception_no,
            exception_item.c.occurrence_count,
            exception_item.c.severity,
            exception_item.c.row_version,
        )
    )


def raise_exception_item(
    uow: UnitOfWork,
    *,
    source: ExceptionSource,
    code: str,
    severity: ExceptionSeverity,
    message: str,
    dedupe: str,
    title: str | None = None,
    suggestion: str | None = None,
    field: str | None = None,
    business_key: str | None = None,
    source_payload: Mapping[str, Any] | None = None,
    import_upload_id: UUID | None = None,
    import_row_id: UUID | None = None,
    sync_run_id: UUID | None = None,
    source_record_id: UUID | None = None,
    contract_id: UUID | None = None,
    obligation_id: UUID | None = None,
    combination_group_id: UUID | None = None,
    entity_id: UUID | None = None,
    period_id: UUID | None = None,
    close_run_id: UUID | None = None,
    priority: int = 3,
    disposition: ExceptionDisposition = ExceptionDisposition.REMEDIABLE,
    severity_cause: str | None = None,
) -> RaisedItem:
    """Record one finding in the exception queue, or count it again while its item is open; an
    open item re-evaluated at a different effective severity takes the current one with an audited
    history entry (D-98 58; ``severity_cause`` names the rule or override behind it). When the
    existing-item read sees no open row but the insert's ``ON CONFLICT`` lands on one, that winner
    is reconciled the same way in this transaction (D-98 69) — never left for a later run."""
    if CODE_FORMAT.fullmatch(code) is None:
        raise ValueError(f"{code!r} is not a §15.4 code")
    if not 1 <= priority <= 5:
        raise ValueError("priority is 1 to 5 (T-IMP-05)")
    again = _seen_again(uow, dedupe, severity=severity, severity_cause=severity_cause)
    if again is not None:
        return again
    principal = uow.principal
    item_id = new_id()
    number = numbering.next_number(uow, SERIES)
    values: dict[str, Any] = {
        "tenant_id": principal.tenant_id,
        "id": item_id,
        "exception_no": number,
        "source": source.value,
        "code": code,
        "severity": severity.value,
        "disposition": ExceptionDisposition(disposition).value,
        "status": ExceptionStatus.OPEN.value,
        "priority": priority,
        "title": _clip(title or finding_title(code), TITLE_LIMIT),
        "message": _clip(message, MESSAGE_LIMIT),
        "suggestion": suggestion,
        "field": field,
        "business_key": business_key,
        "source_payload": None if source_payload is None else dict(source_payload),
        "import_upload_id": import_upload_id,
        "import_row_id": import_row_id,
        "sync_run_id": sync_run_id,
        "source_record_id": source_record_id,
        "contract_id": contract_id,
        "obligation_id": obligation_id,
        "combination_group_id": combination_group_id,
        "entity_id": entity_id,
        "period_id": period_id,
        "dedupe_key": dedupe,
        "occurrence_count": 1,
        "last_seen_at": uow.now,
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    if close_run_id is not None:
        values["close_run_id"] = close_run_id  # T-IMP-05: the close run a CLOSE item belongs to
    row = uow.session.execute(open_item_upsert(values, uow.now)).one()
    created = UUID(str(row.id)) == item_id
    change = (
        None
        if created
        else _reconcile_winner(uow, row, severity=severity, severity_cause=severity_cause)
    )
    if created:
        uow.audit(
            action=CREATE_ACTION,
            object_type=OBJECT_TYPE,
            object_id=item_id,
            object_version="1",
            after={
                "exception_no": number,
                "source": source.value,
                "code": code,
                "severity": severity.value,
                "status": ExceptionStatus.OPEN.value,
                "dedupe_key": dedupe,
            },
            contract_ids=item_contracts(uow.session, values),
        )
    return RaisedItem(
        id=UUID(str(row.id)),
        exception_no=str(row.exception_no),
        created=created,
        occurrence_count=int(row.occurrence_count),
        severity_changed=change is not None,
        previous_severity=None if change is None else change.previous,
    )


# --- the queue (BUILD_SPEC DIN-11) ----------------------------------------------------------------

READ_PERMISSION: Final = "contract.read"  # the guard of the queue's reads (04 API-R-44)
RESOLVE_PERMISSION: Final = "exception.resolve"  # PRD ACT-17
GROUP_OBJECT: Final = "combination_group"
ASSIGN_ACTION: Final = "exception_item.assign"
RESOLVE_ACTION: Final = "exception_item.resolve"
DISMISS_ACTION: Final = "exception_item.dismiss"
WAIVE_ACTION: Final = "exception_item.waive"
REPROCESS_ACTION: Final = "exception_item.reprocess"
REPROCESSED_ACTION: Final = "exception_item.reprocessed"
INPUT_COMMITTED: Final = "INPUT_COMMITTED"  # 04 §16.14 ``dismiss_blocked_reason``
SUGGESTED: Final = "COMBINATION_SUGGESTED"
# 04 §15.4 rev 1.226 (item JOB-FAILED-ITEM-1): the INFO item of a failed job, raised and settled
# through ``domain.imports.job_items``.
JOB_FAILED: Final = "JOB_FAILED"
# 04 §16.14: the codes a person may dismiss whatever became of the item's input.
DISMISSABLE_CODES: Final = frozenset({SUGGESTED, JOB_FAILED})
RULE_ACTION: Final = "E-117"
RULE_OWNER: Final = "T-IMP-05"
DISMISS_SOURCES: Final = frozenset(
    {ExceptionSource.IMPORT.value, ExceptionSource.SYNC.value, ExceptionSource.MIGRATION.value}
)
UPLOAD_SOURCES: Final = frozenset({ExceptionSource.IMPORT.value, ExceptionSource.MIGRATION.value})
WAIVABLE: Final = frozenset({ExceptionSeverity.BLOCKING.value, ExceptionSeverity.WARNING.value})
COMMITTED_UPLOADS: Final = (ImportStatus.COMMITTING.value, ImportStatus.COMMITTED.value)
# SCREENS §13.7 copy keys.
ACTION_LABELS: Final[Mapping[ExceptionAction, str]] = {
    ExceptionAction.ASSIGN: "Assign",
    ExceptionAction.REPROCESS: "Reprocess",
    ExceptionAction.RESOLVE: "Mark resolved",
    ExceptionAction.REQUEST_WAIVER: "Request waiver",
    ExceptionAction.DISMISS: "Dismiss exception",
}
DISMISS_BLOCKED: Final = (
    "Dismissal applies only to input that was never committed. Request a waiver instead."
)
NOT_AVAILABLE: Final = "{action} is not available for this exception."
OWNER_UNKNOWN: Final = "Choose an active member of this workspace."
# [J] Copy of the refusal of 04 API-R-44 rev 1.218 (``assign``), which the documents word here
# first: the owner is told of the item and opens it from that message.
OWNER_CANNOT_READ: Final = "This member cannot open the exception. Choose an owner who can read it."
REPROCESSED: Final = "Reprocessed. Computation {computation} succeeded without {code}."
# ``exception_item`` columns the API-S schema does not show.
# The ``actors.named`` and ``actors.member`` values ``item_select`` reads with each row (dev-guide
# DG-API-11).
RESOLVED_BY_NAMED: Final = "resolved_by__named"
OWNER_NAMED: Final = "owner__named"
# The member ``item_select`` reads with each row under its own name (04 §16.14, rev 1.206).
GROUP_CODE: Final = "combination_group_code"
_HIDDEN: Final = frozenset(
    {
        "tenant_id",
        "created_by",
        "created_by_kind",
        "updated_by",
        "updated_by_kind",
        # shown as the API-S-Actor ``resolved_by`` (04 §16.14, rev 1.139)
        "resolved_by_kind",
        RESOLVED_BY_NAMED,
        # shown as the API-S-Actor ``owner`` beside ``owner_membership_id``
        OWNER_NAMED,
    }
)


def item_select() -> Select[Any]:
    """The T-IMP-05 rows ``item_outs`` takes: every column, with who resolved each item, who owns
    it and the code of the contract group it names read in the same statement. The code is one
    lookup on the group's primary key, null for an item that names no group (04 §16.14, rev 1.206;
    item CLO-QUARANTINE-READ-1): the item of a group of several contracts names no contract, and
    the group's code is what a screen shows in its place."""
    tenant_id = exception_item.c.tenant_id
    group_code = (
        select(combination_group.c.code)
        .where(
            combination_group.c.tenant_id == tenant_id,
            combination_group.c.id == exception_item.c.combination_group_id,
        )
        .scalar_subquery()
    )
    return select(
        exception_item,
        actors.named(exception_item.c.resolved_by, tenant_id=tenant_id).label(RESOLVED_BY_NAMED),
        actors.member(exception_item.c.owner_membership_id, tenant_id=tenant_id).label(OWNER_NAMED),
        group_code.label(GROUP_CODE),
    )


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


@dataclass(frozen=True, slots=True)
class QueueFacts:
    """What the actions of a page of items depend on, read once for the page."""

    committed_uploads: frozenset[UUID]
    error_rows: frozenset[UUID]
    linked_records: frozenset[UUID]
    pending_waivers: frozenset[UUID]
    head_computed_at: Mapping[UUID, datetime]


def _ids(rows: Sequence[Mapping[str, Any]], column: str) -> list[UUID]:
    return sorted({_uuid(row[column]) for row in rows if row[column] is not None})


def queue_facts(session: Session, rows: Sequence[Mapping[str, Any]]) -> QueueFacts:
    """The uploads, rows, source links, pending waivers and head computations the items name."""

    def found(statement: Any, wanted: Sequence[UUID]) -> frozenset[UUID]:
        if not wanted:
            return frozenset()
        return frozenset(_uuid(value) for value in session.scalars(statement))

    uploads = _ids(rows, "import_upload_id")
    import_rows = _ids(rows, "import_row_id")
    records = _ids(rows, "source_record_id")
    items = _ids(rows, "id")
    groups = sorted(
        {
            _uuid(row["combination_group_id"])
            for row in rows
            if row["combination_group_id"] is not None
            and _value(row["source"]) == ExceptionSource.ENGINE.value
        }
    )
    heads: dict[UUID, datetime] = {}
    if groups:
        statement = (
            select(combination_group.c.id, contract_computation.c.created_at)
            .join(
                contract_computation,
                contract_computation.c.id == combination_group.c.head_computation_id,
            )
            .where(
                combination_group.c.id.in_(groups),
                contract_computation.c.status == ComputationStatus.SUCCEEDED.value,
            )
        )
        heads = {_uuid(row.id): row.created_at for row in session.execute(statement)}
    return QueueFacts(
        committed_uploads=found(
            select(import_upload.c.id).where(
                import_upload.c.id.in_(uploads), import_upload.c.status.in_(COMMITTED_UPLOADS)
            ),
            uploads,
        ),
        error_rows=found(
            select(import_row.c.id).where(
                import_row.c.id.in_(import_rows),
                import_row.c.status == ImportRowStatus.ERROR.value,
            ),
            import_rows,
        ),
        linked_records=found(
            select(contract_source_link.c.source_record_id).where(
                contract_source_link.c.source_record_id.in_(records)
            ),
            records,
        ),
        pending_waivers=found(
            select(approval_request.c.subject_id).where(
                approval_request.c.subject_type == ApprovalSubjectType.EXCEPTION_WAIVER.value,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                approval_request.c.subject_id.in_(items),
            ),
            items,
        ),
        head_computed_at=heads,
    )


def _input_committed(row: Mapping[str, Any], facts: QueueFacts) -> bool:
    """[J] L6-1-Q-14 (module docstring)."""
    source = _value(row["source"])
    if source not in DISMISS_SOURCES:
        return True
    if source == ExceptionSource.SYNC.value:
        record = row["source_record_id"]
        return row["contract_id"] is not None or (
            record is not None and _uuid(record) in facts.linked_records
        )
    upload = row["import_upload_id"]
    if upload is None:
        return True
    if _uuid(upload) not in facts.committed_uploads:
        return False
    import_row_id = row["import_row_id"]
    return import_row_id is None or _uuid(import_row_id) not in facts.error_rows


# --- who reads an item, and who acts on it --------------------------------------------------------
#
# 04 T-IMP-05 "An item that names no entity: who reads it" (rev 1.218; item EXC-IMPORT-SCOPE-1;
# the supervisor's rulings of 2026-10-01). An item that names an entity is the row policy's. An
# item that names none passes the policy for every member, and was read and acted on by every
# member: the finding of an import the member could not open, the quarantine of a group that
# holds a contract of another entity (its message names every member contract), a suggestion
# to combine a contract with another entity's. Such an item is read by whoever may read
# EVERYTHING it is about (``readable``) and acted on by whoever holds ``exception.resolve``
# for the same (``actable``): one rule, asked of two permissions.
#
# Predicates of API-R-44 and not a row policy: the rule asks one permission for EVERY entity an
# item is about, or being the uploader of its import, which a policy — it knows the session's
# union of roles and no permission — cannot state; and a count reads the row whoever the caller
# is (``close.gates``), so a member may be told a count that includes an item he is not shown.


def _contract_within(scope: frozenset[UUID], contract_id: Any, tenant_id: UUID) -> Exists:
    """A contract the session reads whose contracting entity ``scope`` names. T-CON-01 is bound
    to its entity by the row policy: a contract outside the session's scope is no row here, so
    "unknown" and "of another entity" are one answer."""
    return exists().where(
        contract.c.tenant_id == tenant_id,
        contract.c.id == contract_id,
        contract.c.contracting_entity_id.in_(sorted(scope, key=str)),
    )


def _suggested_within(scope: frozenset[UUID], tenant_id: UUID) -> ColumnElement[bool]:
    """Every contract a combination suggestion names in its payload (``contract_ids``) is one
    ``_contract_within`` admits. The ids are unnested as uuids, so each is one lookup of T-CON-01
    by its key; a payload without the list names none."""
    ids = exception_item.c.source_payload["contract_ids"]
    listed = case((func.jsonb_typeof(ids) == "array", ids), else_=func.jsonb_build_array())
    element = func.jsonb_array_elements_text(listed).column_valued("value")
    named = (
        func.unnest(select(func.array_agg(cast(element, Uuid()))).scalar_subquery())
        .table_valued(column("id", Uuid()), name="suggested_contract")
        .render_derived()
    )
    unread = ~_contract_within(scope, named.c.id, tenant_id).correlate(named)
    return ~exists().select_from(named).where(unread)


def _members_within(scope: frozenset[UUID], tenant_id: UUID) -> ColumnElement[bool]:
    """Every current member of the group the item names is a contract ``_contract_within``
    admits. Memberships are read from T-CON-04, which no entity scope hides, as the approvals
    kernel reads the members of a group (``subjects.contract_group_entities``). A group that no
    membership names passes for nobody: what cannot be named is not shown."""
    item, member = exception_item.c, combination_group_member.c
    current = and_(
        member.tenant_id == item.tenant_id,
        member.combination_group_id == item.combination_group_id,
        member.valid_to_known_at.is_(None),
    )
    return and_(
        exists().where(current),
        ~exists().where(current, ~_contract_within(scope, member.contract_id, tenant_id)),
    )


def _connection_within(scope: frozenset[UUID]) -> ColumnElement[bool]:
    """Every entity the connection of the item's sync run serves is in ``scope`` (T-INT-01
    ``entity_ids``). A connection that names no entity serves every entity of the workspace, which
    no set of named entities covers."""
    item, served = exception_item.c, integration_connection.c.entity_ids
    return exists().where(
        sync_run.c.tenant_id == item.tenant_id,
        sync_run.c.id == item.sync_run_id,
        integration_connection.c.tenant_id == sync_run.c.tenant_id,
        integration_connection.c.id == sync_run.c.integration_connection_id,
        func.cardinality(served) > 0,
        served.contained_by(sorted(scope, key=str)),
    )


def _about_within(
    scope: frozenset[UUID], tenant_id: UUID, upload: ColumnElement[bool]
) -> ColumnElement[bool]:
    """Everything an item that names no entity is about lies within ``scope``, each clause that
    applies: its import, by ``upload`` — a condition on the T-IMP-02 row the item names; the
    connection of its sync run; the contract it names; each contract a combination suggestion
    names; and, for an item that names a group and no contract, every member of that group. An
    item about none of them — a finding about the workspace — passes."""
    item = exception_item.c
    of_upload = exists().where(
        import_upload.c.tenant_id == item.tenant_id,
        import_upload.c.id == item.import_upload_id,
        upload,
    )
    return and_(
        or_(item.import_upload_id.is_(None), of_upload),
        or_(item.sync_run_id.is_(None), _connection_within(scope)),
        or_(item.contract_id.is_(None), _contract_within(scope, item.contract_id, tenant_id)),
        or_(item.code != SUGGESTED, _suggested_within(scope, tenant_id)),
        or_(
            item.contract_id.is_not(None),
            item.combination_group_id.is_(None),
            _members_within(scope, tenant_id),
        ),
    )


def readable(principal: Principal) -> ColumnElement[bool]:
    """The exception items ``principal`` lists and reads, as a condition on ``exception_item``
    beside the table's row policy (04 T-IMP-05 "An item that names no entity: who reads it", rev
    1.218; item EXC-IMPORT-SCOPE-1). An item that names an entity is the policy's. An item that
    names none is read by a member whose ``contract.read`` covers everything the item is about
    (``_about_within``): the entity of the contract it names, of each contract a combination
    suggestion names and of every member of the group it names; every entity the connection of
    its sync run serves — all entities for a connection that names none; and its import is one
    the member reads (API-R-43, ``imports.scope.visible``) — its uploader, or a holder for every
    entity the upload names: every holder for a tenant-level upload, a holder for all entities
    for an unresolved one. An item that is about none of these is about the workspace and is
    every holder's, as before."""
    scope = principal.permission_scopes.get(READ_PERMISSION)
    if scope == "*":
        return true()
    # imported here: the templates the scope module loads raise items through this module
    from erev_api.domain.imports import scope as import_scope

    held = frozenset() if scope is None else scope
    about = _about_within(held, principal.tenant_id, import_scope.visible(principal))
    return or_(exception_item.c.entity_id.is_not(None), about)


def actable(principal: Principal) -> ColumnElement[bool]:
    """The exception items ``principal`` holds ``exception.resolve`` for (PRD ACT-17; 04 API-R-44
    rev 1.218): the item's entity; for an item that names none, the entities of everything it is
    about (``_about_within``) — every entity its upload names, and every entity of the workspace
    for an upload that names none or is not resolved. Reading follows the import's readers, its
    uploader among them; acting asks the permission for the same set and knows no uploader. An
    item about no import, sync run, contract or group is acted on by a holder for any entity, as
    before — its waiver apart, which spans every entity (``asking``). Until this item an item
    without an entity was acted on by a holder for ANY entity."""
    scope = principal.permission_scopes.get(RESOLVE_PERMISSION)
    if scope is None:
        return false()
    if scope == "*":
        return true()
    item, names = exception_item.c, import_upload.c.named_entity_ids
    entities = sorted(scope, key=str)
    named_within = and_(func.cardinality(names) > 0, names.contained_by(entities))
    return or_(
        item.entity_id.in_(entities),
        and_(item.entity_id.is_(None), _about_within(scope, principal.tenant_id, named_within)),
    )


def acting(
    session: Session, principal: Principal, rows: Sequence[Mapping[str, Any]]
) -> frozenset[UUID]:
    """The items of ``rows`` the principal may act on — those it reads and holds
    ``exception.resolve`` for (``readable``, ``actable``) — in one statement for a page."""
    ids = _ids(rows, "id")
    if not ids or principal.permission_scopes.get(RESOLVE_PERMISSION) is None:
        return frozenset()
    statement = select(exception_item.c.id).where(
        exception_item.c.id.in_(ids), readable(principal), actable(principal)
    )
    return frozenset(_uuid(value) for value in session.scalars(statement))


def _reprocessable(row: Mapping[str, Any]) -> bool:
    """[J] L6-1-Q-11: a remediable ENGINE item naming a combination group; 04 §16.14 rev 1.81: a
    remediable item of a source with a registered reprocessor that names its source record."""
    if _value(row["disposition"]) != ExceptionDisposition.REMEDIABLE.value:
        return False
    source = _value(row["source"])
    if source == ExceptionSource.ENGINE.value:
        return row["combination_group_id"] is not None
    return ExceptionSource(source) in REPROCESSORS and row["source_record_id"] is not None


def _cleared(row: Mapping[str, Any], facts: QueueFacts) -> bool:
    """[J] L6-1-Q-11: the group's head computation succeeded after the item was last seen."""
    if _value(row["source"]) != ExceptionSource.ENGINE.value or row["combination_group_id"] is None:
        return False
    computed_at = facts.head_computed_at.get(_uuid(row["combination_group_id"]))
    return computed_at is not None and computed_at > row["last_seen_at"]


def asking(
    session: Session,
    principal: Principal,
    rows: Sequence[Mapping[str, Any]],
    allowed: frozenset[UUID],
) -> frozenset[UUID]:
    """The items of ``allowed`` — those the principal acts on (``acting``) — whose waiver it may
    ask (04 §16.14 ``REQUEST_WAIVER``, rev 1.218): the approvals kernel takes a request from a
    preparer who reads in full what the request names (``engine.own_scope_covers``; supervisor
    ruling R-64 (6); 04 §16.10 rev 1.319: the waiver's read permission for every entity, where
    it was the entities of the member's roles), and a waiver names the entities whose close its
    item holds (``waiver_entities_of``). A member who acts on an item covers everything it is
    about. An item about the workspace is acted on by a holder for any entity and its waiver
    spans every entity: it is asked by a member who reads all entities alone, and offered to
    nobody else. Read for a page in a bounded number of statements, none for a member who reads
    every entity."""
    waiver = ApprovalSubjectType.EXCEPTION_WAIVER
    if not allowed or approvals.own_scope_covers(principal, waiver, subjects.ALL_ENTITIES):
        return allowed
    named = waiver_entities_of(session, [row for row in rows if _uuid(row["id"]) in allowed])
    return frozenset(
        item_id
        for item_id, entities in named.items()
        if approvals.own_scope_covers(principal, waiver, entities)
    )


def actions_of(
    row: Mapping[str, Any], facts: QueueFacts, *, may_act: bool, may_ask_waiver: bool
) -> tuple[tuple[ExceptionAction, ...], str | None]:
    """04 §16.14 ``available_actions`` and ``dismiss_blocked_reason`` of one item; ``may_act``
    says whether the caller may act on it at all (``acting``), ``may_ask_waiver`` whether the
    approvals kernel would take its waiver from the caller (``asking``)."""
    if _value(row["status"]) not in OPEN_STATUSES:
        return (), None
    dismissable = str(row["code"]) in DISMISSABLE_CODES or not _input_committed(row, facts)
    blocked = None if dismissable else INPUT_COMMITTED
    if not may_act:
        return (), blocked
    found = [ExceptionAction.ASSIGN]
    if _reprocessable(row):
        found.append(ExceptionAction.REPROCESS)
    if _cleared(row, facts):
        found.append(ExceptionAction.RESOLVE)
    if (
        may_ask_waiver
        and _value(row["severity"]) in WAIVABLE
        and _uuid(row["id"]) not in facts.pending_waivers
    ):
        found.append(ExceptionAction.REQUEST_WAIVER)
    if dismissable:
        found.append(ExceptionAction.DISMISS)
    return tuple(found), blocked


def available_actions(
    session: Session, row: Mapping[str, Any], principal: Principal
) -> tuple[ExceptionAction, ...]:
    """04 §16.14 ``available_actions`` of one item for ``principal``."""
    allowed = acting(session, principal, [row])
    item_id = _uuid(row["id"])
    return actions_of(
        row,
        queue_facts(session, [row]),
        may_act=item_id in allowed,
        may_ask_waiver=item_id in asking(session, principal, [row], allowed),
    )[0]


def dismiss_blocked_reason(session: Session, row: Mapping[str, Any]) -> str | None:
    """04 §16.14 ``dismiss_blocked_reason`` of one item (PRD BR-DAT-04)."""
    return actions_of(row, queue_facts(session, [row]), may_act=False, may_ask_waiver=False)[1]


def item_outs(
    session: Session, rows: Sequence[Mapping[str, Any]], principal: Principal
) -> list[ExceptionItemOut]:
    """API-S of each ``item_select`` row with its actions for ``principal``. ``resolved_by`` is
    null until the item is resolved; an item the system resolved names the system. ``owner`` is the
    person behind ``owner_membership_id``, null while nobody owns the item. Whether the principal
    may act, and may ask a waiver, is read for the page at once (``acting``, ``asking``)."""
    facts = queue_facts(session, rows)
    allowed = acting(session, principal, rows)
    askable = asking(session, principal, rows, allowed)
    contract_ids = _ids(rows, "contract_id")
    external = (
        {
            _uuid(found.id): str(found.external_id)
            for found in session.execute(
                select(contract.c.id, contract.c.external_id).where(contract.c.id.in_(contract_ids))
            )
        }
        if contract_ids
        else {}
    )
    outs: list[ExceptionItemOut] = []
    for row in rows:
        item_id = _uuid(row["id"])
        actions, blocked = actions_of(
            row, facts, may_act=item_id in allowed, may_ask_waiver=item_id in askable
        )
        values = {name: value for name, value in row.items() if name not in _HIDDEN}
        contract_id = row["contract_id"]
        outs.append(
            ExceptionItemOut.model_validate(
                {
                    **values,
                    "owner": actors.member_actor(row[OWNER_NAMED]),
                    "resolved_by": None
                    if row["resolved_at"] is None
                    else actors.actor(
                        row["resolved_by"], row["resolved_by_kind"], row[RESOLVED_BY_NAMED]
                    ),
                    "contract_external_id": None
                    if contract_id is None
                    else external.get(_uuid(contract_id)),
                    "available_actions": list(actions),
                    "dismiss_blocked_reason": blocked,
                }
            )
        )
    return outs


def _shown(
    session: Session, principal: Principal, item_id: UUID, *conditions: ColumnElement[bool]
) -> ExceptionItemOut:
    row = (
        session.execute(item_select().where(exception_item.c.id == item_id, *conditions))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return item_outs(session, [dict(row)], principal)[0]


def get_item(session: Session, principal: Principal, item_id: UUID) -> ExceptionItemOut:
    """``GET /exceptions/{id}``: 404 ``not-found`` for an absent item, for one the row policy
    hides and for one the caller may not read (``readable``) — each exactly as an unknown id
    (REQ-PLT-012)."""
    return _shown(session, principal, item_id, readable(principal))


# --- commands ------------------------------------------------------------------------------------


def _locked(uow: UnitOfWork, item_id: UUID) -> dict[str, Any]:
    row = (
        uow.session.execute(
            select(exception_item).where(exception_item.c.id == item_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _require(uow: UnitOfWork, row: Mapping[str, Any], action: ExceptionAction) -> None:
    """Whether the caller may act on the item at all (``acting``): 404 ``not-found``, as for an
    unknown id, for an item it does not read and for one it reads without holding
    ``exception.resolve`` for everything the item is about — the answer a holder for another
    entity had for an entity-named item (DG-KRN-AUTH-04). Then the action among the item's
    available actions. Whether the waiver is this caller's to ask is the approvals kernel's
    answer, by name (``approvals.submit``: 403 for a preparer outside the entities the request
    names): the queue offers the action to nobody the kernel refuses (``asking``)."""
    if _uuid(row["id"]) not in acting(uow.session, uow.principal, [row]):
        raise Problem("not-found")
    actions, _ = actions_of(row, queue_facts(uow.session, [row]), may_act=True, may_ask_waiver=True)
    if action in actions:
        return
    message = (
        DISMISS_BLOCKED
        if action is ExceptionAction.DISMISS and _value(row["status"]) in OPEN_STATUSES
        else NOT_AVAILABLE.format(action=ACTION_LABELS[action])
    )
    raise Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=RULE_ACTION, message=message)],
    )


def _changed(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    values: Mapping[str, Any],
    *,
    action: str,
    approval_request_id: UUID | None = None,
) -> ExceptionItemOut:
    principal = uow.principal
    item_id = _uuid(row["id"])
    uow.session.execute(
        update(exception_item)
        .where(exception_item.c.tenant_id == principal.tenant_id, exception_item.c.id == item_id)
        .values(
            **values,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=exception_item.c.row_version + 1,
        )
    )
    before = {name: _audit_value(row[name]) for name in values if name in row}
    after = {name: _audit_value(value) for name, value in values.items()}
    uow.audit(
        action=action,
        object_type=OBJECT_TYPE,
        object_id=item_id,
        before=before,
        after=after,
        approval_request_id=approval_request_id,
        contract_ids=item_contracts(uow.session, row),
    )
    return _shown(uow.session, principal, item_id)


def _audit_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return _value(value)


def _cleared_values(
    uow: UnitOfWork, status: ExceptionStatus, resolution: str | None
) -> dict[str, Any]:
    principal = uow.principal
    return {
        "status": status.value,
        "resolution": resolution,
        "resolved_at": uow.now,
        "resolved_by": principal.id,
        "resolved_by_kind": principal.kind.value,
    }


def _read_by(uow: UnitOfWork, row: Mapping[str, Any], membership_id: UUID, user_id: UUID) -> bool:
    """Whether the member reads the item — the reading rule of the queue, asked for another
    person (04 API-R-44 rev 1.218, ``assign``). The member's grants are read now, as an uploader's
    are (``effective_grants``; the role tables are tenant-level). An item that names an entity is
    read inside the member's ``contract.read`` scope, as the row policy has it for the member's
    own read of the queue — a transaction of that permission (04 API-C-03 rev 1.319; until then
    the entities of the member's roles); an item that names none by ``readable`` for the member.
    The caller acts on the item, so its own session reads every contract the item is about — the
    statement sees what the member's would."""
    grants = effective_grants(uow.session, membership_id, at=uow.now)
    scope = grants.permission_scopes.get(READ_PERMISSION)
    if scope is None:
        return False
    if row["entity_id"] is not None:
        return scope == "*" or _uuid(row["entity_id"]) in scope
    member = dataclasses.replace(
        uow.principal,
        id=user_id,
        kind=PrincipalKind.USER,
        membership_id=membership_id,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope="*" if scope == "*" else tuple(sorted(scope)),
    )
    statement = select(exception_item.c.id).where(
        exception_item.c.id == row["id"], readable(member)
    )
    return uow.session.execute(statement).first() is not None


def assign(uow: UnitOfWork, *, item_id: UUID, owner_membership_id: UUID) -> ExceptionItemOut:
    """``POST /exceptions/{id}/assign``: record the owner, OPEN → IN_PROGRESS, NTF-11 to them.
    The owner is an ACTIVE member who reads the item (``_read_by``); 422 on
    ``owner_membership_id`` otherwise."""
    row = _locked(uow, item_id)
    _require(uow, row, ExceptionAction.ASSIGN)
    principal = uow.principal
    found = uow.session.execute(
        select(tenant_membership.c.id, tenant_membership.c.user_id).where(
            tenant_membership.c.tenant_id == principal.tenant_id,
            tenant_membership.c.id == owner_membership_id,
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
        )
    ).one_or_none()
    if found is None:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(field="owner_membership_id", rule_id=RULE_OWNER, message=OWNER_UNKNOWN)
            ],
        )
    owner = _uuid(found.id)
    if not _read_by(uow, row, owner, _uuid(found.user_id)):
        # The owner is told of the item (NTF-11) and opens it from that message: an owner who
        # could not read it is refused here, by name. The screen prints the problem's detail.
        raise Problem(
            "validation-failed",
            OWNER_CANNOT_READ,
            errors=[
                ProblemError(
                    field="owner_membership_id", rule_id=RULE_OWNER, message=OWNER_CANNOT_READ
                )
            ],
        )
    out = _changed(
        uow,
        row,
        {"owner_membership_id": owner, "status": ExceptionStatus.IN_PROGRESS.value},
        action=ASSIGN_ACTION,
    )
    notify(
        uow,
        recipient_membership_ids=[owner],
        kind=NotificationKind.EXCEPTION_ASSIGNED,
        title=f"Exception: {row['code']}",  # PRD NTF-11
        body=str(row["message"]),
        link_path=subjects.EXCEPTION_LINK.format(item_id=item_id),
        subject_type=OBJECT_TYPE,
        subject_id=item_id,
    )
    return out


def resolve(uow: UnitOfWork, *, item_id: UUID, resolution: str) -> ExceptionItemOut:
    """``POST /exceptions/{id}/resolve``: RESOLVED once the server finds the condition cleared."""
    row = _locked(uow, item_id)
    _require(uow, row, ExceptionAction.RESOLVE)
    values = _cleared_values(uow, ExceptionStatus.RESOLVED, resolution)
    return _changed(uow, row, values, action=RESOLVE_ACTION)


def dismiss(uow: UnitOfWork, *, item_id: UUID, comment: str) -> ExceptionItemOut:
    """``POST /exceptions/{id}/dismiss``: DISMISSED with the comment (PRD BR-DAT-04)."""
    row = _locked(uow, item_id)
    _require(uow, row, ExceptionAction.DISMISS)
    values = _cleared_values(uow, ExceptionStatus.DISMISSED, comment)
    return _changed(uow, row, values, action=DISMISS_ACTION)


def request_waiver(uow: UnitOfWork, *, item_id: UUID, comment: str) -> WaiverRequestedOut:
    """``POST /exceptions/{id}/request-waiver``: an ``EXCEPTION_WAIVER`` request (PRD SM-06)."""
    row = _locked(uow, item_id)
    _require(uow, row, ExceptionAction.REQUEST_WAIVER)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.EXCEPTION_WAIVER,
        subject_id=item_id,
        summary=f"Waiver of {row['exception_no']} {row['code']}",
        comment=comment,
        auto_approval=False,
    )
    return WaiverRequestedOut(
        approval_request_id=request["id"], request_no=str(request["request_no"])
    )


def request_reprocess(uow: UnitOfWork, *, item_id: UUID) -> JobOut:
    """``POST /exceptions/{id}/reprocess``: defer ``CONTRACT_COMPUTE`` of the item's group; 202
    API-S-Job (04 API-R-44 async ``reprocess``)."""
    # Imported here: the platform jobs module reads job rows the contract jobs also write.
    from erev_api.domain.platform.jobs import job_out_of

    row = _locked(uow, item_id)
    _require(uow, row, ExceptionAction.REPROCESS)
    source = _value(row["source"])
    if source != ExceptionSource.ENGINE.value:
        # 04 §16.14 rev 1.81: the source's registered reprocessor queues its own job (DIN-12: a
        # SYNC_RUN over the stored source record) in this unit of work.
        job = REPROCESSORS[ExceptionSource(source)](uow, row)
        uow.audit(
            action=REPROCESS_ACTION,
            object_type=OBJECT_TYPE,
            object_id=item_id,
            after={"job_id": str(job.id), "source_record_id": str(row["source_record_id"])},
            contract_ids=item_contracts(uow.session, row),
        )
        return job
    params: dict[str, Any] = {
        "combination_group_ids": [str(row["combination_group_id"])],
        "trigger": ComputationTrigger.COMMAND.value,
        "exception_item_id": str(item_id),
    }
    if row["contract_id"] is not None:
        params["contract_id"] = str(row["contract_id"])
    # The job's subject is the group it computes (04 T-PLT-27 ``ck_job__subject_type``).
    deferred = uow.defer(
        JobKind.CONTRACT_COMPUTE,
        params,
        subject_type=GROUP_OBJECT,
        subject_id=_uuid(row["combination_group_id"]),
    )
    job_id = _uuid(deferred["id"])
    uow.audit(
        action=REPROCESS_ACTION,
        object_type=OBJECT_TYPE,
        object_id=item_id,
        after={"job_id": str(job_id), "combination_group_id": str(row["combination_group_id"])},
        contract_ids=item_contracts(uow.session, row),
    )
    return job_out_of(uow.session, job_id)


def settle_record_reprocess(
    uow: UnitOfWork, item_id: UUID, *, resolved: bool, resolution: str | None = None
) -> None:
    """A registered reprocessor's run settles the item (04 §16.14 rev 1.81): ``reprocessed_at`` is
    set, and the item becomes RESOLVED ("Input processed") when the re-run did not raise its code
    again; otherwise it stays open with its occurrence counted by the re-run."""
    row = _locked(uow, item_id)
    values: dict[str, Any] = {"reprocessed_at": uow.now}
    if resolved and _value(row["status"]) in OPEN_STATUSES:
        values |= _cleared_values(uow, ExceptionStatus.RESOLVED, resolution or INPUT_PROCESSED)
    _changed(uow, dict(row), values, action=REPROCESSED_ACTION)


def open_keys(
    session: Session, *, source: ExceptionSource, entity_id: UUID, period_id: UUID
) -> list[tuple[UUID, str]]:
    """(id, ``dedupe_key``) of the OPEN and IN_PROGRESS items of ``source`` for the entity and
    period, in number order; no row is locked."""
    rows = session.execute(
        select(exception_item.c.id, exception_item.c.dedupe_key)
        .where(
            exception_item.c.source == source.value,
            exception_item.c.status.in_(OPEN_STATUSES),
            exception_item.c.entity_id == entity_id,
            exception_item.c.period_id == period_id,
        )
        .order_by(exception_item.c.exception_no)
    ).all()
    return [(_uuid(row.id), str(row.dedupe_key)) for row in rows]


def settle_gone(
    uow: UnitOfWork, item_ids: Sequence[UUID], *, resolution: str, wait: bool = False
) -> tuple[UUID, ...]:
    """A producer that evaluates the facts on every run settles the items whose finding it no
    longer makes (04 T-IMP-05 rev 1.185 "A monitor finding that is gone"; PRD SM-06): RESOLVED by
    the SYSTEM — ``resolved_by_kind`` ``SYSTEM`` and no ``resolved_by``, whoever started the run —
    with ``resolution`` saying so and the AUD-CMD event ``exception_item.resolve``. Only items
    still OPEN or IN_PROGRESS are settled, in number order. A row another transaction holds — a
    run that is counting it again, a person's command on it — is skipped, never waited for: the
    next run settles it if its finding is still gone. ``wait`` is for a producer that settles
    once, with the event that ends its finding, and has no next run (a reopen settles the items
    of a rate changed after the lock, ``close.rate_changes``): a held row is waited for. Returns
    the ids settled."""
    if not item_ids:
        return ()
    found = (
        select(exception_item)
        .where(
            exception_item.c.id.in_(list(item_ids)),
            exception_item.c.status.in_(OPEN_STATUSES),
        )
        .order_by(exception_item.c.exception_no)
    )
    held = found.with_for_update() if wait else found.with_for_update(skip_locked=True)
    rows = uow.session.execute(held).mappings().all()
    values: dict[str, Any] = {
        "status": ExceptionStatus.RESOLVED.value,
        "resolution": _clip(resolution, MESSAGE_LIMIT),
        "resolved_at": uow.now,
        "resolved_by": None,
        "resolved_by_kind": PrincipalKind.SYSTEM.value,
    }
    for row in rows:
        _changed(uow, dict(row), values, action=RESOLVE_ACTION)
    return tuple(_uuid(row["id"]) for row in rows)


def settle_reprocess(
    uow: UnitOfWork,
    item_id: UUID,
    *,
    status: ComputationStatus | None,
    computation: Mapping[str, Any] | None,
    raised: Sequence[UUID],
) -> None:
    """The reprocess computation settles the item: ``reprocessed_at`` is set, and the item becomes
    RESOLVED when the computation SUCCEEDED, was not a replay and did not raise the item again."""
    row = (
        uow.session.execute(
            select(exception_item).where(exception_item.c.id == item_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return
    values: dict[str, Any] = {"reprocessed_at": uow.now}
    replayed = computation is not None and bool(computation.get("replayed"))
    succeeded = status is ComputationStatus.SUCCEEDED and not replayed
    if succeeded and _value(row["status"]) in OPEN_STATUSES and item_id not in set(raised):
        computation_id = "" if computation is None else str(computation.get("id"))
        values |= _cleared_values(
            uow,
            ExceptionStatus.RESOLVED,
            REPROCESSED.format(computation=computation_id, code=row["code"]),
        )
    _changed(uow, dict(row), values, action=REPROCESSED_ACTION)


def _waived(uow: UnitOfWork, item_id: UUID, approval_request_id: UUID) -> None:
    """``EXCEPTION_WAIVER`` approved: WAIVED with the request and its comment (PRD SM-06)."""
    row = _locked(uow, item_id)
    if _value(row["status"]) not in OPEN_STATUSES:
        message = NOT_AVAILABLE.format(action=ACTION_LABELS[ExceptionAction.REQUEST_WAIVER])
        raise Problem(
            "invalid-transition",
            message,
            errors=[ProblemError(field="status", rule_id=RULE_ACTION, message=message)],
        )
    comment = uow.session.execute(
        select(approval_request.c.comment).where(approval_request.c.id == approval_request_id)
    ).scalar_one_or_none()
    values = {
        **_cleared_values(uow, ExceptionStatus.WAIVED, None if comment is None else str(comment)),
        "waiver_approval_request_id": approval_request_id,
    }
    _changed(uow, row, values, action=WAIVE_ACTION, approval_request_id=approval_request_id)


def _unchanged(_: UnitOfWork, __: UUID, ___: UUID) -> None:
    """A rejected or voided waiver leaves the item open."""


def waiver_entities_of(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[UUID, subjects.SubjectEntities]:
    """The legal entities the waiver of each exception item of ``rows`` is bound to — who reads
    the request, who decides it and who may ask it (04 §16.10 rev 1.218;
    ``SubjectLifecycle.entities``; item EXC-IMPORT-SCOPE-1): the entities whose close the item
    holds by the one attribution (``close.gates.item_of_entity``; the supervisor's ruling of
    2026-10-01). The item's entity; for an item that names none, the contracting entity of the
    contract it names, of each contract a combination suggestion names — one more than the
    attribution, which reads the contract the suggestion names: its approver must read what he
    waives (``readable``) — and of every current member of the group it names
    (``item_contracts``); else the entities its upload names and those the connection of its
    sync run serves. EVERY entity where the attribution says every entity: an upload that names
    none or is not resolved, a connection that names none, and an item about none of these — a
    finding about the workspace holds every entity's close, so its waiver is decided by an
    approver for all entities, where before any holder decided it. A contract the session cannot
    read, and a group no membership names, make the subject span every entity rather than drop
    an entity it cannot name; the kernel reads under the tenant's SYSTEM scope, where the first
    does not happen for a row that exists.

    One definition for the kernel, which asks it for one item (``waiver_entities``), and for the
    queue, which asks it for a page (``asking``): at most four statements whatever the number of
    rows, and none for rows that name an entity. ``rows`` are rows of ``exception_item``, keyed
    by ``id`` in the answer."""
    # imported here: the templates the scope module loads raise items through this module
    from erev_api.domain.imports import scope as import_scope

    unnamed = [row for row in rows if row["entity_id"] is None]
    stated = {_uuid(row["id"]): _stated_contracts(row) for row in unnamed}
    members = _group_members(
        session,
        sorted(
            {
                _uuid(row["combination_group_id"])
                for row in unnamed
                if stated[_uuid(row["id"])] is None
            },
            key=str,
        ),
    )
    contracts: dict[UUID, list[UUID]] = {}
    for row in unnamed:
        item_id = _uuid(row["id"])
        named = stated[item_id]
        contracts[item_id] = members[_uuid(row["combination_group_id"])] if named is None else named
    wanted = sorted({value for named in contracts.values() for value in named}, key=str)
    owners: dict[UUID, UUID] = {}
    if wanted:
        owners = {
            _uuid(contract_id): _uuid(entity_id)
            for contract_id, entity_id in session.execute(
                select(contract.c.id, contract.c.contracting_entity_id).where(
                    contract.c.id.in_(wanted)
                )
            )
        }
    # names no entity, contract or group: of the entities of its import and of its connection,
    # and of every entity without either (``gates._of_no_named_entity``)
    rest = [
        row
        for row in unnamed
        if not contracts[_uuid(row["id"])] and row["combination_group_id"] is None
    ]
    uploads = sorted(
        {_uuid(row["import_upload_id"]) for row in rest if row["import_upload_id"] is not None},
        key=str,
    )
    names: dict[UUID, frozenset[UUID] | None] = {}
    if uploads:
        names = {
            _uuid(found["id"]): import_scope.stored(dict(found))
            for found in session.execute(
                select(import_upload.c.id, import_upload.c.named_entity_ids).where(
                    import_upload.c.id.in_(uploads)
                )
            ).mappings()
        }
    runs = sorted(
        {_uuid(row["sync_run_id"]) for row in rest if row["sync_run_id"] is not None}, key=str
    )
    serves: dict[UUID, frozenset[UUID]] = {}
    if runs:
        serves = {
            _uuid(run_id): frozenset(_uuid(value) for value in served or ())
            for run_id, served in session.execute(
                select(sync_run.c.id, integration_connection.c.entity_ids)
                .select_from(
                    sync_run.join(
                        integration_connection,
                        and_(
                            integration_connection.c.tenant_id == sync_run.c.tenant_id,
                            integration_connection.c.id == sync_run.c.integration_connection_id,
                        ),
                    )
                )
                .where(sync_run.c.id.in_(runs))
            )
        }

    def bound(row: Mapping[str, Any]) -> subjects.SubjectEntities:
        if row["entity_id"] is not None:
            return subjects.SubjectEntities(frozenset({_uuid(row["entity_id"])}))
        named = contracts[_uuid(row["id"])]
        if named:
            if any(value not in owners for value in named):
                return subjects.ALL_ENTITIES
            return subjects.SubjectEntities(frozenset(owners[value] for value in named))
        if row["combination_group_id"] is not None:
            return subjects.ALL_ENTITIES
        entities: frozenset[UUID] | None = None
        if row["import_upload_id"] is not None:
            # an upload that names none, is not resolved, or is no row for the session
            entities = names.get(_uuid(row["import_upload_id"]))
            if not entities:
                return subjects.ALL_ENTITIES
        if row["sync_run_id"] is not None:
            served = serves.get(_uuid(row["sync_run_id"]))
            if not served:
                return subjects.ALL_ENTITIES
            entities = served if entities is None else entities & served
        if not entities:
            return subjects.ALL_ENTITIES
        return subjects.SubjectEntities(entities)

    return {_uuid(row["id"]): bound(row) for row in rows}


def waiver_entities(session: Session, item_id: UUID) -> subjects.SubjectEntities:
    """``waiver_entities_of`` for one item, as the approvals kernel asks it
    (``SubjectLifecycle.entities``); 404 for an item that is no row for the session."""
    found = (
        session.execute(select(exception_item).where(exception_item.c.id == item_id))
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    return waiver_entities_of(session, [dict(found)])[item_id]


subjects.register_lifecycle(
    ApprovalSubjectType.EXCEPTION_WAIVER,
    subjects.SubjectLifecycle(
        on_approved=_waived,
        on_rejected=_unchanged,
        on_voided=_unchanged,
        entities=waiver_entities,
    ),
)
