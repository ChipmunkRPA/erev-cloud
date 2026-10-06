"""RPT-35 ``intercompany_pairs`` Intercompany pairs (SCREENS_B §5.6.6 RPT-35; ENGINE_SPEC_B §12
S12-R-15, S12-R-16, S12-INV-07, Table 14-A JET-13; POLICIES POL-170, POL-171, ALG-07; 04 T-SL-04,
table 10-T; PRD J-13-AC-7, WLD-X-14; 03 REQ-ENT-003, REQ-ENT-005; BUILD_SPEC RPS-12).

An obligation performed by an entity other than the contracting entity posts a pair (JET-13): the
contracting entity relieves its contract liability against ``INTERCOMPANY_DUE_TO`` and the
performing entity books ``INTERCOMPANY_DUE_FROM`` against revenue, each line naming the other
entity as its counterparty, in the transaction currency (POL-171). The report reads those T-SL-04
lines of the run's book for the run's entities, each over its own period range, as of the run's
``known_at``.

- Section 1 "Pairs by entity": one row per (due-from entity, due-to entity, currency), ``row_key``
  ``pair:<due from entity>:<due to entity>:<currency>``. ``due_from_amount`` is debit less credit
  of the ``INTERCOMPANY_DUE_FROM`` lines the due-from entity carries against the due-to entity,
  ``due_to_amount`` credit less debit of the ``INTERCOMPANY_DUE_TO`` lines the due-to entity
  carries against the due-from entity, ``unmatched_amount`` their difference. A side whose entity
  is outside the run is not read: its cell and the unmatched cell are empty, never 0.00.
- Section 2 "By contract": one row per contract, obligation and period, ``row_key``
  ``contract:<external id>:<obligation key>:<period key>``. ``pair_amount`` is the contracting
  entity's relief (POL-171), and the performing entity's amount when the contracting entity is
  outside the run; ``unmatched_amount`` as in section 1. Two entities on different calendars list
  each side under its own period.

Tie-out ``TO_IC_UNMATCHED_ZERO`` (S12-R-16, S12-INV-07): every pair whose two entities are in the
run has an unmatched amount of 0; ``NOT_APPLICABLE`` without such a pair. Control totals: the pair
counts and ``due_from_total``, ``due_to_total`` and ``unmatched_total`` per currency.
``currency_view`` ``transaction`` (the default) is always served; another view only when every
line's currency is the functional currency of the entity that carries it, else refused by name.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, legal_entity, obligation, period, subledger_line
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import ranges
from erev_api.domain.reports.builders.out_of_period_register import refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, PeriodRef
from erev_api.uow import UnitOfWork

CODE: Final = "intercompany_pairs"
TO_IC_UNMATCHED_ZERO: Final = tie_outs.TO_IC_UNMATCHED_ZERO
DEFAULT_CURRENCY_VIEW: Final = "transaction"  # SCREENS_B RPT-35 "default `transaction`"
DUE_FROM: Final = "INTERCOMPANY_DUE_FROM"  # the performing entity's role (JET-13)
DUE_TO: Final = "INTERCOMPANY_DUE_TO"  # the contracting entity's role (JET-13)
ROLES: Final = (DUE_FROM, DUE_TO)
PAIR_PREFIX: Final = "pair:"
CONTRACT_PREFIX: Final = "contract:"
FUNCTIONAL_ONLY: Final = (
    "The functional and reporting views show pairs whose currency is the functional currency of "
    "both entities; choose the transaction view."
)
COLUMNS: Final = (
    Column("section", "Section", "integer"),
    Column("due_from_entity_code", "Due from entity", "code"),
    Column("due_to_entity_code", "Due to entity", "code"),
    Column("currency", "Currency", "code"),
    Column("due_from_amount", "Due from", "money"),
    Column("due_to_amount", "Due to", "money"),
    Column("unmatched_amount", "Unmatched", "money"),
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("contracting_entity_code", "Contracting entity", "code"),
    Column("performing_entity_code", "Performing entity", "code"),
    Column("period_key", "Period", "code"),
    Column("pair_amount", "Pair amount", "money"),
)


@dataclass(frozen=True, slots=True)
class Line:
    """One intercompany T-SL-04 line of a run entity — the input of ``dataset_rows``."""

    entity_code: str  # the entity that carries the line
    counterparty_code: str
    account_role: str  # DUE_FROM | DUE_TO
    currency: str
    amount: Decimal  # signed as posted: debit positive
    functional_currency: str  # of the carrying entity
    contract_external_id: str
    obligation_key: str | None
    period_key: str


@dataclass(slots=True)
class _Sides:
    """The two sides of one pair (or of one contract, obligation and period of a pair); a side
    stays None until a line of it is read."""

    due_from: Decimal | None = None
    due_to: Decimal | None = None

    def add(self, line: Line) -> None:
        if line.account_role == DUE_FROM:
            self.due_from = (self.due_from or ZERO) + line.amount
        else:
            self.due_to = (self.due_to or ZERO) - line.amount


def pair_of(line: Line) -> tuple[str, str, str]:
    """(due-from entity, due-to entity, currency) of a line: the carrying entity is the due-from
    entity of an ``INTERCOMPANY_DUE_FROM`` line and the due-to entity of an
    ``INTERCOMPANY_DUE_TO`` line. Pure."""
    if line.account_role == DUE_FROM:
        return line.entity_code, line.counterparty_code, line.currency
    return line.counterparty_code, line.entity_code, line.currency


def check_view(view: str, lines: Iterable[Line]) -> None:
    """``transaction`` always; another view only when every line is in the functional currency of
    the entity that carries it, else refused by name."""
    if view != DEFAULT_CURRENCY_VIEW and any(
        line.currency != line.functional_currency for line in lines
    ):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


def _amounts(
    sides: _Sides, pair: tuple[str, str, str], run_entities: Collection[str]
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """(due from, due to, unmatched) of one pair: a side whose entity is in the run is 0.00
    without lines; a side outside the run is unknown, and so is the unmatched amount."""
    due_from_entity, due_to_entity, _ = pair
    due_from = (sides.due_from or ZERO) if due_from_entity in run_entities else None
    due_to = (sides.due_to or ZERO) if due_to_entity in run_entities else None
    unmatched = None if due_from is None or due_to is None else due_from - due_to
    return due_from, due_to, unmatched


def _money(amount: Decimal | None, currency: str) -> dict[str, str] | None:
    return None if amount is None else tie_outs.money(amount, currency)


def dataset_rows(
    lines: Iterable[Line], *, run_entities: Collection[str]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """(rows of sections 1 and 2, control totals, the ``TO_IC_UNMATCHED_ZERO`` result).
    ``run_entities`` are the entity codes of the run: only their lines are in ``lines``. Pure."""
    pairs: dict[tuple[str, str, str], _Sides] = {}
    details: dict[tuple[str, str, str, tuple[str, str, str]], _Sides] = {}
    for line in lines:
        pair = pair_of(line)
        pairs.setdefault(pair, _Sides()).add(line)
        key = (line.contract_external_id, line.obligation_key or "", line.period_key, pair)
        details.setdefault(key, _Sides()).add(line)
    rows: list[dict[str, Any]] = []
    due_from_total: dict[str, Decimal] = {}
    due_to_total: dict[str, Decimal] = {}
    matched_from: dict[str, Decimal] = {}
    matched_to: dict[str, Decimal] = {}
    complete = broken = 0
    for pair in sorted(pairs):
        due_from_entity, due_to_entity, currency = pair
        due_from, due_to, unmatched = _amounts(pairs[pair], pair, run_entities)
        if due_from is not None:
            tie_outs.add(due_from_total, currency, due_from)
        if due_to is not None:
            tie_outs.add(due_to_total, currency, due_to)
        if due_from is not None and due_to is not None and unmatched is not None:
            complete += 1
            broken += tie_outs.quantized(unmatched, currency) != 0
            tie_outs.add(matched_from, currency, due_from)
            tie_outs.add(matched_to, currency, due_to)
        rows.append(
            {
                "row_key": f"{PAIR_PREFIX}{due_from_entity}:{due_to_entity}:{currency}",
                "section": 1,
                "due_from_entity_code": due_from_entity,
                "due_to_entity_code": due_to_entity,
                "currency": currency,
                "due_from_amount": _money(due_from, currency),
                "due_to_amount": _money(due_to, currency),
                "unmatched_amount": _money(unmatched, currency),
            }
        )
    for key in sorted(details):
        external_id, obligation_key, period_key, pair = key
        due_from_entity, due_to_entity, currency = pair
        due_from, due_to, unmatched = _amounts(details[key], pair, run_entities)
        rows.append(
            {
                "row_key": f"{CONTRACT_PREFIX}{external_id}:{obligation_key}:{period_key}",
                "section": 2,
                "contract_external_id": external_id,
                "obligation_key": obligation_key or None,
                "contracting_entity_code": due_to_entity,
                "performing_entity_code": due_from_entity,
                "period_key": period_key,
                "currency": currency,
                # POL-171: the pair carries the contracting entity's relief
                "pair_amount": _money(due_from if due_to is None else due_to, currency),
                "unmatched_amount": _money(unmatched, currency),
            }
        )
    if complete:
        tie = tie_outs.compared(TO_IC_UNMATCHED_ZERO, matched_to, matched_from)
        if broken:  # two pairs that offset each other are two breaks, not a tie
            tie["result"] = tie_outs.FAIL
    else:
        tie = tie_outs.not_applicable(TO_IC_UNMATCHED_ZERO)
    totals = {
        "pair_count": len(pairs),
        "incomplete_pair_count": len(pairs) - complete,
        "due_from_total": tie_outs.by_currency(due_from_total),
        "due_to_total": tie_outs.by_currency(due_to_total),
        "unmatched_total": tie_outs.by_currency(
            {
                code: matched_from.get(code, ZERO) - matched_to.get(code, ZERO)
                for code in set(matched_from) | set(matched_to)
            }
        ),
    }
    return rows, totals, tie


def sources(
    session: Session,
    params: ReportParams,
    *,
    book_code: str,
    periods: Mapping[UUID, Sequence[PeriodRef]],
) -> list[Line]:
    """The intercompany lines of the run's entities, each over its own period range, recorded by
    the run's ``known_at``."""
    scopes = [
        and_(
            subledger_line.c.entity_id == entity_id,
            subledger_line.c.period_id.in_([item.id for item in items]),
        )
        for entity_id, items in sorted(periods.items(), key=lambda pair: str(pair[0]))
        if items
    ]
    carrier = legal_entity.alias("carrier")
    counter = legal_entity.alias("counterparty")
    statement = (
        select(
            carrier.c.code.label("entity_code"),
            carrier.c.functional_currency,
            counter.c.code.label("counterparty_code"),
            subledger_line.c.account_role,
            subledger_line.c.txn_currency,
            subledger_line.c.amount_txn,
            contract.c.external_id,
            obligation.c.obligation_key,
            period.c.period_key,
        )
        .select_from(
            subledger_line.join(
                carrier,
                and_(
                    carrier.c.tenant_id == subledger_line.c.tenant_id,
                    carrier.c.id == subledger_line.c.entity_id,
                ),
            )
            .join(
                counter,
                and_(
                    counter.c.tenant_id == subledger_line.c.tenant_id,
                    counter.c.id == subledger_line.c.counterparty_entity_id,
                ),
            )
            .join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            )
            .join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
            .outerjoin(
                obligation,
                and_(
                    obligation.c.tenant_id == subledger_line.c.tenant_id,
                    obligation.c.id == subledger_line.c.obligation_id,
                ),
            )
        )
        .where(
            subledger_line.c.book_code == book_code,
            subledger_line.c.account_role.in_(list(ROLES)),
            subledger_line.c.recorded_at <= params.known_at,
            or_(*scopes) if scopes else false(),
        )
        .order_by(subledger_line.c.period_end_date, subledger_line.c.entry_no, subledger_line.c.id)
    )
    return [
        Line(
            entity_code=str(row["entity_code"]),
            counterparty_code=str(row["counterparty_code"]),
            account_role=str(row["account_role"]),
            currency=str(row["txn_currency"]).strip(),
            amount=Decimal(row["amount_txn"]),
            functional_currency=str(row["functional_currency"]).strip(),
            contract_external_id=str(row["external_id"]),
            obligation_key=None if row["obligation_key"] is None else str(row["obligation_key"]),
            period_key=str(row["period_key"]),
        )
        for row in session.execute(statement).mappings()
    ]


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, _ = ranges(session, params)
    lines = sources(session, params, book_code=book_code, periods=periods)
    check_view(str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW), lines)
    rows, totals, tie = dataset_rows(lines, run_entities={entity.code for entity in found})
    return ReportData(
        columns=COLUMNS, rows=tuple(rows), control_totals=totals, tie_out_results=(tie,)
    )


__all__ = [
    "CODE",
    "COLUMNS",
    "DEFAULT_CURRENCY_VIEW",
    "DUE_FROM",
    "DUE_TO",
    "TO_IC_UNMATCHED_ZERO",
    "Line",
    "build",
    "check_view",
    "dataset_rows",
    "pair_of",
    "sources",
]
