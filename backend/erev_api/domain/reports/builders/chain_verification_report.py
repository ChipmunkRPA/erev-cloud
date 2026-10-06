"""RPT-44 ``chain_verification_report`` Audit chain verification report (SCREENS_B §5.6.5 RPT-44,
§6.4 SF-09:verification; 04 T-PLT-23, §15.3 API-R-10, E-98; dev-guide DG-KRN-AUD-07, DG-TST-22;
D-43; PRD J-17.5; 03 REQ-PLT-020; research 07 AU-03, A-19; CTL-039; BUILD_SPEC RPS-10).

One row per audit chain verification (T-PLT-23) finished from ``from`` (inclusive; default: 30
days before the run's ``known_at``) to ``to`` (exclusive; without it the report ends at the run's
record cutoff, "now"), in finishing order; ``row_key`` ``verification:<finished_at>`` with the
instant in the canonical form ``YYYY-MM-DDTHH:MM:SS.ffffffZ``. Two verifications that finished at
the same instant keep distinct keys: the later one (by start, then id) carries ``:2``, and so on.

``trigger`` is ``SCHEDULED`` or ``ON_DEMAND`` (the grid shows "Scheduled", "On demand");
``result`` the E-98 literal; ``first_failure_seq`` the sequence a ``FAIL`` stops at;
``digest_last_hmac`` the last chain value the verification confirmed — of the last event for a
``PASS``, of the event before the failing one for a ``FAIL`` (empty when the first event fails);
``digest_file_id`` the id of the digest file of a ``PASS`` (a ``FAIL`` stores none). T-PLT-23 is
append-only, so a report as of an earlier ``known_at`` states exactly the verifications finished
by then.

Control totals ``verification_count``, ``failure_count`` (``FAIL`` rows) and the range applied
(``from``; ``to`` when given).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import ColumnElement, select

from erev_api.db.tables import audit_chain_verification
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData, utc_text
from erev_api.enums import ControlResult
from erev_api.uow import UnitOfWork

CODE: Final = "chain_verification_report"
ROW_KEY_PREFIX: Final = "verification:"  # RPT-44: row_key `verification:<finished_at ISO>`
START_AFTER_END: Final = "Start must be on or before end."
DEFAULT_WINDOW: Final = timedelta(days=30)  # SCREENS_B RPT-44 "30 days before now"
FAIL: Final = ControlResult.FAIL.value
COLUMNS: Final = (
    Column("finished_at", "Finished", "timestamp"),
    Column("trigger", "Trigger", "code"),
    Column("from_chain_seq", "From sequence", "integer"),
    Column("to_chain_seq", "To sequence", "integer"),
    Column("events_checked", "Events checked", "integer"),
    Column("result", "Result", "code"),
    Column("first_failure_seq", "First failure", "integer"),
    Column("digest_last_hmac", "Last chain value", "code"),
    Column("digest_file_id", "Digest", "code"),
)


def instant_text(moment: datetime) -> str:
    """``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (DG-KRN-CAN). Pure."""
    return canonical_bytes(moment).decode("utf-8")[1:-1]


def dataset_rows(
    found: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in finishing order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    failures = 0
    ordered = sorted(found, key=lambda row: (row["finished_at"], row["started_at"], str(row["id"])))
    for row in ordered:
        key = f"{ROW_KEY_PREFIX}{instant_text(row['finished_at'])}"
        seen[key] = seen.get(key, 0) + 1
        result = str(support.text(row["result"]))
        failures += 1 if result == FAIL else 0
        first_failure = row["first_failure_seq"]
        rows.append(
            {
                "row_key": key if seen[key] == 1 else f"{key}:{seen[key]}",
                "finished_at": row["finished_at"],
                "trigger": str(row["trigger"]),
                "from_chain_seq": int(row["from_chain_seq"]),
                "to_chain_seq": int(row["to_chain_seq"]),
                "events_checked": int(row["events_checked"]),
                "result": result,
                "first_failure_seq": None if first_failure is None else int(first_failure),
                "digest_last_hmac": support.text(row["digest_last_hmac"]),
                "digest_file_id": support.text(row["digest_file_id"]),
            }
        )
    return rows, {"verification_count": len(rows), "failure_count": failures}


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    given_from, end = support.instant(params, "from"), support.instant(params, "to")
    start = params.known_at - DEFAULT_WINDOW if given_from is None else given_from
    if end is not None and start > end:
        raise tie_outs.invalid("from", START_AFTER_END)
    where: list[ColumnElement[bool]] = [
        audit_chain_verification.c.finished_at >= start,
        audit_chain_verification.c.finished_at <= cutoff,
    ]
    if end is not None:
        where.append(audit_chain_verification.c.finished_at < end)
    found = session.execute(select(audit_chain_verification).where(*where)).mappings()
    rows, totals = dataset_rows(dict(row) for row in found)
    totals["from"] = utc_text(start)
    if end is not None:
        totals["to"] = utc_text(end)
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = ["CODE", "COLUMNS", "DEFAULT_WINDOW", "build", "dataset_rows", "instant_text"]
