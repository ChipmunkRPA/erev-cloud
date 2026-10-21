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
Transaction view preserves each contract's currency. Functional view uses recorded LEGACY
functional revenue, reconciled dated primary revenue and engine functional balances. Foreign
legacy liabilities/unbilled balances stay unavailable until supplied carrying evidence exists;
line totals for those captions are also unavailable, never partial totals or artificial zeroes.
Reporting view translates each historical functional revenue movement at its period average
and ending balances at the closing rate. Legacy balance captions are translated separately
from revenue, preserving unavailable positions. Control totals include the contract count,
revenue totals per currency, the date and the ``as_of`` day. A contract
whose pre-standard revenue stands against no ``ASC606`` version in the disclosures (a draft, or
not a contract under Topic 606) has no billed amount to read and is not listed; the control totals
``legacy_only_contract_count`` and ``legacy_only_revenue`` state what stays outside the bridge.

Same-source runs retain per-contract comparison inputs, final legacy-only membership, currency
basis, date and source/rate evidence. Optional sourced functional carrying inputs supplement
endpoint positions without changing the ledger. Bound runs rebuild sections and totals without
live reads.

The report posts nothing: the cumulative-effect adjustment is exported for a manually approved
journal and no 1.0 posting uses the ``RETAINED_EARNINGS`` role (D-14a; REQ-BK-007).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from erev_engine.stages.s01_canonicalize.convert import obligation_subject_key
from erev_engine.trace import Trace
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
from erev_api.domain.reports import functional_balances, reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.out_of_period_register import refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, BalanceRow, EntityRef, PeriodRef
from erev_api.enums import BookCode
from erev_api.explain import store
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE: Final = "adoption_bridge"
EVIDENCE: Final = "adoption_bridge_inputs_v1"
PRIMARY: Final = BookCode.ASC606.value
LEGACY: Final = BookCode.LEGACY.value
PRE_STANDARD_ROLE: Final = "PRE_STANDARD_REVENUE"  # E-01; JET-15 debit (S13-R-08)
REVENUE_NODE: Final = "revenue_cum"  # T-ENG-03 measure per obligation and period
BILLED_NODE: Final = "billed_cum"
DATE_KEY: Final = "date_of_initial_application"
POSITIONS_KEY: Final = "legacy_functional_positions"
POSITION_UNAVAILABLE: Final = "Historical functional legacy position unavailable"
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
    ``dataset_rows``. Amounts use the selected currency; reporting income preserves its
    historical period basis independently of translated ending balances."""

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
    legacy_position_available: bool = True
    legacy_position_values: tuple[Decimal, Decimal] | None = None
    legacy_position_reference: str | None = None

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
                *(self.legacy_position_values or ()),
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
    unavailable = {item.currency for item in listed if not item.legacy_position_available}
    for item in listed:
        money = _money_of(item.currency)
        liability, unbilled = item.legacy_position_values or legacy_position(
            item.billed, item.revenue_legacy
        )
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
                "contract_liability_legacy": money(liability)
                if item.legacy_position_available
                else None,
                "contract_liability_asc606": money(item.contract_liability),
                "asset_asc606": money(item.contract_asset + item.unbilled_receivable),
                **(
                    {"legacy_position_basis": POSITION_UNAVAILABLE}
                    if not item.legacy_position_available
                    else {
                        "legacy_position_basis": (
                            f"Supplied carrying balance: {item.legacy_position_reference}"
                        )
                    }
                    if item.legacy_position_reference
                    else {}
                ),
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
            recorded = code != "COST_ASSETS" and not (
                currency in unavailable and code in {"CONTRACT_LIABILITY", "UNBILLED_RECEIVABLE"}
            )  # the LEGACY book records no contract cost asset
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
                    **(
                        {"legacy_position_basis": POSITION_UNAVAILABLE}
                        if currency in unavailable
                        and code in {"CONTRACT_LIABILITY", "UNBILLED_RECEIVABLE"}
                        else {}
                    ),
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
    if unavailable:
        totals["legacy_position_unavailable_contract_count"] = sum(
            not item.legacy_position_available for item in listed
        )
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
    functional = params.parameters.get("currency_view") == "functional"
    currency = subledger_line.c.functional_currency if functional else subledger_line.c.txn_currency
    amount = func.sum(
        subledger_line.c.amount_functional if functional else subledger_line.c.amount_txn
    ).label("amount")
    statement = (
        select(
            subledger_line.c.contract_id,
            contract.c.external_id,
            customer.c.name.label("customer_name"),
            currency.label("currency"),
            amount,
            func.array_agg(subledger_line.c.id).label("line_ids"),
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
            tie_outs.line_recorded_by(params),
            func.coalesce(origin.c.end_date, subledger_line.c.period_end_date) <= through,
        )
        .group_by(
            subledger_line.c.contract_id,
            contract.c.external_id,
            customer.c.name,
            currency,
        )
        .order_by(contract.c.external_id)
    )
    if contract_id is not None:
        statement = statement.where(subledger_line.c.contract_id == contract_id)
    rows = session.execute(statement).mappings().all()
    tie_outs.record_members(
        params,
        "adoption_legacy_subledger_lines",
        (line_id for row in rows for line_id in row["line_ids"]),
    )
    if functional and any(
        str(row["currency"]).strip() != entity.functional_currency for row in rows
    ):
        raise tie_outs.invalid(
            "currency_view", "Legacy posted functional currency differs from entity."
        )
    return {
        UUID(str(row["contract_id"])): Source(
            contract_external_id=str(row["external_id"]),
            customer_name=None if row["customer_name"] is None else str(row["customer_name"]),
            currency=str(row["currency"]).strip(),
            revenue_legacy=Decimal(row["amount"]),
        )
        for row in rows
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


def functional_revenue_at(
    trace: Trace,
    subjects: Sequence[str],
    period_key: str,
    currency: str,
) -> Decimal:
    """Read dated functional revenue only when its transaction population reconciles.

    Stage 12 relief can differ from gross stage 09 revenue. New cumulative FX nodes retain
    their transaction quantity so a report can reject that mismatch, including old traces
    without enough evidence, rather than display relief as revenue.
    """
    total = ZERO
    for subject in subjects:

        def latest(measure: str, subject: str = subject) -> Any:
            prefix = f"{measure}:{subject}:"
            nodes = [
                node
                for node in trace.nodes
                if node.id.startswith(prefix)
                and node.id[len(prefix) :].startswith("FY")
                and node.id[len(prefix) :] <= period_key
            ]
            return max(nodes, key=lambda node: node.id, default=None)

        txn = latest(REVENUE_NODE)
        functional = latest("revenue_functional")
        expected = ZERO if txn is None else Decimal(txn.value)
        if functional is None:
            if expected == 0:
                continue
            raise tie_outs.invalid("currency_view", "Historical functional revenue is missing.")
        params = functional.params
        if (
            functional.currency != currency
            or "amount_txn" not in params
            or "txn_minor_unit" not in params
            or txn is None
            or params.get("txn_currency") != txn.currency
            or Decimal(params["amount_txn"]).scaleb(-int(params["txn_minor_unit"])) != expected
        ):
            raise tie_outs.invalid(
                "currency_view",
                "Functional revenue does not reconcile to the historical revenue population; "
                "recompute or review the source.",
            )
        if functional.id.rpartition(":")[2] < txn.id.rpartition(":")[2]:
            raise tie_outs.invalid(
                "currency_view", "Historical functional revenue endpoint is incomplete."
            )
        total += Decimal(functional.value)
    return total


def require_dated_revenue(trace: Trace, subjects: Sequence[str], period_key: str) -> None:
    """Do not translate an undated imported cumulative baseline as current-period income."""
    nodes = {node.id: node for node in trace.nodes}
    pending = [
        node.id
        for node in trace.nodes
        for subject in subjects
        if node.id.startswith(f"{REVENUE_NODE}:{subject}:FY")
        and node.id.rpartition(":")[2] <= period_key
    ]
    seen: set[str] = set()
    while pending:
        key = pending.pop()
        if key in seen or key not in nodes:
            continue
        seen.add(key)
        node = nodes[key]
        if node.id.startswith("opening_revenue_cum@") and Decimal(node.value) != 0:
            raise tie_outs.invalid(
                "currency_view",
                "Historical reporting translation requires dated income; an imported cumulative "
                "opening revenue amount has no period allocation.",
            )
        pending.extend(ref for ref in node.inputs if isinstance(ref, str))


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
    require_income_history: bool = False,
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
    functional = params.parameters.get("currency_view") == "functional"
    translated = (
        {
            row.contract_id: row
            for row in functional_balances.read(
                session,
                params,
                balances,
                entities=(entity,),
                periods={entity.id: at},
                book_code=PRIMARY,
            )
        }
        if functional
        else {}
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
        displayed = translated.get(row.contract_id, row)
        revenue = sum(
            (measure_at(nodes, REVENUE_NODE, subject, at.key) for subject in subjects), ZERO
        )
        foreign = functional and row.currency != entity.functional_currency
        if foreign or require_income_history:
            trace = store.load_trace(session, row.version_id)
            if trace is None:
                raise tie_outs.invalid("currency_view", "Historical functional trace is missing.")
            if require_income_history:
                require_dated_revenue(trace, subjects, at.key)
            if foreign:
                revenue = functional_revenue_at(trace, subjects, at.key, entity.functional_currency)
        held = legacy.pop(row.contract_id, None)
        found.append(
            Source(
                contract_external_id=row.external_id,
                customer_name=row.customer_name,
                currency=displayed.currency,
                revenue_legacy=ZERO if held is None else held.revenue_legacy,
                revenue_asc606=revenue,
                billed=sum(
                    (measure_at(nodes, BILLED_NODE, subject, at.key) for subject in subjects), ZERO
                ),
                contract_liability=displayed.value("contract_liability"),
                contract_asset=displayed.value("contract_asset"),
                unbilled_receivable=displayed.value("unbilled_receivable"),
                cost_assets=displayed.value("cost_asset_carrying"),
                legacy_position_available=not foreign,
            )
        )
    # what is left: contracts the LEGACY book holds without an ASC 606 version in the disclosures
    return found, sorted(legacy.values(), key=lambda item: item.contract_external_id)


def translate_sources(
    items: Sequence[Source],
    closing: reporting_currency.Translation,
    entity_id: UUID,
    revenue: Mapping[str, tuple[Decimal, Decimal]],
) -> list[Source]:
    """Translate balances independently of accumulated historical revenue movements."""
    translated: list[Source] = []
    for item in items:
        if item.currency != closing.rates[entity_id]["base_currency"]:
            raise tie_outs.invalid(
                "currency_view", "Reporting translation requires functional amounts."
            )
        legacy, primary = revenue.get(item.contract_external_id, (ZERO, ZERO))
        position = None
        if item.legacy_position_available:
            liability, unbilled = item.legacy_position_values or legacy_position(
                item.billed, item.revenue_legacy
            )
            position = (closing.amount(entity_id, liability), closing.amount(entity_id, unbilled))
        translated.append(
            replace(
                item,
                currency=closing.currency,
                revenue_legacy=legacy,
                revenue_asc606=primary,
                billed=closing.amount(entity_id, item.billed)
                if item.legacy_position_available
                else ZERO,
                contract_liability=closing.amount(entity_id, item.contract_liability),
                contract_asset=closing.amount(entity_id, item.contract_asset),
                unbilled_receivable=closing.amount(entity_id, item.unbilled_receivable),
                cost_assets=closing.amount(entity_id, item.cost_assets),
                legacy_position_values=position,
            )
        )
    return translated


def reporting_sources(
    uow: UnitOfWork,
    params: ReportParams,
    entity: EntityRef,
    *,
    at: PeriodRef,
    periods: Sequence[PeriodRef],
    contract_id: UUID | None,
) -> tuple[list[Source], list[Source]]:
    """Translate each period's change in cumulative income at its approved average rate.

    Classification into included/legacy-only contracts is decided at the final endpoint;
    revenue histories use both populations so a change of classification cannot lose income.
    """
    functional = replace(params, parameters={**params.parameters, "currency_view": "functional"})
    closing = reporting_currency.rates_for_period(
        uow.session,
        params,
        tenant_id=uow.principal.tenant_id,
        entities=(entity,),
        periods={entity.id: at},
        evidence_key="adoption_closing_rate_v1",
    )
    previous: dict[str, tuple[Decimal, Decimal]] = {}
    revenue: dict[str, tuple[Decimal, Decimal]] = {}
    found: list[Source] = []
    outside: list[Source] = []
    for endpoint in sorted((p for p in periods if p.end <= at.end), key=lambda p: p.end):
        found, outside = sources(
            uow.session,
            functional,
            entity,
            at=endpoint,
            contract_id=contract_id,
            require_income_history=closing.currency != entity.functional_currency,
        )
        current = {
            item.contract_external_id: (item.revenue_legacy, item.revenue_asc606)
            for item in (*found, *outside)
        }
        changes = {
            key: tuple(
                now - old
                for now, old in zip(
                    current.get(key, (ZERO, ZERO)), previous.get(key, (ZERO, ZERO)), strict=True
                )
            )
            for key in current.keys() | previous.keys()
        }
        if any(any(value != 0 for value in values) for values in changes.values()):
            average = reporting_currency.rates_for_period(
                uow.session,
                params,
                tenant_id=uow.principal.tenant_id,
                entities=(entity,),
                periods={entity.id: endpoint},
                rate_type="average",
                target_currency=closing.currency,
                evidence_key=f"adoption_average_rate_v1:{endpoint.key}",
            )
            for key, (legacy, primary) in changes.items():
                before = revenue.get(key, (ZERO, ZERO))
                revenue[key] = (
                    before[0] + average.amount(entity.id, legacy),
                    before[1] + average.amount(entity.id, primary),
                )
        previous = current
    found = supplied_positions(found, params, entity.functional_currency, at.end)
    return (
        translate_sources(found, closing, entity.id, revenue),
        translate_sources(outside, closing, entity.id, revenue),
    )


def supplied_positions(
    found: Sequence[Source], params: ReportParams, currency: str, as_of: date | None
) -> list[Source]:
    """Admit explicitly sourced endpoint carrying positions, never infer foreign balances.

    Membership comes from the authorized report population. Inputs are report evidence,
    not ledger postings; their source references remain visible in retained rows and exports.
    """
    records = params.parameters.get(POSITIONS_KEY) or []
    if not records:
        return list(found)

    def refuse(message: str) -> Problem:
        return tie_outs.invalid(POSITIONS_KEY, message)

    if params.parameters.get("currency_view", "transaction") == "transaction":
        raise refuse("Supplied functional balances require Functional or Reporting currency.")
    if as_of is None:
        raise refuse("There is no prior period for these carrying balances.")
    if not isinstance(records, list) or len(records) > 500:
        raise refuse("Supply at most 500 contract carrying positions.")
    members = {item.contract_external_id for item in found}
    positions: dict[str, tuple[Decimal, Decimal, str]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise refuse("Each carrying position must identify a contract and source.")
        key = record.get("contract_external_id")
        if not isinstance(key, str) or key not in members or key in positions:
            raise refuse("Each contract must occur once within the selected report population.")
        if record.get("currency") != currency or record.get("as_of") != as_of.isoformat():
            raise refuse(
                "Carrying balances must use the entity functional currency and prior period end."
            )
        reference = record.get("source_reference")
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 500:
            raise refuse(
                "Supply a source reference for each carrying balance (up to 500 characters)."
            )
        amounts = []
        for field in ("contract_liability", "unbilled_receivable"):
            raw = record.get(field)
            if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,18}(?:\.[0-9]{1,8})?", raw):
                raise refuse("Carrying amounts must be nonnegative decimal strings.")
            amount = Decimal(raw)
            if amount != tie_outs.quantized(amount, currency):
                raise refuse("Carrying amounts must match the currency's minor unit precision.")
            amounts.append(amount)
        if all(amount > 0 for amount in amounts):
            raise refuse(
                "A net legacy position cannot be both a liability and an unbilled receivable."
            )
        positions[key] = (amounts[0], amounts[1], reference.strip())
    return [
        replace(
            item,
            legacy_position_available=True,
            legacy_position_values=positions[item.contract_external_id][:2],
            legacy_position_reference=positions[item.contract_external_id][2],
        )
        if item.contract_external_id in positions
        else item
        for item in found
    ]


def restore_sources(records: Sequence[Mapping[str, Any]]) -> list[Source]:
    amounts = (
        "revenue_legacy",
        "revenue_asc606",
        "billed",
        "contract_liability",
        "contract_asset",
        "unbilled_receivable",
        "cost_assets",
    )
    found: list[Source] = []
    for record in records:
        values = dict(record)
        for key in amounts:
            values[key] = Decimal(values[key])
        position = values.get("legacy_position_values")
        values["legacy_position_values"] = (
            None if position is None else (Decimal(position[0]), Decimal(position[1]))
        )
        found.append(Source(**values))
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    view = str(params.parameters.get("currency_view") or "transaction")
    if view not in {"transaction", "functional", "reporting"}:
        raise tie_outs.invalid(
            "currency_view", "Choose Transaction, Functional or Reporting currency."
        )
    selection = {key: params.parameters.get(key) for key in (DATE_KEY, "contract_external_id")}
    if params.parameters.get(POSITIONS_KEY):
        selection[POSITIONS_KEY] = params.parameters[POSITIONS_KEY]
    if params.binding is not None:
        retained = tie_outs.bound_evidence(params, EVIDENCE)
        if retained["tenant_id"] != str(uow.principal.tenant_id) or set(retained["entity_ids"]) != {
            str(entity) for entity in params.entity_ids
        }:
            raise Problem("forbidden", "The retained adoption population exceeds report scope.")
        if retained["currency_view"] != view:
            raise tie_outs.invalid(
                "currency_view", "The retained bridge uses another currency view."
            )
        if retained["selection"] != selection:
            raise tie_outs.invalid(
                DATE_KEY, "The retained bridge uses another date or contract selection."
            )
    else:
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
            if view == "reporting":
                found, legacy_only = reporting_sources(
                    uow,
                    params,
                    entity,
                    at=at,
                    periods=calendar.periods,
                    contract_id=contract_id,
                )
            else:
                found, legacy_only = sources(
                    session, params, entity, at=at, contract_id=contract_id
                )
        if view != "reporting" or at is None:
            found = supplied_positions(
                found, params, entity.functional_currency, None if at is None else at.end
            )
        retained = json.loads(
            canonical_bytes(
                {
                    "tenant_id": uow.principal.tenant_id,
                    "entity_ids": params.entity_ids,
                    "currency_view": view,
                    "selection": selection,
                    DATE_KEY: day.isoformat(),
                    "as_of": None if at is None else at.end.isoformat(),
                    "sources": [asdict(item) for item in found],
                    "legacy_only": [asdict(item) for item in legacy_only],
                }
            )
        )
        tie_outs.record_evidence(params, EVIDENCE, retained)
    rows, totals = dataset_rows(
        restore_sources(retained["sources"]), restore_sources(retained["legacy_only"])
    )
    totals[DATE_KEY] = retained[DATE_KEY]
    totals["as_of"] = retained["as_of"]
    columns = COLUMNS + (
        (Column("legacy_position_basis", "Legacy position basis", "text"),)
        if view != "transaction"
        else ()
    )
    return ReportData(columns=columns, rows=tuple(rows), control_totals=totals)


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
