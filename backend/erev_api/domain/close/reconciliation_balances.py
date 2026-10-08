"""Shared readers for the subledger side of a GL reconciliation.

Attachment and freshness checks must use the same role/account/balance basis. This
module performs reads only; it has no dependency on reconciliation commands or gates
at runtime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    contract,
    contract_version_balance,
    gl_account,
    ledger_chain_head,
    period,
    subledger_line,
    subledger_posting_seal,
)
from erev_api.domain.close import trial_balance
from erev_api.domain.reports import tie_outs
from erev_api.enums import AccountRole, AccountType, ConfigStatus
from erev_api.explain import store as trace_store

if TYPE_CHECKING:
    from erev_api.domain.close import gates


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


# E-52: the account types whose balance is cumulative; the others are fiscal year to date.
BALANCE_SHEET_TYPES: Final = frozenset(
    {AccountType.ASSET.value, AccountType.LIABILITY.value, AccountType.EQUITY.value}
)
# E-01: the contract balance roles compared on the role basis (supervisor rulings R-69 (a), R-74
# (b)), in row order, each with the T-CON-09 balance it reads and that balance's sign in a trial
# balance (debit positive: a liability is a credit). Their accounts are controlled before their
# first line (R-69 (c)).
POSITION_ROLES: Final[Mapping[str, tuple[str, int]]] = {
    AccountRole.CONTRACT_LIABILITY.value: ("contract_liability", -1),
    AccountRole.CONTRACT_ASSET.value: ("contract_asset", 1),
    AccountRole.UNBILLED_RECEIVABLE.value: ("unbilled_receivable", 1),
}
CONTROL_ROLES: Final = tuple(POSITION_ROLES)
# SCREENS_B §2.2 "Not stated by the subledger": the reasons of a role row without an amount.
NOT_STATED_FOREIGN: Final = (
    "{count} contract(s) in another currency than {functional} hold no {functional} balance at "
    "{period_key}: the functional balance is stored for a contract version's latest period only."
)
NOT_STATED_UNREADABLE: Final = (
    "The balances of {count} contract(s) at {period_key} cannot be read from their calculation "
    "traces."
)
NOT_STATED_SHARED: Final = (
    "Account(s) {accounts} carry {role} and {others}; the ledger does not tell them apart. Map "
    "each contract balance role to accounts of its own."
)


@dataclass(frozen=True, slots=True)
class _Windows:
    """What an account's closing balance covers at the period end (``trial_balance``): every
    period through the end for a balance sheet account, the periods of the period's fiscal year
    through the end for an income statement account."""

    fiscal_year: int
    year_start: date
    period_end: date

    def holds_period(self, account_type: str, fiscal_year: int, end_date: date) -> bool:
        if end_date > self.period_end:
            return False
        return account_type in BALANCE_SHEET_TYPES or fiscal_year == self.fiscal_year

    def holds_date(self, account_type: str, day: date) -> bool:
        if day > self.period_end:
            return False
        return account_type in BALANCE_SHEET_TYPES or day >= self.year_start


def _windows(session: Session, scope: gates.PeriodScope) -> _Windows:
    calendar_id, fiscal_year = session.execute(
        select(period.c.calendar_id, period.c.fiscal_year).where(period.c.id == scope.period_id)
    ).one()
    year_start = session.execute(
        select(func.min(period.c.start_date)).where(
            period.c.calendar_id == calendar_id, period.c.fiscal_year == fiscal_year
        )
    ).scalar_one()
    return _Windows(fiscal_year=int(fiscal_year), year_start=year_start, period_end=scope.end_date)


@dataclass(frozen=True, slots=True)
class _Subledger:
    """The subledger side at a knowledge cutoff: the balance of every account inside its window,
    the accounts that carry a line through the period end, the same two by the account role the
    lines were posted with (T-SL-04 ``account_role``), and the lines recorded after the cutoff,
    which the reconciliation does not hold."""

    balances: tuple[trial_balance.AccountBalance, ...]
    accounts: frozenset[str]
    later_lines: int
    by_role: Mapping[tuple[str, str], Decimal]  # (account code, account role) → balance
    role_accounts: Mapping[str, frozenset[str]]  # account role → the accounts its lines reached


def _subledger_side(
    session: Session,
    scope: gates.PeriodScope,
    windows: _Windows,
    as_of: datetime,
    chain_seq: int | None = None,
) -> _Subledger:
    """The subledger side of the entity and book through the period end. With ``chain_seq`` —
    the reconciliation's chain position (T-CLS-06 ``ledger_chain_seq``) — the reconciliation
    holds the lines of the postings sealed up to it, and a line of a later seal is one it does
    not hold: the chain sequence is the commit order of the book's postings, so "later" is
    "committed later" whenever the posting's unit of work began. Without one (a row generated
    before revision 0121) it holds the lines recorded at or before ``as_of``."""
    posting_period = period.alias("posting_period")
    lines = subledger_line.join(
        gl_account,
        and_(
            gl_account.c.tenant_id == subledger_line.c.tenant_id,
            gl_account.c.id == subledger_line.c.gl_account_id,
        ),
    ).join(
        posting_period,
        and_(
            posting_period.c.tenant_id == subledger_line.c.tenant_id,
            posting_period.c.id == subledger_line.c.period_id,
        ),
    )
    if chain_seq is None:
        within = subledger_line.c.recorded_at <= as_of
    else:
        sealed = subledger_posting_seal
        lines = lines.join(
            sealed,
            and_(
                sealed.c.tenant_id == subledger_line.c.tenant_id,
                sealed.c.subledger_posting_id == subledger_line.c.subledger_posting_id,
            ),
        )
        within = sealed.c.chain_seq <= chain_seq
    rows = session.execute(
        select(
            gl_account.c.code,
            gl_account.c.account_type,
            subledger_line.c.account_role,
            posting_period.c.fiscal_year,
            subledger_line.c.functional_currency,
            func.coalesce(
                func.sum(subledger_line.c.amount_functional).filter(within), Decimal(0)
            ).label("amount"),
            func.count().filter(within).label("held"),
            func.count().filter(~within).label("later"),
        )
        .select_from(lines)
        .where(
            subledger_line.c.entity_id == scope.entity_id,
            subledger_line.c.book_code == scope.book_code,
            subledger_line.c.period_end_date <= scope.end_date,
        )
        .group_by(
            gl_account.c.code,
            gl_account.c.account_type,
            subledger_line.c.account_role,
            posting_period.c.fiscal_year,
            subledger_line.c.functional_currency,
        )
    ).all()
    functional = scope.functional_currency.strip()
    balances: dict[str, Decimal] = {}
    by_role: dict[tuple[str, str], Decimal] = {}
    role_accounts: dict[str, set[str]] = {}
    accounts: set[str] = set()
    later = 0
    for row in rows:
        later += int(row.later)
        if not int(row.held):
            continue
        if str(row.functional_currency).strip() != functional:
            raise ValueError(
                f"subledger lines of {scope.entity_code} are stated in "
                f"{row.functional_currency}, not in its functional currency {functional}"
            )
        code = str(row.code)
        role = _text(row.account_role)
        accounts.add(code)
        role_accounts.setdefault(role, set()).add(code)
        if _text(row.account_type) in BALANCE_SHEET_TYPES or int(row.fiscal_year) == (
            windows.fiscal_year
        ):
            balances[code] = balances.get(code, Decimal(0)) + Decimal(row.amount)
            by_role[(code, role)] = by_role.get((code, role), Decimal(0)) + Decimal(row.amount)
    return _Subledger(
        balances=tuple(
            trial_balance.AccountBalance(account_code=code, amount=amount)
            for code, amount in sorted(balances.items())
        ),
        accounts=frozenset(accounts),
        later_lines=later,
        by_role=by_role,
        role_accounts={role: frozenset(codes) for role, codes in role_accounts.items()},
    )


def _control_role_accounts(
    session: Session, scope: gates.PeriodScope, as_of: datetime
) -> dict[str, frozenset[str]]:
    """Per contract balance role, the GL accounts the published account mapping in force at
    ``as_of`` gives it for the entity and book (T-REF-14, T-REF-15): subledger-controlled before
    the subledger's first line on them (supervisor rulings R-69 (c), R-74 (c))."""
    version = account_mapping_version
    mapped = account_mapping_rule
    found: dict[str, set[str]] = {}
    for role, code in session.execute(
        select(mapped.c.account_role, gl_account.c.code)
        .select_from(
            mapped.join(
                version,
                and_(
                    version.c.tenant_id == mapped.c.tenant_id,
                    version.c.id == mapped.c.account_mapping_version_id,
                ),
            ).join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == mapped.c.tenant_id,
                    gl_account.c.id == mapped.c.gl_account_id,
                ),
            )
        )
        .where(
            mapped.c.account_role.in_(CONTROL_ROLES),
            version.c.status == ConfigStatus.PUBLISHED.value,
            or_(version.c.effective_from.is_(None), version.c.effective_from <= as_of),
            or_(version.c.effective_to.is_(None), version.c.effective_to > as_of),
            or_(mapped.c.entity_id.is_(None), mapped.c.entity_id == scope.entity_id),
            or_(mapped.c.book_code.is_(None), mapped.c.book_code == scope.book_code),
        )
        .distinct()
    ):
        found.setdefault(_text(role), set()).add(str(code))
    return {role: frozenset(codes) for role, codes in found.items()}


