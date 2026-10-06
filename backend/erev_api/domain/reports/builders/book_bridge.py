"""RPT-33 ``book_bridge`` Book-to-book bridge (SCREENS_B §5.6.6 RPT-33; POLICIES §6.2 (the IFRS 15
switch list), POL-011, POL-012, POL-144, POL-150 to POL-152, POL-160, POL-163; ENGINE_SPEC_B §13
S13-R-05, §13.2.3; 04 T-SL-04, T-CON-08, T-CON-09, table 10-T; 01 D-24, D-25; 03 REQ-BK-001,
REQ-BK-002, REQ-BK-006; answer key IFRS-SW01-COLLECTIBILITY-THRESHOLD-PER-BOOK; BUILD_SPEC RPS-12).

For one entity that keeps both the ``ASC606`` and the ``IFRS15`` book, over a period range, the
report compares the two books contract by contract:

- ``REVENUE``: the revenue the entity's subledger carries in each book over the range — credit
  less debit of its T-SL-04 ``REVENUE`` lines, recorded by the run's ``known_at``;
- ``CONTRACT_LIABILITY``, ``CONTRACT_ASSET``, ``UNBILLED_RECEIVABLE``, ``COST_ASSETS`` and
  ``LOSS_PROVISION``: the presented balances of each book at the end of the range
  (``tie_outs.balances_at``: the latest contract version of the book in the disclosures).

A difference is ASC 606 less IFRS 15. Each contract's difference in a measure has one driver,
identified from stored facts, in this order:

1. ``COLLECTIBILITY`` — the Step 1 conclusion differed between the books: at a computation
   recorded by the cutoff exactly one of them held the contract as not a contract (E-06
   ``NOT_A_CONTRACT``); or both books hold it as not a contract at their latest version, when
   revenue can arise only under ASC 606-10-25-7, whose event (c) is the POL-012 switch. Step 1 is
   assessed per book (the ``COLLECTIBILITY_ASSESSED`` and ``CONTRACT_CRITERIA_MET`` events name
   their book; POL-011, POL-012), and a contract that fails it in one book has no revenue and no
   contract balance there: every measure of that contract.
2. ``ONEROUS_CONTRACTS`` — the loss provision (POL-150 to POL-152 are the only switches that
   measure it).
3. ``COST_IMPAIRMENT_REVERSAL`` — the contract cost assets, when the IFRS 15 book posted an
   impairment reversal (JET-09d: a ``CONTRACT_COST_IMPAIRMENT`` debit of a cost-asset role) for
   the contract on or before the range end (POL-144).
4. ``OTHER`` — every other difference.

``ADVANCE_CONSIDERATION_FX`` is 0.00 by construction: the IFRIC 22 layer date (POL-160, POL-163)
moves functional amounts only, and the report serves transaction-currency amounts — the
``functional`` view (the default) only when every contract is in the entity's functional
currency, else it is refused by name. ``FRAMEWORK_ELECTIONS`` and ``LICENCE_RENEWALS`` cannot be
identified from stored facts in 1.0 (the switches of POLICIES §6.2 differ between the books of
every contract; which of them moved an amount is not stored): their effect is part of ``OTHER``.
Their cells show 0.00 when no contract's difference in the measure is left to ``OTHER`` — then
nothing can belong to them — and are empty otherwise, never an unsupported 0.00.

Section 1 "Summary by measure": ``row_key`` ``measure:<MEASURE>``; section 2 "Difference by
driver": ``row_key`` ``driver:<DRIVER>:<MEASURE>``, every driver for each measure in which a
contract differs; section 3 "By contract": ``row_key`` ``contract:<external id>:<MEASURE>``, one
row per contract and measure that differ. Keys of sections 1 and 2 gain ``:<ISO>`` when the run
holds several currencies. Tie-out ``TO_BRIDGE_DRIVERS_EQ_DIFFERENCE``: per measure and currency
the driver effects sum to the section 1 difference.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, contract_version, entity_book, subledger_line
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import FUNCTIONAL_ONLY, ranges
from erev_api.domain.reports.builders.out_of_period_register import refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, EntityRef, PeriodRef
from erev_api.enums import BookCode, ContractStatus
from erev_api.uow import UnitOfWork

CODE: Final = "book_bridge"
TO_BRIDGE_DRIVERS_EQ_DIFFERENCE: Final = tie_outs.TO_BRIDGE_DRIVERS_EQ_DIFFERENCE
DEFAULT_CURRENCY_VIEW: Final = "functional"  # SCREENS_B RPT-33 "default `functional`"
ASC606: Final = BookCode.ASC606.value
IFRS15: Final = BookCode.IFRS15.value
BOOKS: Final = (ASC606, IFRS15)
REVENUE: Final = "REVENUE"
NOT_A_CONTRACT: Final = ContractStatus.NOT_A_CONTRACT.value
IMPAIRMENT_KIND: Final = "CONTRACT_COST_IMPAIRMENT"  # E-29; a debit of an asset role is JET-09d
COST_ASSET_ROLES: Final = ("COST_TO_OBTAIN_ASSET", "COST_TO_FULFILL_ASSET")
MEASURES: Final = (
    REVENUE,
    "CONTRACT_LIABILITY",
    "CONTRACT_ASSET",
    "UNBILLED_RECEIVABLE",
    "COST_ASSETS",
    "LOSS_PROVISION",
)
MEASURE_LABELS: Final[Mapping[str, str]] = {
    REVENUE: "Revenue",
    "CONTRACT_LIABILITY": "Contract liability",
    "CONTRACT_ASSET": "Contract asset",
    "UNBILLED_RECEIVABLE": "Unbilled receivable",
    "COST_ASSETS": "Contract cost assets",
    "LOSS_PROVISION": "Loss provision",
}
# The T-CON-09 balance behind each balance measure.
BALANCE_OF: Final[Mapping[str, str]] = {
    "CONTRACT_LIABILITY": "contract_liability",
    "CONTRACT_ASSET": "contract_asset",
    "UNBILLED_RECEIVABLE": "unbilled_receivable",
    "COST_ASSETS": "cost_asset_carrying",
    "LOSS_PROVISION": "loss_provision",
}
COLLECTIBILITY: Final = "COLLECTIBILITY"
COST_IMPAIRMENT_REVERSAL: Final = "COST_IMPAIRMENT_REVERSAL"
ONEROUS_CONTRACTS: Final = "ONEROUS_CONTRACTS"
OTHER: Final = "OTHER"
DRIVERS: Final = (
    COLLECTIBILITY,
    COST_IMPAIRMENT_REVERSAL,
    "FRAMEWORK_ELECTIONS",
    "LICENCE_RENEWALS",
    ONEROUS_CONTRACTS,
    "ADVANCE_CONSIDERATION_FX",
    OTHER,
)
DRIVER_LABELS: Final[Mapping[str, str]] = {
    COLLECTIBILITY: "Collectibility",
    COST_IMPAIRMENT_REVERSAL: "Contract cost impairment reversal",
    "FRAMEWORK_ELECTIONS": "Framework elections",
    "LICENCE_RENEWALS": "Licence renewals",
    ONEROUS_CONTRACTS: "Onerous contracts",
    "ADVANCE_CONSIDERATION_FX": "Advance consideration FX (IFRIC 22)",
    OTHER: "Other",
}
# Drivers no stored fact identifies in 1.0: their effect is inside OTHER (module docstring).
UNIDENTIFIED: Final = ("FRAMEWORK_ELECTIONS", "LICENCE_RENEWALS")
ENTITY_REQUIRED: Final = "Choose an entity that keeps both the ASC 606 and IFRS 15 books."
MEASURE_PREFIX: Final = "measure:"
DRIVER_PREFIX: Final = "driver:"
CONTRACT_PREFIX: Final = "contract:"
COLUMNS: Final = (
    Column("section", "Section", "integer"),
    Column("measure_code", "Measure code", "code"),
    Column("measure_label", "Measure", "text"),
    Column("driver_code", "Driver code", "code"),
    Column("driver_label", "Driver", "text"),
    Column("contract_external_id", "Contract", "code"),
    Column("currency", "Currency", "code"),
    Column("asc606_amount", "ASC 606", "money"),
    Column("ifrs15_amount", "IFRS 15", "money"),
    Column("difference", "Difference", "money"),
    Column("effect", "Effect", "money"),
    Column("contracts_affected", "Contracts affected", "integer"),
)


@dataclass(frozen=True, slots=True)
class Compared:
    """One contract in both books — the input of ``dataset_rows``: its amount per measure in each
    book (a missing measure is 0), and the stored facts that identify a driver."""

    contract_external_id: str
    currency: str
    asc606: Mapping[str, Decimal] = field(default_factory=dict)
    ifrs15: Mapping[str, Decimal] = field(default_factory=dict)
    step1_differs: bool = False  # ``step1_differs`` over the contract's versions in both books
    impairment_reversed: bool = False  # the IFRS 15 book posted a JET-09d reversal

    def amounts(self, measure: str) -> tuple[Decimal, Decimal]:
        return self.asc606.get(measure, ZERO), self.ifrs15.get(measure, ZERO)

    def difference(self, measure: str) -> Decimal:
        """ASC 606 less IFRS 15, at the currency's minor unit."""
        first, second = self.amounts(measure)
        return tie_outs.quantized(first - second, self.currency)


