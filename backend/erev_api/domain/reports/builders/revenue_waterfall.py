"""RPT-01 ``revenue_waterfall`` Revenue waterfall (SCREENS_B §5.6.1 RPT-01; ENGINE_SPEC_B §15.2.1
S15-R-01, S15-R-02; 04 table 10-T; 03 REQ-RPT-004, REQ-RPT-017; CTL-030; BUILD_SPEC RPS-3).

Population: the obligations of each group's latest version known at the run (``tie_outs``) whose
PERFORMING entity is in the run's scope (SCREENS_B RPT-01 rev 1.69; supervisor rulings R-78 (d) and
R-121 (g)). An obligation is stated under the entity that performs it — the entity whose books
hold its revenue (05 RCP-04, TZ-04; POLICIES JET-13) — in that entity's periods and beside that
entity's journal. Until rev 1.69 the population was read by the contracting entity: a run for the
contracting entity of a contract another entity performs stated revenue its books do not hold, a
run for the performing entity stated none, and the tie-out could pass for neither. New runs
exclude contracts whose first included-chain entry falls after the performing entity's
as-of period end. Entry dates and source versions are retained; older bindings keep their original
population. Every figure
is stated at the as-of period (S15-R-01 rev 1.127; item RPT-ASOF-FIGURES-1; supervisor ruling
R-116 (c)). Per obligation and period of the range:

- **recognized** = −Σ ``REVENUE`` subledger lines of the obligation in the books of its
  performing entity, posted in the period and recorded by ``known_at`` (all reason codes,
  including late-event carries), for the periods up to the as-of period: revenue a computation
  has posted into a later period is not yet recognised at the as-of;
- **scheduled** = Σ ``REVENUE`` schedule lines of the version for periods ending after the as-of
  period, for an obligation whose remainder at the as-of has a scheduled part
  (``reports.cuts.scheduled_after``): the later lines of any other obligation are inside its
  awaiting-trigger amount;
- **awaiting trigger** = the obligation's awaiting-trigger amount at the end of the as-of period
  (one column, no period), read through the reader of the contract reads
  (``reports.cuts.obligations_at``; 04 API-C-10) and not the version's stored column, which is
  the amount at the version's own date.

In transaction currency, recognized + scheduled + awaiting trigger is the allocation at every as-of
(S15-R-02). A cell is recognized + scheduled; ``total`` adds the range's cells and the awaiting
amount. Rows
aggregate obligations by ``row_dimension``: ``contract:<external id>``, ``obligation:<external
id>:<obligation key>``, ``product:<code>``, ``category:<revenue category>``; one ``TOTAL:<ISO>`` row
per currency closes the rows. Each identifier of a row key is CV-21-encoded before the join
(``encode_key``, the engine's one table; SCREENS_B RPT-01 rev 1.26, D-98 104; supervisor ruling
R-40 (a)): the key is the grouping key, and an unescaped join made ``(A:B, C)`` and ``(A, B:C)``
one row. An identifier without ``%`` ``/`` ``@`` ``#`` ``:`` is written unchanged
(``contract:SF-ORD-10001``). Columns ``period:<bucket key>`` are the periods (``MONTH``), fiscal
quarters ``FY<year>-Q<n>`` or fiscal years ``FY<year>``; with ``BY_STATE`` each bucket gives
``period:<key>:recognized`` and ``period:<key>:scheduled``.

Tie-out ``TO_WATERFALL_EQ_JE_REVENUE``: the recognized total of the range equals the revenue journal
total of the same entities, book and periods — the periods up to the as-of period. A run
restricted by ``contract_external_id`` or grid filters compares a part with the whole, so it
answers ``NOT_APPLICABLE``.

``cell`` answers ``GET /explain/report-runs/{id}/cell``: the cell's value and its schedule lines,
subledger lines and, for ``awaiting_trigger``, obligation versions (SB-R-07; REQ-RPT-017).

Functional recognized revenue reads posted functional amounts. Reporting recognized revenue
uses each posting period's approved average rate. Scheduled and awaiting-trigger figures are
forecasts translated at the as-of closing rate, not historical revenue or journal entries.
Rates are retained with the report; forecast rounding is per schedule contribution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.stages.s01_canonicalize import encode_key
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    customer,
    legal_entity,
    obligation,
    obligation_version,
    product,
    schedule,
    schedule_line,
    subledger_line,
)
from erev_api.domain.reports import cuts, reporting_currency, tie_outs
from erev_api.domain.reports.builders import (
    ReportParams,
    contract_history,
    filter_problem,
    unknown_filter,
)
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, Calendar, EntityRef, PeriodRef, add
from erev_api.uow import UnitOfWork

CODE: Final = "revenue_waterfall"
ROW_DIMENSIONS: Final = ("CONTRACT", "OBLIGATION", "PRODUCT", "REVENUE_CATEGORY")
RECOGNIZED: Final = "recognized"
SCHEDULED: Final = "scheduled"
AWAITING: Final = "awaiting_trigger"
TOTAL: Final = "total"
PERIOD_PREFIX: Final = "period:"
TOTAL_PREFIX: Final = "TOTAL:"
FILTERS: Final = ("contract_external_id", "entity_code", "product_code", "revenue_category")
UNKNOWN_CELL: Final = "The run holds no cell {row_key} / {column_key}."


@dataclass(slots=True)
class _Obligation:
    version_row_id: UUID
    obligation_id: UUID
    external_id: str
    obligation_key: str
    line_sequence: int
    product_code: str
    revenue_category: str | None
    customer_name: str | None
    entity_id: UUID  # the performing entity: the row's entity, its periods and its journal
    entity_code: str
    currency: str
    awaiting: Decimal  # at the end of the as-of period (``population``)
    functional_recognized: dict[str, Decimal] = field(default_factory=dict)
    recognized: dict[str, Decimal] = field(default_factory=dict)  # period key → amount
    scheduled: dict[str, Decimal] = field(default_factory=dict)
    # the lines a cell names: of a period up to the as-of beside its posted revenue, of a later
    # period only where the line is the scheduled amount
    schedule_lines: dict[str, list[tuple[UUID, Decimal]]] = field(default_factory=dict)
    fixed_schedule_lines: set[UUID] = field(default_factory=set)
    fixed_schedule_cut: date | None = None
    projected_schedule_periods: set[str] = field(default_factory=set)
    subledger_lines: dict[str, list[tuple[UUID, Decimal]]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Bucket:
    key: str
    label: str
    period_keys: tuple[str, ...]
    entity_period_keys: Mapping[UUID, tuple[str, ...]] | None = None

    def keys_for(self, entity_id: UUID) -> tuple[str, ...]:
        return (
            self.period_keys
            if self.entity_period_keys is None
            else self.entity_period_keys.get(entity_id, ())
        )


@dataclass(frozen=True, slots=True)
class Population:
    book_code: str
    obligations: tuple[_Obligation, ...]
    buckets: tuple[_Bucket, ...]
    period_ids: tuple[UUID, ...]  # the periods up to each entity's as-of period
    entity_ids: tuple[UUID, ...]
    restricted: bool
    translation_rates: tuple[Mapping[str, Any], ...] = ()


def _buckets(periods: Sequence[PeriodRef], granularity: str) -> tuple[_Bucket, ...]:
    grouped: dict[str, tuple[str, list[str]]] = {}
    for item in periods:
        if granularity == "QUARTER":
            quarter = item.quarter_no or (item.period_no - 1) // 3 + 1
            key = f"FY{item.fiscal_year}-Q{quarter}"
            label = (
                f"Q{quarter} {item.fiscal_year}"
                if item.start.year == item.fiscal_year
                else f"FY{item.fiscal_year} Q{quarter}"
            )
        elif granularity == "YEAR":
            key = label = f"FY{item.fiscal_year}"
        else:
            key, label = item.key, item.name
        grouped.setdefault(key, (label, []))[1].append(item.key)
    return tuple(_Bucket(key, label, tuple(keys)) for key, (label, keys) in grouped.items())


CALENDAR_BUCKETS = "waterfall_calendar_buckets_v1"


def _calendar_buckets(
    ranges: Mapping[UUID, Sequence[PeriodRef]], granularity: str
) -> tuple[_Bucket, ...]:
    """Align whole reporting intervals by dates, never by a shared fiscal label alone."""
    grouped: dict[tuple[date, date], dict[UUID, tuple[str, ...]]] = {}
    labels: dict[tuple[date, date], set[tuple[str, str]]] = {}
    signatures = set()
    for entity_id, periods in ranges.items():
        by_key = {period.key: period for period in periods}
        signature = []
        for bucket in _buckets(periods, granularity):
            start = min(by_key[key].start for key in bucket.period_keys)
            end = max(by_key[key].end for key in bucket.period_keys)
            interval = (start, end)
            grouped.setdefault(interval, {})[entity_id] = bucket.period_keys
            labels.setdefault(interval, set()).add((bucket.key, bucket.label))
            signature.append((bucket.key, start, end))
        signatures.add(tuple(signature))
    aligned = len(signatures) <= 1
    return tuple(
        _Bucket(
            next(iter(labels[interval]))[0] if aligned else f"date_{interval[0]}_{interval[1]}",
            sorted(labels[interval])[0][1] if aligned else f"{interval[0]} – {interval[1]}",
            tuple(sorted({key for keys in entities.values() for key in keys})),
            entities,
        )
        for interval, entities in sorted(grouped.items())
    )


def population(session: Session, params: ReportParams) -> Population:
    """The obligations, cells and buckets of a run (module docstring)."""
    book_code = tie_outs.book_of(session, params)
    found_entities = tie_outs.entities(session, params.entity_ids, params=params)
    found_calendars = tie_outs.calendars(session, found_entities, params=params)
    granularity = str(params.parameters.get("granularity") or "MONTH")
    ranges: dict[UUID, tuple[PeriodRef, ...]] = {}
    as_of_ends: dict[UUID, date] = {}
    ordered: list[PeriodRef] = []
    for item in found_entities:
        calendar = found_calendars[item.id]
        periods = tie_outs.range_of(params, calendar, item, year_default=True)
        ranges[item.id] = periods
        as_of_ends[item.id] = _as_of_end(params, calendar, item, periods)
        ordered.extend(found for found in periods if found.key not in {p.key for p in ordered})
    ordered.sort(key=lambda item: item.start)
    contract_id = tie_outs.contract_named(session, params)
    cutoff = tie_outs.cutoff_for(session, params)
    obligations, version_of = _obligations(
        session, params, book_code, cutoff, contract_id, as_of_ends
    )
    period_ids = tuple(item.id for periods in ranges.values() for item in periods)
    key_of = {item.id: item.key for periods in ranges.values() for item in periods}
    end_of = {item.id: item.end for periods in ranges.values() for item in periods}
    by_id = {ob.obligation_id: ob for ob in obligations}
    if by_id:
        _at_as_of(session, obligations, version_of, as_of_ends, period_ids, key_of)
    # recognised: the posted lines of the periods up to the as-of period (04 API-C-10)
    posted_ids = tuple(
        item.id
        for entity_id, periods in ranges.items()
        for item in periods
        if item.end <= as_of_ends[entity_id]
    )
    if by_id and posted_ids:
        _recognized(session, by_id, book_code, posted_ids, key_of, end_of, as_of_ends, params)
    view = str(params.parameters.get("currency_view") or "transaction")
    rates: tuple[Mapping[str, Any], ...] = ()
    if view != "transaction":
        rates = _translate(
            session, params, obligations, found_entities, found_calendars, as_of_ends
        )
    dated_buckets = params.binding is None or params.binding.evidence.get(CALENDAR_BUCKETS) is True
    if params.binding is None:
        tie_outs.record_evidence(params, CALENDAR_BUCKETS, True)
    return Population(
        book_code=book_code,
        obligations=tuple(obligations),
        buckets=_calendar_buckets(ranges, granularity)
        if dated_buckets
        else _buckets(ordered, granularity),
        period_ids=posted_ids,
        entity_ids=tuple(item.id for item in found_entities),
        restricted=contract_id is not None or bool(params.filters),
        translation_rates=rates,
    )


def _translate(
    session: Session,
    params: ReportParams,
    obligations: Sequence[_Obligation],
    entities: Sequence[EntityRef],
    calendars: Mapping[UUID, Calendar],
    as_of_ends: Mapping[UUID, date],
) -> tuple[Mapping[str, Any], ...]:
    """Actuals use posted functional revenue; future amounts use dated forecast FX.

    Conversion is per contributing line, so cells, buckets and totals sum the same
    rounded values. No future average rates or recomputation of historical revenue.
    """
    if not obligations:
        return ()
    tenant_id = session.execute(
        select(legal_entity.c.tenant_id).where(legal_entity.c.id == obligations[0].entity_id)
    ).scalar_one()
    reporting = params.parameters.get("currency_view") == "reporting"
    rates: dict[str, reporting_currency.Translation] = {}
    by_entity = {entity.id: entity for entity in entities}

    def rate(
        entity: EntityRef, period: PeriodRef, kind: str, *, target: str | None = None
    ) -> reporting_currency.Translation:
        key = (
            f"waterfall_fx_v1:{entity.id}:{entity.functional_currency}:"
            f"{target or 'reporting'}:{period.key}:{kind}"
        )
        if key not in rates:
            rates[key] = reporting_currency.rates_for_period(
                session,
                params,
                tenant_id=tenant_id,
                entities=(entity,),
                periods={entity.id: period},
                rate_type=kind,
                evidence_key=key,
                target_currency=target,
            )
        return rates[key]

    for ob in obligations:
        entity = by_entity[ob.entity_id]
        if any(currency != entity.functional_currency for currency in ob.functional_recognized):
            raise tie_outs.invalid(
                "currency_view", "Posted functional currency differs from entity."
            )
        calendar = calendars[entity.id]
        endpoint = calendar.holding(as_of_ends[entity.id])
        if endpoint is None:
            raise tie_outs.invalid(
                "currency_view", "Forecast translation requires a dated endpoint."
            )
        source_currency = ob.currency
        ob.currency = entity.functional_currency
        # The original schedule remains a transaction-currency source, but only
        # future schedule contributions belong in the converted displayed cells.
        ob.schedule_lines = {
            key: lines for key, lines in ob.schedule_lines.items() if key in ob.scheduled
        }
        for key, lines in ob.subledger_lines.items():
            if reporting:
                translated = rate(entity, calendar.named(key, "currency_view"), "average")
                lines = [
                    (identifier, translated.amount(entity.id, amount))
                    for identifier, amount in lines
                ]
                ob.currency = translated.currency
                ob.subledger_lines[key] = lines
            ob.recognized[key] = -sum((amount for _, amount in lines), ZERO)

        forecast = bool(ob.awaiting or any(ob.scheduled.values()))
        functional_rate = None
        if forecast and source_currency != entity.functional_currency:
            functional_rate = rate(
                replace(entity, functional_currency=source_currency),
                endpoint,
                "closing",
                target=entity.functional_currency,
            )
        reporting_rate = rate(entity, endpoint, "closing") if reporting and forecast else None
        if reporting_rate is not None:
            ob.currency = reporting_rate.currency

        def convert(
            amount: Decimal,
            functional_rate: reporting_currency.Translation | None = functional_rate,
            reporting_rate: reporting_currency.Translation | None = reporting_rate,
            entity_id: UUID = entity.id,
        ) -> Decimal:
            if functional_rate is not None:
                amount = functional_rate.amount(entity_id, amount)
            if reporting_rate is not None:
                amount = reporting_rate.amount(entity_id, amount)
            return amount

        ob.awaiting = convert(ob.awaiting)
        for key, lines in ob.schedule_lines.items():
            converted = [(identifier, convert(amount)) for identifier, amount in lines]
            ob.schedule_lines[key] = converted
            ob.scheduled[key] = sum((amount for _, amount in converted), ZERO)
    return tuple(
        {"entity_id": str(entity_id), **fact}
        for translation in rates.values()
        for entity_id, fact in translation.rates.items()
    )


def _as_of_end(
    params: ReportParams, calendar: Calendar, entity: EntityRef, periods: Sequence[PeriodRef]
) -> date:
    """The end of the as-of period: ``as_of``'s period, else the range's last period."""
    if params.as_of_date is None:
        return periods[-1].end if periods else tie_outs.run_day(params, entity)
    holding = calendar.holding(params.as_of_date)
    return params.as_of_date if holding is None else holding.end


def _obligations(
    session: Session,
    params: ReportParams,
    book_code: str,
    cutoff: Any,
    contract_id: UUID | None,
    as_of_ends: Mapping[UUID, date],
) -> tuple[list[_Obligation], dict[UUID, UUID]]:
    """The run's obligations, and the contract version of each by its obligation-version row."""
    statement = (
        select(
            obligation_version.c.id,
            obligation_version.c.contract_version_id,
            obligation_version.c.obligation_id,
            obligation_version.c.obligation_key,
            obligation_version.c.product_code,
            obligation_version.c.txn_currency,
            obligation_version.c.performing_entity_id,
            obligation.c.line_sequence,
            contract.c.id.label("contract_id"),
            contract.c.external_id,
            customer.c.id.label("customer_id"),
            customer.c.name.label("customer_name"),
            product.c.id.label("product_id"),
            product.c.revenue_category,
            legal_entity.c.code.label("entity_code"),
        )
        .select_from(
            obligation_version.join(
                obligation,
                and_(
                    obligation.c.tenant_id == obligation_version.c.tenant_id,
                    obligation.c.id == obligation_version.c.obligation_id,
                ),
            )
            .join(
                contract,
                and_(
                    contract.c.tenant_id == obligation_version.c.tenant_id,
                    contract.c.id == obligation_version.c.contract_id,
                ),
            )
            .outerjoin(
                customer,
                and_(
                    customer.c.tenant_id == contract.c.tenant_id,
                    customer.c.id == contract.c.customer_id,
                ),
            )
            .join(
                product,
                and_(
                    product.c.tenant_id == obligation_version.c.tenant_id,
                    product.c.id == obligation_version.c.product_id,
                ),
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == obligation_version.c.tenant_id,
                    legal_entity.c.id == obligation_version.c.performing_entity_id,
                ),
            )
        )
        .where(
            # 04 T-CON-04 reading rule, form (1): each contract's obligations from the version
            # it is read from — a group's version can still carry a contract read elsewhere.
            tie_outs.rows_read(
                session,
                params,
                obligation_version.c.contract_id,
                obligation_version.c.contract_version_id,
                book_code=book_code,
                cutoff=cutoff,
                only_contract=contract_id,
            ),
            # the performing entity (module docstring): its books hold the obligation's revenue
            obligation_version.c.performing_entity_id.in_(list(params.entity_ids)),
        )
        .order_by(contract.c.external_id, obligation.c.line_sequence, obligation.c.obligation_key)
    )
    if contract_id is not None:
        statement = statement.where(obligation_version.c.contract_id == contract_id)
    rows = [dict(row) for row in session.execute(statement).mappings()]
    rows = _entered_rows(session, params, rows, book_code, cutoff, as_of_ends)
    version_of = {UUID(str(row["id"])): UUID(str(row["contract_version_id"])) for row in rows}
    found = [
        _Obligation(
            version_row_id=UUID(str(row["id"])),
            obligation_id=UUID(str(row["obligation_id"])),
            external_id=str(row["external_id"]),
            obligation_key=str(row["obligation_key"]),
            line_sequence=int(row["line_sequence"] or 0),
            product_code=str(row["product_code"]),
            revenue_category=tie_outs.label_for(
                params,
                "product_revenue_category",
                row["product_id"],
                None if row["revenue_category"] is None else str(row["revenue_category"]),
            ),
            customer_name=tie_outs.label_for(
                params,
                "customer_name",
                row["customer_id"],
                None if row["customer_name"] is None else str(row["customer_name"]),
            ),
            entity_id=UUID(str(row["performing_entity_id"])),
            entity_code=tie_outs.entity_code_for(
                params, UUID(str(row["performing_entity_id"])), str(row["entity_code"])
            ),
            currency=str(row["txn_currency"]).strip(),
            awaiting=ZERO,  # stated at the as-of by ``_at_as_of``, never the stored column
        )
        for row in rows
    ]
    return found, version_of


