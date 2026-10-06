"""Legacy gross and adjustment date-range journal views (BUILD_SPEC CLO-9; ENGINE_SPEC_B §14.3.4
S14-R-23; DEVIATIONS §3 PJR-2 to PJR-5, DEV-001, DEV-003; 03 REQ-JE-007 to REQ-JE-009; POLICIES
POL-006 ``LEGACY_CONTRACT_POB``; SCREENS_B RPT-13).

``legacy_view`` summarises the subledger lines (04 T-SL-04) of the named entities whose effective
date lies in the inclusive window ``[from_date, to_date]`` at the legacy summary grain (PJR-5):

- A line of a revenue role (``REVENUE``, ``PRE_STANDARD_REVENUE``) is keyed by its obligation's
  ``legacy_record_key`` (``<Contract Unique Name> <POB Unique ID> <SKU Name>``, LM-CL-70), else by
  the line's ``legacy_key``. Any other line is keyed by its ``legacy_key``, the contract's unique
  name (T-SL-04), else by the contract's external id. [J] L6-3-Q-35: the platform posts
  ``PRE_STANDARD_REVENUE`` lines with the contract name as ``legacy_key``, so the obligation's key
  comes first for both revenue roles, and pre-standard revenue nets against revenue per obligation.
- A consolidated line is (entity, key, GL account, transaction currency). ``GROSS`` sums the lines
  of ``book_code``. ``DELTA`` sums those lines plus the ``LEGACY`` book lines of the same key; the
  LEGACY book holds the reversal of what the ERP booked (S14-R-23; JET-15; D-89 L7-6-Q-8).
- A consolidated line whose net is 0 is dropped (PJR-5). Nothing else is dropped and nothing is
  rounded: the lines are posted cents (PJR-1; DEV-003), so the view balances whenever the posted
  pairs balance (DEV-001).
- ``by_account``: per account and currency, debit = Σ positive line nets, credit = Σ |negative line
  nets|, net = debit − credit. ``by_entity``: the same sums per entity with the balance flag (RPT-13
  section 2; CTL-022). ``totals``: per currency, ``lines`` (non-zero consolidated lines),
  ``total_debit``, ``total_credit`` and ``net``.

With ``known_at`` (report ``legacy_je_summary``, RPS-5) only the lines recorded at or before it are
summarised, so a rerun of a run reproduces its output.

Amounts are in the transaction currency (RPT-13 has no currency view). [J] L6-3-Q-36: the parity
views hold one currency; a window with several currencies keeps them apart in every section and
gives one ``totals`` row per currency. The read runs in the caller's tenant session, so row-level
security scopes the lines to the principal's entities. Report ``legacy_je_summary`` (RPT-13, RPS-5)
wraps this view.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.currencies import ISO_4217
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    entity_book,
    gl_account,
    legal_entity,
    obligation,
    subledger_line,
)
from erev_api.enums import BookCode, JournalRunMode
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "LegacyAccountTotal",
    "LegacyEntityTotal",
    "LegacyLineItem",
    "LegacyTotals",
    "LegacyView",
    "legacy_view",
]

# PJR-5, table 14.3.2: the roles summarised per obligation under LEGACY_CONTRACT_POB.
REVENUE_ROLES: Final = ("REVENUE", "PRE_STANDARD_REVENUE")
ZERO: Final = Decimal(0)
RULE_VIEW: Final = "RPT-13"
RULE_RANGE: Final = "REQ-RPT-012"
RULE_BOOK: Final = "E-02"
RULE_MODE: Final = "E-32"
RULE_DELTA: Final = "S14-R-23"
RULE_ENTITY_BOOK: Final = "T-REF-03"
NO_ENTITY: Final = "Choose at least one entity."
UNKNOWN_ENTITY: Final = "No entity has the code {code}."
RANGE_ORDER: Final = "Start date must be on or before end date."
UNKNOWN_BOOK: Final = "Choose the book ASC606, IFRS15 or LEGACY."
UNKNOWN_MODE: Final = "Choose the gross (GROSS) or adjustment (DELTA) journal view."
DELTA_OF_LEGACY: Final = (
    "The adjustment view compares a posting book with the LEGACY book. Choose ASC606 or IFRS15."
)
LEGACY_NOT_KEPT: Final = "Enable the Legacy book for {code} before viewing adjustment journals."


@dataclass(frozen=True, slots=True)
class LegacyLineItem:
    """One consolidated line: signed amount, debit positive (RPT-13 section "Line items")."""

    entity_code: str
    key: str
    account: str
    currency: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class LegacyAccountTotal:
    """The line nets of one account and currency (RPT-13 section "By account")."""

    account: str
    currency: str
    debit: Decimal
    credit: Decimal
    net: Decimal


@dataclass(frozen=True, slots=True)
class LegacyEntityTotal:
    """The line nets of one entity and currency (RPT-13 section "By entity")."""

    entity_code: str
    currency: str
    debit: Decimal
    credit: Decimal
    difference: Decimal

    @property
    def balanced(self) -> bool:
        return self.difference == 0


@dataclass(frozen=True, slots=True)
class LegacyTotals:
    """The control totals of one currency (RPT-13 totals row)."""

    currency: str
    lines: int
    total_debit: Decimal
    total_credit: Decimal
    net: Decimal


@dataclass(frozen=True, slots=True)
class LegacyView:
    """The legacy journal view of an effective-date window (module docstring)."""

    mode: str
    book_code: str
    entity_codes: tuple[str, ...]
    from_date: date
    to_date: date
    line_items: tuple[LegacyLineItem, ...]
    by_account: tuple[LegacyAccountTotal, ...]
    by_entity: tuple[LegacyEntityTotal, ...]
    totals: tuple[LegacyTotals, ...]

    def total(self, currency: str) -> LegacyTotals:
        """The totals row of ``currency``; zeros when the window holds no line in it."""
        for row in self.totals:
            if row.currency == currency:
                return row
        zero = _quantized(ZERO, currency)
        return LegacyTotals(currency, 0, zero, zero, zero)


def _invalid(field: str, rule_id: str, message: str) -> Problem:
    error = ProblemError(field=field, rule_id=rule_id, message=message)
    return Problem("validation-failed", "1 field needs attention.", errors=[error])


def _quantized(amount: Decimal, currency: str) -> Decimal:
    """``amount`` at the currency's minor unit, without a negative zero (DG-KRN-MONEY-06)."""
    spec = ISO_4217.get(currency)
    if spec is None:
        raise ValueError(f"{currency} is not in the currency table")
    value = amount.quantize(Decimal(1).scaleb(-spec.minor_unit), rounding=ROUND_HALF_UP)
    return abs(value) if value == 0 else value


