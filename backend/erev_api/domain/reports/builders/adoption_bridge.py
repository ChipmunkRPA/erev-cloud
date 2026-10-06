"""RPT-34 ``adoption_bridge`` Adoption bridge (SCREENS_B §5.6.6 RPT-34; ASC 606-10-65-1(h), (i);
POLICIES POL-218, POL-005, POL-007, POL-008; ENGINE_SPEC_B §13.2.4 S13-R-07 to S13-R-11; 01 D-14a;
04 T-SL-04, T-ENG-03, T-CON-09; 03 REQ-BK-007; answer key ONB-S11-MODRETRO-OWN; BUILD_SPEC RPS-12).

For one entity that keeps the ``LEGACY`` book and a date of initial application — the first day of
a period of the entity's calendar, on or after its first ``ASC606`` period (default: that period's
first day) — the report compares, per contract the entity contracted, the figures under legacy
GAAP and under Topic 606 at the end of the day before that date:

- ``revenue_legacy``: the pre-standard revenue the ``LEGACY`` book holds for the contract through
  that day — debit less credit of its T-SL-04 ``PRE_STANDARD_REVENUE`` lines whose origin period
  (else posting period) ends on or before it (S13-R-08), recorded by the run's ``known_at``.
- ``revenue_asc606``: the cumulative Topic 606 revenue of the contract's obligations at that
  period end — the ``revenue_cum`` nodes of the latest ``ASC606`` contract version (T-ENG-03), the
  source of every balance below (``tie_outs.balances_at``).
- ``cumulative_effect`` = ``revenue_asc606`` − ``revenue_legacy``, the amount ASC 606-10-65-1(h)
  carries to retained earnings.
- ``contract_liability_legacy``: the amount billed to that day (the ``billed_cum`` nodes of the
  same version) less ``revenue_legacy`` when positive — deferred revenue under legacy GAAP. When
  it is negative the legacy position is an unbilled receivable, shown in section 2. [J] Legacy
  GAAP presents no contract asset: the whole legacy position is one of those two captions.
- ``contract_liability_asc606`` and ``asset_asc606`` (contract asset plus unbilled receivable):
  the presented ``ASC606`` balances at that period end.

Section 1 "Cumulative effect by contract" lists every contract with an ``ASC606`` version in the
disclosures (E-06 ``ACTIVE``, ``COMPLETED``, ``TERMINATED``) and a figure on either side,
``row_key`` ``contract:<external id>``; section 2 "Line-item comparison" (65-1(i)) one row per
line and currency, ``row_key`` ``line:<LINE>`` (``:<ISO>`` when several currencies):
``legacy_amount``, ``asc606_amount`` and ``effect`` = Topic 606 − legacy GAAP. The ``LEGACY`` book
records no contract cost asset, so that line's legacy amount and effect are empty, never 0.00.
Amounts are in each contract's transaction currency (no currency view). Control totals: the
contract count, the three revenue totals per currency, the date and the ``as_of`` day. A contract
whose pre-standard revenue stands against no ``ASC606`` version in the disclosures (a draft, or
not a contract under Topic 606) has no billed amount to read and is not listed; the control totals
``legacy_only_contract_count`` and ``legacy_only_revenue`` state what stays outside the bridge.

The report posts nothing: the cumulative-effect adjustment is exported for a manually approved
journal and no 1.0 posting uses the ``RETAINED_EARNINGS`` role (D-14a; REQ-BK-007).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.stages.s01_canonicalize.convert import obligation_subject_key
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    customer,
    entity_book,
    obligation_version,
    period,
    subledger_line,
)
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.out_of_period_register import refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, BalanceRow, EntityRef, PeriodRef
from erev_api.enums import BookCode
from erev_api.explain import store
from erev_api.uow import UnitOfWork

CODE: Final = "adoption_bridge"
PRIMARY: Final = BookCode.ASC606.value
LEGACY: Final = BookCode.LEGACY.value
PRE_STANDARD_ROLE: Final = "PRE_STANDARD_REVENUE"  # E-01; JET-15 debit (S13-R-08)
REVENUE_NODE: Final = "revenue_cum"  # T-ENG-03 measure per obligation and period
BILLED_NODE: Final = "billed_cum"
DATE_KEY: Final = "date_of_initial_application"
CONTRACT_PREFIX: Final = "contract:"
LINE_PREFIX: Final = "line:"
LINES: Final = (
    "REVENUE",
    "CONTRACT_LIABILITY",
    "CONTRACT_ASSET",
    "UNBILLED_RECEIVABLE",
    "COST_ASSETS",
)
LINE_LABELS: Final[Mapping[str, str]] = {
    "REVENUE": "Revenue",
    "CONTRACT_LIABILITY": "Contract liability",
    "CONTRACT_ASSET": "Contract asset",
    "UNBILLED_RECEIVABLE": "Unbilled receivable",
    "COST_ASSETS": "Contract cost assets",
}
ENTITY_REQUIRED: Final = "Choose an entity that keeps the Legacy book."
DATE_TOO_EARLY: Final = "Choose a date on or after the first ASC 606 period."
DATE_NOT_PERIOD_START: Final = "Choose the first day of a period of the entity's calendar."
COLUMNS: Final = (
    Column("section", "Section", "integer"),
    Column("contract_external_id", "Contract", "code"),
    Column("customer_name", "Customer", "text"),
    Column("currency", "Currency", "code"),
    Column("revenue_legacy", "Revenue to date, legacy GAAP", "money"),
    Column("revenue_asc606", "Revenue to date, ASC 606", "money"),
    Column("cumulative_effect", "Cumulative effect", "money"),
    Column("contract_liability_legacy", "Contract liability, legacy GAAP", "money"),
    Column("contract_liability_asc606", "Contract liability, ASC 606", "money"),
    Column("asset_asc606", "Contract asset and unbilled receivable, ASC 606", "money"),
    Column("line_code", "Line code", "code"),
    Column("line_label", "Line item", "text"),
    Column("legacy_amount", "Under legacy GAAP", "money"),
    Column("asc606_amount", "Under Topic 606", "money"),
    Column("effect", "Effect", "money"),
)


@dataclass(frozen=True, slots=True)
class Source:
    """One contract at the end of the day before the date of initial application — the input of
    ``dataset_rows``. Amounts in the contract's transaction currency."""

    contract_external_id: str
    customer_name: str | None
    currency: str
    revenue_legacy: Decimal = ZERO
    revenue_asc606: Decimal = ZERO
    billed: Decimal = ZERO
    contract_liability: Decimal = ZERO
    contract_asset: Decimal = ZERO
    unbilled_receivable: Decimal = ZERO
    cost_assets: Decimal = ZERO

    @property
    def cumulative_effect(self) -> Decimal:
        return self.revenue_asc606 - self.revenue_legacy

    def has_figure(self) -> bool:
        return any(
            value != 0
            for value in (
                self.revenue_legacy,
                self.revenue_asc606,
                self.billed,
                self.contract_liability,
                self.contract_asset,
                self.unbilled_receivable,
                self.cost_assets,
            )
        )