ENTRY_EVIDENCE = "waterfall_entry_dates_v1"


def _entered_rows(
    session: Session,
    params: ReportParams,
    rows: list[dict[str, Any]],
    book_code: str,
    cutoff: Any,
    as_of_ends: Mapping[UUID, date],
) -> list[dict[str, Any]]:
    if params.binding is not None:
        if ENTRY_EVIDENCE not in params.binding.evidence:
            return rows  # Original runs retain their original population.
        entries = params.binding.evidence[ENTRY_EVIDENCE]
    else:
        entries = (
            contract_history.entry_dates(
                session,
                book_code=book_code,
                cutoff=cutoff,
                contract_ids=sorted({UUID(str(row["contract_id"])) for row in rows}, key=str),
            )
            if rows
            else {}
        )
    if params.sources is not None:
        params.sources.record_evidence(ENTRY_EVIDENCE, entries)
    selected = []
    for row in rows:
        source = entries.get(str(row["contract_id"]))
        if source is None:
            raise tie_outs.invalid("as_of", "The contract entry date is unavailable.")
        if date.fromisoformat(source["entry_date"]) <= as_of_ends[row["performing_entity_id"]]:
            selected.append(row)
    return selected


def _at_as_of(
    session: Session,
    obligations: Sequence[_Obligation],
    version_of: Mapping[UUID, UUID],
    as_of_ends: Mapping[UUID, date],
    period_ids: Sequence[UUID],
    key_of: Mapping[UUID, str],
) -> None:
    """Each obligation at the end of its entity's as-of period (module docstring): its
    awaiting-trigger amount, and its scheduled amount by period of the range. Every ``REVENUE``
    line of the obligation's version is read, the range's and the later ones: the lines after the
    as-of period state the scheduled part of the remainder only when they add up to it
    (``cuts.scheduled_after``)."""
    wanted: dict[UUID, set[date]] = {}
    for ob in obligations:
        wanted.setdefault(version_of[ob.version_row_id], set()).add(as_of_ends[ob.entity_id])
    at = cuts.obligations_at(session, wanted)
    statement = (
        select(
            schedule_line.c.id,
            schedule_line.c.contract_version_id,
            schedule_line.c.subject_id,
            schedule_line.c.period_id,
            schedule_line.c.period_end_date,
            schedule_line.c.amount,
            schedule_line.c.trace_node_id,
        )
        .select_from(
            schedule_line.join(
                schedule,
                and_(
                    schedule.c.tenant_id == schedule_line.c.tenant_id,
                    schedule.c.id == schedule_line.c.schedule_id,
                ),
            )
        )
        .where(
            tie_outs.in_versions(schedule_line.c.contract_version_id, sorted(wanted, key=str)),
            schedule_line.c.subject_type == "obligation",
            schedule.c.schedule_kind == tie_outs.REVENUE,
            schedule_line.c.subject_id.in_([ob.obligation_id for ob in obligations]),
        )
        .order_by(schedule_line.c.period_end_date, schedule_line.c.id)
    )
    lines: dict[tuple[UUID, UUID], list[tuple[UUID, date, Decimal, UUID]]] = {}
    line_nodes: dict[UUID, str] = {}
    for row in session.execute(statement).mappings():
        line_nodes[UUID(str(row["id"]))] = str(row["trace_node_id"])
        key = (UUID(str(row["contract_version_id"])), UUID(str(row["subject_id"])))
        lines.setdefault(key, []).append(
            (
                UUID(str(row["id"])),
                row["period_end_date"],
                Decimal(row["amount"]),
                UUID(str(row["period_id"])),
            )
        )
    in_range = set(period_ids)
    for ob in obligations:
        day = as_of_ends[ob.entity_id]
        version_id = version_of[ob.version_row_id]
        found = at[version_id, day][ob.version_row_id]
        ob.awaiting = found.awaiting
        ob.fixed_schedule_cut = found.fixed_schedule_cut
        own = lines.get((version_id, ob.obligation_id), [])
        projected = cuts.projected_after(
            found, day, contract=ob.external_id, obligation=ob.obligation_key
        )
        if projected is not None:
            for projected_key, _, amount in projected:
                if projected_key in {key_of[period_id] for period_id in period_ids}:
                    ob.projected_schedule_periods.add(projected_key)
                    ob.schedule_lines.setdefault(projected_key, []).append(
                        (ob.version_row_id, amount)
                    )
                    ob.scheduled[projected_key] = amount
            scheduled = {}
        else:
            scheduled = {
                line_id: amount
                for line_id, _, amount in cuts.scheduled_after(
                    [(line_id, end, amount) for line_id, end, amount, _ in own],
                    found,
                    day,
                    contract=ob.external_id,
                    obligation=ob.obligation_key,
                    sources=line_nodes,
                )
            }
        for line_id, end, amount, period_id in own:
            if period_id not in in_range or (end > day and line_id not in scheduled):
                continue
            name = key_of[period_id]
            if line_id in scheduled:
                amount = scheduled[line_id]
                if found.fixed_schedule is not None:
                    ob.fixed_schedule_lines.add(line_id)
            ob.schedule_lines.setdefault(name, []).append((line_id, amount))
            if line_id in scheduled:
                ob.scheduled[name] = ob.scheduled.get(name, ZERO) + amount