def _account_order(code: str) -> tuple[int, int, str]:
    """Numeric account codes in numeric order (5001 before 15002), then other codes."""
    return (0, int(code), code) if code.isdigit() else (1, 0, code)


def _book(book_code: str) -> BookCode:
    try:
        return BookCode(book_code)
    except ValueError:
        raise _invalid("book", RULE_BOOK, UNKNOWN_BOOK) from None


def _mode(mode: str) -> JournalRunMode:
    try:
        return JournalRunMode(mode)
    except ValueError:
        raise _invalid("mode", RULE_MODE, UNKNOWN_MODE) from None


def _entities(session: Session, entity_codes: Sequence[str]) -> dict[UUID, str]:
    """The visible entities of ``entity_codes`` by id; 422 for an empty list or an unknown code."""
    codes = tuple(dict.fromkeys(str(code) for code in entity_codes))
    if not codes:
        raise _invalid("entity_codes", RULE_VIEW, NO_ENTITY)
    found = {
        str(row["code"]): UUID(str(row["id"]))
        for row in session.execute(
            select(legal_entity.c.id, legal_entity.c.code).where(legal_entity.c.code.in_(codes))
        ).mappings()
    }
    for code in codes:
        if code not in found:
            raise _invalid("entity_codes", RULE_VIEW, UNKNOWN_ENTITY.format(code=code))
    return {found[code]: code for code in codes}