def legacy_position(billed: Decimal, revenue_legacy: Decimal) -> tuple[Decimal, Decimal]:
    """(contract liability, unbilled receivable) under legacy GAAP: billed less revenue when
    positive is deferred revenue; revenue less billed when positive an unbilled receivable. Pure."""
    net = billed - revenue_legacy
    return (net, ZERO) if net >= 0 else (ZERO, -net)


def application_date(
    given: object, *, first_asc606: PeriodRef, periods: Sequence[PeriodRef]
) -> tuple[date, PeriodRef | None]:
    """(date of initial application, the period that ends the day before it; None when the date
    opens the calendar). ``given`` None takes the first day of the first ASC 606 period. 422 on a
    date before that period or inside a period. Pure."""
    day = first_asc606.start if given is None else date.fromisoformat(str(given))
    if day < first_asc606.start:
        raise tie_outs.invalid(DATE_KEY, DATE_TOO_EARLY)
    if all(item.start != day for item in periods):
        raise tie_outs.invalid(DATE_KEY, DATE_NOT_PERIOD_START)
    before = [item for item in periods if item.end == day - timedelta(days=1)]
    return day, (before[0] if before else None)


def measure_at(
    nodes: Mapping[tuple[str, str], Sequence[tuple[str, Decimal]]],
    measure: str,
    subject: str,
    period_key: str,
) -> Decimal:
    """The value of a per-period T-ENG-03 measure at ``period_key``: its node at that period, else
    the latest earlier one, else 0 (a period after the last node holds the last node's value, as
    ``tie_outs.balances_at`` reads balances). Pure."""
    value = ZERO
    for key, amount in nodes.get((measure, subject), ()):
        if key > period_key:  # period keys sort in period order
            break
        value = amount
    return value