def _mapped_accounts(mapped: Mapping[str, frozenset[str]]) -> frozenset[str]:
    return frozenset(code for codes in mapped.values() for code in codes)


def _period_ref(session: Session, scope: gates.PeriodScope) -> tie_outs.PeriodRef:
    """The reconciled period as the balance reader names one."""
    fiscal_year, period_no, quarter_no = session.execute(
        select(period.c.fiscal_year, period.c.period_no, period.c.quarter_no).where(
            period.c.id == scope.period_id
        )
    ).one()
    return tie_outs.PeriodRef(
        id=scope.period_id,
        key=scope.period_key,
        name=scope.period_name,
        fiscal_year=int(fiscal_year),
        period_no=int(period_no),
        quarter_no=None if quarter_no is None else int(quarter_no),
        start=scope.start_date,
        end=scope.end_date,
    )


def _functional_balances(
    session: Session, scope: gates.PeriodScope, rows: Sequence[tie_outs.BalanceRow]
) -> dict[tuple[UUID, UUID], dict[str, Decimal]]:
    """The stored functional balances (04 T-CON-09) of the member contracts in ``rows`` whose
    version's latest period is the reconciled one — the only period a functional balance is
    stored for — by (contract version, contract): the three role balances by their measure. The
    latest period of a member is the last one a balance node of its subject carries
    (``tie_outs.traced_balances``); a member whose stored transaction balances are not the
    period's is left out."""
    if not rows:
        return {}
    latest: dict[UUID, Mapping[str, str]] = {}
    for version_id in sorted({row.version_id for row in rows}, key=str):
        trace = trace_store.load_trace(session, version_id)
        nodes = () if trace is None else ((node.id, node.value) for node in trace.nodes)
        latest[version_id] = tie_outs.traced_balances(nodes).latest
    by_key = {
        (row.version_id, row.contract_id): row
        for row in rows
        if latest[row.version_id].get(contract_entity_subject_key(row.external_id, row.entity_code))
        == scope.period_key
    }
    if not by_key:
        return {}
    balance = contract_version_balance
    measures = [measure for measure, _ in POSITION_ROLES.values()]
    found: dict[tuple[UUID, UUID], dict[str, Decimal]] = {}
    for stored in session.execute(
        select(
            balance.c.contract_version_id,
            balance.c.contract_id,
            *(balance.c[f"{measure}_txn"] for measure in measures),
            *(balance.c[f"{measure}_functional"] for measure in measures),
        ).where(
            balance.c.entity_id == scope.entity_id,
            tuple_(balance.c.contract_version_id, balance.c.contract_id).in_(
                sorted(by_key, key=str)
            ),
        )
    ).mappings():
        key = (UUID(str(stored["contract_version_id"])), UUID(str(stored["contract_id"])))
        row = by_key[key]
        if all(Decimal(stored[f"{measure}_txn"]) == row.value(measure) for measure in measures):
            found[key] = {measure: Decimal(stored[f"{measure}_functional"]) for measure in measures}
    return found