def _recognized(
    session: Session,
    by_id: Mapping[UUID, _Obligation],
    book_code: str,
    period_ids: Sequence[UUID],
    key_of: Mapping[UUID, str],
    end_of: Mapping[UUID, date],
    as_of_ends: Mapping[UUID, date],
    params: ReportParams,
) -> None:
    """The posted revenue of each obligation by period, for the periods up to its entity's as-of
    period: a line a computation posted into a later period is no revenue recognised at the
    as-of, and the amount is in the scheduled or the awaiting-trigger column. Only the lines in
    the books of the obligation's performing entity are read (module docstring), so no line is
    stated under an entity whose journal does not hold it."""
    statement = select(
        subledger_line.c.id,
        subledger_line.c.obligation_id,
        subledger_line.c.entity_id,
        subledger_line.c.period_id,
        subledger_line.c.amount_txn,
        subledger_line.c.amount_functional,
        subledger_line.c.functional_currency,
    ).where(
        subledger_line.c.book_code == book_code,
        subledger_line.c.account_role == tie_outs.REVENUE,
        subledger_line.c.obligation_id.in_(list(by_id)),
        subledger_line.c.entity_id.in_(sorted({ob.entity_id for ob in by_id.values()}, key=str)),
        subledger_line.c.period_id.in_(list(period_ids)),
        tie_outs.line_recorded_by(params),
        # S15-R-24 (Codex 2154): under a bound run exactly the lines the original consumed.
        *tie_outs.bound_member_where(params, "subledger_line", subledger_line.c.id),
    )
    rows = [
        row
        for row in session.execute(statement.order_by(subledger_line.c.id)).mappings()
        if UUID(str(row["entity_id"])) == by_id[UUID(str(row["obligation_id"]))].entity_id
        and end_of[UUID(str(row["period_id"]))]
        <= as_of_ends[by_id[UUID(str(row["obligation_id"]))].entity_id]
    ]
    tie_outs.require_members(params, "subledger_line", (row["id"] for row in rows))
    tie_outs.record_members(params, "subledger_line", (row["id"] for row in rows))
    for row in rows:
        ob = by_id[UUID(str(row["obligation_id"]))]
        key = key_of[UUID(str(row["period_id"]))]
        amount = Decimal(row["amount_txn"])
        if params.parameters.get("currency_view", "transaction") != "transaction":
            amount = Decimal(row["amount_functional"])
            currency = str(row["functional_currency"]).strip()
            add(ob.functional_recognized, currency, -amount)
        ob.subledger_lines.setdefault(key, []).append((UUID(str(row["id"])), amount))
        ob.recognized[key] = ob.recognized.get(key, ZERO) - amount