def step1_differs(versions: Iterable[tuple[str, str, int, str]]) -> bool:
    """Rule 1 over a contract's versions in both books, each ``(computation, book code, version
    number, status in the book)``: true when a computation left exactly one of the two books
    holding the contract as not a contract, or when the latest version of each book holds it as
    not a contract. A computation that wrote one book only (the other was not kept then) compares
    nothing. Pure."""
    by_computation: dict[str, dict[str, str]] = {}
    latest: dict[str, tuple[int, str]] = {}
    for computation, book_code, version_no, status in versions:
        by_computation.setdefault(computation, {})[book_code] = status
        if book_code not in latest or version_no > latest[book_code][0]:
            latest[book_code] = (version_no, status)
    for statuses in by_computation.values():
        if len(statuses) == len(BOOKS) and (statuses[ASC606] == NOT_A_CONTRACT) != (
            statuses[IFRS15] == NOT_A_CONTRACT
        ):
            return True
    return len(latest) == len(BOOKS) and all(
        status == NOT_A_CONTRACT for _, status in latest.values()
    )


def driver_of(item: Compared, measure: str) -> str:
    """The driver of one contract's difference in ``measure`` (module docstring, rules 1 to 4).
    Pure."""
    if item.step1_differs:
        return COLLECTIBILITY
    if measure == "LOSS_PROVISION":
        return ONEROUS_CONTRACTS
    if measure == "COST_ASSETS" and item.impairment_reversed:
        return COST_IMPAIRMENT_REVERSAL
    return OTHER