def _role_balances(
    session: Session,
    scope: gates.PeriodScope,
    as_of: datetime,
    side: _Subledger,
    mapped: Mapping[str, frozenset[str]],
) -> tuple[trial_balance.RoleBalance, ...]:
    """The subledger side of the three contract balance roles on the role basis (module
    docstring; supervisor rulings R-69 (a), R-74): per role its accounts, and the stored closing
    balances of the entity's contracts in the functional currency with what other roles posted
    on those accounts — or why the role is not stated."""
    functional = scope.functional_currency.strip()
    reached = {
        role: mapped.get(role, frozenset()) | side.role_accounts.get(role, frozenset())
        for role in POSITION_ROLES
    }
    unreadable: tuple[tuple[str, str], ...] | None = None
    try:
        rows: tuple[tie_outs.BalanceRow, ...] = tie_outs.balances_at(
            session,
            entity_ids=[scope.entity_id],
            book_code=scope.book_code,
            period_keys={scope.entity_id: _period_ref(session, scope)},
            cutoff=as_of,
        )
    except tie_outs.BalanceUnreadable as refused:
        rows = ()
        unreadable = _contracts_named(session, scope, refused)
    measures = [measure for measure, _ in POSITION_ROLES.values()]
    foreign = [
        row
        for row in rows
        if row.currency != functional and any(row.value(measure) != 0 for measure in measures)
    ]
    stored = _functional_balances(session, scope, foreign)
    balances: list[trial_balance.RoleBalance] = []
    taken: set[str] = set()
    for role, (measure, sign) in POSITION_ROLES.items():
        codes = tuple(sorted(reached[role] - taken))
        taken |= reached[role]
        others = {
            other: reached[role] & reached[other]
            for other in POSITION_ROLES
            if other != role and reached[role] & reached[other]
        }
        amount = Decimal(0)
        missing: list[tie_outs.BalanceRow] = []
        for row in rows:
            value = row.value(measure)
            if value == 0:
                continue
            if row.currency == functional:
                amount += sign * value
                continue
            held = stored.get((row.version_id, row.contract_id))
            if held is None:
                missing.append(row)
            else:
                amount += sign * held[measure]
        # What other roles posted on the role's accounts is part of what the ledger holds there.
        amount += sum(
            (
                posted
                for (code, posted_role), posted in side.by_role.items()
                if code in codes and posted_role not in POSITION_ROLES
            ),
            Decimal(0),
        )
        not_stated: trial_balance.NotStated | None = None
        if unreadable is not None:
            reason = NOT_STATED_UNREADABLE.format(
                count=len(unreadable), period_key=scope.period_key
            )
            not_stated = trial_balance.NotStated(reason, unreadable)
        elif others:
            reason = NOT_STATED_SHARED.format(
                accounts=", ".join(sorted({code for found in others.values() for code in found})),
                role=role,
                others=" and ".join(others),
            )
            not_stated = trial_balance.NotStated(reason)
        elif missing:
            named = tuple(
                sorted({(str(row.contract_id), row.external_id) for row in missing}, key=_second)
            )
            reason = NOT_STATED_FOREIGN.format(
                count=len(named), functional=functional, period_key=scope.period_key
            )
            not_stated = trial_balance.NotStated(reason, named)
        if not_stated is None and not codes and amount == 0:
            continue  # a role without an account and without a balance has no row
        balances.append(
            trial_balance.RoleBalance(
                account_role=role,
                account_codes=codes,
                amount=None if not_stated is not None else amount,
                not_stated=not_stated,
            )
        )
    return tuple(balances)