def _require_legacy_book(session: Session, entities: dict[UUID, str]) -> None:
    """``DELTA`` needs the ``LEGACY`` book kept and enabled by every named entity (RPT-13)."""
    kept = {
        UUID(str(row["entity_id"]))
        for row in session.execute(
            select(entity_book.c.entity_id).where(
                entity_book.c.entity_id.in_(list(entities)),
                entity_book.c.book_code == BookCode.LEGACY.value,
                entity_book.c.is_enabled.is_(True),
            )
        ).mappings()
    }
    for entity_id, code in sorted(entities.items(), key=lambda item: item[1]):
        if entity_id not in kept:
            raise _invalid("mode", RULE_ENTITY_BOOK, LEGACY_NOT_KEPT.format(code=code))


def _consolidated(
    session: Session,
    *,
    entity_ids: Iterable[UUID],
    books: Sequence[str],
    from_date: date,
    to_date: date,
    known_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Σ ``amount_txn`` per (book, entity, legacy key, account, currency) over the window."""
    tenant_id = subledger_line.c.tenant_id
    revenue_key = func.coalesce(
        obligation.c.legacy_record_key, subledger_line.c.legacy_key, contract.c.external_id
    )
    balance_key = func.coalesce(subledger_line.c.legacy_key, contract.c.external_id)
    key = case(
        (subledger_line.c.account_role.in_(REVENUE_ROLES), revenue_key), else_=balance_key
    ).label("legacy_key")
    joined = (
        subledger_line.join(
            legal_entity,
            and_(
                legal_entity.c.tenant_id == tenant_id,
                legal_entity.c.id == subledger_line.c.entity_id,
            ),
        )
        .join(
            gl_account,
            and_(
                gl_account.c.tenant_id == tenant_id,
                gl_account.c.id == subledger_line.c.gl_account_id,
            ),
        )
        .join(
            contract,
            and_(contract.c.tenant_id == tenant_id, contract.c.id == subledger_line.c.contract_id),
        )
        .outerjoin(
            obligation,
            and_(
                obligation.c.tenant_id == tenant_id,
                obligation.c.id == subledger_line.c.obligation_id,
            ),
        )
    )
    statement = (
        select(
            subledger_line.c.book_code,
            legal_entity.c.code.label("entity_code"),
            key,
            gl_account.c.code.label("account"),
            subledger_line.c.txn_currency,
            func.sum(subledger_line.c.amount_txn).label("amount"),
        )
        .select_from(joined)
        .where(
            subledger_line.c.book_code.in_(list(books)),
            subledger_line.c.entity_id.in_(list(entity_ids)),
            subledger_line.c.effective_date >= from_date,
            subledger_line.c.effective_date <= to_date,
            # A line's posting period ends on or after its effective date: partition pruning.
            subledger_line.c.period_end_date >= from_date,
        )
        .group_by(
            subledger_line.c.book_code,
            legal_entity.c.code,
            key,
            gl_account.c.code,
            subledger_line.c.txn_currency,
        )
    )
    if known_at is not None:
        statement = statement.where(subledger_line.c.recorded_at <= known_at)
    return [dict(row) for row in session.execute(statement).mappings()]


def legacy_view(
    uow: UnitOfWork,
    entity_codes: Sequence[str],
    book_code: str,
    from_date: date,
    to_date: date,
    mode: str,
    *,
    known_at: datetime | None = None,
) -> LegacyView:
    """The legacy gross (``GROSS``) or adjustment (``DELTA``) journal view (module docstring).

    422 ``validation-failed``: no entity or an unknown entity code; start after end; an unknown
    book or mode; ``DELTA`` of the ``LEGACY`` book; ``DELTA`` for an entity without an enabled
    ``LEGACY`` book.
    """
    session = uow.session
    book = _book(book_code)
    view_mode = _mode(mode)
    entities = _entities(session, entity_codes)
    if from_date > to_date:
        raise _invalid("to_date", RULE_RANGE, RANGE_ORDER)
    signs = {book.value: 1}
    if view_mode is JournalRunMode.DELTA:
        if book is BookCode.LEGACY:
            raise _invalid("book", RULE_DELTA, DELTA_OF_LEGACY)
        _require_legacy_book(session, entities)
        signs[BookCode.LEGACY.value] = 1  # primary + LEGACY (S14-R-23; D-89 L7-6-Q-8)
    nets: dict[tuple[str, str, str, str], Decimal] = {}
    for row in _consolidated(
        session,
        entity_ids=entities,
        books=tuple(signs),
        from_date=from_date,
        to_date=to_date,
        known_at=known_at,
    ):
        currency = str(row["txn_currency"]).strip()
        item = (str(row["entity_code"]), str(row["legacy_key"]), str(row["account"]), currency)
        sign = signs[str(getattr(row["book_code"], "value", row["book_code"]))]
        nets[item] = nets.get(item, ZERO) + sign * Decimal(row["amount"])
    line_items = tuple(
        LegacyLineItem(
            entity_code=entity_code,
            key=legacy_key,
            account=account,
            currency=currency,
            amount=_quantized(amount, currency),
        )
        for (entity_code, legacy_key, account, currency), amount in sorted(
            nets.items(),
            key=lambda item: (item[0][1], _account_order(item[0][2]), item[0][3], item[0][0]),
        )
        if amount != 0
    )
    return LegacyView(
        mode=view_mode.value,
        book_code=book.value,
        entity_codes=tuple(sorted(entities.values())),
        from_date=from_date,
        to_date=to_date,
        line_items=line_items,
        by_account=_by_account(line_items),
        by_entity=_by_entity(line_items),
        totals=_totals(line_items),
    )


def _sides(amounts: Iterable[Decimal]) -> tuple[Decimal, Decimal]:
    """(Σ positive nets, Σ |negative nets|)."""
    debit, credit = ZERO, ZERO
    for amount in amounts:
        if amount > 0:
            debit += amount
        else:
            credit -= amount
    return debit, credit


def _by_account(items: Sequence[LegacyLineItem]) -> tuple[LegacyAccountTotal, ...]:
    grouped: dict[tuple[str, str], list[Decimal]] = {}
    for item in items:
        grouped.setdefault((item.account, item.currency), []).append(item.amount)
    rows: list[LegacyAccountTotal] = []
    for (account, currency), amounts in sorted(
        grouped.items(), key=lambda entry: (_account_order(entry[0][0]), entry[0][1])
    ):
        debit, credit = _sides(amounts)
        rows.append(
            LegacyAccountTotal(
                account=account,
                currency=currency,
                debit=_quantized(debit, currency),
                credit=_quantized(credit, currency),
                net=_quantized(debit - credit, currency),
            )
        )
    return tuple(rows)


def _by_entity(items: Sequence[LegacyLineItem]) -> tuple[LegacyEntityTotal, ...]:
    grouped: dict[tuple[str, str], list[Decimal]] = {}
    for item in items:
        grouped.setdefault((item.entity_code, item.currency), []).append(item.amount)
    rows: list[LegacyEntityTotal] = []
    for (entity_code, currency), amounts in sorted(grouped.items()):
        debit, credit = _sides(amounts)
        rows.append(
            LegacyEntityTotal(
                entity_code=entity_code,
                currency=currency,
                debit=_quantized(debit, currency),
                credit=_quantized(credit, currency),
                difference=_quantized(debit - credit, currency),
            )
        )
    return tuple(rows)


def _totals(items: Sequence[LegacyLineItem]) -> tuple[LegacyTotals, ...]:
    grouped: dict[str, list[Decimal]] = {}
    for item in items:
        grouped.setdefault(item.currency, []).append(item.amount)
    rows: list[LegacyTotals] = []
    for currency, amounts in sorted(grouped.items()):
        debit, credit = _sides(amounts)
        rows.append(
            LegacyTotals(
                currency=currency,
                lines=len(amounts),
                total_debit=_quantized(debit, currency),
                total_credit=_quantized(credit, currency),
                net=_quantized(debit - credit, currency),
            )
        )
    return tuple(rows)