def dataset_rows(
    found: Iterable[Source], legacy_only: Iterable[Source] = ()
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows of sections 1 and 2, control totals). ``legacy_only`` are the contracts the
    ``LEGACY`` book holds without an ``ASC606`` version in the disclosures: counted in the control
    totals, never listed. Pure."""
    listed = sorted(
        (item for item in found if item.has_figure()), key=lambda item: item.contract_external_id
    )
    rows: list[dict[str, Any]] = []
    # per currency: line → [legacy GAAP, Topic 606]
    lines: dict[str, dict[str, list[Decimal]]] = {}
    for item in listed:
        money = _money_of(item.currency)
        liability, unbilled = legacy_position(item.billed, item.revenue_legacy)
        rows.append(
            {
                "row_key": f"{CONTRACT_PREFIX}{item.contract_external_id}",
                "section": 1,
                "contract_external_id": item.contract_external_id,
                "customer_name": item.customer_name,
                "currency": item.currency,
                "revenue_legacy": money(item.revenue_legacy),
                "revenue_asc606": money(item.revenue_asc606),
                "cumulative_effect": money(item.cumulative_effect),
                "contract_liability_legacy": money(liability),
                "contract_liability_asc606": money(item.contract_liability),
                "asset_asc606": money(item.contract_asset + item.unbilled_receivable),
            }
        )
        into = lines.setdefault(item.currency, {code: [ZERO, ZERO] for code in LINES})
        for code, legacy, topic_606 in (
            ("REVENUE", item.revenue_legacy, item.revenue_asc606),
            ("CONTRACT_LIABILITY", liability, item.contract_liability),
            ("CONTRACT_ASSET", ZERO, item.contract_asset),
            ("UNBILLED_RECEIVABLE", unbilled, item.unbilled_receivable),
            ("COST_ASSETS", ZERO, item.cost_assets),
        ):
            into[code][0] += legacy
            into[code][1] += topic_606
    mixed = len(lines) > 1
    for currency in sorted(lines):
        money = _money_of(currency)
        for code in LINES:
            legacy, topic_606 = lines[currency][code]
            recorded = code != "COST_ASSETS"  # the LEGACY book records no contract cost asset
            rows.append(
                {
                    "row_key": f"{LINE_PREFIX}{code}:{currency}"
                    if mixed
                    else f"{LINE_PREFIX}{code}",
                    "section": 2,
                    "currency": currency,
                    "line_code": code,
                    "line_label": LINE_LABELS[code],
                    "legacy_amount": money(legacy) if recorded else None,
                    "asc606_amount": money(topic_606),
                    "effect": money(topic_606 - legacy) if recorded else None,
                }
            )
    revenue = {currency: found_lines["REVENUE"] for currency, found_lines in lines.items()}
    outside = [item for item in legacy_only if item.revenue_legacy != 0]
    outside_revenue: dict[str, Decimal] = {}
    for item in outside:
        tie_outs.add(outside_revenue, item.currency, item.revenue_legacy)
    totals = {
        "contract_count": len(listed),
        "revenue_legacy_total": tie_outs.by_currency({c: v[0] for c, v in revenue.items()}),
        "revenue_asc606_total": tie_outs.by_currency({c: v[1] for c, v in revenue.items()}),
        "cumulative_effect_total": tie_outs.by_currency(
            {c: v[1] - v[0] for c, v in revenue.items()}
        ),
        "legacy_only_contract_count": len(outside),
        "legacy_only_revenue": tie_outs.by_currency(outside_revenue),
    }
    return rows, totals


def _money_of(currency: str) -> Any:
    return lambda amount: tie_outs.money(amount, currency)


# --- reads --------------------------------------------------------------------------------------


def _kept_books(session: Session, entity: EntityRef) -> dict[str, UUID]:
    """Book code → first period id of the books the entity keeps (T-REF-05, enabled)."""
    return {
        str(book_code): UUID(str(first_period_id))
        for book_code, first_period_id in session.execute(
            select(entity_book.c.book_code, entity_book.c.first_period_id).where(
                entity_book.c.entity_id == entity.id, entity_book.c.is_enabled.is_(True)
            )
        )
    }


def _legacy_revenue(
    session: Session,
    params: ReportParams,
    entity: EntityRef,
    *,
    through: date,
    contract_id: UUID | None,
) -> dict[UUID, Source]:
    """Per contract the pre-standard revenue of the ``LEGACY`` book through ``through``, by origin
    period, as a ``Source`` that carries only the legacy side."""
    origin = period.alias("origin_period")
    amount = func.sum(subledger_line.c.amount_txn).label("amount")
    statement = (
        select(
            subledger_line.c.contract_id,
            contract.c.external_id,
            customer.c.name.label("customer_name"),
            subledger_line.c.txn_currency,
            amount,
        )
        .select_from(
            subledger_line.join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            )
            .outerjoin(
                customer,
                and_(
                    customer.c.tenant_id == contract.c.tenant_id,
                    customer.c.id == contract.c.customer_id,
                ),
            )
            .outerjoin(
                origin,
                and_(
                    origin.c.tenant_id == subledger_line.c.tenant_id,
                    origin.c.id == subledger_line.c.origin_period_id,
                ),
            )
        )
        .where(
            subledger_line.c.book_code == LEGACY,
            subledger_line.c.entity_id == entity.id,
            subledger_line.c.account_role == PRE_STANDARD_ROLE,
            subledger_line.c.recorded_at <= params.known_at,
            func.coalesce(origin.c.end_date, subledger_line.c.period_end_date) <= through,
        )
        .group_by(
            subledger_line.c.contract_id,
            contract.c.external_id,
            customer.c.name,
            subledger_line.c.txn_currency,
        )
        .order_by(contract.c.external_id)
    )
    if contract_id is not None:
        statement = statement.where(subledger_line.c.contract_id == contract_id)
    return {
        UUID(str(row["contract_id"])): Source(
            contract_external_id=str(row["external_id"]),
            customer_name=None if row["customer_name"] is None else str(row["customer_name"]),
            currency=str(row["txn_currency"]).strip(),
            revenue_legacy=Decimal(row["amount"]),
        )
        for row in session.execute(statement).mappings()
    }


def _version_nodes(
    session: Session, version_id: UUID
) -> dict[tuple[str, str], list[tuple[str, Decimal]]]:
    """(measure, subject) → [(period key, value)] in period order, for the two per-obligation
    measures of the version's trace."""
    trace = store.load_trace(session, version_id)
    nodes: dict[tuple[str, str], list[tuple[str, Decimal]]] = {}
    if trace is None:
        return nodes
    for node in trace.nodes:
        measure, _, rest = node.id.partition(":")
        if measure not in (REVENUE_NODE, BILLED_NODE):
            continue
        subject, _, period_key = rest.rpartition(":")
        if period_key == "-":  # the version-date node; the period nodes carry the history
            continue
        nodes.setdefault((measure, subject), []).append((period_key, Decimal(str(node.value))))
    for values in nodes.values():
        values.sort()
    return nodes


