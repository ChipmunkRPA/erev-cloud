"""RPT-28 ``judgement_register`` Judgement register (SCREENS_B §5.6.2 RPT-28; 04 T-CON-19, E-56,
E-57; PRD SM-10, J-06.1, J-14.1, WLD-B-03; 03 REQ-RPT-023, REQ-POL-008, REQ-CLS-009; research 07
A-07; BUILD_SPEC RPS-11).

One row per judgement record recorded (``created_at``) in ``from_date`` .. ``to_date`` (UTC days;
defaults: the first day of the context fiscal year and the run's day), narrowed by ``topic``
(E-56) and ``status`` (E-57) when given — ``status`` ``SUBMITTED`` lists the records that wait for
review, the list behind close blocker BLK-06. The population is the records of the contracts of
the run's entities and the records that name no contract of their own: of a product, a registry
version or a migration batch always; of a combination group when the run's entities hold a
contract of the group; and the proposal of a combination (topic ``COMBINATION``, whose
conclusion names its contracts) when the run's entities hold EVERY contract it names. The run's
entities stand for its readers — a run is read by every member whose scope covers them — as
in the registers of requests (head R28-READS; supervisor ruling R-28;
``contracts.repo.reads_group`` and ``reads_proposal`` with ``within``). A record of one book is
listed when that book is the run's, a record for all books always. Rows are ordered by
judgement number; ``row_key`` ``judgement:<judgement no>``.

- ``subject_type`` is the T-CON-19 subject literal and ``subject_label`` names the subject: the
  contract's external id; ``<external id> <obligation key>``; the combination group's code; the
  modification's reference, else its number; ``<element code> v<n>`` of an estimate version; the
  product's code; ``<category> v<n>`` of a registry version; the migration's number.
- ``book`` is empty for a record that applies to every book ("All books" in XLSX and PDF);
  ``created_by`` and ``reviewer`` are display names; ``supersedes_no`` the number of the record
  this one replaces.

Control totals ``row_count`` and ``record_count`` with the date range applied.
``record_count`` is the records of the run in all: greater than ``row_count`` by the proposals of
a combination of which the run's entities hold some contracts and not all — a register is
evidence, and a run that is short says by how many. T-CON-19 keeps no history of its status,
so an explicit historical run whose cutoff precedes the last change of a record in scope and range
is refused by name (REGISTER-CUTOFF-1); a live run never refuses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    combination_group,
    contract,
    estimate,
    estimate_version,
    judgement_record,
    migration_batch,
    modification,
    obligation,
    product,
    registry_version,
)
from erev_api.domain.contracts import repo
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import JudgementTopic
from erev_api.uow import UnitOfWork

CODE: Final = "judgement_register"
ROW_KEY_PREFIX: Final = "judgement:"  # RPT-28: row_key `judgement:<judgement no>`
ALL_BOOKS: Final = "All books"
HISTORY_UNAVAILABLE: Final = (
    "The judgement register cannot state {judgement_no} as of {cutoff}: the record last changed "
    "at {updated_at}, after the cutoff, and T-CON-19 keeps no history of its status (not "
    "reconstructed). Run the register at a later known_at or current."
)
COLUMNS: Final = (
    Column("judgement_no", "Judgement", "code"),
    Column("topic", "Topic", "code"),
    Column("subject_type", "Subject type", "code"),
    Column("subject_label", "Subject", "text"),
    Column("contract_external_id", "Contract", "code"),
    Column("book", "Book", "code", empty_text=ALL_BOOKS),
    Column("conclusion", "Conclusion", "text"),
    Column("codification_refs", "Codification references", "codes"),
    Column("created_by", "Preparer", "text"),
    Column("reviewer", "Reviewer", "text"),
    Column("status", "Status", "code"),
    Column("reviewed_at", "Reviewed", "timestamp"),
    Column("supersedes_no", "Supersedes", "code"),
)


@dataclass(frozen=True, slots=True)
class Source:
    """One judgement record with its labels resolved — the input of ``dataset_rows``."""

    judgement_no: str
    topic: str
    subject_type: str
    subject_label: str | None
    contract_external_id: str | None
    book: str | None
    conclusion: str
    codification_refs: tuple[str, ...]
    created_by: tuple[UUID | None, str]
    reviewer_id: UUID | None
    status: str
    reviewed_at: datetime | None
    supersedes_no: str | None


def dataset_rows(
    found: Iterable[Source], names: Mapping[UUID, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in judgement-number order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    for item in sorted(found, key=lambda source: source.judgement_no):
        rows.append(
            {
                "row_key": f"{ROW_KEY_PREFIX}{item.judgement_no}",
                "judgement_no": item.judgement_no,
                "topic": item.topic,
                "subject_type": item.subject_type,
                "subject_label": item.subject_label,
                "contract_external_id": item.contract_external_id,
                "book": item.book,
                "conclusion": item.conclusion,
                "codification_refs": item.codification_refs,
                "created_by": support.actor_names([item.created_by], names)[0],
                "reviewer": None if item.reviewer_id is None else names.get(item.reviewer_id),
                "status": item.status,
                "reviewed_at": item.reviewed_at,
                "supersedes_no": item.supersedes_no,
            }
        )
    return rows, {"row_count": len(rows)}


# --- subject labels -------------------------------------------------------------------------------


def _ids(rows: Sequence[Mapping[str, Any]], subject_type: str) -> list[UUID]:
    found = {UUID(str(row["subject_id"])) for row in rows if row["subject_type"] == subject_type}
    return sorted(found, key=str)


def subject_labels(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[tuple[str, UUID], str]:
    """``subject_label`` of every subject the records name (module docstring)."""
    labels: dict[tuple[str, UUID], str] = {}

    def add(subject_type: str, statement: Any, label: Any) -> None:
        for row in session.execute(statement).mappings():
            labels[(subject_type, UUID(str(row["id"])))] = str(label(row))

    wanted = _ids(rows, "contract")
    if wanted:
        add(
            "contract",
            select(contract.c.id, contract.c.external_id).where(contract.c.id.in_(wanted)),
            lambda row: row["external_id"],
        )
    wanted = _ids(rows, "obligation")
    if wanted:
        add(
            "obligation",
            select(obligation.c.id, obligation.c.obligation_key, contract.c.external_id)
            .select_from(
                obligation.join(
                    contract,
                    and_(
                        contract.c.tenant_id == obligation.c.tenant_id,
                        contract.c.id == obligation.c.contract_id,
                    ),
                )
            )
            .where(obligation.c.id.in_(wanted)),
            lambda row: f"{row['external_id']} {row['obligation_key']}",
        )
    wanted = _ids(rows, "combination_group")
    if wanted:
        add(
            "combination_group",
            select(combination_group.c.id, combination_group.c.code).where(
                combination_group.c.id.in_(wanted)
            ),
            lambda row: row["code"],
        )
    wanted = _ids(rows, "modification")
    if wanted:
        add(
            "modification",
            select(
                modification.c.id, modification.c.reference, modification.c.modification_no
            ).where(modification.c.id.in_(wanted)),
            lambda row: row["reference"] or row["modification_no"],
        )
    wanted = _ids(rows, "estimate_version")
    if wanted:
        add(
            "estimate_version",
            select(estimate_version.c.id, estimate_version.c.version_no, estimate.c.element_code)
            .select_from(
                estimate_version.join(
                    estimate,
                    and_(
                        estimate.c.tenant_id == estimate_version.c.tenant_id,
                        estimate.c.id == estimate_version.c.estimate_id,
                    ),
                )
            )
            .where(estimate_version.c.id.in_(wanted)),
            lambda row: f"{row['element_code']} v{int(row['version_no'])}",
        )
    wanted = _ids(rows, "product")
    if wanted:
        add(
            "product",
            select(product.c.id, product.c.code).where(product.c.id.in_(wanted)),
            lambda row: row["code"],
        )
    wanted = _ids(rows, "registry_version")
    if wanted:
        add(
            "registry_version",
            select(
                registry_version.c.id, registry_version.c.category, registry_version.c.version_no
            ).where(registry_version.c.id.in_(wanted)),
            lambda row: f"{support.text(row['category'])} v{int(row['version_no'])}",
        )
    wanted = _ids(rows, "migration_batch")
    if wanted:
        add(
            "migration_batch",
            select(migration_batch.c.id, migration_batch.c.migration_no).where(
                migration_batch.c.id.in_(wanted)
            ),
            lambda row: row["migration_no"],
        )
    return labels


def _without_contract(ids: Sequence[UUID]) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """(stated, withheld): which records that name no contract of their own a run of the entities
    ``ids`` states, and which it counts without stating them.

    A record of a product, a registry version or a migration batch is the workspace's. A record
    of a combination group is stated when the run's entities hold a contract of the group, and
    its proposal — a ``COMBINATION`` record, whose conclusion names the contracts — when they
    hold every contract it names. A proposal of which they hold some and not all belongs to the
    run and is withheld: the run's ``record_count`` counts it."""
    record = judgement_record.c
    of_a_group = record.subject_type == "combination_group"
    proposal = record.topic == JudgementTopic.COMBINATION.value
    stated_group = and_(
        repo.reads_group(record.tenant_id, record.subject_id, within=ids),
        or_(~proposal, repo.reads_proposal(judgement_record, within=ids)),
    )
    stated = or_(~of_a_group, stated_group)
    withheld = and_(of_a_group, proposal, repo.names_within(judgement_record, ids), ~stated_group)
    return stated, withheld


