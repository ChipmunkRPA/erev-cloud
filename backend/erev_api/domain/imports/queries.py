"""API-R-43 read models: imports, rows and the error report (04 §16.6 API-S-Import, API-S-ImportRow,
error report; T-IMP-02 to T-IMP-05; 05 UPL-20; BUILD_SPEC DIN-1).

``finding_counts`` groups the upload's exception items by code and finding severity (E-43 inverse)
with the number of distinct rows; file-level findings count 0 rows. ``header_match`` is empty for
``LEGACY_V1`` uploads, and CSV v2 uploads wait for mapping profiles (DIN-10).

[J] L4-1-Q-33: the error report lists every ``ERROR`` and ``WARNING`` message of the upload, the
file-level ones first with blank row and column, then by row number and the template's column
order. Text cells pass the UPL-20 apostrophe rule.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Select, Text, and_, case, cast, distinct, exists, func, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    exception_item,
    file_object,
    import_row,
    import_row_lineage,
    import_template,
    import_upload,
)
from erev_api.domain.imports import scope, templates
from erev_api.domain.platform import approval_queries
from erev_api.enums import ImportRowStatus
from erev_api.problems import Problem
from erev_api.schemas.imports import (
    FindingCountOut,
    ImportCountsOut,
    ImportFileOut,
    ImportOut,
    ImportRowLineageOut,
    ImportRowMessageOut,
    ImportRowOut,
    ImportTemplateRefOut,
)

__all__ = [
    "ERROR_REPORT_COLUMNS",
    "error_report",
    "get_import",
    "import_outs",
    "imports_statement",
    "read",
    "readable",
    "row_outs",
    "rows_statement",
]

EXCEPTIONS_HREF: Final = "/api/v1/exceptions?import_upload_id={import_id}"
ERROR_REPORT_COLUMNS: Final = ("row", "column", "rule_id", "message")
# E-43 inverse: exception severity → finding severity.
FINDING_SEVERITY: Final[Mapping[str, str]] = {
    "BLOCKING": "ERROR",
    "WARNING": "WARNING",
    "INFO": "INFO",
}
REPORTED_SEVERITIES: Final = ("BLOCKING", "WARNING")
# D-87 L6-4-Q-14: rows ``sort=severity`` lists ERROR, WARNING, VALID, AGGREGATED, then BLANK rows,
# and rows of one status by row number. The key is rank × span + row number, where the span exceeds
# any row number (50,000 data rows per sheet), so one integer column keeps the keyset cursor
# (API-C-09).
ROW_SEVERITY_ORDER: Final = (
    ImportRowStatus.ERROR.value,
    ImportRowStatus.WARNING.value,
    ImportRowStatus.VALID.value,
    ImportRowStatus.AGGREGATED.value,
    ImportRowStatus.BLANK.value,
)
ROW_SEVERITY_SPAN: Final = 1_000_000
ROW_SEVERITY: Final = (
    case(
        {status: rank for rank, status in enumerate(ROW_SEVERITY_ORDER)},
        value=cast(import_row.c.status, Text),
        else_=len(ROW_SEVERITY_ORDER),
    )
    * ROW_SEVERITY_SPAN
    + import_row.c.row_number
).label("severity_rank")


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """Run ``fn`` in a read-only tenant session of the caller (DG-CMD-13)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def imports_statement(reader: Principal) -> Select[Any]:
    """``GET /imports``: the uploads ``reader`` may read (04 API-R-43 rev 1.107; rulings R-28, R-29
    — its own, and those whose every named entity its ``contract.read`` scope covers); the list
    filters apply through the resource's ``ListSpec``."""
    return select(import_upload).where(scope.visible(reader))


