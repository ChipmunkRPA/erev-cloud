"""RPT-43 ``audit_log_export`` Audit log export (SCREENS_B §5.6.5 RPT-43, §6.3 SF-09:audit-log;
04 T-PLT-19, §15.3 API-R-10; dev-guide DG-KRN-AUD-05, DG-KRN-AUD-06, DG-KRN-CAN; PRD J-17.5; 03
REQ-PLT-018, REQ-PLT-019; research 07 AU-01, A-19; BUILD_SPEC RPS-10).

One row per audit event of the workspace in ``chain_seq`` order; ``row_key``
``event:<chain_seq>``. The columns are every T-PLT-19 column but ``tenant_id``, in table order,
with the column names as headers. The filters are those of the audit log (API-R-10):
``object_type``, ``object_id``, ``actor_id`` and ``action`` match exactly; ``outcome`` keeps the
events of any of the E-81 literals given; ``from`` is inclusive and ``to`` exclusive on
``occurred_at``. Without ``to`` the export ends at the run's record cutoff ("now"); events after
the cutoff are never read. T-PLT-19 is append-only, so an export as of an earlier ``known_at``
states exactly the events that had occurred by then.

``contract_id`` (item RPT-43-PARAMS-1; 04 §16.14, T-PLT-48): the trail of that contract — every
event that names it, whatever its object type — read by the statement the audit log's list reads
it by (``audit_log.trail_source``), and narrowed by the other filters as the list narrows it. An
export under the filters of the list therefore states the rows of the list up to its cutoff; like
the list it reads the trail whole when no range is given. A contract no event names gives no rows.

- ``occurred_at`` is text in the canonical form ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (ISO 8601 UTC
  with microseconds; DG-KRN-CAN), the form the event's HMAC covers.
- ``before``, ``after``, ``diff`` and ``detail`` are canonical JSON strings. Credential keys are
  redacted when an event is recorded; the export passes each value through ``audit.redact`` again,
  so a key of ``erev_api.audit.REDACT`` never leaves in clear. An absent value is an empty cell.
- ``actor_roles`` is the list of role codes; ids are text.

Control totals (the manifest of a CSV output): ``row_count``, ``first_chain_seq``,
``last_chain_seq`` and ``last_hmac`` of the exported rows; the last three are empty for an export
without rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import ColumnElement, Select, select

from erev_api.audit.redact import redact
from erev_api.db.tables import audit_event
from erev_api.domain.platform import audit_log
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ColumnKind, ReportData
from erev_api.uow import UnitOfWork

CODE: Final = "audit_log_export"
ROW_KEY_PREFIX: Final = "event:"  # RPT-43: row_key `event:<chain_seq>`
START_AFTER_END: Final = "Start must be on or before end."
JSON_COLUMNS: Final = ("before", "after", "diff", "detail")
# T-PLT-19 in table order (SCREENS_B RPT-43): column name → cell kind.
KINDS: Final[tuple[tuple[str, ColumnKind], ...]] = (
    ("chain_seq", "integer"),
    ("occurred_at", "text"),
    ("id", "code"),
    ("actor_id", "code"),
    ("actor_kind", "code"),
    ("actor_roles", "codes"),
    ("auth_method", "code"),
    ("mfa_verified", "boolean"),
    ("on_behalf_of_id", "code"),
    ("api_client_id", "code"),
    ("support_grant_id", "code"),
    ("source_ip", "code"),
    ("request_id", "code"),
    ("action", "code"),
    ("object_type", "code"),
    ("object_id", "code"),
    ("object_version", "text"),
    ("before", "text"),
    ("after", "text"),
    ("diff", "text"),
    ("reason_code", "code"),
    ("comment", "text"),
    ("approval_request_id", "code"),
    ("outcome", "code"),
    ("detail", "text"),
    ("prev_hmac", "code"),
    ("hmac", "code"),
    ("hmac_key_id", "code"),
)
COLUMNS: Final = tuple(Column(name, name, kind) for name, kind in KINDS)
FIELDS: Final = tuple(name for name, _ in KINDS)


def canonical_text(value: Any) -> str:
    """The canonical JSON of ``value`` as text (DG-KRN-CAN)."""
    return canonical_bytes(value).decode("utf-8")


def cell(name: str, value: Any) -> Any:
    """The export value of one T-PLT-19 column. Pure."""
    if value is None:
        return None
    if name in JSON_COLUMNS:
        return canonical_text(redact(value))
    if name == "occurred_at":
        return canonical_text(value)[1:-1]
    if name == "chain_seq":
        return int(value)
    if name == "mfa_verified":
        return bool(value)
    if name == "actor_roles":
        return tuple(str(item) for item in value)
    return str(support.text(value))


def dataset_rows(
    events: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in chain order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: int(item["chain_seq"])):
        row: dict[str, Any] = {"row_key": f"{ROW_KEY_PREFIX}{int(event['chain_seq'])}"}
        for name in FIELDS:
            row[name] = cell(name, event[name])
        rows.append(row)
    return rows, {
        "row_count": len(rows),
        "first_chain_seq": rows[0]["chain_seq"] if rows else None,
        "last_chain_seq": rows[-1]["chain_seq"] if rows else None,
        "last_hmac": rows[-1]["hmac"] if rows else None,
    }


# The log as a whole is filtered and ordered by the table's own columns.
_TABLE_COLUMNS: Final[Mapping[str, ColumnElement[Any]]] = MappingProxyType(
    {column.name: column for column in audit_event.c}
)


def filters(
    params: ReportParams,
    *,
    cutoff: datetime,
    columns: Mapping[str, ColumnElement[Any]] = _TABLE_COLUMNS,
) -> list[ColumnElement[bool]]:
    """The API-R-10 filters of the run with the record cutoff, on the columns of the read (the
    table's, or those of a contract's trail); 422 for a start after its end."""
    start, end = support.instant(params, "from"), support.instant(params, "to")
    if start is not None and end is not None and start > end:
        raise tie_outs.invalid("from", START_AFTER_END)
    where: list[ColumnElement[bool]] = [columns["occurred_at"] <= cutoff]
    if start is not None:
        where.append(columns["occurred_at"] >= start)
    if end is not None:
        where.append(columns["occurred_at"] < end)
    given = params.parameters
    if given.get("object_type") is not None:
        where.append(columns["object_type"] == str(given["object_type"]))
    if given.get("object_id") is not None:
        where.append(columns["object_id"] == UUID(str(given["object_id"])))
    if given.get("actor_id") is not None:
        where.append(columns["actor_id"] == UUID(str(given["actor_id"])))
    if given.get("action") is not None:
        where.append(columns["action"] == str(given["action"]))
    outcomes = given.get("outcome")
    if outcomes:  # none given, or an empty list, reads every outcome — as the list does
        where.append(columns["outcome"].in_(sorted({str(value) for value in outcomes})))
    return where


def events_statement(params: ReportParams, *, cutoff: datetime) -> Select[Any]:
    """The T-PLT-19 columns of the run's events in chain order: the log as a whole, or with
    ``contract_id`` the trail of that contract as the audit log's list reads it (module
    docstring)."""
    contract_id = params.parameters.get("contract_id")
    if contract_id is None:
        columns = _TABLE_COLUMNS
        read = select(*(columns[name] for name in FIELDS))
    else:
        source = audit_log.trail_source(UUID(str(contract_id)))
        columns = source.columns
        read = source.statement.with_only_columns(*(columns[name].label(name) for name in FIELDS))
    return read.where(*filters(params, cutoff=cutoff, columns=columns)).order_by(
        columns["chain_seq"]
    )


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    statement = events_statement(params, cutoff=cutoff)
    rows, totals = dataset_rows(dict(row) for row in session.execute(statement).mappings())
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "FIELDS",
    "JSON_COLUMNS",
    "build",
    "canonical_text",
    "cell",
    "dataset_rows",
    "events_statement",
    "filters",
]
