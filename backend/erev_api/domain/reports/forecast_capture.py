"""Internal RPT-39 source capture after forecast computation has completed.

Five heterogeneous tables share a cutoff, book and entity scope. Each child retains its own
source evidence so repeated period-end reads cannot overwrite each other's configuration.
Run admission, publication identity, durable execution and exports belong to the forecast worker;
this module neither queues computations nor advertises a same-source rerun adapter.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import contract
from erev_api.domain.reports import forecast_sections, tie_outs
from erev_api.domain.reports.builders import (
    OPEN,
    Builder,
    ReportParams,
    SourceBinding,
    SourceCollector,
    bbr_currency,
    bbr_sources,
    contract_balances,
    extract_subledger_lines,
    revenue_waterfall,
    rpo,
)
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import PeriodRef
from erev_api.enums import TenantKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    data: ReportData


@dataclass(frozen=True)
class Captured:
    sections: tuple[Section, ...]
    sources: Mapping[str, SourceBinding]
    entity_periods: Mapping[UUID, tuple[PeriodRef, ...]]
    entity_codes: tuple[str, ...]
    book: str
    known_at: datetime
    output_format: str | None
    currency_view: str = "transaction"


def capture(uow: UnitOfWork, params: ReportParams, *, horizon: Sequence[str]) -> Captured:
    """Read computed scenario figures; fail atomically if any requested source is unavailable."""
    if uow.ctx.tenant_kind != TenantKind.SANDBOX:
        raise Problem("sandbox-restricted", "Forecast capture belongs to a scenario sandbox.")
    if params.binding is not None or params.period_lock_id is not None or params.filters:
        raise Problem("validation-failed", "Forecast capture requires an unfiltered live source.")
    if not horizon or len(set(horizon)) != len(horizon) or not params.entity_ids:
        raise Problem(
            "validation-failed", "Choose entities and a nonempty unique forecast horizon."
        )
    requester = params.requester or uow.ctx
    if requester.principal.tenant_id != uow.principal.tenant_id:
        raise Problem("forbidden", "Forecast requester belongs to another workspace.")
    for entity_id in params.entity_ids:
        require_for_entity(requester, "report.run", entity_id)
    view = str(params.parameters.get("currency_view") or "transaction")
    if view not in {"transaction", "functional"}:
        raise Problem("validation-failed", "Forecast capture requires a supported currency basis.")
    if params.output_format not in {None, "JSON", "XLSX", "CSV"}:
        raise Problem("validation-failed", "Forecast outputs supports XLSX, CSV and JSON.")
    base = replace(
        params,
        historical=True,
        output_format=params.output_format or "JSON",
        sources=SourceCollector(),
        as_of_date=None,
        parameters={"currency_view": view},
    )
    found = tie_outs.entities(uow.session, base.entity_ids, params=base)
    if {e.id for e in found} != set(base.entity_ids):
        raise Problem("not-found", "A forecast entity is unavailable.")
    calendars = tie_outs.calendars(uow.session, found, params=base)
    periods = {
        e.id: tuple(calendars[e.id].named(key, "horizon_periods") for key in horizon) for e in found
    }
    for entity_id, selected in periods.items():
        forecast_sections._horizon(selected)
        if calendars[entity_id].between(selected[0], selected[-1]) != selected:
            raise Problem("validation-failed", "Forecast horizon must contain consecutive periods.")
    base = replace(base, book_code=tie_outs.book_of(uow.session, base))
    assert base.sources is not None
    base.sources.record_cutoff(base.known_at)
    sources = {"scope": base.sources.binding(row_keys=(), strategy=OPEN)}

    def child(code: str, **values: Any) -> ReportParams:
        return replace(
            base,
            report_code=code,
            report_version=1,
            sources=SourceCollector(),
            parameters={"currency_view": view, **values},
        )

    def retain(key: str, chosen: ReportParams, data: ReportData) -> ReportData:
        assert chosen.sources is not None
        if chosen.sources.cutoff != base.known_at:
            raise Problem("invalid-transition", "A forecast source used a different cutoff.")
        sources[key] = chosen.sources.binding(
            row_keys=[str(row["row_key"]) for row in data.rows],
            strategy=OPEN,
            report_version=chosen.report_version,
        )
        return replace(data, tie_out_results=())

    def build(key: str, builder: Builder, chosen: ReportParams) -> ReportData:
        return retain(key, chosen, builder(uow, chosen))

    revenue = build(
        "revenue",
        revenue_waterfall.build,
        child(
            "revenue_waterfall",
            from_period_key=horizon[0],
            to_period_key=horizon[-1],
            row_dimension="OBLIGATION",
            granularity="MONTH",
            measure="TOTAL",
        ),
    )
    # Keep classification alongside obligation rows so comparisons use the original labels.
    revenue = replace(
        revenue,
        columns=(
            *revenue.columns,
            Column("revenue_category", "Revenue category", "text", empty_text="Unassigned"),
        ),
    )
    billing_params = child("bookings_billings_revenue")
    raw = bbr_sources.read(
        uow,
        billing_params,
        period_ids=[p.id for ps in periods.values() for p in ps],
    )
    contributions = tuple(
        row
        for row in bbr_sources.billings(raw)
        if any(p.start <= row.effective_date <= p.end for p in periods[row.entity_id])
    )
    labels = dict(
        uow.session.execute(
            select(contract.c.id, contract.c.external_id).where(
                contract.c.tenant_id == uow.principal.tenant_id,
                contract.c.contracting_entity_id.in_(base.entity_ids),
                contract.c.id.in_({row.contract_id for row in contributions}),
                contract.c.created_at <= base.known_at,
            )
        )
        .tuples()
        .all()
    )
    assert billing_params.sources is not None
    for identity, label in labels.items():
        billing_params.sources.record_label("contract_external_id", str(identity), label)
    if view == "functional":
        valued = bbr_currency.functional(uow, billing_params, {"billings": contributions}, found)
        functional = {e.id: e.functional_currency for e in found}
        contributions = tuple(
            replace(
                row,
                currency=functional[row.entity_id],
                amount=row.amount if row.functional_amount is None else row.functional_amount,
            )
            for row in valued["billings"]
        )
    columns = periods[found[0].id]
    billing = retain(
        "billing",
        billing_params,
        forecast_sections.billing(
            contributions,
            periods=columns,
            entity_periods=periods,
            contract_labels=labels,
        ),
    )
    ends: dict[date, list[Mapping[str, Any]]] = {}
    for entity in found:
        for period in periods[entity.id]:
            chosen = replace(
                child("contract_balances", period_key=period.key, include_zero=True),
                entity_ids=(entity.id,),
            )
            data = build(f"balances:{entity.id}:{period.key}", contract_balances.build, chosen)
            ends.setdefault(period.end, []).extend(
                row for row in data.rows if not str(row["row_key"]).startswith("TOTAL:")
            )
    balances = forecast_sections.balances(
        tuple(
            (end, ReportData(columns=(), rows=tuple(rows), control_totals={}))
            for end, rows in sorted(ends.items())
        )
    )
    remaining = build(
        "rpo",
        rpo.build,
        child(
            "rpo",
            period_key=horizon[-1],
            row_dimension="CONTRACT",
        ),
    )
    # RPT-39 uses only RPT-06 section 1; retain the source controls/election notes.
    stop = next(i for i, col in enumerate(remaining.columns) if col.key == "obligation_key")
    remaining = replace(
        remaining,
        columns=remaining.columns[1:stop],
        rows=tuple(
            {key: value for key, value in row.items() if key != "section"}
            for row in remaining.rows
            if row.get("section") == 1
        ),
    )
    lines = build("journals", extract_subledger_lines.build, child("extract_subledger_lines"))
    journals = forecast_sections.journals(lines, periods=columns, currency_view=view)
    assert base.book_code is not None
    return Captured(
        (
            Section("revenue", "Forecast revenue by period", revenue),
            Section("billing", "Forecast billing by period", billing),
            Section("balances", "Projected contract balances", balances),
            Section("rpo", "Projected remaining performance obligations", remaining),
            Section("journals", "Journal preview", journals),
        ),
        sources,
        periods,
        tuple(e.code for e in found),
        base.book_code,
        base.known_at,
        base.output_format,
        view,
    )