def _template_names(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[tuple[str, int], str]:
    codes = sorted({str(row["template_code"]) for row in rows})
    if not codes:
        return {}
    statement = select(
        import_template.c.code, import_template.c.version, import_template.c.name
    ).where(import_template.c.code.in_(codes))
    return {
        (str(code), int(version)): str(name) for code, version, name in session.execute(statement)
    }


def _files(session: Session, rows: Sequence[Mapping[str, Any]]) -> dict[UUID, Mapping[str, Any]]:
    ids = sorted({UUID(str(row["file_object_id"])) for row in rows})
    if not ids:
        return {}
    statement = select(
        file_object.c.id,
        file_object.c.original_filename,
        file_object.c.sha256,
        file_object.c.size_bytes,
    ).where(file_object.c.id.in_(ids))
    return {UUID(str(found["id"])): dict(found) for found in session.execute(statement).mappings()}


def _row_status_counts(session: Session, ids: Sequence[UUID]) -> dict[tuple[UUID, str], int]:
    if not ids:
        return {}
    statement = (
        select(import_row.c.import_upload_id, import_row.c.status, func.count())
        .where(
            import_row.c.import_upload_id.in_(ids),
            import_row.c.status.in_(
                [ImportRowStatus.AGGREGATED.value, ImportRowStatus.BLANK.value]
            ),
        )
        .group_by(import_row.c.import_upload_id, import_row.c.status)
    )
    return {
        (UUID(str(upload_id)), _text(status)): int(count)
        for upload_id, status, count in session.execute(statement)
    }


def _finding_counts(session: Session, ids: Sequence[UUID]) -> dict[UUID, list[FindingCountOut]]:
    found: dict[UUID, list[FindingCountOut]] = {upload_id: [] for upload_id in ids}
    if not ids:
        return found
    statement = (
        select(
            exception_item.c.import_upload_id,
            exception_item.c.code,
            exception_item.c.severity,
            func.count(distinct(exception_item.c.import_row_id)),
        )
        .where(exception_item.c.import_upload_id.in_(ids))
        .group_by(
            exception_item.c.import_upload_id, exception_item.c.code, exception_item.c.severity
        )
        .order_by(exception_item.c.code, exception_item.c.severity)
    )
    for upload_id, code, severity, count in session.execute(statement):
        found[UUID(str(upload_id))].append(
            FindingCountOut.model_validate(
                {"code": code, "severity": FINDING_SEVERITY[_text(severity)], "rows": int(count)}
            )
        )
    return found


def import_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[ImportOut]:
    """API-S-Import of each ``import_upload`` row."""
    ids = [UUID(str(row["id"])) for row in rows]
    names = _template_names(session, rows)
    files = _files(session, rows)
    statuses = _row_status_counts(session, ids)
    findings = _finding_counts(session, ids)
    actors = approval_queries.display_names(session, [row["created_by"] for row in rows])
    outs: list[ImportOut] = []
    for row in rows:
        upload_id = UUID(str(row["id"]))
        code, version = str(row["template_code"]), int(row["template_version"])
        stored = files[UUID(str(row["file_object_id"]))]
        outs.append(
            ImportOut(
                id=upload_id,
                import_no=str(row["import_no"]),
                template=ImportTemplateRefOut(
                    code=code, version=version, name=names[(code, version)]
                ),
                file=ImportFileOut(
                    id=stored["id"],
                    original_filename=stored["original_filename"],
                    sha256=str(stored["sha256"]).strip(),
                    size_bytes=int(stored["size_bytes"]),
                ),
                parameters=dict(row["parameters"] or {}),
                status=row["status"],
                counts=ImportCountsOut(
                    rows=row["row_count"],
                    valid=row["valid_row_count"],
                    warnings=row["warning_count"],
                    errors=row["error_count"],
                    aggregated=statuses.get((upload_id, ImportRowStatus.AGGREGATED.value), 0),
                    blank=statuses.get((upload_id, ImportRowStatus.BLANK.value), 0),
                ),
                is_quarantine_mode=bool(row["is_quarantine_mode"]),
                control_totals=row["control_totals"],
                finding_counts=findings[upload_id],
                header_match=[],
                diff_summary=row["diff_summary"],
                approval_request_id=row["approval_request_id"],
                committed_at=row["committed_at"],
                exceptions_href=EXCEPTIONS_HREF.format(import_id=upload_id),
                created_by=approval_queries.actor(
                    row["created_by"], _text(row["created_by_kind"]), actors
                ),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
    return outs


def _upload(
    session: Session, import_id: UUID, reader: Principal | None = None
) -> Mapping[str, Any]:
    row = (
        session.execute(select(import_upload).where(import_upload.c.id == import_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    found = dict(row)
    if reader is not None:
        scope.require_visible(reader, found)
    return found


def readable(session: Session, import_id: UUID, reader: Principal) -> Mapping[str, Any]:
    """The upload row for a read by ``reader``; 404 ``not-found`` when it is absent or names an
    entity outside ``reader``'s ``contract.read`` scope — one answer for both (REQ-PLT-012)."""
    return _upload(session, import_id, reader)


def get_import(session: Session, import_id: UUID, reader: Principal | None = None) -> ImportOut:
    """``GET /imports/{id}``; 404 ``not-found`` when absent or not visible to ``reader``. A command
    answering its own upload passes no reader."""
    (item,) = import_outs(session, [_upload(session, import_id, reader)])
    return item


def rows_statement(import_id: UUID, *, codes: Sequence[str] = ()) -> Select[Any]:
    """``GET /imports/{id}/rows``; ``code`` keeps rows with a message of one of ``codes``. The
    statement also selects the ``severity`` sort key (``ROW_SEVERITY``)."""
    statement = select(import_row, ROW_SEVERITY).where(import_row.c.import_upload_id == import_id)
    if codes:
        statement = statement.where(
            exists(
                select(exception_item.c.id).where(
                    exception_item.c.import_row_id == import_row.c.id,
                    exception_item.c.code.in_(list(codes)),
                )
            )
        )
    return statement


def row_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[ImportRowOut]:
    """API-S-ImportRow of each ``import_row`` row, with its messages and lineage."""
    ids = [UUID(str(row["id"])) for row in rows]
    messages: dict[UUID, list[ImportRowMessageOut]] = {row_id: [] for row_id in ids}
    lineage: dict[UUID, list[ImportRowLineageOut]] = {row_id: [] for row_id in ids}
    if ids:
        items = session.execute(
            select(
                exception_item.c.import_row_id,
                exception_item.c.code,
                exception_item.c.severity,
                exception_item.c.field,
                exception_item.c.message,
            )
            .where(exception_item.c.import_row_id.in_(ids))
            .order_by(exception_item.c.created_at, exception_item.c.exception_no)
        )
        for row_id, code, severity, field, message in items:
            messages[UUID(str(row_id))].append(
                ImportRowMessageOut.model_validate(
                    {
                        "rule_id": code,
                        "severity": FINDING_SEVERITY[_text(severity)],
                        "field": field,
                        "message": message,
                    }
                )
            )
        emitted = session.execute(
            select(
                import_row_lineage.c.import_row_id,
                import_row_lineage.c.target_type,
                import_row_lineage.c.target_id,
            )
            .where(import_row_lineage.c.import_row_id.in_(ids))
            .order_by(import_row_lineage.c.created_at, import_row_lineage.c.id)
        )
        for row_id, target_type, target_id in emitted:
            lineage[UUID(str(row_id))].append(
                ImportRowLineageOut(target_type=target_type, target_id=target_id)
            )
    return [
        ImportRowOut(
            id=row["id"],
            sheet_name=str(row["sheet_name"]),
            row_number=int(row["row_number"]),
            status=row["status"],
            business_key=row["business_key"],
            raw=dict(row["raw"]),
            normalized=None if row["normalized"] is None else dict(row["normalized"]),
            messages=messages[UUID(str(row["id"]))],
            aggregated_into_row_id=row["aggregated_into_row_id"],
            lineage=lineage[UUID(str(row["id"]))],
        )
        for row in rows
    ]


def error_report(session: Session, import_id: UUID, reader: Principal) -> tuple[str, str]:
    """``GET /imports/{id}/error-report``: the import number and the CSV text (RFC 4180)."""
    upload = _upload(session, import_id, reader)
    template = templates.find_template(
        session, str(upload["template_code"]), int(upload["template_version"])
    )
    order = (
        {}
        if template is None
        else {name: index for index, name in enumerate(templates.header_names(template))}
    )
    statement = (
        select(
            exception_item.c.field,
            exception_item.c.code,
            exception_item.c.message,
            import_row.c.row_number,
        )
        .select_from(
            exception_item.outerjoin(
                import_row,
                and_(
                    import_row.c.tenant_id == exception_item.c.tenant_id,
                    import_row.c.id == exception_item.c.import_row_id,
                ),
            )
        )
        .where(
            exception_item.c.import_upload_id == import_id,
            exception_item.c.severity.in_(REPORTED_SEVERITIES),
        )
    )
    entries = sorted(
        session.execute(statement).tuples(),
        key=lambda entry: (
            -1 if entry[3] is None else int(entry[3]),
            order.get(str(entry[0]), len(order)) if entry[0] is not None else -1,
            str(entry[1]),
        ),
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(ERROR_REPORT_COLUMNS)
    for field, code, message, row_number in entries:
        writer.writerow(
            [
                "" if row_number is None else str(row_number),
                "" if field is None else templates.safe_text(str(field)),
                str(code),
                templates.safe_text(str(message)),
            ]
        )
    return str(upload["import_no"]), buffer.getvalue()