def _obligation_keys(
    session: Session, balances: Sequence[BalanceRow]
) -> dict[tuple[UUID, UUID], list[str]]:
    """(contract version, contract) → the obligation keys of that contract at that version."""
    version_ids = sorted({row.version_id for row in balances}, key=str)
    if not version_ids:
        return {}
    found: dict[tuple[UUID, UUID], list[str]] = {}
    for version_id, contract_id, key in session.execute(
        select(
            obligation_version.c.contract_version_id,
            obligation_version.c.contract_id,
            obligation_version.c.obligation_key,
        )
        .where(obligation_version.c.contract_version_id.in_(version_ids))
        .order_by(obligation_version.c.obligation_key)
    ):
        found.setdefault((UUID(str(version_id)), UUID(str(contract_id))), []).append(str(key))
    return found


def sources(
    session: Session,
    params: ReportParams,
    entity: EntityRef,
    *,
    at: PeriodRef,
    contract_id: UUID | None,
) -> tuple[list[Source], list[Source]]:
    """(every contract of the entity with an ``ASC606`` version in the disclosures, with its
    figures at the end of ``at``; the contracts the ``LEGACY`` book holds without one)."""
    cutoff = tie_outs.cutoff_for(session, params)
    balances = tie_outs.balances_at(
        session,
        entity_ids=(entity.id,),
        book_code=PRIMARY,
        period_keys={entity.id: at},
        cutoff=cutoff,
        contract_id=contract_id,
        params=params,
    )
    legacy = _legacy_revenue(session, params, entity, through=at.end, contract_id=contract_id)
    keys = _obligation_keys(session, balances)
    traces: dict[UUID, dict[tuple[str, str], list[tuple[str, Decimal]]]] = {}
    found: list[Source] = []
    for row in balances:
        if row.version_id not in traces:
            traces[row.version_id] = _version_nodes(session, row.version_id)
        nodes = traces[row.version_id]
        subjects = [
            obligation_subject_key(row.external_id, key)
            for key in keys.get((row.version_id, row.contract_id), ())
        ]
        held = legacy.pop(row.contract_id, None)
        found.append(
            Source(
                contract_external_id=row.external_id,
                customer_name=row.customer_name,
                currency=row.currency,
                revenue_legacy=ZERO if held is None else held.revenue_legacy,
                revenue_asc606=sum(
                    (measure_at(nodes, REVENUE_NODE, subject, at.key) for subject in subjects), ZERO
                ),
                billed=sum(
                    (measure_at(nodes, BILLED_NODE, subject, at.key) for subject in subjects), ZERO
                ),
                contract_liability=row.value("contract_liability"),
                contract_asset=row.value("contract_asset"),
                unbilled_receivable=row.value("unbilled_receivable"),
                cost_assets=row.value("cost_asset_carrying"),
            )
        )
    # what is left: contracts the LEGACY book holds without an ASC 606 version in the disclosures
    return found, sorted(legacy.values(), key=lambda item: item.contract_external_id)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    session = uow.session
    entities = tie_outs.entities(session, params.entity_ids, params=params)
    if len(entities) != 1:
        raise tie_outs.invalid("entity_codes", ENTITY_REQUIRED)
    (entity,) = entities
    kept = _kept_books(session, entity)
    if LEGACY not in kept or PRIMARY not in kept:
        raise tie_outs.invalid("entity_codes", ENTITY_REQUIRED)
    calendar = tie_outs.calendars(session, entities, params=params)[entity.id]
    first = next(item for item in calendar.periods if item.id == kept[PRIMARY])
    day, at = application_date(
        params.parameters.get(DATE_KEY), first_asc606=first, periods=calendar.periods
    )
    contract_id = tie_outs.contract_named(session, params)
    found: list[Source] = []
    legacy_only: list[Source] = []
    if at is not None:  # a date that opens the calendar has no day before it: nothing to date
        found, legacy_only = sources(session, params, entity, at=at, contract_id=contract_id)
    rows, totals = dataset_rows(found, legacy_only)
    totals[DATE_KEY] = day.isoformat()
    totals["as_of"] = None if at is None else at.end.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "DATE_NOT_PERIOD_START",
    "DATE_TOO_EARLY",
    "ENTITY_REQUIRED",
    "LINES",
    "LINE_LABELS",
    "Source",
    "application_date",
    "build",
    "dataset_rows",
    "legacy_position",
    "measure_at",
    "sources",
]
