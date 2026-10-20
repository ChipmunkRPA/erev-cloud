"""Functional/reporting opening-liability disclosure from the retained balance path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_api.domain.reports import locked_ends, reporting_rollforward, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward
from erev_api.domain.reports.outputs import ReportData
from erev_api.enums import BookCode
from erev_api.registry.resolve import resolve
from erev_api.uow import UnitOfWork

KEY = "opening_relief_currency_v1"
ZERO = Decimal(0)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book = tie_outs.book_of(session, params)
    entities, periods, before = rollforward.ranges(session, params)
    cutoff = tie_outs.cutoff_for(session, params)
    locked = locked_ends.Reader(
        uow,
        params,
        book_code=book,
        cutoff=cutoff,
        entity_codes={entity.id: entity.code for entity in entities},
    )
    view = str(params.parameters["currency_view"])
    items = rollforward.rollforwards(
        session,
        entity_ids=params.entity_ids,
        book_code=book,
        periods=periods,
        before=before,
        known_at=params.known_at,
        cutoff=cutoff,
        params=params,
        functional=True,
        period_detail=view == "reporting",
        locked=locked,
        uow=uow,
    )
    if any(
        lines["OTHER"][balance] != 0
        for item in items
        for lines in (item.lines, *item.period_lines.values())
        for balance in tie_outs.ROLLFORWARD_BALANCES
    ):
        raise tie_outs.invalid(
            "currency_view", "Opening relief requires reconciled member balance movements."
        )
    rates: list[dict[str, Any]] = []
    if view == "reporting":
        items, rates = reporting_rollforward.project(
            session,
            params,
            tenant_id=uow.principal.tenant_id,
            entities=entities,
            periods=periods,
            before=before,
            items=items,
            locked=locked,
        )
    contracts = []
    totals: dict[str, dict[str, Decimal]] = {}
    for item in items:
        opening = item.lines["OPENING"][rollforward.LIABILITY]
        from_opening = -item.lines["REVENUE_FROM_OPENING"][rollforward.LIABILITY]
        recognized = sum(
            (
                values[rollforward.ASSET]
                + values[rollforward.UNBILLED]
                - values[rollforward.LIABILITY]
                for code, values in item.lines.items()
                if code in {"REVENUE_FROM_OPENING", "REVENUE_FROM_PERIOD_BILLINGS"}
            ),
            ZERO,
        )
        # Include both the opening holder and the recognizer; neither a zero
        # individual opening nor a different member owner may erase genuine relief.
        if opening == 0 and recognized == 0 and from_opening == 0:
            continue
        contracts.append(
            {
                "row_key": f"contract:{item.external_id}:{item.entity_code}",
                "section": 2,
                "contract_external_id": item.external_id,
                "customer_name": item.customer_name,
                "entity_code": item.entity_code,
                "currency": item.currency,
                "opening_contract_liability": tie_outs.money(opening, item.currency),
                "revenue_recognized": tie_outs.money(recognized, item.currency),
                "revenue_from_opening": tie_outs.money(from_opening, item.currency),
            }
        )
        group = totals.setdefault(item.currency, {})
        for name, value in (
            ("opening", opening),
            ("revenue", recognized),
            ("relief", from_opening),
        ):
            tie_outs.add(group, name, value)
    return finish(
        uow,
        params,
        contracts=contracts,
        totals=totals,
        entities=entities,
        periods=periods,
        book=book,
        view=view,
        rates=rates,
        source_key=KEY,
    )


def finish(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    contracts: list[dict[str, Any]],
    totals: dict[str, dict[str, Decimal]],
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    book: str,
    view: str,
    rates: list[dict[str, Any]],
    source_key: str,
    legacy_contract_footnote: bool = False,
    signed_reversals: bool = False,
) -> ReportData:
    from .builders import revenue_from_opening_liability as disclosure

    session = uow.session
    labels = sorted(
        {f"{p[0].name} to {p[-1].name}" if len(p) > 1 else p[0].name for p in periods.values() if p}
    )
    rows = [
        {
            "row_key": f"summary:{currency}",
            "section": 1,
            "currency": currency,
            "summary": disclosure.SUMMARY.format(range=", ".join(labels)),
            "opening_contract_liability": tie_outs.money(values["opening"], currency),
            "revenue_recognized": tie_outs.money(values["revenue"], currency),
            "revenue_from_opening": tie_outs.money(values["relief"], currency),
        }
        for currency, values in sorted(totals.items())
    ]
    rows.extend(contracts)
    policies = sorted(
        {
            str(
                resolve(
                    session,
                    disclosure.POLICY,
                    book_code=BookCode(book),
                    entity_id=entity.id,
                    known_at=params.known_at,
                ).value
            )
            for entity in entities
        }
    )
    evidence = {
        "currency_view": view,
        "method": (
            "retained_rollforward_sources_v1"
            if source_key == KEY
            else "retained_group_control_path_v1"
        ),
    }
    if signed_reversals:
        evidence["method"] = "retained_signed_revenue_sources_v1"
    if params.binding is not None and params.binding.evidence[source_key] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Opening-relief method differs from retained evidence."
        )
    tie_outs.record_evidence(params, source_key, evidence)
    footnote = (
        "Revenue follows the original liability layers. Combined-contract relief is shown "
        "against the recognizing member, which may differ from the member "
        "holding the opening balance."
    )
    if source_key != KEY:
        footnote = (
            "Opening relief follows FIFO consumption of the retained group control path. "
            "Combined-contract relief is shown against the recognizing member, which may "
            "differ from the member holding the opening balance. Applied policy: "
            f"{disclosure.APPLIED}."
        )
    if signed_reversals:
        footnote = (
            "Opening relief follows original signed liability-consumption sources and creation "
            "dates. Revenue reversals restore the original source attribution; the recognizing "
            "member may differ from the opening-balance holder. "
            f"Applied policy: {disclosure.APPLIED}."
        )
    if any(policy != disclosure.APPLIED for policy in policies):
        footnote += " Per-obligation consumption is not provided in this contract-level disclosure."
    if legacy_contract_footnote:
        footnote = disclosure.footnote(policies)
    return ReportData(
        columns=disclosure.COLUMNS,
        rows=tuple(rows),
        control_totals={
            "revenue_from_opening_total": tie_outs.by_currency(
                {code: values["relief"] for code, values in totals.items()}
            ),
            "currency_view": view,
            "footnote": footnote,
            "resolved_consumption_policies": policies,
            "translation_rates": rates,
        },
    )
