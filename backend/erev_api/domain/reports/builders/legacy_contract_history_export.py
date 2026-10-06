"""RPT-10 ``legacy_contract_history_export`` Legacy contract history export (SCREENS_B §5.6.2
RPT-10; 04 §17.1, §17.2; D-12, D-33; legacy 06 §7.3 TC-REP-01, TC-REP-02, TC-REP-04 to TC-REP-06,
P-REP-01; PRD J-15.8; 03 REQ-RPT-012; BUILD_SPEC RPS-5).

Rows: the RPT-09 population of the ``ASC606`` book (04 §17.1) effective from ``from_date`` to
``to_date``, ordered by contract external id, the version's number along the contract's chain
(``contract_history.chain_numbers``) and ``line_sequence``. Each row is
``legacy_columns.legacy_row``: exactly the 71 ``Contract_Live`` names in legacy order, as headers
and as row keys, with no index column (rules 1 to 4 and 6). ``Current Contract Position - Contract
Level`` is billing − revenue (D-12, D-33). D-98 candidate 89 (04 §17.1 rule 4 rev
1.66): the six exact columns carry ``exact_sources`` texts from each row's own contract
version's trace. Row key ``version:<external id>:<version no>:<obligation key>`` with the number
along the chain, as RPT-09. Control totals ``row_count``, ``from_date`` and ``to_date``; no totals
and no tie-out.
"""

from __future__ import annotations

from typing import Any, Final

from erev_api.domain.reports import exact_sources, legacy_columns
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_history as history
from erev_api.domain.reports.outputs import ReportData
from erev_api.uow import UnitOfWork

CODE: Final = "legacy_contract_history_export"


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    from_date, to_date = history.date_range(session, params, year=True)
    rows = history.population(
        session,
        params,
        book_code=legacy_columns.BOOK,
        where=history.history_where(from_date, to_date),
    )
    previous = history.previous_versions(session, rows)
    # D-98 candidate 89 (04 §17.1 rules 4 and 4a rev 1.75): the exact trace-sourced texts of the
    # six exact columns and the exact activity (LM-CL-55: the posted node's own companion, or the
    # `unavailable` literal), from each row's OWN contract version's stored trace (previous rows
    # included); any missing source refuses the whole run by name
    exact_sources.attach_exact_texts(session, [*rows, *previous.values()])
    items: list[dict[str, Any]] = [
        {
            "row_key": (
                f"version:{row['contract_external_id']}:{row['chain_version_no']}"
                f":{row['obligation_key']}"
            ),
            **legacy_columns.legacy_row(row, history.previous_of(previous, row)),
        }
        for row in rows
    ]
    return ReportData(
        columns=legacy_columns.COLUMNS,
        rows=tuple(items),
        control_totals={
            "row_count": len(items),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        },
    )