def _component(identifier: str | None) -> str:
    """One identifier of a row key, CV-21-encoded (``encode_key``): a delimiter inside it never
    makes two rows one key. An identifier without a delimiter is unchanged; an absent one is
    empty."""
    return encode_key(identifier) if identifier else ""


def _row_key(ob: _Obligation, dimension: str) -> str:
    """The row an obligation belongs to under ``dimension`` — injective in the identifiers."""
    if dimension == "OBLIGATION":
        return f"obligation:{_component(ob.external_id)}:{_component(ob.obligation_key)}"
    if dimension == "PRODUCT":
        return f"product:{_component(ob.product_code)}"
    if dimension == "REVENUE_CATEGORY":
        return f"category:{_component(ob.revenue_category)}"
    return f"contract:{_component(ob.external_id)}"


def _grouped(found: Population, dimension: str) -> dict[str, list[_Obligation]]:
    """Row key → obligations; a key holding several currencies is split by ``:<ISO>`` (the
    encoded identifiers hold no ``:``, so a split key never equals another row's key)."""
    groups: dict[str, list[_Obligation]] = {}
    for ob in found.obligations:
        groups.setdefault(_row_key(ob, dimension), []).append(ob)
    split: dict[str, list[_Obligation]] = {}
    for key, members in groups.items():
        currencies = sorted({ob.currency for ob in members})
        if len(currencies) == 1:
            split[key] = members
            continue
        for code in currencies:
            split[f"{key}:{code}"] = [ob for ob in members if ob.currency == code]
    return split


