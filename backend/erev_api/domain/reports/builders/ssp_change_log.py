"""RPT-19 ``ssp_change_log`` SSP change log (SCREENS_B §5.6.4 RPT-19; 04 T-REF-28, T-REF-29,
T-REF-30, T-PLT-17, T-PLT-20, T-PLT-30; PRD J-02-AC-6, BR-SSP-02; 03 REQ-SSP-001, REQ-SSP-007,
REQ-SSP-008, REQ-SSP-012; CTL-011; BUILD_SPEC RPS-9).

One row per SSP book version with a lifecycle transition in ``from_date`` .. ``to_date`` (UTC days,
inclusive; defaults: the first day of the context fiscal year and the run's day): the version was
created, submitted, decided (approved, rejected, withdrawn or voided) or superseded then.
``ssp_book_code`` keeps one book; the books are those of the run's entities and the tenant-wide
books (``ssp_book.entity_id`` null). Rows are ordered by book code and version number; ``row_key``
``ssp:<book code>:<version no>``.

The transitions come from the rows themselves: ``created_at`` of the version, ``submitted_at`` and
the terminal instant of each ``SSP_BOOK_VERSION`` approval request of the version, and, for
supersession, the approval instant of the successor. The successor of a version is the approved
version of the same book that takes effect on the day after the version's ``effective_to_date``
(BR-SSP-02 ends the version in force on the day before its successor starts); its label is
``superseded_by_label``.

Columns: the version's label (``legacy_version_label`` or ``v<n>``), E-12 status, effective dates,
methodology label and methodology-change flag, the number of its entries, the stored
``diff_summary`` counts against the prior approved version (empty until the version is first
submitted), the preparer (the latest request's preparer, else the version's creator), the approving
deciders of the latest request in decision order, the approval instant and the file names of the
live ``SSP_STUDY`` attachments. Control totals ``row_count`` and the range applied (``from_date``,
``to_date``); no totals and no tie-out.

Cutoff: versions created, requests submitted and decisions taken by the run's record cutoff.
T-REF-29 keeps no row history (status, effective-to date, labels and the diff summary move in
place), so an explicit historical run whose cutoff precedes the last change of a version in scope
is refused by name (REGISTER-CUTOFF-1); a live run never refuses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    file_attachment,
    file_object,
    ssp_book,
    ssp_book_version,
    ssp_entry,
)
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApprovalSubjectType, ConfigStatus, FilePurpose
from erev_api.uow import UnitOfWork

CODE: Final = "ssp_change_log"
ROW_KEY_PREFIX: Final = "ssp:"  # RPT-19: row_key `ssp:<book code>:<version no>`
SUBJECT_TYPE: Final = ApprovalSubjectType.SSP_BOOK_VERSION.value
STUDY_SUBJECT: Final = "ssp_book_version"  # file_attachment.subject_type of a version's study
OPEN_ENDED: Final = "—"  # RPT-19 "em dash when open"
HISTORY_UNAVAILABLE: Final = (
    "The SSP change log cannot state {version} as of {cutoff}: the version last changed at "
    "{updated_at} — its status, effective-to date or diff summary moved after the cutoff and "
    "T-REF-29 keeps no row history, so the log as of {cutoff} is unavailable (not reconstructed, "
    "not narrowed). Run the log at a later known_at or current."
)
COLUMNS: Final = (
    Column("ssp_book_code", "SSP book", "code"),
    Column("version_label", "Version", "code"),
    Column("status", "Status", "code"),
    Column("effective_from_date", "Effective from", "date"),
    Column("effective_to_date", "Effective to", "date", empty_text=OPEN_ENDED),
    Column("methodology_label", "Methodology", "text"),
    Column("is_methodology_change", "Methodology change", "boolean"),
    Column("entry_count", "Entries", "integer"),
    Column("diff_summary.added", "Added", "integer"),
    Column("diff_summary.removed", "Removed", "integer"),
    Column("diff_summary.changed", "Changed", "integer"),
    Column("preparer", "Preparer", "text"),
    Column("approvers", "Approvers", "text"),
    Column("approved_at", "Approved", "timestamp"),
    Column("superseded_by_label", "Superseded by", "code"),
    Column("study_file_name", "Study", "text"),
)


@dataclass(frozen=True, slots=True)
class Source:
    """One SSP book version with its requests, successor and study resolved — the input of
    ``dataset_rows``."""

    book_code: str
    version_no: int
    legacy_version_label: str | None
    status: str
    effective_from_date: date | None
    effective_to_date: date | None
    methodology_label: str
    is_methodology_change: bool
    entry_count: int
    diff_summary: Mapping[str, Any] | None
    created_at: datetime
    created_by: tuple[UUID | None, str]
    requests: tuple[support.Request, ...]  # submission order
    successor_label: str | None
    superseded_at: datetime | None
    study_file_names: tuple[str, ...]

    @property
    def transitions(self) -> tuple[datetime, ...]:
        """The lifecycle instants of the version: created, each submission and terminal decision,
        and the supersession."""
        found = [self.created_at]
        for request in self.requests:
            found.append(request.submitted_at)
            if request.decided_at is not None:
                found.append(request.decided_at)
        if self.superseded_at is not None:
            found.append(self.superseded_at)
        return tuple(found)


def in_range(source: Source, bounds: tuple[datetime, datetime]) -> bool:
    """A lifecycle transition of the version lies in the run's range. Pure."""
    return any(support.within(moment, bounds) for moment in source.transitions)


