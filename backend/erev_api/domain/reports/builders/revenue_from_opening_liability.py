"""RPT-04 ``revenue_from_opening_liability`` Revenue from the opening contract liability (SCREENS_B
§5.6.1 RPT-04; ENGINE_SPEC_B §15.2.2 S15-R-05, S15-INV-05; POLICIES POL-126; 03 REQ-RPT-007;
BUILD_SPEC RPS-3).

Per member contract and contracting entity: the opening contract liability at the end of the period
before the range (``tie_outs.balances_at``); revenue recognized = −Σ ``REVENUE`` subledger lines of
the range, plus the relief another entity's performance makes of this entity's liability (the
contracting side of an intercompany pair, entry kind ``INTERCOMPANY``: ENGINE_SPEC_B S12-R-03;
supervisor ruling R-72 (d), pending the accountant); revenue from the opening contract liability
= min(opening liability, revenue relief of the range), where relief is the net debit of the
role's revenue family — ``REVENUE_RECOGNITION`` and ``INTERCOMPANY`` lines of
``CONTRACT_LIABILITY``, net of negative revenue (POL-126 ``FIFO_WITHIN_CONTRACT``;
``contract_balance_rollforward.REVENUE_KINDS``). A contract appears when it has an opening
liability and revenue in the range.

Section 1 "Summary" gives one row ``summary:<ISO>`` per currency; section 2 "By contract" one row
``contract:<external id>:<entity code>``. The footnote names the resolved POL-126 option. No
tie-out.

D-87 L6-3-Q-23: the footnote names the option applied, ``FIFO_WITHIN_CONTRACT``. When an entity
resolves ``FIFO_WITHIN_POB``, the contract formula still applies and the footnote adds that
per-obligation consumption is not yet available. POB-attributed invoices (POL-126) are on the
backlog.

The opening where the period before the range is locked at the run's cutoff (ENGINE_SPEC_B
S15-R-20 rev 1.168; item RPT-ROLLFWD-LOCKED-CLOSING-1; the supervisor's ruling of 2026-10-02):
the lock's, as the contract balance roll-forward opens (``reports.locked_ends``) — the two
reports are one disclosure and state one opening. A contract that is not in the lock's opening
liability — one activated after the lock — contributes no revenue from the opening.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import subledger_line
from erev_api.domain.reports import locked_ends, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, PeriodRef, add
from erev_api.enums import BookCode
from erev_api.registry.resolve import resolve
from erev_api.uow import UnitOfWork

CODE: Final = "revenue_from_opening_liability"
POLICY: Final = "rollforward.opening_liability_consumption"
SUMMARY: Final = (
    "Revenue recognized in {range} that was included in the contract liability at the beginning "
    "of the period"
)
APPLIED: Final = "FIFO_WITHIN_CONTRACT"
FOOTNOTE: Final = (
    "Measured first-in first-out within each contract "
    "(accounting.rollforward.opening_liability_consumption = {option})."
)
FOOTNOTE_NOT_PER_OBLIGATION: Final = (
    "Measured first-in first-out within each contract ({applied} applied). The policy "
    "accounting.rollforward.opening_liability_consumption names {options}; per-obligation "
    "consumption is not yet available."
)
COLUMNS: Final = (
    Column("section", "Section", "integer"),
    Column("summary", "Summary", "text"),
    Column("contract_external_id", "Contract", "code"),
    Column("customer_name", "Customer", "text"),
    Column("entity_code", "Entity", "code"),
    Column("currency", "Currency", "code"),
    Column("opening_contract_liability", "Opening contract liability", "money"),
    Column("revenue_recognized", "Revenue recognized", "money"),
    Column("revenue_from_opening", "From opening contract liability", "money"),
)


def _activity(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    known_at: datetime,
    params: ReportParams,
) -> tuple[dict[tuple[UUID, UUID], Decimal], dict[tuple[UUID, UUID], Decimal]]:
    """(revenue, relief) per (contract, entity) over the range. S15-R-24 / frps3c-2 (Codex
    production-20260921-1004 R2): the line ids AND the amounts come from ONE statement — the
    population the sums consume IS the population recorded as ``members.subledger_line`` (the job
    runs READ COMMITTED; a ledger writer committing between two reads cannot split them); the
    per-(contract, entity, role, kind) sums are re-computed from those rows EXACTLY (Codex
    production-20260921-1035 C2: rational accumulation — ``Fraction`` of each stored amount, never a
    context-rounded ``Decimal`` sum, so a cancelling population is exactly zero in every order and
    the positive-group relief predicate cannot flip; the exact total is returned as a ``Decimal`` at
    the population's own scale), never a retained aggregate. Under a bound run the read carries the
    bound ids within today's scope and a bound id it does not return refuses by name (D4); an empty
    range records an explicit EMPTY membership (captured, not absent)."""
    period_ids = sorted({item.id for items in periods.values() for item in items}, key=str)
    revenue: dict[tuple[UUID, UUID], Decimal] = {}
    relief: dict[tuple[UUID, UUID], Decimal] = {}
    if not entity_ids or not period_ids:
        tie_outs.require_members(params, "subledger_line", ())
        tie_outs.record_members(params, "subledger_line", ())
        return revenue, relief
    statement = select(
        subledger_line.c.id,
        subledger_line.c.contract_id,
        subledger_line.c.entity_id,
        subledger_line.c.account_role,
        subledger_line.c.entry_kind,
        subledger_line.c.amount_txn,
    ).where(
        subledger_line.c.book_code == book_code,
        subledger_line.c.entity_id.in_(list(entity_ids)),
        subledger_line.c.period_id.in_(period_ids),
        subledger_line.c.recorded_at <= known_at,
        subledger_line.c.contract_id.is_not(None),
        subledger_line.c.account_role.in_((tie_outs.REVENUE, rollforward.LIABILITY_ROLE)),
        *tie_outs.bound_member_where(params, "subledger_line", subledger_line.c.id),
    )
    consumed: list[UUID] = []
    sums: dict[tuple[UUID, UUID, str, str], Fraction] = {}
    scale = 0  # the population's own scale (numeric(24,4) lines: at most 4)
    for row in session.execute(statement).mappings():
        consumed.append(UUID(str(row["id"])))
        group = (
            UUID(str(row["contract_id"])),
            UUID(str(row["entity_id"])),
            str(row["account_role"]),
            str(row["entry_kind"]),
        )
        amount = Decimal(row["amount_txn"])
        scale = max(scale, -int(amount.as_tuple().exponent))
        sums[group] = sums.get(group, Fraction(0)) + Fraction(amount)  # exact, order-independent
    tie_outs.require_members(params, "subledger_line", consumed)
    tie_outs.record_members(params, "subledger_line", consumed)
    exact_revenue: dict[tuple[UUID, UUID], Fraction] = {}
    family: dict[tuple[UUID, UUID], Fraction] = {}
    for (contract_id, entity_id, role, kind), total in sums.items():
        key = (contract_id, entity_id)
        if role == tie_outs.REVENUE:
            exact_revenue[key] = exact_revenue.get(key, Fraction(0)) - total
        elif kind in rollforward.REVENUE_KINDS:
            # the role's revenue family: relief net of negative revenue, whoever performed
            family[key] = family.get(key, Fraction(0)) + total
            if kind != rollforward.REVENUE_KIND:
                # the contracting side of an intercompany pair: revenue another entity
                # recognises against this entity's liability (S12-R-03; R-72 (d))
                exact_revenue[key] = exact_revenue.get(key, Fraction(0)) + total
    # the group rule, decided exactly: a family that nets to a credit relieves nothing
    exact_relief = {key: total for key, total in family.items() if total > 0}
    revenue.update({key: exact_decimal(value, scale) for key, value in exact_revenue.items()})
    relief.update({key: exact_decimal(value, scale) for key, value in exact_relief.items()})
    return revenue, relief


def exact_decimal(value: Fraction, scale: int) -> Decimal:
    """A rational total of stored amounts as the exact ``Decimal`` at ``scale`` (the amounts' own
    scale, so the value is an integer count of that unit): built from its digits, so no context
    precision or rounding applies — regardless of the caller's ``decimal`` context."""
    units = value * 10**scale
    if units.denominator != 1:  # cannot happen for amounts stored at ``scale``: refuse, never round
        raise ValueError(f"{value} is not a whole number of 10^-{scale} units")
    count = int(units)
    digits = tuple(int(d) for d in str(abs(count)))
    return Decimal((1 if count < 0 else 0, digits, -scale))


def footnote(resolved: Iterable[str]) -> str:
    """The footnote of the POL-126 options the run's entities resolve (D-87 L6-3-Q-23)."""
    others = sorted({str(option) for option in resolved} - {APPLIED})
    if not others:
        return FOOTNOTE.format(option=APPLIED)
    return FOOTNOTE_NOT_PER_OBLIGATION.format(applied=APPLIED, options=", ".join(others))


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, before = rollforward.ranges(session, params)
    cutoff = tie_outs.cutoff_for(session, params)
    opening = tie_outs.balances_at(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_keys=before,
        cutoff=cutoff,
        params=params,
        locked_ends=locked_ends.Reader(
            uow,
            params,
            book_code=book_code,
            cutoff=cutoff,
            entity_codes={item.id: item.code for item in found},
        ),
    )
    revenue, relief = _activity(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        periods=periods,
        known_at=params.known_at,
        params=params,
    )
    contracts: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Decimal]] = {}
    for row in opening:
        key = (row.contract_id, row.entity_id)
        liability = row.value("contract_liability")
        recognized = revenue.get(key, ZERO)
        if liability <= 0 or recognized == 0:
            continue
        from_opening = max(ZERO, min(liability, relief.get(key, ZERO)))
        contracts.append(
            {
                "row_key": f"contract:{row.external_id}:{row.entity_code}",
                "section": 2,
                "contract_external_id": row.external_id,
                "customer_name": row.customer_name,
                "entity_code": row.entity_code,
                "currency": row.currency,
                "opening_contract_liability": tie_outs.money(liability, row.currency),
                "revenue_recognized": tie_outs.money(recognized, row.currency),
                "revenue_from_opening": tie_outs.money(from_opening, row.currency),
            }
        )
        into = summary.setdefault(row.currency, {})
        add(into, "opening", liability)
        add(into, "revenue", recognized)
        add(into, "from_opening", from_opening)
    labels = sorted(
        {
            f"{items[0].name} to {items[-1].name}" if len(items) > 1 else items[0].name
            for items in periods.values()
            if items
        }
    )
    range_label = ", ".join(labels)
    rows: list[dict[str, Any]] = [
        {
            "row_key": f"summary:{currency}",
            "section": 1,
            "summary": SUMMARY.format(range=range_label),
            "currency": currency,
            "opening_contract_liability": tie_outs.money(values["opening"], currency),
            "revenue_recognized": tie_outs.money(values["revenue"], currency),
            "revenue_from_opening": tie_outs.money(values["from_opening"], currency),
        }
        for currency, values in sorted(summary.items())
    ]
    rows.extend(contracts)
    options = sorted(
        {
            str(
                resolve(
                    session,
                    POLICY,
                    book_code=BookCode(book_code),
                    entity_id=item.id,
                    known_at=params.known_at,
                ).value
            )
            for item in found
        }
    )
    control: dict[str, Any] = {
        "revenue_from_opening_total": tie_outs.by_currency(
            {code: values["from_opening"] for code, values in summary.items()}
        ),
        "footnote": footnote(options),
    }
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=control)