def check_view(view: str, found: Iterable[Compared], *, functional_currency: str) -> None:
    """``transaction`` always; another view only when every contract is in the entity's
    functional currency, else refused by name (as RPT-03)."""
    if view != "transaction" and any(item.currency != functional_currency for item in found):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


def dataset_rows(
    found: Iterable[Compared],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """(rows of sections 1 to 3, control totals, the ``TO_BRIDGE_DRIVERS_EQ_DIFFERENCE`` result).
    Pure."""
    listed = sorted(
        (
            item
            for item in found
            if any(amount != 0 for measure in MEASURES for amount in item.amounts(measure))
        ),
        key=lambda item: item.contract_external_id,
    )
    # currency → measure → [ASC 606, IFRS 15]
    sums: dict[str, dict[str, list[Decimal]]] = {}
    # (currency, measure) → driver → [effect, contracts affected]
    effects: dict[tuple[str, str], dict[str, list[Any]]] = {}
    contract_rows: list[dict[str, Any]] = []
    for item in listed:
        into = sums.setdefault(item.currency, {measure: [ZERO, ZERO] for measure in MEASURES})
        for measure in MEASURES:
            first, second = item.amounts(measure)
            into[measure][0] += first
            into[measure][1] += second
            difference = item.difference(measure)
            if difference == 0:
                continue
            driver = driver_of(item, measure)
            by_driver = effects.setdefault(
                (item.currency, measure), {code: [ZERO, 0] for code in DRIVERS}
            )
            by_driver[driver][0] += difference
            by_driver[driver][1] += 1
            contract_rows.append(
                {
                    "row_key": f"{CONTRACT_PREFIX}{item.contract_external_id}:{measure}",
                    "section": 3,
                    "contract_external_id": item.contract_external_id,
                    "driver_code": driver,
                    "driver_label": DRIVER_LABELS[driver],
                    "measure_code": measure,
                    "measure_label": MEASURE_LABELS[measure],
                    "currency": item.currency,
                    "asc606_amount": tie_outs.money(first, item.currency),
                    "ifrs15_amount": tie_outs.money(second, item.currency),
                    "difference": tie_outs.money(difference, item.currency),
                }
            )
    mixed = len(sums) > 1
    rows: list[dict[str, Any]] = []
    expected: dict[str, Decimal] = {}
    actual: dict[str, Decimal] = {}
    ties = True
    for currency in sorted(sums):
        suffix = f":{currency}" if mixed else ""
        for measure in MEASURES:
            first, second = sums[currency][measure]
            rows.append(
                {
                    "row_key": f"{MEASURE_PREFIX}{measure}{suffix}",
                    "section": 1,
                    "measure_code": measure,
                    "measure_label": MEASURE_LABELS[measure],
                    "currency": currency,
                    "asc606_amount": tie_outs.money(first, currency),
                    "ifrs15_amount": tie_outs.money(second, currency),
                    "difference": tie_outs.money(first - second, currency),
                }
            )
            tie_outs.add(expected, currency, first - second)
            by_driver = effects.get((currency, measure), {})
            explained = sum((entry[0] for entry in by_driver.values()), ZERO)
            tie_outs.add(actual, currency, explained)
            ties = ties and tie_outs.quantized(first - second, currency) == tie_outs.quantized(
                explained, currency
            )
    for currency in sorted(sums):
        suffix = f":{currency}" if mixed else ""
        for measure in MEASURES:
            differing = effects.get((currency, measure))
            if differing is None:
                continue  # no contract differs in this measure
            unattributed = differing[OTHER][1] > 0
            for driver in DRIVERS:
                effect, affected = differing[driver]
                hidden = driver in UNIDENTIFIED and unattributed
                rows.append(
                    {
                        "row_key": f"{DRIVER_PREFIX}{driver}:{measure}{suffix}",
                        "section": 2,
                        "driver_code": driver,
                        "driver_label": DRIVER_LABELS[driver],
                        "measure_code": measure,
                        "measure_label": MEASURE_LABELS[measure],
                        "currency": currency,
                        "effect": None if hidden else tie_outs.money(effect, currency),
                        "contracts_affected": None if hidden else affected,
                    }
                )
    rows.extend(contract_rows)
    tie = tie_outs.compared(TO_BRIDGE_DRIVERS_EQ_DIFFERENCE, expected, actual)
    if not ties:  # two measures that offset each other are two breaks, not a tie
        tie["result"] = tie_outs.FAIL
    totals = {
        "contract_count": len(listed),
        "revenue_asc606": tie_outs.by_currency({c: v[REVENUE][0] for c, v in sums.items()}),
        "revenue_ifrs15": tie_outs.by_currency({c: v[REVENUE][1] for c, v in sums.items()}),
        "revenue_difference": tie_outs.by_currency(
            {c: v[REVENUE][0] - v[REVENUE][1] for c, v in sums.items()}
        ),
        "other_effect": tie_outs.by_currency(
            {
                currency: sum(
                    (
                        effects[(currency, measure)][OTHER][0]
                        for measure in MEASURES
                        if (currency, measure) in effects
                    ),
                    ZERO,
                )
                for currency in sums
            }
        ),
    }
    return rows, totals, tie


# --- reads --------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Contract:
    external_id: str
    currency: str
    asc606: dict[str, Decimal] = field(default_factory=dict)
    ifrs15: dict[str, Decimal] = field(default_factory=dict)

    def book(self, code: str) -> dict[str, Decimal]:
        return self.asc606 if code == ASC606 else self.ifrs15


def _keeps_both(session: Session, entity: EntityRef) -> bool:
    kept = set(
        session.execute(
            select(entity_book.c.book_code).where(
                entity_book.c.entity_id == entity.id, entity_book.c.is_enabled.is_(True)
            )
        ).scalars()
    )
    return {ASC606, IFRS15} <= {str(code) for code in kept}


def _revenue(
    session: Session,
    params: ReportParams,
    entity: EntityRef,
    items: Sequence[PeriodRef],
    into: dict[UUID, _Contract],
) -> None:
    """The entity's revenue per contract and book over ``items``: credit less debit of the
    ``REVENUE`` lines recorded by ``known_at``."""
    statement = (
        select(
            subledger_line.c.contract_id,
            contract.c.external_id,
            subledger_line.c.book_code,
            subledger_line.c.txn_currency,
            func.sum(subledger_line.c.amount_txn).label("amount"),
        )
        .select_from(
            subledger_line.join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            )
        )
        .where(
            subledger_line.c.book_code.in_(list(BOOKS)),
            subledger_line.c.entity_id == entity.id,
            subledger_line.c.account_role == REVENUE,
            subledger_line.c.period_id.in_([item.id for item in items]),
            subledger_line.c.recorded_at <= params.known_at,
        )
        .group_by(
            subledger_line.c.contract_id,
            contract.c.external_id,
            subledger_line.c.book_code,
            subledger_line.c.txn_currency,
        )
        .order_by(contract.c.external_id, subledger_line.c.book_code)
    )
    for row in session.execute(statement).mappings():
        found = into.setdefault(
            UUID(str(row["contract_id"])),
            _Contract(str(row["external_id"]), str(row["txn_currency"]).strip()),
        )
        amounts = found.book(str(row["book_code"]))
        # a revenue line is a credit: signed debit positive (T-SL-04)
        amounts[REVENUE] = amounts.get(REVENUE, ZERO) - Decimal(row["amount"])