def _second(pair: tuple[str, str]) -> tuple[str, str]:
    return (pair[1], pair[0])


def _contracts_named(
    session: Session, scope: gates.PeriodScope, refused: tie_outs.BalanceUnreadable
) -> tuple[tuple[str, str], ...]:
    """(contract id, external id) of the member contracts a ``BalanceUnreadable`` names — its
    errors carry ``balances[<external id>@<entity code>]`` — in external id order."""
    suffix = f"@{scope.entity_code}]"
    prefix = "balances["
    fields = [error.field for error in refused.errors if error.field is not None]
    named = sorted(
        {
            field[len(prefix) : -len(suffix)]
            for field in fields
            if field.startswith(prefix) and field.endswith(suffix)
        }
    )
    if not named:
        return ()
    found = {
        str(external_id): str(contract_id)
        for contract_id, external_id in session.execute(
            select(contract.c.id, contract.c.external_id).where(contract.c.external_id.in_(named))
        )
    }
    return tuple((found[name], name) for name in named if name in found)


def current_roles(
    session: Session, scope: gates.PeriodScope, known_at: datetime
) -> tuple[trial_balance.RoleBalance, ...]:
    """Read the role basis at the current committed chain position and knowledge cutoff."""
    head = session.scalar(
        select(ledger_chain_head.c.last_chain_seq).where(
            ledger_chain_head.c.book_code == scope.book_code
        )
    )
    side = _subledger_side(session, scope, _windows(session, scope), known_at, int(head or 0))
    return _role_balances(
        session, scope, known_at, side, _control_role_accounts(session, scope, known_at)
    )


def matches_roles(
    totals: Sequence[Mapping[str, Any]],
    roles: Sequence[trial_balance.RoleBalance],
    currency: str,
) -> bool:
    """Compare the complete signed role basis, including unstated reasons and membership.

    Decimal equality preserves every stored digit. Source amounts are deliberately excluded:
    they belong to the attached trial balance, not to the current subledger calculation.
    """
    stored = [row for row in totals if row.get("account_role") is not None]
    by_role = {row["account_role"]: row for row in stored}
    # compare() omits a zero role when the trial balance and findings carry nothing
    # for it. Absence represents zero, not an unknown amount. Keep a role when the
    # signed totals did show it, or when its current balance cannot be omitted.
    roles = tuple(
        role
        for role in roles
        if role.account_role in by_role or role.amount != 0 or role.not_stated is not None
    )
    if len(stored) != len(roles):
        return False
    if len(by_role) != len(stored):
        return False
    for role in roles:
        row = by_role.get(role.account_role)
        if row is None or str(row["currency"]).strip() != currency.strip():
            return False
        amount = row.get("subledger_amount")
        if (None if amount is None else Decimal(str(amount))) != role.amount:
            return False
        if tuple(sorted(row.get("account_codes", ()))) != tuple(sorted(role.account_codes)):
            return False
        not_stated = (
            None
            if role.not_stated is None
            else {
                "reason": role.not_stated.reason,
                "contracts": [
                    {"id": identifier, "external_id": name}
                    for identifier, name in role.not_stated.contracts
                ],
            }
        )
        if row.get("not_stated") != not_stated:
            return False
    return True
