"""RPT-07 ``rpo_rollforward`` RPO rollforward (SCREENS_B §5.6.1 RPT-07; ENGINE_SPEC_B §15.2.3
S15-R-12; research 04 V9; 03 REQ-RPT-010; CTL-030; BUILD_SPEC RPS-4).

The lines of each contract come from ``rpo.rollforward_lines`` over each entity's range: from the
day before ``from_period_key`` to the end of ``to_period_key``. Section 1 "Rollforward" gives one
row per line code (``<line>:<ISO>`` with several currencies) with the money field ``rpo``; section
2 "By contract" one row ``contract:<external id>`` per contract and currency with a money field per
line.
Control totals: opening, closing and unexplained per currency.

Tie-outs: ``TO_ROLLFORWARD_BALANCES`` passes when every unexplained difference is 0 (opening plus
movements equals closing; V9), and ``TO_RPO_ROLLFORWARD_EQ_RPO`` compares the closing with the RPO
report total at the range end.

R-RC-1 (L6-3-Q-18): without modification CR-MARROWBY-2026-09 (CTR-17 post-rc) the K-02 test shows
no modification movement; the openings are restated from the versions, since lock snapshots are
CLO-6.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_api.domain.reports import rpo_currency, rpo_rollforward_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams, rpo
from erev_api.domain.reports.builders import contract_balance_rollforward as balances
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, add
from erev_api.uow import UnitOfWork

CODE: Final = "rpo_rollforward"
LABELS: Final[Mapping[str, str]] = {
    "OPENING": "Opening RPO",
    "NEW_CONTRACTS": "New contracts",
    "MODIFICATIONS": "Modifications",
    "VC_ESTIMATE_CHANGES": "Variable consideration estimate changes",
    "EXEMPTIONS": "Disclosure exemption changes",
    "LATE_EVENTS": "Late events",
    "REVENUE": "Revenue recognized",
    "CANCELLATIONS": "Cancellations and terminations",
    "FX": "FX",
    "ROUNDING": "Currency rounding",
    "UNEXPLAINED": "Unexplained difference",
    "CLOSING": "Closing RPO",
}
COLUMNS: Final = (
    Column("section", "Section", "integer"),
    # D-98 85 (CLO-7c): the stable line code is the row's identity in the frozen dataset; the label
    # is a display attribute.
    Column("line_code", "Line code", "code"),
    Column("line_label", "Line", "text"),
    Column("rpo", "RPO", "money"),
    Column("contract_external_id", "Contract", "code"),
    Column("currency", "Currency", "code"),
    *(Column(line.lower(), LABELS[line], "money") for line in rpo.ROLLFORWARD_LINES),
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, before = balances.ranges(session, params)
    view = str(params.parameters.get("currency_view") or "transaction")
    converted = view != "transaction"
    codes = (
        ("OPENING", *rpo.MOVEMENTS, "ROUNDING", "UNEXPLAINED", "CLOSING")
        if converted
        else rpo.ROLLFORWARD_LINES
    )
    movements = (*rpo.MOVEMENTS, "ROUNDING") if converted else rpo.MOVEMENTS
    ranges: dict[UUID, tuple[date, date]] = {
        entity.id: (periods[entity.id][0].start - timedelta(days=1), periods[entity.id][-1].end)
        for entity in found
        if periods[entity.id]
    }
    cutoff = tie_outs.cutoff_for(session, params)
    store = rpo.load(
        session, entity_ids=params.entity_ids, book_code=book_code, cutoff=cutoff, params=params
    )
    addition_evidence = "rpo_added_obligations_v1"
    store = replace(
        store,
        classify_added_obligations=(
            params.binding is None or addition_evidence in params.binding.evidence
        ),
    )
    if store.classify_added_obligations and params.sources is not None:
        params.sources.record_evidence(addition_evidence, True)
    cancellation_evidence = "rpo_cancelled_changes_v1"
    store = replace(
        store,
        classify_cancelled_changes=(
            params.binding is None or cancellation_evidence in params.binding.evidence
        ),
    )
    if store.classify_cancelled_changes and params.sources is not None:
        params.sources.record_evidence(cancellation_evidence, True)
    applied = rpo.applied_expedients(session, found, book_code=book_code, known_at=params.known_at)
    # S15-R-08 (rev 1.127): the opening, the closing and the revenue between them are read at
    # their dates
    rpo.measure(
        session,
        store,
        {
            entity_id: tuple(day for p in selected for day in (p.start - timedelta(days=1), p.end))
            for entity_id, selected in periods.items()
        }
        if converted
        else ranges,
        applied=applied,
        uow=uow,
        book_code=book_code,
        params=params,
    )
    items = rpo.rollforward_lines(store, ranges=ranges, applied=applied)
    exemption_evidence = "rpo_exemption_details_v1"
    include_exemptions = params.binding is None or exemption_evidence in params.binding.evidence
    exemption_changes = [dict(detail) for item in items for detail in item.exemption_changes]
    if include_exemptions and params.sources is not None:
        params.sources.record_evidence(exemption_evidence, True)
    rates: list[dict[str, Any]] = []
    source_unexplained = False
    exemption_translation: list[dict[str, str]] = []
    translation_evidence = "rpo_exemption_translation_v1"
    include_translation = converted and (
        params.binding is None or translation_evidence in params.binding.evidence
    )
    if include_translation and params.sources is not None:
        params.sources.record_evidence(translation_evidence, True)
    if converted:
        items, rates, source_unexplained, exemption_translation = rpo_rollforward_currency.project(
            uow, params, store, found, periods, before, applied
        )
    totals: dict[str, dict[str, Decimal]] = {}
    for item in items:
        into = totals.setdefault(item.currency, dict.fromkeys(codes, ZERO))
        for line in codes:
            into[line] += item.lines[line]
    rows: list[dict[str, Any]] = []
    mixed = len(totals) > 1
    for currency, lines in sorted(totals.items()):
        for line in codes:
            rows.append(
                {
                    "row_key": f"{line}:{currency}" if mixed else line,
                    "section": 1,
                    "line_code": line,
                    "line_label": "RPO currency translation"
                    if converted and line == "FX"
                    else LABELS[line],
                    # 04 T-CLS-05 dataset identity (D-98 85): a line row is identified by its
                    # line code and currency; the contract column is stated EMPTY, never left
                    # out — the lock freeze reads every key column by name (S15-R-18).
                    "contract_external_id": None,
                    "currency": currency,
                    "rpo": tie_outs.money(lines[line], currency),
                }
            )
    for item in items:
        rows.append(
            {
                "row_key": f"contract:{item.external_id}" + (f":{item.currency}" if mixed else ""),
                "section": 2,
                # a by-contract row is identified by its contract and currency: no line code
                "line_code": None,
                "contract_external_id": item.external_id,
                "currency": item.currency,
                **{line.lower(): tie_outs.money(item.lines[line], item.currency) for line in codes},
            }
        )
    expected: dict[str, Decimal] = {}
    actual: dict[str, Decimal] = {}
    unexplained = source_unexplained
    for currency, lines in totals.items():
        add(expected, currency, lines["CLOSING"])
        add(
            actual,
            currency,
            lines["OPENING"] + sum((lines[code] for code in movements), ZERO),
        )
        unexplained = unexplained or any(item.lines["UNEXPLAINED"] != 0 for item in items)
    balanced = tie_outs.compared(tie_outs.TO_ROLLFORWARD_BALANCES, expected, actual)
    if unexplained:
        balanced["result"] = tie_outs.FAIL
    report_total: dict[str, Decimal] = {}
    bands = tuple(params.parameters.get("time_bands") or rpo.DEFAULT_BANDS)
    at_end = {entity_id: value[1] for entity_id, value in ranges.items()}
    closing_rows = rpo.rows_at(store, as_of=at_end, bands=bands, applied=applied)
    if converted:
        closing_rows = tuple(item for item in closing_rows if item.exemption is None)
        closing_rows, _ = rpo_currency.translate(
            session,
            params,
            closing_rows,
            found,
            {entity_id: selected[-1] for entity_id, selected in periods.items() if selected},
        )
    for found_item in closing_rows:
        if found_item.exemption is None:
            add(report_total, found_item.ob.currency, found_item.total)
    return ReportData(
        columns=(*COLUMNS[:-2], Column("rounding", LABELS["ROUNDING"], "money"), *COLUMNS[-2:])
        if converted
        else COLUMNS,
        rows=tuple(rows),
        control_totals={
            **(
                {
                    "exemption_changes": exemption_changes,
                    "exemption_detail_basis": "transaction_currency_endpoints",
                }
                if include_exemptions
                else {}
            ),
            **({"exemption_translation": exemption_translation} if include_translation else {}),
            "currency_view": view,
            "translation_basis": "monthly_average_flows_closing_endpoints"
            if converted
            else "transaction",
            "translation_rates": rates,
            "source_unexplained": source_unexplained,
            "opening": tie_outs.by_currency({code: v["OPENING"] for code, v in totals.items()}),
            "closing": tie_outs.by_currency({code: v["CLOSING"] for code, v in totals.items()}),
            "unexplained": tie_outs.by_currency(
                {code: v["UNEXPLAINED"] for code, v in totals.items()}
            ),
        },
        tie_out_results=(
            balanced,
            tie_outs.compared(tie_outs.TO_RPO_ROLLFORWARD_EQ_RPO, expected, report_total),
        ),
    )