def _balances(
    session: Session,
    params: ReportParams,
    entity: EntityRef,
    last: PeriodRef,
    into: dict[UUID, _Contract],
) -> None:
    """The presented balances of each book at the end of ``last``."""
    cutoff = tie_outs.cutoff_for(session, params)
    for book_code in BOOKS:
        for row in tie_outs.balances_at(
            session,
            entity_ids=(entity.id,),
            book_code=book_code,
            period_keys={entity.id: last},
            cutoff=cutoff,
            params=params,
        ):
            found = into.setdefault(row.contract_id, _Contract(row.external_id, row.currency))
            amounts = found.book(book_code)
            for measure, balance in BALANCE_OF.items():
                amounts[measure] = row.value(balance)


def _step1_differs(
    session: Session, params: ReportParams, contracts: Mapping[UUID, _Contract]
) -> set[UUID]:
    """The contracts whose Step 1 conclusion differed between the books (``step1_differs``), from
    the versions of both books recorded by the cutoff. A version is of the contract's combination
    group (T-CON-08)."""
    if not contracts:
        return set()
    cutoff = tie_outs.cutoff_for(session, params)
    statement = (
        select(
            contract.c.id,
            contract_version.c.contract_computation_id,
            contract_version.c.book_code,
            contract_version.c.version_no,
            contract_version.c.status_in_book,
        )
        .select_from(
            contract.join(
                contract_version,
                and_(
                    contract_version.c.tenant_id == contract.c.tenant_id,
                    contract_version.c.combination_group_id == contract.c.combination_group_id,
                ),
            )
        )
        .where(
            contract.c.id.in_(sorted(contracts, key=str)),
            contract_version.c.book_code.in_(list(BOOKS)),
            contract_version.c.known_at <= cutoff,
        )
        .order_by(contract.c.id, contract_version.c.book_code, contract_version.c.version_no)
    )
    versions: dict[UUID, list[tuple[str, str, int, str]]] = {}
    for contract_id, computation_id, book_code, version_no, status in session.execute(statement):
        versions.setdefault(UUID(str(contract_id)), []).append(
            (str(computation_id), str(book_code), int(version_no), str(status))
        )
    return {contract_id for contract_id, found in versions.items() if step1_differs(found)}