def _cell(members: Sequence[_Obligation], bucket: _Bucket, state: str | None) -> Decimal:
    total = ZERO
    for ob in members:
        for key in bucket.keys_for(ob.entity_id):
            if state in (None, RECOGNIZED):
                total += ob.recognized.get(key, ZERO)
            if state in (None, SCHEDULED):
                total += ob.scheduled.get(key, ZERO)
    return total


def _columns(
    dimension: str, found: Population, by_state: bool, mixed: bool, converted: bool = False
) -> tuple[Column, ...]:
    columns = [
        Column("contract_external_id", "Contract", "code"),
        Column("customer_name", "Customer", "text"),
    ]
    if dimension == "OBLIGATION":
        columns.append(Column("obligation_key", "Obligation", "code"))
    if dimension in ("OBLIGATION", "PRODUCT"):
        columns.append(Column("product_code", "Product", "code"))
    if dimension == "REVENUE_CATEGORY":
        columns.append(Column("revenue_category", "Revenue category", "text"))
    columns.append(Column("entity_code", "Entity", "code"))
    if mixed:
        columns.append(Column("currency", "Currency", "code"))
    for bucket in found.buckets:
        if by_state:
            columns.append(
                Column(
                    f"{PERIOD_PREFIX}{bucket.key}:{RECOGNIZED}",
                    f"{bucket.label} recognized",
                    "money",
                )
            )
            columns.append(
                Column(
                    f"{PERIOD_PREFIX}{bucket.key}:{SCHEDULED}",
                    f"{bucket.label} scheduled" + (" (as-of FX)" if converted else ""),
                    "money",
                )
            )
        else:
            columns.append(Column(f"{PERIOD_PREFIX}{bucket.key}", bucket.label, "money"))
    columns.append(
        Column(AWAITING, "Awaiting trigger" + (" (as-of FX)" if converted else ""), "money")
    )
    columns.append(Column(TOTAL, "Total", "money"))
    return tuple(columns)


