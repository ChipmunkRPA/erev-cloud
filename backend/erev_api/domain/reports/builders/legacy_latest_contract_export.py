"""RPT-12 ``legacy_latest_contract_export`` Legacy latest contract export (SCREENS_B §5.6.2 RPT-12;
04 §17.1, §17.2; D-12, D-33; legacy 06 §7.3 TC-REP-03, P-REP-02, FX-15; PRD J-21.6, WLD-X-28;
03 REQ-RPT-013; BUILD_SPEC RPS-5).

Rows: the RPT-11 row rule at ``as_of`` over the ``ASC606`` book (04 §17.1), one row per obligation
of each combination group's latest contract version effective on or before ``as_of``. Columns and
formats are the RPT-10 rules: the 71 ``Contract_Live`` names in legacy order as headers and row
keys, no index column (REQ-RPT-013). Row key ``obligation:<external id>:<obligation key>``. Control
totals ``row_count`` and ``as_of``; no totals and no tie-out.
"""

from __future__ import annotations

from typing import Any, Final

from erev_api.domain.reports import exact_sources, legacy_columns
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_history as history
from erev_api.domain.reports.builders import latest_contract_status as latest
from erev_api.domain.reports.outputs import ReportData
from erev_api.uow import UnitOfWork

CODE: Final = "legacy_latest_contract_export"


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    as_of = latest.as_of_date(session, params)
    rows = latest.latest_rows(session, params, book_code=legacy_columns.BOOK)
    previous = history.previous_versions(session, rows)
    # D-98 candidate 89 (04 §17.1 rules 4 and 4a rev 1.75): the exact trace-sourced texts of the
    # six exact columns and the exact activity (LM-CL-55: the posted node's own companion, or the
    # `unavailable` literal), from each row's OWN contract version's stored trace (previous rows
    # included); any missing source refuses the whole run by name
    exact_sources.attach_exact_texts(session, [*rows, *previous.values()])
    items: list[dict[str, Any]] = [
        {
            "row_key": f"obligation:{row['contract_external_id']}:{row['obligation_key']}",
            **legacy_columns.legacy_row(row, history.previous_of(previous, row)),
        }
        for row in rows
    ]
    return ReportData(
        columns=legacy_columns.COLUMNS,
        rows=tuple(items),
        control_totals={"row_count": len(items), "as_of": as_of.isoformat()},
    )