def _kept(
    rows: Sequence[Mapping[str, Any]], params: ReportParams, book_code: str
) -> list[Mapping[str, Any]]:
    """The rows of the run's book — or of every book — and of its ``topic`` and ``status``."""
    topics = {str(value) for value in params.parameters.get("topic") or ()}
    statuses = {str(value) for value in params.parameters.get("status") or ()}
    return [
        row
        for row in rows
        if support.text(row["book_code"]) in (None, book_code)
        and (not topics or support.text(row["topic"]) in topics)
        and (not statuses or support.text(row["status"]) in statuses)
    ]


def withheld_count(
    uow: UnitOfWork, params: ReportParams, *, bounds: tuple[datetime, datetime], book_code: str
) -> int:
    """How many records in range belong to the run and are not stated by it
    (``_without_contract``), under the run's book, ``topic`` and ``status``."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    _, withheld = _without_contract(sorted(params.entity_ids, key=str))
    statement = select(
        judgement_record.c.book_code, judgement_record.c.topic, judgement_record.c.status
    ).where(
        judgement_record.c.contract_id.is_(None),
        withheld,
        judgement_record.c.created_at <= cutoff,
        judgement_record.c.created_at >= bounds[0],
        judgement_record.c.created_at < bounds[1],
    )
    rows = [dict(row) for row in session.execute(statement).mappings()]
    return len(_kept(rows, params, book_code))


def sources(
    uow: UnitOfWork, params: ReportParams, *, bounds: tuple[datetime, datetime], book_code: str
) -> list[Source]:
    """The judgement records in scope and range, as recorded at the cutoff."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    ids = sorted(params.entity_ids, key=str)
    stated, _ = _without_contract(ids)
    scope: ColumnElement[bool] = and_(judgement_record.c.contract_id.is_(None), stated)
    if ids:
        scope = or_(scope, contract.c.contracting_entity_id.in_(ids))
    statement = (
        select(judgement_record, contract.c.external_id.label("contract_external_id"))
        .select_from(
            judgement_record.outerjoin(
                contract,
                and_(
                    contract.c.tenant_id == judgement_record.c.tenant_id,
                    contract.c.id == judgement_record.c.contract_id,
                ),
            )
        )
        .where(
            scope,
            judgement_record.c.created_at <= cutoff,
            judgement_record.c.created_at >= bounds[0],
            judgement_record.c.created_at < bounds[1],
        )
        .order_by(judgement_record.c.judgement_no)
    )
    rows = [dict(row) for row in session.execute(statement).mappings()]
    moved = support.changed_after(rows, cutoff=cutoff, historical=params.historical)
    if moved is not None:
        raise tie_outs.invalid(
            "known_at",
            HISTORY_UNAVAILABLE.format(
                judgement_no=moved["judgement_no"],
                cutoff=cutoff.isoformat(),
                updated_at=moved["updated_at"].isoformat(),
            ),
        )
    kept = _kept(rows, params, book_code)
    labels = subject_labels(session, kept)
    superseded = sorted({UUID(str(row["supersedes_id"])) for row in kept if row["supersedes_id"]})
    numbers: dict[UUID, str] = {}
    if superseded:
        numbers = {
            UUID(str(found_id)): str(number)
            for found_id, number in session.execute(
                select(judgement_record.c.id, judgement_record.c.judgement_no).where(
                    judgement_record.c.id.in_(superseded)
                )
            )
        }
    return [
        Source(
            judgement_no=str(row["judgement_no"]),
            topic=str(support.text(row["topic"])),
            subject_type=str(row["subject_type"]),
            subject_label=labels.get((str(row["subject_type"]), UUID(str(row["subject_id"])))),
            contract_external_id=support.text(row["contract_external_id"]),
            book=support.text(row["book_code"]),
            conclusion=str(row["conclusion"]),
            codification_refs=tuple(str(value) for value in row["codification_refs"] or ()),
            created_by=(
                support.uuid_of(row["created_by"]),
                str(support.text(row["created_by_kind"])),
            ),
            reviewer_id=support.uuid_of(row["reviewer_id"]),
            status=str(support.text(row["status"])),
            reviewed_at=row["reviewed_at"],
            supersedes_no=(
                None
                if row["supersedes_id"] is None
                else numbers.get(UUID(str(row["supersedes_id"])))
            ),
        )
        for row in kept
    ]


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    first, last = support.date_range(session, params, today=True)
    bounds, book_code = support.instants(first, last), tie_outs.book_of(session, params)
    found = sources(uow, params, bounds=bounds, book_code=book_code)
    names = approval_queries.display_names(
        session, [value for item in found for value in (item.created_by[0], item.reviewer_id)]
    )
    rows, totals = dataset_rows(found, names)
    withheld = withheld_count(uow, params, bounds=bounds, book_code=book_code)
    totals["record_count"] = len(rows) + withheld
    totals["from_date"], totals["to_date"] = first.isoformat(), last.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "Source",
    "build",
    "dataset_rows",
    "sources",
    "subject_labels",
    "withheld_count",
]