def row_key(book_code: str, version_no: int) -> str:
    return f"{ROW_KEY_PREFIX}{book_code}:{version_no}"


def _count(summary: Mapping[str, Any] | None, member: str) -> int | None:
    if summary is None or summary.get(member) is None:
        return None
    return int(summary[member])


def dataset_rows(found: Iterable[Source], names: Mapping[UUID, str]) -> list[dict[str, Any]]:
    """The RPT-19 rows in (book code, version number) order. Pure."""
    rows: list[dict[str, Any]] = []
    for item in sorted(found, key=lambda source: (source.book_code, source.version_no)):
        latest = item.requests[-1] if item.requests else None
        preparer = item.created_by if latest is None else latest.preparer
        approvers = () if latest is None else latest.approvers
        rows.append(
            {
                "row_key": row_key(item.book_code, item.version_no),
                "ssp_book_code": item.book_code,
                "version_label": support.version_label(item.legacy_version_label, item.version_no),
                "status": item.status,
                "effective_from_date": item.effective_from_date,
                "effective_to_date": item.effective_to_date,
                "methodology_label": item.methodology_label,
                "is_methodology_change": item.is_methodology_change,
                "entry_count": item.entry_count,
                "diff_summary.added": _count(item.diff_summary, "added"),
                "diff_summary.removed": _count(item.diff_summary, "removed"),
                "diff_summary.changed": _count(item.diff_summary, "changed"),
                "preparer": support.actor_names([preparer], names)[0],
                "approvers": support.joined(support.actor_names(approvers, names)),
                "approved_at": None if latest is None else latest.approved_at,
                "superseded_by_label": item.successor_label,
                "study_file_name": support.joined(item.study_file_names),
            }
        )
    return rows


def successors(rows: Sequence[Mapping[str, Any]]) -> dict[UUID, Mapping[str, Any]]:
    """Version id → the approved version of the same book that takes effect the day after its
    ``effective_to_date`` (BR-SSP-02); the lowest version number wins a tie. Pure."""
    starts: dict[tuple[UUID, date], Mapping[str, Any]] = {}
    for row in sorted(rows, key=lambda item: int(item["version_no"]), reverse=True):
        if (
            support.text(row["status"]) == ConfigStatus.APPROVED.value
            and row["effective_from_date"] is not None
            and row["published_at"] is not None
        ):
            starts[(UUID(str(row["ssp_book_id"])), row["effective_from_date"])] = row
    found: dict[UUID, Mapping[str, Any]] = {}
    for row in rows:
        if row["effective_to_date"] is None:
            continue
        key = (UUID(str(row["ssp_book_id"])), row["effective_to_date"] + timedelta(days=1))
        successor = starts.get(key)
        if successor is not None and successor["id"] != row["id"]:
            found[UUID(str(row["id"]))] = successor
    return found