def _impairment_reversed(
    session: Session, params: ReportParams, entity: EntityRef, last: PeriodRef
) -> set[UUID]:
    """The contracts whose cost assets the IFRS 15 book reversed an impairment of (JET-09d) on or
    before the end of ``last``."""
    statement = (
        select(subledger_line.c.contract_id)
        .where(
            subledger_line.c.book_code == IFRS15,
            subledger_line.c.entity_id == entity.id,
            subledger_line.c.entry_kind == IMPAIRMENT_KIND,
            subledger_line.c.account_role.in_(list(COST_ASSET_ROLES)),
            subledger_line.c.amount_txn > 0,
            subledger_line.c.period_end_date <= last.end,
            subledger_line.c.recorded_at <= params.known_at,
        )
        .distinct()
    )
    return {UUID(str(value)) for value in session.execute(statement).scalars()}


def sources(
    session: Session, params: ReportParams, entity: EntityRef, items: Sequence[PeriodRef]
) -> list[Compared]:
    """Every contract of the entity with an amount in either book over ``items``."""
    contracts: dict[UUID, _Contract] = {}
    _revenue(session, params, entity, items, contracts)
    _balances(session, params, entity, items[-1], contracts)
    differing = _step1_differs(session, params, contracts)
    reversed_ids = _impairment_reversed(session, params, entity, items[-1])
    return [
        Compared(
            contract_external_id=found.external_id,
            currency=found.currency,
            asc606=dict(found.asc606),
            ifrs15=dict(found.ifrs15),
            step1_differs=contract_id in differing,
            impairment_reversed=contract_id in reversed_ids,
        )
        for contract_id, found in sorted(contracts.items(), key=lambda pair: pair[1].external_id)
    ]


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    session = uow.session
    entities, periods, _ = ranges(session, params)
    if len(entities) != 1 or not _keeps_both(session, entities[0]):
        raise tie_outs.invalid("entity_codes", ENTITY_REQUIRED)
    (entity,) = entities
    items = periods[entity.id]
    found = sources(session, params, entity, items) if items else []
    check_view(
        str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW),
        found,
        functional_currency=entity.functional_currency,
    )
    rows, totals, tie = dataset_rows(found)
    return ReportData(
        columns=COLUMNS, rows=tuple(rows), control_totals=totals, tie_out_results=(tie,)
    )


__all__ = [
    "CODE",
    "COLUMNS",
    "DEFAULT_CURRENCY_VIEW",
    "DRIVERS",
    "DRIVER_LABELS",
    "ENTITY_REQUIRED",
    "MEASURES",
    "MEASURE_LABELS",
    "TO_BRIDGE_DRIVERS_EQ_DIFFERENCE",
    "UNIDENTIFIED",
    "Compared",
    "build",
    "check_view",
    "dataset_rows",
    "driver_of",
    "sources",
    "step1_differs",
]
