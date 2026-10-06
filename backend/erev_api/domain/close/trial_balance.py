"""Subledger-to-GL comparison, without a database (03 REQ-CLS-016, REQ-INT-009; 04 T-CLS-06
``totals``, T-CLS-07; research 07 RC-02; SCREENS_B §2.2; BUILD_SPEC CLO-17; control CTL-025;
supervisor rulings R-54 (e), R-69 and R-74).

``compare`` takes, for one entity, book and period, the subledger's balance of every
subledger-controlled account, what each journal batch carries on those accounts, and a trial
balance — the closing balances of ``domain.journals.ports.TrialBalance`` with the GL documents of
the period when an adapter supplies them — and answers the totals by account and the itemised
differences. ``lines_of_sheet`` reads an uploaded trial balance (the columns ``account``,
``currency``, ``amount``).

One measure on both sides: the closing balance at the period end in the entity's functional
currency, debit positive and credit negative (the sign of T-SL-04). A balance sheet account is
cumulative; an income statement account (E-52 ``REVENUE``, ``EXPENSE``) is stated for the fiscal
year to date, as a trial balance states it. ``difference`` = GL − subledger.

Differences of one account are itemised (REQ-CLS-016):

- ``UNPOSTED_BATCH``: a batch the subledger balance holds that the GL has not acknowledged — one
  item per batch and account, the batch's amount on the account as ``subledger_amount``. A batch
  the pulled documents already show is in the GL and is not itemised.
- ``TIMING``: an acknowledged batch that the two sides hold in different windows — the GL posted
  it after the period end, or posted into the period a batch of another period.
- ``DIRECT_GL_ENTRY``: a GL document of the period on a subledger-controlled account that carries
  no external id of this subledger; high risk.
- ``OTHER``: what no batch, posting date or document explains — the account's difference less its
  other items. A trial balance without documents (an upload) can name nothing else.

The role basis (supervisor rulings R-69 (a), R-74). The three contract balance roles —
``CONTRACT_LIABILITY``, ``CONTRACT_ASSET``, ``UNBILLED_RECEIVABLE`` — are compared per ROLE, not
per account: the subledger side of a role row (``RoleBalance``) is the stored closing contract
balances of the entity's contracts, which carry what a ledger kept by the ERP holds on those
accounts and the subledger never posts (the invoices of ``billing.posting = ERP``, a migrated
opening balance); the ledger side is the sum of the role's accounts. A role whose balance the
subledger cannot state in the functional currency is ``NOT_STATED``: its row carries no
subledger amount and no difference, and one item of that kind carries the ledger's balance — a
variance the preparer explains. The batch and document items of a role row name their account
and the role; the residual of a role with several accounts names the role alone. A role neither
side holds anything for has no row.

A GL document made in the ERP whose number is an invoice or credit memo number of the entity
(``billing_references``) is ERP billing, which the stored balances already hold: it raises no
item (R-74 (d)). Every other document without an external id of this subledger stays a
``DIRECT_GL_ENTRY``.

Tolerance is zero (RC-02): every item counts as a variance.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from erev_engine.currencies import ISO_4217

from erev_api.domain.imports.parse import SheetRows, cell_text
from erev_api.domain.journals.ports import TrialBalanceDetail, TrialBalanceLine

__all__ = [
    "DIRECT_GL_ENTRY",
    "HEADERS",
    "NOT_STATED",
    "OTHER",
    "TIMING",
    "UNPOSTED_BATCH",
    "AccountBalance",
    "AccountTotal",
    "BatchPortion",
    "Comparison",
    "Item",
    "NotStated",
    "RoleBalance",
    "SheetError",
    "compare",
    "lines_of_sheet",
]

# 04 T-CLS-07 ``item_kind`` literals of a subledger-to-GL reconciliation.
UNPOSTED_BATCH: Final = "UNPOSTED_BATCH"
TIMING: Final = "TIMING"
DIRECT_GL_ENTRY: Final = "DIRECT_GL_ENTRY"
OTHER: Final = "OTHER"
NOT_STATED: Final = "NOT_STATED"  # rev 1.253 (supervisor ruling R-74 (a))
_KIND_ORDER: Final = {NOT_STATED: 0, UNPOSTED_BATCH: 1, TIMING: 2, DIRECT_GL_ENTRY: 3, OTHER: 4}
ZERO: Final = Decimal(0)

# BUILD_SPEC CLO-17: "an uploaded CSV of account, currency and amount".
HEADERS: Final = ("account", "currency", "amount")
_AMOUNT: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")  # ASCII digits only (D-78)
HEADER_EXPECTED: Final = "Give exactly the columns account, currency and amount."
NO_ROWS: Final = "The file has no account rows."
ACCOUNT_REQUIRED: Final = "Enter the GL account code."
ACCOUNT_REPEATED: Final = "Account {account} appears more than once; give one row per account."
CURRENCY_REQUIRED: Final = "Enter the currency of the balance, {functional}."
CURRENCY_FUNCTIONAL: Final = (
    "A trial balance is stated in the entity's functional currency, {functional}; this row is in "
    "{currency}."
)
AMOUNT_INVALID: Final = (
    "Enter the closing balance as a decimal number, debits positive and credits negative, for "
    "example -1250.00."
)
AMOUNT_PLACES: Final = "Enter {currency} amounts with at most {places} decimal places."
FORMULA_CELL: Final = "The cell holds a formula without a stored value; enter the value."


@dataclass(frozen=True, slots=True)
class AccountBalance:
    """The subledger's balance of one GL account in the entity's functional currency (module
    docstring: cumulative, or fiscal year to date for an income statement account)."""

    account_code: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class BatchPortion:
    """What one journal batch carries on one account (functional currency, debit positive) and
    where it stands: ``in_subledger`` — its period lies in the window the account's subledger
    balance covers; ``posted`` — the GL acknowledged it; ``in_ledger`` — the GL holds it inside
    that window (its GL posting date; the batch's own period when the acknowledgement states no
    date). ``reference`` is the batch's ADP-10 external id; ``gl_document_reference`` the GL
    document of its acknowledgement."""

    reference: str
    account_code: str
    amount: Decimal
    in_subledger: bool
    posted: bool
    in_ledger: bool
    gl_document_reference: str | None = None


@dataclass(frozen=True, slots=True)
class NotStated:
    """Why the subledger states no amount for a contract balance role (supervisor ruling R-74
    (a)), and the contracts concerned as (contract id, external id), in external id order."""

    reason: str
    contracts: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RoleBalance:
    """The subledger side of one contract balance role (module docstring): ``amount`` is the
    closing balance in the functional currency, debit positive — the stored balances of the
    entity's contracts, with what other roles posted on the role's accounts — or None, with
    ``not_stated`` saying why. ``account_codes`` are the role's accounts in code order; an
    account belongs to one role row."""

    account_role: str
    account_codes: tuple[str, ...]
    amount: Decimal | None
    not_stated: NotStated | None = None

    def __post_init__(self) -> None:
        if (self.amount is None) != (self.not_stated is not None):
            raise ValueError("a role balance states an amount or why it states none")


@dataclass(frozen=True, slots=True)
class AccountTotal:
    """One T-CLS-06 ``totals`` row: an account — or a contract balance role with its accounts —
    with the amount of each side; None where a side holds nothing. A role row carries
    ``account_role`` and ``account_codes`` (``account_code`` when the role has exactly one
    account); a row marked ``not_stated`` has no subledger amount and no difference."""

    account_code: str | None
    currency: str
    subledger_amount: Decimal | None
    source_amount: Decimal | None
    account_role: str | None = None
    account_codes: tuple[str, ...] = ()
    not_stated: NotStated | None = None

    @property
    def difference(self) -> Decimal | None:
        if self.not_stated is not None:
            return None
        return (self.source_amount or ZERO) - (self.subledger_amount or ZERO)


@dataclass(frozen=True, slots=True)
class Item:
    """One T-CLS-07 row of a subledger-to-GL reconciliation. A batch or document item carries
    0.00 on the side that holds nothing (SCREENS_B §2.2); ``OTHER`` carries neither amount;
    ``NOT_STATED`` carries the ledger's balance as its source amount and its difference.
    ``account_role`` names the role row the item belongs to."""

    item_kind: str
    account_code: str | None
    currency: str
    difference: Decimal
    subledger_amount: Decimal | None = None
    source_amount: Decimal | None = None
    is_high_risk: bool = False
    gl_document_reference: str | None = None
    account_role: str | None = None


@dataclass(frozen=True, slots=True)
class Comparison:
    """What ``compare`` established: the totals, the items, the trial balance rows of accounts
    the subledger does not control, which are not compared, and the ERP billing documents on
    controlled accounts, which raise no item."""

    totals: tuple[AccountTotal, ...]
    items: tuple[Item, ...]
    ignored_lines: int
    erp_billing_documents: int = 0

    @property
    def direct_entries(self) -> int:
        return sum(1 for item in self.items if item.item_kind == DIRECT_GL_ENTRY)

    @property
    def not_stated(self) -> int:
        return sum(1 for total in self.totals if total.not_stated is not None)


def compare(
    *,
    currency: str,
    accounts: Iterable[str],
    subledger: Sequence[AccountBalance],
    portions: Sequence[BatchPortion],
    lines: Sequence[TrialBalanceLine],
    details: Sequence[TrialBalanceDetail] = (),
    own_references: Iterable[str] = (),
    roles: Sequence[RoleBalance] = (),
    billing_references: Iterable[str] = (),
) -> Comparison:
    """Compare the subledger with a trial balance (module docstring). ``accounts`` are the
    subledger-controlled account codes; ``own_references`` the ADP-10 external ids among
    ``details`` that name a batch of this subledger; ``roles`` the contract balance roles
    compared on the role basis, whose accounts are controlled and whose posted balances in
    ``subledger`` are not read; ``billing_references`` the invoice and credit memo numbers of the
    entity among the documents made in the ERP."""
    own = frozenset(own_references)
    billing = frozenset(billing_references)
    role_of: dict[str, RoleBalance] = {}
    for role in roles:
        for code in role.account_codes:
            if code in role_of:
                raise ValueError(f"account {code} belongs to two role rows")
            role_of[code] = role
    scope = frozenset(accounts) | frozenset(role_of)
    held = {
        item.account_code: item.amount for item in subledger if item.account_code not in role_of
    }
    stated = {line.account_code: line.amount for line in lines if line.account_code in scope}
    ignored = sum(1 for line in lines if line.account_code not in scope)
    rows = [
        AccountTotal(
            account_code=code,
            currency=currency,
            subledger_amount=held.get(code),
            source_amount=stated.get(code),
        )
        for code in set(held) | {code for code in stated if code not in role_of}
    ]
    for role in roles:
        listed = [stated[code] for code in role.account_codes if code in stated]
        rows.append(
            AccountTotal(
                account_code=role.account_codes[0] if len(role.account_codes) == 1 else None,
                currency=currency,
                subledger_amount=role.amount,
                source_amount=sum(listed, ZERO) if listed else None,
                account_role=role.account_role,
                account_codes=role.account_codes,
                not_stated=role.not_stated,
            )
        )
    # A row is placed by its first account; a role without an account follows, by role.
    place = {
        _row_key(row.account_role, row.account_code): (0, row.account_codes[0])
        if row.account_codes
        else (0, row.account_code)
        if row.account_code is not None
        else (1, str(row.account_role))
        for row in rows
    }
    rows.sort(key=lambda row: place[_row_key(row.account_role, row.account_code)])
    totals = tuple(rows)
    unstated = {role.account_role for role in roles if role.not_stated is not None}

    def named(code: str) -> str | None:
        """The role of the row ``code`` belongs to; None for an account row."""
        found = role_of.get(code)
        return None if found is None else found.account_role

    # A batch whose document the GL already shows is posted there, whatever its state here.
    seen_in_ledger = {
        (item.external_id, item.account_code) for item in details if item.external_id in own
    }
    items: list[Item] = []
    for portion in portions:
        code = portion.account_code
        # A role the subledger does not state has no difference for a batch to explain.
        if code not in scope or portion.amount == ZERO or named(code) in unstated:
            continue
        if not portion.posted:
            if portion.in_subledger and (portion.reference, code) not in seen_in_ledger:
                items.append(
                    _subledger_only(
                        UNPOSTED_BATCH, currency, portion, portion.reference, named(code)
                    )
                )
            continue
        reference = portion.gl_document_reference or portion.reference
        if portion.in_subledger and not portion.in_ledger:
            items.append(_subledger_only(TIMING, currency, portion, reference, named(code)))
        elif portion.in_ledger and not portion.in_subledger:
            items.append(
                Item(
                    item_kind=TIMING,
                    account_code=code,
                    currency=currency,
                    difference=portion.amount,
                    subledger_amount=ZERO,
                    source_amount=portion.amount,
                    gl_document_reference=reference,
                    account_role=named(code),
                )
            )
    erp_billing = 0
    for document in details:
        if document.account_code not in scope or document.external_id in own:
            continue
        if document.external_id is None and document.document_reference in billing:
            erp_billing += 1  # R-74 (d): the ERP's own invoice or credit memo
            continue
        items.append(
            Item(
                item_kind=DIRECT_GL_ENTRY,
                account_code=document.account_code,
                currency=currency,
                difference=document.amount,
                subledger_amount=ZERO,
                source_amount=document.amount,
                is_high_risk=True,
                gl_document_reference=document.document_reference,
                account_role=named(document.account_code),
            )
        )
    explained: dict[str, Decimal] = {}
    for item in items:
        key = _row_key(item.account_role, item.account_code)
        explained[key] = explained.get(key, ZERO) + item.difference
    for total in totals:
        key = _row_key(total.account_role, total.account_code)
        if total.not_stated is not None:
            ledger = total.source_amount or ZERO
            items.append(
                Item(
                    item_kind=NOT_STATED,
                    account_code=total.account_code,
                    currency=currency,
                    difference=ledger,
                    source_amount=ledger,
                    account_role=total.account_role,
                )
            )
            continue
        difference = total.difference
        assert difference is not None
        residual = difference - explained.get(key, ZERO)
        if residual != ZERO:
            items.append(
                Item(
                    item_kind=OTHER,
                    account_code=total.account_code,
                    currency=currency,
                    difference=residual,
                    account_role=total.account_role,
                )
            )
    items.sort(
        key=lambda item: (
            # an item of an account without a row (a document on an account neither side states)
            place.get(_row_key(item.account_role, item.account_code), (0, item.account_code or "")),
            _KIND_ORDER[item.item_kind],
            item.account_code or "",
            item.gl_document_reference or "",
        )
    )
    # A role neither side holds anything for — a stated balance of zero, no ledger line and no
    # item — has no row, as an account neither side states has none.
    itemised = {_row_key(item.account_role, item.account_code) for item in items}
    shown = tuple(
        total
        for total in totals
        if total.account_role is None
        or total.not_stated is not None
        or total.subledger_amount != ZERO
        or total.source_amount is not None
        or _row_key(total.account_role, total.account_code) in itemised
    )
    return Comparison(
        totals=shown,
        items=tuple(items),
        ignored_lines=ignored,
        erp_billing_documents=erp_billing,
    )


def _row_key(account_role: str | None, account_code: str | None) -> str:
    """The ``totals`` row an amount belongs to: its role, or its account."""
    return f"role:{account_role}" if account_role is not None else f"account:{account_code}"


def _subledger_only(
    item_kind: str, currency: str, portion: BatchPortion, reference: str, account_role: str | None
) -> Item:
    return Item(
        item_kind=item_kind,
        account_code=portion.account_code,
        currency=currency,
        difference=-portion.amount,
        subledger_amount=portion.amount,
        source_amount=ZERO,
        gl_document_reference=reference,
        account_role=account_role,
    )


# --- an uploaded trial balance --------------------------------------------------------------------


class SheetError(Exception):
    """An uploaded trial balance that cannot be compared: (row number or None, field, message) of
    every finding, in file order."""

    def __init__(self, findings: Sequence[tuple[int | None, str, str]]) -> None:
        super().__init__(f"{len(findings)} trial balance finding(s)")
        self.findings: tuple[tuple[int | None, str, str], ...] = tuple(findings)


def _header(value: Any) -> str:
    text = cell_text(value)
    return "" if text is None else text.strip().lower()


def _account_problem(account: str, seen: set[str]) -> str | None:
    if not account:
        return ACCOUNT_REQUIRED
    return ACCOUNT_REPEATED.format(account=account) if account in seen else None


def _currency_problem(currency: str, functional: str) -> str | None:
    if not currency:
        return CURRENCY_REQUIRED.format(functional=functional)
    if currency.upper() != functional:
        return CURRENCY_FUNCTIONAL.format(functional=functional, currency=currency)
    return None


def _amount_problem(amount: str, functional: str, places: int) -> str | None:
    if not _AMOUNT.fullmatch(amount):
        return AMOUNT_INVALID
    if len(amount.partition(".")[2].rstrip("0")) > places:
        return AMOUNT_PLACES.format(currency=functional, places=places)
    return None


def lines_of_sheet(sheet: SheetRows, *, functional_currency: str) -> tuple[TrialBalanceLine, ...]:
    """The closing balances an uploaded file states, one per account, in file order. ``SheetError``
    names every finding: a header other than ``account``, ``currency``, ``amount`` (any order, any
    case), no account row, a row without an account, an account given twice, a currency other
    than the entity's functional currency, an amount that is no decimal number or carries more
    decimal places than the currency has, and a formula without a stored value."""
    functional = functional_currency.strip()
    headers = tuple(_header(value) for value in sheet.headers)
    while headers and headers[-1] == "":
        headers = headers[:-1]
    if sorted(headers) != sorted(HEADERS):
        raise SheetError([(1, "file_id", HEADER_EXPECTED)])
    column = {name: headers.index(name) for name in HEADERS}
    spec = ISO_4217.get(functional)
    places = 2 if spec is None else int(spec.minor_unit)
    findings: list[tuple[int | None, str, str]] = []
    lines: list[TrialBalanceLine] = []
    seen: set[str] = set()
    for number, cells in sheet.rows:
        values = {
            name: (cell_text(cells[column[name]]) or "").strip()
            if column[name] < len(cells)
            else ""
            for name in HEADERS
        }
        formulas = {name for name in HEADERS if (number, column[name]) in sheet.formula_cells}
        if not (any(values.values()) or formulas):
            continue  # an empty row
        account, currency, amount = values["account"], values["currency"], values["amount"]
        problems = {
            "account": _account_problem(account, seen),
            "currency": _currency_problem(currency, functional),
            "amount": _amount_problem(amount, functional, places),
        }
        seen.add(account)
        found = [
            (number, name, FORMULA_CELL if name in formulas else problems[name])
            for name in HEADERS
            if name in formulas or problems[name] is not None
        ]
        findings.extend((row, name, str(message)) for row, name, message in found)
        if not found:
            lines.append(
                TrialBalanceLine(account_code=account, currency=functional, amount=Decimal(amount))
            )
    if not findings and not lines:
        findings.append((None, "file_id", NO_ROWS))
    if findings:
        raise SheetError(findings)
    return tuple(lines)