def _values(
    members: Sequence[_Obligation], found: Population, by_state: bool, currency: str
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    total = ZERO
    for bucket in found.buckets:
        amount = _cell(members, bucket, None)
        total += amount
        if by_state:
            values[f"{PERIOD_PREFIX}{bucket.key}:{RECOGNIZED}"] = tie_outs.money(
                _cell(members, bucket, RECOGNIZED), currency
            )
            values[f"{PERIOD_PREFIX}{bucket.key}:{SCHEDULED}"] = tie_outs.money(
                _cell(members, bucket, SCHEDULED), currency
            )
        else:
            values[f"{PERIOD_PREFIX}{bucket.key}"] = tie_outs.money(amount, currency)
    awaiting = sum((ob.awaiting for ob in members), ZERO)
    values[AWAITING] = tie_outs.money(awaiting, currency)
    values[TOTAL] = tie_outs.money(total + awaiting, currency)
    return values


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    found = population(session, params)
    dimension = str(params.parameters.get("row_dimension") or "CONTRACT")
    by_state = str(params.parameters.get("measure") or "TOTAL") == "BY_STATE"
    for name in sorted(params.filters):
        if name not in FILTERS:
            raise unknown_filter(name, FILTERS)
    rows: list[dict[str, Any]] = []
    recognized: dict[str, Decimal] = {}
    scheduled: dict[str, Decimal] = {}
    awaiting: dict[str, Decimal] = {}
    totals: dict[str, list[_Obligation]] = {}
    for key, members in _grouped(found, dimension).items():
        first = members[0]
        has_amount = any(ob.recognized or ob.scheduled or ob.awaiting for ob in members)
        if not has_amount:
            continue
        row: dict[str, Any] = {
            "row_key": key,
            "contract_external_id": first.external_id
            if dimension in ("CONTRACT", "OBLIGATION")
            else None,
            "customer_name": first.customer_name
            if dimension in ("CONTRACT", "OBLIGATION")
            else None,
            "obligation_key": first.obligation_key,
            "product_code": first.product_code,
            "revenue_category": first.revenue_category,
            "entity_code": first.entity_code
            if len({ob.entity_code for ob in members}) == 1
            else None,
            "currency": first.currency,
            **_values(members, found, by_state, first.currency),
        }
        if any(str(row.get(name) or "") != value for name, value in sorted(params.filters.items())):
            continue
        rows.append(row)
        for ob in members:
            totals.setdefault(ob.currency, []).append(ob)
            add(recognized, ob.currency, sum(ob.recognized.values(), ZERO))
            add(scheduled, ob.currency, sum(ob.scheduled.values(), ZERO))
            add(awaiting, ob.currency, ob.awaiting)
    for currency, members in sorted(totals.items()):
        rows.append(
            {
                "row_key": f"{TOTAL_PREFIX}{currency}",
                "contract_external_id": None,
                "customer_name": None,
                "obligation_key": None,
                "product_code": None,
                "revenue_category": None,
                "entity_code": None,
                "currency": currency,
                **_values(members, found, by_state, currency),
            }
        )
    mixed = len(totals) > 1
    columns = _columns(
        dimension,
        found,
        by_state,
        mixed,
        params.parameters.get("currency_view", "transaction") != "transaction",
    )
    keys = {column.key for column in columns}
    shaped = tuple(
        {"row_key": row["row_key"], **{name: value for name, value in row.items() if name in keys}}
        for row in rows
    )
    return ReportData(
        columns=columns,
        rows=shaped,
        control_totals={
            "recognized_total": tie_outs.by_currency(recognized),
            "scheduled_total": tie_outs.by_currency(scheduled),
            "awaiting_trigger_total": tie_outs.by_currency(awaiting),
            "currency_view": str(params.parameters.get("currency_view") or "transaction"),
            "forecast_currency_basis": "as_of_closing_rate"
            if params.parameters.get("currency_view", "transaction") != "transaction"
            else "transaction",
            "tie_out_currency_basis": "functional"
            if params.parameters.get("currency_view", "transaction") != "transaction"
            else "transaction",
            "translation_rates": list(found.translation_rates),
        },
        tie_out_results=(tie_out(session, params, found),),
    )


def tie_out(session: Session, params: ReportParams, found: Population) -> dict[str, Any]:
    """``TO_WATERFALL_EQ_JE_REVENUE`` over the run's whole population (S15-R-02; CTL-030)."""
    if found.restricted:
        return tie_outs.not_applicable(tie_outs.TO_WATERFALL_EQ_JE_REVENUE)
    actual: dict[str, Decimal] = {}
    functional = params.parameters.get("currency_view", "transaction") != "transaction"
    for ob in found.obligations:
        if functional:
            for currency, amount in ob.functional_recognized.items():
                add(actual, currency, amount)
        else:
            add(actual, ob.currency, sum(ob.recognized.values(), ZERO))
    expected = tie_outs.journal_revenue(
        session,
        entity_ids=found.entity_ids,
        book_code=found.book_code,
        period_ids=found.period_ids,
        known_at=params.known_at,
        functional=functional,
        params=params,  # S15-R-24: the tie-out's journal-run membership is bound
    )
    result = tie_outs.compared(tie_outs.TO_WATERFALL_EQ_JE_REVENUE, expected, actual)
    if functional:
        result["details"] = [{"currency_basis": "functional", "forecast_included": "false"}]
    return result


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """The value and contributors of one cell (``GET /explain/report-runs/{id}/cell``)."""
    found = population(session, params)
    dimension = str(params.parameters.get("row_dimension") or "CONTRACT")
    groups = _grouped(found, dimension)
    if row_key.startswith(TOTAL_PREFIX):
        currency = row_key[len(TOTAL_PREFIX) :]
        members = [ob for ob in found.obligations if ob.currency == currency]
    else:
        members = groups.get(row_key, [])
    if not members:
        raise filter_problem("row_key", UNKNOWN_CELL.format(row_key=row_key, column_key=column_key))
    currency = members[0].currency
    buckets: Sequence[_Bucket]
    state: str | None = None
    if column_key == AWAITING:
        buckets = ()
    elif column_key == TOTAL:
        buckets = found.buckets
    elif column_key.startswith(PERIOD_PREFIX):
        name, _, state_text = column_key[len(PERIOD_PREFIX) :].partition(":")
        state = state_text or None
        buckets = tuple(bucket for bucket in found.buckets if bucket.key == name)
        if not buckets or state not in (None, RECOGNIZED, SCHEDULED):
            raise filter_problem(
                "column_key", UNKNOWN_CELL.format(row_key=row_key, column_key=column_key)
            )
    else:
        raise filter_problem(
            "column_key", UNKNOWN_CELL.format(row_key=row_key, column_key=column_key)
        )
    value = sum((_cell(members, bucket, state) for bucket in buckets), ZERO)
    contributors: list[dict[str, Any]] = []
    for ob in members:
        for bucket in buckets:
            for key in bucket.keys_for(ob.entity_id):
                if state in (None, SCHEDULED, RECOGNIZED):
                    for line_id, amount in ob.schedule_lines.get(key, ()):
                        if params.parameters.get(
                            "currency_view", "transaction"
                        ) != "transaction" and (key not in ob.scheduled or state == RECOGNIZED):
                            continue
                        if key in ob.projected_schedule_periods:
                            contributors.append(
                                _contributor(
                                    "obligation_version",
                                    ob.version_row_id,
                                    amount,
                                    currency,
                                    measure=f"scheduled_period_at_cut@{ob.fixed_schedule_cut}@{key}",
                                )
                            )
                            continue
                        contributors.append(
                            _contributor(
                                "schedule_line",
                                line_id,
                                amount,
                                currency,
                                measure=(
                                    "scheduled_fixed_amount"
                                    + (
                                        "@" + ob.fixed_schedule_cut.isoformat()
                                        if ob.fixed_schedule_cut is not None
                                        else ""
                                    )
                                )
                                if line_id in ob.fixed_schedule_lines
                                else "amount",
                            )
                        )
                if state in (None, RECOGNIZED):
                    for line_id, amount in ob.subledger_lines.get(key, ()):
                        contributors.append(
                            _contributor(
                                "subledger_line",
                                line_id,
                                -amount
                                if params.parameters.get("currency_view", "transaction")
                                != "transaction"
                                else amount,
                                currency,
                            )
                        )
        if column_key in (AWAITING, TOTAL):
            value += ob.awaiting if column_key == AWAITING or buckets else ZERO
            if ob.awaiting:
                contributors.append(
                    _contributor(
                        "obligation_version",
                        ob.version_row_id,
                        ob.awaiting,
                        currency,
                        measure="awaiting_trigger_amount",
                    )
                )
    if params.parameters.get("currency_view", "transaction") != "transaction":
        for contributor in contributors:
            contributor["details"] = [
                "Contribution shown in the report currency; the source retains its original value.",
                "Recognized revenue uses posted functional amounts, with reporting average FX."
                if contributor["object_type"] == "subledger_line"
                else "Forecast translated using retained as-of closing rates.",
            ]
    return tie_outs.money(value, currency), contributors


def _contributor(
    object_type: str, object_id: UUID, amount: Decimal, currency: str, *, measure: str = "amount"
) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "id": object_id,
        "measure": measure,
        "value": tie_outs.money(amount, currency),
        "href": f"/api/v1/explain/{object_type}/{object_id}/{measure}"
        + (
            "?as_of=" + measure.split("@")[1]
            if measure.startswith("scheduled_period_at_cut@")
            else ""
        ),
    }
