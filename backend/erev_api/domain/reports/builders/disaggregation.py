"""RPT-08 ``disaggregation`` Disaggregation of revenue (SCREENS_B §5.6.1 RPT-08, §0.5 RV-12;
ENGINE_SPEC_B §15.2.5 S15-R-15, S15-R-16; POLICIES POL-190, POL-191; 03 REQ-RPT-011, REQ-RPT-025;
CTL-028; BUILD_SPEC RPS-4).

Population: the ``REVENUE`` subledger lines of the range for the run's entities and book, recorded
by ``known_at``, joined to the obligation version that posted them. The dimension value is the
product's ``revenue_category`` (default) or ``product_family``, or the line's stored dimension of
``dimension_code``; ``include_timing`` adds the timing of transfer from the obligation's
``satisfaction_pattern`` ("Point in time", "Over time"). Revenue is −``amount_txn``. Rows
``<value>:<POINT_IN_TIME | OVER_TIME>`` (or ``<value>``) carry one money field per period
``period:<key>`` and ``total``; one ``TOTAL:<ISO>`` row per currency.

Under POL-191 ``ELECT`` for a nonpublic entity the entity's revenue is disaggregated by timing of
transfer only (rows ``timing:<timing>``), and the RV-12 note "Omitted under the nonpublic
disaggregation relief election." is a control total.

Tie-out ``TO_DISAGGREGATION_EQ_JE_REVENUE``: the disaggregated total equals the revenue journal
total of the same entities, book and periods (CTL-028). A revenue line without an obligation has no
disaggregation value, so it enters the journal total and not the rows, and the tie-out fails.

D-87 L6-3-Q-29: a run that omits ``include_timing`` stores it as true, the SCREENS_B RPT-08 default
(``framework.PARAMETER_DEFAULTS``), and the builder reads an absent value as true.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.db.tables import obligation_version, product, subledger_line
from erev_api.domain.reports import elections, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as balances
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, add
from erev_api.uow import UnitOfWork

CODE: Final = "disaggregation"
TIMINGS: Final = {"POINT_IN_TIME": "Point in time", "OVER_TIME": "Over time"}
UNASSIGNED: Final = "Unassigned"
PERIOD_PREFIX: Final = "period:"
TOTAL_PREFIX: Final = "TOTAL:"


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, _ = balances.ranges(session, params)
    dimension_code = str(params.parameters.get("dimension_code") or "revenue_category")
    include_timing = bool(params.parameters.get("include_timing", True))
    elected = {
        entity.id: elections.entity_elections(
            session, entity_id=entity.id, book_code=book_code, known_at=params.known_at
        )
        for entity in found
    }
    timing_only = {
        entity_id
        for entity_id, value in elected.items()
        if value.is_elected(elections.DISAGGREGATION_RELIEF)
    }
    ordered = sorted(
        {item for items in periods.values() for item in items}, key=lambda item: item.start
    )
    keys = []
    for item in ordered:
        if item.key not in keys:
            keys.append(item.key)
    key_of = {item.id: item.key for items in periods.values() for item in items}
    type Group = tuple[str, str, str | None, str]  # (label, timing, timing label, currency)
    grouped: dict[Group, dict[str, Decimal]] = {}
    if key_of and params.entity_ids:
        statement = (
            select(
                subledger_line.c.id,
                subledger_line.c.entity_id,
                subledger_line.c.period_id,
                subledger_line.c.txn_currency,
                subledger_line.c.amount_txn,
                subledger_line.c.dimensions,
                obligation_version.c.satisfaction_pattern,
                product.c.id.label("product_id"),
                product.c.revenue_category,
                product.c.product_family,
            )
            .select_from(
                subledger_line.join(
                    obligation_version,
                    and_(
                        obligation_version.c.tenant_id == subledger_line.c.tenant_id,
                        obligation_version.c.obligation_id == subledger_line.c.obligation_id,
                        obligation_version.c.contract_version_id
                        == subledger_line.c.contract_version_id,
                    ),
                ).join(
                    product,
                    and_(
                        product.c.tenant_id == obligation_version.c.tenant_id,
                        product.c.id == obligation_version.c.product_id,
                    ),
                )
            )
            .where(
                subledger_line.c.book_code == book_code,
                subledger_line.c.account_role == tie_outs.REVENUE,
                subledger_line.c.entity_id.in_(list(params.entity_ids)),
                subledger_line.c.period_id.in_(sorted(key_of, key=str)),
                subledger_line.c.recorded_at <= params.known_at,
                *tie_outs.bound_member_where(params, "subledger_line", subledger_line.c.id),
            )
        )
        consumed: list[UUID] = []  # frps3c-2: the recognized lines consumed, bound as members
        for row in session.execute(statement).mappings():
            consumed.append(UUID(str(row["id"])))
            entity_id = UUID(str(row["entity_id"]))
            timing = str(row["satisfaction_pattern"])
            currency = str(row["txn_currency"]).strip()
            group: Group
            if entity_id in timing_only:
                group = ("timing", timing, TIMINGS.get(timing, timing), currency)
            else:
                # frps3c-2: the product grouping labels as CONSUMED (bound under a binding;
                # recorded live) — never the live product join under a bound run
                if dimension_code == "revenue_category":
                    value = tie_outs.label_for(
                        params,
                        "product_revenue_category",
                        row["product_id"],
                        row["revenue_category"],
                    )
                elif dimension_code == "product_family":
                    value = tie_outs.label_for(
                        params, "product_family", row["product_id"], row["product_family"]
                    )
                else:
                    value = dict(row["dimensions"] or {}).get(dimension_code)
                label = UNASSIGNED if value in (None, "") else str(value)
                group = (label, timing if include_timing else "", None, currency)
            cells = grouped.setdefault(group, {})
            period_key = key_of[UUID(str(row["period_id"]))]
            cells[period_key] = cells.get(period_key, ZERO) - Decimal(row["amount_txn"])
        tie_outs.require_members(params, "subledger_line", consumed)
        tie_outs.record_members(params, "subledger_line", consumed)
    else:
        # R1: no period / entity in scope is a CAPTURED empty membership, never an absent kind
        tie_outs.require_members(params, "subledger_line", ())
        tie_outs.record_members(params, "subledger_line", ())
    currencies = {group[3] for group in grouped}
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = {}
    for group in sorted(grouped, key=lambda item: (item[3], item[0], item[1])):
        label, timing, timing_label, currency = group
        cells = grouped[group]
        shown_label: str | None
        shown_timing: str | None
        if label == "timing":
            row_key, shown_label = f"timing:{timing}", None
            shown_timing = timing_label
        else:
            row_key = f"{label}:{timing}" if timing else label
            shown_label, shown_timing = label, TIMINGS.get(timing) if timing else None
        if len(currencies) > 1:
            row_key = f"{row_key}:{currency}"
        total = sum(cells.values(), ZERO)
        rows.append(
            {
                "row_key": row_key,
                "dimension_code": "timing" if label == "timing" else dimension_code,
                "dimension_value": None if label == "timing" else label,
                "timing_code": timing or None,
                "dimension_value_label": shown_label,
                "timing": shown_timing,
                "currency": currency,
                **{
                    f"{PERIOD_PREFIX}{key}": tie_outs.money(cells.get(key, ZERO), currency)
                    for key in keys
                },
                "total": tie_outs.money(total, currency),
            }
        )
        into = totals.setdefault(currency, {})
        for key in keys:
            add(into, key, cells.get(key, ZERO))
    revenue: dict[str, Decimal] = {}
    for currency, cells in sorted(totals.items()):
        total = sum(cells.values(), ZERO)
        revenue[currency] = total
        rows.append(
            {
                "row_key": f"{TOTAL_PREFIX}{currency}",
                "dimension_value_label": None,
                "timing": None,
                "currency": currency,
                **{f"{PERIOD_PREFIX}{key}": tie_outs.money(cells[key], currency) for key in keys},
                "total": tie_outs.money(total, currency),
            }
        )
    period_labels = {item.key: item.name for item in ordered}
    columns = (
        # D-98 85 (CLO-7c): the dimension code, the dimension value and the timing code are the
        # row's identity in the frozen dataset; the label columns are display attributes.
        Column("dimension_code", "Dimension", "code"),
        Column("dimension_value", "Dimension value", "code"),
        Column("timing_code", "Timing code", "code"),
        Column("dimension_value_label", dimension_code.replace("_", " ").capitalize(), "text"),
        Column("timing", "Timing of transfer", "text"),
        Column("currency", "Currency", "code"),
        *(Column(f"{PERIOD_PREFIX}{key}", period_labels[key], "money") for key in keys),
        Column("total", "Total", "money"),
    )
    notes = [
        {
            "entity_code": entity.code,
            **elected[entity.id].note(elections.DISAGGREGATION_RELIEF, 1),
        }
        for entity in found
        if entity.id in timing_only
    ]
    expected = tie_outs.journal_revenue(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_ids=key_of,
        known_at=params.known_at,
        params=params,  # S15-R-24: the tie-out's journal-run membership is bound
    )
    return ReportData(
        columns=columns,
        rows=tuple(rows),
        control_totals={"revenue_total": tie_outs.by_currency(revenue), "notes": notes},
        tie_out_results=(
            tie_outs.compared(tie_outs.TO_DISAGGREGATION_EQ_JE_REVENUE, expected, revenue),
        ),
    )