def _entry_counts(session: Session, version_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not version_ids:
        return {}
    statement = (
        select(ssp_entry.c.ssp_book_version_id, func.count())
        .where(ssp_entry.c.ssp_book_version_id.in_(list(version_ids)))
        .group_by(ssp_entry.c.ssp_book_version_id)
    )
    return {UUID(str(version_id)): int(count) for version_id, count in session.execute(statement)}


def _studies(
    session: Session, version_ids: Sequence[UUID], *, cutoff: datetime
) -> dict[UUID, list[str]]:
    """The file names of each version's ``SSP_STUDY`` attachments live at the cutoff, in
    attachment order (REQ-SSP-008)."""
    if not version_ids:
        return {}
    statement = (
        select(file_attachment.c.subject_id, file_object.c.original_filename)
        .select_from(
            file_attachment.join(
                file_object,
                and_(
                    file_object.c.tenant_id == file_attachment.c.tenant_id,
                    file_object.c.id == file_attachment.c.file_object_id,
                ),
            )
        )
        .where(
            file_attachment.c.subject_type == STUDY_SUBJECT,
            file_attachment.c.subject_id.in_(list(version_ids)),
            file_attachment.c.created_at <= cutoff,
            or_(file_attachment.c.voided_at.is_(None), file_attachment.c.voided_at > cutoff),
            file_object.c.purpose == FilePurpose.SSP_STUDY.value,
        )
        .order_by(file_attachment.c.created_at, file_attachment.c.id)
    )
    found: dict[UUID, list[str]] = {}
    for subject_id, name in session.execute(statement):
        found.setdefault(UUID(str(subject_id)), []).append(str(name))
    return found


def sources(uow: UnitOfWork, params: ReportParams) -> list[Source]:
    """Every version of the books in scope recorded by the cutoff (module docstring)."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    scope: ColumnElement[bool] = ssp_book.c.entity_id.is_(None)
    if params.entity_ids:
        scope = or_(scope, ssp_book.c.entity_id.in_(list(params.entity_ids)))
    statement = (
        select(ssp_book_version, ssp_book.c.code.label("book_code"))
        .select_from(
            ssp_book_version.join(
                ssp_book,
                and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
        )
        .where(scope, ssp_book_version.c.created_at <= cutoff)
        .order_by(ssp_book.c.code, ssp_book_version.c.version_no)
    )
    book_code = params.parameters.get("ssp_book_code")
    if book_code is not None:
        statement = statement.where(ssp_book.c.code == str(book_code))
    rows = [dict(row) for row in session.execute(statement).mappings()]
    # REGISTER-CUTOFF-1: the whole population in scope is inspected before the range filter.
    moved = support.changed_after(rows, cutoff=cutoff, historical=params.historical)
    if moved is not None:
        raise tie_outs.invalid(
            "known_at",
            HISTORY_UNAVAILABLE.format(
                version=support.version_name(
                    moved["book_code"], moved["legacy_version_label"], moved["version_no"]
                ),
                cutoff=cutoff.isoformat(),
                updated_at=moved["updated_at"].isoformat(),
            ),
        )
    if not rows:
        return []
    ids = [UUID(str(row["id"])) for row in rows]
    approvals = support.requests_of_subjects(session, SUBJECT_TYPE, ids, cutoff=cutoff)
    following = successors(rows)
    counts = _entry_counts(session, ids)
    studies = _studies(session, ids, cutoff=cutoff)
    found: list[Source] = []
    for row in rows:
        version_id = UUID(str(row["id"]))
        successor = following.get(version_id)
        superseded_at = None if successor is None else successor["published_at"]
        if superseded_at is not None and superseded_at > cutoff:
            successor, superseded_at = None, None
        found.append(
            Source(
                book_code=str(row["book_code"]),
                version_no=int(row["version_no"]),
                legacy_version_label=(
                    None
                    if row["legacy_version_label"] is None
                    else str(row["legacy_version_label"])
                ),
                status=str(support.text(row["status"])),
                effective_from_date=row["effective_from_date"],
                effective_to_date=row["effective_to_date"],
                methodology_label=str(row["methodology_label"]),
                is_methodology_change=bool(row["is_methodology_change"]),
                entry_count=counts.get(version_id, 0),
                diff_summary=row["diff_summary"],
                created_at=row["created_at"],
                created_by=(
                    support.uuid_of(row["created_by"]),
                    str(support.text(row["created_by_kind"])),
                ),
                requests=tuple(approvals.get(version_id, ())),
                successor_label=(
                    None
                    if successor is None
                    else support.version_label(
                        successor["legacy_version_label"], successor["version_no"]
                    )
                ),
                superseded_at=superseded_at,
                study_file_names=tuple(studies.get(version_id, ())),
            )
        )
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    first, last = support.date_range(uow.session, params, today=True)
    bounds = support.instants(first, last)
    found = [item for item in sources(uow, params) if in_range(item, bounds)]
    names = support.names_of(
        uow.session,
        (request for item in found for request in item.requests),
        (item.created_by[0] for item in found),
    )
    rows = dataset_rows(found, names)
    totals = {"row_count": len(rows), "from_date": first.isoformat(), "to_date": last.isoformat()}
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "HISTORY_UNAVAILABLE",
    "Source",
    "build",
    "dataset_rows",
    "in_range",
    "row_key",
    "sources",
    "successors",
]
